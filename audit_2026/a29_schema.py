import json, glob
schema=['detection_rate','repair_rate','false_fix_rate','regression_rate','test_error_rate','oracle_type','test_visible_to_system','patch_plausible','patch_correct','patch_precision','source_patched_unverified','patch_evidence_level','fl_at_k','llm_localization','localization_hit_function','localization_hit_function_at_3','localization_mrr','edit_intent_status','edit_localization','deterministic_repair_status','patch_abstained','patch_abstain_signals','spec_compile_rate','patch_rollback_verdict','patch_rolled_back','mutation_detection_rate','mutants_killed','mutants_total','spec_expr_coverage','specificity_gate_verdict','red_regression_violation','fl_constraint_verdict','fl_constraint_hit_rank','fl_constraint_changed_functions','oracle_quality_history','self_repair_trap_suspected','self_repair_trap_signals','spec_oracle_injected','spec_oracle_verdict']
present={k:0 for k in schema}; nonnull={k:0 for k in schema}; tot=0
for f in glob.glob("experiments/results/**/*.json",recursive=True):
    try: d=json.load(open(f))
    except Exception: continue
    if not isinstance(d,dict) or not isinstance(d.get("results"),dict): continue
    for arm,r in d["results"].items():
        if not isinstance(r,dict) or "details" not in r: continue
        for x in r["details"]:
            if not isinstance(x,dict): continue
            tot+=1
            for k in schema:
                if k in x:
                    present[k]+=1
                    if x[k] is not None: nonnull[k]+=1
print("rows:",tot)
print("keys never present:",[k for k in schema if present[k]==0])
for k in schema: print(f"  {k:34s} present={present[k]:5d} nonnull={nonnull[k]:5d}")
