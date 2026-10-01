"""
9. P2 LLM 集成冒烟脚本（改进清单 P2 #9，CI 可选作业）。

最小成本验证"真实 LLM 端点连通性 + 输出格式基本正常"：发一个极小
（≤ 256 token）的固定 prompt 给默认 LLM 端点（LLM_1_*），断言响应
非空且（若要求）可被宽松 JSON 提取或为合法自然语言。不跑基准、
不写 LLM 缓存（CI 作业已置 AITESTER_LLM_CACHE=0）、不消耗多轮 token。

默认关闭（历史口径零 LLM 成本）：仅当 AITESTER_SMOKE_LLM=true 时执行
真实 LLM 调用；缺省 false 时打印跳过说明并成功退出（CI 作业恒绿，
只有真实端点连通性失败或输出异常才 red）。

用法：
    AITESTER_SMOKE_LLM=true python experiments/run_smoke_llm.py
    python experiments/run_smoke_llm.py --allow-empty   # 仅验证端点可达（不校验 JSON）
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _smoke_enabled() -> bool:
    """冒烟开关（AITESTER_SMOKE_LLM=true 时执行真实调用，默认 false 跳过）。"""
    return os.getenv("AITESTER_SMOKE_LLM", "false").lower() == "true"


def _smoke_prompt() -> str:
    """最小冒烟 prompt（固定文本，≤ 256 token，无代码上下文）。"""
    return "请用一句话回答：1+1 等于几？只输出数字，不要任何解释、前后缀或 markdown 包裹。"


def _check_response(text: str, require_json: bool) -> tuple[bool, str]:
    """断言冒烟响应基本正常。

    Args:
        text: LLM 原始响应。
        require_json: True 时要求响应可被宽松 JSON 提取（或为合法数字/文本）；
            False 时仅要求非空（端点可达）。

    Returns:
        (通过与否, 诊断信息)。
    """
    stripped = (text or "").strip()
    if not stripped:
        return False, "LLM 响应为空（端点可达但无内容）"
    if not require_json:
        return True, f"端点可达，响应 {len(stripped)} 字符"
    # require_json：宽松判定——响应可被 extract_json_object 解析，或为纯数字/短文本
    from src.utils.helpers import extract_json_object

    try:
        extract_json_object(stripped)
        return True, "响应可被宽松 JSON 提取（格式正常）"
    except Exception:
        pass
    # 非 JSON 但为合法短文本（如纯数字）也视为正常（冒烟 prompt 允许自然语言回答）
    if len(stripped) <= 256:
        return True, f"响应为合法短文本（{len(stripped)} 字符），格式正常"
    return False, f"响应过长或格式异常（{len(stripped)} 字符）"


def _call_default_llm() -> str:
    """调用默认 LLM 端点（LLM_1_*）获取冒烟响应。

    复用 base_agent 的故障转移 / 缓存客户端（但 CI 已置 AITESTER_LLM_CACHE=0，
    不写盘），避免重复造轮子。无可用配置时抛异常（调用方捕获）。
    """
    from src.agents.base_agent import BaseAgent

    agent = BaseAgent(system_prompt="You are a minimal smoke-test responder.")
    return agent._call_llm_with_cache(_smoke_prompt(), max_retries=1)


def main() -> int:
    parser = argparse.ArgumentParser(description="AITester LLM 集成冒烟（P2 #9，默认关闭）")
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="仅验证端点可达（不校验响应格式/JSON），用于最低成本连通性检查",
    )
    parser.add_argument(
        "--require-json",
        action="store_true",
        help="要求响应可被宽松 JSON 提取或为合法短文本（默认：仅要求非空）",
    )
    args = parser.parse_args()

    if not _smoke_enabled():
        print("AITESTER_SMOKE_LLM != true，跳过 LLM 冒烟（历史口径零 LLM 成本）。")
        print(
            "如需真实 LLM 集成冒烟，设 AITESTER_SMOKE_LLM=true 并配置 LLM_1_API_KEY / LLM_1_BASE_URL / LLM_1_MODEL_NAME。"
        )
        return 0

    require_json = args.require_json and not args.allow_empty
    print(f"执行 LLM 冒烟（require_json={require_json}, allow_empty={args.allow_empty}）…")
    try:
        response = _call_default_llm()
    except Exception as e:  # 冒烟需捕获所有端点异常
        print(f"FAIL：LLM 端点调用异常：{e}")
        return 1

    ok, diag = _check_response(response, require_json)
    print(f"响应片段：{(response or '').strip()[:120]}…")
    print(f"{'PASS' if ok else 'FAIL'}：{diag}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
