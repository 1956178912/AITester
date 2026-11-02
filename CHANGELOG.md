# 更新日志

> 最后更新：2026-11-02

本文件只记录对外可见的变化；逐轮历史见下方归档。

## [Unreleased]

### Added
- 过夜实验流水线批次（2026-11-01/02）：`experiments/run_benchmark.py` 增量断点续跑（每任务 flush+fsync 落 `INCREMENTAL_RESULTS.jsonl`，重启只补未完成任务，`AITESTER_SKIP_TASK_IDS` 过滤必卡任务）；判定器家族——`scripts/tools/judge_b3_docker.py`（B3 docker 等价重建：daocloud x86 镜像 + worktree 挂载 + 清华源 deps，零代理直连）及克隆修复版 `_v2`（environment markers 改传容器内文件由 pip 自解析，规避 shell 嵌套引号断裂的 line build 全灭）、`scripts/tools/judge_g8_docker.py`（G8 M3 门禁 per-instance 验证：宿主端 git apply + repo 自带 requirements + ghproxy 重写容器内 github 依赖；ansible/qutebrowser/openlibrary 三 repo smoke 全 `harness_valid`）；过夜看护 `experiments/watch_g8_off_20261101.sh`（stall 击杀自动重启、总时限/重试封顶、lock 幂等）。
- G8 full178 两臂收官读数：on 178/178（177 `harness_invalid` + 1 `patch_validation_failed`，passed=0）、off 177/178 + 1 必卡任务显式 skip——**effective 分母 = 0 全池实锤**，四开关对比 ran_unmeasurable 从 10 任务定性升级为全池口径；per-instance 门禁验证通道（第一步不烧 LLM）已建成待全量，用于恢复真实 effective 分母（若恢复，第二步重跑生成需另行授权）。
- H1 修订版（r2）三臂 + REF 重建完成：`env_snapshot` 三臂校验与 `SHA256SUMS` 通过；判据 ≤10pp 冻结（`payload_equivalence_prereg_amendment_20261101.md`），替代原口径的「强制不可判定」收口（REF 工件随 AITester-w-head 删除不可恢复）。
- 扩样判定统计终版（`experiments/results/JUDGE_REPORT_20261101.md`）：C8 修复后 aitester 1/166=0.60%、df 2/109=1.83%（judge_exception 39+34 清零）；TGE 首判 1.1% vs 2.1%；rescue31 + luigi33 检出 0；全批 502 有效判定检出 6≈1.2%，fix_not_green 主导（54.5%）。

### Changed
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
