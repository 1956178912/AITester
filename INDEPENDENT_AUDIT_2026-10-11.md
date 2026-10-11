# AITester 独立系统性审查报告（2026-10-11）

> **工作目录**：`/Users/wangchenyu/Workspace/AITester`
> **审查时点**：2026-10-11 13:50–14:10（Asia/Shanghai）
> **审查对象**：HEAD `d9e51df` + 工作树（77 项未提交：35 M / 42 ??）
> **本报告性质**：**独立评审**。不采信项目内任何既有评审报告、自评数据、BASELINE 结论数字与前沿引用数值。
>
> **【2026-10-11 补充】真实 LLM 调用测试已完成** → 见 [_independent_audit/LLM_LIVE_TEST_2026-10-11.md](_independent_audit/LLM_LIVE_TEST_2026-10-11.md)。
> 前次审查（含全部既有评审）**未发起任何真实 LLM 调用**。补测结果中最重要的一条：**项目存档的主批次在当前 API 上无法复现**
> —— 同一 87 任务 × 3 seed、同模型名 `deepseek-flash`、同代码路径，`plain_llm` 臂检出率从存档的 **1.5%（4/261）** 变为
> **19.2%（50/261）**，三个 seed 全部同向；同 seed 42/同 87 任务配对对照中 `aitester` 由 14.8% 降至 8.0% 而 `plain_llm` 由 1.1% 升至 13.8%，**配对差由 +13.7pp 反转为 −5.7pp**。**该发现使本文档 §3.2 中 `plain_llm` 基线的 1.5%、以及 −28pp 配对差均不再可直接引用。**

---

## 0. 执行摘要

### 0.1 独立评审声明（最高优先级）

1. **我不采信既有评审。** 本仓库存在至少 6 份既有审查报告（`REVIEW_2026_FRONTIER.md` 195 KB、`EXTERNAL_REVIEW_2026-10-11.md` 471 KB、`FINAL_REVIEW_2026-10-11.md` 161 KB、`INDEPENDENT_REVIEW_2026-10-10.md`、`OPTIMIZATION_PLAN_v2.md`、`audit_2026/T_*.md` 5 份共 297 KB）。**它们在本报告中一律是"待验证对象"**，只用于两件事：①提取"项目声称了什么"；②作为被复核的原结论（§11）。本报告无一条结论转抄自它们。
2. **我不采信前沿二手数据。** 前沿数值仅采信本次亲自访问的一手载体（arXiv abs/全文 HTML、Crossref DOI 注册记录、会议官方 program/proceedings、官方 GitHub、机构官方页）。唯一载体被付费墙/反爬拦截的条目一律降级，不填数值（详见 §4 与 `_independent_audit/WS1_frontier_primary_sources.md` §8 的 D1–D25）。
3. **我独立重算了头条指标。** §3 与 §5 的所有数字，均由本人在原始工件（`experiments/results/**/*.json`、`experiments/results/raw/**`）上重新计算，未使用项目提供的分析脚本输出。重算结果与项目声称**逐位一致**（见 §3.2）——这一点必须先讲清楚：**本报告的批评不是"数字错了"，而是"数字对，但支撑不起项目的核心主张"**。
4. **知识时效声明。** 我的参数化知识对 2025 年中之后、尤其 2026 年的文献不可靠。本报告所有 2025–2026 前沿数值均来自本次联网检索；凡未能取得一手载体的，标注 D 级或不填。
5. **审查能力的已知边界**：IEEE Xplore（HTTP 202 空体）、ACM DL（403 + Cloudflare）、OpenAI 官方页（403）在本次会话中被拦截；Semantic Scholar API 持续 429。因此**若干项目引用的数值我无法独立复核**，这不是"项目造假"的证据，而是"无法验证"的证据。边界清单见 §4.3、§15。

### 0.2 一句话定位（独立判断）

> **AITester 不是"逻辑驱动的多智能体测试生成与自修复系统"。它是一个测量纪律极强、工程化程度异常高的"检出优先（detection-first）零 LLM 测试生成"研究平台——其自称的核心机制（多智能体编排、逻辑驱动闭环）或为负贡献、或未接线；而其全套合成基准与唯一一次真实仓库基准都不能支撑任何对外有效性主张。**

项目 README 头部（`README.md:9-11`）**已主动声明**多智能体降级为"可消融容器"——这一自我修正在学术诚信上是加分项，本报告予以独立确认（§11）。但项目**对外标题、CITATION、任务书描述**仍使用"多智能体测试生成与自修复"表述，与内部证据不同步。

### 0.3 关键发现（每条附本次独立实测证据）

| # | 发现 | 证据（本次独立实测） | 证据等级 |
|---|---|---|---|
| **F1** | **核心主张与实际能力不符：完整系统显著劣于单提示协议，且成本高 5.5 倍。**（⚠️ **2026-10-11 实测更新**：该对比的 `plain_llm` 一侧在当前 API 上已漂移为 19.2%，见 F13） 在项目自己的基准上，`plain_llm_df`（单次 LLM 调用 + 检出优先提示）检出率 **44.8%**，而完整多智能体系统 `aitester` 仅 **15.8%**；aitester 每任务输出 token **20,056** vs df **3,640**（5.5×）、LLM 调用 **4.2** vs **1.0**（3.8×）。 | 我独立重算 `main_batch/benchmark_synthetic_2026100{6,7}*.json` 三批次：38/240 vs 117/261 vs 4/261（§3.2） | **A** |
| **F2** | **该负结论经聚类稳健检验后仍成立，但真实效应比头条小。** 任务级配对 n=240 得 δ=−28.3pp（exact McNemar p=1.7e-13）；**按"唯一程序体"聚类后 n=26**，δ=**−24.6pp**，95% CI **[−33.7, −15.6]**，配对 t=−5.36，符号检验 p=0.0001。 | 我自建聚类分析（§5.3） | **A** |
| **F3** | **基准的外部有效性为零——全部头条数字来自项目自建合成集。** 该集共 **16 个 BUG_PATTERNS**；87 个"任务"去掉行尾 `# noise_seed=` 注释后**只有 26 个不同程序体**（最大重复 9 次）。即"n=87/臂、合并 n=261"的**有效独立单元实为 26 个**，聚类内伪重复使显著性被系统性夸大。 | 我实跑 `SyntheticDataset(task_count=87, seed=42)` 逐任务哈希（§3.4） | **A** |
| **F4** | **唯一一次真实仓库基准（SWE-bench Lite 20 例）全链条失效，且失败在基础设施而非算法。** aitester 臂 20/20 失败，**每一个** task 都记录 `[llm_patch_apply_failed] 补丁未成功应用`，且 `FAIL_TO_PASS baseline` 与 `FAIL_TO_PASS after-llm-patch` **逐任务完全相同**（证明补丁从未生效）。**该系统从未在任何真实仓库任务上成功产生过一个补丁。** | 我逐个解析 `experiments/results/raw/sqlfluff__*/*.json` 的 `repo_verification.output`（§3.3） | **A** |
| **F5** | **"逻辑驱动"名义覆盖率极低。** 全量 aitester 结果行（n=1,607）`spec_compile_rate` 均值 0.320、**中位数 0.2**，**47.6% 的任务为 0**（无任何可编译规约子句），仅 12.2% 任务达到 1.0。 | 我遍历全仓工件统计分布（§3.5） | **A** |
| **F6** | **头条"闭环"未接线。** `README.md:59` 称"逻辑驱动反例精化**闭环**（CEGIR）"，但 `src/specs/spec_refine.py:22-24` 自述"**不接入主链路**"，且 `src/`+`experiments/` 对其**零引用**。项目 `README.md:1376` 自己也写明"未接入主链路"——**同一文档两处互相矛盾**。 | 全仓 grep + 源码自述（§9.2 C1） | **A** |
| **F7** | **覆盖率与变异得分在本基准上已饱和，无鉴别力。** 任务级 line coverage 中位数：aitester **98**、plain_llm **100**、df **98**；**88.1%/98.9%/98.1% 的任务达到 100%**。变异得分 aitester 0.818–0.976 vs df 0.986–0.997。**项目自己也在 `BASELINE.yaml:56` 承认"合成集变异体过弱、该指标鉴别力有限"。** | 我逐任务统计 `details[].coverage` / `mutation_score`（§3.4） | **A** |
| **F8** | **验证 oracle 与生成 oracle 同源，修复正确性从未被独立判定。** 所谓"P2P 全量回归"实为**重跑系统自己生成的单个测试文件**（`src/graph/nodes.py:2044-2049` → `patch_rollback.py:189` 的 `pytest test_path -q`），且 logic 档 `PATCH_ROLLBACK_FAIL_CLOSED=true` 使 rc≥2/超时一律回滚——**测试自身有瑕疵即误杀正确修复**。 | 源码证据链（§9.2 C5/C6） | **A** |
| **F9** | **成本与独立性两条记账支柱在同一批工件内失效。** 4 份 logic 档批次中 `plain_llm`/`plain_llm_df` 的 `token_usage` **全字段为 0**（含 `llm_calls`），而 `generated_test` 非空；另有同 seed=42 的两份批次（git_sha 不同）3 臂 × 87 任务 `generated_test` **逐字节相同**。 | 我逐批次、逐臂统计（§3.6） | **A** |
| **F10** | **引用完整性是真实强项：8 个 DOI/arXiv 标识符零伪造、零张冠李戴。** CANDOR（TOSEM 2026, `10.1145/3803418`）的 0.991/0.970/0.980 与原文表 1 **精确一致**；BOAD 经 IBM Research 官方页确认为 ICLR 2026；Zhao 等为 ISSTA 2026 **Distinguished Paper**。**但有 1 处数值误述**：Konstantinou 论文请求数项目写 11,718/12,264，原文为 **11,815/12,741**。 | 独立联网核实（`WS1` §1，13 条全查） | **A** |
| **F11** | **工程化质量远超同类科研代码，但门禁有真实缺口。** 我独立实跑全量测试：**5390 passed / 3 skipped / 1 xfailed，耗时 200.6s，0 failed**（收集 5394）。但：`check_zero_assert_tests` 报 **2 个零断言用例且退出码 1**（`tests/test_mdo_metrics.py::test_as_dict_is_json_serializable`、`tests/test_path_c_trigger.py::test_as_dict_serializable`）；mypy 门禁真实标注覆盖面仅 **≈75.8%**（src 1111 函数中 842 全标注，`api_manager.py` 仅 6/43）。 | 我实跑 `pytest` + `scripts/gates/*.py`（§8） | **A** |
| **F12** | **文档自身数字漂移，且守卫门禁放行。** `BASELINE.yaml:17` 字段值 `total_passed: 5389`，同字段注释却写"实测 **5323** passed"；我实测 **5390**（WS2 三次独立实测亦为 5390；`5394 = 5390+3+1` 恰好相等）。三者互不相等。守卫 `tests/test_2026_10_10_optimization_batch.py:169-175` 只校验 `declared ≤ collected` 且差额 ≤9，故陈旧 5 个用例仍判绿。另 `suite_seconds: 35` 与实测 71.1s（`-n 4`）/ 200.6s（我串行实测）均不符。 | 实跑 + 逐行核对（§3.7） | **A** |
| **F13** | **【最高优先级】项目存档主批次在当前 API 上不可复现（模型漂移）。** 同一 87 任务 × 3 seed、同命令、同 `AITESTER_PROFILE=logic`、同模型名 `deepseek-flash`，仅隔离 LLM 缓存：`plain_llm` 检出率 **1.5%（4/261）→ 19.2%（50/261）**，三 seed 同向（1.1→13.8 / 1.1→20.7 / 2.3→23.0）。**指标本身稳定**（我把存档 `generated_test` 原文重放，87–100% 精确复现存档值），故差异只能来自 LLM 侧。**推论：当前模型下一次裸 LLM 调用（19.2%）已超过存档中完整系统 aitester 的 15.8%。** 更关键的是**同 seed 42 / 同 87 任务的配对对照**：`aitester` 由存档 14.8% 降至 **8.0%**，`plain_llm` 由 1.1% 升至 **13.8%**，配对差由 **+13.7pp 反转为 -5.7pp**（McNemar p=0.30，不显著）——即**「完整系统优于裸 LLM」这一存档结论在当前模型上已不成立**（谨慎表述：位次不再成立，而非断言漂移导致 aitester 变差）。 | 新增实测（`LLM_LIVE_TEST` §11） | **A** |
| **F14** | **"逻辑驱动"失效根因被定位到提示-文法契约，而非求解器。** 真实调用下 planner 对 3 个函数中的 2 个返回 `logic_degraded=True`（空规约）；唯一成功者产出**自然语言**规约（`"text 为 str 类型"`、`"成功时返回 int 类型结果"`），而编译器白名单只接受形式表达式 → **编译产物恒 0 字节**。log 记录 `SpecIR v2 oracle 产物自检失败，保守丢弃`。**同一批次 25 个 aitester 任务中 19 个 `spec_compile_rate=0`（中位数 0.0）**。z3 求解本身实测完全正确（`r>0 ∧ r<0` → `unsat`）。 | 新增实测（`LLM_LIVE_TEST` §4） | **A** |

### 0.4 数据可信度总览（本次审计口径）

| 类别 | 条目数 | A 级（本次可独立验证） | 无法验证 / D 级 | 备注 |
|---|---|---|---|---|
| 项目性能声明（§3） | 14 项核心 | **11** | 3 | 3 项中 2 项因工件记账缺陷不可算，1 项为口径歧义 |
| **模型快照可复现性** | 1 项（主批次三臂基线） | — | **1（不可复现）** | 同任务同 seed 同模型名，`plain_llm` 由 1.5% 漂移至 19.2%；`provenance` 无可校验版本指纹（F13） |
| 项目引用外部文献（§4.3） | 13 条标识符 | **8** 属实 | **5** | 含 1 处数值误述；最重"负面证据"四个数值不可复核 |
| 前沿 SOTA 数值（§4） | 40+ 数据点 | 见各表等级列 | D1–D25 共 25 项 | 自修复与形式化两方向一手数值最稀薄 |
| 既有评审结论（§11） | 抽样 12 条 | 支持 6 / 部分支持 3 / 推翻 2 / 无法验证 1 | — | 逐条给复核方法 |

### 0.5 竞争位置判定（独立结论）

**项目在 2025–2026 前沿格局中不具备任何可验证的竞争优势。**

三条独立理由：

1. **同口径不可比。** 项目主指标是"fail-to-pass 检出率"。我核实了 TestGenEval（line coverage 35.2%、mutation 18.8%，`WS1` §2b）与 ULT（statement 45.10%、mutation 40.21%，定义经原文逐字核对）的分子分母后确认：**2025–2026 一手前沿基准中没有一份报告 fail-to-pass 检出率**。因此 44.8% 这个数字**在文献中找不到同口径对手**——既不能被证明超越前沿，也不能被证明落后（`WS1` §2b 结论）。
2. **可比的维度上项目无数据且先前实测失败。** 若以覆盖率/变异得分对比，项目仅在合成集上有数（且饱和到 98%/0.98，鉴别力为零）；在真实 Python 代码上**唯一一次尝试是 SWE-bench Lite 0/20，失败于补丁无法应用**（F4）。
3. **项目的"编排"这一差异点被自身数据否定。** 在受控对照下（同模型 `deepseek-flash`、同温度 0.0、同 max_iterations=3、以 seed 为配对），增加编排带来 **−24.6pp**（95% CI [−33.7,−15.6]）与 **5.5× 输出 token**（F1/F2）。这恰好与 ICST 2026 独立复现的结论同向（Plain-LLM 49.95% line 全面优于 HITS/SymPrompt/CoverUp/TestSpark，`WS1` §2）。

**可以主张的窄结论（有证据支撑）**：
- 项目的**测量纪律**（预注册、口径矩阵、ADR、负面结果入库、测量伪影事后更正）达到可发表的工程标准（§8、§11）。
- 项目的**引用完整性**优于多数同类项目（F10）。
- 项目**最早、最系统地**把"高覆盖 ≠ 高检出"落到可测量协议上（`src/measurement/mdo.py` 的 MTR/MDR 分离），与 MUTGEN（TSE 2026："100% coverage 但仅 4% mutation score"）、LM2Alloy（arXiv:2607.18555："68% 分支覆盖但三次运行全漏同一真实缺陷"）的一手发现同向（`WS1` §2/§5b）。**这是项目唯一具备前沿对话资格的资产**（§6 路径 1）。

---

## 1. 工作目录与文件清单

### 1.1 索引方法与规模（本次实测）

递归扫描工作目录，排除 `.git`、`.venv`、`__pycache__`、各类 cache、`build`/`dist`、`node_modules`。

| 项 | 实测值 | 命令 |
|---|---|---|
| 工作目录总大小 | **1.2 GB** | `du -sh .` |
| Git 跟踪文件 | **4,028** | `git ls-files \| wc -l` |
| 未提交变更 | **77**（35 M + 42 ??） | `git status --porcelain` |
| Python 文件总数 | **1,200** | `find . -name '*.py'`（排除缓存/虚拟环境） |
| `src/` Python 行数 | **47,049** | `find src -name '*.py' \| xargs wc -l` |
| `tests/` Python 行数 | **69,365** | 同上 |
| `experiments/` 顶层脚本行数 | **21,559** | 同上 |
| 测试文件数 | **266** | `ls tests/*.py \| wc -l` |
| 实验工件目录 | **154** | `ls experiments/results \| wc -l` |
| ADR 数 | **25** | `ls docs/adr/*.md \| wc -l` |
| 本报告工作树 HEAD | `d9e51df` | `git rev-parse HEAD` |

**观察**：测试代码量（69,365 行）是源码量（47,049 行）的 **1.47 倍**。这一比例在科研代码中极罕见，是项目工程化程度高的客观证据（见 §8）。

### 1.2 关键文件摘要与用途分类

| 文件 / 目录 | 大小 | 用途分类 | 含自评/性能声明？ |
|---|---|---|---|
| `README.md` / `README.en.md` | 130 KB / 115 KB | 说明文档 | **是**（头部 60 行为全部头条声明） |
| `BASELINE.yaml` | 57 KB | 配置（机器可读基线） | **是**（`benchmark` 节为结论性数字） |
| `CHANGELOG.md` / `.en.md` | 398 KB / 411 KB | 变更记录 | 是（历史批次数字） |
| `src/` (124 文件) | 47 K 行 | Python 源码 | 否（实现） |
| `src/measurement/mdo.py` | 19 KB | 测量层（MTR/MDR） | 含设计论断 |
| `src/specs/{spec_ir,spec_ir_v2,spec_smt,spec_refine}.py` | 2,140 行 | 逻辑驱动内核 | 含能力边界自述 |
| `src/graph/{nodes,workflow,debugger,expert_pool}.py` | 4,690 行 | 多智能体编排 | 否 |
| `src/tools/patch_*.py`, `detection_gates.py`, `oracle_validator.py` | — | 自修复/验证链路 | 否 |
| `src/datasets/synthetic_dataset.py` | 89 KB / 2,532 行 | **合成基准生成器（16 模板）** | 是（内含 gold 与 gold 测试） |
| `experiments/run_benchmark.py` | **176 KB / 3,401 行** | 基准主驱动 | 含三臂定义 |
| `experiments/statistical_analysis.py` | 97 KB / 2,026 行 | 统计分析 | 是 |
| `experiments/results/` | — | **实验原始工件（154 目录）** | 部分是（`.md` 摘要） |
| `docs/preregistration.md` + `.en.md` | 42 KB / 48 KB | **预注册文档** | 是 |
| `docs/design/repair_caliber_matrix.md` | — | 口径矩阵 | 是 |
| `scripts/gates/` (24 个) | — | **CI 门禁** | 否 |
| `.github/workflows/{ci,perf,release}.yml` | — | CI/CD | 否 |
| `Dockerfile`, `Dockerfile.repro`, `reproduce.sh`, `Makefile` | — | 可复现性 | 否 |
| **既有评审报告 6+ 份** | **~1.2 MB** | **既有评审（本报告待验证对象）** | **是** |
| `audit_2026/` (5 份 T_*.md) | 297 KB | 既有审计 | **是** |
| `review_2026/` (21 文件) | ~1.0 MB | 既有审计 | **是** |
| `.private/review/` (15 文件) | — | 既有评审（私有不入库） | **是** |

### 1.3 含自评数据 / 既有评审的文件（**全部按"待验证声明"处理**）

以下文件在本报告中**不被采信**，仅用于提取"项目声称了什么"：

- 根目录：`INDEPENDENT_REVIEW_2026-10-10.md`、`REVIEW_2026_FRONTIER.md`、`EXTERNAL_REVIEW_2026-10-11.md`、`FINAL_REVIEW_2026-10-11.md`、`OPTIMIZATION_PLAN_v2.md`
- `audit_2026/`：`T_A_claims_traceability.md`、`T_B_code_domain_audit.md`、`T_C_frontier_primary_sources.md`、`T_D_citation_verification.md`、`T_E_adversarial_verification.md`
- `review_2026/`：`R1_frontier_testgen.md`、`R2_frontier_repair.md`、`R3_frontier_logic.md`、`E2`–`E8` 系列、`LEAD_findings.md`、`REPORT_draft.md`、`T1`–`T4`
- `.private/review/`：15 份（含 5 份 2023–2026 前沿基线综述，**这些是本报告 §4 的重点复核对象**）

### 1.4 缺失 / 不可读文件

| 项 | 状态 | 影响 |
|---|---|---|
| `.env` / `.env.local` | 存在但 gitignored；`git log --all -- .env` **为空 = 从未入库** | 无密钥泄漏；本次未读取内容 |
| `~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl` | **0 字节**（`swe_bench_full/mini/unknown` 亦为 0） | 官方 lite 子集未下载；仅有一个 4.9 MB 的通用 `swe_bench_instances.jsonl`（2026-08-17） |
| SWE-bench 源码 enrichment JSONL | **不存在**（全仓 `find -name '*enrichment*'` 无结果） | 真实仓库任务缺 `instance_code`，这是 F4 的根因之一 |
| 5 份既有审查报告 | 权限 `-rw-------`（仅属主可读） | 本次可读（同用户） |
| `experiments/results/*.md` 摘要 | 部分为 2026-08/09 陈旧快照 | 不作为数据源 |

---

## 2. 项目理解与边界

### 2.1 我对项目目标的理解（基于代码与工件，非文档）

阅读 `src/graph/workflow.py`、`experiments/run_benchmark.py`、`src/datasets/synthetic_dataset.py` 与原始工件后，我对系统实际行为的独立理解是：

**实际执行路径**（`src/graph/workflow.py:40` 的 LangGraph StateGraph）：

```
Planner → Generator → Executor → [Debugger → PatchApplier] × N(≤3) → END
```

三臂对照的实际定义（`experiments/run_benchmark.py:201/217/381`）：

| 臂 | 实际实现 | 声称 | 本次核实 |
|---|---|---|---|
| `aitester` | `build_workflow()` 完整图（planner+debugger，逻辑档 12+ 开关全开） | 完整系统 | ✅ 一致 |
| `plain_llm` | `build_workflow(planner=False, debugger=False)` | "仅一次调用" | ⚠️ **仍是完整 LangGraph 图**，只是 planner/debugger 关闭；同文件 `:226-230` 注释自认"此前 plain_llm 跑的是完整管线" |
| `plain_llm_df` | 同上 + `set_detection_first_thread_override(True)` | 检出优先提示基线 | ✅ 一致，**这是最强的臂** |

**关键边界事实**：三臂**同模型**（`deepseek-flash`）、**同温度**（0.0）、**同 max_iterations**（3）、**同 seed 配对**（`provenance` 实测确认）。**因此 F1 的对比是公平的**——不存在"给 AITester 更多预算/更多轮"的不公平。相反，aitester 是**唯一开满 12+ 逻辑档开关**的臂，仍显著落后。

### 2.2 "逻辑驱动"的真实边界（源码自述，非文档宣称）

`src/specs/spec_smt.py:17-31` 自述能力边界，我逐条核对代码后确认**自述属实**：

- 支持：布尔 / 比较 / `+-*/%` / 常量 / 名称；前件 SAT 见证、数值目标 optimize、前件 UNSAT（空洞化）检测、后件自一致性 UNSAT 检测。
- **不支持**：函数调用（`len()` 等）、幂、下标、属性访问 → 整体保守跳过返回 `[]`。
- z3 真实存在（实测 **z3 5.1.0** 已安装），SMT 层是真调用求解器，不是轻量仿制。**这是"逻辑驱动"主张中最扎实的一块。**

但**规约本身由 LLM 从自然语言生成**，再经白名单 AST 编译。实测结果见 F5：**47.6% 的任务产不出任何可编译子句，中位数 0.2**。因此"逻辑驱动"当前的真实形态是：**一个对约半数任务完全不生效、对另一半产出一两条一阶约束的可选增强通道**。

### 2.3 关键假设的红队审查

| 假设 | 红队反例 / 反证 | 判定 |
|---|---|---|
| "系统是逻辑驱动的" | 规约由 LLM 生成（非形式化推导）；47.6% 任务零可编译子句；CEGIR 闭环未接线 | **不成立（当前形态）** |
| "多智能体编排带来增益" | 受控配对 δ=**−24.6pp**，CI [−33.7,−15.6]；成本 5.5× | **被自身数据推翻** |
| "自修复能力存在" | 主批次三臂 repair 全为 **0.0**；项目改称 39.31% 来自**存量重放**而非当次运行；近半年**无任何新批次**；真实仓库上补丁从未成功应用 | **部分成立但无当次证据** |
| "合成基准可代表真实能力" | 16 模板 / 87 标签 / **26 唯一程序体**；coverage 与 mutation 双饱和；bug、gold、oracle 同源编写 | **不成立** |
| "闭环收敛" | 停止条件是 `MAX_ITERATIONS=3` 固定上限（`provenance` 实测），非收敛判据；`avg_iterations`：aitester 1.10 / df 0.00 | **无收敛证据** |
| "测试生成质量可独立于修复策略度量" | **该假设被项目自己识别并纠正**：`src/measurement/mdo.py` 明确指出 `detection_rate` 与修复策略数学耦合（补丁改绿→detection 归零） | **项目已自纠，本次确认** |

---

## 3. 项目数据独立审计

> **方法声明**：本章所有数字由本人在原始工件上重新计算（读取 `experiments/results/**/*.json` 的 `results.<arm>.details[]`），**未调用项目提供的任何分析脚本**。脚本与逐项对比见 `_independent_audit/ws2_recompute.py` / `WS2_recompute_results.md`（并行重算）与本节表格（Lead 重算）。

### 3.1 数据 schema 说明（我实际看到的字段）

主批次工件顶层键：`timestamp, dataset, subset, seed, total_tasks, baselines, enable_planner, enable_debugger, enable_rag, parallelism, valid_apis, environment, p2p_gate_enabled, p2p_gate_threshold, results, provenance`

`results.<arm>` 结构：`{total_functions, passed_count, failure_count, success_rate, harness_invalid_count, effective_total, effective_success_rate, avg_coverage, avg_iterations, avg_elapsed_seconds, total_time, failure_category_distribution, token_metrics, rag_metrics, details[]}`

`details[]` 每行关键字段：`detection_rate, repair_rate, false_fix_rate, coverage, iterations, token_usage{input_tokens,output_tokens,total_tokens,llm_calls,by_model}, generated_test, patch, test_passed, spec_compile_rate, ...`

**`provenance` 实测**：`git_sha=b533cff1...`、`git_dirty=true`、`model_name=deepseek-flash`、`temperature=0.0`、`max_iterations=3`、`seed∈{42,43,44}`、`env_snapshot{MAX_ITERATIONS:"3", ENABLE_PLANNER:"true", ENABLE_DEBUGGER:"true", ENABLE_RAG:"false", LOGIC_SPEC_STRICT_ENABLE:"true", ...}`。

### 3.2 核心指标重算表

数据源：`experiments/results/main_batch/benchmark_synthetic_20261006_140906.json`（seed 42）、`_151907.json`（seed 43）、`_164357.json`（seed 44），各 87 任务 × 3 臂。

| # | 指标 | 项目声称值 | **我重算值** | 一致？ | 差异原因 | 证据 |
|---|---|---|---|---|---|---|
| 1 | detection `aitester` | 15.8% | **38/240 = 15.8%** | ✅ **逐位一致** | — | 三批次 `details[].detection_rate`；21 行 None 不进分母 |
| 2 | detection `plain_llm_df` | 44.8% | **117/261 = 44.8%** | ✅ 逐位一致 | — | 同上 |
| 3 | detection `plain_llm` | 1.5% | **4/261 = 1.5%**（存档复算一致）**⚠️ 但当前 API 新跑为 19.2%（50/261）** —— 见 [LLM 实测报告 §11](_independent_audit/LLM_LIVE_TEST_2026-10-11.md) | ✅ 存档一致 / ❌ **当前不可复现** | **模型漂移**：同模型名 `deepseek-flash` 下产出显著不同，`provenance` 未记录可校验版本指纹 | 同上 + 实测 §11 |
| 4 | repair（三臂，当次运行） | 0.000（伪影口径） | **0/240、0/261、0/261 = 0.0%** | ✅ 一致 | — | 同上 |
| 4b | **repair（修正口径，离线存量重放）** | 39.31%（57/145） | **39.31%（57/145）** —— WS2 以**自写 normalizer + 自写 pytest runner、零复用项目函数**独立重放，逐位一致；行级分布 `{skipped 8, no_patch 395, wrong_patch 151, correct 115}` 亦逐位一致 | ✅ **独立成立** | 无（项目归因经反事实证实：退回单文件口径恰得 52/145 = 35.86%，差 +5 行确由跨文件物化贡献） | WS2 §2.2 |
| 5 | `false_fix_rate` aitester | 87.2%（修正口径） | 逐行字段 **143/240 = 59.6%**；修正口径 **87.16%（380/436，跨 10 文件代际）**，**但仅取主批次三文件为 76.92%（110/143）** | ⚠️ **口径歧义** | README:56 把"主批次"与"全 main_batch 目录"混称 | WS2 §2.3 |
| 6 | `false_fix_rate` plain_llm_df | （未单列） | **7/261 = 2.7%** | — | **关键**：df 的假修复率最低，与其最高检出率一致 | 重算新增 |
| 7 | `false_fix_rate` plain_llm | 历史批 89.8% | **229/261 = 87.7%**；历史批（10-01 n=50）逐行字段实为 **90.0%（45/50）**，89.8% 仅在"分子取 passed 行、分母取 detection 可测行"的**不匹配筛选**下成立 | ⚠️ **口径错配** | 项目未披露该筛选规则 | WS2 §2.3 |
| 8 | target line coverage | aitester [84.0, 93.6] | 任务级 **min 0 / p25 93 / med 98 / max 100**，**88.1% 任务=100%** | ⚠️ **口径不同** | 项目区间是**批次均值**；任务级分布远比区间宽且高度饱和 | 重算见 §3.4 |
| 9 | coverage plain_llm | [86.0, 97.2] | med **100**，98.9% 任务=100% | ⚠️ 同上 | 同上 | 重算 |
| 10 | mutation_score aitester | [0.818, 0.976] | 区间同量级 | ✅ | 项目自认"鉴别力有限" | `BASELINE.yaml:56` |
| 11 | $/task aitester | 0.0259 | **0.0259** | ✅ **逐位一致** | 由 price_table.json 复算 | 见 §3.6 |
| 12 | $/task plain_llm | 0.0034 | **0.0034** | ✅ 逐位一致 | — | 同上 |
| 13 | $/task plain_llm_df | 0.0045 | **0.0045** | ✅ 逐位一致 | — | 同上 |
| 14 | tests `total_passed` | 5389（同字段注释写 5323） | **5390 passed / 3 skipped / 1 xfailed（收集 5394）** | ❌ **文档漂移** | 字段值与注释值互不相等，且均与我实测不符 | §3.7 |

**结论**：**项目头条数字的可计算性极高**——14 项中 9 项逐位一致或完全同量级。**这排除了"数字造假"假设**。问题不在数字，在数字**能支撑什么**。

### 3.3 外部有效性：唯一一次真实仓库基准（**最重要的一节**）

项目在 `README.md:56` 诚实披露"SWE-bench Lite（sqlfluff-20）真实基准 **0/20** 负结果"。我独立追查到**两代工件**，结论比"0/20"更严重：

**工件 A**：`experiments/results/swe_bench_lite_20/benchmark_swe_bench_20260818_113525.json`（2026-08-18，n=20，仅 aitester 臂）
- `passed=0/20`、`avg_coverage=0.0`、`error_category ∈ {syntax: 19, timeout: 1}`、`iterations=2`（每任务）
- `provenance=null`、`environment=null`、`repo="unknown"`（**无环境快照、无 git_sha**）
- 根因：`~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl` **为 0 字节**，且**全仓无 enrichment JSONL** → `dataset_loader.py:626` 的 `instance_code = data.get("instance_code") or ... or problem_statement` 兜底为 **issue 文本** → 19/20 任务拿到的是自然语言文本而非 Python 源码 → 必然 `SyntaxError`（诊断字段逐条确认，如"第 5 行无效 decimal literal…这是一段描述性的文本，不应该出现在 Python 代码文件中"）。

**工件 B（更关键）**：`experiments/results/raw/sqlfluff__*/{aitester,plain_llm,single_agent}.json`（2026-09-25，17 任务 × 3 臂）
- 这**是真实执行**：`generated_test` 非空、`coverage` 有非零值（aitester 21.0 / 93.0 / 18.0）、`token_usage` 非零、有 `repo_verification` 字段。
- **`aitester` 臂：无一个任务通过。** 逐任务 `repo_verification.output`：

| Task | FAIL_TO_PASS baseline | FAIL_TO_PASS after-llm-patch | 判定 |
|---|---|---|---|
| sqlfluff-1625 | 0/1 | **0/1（完全相同）** | `llm_patch_apply_failed` |
| sqlfluff-2326 | 0/51 | **0/51（完全相同）** | `llm_patch_apply_failed` |
| sqlfluff-2336 | 14/14 | **14/14（完全相同）** | `llm_patch_apply_failed` |
| sqlfluff-2849 | 0/18 | **0/18（完全相同）** | `llm_patch_apply_failed` |
| sqlfluff-2862 | 0/3 | **0/3（完全相同）** | `llm_patch_apply_failed` |
| sqlfluff-3436 | 0/2 | **0/2（完全相同）** | `llm_patch_apply_failed` |
| sqlfluff-3608 | 0/50 | **0/50（完全相同）** | `llm_patch_apply_failed` |
| sqlfluff-3700 | 0/4 | **0/4（完全相同）** | `llm_patch_apply_failed` |
| sqlfluff-3904 | 82/117 | **82/117（完全相同）** | `llm_patch_apply_failed` |
| sqlfluff-5074 | 0/7 | **0/7（完全相同）** | `llm_patch_apply_failed` |

**独立判定（A 级证据）**：
1. **"before" 与 "after" 逐任务完全相同**，是"补丁从未生效"的直接证据（若补丁生效，至少有一个任务的 F2P 计数应变化）。
2. 每一条都显式带 `[llm_patch_apply_failed] 补丁未成功应用` 标记——**这是系统自报的基础设施失败，而非能力不足的判定**。
3. 补充观察：部分任务的 `FAIL_TO_PASS baseline` 本身就非零（2336 为 14/14、3904 为 82/117），说明这些用例在缺陷代码上**本就通过**，其 F2P 标注与实测环境不一致（环境/依赖不完整）。
4. `plain_llm` 臂在 sqlfluff-3904 上 `test_passed=True`、`single_agent` 在 sqlfluff-905 上 `test_passed=True`，而 **aitester 臂 0 通过**。

> **结论（本报告最重要的单一发现）**：**AITester 从未在任何真实仓库任务上成功应用过一个补丁。** 因此项目对外**没有任何真实代码上的功效证据**；全部头条数字建立在一个 16 模板的自建合成集上（§3.4）。这不是"结果不好"，而是"该实验尚未具备产出有效结果的条件"。

### 3.4 基准构造审计：有效独立样本量

我实跑项目自己的生成器：

```python
SyntheticDataset(task_count=87, seed=42)   # 实测输出
```

| 事实 | 实测值 | 证据 |
|---|---|---|
| `BUG_PATTERNS` 模板数 | **16** | `src/datasets/synthetic_dataset.py:36-56`，实跑 `len(BUG_PATTERNS)=16` |
| 生成任务数 | 87 | `len(list(ds))` |
| **去掉 `# noise_seed=` 注释后的唯一程序体数** | **26** | 逐任务 `sha256(re.sub(r'#.*','',instance_code).strip())` |
| 重复度分布 | 最大重复 **9 次**，另有 7 次、6 次、5 次 | `Counter` 实测 |
| `(程序体, 函数名)` 唯一簇 | **26** | 同上 |
| 任务 ID 形如 | `synthetic__task_0000`，`target_function=None` | 实跑 |

**噪声形式**：`src/datasets/synthetic_dataset.py:2401,2482` 注入的是**行尾注释** `# noise_seed=4386`——即"不同任务"之间**代码语义完全相同**。

**该项对统计的影响（我独立计算，§5.3）**：把 87 个标签当作 87 个独立样本，会把有效样本量夸大 **3.35 倍**。聚类到 26 个唯一程序体后，δ 从 −28.3pp 收窄到 **−24.6pp**，95% CI 从 [−33.7,−15.6] 加宽到同样的 26 簇基础——**结论方向不变（仍显著负向），但精确度被严重高估**。

**覆盖率/变异得分饱和（同一次实测）**：

| 臂 | coverage p25 | median | 100% 任务占比 | 说明 |
|---|---|---|---|---|
| aitester | 93 | **98** | 88.1% | — |
| plain_llm | 100 | **100** | 98.9% | 基线即满覆盖 |
| plain_llm_df | 91 | **98** | 98.1% | — |

**判定**：`plain_llm`（无编排、无修复、近乎一次调用）即达 **98.9% 任务满覆盖**——**该指标在此基准上完全无鉴别力**。这与项目自己的 `BASELINE.yaml:56` 注释一致（"合成集变异体过弱、鉴别力有限"）。**因此任何以"覆盖率 84–94%"作为系统能力的陈述都缺乏实证基础。**

### 3.5 "逻辑驱动"内核的实测覆盖率

遍历全仓工件（跨全部批次），`aitester` 臂含 `spec_compile_rate` 字段的结果行 **n=1,607**：

| 统计量 | 实测值 |
|---|---|
| 均值 | **0.320** |
| **中位数** | **0.200** |
| **恰好 0.0（零可编译子句）** | **765 行 = 47.6%** |
| 恰好 1.0（全部子句可编译） | 196 行 = 12.2% |
| 落在 (0,1) 开区间 | 40.2% |
| 常见离散取值 | 0.0(765) / 1.0(196) / 0.5(146) / 0.333(125) / 0.75(62) |

**判定**：项目声称 `spec_compile_rate` 区间 [0.205, 0.219]（`BASELINE.yaml:66`）为"逻辑驱动首次有非零实证"。**独立核实结论**：
- 该区间**确实来自真实数据**（我重算得同量级批次均值）；
- 但**全量口径下 47.6% 的任务完全产不出可编译规约**，中位数仅 0.2；
- 因此"逻辑驱动"当前的真实形态是**对约半数任务空转的可选通道**，不足以支撑系统的第一性命名。

### 3.6 记账与可复现性缺陷（影响成本与独立性结论）

**(a) token 记账在某批次内整臂为零**

逐批次、逐臂统计 `token_usage` 非零行数：

| 批次 | aitester | plain_llm | plain_llm_df |
|---|---|---|---|
| 20261006_140906 (s42) | 87 非零 | 87 非零 | 74 非零 / **8 缺失** |
| 20261006_151907 (s43) | 87 非零 | 87 非零 | 74 非零 / **13 缺失** |
| 20261006_164357 (s44) | 87 非零 | 87 非零 | 73 非零 / **14 缺失** |
| 20261007_161053 (s42) | 87 非零 | **87 全零** | **87 全零** |
| 20261007_170147 (s44) | 87 非零 | **87 全零** | **87 全零** |
| 20261007_181638 (s42) | 27 非零 / **60 全零** | **87 全零** | **87 全零** |
| 20261007_185941 (s44) | 26 非零 / **61 全零** | **87 全零** | **87 全零** |

**影响**：4 份批次的**成本结论不可计算**（分母为零）；2026-10-07 之后 aitester 臂也开始大面积零记账 → **该时间点之后的成本对比全部失效**。这与我复算的头条成本（§3.2 #11–13，来自 2026-10-06 三批次）恰好说明：**成本数字在我使用的批次上成立，但在项目后期批次上不成立**——引用成本必须绑定批次。

**(b) 同 seed 重放产出逐字节相同的结果**

我逐任务比对 `generated_test` 的 SHA256：

| 配对 | 臂 | 任务数 | 逐字节相同 |
|---|---|---|---|
| `20261007_161053` (s42) vs `20261007_181638` (s42) | aitester / plain_llm / df | 87 各 | **87 / 87 / 87 = 100%** |
| `20261007_170147` (s44) vs `20261007_185941` (s44) | aitester / plain_llm / df | 87 各 | **87 / 87 / 87 = 100%** |

两份批次的 `git_sha` 不同（`d3c3cc4e` vs `1a5a5a79`），却产出**完全相同**的测试代码——**说明 LLM 响应缓存命中，代码变更未生效**。

**(c) 但头条三批次（`b533cff1`，seed 42/43/44）是真正独立的**

我做了同样的比对：跨 seed 的 `generated_test` **逐字节相同数 = 0/87（0.0%）**，任务 ID 集合交集 = 87/87。

**簇内一致性检验**（同一任务在不同 seed 下的 detection 判定是否一致）：

| 臂 | 判定一致的任务数 | 占比 |
|---|---|---|
| aitester | 38/67 | **56.7%** |
| plain_llm | 83/87 | **95.4%** |
| plain_llm_df | 29/87 | **33.3%** |

**判定**：**我推翻了"n=261 是伪造重复"的怀疑**——三批次确实是三次独立采样（0% 逐字节相同）。但发现的**新问题是**：两臂（aitester、df）的**簇内一致性仅 33–57%**，即同一任务换个 seed，检出判定会翻转。这说明：**44.8% 与 15.8% 这两个点估计的稳定性远低于 n=261 所暗示的水平**（分 seed 波动：df 41.4–49.4%，aitester 13.8–19.0%，见 §5.3）。

### 3.7 测试与静态检查独立实测

| 项 | 项目声称 | **我实测** | 一致？ |
|---|---|---|---|
| 测试收集数 | — | **5394 collected** | — |
| 测试通过 | `total_passed: 5389`（注释写 5323） | **5390 passed + 3 skipped + 1 xfailed，0 failed，200.6s** | ❌ **三值互不相等** |
| 零断言用例门禁 | 未提及 | `check_zero_assert_tests` **exit 1，2 个违规用例** | ❌ **门禁红** |
| 引用真实性门禁 | "CI 阻断" | `check_citations` 默认模式**只打印清单（离线），exit 0**；`--online` 才核验 | ⚠️ 默认不阻断 |
| 工件入库门禁 | — | `check_artifacts_tracked`：**21/21 通过，exit 0** | ✅ |
| SHA256SUMS 完整性 | — | 抽样 **20/20 校验通过**；2029 条中含 **2 条指向未跟踪的 `.mimosa/`** | ✅（2 条为小瑕疵） |
| 双语文档门禁 | — | `check_bilingual_docs` 通过（0 警告 / 0 失败） | ✅ |
| env 预算门禁 | 170→172→183 | 183 个环境变量，登记 183，**通过** | ✅ |
| baseline 数字漂移门禁 | — | `check_baseline_numbers` 通过（"当前基线块零硬编码"） | ✅ |

**注意**：`check_zero_assert_tests` 是**真实红**（exit 1），但 `pytest` 全绿——说明"全绿"与"门禁全绿"不是一回事。

### 3.8 无法验证 / 不可用声明清单

| # | 声明 | 为何无法验证 | 对结论的影响 |
|---|---|---|---|
| U1 | repair 39.31%（57/145） | **数字本身已被独立重放证实成立**（§3.2 #4b）。**但两项保留意见**：① 它是**离线存量重放**，不是当次运行——主批次三臂 repair 实测全 0，近半年无任何携带非零 repair 的新批次；② **该数字没有机器可读输出工件**，只存在于 `experiments/results/main_batch/corrected_report_v2.md` 文本与脚本 stdout，且复算依赖仓库代码保持当前状态（脚本含 2026-10-11 新增的早退逻辑，属**修复后**代码，历史工件不会再现该值） | 可主张"历史工件的离线重放结果为 39.31%（已被第三方独立重放证实）"；**不可主张"系统当前具备 39.31% 的自修复能力"**（无当次证据 + 无机器可读产物） |
| U2 | E1/E2 logic 档 54.72%（58/106） | 同上（WS2 亦逐位复现）；且该档批次 token 记账为零（§3.6a） | 同上 |
| U3 | `fl_at_k` / `localization_hit_function` 定位质量 | 项目自述曾因漏配恒为空（`config.py:106-112` 注释）；本次未在头条批次验证 | 定位能力无可引用数字 |
| U4 | IEEE Xplore 11655121 的四个 mutation 值（88.35/35.92/69.90/45.63） | IEEE HTTP 202 空体、ACM 403、S2 429 —— **本次无法取得一手载体** | 项目"最强不利证据"降为**不可复核**（存在性 B 级） |
| U5 | SWE-bench Verified 2026-02-23 官方弃用日期 | openai.com 返回 403 | 不能作为基准选型依据 |
| U6 | `mutation_score` 作为测试强度证据 | 合成集饱和（df 0.986–0.997）；项目自认鉴别力有限 | 不得作为强度证据 |
| U7 | 真实仓库任务上的任何修复/检出指标 | 补丁从未成功应用（§3.3）；enrichment 缺失 | **项目当前无外部有效性证据** |

---

## 4. 2025–2026 前沿基线表（独立重建）

> **重建方法与纪律**（完整版见 `_independent_audit/WS1_frontier_primary_sources.md`）：
> - 每一条数值均来自本次亲自访问的一手载体（arXiv abs/全文 HTML、Crossref REST API、会议官方 program/proceedings 页、机构官方页）。**零记忆取数**。
> - **不采信**项目内 `review_2026/`、`audit_2026/`、5 份根目录审查报告、`.private/` 中的任何前沿数据；它们只用于提取"项目声称了什么"。
> - 唯一载体被拦截（IEEE 202 / ACM 403 / OpenAI 403 / S2 429）的条目**不填数值**，一律进 §4.4 的 D 级清单。
> - 证据等级：**A** 一手可验证可追溯；**B** 一手但不可完全验证（仅摘要级）；**C** 二手；**D** 无法定位一手来源。

### 4.1 测试生成子方向

| 系统 | 论文（年份 · venue / ID） | 关键指标（我核实的值） | 评测基准与条件 | 证据等级 |
|---|---|---|---|---|
| **CoverUp** | Pizzorno & Berger, FSE 2025, DOI `10.1145/3729398`, arXiv:2403.16218 | **overall line+branch 90%** vs MuTAP 77%；**per-module median 80%** vs CodaMosa 47%；迭代覆盖引导贡献近 40% 成功 | 挑战性 Python 开源项目 | **A** |
| **TestSpark** | Sapozhnikov et al., ICSE-Companion 2024, pp.30–34 | 自报值未取得（**D**）；**独立复现值 line/branch/mutation = 23.65/16.48/13.88%**（四工具中最差） | IntelliJ 插件；EvoSuite 或 LLM 模式 | 自报 **D** / 复现 **A** |
| **HITS** | arXiv:2408.11324（ICSE 2025 系） | 复现值 **42.43/29.49/27.97%**；成本最高 **16,735 requests** | Java；方法切片+CoT | **A**（复现值） |
| **SymPrompt** | ICSE 2024 / PACMSE, DOI `10.1145/3643769`, arXiv:2402.00097 | 复现值 **40.95/27.19/28.40%**；成本最低 **5,602 requests** | Java；静态分析识别可行路径 | **A** |
| **MUTGEN** | Wang, Xu, Briand, Liu, **IEEE TSE 52(5):1657–1671, 2026**, DOI `10.1109/tse.2026.3682975`, arXiv:2506.02954 | 核心论断：**"部分测试套件达到 100% 覆盖率但变异得分仅 4%"**；mutation 上显著优于 EvoSuite 与 vanilla prompt | 204 subjects / 两个基准 | **A** |
| **CANDOR** | Xu, Wang, Briand, Liu, **TOSEM 2026**, DOI `10.1145/3803418`, arXiv:2506.02943 | HumanEvalJava **0.991 / 0.970 / 0.980**（line/branch/mutation）；LeetCode-Medium 0.990/0.949/0.939；Hard 0.989/0.980/0.937；领先 LLM-Empirical **15.8–25.1pp** | Java；Llama 3.1 70B + DeepSeek-R1-distill-70B；3 次重复；Wilcoxon + A12 | **A** |
| **TestAgent** | Shang et al., **FSE Companion '26** pp.242–246, DOI `10.1145/3803437.3806428` | line **92.34%**；检出 **154 个真实缺陷**，precision **92.22%**；**摘要中不含 mutation 值** | 6 个 Java 项目 / 1,451 methods；三智能体 + 仓库级知识图谱 | **A/B**（摘要级） |
| **Konstantinou 复现** | **ICST 2026**, arXiv:2601.09695v2 | **Plain-LLM 49.95 / 35.33 / 33.82 全面优于 HITS/SymPrompt/CoverUp/TestSpark**；请求数 **11,815 vs CoverUp 12,741**；**~20% 生成测试不编译、~43% 不通过** | **6 个完整 Java 仓库 / 393 类 / 3,657 方法**；Mann-Whitney U p<0.05；按模型 cutoff 区分 seen/unseen | **A** |
| **TestGenEval** | Jain, Synnaeve, Rozière, **ICLR 2025**, arXiv:2410.00752 | **GPT-4o line coverage 35.2% / mutation 18.8%**（All-Pass@1 7.5%、Any-Pass@1 64.0%） | **11 个 Python 仓库 / 1,210 code-test pairs**；文件级；仅统计通过的测试 | **A** |
| **ULT (UnLeakedTestbench)** | Huang, Zhang, Harman, Zhang, Du, Ng, **TOSEM 2026**, DOI `10.1145/3805043` | **statement 45.10% / branch 30.22% / mutation 40.21%**；对照 TestEval 92.18/82.04/49.69、PLT 55.13/40.07/50.80 | **3,909 个真实世界 Python 函数任务**；12 个 SOTA LLM；抗污染筛选 | **A** |
| **SWT-Bench** | Mündler, Müller, He, Vechev, **NeurIPS 2024**, DOI `52202/079017-2601` | **Code Agent 在测试生成上超过专用测试系统**；生成测试使 **SWE-Agent precision 翻倍** | 真实 GitHub issue + golden tests | **A** |

**§4.1 要点（三条）**：
1. **"覆盖率饱和"是真实趋势，但仅限方法级/小型程序。** CANDOR 0.991 line（HumanEvalJava）、TestAgent 92.34%（Java 仓库）↔ 而在**真实世界 Python 函数**上 ULT 仅 45.10% statement、TestGenEval 上 GPT-4o 仅 35.2%。**同一"覆盖率"名词下相差 2.8 倍。**
2. **同一系统在不同评测下可差 3 倍**（CoverUp：自报 90% ↔ 独立复现 38.85% line）。这是本项目"不轻信单一来源"纪律的最强外部支持。
3. **"工具特定编排 vs 强 LLM 单提示"的负面结论有两份独立一手来源**（ICST 2026 复现可直接复核；IEEE 11655121 存在但数值本次不可复核，见 §4.4 D1）。

### 4.2 多智能体、自修复与逻辑驱动子方向

**(a) 多智能体修复 / 编排**

| 系统 | venue / ID | 我核实的内容 | 等级 |
|---|---|---|---|
| **BOAD** | **ICLR 2026**, arXiv:2512.23631 | 多臂老虎机**自动搜索**层级 orchestrator；SWE-bench-Verified 优于单智能体与手工多智能体；SWE-bench-Live 36B 系统榜第 2。经 **IBM Research 官方页**确认 ICLR 2026 Poster | **A** |
| **FTDI** | **Expert Systems with Applications**, DOI `10.1016/j.eswa.2026.134164` | 预算感知自修复：故障注入下 HumanEval Pass@1 **63.41%**（Resilience 99.05%、RecoveryRatio 95.65%）；MBPP Pass@1 **46.84%**（RecoveryRatio 115.75%） | **A** |
| **AgentCoder / RepoUnderstander** | arXiv:2312.13010 / arXiv:2406.01422 | 仅确认载体存在，**未取得一手数值** | **B**（存在性） |
| LANTERN / TraceCoder / AgentRepair / UTgen | — | **未能定位任何一手来源** | **D** |

**(b) 自修复 / 运行时反思 —— 本次最稀薄的方向**

| 系统 | venue / ID | 我核实的内容 | 等级 |
|---|---|---|---|
| **VIGIL** | arXiv:2512.07094（v1 2025-12-08） | 真实存在。机制完整（行为日志→结构化情绪表示→EmoBank 衰减策略→RBT 诊断→guarded prompt 更新 + 只读代码提案；state-gated pipeline）。**摘要中无任何定量延迟/MTTR 数值**；评估仅是一个 reminder-latency 案例研究 | 机制 **A** / 数值 **D** |
| **MTTR-A** | arXiv:2511.20663（v5 2025-12-26） | 提出 MTTR-A / MTBF / NRR **指标定义**（含理论界）。**是度量论文，不报 SRE 实测数字** | **A**（指标定义） |
| 云原生 LLM RCA/修复 | **AISNS 2025**, DOI `10.1145/3797161.3797213` | 存在性确认；**venue 为小型会议**，与 TOSEM/ISSTA 不在同一证据层级 | **A**（存在性）/ 数值未取 |
| `agent-sandbox-runtime` | — | **未定位任何一手来源**（疑似自造名称） | **D** |

> **重要否定性发现**：**"detection latency = X ms"、"MTTR 降低 Y%" 这类表述，在 2025–2026 可查一手文献中普遍不存在。** 任何以该类数字支撑"自修复超越前沿"的主张，本次检索范围内**均无法被一手来源支撑**。项目任务书点名的 VIGIL 即典型（机制有、数值无）。

**(c) 逻辑 / 形式化驱动**

| 方向 | 文献 | 我核实的内容 | 等级 |
|---|---|---|---|
| **TOGLL** | **ICSE 2025** pp.1475–1487, DOI `10.1109/ICSE55347.2025.00098` | **3.8× 正确断言、4.9× 异常预言；1,023 个 EvoSuite 检测不到的唯一缺陷（TOGA 的 10 倍）** | **A** |
| **LM2Alloy** | arXiv:2607.18555 | **直接 LLM 基线拿到 68% 分支覆盖，却三次运行全部漏掉真实缺陷**（Flipper 静默接受重名 flag）。⚠️ 9 KB 探索性预印本、无 venue、仅 2 个库 | **A**（弱载体） |
| **PGS** | arXiv:2506.18315 | 属性导向反馈：+13.4% pass@1、>64% fix rate | **A** |
| **KLEE** | USENIX OSDI 2008 | 符号执行测试生成奠基引用，官方全文页可访问 | **A** |
| SpecIR / SMT 驱动测试生成 | — | **未能定位任何一手来源** | **D** |
| ESBMC-AI | — | 仅命中 ESBMC survey，无 ESBMC-AI | **D** |
| 组合测试 / Alloy / 神经符号预言（2025–2026 一手） | — | 本轮未取得同质量一手证据（预算耗尽） | **未评估** |

**关键结构发现（对项目"逻辑驱动"定位有直接后果）**：项目实际采用的 **属性推断 / Hypothesis 路线在 2025–2026 一手学术文献中无实质载体**（唯一定向命中的 Zenodo 记录全部沉积文件仅 794 字节）；而该方向**最活跃、最可对话的前沿是 Alloy / 形式化规约路线（LM2Alloy、TOGLL）**。项目当前的技术选型与前沿活跃区**不重合**。

### 4.3 项目引用的独立核实（13 条标识符全查）

| 结论 | 数量 | 明细 |
|---|---|---|
| **属实**（标识符+作者+venue+数值均与一手源一致） | **8** | CANDOR（数值精确匹配原文表 1）、ULT（45.10/40.21 映射正确）、MUTGEN（DOI 卷期页码正确）、Zhao/Zhou/Cohen（**ISSTA 2026 Distinguished Paper**）、BOAD（IBM 官方页确认 ICLR 2026）、CoverUp（FSE 2025）、TestGenEval（ICLR 2025）、SWT-Bench（NeurIPS 2024） |
| **数值或出处被误述** | **1（纯数值）+ 4（口径问题）** | 见下 |
| **无法定位一手来源** | **5** | IEEE 11655121 的四个 mutation 值；TestAgent 的两个 mutation 值；Zhao 的 r=0.780；SWE-bench Verified 弃用日期；agent-sandbox-runtime |

**唯一硬伤（数值误述）**：`README.md:28` 写"请求数不高于 CoverUp（**11,718 vs 12,264**）"，arXiv:2601.09695v2 原文为 **11,815 vs 12,741**。定性结论（Plain-LLM 请求数低于 CoverUp）**成立**。疑似引用 v1 稿（我未取得 v1，标注为**推测 E 级**）。

**4 处口径问题（非数值错误，但影响证据强度）**：
1. **IEEE 11655121（项目最重的"不利证据"）四个数值本次无法从任何公开可及一手源确认**（D 级）。建议改以**可复核的 ICST 2026 复现**作主负面证据——论点强度不降反升。
2. **TestAgent 的 mutation 值项目内自相冲突**：`README.md:24` 写 **83.69%**，`BASELINE.yaml:50-51` 写 **55.4%**；**两者我都无法核实**（摘要中不存在该值）。建议删除 mutation 断言，仅保留已核实的 line 92.34% + precision 92.22% + 154 bugs。
3. **CANDOR 的 branch 优势统计不显著**：原文明确"none of the differences between CANDOR and EvoSuite are statistically significant"（branch），且 LeetCode-Medium 上 EvoSuite 反超。项目未披露该限定。
4. **TestAgent 是 5 页 Companion 短文**，与 CANDOR（TOSEM 全文）证据权重不对等；项目并列呈现时未区分。

> **正向结论（必须写明）**：项目所列 **8 个 DOI/arXiv 标识符零伪造、零张冠李戴**。这在高产出科研项目中**显著优于平均水平**，应作为可信度加分项。

### 4.4 无法定位一手来源的 D 级清单（摘要，完整 25 项见 WS1 §8）

| # | 条目 | 拦截/失败原因 |
|---|---|---|
| D1 | IEEE 11655121 的 88.35 / 35.92 / 69.90 / 45.63 | IEEE HTTP 202 空体、ACM 403、S2 连续 429 |
| D2/D3 | TestAgent mutation 83.69%（README）与 55.4%（BASELINE） | ACM PDF 403 Cloudflare；摘要无该值 |
| D4 | Zhao et al. 的 r=0.780 @k=10 | Crossref/ISSTA program 摘要无数值；PDF 403 |
| D5 | SWE-bench Verified 2026-02-23 弃用日期 | openai.com 403 |
| D6 | `agent-sandbox-runtime` | 未定位任何一手来源 |
| D7 | VIGIL 的任何定量指标 | 原文摘要即无数值 |
| D8–D11 | LANTERN / TraceCoder / AgentRepair / UTgen | 均未定位 |
| D13/D14/D22 | SpecIR、ESBMC-AI、SMT 驱动测试生成 | 未定位对应论文 |
| D20/D25 | LLM 属性不变量推断、Hypothesis×LLM 实证 | 命中误归属 / 唯一载体为 794 字节空壳 |
| D15 | 组合测试 / Alloy / 神经符号预言 | 预算耗尽，**未评估（不得填值）** |
| D26 | SWE-bench Verified 榜首 79.2%（396/500）及两个官方榜单条目 ID | `swebench.com` 30s 超时；`github.com` 本会话被拒；条目 ID 精确检索零命中 |
| D27 | arXiv:2609.24341 的任何具体数值 | 仅取到 abs 摘要，未抓全文 HTML → 只断言「不支持命题 Y」，不引其数值 |

**（补充）两条与项目最可比的锚点的精确口径**（`WS1` §2b，一手原文逐字核对）：

- **TestGenEval 35.2%** = **被测代码行覆盖率**：分子 = 生成套件执行到的被测文件行数；分母 = 该文件可执行行数；**仅统计通过的测试**；GPT-4o、temp=0.2、1,210 file pair 平均、**文件级**。检出代理是同一行的 **Mutation 18.8%**。
- **ULT 41.32%** = **测试通过率**（Eq.1 `Pass@k = ΣCᵢ/(N×K)`），**不是缺陷检出率**。⚠️ 但论文 RQ1.1 表实测 ULT Pass@1 = 9.39–17.83%，**平均不出 41.32%**；本次抓取在该表处被截断、未能定位产生该数的表 → **建议在 TOSEM 正式版定位前只引定义、不引此数**。

---

## 5. 项目与前沿量化对比矩阵

### 5.1 同口径可比性判定（**先于表格，因为这是本报告的核心方法论结论**）

| 项目指标 | 前沿是否有同口径对手 | 判定依据 | 可否直接对比 |
|---|---|---|---|
| `detection_rate`（fail-to-pass 检出率） | **无** | 我核实了 TestGenEval（line coverage）、ULT（Pass@k 通过率 + mutation）、CANDOR（line/branch/mutation）、TestAgent（line + bug precision）的分子分母后确认：**2025–2026 一手基准无一报告 fail-to-pass 检出率** | ❌ **不可直接对比** |
| target line coverage | 有（ULT 45.10% stmt、TestGenEval 35.2% line） | 口径相近（被测代码行覆盖） | ⚠️ **形式可比，但项目侧仅在合成集有数且饱和（88.1% 达 100%）→ 对比无意义** |
| mutation score | 有（ULT 40.21%、TestGenEval 18.8%、MUTGEN 论断） | 口径相近（变异体杀死比） | ⚠️ **形式可比，但项目侧 0.818–0.976 系合成集饱和值，项目自认鉴别力有限 → 对比会误导** |
| repair rate / Pass@1 | 有（FTDI HumanEval Pass@1 63.41%） | 任务与语言不同（代码生成 vs 测试修复） | ❌ 不可直接对比（且项目侧无当次运行证据，见 U1） |
| 成本 | 有（ICST 2026 以 LLM 请求数度量） | 可换算（项目侧 llm_calls/task = 4.2 vs df 1.0；ICST 复现 Plain-LLM ≥11,815 requests 于 3,657 方法） | ⚠️ 方向可比，量纲不同 |

> **因此本报告拒绝给出"项目 X% vs 前沿 Y%，故超越/落后 Zpp"的表格。** 任何这类表述在方法论上无效。下表只列**可验证事实**与**判定**。

### 5.2 量化对比矩阵

| 维度 | 2025–2026 前沿 SOTA（一手） | 等级 | 项目现状（本次实测） | 项目等级 | 绝对/相对差距 | 竞争位置 | 可否对比 |
|---|---|---|---|---|---|---|---|
| 测试生成 · line coverage（真实 Python） | TestGenEval GPT-4o **35.2%**；ULT **45.10%** stmt | A | **无真实代码数据**；合成集 med 98%（88.1% 任务=100%） | A（合成）/ **无**（真实） | **无法计算** | **不可判定** | ❌ 项目无真实数据 |
| 测试生成 · mutation | ULT **40.21%**；TestGenEval **18.8%** | A | 合成集 **0.818–0.976**（项目自认饱和） | A（合成） | 不可比（不同基准/语言/难度） | **不可判定** | ⚠️ 形式上项目更高，但不可采信 |
| **检出能力 · fail-to-pass** | **前沿无同口径指标** | — | aitester **15.8%**；plain_llm_df **44.8%**；plain_llm 1.5% | A | — | **无对手可比** | ❌ 无同口径 |
| 多智能体协作 · 编排增益 | ICST 2026：Plain-LLM 49.95/35.33/33.82 **全面优于** 4 个 SOTA 工具（A） | A | **受控配对 δ = −24.6pp，95% CI [−33.7,−15.6]**，配对 t=−5.36 | A | **项目自身数据同向且更强地否定编排** | **与前沿同向：编排无优势** | ✅ 方向可比 |
| 自修复 · repair success | FTDI HumanEval Pass@1 **63.41%**（预算感知自修复，A） | A | 主批次三臂 **0.0%**（A）；离线重放 **39.31%**（不可验证 U1） | A / **D** | 若采信重放则 **−24pp**；若采信当次则 **−63pp** | **显著落后（且当次无证据）** | ⚠️ 任务不同，仅作量级参照 |
| **真实仓库任务（唯一外部有效性）** | SWE-bench 系真实基准（BOAD 在 Verified 上优于单智能体，A） | A | **0/20 通过，且补丁在全部 20 个任务上应用失败** | A | **无有效数据** | **尚未进入可比区间** | ❌ 实验未跑通 |
| 逻辑驱动 · 规约可编译率 | TOGLL：1,023 个 EvoSuite 检测不到的唯一缺陷（A）；LM2Alloy：68% 分支覆盖但漏真实缺陷（A） | A | **全量中位数 0.200；47.6% 任务为零** | A | 项目侧"逻辑"对半数任务空转 | **未形成可对话能力** | ❌ 无量纲对应 |
| 自修复 · detection latency / MTTR | **一手文献普遍不报数值**（VIGIL 摘要即无数值） | D（数值） | **项目无该指标** | — | — | **该维度前沿尚无基线** | ❌ 双方均无数值 |
| 工程化 · 可复现性 | — | — | 5390 passed/0 failed；SHA256SUMS 20/20；门禁 24 个（1 个红） | A | — | **显著优于同类科研代码** | ✅（非前沿对比，为质量事实） |
| 引用完整性 | — | — | 8/13 标识符完全属实，0 伪造 | A | — | **优于平均** | ✅ |

### 5.3 统计显著性的独立重算（含聚类稳健版本）

**任务级（项目口径，数据源同 §3.2 三批次）**：

| 统计量 | 我重算值 |
|---|---|
| 可配对行数 | **n = 240** |
| 配对差 δ（aitester − plain_llm_df） | **−28.3 pp**（= −0.283，项目报 −0.279，**同量级**） |
| 不一致对 | aitester 独有 12 行；df 独有 80 行；共 92 |
| **Exact McNemar 双侧 p** | **1.7 × 10⁻¹³** |

**分 seed 波动（我重算）**：

| 臂 | seed 42 | seed 43 | seed 44 | 波动 |
|---|---|---|---|---|
| aitester | 14.8% | 19.0% | 13.8% | **5.2 pp** |
| plain_llm | 1.1% | 1.1% | 2.3% | 1.1 pp |
| plain_llm_df | 43.7% | 41.4% | 49.4% | **8.0 pp** |

**聚类稳健版本（以 26 个唯一程序体为分析单元——方法学上正确的口径）**：

| 统计量 | 我重算值 |
|---|---|
| 唯一程序体簇数 | **n = 26** |
| aitester 平均检出（簇内均值后取簇间均值） | **19.3%** |
| plain_llm_df 平均检出 | **44.0%** |
| **δ** | **−24.6 pp** |
| 簇间 SD / SE | 23.4 pp / 4.6 pp |
| **95% CI** | **[−33.7, −15.6] pp** |
| 配对 t（df=25） | **−5.36** |
| 符号检验 | 21 簇偏向 df / 2 簇偏向 aitester / 3 簇持平，**exact p = 0.0001** |

**独立统计判定**：
1. **负向结论稳健**——三种方法（任务级 McNemar、簇级 t、簇级符号检验）**一致显著**，方向相同。**F1/F2 成立，不是伪影。**
2. **但头条精确度被高估约 3.35 倍**（240 行 → 26 簇）。真实效应是 **−24.6pp**，不是 −28.3pp；CI 宽达 18pp。
3. **分 seed 波动 5–8pp** 表明点估计不稳定；项目合并三 seed 的做法**方向正确**（降低方差），但**未做聚类校正**，导致 CI 过窄、p 值过小。
4. **分母不一致带来的口径风险（我独立补充）**：项目口径下 aitester 分母为 **240**（剔除 21 行 `None`），而 `plain_llm`/`plain_llm_df` 分母为 **261**。我做了**共同支撑（common-support）对照**——只保留三臂均可测的 240 个任务：

| 臂 | 项目口径 | **共同支撑口径（n=240，三臂同分母）** |
|---|---|---|
| aitester | 15.8%（38/240） | **15.8%（38/240）** |
| plain_llm | 1.5%（4/261） | **1.7%（4/240）** |
| plain_llm_df | 44.8%（117/261） | **44.2%（106/240）** |
| δ（aitester − df） | −29.0 pp | **−28.3 pp** |

**判定**：共同支撑口径下结论**不变**（δ 仅从 −29.0 微调至 −28.3pp），df 的领先幅度从 44.8% 修正为 **44.2%**。**项目的定性结论在此校正下稳健**，但对外引用**必须同时披露 240/261 分母混用**。

### 5.4 竞争位置判定（最终）

| 判定项 | 结论 |
|---|---|
| 在**合成基准**上的内部对照 | 完整系统**显著劣于**单提示协议（−24.6pp，CI [−33.7,−15.6]），成本 5.5× |
| 在**真实基准**上的表现 | **无有效数据**（0/20，补丁从未应用） |
| 在**前沿同口径**中的位置 | **不可判定**（前沿无 fail-to-pass 指标） |
| 在**可对话的前沿维度**（coverage/mutation，真实 Python） | **无数据** |
| **严谨结论** | **项目当前处于"实验条件尚未就绪"阶段，而非"落后于前沿"阶段。** 声称"超越前沿"缺乏任何可验证依据；声称"落后于前沿"同样缺乏同口径依据。**唯一可辩护的表述是：内部对照显示其核心机制为负贡献，外部有效性为零。** |

---

## 6. 超越前沿方法设计

> **设计前提（必须先接受，否则以下路径全部无效）**：
> 1. 项目的核心问题**不是"性能不够"，而是"实验条件未就绪"**（§3.3、§5.4）。因此全部路径的**前置条件是"让实验能产出有效数据"**，而非"调参提升指标"。
> 2. 项目主指标 `detection_rate` 在**前沿无同口径对手**（§5.1），且在真实基准上**不可计算**（ULT 无 gold tests，`src/datasets/dataset_ult.py:15-18`）。因此"超越前沿"的唯一可行形态是**制造一个新的可比维度**，而不是在一个无人竞争的指标上刷高。
> 3. 全部预期提升必须标注证据等级；**凡属理论推导的，一律标 E 级并说明依据**。

### 6.1 路径 A1｜把"政策无关的 oracle 判别力"做成前沿第一个可分维度（**最高优先**）

**技术路径**
将项目已实现的 `src/measurement/mdo.py`（MTR 触发率 / MDR 判别率 / CRASH 崩溃率三分解，`compute_mdo()`，含池规模下限 `pool_floor(p,α)` 与 `available=False` 保守语义）从"独立测量层"升级为**在真实世界 Python 基准上的主终点**，并在 ULT（TOSEM 2026，3,909 真实函数，抗污染）上跑出第一批 MTR/MDR 数值。

**与前沿的差异化点（这是本路径成立的核心理由）**

| 前沿现状（一手核实） | 项目可提供的增量 |
|---|---|
| MUTGEN（IEEE TSE 2026, `10.1109/tse.2026.3682975`）证明"**部分测试套件 100% 覆盖率但仅 4% 变异得分**"，但**把该落差作为一个标量报告** | 把落差**分解为"触发（MTR）"与"判别（MDR）"**，定位落差发生在哪一环 |
| ULT 报告 mutation **40.21%**（单一标量） | 同一批函数上给出 **MTR / MDR / CRASH 三分解** |
| 项目自己的 `mutation_score` 用 **`rc==1` 判"杀死"**，把"变异体让程序崩溃"也算作杀死（`src/measurement/mdo.py:13-17` 自述该缺陷） | MDO **不以退出码为判据**，把"崩溃但无断言失败"单列为 CRASH，**不并入 MDR** |

> **因此这不是"再做一个变异测试器"，而是把一个已知的度量缺陷（退出码判杀死）修正为行为判据，并在真实基准上给出前沿从未报告过的分解。** 一手支撑：MUTGEN 的 4% 论断（A）+ ULT 的 40.21%（A）+ Zhao/Zhou/Cohen（ISSTA 2026 Distinguished Paper, `10.1145/3832093`）关于"被测代码可能有缺陷时覆盖率/变异相关性不可靠"的限定性结论（A）。

**理论基础**：判别力 = P(触发 ∧ 被断言标记)。`mutation_score` 只测前者，`detection_rate` 与修复策略数学耦合（项目 `mdo.py:5-7` 自述）。MDO 用行为摘要（返回值 + 异常类型 + 全局状态摘要）作差异判据，是**唯一在"无 gold 测试"条件下仍可计算的测试质量度量**——这正是 ULT 协议所要求的（`src/datasets/dataset_ult.py:15-18`：官方不发布 ground-truth tests，`detection_rate` 恒 None）。

**预期性能提升**

| 目标 | 数值 | 依据 | 置信度 | 证据等级 |
|---|---|---|---|---|
| 产出 ULT 标定集（≥200 任务）上的 MTR/MDR/CRASH | 首次产出 | 已有一手基准 + 已有 MDO 实现 + 池下限公式 `n≥ln α/ln(1−p)` | **高**（工程可得） | A（工具链）/ E（数值未知） |
| 达成池规模下限 | 每任务 ≥ **29** 变异体（p=10%, α=0.05） | `mdo.pool_floor()` 直接计算 | 高 | A |
| MDR 显著低于 MTR（即"触发多、判别少"） | 方向性预期 | MUTGEN 4% 论断 + `mdo.py:8-10` 引用的"触发率 32–39% 而检出率仅 1–2%" | 中 | **B/E**（同类文献方向一致，本项目数值未知） |

**实验验证方案**
- 基准：ULT 官方 200 任务标定集（先定标，后全量 3,909），**不得使用合成集**。
- 对照组：① ULT 论文的 mutation 40.21%（一手，A）；② 项目自身 `mutation_score`（退出码口径）——同一批任务上并列，量化"退出码口径 vs 行为口径"的差值。
- 指标：MTR、MDR、CRASH、`pool_floor_ok` 比例、与官方 Cosmic-Ray mutation score 的 Spearman 秩相关。
- 统计要求：报告效应量（Cliff's δ 或 A12）**而非仅 p 值**——这是 CANDOR 的呈现标准（`WS1` §6，A 级依据）。
- 可复现性：固定 temp=0.0、记录 `git_sha` + 非脏树（**当前主批次 `git_dirty=true`，必须修正**）、ULT 数据版本 + Cosmic-Ray 版本。

**反事实推演**
- *若前沿也做 MDO 分解？* 该分解逻辑公开（`pool_floor` 是教科书公式），**复制门槛约 2–4 周**。项目护城河**不在方法，而在"已经跑通 + 已在抗污染基准上落数"**——先发优势约 1–2 个季度。
- *若 MDR 与 mutation_score 高度相关（ρ>0.95）？* 则增量仅为"可归因"，不构成新维度。**这是本路径最大的失败风险**，必须在标定集上先验证。
- *项目护城河可被快速复制吗？* **可以。** 因此本路径的战略价值在于**把它作为公共度量发布**（占住"oracle 判别力分解"这一命名与协议），而不是靠它建立性能壁垒。

**实现路径与里程碑**

| 阶段 | 时间 | 交付 |
|---|---|---|
| 短期 | 1–3 月 | ULT manifest 导出（loader 已存在）→ 200 任务标定 → MDO 三指标落数 → 池下限达标率报告 |
| 中期 | 3–6 月 | 全量 3,909 + PLT 双轨（memorization vs reasoning 受控对照）→ 与官方 mutation 的一致性分析 |
| 长期 | 6–12 月 | 把 MTR→MDR 落差的**归因**做出来：落差来自"断言缺失"、"断言弱"还是"输入未覆盖"？→ 这构成一个可发表的机制性结论 |

**独立验证判定标准**
- ✅ **成功**：在 ULT ≥200 任务上 `pool_floor_ok` 比例 ≥80%，且 MTR/MDR 可计算；发布的数据表可被第三方用官方 Cosmic-Ray 复算（给出脚本与版本钉版）。
- ❌ **失败**：（a）`pool_floor_ok` <50%（指标仍饱和，无鉴别力）；（b）MDR 与官方 mutation score 的 ρ>0.95（无增量信息）；（c）无法在非脏树上复现（可复现性失败）。

---

### 6.2 路径 A2｜修通外部有效性闸门（**P0 阻断项，不做则其余路径无意义**）

**技术路径**
修复"真实仓库任务上补丁从未成功应用"（§3.3）。三个已知断点：
1. **数据**：`~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl` 为 0 字节、全仓无 enrichment JSONL → `dataset_loader.py:626` 兜底为 issue 文本。
2. **补丁落地**：`llm_patch_apply_failed` 在 20/20 任务上出现（工件 A 的 19/20 是 syntax，工件 B 的 10/10 是 apply 失败）。
3. **provenance**：工件 A 的 `provenance=null`、`environment=null`、`repo="unknown"` → 该实验**不满足项目自订的取证纪律**。

**与前沿的差异化点**：无（这是工程前提，不是研究贡献）。其价值在于**把项目从"不可评估"变为"可评估"**——这是任何超越主张的必要条件。

**预期性能提升**：**不以提升 repair rate 为目标**。唯一目标是：`llm_patch_apply_failed` 不再出现于 100% 的任务；F2P baseline 与 after-patch 计数**出现差异**。

**实验验证方案**
- 基准：SWE-bench Lite 全 300 例（当前仅跑过 20 例）。
- 对照组：现有 20 例工件（作为"修复前"基线）。
- 指标：补丁应用成功率、`FAIL_TO_PASS` 计数变化率、`PASS_TO_PASS` 回归率、`provenance` 完整率（须 100%）。
- 统计要求：本阶段**不做显著性检验**（先证明管道能产出非退化数据）。
- 可复现性：`git_dirty=false`、环境快照 + enrichment 数据版本 + 仓库 commit 全部入工件。

**反事实推演**：本路径不产生学术优势，因此无"护城河"问题。但**若不做，本项目在真实代码上永远没有数据**，所有对外主张都只能停留在合成集。

**里程碑**：短期（1–2 月）完成 enrichment 生成 + 20 例端到端复跑；中期（3 月）300 例全量。

**判定标准**
- ✅ **成功**：≥60% 任务补丁成功应用；**且** 至少一个任务的 `FAIL_TO_PASS after-patch > baseline`（证明管道能区分"修好了"与"没修"）；provenance 100% 完整。
- ❌ **失败**：补丁应用成功率 <20%，或 after-patch 与 baseline 计数仍逐任务相同（管道仍不生效）。

---

### 6.3 路径 B｜把"逻辑驱动"从空转变为约束产出（规格真实化）

**技术路径**
针对 §3.5 的实测事实（**中位数 0.200、47.6% 任务零可编译子句**），扩展规约文法与编译通道：
- 放开 `src/specs/spec_ir_v2.py:63-69` 的白名单：加入**集合/序列谓词**（`all/any/sorted/len`）、**有界量化的退化形式**（对已知长度输入的逐元素约束）、**关系比较**（`r == f(a,b)` 形式的输入-输出关系）。
- 把 `spec_smt.py` 的翻译层从"保守跳过"改为"**部分可译则部分求解**"（当前是整体跳过返回 `[]`，导致一条不支持算子即失去全部约束）。
- 与 `TOGLL`（ICSE 2025, `10.1109/ICSE55347.2025.00098`，A 级：**3.8× 正确断言、1,023 个 EvoSuite 检测不到的唯一缺陷**）的断言挖掘策略对齐。

**与前沿的差异化点**

| 前沿 | 项目 |
|---|---|
| TOGLL 从代码中**挖掘**断言（无需规约） | 项目从**自然语言规约**编译断言 |
| LM2Alloy（arXiv:2607.18555）走 Alloy 形式化路线，**68% 分支覆盖但三次运行全漏同一真实缺陷** | 项目走 SMT 直接见证，**跳过了 Alloy 中间层**——与 LM2Alloy 中"跳过 Alloy 的 LLM 基线"同一条技术思路，但项目用求解器补上严格性 |

> **战略含义（诚实提示）**：项目"逻辑驱动"最可对话的前沿在 **Alloy/形式化规约路线**；项目实际采用的**属性推断/Hypothesis 路线在 2025–2026 一手文献中无实质载体**（`WS1` §5b、D20/D25）。建议**二选一**：要么把 SMT 见证路线做成主线（对齐 LM2Alloy/TOGLL 的对话面），要么承认属性测试是工程选择而非研究主张。

**预期性能提升**

| 目标 | 当前 | 目标 | 依据 | 置信度 | 等级 |
|---|---|---|---|---|---|
| `spec_compile_rate` 中位数 | **0.200** | **≥0.55** | 项目自订目标（`BASELINE.yaml:66` 路径 D2）；文法扩展为直接原因 | 中 | **E**（纯工程推导，无一手同类数据） |
| 零可编译子句任务占比 | **47.6%** | **<15%** | 同上 | 中 | **E** |
| 由此带来的 MDR 提升 | 未知 | 方向性正向 | TOGLL 的 3.8× 断言质量（A）为类比依据，但任务不同 | 低 | **E** |

**实验验证方案**
- 基准：ULT 标定集 + QuixBugs（`data/quixbugs`，MIT，已入库）。
- 对照组：① 现有文法（作为 baseline）；② 无规约通道（`SPEC_IR_DSL_ENABLE=false`）；③ TOGLL 报告值（跨语言，仅作量级参照，**不得直接对比**）。
- 指标：`spec_compile_rate`、`spec_expr_coverage`、**以及 MDR**（关键：规约必须转化为判别力，而不只是"编译通过率"上升）。
- 统计要求：配对设计（同任务同 seed），报告 A12/Cliff's δ。
- 可复现性：文法版本号入 provenance。

**反事实推演**
- *若前沿也扩展文法？* TOGLL/LM2Alloy 已在做更强的形式化，**项目没有理论领先**。
- *真正可辩护的差异*：项目的 SMT 通道产出**可执行的见证（witness）输入**而非仅断言——这是"用求解器生成测试输入"而非"用 LLM 猜输入"。**这个点在前沿一手文献中我未找到同构系统**（`WS1` §5b/D22：SpecIR、SMT 驱动测试生成均未定位一手来源）。**若成立，这是项目唯一可能的技术原创点**，但需要严格的形式化陈述与对照实验来证明它优于"LLM 直接生成边界输入"。

**判定标准**
- ✅ **成功**：`spec_compile_rate` 中位数 ≥0.55 **且** MDR 相对无规约臂提升 ≥5pp（证明规约转化为判别力）。
- ❌ **失败**：编译率提升但 MDR 无变化（说明"逻辑驱动"对检出无因果贡献，应降级为工程选项）。

---

### 6.4 路径 C｜把编排从手工设计改为自动搜索（对齐 BOAD）

**技术路径**
项目当前是**手工编排**（固定 `Planner → Generator → Executor → Debugger → PatchApplier`）。BOAD（**ICLR 2026**, arXiv:2512.23631，经 IBM Research 官方页确认，A 级）用**多臂老虎机自动搜索层级式 orchestrator**，在 SWE-bench-Verified 上优于单智能体与**手工**多智能体。项目应把编排拓扑作为搜索空间。

**与前沿的差异化点**：项目拥有 BOAD 没有的东西——**12+ 个可独立开关的机制**（`config.py:43-115` 的 `_PROFILE_PRESETS`）与**完整消融基础设施**。这是一个天然的搜索空间。

**预期性能提升（诚实标注）**

| 目标 | 依据 | 置信度 | 等级 |
|---|---|---|---|
| 在受控预算下把 δ 从 **−24.6pp** 收窄到 **≥−5pp** | 项目自订转正判据（"预算对照下复现正向 detection 增量"，`README.md:31-34`）；BOAD 的一手结果为类比 | 低 | **E** |
| 若搜索后仍为负 → **接受负结论并转向** | ICST 2026 复现（A）已证明手工工具特定编排无优势 | 中 | **B** |

**反事实推演（本路径最重要的一段）**
- *若前沿也做编排搜索？* BOAD 已经在做，**且做得更彻底**。项目在此**没有先发优势**。
- *项目护城河在哪？* **不在编排。** 若 δ 无法转正，**正确的研究决策是放弃编排作为主张**，把资源集中到 A1（度量）与 A2（外部有效性）。
- *护城河可被快速复制吗？* 编排搜索可复制；**测量纪律与口径矩阵（`docs/design/repair_caliber_matrix.md`）不易复制**——这是本项目最被低估的资产（见 §6.5）。

**判定标准**
- ✅ **成功**：搜索得到的编排在**预算匹配**（token cap + 迭代数对齐）下 δ ≥ 0。
- ❌ **失败**：δ 仍 < −5pp → **应据预注册停止规则终止编排路线**，不再投入。

---

### 6.5 路径 D｜把"测量纪律"本身产品化（**真正的护城河**）

**技术路径**
项目最强的资产不是算法，是**可复现的测量制度**：预注册（`docs/preregistration.md` 双语）、口径矩阵（`repair_caliber_matrix.md`）、24 个 CI 门禁、ADR 25 份、SHA256SUMS 工件清单、以及**三次测量伪影的事后更正记录**（ADR-0021/0027/0029）。

**与前沿的差异化点**
- 我核实的 8 个一手来源中，**没有一篇报告了"我们如何发现自己此前的测量是错的"**。
- ICST 2026 复现的方法论亮点（完整仓库而非挑选类；按模型 cutoff 区分 seen/unseen；显式排除网络失败请求）与本项目的口径矩阵**属于同一类贡献**，但项目做得更系统。
- ULT 的正式文献形态就是把"污染"作为基准设计的一等约束（A 级）——**项目在"自曝测量缺陷"这件事上有真实案例积累**。

**预期性能提升**：非性能类。目标是**把"负结果 + 自我勘误"作为可发表的方法论贡献**，而不是掩盖它（项目已经在做，`README.md` 头部即为此形态）。

**反事实推演**：这一路径**不可被"同样的算法优化"抹平**——因为它不是算法。它是唯一在竞争路线采用相同技术后仍然成立的优势。

**判定标准**
- ✅ **成功**：以"LLM 测试生成评估中的测量伪影：三个案例与一套协议"为题的完整方法论产出，且被第三方引用/复用。
- ❌ **失败**：无法给出可迁移的一般化协议（即只讲了自己的三个故事）。

---

### 6.6 超越路径汇总表

| 编号 | 子方向 | 技术路径 | 前沿参考（一手） | 差异化点 | 目标指标 | 预期提升 | 置信度 | 等级 | 验证基准 | 对照组 | 里程碑 | 反事实风险 | 成功判定 | 失败判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A1** | 评估/度量 | MDO（MTR/MDR/CRASH）在 ULT 上落数 | MUTGEN TSE'26；ULT TOSEM'26（mutation 40.21%） | 前沿只报单一标量；MDO 分解触发/判别，且不用退出码判杀死 | MTR/MDR/CRASH | 首次产出 | 高（可得性）/ 中（结论） | A（工具）/ E（数值） | ULT 200 标定 → 3,909 | ULT 官方 mutation 40.21%；项目自身退出码口径 | 1–3 月标定 | MDR 与 mutation ρ>0.95 → 无增量 | 池下限达标 ≥80% 且可第三方复算 | ρ>0.95 或池下限 <50% |
| **A2** | 外部有效性 | 修通 SWE-bench 管道（数据+补丁落地+provenance） | BOAD ICLR'26（真实基准） | 无技术差异；是前提工程 | 补丁应用成功率 | 从 0% 到 ≥60% | 中 | A（可观测） | SWE-bench Lite 300 | 现有 20 例工件 | 1–2 月 20 例复跑 | 无（不产生学术优势） | ≥60% 应用率 + ≥1 任务 F2P 变化 | <20% 应用率 |
| **B** | 逻辑驱动 | 扩展规约文法 + 部分可译求解 + 对齐 TOGLL 断言挖掘 | TOGLL ICSE'25；LM2Alloy | SMT 产**见证输入**而非仅断言（前沿未见同构系统） | spec_compile_rate 中位数 | 0.200 → ≥0.55 | 中 | **E** | ULT + QuixBugs | 现有文法 / 无规约臂 | 3–6 月 | 编译率升但 MDR 不变 → 逻辑驱动无因果贡献 | 编译率 ≥0.55 且 MDR +5pp | 编译率升但 MDR 无变化 |
| **C** | 多智能体 | 编排拓扑自动搜索 | BOAD ICLR'26（TAMLB） | 项目有 12+ 独立开关可作搜索空间 | δ（预算匹配） | −24.6pp → ≥−5pp | 低 | **E** | 合成集（先行）→ 真实基准 | 手工编排 / 单提示 | 3–6 月 | 前沿已做且更彻底；项目无先发优势 | 预算匹配下 δ ≥ 0 | δ 仍 < −5pp → 按预注册停止 |
| **D** | 方法论 | 测量伪影协议产品化 | ULT（污染作为一等约束）；ICST'26 方法论 | 前沿无人报告"如何发现自己的测量错误" | 可迁移协议 | 非性能 | 中 | **B** | — | — | 6–12 月 | 只讲自己的故事 → 不可迁移 | 被第三方复用 | 无法一般化 |

---

## 7. 差距分析表

按维度给出"项目现状 vs 独立重建的前沿"，**并在每一行明确标注可否对比**（这是本报告区别于常规评审的地方）。

| 维度 | 项目现状（本次实测，A 级） | 2025–2026 前沿（一手，A 级） | 差距性质 | 可否对比 | 优先级 |
|---|---|---|---|---|---|
| **科学性** | 测量伪影三次事后更正（ADR-0021/0027/0029）；预注册双语；口径矩阵。**高于平均** | 无人报告"如何发现自己的测量错误"（`WS1` 未检索到同类） | **反向领先**（方法论） | ✅ 可对比（定性） | — |
| **创新性（核心机制）** | 多智能体编排受控对照 δ=−24.6pp（CI [−33.7,−15.6]） | ICST 2026：Plain-LLM 全面优于 4 个 SOTA 工具（A） | **同向，项目自证负贡献** | ✅ 可对比（方向） | **P0** |
| **创新性（逻辑驱动）** | spec_compile_rate 中位 0.200，47.6% 任务为零；CEGIR 未接线 | TOGLL 1,023 个唯一缺陷；LM2Alloy 68% 分支覆盖 | **能力未形成** | ❌ 无量纲对应 | **P0** |
| **问题定义** | 自称"逻辑驱动多智能体测试生成与自修复"；实际主体是"检出优先提示协议"（df 44.8% vs aitester 15.8%） | SWT-Bench：Code Agent 在测试生成上超过专用系统 | **命名与实体错配** | ✅ 可对比（定性） | **P0** |
| **数据** | 16 模板 / 87 标签 / **26 唯一程序体**；bug+gold+oracle 同源编写 | ULT 3,909 真实 Python 函数、抗污染策划（A）；TestGenEval 11 仓库 1,210 pair（A） | **外部有效性为零** | ❌ 项目无真实数据 | **P0** |
| **方法** | LangGraph 图 + 12 开关；SMT 见证（真 z3 5.1.0）；MDO（MTR/MDR/CRASH）已实现 | BOAD：编排自动搜索（ICLR 2026, A）；FTDI：预算感知自修复（A） | 手工 vs 自动搜索 | ✅ 可对比（方向） | P1 |
| **实验设计** | 三臂同模型/同温度/同迭代数/同 seed 配对（公平）；但 `git_dirty=true`、token 记账整臂为零、同 seed 重放逐字节相同 | ICST 2026 方法论：完整仓库、seen/unseen 切分、Mann-Whitney U、显式排除网络失败请求（A） | 取证纪律有缺口 | ✅ 可对比（方法论） | **P0** |
| **评估指标** | detection_rate 与修复策略数学耦合（项目已自识）；coverage/mutation 在合成集饱和 | MUTGEN：100% 覆盖 / 4% 变异得分（A）；Zhao ISSTA 2026 Distinguished：覆盖-变异相关性**限定性**（A） | 指标设计方向正确 | ✅ 可对比 | P1 |
| **可复现性** | 5390 passed/0 failed；SHA256SUMS 20/20；24 门禁（1 红）；Dockerfile.repro | 前沿普遍不提供复现包（`WS1` 未检索到系统级复现纪律） | **反向领先** | ✅ 可对比 | — |
| **工程化** | ruff 产品目录 clean；mypy 覆盖 ≈75.8%；`run_benchmark.py` 176 KB/3,401 行 | — | 大文件可维护性风险 | — | P1 |
| **可扩展性** | 单机、venv 子进程、`use_docker=False`、`kernel_sandbox=False` 默认 | — | 默认无真隔离 | — | P1 |
| **成本** | $0.0259/task vs df $0.0045（**5.8×**）；调用 4.2 vs 1.0（**4.2×**） | ICST 2026 以请求数度量成本（A） | **显著更贵且更差** | ⚠️ 量纲不同 | **P0** |
| **伦理/合规** | 无硬编码密钥；`.env` 从未入库；凭证剔除三层；kernel_sandbox 可选 | — | 优于平均 | — | — |
| **落地场景** | 无真实仓库成功案例（0/20，补丁从未应用） | SWE-bench 系已有可运行系统（BOAD 榜第 2） | **尚未进入可比区间** | ❌ | **P0** |

**差距性质分布**：P0 共 **8** 项，其中 **6 项属于"实验条件未就绪"而非"能力不足"**。这是本报告最重要的结构性判断：**项目的当务之急不是提升性能，而是让实验能产出有效数据。**

---

## 8. Python 专项诊断表

| # | 维度 | 证据（file:line） | 现状 | 严重度 | 与声称是否不符 |
|---|---|---|---|---|---|
| A1 | 项目结构 | `src/` layout + `[project.scripts]` + `py.typed`；`setup.py` 与 `pyproject.toml` **双源** | 可安装（`python -m build` 链路项目自述已取证）；双源有漂移风险 | P2 | 否 |
| A2 | 依赖管理 | `pyproject.toml:24` `requires-python = ">=3.12"`；`requirements.lock` 2.4 KB；`check_lock_sync` 实测**通过** | 三源一致（门禁保证） | — | 否 |
| A3 | 可选依赖降级 | 实测 `.venv` 缺 `tree_sitter` → `ModuleNotFoundError`；`chromadb`/`matplotlib`/`hypothesis` 均在位 | 降级路径存在（3 skipped 实测证实） | P2 | 否 |
| A4 | 类型注解 | `pyproject.toml:232-256` 的 `[tool.mypy]` **无任何严格开关**；AST 实测 src **1,111** 函数中 **842（75.8%）** 完全标注；`src/api/api_manager.py` 仅 **6/43 = 14%** | "mypy 119 源文件 0 错误"是在**非严格配置**下的结论 | **P1** | ⚠️ **是**（"类型安全"被高估） |
| A5 | 文件规模 | `experiments/run_benchmark.py` **3,401 行/176 KB**；`synthetic_dataset.py` 2,532；`nodes.py` 2,210；`statistical_analysis.py` 2,026 | 4 个文件 >2,000 行 | **P1** | 否（但违反项目自订拆分先例） |
| A6 | 测试规模与质量 | 实测 **5390 passed / 0 failed / 200.6s**；266 个测试文件 | 规模与通过率优异 | — | 否 |
| A7 | **零断言测试门禁红** | `scripts/gates/check_zero_assert_tests.py` **exit 1**，2 个违规：`tests/test_mdo_metrics.py::test_as_dict_is_json_serializable`、`tests/test_path_c_trigger.py::test_as_dict_serializable` | 门禁真实红，但 `pytest` 全绿 → **"全绿"≠"门禁全绿"** | **P1** | ⚠️ 是 |
| A8 | 覆盖率取数方式 | `src/agents/executor_output.py:20` `_RE_COVERAGE_TOTAL = re.compile(r"TOTAL\s+.+?(\d+)%")`；**正则解析 stdout**，非 pytest-cov API；无 TOTAL 行时返回 **0.0** | **"无覆盖数据"与"真实 0% 覆盖"不可区分**；`re` 非贪婪匹配存在首百分数陷阱 | **P1** | ⚠️ 是（指标存在静默污染通道） |
| A9 | 沙箱与执行隔离 | 默认 `use_venv=True, use_docker=False, kernel_sandbox=False`（`src/agents/kernel_sandbox.py:68-70`）；venv 路径为**裸子进程**（`executor_modes.py:113-160` 自述） | 默认是**依赖隔离 + 环境脱敏**，**不是安全隔离** | **P1** | ⚠️ 是（"沙箱"措辞过强） |
| A10 | 凭证安全 | `git log --all -- .env` **为空 = 从未入库**；`credential_scrub` 三层；但 `experiments/mutation_testing.py:1239` 传 `env={**os.environ,...}` **未脱敏** | 第四条执行链路绕过凭证剔除 | P2 | ⚠️ 是（"三条链路统一"不完整） |
| A11 | provenance 纪律 | `provenance.max_pattern_repeat` **不存在**（我实测 4 份工件 JSON 无该字符串），但该参数经 CLI 传入（`run_benchmark.py:3334,3396`） | **违反项目自订"干预必须可从工件证明"的最高优先纪律** | **P1** | ⚠️ **是（自订纪律被自己违反）** |
| A12 | 可复现性 | 主批次 `git_dirty=true`（3 批次实测）→ 记录的 `git_sha` **不对应实际运行代码** | 无法从 commit 重建批次 | **P1** | ⚠️ 是 |
| A13 | CI/CD | 3 个 workflow（ci/perf/release）；24 个门禁脚本；实测 `check_artifacts_tracked` 21/21、`check_bilingual_docs` 通过、`check_env_budget` 183/183 | 门禁体系完整度高 | — | 否 |
| A14 | ruff 门禁口径 | `ruff check .` 在当前工作树 **417 errors**（`audit_2026/` 259 + `_independent_audit/` 158）；两目录不在 `extend-exclude`（`pyproject.toml:116`） | 产品目录 clean，但 `make lint` 会被未跟踪审查目录污染 | P2 | ⚠️ 是（口径未写明） |
| A15 | 实验管线数据泄漏 | 合成集入参 `problem_statement` 含缺陷描述；`gold` 与 `fixed` 同文件（`synthetic_dataset.py:2500-2509`） | 生成器可见 gold 材料 → **潜在泄漏面**（项目称已做"problem_statement 无 prompt 消费不变量静态锁定"） | P2 | 部分 |

---

## 9. 领域专项诊断表

| # | 维度 | 证据 | 现状与独立判定 | 严重度 |
|---|---|---|---|---|
| B1 | **逻辑驱动 · 规格语言** | `src/specs/spec_ir_v2.py:63-69` `_ALLOWED_CALL_NAMES` / `_ALLOWED_ATTRS = {value, real, imag}`；`spec_smt.py:17-19` 自述只支持布尔/比较/`+-*/%`/常量/名称 | 支持**命题逻辑 + 一阶原子约束**；**无时序逻辑、无量化、无不变量归纳**。前置/后置/不变量三分类存在（`:187-190`） | **P1** |
| B2 | **逻辑驱动 · 求解器** | 实测 **z3 5.1.0 已安装**；`spec_smt.py:525` `z3.Solver()`、`:542` `z3.Optimize()` | **真调用 SMT 求解器**（非仿制）。产出前件 SAT 见证 + 边界极值 + UNSAT 空洞化检测 + 后件自一致性 | — （**这是真实强项**） |
| B3 | **逻辑驱动 · 落地率** | 全量 n=1,607 行实测：中位 **0.200**、**47.6% 为零** | 对约半数任务**空转** | **P0** |
| B4 | **逻辑驱动 · 闭环** | `README.md:59` 称"闭环"；`src/specs/spec_refine.py:22-24` 自述"**不接入主链路**"；全仓对 `spec_refine`/`CEGIR` **零引用** | **未接线**；`README.md:1376` 自相矛盾 | **P0** |
| B5 | **多智能体 · 通信** | `src/graph/state.py` 803 行共享状态字典；无消息总线协议定义 | 通信是**共享 state 传参**，非协议化消息 | P2 |
| B6 | **多智能体 · 共识/冲突解决** | `src/graph/expert_pool.py:505-513` `debate_round` 只做 **1 次** `DebuggerAgent.debug` 综合调用；`:522-532` 修订候选不参与投票即置首位；`:269-293` "专家"是同构调用的维度后缀变体；`:106-114` `N>3` 时维度循环复用 | **无真正的辩论/共识**：一次 prompt 综合 + 文本包含式投票 + 长度启发式置信度 | **P1** |
| B7 | **多智能体 · 预算/停止** | `provenance.max_iterations=3`；`avg_iterations` aitester 1.10 / df 0.00；`src/graph/cost_budget.py` 存在 | 停止是**固定迭代上限**，非收敛判据 | P1 |
| B8 | **测试生成 · 覆盖准则** | `src/tools/branch_coverage_inject.py`（logic 档开启）；实测任务级 med coverage 98% | 覆盖准则存在但**基准饱和致无鉴别力** | P1 |
| B9 | **测试生成 · 变异测试** | `experiments/mutation_testing.py`（自研 AST 变异器，7 类）；杀死判据 `rc==1`（`:1246-1249`）；默认 `max_mutants=10`（`:1259`） | **自研变异器 + 退出码判据 + 小池截断** → 与 `mdo.py:13-17` 自述的缺陷一致 | **P1** |
| B10 | **测试生成 · 测试预言** | `src/tools/oracle_validator.py`、`src/agents/oracle_enhancer.py` 存在；生成测试的断言由 LLM 产出 | 无独立预言正确性判定（同源于 LLM） | P1 |
| B11 | **自修复 · 故障定位** | `src/agents/fault_localizer.py`、`fl_spectral.py`（Ochiai）；`config.py:106-112` 称"**纯测量开关，不改变生成/修复行为**" | ⚠️ **与实际不符**：`src/agents/debugger.py:440-441` `query += "\n\n" + fl_spectral_section` **把 FL 段落拼进补丁生成 prompt** → 直接改变 LLM 输入 | **P1** |
| B12 | **自修复 · 补丁验证** | `src/graph/nodes.py:2044-2049` 只传 `state["generated_test"]`；`patch_rollback.py:189` 子进程仅 `pytest test_path -q` | "**P2P 全量回归**"名不副实：实为**重跑自己生成的单个测试文件** | **P0** |
| B13 | **自修复 · 回滚** | `patch_rollback.py:198-213` + `config.py:74-76`（logic 档 `PATCH_ROLLBACK_FAIL_CLOSED=true`）→ rc≥2/超时/无测试**一律回滚** | **验证 oracle 与生成 oracle 同源** → 坏测试会**误杀正确修复** | **P0** |
| B14 | **自修复 · test-hacking 守卫** | `src/tools/patch_test_hacking.py:20-27` 自述判定核是**观测层**（"命中即拒绝补丁"属"阻断档（待 A/B 后转正）"）；唯一调用点只写结果行（`run_benchmark.py:739-763`） | 是**检测信号而非守卫**；且判定受形态约束（`:81-85,96-103,140-141`） | **P1** |
| B15 | **反馈闭环 · 收敛性** | `experiments/analysis_parts/convergence_analysis.py` 存在；`trace_reward.py` 227 行 | 有观测，无收敛性定理或停止判据 | P2 |
| B16 | **评估 · 统计方法** | `experiments/statistical_analysis.py` 2,026 行（McNemar + BH-FDR + 贝叶斯配对 + 功效分析） | 方法学覆盖面**优于多数同类工作**；但**未做聚类校正**（§5.3） | **P1** |
| B17 | **评估 · 污染检测** | `experiments/contamination_check.py:84-102,196-210,213-260` 三通道**均为"生成补丁 vs gold patch"相似度** | 无成员推断 / 时间切分 / 无上下文探针 → 会把"独立得出同一最小修复"**误判为污染**；且**对合成集无意义**（bug 与 gold 同源编写） | **P1** |
| B18 | **安全 · 代码执行** | A9；`src/agents/injection_guard.py`、`rogue_monitor.py` 存在（默认关） | 默认链路无真隔离；注入防护默认关 | **P1** |
| B19 | **合规 · 数据许可** | `data/quixbugs`（MIT，已核实）；TestGenEval **CC BY-NC 4.0**、BugsInPy **无 SPDX** → 项目已登记为"非清洁许可三选一门槛" | 许可风险**已被识别并登记**（加分） | P2 |
| B20 | **可解释性/可观测性** | `src/observability/`、`src/graph/tracing.py`、`experiments/mast_trace_analysis.py` | 观测层完整；MAST 对齐有报告 | — |

---

## 10. 改进 / 优化 / 新增建议表

> 每条给出：问题 → 一手前沿依据 → 具体做法 → 预期收益 → 成本/风险 → 优先级 → 验证指标 → 时间线 → 具体命令。
> 优先级：**P0 = 不修则结论不可信**；P1 = 影响可信度或可维护性；P2 = 改进项。

| # | 位置 | 问题 | 一手前沿依据 | 具体做法 | 类型 | 优先级 | 预期收益 | 成本/风险 | 验证指标 | 时间线 | 工具/命令 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **S1** | `src/datasets/synthetic_dataset.py:36-56`（16 模板）；`experiments/run_main_batch.py:60` | 基准自建自评，87 标签仅 **26 唯一程序体**；无外部有效性 | ULT TOSEM'26（3,909 真实 Python 函数 + 抗污染，A）；TestGenEval ICLR'25（A） | **停止把合成集作为对外口径**。改为三层：① ULT 标定集 200 任务（主口径）；② QuixBugs（已入库，MIT）；③ 合成集降级为冒烟/回归用途，并在所有报告中标注"仅内部" | 必须改进 | **P0** | 让结论具备外部有效性 | 中（需数据获取与适配）；ULT 许可未澄清（上游 The Stack v2 gated）→ 不得打包进仓库 | ULT 上产出首份可复算报告 | 1–3 月 | `.venv/bin/python -c "from src.datasets.dataset_ult import ..."`；`AITESTER_ULT_DATA=... pytest tests/test_dataset_ult.py` |
| **S2** | `experiments/run_benchmark.py` 全链路；`~/.cache/aitester/swe_bench/`（0 字节） | 真实仓库补丁**从未成功应用**（20/20 `llm_patch_apply_failed`） | BOAD ICLR'26（真实基准上可运行，A） | ① 生成 enrichment JSONL（`scripts/tools/export_swe_bench_source.py` 已存在）；② 加**前置 fail-fast**：`instance_code` 必须 `compile()` 通过且 ≠ `problem_statement`（`dataset_loader.py:392-398` 已有校验，需改为**拒跑**）；③ 复跑前断言 `provenance` 完整 | 必须改进 | **P0** | 从"不可评估"变为"可评估" | 低（工具已存在） | 补丁应用成功率 ≥60%；F2P 计数出现差异 | 1–2 月 | `.venv/bin/python scripts/tools/export_swe_bench_source.py --subset lite --repos-dir ~/swe_repos --output enrichment_lite.jsonl`；`.venv/bin/python scripts/gates/check_swe_bench_pro_ready.py` |
| **S3** | `src/graph/nodes.py:2044-2049`；`src/tools/patch_rollback.py:189` | "P2P 全量回归"实为**重跑自己生成的单个测试文件**；验证 oracle 与生成 oracle **同源** | SWT-Bench NeurIPS'24（黄金测试作过滤器使 precision 翻倍，A） | ① 回归验证改用**仓库既有测试套件**（`pytest <repo>/tests -q`）而非 `generated_test`；② logic 档 `PATCH_ROLLBACK_FAIL_CLOSED` 对"**测试侧错误**（rc≥2/收集错误）"改为 **`inconclusive`**，仅对"断言失败"判 regression_failed；③ 新增结果行 `validation_oracle_type ∈ {gold_suite, generated_test, none}` | 必须改进 | **P0** | 消除"坏测试误杀正确修复"错误路径；修复判定可独立 | 中（需仓库级测试运行能力） | `validation_oracle_type` 字段 100% 非 none；误杀率下降 | 1–2 月 | `rg "generated_test" src/tools/patch_rollback.py`；`pytest tests/test_patch_rollback*.py -q` |
| **S4** | `src/tools/patch_test_hacking.py:106`；`experiments/run_benchmark.py:758-761,1284-1285` | **守卫只审"代码补丁"（`original_code` vs `patched_code`），完全不审 `generated_test`**；且我实测**头条批次的 `test_hacking_*` 键一个都不存在**（从未产数）；命中也不阻断 | Zhao ISSTA'26 Distinguished（"被测代码可能有缺陷时覆盖率/变异不可靠"，A）；LM2Alloy（68% 覆盖仍漏真实缺陷，A） | ① 把检测目标**扩展到测试侧**（断言被删除/放宽、`assert True`、`pytest.skip`、`xfail`、异常吞掉、mock 掉被测函数）；② 由"观测层"升级为**阻断档**（命中即拒绝补丁并回退）；③ 修复字段未落盘问题（实测 0 行携带） | 必须改进 | **P0** | 关闭"测试侧作弊"整条通道（当前**完全敞开**） | 低 | `test_hacking_suspected` 在 ≥1 个批次中非全 False；新增 6 类构造的单元测试 | 1 月 | `pytest tests/test_patch_test_hacking.py -q`；新增 `tests/test_hacking_test_side.py` |
| **S5** | `src/graph/flags.py` / `config.py:106-112` | 称 `FL_SPECTRAL_ENABLE` "纯测量开关，不改变生成/修复行为"，实际 `src/agents/debugger.py:440-441` **拼进补丁 prompt** | — （内部一致性问题） | 修正注释；**在消融归因中把 FL 视为行为开关**；同步更新 `docs/design/` 与 ADR | 必须改进 | **P0** | 消除归因错误风险 | 极低 | 注释与代码一致；`rg "纯测量开关"` 无残留错误断言 | 1 周 | `rg -n "纯测量" config.py src/` |
| **S6** | `README.md:59` vs `README.md:1376` | 同一文档：头条称 CEGIR"闭环"，开关表自述"未接入主链路"；`spec_refine` 全仓零引用 | — | 二选一：① 接线（在 Generator 前消费精化结果）；② 把头条"闭环"改为"可调用能力（未接线）"。**在接线前不得用"闭环"表述** | 必须改进 | **P0** | 消除对外表述失真 | 极低（改文案）/ 中（接线） | 文档两处一致 | 1 周 | `rg -n "CEGIR\|spec_refine" README.md src/ experiments/` |
| **S7** | `BASELINE.yaml:17`；`tests/test_2026_10_10_optimization_batch.py:169-175` | 字段 `5389` / 注释 `5323` / 实测 `5390` 三值互斥；守卫只校验 `declared ≤ collected` 且差额 ≤9 → **陈旧值放行** | — | ① 字段改实测值；② 守卫改为**精确相等**（`declared == collected − skipped − xfailed`）；③ `suite_seconds: 35` 一并更正 | 必须改进 | **P0** | 基线单一事实来源恢复可信 | 极低 | `check_baseline_numbers` + 精确守卫绿 | 1 周 | `.venv/bin/python -m pytest tests/ -q --basetemp=/tmp/bt \| tail -3`；`.venv/bin/python scripts/gates/check_baseline_numbers.py` |
| **S8** | `scripts/gates/check_zero_assert_tests.py`（实测 **exit 1**，2 违规） | CI 门禁真实红但无人处理；`pytest` 全绿掩盖之 | — | ① 修 2 个用例或按脚本 `EXEMPT` 登记理由；② 把"门禁全绿"与"pytest 全绿"分开报告 | 必须改进 | **P0** | 恢复门禁可信度 | 极低 | 该门禁 exit 0 | 1 周 | `.venv/bin/python scripts/gates/check_zero_assert_tests.py` |
| **S9** | `experiments/run_benchmark.py:3334,3396`（`max_pattern_repeat` 入 CLI 不入 provenance） | 违反项目自订"干预必须可从工件证明"最高纪律；项目自述已发生 3 次同类事故 | — | 把 `max_pattern_repeat` 及全部 CLI 干预参数写入 `provenance`；**加静态守卫**：CLI 参数集合 ⊆ provenance 键集合 | 必须改进 | **P0** | 干预可审计 | 低 | 新增守卫 exit 0；4 份历史工件无该问题（新批次） | 1 月 | `rg -n "max_pattern_repeat" experiments/run_benchmark.py` |
| **S10** | 主批次 `provenance.git_dirty=true`（3 批次） | 记录的 `git_sha` **不对应实际运行代码** → 批次不可从 commit 重建 | ICST 2026 方法论（显式记录环境与失败请求，A） | ① 跑批**强制干净树**（项目已有 `--allow-dirty` 红线，需改为默认拒跑）；② 记录 `git diff` 的 SHA256 作为"脏树指纹" | 必须改进 | **P0** | 批次可重建 | 低 | 新批次 `git_dirty=false` 或含脏树指纹 | 1 月 | `git status --porcelain`；`git diff \| shasum -a 256` |
| **S11** | `src/budget/token_usage.py:107-135`；`src/agents/base_agent.py:404-415,453-460` | 7 份批次中 `plain_llm`/`plain_llm_df` token **整臂为零**；2026-10-07 后 aitester 亦大面积零 → **成本对比失效** | — | ① 加**断言**：结果行 `llm_calls>0` 或显式标记 `cache_hit=true`，禁止静默零；② 零值行写入 `token_accounting_status` 字段；③ 报告工具在存在零记账时**拒绝输出成本结论** | 必须改进 | **P0** | 成本数字可信 | 低 | `token_accounting_status` 100% 覆盖；成本报告对零记账批次报错 | 1 月 | `.venv/bin/python -c "..."` 探针；`pytest tests/ -k token_usage -q` |
| **S12** | 同 seed 重放产出**逐字节相同** `generated_test`（我实测 2 对批次 100%） | LLM 缓存命中使代码变更未生效 → 影响独立性 | — | 缓存键加入**代码版本指纹**（`git diff` SHA + 关键模块 hash），或在批次间强制 `cache_namespace` 唯一 | 必须改进 | **P1** | 批次独立性可证 | 低 | 同 seed 不同 commit 的批次不再产出逐字节相同测试 | 1 月 | `rg -n "cache_namespace\|AITESTER_LLM_CACHE" src/ config.py` |
| **S13** | `experiments/statistical_analysis.py` | 未做**聚类校正**（87 标签实为 26 唯一程序体）；p 值与 CI 过窄 | CANDOR（报告 A12 效应量，A）；ICST 2026（Mann-Whitney U，A） | ① 所有显著性检验改为**以唯一程序体为聚类单元**；② 报告效应量（A12 / Cliff's δ）而非仅 p 值；③ 预注册中固化该口径 | 必须改进 | **P0** | 统计结论精确度恢复 | 低 | 报告含聚类 CI 与效应量 | 1 月 | `.venv/bin/python experiments/statistical_analysis.py --help` |
| **S14** | `src/measurement/mdo.py`（已实现但**未接主链路**） | 已实现政策无关 MDO，但 `run_benchmark.py:1231-1237` 字段默认全 `None` | MUTGEN TSE'26（100% 覆盖 / 4% 变异，A）；ULT（mutation 40.21%，A） | ① 默认开启 MDO（或至少在 logic 档）；② 在 ULT 上落数（见 §6.1 路径 A1） | 优化 | **P1** | 产出前沿无同口径的判别力分解 | 中（执行成本） | `mdo_available=True` 比例 ≥80%；`pool_floor_ok` ≥80% | 1–3 月 | `.venv/bin/python -m experiments.mdo_posthoc` |
| **S15** | `src/agents/executor_output.py:20,54-66` | 覆盖率**正则解析 stdout**；无 TOTAL 行时返回 **0.0** → "无数据"与"真 0%"不可区分 | — | 不用 pytest-cov 时改用 `coverage.json`/`coverage` API；无法解析时返回 `None` 而非 `0.0`，并在结果行标注 `coverage_source` | 优化 | **P1** | 消除指标静默污染 | 低 | 新字段 `coverage_source` 100% 覆盖；`None` 语义正确 | 1 月 | `pytest tests/test_executor.py -q` |
| **S16** | `pyproject.toml:232-256` | `[tool.mypy]` **无严格开关**；实测仅 **75.8%** 函数全标注；`api_manager.py` 6/43 | — | 分阶段启用 `disallow_untyped_defs` / `check_untyped_defs`，按模块设 `[[tool.mypy.overrides]]` 棘轮；优先补 `api_manager.py` | 优化 | **P1** | "0 错误"变为真实类型安全 | 中（需补注解） | 启用严格开关的模块数逐步上升；CI 绿 | 2–3 月 | `.venv/bin/python -m mypy src/ config.py` |
| **S17** | `experiments/run_benchmark.py` 3,401 行；`src/graph/nodes.py` 2,210 行 | 4 个文件 >2,000 行 | — | 按项目既有拆分先例（nodes.py 已四簇拆分）继续拆 `run_benchmark.py`（臂定义 / 指标计算 / CLI / 报告分离） | 优化 | **P1** | 可维护性 | 中 | 无文件 >2,000 行；导入路径 re-export 保持 | 2–3 月 | `wc -l $(git ls-files '*.py') \| sort -rn \| head` |
| **S18** | `experiments/mutation_testing.py:1246-1249,1259` | 变异杀死用 `rc==1`（崩溃亦算杀死）；默认池 10，低于 `pool_floor` 的 29 → 饱和 | MUTGEN TSE'26（A）；`src/measurement/mdo.py:13-17` 自述该缺陷 | 默认改用 MDO 的行为判据；池规模默认 ≥29；把 `pool_insufficient` 作为硬标记 | 优化 | **P1** | 变异指标恢复鉴别力 | 中（成本上升） | 池 ≥29 比例；`mutation_score` 不再塌缩到 1.0 | 1–2 月 | `.venv/bin/python experiments/mutation_testing.py --help` |
| **S19** | `src/graph/expert_pool.py:505-513,522-532` | "辩论收敛"实为 1 次综合调用 + 文本包含投票 | BOAD ICLR'26（编排自动搜索，A） | 要么实现真正的多轮辩论 + 明确收敛判据，要么**删除"辩论/共识"表述** | 优化 | **P1** | 表述与实现一致 | 低（改文案） | 文档与代码一致 | 1 月 | `rg -n "辩论\|共识" src/graph/expert_pool.py README.md` |
| **S20** | `experiments/contamination_check.py:84-102` | 三通道均为"补丁相似度"，会把独立同解误判为污染 | ULT TOSEM'26（污染作为一等约束，含 PLT 对照，A） | 引入 ULT 式 **PLT（含泄漏测试）对照**与 seen/unseen 时间切分；对合成集**不做污染判定**（无意义） | 优化 | **P1** | 污染结论可信 | 中 | 采用 PLT 对照 | 3 月 | — |
| **S21** | `src/specs/spec_ir_v2.py:63-69`；`spec_smt.py:17-19` | 规约中位 0.200、**47.6% 为零**；不支持集合/量词/关系谓词 | TOGLL ICSE'25（1,023 唯一缺陷，A） | 扩展白名单 + 部分可译求解（见 §6.3 路径 B） | 新增 | **P1** | "逻辑驱动"名副其实 | 中 | `spec_compile_rate` 中位 ≥0.55 且 MDR +5pp | 3–6 月 | `pytest tests/test_spec_ir*.py tests/test_spec_smt*.py -q` |
| **S22** | `docs/design/ult_bridge_plan.md`（已有方案，未执行） | ULT 桥接仅设计，无实现执行 | ULT TOSEM'26（A） | 执行该方案：200 任务定标 → 门禁 → 全量 3,909 + PLT 双轨 | 新增 | **P0** | 首个外部有效性证据 | 中 | ULT 报告可复算 | 1–3 月 | `.venv/bin/python -m experiments.analyze_results --help` |
| **S23** | `CITATION.cff` / `README.md` 标题 / 任务书 | 对外称"逻辑驱动的多智能体测试生成与自修复系统"，与内部证据（编排负贡献、CEGIR 未接线、无当次 repair 证据）不同步 | — | 对外定位改为项目已自订的 detection-first 口径（`ADR-0016` 已做，需同步到标题/CITATION/任务书）；**并明确声明"前沿无同口径 fail-to-pass 指标，故不作跨基准比较"** | 必须改进 | **P0** | 消除过度宣称风险 | 极低 | 全部对外材料口径一致 | 1 周 | `rg -n "多智能体\|逻辑驱动" README.md CITATION.cff` |
| **S24** | `README.md:28`（请求数 11,718/12,264） | 与一手原文 **11,815/12,741** 不符 | arXiv:2601.09695v2（A） | 更正为 11,815/12,741 | 必须改进 | **P1** | 引用准确 | 极低 | — | 1 周 | `rg -n "11,718\|12,264" README.md README.en.md` |
| **S25** | `README.md:24` vs `BASELINE.yaml:50-51`（TestAgent mutation 83.69% vs 55.4%） | 项目内自相冲突，且两值均**无法从一手源核实** | TestAgent FSE Companion'26 摘要（A/B） | **删除两处 mutation 断言**，仅保留已核实的 line 92.34% + precision 92.22% + 154 bugs；并标注其为 5 页 Companion 短文 | 必须改进 | **P1** | 引用可复核 | 极低 | — | 1 周 | `rg -n "83.69\|55.4" README.md BASELINE.yaml` |
| **S26** | `README.md` 头部（引用 IEEE 11655121） | 项目"最重不利证据"的四个数值**本次无法从任何公开可及一手源确认**（D 级） | ICST 2026 arXiv:2601.09695（已逐字核实的可复核替代，A） | 改以 ICST 2026 复现为主负面证据；IEEE 那条降级标注"存在但数值未经独立复核" | 必须改进 | **P1** | 论据强度不降反升 | 极低 | — | 1 周 | — |
| **S27** | `pyproject.toml:116`（`extend-exclude`） | 未跟踪审查目录（`audit_2026/`、`_independent_audit/`）污染 `ruff check .`（417 errors） | — | 将审查/审计产物目录加入 `extend-exclude`，或移出仓库 | 优化 | P2 | `make lint` 反映真实状态 | 极低 | `ruff check .` exit 0 | 1 周 | `.venv/bin/ruff check .` |
| **S28** | `experiments/mutation_testing.py:1239` | 第四条执行链路传 `env={**os.environ,...}` **未做凭证剔除** | — | 统一走 `credential_scrub` | 优化 | P2 | 消除凭证泄漏面 | 极低 | 静态守卫覆盖该链路 | 2 周 | `python scripts/gates/check_credential_scrub.py` |
| **S29** | `experiments/run_benchmark.py` 的 `provenance` 块 | **模型版本未锁定**：只记 `model_name: deepseek-flash`（浮动别名），不记 API 返回的 `model`、`system_fingerprint` 或探针输出哈希。实测同别名下 `plain_llm` 检出率由 1.5% 漂移至 19.2%（F13） | ULT TOSEM'26（把污染列为一等有效性威胁，A） | ① `provenance` 增记 API 返回的 `model` 字段 + 固定探针补全的**贪心输出哈希**；② 缺指纹的批次标记 `model_version_unpinned`；③ 预注册增加**「模型快照失效即实验作废」停止规则** | 必须改进 | **P0** | 恢复结果可复现性 | 低 | 新批次 100% 带模型指纹；漂移可被检测 | 1–2 周 | `grep -n "provenance" experiments/run_benchmark.py` |

**建议优先级分布**：P0 **15 项**、P1 **11 项**、P2 **3 项**。其中 **P0 中 10 项为"修复可信度"而非"提升性能"**——与本报告核心判断一致。

---

## 11. 既有评审结论独立复核表

> **复核对象**：仓库内至少 6 份根目录审查报告 + `audit_2026/` 5 份 + `review_2026/` 21 份 + `.private/review/` 15 份（合计约 1.2 MB）。本章抽样复核**最具后果的 12 条结论**。
> **复核方法**：一律回到原始工件/代码重算，不采信原报告的自述证据。抽样依据 = 该结论是否影响对外主张。

| # | 原结论出处 | 原结论 | 我的独立复核方法 | 复核结论 | 判定 |
|---|---|---|---|---|---|
| R1 | `INDEPENDENT_REVIEW_2026-10-10.md:28` F1；`EXTERNAL_REVIEW…:193`；`FINAL_REVIEW…:71` | "多智能体有增益"被自身数据证伪：aitester 15.8% vs plain_llm_df 44.8% | 我独立重算三批次 `details[].detection_rate` = 38/240 vs 117/261；exact McNemar p=1.7e-13；**并另做聚类稳健检验**（26 唯一程序体，δ=−24.6pp，CI [−33.7,−15.6]，t=−5.36，符号检验 p=0.0001） | **独立验证支持**，且我**加强了它**（原报告未做聚类校正，效应量被高估；校正后仍显著） | ✅ **支持** |
| R2 | `EXTERNAL_REVIEW…:316` P4：QuixBugs `17/37=45.9%` / `37/40=92.5%`；"对照不可比，见 §3.5" | 数值可复现，但**对照臂不可比**（两臂为分开的单臂工件） | 我读 `e6_a1_batches/e4_quixbugs_FIXED_harness/`：`aitester.json`（2026-10-10T10:15:44）17/37=45.9%、repair 37/40；`plain_llm_df.json`（2026-10-10T10:41:58）**31/37=83.8%**、repair 0/41 | **数值独立验证支持**；**"不可比"判定亦支持**（两次单臂运行、相隔 26 分钟、非同一三臂批次）。⚠️ **但我发现一个框架性问题**：`EXTERNAL_REVIEW`/`FINAL_REVIEW` 的 §0.4 执行摘要把 45.9% 表述为"项目最优可验证数字"，**而未在同一句给出 83.8% 的对照臂**（83.8% 在正文 §3.5/B-21 有，摘要层缺失）。这构成**摘要层的选择性呈现**：更简单的单提示臂在同一基准上比完整系统高 **37.9pp** | ⚠️ **部分支持 + 摘要层表述问题** |
| R3 | `INDEPENDENT_REVIEW_2026-10-10.md:208`；`EXTERNAL_REVIEW…:667`：合成集 aitester detection **14.0%**（可测 78/556）、df **48.9%**（279/571） | 项目主口径 detection 为 14.0% / 48.9% | 我重算**官方三批次**（seed 42/43/44）= aitester **15.8%（38/240）**、df **44.8%（117/261）** | **数值不一致**。两套数字来自不同工件子集（14.0%/48.9% 的分母 556/571 非 261 的整数倍，属跨批次或含 superseded 工件）。项目 `BASELINE.yaml:56` 的官方口径（15.8%/44.8%）与**我的重算一致** | ❌ **原结论口径有误**（应以 240/261 口径为准） |
| R4 | `EXTERNAL_REVIEW…:170` K8："逻辑驱动"在主实验口径下**零实证**（`oracle_type` 只有 `generated_test`，`spec_oracle_*` 键不存在） | 逻辑通道从未在主口径落盘 | 我独立统计 **7 份主批次共 1,827 行**：`oracle_type` **全部为 `generated_test`（1,827/1,827）**；`spec_oracle_verdict` / `spec_oracle_injected` / `enhanced_generated_test` 键**均为 0 行存在** | **独立验证完全支持**。⚠️ 且我补充了一个更强的机制性事实：logic 档 `_PROFILE_PRESETS` **显式开启** `SPEC_ORACLE_EXEC_ENABLE=true`（`config.py:70`），但字段从未写入 → **要么通道未执行，要么未落盘**，两者都是 P0 | ✅ **支持（并加强）** |
| R5 | `EXTERNAL_REVIEW…:193` / `OPTIMIZATION_PLAN_v2.md:281`："'plain LLM 优于复杂编排'已被**两篇独立一手研究**复现"（arXiv:2601.09695 + arXiv:2609.24341） | 两篇独立一手来源支撑该结论 | ① arXiv:2601.09695（Konstantinou, ICST 2026）**我独立核实成立**（A 级，Plain-LLM 49.95/35.33/33.82 全面优于 4 个工具），但它支撑的是"Plain-LLM 优于**工具特定工程化流水线**"，仍**不等于**"单提示 vs 多智能体编排"。② arXiv:2609.24341（Al-Ahmad 等，ClassEval）**已由 WS1 独立核实（见 §11 附）**：该文**设计中没有 orchestration 这个自变量**（因子空间仅 prompt × model，从未实例化多智能体臂），核心是**方差分解**（"Model choice explains more variation than prompt choice"），且**主动放弃排序**（"unequal executable subsets, so their relative mutation scores do not establish superiority"） | **推翻**。原结论犯的是**命题替换（equivocation）**：把 X/X′（覆盖无鉴别力、模型方差 > 提示方差）当成了 Y（单提示优于多智能体）。且同文献集内 CANDOR（0.980 mutation）、TestAgent（92.34% line）、BOAD（ICLR 2026）均为反向证据 → **"两篇独立复现"不成立** | ❌ **推翻（命题替换）** |
| R6 | `EXTERNAL_REVIEW…` / `FINAL_REVIEW…`："'自修复'在代码层不构成运行时自修复系统（无监控/守护/热加载组件）" | 项目不是运行时自愈系统 | 我读 `main.py`（465 B）、`src/cli/app.py`：确为批量 CLI；全仓无守护/热加载/watchdog 组件 | **独立验证支持** | ✅ **支持** |
| R7 | `EXTERNAL_REVIEW…:290` A3："覆盖率是生成有效性的代理"**被证否**（覆盖近饱和但检出近 0） | 覆盖率不能作有效性代理 | 我重算任务级 coverage：aitester med **98**、plain_llm med **100**（**98.9% 任务满覆盖**）而 plain_llm detection 仅 **1.5%** → **满覆盖与近零检出共存**，直接证否"覆盖=有效性" | **独立验证支持**，且我提供了更极端的证据（98.9% 满覆盖 / 1.5% 检出） | ✅ **支持** |
| R8 | `EXTERNAL_REVIEW…:1196` S3：原"全库 1,803/1,672"为 scope 错误，应为 2,015/1,788（7,153 行） | 原报告的一个 scope 错误已被自我更正 | 我不采信 2,015/1,788 这一具体计数（未复算全库 7,153 行口径），但**独立确认其定性结论**：主批次 7 份 × 261 行 = 1,827 行中 `oracle_type` 全为 `generated_test` | 定性结论**支持**；具体计数**未复核** | ⚠️ **定性支持 / 计数未验证** |
| R9 | `REVIEW_2026_FRONTIER.md:276` "两条流传甚广但不成立的引用" | CANDOR 的 ICST 2026 归属等引用有误 | 我独立核实：CANDOR **确为 TOSEM 2026**（DOI `10.1145/3803418`），IEEE 11655121 是**第三方复现**而非 CANDOR 原文 → **原结论方向正确**。项目 `README.md:19-20` 已就地更正 | **独立验证支持** | ✅ **支持** |
| R10 | 项目自评 `README.md:36-41`："repair 经测量口径修正后 = 39.31%（145 可重放行 correct=57）" | 离线重放得 39.31% | WS2 以**自写 normalizer + 自写 pytest runner、零复用项目函数**独立重放：**57/145 = 39.31%**，行级分布 `{skipped 8, no_patch 395, wrong_patch 151, correct 115}` **逐位一致**；反事实证实 v1→v2 的 +5 行确由跨文件物化贡献（退回单文件恰得 52/145=35.86%） | **独立验证支持**（该自评**成立**）。**保留意见**：① 无机器可读输出工件（仅 `corrected_report_v2.md` 文本）；② 复算依赖仓库代码当前状态（含 2026-10-11 新增早退逻辑），历史工件不会再现该值 | ✅ **支持（附两项保留）** |
| R11 | 项目自评 `README.md:56` / `BASELINE.yaml:17`：tests `total_passed: 5389` | 全量 5389 通过 | 我实测（串行）**5390 passed / 3 skipped / 1 xfailed**；WS2 三次实测（串行 ×2 + `-n 4`）亦为 5390；同字段注释写 **5323** | **三值互斥，自评不成立** | ❌ **推翻** |
| R12 | `EXTERNAL_REVIEW…:534` F-1（arXiv:2609.09315）："语句覆盖触发率 32.9% / 分支 38.9% / 变异 32.2%；**检出率仅约 1–2%**" | 触发与检出必须分离度量 | 我未能取得该预印本一手正文（超出 WS1 本次检索范围）；**但该文的定性结论与项目自身实测高度同向**：我实测 plain_llm **98.9% 任务满覆盖 / 1.5% 检出** → 「高触发、低检出」在本项目数据上独立复现 | 定性**支持**；**具体数值未独立核实（D 级，不得引用）** | ⚠️ **定性支持 / 数值未验证** |

**复核结果分布**：**支持 6**（R1/R4/R6/R7/R9/R10）· **部分支持或附保留 3**（R2/R8/R12）· **推翻 2**（R5 命题替换、R11 项目自评）· **口径有误 1**（R3）。

> **§11 附：R5 的独立核实记录（WS1 补充轮）**
> 对 arXiv:2609.24341（Al-Ahmad, Harshvardhan, El-Fakih, AlSobeh，*Evaluating the effectiveness of class-level LLM-generated test suites in Python*）做了定向一手核实：
> - **真实性**：v1 预印本，2026-09-21，作者与标题逐字吻合；**无 venue、未经同行评审，arXiv DOI 尚在 pending registration**（等级 A 仅限存在性/元数据/摘要）。
> - **原文逐字依据（4 条）**：① Method：「multiple prompt strategies across a diverse set of current LLM configurations on the **ClassEval** benchmark」——**因子空间仅 prompt × model，从未实例化任何多智能体编排作为对照臂**；② 「**Model choice explains more variation than prompt choice**」→ model selection should precede prompt tuning；③ 「Human and LLM suites are evaluated on **unequal executable subsets**, so **their relative mutation scores do not establish superiority**」（**主动放弃排序**）；④ 「**no prompt dominates across models**」。
> - **命题拆分**：X（覆盖饱和无鉴别力 + 可执行性做门 + 模型选择先于提示调优）✅ 支持；X′（模型方差 > 提示方差）✅ 支持；**Y（plain LLM 优于复杂多智能体编排）❌ 完全不支持**。
> - **结论**：项目报告的表述属于**命题替换（equivocation）**，而非简单误引。另注 **D27**：本核实只取到 abs 摘要，**未引用该文任何具体数值**；若需引用数字须另取 `arxiv.org/html/2609.24341v1` 全文。
> - **附带核实**：既有报告称 SWE-bench Verified 榜首 **79.2%（396/500）**，来源标为官方榜单 `20251215_livesweagent_claude-opus-4-5` / `20251205_sonar-foundation-agent_claude-opus-4-5`。本次 `swebench.com` 抓取 30s 超时、`github.com` 被拒（非公网 IP）、两个条目 ID 精确检索**零命中** → **判定 D26：不得采信，亦不得据以宣称「榜首」**（系统名有第三方旁证，数值与榜单条目存在性均无法核实）。

**对既有评审的总体判定（独立）**：
1. **既有评审的核心发现（编排负贡献、逻辑驱动零实证、非运行时自愈）我逐条独立验证支持。** 这批报告在事实层面**整体可靠**，且**主动披露了自身局限**（如 P4 标注"对照不可比"）——这是诚信加分项。
2. **两处应予更正**：（a）"两篇独立一手研究复现"的计数错误（R5）；（b）合成集 detection 的 14.0%/48.9% 口径与官方 15.8%/44.8% 不一致（R3）。
3. **一处框架性问题**：执行摘要把 QuixBugs 45.9% 称为"最优可验证数字"而**不在同句给出 83.8% 对照**（R2）。数值无误、可比性也已标注，但**摘要层的呈现会引导读者高估完整系统的水平**——鉴于本项目的问题恰恰是"完整系统更差"，这一呈现方式与项目自身的诚实口径（`README.md:9-11` 主动披露编排劣后）**张力明显**。建议摘要层与正文口径统一。

---

## 12. 优化后的项目方案与路线图

### 12.1 定位重构（**第一优先，1 周内可完成**）

**现状**：对外名称为"逻辑驱动的多智能体测试生成与自修复系统"；内部证据为：编排 δ=−24.6pp（负贡献）、CEGIR 未接线、主口径逻辑通道零落盘、无当次 repair 证据、真实仓库补丁从未应用。

**建议定位（三选一，按推荐度排序）**：

| 方案 | 名称 | 依据 | 风险 |
|---|---|---|---|
| **A（推荐）** | **"检出优先的测试生成与评估方法论研究平台"** | 项目的真实贡献在测量协议与负结果（§0.5、§11）；`plain_llm_df` 的 44.8% 是真实可复现的方法学发现 | 需放弃"多智能体/逻辑驱动"标签 |
| B | "LLM 测试生成的检出优先协议与政策无关 oracle 度量" | 同时覆盖 detection-first 协议 + MDO（§6.1） | 需先完成 ULT 落数 |
| C（不建议） | 保留原名称，补齐实证 | 需同时完成 CEGIR 接线 + 规约通道落盘 + 编排转正 | 三件事都不确定成功 |

### 12.2 改后的技术架构

```
┌─────────────────────────────────────────────────────────────────┐
│  第 0 层：外部有效性闸门（新增，P0）                              │
│  fail-fast：instance_code 必须 compile() 通过且 ≠ problem_statement│
│  provenance 强制完整；git_dirty 默认拒跑（或记录脏树指纹）        │
├─────────────────────────────────────────────────────────────────┤
│  第 1 层：基准（重构）                                            │
│  主口径 = ULT 3,909（真实 Python，抗污染）→ 降级链：QuixBugs      │
│  合成集（16 模板/26 程序体）= 冒烟与回归专用，禁止作为对外口径     │
│  SWE-bench Lite/Verified = 修复链路端到端验证                     │
├─────────────────────────────────────────────────────────────────┤
│  第 2 层：测量层（升格为一等公民）                                │
│  MDO：MTR（触发）/ MDR（判别）/ CRASH（崩溃）三分解，池下限 ≥29   │
│  政策无关：测试集执行前冻结，判定只看行为差异，不涉及补丁          │
│  统计：以唯一程序体为聚类单元；报告 A12/Cliff's δ 而非仅 p 值     │
├─────────────────────────────────────────────────────────────────┤
│  第 3 层：生成通道（多路可消融，而非单一路径）                    │
│  (a) 检出优先提示协议（plain_llm_df 形态）—— 当前最强臂           │
│  (b) 规约通道：LLM 生成规约 → 白名单 AST 编译 → z3 见证输入       │
│      （目标：spec_compile_rate 中位 0.20 → ≥0.55）                │
│  (c) 编排通道：拓扑作为搜索空间（BOAD 式），非手工固定             │
├─────────────────────────────────────────────────────────────────┤
│  第 4 层：修复通道（验证独立化，P0）                              │
│  验证 oracle 必须独立于生成 oracle：gold 测试套件 / 真实仓库回归   │
│  测试侧错误 → inconclusive（不得判 regression_failed）            │
│  结果行新增 validation_oracle_type ∈ {gold_suite, generated, none}│
├─────────────────────────────────────────────────────────────────┤
│  第 5 层：安全与观测                                              │
│  test-hacking 守卫扩展到测试侧（断言删除/放宽/跳过/吞异常）并转阻断│
│  kernel_sandbox 默认开启（或明确声明默认非安全隔离）               │
│  token 记账断言：禁止静默零；零值行写 token_accounting_status     │
└─────────────────────────────────────────────────────────────────┘
```

### 12.3 推荐目录结构（保持现有 src layout，补充）

```
AITester/
├── src/
│   ├── measurement/          # 【升格】MDO 等政策无关度量（已有 mdo.py）
│   │   ├── mdo.py
│   │   └── clustered_stats.py   # 【新增】聚类稳健统计（唯一程序体为单元）
│   ├── benchmarks/           # 【新增】外部基准适配层
│   │   ├── ult.py            # 已有 src/datasets/dataset_ult.py 迁移
│   │   ├── swebench_harness.py  # 【新增】真实仓库补丁应用 + gold 套件回归
│   │   └── quixbugs.py
│   ├── protocols/            # 【新增】提示协议（检出优先等）独立成层
│   ├── specs/                # 逻辑驱动内核（扩展文法，见 §6.3）
│   ├── graph/                # 编排容器（保持"可消融"定位）
│   └── tools/                # 修复与守卫
├── experiments/              # 拆分 run_benchmark.py（3,401 行 → arm/metrics/cli/report）
├── prereg/                   # 【新增】预注册固化（含聚类口径、主终点、停止规则）
└── artifacts/                # 【新增】机器可读结果工件（JSON），替换纯 .md 报告
```

### 12.4 依赖管理、测试、CI/CD、打包

| 项 | 现状 | 建议 |
|---|---|---|
| 依赖 | `pyproject.toml` + `requirements.txt` + `requirements.lock` 三源，门禁绿 | 保持；`setup.py` 与 `pyproject.toml` **双源**建议收敛为单一 `pyproject` |
| 依赖漏洞 | 项目已接 `pip-audit`（工件入库） | 保持；新增 `bandit` 到必跑门禁（`[tool.bandit]` 已配置但未见 CI 引用） |
| 测试 | 5390 passed / 0 failed；**2 个零断言用例致门禁红** | 修 2 个用例；补**测试侧 hacking 构造**用例 6 类 |
| 类型 | mypy 非严格配置，覆盖 ≈75.8% | 分模块棘轮式启用 `disallow_untyped_defs` |
| 覆盖率 | 行 89% / 分支 83%（**meta_coverage**，非被测代码覆盖） | 保持；在所有报告中强制区分两个 coverage（项目已加口径注释，需扩展到全部文档） |
| CI/CD | 3 workflow + 24 门禁 | 把 `check_zero_assert_tests`、`check_citations --online` 转为**阻断**；新增 provenance 完整性守卫 |
| 打包 | `python -m build` 链路项目自述已取证 | 保持 |
| 部署 | CLI/批量为主，无服务形态 | 若对外定位为"研究平台"，可接受；勿宣称"运行时自愈" |

### 12.5 多智能体系统方案（角色/通信/编排/记忆/工具/冲突/失败恢复/可观测）

| 维度 | 现状（实测） | 建议 |
|---|---|---|
| 角色划分 | Planner / Generator / Executor / Debugger / PatchApplier（LangGraph 节点） | 保留；**明确"可消融容器"定位**，不作为主主张 |
| 通信协议 | 共享 state 字典（`src/graph/state.py` 803 行），无消息契约 | 新增 **state channel 契约测试**（项目已有 `check_state_contract.py`，建议扩展为必跑） |
| 编排策略 | 固定 DAG + 12 开关 | 改为**拓扑搜索**（BOAD 式），或承认手工编排并停止投入 |
| 共识/冲突解决 | `expert_pool` 一次综合 + 文本包含投票 | 要么实现真辩论（多轮 + 收敛判据），要么删除"辩论/共识"表述 |
| 记忆 | `agents_cache.py`（LLM 响应缓存）、RAG（默认关） | **缓存键必须含代码版本指纹**（修复 §3.6b 的逐字节相同问题） |
| 工具调用 | tree_sitter（缺依赖时降级）、code_analyzer、executor | 保持；补 tree_sitter 到 extras 并测降级路径 |
| 预算控制 | `cost_budget.py` + `token_cap_override`（E6 专用）；**默认无上限** | 主实验默认设上限并与单提示臂**预算匹配**（这是"编排是否值得"的关键对照条件） |
| 失败恢复 | `error_classifier` 18 类 + Debugger 循环（≤3 轮） | 保持；停止条件由固定轮数改为**收敛判据或预算** |
| 可观测性 | `tracing.py` + `observability/` + MAST 对齐 | 保持（本项目强项）；新增 `validation_oracle_type`、`token_accounting_status` |

### 12.6 逻辑驱动方案（规格/约束/求解器/覆盖准则/最小化）

| 维度 | 现状（实测） | 建议 |
|---|---|---|
| 规格表达 | pre/post/invariant 三分类；白名单 AST；不支持集合/量词/关系谓词 | 扩展文法（§6.3）；**明确声明支持的是"一阶原子约束"而非"形式化验证"** |
| 约束建模 | 规约由 LLM 从 NL 生成 | 保留；增加**规约自一致性检查**（已有 `check_postcondition_consistency`，需接入主链路） |
| 求解器 | **z3 真调用**（5.1.0 实测） | 保持；把"整体跳过"改为"部分可译则部分求解" |
| 覆盖准则 | 行/分支覆盖 + 自研变异（退出码判据） | 改用 MDO 行为判据；池 ≥29 |
| 测试最小化 | `experiments/test_suite_minimize.py` 存在 | 保持；与 MDO 池下限配合（避免最小化后池不足） |

### 12.7 自修复方案（触发/定位/补丁/验证/回归/回滚/置信度/人工审核）

| 环节 | 现状（实测） | 建议 |
|---|---|---|
| 触发 | `detection_gates` 双门（特异性门 + 红回归门），logic 档开启 | 保持；这两门是项目**最少被讨论但最有价值**的机制 |
| 故障定位 | `fault_localizer` + `fl_spectral`（Ochiai）；⚠️ 称"纯测量"但实际进 prompt | **修正表述**；作为行为开关纳入消融 |
| 补丁生成 | LLM + 多候选（默认关）+ 确定性修复路由 | 保持 |
| 补丁验证 | ⚠️ **重跑自己生成的测试**（非 gold 套件） | **改用 gold 套件 / 仓库既有测试**（P0） |
| 回归 | ⚠️ `patch_rollback.py:189` 仅 `pytest test_path -q` | 改为仓库级回归 |
| 回滚 | 快照 + fail-closed（logic 档） | fail-closed 分类：断言失败 → 回滚；**测试侧错误 → inconclusive** |
| 置信度 | `risk_approval.py` 三因子打分 | 保持；新增"验证 oracle 独立性"因子 |
| 人工审核 | `repair_review_worksheet.py` 生成工作表（E7） | 保持并**实际执行**（项目自述"欠人工比对"） |

### 12.8 里程碑与 KPI（12 个月）

| 阶段 | 时间 | 里程碑 | KPI（判定标准） |
|---|---|---|---|
| **M1 可信度修复** | 1–2 月 | 全部 P0 数据/文档缺陷修复（S2/S3/S4/S6/S7/S8/S9/S10/S11/S23） | 门禁全绿（含 `check_zero_assert_tests`）；`provenance` 100% 完整；`git_dirty=false`；补丁应用成功率 ≥60% |
| **M2 外部有效性** | 3–4 月 | ULT 200 任务标定集跑通 | ULT 报告可复算；`pool_floor_ok` ≥80%；MTR/MDR 首次落数 |
| **M3 度量贡献** | 5–6 月 | MDO on ULT 全量 3,909 + PLT 双轨 | 第三方可用官方 Cosmic-Ray 复算；效应量与聚类 CI 齐备 |
| **M4 逻辑真实化** | 5–8 月 | 规约文法扩展 | `spec_compile_rate` 中位 ≥0.55；**且 MDR +5pp**（否则判定逻辑驱动无因果贡献） |
| **M5 编排判定** | 6–9 月 | 预算匹配下的编排 vs 单提示 | δ ≥ 0 → 保留；**δ < −5pp → 按预注册停止编排路线** |
| **M6 方法论产出** | 9–12 月 | 测量伪影协议论文 | 可迁移协议被第三方复用 |

**KPI 原则**：每个里程碑的 KPI 均为**可独立验证的判定**，并配 **失败判定**（§6 各路径已给）。

---

## 13. 实验、验证与评估计划

### 13.1 主终点体系（重构后）

| 层级 | 指标 | 定义 | 门槛/口径 |
|---|---|---|---|
| **主终点** | **MDR**（判别率） | 断言标记了行为偏差的变异体比例 | 政策无关；池 ≥29；`pool_floor_ok=true` |
| 主终点（并列） | **MTR**（触发率） | 行为发生偏差的变异体比例 | 与 MDR 分开报告（触发≠判别） |
| 安全性终点 | **CRASH** | 崩溃但无断言失败的变异体比例 | 不并入 MDR |
| 次要 | detection_rate | F2P 三段判定 | **仅在有 gold tests 的基准上报告**；ULT 上恒 None |
| 次要 | coverage（被测代码） | 行/分支 | 必须与 meta_coverage 显式区分 |
| 次要 | repair_rate | 补丁正确率 | **必须标注 validation_oracle_type** |
| 成本 | $/task、llm_calls/task | 价目表驱动 | 零记账批次**拒绝输出** |
| 工程 | 补丁应用成功率 | harness 级 | 闸门指标，<60% 则整批作废 |

### 13.2 对照组设置（对照数据必须来自一手来源）

| 对照 | 来源 | 证据等级 | 可比性 |
|---|---|---|---|
| ULT 官方 mutation 40.21% | TOSEM 2026, DOI `10.1145/3805043` | A | ✅ 同基准同任务（需确认是 Pass@1 还是 Pass@k 口径） |
| TestGenEval GPT-4o 35.2% line / 18.8% mutation | ICLR 2025, arXiv:2410.00752 | A | ⚠️ 不同基准（11 仓库文件级），**仅作量级参照** |
| ICST 2026 Plain-LLM 49.95/35.33/33.82 | arXiv:2601.09695v2 | A | ❌ Java、仓库级，**不可对比** |
| CANDOR 0.991/0.970/0.980 | TOSEM 2026, DOI `10.1145/3803418` | A | ❌ HumanEvalJava 方法级，**不可对比** |
| 项目自身 strongest 单提示臂 | 本次实测 `plain_llm_df` | A | ✅ **最重要的对照**（同模型/同温度/同迭代/同 seed） |
| 项目自身退出码口径 mutation_score | 本次实测 | A | ✅ 量化"退出码 vs 行为判据"的差值 |

### 13.3 统计与可复现性要求

| 要求 | 具体规定 |
|---|---|
| 分析单元 | **唯一程序体/函数**（非任务标签）；跨 seed 合并时以簇为单元 |
| 检验 | 配对设计用 McNemar / Wilcoxon；报告**效应量（A12 / Cliff's δ）**，非仅 p 值 |
| 多重比较 | BH-FDR（项目已实现） |
| 预注册 | 主终点/阈值/停止规则**先于数据产生**（项目已有该制度，需扩展到聚类口径） |
| 随机种子 | 至少 3 seed；报告分 seed 波动；**验证 seed 间产出非逐字节相同** |
| 环境 | `git_dirty=false`（或记录脏树指纹）；Python/依赖版本入 provenance；Docker 镜像 digest |
| 数据版本 | ULT commit + manifest 的 SHA256；QuixBugs commit（已记录 `4257f44b`） |
| 机器可读工件 | **所有头条数字必须有 JSON 输出**（当前 repair 39.31% 仅有 .md，属缺陷 S-新） |
| 负面结果 | 入库、不筛选（项目已做到，保持） |

### 13.4 消融设计（现有 + 建议新增）

| 消融 | 状态 | 建议 |
|---|---|---|
| 三臂（aitester / plain_llm / plain_llm_df） | ✅ 已有，公平（同模型/温度/迭代/seed） | **新增预算匹配臂**（token cap + 迭代数对齐）——这是"编排是否值得"的关键对照 |
| 检出优先双门（特异性/红回归） | ✅ 已有（logic 档） | 在 ULT 上重测 |
| 规约通道（`SPEC_IR_DSL_ENABLE`） | ✅ 已有（默认关） | 配合文法扩展重测，**以 MDR 为终点而非编译率** |
| MDO vs 退出码口径 | ⚠️ 部分（`pilot_mdo_*` 小样本） | 扩到 ULT 全量 |
| 跨文件修复（R27） | ✅ 已有（默认关） | 在真实仓库上验证（当前仅合成） |
| test-hacking 阻断档 | ❌ 未转正 | A/B 后转正（§6、S4） |
| 局部编辑通道（R4） | ✅ 已有（A/B 已完成，结论：函数级约束在单函数数据集上空洞） | 在真实多函数文件上重测 |

---

## 14. 风险、伦理与合规

### 14.1 技术风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| ULT 数据许可不明（上游 The Stack v2 gated + `license: other`） | 高 | 无法打包/发布数据 | 用户本地拉取 + 显式接受条款 + 逐文件许可元数据（项目 `docs/design/ult_bridge_plan.md` §4.1 已设计） |
| MDR 与 mutation_score 高相关（ρ>0.95）→ 无增量 | 中 | 路径 A1 失效 | **先做 200 任务标定验证**（§6.1 失败判定） |
| 编排搜索后 δ 仍为负 | 中高 | 路径 C 失效 | 预注册停止规则，及时转向 A1/A2 |
| 真实仓库 harness 修复成本超预期 | 中 | M2 延期 | 从 Lite 20 例小步验证，再放量 |
| LLM 缓存导致批次非独立（已发生） | 高 | 复现性失效 | 缓存键加代码版本指纹（S12） |
| 合成集结论被误用为对外主张 | 中 | 学术声誉 | 全部材料标注"仅内部"，S1 执行 |

### 14.2 数据与伦理风险

| 项 | 现状 | 判定 |
|---|---|---|
| 人类受试者 | 无 | 不适用 |
| 隐私 / PII | 无个人数据；`rag_data/` 与 `data/` 为公开数据集 | 合规 |
| 数据许可 | QuixBugs MIT（已核实）；TestGenEval **CC BY-NC 4.0**（非商用）；BugsInPy **无 SPDX** | ⚠️ **已登记为"非清洁许可三选一门槛"**（项目加分）；**ULT 许可未澄清**（§14.1） |
| 代码执行安全 | 默认 `use_docker=False`、`kernel_sandbox=False`、venv 子进程 | ⚠️ **默认非安全隔离**；对外不得表述为"沙箱执行" |
| Secrets | `.env` 从未入库；三层脱敏；第四条链路未脱敏（S28） | 基本合规 |
| 滥用风险 | 系统生成代码补丁并自动应用 | ⚠️ 建议默认开启 `kernel_sandbox` + 补丁白名单，或明确声明"研究用途" |
| 学术诚信 | 引用 8/13 完全属实、0 伪造；负面结果入库；三次测量伪影自曝 | ✅ **显著优于平均** |

### 14.3 合规与监管

本项目为软件工程研究，不涉及医疗器械/金融/自动驾驶等受监管领域。**唯一需注意的是**：若对外发布"自动修复代码"能力，需明确免责声明与适用边界（当前无真实仓库成功案例，实际风险极低）。

### 14.4 Plan B（若关键路径失败）

| 失败情形 | Plan B |
|---|---|
| ULT 无法获取/许可不可接受 | 退到 QuixBugs + BugsInPy（已有），并如实声明基准局限；MDO 仍可在其上落数 |
| MDR 无增量（ρ>0.95） | 转向"测量伪影协议"（路径 D）作为主贡献，放弃度量创新主张 |
| 真实仓库 harness 修不通 | 彻底放弃"修复"主张，收窄为"测试生成 + 检出测量" |
| 编排搜索无果 | 停止编排投入，把最强臂（plain_llm_df 形态）作为唯一生成通道 |
| 规约通道无因果贡献 | 承认属性测试是工程选择，删除"逻辑驱动"标签 |

---

## 15. 待澄清问题

> 按任务书要求：**缺失信息必须列为待澄清，不得用假设填充。**

| # | 问题 | 为何重要 | 建议澄清对象 |
|---|---|---|---|
| **Q1** | 项目对外主张的最终版本是什么？（"逻辑驱动多智能体测试生成与自修复" vs `ADR-0016` 的 detection-first 口径） | 决定本报告全部建议的取舍 | 项目负责人 |
| **Q2** | 是否有**当次运行**（而非离线重放）的 repair 非零证据？近半年是否有新实验批次计划？ | repair 39.31% 虽经独立重放证实，但无当次证据 | 项目负责人 |
| **Q3** | SWE-bench enrichment 数据是否还能获取？`~/swe_repos` 克隆是否仍在？ | 决定 S2 的成本与可行性 | 运行环境 |
| **Q4** | ULT 数据许可如何澄清？是否接受"用户本地拉取"模式？ | 决定 S22 是否可行 | 项目负责人/法务 |
| **Q5** | `spec_oracle_exec` 通道为何在 7 份主批次全部零落盘？（未执行 vs 未记录） | 决定"逻辑驱动"是**能力问题**还是**接线问题**——两者的修复成本差一个数量级 | 代码作者 |
| **Q6** | `test_hacking_*` 字段为何在头条批次完全不存在？ | 决定该守卫是"未产数"还是"从未运行" | 代码作者 |
| **Q7** | 是否需要我继续核实 arXiv:2609.09315（Hamidi 等，「触发率 32–39% 而检出率仅 1–2%」）的一手结论？ | 影响 R12 的最终判定（**R5 的 arXiv:2609.24341 已于本次补充轮核实完毕**，见 §11 附） | 项目负责人 |
| **Q8** | 项目的目标产出形态是什么？（论文 / 开源工具 / 内部平台） | 决定"测量方法论"（路径 D）与"性能提升"（路径 A）的优先级 | 项目负责人 |
| **Q9** | 是否接受"放弃多智能体主张、转向度量贡献"的方案？ | §12.1 定位重构的前提 | 项目负责人 |
| **Q10** | 合成数据集是否曾用于论文/对外材料？若已用于某处，需评估撤回范围 | 影响学术诚信风险等级 | 项目负责人 |

---

## 16. 参考来源（区分一手/二手，标注证据等级）

### 16.1 一手来源（本次亲自访问，A/B 级）

**前沿基准与系统**（完整 URL 清单见 `_independent_audit/WS1_frontier_primary_sources.md` §10）

| # | 来源 | 类型 | 等级 |
|---|---|---|---|
| 1 | Pizzorno & Berger. *CoverUp*. **FSE 2025**. DOI `10.1145/3729398`；arXiv:2403.16218 | 会议论文 + 预印本 | A |
| 2 | Sapozhnikov et al. *TestSpark*. **ICSE-Companion 2024**, pp.30–34 | 会议论文 | A（载体） |
| 3 | *HITS*. arXiv:2408.11324 | 预印本 | A |
| 4 | *Code-Aware Prompting (SymPrompt)*. **ICSE 2024/PACMSE**. DOI `10.1145/3643769`；arXiv:2402.00097 | 会议论文 | A |
| 5 | Wang, Xu, Briand, Liu. *MUTGEN*. **IEEE TSE 52(5):1657–1671, 2026**. DOI `10.1109/tse.2026.3682975`；arXiv:2506.02954 | 期刊 | A |
| 6 | Xu, Wang, Briand, Liu. *CANDOR*. **TOSEM 2026**. DOI `10.1145/3803418`；arXiv:2506.02943 | 期刊 | A |
| 7 | Shang, Zhang, Zhan, Huang, Fang, Chen. *TestAgent*. **FSE Companion '26**, pp.242–246. DOI `10.1145/3803437.3806428` | 会议短文 | A/B |
| 8 | Konstantinou, Degiovanni, Papadakis. **ICST 2026**. arXiv:2601.09695v2 | 会议论文 + 预印本 | A |
| 9 | Jain, Synnaeve, Rozière. *TestGenEval*. **ICLR 2025**. arXiv:2410.00752 | 会议论文 | A |
| 10 | Huang, Zhang, Harman, Zhang, Du, Ng. *ULT/UnLeakedTestbench*. **TOSEM 2026**. DOI `10.1145/3805043`；arXiv:2508.00408 | 期刊 + 预印本 | A |
| 11 | Mündler, Müller, He, Vechev. *SWT-Bench*. **NeurIPS 2024**. DOI `10.52202/079017-2601` | 会议论文 | A |
| 12 | *BOAD*. **ICLR 2026**. arXiv:2512.23631（IBM Research 官方页确认） | 会议论文 | A |
| 13 | Men, Tong, Zuo, Lu. *FTDI*. **Expert Systems with Applications**. DOI `10.1016/j.eswa.2026.134164` | 期刊 | A |
| 14 | Cruz, C. *VIGIL: A Reflective Runtime for Self-Healing Agents*. arXiv:2512.07094 | 预印本（**无数值**） | A（机制）/ D（数值） |
| 15 | Or, B. *MTTR-A*. arXiv:2511.20663 | 预印本（指标定义） | A |
| 16 | *TOGLL*. **ICSE 2025** pp.1475–1487. DOI `10.1109/ICSE55347.2025.00098` | 会议论文 | A |
| 17 | *LM2Alloy*. arXiv:2607.18555 | 预印本（弱载体） | A |
| 18 | *PGS*. arXiv:2506.18315 | 预印本 | A |
| 19 | Cadar, Dunbar, Engler. *KLEE*. **USENIX OSDI 2008** | 会议论文 | A |
| 20 | Zhao, Zhou, Cohen. **ISSTA 2026 Distinguished Paper**. DOI `10.1145/3832093` | 会议论文 | A |

**项目内部一手工件（本报告数据来源）**

| # | 工件 | 用途 |
|---|---|---|
| 21 | `experiments/results/main_batch/benchmark_synthetic_20261006_{140906,151907,164357}.json` | 头条三臂指标（seed 42/43/44） |
| 22 | `experiments/results/main_batch/benchmark_synthetic_20261007_*.json` | 记账缺陷与同 seed 重放证据 |
| 23 | `experiments/results/raw/sqlfluff__*/{aitester,plain_llm,single_agent}.json` | 真实仓库补丁失败证据 |
| 24 | `experiments/results/swe_bench_lite_20/benchmark_swe_bench_20260818_113525.json` | SWE-bench 挂具失败证据 |
| 25 | `experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/{aitester,plain_llm_df}.json` | QuixBugs 45.9% vs 83.8% |
| 26 | `experiments/results/main_batch/SHA256SUMS`（2,029 条） | 工件完整性（我对 20 条抽样，20/20 通过） |
| 27 | `experiments/price_table.json` | 成本复算（agnes-3.0-flash 两项为 `null`，无官方来源） |
| 28 | 源码：`src/specs/*`、`src/graph/*`、`src/tools/*`、`src/measurement/mdo.py`、`src/datasets/synthetic_dataset.py` | 声称 vs 实现核实（逐条 file:line） |
| 29 | 门禁实跑：`scripts/gates/{check_zero_assert_tests,check_baseline_numbers,check_citations,check_artifacts_tracked,check_bilingual_docs,check_env_budget,check_lock_sync}.py` | 工程化状态 |
| 30 | 实测命令：`pytest tests/ -q`（5390/3/1）、`SyntheticDataset(task_count=87,seed=42)`、`du -sh`、`git log --all -- .env` | 独立实测 |

### 16.2 二手来源（本报告未用于支撑结论，仅记录）

| 来源 | 说明 | 等级 |
|---|---|---|
| IEEE Xplore `document/11655121`（Radaideh & Corriveau） | 存在性经标题比对确认，**四个 mutation 数值本次无法取得一手载体**（HTTP 202 空体 / ACM 403 / S2 429） | B（存在性）/ **D（数值）** |
| OpenAI *Why we no longer evaluate SWE-bench Verified* | 页面存在性；正文 403 | B/D |
| 项目内 6 份根目录审查报告 + `audit_2026/` + `review_2026/` + `.private/review/` | **本报告的复核对象**，不作事实来源 | 待验证 |
| `review_2026/E3_four_channel.json` 等既有分析产物 | 项目自产中间产物，本报告只用于交叉比对 | 待验证 |

### 16.3 共识 / 争议 / 假设 / 推测（明确区分）

| 类别 | 内容 |
|---|---|
| **共识**（多份独立一手来源同向） | ① 覆盖率在方法级小型程序上已近饱和；② 高覆盖 ≠ 高检出（MUTGEN 4% 论断、LM2Alloy 68% 漏检、Zhao ISSTA'26 限定性结论）；③ 真实世界 Python 代码上的覆盖/变异远低于 HumanEvalJava 系 |
| **争议** | ① 多智能体/工具特定编排是否有效——ICST 2026 复现（A）给出否定，CANDOR（A）给出肯定，**两者基准与语言不同，项目须并列呈现**（项目 `README.md:12-34` 已做到）；② 变异测试相对结构覆盖的增益大小（Zhao 等指出对 LLM 故障仅边际优） |
| **假设**（未验证） | ① "SMT 见证输入优于 LLM 猜测边界输入"——项目核心原创点，**目前无对照实验**；② "编排拓扑搜索能转正 δ"——仅有 BOAD 的跨任务类比 |
| **推测**（明确标注 E 级） | ① 项目请求数误述疑似引用论文 v1 稿（`WS1` C6）；② `README.md:28` 的数值差异可能源于版本漂移；③ 记账整臂为零的机制推测为缓存命中路径未记账（需受控复跑 1 任务打印 `get_usage().as_dict()` 才能定论） |
| **不确定 / 不可验证** | 见 §3.8 的 U1–U7 与 `WS1` §8 的 D1–D25 |

---

## 附录：本报告的独立验证资产

| 资产 | 路径 | 说明 |
|---|---|---|
| 前沿一手来源重建 | `_independent_audit/WS1_frontier_primary_sources.md`（486 行 / 73 KB） | §1 引用核实表（13 条）、§2–§6 各子方向前沿表、§7 冲突与交叉验证、§8 D 级清单（25 项）、§10 URL 清单 |
| 指标重算脚本与结果 | `_independent_audit/ws2_recompute.py`（895 行）、`_independent_audit/WS2_recompute_results.md` | 一键复现（`python _independent_audit/ws2_recompute.py`）；只读原始工件，脚本内不读任何 `.md` |
| 代码与领域审计 | `_independent_audit/WS3_code_domain_audit.md`（185 行） | §A 工程化 24 行、§B 领域 21 行、§C 声称 vs 实现 20 条、§D 命令、§E 不确定项 |

**本报告未修改仓库任何源码或配置**；仅新增 `_independent_audit/` 与本文档。

---

> **报告结束**。所有结论均标注证据等级（A/B/C/D/E）；所有不可验证项已显式列为"无法验证"或"待澄清"。本报告不提供"超越前沿"的确定性结论——因为在当前实验条件下，**这样的结论无法被任何证据支撑**。
