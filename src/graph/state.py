"""
全局状态定义模块：所有智能体之间通过此状态传递信息。

使用 TypedDict 确保类型安全，字段说明详见类文档字符串。
新增 error_category、rag_references 字段支持分层修复和检索增强生成。
"""

from __future__ import annotations

from typing import Any, TypedDict


class AITesterState(TypedDict, total=False):
    """
    多智能体工作流的全局状态。

    该 TypedDict 定义了工作流中所有节点共享的状态字段。
    使用 total=False 表示所有字段均为可选（可在不同阶段逐步填充）。

    字段含义详解：

    ── 任务标识 ──────────────────────────────────────────────
    task_uuid (str):
        数据库任务主键，用于记录实验数据。
        格式通常为 "<filename>_<function>_<timestamp>"，便于日志追踪。

    ── 输入信息 ──────────────────────────────────────────────
    target_file (str):
        被测代码文件路径（绝对路径或相对于项目根目录的路径）。
        Executor 使用此路径设置 PYTHONPATH 并写入补丁文件。

    target_function (str | None):
        指定被测函数名。若为 None，则测试文件中所有函数。
        用于 -k 参数过滤 pytest 运行。

    module_name (str):
        模块文件名（不含 .py 后缀），用于生成正确的 import 语句。
        例如：target_file="examples/calculator.py" → module_name="calculator"

    target_code (str):
        被测代码全文（字符串形式）。
        首次从文件读取，后续迭代中可能被补丁更新。

    ── Planner 输出 ──────────────────────────────────────────
    test_plan (Dict[str, Any] | None):
        PlannerAgent 输出的测试计划，包含：
        - function_name: 目标函数名
        - logic_analysis: 输入域/输出域/前置条件/后置条件/边界情况
        - test_cases: 测试用例列表

    ── Generator 输出 ────────────────────────────────────────
    generated_test (str | None):
        GeneratorAgent 生成的 pytest 测试代码字符串。
        Executor 将此代码写入临时文件后执行。

    ── Executor 输出 ─────────────────────────────────────────
    test_passed (bool | None):
        测试是否全部通过（returncode == 0）。

    test_output (str | None):
        pytest 完整输出文本（stdout + stderr），用于诊断失败原因。

    coverage_report (float | None):
        代码覆盖率百分比（0-100），从 pytest-cov 输出的 TOTAL 行解析。

    failed_cases (List[Dict[str, str]] | None):
        失败用例列表，每项为 {"name": str, "error": str}。
        由 _parse_failed_cases 从 pytest 输出中提取。

    ── Debugger 输出 ─────────────────────────────────────────
    diagnosis (str | None):
        DebuggerAgent 的根因分析文本（中文描述）。

    error_category (str | None):
        错误类型枚举字符串，取值：
        "syntax" | "runtime" | "assertion" | "timeout" | "unknown"

    patch (str | None):
        DebuggerAgent 生成的修复代码（含 ```python 标记）。
        PatchApplier 将其应用到原代码并写入文件。

    ── 迭代控制 ──────────────────────────────────────────────
    iteration (int):
        当前修复迭代次数（从 0 开始）。
        每次进入 debugger → patch_applier 循环后递增。

    max_iterations (int):
        最大迭代次数（来自 config.MAX_ITERATIONS，默认 3）。
        达到此值后 _should_debug 返回 "done" 结束流程。

    repair_history (List[Dict[str, Any]]):
        每次修复的详情记录，每项含：
        - iteration: 迭代编号
        - diagnosis: 根因分析
        - error_category: 错误类型
        - patch_applied: 补丁是否成功应用

    ── RAG 检索结果 ──────────────────────────────────────────
    rag_references (List[Dict[str, Any]] | None):
        RAG 检索到的相似历史案例列表。
        Generator 和 Debugger 各自使用不同的检索查询。
    """

    # 任务标识
    task_uuid: str
    # 输入信息
    target_file: str
    target_function: str | None
    module_name: str
    target_code: str
    # Planner 输出
    test_plan: dict[str, Any] | None
    # Generator 输出
    generated_test: str | None
    # Executor 输出
    test_passed: bool | None
    test_output: str | None
    coverage_report: float | None
    failed_cases: list[dict[str, str]] | None
    # Debugger 输出
    diagnosis: str | None
    error_category: str | None
    patch: str | None
    # 迭代控制
    iteration: int
    max_iterations: int
    repair_history: list[dict[str, Any]]
    # RAG 检索结果
    rag_references: list[dict[str, Any]] | None
