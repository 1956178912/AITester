"""
executor_repo.py 单测：用临时 git 仓库 fixture 验证仓库级执行器。

覆盖：
- setup: 缓存命中 / clone+checkout / pip install 跳过（无 setup.py）
- verify: test_patch 应用、FAIL_TO_PASS 基线失败→LLM 补丁修复后通过
- verify: LLM 补丁修复后仍失败 → passed=False
- verify: PASS_TO_PASS 回归检测
- verify: test_patch 应用失败诊断
- verify: base_not_failing 诊断（基线就全过）
- venv 隔离: use_venv=False 默认行为不变（PYTHONPATH 注入 / 全局 python）
- venv 隔离: use_venv=True 时不注入宿主 PYTHONPATH、PATH 前置 venv/bin
- _normalize_llm_patch: 剥离 ```python 围栏 / 'python' 行首 / 保留纯代码
- _diff_codes: git diff --no-index 产物可被 git apply 解析（整文件替换场景）
- _diff_codes: original == fixed 返回空串（LLM 未改动）

fixture 策略：
- 临时目录 git init 一个最小 Python 仓库（calculator.py 有缺陷 + 正常函数），
  生成 base_commit，构造 test_patch（新增测试文件，FAIL_TO_PASS 指向缺陷函数），
  构造 LLM 补丁（unified diff 修复缺陷函数）。
- SWE_REPO_ENVS_DIR 指向 tmp_path，避免污染真实缓存。
"""

from __future__ import annotations

import os
import subprocess

import pytest

from src.agents.executor_repo import RepoExecutor


def _new_file_patch(target: str, body: str) -> str:
    """生成 git-apply 可解析的新文件补丁（真实换行形态）。

    SWE-bench 官方 JSONL 中 test_patch 经 json.loads 还原后 \\n 为真实换行
    （JSON 源码中的字面量形态在加载后即换行）；git apply 按行解析 hunk。
    形态与官方数据一致，此前"\\n 字面量"误读已修正。
    """
    import hashlib

    h = hashlib.md5(body.encode()).hexdigest()[:12]
    return (
        f"diff --git a/{target} b/{target}\n"
        f"new file mode 100644\nindex 0000000..{h}\n--- /dev/null\n"
        f"+++ b/{target}\n" + "".join(f"+{line}\n" for line in body.splitlines())
    )


@pytest.fixture()
def repo_env(tmp_path, monkeypatch):
    """构造最小 git 仓库 + test_patch + LLM 补丁，返回各要素 dict。"""
    root = tmp_path / "calc_repo"
    root.mkdir()
    # 有缺陷的模块：add 返回 a - b（缺陷），sub 正常
    calc = root / "calculator.py"
    calc.write_text(
        "def add(a, b):\n    return a - b  # bug: should be +\n\n"
        "def sub(a, b):\n    return a - b\n"
        "def mul(a, b):\n    return a * b\n",
        encoding="utf-8",
    )
    readme = root / "README.md"
    readme.write_text("# calc\n", encoding="utf-8")

    def git(*args: str, cwd=root) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("add", ".")
    git("commit", "-q", "-m", "base")
    base_commit = git("rev-parse", "HEAD").stdout.strip()

    # test_patch：新增 test_calculator.py（git apply 需带完整 diff 头）
    new_test = "def test_add():\n    from calculator import add\n    assert add(1, 2) == 3\n\ndef test_sub():\n    from calculator import sub\n    assert sub(5, 3) == 2\n"
    test_patch = _new_file_patch("test_calculator.py", new_test)

    # LLM 补丁：unified diff 修复 add（修改已有文件路径，真实换行形态）。
    # hunk 行计数口径（git 严格校验）：old 行数 = context(3: `def add`/
    # blank/`def sub`)+deletion(1) = 4；new 行数 = context(3)+addition(1) = 4。
    # 此前 -1,2 漏计 post-context（blank+sub 两行是 context，计入行数），
    # git apply 严格校验即拒绝。
    llm_patch = (
        "diff --git a/calculator.py b/calculator.py\n"
        "--- a/calculator.py\n"
        "+++ b/calculator.py\n"
        "@@ -1,4 +1,4 @@\n"
        " def add(a, b):\n"
        "-    return a - b  # bug: should be +\n"
        "+    return a + b\n"
        " \n"
        " def sub(a, b):\n"
        "     return a - b\n"
    )

    monkeypatch.setenv("SWE_REPO_ENVS_DIR", str(tmp_path / "repo_envs"))
    env = {
        "repo_url": str(root),  # 本地路径作为 clone URL（git 支持 file 路径）
        "base_commit": base_commit,
        "test_patch": test_patch,
        "llm_patch": llm_patch,
        "fail_to_pass": ["test_calculator.py::test_add"],
        "pass_to_pass": ["test_calculator.py::test_sub"],
    }
    yield env


def _executor(tmp_path) -> RepoExecutor:
    return RepoExecutor(timeout=60, setup_timeout=60)


class TestSetup:
    def test_setup_creates_env_and_pip_skipped_without_setup_py(self, repo_env, tmp_path):
        ex = _executor(tmp_path)
        env = ex.setup(repo_env["repo_url"], repo_env["base_commit"])
        assert env["error"] is None, env
        assert os.path.isdir(env["workdir"])
        # 无 setup.py/pyproject → pip install 跳过
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=env["workdir"], capture_output=True, text=True
        ).stdout.strip()
        assert head.startswith(repo_env["base_commit"][:12])

    def test_setup_cache_hit(self, repo_env, tmp_path):
        ex = _executor(tmp_path)
        first = ex.setup(repo_env["repo_url"], repo_env["base_commit"])
        assert first["cached"] is False
        second = ex.setup(repo_env["repo_url"], repo_env["base_commit"])
        assert second["cached"] is True
        assert second["workdir"] == first["workdir"]

    def test_setup_missing_commit_fails(self, repo_env, tmp_path):
        ex = _executor(tmp_path)
        env = ex.setup(repo_env["repo_url"], "deadbeef" * 4)
        assert env["error"] is not None


class TestVerify:
    def test_verify_pass_with_llm_fix(self, repo_env, tmp_path):
        ex = _executor(tmp_path)
        r = ex.verify(
            repo_url=repo_env["repo_url"],
            base_commit=repo_env["base_commit"],
            test_patch=repo_env["test_patch"],
            llm_patch=repo_env["llm_patch"],
            fail_to_pass=repo_env["fail_to_pass"],
            pass_to_pass=repo_env["pass_to_pass"],
        )
        assert r["passed"] is True, r
        assert r["fail_to_pass"]["passed"] == 1
        assert r["pass_to_pass"]["passed"] == 1
        assert r["llm_patch_applied"] is True

    def test_verify_fail_when_llm_patch_wrong(self, repo_env, tmp_path):
        ex = _executor(tmp_path)
        wrong = (
            "diff --git a/calculator.py b/calculator.py\n"
            "--- a/calculator.py\n"
            "+++ b/calculator.py\n"
            "@@ -1,4 +1,4 @@\n"
            " def add(a, b):\n"
            "-    return a - b  # bug: should be +\n"
            "+    return a + b + 1\n"
            " \n"
            " def sub(a, b):\n"
            "     return a - b\n"
        )
        r = ex.verify(
            repo_url=repo_env["repo_url"],
            base_commit=repo_env["base_commit"],
            test_patch=repo_env["test_patch"],
            llm_patch=wrong,
            fail_to_pass=repo_env["fail_to_pass"],
            pass_to_pass=repo_env["pass_to_pass"],
        )
        assert r["passed"] is False
        assert r["fail_to_pass"]["passed"] == 0

    def test_verify_base_not_failing_diagnosis(self, repo_env, tmp_path, monkeypatch):
        """基线就全过（test_patch 未覆盖缺陷）→ base_not_failing 诊断。

        构造"test_patch 为空（无 gold 测试覆盖缺陷）+ FAIL_TO_PASS 指向
        仓库内已有的 test_sub（sub 函数正常，基线就过）"的场景。
        monkeypatch _run_test_nodes 模拟基线全过，验证诊断分类路径。
        """
        ex = _executor(tmp_path)
        # monkeypatch _run_test_nodes：基线全过（无 failed_cases）
        monkeypatch.setattr(
            ex,
            "_run_test_nodes",
            lambda repo_dir, nodes, repo_url="": {"expected": len(nodes), "passed": len(nodes), "failed_cases": []},
        )
        r = ex.verify(
            repo_url=repo_env["repo_url"],
            base_commit=repo_env["base_commit"],
            test_patch="",  # 空 test_patch（无 gold 测试），FAIL_TO_PASS 指向正常函数
            llm_patch="",
            fail_to_pass=["test_calculator.py::test_sub"],
            pass_to_pass=[],
        )
        assert r["passed"] is False
        assert r.get("error_info", {}).get("type") == "base_not_failing"

    def test_verify_test_patch_apply_failed(self, repo_env, tmp_path):
        """test_patch 是损坏文本 → git apply 失败 → test_patch_apply_failed 诊断。"""
        ex = _executor(tmp_path)
        r = ex.verify(
            repo_url=repo_env["repo_url"],
            base_commit=repo_env["base_commit"],
            test_patch="this is not a unified diff at all",
            llm_patch=repo_env["llm_patch"],
            fail_to_pass=repo_env["fail_to_pass"],
        )
        assert r["passed"] is False
        assert r.get("error_info", {}).get("type") == "test_patch_apply_failed"

    def test_verify_restores_baseline_after_run(self, repo_env, tmp_path):
        """验证结束后工作区应为'仅 test_patch'基线（llm_patch 被撤）。"""
        ex = _executor(tmp_path)
        r = ex.verify(
            repo_url=repo_env["repo_url"],
            base_commit=repo_env["base_commit"],
            test_patch=repo_env["test_patch"],
            llm_patch=repo_env["llm_patch"],
            fail_to_pass=repo_env["fail_to_pass"],
            pass_to_pass=repo_env["pass_to_pass"],
        )
        workdir = r["repo_env"]["workdir"]
        with open(os.path.join(workdir, "calculator.py"), encoding="utf-8") as f:
            calc = f.read()
        # llm_patch 已撤，缺陷恢复
        assert "a - b" in calc
        # test_patch 保留
        assert os.path.isfile(os.path.join(workdir, "test_calculator.py"))


class TestRunTestNodes:
    def test_empty_nodes(self, repo_env, tmp_path):
        ex = _executor(tmp_path)
        env = ex.setup(repo_env["repo_url"], repo_env["base_commit"])
        r = ex._run_test_nodes(env["workdir"], [])
        assert r == {"expected": 0, "passed": 0, "failed_cases": []}

    def test_node_parse_failure(self, repo_env, tmp_path):
        ex = _executor(tmp_path)
        env = ex.setup(repo_env["repo_url"], repo_env["base_commit"])
        r = ex._run_test_nodes(env["workdir"], ["nonexistent_test.py::test_x"])
        assert r["expected"] == 1
        assert len(r["failed_cases"]) == 1


class TestVenvIsolation:
    def test_default_use_venv_is_false(self, repo_env, tmp_path):
        """默认全局模式行为不变：use_venv=False，_venv_python 返回 None。"""
        ex = RepoExecutor(timeout=60, setup_timeout=60)
        assert ex.use_venv is False
        assert ex._venv_python("/nonexistent") is None

    def test_use_venv_true_creates_venv_dir(self, repo_env, tmp_path, monkeypatch):
        """use_venv=True 时 setup 在 env_dir 旁建 venv（写 .venv_pip_installed）。"""
        monkeypatch.setenv("SWE_REPO_ENVS_DIR", str(tmp_path / "venv_envs"))
        ex = RepoExecutor(timeout=60, setup_timeout=60, use_venv=True)
        env = ex.setup(repo_env["repo_url"], repo_env["base_commit"])
        assert env["error"] is None, env
        # env_dir 旁的 venv 目录存在（venv/bin/python）
        env_dir = os.path.dirname(env["workdir"])
        vpy = os.path.join(env_dir, "venv", "bin", "python")
        assert os.path.isfile(vpy), f"venv python not created: {vpy}"
        # _venv_python 在该环境下返回该路径
        assert ex._venv_python(env_dir) == vpy

    def test_use_venv_false_unchanged_cache_marker(self, repo_env, tmp_path, monkeypatch):
        """默认模式缓存命中仍看 .pip_installed（不破坏既有缓存）。"""
        monkeypatch.setenv("SWE_REPO_ENVS_DIR", str(tmp_path / "glob_envs"))
        ex = RepoExecutor(timeout=60, setup_timeout=60, use_venv=False)
        env = ex.setup(repo_env["repo_url"], repo_env["base_commit"])
        env_dir = os.path.dirname(env["workdir"])
        assert os.path.isfile(os.path.join(env_dir, ".pip_installed"))
        second = ex.setup(repo_env["repo_url"], repo_env["base_commit"])
        assert second["cached"] is True

    def test_run_test_nodes_global_mode_injects_pythonpath(self, repo_env, tmp_path, monkeypatch):
        """全局模式（use_venv=False）PYTHONPATH 注入 src 目录在最前（防跨 commit 污染）。"""
        import sys as _sys

        monkeypatch.setenv("SWE_REPO_ENVS_DIR", str(tmp_path / "gg"))
        ex = RepoExecutor(timeout=60, setup_timeout=60, use_venv=False)
        env = ex.setup(repo_env["repo_url"], repo_env["base_commit"])
        workdir = env["workdir"]
        # 拦截 _run，捕获传入的 env 字典
        captured = {}

        def fake_run(cmd, cwd, timeout, env=None):
            captured["env"] = env
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr("src.agents.executor_repo._run", fake_run)
        ex._run_test_nodes(workdir, ["x.py::test_y"])
        pp = captured["env"]["PYTHONPATH"].split(os.pathsep)
        # 全局模式：repo_dir 在 PYTHONPATH 中
        assert workdir in pp
        # 用 venv python（_venv_python 因 use_venv=False 返回 None → 退回 sys.executable）
        assert captured["cmd"][0] == _sys.executable


class TestLlmPatchHelpers:
    def test_normalize_llm_patch_strips_python_fence(self):
        """```python 围栏剥离（LLM 输出"完整文件重写"形态）。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location("rb", "experiments/run_benchmark.py")
        rb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rb)
        assert rb._normalize_llm_patch("") == ""
        assert rb._normalize_llm_patch("   ") == ""
        # 裸 'python' 行首标记
        assert rb._normalize_llm_patch("python\nimport re\n").strip() == "import re"
        # ```python 围栏
        fenced = "```python\ndef f():\n    return 1\n```"
        assert rb._normalize_llm_patch(fenced).strip() == "def f():\n    return 1"
        # 纯代码原样返回
        assert rb._normalize_llm_patch("import re\n").strip() == "import re"

    def test_diff_codes_empty_when_equal(self):
        """original == fixed（LLM 未改动）→ 空串。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location("rb", "experiments/run_benchmark.py")
        rb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rb)
        assert rb._diff_codes("same", "same", "a/x.py", "a/x.py") == ""

    def test_diff_codes_full_file_replace_is_git_applicable(self, tmp_path):
        """整文件替换场景：git diff --no-index 产物可被 git apply 解析。

        此前 difflib.unified_diff 手工拼接在整文件替换时产出行计数与 git
        解析器不符的 corrupt patch（实测 5/5 单源任务 git apply 拒绝）。
        修复后 _diff_codes 经 git diff --no-index 生成严格 unified diff。
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location("rb", "experiments/run_benchmark.py")
        rb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rb)

        original = "line1\nline2\nline3\nline4\n"
        # 整文件重写（LLM 形态）
        fixed = "line1\nNEW_CONTENT\nline4\n"
        diff = rb._diff_codes(original, fixed, "src/pkg/mod.py", "src/pkg/mod.py")
        assert diff, "non-empty expected"
        # 头应为真实仓库路径
        assert diff.startswith("diff --git a/src/pkg/mod.py b/src/pkg/mod.py")

        # 构造最小 git 仓库，验证 git apply 可解析该 diff
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "src").mkdir()
        (repo / "src" / "pkg").mkdir()
        mod = repo / "src" / "pkg" / "mod.py"
        mod.write_text(original)
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "base"], check=True)
        patch_file = tmp_path / "llm.patch"
        patch_file.write_text(diff)
        r = subprocess.run(
            ["git", "apply", "--check", "--whitespace=nowarn", str(patch_file)],
            cwd=str(repo),
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, f"git apply --check failed: {r.stderr}"
