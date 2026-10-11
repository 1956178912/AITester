import json, glob, os
from collections import Counter
files=sorted(glob.glob("experiments/results/**/*.json",recursive=True))
inc=Counter(); per={}
for f in files:
    try: d=json.load(open(f))
    except Exception: continue
    if not isinstance(d,dict) or not isinstance(d.get("results"),dict): continue
    for arm,r in d["results"].items():
        if not isinstance(r,dict) or "details" not in r: continue
        for x in r["details"]:
            if not isinstance(x,dict): continue
            pc=x.get("patch_correct"); pl=x.get("patch_plausible")
            if pc==1 and pl==0:
                inc["correct1_plausible0"]+=1
                per.setdefault(f,[]).append(x.get("task_id"))
print("rows with patch_correct=1 & patch_plausible=0:", inc["correct1_plausible0"])
for f,ids in per.items(): print("  ",f,len(ids))
# repair_history presence
rh=0; tot=0
for f in files:
    try: d=json.load(open(f))
    except Exception: continue
    if not isinstance(d,dict) or not isinstance(d.get("results"),dict): continue
    for arm,r in d["results"].items():
        if not isinstance(r,dict) or "details" not in r: continue
        for x in r["details"]:
            if not isinstance(x,dict): continue
            tot+=1
            if "repair_history" in x: rh+=1
print(f"rows containing repair_history: {rh}/{tot}")
