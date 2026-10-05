"""
批量实验脚本：对数据集运行 AITester 及多基线对比，记录完整结果。

支持的基线方法：
    - aitester     : 完整多智能体系统（Planner+Generator+Executor+Debugger）
    - plain_llm    : 纯 LLM 基线（无 Planner、无修复循环，仅一次调用）
    - single_agent : 单智能体基线（所有功能合并为一个 LLM 调用）

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
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import zlib
from collections.abc import Callable
from datetime import datetime
from typing import Any

import openai

# 确保项目根目录在路径中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 延迟导入，避免 E402
from config import (  # noqa: E402
    BENCHMARK_PARALLELISM,
    ENABLE_DEBUGGER,
    ENABLE_MUTATION_SCORING,
    ENABLE_PLANNER,
    EXECUTION_TIMEOUT,
    LLM_CONFIGS,
    LLM_RETRY_WAIT,
    MAX_ITERATIONS,
    MUTATION_MAX_MUTANTS,
    REPO_LEVEL_EXECUTION,
    SWE_BENCH_P2P_GATE_ENABLE,
    SWE_BENCH_P2P_GATE_THRESHOLD,
    SWE_REPO_SETUP_TIMEOUT,
)
from src.api.complexity_router import (  # noqa: E402
    complexity_class_to_routing_hints,
    compute_complexity_score,
    routing_enabled,
)
from src.datasets.dataset_loader import (  # noqa: E402
    BenchmarkTask,
    InMemoryDataset,
    load_dataset,
)
from src.graph import token_usage  # noqa: E402
from src.graph.state import AITesterState, create_initial_state  # noqa: E402
from src.graph.workflow import build_workflow, effective_stop_reason, end_task_trace, start_task_trace  # noqa: E402
from src.utils.logging_utils import setup_logger_safety  # noqa: E402

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
    tqdm = None  # type: ignore


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

    agent = GeneratorAgent()
    # 执行超时必须走 config.EXECUTION_TIMEOUT（含容错解析 + [10, 300] 范围校验）；
    # 此前直接 int(os.getenv("EXECUTION_TIMEOUT", "30"))，坏值（如 "abc"）会让基线
    # 运行在 import 后立即 ValueError 崩溃，绕过配置层的兜底
    executor = ExecutorAgent(timeout=EXECUTION_TIMEOUT)

    # 单次 LLM 调用：要求直接生成测试并自行判断是否需要修复
    query = (
        f"你是一个软件测试专家。请分析以下代码并直接生成完整的 pytest 测试代码。\n\n"
        f"目标代码：\n```python\n{state['target_code']}\n```\n\n"
        f"要求：\n"
        f"1. 找出代码中可能存在的 bug，编写能捕获这些 bug 的测试用例\n"
        f"2. 同时生成一个简化版的修复补丁（如果需要）\n"
        f"3. 只输出 pytest 测试代码（用 ```python 包裹），不要输出其他内容"
    )

    test_code = agent._extract_python_code(agent._call_llm(query))
    state["generated_test"] = test_code

    # 1.2 改进（MutGen 式变异反馈闭环）：单智能体基线在修复前消费上一轮
    # 变异评估的"存活变异体"反馈（state["mutation_feedback"]），引导 LLM
    # 针对"当前测试未捕获的故障模式"补强断言；无反馈时行为与历史口径一致
    feedback = state.get("mutation_feedback")
    if feedback and feedback.get("survived_mutants"):
        query += "\n\n【变异反馈】以下变异体未被现有测试捕获，请在生成测试时补充针对性断言：\n" + "\n".join(
            f"- {d}" for d in feedback["survived_mutants"][:5]
        )

    # 执行测试
    result = executor.execute(
        test_code=test_code,
        target_file=state["target_file"],
        target_function=state.get("target_function"),
    )

    state["test_passed"] = result["passed"]
    state["test_output"] = result["output"]
    state["coverage_report"] = result["coverage"]
    state["failed_cases"] = result["failed_cases"]
    state["iteration"] = 0

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
                    retry_result = executor.execute(
                        test_code=test_code,
                        target_file=state["target_file"],
                        target_function=state.get("target_function"),
                    )
                    state["test_passed"] = retry_result["passed"]
                    state["test_output"] = retry_result["output"]
                    state["coverage_report"] = retry_result["coverage"]
                    state["failed_cases"] = retry_result["failed_cases"]
                    state["iteration"] = 1
                else:
                    # 不安全：放弃写盘，保持原代码（与 patch_applier 拒写口径一致）
                    logger.warning("single_agent 基线：修复代码未通过安全检查（过短/丢失函数定义），保留原代码")
                    state["iteration"] = 1

    return state


# 基线方法注册表
BASELINE_REGISTRY: dict[str, callable] = {
    "aitester": run_aitester_baseline,
    "plain_llm": run_plain_llm_baseline,
    "single_agent": run_single_agent_baseline,
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
        "task_metadata": task.metadata,
    }
    raw_dir = os.path.join(output_dir, "raw", task.task_id)
    os.makedirs(raw_dir, exist_ok=True)
    artifact_file = os.path.join(raw_dir, f"{baseline}.json")
    with open(artifact_file, "w", encoding="utf-8") as f:
        json.dump(artifact, f, ensure_ascii=False, indent=2)


def _compute_contamination_risk_level(
    task_result: dict[str, Any],
    golden_patches: dict[str, str] | None,
) -> str:
    """五、多维度污染检测：对单个任务计算污染风险等级（high/medium/low/not_applicable）。

    口径（与 experiments.contamination_check 一致）：
    - 取 task_result["patch"]（系统生成的补丁）与 golden_patches 中对应
      任务的黄金补丁（run_benchmark 顶层 golden_patches 字典，task_id →
      补丁文本），调 patch_semantic_similarity 的多维度检测（token Jaccard +
      AST 语句骨架 LCS + 嵌入余弦/词袋余弦保守代理；EMBEDDING_BACKEND 接入
      真实嵌入库时自动升级为 CodeBERT 类语义余弦），综合得出 risk_level；
    - 返回 "high" / "medium" / "low" / "not_applicable" 之一，写入 details[]
      的 contamination_risk_level 字段（供 analyze_results 的
      _contamination_cross_analysis 消费，区分"含污染样本"与"不含
      污染样本"的结果）。

    设计约束（保守、可复算、口径诚实）：
    - 无黄金补丁材料（无 golden_patches / task 无对应条目 / 补丁任一侧
      为空）→ "not_applicable"（N7，2026-10-05 复审：合成数据集此前恒标
      "low"，把"检测没有发生"与"检测过且无重叠证据"混为一谈——前者
      应显式声明检测不适用，而非暗示低风险）；
    - 检测器抛异常（补丁格式异常等）→ "low"（保守不阻断实验主流程；
      检测已尝试、无重叠证据）；
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
        logger.debug("污染风险等级计算失败（保守标记 low）: task=%s", task_id, exc_info=True)
        return "low"


def _compute_detection_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1（2026-09-29 审查 P0）：检出率（SWT-Bench 口径）—— 详见
    experiments/_m1_metrics.py。
    """
    from experiments._m1_metrics import _compute_detection_rate as _impl

    return _impl(task, final_state)


def _compute_repair_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1（2026-09-29 审查 P0）：修复率（gold 独立裁决）—— 详见
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

    plausible = 有补丁文本 且 写盘成功（repair_history 末条 patch_applied=True）。
    无补丁 / 无 repair_history → 0。
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
    last = history[-1] if isinstance(history[-1], dict) else {}
    return 1 if bool(last.get("patch_applied")) else 0


def _patch_correct(task: Any, final_state: dict[str, Any] | None) -> int:
    """R53：本轮补丁是否被 gold 独立裁决背书（correct 计数，任务级 0/1）。

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


def _patch_precision(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """R53：补丁精确率 = correct / plausible（plausible=0 时 None，避免除零）。"""
    plausible = _patch_plausible(final_state)
    if plausible == 0:
        return None
    return _patch_correct(task, final_state) / plausible


def _fl_at_k(final_state: dict[str, Any] | None) -> dict[str, Any] | None:
    """R8（2026-09-30 独立审查 N7，P1）：FL@k 定位命中指标（FL@1/3/5）。

    口径：fl_spectral_focus 非空时，取真实缺陷行（gold fixed 代码与 buggy
    代码的 diff 行号集合）是否落在 Top-k 的命中情况。无 fl_spectral_focus
    （O2 关 / 测量失败 / Docker 链路）或无 gold diff 行时返回 None
    （保持键集合同构，统计层按"不可测"处理）。
    """
    if final_state is None:
        return None
    focus = final_state.get("fl_spectral_focus")
    if not focus or not focus.get("top_k"):
        return None
    top_k = focus.get("top_k", [])
    ranked_lines = [item.get("line") for item in top_k]
    # gold diff 行：从 state 携带的 patch diff 提取（applied patch 的变更行）
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


def _extract_diff_line_numbers(patch_text: str) -> list[int]:
    """从 unified diff / 补丁文本中提取 new 侧变更行号（保守口径）。

    复用 patch_evidence._patch_changed_lines 的 @@ 解析逻辑（不依赖
    evidence 门开关）；非 diff 格式补丁返回空列表。
    """
    if not patch_text or not patch_text.strip():
        return []
    try:
        from src.tools.patch_evidence import _patch_changed_lines

        return sorted(_patch_changed_lines(patch_text))
    except Exception:
        return []


def _check_swe_bench_p2p_gate(task: BenchmarkTask) -> dict[str, Any] | None:
    """M3（2026-09-29 审查 P0 + D.4-7）/ R46（2026-09-30 独立审查 P0）：
    SWE-bench 实例可解性前置门禁（**默认开启**）。

    R46 起 SWE-bench 批次默认执行本门禁（SWE_BENCH_P2P_GATE_ENABLE 缺省
    "true"）：调用 scripts/verify_instance_solvable.verify_single_instance
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
        from scripts.verify_instance_solvable import verify_single_instance
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
            # 2.2 补丁后处理重采样统计（PATCH_RESAMPLE_ENABLE=true 时写入）
            "patch_resample_stats": final_state.get("patch_resample_stats"),
            # 五、多维度污染检测：对单任务计算 risk_level（high/medium/low/
            # not_applicable）（供 analyze_results 的 _contamination_cross_analysis
            # 消费；无黄金补丁材料时返回 "not_applicable"——N7 口径：检测
            # 不适用与"检测过且无重叠证据"的 "low" 区分）
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
            # M1（2026-09-29 审查 P0）：假通过标记 + 独立裁决三指标。
            # test_regenerated_pass_unverified：M5 执行层标记（测试重生成后
            # 通过且源码未改 → 假成功通道），直接读 state 键（缺省 None）。
            "test_regenerated_pass_unverified": final_state.get("test_regenerated_pass_unverified"),
            # P0（2026-09-30 独立审查 N9/R33）：源码补丁证据门观测。
            # source_patched_unverified：本轮写盘无 gold/谱系定位证据（True）
            # 或有证据背书（False）；None = 本轮无补丁 / 证据门未触发。
            "source_patched_unverified": final_state.get("source_patched_unverified"),
            "patch_evidence_level": final_state.get("patch_evidence_level"),
            # M1 三指标（并行产出，不改变 passed 的历史口径）：
            #   detection_rate（生成测试能否让带缺陷代码变红）/
            #   repair_rate（gold 独立裁决修复是否正确）/
            #   false_fix_rate（passed=True 但 gold 裁决失败的占比）
            # 计算依赖 gold test_cases / fixed（合成模板自带），无 gold 材料时
            # 以 None 占位保持键集合同构（历史结果 JSON 结构向后兼容）。
            "detection_rate": _compute_detection_rate(task, final_state),
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
            #   repair_rate / false_fix_rate 为独立裁决通道（gold 材料），
            #   与自生成验收并行产出，不改变 passed 的历史口径。
            "oracle_type": _oracle_type_label(final_state),
            "test_visible_to_system": True,
            # 2026-09-30 独立审查 R53（P0）：补丁精确率框架
            # （"plausible 精确率 = correct / plausible" 是信息量最大的
            # 修正指标）。口径：
            #   - patch_plausible = 本轮有补丁产出且写盘成功（静态守卫通过）；
            #   - patch_correct = gold 独立裁决通过（repair_rate == 1.0）；
            #   - patch_precision = correct / plausible（无 plausible 时 None）。
            # 供统计层"过拟合度量"消费（假修复 = plausible 但 correct=0）。
            "patch_plausible": _patch_plausible(final_state),
            "patch_correct": _patch_correct(task, final_state),
            "patch_precision": _patch_precision(task, final_state),
            # R8（2026-09-30 独立审查 N7，P1）：FL@1/3/5 定位命中指标
            # （Ochiai 谱系定位的"真实缺陷行是否落在 Top-k"量化口径）
            "fl_at_k": _fl_at_k(final_state),
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
            # R4（2026-09-30 独立审查 P0）：回归率（修复引入回归观测）
            # 补丁应用后 gold P2P 基线测试出现回归 → 1.0；否则 0.0；
            # 无 P2P 材料 / 超时 → None（不可测量）
            "regression_rate": _compute_regression_rate(task, final_state),
            # M3 门禁：harness_invalid 标记（基线 P2P 不达标，不计入统计）
            "harness_invalid": harness_invalid,
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
        # P0（2026-09-30 独立审查 N9/R33）：失败分支无 final_state，
        # 证据门观测键以 None 占位保持键集合同构
        "source_patched_unverified": None,
        "patch_evidence_level": None,
        "detection_rate": None,
        "repair_rate": None,
        "false_fix_rate": None,
        # 2026-09-30 独立审查 N1：失败分支无生成测试，测试执行错误率占位
        "test_error_rate": None,
        # 2026-09-30 独立审查 R52/R53：失败分支无 final_state，
        # oracle 类型声明 / 补丁精确率框架以保守占位保持键集合同构
        "oracle_type": "generated_test",
        "test_visible_to_system": True,
        "patch_plausible": 0,
        "patch_correct": 0,
        "patch_precision": None,
        "fl_at_k": None,
        # R4（2026-09-30 独立审查 P0）：失败分支无 final_state，回归率占位
        "regression_rate": None,
        # 2026-09-29 审查 P0（StopReason）：失败分支无 final_state，终止原因为 None
        "stop_reason": None,
        # M3 门禁：harness_invalid 标记（基线 P2P 不达标，不计入统计）
        "harness_invalid": harness_invalid,
    }


def _build_risk_summary_for_result(final_state: dict[str, Any] | None) -> dict[str, Any]:
    """构建单任务结果行的 G2 风险分级摘要（默认关时 enabled=False 占位）。

    设计口径（保守、零 LLM 成本）：
        - 仅当 `RISK_APPROVAL_ENABLE=true` 时做三因子打分（error_classifier 置信度
          + patch_applier 影响面 + cost_budget 消耗），产出 low/medium/high 分级
          与 auto_merge / human_confirm / force_review 审批动作；
        - 默认关（历史默认）时返回 `{"enabled": False}` 占位，保持结果键集合同构，
          不改变任何历史实验口径。

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


def run_single_task(
    task: BenchmarkTask,
    baselines: list[str],
    output_dir: str,
    verbose: bool = False,
    save_state: bool = False,
    enable_mutation_scoring: bool | None = None,
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
        )

        # 2026-10 改进：跨文件任务预置 cross_file_deps（供 _resolve_target_module
        # 解析被调方真实模块名；单文件任务 no-op）
        _write_cross_file_state(initial_state, task.metadata)

        # P0 1.2 复杂度感知路由（MODEL_ROUTING_STRATEGY=complexity_aware）：
        # 按任务代码行数 / import 数量 / 圈复杂度计算复杂度分数，写入
        # state["complexity_class"]（"simple" | "medium" | "complex"），
        # 供 LLM 调用路径选择对应档位的 LLM 实例。策略=fixed 时恒为 "medium"。
        if routing_enabled():
            num_lines = len(task.instance_code.splitlines())
            num_files = int(task.metadata.get("num_files", 1))
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
            cc = int(task.metadata.get("cyclomatic_complexity", 1))
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
                cc = int(task.metadata.get("cyclomatic_complexity", 1))
                _tree = None
            try:
                from src.api.complexity_router import count_imports

                num_deps = count_imports(task.instance_code, _tree=_tree)
            except Exception:
                num_deps = int(task.metadata.get("num_imports", 0))
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
            from src.graph.cost_budget import reset_budget

            reset_budget()
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
    task, baselines, output_dir, verbose, save_state = args
    results = run_single_task(task, baselines, output_dir, verbose, save_state=save_state)
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
        fut = executor.submit(_run_task_with_progress, (task, baselines, output_dir, verbose, save_state))
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
        # 从 task_id 末段派生（与 _extract_gold_material 一致）
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
    deterministic: bool = False,
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
        deterministic: R11（2026-10-05 审查 P1）确定性采样模式。True 时
            强制 TEMPERATURE=0.0（级联 config 与 base_agent 命名空间——
            二者均为 import 时求值，仅改 os.environ 不生效）+ os.environ
            同步（供 provenance 快照记录 temperature=0.0）。主批次复现
            实验建议开启（配合干净 git tag，缓解"LLM 输出非确定性导致
            结果不可复现"的审查缺口）。默认 False 历史口径不变。

    Returns:
        汇总结果字典。
    """
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

    logger.info("加载数据集: %s (subset=%s, seed=%d)", dataset_name, subset, seed)

    if dataset_name in ("synthetic", "synth"):
        tc = task_count or 60
        logger.info("生成合成数据集：%d 个任务（seed=%d, difficulty=%s）", tc, seed, difficulty)
        from src.datasets.synthetic_dataset import SyntheticDataset

        dataset = SyntheticDataset(task_count=tc, seed=seed, difficulty=difficulty)
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
                )
        else:
            for task in tasks:
                logger.info("处理任务: %s", task.task_id)
                task_results = run_single_task(task, baselines, output_dir, verbose, save_state=save_state)

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
    import platform as _platform
    import subprocess as _sp

    _env_provenance: dict[str, Any] = {
        "python_version": sys.version.split()[0],
        "platform": _platform.platform(),
        "git_sha": None,
        "in_docker_repro": os.path.exists(os.path.join(os.getcwd(), ".repro_provenance")),
    }
    try:
        _git_sha = _sp.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
        _env_provenance["git_sha"] = _git_sha or None
    except (OSError, _sp.SubprocessError):
        _env_provenance["git_sha"] = None
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

    def _aggregate_token_metrics(bl_results: list[dict[str, Any]]) -> dict[str, Any]:
        """聚合一个基线的 token 消耗（P0-2：多智能体系统 vs Plain LLM 性价比对比）。"""
        total_input = sum((r.get("token_usage") or {}).get("input_tokens", 0) for r in bl_results)
        total_output = sum((r.get("token_usage") or {}).get("output_tokens", 0) for r in bl_results)
        total_calls = sum((r.get("token_usage") or {}).get("llm_calls", 0) for r in bl_results)
        total = len(bl_results)
        return {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_llm_calls": total_calls,
            "avg_tokens_per_task": round((total_input + total_output) / total, 2) if total > 0 else 0,
        }

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
        if mutation_enabled:
            # task_id → BenchmarkTask 映射（同一任务跨基线复用 instance_code）
            task_map = {t.task_id: t for t in tasks}
            logger.info("启用变异得分评估（1.2）：每任务 ≤ %d 变异体", MUTATION_MAX_MUTANTS)
            _compute_mutation_scores_for_baseline(bl_results, task_map, MUTATION_MAX_MUTANTS)
            # R5（2026-10-05 审查建议）：变异检出率（SWE-Mutation 2026 口径）
            # 挂同一开关（ENABLE_MUTATION_SCORING）与同一挂点——测试有效性
            # 的客观裁决（生成的测试在 gold 修复代码上全绿、在其 AST 变异体
            # 上变红的比例）；缺 gold fixed 材料的任务记 None。默认关时
            # 零行为变化。
            _compute_mutation_detection_for_baseline(bl_results, task_map, MUTATION_MAX_MUTANTS, seed=seed)

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
            # P0-2 效率指标 + P1 RAG 检索质量（未启用 RAG 时指标全为 0/None）
            "token_metrics": _aggregate_token_metrics(bl_results),
            "rag_metrics": _aggregate_rag_metrics(bl_results),
            "details": bl_results,
        }

    # M9（2026-09-29 审查 P0）：实验 provenance 块 —— 把结果 JSON 顶层
    # 补全 git SHA / 模型版本 / 温度 / max_iterations / 开关快照 / seed，
    # 使论文数字可追溯、可复现（此前结果工件只有 timestamp / dataset /
    # subset / seed / baselines / results，无 git commit SHA、无模型版本、
    # 无 temperature、无 ~118 个环境开关快照 → 跨模型/跨代码版本串味且
    # 不可复算）。
    import subprocess as _subprocess

    def _git_sha() -> str | None:
        try:
            _res = _subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.abspath(__file__)) or ".",
                timeout=10,
            )
            if _res.returncode == 0:
                return _res.stdout.strip()
        except Exception:
            pass
        return None

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

    _git_sha_val = _git_sha()

    # M9（2026-09-29 审查 P0）补充：git dirty 状态（工作树有未提交变更时
    # provenance 须如实标注，否则"git_sha 指向某 commit"具有误导性——
    # 实际运行的是该 commit + 本地 diff 的混合体）
    def _git_dirty() -> bool:
        try:
            _res = _subprocess.run(
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
        "git_dirty": _git_dirty(),
        "model_name": _model_version,
        "temperature": _temperature_val,
        "max_iterations": int(os.environ.get("MAX_ITERATIONS", "3")),
        "seed": seed,
        "env_snapshot": _env_snapshot,
        "cache_enabled": os.environ.get("AITESTER_LLM_CACHE", "1") != "0",
        "cache_isolate_model": os.environ.get("AITESTER_CACHE_ISOLATE_MODEL", "1") != "0",
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
                "max_iterations": int(os.environ.get("MAX_ITERATIONS", "3")),
                "cost_budget_enabled": os.environ.get("COST_BUDGET_ENABLE", "false").lower() == "true",
                "test_regeneration_cap": int(os.environ.get("TEST_REGENERATION_CAP", "2")),
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
            "per_task_time_limit_seconds": int(os.environ.get("EXECUTION_TIMEOUT", "30")),
            "model_version": _model_version,
        },
    }

    # 保存结果
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"benchmark_{dataset_name}_{timestamp_str}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

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
    for baseline in baselines:
        tm = summary["results"][baseline]["token_metrics"]
        logger.info(
            "  [%s] Token效率: 总tokens=%d, 平均每任务tokens=%.2f, LLM调用次数=%d",
            baseline,
            tm["total_tokens"],
            tm["avg_tokens_per_task"],
            tm["total_llm_calls"],
        )

    if use_progress:
        print("\n" + "=" * 60)
        print("基准测试完成！")
        print("=" * 60)
        for baseline in baselines:
            bl = summary["results"][baseline]
            tm = bl["token_metrics"]
            print(f"  [{baseline}] 成功率: {bl['success_rate']}%, 平均覆盖率: {bl['avg_coverage']}%")
            print(f"  [{baseline}] 平均每任务Token: {tm['avg_tokens_per_task']}, LLM调用次数: {tm['total_llm_calls']}")
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
        "--difficulty",
        default="mixed",
        type=click.Choice(
            ["mixed", "level1", "level2", "level2.5", "level2.5-hard", "level3", "level3.5", "level4", "level4.5"]
        ),
        help="P0 2.1 合成数据集分层难度（仅对 synthetic 数据集生效）：mixed（默认，历史口径）/ level1 / level2 / level2.5（运行时异常缺陷库）/ level2.5-hard（困难运行时异常库，定位阶段可激活）/ level3（跨文件双模块）/ level3.5（三模块深链）/ level4 / level4.5",
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
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    cli()
