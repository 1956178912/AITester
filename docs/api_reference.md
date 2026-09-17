> **语言 / Language**：[English](api_reference.en.md) | 简体中文（本文）

# AITester API 参考文档

> 本文档描述 AITester 的核心类和方法，供开发者集成和扩展使用。
> 最后更新：2026-09-16（数据集与评估深化轮次：2.1 污染检测 / 2.2 难度分层 / 4.3 Docker 执行模式 / 4.4 依赖缓存）

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
| `generate()` | `test_plan: dict`, `target_code: str`, `module_name: str = ""`, `rag_references: list[dict] \| None = None`, `focus_function: str \| None = None` | `str` | 生成 pytest 测试代码（超预算时按 focus_function 做 AST 智能截取；后三参数均默认 None/""） |

**验证方法：**

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `_validate_parametrize()` | `code: str` | `bool` | 校验 parametrize 参数匹配 |
| `_fix_import_module()` | `code: str`, `expected_module: str` | `str` | 修正错误的 import 模块名 |

---

### ExecutorAgent

测试执行器，在本地、隔离沙箱或 Docker 容器中运行 pytest 并捕获结果。

```python
from src.agents.executor import ExecutorAgent

agent = ExecutorAgent(timeout=30)  # 默认本地系统环境执行
result = agent.execute(
    test_code="import pytest\nfrom calculator import divide\n\ndef test_divide():\n    assert divide(1, 2) == 0.5",
    target_file="examples/calculator.py",
    target_function="divide",
)

# venv 沙箱隔离执行（P1：不污染系统环境，依赖冲突互不影响）
sandbox_agent = ExecutorAgent(use_venv=True, auto_install_deps=True)

# 4.3 Docker 隔离执行（经 docker CLI 在容器内跑 pytest，镜像内置依赖）
docker_agent = ExecutorAgent(use_docker=True, docker_image="aitester:latest")
```

**关键方法：**

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `execute()` | `test_code: str`, `target_file: str`, `target_function: str \| None` | `dict` | 执行测试，返回通过/失败状态、覆盖率、失败用例；执行模式优先级 Docker > venv 沙箱 > 本地 |
| `_execute_docker()` | 同 `execute()` | `dict` | 4.3 Docker 隔离执行：`docker run` 挂载卷传入被测代码，docker 不可用时返回 `docker_unavailable` 诊断（不静默降级本地） |

**返回格式：**
```json
{
  "passed": true,
  "failed_cases": [],
  "coverage": 85.5,
  "output": "...",
  "docker_image": "aitester:latest"
}
```

> Docker 模式额外携带 `docker_image` 字段（供实验分析记录执行模式差异）；失败时 `error_info.type` 可能为 `docker_unavailable` / `docker_timeout`。

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
| `debug()` | `target_code: str`, `test_output: str`, `failed_cases: list`, `rag_references: list[dict] \| None = None`, `focus_function: str \| None = None`, `target_module: str \| None = None` | `dict` | 分析失败并生成修复补丁（后三项均默认 None：大文件 AST 聚焦截取 / 区分 ASSERTION 与 LOGIC_ERROR） |

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
| `get_venv_cache_stats()` | 无 | `dict` | 4.4 依赖缓存命中率统计：进程内累计 hit/create 事件 + 落盘 JSON 跨进程聚合，返回 `hit_rate = hits/(hits+creates)` |
| `list_venv_cache()` | 无 | `list[dict]` | 4.4 列出缓存目录所有 venv（name / path / size_mb / created_at） |
| `clear_venv_cache()` | `max_age_days: int \| None`, `max_size_mb: int \| None` | `dict` | 4.4 按年龄 / 大小过滤清理缓存，两者均 None 时清空 |

---

### 数据污染检测（2.1）

`experiments/contamination_check.py`：SWE-bench 数据污染风险应对——比较系统生成补丁与数据集官方黄金补丁的 token 级 Jaccard 相似度，标记高度重叠任务（疑似训练数据污染 / 逐字复现）。

```python
from experiments.contamination_check import (
    detect_contamination,
    patch_overlap_score,
    render_contamination_section,
)

# 单对补丁的重叠度（[0.0, 1.0]，空补丁返回 0.0）
score = patch_overlap_score(generated_patch, golden_patch)

# 批量扫描 benchmark 结果 details（details[].patch + golden_patches 映射或 task_metadata.golden_patch）
report = detect_contamination(details, golden_patches={"task_1": "..."})
# → {"checked": n, "high": [...], "medium": [...], "scores": {...}, "contaminated_tasks": [...]}

# Markdown 章节渲染（checked=0 时返回空列表，调用方跳过）
lines = render_contamination_section(report, baseline="aitester")
```

**口径：** high ≥ 0.85（疑似逐字复现）/ medium ≥ 0.6（建议人工复核）；token 为小写化标识符/数字切分，仅统计 diff 修改行（丢弃 diff 元数据）。配套：`dataset_loader` 把官方 patch 存入 `task.metadata["golden_patch"]`（不暴露给 LLM），`run_benchmark` 结果行携带 `patch` 字段，`load_dataset` 支持 `swe_rebench` 别名（抗污染基准）。

---

### 任务难度分层（2.2）

`experiments/difficulty_stratification.py`：按代码复杂度 / 依赖数量 / 文件规模把任务分层，定位"系统在什么难度区间能力衰减"。

```python
from experiments.difficulty_stratification import stratify_by_dimension, render_stratification_section

# 按指定维度分层（code_size / dependency_count / complexity_proxy）
strat = stratify_by_dimension(details, "code_size", instance_codes={...}, test_codes={...})
# → {"small": {"tasks": n, "passed": n, "success_rate": f}, "medium": {...}, "large": {...}}

# Markdown 章节渲染（无 details 时返回空列表）
lines = render_stratification_section(details, baseline="aitester")
```

**分层边界（保守可解释口径）：** code_size small <2KB / medium 2–10KB / large >10KB；dependency_count low 0 / medium 1–2 / high ≥3；complexity_proxy easy 0 / medium 1 / hard ≥2（`iterations × (1 - passed)`，成功任务恒 0）。

---

### 收敛失败模式归因（1.2）

`experiments/analyze_results.py:_convergence_failure_modes(details)`：对达到 MAX_ITERATIONS（iterations>=3）仍未修复的任务，区分两类失败模式：
- **无法定位根因**：诊断文本反复同义（最近 2 轮 diagnosis 相同）且补丁从未写盘成功——说明 Debugger 反复给出相同结论，没有真正识别到问题所在
- **无法生成有效补丁**：补丁曾写盘成功（patch_applied=True）但测试仍失败，或被安全守卫反复拒绝（patch_applied=False 且有 patch 记录）

```python
from experiments.analyze_results import _convergence_failure_modes

report = _convergence_failure_modes(details)
# → {"total_converged_failed": n, "root_cause_stuck": n, "patch_generation_failed": n,
#    "tasks": [...], "available": bool}
# available=False 时无达到 MAX_ITERATIONS 的失败任务，渲染层跳过章节
```

**保守启发，不依赖 LLM**：仅消费 details[].iterations / diagnosis / repair_history / patch 已有字段。

---

### 边界用例覆盖（1.3）

`experiments/analyze_results.py:_boundary_case_coverage(details)`：对 details[].generated_test 做 AST 保守判定，识别是否覆盖 None / 空字符串 / 空集合 / 0 / -1 / >= / <= 等边界条件。

```python
from experiments.analyze_results import _boundary_case_coverage

report = _boundary_case_coverage(details)
# → {"available": bool, "observed_tasks": n, "boundary_types": {"none": n, ...},
#    "tasks_covering_any_boundary": n, "coverage_rate": f}
# 旧 JSON 无 generated_test 时 available=False，渲染层跳过章节
```

---

### 变异得分（1.3）

`experiments/analyze_results.py:_mutation_score_metrics(details)`：收集 details[].mutation_score（外部变异测试器如 mutmut 产出，0.0–1.0），汇总平均 / 高（>=0.7）/ 低（<0.4）分布。无该字段时 available=False，渲染层跳过章节，不阻断主流程。

```python
from experiments.analyze_results import _mutation_score_metrics

report = _mutation_score_metrics(details)
# → {"available": bool, "observed_tasks": n, "avg_mutation_score": f,
#    "high_score_tasks": n, "low_score_tasks": n}
```

---

### 断言强度 AST 增强（1.3）

`experiments/analyze_results.py:_assertion_strength_proxy(details)`：在原有 `assert` 行数统计基础上新增 AST 口径（`ast.parse` + `ast.Assert` 节点计数），输出 `ast_avg_assertions` 与 `ast_parse_failed_tasks`（解析失败任务清单，可交叉异味检测）。旧 JSON 无 generated_test 时整个 proxy available=False。

```python
from experiments.analyze_results import _assertion_strength_proxy

report = _assertion_strength_proxy(details)
# → {"available": bool, "observed_tasks": n, "avg_assertions_per_task": f,
#    "min_assertions": n, "max_assertions": n, "tasks_with_zero_assertions": n,
#    "ast_avg_assertions": f | None, "ast_parse_failed_tasks": [...]}
```

---

### 执行反馈轨迹（3.2）

`state.execution_trace`（list，默认 `[]`）+ `nodes._record_execution_trace`：每次 Executor 执行追加一条记录到 `state["execution_trace"]`，纯观测层默认常开，不影响修复路由。

```python
from src.graph.state import AITesterState, create_initial_state
from src.graph.nodes import _record_execution_trace

state = create_initial_state(task_uuid="t1", target_file="/p.py", target_code="def f(): pass",
                              target_function=None, max_iterations=3)
# 工作流执行后 state["execution_trace"] 形如：
[
  {
    "iteration": 0,
    "passed": False,
    "coverage": 40.0,
    "coverage_delta": None,       # 首轮无前一轮
    "elapsed_seconds": 2.0,
    "reward_signals": {           # 保守线性归一，仅记录观测，不参与路由
      "correctness": 0.0,         # 1.0 if passed else 0.0
      "efficiency": 0.93,         # 1 - elapsed / EXECUTION_TIMEOUT
      "simplicity": 0.97          # 1 - elapsed / (EXECUTION_TIMEOUT * 2)
    }
  },
  {
    "iteration": 1,
    "passed": True,
    "coverage": 85.0,
    "coverage_delta": 45.0,       # 85 - 40
    "elapsed_seconds": 3.0,
    "reward_signals": {"correctness": 1.0, "efficiency": 0.9, "simplicity": 0.95}
  }
]
```

`run_benchmark.py` 结果行带 `execution_trace`（失败分支 `None` 兜底保持键集合同构）；`analyze_results.py` 新增"执行反馈轨迹汇总（3.2）"章节：统计观测任务数 / 总执行次数 / 平均轮数 / 首轮即通过率 / 末轮 correctness & efficiency 均值 / 首末轮覆盖率趋势（delta）。旧 JSON 无该字段时章节跳过。

**用途**：为未来执行反馈驱动的微调（如 BoostAPR 类方法）备料——每次 benchmark 自动把"通过/失败、覆盖率变化、耗时、多维奖励信号"落进结果 JSON，无需额外执行轨迹采集脚本。

---

### 结构化追踪层（4.1）

`src/observability/trace.py`：JSONL 追加式记录每个工作流任务的"任务级"事件（节点输入/输出摘要、token 消耗、墙钟耗时、路由决策），供实验分析直接消费。默认关闭（`AITESTER_TRACE_DIR` 未设时全 no-op，零性能税）；显式设置后启用。

```python
from src.observability.trace import TraceSession, trace_enabled

if trace_enabled():
    session = TraceSession(task_id, trace_dir, config_flags)
    session.record_node("planner", output_summary=..., decision="plan_complete")
    session.record_task_end(passed=True)
```

**关键特性：** 线程安全（`--parallel` 多工作线程并发追加同一 JSONL，单条 append+flush 在锁内）；所有写入文本统一过 `mask_sensitive_info`（与日志脱敏同源）；写盘失败不阻断主流程（仅 warning）。

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

**工作流节点**（节点 ID 在 `src/graph/workflow.py` 经 `add_node` 注册，节点函数实现见 `src/graph/nodes.py`，均为下划线前缀的 `_<id>_node`）：

| 节点 ID | 功能 | 是否调用 LLM |
|---------|------|-------------|
| `planner` | 生成测试计划 | ✅ |
| `generator` | 生成测试代码 | ✅ |
| `executor` | 执行测试 | ❌ |
| `debugger` | 分层诊断 + 生成修复补丁（错误分类在节点内联调用 `error_classifier.classify`，无独立分类节点） | ✅ |
| `patch_applier` | 应用补丁（单文件 `safe_apply_patch`；`CROSS_FILE_ENABLE=true` 时走跨文件多文件分支） | ❌ |
| `cross_file_analyzer` | 3.5 跨文件依赖分析（仅 `CROSS_FILE_ENABLE=true` 时注册，插在 `executor → debugger` 之间） | ❌ |

**条件路由：**
- `_should_debug()`：根据测试结果与迭代轮次决定是否继续进入调试循环（循环终止逻辑）
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

# 2.1 加载 SWE-rebench 抗污染基准（与 SWE-bench 字段同构，经 data_dir 指向 rebench 数据目录）
dataset = load_dataset("swe_rebench", data_dir="/path/to/rebench_data")
```

**支持的数据集名称**（`load_dataset` 的 `dataset_map`，含别名）：
`swe_bench` / `swebench` / `swe_rebench` / `swebench_rebench` / `defects4j_python` / `d4j_py` / `in_memory` / `examples` / `synthetic` / `synth`。未列出的名称降级为 `InMemoryDataset`（graceful degradation）。

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
| `LLM_N_COST_WEIGHT` | float | 0.0（=无信息） | 3.4 成本感知路由的相对成本倍数（0.1~1000，未配置 0.0 时 APIManager 回退 1.0 基准） |
| `MAX_ITERATIONS` | int | 3 | 最大修复迭代次数 |
| `COVERAGE_THRESHOLD` | float | 80.0 | 覆盖率阈值 |
| `EXECUTION_TIMEOUT` | int | 30 | pytest 执行超时（秒） |
| `LLM_TIMEOUT` | int | 60 | LLM 调用超时（秒） |
| `LLM_RETRY_WAIT` | int | 30 | LLM 重试等待（秒） |
| `ENABLE_PLANNER` | bool | true | 启用 Planner |
| `ENABLE_DEBUGGER` | bool | true | 启用 Debugger |
| `ENABLE_RAG` | bool | false | 启用 RAG |
| `CROSS_FILE_ENABLE` | bool | false | 3.5 跨文件修复：启用 `cross_file_analyzer` 节点（插在 executor→debugger 之间）+ 多文件补丁分支 |
| `CROSS_FILE_MAX_MODULES` | int | 5 | 3.5 跨文件修复计划最大模块数（防 token 爆炸） |
| `ASSERTION_AUGMENT_ENABLE` | bool | false | 3.4 断言增强：AST 提取被测代码现有 assert 注入 prompt |
| `ENABLE_MULTI_CANDIDATE_PATCH` | bool | false | 3.1 多候选补丁生成与静态/执行验证筛选（默认关，无候选回退单补丁）；`reproduce.sh` 复现流程默认显式启用（`--no-multi-candidate` 可回退历史口径） |
| `AITESTER_TRACE_DIR` | str | 未设（no-op） | 4.1 结构化 JSONL 追踪层输出目录（未设时追踪层 no-op，不影响运行）；`reproduce.sh` 默认启用（`experiments/results/traces`） |
| `BENCHMARK_PARALLELISM` | int | 0 | 并行度（0=串行） |
| `TEMPERATURE` | float | 0.2 | LLM 采样温度 |
| `MODEL_NAME` / `OPENAI_API_KEY` / `OPENAI_BASE_URL` | str | - | 仅派生值（取自 LLM_1，向后兼容），**不是配置输入** |
| `EXECUTOR_USE_DOCKER` | bool | false | 4.3 Docker 隔离执行（经 docker CLI 在容器内跑 pytest；需本机安装 docker 且镜像已构建，不可用时返回 `docker_unavailable` 诊断不降级本地） |
| `EXECUTOR_DOCKER_IMAGE` | str | `aitester:latest` | 4.3 Docker 执行使用的镜像名（对应仓库根 Dockerfile） |
| `EXECUTOR_USE_VENV` | bool | false | venv 沙箱隔离执行（按依赖组合磁盘缓存，不污染系统环境） |
| `EXECUTOR_AUTO_INSTALL_DEPS` | bool | false | venv 内自动 pip install 缺失依赖 |
| `AITESTER_VENV_CACHE_DIR` | str | `~/.cache/aitester/venvs` | 4.4 venv 缓存目录覆盖（容器/CI 隔离场景指向挂载卷；配合 `clean-venv-cache` 子命令清理） |

**APIManagerConfig 字段**（`src/api/api_health.py` 数据模型，`api_manager.py` 消费；编程接口配置，非环境变量；4.1/4.2 熔断器 + 3.4 成本感知）：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `circuit_cooldown_seconds` | float | 60.0 | 4.1 熔断冷却时长：节点连续失败达 `max_consecutive_failures` 后进入冷却期 |
| `enable_half_open_probe` | bool | True | 4.2 半开探测开关：冷却到期后节点先进入 half-open 窗口仅承载一次探测，成功闭合熔断器 / 失败重开半程冷却；置 False 退回 4.1 直接放行行为 |
| `half_open_probe_penalty_cap_seconds` | float | 30.0 | 4.2 半开探测失败惩罚时长上限：失败重开冷却 = `min(circuit_cooldown_seconds/2, 本字段)` |
| `cost_alert_threshold` | float | 2.0 | 3.4 成本告警阈值：故障转移到 `cost_weight >= 阈值` 的昂贵节点时记 WARNING |

> 监控：`get_status()` 每节点输出 `circuit_open_remaining_s`（熔断冷却剩余秒）与 `circuit_state`（`closed` / `open` / `half_open` 三态，仅 `enable_half_open_probe=True` 时报告 half_open）。

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
| 0.9.16 | 2026-09-15 | 深度重构轮次：AITesterState 初始化双写收敛为 `create_initial_state()` 工厂（CLI + benchmark 单一构造点）、experiments/visualize_results.py 统计检验收敛复用 statistical_analysis.py 配对原语 + NaN/Inf 守卫、code_context.py 补测 9 用例（模块覆盖率 89%→98%）、README 结构树补齐 5 个拆分产物（tracing/rag/nodes、api_health、llm_client）+ 测试状态表 13 处行内数同步 + api_reference 参数默认值标注；全量 1291 passed / ruff 全绿 / 覆盖率 94% |
| 0.9.20 | 2026-09-17 | 结构优化轮次：`executor.py` 按职责拆分为 4 个子模块（`executor_imports.py` / `executor_modes.py` / `executor_output.py` / `executor_runtime.py`，类方法经绑定挂回 `ExecutorAgent`，旧导入路径与测试 patch 目标不变）；`dataset_loader.py` 拆分出 `dataset_defects4j.py` / `dataset_inmemory.py`（re-export 保持旧导入路径，SWE-bench 加载器因模块级 `_datasets` 测试 patch 目标留在主模块）；Docker 执行链路 5 条路径补齐 mock 测试（`TestDockerExecutionFlow`，此前 0 覆盖）、dependency 边界分支 +14 用例（`tools/dependency.py` 90%→99%）、清除 `dataset_loader.py` 重复 JSON 解析死代码、pytest 过滤 scipy 恒定组 t 检验 "precision loss" 数值告警；新增 21 个用例，全量 1386 passed / 覆盖率 95% |
| Unreleased | 2026-09-16 | 评估指标深化轮次：1.2 收敛失败模式归因（`analyze_results.py:_convergence_failure_modes`，对达到 MAX_ITERATIONS 仍未修复的任务区分"无法定位根因" vs "无法生成有效补丁"）/ 1.3 边界用例覆盖（`_boundary_case_coverage`，AST 保守判定 None/空集合/0/-1/>=/<= 等边界条件）/ 1.3 变异得分（`_mutation_score_metrics`，收集 details[].mutation_score）/ 1.3 断言强度 AST 增强（`_assertion_strength_proxy` 新增 `ast_avg_assertions` + `ast_parse_failed_tasks`）/ 3.2 执行反馈轨迹（`state.execution_trace` + `nodes._record_execution_trace` + `run_benchmark.py` 结果行带轨迹 + `analyze_results.py` 自动汇总渲染，纯观测层默认常开，为 RL 微调备料）；新增 14 个用例，全量 1365 passed / 覆盖率 95% |
| Unreleased | 2026-09-16 | 数据集与评估深化轮次：2.1 数据污染检测（`experiments/contamination_check.py` token 级 Jaccard 重叠度，high ≥ 0.85 / medium ≥ 0.6；`dataset_loader` 保留官方 patch 至 `metadata["golden_patch"]`；`load_dataset` 支持 `swe_rebench` 别名）/ 2.2 任务难度分层（`experiments/difficulty_stratification.py`，code_size / dependency_count / complexity_proxy 三维度）/ 4.3 Docker 执行模式转正（`ExecutorAgent._execute_docker` + `EXECUTOR_USE_DOCKER` / `EXECUTOR_DOCKER_IMAGE`，docker 不可用返回 `docker_unavailable` 诊断不降级本地；`scripts/compare_executor_modes.py` 时间对比）/ 4.4 依赖缓存监控完善（CLI `clean-venv-cache` + `AITESTER_VENV_CACHE_DIR` + 命中率入分析）/ 4.1 脱敏审计（`scripts/audit_log_redaction.py` + 子进程环境凭证剔除）/ 3.1 `reproduce.sh` 默认启用多候选补丁 + 3.2t `reproduce.sh` 显式启用 `AITESTER_TRACE_DIR` / 5.1 低覆盖模块补强（logging_utils 90%→100%、analysis.py 统计检验边界、cli/app.py 并发中断/信号处理） |
| 0.9.15 | 2026-09-15 | 代码可维护性深化轮次：Ruff 规则集增强（SIM/PERF/RET/RUF，修复 63 处命中）+ 337 函数完整类型注解 + 9 个高复杂度函数中 7 个重构（get_fix_strategy/run/check_dataset/generate/_execute_sandboxed/clear_venv_cache/analyze_cross_file_deps）；全量 1270 passed / ruff 全绿 |
| 0.9.14 | 2026-09-15 | 全项目收敛轮次：config 集中化（删除 CROSS_FILE/ASSERTION 死常量、SWE_BENCH_ENRICHMENT 收敛 config、MULTI_CANDIDATE_EXEC_VALIDATE 收敛 helper）、修复 executor 标准库清单误列 diskcache、修复跨文件降级路径写不进盘、删除 4 处死代码、RAG 检索器写锁 + _upsert 抽取、refine_final_error_category 收敛；全量 1270 passed / ruff 全绿 |
| 0.9.14 | 2026-09-15 | `tests/test_rag_retriever.py` 补模块级 `pytestmark=skipif(not _chroma_available())`（与 `test_rag_metrics.py` 口径一致，缺 chromadb 时 32 条 RAG 检索器用例优雅跳过而非 ImportError ERROR）；`tests/test_experiments_scripts.py` 的 `TestVisualizeLoadLatestResult` / `TestVisualizeSummaryMdTable` fixture 在惰性导入 `experiments.visualize_results` 前补 `pytest.importorskip("matplotlib")`（缺 matplotlib 时 5 条可视化用例跳过）。精简环境（未全量安装 `requirements.txt`）下全量基线为 **1208 passed / 39 skipped / 0 failed**；全量安装依赖后恢复 **1247 passed / 0 skipped** |
| 0.9.14 | 2026-09-15 | O-01 新增 `tests/test_cli_output.py`（10 用例：colorize TTY 双分支 / 消息 stderr 路由 / print_rich_table 边界），`src/cli/output.py` 覆盖率 58%→92% |
| 0.9.13 | 2026-09-14 | 4.2 熔断器半开探测：`APIHealth` 新增 `in_circuit_half_open` 与 `_probe_circuit_half_open()`（成功闭合 / 失败重开半程冷却 `min(cooldown/2, cap)`），`get_healthy_nodes()` / `_build_node_list()` 将半开窗口节点纳入路由候选，`call()` / `check_health()` 统一消费探测结果，`get_status()` 新增 `circuit_state`（closed / open / half_open）；`APIManagerConfig` 新增 `enable_half_open_probe`（默认 True，置 False 退回 4.1 直接放行行为）与 `half_open_probe_penalty_cap_seconds`（默认 30.0）；`docs/design/cross_file_repair.md` python 代码块格式归一；全量 1237 passed / ruff 全绿 |
| 0.9.13 | 2026-09-14 | 1.2 测试异味检测 + 1.3 修复收敛曲线（`analyze_results.py` 新增 `test_smell_detection` / `repair_convergence_curve` 纯函数 + Markdown 章节）、4.4 依赖缓存监控（`dependency.py` 新增 `get_venv_cache_stats` / `list_venv_cache` / `clear_venv_cache` + `create_venv` 记录 hit/create 事件，修复 `threading.Lock` 不可重入死锁）、5.3 失败根因分类 + 案例知识库（`analyze_failures.py` 新增 `root_cause_classification` / `failure_knowledge_base` + CLI `--knowledge-base`）、3.4 断言增强策略（`generator.py` 新增 `_extract_existing_assertions` + `ASSERTION_AUGMENT_ENABLE` 开关，默认关）、3.5 跨文件修复（新增 `src/tools/cross_file.py` 协调器-提议者架构 + `workflow.py` cross_file_analyzer 节点 + `CROSS_FILE_ENABLE` / `CROSS_FILE_MAX_MODULES` 开关，默认关）；新增设计文档 `docs/design/cross_file_repair.md`；全量 1225 passed / ruff 全绿 |
| 0.9.13 | 2026-09-14 | 结果分析层 1.1/1.2 指标增强：`experiments/analyze_results.py` 新增 `repair_convergence_metrics`（首次尝试成功率、成功/失败任务的迭代 min/avg/median/max、成功任务平均耗时）与 `quality_proxy_metrics`（覆盖率/耗时代理、可选 `generated_test` 的断言行数代理、失败类别 Top N）；`build_analysis` 与 `render_markdown` 渲染「修复收敛效率（1.2）」与「多维质量代理（1.1，保守可复算）」两节 Markdown；旧 JSON 无 `generated_test` / 无 details 时自动降级为 N/A 或跳过章节，不崩溃。全量 1163 passed |
| 0.9.13 | 2026-09-14 | 错误分类 10→12 类（PATCH_VALIDATION_FAILED + RAG_RETRIEVAL_EMPTY 状态细化，`refine_failure_category()` 任务收尾判定）、成本告警阈值可配（`APIManagerConfig.cost_alert_threshold`，默认 2.0）、SWE-bench 源码导出自动化（`scripts/export_swe_bench_source.py` + `tasks_missing_source()`）、RAG 指标自动汇总（按检索类型分解 + RAG 命中 × 失败类别交叉表）、脱敏完整审计（APIManager 7 处日志就地 `_redact()` + `get_status()` base_url 出口脱敏；脱敏审计原 `docs/redaction_audit.md` 已并入 README 安全章节，性能剖析原 `docs/performance_profile_report.md` 已并入 `docs/performance_guide.md` 第九章）；全量 1158 passed |
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
