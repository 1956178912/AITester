# DOC_RECONCILIATION — T2/B1 文档 ↔ 工件核对清单（陈旧声明、事实工件、修正建议）

> **用途**：本文件是 T2/B1 批次的**文档核对交付物**，供 Lead 采纳修正。它只做两件事：①列出与工件矛盾的文档声明（文件:行号 + 原文摘要 + 事实工件）；②给出可直接替换的修正文案。**不是**对文档的修改本身（本批不修改任何生产文档）。
>
> **核对时点**：2026-10-18 09:50–10:05（Asia/Shanghai）。**文档基线** = 主仓切点 `a93c1f60ee31b9582e0146f73e3038e6ce0f01a1` 的 git 版本（`git show <cut>:<file>`，即 T 轮修改前状态）；**另核对**了工作区当前（T 轮已由 Lead 并行修正）版本，以区分"已修正"与"仍陈旧"。
>
> **证据基线（全部为零 LLM 可复算工件）**：
> - 2026-10-09 旧批（两 JSON，跨批拼合）：`experiments/results/e6_a1_batches/e6_phase1_standard_coldcache/benchmark_synthetic_20261009_190234.json`（sha256 `017df799fc47c99a0a1f22ba53217f41d068ab3c85e20c76d69856702a821c8c`；含 `plain_llm` 9/87、`plain_llm_df` 27/87）与 `experiments/results/e6_a1_batches/rt1_no_reinforcement_seed42/benchmark_synthetic_20261009_193509.json`（sha256 `85033785cf81b4fd38cb4e30df1fae3f9d033489cd01b98fb96b276138ba6eee`；RT1 臂 10/87，`DETECTION_FIRST_SECTION_ENABLE=false`）。
> - 2026-10-18 T 轮本批（6 份批次 JSON + 抽取 meta）：`experiments/results/t_round_b1_protocol_text_20261018/`（`ANALYSIS_REPORT.json`、`GATES.json`、`PREREG_CONTINUATION.md`、`SHA256SUMS` 为准；6 份批次 JSON 的 sha256 见 §2.2）。
> - 旧批登记口径：`BASELINE.yaml`（切点版本第 881–890 行）`benchmark.rt1_sampling_control` 已记录旧批为**已执行**。
> - 旧批执行记录：`experiments/results/e6_a1_batches/README.md`（切点版本第 138–161 行）"追加：RT1 采样控制臂（2026-10-09 晚）"、"判定：红队 RT1 假说被证否"、`RT1 vs plain_llm +1.1pp / p=1.0000`、`df vs RT1 +19.5pp / χ²=15.059 / p=0.0001`。
> - 另有一处**文档间自相矛盾**旁证：`INDEPENDENT_REVIEW_2026-10-16.md:239`（工作区未跟踪文件）已引用"项目 RT1 实测提示协议净效应 +19.5pp"，即该审查文档早已把 RT1 当作已执行。

---

## 1. 陈旧声明清单（以切点 `a93c1f6` 版本文档为准）

| # | 文件:行（切点版本） | 原文摘要 | 与工件矛盾点 | 事实工件 | 状态（工作区当前，2026-10-18 10:00） |
|---|---|---|---|---|---|
| S1 | `docs/VALIDITY.md:72`（§4 结论效度表"因果主张…未解耦"行） | "…§3 表中『2×2 消融（协议文本 vs 多一次采样）』一行状态为**未执行**，阻塞原因记『双开关已具备…**需 LLM 配额**』；既有对照未解耦"+43pp 协议效应"与"多一次采样的效应"" | ①2026-10-09 已有 RT1 批（C2 格）与同批 seed42 的 C1/C3 格，可做 C3−C2 文本效应与 C2−C1 采样效应；②T 轮已完成 3 格×2 seed 指纹级复现；③"未执行/需配额"与 `BASELINE.yaml:881-890`、`e6_a1_batches/README.md:138-161` 直接矛盾 | 旧批：C1 9/87、C2 10/87、C3 27/87，df−RT1=+19.5pp（不一致对 17，McNemar 精确 p=1.53e-05；登记口径 χ²=15.059，p=0.0001）；本批：C1 9/12、C2 10/10、C3 24/27，文本效应 +16.1/+19.5pp（p=0.000519/1.5e-05），采样效应 +1.1/−2.3pp（不显著） | ✅ **已修正**（当前 `docs/VALIDITY.md:72` 状态 **reduced**，含 3 格×2 seed 数字与执行修订披露；数字经 §2/§3 核对一致） |
| S2 | `docs/VALIDITY.md:106`（§5.5"为何未缓解"） | "RT1 消融正为此设计（同文件第 522–535 行），但**未执行**（`docs/study/OPTIMIZATION_2026-10-15.md` §3）。" | 同 S1；另所引 `nodes.py` 行号在切点已漂移（实际 `_detection_first_regenerate_entry` 在第 614–625 行、`_detection_first_section` 在第 649–676 行） | 同 S1 | ✅ **已修正**（当前 `docs/VALIDITY.md:106` 已改函数名定位 + "勘误：该消融并非未执行" 段） |
| S3 | `docs/VALIDITY.md:107`（§5.5"什么实验/分析会缓解"） | "以零新代码运行三格对照…**需要 LLM 配额**（同文件 §3）。" | 该动作已于 2026-10-09 与 T 轮执行 | 同 S1 | ✅ **已修正**（当前变为"**已执行的缓解**"，含 b/c、p 值） |
| S4 | `docs/VALIDITY.en.md:83`（§4 对应英文行） | "`…§3` lists "2×2 ablation (protocol text vs one more sample)" as **not executed**, blocked on "both switches already exist … needs LLM quota"" | 同 S1 | 同 S1 | ✅ **已修正**（当前 `docs/VALIDITY.en.md:83` reduced + 3 cells × 2 seeds 数字） |
| S5 | `docs/VALIDITY.en.md:117-118`（§5.5 英文两条 bullet） | "The RT1 ablation was designed exactly for this (same file lines 522–535) but was **not executed**"；"It needs LLM quota (same file §3)." | 同 S1/S2；且该 bullet 仍引切点已漂移的 `nodes.py` 行号（487–501 / 540–547 / 536–539 / 501 / 676） | 同 S1 | ⚠️ **部分修正**：第 118 行已改为 "Mitigation executed"，但第 117 行仍保留**双重否定措辞** "**Correction: the ablation was NOT unexecuted**" 与旧行号（见 §4 待处理 R2） |
| S6 | `docs/study/OPTIMIZATION_2026-10-15.md:111`（§3 未完成表） | "\| 2×2 消融（协议文本 vs 多一次采样） \| 未执行 \| 双开关已具备…**需 LLM 配额** \|" | 同 S1 | 同 S1 | ✅ **已修正**（当前第 111 行 = "**已执行（勘误：2026-10-09 RT1 单 seed 三格批；T 轮 T-2 指纹级 3 格×2 seed 复现）**"） |
| S7 | `docs/PROJECT_STATUS_REGISTER.md:68`（B1 行） | "\| B1 \| 2×2 消融（协议文本开关 × 再生成预算） \| **LLM 配额** \| 双开关已具备、零新代码；跑前设…" | 同 S1；B1 的任务状态被登记为"配额阻断" | 同 S1 | ✅ **已修正**（当前第 68 行 = "✅ **已执行（T 轮 T-2 指纹级复现）**"，含旧批与 T 轮数字） |
| S8 | `docs/EVALUATION_SCOPE.md:25`（C1b 行限定语） | "指令件是**协议包**（文本 + 再生成规则 + 终态标注），二者未分离 → **需 2×2 消融**" | T 轮三格×2 seed 已完成该分离（文本净效应显著、采样效应不显著） | 本批 `ANALYSIS_REPORT.json` / `README.md` §3 | ❌ **仍陈旧**（见 §4 待处理 R1） |
| S9 | `docs/EVALUATION_SCOPE.md:60`（§4 待决项 #1） | "\| 1 \| C1b 因果分离 \| 2×2 消融（协议文本开关 × 再生成预算），**LLM 配额** \| 声明限定为"协议包效应" \|" | 同 S8 | 同 S8 | ❌ **仍陈旧**（见 §4 待处理 R1） |

**另：行号漂移（切点版本多处引用 `src/graph/nodes.py` 固定行号）**——切点实际位置：`_detection_first_regenerate_entry` L614–625、`_detection_first_section` L649–676（RT1 docstring L652–661）、`_detection_first_section_enabled` L797–803、`_over_red_section_enabled` L677、`_over_red_section` L737。文档切点版本引用的 522–535 / 540–547 / 487–501 / 536–539 / 550–557 / 671–676 **全部不对应**。T 轮已把中文 VALIDITY 与 VALIDITY.en.md:83 改为**函数名定位**（正确方向）；仅 VALIDITY.en.md:117 仍保留旧行号（见 §4 R2）。

---

## 2. 事实工件（可复算，供修正文案引用）

### 2.1 旧批（2026-10-09，seed42，跨两批拼合）

| 格 | 臂 | 检出/可测 | 配对口径 | 工件 |
|---|---|---|---|---|
| C1 | `plain_llm` | **9/87 = 10.3%** | — | `e6_phase1_standard_coldcache/benchmark_synthetic_20261009_190234.json` |
| C2 | `plain_llm_df` + `DETECTION_FIRST_SECTION_ENABLE=false` | **10/87 = 11.5%** | regenerated rows **77/87**；token 206,054 | `rt1_no_reinforcement_seed42/benchmark_synthetic_20261009_193509.json` |
| C3 | `plain_llm_df`（全协议） | **27/87 = 31.0%** | token 225,021 | `e6_phase1_standard_coldcache/benchmark_synthetic_20261009_190234.json` |

旧批配对复算（行 `detection_rate`，按 task_id 配对；与 `BASELINE.yaml:881-890` 登记一致）：
- **C3−C2（文本净效应）**：b=17、c=0、不一致对 **17**、Δ=**+19.54pp**；McNemar 精确双侧 **p=1.53e-05**（登记口径用 χ² 连续性校正：χ²=15.059、p=0.0001，两者同向显著，引用须注明 p 口径）。
- **C2−C1（采样效应）**：b=1、c=0、不一致对 **1**、Δ=**+1.15pp**；McNemar p=**1.0**（登记 "+1.1pp / p=1.0000"）。

**旧批证据质量限定（修正文案必须携带）**：
1. `git_dirty=true`、无 `model_fingerprint`、旧批 `env_snapshot` **不含** `DETECTION_FIRST_SECTION_ENABLE` 键（只能由 `dirty_reason` 文本 "RT1 sampling control: regeneration WITHOUT detection-first reinforcement section" 佐证干预口径）；
2. **跨批拼合**：C1 与 C3 来自 phase1 三臂批（2026-10-09 19:02），C2 来自 RT1 单独批（19:35），不是"同一次运行内的三格"——建议文档措辞写"单 seed 三格（跨两批拼合）"而非"单 seed 三格批"；
3. 因此旧批只能作**描述性/历史证据**；"指纹级复现"证据以 T 轮本批为准。

### 2.2 T 轮本批（2026-10-18，切点 `a93c1f6`，6 跑，干净树）

| 格 | seed42 检出/可测 | seed44 检出/可测 |
|---|---|---|
| C1 `plain_llm`（无再生成/无强化段） | **9/87 (10.3%)** | **12/87 (13.8%)** |
| C2 `plain_llm_df` + SECTION=false（RT1） | **10/87 (11.5%)** | **10/87 (11.5%)** |
| C3 `plain_llm_df` 全协议 | **24/87 (27.6%)** | **27/87 (31.0%)** |

- **文本净效应 C3−C2**：seed42 **+16.09pp**（b=15/c=1，McNemar 精确 p=**0.000519**，bootstrap 95% CI [8.05, 24.14]）；seed44 **+19.54pp**（b=17/c=0，p=**1.53e-05**，CI [11.49, 27.59]）→ 2/2 同向且均显著。
- **采样效应 C2−C1**：seed42 **+1.15pp**（b=1/c=0，p=1.0）；seed44 **−2.30pp**（b=0/c=2，p=0.5）→ |Δ|≤5pp 且均不显著。
- **联合 verdict（PREREG §5 冻结规则）**：`confirmed`。
- **GATES**：`status=pass`，blocking=[]，warnings=[]，**17 项 checks 全过**（含 `provenance_clean_tree`、`provenance_sha_matches_cut`、`model_fingerprint_pinned`、`intervention_section_switch_in_artifact`、`mutation_scoring_disabled_all_runs`、`cost_total_under_budget_2usd`）。
- **provenance**：6 跑 `git_dirty=false`、`git_sha=a93c1f6`、`model_fingerprint.pinned=true`（`returned_model=deepseek-flash`，`system_fingerprint` 齐全，6 跑探针 sha256 唯一值=1）、`cache_namespace=t_b1_<cell>_<seed>` 隔离、`temperature=0.0`、同 seed 三格 task 集逐位一致；`ENABLE_MUTATION_SCORING=false`（执行修订，见 `PREREG_CONTINUATION.md`）。
- **成本/墙钟**：6 跑估算 **$0.876339**（价目表标准价上界口径，非账单）；逐跑墙钟之和 1281s；**批次墙钟 1299s（=21.65 min）**。
- 6 份批次 JSON 的 sha256（`staging/<cell>_seed<seed>/benchmark_synthetic_*.json`）：
  - C1_seed42 `829412f5d0ff40ab0fdd18045245094540e286d366490a9c54b35a929f41aadb`
  - C1_seed44 `0f88d689a374846127c7413b72a8063473b604a870ad855b696fdd0b630ebfc2`
  - C2_seed42 `a2cd1153c84bc9a437079ea9f931250e9e3d0c2c1bf2db9c92a0958041b909c2`
  - C2_seed44 `75d6b5a816345197bb6be6b33dce54b3a1cae674681e4da218fd6cc84966ff77`
  - C3_seed42 `b0677e74a266a6dda26653c29f4039af8f5f40a683720e85a17d6c3d6da4e0c2`
  - C3_seed44 `6e0fadfa18dc28b88d0487fae41a458033e94e36b0fd44f7ad5062b36d541cf5`

---

## 3. 工作区当前（T 轮已修正）版本的数字一致性核对

| 当前文档位置 | 文档声称 | 工件实际 | 一致? |
|---|---|---|---|
| `docs/VALIDITY.md:72` / `docs/VALIDITY.en.md:83` | "C1 plain_llm 9/12、C2 RT1 10/10、C3 df 全协议 24/27；文本效应 +16.1/+19.5pp，p=0.000519/1.5e-05；采样效应 +1.1/−2.3pp 不显著" | 同 §2.2 | ✅ |
| `docs/VALIDITY.md:72` 残余项 ③ | "六格（首跑中止后统一重跑）均关闭批后 `ENABLE_MUTATION_SCORING`（仅辅助测量，detection 口径不变；执行修订见 `PREREG_CONTINUATION.md`）" | `GATES.json` `mutation_scoring_disabled_all_runs` ok；`PREREG_CONTINUATION.md` 在场 | ✅ |
| `docs/VALIDITY.md:72` 残余项 ② | "与 R-P0-2 三臂主批次协议不同，不得混池" | 本批单臂逐格、df 协议 C3≈27.6–31% vs 主批 df 44.8%（`statistical_report_3seed_pooled.md`），确不可混池 | ✅ |
| `docs/VALIDITY.en.md:83` 残余项 ③ | "all six cells … had post-hoc `ENABLE_MUTATION_SCORING` disabled" | 六跑 env_snapshot 均 false | ✅ |
| `docs/OPTIMIZATION…:111` | "已执行（勘误：2026-10-09 RT1 单 seed 三格批；T 轮 T-2 指纹级 3 格×2 seed 复现）" | 数字同 §2；措辞建议补"跨批拼合"（见 §4 R3） | ⚠️ 数字✅ / 措辞可再精确 |
| `docs/PROJECT_STATUS_REGISTER.md:68`（B1） | "2026-10-09 RT1 单 seed 批已执行（RT1 10/87 vs plain_llm 9/87 vs df 27/87，df−RT1=+19.5pp）；T 轮 3 格×2 seed…文本效应 +16.1pp(p=0.000519)/+19.5pp(p=1.5e-05)；采样效应 +1.1/−2.3pp" | 同 §2 | ✅ |
| `docs/PROJECT_STATUS_REGISTER.md:181`（T-2 行） | "`DOC_RECONCILIATION.md` 给出 VALIDITY/EMSE/EVAL_SCOPE 四处『未执行』陈旧声明与纠正文案" | 本文件即该交付物 | ✅ |
| `BASELINE.yaml` `target_quality.b1_protocol_text_t_round`（当前工作区 365–378 行） | 数字/口径逐项核对（cells、effects、cost 0.876339、wall 1281、verdict） | 同 §2.2 | ✅（除 §4 R4/R5 两处小口径） |

---

## 4. 仍待处理项（建议 Lead 采纳；均为文案级，不动判据）

### R1（**仍陈旧，建议改**）`docs/EVALUATION_SCOPE.md:25` 与 `:60`

- 当前第 25 行 C1b 行限定语仍是"…二者未分离 → **需 2×2 消融**"；第 60 行 §4 待决项 #1 仍是"2×2 消融…LLM 配额"。
- 建议替换（第 25 行 C1b 行末两列）：
  - 状态：`partial` → **`supported（带口径，T 轮 T-2）`**
  - 限定语：`指令件是协议包（文本 + 再生成规则 + 终态标注），二者未分离 → 需 2×2 消融` → **`T 轮三格×2 seed 已分离：文本净效应 C3−C2 = +16.1/+19.5pp（McNemar p 均显著），多一次采样 C2−C1 = +1.1/−2.3pp（不显著）；残余：单数据集/单模型/2 seed，不得外推为 R-P0-2 三臂等预算结论（`t_round_b1_protocol_text_20261018/`）`**
- 建议替换第 60 行 §4 #1：
  - 需要什么：`2×2 消融（协议文本开关 × 再生成预算），LLM 配额` → **`已执行（T 轮 T-2 指纹级三格×2 seed；工件 `experiments/results/t_round_b1_protocol_text_20261018/`）；残余：主批次三臂未与 T2 同 harness 同批重测`**
  - 若不关闭的限定：`声明限定为"协议包效应"` → **`可写"协议包中的提示词文本为主导成分（2 seed 文本净效应 +16~+20pp 显著、多一次采样 ≤|2.3|pp 不显著）"，仍不得写"架构无关"或外推`**

### R2（**措辞级**）`docs/VALIDITY.en.md:117`

- 现存双重否定："**Correction: the ablation was NOT unexecuted** — a 2026-10-09 single-seed RT1 batch exists…" → 建议改为 "**Correction: the ablation had already been executed** — a 2026-10-09 single-seed RT1 batch exists…"。
- 同 bullet 仍有切点已漂移的 `nodes.py` 行号（487–501 / 540–547 / 536–539 / 501 / 676）→ 建议与 `VALIDITY.en.md:83` 一致改为函数名定位（`_detection_first_regenerate_entry` / `_detection_first_section` / `_detection_first_section_enabled` / `_over_red_section`），删去行号。

### R3（**措辞精确化**）`docs/study/OPTIMIZATION_2026-10-15.md:111` 与 `docs/PROJECT_STATUS_REGISTER.md:68`

- "2026-10-09 RT1 单 seed 三格批"建议改"2026-10-09 单 seed 三格（**C1/C3 来自 phase1 三臂批、C2 来自 RT1 单独批，跨批拼合**；`e6_a1_batches/README.md` 同口径）"，以免读者误以为三格来自同一次运行。

### R4（**一致性小错**）`BASELINE.yaml` `target_quality.b1_protocol_text_t_round.provenance`

- 当前写 "**16 checks 全过**"；工件 `GATES.json` 实为 **17 项 checks**（T2 在原有 16 项上新增 `mutation_scoring_disabled_all_runs`）。建议改 "17 checks 全过（含执行修订生效性检查）"。

### R5（**口径歧义**）`BASELINE.yaml` `target_quality.b1_protocol_text_t_round.cost.wall_seconds`

- 当前 `wall_seconds: 1281` 实为**六跑逐跑墙钟之和**；**批次墙钟**为 **1299s**（`RUN_SUMMARY.log` `BATCH_WALL_SECONDS=1299`；含 6 次 extract/调度开销）。建议字段注释为 `wall_seconds: 1281（六跑墙钟之和；批次墙钟 1299s）`。

### R6（**非本批任务、供参考**）旧批工件本身无法补写 `model_fingerprint`

- 旧批 `git_dirty=true`、无指纹、`env_snapshot` 缺 `DETECTION_FIRST_SECTION_ENABLE` 键。任何引用旧批的文档（含 `BASELINE.yaml:881-890`）均应携带"旧批无指纹、dirty、跨批拼合"限定；**不得**把旧批与 T 轮本批合并统计或宣称同快照。

---

## 5. 结论

1. **必改陈旧声明共 9 处（5 文件）**：切点版本 `VALIDITY.md:72/106/107`、`VALIDITY.en.md:83/117-118`、`OPTIMIZATION_2026-10-15.md:111`、`PROJECT_STATUS_REGISTER.md:68`、`EVALUATION_SCOPE.md:25/60`，其共同错误是把 2026-10-09 已执行的 RT1 消融写成"未执行/需 LLM 配额"，与 `BASELINE.yaml:881-890`、`e6_a1_batches/README.md:138-161` 及两批批次工件直接矛盾。
2. **截至 2026-10-18 10:00，Lead 已在工作区修正 7/9 处**（VALIDITY 中英各 2 处、EMSE 1 处、PROJECT_STATUS 1 处；另有 1 处部分修正），修正后数字经 §3 逐项核对**与工件一致**（9/12、10/10、24/27、+16.1/+19.5pp、p=0.000519/1.5e-05、+1.1/−2.3pp、$0.876339、批次墙钟 1299s）。
3. **仍待处理 2 处陈旧（`docs/EVALUATION_SCOPE.md:25` 与 `:60`）** + **3 处文案/口径小修（R2–R5）**；可直接采用 §4 的替换文案。
4. 本批的"指纹级复现"证据边界：干净切点 + `git_dirty=false` + `model_fingerprint.pinned=true` + PREREG 冻结 + GATES 17 项全过；但仍为 **2 seed、synthetic 单数据集、单模型别名、单臂逐格**，且存在一次**跑中执行修订**（辅助 mutation/MDO 测量关闭，见 `PREREG_CONTINUATION.md`）——文档引用时必须携带这些限定。
