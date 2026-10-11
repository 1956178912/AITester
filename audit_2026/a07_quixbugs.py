import json, os
from collections import Counter
cases = {
 "E4 first run aitester": "experiments/results/e6_a1_batches/e4_quixbugs_aitester/benchmark_quixbugs_20261009_215514.json",
 "E4 first run df": "experiments/results/e6_a1_batches/e4_quixbugs_plain_llm_df/benchmark_quixbugs_20261009_223101.json",
 "E4 FIXED aitester": "experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json",
 "E4 FIXED df": "experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/plain_llm_df.json",
}
for label,f in cases.items():
    d=json.load(open(f))
    if "results" not in d:
        print(label, "-> no results key; keys:", list(d)[:12]); continue
    prov=d.get("provenance",{})
    print("="*70)
    print(label, os.path.basename(f), "n_tasks=",d.get("total_tasks"), "cache=",prov.get("cache_enabled"), "ns=",prov.get("cache_namespace"), "dirty=",prov.get("git_dirty"), "temperature=",prov.get("temperature"))
    for arm,r in d["results"].items():
        rows=r["details"]
        det=[x.get("detection_rate") for x in rows]
        nn=[x for x in det if x is not None]
        pos=sum(1 for x in nn if x>0)
        rep=[x.get("repair_rate") for x in rows]
        repnn=[x for x in rep if x is not None]
        reppos=sum(1 for x in repnn if x>0)
        pl=[x.get("patch_plausible") for x in rows]
        plnn=[x for x in pl if x is not None]
        plpos=sum(1 for x in plnn if x)
        red=[x.get("detection_first_red_seen") for x in rows]
        redtrue=sum(1 for x in red if x is True)
        tm=r.get("token_metrics",{})
        toks=tm.get("total_tokens",0)
        print(f"  {arm:14s} rows={len(rows)} | det nonnull={len(nn)} pos={pos} | rep nonnull={len(repnn)} pos={reppos} | plausible nonnull={len(plnn)} pos={plpos} | red_seen={redtrue} | tok_total={toks} tok/task={toks/len(rows):.0f}")
        sr=Counter(str(x.get('stop_reason')) for x in rows)
        print(f"      stop_reason: {dict(sr)}")
        md=Counter(str(x.get('detection_first_status')) for x in rows)
        print(f"      detection_first_status: {dict(md)}")
