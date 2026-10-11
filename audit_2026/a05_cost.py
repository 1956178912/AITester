import json
files = ["experiments/results/main_batch/benchmark_synthetic_20261006_140906.json",
         "experiments/results/main_batch/benchmark_synthetic_20261006_151907.json",
         "experiments/results/main_batch/benchmark_synthetic_20261006_164357.json"]
PRICE={"input_per_mtok":0.3,"output_per_mtok":1.2}
tot={}
for f in files:
    d=json.load(open(f))
    for arm,r in d["results"].items():
        tm=r["token_metrics"]
        t=tot.setdefault(arm,{"in":0,"out":0,"total":0,"rows":0,"calls":0})
        t["in"]+=tm["total_input_tokens"]; t["out"]+=tm["total_output_tokens"]
        t["total"]+=tm["total_tokens"]; t["rows"]+=len(r["details"]); t["calls"]+=tm["total_llm_calls"]
print(f"{'arm':14s} {'in':>10s} {'out':>10s} {'total':>10s} {'rows':>5s} {'tok/task':>9s} {'$/task':>8s} {'$/detection':>12s}")
det={"aitester":38,"plain_llm":4,"plain_llm_df":117}
for arm,t in tot.items():
    cost=(t["in"]/1e6)*PRICE["input_per_mtok"]+(t["out"]/1e6)*PRICE["output_per_mtok"]
    per=cost/t["rows"]
    print(f"{arm:14s} {t['in']:10d} {t['out']:10d} {t['total']:10d} {t['rows']:5d} {t['total']/t['rows']:9.1f} {per:8.4f} {cost/det[arm]:12.4f}")
print()
# per-seed breakdown
for f in files:
    d=json.load(open(f))
    for arm,r in d["results"].items():
        tm=r["token_metrics"]
        cost=(tm["total_input_tokens"]/1e6)*0.3+(tm["total_output_tokens"]/1e6)*1.2
        print(f"{f[-20:]:20s} {arm:14s} tok={tm['total_tokens']:9d} tok/task={tm['avg_tokens_per_task']:9.1f} $/task={cost/len(r['details']):.4f}")
