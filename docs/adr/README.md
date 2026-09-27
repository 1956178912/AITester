# ADR 索引（Architecture Decision Records）

> 维护说明：新增 ADR 时在此表追加一行（编号递增 + 状态 + 一句话摘要 + 关联模块）。
> ADR 正文位于本目录（`docs/adr/`），编号 `NNNN-<slug>.md`。
> 算法设计文档 `docs/algorithm_design.md` 的"相关 ADR"列与此索引保持同步。

| 编号 | 标题 | 状态 | 一句话摘要 | 关联模块 |
|------|------|------|-----------|---------|
| [0001](0001-langgraph-state-graph.md) | 选用 LangGraph StateGraph 作为工作流编排引擎 | 已采纳 | 用带条件回边的循环 DAG 表达多智能体循环修复路径，而非线性 pipeline | `src/graph/workflow.py`、`nodes.py`、`state.py` |
| [0002](0002-error-classifier-rules.md) | 错误分类器采用纯规则匹配（不消耗 LLM token） | 已采纳 | 17 类正则优先级链 + 状态细化层；2026-09-28 批次叠加置信度分层（L1 规则 + L2 协议预留） | `src/agents/error_classifier.py` |
| [0003](0003-default-off-experiment-hygiene.md) | 默认行为不变原则（实验口径收敛） | 已采纳 | 全部新能力以"默认关 + 独立开关"落地，保证 A/B 对比（ON vs OFF）历史口径不变 | 全部新模块（`patch_postprocess.py` 等） |
| [0004](0004-zero-default-deps.md) | 零默认外部依赖（可选依赖透明降级） | 已采纳 | 核心能力只依赖 langgraph/openai/pytest；可选增强（chromadb/onnxruntime/mypy 等）缺失时透明降级 | `requirements.txt`、`src/utils/embedding_utils.py` |
| [0005](0005-node-degradation.md) | 节点异常降级兜底（工作流不崩溃） | 已采纳 | 各节点捕获 LLM 调用 / 缓存 / 预算异常并降级，避免 LangGraph 整图中断 | `src/graph/nodes.py`、`src/agents/base_agent.py` |

## 状态约定

- **已采纳（Accepted）**：决策已落地，模块行为以此为准；
- **已废弃（Deprecated）**：被后续 ADR 取代，保留历史记录；
- **已取代（Superseded by NNNN）**：指向取代它的 ADR；
- **提案中（Proposed）**：待评审。

## 维护惯例

1. 新增 ADR 用下一个可用编号（当前最大 0005 → 下一个 0006）；
2. 文件命名 `NNNN-<kebab-slug>.md`；
3. 正文结构：`# ADR-NNNN: 标题` + 元信息（日期 / 状态 / 关联模块）+
   背景 / 决策 / 后果 / 已知局限与演进方向；
4. 落地改动须在 ADR"已知局限与演进方向"或本索引标注批次日期；
5. `docs/algorithm_design.md` 的"相关 ADR"列须与本表同步（新增 ADR 时
   评估是否影响算法设计映射表）。
