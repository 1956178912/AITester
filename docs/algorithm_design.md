# 多智能体协作测试生成与自修复协议

> 本文档描述 AITester 的核心算法设计与理论框架，供论文撰写参考。

---

## 1. 系统概述

AITester 是一个基于多智能体协作（Multi-Agent Collaboration）的 Python 自动化测试生成与自修复系统。系统由四个核心智能体构成：

| 智能体 | 职责 | 是否使用 LLM |
|--------|------|:---:|
| PlannerAgent | 逻辑分析与测试规划 | 是 |
| GeneratorAgent | 测试代码生成 | 是 |
| ExecutorAgent | 测试执行与结果解析 | 否 |
| DebuggerAgent | 失败诊断与代码修复 | 是 |

系统工作流为有向无环图（DAG），支持循环修复路径和消融实验开关。

---

## 2. 逻辑驱动思维链算法（Logic-driven Chain-of-Thought）

### 2.1 问题建模

设被测函数为 $f: D_{in} \rightarrow D_{out}$，其中 $D_{in}$ 为输入定义域，$D_{out}$ 为输出值域。

**目标**：生成测试集合 $\mathcal{T} = \{t_1, t_2, \ldots, t_n\}$，使得每个 $t_i$ 对应 $f$ 的一个逻辑分支或边界条件，且 $\bigcup_i \text{coverage}(t_i) \geq \theta$（覆盖率阈值）。

### 2.2 算法步骤

```
Algorithm 1: Logic-Driven Test Planning
Input:  source code S, target function f
Output: test plan P = (LA, TC)

1:  LA ← LLM_Analyze(S, f)          // 逻辑分析：输入域、输出域、前置/后置条件、边界
2:  TC ← []
3:  for each pre-condition pc in LA.preconditions do
4:      TC.append(TestCase(pc, "normal"))
5:  end for
6:  for each post-condition pc in LA.postconditions do
7:      TC.append(TestCase(pc, "normal"))
8:  end for
9:  for each edge-case ec in LA.edge_cases do
10:     TC.append(TestCase(ec, "boundary" or "error"))
11: end for
12: return P = (LA, TC)
```

### 2.3 复杂度分析

- **时间复杂度**：$O(k \cdot C_{LLM})$，其中 $k$ 为逻辑分析维度数（通常 5），$C_{LLM}$ 为单次 LLM 调用成本。
- **空间复杂度**：$O(|S| + |P|)$，存储源代码和测试计划。

---

## 3. 分层错误修复协议（Hierarchical Repair Protocol）

### 3.1 错误分类器

定义错误类型枚举 $\mathcal{E} = \{\text{SYNTAX}, \text{RUNTIME}, \text{ASSERTION}, \text{TIMEOUT}, \text{UNKNOWN}\}$。

分类函数 $C: \text{TestOutput} \rightarrow \mathcal{E}$ 采用规则匹配（正则表达式），确保 $O(1)$ 分类时间且无需 LLM 调用。

```
Algorithm 2: Error Classification
Input:  test output text O, failed cases F
Output: error category e ∈ E

1:  combined ← O ⊕ concat(F.error)     // 拼接输出文本
2:  if matches(combined, SYNTAX_PATTERNS) then return SYNTAX
3:  if matches(combined, RUNTIME_PATTERNS) then return RUNTIME
4:  if matches(combined, ASSERTION_PATTERNS) then return ASSERTION
5:  if matches(combined, TIMEOUT_PATTERNS) then return TIMEOUT
6:  return UNKNOWN
```

### 3.2 分层修复策略

每种错误类型对应唯一的修复策略 $Strat(e)$：

| 错误类型 | 修复策略 | 是否调用 LLM |
|---------|---------|:---:|
| SYNTAX | 重写完整文件（语法修复） | 是 |
| RUNTIME | 定位异常源，修复函数逻辑 | 是 |
| ASSERTION | 判断代码/测试责任，分别修复 | 是 |
| TIMEOUT | 检查循环条件，添加退出逻辑 | 是 |
| UNKNOWN | 通用分析后修复 | 是 |

### 3.3 修复循环算法

```
Algorithm 3: Iterative Repair Loop
Input:  source S, test plan P, max iterations K
Output: fixed source S', test_passed bool

1:  S_current ← S
2:  for i ← 1 to K do
3:      T ← Generator(S_current, P)        // 生成测试
4:      (passed, output, failed) ← Execute(T, S_current)
5:      if passed then return (S_current, true)
6:      e ← Classify(output, failed)       // 错误分类
7:      patch ← Debugger(S_current, output, e)  // 生成修复
8:      S_current ← ApplyPatch(S_current, patch)
9:  end for
10: return (S_current, false)              // 达到最大迭代
```

---

## 4. 多智能体协作协议

### 4.1 状态转移图

系统状态空间 $\mathcal{S}$ 包含字段集合 $\{task\_uuid, target\_code, test\_plan, generated\_test, test\_passed, \ldots\}$。

转移函数 $T: \mathcal{S} \rightarrow \mathcal{S}$ 定义如下：

```
Planner  →  Generator  →  Executor
                          ↓
                    ┌─────┴─────┐
                    │  passed?  │
                    └─────┬─────┘
                   yes ↓   ↓ no
                    END    Debugger → PatchApplier → Executor (loop)
```

### 4.2 消融实验配置矩阵

通过布尔开关控制节点启用/禁用，形成 4 种实验变体：

| 变体 | ENABLE_PLANNER | ENABLE_DEBUGGER | 对应基线 |
|-----|:---:|:---:|---------|
| 完整系统 | true | true | AITester |
| 无 Planner | false | true | 无规划基线 |
| 无 Debugger | true | false | 无修复基线 |
| 纯 LLM | false | false | 单步生成基线 |

---

## 5. 理论正确性说明

### 定理 1（完整性）
若被测函数 $f$ 存在可修复的 bug，且 LLM 具备足够能力，则算法在 $K$ 次迭代内收敛到通过所有测试的状态的概率为 $p > 0$。

**证明**：每次 Debugger 调用根据错误分类提供针对性的修复策略，覆盖了 SYNTAX/RUNTIME/ASSERTION/TIMEOUT 四类已知错误模式。对于未知错误（UNKNOWN），LLM 进行通用分析。由于 LLM 输出空间包含正确的修复方案（假设模型能力足够），存在一条从初始状态到成功状态的路径。∎

### 定理 2（终止性）
算法保证在 $K$ 次迭代后终止。

**证明**：循环上界为 $K = \text{MAX\_ITERATIONS}$，每次迭代执行固定节点序列，不存在无限递归。∎

---

## 6. 与现有方法的对比

| 方法 | 逻辑规划 | 分层修复 | RAG增强 | 消融实验 |
|-----|:---:|:---:|:---:|:---:|
| Pynguin (传统工具) | ✗ | ✗ | ✗ | ✗ |
| 直接 LLM 调用 | ✗ | ✗ | ✗ | ✗ |
| 单智能体系统 | ✗ | 部分 | ✗ | ✗ |
| **AITester (本系统)** | ✓ | ✓ | ✓ | ✓ |

---

## 7. 消融实验配置矩阵（实现版）

通过 `config.py` 中的布尔开关控制节点启用/禁用，形成 4 种实验变体：

| 变体 | ENABLE_PLANNER | ENABLE_DEBUGGER | ENABLE_RAG | 对应基线脚本 |
|-----|:---:|:---:|:---:|-------------|
| 完整系统 | true | true | false | `run_benchmark.py --baselines aitester` |
| 无 Planner | false | true | false | `ENABLE_PLANNER=false run_benchmark.py` |
| 无 Debugger | true | false | false | `ENABLE_DEBUGGER=false run_benchmark.py` |
| 纯 LLM | false | false | false | `run_benchmark.py --baselines plain_llm` |
| 单智能体 | — | — | — | `run_benchmark.py --baselines single_agent` |

各变体的结果通过 `experiments/run_benchmark.py` 自动保存至 `experiments/results/benchmark_<dataset>_<timestamp>.json`，包含每个任务的详细指标（passed、coverage、iterations、elapsed_seconds）。

---

## 8. 数据集加载架构

```
load_dataset(name)
├── "examples" / "in_memory"  → InMemoryDataset（3 个预定义 bug 任务）
├── "swe_bench"               → SWEBenchDataset（从 ~/.cache/aitester/swe_bench/ 读取）
├── "defects4j_python"        → Defects4JPYDataset（从 ~/.cache/aitester/defects4j_python/ 读取）
└── 未知名称                  → InMemoryDataset（graceful degrade）
```

每个任务统一为 `BenchmarkTask` 数据结构：
- `task_id`: 唯一标识（如 `examples__calculator_divide`）
- `repo_name`: 所属仓库（如 `examples/calculator`）
- `instance_code`: 被测源代码（字符串）
- `test_code`: 参考测试代码（字符串）
- `expected_pass_count` / `total_test_count`: 期望通过数 / 总用例数
- `metadata`: 附加元数据（来源、issue 链接等）

