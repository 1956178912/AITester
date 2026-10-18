# T5a 审计报告：文档 ↔ 工件一致性系统审计（T 轮，2026-10-18）

> 审计角色：T5a 文档/工件一致性审计员（只读）
> 审计时刻：2026-10-18 09:00–09:10（Asia/Shanghai）
> 审计基线：`git HEAD = a93c1f6`（S 轮收口），工作树另有 **T 轮在途未提交改动**（见 §7，审计期间的文档/代码行号以本报告落盘时读到的为准）
> 只读边界：未修改任何既有文件、未 git commit；未读取/打印 `.env.local`；唯一写入为本报告文件。
> 未运行的命令：全量 pytest / `make gates` / mypy 全仓以外的重型门禁（B2 真实 LLM 批次在后台运行，按纪律避免 CPU 争用）。所用命令均为轻量只读：`grep`/`read`/Python 读 JSON/XML、`checksum_results.py --verify`、`coverage_ratchet.py --check`、`check_branch_coverage.py`、`check_json_contract_sites.py`、`check_bilingual_docs.py --strict`、`ruff format --check`、`mypy src/ config.py`、`git log/status/diff`、`shasum -c`。

---

## 0. 结论摘要

| 严重度 | 条数 | 定义 |
|---|---|---|
| **P0** | **4** | 结论性错报：核心结论/技术事实被工件或代码直接推翻，会误导论文口径或后续决策 |
| **P1** | **17** | 状态过时：任务/阻断/数字/进度声明落后于工件，不改变已有结论但会误导读者与排期 |
| **P2** | **14** | 措辞/统计口径/自洽性：数字分解方式、行号、引用路径、清单格式等 |

最关键 6 条（详见 §1）：

1. **P0-01** `docs/VALIDITY.md`（+`.en`）、`docs/study/OPTIMIZATION_2026-10-15.md`、`docs/EVALUATION_SCOPE.md` 仍称"RT1 / 2×2 协议文本消融**未执行**、需 LLM 配额"，而 `experiments/results/e6_a1_batches/rt1_no_reinforcement_seed42/`（2026-10-09）已有真实批次与三臂对照分析，`BASELINE.yaml` 已登记 `benchmark.rt1_sampling_control`，T 轮 B1（3 格 × 2 seed）预注册已在途。
2. **P0-02** `docs/PROJECT_STATUS_REGISTER.md:75`（§2 B8）与 `:143` 仍把 A-19 消融列为"**LLM 配额**阻断 / 待配额"，而 S-2 已以失败注入 harness 完成判定 `confirmed`（工件 `s_round_b8_injection_20261018/REPORT.json`、`BASELINE.yaml:244-250`）。
3. **P0-03** `docs/PROJECT_STATUS_REGISTER.md:247`（§4）仍写 postprocess_wall"**hook 尚未接入 run_benchmark**"，与同文件 `:173`（R-3 已接入）、`BASELINE.yaml:261`（status=R-3 已接入）、代码 `experiments/run_benchmark.py:3701`/`:4064` 及 `docs/COST_MODEL.md` "已接入"直接矛盾。
4. **P0-04** `BASELINE.yaml` 逐模块覆盖率 4 项"100%/1.0000"被**同一节引用的** `coverage.xml` 实测推翻：`graph/nodes.py` 746/747=99.87%（称 702/702）、`planner.py` 109/110=99.09%（称 91/91）、`graph/workflow.py` 分支 99.15%、`error_classifier.py` 分支 96.49%（均称 1.0000/100）。
5. **P1-12** `feature_matrix.probes_total=66` 与三个探针模块实际注册 **68** 个探针不符：`observability-trace-redaction` / `observability-event-bus` 在 `e2e_probes_platform.py` 与 `e2e_probes_workflow.py` **重名**，运行器把 2 个记入 `load_errors` 后静默丢弃，报告仍以 66/66 pass 呈现（**T 轮在途 diff 已去重**：workflow 22、logic 21、platform 25，唯一注册 68 且新增 2 个 T 轮探针；需重跑矩阵后以新报告刷新文档）。
6. **P1-06** `docs/PROJECT_STATUS_REGISTER.md:154`（M-5）的论文审计数字（67 条声明 / SRC 18 条 / 覆盖 61=91.0%）与其引用的工件 `docs/study/PAPER_CONSISTENCY_AUDIT_2026-10-17.md:10-15`（77 / 20 / 71=92.2% / 综合 100%）及 `paper/draft.typ` 本地实测 `// SRC:` 20 条不一致；`docs/study/SUBMISSION_CHECKLIST_2026-10-15.md:243` 用的是工件侧数字。

> 与"本轮已手工发现的 4 例"的关系：P0-01/P0-02/P0-03 与第 1/2/3 例同源（本报告给出更精确的工件证据、影响面与修正建议）；第 4 例（`run_preflight.py::quota_probe` ImportError）在审计时刻已由同事以**未提交 diff** 修复（`git diff scripts/tools/run_preflight.py`，见 §7），但登记册/CHANGELOG/BASELINE 均无该缺陷与修复记录 → 见 P1-16。其余 30 条为本轮新发现。

---

## 1. 分级问题清单

### 1.1 P0（结论性错报，4 条）

| 编号 | 文件:行号 | 原文摘要 | 事实证据（工件/命令） | 建议修正 |
|---|---|---|---|---|
| **P0-01** | `docs/VALIDITY.md:72`、`:106-107`；`docs/VALIDITY.en.md:83`、`:117`；`docs/study/OPTIMIZATION_2026-10-15.md:111`；`docs/EVALUATION_SCOPE.md:60` | RT1 消融"**未执行**"；"2×2 消融（协议文本 vs 多一次采样）**未执行**，阻塞原因…**需 LLM 配额**"；§5.5 "RT1 消融正为此设计…但**未执行**" | ① 工件存在：`experiments/results/e6_a1_batches/rt1_no_reinforcement_seed42/benchmark_synthetic_20261009_193509.json`（2026-10-09T19:30，`baselines=['plain_llm_df']`，RT1 臂 10/87=11.5%）；② 分析已落盘：`experiments/results/e6_a1_batches/README.md:138-166` 给出三臂对照（plain_llm 9/87、RT1 10/87、df 27/87；RT1 vs plain_llm p=1.0000；df vs RT1 +19.5pp、χ²=15.059、p=0.0001）；③ `BASELINE.yaml:874-890` 已登记 `rt1_sampling_control`；④ T 轮 B1 已在途：`experiments/results/t_round_b1_protocol_text_20261018/PREREG.md`（3 格 × 2 seed，干净切点 a93c1f6）+ `experiments/run_t2_b1_protocol_text.sh`；⑤ `docs/VALIDITY.en.md` 与中文版逐条同错（双语同步反而"同步地过时"）。 | 改为："单 seed（seed42）三格对照已于 2026-10-09 执行（RT1 批为 C2 臂；C1/C3 取自同 seed 冷缓存批，跨批拼合，见 e6 README）；**指纹级 3 格 × 2 seed 复现（T 轮 B1）在途**。剩余缺口 = 单 seed/跨批证据强度与干净树指纹，而非'未执行'。" 同步删改 `OPTIMIZATION` §3 行或加"已被后续批次收口"脚注；`EVALUATION_SCOPE` §4 第 1 行同步。 |
| **P0-02** | `docs/PROJECT_STATUS_REGISTER.md:75`（§2 B8 行）、`:143`（§3.2 A-19 行）；关联 `:243`（§4 P 轮"下一轮 B8 重做"） | B8 阻断项"类型=**LLM 配额**"；§3.2 "**消融批次待 LLM 配额**（§2 B8）"；§4 "下一轮：B8 重做需…" | ① S-2 已完成并经预注册判定 `confirmed`：`experiments/results/s_round_b8_injection_20261018/REPORT.json`（on stall 10/10、off 0/10、iterations 1.8 vs 3.0、paired Δ1.2、cost 0.046531/0.060761、isolation 生产零 diff）；② 同文件 `:175`（S-2 行）已如实登记；③ `BASELINE.yaml:244-250` `target_quality.b8_injection` 已登记 `verdict: confirmed`；④ 遗留项已收敛为"生产默认协议下 repair-invalid 同迭代抢占 → 只改标签不省迭代"，T 轮 T4 复验脚本在途（`experiments/run_t4_a19_revalidation.sh`，未跟踪）。 | §2 B8 改为"实验层失败注入消融已完成（S-2 confirmed）；剩余 = 生产默认协议抢占优先级复验（T4 在途）"；§3.2 `:143` 改为"消融已执行（P-2 缩小消融无触发 + S-2 失败注入 confirmed）"；§4 `:243` 改为已完成并指向 S-2。 |
| **P0-03** | `docs/PROJECT_STATUS_REGISTER.md:247`（§4 "Q 轮已收口（后处理可观测）"行） | "`postprocess_wall` 模块 + env 读取 + 双语文档 + 88 测试；**hook 尚未接入 run_benchmark**（登记下一轮…）" | ① 同文件 `:173`（R-3，2026-10-18）："postprocess_wall 接入 run_benchmark…"；② `BASELINE.yaml:258-262` `target_quality.postprocess_wall.status`："R-3（2026-10-18）已接入 run_benchmark：逐基线 mutation/MDO 计时 + summary[postprocess_wall] + granularity=per_baseline"；③ 代码：`experiments/run_benchmark.py:3701` `_attach_postprocess_wall_to_summary`、`:4064` 调用点；④ `docs/COST_MODEL.md:87-101` 双语文档写明"已接入/默认调用路径逐字节等价"；⑤ R-3 附带 23 测试 + golden 对比。 | 该行改为"hook 已接入（R-3，2026-10-18）；Q-3 的'下一轮'登记已收口"；§4 增补 R 轮收口段，避免读者把已接入项当待办。 |
| **P0-04** | `BASELINE.yaml:38`（graph_nodes）、`:40`（planner）、`:47`（graph_workflow）、`:48`（error_classifier） | "graph_nodes: 100（**1.0000**，702/702 行）"；"planner: 100（**1.0000**，91/91 行）"；"graph_workflow: 100（1.0000，K 轮 +1 行）"；"error_classifier: 100（1.0000…）" | 同一节 `BASELINE.yaml:30` 引用的 `coverage.xml`（2026-10-18 06:59 产物）实测：`graph/nodes.py` **746/747=0.9987**（branch 0.9904）；`agents/planner.py` **109/110=0.9909**（branch 0.9167）；`graph/workflow.py` branch-rate **0.9915**、line 0.9972；`agents/error_classifier.py` branch-rate **0.9649**。且行数分母已从登记注释中的 702/91 增长为 747/110。**注**：graph_nodes 的 99.87% 按整数四舍五入会显示为 100，单看表值可解释为舍入；但同行注释明确写 **1.0000 与 702/702**，与 746/747 不符——planner（99.09）与两个分支 100 的声明则无法用舍入解释。复算：Python 解析 `coverage.xml`（见附录 A）。`check_branch_coverage.py coverage.xml` 只报"门槛达标"（rc=0），不输出 1.0000，无法复现"100"。 | 按 coverage.xml 刷新四项（节点 99.87 / planner 99.09 / 两个分支 99.15、96.49），并在注释中写清"整数显示 vs 1.0000"的区别；若主张"核心路由函数子集 100%"，必须给出可复算命令与函数级分母（当前门禁脚本不提供该数字）。同步修正 §4 "J-4 补至 100.00%" 的现行叙述（作为历史可保留，但须标注"当批实测；其后新增行/新分支未覆盖"）。 |

### 1.2 P1（状态过时，17 条）

| 编号 | 文件:行号 | 原文摘要 | 事实证据 | 建议修正 |
|---|---|---|---|---|
| P1-01 | `docs/PROJECT_STATUS_REGISTER.md:3` | "最后更新：**2026-10-17（N 轮**：全功能端到端探针矩阵 56/56 pass…）" | 同文件已含 P/Q/R/S 轮条目（`:167` P-2、`:170` Q-2、`:171` R-1、`:174-176` S-1/2/3，日期均为 2026-10-18），§1 标题自述"2026-10-18 S 轮优化批次实测"。 | 更新抬头为"2026-10-18（S 轮 + T 轮在途）"，并保留历史轮次简述。 |
| P1-02 | `BASELINE.yaml:14` | `last_verified: "2026-10-17"`（注释仍写 N 轮 8320/8315） | 同文件 `:17`/`:22`/`:30`/`:45` 均自述 2026-10-18 S/R 轮实测（8846 collected、161.6s、96.55/92.73%）；违反文件自身维护约定 `:9`"任何功能批次落地后，必须同步更新 last_verified"。 | 更新为 `"2026-10-18"`（T 轮结算后再次刷新）。 |
| P1-03 | `docs/PROJECT_STATUS_REGISTER.md:44`；`BASELINE.yaml:385` | "mypy 0 错（**133** 源文件）"；`mypy_source_files: 133` | 审计实测 `.venv/bin/mypy src/ config.py` → `Success: no issues found in **134** source files`；`git ls-files 'src/*.py'`=133，加 `config.py`=134（N-5 新增 `src/budget/pricing.py` 后未回填）。 | 133→134；重跑并记录命令输出日期。 |
| P1-04 | `docs/PROJECT_STATUS_REGISTER.md:44`；`BASELINE.yaml:382-383` | "ruff 全绿 / **755** 文件已格式化 / ruff_warnings: 0" | 审计实测 `.venv/bin/ruff format --check .` → `3 files would be reformatted, 802 files already formatted`（待格式化文件：`experiments/analyze_t1_b2_main_batch.py`〔未跟踪 T 轮脚本〕、`tests/test_batch_quota_preflight.py`、`tests/test_t_round_semantic_fixes.py`〔T 轮在途测试〕）；文件总数 805 ≠ 755。若 T 轮收尾会修复 3 个文件，仍应保留"T 结算后重跑"的时效标注；755 无法用当前树复现。 | T 轮提交前重跑 `ruff format --check .`/`ruff check .`，按实测刷新"文件数 + 全绿"；若 3 个文件属在途 WIP，出版口径须以收尾提交实测为准。 |
| P1-05 | `docs/PROJECT_STATUS_REGISTER.md:83` | "声明→证据→范围对账表（**11 条声明含 2 条 `contradicted`**）" | `docs/EVALUATION_SCOPE.md` 表内 `contradicted` 实为 **3 条**：C2（`:26`）、C5（`:30`）、C11（`:36`）。 | 改为"11 条声明含 3 条 `contradicted`（C2/C5/C11）"。 |
| P1-06 | `docs/PROJECT_STATUS_REGISTER.md:154` | M-5 "`// SRC:` 6 → **18 条**；**67** 条数字声明 → SRC 覆盖 **61（91.0%）**…综合可追溯率 100.0%" | 其引用的工件 `docs/study/PAPER_CONSISTENCY_AUDIT_2026-10-17.md:10-15`：识别声明 **77**、SRC 覆盖 **71**、仅 SRC 覆盖 **92.2%**、综合 **100.0%**、`// SRC:` 注释 **20**；`paper/draft.typ` 本地实测 `grep -c '// SRC:'`=**20**；`docs/study/SUBMISSION_CHECKLIST_2026-10-15.md:243` 也写 77/20/71。 | 按工件刷新为 77/20/71/92.2%（综合 100%），并注明 draft.typ 为本地件（paper/ 不入库）。 |
| P1-07 | `docs/PROJECT_STATUS_REGISTER.md:194`（§4.1 Q11） | "`paper/draft.typ` 数字与工件一致性（评审仅抽查 3 处 SRC 注释）——补审计划见评审报告 §1.3；重点核验…" | 同文件 `:154` + `:227` 已登记 M-5 完成"首次全文对账…综合可追溯率 100.0%"，工件 `PAPER_CONSISTENCY_AUDIT_2026-10-17.md` 存在。 | Q11 行标注"已由 M-5（2026-10-17）收口"，或移出"仍未决"表；保留"投稿前 TODO 10 项清零"作为残余。 |
| P1-08 | `docs/VALIDITY.md:53`；`docs/VALIDITY.en.md:64` | "该数据集仍为未测状态；复跑前置（**配额闸）未实现**，且重跑未执行" | ① `src/budget/batch_quota.py` 存在（模块文档 `:22` 定义 `AITESTER_BATCH_MAX_CALLS` 批次级上限）；② `scripts/tools/run_preflight.py` 已有批次预算报告与阻断（`:145 batch_budget_report`、`:254` 输出批次级上限；`make preflight` strict 语义）；③ 同文件 `docs/PROJECT_STATUS_REGISTER.md:70`（B3）自称"**配额闸已补**（`AITESTER_BATCH_MAX_CALLS`）；`make preflight --strict` 会阻断未配置状态"；④ T 轮 B2 `PREFLIGHT.json` 实测实现了配额探测（`quota_probe_rc=0`）。 | 改为"配额闸已实现（B3）；重跑仍未执行 → 结论仍为 `not_evaluated`"。 |
| P1-09 | `docs/study/OPTIMIZATION_2026-10-15.md:109`、`:112`、`:115` | §3 表："Prompt Card + 哈希锁 **未执行**"；"success 呈现层降级 **未执行**"；"SWE-bench Lite 重跑 **未执行** … 跑批入口**无配额预算控制**" | ① Prompt artifacts 工件在 `experiments/results/prompt_artifacts_2026-10-15/`（PROMPT_ARTIFACTS.json/md + PROMPT_CARD.md，`SHA256SUMS` 3 项 verify 通过），CI 有 "Check instruction-artifact hash lock" 步骤，`make prompt-artifacts-check` 存在；② B6 已于 `8c2b655` 执行（`experiments/visualize_results.py` 等 5 文件、319 行）；③ `src/budget/batch_quota.py` + preflight 已实现配额控制。 | 在该历史文档 §3 对应行加"（已被 2026-10-16/18 后续批次收口：B6 / prompt artifacts / quota gate）"脚注；`docs/VALIDITY.md` §3/§5.5 引用其 §3 时改用最新状态。 |
| P1-10 | `docs/VALIDITY.md:54`、`:118`；`docs/VALIDITY.en.md:65`；`docs/EVALUATION_SCOPE.md:32` | "**四起**测量伪影全部定案并修复…"；"四起伪影的回归锁…"；C7 "`docs/MEASUREMENT_INTEGRITY.md` **四起**" | `docs/MEASUREMENT_INTEGRITY.md:1` 标题为"口径分叉的**五种**形态"、`:26` "**五起**伪影总表"（第⑤起 = K-5 变异生成器无效变异体；总表行在 `:35`，第⑤起登记见 `:6`/`:21`/`:35`）。 | 统一为"五起"（或按版本注"截至 2026-10-15 为四起；K-5 后为五起"）。 |
| P1-11 | `docs/PROJECT_STATUS_REGISTER.md:249`、`:250`、`:251` | §4 "Q 轮新登记：示例自校验/二次过滤 + … + `postprocess_wall` hook 接入 + B8 重做"；"P 轮新登记：① 返回表示归一… ② 示例自校验… ③ 生产接线…"；"O 轮新登记：… D3b…；rollback schema 扩充；均需下一轮立项" | 已完成项：R-2 示例自校验（`:172`）、Q-1 生产接线（`:169`）、R-3 hook（`:173`）、S-2 B8 重做（`:175`）、P-1.1 表示归一（`:166`）。未完成项：无 Planner 臂生成器成本/质量评估、oracle 语义质量治理（correct 仍 0）、D3b、rollback schema（T 轮在途）——需保留。 | 对 §4 三行逐项加"✅ 已完成（轮次）/⏳ 仍未做"标注；避免读者把已完成项当本轮待办。 |
| P1-12 | `BASELINE.yaml:360`、`:361`、`:363`；`scripts/tools/e2e_probe.py:293` | `probes_total: 66`、`probes_by_group` 合计 66、`status: {pass: 66,…}` | 三个探针模块 `grep -c 'group="'` 合计 **68** 个注册（HEAD 时：platform 25 + workflow 24 + logic 19）；`experiments/results/e2e_probe_20261017/report.json` 的 `load_errors` 明确记录 **2 个重名**：`observability-trace-redaction`、`observability-event-bus`（同时注册于 `e2e_probes_platform.py:1298/1305` 与 `e2e_probes_workflow.py:1277/1284`）；运行器在 `e2e_probe.py:293` 记录错误但不失败，报告仍 `summary={pass:66}`。**T 轮在途 diff 已修复该问题**：`e2e_probes_workflow.py` 删除 2 个重复探针（当前 workflow 22），`e2e_probes_logic.py` 新增 2 个（A-19 抢占优先级 / rollback schema，当前 logic 21），去掉重名后当前工作树唯一注册数 = 25+22+21 = **68**。 | 修复重名（T 轮在途已做）后**重跑矩阵**并刷新计数（预计 68 而非 66）；文档须等 T 轮提交后以新报告为准，不能用旧 66/66 pass 直接延续。 |
| P1-13 | `docs/design/e2e_probe_matrix.md:88` | CI 零 LLM job "跑 … `--all`（**47 个零 LLM 探针**；12 个真实 LLM 探针默认 skip…）" | 审计时刻矩阵：`report.json` 66 探针，其中 `requires_llm=true` 12 → **零 LLM 54**；47 = P 轮时点值（`STATUS:168` P-3 实测 47 pass/12 skip），S 轮后新增探针未回填；T 轮在途又新增 2 个零 LLM 探针（A-19 抢占优先级 / rollback schema）→ 54→56。 | 改为"54 个零 LLM + 12 个 LLM（T 轮结算后预计 56）"，并注明计数随轮次变化，以 `--list` 为准。 |
| P1-14 | `docs/PROJECT_STATUS_REGISTER.md:191`（Q7）；`docs/design/smt_witness_batch_plan.md:8` | Q7 "`SPEC_SMT_ENABLE`…是否有任何启用批次记录"；设计文档"z3 SMT 见证层实现在场…但**无任何启用批次记录**" | `grep -rl '"SPEC_SMT_ENABLE": "true"' experiments/results --include=*.json` = **47 个批次工件**（含 `emse_t08_gates_20261013`、`emse_docstring_anchor_20261017`、`s_round_examples_decision_20261018` 等）；根因 `config.py:55-61/79-80` `_PROFILE_PRESETS` 对 logic 档 `setdefault("SPEC_SMT_ENABLE","true")`；`.venv` 内 **z3 已安装**（`importlib.util.find_spec('z3')` 通过）。同时 T 轮 T3b 专项批在途（`experiments/smt_witness_batch.py`、`tests/test_smt_witness_batch.py` 未跟踪）。 | Q7 更新为"logic 档批次（47 个工件）记录到开关=true；是否有产出型见证/专项评估仍未被评估 → T3b 结算后回填"；设计文档"无任何启用批次记录"改为"无专项评估批次；开关启用记录见 provenance"。 |
| P1-15 | `docs/PROJECT_STATUS_REGISTER.md:238`、`:251` | O 轮"登记下一轮：… `patch_rollback_verdict/rolled_back` **进结果行 schema**"；O 轮新登记"rollback schema **扩充**…均需下一轮立项" | 审计时工作树（T 轮未提交 diff）`experiments/run_benchmark.py:1874`/`:2118` 已把两键写入 `_build_task_result` 成功/失败分支（`git diff` 共 +16 行，注释"T 轮 2026-10-18（O 轮登记项落地）"）；HEAD 提交尚不含 → 属"待 T 提交后文档收口"。当前 BASELINE `metrics_schema:463` 已列两键（早于 run_benchmark 投影）。 | T 轮提交后把 §4 该登记项标"已落地（T 轮）"，并在 BASELINE/BASELINE 注释同步；若 T 轮未提交，则保持"在途"。 |
| P1-16 | `docs/PROJECT_STATUS_REGISTER.md`（全文/§4）、`CHANGELOG.md` 顶部、`BASELINE.yaml` | 无 `run_preflight.py::quota_probe` 缺陷记录 | 任务书第 4 例：旧实现 `from src.agents.llm_client import LLMClient`（`src/agents/llm_client.py` 只有 `LLMEmptyResponseError`，无 `LLMClient` 类）→ `--check-quota` 恒 ImportError/skipped。审计时 `git diff scripts/tools/run_preflight.py` 已含同事修复（改用 `_get_llm_config`/`_get_or_create_chat_client` + config 副作用导入；未提交）；T 轮 B2 工件 `experiments/results/t_round_b2_main_batch_20261018/PREFLIGHT.json` 的 `quota_probe_note` 已记录该缺陷并用独立最小调用替代。文档侧（登记册/CHANGELOG/BASELINE）**无任何记录**。 | 在 T 轮条目中补"缺陷 + 修复 + 验证"（引用 diff/B2 PREFLIGHT 证据），并在 §4 "代码缺陷登记"留痕；提醒：修复尚未提交，文档不得先于提交宣称已修。 |
| P1-17 | `BASELINE.yaml:38`、`:40`、`:47`、`:48`（同 P0-04 的"状态"面）；`docs/PROJECT_STATUS_REGISTER.md:44` | 见 P0-04 | 见 P0-04 | 见 P0-04；此处强调"§1 静态检查行与 BASELINE 覆盖率逐模块行需在同一批次一起刷新"，避免只改一处。 |

### 1.3 P2（措辞 / 统计口径 / 自洽性，14 条）

| 编号 | 文件:行号 | 原文摘要 | 事实证据 | 建议修正 |
|---|---|---|---|---|
| P2-01 | `BASELINE.yaml:30` 与 `docs/PROJECT_STATUS_REGISTER.md:40-41` | BASELINE："2026-10-18 **R 轮**全绿收口全量实测 96.55%…"；登记册："2026-10-18 **S 轮**本机实测 96.55%/92.73%" | 两者数字与 `coverage.xml` 逐位一致（17448/18071、6263/6754）；差异仅在轮次标签。产物 `coverage.xml` mtime 2026-10-18 06:59，S 轮提交在 08:5x，S 轮确有全量跑批（BASELINE:22 "S 轮全绿收口全量 161.6s"）。 | 统一轮次标签（建议"S 轮收口全量"），或注明"R 轮首测、S 轮复核同值"。 |
| P2-02 | `BASELINE.yaml:17` 与 `docs/PROJECT_STATUS_REGISTER.md:39` | BASELINE："净增 25 例 = S-3 多采样 **23 + 探针 1 + 其他 1**"；登记册："净增 25 例 = S-3 多采样 **23 + 探针 2**" | `git show a93c1f6 --name-status`：S 轮新增测试文件仅 `tests/test_examples_multisample.py`（23 例）+ 既有 `tests/test_e2e_probes_logic.py` 等改动（1 例新探针测试）；总数 25 下分解应为 23+1+1。 | 两处统一为 23+1+1（或给出可复算的分文件清单）。 |
| P2-03 | `BASELINE.yaml:366-367`；`docs/PROJECT_STATUS_REGISTER.md:3`、`:233` | BASELINE 字段 `probes_found_and_fixed: 10`；同行注释列 8 项；`:367` "8 个真实功能缺陷"；登记册 `:3` "8 个"、`:233` "6 个" | N-2（2026-10-17）列 6 项；N-5 追加 2 项（USD 记账、跨文件审计字段）→ N 轮合计 **8**；`10` 无对应清单。 | 统一为 8（N-2 六项 + N-5 两项），或补充第 9/10 项证据；登记册 `:233` 的 6 改为 8。 |
| P2-04 | `BASELINE.yaml:874-890` | `rt1_sampling_control`："实测（冷缓存 seed42 n=87）：plain_llm 10.3% · RT1 11.5% · df 31.0%"；`switch: DETECTION_FIRST_SECTION_ENABLE=false` | ① 单批 JSON 只含 `plain_llm_df` 一臂（10/87=11.5%）且 `provenance` 仅 `git_sha/git_dirty/model_name/temperature/cache_namespace`，**无 env_snapshot**，开关取值不可由工件自证；② plain_llm 9/87 与 df 27/87 实来自另一批 `e6_a1_batches/e6_phase1_standard_coldcache/benchmark_synthetic_20261009_190234.json`（跨批拼合；`e6_a1_batches/README.md:138-166` 有对照但 BASELINE 未标注来源）。 | 在 BASELINE 该节注明"跨批拼合（RT1 批 + phase1 冷缓存批）"与"旧批无 env_snapshot、开关仅目录名/README 记录"；T 轮 B1 结算后以新批替换。 |
| P2-05 | `BASELINE.yaml:456-472` | `metrics_schema: [...]`（未含 `llm_suite_detection_rate` / `oracle_suite_verdict` / `spec_oracle_examples_source` / `spec_oracle_examples_count`） | 实测 S-1 批次行共 **95 键**，含上述 4 键（`experiments/results/s_round_examples_decision_20261018/benchmark_quixbugs_20261018_065026.json` 首行）；而同文件既有惯例（ADR-0028/I 轮注释）是"新结果键同步 metrics_schema"。 | 补登 4 键（并把 N-3 的 `oracle_suite_verdict` 字段口径标注"行字段"）；或注明该列表非穷举。 |
| P2-06 | `BASELINE.yaml:130`（`target_quality.mechanism_metrics.docstring_anchor_batch_20261017.artifact`） | "…MISGUIDED_REPORT.json（三臂；**body_digest 7248b145…**；交叉校验 0 mismatch）" | 该工件实测 `run_meta.body_digest = 678463c8…`（`experiments/results/emse_misguided_docstring_anchor_20261017/MISGUIDED_REPORT.json`，其 README `:177` 亦记 678463c8…；`CHANGELOG.md:1044` 同样写 678463c8…）；全仓（除 BASELINE 与本报告）grep `7248b145` 无命中。 | 更新为 `678463c8…`（或注明 7248b145 属哪一版旧工件）。 |
| P2-07 | `CHANGELOG.md:13` 与 `:107` | 顶部 "真实 LLM 花费 **≈$0.42**（S-1 ≈$0.28 + S-2 $0.14 + S-3 $0.011）"；S 轮节 "S-1 $0.27884 + S-2 $0.140324 + S-3 $0.010912 ≈ **$0.43**" | 三数之和 = **0.430076**（$0.43）；若只计 S-2 主批（0.107292）则为 0.397（$0.40）。同一文件两个近似值且口径未注明。 | 统一为 $0.43（含 S-2 冒烟口径）并注明"含 S-2 冒烟 $0.033"，或统一主批口径 $0.40。 |
| P2-08 | `README.md:67`（`README.en.md` 对应行） | "**最近改动** ✅ **2026-10-07** 修复引擎批次 XIV…全量 **4669/0**" | 同表 `README.md:64` "**最新优化** ✅ **2026-10-18 S 轮**"；"最近改动"落后 11 天且仍带旧测试数；与"最新优化"行自相矛盾。 | 把"最近改动"改为"历史里程碑（2026-10-07）"或删除该行（当前改进见"最新优化"+ CHANGELOG）；双语同步。 |
| P2-09 | `docs/PROJECT_STATUS_REGISTER.md:72`；`docs/VALIDITY.md:72`、`:106`；`docs/VALIDITY.en.md:83`、`:117` | B5："detection-first 段落现内联于 `src/graph/nodes.py:549-556`、over-red 于 `:660-676`（…**已按实测校正**）"；VALIDITY："第 550–557 / 671–676 行"、"第 522–535 行"、"第 540–547 行"、"第 487–501 行"、"第 536–539、501、676 行" | 当前 `src/graph/nodes.py`：`_detection_first_regenerate_entry` 定义 **:614**；`_detection_first_section` 定义 **:649**、返回段 **:667**；`_over_red_section` 定义 **:737**、返回段 **:778**；`_detection_first_section_enabled` **:797**；`_over_red_section_enabled` **:677**。所有引用行号均已漂移 >100 行，"已按实测校正"不成立。 | 用当前行号刷新，或改为"函数名 + 哈希锁"引用（文档自己声明行号非哈希口径，建议彻底去掉易漂行号）。 |
| P2-10 | `README.md:1011`、`README.en.md:756`；`README.md:594`、`:961`；`README.md:904` | "测试：`tests/test_risk_approval.py`"；"结构化为 `experiments/results/failure_knowledge_base.json`"、"记录原始响应片段到 `failure_knowledge_base.json`"；"`--enrichment data/swe_bench_lite_enriched.jsonl`" | `tests/test_risk_approval.py` 不存在（实际 `tests/test_risk_approval_matrix.py`）；`experiments/results/failure_knowledge_base.json` 不存在且 `git log --all` 无历史；`data/` 下只有 `quixbugs/`，无 `swe_bench_lite_enriched.jsonl`（也未跟踪）。 | 更正测试路径；为后两者补"由脚本生成/需先下载"的生成说明或删除引用；若确为历史产物，移入历史节。 |
| P2-11 | `README.md`、`README.en.md`、`BASELINE.yaml`（多处）、`docs/VALIDITY.md`（§1/§7） | 引用 `docs/design/false_fix_caliber_matrix.md` | 文件不存在、`git log --all` 无记录；`docs/VALIDITY.md:129` 已如实披露"该路径从未纳入版本控制、不是可引用路径"。 | 保留披露即可；建议把死引用改为纯文本"（已废弃路径）"，避免读者/链接检查误报。 |
| P2-12 | `BASELINE.yaml:355` | `feature_matrix:` 块头注释 "**N 轮（2026-10-17）**：全功能端到端探针矩阵…" | 同块 `measured_at: "2026-10-18"`，内容含 O/P/Q/R/S 轮新增探针（`:367` 自述 3+3+2+1+1），显系 S 轮刷新后块头未更新。 | 块头注释更新为"O–S 轮持续扩充（最近刷新 2026-10-18）"。 |
| P2-13 | `docs/PROJECT_STATUS_REGISTER.md:43` | "门禁总数 **25 道全绿**（口径 = `ci.yml` 主工作流逐提交阻断的门禁检查步骤…**可枚举复算**）" | `scripts/gates/*.py` = **26**、`ci.yml` 引用 `scripts/gates/` 脚本 = **24**（均可复算）；"25 道阻断检查步骤"没有附枚举清单，`ci.yml` 内 `- name:` 共 68 个、无法唯一定义"门禁检查步骤"（例如 `Set up Python` 不算）。 | 在 §3 或 docs 中给出 25 项的显式清单（脚本+步骤名），否则删"可枚举复算"。 |
| P2-14 | `experiments/results/emse_docstring_anchor_20261017/SHA256SUMS`（格式） vs `scripts/gates/checksum_results.py` | 文档/登记册称该目录"SHA256SUMS **165 条校验通过**"（`STATUS:145`、`BASELINE.yaml:970`） | 仓内工具 `python scripts/gates/checksum_results.py --verify --results-dir …` 报 **165 项全部"清单外新增（未记录）"**：清单条目带 `./` 前缀、工具用无前缀相对路径比对（`checksum_results.py` `_collect`/`verify_manifest`）；改用 `shasum -a 256 -c SHA256SUMS` 在该目录 **165/165 OK**（rc=0）。其余目录（e6_a1_batches 1088 项、augment 127、instrument 9、b8 58、decision 56、prompt_artifacts 3）用工具 verify 通过。 | 统一清单生成方式（用 `checksum_results.py --write` 重生成该目录清单，或让工具把 `./` 前缀归一化）；文档注明"165 条校验通过"所用工具。 |

---

## 2. A. BASELINE.yaml 声明逐项核对明细（20 项）

> 方法：逐项找"命令/工件/复算"，读到实测值再对声明；不因"文档说 X"认定 X 成立。证据命令见附录 A。

| # | 声明（文件:行） | 声明值 | 复算/证据 | 判定 |
|---|---|---|---|---|
| 1 | `tests.total_passed` `:17` | 8841 passed / 8846 collected / 5 skipped | 未跑全量（B2 在后台）；`.pytest_cache/v/cache/nodeids` 仅 8039（旧/部分缓存，不作证） | **无法核验**（见 §5） |
| 2 | `tests.suite_seconds` `:22` | 161.6s | 无独立日志工件 | **无法核验** |
| 3 | `coverage.line_total_pct` `:30` | 96.55%（17448/18071） | `coverage.xml` line-rate=0.9655、lines-valid=18071、lines-covered=17448；`coverage_ratchet --check` rc=0 | ✅ 一致 |
| 4 | `coverage.branch_total_pct` `:45` | 92.73%（6263/6754） | `coverage.xml` branch-rate=0.9273、branches-valid=6754、branches-covered=6263；ratchet rc=0 | ✅ 一致 |
| 5 | `coverage.line_core_modules` 10 项 `:35-44` | 99/100/94/100/99/100/96/99/93/98 | `coverage.xml` 逐文件：base_agent 329/333=98.80→99✓、api_manager 459/459✓、dataset_loader 290/309=93.85→94✓、**nodes 746/747=99.87（整数可舍入为 100，但注释称 1.0000/702/702）✗**、code_analyzer 160/161=99.38→99✓、**planner 109/110=99.09（声明 100，无法舍入）✗**、dependency 309/321=96.26→96✓、multi_candidate 296/300=98.67→99✓、cross_file 272/293=92.83→93✓、rag 207/211=98.10→98✓ | **8 一致 / 2 不符**（→P0-04） |
| 6 | `coverage.branch_core_routing` `:47-49` | 三项均 100（1.0000） | XML branch-rate：graph/workflow.py **0.9915**、agents/error_classifier.py **0.9649**、graph/state.py 1.0；`check_branch_coverage.py coverage.xml` rc=0 但只报门槛达标、不输出 1.0000 | **1 一致 / 2 不符**（→P0-04） |
| 7 | `coverage` ratchet 水位 `:30/:45` | 96.4 / 92.5 | `docs/coverage_ratchet.yaml` line_total 96.40、branch_total 92.50；`coverage_ratchet.py --check` rc=0（余量 +0.15/+0.23pp） | ✅ 一致 |
| 8 | `static_checks.ruff_version` `:382` | 0.16.3 | `requirements.lock:109 ruff==0.16.3` | ✅ 一致 |
| 9 | `static_checks.mypy_errors` / `mypy_source_files` `:384-385` | 0 错 / 133 文件 | `mypy src/ config.py` → `Success: no issues found in **134** source files` | **文件中数不符**（→P1-03） |
| 10 | `static_checks.ruff_warnings` `:383` + STATUS `:44` | 0 / 755 文件已格式化 | `ruff format --check .` → 3 files would be reformatted, 802 already formatted（3 个含 T 轮在途文件） | **不符**（→P1-04） |
| 11 | `error_categories` `:389` | 18 | `src/agents/error_classifier.py::ErrorCategory` 枚举成员逐个数 = 18 | ✅ 一致 |
| 12 | `synthetic_templates` `:391` | 50 | 8 个 pattern 池合计 16+6+8+11+4+2+1+2 = **50**（`verify_synthetic_templates.py::_POOLS` 同集合） | ✅ 一致 |
| 13 | `python_ci_matrix` `:387` | 3.12/3.13/3.14 | `.github/workflows/ci.yml:118` `python-version: ['3.12','3.13','3.14']` | ✅ 一致 |
| 14 | `benchmark.current_main_batch` `:480` | `experiments/results/main_batch/benchmark_synthetic_20261006_140906.json` | 文件存在 | ✅ 一致 |
| 15 | `benchmark.rt1_sampling_control` `:881-890` | plain_llm 9/87、RT1 10/87、df 27/87；p=1.0/0.0001；δ=+0.1868 | RT1 批 10/87 ✓；phase1 批 plain_llm 9/87、df 27/87 ✓；但两批非同批、RT1 批无 env_snapshot（→P2-04） | **数值一致、口径未标注** |
| 16 | `benchmark.exec_2026_10_09.e4_resettled` `:724-738` | aitester 17/37=45.9%、repair 37/40=92.5%；df 31/37=83.8% | `e4_quixbugs_FIXED_harness/aitester.json` 17/37（repair 均值 0.925）；`plain_llm_df.json` 31/37 | ✅ 一致 |
| 17 | `target_quality.oracle_quality` `:137-152` | injection 49/38/11/1；correct 0/fp 29/silent 9；fp 0.763158；输入 sha 813c/536d/3e90 | `ORACLE_QUALITY_REPORT.json`：inputs sha 逐位匹配 813c…/536d…，anchor_table sha 3e90… 匹配；注入 49/38/11/1；四分类 0/29/9/0；fp_share 0.763158 | ✅ 一致 |
| 18 | `target_quality.mechanism_metrics` `:112-136` | doc 批 df 49.61/doc 40.32/union 41.06；augment effective +9.07/-1.01/-8.07；both_fail +10.75/+6.94 | `MISGUIDED_REPORT.json` 两批 comparison：doc pair effective 49.6073/40.3178（Δ−9.2895）；both_fail Δ+6.9379；augment effective 47.8469/56.9182（Δ+9.0713）、misguided Δ−1.0013、both_pass Δ−8.0713、both_fail Δ+0.0013 | ✅ 数值一致（`body_digest` 声明值除外 →P2-06） |
| 19 | `target_quality.docstring_anchor` / `docstring_augment` `:962-1063` | 86.11/60.00/61.76%；80.56/82.86%；12 个批次/报告 SHA | 3+2 个批次 JSON 的 detection 逐臂复算一致；12 个声明 SHA256（批次/报告/README/SHA256SUMS/PROMPT_EVIDENCE）**全部逐位匹配** | ✅ 一致 |
| 20 | `target_quality.b8_injection` / `examples_decision` / `examples_multisample` / `self_mutation` / `compile_exec` / `feature_matrix` | S-2/S-1/S-3/self-mutation/compile-exec/66 探针 | S-2 REPORT（10/10、0/10、1.8/3.0、Δ1.2、$0.046531/0.060761、$0.107292）✓；S-1 ANALYSIS（Δ6×3、loss 20/0/0、enable_candidate、$0.27884）✓；S-3 digest/artifact `8f1440a5` verify 10 项 ✓；self_mutation 165/215→177/215 ✓、CI gate `self_mutation_ci/gate.md` 0.9067（68/75）✓；compile_exec quixbugs 1.0/0.82、union 0.98、main_batch 0.9958/0.9949 ✓；feature_matrix report 66/12/66 pass/74.3s ✓（另有 P1-12 重名问题） | ✅ 主体一致 |

补充：`benchmark.metrics_schema`（`:456-472`）与结果行存在登记缺口 → P2-05。

---

## 3. B. PROJECT_STATUS_REGISTER §2/§4 逐条判定（只列"发生变化"的条目）

| 条目 | 位置 | 判定 | 依据 |
|---|---|---|---|
| §2 B1（2×2 消融） | `:68` | **已过时（高优先）** | RT1 批已执行（2026-10-09）；T 轮 B1 3 格×2 seed 预注册在途 → P0-01 |
| §2 B2（锁指纹重跑主批次） | `:69` | **状态变化（T 轮在途）** | T 轮 T1/B2 正在执行：`experiments/results/t_round_b2_main_batch_20261018/PREFLIGHT.json`（dirty=0、quota_probe ok、synthetic 87×3 seed×3 臂、预算 $6）；`traces_seed42` 已产出 46 个 trace；HEAD 切点 a93c1f6。结算后 B2 可由"LLM 配额"改为"已完成/见工件" |
| §2 B3（SWE-bench 重跑） | `:70` | **仍成立**（重跑未执行）；但 VALIDITY 称配额闸未实现 → P1-08 |
| §2 B4（E7 人工复核） | `:71` | **仍成立** | `docs/HUMAN_ADJUDICATION_PROTOCOL.md:77-78` 抽样框 72 行（sbfl 单层）→ 10% = 8 行；工作表 `experiments/results/main_batch/e7_review_worksheet.md` 含 8 个候选；仍无 Kappa 工件 |
| §2 B5（Prompt Card + 哈希锁） | `:72` | **主体成立，行号过期** | prompt artifacts 工件与门禁在（`experiments/results/prompt_artifacts_2026-10-15/`，verify 3/3；CI step + `make prompt-artifacts-check`）；JSON 契约门禁 `check_json_contract_sites.py --report` 口径 A 通过；但 nodes.py 行号 549-556/660-676 已漂移 → P2-09 |
| §2 B6（success 呈现层降级） | `:73` | **成立（已完成）** | commit `8c2b655` 存在（`experiments/visualize_results.py` 等 5 文件 +319 行；新测试 `tests/test_visualize_results_b6.py`） |
| §2 B7（原始 LLM 响应归档） | `:74` | **仍成立** | trace JSONL 首行 keys 仅 `event/task/ts/meta`，meta 仅 `dataset_task_id/baseline/target_function` → 不含原始响应 |
| §2 B8（A-19 消融） | `:75` | **已过时（高优先）** | S-2 confirmed（见 P0-02）；剩余为生产默认协议复验（T4 在途） |
| §4 Q11（论文数字审计） | `:194` | **已收口未同步** | M-5 完成全文对账（`PAPER_CONSISTENCY_AUDIT_2026-10-17.md`，综合 100%）→ P1-07（数字版见 P1-06） |
| §4 跨文件 D3b | `:238`、`:251`、`:278` | **仍成立** | `build_cross_file_repair_plan` 定义于 `src/tools/cross_file.py:414`，`src/graph/` 零调用点（`src/graph/nodes.py:1954` 注释"尚未接入图"；`o_round_cross_file_20261017/_helpers/preflight_zero_llm.py:159` AST 扫描证据） |
| §4 rollback schema | `:238`、`:251` | **T 轮在途已实现（未提交）** | `git diff experiments/run_benchmark.py`：成功/失败两分支各 +2 键（`:1874`/`:2118`）→ P1-15 |
| §4 后处理预算/watchdog | `:242` | **部分仍成立** | R-3 已给逐基线 `postprocess_wall` 计时（代码 + COST_MODEL），但"可配置预算 + 阶段阈值 watchdog"未在 `run_benchmark` 中发现实现（grep 无 stage 预算配置） |
| §4 Q/P 轮新登记清单 | `:249-251` | **多项已完成未标注** | 见 P1-11 |
| §4 Q7（SMT witness） | `:191` | **可部分回答，需更新** | 47 个批次工件记录 `SPEC_SMT_ENABLE=true`；T3b 专项批在途 → P1-14 |
| §4 评分表"建议做 B5 文本目检" | `:199` | **仍成立**（人力项） | 无目检记录工件；PROMPT_ARTIFACTS 仅机检 |

---

## 4. C. README / CHANGELOG 抽查 10 点（双语）

| # | 检查点 | 结果 |
|---|---|---|
| 1 | README `最新优化` 行（`:64`）与 BASELINE S 轮节（S-2/S-3/S-1）数字 | ✅ 一致（stall 10/10、iters 1.8/3.0、correct 8→3、Δ+6/3 seed） |
| 2 | README `最新优化` "探针矩阵 65→66（多采样自一致性探针）" | ✅ 与 report 66 一致；65 为 S-3 前基数（O/P/Q/R 新增 3+3+2+1=9，56+9=65）可对账 |
| 3 | README `最新优化` 指向 BASELINE 新节 | ✅ `target_quality.examples_decision` / `examples_multisample` / `b8_injection` 均存在（`:227/:236/:244`） |
| 4 | README 测试/覆盖率披露策略（"数值一律指向 BASELINE"） | ✅ 不再硬编码（`:41-49` 表格） |
| 5 | README `最近改动` 行（`:67`） | ❌ 仍为 2026-10-07 + 全量 4669/0 → P2-08 |
| 6 | README `docs/design/false_fix_caliber_matrix.md` 引用 | ⚠ 死路径，但文档已披露"从未入库" → P2-11 |
| 7 | README 测试路径/工件路径引用（`:1011`、`:594`、`:904`） | ❌ 3 处指向不存在的文件 → P2-10 |
| 8 | CHANGELOG 顶部（`CHANGELOG.md:3`）：S 轮内容与 BASELINE 一致、`Last updated 2026-10-18` | ✅ 主体一致；S 轮总花费 `≈$0.42`（`:13`）与同文件 `:107` `≈$0.43` 不一致 → P2-07 |
| 9 | 双语结构：`README.md` 24 个 `##` vs `README.en.md` 24 个；`check_bilingual_docs.py --strict` rc=0（0 警告/0 失败） | ✅ 同步；README.en 同样有 S 轮"Latest Optimization"行（`:82`）与同样 3 处失效路径（含 `test_risk_approval.py` `:756`）→ P2-10 |
| 10 | CHANGELOG.en 顶部与 CHANGELOG.md 对读 | ✅ 均 2026-10-18 S 轮、S-2/S-3/S-1 内容对应（双语门禁同源） |

---

## 5. D. `docs/` 其他"未执行/未接入/待做"类声明核对（重点项）

| 主题 | 文档声明 | 代码/工件实况 | 判定 |
|---|---|---|---|
| oracle 质量（A-05） | `MEASUREMENT_INTEGRITY.md:190-378` §6 已更新到 O-1/O-2/P-1/Q-1/R-2/S-3，数字 fp 29→2、分母 38→11、correct 0 不变 | 工件 `emse_oracle_instrument_hardening_20261017/`（SHA 44a1f3ab verify 9 项）、`ORACLE_QUALITY_REPORT.json`（correct 0/fp 29/silent 9）、代码 `src/specs/spec_ir_v2.py:996/1115/1232` 的 `oracle-unavailable` 崩溃安全机制在 | ✅ 一致（无需修改） |
| 崩溃安全 harness | O-1 称崩溃→`pytest.skip("oracle-unavailable: …")`、skip 单列 unavailable | `src/specs/spec_ir_v2.py:989-999/1100-1115/1219-1232` + `tests/test_oracle_instrument_safety.py` 在；`_m1_metrics` skip→unavailable 已在 N-3/O-1 工件复算 | ✅ 一致 |
| postprocess_wall | R-3 已接入（BASELINE/COST_MODEL）；但 STATUS §4:247 称"尚未接入" | `experiments/run_benchmark.py:3701/4064` + `experiments/postprocess_wall.py`；`docs/COST_MODEL.md:87-101` | ❌ STATUS 一处矛盾 → P0-03 |
| 示例通道 | P-1/Q-1/R-2/S-3 已实现（生产开关默认关、自校验默认开、多采样判定高风险默认关） | `src/graph/nodes.py`（SPEC_ORACLE_EXAMPLES_ENABLE 门）、`experiments/run_benchmark.py:488-615/2084/4263`、`src/specs/spec_ir_v2.py:1494 self_validate_examples`、`experiments/spec_examples_generator.py:487 generate_examples_multisample`；`docs/design/oracle_quality_metric.md` §13/§14/§15 在；工件 4 个目录 SHA verify 通过 | ✅ 一致；`docs/MEASUREMENT_INTEGRITY.md` §6 口径已覆盖 |
| A-19 停滞检测 | P-2 wiring 修复 + S-2 confirmed（文档 §3.2:167/:175） | 代码 `src/graph/nodes.py:1435`（`_should_debug` 消费）、`experiments/run_benchmark.py:3061/3072/4480/4486`（互斥 CLI）；工件 `p_round_b8_ablation_20261018`（无触发）、`s_round_b8_injection_20261018`（confirmed） | ✅ 代码/工件一致；仅 §2/§3.2:143 状态行过期 → P0-02 |
| per-test 超时（A-06） | `docs/design/misguided_effective_metric.md:181/208/254-259`：A-06 判分 per-test 超时已落地（超时记红） | `experiments/_m1_metrics.py:65/483` 已实现 `--timeout=N`（pytest-timeout signal）；`tests` 中 `pytest_timeout_available` 代码路径在；`docs/reviews/...:732` 记 A-06 已完成 | ✅ 一致（无需修改） |
| SMT witness（Q7） | 设计文档 `smt_witness_batch_plan.md:8`："无任何启用批次记录"；STATUS Q7 未决 | 47 个批次 `env_snapshot.SPEC_SMT_ENABLE="true"`（logic 预设）；z3 已安装；T3b 专项批在途 | ❌ 措辞需更新 → P1-14 |
| D3b（跨文件计划构建器接线） | "图内零调用点，需下一轮立项" | `src/tools/cross_file.py:414` 定义；`src/graph/` 零调用（nodes.py:1954 注释；O 轮 preflight AST 证据） | ✅ 仍成立（无需修改） |
| rollback schema | "进结果行 schema 待做/扩充" | T 轮未提交 diff 已实现 2 键投影（成功/失败分支）；HEAD 未含 | ⏳ 待 T 提交同步 → P1-15 |
| 配额闸（B3/SWE-bench） | VALIDITY:53 "前置换闸未实现"；STATUS B3 "已补" | `src/budget/batch_quota.py`、`run_preflight.py:209`、B2 PREFLIGHT 实测 | ❌ VALIDITY 过时 → P1-08 |
| E7 人工复核 | 全仓一致：未执行、无 Kappa | `HUMAN_ADJUDICATION_PROTOCOL.md`、`e7_review_worksheet.md`（8 候选、判定列空） | ✅ 一致（无需修改） |
| ADR 待做 | ADR-0029 "物化前置 fail-closed 未实现（待立项）"；ADR-0034 "从未执行搜索批次" | ADR-0029 边界未在 `_m1_metrics`/executor 发现新实现；ADR-0034 无 orchestration 搜索批次工件（`experiments/results/` 无相关目录） | ✅ 仍成立（无需修改） |

---

## 6. E. feature_matrix 探针数核对

| 项 | 文档/工件 | 结果 |
|---|---|---|
| 实际注册数 | `grep -c 'group="' scripts/tools/e2e_probes_{platform,workflow,logic}.py` → 25 + 24 + 19 = **68** | — |
| 运行器发现数 | `experiments/results/e2e_probe_20261017/report.json` → `len(probes)=66`；`load_errors` 2 条（重名：`observability-trace-redaction`、`observability-event-bus`） | ❌ 66 ≠ 68 → P1-12 |
| 分组 | 注册：observability=6；报告/BASELINE：observability=**4**（其余 13 组一致：cli 6/workflow 3/agents 3/repair 2/safety 5/localization 3/budget 4/cache 3/rag 2/security 4/executor 5/dataset 4/logic 18） | 差异即上述 2 个重名探针 |
| LLM 探针 | 报告 `requires_llm=true` 12；`BASELINE.yaml:362 llm_probes: 12` | ✅ 一致 |
| 通过状态 | 报告 `summary={pass:66}`；BASELINE `status={pass:66,fail:0,error:0,skip:0}` | ✅ 报告内一致（但见上） |
| 墙钟 | 报告 66 探针 duration 求和 = **74.3s**；BASELINE `:364 wall_seconds: 74.3` | ✅ 一致 |
| N 轮"新功能必须新增探针"纪律 | S 轮新增多采样探针 1 个（e2e_probes_logic.py +36 行，`test_e2e_probes_logic.py` +1 例）；O/P/Q/R 各轮新增见 BASELINE `:367`（3+3+2+1+1） | ✅ 在册；但 2 个重名探针从未执行 → 矩阵完整性缺口 |
| 历史计数并存 | STATUS `:155`（N 轮 56）、`:164`（O 轮 44 零 LLM）、`:168`（P-3 47 pass）、`:233`（56/6）与当前 66/54 并存 | 属历史条目，建议加"历史时点"标签（P1-11 的一部分） |
| **T 轮在途变化** | 审计后工作树继续变动：`e2e_probes_workflow.py` 删除 2 个重名探针（24→22）、`e2e_probes_logic.py` 新增 2 个（19→21：A-19 抢占优先级 / rollback schema）→ 唯一注册总数仍 **68**，但组成已变；`tests/test_e2e_probes_logic.py` 改动、`tests/test_t_round_semantic_fixes.py` 新增 | T 轮提交后必须重跑 `python scripts/tools/e2e_probe.py --all --include-llm` 并刷新 BASELINE `feature_matrix`（计数/分组/status/wall/artifacts）与 `docs/design/e2e_probe_matrix.md` §5 |

---

## 7. F. 工件可复算性（checksum verify）与缺失工件

### 7.1 SHA256SUMS verify（≥5 个通过，全部只读）

| 目录 | 工具结果 |
|---|---|
| `experiments/results/e6_a1_batches` | ✅ `checksum_results.py --verify`：**1088 项全部一致** |
| `experiments/results/emse_docstring_augment_20261017` | ✅ **127 项全部一致** |
| `experiments/results/emse_oracle_instrument_hardening_20261017` | ✅ **9 项全部一致** |
| `experiments/results/s_round_b8_injection_20261018` | ✅ **58 项全部一致** |
| `experiments/results/s_round_examples_decision_20261018` | ✅ **56 项全部一致** |
| `experiments/results/prompt_artifacts_2026-10-15` | ✅ **3 项全部一致** |
| `experiments/results/emse_docstring_anchor_20261017` | ⚠ 工具 `--verify` 报 165 项"清单外新增"（`./` 前缀格式不兼容）；`shasum -a 256 -c SHA256SUMS` **165/165 OK** → P2-14 |
| 声明 SHA 抽检（BASELINE/STATUS 内的批次/报告/清单哈希） | ✅ 31 个可定位的声明 SHA256 全部逐位匹配（anchor 3 批/报告/锚表、augment 2 批/报告/README/SHA256SUMS/PROMPT_EVIDENCE、O-1/O-2/N-3/S/R/Q/P SHA256SUMS 前缀、S-2 REPORT/PREREG、S-1/R-1/Q-2/P-1/P-2 SHA）；另发现 1 个 `body_digest` 声明不符（P2-06） |

### 7.2 文档引用但**不存在**的工件（F 要求 ≥3 例）

| # | 引用位置 | 缺失对象 | 证据 |
|---|---|---|---|
| 1 | `README.md:594`、`:961` | `experiments/results/failure_knowledge_base.json` | 工作树不存在；`git log --all -- <path>` 无输出（从未入库） |
| 2 | `README.md:904` | `data/swe_bench_lite_enriched.jsonl` | `ls data/` 仅 `quixbugs/`；未跟踪、无 git 历史；README 未说明需先生成 |
| 3 | `README.md:1011`、`README.en.md:756` | `tests/test_risk_approval.py` | 不存在；实际文件 `tests/test_risk_approval_matrix.py` |
| 4（已披露） | `README.md`/`BASELINE.yaml`/`docs/VALIDITY.md:129` | `docs/design/false_fix_caliber_matrix.md` | 不存在且从未入库；`VALIDITY.md:129` 已如实说明"不是可引用路径" → 仅建议清理死引用 |
| 5（工件目录） | 见 P2-06 | `emse_misguided_docstring_anchor_20261017/MISGUIDED_REPORT.json` 的 `body_digest 7248b145…` | 实际 `678463c8…`；全仓无 7248b145 |

### 7.3 完整性/可复算性观察（非问题）

- `coverage.xml` 与 BASELINE 总行/总分支逐位一致；ratchet 只升水位检查 rc=0。
- `check_json_contract_sites.py --report` 口径 A 通过（7 个显式 `json_mode=True` 点；输出中另列 6 个 `json_mode` 变量调用候选，非口径 A）。
- `check_bilingual_docs.py --strict` rc=0（0 警告/0 失败）。
- `mypy src/ config.py` 0 错、134 文件（与文档 133 不符，见 P1-03）。
- `ruff format --check` 3 个待格式化文件（见 P1-04）。
- `check_branch_coverage.py coverage.xml` rc=0（门槛达标），但其输出不含逐模块 1.0000 数字（见 P0-04）。

---

## 8. 无需修改（已核验一致）抽样清单

> 每条都做过"声明 ↔ 工件/命令"对照；建议 Lead 在最终同步时保留这些段落不动。

| # | 已核验一致的声明 | 证据 |
|---|---|---|
| 1 | 总覆盖率 96.55% / 92.73% 与 ratchet 水位 96.4/92.5 | `coverage.xml`（17448/18071、6263/6754）；`coverage_ratchet.py --check` rc=0 |
| 2 | L 轮 docstring 锚三臂终局：df 31/36=86.11%、doc 21/35=60.00%、union 21/34=61.76%、δ=−25.71pp、p_two=0.0352、BF10=3.6274、MDE 16.57、verdict not_confirmed | 3 个批次 JSON 逐臂计数；`DF_DOC_REPORT.json` 的 detection/contrast/verdict；12 个声明 SHA 逐位匹配 |
| 3 | M 轮增广二臂：df 29/36=80.56%、aug 29/35=82.86%、δ=+2.86pp、p=0.5、BF10=0.3125、non-inferior；审计 40 attempted_augmented / 10 fallback | 2 个批次 JSON；`DF_AUG_REPORT.json`；批次行 `spec_augment_applied` Counter；2 批 SHA 匹配 |
| 4 | oracle 质量：输入 sha（df_spec 813c…/df 536d…/锚表 3e90…）、注入 49→38（76%）、correct 0 / fp 29 / silent 9 / misguided 0、fp_root_cause 类型计数 | `ORACLE_QUALITY_REPORT.json`（inputs/anchor_table/arms/comparison 逐格一致） |
| 5 | S-2 B8：on stall 10/10、off 0/10、iterations 1.8 vs 3.0、Δ1.2、成本 $0.046531/$0.060761、主批 $0.107292、0 crash、生产零 diff | `s_round_b8_injection_20261018/REPORT.json` + `ISOLATION` + SHA verify 58 项；BASELINE `:244-250` |
| 6 | S-1 3-seed 决策：三 seed Δ 均 +6、loss 20/0/0pp、McNemar p=0.015625、verdict enable_candidate、决策非能力主张 | `s_round_examples_decision_20261018/ANALYSIS_REPORT.json → three_seed_decision`；seed44 两臂 cost 0.142296/0.136544 |
| 7 | self_mutation：before 165/215=0.7674、after 177/215=0.8233；CI gate 0.9067（68/75） | `self_mutation_l_round/self_mutation_l_round.json` summary；`self_mutation_ci/gate.md:30` |
| 8 | compile/exec 率：QuixBugs 五臂 compile 1.0/exec 0.82（排除驱动任务 1.0，union compile 0.98）；main_batch aitester 0.9958/0.9949、plain_llm 1.0/1.0、df 0.9952 | `emse_compile_exec_20261017/COMPILE_EXEC_REPORT.json`（batches/pooled_by_round_arm） |
| 9 | E4 重结算：aitester detection 17/37=45.9%、repair 37/40=92.5%；df 31/37=83.8% | `e6_a1_batches/e4_quixbugs_FIXED_harness/{aitester,plain_llm_df}.json` |
| 10 | 静态数字：ErrorCategory 18 类；合成 pattern 池合计 50；CI Python 矩阵 3.12/3.13/3.14；ruff 0.16.3 钉版；`scripts/gates` 26 脚本/CI 引用 24；env 预算 251 项（含新增 3 键） | 枚举计数/`requirements.lock:109`/`ci.yml:118`/`docs/env_budget.yaml:3`（env_total:251） |
| 11 | B2 "近 5 个批次 model_fingerprint.pinned=true" | 6 个近批目录共 14 个批次 JSON：`pinned=True`、`git_dirty=False`（anchor/augment/O-2/Q-2/R-1/S-1） |
| 12 | E7 抽样口径 72 行单层 → 8 行；工作表 8 个候选、判定列空 | `HUMAN_ADJUDICATION_PROTOCOL.md:77-78`；`e7_review_worksheet.md`（`grep -c '^## 候选'`=8，candidates 8） |
| 13 | B7 traces 不含原始响应 | trace JSONL first-line keys = event/task/ts/meta；meta 仅 3 键（无 response 字段） |
| 14 | D3b 图内零调用点 | `src/tools/cross_file.py:414` 定义；`src/graph/` 无调用（nodes.py:1954 注释 + O 轮 preflight AST 证据） |
| 15 | B6 success 呈现层已执行 | commit `8c2b655`（B6）+ 5 文件改动、`tests/test_visualize_results_b6.py` |
| 16 | feature_matrix 报告主体（66 探针/12 LLM/66 pass/74.3s 与 BASELINE 一致） | `e2e_probe_20261017/report.json`（计数/墙钟） |
| 17 | 双语同步（README/CHANGELOG/docs 配对） | `check_bilingual_docs.py --strict` rc=0；README.md/en 均 24 个 `##`；两 README 均有 S 轮行 |
| 18 | MEASUREMENT_INTEGRITY §6 的 O-1/P-1/Q-1/R-2/S-3 口径与工件数字 | `oracle_instrument_hardening`（fp 29→2、分母 38→11）、`p_round_oracle_examples`、`q_round_examples_ab`、`r_round_examples_selfcheck`、`s_round_examples_multisample` 工件与报告 |
| 19 | P-2 缩小消融：两臂 stall=0、detection 0/10、cost 0.022606/0.024666、total 0.047272 | `p_round_b8_ablation_20261018/ABLATION_REPORT.json` |
| 20 | B4/E7 未执行、无 Kappa；B5 哈希锁门禁运行、7 个 JSON 契约点 | 全仓无 Kappa 工件；`check_prompt_artifacts` CI step；`check_json_contract_sites.py --report` 口径 A 通过 |

---

## 9. 无法核验清单（本报告不作判定）

1. **全量测试 8841 passed / 8846 collected / 5 skipped / 162s / 0 xfail**（BASELINE `:16-22`、STATUS `:39`）：按审计纪律不跑全量 pytest（B2 真实 LLM 批次在后台）；`.pytest_cache/v/cache/nodeids`=8039 为旧/部分缓存，不能作证。
2. **STATUS §1 "门禁 25 道全绿"**（`:43`）：`scripts/gates` 26 脚本、CI 引用 24 个脚本可复算，但"25 道逐提交阻断检查步骤"无显式枚举清单，无法唯一定义/复算（→P2-13）。
3. **BASELINE `tests.slim_environment=1863`**（`:21`）：文件自述 2026-10-05 后未重测；无当前精简环境工件。
4. **`target_quality.specificity_gate` 40/66 vs 162/140、`mutation_score` 区间、`spec_compile_rate`/`spec_expr_coverage` 分数据集数字**（`:64-111`）：需重放 10 批 main_batch 工件/依赖 LLM 缓存，超出本次轻量边界；仅确认所引工件路径存在。
5. **oracle_quality "任务级检出贡献 40 口径"三列**（archived→llm-only→mixed，`:147-149`）：报告 JSON 内字段在，本次未逐任务重算（只核了注入/四分类/输入 sha）。
6. **O-2 墙钟 2297.4/2311.4s、attempt 历史金额细节**（`BASELINE:194-199`）：`ARM_COMPARISON.json` 顶层未含 wall_seconds（cost/batch_sha 已核），墙钟可能在 README/日志，未逐项复核。
7. **`paper/draft.typ` 全文一致性**：paper/ 不入库（本地件），仅核对到本地 `// SRC:`=20 与审计报告一致；投稿前 SRC 完整性以本地件 `make paper-audit` 为准（未运行）。
8. **Docker build / actionlint**：本机未安装（文档已披露；未预演）。
9. **人工项**：B4 E7 执行、B5 文本目检（人力）无法自动核验。
10. **T 轮在途结果**（B1/B2/T3b/T4 等）：审计时刻未结算（见 §10），不能核验，也不应在文档中提前宣称。

---

## 10. 附：T 轮在途观察与最终同步提示（供 Lead 使用，非缺陷判定）

审计时刻 `git status`（HEAD=a93c1f6）显示 T 轮工作正在主树进行，以下内容**尚未提交**，因此本报告对它们的判定一律为"在途/待结算"：

- 修改（12 个）：`experiments/run_benchmark.py`（rollback schema 投影 +16 行，注释"T 轮"）、`experiments/spec_examples_generator.py`、`scripts/gates/check_artifacts_tracked.py`、`scripts/tools/run_preflight.py`（quota_probe 修复）、`scripts/tools/e2e_probes_logic.py`（+2 探针：A-19 抢占优先级 / rollback schema）、`scripts/tools/e2e_probes_workflow.py`（-2 个重名探针）、`src/graph/state.py`、`src/graph/workflow.py`、`tests/test_artifacts_tracked_gate.py`、`tests/test_batch_quota_preflight.py`、`tests/test_e2e_probes_logic.py`、`tests/test_examples_multisample.py`；
- 新增未跟踪（7 个）：`experiments/analyze_t1_b2_main_batch.py`、`experiments/run_t1_b2_main_batch.sh`（T1/B2）、`experiments/run_t2_b1_protocol_text.sh`（T2/B1）、`experiments/run_t4_a19_revalidation.sh`（T4/A-19 默认协议复验）、`experiments/smt_witness_batch.py` + `tests/test_smt_witness_batch.py`（T3b/Q7 专项批）、`tests/test_t_round_semantic_fixes.py`（T 轮语义修复回归测试）。

在途批次的当前状态（只读观察，非结果判定）：

- **B2/T1**：`experiments/results/t_round_b2_main_batch_20261018/` 已有 `PREREG.md`、`PREFLIGHT.json`（干净 worktree、quota_probe ok、3 seed×3 臂×87 任务、预算 $6）、`traces_seed42/` 46 个 trace、`RUN_SUMMARY.log` 空（进行中）。
- **B1/T2**：`t_round_b1_protocol_text_20261018/` 有冻结 `PREREG.md`（3 格 C1/C2/C3 × seed 42/44）与 runner；`seed42/seed44/staging` 目录为空（截至审计时刻未开始或刚启动）。该批将直接决定 P0-01 的最终文案。
- **A-19/T4**：`experiments/results/t_round_semantic_fixes_20261018/A19_REVALIDATION_PREREG.md`（脚本引用）——用于补 S-2 的"默认协议"遗留，结算后 P0-02 可彻底关闭。
- **T3b/Q7**：`experiments/smt_witness_batch.py` 计划零 LLM 单臂观测批（50 行/41 缺陷程序口径），结算后可改写 Q7（P1-14）。

最终文档同步建议顺序（避免二次分裂）：

1. 等 T 轮**提交**（工作树干净）后，一次性刷新 `BASELINE.yaml` 的 `last_verified`、`tests`、`coverage`（含逐模块与 rolling watermarks）、`static_checks`（mypy 134、ruff 文件数+全绿）、`feature_matrix`（探针计数与去重结果）、`benchmark`/`target_quality` 新节（B1/B2/T3b/T4 结果）。
2. 同步 `PROJECT_STATUS_REGISTER.md`：抬头日期/轮次、§1 快照、§2 B1/B2/B8 关闭或改述、§4 新登记项标完成、Q7/Q11 更新、`run_preflight` 缺陷与新工件登记。
3. 同步 `VALIDITY.md/.en.md`（RT1/2×2、配额闸、四起→五起）、`EVALUATION_SCOPE.md`（C1b/§4、contradicted 计数）、`OPTIMIZATION_2026-10-15.md`（§3 收口脚注）、`MEASUREMENT_INTEGRITY.md`（如 T 轮新增仪器结论）。
4. 跑一次 `ruff format --check .`、`make preflight`（若不再与 B2 争用）、`checksum_results.py --verify` 于 T 轮新工节目录；把本报告 §1 的 P0/P1 逐条勾销后，T5a 可关闭。

---

## 附录 A：本报告使用的主要命令（均为只读）

```bash
# 覆盖率/门禁
.venv/bin/python scripts/gates/coverage_ratchet.py --check
.venv/bin/python scripts/gates/check_branch_coverage.py coverage.xml
.venv/bin/python scripts/gates/check_json_contract_sites.py --report
.venv/bin/python scripts/gates/check_bilingual_docs.py --strict
.venv/bin/ruff format --check .
.venv/bin/mypy src/ config.py
# 工件完整性
.venv/bin/python scripts/gates/checksum_results.py --verify --results-dir <dir>   # 5+ 目录通过
(cd experiments/results/emse_docstring_anchor_20261017 && shasum -a 256 -c SHA256SUMS)
# 复算（Python 读 JSON/XML，示例）
.venv/bin/python - <<'EOF'
import xml.etree.ElementTree as ET
r=ET.parse('coverage.xml').getroot(); print(r.get('line-rate'), r.get('branch-rate'))
EOF
# 文档/代码对照
grep -n 'probes_total\|mypy_source_files\|last_verified' BASELINE.yaml
grep -rn '未执行\|尚未接入\|待 LLM 配额' docs/VALIDITY.md docs/PROJECT_STATUS_REGISTER.md docs/study/OPTIMIZATION_2026-10-15.md
git log --oneline -S 'patch_rollback_verdict' -- experiments/run_benchmark.py
git diff experiments/run_benchmark.py scripts/tools/run_preflight.py
```

## 附录 B：本报告未触碰的边界

- 未读取 `.env.local` / `.env` 内容；未打印任何密钥。
- 未修改任何既有文件、未 `git add/commit`；唯一写文件为本报告。
- 未运行全量 pytest / `make gates` / 重型跑批；未与后台 B2 批次争用 CPU 做测量。
- 所有引用的行号均为审计时刻实际读到的当前文件（T 轮在途 diff 可能使个别行号在提交后漂移，建议以符号名/func 名复核）。
