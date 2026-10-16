# 规格锚表（df_spec 臂预计算材料，A-10，2026-10-16）

> **性质**：`plain_llm_df_spec` 臂（独立评审 A-10 / P1 超越路径核心对照臂）
> 的**运行时输入工件**。由 `experiments/build_spec_anchor_table.py` 从既有
> Planner LLM 缓存零 LLM 物化——臂运行时按 `target_code` 内容哈希查表，
> 命中即把 Generator prompt 的"目标代码"块替换为规格锚文档
> （`src/tools/spec_first.build_spec_replace_section` 渲染，与 aitester
> replace 臂同一路径）。

## 1. 内容与口径

| 项 | 值 |
|---|---|
| 键 | `sha256(源码.strip())`（内容寻址；臂侧同口径） |
| 值 | `{function_name, logic_analysis, source_head, source_len, chosen_from, n_candidates, timestamp}` |
| 构建命令 | `.venv/bin/python -m experiments.build_spec_anchor_table` |
| 构建时间 | 2026-10-16 |
| 缓存扫描 | 6754 文件 / Planner 条目 1534 |
| 响应解析 | JSON 1000 / Python 字面量 `ast.literal_eval` 回退 9 / 失败 525（旧批次截断/混语法响应，如实弃用） |
| 表规模 | **416 条锚**（弃用：无源码块 0 / 缺函数名 0 / 渲染为空 0） |
| 确定性 | 重跑逐位一致（SHA256SUMS 锁定） |

**选择纪律**（同源码多候选时）：含 `*_expr` 形式化子句者优先 →
`timestamp` 大者优先 → 文件名小者优先（确定性 tie-break）。
**可用性判据与臂侧运行口径同一函数**（真实渲染 `build_spec_replace_section`
非空才入表，防"表里有、跑起来空"的分裂）。

## 2. 覆盖测量（2026-10-16，锚表落盘当日实测）

| 数据集 | 覆盖 | 说明 |
|---|---|---|
| **QuixBugs（50 程序）** | **50/50（100%）** | P1 主证据数据集：全量可用 |
| ULT 全量本地切片（200） | 59/200（29.5%） | 历史 Planner 运行仅覆盖部分任务（旧批次响应截断/JSON 模式前） |
| synthetic seed=42（87） | 6/87（6.9%） | **合成发生器漂移**（已知缺口②）：历史缓存的 noise_seed/模板与当前生成器版本不一致；逐实例 `# noise_seed` 噪声行使内容寻址拒绝跨版本匹配（有意不剥离——剥离会撞毁不同实例） |

**解释纪律**：分析 df_spec 臂结果时，必须以 `details[].spec_replace_applied`
（`attempted_replaced` / `attempted_fallback`）过滤命中子集；**锚覆盖率是
一等报告数**，与表版本（本目录 SHA256SUMS）成套引用。

## 3. 复现

```bash
# 零 LLM 重建（从本机 Planner 缓存；缓存内容不同的机器将得到不同覆盖）
.venv/bin/python -m experiments.build_spec_anchor_table
# 逐位校验
python scripts/gates/checksum_results.py --results-dir experiments/results/emse_spec_anchor_20261016 --verify
```

臂侧运行：`--baselines plain_llm_df_spec`（显式指定；env `DF_SPEC_ANCHOR_TABLE`
可覆盖表路径，已入批次 env 快照）。

## 4. 已知边界

- 525 条历史响应不可解析（LLM_JSON_MODE 默认开启前的截断/混语法家族）——
  不可廉价修复，已如实计数；如需提升 ULT/synthetic 覆盖，需在**当前生成器
  版本**上补跑 Planner（LLM 成本）后重建。
- 锚材料为 Planner 计划的 `{function_name, logic_analysis}` 子集，不含
  `test_cases`（生成纪律：期望值只从规约导出，防 oracle-from-implementation
  经计划泄漏）。
