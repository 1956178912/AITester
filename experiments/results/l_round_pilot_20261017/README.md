# L 轮 T4 真实 LLM 链路验证 pilot（2026-10-17）

> **性质声明**：**验证性 pilot，不构成实验证据**——不进入任何论文/预注册判定语料。
> 目的：为 L 轮正式跑批（T5 docstring 锚三臂）排雷：验证真实 DeepSeek 端点连通、
> `run_main_batch`/`run_benchmark` 端到端可跑、工件结构/provenance/token 记账/
> trace/日志脱敏/cache 命名空间是否正常，并实测单任务成本/墙钟供正式批预算。
>
> 任务号：T4（L 轮）；执行：exp-runner；日期：2026-10-17。
> 目录性质：`experiments/results/**` 为 gitignored 工件区（无需/不得入库）。

## 0. 结论速览

| 项 | 结果 |
|---|---|
| 真实 LLM 冒烟 | ✅ exit 0，墙钟 1.59s，真实响应 `2`（model=deepseek-flash） |
| 配置层直连 | ✅ 真实响应 `21`，0.511s，30 in / 1 out tokens |
| 3 任务端点验证 | ✅ 3/3 任务完成、工件落盘；墙钟 **793.07s（13m13s）** |
| 工件 | `benchmark_quixbugs_20261017_182835.json`（40,553 B）+ `traces/`×3 + `pilot_runner_meta.json` + `pilot_3task.log` |
| token/成本 | 5747 tokens（in 2593 / out 3154），4 次真实调用，cache_hits=0；标准价 **$0.00456** |
| provenance | model_fingerprint **pinned=true / returned=deepseek-flash**；git_dirty=true（见 OBS-2，pilot 期间主仓被 T1 提交变更；pilot 目录 gitignored，不影响正式批） |
| 判分（M1 三指标） | 字段齐备；detection 可测 1/3=100%（bitcount 属已知"缺陷实现不终止"家族→None 不进分母；test 驱动任务 None 属预期） |
| trace | ✅ `traces/` 3 文件，事件 `task_start/node/task_end`；任务 UUID 字段被脱敏为 `<REDACTED_KEY>`（既有行为，`meta.dataset_task_id` 保留可追溯） |
| 日志脱敏 | ✅ API key 模式扫描 0 命中（`sk-…`/`api_key=…`）；本报告不含任何密钥 |
| cache 写入 | ✅ 使用全新命名空间 `l_round_pilot_r2`（0 命中=真实调用）；`~/.cache/aitester/llm` 在运行窗口有写入；**未删除任何既有缓存** |
| 真缺陷 | ⚠️ **DEF-1：`run_main_batch.py --task-count` 对非合成数据集不生效**（见 §4；T5 用 50=全量恰好不受影响） |

## 1. 冒烟与配置层直连（T4-1）

### 1.1 冒烟脚本

```bash
AITESTER_SMOKE_LLM=true AITESTER_LLM_CACHE=0 \
  .venv/bin/python experiments/run_smoke_llm.py --require-json
# EXIT=0，real 1.59s
# 响应片段：2…
# PASS：响应为合法短文本（1 字符），格式正常
```

- 真实响应 `2`（1+1 冒烟 prompt）；`--require-json` 同时通过（宽松判定：≤256 字符合法短文本）。
- 设置 `AITESTER_LLM_CACHE=0` 是为了**强制真实调用**（脚本 docstring 记录的 CI 口径），避免冒烟被历史缓存重放。

### 1.2 配置层直连（临时探针，不落库）

临时脚本 `/tmp/l_round_llm_probe.py`（5 行核心：`config.LLM_CONFIGS` → `BaseAgent._call_llm`）；
输出仅含模型名/端点，**不含 key**（key 仅在进程内存，未打印）：

```
LLM_CONFIGS count: 1
  [0] model=deepseek-flash base_url=https://api.deepseek.com/v1 key_present=True
elapsed_seconds: 0.511
response: '21'
usage_after: TokenUsage(input_tokens=30, output_tokens=1, total_tokens=31, llm_calls=1, cache_hits=0)
```

- 走项目既有 `openai` 兼容链路（`requests` 栈），**无需改动代码**；系统 urllib 默认证书环境问题不触发。
- 模型名 `deepseek-flash`，真实 completion 正常（往返 <1s，思考模式由 `LLM_THINKING_MODE=disabled` 关闭）。

## 2. 3 任务端点验证（T4-2，pilot 本体）

### 2.1 协议（含 DEF-1 workaround，如实记录）

任务书命令（`run_main_batch.py --dataset quixbugs --task-count 3 …`）实测**不生效**：
见 §4 DEF-1，会跑满 50 任务。首次启动后 3 分钟实测进度 7/50、已落 9 条 trace，
为避免烧配额/占用跑批窗口，于 18:15 终止该误跑（**日志与部分 trace 保留**在
`defect_repro/`，见 §2.5），随后用**等价 workaround** 完成真正的 3 任务 pilot：

- 驱动：`/tmp/l_round_pilot_runner.py` → 直接调用
  `experiments.run_benchmark.run_benchmark(dataset_name="quixbugs", baselines=["plain_llm_df"],
  task_limit=3, seed=42, deterministic=True, dirty_reason="L-round pilot validation (workaround: …)")`
  （与 `run_main_batch.main()` 同一引擎/同一默认确定性协议；并复用其
  `_assert_provenance_dirty` + `_print_r4_summary` 收尾）。
- 等价性：`run_main_batch.py` 是薄壳（`_check_repo_clean` + 透传 + 摘要），
  `task_limit` 是引擎既有的**正确**限任务参数（`run_benchmark.py:3489-3491`）。

| 项 | 值 |
|---|---|
| 环境 | `AITESTER_PROFILE=logic` / `TEMPERATURE=0.0` / `LLM_THINKING_MODE=disabled` / `BENCHMARK_PARALLELISM=2`（工件顶层 `parallelism=2` 记录） / `AITESTER_CACHE_NAMESPACE=l_round_pilot_r2` |
| 数据集 | QuixBugs，`task_limit=3`，seed=42（按数据集顺序 = bitcount / breadth_first_search / breadth_first_search_test） |
| 耗时 | **793.07s**（任务阶段 7m07s + 批后处理 ≈6m） |
| 启动时 git | sha=8d4f35c（主仓），dirty=0 |
| 工件时间戳 | 2026-10-17 18:28:35（本地） |
| 真实调用 | 4 次（0 cache hits，0 cache-avoided tokens） |

### 2.2 工件与实测数字

`benchmark_quixbugs_20261017_182835.json`（`sha256=35f9f651…`）：

| 任务 | detection | repair | false_fix | tokens | calls | elapsed(s) | 备注 |
|---|---|---|---|---|---|---|---|
| `quixbugs__breadth_first_search` | **1.0** | 0.0 | 0.0 | 2963 | 2 | 13.18 | 正常检出 |
| `quixbugs__breadth_first_search_test` | None | None | None | 1613 | 1 | 7.13 | 测试驱动任务，预期 None |
| `quixbugs__bitcount` | None | 0.0 | 0.0 | 1171 | 1 | 95.44 | 已知"缺陷实现不终止"家族：O3 branch/mutation 30–120s 超时门 → M1 不可测（负向防御正常生效，不挂死） |

- **M1 三指标**：可测 1/3；detection(可测)=100%（1/1），repair=0%，false_fix=0%；
  批摘要另打印 `success=0.0% (有效 3/3, harness_invalid=0)`、regression/test_error 0%。
- **token 记账**：`total_input_tokens=2593`、`total_output_tokens=3154`、
  `total_llm_calls=4`、`total_cache_hits=0`、`avg_tokens_per_task=1915.67`、
  `cache_hit_rate_pct=0.0`（全新 namespace 下为**真实独立调用**）。
- **成本（deepseek-flash 标准价 input $0.3/M · output $1.2/M，保守上界）**：
  2593×0.3/M + 3154×1.2/M = **$0.00456 / 3 任务**（≈$0.00152/任务；按同 token
  结构外推 50 任务 ≈ $0.076，与历史 df 臂工件 $0.078 一致）。
- **provenance**（键集齐全：`git_sha/git_dirty/dirty_reason/model_name/
  model_fingerprint/temperature/profile/env_snapshot/cache_namespace/seed/…`）：
  - `model_fingerprint = {requested_alias: deepseek-flash, returned_model: deepseek-flash,
    system_fingerprint: e72d3c7f…, probe_sha256: fc3d9159…, pinned: true, missing: [],
    alias_mismatch: false}`（S29 指纹锁定 ✅）；
  - `git_sha=61493ce`、`git_dirty=true`、`dirty_reason="L-round pilot validation (workaround: …)"`
    —— 见 OBS-2：运行期间主仓被 T1 提交（8d4f35c→61493ce），provenance 在**批次结束时**
    采集 git 状态，故记 end-state；`dirty=true` 如实暴露来源，pilot 结论不依赖该 sha；
  - `env_snapshot` 111 键，含 `AITESTER_PROFILE=logic / TEMPERATURE=0.0 /
    LLM_THINKING_MODE=disabled / AITESTER_CACHE_NAMESPACE=l_round_pilot_r2 /
    ENABLE_MUTATION_SCORING=true`（后者解释了长后处理）。
- **trace 落盘**：`traces/` 3 个 JSONL（`<task>_<baseline>_<epoch>.jsonl`），事件
  `task_start/node/task_end`；节点含 generator/executor 输出长度、时间戳、run_id/span_id。
  trace 的 `task` UUID 字段被日志脱敏规则（`src/utils/logging_utils.py:21` 长 hex 规则）
  替换为 `<REDACTED_KEY>`——**既有行为**（上一批 emse_df_spec_20261016 同样），
  `meta.dataset_task_id` 保留，可追溯，非本轮新缺陷。
- **日志脱敏**：对 `pilot_3task.log` 与 `defect_repro/aborted_full50_run.log` 做
  `sk-[A-Za-z0-9]{10,}|api_key=[A-Za-z0-9]{8,}` 扫描 = **0 命中**；本报告不含密钥。

### 2.3 批后处理耗时披露（对正式批墙钟有直接影响）

任务阶段仅 7m07s，但**批后处理 ≈6m**：`mutation_testing`（每任务/每变异体）、
`m1_metrics`、`mdo`（变异检测）在非终止缺陷程序上连续命中 30s/60s/120s 超时门
（有界防御，均已"已终止整个进程组并返回"，不挂死）。pilot 期间另有队友进程争抢
CPU（10 核机器上多个 pytest 满核运行），超时门命中率被放大。→ 正式批应
在 CPU 让出窗口跑（Lead 已通知其他队友让出），且该后处理是墙钟而非 token 成本。

### 2.4 异常清单（pilot 暴露）

| # | 类型 | 描述 | 影响 | 处置 |
|---|---|---|---|---|
| DEF-1 | **真缺陷** | `run_main_batch.py --task-count` 对非合成数据集不生效：`--task-count 3` 仍跑满 50 | 小批演练/省钱跑批会被误放大 16×；T5 因 50=全量未受影响 | 已立案（§4），**未改源码**，待 Lead 分派；T5 用 `--task-count 50` 恰好安全 |
| OBS-1 | 环境 | 队友并行重载 + 非终止缺陷家族 → 后处理超时门密集触发（30–120s），pilot 后处理 6m | 墙钟拉长；判分 None 增加（M1 分母缩小），**非能力失败** | 正式批前主机已让出 CPU；跑后 `detect_orphan_procs.py` 巡检 |
| OBS-2 | 记账观察 | provenance `git_sha`/`dirty`/`probe_at` 在**批次结束时**采集：pilot 运行中主仓 HEAD 从 8d4f35c → 61493ce，工件记 end-state+dirty=true | 不能证明"跑批全程代码态" | 正式批在**干净 detached worktree（61493ce，dirty=0）**跑，`git_dirty=false` 门禁 + 跑前/跑后 git 状态入 log（T5 已按此执行） |
| OBS-3 | 既有 | trace `task` UUID 被脱敏为 `<REDACTED_KEY>` | 直接看 trace 需用 `dataset_task_id`；非新缺陷 | 记录，不在本轮修改 |
| OBS-4 | 极小 | `env_snapshot` 未登记 `BENCHMARK_PARALLELISM`（顶层 `parallelism=2` 已如实记录） | 无（以顶层为准） | 记录 |
| OBS-5 | 运行卫生 | 首次误跑（DEF-1）被杀后，其子进程 2 个（`test_mutant.py`/branch coverage）被 init 收养、各 100% CPU 存活 13min | 污染 host CPU，可能放大后续超时 | 已用 `detect_orphan_procs.py` 定位 + 手动 SIGTERM/SIGKILL 清理（清理前已记录 PID/命令/age）；正式批跑后巡检 |

### 2.5 DEF-1 证据（误跑 50 任务的 aborted 证据，只读保留）

`defect_repro/`：

- `aborted_full50_run.log`（5,300 B）：命令/环境/进度条 `7/50`、`--task-count 3` 却跑 50 的实测日志；
- `traces_partial_aborted/` 9 个 trace（18:11–18:14），任务集合 `bitcount / breadth_first_search(_test) / bucketsort / depth_first_search(_test) / detect_cycle(_test) / find_first_in_sorted`——证明不止 3 个任务被执行。

## 3. 正式批（T5）成本/墙钟估算（基于 pilot 实测 → 供 Lead 调度）

pilot 单任务 ≈1,916 tokens / ≈$0.00152（标准价）；历史同族工件提供 50 任务/臂口径：

| 臂 | 历史/外推 token（50 任务） | 标准价成本 | 墙钟参考（单臂 P4） |
|---|---|---|---|
| `plain_llm_df`（对照） | 33,188 in / 56,890 out（emse_df_spec_20261016 df 臂实测） | **≈$0.078** | 1h08m（含变异后处理） |
| `plain_llm_df_doc`（docstring 锚） | 介于 df 与 df_spec；预估 +20~60% prompt | **≈$0.10–0.15** | 1h08m–1h15m |
| `plain_llm_df_doc_union`（doc∪Planner） | 接近 df_spec（59,210 in / 103,794 out 实测口径的上限） | **≈$0.12–0.18** | 1h08m–1h20m |
| **三臂合计** | — | **≈$0.28–0.42（上界 $0.5，与预注册 §5 一致）** | 顺序 ≈3.5–4h；df+doc 并发 + union 串行 ≈2.5–3h |

建议（已与 Lead 调度对齐）：① df 与 doc 并发（各 P4、互异 namespace，同批同日对对照最公平），
union 后跑；② 每臂 `AITESTER_BATCH_MAX_CALLS=300` + `COST_BUDGET_ENABLE=true` +
`COST_BUDGET_USD=5` 任务级止损；③ 并行度维持 4（如观测到超时门命中率显著高于历史，
降级单臂串行）；④ 成本以工件 token 记账为准，不手写。

## 4. DEF-1 缺陷报告（最小复现，未修源码）

**标题**：`run_main_batch.py --task-count` 对非合成数据集静默不生效（真实数据集跑满全量）

- **位置**：
  - `experiments/run_main_batch.py:306`：`task_count=args.task_count`（CLI 唯一暴露的任务数参数）；
  - `experiments/run_benchmark.py:3309`（`if dataset_name in ("synthetic", "synth"): tc = task_count or 60`）
    → `task_count` **仅**用于 synthetic 数据集合成；
  - `experiments/run_benchmark.py:3489-3491`：真正的限任务参数是 `task_limit`
    （`if task_limit: tasks = tasks[:task_limit]`），而 `run_main_batch` 未暴露该 CLI；
  - `experiments/run_benchmark.py:4105`（CLI `--task-count` help "合成数据集任务数量"、
    `--task-limit` help "限制运行任务数量"）证明语义分工早已存在，`run_main_batch` 透传错参数。
- **最小复现**（真实 LLM 最小成本；或直接看 §2.5 evidence）：
  ```bash
  AITESTER_CACHE_NAMESPACE=def1_repro .venv/bin/python experiments/run_main_batch.py \
    --dataset quixbugs --task-count 3 --seed 42 --baselines plain_llm_df \
    --output-dir /tmp/def1_repro --skip-stats --allow-dirty --dirty-reason "DEF-1 repro"
  # 观察 1：tqdm 总数为 50（0/50）而非 3；观察 2：>3 个任务落 trace
  ```
- **原始证据**：`defect_repro/aborted_full50_run.log`（`7/50`）+ 9 条 trace（§2.5）。
- **影响面**：
  - 用 `--task-count N`（N<全量）做"小批演练/省钱验证"会静默跑全量 → 配额/时间放大；
  - 历史 df_spec 批用 `--task-count 50`（=QuixBugs 全量），**未受影响**；T5 同（50=全量）；
  - 工件 `total_tasks` 会如实记录实际任务数，不会伪造；问题在**执行成本**与 CLI 契约。
- **建议修复（供 Lead 分派，本轮不动源码）**：`run_main_batch.py` 增加
  `--task-limit` 并透传 `rb.run_benchmark(task_limit=…)`（或将 `--task-count` 在非
  synthetic 数据集上映射为 `task_limit` 并更新 help/文档）；补测试锁定
  "`--task-count 3` + quixbugs → 恰好 3 任务"。
- **T4 处置**：pilot 改用引擎既有 `task_limit=3`（§2.1 workaround），未改 `src/`，
  未改冻结实验文件；正式批命令保持 `--task-count 50`（正确语义=全量）。

## 5. T4 交付脚本：`experiments/run_docstring_anchor_batch.sh`

（位于主仓工作树，**未 commit**——由 Lead 统一提交；worktree 61493ce 内无此文件。）

- 用途：T5 三臂**可复现顺序入口**（df → doc → union，每臂独立 namespace、
  输出 `experiments/results/emse_docstring_anchor_20261017/`、每臂 log、末调 T1
  分析脚本、成本/墙钟汇总、`RUN_MANIFEST_*.json` + `SHA256SUMS`）。
- 已实现：`set -euo pipefail`；`--dry-run`（已实测）；干净树门禁；
  `run_preflight.py --strict`（等价 `make preflight`）；锚表在场/构建检查；
  run_benchmark 臂注册 + T1 分析脚本存在性检查；时间戳文件名不覆盖既有工件；
  每臂 `git status`/`rev-parse` 入 log；跑后 `detect_orphan_procs.py`（只读）；
  成本汇总（读价目表，不编造）；分析 CLI `--df/--doc/[--union]/--out/--markdown`。
- **与 T5 实际调度的偏差（如实记录）**：Lead 因 pilot 实测（3 任务 13m，串行
  三臂 4–6h 超预算）调整为 **df+doc 并发 + union 后跑**；脚本默认仍为顺序三臂，
  正式批以 T5 手动并发命令为准（本 README 与 T5 README 均披露该调度偏差）。
- 脚本头 KNOWN BUG 段已记录 DEF-1，明确"`--task-count <50` 不得用于省钱小批"。

## 6. 文件清单与 sha256

| 文件 | 说明 | sha256 |
|---|---|---|
| `benchmark_quixbugs_20261017_182835.json` | pilot 批次工件（3 任务 + provenance） | `35f9f6518e8333168885a007b399600132dcf821db28ef2a5174747699048af3` |
| `pilot_3task.log` | pilot 完整日志（命令/env/进度/超时门/摘要） | `1434e495171c2a3c2954b74f454e752d024f43eb52bf424c7fa7024cbcb3b991` |
| `pilot_runner_meta.json` | workaround 驱动元数据（引擎调用方式） | `035694ce19845f5829e20a897ddecf5ae5779a68f00382d8afd6a6b65ca7e2f7` |
| `traces/*.jsonl` ×3 | 逐任务 trace（task_start/node/task_end） | 见 `SHA256SUMS` |
| `defect_repro/aborted_full50_run.log` | DEF-1 证据：误跑 50 的日志 | `235ad982aea99b79229b7d565c4e7ae5d9200d6bb5ba2c3dd5210b3ac270f228` |
| `defect_repro/traces_partial_aborted/` ×9 | DEF-1 证据：误跑产生的前 9 条 trace | 见 `SHA256SUMS` |
| `SHA256SUMS` | 本目录工件校验 | — |

复现 pilot（成本 ≈$0.005）：
```bash
AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=2 \
AITESTER_CACHE_NAMESPACE=l_round_pilot_r2 .venv/bin/python /tmp/l_round_pilot_runner.py
# /tmp 驱动未入库；等价命令（分析/复跑用，任务数取引擎 task_limit 语义）：
# .venv/bin/python -c 'import experiments.run_benchmark as rb;
#   rb.run_benchmark(dataset_name="quixbugs", baselines=["plain_llm_df"],
#     output_dir="experiments/results/l_round_pilot_20261017", task_limit=3,
#     seed=42, parallel=2, deterministic=True)'
```
