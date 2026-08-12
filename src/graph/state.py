"""
全局状态定义：所有智能体之间通过此状态传递信息。
使用 TypedDict 确保类型安全。
新增 error_category、rag_references 字段支持分层修复和检索增强生成。
"""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class AITesterState(TypedDict, total=False):
    """
    多智能体工作流的全局状态。

    字段说明:
        task_uuid (str): 数据库任务主键（用于记录实验数据）。
        target_file (str): 被测代码文件路径。
        target_function (str | None): 指定被测函数名，None 表示测试全部。
        target_code (str): 被测代码全文。
        test_plan (Dict[str, Any] | None): PlannerAgent 输出的测试计划（含 logic_analysis）。
        generated_test (str | None): GeneratorAgent 生成的测试代码。
        test_passed (bool | None): 测试是否全部通过。
        test_output (str | None): 测试执行输出。
        coverage_report (float | None): 代码覆盖率（0-100）。
        failed_cases (List[Dict[str, str]] | None): 失败用例列表。
        diagnosis (str | None): DebuggerAgent 的根因分析。
        error_category (str | None): 错误类型（syntax/assertion/runtime/timeout/unknown）。
        patch (str | None): DebuggerAgent 生成的修复代码。
        iteration (int): 当前修复迭代次数。
        max_iterations (int): 最大迭代次数（来自配置）。
        repair_history (List[Dict[str, Any]]): 每次修复的详情记录。
        rag_references (List[Dict[str, Any]] | None): RAG 检索到的相似历史案例。
    """

    task_uuid: str
    target_file: str
    target_function: str | None
    target_code: str
    test_plan: Dict[str, Any] | None
    generated_test: str | None
    test_passed: bool | None
    test_output: str | None
    coverage_report: float | None
    failed_cases: List[Dict[str, str]] | None
    diagnosis: str | None
    error_category: str | None
    patch: str | None
    iteration: int
    max_iterations: int
    repair_history: List[Dict[str, Any]]
    rag_references: List[Dict[str, Any]] | None
