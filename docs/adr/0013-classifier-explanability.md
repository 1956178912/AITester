# ADR-0013: 错误分类可解释性字段与修复策略追踪链

## 状态

已接受（2026-09-29 批次落地，零 LLM 成本纯数据口径）

## 背景

外部数据支撑：

- 2026 年可解释性研究："大多数 AI 驱动的测试解决方案作为不透明的
  黑盒系统运行，限制了透明度、问责制和信任……可解释性应被视为
  **基础设计原则，而非可选功能**"。
- Defects4J 上 LLM 增强工作流实验：可解释性标注使"验证时间减少
  34%，并提高了 AI 生成测试工件的可解释性和可信度"。
- 修复报告此前只记录"走了哪条修复路径"（strategy 标签），不记录
  "**为什么**选这条路径"——审计 / 回归分析 / 监管合规场景下无法
  回答"这个修复策略是怎么决定的"。

## 决策

1. `ClassificationResult` 新增 `explanation` 字段（`error_classifier.py`）：
   - 命中规则特征说明（"命中导入错误特征（缺失模块 pandas）"）；
   - 弱命中显式标注（"仅通用 file.py:line:col 格式命中"）；
   - 置信度口径（"confidence 0.90 (regex_hit)"）；
   - 兜底触发标注（"低置信度 → 触发兜底策略（generic_analysis）"）。
   纯数据口径（零 LLM 成本、确定性可复现），L1 规则层与 L2 注入
   路径均产出说明。
2. 策略追踪链（LLM-dsWF 框架参照"可追踪依赖链"）：
   `错误分类（explanation）→ 修复策略选择（get_recommended_fix_strategy
   结构化记录）→ 补丁生成 → 验证结果（execution_trace）` 四环节
   的现有 state 键（`error_category` / `repair_strategy` /
   `repair_history` / `execution_trace`）经 `explanation` 字段闭环，
   报告层（`src/reports`）后续批次接入渲染。

## 后果

- 正面：修复决策从"黑盒标签"升级为"可审计说明"——每次修复可回答
  "为什么选这个策略、置信度多少、哪些候选被兜底覆盖"；实验分析层
  可按 explanation 关键词聚合"哪类规则命中导致修复质量波动"。
- 负面：字段为纯文本（无结构 schema），消费方解析依赖现有
  confidence/category 结构化字段（explanation 只作人类可读注解）。
- 回归守卫：`tests/test_error_classifier_combinations.py`（L2 注入
  三态 + 全类别策略查表）。

## 参考

- 改进建议 4.4（可解释性与信任）；
- ADR-0002（分类器分层架构"已知局限与演进方向"）。
