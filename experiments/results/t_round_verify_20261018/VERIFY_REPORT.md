# T 轮（2026-10-18）独立复核报告

> 复核角色：T 轮独立复核员（只读）
> 复核时刻：2026-10-18 10:09–10:14（Asia/Shanghai）
> 复核基线：`git HEAD = d95fca4`（T 轮代码 commit `962c77e` + 证据/文档 commit `d95fca4`）；工作树另有 3 个未提交修改（`CHANGELOG.md` / `CHANGELOG.en.md` / `experiments/analyze_t1_b2_main_batch.py`，后者属 B2 在途，按任务书不纳入）。
> 只读边界：未修改任何既有文件、未 git commit、未打印密钥；唯一写入为本报告（`experiments/results/t_round_verify_20261018/`）。
> 运行纪律：**未跑全量 `pytest`**（B2 真实 LLM 主批次在后台跑，避免 CPU 争用；仅 `--collect-only`、定向测试与轻量门禁）。
> B2 主批次（`t_round_b2_main_batch_20261018/`）按任务书**不纳入结果复核**；本报告仅核对其相关的"文档声明"是否与当前工件一致。

---

## 0. 结论摘要

| 项目 | 数量 |
|---|---|
| 复算数字/声明（一致项 62 行 + 不一致项 12 条复算值，均可按附录 A 复现） | **62+ 项** |
| **P0 不一致** | **1** |
| **P1 不一致** | **3** |
| **P2 不一致** | **8** |
| 无法核验项 | **10** |
| 一致项抽查行数 | **62** |

**总体判断**：T 轮**核心实验数字（B1 六格/McNemar、K3、SMT pre/post、A-19、回滚 schema、覆盖率/测试收集/门禁数字）与工件逐项一致**，工件存在性与 SHA 校验基本通过（7/8 目录通过）。主要问题集中在**文档先于工件**：B2 主批次仍在跑，但 README/登记册/BASELINE 注释已按"已完成"引用不存在的工件与 `b2_*` 键（P0）；"全量 0 failed"无日志工件且提交态下可复现确定性失败（P1）；"全部 T 证据目录 SHA verify 通过"对 B2/审计目录不成立（P1）；中文 CHANGELOG 的 B1 执行修订描述与工件相反（P1，英文版正确）。另有 8 处 P2 级数字/口径小错。

---

## 1. 不一致清单

> 分级沿用 T5a 审计报告定义：P0 = 结论性错报/核心技术事实被工件直接推翻；P1 = 状态/数字声明落后于或超出工件、需修正否则误导读者；P2 = 措辞/统计口径/自洽性小错。
> 每条给出「文档值 / 工件复算值 / 证据命令 / 建议修正」。

### 1.1 P0（1 条）

#### P0-01　B2 主批次被文档宣称为"已执行"并引用不存在的工件与 BASELINE 键

| 项 | 内容 |
|---|---|
| 文档位置 | `README.md:64`；`README.en.md:82`；`docs/PROJECT_STATUS_REGISTER.md:3`（抬头）、`:69`（§2 B2 行）、`:180`（§3.2 T-1 行）、`:260`（§4 T 轮收口行）；`BASELINE.yaml:308`（注释"见 b2_*/b1_* 键"）；`docs/VALIDITY.md:72` / `VALIDITY.en.md:83`（残余②称 harness 漂移"已在 T 轮 B2/B1 分析中逐项披露"） |
| 文档值 | README："B2 主批次锁指纹复现（3 seed×3 臂×87 任务…）；**判定与数字见 BASELINE.yaml `target_quality.b2_main_batch_t_round`**，工件 `t_round_b2_main_batch_20261018/`"；登记册 §2 B2："**✅ 已执行（T 轮 T-1）**"；§3.2 T-1："逐 seed `GATES.json`…与三 seed 合并判定 `ANALYSIS_REPORT.json`"、"工件 …（SHA256SUMS + README）"；`BASELINE:308` 称存在 `b2_*` 键 |
| 工件值 | ① `t_round_b2_main_batch_20261018/` 仅含 `PREREG.md`/`PREREG_AMENDMENT_cost_estimate.md`/`PREFLIGHT*.json`/`RUN_SUMMARY.log`（单行，seed42 结尾 `2026-10-18T02:05:53Z`）/`seed42_GATE.json`/`_helpers`/`_preflight`/`seed42`/`_staging_seed42`/`_staging_seed43`/`traces_seed42`/`traces_seed43`；**无 README、无 SHA256SUMS、无 GATES.json、无 ANALYSIS_REPORT.json**；`git ls-files experiments/results/t_round_b2_main_batch_20261018 \| wc -l` = **0**；② `BASELINE.yaml` 中 **不存在** `b2_main_batch_t_round` 或任何 `target_quality.b2_*` 键（`grep -n 'b2_' BASELINE.yaml` 仅命中第 308 行注释）；③ `traces_seed43` 在 10:09 仍在增长（seed43 在跑）；④ d95fca4 commit message 自述"B2 …仍在跑…**不在本提交内声称完成**" |
| 证据命令 | `ls experiments/results/t_round_b2_main_batch_20261018`；`git ls-files experiments/results/t_round_b2_main_batch_20261018 \| wc -l`；`grep -n 'b2_' BASELINE.yaml`；`grep -n 'B2.*已执行' docs/PROJECT_STATUS_REGISTER.md`；`git show --stat d95fca4 \| head -3` |
| 建议修正 | 在 B2 完成并入库前，三处统一改为"**B2 主批次进行中**（seed42 已过 gate，seed43/44 在跑；预注册已冻结、成本估算修订已披露）"，删除 `target_quality.b2_main_batch_t_round`/`b2_*` 引用，登记册 §2 B2 类型改回"进行中"；B2 完成后的后续 commit 再回填工件 SHA256SUMS/README/GATES/ANALYSIS 与 BASELINE `b2_main_batch_t_round`。**该问题在 B2 结果落地后自动消解，但作为当前提交态的文档事实不成立。** |

### 1.2 P1（3 条）

#### P1-01　"全量 8929 passed / 5 skipped / 0 failed"无运行日志工件，且提交态下存在可复现的确定性失败

| 项 | 内容 |
|---|---|
| 文档位置 | `BASELINE.yaml:17-20`（`tests.total_passed: 8929` / `total_failed: 0`）；`docs/PROJECT_STATUS_REGISTER.md:39`（§1"全量测试 **8929 passed / 5 skipped / 0 failed**（…T 轮本机实测…）"） |
| 文档值 | 全量套件 T 轮本机实测 8929 passed / 5 skipped / 0 failed；CHANGELOG 提交版仍保留 `<!-- T-TESTS-PENDING -->` |
| 工件值 | ① `--collect-only` 实测 **8934 collected**（与文档一致）、skipped 5（算术一致）→ 但 **passed=8929 无任何运行日志/工件可对**（coverage.xml 只有行/分支分母与时间戳，不含 pass/fail）；② 在 HEAD=d95fca4 的提交态下（B2 已存在但未入库），`tests/test_artifacts_tracked_gate.py::TestGateEndToEnd::test_gate_exit_zero_on_current_repo` 与 `::TestEmseDirScan::test_scan_passes_on_current_repo` **确定性 FAILED**（本复核实跑：`1 failed`，原因=门禁报 `t_round_b2_main_batch_20261018: 整个目录 0 git 跟踪`；AITester 的 `_scan_evidence_dirs` 依赖 `git ls-files`）；③ `.pytest_cache/v/cache/lastfailed`（**mtime 10:08:23，早于 d95fca4 提交 10:08:33 约 10s**）记录 **49 条 failed node ID**，含上述 2 条、`test_t_round_semantic_fixes.py::…` 旧名用例等；④ CHANGELOG 提交版明确留 `T-TESTS-PENDING` |
| 证据命令 | `.venv/bin/python -m pytest --collect-only -q \| tail -2`（8934 collected）；`.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_artifacts_tracked_gate.py::TestGateEndToEnd::test_gate_exit_zero_on_current_repo tests/test_artifacts_tracked_gate.py::TestEmseDirScan::test_scan_passes_on_current_repo`（1 failed）；`.venv/bin/python scripts/gates/check_artifacts_tracked.py`（exit=1，2 offenders）；`cat .pytest_cache/v/cache/lastfailed \| head`；`stat -f '%Sm' .pytest_cache/v/cache/lastfailed` |
| 建议修正 | 在 B2 入库后跑一次全量（`-p no:cacheprovider`，`COVERAGE_FILE` 隔离）并把**命令/耗时/pass-fail 摘要**落为工件或写入 CHANGELOG；在此之前 BASELINE `tests.total_passed/total_failed` 与登记册 §1 应标"pending/B2 后刷新"，不得写"0 failed（本机实测）"。注意：上述 2 例在 B2 工件入库后可通过，因此本条不升级为 P0；但"0 failed"当前**无法被任何工件证实，且提交态有反例**。 |

#### P1-02　"T 轮证据目录全部 SHA256SUMS --verify 通过（T1/T2/T3/T3b/T3c/T4/T5a）"对 T1/T5a 不成立

| 项 | 内容 |
|---|---|
| 文档位置 | `CHANGELOG.md:129`（英文版对应句同）；commit message d95fca4 亦称"全部 SHA256SUMS verify 通过" |
| 文档值 | "工件：T 轮证据目录**全部** `SHA256SUMS --write/--verify` 通过（T1/T2/T3/T3b/T3c/T4/T5a）" |
| 工件值 | 实际逐一 verify：`t_round_a19_default_gate_20261018` **34 项通过**；`t_round_b1_protocol_text_20261018` **557 项通过**；`t_round_oracle_k3_20261018` **22 项通过**；`t_round_semantic_fixes_20261018` **11 项通过**；`t_round_smt_witness_20261018` **7 项通过**；`t_round_smt_witness_aliasfix_20261018` **9 项通过**；`e2e_probe_t_round_20261018` **5 项通过**；**`t_round_artifact_audit_20261018` 无 SHA256SUMS → `--verify` exit=1 "[FAIL] 清单不存在"**；**T1/B2 目录无 SHA256SUMS**（在跑，见 P0-01） |
| 证据命令 | `for d in experiments/results/t_round_*_20261018 experiments/results/e2e_probe_t_round_20261018; do .venv/bin/python scripts/gates/checksum_results.py --verify --results-dir "$d"; echo exit=$?; done` |
| 建议修正 | 改为可核对清单："T 轮 6 个结果目录 + e2e 目录 verify 通过（34/557/22/11/7/9/5 项）；B2 待其完成；审计目录为单文件只读报告，未生成清单/不适用"；或为审计目录补 `SHA256SUMS`。 |

#### P1-03　中文 CHANGELOG 的 B1 执行修订描述与工件/英文版相反（"C1_seed42 保留 mutation 口径"）

| 项 | 内容 |
|---|---|
| 文档位置 | `CHANGELOG.md:32-33`（T2/B1 条目） |
| 文档值 | "…显式关闭该批后辅助测量并**从 C1_seed44 起生效（C1_seed42 保留 mutation 口径并披露差异）**" |
| 工件值 | **六格全部以 `ENABLE_MUTATION_SCORING=false` 重跑**：`GATES.json` 硬检查 `mutation_scoring_disabled_all_runs` 六格均为 `"false"`（禁用）；六格 batch `provenance.env_snapshot.ENABLE_MUTATION_SCORING="false"`；b1 `README.md:115`"六格最终统一以 `ENABLE_MUTATION_SCORING=false` 重跑"；`PREREG_CONTINUATION.md` §2.1/§2.2"六格全部按修订后统一 env 重跑（不再保留 C1_seed42）"；`VALIDITY.md:72`/`VALIDITY.en.md:83`"六格（首跑中止后统一重跑）均关闭了批后 `ENABLE_MUTATION_SCORING`"；`CHANGELOG.en.md:23`"reran all six cells uniformly"；`STATUS:181` 措辞亦正确（"六格改统一…重跑"）。**无任何一格保留 mutation 口径。** |
| 证据命令 | `.venv/bin/python -c "import json;g=json.load(open('experiments/results/t_round_b1_protocol_text_20261018/GATES.json'));print([c['detail'] for c in g['checks'] if c['id']=='mutation_scoring_disabled_all_runs'])"`；`grep -n '统一' experiments/results/t_round_b1_protocol_text_20261018/README.md`；`git show d95fca4:CHANGELOG.en.md \| sed -n '23p'`；`grep -n '六格' docs/VALIDITY.md` |
| 建议修正 | 中文句改为："首跑因批后 mutation/MDO 辅助测量墙钟超预期被中止（无主终点数据），**六格统一以 `ENABLE_MUTATION_SCORING=false` 重跑**（该开关只关批后辅助测量；本批不引用任何 mutation/MDO 数值）"。附注：`PREREG_CONTINUATION.md` §4"披露义务"仍保留旧表述"`C1_seed42` 为 true、其余 false"，与其 §2.1/§2.2 自相矛盾（该工件已冻结，建议在 b1 `README.md` 加一行勘误说明"§4 为 09:21 前旧计划，实际按 §2.2 六格统一重跑"）。 |

### 1.3 P2（8 条）

| 编号 | 文档位置 | 文档值 | 工件/复算值 | 证据命令 | 建议修正 |
|---|---|---|---|---|---|
| **P2-01** | `CHANGELOG.md:34` | "六格全过 **GATES 16 checks**" | **17 checks** 全过（`GATES.json` `len(checks)=17`，status=pass、blocking=[]、warnings=[]；`BASELINE.yaml:385`"17 checks"；`CHANGELOG.en.md:23`"GATES 17/17 checks pass"） | `.venv/bin/python -c "import json;g=json.load(open('experiments/results/t_round_b1_protocol_text_20261018/GATES.json'));print(len(g['checks']),g['status'],g['blocking'],g['warnings'])"` | 改为 **17 checks**（与英文/BASELINE 对齐） |
| **P2-02** | `CHANGELOG.md:33`；`docs/PROJECT_STATUS_REGISTER.md:181` | "`DOC_RECONCILIATION.md` 列出 **4 处**「未执行」陈旧声明" / "给出 VALIDITY/EMSE/EVAL_SCOPE **四处**…" | 工件 `DOC_RECONCILIATION.md:129`："**必改陈旧声明共 9 处（5 文件）**"（VALIDITY.md:72/106/107；VALIDITY.en.md:83/117-118；EMSE:111；STATUS:68；EVAL_SCOPE:25/60）；`CHANGELOG.en.md:23` 正确写"**nine** stale … across **five** files" | `grep -n '9 处\|必改陈旧' experiments/results/t_round_b1_protocol_text_20261018/DOC_RECONCILIATION.md`；`git show d95fca4:CHANGELOG.en.md \| sed -n '23p'` | 中文两处统一为"**9 处（5 文件）**" |
| **P2-03** | `README.md:64`；`README.en.md:82` | "跨采样保留率 **24%→96.5%**" | S-3（K=2）保留率 = **43/67 = 64.2%**；**24 是"丢弃 24 条"的条数**，不是比率。T-3 = 55/57 = 96.49%✓；`CHANGELOG.md:35`/`CHANGELOG.en`/`MEASUREMENT_INTEGRITY §7`/`oracle_quality_metric §16.2` 均正确写"对比 S-3 的 **64%**" | `.venv/bin/python -c "print(43/67, 55/57)"`；`grep -n 'union 67\|丢弃 24\|64%' experiments/results/s_round_examples_multisample_20261018/README.md` | 改为"跨采样保留率 **64%→96.5%**"（或写"丢弃 24 条（保留 64%）→保留率 96.5%"） |
| **P2-04** | `CHANGELOG.md:19` | "A-19 复验 **≈$0.08**" | 实际 **$0.098**（两臂标准价上界：on 0.049308 + off 0.048692 = 0.098；`t_round_a19_default_gate_20261018/README.md:8`"真实 LLM 花费 **$0.098**"；`REPORT.json.verdict.cost_total_usd=0.098`） | `.venv/bin/python -c "import json;r=json.load(open('experiments/results/t_round_a19_default_gate_20261018/REPORT.json'));print(r['verdict']['cost_total_usd'],r['arms']['on']['cost_usd_standard_price'],r['arms']['off']['cost_usd_standard_price'])"` | 改为 **≈$0.098** |
| **P2-05** | `CHANGELOG.md:19`；`CHANGELOG.en.md:18`；`README.md:64`（"真实 LLM 花费见 CHANGELOG T 轮"） | 花费行仍为 `<!-- T-COST-PENDING -->`（"B2 ≈$…；B1 ≈$…；A-19 复验 ≈$0.08；…e2e LLM 探针 ≈$…"）；提交版 CHANGELOG 同时保留 `T-TESTS-PENDING`/`T-GATES-PENDING` | B1 花费已实测 **$0.876339**（b1 条目自身已写）；K=3 $0.020577✓；A-19 $0.098✓；B2/e2e LLM 未结算 → 总额确实无法给全。工作树已补门禁数字（T-GATES-PENDING 已填），但 `T-TESTS-PENDING`/`T-COST-PENDING` 仍未填 | `grep -n 'PENDING' CHANGELOG.md CHANGELOG.en.md`；`git show d95fca4:CHANGELOG.md \| sed -n '/### Verification/,+8p'` | 至少填入已实测项（B1 $0.876339、A-19 $0.098、K=3 $0.020577），B2/e2e 标"待 B2 结算"；README 指针在花费行未完成前应注明"部分待结算" |
| **P2-06** | `BASELINE.yaml:14` | `last_verified: "2026-10-17"`（注释仍写 N 轮 8320/8315） | 同文件已按 **2026-10-18 T 轮**刷新 `tests/coverage/static_checks/feature_matrix`（`:17`、`:33`、`:51`、`:481` 等）；违反该文件 `:9` 自身约定"任何功能批次落地后，必须同步更新 last_verified"；审计 P1-02 未在 T 轮收口 | `grep -n 'last_verified' BASELINE.yaml`；`.venv/bin/python -c "import yaml;d=yaml.safe_load(open('BASELINE.yaml'));print(d['last_verified'])"` | 改为 `"2026-10-18"` 并更新注释（或在 B2 终稿 commit 时统一刷新） |
| **P2-07** | `docs/VALIDITY.md:72`；`docs/VALIDITY.en.md:83`（§4 表格残余②/④） | "harness 漂移（logic 档自 R-P0-2 起新增 5 个开关）**已在 T 轮 B2/B1 分析中逐项披露**" | B2 分析工件**不存在**（见 P0-01）；B1 侧 `ANALYSIS_REPORT.json`/`README.md`/`PREFLIGHT` 中**没有**"5 个开关逐项披露"小节（B1 仅披露旧批 token 份额差异 `output_share_pct` 与旧批 dirty/无指纹）；`STATUS:180` 同样声称"harness 漂移按 provenance/profile-preset diff 逐项披露"（B2 部分） | `.venv/bin/python -c "import json;d=json.load(open('experiments/results/t_round_b1_protocol_text_20261018/ANALYSIS_REPORT.json'));print([k for k in d])"`；`grep -n '开关\|profile-preset' experiments/results/t_round_b1_protocol_text_20261018/README.md` | B1 侧在 README 增"harness/协议漂移"小节（logic 档 5 开关清单、与 R-P0-2 的输出 token 份额差异）；B2 侧待其分析工件落地后再引用，或把该句改为"B2 分析落地后披露" |
| **P2-08** | `BASELINE.yaml:17`（tests 注释） | "…+ 2 例既有用例按行为变更更新（探针清单并集/ **MANIFEST 长度锁**）" | 测试中**不存在** MANIFEST 长度锁：`tests/test_artifacts_tracked_gate.py:39` 只断言"无重复条目"，`:43-44` 断言条目存在，T 轮新增的是目录扫描面/glob 断言（`len(MANIFEST)` 可自由增长，现为 163 无硬编码）；既有用例更新实际为"探针清单并集（test_e2e_probes_logic）"+"扫描/清单子串（test_artifacts_tracked_gate）" | `grep -n 'len(gate.MANIFEST)' tests/test_artifacts_tracked_gate.py`；`grep -rn '== 163\|MANIFEST.*长度' tests/` | 改为"探针清单并集/工件目录扫描面与 MANIFEST 子串锁"（或补一条 `len(MANIFEST)==163` 硬锁再保留该表述） |

---

## 2. 一致项抽查表（62 行）

> 说明：文档值取自 commit `d95fca4` + 工作树（CHANGELOG 门禁行为工作树，已注明）；工件值均为本次**打开原始 JSON/XML 复算**所得（不信任 ANALYSIS 摘要）。`✓` = 一致（含正常舍入）。

| # | 文档位置 | 文档声明（值） | 工件/复算值 | 证据（命令/文件） | 判定 |
|---|---|---|---|---|---|
| 1 | CHANGELOG:35；BASELINE:378；VALIDITY:107 | B1 C1_seed42 **9/87**（10.3%） | 9/87 = **10.3448%** | 由 `staging/C1_seed42/benchmark_*.json` 行 `detection_rate>=1.0` 复算 | ✓ |
| 2 | 同上 | C1_seed44 **12/87**（13.8%） | 12/87 = **13.7931%** | 同上（seed44 批次） | ✓ |
| 3 | 同上 | C2_seed42 **10/87**（11.5%） | 10/87 = **11.4943%** | 同上 | ✓ |
| 4 | 同上 | C2_seed44 **10/87** | 10/87 = 11.4943% | 同上 | ✓ |
| 5 | 同上 | C3_seed42 **24/87**（27.6%） | 24/87 = **27.5862%** | 同上 | ✓ |
| 6 | 同上 | C3_seed44 **27/87**（31.0%） | 27/87 = **31.0345%** | 同上 | ✓ |
| 7 | CHANGELOG:36；BASELINE:378；VALIDITY:107 | 文本效应 seed42 **+16.1pp**，McNemar **b/c=15/1，p=0.000519** | Δ=**+16.0920pp**；b=15、c=1、n=87；精确二项双侧 **p=0.000518799** | 配对复算：`math.comb` 精确二项（脚本见附录 A） | ✓ |
| 8 | 同上 | 文本效应 seed44 **+19.5pp**，**b/c=17/0，p=1.5e-05** | Δ=**+19.5402pp**；b=17、c=0；p=**1.52588e-05**（工作树 README 写 1.53e-05，同为舍入） | 同上 | ✓ |
| 9 | CHANGELOG:36-37；BASELINE:378 | 采样效应 seed42 **+1.1pp，p=1.0** | Δ=**+1.1494pp**；b=1、c=0；p=**1.0** | 同上 | ✓ |
| 10 | 同上 | 采样效应 seed44 **−2.3pp，p=0.5** | Δ=**−2.2989pp**；b=0、c=2；p=**0.5** | 同上 | ✓ |
| 11 | CHANGELOG:37；BASELINE:382 | B1 六格合计 **$0.876339** | 六格 `cost_usd_standard_price` 之和 = **0.876339** | 读 6 个 `seed*/meta_C*.json` 复算 | ✓ |
| 12 | CHANGELOG:37；BASELINE:382 | 批次墙钟 **1299s**；六跑之和 **1281s** | RUN_SUMMARY：`BATCH_WALL_SECONDS=1299`、`RUNS_WALL_SUM_SECONDS=1281`；meta run_log 差值之和 1281 | `grep 'WALL' RUN_SUMMARY.log`；脚本复算 | ✓ |
| 13 | BASELINE:381；CHANGELOG.en:23 | **GATES 17 checks** 全过，0 blocking / 0 warnings | `status=pass`，`len(checks)=17`，`blocking=[]`，`warnings=[]` | `GATES.json` 解析 | ✓（中文 CHANGELOG 的"16"见 P2-01） |
| 14 | CHANGELOG:37；BASELINE:377-381 | 六格均 `git_dirty=false`、`git_sha=a93c1f6…`、`model_fingerprint.pinned=true` | 6/6 meta provenance 均为 a93c1f60… / dirty=false / pinned=true / returned=deepseek-flash / probe_sha 唯一 | 逐 meta JSON 复算 | ✓ |
| 15 | BASELINE:383；VALIDITY:106 | 旧批（2026-10-09）C1 9/87、C2(RT1) 10/87、C3(df) 27/87，df−RT1=**+19.5pp** | 旧批 JSON 复算：plain_llm 9/87、plain_llm_df(rt1 批) 10/87、df 27/87；17/87=**19.54pp**；旧批 git_dirty=true、无 model_fingerprint | 读 `e6_a1_batches/e6_phase1_standard_coldcache/…json` 与 `rt1_no_reinforcement_seed42/…json` | ✓ |
| 16 | BASELINE:384；CHANGELOG:129 | B1 SHA256SUMS verify | **557 项全部一致**（exit=0） | `checksum_results.py --verify --results-dir …b1…` | ✓ |
| 17 | CHANGELOG:38；BASELINE:315；MEAS_INTEGRITY §7 | K3 **60 次调用、$0.020577、45.3s、回退 0** | SAMPLING_REPORT：llm_calls=60、cost=0.020577、wall_s=45.301、fallback n_tasks=0 | 读 `SAMPLING_REPORT.json`/`RUN_SUMMARY.log` | ✓ |
| 18 | CHANGELOG:39；BASELINE:315 | union **57** / 交集 **55** / 保留率 **96.5%** | 57 / 55；55/57 = **96.4912%**；dropped=2 | `SAMPLING_REPORT.json` 复算 | ✓ |
| 19 | CHANGELOG:39；MEAS_INTEGRITY §7 | 对比 S-3 保留率 **64%** | S-3：union 67 → 交集 43，丢弃 24；43/67 = **64.18%** | `s_round_examples_multisample_20261018/README.md:28` + 复算 | ✓（README"24%"见 P2-03） |
| 20 | CHANGELOG:38-39；BASELINE:316；design §16.2 | K3 基线 correct **8**/fp 0/silent 3/misguided 2/unavailable 7 | 重放报告 B 臂 counts：**8/0/3/2/7**，可分类 13 | 读 `p_round…/ORACLE_EXAMPLES_REPORT_norm.json` arms→aggregate | ✓ |
| 21 | CHANGELOG:39；BASELINE:317-318；design §16.2 | K3 重放 correct **5**/fp 0/silent 6/misguided 1/unavailable 8 | 两臂（R-2 开/关）均 **5/0/6/1/8**，可分类 12 | 读两份 `ORACLE_EXAMPLES_REPORT_k3_*.json` | ✓ |
| 22 | CHANGELOG:39；BASELINE:319 | 判定 `high_risk_default_off`；correct **8→5（损失 3）**、misguided **2→1** | judgment：correct_before 8/after 5/loss 3；misguided 2→1；verdict 命中"correct 损失≥2"规则 | `ANALYSIS_REPORT.json.judgment` | ✓ |
| 23 | CHANGELOG:39；BASELINE:320；MEAS_INTEGRITY §7 | `knapsack` **3/3 一致的新幻觉** `(1,[[1,1]])→0` | K3_STATS 3 个 sample 的 examples 完全相同且均含 `[1,[[1,1]]]→0`；重放 `misguided`；归因说明 buggy 因 `weight<j` 返回 0、fixed 返回 1 | `K3_STATS.json` per_task[knapsack] 三样本逐条比对；`ANALYSIS_REPORT.attribution_notes` | ✓ |
| 24 | BASELINE:322；CHANGELOG:40 | K3 工件 **22 项** SHA verify | **22 项全部一致**（exit=0） | `checksum_results.py --verify` | ✓ |
| 25 | CHANGELOG:41-42；BASELINE:330-332；design §6.1 | SMT pre-fix **D1=184**；sat 19 / unsat 0 / unknown 0 / timeout 0 / error 165 | 由 TASK_LEVEL（41 primary 任务）重聚合：非空子句 **184**、sat **19**、error **165**，其余 0；PER_CLAUSE 复算一致 | 读 `TASK_LEVEL.json` + `PER_CLAUSE.jsonl` 独立重聚合 | ✓ |
| 26 | 同上 | pre-fix **witness_rate 0.088531、reach_rate 0.103261、timeout 0.0** | 41 任务 witness_rate 均值=**0.088531**；reached/nonempty=19/184=**0.103261**；timeout/reached=**0.0** | 同上 | ✓ |
| 27 | CHANGELOG:43；BASELINE:334；MEAS_INTEGRITY §7 | 错误归因最大项 `result_alias_not_reached`=**110（66%）** | expr 通道 error=166（全 50 任务）；110/166=**66.3%**；同表 110/51/5 合计 166 | `ANALYSIS_REPORT.error_attribution.by_channel` | ✓ |
| 28 | CHANGELOG:44-45；BASELINE:332；design §6.2 | T3c post-fix **reached 19→27、sat 19→27、error 165→157**；witness **0.125116**、reach **0.146739** | aliasfix TASK_LEVEL：reached **27**、sat **27**、error **157**；witness 均值 **0.125116**；reached/nonempty=27/184=**0.146739**；16/41 任务有 sat | 读 aliasfix `TASK_LEVEL.json` 独立重聚合 | ✓ |
| 29 | CHANGELOG:45；BASELINE:331-335；design §6.2 | 语义安全：solver_exception=**0**、新增 unsat 任务 **0**、NL 通道 **41/41 不变** | COMPARISON risk_guards：solver_exception_zero=0（pass）、new_unsat=0/0/0（pass）、full_post_group_no_unsat_surge pass；NL old skipped 41 / new skipped 41；expr skipped 39→sat 2/skipped 37 | 读 aliasfix `COMPARISON.json` 与 ANALYSIS `full_post_group_semantics` | ✓ |
| 30 | CHANGELOG:41；BASELINE:329；design §6.1 | SMT 材料：QuixBugs 41 缺陷程序、锚表 **50/50** 命中、anchor sha **3e90b2ad…** | ANALYSIS material_layer：tasks_total 50 / tasks_with_material 50 / gap []；anchor sha256=3e90b2ad5ed3…；41 primary 全有材料 | `ANALYSIS_REPORT.json` + `PREFLIGHT.json` | ✓ |
| 31 | BASELINE:336 | SMT 两批 SHA：pre **7 项**、post **9 项** verify | **7/7**、**9/9** 全通过（exit=0） | `checksum_results.py --verify` ×2 | ✓ |
| 32 | CHANGELOG:46-48；BASELINE:344-356；STATUS:184 | A-19 ON：**10/10** coverage_stall、iterations_mean **1.9**、preempt 日志 **8**、stall **10**、repair-invalid **0**、cost **0.049308**、tokens **87835** | ANALYSIS/REPORT：on stop_reason coverage_stall=10/10、iters 均值 1.9、logs preempt=8/stall=10/repair_invalid=0、cost 0.049308、token 87835、crash 0 | 读 `ANALYSIS.json` + `REPORT.json.arms` | ✓ |
| 33 | 同上 | A-19 OFF：**9/10** skip_debugger_repair_invalid + 1/10 max_iterations、iters **2.1**、repair-invalid 日志 **9**、stall 0、cost **0.048692**、tokens **87216** | 同上：off 9+1、iters 均值 2.1、repair_invalid=9、stall=0、cost 0.048692、token 87216、crash 0 | 同上 | ✓ |
| 34 | CHANGELOG:47-48；BASELINE:348-355；README:64 | A-19 合计 **$0.098**、两臂 **0 crash**、classification **`unexpected_delta`**、Δiterations **0.2**、ON 10/10 停滞终止 / repair-invalid 0 | REPORT verdict：cost_total_usd=0.098、crash 0/0；REPORT/ANALYSIS classification=unexpected_delta；P3 Δ=2.1−1.9=0.2、met=false；P1 met=false（preempt 8≠10） | 读 `REPORT.json.verdict` + `ANALYSIS.json.criteria` | ✓ |
| 35 | BASELINE:338-356；CHANGELOG:46 | A-19 预注册 sha **83a8a645…**、黄金表 **18 行** sha **591c93d8…**、ISOLATION 全绿 | 文件实测 sha256=83a8a645…；`off_golden_table_before.json` rows=**18**、sha256=591c93d8f8fa…；ISOLATION `all_checks_pass=true`（含两臂跑前跑后 clean、diff 空） | 脚本 sha256 复算 + JSON 解析 | ✓ |
| 36 | CHANGELOG:49；BASELINE:358-364；STATUS:184 | 回滚 schema：两键、成功分支投影、失败分支 `(None, False)`、键集合同构 **93=93** | 代码 `experiments/run_benchmark.py:1874-1875`（成功分支两键投影）与 `:2118-2119`（失败分支 `None/False`）；`tests/test_t_round_semantic_fixes.py` 34 例实跑全过（含 93=93 断言） | `grep -n 'patch_rollback_verdict' experiments/run_benchmark.py`；`pytest tests/test_t_round_semantic_fixes.py -q`（34 passed） | ✓ |
| 37 | CHANGELOG:50-52；BASELINE:365-371；MEAS_INTEGRITY §7 | preflight 旧实现 ImportError → 修复后真实探测 **ok=True**，7 例 monkeypatch + AST 回归锁 | `_evidence/preflight_before_fix_check_quota.log`：`{'ok': False, 'skipped': True, 'reason': '导入 LLMClient 失败：ImportError'}`；after：`{'ok': True, 'skipped': False, 'response_prefix': 'OK', 'model': 'deepseek-flash'}`；`TestQuotaProbe` collect=**7** | 读两份日志；`pytest --collect-only tests/test_batch_quota_preflight.py::TestQuotaProbe` | ✓ |
| 38 | CHANGELOG:53；BASELINE:365-371 | D3b 下游消费者 `debugger._resolve_target_module` 读取 `cross_file_plan`；`build_cross_file_repair_plan` 图内零调用 | `src/graph/debugger.py:105 def _resolve_target_module`，`:131-132` 读 `state.get("cross_file_plan")`→`target_modules`；`src/graph/` 内 `build_cross_file_repair_plan` 仅 `nodes.py:1954` 一条"尚未接入图"注释 | `grep -n 'def _resolve_target_module' -A40 src/graph/debugger.py`；`grep -rn 'build_cross_file_repair_plan' src/graph/` | ✓ |
| 39 | CHANGELOG:54-55；BASELINE:455-458 | e2e 探针矩阵 **68**（零 LLM 56 + LLM 12）；新增 2/去重 2；注册数=可执行数 | `report.json` probes=**68**、summary pass=56 skip=12；`report_llm.json` pass=**68**；group 计数合计 68（cli6/workflow3/agents3/repair2/safety5/localization3/observability4/budget4/cache3/rag2/security4/executor5/dataset4/logic20）；load_errors=[] | 读 `e2e_probe_t_round_20261018/report*.json` | ✓ |
| 40 | CHANGELOG:127（工作树）；STATUS:44 | e2e 含 LLM 全量 **68/68 pass**，耗时合计 **97.5s** | report_llm probes 全 pass=68；`sum(duration_s)=97.46s`（≈97.5） | 读 report_llm.json 复算 duration 之和 | ✓ |
| 41 | CHANGELOG:128（工作树）；BASELINE:459-461 | 零 LLM 子集 **56 pass / 12 skip（共 68）** | report.json summary：pass=56、skip=12；总 probes 68 | 同上 | ✓ |
| 42 | CHANGELOG:56-58；MEAS_INTEGRITY §7；BASELINE:365-371 | 旧矩阵"**66/66 pass**"但 2 个 observability 探针重复注册被静默丢弃于 `load_errors`；去重后 66→**68** | 旧报告 `e2e_probe_20261017/report.json`：probes=66、summary={pass:66}、load_errors 恰为 `observability-trace-redaction`、`observability-event-bus` 两条重名 | 读旧 report.json | ✓ |
| 43 | CHANGELOG:59-61；MEAS_INTEGRITY §7；STATUS:185 | `checksum_results --verify` 路径归一；`emse_docstring_anchor_20261017` 清单 **165 条**由误判缺失→全通过；4 例回归含"真缺失仍报错"负控 | 该目录 SHA256SUMS 行数=**165**，`--verify` **165 项全部一致**（exit=0）；`TestManifestPathNormalization` collect=**4**（含 `test_still_detects_missing_after_normalization` 负控） | `wc -l …/SHA256SUMS`；`checksum_results.py --verify`；`pytest --collect-only tests/test_checksum_results_gate.py::TestManifestPathNormalization` | ✓ |
| 44 | CHANGELOG:62-63；BASELINE:365-371 | `check_artifacts_tracked` 扫描面 `emse_*` → `emse_* + *_round_*`；MANIFEST **+31（133→163）** | 代码 `EVIDENCE_DIR_GLOBS` 同时含两种前缀（测试 `test_evidence_globs_cover_emse_and_round_prefixes` 过）；`len(MANIFEST)=163`；相对 a93c1f6 diff 新增 33 条 experiments 路径、删除 2 条 → **净 +31**；T 轮 MANIFEST 条目 30 条全部 git-tracked 且磁盘存在；T 轮清单锁测试 14 passed | `python -c "import scripts.gates.check_artifacts_tracked as g;print(len(g.MANIFEST), g.EVIDENCE_DIR_GLOBS)"`；`git diff a93c1f6 d95fca4 -- scripts/gates/check_artifacts_tracked.py \| grep -c '^+.*experiments/results'`；`pytest tests/test_artifacts_tracked_gate.py -k "t_round or manifest or globs"` | ✓ |
| 45 | CHANGELOG:64-67；BASELINE:386-395 | 文档↔工件审计 **P0=4 / P1=17 / P2=14**；BASELINE **20 项**逐项核对；**10 项**无法核验 | AUDIT_REPORT 头部表 P0=4/P1=17/P2=14；§2 行数=20；§8 抽样一致行数=20；§9 无法核验编号 1–10=10 | 解析 `AUDIT_REPORT.md` 分节计数 | ✓ |
| 46 | BASELINE:33,51；STATUS:40-41；CHANGELOG「BASELINE 覆盖率刷新」条 | 覆盖率：行 **96.55%（17481/18106）**、分支 **92.78%（6274/6762）**；ratchet 水位 96.4/92.5 | `coverage.xml` 根属性：lines-valid **18106**、lines-covered **17481**（96.5481%）、branches-valid **6762**、branches-covered **6274**（92.7832%）；`coverage_ratchet --check` 通过（余量 +0.15/+0.28pp）；`docs/coverage_ratchet.yaml` line_total 96.40/branch_total 92.50 | 解析 coverage.xml；`coverage_ratchet.py --check` | ✓ |
| 47 | BASELINE:34-50；STATUS:40-41 | 逐模块行覆盖 10 项：base_agent 98.80、api_manager 100.00、dataset_loader 93.85、graph_nodes 99.87、code_analyzer 99.38、planner 99.09、dependency 96.26、multi_candidate 98.67、cross_file 92.83、rag_retriever 98.10 | coverage.xml 逐文件复算与文档**逐项相同**（含分母 329/333、459/459、290/309、746/747、160/161、109/110、309/321、296/300、272/293、207/211） | 解析 coverage.xml per-class line 统计 | ✓ |
| 48 | BASELINE:52-55；STATUS:41 | 核心路由 3 项：graph_workflow 分支 **99.17**、error_classifier **96.49**、graph_state **100.00** | 复算：graph/workflow.py **119/120=99.17%**（line 361/362=99.72%）、agents/error_classifier.py **110/114=96.49%**（line 311/311=100%）、graph/state.py **2/2=100%** | 同上（按 `condition-coverage` 聚合） | ✓ |
| 49 | BASELINE:17；STATUS:39 | 测试总数：collected **8934**、passed 登记 **8929**（=collected−skipped 5）、净增 **88**（8846→8934） | `pytest --collect-only -q`（无 `-p no:cacheprovider` 时）报 **8934 tests collected**；S 轮 a93c1f6 BASELINE 记 collected **8846**/passed 8841；8934−8846=**88** | `.venv/bin/python -m pytest --collect-only -q \| tail -2`；`git show a93c1f6:BASELINE.yaml \| sed -n '17p'` | ✓（passed=8929 本身见 P1-01） |
| 50 | CHANGELOG:119（工作树）；STATUS:44；BASELINE:481 | 静态检查：ruff 全绿、`ruff format --check .` **809 文件已格式化**、mypy 0 错 **134** 源文件（`mypy src/ config.py`） | 实测 `ruff check .`=All checks passed；`ruff format --check .`=**809 files already formatted**；`mypy src/ config.py`=**Success: no issues found in 134 source files** | 三条命令 | ✓ |
| 51 | CHANGELOG:120-125（工作树） | 门禁链：doc_links **120 文件/550 链接/0 错**、bilingual 0 错、env_budget **251/251**、state_contract **133 文件**、env_snapshot **覆盖 82/缺失 0**、zero_assert **383 测试文件/0 违规**、baseline(+numbers)、json_contract、tool_versions、prompt_artifacts、artifact_doc_consistency、branch_coverage 全通过 | 逐条实跑输出与文档**逐项一致**（doc_links：120 份/550 条/0 错；env-budget：251 唯一变量/登记 251/无未登记；state-contract：133 文件；env-snapshot：覆盖 82/缺失 0；zero-assert：383 文件/0 违规；`check_baseline`、`check_baseline_numbers`、`check_json_contract_sites`、`check_tool_versions`、`check_prompt_artifacts --strict`、`check_artifact_doc_consistency`（含登记册覆盖率对账）、`check_branch_coverage coverage.xml` 均 exit=0） | 逐条运行 `scripts/gates/*.py`（见附录 A） | ✓ |
| 52 | CHANGELOG:117 | 定向：T4 7 文件 **217 passed** | `_evidence/pytest_targeted_final.log`：**217 passed, 1 warning**（collected 217）；7 文件逐个 collect 之和 34+31+35+26+12+40+39=**217** | 读 evidence log；逐文件 `--collect-only` | ✓ |
| 53 | CHANGELOG:117 | T3c **8 文件 187 passed** | `t_round_smt_witness_aliasfix_20261018/RUN_SUMMARY.log`：8 文件定向命令 → **187 passed** | 读 RUN_SUMMARY.log | ✓ |
| 54 | CHANGELOG:117 | T3 既有 **62** passed（另 33 见"无法核验"） | K3 `PREFLIGHT.json.tests.related_result`="**62 passed**…"（`test_oracle_examples.py`） | 读 K3 PREFLIGHT.json | ✓（33 未核验） |
| 55 | BASELINE:313；CHANGELOG:38 | K3 预注册 sha **c4619018…**、PREFLIGHT sha **6b175807…**、canonical 段 sha **88f4e057…** | 文件 sha256 实测：PREREG=**c4619018f6dd…**、PREFLIGHT=**6b175807cd41…**；SAMPLING_REPORT 记录 canonical_section_sha256=**88f4e057a509…** | 脚本 sha256 复算 + JSON 读取 | ✓ |
| 56 | BASELINE:375；CHANGELOG:30 | B1 预注册 sha **5761901e…**、续跑修订 sha **4cb5218d…**、切点 **a93c1f6…** | 文件实测 sha256=**5761901e8686…** / **4cb5218d158e…**；六格 provenance git_sha=**a93c1f60…** | sha256 复算 | ✓ |
| 57 | BASELINE:344-356；CHANGELOG:47 | A-19 真实 LLM 复验 "10 任务×2 臂并发"、切点 **962c77e** | `ISOLATION.json.details.root=/Users/wangchenyu/Workspace/AITester-t-a19-962c77e`、head=**962c77e16b14…**、dirty_lines=0；on/off 各 n=10 | 读 ISOLATION.json | ✓ |
| 58 | BASELINE:340-341；CHANGELOG:46 | "默认关路径由改前生成黄金表 **18/18** 逐位一致锁定；不承诺迭代节省" | 黄金表 18 行（sha 591c93d8…）；`TestOffGoldenTable` 等含于 `test_t_round_semantic_fixes.py` 34 例（实跑 34 passed）；README §1.2 明示"不改变迭代数/不承诺节省" | pytest 实跑 + JSON | ✓ |
| 59 | CHANGELOG:19；README:64 | K=3 花费 **$0.020577** | SAMPLING_REPORT cost_estimated_usd=**0.020577**（预算 0.05 内） | JSON 读取 | ✓ |
| 60 | CHANGELOG.en:18 | 英文花费行仅 `T-COST-PENDING-EN`（无错误数字） | 与中文行差异一致（中文含部分旧估值，见 P2-04/P2-05） | grep | ✓（但内容未完成） |
| 61 | MEAS_INTEGRITY §7；B2 `PREFLIGHT.json`/`PREREG_AMENDMENT` | 跑前成本估算 input 份额误设：原 76% → ≈$4.5；实测 input/output **22%/78%** → 上界 ≈$8.8 | 公式复算：8,755,871 tok ×(0.76×0.3+0.24×1.2)/M = **$4.518**；×(0.22×0.3+0.78×1.2)/M = **$8.773**；R-P0-2 三批全臂 token 拆分 = input **21.4%**/output 78.6%（seed42 aitester 22.2%/77.8%，与修订示例一致）；B2 PREFLIGHT `cost_estimate.est_usd=4.518, input_share=0.76` | 读 3 个 main_batch JSON token_metrics 复算；读 B2 PREFLIGHT.json/AMENDMENT | ✓ |
| 62 | BASELINE:251-256；STATUS:75 | S-2（B8）已 confirmed：on 10/10 vs off 0/10、iterations **1.8 vs 3.0**、Δ **1.2**、cost 0.046531/0.060761 | s_round REPORT verdict=confirmed；on stall 10/10 iters 1.8 cost 0.046531；verdict iterations_saved=1.2 | 读 `s_round_b8_injection_20261018/REPORT.json` | ✓ |

---

## 3. 无法核验项清单（10 项）

| # | 声明 | 位置 | 原因/边界 |
|---|---|---|---|
| 1 | 全量 **8929 passed / 5 skipped / 0 failed**、**192.06s** | `BASELINE.yaml:17,22`、`STATUS:39` | 按纪律未跑全量；无任何 pass/fail 日志工件（coverage.xml 仅行/分支计数）；且提交态有 2 例确定性失败（见 P1-01）。collected=8934、skipped=5、算术关系已核。 |
| 2 | "T3 既有 **62+33** passed" 中的 **33** | `CHANGELOG.md:117` | 62 有 K3 PREFLIGHT `related_result` 工件；**33** 在所有 T 工件中无对应记录/日志（`grep -rn '33 passed' experiments/results/t_round_*` 无命中）。 |
| 3 | "T5 断言/校验补测全绿" | `CHANGELOG.md:117` | 无统一证据日志/清单；本次仅能替代性核验 checksum gate 13 例、artifacts manifest 相关 14 例均通过。 |
| 4 | `python main.py doctor` **exit=0**、"12 个 LLM 探针按强制零 LLM 跳过" | `CHANGELOG.md:128`（工作树） | 未在本次复跑（避免 B2 期间资源争用）；T 轮无 doctor 输出工件（仅在 CHANGELOG 声明）。 |
| 5 | T 轮**真实 LLM 总花费** | `CHANGELOG.md:19` | `T-COST-PENDING` 未填；已可核的部分= B1 $0.876339、K3 $0.020577、A-19 $0.098；B2 与 e2e LLM 探针成本未结算，且首跑中止的 token 费用仅"约"估计（BASELINE:383 "含首跑累计约 40 min / ≈$0.97" 无法复算）。 |
| 6 | **B2 主批次**全部结果数字（seed42/43/44 检出、判定、成本） | README/STATUS/BASELINE 相关引用 | 按任务书排除；且工件尚未产出（见 P0-01）。`seed42_GATE.json` 仅为过程门禁工件，不能替代最终结果。 |
| 7 | "本轮净增 88 例"的**逐文件分解**（"2 例既有用例按行为变更更新"的具体清单） | `BASELINE.yaml:17-19` | 总数差（8846→8934=88）可核；逐项分解无日志/清单工件（测试文件 diff 可见，但无收集级证据）；且"MANIFEST 长度锁"不存在（见 P2-08）。 |
| 8 | CHANGELOG 提交版 `T-TESTS-PENDING` / `T-GATES-PENDING` 的最终值 | `git show d95fca4:CHANGELOG.md` | 提交版为占位符；工作树已填门禁数字（本次全部复核一致），但 `tests`/`cost` 仍未填；最终以后续 commit 为准。 |
| 9 | B1 "六格全过 GATES 16 checks"（作为**正确口径**） | `CHANGELOG.md:34` | 该数字本身可核且**错误**（实际 17，见 P2-01）；此处列为"无法核验"仅指"16"无任何工件支持。 |
| 10 | `.pytest_cache/v/cache/lastfailed` 49 条失败的**归属运行**（哪条命令/哪棵工作树） | —（环境证据，非文档声明） | 文件 mtime 10:08:23（d95fca4 提交前 10s）且含中间态用例名，无法唯一确定其对应命令；但其存在与"0 failed"声明冲突，已并入 P1-01，不作独立结论。 |

---

## 4. 口径纪律抽查（T 轮新增声明是否携带必要限定）

| # | 应有纪律 | 抽查结果 |
|---|---|---|
| 1 | **B2 仍在跑，不得宣称完成** | ❌ README（中/英）、STATUS §2/§3.2/§4、BASELINE 注释均按"已执行/见 b2_*"呈现（P0-01）；仅 CHANGELOG T1 条目与 commit message 如实写"结果待定"（但 CHANGELOG 整体仍称"B2 主批次锁指纹复现"为已做事项）。 |
| 2 | B1 **单数据集/单模型/2 seed/单臂逐格**限定 | ⚠️ 部分：`VALIDITY.md:72` 残余风险完整（单臂逐格、2 seed、synthetic 单数据集、单模型）；CHANGELOG/README 条目本身未重复限定（可接受，因指向 VALIDITY/BASELINE）；BASELINE protocol 含 dataset=synthetic/seeds=[42,44] 但未写"单模型"（tool 区写 deepseek-flash）。 |
| 3 | B1 **不得与 R-P0-2 三臂主批次混池** | ✓ `BASELINE.yaml:384` caliber_note 明确"不得与 R-P0-2 的 3 臂主批次混池（协议不同…）"；`VALIDITY.md:72` 残余②同。 |
| 4 | SMT **pre-fix/post-fix 并列、不得混池** | ✓ CHANGELOG Changed、`BASELINE:335-336`、`smt_witness_batch_plan §6.3` 三处一致。 |
| 5 | A-19 **不得当作收益主张** | ✓ CHANGELOG T4 条、README、`BASELINE:353`、`STATUS:184` 均带"不得当收益主张/负向预注册"。 |
| 6 | K3 **默认关 + 探索性（n=20/单轮 K=3 不外推）** | ⚠️ 部分：生产默认关在 CHANGELOG/README/BASELINE 均写明 ✓；"探索性/n=20/单轮 K=3 不外推"仅在 `oracle_quality_metric §16.3` 与 K3 README 限制节，CHANGELOG/README 未携带（建议补一句限定）。 |
| 7 | SMT **关联层无对照 + MDE 披露** | ✓ CHANGELOG T3b 条、`BASELINE:331-334`、design §6.1 均写"中位数二分退化→无对照；MDE≈16.57pp 披露"。 |
| 8 | B1 **执行修订披露**（首跑中止、辅助测量关闭） | ⚠️ 中文 CHANGELOG 内容错误（P1-03）；b1 README/PREREG_CONTINUATION/VALIDITY/英文 CHANGELOG 均正确披露。 |

---

## 5. 建议处置顺序（供 Lead 参考）

1. **P0-01（B2 文案）**：B2 完成前把 README/STATUS/BASELINE 注释/B2 引用改为"进行中"；B2 完成后另 commit 回填 `target_quality.b2_main_batch_t_round` 与 SHA256SUMS/README/GATES/ANALYSIS。
2. **P1-01（全量测试）**：B2 入库后跑一次全量并把日志/摘要落工件；未完成前不要在 BASELINE/STATUS 写"0 failed（实测）"。
3. **P1-02（SHA 声明）**：按实际 7 目录 + B2/审计待补改为可核对清单。
4. **P1-03（中文 CHANGELOG B1 修订句）**：改为"六格统一重跑"，并在 b1 README 标注 PREREG_CONTINUATION §4 为过时旧计划。
5. **P2 批量**：16→17 checks；4 处→9 处；24%→64%；≈$0.08→$0.098；成本行填已实测项；BASELINE `last_verified`→2026-10-18；VALIDITY 的"B2/B1 分析逐项披露"改为"B1 已披露/B2 待落地"；MANIFEST 长度锁措辞。
6. 复核旁注：本复核创建的输出目录 `experiments/results/t_round_verify_20261018/` 会被 `check_artifacts_tracked.py` 的 `*_round_*` 扫描面识别为未入库目录（连同在跑的 B2），入库/豁免由 Lead 决定。

---

## 附录 A：复核用主要命令（均为只读；未跑全量 pytest）

```bash
# 1) B1 六格：从 staging 批次 JSON 原始行重算检出/配对 McNemar（math.comb 精确二项）
.venv/bin/python - <<'PY'
import json, math
base='experiments/results/t_round_b1_protocol_text_20261018'
# 6 个 meta → batch_path → results[arm].details 逐行 detection_rate>=1.0
...
PY
# 2) K3：SAMPLING_REPORT/ANALYSIS_REPORT/两份重放报告 + K3_STATS 三样本逐条比对
# 3) SMT：TASK_LEVEL.json + PER_CLAUSE.jsonl 独立重聚合（41 primary 任务的 status/witness/reach）
# 4) A-19：ANALYSIS.json + REPORT.json arms/criteria/verdict + ISOLATION.json
# 5) 覆盖率：解析 coverage.xml 根属性 + 逐 class line/condition-coverage
.venv/bin/python - <<'PY'
import xml.etree.ElementTree as ET, re
r=ET.parse('coverage.xml').getroot()
print(r.attrib['lines-covered'], r.attrib['lines-valid'], r.attrib['branches-covered'], r.attrib['branches-valid'])
PY
# 6) 测试收集（不跑全量）
.venv/bin/python -m pytest --collect-only -q 2>/dev/null | tail -2
# 7) 工件存在性/SHA
for d in experiments/results/t_round_*_20261018 experiments/results/e2e_probe_t_round_20261018; do
  .venv/bin/python scripts/gates/checksum_results.py --verify --results-dir "$d"; echo "$d exit=$?"
done
.venv/bin/python scripts/gates/check_artifacts_tracked.py --list | tail -3
# 8) 轻量门禁（全部通过，输出见正文第 50-51 行）
for c in "check_doc_links.py --strict" "check_bilingual_docs.py --strict" "check_env_budget.py --check" \
         "check_state_contract.py" "check_env_snapshot_keys.py" "check_zero_assert_tests.py" \
         "check_json_contract_sites.py" "check_tool_versions.py" "check_prompt_artifacts.py --strict" \
         "coverage_ratchet.py --check" "check_branch_coverage.py coverage.xml" "check_baseline.py" \
         "check_baseline_numbers.py" "check_artifact_doc_consistency.py"; do
  .venv/bin/python scripts/gates/$c; echo "exit=$?"
done
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy src/ config.py
# 9) 定向测试（不跑全量）
.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_t_round_semantic_fixes.py tests/test_spec_smt_result_alias.py \
  tests/test_smt_witness_batch.py tests/test_examples_multisample.py tests/test_batch_quota_preflight.py
```

---

## 附录 B：复核边界声明

- 本次仅打开并复算工件（JSON/JSONL/XML/日志），未修改任何既有文件；唯一写入为本报告。
- 未运行全量 pytest、未运行 B2 相关命令、未读取/打印任何密钥或 `.env*` 内容。
- 文档与工件冲突时**以工件为准**；本文所有"工件值"均可按附录 A 命令复现。
- B2 主批次结果本身按任务书留给 Lead 在其完成后另行复核。
