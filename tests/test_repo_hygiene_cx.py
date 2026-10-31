"""CX 轮：仓库卫生守卫 `scripts/gates/check_repo_hygiene.py` 的回归锁。

纪律：**零 LLM、$0**。判定分两类：
  - 规则面（合成路径串，不写真实文件）：什么形态算「临时/缓存产物」；
  - 接线面（真实树）：这道门**有人在跑**吗？

为什么这道门必须存在（本轮实测）：CW 轮的一次 pytest 运行把 `--basetemp` 落在
仓库内的 `.tmp_pytest/`，而 `.gitignore` 只登记了 `.pytest_tmp/` 与 `.pytest_tmp*/`
——**模式不覆盖它** ⇒ 12 个 pytest 临时文件（含 `.lock` 与 `pytest-current`
**符号链接**）被提交进仓库，随 v1.0.0 一同发布。符号链接进版本库在跨平台检出时
会炸；它们每次跑测试都在变 ⇒ 永久制造无意义 diff。

判据设计上的两个刻意选择（都有负例钉住）：
  1. **按路径分量判定，不按后缀**。`.log` 在 `experiments/results/` 下是**故意的
     证据工件**（`preflight.log` / `arm_df.log` 等），按后缀一刀切会把真工件误杀；
     反过来 `docs/tmp_trace_notes.md` 这种**普通文件**也不能因为名字里含
     `tmp_trace` 就被误伤——所以只有**某个分量整体等于** `tmp_trace` 才算命中。
  2. **不设豁免表**。缓存/临时文件进版本库没有正当理由；确有需要时应当**改名**
     成语义化的工件（如 `run_artifacts_<ts>/`）后再入库。

本文件自身也是 `--list` 开关的**代码锁**（它点名 `check_repo_hygiene` 并真传
`--list`）——按 CG 门的分类，`--list` 属「判据档」，判据档无读者即红。

分组：A 规则面 8 例 / B 接线面 4 例 / C 敏感路径面（2026-10-26 用户口径）。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = PROJECT_ROOT / "scripts" / "gates" / "check_repo_hygiene.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("_check_repo_hygiene", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_check_repo_hygiene"] = module
    spec.loader.exec_module(module)
    return module


gate = _load()


class TestHygieneRules:
    """A 组：规则面——什么形态算「临时/缓存产物」。"""

    @pytest.mark.parametrize(
        "path",
        [
            ".tmp_pytest/pytest-of-root/pytest-0/.lock",
            ".tmp_pytest/pytest-current",
            ".pytest_cache/v/cache/lastfailed",
            ".pytest_tmp/x/1",
            ".pytest_tmp_something/x/1",
            ".tmp_run/out.log",
            "src/__pycache__/foo.cpython-314.pyc",
            "src/foo.pyc",
            "src/foo.pyo",
            ".coverage",
            ".coverage.hostname.1234",
            "pkg.egg-info/PKG-INFO",
            "node_modules/left-pad/index.js",
            ".venv/bin/python",
            "venv/bin/python",
            "tmp_trace/trace.jsonl",
        ],
    )
    def test_junk_paths_are_flagged(self, path: str) -> None:
        assert gate._hit_reason(tuple(path.split("/"))) is not None, path

    @pytest.mark.parametrize(
        "path",
        [
            # 真证据工件：`.log` 是故意入库的运行日志，不得误杀
            "experiments/results/emse_docstring_anchor_20261017/preflight.log",
            # 名字里含 tmp_trace 但不是该分量
            "docs/tmp_trace_notes.md",
            "src/utils/trace_cache.py",
            # 名字里含 coverage 但不是 coverage 数据文件
            "scripts/gates/check_branch_coverage.py",
            "docs/coverage_ratchet.yaml",
            # 名字里含 cache 但不是缓存目录
            "src/cache_utils.py",
            "docs/adr/0014-branch-coverage-gates.md",
        ],
    )
    def test_legit_paths_are_not_flagged(self, path: str) -> None:
        assert gate._hit_reason(tuple(path.split("/"))) is None, path

    def test_rule_hit_reports_a_reason(self) -> None:
        hit = gate._hit_reason((".tmp_pytest", "pytest-current"))
        assert hit is not None
        assert hit[0] == ".tmp_pytest"
        assert hit[1]

    def test_gitignore_covers_the_basetemp_variant(self) -> None:
        """`.gitignore` 必须登记 `.tmp_pytest/`——`.pytest_tmp*/` 的模式覆盖不到它。"""
        ignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert ".tmp_pytest/" in ignore

    def test_gitignore_ignores_the_artifact(self) -> None:
        """登记必须是有效的：`git check-ignore` 逐条确认（目录级规则要能覆盖内容）。"""
        proc = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "check-ignore", "-v", ".tmp_pytest/pytest-current"],
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")


class TestHygieneWiring:
    """B 组：接线面——这道门有人在跑吗？"""

    def test_real_tree_has_no_tracked_junk(self) -> None:
        """真实树：跟踪面内无临时/缓存产物（否则本门应当红）。"""
        proc = subprocess.run(
            [sys.executable, str(_SCRIPT)],
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")

    def test_list_switch_is_readable(self) -> None:
        """`--list` 必须真参与调度（CH 轮的门禁会判「dest 从不被读」的死开关）。"""
        proc = subprocess.run(
            [sys.executable, str(_SCRIPT), "--list"],
            capture_output=True,
            check=False,
        )
        out = proc.stdout.decode("utf-8", "replace")
        assert proc.returncode == 0, out
        assert "规则清单" in out
        assert ".tmp_pytest" in out

    def test_gate_is_in_the_makefile_gates_chain(self) -> None:
        """「写了没人跑」是本项目反复出现的病症：必须进 `make gates` 链。"""
        makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
        assert "repo-hygiene:" in makefile
        assert "scripts/gates/check_repo_hygiene.py" in makefile
        chain = next(line for line in makefile.splitlines() if line.startswith("gates:"))
        assert "repo-hygiene" in chain

    def test_gate_is_wired_into_ci(self) -> None:
        """必须进 CI（否则只在本地跑，远端树照样能污染）。"""
        ci = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "scripts/gates/check_repo_hygiene.py" in ci


class TestPrivatePathRules:
    """C 组：敏感/私有路径不得被跟踪（2026-10-26 用户口径）。

    口径来源：用户明确「上传 GitHub 的只能是项目相关代码和必要的说明性文档」。
    论文源（`paper/`）、私有审查（`.private/`）、数据集（`data/`）、RAG 持久化库
    （`rag_data/`）、工具生成的 RepoWiki（`.qoder/`）、本机密钥（`.env` /
    `.env.local*`）与投稿/预注册类文档一律**保持未跟踪**——`.gitignore` 只能挡住
    「未跟踪」面，一旦被 `git add`（尤其 `-f`）就随提交上传，所以这里再加一道
    **索引面**断言：`git ls-files` 里出现这些路径即判红。

    两个刻意选择（都有负例钉住）：
      1. 顶层目录锚定，不做全局分量匹配——`docs/paper/notes.md`、`src/data/x.py`
         是正常文档/代码，不得误伤；
      2. 只锚定 `docs/study/*_PREREG_*.md`——`experiments/results/` 下的
         `PREREG.md` 是公开证据工件（已入库），不在禁列。
    """

    @pytest.mark.parametrize(
        "path",
        [
            "paper/tex/manuscript.tex",
            "paper/SUBMISSION.md",
            ".private/audit/project_full_audit.md",
            "data/dataset.jsonl",
            "rag_data/index.faiss",
            ".qoder/repowiki/zh/content/index.md",
            ".workbuddy/memory/notes.md",
            "tmp_apr_baseline/crawl.json",
            ".env",
            ".env.local",
            ".env.local.bak_g8",
            ".gitignore-sensitive",
            "INDEPENDENT_REVIEW_2026-01-01.md",
            "docs/study/OPTIMIZATION_APPENDIX_v1.md",
            "docs/study/ULT_DF200_PREREG_2026-10-20.md",
            "docs/study/BATCH8_MUTK_VALIDITY_2026.md",
            "docs/study/GOLD_CONFORMANCE_2026.md",
            "docs/study/PAPER_CONSISTENCY_AUDIT_2026-10-17.md",
            "docs/design/stvr_empirical_study_design.md",
            "docs/design/false_fix_caliber_matrix.md",
            "SPEC_REPLACE_AB_SCALE87_REPORT_2026.md",
        ],
    )
    def test_private_paths_are_flagged(self, path: str) -> None:
        assert gate._private_hit_reason(tuple(path.split("/"))) is not None, path

    @pytest.mark.parametrize(
        "path",
        [
            # 模板无密钥值，必须入库供他人配置
            ".env.example",
            ".env.local.template",
            # 嵌套同名目录不是顶层敏感目录
            "docs/paper/notes.md",
            "src/data/loader.py",
            # 公开证据工件与说明文档
            "experiments/results/p_round_b8_ablation_20261018/PREREG.md",
            "experiments/results/main_batch/benchmark_x.json",
            "experiments/results/emse_docstring_anchor_20261017/preflight.log",
            "docs/study/PAPER_BUILD.md",
            "docs/study/PAPER_CITATION_KEYS.md",
            "docs/study/EXTERNAL_READINGS_2026-10-25.md",
            "docs/study/OPTIMIZATION_2026-10-15.md",
            "docs/design/adr-0014-branch-coverage-gates.md",
            "llm_configs.json",
            "scripts/gates/check_repo_hygiene.py",
        ],
    )
    def test_public_paths_are_not_flagged(self, path: str) -> None:
        assert gate._private_hit_reason(tuple(path.split("/"))) is None, path

    def test_private_hit_reports_a_reason(self) -> None:
        hit = gate._private_hit_reason(("paper", "tex", "manuscript.tex"))
        assert hit is not None
        assert hit[0]
        assert hit[1]

    def test_index_surface_detects_a_tracked_secret(self, tmp_path: Path) -> None:
        """判据读索引：`git add -f` 过的 `.env.local` 在提交前就能被拦住。"""
        subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
        (tmp_path / ".env.local").write_text("LLM_1_API_KEY=placeholder\n", encoding="utf-8")
        (tmp_path / "ok.py").write_text("print(1)\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "-f", ".env.local", "ok.py"],
            check=True,
        )
        offenders = gate.find_private_offenders(tmp_path)
        assert [path for path, _, _ in offenders] == [".env.local"]

    def test_real_tree_has_no_tracked_private_paths(self) -> None:
        """真实树：跟踪面内无敏感/私有路径。"""
        assert gate.find_private_offenders(PROJECT_ROOT) == []

    def test_list_switch_discloses_private_rules(self) -> None:
        """`--list` 必须披露新增判据面（否则判据档无读者）。"""
        proc = subprocess.run(
            [sys.executable, str(_SCRIPT), "--list"],
            capture_output=True,
            check=False,
        )
        out = proc.stdout.decode("utf-8", "replace")
        assert proc.returncode == 0, out
        assert "敏感/私有" in out
        assert ".env.local" in out

    def test_gitignore_ignores_qoder_state(self) -> None:
        """`.qoder/`（工具生成的 RepoWiki，可重建）必须被有效忽略。"""
        ignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert ".qoder/" in ignore
        proc = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "check-ignore", "-v", ".qoder/repowiki/zh/content/index.md"],
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")

    def test_pre_commit_runs_the_gate(self) -> None:
        """本判据必须在提交前执行（`make gates`/CI 只能事后发现，内容已进历史）。"""
        hook = (PROJECT_ROOT / ".git-hooks" / "pre-commit.sh").read_text(encoding="utf-8")
        assert "scripts/gates/check_repo_hygiene.py" in hook


class TestGateRegistrySurface:
    """B 组补：判定面 B——`scripts/README.md` 的门禁清单必须完整且与盘面一致。

    起因（本轮实测）：那张表写「## gates/（27 个）」且**表头与表体自洽**（27 行），
    但盘上已有 **34 个**门禁——CF / CG / CH / BN / BK / CU 几轮新增的 7 道从未登记。
    读者按文档找门禁会漏掉 7 道；「门禁有多少个」这个手写数字也没有任何机制能发现
    它过期——它和 SUBMISSION.md 的「55 页」是同一类病：**看起来像对的数字没人核**。
    """

    def test_real_registry_is_complete(self) -> None:
        """真实树：清单不漏登、表头数字与盘面一致、表体行数与表头一致。"""
        problems = gate.check_gate_registry(PROJECT_ROOT)
        assert problems == [], problems

    def test_registry_detects_a_missing_entry(self, tmp_path) -> None:
        """负例：从清单里删掉一道门 ⇒ 判红（漏登必须被抓到）。"""
        gates_dir = tmp_path / "scripts" / "gates"
        gates_dir.mkdir(parents=True)
        (gates_dir / "check_alpha.py").write_text("", encoding="utf-8")
        (gates_dir / "check_beta.py").write_text("", encoding="utf-8")
        (tmp_path / "scripts" / "README.md").write_text(
            "## gates/（2 个）\n\n| 脚本 | 守卫内容 |\n| --- | --- |\n"
            "| `check_alpha.py` | 甲 |\n"
            "| `check_beta.py` | 乙 |\n",
            encoding="utf-8",
        )
        problems = gate.check_gate_registry(tmp_path)
        assert problems == [], problems

        text = (tmp_path / "scripts" / "README.md").read_text(encoding="utf-8")
        (tmp_path / "scripts" / "README.md").write_text(
            text.replace("| `check_beta.py` | 乙 |\n", ""), encoding="utf-8"
        )
        problems = gate.check_gate_registry(tmp_path)
        assert any("漏登" in p for p in problems), problems

    def test_registry_detects_a_stale_header_count(self, tmp_path) -> None:
        """负例：表头写的个数与盘面不一致 ⇒ 判红（手写数字必须被核）。"""
        gates_dir = tmp_path / "scripts" / "gates"
        gates_dir.mkdir(parents=True)
        (gates_dir / "check_alpha.py").write_text("", encoding="utf-8")
        (tmp_path / "scripts" / "README.md").write_text(
            "## gates/（5 个）\n\n| 脚本 | 守卫内容 |\n| --- | --- |\n| `check_alpha.py` | 甲 |\n",
            encoding="utf-8",
        )
        problems = gate.check_gate_registry(tmp_path)
        assert any("盘上实有" in p for p in problems), problems

    def test_registry_ignores_rows_of_other_sections(self, tmp_path) -> None:
        """负例（防误判）：tools/ 等小节的表格行不得被算进 gates 表的行数。"""
        gates_dir = tmp_path / "scripts" / "gates"
        gates_dir.mkdir(parents=True)
        (gates_dir / "check_alpha.py").write_text("", encoding="utf-8")
        (tmp_path / "scripts" / "README.md").write_text(
            "## gates/（1 个）\n\n| 脚本 | 守卫内容 |\n| --- | --- |\n"
            "| `check_alpha.py` | 甲 |\n"
            "\n## tools/（2 个）\n\n| 脚本 | 用途 |\n| --- | --- |\n"
            "| `tool_one.py` | 乙 |\n| `tool_two.py` | 丙 |\n",
            encoding="utf-8",
        )
        problems = gate.check_gate_registry(tmp_path)
        assert problems == [], problems
