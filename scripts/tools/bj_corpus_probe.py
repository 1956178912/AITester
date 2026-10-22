#!/usr/bin/env python3
"""BJ 轮语料探针（只读）：AST 断言一致性检查的"读不懂"腿在归档里的真实占比。

手册 `docs/reviews/ORACLE_VALIDATOR_MEASURABILITY_BJ_2026-10-22.md` §3 的读数由
本脚本产出，可重跑核对（零 LLM、零写入、零网络）。

口径：
- 语料 = `experiments/results/**/*.json`（能解析的才计入 parsed，失败按异常类型点名）；
- 站点 = 任一 dict 里的 `generated_test` 字符串值（递归全树，含嵌套 task 记录）；
- 判定面 = 现版 `check_assertions` 写入 sink 的逐腿 `{status, reason}`；
- `ORACLE_VALIDATE_ENABLE` 命中 = 归档 JSON 里任一层出现该键且折叠为真
  （`"false"` 字符串按假处理，不吃 Python 的 truthy 口径）。
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.tools.oracle_validator import check_assertions
from src.utils.check_status import parses_as_module

RESULTS = Path(__file__).resolve().parents[2] / "experiments" / "results"
_ENV_FLAG = "ORACLE_VALIDATE_ENABLE"
_LOAD_ERRORS = (OSError, ValueError, RecursionError, UnicodeDecodeError)


def _load_json(path: Path, errors: Counter[str]) -> Any:
    """读一个归档；失败时按异常类型计数并返回 None（不静默吞掉样本面）。"""
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except _LOAD_ERRORS as exc:
        errors[type(exc).__name__] += 1
        return None


def _iter_key(node: Any, key: str):
    """递归产出全树中 `key` 对应的字符串值（用于 target_code 共位性核查）。"""
    if isinstance(node, dict):
        value = node.get(key)
        if isinstance(value, str):
            yield value
        for sub in node.values():
            yield from _iter_key(sub, key)
    elif isinstance(node, list):
        for sub in node:
            yield from _iter_key(sub, key)


def _nearest_target(node: dict[str, Any], ancestors: list[dict[str, Any]]) -> str | None:
    """自内向外找最近的 `target_code` 字符串（生产消费点恒传 state["target_code"]）。"""
    for holder in reversed([*ancestors, node]):
        candidate = holder.get("target_code")
        if isinstance(candidate, str):
            return candidate
    return None


def _walk_pairs(node: Any, ancestors: list[dict[str, Any]]):
    """递归产出 (generated_test, 最近的 target_code) 配对。"""
    if isinstance(node, dict):
        generated = node.get("generated_test")
        if isinstance(generated, str):
            yield generated, _nearest_target(node, ancestors)
        for sub in node.values():
            yield from _walk_pairs(sub, [*ancestors, node])
    elif isinstance(node, list):
        for sub in node:
            yield from _walk_pairs(sub, ancestors)


def _truthy(value: Any) -> bool:
    """把归档里的开关值折成真假（`"false"` 字符串是**假**，不是 Python 的 truthy）。"""
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _flag_enabled(node: Any) -> bool:
    if isinstance(node, dict):
        if _ENV_FLAG in node and _truthy(node[_ENV_FLAG]):
            return True
        return any(_flag_enabled(sub) for sub in node.values())
    if isinstance(node, list):
        return any(_flag_enabled(sub) for sub in node)
    return False


def main() -> int:
    files = 0
    parsed = 0
    enabled_files = 0
    sites = 0
    enabled_sites = 0
    findings_sites = 0
    enabled_blind = 0
    target_strings = 0
    target_unparsable = 0
    leg: Counter[str] = Counter()
    target_leg: Counter[str] = Counter()
    load_errors: Counter[str] = Counter()
    enabled_blind_paths: list[str] = []

    for path in sorted(RESULTS.rglob("*.json")):
        files += 1
        data = _load_json(path, load_errors)
        if data is None:
            continue
        parsed += 1
        file_enabled = _flag_enabled(data)
        if file_enabled:
            enabled_files += 1
        for target in _iter_key(data, "target_code"):
            target_strings += 1
            if target.strip() and not parses_as_module(target):
                target_unparsable += 1
        for generated, target in _walk_pairs(data, []):
            sink: list[dict[str, Any]] = []
            findings = check_assertions(generated, target, outcome_sink=sink)
            sites += 1
            if file_enabled:
                enabled_sites += 1
            head = sink[0]
            leg[f"{head['status']}:{head['reason']}"] += 1
            if len(sink) > 1:
                tail = sink[1]
                target_leg[f"{tail['status']}:{tail['reason']}"] += 1
            if findings:
                findings_sites += 1
            if file_enabled and head["status"] != "ok":
                enabled_blind += 1
                if len(enabled_blind_paths) < 5:
                    enabled_blind_paths.append(f"{path} {head['status']}:{head['reason']}")

    print(f"json_files={files} parsed={parsed} 读取失败={files - parsed}（{dict(load_errors)}）")
    print(f"{_ENV_FLAG}=true 归档={enabled_files}（其 generated_test 站点={enabled_sites}）")
    print(f"generated_test 站点合计={sites}")
    print("assertion_consistency 腿分布：")
    for key, count in leg.most_common():
        print(f"  {key} = {count}")
    print(f"有疑点站点（findings 非空）={findings_sites}")
    print(f"开关开启归档中的不可测量站点（本轮 O4 盲区）={enabled_blind}")
    for item in enabled_blind_paths:
        print(f"  盲区样本：{item}")
    if enabled_blind > len(enabled_blind_paths):
        print(f"  （样本仅列前 {len(enabled_blind_paths)} 个，其余未点名）")
    print(f"归档内 target_code 字符串={target_strings}（其中读不懂={target_unparsable}）")
    print("target_type_inference 腿分布（generated_test 站点向上找最近 target_code）：")
    for key, count in target_leg.most_common():
        print(f"  {key} = {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
