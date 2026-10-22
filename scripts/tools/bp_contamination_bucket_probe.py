"""BP 轮改前探针（只读，零 LLM，$0）：行级 `contamination_risk_level` 的缺席在两个消费者手里去向不同。

同一批 details 行、同一个"这一行没有污染级别"的事实，被两个消费者折成两种东西：
  · `analysis_parts/cross_analysis._contamination_cross_analysis` 用 `if not level: continue`
    ——缺席行**不进任何桶**，输出里也没有"被丢了几行"的面；
  · `statistical_analysis.contamination_view_summary` 用 `row.get(...) or "unknown"`
    ——缺席行**并进 unknown**，与"检测腿跑了但判不了"同计数。
于是 5.3 表的「未入对照任务」列与批次 IX 的 unknown 列对不上账，而渲染层脚注
（`analyze_results.py` 的 5.3 注）却按后一种口径解释前一种口径的数。

三面测量：
  A 取值形态普查：归档里 details 行的该字段按「键不存在 / 值为 null / 空串 /
    词表内 / 词表外」分档——先证明"缺席"到底有几种形状、真实语料里各有多少。
  B 两消费者对账：逐份逐臂同时跑两个函数，数 `n_details - Σ by_risk_level.tasks`
    （cross 侧静默丢弃的行数）与 `view.unknown - cross.unknown`（unknown 桶的口径差），
    并检查二者是否逐臂相等。
  C 渲染层对账：复算 5.3 表的 `excluded` 公式，检查 `high + low + excluded == n_details`
    在不成立时差多少；统计 `available=False`（整节沉默）里"确有行但全无字段"的臂数，
    以及 `available=True` 时 `high_vs_low_success_delta` 键缺席的分布（docstring 声明
    `float | None`，代码是"键不存在"）。

用法：.venv/bin/python scripts/tools/bp_contamination_bucket_probe.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.analysis_parts.cross_analysis import _contamination_cross_analysis  # noqa: E402
from experiments.statistical_analysis import contamination_view_summary  # noqa: E402

RESULTS = ROOT / "experiments" / "results"
VOCAB = ("high", "medium", "low", "unknown", "not_applicable")


def _shape(row: dict[str, Any]) -> str:
    """一行里 `contamination_risk_level` 的形态档（键级缺席与值级缺席分开）。"""
    if "contamination_risk_level" not in row:
        return "key_absent"
    value = row["contamination_risk_level"]
    if value is None:
        return "value_null"
    if value == "":
        return "value_blank"
    if value in VOCAB:
        return f"vocab:{value}"
    return f"off_vocab:{value!r}"


def _iter_arms(payload: Any):
    """归档批次 JSON → (臂名, details 列表)。details 非 list 的臂跳过（不当成空集）。"""
    if not isinstance(payload, dict):
        return
    results = payload.get("results")
    if not isinstance(results, dict):
        return
    for arm, block in results.items():
        if isinstance(block, dict) and isinstance(block.get("details"), list):
            yield str(arm), block["details"]


def probe_a_shapes() -> list[tuple[Path, str, list[dict[str, Any]]]]:
    print("== A 取值形态普查 ==")
    shapes: Counter[str] = Counter()
    corpus: list[tuple[Path, str, list[dict[str, Any]]]] = []
    scanned = 0
    for path in sorted(RESULTS.rglob("benchmark_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        arms = list(_iter_arms(payload))
        if not arms:
            continue
        touched = False
        for arm, details in arms:
            rows = 0
            for row in details:
                if not isinstance(row, dict):
                    shapes["row_unusable"] += 1
                    continue
                shapes[_shape(row)] += 1
                if "contamination_risk_level" in row:
                    touched = True
                rows += 1
            if rows:
                corpus.append((path, arm, details))
        scanned += 1 if touched else 0
    print(f"含该键的批次文件数 = {scanned}；参与对账的 (文件, 臂) 数 = {len(corpus)}")
    for key, count in sorted(shapes.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {key:26s} {count}")
    absent = sum(count for key, count in shapes.items() if key in ("key_absent", "value_null", "value_blank"))
    print(f"  ⇒ 缺席合计（键不存在 + null + 空白）= {absent}")
    return corpus


def probe_b_two_consumers(corpus) -> None:
    print("\n== B 两消费者对账（同一批行，两种缺席去向） ==")
    arms_with_unbucketed = 0
    total_unbucketed = 0
    mismatch = 0
    invariant_ok = 0
    disclosed = 0
    examples: list[str] = []
    for path, arm, details in corpus:
        n = len(details)
        cross = _contamination_cross_analysis(details)
        by_level = cross.get("by_risk_level", {}) if cross.get("available") else {}
        counted = sum(int(block.get("tasks", 0)) for block in by_level.values())
        unbucketed = n - counted
        view = contamination_view_summary({arm: details})[arm]
        cross_unknown = int(by_level.get("unknown", {}).get("tasks", 0))
        gap = int(view["counts"].get("unknown", 0)) - cross_unknown
        if int(view.get("unknown_of_which_absent", 0) or 0) == unbucketed:
            disclosed += 1
        if gap == unbucketed:
            invariant_ok += 1
        else:
            mismatch += 1
        if unbucketed:
            arms_with_unbucketed += 1
            total_unbucketed += unbucketed
            if len(examples) < 6:
                examples.append(
                    f"  {path.name} [{arm}] n={n} cross 进桶 {counted} ⇒ 未进桶 {unbucketed} 行"
                    f"（cross.unobserved_total={cross.get('unobserved_total')}）；"
                    f"view.unknown {cross_unknown + gap} vs cross.unknown {cross_unknown}（差 {gap}）"
                )
    print(f"有未进桶行的 (文件, 臂) = {arms_with_unbucketed}；未进桶行数合计 = {total_unbucketed}")
    print(
        f"恒等式 view.unknown == cross.unknown + 未进桶数 成立的臂 = {invariant_ok} / {len(corpus)}（不成立 {mismatch}）"
    )
    print(f"view.unknown_of_which_absent == 未进桶数 成立的臂 = {disclosed} / {len(corpus)}")
    for line in examples:
        print(line)


def probe_c_renderer(corpus) -> None:
    print("\n== C 渲染层对账（5.3 表的合计是否等于行数） ==")
    unequal = 0
    diff_hist: Counter[str] = Counter()
    legacy_gap: Counter[str] = Counter()
    silent_sections = 0
    all_absent_sections = 0
    delta_absent = 0
    delta_none = 0
    delta_missing: Counter[str] = Counter()
    available_total = 0
    silent_examples: list[str] = []
    for path, arm, details in corpus:
        n = len(details)
        cross = _contamination_cross_analysis(details)
        if not cross.get("available"):
            silent_sections += 1
            if n and all("contamination_risk_level" not in row for row in details if isinstance(row, dict)):
                all_absent_sections += 1
                if len(silent_examples) < 5:
                    silent_examples.append(
                        f"  {path.name} [{arm}] n={n} 全部未记录 ⇒ reason={cross.get('reason')!r}"
                        f" / unobserved={cross.get('unobserved_total')}"
                    )
            continue
        available_total += 1
        if "high_vs_low_success_delta" not in cross:
            delta_absent += 1
        if cross.get("high_vs_low_success_delta") is None:
            delta_none += 1
            delta_missing[str(cross.get("delta_missing_buckets"))] += 1
        by_level = cross.get("by_risk_level", {})
        three_tiers = sum(int(b.get("tasks", 0)) for lv, b in by_level.items() if lv not in ("high", "low"))
        excluded = three_tiers + int(cross.get("unobserved_total", 0))
        shown = int(by_level.get("high", {}).get("tasks", 0)) + int(by_level.get("low", {}).get("tasks", 0)) + excluded
        legacy = (
            int(by_level.get("high", {}).get("tasks", 0)) + int(by_level.get("low", {}).get("tasks", 0)) + three_tiers
        )
        if shown != n:
            unequal += 1
            diff_hist[str(n - shown)] += 1
        if legacy != n:
            legacy_gap[str(n - legacy)] += 1
    print(
        f"available=True 的臂 = {available_total}；delta 键缺席（改前 docstring 声明 float | None 却缺键）= "
        f"{delta_absent}；delta 显式为 None 的臂 = {delta_none}，缺失桶分布 = {dict(delta_missing.most_common(6))}"
    )
    print(
        f"available=False 的臂 = {silent_sections}（改前整节从报告消失，改后由披露行点名）；"
        f"其中「确有行但全部行无该字段」= {all_absent_sections}"
    )
    print(f"表内合计 ≠ 行数的臂 = {unequal}；差额分布（行数 − 表内合计）= {dict(diff_hist.most_common(8))}")
    print(f"改前公式（三档合计）对不上行数的差额分布 = {dict(legacy_gap.most_common(8))}")
    for line in silent_examples:
        print(line)


def main() -> int:
    corpus = probe_a_shapes()
    probe_b_two_consumers(corpus)
    probe_c_renderer(corpus)
    return 0


if __name__ == "__main__":
    sys.exit(main())
