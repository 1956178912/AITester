"""
工作流节点函数模块。

从 workflow.py 拆分而来（代码可维护性优化）：承载 LangGraph 工作流图的各个
节点实现（Planner / Generator / Executor / Debugger / CrossFileAnalyzer /
PatchApplier）及其辅助函数（路径白名单校验、原子写盘、多候选补丁、Planner
输出校验与默认计划）。图构建与条件路由保留在 workflow.py，通过
`from .nodes import ...` 注册这些节点函数。
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict
from typing import Any, cast

from config import (
    ENABLE_RAG,
    EXECUTION_TIMEOUT,
    EXECUTOR_AUTO_INSTALL_DEPS,
    EXECUTOR_DEP_INSTALL_TIMEOUT,
    EXECUTOR_DOCKER_IMAGE,
    EXECUTOR_USE_DOCKER,
    EXECUTOR_USE_VENV,
    MAX_ITERATIONS,
    MAX_REGENERATIONS,
    detection_first_enabled,
)

# S4（2026-10-09 R4）：DebuggerAgent / ExecutorAgent 顶层导入保留（noqa）——
# nodes.py 自身已不直接构造二者（patch 簇拆分后由 patch_io / debugger 模块
# 构造），但 agents_cache.py 的延迟导入 `from src.graph.nodes import
# DebuggerAgent/ExecutorAgent` 与测试 `patch("src.graph.nodes.DebuggerAgent")`
# 的历史 mock 口径依赖此命名空间转发（与 flags re-export 同口径，须保留）。
from src.agents.debugger import DebuggerAgent  # noqa: F401
from src.agents.executor import ExecutorAgent  # noqa: F401
from src.agents.executor_runtime import summarize_execution_attempts
from src.agents.generator import GeneratorAgent, _repro_test_enabled
from src.agents.planner import PlannerAgent, spec_oracle_examples_enabled
from src.agents.rogue_monitor import rogue_monitor_enabled
from src.budget.cost_budget import BudgetExceededError

# S7（2026-10-08 R3）：Agent 复用缓存已拆分到 src/graph/agents_cache.py，
# 此处 re-export 保持 `from src.graph.nodes import get_or_create_agent` 等
# 历史导入路径不变。
from src.graph.agents_cache import (  # noqa: F401
    _MAX_CACHED_AGENTS,
    _agent_instance_cache,
    _agent_instance_cache_lock,
    _executor_agent_cache,
    _executor_agent_cache_lock,
    _get_or_create_debugger_agent,
    _get_or_create_executor_agent,
    clear_agent_instance_cache,
    clear_executor_agent_cache,
    get_or_create_agent,
)

# S7（2026-10-08 R3）：debugger 节点簇已拆分到 src/graph/debugger.py，此处
# re-export 保持 `from src.graph.nodes import _debugger_node` 历史导入路径不变。
from src.graph.debugger import (  # noqa: F401
    _build_failure_frequency_section,
    _debugger_node,
    _diagnosis_node,
    _resolve_target_module,
)
from src.graph.event_bus import (
    PlanGenerated,
    publish_event,
    publish_patch_applied,
    publish_tests_executed,
)

# S7（2026-10-08 R3）：功能开关辅助已拆分到 src/graph/flags.py，此处
# re-export 保持 `from src.graph.nodes import _xxx_enabled` 历史导入路径不变。
# 注：下一行 F401 豁免是因为部分开关已不再被 nodes.py 直接使用（改由
# debugger / agents_cache 等拆分模块消费），但测试与历史调用方仍从
# src.graph.nodes 导入，须保留。
from src.graph.flags import (  # noqa: F401
    _agent_reuse_enabled,
    _boundary_triplets_enabled,
    _branch_coverage_inject_enabled,
    _context_tier_downgrade_enabled,
    _detection_spec_mode,
    _failure_frequency_enabled,
    _feedback_compression_enabled,
    _fl_spectral_enabled,
    _flaky_check_enabled,
    _oracle_enhance_enabled,
    _oracle_validate_enabled,
    _patch_resample_enabled,
    _patch_resample_max,
    _patch_resample_temperature,
    _probe_snapshot_locate_enabled,
    _repo_core_protection_enabled,
    _runtime_probe_enabled,
    _spec_ir_dsl_enabled,
    _spec_ir_enabled,
    _spec_oracle_exec_enabled,
)

# S4（2026-10-09 R4）：补丁应用安全核心已拆分到 src/graph/patch_io.py，
# 此处 re-export 保持 `from src.graph.nodes import _safe_write_patch` 等
# 历史导入路径不变（与 S7 拆分 debugger/flags 同口径）。
from src.graph.patch_io import (  # noqa: F401
    _ALLOWED_WRITE_ROOTS,
    _ALLOWED_WRITE_ROOT_PREFIXES,
    _HARD_ERROR_CATEGORIES,
    _HAS_FUNC_DEF_RE,
    _PROTECTED_CORE_BASENAMES,
    _PROTECTED_CORE_DIRS,
    _is_repo_core_path,
    _is_within_allowed_roots,
    _rollback_last_patch,
    _safe_write_patch,
    _select_multi_candidate_patch,
    _write_file_atomic,
)
from src.graph.rag import (
    RAG_MODULE_AVAILABLE,
    TestCaseRetriever,
    _build_rag_stat,
    get_rag_retriever,
    rag_guarded,
)
from src.graph.state import AITesterState

# S7（2026-10-08 R3）：trace/reward 簇已拆分到 src/graph/trace_reward.py，
# 此处 re-export 保持 `from src.graph.nodes import _record_execution_trace`
# 等历史导入路径与 workflow.py 的 re-export 逐字节不变。
from src.graph.trace_reward import (  # noqa: F401
    _append_trace_record,
    _compute_reward_signals,
    _dynamic_temperature_from_suggestion,
    _patch_line_delta_for_reward,
    _record_execution_trace,
    _suggest_iteration_strategy,
)
from src.graph.tracing import _trace_node
from src.tools.cross_file import analyze_multi_entry_deps, cross_file_enabled
from src.tools.multi_candidate import (
    multi_candidate_available,
)
from src.tools.patch_applier import apply_patch_to_code
from src.tools.patch_rollback import snapshot_rollback_enabled
from src.utils.env_utils import env_flag, env_flag_opt_out, env_int

# 模块级 logger，用于记录节点执行过程，便于实验追踪和问题排查
logger = logging.getLogger(__name__)

# 修复历史上限：超过后仅保留最近 N 条，防止长迭代循环占用内存（经验值 5）
_MAX_REPAIR_HISTORY = 5

# P0 1.1 分层代码压缩：调用链展开层数（与 BaseAgent.truncate_code 同口径，
# CODE_FOCUS_DEPTH 环境变量，默认 1；跨文件任务建议 2）
# F 轮加固：改经 env_int 容错解析——此前裸 int() 在坏值（CODE_FOCUS_DEPTH=abc）
# 时于 import 期抛 ValueError，即一个拼错的环境变量让整个 nodes 模块不可导入。
CODE_FOCUS_DEPTH: int = env_int("CODE_FOCUS_DEPTH", 1)


# P0-4（REVIEW_2026_FRONTIER I-07，2026-10-10）：规约 oracle 行级判定取值域。
# 结果行 spec_oracle_verdict 直接读取本取值域（键集合同构，失败分支由实验层
# None 占位）——修复 T3 审查指出的"注入 oracle 造成的红与 LLM 断言造成的红
# 在结果行里逐位同构"缺口（注入量 / 注入后判定首次可单独归因）。
_SPEC_ORACLE_VERDICT_NOT_ATTEMPTED = "not_attempted"
_SPEC_ORACLE_VERDICT_COMPILED_EMPTY = "compiled_empty"
_SPEC_ORACLE_VERDICT_INJECTED = "injected"
_SPEC_ORACLE_VERDICT_INJECTED_AND_PASSED = "injected_and_passed"
_SPEC_ORACLE_VERDICT_INJECTED_AND_FAILED = "injected_and_failed"
# N-3（2026-10-17，A-05 后续修复）：**未尝试注入**的可审计原因细分。
# 历史批次只有 "not_attempted" 一个值（无规约材料 / 开关关）；A-05 修复接
# `state["spec_anchor"]` 材料源后，需要把"有材料但不可编译"与"根本没有材料"
# 区分开，否则 df/doc 臂的接线缺口再次不可归因。取值域**向后兼容扩展**：
# 旧值逐字不变（历史 JSON 不受影响），新值只在
# SPEC_ORACLE_EXEC_ENABLE=true 且命中下列材料形态时出现。
_SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_MISSING_TARGET = "not_attempted_missing_target"
_SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_HUMAN_SPEC_ONLY = "not_attempted_human_spec_only"
_SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_ANCHOR_UNPARSEABLE = "not_attempted_anchor_unparseable"
# 判定取值域（state.py 注释与结果行 schema 的共同事实源；新增值须同步文档）
_SPEC_ORACLE_VERDICT_DOMAIN: tuple[str, ...] = (
    _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED,
    _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_MISSING_TARGET,
    _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_HUMAN_SPEC_ONLY,
    _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_ANCHOR_UNPARSEABLE,
    _SPEC_ORACLE_VERDICT_COMPILED_EMPTY,
    _SPEC_ORACLE_VERDICT_INJECTED,
    _SPEC_ORACLE_VERDICT_INJECTED_AND_PASSED,
    _SPEC_ORACLE_VERDICT_INJECTED_AND_FAILED,
)
# 注入产物的测试函数名前缀：主 oracle（spec_ir_v2.compile_spec_oracle）与
# SMT 见证（spec_smt 追加的 test_specir_v2_smt_witness_*）。_executor_node
# 用它们在 pytest 失败清单 / -v 输出里把 oracle 用例单独摘出来。
_SPEC_ORACLE_TEST_NAMES: tuple[str, ...] = ("test_specir_v2_oracle", "test_specir_v2_smt_witness")


def _resolve_spec_oracle_material(state: AITesterState) -> tuple[dict[str, Any] | None, str, str]:
    """N-3（2026-10-17，A-05 后续修复）：解析确定性 oracle 的规约材料。

    四源优先级（**接线缺口修复的关键**：生产 df_spec/doc/union/augment 类臂
    只写 ``state["spec_anchor"]``、Planner 关闭无 ``test_plan``——修复前
    这些臂的 oracle 注入永远 ``not_attempted``）：

    1. ``state["spec_ir"]``：R7/Planner 现场产物（最权威，历史口径不变）；
    2. ``state["test_plan"]["logic_analysis"]``：现场解析（R7 关闭时的历史
       降级口径，与 DSL 层独立降级同源）；
    3. ``state["spec_anchor"]["logic_analysis"]``：预计算锚表材料
       （df_spec / union 臂；A-05 修复新增）；
    4. ``state["spec_anchor"]["human_spec"]``：人类 docstring 规格锚
       （doc / augment 臂）。**非 SpecExpr 材料，不强行编译**——如实返回
       ``not_attempted_human_spec_only``（人类规格→可执行断言的翻译是独立
       研究问题，超出本修复范围）。

    Args:
        state: 工作流状态（spec_ir / test_plan / spec_anchor）。

    Returns:
        (spec_material | None, source 标签, 未尝试时的 verdict)。
        ``source`` 只用于日志/审计；verdict 取值见 ``_SPEC_ORACLE_VERDICT_DOMAIN``。
    """
    from src.specs import parse_logic_analysis as _parse_logic_analysis

    spec_ir = state.get("spec_ir")
    if isinstance(spec_ir, dict) and spec_ir:
        return spec_ir, "spec_ir", _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED

    test_plan = state.get("test_plan")
    if isinstance(test_plan, dict):
        parsed = _parse_logic_analysis(test_plan.get("logic_analysis"))
        if parsed:
            return parsed, "test_plan.logic_analysis", _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED

    anchor = state.get("spec_anchor")
    if isinstance(anchor, dict):
        parsed = _parse_logic_analysis(anchor.get("logic_analysis"))
        if parsed:
            return parsed, "spec_anchor.logic_analysis", _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED
        if anchor.get("logic_analysis") is not None:
            # 锚材料在场但解析为空（形态不合法 / 无任何可识别字段）→ 可审计原因
            return None, "spec_anchor.logic_analysis", _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_ANCHOR_UNPARSEABLE
        human_spec = anchor.get("human_spec")
        if isinstance(human_spec, str) and human_spec.strip():
            return None, "spec_anchor.human_spec", _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_HUMAN_SPEC_ONLY
    return None, "", _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED


def _append_spec_oracle_to_test_with_verdict(generated_test: str, state: AITesterState) -> tuple[str, bool, str]:
    """R1c + P0-4：把确定性规约 oracle 追加到 LLM 生成测试尾部，并给出行级判定。

    compile_spec_oracle 产物（签名感知绑定的可执行断言）与 LLM 测试**并列**
    执行——LLM 测试通过 ≠ 规约 oracle 通过，后者失败 = "逻辑驱动"通道的
    确定性检出。产物经编译层 ast.parse 自检 + "无断言即丢弃"双重守卫
    （spec_ir_v2 口径），注入面与 LLM 生成代码同沙箱档执行。

    Args:
        generated_test: LLM 生成的测试代码。
        state: 工作流状态（spec_ir / test_plan / spec_anchor / target_code /
            module_name / target_function）。材料优先级见
            ``_resolve_spec_oracle_material``：spec_ir →
            test_plan.logic_analysis → spec_anchor.logic_analysis /
            spec_anchor.human_spec。

    Returns:
        (追加后的测试代码, 是否注入, verdict)。verdict（完整取值域见
        ``_SPEC_ORACLE_VERDICT_DOMAIN``）：
        - 无任何规约材料 → "not_attempted"（未尝试编译，历史口径）；
        - 仅人类 docstring 锚（human_spec，非 SpecExpr）→
          "not_attempted_human_spec_only"（不强行编译）；
        - 锚材料在场但解析为空 → "not_attempted_anchor_unparseable"；
        - 有材料但缺函数名 / 模块名 → "not_attempted_missing_target"；
        - 编译产物为空（无可编译子句 / 自检失败 / 意外异常兜底）→
          "compiled_empty"；
        - 注入成功 → "injected"。
    """
    from src.specs import compile_spec_oracle as _compile_spec_oracle
    from src.specs import extract_signature_params as _extract_signature_params

    # N-3（2026-10-17，A-05 后续修复）：四源材料优先级解析（spec_ir →
    # test_plan.logic_analysis → spec_anchor.logic_analysis / human_spec）。
    # 修复前只试前两级 → df_spec/doc/union/augment 类臂（Planner 关闭、只有
    # 锚材料）永远 not_attempted。human_spec（人类 docstring）不强行编译，
    # 如实记 not_attempted_human_spec_only。
    spec_material, material_source, not_attempted_verdict = _resolve_spec_oracle_material(state)
    # Q-1（2026-10-18）：examples 通道双门守门——开关关时即使材料里带 examples
    # （历史缓存/外部构造）也**剥离**后再编译，保证关闭口径与历史逐字节一致；
    # 开关开且材料带 examples 时由 compile_spec_oracle 逐示例编译断言。
    if not spec_oracle_examples_enabled() and isinstance(spec_material, dict) and "examples" in spec_material:
        spec_material = {key: value for key, value in spec_material.items() if key != "examples"}
        material_source = f"{material_source}+examples_stripped"
    oracle_func = str(state.get("target_function") or "")
    if not oracle_func and isinstance(spec_material, dict):
        oracle_func = str(spec_material.get("function_name") or "")
    if not oracle_func and isinstance(state.get("spec_anchor"), dict):
        # 人类规格锚条目通常自带 function_name；无可编译材料时仍保留来源，
        # 便于审计"该任务缺的是材料还是目标函数"（verdict 不变）。
        oracle_func = str((state.get("spec_anchor") or {}).get("function_name") or "")
    if not spec_material:
        return generated_test, False, not_attempted_verdict
    if not (oracle_func and state.get("module_name")):
        return generated_test, False, _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_MISSING_TARGET
    sig_params = _extract_signature_params(state.get("target_code") or "", str(oracle_func))
    try:
        oracle_code = _compile_spec_oracle(
            spec_material,
            target_module=str(state.get("module_name") or ""),
            target_function=str(oracle_func),
            signature_params=sig_params,
        )
    except (SyntaxError, ValueError, TypeError, KeyError) as e:
        # 编译层内部已保守降级，此处兜底捕获意外异常（防注入链路崩图）
        logger.warning("R1c 规约 oracle 编译异常，保守跳过注入：%s", e)
        return generated_test, False, _SPEC_ORACLE_VERDICT_COMPILED_EMPTY
    if not oracle_code:
        return generated_test, False, _SPEC_ORACLE_VERDICT_COMPILED_EMPTY
    logger.info(
        "R1c 确定性规约 oracle 已注入（fn=%s, sig_params=%d, 追加 %d 字符, material=%s）",
        oracle_func,
        len(sig_params or []),  # 签名提取失败时为 None，日志口径按 0 参计
        len(oracle_code),
        material_source,
    )
    return f"{generated_test}\n\n\n{oracle_code}", True, _SPEC_ORACLE_VERDICT_INJECTED


def _append_spec_oracle_to_test(generated_test: str, state: AITesterState) -> tuple[str, bool]:
    """R1c 兼容包装：二元返回（既有调用方 / 既有测试契约不变）。

    需要行级判定（P0-4 spec_oracle_verdict）时改用
    _append_spec_oracle_to_test_with_verdict。
    """
    merged, injected, _verdict = _append_spec_oracle_to_test_with_verdict(generated_test, state)
    return merged, injected


def _spec_oracle_injection_verdict(generated_test: str, state: AITesterState) -> tuple[str, bool | None, str]:
    """开关守门 + 注入 + 行级判定（纯函数，_generator_node 的唯一调用点）。

    Returns:
        (测试代码, spec_oracle_injected, spec_oracle_verdict)

        - 开关关（SPEC_ORACLE_EXEC_ENABLE=false，默认）→ (原文, None,
          "not_attempted")——历史口径零注入，spec_oracle_injected 维持 None；
        - 开关开但无规约材料（未尝试编译）→ (原文, None, "not_attempted")；
        - 开关开、有材料但不可尝试（仅人类规格锚 / 锚不可解析 / 缺目标）
          → (原文, None, "not_attempted_*")——N-3 新增的细粒度可审计值，
          语义均为"未注入"，injected 仍为 None（向后兼容）；
        - 开关开、尝试编译但产物为空 → (原文, False, "compiled_empty")；
        - 注入成功 → (追加产物, True, "injected")（执行后由 _executor_node
          升级为 injected_and_passed / injected_and_failed）。
    """
    if not _spec_oracle_exec_enabled():
        return generated_test, None, _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED
    merged, _injected, verdict = _append_spec_oracle_to_test_with_verdict(generated_test, state)
    if verdict == _SPEC_ORACLE_VERDICT_INJECTED:
        return merged, True, verdict
    if verdict == _SPEC_ORACLE_VERDICT_COMPILED_EMPTY:
        return merged, False, verdict
    return merged, None, verdict


def _spec_oracle_verdict_after_run(state: AITesterState, result: dict[str, Any]) -> str | None:
    """P0-4：把本轮 "injected" 升级为执行后判定（纯函数，_executor_node 调用）。

    判定口径（保守，宁缺毋滥）：
    - 仅 spec_oracle_verdict == "injected" 且 spec_oracle_injected 为真时升级；
      其余（None / not_attempted / compiled_empty / 已升级）返回 None（不写键）；
    - 测试全过（result["passed"]=True）→ "injected_and_passed"（oracle 与
      LLM 断言同文件执行，全过 ⇒ oracle 用例通过）；
    - 失败清单含 oracle 用例名（test_specir_v2_oracle* / SMT 见证）→
      "injected_and_failed"（"逻辑驱动"通道的确定性检出信号）；
    - 失败但失败清单不含 oracle 用例：仅当 pytest -v 输出里显式出现 oracle
      用例 PASSED 行才记 "injected_and_passed"；否则返回 None（收集错误 /
      未执行 / 输出不可解析时保留 "injected" 未决态，不臆测）。

    Args:
        state: 本轮执行前的工作流状态（含 _generator_node 写入的 verdict）。
        result: ExecutorAgent.execute 的返回（passed / failed_cases / output）。

    Returns:
        升级后的 verdict；不适用时为 None（调用方跳过写键）。
    """
    if state.get("spec_oracle_verdict") != _SPEC_ORACLE_VERDICT_INJECTED or not state.get("spec_oracle_injected"):
        return None
    failed_names = [
        str(case.get("name") or "") for case in (result.get("failed_cases") or []) if isinstance(case, dict)
    ]
    if any(any(marker in name for marker in _SPEC_ORACLE_TEST_NAMES) for name in failed_names):
        return _SPEC_ORACLE_VERDICT_INJECTED_AND_FAILED
    output = str(result.get("output") or "")
    # O-1（2026-10-18）仪器加固配套：oracle 执行体在绑定/前件/调用/后件抛非断言
    # 异常时 `pytest.skip("oracle-unavailable: ...")`。此时套件 passed=True 并不
    # 意味着 oracle 通过（它根本没判定）——若显式出现 SKIPPED 行，保留未决态
    # "injected"（不臆测 passed），与独立判读 oracle_suite_verdict=unavailable 对齐。
    if any(
        "SKIPPED" in line and any(marker in line for marker in _SPEC_ORACLE_TEST_NAMES) for line in output.splitlines()
    ):
        return None
    if result.get("passed"):
        return _SPEC_ORACLE_VERDICT_INJECTED_AND_PASSED
    for line in output.splitlines():
        if "PASSED" in line and any(marker in line for marker in _SPEC_ORACLE_TEST_NAMES):
            return _SPEC_ORACLE_VERDICT_INJECTED_AND_PASSED
    return None


def _planner_node(state: AITesterState) -> dict[str, Any]:
    """
    PlannerAgent 节点：生成逻辑驱动的结构化测试计划。

    优化：添加输出验证，确保 Planner 返回符合预期的 JSON 结构。
    若验证失败，使用默认计划兜底。

    这是工作流的第一个节点（当 ENABLE_PLANNER=True 时），负责：
    1. 调用 PlannerAgent 对被测代码进行逻辑分析（输入域/输出域/前置-后置条件/边界情况）
    2. 生成包含 logic_analysis 和 test_cases 的结构化测试计划 JSON
    3. 若 LLM 返回格式不良的 JSON，使用默认计划兜底，确保工作流不中断

    设计考虑：
    - 使用 try-except 捕获 LLM 调用失败，避免单点故障导致整个流程崩溃
    - 验证输出结构，确保包含必需的字段（function_name, logic_analysis）
    - 默认计划包含空逻辑分析，下游 Generator 仍可基于目标代码生成测试

    Args:
        state: 当前状态，包含 target_code（被测代码）和 target_function（可选的目标函数名）。

    Returns:
        更新后的状态字典，包含 test_plan 字段（PlannerAgent 输出的测试计划）。
    """
    agent = get_or_create_agent(PlannerAgent)
    t0 = time.time()
    _planner_budget_hit = False  # 5.4 预算封顶标记（O35；正常 / 验证降级路径恒 False）
    try:
        # 调用 Planner 生成测试计划，传入被测代码和可选的目标函数名
        # 若指定了 target_function，Planner 将只分析该函数，缩小分析范围
        test_plan = agent.plan(state["target_code"], state.get("target_function"))
        # 验证输出结构
        if not _validate_planner_output(test_plan):
            # I2（2026-10-16，ADR-0032）：整份替换计划前先摘出 planner 已写下的
            # M10 归因标记。extract_json_object 的叶子降级档返回**最内层片段**
            # （如 {"k": 42}），片段通常连 function_name 都没有 → 本分支正是该
            # 场景的必经之路；若标记随旧 test_plan 一起被丢弃，顶层抬升只能读到
            # False，"提取器误诊"被记成"LLM 真未输出"——ADR-0032 的可分离性
            # 恰好在它最该生效的场景下**反向错判**（实测日志链：helpers.py:735
            # 叶子回退 → planner.py:380 写标记 → 本行默认计划替换 → 标记消失）。
            _m10_leaf_fallback = bool(isinstance(test_plan, dict) and test_plan.get("m10_leaf_fallback"))
            logger.warning("Planner 输出结构不完整，使用默认计划")
            test_plan = _get_default_test_plan(state.get("target_function"))
            # M10（2026-09-29 审查 P0）：验证失败走默认计划 → 逻辑驱动路径
            # 实际未发生，标记 logic_degraded=True（纯观测，供实验层区分
            # "逻辑驱动成功"与"降级到默认计划"）。
            test_plan["logic_degraded"] = True
            if _m10_leaf_fallback:
                test_plan["m10_leaf_fallback"] = True
        # P0 测试预言增强（ORACLE_ENHANCE_ENABLE=true 时启用，默认关）：
        # 在 Planner 产出 logic_analysis（规约）后，由独立 LLM 调用对每个
        # test_case 做规约驱动预言推理，追加 oracle / oracle_source /
        # oracle_confidence 字段；下游 Generator 经 _build_query 的
        # json.dumps(test_plan) 自然消费强化断言预言。
        # 保守降级：LLM 失败时保留原 test_cases（oracle_enhanced=False），不阻断生成。
        # 默认关闭时零行为变化（历史口径不变）。
        if _oracle_enhance_enabled():
            from src.agents.oracle_enhancer import OracleEnhancerAgent

            enhancer = OracleEnhancerAgent()
            test_plan = enhancer.enhance(test_plan)
            _oracle_enhanced = bool(test_plan.get("oracle_enhanced"))
            logger.info(
                "P0 测试预言增强：%s（函数=%s，oracle 注入 %d 条）",
                "成功" if _oracle_enhanced else "降级保留原 test_cases",
                test_plan.get("function_name", "unknown"),
                sum(1 for c in test_plan.get("test_cases", []) if c.get("oracle")),
            )
        logger.info("Planner 完成规划，函数=%s", test_plan.get("function_name", "unknown"))
    except (json.JSONDecodeError, RuntimeError, OSError) as e:
        # LLM 调用失败或返回非 JSON 格式时，使用默认计划兜底
        # 这确保了即使 LLM 服务异常，工作流仍可以继续执行（降级模式）
        # 2026-09-26 全面审查：扩捕获 OSError——agent.plan 内部 LLM 文件缓存
        # 读写（_call_llm_with_cache）在缓存目录被外部删除/磁盘满等场景抛
        # OSError，此前未捕获会让整图崩溃（与 debugger 节点同口径兜底）。
        # 复用 _get_default_test_plan（与上方验证失败分支同一构造点）：
        # 其 "or 'unknown'" 兜底比原内联 .get(key, "unknown") 更严格
        # （空串/None 键值也会归一为 "unknown"，语义向成功分支收敛）
        # 5.4 预算封顶：BudgetExceededError（isinstance 判定）同走默认计划兜底，
        # 任务不会因预算异常崩溃（后续迭代前置守卫快速失败，自然收敛）
        _planner_budget_hit = isinstance(e, BudgetExceededError)
        logger.warning(
            "Planner LLM 失败（%s），使用默认计划: %s", "5.4 预算封顶" if _planner_budget_hit else "JSON 解析失败", e
        )
        test_plan = _get_default_test_plan(state.get("target_function"))
        # M10（2026-09-29 审查 P0）：LLM 失败走默认计划 → 逻辑驱动路径
        # 实际未发生，标记 logic_degraded=True（纯观测，供实验层区分
        # "逻辑驱动成功"与"降级到默认计划"）。
        test_plan["logic_degraded"] = True
    _trace_node(
        "planner",
        output_summary={
            "function_name": test_plan.get("function_name"),
            "test_cases": len(test_plan.get("test_cases", [])),
        },
        decision="plan_complete",
        duration_ms=(time.time() - t0) * 1000,
    )
    # 1.4 事件总线接线：PlanGenerated（纯观测，不改路由）
    publish_event(
        PlanGenerated(
            task_uuid=str(state.get("task_uuid", "")),
            function_name=str(test_plan.get("function_name") or ""),
            test_case_count=len(test_plan.get("test_cases", [])),
            iteration=int(state.get("iteration", 0)),
        )
    )
    # 观测层：把"预言增强是否触发"写回 state（供实验分析消费，默认关时不写）
    update: dict[str, Any] = {"test_plan": test_plan}
    # G3（2026-10-16）：把 logic_degraded 抬到顶层通道。三个写侧（本节点两处
    # 降级分支 + planner.plan 的 M10 兜底/schema findings）历史上只写进 test_plan
    # 内部，而唯一读侧 failure_taxonomy.annotate_final_state 读顶层键 → 恒 None，
    # "规约降级弱信号"归因分支从未 fire（既有单测手工构造顶层键，掩盖了断链）。
    # 无条件抬升：False 同样有意义（证明逻辑驱动路径确实走通）。纯观测，不参与路由。
    update["logic_degraded"] = bool(test_plan.get("logic_degraded"))
    # I2（2026-10-16，ADR-0032）：同一缺陷形态的第二处——planner.plan 的 M10
    # 兜底分支把 m10_leaf_fallback 只写进 test_plan 内部，实验层从投影行读不到，
    # ADR-0032 声称的"logic_degraded=True ∧ m10_leaf_fallback=True ⇒ 提取器误诊
    # （非 LLM 未输出）"因此不可机读。无条件抬升（False 同样有意义：证明该次
    # M10 降级确为 LLM 真未输出）。纯观测，不参与路由。
    update["m10_leaf_fallback"] = bool(test_plan.get("m10_leaf_fallback"))
    if _oracle_enhance_enabled():
        update["oracle_enhanced"] = bool(test_plan.get("oracle_enhanced"))
    # R7（2026-09-30 独立审查 P0）：SpecIR——把 logic_analysis（自然语言规约）
    # + 确定性边界三元组解析为可执行 SpecIR IR，校验 findings 写回 state
    # （SPEC_IR_ENABLE=true 时非空，默认关时 None，历史口径零变化）。
    # 保守：解析/校验失败 → spec_ir=None（不阻断 Planner 主流程）。
    if _spec_ir_enabled():
        from src.specs import parse_logic_analysis, validate_spec_ir
        from src.tools.logic_spec import derive_boundary_triplets

        _spec_ir = parse_logic_analysis(
            test_plan.get("logic_analysis"),
            boundary_triplets=derive_boundary_triplets(state["target_code"], state.get("target_function")),
        )
        if _spec_ir is not None:
            _spec_ir["findings"] = validate_spec_ir(_spec_ir)
        update["spec_ir"] = _spec_ir
    # A-01（2026-10-04 系统审查 P0）：SpecIR v2 DSL 层——"逻辑驱动"主张的
    # 可测量内核：SPEC_IR_DSL_ENABLE=true（默认关，与 R7 主开关独立）时，
    # 对 SpecIR 的 pre/post/invariant 子句做"可编译率"判定（受限表达式
    # DSL + 白名单，纯静态零 LLM）写入 state["spec_compile_rate"]（float
    # 0.0~1.0，无规约材料时 0.0——可证伪口径："逻辑驱动"贡献 = 可编译率，
    # 而非 100% 宣称）。纯观测字段，不参与路由（与 spec_ir 同档位）。
    if _spec_ir_dsl_enabled():
        from src.specs import (
            compile_readiness,
            spec_expr_coverage,
            spec_provenance,
            spec_reject_reasons,
        )

        _dsl_spec = update.get("spec_ir")
        if _dsl_spec is None:
            # DSL 层独立于 R7 主开关：R7 关但 DSL 开时，直接解析
            # logic_analysis（保守降级：无材料 → 0.0）
            from src.specs import parse_logic_analysis

            _dsl_spec = parse_logic_analysis(test_plan.get("logic_analysis"))
        # P0-3（2026-10-10）：绑定上下文与注入通道**同口径**——注入侧
        # （_append_spec_oracle_to_test）用 extract_signature_params(
        # target_code, 函数名) 构造 signature_params；度量侧若缺席（历史默认
        # 集合 {r,x,a,b,y}）会把"自定义参数名可编译"的子句误判为不可编译，
        # 度量又变成下界。函数名解析口径与注入侧逐字一致：
        # target_function → spec.function_name（注入侧同为这两级）。
        # 2026-10-14 第三级回退（度量侧专用，EMSE SpecExpr 确认性实验诊断）：
        # Planner 降级时前两级皆空**或为字面量 "unknown"**（M10 降级的两种
        # 形态：JSON 解析失败缺字段 / 占位 "unknown"——实测 12 任务样本
        # 2/12 为 "unknown"）→ 签名提取回退历史默认集 {r,x,a,b,y} →
        # 自定义参数名的可编译子句被误判 unknown_name（合成集实测 270 次
        # 拒绝的主要来源）。回退取模块唯一顶层函数名（确定性 AST，仅单
        # 函数模块 fire，多函数模块保守空串）。刻意不动注入侧（改 injection
        # 会动处理/prompt，属另一实验）。
        from src.specs import extract_signature_params as _extract_sig_params
        from src.tools.spec_first import sole_top_level_function_name as _sole_fn_name

        _dsl_func_raw = state.get("target_function") or (_dsl_spec or {}).get("function_name") or ""
        _dsl_func = (
            _dsl_func_raw
            if _dsl_func_raw and _dsl_func_raw != "unknown"
            else _sole_fn_name(state.get("target_code") or "")
        )
        _dsl_signature_params = (
            _extract_sig_params(state.get("target_code") or "", str(_dsl_func)) if _dsl_func else None
        )
        update["spec_compile_rate"] = compile_readiness(_dsl_spec, _dsl_signature_params)
        # AC1（2026-10-06 第十轮审查 T-P0-2）：表达式通道覆盖率并列透出
        # （compile_rate=编译器接受率，coverage=LLM 形式化覆盖率，正交观测）
        update["spec_expr_coverage"] = spec_expr_coverage(_dsl_spec)
        # T1（2026-10-11 独立评审落地）：规约被拒原因分布——把"可编译率恒 0"
        # 拆成 {natural_language / unsupported_operator / unknown_name / ...}
        # 计数（纯观测、零 LLM，与 compile_readiness 同一判定门，可与之对账）。
        # 动机：全量 1,607 行实测中位数仅 0.200、47.6% 恒为 0，但"为何为 0"
        # 不可归因；真实调用已定位根因是 planner 产出自然语言规约。本字段使
        # "修提示 vs 扩文法"的取舍有据可依。空 dict 不写入（保持键集合同构）。
        _reject = spec_reject_reasons(_dsl_spec, _dsl_signature_params)
        if _reject:
            update["spec_reject_reasons"] = _reject
        _prov = spec_provenance(_dsl_spec)
        if _prov:
            update["spec_provenance"] = _prov
    # 5.4 预算封顶标记（O35）：置真后不回退，供 determine_stop_reason 的
    # BUDGET_EXCEEDED 分支与实验分析消费（此前该分支无任何写入点，恒不可达）。
    if _planner_budget_hit:
        update["budget_exceeded"] = True
    return update


def _detection_first_regenerate_entry(state: AITesterState) -> bool:
    """W3（2026-10-05 审查落地·检出优先协议）：判定本节点是否由"检出优先
    再生成"路由进入（_should_debug 的 detection_first_all_green 分支）。

    特征（与首生成 / 其他三类再生成路径可区分）：
    - DETECTION_FIRST_ENABLE=true；
    - test_passed 为 True（首生成恒 None；其余再生成路径均因测试失败触发）；
    - iteration==0（未发生修复；detection_first 的再生成只发生在首轮）。

    供两处消费：
    1. 再生成计数（regeneration_count +1，防 executor↔generator 乒乓，
       与其余三类再生成路径同口径）；
    2. 构造"先红后绿"强化提示段落（见 _detection_first_section）。
    """
    return detection_first_enabled() and state.get("test_passed") is True and int(state.get("iteration", 0)) == 0


def _specificity_over_red_regenerate_entry(state: AITesterState) -> bool:
    """AC2 特异性门过红再生成入口检测（修复引擎批次 III 补漏，2026-10-07）。

    根因（E2 实证 16/174 任务撞 recursion_limit 的通道之一）：
    _should_debug 的 over_red 分支以 test_passed=**False** 进入 generator
    （测试红、但红得不特异），而 _detection_first_regenerate_entry 只认
    test_passed is True → 五类再生成入口检测无一命中 → regeneration_count
    恒不递增 → over_red 分支的 regeneration_count < MAX_REGENERATIONS
    上限永不绑定 → executor↔generator 无限乒乓直至 recursion_limit
    （O4/W3 同类漏计根因的第三个实例）。

    判定特征：iteration==0（over_red 分支只在首轮触发）且
    specificity_gate_verdict=="over_red"（该值只在特异性门对照执行时
    写入——门关时恒 None，无需重复判门开关）。
    """
    return int(state.get("iteration", 0)) == 0 and state.get("specificity_gate_verdict") == "over_red"


def _detection_first_section(state: AITesterState) -> str | None:
    """W3：检出优先再生成路径的 prompt 强化段落（非该路径时 None 不注入）。

    RT1 消融（2026-10-09 审查报告 §8.6 红队 RT1，`DETECTION_FIRST_SECTION_ENABLE`）：
    该开关默认 **true**（历史口径零变化）。置 false 时**保留再生成路由**
    （`_should_debug` 的 `detection_first_all_green` 分支与 `regeneration_count`
    计数照旧）但**不注入本强化段落**——用于分离"协议提示词效应"与
    "多一次采样的效应"：
    - `plain_llm_df` 臂有再生成 + 有强化段（现口径）；
    - RT1 臂有再生成 + **无**强化段；
    - 二者检出差即**协议文本的净效应**，其余样本量/调用次数对齐。
    动机：df 臂在首轮全绿时**必然**再生成一次，而 `plain_llm` 只生成一次——
    "+43pp 协议效应"与"多一次采样的效应"在既有对照中未解耦（RT1）。
    """
    if not _detection_first_section_enabled():
        return None
    if not _detection_first_regenerate_entry(state):
        return None
    return (
        "【检出优先·先红后绿】上一版测试在当前（未修复的）代码上全部通过——"
        "这说明测试没有检出任何缺陷，属于无效的全绿测试。请重新生成更强的测试："
        "针对代码中最可能隐藏缺陷的边界条件、异常路径与特殊输入构造断言，"
        "使测试在当前含缺陷的代码上**至少一个用例失败（变红）**。"
        "禁止放松、删减或条件化断言来换取通过；禁止重新实现被测函数；"
        "断言的期望值必须来自问题语义（数学定律/规约），不得抄袭实现当前行为。"
    )


def _over_red_section_enabled() -> bool:
    """过红再生成强化段落的消融开关（``OVER_RED_SECTION_ENABLE``，默认 **false**）。

    默认关 = 历史口径零变化（ADR-0003：新功能默认关）；置 "true"/"1" 时
    `_over_red_section` 才可能注入段落。置 false 时**再生成路由与计数不受影响**
    （与 `DETECTION_FIRST_SECTION_ENABLE` 同一口径：开关只控制提示词，不控制路由）。
    """
    return env_flag("OVER_RED_SECTION_ENABLE")


def _empty_plan_shortcut_enabled() -> bool:
    """空计划短路的消融开关（``EMPTY_PLAN_SHORTCUT_ENABLE``，默认 **false**）。

    背景（独立审查 2026-10-10 落地，报告建议 13 置信度短路）：
        Planner 产出空计划（``test_cases=[]``）时，Generator 无法据此生成
        有效测试——D1 根因（JSON 解析失败兜底 `_get_default_test_plan`）
        实测空计划率 39.1%（冷缓存 seed42 n=87）。空计划调用 Generator 只会
        产出无用/空测试，白白消耗一次 LLM 调用（成本优化：报告 P0 建议 11
        的"空计划短路"与建议 13 的"置信度短路"）。

    默认关 = 历史口径零变化（ADR-0003）；置 "true"/"1" 时 `_generator_node`
    在空计划下跳过 ``agent.generate`` 直接产出空测试并标记
    ``empty_plan_shortcut=True``（纯观测，不改变路由 / 主终点口径）。
    """
    return env_flag("EMPTY_PLAN_SHORTCUT_ENABLE")


def _path_enum_inject_enabled() -> bool:
    """路径枚举注入的消融开关（``PATH_ENUM_INJECT_ENABLE``，默认 **false**）。

    背景（独立审查 2026-10-10 落地，报告建议 4 结构接地的静态基础）：
        SPARC（arXiv:2602.16671）"路径定向测试合成"——把函数的独立执行路径
        （if/elif/else 分支组合）枚举后注入 prompt，引导 LLM 按路径逐一生成
        测试（而非一次性自由发挥）。与既有 CFG 摘要（build_cfg_prompt_section，
        注入 Planner）形成递进：CFG 摘要给"分支/循环/异常"的粗粒度提示，
        路径枚举给"每条路径需满足的条件组合"的细粒度提示。

    默认关 = 历史口径零变化（ADR-0003）；置 "true"/"1" 时 `_generator_node`
    在 generate 调用前构建路径段落并注入（纯静态零 LLM 成本，不改变调用次数）。
    """
    return env_flag("PATH_ENUM_INJECT_ENABLE")


def _operation_map_inject_enabled() -> bool:
    """操作图注入的消融开关（``OPERATION_MAP_INJECT_ENABLE``，默认 **false**）。

    背景（独立审查 2026-10-10 落地，报告建议 4 结构接地的第 2 阶段静态基础）：
        SPARC（arXiv:2602.16671）第 2 阶段"Operation Map"——把 LLM 测试合成
        **接地在已验证的 utility helper 上**（函数签名 / 类 / 常量 / 导入），
        避免 leap-to-code 失败（LLM 凭空调用不存在的 helper / 编造 API / 错写
        参数签名）。与路径枚举（PATH_ENUM_INJECT_ENABLE）共同构成结构接地
        的静态两件套：路径枚举告诉 LLM"走哪些路径"，操作图告诉 LLM
        "能调用哪些符号"。

    默认关 = 历史口径零变化（ADR-0003）；置 "true"/"1" 时 `_generator_node`
    在 generate 调用前构建操作图段落并注入（纯静态零 LLM 成本，不改变调用次数）。
    """
    return env_flag("OPERATION_MAP_INJECT_ENABLE")


def _over_red_section(state: AITesterState) -> str | None:
    """过红（over_red）再生成路径的 prompt 强化段落（非该路径时 None 不注入）。

    背景（2026-10-10 审查报告 §11.1b 结果二十四/二十五，实测证据）
    ---------------------------------------------------------------
    QuixBugs 41 缺陷程序口径下的**轮次级**观测：

    | 首轮 verdict | aitester 占比 | 两臂 detection |
    |---|---|---|
    | ``specific_red``（首轮特异红） | 19/50（38%） | **100%** |
    | ``over_red``（盲/过红，需再生成） | **30/50（60%）** | **0%** |

    即 **`over_red` 覆盖 aitester 六成任务，而其中检出率为 0**。
    代码级根因：`_detection_first_section` 要求
    ``_detection_first_regenerate_entry``（``test_passed is True``），
    而 ``over_red`` 是 ``test_passed=False`` 进入的（测试红了，但红得不特异——
    或**因缺陷代码不终止而挂起**）→ **拿不到任何强化提示** →
    再生成只是"用同一份计划再问一次" → 注定同样 over_red，**不可恢复**。

    与 ``plain_llm_df`` 的对照印证：df 无 Planner 故无缺陷锚定的计划，
    首轮特异红 34/50（68%）、over_red 仅 15/50（30%）。

    本段落针对性给出"过红"专有的三条指令：
    1. **不终止即失败**：若上一版测试在缺陷代码上**挂起/超时**，说明它无法
       给出判定——须改用**输入规模受控**的用例，使函数要么返回、要么快速失败
       （实测样例：`bitcount` 的缺陷实现 `n ^= n - 1` 对任何 n 都不终止，
       `assert bitcount(127) == 7` 只会永久挂起）；
    2. **期望值来自契约而非实现**：期望值须由 docstring / 类型注解 /
       数学性质推出，**不得**照抄被测实现当前行为（那是缺陷行为）；
    3. **保持特异性**：不得为求通过而放松/删减/条件化断言。

    Args:
        state: 工作流状态。

    Returns:
        强化段落文本，或 None（开关关 / 非 over_red 路径）。
    """
    if not _over_red_section_enabled():
        return None
    if not _specificity_over_red_regenerate_entry(state):
        return None
    return (
        "【过红修复·重写为特异测试】上一版测试在**未修复**的代码上变红了，"
        "但这个红**不可判定**或**不特异**——常见两种形态："
        "① 测试**挂起/超时**（被测函数在当前缺陷实现下不终止），"
        "此时它既不能算检出也不能算通过；"
        "② 测试红了，但红了**非缺陷相关**的位置（如收集错误、与被测函数无关的断言）。"
        "请重新生成测试，务必满足："
        "**（a）输入规模受控**——所有用例都必须在有限时间内返回或快速抛错，"
        "禁止使用会让当前实现陷入长循环的大输入（若要触发已知的非终止缺陷，"
        "请用 `pytest.raises` / `pytest.mark.timeout` 或在断言前限制迭代规模的等价手段，"
        "使测试**快速失败**而不是挂起）；"
        "**（b）期望值必须来自契约**——由 docstring、类型注解与数学性质推出，"
        "严禁照抄被测实现当前的返回值（当前实现含缺陷，照抄即等于把缺陷写成期望）；"
        "**（c）保持特异性**——故障必须出在**被测函数的行为断言**上，"
        "且该断言在正确实现下应当通过；"
        "禁止放松、删减或条件化断言来换取通过。"
    )


def _detection_first_section_enabled() -> bool:
    """RT1 消融开关（`DETECTION_FIRST_SECTION_ENABLE`，默认 true = 历史口径）。

    置 "false"/"0" 时 `_detection_first_section` 返回 None（不注入强化段落），
    但 `_detection_first_regenerate_entry` 与再生成路由**不受影响**。
    """
    return env_flag_opt_out("DETECTION_FIRST_SECTION_ENABLE")


def _derive_detection_first_status(passed: bool, red_seen: bool | None) -> str | None:
    """Y1（2026-10-05 X 批次真实冒烟发现）：检出优先终态标注的三值推导（纯函数）。

    背景：W3 原实现仅在 test_passed=True 时写 detection_first_status——
    "首轮全绿 → 再生成 → 第二版变红 → 终止"轨迹（plain_llm_df 冒烟实测，
    trace: PASS→regenerate→FAIL→done）下，exec1 写入的 all_green_unverified
    残留为终值，与 detection_first_red_seen=True 并列出现语义矛盾
    （"从未红"标注 vs "曾检出"信号）。终态标注应覆盖失败终局：

    - passed ∧ red_seen  → red_then_green（先检出再修复——W3 原口径）
    - passed ∧ 无 red    → all_green_unverified（弱测试假成功——W3 原口径）
    - ¬passed ∧ red_seen → red_not_repaired（检出成功但未修复：plain_llm_df
      无修复循环的正常终态 / aitester 修复失败的终态；**这是有效检出**，
      评估层 detection 口径应计数，不得因 passed=False 丢弃）
    - ¬passed ∧ 无 red   → None（不写：无检出无修复的失败无可标注语义，
      保留上一轮写入值）

    每轮执行后写，LangGraph 后写覆盖 → 最终值即终态（与 W3 注释口径一致）。
    """
    if passed:
        return "red_then_green" if red_seen else "all_green_unverified"
    if red_seen:
        return "red_not_repaired"
    return None


def _apply_test_suite_dedup(generated_test: str) -> tuple[str, int]:
    """N5 测试套件断言去重（TEST_SUITE_DEDUP_ENABLE=true 时启用，默认关）。

    A14（2026-10-18 第三方评审 P1）：`experiments.test_suite_minimize` 属仓库
    实验树（wheel 只收 src*），旧实现在开关开启时裸 import——干净基础 wheel
    下 ImportError 直接打断 generator 节点。现导入失败保守降级：保留原文、
    移除数记 0（与开关关闭路径一致），不阻断主生成流程。

    Args:
        generated_test: LLM 生成的测试代码。

    Returns:
        (去重后的测试代码, 移除的重复断言条数)；开关关 / 依赖不可用时原样返回。
    """
    if not env_flag("TEST_SUITE_DEDUP_ENABLE"):
        return generated_test, 0
    try:
        from experiments.test_suite_minimize import dedup_assertions as _dedup_assertions
    except Exception as exc:  # 发行缺包（wheel 不含 experiments）→ 保守降级
        logger.warning("N5 测试套件去重层不可用（experiments 包缺失/导入失败），保守跳过: %s", exc)
        return generated_test, 0
    deduped_code, dedup_removed = _dedup_assertions(generated_test)
    return deduped_code, len(dedup_removed)


def _retrieve_generator_rag_refs(state: AITesterState) -> tuple[list | None, dict[str, Any] | None]:
    """Generator 节点的 RAG 检索段（自 `_generator_node` 提取，行为等价）。

    仅当 ``ENABLE_RAG`` 开启且 RAG 模块可用时经 ``rag_guarded`` 降级守卫
    检索 Top-3 相似历史测试用例；检索失败静默跳过，不影响主生成流程。

    Args:
        state: 当前状态（读取 ``target_code``）。

    Returns:
        ``(rag_refs, update_rag_stat)`` 二元组：前者为参考用例列表或 None，
        后者为本轮检索质量统计（供 ``state["rag_stats"]`` 累计）。
    """
    # 初始化 RAG 参考列表为 None（默认不使用检索增强）
    # 仅当 RAG 开关开启、模块可用时才进行检索（统一走 rag_guarded 降级守卫，P1 重构）
    # 闭包写回需要外层可变容器（list 包装：Python 闭包内无法 rebinding 外层局部名）
    rag_refs_box: list = [None]

    def _on_retrieve(retriever) -> None:
        # top_k=3 是经验值：太多会增加 prompt 长度，太少可能缺乏代表性
        refs = retriever.retrieve_test_cases(state["target_code"], top_k=3)
        # P2 RAG 相关性评分 + 条件注入（2026-10 改进，A/B 阴性结果驱动）：
        # 生成侧同样做相关性过滤（默认关，历史口径零变化）——低相关案例
        # 反增 token 噪声（ContextSniper 式"先筛选再注入"）
        if refs:
            from src.graph.rag import filter_by_relevance

            refs, _filtered_n, _filter_rate = filter_by_relevance(refs)
        logger.info("RAG 检索到 %d 个相似测试用例", len(refs) if refs else 0)
        rag_refs_box[0] = refs

    rag_guarded(
        "retrieve_test_cases",
        _on_retrieve,
        enabled=ENABLE_RAG,
        module_available=RAG_MODULE_AVAILABLE,
        retriever_cls=TestCaseRetriever,
        get_retriever=get_rag_retriever,
    )
    rag_refs: list | None = rag_refs_box[0]

    # P1：记录本次 RAG 检索的质量指标（命中数/相似度），随状态累计供实验汇总
    update_rag_stat = _build_rag_stat(rag_refs, kind="test_cases")
    return rag_refs, update_rag_stat


def _build_generator_static_sections(state: AITesterState, ctx_minimal: bool) -> dict[str, Any]:
    """构建 Generator 的静态分析增强段落（自 prompt 段构建器拆出，行为等价）。

    覆盖分支覆盖率 / 反馈压缩 / AST 边界锚点 / 路径枚举 / 操作图五节；
    ``ctx_minimal`` 为 True（oracle 上下文消融档）时全部保持 None 不注入。
    全部为零 LLM 静态分析或既有观测渲染，不调用 LLM、不写 state。

    Args:
        state: 当前状态（读取 target_code / branch_coverage 等）。
        ctx_minimal: 是否处于 oracle 上下文消融档（minimal）。

    Returns:
        六个段落键的字典（未启用时为 None）。
    """
    # O3（2026-09-29 审查 P1）：分支覆盖率注入——_executor_node 上一轮测量
    # 的未覆盖分支清单渲染为 prompt 段落（BRANCH_COVERAGE_INJECT_ENABLE=true
    # 时非空，默认关时 None，历史口径零变化）
    _bc_section: str | None = None
    if not ctx_minimal and _branch_coverage_inject_enabled() and state.get("branch_coverage"):
        from src.tools.branch_coverage_inject import build_branch_coverage_prompt_section as _build_bc_section

        _bc_section = _build_bc_section(state.get("branch_coverage"))
    # P2 一期（观测级行粒度压缩）：Debugger→Generator 反馈的压缩段落。
    # 从 state 既有观测（probe 快照最内层帧 / fl_spectral Top-k /
    # traceback 行号 / mutation_feedback）提取「失败测试涉及的源代码行
    # + 错误类型 + 存活变异体摘要」，渲染为有界段落（≤4000 字符）注入
    # Generator prompt——替代朴素全量 trace 注入。零 LLM 成本（纯文本
    # 提取）；无实质内容时 compressed_feedback=None，历史口径零变化；
    # 与 oracle_context_minimal 消融档联动（minimal 时不注入，与 O3
    # 同口径）。构建点选消费侧（本节点）而非 _debugger_node：_should_debug
    # 的 over_red 再生成路由不过 debugger，消费侧构建覆盖全部再生成路径。
    _compressed_feedback: dict[str, Any] | None = None
    _fc_section: str | None = None
    if not ctx_minimal and _feedback_compression_enabled():
        from src.tools.feedback_compression import build_compressed_feedback as _build_fc
        from src.tools.feedback_compression import build_feedback_compression_section as _build_fc_section

        _compressed_feedback = _build_fc(state)
        _fc_section = _build_fc_section(_compressed_feedback)
        if _fc_section:
            logger.info(
                "P2 观测级压缩反馈：错误类型=%s 涉及行=%d 存活变异=%d（%d 字符）",
                (_compressed_feedback or {}).get("error_category"),
                len((_compressed_feedback or {}).get("target_lines") or []),
                len((_compressed_feedback or {}).get("survived_mutants") or []),
                len(_fc_section),
            )
    # M10（2026-09-29 审查 P0）：确定性边界锚点——从 target_code 的 AST
    # 分支条件推导边界三元组（零 LLM 成本），渲染为 prompt 段落注入
    # Generator（BOUNDARY_TRIPLETS_ENABLE=true 时非空，默认关时 None，
    # 历史口径零变化）。与 O3 分支覆盖率注入同位（在 generate 调用前
    # 构建，传入 generate 的新参数 boundary_triplets_section）。
    _bt_section: str | None = None
    if not ctx_minimal and _boundary_triplets_enabled():
        from src.tools.logic_spec import build_boundary_triplets_section as _build_bt_section
        from src.tools.logic_spec import derive_boundary_triplets as _derive_bt

        _bt_triplets = _derive_bt(state["target_code"], state.get("target_function"))
        if _bt_triplets:
            _bt_section = _build_bt_section(_bt_triplets)
    # 2026-10-10 独立审查落地（报告建议 4 结构接地·路径定向合成）：独立执行
    # 路径枚举段落——control_flow.enumerate_paths（零 LLM 静态分析）枚举
    # if/elif/else 分支组合 + 循环三边界，渲染为"路径定向"提示注入 Generator。
    # PATH_ENUM_INJECT_ENABLE=true 时非空；默认关时 None，历史口径零变化。
    _paths_section: str | None = None
    if not ctx_minimal and _path_enum_inject_enabled():
        from src.tools.control_flow import build_paths_prompt_section as _build_paths_section
        from src.tools.control_flow import enumerate_paths as _enumerate_paths

        _paths_result = _enumerate_paths(state["target_code"], state.get("target_function"))
        _paths_section = _build_paths_section(_paths_result)
    # 2026-10-10 独立审查落地（报告建议 4 结构接地·操作图）：已验证 utility
    # helper 清单段落——operation_map.build_operation_map（零 LLM 静态分析）
    # 收集函数签名/类/常量/导入，渲染为"已验证符号清单"注入 Generator，
    # 避免 leap-to-code（编造不存在的 API / 错写参数签名）。
    # OPERATION_MAP_INJECT_ENABLE=true 时非空；默认关时 None，历史口径零变化。
    _opmap_section: str | None = None
    if not ctx_minimal and _operation_map_inject_enabled():
        from src.tools.operation_map import build_operation_map as _build_opmap
        from src.tools.operation_map import build_operation_map_section as _build_opmap_section

        _opmap_section = _build_opmap_section(_build_opmap(state["target_code"]))
    return {
        "branch_coverage_section": _bc_section,
        "feedback_compression_section": _fc_section,
        "compressed_feedback": _compressed_feedback,
        "boundary_triplets_section": _bt_section,
        "paths_section": _paths_section,
        "operation_map_section": _opmap_section,
    }


def _build_generator_oracle_sections(
    state: AITesterState, test_plan: dict[str, Any], ctx_minimal: bool
) -> dict[str, Any]:
    """构建 Generator 的无 oracle / 规格 / 注入防护段落（行为等价拆出）。

    覆盖 N2 蜕变关系 / N4 差分测试 / 输入侧注入扫描 / 规格优先（replace）
    / 规格增广（augment）/ 空计划短路六节；``ctx_minimal`` 为 True 时增强
    段与规格段均不注入（空计划短路开关独立生效）。全程不调用 LLM。

    Args:
        state: 当前状态（读取外部可控文本 / 规格锚等）。
        test_plan: Planner 计划（可为空 dict）。
        ctx_minimal: 是否处于 oracle 上下文消融档（minimal）。

    Returns:
        九个段落与观测标记键的字典。
    """
    # P2-7（N2/N4 接线审计，2026-10）：无 oracle 场景增强段落。
    # N2 蜕变关系：从函数名/签名/文档启发式匹配 MR 模板（零 LLM 成本），
    # 命中时渲染 prompt 段落注入（METAMORPHIC_ENABLE=true 时非空，默认关
    # 时 None，历史口径零变化）。
    # N4 差分测试：引导 LLM 生成"参考实现 vs 被测实现"随机输入比对指令
    # （DIFFERENTIAL_TEST_ENABLE=true 时非空，默认关时 None）。
    # 两节均为纯观测层 prompt 增强，不改变路由 / 开关默认行为。
    _fn_name = state.get("target_function") or ""
    _mr_section: str | None = None
    _diff_section: str | None = None
    try:
        from experiments.metamorphic_oracle import (
            build_metamorphic_prompt_section as _build_mr_section,
        )
        from experiments.metamorphic_oracle import (
            metamorphic_enabled as _mr_enabled,
        )
        from experiments.metamorphic_oracle import (
            suggest_metamorphic_relations as _suggest_mrs,
        )

        if not ctx_minimal and _mr_enabled() and _fn_name:
            _mrs = _suggest_mrs(_fn_name)
            if _mrs:
                _mr_section = _build_mr_section(_mrs)
        from experiments.differential_test import (
            build_differential_prompt_section as _build_diff_section,
        )
        from experiments.differential_test import (
            differential_enabled as _diff_enabled,
        )

        if not ctx_minimal and _diff_enabled() and _fn_name:
            _diff_section = _build_diff_section(_fn_name)
    except Exception as _oracle_hook_exc:  # 观测层钩子失败不得阻断主生成
        logger.warning("N2/N4 无 oracle 增强段落构建失败，降级跳过: %s", _oracle_hook_exc)
    # P2（2026-10 批次·续二）：注入扫描回归基准接线——此前
    # detect_prompt_injection 输入侧全仓无调用方（孤儿函数，威胁模型 P2
    # 缺口"注入扫描无回归基准"）。本段在 Generator 消费外部可控文本
    # （problem_statement / 缺陷描述 / 任务描述）前做输入侧注入特征扫描
    # （INJECTION_GUARD_ENABLE 默认关时恒 []，历史口径零变化）；命中时
    # 把 findings 写入 state["injection_findings"]（供 agent_telemetry
    # 的 injection_detected 模式消费 + trace 记录）并经
    # build_injection_warning 追加系统侧警示到本次 LLM query（OWASP ASI
    # "检测+隔离"口径：只警示不自动阻断，阻断决策留给调用方）。
    # 外部可控文本来源（按优先级）：
    #   1. state["problem_statement"]（SWE-bench 任务描述 / issue 文本）
    #   2. state["diagnosis"] / state["review_reason"]（上一轮诊断描述）
    #   3. state["task_description"]（CLI 自定义任务描述，若存在）
    _injection_task_text = (
        state.get("problem_statement")
        or state.get("diagnosis")
        or state.get("review_reason")
        or state.get("task_description")
        or ""
    )
    _injection_findings: list[str] = []
    _injection_warning: str | None = None
    if _injection_task_text:
        from src.agents.injection_guard import (
            build_injection_warning,
            detect_prompt_injection,
        )
        from src.agents.injection_guard import (
            injection_guard_enabled as _injection_guard_enabled,
        )

        _injection_text = str(_injection_task_text)
        if _injection_guard_enabled():
            _injection_findings = detect_prompt_injection(_injection_text)
            if _injection_findings:
                _injection_warning = build_injection_warning(_injection_findings)
                logger.warning(
                    "P2 注入扫描：外部文本检出注入特征 %s（追加系统侧警示，不自动阻断）", _injection_findings
                )
    # P0-A-2（2026-10-12 独立评审落地）：规格优先生成（Spec-First）——
    # DETECTION_SPEC_MODE=replace 时，把 Generator prompt 的"目标代码"块
    # 替换为规约文档（签名 + NL 规约 + SpecExpr 子句 + 生成纪律），从源头
    # 切断 oracle-from-implementation 锚点（misguidance effect：缺陷代码
    # 入提示诱发"断言错误行为"的测试；项目 48.6% 全绿未检出同根因）。
    # 默认 off / minimal 消融档 / 无规约材料 → None，prompt 与历史逐字节
    # 一致（spec_first.build_spec_replace_section 保守返回空串）。
    # A-10（2026-10-16）：锚材料选择——df_spec 臂预载 state["spec_anchor"]
    # （预计算 Planner 计划子集 {function_name, logic_analysis}）时优先；
    # 缺席/非法类型回落 test_plan（历史口径：其它臂从不写 spec_anchor，
    # 行为逐字节不变）。
    _spec_material: Any = state.get("spec_anchor")
    if not isinstance(_spec_material, dict):
        _spec_material = test_plan
    # 模式只解析一次（minimal 消融档不解析：该档意图"无额外上下文"，
    # 与修复前 short-circuit 口径一致）；replace / augment 二选一。
    _spec_mode = "off" if ctx_minimal else _detection_spec_mode()
    _spec_replace_applied: str | None = None
    _spec_replace_section: str | None = None
    if _spec_mode == "replace":
        from src.tools.spec_first import build_spec_replace_section as _build_spec_replace

        _spec_replace_section = _build_spec_replace(
            _spec_material,
            state["target_code"],
            module_name=state.get("module_name", ""),
            # target_function 可缺席（state 可选字段）；spec_first 内按
            # test_plan.function_name 回退，None 透传是显式契约
            target_function=state.get("target_function") or "",
        )
        if _spec_replace_section:
            logger.info(
                "P0-A-2 规格优先模式：规约文档替换目标代码注入 Generator（%d 字符）", len(_spec_replace_section)
            )
            _spec_replace_applied = "attempted_replaced"
        else:
            _spec_replace_applied = "attempted_fallback"
    # M-1（2026-10-17）：规格增广模式（承接 L 轮 replace 阴性结论）——
    # 保留完整缺陷代码，把人类独立规格锚作为**独立 prompt 段并列追加**
    # （generator._build_query 在 code block 之后消费）。与 replace 分支
    # 互斥（同一 DETECTION_SPEC_MODE 只走一支，代码块不被替换）。
    # 无非空规格材料（如 QuixBugs node.py / 表缺失）→ None + 审计
    # attempted_fallback → prompt 即纯 df 代码口径（不产出空洞/误导段）。
    _spec_augment_applied: str | None = None
    _spec_augment_section: str | None = None
    if _spec_mode == "augment":
        from src.tools.spec_first import build_spec_augment_section as _build_spec_augment

        _spec_augment_section = (
            _build_spec_augment(
                _spec_material,
                state["target_code"],
                module_name=state.get("module_name", ""),
                target_function=state.get("target_function") or "",
            )
            or None
        )
        if _spec_augment_section:
            logger.info("M-1 规格增广模式：人类规格锚并列追加在目标代码之后（%d 字符）", len(_spec_augment_section))
            _spec_augment_applied = "attempted_augmented"
        else:
            _spec_augment_applied = "attempted_fallback"
    # 空计划短路（EMPTY_PLAN_SHORTCUT_ENABLE，默认关，ADR-0003）：
    # Planner 产出空计划（test_cases=[]，D1 根因：JSON 解析失败兜底
    # _get_default_test_plan）时，Generator 无法据此生成有效测试——跳过
    # LLM 调用直接产出空测试，省一次无用 LLM 调用（报告建议 13 置信度
    # 短路）。默认关时零行为变化（历史口径不变）。
    _empty_plan_shortcut = bool(
        _empty_plan_shortcut_enabled() and isinstance(test_plan, dict) and not test_plan.get("test_cases")
    )
    return {
        "metamorphic_section": _mr_section,
        "differential_section": _diff_section,
        "injection_findings": _injection_findings,
        "injection_warning": _injection_warning,
        "spec_replace_section": _spec_replace_section,
        "spec_augment_section": _spec_augment_section,
        "spec_replace_applied": _spec_replace_applied,
        "spec_augment_applied": _spec_augment_applied,
        "empty_plan_shortcut": _empty_plan_shortcut,
    }


def _build_generator_prompt_sections(state: AITesterState, test_plan: dict[str, Any]) -> dict[str, Any]:
    """构建 Generator prompt 的全部增强段落（自 `_generator_node` 提取，行为等价）。

    组合两组纯观测/prompt 增强层：静态分析段（分支覆盖 / 反馈压缩 / 边界
    锚点 / 路径 / 操作图）与无 oracle 段（蜕变 / 差分 / 注入扫描 / 规格优先
    / 规格增广 / 空计划短路）。各段开关默认关时返回 None（或空列表），
    历史 prompt 逐字节不变；``oracle_context_minimal`` 消融档下增强段统一
    不注入。本函数不调用 LLM、不写 state。

    Args:
        state: 当前状态（读取 target_code / 诊断文本等）。
        test_plan: Planner 计划（可为空 dict）。

    Returns:
        段落与观测标记字典，键集合固定（主节点按名消费）。
    """
    # 消融档只解析一次，两组段落共用同一口径（避免中途环境变化造成分叉）
    from src.tools.logic_spec import oracle_context_minimal as _oracle_ctx_minimal

    _ctx_minimal = _oracle_ctx_minimal()
    sections = _build_generator_static_sections(state, _ctx_minimal)
    sections.update(_build_generator_oracle_sections(state, test_plan, _ctx_minimal))
    return sections


def _run_generator_postchecks(state: AITesterState, generated_test: str) -> dict[str, Any]:
    """Generator 产出后的静态检查与确定性 oracle 注入（行为等价提取）。

    顺序与历史实现一致：AST 断言一致性 → 确定性守卫 → 恒真断言重生成判定
    → 测试套件断言去重 → 规约 oracle 注入。全部为纯静态分析（零 LLM），
    开关默认关时零行为变化。

    Args:
        state: 当前状态（读取 target_code / module_name 等）。
        generated_test: Generator 原始产出。

    Returns:
        含生成后代码、观测结果与再生成判定的字典（键集合固定）。BJ 轮起额外含
        ``oracle_check_status``（四值词表 worst-of 聚合）与 ``oracle_check_outcomes``
        （逐腿 ``{check, status, reason}``）：``oracle_findings`` 为空只有在
        status 为 ``ok`` 时才是"无疑点"证据。
    """
    # AST 级断言一致性检查（ORACLE_VALIDATE_ENABLE=true 时启用，默认关）：
    # 纯 AST 静态分析（零 LLM 成本），识别恒真断言 / 魔数断言 / 类型不一致
    # 三类疑点，写入 state["oracle_findings"] 供实验分析消费（观测层，不阻断
    # 主流程）。开关关闭 / 无生成内容时不执行（历史口径不变）。
    # BJ 轮（2026-10-22）：此前"findings 为空"这四种成因（扫过无疑点 / 开关关 /
    # 无生成内容 / 产物读不懂）在下方 tautological_count 与 O4 判定上完全不可
    # 区分——读不懂的产物恒判"零恒真断言" ⇒ O4 强制重生成对这类产物永不触发。
    # 现同向补披露（返回契约与判定方向逐字节不变）。
    from src.utils.check_status import CHECK_DISABLED, CHECK_OK, record_check_outcome, worst_check_status

    oracle_findings: list[dict[str, Any]] = []
    oracle_outcomes: list[dict[str, Any]] = []
    if not _oracle_validate_enabled():
        record_check_outcome(oracle_outcomes, "assertion_consistency", CHECK_DISABLED, "oracle_validate_disabled")
    elif not generated_test:
        record_check_outcome(oracle_outcomes, "assertion_consistency", CHECK_DISABLED, "no_generated_test")
    else:
        from src.tools.oracle_validator import check_assertions

        oracle_findings = check_assertions(generated_test, state["target_code"], outcome_sink=oracle_outcomes)
        if oracle_findings:
            logger.info(
                "AST 断言一致性检查发现 %d 个疑点（类型=%s）",
                len(oracle_findings),
                [f.get("type") for f in oracle_findings],
            )
    # 两条检查腿（断言一致性 + 被测侧类型推断）相互独立 ⇒ 最差者优先聚合。
    oracle_status = worst_check_status(str(o.get("status", "")) for o in oracle_outcomes)
    if oracle_status != CHECK_OK:
        logger.warning(
            "AST 断言一致性检查不可测量（status=%s）：疑点列表为空不构成无疑点证据（各腿=%s）",
            oracle_status,
            ", ".join(f"{o['check']}={o['status']}:{o['reason'] or '-'}" for o in oracle_outcomes),
        )
    # O6（2026-09-29 审查 P1）：确定性守卫（DETERMINISTIC_GUARD_ENABLE=true 时启用，默认关）。
    # 对 LLM 生成的测试代码做非确定性静态扫描（random / time.sleep / wall_clock /
    # 外部副作用），含 finding 的测试文件标记为"非确定性"，供实验层决定是否
    # 入库确定性套件。纯 AST 扫描（零 LLM 成本），不阻断主流程。
    # 开关关闭时 scan_test_file 返回空 findings（is_deterministic 恒 True），
    # 历史口径零变化。
    deterministic_guard_report: Any = None
    if generated_test:
        from src.agents.deterministic_guard import scan_test_file as _scan_det_guard

        _det_report = _scan_det_guard(generated_test, filename=state.get("module_name", "<memory>"))
        if _det_report.findings:
            logger.info(
                "O6 确定性守卫：%d 个非确定性 finding（规则=%s）",
                len(_det_report.findings),
                [f.rule for f in _det_report.findings],
            )
            deterministic_guard_report = _det_report
    # O4（2026-09-29 审查 P1）：恒真断言触发一次强制重生成。
    # tautological>=1 时标记 defect_type=test_defect，路由回 generator
    # 重生成（受再生成上限保护，防死循环）。
    # 开关关闭（ORACLE_VALIDATE_ENABLE=false，默认）时 oracle_findings 恒空，
    # 历史口径零变化。
    # Z2（2026-10-06 审查修复）：删除本函数内的同值局部字面量
    # `_MAX_REGENERATIONS = 1`（与 workflow 模块常量双源，靠注释"同口径"
    # 维系，漂移风险已登记），改用 config.MAX_REGENERATIONS 单一事实源。
    _tautological_count = sum(1 for f in oracle_findings if f.get("type") == "tautological")
    _o4_triggered = (
        _tautological_count >= 1
        and state.get("defect_type") != "test_defect"
        and int(state.get("regeneration_count", 0)) < MAX_REGENERATIONS
    )

    # N5（2026-09-29 审查 P2）：测试套件断言去重（HYPOTHESIS_ENABLE 同口径，
    # 独立开关 TEST_SUITE_DEDUP_ENABLE 默认 false 保持历史口径）。
    # LLM 生成的测试套件常含大量恒真断言（O4 已识别但无去重）；
    # 本层在 generator 产出后对 test_code 做 AST 级重复断言去除
    # （experiments/test_suite_minimize.dedup_assertions），纯数据
    # 零 LLM 成本，不改变路由 / 开关默认行为。
    generated_test, _dedup_removed = _apply_test_suite_dedup(generated_test)
    if _dedup_removed:
        logger.info("N5 测试套件断言去重：移除 %d 条重复断言", _dedup_removed)

    # R1c（2026-10-05 审查 P0）：确定性规约 oracle 注入（SPEC_ORACLE_EXEC_ENABLE=true
    # 时启用，默认关时零注入，历史口径不变）。详见 _append_spec_oracle_to_test。
    # P0-4（2026-10-10）：注入与行级判定一步到位——开关关 → (原文, None,
    # "not_attempted")；产物空 → (原文, False, "compiled_empty")；
    # 注入成功 → (追加产物, True, "injected")（执行后由 _executor_node 升级）。
    generated_test, _spec_oracle_injected, _spec_oracle_verdict = _spec_oracle_injection_verdict(generated_test, state)
    return {
        "generated_test": generated_test,
        "oracle_findings": oracle_findings,
        "oracle_check_status": oracle_status,
        "oracle_check_outcomes": list(oracle_outcomes),
        "deterministic_guard_report": deterministic_guard_report,
        "tautological_count": _tautological_count,
        "o4_triggered": _o4_triggered,
        "spec_oracle_injected": _spec_oracle_injected,
        "spec_oracle_verdict": _spec_oracle_verdict,
    }


def _generator_node(state: AITesterState) -> dict[str, Any]:
    """
    GeneratorAgent 节点：根据测试计划生成 pytest 测试代码。

    本节点的核心职责：
    1. 若 RAG 已启用，先检索相似历史测试用例作为风格参考（检索增强）
    2. 调用 GeneratorAgent 生成完整的 pytest 测试代码字符串
    3. 记录生成结果的长度，便于后续分析和调试

    设计考虑：
    - RAG 检索失败时静默跳过（logger.warning），不影响主流程
    - 若 ENABLE_PLANNER=False，传入 None 作为 test_plan，Generator 将基于裸代码生成

    Args:
        state: 当前状态，包含 test_plan（可选）、target_code、module_name 等字段。

    Returns:
        更新后的状态字典，包含 generated_test（测试代码字符串）和 rag_references（RAG 参考列表）。
    """
    agent = get_or_create_agent(GeneratorAgent)

    rag_refs, update_rag_stat = _retrieve_generator_rag_refs(state)

    # 调用 Generator 生成测试代码
    # 参数说明：
    #   - test_plan: 若启用 Planner 则传入结构化计划，否则为 None（Generator 将自行推断）
    #   - target_code: 被测代码全文，Generator 需要它来理解业务逻辑和生成 import 语句
    #   - module_name: 模块名（不含 .py），用于生成正确的 from X import Y 语句
    #   - rag_references: RAG 检索到的历史案例，用于风格参考（可为 None）
    #   - focus_function: 目标函数名（P0 大文件优化），超长代码时按该函数
    #     做 AST 智能截取，保留目标函数及直接依赖，避免 LLM 看不到完整上下文
    # Planner 缺席时 test_plan 为 None（documented behavior：Generator 基于裸代码自行推断，
    # 见 tests/test_workflow.py::test_generator_node_missing_test_plan_key_no_keyerror 回归口径）。
    # mypy 按 TypedDict 报 dict|None → dict，显式 cast 收窄（运行期传 None，Generator 内
    # isinstance(test_plan, dict) 守卫已覆盖 None 路径，行为不变）
    test_plan = cast("dict[str, Any]", state.get("test_plan"))

    # 2026-09-26 全面审查（P1 降级兜底）：此前 agent.generate 无 try-except，
    # LLM 调用失败（RuntimeError，含跨 API 故障转移耗尽）/ 缓存 OSError 会
    # 直接让整图崩溃——与 planner/debugger 节点"降级兜底"口径不一致（二者
    # 均有默认计划 / 空 patch 兜底），且 workflow.py 文档声称"使用 try-except
    # 捕获 LLM 调用异常，确保工作流不因单点故障而崩溃"。现补降级：LLM 失败时
    # 生成空测试 + 记诊断，executor 拿到空测试自然失败 → 路由到 debugger
    # （修代码）或 done，不再崩溃整图。历史行为是崩溃，新行为是优雅降级——
    # 对"LLM 完全不可用"场景更合理（崩溃 = 零产出，降级 = 仍有修复机会）。
    _generator_budget_hit = False  # 5.4 预算封顶标记（O35；正常路径恒 False）
    _empty_plan_shortcut = False  # 空计划短路标记（try 块外初始化，except 分支可达）
    # prompt 增强段落容器（try 块外初始化，except 分支可达；正常路径由
    # _build_generator_prompt_sections 填充，异常降级时各键按默认值消费）
    _sections: dict[str, Any] = {}
    try:
        _sections = _build_generator_prompt_sections(state, test_plan)
        _empty_plan_shortcut = _sections.get("empty_plan_shortcut", False)
        if _empty_plan_shortcut:
            logger.info("空计划短路：test_plan.test_cases 为空，跳过 Generator LLM 调用")
            generated_test = ""
        else:
            generated_test = agent.generate(
                test_plan,  # Planner 节点在图中时必带 test_plan；缺席时为 None，Generator 自行推断
                state["target_code"],
                module_name=state.get("module_name", ""),
                rag_references=rag_refs,
                focus_function=state.get("target_function"),
                # 1.2 改进（MutGen 式变异反馈闭环）：上一轮变异测试的存活变异体注入
                # prompt，引导生成针对"当前未捕获故障"的更强断言（None 时不注入）
                mutation_feedback=state.get("mutation_feedback"),
                # 3.3 改进：执行反馈驱动的动态 temperature（覆盖率连降时减半，None 时不覆盖）
                temperature=_dynamic_temperature_from_suggestion(state.get("iteration_strategy_suggestion")),
                # O12（2026-09-29 审查 P1）：复杂度感知路由——complexity_class 非 None 时
                # 经 _call_llm_with_cache → _call_llm → _reorder_api_groups_by_complexity
                # 按档位重排 API 组（complex → 高成本端点在前），使
                # MODEL_ROUTING_STRATEGY=complexity_aware（默认值）真实生效。
                complexity_class=state.get("complexity_class"),
                # O3（2026-09-29 审查 P1）：未覆盖分支清单提示段落（None 时不注入）
                branch_coverage_section=_sections.get("branch_coverage_section"),
                # M10（2026-09-29 审查 P0）：确定性边界锚点提示段落（None 时不注入）
                boundary_triplets_section=_sections.get("boundary_triplets_section"),
                # P2-7（N2/N4）：无 oracle 场景增强段落（None 时不注入）
                metamorphic_section=_sections.get("metamorphic_section"),
                differential_section=_sections.get("differential_section"),
                # W3（2026-10-05 审查落地·检出优先协议）：检出优先再生成路径的
                # "先红后绿"强化段落（非该路径时 None 不注入，历史口径零变化）
                detection_first_section=_detection_first_section(state),
                # 2026-10-10（结果二十四）：过红再生成强化段落
                # （OVER_RED_SECTION_ENABLE 默认关 → None 不注入，历史口径零变化）
                over_red_section=_over_red_section(state),
                # 2026-10-10 独立审查落地（报告建议 4 结构接地·路径定向合成）：
                # 独立执行路径枚举段落（PATH_ENUM_INJECT_ENABLE 默认关时 None 不注入）
                paths_section=_sections.get("paths_section"),
                # 2026-10-10 独立审查落地（报告建议 4 结构接地·操作图）：
                # 已验证符号清单段落（OPERATION_MAP_INJECT_ENABLE 默认关时 None 不注入）
                operation_map_section=_sections.get("operation_map_section"),
                # P2（2026-10 批次·续二）：注入扫描系统侧警示（命中注入特征时非空，
                # INJECTION_GUARD_ENABLE 默认关时恒 None，历史口径零变化）
                injection_warning=_sections.get("injection_warning"),
                # P0-A-2（2026-10-12）：规格优先生成规约文档段（replace 模式且
                # 有规约材料时非空；None 时 _build_query 保持历史口径注入目标代码）
                spec_replace_section=_sections.get("spec_replace_section"),
                # M-1（2026-10-17）：规格增广段（augment 模式且存在非空规格材料
                # 时非空；None 时 _build_query 保持历史查询逐字节不变）
                spec_augment_section=_sections.get("spec_augment_section"),
                # P2 一期（观测级压缩）：失败行+错误类型+变异摘要的压缩反馈
                # 段落（FEEDBACK_COMPRESSION_ENABLE 默认关时 None 不注入，
                # 历史口径零变化）
                feedback_compression_section=_sections.get("feedback_compression_section"),
            )
    except (RuntimeError, OSError, json.JSONDecodeError) as e:
        # 5.4 预算封顶：BudgetExceededError（isinstance 判定）快速降级空测试，
        # 后续迭代经 MAX_ITERATIONS 自然收敛（各节点前置预算守卫行为一致）
        if isinstance(e, BudgetExceededError):
            logger.warning("Generator LLM 调用失败（5.4 预算封顶），降级为空测试: %s", e)
        else:
            logger.warning("Generator LLM 调用失败，降级为空测试: %s", e)
        generated_test = ""
        _generator_budget_hit = isinstance(e, BudgetExceededError)

    # 2.3 改进：复现测试专项生成（REPRO_TEST_ENABLE=true 且已有缺陷描述时）。
    # 缺陷描述优先取 diagnosis（上一轮 Debugger 根因分析），跨文件修复场景下
    # 该描述含缺陷触发路径信息；生成覆盖触发路径的复现测试写入 state["repro_test"]。
    repro_test: str | None = None
    defect_description = state.get("diagnosis") or state.get("review_reason") or ""
    if _repro_test_enabled() and defect_description:
        # target_module 缺失/空串时跳过（falsy 过滤保持原语义），非空则纳入跨文件提示
        cross_modules = [
            str(d["target_module"]) for d in (state.get("cross_file_deps") or []) if d.get("target_module")
        ]
        # 2026-10-01 全面审查 P1 修复：2.3 复现测试分支此前无 try/except 兜底——
        # 主生成路径（agent.generate，L546）有 try/except (RuntimeError, OSError,
        # json.JSONDecodeError) 降级为空测试，但 generate_repro_test 走同一条 LLM
        # 调用路径（_call_llm_with_cache，可抛 RuntimeError / BudgetExceededError /
        # OSError / JSONDecodeError），异常直接传播出 _generator_node 崩整图，
        # 与主生成路径的"降级兜底"口径不一致（workflow.py 文档承诺"工作流不因
        # 单点故障崩溃"）。现补同口径 try/except：LLM 失败时 repro_test=None
        # 降级（复现测试缺失不阻断主生成路径，executor 仍走 generated_test）。
        try:
            repro_test = agent.generate_repro_test(
                defect_description=defect_description,
                target_code=state["target_code"],
                module_name=state.get("module_name", ""),
                cross_file_modules=cross_modules or None,
                temperature=_dynamic_temperature_from_suggestion(state.get("iteration_strategy_suggestion")),
            )
        except (RuntimeError, OSError, json.JSONDecodeError) as e:
            if isinstance(e, BudgetExceededError):
                logger.warning("复现测试（2.3）LLM 调用失败（5.4 预算封顶），降级为跳过: %s", e)
            else:
                logger.warning("复现测试（2.3）LLM 调用失败，降级为跳过（不阻断主生成）: %s", e)
            repro_test = None
        logger.info("复现测试（2.3）生成完成，长度=%d", len(repro_test or ""))
    # 记录生成结果长度，便于评估 Generator 的输出质量
    logger.info("Generator 完成测试代码生成，长度=%d", len(generated_test))

    _post = _run_generator_postchecks(state, generated_test)
    generated_test = _post["generated_test"]
    oracle_findings = _post["oracle_findings"]
    oracle_check_status = _post["oracle_check_status"]
    oracle_check_outcomes = _post["oracle_check_outcomes"]
    deterministic_guard_report = _post["deterministic_guard_report"]
    _tautological_count = _post["tautological_count"]
    _o4_triggered = _post["o4_triggered"]
    _spec_oracle_injected = _post["spec_oracle_injected"]
    _spec_oracle_verdict = _post["spec_oracle_verdict"]

    _trace_node(
        "generator",
        # BL 轮（2026-10-22）：把 oracle 腿的可测量性带进 trace——G4 的
        # `check_unmeasurable` 模式是这些 status 键在判定侧的第一个读者，
        # 但 trace 不带键时它对真实 JSONL 恒不命中（"没读到"≠"没发生"）。
        # 纯观测，不改 decision。
        output_summary={"generated_test_len": len(generated_test), "oracle_check_status": oracle_check_status},
        decision="regenerated"
        if state.get("iteration", 0) >= state.get("max_iterations", MAX_ITERATIONS)
        else "generated",
    )
    update: dict[str, Any] = {
        "generated_test": generated_test,
        "rag_references": rag_refs,
    }
    # 空计划短路标记（EMPTY_PLAN_SHORTCUT_ENABLE 默认关时恒 False；开启且命中
    # 时 True，供实验层统计"短路省了多少次 LLM 调用"，纯观测不改变路由）。
    update["empty_plan_shortcut"] = _empty_plan_shortcut
    # R1c（2026-10-05 审查 P0）+ P0-4（2026-10-10）：确定性规约 oracle 注入标记与
    # 行级判定结果（state 键已声明，不会被 LangGraph 白名单丢弃）。三态：
    # True = 已注入 / False = 尝试编译但产物空 / None = 开关关或未尝试；
    # verdict 取值域见 _SPEC_ORACLE_VERDICT_* 常量（执行后由 _executor_node 升级）。
    update["spec_oracle_injected"] = _spec_oracle_injected
    update["spec_oracle_verdict"] = _spec_oracle_verdict
    # P0-A-2（2026-10-12）：规格优先替换段可审计观测（state 键已声明，不会被
    # LangGraph 白名单丢弃；取值域见 _spec_replace_applied 初始化处注释，
    # 与 R1c 确定性 oracle 执行注入 spec_oracle_injected 独立）。
    update["spec_replace_applied"] = _sections.get("spec_replace_applied")
    # M-1（2026-10-17）：规格增广段可审计观测（state 键已声明，不会被 LangGraph
    # 白名单丢弃；取值域见 _spec_augment_applied 初始化处注释：
    # attempted_augmented / attempted_fallback / None）。
    update["spec_augment_applied"] = _sections.get("spec_augment_applied")
    # 5.4 预算封顶标记（O35）：Generator 捕获 BudgetExceededError 时置真
    # （planner / debugger 同口径），使 determine_stop_reason 可达 BUDGET_EXCEEDED。
    if _generator_budget_hit or state.get("budget_exceeded"):
        update["budget_exceeded"] = True
    # 2.3 改进：复现测试生成结果（未启用 / 无缺陷描述时保持 None）
    if repro_test:
        update["repro_test"] = repro_test
    # P2（2026-10 批次·续二）：注入扫描 findings 写入 state（INJECTION_GUARD_ENABLE
    # 默认关时恒 []，历史口径零变化；非空时供 agent_telemetry 的
    # injection_detected 模式消费 + trace 记录，配合 experiments/
    # injection_benchmark_samples.json 回归基准度量召回/误伤）。
    update["injection_findings"] = _sections.get("injection_findings", [])
    # AST 级断言一致性检查（ORACLE_VALIDATE_ENABLE=true 时非空，默认关时零变化）
    if oracle_findings:
        update["oracle_findings"] = oracle_findings
    # BJ 轮（2026-10-22）：上面那条"非空才写键"的可测量性对偶——本轮新增两键恒写
    # （开关关时为 disabled）。读法：``oracle_findings`` 为空且 status != ok ⇒
    # "没读出疑点"而不是"没有疑点"，O4 强制重生成对这类产物恒不触发。
    # 键已在 AITesterState 显式声明（state.py），不会被 LangGraph 白名单丢弃。
    update["oracle_check_status"] = oracle_check_status
    update["oracle_check_outcomes"] = oracle_check_outcomes
    # P2 一期（观测级压缩）：压缩反馈产物持久化（FEEDBACK_COMPRESSION_ENABLE
    # 默认关时恒 None，键集合同构；state 键已在 AITesterState 显式声明，
    # 不会被 LangGraph 白名单丢弃——O35 教训）。供实验层统计「压缩通道
    # 到达率 / 段落体积（section_chars）」消费，纯观测不参与路由。
    update["compressed_feedback"] = _sections.get("compressed_feedback")
    # 修复引擎批次 XIV（ADR-0028 观测层）：oracle 质量历史快照——
    # Self-Repair Trap（DCAware：迭代自修复驱使断言退化）的数据面。
    # 每次生成/再生成的最终测试（去重与规约注入之后）落一份快照；
    # 空测试不落（生成失败是另一类失败模式，不属于"断言退化"）。
    # 纯观测零行为影响；阻断 / 策略切换须先有 A/B 数据与预注册判据。
    if generated_test:
        from src.tools.self_repair_trap import snapshot_test_quality

        _mf = state.get("mutation_feedback")
        _ms = _mf.get("mutation_score") if isinstance(_mf, dict) else None
        _quality_history = list(state.get("oracle_quality_history") or [])
        _quality_history.append(
            snapshot_test_quality(
                generated_test,
                mutation_score=float(_ms) if isinstance(_ms, (int, float)) and not isinstance(_ms, bool) else None,
                regeneration=int(state.get("regeneration_count", 0)),
            )
        )
        update["oracle_quality_history"] = _quality_history
    # O4（2026-09-29 审查 P1）：恒真断言强制重生成——标记 defect_type=test_defect，
    # 触发 _should_debug 的 regenerate 路由（受 regeneration_count 上限保护，防死循环）。
    if _o4_triggered:
        logger.info(
            "O4：恒真断言 %d 条，标记 defect_type=test_defect 触发强制重生成（regeneration_count=%d）",
            _tautological_count,
            state.get("regeneration_count", 0),
        )
        update["defect_type"] = "test_defect"
    # O6（2026-09-29 审查 P1）：确定性守卫报告（DETERMINISTIC_GUARD_ENABLE=true 时非空，默认关时零变化）
    if deterministic_guard_report is not None:
        update["deterministic_guard_report"] = {
            "filename": deterministic_guard_report.filename,
            "findings": [
                {"rule": f.rule, "detail": f.detail, "line": f.line} for f in deterministic_guard_report.findings
            ],
            "is_deterministic": deterministic_guard_report.is_deterministic,
        }
    # O4（2026-09-29 审查 P1）：恒真断言强制重生成路径。
    # _tautological_count >= 1 时已写入 update["defect_type"] = "test_defect"，
    # 下方再生成路径检测的条件 2（state.get("defect_type") == "test_defect"）
    # 读取的是**历史** state（非 update），故须将 O4 触发条件并入再生成路径判定：
    # _tautological_count >= 1 且 regeneration_count 未达上限时，视为再生成路径，
    # +1 计数并清空旧诊断（与 3.1 双向诊断路径同口径，防死循环）。
    # _o4_triggered 已在上方（L658）定义，此处直接引用。
    # 累计 RAG 检索指标（本节点读取后携带历史值，避免后续节点覆盖丢失）
    if update_rag_stat:
        update["rag_stats"] = [*list(state.get("rag_stats") or []), update_rag_stat]
    # 再生成路径检测：判定"本节点是否由 regenerate 路由进入"。
    # 覆盖三类进入方式：
    #   1. _should_debug 路由 "regenerate"（iteration >= max_iterations，诊断指向测试生成错误）；
    #   2. 3.1 双向诊断路由 "regenerate"（defect_type == "test_defect"，Review Agent
    #      判定为测试缺陷，可在任意 iteration 触发）；
    #   3. _should_debug 早期路由 "regenerate"（iteration < max_iterations 且 diagnosis
    #      命中 test-generation 关键词，2026-09-26 审查提升为任意 iteration 可触发的
    #      独立分支，reason=test_gen_diagnosis_early）：特征为 iteration > 0 且
    #      diagnosis 非空（首生成恒 iteration=0 且 diagnosis=None，故可区分）。
    # 此前仅条件 1/2 成立时 +1 计数，条件 3 的早期路径漏计 regeneration_count
    # → _should_debug 第 425 行上限保护（regeneration_count < _MAX_REGENERATIONS）
    # 永远 0 < 1 成立 → 关键词持续命中时 generator↔executor 无限乒乓
    # （实测 fibonacci_inefficient 任务 trace 6000+ 行死循环）。
    # - 首次生成（iteration=0，diagnosis=None）：不改变 regeneration_count，保留原有
    #   diagnosis（尚无修复结论）
    # - 再生成：计数 +1（供 _should_debug 上限判断），并清空上一轮诊断，
    #   避免旧的 diagnosis 关键词在新测试仍失败时再次触发 regenerate（死循环根因）
    if (
        state.get("iteration", 0) >= state.get("max_iterations", MAX_ITERATIONS)
        or state.get("defect_type") == "test_defect"
        or (state.get("iteration", 0) > 0 and state.get("diagnosis") is not None)
        # J-4（2026-10-17）：`or _o4_triggered` 已移除——本块统计的是"本节点因
        # 再生成路由而进入"，而 O4 是本轮**发出**再生成信号（发出方不是进入方）。
        # config.MAX_REGENERATIONS 当前为 1，在发出的那一轮就 +1 会把唯一一次
        # 再生成预算直接烧掉：_should_debug 的 defect_type 分支要求
        # regeneration_count < 上限，于是恒 1 < 1 = False → done，O4 强制重生成
        # 即使修好标记覆盖（见下方 defect_type 守卫）也仍然走不到。
        # 防死循环不受影响：下一轮 state["defect_type"] == "test_defect" 命中
        # 上方第二个条件时照常 +1 并清空标记，上限保护与 3.1 双向诊断同口径。
        # W3（2026-10-05 审查落地·检出优先协议）：第 4 类再生成进入方式——
        # _should_debug 的 detection_first_all_green 分支（首轮全绿未检出）。
        # 特征 iteration==0 + test_passed=True 与首生成（test_passed=None）可区分，
        # 不并入本条件则该路径 regeneration_count 恒 0 → 上限保护失效 →
        # executor↔generator 无限乒乓直至 recursion_limit（O4 同类根因）。
        or _detection_first_regenerate_entry(state)
        # 修复引擎批次 III（AC2 补漏）：第 5 类再生成进入方式——特异性门
        # over_red 路由（test_passed=False，W3 检测不覆盖；不并入则该路径
        # 计数恒 0 → 上限失效 → executor↔generator 无限乒乓撞 recursion_limit，
        # E2 实证 16/174 触顶的根因通道）。
        or _specificity_over_red_regenerate_entry(state)
    ):
        update["regeneration_count"] = state.get("regeneration_count", 0) + 1
        update["diagnosis"] = None
        update["error_category"] = None
        # 3.1 双向诊断 + O4：重新生成测试后清空旧判定，避免"test_defect"信号
        # 在下一轮仍触发 regenerate（与 regeneration_count 上限共同防死循环）
        #
        # J-4（2026-10-17）修复：清的是**历史**判定，本轮 O4 新写的标记必须保留。
        # 此前无条件置 None 与上方 update["defect_type"] = "test_defect"（O4 分支）
        # 写同一个键、同一次返回，后写覆盖前写；而本块的进入条件之一恰是
        # _o4_triggered —— 于是 O4"恒真断言触发强制重生成"的路由信号永远到不了
        # _should_debug（workflow.py 只读 state["defect_type"]，oracle_findings
        # 全仓无路由消费者），该机制自落地起即为死路径（开关
        # ORACLE_VALIDATE_ENABLE 默认关，故历史实验数据不受影响）。
        # _o4_triggered 蕴含 state["defect_type"] != "test_defect"（触发条件之一），
        # 故此处保留新标记与"清旧判定"的原意不冲突。
        if not _o4_triggered:
            update["defect_type"] = None
        update["review_reason"] = None
    return update


# ─── ExecutorAgent 惰性单例（2026-09-28 性能优化）────────────────────────────
# _executor_node 每轮迭代 new 一个 ExecutorAgent。其构造仅存储沙箱配置
# （timeout/use_docker/use_venv/auto_install_deps/dep_install_timeout/
# docker_image），无内部可变状态：agent.execute() 每次调用独立构建沙箱、
# 运行 pytest、回收输出。沙箱参数全部来自 config 模块常量（进程内不变），
# 仅 execution_timeout 可经 CLI 注入——故按完整参数元组分键缓存实例：
# 同配置复用（省每轮构造 + 日志初始化），不同配置（--timeout 变体）各建一份，
# 并发下 DCL + 线程锁保证同键只构造一次。开关：
# AITESTER_EXECUTOR_AGENT_CACHE=0 关闭（默认启用，行为不变）。


def _executor_attempt_evidence(result: dict[str, Any]) -> dict[str, Any]:
    """A16（2026-10-18 第三方评审 P1）：从 Executor 结果恢复尝试证据。

    兼容旧结果 dict（无 execution_attempts / flaky_fail_then_pass 字段时
    行为与历史逐字一致：summary 全零、fail_then_pass=False）。真实序列优先：
    fail→pass = 同一 (target_code, generated_test) 多次执行结果不一致，是
    flaky 的直接证据，不能被最后一次成功结果抹掉。

    Args:
        result: ExecutorAgent.execute 返回 dict。

    Returns:
        summarize_execution_attempts 汇总 dict，并把 flaky_fail_then_pass
        显式标记并入 ``fail_then_pass`` 键。
    """
    raw_attempts = result.get("execution_attempts")
    records = [dict(item) for item in raw_attempts if isinstance(item, dict)] if isinstance(raw_attempts, list) else []
    summary = summarize_execution_attempts(records)
    summary["fail_then_pass"] = bool(result.get("flaky_fail_then_pass")) or bool(summary["fail_then_pass"])
    return summary


def _apply_executor_rogue_monitor(update: dict[str, Any]) -> None:
    """R16 流氓 agent 行为监控（自 `_executor_node` 提取，行为等价）。

    ``ROGUE_MONITOR_ENABLE=true`` 时对四个核心 agent（Planner/Generator/
    Executor/Debugger）做三类信号检测（调用频率 z-score / 动作熵 / 能力违规）；
    非空 findings 写入 ``update["rogue_findings"]``。纯观测，不改路由——
    隔离/升级由调用方决定，与 rogue_monitor 模块"只报警不熔断"口径一致。

    Args:
        update: 本节点待返回的状态更新字典（原地写入）。

    Returns:
        None
    """
    if rogue_monitor_enabled():
        from src.agents.rogue_monitor import get_rogue_monitor as _get_rogue_monitor

        _rogue_findings: list[dict[str, Any]] = []
        _monitor = _get_rogue_monitor()
        for _agent_cls in ("PlannerAgent", "GeneratorAgent", "ExecutorAgent", "DebuggerAgent"):
            _rogue_findings.extend(
                {"agent_id": f.agent_id, "kind": f.kind, "detail": f.detail, "metric": f.metric}
                for f in _monitor.check(_agent_cls)
            )
        if _rogue_findings:
            logger.warning(
                "R16 流氓行为监控：%d 个 finding（%s）", len(_rogue_findings), [f["kind"] for f in _rogue_findings]
            )
            update["rogue_findings"] = _rogue_findings


def _apply_executor_flaky_gate(
    update: dict[str, Any],
    state: AITesterState,
    agent: Any,
    result: dict[str, Any],
    passed: bool,
    attempt_summary: dict[str, Any],
    fail_then_pass: bool,
) -> None:
    """R35/R31 + A16 flaky 门（自 `_executor_node` 提取，行为等价）。

    两条证据通道：① 重试层已观察到 fail→pass（A16，证据本身即结论，
    不再重复执行）；② ``FLAKY_CHECK_ENABLE=true`` 时对失败轮重复执行
    ``FLAKY_REPEAT_COUNT`` 次。命中 flaky 时 ``test_passed`` 保守记 False
    （不稳定结果不能作"修复正确"证据），并写 flaky 观测键。

    Args:
        update: 本节点待返回的状态更新字典（原地写入）。
        state: 当前状态。
        agent: 执行器实例（供重复执行复用）。
        result: 本轮执行结果。
        passed: 本轮有效通过标记（已消费 fail→pass 证据）。
        attempt_summary: 重试层尝试摘要。
        fail_then_pass: 重试层是否观察到 fail→pass。

    Returns:
        None
    """
    _attempt_flaky_handled = False
    if fail_then_pass:
        _attempt_flaky_handled = True
        update["flaky_detected"] = True
        update["flaky_pass_count"] = int(attempt_summary.get("pass_count", 0))
        update["flaky_total_count"] = int(attempt_summary.get("attempts", 0))
        update["flaky_unverified"] = True
        update["test_passed"] = False
        logger.warning(
            "A16 观察到 fail→pass 重试证据（%d 次尝试中 %d 通过 / %d 失败），test_passed 保守记 False（flaky）",
            int(attempt_summary.get("attempts", 0)),
            int(attempt_summary.get("pass_count", 0)),
            int(attempt_summary.get("fail_count", 0)),
        )
    if _flaky_check_enabled() and not passed and not _attempt_flaky_handled:
        from src.agents.flaky_gate import detect_flaky as _detect_flaky

        _flaky = _detect_flaky(
            executor=agent,
            test_code=state.get("generated_test") or "",
            target_file=state.get("target_file") or "",
            target_function=state.get("target_function"),
            base_result=result,
        )
        update["flaky_detected"] = bool(_flaky["flaky"])
        update["flaky_pass_count"] = _flaky["pass_count"]
        update["flaky_total_count"] = _flaky["total"]
        if _flaky["flaky"]:
            logger.warning(
                "R35 flaky 检测：同测试 %d 次执行 %d 通过 / %d 失败（不稳定），test_passed 保守记 False",
                _flaky["total"],
                _flaky["pass_count"],
                _flaky["fail_count"],
            )
            # flaky 轮：结果不可信，保守按失败处理（不作"修复正确"证据）
            update["test_passed"] = False
            update["flaky_unverified"] = True
        else:
            # 全 fail（稳定失败）：结果可信，保留原 test_passed=False
            update["flaky_unverified"] = False


def _apply_executor_detection_first(update: dict[str, Any], state: AITesterState, passed: bool) -> None:
    """W3 检出优先三值终态标注（自 `_executor_node` 提取，行为等价）。

    首轮（iteration==0）执行时维护任务级粘性信号 ``detection_first_red_seen``；
    每轮按 (passed, red_seen) 写三值终态（red_then_green /
    all_green_unverified / red_not_repaired），最后一次写入即终态。

    Args:
        update: 本节点待返回的状态更新字典（原地写入）。
        state: 当前状态。
        passed: 本轮有效通过标记。

    Returns:
        None
    """
    if detection_first_enabled():
        if int(state.get("iteration", 0)) == 0:
            update["detection_first_red_seen"] = (not passed) or bool(state.get("detection_first_red_seen"))
        _df_red_seen = update.get("detection_first_red_seen", state.get("detection_first_red_seen"))
        _df_status = _derive_detection_first_status(bool(passed), _df_red_seen)
        if _df_status is not None:
            update["detection_first_status"] = _df_status


def _apply_executor_ac2_gates(update: dict[str, Any], state: AITesterState, passed: bool) -> None:
    """AC2 检出优先双门（自 `_executor_node` 提取，行为等价）。

    ① 特异性门（``DETECTION_SPECIFICITY_GATE_ENABLE``）：首轮红时在 gold
    fixed 代码上复测，判定 specific_red / over_red / unavailable，并写
    ``specificity_gate_verdict`` 与红证人快照；
    ② 红回归门（``RED_REGRESSION_GATE_ENABLE``）：曾见红 + 测试再生成后变绿
    + 源码未修补 = 抹红假成功，恢复红证人并保守置失败。

    Args:
        update: 本节点待返回的状态更新字典（原地写入）。
        state: 当前状态。
        passed: 本轮有效通过标记。

    Returns:
        None
    """
    if not detection_first_enabled():
        return
    from src.tools.detection_gates import (
        detection_specificity_gate_enabled,
        red_regression_check,
        specificity_verdict,
    )

    _gate_passed = passed
    if int(state.get("iteration", 0)) == 0 and not _gate_passed:
        _verdict: str | None = None
        if detection_specificity_gate_enabled():
            # P0-1（2026-10-11 全面优化批次）：透传 task_metadata——跨文件
            # 任务的伴生模块（module_a/b/c 代码与名）由 M1 委托层据此物化；
            # 缺失时委托层回退单文件口径（与历史逐位一致，零回归）。
            # 构建与 M1 委托层同口径的 metadata：is_cross_file 由 cross_file_deps
            # 非空推导；target_module 由 _resolve_target_module 口径（module_name）
            # 填入；source 取 state 原始值（缺省 None，不注入）。
            _has_cross_file = bool(state.get("cross_file_deps"))
            _gate_task_metadata: dict[str, Any] | None = None
            if _has_cross_file:
                # P0-1 勘误：模块代码/名键不在 TypedDict state 中（由
                # run_benchmark 写盘而非 state），委托层走单文件物化口径。
                _gate_task_metadata = {"is_cross_file": True}
                if state.get("module_name"):
                    _gate_task_metadata["target_module"] = str(state["module_name"])
            _verdict = specificity_verdict(
                state.get("generated_test") or "",
                state.get("gold_fixed_code"),
                state.get("module_name"),
                task_metadata=_gate_task_metadata,
            )
            update["specificity_gate_verdict"] = _verdict
            logger.info("AC2 特异性门判定：%s", _verdict)
        if _verdict != "over_red":
            update["red_witness_test_code"] = state.get("generated_test")
    elif _gate_passed:
        _gate_upd = red_regression_check(state, state.get("generated_test") or "")
        if _gate_upd:
            update.update(_gate_upd)
            # 门②恢复后同步重推三值终态（本轮 test_passed 已被门改 False）
            _rv_status = _derive_detection_first_status(
                False, update.get("detection_first_red_seen", state.get("detection_first_red_seen"))
            )
            if _rv_status is not None:
                update["detection_first_status"] = _rv_status
            logger.warning("AC2 红回归门：再生成测试抹掉红证人（源码未修补），恢复红证人交回修复循环")


def _apply_executor_branch_coverage(update: dict[str, Any], state: AITesterState) -> None:
    """O3 分支覆盖率注入层（自 `_executor_node` 提取，行为等价）。

    ``BRANCH_COVERAGE_INJECT_ENABLE=true`` 且非 Docker 链路时，对
    (target_file, generated_test) 做 branch=True 测量，写
    ``update["branch_coverage"]``。纯观测层，测量失败时不写键。

    Args:
        update: 本节点待返回的状态更新字典（原地写入）。
        state: 当前状态。

    Returns:
        None
    """
    if _branch_coverage_inject_enabled() and not EXECUTOR_USE_DOCKER:
        from src.tools.branch_coverage_inject import measure_branch_coverage as _measure_bc

        _bc_result = _measure_bc(
            target_file=state.get("target_file") or "",
            test_code=state.get("generated_test") or "",
            module_name=state.get("module_name") or "",
        )
        if _bc_result is not None:
            update["branch_coverage"] = _bc_result


def _apply_executor_patch_rollback(update: dict[str, Any], state: AITesterState, passed: bool) -> None:
    """M6 坏补丁失败回滚（自 `_executor_node` 提取，行为等价）。

    本轮执行失败且 state 中存在上一轮补丁快照时，恢复原始代码并同步写回
    磁盘（C6：状态与存储同事务）；回滚成功置 ``last_patch_rolled_back=True``
    并经 update 清空快照键（O35）。失败轮同时丢弃上一轮暂存修复案例。

    Args:
        update: 本节点待返回的状态更新字典（原地写入）。
        state: 当前状态。
        passed: 本轮有效通过标记。

    Returns:
        None
    """
    if not passed:
        # C6（2026-10-05 系统审查 P0）：磁盘与 state 同事务恢复——
        # restored_out 携带快照原文，写回 state["target_code"]，否则下一轮
        # Debugger 分析/补丁基底仍是坏补丁代码（"测原码/修补码"幻象迭代）。
        _restored: dict[str, Any] = {}
        _rolled_back = _rollback_last_patch(state, restored_out=_restored)
        if _rolled_back:
            update["last_patch_rolled_back"] = True
            update["_last_patch_snapshot"] = None
            update["_last_patch_iteration"] = None
            if "content" in _restored:
                update["target_code"] = _restored["content"]
        # C10：本轮失败 → 上一轮补丁未通过验证，丢弃暂存（不入修复案例库）
        update["last_applied_repair"] = None


def _runtime_probe_backend(agent: Any, result: dict[str, Any]) -> str:
    """N01（2026-10-22 第三方复审 P1）：主执行实际隔离级别 → 探针可用后端。

    探针只在宿主解释器里跑，因此只有在主执行本来就没有更强隔离可用时
    （local / venv）才允许重放；Docker / 内核沙箱 / 隔离拒绝一律返回不可用
    档位，由 `capture_failure_snapshot` 拒绝启动子进程（宁缺不降级）。

    Args:
        agent: 执行器实例（读 use_docker / use_venv / 内核沙箱观测）。
        result: 执行结果（读 error_info.type 识别隔离拒绝）。

    Returns:
        "local" / "venv" / "docker" / "kernel" / "refused"。
    """
    err_type = str(((result or {}).get("error_info") or {}).get("type") or "")
    if err_type in ("docker_unavailable", "kernel_sandbox_unavailable", "sandbox_unavailable"):
        # 显式隔离拒绝之后不得在宿主重执行（威胁模型 T4：不可用即拒绝）
        return "refused"
    if getattr(agent, "use_docker", False):
        return "docker"
    if getattr(agent, "_kernel_sandbox_executable", None):
        return "kernel"
    if getattr(agent, "use_venv", False):
        return "venv"
    return "local"


def _executor_node(state: AITesterState) -> dict[str, Any]:
    """
    ExecutorAgent 节点：执行测试并记录结果。
    测试通过后自动入库（若 RAG 可用且已启用），供后续检索使用。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典，包含 test_passed, test_output, coverage_report, failed_cases。

    超时优先级：state["execution_timeout"]（CLI --timeout 注入）> config.EXECUTION_TIMEOUT。
    此前直接读环境变量原始值，绕过了 config 的范围校验（_validate_timeout），
    导致 CLI --timeout 不生效且非法配置（如 0s）未被兜底。
    3.2 执行反馈轨迹：每次执行经 _record_execution_trace 追加到
    state["execution_trace"]（3.2 默认常开，纯观测层，不参与路由）。
    """
    # CLI 通过 state 注入的执行超时优先，未注入时回退到 config 中已校验的值
    executor_timeout = int(state.get("execution_timeout") or EXECUTION_TIMEOUT)
    t0 = time.time()
    # 隔离沙箱参数（P1 依赖隔离）：默认关闭，保持与历史实验一致；
    # 通过环境变量 EXECUTOR_USE_VENV / EXECUTOR_AUTO_INSTALL_DEPS 开启。
    # 4.3 Docker 隔离执行：EXECUTOR_USE_DOCKER=true 时经 docker CLI 在容器内
    # 跑 pytest（镜像 EXECUTOR_DOCKER_IMAGE，默认 aitester:latest）。
    # （2026-09-26 全面审查：EXECUTOR_DOCKER_IMAGE / EXECUTOR_USE_DOCKER 移入
    # 文件头导入，与同文件其他 config 符号风格一致）
    agent = _get_or_create_executor_agent(
        timeout=executor_timeout,
        use_docker=EXECUTOR_USE_DOCKER,
        use_venv=EXECUTOR_USE_VENV,
        auto_install_deps=EXECUTOR_AUTO_INSTALL_DEPS,
        dep_install_timeout=EXECUTOR_DEP_INSTALL_TIMEOUT,
        docker_image=EXECUTOR_DOCKER_IMAGE,
    )
    result = agent.execute(
        test_code=state["generated_test"] or "",
        target_file=state["target_file"],
        target_function=state.get("target_function"),
    )
    # A16（2026-10-18 第三方评审 P1）：重试层保留每次尝试记录；首败次过
    # （fail→pass）是"测试自身不稳定"的真实证据——旧实现只留最后一次成功
    # 结果，flaky 门（仅对 passed=False 生效）永远看不到它。现按真实序列
    # 保守处理：effective passed = 最后一次 rc==0 且未观察到 fail→pass；
    # 无该证据时本变量与 result["passed"] 完全相同（历史字段/行为不变）。
    _attempt_summary = _executor_attempt_evidence(result)
    _fail_then_pass = bool(_attempt_summary.get("fail_then_pass"))
    _passed = bool(result["passed"]) and not _fail_then_pass
    status = "PASS" if _passed else "FAIL"
    logger.info(
        "Executor 完成第 %d 轮测试：%s，覆盖率=%.1f%%，失败用例数=%d",
        state.get("iteration", 0) + 1,
        status,
        result["coverage"],
        len(result["failed_cases"]),
    )
    _trace_node(
        "executor",
        output_summary={
            "passed": _passed,
            "coverage": result["coverage"],
            "failed_cases": len(result["failed_cases"]),
        },
        decision=status,
        duration_ms=(time.time() - t0) * 1000,
        iteration=state.get("iteration", 0),
    )

    # 统一走 rag_guarded 降级守卫（P1 重构）：测试通过时入库成功用例
    _consume_pending_repair = False
    if _passed:
        rag_guarded(
            "add_case",
            lambda r: r.add_case(
                code=state["target_code"],
                test_code=state["generated_test"],
                passed=True,
                metadata={"function": state.get("target_function"), "coverage": result["coverage"]},
            ),
            enabled=ENABLE_RAG,
            module_available=RAG_MODULE_AVAILABLE,
            retriever_cls=TestCaseRetriever,
            get_retriever=get_rag_retriever,
        )
        # C10（2026-10-05 系统审查 P1）：修复案例验证门入库。上一轮写盘的
        # 补丁（_patch_applier_node 暂存 last_applied_repair）经本轮执行验证
        # 通过（test_passed=True）才进入修复案例库——失败/回滚补丁不再污染
        # 后续任务的 RAG 检索参考。入库后经下方 update dict 置 None 消费
        # （防重复入库）。
        _pending_repair = state.get("last_applied_repair")
        if _pending_repair and _pending_repair.get("patch"):
            rag_guarded(
                "add_repair",
                lambda r: r.add_repair(
                    original_code=_pending_repair.get("original_code", ""),
                    patch=_pending_repair.get("patch", ""),
                    error_category=_pending_repair.get("error_category", "unknown"),
                ),
                enabled=ENABLE_RAG,
                module_available=RAG_MODULE_AVAILABLE,
                retriever_cls=TestCaseRetriever,
                get_retriever=get_rag_retriever,
            )
            _consume_pending_repair = True

    # P0 运行时探针采集层（RUNTIME_PROBE_ENABLE=true 时启用，默认关）：
    # 测试失败时，经 sys.settrace 一次性探针捕获"失败时刻局部变量快照"，
    # 写入 state["runtime_probe_snapshot"] 供下一轮 _debugger_node 注入 prompt。
    # 纯观测层：探针失败 / 测试全过时 state["runtime_probe_snapshot"]=None，
    # 历史口径不变。默认关闭时零行为变化。
    runtime_probe_snapshot: dict[str, Any] | None = None
    if not _passed and _runtime_probe_enabled():
        from src.agents.runtime_probe import capture_failure_snapshot

        _probe_backend = _runtime_probe_backend(agent, result)
        runtime_probe_snapshot = capture_failure_snapshot(
            test_code=state.get("generated_test") or "",
            target_module=state.get("module_name"),
            target_file=state.get("target_file"),
            backend=_probe_backend,
        )
        _trace_node(
            "runtime_probe",
            output_summary={
                "captured": runtime_probe_snapshot is not None,
                "frames": len((runtime_probe_snapshot or {}).get("frames", [])),
                "backend": _probe_backend,
            },
            # N01：隔离级别不匹配时是"按契约拒绝"，与探针自身降级分开标注
            decision=(
                "probe_captured"
                if runtime_probe_snapshot
                else ("probe_blocked" if _probe_backend not in ("local", "venv") else "probe_degraded")
            ),
            iteration=state.get("iteration", 0),
        )

    # 3.2 执行反馈轨迹：追加本次执行记录（纯观测层，默认常开）。
    # 上一轮覆盖率从入参轨迹前缀直接读（_record_execution_trace 内部再
    # 复制一份轨迹，故此处不预先计算 prev_coverage，避免重复扫描）
    new_trace = _record_execution_trace(
        state,
        passed=_passed,
        coverage=result["coverage"],
        elapsed_seconds=round(time.time() - t0, 2),
    )
    # 3.2 改进：基于历史轨迹（含本次）的动态迭代策略建议（观测层，不参与路由）
    prev_coverage = None
    if state.get("execution_trace"):
        prev_coverage = state["execution_trace"][-1].get("coverage")
    coverage_delta = round(result["coverage"] - prev_coverage, 2) if prev_coverage is not None else None
    strategy_suggestion = _suggest_iteration_strategy(new_trace, coverage_delta)

    # 1.4 事件总线接线：TestsExecuted（纯观测，不改路由）
    publish_tests_executed(state, passed=_passed, coverage=result["coverage"])

    update: dict[str, Any] = {
        "test_passed": _passed,
        "test_output": result["output"],
        "coverage_report": result["coverage"],
        "failed_cases": result["failed_cases"],
        "execution_trace": new_trace,
        "iteration_strategy_suggestion": strategy_suggestion,
    }
    # C10：验证门入库消费——入库完成的暂存补丁置 None（经 update dict
    # 合法通道回写，防下一轮重复入库）
    if _consume_pending_repair:
        update["last_applied_repair"] = None
    _apply_executor_rogue_monitor(update)
    _apply_executor_flaky_gate(update, state, agent, result, _passed, _attempt_summary, _fail_then_pass)
    # P0 运行时探针快照（RUNTIME_PROBE_ENABLE=true 时写入；默认关时不写，
    # 历史口径不变。None 表示探针未触发 / 降级；非 None 时含 frames 列表）
    if _runtime_probe_enabled():
        update["runtime_probe_snapshot"] = runtime_probe_snapshot
    # M5（2026-09-29 审查 P0）：测试重生成假通过标记。
    # 判定：本节点由"再生成"路由进入（regeneration_count > 0，即测试在
    # 当前轮或前轮被重新生成过）且本轮 test_passed=True。此时源码并未被
    # 修复（regenerate 路由不经过 debugger/patch_applier），测试重生成后
    # 通过**不等于缺陷被处理**——这是经典 oracle-from-implementation 假
    # 成功通道。写入 test_regenerated_pass_unverified 标记（纯观测，不改
    # 路由），供评估层把该类任务归入"未验证假通过"而非"修复成功"。
    if _passed and int(state.get("regeneration_count", 0)) > 0:
        update["test_regenerated_pass_unverified"] = True
    _apply_executor_detection_first(update, state, _passed)
    _apply_executor_ac2_gates(update, state, _passed)
    _apply_executor_branch_coverage(update, state)
    _apply_executor_patch_rollback(update, state, _passed)
    # P0-4（2026-10-10）：规约 oracle 行级判定升级——本轮 "injected"（_generator_node
    # 写入）在本轮测试执行后升级为 injected_and_passed / injected_and_failed，
    # 使"注入 oracle 造成的红"与"LLM 断言造成的红"在结果行里可分离（T3 审查
    # 指出的逐位同构缺口）。纯观测：不改路由；未注入轮 / 不可判定轮不写键
    # （返回 None，保留原判定，不臆测）。
    _oracle_verdict_upgraded = _spec_oracle_verdict_after_run(state, dict(result, passed=_passed))
    if _oracle_verdict_upgraded is not None:
        update["spec_oracle_verdict"] = _oracle_verdict_upgraded
    return update


# ─── BaseAgent 子类惰性单例复用（2026-09-28 性能优化）────────────────────────
# _debugger_node / _diagnosis_node 每轮迭代都 new 一个 DebuggerAgent()，而
# BaseAgent.__init__ 的实质工作是"查 llm_client 的客户端缓存（或新建
# ChatOpenAI 并锁内插缓存）"——循环修复（MAX_ITERATIONS 轮 × 多任务）下该
# 构造/查表开销线性累积。实例缓存的并发等价性：
# - BaseAgent 实例唯一状态 = self.llm（共享缓存客户端，线程安全）+
#   self.system_prompt（不可变构造参数，实例间同值）；
# - 实例方法不写实例字段（execute/debug 均走模块函数 + 共享缓存），
#   按类键单例与按次新建在任意并发模式下逐字节等价。
# 键 = 类名（str，稳定可哈希）；容量 16 + FIFO 淘汰（与 llm_client 客户端
# 缓存同口径）。开关：AITESTER_AGENT_REUSE=0 关闭（默认启用，行为不变）。


def _cross_file_analyzer_node(state: AITesterState) -> dict[str, Any]:
    """3.5 跨文件修复：分析被测代码的跨文件依赖关系（CROSS_FILE_ENABLE=true 时启用）。

    流程：
        1. 从 state["target_code"] 提取源码；
        2. 调用 analyze_cross_file_deps 做 AST 依赖分析（entry → target 的 import 关系）；
        3. 把依赖边列表写入 state["cross_file_deps"]（供后续节点 / 报告使用）；
        4. 若依赖图为空（单文件项目），写入空列表并降级为单文件模式
           （cross_file_plan 置 None，后续 patch_applier 走单文件路径）。

    设计约束：
        - 默认关闭（CROSS_FILE_ENABLE=false），启用时需显式设置环境变量；
        - 单文件项目自动降级（依赖边为空时 cross_file_plan 保持 None）；
        - 节点不直接生成补丁，仅做"协调器"角色（依赖分析 + 路由决策），
          补丁生成仍由现有 _debugger_node 完成（提议者角色），保持 LLM 调用路径不变。

    Args:
        state: 当前工作流状态（含 target_code / target_file / module_name 等字段）。

    Returns:
        更新后的状态字典，包含 cross_file_deps（依赖边列表，可为空）。
    """
    t0 = time.time()
    entry_module = state.get("module_name") or os.path.basename(state.get("target_file", ""))
    target_code = state.get("target_code", "")

    # 3.5 二期：多入口依赖分析（保守口径：一级展开，不递归——防依赖图爆炸）。
    # 当前 state 中仅 target_code 可用（单入口视角），entry_modules 传 [entry]；
    # 未来扩展多入口时，把其他模块名追加进 entry_modules 即可，节点无需改动。
    source_files: dict[str, str] = {}
    entry_modules: list[str] = []
    if entry_module:
        source_files[entry_module] = target_code
        entry_modules.append(entry_module)
    # 若有其他模块内容（未来扩展），在此追加到 source_files 与 entry_modules

    deps = analyze_multi_entry_deps(entry_modules, source_files)
    # O-3（2026-10-18）可观测性修复：此前 trace 的 dep_edges/decision 只看
    # **AST 推导边**（deps），而 benchmark 层预置依赖边（state["cross_file_deps"]，
    # 由 _write_cross_file_state 按 dep_chain 注入）在下游会被保留——于是
    # "预置边非空 + AST 边为空"的真实跨文件任务在 trace 里被标成
    # `single_file_fallback`/`dep_edges=0`（O-3 实跑实测），审计侧误判
    # "analyzer 没找到依赖"。现把两条来源分列并让 decision 反映**有效依赖边**
    # （AST 优先；AST 空时预置边即有效）。纯观测口径，路由/落态零变化。
    _preset_deps = state.get("cross_file_deps") or []
    _effective_dep_count = len(deps) if deps else len(_preset_deps)
    _trace_node(
        "cross_file_analyzer",
        output_summary={
            "entry_module": entry_module,
            "ast_dep_edges": len(deps),
            "preset_dep_edges": len(_preset_deps),
            "dep_edges": _effective_dep_count,
        },
        decision="deps_found" if _effective_dep_count else "single_file_fallback",
        duration_ms=(time.time() - t0) * 1000,
        iteration=state.get("iteration", 0),
    )

    # 显式 asdict（而非 d.__dict__）：dataclass 未来加内部字段会无声改变
    # state["cross_file_deps"] 的 schema，下游节点按固定 key 取值的契约
    # （_patch_applier_node :985）保持稳定——2026-09-26 全面审查修复
    #
    # 2026-10 P3（A/B 阴性结果驱动）：跨文件任务预置依赖边（_write_cross_file_state
    # 按 dep_chain 写入 state["cross_file_deps"]）时，本节点只对被调方
    # target_code（如 module_c）做 AST 分析——module_c 是被调方，其 import
    # 方向为反向（不 import 调用方 module_a/b）→ AST 分析 0 条边 → 覆盖预置边。
    # 修复：AST 分析结果为空、且预置边非空时，保留预置边（双向依赖图：被调方
    # 视角缺失的"调用方 → 被调方"反向边由 dep_chain 预置补全）。预置边为空时
    # 维持历史 AST 单视角口径（零行为变化）。
    if deps:
        # AST 分析命中 → 用 AST 结果（历史口径）
        # O11（2026-09-29 审查 P1）：显式标记边来源为 AST 推导
        # （区别于 _write_cross_file_state 的 benchmark 层预置边）。
        # "source": "ast_derived" 使实验分析能区分两类边，
        # 跨文件 A/B 结论可外推的前提是两类边均非空。
        _ast_edges = [asdict(d) for d in deps]
        for _edge in _ast_edges:
            _edge["source"] = "ast_derived"
        update: dict[str, Any] = {"cross_file_deps": _ast_edges}
    elif _preset_deps:
        # AST 为空 + 预置边非空 → 保留预置边（双向依赖图反向补全）
        update = {"cross_file_deps": _preset_deps}
        logger.info(
            "3.5 跨文件修复：AST 单视角 0 条边，保留预置依赖边 %d 条"
            "（双向依赖图：被调方视角缺失的调用方反向边由 dep_chain 补全）",
            len(_preset_deps),
        )
    else:
        # 无 AST 边 + 无预置边 → 历史单文件降级口径
        update = {"cross_file_deps": []}

    # ── P0 1.1 分层代码压缩（跨文件调用链上下文）────────────────────────
    # 跨文件任务时，为每个依赖边的 target_module 构建"目标函数 → 被调函数
    # （CODE_FOCUS_DEPTH 层）"的调用链上下文（纯静态、不消耗 LLM token），
    # 写入 state["cross_file_contexts"]：{module_name: focused_code}。
    # 后续 _debugger_node 生成跨文件补丁时把相关模块的聚焦上下文一并注入
    # prompt，替代"整模块全文 → 截断猜"的旧口径。
    if deps:
        from src.tools.code_analyzer import extract_function_context

        focused_contexts: dict[str, str] = {}
        for dep in deps:
            module_src = source_files.get(dep.target_module, "")
            if not module_src:
                continue
            focused = extract_function_context(module_src, dep.symbol, depth=CODE_FOCUS_DEPTH)
            if focused:
                focused_contexts.setdefault(dep.target_module, focused)
        if focused_contexts:
            update["cross_file_contexts"] = focused_contexts
            # L4 逻辑修复（2026-09-29 审查）：source_files 一期仅含 entry
            # 模块（本节点上方 source_files / entry_modules 构建块），被依赖
            # 模块（dep.target_module）源码未载入 → 上面的循环对非 entry 模块
            # 恒取 "" 跳过。日志须如实反映"仅 entry 模块生效"，避免高估已构建
            # 的模块数。AA 轮（2026-10-19）把该能力边界钉成反面锁定
            # （tests/test_cross_file_plan_wiring.py::TestStepBNotWired）；
            # 扩展跨文件源码载入后此处可改回全模块口径，届时该锁必红，
            # 需与 docs/design/cross_file_plan_wiring_prereg.md §3.5 同步改写。
            logger.info(
                "P0 1.1 跨文件调用链上下文：构建 %d 个模块的聚焦上下文"
                "（depth=%d，当前仅 entry 模块 %s 生效——被依赖模块源码"
                "二期扩展后自动纳入）",
                len(focused_contexts),
                CODE_FOCUS_DEPTH,
                state.get("module_name") or os.path.basename(state.get("target_file") or ""),
            )

    # 跨文件计划落态：默认写 None 占位。D3b Step A（2026-10-18）起，
    # CROSS_FILE_PLAN_BUILD_ENABLE=true 时由 _debugger_node（LLM 分支，具备
    # debugger 实例与 test_output）经 build_cross_file_repair_plan_cached 构建
    # 真实计划并覆盖本占位；消费由 CROSS_FILE_PLAN_CONSUME_ENABLE 门控
    # （_resolve_target_module）。设计依据 docs/design/cross_file_plan_wiring_prereg.md。
    if not deps and not _preset_deps:
        logger.info("3.5 跨文件修复：依赖图为空（单文件项目），降级为单文件模式")
    elif deps:
        logger.info("3.5 跨文件修复：发现 %d 条跨文件依赖边", len(deps))
    # 预置边分支的日志已在上方 elif _preset_deps 分支给出（不再重复打印误导性"降级"）
    update["cross_file_plan"] = None  # 占位，待二期实现完整计划构建
    return update


def _run_patch_resample(
    state: AITesterState,
    original_code: str,
    new_code: str,
    applied: bool,
) -> tuple[str, bool, dict[str, Any] | None]:
    """2.2 补丁后处理重采样（自 `_patch_applier_node` 提取，行为等价）。

    补丁应用失败时把"负面反馈"回传 Debugger 重新生成一次（严格 prompt +
    1.3 降级链档位收紧温度），最多 ``PATCH_RESAMPLE_MAX`` 次；仍失败则写
    ``_2_2_patch_syntax_invalid`` 临时键（refine_failure_category 消费）并
    保留原代码。未启用时（默认）零行为变化、不产生额外 LLM 调用。

    Args:
        state: 当前状态（读取 patch / 写重采样临时键）。
        original_code: 应用前原文。
        new_code: 应用后候选代码。
        applied: 补丁是否已成功应用。

    Returns:
        ``(new_code, applied, resample_stats)``：resample_stats 为 None 表示
        未进入重采样分支。
    """
    resample_stats: dict[str, Any] | None = None
    if not applied and _patch_resample_enabled():
        from src.agents.debugger import DebuggerAgent
        from src.tools.patch_applier import apply_patch_with_resample

        resampler = DebuggerAgent()

        def _on_resample(query: str, original_code: str, patch: str, ast_error: str) -> str | None:
            """2.2 重采样回调：严格 prompt + 1.3 降级链档位温度重新生成补丁。

            注入"被拒补丁 + AST 错误 + 原始代码片段 + 档位温度"，让 LLM 在
            更高约束下修订。返回的修订补丁已通过静态验证（AST 合法 + 不破坏
            命名契约 + 能成功应用）才返回，否则 None（保守保留原代码）。
            """
            if not patch and not ast_error:
                return None
            # 提取被拒补丁里的 python 代码块（LLM 输出可能带 markdown 包裹）
            from src.utils.helpers import extract_code_block

            _rejected = extract_code_block(patch or "", language="python") or (patch or "")[:1000]
            # 注入 1.3 降级链档位（被符号守卫拒绝后自动降级到的档位）
            from src.tools.patch_applier import _current_context_tier

            _tier_name, _idx, _temp = _current_context_tier()
            strict_prompt = (
                "【补丁语法校验失败反馈】上一轮补丁应用后 AST 解析失败或未能定位到目标函数，"
                f"具体错误：\n{ast_error[:500]}\n\n"
                "请基于同样的错误上下文，重新生成一个语法合法的补丁。"
                "必须保留原文件中所有模块级符号（函数名/类名/__all__/注册装饰器/插件入口点），"
                "只允许修改函数/方法体内部逻辑。用 ```python ... ``` 包裹输出。"
                f"\n\n【当前档位：{_tier_name}（温度 {_temp}）】"
                f"\n【被拒补丁片段】\n```\n{_rejected}\n```\n"
                f"\n【原始代码片段】\n```\n{(original_code or '')[:2000]}\n```"
            )
            try:
                _result = resampler._call_llm_with_cache(strict_prompt, temperature=_patch_resample_temperature())
                _extracted = extract_code_block(_result or "", language="python")
                if not _extracted:
                    return None
                # 二次静态验证：必须能 ast.parse 且不破坏命名契约
                from src.tools.patch_applier import safe_apply_patch

                _try_code, _try_ok = safe_apply_patch(original_code, _extracted)
                if not _try_ok:
                    return None
                # J-3 注释纠错（2026-10-17）：原注释称"safe_apply_patch 已做过命名契约、
                # 此处 _ck 是纯冗余 AST"——**不成立**：safe_apply_patch 只做语法校验 +
                # 危险 API 差集，命名契约由下面这次 check_naming_contract 把关（失败即
                # 保守返回 None）。照原注释删除 _ck 会让重采样路径静默失去契约保护。
                # （历史上确有一个包装器 safe_apply_patch_contract = safe_apply_patch +
                # 本段两行，全仓零调用零测试，J-3 已删；契约开关 PATCH_CONTRACT_CHECK
                # 在 check_naming_contract 内部生效。）
                from src.tools.patch_applier import check_naming_contract as _ck

                _contract_ok, _missing = _ck(original_code, _try_code)
                if not _contract_ok:
                    return None
                return _extracted
            except Exception:
                logger.debug("2.2 重采样 LLM 调用失败（保守返回 None，不阻断主流程）", exc_info=True)
                return None

        new_code, applied, resample_stats = apply_patch_with_resample(
            original_code,
            state.get("patch") or "",
            resample_fn=_on_resample,
            max_resamples=_patch_resample_max(),
        )
        if resample_stats.get("resampled"):
            logger.info(
                "2.2 补丁后处理重采样 %d 次，成功=%s",
                resample_stats.get("resample_count", 0),
                resample_stats.get("success", False),
            )
            # 重采样成功后重新走契约检查与写盘路径
            if applied and new_code != original_code:
                from src.tools.patch_applier import check_naming_contract as _ck

                _ok2, _missing2 = _ck(original_code, new_code)
                if not _ok2:
                    logger.warning("2.2 重采样后命名契约仍被破坏（%s），拒绝写盘", _missing2[:5])
                    applied = False
                    new_code = original_code
                    # 2026-10-19 工程质量轮：历史实现的 contract_missing 局部赋值
                    # 无任何读侧（契约缺失符号经 _check_patch_safety 写 state
                    # 临时键），拆分后由 ruff F841 暴露并删除，行为不变。
            if resample_stats.get("success") is False and resample_stats.get("resampled"):
                # 2.2 标记：重采样耗尽仍失败 → patch_syntax_invalid
                # （refine_failure_category 在任务收尾时消费）
                cast("dict[str, Any]", state)["_2_2_patch_syntax_invalid"] = True
    return new_code, applied, resample_stats


def _check_patch_safety(
    state: AITesterState,
    original_code: str,
    new_code: str,
    applied: bool,
) -> tuple[bool, str]:
    """命名契约 + 危险 API 双保险（自 `_patch_applier_node` 提取，行为等价）。

    补丁应用后、写盘前执行两道独立安全检查：
    ① ``PATCH_CONTRACT_CHECK``（默认 true）：对比修改前后的模块级符号集合，
       缺失任何原符号即拒绝应用，并（按 ``CONTEXT_TIER_DOWNGRADE_ENABLE``）
       推进上下文档位、写回契约反馈临时键；
    ② ``PATCH_DANGEROUS_API_GUARD``（默认 true）：正则 + AST 差集双通道拦截
       新引入的危险调用，命中即拒绝（保守不引入半应用状态）。

    Args:
        state: 当前状态（写 ``_1_3_contract_missing`` /
            ``_1_3_contract_feedback`` 两个节点内临时键，由主节点末尾 pop）。
        original_code: 应用前原文。
        new_code: 应用后候选代码。
        applied: 补丁是否已成功应用。

    Returns:
        ``(applied, new_code)``：拒绝时 applied=False 且 new_code 回退原文；
        契约缺失符号经 state 临时键 ``_1_3_contract_missing`` 透传，BI 轮新增的
        预检可测量性经 ``_bi_safety_outcomes`` 临时键透传（键本身不入 TypedDict，
        通道键为 ``safety_check_status`` / ``safety_check_outcomes``）。
    """
    contract_missing: list[str] = []
    _dangerous_added: list[str] | None = None
    _safety_outcomes: list[dict[str, Any]] = []
    if applied and new_code != original_code:
        from src.tools.patch_applier import check_naming_contract, dangerous_api_added

        ok, missing = check_naming_contract(original_code, new_code, outcome_sink=_safety_outcomes)
        # P0-4 性能（2026-10-01）：预计算 AST 危险差集，供下方 S2 双保险复用
        # （同一 (original, new) 输入只算一次，避免重复 ast.parse×2）
        _dangerous_added = dangerous_api_added(original_code, new_code, outcome_sink=_safety_outcomes)
        if not ok:
            logger.warning("P0 1.3 命名契约检查失败，拒绝应用补丁：缺失符号 %s", missing)
            applied = False
            new_code = original_code
            contract_missing = list(missing)
            # 1.3 分层压缩降级链：守卫拒绝时推进上下文档位（进程内状态），
            # 并把 (档位名, 缺失符号) 经 state 透传给下一轮 _debugger_node。
            # 开关 CONTEXT_TIER_DOWNGRADE_ENABLE（默认 false，保持历史口径；
            # true 时降级链全链路生效）。
            if _context_tier_downgrade_enabled():
                from src.tools.patch_applier import _current_context_tier, advance_context_tier

                advance_context_tier()
                tier_name, _idx, _temp = _current_context_tier()
                # 临时键：本节点函数内先写入、末尾经 state.pop 取出合并进返回
                # dict（键本身不进入 LangGraph 通道——通道键为
                # contract_reject_feedback，见 1.3 降级链注释）。mypy 无法
                # 对 TypedDict 的临时动态键收窄，故对 state 做窄化 cast。
                _state = cast("dict[str, Any]", state)
                _state["_1_3_contract_feedback"] = {
                    "tier": tier_name,
                    "missing_symbols": contract_missing,
                }
            # mypy：同上，cast 收窄（临时键不入 TypedDict 声明）
            cast("dict[str, Any]", state)["_1_3_contract_missing"] = contract_missing
        if applied:
            # S2 安全双保险（2026-09-29 审查）：危险操作拦截走正则
            # （injection_guard.check_llm_patch_safety，默认开）+ AST 差集
            # （patch_applier.dangerous_api_added，默认开）双通道。
            # 正则 findings 或 AST 差集非空即拒绝（保守不引入半应用状态）。
            from src.agents.injection_guard import check_llm_patch_safety

            _regex_hits = check_llm_patch_safety(new_code)
            # P0-4 性能（2026-10-01）：复用上方已算的 dangerous_api_added 结果，
            # 避免对同一 (original_code, new_code) 重复做 AST 差集（两遍
            # ast.parse×2）
            _added = (
                _dangerous_added
                if _dangerous_added is not None
                else dangerous_api_added(original_code, new_code, outcome_sink=_safety_outcomes)
            )
            _hits = list(dict.fromkeys(_regex_hits + _added))  # 去重保序
            if _hits:
                logger.warning("S2 危险操作拦截：补丁被拒绝（%s）", "、".join(_hits))
                applied = False
                new_code = original_code
    if _safety_outcomes:
        # BI 轮（2026-10-22）：两道预检相互独立 ⇒ 最差者优先。status != ok 时
        # 空结果（missing=[] / 危险差集=[]）不构成"预检通过"的证据，点名披露。
        from src.utils.check_status import CHECK_OK, worst_check_status

        _safety_status = worst_check_status(str(o.get("status", "")) for o in _safety_outcomes)
        if _safety_status != CHECK_OK:
            logger.warning(
                "写盘前静态预检可测量性降级（整体 status=%s）：%s",
                _safety_status,
                ", ".join(f"{o['check']}={o['status']}:{o['reason'] or '-'}" for o in _safety_outcomes),
            )
        # 临时键：本节点函数内写入、由 _patch_applier_node 末尾 pop 并入通道键。
        cast("dict[str, Any]", state)["_bi_safety_outcomes"] = _safety_outcomes
    return applied, new_code


def _apply_patch_evidence_gate(
    state: AITesterState,
    original_code: str,
    new_code: str,
    written: bool,
    snapshot: dict[str, Any],
) -> tuple[bool, str, dict[str, Any]]:
    """源码补丁证据门（自 `_patch_applier_node` 提取，行为等价）。

    写盘成功后评估补丁证据等级；``patch_evidence_gate_enabled()`` 且等级
    不足（非 gold/sbfl）时恢复磁盘原文件并置 written=False（fail-closed）。
    恢复失败时如实降级为"写盘后标记"口径（C6：磁盘与状态必须一致声明）。
    证据等级本身始终记录（消融对照不受影响）。

    Args:
        state: 当前状态。
        original_code: 应用前原文。
        new_code: 应用后代码。
        written: 补丁是否已写盘成功。
        snapshot: 快照出参（阻断时 clear——无可回滚物）。

    Returns:
        ``(written, new_code, evidence_update)``。
    """
    _evidence_update: dict[str, Any] = {}
    if written:
        from src.tools.patch_evidence import (
            assess_patch_evidence,
            evidence_allows_write,
            patch_evidence_gate_enabled,
        )

        _ev_level = assess_patch_evidence(cast("dict[str, Any]", state), original_code, new_code)
        _evidence_update["patch_evidence_level"] = _ev_level
        if patch_evidence_gate_enabled() and not evidence_allows_write(_ev_level):
            _evidence_update["source_patched_unverified"] = True
            _disk_restored_ev = False
            try:
                _write_file_atomic(os.path.abspath(state.get("target_file", "")), original_code)
                _disk_restored_ev = True
            except Exception:
                logger.exception(
                    "证据门阻断恢复原文件失败：磁盘仍保留无证据补丁（target_file=%s）",
                    state.get("target_file"),
                )
            if _disk_restored_ev:
                written = False
                new_code = original_code
                snapshot.clear()  # 与"安全检查拒绝"同构：无可回滚物，快照键不写 channel
                logger.warning(
                    "P0 源码补丁证据门：本轮补丁证据等级=%s（不足 gold/sbfl），"
                    "已恢复原文件（拒绝写盘，patch_applied=False）",
                    _ev_level,
                )
            else:
                # 恢复失败时如实降级为"写盘后标记"口径（C6 教训：磁盘与
                # 状态必须一致声明——盘上有补丁就不能声称拒绝写盘）
                logger.warning(
                    "P0 源码补丁证据门：等级=%s 不足但原文件恢复失败，"
                    "降级为写盘后标记口径（source_patched_unverified）",
                    _ev_level,
                )
        else:
            _evidence_update["source_patched_unverified"] = False
    return written, new_code, _evidence_update


def _maybe_run_testless_validation(
    state: AITesterState,
    original_code: str,
    effective_code: str,
    written: bool,
) -> dict[str, Any]:
    """O6 testless 修复验证层（自 `_patch_applier_node` 提取，行为等价）。

    ``TESTLESS_VALIDATION_ENABLE=true`` 且补丁已写盘时，对
    (original_code, effective_code) 做四层静态验证（AST 符号守卫 / mypy /
    命名契约 / 导入冒烟）；结果作为纯观测信号写入返回 dict，不阻断主流程。
    未启用 / 未写盘 / 执行异常均返回空 dict（历史口径零变化）。

    Args:
        state: 当前状态（读取 module_name）。
        original_code: 应用前原文。
        effective_code: 实际生效代码。
        written: 补丁是否已写盘成功。

    Returns:
        含 ``testless_validation`` 键的 update 片段，或空 dict。
    """
    testless_validation_result: dict[str, Any] | None = None
    if written:
        from src.tools.testless_validation import run_testless_validation as _run_tlv
        from src.tools.testless_validation import testless_validation_enabled as _tlv_enabled

        if _tlv_enabled():
            try:
                testless_validation_result = _run_tlv(
                    original_code=original_code,
                    patched_code=effective_code,
                    target_module=state.get("module_name", ""),
                )
                if not testless_validation_result.get("passed", True):
                    logger.info(
                        "O6 testless 验证未通过（失败层: %s），标记为观测信号（不阻断主流程）",
                        testless_validation_result.get("failed_layers", []),
                    )
                elif testless_validation_result.get("validation_status", "ok") != "ok":
                    # BH（2026-10-21）：passed=True 但整体不可测量——必须显式
                    # 披露，否则下游把"没有一层报告缺陷"读成"四层都验证通过"。
                    logger.info(
                        "O6 testless 验证 passed=True 但可测量性降级（status=%s，降级层: %s）："
                        "不构成'验证通过'的证据（不阻断主流程）",
                        testless_validation_result.get("validation_status"),
                        testless_validation_result.get("degraded_layers", []),
                    )
            except Exception:
                logger.debug("O6 testless 验证执行异常（保守跳过，保持历史口径）", exc_info=True)
    if testless_validation_result is not None:
        return {"testless_validation": testless_validation_result}
    return {}


def _resolve_patch_application(state: AITesterState, original_code: str) -> tuple[str, bool, dict[str, Any]]:
    """补丁应用分支选择（自 `_patch_applier_node` 提取，行为等价）。

    三路互斥：① ``cross_file_deps`` 非空且 ``CROSS_FILE_ENABLE`` 开启时按
    依赖图拓扑序做多文件应用（失败降级单文件）；② 多候选开关开启时静态
    筛选 + 可选执行验证选最优候选；③ 否则走历史单补丁路径。任一环节无
    有效结果都保守回退原文，不引入劣化。

    Args:
        state: 当前状态（读取 cross_file_deps / patch / module_name 等）。
        original_code: 应用前原文。

    Returns:
        ``(new_code, applied, multi_candidate_update)``：多候选分支的额外
        状态更新（其它分支为空 dict）。
    """
    multi_candidate_update: dict[str, Any] = {}
    cross_file_deps = state.get("cross_file_deps") or []
    if cross_file_deps and cross_file_enabled():
        # 3.5 跨文件修复分支：按依赖图拓扑序对多个模块应用补丁
        from src.tools.cross_file import CrossFileDependency, apply_multi_file_patch, cross_file_fallback_single_file

        # 把 state 中序列化的依赖边还原为 CrossFileDependency 对象
        # （拓扑序补丁应用需要结构化边信息，被调用方先改、调用方后改）
        dep_objects = [
            CrossFileDependency(
                source_module=d.get("source_module", ""),
                target_module=d.get("target_module", ""),
                symbol=d.get("symbol", ""),
                call_line=int(d.get("call_line", 0)),
                context=d.get("context", ""),
            )
            for d in cross_file_deps
        ]
        # 从 state 收集所有模块的原始代码（当前仅 target_code 可用；
        # 二期扩展后从 source_files 字典读取）
        entry_module = state.get("module_name") or os.path.basename(state.get("target_file", ""))
        original_files = {entry_module: original_code}
        # 多文件补丁：entry_module 用 state["patch"]（当前单补丁路径生成），
        # 其他模块的补丁由 _debugger_node 后续生成（二期）
        patches: dict[str, str] = {}
        if state.get("patch"):
            patch_val = state["patch"]
            assert isinstance(patch_val, str)  # TypedDict 标 str | None，真值守卫后必为 str
            patches[entry_module] = patch_val
        # 尝试多文件应用（传依赖边 → 拓扑序）；失败时降级为单文件
        new_files, applied = apply_multi_file_patch(original_files, patches, entry_module, deps=dep_objects)
        new_code = new_files.get(entry_module, original_code)
        if not applied:
            # 多文件失败 → 降级单文件（保守口径，不引入劣化）
            logger.info("3.5 跨文件补丁应用失败，降级单文件模式")
            # 注意：cross_file_fallback_single_file 返回 (新文件映射, 成功)，
            # 需再取 entry_module 的代码字符串——此前误把整个映射当 new_code，
            # len(dict) 恒为 1，降级补丁永远卡在"过短"安全检查、永远写不进盘
            fallback_files, applied = cross_file_fallback_single_file(original_files, patches, entry_module)
            new_code = fallback_files.get(entry_module, original_code)
    elif multi_candidate_available():
        new_code, applied, multi_candidate_update = _select_multi_candidate_patch(
            state, original_code, iteration=state.get("iteration", 0)
        )
    else:
        new_code, applied = apply_patch_to_code(original_code=original_code, patch=state.get("patch") or "")
    return new_code, applied, multi_candidate_update


def _apply_snapshot_rollback(
    state: AITesterState,
    original_code: str,
    written: bool,
    effective_code: str,
    resample_update: dict[str, Any],
) -> tuple[str, bool]:
    """A-03 快照 / P2P 回归 / 失败自动回滚协议（自 `_patch_applier_node` 提取）。

    ``PATCH_SNAPSHOT_ROLLBACK_ENABLE=true`` 且已写盘时，对"应用补丁后的
    代码"跑独立测试套件 P2P 回归：断言级失败 → 状态与磁盘同步恢复原文
    （落盘失败如实记 rolled_back=False）；通过 → 保留补丁并标注 verified；
    无测试材料 / 坏测试 → 保守保留补丁。观测字段纯观测、不参与路由。

    Args:
        state: 当前状态。
        original_code: 应用前原文。
        written: 补丁是否已写盘成功。
        effective_code: 当前实际生效代码。
        resample_update: 本轮 update 片段（原地写入回滚观测键）。

    Returns:
        ``(effective_code, written)``（回滚后 written=False）。
    """
    if snapshot_rollback_enabled() and written:
        from src.tools.patch_rollback import PatchRollbackProtocol

        _pr_result = PatchRollbackProtocol().run(
            original_code=original_code,
            patch=state.get("patch") or "",
            test_code=state.get("generated_test") or "",
            module_name=state.get("module_name") or "module_under_test",
        )
        _verdict = _pr_result["verdict"]
        _rolled_back = bool(_pr_result["rolled_back"])
        if _rolled_back and _verdict == "regression_failed":
            # 自动回滚：target_code 恢复快照原文（written=False，patch_applied
            # 记 False——与"安全检查失败保持原代码"同口径，避免 Executor
            # 测回滚前代码、Debugger 分析回滚后代码的"幻象迭代"）
            # C6（2026-10-05 系统审查 P0）：同时恢复**磁盘**——此前仅改
            # state（effective_code/original_code）不写回 target_file，下一轮
            # executor 读磁盘测到的仍是"已回滚"的坏补丁代码，状态与存储分叉。
            effective_code = original_code
            written = False
            _disk_restored = False
            try:
                _write_file_atomic(os.path.abspath(state.get("target_file", "")), original_code)
                _disk_restored = True
            except Exception:
                logger.exception(
                    "A-03 回滚落盘失败：磁盘仍保留坏补丁（target_file=%s）",
                    state.get("target_file"),
                )
            # 磁盘未恢复时如实报告 rolled_back=False（避免下游把
            # "仅状态回滚"当作已恢复证据消费）
            _rolled_back = _disk_restored
            logger.warning(
                "A-03 P2P 回归失败，补丁已自动回滚（verdict=%s, snapshot=%s, disk_restored=%s）",
                _verdict,
                _pr_result["snapshot_id"],
                _disk_restored,
            )
        resample_update["patch_rollback_verdict"] = _verdict
        resample_update["patch_rolled_back"] = _rolled_back
    else:
        resample_update["patch_rollback_verdict"] = "not_enabled"
        resample_update["patch_rolled_back"] = False
    return effective_code, written


def _patch_applier_node(state: AITesterState) -> dict[str, Any]:
    """
    补丁应用节点：将 Debugger 生成的补丁应用到被测代码，并写回文件。
    应用后更新 iteration 计数器，供下次循环使用。

    2.2 补丁后处理重采样（PATCH_RESAMPLE_ENABLE=true，默认关）：应用失败
    （定位不到目标函数 / AST 解析不通过）时，把"负面反馈"回传 Debugger
    重新生成一次（严格 prompt + 1.3 降级链档位收紧温度），最多
    PATCH_RESAMPLE_MAX（默认 2）次；仍失败则把该轮标记为
    patch_syntax_invalid（refine_failure_category 消费）并保留原代码。

    1.3 分层压缩降级链（CONTEXT_TIER_DOWNGRADE_ENABLE=true，默认关）：
    符号守卫（check_naming_contract）拒绝补丁时，调 advance_context_tier()
    推进上下文档位，并把 (档位, 缺失符号) 作为 contract_reject_feedback
    写入 state——下一轮 _debugger_node 读到该反馈后按"更高约束"的
    上下文（补丁配方保留 / 签名+import 极简）+ 更低温度重新生成。
    未启用时（默认）行为与历史完全一致（仅拒绝本轮、不动档位）。

    状态/磁盘一致性：只有当补丁真正写入磁盘成功时，才把 target_code 更新为
    新代码并记录 patch_applied=True；任何一道安全检查（空/过短/无函数定义/
    路径不合法）拒绝写入时，target_code 保持原代码、patch_applied 记 False，
    避免下游 Executor 测旧文件、Debugger 却分析新代码的"幻象迭代"。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典，包含更新后的 target_code 和修复历史。
    """
    original_code = state["target_code"]

    # 后处理层需要判断是否跨文件/多候选（分支选择内部自行读取同一键）
    cross_file_deps = state.get("cross_file_deps") or []
    new_code, applied, multi_candidate_update = _resolve_patch_application(state, original_code)

    # ── 1.1 LLM 输出后处理层（P1 空壳检测 + P2/P3 卫生化，默认观测口径）──
    # P2 导入回填 / P3 契约别名回填默认关（环境变量控制，见
    # patch_postprocess.postprocess_enabled_flags）；P1 空壳检测默认启用，
    # 仅产出"empty_patch"标签观测（EMPTY_LLM_PATCH 场景从不可观测变为
    # 可识别标签，供 refine_failure_category / 实验分析消费），不改代码。
    # P2/P3 启用时：卫生化结果替换本轮 patch 后重新应用（仅单文件分支；
    # 多候选/跨文件分支的候选池各有独立静态筛选，不重复卫生化）。
    postprocess_labels: list[str] = []
    postprocess_update: dict[str, Any] = {}
    if (not cross_file_deps or not cross_file_enabled()) and not multi_candidate_available():
        try:
            from src.tools.patch_postprocess import postprocess_enabled_flags, sanitize_patch

            _pp_flags = postprocess_enabled_flags()
            _sanitized, _pp_labels = sanitize_patch(original_code, state.get("patch"))
            postprocess_labels = list(_pp_labels)
            if (_pp_flags["import_repair"] or _pp_flags["contract_alias"]) and (
                "imports_repaired" in _pp_labels or "contract_aliases_restored" in _pp_labels
            ):
                # P2/P3 生效：用卫生化后的补丁重新应用单文件路径
                new_code, applied = apply_patch_to_code(original_code=original_code, patch=_sanitized)
            postprocess_update["postprocess_labels"] = postprocess_labels
        except Exception:
            logger.debug("1.1 后处理层执行异常（保守跳过，保持历史口径）", exc_info=True)

    applied, new_code = _check_patch_safety(state, original_code, new_code, applied)

    new_code, applied, resample_stats = _run_patch_resample(state, original_code, new_code, applied)

    # 默认视为"未真正写盘"，任何安全检查失败都保持该值。
    # O35（P1）：快照经出参取回（见 _safe_write_patch 的 snapshot_out 注释），
    # 再放进本函数**返回的 update dict**——只有经 update dict 才会被 LangGraph
    # 写回 channel，_rollback_last_patch（下一轮 executor）才读得到快照。
    _snapshot: dict[str, Any] = {}
    written = _safe_write_patch(original_code, new_code, applied, state, snapshot_out=_snapshot)

    written, new_code, _evidence_update = _apply_patch_evidence_gate(state, original_code, new_code, written, _snapshot)

    # 状态/磁盘一致性：仅写盘成功才更新 target_code，否则保留原代码
    effective_code = new_code if written else original_code

    # 0.8 一致性口径：节点函数保持"纯函数更新字典"（--parallel 线程下
    # LangGraph 共享 TypedDict 不允许原地写）——此前 history.append 直接
    # 改写 state["repair_history"] 原列表（其他节点/路由对同一 state 的读取
    # 会看到被改写的中间值）；现改为拷贝后追加、经 update dict 写回
    history = list(state.get("repair_history") or [])
    history.append(
        {
            "iteration": state.get("iteration", 0) + 1,
            "diagnosis": state.get("diagnosis", ""),
            "error_category": state.get("error_category", "unknown"),
            "patch_applied": written,
        }
    )
    # 限制 repair_history 大小，避免无限增长占用内存（最多保留 _MAX_REPAIR_HISTORY 条）
    if len(history) > _MAX_REPAIR_HISTORY:
        history = history[-_MAX_REPAIR_HISTORY:]
    _trace_node(
        "patch_applier",
        output_summary={"patch_applied": written, "new_code_len": len(effective_code)},
        decision="written" if written else "rejected",
        iteration=state.get("iteration", 0),
    )
    # 1.3 改进：把本轮契约缺失符号（可能来自 2.2 重采样路径）写回 state，
    # 供 refine_failure_category / 实验分析消费（"5/7 任务破坏 sqlfluff
    # 插件命名契约"场景的直接可观测信号）
    contract_update: dict[str, Any] = {}
    # mypy：_1_3_contract_missing 为本节点函数内写入的临时键（不进入
    # AITesterState TypedDict 声明——通道键为 contract_missing_symbols，
    # 见上方 1.3 注释），对 state 做窄化 cast 消除 typeddict-unknown-key
    _state_pop = cast("dict[str, Any]", state)
    _missing_now = _state_pop.pop("_1_3_contract_missing", None) or []
    if _missing_now:
        contract_update["contract_missing_symbols"] = list(_missing_now)
    # 1.3 降级链档位反馈：透传给 _debugger_node（下一轮 debug 按档位收紧上下文）
    feedback_update: dict[str, Any] = {}
    _feedback_now = _state_pop.pop("_1_3_contract_feedback", None)
    if _feedback_now:
        feedback_update["contract_reject_feedback"] = _feedback_now
    # BI 轮（2026-10-22）：写盘前静态预检的可测量性。两道预检相互独立 ⇒ 最差者
    # 优先；``status != "ok"`` 时 contract_missing_symbols / 危险差集为空**不是**
    # "预检通过"的证据（未启用本轮检查时两键保持 None = 本轮未执行）。
    safety_update: dict[str, Any] = {}
    _safety_now = _state_pop.pop("_bi_safety_outcomes", None)
    if _safety_now:
        from src.utils.check_status import status_for_check, worst_check_status

        safety_update["safety_check_outcomes"] = list(_safety_now)
        safety_update["safety_check_status"] = worst_check_status(
            str(outcome.get("status", "")) for outcome in _safety_now
        )
        # BL 轮（2026-10-22）：把命名契约**这一腿**的可测量性单独落通道。上面
        # 的 worst-of 聚合会把"危险 API 腿读不懂"记成契约也可疑；反之契约腿
        # error 也可能被危险腿的 ok 拉平。恒写（该腿没记录 ⇒ None），不复用
        # BJ 轮点名的"非空才写键"反例。
        safety_update["contract_status"] = status_for_check(_safety_now, "naming_contract")
    # 2.2 重采样统计 + patch_syntax_invalid 标记（refine 消费）
    resample_update: dict[str, Any] = {}
    if resample_stats is not None:
        resample_stats_out = dict(resample_stats)
        from src.tools.patch_applier import _current_context_tier as _tier_fn

        _tier_name_now, _idx_now, _temp_now = _tier_fn()
        resample_stats_out["tiered_context"] = _tier_name_now
        resample_update["patch_resample_stats"] = resample_stats_out
    _syntax_invalid_flag = _state_pop.pop("_2_2_patch_syntax_invalid", False)
    if _syntax_invalid_flag:
        # patch_syntax_invalid 标记写入 error_category（refine_failure_category
        # 会在任务收尾时把 "patch_syntax_invalid" 归一到 PATCH_SYNTAX_INVALID）
        resample_update["error_category"] = "patch_syntax_invalid"
        # L1 逻辑修复（2026-09-29 审查）：同时补写 TypedDict 通道键
        # patch_syntax_invalid_flag（state.py:242 声明，refine_final_error_category
        # 经 final_state.get("patch_syntax_invalid_flag") 消费）——历史实现只写
        # error_category 字符串值，flag 通道恒 False（死通道），5.2 失败细化
        # 仅靠字符串路径兜底可达，与 TypedDict 契约脱节。双通道一致。
        resample_update["patch_syntax_invalid_flag"] = True
    effective_code, written = _apply_snapshot_rollback(state, original_code, written, effective_code, resample_update)
    # 1.4 事件总线接线：PatchApplied（含 1.1 后处理标签，纯观测）
    # P0（2026-10-05 独立审查）：证据门判定已**前移**至写盘点之后
    # （_safe_write_patch 返回处）——阻断语义（等级不足恢复原文件、
    # written=False）必须在 A-03 快照回滚 / repair_history / 事件总线
    # 构造之前生效，否则下游基于"已写盘"的假象运行。此处仅剩
    # publish_patch_applied 消费阻断后的 written。
    publish_patch_applied(state, applied=written, new_code=effective_code)
    _testless_update = _maybe_run_testless_validation(state, original_code, effective_code, written)
    # C10（2026-10-05 系统审查 P1）：验证门修复案例暂存——写盘成功的补丁
    # 三元组（含写盘前原文）经 state["last_applied_repair"] 交给下一轮
    # executor：验证通过才 add_repair 入库，失败/回滚（written=False）置
    # None 丢弃。多候选胜出时补丁文本取 stats.applied_patch（胜出候选，
    # 而非 debugger 原始单补丁）。
    _repair_patch = state.get("patch") or ""
    _mc_stats_for_repair = multi_candidate_update.get("multi_candidate_stats") or {}
    if isinstance(_mc_stats_for_repair.get("applied_patch"), str) and _mc_stats_for_repair["applied_patch"]:
        _repair_patch = _mc_stats_for_repair["applied_patch"]
    _repair_stash_update: dict[str, Any] = (
        {
            "last_applied_repair": {
                "original_code": original_code,
                "patch": _repair_patch,
                "error_category": state.get("error_category") or "unknown",
            }
        }
        if written
        else {"last_applied_repair": None}
    )
    return {
        "target_code": effective_code,
        "repair_history": history,
        "iteration": state.get("iteration", 0) + 1,
        **multi_candidate_update,
        **contract_update,
        **safety_update,
        **feedback_update,
        **resample_update,
        **postprocess_update,
        **_testless_update,
        # P0（2026-09-30 独立审查 N9/R33）：源码补丁证据门（证据等级 +
        # 未验证标记，纯观测；opt-out 时 patch_evidence_level 仍记录）
        **_evidence_update,
        # O35（P1）M6 快照经 update dict 落 channel（仅写盘成功时写；
        # 写盘被拒时不写该键，保留上一轮尚待 executor 消费的快照，
        # 避免把"可回滚状态"提前清空）。
        **(
            {"_last_patch_snapshot": _snapshot["path"], "_last_patch_iteration": _snapshot["iteration"]}
            if "path" in _snapshot
            else {}
        ),
        # C10：验证门修复案例暂存（见上方注释）
        **_repair_stash_update,
    }


def _validate_planner_output(test_plan: dict[str, Any]) -> bool:
    """
    验证 Planner 输出是否符合预期结构。

    检查必需字段：function_name 和 logic_analysis。

    Args:
        test_plan: PlannerAgent 输出的测试计划字典。

    Returns:
        True 表示结构完整，False 表示需要降级使用默认计划。
    """
    if not isinstance(test_plan, dict):
        return False
    # 必需字段检查
    required_keys = ["function_name", "logic_analysis"]
    for key in required_keys:
        if key not in test_plan:
            logger.warning("Planner 输出缺少必需字段: %s", key)
            return False
    # logic_analysis 内部结构验证
    la = test_plan.get("logic_analysis", {})
    return isinstance(la, dict)


def _get_default_test_plan(function_name: str | None) -> dict[str, Any]:
    """
    生成默认测试计划（降级方案）。

    Args:
        function_name: 目标函数名。

    Returns:
        默认测试计划字典。
    """
    return {
        "function_name": function_name or "unknown",
        "description": "自动生成的默认测试计划",
        "logic_analysis": {
            "input_domain": "未知",
            "output_domain": "未知",
            "preconditions": [],
            "postconditions": [],
            "edge_cases": [],
        },
        "test_cases": [],
    }
