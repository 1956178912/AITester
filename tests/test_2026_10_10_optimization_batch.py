"""2026-10-10 独立审查优化批次的回归锁。

覆盖三项本轮改动（均为"防事故/防漂移"性质，必须由测试钉住）：

1. **`_env_snapshot_keys` 完备性**（I-02 收口）
   事前教训：A1 首跑因 `PLAN_STRIP_EXPECTED_OUTPUT_ENABLE` 未入 provenance，
   "开关未生效却被当成零效应"（假阴性）→ 结论作废；RT1 同类。
   本轮把快照从 39 键补到 98 键（75 个 `*_ENABLE` 全覆盖）。
   本测试防止后续新增开关时再次出现缺口。

2. **证据门分档**（I-29）
   事前教训：二值门把 `keyword` 级证据一并丢弃；而**二值旁路已被真实 A/B 证否**
   （correct 总量不变、落盘精确率 92.6%→71.1%，见
   `review_2026/E6_factorial_2x2_result.md`）。故改为**门限可下移一档**，
   但默认必须仍是历史口径（ADR-0003）。

3. **`BASELINE.yaml` 数字与实测一致**（G11 治理漂移）
   `tests.total_passed` 此前写 5015、同页另写 5107+3，实测 5233——三值不一致。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import yaml

from src.tools.patch_evidence import evidence_allows_write

ROOT = Path(__file__).resolve().parents[1]


# ───────────────────────── 1. env_snapshot 完备性 ─────────────────────────


class TestEnvSnapshotCompleteness:
    """快照必须覆盖扫描面内全部开关（防 A1 假阴性事故复发）。"""

    def test_gate_reports_no_missing(self) -> None:
        """门禁本体必须 exit 0（缺失即阻断）。"""
        import subprocess
        import sys

        r = subprocess.run(
            [sys.executable, "scripts/gates/check_env_snapshot_keys.py"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert r.returncode == 0, f"快照门禁应 exit 0，实际 {r.returncode}\n{r.stdout}\n{r.stderr}"

    def test_key_incident_switches_registered(self) -> None:
        """三起已知事故涉及的开关必须在册（本条是最小防复发集）。"""
        src = (ROOT / "experiments" / "run_benchmark.py").read_text(encoding="utf-8")
        m = re.search(r"_env_snapshot_keys\s*=\s*\[(.*?)\n    \]", src, re.S)
        assert m, "未找到 _env_snapshot_keys 字面量"
        keys = set(re.findall(r'"([A-Z0-9_]+)"', m.group(1)))
        for probe in (
            "PLAN_STRIP_EXPECTED_OUTPUT_ENABLE",  # A1 假阴性
            "OVER_RED_SECTION_ENABLE",  # D3 登记缺陷
            "DETECTION_FIRST_SECTION_ENABLE",  # RT1 未登记
            "SPEC_ORACLE_EXEC_ENABLE",  # P0-4 新增指标配套
            "PATCH_EVIDENCE_GATE_ENABLE",  # I-27/E6 主变量
            "PYTEST_TIMEOUT_ENABLE",  # 执行器挂死修复配套
        ):
            assert probe in keys, f"{probe} 未登记进 _env_snapshot_keys（干预生效性将不可审计）"

    def test_snapshot_size_not_regressed(self) -> None:
        """键数不得回退（本轮从 39 补到 98）。"""
        src = (ROOT / "experiments" / "run_benchmark.py").read_text(encoding="utf-8")
        m = re.search(r"_env_snapshot_keys\s*=\s*\[(.*?)\n    \]", src, re.S)
        keys = re.findall(r'"([A-Z0-9_]+)"', m.group(1))
        assert len(keys) >= 98, f"快照键数回退：{len(keys)} < 98"


# ───────────────────────── 2. 证据门分档 ─────────────────────────


class TestEvidenceGateTiering:
    """I-29：门限可下移，但默认必须与历史口径逐字一致。"""

    @pytest.mark.parametrize(
        ("level", "expected"),
        [("gold", True), ("sbfl", True), ("keyword", False), ("none", False)],
    )
    def test_default_threshold_is_sbfl(self, monkeypatch: pytest.MonkeyPatch, level: str, expected: bool) -> None:
        """未设门限 → 历史二值口径（gold/sbfl 放行）。"""
        monkeypatch.delenv("PATCH_EVIDENCE_GATE_MIN_LEVEL", raising=False)
        assert evidence_allows_write(level) is expected

    @pytest.mark.parametrize(
        ("level", "expected"),
        [("gold", True), ("sbfl", True), ("keyword", True), ("none", False)],
    )
    def test_keyword_threshold_admits_keyword_only(
        self, monkeypatch: pytest.MonkeyPatch, level: str, expected: bool
    ) -> None:
        """门限下移到 keyword：只多放行 keyword，none 仍拒（不放宽到无证据）。"""
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_MIN_LEVEL", "keyword")
        assert evidence_allows_write(level) is expected

    def test_gold_threshold_is_stricter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """门限上移到 gold：sbfl 也被拒（收紧方向同样可用）。"""
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_MIN_LEVEL", "gold")
        assert evidence_allows_write("gold") is True
        assert evidence_allows_write("sbfl") is False

    def test_illegal_threshold_falls_back_conservatively(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """非法门限值 → 回退历史口径，**不得静默放宽**。"""
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_MIN_LEVEL", "not-a-level")
        assert evidence_allows_write("sbfl") is True
        assert evidence_allows_write("keyword") is False

    def test_unknown_level_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """未知等级保守拒绝（与"任何异常降级 none"同口径）。"""
        monkeypatch.delenv("PATCH_EVIDENCE_GATE_MIN_LEVEL", raising=False)
        assert evidence_allows_write("weird-level") is False


# ───────────────────────── 3. BASELINE 数字一致 ─────────────────────────


class TestBaselineNumbersConsistency:
    """G11：文档中的当前数字必须与实测一致（单一事实来源纪律）。"""

    def test_baseline_parses(self) -> None:
        d = yaml.safe_load((ROOT / "BASELINE.yaml").read_text(encoding="utf-8"))
        assert "tests" in d and "static_checks" in d

    def test_tests_and_mypy_are_current(self) -> None:
        """`total_passed` 必须与 `--collect-only` 自洽，且字段形状合法。

        重要校正（本测试初版写错，已修）：pytest 的 "N tests collected"
        **已把 skip/xfail 计入**，故 `collected == passed + skipped + xfailed`
        是**错误等式**。可确证的只有：
          ① `passed` 不得大于 `collected`；
          ② `passed` 应接近 `collected`（差值 ≤ skipped + xfailed + 余量）；
          ③ `total_failed == 0`；④ mypy 源文件数 ≥ 119。

        S7（2026-10-11 独立评审落地）：**收紧余量**。原余量为固定 `+5`，
        但真正的判据是 `collected − passed ≈ skipped + xfailed`——
        `+5` 会让"新增了若干测试但忘了刷新 BASELINE"悄悄通过（实测该漂移
        已累积到 101 例）。现按 skipped + xfailed 精确对账、余量降为
        `+1`（容忍 collect 口径的 ±1 抖动），使**任何新增测试都必须同步
        刷新 BASELINE.yaml**。仍不硬编码精确值（保持"新增即刷新"而非
        "改本测试"的维护语义）。
        """
        import subprocess
        import sys

        d = yaml.safe_load((ROOT / "BASELINE.yaml").read_text(encoding="utf-8"))
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q", "-p", "no:cacheprovider"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
        m = re.search(r"(\d+) tests collected", r.stdout)
        assert m, f"无法解析 collect 数：{r.stdout[-400:]}"
        collected = int(m.group(1))
        t = d["tests"]
        declared = t["total_passed"]
        assert declared <= collected, f"BASELINE total_passed={declared} > 实收 {collected}（不可能）"
        # S7（2026-10-11 独立评审落地）：按 skipped + xfailed 精确对账，
        # 余量从固定 +5 收紧为 +1（容忍 collect 口径 ±1 抖动）。原 +5 使
        # "新增测试但忘刷 BASELINE"可静默通过——该漂移实测已累积 101 例。
        slack = t["total_skipped"] + t["total_xfailed"] + 1
        assert collected - declared <= slack, (
            f"BASELINE 与实收差距过大：实收 {collected} − passed {declared} = {collected - declared} > {slack}"
            f"（期望 collected − passed ≈ skipped({t['total_skipped']}) + xfailed({t['total_xfailed']})）；"
            "BASELINE 数字已过期，请跑全量 pytest 后刷新 total_passed"
        )
        assert t["total_failed"] == 0
        assert d["static_checks"]["mypy_source_files"] >= 119

    def test_no_stale_test_count_in_baseline(self) -> None:
        """`total_passed` 字段不得再是过期值（防三值矛盾复发）。

        注：只校验**字段值**，不全文搜 "5107"——该数字在 `benchmark.ci_gates_2026_10_09`
        节里作为**历史记录**合法存在（当次 CI 实测），删掉反而是丢失证据。
        """
        d = yaml.safe_load((ROOT / "BASELINE.yaml").read_text(encoding="utf-8"))
        assert d["tests"]["total_passed"] not in (5015, 5107), "total_passed 仍是过期值"
        assert isinstance(d["tests"]["total_passed"], int)


# ───────────────────────── 4. 分析脚本可导入 ─────────────────────────


class TestAnalysisScriptsImportable:
    """本轮新增的分析脚本必须可导入（防止语法/依赖漂移）。"""

    @staticmethod
    def _load(path: Path, name: str):
        """按文件路径载入模块（须先注册 sys.modules——dataclass/typing 会回查它）。"""
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.modules.pop(name, None)
        return mod

    def test_four_channel_recompute_importable(self) -> None:
        self._load(ROOT / "experiments" / "four_channel_recompute.py", "_t_four_channel")

    def test_run_logic_ab_importable(self) -> None:
        mod = self._load(ROOT / "scripts" / "tools" / "run_logic_ab.py", "_t_run_logic_ab")
        # 关键：过滤数据集构造器存在（挂死任务排除用）
        assert hasattr(mod, "_build_filtered_dataset")

    def test_patch_evidence_min_level_env_registered(self) -> None:
        """新开关必须出现在 env 预算登记表（P0-5 冻结决策）。"""
        names = yaml.safe_load((ROOT / "docs" / "env_budget.yaml").read_text(encoding="utf-8"))["names"]
        assert os.environ is not None  # 保持 import 使用
        assert "PATCH_EVIDENCE_GATE_MIN_LEVEL" in names, "新开关未登记 docs/env_budget.yaml"


# ───────── 5. SWE-bench 导出脚本字段名（2026-10-10 E7 修复回归锁）─────────


class TestSweBenchExportFieldName:
    """`export_swe_bench_source.py` 必须读官方 JSONL 的 `repo` 字段。

    事前教训（E7）：脚本只读 `data.get("repository")`，而官方 SWE-bench JSONL
    的字段名是 **`repo`** → 恒取到 "" → `resolve_repo_dir("")` 回退 cwd →
    `git show` 在**当前工作目录**执行 → 全部实例 `not a git repository`
    → **该脚本从未成功导出过任何源码**（实测修复前 225/225 失败、产物 0 行）。
    修复后 48/225 成功。本测试防止字段名再次漂移。
    """

    def test_reads_repo_field_not_repository(self, tmp_path: Path) -> None:
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location(
            "_t_export", ROOT / "scripts" / "tools" / "export_swe_bench_source.py"
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_t_export"] = mod
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.modules.pop("_t_export", None)

        # 官方 JSONL 形态：只有 `repo`，没有 `repository`
        official = [
            {
                "instance_id": "sqlfluff__sqlfluff-4764",
                "repo": "sqlfluff/sqlfluff",
                "base_commit": "a820c139ccbe",
                "patch": "diff --git a/src/sqlfluff/cli/commands.py b/src/sqlfluff/cli/commands.py\n--- a/x\n+++ b/src/sqlfluff/cli/commands.py\n",
            }
        ]
        res = mod.export_instance_sources(official, repos_dir=tmp_path, dry_run=True)
        assert res, "应产出 1 条（dry-run）"
        assert res[0].repository == "sqlfluff/sqlfluff", (
            f"未读到 repo 字段：repository={res[0].repository!r}（字段名漂移会导致全量导出失败）"
        )

    def test_repository_field_still_supported(self, tmp_path: Path) -> None:
        """兼容自建/旧版 JSONL 的 `repository` 键（双读，不回归）。"""
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location(
            "_t_export2", ROOT / "scripts" / "tools" / "export_swe_bench_source.py"
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_t_export2"] = mod
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.modules.pop("_t_export2", None)
        legacy = [
            {
                "instance_id": "x__y-1",
                "repository": "org/name",
                "base_commit": "abc",
                "patch": "+++ b/f.py\n",
            }
        ]
        res = mod.export_instance_sources(legacy, repos_dir=tmp_path, dry_run=True)
        assert res and res[0].repository == "org/name"


# ───────── 6. SWE-bench 截断节点 ID 净化（E7 §5.4 回归锁）─────────


class TestSweBenchMalformedNodeIdSanitization:
    """被截断的参数化节点 ID 必须被剔除并留痕。

    事前教训（E7 §5.4，实测）：上游 `princeton-nlp/SWE-bench` 的
    FAIL_TO_PASS/PASS_TO_PASS 含被截断的参数化节点 ID（530/24,122 = 2.20%，
    跨 sqlfluff/pydicom/marshmallow/astroid），如
    `…jinja_test.py::test__templater_jinja_slice_file[{%`（缺 `-if …-%}]`）。

    危害：pytest 对无法匹配的节点 ID 报 `ERROR: not found: <id>` 并以
    **rc=4 中止整个调用** → **一个坏 ID 毒化该任务全部测试**（实测：单独给
    合法 ID 得 rc=1「1 failed」，混入坏 ID 后变 rc=4「no tests ran」）。

    修法：加载期剔除坏 ID（不猜补全），并把剔除项写入
    `fail_to_pass_malformed_ids` / `pass_to_pass_malformed_ids` 供下游知晓
    覆盖率折损。
    """

    @staticmethod
    def _cls():
        from src.datasets.dataset_loader import SWEBenchDataset

        return SWEBenchDataset

    def test_truncated_id_dropped_and_recorded(self) -> None:
        kept, dropped = self._cls()._drop_malformed_test_ids(
            [
                "test/api/simple_test.py::test__api__lint_string",
                "test/core/templaters/jinja_test.py::test__templater_jinja_slice_file[{%",
                "test/core/templaters/jinja_test.py::test__templater_jinja_slice_file[{%-",
            ]
        )
        assert kept == ["test/api/simple_test.py::test__api__lint_string"]
        assert len(dropped) == 2, f"应剔除 2 个截断 ID，实得 {dropped}"

    def test_wellformed_parametrized_id_kept(self) -> None:
        """闭合的参数化 ID 必须保留（不得误杀）。"""
        good = "test/core/templaters/jinja_test.py::test__templater_jinja_slice_file[{%-if x-%}]"
        kept, dropped = self._cls()._drop_malformed_test_ids([good])
        assert kept == [good], "闭合 ID 被误杀"
        assert dropped == []

    def test_non_parametrized_id_kept(self) -> None:
        kept, dropped = self._cls()._drop_malformed_test_ids(["test/a.py::test_b"])
        assert kept == ["test/a.py::test_b"] and dropped == []

    def test_no_guessing_completion(self) -> None:
        """绝不"补全"截断 ID（宁缺毋滥）。"""
        bad = "test/x.py::test_y[abc"
        kept, dropped = self._cls()._drop_malformed_test_ids([bad])
        assert kept == [] and dropped == [bad], "不得把截断 ID 猜成完整形态"
