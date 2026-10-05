# ADR-0002: 错误分类器采用纯规则匹配（不消耗 LLM token）

- 日期：2026-09（原文误标 2025-10，git 首次入库为 2026-09-27，V 批次 P1-9 修正）（初始 5 类），2026-09-14 批次扩至 12 类，
  2026-09-27 批次扩至 17 类
- 状态：已采纳（Accepted）
- 关联：`src/agents/error_classifier.py`

## 背景（Context）

测试失败后需要判断"该走哪条修复路径"（改代码 / 改测试 / 装依赖 /
排查执行链路）。把分类本身交给 LLM（如"让 LLM 判断这是断言失败还是
逻辑错误"）成本不可接受（每个失败任务多 1-2 次 LLM 调用），且分类
本身是**高频、低延迟、可确定性复现**的判断——正则规则匹配即可覆盖
绝大多数已知失败模式。

## 决策（Decision）

**分层分类策略**：

1. **文本正则层**（`classify(test_output, failed_cases, target_module)`）：
   十类优先级链（`LLM_FORMAT_ERROR > IMPORT_ERROR > SYNTAX > TYPE_ERROR >
   INDEX_ERROR > RUNTIME > ASSERTION/LOGIC_ERROR > TIMEOUT > UNKNOWN`），
   全基于正则，零 LLM 成本；
2. **LLM 响应直接分类层**（`classify_llm_response(raw_response)`）：
   P0 4.1 批次新增——在 Debugger 收到 LLM 原始响应后、JSON 解析前直接
   判定 `LLM_EMPTY_RESPONSE` / `LLM_JSON_PARSE_FAILED`（`LLM_FORMAT_ERROR`
   的精确子类），不走正则；
3. **状态细化层**（`refine_failure_category(state)`）：
   按 repair_history / rag_stats / execution_trace /
   multi_candidate_stats / patch_resample_stats 信号判定 5 类
   （`PATCH_VALIDATION_FAILED` / `RAG_RETRIEVAL_EMPTY` /
   `EXECUTION_TRACE_MISSING` / `MULTI_CANDIDATE_ALL_REJECTED` /
   `PATCH_SYNTAX_INVALID`），任务收尾时调用，不走正则；
4. **修复策略显式映射**（`get_recommended_fix_strategy(category)`，
   2.1 批次）：把"该走哪条修复路径"从 workflow 隐式分支收敛为分类器
   输出的结构化标签（`strategy` snake_case 标签 + `repair_action` 四档），
   全 17 类显式覆盖。

## 后果（Consequences）

**正面**：

- 零 LLM 成本——分类器本身不消耗 token（与 3.4 成本优化目标一致）；
- 确定性可复现——同一 test_output 永远分到同一类（实验可 A/B）；
- 新失败模式只需加一条正则 / 一个状态细化信号（扩展成本低，
  不动分类器主结构）。

**负面 / 已知代价**：

- 规则库对**未知失败模式**无能为力（落入 UNKNOWN → LLM 兜底）——
  这是"保守可观测"而非"万能分类"的设计取舍；
- LLM_FORMAT_ERROR 必须置于优先级链最前（JSON 解析失败文本可能
  含 IndexError/assert 子串，顺序放反会误判）——优先级是**硬编码
  约定**，新增正则类时须遵守此序。

## 已知局限与演进方向（2026-09-28 评估，未改变当前纯规则实现）

当前 17 类为扁平"追加类别"模式（12→14→16→17）。类别数增长后，
规则匹配的复杂度与误分类风险同步上升（正则优先级链变长、相邻类
边界模糊，如 `RUNTIME` 与 `INDEX_ERROR` / `ASSERTION` 的文本重叠）。
评估三条演进方向（**均为建议，默认行为不变**，任一落地需独立 ADR +
回归守卫）：

1. **层级分类（大类 → 子类）**：把 17 类按根因域聚合为 3-4 个大类
   （LLM 响应域 / 代码域 / 执行环境域 / 状态域），细类挂在大类下；
   大类决策（走向哪条修复策略族）稳定后细类仅做观测细分。收益：
   新增细类不再扰动大类优先级链；代价：重构 `ErrorCategory` 枚举
   与 `get_recommended_fix_strategy` 映射表（全 17 类显式覆盖需
   重建）。建议**仅在类别数 ≥ 20 或误分类率实测上升时启动**，
   避免过早抽象。
2. **概率 / 置信度分类（top-2 + 置信度）**：正则命中不止一类时
   输出 top-2 类别 + 启发式置信度（命中正则数 / 文本段占比），
   而非单类硬判定。低置信度样本走**降级路径**：触发针对性重试
   （按 top-1 策略重试一次，仍低置信则进通用兜底），减少对 LLM
   通用修复的依赖。建议独立开关 `SEMANTIC_CLASSIFY_ENABLE`
   （默认 false，复用 5.1 嵌入后端的轻量语义兜底，见
   algorithm_design §3.1 已知局限①）先行落地，概率化作为其后
   观察项。
   > **2026-09-28 改进批次已落地最小置信度分层**（不改变本 ADR 决策，
   > 纯增强）：`ErrorClassifier.classify_with_confidence()` 在 L1 规则
   > 层上叠加置信度（具体特征命中 0.9 / 弱命中 0.5 / 未命中 0.2），
   > 低置信度样本（confidence ≤ 0.5）触发**低置信度兜底策略**
   > （收敛到 generic_analysis 而非硬性路由），并预留 L2 概率化/ML
   > 层 `ProbabilisticClassifier` 协议（当前 `_default_probabilistic_
   > classifier` 恒 None，落地 L2 需独立 ADR + 回归守卫）。
   > 历史 17 类口径逐样本等价（`enable_fallback=False` 时兜底不触发）。
3. **UNKNOWN 收敛 SLA**：`docs/failure_analysis.md` 历史快照中
   UNKNOWN 曾占 75%，经类别扩展已收敛。建议为"UNKNOWN 占失败
   总数比例"设定监控目标（≤ 15%），超阈值时由失败知识库
   （`experiments/analyze_failures.py --knowledge-base`）的高频
   根因模式驱动新增类别，而非无目的追加——离线→在线闭环设计
   见 `docs/design/failure_knowledge_feedback.md`。

> 边界声明：本 ADR 的当前决策（纯规则、零 LLM 成本、确定性可复现）
> **保持不变**；上述方向为演进评估，不改变 17 类现有实现。
