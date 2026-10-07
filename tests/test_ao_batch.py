"""AO 批次（2026-10-07 第十五轮审查落地）锁定测试。

覆盖五项自主执行项（第十五轮审查报告 R15-4/R15-7/R15-9 + E7 前置）：
- AO1 E6 预注册修订：matched cap 改取 E2 实测均值（shell 占位变量注入），
  R-P0-2 旧常数（26,115/4,223）不得再以字面 cap 出现；修订效力声明在场；
- AO2 CI 安装切换 requirements.lock：test/smoke 作业安装与缓存键走 lock
  （132 项全量钉版），lock 含关键测试工具链；
- AO3 en README 头部 Last updated 与 AN/AO 批次同步（修内部日期漂移）；
- AO4 U10 弃用别名移除时间线定档（v0.8.0）；
- AO5 E7 候选清单工件：存在、口径齐全、SHA256SUMS 登记、真实工件上
  确定性复算逐位一致。
"""

from __future__ import annotations

import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PREREG_ZH = (PROJECT_ROOT / "docs" / "preregistration.md").read_text(encoding="utf-8")
PREREG_EN = (PROJECT_ROOT / "docs" / "preregistration.en.md").read_text(encoding="utf-8")
CI_YML = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
README_EN_HEAD = "\n".join((PROJECT_ROOT / "README.en.md").read_text(encoding="utf-8").splitlines()[:10])
E7_ARTIFACT = PROJECT_ROOT / "experiments" / "results" / "main_batch" / "e7_repair_sample_candidates.md"


class TestPreregE6CapAmendment:
    """AO1：E6 matched cap 来源修订（R-P0-2 常数 → E2 实测均值）锁定。"""

    def test_amendment_marker_and_effect_statement(self) -> None:
        """修订标记与效力声明双语在场（修订时点早于任何 E6 数据）。"""
        assert "AO 修订，2026-10-07，早于任何 E6 数据" in PREREG_ZH
        assert "修订效力声明" in PREREG_ZH
        assert "E2 实测均值" in PREREG_ZH
        assert "amended by batch AO, 2026-10-07" in PREREG_EN
        assert "Amendment effect statement" in PREREG_EN
        assert "E2 measured means" in PREREG_EN

    def test_extraction_command_present(self) -> None:
        """就绪命令含"E2 实测均值提取"步骤（行级 token_usage 聚合口径）。"""
        for text in (PREREG_ZH, PREREG_EN):
            assert "mean_total_tokens_per_task" in text
            assert "token_usage']['total_tokens']" in text

    def test_placeholder_caps_in_both_languages(self) -> None:
        """双语命令块均以占位变量注入两个 matched 臂的 cap。"""
        for text in (PREREG_ZH, PREREG_EN):
            assert '--per-task-token-caps "aitester=${DF_MEAN}"' in text
            assert '--per-task-token-caps "plain_llm_df=${AITESTER_MEAN}"' in text


class TestCILockInstall:
    """AO2：CI 执行环境切换 requirements.lock（R15-7）锁定。"""

    def test_ci_yaml_parses(self) -> None:
        """ci.yml 可被 YAML 解析器加载（防块标量语法回归）。"""
        import yaml

        cfg = yaml.safe_load(CI_YML)
        assert isinstance(cfg, dict) and "jobs" in cfg

    def test_install_and_cache_use_lock(self) -> None:
        """test/smoke 两作业安装走 lock 且无 requirements.txt 安装残留；
        缓存键随 lock（2 处：test + smoke）。"""
        assert CI_YML.count("pip install -r requirements.lock") == 2
        assert "pip install -r requirements.txt" not in CI_YML
        assert CI_YML.count("cache-dependency-path: requirements.lock") == 2

    def test_lock_contains_test_toolchain(self) -> None:
        """lock 全量钉版覆盖测试工具链（pytest 系/ruff/hypothesis/coverage）。"""
        lock = (PROJECT_ROOT / "requirements.lock").read_text(encoding="utf-8")
        for pin in (
            "pytest==",
            "pytest-cov==",
            "pytest-xdist==",
            "pytest-timeout==",
            "ruff==",
            "hypothesis==",
            "coverage==",
        ):
            assert pin in lock, f"requirements.lock 缺少 {pin} 钉版"


class TestReadmeEnHeader:
    """AO3：en README 头部 Last updated 与最新批次同步。"""

    def test_head_updated_line_current(self) -> None:
        """头部日期行为 2026-10-07 且提及 AO 批（不再滞留 2026-10-06/AM）。"""
        assert "Last updated: 2026-10-07" in README_EN_HEAD
        assert "batch AO" in README_EN_HEAD


class TestDeprecationTimeline:
    """AO4：U10 弃用别名移除时间线定档。"""

    def test_old_alias_warns_with_removal_version(self) -> None:
        """entry_ocurrence_stat 旧名触发 DeprecationWarning 且含 v0.8.0 移除档。"""
        from src.agents.failure_kb import entry_ocurrence_stat

        entries = [{"error_category": "assertion", "target_module": "foo"}]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            entry_ocurrence_stat(entries, "assertion", {"error_category": "assertion"})
        messages = [str(item.message) for item in caught if item.category is DeprecationWarning]
        assert messages, "旧名未触发 DeprecationWarning"
        assert any("v0.8.0" in message for message in messages)


class TestE7CandidateArtifact:
    """AO5：E7 修复上限抽样候选清单（预注册 E7 的人工复核入口）。"""

    def test_artifact_registered_with_checksums(self) -> None:
        """候选清单存在、口径齐全且已登记 SHA256SUMS。"""
        content = E7_ARTIFACT.read_text(encoding="utf-8")
        assert content.startswith("# E7")
        assert "seed=42" in content
        assert "（待复核）" in content
        sums = (PROJECT_ROOT / "experiments" / "results" / "main_batch" / "SHA256SUMS").read_text(encoding="utf-8")
        assert "e7_repair_sample_candidates.md" in sums

    def test_sampling_deterministic_on_real_artifacts(self) -> None:
        """真实批次工件上同参复算：两次抽样 task_id 序列逐位一致，且行数
        与候选清单登记行数一致（预注册确定性口径）。"""
        from experiments.repair_sample_selection import (
            _DEFAULT_BATCHES,
            build_sampling_frame,
            select_stratified_sample,
            stratify,
        )
        from experiments.statistical_analysis import load_experiment_results_with_sources

        results, _ = load_experiment_results_with_sources(
            "experiments/results/main_batch",
            list(_DEFAULT_BATCHES),
            allow_schema_mixed=False,
            pool_seeds=True,
        )
        frame = build_sampling_frame(results.get("aitester") or [])
        strata = stratify(frame)
        first = [r["task_id"] for r in select_stratified_sample(strata, 0.10, 42)]
        second = [r["task_id"] for r in select_stratified_sample(strata, 0.10, 42)]
        assert first == second
        content = E7_ARTIFACT.read_text(encoding="utf-8")
        assert len(first) == content.count("（待复核）")

    def test_frame_single_stratum_disclosed(self) -> None:
        """抽样框分层信息在清单中如实披露（当前 72 行全部 sbfl 单层）。"""
        content = E7_ARTIFACT.read_text(encoding="utf-8")
        assert "sbfl" in content
        assert "72 行" in content
