# T-A 独立声明溯源审计（零 LLM 复算）

- 审计执行者：独立评审团队 T-A（claims-auditor）
- 执行时间：2026-10-11 10:15–11:05（Asia/Shanghai）
- 工作目录：`/Users/wangchenyu/Workspace/AITester`（git HEAD `d9e51df`，**工作树 dirty：`git status --short` 共 59 项**）
- 解释器：`.venv/bin/python`（3.14）；机器上另有 2 个**孤儿 pytest 进程**（见缺陷 D-01）持续占用 ~2 核
- 纪律声明：本报告不采信 `README.md` / `BASELINE.yaml` / `CHANGELOG.md` / `INDEPENDENT_REVIEW_2026-10-10.md` / `REVIEW_2026_FRONTIER.md` / `review_2026/*.md` 的任何结论。**下文每个"复算值"均由我本人在原始工件（`experiments/results/**`）上重新计算得到**，命令见 §7。项目自评数字一律作为"待验证声明"处理。
- 零 LLM 声明：全程未调用任何 LLM API；未开实验批次；未跑 `run_benchmark`/`run_main_batch`。允许的写操作仅限 `audit_2026/`（临时脚本）与本文件。

## 0. 证据等级定义（本报告自定义，先声明后使用）

| 等级 | 定义 |
|---|---|
| **A** | 用入库原始工件逐位复算，与声明值一致（差异仅来自四舍五入）；工件路径 + 命令 + 数值齐备 |
| **B** | 数值可复算，但**口径需限定**：分母/子集/批次未披露、跨批次拼接、或存在**伪重复**（同一实验被重复计数） |
| **C** | 部分一致：数值或文字标注有可指认的偏差（如标 12 实测 13），或仅总量可核、分项不可核 |
| **D** | 不一致：复算值与声明值冲突，或声明定性被工件直接否证 |
| **E** | 无法溯源/无法验证：无入库工件、无对应字段、被后续修复取代，或在当前环境无法测量 |

---

## 1. 声明复核总表

> 位置列格式 `文件:行`。复算命令简写见 §7 命令清单（`P<n>` 对应脚本）。"复现性"列为 可复现 / 部分可复现 / 不可复现 / 无法溯源。

### 1.1 tests 与 static_checks 节

| 编号 | 位置 | 声明内容 | 原始工件/依据 | 复算值 | 声明值 | 判定 | 复现性 | 等级 |
|---|---|---|---|---|---|---|---|---|
| T-01 | `BASELINE.yaml:17` | 全量 pytest `total_passed=5262` | 当前工作树 tests/（262 个测试文件） | 实测 **5311 passed + 2 failed + 3 skipped + 1 xfailed**；`--collect-only` **5317** | 5262 passed / 0 failed | 与声明冲突（且**项目自带守卫** `test_tests_and_mypy_are_current` 断言 `5317−5262 ≤ 9` 失败，报"BASELINE 数字可能已过期"） | 不可复现 | **D** |
| T-02 | `BASELINE.yaml:17` 注释 | "--collect-only 收集 5259" | 同上 | **5317 tests collected in 2.17s** | 5259 | 不一致（+58） | 不可复现 | **D** |
| T-03 | `BASELINE.yaml:18` | `total_failed: 0` | 同上 | **2 failed**：`TestEnvSnapshotCompleteness::test_gate_reports_no_missing`、`TestBaselineNumbersConsistency::test_tests_and_mypy_are_current` | 0 | 不一致 | 不可复现 | **D** |
| T-04 | `BASELINE.yaml:19` | `total_skipped: 3` | 同上 | **3 skipped** | 3 | 一致 | 可复现 | **A** |
| T-05 | `BASELINE.yaml:20` | `total_xfailed: 1` | 同上 | **1 xfailed** | 1 | 一致 | 可复现 | **A** |
| T-06 | `BASELINE.yaml:22` | `suite_seconds: 35`（注：xdist -n 4 实测 34.5s） | 同上 | 串行 **223.21s**；`-n 4` **82.28s**（受 D-01 两孤儿进程抢核影响，不能排除负载混杂） | 35 | 量级一致但数值差 2.4× | 部分可复现 | **C** |
| T-07 | `BASELINE.yaml:21` | `slim_environment: 1863` | 需精简依赖环境 | 未测（需卸载 chromadb/matplotlib 类依赖，超出只读审计范围） | 1863 | 无法验证 | 无法溯源 | **E** |
| S-01 | `BASELINE.yaml:82` | `ruff_warnings: 0` | 全仓（除我自己的 `audit_2026/`） | `ruff check . --extend-exclude audit_2026` → **All checks passed**；`ruff format --check` → 591 files already formatted | 0 | 一致 | 可复现 | **A** |
| S-02 | `BASELINE.yaml:83` | `mypy_errors: 0` | src/ + config.py | `mypy src/ config.py` → **Success: no issues found in 123 source files** | 0 | 一致 | 可复现 | **A** |
| S-03 | `BASELINE.yaml:84` | `mypy_source_files: 120` | 同上 | **123** | 120 | 不一致（+3） | 不可复现 | **D** |
| S-04 | `BASELINE.yaml:81` | `ruff_version: 0.16.3` | venv | `ruff --version` → **0.16.3**；`mypy --version` → **1.15.0** | 0.16.3 | 一致 | 可复现 | **A** |
| C-01 | `BASELINE.yaml:30` | `line_total_pct: 89`（89.56） | 需 `--cov=src` 全量跑批 | 未跑覆盖率；仓库根 `.coverage` 文件**仅含 1 个被测文件**（已退化，无法支撑任何结论） | 89 | 无法验证 | 无法溯源 | **E** |
| C-02 | `BASELINE.yaml:42` | `branch_total_pct: 83`（82.78） | 同上 | 同上 | 83 | 无法验证 | 无法溯源 | **E** |
| C-03 | `BASELINE.yaml:31-41` | 10 个核心模块逐文件行覆盖（70–91） | 同上 | 同上 | — | 无法验证 | 无法溯源 | **E** |
| C-04 | `BASELINE.yaml:43-46` | 核心路由分支覆盖 98/91/100 | 同上 | 同上 | — | 无法验证 | 无法溯源 | **E** |

### 1.2 target_quality 节（被测代码侧指标）

> 复算方法：对 `experiments/results/main_batch/benchmark_synthetic_*.json` 共 **10 个批次**逐行取 `details[].<field>`，剔除 None 后求**批次均值**，再看区间（与 BASELINE 注释口径一致）。

| 编号 | 位置 | 声明内容 | 复算值（我的批次均值区间） | 声明值 | 判定 | 复现性 | 等级 |
|---|---|---|---|---|---|---|---|
| Q-01 | `BASELINE.yaml:61` | aitester 被测行覆盖区间，注"10 批次区间（n=87/批）" | `[83.977, 93.58]`（10 批：5/5/50/87×7） | [84.0, 93.6] | 数值一致；**注记 n=87/批 错误**（含 2 个 n=5 冒烟批 + 1 个 n=50 批） | 可复现（口径需更正） | **B** |
| Q-02 | `BASELINE.yaml:62` | plain_llm 覆盖区间 [86.0, 97.2] | 全 10 批 `[70.4, 97.22]`；剔除 2 个 n=5 冒烟批后 `[85.96, 97.22]` | [86.0, 97.2] | 需**静默剔除 2 个批次**才成立，注记未披露 | 可复现（口径需限定） | **B** |
| Q-03 | `BASELINE.yaml:63` | plain_llm_df 覆盖区间 [81.5, 93.6] | `[81.483, 93.552]`（df 仅存在于 5 个批次） | [81.5, 93.6] | 一致；df 批次数（5）未披露 | 可复现（口径需限定） | **B** |
| Q-04 | `BASELINE.yaml:66` | aitester mutation_score [0.818, 0.976]，7 批 n=77–81 | `[0.8175, 0.9760]`，n=77/79/80/77/81/77/81 | [0.818, 0.976] | 逐位一致 | 可复现 | **A** |
| Q-05 | `BASELINE.yaml:67` | plain_llm mutation [0.951, 0.992] | `[0.9515, 0.9916]` | [0.951, 0.992] | 一致（0.9916→0.992） | 可复现 | **A** |
| Q-06 | `BASELINE.yaml:68` | plain_llm_df mutation [0.986, 0.997] | `[0.9856, 0.9968]` | [0.986, 0.997] | 一致 | 可复现 | **A** |
| Q-07 | `BASELINE.yaml:71` | spec_compile_rate aitester [0.205, 0.219]，"E1/E2 logic 档**四批次**" n=77/81 | `[0.2045, 0.2189]`；但 4 个文件实为**2 个种子 × 2 次重跑**（见缺陷 D-02），独立测量只有 2 个 | [0.205, 0.219] | 数值一致，**"四批次"计数失真** | 可复现（独立性存疑） | **B** |
| Q-08 | `BASELINE.yaml:74` | spec_expr_coverage [0.723, 0.741]，n=45/51 | `[0.7232, 0.7415]`，n=45/51 逐位一致；同 D-02 伪重复 | [0.723, 0.741] | 一致 | 可复现（独立性存疑） | **B** |
| Q-09 | `BASELINE.yaml:76` | specificity_gate aitester `{specific_red: 40, over_red: 66}` | 4 批之和 = 9+11+9+11=**40**、18+15+18+15=**66**；但其中 2 批与另 2 批**逐行同值**（D-02），实际 n 减半 | {40, 66} | 数值一致，跨批合计**双重计数** | 可复现（合计口径不成立） | **B** |
| Q-10 | `BASELINE.yaml:77` | specificity_gate plain_llm_df `{162, 140}` | 38+43+38+43=**162**、38+32+38+32=**140** | {162, 140} | 同上（双重计数） | 可复现（合计口径不成立） | **B** |
| Q-11 | `BASELINE.yaml:78` | "df 的 specific_red/over_red ≈1.16 而 aitester ≈0.61" | 162/140 = **1.157**；40/66 = **0.606** | ≈1.16 / ≈0.61 | 一致 | 可复现 | **A** |
| Q-12 | `BASELINE.yaml:59` | "aitester 覆盖率 84–94% 而检出率仅 **13–16%**" | 7 批（10-06/10-07）aitester detection：`10.3%–17.2%`（全行分母）或 `11.7%–19.0%`（非 None 分母）；R-P0-2 合并 `38/261=14.6%` / `38/240=15.8%` | 13–16% | **无法复算出该区间**（口径未注明，与任一自然口径都不吻合） | 部分可复现 | **C** |
| Q-13 | `BASELINE.yaml:72` | "AC 批后由**恒 0.0** 抬升到 ~0.21" | `ab1_validation/benchmark_synthetic_20261006_172151.json` aitester spec_compile_rate 均值 = **0.0000**（n=12） | 恒 0.0 | 一致 | 可复现 | **A** |

### 1.3 benchmark 节：R-P0-2 主批次（n=261/臂，3 种子）

> 基线：`benchmark_synthetic_20261006_{140906,151907,164357}.json`，seed 42/43/44，`git_dirty=true`，cache namespace seed42/43/44。

| 编号 | 位置 | 声明内容 | 复算值 | 声明值 | 判定 | 复现性 | 等级 |
|---|---|---|---|---|---|---|---|
| B-01 | `BASELINE.yaml:168`, `README.md:56` | df detection 44.8%（117/261） | **117/261 = 44.83%**（38+36+43） | 44.8% | 逐位一致 | 可复现 | **A** |
| B-02 | 同上 | aitester 15.8%（38/240，21 行 None 不进分母） | **38/240 = 15.83%**；None 行数 6+8+7=**21** | 15.8% | 逐位一致 | 可复现 | **A** |
| B-03 | 同上 | plain_llm 1.5%（4/261） | **4/261 = 1.53%** | 1.5% | 一致 | 可复现 | **A** |
| B-04 | `BASELINE.yaml:170` | δ(df vs plain_llm)=+0.426 | 配对 n=261，n10/n01=113/0；Dirichlet 后验均值 **+0.4264** | +0.426 | 逐位一致 | 可复现 | **A** |
| B-05 | 同上 | δ(aitester vs plain_llm)=+0.139 | 配对 n=240，37/3；后验均值 **+0.1393** | +0.139 | 逐位一致 | 可复现 | **A** |
| B-06 | 同上 | δ(aitester vs df)=−0.279（"−28pp"） | 配对 n=240，12/80；后验均值 **−0.2787**；**非配对差为 −28.99pp** | −0.279 | 一致；两种口径分别对应 −27.9pp/−29.0pp，均约 −28pp | 可复现 | **A** |
| B-07 | `BASELINE.yaml:156` | repair 修正口径 **39.31%（57/145）** | 我**独立重放** 10 个批次的全部带补丁行：R-P0-2 可重放 **145**、correct **57** → **0.3931** | 39.31% (57/145) | 逐位一致 | 可复现 | **A** |
| B-08 | `BASELINE.yaml:157` | E1/E2 修正 repair **54.72%（58/106）** | 独立重放：可重放 **106**、correct **58** → **0.5472** | 54.72% (58/106) | 逐位一致 | 可复现 | **A** |
| B-09 | `BASELINE.yaml:181` | "早期 10-01 批 **0/15 系真零**" | 独立重放：早期批次可重放 **15**、correct **0** | 0/15 | 一致 | 可复现 | **A** |
| B-10 | `BASELINE.yaml:157` | v1 口径 35.86%（52/145）/ 48.11%（51/106） | 未复算（需要"未清理围栏"的旧判分路径，当前代码已修） | 35.86%/48.11% | 无法验证（历史口径已被取代） | 无法溯源 | **E** |
| B-11 | `BASELINE.yaml:179`, `README.md:56` | 漏斗修正：patch 产出 **94%** / plausible **47%** / correct **39.31%** | 修复循环（`detection_first_status ∈ {red_then_green, red_not_repaired}`）**154/261**；带补丁 **145**（94.2%）；`patch_plausible=1` **72**（46.8%）；correct 57（39.31% of 145） | 94%/47%/39.31% | 逐位一致 | 可复现 | **A** |
| B-12 | `BASELINE.yaml:182-183`, `README.md:56` | $/task：aitester **0.0259** / plain_llm **0.0034** / df **0.0045** USD | 按 `experiments/price_table.json`（deepseek-flash in $0.3/M、out $1.2/M）× 三批 261 行 token_metrics：**0.02590 / 0.00345 / 0.00455** | 0.0259/0.0034/0.0045 | 逐位一致 ⚠️ 见缺陷 D-04（缓存命中不计 token ⇒ df/plain_llm 成本是下界） | 可复现（记账不完整） | **A** |
| B-13 | `BASELINE.yaml:178` | "三批次 git_dirty=true（--allow-dirty 口径跑批）" | 三批 `provenance.git_dirty` 全为 **true** | true | 一致 | 可复现 | **A** |
| B-14 | `README.md:56` | "主批次修正 false_fix=**87.2%**" | 同源重放 + 修正规则：passed 可测 **436**，false_fix **380** → **0.8716** | 87.2% | 逐位一致；**但 380 中 332 行为"根本没有补丁产出"**（仅 48 行为真实错误补丁），见 §5 解读 | 可复现（语义需解读） | **A** |
| B-15 | `README.md:56` | "CPR=84.3%"（ADR-0027 口径） | 同源重跑 `corrected_metrics` 得 **0.8451（60/71）**，与库内 `corrected_report_v2.md` 逐字节一致；我已独立复算分母：plausible 行 **144**、其中 correct **71** | 84.3% vs 84.51% | README 引用的是 v1 旧值（v1/v2 两版同指标两名） | 部分可复现（引用陈旧） | **C** |

### 1.4 benchmark 节：E4 / QuixBugs 真实基准

| 编号 | 位置 | 声明内容 | 工件的复算值 | 声明值 | 判定 | 复现性 | 等级 |
|---|---|---|---|---|---|---|---|
| B-16 | `BASELINE.yaml:306,326` | E4 首次跑 aitester detection **0/41** | `e4_quixbugs_aitester/benchmark_quixbugs_20261009_215514.json`：detection 非 None **41**，正例 **0** | 0/41 | 一致 | 可复现 | **A** |
| B-17 | `BASELINE.yaml:327` | repair **35/40 = 87.5%**；false_fix **2.5%** | repair 非 None **40**、正例 **35**；detection 非 None 行 false_fix 均值 **0.025** | 35/40；2.5% | 一致 | 可复现 | **A** |
| B-18 | `BASELINE.yaml:329-330,336-337` | token/task **17156**（df **2370**）；red_seen **40/41**、**41/41** | 41 个非测试驱动行均值：**17156.5** / **2370.4**；40/41、41/41 | 同左 | 一致（**分母为 41 缺陷程序**，而 detection/repair 用 41/40，口径已在同一区块混用） | 可复现（口径需披露） | **A** |
| B-19 | `BASELINE.yaml:364,381` | 修正后 aitester detection **17/37 = 45.9%** | `e4_quixbugs_FIXED_harness/aitester.json`：非 None **37**、正例 **17** | 17/37 | 一致 | 可复现 | **A** |
| B-20 | `BASELINE.yaml:364,381` | 修正后 repair **37/40 = 92.5%** | 行级 repair_rate 非 None **40**、`repair_rate==1.0` **37** | 37/40 | 数值逐位可复算；**但 13/37 行 `patch_correct=1` 同时 `patch_plausible=0`**（逻辑冲突，缺陷 D-05）；若要求"写盘成功 ∧ gold 通过"则仅 **24/40 = 60%** | 可复现（内部自相矛盾） | **C** |
| B-21 | `BASELINE.yaml:365,386` | df detection **31/37 = 83.8%** | 非 None **37**、正例 **31** | 31/37 | 一致 | 可复现 | **A** |
| B-22 | `BASELINE.yaml:364-365,385-386` | token **16038** vs **1905**，"成本高 **8.4×**" | 41 非测试驱动行均值 **16037.5** / **1905.3**，比值 **8.42×**（全 50 行口径为 15252.6/2309.3 = 6.61×） | 16038/1905/8.4× | 一致；分母（41）未在 BASELINE 披露 | 可复现（口径需限定） | **B** |
| B-23 | `BASELINE.yaml:382` | 伪影修正前后 McNemar：不一致对 17、χ²=15.059、p=1.042e-04、n10=17/n01=0 | 我的配对：n01=**17**、n10=**0**、χ²(cc)=**15.059**、渐近 p=**1.042e-04**（精确二项 p=1.5e-05） | 同左 | 一致（p 为 χ² 渐近值，非精确二项） | 可复现 | **A** |
| B-24 | `BASELINE.yaml:387` | 双臂终局 McNemar：不一致对 14、χ²=12.071、p=0.0005 | 我的配对：**14/0**、χ²(cc)=**12.071**、渐近 p=**5.12e-04** | 同左 | 一致 | 可复现 | **A** |
| B-25 | `BASELINE.yaml:432-435` | "**首轮** over_red 30/50（60%）detection 0%；specific_red 19/50（38%）detection 100%" | FIXED harness **终审**分布：over_red **30**（其中 20 行 detection 可判，正例 **0**）、specific_red **19**（17 行可判，正例 **17**=100%） | 30/50、19/50 | 数值一致，但工件只有**终审** verdict，**无"首轮"字段** ⇒ "首轮"标注不可验证 | 部分可复现 | **C** |
| B-26 | `BASELINE.yaml:466-468` | detection=None 的 4 任务：bitcount / find_first_in_sorted / sqrt / wrap，均为"缺陷实现不终止" | FIXED harness 中 detection=None 的 13 个任务 = 9 个 `*_test` 测试驱动 + **bitcount / find_first_in_sorted / sqrt / wrap** | 4 任务 | 一致 | 可复现 | **A** |
| B-27 | `BASELINE.yaml:369-371` | 第四起伪影零 LLM 复现："9/9 缺陷程序在 buggy/fixed 两侧均 rc=2"、"F2P 检出 0/7 → 6/7" | 唯一相关入库工件 `diagnostic_12task_prerepair.json` 的 12 行**没有 rc 列**（`rc`/`pytest_rc` 均为 None）；无 9 任务或 7 任务诊断工件 | 9/9；0/7→6/7 | 无入库证据 | 无法溯源 | **E** |
| B-28 | `BASELINE.yaml:484-489` | 孤儿 pytest 进程：observed 2、ppid=1、~100% CPU、uptime 56–63 分钟 | 我实测同机 **2 个孤儿进程**：`pid 36935/37116`，**ppid=1**、**~97% CPU**、**etime 16:31:25 / 16:30:18**（≈16.5 小时，远超声明） | 2 个 / 56–63min | 一致且更严重 | 可复现 | **A** |
| B-29 | `BASELINE.yaml:489` | "第 1 环未修"；`batch_hang_fix.tests: 12` | 代码层确认：`experiments/_m1_metrics.py:358-372` 用裸 `subprocess.run(timeout=)`，**无 `start_new_session`/killpg** → 孙进程可被 launchd 收养（与实测孤儿一致）。`tests/test_process_utils.py` 当前收集 **13** 例（声明 12） | 12 | 机制一致；测试数 13≠12 | 部分可复现 | **C** |
| B-30 | `BASELINE.yaml:374` | `measurement_artifact_4.regression_tests: tests/test_m1_packaged_tests.py::TestDualLayout（5 例）` | 收集 **5 tests** | 5 例 | 一致 | 可复现 | **A** |

### 1.5 benchmark 节：E6 / A1 / RT1 / D1 消融批次

| 编号 | 位置 | 声明内容 | 复算值（`e6_a1_batches/...`） | 声明值 | 判定 | 复现性 | 等级 |
|---|---|---|---|---|---|---|---|
| B-31 | `BASELINE.yaml:508-510` | E6 control：aitester **8/87 (9.2%)**、df **30/87 (34.5%)**、plain_llm **0/87** | 8 / 30 / 0（非 None 均 87） | 同左 | 一致 | 可复现 | **A** |
| B-32 | `BASELINE.yaml:518` | E6 control aitester vs df：χ²=**16.962**、δ=−25.3pp | 配对 n=87，n10/n01=2/24，χ²(cc)=**16.962**；朴素差 34.5−9.2=**−25.3pp** | 同左 | 一致 | 可复现 | **A** |
| B-33 | `BASELINE.yaml:399-402` | A1 消融"从未生效"：env_snapshot 中 `PLAN_STRIP_EXPECTED_OUTPUT_ENABLE` 缺失（null）、detection 与标准臂逐点相同 8/87 vs 8/87、日志 0 条生效行 | `a1_strip_seed42/benchmark_...180655.json` 的 `provenance.env_snapshot` **无该键**；detection **8/87**（与 control 完全相同） | null；8/87 | 一致（键缺失=未生效的直接证据） | 可复现 | **A** |
| B-34 | `BASELINE.yaml:539-541` | E6 phase1（冷缓存）：aitester **6/87 (6.9%)**、df **27/87 (31.0%)**、plain_llm **9/87 (10.3%)**；tokens 8857/2586/1257 | 6 / 27 / 9；token/task **8857.5 / 2586.4 / 1257.2** | 同左 | 逐位一致 | 可复现 | **A** |
| B-35 | `BASELINE.yaml:543-546` | E6 phase2（matched）：aitester **2/87 (2.3%)**、tokens 3735、`budget_capped 87/87`、top stop_reason `budget_exceeded 84`；df **23/87 (26.4%)**、tokens 2602、capped 1/87 | aitester：正例 **2**，但 detection **非 None 仅 11/87**（18.2%）；tokens 3734.6；capped **87/87**；`budget_exceeded` **84**。df：正例 **23**，非 None **86**（26.7%）；tokens 2602.1；capped **1** | 2/87、23/87 | 数字对，但**双臂分母不同源**（aitester 2/87 的 87 中 76 行从未判定）⇒ "matched 对照"非同类比较 | 可复现（口径需限定） | **B** |
| B-36 | `BASELINE.yaml:548-549` | phase2 主终点：df_matched vs aitester_standard χ²=13.474 p=0.0002；aitester_matched vs df_standard χ²=0.5 p=0.4795 | 配对 86 行，19 不一致，χ²(cc)=**13.474**，渐近 p=**2.41e-04**；另一对不一致 2、χ²=**0.5**、p=**0.4795** | 同左 | 一致（p 为渐近值） | 可复现 | **A** |
| B-37 | `BASELINE.yaml:551` | 预算工具性检验：df_standard vs df_matched Δ=−4.6pp、χ²=1.125、p=0.2888 | 27/87 vs 23/87 → **−4.6pp**；配对 86、不一致 8、χ²(cc)=**1.125**、渐近 p=**0.2888** | 同左 | 一致 | 可复现 | **A** |
| B-38 | `BASELINE.yaml:571-574` | RT1：plain_llm 10.3% · RT1 **11.5%（10/87）** · df 31.0%；tokens 1257/2368/2586；regenerated 0/87、77/87、76/87 | rt1 工件内只有 **1 个臂（df 形态）**：10/87、token 2368.4、regen>0 **77/87**；plain_llm 9/87 与 df 27/87 取自**另一批次** `e6_phase1`（1257.2、2586.4、regen 0/76） | 同左 | 数值一致，但三臂**跨批次拼接**（RT1 批内无对照臂） | 可复现（口径需限定） | **B** |
| B-39 | `BASELINE.yaml:577` / `:503` | RT1 变量为 `DETECTION_FIRST_SECTION_ENABLE=false` | 该键**不在** `rt1_no_reinforcement_seed42` 工件的 `provenance.env_snapshot` 中（envelope 与 D3 同类） | false | 开关生效性无法从工件验证 | 无法溯源 | **E** |
| B-40 | `BASELINE.yaml:296-303` | D1 JSON 修复：可解析率 **427/621 → 555/621**（+128） | 未找到 621 条 Planner 形态缓存响应的入库工件/日志 | 427/621→555/621 | 无法验证 | 无法溯源 | **E** |
| B-41 | `BASELINE.yaml:306-310` | D1 消融：空计划 **34/87 → 22/87** | 结果行**无"是否空计划"字段**，无从复算 | 34/87→22/87 | 无法验证 | 无法溯源 | **E** |
| B-42 | `BASELINE.yaml:311-315` | D1 副产物：detection 6.9%→8.0%、repair **15→20**、false_fix **75.9%→70.1%** | phase1 aitester 6/87=6.9%、repair 正例 **15**、false_fix 均值 **75.9%**；d1 批 7/87=8.0%、repair 正例 **20**、false_fix **70.1%** | 同左 | 逐位一致 | 可复现 | **A** |
| B-43 | `BASELINE.yaml:441-449` | over_red 段消融：detection 17/37→**19/37 (51.4%)**、env flag **true**、McNemar 不一致 8/χ²=0.125/p=0.7237 | `ablation_r9/over_red_section_verified.json`：`OVER_RED_SECTION_ENABLE='true'`、19/37；配对 37 行、不一致 8（3/5）、χ²(cc)=**0.125**、渐近 p=**0.7237** | 同左 | 一致（p 为渐近值） | 可复现 | **A** |
| B-44 | `BASELINE.yaml:453-457` | over_red 首跑"不作结论依据"：22/37 (59.5%)、env flag **null** | 工件 22/37；`env_snapshot` **无 OVER_RED_SECTION_ENABLE 键** | null | 一致（该文件被项目自我否决，处理正确） | 可复现 | **A** |
| B-45 | `BASELINE.yaml:459-463` | 消融开关未入快照（D3）②`tests/test_over_red_section.py`（**21 例**） | 当前收集 **23 tests** | 21 | 不一致（文档测试例数漂移，见 D-10） | 部分可复现 | **C** |
| B-46 | `BASELINE.yaml:521-523` | E6 matched 结论："**已执行：预算混杂被证否 → −28pp 归因编排结构**" | 支撑统计（B-35/B-36/B-37）可复算；但 matched 臂 aitester 仅 11 行可判定（B-35），阶段 2 的 cap 低于其实际需求（87/87 触顶） | 已执行/已证否 | 数值可复现，**结论强度**受 B-35 分母问题限制（声明自身也承认测的是"预算不足时编排表现"） | 部分可复现 | **C** |
| B-47 | `BASELINE.yaml:513-516`, `:479-482` | D2：缓存命中不计 token（`src/agents/base_agent.py:437`、LRU 快路径 :389） | 代码复核：`base_agent.py:383-395` 的缓存快路径（含 `_cache_ns` 命名空间逻辑）确实绕过使用量记账。**我实测的 `total_tokens==0` 行数**：R-P0-2（热缓存）aitester **0/261**、plain_llm **0/261**、df **35/261**；E1/E2 四批（热缓存）aitester **121/348**、plain_llm **348/348**、df **348/348**（两臂 token 总量为 **0**）；E6 control plain_llm/df **87/87**、aitester 50/87；E6 phase1（冷缓存）三臂 **0/87** | 已登记缺陷 | 一致（且我给出污染面量化：热缓存批次几乎必然污染，冷缓存批次为 0） | 可复现 | **A** |
| B-48 | `BASELINE.yaml:492-500` | A2：规约 oracle 注入 **合成 2–3/87（≈2.3%）**、**真实 QuixBugs 20/50 = 40%** | 全库 7153 行扫描：`spec_oracle_injected=True` 仅出现在 2026-10-10 的 3 个 llm_logic_ab 批次（25/19/18 行）；**E6 合成批与 E4 QuixBugs 批均为 0**；且 `oracle_type` 在全库 100% 为 `generated_test` | 2–3/87、20/50 | **无入库证据**（与声明批次不符） | 无法溯源 | **E** |
| B-49 | `BASELINE.yaml:474-478` | S6 通道：注入率 0/2→**1/2**、子句可编译 **3/5=60%**、规格产物 0→224 字符 | 未找到对应工件/日志 | 1/2；3/5 | 无法验证 | 无法溯源 | **E** |
| B-50 | `BASELINE.yaml:471-472` | spec_compile_rate 由 0.205–0.219 升至 **0.472–0.517** | 可复算的批次均值：phase1 **0.4722**、d1_json_repair **0.5167**、E4 aitester **0.4784**；即区间由**两个不同批次**拼出（0.472 与 0.517 分属 10-09 两批，配置不同） | 0.472–0.517 | 数值一致，跨批次拼接未披露 | 可复现（口径需限定） | **B** |

### 1.6 README 头部与 SWE-bench 相关声明

| 编号 | 位置 | 声明内容 | 复算值 | 声明值 | 判定 | 复现性 | 等级 |
|---|---|---|---|---|---|---|---|
| B-51 | `README.md:56` | "**SWE-bench Lite（sqlfluff-20）真实基准 0/20 负结果**与统计检验同样如实披露、不筛选" | 全库 `dataset∈{swe_bench, swe_bench_pro}` **24 个工件 / 365 行**：`detection_rate` 键 **0/365**；`task_metadata.instance_code` **100% 为空**；`passed=True` 仅 **4/365**；Aug-18 批 20 行 `repo` 全为 `unknown`、无 `generated_test`/`patch` 落盘；`error_category` = patch_validation_failed 148 / 空 125 / execution_trace_missing 59 / syntax 28 / 其他 5 | 0/20 负结果 | **"负结果"定性不被工件支持**：从未产生过 detection 测量（无该字段），且失败发生在判定之前（无源码、无补丁） | 不可复现（定性冲突） | **D** |
| B-52 | `README.md:1627` | "该批次实验受 API 限流影响，**结果未归档到仓库**" | 同名实验的工件**已入库** 365 行（含 `experiments/results/swe_bench_lite_20/benchmark_swe_bench_20260818_113525.json`）；同目录 `swebench_20_run.log` 内有 **7 条 403 insufficient_quota**（qwen-plus）与 12 条"测试代码语法错误" | 未归档 | 与仓库现状矛盾（同一 README 内两处互相冲突） | 不可复现 | **D** |
| B-53 | `README.md:1633-1635` | "管道与环境已全部修通，0/N 是 **LLM 引擎修复质量边界**，非管道/非环境" | Sep-25 三批 `repo='sqlfluff/sqlfluff'`（管道确已修通）；aitester 0/20×3，`error_category=patch_validation_failed` 18–20/20；plain_llm 臂 `error_category` 全为空串（无遥测）；single_agent 20/20 `execution_trace_missing`。**无任何行含 detection_rate 或 F2P 判定字段** | 非管道/非环境 | 定性无法用行级数据证实（无 F2P/检测字段）；且 plain_llm/single_agent 臂遥测缺失 | 部分可复现 | **C** |
| B-54 | `BASELINE.yaml:511-517` | E6 `env_snapshot` 缺 `PLAN_STRIP_EXPECTED_OUTPUT_ENABLE`（D3）+ followup"建议做成门禁（未实施）" | 该门禁**已实施**（`tests/test_2026_10_10_optimization_batch.py:40-54` 调用 `scripts/gates/check_env_snapshot_keys.py`），但**当前 exit 1**：3 个新开关（`EMPTY_PLAN_SHORTCUT_ENABLE`/`OPERATION_MAP_INJECT_ENABLE`/`PATH_ENUM_INJECT_ENABLE`，均定义于 `src/graph/nodes.py`）未登记入 `_env_snapshot_keys` | 未实施 | 已实施但**当前红**（同类事故复发，见 D-07） | 不可复现 | **D** |
| B-55 | `README.md:58` | "✅ **无硬编码密钥**（`.env*` / `.private` 已 gitignore / 删除）" | `git check-ignore` 确认 `.env`、`.env.local`、`.private/` 均被忽略；但工作树**存在** `.env.local`（含非空 `LLM_1_API_KEY`，≥20 字符）与 `.private/.env.local`；`llm_configs.json`（**已 tracked**）无密钥材料；`.env.local.template`（tracked）为占位符。项目自带 `.git-hooks/check_secret_leak.sh` **exit 1**，但命中的是 40 位 git SHA 等**误报**（`review_2026/*.md`、`experiments/run_payload_ab.py`） | 无硬编码密钥 | 未入库到 git 属实；本地明文凭证在盘属"已知可接受风险"（README 同段已声明），但**密钥泄漏守卫当前为红且误报率高** | 部分可复现 | **C** |
| B-56 | `BASELINE.yaml:565-570` | ci_gates_2026_10_09：`full_suite: 5107 passed / 3 skipped / 0 failed`、`guards: 10/10 exit 0` | 历史批次声明（2026-10-09）；**当前树**全量 = 5311 passed / 2 failed；`check_env_snapshot_keys.py` exit **1** | 10/10 exit 0 | 历史值无法回验；当前门禁红 | 无法溯源 | **E** |

> 全表共 **90 条**声明（含 §1.7 补充项），等级分布见 §2（由脚本对本文档"等级"列计数得出，非手工统计）。

### 1.7 补充声明（metrics_schema 声明 vs 实际落盘）

| 编号 | 位置 | 声明内容 | 复算值（全库 7153 行扫描） | 判定 | 等级 |
|---|---|---|---|---|---|
| M-01 | `BASELINE.yaml:128-153` | `metrics_schema` 声明 `patch_rollback_verdict`、`patch_rolled_back`（A-03 观测层） | **0/7153 行出现该键**（键名从未落盘） | 声明字段从未产出 | **E** |
| M-02 | 同上 | `regression_rate` 为核心三指标之一 | 键存在于 3968 行，**非 None 0 行**（恒未填充） | 从未产出 | **E** |
| M-03 | 同上 | `red_regression_violation`（双门协议观测） | 2997 行含键，**非 None 0 行** | 从未产出 | **E** |
| M-04 | 同上 | `deterministic_repair_status`（ADR-0019 观测层） | 1891 行含键，**非 None 0 行** | 从未产出 | **E** |
| M-05 | 同上 | `fl_at_k`（"定位维度随结果行并列输出"，`README.md:56`） | 仅 **784/7153 = 11.0%** 行非 None；E1/E2 四批中只有 2 批有值（且 3 个种子值为 0/1 混合） | 名义可得、实际覆盖率 11% | **C** |
| M-06 | 同上 | `patch_precision`（过拟合度量） | 非 None **685/7153**；行级取值仅 0.0/1.0；**无法作为聚合量**（见 D-05） | 口径缺陷 | **C** |

---

## 2. 复现性统计（我实际计数）

对 §1 表中 **90 条**声明逐条判定（计数由脚本对本文档"等级"列统计，可复算；分级明细见 §2.1）：

| 等级 | 条数 | 占比 | 含义 |
|---|---|---|---|
| **A** 可复现（逐位） | **43** | 47.8% | 原始工件重算一致 |
| **B** 可复现但口径需限定 | **11** | 12.2% | 数值对，但分母/子集/独立性有隐藏问题 |
| **C** 部分可复现 / 标注偏差 | **12** | 13.3% | 数值或文字标注有可指认偏差 |
| **D** 不可复现 / 定性冲突 | **7** | 7.8% | 与工件直接冲突 |
| **E** 无法溯源 / 无法验证 | **17** | 18.9% | 无工件、无字段或环境不可测 |
| 合计 | **90** | 100% | — |

> 计数命令（可复算）：
> `python3 -c "import re,collections;t=open('audit_2026/T_A_claims_traceability.md',encoding='utf-8').read();r=re.findall(r'^\|\s*(?:T|S|C|Q|B|M)-\d+\s*\|(.*)\|\s*$',t,re.M);print(collections.Counter(re.fullmatch(r'\*\*([ABCDE])\*\*',[x.strip() for x in l.split('|')][-1].strip()).group(1) for l in r))"`

### 2.1 逐条分级明细（供 Lead 抽查）

| 编号 | 等级 | 编号 | 等级 | 编号 | 等级 | 编号 | 等级 | 编号 | 等级 |
|---|---|---|---|---|---|---|---|---|---|
| T-01 | D | T-02 | D | T-03 | D | T-04 | A | T-05 | A |
| T-06 | C | T-07 | E | S-01 | A | S-02 | A | S-03 | D |
| S-04 | A | C-01 | E | C-02 | E | C-03 | E | C-04 | E |
| Q-01 | B | Q-02 | B | Q-03 | B | Q-04 | A | Q-05 | A |
| Q-06 | A | Q-07 | B | Q-08 | B | Q-09 | B | Q-10 | B |
| Q-11 | A | Q-12 | C | Q-13 | A | B-01 | A | B-02 | A |
| B-03 | A | B-04 | A | B-05 | A | B-06 | A | B-07 | A |
| B-08 | A | B-09 | A | B-10 | E | B-11 | A | B-12 | A |
| B-13 | A | B-14 | A | B-15 | C | B-16 | A | B-17 | A |
| B-18 | A | B-19 | A | B-20 | C | B-21 | A | B-22 | B |
| B-23 | A | B-24 | A | B-25 | C | B-26 | A | B-27 | E |
| B-28 | A | B-29 | C | B-30 | A | B-31 | A | B-32 | A |
| B-33 | A | B-34 | A | B-35 | B | B-36 | A | B-37 | A |
| B-38 | B | B-39 | E | B-40 | E | B-41 | E | B-42 | A |
| B-43 | A | B-44 | A | B-45 | C | B-46 | C | B-47 | A |
| B-48 | E | B-49 | E | B-50 | B | B-51 | D | B-52 | D |
| B-53 | C | B-54 | D | B-55 | C | B-56 | E | M-01 | E |
| M-02 | E | M-03 | E | M-04 | E | M-05 | C | M-06 | C |

**关键结论**：项目**核心实验数字**（detection 38/240、117/261、4/261；repair 57/145、58/106；$/task 0.0259/0.0034/0.0045；E4 17/37、37/40、31/37；E6 8/87、30/87；A1/RT1/D1 全部过程指标）**逐位可复现**，我未发现任何被凭空编造的实验数值。问题集中在**当前状态类声明（tests/static）**、**指标可得性声明**、**"四批次"伪重复**、**SWE-bench 定性**，以及**记账完整性**。

---

## 3. 关键机制性主张交叉检验（task-1 第 4 项）

### (a) detection aitester 15.8% vs plain_llm_df 44.8%（−28pp）—— **成立（A）**
- 复算：`38/240 = 15.83%`、`117/261 = 44.83%`、`4/261 = 1.53%`；与声明逐位一致。
- 配对：aitester vs df 共 240 任务，不一致对 **92**（12/80），McNemar χ²(cc)=**48.793**，精确二项 p≈0；Dirichlet 后验均值 δ=**−0.2787**（CI 见声明，未复算 MC 部分）。
- **限定**：分母不同源（aitester 240 vs df 261）——项目已在 BASELINE 显式披露 21 行 None，属诚实披露；如实披露这一点值得肯定。
- "−28pp" 是**贝叶斯后验均值**（−27.87pp）而非朴素差（−28.99pp），两者都约等于 −28pp，不构成误导。

### (b) 非特异过红机制（specific_red 40 / over_red 66 vs df 162/140）—— **可重算，但合计口径双重计数（B）**
- 逐行重算 4 个 10-07 批次的 `specificity_gate_verdict`：aitester `9+11+9+11=40` / `18+15+18+15=66`；df `38+43+38+43=162` / `38+32+38+32=140`。**声明值逐位正确**。
- **但**：批次 `161053`(seed42) 与 `181638`(seed42) 的 87 行 `detection_rate`、`specificity_gate_verdict`、`generated_test` **逐行完全相同**（87/87）；`170147`(seed44) 与 `185941`(seed44) 同样（87/87）。二者 git_sha 不同（`d3c3cc4e` → `1a5a5a79`）、cache namespace 相同（seed42/seed44）。
- ⇒ "跨批次合计" 的 n 被**系统性放大 2 倍**；比值 0.61 vs 1.16 仍成立（比值不受放大影响），但**样本量与统计功效的所有引用都会失真**（见 D-02）。

### (c) repair 39.31%（57/145）与 QuixBugs repair 92.5% —— **39.31% 成立；92.5% 数值可复算但口径内部自相矛盾（A / C）**
- **39.31%**：我独立重放 main_batch 全部 10 个批次、669 行（零 LLM，复用项目 `replay_row`，单行 <1s，200.4s 跑完）：R-P0-2 可重放 **145**、correct **57** → **0.3931**；E1/E2 可重放 **106**、correct **58** → **0.5472**；早期 **15/0** → 0.0000；裁决分布 `correct 115 / wrong_patch 151 / skipped_no_material 403`，与库内报告 `correct 115 / wrong_patch 151 / skipped_no_material 8 / no_patch 395` **完全同构**（403 = 8 + 395）。
- **分母构造**：145 = 三个 20261006 批次中 `patch` 字段非空的函数行数（54+46+45）。剔除规则在 `experiments/corrected_metrics.py:72-76`（无 patch → `no_patch`，出分母）与 `experiments/repair_replay.py:77-83`（有 patch 但 `task_metadata.test_cases` 空 → `skipped_no_material`；diff 形态 → `not_replayable_diff`；超时 → `unverifiable`，三者均出分母）；`analyze_arm` 在 `corrected_metrics.py:120-124` 把 `correct + wrong_patch` 作为"可重放"分母。E1/E2 的 106 与早期的 15（另有 8 行有 patch 无 gold 材料被剔除）同样如此。
- **两者口径差异**：（i）语料不同——R-P0-2 是合成单文件集、E4 是 QuixBugs 真实程序；（ii）**分子分母口径不同**——39.31% 的分母是"进了修复循环且产出补丁的可重放行"，E4 92.5% 的分母是"gold 判分非 None 的行"（40），且其分子同时要求 `patch_correct=1`；（iii）**独立裁决强度不同**——39.31% 由 `corrected_metrics` 事后重放（判分树=项目自实现），92.5% 直接读行内 `repair_rate` 字段。
- **92.5% 的严重限定**：FIXED harness 50 行中 **13 行 `patch_correct=1` 且 `patch_plausible=0`**（另 2 行反向），全部 `source_patched_unverified=True`、`patch_evidence_level='none'`、`stop_reason='skip_debugger_repair_invalid'`、`false_fix_rate=0.0`、`passed=False`。若把"写盘通道"也作为必要条件，则 repair = **24/40 = 60%**；若按全部 50 任务计 = **74%**。**32.5pp 的差距完全由这 13 行双通道冲突产生**（缺陷 D-05）。

### (d) SWE-bench Lite 0/20 —— **原始记录存在，但为"判定之前"的失败；"负结果"表述不成立（D）**
- 原始记录：`experiments/results/swe_bench_lite_20/benchmark_swe_bench_20260818_113525.json` 存在，20 行，`passed_count=0`。
- **不是检测测量**：该工件行只有 9 个键，**无 `detection_rate`**；全部 365 行 swe_bench/swe_bench_pro 工件均无该键（0/365）。
- **harness 无效的直接证据**：(1) 20/20 行 `repo='unknown'`（连仓库名都没解析出来）；(2) 无 `generated_test`/`patch` 落盘（0/20）；(3) `error_category` = syntax 19 + timeout 1，`diagnosis` 文本显示喂进去的"被测代码"是**描述性文本**（如"包含了一个无效的 decimal literal…这是一段描述性文本，不应该出现在 Python 代码文件中"）；(4) 上游数据缓存 `~/.cache/aitester/swe_bench/swe_bench_instances.jsonl` **225 行中 0 行有 `instance_code` 字段**（我逐行解析确认，无该键），即系统从未拿到源码；(5) 同名实验的兄弟日志 `experiments/results/swebench_20_run.log` 含 **7 条 403 insufficient_quota**（qwen-plus 免费额度耗尽）与 `swebench_20_summary.json`（2026-08-17）自述 "All 7 completed tasks failed due to API rate limiting (429 errors)"。
- **结论**：`0/20` 是"未评测/评测管道无效"的记录，**不能作为系统能力的负结果**；README 把它表述为"负结果如实披露"属于**定性错误**（同一 README 的另一处又承认"受 API 限流影响，结果未归档"，两处互相矛盾，见 B-52）。
- 附带：Sep-25 三批 repo 已正确解析（`sqlfluff/sqlfluff`），但 aitester 仍 0/20 且失败在 `patch_validation_failed`（补丁未通过静态守卫）——同样是**判定之前**；plain_llm/single_agent 臂 `error_category` 为空串或 `execution_trace_missing`，说明这些臂**没有可用遥测**。因此"LLM 引擎修复质量边界"的定性（B-53）在我可见的行级数据中无法证实。

### (e) $/task 0.0259 vs 0.0045 的 token 记账完整性 —— **计算正确，但记账不完整（A + D-04）**
- 计算链可逐位复现：`price_table.json`（deepseek-flash 输入 $0.3/Mtok、输出 $1.2/Mtok，source=官方价目页） × 三批 `token_metrics`（in 1,581,326 / out 5,234,651 for aitester 等） ÷ 261 → **0.02590 / 0.00345 / 0.00455**。
- **完整性缺陷**：(1) 缓存命中不计 token（D2，`src/agents/base_agent.py:383-395`、`:437`）——我实测 `total_tokens==0` 行数：R-P0-2 三批（热缓存）aitester **0/261**、plain_llm **0/261**、df **35/261**；E1/E2 四批（热缓存）plain_llm **348/348**、df **348/348**（两臂 token 总量为 0，完全无法计价）、aitester 121/348；E6 control plain_llm/df 各 **87/87**；冷缓存批次（E6 phase1）三臂 **0/87**。⇒ **df/plain_llm 的 $/task 系统性偏低（下界）**，aitester 贵 5.75× 的比值被高估（真实比值应更小）；R-P0-2 恰是污染最小的一批（df 仅 35/261 行为 0），故 0.0259/0.0045 本身可复算，但同族数字在 10-07 批次上**不可复算**。
- (2) 价目表为"峰时全额"，缓存命中价（$0.006/M）与错峰半价均未计入——项目已在 `price_table.json._comment` 中如实声明为保守上界，属**已披露**的口径选择。
- (3) 分母是任务数 261（含 21 行 detection=None 的死亡任务），其 token 也计入——口径本身自洽（成本按任务摊），但与 detection 的有效分母不同源，跨表引用易误读。

---

## 4. 端到端（全任务）修复率 —— 回答"39.31% 与 261 的分母关系"（Lead 交叉核对第 3 项）

同源重放（`replay_row`）后按不同分母计算：

| 口径 | 分子 | 分母 | 结果 | 说明 |
|---|---|---|---|---|
| 条件修复率（对外口径） | 57 | 145（产出补丁且可重放） | **39.31%** | 声明口径；排除 116 行"无补丁" |
| **全任务端到端（R-P0-2）** | 57 | **261** | **21.84%** | 含 116 行根本没产出补丁 |
| 全任务端到端（E1/E2） | 58 | 348 | 16.67% | — |
| 全任务端到端（10-06/10-07 七批） | 115 | 609 | 18.88% | — |
| 全任务端到端（main_batch 全 10 批） | 115 | 669 | 17.19% | 与修正报告的 115/669 行级分布一致 |
| **含"零修复尝试"的诚实分解** | 296/609 = **48.6%** 的 aitester 行是 `all_green_unverified` + `iterations=0` + 无补丁 | 609 | — | 这些行被记 `repair=0`；它们不是"修错了"，而是**从未进入修复通道** |

要点：**39.31% 与 261 不是同一分母**。39.31% 是"补丁产出条件下的成功率"，无条件端到端约 **17–22%**。对外引用 39.31% 时必须同时给出 145 的构成（否则读者会误以为 261 任务里有四成被修好）。项目 README 已写"57/145 可重放行"，属**已披露**，但同句未给全任务分母，易被误读为 261 口径。另注：BASELINE 引用的 `repair_ceiling_report.md` 漏斗（154/261→145→72→57，即 94.2%/46.8%/39.31%）中**每一个分子分母我都独立复算一致**（该报告原文本身未读，仅核 BASELINE 转述与其所称工件）。

---

## 5. 新发现的缺陷 / 测量伪影（既有评审未记录或未量化）

> 每条附"零 LLM 复现命令"。**D-01/D-02/D-03/D-05 是我认为最重要的四条。**

### D-01 【严重】孤儿 pytest 进程仍在烧 CPU，且机制已定位到未修复的代码路径
- 证据（我实测）：`ps -o pid,ppid,pcpu,etime -p 36935,37116` →
  `36935 ppid=1 97.6%CPU etime=16:31:25`、`37116 ppid=1 96.3%CPU etime=16:30:18`；命令行分别为 `aitester_m1_bitcount_.../test_bitcount.py`、`aitester_m1_find_first_in_sorted_.../test_find_first_in_sorted.py`。
- 代码依据：`experiments/_m1_metrics.py:358-372` 的 `subprocess.run(..., timeout=timeout)` **没有 `start_new_session=True`**，超时只杀直接子进程 → 孙进程被 launchd 收养（ppid=1）并永久持有管道。项目已修 `branch_coverage_inject`（`src/utils/process_utils.py::run_with_timeout`）但**未接到 M1 判分路径**。
- 影响：单机 2 核被占 >16 小时；我的全量 pytest（223s）与 xdist（82s）耗时均受此污染；任何在病态 QuixBugs 任务上跑的批次都会持续累积孤儿。
- 零 LLM 复现：`ps -o pid,ppid,pcpu,etime -p $(pgrep -f aitester_m1 | paste -sd, -)`；`grep -n "subprocess.run" -A 16 experiments/_m1_metrics.py`
- 处置建议（供 Lead）：不要擅自 kill（它们是缺陷的活证据，且可能是别的会话的产物）；登记为 P0 并给 `_run_pytest_in_tmp` 换 `run_with_timeout`。

### D-02 【严重】E1/E2"四批次"是伪重复：2 个种子 × 2 次重跑，跨批合计放大 2 倍
- 证据：`benchmark_synthetic_20261007_161053.json`(seed42) 与 `_181638.json`(seed42) 对全部 3 臂 **87/87 行** `detection_rate`、`specificity_gate_verdict`、`generated_test` **逐行相同**；`_170147`(seed44) 与 `_185941`(seed44) 同样。批次均值在所有 target_quality 指标上也逐位相同（cov 86.4138/90.6322、mut 0.8585/0.8175、spec 0.2045/0.2189、expr 0.7415/0.7232）。
- 影响面：`specificity_gate` 合计（40/66、162/140）、`repair 58/106`、`spec_compile_rate [0.205,0.219] n=77/81`、`spec_expr_coverage n=45/51` 全部按"4 批"计数；独立实验单位实际只有 **2 个**。
- 代码侧的自我矛盾：`src/agents/base_agent.py:383-386` 注释明确承认"同 seed 复跑仍共享缓存 ⇒ 统计独立性失效"，但 BASELINE 仍把同 seed 重跑算作独立批次。
- 零 LLM 复现：`P12`（逐行比对脚本）。
- 建议：把 4 批折成 2 个独立单位重报区间/合计，或在文档中显式标注"重跑非独立重复"。

### D-03 【高】当前树"全绿"声明失效：全量 2 failed，且两个失败都指向基线自身失真
- `2 failed, 5311 passed, 3 skipped, 1 xfailed in 223.21s`（xdist -n4：82.28s，同样 2 failed）。
- `TestBaselineNumbersConsistency::test_tests_and_mypy_are_current`：断言消息 `实收 5317 − passed 5262 = 55 > 9（BASELINE 数字可能已过期，请跑全量 pytest 后刷新）`——**项目自己的守卫否定 BASELINE**。
- `TestEnvSnapshotCompleteness::test_gate_reports_no_missing`：`scripts/gates/check_env_snapshot_keys.py` exit 1，缺失 3 键（见 D-07）。
- 时间线证据：BASELINE.yaml mtime **10-10 22:43**，而 `tests/` 下 8 个文件 mtime **10-10 23:04–23:30**（晚于基线落盘）⇒ "5262" 在其写下的时刻可能成立，但**当前修订不可复现**，且**未按 `last_verified` 流程刷新**。
- 零 LLM 复现：`P01`、`P02`。

### D-04 【高】token 记账不完整污染成本结论（污染面已量化）
- 我实测的 `total_tokens==0` 行数（`P13`）：
  - R-P0-2 三批（热缓存）：aitester **0/261**、plain_llm **0/261**、**df 35/261**（=8+13+14，与工件逐批一致）。
  - E1/E2 四批（热缓存）：aitester **121/348**、plain_llm **348/348**、df **348/348**；且 plain_llm/df 两臂 `token_metrics.total_tokens` 均为 **0** —— 这两批**完全无法计价**。
  - E6 control（热缓存）：plain_llm **87/87**、df **87/87**、aitester 50/87。
  - E6 phase1（冷缓存）：三臂 **0/87** —— 说明该缺陷与缓存开关**严格同现**，机制定位成立。
- 含义：`$/task` 的 df/plain_llm 值是**下界**（少算了缓存命中的真实计费），"aitester 贵 5.75×" 被系统性高估；R-P0-2 的主成本数字（0.0259 vs 0.0045）恰好落在**污染最小**的一批（df 仅 35/261 行为 0），但同族结论在 10-07 批次上**不可复算**。E4 的 "8.4×" 同源问题（df 1905 亦为缓存复用后均值）。
- 零 LLM 复现：`P13` = `audit_2026/a28_zerotok.py`。

### D-05 【高】`patch_correct=1` 与 `patch_plausible=0` 共 129 行并存 → `patch_precision` 聚合值可 >1
- 全库扫描（`P14`）：**129 行**同时满足 `patch_correct==1 ∧ patch_plausible==0`，逐文件：`e4_quixbugs_FIXED_harness/aitester.json` **13**、`ablation_r9/over_red_section_verified.json` **13**、`ablation_r9/over_red_section_firstrun_NOTVERIFIABLE.json` **13**、`ablation_r9/a1_strip_fixedharness.json` **12**、`e4_quixbugs_aitester` **11**、`llm_logic_ab_*/c2 8`、`c1 7`、`_superseded` 三批 **26**、`r4_batches` 三批 **13**、其余 6 个文件共 **13**（a1_strip_seed42 4 / d1 2 / diagnostic_12task 3 / e6_control 2 / e6_phase1 2）。反向（`plausible=1 ∧ correct=0`）在 FIXED harness 有 **2** 行。
- 定义依据：`experiments/run_benchmark.py:602-618` `_patch_plausible` 只看 `final_state["repair_history"][-1]["patch_applied"]`（**最后一条**修复历史），而 `:621-635` `_patch_correct` 走 gold 独立裁决；`_patch_precision`（`:638-643`）= correct/plausible，隐含 `correct ⊆ plausible`，但数据违反该不变量。
- 连带伪影：`review_2026/E2_fence_recompute.json` 的 `groups_summary.e6_a1_batches.precision_original = 1.0648`（**precision > 1**，不可能值）——正是 Σcorrect(263)/Σplausible(247) 这种跨口径聚合的产物。
- 影响：E4 的 92.5% 与 60% 相差 32.5pp；`patch_precision` 在 13 行被迫为 None（分母 0），"过拟合度量"实际覆盖不全。
- **定性（回答 Lead 第 5 项）：属记账缺陷，不是口径定义差异。** 判据三条：(1) 项目自己在 `experiments/run_benchmark.py:1114-1120` 把 `patch_precision` 定义为 `correct / plausible` 并声明"无 plausible 时 None"，该定义**隐含 `correct ⊆ plausible` 不变量**，数据违反它；(2) `patch_plausible` 的取值来源 `final_state["repair_history"][-1]["patch_applied"]` **从未落盘**——我扫描全库 **7153 行，`repair_history` 键出现 0 次**，故该字段无法从任何工件复核，只能信任单一写盘点；(3) 13 行同时是 `source_patched_unverified=True` + `patch_evidence_level='none'` + `passed=False` + `repair_rate=1.0`，即"未被证实写入源码"却"被判定修复成功"，两个通道给出相反结论而工件没有任何仲裁字段。三者叠加只能是记账口径未对齐，而非有意设计的两套口径。
- 零 LLM 复现：`P14`。

### D-06 【中】被声明的指标从未落盘（schema 声明 ≠ 实际可得）
- `patch_rollback_verdict` / `patch_rolled_back`：**0/7153 行**出现（键都不存在）。
- `regression_rate`：3968 行有键，**非 None 0 行**；`red_regression_violation`：2997 行有键，**非 None 0 行**；`deterministic_repair_status`：1891 行有键，**非 None 0 行**。
- `fl_at_k` 仅 11.0% 行有值；`spec_oracle_injected` 仅 120/7153（1.7%）。
- 影响：任何"观测层已落地"的表述缺少行级证据；引用这些指标时读者会以为可得。
- 零 LLM 复现：`P15`。

### D-07 【中】env_snapshot 门禁复发（与 A1 假阴性同类）
- `scripts/gates/check_env_snapshot_keys.py` → 扫描 122 文件、开关全集 78、快照 99 键、覆盖 75、**缺失 3**：`EMPTY_PLAN_SHORTCUT_ENABLE`、`OPERATION_MAP_INJECT_ENABLE`、`PATH_ENUM_INJECT_ENABLE`（均定义于 `src/graph/nodes.py`），exit 1。
- 讽刺点：锁定该事故的测试 `test_key_incident_switches_registered` 只检查 6 个**具名探针**，所以**通过**；而真正扫描全量的门禁**失败**——门禁与测试口径不一致。
- 影响：这 3 个新开关的干预生效性不可审计，正是 A1（PLAN_STRIP 未生效却记"零效应"）与 D3（OVER_RED 未入快照）**同一类事故的第三次复发**。
- 零 LLM 复现：`P16`。

### D-08 【中】`repair_replay.build_report` 的"带补丁行"列是行数而非补丁数（误导性表头）
- `experiments/repair_replay.py:156-159` 把单元格值算成 `replayed + not_replayable_diff + skipped_no_material` = **该批次总行数**，而表头写"带补丁行"。
- 实证：`python -m experiments.repair_replay experiments/results/main_batch/benchmark_synthetic_20261006_140906.json --arm aitester` 会输出"带补丁 87 行"，而该批真实带补丁行只有 **54**（其余 33 行是空 patch）。本团队 Lead 的交叉核对消息即据此写下"带补丁 87 行"，属**已被该表头误导的实际案例**。
- 影响：任何按该报告核对分母的人都会算错（这也是 `corrected_report_v2.md` 用另一种口径的正确原因）。
- 零 LLM 复现：`P17`。

### D-09 【中】stop_reason 遥测只覆盖编排臂，跨臂比较结构上不可比
- R-P0-2：`stop_reason='unknown'` 占比 aitester **8.0%（21 行 None）**、plain_llm **12.3%**、plain_llm_df **97.3%**；E1/E2 类似（9.2/12.1/97.7%）；E4 QuixBugs df 臂 **50/50 = 100% unknown**。
- 影响：任何"两臂 stop_reason 分布不同"的推论都不成立；E6 phase2 的 `budget_exceeded 84` 只对 aitester 有意义（df 臂 39/87 仍是 unknown，仅靠 `token_budget_capped` 标志可判）。
- 零 LLM 复现：`P18`。

### D-10 【低-中】文档引用的测试例数与当前树不符
- `test_process_utils.py` 收集 **13**（声明 12）；`test_over_red_section.py` 收集 **23**（声明 21）；`TestDualLayout` 收集 **5**（声明 5 ✓）。
- 影响：轻微；但"12 个单元测试"是 hang 修复的验收证据之一，应刷新。
- 零 LLM 复现：`P19`。

### D-11 【低】密钥泄漏守卫误报且当前阻断
- `.git-hooks/check_secret_leak.sh` exit **1**，命中物为 40 位 git SHA（`review_2026/E2_fence_recompute.json` 的 `provenance_git_sha`、`experiments/run_payload_ab.py` 的 sha256）与文档正文（`--per-task-token-caps` 等），全部**误报**；被扫文件主要为 untracked 的审查产物。
- 未发现任何真实密钥进入 git：`.env`、`.env.local`、`.private/` 均被 `.gitignore` 覆盖（`git check-ignore -v` 逐项确认）；`llm_configs.json`（tracked）经字段扫描无密钥材料。
- 风险提示（不粘贴明文）：工作树 `.env.local` 与 `.private/.env.local` **各含一份非空 API Key**（本地磁盘明文，未入库）。
- 零 LLM 复现：`P20`。

### D-12 【低】`ruff check .`/`ruff format --check .` 当前为红——但**起因是本审计自身**的 `audit_2026/` 目录
- `ruff check .` → 341 errors，**全部**落在 `audit_2026/*.py`（我的临时脚本，29 个文件）；`--extend-exclude audit_2026` 后 **All checks passed**、`591 files already formatted`。
- 我的处理：不改项目配置（越权），如实登记。若项目后续要在 clean tree 上跑 `ruff check .`，请把 `audit_2026/` 加入 `[tool.ruff] extend-exclude` 或由我清理脚本。
- 零 LLM 复现：`P21`。

---

## 6. "无法验证 / 无法溯源"声明清单（等级 E）

1. `tests.slim_environment=1863`（需精简依赖环境，未测）。
2. `coverage.line_total_pct=89` / `branch_total_pct=83` / 10 个核心模块行覆盖 / 3 个核心路由分支覆盖（需 `--cov` 全量跑批；仓库 `.coverage` 仅含 1 个被测文件，已退化）。
3. v1 修正口径 `35.86% (52/145)` / `48.11% (51/106)`（旧判分路径已被修复取代）。
4. 第四起伪影的零 LLM 证据 "9/9 双 rc=2"、"F2P 0/7→6/7"（`diagnostic_12task_prerepair.json` 无 rc 列，且无 9/7 任务工件）。
5. `spec_oracle_injected` 合成 2–3/87、QuixBugs 20/50（声明批次内该字段全为 None/False；命中只出现在 10-10 的另一族批次）。
6. S6 通道注入率 0/2→1/2、子句 3/5（无工件/日志）。
7. RT1 开关 `DETECTION_FIRST_SECTION_ENABLE` 的实际取值（不在该批 `env_snapshot`）。
8. D1 的 "427/621→555/621" 与 "空计划 34/87→22/87"（无缓存响应工件、无空计划字段）。
9. `patch_rollback_verdict` / `patch_rolled_back` / `regression_rate` / `red_regression_violation` / `deterministic_repair_status` 的**取值**（键存在或不存在，但全库 0 个非 None 值）。
10. 历史 CI 声明 `ci_gates_2026_10_09: full_suite 5107 passed`、`guards 10/10 exit 0`（无法回验历史提交时点；当前树门禁为红）。

---

## 7. 我实际执行的命令（可复算清单）

所有脚本位于 `audit_2026/`，只读解析 + 零 LLM。

| 简写 | 命令 | 用途 |
|---|---|---|
| P00 | `.venv/bin/python audit_2026/a01_main3seed.py` | 三批逐臂 detection/repair 计数 |
| P01 | `.venv/bin/python -m pytest tests/ -q --collect-only` | 收集数 = **5317** |
| P02 | `.venv/bin/python -m pytest tests/ -q --tb=line -p no:cacheprovider --basetemp=/tmp/aitester_audit_bt_20261011` | 全量 = **2 failed, 5311 passed, 3 skipped, 1 xfailed, 223.21s** |
| P03 | `.venv/bin/python -m pytest tests/ -q -n 4 -p no:cacheprovider --basetemp=/tmp/aitester_audit_bt_xdist` | xdist = **82.28s**，同为 2 failed |
| P04 | `.venv/bin/python -m mypy src/ config.py` | **123 source files, 0 errors** |
| P05 | `.venv/bin/ruff check . --extend-exclude audit_2026` / `ruff format --check . --extend-exclude audit_2026` | 全绿 / 591 files formatted |
| P06 | `audit_2026/a03_pooled261.py` | 261 行合并 detection + 配对 δ/χ² |
| P07 | `audit_2026/a05_cost.py` | 价目表 × token_metrics → $/task |
| P08 | `audit_2026/a04_specgate.py` | 全库 specificity_gate 分布 |
| P09 | `audit_2026/a07_quixbugs.py`、`a08_tokens.py`、`a09_e4denom.py` | E4 双臂/三种分母复算 |
| P10 | `audit_2026/a15_pairs.py`、`a26_e4deep.py` | E6/E4 全部 McNemar 复算（含 scipy 渐近 p） |
| P11 | `audit_2026/a23_replay_full.py`（200.4s） | **独立全量重放**：57/145、58/106、115/151/403 |
| P12 | `audit_2026/a12_dupruns.py` | 10-07 四批逐行同一性（伪重复证据） |
| P13 | `audit_2026/a28_zerotok.py` | `total_tokens==0` 行污染面（热/冷缓存对照） |
| P14 | `audit_2026/a17_precision.py`、`a18_consistency.py` | `correct=1 ∧ plausible=0` 129 行 |
| P15 | `audit_2026/a29_schema.py` | metrics_schema 逐键 present/non-None 计数 |
| P16 | `.venv/bin/python scripts/gates/check_env_snapshot_keys.py` | exit 1，缺 3 键 |
| P17 | `.venv/bin/python -m experiments.repair_replay experiments/results/main_batch/benchmark_synthetic_20261006_140906.json --arm aitester` | "带补丁行 87" 误导列 |
| P18 | `audit_2026/a19_stop.py` | stop_reason 分臂分布 |
| P19 | `.venv/bin/python -m pytest tests/test_process_utils.py -q --collect-only` 等 | 13 / 23 / 5 例 |
| P20 | `bash .git-hooks/check_secret_leak.sh; git check-ignore -v .env .env.local .private` | exit 1（误报）+ 忽略状态 |
| P21 | `.venv/bin/ruff check .` | 341 errors（全在 audit_2026/） |
| P22 | `audit_2026/a24_swe_census.py` | 365 行 SWE 普查（0 detection_rate、100% 无 instance_code） |
| P23 | `ps -o pid,ppid,pcpu,etime -p 36935,37116` | 孤儿进程 16.5h |
| P24 | `.venv/bin/python -m experiments.corrected_metrics experiments/results/main_batch --arm aitester` | 同源重生成修正报告（与库内 v2 对照，见 §8） |

---

## 8. 同源重生成对照（corrected_report_v2.md）—— **正文逐字节一致**

我重跑 `experiments.corrected_metrics experiments/results/main_batch --arm aitester`（零 LLM，全量 669 行重放），与库内 `experiments/results/main_batch/corrected_report_v2.md` 逐节比对：

- **正文（"- 目录：" 起至 "*报告生成：" 前）逐字节相同**：`body equal: True`（各 1659 字符）。差异仅在文件头：v2 多出一段 "ADR-0029 / R27 后重生成" 的前言块 + 标题后缀 `v2`。
- 关键数字（库内 = 我重跑）：
  - 行级裁决 `{'skipped_no_material': 8, 'no_patch': 395, 'wrong_patch': 151, 'correct': 115}` —— 一致；我另证 403 = 395（无 patch）+ 8（有 patch 无 gold 材料）。
  - 分代际 repair：E1/E2 `106/106/58 → 0.5472`、R-P0-2 `145/145/57 → 0.3931`、早期 `15/15/0 → 0.0000` —— 逐位一致。
  - §2 false_fix：passed 可测 **436**、false_fix **380** → **0.8716** —— 逐位一致（我另分解：332 行为 `no_patch`、48 行为 `wrong_patch`）。
  - §3：plausible **144**、IDR **0.3485**、CPR **0.8451（60/71）**、弃权拦截面 **0.7847**、passed 压制 **392/443**、弃权精确率 **0.8597** —— 全部由我独立重跑复现（同源脚本 + 同源工件）。
- 结论：`corrected_report_v2.md` 的数字链**完全可复现**，且其"不可重放行降级为 None、不臆造"的设计经我核验属实。**这是本项目数据纪律最好的一环。**

---

## 9. 明确标注为"项目自报、我未独立验证"的数字

以下为项目自评但本审计**未能独立验证**（除 §6 清单外，还包括）：

- 全部**外部文献引用**（CANDOR/TOSEM 2026、TestAgent/FSE 2026、ICST 2026 复现、IEEE 11655121、BOAD/ICLR 2026 等）的 DOI/数值——本次审计不涉及文献核查。
- 覆盖率 ratchet 水位（89.5 / 82.5）、门槛（85%/77%）、门禁脚本 10/10 绿。
- `mutation_score` 的**变异体生成正确性**（我复算了分数分布，未验证变异算子实现的正确性——属 code-auditor 范围）。
- `fl_at_k`、`llm_localization`、`localization_hit_function*` 的**语义正确性**（我核了非空率与取值，未核其与 gold 函数集合的比对实现）。
- `pre-commit`/CI 门禁矩阵在 3.12/3.13/3.14 的实际执行结果（本机仅 3.14）。
- E4 的 wallclock（21m07s / 8m15s / 37 分钟）——日志有时间戳但非结构化汇总，未精确复算。
- E6 matched 的 `bh_q`、`sign_test p`、聚类校正 χ²_adj（依赖模板簇结构，未复现）。
- `repair_ceiling_report.md` 的 bug_type 分层解混杂表（需 `fl_hit_value` 与 gold 变更函数集合，未复现）。
- 2026-10-01 `false_fix=89.8%` 历史值（该批 `detection_rate`/`repair_rate` 大量为 None，仅 49 行可判；未逐行复算 false_fix）。

---

## 10. 判定摘要（一句话版）

1. **核心实验数字可复现**：detection 38/240、117/261、4/261；repair 57/145、58/106；$/task 0.0259/0.0034/0.0045；E4 17/37、37/40、31/37；E6 8/87、30/87；A1/RT1/D1 过程指标——**我逐位复算一致，无编造痕迹**（A 级 43/90）。
2. **当前状态类声明失真**：`5262 passed / 0 failed`、`collect 5259`、`mypy 120 文件` 均与当前树不符（实测 5311+2F / 5317 / 123），且**项目自带守卫已红**（D-03）。
3. **伪重复**：E1/E2"四批次"实为 2 个独立单位 × 2 次缓存重跑，所有跨批合计（含 specificity_gate 与 repair 58/106）n 放大 2 倍（D-02）。
4. **SWE-bench 0/20 不是负结果**：0/365 行有 detection_rate，100% 实例无源码字段，Aug-18 批 repo=unknown 且日志有配额耗尽；README 两处自相矛盾（B-51/B-52）。
5. **记账缺陷影响对外数字的强度**：token 记账漏计缓存（D-04）、`patch_correct`/`patch_plausible` 双通道冲突 129 行使 92.5% 与 60% 相差 32.5pp（D-05）、若干声明指标从未落盘（D-06）、env 快照门禁第三次复发（D-07）。
6. **未见证据表明数据被伪造**；问题集中在**口径披露、伪重复、指标可得性与当前树状态刷新**。
