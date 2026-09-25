> **语言 / Language**：[English](failure_analysis.en.md) | 简体中文（本文）

# 失败案例分析 (Failure Case Analysis)

## 概述

本文档对 AITester 在合成数据集实验中的失败案例进行深入分析，识别系统瓶颈和改进方向。

> **状态说明（2026-09-14 批次③）**：本文档为历史数据快照（50 任务合成实验）。下文中 UNKNOWN 占 75%（JSON 解析失败、空响应）与 RUNTIME 中的索引越界两类根因，已在 2026-09-14 批次通过 `ErrorCategory` 扩展为 12 类（新增 `LLM_FORMAT_ERROR` / `INDEX_ERROR`，批次②再补状态细化类 `PATCH_VALIDATION_FAILED` / `RAG_RETRIEVAL_EMPTY`）解决——这两类错误现在会被分类器单独识别，Debugger 走针对性策略而非通用 LLM 兜底。重跑实验时新的失败分布应显著低于本快照，请以最新 `experiments/analyze_results.py` 输出的三处章节为准：**"按基线失败原因分布"**（1.2 细化类别可单独计数）+ **"修复收敛效率（1.2）"**（首次尝试成功率 / 成功任务迭代与耗时统计）+ **"多维质量代理（1.1，保守可复算）"**（覆盖率/耗时/断言行数/失败 Top N 类别）。另：5.3 批次后 `experiments/analyze_failures.py` 新增**失败根因三大类**（`llm_capability` / `dependency` / `framework`，`root_cause_classification()` 保守启发式归类）+ **失败案例知识库**（`failure_knowledge_base()` 结构化 JSON，CLI `--knowledge-base/-k` 落盘 `failure_knowledge_base.json`），失败归因口径以该脚本输出为准。

**实验设置**（历史数据快照，非当前版本性能承诺）：
- 数据集：Synthetic Dataset (50 tasks)
- 基线：AITester (完整系统)
- 失败数：16/50 (32% failure rate)

---

## 失败案例统计

### 按错误类型分布

| 错误类型 | 数量 | 占比 | 典型场景 |
|---------|------|------|---------|
| UNKNOWN | 12 | 75% | JSON解析失败、空响应 |
| RUNTIME | 3 | 19% | 未预期的异常类型 |
| ASSERTION | 1 | 6% | 测试断言不匹配 |

### 按Bug模式分布

| Bug模式 | 失败数 | 成功率 |
|--------|--------|--------|
| palindrome_case_sensitive | 2 | 0% |
| off_by_one_right | 1 | 50% |
| clamp_range_error | 1 | 0% |
| divide_by_zero_missing | 1 | 50% |
| string_split_empty | 1 | 0% |
| 其他 | 10 | ~70% |

---

## 典型失败案例分析

### 案例1: JSON解析失败 (UNKNOWN)

**任务ID**: `synthetic__palindrome_case_sensitive_0002`

**失败现象**:
```
diagnosis: "JSON 解析失败: Could not find complete JSON: line 1 column 1 (char 0)"
```

**根因分析**:
1. LLM返回的响应格式不符合预期（非标准JSON）
2. GeneratorAgent的JSON提取逻辑过于严格
3. 系统Prompt可能未明确指定输出格式要求

**改进建议**:
- 增强JSON提取的鲁棒性，支持多种格式（markdown代码块、纯JSON、混合内容）
- 添加响应格式验证和自动修复机制
- 优化System Prompt，明确指定输出格式规范

**优先级**: 🔴 高（影响核心流程）

---

### 案例2: 边界条件处理失败 (UNKNOWN)

**任务ID**: `synthetic__off_by_one_right_0001`

**失败现象**: Debugger在修复二分查找边界错误时未能正确识别问题

**根因分析**:
1. 错误分类器将问题归类为UNKNOWN而非RUNTIME
2. Debugger的修复策略对边界错误不够针对性
3. 缺乏对索引越界问题的专门处理规则

**改进建议**:
- 扩展错误分类模式，增加IndexError相关匹配规则
- 为边界错误添加专门的修复策略模板
- 增强Debugger的上下文理解能力

**优先级**: 🟠 中（需要算法改进）

---

### 案例3: 复杂逻辑修复失败 (RUNTIME)

**任务ID**: `synthetic__clamp_range_error_0005`

**失败现象**: clamp函数在min_val > max_val时未抛出异常

**根因分析**:
1. 测试用例期望特定行为（抛出ValueError）
2. 原代码仅处理正常范围情况
3. Debugger未能生成正确的边界检查代码

**改进建议**:
- 增加对值域验证错误的识别
- 为范围检查添加专用修复模板
- 增强RAG检索，找到类似的范围验证案例

**优先级**: 🟡 低（可以通过提示工程缓解）

---

## 系统性问题

### 问题1: LLM响应质量不稳定

**影响范围**: 75%的失败案例

**表现**:
- 部分响应包含思考过程（reasoning_content）
- 部分响应格式不符合JSON规范
- 部分响应为空或截断

**解决方案**:
1. 实现响应后处理管道，标准化输出格式
2. 添加重试机制，针对格式错误自动重试
3. 使用更可靠的模型（如gpt-4o替代flash模型）

---

### 问题2: 错误分类器覆盖不足

**影响范围**: 所有失败案例

**表现**:
- 12/16失败案例被归类为UNKNOWN
- 分类器依赖正则匹配，难以覆盖复杂错误模式
- 缺少语义级错误理解

**解决方案**:
1. 扩充错误模式库，覆盖更多异常类型
2. 引入轻量级语义分类（使用小模型）
3. 添加人工标注数据进行模型微调

---

### 问题3: RAG检索效果有限

**影响范围**: 中等

**表现**:
- 当前RAG启用率较低（默认false）
- 向量检索对相似bug的匹配精度有限
- ~~缺少失败案例的知识库~~ → 5.3 已实现：`experiments/analyze_failures.py --knowledge-base/-k` 输出结构化失败案例知识库（`failure_knowledge_base.json`，含 task_id / root_cause / reproducible_steps / suggested_fix），按 error_category 多样性优先选取

**解决方案**:
1. ~~启用RAG并构建失败案例知识库~~（5.3 已落地 `failure_knowledge_base`，结构化案例 + 可复现步骤 + 建议修复）
2. 优化嵌入模型，提升语义匹配精度
3. 实现混合检索（向量+关键词）

---

## 改进路线图

### 短期改进（1-2周）

- [x] ~~增强JSON提取逻辑，支持多种响应格式~~ → 已实现：JSON 提取已支持多格式（markdown 代码块 / 纯 JSON / 混合内容，见 `extract_json_object`）
- [x] ~~扩充错误分类模式库~~ → 已实现：错误分类已从 5 类扩展至 14 类（`LLM_FORMAT_ERROR` / `INDEX_ERROR` / `PATCH_VALIDATION_FAILED` / `RAG_RETRIEVAL_EMPTY` / `EXECUTION_TRACE_MISSING` / `MULTI_CANDIDATE_ALL_REJECTED` 等）
- [ ] 为关键bug模式添加专用修复模板
- [x] ~~启用RAG并优化检索策略~~ → 已实现：`--enable-rag` 纳入主实验（2.3 RAG 消融），检索指标自动汇总（Hit Rate / MRR / 按检索类型分解 / RAG 命中 × 失败类别交叉表）

### 中期改进（1个月）

- [x] ~~实现响应后处理管道~~ → 已实现：重试 + 故障转移（APIManager 熔断冷却 + 半开探测 + 成本感知路由）
- [x] ~~添加失败案例学习和知识沉淀机制~~ → 已实现：5.3 失败根因三大类（`llm_capability` / `dependency` / `framework`）+ 结构化失败案例知识库（`failure_knowledge_base.json`）
- [ ] 优化System Prompt模板
- [ ] 引入模型选择策略（根据任务复杂度自动选择模型）
- [x] ~~数据污染风险应对（2.1）~~ → 已实现：SWE-bench 黄金补丁重叠度检测（`experiments/contamination_check.py`，high ≥ 0.85 / medium ≥ 0.6）+ SWE-rebench 抗污染基准支持（`load_dataset("swe_rebench")`），分析报告自动标注疑似污染任务
- [x] ~~任务难度分层分析（2.2）~~ → 已实现：按 code_size / dependency_count / complexity_proxy 三维度分层（`experiments/difficulty_stratification.py`），定位"系统在什么难度区间能力衰减"
- [x] ~~收敛失败模式归因（1.2）~~ → 已实现：`analyze_results.py:_convergence_failure_modes` 对达到 MAX_ITERATIONS 仍未修复的任务，区分"无法定位根因"（诊断反复同义且从未写盘成功）与"无法生成有效补丁"（补丁写盘成功但测试仍失败 / 被安全守卫反复拒绝）
- [x] ~~边界用例覆盖检测（1.3）~~ → 已实现：`analyze_results.py:_boundary_case_coverage` 对 generated_test 做 AST 保守判定，识别 None / 空字符串 / 空集合 / 0 / -1 / >= / <= 等边界条件，输出各边界类型命中数与覆盖率
- [x] ~~变异得分收集（1.3）~~ → 已实现：`analyze_results.py:_mutation_score_metrics` 收集 details[].mutation_score（外部变异测试器产出），汇总平均 / 高（>=0.7）/ 低（<0.4）分布；无该字段时章节跳过
- [x] ~~断言强度 AST 增强（1.3）~~ → 已实现：`_assertion_strength_proxy` 在原有 `assert` 行数统计基础上新增 AST 口径（`ast.parse` + `ast.Assert` 节点计数），输出 `ast_avg_assertions` 与 `ast_parse_failed_tasks`
- [x] ~~执行反馈轨迹收集（3.2，为 RL 微调备料）~~ → 已实现：`state.execution_trace` + `nodes._record_execution_trace` 每次 Executor 执行追加 passed / coverage_delta / elapsed / reward_signals {correctness, efficiency, simplicity}，纯观测层默认常开；`run_benchmark.py` 结果行带轨迹，`analyze_results.py` 自动汇总渲染

### 长期改进（3个月）

- [ ] 开发专属微调模型
- [x] ~~构建失败案例知识库~~ → 已实现（5.3，见上）
- [ ] 实现人机协同修复机制
- [ ] 扩展到多语言支持（跨语言泛化：当前仅 Python，可在 Java 生态的 Defects4J 上做初步适配验证）

---

## 结论

当前32%的失败率主要来自LLM响应格式问题和错误分类器覆盖不足。通过增强JSON提取鲁棒性、扩充错误模式库、启用RAG检索，预计可将失败率降低至15%以下。下一步重点改进方向：

1. **响应格式标准化**：处理LLM输出的多样性
2. **错误分类精细化**：从规则匹配升级为语义理解
3. **知识库建设**：积累失败案例和修复经验
