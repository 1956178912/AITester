# T-C 2025–2026 前沿基线一手来源重建（独立审计）

- **负责人**：frontier-scout（独立评审团队 T-C）
- **检索日期**：2026-10-11（Asia/Shanghai）
- **工作目录**：`/Users/wangchenyu/Workspace/AITester`
- **产出范围**：仅本文件。未修改项目任何其它文件。
- **纪律声明**：本文件**不采信**项目内文档（`README.md` / `BASELINE.yaml` / `review_2026/R1-R3` / `REVIEW_2026_FRONTIER.md`）中的任何前沿数字。下表中每一个数值均来自本节说明的一手端点，并逐条标注证据等级与交叉验证情况。**凡未取得一手来源者一律标注"未取得一手来源"，不做任何数值推测。**

---

## 0. 检索方法与可用性说明（含失败端点）

### 0.1 实际使用的端点（全部为程序化直接读取，非记忆）

| 端点 | 用途 | 状态 |
|---|---|---|
| `https://export.arxiv.org/api/query?id_list=<id>` | 核验 arXiv id ↔ 标题/作者/日期/comment/摘要 | ✅ 可用（需重试，偶发超时） |
| `https://export.arxiv.org/api/query?search_query=ti:"X"` / `all:"X"` | 存在性检索 | ✅ 可用 |
| `https://raw.githubusercontent.com/swe-bench/experiments/main/evaluation/{verified,lite}/<entry>/…` | **SWE-bench 官方榜单条目**：`metadata.yaml` / `results/results.json` / `per_instance_details.json` | ✅ 可用（无速率限制） |
| `https://api.github.com/repos/swe-bench/experiments/contents/...` | 榜单条目目录枚举 | ⚠️ 未认证 60 req/h，**已耗尽并被 429**；改用 `raw.githubusercontent.com` + `git sparse-checkout` 绕过 |
| `git clone --filter=blob:none --sparse https://github.com/swe-bench/experiments` | 枚举 `evaluation/lite` 全部 84 个条目 | ✅ 可用 |
| `https://api.crossref.org/works/<DOI>` | DOI → 标题/作者/卷期页/摘要 | ✅ 可用 |
| `https://api.openalex.org/works?search=…` | 存在性交叉验证 | ✅ 可用 |
| `https://doi.org/…`、`https://www.swebench.com/submit.html` | 官方提交规则 | ✅ 可用 |

### 0.2 失败/受限端点（影响覆盖度，如实列出）

| 端点 | 失败情况 | 影响 |
|---|---|---|
| `https://dblp.org/search/publ/api` | 被 **Anubis 反爬**拦截（返回 "Making sure you're not a bot!" HTML），加 UA 亦无效 | **DBLP 完全未用上**；改用 Crossref + OpenAlex + arXiv 三方替代 |
| `https://api.semanticscholar.org/graph/v1/paper/search` | HTTP **429 Too Many Requests** | Semantic Scholar 未用上 |
| `https://www.swebench.com/verified.html` | web_fetch 超时 / curl 连接超时 | 榜单表格未从站点 HTML 读到；**改为直接读官方榜单仓库的逐条结果文件**（更一手） |
| `https://huggingface.co/` | HTTP 502 | 未使用（不影响本任务） |
| `web_fetch` 工具对 `github.com` / `raw.githubusercontent.com` | 报 "resolves to a non-public IP address"（DNS 限制） | 改用 `bash` + `curl`（网络可用），已绕过 |

### 0.3 证据等级定义（本文件统一口径）

- **A**＝一手可逐条复算：数值直接取自官方榜单文件（`results.json` / 逐实例 `resolved`）或会议 DOI 的 Crossref 结构化元数据。
- **B**＝一手原文可打开，但仅核到 arXiv 官方摘要中的数值，**未逐条核对正文表格与实验条件**。
- **C**＝二手转述（第三方页面 / 搜索片段 / 项目文档），无可打开的原文。
- **D**＝不可验证 / 检索无命中，**疑似不存在**。
- **E**＝推测（本文件不使用 E 级数值）。

### 0.4 关键换算与口径（避免把榜单率算错）

- SWE-bench Verified 分母 **500**；SWE-bench Lite 分母 **300**。
- 官方 `metadata.yaml` 的 `info.resolved` 字段即官方 resolve rate（百分数），与逐实例统计一致。
- ⚠️ **本审计发现的真实口径陷阱（A 级证据）**：条目 `20260901_mini-v2.4.2_gemini-3-5-flash` 的 `per_instance_details.json` **只有 441 条**实例（359 resolved / 82 not），若用 441 作分母会得到 **81.4%**，而官方 `metadata.yaml` 与 500 分母给出的是 **71.8%（=359/500）**。任何"用逐实例文件求和再除以文件行数"的复算脚本都会**高估 9.6pp**。本项目若存在此类复算，必须统一用 500/300 分母。

---

## 表 1 ｜ LLM 测试生成（覆盖率 / 变异得分 / 缺陷检测）

| 方法/系统 | 指标 | 指标值 | 基准 | 一手来源 | 年份 | venue | 等级 | 交叉验证 |
|---|---|---|---|---|---|---|---|---|
| **TestGenEval** | 平均覆盖率（最佳模型 GPT-4o） | **35.2%** | TestGenEval（68,647 tests / 1,210 file pairs / 11 Python 仓库） | https://arxiv.org/abs/2410.00752 | 2024-10 | arXiv 预印本（Meta） | B | ① 原文摘要；② TestForge 论文以 TestGenEval 为评测基准并说明其构成（arXiv:2503.14713） |
| **TestForge** | pass@1 / line coverage / mutation score | **84.3% / 44.4% / 33.8%**；成本 $0.63/file | TestGenEval | https://arxiv.org/abs/2503.14713 | 2025-03 | arXiv 预印本 | B | ① 原文摘要；② 与 TestGenEval 的 35.2% 覆盖率口径不同（pass@1 vs 平均覆盖率），**二者不可直接比较**——本表并列仅为说明同基准不同指标 |
| **CoverUp** | per-module median line+branch coverage | **80%**（对照 CodaMosa **47%**） | 挑战性 Python 模块基准 | https://arxiv.org/abs/2403.16218 | 2024-03（v4 2025-05） | **FSE 2025**（comment: to appear at FSE'25） | B | ① 原文摘要；② 第三方复现研究 arXiv:2601.09695 将其列为被复现的 4 个 SOTA 工具之一 |
| **CoverUp** | overall line+branch coverage | **89%**（对照 MuTAP **77%**） | 同上 | https://arxiv.org/abs/2403.16218 | 同上 | FSE 2025 | B | 同上 |
| **SymPrompt** | 正确测试数 / 相对覆盖率提升 | **×5** 正确测试；CodeGen2 相对覆盖率 **+26%**；GPT-4 覆盖率 **>2×**（vs baseline prompting） | 开源 Python 项目挑战性方法 | https://arxiv.org/abs/2402.00097 | 2024-01 | arXiv 预印本 | B | ① 原文摘要；② arXiv 全库检索 `all:"SymPrompt"` 仅 3 条命中，其中 2601.09695 明确称"复现了 SymPrompt" |
| **HITS** | line / branch coverage（相对 SOTA 与 EvoSuite） | 摘要**未给数值**（仅"significantly outperforms"） | 复杂 focal methods 数据集 | https://arxiv.org/abs/2408.11324 | 2024-08 | **ASE 2024**（comment） | B | ① 原文摘要无数字；② 被 arXiv:2601.09695 列为被复现工具。**数值未取得一手来源** |
| **ChatUniTest** | line coverage vs TestSpark / EvoSuite | **在半数项目上最优**（摘要未给具体百分数） | 自建项目集 | https://arxiv.org/abs/2305.04764 | 2023-05（v2 2024-05） | **FSE 2024 Demo**（comment） | B | ① 原文摘要；② 代码库 github.com/ZJU-ACES-ISE/ChatUniTest（摘要中给出）。**具体覆盖率数值未取得一手来源** |
| **TestSpark** | 工具型论文，摘要**未给覆盖/变异数值** | 未取得一手来源 | — | https://arxiv.org/abs/2401.06580 | 2024-01 | arXiv 预印本（JetBrains Research） | B | 被 arXiv:2601.09695 列为被复现工具 |
| **TestPilot** | median statement / branch coverage | **70.2% / 52.8%**（对照 Nessie 51.3% / 25.6%） | **25 个 npm 包、1,684 个 JS API 函数** | https://arxiv.org/abs/2302.06527 | 2023-02（v4 2023-12） | arXiv 预印本（TOSEM 系工作） | B | ① 原文摘要；② OpenAlex 检索确认存在。⚠️ **口径警告：TestPilot 是 JavaScript/npm 工具，"LLM 单元测试生成"若在 Java 语境引用 TestPilot，属于基准错配** |
| **AID → 已更名 TrickCatcher** | recall / precision / F1（相对 SOTA 基线倍数） | **1.80× / 2.65× / 1.66×** | TrickyBugs + EvalPlus（366 人工 + 151 AI 生成 plausible programs） | https://arxiv.org/abs/2404.10304 | v1 2024-04（AID）/ v2 2025-05（TrickCatcher） | **ACL 2025 Main**（comment，v2） | A（v1/v2 更名事实）+ B（数值来自摘要） | ① v1 摘要明写 "this paper proposes AID"；② v2 摘要明写 "we propose TrickCatcher"。**这是同一个 arXiv id 的更名，`ti:"AID"` 检索因此 0 命中**，属可复现的检索陷阱 |
| **ULT (UnLeakedTestbench)** | 12 模型均值 accuracy / statement / branch / mutation | **41.32% / 45.10% / 30.22% / 40.21%** | ULT（**3,909** 个真实 Python 函数级任务，抗泄漏构造） | https://arxiv.org/abs/2508.00408 | 2025-08 | arXiv 预印本（under review） | B | ① 原文摘要给出全部四个数值；② arXiv 全库 `all:"UnLeakedTestbench"` 命中该文 + arXiv:2608.24473（Ockhamareto）引用 ULT |
| **PLT (PreLeakedTestbench)** | 同上（泄漏对照臂） | **47.07% / 55.13% / 40.07% / 50.80%** | PLT（ULT 的泄漏配对基准） | https://arxiv.org/abs/2508.00408 | 2025-08 | arXiv 预印本 | B | 同上。**泄漏使 branch coverage 膨胀 +9.85pp（40.07→30.22 的反向差），是"记忆 vs 推理"对照设计的直接证据** |
| **TESTEVAL（对照基准）** | 同上 | **91.79% / 92.18% / 82.04% / 49.69%** | TESTEVAL（210 个 LeetCode Python 程序） | https://arxiv.org/abs/2406.04531（数值出自 2508.00408 同表） | 2024-06（v2 2025-02） | **NAACL 2025 Findings**（comment） | B | ① ULT 原文摘要并列给出 TESTEVAL 数值；② TESTEVAL 自身 arXiv 记录存在（210 程序、3 任务）。⚠️ TESTEVAL 是 LeetCode 题 → 与 ULT 的高复杂度真实函数**不可直接横比** |
| **CANDOR** | oracle correctness vs SOTA fine-tuning 基线 TOGLL | **≥ +21.1 pp**；覆盖率与 EvoSuite 相当，**mutation score 明显更优** | Java 单元测试（多智能体 + panel discussion 共识） | https://arxiv.org/abs/2506.02943 | 2025-06（v7 2026-03） | arXiv 预印本（**venue 未在 arXiv comment 中给出；项目文档称 TOSEM 2026，本次未取得一手 venue 证据**） | B（数值）/ D（venue） | ① 原文摘要；② TOGLL 原文 https://arxiv.org/abs/2405.03786 独立存在，构成对照锚点 |
| **TOGLL** | 正确 assertion oracle / exception oracle / 独有 bug 数 | **3.8× / 4.9×** 于 SOTA 神经方法；能发现 **1,023** 个 EvoSuite 无法发现的 bug | SF110 微调 + 25 个大型 Java 项目 | https://arxiv.org/abs/2405.03786 | 2024-05（v2 2024-12） | arXiv 预印本 | B | ① 原文摘要；② CANDOR 摘要独立引用 TOGLL 为 SOTA 基线 |
| **TestAgent** | execution rate / line cov / branch cov / mutation score | **97.46% / 92.34% / 90.24% / 83.69%** | 6 个 Java 项目 | https://arxiv.org/abs/2607.09101 | 2026-07 | arXiv 预印本 | B | ① 原文摘要；② `ti:"TestAgent" AND cat:cs.SE` 仅 1 条命中，无歧义。⚠️ 6 个项目样本量极小 |
| **AdverTest**（对抗式 test vs mutant 智能体） | fault detection rate 提升 | **+8.56%** vs 最强 LLM 基线；**+63.30%** vs EvoSuite；同时提升 line/branch coverage | **Defects4J**（Python 11/12，据 Lead 独立核验） | https://arxiv.org/abs/2602.08146 | 2026-02（v3 2026-08） | **ISSTA 2026**（DOI `10.1145/3832122`，由 Lead 独立核验） | B（数值）+ A（DOI 由 Lead 核验） | ① 原文摘要；② Lead 独立核验 DOI ← **跨成员交叉验证成立** |
| **纯提示基线复现研究（反例）** | plain LLM 相对 4 个 SOTA 工具的提升 | line **+17.72%** / branch **+19.80%** / mutation **+20.92%**；plain LLM 绝对值为 49.95 / 35.33 / 33.82 | **393 类 / 3,657 方法** | https://arxiv.org/abs/2601.09695 | 2026-01（v2 2026-07） | **ICST 2026**（DOI `10.1109/icst69053.2026.00040`，由 Lead 独立核验） | B（数值）+ A（DOI 由 Lead 核验） | ① 原文摘要明确列出被复现的 4 个工具：**HITS、SymPrompt、TestSpark、CoverUp**；② Lead 独立核验。**这是本方向最重要的反例：表 1 中 HITS/SymPrompt/TestSpark/CoverUp 的原始增益，在换用新一代 LLM + 等强提示后可能被纯提示基线反超** |
| **METAMON** | 文档-行为不一致分类 precision / recall | **0.72 / 0.48** | 9,482 组 code-doc 对，来自 Defects4J v2.0.1 的 5 个开源项目 | https://arxiv.org/abs/2502.02794 | 2025-02 | **LLM4Code 2025**（comment） | B | ① 原文摘要；② **关键更正**：`arXiv:2502.02794` 是 **METAMON**，**不是 TestGenEval**。TestGenEval 的真实 id 是 **arXiv:2410.00752**（见本表第 1 行）。任务简报中"TestGenEval（arXiv 2502.02794 等）"这一映射**经一手核验为错误** |

**表 1 小结（覆盖率/变异得分的"真实分布"）**
- 在**抗泄漏、高复杂度、真实函数级**基准上，LLM 的覆盖率是 **30–45% 量级**（ULT: statement 45.10% / branch 30.22%），变异得分 **~40%**（ULT: 40.21%）。
- 在 **LeetCode 式简单程序**上同一批模型可到 **92% statement / 82% branch**（TESTEVAL）。
- 在 **TestGenEval**（真实仓库、从零写测试）上最佳模型平均覆盖率仅 **35.2%**。
- 结论：**"LLM 单元测试覆盖率"这一指标在 30%–92% 之间浮动，几乎完全由基准难度与泄漏程度决定，不存在一个可跨论文横比的"前沿覆盖率基线"**。任何把不同基准的覆盖率数值并列成"提升"的表述都不可比。

---

## 表 2 ｜ 多智能体 / 程序修复（agentic vs agentless）

### 2A. 官方榜单口径（A 级：直接读取官方结果文件）

| 条目（官方目录名） | 系统 + 模型 | 指标 | 值（官方 `resolved`） | 基准 | 一手来源 | 等级 |
|---|---|---|---|---|---|---|
| `20251215_livesweagent_claude-opus-4-5` | live-SWE-agent + Claude 4.5 Opus (medium) | resolve rate | **396/500 = 79.2%** | SWE-bench **Verified** | `…/evaluation/verified/20251215_livesweagent_claude-opus-4-5/results/results.json` | A |
| `20251205_sonar-foundation-agent_claude-opus-4-5` | Sonar Foundation Agent + Claude 4.5 Opus | resolve rate | **396/500 = 79.2%** | Verified | 同仓库对应条目 | A |
| `20250928_trae_doubao_seed_code` | TRAE + Doubao-Seed-Code | resolve rate | **394/500 = 78.8%** | Verified | 同上 | A |
| `20251127_openhands_claude-opus-4-5` | OpenHands + Claude Opus 4.5 | resolve rate | **388/500 = 77.6%** | Verified | 同上 | A |
| `20251120_livesweagent_gemini-3-pro-preview` | live-SWE-agent + Gemini 3 Pro Preview | resolve rate | **387/500 = 77.4%** | Verified | 同上 | A |
| `20260807…`→`20250807_openhands_gpt5` | OpenHands + GPT-5 | resolve rate | **359/500 = 71.8%** | Verified | 同上 | A |
| `20260901_mini-v2.4.2_gemini-3-5-flash` | mini-SWE-agent v2.4.2 + Gemini 3.5 Flash | resolve rate | **71.8%**（官方 metadata；359/500）**最新条目** | Verified | `…/metadata.yaml`（`resolved: 71.8`） | A |
| `20250611_moatless_claude-4-sonnet-20250514` | Moatless Tools + Claude 4 Sonnet | resolve rate | **354/500 = 70.8%** | Verified | 同上 | A |
| `20250519_trae` | TRAE | resolve rate | **353/500 = 70.6%** | Verified | 同上 | A |
| `20241029_OpenHands-CodeAct-2.1-sonnet-20241022` | OpenHands + CodeAct v2.1 | resolve rate | **265/500 = 53.0%** | Verified | 同上 | A |
| `20241202_agentless-1.5_claude-3.5-sonnet-20241022` | Agentless-1.5 + Claude-3.5 Sonnet | resolve rate | **254/500 = 50.8%** | Verified | 同上 | A |
| `20250226_swerl_llama3_70b` | SWE-RL (Llama3-SWE-RL-70B + Agentless Mini) | resolve rate | **206/500 = 41.2%** | Verified | 同上 | A |
| `20241028_agentless-1.5_gpt4o` | Agentless-1.5 + GPT 4o | resolve rate | **194/500 = 38.8%** | Verified | 同上 | A |
| `20240628_autocoderover-v20240620` | AutoCodeRover (v20240620) + GPT 4o | resolve rate | **192/500 = 38.4%** | Verified | 同上 | A |
| `20240612_MASAI_gpt4o` | MASAI + GPT 4o | resolve rate | **163/500 = 32.6%** | Verified | 同上 | A |

**Lite 榜单（官方 300 分母，A 级）**

| 条目 | 系统 + 模型 | 值 | 一手来源 | 等级 |
|---|---|---|---|---|
| `20250625_ExpeRepair-v1_claude-4-sonnet-20250514` | ExpeRepair-v1.0 + Claude 4 Sonnet | **181/300 = 60.3%（Lite 榜首）** | `…/evaluation/lite/…/results/results.json` | A |
| `20250425_Refact_Agent` | Refact.ai Agent | **180/300 = 60.0%** | 同上 | A |
| `20250906_KGCompass_claude-4-sonnet-20250514` | KGCompass + Claude 4 Sonnet | **175/300 = 58.3%** | 同上 | A |
| `20250526_sweagent_claude-4-sonnet-20250514` | SWE-agent + Claude 4 Sonnet | **170/300 = 56.7%** | 同上 | A |
| `20250114_Isoform` | Isoform | **165/300 = 55.0%** | 同上 | A |
| `20241025_OpenHands-CodeAct-2.1-sonnet-20241022` | OpenHands + CodeAct v2.1 | **125/300 = 41.7%** | 同上 | A |
| `20241202_agentless-1.5_claude-3.5-sonnet-20241022` | Agentless-1.5 + Claude-3.5 Sonnet | **122/300 = 40.7%** | 同上 | A |
| `20250114_moatless_claude-3.5-sonnet-20241022` | Moatless Tools + Claude 3.5 Sonnet | **117/300 = 39.0%** | 同上 | A |
| `20250214_agentless_lite_o3_mini` | Agentless Lite + O3 Mini | **97/300 = 32.3%** | 同上 | A |
| `20241028_agentless-1.5_gpt4o` | Agentless-1.5 + GPT 4o | **96/300 = 32.0%** | 同上 | A |
| `20240621_autocoderover-v20240620` | AutoCodeRover (v20240620) + GPT 4o | **92/300 = 30.7%** | 同上 | A |
| `20240630_agentless_gpt4o` | Agentless + GPT 4o | **82/300 = 27.3%** | 同上 | A |
| `20240530_autocoderover-v20240408` | AutoCodeRover (v20240408) + GPT 4 | **57/300 = 19.0%** | 同上 | A |
| `20240402_sweagent_gpt4` | SWE-agent + GPT 4 (1106) | **54/300 = 18.0%** | 同上 | A |

> **榜单状态（A 级一手证据）**
> 1. **Lite 的最后一条官方提交是 `20250911_isea_...`（2025-09-11）**，此后无新条目 → Lite 事实上已停更，不再是活跃竞技场。
> 2. **Verified 仍有新条目**，最新为 `20260901_mini-v2.4.2_gemini-3-5-flash`（2026-09-01）。
> 3. **提交规则重大变更（一手 README 原文）**：`swe-bench/experiments` README 载明 **[11/18/2025] SWE-bench Verified 与 Multilingual 仅接受学术团队/研究机构、方法开源、且有同行评审论文的提交**；明确举例"仍合格：OpenHands、SWE-RL、FrogBoss、AutoCodeRover"，"不再合格：Augment Code、Solver AI、Honeycomb.sh"。Multimodal 榜单不受限。来源：`https://raw.githubusercontent.com/swe-bench/experiments/main/README.md`。
> 4. 官方仓库要求提交者提供**自有公开制品仓库**（`assets.repo`），并提供 `swebench submit verify` 可**从记录的执行输出重新评分**（本仓库校验路径），即榜单结果具备可复算性。

### 2B. 论文自报数值（B 级：arXiv 官方摘要）

| 方法 | 指标 | 值 | 基准 | 一手来源 | 年份 | venue | 等级 | 交叉验证 |
|---|---|---|---|---|---|---|---|---|
| **Agentless** | 最高性能 / 修复数 / 成本 | **32.00%（96 个正确修复）/ $0.70** | SWE-bench **Lite** | https://arxiv.org/abs/2407.01489 | 2024-07 | arXiv 预印本 | B | ① 摘要；② 官方 Lite 榜单 `20240630_agentless_gpt4o` = **82/300 = 27.3%**（GPT-4o，非论文的 GPT-4o 配置口径不同）；`20241028_agentless-1.5_gpt4o` = **32.0%** ← **与论文 32.00% 精确吻合的是 Agentless-1.5，而非初版 Agentless**。此处存在**版本混淆风险** |
| **AutoCodeRover** | SWE-bench-Lite 解决率 / 平均成本 | **19% / $0.43** | SWE-bench Lite | https://arxiv.org/abs/2404.05427 | 2024-04 | **ISSTA 2024**（comment） | B | ① 摘要；② 官方 Lite 榜单 `20240530_autocoderover-v20240408` = **57/300 = 19.0%** ← **精确吻合**，双向交叉验证成立 |
| **SWE-agent** | pass@1 | **12.5%**（SWE-bench 全集）/ **87.7%**（HumanEvalFix） | SWE-bench / HumanEvalFix | https://arxiv.org/abs/2405.15793 | 2024-05 | arXiv 预印本（NeurIPS 2024 D&B） | B | ① 摘要；② 官方 Lite 榜单 `20240402_sweagent_gpt4` = 18.0%（Lite 300）、Verified `20240402_sweagent_gpt4` = 22.4%（500）。⚠️ **12.5% 是全集口径，与任何 Lite/Verified 数值都不可直接比较** |
| **SWE-RL** | solve rate | **41.0%** | SWE-bench **Verified** | https://arxiv.org/abs/2502.18449 | 2025-02（v2 2025-12） | **NeurIPS 2025 Main**（comment） | B | ① 摘要；② 官方 Verified 榜单 `20250226_swerl_llama3_70b` = **206/500 = 41.2%** ← **吻合（0.2pp 差异，应为榜单使用 Agentless Mini 脚手架）**，双向交叉验证成立 |
| **MAGIS** | resolved ratio | **13.94%** | SWE-bench（原版） | https://arxiv.org/abs/2403.17927 | 2024-03（v2 2024-06） | arXiv 预印本 | B | ① 摘要。**官方榜单无 MAGIS 条目**（`evaluation/verified` 与 `evaluation/lite` 均无），故无法二次验证 |
| **RepairAgent** | 修复 bug 数 / 每 bug token 成本 | **164 个 Defects4J bug**（其中 **39 个**为已有技术未修复）/ **270,000 tokens ≈ $0.14** | Defects4J（Java，**非 SWE-bench**） | https://arxiv.org/abs/2403.17134 | 2024-03（v2 2024-10） | arXiv 预印本 | B | ① 摘要。⚠️ **Defects4J ≠ SWE-bench，与表 2A 的任何 resolve rate 都不可比** |
| **SWE-Search** | 相对提升 | **+23% relative**（vs 无 MCTS 的标准开源 agent，跨 5 个模型） | SWE-bench | https://arxiv.org/abs/2410.20285 | 2024-10（v6 2025-04） | arXiv 预印本 | B | ① 摘要。**只报相对提升，未报绝对 resolve rate** → 不可用于跨系统排序 |
| **CodeMonkeys** | resolve rate / 成本 / 集成 | **57.4%**（预算约 **$2,300**）/ 对已有 top 提交做选择集成得 **66.2%** | SWE-bench Verified | https://arxiv.org/abs/2501.14723 | 2025-01（v2 2025-02） | arXiv 预印本 | B | ① 摘要；② 官方榜单**无 CodeMonkeys 条目**。⚠️ **66.2% 是对"他人提交的集成选择"，不是单体系统成绩**，任何把它当作系统 SOTA 的引用都是误读 |
| **Kimi-Dev** | Verified resolve rate / SWE-Agent pass@1 | **60.4%**（workflow/agentless 类最佳）/ **48.6%** pass@1（SFT 适配后） | SWE-bench Verified | https://arxiv.org/abs/2509.23045 | 2025-09（v3 2025-12） | arXiv 预印本（MoonshotAI） | B | ① 摘要；② 官方榜单**无 Kimi-Dev 条目** |
| **Live-SWE-agent** | solve rate（无 test-time scaling）/ SWE-bench Pro | **77.4%** / **45.8%** | Verified / SWE-bench Pro | https://arxiv.org/abs/2511.13646 | 2025-11 | arXiv 预印本（UIUC） | B | ① 摘要的 **77.4%**；② 官方榜单 `20251120_livesweagent_gemini-3-pro-preview` = **387/500 = 77.4%** ← **精确吻合**；③ 官方榜单 `20251215_livesweagent_claude-opus-4-5` = **79.2%**（更高，说明 77.4% 是 Gemini 3 Pro 那一配置）。**三方一致，双重交叉验证成立** |

**表 2 小结（"agentic 是否优于单提示"）**
- **官方榜单层面**：Verified 上 agentic 脚手架（OpenHands / live-SWE-agent / TRAE / Sonar）确实占据高位（77–79%），agentless 血统的 Kimi-Dev（workflow）自报 60.4%。但**榜单本身已丧失区分度**——见下方表 5 的统计证据。
- **反例**：`20250627_agentless_MCTS-Refine-7B` 仅 **116/500 = 23.2%**（Verified）与 **49/300 = 16.3%**（Lite），说明**给 agentless 加搜索并不自动带来增益**；`20250725_sweagent_devstral_small_2507` = 38.0% 与 `20250511_sweagent_lm_32b` = 40.2% 同样处于低位。
- **最关键的复现反例在测试生成方向**（表 1 的 ICST 2026 复现研究），而非修复方向。**本审计未找到修复方向上"agentic 不优于单提示"的同等强度一手复现研究**；这是一个真实的知识缺口。

---

## 表 3 ｜ 自愈 / 运行时系统评估指标（MTTR、detection latency、recovery quality）

> ⚠️ **本方向是本审计中信噪比最差的一个。** 表内所有条目均为 B 或 C 级，**没有任何一条给出可复算的绝对值 + 官方基准 + 同行评审 venue 三要素齐全的证据**。

| 方法/系统 | 指标 | 指标值 | 基准/实验设置 | 一手来源 | 年份 | venue | 等级 | 问题 |
|---|---|---|---|---|---|---|---|---|
| **Cognitive Platform Engineering** | MTTR / 资源效率 / 合规 | **摘要未给任何数值**（仅称 "demonstrates improvements in mean time to resolution"） | K8s + Terraform + OPA + ML 异常检测原型 | https://arxiv.org/abs/2601.17542 | 2026-01 | arXiv 预印本 | B | 主张 MTTR 改善却**不提供数字**；无法用于建立任何基线 |
| **SF-DTM** | availability / MTBF / MTTR | availability **+13.2%**；MTBF 更高、MTTR 更低（**均未给绝对值**） | 云数字孪生处理，真实 trace | https://arxiv.org/abs/2505.01215 | 2025-05 | arXiv 预印本 | B | 只有相对值；域为数字孪生 VM 分配，**与云原生微服务自愈不可比** |
| **AutoGuard** | threat detection accuracy / MTTR | 检测准确率 **+22%**；MTTR **−38%** | **模拟** CI/CD 环境 | https://arxiv.org/abs/2512.04368 | 2025-12 | IEEE **UPWIECON 2025**（comment） | B | 模拟环境、无绝对值、无基线代码、venue 层级低 |
| **AegisFlow** | MTTR / patch success rate | MTTR **170 min → 3.2 min（+98.1%）**；patch 成功率 **92%**；JSON schema 变更 96%、标点漂移 98%、Shadow DOM 85% | **5 个失败场景**（n=5） | https://arxiv.org/abs/2610.06971 | 2026-10 | arXiv 预印本（43 页） | B | **n=5 的失败场景**支撑 98% 的 MTTR 主张；无独立复现；"释放 98% on-call 时间"属推断 |
| **LLM agent 自愈框架** | task success rate / failure propagation | **摘要未给任何数值**（"significantly increases"） | 多智能体工作流环境 | https://arxiv.org/abs/2605.06737 | 2026-05 | arXiv 预印本 | B | 无数字、无基线 |
| **AutoGuard 类 RL 自愈**（旁证） | — | 见 AutoGuard 行 | — | — | — | — | — | — |

**表 3 关键结论（可直接引用为审计判断）**
1. **"自愈系统 MTTR 降低 X%" 这一指标在 2025–2026 的一手文献中不存在可信的统一基线。** 现有全部一手来源要么只有相对值（SF-DTM、AutoGuard）、要么无数字（2601.17542、2605.06737）、要么建立在 n=5 的模拟场景上（AegisFlow）。
2. **没有任何一篇给出"detection latency"与"recovery quality"的标准化定义与可复算测量协议**（本次检索 `all:"self-healing" AND all:"MTTR"` 仅 3 条命中，`ti:"self-healing" AND cat:cs.SE` 22 条中无一条给出可复算协议）。
3. 因此，**若项目需要"自愈系统前沿基线"这一维度，本审计的结论是：该基线尚未建立，无法对比。** 任何凭单一个人 GitHub README、单作者预印本或 n<10 案例研究得出的 MTTR 数字都不应进入基线表。

---

## 表 4 ｜ 逻辑驱动 / 神经符号测试生成（符号执行 + LLM、SMT/不变式/后置条件）

| 方法/系统 | 指标 | 指标值 | 基准 | 一手来源 | 年份 | venue | 等级 | 交叉验证 |
|---|---|---|---|---|---|---|---|---|
| **Gordian** | coverage 提升 / token 削减 | coverage **+28.5–115.2%** vs 传统符号执行基线；**+74.1–189.8%** vs LLM-based 符号执行基线；LLM token 用量平均 **−91–96%** | 合成 "logic bombs" + FDLibM 数学库 + 四个结构化输入程序（libexpat, jq, bc, libyaml）；实现于 **KLEE** | DOI `10.1145/3832126`（Crossref 元数据 + 摘要全文） | 公开日期 2026-10-01 | **PACMSE Vol.3, Issue ISSTA, pp. 802–823** | **A**（DOI/卷期页/摘要三方一致） | ① Crossref 结构化记录；② OpenAlex 同一条目（标题/年/DOI 一致）；③ 作者 Dimitrios Stamatios Bouras, Sergey Mechtaev。⚠️ **基线口径必须写清**：`+28.5–115.2%` 是**相对传统符号执行**，不是相对一般测试生成工具；且**任务简报中给出的目标程序名（如 libyaml 等）与 DOI 记录一致** |
| **TestTailor** | statement / branch coverage 提升 / 成本 | 摘要给出方法（path-proximal tests + 符号约束），**具体数值本次未取得** | Python（对照 CoverUp） | DOI `10.1145/3797140`（Crossref 元数据 + 摘要） | 2026-06-30 | **PACMSE Vol.3, Issue FSE, pp. 277–298** | **A**（DOI/卷期页/作者）+ 🚫（数值未取得） | ① Crossref 完整记录（作者 Xiaoxuan Zhou, Yiling Lou, Jinhao Dong, Dan Hao）；② **arXiv 全库 `all:"TestTailor"` = 0 命中** ← 说明**只在 Crossref 可查、不在 arXiv**，属"能验证存在、不能验证数值" |
| **SpecGen** | 可验证规约生成数 | **279 / 385** 程序成功生成可验证规约 | SV-COMP Java 类别基准 + 自建数据集；对照 Houdini、Daikon | https://arxiv.org/abs/2401.08807 | 2024-01（v5 2025-02） | arXiv 预印本 | B | ① 原文摘要；② `all:"SpecGen"` 9 条命中中存在同名异域论文（神经 BRDF、RGBT 视觉），**引用时必须用 id 而非名字** |
| **nl2postcond** | 捕获的真实历史 bug 数 | **64 个 Defects4J 真实历史 bug** | Defects4J | https://arxiv.org/abs/2310.01831 | 2023-10（v2 2024-04） | **PACMSE / FSE 2024**（comment） | B | ① 原文摘要；② `all:"NL2Postcond"` 仅 2 条命中，无歧义。注意：**nl2postcond 是问题命名（problem），不是系统名** |
| **AssertFlip** | fail-to-pass 成功率 | **43.6%** | **SWT-Bench Verified**（bug 可复现测试基准） | https://arxiv.org/abs/2507.17542 | 2025-07（v2 2026-01） | arXiv 预印本 | B | ① 原文摘要自称"outperforms all known techniques in the leaderboard of SWT-Bench"。**未独立打开 SWT-Bench 官方榜单二次验证** |
| **SWE-Proof / Benchproofer** | 形式化验证 vs 测试的差异 / 规格质量 | **1/4 通过测试的补丁存在反例**；正确形式化规约把 resolution 从 **85% → 95%**；自行撰写规约的 agent **不比无辅助基线更好**；仅 **56%** 的规格通过审计；规格质量在未解决实例上失败率 **92%** vs 已解决 **51%** | SWE-bench Verified 的 500 个 issue（形式化重铸） | https://arxiv.org/abs/2609.21190 | 2026-09 | arXiv 预印本 | B | ① 原文摘要；② 引用了 ImpossibleBench 之外的独立评测对象 Claude Opus 4.8。⚠️ **"85% → 95%" 是特定模型在形式化规约条件下的 resolution，不是通用基线** |
| **ImpossibleBench** | cheating rate（规格-测试冲突下通过率） | 摘要给出方法，**未给单一数值**（框架型论文） | LiveCodeBench + SWE-bench 的 "impossible" 变体 | https://arxiv.org/abs/2510.20270 | 2025-10 | arXiv 预印本 | B | ① 原文摘要；② GitHub `safety-research/impossiblebench` 在摘要中给出。**这是评估"LLM 是否真的解决问题还是改测试"的关键工具** |
| **符号执行 + LLM 相关（检索为负）** | — | **未找到** | — | — | — | — | **D** | `all:"CodeQL" AND abs:"test generation"` = **0 命中**；`ti:"AID" AND abs:"unit test generation"` = 0；`all:"HumanEvalJava"` = **0 命中**；`all:"HumanEval-J"` = **0 命中**。→ **"CodeQL 引导的测试生成"与"HumanEvalJava / HumanEval-J 作为 LLM 单元测试基准"这两个说法，本次检索未能取得任何一手来源** |

**表 4 小结**
- **神经符号方向唯一达到 A 级（DOI + 卷期页 + 摘要一致）的条目是 Gordian（KLEE + LLM ghost code）与 TestTailor（PACMSE FSE 2026，路径邻近测试 + 符号约束）。**
- 两者都是**"符号/形式化组件提供细粒度路径或约束引导，LLM 负责生成"**，且都明确以 KLEE 或符号约束为核心 —— 这与简报中"符号执行+LLM、SMT/不变式"的方向一致，**方向本身有一手支撑，不存在"疑似不存在"的问题；被证伪的是具体数字的可用性**（TestTailor 数值未取得）。
- **"CodeQL 引导"这一具体技术路线在一手文献中无命中**，建议在基线表中删除或标注为未建立。

---

## 表 5 ｜ 评估基准与方法学（SWE-bench 榜单状态、非确定性、统计显著性）

| 主题 | 关键发现 | 数值 | 一手来源 | 年份 | venue | 等级 | 交叉验证 |
|---|---|---|---|---|---|---|---|
| **SWE-bench 榜单提交规则变更** | Verified/Multilingual 仅收学术机构 + 开源方法 + 有同行评审论文 | 生效日 **2025-11-18**；仍合格举例 OpenHands、SWE-RL、FrogBoss、AutoCodeRover；不再合格 Augment Code、Solver AI、Honeycomb.sh | `raw.githubusercontent.com/swe-bench/experiments/main/README.md` | 2025-11-18 | 官方仓库政策 | **A** | ① 官方 README 原文；② `https://www.swebench.com/submit.html` 指向同一仓库与流程 |
| **SWE-bench 官方可复算性** | 提交须附自有公开制品仓库；`swebench submit verify` 可**从记录的执行输出重新评分**，不需 Docker 重跑 | — | 官方 README + submit.html | 2026 | 官方文档 | **A** | ① README 命令示例；② submit.html 页面 |
| **榜单已失去区分度（核心方法学证据）** | Verified 前两名**各解 396/500**；前 10 名共享 **285** 个成功与 **51** 个失败，只有 **164** 个实例能区分它们；frontier 解集 median nesting **0.935**（对照 score-implied baseline 0.774）；**29 对相邻 top-30 的精确配对 McNemar 检验在 α=0.05 下全部不显著（0/29）**；Test split 上 23 对中有 14 对显著；within-model scaffold 极差达 **29.8pp**，而 top-30 的总分跨度仅 **8.8pp** | 见左 | https://arxiv.org/abs/2609.17394 | 2026-09-15 | **ADMA 2026**（comment；Special Session on Responsible Data Intelligence） | B（原文摘要）；**与官方榜单 A 级数据一致** | ① 原文摘要；② **本审计独立从官方 `results.json` 读到 `20251215_livesweagent_…` = 396/500 与 `20251205_sonar-foundation-agent_…` = 396/500** ← **"前两名各 396/500" 与本审计的 A 级扫描精确吻合，交叉验证成立** |
| **SWE-bench 生态构成审计** | 分析 **79** 条 Lite + **133** 条 Verified 提交 | 结论：两个榜单的多数提交来自产业界（小公司与大型上市公司），且常居榜首；学术贡献（通常开源）仍具竞争力；**专有 LLM（尤其 Claude 系）占主导** | https://arxiv.org/abs/2602.04449 | 2026-02 | **ICSE-SEIP 2026**（comment，DOI `10.1145/3786583.3786904`） | B | ① 原文摘要；② 与本审计的 182 条 Verified / 84 条 Lite 目录扫描**量级一致**（论文统计时点更早，另有部分条目被拒/合并） |
| **LLM-as-Judge 判定非确定性** | 同一 temperature=0 判定器、同一服务端版本，**重复运行仍产生不同判定**；per-item flip rate 平均约 **5%**，在决定榜单名次的 close-call 项上约 **40%**；单判定器幅度跨 **40×**（**0.13% – 近 10%**）；主判定器聚合排名稳定（0% top-K 不稳），但配对层级 bootstrap 下**约 1/5 至 3/4 的相邻名次统计上不可区分**；Gemini 与 Sonnet 判定器在 Arena-Hard 上 Kendall's τ = **0.42–0.64**；15 个预期头对头排序中仅 8 个在所有判定器下都成立 | 见左 | https://arxiv.org/abs/2609.33044 | 2026-09-27（v2 2026-09-30） | arXiv 预印本（单作者） | B | ① 原文摘要；② 与本表 2609.17394 的"相邻无效"结论**方向一致且互相独立**（一个针对 judge，一个针对 SWE-bench 榜单） |
| **判定器偏差的方差分解** | 将 benchmark 得分方差分解为 scenario / generation / judge / residual 四分量；judge 偏差**无法通过增加场景或生成数平均掉**；提出 CyclicJudge 轮转分配判定器，在固定判定器与调用预算下精确恢复 panel 均值 | — | https://arxiv.org/abs/2603.01865 | 2026-03（v3 2026-05） | arXiv 预印本 | B | ① 原文摘要；② 与 2609.33044 的"单判定器不可靠"结论互为佐证 |
| **真实评测中的作弊/走捷径度量** | ImpossibleBench：构造规格与测试直接冲突的 "impossible" 任务，pass rate 即 cheating rate | 摘要**未给单一数值** | https://arxiv.org/abs/2510.20270 | 2025-10 | arXiv 预印本 | B | 见上 |

**表 5 小结（方法学硬约束）**
1. **"SWE-bench Verified 上 A 比 B 高 X 个点"在 top-30 内几乎全部不具统计显著性**（0/29 相邻对通过 McNemar）。任何以几个百分点的差距论证"本系统优于前沿系统"的表述，在有 500 实例的 Verified 上**不成立**。这有 A 级官方数据 + 独立方法学论文双重支撑。
2. **单次评测的分数波动来源已有一手量化**：per-item flip ~5%、close-call ~40%（LLM-as-judge）；within-model scaffold 极差 29.8pp（远大于系统间差异 8.8pp）。**"多运行取均值 + 报告方差/置信区间 + 配对检验"是必要而非可选的报告项。**
3. **榜单已有政策层面的开放性收缩**（2025-11-18 起），且 **Lite 已事实停更**（最后条目 2025-09-11）。以 Lite 作为主竞技场已过时。

---

## 6. 交叉验证与冲突说明（≥8 个数据点做了两个独立来源）

| # | 数据点 | 来源 1 | 来源 2 | 结论 |
|---|---|---|---|---|
| 1 | live-SWE-agent **77.4%** Verified | arXiv:2511.13646 摘要自报 77.4% | 官方榜单 `20251120_livesweagent_gemini-3-pro-preview` = 387/500 = **77.4%** | **精确吻合**，且榜单另有一条 79.2%（Claude 4.5 Opus 配置）说明 77.4% 的模型归属 |
| 2 | Verified 前两名各 **396/500** | arXiv:2609.17394（Lead 独立核验 + 本审计核验） | 本审计从官方 `results.json` 逐条读取：`20251215_livesweagent…`=396、`20251205_sonar…`=396 | **精确吻合** |
| 3 | AutoCodeRover **19%** Lite | arXiv:2404.05427 摘要 19% | 官方 Lite `20240530_autocoderover-v20240408` = 57/300 = **19.0%** | **精确吻合** |
| 4 | SWE-RL **41.0%** Verified | arXiv:2502.18449 摘要 41.0% | 官方 `20250226_swerl_llama3_70b` = 206/500 = **41.2%** | 吻合（0.2pp，应为脚手架差异） |
| 5 | Agentless **32.00%** Lite | arXiv:2407.01489 摘要 32.00%（96 fixes） | 官方 Lite：`20240630_agentless_gpt4o` = **27.3%**；`20241028_agentless-1.5_gpt4o` = **32.0%** | ⚠️ **冲突已定位**：与 32.00% 吻合的是 **Agentless-1.5**，非初版 Agentless。**引用时必须区分版本** |
| 6 | Gordian DOI `10.1145/3832126` | Crossref 结构化记录（标题/作者/PACMSE Vol.3 ISSTA/pp.802-823/摘要） | OpenAlex 同条目（标题/年/DOI 一致） | **一致**。但**基线口径需纠正**：+28.5–115.2% 是相对**传统符号执行** |
| 7 | TestGenEval 的 arXiv id | 任务简报称 2502.02794 | arXiv API：**2502.02794 = METAMON**；`ti:"TestGenEval"` → **2410.00752** | ⚠️ **简报映射错误，已一手证伪** |
| 8 | ULT 的四个指标 | arXiv:2508.00408 摘要 | arXiv:2608.24473（Ockhamareto）全文引用 ULT（`all:"UnLeakedTestbench"` 命中） | 一致 |
| 9 | CANDOR 的存在性与对手 | arXiv:2506.02943 摘要 | `all:"CANDOR" AND cat:cs.SE` 唯一命中即该文；对手 TOGLL 独立存在（2405.03786） | 系统真实存在；**venue 未取得一手证据（项目称 TOSEM 2026，本次 D 级）** |
| 10 | AdverTest / 复现研究 | arXiv:2602.08146、arXiv:2601.09695 摘要 | **Lead 独立核验的 DOI**（10.1145/3832122 / 10.1109/icst69053.2026.00040） | 一致（跨成员交叉验证） |
| 11 | AID 是否存在 | 搜索片段指向 arXiv:2404.10304 "We propose AID" | arXiv API v1 摘要确含 AID；v2 摘要已改名 **TrickCatcher**（ACL 2025） | 存在，但**因更名导致按名字检索失败**；引用必须用 id 或新名 |
| 12 | TestTailor 是否存在 | 项目文档称 FSE 2026 | Crossref DOI `10.1145/3797140`：PACMSE Vol.3 FSE, pp.277-298, 2026-06-30；**arXiv `all:"TestTailor"` = 0** | 存在，但**仅 Crossref 可查**；数值未取得 |

### 未解决的冲突 / 无法判断项
- **MAGIS 13.94%**、**CodeMonkeys 57.4% / 66.2%**、**Kimi-Dev 60.4%**、**RepairAgent 164 bugs**、**SWE-Search +23%**：均**只有论文自报，无官方榜单条目可二次验证**（B 级单源）。
- **CANDOR 的 venue**：项目文档称 TOSEM 2026，arXiv comment 未载明 → 本次未能取得一手 venue 证据（D）。**注意：arXiv v7 更新至 2026-03，与"TOSEM 2026"不矛盾，但也不构成证据。**
- **TestPilot 的口径**：真实存在（arXiv:2302.06527），但它是 **JavaScript/npm** 工具。"LLM 单元测试生成"若在 Java 语境引用 TestPilot 数值，属**基准错配**。

---

## 7. "疑似不存在 / 无法验证"清单（含实际检索词与返回）

| 名称 | 声称（仅在项目文档或简报中出现） | 实际检索 | 返回 | 判定 |
|---|---|---|---|---|
| **TwinMem / TwinMem-Agent** | 项目文档提及 "TwinMem-Agent 的 89.1%" | `all:"TwinMem"`（arXiv API） | `TOTAL: 0` | **D — 未取得任何一手来源，疑似不存在** |
| **ARC-APR** | 项目文档称"疑似不存在" | `all:"ARC-APR"` | 仅 1 条无关命中（APR-Transformer 绝对位姿回归，arXiv:2505.09356，机器人定位） | **D — 疑似不存在**（与项目文档判断一致） |
| **Defects4J v3 / Defects4J version 3** | 项目文档提及 | `all:"Defects4J v3"`；`all:"Defects4J" AND all:"version 3"` | 两条查询均 `TOTAL: 0` | **D — 未取得一手来源，疑似不存在** |
| **AgentRepair** | 项目文档称"无可获取指标" | arXiv `all:"AgentRepair"` = **0**；Crossref 检索 | Crossref 命中：**"AgentRepair: Multi-Agent, AST-Anchored, Retrieval-Augmented Program Repair for Cold-Start Environments"**，*2025 12th Int'l Conf. on Dependable Systems and Their Applications (DSA)*，DOI `10.1109/dsa66321.2025.00025` | **存在但数值不可及（C/D）**：论文真实存在，**IEEE 付费墙，摘要与指标未能取得**。项目文档"无可获取指标"的结论**成立**，但"疑似不存在"的措辞**不准确** |
| **TestTailor** | 项目文档称 FSE 2026 | arXiv `all:"TestTailor"` = **0**；Crossref `query.bibliographic=TestTailor…` | Crossref 命中 DOI `10.1145/3797140`，PACMSE Vol.3 Issue FSE, pp.277-298 | **存在（A 级存在性）**，但**数值未取得** → 不得引用其数字 |
| **CodeQL 引导的测试生成** | 简报列为需覆盖方向 | `all:"CodeQL" AND abs:"test generation"`（arXiv） | `TOTAL: 0` | **D — 未取得一手来源**；建议标注"该技术路线未建立基线" |
| **HumanEvalJava / HumanEval-J（作为 LLM 单元测试基准）** | 简报列为需覆盖基准 | `all:"HumanEvalJava"`；`all:"HumanEval-J"` | 两条查询均 `TOTAL: 0` | **D — 未取得一手来源**。⚠️ APR 文献中的 "HumanEval-Java" 需另行核验，本次**未取得** |
| **"test generation" 的 "简单提示即够" 复现研究** | 简报要求覆盖 | `abs:"test generation" AND abs:"simple prompting"` | 仅 1 条弱相关（AugmenTest, arXiv:2501.17461）；**但通过 `all:"SymPrompt"` 反向命中 2601.09695（ICST 2026）** | **存在，已取得**（见表 1 反例行）——检索词需调整才能命中 |
| **AID（按名字检索）** | 简报列为需覆盖 | `ti:"AID" AND abs:"unit test generation"` = 0；`all:"AID" AND abs:"unit test" AND cat:cs.SE` = 7 条全部无关 | 需通过 `all:"SymPrompt"` 路径与搜索片段才回溯到 arXiv:2404.10304 | **存在但已更名 TrickCatcher**；**按旧名检索必然失败** |
| **TestGenEval（按 arXiv:2502.02794 检索）** | 简报给出的 id | arXiv API `id_list=2502.02794` | 返回 **METAMON: Finding Inconsistencies between Program Documentation and Behavior using Metamorphic LLM Queries**（Lee, An, Yoo, LLM4Code 2025） | **id 映射错误**；TestGenEval 真实 id = **2410.00752** |
| **GORDIAN（按名称 + arXiv 检索）** | 项目文档称 PACMSE DOI 10.1145/3832126 | `all:"GORDIAN"`（arXiv）= 91 条，前 5 条全为纽结理论 | 通过 **Crossref DOI 直查**才命中 | **存在（A 级）**；**仅靠 arXiv 名称检索会误判为不存在** |
| **TestPilot（按名称）** | 简报列为需覆盖 | `ti:"TestPilot"`（arXiv）= **0**（标题不含该词） | 需 `web_search` + `all:"TestPilot"` 反向定位到 arXiv:2302.06527 | **存在**；标题检索失败 |

### 7.1 由本清单导出的检索方法学警告（对项目同样适用）
1. **"arXiv 标题检索 0 命中" ≠ "不存在"**。已出现 3 个反例：GORDIAN（DOI 只在 Crossref）、TestTailor（只在 Crossref/PACMSE）、TestPilot（系统名不在标题里）。
2. **"arXiv 名称检索命中无关论文" ≠ "不存在"**。CANDOR 的 3 条无关命中（off-policy evaluation / unanswerability / 音视频语音识别）极易被误判为伪造。
3. **系统更名会造成"检索性不存在"**：AID → TrickCatcher 是实例。
4. 因此，判"疑似不存在"必须满足：**arXiv（名称 + 标题 + 全文）× Crossref（bibliographic）× OpenAlex（search）四路均无命中**，并在产出中写明全部检索词。本清单中真正满足此标准的只有 **TwinMem、ARC-APR、Defects4J v3、CodeQL-guided test generation、HumanEvalJava**。

---

## 8. 未完成 / 无法核验清单（供 Lead 判断哪些维度"基线未建立"）

| # | 目标 | 已尝试的检索词 / 端点 | 结果与原因 |
|---|---|---|---|
| 1 | **SWE-bench 官网榜单 HTML 表格** | `web_fetch https://www.swebench.com/verified.html`、`curl https://www.swebench.com/index.html` | 前者 30s 超时，后者 60s 连接超时。**已用官方榜单仓库逐条结果文件替代（更一手）**，故不影响结论 |
| 2 | **DBLP 全库核验** | `https://dblp.org/search/publ/api?q=…&format=json`（含浏览器 UA） | **Anubis 反爬返回 bot 校验页**。DBLP 完全未用上；**任何依赖 DBLP 的 venue 判定（尤其 CANDOR 的 TOSEM 2026）本次无法完成** |
| 3 | **Semantic Scholar 交叉验证** | `api.semanticscholar.org/graph/v1/paper/search` | HTTP **429**，未取得数据 |
| 4 | **HITS 的覆盖/变异具体数值** | arXiv:2408.11324 摘要；`all:"HITS"` | **摘要只写 "significantly outperforms"，无数字**；正文表格未逐页核对 → **数值未取得一手来源** |
| 5 | **TestSpark 的效果数值** | arXiv:2401.06580 摘要 | 工具型 demo 论文，**摘要无覆盖/变异数值** → 未取得 |
| 6 | **ChatUniTest 的具体覆盖率** | arXiv:2305.04764 摘要 | 只写"在半数项目上最优"，**无百分数** → 未取得 |
| 7 | **CANDOR 的 venue（TOSEM 2026?）与绝对 mutation score** | arXiv:2506.02943 摘要 + comment 字段；DBLP（失败） | arXiv comment **未载明 venue**；摘要只给"≥21.1pp vs TOGLL"与"mutation score 明显更优"，**无绝对值** → venue 与绝对值均未取得 |
| 8 | **TestTailor 的 statement/branch 提升与成本** | Crossref DOI 记录摘要（截断）；arXiv（0 命中） | Crossref 摘要被截断且**未含数值**；全文付费墙 → **数值未取得** |
| 9 | **AgentRepair 的任何指标** | arXiv（0）、Crossref（命中 DSA 2025）、DOI 全文 | **IEEE 付费墙**，摘要与指标不可得 → **未取得** |
| 10 | **SWT-Bench 官方榜单现状** | 未找到公开榜单端点（`all:"SWT-Bench"` 未返回榜单地址） | AssertFlip 43.6% **仅有论文自报**，未做榜单二次验证 |
| 11 | **MAGIS / CodeMonkeys / Kimi-Dev / SWE-Search 的官方榜单条目** | 逐条扫描 `evaluation/verified`（182 条）与 `evaluation/lite`（84 条） | **四者均无官方条目** → 只能保留 B 级单源 |
| 12 | **"defect detection rate" 的统一口径** | 检索多个候选定义 | 未找到标准化定义（不同论文分别用 fault detection rate / FDR / 检出 bug 数 / mutation score）→ **该指标目前不可跨论文比较** |
| 13 | **自愈系统的 detection latency / recovery quality 标准协议** | `all:"self-healing" AND all:"MTTR"`、`ti:"self-healing" AND cat:cs.SE`（22 条）、`all:"mean time to repair" AND all:"cloud"`、`ti:"AIOps" AND abs:"root cause"` | **无任何一篇给出可复算的标准化协议与绝对值** → **判：该维度前沿基线未建立，无法对比** |
| 14 | **CodeQL 引导的测试生成** | `all:"CodeQL" AND abs:"test generation"` | `TOTAL: 0` → **该技术路线无一手基线** |
| 15 | **HumanEvalJava / HumanEval-J 作为 LLM 单元测试生成基准** | `all:"HumanEvalJava"`、`all:"HumanEval-J"` | 均 `TOTAL: 0` → **未取得**。APR 文献中的 HumanEval-Java **本次未核验** |
| 16 | **修复方向"agentic 不优于单提示"的复现研究** | 多组检索（`test generation` + `simple prompting`、`SymPrompt` 反向路径等） | 复现反例**只在测试生成方向找到**（ICST 2026）；**修复方向未找到同等强度的一手复现研究** → 真实知识缺口 |
| 17 | **GORDIAN 的实验条件细节**（哪些 benchmark 贡献了区间端点） | Crossref 摘要（完整）+ OpenAlex | 区间端点对应哪些程序**摘要未逐项对应**；全文付费墙 → **区间已取得，端点归属未取得** |

---

## 9. 本审计给出的"最高置信度前沿基线"（仅 A 级与强 B 级）

1. **SWE-bench Verified 官方榜首（并列）：396/500 = 79.2%** — live-SWE-agent + Claude 4.5 Opus（`20251215`）与 Sonar Foundation Agent + Claude 4.5 Opus（`20251205`）。**A 级，可逐条复算。**
2. **SWE-bench Lite 官方榜首：181/300 = 60.3%** — ExpeRepair-v1.0 + Claude 4 Sonnet（`20250625`）。**A 级。Lite 已于 2025-09-11 后停更。**
3. **SWE-bench Verified 最新条目：71.8%（359/500）** — mini-SWE-agent v2.4.2 + Gemini 3.5 Flash（`20260901`）。**A 级，且暴露 441 vs 500 分母陷阱。**
4. **Agentless 血统最强 workflow 系统：Kimi-Dev 60.4%**（Verified，自报，B 级单源）。
5. **LLM 单元测试生成的"真实"覆盖率区间：ULT 上 statement 45.10% / branch 30.22% / mutation 40.21%**（3,909 抗泄漏任务，12 模型均值，B 级）；同批模型在 TESTEVAL 上 92.18% / 82.04% / 49.69% → **覆盖率指标跨基准不可比**。
6. **最强反例（方法学价值最高）：纯提示基线在 line/branch/mutation 上分别反超 HITS/SymPrompt/TestSpark/CoverUp 17.72 / 19.80 / 20.92 个百分点**（393 类 / 3,657 方法，ICST 2026，B 级 + Lead 核验 DOI）。
7. **神经符号唯一 A 级基线：Gordian（KLEE + LLM ghost code）覆盖率 +28.5–115.2% vs 传统符号执行、+74.1–189.8% vs LLM-based 符号执行、token −91–96%**（PACMSE Vol.3 ISSTA, pp.802-823, DOI `10.1145/3832126`）。
8. **榜单区分度已失效：Verified 前两名各 396/500，29 对相邻 top-30 的 McNemar 检验 0 对显著**（arXiv:2609.17394 + 本审计官方数据交叉验证）。
9. **评测非确定性的量化下界：LLM-as-Judge per-item flip ~5%、close-call ~40%、单判定器幅度 0.13%–10%**（arXiv:2609.33044）。
10. **自愈方向：无任何可信前沿基线**（表 3 全部为无绝对值、模拟环境或 n=5 的 B 级来源）。

---

## 10. 可被项目直接引用的 6 条"引用纪律"（由本审计一手证据导出）

1. **不得把不同基准的 coverage/mutation 数值并列成"提升"** —— ULT vs TESTEVAL 的 30.22% vs 82.04% branch 差异来自基准难度与泄漏，不是方法差异。
2. **不得用 top-30 内的几个百分点差论证优劣** —— 0/29 相邻对通过 McNemar；within-model scaffold 极差 29.8pp > top-30 总跨度 8.8pp。
3. **不得把 Agentless 与 Agentless-1.5 混为一条基线** —— 论文 32.00% 对应 **Agentless-1.5**；初版官方榜单为 27.3%。
4. **不得把 CodeMonkeys 的 66.2% 当作单体系统成绩** —— 那是对已有 top 提交做集成选择的结果。
5. **不得把 Gordian 的 +28.5–115.2% 当作"相对一般测试生成工具"的提升** —— 基线是**传统符号执行**。
6. **凡引用 SWE-bench resolve rate，必须写明 split（Verified 500 / Lite 300 / 全集 2,294）、脚手架、模型版本与推理预算**；本审计已证明同一系统换模型/脚手架可差 29.8pp。

---

*本文件所有数值均来自第 0 节列出的端点，检索日期 2026-10-11。未使用任何项目内文档中的前沿数字。凡未能打开原文核对者均已标注 B/C/D 级并写明"未取得一手来源"。*
