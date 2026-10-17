"""P-1（2026-10-18）规格可执行示例生成器：**spec-only**（零缺陷代码输入）。

动机（承接 O-1）
----------------
O-1 仪器治疗后 oracle 分类从 `fp 29` 降到 `fp 2`（仅断言型），但
**`correct` 仍为 0**——语义质量瓶颈是"机器化断言不触达缺陷行为"。P-1 给
oracle 增加一条**规格可执行示例**通道：由 LLM **只看规约材料**（Planner
`logic_analysis` / 人类 docstring，**绝不发送缺陷代码**）生成
`{"input": ..., "expected": ...}` 示例，编译为 `assert f(*input) == expected`。
spec-only 的理由：向 LLM 发送缺陷代码会让它从"实现"反推期望值（oracle-from-
implementation，正是 M-2 记录的 misguided 根因）；只给规约才能测"规格是否
足够可执行"。

口径纪律
--------
- **每任务最多 1 次 LLM 调用**（`--per-task-calls 1` 语义；由调用方按任务循环）；
  默认 `LLM_MAX_OUTPUT_TOKENS=512`（小 max_tokens 控成本）。
- **strict schema**：响应必须是 JSON 对象 `{"examples": [{"input":...,
  "expected":...}, ...]}`（兼容裸 list）；非法条目由
  ``src.specs.spec_ir.parse_examples`` 丢弃（NaN/非字面量/形状不符），
  **解析/调用失败一律透传空列表并记录原因**（不抛异常、不阻断重放）。
- **缓存**：走项目 `_call_llm_with_cache`（支持 `AITESTER_CACHE_NAMESPACE`
  与 `AITESTER_LLM_CACHE`）；本模块可显式传 `cache_namespace`（临时设置并
  恢复环境变量，防跨臂串味）。
- 不打印/不落盘任何 API key；prompt/response 只落 sha256。

用法（由 `experiments/oracle_examples_replay.py` 消费）::

    from experiments.spec_examples_generator import generate_spec_examples
    result = generate_spec_examples(
        {"function_name": "add", "postconditions": [...]},
        signature_params=["a", "b"],
        task_id="quixbugs__add",
    )
    # {"status": "ok"/"empty"/"error", "examples": [...], "reason": str|None,
    #  "prompt_sha256": ..., "usage": {...}, "wall_s": ...}
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from src.specs.spec_ir import _DEFAULT_EXAMPLES_MAX, parse_examples

logger = logging.getLogger(__name__)

# 默认小 max_tokens（P-1 预算口径；环境变量显式给出时优先）
DEFAULT_MAX_OUTPUT_TOKENS = 512
_ENV_MAX_OUTPUT_TOKENS = "LLM_MAX_OUTPUT_TOKENS"
_ENV_CACHE_NAMESPACE = "AITESTER_CACHE_NAMESPACE"
_PRICE_TABLE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "price_table.json"

SYSTEM_PROMPT = """你是"规格可执行示例"生成器。你只能看到被测函数的**规格描述**
（函数名、参数名、输入/输出域、前置/后置条件、边界情况、人类 docstring）。

任务：给出最多 5 条可执行示例，每条形如：
    {"input": <按参数顺序的实参列表>, "expected": <函数返回值>}

硬性要求：
1. 只依据规格推导期望值；**不要猜测实现**，规格未定义的情形不要输出示例；
2. input 必须是 JSON 字面量列表 [参数1, 参数2, ...]（参数顺序见"参数名"，
   即按位置展开的实参；单参函数也写成 [x]），每个值必须是
   int/float/str/bool/null/列表/字典等 JSON 字面量；
3. expected 必须是 JSON 字面量；
4. 示例输入应**小且可快速执行**：避免大整数（>1e6）、长序列/大集合、
   深递归或组合爆炸输入（如 n>1000），否则会拖慢/超时判定；
5. 期望值必须严格由规格推导；边界情况（空输入/0/负数/重复元素/
   非法输入）只有在规格明确给出结果时才作为示例，否则省略；
4. 只输出一个 JSON 对象，格式严格为：
   {"examples": [{"input": [...], "expected": ...}, ...]}
   不要输出 markdown 代码围栏、解释或任何其它文本。"""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _format_material(material: dict[str, Any] | None) -> str:
    """把规约材料渲染为 prompt 段落（只含规格字段；**不含**缺陷代码）。"""
    if not isinstance(material, dict):
        return "（无规约材料）"
    lines: list[str] = []
    for key, label in (
        ("function_name", "函数名"),
        ("source", "规约来源"),
        ("input_domain", "输入域"),
        ("output_domain", "输出域"),
        ("preconditions", "前置条件"),
        ("postconditions", "后置条件"),
        ("invariants", "不变量"),
        ("edge_cases", "边界情况"),
        ("preconditions_expr", "前置条件（表达式）"),
        ("postconditions_expr", "后置条件（表达式）"),
        ("invariants_expr", "不变量（表达式）"),
    ):
        value = material.get(key)
        if value in (None, "", [], {}):
            continue
        rendered = "\n".join(f"  - {item}" for item in value) if isinstance(value, list) else f"  {value}"
        lines.append(f"{label}：\n{rendered}")
    human_spec = material.get("human_spec")
    if isinstance(human_spec, str) and human_spec.strip():
        lines.append(f"人类规格（docstring）：\n{human_spec.strip()}")
    return "\n".join(lines) if lines else "（无规约材料）"


def build_spec_examples_prompt(
    material: dict[str, Any] | None,
    signature_params: list[str] | None,
    *,
    max_examples: int = _DEFAULT_EXAMPLES_MAX,
) -> str:
    """构造 spec-only prompt（P-1：**不包含**任何缺陷代码/实现片段）。

    Args:
        material: 规约材料（Planner logic_analysis / 人类 docstring / 锚材料）。
        signature_params: 参数名列表（仅元数据，用于 input 顺序；可以为 None）。
        max_examples: 最多示例数（≤5）。

    Returns:
        prompt 字符串（纯规格；测试会断言不含缺陷代码片段）。
    """
    params = "、".join(signature_params) if signature_params else "（未知；input 用单元素列表）"
    func_name = material.get("function_name") if isinstance(material, dict) else None
    return (
        f"函数名：{func_name or 'unknown'}\n"
        f"参数名（input 列表按此顺序）：{params}\n"
        f"最多示例数：{max(0, int(max_examples))}\n\n"
        "规格材料：\n"
        f"{_format_material(material)}\n\n"
        '请只输出 JSON：{"examples": [{"input": [...], "expected": ...}]}'
    )


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_json_payload(text: str) -> Any:
    """从 LLM 响应提取 JSON（兼容代码围栏/前后解释文本；失败抛 ValueError）。"""
    raw = _FENCE_RE.sub("", str(text or "")).strip()
    if not raw:
        raise ValueError("empty_response")
    # 直接解析 → 失败则扫描首个 { 或 [ 并 raw_decode（容忍前缀说明文字）
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char not in "[{":
            continue
        try:
            value, _end = decoder.raw_decode(raw[index:])
            return value
        except json.JSONDecodeError:
            continue
    raise ValueError("json_parse_error")


def validate_examples_payload(payload: Any, *, max_examples: int = _DEFAULT_EXAMPLES_MAX) -> list[dict[str, Any]]:
    """strict schema 校验：只接受 ``{"examples": [...]}`` 或裸 list。

    逐条校验交给 ``spec_ir.parse_examples``（非法形状丢弃、不抛异常、≤5 条）。
    """
    raw: Any = None
    if isinstance(payload, dict):
        raw = payload.get("examples")
    elif isinstance(payload, list):
        raw = payload
    return parse_examples(raw, max_examples=max_examples)


def parse_examples_response(
    text: str,
    *,
    max_examples: int = _DEFAULT_EXAMPLES_MAX,
) -> tuple[list[dict[str, Any]], str | None]:
    """响应文本 → (examples, 失败原因)。失败透传空列表 + 原因（不抛异常）。"""
    try:
        payload = extract_json_payload(text)
    except ValueError as e:
        return [], str(e)
    examples = validate_examples_payload(payload, max_examples=max_examples)
    if not examples:
        return [], "schema_invalid_or_no_valid_example"
    return examples, None


def _call_examples_llm(prompt: str, *, temperature: float = 0.0) -> str:
    """单次 LLM 调用（可被单测 monkeypatch；真实路径走项目缓存客户端）。"""
    agent = _get_agent()
    return agent._call_llm_with_cache(prompt, max_retries=1, temperature=temperature, json_mode=True)


_AGENT: Any = None


def _get_agent() -> Any:
    """惰性构造示例生成 agent（BaseAgent 子类；无 LLM 配置时抛异常由调用方降级）。"""
    global _AGENT
    if _AGENT is None:
        from src.agents.base_agent import BaseAgent

        class _ExamplesAgent(BaseAgent):
            def __init__(self) -> None:
                super().__init__(system_prompt=SYSTEM_PROMPT)

        _AGENT = _ExamplesAgent()
    return _AGENT


def _usage_snapshot() -> dict[str, Any]:
    """当前线程 token 记账快照（真实 API 消耗；缓存命中不计入）。"""
    try:
        from src.budget.token_usage import get_usage

        return dict(get_usage().as_dict())
    except Exception:  # pragma: no cover - 记账层不可用不阻断生成
        return {}


def _usage_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, int]:
    """两次快照差值（input/output/total/llm_calls/cache_hits）。"""
    keys = ("input_tokens", "output_tokens", "total_tokens", "llm_calls", "cache_hits", "cache_avoided_tokens")
    return {key: int(after.get(key, 0) or 0) - int(before.get(key, 0) or 0) for key in keys}


def load_price_table(path: Path = _PRICE_TABLE_PATH) -> dict[str, Any]:
    """读取项目价目表（缺失/非法 → 空 dict；成本不编造）。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def estimate_cost_usd(model: str, usage: dict[str, Any], price_table: dict[str, Any] | None = None) -> float | None:
    """按项目 `price_table.json` 估算美元成本（价目缺失/币种非 USD → None，不编造）。"""
    table = price_table if price_table is not None else load_price_table()
    entry = ((table.get("models") or {}).get(model)) or {}
    if str(entry.get("currency") or "").upper() != "USD":
        return None
    inp = entry.get("input_per_mtok")
    out = entry.get("output_per_mtok")
    if inp is None or out is None:
        return None
    input_tokens = float(usage.get("input_tokens", 0) or 0)
    output_tokens = float(usage.get("output_tokens", 0) or 0)
    return round(input_tokens / 1_000_000 * float(inp) + output_tokens / 1_000_000 * float(out), 6)


def generate_spec_examples(
    material: dict[str, Any] | None,
    *,
    signature_params: list[str] | None = None,
    task_id: str = "",
    max_examples: int = _DEFAULT_EXAMPLES_MAX,
    cache_namespace: str | None = None,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """**每任务 1 次** LLM 调用生成 spec-only 可执行示例（失败透传空 + 原因）。

    Args:
        material: 规约材料（不含缺陷代码）。
        signature_params: 参数名（input 顺序元数据）。
        task_id: 任务 id（仅审计字段）。
        max_examples: 最多示例数（≤5）。
        cache_namespace: 显式缓存命名空间（临时设置 ``AITESTER_CACHE_NAMESPACE``，
            结束时恢复；None = 沿用宿主环境）。
        temperature: 采样温度（默认 0.0，确定性）。

    Returns:
        {"status": "ok"|"empty"|"error", "examples": [...], "reason": str|None,
         "prompt_sha256", "prompt_chars", "response_sha256", "response_chars",
         "usage": {...}, "wall_s", "model", "max_output_tokens",
         "cache_namespace", "task_id"}
        —— 任何失败都不抛异常（examples 空、status/reason 可审计）。
    """
    prompt = build_spec_examples_prompt(material, signature_params, max_examples=max_examples)
    result: dict[str, Any] = {
        "task_id": task_id,
        "status": "empty",
        "examples": [],
        "reason": None,
        "prompt_sha256": _sha256_text(prompt),
        "prompt_chars": len(prompt),
        "response_sha256": None,
        "response_chars": 0,
        "usage": {},
        "wall_s": 0.0,
        "model": _model_name(),
        "max_output_tokens": os.environ.get(_ENV_MAX_OUTPUT_TOKENS, ""),
        "cache_namespace": cache_namespace,
    }
    previous_namespace = os.environ.get(_ENV_CACHE_NAMESPACE)
    t0 = time.time()
    before = _usage_snapshot()
    try:
        # 小 max_tokens：未显式配置时注入默认值（客户端 extra_body 与缓存键读取
        # 该 env；显式 AITESTER env 优先，不覆盖用户设置）
        if _ENV_MAX_OUTPUT_TOKENS not in os.environ:
            os.environ[_ENV_MAX_OUTPUT_TOKENS] = str(DEFAULT_MAX_OUTPUT_TOKENS)
        if cache_namespace:
            os.environ[_ENV_CACHE_NAMESPACE] = cache_namespace
        response = _call_examples_llm(prompt, temperature=temperature)
        examples, reason = parse_examples_response(response, max_examples=max_examples)
        result.update(
            status="ok" if examples else "empty",
            examples=examples,
            reason=reason,
            response_sha256=_sha256_text(response),
            response_chars=len(str(response or "")),
        )
    except Exception as e:  # LLM/网络/配置失败 → 透传空 + 原因（不阻断重放）
        result.update(status="error", reason=f"llm_error:{type(e).__name__}:{str(e)[:200]}")
    finally:
        result["wall_s"] = round(time.time() - t0, 3)
        result["usage"] = _usage_delta(before, _usage_snapshot())
        result["max_output_tokens"] = os.environ.get(_ENV_MAX_OUTPUT_TOKENS, "")
        if cache_namespace:
            if previous_namespace is None:
                os.environ.pop(_ENV_CACHE_NAMESPACE, None)
            else:
                os.environ[_ENV_CACHE_NAMESPACE] = previous_namespace
    return result


def _model_name() -> str:
    """当前默认模型名（非敏感；不打印 key/base_url）。"""
    try:
        import config

        configs = list(getattr(config, "LLM_CONFIGS", []))
        return str(configs[0].model_name) if configs else "unknown"
    except Exception:  # pragma: no cover - 配置缺失不阻断
        return "unknown"
