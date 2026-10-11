import json, glob, os, sys, time
from collections import Counter
sys.path.insert(0,".")
from experiments.repair_replay import replay_row
def gen(name):
    if "20261006" in name: return "R-P0-2"
    if "20261007" in name: return "E1/E2"
    return "early"
tot=Counter(); per={}
t0=time.time()
for f in sorted(glob.glob("experiments/results/main_batch/benchmark_synthetic_*.json")):
    d=json.load(open(f)); g=gen(os.path.basename(f)); c=Counter()
    for r in d["results"]["aitester"]["details"]:
        v=replay_row(r, timeout=60)
        c[v["status"]]+=1; tot[v["status"]]+=1
    per[os.path.basename(f)]=(g,dict(c))
    print(f"{os.path.basename(f):44s} {g:8s} {dict(c)}", flush=True)
print("\n=== per-generation ===")
agg={}
for name,(g,c) in per.items():
    a=agg.setdefault(g,Counter())
    for k,v in c.items(): a[k]+=v
for g,a in agg.items():
    replayable=a["correct"]+a["wrong_patch"]
    print(f"{g:8s} patched={a['correct']+a['wrong_patch']+a['not_replayable_diff']} replayable={replayable} correct={a['correct']} rate={a['correct']/replayable if replayable else None:.4f} skipped_no_material={a['skipped_no_material']} diff={a['not_replayable_diff']} unverifiable={a['unverifiable']}")
print("\ntotal:",dict(tot),"elapsed %.1fs"%(time.time()-t0))
