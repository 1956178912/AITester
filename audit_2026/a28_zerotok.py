import json, glob, os
groups={"R-P0-2(3批)":["experiments/results/main_batch/benchmark_synthetic_20261006_140906.json","experiments/results/main_batch/benchmark_synthetic_20261006_151907.json","experiments/results/main_batch/benchmark_synthetic_20261006_164357.json"],
        "E1/E2(4批)":sorted(glob.glob("experiments/results/main_batch/benchmark_synthetic_20261007_*.json"))}
for g,fs in groups.items():
    print(g)
    for arm in ("aitester","plain_llm","plain_llm_df"):
        zero=tot=0; toksum=0
        for f in fs:
            d=json.load(open(f)); r=d["results"].get(arm)
            if not r: continue
            for x in r["details"]:
                tot+=1; t=(x.get("token_usage") or {}).get("total_tokens") or 0
                toksum+=t
                if t==0: zero+=1
        if tot: print(f"   {arm:14s} zero_token_rows={zero}/{tot} total_tokens={toksum}")
