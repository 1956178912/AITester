# R-2 预注册（跑批前冻结）：示例自校验过滤器离线评估

- 冻结时间：2026-10-18（过滤器实现完成、重放开始前）
- 性质：**探索性机制验证**（非 confirmatory；零 LLM、复用 P-1 已生成 examples）
- 输入：`experiments/results/p_round_oracle_examples_20261018/ORACLE_EXAMPLES_REPORT.json`
  的 20 任务 / 90 条 LLM spec-only examples（P-1 raw；不重新生成）
- 基线：P-1.1 表示归一结果 `ORACLE_EXAMPLES_REPORT_norm.json`（correct 8 / fp 0 /
  silent 3 / misguided 2 / unavailable 7；分母 13，两源臂相同）
- 处理：`src/specs/spec_ir_v2.py::self_validate_examples`（默认开启；env
  `SPEC_EXAMPLES_SELF_VALIDATE=false/0/off` 可关）。仅当可机检后置子句
  （`postconditions_expr`）在受限 AST 求值下为 **False** 时丢弃该示例
  （原因 `postcondition_false`）；语法/白名单外/名称缺失/异常/超长 → **保留**
  （保守放行，不误杀）。无 examples 路径零变化。
- 重放：`experiments/oracle_examples_replay.py --reuse-examples <P-1 raw>`
  到本目录（`ORACLE_EXAMPLES_REPORT_selfcheck.json`），仅本地 pytest 分类，
  **零 LLM 调用**。

## 判定规则（预先冻结，跑后不得改）

1. **有效过滤**（primary）：过滤后 B 臂 `misguided` 从 2 → ≤1 **且**
   `correct` 损失 ≤1（相对 8）→ 记为「有效过滤」；
2. **高风险，默认关**：过滤误杀 `correct` 示例导致 correct 下降 **≥2** →
   记为「高风险，默认关」；
3. 其余（如 misguided 未下降且 correct 无损失）→ 记为「**未达有效过滤（无效）**」，
   如实报告并给下一步；不得事后调整阈值或口径。

## 预先声明的预期与风险

- 已知 2 例 hallucination 的规格后置子句很弱：
  `is_valid_parenthesization` 仅 `isinstance(result, bool)`、
  `knapsack` 仅 `isinstance(result, int)` / `result >= 0`——两者对幻觉期望值
  （True / 0）都**不构成可机检矛盾**。因此**预注册预期：过滤器可能 0 拦截、
  无法命中这 2 例**；本评估的价值在于量化"自校验受规约表达力上界约束"，
  而非假定过滤必然有效。
- 次要指标：90 条中 n_evaluable（fully/partially）、n_unevaluable、n_dropped、
  命中任务数、correct/fp/silent/misguided/unavailable 全表、以及逐示例
  决策明细（`FILTER_STATS.json`）。
- 限制：同一批 20 任务、单次重放、n 小；不过滤 LLM 示例质量本身；非
  confirmatory。任何"有效"结论也仅限本批工件，不外推。
