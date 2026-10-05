"""终局失效分类标注框架（U11，2026-10-05 系统性审查落地）。

背景（2026-10-05 独立系统性审查）：
    系统已有 18 类任务侧错误分类（src/agents/error_classifier.py）与 12 类
    StopReason 终止原因（src/graph/workflow.py），但失败任务只有"没修好"
    一个标签，无法回答"失败发生在哪个环节、属于哪类协作/能力失效"。
    多智能体失效的科学度量（分类视角参考 MAST，arXiv:2503.13657，
    NeurIPS 2025）要求把终局状态映射到可比较的失效桶。

本模块（纯静态、零 LLM、零子进程、不参与路由）：
    1. FailureBucket：五个自有终局桶（桶定义为项目自有，非 MAST 转述）；
    2. annotate_final_state(state)：按优先级把工作流最终状态映射到
       (bucket, stop_reason, detail)；
    3. summarize_batch(states)：桶计数 + 占比（观测层聚合）；
    4. render_markdown(summary)：Markdown 表渲染（报告层消费）。

消费方：experiments/ 分析脚本（对 run_benchmark 产出的 per-task 终局
状态批量标注）与报告层。**不接主流程路由**——桶判定纯观测，路由语义
仍由 workflow.py 的 StopReason 体系单独负责。

映射优先级（与 determine_stop_reason 的判定顺序对齐，workflow.py:119）：
    1. test_passed=True                    → TASK_COMPLETED（收敛优先于一切）
    2. budget_exceeded=True                → VERIFICATION_FAILURE
    3. regression_detected=True            → VERIFICATION_FAILURE
    4. stop_reason 命中规约/计划层失效集合  → SPECIFICATION_FAILURE
    5. stop_reason 命中生成能力失效集合     → GENERATION_CAPABILITY_FAILURE
    6. 其余（含 stop_reason 缺失/UNKNOWN）  → UNCATEGORIZED（兜底可度量）
"""

from __future__ import annotations

from enum import StrEnum


class FailureBucket(StrEnum):
    """终局失效桶（项目自有定义，观测层分类视角参考 MAST arXiv:2503.13657）。

    TASK_COMPLETED
        测试收敛（test_passed=True）——任务终局为"生成测试全部通过"。
    SPECIFICATION_FAILURE
        规约/计划层失效：Planner 规约降级（logic_degraded）、测试缺陷判定
        达再生成上限、诊断关键词把失败归因于"测试生成错误"——问题出在
        "对被测代码的理解/计划"环节。
    GENERATION_CAPABILITY_FAILURE
        生成能力不足：迭代耗尽仍未通过、连续补丁无效、覆盖率停滞——
        系统正常运转但"生成不出有效产物"。
    VERIFICATION_FAILURE
        验证侧拦截：预算硬闸触发、回归检测拒绝——产物被安全/资源闸门
        主动终止（区别于"生成不出"）。
    UNCATEGORIZED
        兜底桶：状态信息不足或未命中任何映射（必须保持可度量，
        占比过高说明映射表需扩展）。
    """

    TASK_COMPLETED = "task_completed"
    SPECIFICATION_FAILURE = "specification_failure"
    GENERATION_CAPABILITY_FAILURE = "generation_capability_failure"
    VERIFICATION_FAILURE = "verification_failure"
    UNCATEGORIZED = "uncategorized"


# StopReason.value → 失效桶映射（与 workflow.py StopReason 枚举值对齐）。
# 映射表为模块级常量，扩展 StopReason 时同步维护（UNCATEGORIZED 兜底保证
# 未映射新值不抛异常，只进兜底桶并可被观测）。
_STOP_REASON_TO_BUCKET: dict[str, FailureBucket] = {
    "test_passed": FailureBucket.TASK_COMPLETED,
    "test_passed_converged": FailureBucket.TASK_COMPLETED,
    # 规约/计划层失效
    "test_defect_regeneration_cap": FailureBucket.SPECIFICATION_FAILURE,
    "test_gen_diagnosis": FailureBucket.SPECIFICATION_FAILURE,
    "test_gen_diagnosis_early": FailureBucket.SPECIFICATION_FAILURE,
    # 生成能力不足
    "max_iterations": FailureBucket.GENERATION_CAPABILITY_FAILURE,
    "max_iterations_reached": FailureBucket.GENERATION_CAPABILITY_FAILURE,
    "skip_debugger_repair_invalid": FailureBucket.GENERATION_CAPABILITY_FAILURE,
    "coverage_stall": FailureBucket.GENERATION_CAPABILITY_FAILURE,
    "recursion_limit": FailureBucket.GENERATION_CAPABILITY_FAILURE,
    # 验证侧拦截
    "budget_exceeded": FailureBucket.VERIFICATION_FAILURE,
    "regression_detected": FailureBucket.VERIFICATION_FAILURE,
    # unknown 显式进兜底（不冒充分类结论）
    "unknown": FailureBucket.UNCATEGORIZED,
}


def annotate_final_state(state: dict) -> dict:
    """把工作流最终状态标注为失效桶（纯函数，幂等，零副作用）。

    判定优先级见模块 docstring；test_passed=True 恒优先（收敛即完成，
    不看 stop_reason——收敛后其他字段的残留状态不改变终局语义）。

    Args:
        state: 工作流最终状态（run_benchmark per-task 行 / graph.invoke 输出）。
            必需键：无（缺键保守落 UNCATEGORIZED）。

    Returns:
        {"bucket": FailureBucket, "stop_reason": str, "detail": str}
        stop_reason 为 state 中的原值（缺失记 ""）。
    """
    test_passed = bool(state.get("test_passed"))
    stop_reason = str(state.get("stop_reason") or "")

    if test_passed:
        return {
            "bucket": FailureBucket.TASK_COMPLETED,
            "stop_reason": stop_reason,
            "detail": "测试全部通过（收敛优先，不看 stop_reason）",
        }
    # 未收敛：预算/回归是显式拦截信号（状态字段与 stop_reason 任一命中即判）
    if state.get("budget_exceeded") or stop_reason == "budget_exceeded":
        return {
            "bucket": FailureBucket.VERIFICATION_FAILURE,
            "stop_reason": stop_reason,
            "detail": "任务级预算硬闸触发（token/费用超限）",
        }
    if state.get("regression_detected") or stop_reason == "regression_detected":
        return {
            "bucket": FailureBucket.VERIFICATION_FAILURE,
            "stop_reason": stop_reason,
            "detail": "回归检测拒绝（P2P 门禁判过度修复/误删逻辑）",
        }
    # 其余按 stop_reason 查表；无 stop_reason 时（路由层写入会被 LangGraph
    # 丢弃的已知问题）尝试用 logic_degraded 弱信号提示规约层失效
    if stop_reason:
        bucket = _STOP_REASON_TO_BUCKET.get(stop_reason, FailureBucket.UNCATEGORIZED)
        return {
            "bucket": bucket,
            "stop_reason": stop_reason,
            "detail": f"按 stop_reason={stop_reason} 查表映射",
        }
    if state.get("logic_degraded"):
        return {
            "bucket": FailureBucket.SPECIFICATION_FAILURE,
            "stop_reason": "",
            "detail": "stop_reason 缺失且 logic_degraded=True（规约降级弱信号）",
        }
    return {
        "bucket": FailureBucket.UNCATEGORIZED,
        "stop_reason": stop_reason,
        "detail": "状态信息不足，未命中任何映射（兜底桶）",
    }


def summarize_batch(states: list[dict]) -> dict:
    """批量标注并聚合桶分布（占比保留 4 位小数，和恒为 1）。

    Args:
        states: 工作流最终状态列表（可为空）。

    Returns:
        {"total": int, "counts": {桶值: int}, "shares": {桶值: float}}；
        空列表 → total=0、counts/shares 全桶为 0。
    """
    counts = {bucket.value: 0 for bucket in FailureBucket}
    for state in states:
        counts[annotate_final_state(state)["bucket"].value] += 1
    total = len(states)
    shares = {k: (round(v / total, 4) if total else 0.0) for k, v in counts.items()}
    return {"total": total, "counts": counts, "shares": shares}


def render_markdown(summary: dict, title: str = "终局失效分布") -> str:
    """把 summarize_batch 的结果渲染为 Markdown 表（报告层消费）。

    Args:
        summary: summarize_batch 的输出。
        title: 表格标题。

    Returns:
        Markdown 文本（含标题、表头、全部五桶行——0 桶也列出，保证
        分布口径跨批次可比）。
    """
    lines = [f"## {title}", ""]
    lines.append("| 失效桶 | 数量 | 占比 |")
    lines.append("| --- | ---: | ---: |")
    label_map = {b.value: b.name for b in FailureBucket}
    for bucket in FailureBucket:
        key = bucket.value
        lines.append(
            f"| {label_map[key]} ({key}) | {summary['counts'].get(key, 0)} | {summary['shares'].get(key, 0.0):.4f} |"
        )
    lines.append("")
    lines.append(f"总计：{summary.get('total', 0)} 个任务")
    return "\n".join(lines)


__all__ = [
    "FailureBucket",
    "annotate_final_state",
    "render_markdown",
    "summarize_batch",
]
