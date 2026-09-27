# ADR-0001: 选用 LangGraph StateGraph 作为工作流编排引擎

- 日期：2025-10（项目初始架构）
- 状态：已采纳（Accepted）
- 关联：`src/graph/workflow.py`、`src/graph/nodes.py`、`src/graph/state.py`

## 背景（Context）

AITester 是一个多智能体系统（Planner → Generator → Executor → Debugger →
PatchApplier），节点间存在循环修复路径（Executor 失败 → Debugger → PatchApplier
→ 再回 Executor，最多 N 轮）。需要一种图式编排引擎来表达这种**带条件回边的
循环 DAG**，而非线性 pipeline。

## 决策（Decision）

采用 **LangGraph StateGraph**（Python 版）：

- 共享状态字典（`AITesterState` TypedDict）在节点间传递，节点是
  `state → update_dict` 的纯函数（无副作用，线程安全，可被 LangGraph 并发调度）；
- 条件路由函数（`_should_debug`）实现循环终止（test_passed / iteration >=
  MAX_ITERATIONS / regenerate 上限）；
- 各节点函数拆分到 `src/graph/nodes.py`（与 workflow.py 解耦，
  workflow.py 仅保留图构建与路由）。

## 后果（Consequences）

**正面**：

- 循环回边由 LangGraph 原生支持（add_conditional_edges 的 "debug" 分支回边），
  比手写状态机 / 循环结构清晰；
- 节点纯函数化 → --parallel 多任务并发安全（LangGraph 线程池调度，
  节点不共享可变状态）；
- 消融开关（ENABLE_PLANNER / ENABLE_DEBUGGER）通过 build_workflow(planner,
  debugger) 参数化建图实现，"无 Planner / 无 Debugger"的基线工作流开箱即用。

**负面 / 已知代价**：

- LangGraph 对节点异常的处理是**整图中断**（不像线性脚本 try/except 只
  影响当前步骤）→ 所有节点必须 try/except 捕获 LLM 调用失败（
  JSONDecodeError / RuntimeError / OSError / BudgetExceededError）并降级兜底，
  保证工作流不因单点故障崩溃（见 ADR-0005）；
- 节点间通信只通过共享状态字典（紧耦合在 state schema 上）→ 后续批次
  引入 1.4 事件总线（`src/graph/event_bus.py`）作为**旁路观测层**
  （不改 LangGraph 路由，见 ADR-0007）。
