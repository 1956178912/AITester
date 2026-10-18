# T1（B2）预注册（FROZEN，跑前冻结）：主批次锁指纹复现批（3 seed × 3 臂）

> **状态：FROZEN（2026-10-18，跑前落盘；PREREG sha256 记入 PREFLIGHT.json）**。判定与失败处理规则冻结后不改。
> **性质：复现性测量（reproducibility measurement），非能力主张、非新假设检验**。回答的问题只有一个：
> 在**干净工作树 + 模型指纹 pinned=true + 完整 provenance** 的现代 harness 上，R-P0-2 头条三种子
> 结论（`plain_llm_df` 检出 > `aitester` > `plain_llm`；aitester vs df 为负）是否**方向性复现**。
> 本批不宣称任何新能力，不改变生产默认开关。

## 0. 切点与运行环境

| 项 | 值 |
|---|---|
| 切点 commit | `a93c1f60ee31b9582e0146f73e3038e6ce0f01a1`（S 轮终稿；`git rev-parse HEAD` 校验） |
| 干净 worktree | `/Users/wangchenyu/Workspace/AITester-t-b2-a93c1f6`（detached HEAD=切点；跑前 `git status --porcelain`=0；`.env`/`.env.local` 已复制，均 gitignore） |
| 原批次参照（只读） | `main_batch/benchmark_synthetic_20261006_140906.json`（seed42，sha256=`6e31c07d…`）/ `..._151907.json`（seed43，sha256=`bb5fcfc8…`）/ `..._164357.json`（seed44，sha256=`be6a42e5…`） |
| 模型/档位 | deepseek-flash；`AITESTER_PROFILE=logic`；`TEMPERATURE=0.0`；`LLM_THINKING_MODE=disabled`（默认）；`BENCHMARK_PARALLELISM=4`；冷缓存 `AITESTER_LLM_CACHE=0` |
| 预算/墙钟 | 估算 **≈$4.5**（R-P0-2 三批实测 8,755,871 tok × 官方价目上界）/ 已批 ≤$6；墙钟 **≤ 4h**；watchdog **7200s/seed**；单 seed 失败/超时如实报告、不重跑 |
| 任务协议 | `--dataset synthetic --task-count 87 --max-pattern-repeat 2 --seed <42|43|44> --baselines aitester,plain_llm,plain_llm_df --skip-stats`（**已实测核对**：`max_pattern_repeat=2` 生成的 87 任务 `task_id` 集合、`pattern_name`、`noise_seed` 与原批次逐项一致；`None` 口径 57/87 不一致） |

### 0.1 环境变量（显式，冻结）

```
AITESTER_PROFILE=logic
TEMPERATURE=0.0
LLM_THINKING_MODE=disabled
MAX_ITERATIONS=3
LLM_TIMEOUT=60
EXECUTION_TIMEOUT=30
ENABLE_PLANNER=true
ENABLE_DEBUGGER=true
ENABLE_RAG=false
BENCHMARK_PARALLELISM=4
AITESTER_LLM_CACHE=0
AITESTER_CACHE_NAMESPACE=t_b2_main_<seed>
AITESTER_TRACE_DIR=<OUT>/traces_seed<seed>（仓库外，保持 worktree 干净）
# 安全护栏（非行为开关；原批 cost_budget_enabled=false，本批启用仅作失控保护）
COST_BUDGET_ENABLE=true
COST_BUDGET_TOKENS=200000      # 单任务 token 硬上限（R-P0-2 实测单任务最大 96,479，2× 余量，预期不绑定）
COST_BUDGET_USD=1.0            # 单任务美元上限（预期不绑定）
AITESTER_BATCH_MAX_CALLS=6000  # 批次级调用上限（预检估算上界 5,051，实际约 1,652）
AITESTER_BATCH_MAX_USD=6.0
AITESTER_RUN_PREFLIGHT=true
```

**Harness 漂移声明（跑前已知，必须随结果披露）**：原批（2026-10-06，commit `b533cff`）到切点
`a93c1f6` 之间 `logic` 档与默认配置有增量（如后续轮次新增的 oracle 执行档、变异顾问、
回滚 fail-closed、停滞检测默认关等）。本批判据是"**当前切点 documented protocol 下的方向性复现**"，
**不是逐字节等价重跑**；逐项漂移以两批 provenance `env_snapshot` 的 diff 呈现，不做静默口径合并。
**护栏偏离**：本批启用任务级预算护栏（原批 `cost_budget_enabled=false`）——上限按 R-P0-2 实测
单任务最大 token 的 2× 设定，预期不绑定；若日志出现 `budget_exceeded`，该行按事实报告并计入分析披露。

## 1. 判据（预注册，冻结）

### 1.1 可复现性硬门槛（任一项失败 → 本批按 `not_reproducible_grade` 报告，不得用于引用）

1. 三批 provenance 均 `git_dirty=false` 且 `git_sha=a93c1f6…`；
2. 三批 `model_fingerprint.pinned=true`（探针哈希/返回 model/system_fingerprint 齐全）；
3. 每批每臂 **87 行**、`exit_code=0`、0 crash（批次 JSON 可解析、无 traceback 终止）；
4. `task_id` 集合与 §0 原批次逐 seed 一致（87/87）。

### 1.2 方向性复现判据（主判据，逐 seed 并列 + 三 seed 合并）

- **R1 排序**：合并口径（3 seed 各 87 任务池化，n=261/臂）`detection_rate` 满足
  `plain_llm_df > aitester` 且 `aitester > plain_llm`；
- **R2 负向差**：`aitester` vs `plain_llm_df` 配对差 δ<0（McNemar 精确检验 + bootstrap 95% CI 为参考量）；
- **R3 逐 seed 稳健**：R1 排序在 **≥2/3 seeds** 成立（单 seed n=87，MDE 级噪声下不要求 3/3）。

判定：
- **`reproduced`** = 1.1 全过 ∧ R1 ∧ R2 ∧ R3；
- **`direction_partial`** = 1.1 全过 ∧ R1 成立但 R2 不显著（CI 含 0）；
- **`not_reproduced`** = 1.1 全过 ∧ R1 或 R2 反向；
- **`not_reproducible_grade`** = 1.1 任一项失败（此时只报告事实，不出方向性结论）。

### 1.3 并列报告（不参与判定）

三指标（detection / repair / false_fix）逐 seed 逐臂；repair/false_fix 用与主批次一致的
**修正口径**（`make corrected-metrics` 同源函数，只读本批工件）；token/成本/墙钟；
`stop_reason` 分布；`llm_suite_detection_rate` 与 `detection_rate` 双口径并列（N-3 后口径，
若字段存在）；与原批次逐 seed 数字并排（只描述差异，不做事后改判）。

## 2. 执行顺序与失败处理

- seed 顺序 = 42 → 43 → 44（固定，不按结果择序）；每 seed 跑完**立即校验 §1.1 门槛**并落盘
  `seed<seed>_GATE.json`；任一 seed 门槛失败 → 记录事实，**仍按序跑完剩余 seed**（不得中途换 seed/重跑）。
- 单 seed 超 watchdog（7200s）→ SIGTERM→SIGKILL 进程组，记 `timeout`，继续下一 seed。
- 成本失控（估算超 $6）→ 中止后续 seed，如实报告（已产生 seed 照常分析）。
- 跑批期间 worktree 源码**零改动**（TOCTOU：preflight 记录关键文件 sha256，launch 前复核；
  运行中若 sha 变化 → 该批次作废并如实披露）。

## 3. 产物

`experiments/results/t_round_b2_main_batch_20261018/`：`PREREG.md`（本件）/**`PREFLIGHT.json`**（切点/干净度/
env/预估/源码哈希）/**`RUN_SUMMARY.log`**（逐 seed 命令/墙钟/exit）/`seed<NN>/benchmark_synthetic_*.json` +
`traces/` / `seed<NN>_GATE.json` / `GATES.json`（门槛汇总）/ `README.md` / `ANALYSIS_REPORT.json`
（§1.2 判定 + §1.3 并列表 + 与原批并排）/ `SHA256SUMS`（`checksum_results.py --write` 且 `--verify` 通过；
`traces` 为可再生物，按项目惯例不入校验清单）。
真实 LLM 的原始响应不入库（项目既有口径：trace JSONL 只存结构化事件，见 B7）。

## 4. 局限（跑前声明，不得事后删除）

- 单次运行/seed，温度 0 仍有服务端非确定性；**复现 ≠ 逐位相等**，判据只到方向/排序级；
- harness 已漂移（§0.1），跨批差异归因不给单一原因；
- `plain_llm_df` 跨批 detection 波动（83.8%→77.8% 历史区间，Q5 未决）已登记，本批不解释该波动；
- 本批不新增 e2e 探针、不改生产默认开关；产物入库后由后续门禁扫描（A-04 域）。
