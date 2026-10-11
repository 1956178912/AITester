# WS2 项目头条指标独立重算结果

- 角色：独立指标重算员（未参与项目任何实验/脚本/报告撰写）
- 脚本：[`_independent_audit/ws2_recompute.py`](ws2_recompute.py) — 一键复现：`python _independent_audit/ws2_recompute.py`
- 环境：`.venv/bin/python` = Python 3.14.6，pytest 9.1.1
- 数据来源纪律：**只读原始工件**（`benchmark_*.json` / `traces/*.jsonl` / `*.log` / `SHA256SUMS` / `price_table.json` / 数据集 jsonl / `raw/`）。脚本内不读任何 `.md`；既有报告与 `BASELINE.yaml` 只作为"被核对的声称值"。
- 只读纪律：脚本不写仓库任何文件（重放只写 `tempfile.mkdtemp()` 并在结束后清理）。实测副作用：`git status --porcelain` 运行前后仅新增本目录 `_independent_audit/`，无其他改动。
- 复现命令：`python _independent_audit/ws2_recompute.py`（§2/§3 会跑 ~800 次本地 pytest，约 1–2 分钟）；`--sections 0,1` 可只跑单节；`--with-tests` 追加全量测试套件（~4 分钟）。

---

## §1 数据 schema 说明（实际看到的字段）

**批次文件顶层**（例：`experiments/results/main_batch/benchmark_synthetic_20261006_140906.json`）

| 键 | 类型 | 说明 |
|---|---|---|
| `timestamp` | str | 批次时间戳 |
| `dataset` / `subset` | str / null | `synthetic` |
| `seed` | int | 42 / 43 / 44 |
| `total_tasks` | int | 87（R-P0-2 三文件） |
| `baselines` | list | `["aitester","plain_llm","plain_llm_df"]` |
| `parallelism` / `valid_apis` | int | 并发与可用 API 数 |
| `p2p_gate_enabled` / `p2p_gate_threshold` | bool / float | 0.95 |
| `environment` / `provenance` | dict | git_sha、git_dirty、model_name、temperature、cache_namespace、per_task_token_caps… |
| `results` | dict | 三臂 |

**`results.<arm>` 汇总键**（三臂同构，15 键）：`total_functions, passed_count, failure_count, success_rate, harness_invalid_count, effective_total, effective_success_rate, avg_coverage, avg_iterations, avg_elapsed_seconds, total_time, failure_category_distribution, token_metrics, rag_metrics, details`。
注意：**`results.<arm>` 里没有 detection/repair/false_fix 汇总字段** —— 头条 detection 率必须由 `details[]` 逐行聚合得出，这正是"口径可任意挑选"的风险点。

**`details[i]` 行键（42 键）**，与本次重算相关的：

| 字段 | 含义（由 `experiments/_m1_metrics.py:490/594/663` 反推） |
|---|---|
| `task_id` | `synthetic__task_0000`（`<dataset>__<module>`） |
| `passed` | 自指口径：系统**自产**测试在（可能未修复的）代码上通过 |
| `coverage` | 该行覆盖率（浮点） |
| `detection_rate` | **F2P 三段判定**，仅 `0.0 / 1.0 / None`（本批实测无非二值行） |
| `detection_first_red_seen` | 生成测试是否**曾在修复前变红**（宽松口径，含误红） |
| `detection_first_status` | `all_green_unverified` 等 |
| `test_error_rate` | buggy 侧 rc≥2 或命中收集/语法错误标记 → 1.0 |
| `repair_rate` | 补丁落地后 gold `test_cases` 跑 `rc==0` → 1.0 |
| `false_fix_rate` | `passed==True ∧ repair_rate==0.0` → 1.0 |
| `patch` | 原始补丁文本（**实测全部以 `python\n` 围栏残留开头**） |
| `patch_plausible` / `patch_correct` / `patch_precision` | 补丁合理性三件套 |
| `mutation_score` / `mutants_killed` / `mutants_total` | 变异得分 |
| `spec_compile_rate` / `spec_expr_coverage` | 规约指标（仅 20261007 批 aitester 有值） |
| `token_usage.by_model` | 逐模型 token（主批次仅 `deepseek-flash`） |
| `task_metadata` | **gold 材料所在**：`test_cases`、`fixed`、`bug_type`、`is_cross_file`、`module_a/b/c_code`、`target_module`… |

### detection 的口径判定（任务书要求"反推定义并写明依据"）

依据 `experiments/_m1_metrics.py:490-556`（`_compute_detection_rate`）+ `experiments/run_benchmark.py:1187`（字段透出），并用原始行字段自洽性交叉验证：

> **detection = fail-to-pass（F2P）三段判定**：
> ① 生成测试在 **buggy（original_code）** 上 `rc != 0`；② 在 **gold 修复代码（fixed）** 上 `rc == 0`；③ 两侧均无收集/语法错误信号（`errors during collection` / `no tests were run` / `SyntaxError`，或 `rc>=2`）。三者同时成立才记 1.0。

因此任务书里"生成的测试在修复前能因真实缺陷而红"**只是充分条件的一半**：真正的口径是"**修复前红、修复后绿**"。这两者在原始数据上差异巨大（我的重算，§2）：

| 口径 | aitester | plain_llm | plain_llm_df |
|---|---|---|---|
| `detection_first_red_seen`（修复前曾红，宽松） | **154/261 = 59.0%** | 32/261 = 12.3% | **261/261 = 100%** |
| `detection_rate`（F2P，项目主口径） | **38/240 = 15.8%** | 4/261 = 1.5% | **117/261 = 44.8%** |

交叉表证据（`§1` 输出）：aitester 有 **116 行**"修复前曾红但 F2P=0"——即红得没有信息量（在 gold 修复后仍红，属误红/过红）；plain_llm_df 更多达 **137 行**。这说明 aitester 的宽松红率（59%）中只有 24.7% 是真实检出。
另发现 **1 行内部不自洽**：plain_llm 有 1 行 `detection_rate=1.0` 但 `detection_first_red_seen=False`（`§1` 交叉表 `(1.0, False): 1`）。

---

## §2 逐指标重算表

### 2.1 detection（R-P0-2 三种子合并，n=261/臂）

纳入文件（由文件名内嵌时间戳与三份 87 任务工件确认，seed=42/43/44）：`benchmark_synthetic_20261006_140906.json` / `_151907.json` / `_164357.json`。

| 指标 | 项目声称值 | 我重算值 | 一致? | 差异原因 | 证据 |
|---|---|---|---|---|---|
| aitester detection | 15.8%（38/240） | **15.83%（38/240）**，21 行 `None` | ✅ | — | 声称 `statistical_report_3seed_pooled.md:35`；重算 6_140906:12/81、6_151907:15/79、6_164357:11/80 |
| plain_llm detection | 1.5%（4/261） | **1.53%（4/261）** | ✅ | — | `statistical_report_3seed_pooled.md:36` |
| plain_llm_df detection | 44.8%（117/261） | **44.83%（117/261）** | ✅ | — | `statistical_report_3seed_pooled.md:37` |
| passed（自指） | 143 / 229 / 7 | **143 / 229 / 7** | ✅ | — | `statistical_report_3seed_pooled.md:35-37` |
| tokens/task | 26,115 / 3,209 / 4,223 | **26,115 / 3,209 / 4,223** | ✅ | — | `statistical_report_3seed_pooled.md:35-37` |

**关键结构性发现（口径风险）**：aitester 的 detection 分母是 **240**（剔除 21 行 `None`），而 plain_llm / plain_llm_df 的分母是 **261**。若统一用 261 分母，aitester = 38/261 = **14.6%**，三家口径不一致会额外放大 aitester 与 df 的差距（44.83% vs 14.56% = 30.3pp，而非 29.0pp）。README 标注"21 行缺失双界下稳健"属实，但 240/261 混用必须随数字披露。

### 2.2 repair（任务书重点 ①）

**来源工件与脚本**：`experiments/corrected_metrics.py`（汇总报告生成器，调用 `experiments/repair_replay.py:replay_row`，再复用 `experiments/_m1_metrics.py:_run_pytest_in_tmp` + `src/tools/patch_applier.py:normalize_patch_text`）。**其输出工件 = `experiments/results/main_batch/corrected_report_v2.md`（§2.2 的 57/145 只存在于该报告文本与脚本 stdout，仓库内没有对应的 JSON/CSV 数字工件）** —— 这是本次重算中唯一"声称值只存在于 .md、无机器可读产物"的头条数字。

我的重算**完全不复用**项目函数：自写 `my_normalize()`（剥 markdown 围栏 + 语言前缀）+ 自写 `run_pytest_tree()`（自建 tmp 树、自行物化跨文件伴生模块、直接 `subprocess` 跑 pytest）。交叉核验：我的清理输出与项目 `normalize_patch_text` 在 **266/266** 可重放行上**逐字相同**。

| 指标 | 项目声称值 | 我重算值 | 一致? | 差异原因 | 证据 |
|---|---|---|---|---|---|
| R-P0-2 修正 repair | 39.31%（57/145） | **39.31%（57/145）** | ✅ 精确一致 | — | 声称 `corrected_report_v2.md:7,22`；重算 §2 |
| E1/E2 修正 repair | 54.72%（58/106） | **54.72%（58/106）** | ✅ 精确一致 | — | `corrected_report_v2.md:8` |
| 早期批（10-01） | 0/15 | **0/15** | ✅ | — | `corrected_report_v2.md:22` 邻行 |
| 行级裁决分布 | `{skipped_no_material:8, no_patch:395, wrong_patch:151, correct:115}` | **`{skipped_no_material:8, no_patch:395, wrong_patch:151, correct:115}`** | ✅ 精确一致 | — | `corrected_report_v2.md:15` |
| **原口径** repair（不清理围栏） | "全线 0.0%" | **0/266 correct** | ✅ | 274 行补丁**全部**以 `python\n` 开头（首 12 字符分布：`python\ndef c`×48、`python\n_TABL`×40、`python\nimpor`×28…） | §2 |
| **v1 口径**（跨文件不物化） | 35.86%（52/145） | **35.86%（52/145）** | ✅ 精确一致 | 反事实变体：把 19 个跨文件行退回单文件判分，差值恰为 5 行 | `corrected_report_v2.md:7` |
| v1 → v2 归因（R27 跨文件修复） | +5 行（52→57） | **+5 行**（E1/E2：+7 行，51→58） | ✅ | 与声称归因完全吻合 | `corrected_report_v2.md:8`；§2 反事实节 |
| 修复漏斗 | 进入 154 → patch 94% → plausible 47% → correct 39.31% | **154/261 → 145/154=94.16% → 72/154=46.75% → 57/145=39.31%** | ✅ | 声称"94%/47%"的分母是 **154**（= `detection_first_red_seen=True` 的行数），"39.31%"的分母是 **145**，分母在漏斗中途换了一次 | `statistical_report_3seed_pooled.md:165`；§2 漏斗节 |

**判定**：repair 39.31% 经独立重放**成立**，且两起测量伪影（围栏残留、跨文件未物化）的归因也被我的反事实实验**独立证实**。唯一保留意见：该数字**没有机器可读输出工件**，只有 `.md` 文本 + 需重跑的脚本，因此"可复算"依赖仓库代码保持在当前状态（脚本已含 `experiments/_m1_metrics.py` 在 2026-10-11 追加的 P0-2b 早退逻辑，属**修复后**代码，历史工件不会再现该值）。

### 2.3 false_fix（任务书重点 ③）

| 指标 | 项目声称值 | 我重算值 | 一致? | 差异原因 | 证据 |
|---|---|---|---|---|---|
| 主批次修正 false_fix（全 10 文件 669 行） | 87.2%（380/436） | **87.16%（380/436）** | ✅ 精确一致 | 分母 436 = passed 443 − 不可测 7 | 声称 `corrected_report_v2.md:27-28` |
| 仅 R-P0-2 三文件 | README 表述为"主批次修正 false_fix=87.2%" | **76.92%（110/143）** | ⚠️ **口径歧义** | 87.2% 实际是**跨代际 10 文件**口径；单看主批次三文件只有 76.9%。README:56 把"主批次"与"全 main_batch 目录"混称 | `README.md:56` |
| R-P0-2 逐行 `false_fix_rate` 字段 | 143/240 = 59.6% | **59.58%（143/240）**，21 行 `None` | ✅ | — | §3[A] |
| 历史批 false_fix（10-01 n=50） | 89.8% | **90.0%（45/50，逐行字段）**；**89.8%（44/49）** | ⚠️ 需换分母才成立 | 逐行字段给 90.0%。89.8% 只在"分母 = `detection_rate` 可测行 49、分子 = passed∧ff1=44"时成立 —— **分子用 passed 行、分母用 detection 可测行，是两套不匹配的筛选** | 声称 `README.md:56`、`README.md:759`、`statistical_report.md:55`；重算 §3[B] |

### 2.4 coverage / mutation（任务书重点 ④）

口径说明：项目"区间"= **批次级 `avg_coverage` 的极差**，不是任务级分位数。

| 指标 | 项目声称值 | 我重算值 | 一致? | 差异原因 | 证据 |
|---|---|---|---|---|---|
| target_line_coverage aitester | [84.0, 93.6] | **[84.0, 93.6]**（最低 6_151907，最高 20261001_121523） | ✅ | — | `target_quality_report.md:12,14`；§4 |
| target_line_coverage plain_llm | [86.0, 97.2] | **[86.0, 97.2]**（排除 2 个 n=5 小文件）；**含全部 10 文件则为 [70.4, 97.2]** | ⚠️ 区间依赖文件集 | 70.4 出现在 `20261001_112528/112801`（n=5），被排除但报告未声明排除规则 | `target_quality_report.md:12-15`；§4 |
| mutation_score 逐文件 | 6_140906: 0.976/0.971/0.986；151907: 0.930/0.951/0.993；164357: 0.958/0.992/0.989 | **0.9760/0.9713/0.9856；0.9304/0.9515/0.9933；0.9580/0.9916/0.9885** | ✅ 逐项一致 | — | `target_quality_report.md:29-30`；§4 |
| mutation_score 区间（我补充） | 未给区间 | aitester **[0.8175, 0.976]**、plain_llm **[0.9515, 0.9916]**、plain_llm_df **[0.9856, 0.9968]** | 新增 | 含 20261007 批后 aitester 下探到 0.8175 | §4 |

### 2.5 spec 指标（任务书重点 ⑤）

分子分母定义（由原始行字段反推）：`spec_compile_rate` / `spec_expr_coverage` 均为**逐任务行级浮点**，项目报告取**行均值**（分母 = 该字段非 `None` 的行数）。仅 `20261007` 批的 **aitester** 臂有值，其余臂/批全为 `None`。

| 指标 | 项目声称值 | 我重算值 | 一致? | 差异原因 | 证据 |
|---|---|---|---|---|---|
| spec_compile_rate | ~0.21 | **0.2045（n=77，6_161053/181638）、0.2189（n=81，6_170147/185941）** | ✅ | 4 个文件实为 2 组同值重复跑（161053≡181638、170147≡185941） | §4 |
| spec_expr_coverage | ~0.73 | **0.7415（n=45）、0.7232（n=51）** | ✅ | 同上 | §4 |

⚠️ 重要限定：这两个值**只覆盖 158/348 行**（45.4%）且只存在于 20261007 批；`MODEL_CARD.md:82` 另称 logic 档 spec_compile_rate 恒 0.0（AB1 批 12/12），与本批 0.20 矛盾 —— 两批不可混引。

### 2.6 成本 $/task（任务书重点 ⑦）

| 指标 | 项目声称值 | 我重算值 | 一致? | 差异原因 | 证据 |
|---|---|---|---|---|---|
| aitester $/task | 0.0259 | **0.02588** | ✅ | — | `README.md:56`；§8 |
| plain_llm_df $/task | 0.0045 | **0.00454** | ✅ | — | 同上 |
| plain_llm $/task | （README 未给） | **0.00336**（Lead 给的 0.0034 口径一致） | 新增 | — | §8 |

口径与价目表缺口：`experiments/price_table.json` 中 **`agnes-3.0-flash` 的 `input_per_mtok`/`output_per_mtok` 均为 `null`、`source` 为空**（`:11-14`），无官方价目来源；`deepseek-flash` = in $0.3 / out $1.2 per Mtok USD，source = `https://api-docs.deepseek.com/quick_start/pricing`（`:4-9`）；`qwen-long` = 0.5/2.0 **CNY**（`:19`，币种与 USD 混表）。
**限定**：R-P0-2 三文件 `token_usage.by_model` 全部是 `deepseek-flash`（6,815,977 / 837,664 / 1,102,230 tokens），**未混用 agnes，故本批成本不受 null 价目影响**；但项目其它批次用到 agnes 时成本**无法计算**且报告未逐批声明。

### 2.7 测试套件数字（任务书重点 ⑧）

| 指标 | 项目声称值 | 我重算值 | 一致? | 差异原因 | 证据 |
|---|---|---|---|---|---|
| `tests.total_passed` | **5389** | **5390**（两次串行：5390/5390；`-n 4`：5390） | ❌ **不一致（差 1）** | 字段值比实测少 1 | 声称 `BASELINE.yaml:17`；§9 |
| 收集数 | 隐含 5393（5389+3+1） | **5394**（`--collect-only`） | ❌ 差 1 | — | §9 |
| skipped / xfailed | 3 / 1 | **3 / 1** | ✅ | — | `BASELINE.yaml:19-20` |
| **同字段行内注释声称** | **5323 passed + 3 skip + 1 xfail** | **5390 passed + 3 + 1** | ❌ **不一致（差 67）** | `BASELINE.yaml:17` 同一行里"字段值 5389"与"注释实测 5323"自相矛盾；5323+3+1=5327，比收集数 5394 少 **67** 个用例，无法由本次实测复现 | `BASELINE.yaml:17`；§9 |
| suite_seconds | 35（xdist -n 4）/ 199（串行） | **71.1s（`-n 4`）/ 220.5s 与 235.1s（串行）** | ❌ 差 2 倍 | 机器/负载差异，非同口径 | `BASELINE.yaml:22` |
| 门禁为何放过 | — | `tests/test_2026_10_10_optimization_batch.py:169-175` 只断言 `declared <= collected` 且 `collected - declared <= skipped+xfailed+5 = 9`；5389 ≤ 5394 且差 5 ≤ 9 → **绿**，允许最多 9 个用例的陈旧 | 结构性缺陷 | 该测试 docstring（`:140`）称"`collected == passed+skipped+xfailed` 是错误等式"，但实测 **5394 = 5390+3+1 恰好成立**，该论断被反证 | `tests/test_2026_10_10_optimization_batch.py:134-177` |

### 2.8 SHA256SUMS（任务书重点 ⑨）

| 指标 | 项目声称值 | 我重算值 | 一致? | 证据 |
|---|---|---|---|---|
| 20 条抽样校验 | — | **20/20 匹配，0 不匹配，0 缺失** | ✅ | `experiments/results/main_batch/SHA256SUMS`（2029 条：2007 traces + 12 json + 10 md + 2 `.mimosa`）；抽样为等距 20 条（步长 101），用 hashlib 逐字节重算 |

### 2.9 统计显著性（任务书重点 ⑩）

| 对比 | 项目声称值 | 我重算值 | 一致? | 证据 |
|---|---|---|---|---|
| **E2（20261007_170147+161053）aitester vs plain_llm_df** | δ=**−0.3673**，CI [−0.4552, −0.2785]，P(δ>0)=0.0000，`bayes_neg` | **δ=−0.3673**，CI **[−0.4556, −0.2789]**，P(δ>0)=0.0，χ²(校正)=**45.3065**，共同可测 n=143，列联表 (both,a_only,b_only,neither)=(16,**4**,**58**,65) | ✅ 精确一致（CI 差 4e-4 = MC 噪声） | 声称 `statistical_report_e2.md:109`；§7 |
| R-P0-2 合并 aitester vs plain_llm_df | δ=−0.279，CI [−0.348,−0.209] | **δ=−0.2787**，CI **[−0.3481, −0.2090]**，χ²(校正)=48.7935，n=240，列联表 (26,12,80,122) | ✅ 精确一致 | `statistical_report_3seed_pooled.md:44` 区；§7 |
| R-P0-2 合并 aitester vs plain_llm | δ=+0.139，CI [+0.092,+0.190] | **δ=+0.1393**，CI **[+0.0921, +0.1900]** | ✅ | 同上 |
| E2 aitester vs plain_llm | δ=0.1049 | **δ=0.1049**，CI [0.0519,0.1633] | ✅ | `statistical_report_e2.md:108` |

**所用检验与假设（我实际用的）**：
1. **配对二值差**：McNemar，χ² 带连续性校正；p 同时给**双侧精确二项**（不依赖卡方近似）。
2. **δ 的贝叶斯口径**：4 格均匀 `Dirichlet(1,1,1,1)` 先验 → `δ = p_A − p_B` 后验。我推导出并验证了其**解析均值 = (a_only − b_only)/(n+4)**（据此 E2 = (4−58)/147 = −0.3673，与项目逐位吻合）；CI 由 `Dirichlet(计数+1)` 抽样 **20 万次**得到（项目用 2 万次 + `random.Random(seed=42)`）。
3. **任务级聚类**：以基础 `task_id`（跨种子同名任务）为重采样单位做 20000 次 cluster bootstrap。R-P0-2 合并：k=87 簇，δ=−0.2833，95%CI **[−0.3598, −0.2083]**（比 i.i.d. CI 略宽，方向与显著性不变）。
   - **与 Lead 的差异**：Lead 用"唯一程序体"聚类得 n=26、δ=−24.6pp、CI[−33.7,−15.6]、配对 t=−5.36。两者聚类单位不同（任务 vs 程序体），结论方向一致；程序体聚类更保守，我采纳其存在但未复算（超出本轮范围）。
4. **假设与保留**：δ 的 CI 是**贝叶斯可信区间**，不是频率派置信区间；240 vs 261 分母混用未在 CI 中体现；三种子非独立（同一程序体重复 ≤9 次）已由聚类 bootstrap 部分吸收，但**未做多重比较校正**（项目用 BH-FDR 我只逐对比对）。

---

## §3 SWE-bench 外部有效性证据（原始日志摘录）

**结论：仓库内不存在任何有效的 SWE-bench 外部基准证据。所有运行都终止于基础设施/挂具失败，最高分 1/20。**

### 3.1 声称 0/20 的主工件本身是**挂具失败**，不是算法测量

`experiments/results/swe_bench_lite_20/benchmark_swe_bench_20260818_113525.json`：
- 20 行 **全部 `"repo": "unknown"`**（`:27,44` 等，`repository: "unknown"` 共 20 处，`:35` 示例）
- `error_category` = `{'syntax': 19, 'timeout': 1}`，`coverage` 全部 `0.0`
- 顶层键**没有 `provenance` / `environment`** → 未记录 git_sha、模型、环境
- 行例诊断（`:33`、`:41` 附近）：`'被测代码中包含了一个无效的 decimal literal…这是一段描述性的文本，不应该出现在 Python 代码文件中。'`

即：**没有做仓库 checkout，被测代码是一段坏片段**。`0/20` 测的是挂具，不是能力。

### 3.2 数据集本身完好可得 → 不是网络问题

本地缓存 `/Users/wangchenyu/.cache/aitester/swe_bench/swe_bench_instances.jsonl`（225 行，4.7 MB）：
- 真实 `repo` 分布：`pvlib/pvlib-python` 63、`pydicom/pydicom` 56、`sqlfluff/sqlfluff` 50、`pylint-dev/astroid` 31、`pyvista/pyvista` 16、`marshmallow-code/marshmallow` 9
- 上述 20 个 instance_id **20/20 全部命中**；例：`sqlfluff__sqlfluff-4764` → `repo=sqlfluff/sqlfluff`、`base_commit=a820c139ccbe`、`FAIL_TO_PASS=149` 条、`test_patch` 2781 字符

⚠️ 附带发现：该缓存只有 **225 条**（官方 SWE-bench Lite 为 300 条），且被选中的 20 条**全是 sqlfluff**（非随机抽样），因此即使跑通也**不构成对 SWE-bench Lite 的代表性声明**。

### 3.3 另一个运行日志显示失败于 API 限流 + 超时

`experiments/results/swebench_20_summary.json`：`:6` `tasks_completed=7`、`:8` `tasks_timeout=10`（共尝试 20）、`:12` `pass_rate: "0/7 (0%)"`、`:13` `notes: "All 7 completed tasks failed due to API rate limiting (429 errors)"`、`:16` `issues: ["API rate limiting (429) from all configured endpoints", "International Agnes API returned 404 (model not found)", "Experiment timed out at 600s limit after 7/20 tasks"]`、`:25` `total_available=225`。
配套运行日志 `experiments/results/swebench_20_run.log` / `swe_bench_lite_20.log` 中**没有** clone/网络报错，失败信息是"第 1/2 次执行失败，尝试重试"+"测试代码语法错误: invalid syntax"。

### 3.4 唯一"真实执行"的一批：仍全数挂在补丁应用

`experiments/results/raw/sqlfluff__*/aitester.json`（20 个目录）含真实仓库上下文（`_lint_aliases_in_join`、`LintFix`/`LintResult` 等真实代码符号）。逐任务 `output` 字段（例：`experiments/results/raw/sqlfluff__sqlfluff-1625/aitester.json:185`）：

```
[FAIL_TO_PASS baseline] 0/1 passed
[FAIL_TO_PASS after-llm-patch] 0/1 passed
[PASS_TO_PASS] 8/64 passed
[llm_patch_apply_failed] 补丁未成功应用（判定按 FAIL_TO_PASS 实测）
```

- **20/20 目录命中 `llm_patch_apply_failed`**（`grep -rl` 计数 = 20）→ 补丁从未落地
- `FAIL_TO_PASS baseline` 与 `after-llm-patch` **逐任务完全相同**（Lead 独立复核一致）→ 无任何行为改变
- 更严重：`PASS_TO_PASS` 基线只有 **8/64**（健康环境应为 64/64）→ **环境本身未就绪**

### 3.5 全仓库 SWE-bench 运行一览（`experiments/results/**/benchmark_swe_bench*.json`，17 文件 329 行）

| 类别 | 运行数 | 说明 |
|---|---|---|
| `repo=unknown`（无 checkout） | 8 个运行 / 135 行 | 2026-08-17(10)、2026-08-18(**声称 0/20 的主工件**)、2026-09-26 五个 lite20 运行、2026-09-29 retest(5) |
| `repo=sqlfluff/sqlfluff`（有 checkout） | 11 个运行 / 191 行 | 2026-09-25~09-29 共 190 行中 **0-1 通过**；最高 **1/20（5%）**，出现在 `benchmark_swe_bench_20260925_184622.json`（plain_llm 与 single_agent 各 1） |
| 非 SWE-bench 的真实仓库（examples/*） | 1 个运行 / 3 行 | `benchmark_swe_bench_20260921_175906.json`，`examples/calculator` 等，2/3 通过 —— **是自带示例仓库，不是 SWE-bench** |

**判定**：`0/20` 作为"负结果如实披露"是诚实的，但它**不能**被读作"系统在 SWE-bench Lite 上得 0 分"；实际是"**外部基准从未成功运行**"。项目若需要外部有效性证据，必须重跑一次补丁能落地的 SWE-bench 子集。

---

## §4 SHA256SUMS 抽样校验结果

- 文件：`experiments/results/main_batch/SHA256SUMS`（261,837 字节，**2029 条目**）
- 条目构成：`traces/*.jsonl` 2007 + `*.json` 12 + `*.md` 10 + `.mimosa/hook-*` 2
- 抽样方法：等距抽样 **20 条**（步长 101），用 `hashlib.sha256` 对实际字节重算比对（等价 `sha256sum -c`）
- **结果：匹配 20/20，不匹配 0，文件缺失 0**
- 涵盖 `benchmark_synthetic_20261006_140906.json`（`:6`，记录 `6e31c07d…4aec`）等核心工件

⚠️ 限定：SHA256SUMS 覆盖 `experiments/results/main_batch/` 全目录（含 10 个 `.md` 报告本身），**但抽取的 20 条等距样本恰好未覆盖 2 个 `.mimosa` 条目**；且该校验只能证明"文件未被事后改动"，**不能证明文件内容正确**（哈希由同一批运行写入）。未做 100% 全量校验（2007 个 trace × 平均 130KB ≈ 260MB，超出本轮时间盒）。

---

## §5 统计显著性独立重算

详见 §2.9。要点：

| 量 | 我重算 | 项目声称 |
|---|---|---|
| E2 δ（aitester vs df） | **−0.3673** | −0.3673 ✅ |
| E2 95% 可信区间 | **[−0.4556, −0.2789]** | [−0.4552, −0.2785] ✅ |
| E2 McNemar χ²(校正) / 列联表 | **45.3065**，(16,4,58,65)，n=143 | 45.3065，(—,62,—)，143 ✅ |
| R-P0-2 合并 δ / CI | **−0.2787** / **[−0.3481, −0.2090]** | −0.279 / [−0.348,−0.209] ✅ |
| R-P0-2 合并精确 McNemar p | **1.72e-13** | 与 Lead 的 1.7e-13 一致 ✅ |
| 任务级聚类 bootstrap（k=87） | δ=**−0.2833**，95%CI **[−0.3598, −0.2083]** | 未声称（项目给 i.i.d. CI）—— 聚类后仍显著为负 |

**方法学保留**：项目「贝叶斯 δ」实为均匀 Dirichlet 先验下的收缩点估计（解析式 `(a_only−b_only)/(n+4)`），不是频率派配对差估计；两者在 n=240 时数值接近，但**置信区间不可互换解读**。项目未做多重比较校正即并列 6 个对比。

---

## §6 无法重算清单

| # | 项目 | 状态 | 原因 |
|---|---|---|---|
| 1 | `BASELINE.yaml:17` 行内注释的 **5323 passed** | **无法重算** | 需要当时的代码状态/命令行参数；本次三次实测（串行 ×2、`-n 4` ×1）均为 **5390 passed**，注释值与实测差 67，且注释未记录命令、路径、选择器。属"不可复现的历史声称"，非"算不出来"。 |
| 2 | 历史批 false_fix **89.8%** 的**确切算法** | **无法完全重算** | 逐行字段口径给 90.0%（45/50）；89.8% = 44/49 只在"分子取 passed 行、分母取 detection 可测行"这一**未在任何脚本/工件中登记**的筛选下成立。仓库内无生成该数字的脚本或 JSON 产物，无法确认其确切分母定义。（`audit_2026/T_A_claims_traceability.md:413` 自述"未逐行复算"，与此一致。） |
| 3 | repair 39.31% 的**机器可读输出工件** | **不存在** | 57/145 仅存在于 `corrected_report_v2.md` 文本与脚本 stdout；仓库无对应 JSON/CSV。我的重算须重跑 800 次 pytest，结果依赖当前（已修复的）代码状态。 |
| 4 | SWE-bench Lite **官方 300 条**口径 | **无法评估** | 本地缓存只有 225 条；被选中的 20 条全为 sqlfluff（非随机）；且从未成功 checkout+apply。无法给出任何 SWE-bench Lite 分数。 |
| 5 | `agnes-3.0-flash` 成本 | **无法计算** | `price_table.json:11-14` 价格与 source 均为 null；用到该模型的批次 $/task 不可得。主批次未用到，故头条 0.0259/0.0045 不受影响。 |
| 6 | `spec_compile_rate ~0.21` 的**任务级分布/显著性** | **无法重算** | 仅 158/348 行有值（45.4% 覆盖），且仅 aitester 臂；其余臂全 `None`，无法做任何配对检验。 |
| 7 | detection 的**原始 pytest rc 证据** | **无法直接重放** | traces/*.jsonl 只有 6 行/任务（`task_start/node/task_end`，含 `passed`/`token_usage`），**不记录 buggy/fixed 两侧 rc 与输出**；无法从 trace 独立重建 F2P 判定，只能采信结果行已算好的 `detection_rate` 字段。 |
| 8 | 2007 个 trace 的**全量** SHA256 校验 | **未完成** | 时间盒限制（≈260MB），只做 20 条等距抽样（20/20 通过）。 |

---

## §7 一句话结论

**经独立重算，项目最硬的一组数字是真的：detection 三臂 15.8% / 1.5% / 44.8%、repair 39.31%（57/145，连 v1→v2 的跨文件归因 +5 行）、修正 false_fix 87.16%（380/436）、$/task 0.0259 vs 0.0045、统计 δ 与 CI（−0.3673 / [−0.4556,−0.2789]）、SHA256SUMS 20/20 全部逐位复现；但四个头条口径不成立或需重写：(a) 测试数 **5389 应为 5390**（同行注释的 5323 差 67，无法复现）；(b) 历史 false_fix **89.8% 应为 90.0%**（89.8% 用了一套分子分母不匹配的筛选）；(c) 修正 false_fix **87.2% 是跨 10 文件的代际合并口径，主批次三文件只有 76.9%**；(d) **SWE-bench 0/20 不是"跑了但 0 成功"而是"外部基准从未成功运行"**（主工件 20/20 `repo=unknown`、无 checkout、被测代码语法错误；唯一真实执行的一批 20/20 `llm_patch_apply_failed` 且 P2P 基线仅 8/64），因此**该项目目前没有任何外部有效性证据**。**

---

*重算脚本：`_independent_audit/ws2_recompute.py`（§0–§9，只读原始工件，不读任何 .md）。本报告所有数字均可由该脚本一条命令复现。*
