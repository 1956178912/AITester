# AITester 错误报告生成器使用指南

> 本文档介绍如何使用 `src/reports/` 模块生成结构化的测试失败诊断报告。

## 快速开始

```python
from src.reports import ReportGenerator, ReportFormat

# 创建报告生成器
generator = ReportGenerator()

# 生成错误报告
report = generator.generate(
    task_id="task_001",
    target_file="examples/calculator.py",
    target_function="divide",
    error_output="FAILED test_calculator.py::test_divide - ZeroDivisionError: division by zero",
    coverage=75.0,
)

# 输出不同格式
print(report.to_text())      # 纯文本格式
print(report.to_json())      # JSON 格式
print(report.to_markdown())  # Markdown 格式

# 保存到文件
generator.save_report(report, output_dir="./reports", format=ReportFormat.JSON)
```

## 支持的错误类型

| 错误分类 | 说明 | 示例 |
|---------|------|------|
| `SYNTAX` | 语法/编译错误 | `ImportError`, `SyntaxError` |
| `RUNTIME` | 运行时异常 | `ZeroDivisionError`, `TypeError` |
| `ASSERTION` | 断言失败 | `AssertionError` |
| `TIMEOUT` | 执行超时 | `pytest-timeout` |
| `UNKNOWN` | 无法识别 | 其他错误 |

## 报告内容

生成的报告包含以下信息：

1. **基本信息**：任务 ID、被测文件、被测函数
2. **错误分类**：错误类型和子类型
3. **错误位置**：文件名、行号、列号（如有）
4. **根本原因**：自动分析的错误原因
5. **修复建议**：针对性的修复方案列表
6. **失败用例**：解析出的失败测试用例
7. **历史修复记录**：迭代修复历史

## 输出格式

### 文本格式 (`.txt`)

```
============================================================
AITester 错误诊断报告
============================================================

任务 ID: task_001
被测文件: examples/calculator.py
被测函数: divide
错误分类: runtime
迭代次数: 1
当前覆盖率: 75.0%

--- 错误信息 ---
FAILED test_calculator.py::test_divide - ZeroDivisionError: division by zero

--- 根本原因 ---
除零错误：被除数可能为 0，需要添加边界条件检查

--- 修复建议 ---
1. 在被除数使用前添加零值检查
2. 使用 try-except 捕获除零异常
3. 添加测试用例覆盖除数为 0 的场景

============================================================
报告生成时间: 2026-08-18T10:00:00
============================================================
```

### JSON 格式 (`.json`)

```json
{
  "task_id": "task_001",
  "target_file": "examples/calculator.py",
  "target_function": "divide",
  "error_category": "runtime",
  "root_cause": "除零错误：被除数可能为 0，需要添加边界条件检查",
  "suggested_fix": "1. 在被除数使用前添加零值检查\n2. 使用 try-except 捕获除零异常",
  "failed_cases": [...],
  "coverage": 75.0,
  "created_at": "2026-08-18T10:00:00"
}
```

### Markdown 格式 (`.md`)

```markdown
# AITester 错误诊断报告

| 字段 | 值 |
|------|-----|
| 任务 ID | `task_001` |
| 被测文件 | `examples/calculator.py` |
| 被测函数 | `divide` |

## 错误信息

```
FAILED test_calculator.py::test_divide - ZeroDivisionError: division by zero
```

## 根本原因

除零错误：被除数可能为 0，需要添加边界条件检查

## 修复建议

1. 在被除数使用前添加零值检查
2. 使用 try-except 捕获除零异常
```

## API 参考

### `ReportGenerator.generate()`

```python
def generate(
    task_id: str,
    target_file: str,
    target_function: str,
    error_output: str,
    failed_cases: list[dict] | None = None,
    coverage: float = 0.0,
    iteration_count: int = 0,
    history: list[dict] | None = None,
) -> ErrorReport
```

**参数：**
- `task_id`: 任务唯一标识
- `target_file`: 被测文件路径
- `target_function`: 被测函数名
- `error_output`: 测试执行错误输出
- `failed_cases`: 失败的测试用例列表（可选）
- `coverage`: 代码覆盖率（可选，默认 0.0）
- `iteration_count`: 已修复迭代次数（可选，默认 0）
- `history`: 历史修复记录（可选）

**返回：** `ErrorReport` 对象

### `ReportGenerator.save_report()`

```python
def save_report(
    report: ErrorReport,
    output_dir: str = "reports",
    format: ReportFormat = ReportFormat.TEXT,
) -> Path
```

**参数：**
- `report`: 要保存的报告对象
- `output_dir`: 输出目录（默认 `./reports`）
- `format`: 输出格式（默认 TEXT）

**返回：** 报告文件路径

### `get_report_generator()`

```python
def get_report_generator() -> ReportGenerator
```

获取报告生成器单例实例。

## 集成到工作流

在 `src/graph/workflow.py` 中添加报告生成节点：

```python
from src.reports import ReportGenerator, ReportFormat

async def _generate_report_node(state: AITesterState) -> dict:
    """生成错误诊断报告节点。"""
    if state.get("error_output"):
        generator = get_report_generator()
        report = generator.generate(
            task_id=state["task_id"],
            target_file=state["target_file"],
            target_function=state["target_function"],
            error_output=state["error_output"],
            coverage=state.get("coverage", 0.0),
            iteration_count=state.get("iteration_count", 0),
        )
        generator.save_report(report, format=ReportFormat.JSON)
    return {}
```

## 注意事项

1. 报告生成器依赖 `ErrorClassifier` 进行错误分类
2. 失败用例解析基于 pytest 输出格式
3. 报告文件默认保存在 `./reports/` 目录
4. JSON 格式适合程序化处理，Markdown 适合人类阅读
