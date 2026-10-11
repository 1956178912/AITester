"""T-B 临时分析脚本（只读复算，无 LLM）：交叉核对 Lead 的 4 条复算。
逐条打印原始字段计数，不做任何推断性填充。
"""

import glob
import json
import os
from collections import Counter

FILES = sorted(glob.glob("experiments/results/main_batch/benchmark_synthetic_2026100[67]_*.json"))
print("== 文件集（glob 2026100[67]_*）==")
for f in FILES:
    print("  ", os.path.basename(f))
print("文件数 =", len(FILES))

agg = {}
for f in FILES:
    d = json.load(open(f))
    for arm, rd in (d.get("results") or {}).items():
        rows = rd.get("details") or []
        a = agg.setdefault(arm, {"rows": 0, "det_num": 0, "det_pos": 0, "det_none": 0,
                                 "gate": Counter(), "redviol": Counter(), "status": Counter(),
                                 "oracle_type": Counter(), "iter0_nopatch": 0,
                                 "aggreen_iter0_nopatch": 0, "rtg_det1": 0, "rtg_det0": 0})
        for r in rows:
            a["rows"] += 1
            det = r.get("detection_rate")
            if det is None:
                a["det_none"] += 1
            else:
                a["det_num"] += 1
                if det == 1.0:
                    a["det_pos"] += 1
            a["gate"][repr(r.get("specificity_gate_verdict"))] += 1
            a["redviol"][repr(r.get("red_regression_violation"))] += 1
            st = str(r.get("detection_first_status"))
            a["status"][st] += 1
            a["oracle_type"][repr(r.get("oracle_type"))] += 1
            it = r.get("iterations")
            patch = (r.get("patch") or "").strip()
            if it == 0 and not patch:
                a["iter0_nopatch"] += 1
                if st == "all_green_unverified":
                    a["aggreen_iter0_nopatch"] += 1
            if st == "red_then_green":
                if det == 1.0:
                    a["rtg_det1"] += 1
                elif det == 0.0:
                    a["rtg_det0"] += 1

print("\n== 按臂汇总（7 批合计）==")
for arm, a in sorted(agg.items()):
    print(f"[{arm}] rows={a['rows']} det_num={a['det_num']} det_pos={a['det_pos']} "
          f"det_none={a['det_none']} ({a['det_pos']}/{a['det_num']}"
          f"={100.0*a['det_pos']/a['det_num'] if a['det_num'] else 0:.1f}%)")
    print(f"    gate={dict(a['gate'])}")
    print(f"    red_regression_violation={dict(a['redviol'])}")
    print(f"    detection_first_status={dict(a['status'])}")
    print(f"    oracle_type={dict(a['oracle_type'])}")
    print(f"    iterations==0 且 patch 为空: {a['iter0_nopatch']}；其中 all_green_unverified="
          f"{a['aggreen_iter0_nopatch']}")
    print(f"    red_then_green: det=1 -> {a['rtg_det1']}, det=0 -> {a['rtg_det0']}")

print("\n== 逐文件：gate verdict 非 None 的文件 ==")
for f in FILES:
    d = json.load(open(f))
    for arm, rd in (d.get("results") or {}).items():
        c = Counter(str(r.get("specificity_gate_verdict")) for r in (rd.get("details") or []))
        if any(k != "None" for k in c):
            print(f"  {os.path.basename(f)} [{arm}] {dict(c)}")

print("\n== 逐文件：aitester detection 分子/分母 ==")
for f in FILES:
    d = json.load(open(f))
    rd = (d.get("results") or {}).get("aitester") or {}
    rows = rd.get("details") or []
    nn = [r.get("detection_rate") for r in rows if r.get("detection_rate") is not None]
    print(f"  {os.path.basename(f)} profile={(d.get('provenance') or {}).get('profile')} "
          f"rows={len(rows)} det_pos={sum(1 for x in nn if x == 1.0)}/{len(nn)}")

print("\n== 样本行（第一个非 None gate verdict）==")
found = False
for f in FILES:
    d = json.load(open(f))
    for arm, rd in (d.get("results") or {}).items():
        for r in (rd.get("details") or []):
            if r.get("specificity_gate_verdict") is not None and not found:
                found = True
                print("  file=", os.path.basename(f), "arm=", arm, "task=", r.get("task_id"))
                for k in ("specificity_gate_verdict", "detection_rate", "detection_first_status",
                          "iterations", "test_passed", "regeneration_count", "stop_reason"):
                    print("   ", k, "=", repr(r.get(k)))
