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

消费方（I1，2026-10-16 起为**生产接线**，此前只有单测消费）：
    - experiments/run_benchmark.py::_failure_attribution_for_result —— 逐任务
      把终局状态标注为四键（failure_bucket / failure_bucket_detail /
      attribution_edge / attribution_fault_side）写进批次工件 details[]；
    - 同文件 _aggregate_failure_buckets —— 臂级桶分布 + edge/fault_side 计数，
      落 summary.results[臂].failure_bucket_distribution；
    - render_markdown —— 报告层表格（分布 + 分母披露）。
**不接主流程路由**——桶判定纯观测，路由语义仍由 workflow.py 的 StopReason
体系单独负责。

映射优先级（与 determine_stop_reason 的判定顺序对齐，workflow.py:127）：
    1. test_passed=True                    → TASK_COMPLETED（收敛优先于一切）
    2. budget_exceeded=True                → VERIFICATION_FAILURE
    3. regression_detected=True            → VERIFICATION_FAILURE
    4. stop_reason 命中规约/计划层失效集合  → SPECIFICATION_FAILURE
    5. stop_reason 命中生成能力失效集合     → GENERATION_CAPABILITY_FAILURE
    5.5 stop_reason 无信息（缺失或 "unknown"）且 logic_degraded=True
                                           → SPECIFICATION_FAILURE（弱信号，
                                             I3：unknown 不再抢占本步）
    6. 其余                                → UNCATEGORIZED（兜底可度量）
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
    # unknown 显式进兜底（不冒充分类结论）。I3（2026-10-16）：本条目现仅保证
    # 映射表对 StopReason 全域**封闭**（test_mapping_covers_all_workflow_stop_reasons
    # 依赖它），annotate_final_state 已不再用它抢占 logic_degraded 弱信号——
    # "unknown" 语义是无信息，不是一条归因证据。
    "unknown": FailureBucket.UNCATEGORIZED,
}


# ─── 修复引擎批次 XII（ADR-0026）：交互中心归因增补 ──────────────────────────
# 第十七轮审查建议 19（"Model or Harness?" 2026 交互中心分类法——引用核验
# 状态：未一手核验，方向锚点）：把失败定位到具体交互边并标注故障侧，
# 使每个标签直接对应修复动作（model-side → prompt/后训练；harness-side
# → scaffolding；environment → 执行环境；grader → 评估口径）。
# 本层为终局桶的**增补维度**（非替换——终局桶保留跨臂可比职能，
# MAST 式分布照旧输出）；纯确定性推导，零 LLM。

# edge（交互边）× fault_side（故障侧）取值域
INTERACTION_EDGES = (
    "planner_to_generator",  # 规约/计划 ↔ 测试生成
    "generator_to_executor",  # 测试生成 ↔ 执行
    "debugger_to_executor",  # 补丁生成 ↔ 验证
    "harness",  # 编排/基础设施（无特定 agent 交互边）
    "uncategorized",
)
FAULT_SIDES = ("model_side", "harness_side", "environment", "grader", "uncategorized")

# stop_reason → (edge, fault_side) 映射（与 _STOP_REASON_TO_BUCKET 同源维护）
_STOP_REASON_TO_INTERACTION: dict[str, tuple[str, str]] = {
    # 规约/计划层失效：理解/计划错——LLM 侧
    "test_defect_regeneration_cap": ("planner_to_generator", "model_side"),
    "test_gen_diagnosis": ("planner_to_generator", "model_side"),
    "test_gen_diagnosis_early": ("planner_to_generator", "model_side"),
    # 生成能力不足：LLM 产物不达标
    "max_iterations": ("debugger_to_executor", "model_side"),
    "max_iterations_reached": ("debugger_to_executor", "model_side"),
    "skip_debugger_repair_invalid": ("debugger_to_executor", "model_side"),
    "coverage_stall": ("generator_to_executor", "model_side"),
    # 编排上界/预算：scaffolding 侧
    "recursion_limit": ("harness", "harness_side"),
    "budget_exceeded": ("harness", "harness_side"),
    # 验证门拦截：门组件属 harness
    "regression_detected": ("debugger_to_executor", "harness_side"),
}


def interaction_attribution(state: dict) -> dict:
    """交互边 × 故障侧归因（批次 XII 增补维度，纯函数零 LLM）。

    判定优先级（与 annotate_final_state 对齐）：
        1. 收敛任务（test_passed=True）→ ("harness", "uncategorized")
           归因只对失败有意义（收敛行 edge 记 harness、side 记
           uncategorized，不冒充归因结论）；
        2. budget_exceeded / recursion_limit → harness 边 + harness 侧
           （编排上界问题——修复动作指向 scaffolding）；
        3. regression_detected → debugger↔executor 边 + harness 侧
           （验证门组件拦截，区别于"补丁质量差"的 model 侧）；
        4. 其余按 stop_reason 查 _STOP_REASON_TO_INTERACTION；
        5. 未命中（缺 stop_reason / unknown）→ uncategorized。

    Returns:
        {"edge": str, "fault_side": str}。
    """
    if bool(state.get("test_passed")):
        return {"edge": "harness", "fault_side": "uncategorized"}
    stop_reason = str(state.get("stop_reason") or "")
    if state.get("budget_exceeded") or stop_reason in ("budget_exceeded", "recursion_limit"):
        return {"edge": "harness", "fault_side": "harness_side"}
    if state.get("regression_detected") or stop_reason == "regression_detected":
        return {"edge": "debugger_to_executor", "fault_side": "harness_side"}
    if stop_reason in _STOP_REASON_TO_INTERACTION:
        edge, side = _STOP_REASON_TO_INTERACTION[stop_reason]
        return {"edge": edge, "fault_side": side}
    return {"edge": "uncategorized", "fault_side": "uncategorized"}


def annotate_final_state(state: dict) -> dict:
    """把工作流最终状态标注为失效桶（纯函数，幂等，零副作用）。

    判定优先级见模块 docstring；test_passed=True 恒优先（收敛即完成，
    不看 stop_reason——收敛后其他字段的残留状态不改变终局语义）。

    Args:
        state: 工作流最终状态（`graph.invoke` 输出 / AITesterState 形状的 dict）。
            必需键：无（缺键保守落 UNCATEGORIZED）。
            口径限定（G3，2026-10-16）：本函数读的是**状态通道顶层键**
            （test_passed / stop_reason / budget_exceeded / regression_detected /
            logic_degraded）。run_benchmark 落盘的 per-task 行是**投影**而非状态
            本身（成功键叫 `passed`，且不含 test_plan / logic_degraded），直接喂进来
            会把已收敛任务误判成 UNCATEGORIZED——需先按键名映射回状态形状。
            该映射已由 I1（2026-10-16）实现在
            run_benchmark._failure_attribution_for_result：test_passed 取
            final_state 原值，stop_reason 走 effective_stop_reason（O35：条件边
            函数原地写入的 stop_reason 不被 LangGraph 回写，直读恒 None →
            失败任务会全部落兜底桶），其余三键直读顶层。

    Returns:
        {"bucket": FailureBucket, "stop_reason": str, "detail": str,
         "edge": str, "fault_side": str}——edge/fault_side 为批次 XII
        交互中心归因增补（向后兼容：仅加键，既有消费方零影响）。
        stop_reason 为 state 中的原值（缺失记 ""）。
    """
    test_passed = bool(state.get("test_passed"))
    stop_reason = str(state.get("stop_reason") or "")
    attribution = interaction_attribution(state)

    if test_passed:
        return {
            "bucket": FailureBucket.TASK_COMPLETED,
            "stop_reason": stop_reason,
            "detail": "测试全部通过（收敛优先，不看 stop_reason）",
            **attribution,
        }
    # 未收敛：预算/回归是显式拦截信号（状态字段与 stop_reason 任一命中即判）
    if state.get("budget_exceeded") or stop_reason == "budget_exceeded":
        return {
            "bucket": FailureBucket.VERIFICATION_FAILURE,
            "stop_reason": stop_reason,
            "detail": "任务级预算硬闸触发（token/费用超限）",
            **attribution,
        }
    if state.get("regression_detected") or stop_reason == "regression_detected":
        return {
            "bucket": FailureBucket.VERIFICATION_FAILURE,
            "stop_reason": stop_reason,
            "detail": "回归检测拒绝（P2P 门禁判过度修复/误删逻辑）",
            **attribution,
        }
    # 其余按 stop_reason 查表。I3（2026-10-16）：**"unknown" 不在此列**——它是
    # determine_stop_reason 的保守兜底（第 8 优先级），语义等于"无信息"，而非
    # 一条可用的归因证据。此前 `if stop_reason:` 把它当作有信息处理，于是任何
    # 经 effective_stop_reason（唯一权威读取口径，O35）取终止原因的调用方都会
    # 拿到非空 "unknown" → 查表 → UNCATEGORIZED，**永远走不到下面的
    # logic_degraded 弱信号分支**：G3 把该标记抬到顶层通道修好了键路径，
    # 但读侧分支在生产路径上依然不可达（既有单测只构造"stop_reason 缺失"
    # 的输入，掩盖了这一点；接线批次落盘时才暴露）。弱信号本就是为
    # "stop_reason 不可用"设计的，unknown 正是不可用。
    if stop_reason and stop_reason != "unknown":
        bucket = _STOP_REASON_TO_BUCKET.get(stop_reason, FailureBucket.UNCATEGORIZED)
        return {
            "bucket": bucket,
            "stop_reason": stop_reason,
            "detail": f"按 stop_reason={stop_reason} 查表映射",
            **attribution,
        }
    # 顶层 logic_degraded 由 _planner_node 从 test_plan 抬升写入（G3，2026-10-16）；
    # 在此之前该标记只存在于 test_plan 内部，本分支恒不可达。
    if state.get("logic_degraded"):
        return {
            "bucket": FailureBucket.SPECIFICATION_FAILURE,
            "stop_reason": stop_reason,
            "detail": f"stop_reason 无信息（{stop_reason or '缺失'}）且 logic_degraded=True（规约降级弱信号）",
            **attribution,
        }
    return {
        "bucket": FailureBucket.UNCATEGORIZED,
        "stop_reason": stop_reason,
        "detail": "状态信息不足，未命中任何映射（兜底桶）",
        **attribution,
    }


def summarize_batch(states: list[dict]) -> dict:
    """批量标注并聚合桶分布（占比保留 4 位小数，和恒为 1）。

    Args:
        states: 工作流最终状态列表（可为空）。

    Returns:
        {"total": int, "counts": {桶值: int}, "shares": {桶值: float},
         "fault_side_counts": {侧值: int}, "edge_counts": {边值: int}}——
        后两键为批次 XII 交互中心归因聚合；空列表 → 全零。
    """
    counts = {bucket.value: 0 for bucket in FailureBucket}
    fault_side_counts = dict.fromkeys(FAULT_SIDES, 0)
    edge_counts = dict.fromkeys(INTERACTION_EDGES, 0)
    for state in states:
        annotation = annotate_final_state(state)
        counts[annotation["bucket"].value] += 1
        fault_side_counts[annotation["fault_side"]] += 1
        edge_counts[annotation["edge"]] += 1
    total = len(states)
    shares = {k: (round(v / total, 4) if total else 0.0) for k, v in counts.items()}
    return {
        "total": total,
        "counts": counts,
        "shares": shares,
        "fault_side_counts": fault_side_counts,
        "edge_counts": edge_counts,
    }


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
    # I1（2026-10-16）：分母诚实——批次聚合方（run_benchmark
    # ._aggregate_failure_buckets）把"无工作流终局状态"的行（运行异常 /
    # 限流耗尽）单列 unclassified_rows 而**不**折进 uncategorized 桶，故
    # total 只是"有终局状态可分类"的行数。不显式披露会让报表把批次规模
    # 读小，且"归因未接线"与"状态信息不足"同形。summarize_batch 的输出
    # 无该键（全量分类）→ 不渲染此行，向后兼容。
    if summary.get("unclassified_rows"):
        lines.append(
            f"（另有 {summary['unclassified_rows']} 个任务无工作流终局状态"
            f"〔运行异常/限流〕，不计入分布；批次共 {summary.get('total_rows', 0)} 行）"
        )
    # 批次 XII（ADR-0026）：交互中心归因表（增补维度，未命中键全零渲染）
    lines += ["", "### 交互中心归因（edge × fault_side，批次 XII 增补）", ""]
    lines.append("| 故障侧 | 数量 | 修复动作指向 |")
    lines.append("| --- | ---: | --- |")
    action_map = {
        "model_side": "prompt/后训练/生成质量",
        "harness_side": "scaffolding/编排/守卫组件",
        "environment": "执行环境",
        "grader": "评估口径",
        "uncategorized": "—（信息不足）",
    }
    side_counts = summary.get("fault_side_counts") or {}
    for side in FAULT_SIDES:
        lines.append(f"| {side} | {side_counts.get(side, 0)} | {action_map[side]} |")
    lines.append("")
    edge_counts = summary.get("edge_counts") or {}
    lines.append("| 交互边 | 数量 |")
    lines.append("| --- | ---: |")
    for edge in INTERACTION_EDGES:
        lines.append(f"| {edge} | {edge_counts.get(edge, 0)} |")
    return "\n".join(lines)


__all__ = [
    "FAULT_SIDES",
    "INTERACTION_EDGES",
    "FailureBucket",
    "annotate_final_state",
    "interaction_attribution",
    "render_markdown",
    "summarize_batch",
]
