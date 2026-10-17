# N-4 产物终检：孤儿 pytest 巡检与清理记录（只读巡检 → 人工确认 → SIGTERM/SIGKILL）
scan_time_utc=2026-10-17T15:33:04Z
detector_cmd=detect_orphan_procs.py --json --min-age 60

## 发现（detector JSON）
{"available": true, "scanned": 716, "min_age_seconds": 60, "leaked": [{"pid": 24159, "ppid": 1, "etime": "32:33", "age_seconds": 1953, "command": "/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m pytest /var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tmpo12l918e/test_mutant.py --tb=no -q", "matched_marker": "test_mutant.py"}], "leaked_count": 1}

## ps 详情（清理前）
  PID  PPID ELAPSED  %CPU STARTED                      COMMAND
24159     1   32:33 100.0 Sat Oct 17 23:00:31 2026     /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m pytest /var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/tmpo12l918e/test_mutant.py --tb=no -q

判定：ppid=1（已被 init 收养）、age>1900s、批内父进程（run_main_batch/看门狗）早已退出、批内正常子进程不存在 → 确认孤儿；属 mutation_testing 的 test_mutant.py 子进程（M-3 已知族）。
cleanup_time_utc=2026-10-17T15:33:07Z
cleanup=SIGTERM（3s 宽限）→ 若存活再 SIGKILL；清理后存活探测：
GONE(已回收)

## 清理后复检（detector）
{"available": true, "scanned": 715, "min_age_seconds": 60, "leaked": [], "leaked_count": 0}
