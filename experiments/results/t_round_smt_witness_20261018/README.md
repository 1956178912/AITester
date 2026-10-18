# T3b：z3 SMT 见证层最小启用批次（A-18 / Q7，零 LLM）

> 单臂观测批（无对照臂）· 主判定集 QuixBugs 41 缺陷程序（与 df_spec 同集）·
> 零 LLM（0 次 LLM 调用、0 USD、不联网）· 预注册 `PREREG.md` 跑前冻结。

## 0. 机制层判定

- **判定：`pass`** —— 见证率 > 0 且超时率有界且逐子句可复算（层在工作）
- `smt_witness_rate` 全任务均值 = **0.088531**（阈值 > 0，满足）
- `smt_timeout_rate`（pooled timeout/reached）= **0.0**（阈值 < 20%，满足）
- 每个 status 桶可逐子句复算：**是**（PER_CLAUSE 行重聚合 == 任务行 == 池化桶计数）
- **机制证据**：到达求解器的子句 n=19，其中 sat=19 / unsat=0 / unknown=0 / timeout=0；到达率（reached/D1）=0.103261；有见证任务 13/41（其余任务见证率为 0，主因材料未达求解器）
- 均值口径说明：均值由 13/41 有见证任务贡献，28/41 任务见证率为 0（材料未达求解器为主因）

## 1. 材料覆盖

- 锚表内容寻址命中：**50/50** 任务（sha256(buggy_source.strip())；锚表 sha256=`3e90b2ad5ed365ad…`，加载时按 SHA256SUMS 校验）
- 主判定集（41）有材料任务 **41**；剔除缺口任务：0
- 缺口任务不补跑（零 LLM 纪律），逐子句/任务级均不进入主判定均值。

## 2. 逐 status 桶计数（主判定集 41）

| smt_status | 子句数 | 说明 |
|---|---:|---|
| sat | 19 | 求解器给出可满足模型（前件见证 / 后件自洽） |
| unsat | 0 | 求解器给出不可满足（前件空洞 / 后件自相矛盾） |
| unknown | 0 | 求解器未知且未达超时阈值（保守记录，不计 unsat） |
| timeout | 0 | 墙钟 ≥ 0.9×5s，计超时，**不计 unsat** |
| error | 165 | 未达求解器（保守拒绝）或求解器异常（见 error_kind 分解） |
| **合计** | **184** | 主判定集非空评估子句（D1） |

- 全 50 任务扩展口径（含 9 个 `*_test` 驱动；不参与判定）池化桶：sat=19 / unsat=0 / unknown=0 / timeout=0 / error=185
- 通道 `expr`：sat=19 / unsat=0 / unknown=0 / timeout=0 / error=166
- 通道 `nl`：sat=0 / unsat=0 / unknown=0 / timeout=0 / error=19
- **到达求解器子句**（reached）的结果分解：sat=19 / unsat=0 / unknown=0 / timeout=0（n=19）
- `error`（未达求解器）逐子句归因（启发式文本特征，逐子句可复算）：

| 通道 | 归因原因 | 子句数 |
|---|---|---:|
| expr | other_not_reached | 5 |
| expr | result_alias_not_reached | 110 |
| expr | untranslatable_call | 51 |
| nl | other_not_reached | 15 |
| nl | untranslatable_call | 4 |

归因规则：启发式文本归因（仅 error/not_reached 行）：result 别名 → 白名单调用不可翻译 → 下标 → 属性 → 其他。

## 3. 任务级率分布（主判定集 41）

| 指标 | 值 |
|---|---:|
| witness_rate 均值 | 0.088531 |
| witness_rate 中位数 | 0.0 |
| witness_rate 最小 / 最大 | 0.0 / 0.5 |
| reach_rate（reached/D1，pooled） | 0.103261 |
| timeout_rate（timeout/reached，pooled） | 0.0 |
| timeout_share_nonempty（timeout/D1，pooled） | 0.0 |

`witness_rate` 分布（逐任务，升序）：

```
0.2, 0.0, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.5, 0.428571, 0.0, 0.166667, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.166667, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 0.0, 0.0, 0.142857, 0.4, 0.125, 0.4, 0.0, 0.2
```

## 4. 关联层（探索性，非确认性）

- 状态：`exploratory`；分桶规则：`median_split_on_smt_witness_rate`；n=41；MDE≈16.57pp（来源 `emse_df_spec_20261016/DF_SPEC_REPORT.json::contrast_41.mde_pp`）
- **无对照**：两桶任一为空（分桶退化），无对照，不做 detection 比较（median=0.0；≥median 桶 n=41，<median 桶 n=0）
- 退化原因（结构性事实）：41 个任务中 28 个 `smt_witness_rate=0`、13 个 >0，中位数=0，按预注册的 `≥median vs <median` 规则低桶为空 → 冻结规则下**不做 detection 比较**（防事后换分桶口径）。df_spec detection 已与 SMT 字段同行落盘于 `TASK_LEVEL.json`（`dfspec_detection_rate`），若后续要做「有见证 vs 无见证」分组，须**另行预注册**后跑新批次，不得回读本批做确认性推断。
- **措辞纪律**：差异 < MDE 只作方向性描述；禁止「提升/显著/证明」措辞；不做 p 值/检验；不引为确认性结论；不服务「规格锚增益」主张。

## 5. 逐子句审计样例（绑定具体子句，UNSAT 解释不脱离子句）

| task_id | status | channel_field | clause_sha256_16 | 子句 | 求解 ms |
|---|---|---|---|---|---:|
| quixbugs__bitcount | sat | preconditions_expr | `c452007488ce5f2e` | `n >= 0` | 20.491 |
| quixbugs__bitcount | error | preconditions_expr | `620df5e5e6244ebc` | `isinstance(n, int)` | 0.077 |
| quixbugs__gcd | sat | invariants_expr | `0e9d5bf7f1d8df70` | `b == 0 or a % b >= 0` | 2.164 |
| quixbugs__bitcount | error | postconditions_expr | `2fe2294d1b290f16` | `result >= 0` | 0.028 |
| quixbugs__breadth_first_search | error | preconditions_expr | `c84f521f9947f087` | `startnode is not None` | 0.051 |

- 出现 status：['error', 'sat']；**未出现 status**：['unsat', 'unknown', 'timeout']（本批该类子句为 0 条，如实标注、不构造样例）。
- `error/not_reached` 行的归因优先展示 `result` 别名与不可翻译调用两类（本批误差主因），逐子句 sha256 可在 `PER_CLAUSE.jsonl` 全量复算。

## 6. 成本与算力

- LLM 调用：**0** 次（配额 0；预算 0 USD）；网络调用：0
- z3 求解累计墙钟：57.354 ms；批次总墙钟：0.18 s
- 环境：Python 3.14.6 / z3 5.1.0 / 平台 macOS-27.0.1-arm64-arm-64bit-Mach-O

## 7. 确定性 / 幂等

- 进程内**两次独立求解**（第二次完整重建）的 status/分类/计数/率字段一致：`True`（mismatch=[]；比较范围：剔除计时键后的任务行/聚合行规范化 JSON（两次独立求解））
- 计时键 `smt_solve_ms, smt_solve_ms_total, solve_ms_total, solver_cpu_ms_total, wall_clock_seconds` 本质非确定，允许运行间波动，不纳入逐字节幂等声明；`PREFLIGHT.json` / `RUN_SUMMARY.log` 另含墙钟字段。
- z3 未设置随机参数；本批为整数/布尔约束，同一输入返回同一 status 已由上条双求解验证。

## 8. 限制（必须与结论同读）

1. **生产通道差**：生产 `spec_smt._collect_pre_constraints` 消费 `spec['preconditions']`（NL 通道），本批主材为 `*_expr` 形式化通道（以单子句 spec 喂入同一公开入口）。本批测的是「形式化子句有界可解性」，**不测**生产从 NL 通道到求解器的实际到达率。
2. **结果变量别名口径**：锚材料形式化后件统一写 `result`，而 `check_postcondition_consistency` 的自由结果变量域为 `r`——含 `result` 的后件/不变量子句在排序推断阶段被保守拒绝（`error/not_reached`）。本批**不**做别名改写（保持 src 口径原样），故 post/inv 通道可解率结构性偏低。
3. 单臂观测、无对照臂：无法归因任何 detection 差异于 SMT 层；关联层分桶为探索性，n=41、可判定 35。
4. 每子句 5s 超时映射依赖公开 API 的 `unknown` + 墙钟 0.9×timeout 规则（公开 API 不暴露 z3 `reason_unknown`）；本批 timeout 桶实为 0，规则未被触发。
5. 锚材料为 Planner 缓存物化（零 LLM），其质量上限即既有缓存质量；不重跑 Planner、不做规格精化。

## 9. 复跑

```bash
.venv/bin/python -m experiments.smt_witness_batch
python scripts/gates/checksum_results.py --write --results-dir experiments/results/t_round_smt_witness_20261018
python scripts/gates/checksum_results.py --verify --results-dir experiments/results/t_round_smt_witness_20261018
```

## 10. 产物

- `PREREG.md`
- `PREFLIGHT.json`
- `PER_CLAUSE.jsonl`
- `TASK_LEVEL.json`
- `ANALYSIS_REPORT.json`
- `README.md`
- `RUN_SUMMARY.log`
- `SHA256SUMS`

