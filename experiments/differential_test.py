"""
N4（2026-09-29 审查 P2）：差分测试（differential testing）原语。

历史口径：无规格场景（函数无文档、无类型注解、无明确期望值）下，
LLM 生成的测试要么退化为恒真断言（O4 已识别），要么依赖人工提供
"参考实现"。差分测试（Differential Testing）思想：用两个独立实现
（ref_impl 与 alt_impl）交叉比对输出——两者一致 = 通过，不一致 =
发现缺陷（无需任何 oracle / 期望值）。

本模块提供纯数据原语（零 LLM / 默认关，`DIFFERENTIAL_TEST_ENABLE`
开关）：

- `differential_enabled()` — 开关判定（默认 false 保持历史口径）。
- `run_differential_check(ref_impl, alt_impl, inputs, ...)` — 对一组
  输入在两个实现上分别执行，逐条比对输出，返回
  {"agreement_rate", "mismatches": [...], "errors": [...]}。
  输入可以是随机生成的（调用方经 hypothesis @given 或固定样本集）。
- `build_differential_prompt_section(function_name, ref_source, alt_source)` —
  生成注入 Generator prompt 的差分测试指令（"请生成 N 个随机输入，
  在 ref_impl 与 alt_impl 上分别执行并比对输出"）。
- `compare_outputs(ref_out, alt_out, tolerance)` — 单条输出比对
  （数值容差 tolerance 用于 float 比较，默认相对 1e-9）。

验收指标（N4）：无规格场景下差分检出的缺陷数 ≥ 样本驱动断言
（同一输入集）检出数（实验层对照：DIFFERENTIAL_TEST_ENABLE on/off
的 detection_rate 差异）。

用法（调用方示例）：
    from experiments.differential_test import (
        differential_enabled,
        run_differential_check,
    )

    if differential_enabled():
        # ref_impl = 已知正确实现（如标准库函数 / 上一版本）
        # alt_impl = 被测实现（LLM 修复后的版本）
        result = run_differential_check(
            ref_impl=math.floor,
            alt_impl=custom_floor,
            inputs=[(3.7,), (-3.7,), (0.0,), (float('nan'),)],
        )
        assert result["agreement_rate"] == 1.0  # 全一致 = 通过
"""

from __future__ import annotations

import math
import os
from typing import Any

__all__ = [
    "build_differential_prompt_section",
    "compare_outputs",
    "differential_enabled",
    "run_differential_check",
]


def differential_enabled() -> bool:
    """N4 差分测试开关（默认 false 保持历史口径零变化）。"""
    return os.getenv("DIFFERENTIAL_TEST_ENABLE", "false").lower() in ("true", "1", "on")


def compare_outputs(
    ref_out: Any,
    alt_out: Any,
    relative_tolerance: float = 1e-9,
) -> bool:
    """N4：单条输出比对（float 用相对容差，其余用 ==）。

    - 两个都是 float/int（非 NaN）：`math.isclose` 相对容差；
    - 两个都是 NaN：视为一致（NaN == NaN 在 Python 中为 False，
      但语义上"两者都未定义"视为一致）；
    - 其他类型：`==` 全等（list/dict/tuple 递归 ==，Python 原生）。

    Args:
        ref_out: 参考实现输出。
        alt_out: 被测实现输出。
        relative_tolerance: 浮点相对容差（默认 1e-9，双精度安全口径）。

    Returns:
        True = 两输出一致（或浮点容差内）；False = 不一致。
    """
    # 特殊 float 值（NaN / inf）
    if isinstance(ref_out, float) and isinstance(alt_out, float):
        if math.isnan(ref_out) and math.isnan(alt_out):
            return True  # 双 NaN 视为一致（语义"都未定义"）
        if math.isinf(ref_out) and math.isinf(alt_out):
            return ref_out == alt_out  # +inf vs -inf 区分
        return math.isclose(ref_out, alt_out, rel_tol=relative_tolerance, abs_tol=0.0)
    return ref_out == alt_out


def run_differential_check(
    ref_impl: Any,
    alt_impl: Any,
    inputs: list[tuple[Any, ...]] | list[Any],
    relative_tolerance: float = 1e-9,
) -> dict[str, Any]:
    """N4：对一组输入在 ref_impl 与 alt_impl 上分别执行，逐条比对输出。

    Args:
        ref_impl: 参考实现 callable（已知正确 / 上一版本 / 标准库函数）。
        alt_impl: 被测实现 callable（LLM 修复后版本）。
        inputs: 输入列表；每项为元组（多参数）或裸值（单参数），
            调用方自行统一口径（本模块不自动解包）。
        relative_tolerance: 浮点相对容差（传给 compare_outputs）。

    Returns:
        结果 dict：
        - "agreement_rate": float（一致条目 / 总条目，含错误条目计不一致）
        - "mismatches": [{"index", "input", "ref_out", "alt_out"}, ...]
          （输出不一致的条目，最多 20 条避免膨胀）
        - "errors": [{"index", "input", "impl", "error"}, ...]
          （任一实现抛异常的条目，计入不一致）
        - "total": int（输入总数）
        - "passed": bool（agreement_rate == 1.0 且无 errors）
    """
    _mismatches: list[dict[str, Any]] = []
    _errors: list[dict[str, Any]] = []
    _agree_count = 0
    total = len(inputs)

    for i, inp in enumerate(inputs):
        _args: tuple[Any, ...] = inp if isinstance(inp, tuple) else (inp,)

        # 参考实现
        _ref_out: Any
        _ref_err: str | None = None
        try:
            _ref_out = ref_impl(*_args)
        except Exception as e:
            _ref_out = None
            _ref_err = f"{type(e).__name__}: {str(e)[:120]}"
            _errors.append({"index": i, "input": _args, "impl": "ref", "error": _ref_err})

        # 被测实现
        _alt_out: Any
        _alt_err: str | None = None
        try:
            _alt_out = alt_impl(*_args)
        except Exception as e:
            _alt_out = None
            _alt_err = f"{type(e).__name__}: {str(e)[:120]}"
            _errors.append({"index": i, "input": _args, "impl": "alt", "error": _alt_err})

        if _ref_err is None and _alt_err is None:
            _agree = compare_outputs(_ref_out, _alt_out, relative_tolerance)
            if _agree:
                _agree_count += 1
            else:
                _mismatches.append(
                    {
                        "index": i,
                        "input": _args,
                        "ref_out": repr(_ref_out)[:120],
                        "alt_out": repr(_alt_out)[:120],
                    }
                )

    _rate = (_agree_count / total) if total > 0 else 0.0
    return {
        "agreement_rate": round(_rate, 4),
        "mismatches": _mismatches[:20],
        "errors": _errors[:20],
        "total": total,
        "passed": _rate == 1.0 and not _errors,
    }


def build_differential_prompt_section(
    function_name: str,
    ref_description: str = "standard library / previous version",
    num_random_inputs: int = 5,
) -> str:
    """N4：生成差分测试指令片段（注入 Generator prompt，METAMORPHIC 同口径）。

    Args:
        function_name: 被测函数名。
        ref_description: 参考实现描述（如 "math.floor" / "v2 实现"）。
        num_random_inputs: 要求生成的随机输入数量（默认 5）。

    Returns:
        prompt 注入文本（开关关闭时调用方不应调用本函数）。
    """
    return "\n".join(
        [
            "【N4 差分测试要求】（DIFFERENTIAL_TEST_ENABLE=true，无 oracle 场景）",
            f"针对函数 `{function_name}`，请额外生成 {num_random_inputs} 条随机输入"
            "（覆盖正常值 / 边界 / 异常值），并在以下两个实现上分别执行：",
            f"  - 参考实现：{ref_description}",
            f"  - 被测实现：{function_name}",
            "对每条输入比对两者输出（数值型用 math.isclose 容差 1e-9；"
            "其他类型用 ==），断言全部一致（assert ref_out == alt_out）。"
            "若某条输入两者不一致，说明被测实现存在缺陷，记录该输入并输出"
            "诊断（而非直接断言失败）——差分测试的价值在于**发现缺陷**而非通过。",
        ]
    )
