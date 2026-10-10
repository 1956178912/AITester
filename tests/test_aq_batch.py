"""AQ 批次（2026-10-07 第十五轮审查续二）锁定测试。

覆盖三项自主执行项：
- AQ1 工作表 v2：每候选节增补"patch vs gold fixed 逐行差异"（difflib
  unified diff，机械对比备料不裁决）——生成器产出 diff 节、工件已登记
  SHA256SUMS、围栏无破损；
- AQ3 工件引用链扩展：check_artifacts_tracked MANIFEST 登记 prereg 双语
  E7 节引用的两个复核工件（11→13），清单长度锁定；
- AQ2/AQ4 survey 打包陈旧声称勘误：PEP 621/[build-system]/license 三处
  P0 结论系 O9 批（2026-09-29）落地前的过期评估，勘误后旧声称不得残留。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

WORKSHEET = PROJECT_ROOT / "experiments" / "results" / "main_batch" / "e7_review_worksheet.md"

# 2026-10-09 清理批次：survey 文档与根目录 5 份 *_BASELINE_2023-2026.md 一并
# 删除（scripts/gates/check_bilingual_docs.py 的 _EXEMPT_NO_EN 豁免条目亦同步移除）。
# 本文件原先在**模块级**执行 read_text()——文档一旦缺失，pytest 会在
# **收集阶段**即抛 FileNotFoundError，导致整个测试套件无法运行（实测：
# 全量 pytest 在 tests/test_aq_batch.py 处 Interrupted: 1 error during
# collection）。改为惰性读取 + 缺失即空串，配合下方 skip：
#   - 不再阻断收集；
#   - 文档若回归，两条断言自动恢复生效（不留死代码）。
_SURVEY_PATH = PROJECT_ROOT / "docs" / "Python工程化前沿基线（2024–2026）.md"
SURVEY = _SURVEY_PATH.read_text(encoding="utf-8") if _SURVEY_PATH.is_file() else ""

_E7_ARTIFACTS = (
    "experiments/results/main_batch/e7_repair_sample_candidates.md",
    "experiments/results/main_batch/e7_review_worksheet.md",
)


def _load_artifacts_guard() -> Any:
    """以 importlib 加载 scripts/gates/check_artifacts_tracked.py（scripts 非包）。"""
    spec = importlib.util.spec_from_file_location(
        "check_artifacts_tracked_under_test",
        PROJECT_ROOT / "scripts" / "gates" / "check_artifacts_tracked.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestWorksheetV2Diff:
    """AQ1：工作表 v2 的逐行差异段（机械对比备料，判定仍属人工）。"""

    def test_generator_produces_diff_sections(self) -> None:
        """当前生成器对真实工件渲染产出 8 个 diff 节（防特性被静默移除）。"""
        from experiments.repair_review_worksheet import render_worksheet
        from experiments.repair_sample_selection import (
            _DEFAULT_BATCHES,
            build_sampling_frame,
            select_stratified_sample,
            stratify,
        )
        from experiments.statistical_analysis import load_experiment_results_with_sources

        results, source_files = load_experiment_results_with_sources(
            "experiments/results/main_batch",
            list(_DEFAULT_BATCHES),
            allow_schema_mixed=False,
            pool_seeds=True,
        )
        strata = stratify(build_sampling_frame(results.get("aitester") or []))
        selected = select_stratified_sample(strata, 0.10, 42)
        rendered = render_worksheet(selected, source_files, 0.10, 42)
        assert rendered.count("### patch vs gold fixed") == 8
        assert rendered.count("````diff") == 8

    def test_artifact_diff_sections_and_fences(self) -> None:
        """入库工件与生成器一致：8 个 diff 节、四反引号围栏无破损、
        SHA256SUMS 登记在案。"""
        content = WORKSHEET.read_text(encoding="utf-8")
        assert content.count("### patch vs gold fixed") == 8
        assert content.count("````diff") == 8
        lines = content.splitlines()
        assert not [line for line in lines if line.startswith("``````")]
        assert not [line for line in lines if re.match(r"^```($|[^`])", line)]
        sums = (PROJECT_ROOT / "experiments" / "results" / "main_batch" / "SHA256SUMS").read_text(encoding="utf-8")
        assert "e7_review_worksheet.md" in sums


class TestArtifactsManifestE7:
    """AQ3：prereg 引用的 E7 复核工件纳入入库守卫（AK3 引用链口径）。"""

    def test_manifest_registers_e7_artifacts(self) -> None:
        """MANIFEST 含两个 E7 工件且清单长度锁定为 21（漏登记属新缺口）。

        R14（2026-10-08 R2）：登记 8 个 r4_batches 路径（6 批次 JSON +
        README + SHA256SUMS），清单 13→21——R4/QuixBugs 存量批次此前滞留
        /tmp（易失、违反预注册工件条款），入库后成为口径矩阵与勘误的
        证据链。长度锁随显式登记推进（同 AO 改 cap 同步 test_am 先例）。
        """
        module = _load_artifacts_guard()
        for rel in _E7_ARTIFACTS:
            assert rel in module.MANIFEST, f"MANIFEST 缺少 {rel}"
        assert len(module.MANIFEST) == 21


class TestSurveyPackagingErrata:
    """AQ2/AQ4：survey 打包陈旧声称勘误（PEP 621 系 O9 已达成项）。

    前提说明：本组断言以 survey 文档为载体。该文档已于 2026-10-09 清理批次
    删除，故两条用例在文档缺失时 **skip**（而非 fail / 而非阻断收集）。
    """

    def _require_survey(self) -> None:
        """survey 文档缺失时显式跳过（清理批次已删除该文件，见模块级说明）。"""
        if not SURVEY:
            pytest.skip(
                "survey 文档已随 2026-10-09 清理批次删除，勘误断言无载体；"
                "打包事实本身由 tests/test_packaging.py 与 CI 门禁继续覆盖"
            )

    def test_stale_packaging_claims_absent(self) -> None:
        """三处过期 ❌ 结论不得残留（无 [project] / 无 [build-system] /
        完全没有 license）——勘误文本对旧结论的**引用**不算残留，
        故断言锚定旧句的原始表格语境（❌ 前缀 / 完整旧句）。"""
        self._require_survey()
        assert "无 `[project]`、无 `[build-system]`" not in SURVEY
        assert "元数据全在 `setup.py`（name/version/python_requires" not in SURVEY
        assert "❌ 完全没有 license 声明" not in SURVEY
        assert "完全没有 license 元数据。这既是合规缺口" not in SURVEY

    def test_errata_markers_present(self) -> None:
        """勘误标记与现状结论在位（O9 已达成 + AQ 勘误留痕 + PEP 639 剩余
        差距→AS 批闭环后的现状）。AS 批（同日）把 license 行推进为
        "已达成"，本测试的 AQ 时代断言随状态演进而更新（同 AO 改 cap
        常数时同步 test_am_batch 先例）。"""
        self._require_survey()
        assert "已达成（O9 批，2026-09-29" in SURVEY
        assert "AQ 批 2026-10-07 勘误" in SURVEY
        assert "已达成（AS 批，2026-10-07）" in SURVEY
        assert "License-Expression: MIT" in SURVEY
        assert "setuptools>=77" in SURVEY
