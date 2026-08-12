# AITester：逻辑驱动的多智能体测试生成与自修复框架

## 算法形式化描述

### 定义 1（状态空间）
令 $S$ 为工作流状态空间，每个状态 $s \in S$ 是一个元组：
$$s = \langle f, c, p, t, \sigma, i, h \rangle$$
其中：
- $f$：被测代码文件路径
- $c$：被测代码文本
- $p$：测试计划（含逻辑分析）
- $t$：生成的测试代码
- $\sigma$：测试执行结果（pass/fail）
- $i$：当前迭代次数
- $h$：修复历史列表

### 定义 2（状态转移函数）
工作流定义了一个马尔可夫决策过程，状态转移函数 $F: S \times A \rightarrow S$：

$$s_{t+1} = F(s_t, a_t)$$

其中动作空间 $A = \{a_{plan}, a_{gen}, a_{exec}, a_{debug}\}$ 对应四个智能体节点：

#### 转移规则：
1. **规划转移**：$s' = F(s, a_{plan})$
   $$p = \text{Planner}(c, f) = \text{LogicAnalysis}(c, f) \rightarrow \text{TestPlan}(c, f)$$
   其中 $\text{LogicAnalysis}$ 显式输出输入域、输出域、前置/后置条件、边界情况。

2. **生成转移**：$s' = F(s, a_{gen})$
   $$t = \text{Generator}(p, c)$$
   Generator 依据逻辑分析结果 $p$ 生成 pytest 测试代码 $t$。

3. **执行转移**：$s' = F(s, a_{exec})$
   $$\sigma = \text{Executor}(t, c), \quad r = \text{Coverage}(t, c)$$
   Executor 运行测试并返回通过状态 $\sigma$ 和覆盖率 $r$。

4. **调试转移**：若 $\sigma = \text{fail}$ 且 $i < i_{max}$：
   $$\langle d, e, patch \rangle = \text{Debugger}(c, \sigma, h, e_{cat})$$
   其中 $e_{cat} = \text{Classify}(\sigma) \in \{\text{syntax, assertion, runtime, timeout, unknown}\}$

#### 终止条件：
$$\text{Stop}(s) = (\sigma = \text{pass}) \lor (i \geq i_{max})$$

### 定义 3（测试计划数据结构）
测试计划 $p$ 的结构化表示：
```
p = {
  function_name: str,
  description: str,
  logic_analysis: {
    input_domain: str,      // 输入参数域
    output_domain: str,     // 输出值域
    preconditions: List[str], // 前置条件
    postconditions: List[str],// 后置条件
    edge_cases: List[str]    // 边界情况
  },
  test_cases: List<{
    case_name: str,
    input_args: Dict[str, Any],
    expected_output: str,
    category: "normal" | "boundary" | "error",
    logic_coverage: str     // 对应逻辑分析中的条件编号
  }>
}
```

### 定义 4（分层错误修复策略）
定义错误类型映射函数 $E: \Sigma \rightarrow \mathcal{E}$，其中 $\mathcal{E} = \{e_s, e_a, e_r, e_t, e_u\}$：
- $e_s$（语法错误）：策略 $Strat(e_s) =$ "重新生成完整代码文件"
- $e_r$（运行时异常）：策略 $Strat(e_r) =$ "分析异常栈，定位 bug 函数"
- $e_a$（断言失败）：策略 $Strat(e_a) =$ "判断代码/测试预期值错误"
- $e_t$（超时）：策略 $Strat(e_t) =$ "检查循环/递归终止条件"
- $e_u$（未知）：策略 $Strat(e_u) =$ "通用分析"

### 算法伪代码

```
Algorithm 1: AITester Workflow
Input:  target_file f, target_function name (optional)
Output: test_passed bool, coverage float

1:  c ← ReadFile(f)                                    // 读取被测代码
2:  state ← InitializeState(f, c, name)                // 初始化状态
3:  while NOT state.test_passed AND state.iteration < MAX do
4:      // Phase 1: Logic-driven Planning
5:      plan ← Planner.Plan(c, name)
6:      state.test_plan ← plan
7:      
8:      // Phase 2: Test Generation
9:      test_code ← Generator.Generate(plan, c)
10:     state.generated_test ← test_code
11:     
12:     // Phase 3: Execution
13:     result ← Executor.Execute(test_code, f, name)
14:     state.test_passed ← result.passed
15:     state.test_output ← result.output
16:     state.coverage_report ← result.coverage
17:     state.failed_cases ← result.failed_cases
18:     
19:     if state.test_passed then
20:         break                                      // 测试通过，终止
21:     fi
22:     
22:     // Phase 4: Hierarchical Debugging
23:     error_cat ← Classifier.Classify(result.output, result.failed_cases)
24:     fix_strat ← GetFixStrategy(error_cat)
25:     debug_result ← Debugger.Debug(c, result.output, result.failed_cases, error_cat, fix_strat)
26:     state.diagnosis ← debug_result.root_cause
27:     state.error_category ← error_cat
28:     state.patch ← debug_result.patch
29:     
30:     // Phase 5: Patch Application
31:     new_code, applied ← PatchApplier.Apply(c, debug_result.patch)
32:     if applied then
33:         WriteFile(f, new_code)
34:         state.target_code ← new_code
35:     fi
36:     state.repair_history.append({iteration, diagnosis, error_category, applied})
37:     state.iteration ← state.iteration + 1
38:  end while
39:  return state.test_passed, state.coverage_report
```

## 复杂度分析

- **时间复杂度**：最坏情况下执行 $i_{max}$ 轮迭代，每轮包含一次 LLM 调用（规划+生成+调试），故总体复杂度为 $O(i_{max} \cdot C_{LLM})$，其中 $C_{LLM}$ 为单次 LLM 调用的计算成本。
- **空间复杂度**：状态空间大小为 $O(|c| + |t| + |p|)$，其中 $|c|$ 为被测代码长度，$|t|$ 为测试代码长度，$|p|$ 为测试计划大小。

## 与基线方法的对比

| 方法 | 逻辑分析 | 错误分类 | 修复策略 | 迭代修复 |
|------|---------|---------|---------|---------|
| Baseline-1（直接LLM生成） | ✗ | ✗ | ✗ | ✗ |
| Baseline-2（单智能体） | ✗ | ✗ | ✗ | ✓ |
| Baseline-3（无分类修复） | ✓ | ✗ | 统一 | ✓ |
| **AITester（本文）** | ✓ | ✓ | 分层 | ✓ |
