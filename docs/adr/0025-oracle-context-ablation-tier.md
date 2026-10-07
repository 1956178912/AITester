# ADR-0025: oracle 生成上下文消融档——ORACLE_CONTEXT_TIER（full | minimal）

- 日期：2026-10-07（修复引擎批次 XI，第十七轮审查建议 9）
- 状态：已采纳（Accepted——消融臂；默认 full，A/B 后再议默认值）
- 关联：ADR-0003（默认关惯例）、`src/tools/logic_spec.py`、`src/graph/nodes.py`

## 背景（Context）

ASE 2025 实证研究（13,866 个 LLM 训练截止后的测试预言，135 个 Java 项目）：LLM 生成预言的平均 mutation score 43% 接近人类 45%；关键发现——**测试前缀与被测程序中调用的方法提供了足够信息，额外的代码上下文不带来相关收益**（引用核验状态：venue/数字未一手核验，方向锚点）。

本仓 Generator prompt 的"额外上下文"注入段有四：分支覆盖清单（O3）、AST 边界三元组（M10）、蜕变关系（N2）、差分测试（N4）——各段有独立开关但从未做"全有 vs 全无"的边际贡献消融；若 ASE 结论在本管线成立，可显著降低 token 成本。

## 决策（Decision)

1. `ORACLE_CONTEXT_TIER`（`full` | `minimal`，默认 `full`，非法值回退 full）：minimal 时 `_generator_node` 的四个增强段**全部强制不构造**（各段保持 None，与各自开关关闭同构）——消融对照臂。
2. 范围界定：minimal 只剥离四增强段；`target_code`（被测源码）仍完整注入——生成可执行测试骨架（import/调用）必需，ASE 口径针对的是 oracle（断言）部分的额外上下文，不覆盖骨架输入。
3. A/B 协议（预注册后执行）：同任务集 × {full, minimal} × 四开关全开 → 比较 spec_compile_rate / mutation_detection_rate / token 成本；若 minimal 无质量损失且省 token 显著，再议默认值变更（口径变更须过 ADR）。

## 后果（Consequences）

**正面**：额外上下文的边际贡献首次可测；若 ASE 结论成立，oracle 生成 token 成本可结构性下降。

**负面/风险**：四段在 synthetic 简单任务上可能本就低频命中（消融差异小、需功效足够的任务数）；ASE 研究为 Java 项目，向 Python synthetic 的外推未证。

## 验证

- 批次 XI 测试锁 7 项（档位三态 + 大小写 + 四段接线源码契约 + None 缺省结构保证）；默认 full 历史口径零变化。

## 修订记录

1. 2026-10-07 首次落地（批次 XI）：`oracle_context_tier`/`oracle_context_minimal` + `_generator_node` 四段 minimal 守卫 + 7 项测试。
