# ADR-0035: SpecExpr 被测函数自递归子句——目标函数名入绑定上下文

- **状态**：已接受
- **日期**：2026-10-17
- **决策**：把被测函数名（`target_function`）作为**受限自调用**注入 SpecExpr
  DSL 的绑定上下文与调用白名单，使 `fibonacci(5) == 5` 一类的自递归规约子句
  可编译为确定性 oracle 断言。

## 1. 背景与问题

- SpecExpr DSL（`src/specs/spec_ir_v2.py`）的调用白名单 `_ALLOWED_CALL_NAMES`
  只收纯内建（len/abs/sorted/...），**刻意排除被测函数自递归**（v4 注释：
  `fibonacci×4 / gcd×1 / factorial×1`，语料 6 实例）——oracle 断言调用被测
  函数自身被列为「语义扩展，需单独设计评审（递归不终止 / 自指真值性）」。
- 后果：6 条真实 Planner 产出的自递归子句整条被 `unsupported_operator`
  拒绝，编译率损失（子句级 0.8847→0.9127 之后仍存的残余阻塞项之一）。
- 事实基础：`compile_spec_oracle` / `_compile_single_clause` **已携带
  `target_function` 参数**（import + 调用用），但该名既未进
  `_known_names_for_signature` 的绑定上下文，也未进 `_WhitelistVisitor` 的
  调用放行集——自递归子句既撞 `dangerous_call` 门、又撞 `unknown_name` 门。

## 2. 决策：受限自调用放行（窄化，不放宽任意注入）

- **机制**：仅把 `target_function` 这一个名字注入
  ① 调用白名单（`_WhitelistVisitor` 的 `visit_Call` 直调形态）；
  ② 绑定上下文（`known_names`）。
  其余任意名字照旧被 `dangerous_call` / `unknown_name` 拒绝——注入面只
  扩到「被测函数自身」，不扩大「oracle 可调任意函数」的暴露面。
- **自指真值性风险（为何可接受）**：`fibonacci(n) == fibonacci(n)` 这类
  恒真断言，与既有 `x == x` 恒真子句**同一风险类**（形态门/白名单门本就不
  拦截裸字面量恒真），不构成新增风险类；而 `fibonacci(0) == 0` 是**已知正确
  属性**——若被测函数有缺陷，该断言在 buggy 代码上变红，正是**最强检测信号**
  （机器锚点与 LLM 断言并行，见 compile_spec_oracle docstring）。
- **递归不终止风险（为何有界）**：oracle 运行受执行器 30s 超时兜底
  （`EXECUTION_TIMEOUT`）；自递归子句只在断言里再调一次被测函数（不是
  oracle 内递归嵌套），实际不引入无界递归。
- **与 df_spec 负结果的关系（关键限定）**：df_spec（2026-10-17）证明
  「以缺陷代码派生锚为规格」会误导；自递归子句的**值取决于 Planner 是否
  从缺陷代码推导出正确属性值**——这是**规格优先路线的通用风险**，不是
  自递归特有。因此本扩展**不改变**规格优先路线的整体结论，只把「本来就在
  NL 通道里的正确属性」提升为可编译断言（口径收紧，非放宽）。

## 3. 实施范围

- `_WhitelistVisitor.__init__` 增 `extra_call_names` 参数（默认空，历史零变化）；
- `_whitelist_check(expr_text, extra_call_names=None)` 透传；
- `_clause_reject_reason_for_known` / `_clause_is_compilable` 增
  `extra_call_names` 透传（默认 None = 历史口径）；
- `_compile_single_clause` / `compile_spec_oracle` 把 `target_function`
  传入 `extra_call_names`，并并入 `known_names`；
- 测试：新增自递归子句可编译用例 + 危险调用仍拒的负例 + 现有 property /
  grammar 契约测试零回归。

## 4. 边界（不做的事）

- 不收**任意**域名函数（graph 的 successor 等，照旧 attr_escape 拒绝）；
- 不收模块链（`collections.abc.Sequence` / `heapq.*` 照旧白名单外门拒）；
- 嵌套自调用（`fibonacci(fibonacci(3))`）**放行**——实参为字面量、有界，
  不构成无界递归，由执行器 30s 超时兜底；
- 不改 `_ALLOWED_CALL_NAMES` 本体（内建白名单保持 frozenset 静态）。
