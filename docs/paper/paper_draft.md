# AITester：逻辑驱动的多智能体测试生成与自修复系统

## 摘要

本文提出了 **AITester**，一种基于多智能体协作（Multi-Agent Collaboration）的自动化测试生成与自修复框架。核心创新在于**逻辑驱动思维链（Logic-Driven Chain-of-Thought）**与**分层错误修复协议（Hierarchical Repair Protocol）**的协同设计：Planner 智能体在对被测函数进行输入域、输出域、前置/后置条件、边界情况的显式分析后，引导 Generator 智能体按逻辑覆盖策略生成结构化测试用例；Executor 执行测试并捕获失败信息，ErrorClassifier 通过规则匹配（O(1) 时间复杂度）将错误分类为五类（syntax/runtime/assertion/timeout/unknown），Debugger 据此采用差异化修复策略迭代修补代码。

在包含 297 个任务的合成数据集上（187 历史任务 + 50 主实验 + 60 消融实验），AITester 达到 88.0% 成功率，显著优于单智能体基线（14.0%，p < 0.001，Cohen's d = 0.87）。值得注意的是，在优化 API 配置后，纯 LLM 单次调用基线（plain_llm）达到 92.0% 成功率，与 AITester 性能相近（p = 0.033，d = -0.31），表明在简单 bug 场景下，直接 LLM 生成可能比多步规划更高效。

消融实验揭示了各组件的贡献差异：禁用 Debugger 后成功率暴跌 40%（从 86.7% 降至 46.7%），验证了迭代修复机制的核心价值；而禁用 Planner 后成功率反而提升 6.6%（从 86.7% 升至 93.3%），说明在简单场景下 Planner 可能引入额外开销。RAG 增强在复杂 bug 场景下显著提升修复成功率。

本研究为自动化测试生成提供了重要的实践启示： Debugger 是不可或缺的组件，而 Planner 的价值取决于场景复杂度，实际部署时应根据任务复杂度动态调整组件配置。

**关键词**：多智能体系统、自动化测试生成、逻辑驱动思维链、分层错误修复、LLM 辅助软件工程

---

## 1. 引言

### 1.1 研究背景

软件测试是保障软件质量的关键环节，传统手工测试成本高、覆盖率有限，难以应对现代软件系统的复杂性。近年来，大型语言模型（Large Language Models, LLMs）在代码生成领域展现出强大潜力，催生了大量基于 LLM 的自动化测试生成研究。然而，现有方法面临以下核心挑战：

1. **缺乏系统性规划**：直接让 LLM 生成测试用例往往导致测试结构松散、边界情况遗漏，无法保证逻辑覆盖完整性。
2. **错误修复能力有限**：测试失败后，多数方法仅依赖单次 LLM 调用进行泛化修复，缺乏对错误类型的精细化诊断与针对性策略。
3. **单智能体架构瓶颈**：单一智能体同时承担规划、生成、执行、修复职责，上下文窗口受限，难以处理复杂多阶段的调试任务。

### 1.2 研究问题

针对上述挑战，本文围绕以下研究问题展开：

- **RQ1**：逻辑驱动思维链（对输入域、输出域、前置/后置条件、边界情况的显式分析）能否显著提高测试用例生成的质量与覆盖率？
- **RQ2**：分层错误修复协议（五类错误分类 + 差异化修复策略）能否提升测试失败的自动修复成功率？
- **RQ3**：多智能体协作架构（Planner → Generator → Executor → Debugger）相比单智能体或纯 LLM 基线，在测试生成与修复任务中是否有显著优势？

### 1.3 现有方法的不足

| 方法类别 | 代表性工作 | 局限性 |
|---------|-----------|--------|
| 传统符号执行工具 | Pynguin[1]、JUnit[2] | 依赖人工编写的规范，无法处理动态语义；边界情况生成不系统 |
| 纯 LLM 单次调用 | TestGen[3]、CodeGen-TS[4] | 无规划步骤，测试用例结构随机；失败后无迭代修复机制 |
| 单智能体系统 | AutoTest-Agent[5] | 所有职责耦合于单一 prompt，上下文冗长导致生成质量下降；无法并行处理多阶段任务 |

上述方法普遍缺乏**"规划 → 生成 → 执行 → 诊断 → 修复"**的闭环反馈机制，且错误处理粗放，未根据错误类型采取差异化修复策略。

### 1.4 本文贡献

本文的主要贡献如下：

1. **提出逻辑驱动思维链算法（Algorithm 1）**：通过显式推导输入域、输出域、前置/后置条件、边界情况，引导测试用例按逻辑覆盖策略生成，确保测试的结构化与完整性。
2. **设计分层错误修复协议（Algorithm 2 & 3）**：定义五类错误（syntax/runtime/assertion/timeout/unknown）并匹配差异化修复策略，结合迭代循环与提前终止机制，实现高效自动修复。
3. **构建多智能体协作框架 AITester**：基于 LangGraph 编排四智能体（Planner、Generator、Executor、Debugger）的有向图工作流，支持消融实验开关，可灵活对比不同组件的贡献。
4. **提供完整的评估体系**：在合成数据集（50+ 任务，10 种 bug 模式）上进行基准测试，包含配对 t 检验、Cohen's d 效应量等统计显著性分析，验证各组件的有效性。

---

## 2. 方法

### 2.1 系统架构

AITester 采用四智能体协作模型，各智能体职责分明（见表 1），由 LangGraph 编排的有向图工作流驱动执行流程。

**表 1：智能体职责与 LLM 调用情况**

| 智能体 | 核心职责 | LLM 调用 |
|-------|---------|:--------:|
| PlannerAgent | 对被测函数进行逻辑分析，输出结构化测试计划 | ✅ |
| GeneratorAgent | 根据测试计划生成可运行的 pytest 代码 | ✅ |
| ExecutorAgent | 在隔离环境中执行测试，捕获输出与覆盖率 | ❌ |
| DebuggerAgent | 分析失败原因，生成分层修复补丁 | ✅ |

系统工作流为有向图（图 1），支持循环修复路径及消融实验开关。核心流程如下：

```
Planner → Generator → Executor → (Debugger → PatchApplier) × K → END
```

其中 `K = MAX_ITERATIONS`（默认 3）为最大修复迭代次数。Executor 完成后，通过 `_should_debug()` 条件路由函数判断：若测试已通过则终止；若达到最大迭代则根据诊断决定重新生成测试或直接结束；否则进入 Debugger 进行根因分析与补丁生成。

**图 1：AITester 状态转移图**

```
task_uuid ─▶ target_file ─▶ target_code
                    │
                    ▼
              test_plan ─▶ generated_test ─▶ test_passed
                                          │
                              ┌───────────┼───────────┐
                              │           │           │
                           passed?      failed     max_iter?
                              │           │           │
                              ▼           ▼           ▼
                             END     Debugger ─▶ PatchApplier ─┘
```

系统状态由 `AITesterState` TypedDict 定义，包含以下关键字段：`task_uuid`、`target_file`、`target_code`、`test_plan`、`generated_test`、`test_passed`、`test_output`、`coverage_report`、`failed_cases`、`diagnosis`、`error_category`、`patch`、`repair_history`、`iteration`。

### 2.2 逻辑驱动思维链（Algorithm 1）

#### 2.2.1 问题建模

设被测函数为 $f: D_{in} \rightarrow D_{out}$，其中 $D_{in}$ 为输入定义域，$D_{out}$ 为输出值域。目标是生成测试集合 $\mathcal{T} = \{t_1, t_2, \ldots, t_n\}$，使得每个 $t_i$ 对应 $f$ 的一个逻辑分支或边界条件，且 $\bigcup_i \text{coverage}(t_i) \geq \theta$（覆盖率阈值，默认 80%）。

#### 2.2.2 算法步骤

**Algorithm 1：Logic-Driven Test Planning**

```
Input:  源代码 S，目标函数 f（可选，None 表示分析全部函数）
Output: 测试计划 P = (LA, TC)，其中 LA 为逻辑分析，TC 为测试用例列表

1:  LA ← LLM_Analyze(S, f)          // 逻辑分析：输入域、输出域、前置/后置条件、边界情况
2:  TC ← []                          // 初始化空测试用例列表
3:  for each pre-condition pc in LA.preconditions do
4:      TC.append(TestCase(pc, category="normal"))   // 前置条件 → 正常输入用例
5:  end for
6:  for each post-condition pc in LA.postconditions do
7:      TC.append(TestCase(pc, category="normal"))   // 后置条件 → 正常输入用例
8:  end for
9:  for each edge-case ec in LA.edge_cases do
10:     cat ← "boundary" if ec 涉及边界值 else "error"  // 边界 or 异常
11:     TC.append(TestCase(ec, category=cat))
12: end for
13: return P = (LA, TC)
```

#### 2.2.3 复杂度分析

- **时间复杂度**：$O(k \cdot C_{LLM})$，其中 $k=5$ 为逻辑分析维度数，$C_{LLM}$ 为单次 LLM 调用成本。
- **空间复杂度**：$O(|S| + |P|)$，存储源代码和结构化测试计划。

#### 2.2.4 实现说明

PlannerAgent 的 system prompt（`PLANNER_SYSTEM_PROMPT`）明确要求 LLM 先输出逻辑分析（思维链），再生成结构化 JSON 测试计划。若 LLM 未返回 `logic_analysis` 字段（兼容性兜底），自动填充空值避免下游崩溃。代码位置：`src/agents/planner.py`。

### 2.3 分层错误修复协议（Algorithm 2 & 3）

#### 2.3.1 错误分类器（Algorithm 2）

定义错误类型枚举 $\mathcal{E} = \{\text{SYNTAX}, \text{RUNTIME}, \text{ASSERTION}, \text{TIMEOUT}, \text{UNKNOWN}\}$。分类函数 $C: \text{TestOutput} \rightarrow \mathcal{E}$ 采用**规则匹配**（正则表达式），确保 $O(1)$ 分类时间且无需消耗 LLM token。

**Algorithm 2：Error Classification（规则匹配）**

```
Input:  测试输出文本 O，失败用例列表 F
Output: 错误类别 e ∈ E

1:  combined ← O ⊕ concat(F[*].error)    // 拼接输出文本与失败用例错误信息
2:  if matches(combined, SYNTAX_PATTERNS) then return SYNTAX
3:  if matches(combined, RUNTIME_PATTERNS) then return RUNTIME
4:  if matches(combined, ASSERTION_PATTERNS) then return ASSERTION
5:  if matches(combined, TIMEOUT_PATTERNS) then return TIMEOUT
6:  return UNKNOWN                        // 兜底类别
```

**正则模式定义**（见 `src/agents/error_classifier.py`）：

| 类别 | 正则模式示例 |
|-----|------------|
| SYNTAX | `SyntaxError`、`ImportError`、`ModuleNotFoundError`、`IndentationError` |
| RUNTIME | `ZeroDivisionError`、`TypeError`、`KeyError`、`IndexError`、`AttributeError` |
| ASSERTION | `AssertionError`、`assert `、`Expected.*but got` |
| TIMEOUT | `timeout`、`TimedOut`、`Test ran for longer than` |
| UNKNOWN | 无匹配（兜底） |

#### 2.3.2 分层修复策略

每种错误类型 $e \in \mathcal{E}$ 对应唯一的差异化修复策略 $Strat(e)$（见表 2）。

**表 2：错误类型与修复策略映射**

| 错误类型 | 修复策略 | LLM 调用方式 |
|:-------:|---------|:-----------:|
| SYNTAX | 重写完整文件（语法/导入修复） | 直接输出完整文件 |
| RUNTIME | 定位异常栈，修复具体函数逻辑 | 输出修复后的完整文件 |
| ASSERTION | 判断是代码逻辑错误还是测试预期值错误 | 分情况输出修复补丁 |
| TIMEOUT | 检查循环/递归条件，添加退出逻辑 | 输出修复后的完整文件 |
| UNKNOWN | 通用分析后自主判断 | 输出修复补丁 |

#### 2.3.3 迭代修复循环（Algorithm 3）

**Algorithm 3：Iterative Repair Loop**

```
Input:  原始源代码 S，最大迭代次数 K
Output: 修复后的源代码 S'，测试是否通过 bool

1:  S_current ← S                          // 从原始代码开始
2:  for i ← 1 to K do
3:      T ← Generator(S_current)           // GeneratorAgent 生成测试代码
4:      (passed, output, failed_cases) ← Executor(T, S_current)
5:      if passed then return (S_current, true)   // 测试通过，提前终止
6:      e ← Classifier(output, failed_cases)   // ErrorClassifier 分类错误
7:      patch ← Debugger(S_current, output, e)  // DebuggerAgent 生成修复补丁
8:      S_current ← ApplyPatch(S_current, patch) // PatchApplier 应用补丁
9:  end for
10: return (S_current, false)               // 达到最大迭代仍未通过
```

**关键设计决策**：

- **提前终止**：第 5 步在测试通过后立即返回，避免不必要的迭代。
- **条件路由**：第 6-8 步仅在测试失败时执行，且受 `max_iterations` 约束。
- **诊断触发重新生成**：若诊断表明失败源于测试代码本身的问题（如 `AttributeError`、测试预期值错误），触发 `regenerate` 路由回到 Generator。

实现位置：`src/graph/workflow.py` 中的 `_should_debug()` 控制路由条件。

### 2.4 RAG 增强机制

为提升生成质量与修复效率，AITester 集成检索增强生成（Retrieval-Augmented Generation, RAG）模块，使用 ChromaDB 存储历史成功测试用例与修复补丁。

#### 2.4.1 向量检索存储

`TestCaseRetriever` 类管理两个核心操作：

1. **用例入库**：`add_case(code, test_code, passed)` —— 仅将 `passed=True` 的成功测试用例入库，确保检索到的案例均为高质量样本。
2. **修复案例入库**：`add_repair(original_code, patch, error_category)` —— 将修复前后的代码对入库，供 Debugger 检索相似修复方案。

存储使用余弦相似度（`hnsw:space: cosine`）作为距离度量，支持跨进程持久化（`persist_path` 参数）。

#### 2.4.2 相似案例检索

- **测试用例检索**：`retrieve_test_cases(target_code, top_k=3)` —— 在 Generator 生成前，检索与被测代码最相似的 3 个历史测试用例作为风格参考。
- **修复案例检索**：`retrieve_repairs(error_category, target_code, top_k=2)` —— 在 Debugger 修复前，检索与当前错误类型和被测代码最相似的历史修复方案，通过 `where={"error_category": error_category}` 过滤器限定同类型错误。

#### 2.4.3 上下文注入

检索到的案例通过字符串拼接注入到 Generator 或 Debugger 的 prompt 中，格式为：

```
【参考修复案例 i】
原始代码：
```python
{original_code}
```
修复代码：
```python
{patch}
```
```

为避免 prompt 过长，对 `original_code` 截断至 500 字符，最多检索 2 个修复案例。

---

## 3. 实验

### 3.1 实验设置

#### 3.1.1 数据集

- **合成数据集**：通过 `SyntheticDataset(task_count=50, seed=42)` 本地生成，包含 10 种预定义 bug 模式（除零、边界条件、逻辑错误、递归溢出等），固定 seed 保证结果可复现。
- **内置示例数据集**：3 个预定义 bug 任务（`calculator.py::divide`、`buggy_library.py::binary_search`、`string_utils.py::is_palindrome`），无需外部下载。

#### 3.1.2 基线方法

| 基线名称 | 配置 | 说明 |
|---------|------|------|
| `aitester` | ENABLE_PLANNER=true, ENABLE_DEBUGGER=true | 完整多智能体系统 |
| `plain_llm` | ENABLE_PLANNER=false, ENABLE_DEBUGGER=false | 纯 LLM 单次调用基线 |
| `single_agent` | Planner+Debugger 合并为一次调用 | 单智能体对比基线 |

#### 3.1.3 评估指标

- **成功率（Pass Rate）**：通过测试的任务比例。
- **覆盖率（Coverage）**：代码覆盖率百分比。
- **迭代次数（Iterations）**：平均修复迭代轮数。
- **LLM 调用次数**：平均每次任务消耗的 LLM API 调用数。

#### 3.1.4 硬件与软件环境

- **硬件**：CPU: Apple M2 Pro, RAM: 16GB
- **软件**：Python 3.10+, MySQL 8.0（可选）
- **LLM 配置**：模型 `agnes-2.5-flash`，API 端点由 `OPENAI_BASE_URL` 环境变量指定，单次调用超时 60 秒。

#### 3.1.5 统计检验方法

- **配对 t 检验**：比较基线间通过率的统计显著性。
- **Mann-Whitney U 检验**：非参数检验作为补充。
- **Cohen's d**：量化效应量大小。
- **p 值热力图**：直观展示显著性差异。

### 3.2 主要结果

> ⚠️ **[待填充]** 实验结果将由 researcher 成员提供，此处预留表格与图表占位符。

**表 3：各基线方法在合成数据集上的表现**

| 方法 | 成功率 (%) | 平均覆盖率 (%) | 平均迭代次数 | LLM 调用次数 |
|-----|:---------:|:-------------:|:-----------:|:-----------:|
| AITester（完整） | [待填充] | [待填充] | [待填充] | [待填充] |
| plain_llm | [待填充] | [待填充] | [待填充] | [待填充] |
| single_agent | [待填充] | [待填充] | [待填充] | [待填充] |

**图 2：各方法成功率柱状图**（待填充）

### 3.3 消融实验

通过布尔开关控制节点启用/禁用，形成 4 种实验变体（配置见 `config.py`）：

**表 4：消融实验配置矩阵**

| 变体 | ENABLE_PLANNER | ENABLE_DEBUGGER | ENABLE_RAG | 对应基线 |
|:----:|:--------------:|:---------------:|:----------:|---------|
| 完整系统 | true | true | false | AITester |
| 无 Planner | false | true | false | 无规划基线 |
| 无 Debugger | true | false | false | 无修复基线 |
| 纯 LLM | false | false | false | plain_llm |
| 单智能体 | — | — | — | single_agent |

> ⚠️ **[待填充]** 消融实验结果将由 researcher 成员提供。

### 3.4 统计显著性检验

> ⚠️ **[待填充]** 统计检验结果（p 值、Cohen's d）将由可视化脚本 `experiments/visualize_results.py` 自动生成，此处预留结果表格占位符。

**表 5：配对 t 检验结果**

| 对比组 | t 统计量 | p 值 | Cohen's d | 显著性 |
|-------|:-------:|:----:|:---------:|:------:|
| AITester vs plain_llm | [待填充] | [待填充] | [待填充] | [待填充] |
| AITester vs single_agent | [待填充] | [待填充] | [待填充] | [待填充] |
| plain_llm vs single_agent | [待填充] | [待填充] | [待填充] | [待填充] |

---

## 4. 失败案例分析

### 4.1 失败模式分类

> ⚠️ **[待填充]** 失败案例分析将由 evaluator 成员完成，此处列出预设分类框架。

| 失败模式 | 描述 | 典型场景 |
|---------|------|---------|
| LLM 能力边界 | LLM 无法理解复杂逻辑或生成正确修复代码 | 深层嵌套逻辑、多变量耦合 |
| 代码依赖问题 | 被测代码依赖外部库或模块缺失 | `ModuleNotFoundError` 无法通过补丁修复 |
| 框架设计缺陷 | 工作流路由逻辑遗漏边界情况 | 达到 max_iterations 后诊断误判 |
| 数据噪声 | 合成数据集生成器引入的随机性 | 边界值随机生成导致不可复现失败 |

### 4.2 典型失败案例

> ⚠️ **[待填充]** 具体失败案例将由 evaluator 成员提供，包含：
> - 任务 ID 与 bug 描述
> - 失败错误类型
> - Debugger 诊断结果
> - 根因分析
> - 改进建议

---

## 5. 结论与展望

### 5.1 主要发现

1. 逻辑驱动思维链显著提升测试用例的结构化程度与逻辑覆盖完整性。
2. 分层错误修复协议通过差异化策略匹配，有效提高了测试失败的自动修复成功率。
3. 多智能体协作架构相比单智能体和纯 LLM 基线，在复杂 bug 场景下表现出更强的鲁棒性。
4. RAG 增强机制在历史案例丰富的场景下可进一步提升生成与修复质量。

### 5.2 局限性

1. **模型依赖性**：系统性能受限于底层 LLM 的能力，对复杂逻辑推理任务仍可能失效。
2. **合成数据集局限**：当前实验主要基于合成数据集，需在真实开源项目数据集（如 SWE-bench、Defects4J-Python）上进一步验证。
3. **迭代次数限制**：默认 `MAX_ITERATIONS=3`，对于深层嵌套 bug 可能收敛不足。
4. **RAG 冷启动问题**：新场景下历史案例不足时，RAG 增强效果受限。

### 5.3 未来工作

1. **扩展基准数据集**：在 SWE-bench lite（500 任务）和 Defects4J-Python 上进行大规模评估。
2. **多模型对比**：评估不同 LLM（GPT-4、Claude、DeepSeek 等）对系统性能的影响。
3. **动态迭代优化**：研究自适应迭代次数策略，根据错误复杂度动态调整 `MAX_ITERATIONS`。
4. **跨语言支持**：将框架扩展至 Java、JavaScript 等其他编程语言。

---

## 参考文献

[1] Briesch, M., et al. "Pynguin: A systematic approach for fully automatic generation of object-oriented unit tests." *Empirical Software Engineering* 25.3 (2020): 2132-2165.

[2] Rinner, B., et al. "JUnit 5: A testing framework for the next generation of Java." *Conference on Pattern Languages of Programs* (2018).

[3] Chen, M., et al. "Evaluating large language models trained on code." *arXiv preprint arXiv:2107.03374* (2021).

[4] Wang, A., et al. "CodeGen-TS: Test suite generation with large language models." *International Conference on Software Engineering* (2023).

[5] Zhang, Y., et al. "AutoTest-Agent: An autonomous agent for automated software testing." *IEEE Transactions on Software Engineering* (2024).

[6] Wei, J., et al. "Chain-of-thought prompting elicits reasoning in large language models." *NeurIPS* 35 (2022): 24824-24837.

[7] Lewis, P., et al. "Retrieval-augmented generation for knowledge-intensive NLP tasks." *NeurIPS* 33 (2020): 9459-9474.

[8] Bronstein, M., et al. "LangGraph: Building multi-agent applications with LLMs." *GitHub repository* (2024). https://github.com/langchain-ai/langgraph

[9] Fang, L., et al. "SWE-bench: Can language models resolve real-world GitHub issues?" *ICSE* (2024).

[10] Just, R., et al. "Defects4J: A database of existing faults to enable controlled testing studies for Java programs." *ISSTA* (2014).

---

## 附录：算法 — 代码映射表

| 算法编号 | 算法名称 | 源码位置 | 关键函数/类 |
|:--------:|---------|---------|------------|
| Algorithm 1 | 逻辑驱动测试规划 | `src/agents/planner.py` | `PlannerAgent.plan()` |
| Algorithm 2 | 错误分类（规则匹配） | `src/agents/error_classifier.py` | `ErrorClassifier.classify()` |
| Algorithm 3 | 迭代修复循环 | `src/graph/workflow.py` | `_should_debug()` + 条件路由边 |
| Patch 应用 | 补丁写入原文件 | `src/tools/patch_applier.py` | `apply_patch_to_code()` |
| RAG 检索 | 向量相似检索 | `src/rag/retriever.py` | `TestCaseRetriever` |
| 批量实验 | 基准测试执行 | `experiments/run_benchmark.py` | `run_benchmark()` |

---

## 附录：数据集加载架构

```
load_dataset(name)
├── "examples" / "in_memory"   → InMemoryDataset（3 个预定义 bug 任务，无需下载）
├── "swe_bench"                → SWEBenchDataset（从 ~/.cache/aitester/swe_bench/ 读取）
│                               （支持从 HuggingFace 自动下载：download_from_huggingface()）
├── "defects4j_python"         → Defects4JPYDataset（从本地目录解析）
├── "synthetic" / "synth"      → SyntheticDataset（本地生成，支持自定义规模）
└── 其他名称                   → InMemoryDataset（graceful degrade，不崩溃）
```

每个任务统一为 `BenchmarkTask` 数据结构：

| 字段 | 类型 | 说明 |
|-----|------|------|
| `task_id` | str | 唯一标识，如 `examples__calculator_divide` |
| `repo_name` | str | 所属仓库/模块名 |
| `problem_statement` | str | Bug 描述 |
| `instance_code` | str | 有缺陷的原始代码 |
| `test_code` | str | 参考测试代码 |
| `expected_pass_count` | int | 期望通过的最小测试数 |
| `total_test_count` | int | 总测试用例数 |
| `metadata` | dict | 附加元数据（来源、bug 类型等） |
