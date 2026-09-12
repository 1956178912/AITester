# AITester API 参考文档

> 本文档描述 AITester 的核心类和方法，供开发者集成和扩展使用。
> 最后更新：2026-09-14

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
    target_function="divide",
)
```

**关键方法：**

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `plan()` | `target_code: str`, `target_function: str \| None = None` | `dict` | 生成测试计划，包含 `logic_analysis` 和 `test_cases`；`target_function` 为 None 时分析全部函数 |

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
| `generate()` | `test_plan: dict`, `target_code: str`, `module_name: str`, `rag_references: list`, `focus_function: str` | `str` | 生成 pytest 测试代码（超预算时按 focus_function 做 AST 智能截取） |

**验证方法：**

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `_validate_parametrize()` | `code: str` | `bool` | 校验 parametrize 参数匹配 |
| `_fix_import_module()` | `code: str`, `expected_module: str` | `str` | 修正错误的 import 模块名 |

---

### ExecutorAgent

测试执行器，在本地或隔离沙箱中运行 pytest 并捕获结果。

```python
from src.agents.executor import ExecutorAgent

agent = ExecutorAgent(timeout=30)  # 默认本地系统环境执行
result = agent.execute(
    test_code="import pytest\nfrom calculator import divide\n\ndef test_divide():\n    assert divide(1, 2) == 0.5",
    target_file="examples/calculator.py",
    target_function="divide",
    coverage=True,
)

# venv 沙箱隔离执行（P1：不污染系统环境，依赖冲突互不影响）
sandbox_agent = ExecutorAgent(use_venv=True, auto_install_deps=True)
```

**关键方法：**

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `execute()` | `test_code: str`, `target_file: str`, `target_function: str`, `coverage: bool` | `dict` | 执行测试，返回通过/失败状态、覆盖率、失败用例 |

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
| `debug()` | `target_code: str`, `test_output: str`, `failed_cases: list`, `rag_references: list`, `focus_function: str`, `target_module: str` | `dict` | 分析失败并生成修复补丁（后两项可选：大文件 AST 聚焦截取 / 区分 ASSERTION 与 LOGIC_ERROR） |

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
# 提供被测模块名时，断言失败可区分 ASSERTION（代码 bug）与 LOGIC_ERROR（测试预期值写错）
category = classifier.classify(test_output, failed_cases, target_module="calculator")
```

**错误类别枚举（十二类，P2 细化 + 1.2 残余 + 1.1 状态细化）：**

| 值 | 说明 | 处理策略 |
|----|------|---------|
| `llm_format_error` | LLM 响应格式异常（JSON 解析失败 / 响应被截断 / 空响应），此前 75% UNKNOWN 的根因之一（1.2 残余细化） | 重新请求 LLM 生成合规响应 / 剥离 markdown 代码块后再解析 / 降低单次输出长度 |
| `import_error` | 模块导入失败（ModuleNotFoundError/ImportError），通常缺第三方依赖或模块路径错误 | 安装缺失依赖 / 修正导入语句（配合 executor `auto_install_deps` 自动装依赖） |
| `syntax` | 语法/编译错误（SyntaxError、IndentationError） | 重新生成完整文件 |
| `type_error` | 类型不匹配（TypeError） | 核对参数与返回类型 |
| `index_error` | 索引越界（IndexError / index out of range / 下标越界），此前落入 RUNTIME/UNKNOWN 致 Debugger 无法针对性修复（1.2 残余细化） | 补边界判断（空容器先判空再访问），不用 try/except 静默吞掉越界 |
| `assertion` | 断言失败且失败栈触及被测代码 | 判断是代码逻辑错误 |
| `logic_error` | 断言失败但失败栈未触及被测模块，疑似测试预期值写错 | 修正测试用例断言（而非盲目改被测代码） |
| `runtime` | 其他运行时异常（除零、NameError 等） | 分析异常栈定位 bug |
| `timeout` | 执行超时 | 检查死循环 |
| `unknown` | 无法识别的错误 | 通用分析（LLM 兜底） |
| `patch_validation_failed` | 补丁被 PatchApplier 安全守卫拒绝（空/过短/无函数定义/路径不合法，repair_history 中 patch_applied=False），1.1 状态细化——由 `refine_failure_category()` 按 repair_history 信号判定，不走 `classify()` 文本正则 | 重新生成完整修复补丁（先补函数定义与最小长度再走验证），区分"补丁未生效"与"补丁应用后仍失败" |
| `rag_retrieval_empty` | RAG 启用但任务内全部检索命中为 0（rag_stats 非空且所有 results==0），标识 RAG 失效场景（1.1 状态细化）——由 `refine_failure_category()` 按 rag_stats 信号判定，不走 `classify()` 文本正则 | 检查 RAG 检索库是否已填充 / 降低 top_k / 改启用混合检索；本类命中占比恒 0，可当 RAG 自检指标 |

分类优先级（`classify()` 文本正则十类）：`LLM_FORMAT_ERROR > IMPORT_ERROR > SYNTAX > TYPE_ERROR > INDEX_ERROR > RUNTIME > ASSERTION/LOGIC_ERROR > TIMEOUT > UNKNOWN`，全部基于正则规则匹配，不消耗 LLM token。LLM_FORMAT_ERROR 置于最前（JSON 解析失败文本几乎不含 IndexError，但 IndexError 文本可能出现 assert，顺序放反会误判）。后 2 类（`PATCH_VALIDATION_FAILED` / `RAG_RETRIEVAL_EMPTY`）为 1.1 状态细化类，不走 `classify()` 文本正则，由纯函数 `refine_failure_category()` 在任务收尾按 `repair_history`（补丁被拒）/ `rag_stats`（检索全空）信号判定——补丁被拒优先于 RAG 检索空；成功任务原样返回。benchmark 与 CLI 两个出口口径一致。

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

### CodeContext

基于 AST 的智能代码截取工具（P0：大文件场景 LLM 上下文优化）。

```python
from src.tools.code_context import extract_focused_code

focused = extract_focused_code(
    source_code,
    focus_function="divide",  # 保留 import + 该函数及其直接依赖的辅助函数
    max_chars=3000,
)
```

**关键函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `extract_focused_code()` | `code`, `focus_function`, `max_chars` | `str` | AST 截取：保留 import + 焦点函数及直接依赖；无法解析或仍超预算时返回原样/兜底结果 |

---

### Dependency

第三方依赖检测与缓存 venv 管理（P1：执行隔离）。

```python
from src.tools.dependency import find_missing_modules, venv_cache_dir, create_venv, install_packages

missing = find_missing_modules("import pandas\ndef f(): ...")
# → {"pandas"}（标准库与非 import 语句会被过滤）

venv_dir = venv_cache_dir(["pandas"])  # 按依赖组合的磁盘缓存目录
venv_python = create_venv(venv_dir, timeout=120)
install_packages(venv_python, ["pandas"], timeout=120)
```

**关键函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `extract_imported_modules()` | `code: str` | `set[str]` | 提取代码中 import 的顶层模块名 |
| `is_standard_library()` | `module_name: str` | `bool` | 判断是否标准库 |
| `find_missing_modules()` | `code: str` | `set[str]` | 代码中导入但当前环境不可用的第三方模块 |
| `suggest_package_names()` | `module_names: set[str]` | `list[str]` | 模块名 → 建议的 pip 包名（处理下划线/别名映射） |
| `create_venv()` | `venv_dir: str`, `timeout: int` | `str` | 创建 venv 并返回 python 解释器路径（磁盘缓存复用） |
| `install_packages()` | `venv_python`, `packages`, `timeout` | `bool` | 在 venv 内 pip install（失败返回 False，不抛异常） |

---

### TokenUsage

线程局部 LLM token 用量统计（P0：效率指标）。

```python
from src.graph import token_usage

token_usage.record_usage(1200, 300, model="gpt-4o")
usage = token_usage.get_usage()
print(usage.total_tokens)  # 1500
usage.reset()  # 单线程重置（基线运行前调用）
```

**关键函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `record_usage()` | `input_tokens`, `output_tokens`, `model` | `None` | 记入当前线程统计（按模型分桶） |
| `get_usage()` | - | `TokenUsage` | 当前线程累计（含 total_tokens / by_model，`as_dict()` 可序列化） |
| `reset()` | - | `TokenUsage` | 重置当前线程统计，返回重置前快照 |

---

## 工作流编排

### WorkflowGraph

LangGraph 工作流图，协调多智能体协作流程。

```python
from src.graph.workflow import build_workflow
from src.graph.state import AITesterState

# 构建并编译工作流图。planner / debugger 可显式覆盖 config 开关
# （消融基线如 plain_llm 可传 False）；None（默认）读取 config.ENABLE_PLANNER / ENABLE_DEBUGGER
graph = build_workflow()
# 消融示例：纯 LLM 基线（无规划、无修复循环）
# graph = build_workflow(planner=False, debugger=False)

# 运行工作流：invoke 接收初始状态字典，返回最终状态
state: AITesterState = {
    "target_code": "def divide(a, b): return a - b",
    "target_file": "/path/to/calculator.py",
    "target_function": "divide",
    "max_iterations": 3,
}
final_state = graph.invoke(state)
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
from src.datasets import load_dataset

# 加载内置示例数据集
dataset = load_dataset("examples")

# 加载合成数据集
from src.datasets import SyntheticDataset

dataset = SyntheticDataset(task_count=50, seed=42)

# 加载 SWE-bench 数据集
from src.datasets import SWEBenchDataset

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
from config import LLM_CONFIGS, MODEL_NAME

print(len(LLM_CONFIGS))  # 已加载的 LLM Provider 数量
print(MODEL_NAME)  # 默认模型（LLM_1）名称
```

**配置项清单：**

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `LLM_N_API_KEY` | str | - | 第 N 个 LLM 的 API 密钥（写在 `.env.local`） |
| `LLM_N_BASE_URL` | str | - | 第 N 个 LLM 的 API 基础 URL |
| `LLM_N_MODEL_NAME` | str | - | 第 N 个 LLM 的模型名称 |
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
| `MODEL_NAME` / `OPENAI_API_KEY` / `OPENAI_BASE_URL` | str | - | 仅派生值（取自 LLM_1，向后兼容），**不是配置输入** |

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

1. 实现 `BaseDatasetLoader` 抽象基类
2. 返回 `target_code`, `function_name`, `module_name`
3. 在 `load_dataset()` 工厂函数的 `dataset_map` 中注册

```python
from src.datasets.dataset_loader import BaseDatasetLoader


class CustomDataset(BaseDatasetLoader):
    def __init__(self):
        self.tasks = [...]

    def __iter__(self):
        return iter(self.tasks)
```

---

## 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| 0.9.13 | 2026-09-14 | 错误分类 8→10 类（LLM_FORMAT_ERROR + INDEX_ERROR，1.2 残余）、APIManager 熔断冷却期（4.1 残余，默认 60s）、结果分析脚本 analyze_results.py（4.3）、基线 token 效率汇总（2.2） |
| 0.9.12 | 2026-09-13 | 多候选补丁（3.1，默认关）、结构化 JSONL 追踪层（4.1，默认关）、成本感知路由（3.4）、RAG 纳入主实验（2.3）、CLI 边界补测（1.5） |
| 1.0.0 | 2026-08-17 | 初始版本，包含 4 个智能体和完整工作流 |
| 0.9.11 | 2026-09-11 | import 提取单一实现、故障转移模型路由、MySQL 单例 DCL、RAG 粘性标志、NaN/Inf 序列化修复（详见 CHANGELOG） |
| 0.9.10 | 2026-09-11 | CLI 并发派发器去重与回归防护（详见 CHANGELOG） |
| 0.9.9 | 2026-09-11 | 死分支清理、visualize 结果误选与标准化实验 KeyError 修复（详见 CHANGELOG） |
| 0.9.8 | 2026-09-10 | 格式门禁恢复、benchmark 结果构造去重、后台健康线程可关闭（详见 CHANGELOG） |
| 0.9.7 | 2026-09-10 | AST 智能截取、SWE-bench 质量校验、token 统计、venv 沙箱、RAG 持久化、错误分类 5→8 类（详见 CHANGELOG） |
| 0.9.6 | 2026-09-10 | regenerate 死循环、patch 写盘原子化、脱敏加固、CLI 失败门控等 14 项修复（详见 CHANGELOG） |
| 0.9.5 | 2026-09-10 | 配置整块移除、打包修复、数值环境变量容错解析、日志脱敏接入（详见 CHANGELOG） |
| 0.9.4 | 2026-09-13 | 环境变量名推导、真实 t 检验、统计双实现收敛、chromadb 现代 API（详见 CHANGELOG） |
| 0.9.3 | 2026-09-13 | 配置写盘路径修正与运行时刷新（详见 CHANGELOG） |
| 0.9.2 | 2026-09-09 | CI 门禁修复、单例线程安全、后台线程泄漏修复、版本号单一来源（详见 CHANGELOG） |
| 0.9.1 | 2026-09-09 | CLI 选项 state 贯通、退避公式修正、import 替换相似度门控（详见 CHANGELOG） |
| 0.9.0 | 2026-08-16 | 添加 RAG 支持和性能优化 |
