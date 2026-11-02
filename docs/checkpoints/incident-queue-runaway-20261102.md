# 事故处置：队列脚本失控重启（2026-11-02 15:39–15:45）

## 现象

| 指标 | 实测 |
|---|---|
| 判定进程总数 | 983（`judge_c8_generated_tests` 788 + `judge_swebench_generated_tests` 195） |
| 系统负载 | load 747 / 739 / 729（10 核） |
| `b3_queue.sh` 累计重启 | 6,425 次（首轮 11-01 19:03，均约 11 秒一轮） |
| `recovery_queue.sh` 累计重启 | 772 次 |
| 队列日志 | `/tmp/b3_queue.log` 80 MB，持续以 21 KB/20 s 增长 |

## 根因

`~/Library/LaunchAgents/com.aitester.queueA.plist` / `queueB.plist` 以
`KeepAlive=true` + `RunAtLoad=true` 托管了两个**一次性批处理脚本**
（`scripts/recovery_queue.sh`、`scripts/b3_queue.sh`）。

脚本正常退出后 launchd 立即重拉。两个脚本内：
- 生成步骤有产物判据（`benchmark_*.json` 存在即 skip），**幂等**；
- 判定步骤**无幂等、无锁**，每轮重拉都新起全量判定，且多个实例并发写同一
  `--out` 文件。

⇒ 11 秒一轮、每轮新增一批判定进程，孤儿进程（父 PID=1）逐轮累积。

## 附带影响

1. `C8_JUDGE.json` 始终未生成（并发互写风险），但 11-01 的 16 个分片
   `C8_JUDGE_{arm}_s*.json` 未被改动（mtime 仍为 11-01 21:3x–21:5x），
   `JUDGE_REPORT_20261101.md` 的分片聚合读数不受影响。
2. 空转批次在 15:40 写出 `b3_lite_20261031/B3_JUDGE.json`（298 条全
   `env_error`）——与 docker v2 的 222 red + 78 env_error 冲突，已重命名为
   `B3_JUDGE.json.INVALID-20261102-env_error298` 隔离，不得作读数来源。
3. 11-02 的 G8 r2 生成（off 13:42–14:15 / on 13:49–14:13）与生成判定（14:50 收官）
   全程落在本次事故窗口内（load 700+）。双臂同受同一资源约束，**对称零的方向不受影响**，
   但生成质量可能整体偏低；论文引用时宜披露该窗口，或待独立复核后定稿。

## 处置

1. `launchctl bootout gui/501/com.aitester.queueA`、`...queueB` —— 断源。
2. plist 重命名为 `*.plist.disabled-20261102`（保留原文，可回滚）。
3. `kill -TERM` 全部 983 个孤儿判定进程，12 秒内清零。
4. 脚本加固（`scripts/b3_queue.sh`、`scripts/recovery_queue.sh`）：
   - **重入锁**：`mkdir /tmp/<script>.lock` 原子占锁，并发实例直接 `exit 0`；
     `trap ... EXIT` 释放。
   - **完成标记**：`QUEUE_DONE.marker` 存在即退出，失败不落标记（保留重跑路径）。
   - **判定幂等**：C8 判定改按「16 分片齐备」跳过；B3 判定按 out 文件存在跳过。
   - B3 判定步骤加口径警告：该 repo 级通道已被 `judge_b3_docker_v2.py` 取代。

## 验证

| 项 | 结果 |
|---|---|
| `bash -n` 双脚本 | 通过 |
| 锁分支（预占锁） | 双脚本 exit 0，未触发跑批 |
| 完成标记分支 | 双脚本 exit 0，日志落 `done marker present, skip` |
| 处置后残留进程 | 0（`pgrep` 空） |
| 日志增长 | 0 bytes / 10 s |
| load（1 分钟均值） | 747 → 539（15:45，持续下降） |

## 回滚

```bash
mv ~/Library/LaunchAgents/com.aitester.queue{A,B}.plist.disabled-20261102 \
   ~/Library/LaunchAgents/com.aitester.queue{A,B}.plist
launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.aitester.queueA.plist
launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.aitester.queueB.plist
```

回滚前须先把 plist 的 `KeepAlive` 改为 `false`，否则事故会原样复现。

## 遗留项（本次未处理）

1. **G8 r2 的 `passed=0` 与「对称零」不矛盾，禁止混引**：`run_benchmark` 的
   `passed=False`（`stop_reason=skip_debugger_repair_invalid`、
   `error_category=patch_validation_failed`）是**修复补丁验证**未过，**不是**生成测试
   判定。生成测试的判定走 `judge_g8_gen.py` 的 per-instance 通道，终版读数为
   detected 0 / 0、green_buggy 346/354（`G8_GEN_SUMMARY.md`，14:50 收官）。
   引用 r2 结论必须带「生成判定」标签，不得用 `passed` 字段反推检出率。
2. B3 空转产物已隔离，聚合脚本若按 glob 匹配 `B3_JUDGE*.json` 需排除 `.INVALID`。
3. `rmdir` 在本沙箱内被拒（锁目录测试残留已用 Python 清理）；脚本由 launchd
   在沙箱外运行不受影响。
