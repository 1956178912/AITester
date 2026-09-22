"""
全局状态定义模块：所有智能体之间通过此状态传递信息。

使用 TypedDict 确保类型安全，字段说明详见类文档字符串。
新增 error_category、rag_references 字段支持分层修复和检索增强生成。
"""

from __future__ import annotations

import os
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

    regeneration_count (int):
        触发 "regenerate"（重新生成测试代码）的次数（从 0 开始）。
        达到最大迭代后，若诊断指向测试生成错误，_should_debug 会路由回
        generator 重新生成；为避免 generator↔executor 无限乒乓（旧 diagnosis
        关键词反复命中导致每轮都再生成，最终撞上 LangGraph recursion_limit），
        该计数在每次再生成时 +1，达到上限（workflow._MAX_REGENERATIONS）后
        _should_debug 不再路由 regenerate 而是返回 "done"。

    ─── 执行控制（可选，由 CLI 注入）──────────────────────────────
    execution_timeout (int | None):
        单次测试执行的超时秒数（CLI --timeout 注入）。
        未提供时 Executor 回退到 config.EXECUTION_TIMEOUT。

    coverage_threshold (float | None):
        覆盖率达标阈值百分比（CLI --coverage-threshold 注入）。
        未提供时 CLI 汇总输出使用 config.COVERAGE_THRESHOLD。

    repair_history (List[Dict[str, Any]]):
        每次修复的详情记录，每项含：
        - iteration: 迭代编号
        - diagnosis: 根因分析
        - error_category: 错误类型
        - patch_applied: 补丁是否成功应用

    execution_trace (List[Dict[str, Any]]):
        3.2 执行反馈轨迹：每次 Executor 执行的记录（3.2 默认常开，
        始终写入；纯观测层，不影响修复流程），每项含：
        - iteration: 迭代编号
        - passed: 测试是否通过
        - coverage_delta: 相对上一轮覆盖率的增减（首轮为 None）
        - elapsed_seconds: 本节点墙钟耗时
        - reward_signals: 多维度奖励信号 {correctness / efficiency /
          simplicity}（保守线性归一，供未来执行反馈 RL 训练备料；
          仅记录观测，不参与工作流路由）

    ── RAG 检索结果 ──────────────────────────────────────────
    rag_references (List[Dict[str, Any]] | None):
        RAG 检索到的相似历史案例列表。
        Generator 和 Debugger 各自使用不同的检索查询。

    rag_stats (List[Dict[str, Any]] | None):
        RAG 检索质量指标累计（P1：消融实验单独报告检索质量）。
        每项为 {"kind": "test_cases"|"repairs", "results": int,
                "max_similarity": float | None, "avg_similarity": float | None}，
        由 Generator/Debugger 节点在检索后追加。
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
    regeneration_count: int
    repair_history: list[dict[str, Any]]
    # 3.2 执行反馈轨迹（默认常开：纯观测层，随 executor 节点追加）
    execution_trace: list[dict[str, Any]]
    # 执行控制（可选，由 CLI 注入）
    execution_timeout: int | None
    coverage_threshold: float | None
    # RAG 检索结果
    rag_references: list[dict[str, Any]] | None
    # RAG 检索质量指标累计（P1）
    rag_stats: list[dict[str, Any]] | None
    # 3.5 跨文件修复计划（CROSS_FILE_ENABLE=true 时由 cross_file_analyzer 节点写入）
    cross_file_deps: list[dict[str, Any]] | None
    cross_file_plan: dict[str, Any] | None
    # 1.2 变异反馈闭环（MutGen 式）：上一轮变异测试的存活变异体信息
    # {survived_mutants: list[str], mutation_score: float}
    # 由 run_benchmark 变异评估后写入，Generator 再生成时消费；None 表示无反馈
    mutation_feedback: dict[str, Any] | None
    # 5.2 多候选补丁统计（ENABLE_MULTI_CANDIDATE_PATCH=true 时由 patch_applier 写入）：
    # {"candidates": N, "static_passed": M, "exec_validated": bool, "selected": int | None}
    multi_candidate_stats: dict[str, Any] | None
    # 3.2 改进：执行反馈驱动的动态迭代策略建议（由 executor 节点写入，
    # 纯观测层：基于前几轮覆盖率趋势建议"降低温度/切换修复视角"，
    # 供未来 Debugger 消费；当前仅记录不改变路由）
    iteration_strategy_suggestion: str | None
    # 3.1 双向代码-测试诊断结果（BIDIRECTIONAL_DIAGNOSIS_ENABLE=true 时由
    # debugger 节点写入）：implementation_defect（实现缺陷）/ test_defect（测试缺陷）
    defect_type: str | None
    # 3.1 Review Agent 判定依据文本（defect_type 的补充说明）
    review_reason: str | None
    # 2.3 复现测试专项生成结果（REPRO_TEST_ENABLE=true 时由 generator 节点写入）：
    # 覆盖缺陷触发路径的复现测试代码（先失败后通过）
    repro_test: str | None


def create_initial_state(
    task_uuid: str,
    target_file: str,
    target_code: str,
    max_iterations: int,
    module_name: str | None = None,
    target_function: str | None = None,
    execution_timeout: int | None = None,
    coverage_threshold: float | None = None,
) -> AITesterState:
    """
    创建初始工作流状态的唯一工厂函数。

    此前 CLI（cli/app.py）与 benchmark（experiments/run_benchmark.py）
    各自手写一份初始化字典，TypedDict 新增字段时两处易漂移
    （如 3.5 批次的 cross_file_* 字段仅由节点写入，初始字典不补即缺键，
    后续节点 ``state.get("cross_file_plan")`` 永远 None 而难察觉）。
    收敛为本单一构造点后，新增字段只改一处。

    Args:
        task_uuid: 任务标识（CLI 为 "<file>_<func>_<ts>"，benchmark 为 task_id）。
        target_file: 被测代码文件路径。
        target_code: 被测代码全文。
        max_iterations: 最大修复迭代次数。
        module_name: 模块文件名（不含 .py）；None 时按 target_file 推导
            （``os.path.splitext(os.path.basename(target_file))[0]``）。
        target_function: 指定被测函数名；None 表示测试全部函数。
        execution_timeout: 单次测试执行超时秒数（CLI 注入）；None 时
            Executor 回退 config.EXECUTION_TIMEOUT。
        coverage_threshold: 覆盖率达标阈值百分比（CLI 注入）；None 时
            CLI 汇总回退 config.COVERAGE_THRESHOLD。

    Returns:
        完整初始化的 AITesterState，所有 TypedDict 字段均显式赋值
        （未提供的可选项为 None，列表项为初始空值）。
    """
    if module_name is None:
        module_name = os.path.splitext(os.path.basename(target_file))[0]

    return AITesterState(
        # 任务标识
        task_uuid=task_uuid,
        # 输入信息
        target_file=target_file,
        target_function=target_function,
        module_name=module_name,
        target_code=target_code,
        # Planner 输出
        test_plan=None,
        # Generator 输出
        generated_test=None,
        # Executor 输出
        test_passed=None,
        test_output=None,
        coverage_report=None,
        failed_cases=None,
        # Debugger 输出
        diagnosis=None,
        error_category=None,
        patch=None,
        # 迭代控制
        iteration=0,
        max_iterations=max_iterations,
        regeneration_count=0,
        repair_history=[],
        # 3.2 执行反馈轨迹（随 executor 节点追加，初始空列表）
        execution_trace=[],
        # 执行控制（可选，由 CLI 注入）
        execution_timeout=execution_timeout,
        coverage_threshold=coverage_threshold,
        # RAG 检索结果
        rag_references=None,
        rag_stats=None,
        # 3.5 跨文件修复计划
        cross_file_deps=None,
        cross_file_plan=None,
        # 1.2 变异反馈闭环（默认 None，由 run_benchmark 变异评估后注入）
        mutation_feedback=None,
        # 5.2 多候选补丁统计（默认 None，启用多候选时由 patch_applier 节点写入）
        multi_candidate_stats=None,
        # 3.2 改进：迭代策略建议（默认 None，executor 节点写入观测层建议）
        iteration_strategy_suggestion=None,
        # 3.1 双向诊断结果（默认 None，启用双向诊断时由 debugger 节点写入）
        defect_type=None,
        review_reason=None,
        # 2.3 复现测试生成结果（默认 None，启用复现测试生成时由 generator 节点写入）
        repro_test=None,
    )
