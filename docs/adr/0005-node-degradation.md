# ADR-0005: 节点异常降级兜底（工作流不崩溃）

- 日期：2026-09（原文误标 2025-10，git 首次入库为 2026-09-27，V 批次 P1-9 修正）（初始），2026-09-26 全面审查批次扩展
- 状态：已采纳（Accepted）
- 关联：`src/graph/nodes.py` 全部节点、`src/agents/base_agent.py`

## 背景（Context）

LangGraph 对节点异常的处理是**整图中断**（与 ADR-0001 的负面
后果对应）。任何 LLM 调用失败（网络超时 / JSON 解析失败 /
响应为空 / 缓存目录被删 / 预算耗尽）若不被节点捕获，会让整个
多智能体工作流崩溃——用户拿到的是一个 LangGraph 异常堆栈，
而非"这个任务修复失败，原因是 X"的语义化结果。

## 决策（Decision）

**每个 LLM 消费节点 try/except 降级兜底**（统一口径）：

- 捕获集合（2026-09-26 批次统一扩展）：
  `(json.JSONDecodeError, RuntimeError, OSError, BudgetExceededError)`
  - `OSError`——LLM 文件缓存读写在缓存目录被外部删除/磁盘满时抛出
    （此前未捕获会让整图崩溃，与 debugger 节点同口径兜底）；
  - `BudgetExceededError`（5.4 批次新增，`RuntimeError` 子类）——
    任务级预算耗尽，节点捕获后**快速降级**（planner 走默认计划、
    generator 空测试、debugger 跳过本轮修复 + 标记
    `error_category="budget_exceeded"`），后续迭代前置守卫
    （`BaseAgent._call_llm` 的 `is_budget_exceeded()` 检查）
    同样快速失败，任务自然收敛；
- 降级策略（保持"失败任务"语义，非"成功"）：
  - planner → 默认计划（空逻辑分析，generator 仍可基于目标代码生成）；
  - generator → 空测试字符串；
  - debugger → `root_cause="JSON 解析失败: {e}"` + 空 patch；
  - patch_applier → 不写盘（`written=False`）；
- **5.4 批次起改用 `isinstance(e, BudgetExceededError)` 判定**
  （而非字符串匹配 `"预算耗尽" in str(e)`）——字符串匹配在
  异常消息文案变更后静默失效，isinstance 是稳定口径。

## 后果（Consequences）

**正面**：

- 工作流不因单点故障崩溃——LLM 异常 / 缓存 IO 异常 / 预算耗尽
  全部降级为"失败任务 + 语义化错误类别"，benchmark 可统计
  "预算封顶任务数" / "JSON 解析失败任务数"等口径；
- 用户拿到的是结构化失败结果（error_category / root_cause），
  而非 LangGraph 堆栈。

**负面 / 已知代价**：

- 降级路径掩盖了"本该成功"的场景（如 planner 默认计划 =
  空逻辑分析，generator 只能盲生成）——这是"不崩"与"不掩盖
  失败"的取舍，通过 `error_category` 标签（非 `unknown`）
  保留可观测性。
