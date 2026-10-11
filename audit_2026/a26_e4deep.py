import json
from collections import Counter
from math import comb
def load(f,arm="aitester"):
    d=json.load(open(f)); return {r["task_id"]:r for r in d["results"][arm]["details"]}
OLD=load("experiments/results/e6_a1_batches/e4_quixbugs_aitester/benchmark_quixbugs_20261009_215514.json")
FIX=load("experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json")
DF =load("experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/plain_llm_df.json","plain_llm_df")
def pair(A,B,na,nb):
    ks=[k for k in A if k in B]
    d2=[k for k in ks if A[k].get("detection_rate") is not None and B[k].get("detection_rate") is not None]
    a=sum(1 for k in d2 if A[k]["detection_rate"]>0); b=sum(1 for k in d2 if B[k]["detection_rate"]>0)
    n10=sum(1 for k in d2 if A[k]["detection_rate"]>0 and B[k]["detection_rate"]==0)
    n01=sum(1 for k in d2 if A[k]["detection_rate"]==0 and B[k]["detection_rate"]>0)
    chi=((abs(n10-n01)-1)**2/(n10+n01)) if n10+n01 else 0
    from scipy.stats import chi2 as c2
    print(f"{na} vs {nb}: common_nonnull={len(d2)} A={a} B={b} n10={n10} n01={n01} chi2_cc={chi:.3f} p_asym={c2.sf(chi,1):.6f}")
pair(OLD,FIX,"old(0/41)","fixed(17/37)")
pair(FIX,DF,"fixed_aitester(17/37)","fixed_df(31/37)")
# detection by final verdict (FIXED harness)
rows=list(FIX.values())
for v in ("specific_red","over_red","unavailable"):
    sub=[r for r in rows if r.get("specificity_gate_verdict")==v]
    nn=[r for r in sub if r.get("detection_rate") is not None]
    print(f"  verdict={v}: rows={len(sub)} det_nonnull={len(nn)} det_pos={sum(1 for r in nn if r['detection_rate']>0)}")
# None tasks
none_ids=[r["task_id"] for r in rows if r.get("detection_rate") is None]
print("  detection None tasks (fixed harness):", none_ids)
# diagnostic 12-task file
d=json.load(open("experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/diagnostic_12task_prerepair.json"))
for arm,r in d["results"].items():
    rr=r["details"]; print("  diagnostic rows:",len(rr),"keys:",sorted(rr[0]))
    print("   rc values:",Counter(str(x.get("rc") or x.get("pytest_rc")) for x in rr))
