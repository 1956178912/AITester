#!/usr/bin/env python3
"""J-4（2026-10-17）覆盖率补口：仓库级执行器的缓存 / 安装 / 守卫分支。

动机：``src/agents/executor_repo.py`` 在补口前有 118 行未覆盖，且缺失面集中在
**环境准备与降级路径**（setup 缓存复检、P0 4.3 venv 复用、官方 swebench harness
降级、M3 基线 P2P 门禁、S6 conftest 扫描 fail-closed）。这些分支的特征是
"平时不走、走的时候正是出问题的时候"——未覆盖即意味着**降级口径从未被验证过**：
指纹命中却重装、标记名与 use_venv 不对齐、官方 harness 返回值形状与自建口径
不同构、P2P 门禁该拦未拦，都会静默改变实验裁决。

纪律：零 LLM、零网络、零真实 git / pip / venv / swebench。全部经模块内唯一子
进程收敛点 ``_run`` 的 monkeypatch + ``tmp_path`` 假文件系统驱动；``SWE_REPO_ENVS_DIR``
一律指向 tmp_path，绝不写 ``~/.cache/aitester/repo_envs``。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest

import src.agents.executor_repo as repo_mod
from src.agents.executor_repo import RepoExecutor

_COMMIT = "0123456789abcdef0123456789abcdef01234567"
_REPO_URL = "https://github.com/foo/bar.git"


def _proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["cmd"], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """替换模块内 ``_run``，记录调用并按脚本返回（缺省一律 rc=0）。

    ``results`` 元素既可以是 ``CompletedProcess``，也可以是接受
    ``(cmd, cwd, timeout)`` 并返回 CompletedProcess 的可调用——用于"子进程跑完
    后按副作用落盘"的官方 harness 成功场景。
    """
    state: dict[str, Any] = {"calls": [], "results": [], "raise_on": None}

    def _fake_run(cmd, cwd, timeout, env=None):
        state["calls"].append({"cmd": list(cmd), "cwd": cwd, "timeout": timeout})
        if state["raise_on"] is not None:
            raise state["raise_on"]
        res = state["results"].pop(0) if state["results"] else _proc()
        return res(cmd, cwd, timeout) if callable(res) else res

    monkeypatch.setattr(repo_mod, "_run", _fake_run)
    return state


@pytest.fixture
def envs_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """仓库环境缓存根指向 tmp_path（setup() 会在此下建目录 / 写标记）。"""
    root = tmp_path / "repo_envs"
    monkeypatch.setenv("SWE_REPO_ENVS_DIR", str(root))
    return root


def _paths(executor: RepoExecutor, commit: str = _COMMIT) -> tuple[str, str, str]:
    """按 setup() 的目录口径复算 (env_dir, repo_dir, shared_venv_dir)。"""
    env_dir = os.path.join(executor.env_root, "bar", commit[:12])
    return env_dir, os.path.join(env_dir, "repo"), os.path.join(executor.env_root, "bar", "_shared_venv")


@pytest.mark.unit
class TestDepFingerprint:
    """P0 4.3 依赖指纹（决定是否复用 venv）——纯文件系统、零子进程。"""

    def test_no_dep_files_returns_no_deps(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
        assert RepoExecutor()._dep_fingerprint(str(tmp_path)) == "no-deps"

    def test_missing_repo_dir_returns_no_deps(self, tmp_path: Path):
        assert RepoExecutor()._dep_fingerprint(str(tmp_path / "absent")) == "no-deps"

    def test_source_only_change_keeps_fingerprint(self, tmp_path: Path):
        (tmp_path / "requirements.txt").write_text("click==8.0\n", encoding="utf-8")
        (tmp_path / "pkg.py").write_text("def f(): ...\n", encoding="utf-8")
        before = RepoExecutor()._dep_fingerprint(str(tmp_path))
        (tmp_path / "pkg.py").write_text("def f(): return 2\n", encoding="utf-8")
        assert RepoExecutor()._dep_fingerprint(str(tmp_path)) == before, "源码变更不应触发依赖重装"

    def test_dependency_change_switches_fingerprint(self, tmp_path: Path):
        (tmp_path / "requirements.txt").write_text("click==8.0\n", encoding="utf-8")
        before = RepoExecutor()._dep_fingerprint(str(tmp_path))
        (tmp_path / "requirements.txt").write_text("click==8.1\n", encoding="utf-8")
        assert RepoExecutor()._dep_fingerprint(str(tmp_path)) != before

    def test_concatenation_order_is_sorted_requirements_then_manifests(self, tmp_path: Path):
        # 锁定拼接口径：requirements*.txt 按文件名字典序，其后 pyproject/setup.py/setup.cfg
        (tmp_path / "requirements-dev.txt").write_bytes(b"dev\n")
        (tmp_path / "requirements.txt").write_bytes(b"base\n")
        (tmp_path / "setup.py").write_bytes(b"setup\n")
        expected = hashlib.sha256(b"dev\nbase\nsetup\n").hexdigest()
        assert RepoExecutor()._dep_fingerprint(str(tmp_path)) == expected

    def test_requirements_named_prefix_dir_is_ignored(self, tmp_path: Path):
        # `requirements.txt.bak` / 目录形态的 requirements* 都不入指纹
        (tmp_path / "requirements.txt.bak").write_text("junk\n", encoding="utf-8")
        (tmp_path / "requirements").mkdir()
        assert RepoExecutor()._dep_fingerprint(str(tmp_path)) == "no-deps"

    def test_requirements_txt_as_directory_is_ignored(self, tmp_path: Path):
        # 名字恰为 requirements.txt 但形态是目录：名单命中、isfile 不命中，
        # 不得因 open(目录) 抛 IsADirectoryError 把整个 setup 打断。
        (tmp_path / "requirements.txt").mkdir()
        assert RepoExecutor()._dep_fingerprint(str(tmp_path)) == "no-deps"


@pytest.mark.unit
class TestSplitDiffHunksExtraShapes:
    """``_split_diff_hunks`` 的两条残余分支（hunk 内非法行 / no-newline 标记）。"""

    def test_no_newline_marker_is_skipped(self):
        patch_text = "@@ -1,1 +1,1 @@\n+a\n\\ No newline at end of file\n"
        hunks = RepoExecutor._split_diff_hunks(patch_text)
        assert hunks == [(["a"], [], ["a"])]

    def test_illegal_line_closes_hunk_and_drops_trailing_content(self):
        # hunk 内非法前缀行（index 头）→ 收尾当前 hunk 并退出 hunk 态；
        # 后续 +b 因不在 hunk 内被丢弃（直到下一个 @@ 才重新开 hunk）。
        patch_text = "@@ -1 +1 @@\n+a\nindex 111..222 100644\n+b\n"
        hunks = RepoExecutor._split_diff_hunks(patch_text)
        assert hunks == [(["a"], [], ["a"])]
        assert all("index" not in "".join(a + b + c) for a, b, c in hunks), "非法行本身不得入任何切片"

    def test_leading_space_diff_header_is_context_not_illegal(self):
        # 锁定 L1074 口径：带 " " 前缀的行一律按上下文处理（含误带前缀的 diff --git），
        # 不会提前收尾 hunk——这正是 LLM 输出里最常见的形态。
        patch_text = "@@ -1 +1 @@\n+a\n diff --git a/x.py b/x.py\n"
        assert RepoExecutor._split_diff_hunks(patch_text) == [
            (["a", "diff --git a/x.py b/x.py"], ["diff --git a/x.py b/x.py"], ["a"])
        ]

    def test_second_hunk_header_flushes_previous(self):
        patch_text = "@@ -1 +1 @@\n+a\n@@ -9 +9 @@\n+b\n"
        assert RepoExecutor._split_diff_hunks(patch_text) == [(["a"], [], ["a"]), (["b"], [], ["b"])]

    def test_empty_hunk_is_not_flushed(self):
        # 连续两个 @@ 之间没有内容行 → _flush 的三个列表全空，不得产出空 hunk
        # （空 hunk 会让下游把"零新增行"当成一个可审查切片）。
        assert RepoExecutor._split_diff_hunks("@@ -1 +1 @@\n@@ -2 +2 @@\n") == []


@pytest.mark.unit
class TestCreateVenv:
    def test_existing_venv_python_short_circuits(self, tmp_path: Path, recorder: dict[str, Any]):
        vpy = tmp_path / "venv" / "bin" / "python"
        vpy.parent.mkdir(parents=True)
        vpy.write_text("", encoding="utf-8")
        assert RepoExecutor()._create_venv(str(tmp_path)) is None
        assert recorder["calls"] == [], "已有 venv 不应再跑 python -m venv"

    def test_nonzero_returncode_returns_error_text(self, tmp_path: Path, recorder: dict[str, Any]):
        recorder["results"] = [_proc(1, "", "ensurepip failed")]
        err = RepoExecutor()._create_venv(str(tmp_path))
        assert err and "ensurepip failed" in err

    def test_zero_returncode_but_missing_python_returns_error(self, tmp_path: Path, recorder: dict[str, Any]):
        recorder["results"] = [_proc(0)]
        assert RepoExecutor()._create_venv(str(tmp_path)), "rc=0 但 venv/bin/python 不存在必须判失败"

    def test_success_returns_none(self, tmp_path: Path, recorder: dict[str, Any]):
        vpy = tmp_path / "venv" / "bin" / "python"

        def _runner(_cmd, _cwd, _timeout):
            vpy.parent.mkdir(parents=True, exist_ok=True)
            vpy.write_text("", encoding="utf-8")  # 模拟 venv 建成
            return _proc(0)

        recorder["results"] = [_runner]
        assert RepoExecutor()._create_venv(str(tmp_path)) is None


@pytest.mark.unit
class TestPipInstallLegs:
    def test_venv_pip_install_skips_without_manifest(self, tmp_path: Path, recorder: dict[str, Any]):
        assert RepoExecutor()._venv_pip_install(str(tmp_path), str(tmp_path)) is None
        assert recorder["calls"] == []

    def test_venv_pip_install_uses_venv_python_and_reports_failure(self, tmp_path: Path, recorder: dict[str, Any]):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "setup.py").write_text("from setuptools import setup\nsetup()\n", encoding="utf-8")
        venv_env = tmp_path / "env"
        recorder["results"] = [_proc(1, "", "ResolutionImpossible")]
        err = RepoExecutor()._venv_pip_install(str(repo), str(venv_env))
        assert err and "ResolutionImpossible" in err
        assert recorder["calls"][0]["cmd"][0] == os.path.join(str(venv_env), "venv", "bin", "python")

    def test_venv_pip_install_success_returns_none(self, tmp_path: Path, recorder: dict[str, Any]):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        recorder["results"] = [_proc(0)]
        assert RepoExecutor()._venv_pip_install(str(repo), str(tmp_path / "env")) is None

    def test_editable_install_skips_without_manifest(self, tmp_path: Path, recorder: dict[str, Any]):
        assert RepoExecutor()._pip_install_editable(str(tmp_path)) is None
        assert recorder["calls"] == []

    def test_editable_install_failure_text(self, tmp_path: Path, recorder: dict[str, Any]):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        recorder["results"] = [_proc(1, "", "network unreachable")]
        assert "network unreachable" in (RepoExecutor()._pip_install_editable(str(repo)) or "")

    def test_editable_install_success(self, tmp_path: Path, recorder: dict[str, Any]):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "setup.py").write_text("setup()\n", encoding="utf-8")
        recorder["results"] = [_proc(0)]
        assert RepoExecutor()._pip_install_editable(str(repo)) is None


@pytest.mark.unit
class TestCloneWithoutGit:
    def test_git_unavailable_returns_error_before_any_subprocess(
        self, tmp_path: Path, recorder: dict[str, Any], monkeypatch
    ):
        monkeypatch.setattr(repo_mod.shutil, "which", lambda _exe: None)
        err = RepoExecutor()._clone_and_checkout(_REPO_URL, _COMMIT, str(tmp_path / "repo"))
        assert err == "git 不可用，无法准备仓库环境"
        assert recorder["calls"] == []

    def test_partial_clone_failure_then_full_clone_retry(self, tmp_path: Path, recorder: dict[str, Any]):
        # 部分克隆（--filter=blob:none）失败 → rmtree 残留后重试全量 clone；
        # 重试成功即继续 checkout（退化方向是"多花一次 clone"，不是误判失败）。
        recorder["results"] = [_proc(1, "", "filtered clone rejected"), _proc(0), _proc(0)]
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()  # 故意留残留目录，验证重试前的 rmtree
        assert RepoExecutor()._clone_and_checkout(_REPO_URL, _COMMIT, str(repo_dir)) is None
        cmds = [c["cmd"] for c in recorder["calls"]]
        assert "--filter=blob:none" in cmds[0], "首腿须是部分克隆"
        assert "--filter=blob:none" not in cmds[1], "重试腿必须退回全量克隆（否则同样失败）"
        assert cmds[2][:2] == ["git", "checkout"]
        assert not repo_dir.exists(), "重试前必须 rmtree 掉部分克隆的残留（否则全量 clone 撞已有目录）"

    def test_both_clone_legs_fail_returns_error(self, tmp_path: Path, recorder: dict[str, Any]):
        recorder["results"] = [_proc(1, "", "partial down"), _proc(128, "", "dns fail")]
        err = RepoExecutor()._clone_and_checkout(_REPO_URL, _COMMIT, str(tmp_path / "repo"))
        assert err == "git clone 失败: dns fail"

    def test_checkout_failure_reported(self, tmp_path: Path, recorder: dict[str, Any]):
        recorder["results"] = [_proc(0), _proc(1, "", "reference is not a tree")]
        assert "reference is not a tree" in (
            RepoExecutor()._clone_and_checkout(_REPO_URL, _COMMIT, str(tmp_path / "repo")) or ""
        )


@pytest.mark.unit
class TestConftestScanFailClosed:
    """S6 conftest 扫描的体积上限、读失败侧与分层裁决（G 轮 fail-closed 决策）。"""

    def test_oversize_conftest_refused(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(RepoExecutor, "_CONFTEST_SCAN_MAX_BYTES", 16)
        (tmp_path / "conftest.py").write_text("x = 1  # " + "a" * 200 + "\n", encoding="utf-8")
        assert RepoExecutor._scan_repo_conftests(str(tmp_path)) == [("conftest.py", ["<oversize>"])]

    def test_unreadable_conftest_refused(self, tmp_path: Path):
        os.symlink(str(tmp_path / "nowhere.py"), str(tmp_path / "conftest.py"))
        assert RepoExecutor._scan_repo_conftests(str(tmp_path)) == [("conftest.py", ["<unreadable>"])]

    def test_skip_dirs_are_pruned(self, tmp_path: Path):
        broken = tmp_path / ".venv" / "conftest.py"
        broken.parent.mkdir()
        broken.write_text("def (:\n", encoding="utf-8")
        assert RepoExecutor._scan_repo_conftests(str(tmp_path)) == []

    def test_unparseable_conftest_refused(self, tmp_path: Path):
        (tmp_path / "conftest.py").write_text("def (:\n", encoding="utf-8")
        assert RepoExecutor._scan_repo_conftests(str(tmp_path)) == [("conftest.py", ["<unparseable>"])]

    def test_tier1_hit_is_hard_refused(self, tmp_path: Path):
        (tmp_path / "conftest.py").write_text("import os\n\nos.system('id')\n", encoding="utf-8")
        assert RepoExecutor._scan_repo_conftests(str(tmp_path)) == [("conftest.py", ["os.system"])]

    def test_tier2_hit_warns_but_does_not_block(self, tmp_path: Path):
        # Tier 2（subprocess/socket/urllib/shutil.rmtree）是真实测试基建常用能力，
        # 硬拒会把近两成真实仓库挡在门外 → 仅 WARNING 留审计线索（G 轮分层决策）。
        (tmp_path / "conftest.py").write_text("import subprocess\n\nsubprocess.run(['ls'])\n", encoding="utf-8")
        assert RepoExecutor._scan_repo_conftests(str(tmp_path)) == []

    def test_clean_conftest_passes(self, tmp_path: Path):
        (tmp_path / "conftest.py").write_text(
            "import pytest\n\n\n@pytest.fixture\ndef fix():\n    return 1\n", encoding="utf-8"
        )
        assert RepoExecutor._scan_repo_conftests(str(tmp_path)) == []

    def test_switch_off_short_circuits_whole_scan(self, tmp_path: Path, monkeypatch):
        # J-2 收敛后的 fail-closed 口径站点：CONTEST_AST_SCAN_ENABLE=false 显式关闭
        # 守卫时连"读不懂也拒"一并失效（这是唯一的 opt-out 通道，须如实生效）。
        (tmp_path / "conftest.py").write_text("def (:\n", encoding="utf-8")
        monkeypatch.setenv("CONTEST_AST_SCAN_ENABLE", "false")
        assert RepoExecutor._scan_repo_conftests(str(tmp_path)) == []

    def test_run_test_nodes_refuses_before_any_pytest(self, tmp_path: Path, recorder: dict[str, Any], monkeypatch):
        monkeypatch.setattr(
            RepoExecutor, "_scan_repo_conftests", classmethod(lambda cls, _d: [("conftest.py", ["<oversize>"])])
        )
        out = RepoExecutor()._run_test_nodes(str(tmp_path), ["tests/test_a.py::x", "tests/test_a.py::y"])
        assert out["expected"] == 2 and out["passed"] == 0
        assert [c["name"] for c in out["failed_cases"]] == ["tests/test_a.py::x", "tests/test_a.py::y"]
        assert "守卫拒绝执行" in out["failed_cases"][0]["error"]
        assert recorder["calls"] == [], "守卫硬拒必须拦在任何 pytest 子进程之前"


@pytest.mark.unit
class TestOfficialSwebenchHarness:
    """M3 官方 harness 的四条降级 / 成功腿（返回值须与自建口径同构）。"""

    def _executor(self) -> RepoExecutor:
        return RepoExecutor(timeout=5, setup_timeout=5)

    def test_nonzero_returncode_degrades_to_none(self, recorder: dict[str, Any], tmp_path: Path, monkeypatch):
        recorder["results"] = [_proc(1, "", "No module named swebench")]
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        assert self._executor()._run_official_swebench_harness(_REPO_URL, _COMMIT, "", "", ["a"], []) is None

    def test_missing_report_degrades_to_none(self, recorder: dict[str, Any], tmp_path: Path, monkeypatch):
        recorder["results"] = [_proc(0)]
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        assert self._executor()._run_official_swebench_harness(_REPO_URL, _COMMIT, "", "", ["a"], []) is None
        assert list(tmp_path.iterdir()) == [], "降级后临时输入文件必须清理"

    def test_report_resolved_maps_to_self_built_shape(self, recorder: dict[str, Any], tmp_path: Path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

        def _runner(_cmd, _cwd, _timeout):
            # 模拟官方 runner 的副作用：与 pred_file 同目录落 report.json
            pred = next(tmp_path.glob("aitester_swebench_pred_*.json"))
            pred.with_name(pred.stem + "_report.json").write_text(
                json.dumps({"resolved": True, "fail_to_pass_pass": 2, "pass_to_pass_pass": 3}), encoding="utf-8"
            )
            return _proc(0)

        recorder["results"] = [_runner]
        out = self._executor()._run_official_swebench_harness(
            _REPO_URL, _COMMIT, "tp", "lp", ["a", "b"], ["c", "d", "e"]
        )
        assert out == {
            "passed": True,
            "fail_to_pass": {"expected": 2, "passed": 2},
            "pass_to_pass": {"expected": 3, "passed": 3},
            "harness_invalid": False,
            "output": "[M3 官方 swebench harness] resolved=True",
        }
        assert list(tmp_path.iterdir()) == [], "成功路径同样要清理 pred/report 两个临时文件"

    def test_subprocess_exception_degrades_to_none(self, recorder: dict[str, Any], tmp_path: Path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        recorder["raise_on"] = OSError("exec fail")
        assert self._executor()._run_official_swebench_harness(_REPO_URL, _COMMIT, "", "", ["a"], []) is None
        assert list(tmp_path.iterdir()) == []

    def test_report_dir_unreadable_degrades_and_swallows_cleanup_error(
        self, recorder: dict[str, Any], tmp_path: Path, monkeypatch
    ):
        # finally 里 os.remove 失败（report 路径被占用为目录）只吞异常、不得把降级
        # 路径炸成抛出——官方 harness 是"尽力而为"支路，清理失败不构成新故障。
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        pred = tmp_path / f"aitester_swebench_pred_{os.getpid()}_{threading.get_ident()}.json"
        pred.with_name(pred.stem + "_report.json").mkdir()
        recorder["results"] = [_proc(0)]
        assert self._executor()._run_official_swebench_harness(_REPO_URL, _COMMIT, "", "", ["a"], []) is None
        assert pred.with_name(pred.stem + "_report.json").is_dir(), "清理失败被吞（不抛出）"


@pytest.mark.unit
class TestSetupLockRecheck:
    """Z3 锁内复检命中（首轮 checkout 漂移、复检命中）——230-231。"""

    def test_first_check_drifts_then_lock_recheck_hits(self, envs_root: Path, recorder: dict[str, Any]):
        ex = RepoExecutor()
        env_dir, repo_dir, _ = _paths(ex)
        os.makedirs(repo_dir)
        with open(os.path.join(env_dir, ".pip_installed"), "w", encoding="utf-8") as f:
            f.write(_COMMIT)
        recorder["results"] = [_proc(1, "", "dangling"), _proc(0, stdout=_COMMIT)]
        out = ex.setup(_REPO_URL, _COMMIT)
        assert out["cached"] is True and out["error"] is None
        assert len(recorder["calls"]) == 2, "复检命中后不应再进 clone/install 序列"


@pytest.mark.unit
class TestSetupVenvReuseBranches:
    """P0 4.3 按仓库复用 venv 的各条腿（249-251 / 265-318）。"""

    # setup() 会先 rmtree 已存在的 repo_dir，指纹只能取"clone 副作用落盘之后"的
    # 值——而 _clone 被替换成固定写 `click==8.0` 的假实现，故指纹可预计算。
    _FP = hashlib.sha256(b"click==8.0\n").hexdigest()

    def _prepare(self, envs_root: Path, recorder: dict[str, Any], monkeypatch, *, create_venv_err=None):
        ex = RepoExecutor(use_venv=True, venv_reuse_by_repo=True)
        env_dir, repo_dir, venv_dir = _paths(ex)

        def _clone(_url, _commit, _dir):
            os.makedirs(_dir, exist_ok=True)
            with open(os.path.join(_dir, "requirements.txt"), "w", encoding="utf-8") as f:
                f.write("click==8.0\n")

        monkeypatch.setattr(ex, "_clone_and_checkout", _clone)
        monkeypatch.setattr(ex, "_create_venv", lambda _d: create_venv_err)
        os.makedirs(venv_dir, exist_ok=True)
        return ex, env_dir, repo_dir, venv_dir

    def test_fingerprint_hit_repoints_once_and_writes_env_marker(self, envs_root, recorder, monkeypatch):
        ex, env_dir, _repo_dir, venv_dir = self._prepare(envs_root, recorder, monkeypatch)
        with open(os.path.join(venv_dir, ".venv_dep_fingerprint"), "w", encoding="utf-8") as f:
            f.write(self._FP + "\n")  # 带尾空白：读取侧 .strip() 口径
        calls: list[tuple[str, str]] = []
        monkeypatch.setattr(ex, "_venv_pip_install", lambda _r, _v: calls.append((_r, _v)) or None)
        out = ex.setup(_REPO_URL, _COMMIT)
        assert out["error"] is None and out["cached"] is False
        assert len(calls) == 1, "O35：指纹命中只 repoint 一次，第二次 install 是白付开销"
        with open(os.path.join(env_dir, ".venv_pip_installed"), encoding="utf-8") as f:
            assert f.read() == _COMMIT

    def test_repoint_failure_keeps_env_marker(self, envs_root, recorder, monkeypatch):
        ex, env_dir, _repo_dir, venv_dir = self._prepare(envs_root, recorder, monkeypatch)
        with open(os.path.join(venv_dir, ".venv_dep_fingerprint"), "w", encoding="utf-8") as f:
            f.write(self._FP)
        monkeypatch.setattr(ex, "_venv_pip_install", lambda _r, _v: "pip 网络异常")
        out = ex.setup(_REPO_URL, _COMMIT)
        # 保守路径：repoint 失败仅告警，不清环境标记、不把 setup 判为失败
        assert out["error"] is None
        assert os.path.isfile(os.path.join(env_dir, ".venv_pip_installed"))

    def test_fingerprint_missing_installs_then_records_fingerprint(self, envs_root, recorder, monkeypatch):
        ex, env_dir, repo_dir, venv_dir = self._prepare(envs_root, recorder, monkeypatch)
        monkeypatch.setattr(ex, "_venv_pip_install", lambda _r, _v: None)
        assert ex.setup(_REPO_URL, _COMMIT)["error"] is None
        with open(os.path.join(venv_dir, ".venv_dep_fingerprint"), encoding="utf-8") as f:
            assert f.read() == ex._dep_fingerprint(repo_dir) == self._FP
        assert os.path.isfile(os.path.join(env_dir, ".venv_pip_installed"))

    def test_dependency_change_forces_reinstall(self, envs_root, recorder, monkeypatch):
        # 指纹失配（依赖变了）→ need_install 保持 True → 必须重装并重记指纹
        ex, _env_dir, repo_dir, venv_dir = self._prepare(envs_root, recorder, monkeypatch)
        with open(os.path.join(venv_dir, ".venv_dep_fingerprint"), "w", encoding="utf-8") as f:
            f.write(hashlib.sha256(b"click==7.0\n").hexdigest())
        calls: list[str] = []
        monkeypatch.setattr(ex, "_venv_pip_install", lambda _r, _v: calls.append(_r) or None)
        assert ex.setup(_REPO_URL, _COMMIT)["error"] is None
        assert calls == [repo_dir]
        with open(os.path.join(venv_dir, ".venv_dep_fingerprint"), encoding="utf-8") as f:
            assert f.read() == self._FP

    def test_install_failure_warns_but_keeps_env_marker(self, envs_root, recorder, monkeypatch):
        ex, _env_dir, _repo_dir, venv_dir = self._prepare(envs_root, recorder, monkeypatch)
        monkeypatch.setattr(ex, "_venv_pip_install", lambda _r, _v: "pip 失败")
        out = ex.setup(_REPO_URL, _COMMIT)
        assert out["error"] == "pip 失败", "安装错误仍如实返回（供上层诊断），但不阻断验证"
        assert not os.path.exists(os.path.join(venv_dir, ".venv_dep_fingerprint")), "安装失败不得记录指纹"

    def test_venv_create_failure_falls_back_to_global_editable(self, envs_root, recorder, monkeypatch):
        ex, env_dir, _repo_dir, _ = self._prepare(envs_root, recorder, monkeypatch, create_venv_err="venv 创建失败")
        monkeypatch.setattr(ex, "_pip_install_editable", lambda _r: None)
        assert ex.setup(_REPO_URL, _COMMIT)["error"] is None
        # 标记名须与 use_venv 对齐（否则下次 setup 永远缓存 miss → 重复 clone）
        with open(os.path.join(env_dir, ".venv_pip_installed"), encoding="utf-8") as f:
            assert f.read() == _COMMIT
        assert not os.path.exists(os.path.join(env_dir, ".pip_installed"))

    def test_venv_create_and_editable_both_fail(self, envs_root, recorder, monkeypatch):
        ex, env_dir, _, _ = self._prepare(envs_root, recorder, monkeypatch, create_venv_err="venv 创建失败")
        monkeypatch.setattr(ex, "_pip_install_editable", lambda _r: "pip 失败")
        out = ex.setup(_REPO_URL, _COMMIT)
        assert out["error"] == "pip 失败"
        assert not os.path.exists(os.path.join(env_dir, ".venv_pip_installed"))


@pytest.mark.unit
class TestSetupLegacyAndGlobalModes:
    """传统 per-commit venv 与全局模式的失败 / 成功腿（319-344）。"""

    def _prepare(self, envs_root: Path, monkeypatch, **kwargs):
        ex = RepoExecutor(**kwargs)
        env_dir, repo_dir, _ = _paths(ex)

        def _clone(_url, _commit, _dir):
            os.makedirs(_dir, exist_ok=True)

        monkeypatch.setattr(ex, "_clone_and_checkout", _clone)
        return ex, env_dir, repo_dir

    def test_legacy_venv_create_failure_then_editable_ok(self, envs_root, recorder, monkeypatch):
        ex, env_dir, _ = self._prepare(envs_root, monkeypatch, use_venv=True)
        monkeypatch.setattr(ex, "_create_venv", lambda _d: "venv 失败")
        monkeypatch.setattr(ex, "_pip_install_editable", lambda _r: None)
        assert ex.setup(_REPO_URL, _COMMIT)["error"] is None
        assert os.path.isfile(os.path.join(env_dir, ".pip_installed"))

    def test_legacy_venv_create_and_editable_both_fail(self, envs_root, recorder, monkeypatch):
        ex, env_dir, _ = self._prepare(envs_root, monkeypatch, use_venv=True)
        monkeypatch.setattr(ex, "_create_venv", lambda _d: "venv 失败")
        monkeypatch.setattr(ex, "_pip_install_editable", lambda _r: "pip 失败")
        out = ex.setup(_REPO_URL, _COMMIT)
        assert out["error"] == "pip 失败" and not os.path.exists(os.path.join(env_dir, ".pip_installed"))

    def test_legacy_venv_pip_install_failure(self, envs_root, recorder, monkeypatch):
        ex, env_dir, _ = self._prepare(envs_root, monkeypatch, use_venv=True)
        monkeypatch.setattr(ex, "_create_venv", lambda _d: None)
        monkeypatch.setattr(ex, "_venv_pip_install", lambda _r, _v: "pip 失败")
        assert ex.setup(_REPO_URL, _COMMIT)["error"] == "pip 失败"
        assert not os.path.exists(os.path.join(env_dir, ".venv_pip_installed"))

    def test_legacy_venv_success_writes_venv_marker(self, envs_root, recorder, monkeypatch):
        ex, env_dir, _ = self._prepare(envs_root, monkeypatch, use_venv=True)
        monkeypatch.setattr(ex, "_create_venv", lambda _d: None)
        monkeypatch.setattr(ex, "_venv_pip_install", lambda _r, _v: None)
        assert ex.setup(_REPO_URL, _COMMIT)["error"] is None
        assert os.path.isfile(os.path.join(env_dir, ".venv_pip_installed"))

    def test_global_mode_editable_failure_only_warns(self, envs_root, recorder, monkeypatch):
        ex, env_dir, _ = self._prepare(envs_root, monkeypatch)
        monkeypatch.setattr(ex, "_pip_install_editable", lambda _r: "pip 失败")
        assert ex.setup(_REPO_URL, _COMMIT)["error"] == "pip 失败"
        assert not os.path.exists(os.path.join(env_dir, ".pip_installed"))

    def test_global_mode_success(self, envs_root, recorder, monkeypatch):
        ex, env_dir, _ = self._prepare(envs_root, monkeypatch)
        monkeypatch.setattr(ex, "_pip_install_editable", lambda _r: None)
        assert ex.setup(_REPO_URL, _COMMIT)["error"] is None
        assert os.path.isfile(os.path.join(env_dir, ".pip_installed"))

    def test_clone_failure_short_circuits(self, envs_root, recorder, monkeypatch):
        ex, env_dir, _ = self._prepare(envs_root, monkeypatch)
        monkeypatch.setattr(ex, "_clone_and_checkout", lambda _u, _c, _d: "git clone 失败")
        out = ex.setup(_REPO_URL, _COMMIT)
        assert out == {"workdir": os.path.join(env_dir, "repo"), "cached": False, "error": "git clone 失败"}


@pytest.mark.unit
class TestVerifyOfficialHarnessBranches:
    """verify() 走官方 harness 的三条提前 return / 降级腿（556-585）。"""

    def _executor(self, tmp_path: Path, monkeypatch):
        ex = RepoExecutor(timeout=5, setup_timeout=5)
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        scratch = tmp_path / "tmp"
        scratch.mkdir()
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(scratch))
        monkeypatch.setattr(ex, "setup", lambda _u, _c: {"workdir": str(repo_dir), "cached": True, "error": None})
        monkeypatch.setattr(ex, "_official_harness_enabled", lambda: True)
        return ex

    def test_conftest_refuse_blocks_official_call(self, envs_root, tmp_path: Path, monkeypatch):
        ex = self._executor(tmp_path, monkeypatch)
        monkeypatch.setattr(ex, "_scan_repo_conftests", lambda _d: [("conftest.py", ["<oversize>"])])
        called = []
        monkeypatch.setattr(ex, "_run_official_swebench_harness", lambda **_kw: called.append(1) or {})
        out = ex.verify(_REPO_URL, _COMMIT, "tp", "lp", ["t.py::a"], ["t.py::b"])
        assert called == [], "conftest 硬拒必须拦在官方 harness 之前"
        assert "[S6 conftest 守卫拒绝执行]" in out["output"]
        assert [c["name"] for c in out["failed_cases"]] == ["t.py::a", "t.py::b"]
        assert list((tmp_path / "tmp").iterdir()) == [], "硬拒提前 return 也不得留下临时补丁文件"

    def test_official_result_merged_and_marked(self, envs_root, tmp_path: Path, monkeypatch):
        ex = self._executor(tmp_path, monkeypatch)
        monkeypatch.setattr(ex, "_scan_repo_conftests", lambda _d: [])
        monkeypatch.setattr(
            ex,
            "_run_official_swebench_harness",
            lambda **_kw: {"passed": True, "output": "official", "harness_invalid": False},
        )
        out = ex.verify(_REPO_URL, _COMMIT, "tp", "lp", ["t.py::a"], [])
        assert out["passed"] is True and out["harness_source"] == "official_swebench"

    def test_official_degrade_continues_self_built(self, envs_root, tmp_path: Path, monkeypatch, recorder):
        ex = self._executor(tmp_path, monkeypatch)
        monkeypatch.setattr(ex, "_scan_repo_conftests", lambda _d: [])
        monkeypatch.setattr(ex, "_run_official_swebench_harness", lambda **_kw: None)
        monkeypatch.setattr(ex, "_apply_patch_robust", lambda _d, _f: True)
        monkeypatch.setattr(ex, "_apply_llm_patch", lambda _d, _p: True)
        legs = [
            {"expected": 1, "passed": 0, "failed_cases": [{"name": "a", "error": "boom"}]},
            {"expected": 1, "passed": 1, "failed_cases": []},
        ]
        monkeypatch.setattr(ex, "_run_fail_to_pass", lambda _d, _n, repo_url="": legs.pop(0))
        monkeypatch.setattr(
            ex, "_run_pass_to_pass", lambda _d, _n, repo_url="": {"expected": 1, "passed": 1, "failed_cases": []}
        )
        out = ex.verify(
            _REPO_URL, _COMMIT, "--- a/t.py\n+++ b/t.py\n@@ -1 +1 @@\n-x\n+y\n", "lp", ["t.py::a"], ["t.py::b"]
        )
        assert out["passed"] is True, "官方降级后自建口径照常裁决"
        assert out["harness_invalid"] is False
        assert out["llm_patch_applied"] is True


@pytest.mark.unit
class TestVerifyP2PGate:
    """M3 基线 P2P 门禁（684-716）：通过率低于阈值即 harness_invalid 并强制 passed=False。"""

    def _run_verify(self, envs_root, tmp_path: Path, monkeypatch, recorder, p2p_passed: int, p2p_expected: int):
        ex = RepoExecutor(timeout=5, setup_timeout=5)
        repo_dir = tmp_path / "repo"
        # 防御式 mkdir（A-08，2026-10-18 独立评审）：同一测试内四轮复用 tmp_path，
        # 目录已存在时不得再调 mkdir——沙箱 broker 的 mkdir 垫片不尊重 exist_ok
        # （已存在也抛 EEXIST/PermissionError），显式存在性守卫在两种环境下都安全。
        if not repo_dir.exists():
            repo_dir.mkdir(parents=True)
        scratch = tmp_path / "tmp"
        if not scratch.exists():
            scratch.mkdir(parents=True)  # 允许同一测试内多轮复用（四条腿形状同构测试）
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(scratch))
        monkeypatch.setattr(ex, "setup", lambda _u, _c: {"workdir": str(repo_dir), "cached": True, "error": None})
        monkeypatch.setattr(ex, "_official_harness_enabled", lambda: False)
        monkeypatch.setattr(ex, "_apply_patch_robust", lambda _d, _f: True)
        monkeypatch.setattr(ex, "_apply_llm_patch", lambda _d, _p: True)
        legs = [
            {"expected": 1, "passed": 0, "failed_cases": [{"name": "a", "error": "boom"}]},
            {"expected": 1, "passed": 1, "failed_cases": []},
        ]
        monkeypatch.setattr(ex, "_run_fail_to_pass", lambda _d, _n, repo_url="": legs.pop(0))
        monkeypatch.setattr(
            ex,
            "_run_pass_to_pass",
            lambda _d, _n, repo_url="": {"expected": p2p_expected, "passed": p2p_passed, "failed_cases": []},
        )
        # 非空 test_patch：让 git apply --check 预检 + _apply_patch_robust 两条腿
        # 真正走到（空 test_patch 会跳过整段，等于没测）。
        out = ex.verify(
            _REPO_URL,
            _COMMIT,
            "--- a/t.py\n+++ b/t.py\n@@ -1 +1 @@\n-x\n+y\n",
            "lp",
            ["t.py::a"],
            ["t.py::b"] * p2p_expected,
        )
        assert list(scratch.iterdir()) == [], "verify 退出后临时补丁文件必须清理"
        return out

    def test_below_threshold_invalidates_harness(self, envs_root, tmp_path, monkeypatch, recorder):
        monkeypatch.delenv("P2P_GATE_ENABLE", raising=False)
        monkeypatch.delenv("P2P_GATE_THRESHOLD", raising=False)
        out = self._run_verify(envs_root, tmp_path, monkeypatch, recorder, p2p_passed=5, p2p_expected=10)
        assert out["harness_invalid"] is True and out["passed"] is False
        assert out["p2p_baseline_rate"] == 0.5
        assert out["error_info"]["type"] == "harness_invalid"

    def test_gate_disabled_restores_history(self, envs_root, tmp_path, monkeypatch, recorder):
        monkeypatch.setenv("P2P_GATE_ENABLE", "false")
        out = self._run_verify(envs_root, tmp_path, monkeypatch, recorder, p2p_passed=5, p2p_expected=10)
        assert out["harness_invalid"] is False and out["passed"] is True
        assert "p2p_baseline_rate" not in out, "门禁关闭时不记录基线通过率（历史口径零变化）"

    def test_threshold_relaxed_lets_result_through(self, envs_root, tmp_path, monkeypatch, recorder):
        monkeypatch.setenv("P2P_GATE_ENABLE", "true")
        monkeypatch.setenv("P2P_GATE_THRESHOLD", "0.5")
        out = self._run_verify(envs_root, tmp_path, monkeypatch, recorder, p2p_passed=5, p2p_expected=10)
        assert out["harness_invalid"] is False and out["p2p_baseline_rate"] == 0.5
        assert out["passed"] is True

    def test_harness_invalid_key_present_on_every_leg(self, envs_root, tmp_path, monkeypatch, recorder):
        # J-4 回归：此前"门禁开启且基线健康"这条腿**不写** harness_invalid 键，
        # 而结果字典整体落进 final_state["repo_verification"]，取键即 KeyError。
        # 四条腿（拦截 / 门禁关闭 / 阈值放宽 / 无 P2P 期望）都必须带布尔值。
        cases = [
            ({"P2P_GATE_ENABLE": None, "P2P_GATE_THRESHOLD": None}, 5, 10),
            ({"P2P_GATE_ENABLE": "false", "P2P_GATE_THRESHOLD": None}, 5, 10),
            ({"P2P_GATE_ENABLE": "true", "P2P_GATE_THRESHOLD": "0.5"}, 5, 10),
            ({"P2P_GATE_ENABLE": None, "P2P_GATE_THRESHOLD": None}, 0, 0),
        ]
        for env_values, passed, expected in cases:
            for name, value in env_values.items():
                if value is None:
                    monkeypatch.delenv(name, raising=False)
                else:
                    monkeypatch.setenv(name, value)
            out = self._run_verify(envs_root, tmp_path, monkeypatch, recorder, p2p_passed=passed, p2p_expected=expected)
            assert isinstance(out["harness_invalid"], bool), f"{env_values} 分支缺 harness_invalid 键"

    def test_garbage_threshold_falls_back_to_default(self, envs_root, tmp_path, monkeypatch, recorder):
        # J-1d 口径：坏阈值不得让判分路径抛异常，回退 0.95 后 0.5 仍应判无效
        monkeypatch.setenv("P2P_GATE_THRESHOLD", "0.95x")
        out = self._run_verify(envs_root, tmp_path, monkeypatch, recorder, p2p_passed=5, p2p_expected=10)
        assert out["harness_invalid"] is True

    def test_no_p2p_expectation_skips_gate(self, envs_root, tmp_path, monkeypatch, recorder):
        monkeypatch.delenv("P2P_GATE_ENABLE", raising=False)
        out = self._run_verify(envs_root, tmp_path, monkeypatch, recorder, p2p_passed=0, p2p_expected=0)
        assert out["harness_invalid"] is False and out["passed"] is True


@pytest.mark.unit
class TestApplyPatchRobustBackfill:
    """git apply 之后的 new-file 手动回填（1302-1332）：缺文件补写、内容一致不重写。"""

    _NEW_FILE_PATCH = (
        "diff --git a/tests/test_new.py b/tests/test_new.py\n"
        "--- /dev/null\n"
        "+++ b/tests/test_new.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+def test_x():\n"
        "+    assert True\n"
    )

    def _write_patch(self, tmp_path: Path) -> str:
        patch_file = tmp_path / "p.patch"
        patch_file.write_text(self._NEW_FILE_PATCH, encoding="utf-8")
        return str(patch_file)

    def test_missing_target_is_backfilled(self, tmp_path: Path, recorder: dict[str, Any]):
        # rc!=0 也执行兜底解析（Apple Git 2.54 的 new-file bug 正是 rc=0 但产出空文件）
        recorder["results"] = [_proc(1, "", "bad new-file blame")]
        repo = tmp_path / "repo"
        repo.mkdir()
        RepoExecutor()._apply_patch_robust(str(repo), self._write_patch(tmp_path))
        assert (repo / "tests" / "test_new.py").read_text(encoding="utf-8") == "def test_x():\n    assert True\n"

    def test_existing_content_matching_is_not_rewritten(self, tmp_path: Path, recorder: dict[str, Any]):
        patch_file = self._write_patch(tmp_path)
        repo = tmp_path / "repo"
        (repo / "tests").mkdir(parents=True)
        target = repo / "tests" / "test_new.py"
        target.write_text("def test_x():\n    assert True\n", encoding="utf-8")
        recorder["results"] = [_proc(0), _proc(0)]
        before = target.stat().st_mtime_ns
        RepoExecutor()._apply_patch_robust(str(repo), patch_file)
        assert target.stat().st_mtime_ns == before, "内容已一致仍重写 = 白白失效一次文件缓存"


@pytest.mark.unit
class TestApplyLlmPatchGuards:
    """M2 测试文件保护 + C5 危险 API 守卫（1171-1210）：三条拒绝腿都须先于 git apply。"""

    _GUARD_URL_REPO_DIR = "/nonexistent-repo"

    def test_touching_test_file_refuses_before_git_apply(self, recorder: dict[str, Any]):
        ex = RepoExecutor(timeout=5, setup_timeout=5)
        # 必须以 diff --git / @@ 开头，否则 _apply_llm_patch 在 is_unified 处就返回
        # False（"非 unified diff 形态"腿），根本走不到 M2 守卫——此前本用例正是
        # 因缺 diff --git 头而"假过"：断言成立，但验证的是另一条腿。
        patch_text = (
            "diff --git a/tests/test_a.py b/tests/test_a.py\n"
            "--- a/tests/test_a.py\n+++ b/tests/test_a.py\n@@ -1 +1 @@\n-x\n+y\n"
        )
        assert ex._apply_llm_patch(self._GUARD_URL_REPO_DIR, patch_text) is False
        assert recorder["calls"] == [], "拒绝应发生在任何 git apply 之前"

    def test_non_unified_full_file_code_refuses(self, recorder: dict[str, Any]):
        # LLM 重写整个模块的形态：路径无法映射到仓库真实文件 → 保守 False。
        ex = RepoExecutor(timeout=5, setup_timeout=5)
        assert ex._apply_llm_patch(self._GUARD_URL_REPO_DIR, "def f():\n    return 2\n") is False
        assert recorder["calls"] == []

    def test_new_dangerous_call_refuses(self, recorder: dict[str, Any]):
        ex = RepoExecutor(timeout=5, setup_timeout=5)
        patch_text = (
            "diff --git a/pkg.py b/pkg.py\n--- a/pkg.py\n+++ b/pkg.py\n@@ -1 +1 @@\n-import os\n+os.system('id')\n"
        )
        assert ex._apply_llm_patch(self._GUARD_URL_REPO_DIR, patch_text) is False
        assert recorder["calls"] == []

    def test_unparseable_added_line_refuses_fail_closed(self, recorder: dict[str, Any]):
        # 残行数 > 0：空特征集只表示"读不懂"而非"安全"，按 G 轮决策拒绝应用。
        ex = RepoExecutor(timeout=5, setup_timeout=5)
        patch_text = "diff --git a/pkg.py b/pkg.py\n--- a/pkg.py\n+++ b/pkg.py\n@@ -1 +1 @@\n-x = 1\n+x = = 1\n"
        found, residue = RepoExecutor._llm_patch_dangerous_calls(patch_text)
        assert found == set() and residue > 0, "本用例前提：读不懂但未命中特征（否则测的是另一条腿）"
        assert ex._apply_llm_patch(self._GUARD_URL_REPO_DIR, patch_text) is False
        assert recorder["calls"] == []

    def test_clean_patch_reaches_git_apply(self, recorder: dict[str, Any], tmp_path: Path, monkeypatch):
        # 正向对照：三条守卫腿都放行后才会真正调用 git apply --check（否则上面的
        # calls == [] 断言毫无区分力）。
        scratch = tmp_path / "tmp"
        scratch.mkdir()
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(scratch))
        ex = RepoExecutor(timeout=5, setup_timeout=5)
        monkeypatch.setattr(ex, "_apply_patch_robust", lambda _d, _f: True)
        patch_text = "diff --git a/pkg.py b/pkg.py\n--- a/pkg.py\n+++ b/pkg.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
        recorder["results"] = [_proc(0)]
        assert ex._apply_llm_patch(str(tmp_path), patch_text) is True
        assert recorder["calls"][0]["cmd"][:2] == ["git", "apply"]
        assert list(scratch.iterdir()) == [], "补丁临时文件须在 finally 清理"

    def test_check_rejected_applies_nothing(self, recorder: dict[str, Any], tmp_path: Path, monkeypatch):
        scratch = tmp_path / "tmp"
        scratch.mkdir()
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(scratch))
        ex = RepoExecutor(timeout=5, setup_timeout=5)
        called = []
        monkeypatch.setattr(ex, "_apply_patch_robust", lambda _d, _f: called.append(1) or True)
        patch_text = "diff --git a/pkg.py b/pkg.py\n--- a/pkg.py\n+++ b/pkg.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
        recorder["results"] = [_proc(1, "", "context mismatch")]
        assert ex._apply_llm_patch(str(tmp_path), patch_text) is False
        assert called == [], "--check 未过不得进 _apply_patch_robust"
        assert list(scratch.iterdir()) == []
