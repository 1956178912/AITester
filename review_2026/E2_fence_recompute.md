# E2 / P0-2 围栏回灌重算报告（`patch` 字段口径修正，只读）

生成时间：2026-10-10T09:05:29+00:00　生成工具：`scripts/tools/refresh_patch_field.py`（零 LLM，只读）

## 0. 结论摘要（与 ADR-0021 声称数字对账）

- **围栏行数**：16 个入库批次（main_batch 10 + r4_batches 6）带补丁行 **476** 行，其中围栏形态 **476** 行（`python\n` 前缀 322 + markdown 围栏 154），**清理后与原文不同 476 行（100.0%）**——ADR-0021 的 **274/274** 恰为其中 main_batch 部分。
- 全三组（含 e6_a1_batches）带补丁行 **862** 行，围栏 **862/862**（`python\n` 708 + markdown 154），清理后**全部**变化，**wellformed 862/862**（`ast.parse` 全通过，0 语法错误）。
- **plausible → wellformed 变化**：入库 16 批 `patch_written`（原 `patch_plausible`）**213** → 重算 `patch_wellformed` **476**（+263 行 = 未落盘但文本合法的补丁；wellformed 覆盖带补丁行 100.0%）；全三组 **460 → 862**（+402）。
- **矛盾行（written=0 但 correct=1）**：全三组 **88** 行（入库 16 批 13 行）；其中 QuixBugs FIXED 批（`e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json`）实测 **13 行**（与 task-6 背景一致）——这些补丁文本经 gold 裁决**可用**，却因写盘层拒绝未落盘。
- 比率 `correct/wellformed`：入库 16 批 5.0%；全三组 33.3%。对照 `correct/written`（原 `patch_plausible` 分母）：入库 16 批 11.3%、全三组 62.4%——**>100% 即 written 口径漏计的量化证据**（correct 行数超过 written 行数，逐行 `patch_precision` 定义域不受影响，此处是聚合比率）。

## 1. 逐批重算表（口径见 §3）

| 批次 | 臂 | 行数 | 进入修复循环 | 有补丁文本 | 围栏(=清理后变化) | plausible(=written) | wellformed | correct | written=0 & correct=1 | correct/wellformed |
|---|---|---|---|---|---|---|---|---|---|---|
| `main_batch/benchmark_synthetic_20261001_112528.json` | aitester | 5 | 4 | 4 | 4 (= 4) | 3 | 4 | 0 | 0 | 0.0% |
| `main_batch/benchmark_synthetic_20261001_112801.json` | aitester | 5 | 4 | 4 | 4 (= 4) | 4 | 4 | 0 | 0 | 0.0% |
| `main_batch/benchmark_synthetic_20261001_121523.json` | aitester | 50 | 16 | 15 | 15 (= 15) | 15 | 15 | 0 | 0 | 0.0% |
| `main_batch/benchmark_synthetic_20261006_140906.json` | aitester | 87 | 58 | 54 | 54 (= 54) | 27 | 54 | 0 | 0 | 0.0% |
| `main_batch/benchmark_synthetic_20261006_151907.json` | aitester | 87 | 49 | 46 | 46 (= 46) | 25 | 46 | 0 | 0 | 0.0% |
| `main_batch/benchmark_synthetic_20261006_164357.json` | aitester | 87 | 47 | 45 | 45 (= 45) | 20 | 45 | 0 | 0 | 0.0% |
| `main_batch/benchmark_synthetic_20261007_161053.json` | aitester | 87 | 27 | 27 | 27 (= 27) | 14 | 27 | 0 | 0 | 0.0% |
| `main_batch/benchmark_synthetic_20261007_170147.json` | aitester | 87 | 26 | 26 | 26 (= 26) | 11 | 26 | 0 | 0 | 0.0% |
| `main_batch/benchmark_synthetic_20261007_181638.json` | aitester | 87 | 27 | 27 | 27 (= 27) | 14 | 27 | 0 | 0 | 0.0% |
| `main_batch/benchmark_synthetic_20261007_185941.json` | aitester | 87 | 26 | 26 | 26 (= 26) | 11 | 26 | 0 | 0 | 0.0% |
| `r4_batches/loc_test_quix/benchmark_quixbugs_20261007_195728.json` | aitester | 50 | 48 | 48 | 48 (= 48) | 15 | 48 | 0 | 0 | 0.0% |
| `r4_batches/r4_ab_arm_a/benchmark_synthetic_20261008_133303.json` | aitester | 50 | 18 | 18 | 18 (= 18) | 5 | 18 | 8 | 4 | 44.4% |
| `r4_batches/r4_ab_arm_b/benchmark_synthetic_20261008_134156.json` | aitester | 50 | 18 | 18 | 18 (= 18) | 4 | 18 | 8 | 5 | 44.4% |
| `r4_batches/r4_qb_arm_a/benchmark_quixbugs_20261008_165558.json` | aitester | 50 | 50 | 50 | 50 (= 50) | 20 | 50 | 0 | 0 | 0.0% |
| `r4_batches/r4_qb_arm_b/benchmark_quixbugs_20261008_165603.json` | aitester | 50 | 50 | 50 | 50 (= 50) | 20 | 50 | 0 | 0 | 0.0% |
| `r4_batches/r4_synth_arm_b2/benchmark_synthetic_20261008_161508.json` | aitester | 50 | 18 | 18 | 18 (= 18) | 5 | 18 | 8 | 4 | 44.4% |
| `e6_a1_batches/a1_strip_seed42/benchmark_synthetic_20261009_180655.json` | aitester | 87 | 34 | 34 | 34 (= 34) | 30 | 34 | 19 | 4 | 55.9% |
| `e6_a1_batches/ablation_r9/a1_strip_fixedharness.json` | aitester | 50 | 49 | 49 | 49 (= 49) | 25 | 49 | 35 | 12 | 71.4% |
| `e6_a1_batches/ablation_r9/over_red_section_firstrun_NOTVERIFIABLE.json` | aitester | 50 | 50 | 50 | 50 (= 50) | 25 | 50 | 37 | 13 | 74.0% |
| `e6_a1_batches/ablation_r9/over_red_section_verified.json` | aitester | 50 | 50 | 50 | 50 (= 50) | 25 | 50 | 37 | 13 | 74.0% |
| `e6_a1_batches/d1_json_repair_seed42/benchmark_synthetic_20261009_200343.json` | aitester | 87 | 29 | 29 | 29 (= 29) | 26 | 29 | 20 | 2 | 69.0% |
| `e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json` | aitester | 50 | 50 | 50 | 50 (= 50) | 26 | 50 | 37 | 13 | 74.0% |
| `e6_a1_batches/e4_quixbugs_FIXED_harness/diagnostic_12task_prerepair.json` | aitester | 12 | 12 | 12 | 12 (= 12) | 6 | 12 | 9 | 3 | 75.0% |
| `e6_a1_batches/e4_quixbugs_FIXED_harness/plain_llm_df.json` | aitester | 0 | 0 | 0 | 0 (= 0) | 0 | 0 | 0 | 0 | — |
| `e6_a1_batches/e4_quixbugs_aitester/benchmark_quixbugs_20261009_215514.json` | aitester | 50 | 49 | 49 | 49 (= 49) | 26 | 49 | 35 | 11 | 71.4% |
| `e6_a1_batches/e4_quixbugs_plain_llm_df/benchmark_quixbugs_20261009_223101.json` | aitester | 0 | 0 | 0 | 0 (= 0) | 0 | 0 | 0 | 0 | — |
| `e6_a1_batches/e6_control_seed42/benchmark_synthetic_20261009_181758.json` | aitester | 87 | 37 | 37 | 37 (= 37) | 34 | 37 | 19 | 2 | 51.4% |
| `e6_a1_batches/e6_phase1_standard_coldcache/benchmark_synthetic_20261009_190234.json` | aitester | 87 | 27 | 26 | 26 (= 26) | 24 | 26 | 15 | 2 | 57.7% |
| `e6_a1_batches/e6_phase2_matched_coldcache/benchmark_synthetic_20261009_191716.json` | aitester | 87 | 84 | 0 | 0 (= 0) | 0 | 0 | 0 | 0 | — |
| `e6_a1_batches/rt1_no_reinforcement_seed42/benchmark_synthetic_20261009_193509.json` | aitester | 0 | 0 | 0 | 0 (= 0) | 0 | 0 | 0 | 0 | — |
| **16 入库批次合计**（main_batch + r4_batches） | aitester | 969 | 486 | 476 | 476 (= 476) | 213 | 476 | 24 | 13 | 5.0% |
| **e6_a1_batches 合计**（审查批次） | aitester | 697 | 471 | 386 | 386 (= 386) | 247 | 386 | 263 | 75 | 68.1% |
| **全三组合计** | aitester | 1666 | 957 | 862 | 862 (= 862) | 460 | 862 | 287 | 88 | 33.3% |

注：以下文件在请求的臂（默认 `aitester`）下无结果行，已按 0 行列出（其臂集合见 JSON `arms_present`）：`e6_a1_batches/e4_quixbugs_FIXED_harness/plain_llm_df.json`、`e6_a1_batches/e4_quixbugs_plain_llm_df/benchmark_quixbugs_20261009_223101.json`、`e6_a1_batches/rt1_no_reinforcement_seed42/benchmark_synthetic_20261009_193509.json`

## 2. 漏斗（同一分母：进入修复循环）

漏斗分母 = 进入修复循环的行（§1 的"行数"列是全部行，两者不可混用）；同分母下各层占比列在括号内。

| 范围 | 进入修复循环 | 有补丁文本 | wellformed | written(原 plausible) | correct |
|---|---|---|---|---|---|
| **16 入库批次合计**（main_batch + r4_batches） | 486 (100%) | 476 (97.9%) | 476 (97.9%) | 213 (43.8%) | 24 (4.9%) |
| **e6_a1_batches 合计**（审查批次） | 471 (100%) | 386 (82.0%) | 386 (82.0%) | 247 (52.4%) | 263 (55.8%) |
| **全三组合计** | 957 (100%) | 862 (90.1%) | 862 (90.1%) | 460 (48.1%) | 287 (30.0%) |

## 3. 口径与字段语义

- `patch_written`：原 `patch_plausible` 原值（写盘成功；**未修改工件**，仅改名呈现）；
- `patch_wellformed`：`normalize_patch_text(patch)` 后非空 ∧ `ast.parse` 通过；
- `patch_precision_recomputed = patch_correct / patch_wellformed`（分母 0 → null）；
- 漏斗分母：进入修复循环 = `detection_first_status ∈ {red_then_green, red_not_repaired}`；该字段缺失的老批次（2026-10-01 三批）回退为 `iterations >= 1`（报告 JSON 的 `loop_rules` 标注每批所用口径）；
- `written=0 & correct=1`：写盘层拒绝但 gold 裁决通过的补丁——见 `review_2026/E2_patch_not_landed.md`（原因 100% 为证据门阻断）。

## 4. 工件完整性（SHA256SUMS 对账，证明未原地修改）

| 批次文件 | sha256(实测) | sha256(SHA256SUMS) | 匹配 |
|---|---|---|---|
| `main_batch/benchmark_synthetic_20261001_112528.json` | `6f468ee7539568cc…` | `6f468ee7539568cc` | ✅ |
| `main_batch/benchmark_synthetic_20261001_112801.json` | `5e9b4fd91821b633…` | `5e9b4fd91821b633` | ✅ |
| `main_batch/benchmark_synthetic_20261001_121523.json` | `043bd124273fd741…` | `043bd124273fd741` | ✅ |
| `main_batch/benchmark_synthetic_20261006_140906.json` | `6e31c07dd76ce7c3…` | `6e31c07dd76ce7c3` | ✅ |
| `main_batch/benchmark_synthetic_20261006_151907.json` | `bb5fcfc8afebeb5a…` | `bb5fcfc8afebeb5a` | ✅ |
| `main_batch/benchmark_synthetic_20261006_164357.json` | `be6a42e5597a449b…` | `be6a42e5597a449b` | ✅ |
| `main_batch/benchmark_synthetic_20261007_161053.json` | `ace15385f816fe0f…` | `ace15385f816fe0f` | ✅ |
| `main_batch/benchmark_synthetic_20261007_170147.json` | `7ade04206588c434…` | `7ade04206588c434` | ✅ |
| `main_batch/benchmark_synthetic_20261007_181638.json` | `a58320b04cdddd74…` | `a58320b04cdddd74` | ✅ |
| `main_batch/benchmark_synthetic_20261007_185941.json` | `e796bd549c80919d…` | `e796bd549c80919d` | ✅ |
| `r4_batches/loc_test_quix/benchmark_quixbugs_20261007_195728.json` | `4053be2af43eb9c3…` | `4053be2af43eb9c3` | ✅ |
| `r4_batches/r4_ab_arm_a/benchmark_synthetic_20261008_133303.json` | `6fe7e1617156991c…` | `6fe7e1617156991c` | ✅ |
| `r4_batches/r4_ab_arm_b/benchmark_synthetic_20261008_134156.json` | `a485fb39c93b4e06…` | `a485fb39c93b4e06` | ✅ |
| `r4_batches/r4_qb_arm_a/benchmark_quixbugs_20261008_165558.json` | `9df660030613341b…` | `9df660030613341b` | ✅ |
| `r4_batches/r4_qb_arm_b/benchmark_quixbugs_20261008_165603.json` | `fda65020e00b06c8…` | `fda65020e00b06c8` | ✅ |
| `r4_batches/r4_synth_arm_b2/benchmark_synthetic_20261008_161508.json` | `e5e5e3a6d21e0a09…` | `e5e5e3a6d21e0a09` | ✅ |
| `e6_a1_batches/a1_strip_seed42/benchmark_synthetic_20261009_180655.json` | `44b796e4a0dba5e5…` | `44b796e4a0dba5e5` | ✅ |
| `e6_a1_batches/ablation_r9/a1_strip_fixedharness.json` | `5f7682cbd8bd20a5…` | `5f7682cbd8bd20a5` | ✅ |
| `e6_a1_batches/ablation_r9/over_red_section_firstrun_NOTVERIFIABLE.json` | `492d549419095c80…` | `492d549419095c80` | ✅ |
| `e6_a1_batches/ablation_r9/over_red_section_verified.json` | `2fc71b7953b431b8…` | `2fc71b7953b431b8` | ✅ |
| `e6_a1_batches/d1_json_repair_seed42/benchmark_synthetic_20261009_200343.json` | `3b1247725a4a1fc2…` | `3b1247725a4a1fc2` | ✅ |
| `e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json` | `2cbf4009e427306b…` | `2cbf4009e427306b` | ✅ |
| `e6_a1_batches/e4_quixbugs_FIXED_harness/diagnostic_12task_prerepair.json` | `ec5cf84a9b99cf95…` | `ec5cf84a9b99cf95` | ✅ |
| `e6_a1_batches/e4_quixbugs_FIXED_harness/plain_llm_df.json` | `d23402fb03602e3b…` | `d23402fb03602e3b` | ✅ |
| `e6_a1_batches/e4_quixbugs_aitester/benchmark_quixbugs_20261009_215514.json` | `4617b8da43a4043d…` | `4617b8da43a4043d` | ✅ |
| `e6_a1_batches/e4_quixbugs_plain_llm_df/benchmark_quixbugs_20261009_223101.json` | `163ff01182846550…` | `163ff01182846550` | ✅ |
| `e6_a1_batches/e6_control_seed42/benchmark_synthetic_20261009_181758.json` | `7a9ccb11ed4797ac…` | `7a9ccb11ed4797ac` | ✅ |
| `e6_a1_batches/e6_phase1_standard_coldcache/benchmark_synthetic_20261009_190234.json` | `017df799fc47c99a…` | `017df799fc47c99a` | ✅ |
| `e6_a1_batches/e6_phase2_matched_coldcache/benchmark_synthetic_20261009_191716.json` | `c631595b86eb2627…` | `c631595b86eb2627` | ✅ |
| `e6_a1_batches/rt1_no_reinforcement_seed42/benchmark_synthetic_20261009_193509.json` | `85033785cf81b4fd…` | `85033785cf81b4fd` | ✅ |

## 5. 与既有口径的差异（诚实声明）

- ADR-0021 的 `274/274` 只覆盖 main_batch 10 批；本工具把同一口径推广到全部 16 入库批次 → **476/476**；再含 e6 审查批次 → **862/862**。
- 本工具**不重放 gold 测试**（不含修复裁决），`patch_correct` 直接取工件原值；重放口径见 `experiments/repair_replay.py`（ADR-0021）。

