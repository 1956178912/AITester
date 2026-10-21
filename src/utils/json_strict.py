"""严格 JSON 序列化（RFC 8259）：拒绝 NaN / ±Infinity，失败时点名结构化路径。

背景（AF 轮，2026-10-20）：Python `json.dumps` 默认 `allow_nan=True`，会把
非有限浮点写成裸 `NaN` / `Infinity`——这不是 RFC 8259 合法 JSON。Python 自身的
`json.loads` 能读回，但 jq / Go / Rust serde / JavaScript `JSON.parse` 等严格
解析器会直接拒绝，形成"生产端静默写出、消费端读不动"的跨语言缺口。

`strict_json_dumps` 先递归定位非有限浮点（含 dict 键），抛
`NonFiniteJSONError` 并列出 JSON 路径；不含非有限值时只做一次 `json.dumps`
（`allow_nan=False` 作为第二道防线）。
"""

from __future__ import annotations

import json
import math
from typing import Any

_MAX_REPORTED = 5


class NonFiniteJSONError(ValueError):
    """对象含 NaN / ±Infinity 时拒绝序列化（带 JSON 路径的 fail-closed）。"""

    def __init__(self, pointers: list[str]) -> None:
        self.pointers = tuple(pointers)
        shown = "、".join(pointers[:_MAX_REPORTED])
        suffix = f" 等 {len(pointers)} 处" if len(pointers) > _MAX_REPORTED else ""
        super().__init__(f"非有限浮点数不是 RFC 8259 JSON 的合法值：{shown}{suffix}")


def _child_pointer(path: str, key: Any) -> str:
    if isinstance(key, str) and key.isidentifier():
        return f"{path}.{key}"
    return f"{path}[{key!r}]"


def nonfinite_pointers(obj: Any) -> list[str]:
    """返回对象中全部非有限浮点（含 dict 键）的 JSON 路径；无则空列表。"""
    pointers: list[str] = []
    seen: set[int] = set()

    def walk(value: Any, path: str) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            pointers.append(path)
            return
        if isinstance(value, dict):
            if id(value) in seen:
                return
            seen.add(id(value))
            for key, item in value.items():
                if isinstance(key, float) and not math.isfinite(key):
                    pointers.append(f"{path}[<key {key!r}>]")
                    continue
                walk(item, _child_pointer(path, key))
        elif isinstance(value, (list, tuple)):
            if id(value) in seen:
                return
            seen.add(id(value))
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(obj, "$")
    return pointers


def strict_json_dumps(
    obj: Any,
    *,
    indent: int | None = None,
    ensure_ascii: bool = False,
    sort_keys: bool = False,
    default: Any = None,
) -> str:
    """严格序列化：非有限浮点抛 `NonFiniteJSONError`，绝不写裸 NaN/Infinity。"""
    pointers = nonfinite_pointers(obj)
    if pointers:
        raise NonFiniteJSONError(pointers)
    return json.dumps(
        obj,
        ensure_ascii=ensure_ascii,
        indent=indent,
        sort_keys=sort_keys,
        default=default,
        allow_nan=False,
    )


__all__ = ["NonFiniteJSONError", "nonfinite_pointers", "strict_json_dumps"]
