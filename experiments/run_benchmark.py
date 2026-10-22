"""
批量实验脚本：对数据集运行 AITester 及多基线对比，记录完整结果。

支持的基线方法：
    - aitester     : 完整多智能体系统（Planner+Generator+Executor+Debugger）
    - plain_llm    : 纯 LLM 基线（无 Planner、无修复循环，仅一次调用）
    - single_agent : 单智能体基线（所有功能合并为一个 LLM 调用）
    - plain_llm_df : plain_llm + 检出优先协议（X1/2026-10-05 审查 P0-3，
                     归因基线：隔离"检出优先提示词效应"与"多智能体编排
                     效应"；显式 --baselines 指定，不进默认列表）
    - plain_llm_df_spec : plain_llm_df + 规格锚（A-10/2026-10-16 独立评审 P0：
                     Generator prompt 的"目标代码"块被预计算规格锚文档替换
                     ——specification-anchored 归因臂；显式 --baselines 指定，
                     不进默认列表）

支持的数据集（通过 dataset 参数指定）：
    - examples     : 内置示例数据集（InMemoryDataset，无需下载）
    - swe_bench    : SWE-bench 数据集（需提前下载到 ~/.cache/aitester/swe_bench/）
    - defects4j_py : Defects4J-Python 数据集（需提前下载）
    - synthetic    : 合成数据集（本地生成，支持自定义规模，无需外部下载）

使用方式：
    # 仅运行内置示例数据集
    python experiments/run_benchmark.py --dataset examples --baselines aitester plain_llm single_agent

    # 运行 SWE-bench lite 子集
    python experiments/run_benchmark.py --dataset swe_bench --subset lite --baselines aitester

    # 保存结果到指定目录
    python experiments/run_benchmark.py --output-dir ./my_results --verbose

    # 并行执行（需设置 BENCHMARK_PARALLELISM 环境变量或 --parallel 参数）
    BENCHMARK_PARALLELISM=4 python experiments/run_benchmark.py --dataset synthetic --task-count 10
"""

from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import openai

# 确保项目根目录在路径中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 延迟导入，避免 E402
from config import (  # noqa: E402
    ACTIVE_PROFILE,
    BENCHMARK_PARALLELISM,
    ENABLE_DEBUGGER,
    ENABLE_MUTATION_SCORING,
    ENABLE_PLANNER,
    EXECUTION_TIMEOUT,
    LLM_CONFIGS,
    LLM_RETRY_WAIT,
    MAX_ITERATIONS,
    MAX_REGENERATIONS,
    MUTATION_MAX_MUTANTS,
    REPO_LEVEL_EXECUTION,
    SWE_BENCH_P2P_GATE_ENABLE,
    SWE_BENCH_P2P_GATE_THRESHOLD,
    SWE_REPO_SETUP_TIMEOUT,
)
from experiments.postprocess_wall import (  # noqa: E402
    StageTimer,
    build_postprocess_wall,
    postprocess_warn_s,
)
from src.api.complexity_router import (  # noqa: E402
    complexity_class_to_routing_hints,
    compute_complexity_score,
    routing_enabled,
)
from src.budget.token_usage import aggregate_row_token_usage, token_metric_reading  # noqa: E402
from src.datasets.dataset_loader import (  # noqa: E402
    BenchmarkTask,
    InMemoryDataset,
    _strict_instance_code_enabled,
    load_dataset,
)
from src.graph import token_usage  # noqa: E402
from src.graph.state import AITesterState, create_initial_state  # noqa: E402
from src.graph.workflow import build_workflow, effective_stop_reason, end_task_trace, start_task_trace  # noqa: E402
from src.observability.failure_taxonomy import (  # noqa: E402
    FAULT_SIDES,
    INTERACTION_EDGES,
    FailureBucket,
    annotate_final_state,
)
from src.tools.patch_abstain import evaluate_patch_abstention  # noqa: E402
from src.tools.patch_validate import evaluate_patch_validation  # noqa: E402
from src.utils.logging_utils import setup_logger_safety  # noqa: E402
from src.utils.process_utils import run_with_timeout as _run_with_timeout  # noqa: E402

logger = logging.getLogger(__name__)

# P2-8：experiments 入口此前从未接入日志脱敏（脱敏过滤器只在 CLI 入口挂载）。
# 这里显式挂载，确保 LLM 调用路径的异常日志（可能含凭证）在实验场景下也被脱敏。
setup_logger_safety()

# 进度条支持
try:
    from tqdm import tqdm

    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    tqdm = None  # type: ignore[assignment]


# ─── 进度条工具 ───────────────────────────────────────────────────────────────


class ProgressBar:
    """进度条包装类，兼容有无 tqdm 的情况。"""

    def __init__(self, total: int, desc: str = "处理任务", enabled: bool = True):
        self.total = total
        self.desc = desc
        self.enabled = enabled
        self._pbar = None

        if enabled and HAS_TQDM and tqdm is not None:
            self._pbar = tqdm(
                total=total,
                desc=desc,
                unit="task",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
            )
        else:
            self._pbar = _DummyProgressBar()

    def update(self, n: int = 1) -> None:
        """更新进度。"""
        self._pbar.update(n)

    def set_description(self, desc: str) -> None:
        """设置描述。"""
        self._pbar.set_description(desc)

    def close(self) -> None:
        """关闭进度条。"""
        self._pbar.close()

    def __enter__(self) -> ProgressBar:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class _DummyProgressBar:
    """无 tqdm 时的占位进度条。"""

    def update(self, n: int = 1) -> None:
        pass

    def set_description(self, desc: str) -> None:
        pass

    def close(self) -> None:
        pass


# ─── API 配置管理 ──────────────────────────────────────────────────────────────


# 所有可用的 API 配置（从 config.LLM_CONFIGS 读取）
# O32（2026-09-29 审查 P0）：repr 脱敏——此前 _VALID_APIS 是含
# api_key 明文的 dict 列表，repr(_VALID_APIS) / 日志 / JSON 工件
# 中 "valid_apis" 字段若被序列化会泄露密钥。现改为：
# 1. 存储时保留 key（运行期 _set_thread_api 消费）；
# 2. 工件 JSON 的 "valid_apis" 字段只写**数量**（历史口径不变）；
# 3. 新增 _VALID_APIS_REDACTED 供日志 / repr 场景消费（key 已脱敏）。
_VALID_APIS = [{"key": c.api_key, "url": c.base_url, "model": c.model_name} for c in LLM_CONFIGS]
_VALID_APIS_REDACTED = [
    {"key": "<REDACTED>" if c.api_key else "", "url": c.base_url, "model": c.model_name} for c in LLM_CONFIGS
]


def _get_api_for_task(task_index: int) -> dict:
    """根据任务索引分配 API（轮询分摊限流压力）。"""
    if not _VALID_APIS:
        return {"key": "", "url": "", "model": ""}
    return _VALID_APIS[task_index % len(_VALID_APIS)]


def _set_thread_api(task_index: int) -> None:
    """为当前线程设置 API 配置。

    需同时设置 model_name：_get_llm_config 在 _thread_local.api_key 非空时
    经 getattr(_thread_local, "model_name", LLM_CONFIGS[0].model_name) 读取，
    此前只设 api_key/base_url、丢弃 model，多模型轮询时 model 恒回退首配置，
    轮询失效。
    """
    from src.agents.llm_client import _thread_local

    api = _get_api_for_task(task_index)
    _thread_local.api_key = api["key"]
    _thread_local.base_url = api["url"]
    _thread_local.model_name = api["model"]


# ─── 基线方法实现 ─────────────────────────────────────────────────────────────


def run_aitester_baseline(
    state: AITesterState,
) -> dict[str, Any]:
    """
    完整 AITester 基线：Planner → Generator → Executor → (Debugger → PatchApplier) × N。

    Args:
        state: 初始工作流状态。

    Returns:
        最终状态字典，包含 test_passed, coverage_report 等字段。
    """
    graph = build_workflow()
    return graph.invoke(state)


def run_plain_llm_baseline(
    state: AITesterState,
) -> dict[str, Any]:
    """
    纯 LLM 基线（Baseline B）：不启用 Planner，不进行修复循环。
    Generator 直接基于目标代码生成测试，Executor 执行一次，无 Debugger。

    模拟"无规划、无自修复"的简单 LLM 调用场景。

    实现说明：直接构建 planner=False、debugger=False 的降级工作流。
    此前用 importlib.reload(wf_module) 改模块全局开关，但 workflow.py 读取的是
    config 模块的 ENABLE_PLANNER/ENABLE_DEBUGGER（reload 后重新 from config import，
    值不变），开关实际未生效——"plain_llm" 跑的是完整管线。参数化后彻底移除 reload
    （并行模式下多线程 reload 共享模块还有竞态风险）。

    Args:
        state: 初始工作流状态。

    Returns:
        最终状态字典。
    """
    graph = build_workflow(planner=False, debugger=False)
    return graph.invoke(state)


def _apply_execution_flaky_evidence(state: dict[str, Any], result: dict[str, Any]) -> None:
    """A16（2026-10-18 第三方评审 P1）：把 Executor 尝试证据写入 single_agent state。

    single_agent 基线绕过工作流 ``_executor_node`` 直接调用 ExecutorAgent，
    因此不会经过节点侧的 fail→pass 消费——若不同步，该基线仍把"同测试首败
    次过"记成 ``test_passed=True``，把执行不稳定的证据抹掉（评审 A16 的
    "检测与判分消费真实序列"要求）。

    与 ``_executor_node`` 同口径（保守）：
    - ``flaky_fail_then_pass=True``（执行层观察到失败后重试通过）→ 写
      ``flaky_detected/flaky_unverified=True`` + 真实 pass/total 计数，
      ``test_passed`` 保守记 False（不稳定结果不能作为成功证据）；
    - 无该证据（None/False）→ 仅按历史口径写 test_passed，其余键不写
      （state 默认 None，历史字段/行为逐位不变）。
    """
    if not bool(result.get("flaky_fail_then_pass")):
        state["test_passed"] = bool(result["passed"])
        return
    attempts = result.get("execution_attempts") or []
    records = [a for a in attempts if isinstance(a, dict)]
    state["test_passed"] = False
    state["flaky_detected"] = True
    state["flaky_unverified"] = True
    state["flaky_pass_count"] = sum(1 for a in records if a.get("passed"))
    state["flaky_total_count"] = len(records)


def run_single_agent_baseline(
    state: AITesterState,
) -> dict[str, Any]:
    """
    单智能体基线（Baseline C）：将 Planner + Generator + Debugger 功能合并为一次 LLM 调用。
    无工作流，只有一个大 Prompt 让 LLM 直接输出测试代码，并允许一轮修复。

    模拟"单一 LLM 调用"的对比实验场景。

    Args:
        state: 初始工作流状态。

    Returns:
        最终状态字典（test_passed, coverage_report 等）。
    """
    from src.agents.executor import ExecutorAgent
    from src.agents.generator import GeneratorAgent
    from src.graph.nodes import _record_execution_trace

    agent = GeneratorAgent()
    # 执行超时必须走 config.EXECUTION_TIMEOUT（含容错解析 + [10, 300] 范围校验）；
    # 此前直接 int(os.getenv("EXECUTION_TIMEOUT", "30"))，坏值（如 "abc"）会让基线
    # 运行在 import 后立即 ValueError 崩溃，绕过配置层的兜底
    executor = ExecutorAgent(timeout=EXECUTION_TIMEOUT)

    # W6（2026-10-05 审查落地·基线健全性修复）：
    # 1) prompt 注入真实模块名——此前不含模块名，合成任务模块名是 task_id
    #    末段（如 sqrt_negative_input_0000），LLM 只能猜测（主批次
    #    benchmark_synthetic_20261001_121523 实测 50/50 猜成 math_utils 等
    #    错误名）→ M1 干净复跑全部 collection error（test_error_rate=94%），
    #    且失败类别恒误报 execution_trace_missing。plain_llm 走完整工作流
    #    （模块名由 Generator 节点注入），单智能体基线口径应对齐。
    # 2) 移除与"只输出测试代码"自相矛盾的"生成修复补丁"要求——修复轮
    #    由下方 fix_query 独立承载，该要求从未被消费且诱导模型输出双代码块。
    module_name = str(state.get("module_name") or os.path.splitext(os.path.basename(str(state["target_file"])))[0])
    # 单次 LLM 调用：要求直接生成测试并自行判断是否需要修复
    query = (
        f"你是一个软件测试专家。请分析以下代码并直接生成完整的 pytest 测试代码。\n\n"
        f"被测模块名为 `{module_name}`：测试代码必须 `from {module_name} import ...` 导入被测函数，"
        f"禁止猜测其他模块名，禁止重新实现被测函数。\n\n"
        f"目标代码：\n```python\n{state['target_code']}\n```\n\n"
        f"要求：\n"
        f"1. 找出代码中可能存在的 bug，编写能捕获这些 bug 的测试用例\n"
        f"2. 只输出 pytest 测试代码（用 ```python 包裹），不要输出其他内容"
    )

    # 1.2 改进（MutGen 式变异反馈闭环）：单智能体基线在修复前消费上一轮
    # 变异评估的"存活变异体"反馈（state["mutation_feedback"]），引导 LLM
    # 针对"当前测试未捕获的故障模式"补强断言；无反馈时行为与历史口径一致。
    # W6 修复：反馈拼接移到 LLM 调用**之前**——此前在调用之后才拼进 query，
    # 修改后的 query 从未再次使用（反馈从未真正进入 prompt，死代码）。
    feedback = state.get("mutation_feedback")
    if feedback and feedback.get("survived_mutants"):
        query += "\n\n【变异反馈】以下变异体未被现有测试捕获，请在生成测试时补充针对性断言：\n" + "\n".join(
            f"- {d}" for d in feedback["survived_mutants"][:5]
        )

    test_code = agent._extract_python_code(agent._call_llm(query))
    state["generated_test"] = test_code

    # 执行测试
    _t0 = time.perf_counter()
    result = executor.execute(
        test_code=test_code,
        target_file=state["target_file"],
        target_function=state.get("target_function"),
    )
    _elapsed = time.perf_counter() - _t0

    # A16：执行证据统一走 helper（fail→pass → 保守判分 + flaky 标记）
    _apply_execution_flaky_evidence(state, result)
    state["test_output"] = result["output"]
    state["coverage_report"] = result["coverage"]
    state["failed_cases"] = result["failed_cases"]
    state["iteration"] = 0
    # W6 修复：补记 execution_trace——此前绕过工作流 _executor_node 直接调
    # ExecutorAgent，轨迹恒空 → refine_final_error_category 把全部失败
    # 误判为 EXECUTION_TRACE_MISSING（"执行器异常路径"），掩盖真实失败类别
    state["execution_trace"] = _record_execution_trace(
        state,
        passed=bool(result["passed"]),
        coverage=float(result.get("coverage") or 0.0),
        elapsed_seconds=round(_elapsed, 3),
    )

    # 若测试失败，尝试一轮 LLM 修复（单智能体只能修复一次）
    if not result["passed"] and result["failed_cases"]:
        fix_query = (
            f"测试失败了，请修复目标代码中的 bug。只输出修复后的完整代码（```python 包裹）。\n\n"
            f"原始代码：\n```python\n{state['target_code']}\n```\n\n"
            f"测试输出：\n{result['output'][:1000]}"
        )
        fix_raw = agent._call_llm(fix_query)
        fix_code = agent._extract_python_code(fix_raw)
        if fix_code:
            from src.tools.patch_applier import apply_patch_to_code

            new_code, applied = apply_patch_to_code(state["target_code"], fix_code)
            if applied:
                # 2026-09-26 全面审查（P0 数据完整性）：single_agent 基线
                # 此前直接 open("w") 写 LLM 输出的 new_code，绕过
                # _patch_applier_node 的安全检查——LLM 返回空壳/过短代码时
                # 会把被测实例文件清空，后续基线/重试拿到空代码。
                # 现补最小守卫：非空（≥ 原代码 10%）+ 函数定义数不减少
                # （与工作流 _patch_applier_node 安全检查口径一致）。
                import re

                _n_orig_defs = len(re.findall(r"^\s*def \w+", state["target_code"], re.M))
                _n_new_defs = len(re.findall(r"^\s*def \w+", new_code, re.M))
                if len(new_code) >= max(1, len(state["target_code"]) // 10) and _n_new_defs >= _n_orig_defs:
                    state["target_code"] = new_code
                    # 安全检查通过，写回文件并重试
                    with open(state["target_file"], "w", encoding="utf-8") as f:
                        f.write(new_code)
                    _t1 = time.perf_counter()
                    retry_result = executor.execute(
                        test_code=test_code,
                        target_file=state["target_file"],
                        target_function=state.get("target_function"),
                    )
                    _apply_execution_flaky_evidence(state, retry_result)
                    state["test_output"] = retry_result["output"]
                    state["coverage_report"] = retry_result["coverage"]
                    state["failed_cases"] = retry_result["failed_cases"]
                    state["iteration"] = 1
                    # W6 修复：修复轮执行同样补记 execution_trace（口径同首轮）
                    state["execution_trace"] = _record_execution_trace(
                        state,
                        passed=bool(retry_result["passed"]),
                        coverage=float(retry_result.get("coverage") or 0.0),
                        elapsed_seconds=round(time.perf_counter() - _t1, 3),
                    )
                else:
                    # 不安全：放弃写盘，保持原代码（与 patch_applier 拒写口径一致）
                    logger.warning("single_agent 基线：修复代码未通过安全检查（过短/丢失函数定义），保留原代码")
                    state["iteration"] = 1

    return state


def run_plain_llm_df_baseline(
    state: AITesterState,
) -> dict[str, Any]:
    """plain_llm + 检出优先协议基线（X1/2026-10-05 审查 P0-3，归因基线）。

    动机：检出优先协议（ADR-0015）的提示词效应与多智能体编排效应在
    "aitester(DETECTION_FIRST_ENABLE=true) vs plain_llm" 对照中混在一起
    ——强模型下若 plain_llm 追平 aitester，无法归因是"协议提示词有效"
    还是"编排无效"。本基线把检出优先协议叠加到 plain_llm（无 Planner、
    无修复循环）上：单次生成 + 执行 + 首轮全绿时再生成更强测试（受
    _MAX_REGENERATIONS 上限保护），隔离两个效应。

    实现：
    - build_workflow(planner=False, debugger=False, allow_regeneration=True)：
      无修复循环但保留 executor → generator 再生成路由（"debug" 映射
      "done"——失败测试即潜在检出，不修复，与 plain_llm 口径一致）；
    - config.set_detection_first_thread_override(True)：线程级覆盖（非
      os.environ——--parallel 下多任务线程并发跑不同基线，进程级 env
      会串扰邻线程的 plain_llm 基线）；invoke 结束 finally 恢复 None，
      防线程池复用残留；
    - 复用全套既有机制：_should_debug 的 detection_first_all_green 分支、
      _generator_node 的强化段落与 regeneration_count 计数、
      detection_first_red_seen / detection_first_status 观测字段
      （_build_task_result 通用透传，无需特判）。

    Args:
        state: 初始工作流状态。

    Returns:
        最终状态字典。
    """
    import config as _cfg

    graph = build_workflow(planner=False, debugger=False, allow_regeneration=True)
    _cfg.set_detection_first_thread_override(True)
    try:
        return graph.invoke(state)
    finally:
        _cfg.set_detection_first_thread_override(None)


# ─── A-10（2026-10-16，独立评审 P0）：df_spec 臂的规格锚表 ────────────────────
# 表由 experiments/build_spec_anchor_table.py 从 Planner LLM 缓存零 LLM 物化
# （{function_name, logic_analysis} 计划子集，按 target_code 内容哈希索引）。
# env DF_SPEC_ANCHOR_TABLE 可覆盖路径（测试/复跑用；已入 env 快照）；默认
# 指向归档工件目录。表缺失/损坏 → 臂整体回落 df 口径（逐任务
# spec_replace_applied=attempted_fallback，命中率可审计）。
_DF_SPEC_ANCHOR_TABLE_DEFAULT = os.path.join(
    PROJECT_ROOT, "experiments", "results", "emse_spec_anchor_20261016", "SPEC_ANCHOR_TABLE.json"
)

_SPEC_ANCHOR_TABLE_CACHE: dict[str, dict[str, dict[str, Any]] | None] = {}


def _load_spec_anchor_table() -> dict[str, dict[str, Any]] | None:
    """加载规格锚表 anchors 映射（缺失/损坏/形状不符 → None）。按解析路径进程内缓存。"""
    raw = (os.environ.get("DF_SPEC_ANCHOR_TABLE") or "").strip()
    path = raw or _DF_SPEC_ANCHOR_TABLE_DEFAULT
    if path in _SPEC_ANCHOR_TABLE_CACHE:
        return _SPEC_ANCHOR_TABLE_CACHE[path]
    anchors: dict[str, dict[str, Any]] | None = None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("anchors"), dict):
            anchors = data["anchors"]
    except (OSError, ValueError):
        anchors = None
    _SPEC_ANCHOR_TABLE_CACHE[path] = anchors
    return anchors


def _lookup_spec_anchor(state: AITesterState) -> dict[str, Any] | None:
    """按 target_code 内容哈希（strip 后 sha256）查锚材料；未命中/表不可用 → None。"""
    table = _load_spec_anchor_table()
    if not table:
        return None
    source = str(state.get("target_code") or "").strip()
    if not source:
        return None
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    material = table.get(digest)
    return material if isinstance(material, dict) else None


def _attach_generated_spec_examples(state: AITesterState) -> int:
    """Q-1（2026-10-18）：无 Planner 臂（df_spec/doc/union/augment）的示例生成接线。

    双门 ``SPEC_ORACLE_EXAMPLES_ENABLE ∧ SPEC_ORACLE_EXEC_ENABLE`` 开启时，
    对这些"Planner 关闭、只有锚材料"的臂调用
    ``experiments/spec_examples_generator.py``（**spec-only**，不发送缺陷代码）：
    - 每任务 **+1 次 LLM 调用**（小 max_tokens、示例 ≤3 条、cache namespace
      沿用当前 ``AITESTER_CACHE_NAMESPACE``）；
    - 成功 → 把 examples 并入锚材料（``spec_anchor.logic_analysis``；仅
      human_spec 的锚则构造 ``{"function_name", "examples"}`` 的 logic_analysis），
      N-3 材料解析器随后解析并编译为逐示例断言；
    - 失败/空 → 透传空、不修改锚材料（回落无示例口径，可审计：行字段
      ``spec_oracle_examples_source=none``）。

    Args:
        state: 任务初始状态（需已写入 ``spec_anchor``）。

    Returns:
        附加示例条数（0 = 开关关/无材料/生成失败/空示例）。
    """
    try:
        from experiments.spec_examples_generator import (
            PRODUCTION_MAX_EXAMPLES,
            generate_spec_examples,
            spec_examples_production_enabled,
        )
    except Exception:  # pragma: no cover - 实验层导入失败不阻断主链路
        return 0
    if not spec_examples_production_enabled():
        return 0
    anchor = state.get("spec_anchor")
    if not isinstance(anchor, dict) or not anchor:
        return 0
    logic = anchor.get("logic_analysis")
    logic_material: dict[str, Any] | None = None
    if isinstance(logic, dict) and logic:
        logic_material = logic
        material: dict[str, Any] = dict(logic)
        kind = "logic"
    else:
        human_spec = anchor.get("human_spec")
        if not (isinstance(human_spec, str) and human_spec.strip()):
            return 0
        material = {"function_name": str(anchor.get("function_name") or ""), "human_spec": human_spec}
        kind = "human"
    human_anchor = anchor.get("human_spec")
    if isinstance(human_anchor, str) and human_anchor.strip():
        material.setdefault("human_spec", human_anchor)
    target_function = str(
        state.get("target_function") or anchor.get("function_name") or material.get("function_name") or ""
    )
    from src.specs import extract_signature_params

    sig_params = extract_signature_params(str(state.get("target_code") or ""), target_function)
    try:
        result = generate_spec_examples(
            material,
            signature_params=sig_params,
            task_id=str(state.get("task_id") or ""),
            max_examples=PRODUCTION_MAX_EXAMPLES,
        )
    except Exception as e:  # 失败透传（不阻断任务）
        logger.warning("Q-1 示例生成异常，透传空（无示例口径）：%s", e)
        return 0
    examples = result.get("examples") or []
    if not examples:
        logger.info(
            "Q-1 示例生成无有效示例（status=%s reason=%s），回落无示例口径",
            result.get("status"),
            result.get("reason"),
        )
        return 0
    new_anchor = dict(anchor)
    if kind == "logic" and logic_material is not None:
        new_logic = dict(logic_material)
        new_logic["examples"] = examples
        new_anchor["logic_analysis"] = new_logic
    else:
        new_anchor["logic_analysis"] = {"function_name": target_function, "examples": examples}
    state["spec_anchor"] = new_anchor
    logger.info(
        "Q-1 已附加 %d 条 spec-only 示例（source=spec_generator, fn=%s）",
        len(examples),
        target_function or "?",
    )
    return len(examples)


def _spec_oracle_examples_fields(state: dict[str, Any] | None) -> dict[str, Any]:
    """Q-1 行字段：示例来源/条数（成功/失败两分支键位一致）。

    口径（只报"实际被 oracle 使用的示例"）：
    - ``planner``：examples 来自 Planner 现场输出（``spec_ir`` 优先，
      ``test_plan.logic_analysis`` 兜底）；
    - ``spec_generator``：无 Planner 臂由 spec-only 生成器附加到
      ``spec_anchor.logic_analysis`` 的示例；
    - ``none``：开关关 / 无示例（含生成失败/空）；
    ``count`` = 该来源实际示例条数（int，关闭时 0）。开关关时恒 none/0
    （历史批次 JSON 键位同构，值语义不变）。
    """
    source = "none"
    count = 0
    try:
        from src.agents.planner import spec_oracle_examples_enabled

        enabled = spec_oracle_examples_enabled()
    except Exception:  # pragma: no cover
        enabled = False
    if state and enabled:

        def _count(container: Any) -> int:
            if isinstance(container, dict):
                examples = container.get("examples")
                if isinstance(examples, list) and examples:
                    return len(examples)
            return 0

        n = _count(state.get("spec_ir"))
        if n:
            source, count = "planner", n
        else:
            test_plan = state.get("test_plan")
            n = _count(test_plan.get("logic_analysis")) if isinstance(test_plan, dict) else 0
            if n:
                source, count = "planner", n
            else:
                anchor = state.get("spec_anchor")
                n = _count(anchor.get("logic_analysis")) if isinstance(anchor, dict) else 0
                if n:
                    source, count = "spec_generator", n
    return {"spec_oracle_examples_source": source, "spec_oracle_examples_count": count}


def run_plain_llm_df_spec_baseline(state: AITesterState) -> dict[str, Any]:
    """plain_llm_df + 规格锚（A-10/2026-10-16，独立评审 P0：P1 超越路径核心对照臂）。

    三效应隔离链（每步只增一个变量）：
        plain_llm → +检出优先协议 = plain_llm_df → +规格锚 = plain_llm_df_spec

    实现（与 plain_llm_df 同构，唯一增量 = Generator prompt 侧规格替换）：
    - 锚材料预载：state["spec_anchor"] ← 预计算锚表（Planner 计划子集；由
      experiments/build_spec_anchor_table.py 从既有 LLM 缓存零 LLM 物化）。
      未命中不写键 → 回落 df 口径，逐任务 spec_replace_applied=
      "attempted_fallback" 可审计（命中率即"锚覆盖率"，分析层按该字段
      过滤命中子集）。
    - 线程级规格模式覆盖 set_spec_mode_thread_override("replace")（非
      os.environ——--parallel 下不串扰邻线程其它臂；与 df 臂检出优先
      线程覆盖同模式）；finally 恢复 None，防线程池复用残留。
    - 渲染路径与 aitester replace 臂共用（build_spec_replace_section）。

    运行要求：先跑 experiments/build_spec_anchor_table.py 生成/更新锚表；
    结果解释必须与该次填充的锚表版本（SPEC_ANCHOR_TABLE.json + SHA256SUMS）
    成套归档（"replace 是否实际生效"以 details[].spec_replace_applied 为准）。
    """
    import config as _cfg
    from src.tools.spec_first import set_spec_mode_thread_override

    anchor = _lookup_spec_anchor(state)
    if anchor is not None:
        state["spec_anchor"] = anchor
    else:
        logger.info("df_spec：任务 %s 无规格锚材料（回落 df 口径）", state.get("task_id", "?"))
    # Q-1：无 Planner 臂在双门开时 +1 次 spec-only 示例生成（默认关零变化）
    _attach_generated_spec_examples(state)
    graph = build_workflow(planner=False, debugger=False, allow_regeneration=True)
    _cfg.set_detection_first_thread_override(True)
    set_spec_mode_thread_override("replace")
    try:
        return graph.invoke(state)
    finally:
        set_spec_mode_thread_override(None)
        _cfg.set_detection_first_thread_override(None)


# ─── P1（2026-10-17 独立评审 §6 P1 / A-02）：人类 docstring 独立规格锚两臂 ────
# df_spec（A-10）的锚材料 = Planner 对**缺陷代码**的再描述；P1 修复路径改用
# 独立于缺陷实现的人类规格锚。表由 experiments/build_docstring_anchor_table.py
# 零 LLM 从 QuixBugs 数据目录物化（模块级人类规格块；union 变体另并入既有
# Planner 锚的 logic_analysis）。env DOC_ANCHOR_TABLE 可覆盖路径（测试/复跑
# 用；已入 env 快照）；默认路径按臂区分（doc / union 两套工件互不覆盖）。
# 表缺失/损坏 → 臂整体回落 df 口径（逐任务 spec_replace_applied=
# attempted_fallback，与 df_spec 同字段语义；命中率可审计，不 crash）。
_DOC_ANCHOR_TABLE_DEFAULT = os.path.join(
    PROJECT_ROOT, "experiments", "results", "emse_docstring_anchor_20261017", "DOCSTRING_ANCHOR_TABLE.json"
)
_DOC_ANCHOR_TABLE_UNION_DEFAULT = os.path.join(
    PROJECT_ROOT, "experiments", "results", "emse_docstring_anchor_20261017", "DOCSTRING_ANCHOR_TABLE_UNION.json"
)

_DOC_ANCHOR_TABLE_CACHE: dict[str, dict[str, dict[str, Any]] | None] = {}


def _load_doc_anchor_table(default_path: str) -> dict[str, dict[str, Any]] | None:
    """加载 docstring 锚表 anchors 映射（env DOC_ANCHOR_TABLE 优先；缺失/损坏/形状不符 → None）。

    按**解析路径**进程内缓存（与 df_spec 锚表缓存同模式）；env 覆盖对两臂
    同时生效——正式跑批不得设该变量（默认路径即预注册锚表）。
    """
    raw = (os.environ.get("DOC_ANCHOR_TABLE") or "").strip()
    path = raw or default_path
    if path in _DOC_ANCHOR_TABLE_CACHE:
        return _DOC_ANCHOR_TABLE_CACHE[path]
    anchors: dict[str, dict[str, Any]] | None = None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("anchors"), dict):
            anchors = data["anchors"]
    except (OSError, ValueError):
        anchors = None
    _DOC_ANCHOR_TABLE_CACHE[path] = anchors
    return anchors


def _lookup_doc_anchor(state: AITesterState, default_path: str) -> dict[str, Any] | None:
    """按 target_code 内容哈希（strip 后 sha256）查 doc 锚材料；未命中/表不可用 → None。"""
    table = _load_doc_anchor_table(default_path)
    if not table:
        return None
    source = str(state.get("target_code") or "").strip()
    if not source:
        return None
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    material = table.get(digest)
    return material if isinstance(material, dict) else None


def _run_plain_llm_df_anchor_baseline(
    state: AITesterState,
    *,
    default_anchor_path: str,
    arm_label: str,
    spec_mode: str = "replace",
) -> dict[str, Any]:
    """plain_llm_df + 独立锚（doc / union / augment 三臂共享实现；与 df_spec 臂同构）。

    实现（与 run_plain_llm_df_spec_baseline 唯一差别 = 锚表来源/默认路径/模式）：
    - 锚材料预载：state["spec_anchor"] ← 预计算锚表条目。未命中不写键 →
      回落 df 口径（节点渲染空串 → spec_replace_applied=attempted_fallback
      ［replace］或 spec_augment_applied=attempted_fallback ［augment］）。
    - 线程级规格模式覆盖 set_spec_mode_thread_override(spec_mode)（非
      os.environ——--parallel 下不串扰邻线程其它臂）；finally 恢复 None。
    - spec_mode="replace"（默认，既有 doc / union 两臂行为不变）：渲染路径
      与 aitester replace 臂共用（build_spec_replace_section，目标代码被替换）。
    - spec_mode="augment"（M-1，2026-10-17）：渲染路径改用
      build_spec_augment_section——缺陷代码完整保留 + 人类规格锚并列追加
      （L 轮 replace 阴性结论的直接后续假设）。

    运行要求：先跑 experiments/build_docstring_anchor_table.py 生成锚表；
    结果解释必须与该次填充的锚表版本（.json + SHA256SUMS）成套归档。
    """
    import config as _cfg
    from src.tools.spec_first import set_spec_mode_thread_override

    anchor = _lookup_doc_anchor(state, default_anchor_path)
    if anchor is not None:
        state["spec_anchor"] = anchor
    else:
        logger.info("%s：任务 %s 无锚材料（回落 df 口径）", arm_label, state.get("task_id", "?"))
    # Q-1：无 Planner 臂在双门开时 +1 次 spec-only 示例生成（默认关零变化）
    _attach_generated_spec_examples(state)
    graph = build_workflow(planner=False, debugger=False, allow_regeneration=True)
    _cfg.set_detection_first_thread_override(True)
    set_spec_mode_thread_override(spec_mode)
    try:
        return graph.invoke(state)
    finally:
        set_spec_mode_thread_override(None)
        _cfg.set_detection_first_thread_override(None)


def run_plain_llm_df_doc_baseline(state: AITesterState) -> dict[str, Any]:
    """plain_llm_df + 人类 docstring 独立规格锚（P1 回退 (a) 档）。

    锚材料 = 模块级人类规格块（QuixBugs 尾部 Input/Output/Examples），
    **不含**任何 Planner 对缺陷代码的再描述——从源头切断
    oracle-from-implementation 锚点。缺人类规格的任务（QuixBugs ``node.py``）
    仍走替换口径但锚文本为空（human_spec 键在场语义，见 spec_first）。
    """
    return _run_plain_llm_df_anchor_baseline(
        state,
        default_anchor_path=_DOC_ANCHOR_TABLE_DEFAULT,
        arm_label="df_doc",
        spec_mode="replace",
    )


def run_plain_llm_df_doc_union_baseline(state: AITesterState) -> dict[str, Any]:
    """plain_llm_df + 人类规格锚 ∪ Planner SpecExpr 子句（P1 回退 (b) 档）。

    锚材料 = 人类规格块 + 既有 Planner 锚表的 ``logic_analysis``（内容寻址
    命中时并入；未命中只保留人类规格）——保留形式化子句增益，但不让
    Planner 再描述**替换**人类规格。
    """
    return _run_plain_llm_df_anchor_baseline(
        state,
        default_anchor_path=_DOC_ANCHOR_TABLE_UNION_DEFAULT,
        arm_label="df_doc_union",
        spec_mode="replace",
    )


def run_plain_llm_df_doc_augment_baseline(state: AITesterState) -> dict[str, Any]:
    """plain_llm_df + 人类规格锚**并列增广**（M-1，2026-10-17；L 轮阴性后续假设）。

    与 doc 臂的唯一差别 = 规格模式 "augment"（而非 "replace"）：
    - Generator prompt **保留完整缺陷代码**（代码块不替换）；
    - 人类独立规格锚作为独立段并列追加在代码块之后
      （build_spec_augment_section 渲染）；
    - 动机：L 轮 replace 三臂实测 df 86.11% / doc 60.00% / union 61.76%
      （not_confirmed）——"移除实现代码"是检出损失主因；增广检验"代码 + 独立
      规格并列"能否在不损失检出的前提下提升检出。

    锚表同 doc 臂（默认 ``DOCSTRING_ANCHOR_TABLE.json``；env DOC_ANCHOR_TABLE
    可覆盖）。表缺失/命中失败 → 不写 spec_anchor → 节点渲染空串 →
    spec_augment_applied=attempted_fallback（纯 df 代码口径，不 crash）。
    """
    return _run_plain_llm_df_anchor_baseline(
        state,
        default_anchor_path=_DOC_ANCHOR_TABLE_DEFAULT,
        arm_label="df_doc_augment",
        spec_mode="augment",
    )


# 基线方法注册表
BASELINE_REGISTRY: dict[str, callable] = {
    "aitester": run_aitester_baseline,
    "plain_llm": run_plain_llm_baseline,
    "single_agent": run_single_agent_baseline,
    # X1（2026-10-05 审查 P0-3）：检出优先归因基线（显式 --baselines 指定，
    # 不进默认列表——默认三基线口径不变，历史批次可比性保持）
    "plain_llm_df": run_plain_llm_df_baseline,
    # A-10（2026-10-16 独立评审 P0）：检出优先 + 规格锚归因臂（同上口径，
    # 显式 --baselines 指定；依赖锚表工件，见 run_plain_llm_df_spec_baseline）
    "plain_llm_df_spec": run_plain_llm_df_spec_baseline,
    # P1（2026-10-17 独立评审 §6 P1 / A-02）：人类 docstring 独立规格锚两臂
    # （显式 --baselines 指定；依赖 docstring 锚表工件，见
    # docs/design/docstring_anchor.md——doc=纯人类规格 / union=人类规格 +
    # Planner SpecExpr 子句并集）
    "plain_llm_df_doc": run_plain_llm_df_doc_baseline,
    "plain_llm_df_doc_union": run_plain_llm_df_doc_union_baseline,
    # M-1（2026-10-17，L 轮 replace 阴性结论的后续假设）：人类 docstring 规格锚
    # **并列增广**臂——保留完整缺陷代码 + 规格锚并列追加（显式 --baselines 指定；
    # 锚表同 doc 臂，模式 augment，见 run_plain_llm_df_doc_augment_baseline）
    "plain_llm_df_doc_augment": run_plain_llm_df_doc_augment_baseline,
}


# ─── 单任务运行函数 ────────────────────────────────────────────────────────────


def _dump_state_artifacts(output_dir: str, task: BenchmarkTask, baseline: str, final_state: dict[str, Any]) -> None:
    """把单基线运行的环节级状态落盘（P0-2 排查工具的数据基础）。

    保存 Planner 测试计划 / Generator 测试代码 / Debugger 诊断与补丁等
    环节级产物，供 compare_failures.py 逐环节对比"AITester 失败但
    Plain LLM 成功"的任务，定位差异出现在哪个环节。

    Args:
        output_dir: 结果输出目录（raw 子目录自动创建）。
        task: 基准测试任务。
        baseline: 基线方法名。
        final_state: 基线运行结束后的工作流状态。
    """
    artifact = {
        "task_id": task.task_id,
        "baseline": baseline,
        "test_plan": final_state.get("test_plan"),
        "generated_test": final_state.get("generated_test"),
        "diagnosis": final_state.get("diagnosis"),
        "error_category": final_state.get("error_category"),
        "patch": final_state.get("patch"),
        "test_passed": final_state.get("test_passed"),
        "iterations": final_state.get("iteration"),
        "coverage": final_state.get("coverage_report"),
        "rag_stats": final_state.get("rag_stats"),
        # 3.3 位置感知迭代修复定位结果（POSITION_AWARE_REPAIR_ENABLE=true 时
        # 由 debugger 节点写入；position_aware_ab.py 的 _locate_accuracy 读取
        # 本字段计算"定位正确率"。此前缺失 → A/B 脚本永远读到 None → 定位
        # 正确率恒 0.0（指标失真，非功能未生效）。
        "position_aware_focus": final_state.get("position_aware_focus"),
        # P0 仓库级验证诊断（仅 REPO_LEVEL_EXECUTION=true 且 SWE-bench 任务有）
        "repo_verification": final_state.get("repo_verification"),
        # 2026-10 P3（A/B 阴性结果驱动）：跨文件依赖图 + 任务元数据
        # （cross_file_root_cause.py 的 DEP_GRAPH_INCOMPLETE 判定依赖
        # cross_file_deps 边数 vs num_files；难度过滤依赖 task_metadata.difficulty。
        # 此前 raw state 未落盘这两键 → 根因分析永远拿到 dep_edges=0 →
        # 失败任务全部误判为 DEP_GRAPH_INCOMPLETE，根因分析对真实瓶颈全盲）。
        "cross_file_deps": final_state.get("cross_file_deps"),
        # H 轮（2026-10-16）：两个"只写不读"的观测信号补落盘。此前它们写进
        # state 后既无路由消费方、也不在本白名单里 → LangGraph 直接丢弃，
        # 节点注释承诺的用途全部落空：
        #   - testless_validation（nodes.py 补丁应用后跑四层静态验证）注释称
        #     "供 G2 风险分级放大风险分"，但 risk_approval 不读它；
        #   - deterministic_guard_report（生成测试的非确定性 AST 扫描）注释称
        #     "供实验层决定是否入库确定性套件"，实验层从未拿到过。
        # 与本白名单前两次扩容（position_aware_focus / cross_file_deps）同一
        # 缺陷形态：信号采到了、没落盘 → 下游永远读到 None → 指标失真。
        # 两开关（TESTLESS_VALIDATION_ENABLE / DETERMINISTIC_GUARD_ENABLE）默认关，
        # 默认档批次这两键恒为 null，历史工件语义零变化。
        "testless_validation": final_state.get("testless_validation"),
        "deterministic_guard_report": final_state.get("deterministic_guard_report"),
        # I2（2026-10-16，ADR-0032）：M10 归因分离标记。此前只写进 test_plan
        # 内部（本工件虽落 test_plan，但读侧需自行下钻嵌套字典，且 LangGraph
        # 未声明该顶层键 → 状态通道读不到）；现由 _planner_node 抬到顶层后
        # 显式登记进白名单，ADR-0032 的 logic_degraded ∧ m10_leaf_fallback
        # 可分离性变为**可机读**。
        "m10_leaf_fallback": final_state.get("m10_leaf_fallback"),
        # BN（2026-10-22）：状态通道的落盘归位。BH→BM 五轮把"读不懂 ⇒ 判优"逐个
        # 收成四值 status 并在判定侧/消费侧接上双读，但这些通道既不在本白名单、
        # 也没进结果行。实测（scripts/tools/bn_dump_boundary_probe.py）：
        # static/safety/oracle 三个检查通道的 status+outcomes 在**两道落盘边界**
        # 都是"5 种运行时态 → 1 种落盘形状"（ok / error / unavailable / disabled /
        # 键不存在逐字节同形）；contract_status 在结果行已披露、在 raw 仍被丢弃。
        # 后果：归档里这些键 0 次出现（普查 1700 个 JSON + 9096 条 JSONL 轨迹行，
        # 见 scripts/tools/bn_archive_status_census.py），"检查完成且零疑点"与
        # "检查崩了 / 按设计没跑"事后不可复核——前几轮补的披露只活在内存里。
        # 本轮只做归位：判定值与判定方向逐字节不变，历史工件一个字节不动，
        # 新批次里默认档（通道未写入）落 null、写入了落真实取值。
        "contract_status": final_state.get("contract_status"),
        "static_check_status": final_state.get("static_check_status"),
        "static_check_outcomes": final_state.get("static_check_outcomes"),
        "safety_check_status": final_state.get("safety_check_status"),
        "safety_check_outcomes": final_state.get("safety_check_outcomes"),
        "oracle_check_status": final_state.get("oracle_check_status"),
        "oracle_check_outcomes": final_state.get("oracle_check_outcomes"),
        "detection_first_status": final_state.get("detection_first_status"),
        "edit_intent_status": final_state.get("edit_intent_status"),
        "deterministic_repair_status": final_state.get("deterministic_repair_status"),
        "task_metadata": task.metadata,
    }
    raw_dir = os.path.join(output_dir, "raw", task.task_id)
    os.makedirs(raw_dir, exist_ok=True)
    artifact_file = os.path.join(raw_dir, f"{baseline}.json")
    with open(artifact_file, "w", encoding="utf-8") as f:
        json.dump(artifact, f, ensure_ascii=False, indent=2, allow_nan=False)


def _compute_contamination_risk_level(
    task_result: dict[str, Any],
    golden_patches: dict[str, str] | None,
) -> str:
    """五、多维度污染检测：对单个任务计算污染风险等级（high/medium/low/unknown/not_applicable）。

    口径（与 experiments.contamination_check 一致）：
    - 取 task_result["patch"]（系统生成的补丁）与 golden_patches 中对应
      任务的黄金补丁（run_benchmark 顶层 golden_patches 字典，task_id →
      补丁文本），调 patch_semantic_similarity 的多维度检测（token Jaccard +
      AST 语句骨架 LCS + 嵌入余弦/词袋余弦保守代理；EMBEDDING_BACKEND 接入
      真实嵌入库时自动升级为 CodeBERT 类语义余弦），综合得出 risk_level；
    - 返回 "high" / "medium" / "low" / "unknown" / "not_applicable" 之一，写入 details[]
      的 contamination_risk_level 字段（供 analyze_results 的
      _contamination_cross_analysis 消费，区分"含污染样本"与"不含
      污染样本"的结果）。

    设计约束（保守、可复算、口径诚实）：
    - 无黄金补丁材料（无 golden_patches / task 无对应条目 / 补丁任一侧
      为空）→ "not_applicable"（N7，2026-10-05 复审：合成数据集此前恒标
      "low"，把"检测没有发生"与"检测过且无重叠证据"混为一谈——前者
      应显式声明检测不适用，而非暗示低风险）；
    - 检测器抛异常（补丁非文本、依赖导入失败等）→ "unknown"（BM 轮，
      2026-10-22：此前折成 "low"，把"这条腿没测成"记进 statistical_analysis
      的"干净组"分母——O22 在 _combined_risk_level 里修掉的就是同一个
      fail-open，包装器漏改）。主流程仍不阻断（不抛异常），但崩了既不
      判污染也不判干净，与两个消费侧已排除 unknown 的口径对齐；
    - 仅读 task_result["patch"]（LLM 修订后的最终补丁），不读中间态。
    """
    task_id = task_result.get("task_id", "")
    generated_patch = task_result.get("patch", "") or ""
    if not golden_patches or not task_id or task_id not in golden_patches:
        return "not_applicable"
    golden_patch = golden_patches.get(task_id, "") or ""
    if not generated_patch or not golden_patch:
        return "not_applicable"
    try:
        from experiments.contamination_check import _combined_risk_level, patch_semantic_similarity

        similarities = patch_semantic_similarity(generated_patch, golden_patch)
        _level = _combined_risk_level(similarities)
        logger.debug(
            "五、污染检测 task=%s: jaccard=%s structural=%s semantic=%s source=%s → %s",
            task_id,
            similarities.get("jaccard"),
            similarities.get("structural"),
            similarities.get("semantic"),
            similarities.get("semantic_source"),
            _level,
        )
        return _level
    except Exception:
        logger.debug("污染风险等级计算失败（标记 unknown，不入干净组）: task=%s", task_id, exc_info=True)
        return "unknown"


def _compute_detection_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1（2026-09-29 审查 P0）：检出率（SWT-Bench 口径）—— 详见
    experiments/_m1_metrics.py。
    """
    from experiments._m1_metrics import _compute_detection_rate as _impl

    return _impl(task, final_state)


def _compute_repair_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1（2026-09-29 审查 P0）：修复率（gold 材料独立裁决／自动化 oracle）—— 详见
    experiments/_m1_metrics.py。
    """
    from experiments._m1_metrics import _compute_repair_rate as _impl

    return _impl(task, final_state)


def _compute_false_fix_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1（2026-09-29 审查 P0）：假修复率（任务级布尔）—— 详见
    experiments/_m1_metrics.py。
    """
    from experiments._m1_metrics import _compute_false_fix_rate as _impl

    return _impl(task, final_state)


def _compute_regression_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """R4（2026-09-30 独立审查 P0）：回归率（任务级布尔）—— 详见
    experiments/_m1_metrics.py。
    """
    from experiments._m1_metrics import _compute_regression_rate as _impl

    return _impl(task, final_state)


def _compute_test_error_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1（2026-09-30 独立审查 N1，P0）：测试执行错误率（任务级布尔）——
    生成测试在 buggy 代码上以"收集错误/语法错误"（根本没跑起来）退出
    记 1.0。详见 experiments/_m1_metrics.py。
    """
    from experiments._m1_metrics import _compute_test_error_rate as _impl

    return _impl(task, final_state)


def _compute_oracle_suite_verdict(task: Any, final_state: dict[str, Any] | None) -> str:
    """N-3（2026-10-17，A-05 后续修复）：确定性 oracle 独立判定 —— 详见
    experiments/_m1_metrics.py。

    与 LLM 测试**分开执行/分开判定**（`-k` 只选 oracle 测试名）；无 oracle
    注入时返回 "unavailable" 且不启动额外子进程（历史口径零差异）。
    取值域：correct / fp / silent / misguided / unavailable。
    """
    from experiments._m1_metrics import _compute_oracle_suite_verdict as _impl

    return _impl(task, final_state)


def _oracle_type_label(final_state: dict[str, Any] | None) -> str:
    """R52（2026-09-30 独立审查 P0）：验收 oracle 类型标签。

    口径：
    - ORACLE_ENHANCE_ENABLE=true 且 test_plan 经增强（oracle_enhanced=True）
      → "enhanced_generated_test"（规约驱动的增强断言）；
    - 否则 → "generated_test"（历史口径：LLM 自生成测试的通过性）。
    最终状态缺失时保守记 "generated_test"（历史默认口径）。
    """
    try:
        import os as _os

        enhanced = _os.getenv("ORACLE_ENHANCE_ENABLE", "false").lower() in ("true", "1", "on")
        if final_state is not None and enhanced and bool(final_state.get("oracle_enhanced")):
            return "enhanced_generated_test"
    except Exception:
        pass
    return "generated_test"


def _patch_plausible(final_state: dict[str, Any] | None) -> int:
    """R53：本轮是否产出"可行"补丁（plausible 计数，任务级 0/1）。

    plausible = 有补丁文本 且 **任一** 迭代的补丁成功写盘。

    ⚠️ **本次修正（2026-10-11，外部评审 §3.5.4 / P0-2 落地实测发现）**
    ------------------------------------------------------------------
    原口径只看 `repair_history[-1]["patch_applied"]`（**末条**），这是一个
    **假阴性源**：当**早期**迭代成功写盘（补丁已进文件、gold 裁决可通过），
    而**后续**迭代被 P0 源码补丁证据门拒绝（`patch_applied=False`）时，
    文件里留着早期那次成功的补丁，但末条记录为 False → `plausible` 被误记 0。

    实测证据（2026-10-11 真实 LLM 批次，QuixBugs n=10）：
    `quixbugs__bitcount` 与 `quixbugs__find_first_in_sorted` 两行出现
    `correct=1 ∧ plausible=0`，逐行证据 `evidence.basis='rejected'`、
    `history_len=2`、`last_patch_applied=False`，但 `repair_rate=1.0`
    （gold 裁决补丁正确）、`source_patched_unverified=True`。
    这与外部评审在存量工件中记录的 **129 行**属同一形态。

    修正后的口径与"补丁是否真的在文件里"一致：**任一*** `patch_applied=True`
    即 plausible（且要求有补丁文本）。该修正使不变量 `correct ⊆ plausible`
    在结构上成立（除被证据门回滚的极端情形，由守卫显式观测）。
    """
    if final_state is None:
        return 0
    patch = final_state.get("patch") or ""
    if not str(patch).strip():
        return 0
    history = final_state.get("repair_history") or []
    if not history:
        # 有补丁文本但无写盘记录（未进入 patch_applier）→ 保守 0
        return 0
    return 1 if any(bool(h.get("patch_applied")) for h in history if isinstance(h, dict)) else 0


def _patch_correct(task: Any, final_state: dict[str, Any] | None) -> int:
    """R53：本轮补丁是否被 gold 材料独立裁决（自动化 oracle，无人工参与）背书（correct 计数，任务级 0/1）。

    口径：repair_rate == 1.0（gold 测试在应用补丁后的代码上全过）。
    无 gold 材料（repair_rate=None）→ 保守 0（不可证正确）。
    """
    if final_state is None:
        return 0
    try:
        from experiments._m1_metrics import _compute_repair_rate as _impl

        val = _impl(task, final_state)
        return 1 if val == 1.0 else 0
    except Exception:
        return 0


def _repair_history_public(final_state: dict[str, Any] | None) -> list[dict[str, Any]]:
    """P0-2：repair_history 的**可落盘投影**（仅保留可序列化标量）。

    此前该键从不落盘，导致 `patch_plausible` 无法复核（外部评审 §3.5.4）。
    投影只保留标量字段，避免把大对象写进结果行；非标量字段丢弃并在
    `patch_plausible_evidence` 中标注。
    """
    if not final_state:
        return []
    history = final_state.get("repair_history") or []
    out: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        row: dict[str, Any] = {}
        for key, val in item.items():
            if isinstance(val, str | int | float | bool) or val is None:
                row[str(key)] = val
            elif isinstance(val, list):
                row[str(key)] = [str(v)[:200] for v in val[:20]]
        out.append(row)
    return out


def _patch_plausible_evidence(final_state: dict[str, Any] | None) -> dict[str, Any]:
    """P0-2：`patch_plausible` 的判据证据（供事后逐行复核）。

    返回：`has_patch` / `history_len` / `last_patch_applied` / `basis`。
    `basis` 取值：`no_patch`（无补丁文本）/ `no_history`（未进 patch_applier）
    / `applied`（写盘成功）/ `rejected`（写盘被拒）。
    """
    if final_state is None:
        return {"has_patch": False, "history_len": 0, "last_patch_applied": None, "basis": "no_state"}
    has_patch = bool(str(final_state.get("patch") or "").strip())
    history = final_state.get("repair_history") or []
    last_applied: bool | None = None
    if history and isinstance(history[-1], dict):
        raw = history[-1].get("patch_applied")
        last_applied = bool(raw) if raw is not None else None
    # 修正（2026-10-11）：plausible 口径为"**任一**迭代写盘成功"，
    # 因此证据须同时透出"是否曾成功"，否则无法区分
    # ① 从未写盘成功（rejected）与 ② 早期成功、末条被拒（applied_then_rejected）。
    ever_applied = any(bool(h.get("patch_applied")) for h in history if isinstance(h, dict))
    if not has_patch:
        basis = "no_patch"
    elif not history:
        basis = "no_history"
    elif last_applied:
        basis = "applied"
    elif ever_applied:
        basis = "applied_then_rejected"
    else:
        basis = "rejected"
    return {
        "has_patch": has_patch,
        "history_len": len(history),
        "last_patch_applied": last_applied,
        "ever_patch_applied": ever_applied,
        "basis": basis,
    }


def _patch_plausible_invariant_violation(task: Any, final_state: dict[str, Any] | None) -> bool:
    """P0-2 不变量观测：`correct=1` 但 `plausible=0` 即记账缺陷。

    该组合在语义上不可能（补丁被 gold 裁决通过 ⇒ 必然已写盘成功），
    实测存量工件出现 129 行（外部评审 §11 C-7）。本字段把违反显式落盘，
    以便：① 新批次可直接统计；② 与存量工件的 129 行对照。
    """
    try:
        return bool(_patch_correct(task, final_state) == 1 and _patch_plausible(final_state) == 0)
    except Exception:
        return False


def _patch_precision(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """R53：补丁精确率 = correct / plausible（plausible=0 时 None，避免除零）。"""
    plausible = _patch_plausible(final_state)
    if plausible == 0:
        return None
    return _patch_correct(task, final_state) / plausible


def _test_hacking_result(task: Any, final_state: dict[str, Any] | None) -> dict[str, Any]:
    """批次 VIII（ADR-0022 观测层）：test-hacking 确定性检测。

    补丁后代码经 _target_code_after_patch（批次 VII 修正口径）与原码做
    AST 差集——只看补丁新引入的硬编码输入分支 / 断言删除 / 吞异常。
    无补丁 / 无原码 / 解析失败 → {"suspected": False, "signals": []}
    （保守降级，与弃权门口径一致）。
    """
    empty = {"suspected": False, "signals": []}
    if final_state is None:
        return empty
    patch = final_state.get("patch") or ""
    if not str(patch).strip():
        return empty
    original_code = str(getattr(task, "instance_code", "") or "")
    if not original_code.strip():
        return empty
    try:
        from experiments._m1_metrics import _target_code_after_patch
        from src.tools.patch_test_hacking import detect_test_hacking

        patched = _target_code_after_patch(original_code, patch)
        return detect_test_hacking(original_code, patched)
    except Exception:  # —— 检测异常不阻断结果行组装
        return empty


def _fl_at_k(final_state: dict[str, Any] | None, task: Any = None) -> dict[str, Any] | None:
    """R8（2026-09-30 独立审查 N7，P1）：FL@1/3/5 定位命中指标（FL@1/3/5）。

    口径：fl_spectral_focus 非空时，取**真实缺陷行**是否落在 Top-k 的命中
    情况。真实缺陷行的提取优先级（E2-iter 修复，2026-10-07）：
    1. **gold diff**（R8 设计口径，docstring 既有承诺）：buggy 代码与
       gold fixed 代码的 SequenceMatcher 差异行（buggy 侧 1-based 行号——
       fl Top-k 行号即 buggy 代码行号，两轴一致）；有 gold 材料的合成任务
       （repair=0 主力人群）由此**首次可测**；
    2. fallback：系统补丁的 diff 变更行（真实仓库无 gold 场景；整文件
       替换口径下解析不出行号 → None，历史口径）。
    无 fl_spectral_focus（O2 关 / 测量失败 / 无 debugger 路径）或两路
    均无 diff 行时返回 None（保持键集合同构，统计层按"不可测"处理）。

    E2 实证根因（0/174 全空）：实现原只走第 2 路——synthetic 任务的
    patch 是整文件替换文本（非 unified diff）恒解析为空，且修复失败
    任务（patch 本就为空）同样被排除，使 fl 分母在 gold 材料齐备的
    合成集上结构性为空。
    """
    if final_state is None:
        return None
    focus = final_state.get("fl_spectral_focus")
    if not focus or not focus.get("top_k"):
        return None
    top_k = focus.get("top_k", [])
    ranked_lines = [item.get("line") for item in top_k]
    diff_lines: list[int] = []
    if task is not None:
        try:
            from experiments._m1_metrics import _gold_fixed_code as _gold_fixed

            fixed_code = _gold_fixed(task)
            buggy_code = str(getattr(task, "instance_code", "") or "")
            if fixed_code.strip() and buggy_code.strip():
                import difflib

                sm = difflib.SequenceMatcher(a=buggy_code.splitlines(), b=fixed_code.splitlines(), autojunk=False)
                defect_set: set[int] = set()
                for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
                    if tag in ("delete", "replace"):
                        defect_set.update(range(i1 + 1, i2 + 1))
                diff_lines = sorted(defect_set)
        except Exception:
            diff_lines = []
    if not diff_lines:
        # fallback：系统补丁 diff 行（真实仓库无 gold 场景，历史口径）
        patch = final_state.get("patch") or ""
        diff_lines = _extract_diff_line_numbers(patch)
    if not diff_lines:
        return None
    diff_set = set(diff_lines)
    result: dict[str, Any] = {}
    for k in (1, 3, 5):
        top_set = set(ranked_lines[:k])
        hit = len(top_set & diff_set)
        result[f"fl_at_{k}"] = 1.0 if hit > 0 else 0.0
    return result


def _localization_hit_function(task: Any, final_state: dict[str, Any] | None) -> bool | None:
    """修复引擎第一阶段：函数级局部化命中（局部化独立指标口径）。

    LLM 推理定位（state["llm_localization"]）的 function_name 是否落在
    gold 变更函数集合（buggy vs gold fixed 的 diff 行 → AST 所属函数）。
    None = 未定位 / 无 gold 材料（保守不可测，键集合同构占位）。
    """
    if final_state is None:
        return None
    loc = final_state.get("llm_localization")
    if not loc:
        return None
    try:
        from experiments._m1_metrics import _gold_fixed_code as _gold_fixed
        from src.agents.fault_localizer import gold_changed_functions, localization_hit

        fixed_code = _gold_fixed(task)
        buggy_code = str(getattr(task, "instance_code", "") or "")
        if not fixed_code.strip() or not buggy_code.strip():
            return None
        return localization_hit(loc, gold_changed_functions(buggy_code, fixed_code)).get("localization_hit_function")
    except Exception:
        return None


def _localization_rank_metrics(task: Any, final_state: dict[str, Any] | None) -> dict[str, Any] | None:
    """修复引擎批次 II：元素级 Top-3 命中与 MRR（RGFL 排序评测口径）。

    与 _localization_hit_function 同 gold 口径（buggy vs gold fixed 的
    diff 行 → AST 所属函数集合），消费 state["llm_localization"]["candidates"]
    （批次 II 起 localize 输出 1~3 个排序候选；旧 schema 无 candidates 时
    在 localization_rank_metrics 内退化为单候选）。
    None = 未定位 / 无 gold 材料（不可测，键集合同构占位）。
    """
    if final_state is None:
        return None
    loc = final_state.get("llm_localization")
    if not loc:
        return None
    try:
        from experiments._m1_metrics import _gold_fixed_code as _gold_fixed
        from src.agents.fault_localizer import gold_changed_functions, localization_rank_metrics

        fixed_code = _gold_fixed(task)
        buggy_code = str(getattr(task, "instance_code", "") or "")
        if not fixed_code.strip() or not buggy_code.strip():
            return None
        return localization_rank_metrics(loc, gold_changed_functions(buggy_code, fixed_code))
    except Exception:
        return None


def _fl_constraint_result(task: Any, final_state: dict[str, Any] | None) -> dict[str, Any]:
    """修复引擎批次 XIV（ADR-0028 观测层）：FL Top-k 约束门结果。

    问题口径（外部报告 P0-3 净新增）："补丁是否真的修改了定位候选
    位置之一"——定位命中但补丁改在别处 = 定位信号被合成侧浪费
    （ADR-0024"生成侧主导"假设的行级验证器）。补丁后代码经
    _target_code_after_patch（批次 VII 修正口径）与原码做 diff →
    AST 函数归属（patch_changed_functions，含纯插入锚定），与
    state["llm_localization"] Top-3 候选求交（fl_constraint_verdict）。

    Returns:
        {"verdict": "hit" | "miss" | "not_evaluable", "hit_rank": int | None,
         "changed_functions": [str, ...]}；not_evaluable = 无定位 / 无补丁 /
         无原码 / 变更集合为空（保守降级，与 test-hacking 门口径一致）。

    已知局限（ADR-0028 登记）：整文件重写补丁的变更集合 ≈ 全文件函数，
    判定近乎恒 hit（无约束力）——约束力集中在局部编辑通道
    （EDIT_INTENT / 函数级补丁）。观测层零行为影响（passed 历史口径
    不变）；阻断档转正判据见 ADR-0028。
    """
    empty: dict[str, Any] = {"verdict": "not_evaluable", "hit_rank": None, "changed_functions": []}
    if final_state is None:
        return empty
    patch = str(final_state.get("patch") or "")
    if not patch.strip():
        return empty
    loc = final_state.get("llm_localization")
    if not loc:
        return empty
    original_code = str(getattr(task, "instance_code", "") or "")
    if not original_code.strip():
        return empty
    try:
        from experiments._m1_metrics import _target_code_after_patch
        from src.agents.fault_localizer import fl_constraint_verdict, patch_changed_functions

        patched = _target_code_after_patch(original_code, patch)
        changed = patch_changed_functions(original_code, patched)
        verdict = fl_constraint_verdict(loc, changed)
        if verdict is None:
            return empty
        return verdict
    except Exception:  # —— 观测异常不阻断结果行组装
        return empty


def _self_repair_trap_result(final_state: dict[str, Any] | None) -> dict[str, Any]:
    """修复引擎批次 XIV（ADR-0028 观测层）：Self-Repair Trap 判定。

    消费 state["oracle_quality_history"]（Generator 每次产出测试后的
    质量快照序列）跑 detect_self_repair_trap 三信号判定核（DCAware
    "迭代自修复驱使断言退化"风险口径；最新快照不可解析时不冒充退化）。

    Returns:
        {"suspected": bool, "signals": [str, ...]}；无历史 / 结构异常 →
        不怀疑（保守，与 test-hacking / 弃权门降级口径一致）。
    """
    empty: dict[str, Any] = {"suspected": False, "signals": []}
    if final_state is None:
        return empty
    history = final_state.get("oracle_quality_history")
    if not isinstance(history, list):
        return empty
    try:
        from src.tools.self_repair_trap import detect_self_repair_trap

        return detect_self_repair_trap(history)
    except Exception:  # —— 观测异常不阻断结果行组装
        return empty


def _extract_diff_line_numbers(patch_text: str) -> list[int]:
    """从 unified diff / 补丁文本中提取 new 侧变更行号（保守口径）。

    E2-iter 修复（2026-10-07）：原实现把 patch 文本单参数传入
    patch_evidence._patch_changed_lines（签名为 original/new 两参）——
    TypeError 被裸 except 吞掉**恒返回空列表**，本函数自诞生起从未
    成功解析过任何 diff。现直接解析 unified diff 文本（@@ 起始行 +
    "+" 行计数，与 _patch_changed_lines 同口径）；非 diff 格式补丁
    （如整文件替换文本）无 @@ → new_line 恒 0 → 空列表（语义不变）。
    """
    if not patch_text or not patch_text.strip():
        return []
    changed: list[int] = []
    new_line = 0
    try:
        for line in patch_text.splitlines():
            if line.startswith(("---", "+++")):
                continue
            if line.startswith("@@"):
                try:
                    plus_part = line.split("+", 2)[1]
                    new_line = int(plus_part.split(",")[0].strip())
                except (IndexError, ValueError):
                    new_line = 0
                continue
            if line.startswith("+"):
                if new_line > 0:
                    changed.append(new_line)
                    new_line += 1
            elif line.startswith("-"):
                continue
            elif new_line > 0:
                new_line += 1
        return sorted(set(changed))
    except Exception:
        return []


def _check_swe_bench_p2p_gate(task: BenchmarkTask) -> dict[str, Any] | None:
    """M3（2026-09-29 审查 P0 + D.4-7）/ R46（2026-09-30 独立审查 P0）：
    SWE-bench 实例可解性前置门禁（**默认开启**）。

    R46 起 SWE-bench 批次默认执行本门禁（SWE_BENCH_P2P_GATE_ENABLE 缺省
    "true"）：调用 scripts/tools/verify_instance_solvable.verify_single_instance
    验证基线 PASS_TO_PASS ≥ SWE_BENCH_P2P_GATE_THRESHOLD；不可解实例返回
    {"harness_invalid": True, ...} 供调用方标记并剔除（不计入"0 解出"
    统计，还原为"harness 无效"而非"系统无效"）。
    设 SWE_BENCH_P2P_GATE_ENABLE=false 可显式退回关闭（消融 / 无 verify 脚本）。

    合成数据集 / examples 任务无 repo_url/base_commit 元数据，永不命中，
    历史口径零变化。

    Returns:
        不可解时返回 {"harness_invalid": True, "error_type": str, "details": dict}；
        可解或未启用门禁时返回 None。
    """
    if not SWE_BENCH_P2P_GATE_ENABLE:
        return None
    meta = task.metadata or {}
    repo_url = meta.get("repo_url", "")
    base_commit = meta.get("base_commit", "")
    if meta.get("source") != "swe_bench" or not repo_url or not base_commit:
        return None
    try:
        from scripts.tools.verify_instance_solvable import verify_single_instance
    except ImportError:
        logger.warning("M3 P2P 门禁：verify_single_instance 不可用，跳过门禁检查")
        return None
    fail_to_pass = meta.get("fail_to_pass") or []
    pass_to_pass = meta.get("pass_to_pass") or []
    gold_patch = meta.get("golden_patch") or ""
    test_patch = meta.get("test_patch") or ""
    logger.info("M3 P2P 门禁：验证任务 %s 可解性（P2P 阈值 %.2f）", task.task_id, SWE_BENCH_P2P_GATE_THRESHOLD)
    result = verify_single_instance(
        repo_url=repo_url,
        base_commit=base_commit,
        gold_patch=gold_patch,
        test_patch=test_patch,
        fail_to_pass=fail_to_pass,
        pass_to_pass=pass_to_pass,
        p2p_gate_threshold=SWE_BENCH_P2P_GATE_THRESHOLD,
    )
    if not result["solvable"]:
        logger.warning(
            "M3 P2P 门禁：任务 %s 不可解（%s），标记 harness_invalid 剔除",
            task.task_id,
            result.get("error_type"),
        )
        return {
            "harness_invalid": True,
            "error_type": result.get("error_type", "unknown"),
            "details": result.get("details", {}),
        }
    logger.info("M3 P2P 门禁：任务 %s 可解，继续执行", task.task_id)
    return None


def _failure_attribution_for_result(final_state: dict[str, Any] | None) -> dict[str, Any]:
    """构建单任务结果行的终局失效归因（I1，2026-10-16；纯观测，零 LLM）。

    接线动机：`observability.failure_taxonomy.annotate_final_state` 自 U11
    （2026-10-05）落地以来**没有任何生产调用点**——五个终局桶与批次 XII 的
    edge × fault_side 增补维度只在单测里被断言，批次工件与报表一处都不落，
    "失败发生在哪个环节、属于哪类协作/能力失效"因此无法从工件复算（登记册
    §4 "G 轮新登记"条：修键路径是必要非充分，末端不落盘则分布不产出）。

    喂入口径（annotate_final_state docstring 的 G3 限定）：该函数读的是**状态
    通道顶层键**，而结果行是投影——成功键叫 `passed`，且 `stop_reason` 必须经
    `effective_stop_reason` 兜底（O35：条件边函数原地写入的 stop_reason 不被
    LangGraph 回写，直读恒 None）。故此处按权威值重建状态视图再喂入；直接把
    final_state 丢进去会让**失败任务全部落 UNCATEGORIZED**（stop_reason 恒空），
    把"归因未接线"伪装成"系统失效无法分类"。

    Returns:
        {"failure_bucket": str | None, "failure_bucket_detail": str | None,
         "attribution_edge": str | None, "attribution_fault_side": str | None}。
        final_state 为 None（运行异常 / 限流耗尽，无工作流终局）时四键全 None：
        那不是 UNCATEGORIZED 的语义（"状态信息不足"），而是**根本没有终局状态**
        可分类；折进兜底桶会让桶分布的分母失去意义，故由
        _aggregate_failure_buckets 单列 unclassified_rows 计数（缺席不等于消失）。
    """
    if final_state is None:
        return {
            "failure_bucket": None,
            "failure_bucket_detail": None,
            "attribution_edge": None,
            "attribution_fault_side": None,
        }
    annotation = annotate_final_state(
        {
            "test_passed": bool(final_state.get("test_passed")),
            # 与结果行 "stop_reason" 同源（effective_stop_reason），避免两处口径漂移
            "stop_reason": effective_stop_reason(final_state),
            "budget_exceeded": final_state.get("budget_exceeded"),
            "regression_detected": final_state.get("regression_detected"),
            "logic_degraded": final_state.get("logic_degraded"),
        }
    )
    return {
        "failure_bucket": annotation["bucket"].value,
        "failure_bucket_detail": annotation["detail"],
        "attribution_edge": annotation["edge"],
        "attribution_fault_side": annotation["fault_side"],
    }


def _aggregate_failure_buckets(bl_results: list[dict[str, Any]]) -> dict[str, Any]:
    """聚合一个基线的**终局失效桶**分布（I1，2026-10-16）。

    与 failure_category_distribution 的分工：后者统计 error_category
    （18 类任务侧错误分类，只覆盖失败任务），本项统计 annotate_final_state
    的五桶终局归类 + 批次 XII 的 edge × fault_side 增补维度（**含收敛任务**，
    分母是全部有终局状态的行）。两者互补：一个回答"错在哪类异常"，
    一个回答"失效发生在哪个环节、故障侧指向 model 还是 harness"。

    输出形状与 failure_taxonomy.summarize_batch 同构（counts / shares /
    fault_side_counts / edge_counts / total），故 render_markdown 可直接
    消费本 dict 渲染报告层表格；额外两键 total_rows / unclassified_rows
    把分母口径显式化——运行异常行（无工作流终局状态）单列计数而**不**折进
    uncategorized 桶，否则"归因未接线"与"状态信息不足"会同形。

    位置说明：本函数与下列 rag/token/failure_categories 三个聚合同样为模块级
    （J-1b，2026-10-17 由 `run_benchmark()` 嵌套函数外提，行为逐字节不变）——
    分母口径（total vs total_rows）是本类指标唯一容易读错的地方，必须可测。
    """
    counts = dict.fromkeys((b.value for b in FailureBucket), 0)
    fault_side_counts = dict.fromkeys(FAULT_SIDES, 0)
    edge_counts = dict.fromkeys(INTERACTION_EDGES, 0)
    unclassified_rows = 0
    for r in bl_results:
        bucket = r.get("failure_bucket")
        if bucket is None:
            unclassified_rows += 1
            continue
        counts[bucket] = counts.get(bucket, 0) + 1
        side = r.get("attribution_fault_side")
        if side in fault_side_counts:
            fault_side_counts[side] += 1
        edge = r.get("attribution_edge")
        if edge in edge_counts:
            edge_counts[edge] += 1
    classified = len(bl_results) - unclassified_rows
    return {
        "total": classified,
        "total_rows": len(bl_results),
        "unclassified_rows": unclassified_rows,
        "counts": counts,
        "shares": {k: (round(v / classified, 4) if classified else 0.0) for k, v in counts.items()},
        "fault_side_counts": fault_side_counts,
        "edge_counts": edge_counts,
    }


def _aggregate_rag_metrics(bl_results: list[dict[str, Any]]) -> dict[str, Any]:
    """聚合一个基线的 RAG 检索质量指标（P1：RAG 消融数据）。

    - hit_rate: 检索命中（返回 ≥1 个参考案例）的检索占比；
    - avg_max_similarity: 各次检索最高相似度的平均值（检索质量代理指标）。

    Returns:
        {"retrievals": int, "hits": int, "hit_rate": float, "avg_max_similarity": float}
    """
    all_stats = [s for r in bl_results for s in (r.get("rag_stats") or [])]
    if not all_stats:
        return {"retrievals": 0, "hits": 0, "hit_rate": 0.0, "avg_max_similarity": None}
    hits = sum(1 for s in all_stats if s.get("results", 0) > 0)
    sim_values = [s.get("max_similarity") for s in all_stats if s.get("max_similarity") is not None]
    return {
        "retrievals": len(all_stats),
        "hits": hits,
        "hit_rate": round(hits / len(all_stats), 4),
        "avg_max_similarity": round(sum(sim_values) / len(sim_values), 4) if sim_values else None,
    }


def _token_efficiency_texts(metrics: Any) -> tuple[str, str, list[str]]:
    """终端 token 效率两行主体 + 不可读机制（AX，2026-10-21）。

    `token_metrics` 是 AN 写盘的聚合对象：字段在场 `None` 是上游拒绝
    （AT 的写拒绝 / AN 的不给部分和），缺席按 AE2 历史 0。此前终端行用
    `%d` / `%.2f` 直出，一个被拒绝的字段会让整轮基准在跑完后的汇总处抛
    `TypeError`。返回 `(日志行主体, 进度行主体, 去重机制名)`。
    """
    total = token_metric_reading(metrics, "total_tokens")
    avg = token_metric_reading(metrics, "avg_tokens_per_task", allow_float=True)
    calls = token_metric_reading(metrics, "total_llm_calls")
    reasons = list(
        dict.fromkeys(
            code for reading in (total, avg, calls) if reading["value"] is None for code in reading["reasons"]
        )
    )
    total_text = "不可读" if total["value"] is None else str(total["value"])
    avg_text = "不可读" if avg["value"] is None else str(avg["value"])
    avg_fixed = "不可读" if avg["value"] is None else f"{avg['value']:.2f}"
    calls_text = "不可读" if calls["value"] is None else str(calls["value"])
    return (
        f"总tokens={total_text}, 平均每任务tokens={avg_fixed}, LLM调用次数={calls_text}",
        f"平均每任务Token: {avg_text}, LLM调用次数: {calls_text}",
        reasons,
    )


def _aggregate_token_metrics(bl_results: list[dict[str, Any]]) -> dict[str, Any]:
    """聚合一个基线的 token 消耗（P0-2：多智能体系统 vs Plain LLM 性价比对比）。

    AD1（2026-10-06 输出成本控制）新增 output_share_pct / avg_output_per_task /
    avg_output_per_call——输出 token 单价约为输入命中缓存的 10 倍以上
    （DeepSeek 口径），输出占比是成本结构的首要指标（R-P0-2 实测
    aitester 臂输出占 78%）。

    AN（2026-10-21）：逐行读数交给 `aggregate_row_token_usage`（与可信报告 /
    旧批次兜底同一份策略）。整键缺席按历史 0；在场坏值让对应总量为 None
    （不折 0、不给部分和）；拆分矛盾只披露（token 总量仍取行内真值）；缓存
    半套 / 坏值让缓存读数为 None。披露键只在真发生时写入 ⇒ 干净批次的
    `token_metrics` 返回域逐键不变（真批次 783 行复算与已落值一致）。

    缓存指标口径：
        cache_hit_rate = 命中 / (命中 + 真实调用)——缓存命中率是成本首要指标
        （前沿：缓存命中率 0%→94% 产生 9 倍成本差异，超过模型层级差异）。
        uncached_theoretical_tokens = 真实 + 避免——还原"无缓存理论成本"，
        消除"缓存命中率漂移导致 $/token 结论不可比"的系统性偏差。
    """
    agg = aggregate_row_token_usage(bl_results)
    total_input = agg["input_tokens"]
    total_output = agg["output_tokens"]
    total_tokens = agg["total_tokens"]
    total_calls = agg["llm_calls"]
    cache = agg["cache"]
    if cache["present"]:
        total_cache_hits = cache["hits"]
        total_cache_avoided = cache["avoided"]
    else:
        # 旧 schema 整批无缓存字段：历史 0（AJ：缓存披露键只在真发生时写入）。
        total_cache_hits = 0
        total_cache_avoided = 0
    total = agg["n_rows"]

    if total_cache_hits is None or total_calls is None:
        cache_hit_rate: float | None = None
    elif total_cache_hits + total_calls > 0:
        cache_hit_rate = round(total_cache_hits / (total_cache_hits + total_calls) * 100, 2)
    else:
        cache_hit_rate = 0.0
    uncached = None if total_tokens is None or total_cache_avoided is None else total_tokens + total_cache_avoided
    avg_tokens_per_task = None if total_tokens is None else (round(total_tokens / total, 2) if total > 0 else 0)
    if total_input is None or total_output is None:
        output_share: float | None = None
    elif total_input + total_output > 0:
        output_share = round(total_output / (total_input + total_output) * 100, 2)
    else:
        output_share = 0.0
    avg_output_per_task = None if total_output is None else (round(total_output / total, 2) if total > 0 else 0)
    avg_output_per_call = (
        None
        if total_output is None or total_calls is None
        else (round(total_output / total_calls, 2) if total_calls > 0 else 0)
    )

    metrics: dict[str, Any] = {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_tokens,
        "total_llm_calls": total_calls,
        "total_cache_hits": total_cache_hits,
        "total_cache_avoided_tokens": total_cache_avoided,
        "cache_hit_rate_pct": cache_hit_rate,
        "uncached_theoretical_tokens": uncached,
        "avg_tokens_per_task": avg_tokens_per_task,
        # AD1：输出成本结构观测（键集合同构，纯新增）
        "output_share_pct": output_share,
        "avg_output_per_task": avg_output_per_task,
        "avg_output_per_call": avg_output_per_call,
    }
    if agg["n_unreadable_rows"]:
        metrics["n_token_unreadable_rows"] = agg["n_unreadable_rows"]
        metrics["token_reading_reasons"] = agg["reading_reasons"]
    if agg["n_contradiction_rows"]:
        metrics["n_token_split_mismatch_rows"] = agg["n_contradiction_rows"]
    if cache["present"] and not cache["complete"]:
        metrics["cache_reading_reasons"] = {**cache["missing"], **cache["reasons"]}
    return metrics


def _aggregate_failure_categories(bl_results: list[dict[str, Any]]) -> dict[str, int]:
    """聚合一个基线的失败原因分布（2.2 公平性 + 1.2 细化类别可单独计数）。

    仅统计失败任务的 error_category（"rate_limit"/"error" 占位值同样计入，
    便于区分"API 故障"与"真实错误类别"）；成功任务无 error_category，不计入。
    """
    counter: dict[str, int] = {}
    for r in bl_results:
        if not r.get("passed") and r.get("error_category"):
            counter[r["error_category"]] = counter.get(r["error_category"], 0) + 1
    return dict(sorted(counter.items(), key=lambda kv: kv[1], reverse=True))


def _cross_file_audit_fields(final_state: dict[str, Any] | None) -> dict[str, Any]:
    """D3（N-5，2026-10-17）：跨文件结果行审计字段（成功/失败分支键位一致）。

    N-4 item03 实测：synthetic level3 跨文件任务的结果行**不含**
    `cross_file_deps`（只在 `_dump_state_artifacts` 的 raw 落盘），跨文件修复
    路径是否被触达/依赖图是否为空**无法从批次工件逐行审计**。现新增三键
    （纯观测，不改判分口径、不改既有键）：

    - ``cross_file_enabled``：本行运行时 `CROSS_FILE_ENABLE` 是否开启
      （bool；读取异常时 None，不阻断结果构造）；
    - ``cross_file_deps``：终态依赖边列表（成功分支取 state；失败分支/无状态
      为 None——失败分支本来就没有工作流终态，不臆造空列表）；
    - ``cross_file_plan_present``：终态是否产出多文件修复计划
      （`cross_file_plan` 非空；失败分支恒 False）。

    Args:
        final_state: 基线运行结束后的工作流状态；None 表示失败分支（无终态）。

    Returns:
        含三键的 dict（直接 ** 展开进结果行，成功/失败分支键集一致）。
    """
    enabled: bool | None
    try:
        from src.tools.cross_file import cross_file_enabled as _cross_file_enabled

        enabled = bool(_cross_file_enabled())
    except Exception:  # pragma: no cover - 极端 import 异常：显式 None（不阻断行构造）
        enabled = None
    if final_state is None:
        return {
            "cross_file_enabled": enabled,
            "cross_file_deps": None,
            "cross_file_plan_present": False,
        }
    deps = final_state.get("cross_file_deps")
    plan = final_state.get("cross_file_plan")
    return {
        "cross_file_enabled": enabled,
        "cross_file_deps": deps if isinstance(deps, list) else None,
        "cross_file_plan_present": bool(plan),
    }


def _build_task_result(
    task: BenchmarkTask,
    elapsed: float,
    final_state: dict[str, Any] | None = None,
    diagnosis: str = "",
    error_category: str = "",
    golden_patches: dict[str, str] | None = None,
    harness_invalid: bool = False,
) -> dict[str, Any]:
    """构建单基线运行的结果字典（单一构造点，供成功/限流重试/异常三分支复用）。

    此前三个分支各写一份同构字典，新增指标字段（如 token_metrics/rag_metrics）
    需同步改三处，极易漏改导致 JSON 结果结构漂移；统一经此函数构建后，
    字段口径只有一处。

    Args:
        task: 基准测试任务。
        elapsed: 本次基线运行耗时（秒），内部 round(…, 2) 落盘。
        final_state: 基线运行结束后的工作流状态；None 表示运行失败
            （无最终状态），此时 passed/coverage/iterations/rag_stats 记占位值，
            diagnosis/error_category 用传入值。
        diagnosis: 失败分支的诊断说明（如 "执行异常: …"）。
        error_category: 失败分支的错误类别（"rate_limit" / "error"）。
        harness_invalid: M3 门禁：基线 P2P 不达标标记（不计入"0 解出"统计）。

    Returns:
        结果字典（结构见 run_single_task 各分支的原始实现，字段完全一致）。
    """
    if final_state is not None:
        # 1.1 状态细化：失败任务按 repair_history / rag_stats 信号补两类
        # 专属失败类别（补丁被安全守卫拒绝 / RAG 检索全空），供失败分布
        # 统计区分"修复失败"与"补丁不安全"、"RAG 失效场景"
        from src.agents.error_classifier import refine_final_error_category

        error_category = refine_final_error_category(final_state)
        # 修复引擎批次 II：元素级排序指标（Top-3 命中 + MRR）单次计算，
        # 下方结果行两键共享（gold 提取与 diff/AST 解析不重复执行）
        _loc_rank = _localization_rank_metrics(task, final_state) or {}
        # 修复引擎批次 XIV（ADR-0028 观测层）：约束门与陷阱判定单次计算，
        # 下方结果行共享（观测异常在 helper 内降级，不阻断组装）
        _fl_constraint = _fl_constraint_result(task, final_state)
        _trap = _self_repair_trap_result(final_state)
        # I1（2026-10-16）：终局失效归因单次计算，下方结果行四键共享
        _attribution = _failure_attribution_for_result(final_state)
        # N-3（2026-10-17，A-05 后续修复）：独立判读两键**单次计算**——
        #   - detection_rate 语义收敛为 LLM-suite（排除 oracle 测试名执行）；
        #   - oracle_suite_verdict 由 oracle 测试单独运行判定（oracle 失败不再
        #     改写 LLM 检出结论；无 oracle 注入时恒 "unavailable" 且零额外子进程）。
        # 复用同一计算值避免重复 pytest 子进程（两者共享 M1 gold 材料路径）。
        _llm_suite_detection = _compute_detection_rate(task, final_state)
        _oracle_suite_verdict = _compute_oracle_suite_verdict(task, final_state)
        return {
            "task_id": task.task_id,
            "repo": task.repo_name,
            "passed": final_state.get("test_passed", False),
            "coverage": final_state.get("coverage_report") or 0.0,
            "iterations": final_state.get("iteration", 0),
            "diagnosis": final_state.get("diagnosis", ""),
            "error_category": error_category,
            "elapsed_seconds": round(elapsed, 2),
            # P0-2 效率指标：单次基线运行的 token 消耗（性价比对比依据）
            "token_usage": token_usage.get_usage().as_dict(),
            # P1 RAG 检索质量：本基线累计的检索指标（未启用 RAG 时为空）
            "rag_stats": final_state.get("rag_stats"),
            # 2.1 数据污染检测：系统最终生成的补丁（无修复动作时可能为空）
            "patch": final_state.get("patch"),
            # 1.2 变异得分：保留生成测试代码，供 compute_mutation_score 复用
            # （此前 generated_test 仅经 --save-state 落盘 raw/，标准结果 JSON
            # 不携带；1.2 接线后需把字段写进 details[]，让 mutation_score 计算
            # 与 analyze_results._mutation_score_metrics 都能直接消费）
            "generated_test": final_state.get("generated_test"),
            # 3.2 执行反馈轨迹：逐轮执行的通过/覆盖率变化/耗时与奖励信号
            # （executor 节点默认常开写入；旧状态缺失时以 None 兜底保持键集合同构）
            "execution_trace": final_state.get("execution_trace"),
            # 1.3 命名契约符号守卫（守卫拒绝时 _patch_applier_node 写入）
            "contract_missing_symbols": final_state.get("contract_missing_symbols"),
            # BL 轮（2026-10-22）：上一行的**读法**。contract_missing_symbols=null
            # 在 contract_status≠ok 时只表示"没比出符号差异"，不是"契约成立"；
            # 两个键必须一起落盘，否则归档里这两种情形折叠成同一件事（实测归档
            # 8865 处 contract_missing_symbols 全是 None，历史无法回溯区分）。
            "contract_status": final_state.get("contract_status"),
            # BN 轮（2026-10-22）：另外三条静态预检通道的"读法"随值落盘。
            # static/safety/oracle 的 status+outcomes 此前**两道落盘边界都不在**
            # （5 种运行时态折成 1 种行形状，逐字节同形），结果行只带了
            # contract_status 一条腿；findings 类键（type_repair_findings /
            # oracle_findings）为空时的四种成因因此无法从工件区分。
            # 纯新增列：passed / coverage / stop_reason 等判分字段一个不动。
            "static_check_status": final_state.get("static_check_status"),
            "static_check_outcomes": final_state.get("static_check_outcomes"),
            "safety_check_status": final_state.get("safety_check_status"),
            "safety_check_outcomes": final_state.get("safety_check_outcomes"),
            "oracle_check_status": final_state.get("oracle_check_status"),
            "oracle_check_outcomes": final_state.get("oracle_check_outcomes"),
            # 2.2 补丁后处理重采样统计（PATCH_RESAMPLE_ENABLE=true 时写入）
            "patch_resample_stats": final_state.get("patch_resample_stats"),
            # 五、多维度污染检测：对单任务计算 risk_level（high/medium/low/
            # unknown/not_applicable）（供 analyze_results 的 _contamination_cross_analysis
            # 消费；无黄金补丁材料时返回 "not_applicable"——N7 口径：检测
            # 不适用与"检测过且无重叠证据"的 "low" 区分；检测腿崩了返回
            # "unknown"——BM 轮：崩了不折成最有利档 "low"）
            "contamination_risk_level": _compute_contamination_risk_level(
                {"task_id": task.task_id, "patch": final_state.get("patch") or ""},
                golden_patches,
            ),
            # P0 仓库级验证诊断（仅 REPO_LEVEL_EXECUTION=true 且 SWE-bench 任务有；
            # 未启用 / 路由未命中时 final_state 无此键，get 返回 None 占位保持
            # 键集合同构，历史口径零变化）
            "repo_verification": final_state.get("repo_verification"),
            "task_metadata": task.metadata,
            # G2 风险分级人工回路（RISK_APPROVAL_ENABLE=true 时写入；默认关时
            # enabled=False 占位保持键集合同构，历史口径零变化）
            "risk_summary": _build_risk_summary_for_result(final_state),
            # M1（2026-09-29 审查 P0）：假通过标记 + gold 材料独立裁决三指标（自动化 oracle）。
            # test_regenerated_pass_unverified：M5 执行层标记（测试重生成后
            # 通过且源码未改 → 假成功通道），直接读 state 键（缺省 None）。
            "test_regenerated_pass_unverified": final_state.get("test_regenerated_pass_unverified"),
            # A16（2026-10-18 第三方评审 P1）：执行不稳定（fail→pass）证据行级透出
            # （_executor_node / single_agent helper 写入；历史批次缺键为 None，
            # 键集合同构）。flaky_unverified=True 时 M1 指标按不可测（None）处理。
            "flaky_unverified": final_state.get("flaky_unverified"),
            "flaky_detected": final_state.get("flaky_detected"),
            "flaky_pass_count": final_state.get("flaky_pass_count"),
            "flaky_total_count": final_state.get("flaky_total_count"),
            # W3（2026-10-05 审查落地·检出优先协议，DETECTION_FIRST_ENABLE 默认关）：
            # 首轮红灯观测 + 终态标注（red_then_green / all_green_unverified /
            # red_not_repaired——Y1 补失败终局：检出成功但未修复，评估层
            # detection 口径应计数）。默认关时恒 None（键集合同构，历史口径
            # 零变化）；评估层消费口径：all_green_unverified 的 passed 不得计为
            # "检出/修复成功"。
            "detection_first_red_seen": final_state.get("detection_first_red_seen"),
            "detection_first_status": final_state.get("detection_first_status"),
            # Y1（2026-10-05 X 批次冒烟补遗）：再生成计数透出——量化检出优先
            # 协议的 +1 LLM call 成本（协议开启时首轮全绿任务计 1；O4/诊断
            # 关键词路径同样累计）。协议关时恒 None（键集合同构）。
            "regeneration_count": final_state.get("regeneration_count"),
            # AB3（2026-10-06，R-P0-5 首块）：规约可编译率行级透出——
            # _generator_node 在 SPEC_IR_DSL_ENABLE=true 时把 SpecIR
            # invariant 子句可编译率写入 state（logic/scientific 档生效）。
            # 默认关恒 None（键集合同构，历史批次 JSON 向后兼容）；
            # 生死实验复审指出该缺口使规约 oracle 独立贡献无法评估。
            "spec_compile_rate": final_state.get("spec_compile_rate"),
            # P0-4（2026-10-10 独立审查）：确定性规约 oracle 的**注入可观测性**。
            # 此前 BASELINE.yaml:110-112 已在注释里"登记" spec_oracle_injected，
            # 但**从未出现在 metrics_schema、也从未在结果行产出**——是一个
            # "文档化了但未实现的指标"，导致"逻辑驱动通道是否真的注入"
            # 无法从任何工件观测（审查者只能靠在 generated_test 文本里找
            # `test_specir_v2_oracle` 这一脆弱手段；实测 QuixBugs FIXED 批
            # 18/50 行注入）。
            # 口径（三态，与 src/graph/nodes.py 的 _spec_oracle_injection_verdict 一致）：
            #   spec_oracle_injected: True=实际注入 / False=尝试但产物为空 /
            #     None=开关关或未尝试（历史默认口径，零行为变化）；
            #   spec_oracle_verdict: "not_attempted" / "compiled_empty" /
            #     "injected" / "injected_and_passed" / "injected_and_failed" /
            #     None。
            "spec_oracle_injected": final_state.get("spec_oracle_injected"),
            "spec_oracle_verdict": final_state.get("spec_oracle_verdict"),
            # Q-1（2026-10-18，示例通道生产接线）：examples 来源/条数审计。
            # source ∈ planner / spec_generator / none；count = 实际被 oracle
            # 使用的示例数（默认关恒 none/0，历史键位同构）。成功/失败分支
            # 键位一致（失败分支见下方 None 占位段）。
            **_spec_oracle_examples_fields(final_state),
            # P0-A-2（2026-10-12 独立评审落地，SPEC_REPLACE_AB_REPORT §5 建议）：
            # 规格优先替换段逐任务可审计观测——DETECTION_SPEC_MODE=replace 时
            # "attempted_replaced"（规约材料非空，规约文档实际替换了目标代码
            # 块注入 Generator）/ "attempted_fallback"（规约材料为空，渲染返
            # 回空串，prompt 保持历史口径注入目标代码）/ None（DETECTION_SPEC_MODE
            # 默认 off 或 minimal 消融档，历史口径零变化）。与 R1c 确定性 oracle
            # 执行注入（spec_oracle_injected，SPEC_ORACLE_EXEC_ENABLE）解耦——
            # 前者是 prompt 构建路径观测，后者是执行链 oracle 注入观测。
            "spec_replace_applied": final_state.get("spec_replace_applied"),
            # M-1（2026-10-17）：规格**增广**段逐任务可审计观测——
            # DETECTION_SPEC_MODE=augment 时 "attempted_augmented"（人类规格
            # 锚已并列追加在完整缺陷代码之后）/ "attempted_fallback"（无非空
            # 规格材料，渲染空串 → prompt 保持纯 df 代码口径）/ None（模式
            # 非 augment，历史口径零变化）。与 spec_replace_applied 互斥
            # （同一模式只写其一，另一恒 None），供实验层审计增广覆盖率。
            "spec_augment_applied": final_state.get("spec_augment_applied"),
            # AC1（2026-10-06 第十轮审查 T-P0-2）：表达式通道覆盖率——LLM 把
            # NL 规约形式化为 *_expr 子句的占比（与 compile_rate 的编译器
            # 接受率正交；默认关恒 None，键集合同构）。
            "spec_expr_coverage": final_state.get("spec_expr_coverage"),
            # T1（2026-10-11 独立评审落地）：规约**被拒原因分布**（纯观测、
            # 零 LLM）——把"可编译率恒 0"拆成 {natural_language /
            # unsupported_operator / unknown_name / parse_error / ...} 计数。
            # 动机：全量 1,607 行实测 spec_compile_rate 中位数 0.200、47.6%
            # 恒为 0，但"为何为 0"不可归因；真实 LLM 调用已定位根因是
            # planner 系统性产出自然语言规约。本键使"修提示 vs 扩文法"的
            # 取舍有据可依。默认关恒 None，键集合同构。
            "spec_reject_reasons": final_state.get("spec_reject_reasons"),
            # AC2（T-P0-4）：双门观测——特异性门终审（specific_red /
            # over_red / unavailable）与红回归门违规标记（True = 抹红被
            # 门拦截并恢复红证人）。默认关恒 None，键集合同构。
            "specificity_gate_verdict": final_state.get("specificity_gate_verdict"),
            "red_regression_violation": final_state.get("red_regression_violation"),
            # P0（2026-09-30 独立审查 N9/R33）：源码补丁证据门观测。
            # source_patched_unverified：本轮写盘无 gold/谱系定位证据（True）
            # 或有证据背书（False）；None = 本轮无补丁 / 证据门未触发。
            "source_patched_unverified": final_state.get("source_patched_unverified"),
            "patch_evidence_level": final_state.get("patch_evidence_level"),
            # T 轮 2026-10-18（O 轮登记项落地）：A-03 快照/P2P 回归/自动回滚
            # 观测字段逐行透出（纯观测，不参与路由——写点位
            # src/graph/nodes.py::_patch_applier_node，本行只做 state 投影）：
            #   patch_rollback_verdict: verified / regression_failed / no_oracle /
            #     regression_error / apply_failed / not_enabled；
            #     None = 本轮未走 _patch_applier_node（无补丁/未进入修复环），
            #     "回滚协议未执行"（与 not_enabled"开关关"区分）
            #   patch_rolled_back: True = 本轮补丁已被 P2P 回归失败自动回滚
            #     （磁盘恢复成功）；False = 执行过但未回滚；None = 未执行
            "patch_rollback_verdict": final_state.get("patch_rollback_verdict"),
            "patch_rolled_back": final_state.get("patch_rolled_back"),
            # M1 三指标（并行产出，不改变 passed 的历史口径）：
            #   detection_rate（生成测试能否让带缺陷代码变红）/
            #   repair_rate（gold 材料独立裁决（自动化 oracle，无人工参与）修复是否正确）/
            #   false_fix_rate（passed=True 但 gold 裁决失败的占比）
            # 计算依赖 gold test_cases / fixed（合成模板自带），无 gold 材料时
            # 以 None 占位保持键集合同构（历史结果 JSON 结构向后兼容）。
            # detection_rate 语义（N-3 起）= LLM-suite；两键同值，后者为显式口径名。
            "detection_rate": _llm_suite_detection,
            "llm_suite_detection_rate": _llm_suite_detection,
            # N-3：oracle 独立判定（correct/fp/silent/misguided/unavailable；
            # 未注入/材料缺失/超时 → unavailable，fail-closed 不臆测）。
            "oracle_suite_verdict": _oracle_suite_verdict,
            "repair_rate": _compute_repair_rate(task, final_state),
            "false_fix_rate": _compute_false_fix_rate(task, final_state),
            # 2026-09-30 独立审查 N1：测试执行错误率（坏测试直接防线，
            # 恒失败/收集错误测试不得记 detection=1.0 的占比观测）
            "test_error_rate": _compute_test_error_rate(task, final_state),
            # 2026-09-30 独立审查 R52（P0）：oracle 类型声明（APR 严谨性
            # 检查点 #2）——供读者判断结论强度：本系统的验收 oracle 是什么
            # 来源（自生成测试 / 增强测试 / 留出 gold / 人工），以及测试
            # 是否对系统自身可见（test_visible_to_system）。
            # 口径（保守、零 LLM 成本）：
            #   - oracle_type = "generated_test"（历史口径：验收以 LLM 生成
            #     的测试通过为准）；ORACLE_ENHANCE_ENABLE=true 时为
            #     "enhanced_generated_test"；
            #   - test_visible_to_system = True（生成测试由 Executor 直接
            #     执行并通过性作为验收信号——系统"看见"了测试）。
            #   repair_rate / false_fix_rate 为 gold 材料独立裁决通道（自动化 oracle），
            #   与自生成验收并行产出，不改变 passed 的历史口径。
            "oracle_type": _oracle_type_label(final_state),
            "test_visible_to_system": True,
            # 2026-09-30 独立审查 R53（P0）：补丁精确率框架
            # （"plausible 精确率 = correct / plausible" 是信息量最大的
            # 修正指标）。口径：
            #   - patch_plausible = 本轮有补丁产出且写盘成功（静态守卫通过）；
            #   - patch_correct = gold 材料独立裁决（自动化 oracle，无人工参与）通过（repair_rate == 1.0）；
            #   - patch_precision = correct / plausible（无 plausible 时 None）。
            # 供统计层"过拟合度量"消费（假修复 = plausible 但 correct=0）。
            "patch_plausible": _patch_plausible(final_state),
            "patch_correct": _patch_correct(task, final_state),
            "patch_precision": _patch_precision(task, final_state),
            # P0-2（2026-10-11 外部评审 §10）：repair_history 落盘。
            # 背景：patch_plausible 的判据是 repair_history[-1]["patch_applied"]，
            # 但该键在**全库 7,153 行结果中从未落盘**（0 次出现）→ ① 无法从
            # 任何工件复核 plausible；② 129 行出现 correct=1 ∧ plausible=0 的
            # 不变量违反且无从定位。现把写盘记录与两项派生观测一并透出。
            "repair_history": _repair_history_public(final_state),
            "patch_plausible_evidence": _patch_plausible_evidence(final_state),
            # 不变量观测：correct=1 但 plausible=0（应为 0 行；非 0 即记账缺陷）
            "patch_plausible_invariant_violation": _patch_plausible_invariant_violation(task, final_state),
            # MDO（2026-10-11 优化方案 v2 §3.1）：**政策无关**的变异判别力度量。
            # 与 mutation_score 的区别：① 判据是行为差异（非退出码）；
            # ② 触发/判别/崩溃三分；③ 池规模显式置位。计算在
            # _compute_mdo_for_baseline（同 ENABLE_MUTATION_SCORING 挂点），
            # 此处仅占位 None（键集合同构，默认关时零行为变化）。
            "mdo_available": None,
            "mtr": None,
            "mdr": None,
            "mdo_crash_rate": None,
            "mdo_pool_size": None,
            "mdo_pool_floor_ok": None,
            "mdo_not_available_reason": None,
            # T6（2026-10-11 独立评审落地）：池未达下限时 mdo.py 的 as_dict()
            # 会把 mtr/mdr/crash_rate 规范键置 None 并给出 mdo_provisional=True
            # + mdo_raw（原始值，审计用）。此处占位保持**键集合同构**——
            # 不跑 MDO 的批次也必须带这两个键，否则分析侧无法按列读取。
            "mdo_provisional": None,
            "mdo_raw": None,
            # R8（2026-09-30 独立审查 N7，P1）：FL@1/3/5 定位命中指标
            # （Ochiai 谱系定位的"真实缺陷行是否落在 Top-k"量化口径）
            "fl_at_k": _fl_at_k(final_state, task),
            # 修复引擎第一阶段（2026-10-07 范式转向）：局部化独立指标——
            # LLM 推理定位（RGFL 式）透出 + 函数级命中（与 gold 变更函数
            # 集合比对）。None = 未定位 / 无 gold 材料（键集合同构占位）。
            "llm_localization": (final_state or {}).get("llm_localization"),
            "localization_hit_function": _localization_hit_function(task, final_state),
            # 修复引擎批次 II：元素级排序指标（Top-3 命中 + MRR），
            # 与 Hit@1 并列透出（None 占位口径同上）。
            "localization_hit_function_at_3": _loc_rank.get("localization_hit_function_at_3"),
            "localization_mrr": _loc_rank.get("localization_mrr"),
            # 修复引擎批次 III：编辑意图确定性落盘观测（EDIT_INTENT_ENABLE
            # 默认关时恒 None；开启时 {"ok","applied","total","diagnostics"}，
            # ok=False 表示确定性引擎拒绝并回落整文件补丁通道）。
            "edit_intent_status": (final_state or {}).get("edit_intent_status"),
            # R4（2026-10-08 局部编辑通道原型）：定位锚定的局部编辑合规观测
            # （LOCALIZED_EDIT_ENABLE 默认关时恒 None；开启时 {"localized_count",
            # "total","constrained","candidate_functions","violations",
            # "localized_ratio"}——edit_intents 锚点落在定位候选函数内的占比，
            # ADR-0024"生成侧不消费定位"反事实的行级验证器）。
            "edit_localization": (final_state or {}).get("edit_localization"),
            # 修复引擎批次 IV（ADR-0019）：确定性优先修复路由观测（默认关
            # 恒 None；patch_produced=True 表示该修复轮跳过 LLM、补丁由
            # 确定性变换器产出——实验层据此统计接管率与省 token 量）。
            "deterministic_repair_status": (final_state or {}).get("deterministic_repair_status"),
            # 修复引擎批次 V（ADR-0020 观测层）：弃权门判定核输出——
            # patch_abstained = 命中任一不可信信号（M5 假通过 / 全程
            # 全绿未检出 / 终审过红 / 证据等级 none / 写盘未验证）；
            # 历史口径零变化（passed 不受影响），供"弃权调整后 passed
            # 率"与弃权精确率 A/B 消费（阻断档转正判据见 ADR-0020）。
            "patch_abstained": evaluate_patch_abstention(final_state)["abstain"],
            "patch_abstain_signals": evaluate_patch_abstention(final_state)["signals"],
            # 修复引擎批次 XVI（ADR-0020 弃权+验证双策略·验证半边，观测层）：
            # patch_validated = 补丁是否有独立于生成器的验证证据（gold 独立
            # 裁决 / 确定性引擎产出 / 确定性证据门放行）；与弃权门对称——
            # 弃权看"不可信信号"，验证看"正面证据"。历史口径零变化
            # （passed 不受影响），供 filtered success rate 消费（阻断档
            # 转正判据见 ADR-0020 修订）。
            "patch_validated": evaluate_patch_validation(final_state)["validated"],
            "patch_validate_verdict": evaluate_patch_validation(final_state)["verdict"],
            # 修复引擎批次 VIII（ADR-0022 观测层）：test-hacking 确定性检测——
            # 补丁新引入的硬编码输入分支 / 断言删除 / 吞异常（AST 差集，
            # 零 LLM）；补丁后代码经 _target_code_after_patch（批次 VII 修正
            # 口径，与写盘对齐清理）。历史口径零变化（passed 不受影响），
            # 供误伤率/富集度 A/B 消费（阻断档转正判据见 ADR-0022）。
            "test_hacking_suspected": _test_hacking_result(task, final_state)["suspected"],
            "test_hacking_signals": _test_hacking_result(task, final_state)["signals"],
            # 修复引擎批次 XIV（ADR-0028 观测层）：FL Top-k 约束门——
            # "补丁是否真的修改了定位候选位置之一"（定位命中但补丁改在
            # 别处 = 定位信号被合成侧浪费，ADR-0024 生成侧主导的行级
            # 验证器）；hit_rank = 首个命中候选序数。观测层 passed 历史
            # 口径零变化，阻断档转正判据见 ADR-0028。
            "fl_constraint_verdict": _fl_constraint["verdict"],
            "fl_constraint_hit_rank": _fl_constraint["hit_rank"],
            "fl_constraint_changed_functions": _fl_constraint["changed_functions"],
            # 修复引擎批次 XIV（ADR-0028 观测层）：Self-Repair Trap——
            # 迭代自修复是否驱使断言退化（三信号判定核，DCAware 风险
            # 口径）；oracle_quality_history 一并透出供离线复算。
            "oracle_quality_history": final_state.get("oracle_quality_history"),
            "self_repair_trap_suspected": _trap["suspected"],
            "self_repair_trap_signals": _trap["signals"],
            # 2026-09-29 审查 P0（StopReason 统一停止条件）：终止原因分布
            # 可解释（"test_passed" / "max_iterations" /
            # "skip_debugger_repair_invalid" / "test_defect_regeneration_cap" /
            # "budget_exceeded" / "regression_detected" / "unknown"）。
            # O35（2026-09-30 全面审查 P1）：此前直接读 final_state["stop_reason"]
            # ——该键由条件边函数原地写入入参 dict，LangGraph 不回写状态，
            # 实测恒为 None（stop_reason 列全空）。现经 effective_stop_reason
            # 兜底：state 已有值则用之，否则按 determine_stop_reason 同一优先级
            # 对最终状态重新判定（各基线均可得终止原因，不再恒 None）。
            "stop_reason": effective_stop_reason(final_state),
            # I1（2026-10-16）：终局失效桶 + 批次 XII 交互中心归因（edge ×
            # fault_side）。四键由 annotate_final_state 单次推导（纯静态零 LLM，
            # 状态视图重建口径见 _failure_attribution_for_result）。此前该框架
            # **无任何生产消费方**——分桶只在单测里被断言，批次工件与报表一处
            # 不落，"失败发生在哪个环节、属于哪类失效"无法从工件复算。历史
            # 口径零变化（passed / stop_reason / failure_category_distribution
            # 均不动），纯新增列。
            "failure_bucket": _attribution["failure_bucket"],
            "failure_bucket_detail": _attribution["failure_bucket_detail"],
            "attribution_edge": _attribution["attribution_edge"],
            "attribution_fault_side": _attribution["attribution_fault_side"],
            # I2（2026-10-16，ADR-0032）：M10 降级归因分离标记（提取器叶子
            # 回退误诊 vs LLM 真未输出）。此前只写进 test_plan 内部 → 投影行
            # 读不到 → ADR-0032 声称的可分离性不可机读；现由 _planner_node
            # 抬到顶层通道（state.py 已声明）后随行落盘。
            "m10_leaf_fallback": final_state.get("m10_leaf_fallback"),
            # R4（2026-09-30 独立审查 P0）：回归率（修复引入回归观测）
            # 补丁应用后 gold P2P 基线测试出现回归 → 1.0；否则 0.0；
            # 无 P2P 材料 / 超时 → None（不可测量）
            "regression_rate": _compute_regression_rate(task, final_state),
            # M3 门禁：harness_invalid 标记（基线 P2P 不达标，不计入统计）
            "harness_invalid": harness_invalid,
            # AM1（2026-10-06 第十三轮审查 / 预注册 E6 执行前置）：本任务
            # LLM 调用是否被臂级 token 上限拦停（与任务末预算快照一致；
            # harness_invalid 早退路径为上一任务残留快照，但该行经 M3 门禁
            # 本就不计入统计）。cap 未注入（历史口径）时恒 False。
            "token_budget_capped": _current_budget_exceeded(),
            # D3（N-5，2026-10-17）：跨文件审计字段（成功分支；与失败分支键位一致）
            **_cross_file_audit_fields(final_state),
        }
    return {
        "task_id": task.task_id,
        "repo": task.repo_name,
        "passed": False,
        "coverage": 0.0,
        "iterations": 0,
        "diagnosis": diagnosis,
        "error_category": error_category,
        "elapsed_seconds": round(elapsed, 2),
        "token_usage": token_usage.get_usage().as_dict(),
        "rag_stats": None,
        # 2.1 数据污染检测：失败分支无生成补丁，patch 以 None 兜底保持键集合同构
        "patch": None,
        # 1.2 变异得分：失败分支无生成测试，generated_test 以 None 兜底
        "generated_test": None,
        # 3.2 执行反馈轨迹：失败分支（无 final_state）无轨迹可带，None 兜底
        "execution_trace": None,
        # 1.3 命名契约符号守卫 / 2.2 重采样：失败分支无 final_state，
        # 各以 None 兜底保持键集合同构
        "contract_missing_symbols": None,
        # BL：失败分支无 final_state，读法同样 None 占位（与上一行同数，保持键集合同构）
        "contract_status": None,
        # BN：失败分支同口径 None 占位（与成功分支新增的六键保持键集合同构）
        "static_check_status": None,
        "static_check_outcomes": None,
        "safety_check_status": None,
        "safety_check_outcomes": None,
        "oracle_check_status": None,
        "oracle_check_outcomes": None,
        "patch_resample_stats": None,
        # 五、多维度污染检测：失败分支无生成补丁（patch=None）→ 检测不适用
        # （N7 口径：与"检测过且无重叠证据"的 "low" 区分；成功分支走
        # _compute_contamination_risk_level 实算）
        "contamination_risk_level": "not_applicable",
        # P0 仓库级验证诊断：失败分支（无 final_state）无仓库级验证结果，
        # None 兜底保持键集合同构（成功分支在 final_state 非 None 时写入）
        "repo_verification": None,
        "task_metadata": task.metadata,
        # G2 风险分级人工回路（失败分支无 final_state，保守占位）
        "risk_summary": _build_risk_summary_for_result(None),
        # M1（2026-09-29 审查 P0）：失败分支（无 final_state）三指标与假
        # 通过标记以 None 占位保持键集合同构（假通过通道仅对 passed=True
        # 有意义，失败分支恒无）
        "test_regenerated_pass_unverified": None,
        # A16：失败分支无执行尝试证据，flaky 键以 None 占位保持键集合同构
        "flaky_unverified": None,
        "flaky_detected": None,
        "flaky_pass_count": None,
        "flaky_total_count": None,
        # W3（检出优先协议）：失败分支无 final_state，None 占位保持键集合同构
        "detection_first_red_seen": None,
        "detection_first_status": None,
        # Y1：再生成计数失败分支占位（键集合同构）
        "regeneration_count": None,
        # AB3：规约可编译率失败分支占位（无 final_state / 生成测试，
        # SPEC_IR_DSL 链路未触达；键集合同构）
        "spec_compile_rate": None,
        # P0-4（2026-10-10 独立审查）：规约 oracle 注入观测键失败分支占位
        # （无 final_state → 键集合同构；不影响历史批次 JSON 的键集合）
        "spec_oracle_injected": None,
        "spec_oracle_verdict": None,
        # Q-1：示例审计键失败分支占位（无 final_state → 键集合同构；默认关
        # 恒 none/0，历史批次 JSON 向后兼容）
        "spec_oracle_examples_source": "none",
        "spec_oracle_examples_count": 0,
        # P0-A-2（2026-10-12）：规格优先替换段观测键失败分支占位
        # （无 final_state → 键集合同构；不影响历史批次 JSON 的键集合）
        "spec_replace_applied": None,
        # M-1（2026-10-17）：规格增广段观测键失败分支占位
        # （无 final_state → 键集合同构；不影响历史批次 JSON 的键集合）
        "spec_augment_applied": None,
        # AC1：表达式通道覆盖率失败分支占位（键集合同构）
        "spec_expr_coverage": None,
        # T1（2026-10-11 独立评审落地）：规约被拒原因分布失败分支占位
        # （无 final_state → 键集合同构；不影响历史批次 JSON 的键集合）
        "spec_reject_reasons": None,
        # AC2：双门观测失败分支占位（无 final_state，键集合同构）
        "specificity_gate_verdict": None,
        "red_regression_violation": None,
        # P0（2026-09-30 独立审查 N9/R33）：失败分支无 final_state，
        # 证据门观测键以 None 占位保持键集合同构
        "source_patched_unverified": None,
        "patch_evidence_level": None,
        # T 轮 2026-10-18：回滚 verdict schema 失败分支占位（键集合同构）。
        # 无 final_state ⇒ 无回滚语义：verdict=None（不可判定/未执行）、
        # rolled_back=False（明确未发生回滚，不得写成 True）
        "patch_rollback_verdict": None,
        "patch_rolled_back": False,
        "detection_rate": None,
        # N-3：失败分支无 final_state → LLM-suite 不可判（None）/ oracle 未运行
        # （unavailable）；键集合同构（成功/失败两分支键集合完全一致）。
        "llm_suite_detection_rate": None,
        "oracle_suite_verdict": "unavailable",
        "repair_rate": None,
        "false_fix_rate": None,
        # 2026-09-30 独立审查 N1：失败分支无生成测试，测试执行错误率占位
        "test_error_rate": None,
        # 2026-09-30 独立审查 R52/R53：失败分支无 final_state，
        # oracle 类型声明 / 补丁精确率框架以保守占位保持键集合同构
        "oracle_type": "generated_test",
        "test_visible_to_system": True,
        "patch_plausible": 0,
        # P0-2：键集合同构占位（失败分支无 final_state，因此无可落盘历史）
        "repair_history": [],
        "patch_plausible_evidence": {
            "has_patch": False,
            "history_len": 0,
            "last_patch_applied": None,
            "basis": "no_state",
        },
        "patch_plausible_invariant_violation": False,
        # MDO 键集合同构占位（失败分支无 final_state）
        "mdo_available": None,
        "mtr": None,
        "mdr": None,
        "mdo_crash_rate": None,
        "mdo_pool_size": None,
        "mdo_pool_floor_ok": None,
        "mdo_not_available_reason": None,
        # T6：与成功分支同构（见 _build_task_result 的说明）
        "mdo_provisional": None,
        "mdo_raw": None,
        "patch_correct": 0,
        "patch_precision": None,
        "fl_at_k": None,
        # 修复引擎第一阶段：失败分支无 final_state，定位键 None 占位
        # （键集合同构，与成功分支 llm_localization/localization_hit_function 配对）
        "llm_localization": None,
        "localization_hit_function": None,
        # 修复引擎批次 II：失败分支排序指标 None 占位（键集合同构）
        "localization_hit_function_at_3": None,
        "localization_mrr": None,
        # 修复引擎批次 III：失败分支编辑意图观测 None 占位（键集合同构）
        "edit_intent_status": None,
        # R4：失败分支局部编辑合规观测 None 占位（键集合同构）
        "edit_localization": None,
        # 修复引擎批次 IV：失败分支确定性路由观测 None 占位（键集合同构）
        "deterministic_repair_status": None,
        # 修复引擎批次 V：失败分支弃权观测占位（无 final_state 不可评估，
        # 保守 False/[]——与求值核 None 口径一致，键集合同构）
        "patch_abstained": False,
        "patch_abstain_signals": [],
        # 修复引擎批次 XVI：失败分支验证观测占位（无 final_state 不可评估，
        # 保守 False/"not_applicable"——与求值核 None 口径一致，键集合同构）
        "patch_validated": False,
        "patch_validate_verdict": "not_applicable",
        # 修复引擎批次 VIII（ADR-0022）：失败分支无补丁可检测，
        # False/[] 占位（键集合同构）
        "test_hacking_suspected": False,
        "test_hacking_signals": [],
        # 修复引擎批次 XIV（ADR-0028）：失败分支无 final_state，约束门 /
        # 陷阱观测以 None/False/[] 占位（键集合同构）
        "fl_constraint_verdict": None,
        "fl_constraint_hit_rank": None,
        "fl_constraint_changed_functions": [],
        "oracle_quality_history": None,
        "self_repair_trap_suspected": False,
        "self_repair_trap_signals": [],
        # R4（2026-09-30 独立审查 P0）：失败分支无 final_state，回归率占位
        "regression_rate": None,
        # 2026-09-29 审查 P0（StopReason）：失败分支无 final_state，终止原因为 None
        "stop_reason": None,
        # I1（2026-10-16）：失败分支（运行异常 / 限流耗尽）无工作流终局状态，
        # 归因四键以 None 占位保持键集合同构。**不填 uncategorized**——那不是
        # "状态信息不足"，而是"根本没有终局状态可分类"，折进兜底桶会让
        # failure_bucket_distribution 的分母失去意义（改由 unclassified_rows 单列）。
        "failure_bucket": None,
        "failure_bucket_detail": None,
        "attribution_edge": None,
        "attribution_fault_side": None,
        # I2（2026-10-16，ADR-0032）：失败分支无 final_state，占位 None
        "m10_leaf_fallback": None,
        # M3 门禁：harness_invalid 标记（基线 P2P 不达标，不计入统计）
        "harness_invalid": harness_invalid,
        # AM1：失败分支同读当前线程预算快照（异常路径同线程，值为真实口径）
        "token_budget_capped": _current_budget_exceeded(),
        # D3（N-5，2026-10-17）：跨文件审计字段（失败分支占位；键位与成功分支一致）
        **_cross_file_audit_fields(None),
    }


def _build_risk_summary_for_result(final_state: dict[str, Any] | None) -> dict[str, Any]:
    """构建单任务结果行的 G2 风险分级摘要（默认关时 enabled=False 占位）。

    设计口径（保守、零 LLM 成本）：
        - 仅当 `RISK_APPROVAL_ENABLE=true` 时做三因子打分（error_classifier 置信度
          + patch_applier 影响面 + cost_budget 消耗），产出 low/medium/high 分级
          与 auto_merge / human_confirm / force_review 审批动作；
        - 默认关（历史默认）时返回 `{"enabled": False}` 占位，保持结果键集合同构，
          不改变任何历史实验口径。

    BM 轮（2026-10-22）：成功分支把 `final_state["contract_status"]` 逐字透传给
    `build_risk_summary`。发布侧（BI/BL 轮）已经把该键写进工作流状态和结果行，
    这里是实验侧最后一个"写了没人读"的消费点；它只驱动披露文本
    （`contract_unmeasurable(...)`）与摘要里的读法字段，**不参与任何打分**。
    失败分支没有最终状态，保持 `None`（="这条腿本轮没做"），不按 0 处理。

    Args:
        final_state: 任务最终状态 dict（成功分支）；None 表示失败分支
            （无最终状态，保守占位，不打风险分）。

    Returns:
        可直接嵌入 JSON 的 dict。
    """
    from src.graph.risk_approval import build_risk_summary

    if final_state is None:
        return build_risk_summary(
            confidence=None,
            changed_lines=None,
            changed_files=None,
            contract_missing_symbols=None,
            full_file_patch=None,
            budget_ratio=None,
            budget_exceeded=None,
        )
    # 三因子输入（纯数据，缺信号时 None，保守打分不报错）：
    #   - 置信度：final_state 未直接携带（classifier 在节点内消费），保守 None；
    #   - 影响面：patch 行数（变更行数的保守代理）+ 跨文件数（cross_file_deps）；
    #   - 预算：cost_budget.get_budget_stats() 的 consumed/limit 比例（未启用时 None）。
    patch_text = final_state.get("patch") or ""
    changed_lines = len([ln for ln in patch_text.splitlines() if ln.strip()])
    changed_files = len(final_state.get("cross_file_deps") or []) or (1 if changed_lines else 0)
    contract_missing = final_state.get("contract_missing_symbols") or []

    from src.graph.cost_budget import get_budget_stats

    budget_stats = get_budget_stats()
    budget_exceeded = bool(budget_stats.get("exceeded"))
    consumed = float(budget_stats.get("consumed_tokens") or 0.0)
    limit = float(budget_stats.get("token_limit") or 0.0)
    budget_ratio = (consumed / limit) if limit > 0 else None

    return build_risk_summary(
        confidence=None,
        changed_lines=changed_lines,
        changed_files=changed_files,
        contract_missing_symbols=list(contract_missing),
        full_file_patch=None,
        budget_ratio=budget_ratio,
        budget_exceeded=budget_exceeded,
        contract_status=final_state.get("contract_status"),
    )


def _write_cross_file_modules(tmp_dir: str, task_metadata: dict[str, Any]) -> None:
    """P0 2026-10 改进：跨文件任务的伴生模块物化（纯磁盘操作，零 LLM 成本）。

    把 SyntheticDataset 写入 task.metadata 的 module_a_code / module_b_code /
    module_c_code 同步落盘到 tmp_dir，使跨文件修复架构（cross_file_analyzer
    节点 + 多文件 patch_applier）能在真实多文件工作区上消费依赖图。

    设计口径（保守、历史零变化）：
    - 仅当 metadata 携带 is_cross_file=True 且存在 module_a_code 时才执行；
      非跨文件任务（Level 1/2/4）直接 return，行为与历史逐字节一致；
    - 模块名取 metadata 的 module_a_name / module_b_name / module_c_name
      （缺省时按 module_a.py / module_b.py / module_c.py 兜底）；
    - 写文件失败（磁盘满 / 权限）仅记录 warning，不阻断任务主流程
      （降级为"仅被调方单文件"的历史口径，cross_file_analyzer 拿到
      缺模块的 source_files 时自动降级单文件模式）。

    Args:
        tmp_dir: 任务临时目录（已存在，含被调方 instance_code 文件）。
        task_metadata: BenchmarkTask.metadata（跨文件任务含伴生模块键）。
    """
    if not task_metadata.get("is_cross_file"):
        return
    module_specs = [
        ("module_a_code", task_metadata.get("module_a_name", "module_a")),
        ("module_b_code", task_metadata.get("module_b_name", "module_b")),
        ("module_c_code", task_metadata.get("module_c_name", "module_c")),
    ]
    for code_key, name_key in module_specs:
        code = task_metadata.get(code_key)
        if not code:
            continue  # 模块缺失（如 level3 双模块无 module_c）：跳过，保守口径
        module_name = task_metadata.get(name_key, code_key.replace("_code", ""))
        try:
            with open(os.path.join(tmp_dir, f"{module_name}.py"), "w", encoding="utf-8") as f:
                f.write(code)
        except OSError as e:
            logger.warning("跨文件伴生模块 %s.py 写入失败（降级单文件口径）: %s", module_name, e)


def _write_cross_file_state(initial_state: dict[str, Any], task_metadata: dict[str, Any]) -> None:
    """P0 2026-10 改进：跨文件任务的 state["cross_file_deps"] 预置（零 LLM 成本）。

    跨文件任务（metadata 携带 dep_chain + is_cross_file）把依赖链
    （如 module_a → module_b → module_c）预置到 state["cross_file_deps"]，
    使 nodes._cross_file_analyzer_node 在 CROSS_FILE_ENABLE=true 时能
    消费预置依赖图（避免 AST 分析空转），同时 _resolve_target_module
    能从 cross_file_deps 解析出被调方真实模块名（module_c），供
    _locate_repair_focus 的跨文件保护与探针定位消费。

    设计口径（保守、历史零变化）：
    - 仅当 metadata 携带 is_cross_file=True 且 dep_chain 非空时执行；
      非跨文件任务 / 无 dep_chain 时直接 return（state 保持 None，
      由 _cross_file_analyzer_node 现场 AST 分析，历史口径不变）；
    - 依赖边按 dep_chain 相邻对构造（source_module → target_module），
      symbol 留空（LLM 补丁侧按需解析调用符号）；
    - 已存在 cross_file_deps（CLI 手动注入 / 此前节点已写入）时不覆盖。

    Args:
        initial_state: 任务初始状态 dict（create_initial_state 产物）。
        task_metadata: BenchmarkTask.metadata（跨文件任务含 dep_chain）。
    """
    if not task_metadata.get("is_cross_file"):
        return
    dep_chain = task_metadata.get("dep_chain") or []
    if len(dep_chain) < 2:
        # 2026-10 改进（P3 双向依赖图驱动）：双模块任务（L3）dep_chain 为 None，
        # 历史 _write_cross_file_state 直接跳过 → cross_file_deps 为空 →
        # 跨文件修复架构（CROSS_FILE_ENABLE=true）拿不到依赖图，降级单文件
        # 修复，根因分析报 DEP_GRAPH_INCOMPLETE（OFF 组 L3 失败任务的主要
        # 根因之一）。现按 module_a_name → target_module 补一条单边（调用方
        # module_a → 被调方 target_module，如 module_b / module_c），使双模块
        # 任务也拥有依赖边。dep_chain 已存在（L3.5 三模块）时仍走原路径，
        # 不重复补边。
        target_module = task_metadata.get("target_module")
        module_a_name = task_metadata.get("module_a_name", "module_a")
        if target_module:
            dep_chain = [module_a_name, target_module]
    if len(dep_chain) < 2:
        return
    # 依赖边：dep_chain[i] → dep_chain[i+1]（调用方 → 被调用方）
    dep_edges = [
        {
            "source_module": dep_chain[i],
            "target_module": dep_chain[i + 1],
            "symbol": "",
            "call_line": 0,
            # O11（2026-09-29 审查 P1）：显式标记边来源为 benchmark 层预置
            # （区别于 _cross_file_analyzer_node 的 AST 推导边）。
            # "source": "benchmark_preset" 使实验分析能区分"预置边"与"
            # AST 推导边"，跨文件 A/B 结论可外推的前提是两类边均非空。
            "source": "benchmark_preset",
            "context": f"dep_chain[{i}]: {dep_chain[i]} -> {dep_chain[i + 1]}",
        }
        for i in range(len(dep_chain) - 1)
    ]
    initial_state["cross_file_deps"] = dep_edges


def _current_budget_exceeded() -> bool:
    """AM1：当前线程预算快照是否已超限（结果行 token_budget_capped 取值）。"""
    try:
        from src.graph.cost_budget import is_budget_exceeded

        return bool(is_budget_exceeded())
    except Exception:  # pragma: no cover - 预算模块不可用时观测位降级 False
        return False


def parse_per_task_token_caps(spec: str | None) -> dict[str, int]:
    """AM1（2026-10-06 第十三轮审查 / 预注册 E6 执行前置）：解析臂级 token 上限。

    Args:
        spec: 形如 ``"aitester=4223,plain_llm_df=26115"`` 的映射串；
            None / 空串 → 空 dict（历史口径，无 cap）。

    Returns:
        臂名 → 每任务 token 硬上限（正整数）。未知臂名或非法数值抛
        ValueError（fail-fast：E6 是预注册实验，静默忽略 cap 会让
        "budget-matched" 臂退化为 standard 口径而不自知）。
    """
    if not spec or not spec.strip():
        return {}
    caps: dict[str, int] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"--per-task-token-caps 片段须为 arm=cap 形式，收到 {part!r}")
        arm, _, raw = part.partition("=")
        arm = arm.strip()
        try:
            cap = int(raw.strip())
        except ValueError as exc:
            raise ValueError(f"--per-task-token-caps 的 {arm} 上限须为整数，收到 {raw!r}") from exc
        if cap <= 0:
            raise ValueError(f"--per-task-token-caps 的 {arm} 上限须为正整数，收到 {cap}")
        if arm not in BASELINE_REGISTRY:
            raise ValueError(f"--per-task-token-caps 未知基线臂 {arm!r}（可选：{sorted(BASELINE_REGISTRY)}）")
        caps[arm] = cap
    return caps


def run_single_task(
    task: BenchmarkTask,
    baselines: list[str],
    output_dir: str,
    verbose: bool = False,
    save_state: bool = False,
    enable_mutation_scoring: bool | None = None,
    per_task_token_caps: dict[str, int] | None = None,
) -> dict[str, Any]:
    """
    对单个 BenchmarkTask 运行所有指定的基线方法，返回汇总结果。

    Args:
        task: 基准测试任务。
        baselines: 要运行的基线方法列表。
        output_dir: 结果输出目录。
        verbose: 是否输出详细日志。
        save_state: 是否把环节级状态（测试计划/生成代码/诊断/补丁）
            落盘到 output_dir/raw/<task_id>/<baseline>.json（P0-2 排查用）。
        enable_mutation_scoring: 1.2 改进（MutGen 式变异反馈闭环）开关。
            None 时沿用 config.ENABLE_MUTATION_SCORING（默认 False）；
            True 时每个基线任务运行结束后把"存活变异体"写回结果行，
            供后续再生成/分析消费（mutation_feedback 字段）。
        per_task_token_caps: AM1（预注册 E6 执行前置）臂级每任务 token
            硬上限（arm → cap；空/None = 历史口径无 cap）。经
            set_task_token_cap 写入任务预算实例，超限走既有
            BudgetExceededError → BUDGET_EXCEEDED 停止通道。

    Returns:
        包含各基线结果的字典。
    """
    # 1.2 改进（MutGen 式变异反馈闭环）：解析变异评估开关
    # （None 沿用 config.ENABLE_MUTATION_SCORING 默认值；True/False 显式覆盖）
    mutation_enabled = ENABLE_MUTATION_SCORING if enable_mutation_scoring is None else bool(enable_mutation_scoring)
    # 五、多维度污染检测：从任务 metadata 收集黄金补丁（SWE-bench 数据集
    # 携带 metadata["golden_patch"]，合成数据集无 golden patch → 全
    # "not_applicable"，N7 口径：检测不适用而非低风险）
    golden_patches: dict[str, str] = {}
    _gp = (task.metadata or {}).get("golden_patch")
    if _gp:
        golden_patches[task.task_id] = _gp

    # M3 门禁（2026-09-29 审查 P0 + D.4-7）：SWE-bench 实例可解性前置验证。
    # SWE_BENCH_P2P_GATE_ENABLE=true 时，验证基线 PASS_TO_PASS ≥ 阈值；
    # 不可解实例标记 harness_invalid 并直接返回（不计入"0 解出"统计）。
    _harness_invalid = False
    _gate_result = _check_swe_bench_p2p_gate(task)
    if _gate_result is not None:
        _harness_invalid = True
        logger.warning(
            "M3 P2P 门禁：任务 %s 基线 P2P 不达标（%s），标记 harness_invalid",
            task.task_id,
            _gate_result.get("error_type"),
        )
    # 创建临时目录存放任务相关文件（避免修改原始文件）
    tmp_dir = tempfile.mkdtemp(prefix=f"aitester_{task.task_id}_")
    # W 轮（2026-10-19 复核残留连带修复）：线程局部 API 分配快照-恢复。
    # `_set_thread_api` 把任务分配写入当前线程的 llm_client._thread_local
    # （api_key/base_url/model_name）。并行跑批下每个工作线程在任务开始时
    # 重新分配、行为不变；但进程内单线程调用方（CLI / 库调用 / 测试）此前会
    # 把最后一次任务的分配**永久留在主线程**，污染后续所有 `_get_llm_config`
    # / `_get_all_api_configs` 调用（真实 env 凭证进入后续请求身份）。测试
    # 全量跑中该泄漏曾使 test_base_agent::TestGetLlmConfig 按 worker 文件
    # 配对顺序随机转红。任务结束时恢复进入前状态（含"未设置"状态）。
    from src.agents.llm_client import _thread_local as _task_thread_local

    _tl_attrs = ("api_key", "base_url", "model_name")
    _tl_prev: dict[str, Any] = {attr: getattr(_task_thread_local, attr, None) for attr in _tl_attrs}
    _tl_had: dict[str, bool] = {attr: hasattr(_task_thread_local, attr) for attr in _tl_attrs}
    try:
        # M3 门禁（2026-09-29 审查 P0 + D.4-7）：harness_invalid 时跳过执行，
        # 直接构建失败结果（不计入"0 解出"统计）。
        if _harness_invalid:
            logger.info("M3 P2P 门禁：任务 %s harness_invalid，跳过执行", task.task_id)
            results: dict[str, dict[str, Any]] = {}
            for baseline in baselines:
                results[baseline] = _build_task_result(
                    task,
                    0.0,
                    diagnosis=f"M3 P2P 门禁：harness_invalid（{_gate_result.get('error_type', 'unknown')}）",
                    error_category="harness_invalid",
                    golden_patches=golden_patches,
                    harness_invalid=True,
                )
            return results
        # 写入 instance_code 到临时文件
        # 使用 task_id 的最后一段作为模块名，确保与文件名一致
        # 转换非法字符：连字符→下划线，确保是合法 Python 标识符
        # P1-4（2026-10-05 独立审查）：泄漏修复在生成层——synthetic_dataset
        # 已把 task_id 末段中性化（task_XXXX）并同步重写 gold import，本侧
        # 派生规则不变即自动中性（单点派生，generator 看到的文件名不含
        # pattern 语义）
        raw_name = task.task_id.split("__")[-1]
        module_name = raw_name.replace("-", "_")[:50]
        instance_file = os.path.join(tmp_dir, f"{module_name}.py")
        with open(instance_file, "w", encoding="utf-8") as f:
            f.write(task.instance_code)

        # P0 2026-10 改进（失败模式多样性）：跨文件任务（is_cross_file=True）
        # 把 metadata 里的 module_a / module_b / module_c 源码同步写入临时目录，
        # 使跨文件修复架构（cross_file_analyzer → 多文件 patch_applier）能在
        # 真实多文件工作区上消费依赖图，而非仅靠"被调方单文件 + 文本拼接"。
        # 非跨文件任务零行为变化（无 module_a_code 键时直接跳过）。
        _write_cross_file_modules(tmp_dir, task.metadata)

        # 初始化工作流状态（唯一构造点：create_initial_state，与 CLI 口径一致）
        # 作为所有基线的起点，逐基线 deepcopy 隔离
        # P0：SWE-bench 任务从官方 patch 提取的 suggested_function 初始化
        # target_function，驱动 Planner/Generator/Debugger 的 AST 聚焦截取
        suggested_function = task.metadata.get("suggested_function")
        initial_state = create_initial_state(
            task_uuid=task.task_id,
            target_file=instance_file,
            target_function=suggested_function,
            module_name=module_name,
            target_code=task.instance_code,
            max_iterations=MAX_ITERATIONS,
            # P1-6：问题描述入 state（注入防护的外部可控文本主源——此前
            # state.get("problem_statement") 读未声明键恒 None，防护空转）
            problem_statement=getattr(task, "problem_statement", None),
        )

        # 2026-10 改进：跨文件任务预置 cross_file_deps（供 _resolve_target_module
        # 解析被调方真实模块名；单文件任务 no-op）
        _write_cross_file_state(initial_state, task.metadata)

        # AC2（2026-10-06 第十轮审查 T-P0-4）：门①材料管道——gold 修复
        # 代码注入 state["gold_fixed_code"]（特异性门在 gold fixed 上对照
        # 执行）。**评估/门禁专用材料，任何 agent prompt 不得引用**
        # （test_visible_to_system 卫生口径）；无 gold 材料（真实仓库任务）
        # 保持缺省 None，门①自动降级 unavailable（后续批次以变异体裁决）。
        try:
            from experiments._m1_metrics import _gold_fixed_code as _extract_gold_fixed

            _gold_fixed = _extract_gold_fixed(task)
            if _gold_fixed and _gold_fixed.strip():
                initial_state["gold_fixed_code"] = _gold_fixed
        except Exception:
            pass

        # P0 1.2 复杂度感知路由（MODEL_ROUTING_STRATEGY=complexity_aware）：
        # 按任务代码行数 / import 数量 / 圈复杂度计算复杂度分数，写入
        # state["complexity_class"]（"simple" | "medium" | "complex"），
        # 供 LLM 调用路径选择对应档位的 LLM 实例。策略=fixed 时恒为 "medium"。
        if routing_enabled():
            num_lines = len(task.instance_code.splitlines())
            # 2026-10-12 ULT 实跑勘误：metadata 键"存在但为显式 None"时
            # （如 ULT_Lite 无 cyclomatic_complexity 字段 → 加载器写 None），
            # dict.get(key, default) 返回的是 None 而非 default → int(None)
            # TypeError，46 任务全崩。用 `or` 兜底 None/缺键双态。
            num_files = int(task.metadata.get("num_files") or 1)
            # P0 审查修正：num_deps / cyclomatic_complexity 此前仅从
            # task.metadata 读取，而合成数据集 / SWE-bench 官方任务从未
            # 写入这两个键 → 永远走默认值（num_deps=0 / cc=1），评分退化为
            # "仅按行数分档"。现按需从 instance_code 直接计算（AST 口径，
            # 与 complexity_router.count_imports / code_analyzer 一致）。
            # 2026-09-26 优化：单次 ast.parse 复用——此前 count_imports 内部
            # 再 parse 一次（本函数第二次解析），--parallel 多任务热路径上
            # 每任务 2 次 200ms 级解析。现统一 parse 一次，count_imports
            # 经 _tree 参数复用（独立调用方不传 _tree 时行为不变）。
            num_deps = 0
            # 2026-10-12 ULT 实跑勘误：`or` 兜底"键存在但 None"态
            # （ULT_Lite 无 cyclomatic_complexity 字段 → 加载器写 None，
            # dict.get(key, 1) 返回 None → int(None) 崩溃）
            cc = int(task.metadata.get("cyclomatic_complexity") or 1)
            try:
                import ast as _ast

                _tree = _ast.parse(task.instance_code)
                _funcs = [n for n in _ast.walk(_tree) if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))]

                def _count_cc(node: _ast.AST) -> int:
                    """圈复杂度（函数级）：1 + if/for/while/except/and/or/assert 计数。"""
                    cc = 1
                    for n in _ast.walk(node):
                        if isinstance(n, (_ast.If, _ast.For, _ast.While, _ast.ExceptHandler, _ast.BoolOp, _ast.Assert)):
                            if isinstance(n, _ast.BoolOp):
                                cc += len(n.values) - 1
                            else:
                                cc += 1
                    return cc

                cc = max((_count_cc(f) for f in _funcs), default=1)
            except (SyntaxError, ValueError):
                # 解析失败（含 MemoryError 等 ValueError 子类保守口径）：
                # cc 回退 metadata（历史口径），count_imports 走独立 parse 路径
                # 2026-10-12 ULT 实跑勘误：同上用 `or` 兜底 None 态
                cc = int(task.metadata.get("cyclomatic_complexity") or 1)
                _tree = None
            try:
                from src.api.complexity_router import count_imports

                num_deps = count_imports(task.instance_code, _tree=_tree)
            except Exception:
                num_deps = int(task.metadata.get("num_imports") or 0)
            score_obj = compute_complexity_score(
                lines=num_lines,
                num_files=num_files,
                num_deps=num_deps,
                cyclomatic_complexity=cc,
            )
            routing_hints = complexity_class_to_routing_hints(score_obj.complexity_class)
            initial_state["complexity_class"] = score_obj.complexity_class
            initial_state["complexity_score"] = score_obj.score
            initial_state["complexity_breakdown"] = score_obj.breakdown
            initial_state["routing_hints"] = routing_hints
            logger.debug(
                "P0 1.2 任务 %s 复杂度评分：score=%.3f class=%s (%s)",
                task.task_id,
                score_obj.score,
                score_obj.complexity_class,
                routing_hints.get("hint_text", ""),
            )
        else:
            initial_state["complexity_class"] = "medium"  # 历史口径

        # 为每个基线分配 API
        # O31（2026-09-29 审查 P0 + 2026-09-30 修复验证 D.4-1）：基线模型混淆修复。
        #
        # 正确语义：三基线（aitester / plain_llm / single_agent）在同一任务上
        # 必须使用**同一模型**，否则架构效应与模型效应不可分离。
        # 默认口径（O31 修复后）：按 task 哈希选 slot，同任务三基线共享 slot。
        # 可选覆盖：设 AITESTER_BASELINE_LOAD_BALANCE=1 可按 baseline 名称
        # 哈希分散到不同 slot（用于不需要控制模型变量的负载测试）。
        results: dict[str, dict[str, Any]] = {}
        for _baseline_idx, baseline in enumerate(baselines):
            if os.environ.get("AITESTER_BASELINE_LOAD_BALANCE", "0") == "1":
                # 负载均衡模式：按 baseline 名称哈希，同基线跨任务稳定
                _api_idx = zlib.crc32(baseline.encode()) % len(_VALID_APIS) if _VALID_APIS else 0
            else:
                # O31 默认口径：同任务三基线同 slot（消除模型混淆）
                _api_idx = zlib.crc32(task.task_id.encode()) % len(_VALID_APIS) if _VALID_APIS else 0
            _set_thread_api(_api_idx)

            # 基线隔离：deepcopy 初始状态并重置磁盘实例文件为原始代码。
            # single_agent 基线执行中会把修复后的代码写回 target_file
            # （open(target_file, "w")），若不重置，后续基线会从"已修复代码 +
            # 已递增的 iteration"起步，基线对比数据无效
            state = copy.deepcopy(initial_state)
            # 1.2 改进（MutGen 式变异反馈闭环）：把上一轮变异评估的"存活变异体"
            # 注入 state，Generator 再生成时消费（形成变异引导的测试增强）
            # mutation_feedback 由基线运行前的变异评估（或上一任务结果）提供
            with open(instance_file, "w", encoding="utf-8") as f:
                f.write(task.instance_code)

            # P0-2 效率指标：重置本线程 token 统计，基线运行结束后记录消耗
            # （parallel 模式下每个工作线程独立累计，互不串扰）
            token_usage.reset()
            # O35（2026-09-30 全面审查 P1）：任务级成本预算同口径复位。
            # reset_budget() 此前**零生产调用点**（仅测试 / demo 引用），而
            # cost_budget 是线程局部 BudgetSnapshot 且 budget.exceeded 会一直
            # 置真——开启 COST_BUDGET_ENABLE 后，一旦某线程上的任务触顶，
            # 该线程后续**所有**任务的 LLM 调用都被 is_budget_exceeded()
            # 前置守卫拦下（planner→默认计划 / generator→空测试），
            # "任务级预算"退化成"线程级终身封顶"，产批系统性假失败。
            # 与 token_usage.reset() 并置：每个任务（每基线）开跑前清零。
            from src.graph.cost_budget import reset_budget, set_task_token_cap

            reset_budget()
            # AM1（预注册 E6 执行前置）：臂级 token 上限在预算复位后注入——
            # cap 写入本任务 BudgetSnapshot 实例（跟随任务，专家池 worker 经
            # attach_budget 自动继承）；超限走既有 BudgetExceededError 通道，
            # 结果行 stop_reason=budget_exceeded、token_budget_capped=True。
            _arm_cap = (per_task_token_caps or {}).get(baseline)
            if _arm_cap:
                set_task_token_cap(_arm_cap)
            start_time = time.time()
            state["task_uuid"] = f"{task.task_id}_{baseline}_{int(start_time)}"
            # 4.1 结构化追踪：本任务（baseline）会话开启（未启用时 no-op），
            # 节点级事件随工作流执行追加到 <task_uuid>.trace.jsonl
            start_task_trace(
                state["task_uuid"],
                task_meta={
                    "dataset_task_id": task.task_id,
                    "baseline": baseline,
                    "target_function": task.metadata.get("suggested_function"),
                },
            )

            if verbose:
                logger.info("  [%s] 运行 %s ...", baseline, task.task_id)

            try:
                final_state = BASELINE_REGISTRY[baseline](state)
                elapsed = time.time() - start_time

                # P0 仓库级验证路由（REPO_LEVEL_EXECUTION=true，opt-in，默认关）：
                # SWE-bench 官方验证口径——gold test_patch 前后对比 + FAIL_TO_PASS /
                # PASS_TO_PASS 实测。仅当任务携带 source/repo_url/base_commit/fail_to_pass
                # 且开关打开且基线为 aitester 时启用；合成集 / examples 任务无这些
                # 字段，永不命中，历史实验口径零变化。
                # LLM 修复循环（工作流）照常运行产生补丁，验证从"LLM 生成测试跑
                # pytest"切换为"仓库环境内 gold 测试实测"（官方口径优先）。
                if (
                    REPO_LEVEL_EXECUTION
                    and baseline == "aitester"
                    and task.metadata.get("source") == "swe_bench"
                    and task.metadata.get("fail_to_pass")
                    and task.metadata.get("repo_url")
                    and task.metadata.get("base_commit")
                ):
                    import config as _cfg
                    from src.agents.executor_repo import RepoExecutor

                    executor_repo = RepoExecutor(
                        timeout=EXECUTION_TIMEOUT,
                        setup_timeout=SWE_REPO_SETUP_TIMEOUT,
                        use_venv=getattr(_cfg, "SWE_REPO_VENV_ISOLATION", False),
                        # F10（2026-10-19 Z 轮审查 P1）：README 承诺的共享 venv
                        # 开关 SWE_REPO_VENV_REUSE_BY_REPO 此前全仓无消费点 →
                        # 文档承诺的"按仓库复用 venv"实际不可达（F10 的 A→B→A
                        # 场景无法经 CLI 触发）。与 use_venv 同口径接线；该变量
                        # 只在 experiments/ 消费，不在 ADR-0003 env 扫描面，故无
                        # 需登记（docstring 已由 README 承诺该开关存在）。
                        venv_reuse_by_repo=os.environ.get("SWE_REPO_VENV_REUSE_BY_REPO", "false").lower() == "true",
                    )
                    # gold patch 首个非测试源文件路径（git diff 的 a/b 头）
                    gold_target_rel = _extract_gold_target_relpath(task.metadata.get("golden_patch") or "")
                    # LLM 修复补丁：工作流已把修复写回 target_file（state 的
                    # target_code）。LLM 可能输出"完整文件重写"形态（python 包裹
                    # 而非 diff）——_normalize_llm_patch 提取出纯代码正文后，
                    # 按 gold 目标文件路径生成 unified diff，使
                    # _apply_patch_robust → git apply 能映射进真实仓库。
                    # instance_code 与 raw_patch 完全一致（LLM 未改动）→
                    # 空补丁，FAIL_TO_PASS 按无补丁实测裁决。
                    raw_patch = _normalize_llm_patch(final_state.get("patch") or "")
                    llm_patch_text = ""
                    if raw_patch and task.instance_code:
                        llm_patch_text = _diff_codes(
                            task.instance_code,
                            raw_patch,
                            fromfile=gold_target_rel,
                            tofile=gold_target_rel,
                        )
                    repo_result = executor_repo.verify(
                        repo_url=task.metadata["repo_url"],
                        base_commit=task.metadata["base_commit"],
                        test_patch=task.metadata.get("test_patch") or "",
                        llm_patch=llm_patch_text,
                        fail_to_pass=list(task.metadata["fail_to_pass"]),
                        pass_to_pass=list(task.metadata.get("pass_to_pass") or []),
                        # F11（2026-10-19 Z 轮审查 P1）：官方 swebench harness 的
                        # predictions / 报告解析都需要**真实** instance_id（如
                        # "django__django-12345"），历史实现伪造 repo@commit。
                        # 缺失时 verify 的官方路径降级自建口径（不伪造、不假过）。
                        instance_id=task.metadata.get("instance_id"),
                    )
                    # 仓库级验证结果覆盖 LLM 生成测试的判定（官方口径优先）
                    final_state["test_passed"] = repo_result["passed"]
                    final_state["repo_verification"] = repo_result
                    logger.info(
                        "    [%s] %s 仓库级验证: passed=%s f2p=%s p2p=%s",
                        baseline,
                        task.task_id,
                        repo_result["passed"],
                        repo_result.get("fail_to_pass"),
                        repo_result.get("pass_to_pass"),
                    )

                # 1.2 改进（MutGen 式变异反馈闭环）：workflow 结束后若启用变异
                # 评估，把"存活变异体"写回结果行，供后续再生成/分析消费
                # （首轮生成 vs 被测代码的变异测试，存活变异体 = 当前测试未
                #  捕获的故障模式，注入 Generator 后可引导补强断言）
                if mutation_enabled and final_state.get("generated_test"):
                    from experiments.mutation_testing import build_mutation_feedback

                    _feedback = build_mutation_feedback(
                        source_code=task.instance_code,
                        test_code=final_state["generated_test"],
                        max_mutants=MUTATION_MAX_MUTANTS,
                    )
                    if _feedback.get("available"):
                        # 2026-09-27 round10 P2：旧实现在此向 results[baseline]
                        # 写入 mutation_feedback，但 L711 _build_task_result 整体
                        # 替换 results[baseline]（新 dict 不含该键）→ 死写；
                        # 真正的闭环经 final_state["mutation_feedback"] →
                        # workflow 下轮 Generator 消费（nodes.py L240），正确。
                        # 删除 results 死写，仅保留 final_state 写入。
                        final_state["mutation_feedback"] = _feedback
                        logger.info(
                            "    [%s] %s 变异反馈闭环: 存活 %d 变异体（score=%.4f）",
                            baseline,
                            task.task_id,
                            len(_feedback.get("survived_mutants", [])),
                            _feedback.get("mutation_score") or 0.0,
                        )

                results[baseline] = _build_task_result(
                    task,
                    elapsed,
                    final_state=final_state,
                    golden_patches=golden_patches,
                    harness_invalid=_harness_invalid,
                )
                if save_state:
                    _dump_state_artifacts(output_dir, task, baseline, final_state)

                status = "PASS" if final_state.get("test_passed") else "FAIL"
                logger.info(
                    "    [%s] %s: %s (%.1fs, coverage=%.1f%%, tokens=%d)",
                    baseline,
                    task.task_id,
                    status,
                    elapsed,
                    final_state.get("coverage_report", 0.0),
                    token_usage.get_usage().total_tokens,
                )
                # 4.1 追踪收尾：记录 token 快照与最终结果
                end_task_trace(final_state.get("test_passed"), token_snapshot=token_usage.get_usage().as_dict())
            except openai.RateLimitError:
                # 限流：等待后重试（重试共享同一 token 统计窗口，结果含两次调用消耗）
                logger.warning("    [%s] %s 触发 API 限流，等待 %ds 后重试...", baseline, task.task_id, LLM_RETRY_WAIT)
                time.sleep(LLM_RETRY_WAIT)
                try:
                    final_state = BASELINE_REGISTRY[baseline](state)
                    elapsed = time.time() - start_time
                    results[baseline] = _build_task_result(
                        task,
                        elapsed,
                        final_state=final_state,
                        golden_patches=golden_patches,
                        harness_invalid=_harness_invalid,
                    )
                    if save_state:
                        _dump_state_artifacts(output_dir, task, baseline, final_state)
                    end_task_trace(final_state.get("test_passed"), token_snapshot=token_usage.get_usage().as_dict())
                except Exception as e2:
                    elapsed = time.time() - start_time
                    logger.error("    [%s] %s 重试后仍失败: %s", baseline, task.task_id, e2)
                    results[baseline] = _build_task_result(
                        task,
                        elapsed,
                        diagnosis=f"限流重试失败: {e2}",
                        error_category="rate_limit",
                        golden_patches=golden_patches,
                        harness_invalid=_harness_invalid,
                    )
                    end_task_trace(False, token_snapshot=token_usage.get_usage().as_dict())
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error("    [%s] %s 执行失败: %s", baseline, task.task_id, e)
                results[baseline] = _build_task_result(
                    task,
                    elapsed,
                    diagnosis=f"执行异常: {e}",
                    error_category="error",
                    golden_patches=golden_patches,
                    harness_invalid=_harness_invalid,
                )
                end_task_trace(False, token_snapshot=token_usage.get_usage().as_dict())

        return results

    finally:
        # 清理临时目录
        shutil.rmtree(tmp_dir, ignore_errors=True)
        # 恢复线程局部 API 分配（W 轮连带修复：不留任务级分配在调用线程）
        for _attr in _tl_attrs:
            if _tl_had[_attr]:
                setattr(_task_thread_local, _attr, _tl_prev[_attr])
            elif hasattr(_task_thread_local, _attr):
                delattr(_task_thread_local, _attr)


def _diff_codes(original: str, fixed: str, fromfile: str, tofile: str) -> str:
    """生成 original → fixed 的 unified diff（RepoExecutor LLM 补丁输入）。

    fromfile/tofile 为 git apply 用的目标路径名（git diff 的 a/ b/ 头），
    LLM 补丁经 _apply_patch_robust → git apply 应用进仓库工作区；路径
    对不上（fromfile ≠ 仓库真实文件路径）时 git apply 拒绝，RepoExecutor
    记 llm_patch_applied=False，FAIL_TO_PASS 实测裁决（不误判通过）。

    实现：`git diff --no-index` 在两个临时文件（git 仓库内）上运行，
    产出的 unified diff 行计数 / 尾部换行语义严格正确（difflib
    手工拼接在"整文件替换"场景会产生行计数与 git 解析器不符的损坏
    补丁，已实测），且 `--- / +++` 头被替换为真实仓库路径；git 不可用
    或仓库缺失时退回 difflib。两串相同（LLM 未修复或修复为空）时
    返回空串，RepoExecutor 按"无补丁"处理（FAIL_TO_PASS 实测基线，
    不通过即如实判定）。
    """
    if original == fixed:
        return ""
    import difflib
    import subprocess as _sp
    import tempfile as _tf

    # 在一个最小 git 仓库内跑 git diff --no-index（无仓库时 git 可能
    # 拒绝 --no-index，或产出相对路径头；git 头在下方被显式重写为
    # 真实仓库路径，产物不受仓库内相对路径影响）
    _tmp = _tf.mkdtemp(prefix="aitester_diff_")
    try:
        _repo = os.path.join(_tmp, "repo")
        os.makedirs(_repo, exist_ok=True)
        _orig = os.path.join(_repo, "original")
        _new = os.path.join(_repo, "modified")
        with open(_orig, "w", encoding="utf-8") as _f:
            _f.write(original)
        with open(_new, "w", encoding="utf-8") as _f:
            _f.write(fixed)

        def _git(_args: list[str]) -> _sp.CompletedProcess[str]:
            return _sp.run(["git", "-C", _repo, *_args], capture_output=True, text=True)

        _git(["init", "-q"])
        _git(["add", "original"])
        _git(["commit", "-q", "--no-verify", "-m", "init", "--author", "aitester <aitester@local>"])
        # original 已提交、modified 留在工作区 → --no-index 对比两文件
        _r = _git(["diff", "--no-index", "--", "original", "modified"])
        # 退出码 1 = 有差异（正常）；0/2 才是异常
        if _r.returncode in (0, 1) and _r.stdout:
            _lines = _r.stdout.splitlines()
            # _lines[0] = 'diff --git a/original b/modified'（git 头，丢弃）
            # _lines[1] = 'index ...'（git 元数据，丢弃）
            # _lines[2:] = '--- a/...' '+++ b/...' '@@ ... @@' 及 hunk 正文
            if len(_lines) >= 4 and _lines[2].startswith("--- ") and _lines[3].startswith("+++ "):
                _hdr = f"diff --git a/{fromfile} b/{tofile}\n"
                _body = "\n".join(_lines[2:])
                # 关键：重写 --- / +++ 行中的文件名（git --no-index 产出
                # a/original b/modified 相对名，必须换成真实仓库路径，
                # git apply 才能定位到仓库内的实际文件）
                _body_lines = _body.split("\n")
                _body_lines[0] = f"--- a/{fromfile}"
                _body_lines[1] = f"+++ b/{tofile}"
                return _hdr + "\n".join(_body_lines) + ("\n" if _body_lines[-1] else "")
            logger.warning(
                "git diff --no-index 输出结构异常（首行: %s），退回 difflib",
                _lines[0][:80] if _lines else "(空)",
            )
        else:
            logger.warning(
                "git diff --no-index 失败（rc=%s），退回 difflib: %s",
                _r.returncode,
                _r.stderr.strip()[:120],
            )
    except Exception as _e:
        logger.warning("git diff 异常，退回 difflib: %s", _e)
    finally:
        import shutil as _sh

        _sh.rmtree(_tmp, ignore_errors=True)

    old_lines = original.splitlines(keepends=True)
    new_lines = fixed.splitlines(keepends=True)
    return "".join(difflib.unified_diff(old_lines, new_lines, fromfile=fromfile, tofile=tofile, n=3))


def _normalize_llm_patch(raw: str) -> str:
    """把 LLM 的"完整文件重写"形态提取为纯代码正文。

    工作流 patch_applier 产出的补丁常带 ```python 围栏 / 'python' 行首标记，
    直接喂给 difflib 会把围栏当代码行。剥离这些包裹，还原 LLM 想写的
    目标文件完整代码。无法还原（空 / 无围栏但非代码）时返回原文。
    """
    if not raw or not raw.strip():
        return ""
    s = raw.strip()
    # 去 ```python ... ``` 围栏
    if s.startswith("```"):
        lines = s.splitlines()
        # 找围栏头（```python / ```）与围栏尾（```）
        if lines[0].startswith("```"):
            body_lines = lines[1:]
            if body_lines and body_lines[-1].strip() == "```":
                return "\n".join(body_lines[:-1])
        # 只有头无尾：返回头之后的全部内容
        return "\n".join(lines[1:])
    # 首行恰为 'python'（patch_applier 的裸标记形态）→ 剥离
    lines = s.splitlines()
    if lines and lines[0].strip() == "python":
        return "\n".join(lines[1:])
    return s


def _extract_gold_target_relpath(golden_patch: str) -> str:
    """从官方 gold patch 提取首个非测试源文件的仓库相对路径（b/ 侧）。

    SWE-bench 任务的 LLM 补丁（_diff_codes 产物）需映射进真实仓库路径
    才能 git apply；从 gold patch 的 `diff --git a/<p> b/<p>` 头取首个
    非 test/ / tests/ / test_ 开头的文件。gold patch 缺失或全为测试文件
    时返回空串（_diff_codes 退化为裸路径，git apply 拒绝，FAIL_TO_PASS
    实测裁决）。
    """
    import re

    if not golden_patch:
        return ""
    for m in re.finditer(r"diff --git a/(\S+) b/(\S+)", golden_patch):
        rel = m.group(2)
        base = rel.split("/")[-1]
        if not (rel.startswith("test/") or rel.startswith("tests/") or base.startswith("test_")):
            return rel
    return ""


def _run_task_with_progress(args: tuple) -> tuple[BenchmarkTask, dict[str, Any]]:
    """并行执行任务包装器。"""
    task, baselines, output_dir, verbose, save_state, *rest = args
    # AM1：第 6 位为臂级 token 上限映射（旧 5 元组兼容，cap=None 历史口径）
    caps = rest[0] if rest else None
    results = run_single_task(task, baselines, output_dir, verbose, save_state=save_state, per_task_token_caps=caps)
    return task, results


def _run_tasks_sliding_window(
    executor: concurrent.futures.ThreadPoolExecutor,
    tasks: list[BenchmarkTask],
    baselines: list[str],
    output_dir: str,
    verbose: bool,
    save_state: bool,
    max_inflight: int,
    on_task_done: Callable[[BenchmarkTask, dict[str, Any]], None],
    per_task_token_caps: dict[str, int] | None = None,
) -> None:
    """0.7 债务项 2.5：滑窗提交任务，保持在途 future ≤ max_inflight。

    此前一次性 submit 全部任务（100+ 任务时 future 列表 100+ 个，每个持有
    task/baselines 等完整引用常驻内存），大对象常驻 + 长任务场景下内存峰值
    偏高；滑窗保持 ≤max_inflight 个在途即可。完成一个补一个（FIRST_COMPLETED），
    每个任务的结果经 on_task_done 回调收集（回调负责汇总结果 / 进度条 / 累计
    耗时），任务异常时回调收到空结果（不影响其余任务继续执行）。

    Args:
        executor: 线程池执行器（max_workers 已设）。
        tasks: 待执行的任务列表。
        baselines: 基线列表。
        output_dir: 输出目录。
        verbose: 是否详细输出。
        save_state: 是否保存中间状态。
        max_inflight: 在途 future 上限（通常 2×max_workers）。
        on_task_done: 每个任务完成后的回调，参数为 (task, task_results)。
    """
    task_iter = iter(tasks)
    pending: dict[concurrent.futures.Future, Any] = {}

    def _submit_next() -> None:
        """从任务迭代器取下一个任务提交（耗尽时 no-op）。"""
        try:
            task = next(task_iter)
        except StopIteration:
            return
        fut = executor.submit(
            _run_task_with_progress, (task, baselines, output_dir, verbose, save_state, per_task_token_caps)
        )
        pending[fut] = task

    # 填满初始滑窗
    for _ in range(max_inflight):
        _submit_next()

    while pending:
        done, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
        for future in done:
            task = pending.pop(future)
            try:
                _, task_results = future.result()
            except Exception as e:
                logger.error("任务 %s 执行失败: %s", task.task_id, e)
                task_results = {}
            on_task_done(task, task_results)
            # 完成一个补一个，保持在途 ≤ max_inflight
            _submit_next()


def _apply_rag_setting(enable_rag: bool | None) -> bool:
    """把 RAG 开关应用到 workflow 模块，返回生效值（P1：RAG 纳入主实验）。

    workflow 节点读取的是模块全局 ENABLE_RAG，直接改写模块属性即可生效
    （与测试中 patch("src.graph.workflow.ENABLE_RAG") 同机制），
    无需 reload 模块。

    Args:
        enable_rag: 显式开关；None 时保持 workflow 当前的 config 值。

    Returns:
        生效的 RAG 开关（bool）。
    """
    import src.graph.workflow as _wf

    enabled = _wf.ENABLE_RAG if enable_rag is None else bool(enable_rag)
    if enabled != _wf.ENABLE_RAG:
        logger.info("RAG 开关已切换: %s → %s", _wf.ENABLE_RAG, enabled)
        _wf.ENABLE_RAG = enabled
    return enabled


def _apply_stagnation_arm(enable: bool = False, disable: bool = False) -> str | None:
    """A-19（2026-10-17 独立评审）：把覆盖率停滞检测消融臂落到环境变量。

    workflow 每次判定都现读 `COVERAGE_STALL_DETECT_ENABLE`
    （`_coverage_stall_enabled` → `env_flag`），故 CLI 层写 env 即全链路生效，
    无需把开关穿透 `run_benchmark` 形参；该键已在 provenance 清单内，
    工件里可直接复核这一臂到底开没开（`check_env_snapshot_keys.py` 守）。

    Args:
        enable: `--enable-stagnation`（开臂）。
        disable: `--no-stagnation`（对照臂）。

    Returns:
        落盘的取值（"true"/"false"）；两臂都未指定时返回 None=沿用配置默认。

    Raises:
        ValueError: 两臂同时指定——消融臂自相矛盾，静默取其一会让工件里的臂
            与命令意图不一致且看不出来，故 fail fast。
    """
    if enable and disable:
        raise ValueError("--enable-stagnation 与 --no-stagnation 互斥，请只指定其一")
    if enable:
        os.environ["COVERAGE_STALL_DETECT_ENABLE"] = "true"
        return "true"
    if disable:
        os.environ["COVERAGE_STALL_DETECT_ENABLE"] = "false"
        return "false"
    return None


# ─── 主基准测试函数 ────────────────────────────────────────────────────────────


def _compute_mutation_scores_for_baseline(
    bl_results: list[dict[str, Any]],
    dataset_tasks: dict[str, BenchmarkTask],
    max_mutants: int,
) -> None:
    """1.2 变异得分：对每个任务的"生成测试 vs 被测源码"计算 mutation_score。

    就地写回 bl_results[].mutation_score（float 0.0-1.0）；任务无
    generated_test / 无变异体可生成时写 None（保持键集合同构，
    汇总层 mutation_score_metrics 会跳过 None）。

    实现口径：复用 experiments/mutation_testing.compute_mutation_score
    （内置 AST 级轻量变异生成器，每任务 ≤ max_mutants 个变异体，
    每个变异体跑一次 pytest 子进程判杀死/存活）。失败测试（passed=False
    且无 generated_test）直接跳过，避免对空测试做无效变异。

    Args:
        bl_results: 该基线的逐任务结果列表（就地修改）。
        dataset_tasks: task_id → BenchmarkTask 映射（提供 instance_code）。
        max_mutants: 每任务最多评估的变异体数量。
    """
    from experiments.mutation_testing import compute_mutation_score

    for r in bl_results:
        task_id = r.get("task_id")
        task = dataset_tasks.get(task_id)
        if task is None or not task.instance_code:
            r["mutation_score"] = None
            continue
        # 1.2 接线：generated_test 已写进 results 行（_build_task_result 成功分支）；
        # 旧 JSON（无该键）或失败分支（None）时跳过——变异得分依赖
        # "生成测试 + 被测源码"两者，缺一即 None 兜底
        test_code = r.get("generated_test")
        if not test_code:
            r["mutation_score"] = None
            continue
        # 被测模块文件路径：占位即可——2026-09-26 round9（P1 模块名对齐
        # 修复）后 _run_mutant_tests 的沙箱模块名由
        # _infer_imported_module_name(test_code) 解析（取测试代码 import 语句
        # 的被导入模块名），module_file 参数仅作文档性引用。
        import tempfile

        placeholder_module_file = os.path.join(tempfile.gettempdir(), "placeholder_module.py")
        result = compute_mutation_score(
            source_code=task.instance_code,
            test_code=test_code,
            module_file=placeholder_module_file,
            max_mutants=max_mutants,
        )
        r["mutation_score"] = result.get("mutation_score")
        logger.info(
            "    [%s] %s 变异得分: %s（%d/%d 杀死，耗时 %.1fs）",
            task_id,
            r.get("repo", ""),
            result.get("mutation_score"),
            result.get("mutants_killed", 0),
            result.get("mutants_total", 0),
            result.get("elapsed_seconds", 0.0),
        )


# MDO「不可测」分支统一置 None 的键集合（单一来源）。
#
# 四条兜底路径（no_task_or_test / no_gold_fixed_material / no_gold_material /
# exception）与本函数正常出口必须**键集合同构**——否则分析侧按列读取时，
# "不可测"行会缺列。T6（2026-10-11 独立评审落地）：mdo.as_dict() 在池未达
# 下限时新增 `mdo_provisional` / `mdo_raw` 两个键，兜底分支不带即破坏同构。
_MDO_UNAVAILABLE_KEYS: tuple[str, ...] = (
    "mdo_available",
    "mtr",
    "mdr",
    "mdo_crash_rate",
    "mdo_pool_size",
    "mdo_pool_floor_ok",
    "mdo_provisional",
    "mdo_raw",
)


def _compute_mdo_for_baseline(
    bl_results: list[dict[str, Any]],
    dataset_tasks: dict[str, BenchmarkTask],
    max_mutants: int = 120,
) -> None:
    """MDO（政策无关变异判别力度量）逐任务写回 details[] 七个字段。

    **动机（外部评审 §3.4 / 优化方案 v2 §2.3）**：原有 `detection_rate` 与修复
    策略**数学耦合**——系统用补丁把测试"改绿"后，最终测试在缺陷原码上不再变红，
    该行 detection 归零（实测 `red_then_green` 93 行中 34 行因此丢失检出证据）。
    因此"测试生成质量"无法与"修复策略"分离度量。MDO 以**行为差异 + 断言结果**
    为判据、不涉及任何补丁动作，从而做到政策无关。

    **与 `_compute_mutation_scores_for_baseline` 的分工**：
    - `mutation_score`：对缺陷代码变异，判据 rc==1（退出码）；
    - `mdr`（本函数）：判据是"行为发生偏差 **且** 测试以断言失败结束"，
      并把崩溃（rc>=2/5）单列为 `mdo_crash_rate`，不计入判别。
    实测差异：弱断言（只 `assert isinstance(...)`）在 `mutation_score` 下得
    **1.0**，在 `mdr` 下只有 **0.2**——这是本指标存在的理由。

    **前置条件（缺一即 None，不误报 0）**：测试在 **gold 修复后代码**上必须全绿
    （= 与 M1 detection 的 F2P 第二段同源，保证"红"是缺陷特异而非恒失败）；
    变异体池非空；gold 材料齐备。
    池规模未达下限（p=10% → 29）时 `mdo_pool_floor_ok=False`，调用方须据此
    避免在饱和池上出结论。

    Args:
        bl_results: 该基线的逐任务结果列表（就地修改）。
        dataset_tasks: task_id → BenchmarkTask 映射。
        max_mutants: 池上限（用扩展算子集，默认 120）。
    """
    from experiments.mutation_testing import ExtendedMutationGenerator
    from src.measurement.mdo import compute_mdo

    generator = ExtendedMutationGenerator(max_per_task=max_mutants)
    for r in bl_results:
        task_id = str(r.get("task_id") or "")
        task = dataset_tasks.get(task_id)
        test_code = r.get("generated_test")
        if task is None or not test_code:
            # 键集合同构：缺材料一律 None（不可测），不改既有键
            for k in _MDO_UNAVAILABLE_KEYS:
                r[k] = None
            r["mdo_not_available_reason"] = "no_task_or_test"
            continue
        # **基准必须是 gold 修复后代码**（语义关键，2026-10-11 修正）：
        # MDO 度量的是"测试对**正确实现**的变异体是否具备判别力"，因此测试
        # 必须在基准上全绿——这与 M1 detection 的 F2P 第二段判据同源
        # （buggy 红 ∧ gold 绿），保证"红"是**缺陷特异**的而非恒失败。
        # 若误用 instance_code（缺陷代码），则测试本应红 → MDO 会大面积
        # 记 not_measurable（实测 aitester 臂几乎全部不可测）。
        from experiments._m1_metrics import _extract_gold_material, _gold_fixed_code

        base_code = _gold_fixed_code(task)
        if not base_code.strip():
            for k in _MDO_UNAVAILABLE_KEYS:
                r[k] = None
            r["mdo_not_available_reason"] = "no_gold_fixed_material"
            continue
        mat = _extract_gold_material(task)
        if mat is None:
            for k in _MDO_UNAVAILABLE_KEYS:
                r[k] = None
            r["mdo_not_available_reason"] = "no_gold_material"
            continue
        try:
            # 模块名与 M1 同源派生（保证测试 import 名与沙箱写盘名一致）
            module_name = str(mat[0])
            pool = generator.generate(base_code)
            res = compute_mdo(
                base_code=base_code,
                test_code=str(test_code),
                module_name=module_name,
                mutants=pool,
                # 单变异体超时与 M1 判分同量级（30s）；池大时总耗时为
                # O(池) × 2 次执行（行为探针 + 测试），调用方须据此估预算。
                timeout_seconds=30,
            )
        except Exception:
            logger.warning("MDO 计算失败（task=%s），记不可测", task_id, exc_info=True)
            for k in _MDO_UNAVAILABLE_KEYS:
                r[k] = None
            r["mdo_not_available_reason"] = "exception"
            continue
        payload = res.as_dict()
        r["mdo_available"] = payload["mdo_available"]
        r["mtr"] = payload["mtr"]
        r["mdr"] = payload["mdr"]
        r["mdo_crash_rate"] = payload["crash_rate"]
        r["mdo_pool_size"] = payload["mdo_pool_size"]
        r["mdo_pool_floor_ok"] = payload["mdo_pool_floor_ok"]
        r["mdo_not_available_reason"] = payload["mdo_not_available_reason"]
        # T6（2026-10-11 独立评审落地）：池未达下限时 as_dict() 已把规范键
        # mtr/mdr/crash_rate 置 None 并把原始值移入 mdo_raw——本函数是**逐键
        # 显式复制**，不补这两行则新语义在工件层不可见（mdo_provisional /
        # mdo_raw 缺失 → 审计侧无法区分"未测"与"测得但池不足"）。
        # 池达下限时为 False/None（与默认键集合同构）。
        r["mdo_provisional"] = payload.get("mdo_provisional", False)
        r["mdo_raw"] = payload.get("mdo_raw")
        logger.info(
            "    [%s] MDO: MTR=%s MDR=%s CRASH=%s 池=%s(达下限=%s) status=%s",
            task_id,
            payload["mtr"],
            payload["mdr"],
            payload["crash_rate"],
            payload["mdo_pool_size"],
            payload["mdo_pool_floor_ok"],
            payload["mdo_status"],
        )


def _compute_mutation_detection_for_baseline(
    bl_results: list[dict[str, Any]],
    dataset_tasks: dict[str, BenchmarkTask],
    n_mutants: int,
    seed: int = 42,
) -> None:
    """R5（2026-10-05 审查建议）：变异检出率逐任务写回 details[] 三个新字段。

    口径（SWE-Mutation 2026，测试有效性客观裁决）：生成的测试在 **gold
    修复代码**上全绿、且在其 AST 变异体上变红的比例。与 mutation_score
    （对缺陷代码变异，生成器视角故障覆盖）互补——主批次 detection_rate=2% /
    false_fix=90% 说明生成测试大多检不出缺陷，本指标给出"测试究竟有没有
    效"的独立客观测量（纯子进程，零 LLM）。

    就地写回：
    - mutation_detection_rate：float | None（缺 gold fixed 材料 / 测试在
      fixed 上不绿 / 无变异体时 None——保守不误报 0，统计层按不可测跳过）；
    - mutants_killed / mutants_total：int（跳过时 0/0 占位，与函数返回同构）。

    fixed 材料来源：复用 _m1_metrics._gold_fixed_code（单文件任务把
    metadata["fixed"] 应用到 instance_code；跨文件任务用 fixed_module_code；
    SWE-bench / 无 gold 材料 → 空 → 跳过写 None）。模块名与 M1 指标同源
    （_extract_gold_material 从 task_id 末段派生），保证生成测试的 import
    名与变异沙箱写盘名一致。

    Args:
        bl_results: 该基线的逐任务结果列表（就地修改）。
        dataset_tasks: task_id → BenchmarkTask 映射。
        n_mutants: 每任务最多评估的变异体数量。
        seed: 变异体随机采样种子（跨运行可复现）。
    """
    from experiments._m1_metrics import _extract_gold_material, _gold_fixed_code
    from experiments.mutation_detection import mutation_detection_rate

    for r in bl_results:
        task_id = str(r.get("task_id") or "")
        task = dataset_tasks.get(task_id)
        test_code = r.get("generated_test")
        fixed_code = _gold_fixed_code(task) if task is not None else ""
        if task is None or not test_code or not fixed_code.strip():
            # 缺任务映射 / 无生成测试 / 缺 gold fixed 材料 → 跳过记 None
            r["mutation_detection_rate"] = None
            r["mutants_killed"] = 0
            r["mutants_total"] = 0
            continue
        mat = _extract_gold_material(task)
        # 有 fixed 材料但无 gold test_cases 的边缘任务：模块名按 M1 同规则
        # 从 task_id 末段派生（与 _extract_gold_material 一致；P1-4 中性化
        # 在生成层完成后，此处自动为中性 task_XXXX）
        module_name = mat[0] if mat is not None else str(task.task_id).split("__")[-1].replace("-", "_")[:50]
        result = mutation_detection_rate(
            fixed_code=fixed_code,
            test_code=str(test_code),
            module_name=module_name,
            n_mutants=n_mutants,
            seed=seed,
        )
        r["mutation_detection_rate"] = result.get("rate")
        r["mutants_killed"] = result.get("mutants_killed", 0)
        r["mutants_total"] = result.get("mutants_total", 0)
        logger.info(
            "    [%s] %s 变异检出率: %s（%s/%s 检出，%.1fs%s）",
            task_id,
            r.get("repo", ""),
            result.get("rate"),
            result.get("mutants_killed", 0),
            result.get("mutants_total", 0),
            result.get("elapsed_seconds", 0.0),
            f"，跳过：{result.get('skip_reason', '')}" if result.get("skipped") else "",
        )


def _apply_deterministic_temperature() -> None:
    """R11：强制 TEMPERATURE=0.0（三处级联，可独立测试的纯副作用函数）。

    config.TEMPERATURE 与 base_agent.TEMPERATURE 均为 import 时求值的
    模块级常量（from config import TEMPERATURE 是值拷贝），仅改
    os.environ 不生效；本函数三处同步：
    1. os.environ["TEMPERATURE"]="0.0"（供 provenance temperature 快照记录真实生效值）；
    2. config.TEMPERATURE=0.0（后续 import config 的读取方）；
    3. src.agents.base_agent.TEMPERATURE=0.0（LLM 调用侧的 from-import 拷贝，
       base_agent.py `_get_or_create_chat_client` 与 `_call_llm` 直接读该名）。
    """
    import config as _config_module
    import src.agents.base_agent as _base_agent_module

    os.environ["TEMPERATURE"] = "0.0"
    _config_module.TEMPERATURE = 0.0
    _base_agent_module.TEMPERATURE = 0.0
    logger.info("R11 确定性采样模式：TEMPERATURE 强制 0.0（config + base_agent 级联）")


# ─── S29（2026-10-11 独立评审落地）：模型版本指纹探针 ────────────────────────
#
# F13/S29：`deepseek-flash` 是**浮动别名**，provenance 此前只记录别名，无任何
# 可校验的版本指纹 → 同一 87 任务 × 3 seed 的 plain_llm 检出率从存档 1.5%
# (4/261) 漂移到 19.2%(50/261)，**全部历史结论失去可复现性**。
#
# 本探针在跑批开始时对**固定 prompt** 做一次贪心（temperature=0.0）调用，
# 把 (a) API 实际返回的 model 名、(b) system_fingerprint、(c) 响应文本的
# sha256 三者写入 provenance：同别名不同快照 → 指纹不同 → 批次不可与历史
# 批次合并统计（预注册停止规则：快照失效即实验作废）。
#
# 纪律：
#   1. **离线可降级**——探针失败（无凭证 / API 不可达 / 超时）绝不让整个
#      跑批崩溃，只写 pinned=False + error（事实标注优先于"漂亮通过"）；
#   2. **进程内缓存**——同进程只调一次（多基线 / 多 seed 复跑不重复烧配额）;
#   3. 探针为**观测**，不参与任何评分路径（失败不影响任务执行）。

# 固定探针 prompt：内容无关紧要，只要**跨批次逐字节一致**（同一 prompt 在
# 同一模型快照上应产生同一贪心输出；不同快照可能产生不同输出）。
_FINGERPRINT_PROBE_PROMPT = "Reply with exactly: PROBE"

# 探针响应作为指纹证据的最小长度（更短视为无效证据—空响应无法区分快照）。
_FINGERPRINT_MIN_RESPONSE_LEN = 1

# 进程内缓存：{requested_alias: fingerprint_dict}。同一进程只探一次
# （多 seed / 多基线 / 重入路径共享）；测试可清空本字典重置缓存。
_MODEL_FINGERPRINT_CACHE: dict[str, dict[str, Any]] = {}

# pinned=True 的必要条件：三项指纹证据齐全。system_fingerprint 缺失时
# （部分兼容网关不返回该字段）如实记为 pinned=False——这正是本探针要
# 暴露的"该 provider 无法锁定版本"状态，不得用"有 model 名就算锁定"糊过去。
_FINGERPRINT_REQUIRED_KEYS: tuple[str, ...] = ("requested_alias", "returned_model", "system_fingerprint")


def _fingerprint_missing_keys(requested_alias: str | None, returned_model: Any, system_fingerprint: Any) -> list[str]:
    """计算未锁定项（必需键中取不到值的那些）。

    键集合与判定口径的**单一来源**：成功路径与失败降级路径共用本函数，
    保证"探针失败"与"provider 不返回 system_fingerprint"在工件里以同一种
    方式表达（missing 列表），下游 gate / 分析不必分情况解析。
    """
    values: dict[str, Any] = {
        "requested_alias": requested_alias,
        "returned_model": returned_model,
        "system_fingerprint": system_fingerprint,
    }
    return [key for key in _FINGERPRINT_REQUIRED_KEYS if not values.get(key)]


def _fingerprint_response_text(response: Any) -> str | None:
    """从 ChatCompletion 响应提取首条 message 的文本内容（取不到返回 None）。

    分步 getattr（而非 `response.choices[0].message.content` 一步到底）：
    mock / 兼容网关可能返回 choices 为空或 message 不是对象，任一步缺失
    都返回 None，由调用方如实记 pinned=False，不抛异常中断跑批。
    """
    try:
        choices = getattr(response, "choices", None)
        if not choices:
            return None
        first = choices[0]
        message = getattr(first, "message", None)
        if message is None:
            return None
        content = getattr(message, "content", None)
        return content if isinstance(content, str) else None
    except (AttributeError, IndexError, KeyError, TypeError):
        return None


def _build_fingerprint_from_response(
    response: Any,
    requested_alias: str | None,
    probe_at: str,
) -> dict[str, Any]:
    """从探针响应构造 model_fingerprint 块（纯函数——不发起任何调用）。

    Args:
        response: APIManager.call 返回的 ChatCompletion 对象（测试传 mock）。
        requested_alias: 本次请求携带的模型别名（config 侧的 MODEL_NAME）。
        probe_at: 探针时刻（UTC ISO 时间戳，由调用方注入以便测试断言）。

    Returns:
        含 requested_alias / returned_model / system_fingerprint / probe_sha256 /
        probe_at / pinned / missing / error 的字典（键集合恒定，便于下游读取）。

    Raises:
        RuntimeError: 响应用例不足（无文本内容）时抛出——由调用方捕获并
            降级为 pinned=False（本函数不做静默兜底，避免"空哈希"冒充指纹）。
    """
    content = _fingerprint_response_text(response)
    if content is None or len(content) < _FINGERPRINT_MIN_RESPONSE_LEN:
        raise RuntimeError("探针响应无文本内容，无法构造指纹")

    returned_model = getattr(response, "model", None)
    system_fingerprint = getattr(response, "system_fingerprint", None)

    fingerprint: dict[str, Any] = {
        "requested_alias": requested_alias,
        "returned_model": returned_model,
        "system_fingerprint": system_fingerprint,
        "probe_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "probe_at": probe_at,
    }
    missing = _fingerprint_missing_keys(requested_alias, returned_model, system_fingerprint)
    fingerprint["missing"] = missing
    fingerprint["pinned"] = not missing
    if missing:
        # 如实给出"为何未锁定"：兼容网关不返回 system_fingerprint 是常见成因，
        # 不能与"探针根本没跑"混为一谈。
        fingerprint["error"] = f"指纹字段缺失（无法锁定模型版本）: {', '.join(missing)}"
    else:
        fingerprint["error"] = None
    return fingerprint


def collect_model_fingerprint(
    requested_alias: str | None,
    cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """采集（或复用缓存的）模型版本指纹（S29）。

    Args:
        requested_alias: 请求侧模型别名（None 时仍尝试探针，但 pinned 必为
            False——无别名则"别名→快照"映射不可登记）。
        cache: 进程内缓存（默认模块级 _MODEL_FINGERPRINT_CACHE）；测试可传
            独立 dict 做隔离，无需清全局状态。

    Returns:
        model_fingerprint 块（键集合恒定）。探针失败时 pinned=False 且
        error 为脱敏后的异常文本——**任何情况下都不抛异常**（跑批不得因
        探针失败而崩溃）。
    """
    _cache = _MODEL_FINGERPRINT_CACHE if cache is None else cache
    _cache_key = requested_alias or "<none>"
    cached = _cache.get(_cache_key)
    if cached is not None:
        return cached

    probe_at = datetime.now(UTC).isoformat()
    try:
        # enable_health_checker=False：探针无需后台健康检查线程（该线程会
        # 周期性发起真实请求，消耗配额且是构造副作用）。
        # 口径说明：APIManager 与 llm_client._get_llm_config 同源读
        # config.LLM_CONFIGS，均取"第一个有效配置"——探针与跑批流量因此
        # 落在同一 provider/model 上（这是指纹有效的前提）。**已知边界**：
        # 线程局部覆盖（_thread_local.model_name）只在 worker 线程生效，
        # 主线程探针取全局配置，故不覆盖"每线程不同模型"的场景。
        from src.api.api_manager import APIManager

        response = APIManager(enable_health_checker=False).call(
            [{"role": "user", "content": _FINGERPRINT_PROBE_PROMPT}],
            # 贪心解码：同快照应给出同一输出，使 probe_sha256 成为快照证据
            temperature=0.0,
            # 上限须容纳**思维链 token**（真实调用实测，2026-10-11）：
            # deepseek-flash 系默认开启思考，单次探针实测 reasoning 56–65
            # tokens。原 max_tokens=16 会把预算全部耗在思考上、正文被截成
            # 'PRO' 且 finish_reason='length'——探针因此恒失败、pinned 恒
            # False，S29 形同虚设。64 实测正文完整（'PROBE'，
            # finish_reason='stop'），成本仍可忽略。
            max_tokens=64,
        )
        fingerprint = _build_fingerprint_from_response(response, requested_alias, probe_at)
        if requested_alias and fingerprint.get("returned_model") != requested_alias:
            # 别名 → 实际模型不一致：可能只是命名口径差异，但必须留痕
            # （"请求的"与"实际服务的"不是同一字符串时，跨批次可比性存疑）。
            fingerprint["alias_mismatch"] = True
        else:
            fingerprint["alias_mismatch"] = False
    except Exception as e:
        fingerprint = {
            "requested_alias": requested_alias,
            "returned_model": None,
            "system_fingerprint": None,
            "probe_sha256": None,
            "probe_at": probe_at,
            # 失败路径的缺失项也走同一口径：别名本身可解析时**不**列为缺失
            # （否则"探针没跑"与"别名读不到"混为一谈）
            "missing": _fingerprint_missing_keys(requested_alias, None, None),
            "pinned": False,
            "alias_mismatch": None,
            # 异常文本可能回显带 token 的 base_url / 网关体——出口统一脱敏
            # （与 api_manager 的 _redact 口径一致）
            "error": _redact_credential_text(f"{type(e).__name__}: {e}")[:300],
        }

    _cache[_cache_key] = fingerprint
    if fingerprint.get("pinned"):
        logger.info(
            "S29 模型指纹：pinned=True（alias=%s, model=%s, fingerprint=%s, probe=%s…）",
            requested_alias,
            fingerprint.get("returned_model"),
            fingerprint.get("system_fingerprint"),
            str(fingerprint.get("probe_sha256"))[:12],
        )
    else:
        logger.warning(
            "S29 模型指纹：pinned=False（alias=%s，缺失=%s，error=%s）——"
            "本批次模型版本未锁定，预注册停止规则下不得与历史批次合并统计",
            requested_alias,
            fingerprint.get("missing"),
            fingerprint.get("error"),
        )
    return fingerprint


def _redact_credential_text(text: str) -> str:
    """对探针异常文本做凭证脱敏（复用项目统一的脱敏工具，缺失时降级）。

    探针失败信息会写入结果 JSON（对外工件），异常里可能回显 base_url 的
    api_key 查询串 / 网关响应体。脱敏工具不可用时退化为"截断"（不阻断
    provenance 写入——宁可少信息，不可写入明文凭证）。
    """
    try:
        from src.utils.logging_utils import redact_text

        return str(redact_text(text))
    except Exception:
        return "[redact-unavailable] " + text[:200]


# ─── Q-3/R-3（2026-10-18）：批后处理墙钟可观测 hook ──────────────────────────
# 纯观测：只把实测 wall 收集进 stage_durations，不改变任何判分/重试/超时逻辑。
# 字段语义：summary["postprocess_wall"] = {stage: {wall_s, n_tasks, mean_s,
# p50_s, p95_s, max_s, timed_out_tasks}}；当前样本粒度 = 每基线一次
# （summary["postprocess_wall_granularity"]="per_baseline"）；mutation 关闭时
# 字段仍存在但为空映射（只包含实际执行的阶段）。


def _run_postprocess_stage(
    stage_durations: dict[str, list[float]],
    stage: str,
    *callables: Callable[[], Any],
) -> None:
    """跑一个后处理阶段并把实测 wall 追加到 ``stage_durations[stage]``。

    Q-3/R-3：阶段内调用**原样执行**（异常不吞、不改重试/超时）；无论成功或
    异常都追加一条 wall 样本（StageTimer.__exit__ 已在异常路径 stop），随后
    异常原样上抛。每基线调用一次 ⇒ 样本粒度 per_baseline。

    Args:
        stage_durations: {阶段名: 每基线实测 wall 列表}（就地追加）。
        stage: 后处理阶段名（``mutation`` / ``mdo``；Q-3 模块登记名）。
        *callables: 该阶段内按序执行的调用（零参可调用，返回忽略）。
    """
    timer = StageTimer(stage)
    try:
        with timer:
            for func in callables:
                func()
    finally:
        # 异常路径也记录（finally 先于异常继续传播执行）；timer.wall_s 在
        # __exit__ 中已累计本次 wall。
        stage_durations.setdefault(stage, []).append(timer.wall_s)


def _run_baseline_postprocess_with_wall(
    bl_results: list[dict[str, Any]],
    tasks: list[Any],
    stage_durations: dict[str, list[float]],
    *,
    mutation_enabled: bool,
    mutation_max_mutants: int,
    seed: int,
) -> None:
    """单基线后处理（1.2 mutation scoring/detection + MDO）——Q-3 wall 计时包装。

    **默认调用路径与历史内联块逐字节等价**：执行顺序/入参/日志（logger.info
    "启用变异得分评估"）完全不变；唯一新增是每阶段墙钟样本追加到
    ``stage_durations``。``mutation_enabled=False`` 时立即返回——不构建 task_map
    （零额外工作、零行为差异），也不产生任何阶段键。

    Args:
        bl_results: 该基线逐任务结果行（就地写入 mutation/MDO 字段）。
        tasks: 数据集任务列表（仅在开关启用时构建 task_id → task 映射）。
        stage_durations: 墙钟样本收集器（就地追加）。
        mutation_enabled: 1.2 变异得分开关（mutation/MDO 共用挂点）。
        mutation_max_mutants: 每任务变异体上限。
        seed: 变异体生成种子（与历史调用一致）。
    """
    if not mutation_enabled:
        return
    # task_id → BenchmarkTask 映射（同一任务跨基线复用 instance_code）
    task_map = {t.task_id: t for t in tasks}
    logger.info("启用变异得分评估（1.2）：每任务 ≤ %d 变异体", mutation_max_mutants)
    _run_postprocess_stage(
        stage_durations,
        "mutation",
        lambda: _compute_mutation_scores_for_baseline(bl_results, task_map, mutation_max_mutants),
        lambda: _compute_mutation_detection_for_baseline(bl_results, task_map, mutation_max_mutants, seed=seed),
    )
    _run_postprocess_stage(
        stage_durations,
        "mdo",
        lambda: _compute_mdo_for_baseline(bl_results, task_map),
    )


def _postprocess_wall_summary_fields(
    stage_durations: dict[str, list[float]],
) -> tuple[dict[str, Any], list[str]]:
    """构建批次 summary 的 postprocess_wall 两个键 + 阈值告警列表。

    Returns:
        ``(fields, warnings)``：fields 含 ``postprocess_wall``（稳定 JSON 形状，
        无执行阶段时为 ``{}``）与 ``postprocess_wall_granularity="per_baseline"``；
        warnings 为超阈值阶段消息（供调用方 logger.warning）。
    """
    wall = build_postprocess_wall(stage_durations, warn_s=postprocess_warn_s())
    fields: dict[str, Any] = {
        "postprocess_wall": wall,
        # 当前 hook 粒度：每基线一个样本（每阶段 wall = 该基线后处理调用总 wall）。
        # 任务级/变异体级更细粒度留待后续，Q-3 模块 API 不变。
        "postprocess_wall_granularity": "per_baseline",
    }
    return fields, list(wall.warnings)


def _attach_postprocess_wall_to_summary(
    summary: dict[str, Any],
    stage_durations: dict[str, list[float]],
) -> None:
    """把后处理墙钟字段写入批次 summary，并逐条 logger.warning 阈值告警。

    纯新增：只 update 两个键（``postprocess_wall`` / ``postprocess_wall_granularity``），
    不触碰既有 summary 字段（判分/统计口径零变化）。
    """
    fields, warnings = _postprocess_wall_summary_fields(stage_durations)
    summary.update(fields)
    for message in warnings:
        logger.warning("%s", message)


# ─── A03（2026-10-18 第三方审查，P1）：.repro_provenance 的 GIT_SHA 消费 ──────
# 背景：Dockerfile.repro 通过 `docker build --build-arg GIT_SHA=...` 把提交 SHA
# 写入容器内 /workspace/.repro_provenance；但 .dockerignore 排除 .git，容器内
# `git rev-parse HEAD` 必然失败——历史实现只把 marker 当"是否在复现容器内"的
# 存在性标记（environment.in_docker_repro），从不读取其中的 GIT_SHA，结果
# provenance.git_sha 在复现容器内为 None，"build-arg 使提交可追溯"的承诺落空。
# 现口径（本组 helper 为单一实现，environment 与 provenance 两块共用）：
#   - 有 git 元数据：以 git rev-parse 为 git_sha 来源，同时记录 marker 值并校验
#     一致性（git_sha_matches_marker=true/false/null）；
#   - 无 git（复现容器 / 源码 tar 包）：以 marker 的 GIT_SHA 为来源
#     （git_sha_source="repro_provenance"）；
#   - 两者都没有：git_sha=None、git_sha_source=None（如实标注"不可追溯"）。
# 不新增环境变量；marker 路径固定为工作目录下 .repro_provenance（与
# Dockerfile.repro 的 WORKDIR=/workspace 口径一致，也与历史 in_docker_repro 检查点一致）。
_REPRO_PROVENANCE_FILE = ".repro_provenance"
_REPRO_UNKNOWN_SHA_VALUES = frozenset({"", "unknown", "none", "null"})


def _read_repro_provenance_marker(workspace_dir: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """读取复现容器 marker（``GIT_SHA=<sha>``）并解析。

    Args:
        workspace_dir: 工作目录（marker 所在目录）；None = 当前工作目录。

    Returns:
        dict：``present``（文件是否存在）、``path``（工作目录相对文件名）、
        ``git_sha``（解析出的 SHA；``unknown``/空值视为未提供 → None）、
        ``error``（读取异常信息，正常为 None）。
    """
    base = Path(workspace_dir) if workspace_dir is not None else Path(os.getcwd())
    marker = base / _REPRO_PROVENANCE_FILE
    info: dict[str, Any] = {
        "present": marker.is_file(),
        "path": _REPRO_PROVENANCE_FILE,
        "git_sha": None,
        "error": None,
    }
    if not info["present"]:
        return info
    try:
        text = marker.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        info["error"] = f"{type(e).__name__}: {e}"
        return info
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if not sep or key.strip().upper() != "GIT_SHA":
            continue
        value = value.strip()
        if value.lower() not in _REPRO_UNKNOWN_SHA_VALUES:
            info["git_sha"] = value
        break
    return info


def _resolve_git_provenance(
    workspace_dir: str | os.PathLike[str] | None = None,
    repo_dir: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """合并 git 元数据与 .repro_provenance marker，得出可审计的提交来源块。

    Args:
        workspace_dir: marker 所在工作目录；None = 当前工作目录。
        repo_dir: git 命令执行目录（仓库根）；None = 本文件上一级（仓库根）。

    Returns:
        dict：``git_sha``（生效 SHA）、``git_sha_source``
        （``"git" | "repro_provenance" | None``）、``git_available``、
        ``in_docker_repro``（marker 是否存在，等价历史字段）、
        ``repro_provenance``（marker 明细：present/path/git_sha/
        git_sha_matches_git/git_sha_conflict/error）。
    """
    marker = _read_repro_provenance_marker(workspace_dir)
    git_sha: str | None = None
    cwd = str(repo_dir) if repo_dir is not None else str(Path(__file__).resolve().parent.parent)
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd,
        )
        if proc.returncode == 0:
            git_sha = proc.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        git_sha = None

    marker_sha = marker["git_sha"]
    matches: bool | None = None
    conflict = False
    if marker_sha is not None and git_sha is not None:
        matches = marker_sha == git_sha
        conflict = not matches
        if conflict:
            logger.warning(
                "复现容器 marker 的 GIT_SHA=%s 与当前 git HEAD=%s 不一致（构建来源与运行代码不同？），"
                "已同时记录两者并标记冲突",
                marker_sha,
                git_sha,
            )
    source = "git" if git_sha is not None else ("repro_provenance" if marker_sha is not None else None)
    return {
        "git_sha": git_sha if git_sha is not None else marker_sha,
        "git_sha_source": source,
        "git_available": git_sha is not None,
        "in_docker_repro": bool(marker["present"]),
        "repro_provenance": {
            "present": bool(marker["present"]),
            "path": marker["path"],
            "git_sha": marker_sha,
            "git_sha_matches_git": matches,
            "git_sha_conflict": conflict,
            "error": marker["error"],
        },
    }


def _build_environment_provenance(
    workspace_dir: str | os.PathLike[str] | None = None,
    git_block: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造结果 JSON 的 ``environment`` 块（Python/平台/提交来源/容器标记）。

    Args:
        workspace_dir: marker 所在工作目录；None = 当前工作目录。
        git_block: 可选的 ``_resolve_git_provenance`` 结果（避免重复执行 git）；
            None 时内部解析。
    """
    import platform as _platform

    resolved = git_block if git_block is not None else _resolve_git_provenance(workspace_dir)
    return {
        "python_version": sys.version.split()[0],
        "platform": _platform.platform(),
        "git_sha": resolved["git_sha"],
        "git_sha_source": resolved["git_sha_source"],
        "in_docker_repro": resolved["in_docker_repro"],
        "repro_provenance": resolved["repro_provenance"],
    }


def run_benchmark(
    dataset_name: str = "examples",
    subset: str | None = None,
    baselines: list[str] | None = None,
    output_dir: str = "experiments/results",
    verbose: bool = False,
    task_limit: int | None = None,
    task_count: int | None = None,
    parallel: int | None = None,
    seed: int = 42,
    enable_rag: bool | None = None,
    save_state: bool = False,
    enable_mutation_scoring: bool | None = None,
    difficulty: str = "mixed",
    max_pattern_repeat: int | None = None,
    deterministic: bool = False,
    per_task_token_caps: str | None = None,
    dirty_reason: str | None = None,
) -> dict[str, Any]:
    """
    批量运行基准测试，支持多基线方法对比和消融实验。

    Args:
        dataset_name: 数据集名称。
        subset: 数据子集。
        baselines: 要运行的基线方法列表。
        output_dir: 结果输出目录。
        verbose: 是否输出详细日志。
        task_limit: 限制运行任务数量。
        task_count: 合成数据集任务数量。
        parallel: 并行任务数。
        seed: 合成数据集随机种子（此前硬编码为 42，--seed 参数被静默忽略；
               现透传到 SyntheticDataset，保证实验可复现）。
        enable_rag: RAG 开关（P1：此前 RAG 默认关闭且未纳入主实验）。
            None 时沿用 config.ENABLE_RAG；True/False 显式覆盖。
        save_state: 是否把环节级状态落盘到 output_dir/raw/（P0-2 排查工具数据基础）。
        enable_mutation_scoring: 1.2 变异得分评估开关。None 时沿用
            config.ENABLE_MUTATION_SCORING（默认 False）；True 时在基线
            结果构建后逐任务调用 compute_mutation_score，把 mutation_score
            写回 details[]（缺失 generated_test / 无变异体可生成时写 None）。
        difficulty: P0 2.1 合成数据集分层难度（仅对 synthetic 数据集生效）。
            可选值："mixed"（默认，历史口径）/ "level1" / "level2" /
            "level3"（跨文件）/ "level4"（边界+异常隐蔽缺陷）。
        max_pattern_repeat: AA（2026-10-06）合成数据集同池模板重复上限
            （仅 synthetic 生效）。None（默认）= 历史口径；>=1 透传
            SyntheticDataset，防单 pattern 分布塌缩（DATA_CARD §2/§3）。
        deterministic: R11（2026-10-05 审查 P1）确定性采样模式。True 时
            强制 TEMPERATURE=0.0（级联 config 与 base_agent 命名空间——
            二者均为 import 时求值，仅改 os.environ 不生效）+ os.environ
            同步（供 provenance 快照记录 temperature=0.0）。主批次复现
            实验建议开启（配合干净 git tag，缓解"LLM 输出非确定性导致
            结果不可复现"的审查缺口）。默认 False 历史口径不变。
        per_task_token_caps: AM1（2026-10-06 第十三轮审查 / 预注册 E6
            执行前置）臂级每任务 token 硬上限映射串
            （如 "aitester=4223,plain_llm_df=26115"；None = 历史口径
            无 cap）。解析经 parse_per_task_token_caps（未知臂/非法值
            fail-fast）；超限走既有 BudgetExceededError →
            BUDGET_EXCEEDED 停止通道，结果行透出 token_budget_capped。

    Returns:
        汇总结果字典。
    """
    # AM1：臂级 token 上限解析（fail-fast，入口即校验）
    token_caps = parse_per_task_token_caps(per_task_token_caps)
    if token_caps:
        logger.info("AM1 臂级每任务 token 上限：%s", token_caps)
    # R11 确定性采样：三处级联更新（详见 _apply_deterministic_temperature）
    if deterministic:
        _apply_deterministic_temperature()
    # P0 4.2 追踪层主动启用：默认 AITESTER_TRACE_DIR=results/traces/（可被
    # 环境变量覆盖；设置 AITESTER_TRACE_DIR= 为空串可显式关闭追踪）。
    # 节点级 JSONL 记录（输入长度、输出长度、token、耗时、路由决策）随
    # 工作流执行自动追加到 <task_uuid>.trace.jsonl，供 SWE-bench 失败
    # 根因分析直接消费（此前追踪默认关闭 → 无节点级数据 → 无法做
    # "哪个节点消耗了最多 token / 哪次路由决策导致了空响应" 的结构化回放）。
    import os as _os

    _trace_dir = _os.environ.get("AITESTER_TRACE_DIR", "").strip()
    if not _trace_dir:
        import pathlib as _pathlib

        _trace_dir = str(_pathlib.Path(output_dir) / "traces") if output_dir else "results/traces"
        _os.environ["AITESTER_TRACE_DIR"] = _trace_dir
        logger.info(
            "P0 4.2 追踪层默认启用：AITESTER_TRACE_DIR=%s（节点级 JSONL 记录）",
            _trace_dir,
        )
    else:
        logger.info("追踪层已配置：AITESTER_TRACE_DIR=%s", _trace_dir)

    # RAG 开关在数据集加载前生效（检索发生在工作流节点内，切换时机不影响正确性）
    rag_enabled = _apply_rag_setting(enable_rag)
    if baselines is None:
        baselines = ["aitester"]

    unknown = [b for b in baselines if b not in BASELINE_REGISTRY]
    if unknown:
        raise ValueError(f"不支持的基线方法: {unknown}，支持: {list(BASELINE_REGISTRY.keys())}")

    # X1（2026-10-05 审查 P0-4a）：缓存实验命名空间自动设置。
    # 背景：LLM 文件缓存键不含 seed（seed 只作用于任务采样，不传 API）——
    # 缓存开启时多 seed 复跑是同一响应的确定性重放，统计独立性失效。
    # 修复：缓存开启且用户未显式设 AITESTER_CACHE_NAMESPACE 时，自动设为
    # "seed<N>"（不同 seed → 不同缓存命名空间 → 各自真实调用；同 seed
    # 复跑共享缓存 = 可复现性保留）。缓存关闭时无需隔离（无缓存可串）。
    # 注意：os.environ 为进程级，--parallel 下同批全部任务同 seed 同批
    # 次共享同一命名空间——正是期望语义（批次内命中 OK，跨 seed 隔离）。
    if os.environ.get("AITESTER_LLM_CACHE", "1") != "0" and not os.environ.get("AITESTER_CACHE_NAMESPACE"):
        os.environ["AITESTER_CACHE_NAMESPACE"] = f"seed{seed}"
        logger.info(
            "X1 缓存命名空间：AITESTER_CACHE_NAMESPACE=seed%d（多 seed 复跑独立性隔离；同 seed 复跑仍共享缓存）",
            seed,
        )

    logger.info("加载数据集: %s (subset=%s, seed=%d)", dataset_name, subset, seed)

    if dataset_name in ("synthetic", "synth"):
        tc = task_count or 60
        logger.info(
            "生成合成数据集：%d 个任务（seed=%d, difficulty=%s, max_pattern_repeat=%s）",
            tc,
            seed,
            difficulty,
            max_pattern_repeat,
        )
        from src.datasets.synthetic_dataset import SyntheticDataset

        dataset = SyntheticDataset(
            task_count=tc, seed=seed, difficulty=difficulty, max_pattern_repeat=max_pattern_repeat
        )
        # 确保数据集已加载
        _ = dataset.tasks
    else:
        try:
            dataset = load_dataset(dataset_name, subset=subset)
        except Exception as e:
            logger.error("数据集加载失败: %s", e)
            raise

    if dataset.size == 0:
        # 0.7 P0 数据完整性修正：此前降级到内置示例数据集后，结果归档的
        # "dataset" 字段仍标原始请求名（如 "swe_bench"），但实际跑的是合成
        # 任务（task_id 前缀 examples__）——误导性归档（R-01 探路首跑暴露）。
        # 现降级时把 dataset_name 改回实际数据集名（examples），并明确标注。
        logger.warning(
            "数据集 %s（subset=%s）为空，静默降级到内置示例数据集 examples——"
            "结果归档将标 dataset=examples，非原始请求的 %s",
            dataset_name,
            subset,
            dataset_name,
        )
        dataset_name = "examples"
        subset = None
        dataset = InMemoryDataset.create_with_samples()

    tasks = dataset.tasks
    # S2（2026-10-11 独立评审落地）：**strict 剔除计数**——AITESTER_DATASET_
    # STRICT_INSTANCE_CODE=true 时，加载器把"instance_code 兜底为 issue 文本"
    # 的行**从批次剔除**（历史默认 false = 保留兜底口径）。剔除数必须入
    # provenance：否则"389 行工件 389 行缺检测率"这类缺口在结果里不可见
    # （F4/S2/K6 的根因之一就是"静默兜底 + 静默计数"）。
    # getattr 防御：非 SWE-bench 加载器（InMemory / 合成集）无本属性。
    _strict_skipped: list[str] = list(getattr(dataset, "strict_skipped_task_ids", []) or [])
    if _strict_skipped:
        logger.warning(
            "S2 strict 模式：%d 个任务因 instance_code 兜底为 issue 文本被剔除（不参与跑批）",
            len(_strict_skipped),
        )
    # 2026-09-26 全面审查（P2 正确性）：task_limit 边界归一——负数原语义
    # 为 slice 静默截断（tasks[:-1] 丢最后一个任务），0 走 else 当全量；
    # 现统一 <1 视为不限制（全量），仅正数生效，消除负数静默改任务数。
    if task_limit is not None and task_limit < 1:
        logger.warning("task_limit=%r 无效（需正整数），按全量任务处理", task_limit)
        task_limit = None
    if task_limit:
        tasks = tasks[:task_limit]
    logger.info("可用 API 配置数: %d", len(_VALID_APIS))

    if parallel is None:
        # 走 config.BENCHMARK_PARALLELISM（_parse_int_env 容错解析 + 下限校验），
        # 此前直接 int(os.getenv(...))，坏值（如 "abc"）会在 import 阶段直接 ValueError 崩溃
        parallel = BENCHMARK_PARALLELISM

    use_progress = HAS_TQDM
    logger.info("待运行任务数: %d，基线: %s，并行度: %d", len(tasks), baselines, parallel)

    os.makedirs(output_dir, exist_ok=True)
    all_results: dict[str, list[dict[str, Any]]] = {bl: [] for bl in baselines}
    total_time = 0.0

    desc = f"基准测试 [{', '.join(baselines)}]"

    with ProgressBar(len(tasks), desc=desc, enabled=use_progress) as pbar:
        if parallel > 1:
            logger.info("启用并行执行，并发度: %d", parallel)
            with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:

                def _on_task_done(task: BenchmarkTask, task_results: dict[str, Any]) -> None:
                    """单个任务完成回调：汇总结果 + 进度条 + 累计耗时。"""
                    nonlocal total_time
                    for baseline, result in task_results.items():
                        all_results[baseline].append(result)
                    elapsed_this = sum(r["elapsed_seconds"] for r in task_results.values())
                    total_time += elapsed_this
                    pbar.update(1)
                    pbar.set_description(f"{desc} - 耗时: {total_time:.1f}s")

                # 0.7 债务项 2.5：滑窗提交，保持在途 future ≤ 2×parallel，
                # 避免一次性 submit 全部任务导致大对象常驻内存
                _run_tasks_sliding_window(
                    executor,
                    tasks,
                    baselines,
                    output_dir,
                    verbose,
                    save_state,
                    max(2 * parallel, 1),
                    _on_task_done,
                    token_caps,
                )
        else:
            for task in tasks:
                logger.info("处理任务: %s", task.task_id)
                task_results = run_single_task(
                    task, baselines, output_dir, verbose, save_state=save_state, per_task_token_caps=token_caps
                )

                for baseline, result in task_results.items():
                    all_results[baseline].append(result)

                elapsed_this = sum(r["elapsed_seconds"] for r in task_results.values())
                total_time += elapsed_this
                logger.info("  本轮耗时: %.1fs（累计 %.1fs）", elapsed_this, total_time)
                pbar.update(1)
                pbar.set_description(f"{desc} - 耗时: {total_time:.1f}s")

    # 生成汇总统计
    # P1（2026-10 Docker 化实验复现）：environment provenance 块——
    # Python 版本 / git sha（有 git 时）/ 容器标记（.repro_provenance 存在时）
    # / 关键开关，写入 summary["environment"]，使任意批次结果 JSON 自带
    # 复现坐标（配合 Dockerfile.repro 的 docker run 一条命令复现）。
    # A03（2026-10-18 第三方审查 P1）：容器内 .git 被排除时，从 marker 的
    # `GIT_SHA=<sha>` 读取提交 SHA 作为 provenance 来源（不再只做存在性检查）；
    # 有 git 时同时记录两者并校验一致性。实现见 _build_environment_provenance。
    _git_block = _resolve_git_provenance(os.getcwd())
    _env_provenance: dict[str, Any] = _build_environment_provenance(os.getcwd(), git_block=_git_block)
    summary = {
        "timestamp": datetime.now().isoformat(),
        "dataset": dataset_name,
        "subset": subset,
        "seed": seed,
        "total_tasks": len(tasks),
        "baselines": baselines,
        "enable_planner": ENABLE_PLANNER,
        "enable_debugger": ENABLE_DEBUGGER,
        # P1：此前硬编码 False，现反映本次运行实际生效的 RAG 开关
        "enable_rag": rag_enabled,
        "parallelism": parallel,
        "valid_apis": len(_VALID_APIS),
        "environment": _env_provenance,
        # R46（2026-09-30 独立审查 P0）：SWE-bench 批次 P2P 门禁默认开，
        # harness_invalid（基线 P2P 不达标）实例从统计中剔除（不计入"0 解出"）。
        # 汇总含 harness_invalid_count + 剔除后的有效任务数 + 有效通过率，
        # 使"0 解出"可区分"系统无效"与"harness 无效"。
        "p2p_gate_enabled": SWE_BENCH_P2P_GATE_ENABLE,
        "p2p_gate_threshold": SWE_BENCH_P2P_GATE_THRESHOLD,
        "results": {},
    }

    # Q-3/R-3（2026-10-18）：批后处理墙钟观测收集器（阶段名 → 每基线实测 wall）。
    # 仅包含实际执行的阶段；mutation 关闭时保持空 dict，summary 字段仍存在。
    postprocess_stage_durations: dict[str, list[float]] = {}

    for baseline in baselines:
        bl_results = all_results[baseline]
        passed = sum(1 for r in bl_results if r["passed"])
        total = len(bl_results)
        # R46（2026-09-30 独立审查 P0）：harness_invalid（P2P 门禁剔除）计数。
        # 有效任务数 = total - harness_invalid_count；有效通过率 =
        # passed / 有效任务数（剔除 harness 无效实例后"0 解出"才反映
        # 系统真实能力边界，而非 harness 缺陷）。
        harness_invalid_count = sum(1 for r in bl_results if r.get("harness_invalid"))
        effective_total = total - harness_invalid_count
        effective_success_rate = round(passed / effective_total * 100, 1) if effective_total > 0 else 0
        avg_coverage = sum(r.get("coverage") or 0 for r in bl_results) / total if total > 0 else 0
        # 2026-09-27 round10 P1：iterations/elapsed_seconds 可能为 None
        # （历史落盘缺省/任务异常），裸 r["..."] KeyError/TypeError 崩溃——
        # None 视为 0（缺省语义：该任务未记录迭代/耗时，贡献 0），
        # 数值路径零变化
        avg_iterations = sum(r.get("iterations") or 0 for r in bl_results) / total if total > 0 else 0
        avg_time = sum(r.get("elapsed_seconds") or 0 for r in bl_results) / total if total > 0 else 0

        # 1.2 变异得分：在汇总统计前逐任务计算（仅当开关启用），
        # 把 mutation_score 写回 bl_results[].mutation_score，
        # 后续 summary["details"] 直接携带该字段，供
        # analyze_results._mutation_score_metrics 汇总
        mutation_enabled = ENABLE_MUTATION_SCORING if enable_mutation_scoring is None else bool(enable_mutation_scoring)
        # R5（2026-10-05 审查建议）/ MDO（2026-10-11 优化方案 v2 §3.1）：mutation
        # scoring/detection + MDO 同开关同挂点。Q-3/R-3 起三个调用移入
        # _run_baseline_postprocess_with_wall（顺序/入参/日志逐字节等价），
        # 仅新增每阶段 wall 观测（纯观测，判分/重试/超时零变化）。
        _run_baseline_postprocess_with_wall(
            bl_results,
            tasks,
            postprocess_stage_durations,
            mutation_enabled=mutation_enabled,
            mutation_max_mutants=MUTATION_MAX_MUTANTS,
            seed=seed,
        )

        summary["results"][baseline] = {
            "total_functions": total,
            "passed_count": passed,
            "failure_count": total - passed,
            "success_rate": round(passed / total * 100, 1) if total > 0 else 0,
            # R46（2026-09-30 独立审查 P0）：P2P 门禁剔除口径
            "harness_invalid_count": harness_invalid_count,
            "effective_total": effective_total,
            "effective_success_rate": effective_success_rate,
            "avg_coverage": round(avg_coverage, 1),
            "avg_iterations": round(avg_iterations, 2),
            "avg_elapsed_seconds": round(avg_time, 2),
            "total_time": round(sum(r.get("elapsed_seconds") or 0 for r in bl_results), 2),
            # 2.2 公平性对照：失败原因分布（1.2 细化后 LLM_FORMAT_ERROR/INDEX_ERROR
            # 可单独计数；未失败任务不记 error_category，不计入分布）
            "failure_category_distribution": _aggregate_failure_categories(bl_results),
            # I1（2026-10-16）：终局失效桶分布（五桶 + edge × fault_side）。
            # annotate_final_state 此前无生产消费方，分桶结果只在单测里被断言；
            # 接线后论文级"失败归因分布"可直接从批次工件复算。
            "failure_bucket_distribution": _aggregate_failure_buckets(bl_results),
            # P0-2 效率指标 + P1 RAG 检索质量（未启用 RAG 时指标全为 0/None）
            "token_metrics": _aggregate_token_metrics(bl_results),
            "rag_metrics": _aggregate_rag_metrics(bl_results),
            "details": bl_results,
        }

    # Q-3/R-3（2026-10-18）：批后处理墙钟可观测（纯观测，判分/重试/超时零变化）。
    # 字段总在：mutation 关闭时 postprocess_wall={}（只包含实际执行的阶段）；
    # 粒度 per_baseline（每基线每阶段一个 wall 样本）。
    _attach_postprocess_wall_to_summary(summary, postprocess_stage_durations)

    # M9（2026-09-29 审查 P0）：实验 provenance 块 —— 把结果 JSON 顶层
    # 补全 git SHA / 模型版本 / 温度 / max_iterations / 开关快照 / seed，
    # 使论文数字可追溯、可复现（此前结果工件只有 timestamp / dataset /
    # subset / seed / baselines / results，无 git commit SHA、无模型版本、
    # 无 temperature、无 ~118 个环境开关快照 → 跨模型/跨代码版本串味且
    # 不可复算）。
    # A03（2026-10-18 第三方审查 P1）：git 元数据与 .repro_provenance marker
    # 在 environment 块处已统一解析（_git_block），此处直接复用——无 git 的
    # 复现容器内 git_sha 来自 build-arg 写入的 marker，不再退化为 None。

    _env_snapshot_keys = [
        "MAX_ITERATIONS",
        "LLM_TIMEOUT",
        "EXECUTION_TIMEOUT",
        "TEMPERATURE",
        "ENABLE_PLANNER",
        "ENABLE_DEBUGGER",
        "ENABLE_RAG",
        "DIAGNOSIS_NODE_ENABLE",
        "TYPE_CHECK_ENABLE",
        "COST_BUDGET_ENABLE",
        "EXPERT_POOL_ENABLE",
        "MUTATION_TEST_ENABLE",
        "KERNEL_SANDBOX_ENABLE",
        "PATCH_RESAMPLE_ENABLE",
        "REPO_LEVEL_EXECUTION",
        "AITESTER_LLM_CACHE",
        "AITESTER_CACHE_ISOLATE_MODEL",
        # M7/M10/O2/O3/O8 系列新增开关（2026-09-29 审查批次）
        "MUTATION_ADVISOR_ENABLE",
        "LOGIC_SPEC_STRICT_ENABLE",
        "BOUNDARY_TRIPLETS_ENABLE",
        "FL_SPECTRAL_ENABLE",
        "FL_SPECTRAL_TOP_K",
        "BRANCH_COVERAGE_INJECT_ENABLE",
        "RAG_POISONING_FILTER",
        # R7/R35/R59（2026-09-30 独立审查批次）
        "SPEC_IR_ENABLE",
        "FLAKY_CHECK_ENABLE",
        "FLAKY_REPEAT_COUNT",
        "PIP_PACKAGE_WHITELIST_ENABLE",
        # R46：SWE-bench P2P 门禁（R46 起默认开）
        "SWE_BENCH_P2P_GATE_ENABLE",
        "SWE_BENCH_P2P_GATE_THRESHOLD",
        # X1（2026-10-05 审查 P0-3/P0-4a）：检出优先协议开关 + 缓存命名空间
        # （多 seed 独立性口径——缓存开但无命名空间 = 复跑重放，统计独立性
        # 不成立，provenance 须可审计）
        "DETECTION_FIRST_ENABLE",
        "AITESTER_CACHE_NAMESPACE",
        # AB2（2026-10-06 生死实验观测缺口）：profile 原文 + M10 降级开关入
        # 快照——此前 profile 生效证据只能靠反推预设开关组合，分析侧无法
        # 直接按档位分桶；fallback 开关改变 strict 语义，审计必须可见。
        "AITESTER_PROFILE",
        "LOGIC_SPEC_STRICT_FALLBACK_ENABLE",
        # AD1（2026-10-06 输出成本控制）：LLM 传输层三参数入快照——thinking
        # 模式直接改变输出 token 量级（R-P0-2 实测 90%+ 输出为思维链，
        # 单任务最高 84k），跨批次成本/质量对比必须可审计。
        "LLM_THINKING_MODE",
        "LLM_REASONING_EFFORT",
        "LLM_MAX_OUTPUT_TOKENS",
        # 2026-10-14 LLM_JSON_MODE：DeepSeek JSON Output（response_format=
        # json_object，Planner/Debugger 的 JSON 调用点）——改变结构化输出
        # 的采样约束，跨批次质量对比必须可审计；默认 on，off=历史口径。
        "LLM_JSON_MODE",
        # 2026-10-09（D3 修复）：A1 消融开关入快照——A1 首跑工件缺该键，
        # 消融臂可复现性证据缺失（无法从工件证明 strip 是否生效）。
        # 消融类开关必须在 provenance 留痕，否则臂间不可审计。
        "PLAN_STRIP_EXPECTED_OUTPUT_ENABLE",
        # 2026-10-10（本轮审计发现）：over_red 强化段开关也必须入快照。
        # 首跑 over_red 受控臂时该键未登记 → env_snapshot 无此项 →
        # **无法从工件证明干预是否生效**，与 A1 首跑（PLAN_STRIP 未生效却
        # 被当成"零效应"）是同一审计缺口。消融类开关一律在 provenance 留痕。
        "OVER_RED_SECTION_ENABLE",
        # 2026-10-10（独立审查 P0-2 + D3 同类缺口收口）：**默认开（字面量默认
        # true）的开关必须入快照**——这是审计缺口的最高优先档：
        # 默认开的开关"已经在生效"这一事实，若不落 provenance，则
        #   ① 无法从工件证明它确实开着；② 未来把它翻转为 false 时不可审计。
        # 这正是 A1（PLAN_STRIP 未生效却被当成"零效应"）的同一机制。
        # 清单来源：scripts/gates/check_env_snapshot_keys.py 的 P0 档
        # （AST 扫描 src/**/*.py 得出，报告见 review_2026/E2_env_snapshot_report.md）。
        # 另有 P1 档 41 键（修复/裁决主链路）与 P2/P3 档待后续批次补齐。
        "CFG_ANALYSIS_ENABLE",
        "CONTEST_AST_SCAN_ENABLE",
        # A-06（2026-10-17 独立评审）：M1 判分 per-test 超时开关——改变
        # detection 判分语义（None→可判定的转换只发生在该开关生效的批次），
        # provenance 必须留痕，否则跨批次 None 率差异不可审计。
        "M1_PER_TEST_TIMEOUT",
        "DETECTION_FIRST_SECTION_ENABLE",
        "EVENT_BUS_ENABLE",
        "FAULT_LOCALIZER_ENABLE",
        "INJECTION_GUARD_OUTPUT_ENABLE",
        "P2P_GATE_ENABLE",
        "PATCH_EVIDENCE_GATE_ENABLE",
        "POSITION_AWARE_REPAIR_ENABLE",
        "TRACE_MEMORY_BUFFER_ENABLE",
        # 2026-10-10（独立审查 P0-4 配套）：规约 oracle 注入开关必须入快照——
        # 实测 QuixBugs FIXED 批 18/50 行注入了 oracle，但该批 env_snapshot
        # **没有这个键**，因此"逻辑通道是否开启"无法从工件证明。
        "SPEC_ORACLE_EXEC_ENABLE",
        # 2026-10-10（执行器挂死修复配套）：pytest 插件级超时开关入快照——
        # 它改变了测试执行的超时语义（测试内部超时 → 非零 rc，而非外层 kill），
        # 属"改变执行口径"的开关，必须可审计（否则跨批次对比无法归因）。
        "PYTEST_TIMEOUT_ENABLE",
        "PYTEST_TIMEOUT_SECONDS",
        # 2026-10-10 E8：污染检测 structural 佐证口径开关（默认关=修正后口径）
        "AITESTER_CONTAMINATION_STRICT_MAX",
        # 2026-10-10（独立审查 P0-2 收口·第二批）：**补全剩余全部 46 个开关**。
        # 依据：scripts/gates/check_env_snapshot_keys.py 的 AST 扫描（扫描面
        # src/**/*.py，含经模块级常量间接引用者）。此前分批补入 P0/P1 后仍缺 46 键；
        # 缺口机制与 A1 首跑假阴性完全同源——开关未入 provenance，则"它到底开没开"
        # 无法从工件证明，干预生效性不可审计（这是本项目已发生 3 次的事故类）。
        # 本批一次补齐，使门禁从 exit 1 转为 exit 0（真正的阻断门禁）。
        # 门禁：scripts/gates/check_env_snapshot_keys.py（缺失即 exit 1）。
        # 默认开（字面量默认 true）——最高优先：不落 provenance 则"默认已生效"不可证明
        "API_HEALTH_CHECKER_ENABLE",
        "CREDENTIAL_SCRUB_WHITELIST_ENABLE",
        # 其余（默认关；同样必须可审计——消融/开启时需从工件可验证）
        "ADVERSARIAL_DEBUGGING_ENABLE",
        "AGENT_TELEMETRY_ENABLE",
        "ASSERTION_AUGMENT_ENABLE",
        "BIDIRECTIONAL_DIAGNOSIS_ENABLE",
        "CONTEXT_TIER_DOWNGRADE_ENABLE",
        "CONTRACT_ALIAS_ENABLE",
        "COVERAGE_STALL_DETECT_ENABLE",
        "CROSS_FILE_ENABLE",
        "CROSS_FILE_PLAN_BUILD_ENABLE",
        "CROSS_FILE_PLAN_CONSUME_ENABLE",
        "DETECTION_SPECIFICITY_GATE_ENABLE",
        "DETERMINISTIC_GUARD_ENABLE",
        "DETERMINISTIC_REPAIR_FIRST_ENABLE",
        "EDIT_INTENT_ENABLE",
        "EXPERT_POOL_DEBATE_ENABLE",
        "FAILURE_FREQUENCY_ENABLE",
        "FAILURE_KB_ENABLE",
        "FL_GOLD_INJECTION_ENABLE",
        "GRAPH_RAG_ENABLE",
        "HIERARCHICAL_SUMMARY_ENABLE",
        "IMPORT_REPAIR_ENABLE",
        "INJECTION_GUARD_ENABLE",
        "LOCALIZED_EDIT_ENABLE",
        "ORACLE_ENHANCE_ENABLE",
        "ORACLE_VALIDATE_ENABLE",
        "PATCH_SNAPSHOT_ROLLBACK_ENABLE",
        "PROBE_SNAPSHOT_LOCATE_ENABLE",
        "RAG_CONDITIONAL_ENABLE",
        "RAG_JUDGE_INSTRUCTION_ENABLE",
        "RAG_KEYWORD_FALLBACK_ENABLE",
        "RAG_RELEVANCE_THRESHOLD_ENABLE",
        "RED_REGRESSION_GATE_ENABLE",
        "REPRO_TEST_ENABLE",
        "REWARD_PREDICTOR_ENABLE",
        "RISK_APPROVAL_ENABLE",
        "ROGUE_MONITOR_ENABLE",
        "ROUTE_STRUCTURED_ENABLE",
        "RUNTIME_PROBE_ENABLE",
        "SEMANTIC_CACHE_ENABLE",
        "SPEC_IR_DSL_ENABLE",
        "SPEC_REFINE_ENABLE",
        "SPEC_SMT_ENABLE",
        "STRATEGY_BANK_ENABLE",
        "TESTLESS_VALIDATION_ENABLE",
        "TEST_SUITE_DEDUP_ENABLE",
        "TYPE_REPAIR_LLM_ENABLE",
        # 2026-10-11（外部评审 P0-3 / 第四次同类缺口复发）：三个消融类开关
        # 在 src/graph/nodes.py 定义了 getenv 但未登记 → 快照门禁 exit 1、
        # 单测 test_gate_reports_no_missing 长期红。缺口机制与 A1 首跑假阴性
        # 完全同源（开关不入 provenance ⇒ 干预是否生效无法从工件证明）。
        "EMPTY_PLAN_SHORTCUT_ENABLE",
        "OPERATION_MAP_INJECT_ENABLE",
        "PATH_ENUM_INJECT_ENABLE",
        # 2026-10-12（独立评审优化批次·P2-A/P1-A）：观测级压缩（改变
        # Generator prompt 内容）与编排自动搜索（实验 harness 主门）入
        # 快照——同类缺口第五次预防：两者"是否生效"必须能从工件 provenance
        # 逐位证明（A1 首跑假阴性机制）。
        "FEEDBACK_COMPRESSION_ENABLE",
        "ORCHESTRATION_SEARCH_ENABLE",
        # 2026-10-12（STVR 实证研究设计批次·第六次同类缺口预防）：检索质量
        # Recall@k 观测开关入快照——stvr_ablation_study 消融臂（RQ2 检索
        # 策略差异化）必须从工件 provenance 可证明"该臂是否开启了
        # RAG_RETRIEVAL_RECALL_ENABLE"，否则消融结果不可归因。
        "RAG_RETRIEVAL_RECALL_ENABLE",
        # 2026-10-13（EMSE 投稿优化批次·第七次同类缺口收口）：两个开关均未登记。
        # ① DETECTION_SPEC_MODE（spec_first.py，P0-A-2 规格优先主门，改变
        #    Generator prompt 的目标代码块）：scale87 spec_replace 扩样批次
        #    env_snapshot 无此键——spec_replace_applied=50/50 佐证 replace 臂
        #    确实生效，但"是否 replace"无法从快照逐位证明（同 A1 首跑假阴性）。
        # ② ENABLE_MUTATION_SCORING（logic/scientific 档默认 true 的变异评分
        #    主门）：主批次 env_snapshot 无此键——logic 档实际开启（config.py
        #    预设），但 mutation_score 数据的开关前提无法从工件证明。
        "DETECTION_SPEC_MODE",
        "ENABLE_MUTATION_SCORING",
        # 2026-10-16（A-10 df_spec 臂·第八次同类缺口预防）：规格锚表路径入
        # 快照——表内容决定 df_spec 臂的 prompt 材料，"用了哪版锚表"必须
        # 能从工件 provenance 逐位证明（同 A1 首跑假阴性机制）。
        "DF_SPEC_ANCHOR_TABLE",
        # 2026-10-17（P1 docstring 锚臂·第九次同类缺口预防）：docstring 锚表
        # 路径入快照——plain_llm_df_doc / plain_llm_df_doc_union 两臂的 prompt
        # 材料完全由该表决定（人类规格 / 人类规格 ∪ Planner 子句），"用了哪版
        # 锚表"必须从工件 provenance 逐位证明（同 A1 首跑假阴性机制）。
        "DOC_ANCHOR_TABLE",
        # Q-1（2026-10-18）：示例通道生产接线双门之一入快照——examples 会改变
        # Planner prompt 契约与 oracle 产物（逐示例断言），Q-2 A/B 的干预
        # 生效性必须能从工件 provenance 逐位证明（同 A1 首跑假阴性机制）。
        "SPEC_ORACLE_EXAMPLES_ENABLE",
        # Q-3（2026-10-18）：批后处理墙钟告警阈值——仅登记（默认 600s），
        # 用于从工件审计后处理告警阈值口径（不改变主链路行为）。
        "AITESTER_POSTPROCESS_WARN_S",
    ]
    _env_snapshot: dict[str, str | None] = {}
    for _k in _env_snapshot_keys:
        _v = os.environ.get(_k)
        _env_snapshot[_k] = _v

    # 模型版本：从 llm_client.get_first_valid_model_name 读取（线程局部
    # 覆盖的 model_name 作为当前活跃模型的代理；R13 起
    # AITESTER_CACHE_ISOLATE_MODEL 默认开启跨模型缓存隔离，正式实验
    # 如需"不隔离"历史口径可显式设 0）
    try:
        from src.agents.llm_client import get_first_valid_model_name as _get_model_name

        _model_version = _get_model_name()
    except Exception:
        _model_version = None

    _temperature_raw = os.environ.get("TEMPERATURE", "")
    try:
        _temperature_val: float | str = float(_temperature_raw)
    except (ValueError, TypeError):
        _temperature_val = _temperature_raw

    # A03：git_sha 由 environment 块的统一解析结果给出（有 git → git HEAD；
    # 无 git 的复现容器 → .repro_provenance marker 的 build-arg GIT_SHA）。
    _git_sha_val = _git_block["git_sha"]

    # M9（2026-09-29 审查 P0）补充：git dirty 状态（工作树有未提交变更时
    # provenance 须如实标注，否则"git_sha 指向某 commit"具有误导性——
    # 实际运行的是该 commit + 本地 diff 的混合体）
    def _git_dirty() -> bool:
        try:
            _res = _run_with_timeout(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.abspath(__file__)) or ".",
                timeout=10,
            )
            return bool(_res.stdout.strip())
        except Exception:
            return False

    summary["provenance"] = {
        "git_sha": _git_sha_val,
        # A03：提交来源可审计——"git"（工作树元数据）或 "repro_provenance"
        # （复现容器 build-arg 写入的 .repro_provenance marker；容器内 .git 被
        # .dockerignore 排除时仍可追溯）；None = 两来源均不可用。
        "git_sha_source": _git_block["git_sha_source"],
        # marker 明细：present/git_sha/git_sha_matches_git/git_sha_conflict/error。
        # 有 git 时 both 记录并校验一致性；冲突时上面已 logger.warning。
        "repro_provenance": _git_block["repro_provenance"],
        "git_dirty": _git_dirty(),
        # R15（2026-10-08 R2）：脏树豁免原因入 provenance——--allow-dirty 跑批时
        # 记录"为何带脏树"（如调试/迭代），使豁免可审计（此前豁免无登记，
        # 历史 synthetic 两臂 provenance git_dirty=True 而无原因字段）。
        # 非 allow-dirty 时为 None（干净树无豁免）。
        "dirty_reason": dirty_reason,
        "model_name": _model_version,
        # S29（2026-10-11 独立评审落地，F13：同别名 12.5 倍漂移）：
        # **模型版本指纹**——`model_name` 只是**请求侧浮动别名**，
        # 不能证明"两次跑批用的是同一模型快照"。本子块记录 API 实际返回的
        # model / system_fingerprint + 固定 prompt 贪心输出的 sha256：
        # 同别名下探针哈希不一致 → 快照已变 → 该批次不得与历史批次合并统计
        # （预注册停止规则：快照失效即实验作废）。
        # 探针失败（离线 / 无凭证）时 pinned=False + error，**不表失败为成功**。
        "model_fingerprint": collect_model_fingerprint(_model_version),
        # S2（2026-10-11 独立评审落地，F4/K6：389/389 行缺 instance_code）：
        # strict 模式下的剔除面必须可审计——记录开关是否启用 + 被剔除的
        # 任务数 + 任务 ID 列表（上限 200 条，防 provenance 体积失控；被截断
        # 时以 strict_skipped_truncated 标明，全量清单以日志为准）。
        "strict_instance_code": _strict_instance_code_enabled(),
        "strict_skipped_count": len(_strict_skipped),
        "strict_skipped_task_ids": _strict_skipped[:200],
        "strict_skipped_truncated": len(_strict_skipped) > 200,
        "temperature": _temperature_val,
        "max_iterations": MAX_ITERATIONS,
        "seed": seed,
        # AB2（2026-10-06 生死实验观测缺口）：profile 显式入 provenance——
        # 生死实验复审发现 provenance 无 profile 字段（档位只能反推），
        # 多档位批次横比时分析侧无法直接分桶。config.ACTIVE_PROFILE 为
        # import 期 _apply_profile_presets 的生效值（None = 默认档 fast）。
        "profile": ACTIVE_PROFILE,
        # BO（2026-10-22）：环节级工件落盘开关态入 provenance。`--save-state`
        # 决定 raw/<task_id>/<baseline>.json 到底存不存在，而 raw 读侧的一切
        # "工件缺席"折叠（根因归因、定位命中率、失败对比报告）都以它为唯一
        # 前提。实测（scripts/tools/bo_raw_readside_fold_probe.py A 段）：246 份
        # 批次 JSON 中该值出现 0 次、provenance 15 个键里也没有它，而 raw 是否
        # 随归档留存是**逐批次**事实（磁盘 34 个 raw/ 目录，只有 88 份文件入库，
        # `.gitignore:172` 忽略 `experiments/results/**`）⇒ 事后既不能证明"当初
        # 没落盘"，也不能证明"落盘了但没归档"。本字段只对新批次生效，历史工件
        # 一字节不动（同 BN 口径：归位不改判定，只补可复核性）。
        "save_state": bool(save_state),
        "env_snapshot": _env_snapshot,
        "cache_enabled": os.environ.get("AITESTER_LLM_CACHE", "1") != "0",
        "cache_isolate_model": os.environ.get("AITESTER_CACHE_ISOLATE_MODEL", "1") != "0",
        # X1（P0-4a）：缓存命名空间入 provenance（None/空 + cache_enabled=true
        # = 跨批次复用风险口径，读者可据此判定"多批次"是否独立样本）
        "cache_namespace": os.environ.get("AITESTER_CACHE_NAMESPACE") or None,
        # AM1（2026-10-06 第十三轮审查 / 预注册 E6 执行前置）：臂级 token 上限
        # 入 provenance——budget-matched 臂与 standard 臂的口径区分字段
        # （None = 全臂无 cap 历史口径；非 None 时读者可判定哪些臂被限流）
        "per_task_token_caps": token_caps or None,
        # O32（2026-09-29 审查 P0）：API 配置脱敏（不写入明文密钥）
        "valid_apis": [{"url": a["url"], "model": a["model"], "key": "<REDACTED>"} for a in _VALID_APIS],
        # R56（2026-09-30 独立审查 P0）：harness 披露——消除"脚手架主张
        # 伪装成协作主张"（2608.26218：只改 harness → F2PF 28%→49%）。
        # 披露执行隔离档位 / 上下文策略 / 重试与停止规则 / 单次时限 /
        # 模型版本 + 快照日期，使架构主张须对"调好的单智能体 harness"
        # 消融才成立（工件含 harness 快照，读者可判定增益来自角色协作
        # 还是脚手架）。
        "harness": {
            "snapshot_date": datetime.now().strftime("%Y-%m-%d"),
            "execution_isolation": {
                # R10 起 EXECUTOR_USE_VENV 默认 true（venv 沙箱），
                # Docker / 内核沙箱为可选增强档位（默认关）
                "use_venv": os.environ.get("EXECUTOR_USE_VENV", "true").lower() == "true",
                "use_docker": os.environ.get("EXECUTOR_USE_DOCKER", "false").lower() == "true",
                "kernel_sandbox": os.environ.get("KERNEL_SANDBOX_ENABLE", "false").lower() == "true",
                "auto_install_deps": os.environ.get("EXECUTOR_AUTO_INSTALL_DEPS", "false").lower() == "true",
            },
            "context_strategy": {
                # 上下文管理：RAG 检索增强 / 分层压缩 / 截断优先（R49）
                "rag_enabled": os.environ.get("ENABLE_RAG", "false").lower() == "true",
                "context_tier_downgrade": os.environ.get("CONTEXT_TIER_DOWNGRADE_ENABLE", "false").lower() == "true",
                "truncation_first": os.environ.get("TRUNCATION_FIRST_ENABLE", "false").lower() == "true",
                "branch_coverage_inject": os.environ.get("BRANCH_COVERAGE_INJECT_ENABLE", "false").lower() == "true",
            },
            "retry_stop_rules": {
                # 重试与停止：失败重试一次 / 最大迭代 / 预算封顶 /
                # 测试重生成上限 / 回归检测停止条件（StopReason 统一）
                "executor_retry_on_fail": 1,
                "max_iterations": MAX_ITERATIONS,
                "cost_budget_enabled": os.environ.get("COST_BUDGET_ENABLE", "false").lower() == "true",
                # J-1d（2026-10-17）provenance 纠错：原写法读一个**无人消费**的
                # `TEST_REGENERATION_CAP` 环境变量（全仓零读侧），默认写 2；实际生效的重生成
                # 上限是 config.MAX_REGENERATIONS（Z2 已确立单一事实源，当前 1）。即历史批次
                # 工件里的 `test_regeneration_cap: 2` 系统性地**高估了一倍**。现改读真实来源。
                "test_regeneration_cap": MAX_REGENERATIONS,
                "stop_reasons": [
                    "test_passed",
                    "max_iterations",
                    "skip_debugger_repair_invalid",
                    "test_defect_regeneration_cap",
                    "budget_exceeded",
                    "regression_detected",
                    "unknown",
                ],
            },
            "per_task_time_limit_seconds": EXECUTION_TIMEOUT,
            "model_version": _model_version,
        },
    }

    # 保存结果
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"benchmark_{dataset_name}_{timestamp_str}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, allow_nan=False)

    logger.info("基准测试完成，结果已保存至: %s", output_file)
    logger.info("汇总：总耗时=%.1fs", total_time)
    for baseline in baselines:
        bl = summary["results"][baseline]
        logger.info(
            "  [%s] 成功率=%.1f%%, 平均覆盖率=%.1f%%, 平均迭代=%.1f",
            baseline,
            bl["success_rate"],
            bl["avg_coverage"],
            bl["avg_iterations"],
        )
    # 2.2 公平性对照：Token 效率维度（"完整系统 vs Plain LLM"不能只看成功率，
    # 多智能体系统 token 消耗通常远高于单模型直答，效率-效果二维对照才有意义）
    token_texts: dict[str, tuple[str, str, list[str]]] = {}
    for baseline in baselines:
        tm = summary["results"][baseline].get("token_metrics")
        token_texts[baseline] = _token_efficiency_texts(tm)
        log_text, _, reasons = token_texts[baseline]
        logger.info("  [%s] Token效率: %s", baseline, log_text)
        if reasons:
            logger.warning("  [%s] Token读数不可判定：%s", baseline, "；".join(reasons))

    if use_progress:
        print("\n" + "=" * 60)
        print("基准测试完成！")
        print("=" * 60)
        for baseline in baselines:
            bl = summary["results"][baseline]
            _, progress_text, reasons = token_texts[baseline]
            print(f"  [{baseline}] 成功率: {bl['success_rate']}%, 平均覆盖率: {bl['avg_coverage']}%")
            print(f"  [{baseline}] {progress_text}")
            if reasons:
                print(f"  [{baseline}] Token读数不可判定：{'；'.join(reasons)}")
        print(f"总耗时: {total_time:.1f}s")
        print(f"结果文件: {output_file}")
        print("=" * 60)

    return summary


if __name__ == "__main__":
    import click

    @click.command()
    @click.option("--dataset", "-d", default="examples", help="数据集名称")
    @click.option("--subset", "-s", default=None, help="数据子集")
    @click.option("--baselines", "-b", default="aitester,plain_llm,single_agent", help="基线方法列表（逗号分隔）")
    @click.option("--output-dir", "-o", default="experiments/results", help="结果输出目录")
    @click.option("--verbose", "-v", is_flag=True, help="详细日志输出")
    @click.option("--task-count", "-c", default=None, type=int, help="合成数据集任务数量")
    @click.option("--task-limit", "-n", default=None, type=int, help="限制运行任务数量")
    @click.option("--parallel", "-p", default=None, type=int, help="并行任务数")
    @click.option("--seed", default=42, type=int, help="合成数据集随机种子（默认 42）")
    @click.option("--enable-rag", is_flag=True, help="显式开启 RAG 检索增强（P1：RAG 消融实验）")
    @click.option("--no-rag", is_flag=True, help="显式关闭 RAG（覆盖 config.ENABLE_RAG，默认即关）")
    @click.option(
        "--save-state",
        is_flag=True,
        help="把环节级状态（测试计划/生成代码/诊断/补丁）落盘到 <output-dir>/raw/（P0-2 排查用）",
    )
    @click.option(
        "--enable-mutation",
        "enable_mutation",
        is_flag=True,
        help="1.2 变异得分评估：对每任务的生成测试 vs 被测源码计算 mutation_score（默认关闭；开启后每任务 ≤ MUTATION_MAX_MUTANTS 变异体，耗时显著增加）",
    )
    @click.option(
        "--no-mutation",
        "no_mutation",
        is_flag=True,
        help="显式关闭变异得分评估（覆盖 config.ENABLE_MUTATION_SCORING）",
    )
    @click.option(
        "--enable-stagnation",
        "enable_stagnation",
        is_flag=True,
        help="A-19 消融开臂：置 COVERAGE_STALL_DETECT_ENABLE=true，使覆盖率连续停滞（|delta|<eps 且本轮未通过）提前停（默认关）",
    )
    @click.option(
        "--no-stagnation",
        "no_stagnation",
        is_flag=True,
        help="A-19 消融对照臂：显式置 COVERAGE_STALL_DETECT_ENABLE=false（覆盖环境/档位预设，锁定不提前停口径）",
    )
    @click.option(
        "--difficulty",
        default="mixed",
        type=click.Choice(
            ["mixed", "level1", "level2", "level2.5", "level2.5-hard", "level3", "level3.5", "level4", "level4.5"]
        ),
        help="P0 2.1 合成数据集分层难度（仅对 synthetic 数据集生效）：mixed（默认，历史口径）/ level1 / level2 / level2.5（运行时异常缺陷库）/ level2.5-hard（困难运行时异常库，定位阶段可激活）/ level3（跨文件双模块）/ level3.5（三模块深链）/ level4 / level4.5",
    )
    @click.option(
        "--max-pattern-repeat",
        "max_pattern_repeat",
        default=None,
        type=int,
        help="AA：合成数据集同池模板重复上限（仅 synthetic 生效；默认 None=历史口径；>=1 时同 (difficulty, pattern) 至多出现 N 次，全池达上限后轮转重置，防单 pattern 分布塌缩）",
    )
    @click.option(
        "--per-task-token-caps",
        "per_task_token_caps",
        default=None,
        help="AM1：臂级每任务 token 硬上限映射（如 'aitester=4223,plain_llm_df=26115'；默认 None=历史口径无上限；超限走 budget_exceeded 停止通道，预注册 E6 预算匹配臂专用）",
    )
    def cli(
        dataset,
        subset,
        baselines,
        output_dir,
        verbose,
        task_limit,
        task_count,
        parallel,
        seed,
        enable_rag,
        no_rag,
        save_state,
        enable_mutation,
        no_mutation,
        difficulty,
        max_pattern_repeat,
        per_task_token_caps,
        enable_stagnation,
        no_stagnation,
    ):
        """AITester 基准测试工具"""
        bl_list = [b.strip() for b in baselines.split(",") if b.strip()]

        # --enable-rag / --no-rag 显式覆盖 config.ENABLE_RAG；均未指定时沿用配置默认
        rag_override = None
        if no_rag:
            rag_override = False
        elif enable_rag:
            rag_override = True

        # --enable-mutation / --no-mutation 显式覆盖 config.ENABLE_MUTATION_SCORING；
        # 均未指定时沿用配置默认（默认 False，保持历史实验口径不变）
        mutation_override = None
        if no_mutation:
            mutation_override = False
        elif enable_mutation:
            mutation_override = True

        # A-19：覆盖率停滞检测开/关消融臂（映射逻辑在模块级 helper，便于单测）
        try:
            _apply_stagnation_arm(enable_stagnation, no_stagnation)
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc

        summary = run_benchmark(
            dataset_name=dataset,
            subset=subset,
            baselines=bl_list,
            output_dir=output_dir,
            verbose=verbose,
            task_limit=task_limit,
            task_count=task_count,
            parallel=parallel,
            seed=seed,
            enable_rag=rag_override,
            save_state=save_state,
            enable_mutation_scoring=mutation_override,
            difficulty=difficulty,
            max_pattern_repeat=max_pattern_repeat,
            per_task_token_caps=per_task_token_caps,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    cli()
