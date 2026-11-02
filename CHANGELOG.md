# 更新日志

> 最后更新：2026-11-02

本文件只记录对外可见的变化；逐轮历史见下方归档。

## [Unreleased]

### Added
- 过夜实验流水线批次（2026-11-01/02）：`experiments/run_benchmark.py` 增量断点续跑（每任务 flush+fsync 落 `INCREMENTAL_RESULTS.jsonl`，重启只补未完成任务，`AITESTER_SKIP_TASK_IDS` 过滤必卡任务）；判定器家族——`scripts/tools/judge_b3_docker.py`（B3 docker 等价重建：daocloud x86 镜像 + worktree 挂载 + 清华源 deps，零代理直连）及克隆修复版 `_v2`（environment markers 改传容器内文件由 pip 自解析，规避 shell 嵌套引号断裂的 line build 全灭）、`scripts/tools/judge_g8_docker.py`（G8 M3 门禁 per-instance 验证：宿主端 git apply + repo 自带 requirements + ghproxy 重写容器内 github 依赖；ansible/qutebrowser/openlibrary 三 repo smoke 全 `harness_valid`）；过夜看护 `experiments/watch_g8_off_20261101.sh`（stall 击杀自动重启、总时限/重试封顶、lock 幂等）。
- G8 full178 两臂收官读数：on 178/178（177 `harness_invalid` + 1 `patch_validation_failed`，passed=0）、off 177/178 + 1 必卡任务显式 skip——**effective 分母 = 0 全池实锤**，四开关对比 ran_unmeasurable 从 10 任务定性升级为全池口径；per-instance 门禁验证通道（第一步不烧 LLM）已建成待全量，用于恢复真实 effective 分母（若恢复，第二步重跑生成需另行授权）。
- H1 修订版（r2）三臂 + REF 重建完成：`env_snapshot` 三臂校验与 `SHA256SUMS` 通过；判据 ≤10pp 冻结（`payload_equivalence_prereg_amendment_20261101.md`），替代原口径的「强制不可判定」收口（REF 工件随 AITester-w-head 删除不可恢复）。
- 扩样判定统计终版（`experiments/results/JUDGE_REPORT_20261101.md`）：C8 修复后 aitester 1/166=0.60%、df 2/109=1.83%（judge_exception 39+34 清零）；TGE 首判 1.1% vs 2.1%；rescue31 + luigi33 检出 0；全批 502 有效判定检出 6≈1.2%，fix_not_green 主导（54.5%）。

### Fixed
- G8 p2p 判定器转义缺陷（2026-11-02）：`judge_g8_p2p.py` 用 `x.replace("'", "'''")` 转义测试名中的单引号，该写法在 shell 单引号语境下不成立，含引号的参数化测试名使命令提前闭合 → 3 例被误记为 `p2p_broken`（并非 gold patch 破坏 pass-to-pass）。改用 `shlex.quote` 后复验 **19/19 `p2p_ok`**（3 例原 broken + 16 例含引号任务的静默假绿筛查，均无假绿）。完整门禁 **141/178 = 79.2% → 144/178 = 80.9%**，真实 p2p 破坏 **0 例**；稿件 G8 段与 SRC 注释同步更正并重编译（73 页 / 0 错误 / style 9/9 / compliance 0 FAIL）。四开关对称零（0/177）结论不变。
- 队列脚本失控重启（2026-11-02 事故）：`scripts/b3_queue.sh` / `scripts/recovery_queue.sh` 被 launchd 以 `KeepAlive=true` 托管，退出即重拉（实测 6,425 / 772 次），判定步骤不幂等导致 983 个孤儿判定进程、load 747。已卸载并禁用两个 LaunchAgent、终止全部残留进程，脚本补**重入锁 + 完成标记 + 判定幂等**三重防护；空转批次写出的 `b3_lite_20261031/B3_JUDGE.json`（298 条全 `env_error`）重命名为 `.INVALID-20261102-env_error298` 隔离。处置与回滚见 `docs/checkpoints/incident-queue-runaway-20261102.md`。

### Changed
- B3 Lite 判定口径更新（docker v2 终版）：原 78 条 `env_error` 复核为**冷启动资源竞争**——`judge_b3_docker_v2.py` 未校验 `docker run` 返回值，容器未运行被折叠成环境失败；分布上 78 条全部落在第一批 s1–s3（同批 s4–s6 为 0）。补跑 78/78 全部转 `red`（22m55s，零 LLM），有效分母 **222→300**、`env_error` 归零、**检出 0/300**。判定器已补返回值校验与一次重试（`58e0c41d`）。旧口径（py3.8/py3.14/conda 三版基线 env_error 246→281→286）为历史读数，**不可与 v2 混池**。
- off 臂必卡任务处置口径：attempt29–33 五轮同点 stall、看护进度提取失效（`progress=?`）⇒ 两轮交叉 skip 失效，改 `AITESTER_SKIP_TASK_IDS` 显式跳过收官；两臂读数口径披露为 on 178/178 vs off 177/178+1skip，skip 任务的门禁读数由 per-instance 通道补位。
- 逐轮条目归档：2026-11-02 批次之前的全部 `[Unreleased]` 条目（GK/GJ/GG/第十轮/GH/FF/FE/FD/FC/FB/DF 及更早 Fixed 各轮，128 行原文）移入 [docs/history/CHANGELOG_2026-11-02_batches.md](docs/history/CHANGELOG_2026-11-02_batches.md)（**原文逐字保留，未删改**；英文版同目录 `.en.md`）。

## [1.0.0] - 2026-10-25

### Added
- 复现包 `REPLICATION.md`、`REPRODUCE_SKIP_TESTS` 显式逃生口与零 LLM 复算链。
- 发布判据 ADR-0036；发布新鲜度守卫。

### Changed
- repair 读数采用修正口径 v2（39.31%，57/145 可重放行，gold 独立裁决）；
  历史口径见 `docs/design/repair_caliber_matrix.md`。
- 模型调用默认关闭 thinking、默认开启 JSON 模式（ADR-0031）。

### Fixed
- 修复 `repair=0` 两起测量伪影：patch 字段围栏残留、跨文件任务未物化。
- 文档命令可执行性、引用库可编译性等门禁补链。

### Security
- 敏感/私有路径纳入仓库卫生门禁；`.env*` 与私有目录不得被跟踪。
- git 历史存量泄漏处置见 `docs/security/history_leak_remediation_runbook.md`。

## 更早版本

0.8 / 0.9 系列与更早的逐轮记录见归档（原样保留，链接不保证可达）：
[README（中文）](docs/history/README_2026-10-26_full.md) · [README（英文）](docs/history/README_2026-10-26_full.en.md) ·
[CHANGELOG（中文）](docs/history/CHANGELOG_2026-10-26_full.md) · [CHANGELOG（英文）](docs/history/CHANGELOG_2026-10-26_full.en.md)。
