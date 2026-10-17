#!/usr/bin/env python3
"""工件 git 入库守卫（`scripts/gates/check_artifacts_tracked.py`）的回归锁定。

锁定四件事（2026-10-17 独立评审 A-04）：

1. **emse_* 目录覆盖扫描**：每个 `experiments/results/emse_*/` 目录必须
   git 入库或显式登记豁免——防"新结果目录静默缺席"复发（四批旗舰工件
   曾 0 跟踪而无门禁察觉）；
2. **豁免必须带理由**：`EMSE_DIR_EXEMPTIONS` 的值一律为非空字符串；
3. **真扫描真的会失败**：构造未跟踪目录必须被 `_scan_emse_dirs` 报出；
4. **MANIFEST 无重复条目**（重复登记会掩盖清单增长审计）。

注意：本测试在真实仓库上运行（门禁语义依赖 git），不 mock git。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_GATE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "gates" / "check_artifacts_tracked.py"
_spec = importlib.util.spec_from_file_location("_artifacts_tracked_gate", _GATE_PATH)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
sys.modules["_artifacts_tracked_gate"] = gate
_spec.loader.exec_module(gate)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestManifestHygiene:
    def test_manifest_has_no_duplicates(self):
        assert len(gate.MANIFEST) == len(set(gate.MANIFEST)), "MANIFEST 存在重复条目"

    def test_manifest_entries_exist_in_worktree(self):
        """清单内每个路径必须存在于工作区（缺失=引用链断裂，门禁应红）。"""
        missing = [rel for rel in gate.MANIFEST if not (PROJECT_ROOT / rel).exists()]
        assert not missing, f"MANIFEST 条目不存在于工作区: {missing}"

    def test_manifest_covers_q_round_chain(self):
        """Q 轮（2026-10-18）：示例生产化 A/B / 事故披露 / 后处理墙钟工件必须在清单。"""
        required_substrings = (
            "q_round_examples_ab_20261018/ANALYSIS_REPORT.json",
            "q_round_examples_ab_20261018/SHA256SUMS",
            "q_round_examples_ab_20261018/_incident_unintended_llm_launch_20261018/README_INCIDENT.md",
            "q_round_postprocess_wall_20261018/SHA256SUMS",
        )
        for needle in required_substrings:
            assert any(needle in rel for rel in gate.MANIFEST), f"清单缺少 Q 轮工件条目: {needle}"

    def test_manifest_covers_r_round_chain(self):
        """R 轮（2026-10-18）：seed-43 复现批与示例自校验工件必须在清单。"""
        required_substrings = (
            "r_round_examples_repro_20261018/DIAGNOSIS.md",
            "r_round_examples_repro_20261018/PREREG_REPRO.md",
            "r_round_examples_repro_20261018/SHA256SUMS",
            "r_round_examples_selfcheck_20261018/FILTER_STATS.json",
            "r_round_examples_selfcheck_20261018/SHA256SUMS",
        )
        for needle in required_substrings:
            assert any(needle in rel for rel in gate.MANIFEST), f"清单缺少 R 轮工件条目: {needle}"

    def test_manifest_covers_s_round_chain(self):
        """S 轮（2026-10-18）：3-seed 决策 / B8 注入 / 多采样评估工件必须在清单。"""
        required_substrings = (
            "s_round_examples_decision_20261018/PREREG_DECISION.md",
            "s_round_examples_decision_20261018/SHA256SUMS",
            "s_round_b8_injection_20261018/ISOLATION.json",
            "s_round_b8_injection_20261018/REPORT.json",
            "s_round_examples_multisample_20261018/MULTISAMPLE_STATS.json",
        )
        for needle in required_substrings:
            assert any(needle in rel for rel in gate.MANIFEST), f"清单缺少 S 轮工件条目: {needle}"

    def test_manifest_covers_df_spec_chain(self):
        """A-04：df_spec / M4 / D1 / ULT-df200 四批旗舰工件的关键件必须在清单。"""
        required_substrings = (
            "emse_df_spec_20261016/DF_SPEC_REPORT.json",
            "emse_df_spec_20261016/SHA256SUMS",
            "emse_quixbugs_specir_expand_20261014/QUIXB_EXPAND_ABCD_REPORT.json",
            "emse_d1_quixbugs_ab_20261013/README.md",
            "emse_ult_df200_20261017/ACCURACY_REPORT.json",
            "emse_ult_df200_20261017/SHA256SUMS",
        )
        for needle in required_substrings:
            assert any(needle in rel for rel in gate.MANIFEST), f"清单缺少旗舰工件条目: {needle}"

    def test_manifest_covers_l_round_chain(self):
        """L 轮（2026-10-17）：P1 三臂批 / misguided 度量 / 自身变异 / pilot 四链证据必须在清单。

        这些工件被 BASELINE `benchmark.docstring_anchor`、`target_quality.
        mechanism_metrics`、`self_mutation` 与登记册 L-1~L-6 直接引用——清单漏登记
        即为"报告引用未入库工件"的引用链断裂（本守卫的核心失效形态）。
        """
        required_substrings = (
            "emse_docstring_anchor_20261017/DF_DOC_REPORT.json",
            "emse_docstring_anchor_20261017/SHA256SUMS",
            "emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_194444.json",
            "emse_misguided_20261017/MISGUIDED_REPORT.json",
            "emse_misguided_docstring_anchor_20261017/MISGUIDED_REPORT.json",
            "self_mutation_l_round/SELF_MUTATION_L_ROUND.md",
            "l_round_pilot_20261017/defect_repro/aborted_full50_run.log",
        )
        for needle in required_substrings:
            assert any(needle in rel for rel in gate.MANIFEST), f"清单缺少 L 轮工件条目: {needle}"

    def test_manifest_covers_m_round_chain(self):
        """M 轮（2026-10-17）：增广批 / oracle 质量 / 编译执行率 / 孤儿根因四链证据必须在清单。

        这些工件被 BASELINE 新增节（`benchmark.docstring_augment`、
        `target_quality.oracle_quality` / `compile_exec`）、MEASUREMENT_INTEGRITY §6
        与登记册 M-1~M-6 直接引用——漏登记即引用链断裂。
        """
        required_substrings = (
            "emse_docstring_augment_20261017/DF_AUG_REPORT.json",
            "emse_docstring_augment_20261017/SHA256SUMS",
            "emse_docstring_augment_20261017/PROMPT_EVIDENCE.json",
            "emse_misguided_augment_20261017/MISGUIDED_REPORT.json",
            "emse_oracle_quality_20261017/ORACLE_QUALITY_REPORT.json",
            "emse_compile_exec_20261017/COMPILE_EXEC_REPORT.json",
            "orphan_repro_20261017/README.md",
        )
        for needle in required_substrings:
            assert any(needle in rel for rel in gate.MANIFEST), f"清单缺少 M 轮工件条目: {needle}"

    def test_manifest_covers_n_round_chain(self):
        """N 轮（2026-10-17）：功能矩阵 / oracle 独立判读 / 真实 LLM 重型探针链必须在清单。"""
        required_substrings = (
            "e2e_probe_20261017/report.json",
            "e2e_probe_workflow_20261017/report.json",
            "e2e_probe_platform_20261017/llm_report.json",
            "emse_oracle_independent_judging_20261017/ORACLE_INDEPENDENT_JUDGING_REPORT.json",
            "e2e_llm_probes_20261017/ITEM_RESULTS.json",
        )
        for needle in required_substrings:
            assert any(needle in rel for rel in gate.MANIFEST), f"清单缺少 N 轮工件条目: {needle}"

    def test_manifest_covers_p_round_chain(self):
        """P 轮（2026-10-18）：示例通道双报告与 B8 消融工件必须在清单。"""
        required_substrings = (
            "p_round_oracle_examples_20261018/ORACLE_EXAMPLES_REPORT.json",
            "p_round_oracle_examples_20261018/ORACLE_EXAMPLES_REPORT_norm.json",
            "p_round_oracle_examples_20261018/SHA256SUMS",
            "p_round_b8_ablation_20261018/ABLATION_REPORT.json",
            "p_round_b8_ablation_20261018/SHA256SUMS",
        )
        for needle in required_substrings:
            assert any(needle in rel for rel in gate.MANIFEST), f"清单缺少 P 轮工件条目: {needle}"

    def test_manifest_covers_o_round_chain(self):
        """O 轮（2026-10-18）：oracle 仪器治疗 / 跨文件路径 / oracle 二臂验证链必须在清单。"""
        required_substrings = (
            "emse_oracle_instrument_hardening_20261017/ORACLE_QUALITY_REPORT.json",
            "emse_oracle_instrument_hardening_20261017/SHA256SUMS",
            "o_round_cross_file_20261017/O3_EVIDENCE.json",
            "emse_oracle_enabled_validation_20261017/ARM_COMPARISON.json",
        )
        for needle in required_substrings:
            assert any(needle in rel for rel in gate.MANIFEST), f"清单缺少 O 轮工件条目: {needle}"


class TestEmseDirScan:
    def test_exemptions_have_reasons(self):
        for name, reason in gate.EMSE_DIR_EXEMPTIONS.items():
            assert reason and reason.strip(), f"豁免 {name} 未登记理由"
            assert not name.endswith("/"), "豁免名应为目录名（不带斜杠）"

    def test_scan_passes_on_current_repo(self):
        """当前仓库（四批旗舰已 force-add 后）覆盖扫描必须零违例。"""
        offenders = gate._scan_emse_dirs()
        assert offenders == [], f"emse_* 目录存在未入库且未豁免者: {offenders}"

    def test_scan_flags_untracked_dir(self, tmp_path, monkeypatch):
        """构造一个未跟踪的 emse_* 目录，扫描必须报错（防扫描退化为永真）。"""
        fake_results = tmp_path / "experiments" / "results"
        fake_dir = fake_results / "emse_fake_untracked_20261017"
        fake_dir.mkdir(parents=True)
        (fake_dir / "data.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(gate, "PROJECT_ROOT", tmp_path)
        # 在 fake 仓库里 git ls-files 对不存在仓库返回空 → 视为未跟踪
        offenders = gate._scan_emse_dirs()
        rels = [rel for rel, _ in offenders]
        assert any("emse_fake_untracked_20261017" in rel for rel in rels), f"未检出未跟踪目录: {offenders}"

    def test_exempt_dir_is_skipped(self, tmp_path, monkeypatch):
        """登记豁免的目录即使未跟踪也不报。"""
        fake_results = tmp_path / "experiments" / "results"
        fake_dir = fake_results / "emse_d2_profile_smoke_20261013"
        fake_dir.mkdir(parents=True)
        monkeypatch.setattr(gate, "PROJECT_ROOT", tmp_path)
        offenders = gate._scan_emse_dirs()
        assert offenders == [], f"豁免目录被误报: {offenders}"


class TestGateEndToEnd:
    def test_gate_exit_zero_on_current_repo(self):
        """端到端：当前暂存/提交态下门禁 exit 0。"""
        result = subprocess.run(
            [sys.executable, str(_GATE_PATH)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"门禁失败:\n{result.stdout}\n{result.stderr}"
