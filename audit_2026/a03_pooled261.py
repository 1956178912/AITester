import json, itertools
files = ["experiments/results/main_batch/benchmark_synthetic_20261006_140906.json",
         "experiments/results/main_batch/benchmark_synthetic_20261006_151907.json",
         "experiments/results/main_batch/benchmark_synthetic_20261006_164357.json"]
arms=["aitester","plain_llm","plain_llm_df"]
pool={a:{} for a in arms}
for f in files:
    d=json.load(open(f)); seed=d["seed"]
    for a in arms:
        for r in d["results"][a]["details"]:
            pool[a][(seed,r["task_id"])]=r
print("pool sizes:", {a:len(pool[a]) for a in arms})
keys=sorted(pool["aitester"])
print("same key sets:", set(pool["aitester"])==set(pool["plain_llm"])==set(pool["plain_llm_df"]))
for a in arms:
    rows=[pool[a][k] for k in keys]
    nn=[r for r in rows if r.get("detection_rate") is not None]
    pos=sum(1 for r in nn if r["detection_rate"]>0)
    none=sum(1 for r in rows if r.get("detection_rate") is None)
    print(f"{a:14s} rows={len(rows)} nonnull={len(nn)} pos={pos} rate_nonnull={pos/len(nn)*100:.2f}%  none={none}")
print()
for a,b in itertools.combinations(arms,2):
    common=[k for k in keys if pool[a][k].get("detection_rate") is not None and pool[b][k].get("detection_rate") is not None]
    ra=sum(1 for k in common if pool[a][k]["detection_rate"]>0)/len(common)
    rb=sum(1 for k in common if pool[b][k]["detection_rate"]>0)/len(common)
    n10=sum(1 for k in common if pool[a][k]["detection_rate"]>0 and pool[b][k]["detection_rate"]==0)
    n01=sum(1 for k in common if pool[a][k]["detection_rate"]==0 and pool[b][k]["detection_rate"]>0)
    # naive unpaired (non-null denominators)
    nnA=[k for k in keys if pool[a][k].get("detection_rate") is not None]
    nnB=[k for k in keys if pool[b][k].get("detection_rate") is not None]
    pa=sum(1 for k in nnA if pool[a][k]["detection_rate"]>0)/len(nnA)
    pb=sum(1 for k in nnB if pool[b][k]["detection_rate"]>0)/len(nnB)
    print(f"{a} vs {b}: common={len(common)} pair_delta={ra-rb:+.4f} unpaired_delta={pa-pb:+.4f} n10={n10} n01={n01}")
# McNemar exact for common pairs
from math import comb
def binom_two_sided(n10,n01):
    n=n10+n01
    if n==0: return 1.0
    k=min(n10,n01)
    p=sum(comb(n,i) for i in range(0,k+1))/2**n
    return min(1.0,2*p)
for a,b in itertools.combinations(arms,2):
    common=[k for k in keys if pool[a][k].get("detection_rate") is not None and pool[b][k].get("detection_rate") is not None]
    n10=sum(1 for k in common if pool[a][k]["detection_rate"]>0 and pool[b][k]["detection_rate"]==0)
    n01=sum(1 for k in common if pool[a][k]["detection_rate"]==0 and pool[b][k]["detection_rate"]>0)
    chi2 = (abs(n10-n01)-1)**2/(n10+n01) if (n10+n01)>0 else 0.0
    print(f"McNemar {a} vs {b}: discordant={n10+n01} chi2_cc={chi2:.3f} exact_p={binom_two_sided(n10,n01):.5f}")
