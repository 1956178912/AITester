import json
pairs=[("experiments/results/main_batch/benchmark_synthetic_20261007_161053.json","experiments/results/main_batch/benchmark_synthetic_20261007_181638.json",42),
       ("experiments/results/main_batch/benchmark_synthetic_20261007_170147.json","experiments/results/main_batch/benchmark_synthetic_20261007_185941.json",44)]
for fa,fb,seed in pairs:
    A=json.load(open(fa)); B=json.load(open(fb))
    print(f"=== seed {seed}: {fa.split('/')[-1]} vs {fb.split('/')[-1]} ===")
    for arm in ("aitester","plain_llm","plain_llm_df"):
        ra={r["task_id"]:r for r in A["results"][arm]["details"]}
        rb={r["task_id"]:r for r in B["results"][arm]["details"]}
        same_det=sum(1 for k in ra if ra[k].get("detection_rate")==rb[k].get("detection_rate"))
        same_verdict=sum(1 for k in ra if ra[k].get("specificity_gate_verdict")==rb[k].get("specificity_gate_verdict"))
        same_patch=sum(1 for k in ra if (ra[k].get("patch") or "")==(rb[k].get("patch") or ""))
        same_test=sum(1 for k in ra if (ra[k].get("generated_test") or "")==(rb[k].get("generated_test") or ""))
        n=len(ra)
        print(f"  {arm:14s} n={n} identical detection={same_det} verdict={same_verdict} patch={same_patch} generated_test={same_test}")
    print("  git_sha:", A["provenance"]["git_sha"][:8], B["provenance"]["git_sha"][:8], "| git_dirty:", A["provenance"]["git_dirty"], B["provenance"]["git_dirty"],
          "| cache_ns:", A["provenance"].get("cache_namespace"), B["provenance"].get("cache_namespace"))
