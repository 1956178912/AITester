> **语言 / Language**：[English](api_reference.en.md) | 简体中文（本文）

# AITester API 参考文档

> 本文档描述 AITester 的核心类和方法，供开发者集成和扩展使用。
> 最后更新：2026-09-19（0.2 代码质量优化轮次：RAG 降级守卫抽取 / 多函数补丁排序 O(n·m)→O(n+m) / 实验排名绑定修复 / 库名白名单 / 批量健康检查间隔可配 / 脱敏双实现收敛；全量 1460 测试用例 / 覆盖率 96%）

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
| `apply_multi_function_patch()` | `code: str`, `patches: list[dict]` | `tuple[str, bool]` | 多函数同时修复：每项 patch 为 `{"function_name": str, "patch": str}`；按函数起始行号从高到低应用（避免行号偏移）。0.2 性能优化：排序 key 复用预切分行（O(n+m)，此前每个 patch 各自 split 一遍代码 O(n·m)） |
| `safe_apply_patch()` | `code`, `patch` | `tuple[str, bool]` | 应用补丁后做语法校验，失败自动回滚到原始代码 |

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

venv_dir = venv_cache_dir(["pandas"])  # 按依赖组合 + 当前 Python 版本的磁盘缓存目录（4.4 多版本支持）
venv_dir_310 = venv_cache_dir(["pandas"], python_version="3.10")  # 指定 Python 版本（py3.10 前缀隔离）
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
| `venv_cache_dir()` | `required_packages: list[str]`, `python_version: str \| None = None` | `str` | 4.4 多版本缓存：按依赖组合 + Python 版本计算缓存目录（`python_version` 为 None 时取 `sys.version_info` 前两位；不同版本目录隔离存放，避免交叉复用） |
| `create_venv()` | `venv_dir: str`, `timeout: int` | `str` | 创建 venv 并返回 python 解释器路径（磁盘缓存复用） |
| `install_packages()` | `venv_python`, `packages`, `timeout` | `bool` | 在 venv 内 pip install（失败返回 False，不抛异常） |
| `get_venv_cache_stats()` | 无 | `dict` | 4.4 依赖缓存命中率统计：进程内累计 hit/create 事件 + 落盘 JSON 跨进程聚合，返回 `hit_rate = hits/(hits+creates)` |
| `list_venv_cache()` | 无 | `list[dict]` | 4.4 列出缓存目录所有 venv（name / path / size_mb / created_at） |
| `clear_venv_cache()` | `max_age_days: int \| None`, `max_size_mb: int \| None` | `dict` | 4.4 按年龄 / 大小过滤清理缓存，两者均 None 时清空 |
| `get_venv_cache_size_mb()` | 无 | `float` | 4.4 改进：统计 venv 缓存目录总大小（MB，保留 2 位小数，目录不存在返回 0.0） |
| `check_venv_cache_size()` | 无 | `dict` | 4.4 改进：缓存容量监控，返回 `{size_mb, threshold_mb(5120), exceeded, recommendation}`；超过 5GB 阈值时 `exceeded=True` 并给出清理建议（只监控不自动清理） |

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

state = create_initial_state(
    task_uuid="t1", target_file="/p.py", target_code="def f(): pass", target_function=None, max_iterations=3
)
# 工作流执行后 state["execution_trace"] 形如：
[
    {
        "iteration": 0,
        "passed": False,
        "coverage": 40.0,
        "coverage_delta": None,  # 首轮无前一轮
        "elapsed_seconds": 2.0,
        "reward_signals": {  # 保守线性归一，仅记录观测，不参与路由
            "correctness": 0.0,  # 1.0 if passed else 0.0
            "efficiency": 0.93,  # 1 - elapsed / EXECUTION_TIMEOUT
            "simplicity": 0.97,  # 1 - elapsed / (EXECUTION_TIMEOUT * 2)
        },
    },
    {
        "iteration": 1,
        "passed": True,
        "coverage": 85.0,
        "coverage_delta": 45.0,  # 85 - 40
        "elapsed_seconds": 3.0,
        "reward_signals": {"correctness": 1.0, "efficiency": 0.9, "simplicity": 0.95},
    },
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

**RAG 降级守卫（0.2 新增）**：`src/graph/rag.py` 的 `rag_guarded` 统一了 `nodes.py` 中 4 处同构的「ENABLE_RAG 前置判断 + 取检索器单例 + try/except 降级」模板（generator 检索 / executor 入库 / debugger 检索 / debugger 入库）。采用依赖注入式设计（`enabled` / `module_available` / `retriever_cls` / `get_retriever` 作为参数传入，而非模块内直读全局），保持历史 patch 路径（`src.graph.nodes.ENABLE_RAG` / `get_rag_retriever` 等）继续有效。未来调整 RAG 降级策略（失败计数、熔断等）只改 `rag_guarded` 一处，4 个调用点不动。

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
| `CROSS_FILE_BIDIRECTIONAL` | bool | false | 2.2 跨文件双向依赖图：`CROSS_FILE_ENABLE=true` 基础上额外收集"其他模块→entry"反向依赖边（被调用方视角），使修复计划同步更新调用方模块；需配合 `CROSS_FILE_ENABLE=true` 生效，独立开关保证两级保守 |
| `ADVERSARIAL_DEBUGGING_ENABLE` | bool | false | 3.1 对抗性推理：Debugger 生成补丁前注入 2-3 个"击穿当前实现"的对抗性意图假设（AdverIntent-Agent 式）+ 生成针对性测试，生成后独立批评者评估，被击穿则重生成一次补丁；纯观测层，启用会增加 2-4 次 LLM 调用/修复轮 |
| `API_CIRCUIT_BACKOFF` | bool | true | 4.4 API 熔断器指数退避开关：`mark_failure` 冷却期改按 `base * 2^open_count` 指数退避（封顶 `half_open_probe_penalty_cap_seconds`），彻底死掉的 provider 冷却期单调增长；设 false 回退 4.2 固定冷却期口径（便于对比实验） |
| `API_PROMETHEUS_EXPORT` | bool | false | 4.4 Prometheus 指标导出开关：启用后 `APIManager.to_prometheus_text()` 输出 7 类指标（health / circuit_state / open_remaining_s / open_count / probe_success_rate / success_rate / avg_response_ms）供监控抓取；纯旁路不影响既有路由行为 |
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
| `batch_health_check_interval` | float | 0.1 | 批量健康检查节点间隔（秒）：串行探测时避免瞬时流量触发限流；0 表示纯串行排队（大节点池场景）；0.1 保持历史默认行为 |

> 监控：`get_status()` 每节点输出 `circuit_open_remaining_s`（熔断冷却剩余秒）与 `circuit_state`（`closed` / `open` / `half_open` 三态，仅 `enable_half_open_probe=True` 时报告 half_open）。
>
> **4.4 指数退避 + Prometheus 导出**：`API_CIRCUIT_BACKOFF=true`（默认）时，`mark_failure` 冷却期改按 `base * 2^circuit_open_count` 指数退避（封顶 `half_open_probe_penalty_cap_seconds`），彻底死掉的 provider 冷却期单调增长（60s → 120s → 240s → …），避免反复短冷却打同一死点；`mark_success` 重置 `circuit_open_count`。`get_status()` 额外暴露 `circuit_open_count` / `half_open_success` / `half_open_failure` / `half_open_probe_success_rate`。`API_PROMETHEUS_EXPORT=true`（默认 false）时，`APIManager.to_prometheus_text()` 导出 7 类 Prometheus 指标（`aitester_api_health` / `aitester_api_circuit_state` / `aitester_api_circuit_open_remaining_s` / `aitester_api_circuit_open_count` / `aitester_api_half_open_probe_success_rate` / `aitester_api_success_rate` / `aitester_api_avg_response_ms`）供监控抓取，纯旁路不影响既有路由行为。

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
| 0.4 | 2026-09-20 | 五大章节系统能力增强：1.1 评估指标深化（异味 EagerTest/LackOfCohesion + 收敛 token 效率 + 难度分层迭代 + 变异-断言交叉 + RAG token/相似度 + 根因趋势 + 污染交叉）；1.2 变异反馈闭环（boundary_shift/return_void 变异体 + prompt 注入 + run_single_task 开关修复）；2.1 多维污染检测（结构级 AST 骨架 LCS + 语义级词袋余弦 + 抗污染基准注册表）；2.2 跨文件双向依赖图（反向依赖边 + 符号定义行定位，`CROSS_FILE_BIDIRECTIONAL` 默认 false）；3.1 对抗性推理（AdverIntent + 批评者评估 + 补丁重生成，`ADVERSARIAL_DEBUGGING_ENABLE` 默认 false）；3.2 执行反馈动态迭代策略 + 多候选行级信用分配（BOOSTAPR 式）；4.4 熔断器指数退避 + Prometheus 导出（`API_CIRCUIT_BACKOFF` 默认 true / `API_PROMETHEUS_EXPORT` 默认 false）+ venv 缓存容量监控（5GB 阈值，只监控不自动清理）；4.2 redact_dict 递归脱敏 + 降级路径补 JWT 拦截 + 注入回归 CI 用例；5.2 错误分类体系 12→14 类（EXECUTION_TRACE_MISSING + MULTI_CANDIDATE_ALL_REJECTED）；全量 1548 测试通过 / 零回归 |
| 0.2 | 2026-09-19 | 代码质量与可靠性优化轮次（无新功能，零功能破坏）：RAG 降级守卫抽取（`graph/rag.py` 新增依赖注入式 `rag_guarded`，统一 `nodes.py` 4 处同构模板，历史 patch 路径不变）；多函数补丁排序 O(n·m)→O(n+m)（`patch_applier.py` 新增 `_find_function_start_line_in_lines` 预切分行复用）；实验排名绑定修复（`experiments/analysis.py` 按 name/value 绑定排序 + 新增乱序插入回归测试，全量 1459→1460）；数据库库名白名单（`init_db.py`，堵环境变量注入 SQL 向量）；懒导入消除（`base_agent.py`）；脱敏双实现收敛（`llm_client._redact_log_text` / `api_manager._redact`）；批量健康检查间隔提为可配置项 `APIManagerConfig.batch_health_check_interval`；tests/ 存量 Ruff 告警 24 条清理 + 1 处恒真断言修复；`ruff check src/ tests/` 全绿 |
| 0.1 | 2026-09-18 | 首个正式版本：四智能体协作架构（Planner/Generator/Executor/Debugger）+ 十二类错误分层修复 + 逻辑驱动 CoT；多基线对比（aitester/plain_llm/single_agent）+ SWE-bench/Defects4J-Python/合成数据集支持；SWE-bench 源码导出自动化 + 数据污染检测；统计检验（t 检验/Mann-Whitney U/Cohen's d）；结果分析层（修复收敛/边界覆盖/变异得分/断言强度/执行反馈轨迹）；内置变异测试生成器 + 测试异味检测；结构化 JSONL 追踪层；多候选补丁；成本感知路由 + 熔断冷却期 + 半开探测；跨文件修复；断言增强；Docker 隔离执行；依赖缓存监控 + clean-venv-cache CLI；Ruff + pre-commit + GitHub Actions CI；全量 1459 测试用例 / 覆盖率 96% |

