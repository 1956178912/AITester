# PREREG — T2/B1：RT1 协议文本消融的指纹级复现（3 格 × 2 seed，真 LLM）

> **冻结声明**：本文件在**任何本批真实 LLM 调用发生之前**写成并冻结（冻结时刻见文末「冻结与哈希」；PREFLIGHT.json 记录其 sha256）。冻结之后**不得修改判定规则、停止规则、格子定义与 seeds**。若跑后发现设计缺陷，只能如实报告并标注"探索性"，不得改判。
>
> 本预注册是 2026-10-09 已执行 RT1 采样对照（`experiments/results/e6_a1_batches/rt1_no_reinforcement_seed42/`）的**指纹级、可引用复现**。与旧批的关键差别：①新切点干净树、`git_dirty=false`；②工件含 `model_fingerprint`（旧批无此键）；③按 3 格 × 2 seed 重跑，而非旧批的单 seed 单格。

## 1. 切点与工作树（跑前已核验）

| 项 | 值 |
|---|---|
| 切点 sha | `a93c1f60ee31b9582e0146f73e3038e6ce0f01a1`（= 2026-10-18 T 轮主仓 HEAD） |
| 主仓 | `/Users/wangchenyu/Workspace/AITester` |
| 跑批工作树 | `/Users/wangchenyu/Workspace/AITester-t-b1-a93c1f6`（`git worktree add --detach`） |
| 工作树洁净要求 | 跑前/跑后 `git status --porcelain` 均为空；真实模式启动前强制校验 HEAD==切点 sha 且 dirty=0 |
| 敏感配置 | 主仓 `.env`、`.env.local`（gitignore，不入清单）复制进工作树；**不打印、不提交、不写入任何工件**。provenance 的 `valid_apis[].key` 由既有代码脱敏为 `<REDACTED>` |
| 代码修改 | **无**。工作树与切点逐字节一致（本批不新增/不改任何生产源码或文档） |

## 2. 研究问题与三格设计

**研究问题**：RT1 消融要分离的两个效应——(a)「检出优先强化提示段落的**协议文本净效应**」与 (b)「首轮全绿时**多一次采样/再生成的效应**」——在干净切点、指纹在案的条件下能否复现？

干预实现（`src/graph/nodes.py`，本切点）：
- `DETECTION_FIRST_ENABLE`（df 臂线程级覆盖 true）= 路由 + 再生成计数 + 强化段落三合一；
- `DETECTION_FIRST_SECTION_ENABLE`（env，默认 true）= **只控制提示词段落**，不控制路由；置 false 时再生成路由与 `regeneration_count` 计数照旧（`_detection_first_section()` 返回 None；`_detection_first_regenerate_entry()` / `_should_debug` 的 `detection_first_all_green` 分支不受影响）。

**三格（每 seed 独立跑，同一运行协议，仅 `--baselines` 与一个 env 开关不同）**：

| 格 | `--baselines` | 再生成路由 | 强化段落 | 语义 |
|---|---|---|---|---|
| **C1** | `plain_llm` | 无 | 无（结构上不可达） | 纯单次生成基线（"无强化、无再生成"） |
| **C2** | `plain_llm_df` + `DETECTION_FIRST_SECTION_ENABLE=false` | 有 | **无** | RT1 臂（"有再生成、无强化段落"）——即 2026-10-09 旧批口径 |
| **C3** | `plain_llm_df`（默认 section=true） | 有 | **有** | 全协议（"有再生成、有强化段落"） |

语义对照：
- **文本净效应** = C3 − C2（两者路由/计数一致，唯一差别 = 强化段落文本）；
- **多一次采样效应** = C2 − C1（C1 无再生成；C2 首轮全绿会再生成一次，受 `MAX_REGENERATIONS` 上限保护）。

## 3. 数据、seeds 与运行命令

- 数据集：`synthetic`；`--task-count 87 --max-pattern-repeat 2`（与旧批同口径，87 = 旧批分母）。
- seeds：`42`、`44`（每 seed 独立跑三格；seed 只作用于任务采样与缓存命名空间，不传 LLM API——`experiments/run_benchmark.py` 既有语义）。
- 每格每 seed 一条命令（cwd = 跑批工作树，用主仓 venv 解释器）：

```bash
/Users/wangchenyu/Workspace/AITester/.venv/bin/python -m experiments.run_benchmark \
  --dataset synthetic --task-count 87 --max-pattern-repeat 2 \
  --seed <42|44> --baselines <plain_llm|plain_llm_df> \
  --output-dir /Users/wangchenyu/Workspace/AITester/experiments/results/t_round_b1_protocol_text_20261018/staging/<cell>_seed<seed>
```

**共享 env（6 跑全同）**：

```
AITESTER_PROFILE=logic
TEMPERATURE=0.0
LLM_THINKING_MODE=disabled
BENCHMARK_PARALLELISM=4
AITESTER_LLM_CACHE=0
AITESTER_CACHE_NAMESPACE=t_b1_<cell>_<seed>   # 每跑独立命名空间
COST_BUDGET_ENABLE=true
COST_BUDGET_TOKENS=200000                     # 单任务 token 硬上限（约 77× 实测均值，护栏性质）
COST_BUDGET_USD=1.0                           # 单任务费用硬上限（护栏性质）
AITESTER_BATCH_MAX_CALLS=4000                 # 批次级调用上界（估算 87×4.3×1.5≈562 ≪ 4000）
AITESTER_BATCH_MAX_USD=2.0                    # 批次级费用上界（每跑独立估值远低于此）
AITESTER_TRACE_DIR=<OUT>/traces/<cell>_seed<seed>   # 追踪落主仓结果目录（跑批工作树之外，保持 worktree clean）
```

**格间唯一差异**：C2 额外 `DETECTION_FIRST_SECTION_ENABLE=false`；C1 用 `--baselines plain_llm`（该臂 `build_workflow(planner=False, debugger=False)`，结构上无再生成路由，`DETECTION_FIRST_SECTION_ENABLE` 取值对其无影响，故与 C3 同 env）。

## 4. 指标定义（跑前冻结）

**主口径 = 行级 `detection_rate`**（既有 M1 口径，与旧批/BASELINE 完全一致）：

- 可测行：`detection_rate` 为数值（0 或 1）的行；`None` **不进分母**（与既有 M1 一致）。
- 检出：`detection_rate >= 1.0`。
- 臂级检出率 = 检出数 / 可测行数；分母随格报告（不假设三格分母相同）。
- **并列报告** `llm_suite_detection_rate`（若工件存在该字段，同口径计算），作为第二口径；主判据只用 `detection_rate`。

**配对**：同 seed 内按 `task_id` 精确配对；C1/C2/C3 的 `task_id` 集合必须完全相同（GATES 硬检查），否则只在交集上配对并在分析中披露。

**McNemar 精确检验（双侧）**：配对 2×2 表，`b` = 高检出格检出/低检出格未检出，`c` = 反向；`n=b+c`；
`p = min(1.0, 2 * Σ_{k=0}^{min(b,c)} C(n,k) / 2^n)`（`math.comb` 手算，零依赖；n=0 → p=1.0）。
方向定义：文本效应比较 C3 vs C2（高 = C3），采样效应比较 C2 vs C1（高 = C2）。

**配对 bootstrap（敏感性，非主判据）**：按任务重采样 10 000 次（固定种子 20261018），按任务自身的可测掩码重算两格率，取 Δ_pp 的 2.5/97.5 百分位为 95% CI。

**其他并列读数**：tokens（`token_metrics`，输入/输出/总计）、费用（`experiments/price_table.json` deepseek-flash 标准价 0.3/1.2 USD/Mtok，上界口径）、墙钟（每跑 log 内 start/end）、`regeneration_count` 行数分布、`stop_reason` 分布、`pass`（success_rate）、`detection_first_red_seen`/`detection_first_status` 分布。

## 5. 判定规则（跑前冻结，不得事后改动）

### H-text（主判据）：「协议文本净效应」复现

- 逐 seed 计算 `Δ_text_pp = (C3 检出率 − C2 检出率) × 100`。
- **复现（方向）** = `Δ_text_pp > 0` 在 **2/2 seeds** 成立。
- **强证据** = 复现（方向）成立且 **≥1 个 seed** 的 C3-vs-C2 McNemar 双侧 `p < 0.05`。
- 判定枚举：`replicated_strong`（2/2 方向 + ≥1 seed p<0.05）/ `replicated_direction_only`（2/2 方向、无 seed 显著）/ `not_replicated`（任一 seed Δ≤0）。

### H-sampling（辅助判据）：「多一次采样效应可忽略」

- 逐 seed 计算 `Δ_sampling_pp = (C2 检出率 − C1 检出率) × 100`。
- **可忽略** = 每 seed `|Δ_sampling_pp| ≤ 5.0` **且** 该 seed C2-vs-C1 McNemar 双侧 `p ≥ 0.05`。
- 判定枚举：`sampling_effect_negligible`（2/2 seeds 满足）/ `sampling_effect_not_negligible`（至少 1 seed 不满足；如实报告方向与幅度）。

### 联合 verdict（供 Lead 引用；不得超出）

| H-text | H-sampling | 联合 verdict |
|---|---|---|
| `replicated_strong` | `sampling_effect_negligible` | **`confirmed`**：文本净效应在指纹在案批次中复现，采样效应可忽略 |
| `replicated_strong` | `sampling_effect_not_negligible` | `text_effect_confirmed_sampling_not_negligible`（文本效应成立，但"可忽略采样"不成立） |
| `replicated_direction_only` | 任意 | `directional_only`（方向复现、统计强度不足，不得称 confirmed） |
| `not_replicated` | 任意 | `not_replicated` |

**与 2026-10-09 旧批的并排对照只作描述性**：旧批无 `model_fingerprint`、`git_dirty=true`、单 seed 单格（C2），其数字（plain_llm 9/87=10.3%、RT1 10/87=11.5%、df 全协议 27/87=31.0%；RT1 vs plain_llm p=1.0；df vs RT1 不一致对 17、χ²=15.059、p=0.0001、贝叶斯 δ=+0.1868）**不构成本批判据**；本批只用它做"新旧差值/漂移"的描述与文档核对。

### 「指纹级证据」的判定（附加客观项，非统计判据）

若 6 跑的 provenance 均为 `git_dirty=false` 且 `git_sha==a93c1f6…`，且 `model_fingerprint` 块在场：
- `model_fingerprint.pinned=true` → 证据可标 **"指纹级（pinned）"**；
- `pinned=false`（如 provider 不返回 `system_fingerprint`）→ 证据标 **"指纹块在场但未 pinned（provider 限制）"**，并如实披露 `missing`/`error`，**不得**声称已锁定模型快照。

## 6. 失败 / 超时 / 停止规则（跑前冻结）

1. **单跑失败或超时：如实记录，不重跑**（同一格同一 seed 只跑一次）。单跑墙钟上限 1800 s（watchdog：SIGTERM 进程组 → 30 s 后 SIGKILL）。
2. 判定"跑成功"的客观条件：输出目录存在恰好一个 `benchmark_synthetic_*.json`，`results[<arm>]['details']` 行数 == 87，且 87 个 `task_id` 无重复。任一不满足 → 该跑记 `run_status=failed`，保留原始日志与（若有）JSON。
3. **判定数据完整性**：某 seed 三格中任一格失败 → 该 seed 从 H-text / H-sampling 的 2-seed 判定中剔除，并在报告中标注"仅 1 seed 可用"；若 0 seed 完整 → 联合 verdict = `insufficient_data`。若仅 C1 失败 → C2 与 C3 的 H-text 仍可判定（H-sampling 标 `insufficient_data`）。
4. **预算/墙钟硬停止**（任一触发即停止剩余跑批，如实报告"部分完成"）：
   - 累计估算费用 > **$1.8**（预留 $0.2 余量；总预算上限 $2.0）；
   - 跑批累计墙钟 > **5100 s（85 min）**（总上限 90 min）。
   - 费用估算口径：`token_metrics.total_input_tokens × 0.3/Mtok + total_output_tokens × 1.2/Mtok`（price_table.json 标准价，上界口径）。
5. **指纹/洁净硬检查失败**：真实模式启动前若 HEAD≠切点或工作树 dirty≠0 → 直接中止（不产生任何 LLM 调用）。跑后若 provenance 出现 `git_dirty=true` 或 `git_sha≠切点` → 数据保留但判定降级为"非指纹级"并报告原因。
6. API 可用性导致的失败（429/超时/鉴权）同样**不重跑**，如实记录退出码与日志尾部。

## 7. 预算与墙钟（跑前估算，基于旧批实测工件推算）

- token 估算（旧批实测，seed42，`e6_phase1_standard_coldcache` + `rt1_no_reinforcement_seed42`）：
  C1 109,377 tok（in 39,906 / out 69,471）；C2 206,054 tok（in 74,786 / out 131,268）；C3 225,021 tok（in 83,912 / out 141,109）。
- 每 seed 合计 in ≈ 198,604 tok、out ≈ 341,848 tok → **≈ $0.47/seed**（0.3/1.2 USD/Mtok 标准价）；2 seeds ≈ **$0.94**；留 30% 漂移余量 ≈ **$1.22**。总预算上限 **$2.0**，硬停止阈值 $1.8。
- 墙钟估算：旧批 C2 单跑实测 713.5 s（87 任务、parallelism=4）；C1 约 0.4–0.6×，C3 约 1.0–1.3× → 每 seed 估算 ≈ 1,800–2,100 s，2 seeds ≈ **60–70 min**；预留覆盖至 85 min 硬停止（总上限 90 min）。
- 说明：B2 主批次（另一 teammate）正在并行运行，CPU/API 争用可能抬高本批墙钟；按上述硬停止规则如实报告，不通过降低并行度或缩样本"美化"。

## 8. 产物（跑后写，均在本目录）

| 文件 | 内容 |
|---|---|
| `PREREG.md` | 本冻结预注册（sha256 记入 PREFLIGHT.json） |
| `PREFLIGHT.json` | 跑前闸：工作树 HEAD/dirty、PREREG sha256、dry-run 结果、环境探针、预算/墙钟估算 |
| `staging/<cell>_seed<seed>/benchmark_synthetic_<ts>.json` | 6 份原始批次工件（每跑一份） |
| `logs/<cell>_seed<seed>.log` | 6 份运行日志（含起止 ISO/epoch、命令、env、退出码、墙钟） |
| `traces/<cell>_seed<seed>/` | `AITESTER_TRACE_DIR` 追踪产物 |
| `seed42/`、`seed44/` | 每 seed 三格的抽取元数据（`meta_<cell>.json`：任务表、tokens、成本、墙钟） |
| `RUN_SUMMARY.log` | 逐跑命令/起止/退出码/墙钟/摘要 + 总墙钟/总 token/总估算费用 |
| `GATES.json` | 硬检查清单（行数 87、task_id 集合一致、provenance 洁净、指纹在场、预算/墙钟） |
| `ANALYSIS_REPORT.json` | 逐 seed 三格计数/率、Δ_text/Δ_sampling、McNemar p、bootstrap CI、tokens/成本/墙钟、regenerated 行数、旧批并排、verdict |
| `README.md` | 中文报告（含结论口径与局限） |
| `DOC_RECONCILIATION.md` | 与工件矛盾的陈旧文档声明核对清单（文件:行号 + 原文摘要 + 事实工件 + 建议修正文案） |
| `SHA256SUMS` | `scripts/gates/checksum_results.py --write` 生成、`--verify` 通过 |
| `_helpers/` | 零 LLM 可复算脚本（watchdog、抽元数据、分析、门禁） |

---

## 冻结与哈希

- 冻结时点（本地 Asia/Shanghai）：**2026-10-18 09:00（UTC+8）**，早于本批任何真实 LLM 调用。
- 预注册 sha256：运行 `PREFLIGHT.json` 时由 `sha256sum PREREG.md` 写入；`SHA256SUMS` 再次锁定。
- 若本文件在跑后被修改（除追加"跑后附录"外），本批不得作为预注册证据引用。**跑后只允许在文末追加带时间戳的附录**（如实际完成情况），不得改动 §2–§7。
