# 多智能体协作测试生成与自修复协议（算法设计文档）

> 本文档描述 AITester 的核心算法设计与理论框架，供论文撰写与代码审查参考。
> 附录提供算法到源码的精确映射表，便于快速定位实现细节。

---

## 附录：算法 — 代码映射表

| 算法编号 | 算法名称 | 源码位置 | 关键函数/类 |
|:--------:|---------|---------|------------|
| Algorithm 1 | 逻辑驱动测试规划 | [src/agents/planner.py](../src/agents/planner.py) | `PlannerAgent.plan()` |
| Algorithm 2 | 错误分类（规则匹配） | [src/agents/error_classifier.py](../src/agents/error_classifier.py) | `ErrorClassifier.classify()` |
| Algorithm 3 | 迭代修复循环 | [src/graph/workflow.py](../src/graph/workflow.py) | `_should_debug()` + 条件路由边 |
| Patch 应用 | 补丁写入原文件 | [src/tools/patch_applier.py](../src/tools/patch_applier.py) | `apply_patch_to_code()` |
| RAG 检索 | 向量相似检索 | [src/rag/retriever.py](../src/rag/retriever.py) | `TestCaseRetriever` |
| 批量实验 | 基准测试执行 | [experiments/run_benchmark.py](../experiments/run_benchmark.py) | `run_benchmark()` |

---

## 1. 系统概述

AITester 是一个基于多智能体协作（Multi-Agent Collaboration）的 Python 自动化测试生成与自修复系统。

系统由四个核心智能体构成，各自职责如下：

| 智能体 | 职责 | 是否调用 LLM |
|:------:|------|:------------:|
| **PlannerAgent** | 对目标函数进行逻辑分析，输出结构化测试计划 | ✅ 是 |
| **GeneratorAgent** | 根据测试计划生成可运行的 pytest 代码 | ✅ 是 |
| **ExecutorAgent** | 在隔离环境中执行测试，捕获输出与覆盖率 | ❌ 否 |
| **DebuggerAgent** | 分析失败原因，生成分层修复补丁 | ✅ 是 |

系统整体工作流为有向图（由 LangGraph 编排），支持循环修复路径及消融实验开关。

---

## 2. 逻辑驱动思维链算法（Algorithm 1）

### 2.1 问题建模

设被测函数为 $f: D_{in} \rightarrow D_{out}$，其中 $D_{in}$ 为输入定义域，$D_{out}$ 为输出值域。

**目标**：生成测试集合 $\mathcal{T} = \{t_1, t_2, \ldots, t_n\}$，使得每个 $t_i$ 对应 $f$ 的一个逻辑分支或边界条件，且 $\bigcup_i \text{coverage}(t_i) \geq \theta$（覆盖率阈值，默认 80%）。

### 2.2 算法步骤

```
Algorithm 1: Logic-Driven Test Planning
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

### 2.3 复杂度分析

- **时间复杂度**：$O(k \cdot C_{LLM})$，其中 $k=5$ 为逻辑分析维度数，$C_{LLM}$ 为单次 LLM 调用成本。
- **空间复杂度**：$O(|S| + |P|)$，存储源代码和结构化测试计划。

### 2.4 实现说明

- 代码位置：[src/agents/planner.py](../src/agents/planner.py)
- System Prompt 定义于 [src/prompts/templates.py](../src/prompts/templates.py) 的 `PLANNER_SYSTEM_PROMPT`
- 若 LLM 未返回 `logic_analysis` 字段（兼容性兜底），自动填充空值避免下游崩溃

---

## 3. 分层错误修复协议（Algorithm 2 & 3）

### 3.1 错误分类器（Algorithm 2）

定义错误类型枚举 $\mathcal{E} = \{\text{SYNTAX}, \text{RUNTIME}, \text{ASSERTION}, \text{TIMEOUT}, \text{UNKNOWN}\}$。

分类函数 $C: \text{TestOutput} \rightarrow \mathcal{E}$ 采用**规则匹配**（正则表达式），确保 $O(1)$ 分类时间且无需消耗 LLM token。

```
Algorithm 2: Error Classification（规则匹配）
Input:  测试输出文本 O，失败用例列表 F
Output: 错误类别 e ∈ E

1:  combined ← O ⊕ concat(F[*].error)    // 拼接输出文本与失败用例错误信息
2:  if matches(combined, SYNTAX_PATTERNS) then return SYNTAX
3:  if matches(combined, RUNTIME_PATTERNS) then return RUNTIME
4:  if matches(combined, ASSERTION_PATTERNS) then return ASSERTION
5:  if matches(combined, TIMEOUT_PATTERNS) then return TIMEOUT
6:  return UNKNOWN                        // 兜底类别
```

**正则模式定义**（见 [src/agents/error_classifier.py](../src/agents/error_classifier.py)）：
- `SYNTAX_PATTERNS`：SyntaxError、ImportError、ModuleNotFoundError 等编译期错误
- `RUNTIME_PATTERNS`：ZeroDivisionError、TypeError、KeyError、IndexError 等运行时异常
- `ASSERTION_PATTERNS`：AssertionError、assert 语句、Expected...but got 等
- `TIMEOUT_PATTERNS`：timeout、TimedOut、Test ran for longer than 等

### 3.2 分层修复策略

每种错误类型 $e \in \mathcal{E}$ 对应唯一的差异化修复策略 $Strat(e)$：

| 错误类型 | 修复策略 | LLM 调用方式 |
|:--------:|---------|:------------:|
| SYNTAX | 重写完整文件（语法/导入修复） | 直接输出完整文件 |
| RUNTIME | 定位异常栈，修复具体函数逻辑 | 输出修复后的完整文件 |
| ASSERTION | 判断是代码逻辑错误还是测试预期值错误 | 分情况输出修复补丁 |
| TIMEOUT | 检查循环/递归条件，添加退出逻辑 | 输出修复后的完整文件 |
| UNKNOWN | 通用分析后自主判断 | 输出修复补丁 |

### 3.3 迭代修复循环（Algorithm 3）

```
Algorithm 3: Iterative Repair Loop
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

**实现位置**：[src/graph/workflow.py](../src/graph/workflow.py) 中的 `_should_debug()` 控制路由条件。

---

## 4. 多智能体协作协议

### 4.1 状态转移图

系统状态空间 $\mathcal{S}$ 由 TypedDict `AITesterState` 定义（见 [src/graph/state.py](../src/graph/state.py)），包含以下关键字段：

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

### 4.2 消融实验配置矩阵

通过布尔开关控制节点启用/禁用，形成 4 种实验变体（配置见 [config.py](../config.py)）：

| 变体 | ENABLE_PLANNER | ENABLE_DEBUGGER | ENABLE_RAG | 对应基线 |
|:----:|:--------------:|:---------------:|:----------:|---------|
| 完整系统 | true | true | false | AITester |
| 无 Planner | false | true | false | 无规划基线 |
| 无 Debugger | true | false | false | 无修复基线 |
| 纯 LLM | false | false | false | plain_llm |
| 单智能体 | — | — | — | single_agent |

---

## 5. 理论正确性说明

### 定理 1（完整性）

若被测函数 $f$ 存在可修复的 bug，且 LLM 具备足够能力，则算法在 $K$ 次迭代内收敛到通过所有测试的状态的概率为 $p > 0$。

**证明**：每次 Debugger 调用根据错误分类提供针对性修复策略，覆盖 SYNTAX/RUNTIME/ASSERTION/TIMEOUT 四类已知模式。对于 UNKNOWN 类别，LLM 进行通用分析。由于 LLM 输出空间包含正确修复方案（假设模型能力足够），存在一条从初始状态到成功状态的路径。∎

### 定理 2（终止性）

算法保证在 $K$ 次迭代后终止，不会无限循环。

**证明**：循环上界由 `MAX_ITERATIONS`（默认 3）控制，每次迭代执行固定节点序列（Generator → Executor → Debugger → PatchApplier），不存在递归调用自身的情况。∎

---

## 6. 与现有方法的对比

| 方法 | 逻辑规划 | 分层修复 | RAG 增强 | 消融实验 |
|:---:|:-------:|:-------:|:-------:|:-------:|
| Pynguin（传统工具） | ✗ | ✗ | ✗ | ✗ |
| 直接 LLM 单次调用 | ✗ | ✗ | ✗ | ✗ |
| 单智能体系统 | ✗ | 部分 | ✗ | ✗ |
| **AITester（本系统）** | ✅ | ✅ | ✅（可选） | ✅ |

---

## 7. 数据集加载架构

```
load_dataset(name)
├── "examples" / "in_memory"   → InMemoryDataset（3 个预定义 bug 任务，无需下载）
├── "swe_bench"                → SWEBenchDataset（从 ~/.cache/aitester/swe_bench/ 读取）
│                               （支持从 HuggingFace 自动下载：download_from_huggingface()）
├── "defects4j_python"         → Defects4JPYDataset（从本地目录解析）
├── "synthetic" / "synth"      → SyntheticDataset（本地生成，支持自定义规模）
└── 其他名称                   → InMemoryDataset（graceful degrade，不崩溃）
```

每个任务统一为 `BenchmarkTask` 数据结构（定义于 [src/dataset_loader.py](../src/dataset_loader.py)）：

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
