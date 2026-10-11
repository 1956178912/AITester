import json, glob, os, collections
files = sorted(glob.glob("experiments/results/**/*.json", recursive=True))
def rows_of(d, arm):
    try: return d["results"][arm]["details"]
    except Exception: return None
for f in files:
    try: d=json.load(open(f))
    except Exception: continue
    if not isinstance(d,dict) or "results" not in d or not isinstance(d.get("results"),dict): continue
    arms=[a for a in d["results"] if isinstance(d["results"].get(a),dict) and "details" in d["results"][a]]
    out=[]
    for a in arms:
        c=collections.Counter()
        for r in d["results"][a]["details"]:
            v=r.get("specificity_gate_verdict")
            if v is not None: c[str(v)]+=1
        if c: out.append(f"{a}={dict(c)}")
    if out:
        print(f"{f}\n    " + " | ".join(out))
