"""AP 批次（2026-10-07 第十五轮审查续）锁定测试。

覆盖四项自主执行项：
- AP1 E7 复核工作表：存在、登记 SHA256SUMS、四段素材齐全、围栏无破损、
  确定性复算逐位一致（预注册 E7 人工复核的备料工件）；
- AP2 E6 token 字段 schema 守卫：三种子批次行的 `token_usage.total_tokens`
  路径在位——预注册 E6"第 1 步提取均值"命令依赖该字段，改名会静默断链；
- AP3 check_tool_versions 缩进盲区修复：pre-commit rev（YAML 缩进行）
  此前恒报 "<absent>"，ci↔hook 一致性校验形同虚设——修复后须真实检出
  且与 CI 一致（经 importlib 直调 main()，不启用子进程）；
- AP4 survey 文档陈旧声称：CI 安装口径已切 lock（AO2），"CI 里是裸
  pip install -r requirements.txt" 的旧行不得残留。
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PREREG_ZH = (PROJECT_ROOT / "docs" / "preregistration.md").read_text(encoding="utf-8")
PREREG_EN = (PROJECT_ROOT / "docs" / "preregistration.en.md").read_text(encoding="utf-8")
WORKSHEET = PROJECT_ROOT / "experiments" / "results" / "main_batch" / "e7_review_worksheet.md"
LIFECYCLE_BATCHES = (
    "benchmark_synthetic_20261006_140906.json",
    "benchmark_synthetic_20261006_151907.json",
    "benchmark_synthetic_20261006_164357.json",
)
_MATERIAL_HEADINGS = (
    "### 生成补丁（patch）",
    "### gold fixed",
    "### gold 官方测试",
    "### 最终生成测试",
)


def _load_checker_module() -> Any:
    """以 importlib 加载 scripts/check_tool_versions.py（scripts 非包）。"""
    spec = importlib.util.spec_from_file_location(
        "check_tool_versions_under_test",
        PROJECT_ROOT / "scripts" / "check_tool_versions.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestE7ReviewWorksheet:
    """AP1：E7 对照式复核工作表（人工复核备料，不裁决）。"""

    def test_worksheet_registered_with_checksums(self) -> None:
        """工作表存在、口径齐全且已登记 SHA256SUMS。"""
        content = WORKSHEET.read_text(encoding="utf-8")
        assert content.startswith("# E7 修复上限人工复核工作表")
        assert "seed=42" in content
        assert "equivalent / plausible_overfit / wrong_location / test_only / incomplete" in content
        sums = (PROJECT_ROOT / "experiments" / "results" / "main_batch" / "SHA256SUMS").read_text(encoding="utf-8")
        assert "e7_review_worksheet.md" in sums

    def test_worksheet_sections_and_fences(self) -> None:
        """8 个候选节各含四段素材与判定勾选；围栏恰为四反引号无破损。"""
        content = WORKSHEET.read_text(encoding="utf-8")
        lines = content.splitlines()
        assert sum(1 for line in lines if line.startswith("## 候选")) == 8
        for heading in _MATERIAL_HEADINGS:
            assert content.count(heading) == 8, f"素材段缺失：{heading}"
        assert content.count("☐ equivalent") == 8
        # 围栏守卫：不允许 6 反引号（拼接 bug 签名）与裸 3 反引号行
        assert not [line for line in lines if line.startswith("``````")]
        assert not [line for line in lines if re.match(r"^```($|[^`])", line)]

    def test_worksheet_deterministic(self) -> None:
        """同参复算：两次渲染逐位一致，候选节数与工件一致。"""
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
        first = render_worksheet(selected, source_files, 0.10, 42)
        second = render_worksheet(selected, source_files, 0.10, 42)
        assert first == second
        assert first.count("## 候选") == WORKSHEET.read_text(encoding="utf-8").count("## 候选")


class TestE6TokenSchemaGuard:
    """AP2：预注册 E6"提取均值"命令依赖的行级字段路径守卫。"""

    def test_lifecycle_rows_expose_total_tokens(self) -> None:
        """三种子批次 aitester 臂行级 token_usage.total_tokens 均为正整数
        （字段改名会静默断链 E6 就绪命令，此处显式红）。"""
        for name in LIFECYCLE_BATCHES:
            data = json.loads(
                (PROJECT_ROOT / "experiments" / "results" / "main_batch" / name).read_text(encoding="utf-8")
            )
            rows = data["results"]["aitester"]["details"]
            assert rows, f"{name} aitester 臂为空"
            for row in rows:
                usage = row.get("token_usage") or {}
                total = usage.get("total_tokens")
                assert isinstance(total, int) and total > 0, f"{name} 行 {row.get('task_id')} token 路径断裂"


class TestToolVersionCheckerFix:
    """AP3：check_tool_versions 缩进盲区修复（B-05 校验恢复实效）。"""

    def test_pre_commit_versions_detected_and_consistent(self, capsys) -> None:
        """main() 直调成功，且输出真实检出 pre-commit 版本（非 <absent>）。"""
        module = _load_checker_module()
        module.main()  # 失败路径会 sys.exit(1) 使本测试红
        out = capsys.readouterr().out
        assert "B-05 工具版本一致性：OK" in out
        assert "pre-commit=1.15.0" in out
        assert "pre-commit=0.16.3" in out
        assert "<absent>" not in out

    def test_pre_commit_rev_matches_indented_lines(self, tmp_path: Path) -> None:
        """单元锁：带 YAML 缩进的 rev 行可被检出，且块间不串味。"""
        module = _load_checker_module()
        config = tmp_path / ".pre-commit-config.yaml"
        config.write_text(
            "repos:\n"
            "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
            "    # 注释行夹在 repo 与 rev 之间\n"
            "    rev: v0.16.3\n"
            "    hooks:\n"
            "      - id: ruff\n"
            "  - repo: https://github.com/pre-commit/mirrors-mypy\n"
            "    rev: v1.15.0\n"
            "    hooks:\n"
            "      - id: mypy\n",
            encoding="utf-8",
        )
        assert module._pre_commit_rev(config, "astral-sh/ruff-pre-commit") == "0.16.3"
        assert module._pre_commit_rev(config, "pre-commit/mirrors-mypy") == "1.15.0"
        assert module._pre_commit_rev(config, "some/other-repo") is None


class TestSurveyDocFreshness:
    """AP4：survey 文档的 CI 安装口径与 AO2 后现实一致。"""

    def test_no_stale_ci_install_claim(self) -> None:
        """旧行"CI 里是裸 pip install -r requirements.txt"不得残留；
        现口径（lock 安装 + 剩余无 hash 差距）在位。"""
        survey = (PROJECT_ROOT / "docs" / "Python工程化前沿基线（2024–2026）.md").read_text(encoding="utf-8")
        assert "CI 里是裸 `pip install -r requirements.txt`" not in survey
        assert "requirements.lock`（132 项全钉）安装" in survey


class TestPreregWorksheetRef:
    """AP1 配套：预注册 E7 节双语引用工作表路径（复核入口齐备）。"""

    def test_prereg_mentions_worksheet(self) -> None:
        for text in (PREREG_ZH, PREREG_EN):
            assert "e7_review_worksheet.md" in text
