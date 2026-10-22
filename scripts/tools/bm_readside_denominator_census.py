"""BM 轮（2026-10-22）只读复算：批次摘要口径的 R4/N1 两套分母与 P2P 材料对角线。

口径（与手册 §3.2—3.4 一致）：批次摘要 = 只算 `results.<bl>.details` 行；只读，不写文件。
用法：.venv/bin/python scripts/tools/bm_readside_denominator_census.py
"""

import collections
import glob
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
PATTERN = f"{ROOT / 'experiments' / 'results'}/**/*.json"
KEYS = ("regression_rate", "test_error_rate")

files = sorted(glob.glob(PATTERN, recursive=True))
per_bl: dict = collections.defaultdict(collections.Counter)
agg: collections.Counter = collections.Counter()
cross: collections.Counter = collections.Counter()
scanned = 0
used = 0
unreadable = 0
for path in files:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        unreadable += 1
        continue
    if b'"details"' not in raw:
        continue
    scanned += 1
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        unreadable += 1
        continue
    res = doc.get("results") if isinstance(doc, dict) else None
    if not isinstance(res, dict):
        continue
    for bl, rd in res.items():
        det = rd.get("details") if isinstance(rd, dict) else None
        if not isinstance(det, list) or not det:
            continue
        used += 1
        st = per_bl[bl]
        st["files"] += 1
        st["n"] += len(det)
        for key in KEYS:
            present = [r for r in det if isinstance(r, dict) and key in r]
            meas = [r for r in present if r.get(key) is not None]
            st[f"{key}_absent"] += len(det) - len(present)
            st[f"{key}_none"] += len(present) - len(meas)
            st[f"{key}_meas"] += len(meas)
            st[f"{key}_ones"] += sum(1 for r in meas if r.get(key) == 1.0)
            for r in present:
                agg[f"{key}:{r.get(key)!r}"] += 1
        for r in det:
            if not isinstance(r, dict) or "task_metadata" not in r:
                continue
            md = r["task_metadata"]
            md = md if isinstance(md, dict) else {}
            if "pass_to_pass" not in md:
                state = "absent"
            elif isinstance(md["pass_to_pass"], (list, str, dict)) and md["pass_to_pass"]:
                state = "nonempty"
            else:
                state = "empty"
            cross[f"p2p:{state}"] += 1
            cross[f"p2p:{state}|regression_rate={r.get('regression_rate', '<absent>')!r}"] += 1

print(
    f"json 文件: {len(files)} | 含 details 字节: {scanned} | 命中 results/details 批次组合: {used} | 不可解析: {unreadable}"
)
print("\n== 全局取值域（非空） ==")
for k in sorted(agg):
    if agg[k] and not k.endswith(":[]"):
        print(f"  {k} = {agg[k]}")


def pct(ones: int, denom: int) -> str:
    return f"{round(ones / denom * 100, 1)}%" if denom else "非可测"


print("\n== 按基线：现口径(/n) vs 可测口径(/k) ==")
print(
    f"  {'baseline':<28} {'n':>6} {'regr k':>7} {'regr 1.0':>8} {'现值%':>7} {'可测%':>7} {'te k':>6} {'te 1.0':>7} {'现值%':>7} {'可测%':>7}"
)
for bl in sorted(per_bl):
    s = per_bl[bl]
    n = s["n"]
    print(
        f"  {bl:<28} {n:>6} {s['regression_rate_meas']:>7} {s['regression_rate_ones']:>8} "
        f"{pct(s['regression_rate_ones'], n):>7} {pct(s['regression_rate_ones'], s['regression_rate_meas']):>7} "
        f"{s['test_error_rate_meas']:>6} {s['test_error_rate_ones']:>7} "
        f"{pct(s['test_error_rate_ones'], n):>7} {pct(s['test_error_rate_ones'], s['test_error_rate_meas']):>7}"
    )

tot = collections.Counter()
for s in per_bl.values():
    tot.update(s)
print("\n== 合计 ==")
print("  行 n =", tot["n"])
for key in KEYS:
    a, m, k, o = tot[f"{key}_absent"], tot[f"{key}_none"], tot[f"{key}_meas"], tot[f"{key}_ones"]
    print(
        f"  {key}: 缺键 {a} + None {m} + 可测 {k} = {a + m + k} | 其中 1.0 计数 {o} | 现口径 {pct(o, tot['n'])} vs 可测口径 {pct(o, k)}"
    )

print("\n== P2P 材料 × regression_rate 键写入（对角线证据） ==")
print("  带 task_metadata 的行:", sum(v for k, v in cross.items() if "|" not in k))
for k in sorted(x for x in cross if "|" in x):
    print(f"  {k} = {cross[k]}")
