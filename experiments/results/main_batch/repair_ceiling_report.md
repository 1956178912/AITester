# R-P0-2 修复上限归因分析（AK1，2026-10-06）

数据来源（与 statistical_report_3seed_pooled.md 同参口径）：3 个批次
- benchmark_synthetic_20261006_164357.json
- benchmark_synthetic_20261006_151907.json
- benchmark_synthetic_20261006_140906.json

## 1. 修复通道漏斗（aitester 臂，多种子拼接）

| 漏斗层 | 行数 | 占比（分母=上行） |
|------|----|----|
| 总任务 | 261 | — |
| └ detection_first_status=red_not_repaired | 97 | 37.2% |
| └ detection_first_status=all_green_unverified | 86 | 33.0% |
| └ detection_first_status=red_then_green | 57 | 21.8% |
| └ detection_first_status=None | 21 | 8.0% |
| 修复循环进入（red 两桶合计） | 154 | 59.0% |
| patch 产出（patch 非空） | 145 | 94.2% |
| patch_plausible=1 | 72 | 46.8% |
| patch_correct=1（gold 裁决） | 0 | 0.0% |

## 2. repair=0 归因分布（修复循环行）

- patch_evidence_level：none: 74（48.1%），sbfl: 73（47.4%），keyword: 6（3.9%），None: 1（0.6%）
- stop_reason：skip_debugger_repair_invalid: 77（50.0%），test_passed: 57（37.0%），max_iterations: 20（13.0%）
- error_category：patch_validation_failed: 89（57.8%），test_regenerated_pass_unverified: 54（35.1%），assertion: 7（4.5%），type_error: 2（1.3%），runtime: 1（0.6%），timeout: 1（0.6%）
- fl_at_k 观测覆盖：0/154（R-P0-2 批 FL_SPECTRAL_ENABLE 未接线——AI 批次已补，E2 起产出）
- mutation_detection_rate 观测覆盖：39/154

## 3. 21 行 detection=None 敏感性双界（R12）

| 对比 | 情形 | 共同任务 | A 阳性 | B 阳性 | 配对差 | McNemar χ² | p |
|------|------|----|----|----|----|----|----|
| aitester vs plain_llm（None 21 行） | base | 240 | 38 | 4 | +0.142 | 27.23 | 1.8e-07 |
| aitester vs plain_llm（None 21 行） | worst(None→0) | 261 | 38 | 4 | +0.130 | 27.23 | 1.8e-07 |
| aitester vs plain_llm（None 21 行） | best(None→1) | 261 | 59 | 4 | +0.211 | 47.80 | 4.7e-12 |
| aitester vs plain_llm_df（None 21 行） | base | 240 | 38 | 117 | -0.329 | 48.79 | 2.8e-12 |
| aitester vs plain_llm_df（None 21 行） | worst(None→0) | 261 | 38 | 117 | -0.303 | 59.07 | 1.5e-14 |
| aitester vs plain_llm_df（None 21 行） | best(None→1) | 261 | 59 | 117 | -0.222 | 31.85 | 1.7e-08 |

## 4. iteration-to-stop 分布（aitester 臂，收敛性观测）

| 迭代数 | 任务数 |
|----|----|
| 0 | 107 |
| 1 | 42 |
| 2 | 90 |
| 3 | 22 |

## 5. 结论口径

- repair=0 的漏斗分解见 §1/§2：上限层（patch_correct）之前的各层
  行数即 E7 实验设计的分层抽样框；观测覆盖为 0 的指标（fl_at_k、
  mutation）属批内口径缺口而非真实为 0，不得按 0 解读。
- §3 双界若与原口径同号且均显著，则 pooled 报告两定性结论
  （+14pp 正向 / −28pp 负向）对差异性缺失稳健，勘误节引用本表。
- 本报告纯离线生成（零 LLM 成本），随批次工件入 SHA256SUMS。
