# 失败知识库 → 修复策略 离线→在线闭环设计（Design-only，未实装）

> 立项日期：2026-09-28
> 状态：**设计文档（Design-only）**——本文档定义闭环流程与落点，
> 尚未改动任何运行时代码（默认行为不变；实装时另立批次 + ADR）。
> 关联：`experiments/analyze_failures.py`（`failure_knowledge_base()` /
> `root_cause_classification()` / CLI `--knowledge-base/-k`）、
> `src/agents/error_classifier.py`（`ErrorClassifier` /
> `get_recommended_fix_strategy`）、`docs/adr/0002-error-classifier-rules.md`。

## 1. 背景与动机

`experiments/analyze_failures.py` 已支持 `failure_knowledge_base()` 输出
结构化 JSON（`task_id` / `root_cause`（`llm_capability` / `dependency` /
`framework` 三大类）/ `error_category` / 复现步骤 / 建议修复），并可通过
CLI `--knowledge-base/-k` 落盘 `failure_knowledge_base.json`。但当前该
知识库**仅用于分析报告**，尚未与运行时 Debugger 策略选择形成闭环——
离线积累的高频根因模式（如 `LLM_BREAKS_IMPORT` 在特定项目结构下
复发）没有反哺到 `ErrorClassifier` 规则权重或 Debugger prompt 模板
选择。

目标：设计一条**离线积累 → 人工审核 → 高置信度模式固化为规则 /
prompt 片段 → 后续运行验证效果**的闭环，减少对 LLM 通用修复兜底
的依赖，使高频已知模式走确定性路径。

## 2. 闭环流程（五阶段）

```
┌─────────────┐    ┌─────────────┐    ┌──────────────┐
│ ① 离线积累   │ →  │ ② 人工审核   │ →  │ ③ 固化落地    │
│ analyze_     │    │ 高置信度模式  │    │ 规则权重 /    │
│ failures -k  │    │ 聚类 + 打分  │    │ prompt 片段   │
└─────────────┘    └─────────────┘    └──────┬───────┘
                                              │
┌─────────────┐    ┌─────────────┐           │
│ ⑤ 效果验证   │ ←  │ ④ 后续运行   │ ←────────┘
│ 对比修复率 /  │    │ 消费固化产物  │
│ token 消耗    │    │              │
└─────────────┘
```

### ① 离线积累

`experiments/analyze_failures.py --results-dir experiments/results -k
experiments/results/failure_knowledge_base.json` 产出结构化知识库。
积累口径：多次 benchmark 批次的 `failure_knowledge_base.json` 合并，
按 `(root_cause, error_category)` 聚合出现频次。

### ② 人工审核（高置信度判定）

对知识库中的模式做聚类与置信度打分，**人工确认**哪些模式可固化。
保守口径（先人工、后自动）：

- 频次阈值：同一 `(root_cause, error_category)` 组合在 ≥ N 次独立
  批次中出现（N 默认 3，保守防单批次噪声）；
- 一致性：该组合下复现步骤 / 建议修复文本相似度 ≥ 阈值（词袋
  余弦，复用 `src/utils/embedding_utils.py` 的 `cosine_similarity`）；
- 人工签核：每条拟固化模式需记录"签核人 + 批次来源 + 决策日期"
  （落 `experiments/results/kb_review_log.json`，审计可追溯）。

不通过签核的模式**不进入**③，保留在知识库作观察项。

### ③ 固化落地（两个可选落点，均默认关）

**落点 A：`ErrorClassifier` 规则权重增强**（`src/agents/error_classifier.py`）

- 高置信度模式 → 该 `ErrorCategory` 的正则命中权重上调（在
  `classify()` 的多候选判定中作为 tie-breaker）；
- 独立开关 `KB_CLASSIFIER_BOOST_ENABLE`（默认 false），权重表经
  环境变量 / 配置文件注入（不在分类器内硬编码，保持"纯规则、
  零 LLM 成本"ADR-0002 口径）；
- 回归守卫：开关关时分类结果与历史 17 类口径**逐样本等价**
  （`tests/test_error_classifier.py` 加等价性守卫用例）。

**落点 B：Debugger prompt 模板片段注入**（`src/agents/debugger.py`）

- 高置信度模式 → 该 `error_category` 对应的针对性 prompt 片段
  （如 `LLM_BREAKS_IMPORT` 在 sqlfluff 插件结构下：强调"保留
  `Rule_L*` 命名契约、仅改方法体不改类名"）；
- 片段落 `experiments/results/kb_prompt_snippets.json`（人工签核
  后生成），经 `KB_PROMPT_SNIPPET_ENABLE`（默认 false）在
  `_debugger_node` 注入；
- 保守口径：片段仅**追加**到既有 prompt 尾部（不替换历史模板），
  注入失败 / 开关关时 prompt 与历史逐字节一致。

### ④ 后续运行消费

下一轮 benchmark / 实验运行时，开启对应开关后分类器 / Debugger
自动消费固化产物；`state` 新增观测键（`kb_classifier_boost_applied` /
`kb_prompt_snippet_applied`，默认 None）供 `analyze_results.py` 统计
"哪些任务走了 KB 增强路径"。

### ⑤ 效果验证（转正判据）

- **修复率**：KB 增强批次 vs 同任务集非增强批次，目标错误组合的
  修复成功率**不下降**（理想 +5pp 以上）；
- **token 消耗**：走 KB 路径的任务平均 `total_tokens` ≤ 非 KB 批次
  （针对性 prompt 应省通用 LLM 兜底 token）；
- **回归**：全量 `pytest tests/` 零回归 + 默认路径（开关全关）
  口径逐样本等价。
  未满足 → 回退固化产物（删 kb_prompt_snippets.json 对应条目 +
  记录 review log），不强行上线。

## 3. 与现有组件的边界

- 不改变 ADR-0002 当前决策（纯规则、零 LLM 成本、确定性可复现）——
  落点 A/B 均为**可选增强**，默认关时与历史口径逐样本等价；
- 不自动改写分类器源码（权重 / 片段经外部 JSON 注入，规则库本身
  不膨胀）；与 ADR-0002"已知局限与演进方向"（层级 / 概率分类）
  正交——KB 闭环解决"高频已知模式的确定性路径"，层级化解决
  "类别数增长的复杂度治理"，二者可叠加但不互相依赖；
- 失败知识库的三大根因（`llm_capability` / `dependency` /
  `framework`）分类口径以 `root_cause_classification()` 保守
  启发式为准，本文档不重定义根因域。

## 4. 实装里程碑（后续批次，独立 ADR）

| 里程碑 | 内容 | 前置 |
|--------|------|------|
| M1 | 落点 B（prompt 片段注入，`KB_PROMPT_SNIPPET_ENABLE`）+ 2 条人工签核片段 | ①②③ 流程人工走通一次 |
| M2 | 落点 A（分类器权重增强，`KB_CLASSIFIER_BOOST_ENABLE`） | M1 验证无回归 |
| M3 | ⑤ 效果验证自动化（`analyze_results.py` 增"KB 增强批次"章节） | M1/M2 至少一个转正 |

> 任一里程碑实装前：`pytest tests/` 全绿 + 双语文档同步 +
> BASELINE.yaml 刷新；默认行为不变（新开关全默认关）。
