"""
M7（2026-09-29 审查 P0）：变异反馈闭环——图内 mutation_advisor 节点 +
变异器上移（experiments/ → src/tools/）。

背景：
    历史变异反馈闭环"未闭合"——`experiments/run_benchmark.py` 在 workflow
    终止**之后**才经 build_mutation_feedback 计算"存活变异体"并写入
    `final_state["mutation_feedback"]`，但该键在 workflow 执行期间从不被
    Generator 消费（图内 `state.get("mutation_feedback")` 恒为 None），
    单智能体基线的反馈路径是死代码。本模块把闭环变成真实图内节点：
    executor → mutation_advisor → generator（复用现有 `regenerate` 路由
    与 `_MAX_REGENERATIONS` 上限），变异评估在每一轮 executor 失败后
    即时产出"存活变异体清单"，供下一轮 Generator 消费补强断言。

设计口径（保守、默认关、零 LLM 成本）：
    - MUTATION_ADVISOR_ENABLE=false（默认）时，图拓扑与历史完全一致：
      mutation_advisor 节点不注册，_should_debug 路由行为零变化；
    - MUTATION_ADVISOR_ENABLE=true 时，在 executor → _should_debug 的
      "regenerate" 路径中插入 mutation_advisor 节点（executor →
      mutation_advisor → generator），该节点对 (target_code,
      generated_test) 跑一次变异评估（subprocess 沙箱，零 LLM），把
      存活变异体清单写入 state["mutation_feedback"]，Generator 下一轮
      经 build_mutation_prompt_section 消费注入 prompt；
    - mutation_advisor 节点自身是纯数据节点（不产生 LLM 调用），
      测量失败 / 无存活变异体 / 开关关时 state["mutation_feedback"]
      保持 None（历史口径不变）；
    - 受 _MAX_REGENERATIONS 上限保护（与 3.1 双向诊断 / O4 恒真断言
      同口径），防死循环。

消费方式：
    - _generator_node 读取 state["mutation_feedback"]，经
      build_mutation_prompt_section 渲染为"存活变异体清单"段落注入
      Generator prompt（1.2 改进的图内接线版——历史 1.2 的 prompt
      注入逻辑不变，仅数据来源从"benchmark 层预置"改为"图内节点
      即时产出"）；
    - 实验分析：experiments/ 读取 state["mutation_feedback"] 统计
      "闭环触发率"与"mutation_score 随迭代收敛曲线"。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from src.graph.state import AITesterState

logger = logging.getLogger(__name__)

_ENV = "MUTATION_ADVISOR_ENABLE"


def mutation_advisor_enabled() -> bool:
    """M7 开关（MUTATION_ADVISOR_ENABLE=true 时启用，默认 false 历史口径）。"""
    return os.getenv(_ENV, "false").lower() in ("true", "1", "on")


def build_mutation_prompt_section(mutation_feedback: dict[str, Any] | None) -> str:
    """把存活变异体清单渲染为 Generator prompt 注入段落（空时返回空串）。

    保守口径：mutation_feedback 为 None / 无存活变异体 / 开关关时
    调用方不调本函数，prompt 与历史逐字节一致。

    与 experiments/mutation_testing.build_mutation_feedback 产出的
    dict schema 同构（{"available": bool, "survived_mutants": [str],
    "mutation_score": float, ...}），本函数仅做渲染，不做测量。
    """
    if not mutation_feedback or not mutation_feedback.get("survived_mutants"):
        return ""
    survived = mutation_feedback.get("survived_mutants", [])
    score = mutation_feedback.get("mutation_score")
    lines = [f"【存活变异体清单（M7 图内变异反馈，共 {len(survived)} 条，变异得分 {score}）】"]
    for i, desc in enumerate(survived[:15], start=1):
        lines.append(f"{i}. {desc}")
    lines.append("请优先为上述存活变异体设计能捕获的断言（边界值 / 异常路径 / 短路条件），提升变异测试得分。")
    return "\n".join(lines)


def _mutation_advisor_node(state: AITesterState) -> dict[str, Any]:
    """M7 图内变异顾问节点：对 (target_code, generated_test) 跑变异评估。

    纯数据节点（零 LLM 成本）：
    - 调用 build_mutation_feedback（experiments/mutation_testing 的
      测量层，subprocess 沙箱跑 pytest + 变异体）；
    - 把结果写入 state["mutation_feedback"]（Generator 下一轮消费）；
    - 测量失败 / 无变异体 / 无存活变异体时 mutation_feedback 保持
      None（保守降级，不阻断主流程）。

    节点仅在 MUTATION_ADVISOR_ENABLE=true 时注册（见 workflow.py
    build_workflow 的条件注册块），默认关时图拓扑与历史完全一致。

    Args:
        state: 当前工作流状态（含 target_code / generated_test /
            iteration 等字段）。

    Returns:
        更新后的状态字典，包含 mutation_feedback（dict | None）。
    """
    from src.graph.tracing import _trace_node

    t0 = time.time()

    # 调用 experiments/mutation_testing 的测量层（纯 subprocess + pytest，
    # 零 LLM 成本；_run_mutant_tests 沙箱超时 30s，整体节点耗时可控）
    from experiments.mutation_testing import build_mutation_feedback

    feedback: dict[str, Any] | None = None
    try:
        feedback = build_mutation_feedback(
            source_code=state.get("target_code") or "",
            test_code=state.get("generated_test") or "",
        )
    except Exception as e:
        logger.debug("M7 变异顾问节点执行异常（保守降级 None）: %s", e)
        feedback = None

    # 仅当评估可用且有存活变异体时写入 state（无存活变异体 = 测试已
    # 全杀死，无需补强，历史口径不变）
    update: dict[str, Any] = {}
    if feedback and feedback.get("available") and feedback.get("survived_mutants"):
        update["mutation_feedback"] = feedback
        logger.info(
            "M7 变异顾问节点：存活 %d 变异体（score=%.4f），注入下一轮 Generator prompt",
            len(feedback["survived_mutants"]),
            feedback.get("mutation_score") or 0.0,
        )
    else:
        logger.info(
            "M7 变异顾问节点：无存活变异体（available=%s, survived=%d），不注入",
            bool(feedback and feedback.get("available")),
            len((feedback or {}).get("survived_mutants", [])),
        )

    _trace_node(
        "mutation_advisor",
        output_summary={
            "survived_mutants": len((feedback or {}).get("survived_mutants", [])),
            "mutation_score": (feedback or {}).get("mutation_score"),
        },
        decision="injected" if update.get("mutation_feedback") else "no_surge",
        duration_ms=(time.time() - t0) * 1000,
        iteration=state.get("iteration", 0),
    )
    return update


# 供 workflow.py 注册节点用（避免直接 import 内部函数名 _mutation_advisor_node
# 触发 ruff F401 未使用警告；节点函数本身经 workflow.build_workflow 的条件
# 注册路径消费，本处仅做模块级导出声明）
__all__ = [
    "_mutation_advisor_node",
    "build_mutation_prompt_section",
    "mutation_advisor_enabled",
]
