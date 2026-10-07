# ADR-0026: 交互中心失败归因——终局桶增补 edge × fault_side 维度

- 日期：2026-10-07（修复引擎批次 XII，第十七轮审查建议 19）
- 状态：已采纳（Accepted——增补维度，终局桶/MAST 口径保留）
- 关联：`src/observability/failure_taxonomy.py`、ADR-0021（correct 口径修正使失败归因更有意义）

## 背景（Context）

1. 第十七轮审查建议 19：MAST 式终局分类是"系统级结果导向"，不足以支撑修复分配；"Model or Harness?"（2026）的交互中心分类法把失败定位到**交互边**并标注**故障侧**，使每个标签直接对应修复动作（引用核验状态：未一手核验，方向锚点）。
2. 本仓终局桶（U11 五桶）已服务跨臂对比；缺的是"失败该找谁修"的维度。

## 决策（Decision）

1. **增补而非替换**：`interaction_attribution(state)` → `{"edge", "fault_side"}`；`annotate_final_state` 输出加键（向后兼容，既有三键语义零变化）；MAST 式桶分布照旧输出（跨臂可比职能保留）。
2. 取值域：edge ∈ {planner_to_generator, generator_to_executor, debugger_to_executor, harness, uncategorized}；fault_side ∈ {model_side, harness_side, environment, grader, uncategorized}。
3. 映射（确定性、与终局桶判定同源维护 `_STOP_REASON_TO_INTERACTION`）：
   - recursion_limit / budget_exceeded → (harness, harness_side)——编排上界问题，修复动作指向 scaffolding；
   - 规约层失效（test_gen_diagnosis* / regeneration_cap）→ (planner_to_generator, model_side)；
   - 生成能力不足（max_iterations / coverage_stall / repair_invalid）→ (debugger_to_executor, model_side)；
   - 回归门拦截 → (debugger_to_executor, **harness_side**)——验证门组件拦截，与"补丁质量差"（model 侧）显式区分；
   - 收敛行不冒充归因（fault_side=uncategorized）。
4. `summarize_batch` 增 `fault_side_counts`/`edge_counts`；`render_markdown` 增交互归因表（附修复动作指向列）。

## 后果（Consequences）

**正面**：失败分布首次带"该找谁修"的行动语义（model_side 占比 = 生成质量优化空间；harness_side 占比 = scaffolding 缺陷面）；存量 final_state 行零成本重算。

**负面/风险**：environment / grader 两档当前映射表无命中入口（预留取值域，等 SWE-bench 类真实环境任务与裁决口径事件接入）；映射表与 StopReason 双表同源维护有漂移风险（测试锁取值域）。

## 验证

- 批次 XII 测试锁 12 项（映射七态 / 取值域 / 向后兼容全分支 / 聚合与渲染）+ 既有 taxonomy 28 项全绿。

## 修订记录

1. 2026-10-07 首次落地（批次 XII）：`interaction_attribution` + `annotate_final_state` 增补键 + `summarize_batch`/`render_markdown` 交互视角聚合 + 12 项测试。
