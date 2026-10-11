import json
TESTS={"breadth_first_search_test","depth_first_search_test","detect_cycle_test","minimum_spanning_tree_test","reverse_linked_list_test","shortest_path_length_test","shortest_path_lengths_test","shortest_paths_test","topological_ordering_test"}
for label,f,arm in [
 ("E4 first aitester","experiments/results/e6_a1_batches/e4_quixbugs_aitester/benchmark_quixbugs_20261009_215514.json","aitester"),
 ("E4 first df","experiments/results/e6_a1_batches/e4_quixbugs_plain_llm_df/benchmark_quixbugs_20261009_223101.json","plain_llm_df"),
 ("E4 FIXED aitester","experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json","aitester"),
 ("E4 FIXED df","experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/plain_llm_df.json","plain_llm_df"),
]:
    d=json.load(open(f)); rows=d["results"][arm]["details"]
    ids=[str(r["task_id"]).split("__")[-1] for r in rows]
    drv=[i for i,n in enumerate(ids) if n in TESTS]
    nondrv=[i for i,n in enumerate(ids) if n not in TESTS]
    toks=[(r.get("token_usage") or {}).get("total_tokens") or 0 for r in rows]
    det=[r.get("detection_rate") for r in rows]
    print(f"{label}: rows={len(rows)} test_driver_matched={len(drv)} non_driver={len(nondrv)}")
    if nondrv:
        print(f"   mean tokens over non-driver({len(nondrv)}) = {sum(toks[i] for i in nondrv)/len(nondrv):.1f}")
    # detection nonnull rows
    nn=[i for i in range(len(rows)) if det[i] is not None]
    print(f"   det nonnull={len(nn)} mean_tokens_over_detnonnull={sum(toks[i] for i in nn)/len(nn):.1f}")
    # what about rows where detection_rate is not None AND non-driver
    both=[i for i in nn if ids[i] not in TESTS]
    print(f"   det-nonnull ∩ non-driver = {len(both)} mean={sum(toks[i] for i in both)/max(1,len(both)):.1f}")
    # false_fix claim
    ff=[r.get("false_fix_rate") for r in rows if r.get("detection_rate") is not None]
    print("   false_fix (det nonnull rows) mean:", round(sum(x for x in ff if x is not None)/max(1,len([x for x in ff if x is not None])),4))
