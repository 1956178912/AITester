# ADR-0032: M10 可观测性强化（叶子回退静默片段显式告警）

- **日期**：2026-10-14
- **状态**：已采纳（纯观测改进，默认全开，无开关——解析行为零变化）
- **关联模块**：`src/utils/helpers.py`、`src/agents/planner.py`、`tests/test_llm_oms_leaf_fallback.py`
- **关联 ADR**：ADR-0031（§已知局限②"叶子回退静默返回错误片段的分辨率问题"的落实）

## 背景

ADR-0031 §已知局限②登记了一个待落实的可观测性缺口：
`extract_json_object` 的**叶子降级档**（正则取最内层无嵌套 `{...}` 片段）
在括号平衡法 + 修复链均失败时会**静默返回一个错误片段**（如
`{'items': ...}`）。该片段缺失 `logic_analysis` 等关键字段时，下游
Planner M10 路径把"缺字段"归因为"LLM 未输出 logic_analysis"
（`M10：LLM 未输出 logic_analysis，已填充空值并标记 logic_degraded=True`），
实为**提取器缺陷**而非 LLM 缺陷——LLM 实际上输出了完整正确的 JSON，
只是解析链回退到了错误片段。

2026-10-14 日志审计（ADR-0031 批次）发现：此前 ~7-8% 的任务（6/75）
触发 M10 降级，其中**大部分**属于此"误诊"模式——"逻辑驱动"路径的
实际覆盖率比历史记录更高。但 M10 统计无法区分"LLM 真未输出"与
"提取器静默回退"，构成度量盲区。

## 决策

三项纯观测改进（**不改变任何解析行为与返回值**，历史口径零变化）：

1. **模块级哨兵**（`helpers._LEAF_FALLBACK_ACTIVE` +
   `was_leaf_fallback_used()`）：`extract_json_object` 的叶子档（最内层
   片段 / 次新候选 / 尾扫三档）命中时置 `True` + 记录
   `logger.warning`；**每次调用入口清零**（`global _LEAF_FALLBACK_ACTIVE
   = False`），保证哨兵只反映"最近一次调用"；raise 路径不复位
   （哨兵保持 False——全方案失败即无叶子回退）。调用方须在同一调用栈
   立即读取（线程无关：Python GIL 下 `extract_json_object` 为同步调用；
   跨线程/缓存回放路径不得依赖哨兵——历史缓存响应不经
   `extract_json_object`，哨兵恒 False）。

2. **Planner M10 归因改写**（`planner.py`）：`_extract_json(raw)` 后
   立即读取 `was_leaf_fallback_used()`；命中叶子回退且
   `logic_analysis` 缺失时，把 M10 日志归因从"LLM 未输出"改写为
   "提取器叶子回退误诊"，并在 `result` 中写入纯观测标记
   `m10_leaf_fallback=True`（供实验层把 M10 降级任务中"实为提取器缺陷"
   的子集从"LLM 未输出"中分离计数）。

3. **回归测试**（`tests/test_llm_oms_leaf_fallback.py`，6 例）：
   锁定哨兵在正常路径恒 False、叶子命中恒 True、全失败复位 False、
   纯观测（同输入修复前后逐字同结果）、日志 warning 触发。

## 后果

- **M10 误诊计数可分离**：`logic_degraded=True ∧ m10_leaf_fallback=True`
  的子集为"提取器叶子回退"（误诊来源）；`logic_degraded=True ∧
  m10_leaf_fallback=False` 为"LLM 真未输出"（真 M10）。EMSE 报告
  §6.10 可据此把 ~7-8% M10 率进一步分层为"LLM 缺字段" vs
  "解析层误诊"——前者是模型能力信号，后者是工程噪声。
- **零行为变化**：哨兵只写日志与标记，不影响任何解析路径的返回值
  或路由；历史批次工件（缓存回放）不受影响（哨兵在缓存回放路径恒
  False，不会误标历史数据）。
- **已知局限**：① 哨兵为模块级全局变量，**跨线程不安全**（若未来
  `extract_json_object` 被并发调用，须改为 `contextvar` 或
  `threading.local`）；② 叶子档命中 ≠ 片段一定缺关键字段（可能只是
  片段结构不同）——`m10_leaf_fallback` 标记的是"提取器回退事件"，
  不保证下游字段缺失由回退引起（需配合 `logic_degraded` 联合判读）。

## 落地状态（2026-10-16 I 轮补记）

本 ADR 采纳后**两天内其核心主张并不成立**——"可分离性"只是设计意图，不可机读。
两处断口，均在 I 轮接线 `failure_taxonomy` 时实测发现：

1. **标记写进了 `test_plan` 内部，从未抬到状态顶层**（登记册 §4 "G 轮新登记"条：
   1 个写侧、0 个读侧）。`m10_leaf_fallback` 又未在 `AITesterState` 声明，故
   LangGraph 直接丢弃该键，批次工件的投影行也读不到 → 无法从任何工件验证
   某次运行是否真走了 M10 叶子回退。**已修**：`state.py` 声明 + 默认 False、
   `_planner_node` 无条件抬升（与 G3 的 `logic_degraded` 同构）、批次工件
   白名单与 per-task 行各加一键（I2）。

2. **标记在它最该生效的路径上被吞掉**（更隐蔽，且方向是**反向错判**）。
   叶子降级档返回的是最内层片段（如 `{"k": 42}`），片段通常连 `function_name`
   都没有 → `_validate_planner_output` 判 False → `_planner_node` 用默认计划
   **整份替换** `test_plan`，planner 刚写下的标记随之丢弃 → 顶层只能抬到
   `False`，"提取器误诊"被记成"LLM 真未输出"。实测日志链：
   `helpers.py:735`（叶子回退）→ `planner.py:380`（写标记）→
   `nodes.py:2324`（缺 function_name）→ `nodes.py:337`（默认计划，标记消失）。
   **已修**：替换前先摘出标记再回填（I2b）。

两处修复的回归护栏均为端到端用例（真 `PlannerAgent` + 真 `_planner_node`），
不再手工构造理想输入——本 ADR 原先的 6 例只覆盖 `helpers` 侧哨兵，
**写侧的 `result["m10_leaf_fallback"]` 赋值本身此前无任何测试**，这正是
断口能存活两天的原因。见
`tests/test_nodes_batch11_pure_logic.py::TestM10LeafFallbackTopLevelLift`
（含 `test_marker_survives_default_plan_replacement`）与
`tests/test_planner.py::test_plan_leaf_fallback_marks_m10_misattribution`。

"写侧从未被测过"有独立的覆盖率证据：`agents/planner.py` 在 H 轮终态为
**0.9780（89/91 行）**，两行未覆盖恰是 `352`（叶子回退归因告警）与
`379`（`result["m10_leaf_fallback"] = True`）——即本 ADR 决策 2 的写侧本体；
I 轮补齐 3 例后该模块升至 **1.0000（91/91）**，两个半覆盖分支
（`351(50%)` / `378(50%)`）同时补齐。

> 方法论：本 ADR 的"后果"一节写的是**期望**，不是**已验证事实**。
> "纯观测标记已写入"与"该标记可被下游读到"是两件事；后者需要一条
> 从写侧到工件的端到端用例，否则装饰性观测标记可以无限期存活。

## 演进方向

- 若 M10 误诊计数（`m10_leaf_fallback=True`）在成规模跑批中占比
  显著（>50% 的 M10 任务），考虑把叶子回退档从"静默兜底"升级为
  "显式 raise + 上游重试"（与 ADR-0031 finish_reason 守卫同模式）；
- `contextvar` 替代模块级哨兵（若并发场景需要）；
- 与 ADR-0031 §已知局限③（`max_tokens` 未预防性上调）联合：
  若观测到成规模 `finish_reason=length` 截断，对 JSON 调用点
  显式设 `max_tokens`。
