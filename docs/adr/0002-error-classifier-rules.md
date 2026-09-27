# ADR-0002: 错误分类器采用纯规则匹配（不消耗 LLM token）

- 日期：2025-10（初始 5 类），2026-09-14 批次扩至 12 类，
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
