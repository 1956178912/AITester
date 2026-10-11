# Lead 独立复核发现（原始记录，供最终报告引用）

复核对象：`experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json`
（2026-10-10 批次，QuixBugs 50 任务，logic 档，seed 42）
复核脚本：`.venv/bin/python` 只读解析 `results.aitester.details[]`（未调用 LLM）。

## F1 复现成功的口径（与 BASELINE.yaml 一致）

| 指标 | 复核值 | BASELINE 声明 | 结论 |
|---|---|---|---|
| detection | 17/37 = 45.9% | 17/37 = 45.9% | ✅ 一致（det_measured=37，13 行 None） |
| repair | 37/40 = 92.5% | 37/40 = 92.5% | ✅ 一致 |
| token/task | 16,038 | 16,038 | ✅ 一致 |
| coverage 均值 | 69.12% | 未在 BASELINE 登记 | ⚠️ 新数据点 |
| mutation_score 均值 | 0.721 | 未在 BASELINE 登记（合成集为 0.818–0.976） | ⚠️ 真实基准显著低于合成集 |
| spec_compile_rate 均值 | 0.4599 | 0.472–0.517（区间） | ⚠️ 略低于区间下界，口径需注明 |
| 对照臂 plain_llm_df | 31/37 = 83.8% | 31/37 = 83.8% | ✅ 一致 |

## F2 新发现 P0：`patch_plausible` 与 `patch_correct` 在同批工件内自相矛盾（13/50）

`experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json`：

```
(stop_reason, patch_plausible, patch_correct, patch_precision, has_patch) → n
('test_passed',                  1, 1, 1.0,  True) 13
('skip_debugger_repair_invalid', 0, 1, None, True) 13   ← 矛盾
('skip_debugger_repair_invalid', 0, 0, None, True) 11
('max_iterations',               1, 1, 1.0,  True) 11
('max_iterations',               1, 0, 0.0,  True)  2
```

- 不一致计数：`plausible=0` 而 `correct=1` = **13 行**；反向 2 行。
- **13 行全部落在 `stop_reason=skip_debugger_repair_invalid`**，且全部 `iterations=2`。

代码级定位：
- `patch_plausible` 定义在 `experiments/run_benchmark.py:601-617`：要求
  `final_state["repair_history"][-1]["patch_applied"] is True`；无 `repair_history` → 保守 0。
- `patch_correct` 定义在 `experiments/run_benchmark.py:620-634`：取
  `_m1_metrics._compute_repair_rate(task, final_state) == 1.0`（gold 独立裁决）。

**推论（待 T4 独立确认）**：`repair_history` 的写盘记录在
`skip_debugger_repair_invalid` 早退路径上未落盘 / 被覆盖，导致
`patch_plausible` 系统性低估；而 `REPAIR_CEILING` 漏斗
（`experiments/repair_ceiling_analysis.py:74,100,191`）以
`patch_plausible=1` 作为漏斗闸口 → **漏斗分母与 repair 主指标的分子不同源**，
"patch 产出 94.2% → plausible 46.8% → correct 39.31%"这一叙事链
在最关键的一段上可能由 `repair_history` 记账缺陷而非真实质量差异造成。

判定：**第五起疑似测量伪影（记账类）**，与 ADR-0021/0029 同类，但发生在
"plausible 闸口"而非"detection 判分树"。影响面：`patch_precision`（26 行非空
而非应有的 37+）、CPR/IDR 报表（`experiments/cpr_idr_report.py:118` 以
`patch_plausible != 1` 直接跳过行）、E7 分层抽样框
（`experiments/repair_sample_selection.py:57-62`）。

零 LLM 复现路径（无需跑批）：直接对上述 JSON 重算计数（本文件 F2 的表格即为复现输出）。

## F3 新发现 P1：修复循环在 48%（24/50）任务上被"连续修复无效"提前终止

- `stop_reason` 分布：`skip_debugger_repair_invalid` 24 / `test_passed` 13 / `max_iterations` 13。
- 24 行全部 `iterations=2`、全部 `passed=False`、20 行未检出。
- 其中 13 行最终仍被 gold 判定修复正确 —— 即**修复能力存在，但循环被路由层提前掐断**。
- 代码定位：`src/graph/workflow.py:727-734`（`_recent_repairs_invalid(state)` 触发
  在 `iteration < max_iterations` 时直接 done）。

这是 repair 天花板的一个**未被归因的损失通道**（BASELINE 与 repair_ceiling_report
把卡点归因为"生成侧合成质量"，而本批真实基准上 48% 任务根本没跑完修复循环）。

## F4 新发现 P1：`fl_at_k`（谱系定位）在真实基准上全线 0，与 LLM 定位强反差

同一批 50 任务：
- `localization_hit_function`（LLM 推理定位，元素级 Hit@1）= **29/50 = 58%**（13 行 None，8 行 False）
- `localization_hit_function_at_3` = **30/50 = 60%**；`localization_mrr` 均值 **0.797**（n=37）
- `fl_at_k`（Ochiai 谱系定位）样本 `{'fl_at_1': 0.0, 'fl_at_3': 0.0, 'fl_at_5': 0.0}` —— 全部 0

含义：项目自述的"FaultLocalizer 范式转向"（ADR-0017）在真实基准上**LLM 定位可用、
谱系通道无效**；而 ADR-0028 的 FL Top-k 约束门（补丁变更函数集合 ∩ 定位 Top-3）
依赖 `fl_at_k` 通道，在 QuixBugs 上等于恒空 → 该门在真实基准上**不可评估**。

## F5 观察：`edit_intent_status` 全为 None

50 行全 `None` → 该批未开 `EDIT_INTENT_ENABLE`（与"默认关"一致），但意味着
ADR-0018/0019 的确定性修复通道**在真实基准上没有对照数据**。

## F6 观察：oracle 单一化

`oracle_type` 全为 `generated_test`（50/50）——`spec_oracle_injected` 通道在
该批未产生任何一行，与 BASELINE `a2_logic_chain_reach` 自述
"真实 QuixBugs 注入 20/50 = 40%"不一致，需核对（可能是批次/开关差异）。

## F7 新发现 P0：SWE-bench（Lite/Pro）工件是"失败分支"行，不是有效基准结果

复核 `experiments/results/swe_bench_lite_20/benchmark_swe_bench_20260818_113525.json`
与 `experiments/results/g8_lite_retest{,2,3,4}/*.json`、`full_stack_swe_bench_pro_*`：

- 所有工件的结果行 **只有 9–19 个键**，`detection_rate` / `repair_rate` / `oracle_type` /
  `stop_reason` **全部缺失**；而正常批次行有 **65 个键**。
- 对应 `experiments/run_benchmark.py:1225-1244` 的**失败分支**行字典（无 `final_state`）。
- `task_metadata.instance_code` 长度 = **0**（20/20），`coverage` 全为 0.0。
- `error_category`：syntax 19 / timeout 1（SWE-bench Lite 20 任务）；诊断文本如
  "被测代码中存在未闭合的字符串字面量" —— 说明**喂给系统的是占位/损坏文本**，
  不是真实仓库源码。
- `provenance` = `{}`（无模型/温度/种子/开关快照）。

结论：README 中"**SWE-bench Lite（sqlfluff-20）真实基准 0/20 负结果与统计检验
同样如实披露**"这句话把"评测无法执行（输入物化失败）"表述成了"负结果"。
两者证据强度完全不同：前者是**管道缺陷**，后者是**方法学发现**。
`docs/design/swe_bench_probe.md` 与 `real_benchmark_upgrade.md` 需要按此改写。

影响：项目**目前唯一有效的真实基准只有 QuixBugs（50 个玩具程序，41 个有 gold）**。
`full_stack`（SWE-bench Pro）n=2–5 的批次同样无 `detection_rate`，
"G8 full-stack" 类结论不可作为外部有效性证据。

## F8 观察：合成集的"模式重复"造成聚类效应（项目已部分自认）

主批次 `benchmark_synthetic_20261006_140906.json`（n=87）：
`task_metadata.pattern_name` 去重后只有 **29 个不同模板**，最高重复 8 次
（`import_chain_type_contract`）；`bug_type` = assertion 46 / runtime 41；
`difficulty` = 1:22 / 2:20 / 3:19 / 4:11 / 5:15。
项目已在 A1 分析里登记 `cluster_k=29 / ICC=0.671 / DEFF=4.356 / n_eff=39.9`，
方向正确；但 `BASELINE.yaml` 主表（detection 44.8% vs 15.8%）**未附 n_eff**，
对外引用存在把 n=261 当作独立样本量的风险。

## 待 T4 独立确认项

1. F2 的机制（`repair_history` 在哪个分支丢失写盘记录）。
2. 合成集主批次（n=261）是否同样存在 `plausible=0 & correct=1` 的不一致。
3. F6 的注入率差异。
