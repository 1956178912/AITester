"""BM 轮（2026-10-22）只读复算：归档 contamination_risk_level 行级普查 × patch 字段形状。

口径（与手册 §3.2 一致）：行级 = 递归展开所有含该键的 dict；只读，不写任何文件。
用法：.venv/bin/python scripts/tools/bm_archive_level_patch_census.py
"""

import collections
import json
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments" / "results"


def rows(node: object, out: list) -> None:
    if isinstance(node, dict):
        if "contamination_risk_level" in node:
            out.append(node)
        for v in node.values():
            rows(v, out)
    elif isinstance(node, list):
        for v in node:
            rows(v, out)


all_rows = []
parsed = 0
bad = 0
for dirpath, _dirnames, filenames in os.walk(RESULTS):
    if "__pycache__" in dirpath:
        continue
    for name in sorted(filenames):
        if not name.endswith(".json"):
            continue
        path = os.path.join(dirpath, name)
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except Exception:
            bad += 1
            continue
        parsed += 1
        out: list = []
        rows(doc, out)
        src = path.split("results/")[1].split("/")[0]
        for r in out:
            r["_src"] = src
            all_rows.append(r)

print("可解析 json 文件:", parsed, "| 解析失败:", bad, "| 含该键的行:", len(all_rows))

xtab = collections.Counter()
lvl = collections.Counter()
for r in all_rows:
    key = str(r.get("contamination_risk_level"))
    lvl[key] += 1
    pt = r.get("patch")
    if pt is None:
        shape = "<absent>" if "patch" not in r else "null"
    elif isinstance(pt, str):
        shape = "empty" if not pt.strip() else "non_empty"
    else:
        shape = "non_string:" + type(pt).__name__
    xtab[(key, shape)] += 1

print("\n== 档位分布 ==")
for k in sorted(lvl):
    print(f"  {k} = {lvl[k]}")
print("\n== 档位 × patch 形状 ==")
for (name, shape), n in sorted(xtab.items(), key=lambda x: (-x[1], x[0])):
    print(f"  {name:<16} patch={shape:<12} {n}")
low_all = lvl["low"]
low_empty = xtab[("low", "empty")]
print(f"\n  干净组（low）共 {low_all} 行，其中补丁为空 {low_empty} 行 = {low_empty / low_all:.2%}")
by_batch = collections.Counter(r["_src"] for r in all_rows if r.get("contamination_risk_level") == "low")
print("  low 行按批次目录 top:", by_batch.most_common(6))
