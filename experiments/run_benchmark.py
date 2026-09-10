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
from datetime import datetime
from typing import Any

import openai

# 确保项目根目录在路径中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 延迟导入，避免 E402
from config import (  # noqa: E402
    ENABLE_DEBUGGER,
    ENABLE_PLANNER,
    EXECUTION_TIMEOUT,
    LLM_CONFIGS,
    LLM_RETRY_WAIT,
    MAX_ITERATIONS,
)
from src.datasets.dataset_loader import (  # noqa: E402
    BenchmarkTask,
    InMemoryDataset,
    load_dataset,
)
from src.graph import token_usage  # noqa: E402
from src.graph.state import AITesterState  # noqa: E402
from src.graph.workflow import build_workflow  # noqa: E402
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
_VALID_APIS = [{"key": c.api_key, "url": c.base_url, "model": c.model_name} for c in LLM_CONFIGS]


def _get_api_for_task(task_index: int) -> dict:
    """根据任务索引分配 API（轮询分摊限流压力）。"""
    if not _VALID_APIS:
        return {"key": "", "url": "", "model": ""}
    return _VALID_APIS[task_index % len(_VALID_APIS)]


def _set_thread_api(task_index: int) -> None:
    """为当前线程设置 API 配置。"""
    from src.agents.base_agent import _thread_local

    api = _get_api_for_task(task_index)
    _thread_local.api_key = api["key"]
    _thread_local.base_url = api["url"]


def _is_zai_url(base_url: str) -> bool:
    """判断是否为 zai SDK 兼容的 API（如 BigModel 智谱）。"""
    return any(d in base_url for d in ["bigmodel.cn", "zhipuai"])


def _call_llm_with_fallback(prompt: str, system_prompt: str, max_retries: int = 3) -> str:
    """
    调用 LLM，失败时自动切换到备用 API。
    支持 OpenAI 兼容接口和 zai SDK（BigModel）两种调用路径。

    Args:
        prompt: 用户消息
        system_prompt: System 提示词
        max_retries: 每个 API 的最大重试次数

    Returns:
        LLM 响应文本
    """
    from src.agents.base_agent import _get_all_api_configs

    for api_key, base_url, model in _get_all_api_configs():
        is_zai = _is_zai_url(base_url)

        try:
            if is_zai:
                # BigModel 等非 OpenAI 兼容接口：使用 zai SDK
                from zai import ZhipuAiClient
                from zai.core._errors import APIReachLimitError, APIStatusError

                client = ZhipuAiClient(api_key=api_key, base_url=base_url)
                for attempt in range(max_retries):
                    try:
                        response = client.chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt},
                            ],
                            max_tokens=4096,
                            thinking={"type": "disabled"},
                        )
                        msg = response.choices[0].message
                        text = (msg.content or msg.reasoning_content or "").strip()
                        if text:
                            logger.debug("zai API %s 调用成功", base_url.split("/")[2])
                            return text
                        raise ValueError("空响应")
                    except (APIReachLimitError, APIStatusError) as e:
                        if attempt < max_retries - 1:
                            wait_time = 2**attempt * 5
                            logger.warning("zai API 限流 (attempt %d/%d): %s", attempt + 1, max_retries, e)
                            time.sleep(wait_time)
                            continue
                        raise
                    except Exception as e:
                        if attempt < max_retries - 1:
                            wait_time = 2**attempt
                            logger.warning(
                                "zai API %s 调用失败 (attempt %d/%d): %s", base_url, attempt + 1, max_retries, e
                            )
                            time.sleep(wait_time)
                            continue
                        raise
            else:
                # OpenAI 兼容接口：使用 openai SDK
                import openai

                client = openai.OpenAI(api_key=api_key, base_url=base_url)
                for attempt in range(max_retries):
                    try:
                        response = client.chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt},
                            ],
                            max_tokens=4096,
                        )
                        text = response.choices[0].message.content.strip()
                        if text:
                            logger.debug("API %s 调用成功", base_url.split("/")[2])
                            return text
                        raise ValueError("空响应")
                    except Exception as e:
                        if attempt < max_retries - 1:
                            wait_time = 2**attempt
                            logger.warning(
                                "API %s 调用失败 (attempt %d/%d): %s, 等待 %ds",
                                base_url,
                                attempt + 1,
                                max_retries,
                                e,
                                wait_time,
                            )
                            time.sleep(wait_time)
                            continue
                        logger.warning("API %s 所有重试失败，切换备用 API: %s", base_url, e)
                        break
                else:
                    continue
                break
        except Exception:
            continue
    else:
        raise RuntimeError(f"所有 API 调用失败: {max_retries} 次重试后仍失败")

    raise RuntimeError("LLM 调用失败，已尝试所有 API")


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
                state["target_code"] = new_code
                # 写回文件并重试
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
        "token_usage": token_usage.get_usage().as_dict(),
    }
    raw_dir = os.path.join(output_dir, "raw", task.task_id)
    os.makedirs(raw_dir, exist_ok=True)
    artifact_file = os.path.join(raw_dir, f"{baseline}.json")
    with open(artifact_file, "w", encoding="utf-8") as f:
        json.dump(artifact, f, ensure_ascii=False, indent=2)


def _build_task_result(
    task: BenchmarkTask,
    elapsed: float,
    final_state: dict[str, Any] | None = None,
    diagnosis: str = "",
    error_category: str = "",
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

    Returns:
        结果字典（结构见 run_single_task 各分支的原始实现，字段完全一致）。
    """
    if final_state is not None:
        return {
            "task_id": task.task_id,
            "repo": task.repo_name,
            "passed": final_state.get("test_passed", False),
            "coverage": final_state.get("coverage_report") or 0.0,
            "iterations": final_state.get("iteration", 0),
            "diagnosis": final_state.get("diagnosis", ""),
            "error_category": final_state.get("error_category", ""),
            "elapsed_seconds": round(elapsed, 2),
            # P0-2 效率指标：单次基线运行的 token 消耗（性价比对比依据）
            "token_usage": token_usage.get_usage().as_dict(),
            # P1 RAG 检索质量：本基线累计的检索指标（未启用 RAG 时为空）
            "rag_stats": final_state.get("rag_stats"),
            "task_metadata": task.metadata,
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
        "task_metadata": task.metadata,
    }


def run_single_task(
    task: BenchmarkTask,
    baselines: list[str],
    output_dir: str,
    verbose: bool = False,
    save_state: bool = False,
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

    Returns:
        包含各基线结果的字典。
    """
    # 创建临时目录存放任务相关文件（避免修改原始文件）
    tmp_dir = tempfile.mkdtemp(prefix=f"aitester_{task.task_id}_")
    try:
        # 写入 instance_code 到临时文件
        # 使用 task_id 的最后一段作为模块名，确保与文件名一致
        # 转换非法字符：连字符→下划线，确保是合法 Python 标识符
        raw_name = task.task_id.split("__")[-1]
        module_name = raw_name.replace("-", "_")[:50]
        instance_file = os.path.join(tmp_dir, f"{module_name}.py")
        with open(instance_file, "w", encoding="utf-8") as f:
            f.write(task.instance_code)

        # 初始化工作流状态（作为所有基线的起点，逐基线 deepcopy 隔离）
        # P0：SWE-bench 任务从官方 patch 提取的 suggested_function 初始化
        # target_function，驱动 Planner/Generator/Debugger 的 AST 聚焦截取
        suggested_function = task.metadata.get("suggested_function")
        initial_state: AITesterState = {
            "task_uuid": task.task_id,
            "target_file": instance_file,
            "target_function": suggested_function,
            "module_name": module_name,
            "target_code": task.instance_code,
            "test_plan": None,
            "generated_test": None,
            "test_passed": None,
            "test_output": None,
            "coverage_report": None,
            "failed_cases": None,
            "diagnosis": None,
            "error_category": None,
            "patch": None,
            "iteration": 0,
            "max_iterations": MAX_ITERATIONS,
            "repair_history": [],
        }

        # 为每个基线分配不同的 API（轮询）
        results: dict[str, dict[str, Any]] = {}
        for _baseline_idx, baseline in enumerate(baselines):
            # 根据任务索引和基线索引分配 API
            _set_thread_api(hash(task.task_id) % len(_VALID_APIS) if _VALID_APIS else 0)

            # 基线隔离：deepcopy 初始状态并重置磁盘实例文件为原始代码。
            # single_agent 基线执行中会把修复后的代码写回 target_file
            # （open(target_file, "w")），若不重置，后续基线会从"已修复代码 +
            # 已递增的 iteration"起步，基线对比数据无效
            state = copy.deepcopy(initial_state)
            with open(instance_file, "w", encoding="utf-8") as f:
                f.write(task.instance_code)

            # P0-2 效率指标：重置本线程 token 统计，基线运行结束后记录消耗
            # （parallel 模式下每个工作线程独立累计，互不串扰）
            token_usage.reset()
            start_time = time.time()
            state["task_uuid"] = f"{task.task_id}_{baseline}_{int(start_time)}"

            if verbose:
                logger.info("  [%s] 运行 %s ...", baseline, task.task_id)

            try:
                final_state = BASELINE_REGISTRY[baseline](state)
                elapsed = time.time() - start_time

                results[baseline] = _build_task_result(task, elapsed, final_state=final_state)
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
            except openai.RateLimitError:
                # 限流：等待后重试（重试共享同一 token 统计窗口，结果含两次调用消耗）
                logger.warning("    [%s] %s 触发 API 限流，等待 %ds 后重试...", baseline, task.task_id, LLM_RETRY_WAIT)
                time.sleep(LLM_RETRY_WAIT)
                try:
                    final_state = BASELINE_REGISTRY[baseline](state)
                    elapsed = time.time() - start_time
                    results[baseline] = _build_task_result(task, elapsed, final_state=final_state)
                    if save_state:
                        _dump_state_artifacts(output_dir, task, baseline, final_state)
                except Exception as e2:
                    elapsed = time.time() - start_time
                    logger.error("    [%s] %s 重试后仍失败: %s", baseline, task.task_id, e2)
                    results[baseline] = _build_task_result(
                        task, elapsed, diagnosis=f"限流重试失败: {e2}", error_category="rate_limit"
                    )
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error("    [%s] %s 执行失败: %s", baseline, task.task_id, e)
                results[baseline] = _build_task_result(
                    task, elapsed, diagnosis=f"执行异常: {e}", error_category="error"
                )

        return results

    finally:
        # 清理临时目录
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _run_task_with_progress(args: tuple) -> tuple[BenchmarkTask, dict[str, Any]]:
    """并行执行任务包装器。"""
    task, baselines, output_dir, verbose, save_state = args
    results = run_single_task(task, baselines, output_dir, verbose, save_state=save_state)
    return task, results


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
    if _wf.ENABLE_RAG != enabled:
        logger.info("RAG 开关已切换: %s → %s", _wf.ENABLE_RAG, enabled)
        _wf.ENABLE_RAG = enabled
    return enabled


# ─── 主基准测试函数 ────────────────────────────────────────────────────────────


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

    Returns:
        汇总结果字典。
    """
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
        logger.info("生成合成数据集：%d 个任务（seed=%d）", tc, seed)
        from src.datasets.synthetic_dataset import SyntheticDataset

        dataset = SyntheticDataset(task_count=tc, seed=seed)
        # 确保数据集已加载
        _ = dataset.tasks
    else:
        try:
            dataset = load_dataset(dataset_name, subset=subset)
        except Exception as e:
            logger.error("数据集加载失败: %s", e)
            raise

    if dataset.size == 0:
        logger.warning("数据集为空，尝试使用内置示例数据集")
        dataset = InMemoryDataset.create_with_samples()

    tasks = dataset.tasks[:task_limit] if task_limit else dataset.tasks
    logger.info("可用 API 配置数: %d", len(_VALID_APIS))

    if parallel is None:
        parallel = int(os.getenv("BENCHMARK_PARALLELISM", "0"))

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
                futures = {
                    executor.submit(_run_task_with_progress, (task, baselines, output_dir, verbose, save_state)): task
                    for task in tasks
                }
                for future in concurrent.futures.as_completed(futures):
                    task = futures[future]
                    try:
                        _, task_results = future.result()
                    except Exception as e:
                        logger.error("任务 %s 执行失败: %s", task.task_id, e)
                        task_results = {}

                    for baseline, result in task_results.items():
                        all_results[baseline].append(result)

                    elapsed_this = sum(r["elapsed_seconds"] for r in task_results.values())
                    total_time += elapsed_this
                    pbar.update(1)
                    pbar.set_description(f"{desc} - 耗时: {total_time:.1f}s")
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

    for baseline in baselines:
        bl_results = all_results[baseline]
        passed = sum(1 for r in bl_results if r["passed"])
        total = len(bl_results)
        avg_coverage = sum(r.get("coverage", 0) for r in bl_results) / total if total > 0 else 0
        avg_iterations = sum(r["iterations"] for r in bl_results) / total if total > 0 else 0
        avg_time = sum(r["elapsed_seconds"] for r in bl_results) / total if total > 0 else 0

        summary["results"][baseline] = {
            "total_functions": total,
            "passed_count": passed,
            "failure_count": total - passed,
            "success_rate": round(passed / total * 100, 1) if total > 0 else 0,
            "avg_coverage": round(avg_coverage, 1),
            "avg_iterations": round(avg_iterations, 2),
            "avg_elapsed_seconds": round(avg_time, 2),
            "total_time": round(sum(r["elapsed_seconds"] for r in bl_results), 2),
            # P0-2 效率指标 + P1 RAG 检索质量（未启用 RAG 时指标全为 0/None）
            "token_metrics": _aggregate_token_metrics(bl_results),
            "rag_metrics": _aggregate_rag_metrics(bl_results),
            "details": bl_results,
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

    if use_progress:
        print("\n" + "=" * 60)
        print("基准测试完成！")
        print("=" * 60)
        for baseline in baselines:
            bl = summary["results"][baseline]
            print(f"  [{baseline}] 成功率: {bl['success_rate']}%, 平均覆盖率: {bl['avg_coverage']}%")
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
    @click.option(
        "--save-state",
        is_flag=True,
        help="把环节级状态（测试计划/生成代码/诊断/补丁）落盘到 <output-dir>/raw/（P0-2 排查用）",
    )
    def cli(
        dataset, subset, baselines, output_dir, verbose, task_limit, task_count, parallel, seed, enable_rag, save_state
    ):
        """AITester 基准测试工具"""
        bl_list = [b.strip() for b in baselines.split(",") if b.strip()]

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
            enable_rag=enable_rag or None,  # 未指定 --enable-rag 时沿用 config.ENABLE_RAG
            save_state=save_state,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    cli()
