import json
from math import comb
def load(f,arm="aitester"):
    d=json.load(open(f)); return {r["task_id"]:r for r in d["results"][arm]["details"]}
def mcnemar(A,B):
    ks=[k for k in A if k in B]
    d2=[k for k in ks if A[k].get("detection_rate") is not None and B[k].get("detection_rate") is not None]
    n10=sum(1 for k in d2 if A[k]["detection_rate"]>0 and B[k]["detection_rate"]==0)
    n01=sum(1 for k in d2 if A[k]["detection_rate"]==0 and B[k]["detection_rate"]>0)
    n=n10+n01
    chi2=((abs(n10-n01)-1)**2/n) if n else 0.0
    # exact two-sided binomial
    k=min(n10,n01)
    p=min(1.0, 2*sum(comb(n,i) for i in range(k+1))/2**n) if n else 1.0
    return dict(common=len(ks), both_nonnull=len(d2), posA=sum(1 for k in d2 if A[k]['detection_rate']>0), posB=sum(1 for k in d2 if B[k]['detection_rate']>0), n10=n10,n01=n01,chi2_cc=round(chi2,3), p_exact=round(p,4))
E6C=load("experiments/results/e6_a1_batches/e6_control_seed42/benchmark_synthetic_20261009_181758.json")
P1A=load("experiments/results/e6_a1_batches/e6_phase1_standard_coldcache/benchmark_synthetic_20261009_190234.json")
P1L=load("experiments/results/e6_a1_batches/e6_phase1_standard_coldcache/benchmark_synthetic_20261009_190234.json","plain_llm")
P1D=load("experiments/results/e6_a1_batches/e6_phase1_standard_coldcache/benchmark_synthetic_20261009_190234.json","plain_llm_df")
P2A=load("experiments/results/e6_a1_batches/e6_phase2_matched_coldcache/benchmark_synthetic_20261009_191716.json")
P2D=load("experiments/results/e6_a1_batches/e6_phase2_matched_coldcache/benchmark_synthetic_20261009_191716.json","plain_llm_df")
E6L=load("experiments/results/e6_a1_batches/e6_control_seed42/benchmark_synthetic_20261009_181758.json","plain_llm")
E6D=load("experiments/results/e6_a1_batches/e6_control_seed42/benchmark_synthetic_20261009_181758.json","plain_llm_df")
tests=[("E6ctrl aitester vs df",E6C,E6D,"claim chi2=16.962"),
 ("E6ctrl aitester vs plain_llm",E6C,E6L,"claim +8.8pp sig-test p=0.0625"),
 ("phase2 df_matched vs phase1 aitester_standard",P2D,P1A,"claim discordant 19 chi2 13.474 p=0.0002"),
 ("phase2 aitester_matched vs phase1 df_standard",P2A,P1D,"claim discordant 2 chi2 0.5 p=0.4795"),
 ("phase1 df vs phase2 df (instrumentality)",P1D,P2D,"claim delta -4.6pp chi2 1.125 p=0.2888"),
 ("phase1 aitester vs E6ctrl aitester",P1A,E6C,"-"),
 ("phase1 df vs E6ctrl df",P1D,E6D,"-")]
for name,A,B,claim in tests:
    print(f"{name}: {mcnemar(A,B)}   [{claim}]")
