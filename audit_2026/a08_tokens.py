import json
from collections import Counter
for label,f,arm in [
 ("E4 first aitester","experiments/results/e6_a1_batches/e4_quixbugs_aitester/benchmark_quixbugs_20261009_215514.json","aitester"),
 ("E4 first df","experiments/results/e6_a1_batches/e4_quixbugs_plain_llm_df/benchmark_quixbugs_20261009_223101.json","plain_llm_df"),
 ("E4 FIXED aitester","experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json","aitester"),
 ("E4 FIXED df","experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/plain_llm_df.json","plain_llm_df"),
]:
    d=json.load(open(f)); rows=d["results"][arm]["details"]
    toks=[(x.get("token_usage") or {}).get("total_tokens") or 0 for x in rows]
    det=[x.get("detection_rate") for x in rows]
    gold=[i for i,x in enumerate(rows) if det[i] is not None]
    dev=[i for i,x in enumerate(rows) if not str(rows[i]["task_id"]).endswith("_test")]
    print("="*60); print(label)
    print("  rows", len(rows), "sum_tok", sum(toks), "mean_all", round(sum(toks)/len(rows),1))
    print("  mean over detection-nonnull(%d):"%len(gold), round(sum(toks[i] for i in gold)/len(gold),1))
    print("  mean over nonzero-token rows(%d):"%sum(1 for t in toks if t), round(sum(t for t in toks if t)/max(1,sum(1 for t in toks if t)),1))
    print("  zero-token rows:", sum(1 for t in toks if t==0), "of", len(rows))
    # token_metrics avg
    print("  token_metrics.avg_tokens_per_task:", d["results"][arm]["token_metrics"].get("avg_tokens_per_task"), "total:", d["results"][arm]["token_metrics"]["total_tokens"])
    print("  detection_first_red_seen True:", sum(1 for x in rows if x.get("detection_first_red_seen") is True), "over gold rows:", sum(1 for i in gold if rows[i].get("detection_first_red_seen") is True))
    # try denominator giving claimed numbers
    for claim in (17156,16038,2370,1905):
        if sum(toks)/claim > 1:
            print(f"   claim {claim}: implied denominator = {sum(toks)/claim:.2f}")
