"""BN 轮（2026-10-22）只读复算：status 通道在**落盘边界**的出现面普查。

问题形状：BH→BM 把"读不懂 / 没测成"写进了 `src/graph/state.py` 的 status 通道，
`experiments/run_benchmark.py::_dump_state_artifacts` 却按**白名单**落盘单任务环节级工件。
不在白名单里的键由 LangGraph 直接丢弃 ⇒ 归档工件事后无法区分"检查完成且零疑点"与
"检查崩了 / 没跑"。本脚本只读，不写任何文件。

用法：.venv/bin/python scripts/tools/bn_archive_status_census.py
"""

import collections
import glob
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments" / "results"

#: 落盘边界的候选通道（status / 逐腿 outcomes / 已落盘的父字典）
KEYS: tuple[str, ...] = (
    "static_check_status",
    "static_check_outcomes",
    "safety_check_status",
    "safety_check_outcomes",
    "contract_status",
    "oracle_check_status",
    "oracle_check_outcomes",
    "check_status",
    "edit_intent_status",
    "deterministic_repair_status",
    "detection_first_status",
    "validation_status",
    "degraded_layers",
    # 已在白名单内的对照（用于证明"本普查不是全体缺失"）
    "testless_validation",
    "repo_verification",
    "position_aware_focus",
    "m10_leaf_fallback",
    "deterministic_guard_report",
)

#: 四值词汇里代表"完成且可信"的取值
_OK = "ok"


def value_class(has_key: bool, val: object) -> str:
    """按键存在性与取值分档；**缺键 / null / 空 / 有值不得两合一**（廉洁分册 §57 ⑦）。"""
    if not has_key:
        return "absent"
    if val is None:
        return "null"
    if isinstance(val, (list, dict, str)) and not val:
        return "empty"
    if isinstance(val, str):
        return "ok" if val == _OK else "non_ok"
    return "structured"


def walk(container: object, key: str) -> list[object]:
    """在任意嵌套 JSON 结构里收集 `key` 的出现（返回 (存在性, 值) 已由调用方处理）。"""
    found: list[tuple[bool, object]] = []
    if isinstance(container, dict):
        for k, v in container.items():
            if k == key:
                found.append((True, v))
            found.extend(walk(v, key))
    elif isinstance(container, list):
        for item in container:
            found.extend(walk(item, key))
    return found


def main() -> None:
    json_files = sorted(glob.glob(f"{RESULTS}/**/*.json", recursive=True))
    jsonl_files = sorted(glob.glob(f"{RESULTS}/**/*.jsonl", recursive=True))
    kinds = collections.Counter()
    for path in json_files:
        p = pathlib.Path(path)
        kinds["raw_state" if "/raw/" in str(p) else "summary_or_other"] += 1
    print(
        f"JSON 工件 {len(json_files)}（raw 环节级 {kinds['raw_state']} / 其余 {kinds['summary_or_other']}）"
        f" | JSONL 轨迹 {len(jsonl_files)}"
    )

    unparsable = collections.Counter()
    stats: dict[str, collections.Counter] = {k: collections.Counter() for k in KEYS}
    files_with_key: dict[str, set[str]] = {k: set() for k in KEYS}
    files_with_key_nonnull: dict[str, set[str]] = {k: set() for k in KEYS}

    def census(path: str, container: object) -> None:
        for key in KEYS:
            hits = walk(container, key)
            if not hits:
                continue
            files_with_key[key].add(path)
            for _, val in hits:
                stats[key]["hits"] += 1
                cls = value_class(True, val)
                stats[key][cls] += 1
                if cls not in ("null", "absent"):
                    files_with_key_nonnull[key].add(path)

    for path in json_files:
        try:
            raw = pathlib.Path(path).read_bytes()
        except OSError:
            unparsable["read_error"] += 1
            continue
        if not any(k.encode() in raw for k in KEYS):
            continue
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            unparsable["json_error"] += 1
            continue
        census(path, doc)

    trace_rows = 0
    for path in jsonl_files:
        try:
            text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            unparsable["read_error"] += 1
            continue
        for line in text.splitlines():
            if not line.strip() or not any(k in line for k in KEYS):
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                unparsable["jsonl_line_error"] += 1
                continue
            trace_rows += 1
            census(path, rec)
    print(f"轨迹里带候选键的行：{trace_rows} | 不可解析：{dict(unparsable) or '无'}")

    print("\n== 逐键出现面（归档全量） ==")
    print(f"  {'key':<30} {'hits':>6} {'文件':>6} {'非 null 文件':>11}  取值分档")
    for key in KEYS:
        st = stats[key]
        dist = {k: v for k, v in st.items() if k != "hits"}
        mark = "" if st["hits"] else "  ← 归档 0 次出现"
        print(
            f"  {key:<30} {st['hits']:>6} {len(files_with_key[key]):>6} "
            f"{len(files_with_key_nonnull[key]):>11}  {dist or '{}'}{mark}"
        )

    print("\n== 落盘白名单（_dump_state_artifacts 实际持久化的顶层键） ==")
    try:
        src = (ROOT / "experiments" / "run_benchmark.py").read_text(encoding="utf-8")
    except OSError:
        src = ""
    start = src.find("def _dump_state_artifacts")
    end = src.find("\ndef ", start + 1)
    block = src[start:end] if start >= 0 and end > start else ""
    persisted = sorted(set(re.findall(r'"([a-z0-9_]+)":\s*final_state\.get', block)))
    print(f"  白名单键 {len(persisted)} 个：{persisted}")
    status_in_whitelist = [k for k in KEYS if k in persisted]
    missing = [
        k
        for k in KEYS
        if k not in persisted
        and k
        not in (
            "testless_validation",
            "repo_verification",
            "position_aware_focus",
            "m10_leaf_fallback",
            "deterministic_guard_report",
        )
    ]
    print(f"  候选通道已在白名单内：{status_in_whitelist or '无'}")
    print(f"  候选通道不在白名单内（落盘即丢）：{missing}")


if __name__ == "__main__":
    main()
