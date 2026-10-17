# P1 docstring 独立锚三臂正式批（L 轮 T5，2026-10-17 真 LLM 实跑）

> **性质**：预注册正式批执行工件（EMSE Registered Reports 口径）。
> **预注册**（结果产出前落盘，Lead 提交 `61493ce` 记录其 sha256）：
> `docs/emse/EMSE_DOCSTRING_ANCHOR_PREREG_2026-10-17.md`
> sha256=`76c7ced181ffc0f1a9d6f9e88cf45e8ee69aa5d7e63985883476d928b9259a6e`。
> 判定常量由 `experiments/emse_docstring_anchor_analysis.py` 在结果产出前入库锁定
> （0.65 成功线 / 0.55 失败线 / α=0.05 / trend 0.10），本 README 与判定报告数字
> **一律由脚本从批次 JSON 直出**，不手写。
>
> **跑批切点（干净树）**：`/Users/wangchenyu/Workspace/AITester-l-batch-61493ce`
> detached HEAD = **`61493ce86f0740d1ff4a39f0899d65bd18043367`**，
> 跑前/跑后 `git status --porcelain` 均 **0 行**（每臂 log 头/尾记录）。
> 三臂批次工件 provenance **`git_dirty=false`**、无 `dirty_reason`。
>
> **数据集/模型**：QuixBugs 50 行（41 缺陷程序 + 9 测试驱动；主分析集=41 口径）；
> deepseek-flash（三臂同批指纹 `pinned=true`，`returned_model=deepseek-flash`）。
>
> 配套：T4 验证性 pilot（同环境排雷、含 `--task-count` 缺陷立案）见
> `experiments/results/l_round_pilot_20261017/README.md`。

## 1. 跑批协议（三臂、同 seed/判分口径、逐臂独立 cache namespace）

| 项 | df（对照） | doc（处理 A） | union（处理 B，次级） |
|---|---|---|---|
| baseline | `plain_llm_df` | `plain_llm_df_doc` | `plain_llm_df_doc_union` |
| cache namespace | `emse_docstring_anchor_20261017_df` | `emse_docstring_anchor_20261017_doc` | `emse_docstring_anchor_20261017_union` |
| 批次工件 | `benchmark_quixbugs_20261017_194444.json` | `benchmark_quixbugs_20261017_193626.json` | `benchmark_quixbugs_20261017_201928.json` |
| 时间窗（本地） | 18:28:47 → 19:44:45 | 18:28:47 → 19:36:27 | 19:06:23 → 20:19:29 |
| 墙钟 | **76m08s**（4567.68s） | **67m49s**（4069.48s） | **73m06s**（4385.84s） |
| 其中任务阶段* | 1020.6s | 1407.3s | 1908.5s |
| parallelism | 4 | 4 | 4 |
| provenance git_sha / dirty | `61493ce` / **false** | `61493ce` / **false** | `61493ce` / **false** |

\* 任务阶段=run_benchmark 进度条阶段（LLM 生成/执行/判分）；墙钟余量为批后处理
（变异得分 / 变异检出 / MDO 三个逐任务串行 loop）。

共同协议（每臂）：

```bash
AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled \
BENCHMARK_PARALLELISM=4 AITESTER_CACHE_NAMESPACE=emse_docstring_anchor_20261017_<df|doc|union> \
AITESTER_BATCH_MAX_CALLS=300 COST_BUDGET_ENABLE=true COST_BUDGET_USD=5 \
/Users/wangchenyu/Workspace/AITester/.venv/bin/python experiments/run_main_batch.py \
  --dataset quixbugs --task-count 50 --seed 42 --baselines <arm> \
  --output-dir experiments/results/emse_docstring_anchor_20261017 --skip-stats
```

（`--task-count 50` = QuixBugs 全量 50 行，恰好不触发 T4 立案的
`--task-count 对非合成数据集不生效` CLI 缺陷；详见 pilot README §4。）

**调度偏差披露（Lead 批准，务必与单臂口径分开阅读）**：

- ① **df 与 doc 两臂并发执行**（两个独立进程，各 P4、互异 namespace/log）。
  理由：T4 pilot 实测 3 任务 13m13s（后处理主导），三臂全串行预计 4–6h 超预算；
  Lead 批准改为 df+doc 并发（18:28:47 同秒启动，同一窗口对对照最公平），
  union 后跑。**单臂内部协议不变**（P4/temp=0/logic/seed42/判分口径）。
- ② **union 与 df/doc 的后处理重叠**（Lead 19:00 批准）：union 于 19:06:23 启动，
  此时 df/doc 已完成任务阶段、处于批后处理（仅占 ~2–4/10 核，CPU 大量空闲）。
  理由：节省 ~40–60min；代价是 union 任务阶段与 df/doc 后处理时间窗重叠，
  可能在**次指标**（mutation_score/MDO 等变异类测量）上引入 CPU 争抢噪声。
  **主指标 detection 在任务阶段采集，不受批后处理 CPU 争抢影响**；且三臂均有
  重叠（df/doc 任务阶段互相并发 + union 与前两者后处理并发），方向不系统性
  偏向任一臂。该限制见 §7。
- ③ 三臂均未中断、未重跑、未删除任何日志/工件；后处理超时率偏高（见 §7）如实保留。

## 2. 跑批前置闸（preflight）

`/Users/wangchenyu/Workspace/AITester/.venv/bin/python scripts/tools/run_preflight.py
--expect-tasks 50 --parallelism 4`（worktree 61493ce；输出见 `preflight.log`）：

- 工作树：sha=`61493ce`，**dirty=False**；
- 孤儿进程巡检：扫描 819 进程，泄漏嵌套测试子进程 **0**；
- 告警（均已按 Lead 要求用环境变量覆盖/记录）：
  - 任务级预算未启用 → 每臂显式 `COST_BUDGET_ENABLE=true COST_BUDGET_USD=5`；
  - 批次级调用上限未配置 → 每臂显式 `AITESTER_BATCH_MAX_CALLS=300`；
  - worktree 内无历史 pinned 指纹 → 本批工件自身指纹 **pinned=true**（§5）。

锚表（预注册材料，随切点提交入库，跑批前校验在场）：

| 文件 | sha256 |
|---|---|
| `DOCSTRING_ANCHOR_TABLE.json` | `2a650afdb181cc7035745d9f6c50b105317e5e1a5268fc309b24c52f3734272d` |
| `DOCSTRING_ANCHOR_TABLE_UNION.json` | `6120ea40c7a8be47d5ed4b8456955c2bf050f49f1e8bc2f32c85089980f7a8e8` |

## 3. 结果（数字由工件复算；判定见 §4）

### 3.1 检出（41 缺陷程序口径，可判定子集）

| 臂 | detection | 可判定/41 行 | 41 口径 None | 全 50 行 None |
|---|---|---|---|---|
| df（对照） | **86.11%（31/36）** | 36/41 | 5 | 14 |
| doc（处理 A） | **60.00%（21/35）** | 35/41 | 6 | 15 |
| union（处理 B） | **61.76%（21/34）** | 34/41 | 7 | 16 |

- 全 50 行 None = 9 个测试驱动任务（detection 恒 None，口径设计）+ 已知
  "缺陷实现不终止"家族（bitcount / find_first_in_sorted / sqrt / wrap）的 M1
  不可测 + `node`（缺 human_spec 的程序）；union 臂另加
  `longest_common_subsequence`、doc 臂另加 `to_base`（均因超时门 → fail-closed
  不进分母）。**None 不参与分母**，各臂分母已在上表如实披露。
- repair / false_fix 三臂均 0（df 协议不修缺陷，仅检出）；union 臂
  `test_error_rate=2.0%`（1/50），df/doc 均 0。

### 3.2 配对对比（精确 McNemar；a=前臂 vs b=df）

| 对比 | 配对 n | a 独有 : b 独有 | δ | 单向 p | 双向 p | BF10 | MDE(80%) |
|---|---|---|---|---|---|---|---|
| **doc vs df（主）** | 35 | **3 : 12** | **−25.71pp** | 0.9963 | 0.0352 | **3.6274** | 16.57pp |
| union vs df（次级） | 34 | 1 : 9 | −23.53pp | 0.9990 | 0.0215 | 9.4961 | 16.81pp |

### 3.3 审计面（仪器/机制侧，描述性）

| 项（41 口径） | df | doc | union |
|---|---|---|---|
| `spec_replace_applied` | `none: 50`（非该臂） | **attempted_replaced 41 / attempted_fallback 9** | **attempted_replaced 41 / attempted_fallback 9** |
| specificity verdict | over_red 6 / specific_red 33 / unavailable 2 | over_red **15** / specific_red 22 / unavailable 4 | over_red **13** / specific_red 22 / unavailable 6 |
| over_red 占比（over/(spec+over)） | 15.4% | **40.5%** | **37.1%** |

- 锚命中率 100%（41/41 缺陷程序 `attempted_replaced`；9 个测试驱动任务回落，
  `node.py` 为 human_spec 空串的"键在场"命中语义）——**仪器无故障**。
- **over_red 占比方向与预注册预期相反**（预注册机制侧预期下降 ≥30%，实测
  doc/union 均上升；与 df_spec 阴性批同方向）——这是描述性 proxy，
  **不作机制证明**；严格版 misguided/effective 逐测试度量由 T2
  `experiments/misguided_metrics.py` 对本批工件另行重放（见 §8）。

## 4. 预注册判定（`DF_DOC_REPORT.json` / `.md` 直出，数字不手写）

**主判定：`verdict = not_confirmed`；`fail_line_triggered = false`。**
**次级判定（union vs df）：`not_confirmed`（预注册声明为 secondary，不参与主判定）。**

| 预注册条件（doc vs df） | 阈值 | 实测 | 满足 |
|---|---|---|---|
| C1 绝对线：doc detection | ≥ 65% | **60.00%** | ✗ |
| C2 单向 McNemar p（H2: doc > df） | < 0.05 | **0.9963** | ✗ |
| C3 方向 δ > 0 | > 0 | **−25.71pp** | ✗ |
| 失败线（独立标记） | < 55% | 60.00% | 未触发 |

**如实解读**（预注册口径）：H2（独立 docstring 锚提升检出）**未获支持**；
doc 相对 df **显著更低**（双向精确 p=0.0352、BF10=3.63，方向为负；union 同向
p=0.0215、BF10=9.50）。n=35/34 的 MDE≈16.6–16.8pp，δ≈−24~−26pp 超出 MDE，
方向证据较强；但**负向显著仍是"存在差异"的证据，不是机制证明**。与 df_spec
（Planner 锚：54.3% vs 77.8%，δ=−25.7pp）对比：**换成独立人类 docstring 锚
并未逆转负向**，方向与幅度几乎一致——这是本轮最重要的经验事实；可能解释
（供假设生成，未检验）：锚文本（Input/Output/Examples）仍不足以约束断言
规格、detection-first 协议对锚的利用方式、或任务/模型交互。**须独立预注册
再检验，不得由本批直接下因果结论。**

## 5. provenance / 完整性

每臂批次 JSON 的 `provenance` 块（键集齐全）：

| 项 | 三臂共同值 |
|---|---|
| `git_sha` | `61493ce86f0740d1ff4a39f0899d65bd18043367` |
| `git_dirty` / `dirty_reason` | **false** / null |
| `model_name` / fingerprint | deepseek-flash / **pinned=true**、`returned_model=deepseek-flash`、`missing=[]`、`alias_mismatch=false` |
| `temperature` / `profile` / `seed` | 0.0 / logic / 42 |
| `env_snapshot` | 109–111 键，含 `AITESTER_CACHE_NAMESPACE=emse_docstring_anchor_20261017_<arm>`、`AITESTER_PROFILE=logic`、`TEMPERATURE=0.0`、`LLM_THINKING_MODE=disabled`、`ENABLE_MUTATION_SCORING=true` 等 |
| 顶层 `parallelism` | 4（三臂） |

- 运行前后工作树均为 0 dirty（每臂 log 尾 `GIT_STATUS_AFTER:` 为空）。
- 输入工件 sha256 已由分析脚本写入 `DF_DOC_REPORT.json.inputs`（见 §8）。

## 6. 成本（真实 token 记账 × deepseek-flash 标准价目表，保守上界）

| 臂 | input tok | output tok | total tok | LLM calls | cache hits | cache-avoided tok | **成本（USD）** |
|---|---|---|---|---|---|---|---|
| df | 35,203 | 53,761 | 88,964 | 56 | 5 | 8,229 | **$0.0751** |
| doc | 48,430 | 86,359 | 134,789 | 65 | 15 | 29,531 | **$0.1182** |
| union | 63,965 | 87,160 | 151,125 | 64 | 21 | 52,751 | **$0.1238** |
| **合计** | **147,598** | **227,280** | **374,878** | **185** | **41** | **90,511** | **≈$0.3170** |

- 价目表：`experiments/price_table.json`（deepseek-flash：$0.3/M in、$1.2/M out，
  as_of 2026-10-06，标准价/峰时价，非错峰半价 → 结果为**上界**）。
- 与 T4 pilot/预注册估算（$0.28–0.42，上界 $0.5）一致；实际合计 **$0.317**。
- 三臂均为全新 cache namespace，批内 cache hits 为同批 LRU/文件命中（不影响
  独立样本主张：不同臂/不同任务 prompt 不共享响应；`cache_avoided_tokens` 单列）。

## 7. 异常与限制（如实披露）

1. **调度偏差**：df/doc 并发 + union 与 df/doc 后处理时间窗重叠（§1 ①②，Lead
   批准）；单臂协议不变，但**次指标（mutation_score / MDR / MDO 等变异类测量）
   的时间窗含 CPU 争抢噪声**（三臂均有重叠，方向不系统性偏向任一臂）；
   detection 主指标在任务阶段采集，不受批后处理争抢影响。
2. **批后处理耗时/超时率偏高**：三臂墙钟中后处理占比 df≈78%、doc≈65%、
   union≈56%；`mutation_testing` 30s 超时防御（有界终止，不挂死）计数
   df=68+ / doc=79+ / union=86+，另有 `m1_metrics` 60–120s、`O3 branch` 60s、
   MDO 相关 30s 超时。根因=QuixBugs 已知"缺陷实现不终止"家族
   （bitcount/find_first_in_sorted/sqrt/wrap）+ 并发跑批的机器负载；
   这直接导致部分任务 M1/变异类指标 None（分母已在 §3 如实披露），
   **不影响 detection 主指标判定**（None fail-closed 不进分母，与预注册口径一致）。
3. **`m1_metrics` 路径孤儿 pytest 泄漏复发（K-6 类，新证据）**：18:36 出现
   `ppid=1` 的 `pytest … /tmp/aitester_m1_bitcount_*/python_testcases/test_bitcount.py`
   （PID 57034，age 9m42s，持续 ~98% CPU），由某臂 m1 测量 120s 超时防御后
   子进程被 init 收养。已手动 SIGTERM/SIGKILL 清理并记录（清理前 PID/命令/
   etime 入报告）；`scripts/tools/detect_orphan_procs.py` 因 600s 最小年龄
   窗口未自动报出。跑批全程每 5min 只读巡检，记录见 `proc_hygiene.log`
   （最终巡检=无泄漏）。**建议 Lead 记入开放问题**：m1_metrics 子进程组
   清理/回收（本轮未改 src）。
4. **`test_error_rate` union 臂 2.0%（1/50）**：单任务生成测试执行错误；
   df/doc 为 0；detection 判定按 fail-closed≈None 处理（已计入分母披露）。
5. **单模型/单数据集/单 seed**：deepseek-flash + QuixBugs（仅 41 缺陷程序
   可判定子集），跨模型/跨数据集不可外推；MDE 16.6–16.8pp，小效应不可判定。
6. **既有口径**（非本轮新增）：trace 的 `task` UUID 字段被脱敏为
   `<REDACTED_KEY>`（`meta.dataset_task_id` 保留可追溯）；`env_snapshot` 未登记
   `BENCHMARK_PARALLELISM`（顶层 `parallelism=4` 已如实记录）。
7. **T4 已立案 CLI 缺陷不影响本批**：`run_main_batch --task-count` 对非合成
   数据集不生效；本批 `--task-count 50` = QuixBugs 全量 50 行，实际执行
   与计划一致（各臂批次 `total_tasks=50`、details 50 行可核）。
8. 跑批过程**未中断、未重跑、未删除/手改任何日志与工件**；无 API key 泄露
   （日志脱敏机制在岗；本报告不含密钥）。

## 8. 复现与判定命令（零 LLM 复算）

```bash
# 三条臂跑批（本批实际命令，见 §1；任一臂可独立复跑，需全新 namespace）
AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled \
BENCHMARK_PARALLELISM=4 AITESTER_CACHE_NAMESPACE=emse_docstring_anchor_20261017_<arm> \
.venv/bin/python experiments/run_main_batch.py --dataset quixbugs --task-count 50 \
  --seed 42 --baselines <arm> --output-dir experiments/results/emse_docstring_anchor_20261017 --skip-stats

# 预注册判定（零 LLM；本批实际命令）
.venv/bin/python -m experiments.emse_docstring_anchor_analysis \
  --df    experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_194444.json \
  --doc   experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_193626.json \
  --union experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_201928.json \
  --out   experiments/results/emse_docstring_anchor_20261017/DF_DOC_REPORT.json \
  --markdown experiments/results/emse_docstring_anchor_20261017/DF_DOC_REPORT.md

# 完整性
cd experiments/results/emse_docstring_anchor_20261017 && shasum -a 256 -c SHA256SUMS
```

## 9. 文件与 sha256（完整清单见 `SHA256SUMS`）

| 文件 | 说明 | sha256 |
|---|---|---|
| `benchmark_quixbugs_20261017_194444.json` | df 臂批次（50 行） | `9405176136db2c2e4e7885ca4e6a7116d1647893c31ddd0b8e76b512f1239672` |
| `benchmark_quixbugs_20261017_193626.json` | doc 臂批次（50 行） | `3e2a69896d308d389bdd35ed5ce38ae532b9accf89109b297391c265696f78b2` |
| `benchmark_quixbugs_20261017_201928.json` | union 臂批次（50 行） | `746090a277cc6a91fa12151aa1a01f4702efc5e4df1289ceb1afc18bf7e842b2` |
| `DF_DOC_REPORT.json` / `.md` | 预注册判定（脚本直出） | `de3f2023…` / `7882d2ec…`（见 SHA256SUMS） |
| `log_df.log` / `log_doc.log` / `log_union.log` | 每臂完整日志（命令/env/进度/超时门/摘要/git 前后状态） | 见 `SHA256SUMS` |
| `preflight.log` | 前置闸输出 | 见 `SHA256SUMS` |
| `proc_hygiene.log` | 跑批期每 5min 孤儿巡检记录（只读） | 见 `SHA256SUMS` |
| `traces/` ×150 | 逐任务 trace（3 臂 × 50） | 见 `SHA256SUMS` |
| `DOCSTRING_ANCHOR_TABLE(.json/_UNION.json)` | 预注册锚表（随切点提交；与主仓逐字节一致） | `2a650afd…` / `6120ea40…` |

**交接**：本批三份批次 JSON 可交给 T2（metrics-dev）做 misguided/effective
逐测试重放（预注册机制指标）；路径/sha256 见上表和 `DF_DOC_REPORT.json.inputs`。
