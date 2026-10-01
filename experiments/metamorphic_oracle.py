"""
N2（2026-09-29 审查 P2）：蜕变关系（metamorphic testing）oracle 钩子。

历史口径：LLM 生成的测试用例是"样本驱动 + 恒真断言检测（O4）"，
当函数无文档字符串、无类型注解（无 oracle 可推导）时检出能力骤降——
这是 SWT-Bench 类"无规格"场景的核心痛点。

蜕变关系（Metamorphic Relation, MR）思想：不验证"输出 == 期望值"
（无 oracle 时不可得），而验证"输入变换后输出满足已知关系"。
例：
- 排序函数：`sort(reverse=True)(x) == list(reversed(sort(x)))`；
- 字符串函数：`f(x.upper()) == f(x)` 当 f 不区分大小写；
- 幂等函数：`f(f(x)) == f(x)`；
- 交换律：`f(a, b) == f(b, a)`。

本模块提供纯数据原语（零 LLM / 零 subprocess，默认关）：

- `metamorphic_enabled()` — 开关判定（METAMORPHIC_ENABLE=true 默认 false）。
- `suggest_metamorphic_relations(function_name, signature, docstring)` —
  从签名/文档启发式匹配 6 类常见 MR 模板，返回可注入 Generator prompt
  的 MR 候选清单（name + description + code_stub）。
- `build_metamorphic_prompt_section(mr_list)` — 把 MR 候选渲染为
  prompt 注入文本（开关关闭时调用方不应调用）。
- `check_metamorphic_relation(relation_code, ref_impl, alt_input, ...)` —
  纯 Python 执行 MR 检查（在 ref_impl 上执行 relation_code 判定是否满足），
  供 executor 层消费（无 subprocess 开销）。

验收指标（N2）：无文档字符串任务（SWT-Bench 口径）的检出率
较纯样本驱动提升（实验层对照：METAMORPHIC_ENABLE on/off 的
detection_rate 差异）。
"""

from __future__ import annotations

import os
from typing import Any

__all__ = [
    "build_metamorphic_prompt_section",
    "check_metamorphic_relation",
    "metamorphic_enabled",
    "suggest_metamorphic_relations",
]

# ─── MR 模板库（6 类常见蜕变关系）──────────────────────────────────────────
# 每项：{"name": 关系名, "description": 语义说明, "trigger": 触发条件,
#        "code_stub": 测试代码骨架（{func} 占位符）}
_MR_TEMPLATES: tuple[dict[str, str], ...] = (
    {
        "name": "idempotence",
        "description": "幂等性：f(f(x)) == f(x)（如归一化/清理函数）",
        "trigger": "func name contains 'normalize|clean|sanitize|strip|trim|dedup|canonical'",
        "code_stub": "r1 = {func}(x)\nassert {func}(r1) == r1, '幂等性违反：f(f(x)) != f(x)'",
    },
    {
        "name": "commutativity",
        "description": "交换律：f(a, b) == f(b, a)（如加法/集合运算）",
        "trigger": "func has 2+ args and name contains 'add|sum|union|merge|combine|intersect'",
        "code_stub": "assert {func}(a, b) == {func}(b, a), '交换律违反：f(a,b) != f(b,a)'",
    },
    {
        "name": "monotonicity",
        "description": "单调性：x <= y → f(x) <= f(y)（如排序/累加）",
        "trigger": "func name contains 'sort|rank|accumulate|cumulative|min|max|log'",
        "code_stub": "assert {func}(x) <= {func}(y), '单调性违反（x<=y 但 f(x)>f(y)）'",
    },
    {
        "name": "reversibility",
        "description": "可逆性：g(f(x)) == x（如 encode/decode、serialize/deserialize）",
        "trigger": "func name contains 'encode|serialize|pack|compress' AND a paired inverse function exists",
        "code_stub": "inv = {inverse}({func}(x))\nassert inv == x, '可逆性违反：g(f(x)) != x'",
    },
    {
        "name": "invariance",
        "description": "不变量：对合法输入，输出类型/范围恒成立（如非负、长度）",
        "trigger": "func has return type hint or docstring mentions constraint",
        "code_stub": "result = {func}(x)\nassert isinstance(result, {ret_type}), '输出类型不变量违反'",
    },
    {
        "name": "dimension_preserve",
        "description": "维度保持：len(f(xs)) == len(xs)（如 map/filter 配对函数）",
        "trigger": "func name contains 'map|transform|apply' AND processes sequences",
        "code_stub": "assert len({func}(xs)) == len(xs), '维度保持违反：输出长度 != 输入长度'",
    },
)


def metamorphic_enabled() -> bool:
    """N2 蜕变关系 oracle 开关（默认 false 保持历史样本驱动口径）。"""
    return os.getenv("METAMORPHIC_ENABLE", "false").lower() in ("true", "1", "on")


def suggest_metamorphic_relations(
    function_name: str,
    signature: str = "",
    docstring: str = "",
) -> list[dict[str, str]]:
    """N2：从函数名/签名/文档启发式匹配 MR 模板，返回候选清单。

    匹配口径（保守，纯字符串/正则启发式，零 LLM）：
    - 遍历 _MR_TEMPLATES，trigger 中的"func name contains"关键词
      在 function_name 中命中即纳入候选；
    - "func has 2+ args" 检查 signature 参数数；
    - 全部不命中时返回空列表（调用方按"无 MR 候选"处理，
      历史口径零变化）。

    Args:
        function_name: 被测函数名。
        signature: 参数签名（如 "a: int, b: int"）。
        docstring: 函数文档字符串（辅助匹配约束类 MR）。

    Returns:
        MR 候选清单：[{"name", "description", "code_stub"}, ...]
        （code_stub 中 {func} 已替换为 function_name，{inverse} /
        {ret_type} 保留占位符由 LLM 补全）。
    """
    _fn_lower = function_name.lower()
    _sig_params = [p for p in signature.split(",") if p.strip() and ":" in p]
    _text = f"{function_name} {docstring}".lower()

    _candidates: list[dict[str, str]] = []
    for tpl in _MR_TEMPLATES:
        _trigger = tpl["trigger"].lower()
        _matched = False
        if "func name contains" in _trigger:
            _kws = _trigger.split("'")[2].split("|") if "'" in _trigger else []
            _matched = any(kw and kw in _fn_lower for kw in _kws if kw)
        if not _matched and "func has" in _trigger:
            _min_args = int(_trigger.split("func has")[1].split(" args")[0]) if "func has" in _trigger else 0
            _matched = len(_sig_params) >= _min_args if _min_args > 0 else False
        if not _matched:
            continue
        _stub = tpl["code_stub"].replace("{func}", function_name)
        _candidates.append({"name": tpl["name"], "description": tpl["description"], "code_stub": _stub})
    return _candidates


def build_metamorphic_prompt_section(mr_list: list[dict[str, str]]) -> str:
    """N2：把 MR 候选清单渲染为 prompt 注入文本（供 Generator 消费）。

    开关关闭时调用方不应调用本函数（metamorphic_enabled() 守门）。
    """
    if not mr_list:
        return ""
    lines = [
        "【N2 蜕变关系要求】（METAMORPHIC_ENABLE=true，无 oracle 场景增强检出能力）",
        "当函数无文档字符串 / 无明确期望值（无规格）时，请针对以下蜕变关系",
        "补充 1–2 条属性断言（不依赖精确期望值，只验证输入变换后输出满足的已知关系）：",
    ]
    for i, mr in enumerate(mr_list, start=1):
        lines.append(f"  {i}. {mr['name']}：{mr['description']}")
        lines.append(f"     代码骨架（{mr['name']}）：")
        lines.extend(f"       {code_line}" for code_line in mr["code_stub"].split("\n"))
    lines.append("请把上述骨架中的 {inverse} / {ret_type} 占位符替换为实际函数名 / 类型，")
    lines.append("并补全 1–2 条可执行的 assert（hypothesis @given 或普通参数化均可）。")
    return "\n".join(lines)


def check_metamorphic_relation(
    relation_code: str,
    ref_impl: Any,
    test_input: Any,
    expected_property: str = "no_exception",
) -> dict[str, Any]:
    """N2：在 ref_impl 上执行单条 MR 检查（纯 Python，无 subprocess）。

    口径（保守）：
    - expected_property="no_exception"（默认）：ref_impl(test_input) 不抛
      异常即满足（最弱的 MR 检查，用于"无规格"场景的基本健全性）；
    - 其他值：调用方自行断言（本函数仅执行 ref_impl(test_input) 并
      返回实际值，由调用方比对 expected_property）。

    Args:
        relation_code: MR 断言代码（信息性字段，本函数不执行它，
            实际执行的是 ref_impl(test_input)；保留该参数供调用方
            记录哪条 MR 触发了检查）。
        ref_impl: 被测函数/方法 callable。
        test_input: 输入值（可多参 tuple，调用方自行解包）。
        expected_property: 期望性质标签（信息性，不影响执行逻辑）。

    Returns:
        {"relation": relation_code, "passed": bool, "error": str|None,
         "output": Any（实际返回值，截断至 200 字符 repr）}
    """
    _error: str | None = None
    _output: Any = None
    try:
        _output = ref_impl(*test_input) if isinstance(test_input, (tuple, list)) else ref_impl(test_input)
    except Exception as e:
        _error = f"{type(e).__name__}: {str(e)[:150]}"
    _passed = _error is None
    return {
        "relation": relation_code,
        "passed": _passed,
        "error": _error,
        "output": repr(_output)[:200] if _output is not None else None,
    }
