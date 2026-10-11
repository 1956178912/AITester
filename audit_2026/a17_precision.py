import json, glob, os
def stats(files, arm="aitester"):
    S={"correct":0,"plausible":0,"precision_nonnull":0,"prec_gt1":0,"prec_mismatch":0,"rows":0,"patch":0}
    for f in files:
        try: d=json.load(open(f))
        except Exception: continue
        r=d.get("results",{}).get(arm)
        if not r: continue
        for x in r["details"]:
            S["rows"]+=1
            if str(x.get("patch") or "").strip(): S["patch"]+=1
            S["correct"]+=int(bool(x.get("patch_correct")))
            S["plausible"]+=int(bool(x.get("patch_plausible")))
            pp=x.get("patch_precision")
            if pp is not None:
                S["precision_nonnull"]+=1
                if pp>1: S["prec_gt1"]+=1
                exp=(int(bool(x.get("patch_correct")))/int(bool(x.get("patch_plausible")))) if x.get("patch_plausible") else None
                if exp is not None and abs(pp-exp)>1e-9: S["prec_mismatch"]+=1
    return S
groups={
 "main_batch(10)": sorted(glob.glob("experiments/results/main_batch/benchmark_*.json")),
 "e6_a1_batches(all json)": sorted(glob.glob("experiments/results/e6_a1_batches/**/*.json",recursive=True)),
 "r4_batches": sorted(glob.glob("experiments/results/r4_batches/**/benchmark_*.json",recursive=True)),
 "main_batch 3-seed R-P0-2": ["experiments/results/main_batch/benchmark_synthetic_20261006_140906.json","experiments/results/main_batch/benchmark_synthetic_20261006_151907.json","experiments/results/main_batch/benchmark_synthetic_20261006_164357.json"],
}
for g,fs in groups.items():
    print(g, stats(fs))
print()
# E4 FIXED harness detail
for f in ["experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json","experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/plain_llm_df.json","experiments/results/e6_a1_batches/e4_quixbugs_aitester/benchmark_quixbugs_20261009_215514.json"]:
    d=json.load(open(f))
    for arm,r in d["results"].items():
        rows=r["details"]
        c=sum(int(bool(x.get("patch_correct"))) for x in rows)
        pl=sum(int(bool(x.get("patch_plausible"))) for x in rows)
        pr=[x.get("patch_precision") for x in rows if x.get("patch_precision") is not None]
        print(os.path.basename(f), arm, "correct=",c,"plausible=",pl,"precision_nonnull=",len(pr),"values=",sorted(set(pr))[:8])
