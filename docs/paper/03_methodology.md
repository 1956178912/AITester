# 3. 方法论

## 3.1 系统架构

AITester 采用四智能体协作架构，整体工作流由 LangGraph 编排（图 1）。四个核心智能体分别为：

| 智能体 | 职责 | LLM 调用 |
|:------:|------|:--------:|
| PlannerAgent | 逻辑分析，生成结构化测试计划 | 是 |
| GeneratorAgent | 根据计划生成 pytest 测试代码 | 是 |
| ExecutorAgent | 隔离执行测试，捕获输出与覆盖率 | 否 |
| DebuggerAgent | 分析失败原因，生成分层修复补丁 | 是 |

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Planner    │───▶│  Generator  │───▶│  Executor   │───▶│  Debugger   │
│  (LLM)      │    │  (LLM)      │    │  (规则)     │    │  (LLM)      │
└─────────────┘    └─────────────┘    └─────────────┘    └──────┬───────┘
                                                                │
                          ┌─────────────────────────────────────┘
                          ▼
                    ┌─────────────┐
                    │ PatchApplier │──▶ Executor (loop ≤ K)
                    └─────────────┘
```

**图 1：AITester 四智能体协作架构**

系统状态由 TypedDict `AITesterState` 统一定义（见 [src/graph/state.py](../src/graph/state.py)），包含 `task_uuid`、`target_code`、`test_plan`、`generated_test`、`test_passed` 等关键字段，确保各智能体间状态传递的一致性与可追踪性。

## 3.2 逻辑驱动思维链（Algorithm 1）

### 3.2.1 问题建模

设被测函数为 $f: D_{in} \rightarrow D_{out}$，其中 $D_{in}$ 为输入定义域，$D_{out}$ 为输出值域。目标为生成测试集合 $\mathcal{T} = \{t_1, t_2, \ldots, t_n\}$，使得每个 $t_i$ 对应 $f$ 的一个逻辑分支或边界条件，且 $\bigcup_i \text{coverage}(t_i) \geq \theta$（覆盖率阈值，默认 80%）。

### 3.2.2 算法步骤

**Algorithm 1: 逻辑驱动测试规划**

```
输入：源代码 S，目标函数 f（可选，None 表示分析全部函数）
输出：测试计划 P = (LA, TC)

1: LA ← LLM_Analyze(S, f)          // 逻辑分析：输入域、输出域、前置/后置条件、边界情况
2: TC ← []                          // 初始化空测试用例列表
3: for each pre-condition pc in LA.preconditions do
4:     TC.append(TestCase(pc, category="normal"))
5: end for
6: for each post-condition pc in LA.postconditions do
7:     TC.append(TestCase(pc, category="normal"))
8: end for
9: for each edge-case ec in LA.edge_cases do
10:    cat ← "boundary" if ec 涉及边界值 else "error"
11:    TC.append(TestCase(ec, category=cat))
12: end for
13: return P = (LA, TC)
```

逻辑分析维度 $k=5$（输入域、输出域、前置条件、后置条件、边界情况），时间复杂度为 $O(k \cdot C_{\text{LLM}})$，其中 $C_{\text{LLM}}$ 为单次 LLM 调用成本。

### 3.2.3 实现细节

Planner 的 System Prompt 定义于 [src/prompts/templates.py](../src/prompts/templates.py) 的 `PLANNER_SYSTEM_PROMPT`，强制要求输出 JSON 格式的结构化计划，包含 `logic_analysis` 和 `test_cases` 两个字段。若 LLM 未返回 `logic_analysis` 字段（兼容性兜底），系统自动填充空值避免下游崩溃。

## 3.3 分层错误修复协议（Algorithm 2 & 3）

### 3.3.1 错误分类器（Algorithm 2）

定义错误类型枚举 $\mathcal{E} = \{\text{SYNTAX}, \text{RUNTIME}, \text{ASSERTION}, \text{TIMEOUT}, \text{UNKNOWN}\}$。

分类函数 $C: \text{TestOutput} \rightarrow \mathcal{E}$ 采用**规则匹配**（正则表达式），确保 $O(1)$ 分类时间且无需消耗 LLM token。

**Algorithm 2: 错误分类（规则匹配）**

```
输入：测试输出文本 O，失败用例列表 F
输出：错误类别 e ∈ E

1: combined ← O ⊕ concat(F[*].error)
2: if matches(combined, SYNTAX_PATTERNS) then return SYNTAX
3: if matches(combined, RUNTIME_PATTERNS) then return RUNTIME
4: if matches(combined, ASSERTION_PATTERNS) then return ASSERTION
5: if matches(combined, TIMEOUT_PATTERNS) then return TIMEOUT
6: return UNKNOWN
```

正则模式定义见 [src/agents/error_classifier.py](../src/agents/error_classifier.py)：
- `SYNTAX_PATTERNS`：SyntaxError、ImportError、ModuleNotFoundError 等编译期错误
- `RUNTIME_PATTERNS`：ZeroDivisionError、TypeError、KeyError、IndexError 等运行时异常
- `ASSERTION_PATTERNS`：AssertionError、assert 语句、Expected...but got 等
- `TIMEOUT_PATTERNS`：timeout、TimedOut、Test ran for longer than 等

### 3.3.2 分层修复策略

| 错误类型 | 修复策略 | LLM 调用方式 |
|:--------:|---------|:------------:|
| SYNTAX | 重写完整文件（语法/导入修复） | 直接输出完整文件 |
| RUNTIME | 定位异常栈，修复具体函数逻辑 | 输出修复后的完整文件 |
| ASSERTION | 判断代码逻辑错误还是测试预期值错误 | 分情况输出修复补丁 |
| TIMEOUT | 检查循环/递归条件，添加退出逻辑 | 输出修复后的完整文件 |
| UNKNOWN | 通用分析后自主判断 | 输出修复补丁 |

### 3.3.3 迭代修复循环（Algorithm 3）

**Algorithm 3: 迭代修复循环**

```
输入：原始源代码 S，最大迭代次数 K
输出：修复后的源代码 S'，测试是否通过 bool

1: S_current ← S
2: for i ← 1 to K do
3:     T ← Generator(S_current)
4:     (passed, output, failed_cases) ← Executor(T, S_current)
5:     if passed then return (S_current, true)
6:     e ← Classifier(output, failed_cases)
7:     patch ← Debugger(S_current, output, e)
8:     S_current ← ApplyPatch(S_current, patch)
9: end for
10: return (S_current, false)
```

循环上界由 `MAX_ITERATIONS`（默认 3）控制，保证算法终止性。修复节点的路由条件定义于 [src/graph/workflow.py](../src/graph/workflow.py) 的 `_should_debug()` 函数。

## 3.4 消融实验配置矩阵

通过布尔开关控制节点启用/禁用，形成四种实验变体（配置见 [config.py](../config.py)）：

| 变体 | ENABLE_PLANNER | ENABLE_DEBUGGER | ENABLE_RAG | 对应基线 |
|:----:|:--------------:|:---------------:|:----------:|---------|
| 完整系统 | true | true | false | AITester |
| 无 Planner | false | true | false | 无规划基线 |
| 无 Debugger | true | false | false | 无修复基线 |
| 纯 LLM | false | false | false | plain_llm |
| 单智能体 | — | — | — | single_agent |

## 3.5 检索增强生成（RAG）

使用 ChromaDB 存储历史成功测试用例与修复补丁。Generator 生成前检索相似历史测试用例作为风格参考（top-k=3）；Debugger 修复前检索相似历史修复案例作为策略参考（top-k=2）。仅当 `ENABLE_RAG=true` 时启用，默认关闭以保证实验基线公平。详见 [src/rag/retriever.py](../src/rag/retriever.py)。
