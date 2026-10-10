# E6 control + A1 消融批次入库（2026-10-09）

> 本目录为 **2026-10-09 实跑两批**的归档副本。入库前原始工件位于 `/tmp`
> （易失、未入库、无 SHA256SUMS），违反预注册"全部工件入 git 白名单"条款。
> 本目录为其归档，`SHA256SUMS` 覆盖全部 **352** 个文件
> （2 批次 JSON + 351 逐任务 trace + 跑批日志）。
>
> **执行授权**：用户于 2026-10-09 明确授权使用其 DeepSeek-flash 预算执行
> 审查报告 §11 中此前受阻的实验。

## 批次清单与 provenance

| 目录 | 批次 JSON | 数据集 | 臂 | seed | n | profile | thinking | 模型 | git_dirty |
|------|-----------|--------|----|------|---|---------|----------|------|-----------|
| `e6_control_seed42/` | `benchmark_synthetic_20261009_181758.json` | synthetic | aitester / plain_llm / plain_llm_df | 42 | 87 | logic | disabled | deepseek-flash | **True** |
| `a1_strip_seed42/` | `benchmark_synthetic_20261009_180655.json` | synthetic | aitester（+`PLAN_STRIP_EXPECTED_OUTPUT_ENABLE=true`） | 42 | 87 | logic | disabled | deepseek-flash | **True** |

**共同协议**：`TEMPERATURE=0.0`（确定性协议）、`--max-pattern-repeat 2`、
`BENCHMARK_PARALLELISM=4`、LLM 缓存开启（namespace `seed42`）、
**`LLM_THINKING_MODE=disabled`**（与 E2 及 E6 预注册预算口径一致，
`docs/preregistration.md:96`）、`--allow-dirty`（同 R-P0-2 `b533cff` 先例）。

## 结果摘要

### A1 消融（先声明后取数，声明见 `docs/preregistration.md`）

| 指标 | aitester standard（control 批） | aitester STRIP（本批） |
|---|---|---|
| detection | **8/87 = 9.2%** | **8/87 = 9.2%** |
| repair | 19/87 = 21.8% | 19/87 = 21.8% |
| false_fix | 67.8% | 69.0% |

配对 McNemar：b=1、c=1、不一致对 **2**，χ²（连续性校正）= **0.500**，
精确二项双尾 **p = 1.0000**，**δ = +0.0pp**。
→ **H-A1 不成立**（剥除 Planner 的 `expected_output` 不改变检出）。

**重要限定（须并列披露）**：本批**34/87（39%）任务**触发
`Planner 输出结构不完整，使用默认计划`，此时 `test_cases = []`、`logic_degraded=True`
——**空 `test_cases` 无 `expected_output` 可剥，干预结构性空转**。
故本实验效力范围是剩余 **61%** 任务；在该范围内仍为零效应。

### E6 control（−28pp 第三次独立复现）

| 臂 | detection | repair | false_fix |
|---|---|---|---|
| aitester | 8/87 = **9.2%** | 19/87 = 21.8% | 67.8% |
| plain_llm_df | 30/87 = **34.5%** | 0/87 = 0.0% | 3.4% |
| plain_llm | 0/87 = **0.0%** | 0/87 = 0.0% | 90.8% |

配对 McNemar（aitester vs plain_llm_df）：b=24、c=2、不一致对 26，
**χ² = 16.962**，**δ = −25.3pp**。方向与量级复现 R-P0-2（δ=−0.279）与 E2（δ=−0.3673）。

## 已知偏差与缺陷（如实登记，不得掩盖）

| # | 项 | 证据 | 影响 |
|---|---|---|---|
| **D1** | **Planner 39% 回退空计划** | 34/87 次 `Planner 输出结构不完整，使用默认计划`；真 plan `test_cases` 长度 0 | Generator 近四成任务无计划；**never-red 最强候选真因** |
| **D2** | **缓存命中不计 token** | `src/agents/base_agent.py:437`（文件缓存命中）/`:389`（LRU 快路径）提前 `return`，绕过 `record_usage` | `plain_llm`/`plain_llm_df` 两臂 **0/87 行**有 token；aitester 仅 37/87。**E6 matched-cap 无分母 → E6 不可执行** |
| **D3** | **消融开关未入 provenance** | `a1_strip_seed42` 工件 `env_snapshot` **无** `PLAN_STRIP_EXPECTED_OUTPUT_ENABLE` 键（白名单未含） | 消融臂可复现性证据缺失，须补白名单 |
| **D4** | 脏树跑批 | 两批 `git_dirty=True`（`--allow-dirty`，reason 已写入 provenance） | 与 R-P0-2 同先例；代码状态含 R2–R5 未提交改动 |

## 复现命令

```bash
# E6 control（三臂）
AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled \
BENCHMARK_PARALLELISM=4 \
.venv/bin/python experiments/run_main_batch.py \
  --dataset synthetic --task-count 87 --seed 42 \
  --baselines aitester,plain_llm,plain_llm_df \
  --max-pattern-repeat 2 --skip-stats \
  --allow-dirty --dirty-reason "E6 control batch (seed42)" \
  --output-dir <out>

# A1 消融（单臂 + 剥除开关）
PLAN_STRIP_EXPECTED_OUTPUT_ENABLE=true \
AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled \
BENCHMARK_PARALLELISM=4 \
.venv/bin/python experiments/run_main_batch.py \
  --dataset synthetic --task-count 87 --seed 42 --baselines aitester \
  --max-pattern-repeat 2 --skip-stats \
  --allow-dirty --dirty-reason "A1 ablation arm (seed42)" \
  --output-dir <out>
```

## 校验

```bash
cd experiments/results/e6_a1_batches && shasum -a 256 -c SHA256SUMS
```

---

## 追加：E6 两阶段实跑（2026-10-09 晚）

### 目录

| 目录 | 批次 JSON | 臂 | 说明 |
|---|---|---|---|
| `e6_phase1_standard_coldcache/` | `benchmark_synthetic_20261009_190234.json` | aitester / plain_llm / plain_llm_df | **冷缓存**（`AITESTER_LLM_CACHE=0`）取得**完整** token 记账 87/87 三臂 |
| `e6_phase2_matched_coldcache/` | `benchmark_synthetic_20261009_191716.json` | aitester / plain_llm_df | matched 两臂，cap 经 `--per-task-token-caps` 注入 |

**为何用冷缓存**：`src/agents/base_agent.py:339` 自述"缓存命中…不再消耗 token——历史
口径保持。**正式实验须显式 `AITESTER_LLM_CACHE=0`**"。热缓存批次因此 token 记账
不完整（control 批 df 臂 0/87），无法用于 matched cap 推导。

### 四臂结果

| 臂 | detection | token/task | `token_budget_capped` | 主要 stop_reason |
|---|---|---|---|---|
| aitester standard | 6/87 = **6.9%** | **8,857** | 0/87 | test_passed 72 |
| aitester MATCHED（cap 2,586） | 2/87 = **2.3%** | 3,735 | **87/87** | **budget_exceeded 84** |
| df standard | 27/87 = **31.0%** | **2,586** | 0/87 | test_passed 42 |
| df MATCHED（cap 8,857） | 23/87 = **26.4%** | **2,602** | 1/87 | test_passed 47 |

### 判定：预算混杂假说被证否

1. **df 抬预算 → 不消费**：2,586 → 2,602 tok（几乎不变），检出无显著变化
   （−4.6pp，McNemar p=0.2888，贝叶斯 P(|δ|≤ROPE)=0.578）；
2. **aitester 压预算 → 更差**：6.9% → 2.3%，87/87 行触顶（84 行以
   `budget_exceeded` 停止）；
3. 故 **−28pp 不可由预算分配解释，归因编排结构**——**ADR-0016 结论加固**。

### 限定（必须并列）

- aitester(matched) 的 cap（2,586）**低于其单任务实际需求**（84/87 行提前终止），
  该臂测的是"**预算不足时编排的表现**"，**非严格等能量的公平对比**；
- 严格等能量口径仍需一条"预算充足但总量不超 df"的臂，本次未做；
- 协议：logic 档 / 双门 / `TEMPERATURE=0` / `LLM_THINKING_MODE=disabled` /
  seed 42 / n=87 / `--max-pattern-repeat 2` / `git_dirty=true`（`--allow-dirty`）。

### SHA256SUMS

本目录 `SHA256SUMS` 覆盖全部 **792** 个文件（含 phase1/phase2 的 XML/JSON/trace/日志）。

---

## 追加：RT1 采样控制臂（2026-10-09 晚）

| 目录 | 批次 JSON | 臂 | 开关 |
|---|---|---|---|
| `rt1_no_reinforcement_seed42/` | `benchmark_synthetic_20261009_193509.json` | `plain_llm_df` | **`DETECTION_FIRST_SECTION_ENABLE=false`** |

**目的（红队 RT1）**：df 臂首轮全绿时**必然再生成一次**，`plain_llm` 只生成一次——
"+43pp 协议效应"可能只是"多一次采样"。本臂**保留再生成路由、关闭强化 prompt 段落**，
从而分离两个变量。

**三臂对照（同为冷缓存、seed42、n=87、logic 档、thinking disabled）**

| 臂 | 再生成 | 强化段 | detection | token/task | 再生成行数 |
|---|---|---|---|---|---|
| `plain_llm` | ❌ | — | 9/87 = **10.3%** | 1,257 | 0/87 |
| **RT1** | ✅ | ❌ | 10/87 = **11.5%** | 2,368 | 77/87 |
| `plain_llm_df` | ✅ | ✅ | 27/87 = **31.0%** | 2,586 | 76/87 |

**判定：红队 RT1 假说被证否**

| 对比 | 差值 | McNemar |
|---|---|---|
| RT1 vs `plain_llm`（再生成本身） | **+1.1pp** | 不一致对 **1**，p=**1.0000** |
| df vs RT1（强化段净效应） | **+19.5pp** | 不一致对 17，χ²=**15.059**，p=**0.0001**，δ=+0.1868 |

→ **"多一次采样"几乎不贡献检出；+43pp 确证来自检出优先提示协议本身。**
与 A1（编排侧 `expected_output` 剥离）**零效应**形成对照：
**增益在提示协议层，不在编排层，也不在采样次数层。**

## 全部四批汇总

| 批次 | 目录 | 用途 |
|---|---|---|
| E6 control（热缓存） | `e6_control_seed42/` | A1 对照 + −28pp 复现 |
| A1 消融 | `a1_strip_seed42/` | plan 去 `expected_output`（**零效应**） |
| E6 phase1（冷缓存） | `e6_phase1_standard_coldcache/` | 完整 token 记账 → matched cap |
| E6 phase2（冷缓存） | `e6_phase2_matched_coldcache/` | 预算匹配四臂（**预算混杂证否**） |
| RT1（冷缓存） | `rt1_no_reinforcement_seed42/` | 采样 vs 协议（**协议确证**） |

`SHA256SUMS` 覆盖全部 **881** 个文件。
