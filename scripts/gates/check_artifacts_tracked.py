#!/usr/bin/env python3
"""AK3（2026-10-06 第十二轮审查 R1）：主批次工件 git 入库守卫。

背景：
    R-P0-2 生死实验的批次工件（3 种子 JSON、两统计报告、MAST 分布
    报告、SHA256SUMS）与预注册文档曾长期处于 untracked 状态——
    statistical_report_3seed_pooled.md 曾声称"git_dirty=False"而工件
    实测 git_dirty=true，且 preregistration.md:24-25 的时间顺序审计
    条款（"入库 commit 必须早于"）在工件未入库时不可执行。本守卫
    把"关键工件必须入库"转为 CI 阻断项：报告引用的每一个证据工件
    都必须被 git 跟踪，否则引用链（报告 → 工件 → commit 时间序）
    断裂。

口径：
    - MANIFEST 为"报告直接引用的证据工件"白名单（新增报告引用新
      工件时同步登记——漏登记属新缺口，可在测试中锁定清单长度）；
    - 只做 git ls-files 存在性判定（零网络、纯本地，秒级）；
    - 文件缺失 / 未跟踪 / 被 .gitignore 忽略分别报错（忽略 = 永远
      不可能入库，需先修 .gitignore 白名单）。

用法：
    python scripts/gates/check_artifacts_tracked.py          # 审计，违规 exit 1
    python scripts/gates/check_artifacts_tracked.py --list   # 打印清单

CI 接线：ci.yml test 作业（仅 3.14 档，工件与 Python 版本无关）。
本地注意：工作树未提交时本守卫会红（这是预期——本地用 make gates
不含本步，入库前的强制项由 CI 承担）。
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# "报告 → 证据工件"引用链清单（相对仓库根）。新增引用新工件时同步登记。
MANIFEST: tuple[str, ...] = (
    # R-P0-2 生死实验三种子批次（statistical_report_3seed_pooled.md 数据来源）
    "experiments/results/main_batch/benchmark_synthetic_20261006_140906.json",
    "experiments/results/main_batch/benchmark_synthetic_20261006_151907.json",
    "experiments/results/main_batch/benchmark_synthetic_20261006_164357.json",
    # canonical 与 pooled 统计报告 + MAST 分布 + 修复上限归因（AK1 新增）
    "experiments/results/main_batch/statistical_report.md",
    "experiments/results/main_batch/statistical_report_3seed_pooled.md",
    "experiments/results/main_batch/mast_distribution_report.md",
    "experiments/results/main_batch/repair_ceiling_report.md",
    # E7 修复上限人工复核工件（AO5 候选清单 + AP1 工作表；AQ 批登记——
    # prereg 双语 E7 节引用的复核入口，入库前本守卫本地预期红）
    "experiments/results/main_batch/e7_repair_sample_candidates.md",
    "experiments/results/main_batch/e7_review_worksheet.md",
    # 完整性锚点与成本价目（$/task 口径依赖）
    "experiments/results/main_batch/SHA256SUMS",
    "experiments/price_table.json",
    # R14（2026-10-08 R2）：R4 / QuixBugs 存量批次入库（口径矩阵与勘误引用的
    # 证据链——此前全部滞留 /tmp，易失且违反预注册工件条款）
    "experiments/results/r4_batches/README.md",
    "experiments/results/r4_batches/SHA256SUMS",
    "experiments/results/r4_batches/r4_ab_arm_a/benchmark_synthetic_20261008_133303.json",
    "experiments/results/r4_batches/r4_ab_arm_b/benchmark_synthetic_20261008_134156.json",
    "experiments/results/r4_batches/r4_synth_arm_b2/benchmark_synthetic_20261008_161508.json",
    "experiments/results/r4_batches/r4_qb_arm_a/benchmark_quixbugs_20261008_165558.json",
    "experiments/results/r4_batches/r4_qb_arm_b/benchmark_quixbugs_20261008_165603.json",
    "experiments/results/r4_batches/loc_test_quix/benchmark_quixbugs_20261007_195728.json",
    # 预注册（时间顺序审计条款的执行前提）
    "docs/preregistration.md",
    "docs/preregistration.en.md",
    # 独立评审 A-04（2026-10-17）：2026-10-14 之后四批旗舰实验工件此前
    # 全部 0 git 跟踪（新结果目录静默缺口——本守卫的硬编码清单不覆盖
    # 新目录，缺口无声复发）。补齐引用链关键件（df_spec / M4 specir 扩样 /
    # D1 / ULT df200），并新增证据目录覆盖扫描（T 轮扩展为 emse_* + *_round_*，
    # 见 _scan_evidence_dirs）。
    "experiments/results/emse_df_spec_20261016/DF_SPEC_REPORT.json",
    "experiments/results/emse_df_spec_20261016/SHA256SUMS",
    "experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json",
    "experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json",
    "experiments/results/emse_quixbugs_specir_expand_20261014/QUIXB_EXPAND_ABCD_REPORT.json",
    "experiments/results/emse_quixbugs_specir_expand_20261014/SHA256SUMS.txt",
    "experiments/results/emse_d1_quixbugs_ab_20261013/README.md",
    "experiments/results/emse_d1_quixbugs_ab_20261013/SHA256SUMS",
    "experiments/results/emse_ult_df200_20261017/ACCURACY_REPORT.json",
    "experiments/results/emse_ult_df200_20261017/SHA256SUMS",
    "experiments/results/emse_ult_df200_20261017/benchmark_ult_20261017_110803.json",
    # spec_compile_rate / spec_expr_coverage 校准链（BASELINE 引用的证据源；
    # 各目录的聚合报告名以实物为准：CALIB.md / CALIB_QB_ULT.json）
    "experiments/results/emse_calib_quixbugs_20261014/benchmark_quixbugs_20261014_165103.json",
    "experiments/results/emse_calib_ult_20261014/benchmark_ult_20261014_165906.json",
    "experiments/results/emse_calib_synth_20261014/CALIB.md",
    "experiments/results/emse_calib_synth_20261014/CALIB.json",
    "experiments/results/emse_calib_synth174_20261014/CALIB_QB_ULT.json",
    # 过红 P1-P4 分类（SUBMISSION_CHECKLIST 引用的证据源）
    "experiments/results/emse_batch5_20261014/OVERRED_P1_P4.json",
    # T-08 双门多种子原始数据（BASELINE §exec_2026_10_09 的 3 种子声称；
    # seed43 目录仅含 traces，由下方 emse_* 目录扫描兜底"整目录入库"）
    "experiments/results/emse_t08_gates_seed44_20261013/benchmark_synthetic_20261014_002657.json",
    # 统计扩展（SUBMISSION_SKELETON 引用的证据源）
    "experiments/results/emse_stats_extensions_20261016/README.md",
    "experiments/results/emse_stats_extensions_20261016/STATS_EXTENSIONS.json",
    # L 轮（2026-10-17）：P1 独立 docstring 锚三臂正式批（真 LLM，预注册判定）
    # —— BASELINE benchmark.docstring_anchor / README 最新优化 / 登记册 L-2 的证据源
    "experiments/results/emse_docstring_anchor_20261017/README.md",
    "experiments/results/emse_docstring_anchor_20261017/SHA256SUMS",
    "experiments/results/emse_docstring_anchor_20261017/DF_DOC_REPORT.json",
    "experiments/results/emse_docstring_anchor_20261017/DF_DOC_REPORT.md",
    "experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_194444.json",
    "experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_193626.json",
    "experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_201928.json",
    # L 轮：misguided/effective 逐测试三分度量报告（MEASUREMENT_INTEGRITY §5 /
    # BASELINE target_quality.mechanism_metrics 的证据源）
    "experiments/results/emse_misguided_20261017/README.md",
    "experiments/results/emse_misguided_20261017/MISGUIDED_REPORT.json",
    "experiments/results/emse_misguided_20261017/MISGUIDED_REPORT.md",
    "experiments/results/emse_misguided_docstring_anchor_20261017/README.md",
    "experiments/results/emse_misguided_docstring_anchor_20261017/MISGUIDED_REPORT.json",
    "experiments/results/emse_misguided_docstring_anchor_20261017/MISGUIDED_REPORT.md",
    # L 轮：自身变异测试击杀批次（BASELINE self_mutation 的证据源）
    "experiments/results/self_mutation_l_round/SELF_MUTATION_L_ROUND.md",
    "experiments/results/self_mutation_l_round/self_mutation_l_round.json",
    # L 轮：真实 LLM 链路 pilot（DEF-1 缺陷证据链；验证性、不构成能力证据）
    "experiments/results/l_round_pilot_20261017/README.md",
    "experiments/results/l_round_pilot_20261017/SHA256SUMS",
    "experiments/results/l_round_pilot_20261017/defect_repro/aborted_full50_run.log",
    # M 轮（2026-10-17）：规格增广二臂正式批（BASELINE benchmark.docstring_augment /
    # README 最新优化 / 登记册 M-2 的证据源；预注册判定 + prompt 一等证据）
    "experiments/results/emse_docstring_augment_20261017/README.md",
    "experiments/results/emse_docstring_augment_20261017/SHA256SUMS",
    "experiments/results/emse_docstring_augment_20261017/DF_AUG_REPORT.json",
    "experiments/results/emse_docstring_augment_20261017/PROMPT_EVIDENCE.json",
    "experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261017_221735.json",
    "experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261017_221948.json",
    # M 轮：misguided/effective 机制重放（增广批）
    "experiments/results/emse_misguided_augment_20261017/README.md",
    "experiments/results/emse_misguided_augment_20261017/MISGUIDED_REPORT.json",
    "experiments/results/emse_misguided_augment_20261017/SHA256SUMS",
    # M 轮：A-05 oracle 质量（MEASUREMENT_INTEGRITY §6 / BASELINE target_quality.oracle_quality 证据源）
    "experiments/results/emse_oracle_quality_20261017/README.md",
    "experiments/results/emse_oracle_quality_20261017/ORACLE_QUALITY_REPORT.json",
    "experiments/results/emse_oracle_quality_20261017/SHA256SUMS",
    # M 轮：A-11 编译/执行率（BASELINE target_quality.compile_exec 证据源）
    "experiments/results/emse_compile_exec_20261017/COMPILE_EXEC_REPORT.json",
    "experiments/results/emse_compile_exec_20261017/SHA256SUMS",
    # M 轮：m1_metrics 孤儿根因证据（M-3；before/after + 现场残留证据）
    "experiments/results/orphan_repro_20261017/README.md",
    "experiments/results/orphan_repro_20261017/SHA256SUMS",
    # N 轮（2026-10-17）：全功能 e2e 探针矩阵（三组探针 + 汇总报告；功能矩阵证据源）
    "experiments/results/e2e_probe_20261017/README.md",
    "experiments/results/e2e_probe_20261017/report.json",
    "experiments/results/e2e_probe_20261017/SHA256SUMS",
    "experiments/results/e2e_probe_workflow_20261017/README.md",
    "experiments/results/e2e_probe_workflow_20261017/report.json",
    "experiments/results/e2e_probe_workflow_20261017/SHA256SUMS",
    "experiments/results/e2e_probe_platform_20261017/README.md",
    "experiments/results/e2e_probe_platform_20261017/llm_report.json",
    "experiments/results/e2e_probe_platform_20261017/SHA256SUMS",
    # N 轮：oracle 接线 + 独立判读（N-3；口径变更与重放对账证据）
    "experiments/results/emse_oracle_independent_judging_20261017/README.md",
    "experiments/results/emse_oracle_independent_judging_20261017/ORACLE_INDEPENDENT_JUDGING_REPORT.json",
    "experiments/results/emse_oracle_independent_judging_20261017/SHA256SUMS",
    # N 轮：真实 LLM 重型功能探针（N-4；logic/RAG/跨文件/venv/预算/safe 路径证据）
    "experiments/results/e2e_llm_probes_20261017/README.md",
    "experiments/results/e2e_llm_probes_20261017/ITEM_RESULTS.json",
    "experiments/results/e2e_llm_probes_20261017/SHA256SUMS",
    # O 轮（2026-10-18）：oracle 仪器治疗（O-1；before/after + 生产独立判读验证）
    "experiments/results/emse_oracle_instrument_hardening_20261017/README.md",
    "experiments/results/emse_oracle_instrument_hardening_20261017/ORACLE_QUALITY_REPORT.json",
    "experiments/results/emse_oracle_instrument_hardening_20261017/SHA256SUMS",
    # O 轮：跨文件修复路径真实进入（O-3；8 节点 trace + 多文件回滚证据）
    "experiments/results/o_round_cross_file_20261017/README.md",
    "experiments/results/o_round_cross_file_20261017/O3_EVIDENCE.json",
    "experiments/results/o_round_cross_file_20261017/SHA256SUMS",
    # O 轮：oracle-enabled 二臂真实验证（O-2；同批 only-switch 差异 + 无 fp 分布）
    "experiments/results/emse_oracle_enabled_validation_20261017/README.md",
    "experiments/results/emse_oracle_enabled_validation_20261017/ARM_COMPARISON.json",
    "experiments/results/emse_oracle_enabled_validation_20261017/SHA256SUMS",
    # P 轮（2026-10-18）：规格可执行示例通道质量重放（P-1/P-1.1；raw + 表示归一双报告）
    "experiments/results/p_round_oracle_examples_20261018/README.md",
    "experiments/results/p_round_oracle_examples_20261018/ORACLE_EXAMPLES_REPORT.json",
    "experiments/results/p_round_oracle_examples_20261018/ORACLE_EXAMPLES_REPORT_norm.json",
    "experiments/results/p_round_oracle_examples_20261018/SHA256SUMS",
    # P 轮：A-19 停滞检测 wiring 修复 + B8 缩小消融（探索性，无触发场景如实披露）
    "experiments/results/p_round_b8_ablation_20261018/README.md",
    "experiments/results/p_round_b8_ablation_20261018/ABLATION_REPORT.json",
    "experiments/results/p_round_b8_ablation_20261018/SHA256SUMS",
    # Q 轮（2026-10-18）：示例通道生产化预注册 A/B（含事故披露件）
    "experiments/results/q_round_examples_ab_20261018/README.md",
    "experiments/results/q_round_examples_ab_20261018/ANALYSIS_REPORT.json",
    "experiments/results/q_round_examples_ab_20261018/SHA256SUMS",
    "experiments/results/q_round_examples_ab_20261018/_incident_unintended_llm_launch_20261018/README_INCIDENT.md",
    # Q 轮：批后处理墙钟可观测模块（smoke + 说明）
    "experiments/results/q_round_postprocess_wall_20261018/README.md",
    "experiments/results/q_round_postprocess_wall_20261018/SHA256SUMS",
    # R 轮（2026-10-18）：Q-2 检出损失诊断 + seed-43 复现批
    "experiments/results/r_round_examples_repro_20261018/README.md",
    "experiments/results/r_round_examples_repro_20261018/DIAGNOSIS.md",
    "experiments/results/r_round_examples_repro_20261018/PREREG_REPRO.md",
    "experiments/results/r_round_examples_repro_20261018/SHA256SUMS",
    # R 轮：示例自校验过滤器离线评估
    "experiments/results/r_round_examples_selfcheck_20261018/README.md",
    "experiments/results/r_round_examples_selfcheck_20261018/FILTER_STATS.json",
    "experiments/results/r_round_examples_selfcheck_20261018/ORACLE_EXAMPLES_REPORT_selfcheck.json",
    "experiments/results/r_round_examples_selfcheck_20261018/SHA256SUMS",
    # S 轮（2026-10-18）：seed-44 复现批 + 3-seed 生产化决策
    "experiments/results/s_round_examples_decision_20261018/README.md",
    "experiments/results/s_round_examples_decision_20261018/PREREG_DECISION.md",
    "experiments/results/s_round_examples_decision_20261018/ANALYSIS_REPORT.json",
    "experiments/results/s_round_examples_decision_20261018/SHA256SUMS",
    # S 轮：B8/A-19 失败注入重做
    "experiments/results/s_round_b8_injection_20261018/README.md",
    "experiments/results/s_round_b8_injection_20261018/PREREG.md",
    "experiments/results/s_round_b8_injection_20261018/REPORT.json",
    "experiments/results/s_round_b8_injection_20261018/ISOLATION.json",
    "experiments/results/s_round_b8_injection_20261018/SHA256SUMS",
    # S 轮：多采样示例自一致性评估
    "experiments/results/s_round_examples_multisample_20261018/README.md",
    "experiments/results/s_round_examples_multisample_20261018/PREREG.md",
    "experiments/results/s_round_examples_multisample_20261018/MULTISAMPLE_STATS.json",
    "experiments/results/s_round_examples_multisample_20261018/SHA256SUMS",
    # T 轮（2026-10-18）：真实 LLM 配额解锁后的可引用证据链——
    # ① K=3 示例治理（判定 high_risk_default_off）；② SMT 见证 pre/post-fix 并列；
    # ③ 语义修复汇总 + A-19 默认门复验（classification=unexpected_delta）；
    # ④ 文档↔工件审计报告；⑤ B1/B2 复现批（见各目录）。全部 SHA256SUMS verify 通过。
    "experiments/results/t_round_oracle_k3_20261018/PREREG.md",
    "experiments/results/t_round_oracle_k3_20261018/ANALYSIS_REPORT.json",
    "experiments/results/t_round_oracle_k3_20261018/README.md",
    "experiments/results/t_round_oracle_k3_20261018/SHA256SUMS",
    "experiments/results/t_round_smt_witness_20261018/PREREG.md",
    "experiments/results/t_round_smt_witness_20261018/ANALYSIS_REPORT.json",
    "experiments/results/t_round_smt_witness_20261018/README.md",
    "experiments/results/t_round_smt_witness_20261018/SHA256SUMS",
    "experiments/results/t_round_smt_witness_aliasfix_20261018/PREREG_ALIASFIX.md",
    "experiments/results/t_round_smt_witness_aliasfix_20261018/COMPARISON.json",
    "experiments/results/t_round_smt_witness_aliasfix_20261018/ANALYSIS_REPORT.json",
    "experiments/results/t_round_smt_witness_aliasfix_20261018/README.md",
    "experiments/results/t_round_smt_witness_aliasfix_20261018/SHA256SUMS",
    "experiments/results/t_round_semantic_fixes_20261018/README.md",
    "experiments/results/t_round_semantic_fixes_20261018/A19_REVALIDATION_PREREG.md",
    "experiments/results/t_round_semantic_fixes_20261018/D3B_DESIGN_AND_PREREG_DRAFT.md",
    "experiments/results/t_round_semantic_fixes_20261018/SHA256SUMS",
    "experiments/results/t_round_a19_default_gate_20261018/PREREG.md",
    "experiments/results/t_round_a19_default_gate_20261018/ANALYSIS.json",
    "experiments/results/t_round_a19_default_gate_20261018/ISOLATION.json",
    "experiments/results/t_round_a19_default_gate_20261018/README.md",
    "experiments/results/t_round_a19_default_gate_20261018/SHA256SUMS",
    "experiments/results/t_round_artifact_audit_20261018/AUDIT_REPORT.md",
    "experiments/results/t_round_artifact_audit_20261018/SHA256SUMS",
    "experiments/results/t_round_verify_20261018/VERIFY_REPORT.md",
    "experiments/results/t_round_verify_20261018/SHA256SUMS",
    "experiments/results/e2e_probe_t_round_20261018/README.md",
    "experiments/results/e2e_probe_t_round_20261018/SHA256SUMS",
    "experiments/results/t_round_b1_protocol_text_20261018/PREREG.md",
    "experiments/results/t_round_b1_protocol_text_20261018/PREREG_CONTINUATION.md",
    "experiments/results/t_round_b1_protocol_text_20261018/GATES.json",
    "experiments/results/t_round_b1_protocol_text_20261018/ANALYSIS_REPORT.json",
    "experiments/results/t_round_b1_protocol_text_20261018/README.md",
    "experiments/results/t_round_b1_protocol_text_20261018/DOC_RECONCILIATION.md",
    "experiments/results/t_round_b1_protocol_text_20261018/SHA256SUMS",
    "experiments/results/t_round_b2_main_batch_20261018/PREREG.md",
    "experiments/results/t_round_b2_main_batch_20261018/PREFLIGHT.json",
    "experiments/results/t_round_b2_main_batch_20261018/PREREG_AMENDMENT_cost_estimate.md",
    "experiments/results/t_round_b2_main_batch_20261018/GATES.json",
    "experiments/results/t_round_b2_main_batch_20261018/ANALYSIS_REPORT.json",
    "experiments/results/t_round_b2_main_batch_20261018/README.md",
    "experiments/results/t_round_b2_main_batch_20261018/SHA256SUMS",
    "experiments/results/t_round_final_checks_20261018/README.md",
    "experiments/results/t_round_final_checks_20261018/GATES.md",
    "experiments/results/t_round_final_checks_20261018/SHA256SUMS",
    "experiments/results/t_round_final_checks_20261018/full_suite_cov.log",
)

# 证据目录覆盖扫描的显式豁免登记（相对 experiments/results/）。
# 口径：冒烟批次 / 被更新批次取代 / 结论性数字经聚合报告入库的原始数据，
# 按项目"本地件"惯例保留工作树——但必须**显式登记理由**，禁止静默缺席
# （独立评审 A-04： silent gap 曾使四批旗舰工件脱离 git 而无人察觉）。
# T 轮（2026-10-18）扩展：扫描面从 emse_* 扩到所有轮次证据目录
# （`*_round_*`，如 q_round_/r_round_/s_round_/t_round_）——历史教训是
# "每次新轮次命名一种前缀，硬编码清单就再漏一次"。
EVIDENCE_DIR_EXEMPTIONS: dict[str, str] = {
    "emse_d2_profile_smoke_20261013": "D2 profile 冒烟；结论性数字经 df_spec/主批次聚合报告入库",
    "emse_d3_ult_20261013": "D3 cosmic-ray 冒烟；正式 Mut@k 见 emse_ult_mutk_full_20261015（已入库）",
    "emse_dsl_diag_20261014": "DSL diag v1 初版；被 emse_dsl_diag3_20261015（已入库）取代",
    "emse_jsonmode_smoke_20261013": "JSON mode 冒烟",
    "emse_jsonmode_smoke_20261014": "JSON mode 冒烟",
    "emse_jsonmode_smoke_v2_20261014": "JSON mode 冒烟（被 v4 已入库版取代）",
    "emse_jsonmode_smoke_v3_20261014": "JSON mode 冒烟（被 v4 已入库版取代）",
    "emse_quixbugs_mutk_20261014": "Mut@k 截断面初版；被 emse_quixbugs_mutk_full_20261015（已入库）取代",
    "emse_spec_ir_qb_smoke_20261013": "SpecIR QuixBugs 冒烟",
    "emse_spec_ir_quixbugs_20261013": "SpecIR QuixBugs 初版；正式见 spec_replace_ab_scale87 链（已入库）",
    "emse_spec_ir_quixbugs_smoke_20261013": "SpecIR QuixBugs 冒烟",
    "emse_specexpr_smoke_20261014": "SpecExpr 冒烟；确认性正式批见 emse_specexpr_synth_20261014（已入库）",
    "emse_stats_2026-10-15": "统计报告初版；被 emse_stats_extensions_20261016（已入库）取代",
    "emse_t08_gates_seed43_v2_20261013": "T-08 seed43 重跑中间态；定稿见 seed43 主目录（已入库）",
    "emse_t11_spec_compile_20261013": "T-11 spec 编译率冒烟；正式校准见 emse_calib_*（已入库）",
    "emse_ult_dfsmoke_20261017": "ULT df 冒烟；正式 200 任务批见 emse_ult_df200_20261017（已入库）",
}

# 向后兼容别名（T 轮前仅扫 emse_*；既有测试/调用方仍可用旧名）。
STUDY_DIR_EXEMPTIONS = EVIDENCE_DIR_EXEMPTIONS

# 证据目录扫描面（experiments/results/ 下按 glob 匹配；新增轮次前缀须在此登记，
# 否则下一轮证据目录又成静默缺口——T 轮把"新增前缀登记"本身变成必须动作）。
EVIDENCE_DIR_GLOBS: tuple[str, ...] = ("emse_*", "*_round_*")


def _is_tracked(path: Path) -> tuple[bool, str]:
    """返回 (是否被 git 跟踪, 状态说明)。缺失 / 未跟踪 / 被忽略分别可辨。"""
    if not path.exists():
        return False, "文件不存在（路径拼写错误或未生成）"
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    ls = subprocess.run(["git", "ls-files", "--", rel], cwd=PROJECT_ROOT, capture_output=True, text=True)
    if ls.returncode != 0:
        return False, f"git ls-files 失败: {ls.stderr.strip()}"
    if ls.stdout.strip():
        return True, ""
    check_ignore = subprocess.run(["git", "check-ignore", "-q", rel], cwd=PROJECT_ROOT, capture_output=True, text=True)
    if check_ignore.returncode == 0:
        return False, "被 .gitignore 忽略（永远无法入库——先修白名单）"
    return False, "存在于工作区但未被 git 跟踪（git add 后提交）"


def _scan_evidence_dirs() -> list[tuple[str, str]]:
    """覆盖扫描：`experiments/results/` 下轮次证据目录必须入库或显式豁免。

    扫描面 = `EVIDENCE_DIR_GLOBS`（`emse_*` 与 `*_round_*`）。防"新结果目录
    静默缺席"复发（独立评审 A-04：四批旗舰工件曾 0 跟踪而无任何门禁察觉——
    MANIFEST 是硬编码白名单，天然不覆盖未来目录；T 轮进一步发现单靠
    `emse_*` 前缀也会漏掉 `q/r/s/t_round_*` 新命名）。

    口径：目录内**至少一个**文件被 git 跟踪即通过（可再生物/日志/缓存不入库
    是项目既有惯例）；整目录 0 跟踪才报错并要求 add -f 或登记豁免。
    """
    offenders: list[tuple[str, str]] = []
    results_root = PROJECT_ROOT / "experiments/results"
    if not results_root.is_dir():
        return offenders
    seen: set[str] = set()
    for pattern in EVIDENCE_DIR_GLOBS:
        for child in sorted(results_root.glob(pattern)):
            if not child.is_dir():
                continue
            rel = child.relative_to(PROJECT_ROOT).as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            name = child.name
            if name in EVIDENCE_DIR_EXEMPTIONS:
                continue
            ls = subprocess.run(["git", "ls-files", "--", rel], cwd=PROJECT_ROOT, capture_output=True, text=True)
            if ls.returncode != 0:
                offenders.append((rel, f"git ls-files 失败: {ls.stderr.strip()}"))
                continue
            if not ls.stdout.strip():
                offenders.append(
                    (
                        rel,
                        "整个目录 0 git 跟踪。若为证据性批次：git add -f 后提交；"
                        "若为冒烟/被取代批次：在 EVIDENCE_DIR_EXEMPTIONS 显式登记理由",
                    )
                )
    return offenders


def _scan_emse_dirs() -> list[tuple[str, str]]:
    """向后兼容别名：等价于 `_scan_evidence_dirs()`（仅 emse_* 时代的历史名）。"""
    return _scan_evidence_dirs()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="主批次工件 git 入库守卫（AK3）")
    parser.add_argument("--list", action="store_true", help="仅打印清单后退出")
    args = parser.parse_args(argv)

    if args.list:
        for rel in MANIFEST:
            print(rel)
        return 0

    offenders: list[tuple[str, str]] = []
    for rel in MANIFEST:
        tracked, reason = _is_tracked(PROJECT_ROOT / rel)
        if not tracked:
            offenders.append((rel, reason))

    evidence_offenders = _scan_evidence_dirs()
    offenders.extend(evidence_offenders)

    if offenders:
        print(f"✗ {len(offenders)} 个关键工件/目录未入库（引用链断裂，CI 阻断）：")
        for rel, reason in offenders:
            print(f"  - {rel}: {reason}")
        print("修复：git add <路径> 并随本批提交（预注册时间顺序审计的前提）。")
        return 1
    print(
        f"✓ {len(MANIFEST)}/{len(MANIFEST)} 关键工件均已入库；"
        f"证据目录覆盖扫描通过（{'/'.join(EVIDENCE_DIR_GLOBS)}，引用链完整）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
