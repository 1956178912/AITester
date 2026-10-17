# O-2 attempt#2 孤儿 pytest 巡检与清理（只读巡检→人工确认→SIGTERM）
scan_time_utc=2026-10-17T17:57:44Z
detector_cmd=detect_orphan_procs.py --json --min-age 60

## 发现（detector JSON）
{"available": true, "scanned": 608, "min_age_seconds": 60, "leaked": [{"pid": 63956, "ppid": 1, "etime": "01:22", "age_seconds": 82, "command": "/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m pytest -q --no-header -p no:cacheprovider /var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/aitester_mdo_t_5fehw6dq/test_find_first_in_sorted.py", "matched_marker": "aitester_mdo_"}], "leaked_count": 1}

## ps 详情（清理前）
  PID  PPID ELAPSED  %CPU STARTED                      COMMAND
63956     1   01:22  99.2 Sun Oct 18 01:56:22 2026     /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m pytest -q --no-header -p no:cacheprovider /var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/aitester_mdo_t_5fehw6dq/test_find_first_in_sorted.py

判定：ppid=1、age 71s、批内父进程（control run_main_batch）已被 2400s 看门狗 SIGTERM 终止 → 确认孤儿；属 MDO post-processing 的 pytest 子进程（M-3 已知族）。

cleanup_time_utc=2026-10-17T17:57:47Z
GONE(已回收)

## 清理后复检（detector）
{"available": true, "scanned": 607, "min_age_seconds": 60, "leaked": [], "leaked_count": 0}
