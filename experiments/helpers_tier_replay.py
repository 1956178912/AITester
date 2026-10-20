#!/usr/bin/env python3
"""AB-1（AB 轮 2026-10-19）：真实 LLM 响应缓存离线重放——`helpers` 首对象修复档（档 2）到底还会不会返回（零 LLM，$0）。

背景：`src/utils/helpers.py:767-789` 的档 2 在 AA-5 被判为"返回分支恒不可达"，
但该结论建立在**合成残片枚举**（54,006 输入）上——ROUND4 审计 §4.2 因此明确写了
"这是下一轮值得单独处理的项，判据要用真实 LLM 响应语料，不是随机残片"。盘上恰好
有：产品自身的 LLM 响应缓存（默认 `~/.cache/aitester/llm`，可用
`AITESTER_LLM_CACHE_DIR` 覆盖）存的是**原始响应字符串**，可直接喂给
`extract_json_object` 复算，一次调用都不必发。

本脚本只做观测，不改任何被评估代码：包裹 `_first_balanced_object` 作为"走到档 2"
的入口探针，并对每个探针取到的片段离线复算档 2 的五个候选是否会解析成非空字典
（= 返回分支是否会触发）。另记一项**机制**口径：档 2 相对档 1 的唯一增量是"两个
扫描器分歧"，故单独统计分歧子集及其触发数——这比"总数 0"更能说明冗余而非运气。

**隐私纪律**：缓存含完整 prompt 与响应正文（可能夹带被测代码）。本脚本
**只输出聚合计数与文件名清单摘要**，绝不打印、写出或复制任何响应正文。
需要特别处理的是：被观测的 `helpers` 在叶子回退档会 `logger.warning` 打印
**片段前缀**（`helpers.py:835`/`847`），语料越大漏得越多——那不是本脚本在打印正文，
但它确实让"聚合输出"这句话变成假的。因此重放期给 `helpers` 的 logger 挂一个
**只计数不放行**的 filter，把正文型告警换算成 `n_suppressed_warnings` 计数：
信息一条不少（条数），正文一条不出。该性质由
`tests/test_helpers_tier_replay.py` 用植入哨兵串钉成回归锁。

用法::

    python experiments/helpers_tier_replay.py                 # 人类可读
    python experiments/helpers_tier_replay.py --json          # 机器可读
    python experiments/helpers_tier_replay.py --cache-dir DIR # 指向固化语料做测试
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils import helpers  # noqa: E402

# 被探针包裹的原函数引用（模块级只取一次）。`extract_json_object` 经模块全局解析
# `_first_balanced_object`，因此替换该全局即可拦截档 2 入口；原实现必须在此固化，
# 否则包裹后无法回调（`replay` 的 finally 依赖它还原）。
_ORIG_FIRST_BALANCED_OBJECT = helpers._first_balanced_object

# 输出字段固定序：新增键须同步改 `_COUNTER_KEYS` 与报告，避免"同一脚本两次跑出
# 不同字段集"这类口径漂移。
_COUNTER_KEYS: tuple[str, ...] = (
    "n_response_str",
    "n_planner_form",
    "n_multi_brace",
    "n_ok_dict",
    "n_raise",
    "n_leaf_fallback",
    "n_suppressed_warnings",
    "tier2_entered",
    "tier2_no_fragment",
    "tier2_fragment",
    "tier2_multi_call",
    "tier2_scanner_divergent",
    "tier2_would_return_any",
    "tier2_would_return_nonempty",
    "tier2_would_return_empty_only",
    "divergent_would_return_any",
)


def default_cache_dir() -> str:
    """复用产品的缓存目录解析（含 `AITESTER_LLM_CACHE_DIR` 覆盖），不另起一套路径逻辑。"""
    from src.agents.llm_client import _llm_cache_dir

    return _llm_cache_dir()


def _iter_responses(cache_dir: Path) -> list[tuple[str, str, str]]:
    """读缓存目录，返回 (文件名, system, response)；坏文件与缺 response 的条目跳过并计数。"""
    out: list[tuple[str, str, str]] = []
    for f in sorted(cache_dir.glob("*.json")):
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        resp = payload.get("response")
        if not isinstance(resp, str):
            continue
        system = payload.get("system")
        out.append((f.name, system if isinstance(system, str) else "", resp))
    return out


def _tier2_candidates(fragment: str) -> tuple[str, ...]:
    """档 2 的候选序：与 `helpers.py` 的档 2 候选元组逐字镜像。
    行号（约 793-798）仅供定位，权威绑定由 AST 锁负责。

    刻意**不复用局部别名**、也刻意保留 `_repair_json_text` 的重复计算：
    镜像的职责是"和源码一模一样"，不是"更高效"。二者的等值关系由
    `tests/test_helpers_tier_replay.py::TestMirrorStaysInSyncWithSource`
    按 AST 逐字钉住——源码一改候选序，本镜像测试先红。
    """
    return (
        fragment,
        helpers._repair_json_text(fragment),
        helpers._quote_python_expressions(fragment),
        helpers._quote_python_expressions(helpers._repair_json_text(fragment)),
        helpers._repair_json_bounded(fragment),
    )


def _first_parse(fragment: str) -> dict[str, Any] | None:
    """档 2 五个候选里首个可解析为 dict 的结果（含空字典，便于区分 `and _obj` 门）。"""
    for cand in _tier2_candidates(fragment):
        try:
            obj = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _tier1_base(cleaned: str) -> str | None:
    """档 1 在同一 `cleaned` 上取的片段基（`_find_balanced_json` + `.strip()`）。"""
    start = cleaned.find("{")
    if start == -1:
        return None
    base = helpers._find_balanced_json(cleaned, start)
    return None if base is None else base.strip()


class _WarningCounter(logging.Filter):
    """重放期只计数不放行 `helpers` 的正文型告警（见模块头"隐私纪律"）。"""

    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def filter(self, record: logging.LogRecord) -> bool:
        self.count += 1
        return False


def replay(cache_dir: Path, *, limit: int | None = None) -> dict[str, Any]:
    """把缓存里的每条原始响应喂给 `extract_json_object`，统计档 2 的真实触发情况。"""
    entries = _iter_responses(cache_dir)
    if limit is not None:
        entries = entries[:limit]
    counters: Counter[str] = Counter()
    probe = _Tier2Probe()
    warn_filter = _WarningCounter()
    original = helpers._first_balanced_object
    helpers.logger.addFilter(warn_filter)
    helpers._first_balanced_object = probe.__call__
    try:
        for _name, system, resp in entries:
            counters["n_response_str"] += 1
            if "logic_analysis" in system:
                counters["n_planner_form"] += 1
            if resp.count("{") >= 2:
                counters["n_multi_brace"] += 1
            probe.begin()
            try:
                counters["n_ok_dict"] += 1 if isinstance(helpers.extract_json_object(resp), dict) else 0
            except json.JSONDecodeError:
                counters["n_raise"] += 1
            if helpers.was_leaf_fallback_used():
                counters["n_leaf_fallback"] += 1
            probe.commit(counters)
    finally:
        helpers._first_balanced_object = original
        helpers.logger.removeFilter(warn_filter)
    counters["n_suppressed_warnings"] = warn_filter.count
    digest = hashlib.sha256("\n".join(n for n, _s, _r in entries).encode("utf-8")).hexdigest()
    return {
        "corpus_dir": str(cache_dir),
        "n_files": len(list(cache_dir.glob("*.json"))),
        "n_entries_used": len(entries),
        "corpus_sha256": digest,
        **{k: counters[k] for k in _COUNTER_KEYS},
    }


class _Tier2Probe:
    """档 2 入口探针：区分"走到档 2""取到片段""扫描器分歧""真的会返回"四层。

    这四层必须分开数：`extract_json_object` 只在档 2 入口调用一次
    `_first_balanced_object`（实测 `src/utils/helpers.py` 仅 791 一个调用点，
    `tier2_multi_call` 是这一假设的守卫），把它记成**一个**指标就会把
    "25 条走到档 2 但没取到片段"和"667 条取到片段"混成同一个数——
    正是本轮要消灭的那类静默合流。
    原片段只能在**调用时**记下：`commit` 里复算会把"探针包裹下的行为"与
    "原实现的行为"混成两个口径。
    """

    def __init__(self) -> None:
        self._calls: list[tuple[str, str | None]] = []

    def begin(self) -> None:
        self._calls = []

    def __call__(self, text: str) -> str | None:
        out = _ORIG_FIRST_BALANCED_OBJECT(text)
        self._calls.append((text, out))
        return out

    def commit(self, counters: Counter[str]) -> None:
        if not self._calls:
            return
        counters["tier2_entered"] += 1
        if len(self._calls) > 1:
            counters["tier2_multi_call"] += 1
        cleaned, fragment = self._calls[-1]
        if not fragment:
            counters["tier2_no_fragment"] += 1
            return
        counters["tier2_fragment"] += 1
        # 档 2 相对档 1 的唯一增量 = 两个扫描器在同一 cleaned 上取到不同片段
        base = _tier1_base(cleaned)
        divergent = base != fragment
        if divergent:
            counters["tier2_scanner_divergent"] += 1
        parsed = _first_parse(fragment)
        if parsed is not None:
            counters["tier2_would_return_any"] += 1
            if parsed:
                counters["tier2_would_return_nonempty"] += 1
            else:
                counters["tier2_would_return_empty_only"] += 1
            if divergent:
                counters["divergent_would_return_any"] += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="真实 LLM 响应缓存离线重放（档 2 触发判定，零 LLM）")
    parser.add_argument("--cache-dir", default=None, help="缓存目录（默认取产品解析的目录）")
    parser.add_argument("--limit", type=int, default=None, help="只重放前 N 条（调试用）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（仅聚合计数，无正文）")
    args = parser.parse_args(argv)

    cache_dir = Path(args.cache_dir) if args.cache_dir else Path(default_cache_dir())
    if not cache_dir.is_dir():
        print(f"[FAIL] 缓存目录不存在：{cache_dir}（fail-closed，不返回全零结果）", file=sys.stderr)
        return 2
    report = replay(cache_dir, limit=args.limit)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    print(f"语料目录 : {report['corpus_dir']}")
    print(f"文件数   : {report['n_files']}（实际使用 {report['n_entries_used']}）")
    print(f"语料摘要 : sha256(文件名清单) = {report['corpus_sha256'][:16]}…")
    for key in _COUNTER_KEYS:
        print(f"{key:32s} {report[key]}")
    print(
        "\n判读：`tier2_would_return_nonempty` = 档 2 返回分支在真实语料上的实际触发数；"
        "`divergent_would_return_any` 是它唯一可能的增量（扫描器分歧子集）。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
