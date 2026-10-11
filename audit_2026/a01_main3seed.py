import json, glob, os
files = ["experiments/results/main_batch/benchmark_synthetic_20261006_140906.json",
         "experiments/results/main_batch/benchmark_synthetic_20261006_151907.json",
         "experiments/results/main_batch/benchmark_synthetic_20261006_164357.json"]
for f in files:
    d=json.load(open(f))
    print("###", os.path.basename(f), "seed=",d.get("seed"), "ts=",d.get("timestamp"), "n=",d.get("total_tasks"), "dirty=",d["provenance"].get("git_dirty"), "cache_ns=",d["provenance"].get("cache_namespace"))
    for arm,r in d["results"].items():
        rows=r["details"]
        det=[x.get("detection_rate") for x in rows]
        nonnull=[x for x in det if x is not None]
        nred=sum(1 for x in nonnull if x>0)
        none_ct=sum(1 for x in det if x is None)
        rep=[x.get("repair_rate") for x in rows]
        repnn=[x for x in rep if x is not None]
        repok=sum(1 for x in repnn if x>0)
        ff=[x.get("false_fix_rate") for x in rows]
        ffnn=[x for x in ff if x is not None]
        print(f"   {arm:14s} rows={len(rows)} det_nonnull={len(nonnull)} det_pos={nred} det_none={none_ct} rep_nonnull={len(repnn)} rep_pos={repok} ff_nonnull={len(ffnn)} tok_total={r['token_metrics']['total_tokens']}")
