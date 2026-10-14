# SpecExpr DSL 修复后管线冒烟（2026-10-14，3 任务 save-state）

> 用途：验证 §6.9 两项度量门修复在**真实管线**端到端有效（nodes.py 接线
> 无崩溃、compile rate 按新门计算）。干净口径（replace + SPEC_IR +
> DSL，无 profile），seed45 前 3 任务，缓存 namespace `dsl_fix_smoke_v1`。

## 结果

| task | compile_rate | expr_coverage | spec_replace_applied |
|---|---|---|---|
| synthetic__task_0000 | 1.0 | 1.0 | attempted_replaced |
| synthetic__task_0001 | 1.0 | 0.8 | attempted_replaced |
| synthetic__task_0002 | 0.0 | None | attempted_fallback（无规约材料） |

provenance：profile=None、SPEC_IR_ENABLE=true、SPEC_IR_DSL_ENABLE=true、
DETECTION_SPEC_MODE=replace、指纹 aeb56401ca74e127… pinned。

**注意**：本冒烟为修复后**全新 LLM 抽样**（Planner 跨跑批非确定性），
与 `emse_dsl_diag2_20261014` 的子句不同——compile rate 的**受控对比**
以后者的离线对账为准（36.7%→46.7%），本工件只证明接线有效性。
