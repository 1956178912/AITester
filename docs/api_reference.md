# AITester API 参考文档

> 本文档描述 AITester 的核心类和方法，供开发者集成和扩展使用。
> 最后更新：2026-08-17

---

## 目录

1. [智能体模块](#智能体模块)
2. [工具模块](#工具模块)
3. [工作流编排](#工作流编排)
4. [数据集加载](#数据集加载)
5. [配置管理](#配置管理)

---

## 智能体模块

### PlannerAgent

测试规划师，负责分析目标函数并生成结构化测试计划。

```python
from src.agents.planner import PlannerAgent

agent = PlannerAgent()
plan = agent.plan(
    target_code="def divide(a, b): return a / b",
    function_name="divide",
)
```

**关键方法：**

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `plan()` | `target_code: str`, `function_name: str` | `dict` | 生成测试计划，包含 `logic_analysis` 和 `test_cases` |

**返回格式：**
```json
{
  "function_name": "divide",
  "description": "两数除法",
  "logic_analysis": {
    "input_domain": "float, float",
    "output_domain": "float",
    "preconditions": ["b != 0"],
    "postconditions": ["result * b == a"],
    "edge_cases": ["b == 0 时抛出 ValueError"]
  },
  "test_cases": [...]
}
```

---

### GeneratorAgent

测试代码生成器，根据测试计划生成可运行的 pytest 代码。

```python
from src.agents.generator import GeneratorAgent

agent = GeneratorAgent()
test_code = agent.generate(
    test_plan=plan,
    target_code="def divide(a, b): return a / b",
    module_name="calculator",
    rag_references=[...],  # 可选，RAG 检索结果
)
```

**关键方法：**

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `generate()` | `test_plan: dict`, `target_code: str`, `module_name: str`, `rag_references: list` | `str` | 生成 pytest 测试代码 |

**验证方法：**

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `_validate_parametrize()` | `code: str` | `bool` | 校验 parametrize 参数匹配 |
| `_fix_import_module()` | `code: str`, `expected_module: str` | `str` | 修正错误的 import 模块名 |

---

### ExecutorAgent

测试执行器，在隔离环境中运行 pytest 并捕获结果。

```python
from src.agents.executor import ExecutorAgent

agent = ExecutorAgent()
result = agent.execute(
    test_code="import pytest\nfrom calculator import divide\n\ndef test_divide():\n    assert divide(1, 2) == 0.5",
    coverage=True,
    timeout=30,
)
```

**关键方法：**

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `execute()` | `test_code: str`, `coverage: bool`, `timeout: int` | `dict` | 执行测试，返回通过/失败状态、覆盖率、失败用例 |

**返回格式：**
```json
{
  "passed": true,
  "failed": [],
  "coverage": 85.5,
  "output": "...",
  "status": "success"
}
```

---

### DebuggerAgent

调试修复师，分析测试失败并生成修复补丁。

```python
from src.agents.debugger import DebuggerAgent

agent = DebuggerAgent()
result = agent.debug(
    target_code="def divide(a, b): return a - b",
    test_output="AssertionError: expected 0.5, got -1.0",
    failed_cases=[{"name": "test_divide", "error": "expected 0.5, got -1.0"}],
    rag_references=[...],  # 可选，RAG 修复案例
)
```

**关键方法：**

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `debug()` | `target_code: str`, `test_output: str`, `failed_cases: list`, `rag_references: list` | `dict` | 分析失败并生成修复补丁 |

**返回格式：**
```json
{
  "root_cause": "除法是减法而非除法，第 3 行应为 return a / b",
  "error_category": "assertion",
  "fix_strategy": "修改除法运算符",
  "patch": "```python\ndef divide(a, b): return a / b\n```"
}
```

---

### ErrorClassifier

错误类型分类器，使用规则匹配快速判断错误类别。

```python
from src.agents.error_classifier import ErrorClassifier, ErrorCategory

classifier = ErrorClassifier()
category = classifier.classify(test_output, failed_cases)
```

**错误类别枚举：**

| 值 | 说明 | 处理策略 |
|----|------|---------|
| `syntax` | 语法错误 | 重新生成完整文件 |
| `runtime` | 运行时异常 | 分析异常栈定位 bug |
| `assertion` | 断言失败 | 判断是代码逻辑还是测试预期错误 |
| `timeout` | 执行超时 | 检查死循环 |
| `unknown` | 未知错误 | 通用分析 |

---

## 工具模块

### CodeAnalyzer

AST 代码分析工具，提供精确的代码替换能力。

```python
from src.tools.code_analyzer import analyze_complexity, replace_function_code

# 计算圈复杂度
complexity = analyze_complexity(code_string)

# 替换函数实现
new_code = replace_function_code(
    original_code,
    function_name,
    new_body,
)
```

**关键函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `analyze_complexity()` | `code: str` | `int` | 计算圈复杂度 |
| `replace_function_code()` | `original_code`, `function_name`, `new_body` | `str` | AST 精确替换函数体 |

---

### PatchApplier

补丁应用工具，支持完整文件和单函数模式。

```python
from src.tools.patch_applier import apply_patch_to_code

# 应用完整文件补丁
fixed_code = apply_patch_to_code(
    original_code=buggy_code,
    patch="```python\ndef divide(a, b): return a / b\n```",
    mode="full_file",
)

# 单函数模式（推荐）
fixed_code = apply_patch_to_code(
    original_code=buggy_code,
    patch="return a / b",
    mode="function",
    function_name="divide",
)
```

**关键函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `apply_patch_to_code()` | `original_code`, `patch`, `mode`, `function_name` | `str` | 应用补丁到代码 |

---

## 工作流编排

### WorkflowGraph

LangGraph 工作流图，协调多智能体协作流程。

```python
from src.graph.workflow import build_workflow, run_workflow

# 构建工作流图
graph = build_workflow(
    enable_planner=True,
    enable_debugger=True,
    enable_rag=False,
)

# 运行工作流
result = run_workflow(
    graph=graph,
    target_code="def divide(a, b): return a - b",
    function_name="divide",
    max_iterations=3,
)
```

**工作流节点：**

| 节点 | 功能 | 是否调用 LLM |
|------|------|-------------|
| `planner_node` | 生成测试计划 | ✅ |
| `generator_node` | 生成测试代码 | ✅ |
| `executor_node` | 执行测试 | ❌ |
| `classifier_node` | 分类错误类型 | ❌ |
| `debugger_node` | 生成修复补丁 | ✅ |
| `patch_applier_node` | 应用补丁 | ❌ |

**条件路由：**
- `should_debug()`：根据测试结果决定是否进入调试循环
- 最大迭代次数限制：防止无限循环

---

## 数据集加载

### DatasetLoader

数据集加载基类。

```python
from src.dataset_loader import load_dataset

# 加载内置示例数据集
dataset = load_dataset("examples")

# 加载合成数据集
from src.synthetic_dataset import SyntheticDataset
dataset = SyntheticDataset(task_count=50, seed=42)

# 加载 SWE-bench 数据集
from src.dataset_loader import SWEBenchDataset
dataset = SWEBenchDataset(subset="lite")
```

**数据集接口：**

```python
# 遍历任务
for task in dataset:
    target_code = task["target_code"]
    function_name = task["function_name"]
    # ...
```

---

## 配置管理

### Config

全局配置管理，从环境变量和配置文件读取。

```python
from config import get_config

config = get_config()
print(config["MODEL_NAME"])  # agnes-2.5-flash
print(config["MAX_ITERATIONS"])  # 3
```

**配置项清单：**

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `LLM_N_API_KEY` | str | - | LLM API 密钥（必填） |
| `MODEL_NAME` | str | `agnes-2.5-flash` | LLM 模型名称 |
| `OPENAI_BASE_URL` | str | - | API 基础 URL |
| `MAX_ITERATIONS` | int | 3 | 最大修复迭代次数 |
| `COVERAGE_THRESHOLD` | float | 80.0 | 覆盖率阈值 |
| `EXECUTION_TIMEOUT` | int | 30 | pytest 执行超时（秒） |
| `LLM_TIMEOUT` | int | 60 | LLM 调用超时（秒） |
| `LLM_RETRY_WAIT` | int | 30 | LLM 重试等待（秒） |
| `ENABLE_PLANNER` | bool | true | 启用 Planner |
| `ENABLE_DEBUGGER` | bool | true | 启用 Debugger |
| `ENABLE_RAG` | bool | false | 启用 RAG |
| `BENCHMARK_PARALLELISM` | int | 0 | 并行度（0=串行） |
| `TEMPERATURE` | float | 0.2 | LLM 采样温度 |

---

## 错误处理

### 常见异常

| 异常 | 触发场景 | 处理方式 |
|------|---------|---------|
| `RuntimeError` | LLM 调用失败 | 检查 API Key 和网络连接 |
| `ModuleNotFoundError` | import 模块不存在 | 检查 `module_name` 配置 |
| `SyntaxError` | 生成的代码有语法错误 | Debugger 会重新生成 |
| `TimeoutError` | 测试执行超时 | 增加 `EXECUTION_TIMEOUT` |

---

## 扩展开发

### 添加新的智能体

1. 继承 `BaseAgent` 类
2. 定义 System Prompt
3. 实现核心方法
4. 注册到工作流图

```python
from src.agents.base_agent import BaseAgent

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(MY_SYSTEM_PROMPT)
    
    def my_method(self, input_data):
        # 实现逻辑
        pass
```

### 添加新的数据集

1. 实现 `Dataset` 接口
2. 返回 `target_code`, `function_name`, `module_name`
3. 注册到 `load_dataset()` 工厂函数

```python
from src.dataset_loader import Dataset

class CustomDataset(Dataset):
    def __init__(self):
        self.tasks = [...]
    
    def __iter__(self):
        return iter(self.tasks)
```

---

## 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| 1.0.0 | 2026-08-17 | 初始版本，包含 4 个智能体和完整工作流 |
| 0.9.0 | 2026-08-16 | 添加 RAG 支持和性能优化 |
