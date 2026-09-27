"""
能力演示：任务级成本预算硬上限（COST_BUDGET_ENABLE，5.4）。

最小可运行脚本：验证"消耗超限时自动停调用，避免免费额度跑飞"的能力。
无需真实 LLM key 亦可离线运行——本脚本仅演示预算累计器 / 超限判定
的观测口径，不发起 LLM 调用。

运行：
    python examples/cost_budget_demo/run.py

预期输出说明：
    - 离线（默认）：打印预算开关状态与"模拟消耗"的超限判定，
      演示 check_budget 在超限时返回 False（调用方降级停调）；
    - 启用（COST_BUDGET_ENABLE=true + COST_BUDGET_TOKENS=1000）：
      真实工作流中 token 累计超限时 BaseAgent._call_llm 前置守卫
      抛 BudgetExceededError，planner / generator / debugger 节点
      降级兜底（不再空转烧 token）。

涉及的环境变量开关（详见 .env.example 注释）：
    COST_BUDGET_ENABLE     默认 false（开启任务级预算硬上限）
    COST_BUDGET_TOKENS     token 预算值（COST_BUDGET_ENABLE=true 时生效）
    COST_BUDGET_USD        费用预算值（与 token 预算取先到者）
    COST_USD_PER_1K        每 1K token 计价（费用预算换算用）
"""

from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main() -> int:
    """演示成本预算累计器与超限判定的观测口径（不消耗 LLM token）。"""
    from src.graph.cost_budget import (
        _budget_enabled,
        check_budget,
        get_process_budget_stats,
        is_budget_exceeded,
        reset_budget,
    )

    # 演示"未启用"默认口径：超限判定恒 True（历史行为不变，预算守卫短路）
    os.environ.setdefault("COST_BUDGET_ENABLE", "false")
    reset_budget()
    print("── 默认口径（COST_BUDGET_ENABLE=false，历史行为）")
    print(f"  _budget_enabled() = {_budget_enabled()}")
    print(f"  模拟消耗 99999 token 的超限判定 = {check_budget(consumed_delta_tokens=99999)}（开关关 → 恒 True 可继续）")
    print(f"  is_budget_exceeded() = {is_budget_exceeded()}")

    # 演示"启用 + 小预算"口径：超限判定为 False（调用方应停调）
    os.environ["COST_BUDGET_ENABLE"] = "true"
    os.environ["COST_BUDGET_TOKENS"] = "1000"
    reset_budget()
    print("\n── 启用口径（COST_BUDGET_ENABLE=true, COST_BUDGET_TOKENS=1000）")
    ok_100 = check_budget(consumed_delta_tokens=100)
    ok_9999 = check_budget(consumed_delta_tokens=9999)
    print(f"  消耗 100 token（<预算）→ check_budget = {ok_100}（继续）")
    print(f"  再消耗 9999 token（超预算）→ check_budget = {ok_9999}（应停调）")
    print(f"  超限后 is_budget_exceeded() = {is_budget_exceeded()}")
    print(f"  进程级预算统计 = {get_process_budget_stats()}")

    print(
        "\n注意：本脚本仅演示观测口径，不发起真实 LLM 调用；真实工作流中"
        " 超限经 BaseAgent._call_llm 前置守卫抛 BudgetExceededError，"
        " planner / generator / debugger 节点降级兜底（不再空转烧 token）。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
