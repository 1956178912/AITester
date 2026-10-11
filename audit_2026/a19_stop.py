import json, glob, os
from collections import Counter
groups={
 "R-P0-2 3seed": ["experiments/results/main_batch/benchmark_synthetic_20261006_140906.json","experiments/results/main_batch/benchmark_synthetic_20261006_151907.json","experiments/results/main_batch/benchmark_synthetic_20261006_164357.json"],
 "E1/E2 4批": sorted(glob.glob("experiments/results/main_batch/benchmark_synthetic_20261007_*.json")),
 "E6 control": ["experiments/results/e6_a1_batches/e6_control_seed42/benchmark_synthetic_20261009_181758.json"],
 "E6 phase1": ["experiments/results/e6_a1_batches/e6_phase1_standard_coldcache/benchmark_synthetic_20261009_190234.json"],
 "E6 phase2": ["experiments/results/e6_a1_batches/e6_phase2_matched_coldcache/benchmark_synthetic_20261009_191716.json"],
 "E4 fixed": ["experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json","experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/plain_llm_df.json"],
}
for g,fs in groups.items():
    print("="*70); print(g)
    per={}
    for f in fs:
        d=json.load(open(f))
        for arm,r in d["results"].items():
            c=per.setdefault(arm,Counter())
            for x in d["results"][arm]["details"]:
                c[str(x.get("stop_reason"))]+=1
    for arm,c in per.items():
        tot=sum(c.values())
        unk=c.get("unknown",0)+c.get("None",0)
        print(f"  {arm:14s} n={tot:3d} unknown/None={unk:3d} ({unk/tot*100:.1f}%)  {dict(c)}")
