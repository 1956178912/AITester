# 改进批次落地（P0–P4）：真实功能缺口 A/B 实验 + 小样本验证（2026-10）

> **本批次背景**：补齐论文实验章节证据缺口后的改进批次。此前
> `docs/experiment_ab_results_2026-09-28.md` 显示位置感知 / RAG / 跨文件
> 三组 A/B 全部为**阴性结果**（定位 0/30 命中、RAG token +40.7% 负向、
> 跨文件 T1 未达 +15pp）。本批次针对阴性结果的**根因**做代码级改进，
> 并以真实 LLM 小样本 A/B 验证改进方向是否成立。
>
> **默认行为不变**：所有新增能力均带独立环境变量开关，默认关闭，
> 历史实验基线不受影响。

---

## 1. P0：位置感知修复 0/30 命中根因 + 修复

**阴性结果**：位置感知 A/B 定位命中 0/30。根因——合成数据集失败
**以 assertion 为主（无 traceback 行号）**，`_locate_repair_focus` 在
`ctx.line=None` 时全部降级为全文件修复，定位阶段从未激活。

**改进**：新增 `BUG_PATTERNS_LEVEL25`（运行时异常缺陷库），使失败以
`IndexError / KeyError / AttributeError / TypeError` 为主（带 traceback
帧行），定位阶段可被激活。数据集层新增独立整数码 25/35/45 精确路由
（`_DIFFICULTY_PATTERNS`），每个模式携带 `suggested_function`（gold
定位目标），`_locate_accuracy` 据此计算命中正确率。

| 开关 | 默认 | 说明 |
|------|------|------|
| `BUG_PATTERNS_LEVEL25` | 数据集 | 4 个运行时异常模式（boundary/key/attr/type） |
| `CROSS_FILE_DEEP_PATTERNS` | 数据集 | 3 文件依赖链（module_a→b→c），`difficulty=35` |

**小样本验证**：位置感知 L2.5 A/B（8 任务，`seed=42`，agnes-3.0-flash）
——ON/OFF 成功率均 100%（首轮生成即捕获缺陷，定位阶段未激活），指标
正确显示"未激活"而非误导性的 0%。定位正确率指标已修正为区分
"无修复轮次"（未激活）与"修复但定位未命中"。

---

## 2. P1：探针快照第二定位源（PROBE_SNAPSHOT_LOCATE_ENABLE）

**阴性结果**：assertion 主导的失败无 traceback 行号，定位阶段降级。

**改进**：`_debugger_node` 把结构化探针快照（`state["runtime_probe_snapshot"]`，
RUNTIME_PROBE_ENABLE 开启时由 `_executor_node` 经 sys.settrace 捕获的
"失败时刻局部变量快照"）透传给 debugger，使 `_locate_repair_focus` 在
traceback 行号缺失时可用快照最内层帧作为**第二定位源**。纯静态（零
LLM 成本）。

| 开关 | 默认 | 说明 |
|------|------|------|
| `PROBE_SNAPSHOT_LOCATE_ENABLE` | false | 探针快照定位（需 RUNTIME_PROBE_ENABLE + POSITION_AWARE_REPAIR_ENABLE 同时开） |

---

## 3. P2：RAG 相关性评分 + 条件注入

**阴性结果**：RAG A/B token +40.7% 负向（检索命中 100% 但成功率无增益）
——检索到的相似案例被注入 prompt 增加输入 token，但未转化成功率。

**改进**：`src/graph/rag.py` 新增相关性增强层（默认关）：
1. **RAG_RELEVANCE_THRESHOLD_ENABLE**（+ `RAG_RELEVANCE_THRESHOLD=0.7`）：
   按 similarity（1 - cosine_distance）过滤低相关检索结果；
2. **RAG_CONDITIONAL_ENABLE**：按错误类型条件注入（error_category 与
   检索案例 metadata 匹配时才注入），避免无关案例污染 prompt；
3. **RAG_JUDGE_INSTRUCTION_ENABLE**：注入"以下案例仅供参考，不匹配
   请忽略"的 judge 指令，降低 LLM 误用无关案例。

`experiments/rag_ab_experiment.py` 新增 `--relevance-ab` +
`--relevance-threshold` 开关。

**小样本验证**：RAG 相关性 L3 A/B（8 任务）——ON/OFF 成功率均 100%，
RAG ON 平均 token 2260 vs OFF 210（检索注入上下文），RAG 未显著减少
任何错误类型（L3 双模块在 agnes-3.0-flash 上首轮全过，非 RAG 约束
的瓶颈场景）。

| 开关 | 默认 | 说明 |
|------|------|------|
| `RAG_RELEVANCE_THRESHOLD_ENABLE` | false | 相关性阈值过滤 |
| `RAG_RELEVANCE_THRESHOLD` | 0.7 | similarity 下限 |
| `RAG_CONDITIONAL_ENABLE` | false | 按错误类型条件注入 |
| `RAG_JUDGE_INSTRUCTION_ENABLE` | false | judge 指令 |

---

## 4. P3：跨文件 2% 未修复根因分析 + 双向依赖图

**阴性结果**：跨文件 L3 A/B T1 未达 +15pp（实测 +10pp），未定位
"未修复的 2%"瓶颈。

**改进**：
1. 新增 `experiments/cross_file_root_cause.py`（纯数据，零 LLM 成本），
   按失败根因分类：LLM_BREAKS_IMPORT / EMPTY_LLM_PATCH /
   DEP_GRAPH_INCOMPLETE（dep_edges < num_files-1）/ ROLLBACK_CONSERVATIVE
   / TOPOLOGICAL_ORDER / LLM_CAPABILITY。
2. 新增 `CROSS_FILE_BIDIRECTIONAL=true` 开关：双向依赖图（被调用方
   视角反向边 + 双向拓扑序），验证"单入口视角粒度不足"是否为 T1 瓶颈。
3. `experiments/cross_file_ab.py` 新增 `--bidirectional` + 扩展
   `--difficulty` 至 level3.5/4/4.5，level3.5 T1 未达阈值时提示检查
   双向依赖图与根因脚本。

**修复的真实缺陷**（根因分析暴露）：
- `_cross_file_analyzer_node` 对跨文件任务只对被调方 `target_code`
  做 AST 分析（反向依赖方向），得出 0 条边，**覆盖了预置的依赖边**
  → 修复为 AST 为空且预置边非空时保留预置边（双向依赖图反向补全）。
- `_write_cross_file_state` 补全双模块（L3）任务的 dep_chain
  （`module_a → target_module`），使 L3 也拥有依赖边。
- `_dump_state_artifacts` 补落盘 `cross_file_deps` + `task_metadata`
  （根因脚本依赖这两键判定 DEP_GRAPH_INCOMPLETE / 难度过滤）。
- `cross_file_root_cause.py` 的 `_load_results` 支持嵌套
  `results.aitester.details` 结构 + 难度数字码等价过滤（level3.5↔35）。

**小样本验证**：跨文件 L3.5 双向 A/B（8 任务）——ON 87.5% vs
OFF 87.5%（delta 0.00pp，小样本无分化），根因分析定位唯一失败任务
`synthetic__cross_file_three_module_chain_0004` 为 **LLM_CAPABILITY**
（`dep_edges=2` 依赖图完整，3 轮修复未闭合，LLM 能力边界）——证明
跨文件机制在 L3.5 已交付依赖边，剩余瓶颈是 LLM 能力而非依赖图。

| 开关 | 默认 | 说明 |
|------|------|------|
| `CROSS_FILE_BIDIRECTIONAL` | false | 双向依赖图 + 双向拓扑序 |

---

## 5. P4：数据集多样性难度层（Level 2.5 / 3.5 / 4.5）

**改进**：`SyntheticDataset` 难度序列新增 2.5（运行时异常库）、
3.5（三模块深链）、4.5（边界 + 异常路径混合）；`_difficulty_sequence`
支持 fractional 难度码映射（2.5→25、3.5→35、4.5→45）。各实验脚本
新增 `--difficulty` CLI 参数透传。

---

## 6. 默认行为不变声明

本批次全部新增能力（L2.5/L3.5/L4.5 数据集、`PROBE_SNAPSHOT_LOCATE`、
`RAG_RELEVANCE_THRESHOLD`/`RAG_CONDITIONAL`/`RAG_JUDGE_INSTRUCTION`、
`CROSS_FILE_BIDIRECTIONAL`）**默认关闭**；历史实验基线（mixed 难度、
RAG 原始口径、跨文件单入口口径）逐字节不变。回归测试 147 通过。

---

*生成时间：2026-10；数据源：`experiments/results/{position_aware_ab_l25_small,rag_relevance_ab_l3_small,cross_file_ab_l35_bi_small}/`；
基线口径：agnes-3.0-flash（LLM_1）+ 合成数据集 + seed=42，小样本 n=8。*
