# B2 指纹复现批预注册（2026-10-29，引用 T 轮设计 + E8 发现）

状态：FROZEN（跑前落盘；用户 2026-10-28 已授权 B1 组全部配额实验）。

## 动机与目的

T 轮 B2 锁指纹复现批（2026-10-18，a93c1f6 切点、3 seed × 3 臂 × 87）判定
`not_reproduced`（次级排序 R1/R3 失败而核心负面 R2 仍显著）。E8 三格
（2026-10-28）进一步发现：**同切点 legacy-on 格 df 6.9% vs R-P0-2 原批
59.58%**，漂移不能归因 thinking mode，主要嫌疑 = **模型快照漂移**。

本批目的：**以多 seed 复现 + 指纹探针对比验证快照漂移假说**——
1. 新批次 `model_fingerprint`（system_fingerprint + 探针 sha256）与 T 轮
   批次工件记录对比：指纹不同 = 快照已变 = T 轮 not_reproduced 的机械成因
   锁定；
2. 3 seed 方向性复现检验（E8 单 seed 结论的稳健性）。

## 设计（冻结，与 T 轮 run_t1_b2_main_batch.sh 同口径）

- 切点：`a93c1f60ee31b9582e0146f73e3038e6ce0f01a1`（干净 worktree）
- 3 seed（42/43/44）× 3 臂（aitester, plain_llm, plain_llm_df）× synthetic 87
- `AITESTER_PROFILE=logic`、`TEMPERATURE=0.0`、`LLM_THINKING_MODE=disabled`、
  冷缓存（AITESTER_LLM_CACHE=0）、`ENABLE_MUTATION_SCORING=false`
  （T 轮口径修正：mutation 不进复现判据，节省 postprocess 墙钟——T 轮
  watchdog 7200s 内完成，本批保留 7200s 但 mutation 关闭）
- 逐 seed 硬门槛：干净树 / model_fingerprint.pinned=true / 87 行 / exit=0 /
  task 集一致
- 成本预估：3 × $1.65（E8 off 格实测外推）≈ **$5**，批次闸 $6

## 判定（冻结）

- **指纹判据（新增，本批主问题）**：新批 system_fingerprint 与 T 轮批
  `t_round_b2_main_batch_20261018` 记录对比——一致 ⇒ 快照漂移假说**否定**，
  漂移须另寻归因（协议/任务发生器）；不一致 ⇒ **快照漂移实锤**，T 轮
  not_reproduced 与 E8 legacy 复现失败统一归因模型侧，harness 侧排除。
- 方向性判据（同 T 轮）：三 seed 的三臂读数方向与 T 轮对比，如实报告，
  不设通过阈值（复现性测量非假设检验）。

## 失败策略

单 seed 失败/超时如实记录、不重跑；跑完剩余 seed。任格硬门槛失败该格
作废并披露。
