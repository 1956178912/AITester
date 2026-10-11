import json, glob, os
from collections import Counter
rows_all=[]; files=[]
for f in sorted(glob.glob("experiments/results/**/*.json",recursive=True)):
    try: d=json.load(open(f))
    except Exception: continue
    if not isinstance(d,dict): continue
    ds=str(d.get("dataset"))
    if "swe_bench" not in ds: continue
    files.append((f,ds,d.get("subset"),d.get("total_tasks")))
    for arm,r in d.get("results",{}).items():
        if not isinstance(r,dict) or "details" not in r: continue
        for x in r["details"]:
            if isinstance(x,dict): rows_all.append((f,arm,x))
print("swe_bench artifact files:", len(files))
for f,ds,sub,n in files:
    print(f"   {f}  dataset={ds} subset={sub} total_tasks={n}")
print("\ntotal swe_bench rows:",len(rows_all))
print("arm dist:",Counter(a for _f,a,_x in rows_all))
print("error_category:",Counter(str(x.get("error_category")) for _f,_a,x in rows_all))
print("has detection_rate key:", sum(1 for _f,_a,x in rows_all if "detection_rate" in x))
print("detection_rate non-null:", sum(1 for _f,_a,x in rows_all if x.get("detection_rate") is not None))
print("instance_code empty/absent:", sum(1 for _f,_a,x in rows_all if not str(((x.get("task_metadata") or {}).get("instance_code")) or "").strip())/len(rows_all))
print("repo=unknown:", sum(1 for _f,_a,x in rows_all if str(x.get("repo"))=="unknown"))
print("has generated_test nonempty:", sum(1 for _f,_a,x in rows_all if str(x.get("generated_test") or "").strip()))
print("has patch nonempty:", sum(1 for _f,_a,x in rows_all if str(x.get("patch") or "").strip()))
print("passed True:", sum(1 for _f,_a,x in rows_all if x.get("passed") is True))
