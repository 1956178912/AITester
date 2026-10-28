# 更新日志

> 最后更新：2026-10-28

本文件只记录对外可见的变化；逐轮历史见下方归档。

## [Unreleased]

### Added
- 「稿件外部读数数字 ↔ 登记册落点」门禁（GJ 轮）：外部读数登记册的「读数」列是外部数字的唯一权威记录，而三道既有机制各管一段——行级锁只做**行内**自洽（读数列的数字在本行引文里）、引文核验只管**引文 ↔ 官方摘要**、审计器只查「SRC 所指工件里有没有这个数」（查无只是披露，不判红）——**跨段的那一格没人管**：稿件在某个段落里写下一个外部数字、而登记册里根本没有对应行时，没有任何机制会红。现新增 `scripts/tools/export_paper_external_numbers.py` + 入库快照 `docs/study/PAPER_EXTERNAL_NUMBERS.md`（`paper/` 按双盲纪律不入库 ⇒ 快照是把稿件侧事实搬进 CI 的唯一通道）：稿件段落引用了登记册键时，该段的每个高精度数字（千分位整数或 ≥2 位小数，与审计器同口径）必须能在**被引键之一的**登记行里逐字找到，否则 rc=1；接为 `make paper-external-numbers` 与 ci.yml 3.14 阻断步骤。11 例锁（落点逐字核验 + 权威源路径锁 + 工具 rc 路径端到端锁 + 2 例负对照）。
- 前沿补扫五篇（GJ 轮 §23）：跨 7 个分类（cs.SE / cs.CR / cs.AI / cs.PL / cs.MA / cs.SI / cs.LF）+ 27 条检索式（论断族 + 分类降序）补扫，检索面去重 **472 篇**、与已登记 98 个 arXiv ID 求差后 **443 篇未登记**，按族命中筛出 4 篇高相关候选逐篇读官方摘要后判定：**无新增直接占位**本稿三块增量；但新增三处定位约束——① `2606.14589`（生产 agent 运行时 4,286 单测 + 827 治理检查之下「约 70% 的静默失败由人眼而非测试/审计发现」）是本稿核心现象的**逆向条件**形态（它的分母=真实失败，本稿的分母=声明通过），与本稿 59.58% **严禁并列、严禁换算**；② `2610.05981`（与①**同作者同数据** ⇒ 按既有纪律**只算一个独立实例**）是本稿「测量装置即贡献」的**方法论同构**实例（确定性层 + 引文逐字举证的 LLM 判定 + 破坏式验证 + 「零判决不得读作成功」+ 披露观察器自身失败）⇒ 正文不得宣称本稿首创这套纪律；③ `2610.36947`（上下文 1→50 ⇒ token 49 倍而不改善判定；确定性范围检查 100% 正确 vs 模型只拒 70–100%）是编排负结果的同向实例。另 `2610.32548`（「覆盖/杀分 ≠ 行为检出」族第三个实例）与 `2610.36623`（邻接不同构）仅登记不入正文。
- 批量补图（第十轮）：稿件图数 8→20 张——锚定检测、成本对比、测量管线、证据阶梯、数据重置时间线、声明率签名、gold 影响、分母分解、门禁家族、gold 材料、复现链、规格仪器共 12 张新图；每张走「入库快照 → `figure_data.py` load 自检 → plot 脚本 → 生成 → 目检」闭环，数字一律读 `docs/study/*_2026-10-27.json` 快照（单一事实源，转录自稿件对应表，上游 = `WITHDRAWN_ARTIFACTS_2026-10-24.md`）；`tests/test_paper_figures.py` 扩到 20 图 + 9 例新内容锚点锁（70 passed）。
- 前沿补扫（GG 轮 §22）：按论断族（cs.SE 60 条 + 四族补扫，arXiv 官方 API 逐字核验）收口前补扫——检索面内**无新增直接占位**本稿剩余三块增量，但两条既有让渡各获**第二独立实例**：`2607.19843`（官方原句 "test--fix error coupling" 坐实「补丁与测试同源 ⇒ 互相印证」机制非新观察）、`2606.10417`（17.5% 行为缺口 + 高覆盖方法仍有缺口，坐实「覆盖≠检出」非新观察）；邻接不占位 `2610.04921` / `2610.27672`——**散文登记**（未进 `refs.bib`，不建行）。
- 研究设计总览图（第 5 张，GG 轮）：单栏纵向四段（7 工件 → 三臂效应隔离链 → C1/C2/C3 协议单元 → 两世代），数字经 `figure_data.py::artifact_registry_summary()` 读源码登记表（与 Table 1 同源：7 工件 / 4,303 字符 / 主工件 196 字符）；新增 3 例锁（登记表 1 例 + 图 parametrize 2 例）。
- 重分类堆叠条图（第 6 张，GH 轮）：RQ4 规格锚定下的任务级重分类——把 `tab:reclass` 的数字墙表还原为其 Typst 原始形态的堆叠条（每臂 41 任务 × control/anchored 两条件 × specific red / over-red / unmeasurable 三分类）；数字读入库快照 `docs/study/RECLASSIFICATION_ANCHOR_2026-10-27.json`（单一事实源，转录自稿件 `tab:reclass`，上游 = 重建世代锚定批 `audit.specificity_gate_verdict`，作者机可复算），`figure_data.py::load_reclassification()` 加载时自检（n=41 / 三分类键齐全 / 每条件合计 41 / 恰 4 臂，不一致即抛错拒绝出图）；新增 3 例锁（reclassification PDF parametrize + PNG parametrize + 快照四臂/三分类**内容锚点**锁）。
- 前沿登记补扫三篇（FF 轮 §20）：按论断族（cs.SE + 全库论断关键词，官方 API 逐字核验）登记 `2610.33708`（**直接占位**「覆盖报告不证明检出能力」的测量工具化——Veritas 实测 51,382 个被覆盖对象分支 outcome 中 **18% 翻转后无测试失败**、弱检位置比强检位置多 12.4–54.7pp 的独立未检出缺陷；本稿③的「效度」侧必须显式承认这类判据侧工具的存在，「覆盖 ≠ 检出」不得写成新观察）、`2610.34817`（LLM agent 的 prompt-caching 静默误集成：120 PR 实证，多数误集成无可见运行时故障）、`2610.35223`（ORION：PR 级行为回归的结构化 oracle）——**散文登记**（未进 `refs.bib`，不建行）。
- 引文逐字核验门禁（FE 轮）：外部读数登记册 89 行 / 188 条引文的行级判据（CP 轮）只做**行内自洽**，回答不了「这句引文到底是不是原文」——FE 实测抓到三类行内判据看不见的缺陷：**翻译腔改写**（`hamidi2026criteria` 登记的「approximately miss approximately 99%」在官方摘要里**既无此句也无 99% 这个数字**，摘要说 fault detection「often near zero」）、**改写**（`konstantinou2026coding`）、**跨句拼接**（9 行把官方摘要里不连续的句子接在一起，拼接处漏了句号）。现新增 `scripts/tools/verify_citation_quotes.py` + 入库快照 `docs/study/EXTERNAL_READINGS_ABSTRACTS.json`（arXiv 官方 API 的 `summary` + `title`，**按版本**存——`kim2026scaling` 的 R²=0.524 出自 v2、v3 已改 0.373/0.413，只存最新版会把按 v2 登记的引文误判；CI 不联网 ⇒ 快照入库、离线可复跑）：每条引文必须**逐字连续命中**官方摘要，或出处/引文列显式标注正文层级，否则 rc=1；接为 `make citation-quotes` 与 ci.yml 3.14 阻断步骤。12 例锁（快照完整性 + 全部引文可核 + 覆盖面不得塌缩 + 3 例负对照）。全量回核：84 个 arXiv 条目的快照与官方 API 逐字一致。
- 前沿登记补扫两篇（FE 轮 §18）：按论断族（cs.SE + cs.AI，官方 API 逐字核验）登记 `2607.16646`（**占位本稿③的邻接方法论**——「测量手段必须显式声明其检出下界与盲区」，并给出「可靠判据与阈值判据不可兼得」的证明；本稿据此强化披露、不得把「显式声明盲区」写成新方法）与 `2609.09315`（已在册，本轮复核改错登记措辞）；本稿②③的可主张部分继续收窄为**分母构成层面**的分解。
- 前沿登记补扫三篇（FD 轮）：按论断族（cs.SE + cs.AI/cs.MA，arXiv 官方 API 逐字核验）登记 `2610.28675`（**直接占位**「测量协议改变测得失败率」这一一般形式，采样维度，漏检率 12.10%–28.03%）、`2610.34634`（可复用验证器的门禁增益必须对可核验基线作差）、`2610.25308`（从提交对造可执行回归实例，不构成本稿构念）——**散文登记**（未进 `refs.bib`，不建行）。本稿②的可主张部分据此收窄为：协议扰动发生在**声明的分母构成**上（条件 vs 边际）且与效度联立，不是采样密度层面的一般现象。
- 前沿登记补扫三篇（FC 轮）：按 arXiv 官方 API（`export.arxiv.org/api/query`）逐字核验 `2609.10548`（安全域 silent failures，**直接占位**「测试通过 ≠ 缺陷被检出」这一一般论断）、`2607.28871`（BSG-VA：验证证据的判别力）、`2609.04909`（APR 修复幻觉）后**散文登记**（未进 `refs.bib`，不建行）；并查明 `2609.10548` 与已登记的 `2610.06163` **同作者同数据集** ⇒ 只有一次独立命中，**不得写成多方独立复现**；本稿可主张的增量仍限三块分母层面的分解。
- APR 实验设置前沿登记（FB 轮）：按 arXiv 官方摘要页核验 `2609.17993`，登记 task unit / fault-localization assumptions / initial input / tool access / repair-time feedback / final validation / resource budget 七维机器可读契约；当前 provenance 不声明已完全符合该 schema，后续对齐列入 1.x，不在 1.0.0 稳定批次借“前沿”名义引入未验证新功能。
- 依赖漏洞豁免过期守卫（DF 轮）：`make dependency-audit` 与 CI 阻断步骤真实跑一次**不带** `--ignore-vuln` 的 pip-audit——修复版出现、新 advisory 未登记、版本漂移即红；豁免理由由 `src/` 静态扫描锁定；离线 `[SKIP]` 披露，CI `--require-audit` 把「无法验证」判红（37 例锁）。

### Changed
- 发布新鲜度例外登记（GK 轮）：`v1.0.0` 前移之后 main 上又落了 1 个 **src/ 层**提交（agents 三处实测缺陷修复），`git diff v1.0.0..HEAD -- src/` **非空**（与 GG/GH 轮「src/ 零改动」性质不同——该提交的 src/ 改动不在 v1.0.0 所指的发布产物里）。按项目纪律「tag 前移属作者决定」（前移等于把未经作者复核的代码变更算作已发布），本轮**只登记承担这个本地落后、不前移 tag**，是否前移待作者决定并清理例外表；登记的判据有效性已验（去掉⇒`test_current_tag_gap_is_registered` 红，恢复⇒绿）。
- 稿件对齐 EMSE 语体与修稿轮（GK 轮）：按本地 100 篇 EMSE OA 论文（1,488,314 词）的实测阈值逐项对账——**句长/分号/破折号/连接词/被动/we 时态 7 项达标**，句内 `\textbf{}` 强调降级 41 处为纯文本或 `\emph{}`（段首小节式标签、itemize 标签、逐字引文块保留不动），口语程度副词清零，普适断言（`structurally impossible` → `structurally unavailable`）与修辞化表达（`contributes less than nothing` → `accounts for the remaining −20.6 pp`）按修订清单 P3-2/P3-3 改写；摘要结论句改 EMSE 惯用的 `These results suggest that …`（并压缩 6 词，保持 229 词 / 严格口径 244 词，不触 250 上限）。新增只读判据 `paper/check_emse_style_fit.py`（本稿 vs 语料逐项对照，口径复用 `check_manuscript_style.py` 的现成函数）。
- 修正门禁口径漂移（GK 轮）：GJ 轮新增 `paper-external-numbers` 门禁后 `BASELINE.yaml` 的 `make_targets` / `make_commands` 已更新为 **28 / 30**，但稿件（`paper/` 双盲不入库）仍写 27 / 29；且原句「29 of those 38 scripts」**把命令数当成了脚本数**——实测 `make gates` 的 28 个目标 = 4 个 toolchain + 24 个门禁目标，链上可达门禁脚本恰 **24** 个。稿件正文 3 处、图注 1 处、表注 1 处与入库快照 `docs/study/GATES_FAMILIES_2026-10-27.json` / `REPRODUCTION_CHAIN_2026-10-27.json` 同步为 28 目标 / 30 命令 / 24 脚本；`fig:gates_families` 重画（脚注同步 37 步 / 39 调用点 / 35 阻断 / 2 非阻断）。
- 修正门禁图注的非阻断步数（GK 轮）：实测 `ci.yml` 的 37 个门禁步骤中**非阻断有 2 个**（citation check 走 `continue-on-error`、history-drift 走 `--warn-only`），稿件图注原写「one non-blocking citation check」漏计另一个，表注「35 of the 36 are blocking steps」把步骤数与脚本数混了口径；两处按 `check_invocation_caliber.py` 的实测分解改写，图脚本脚注同步。
- 修复表引用顺序判据的假阳性（GK 轮）：`paper/check_emse_compliance.py` 的 `prose_only()` 只抹白表格环境、**不剥注释行**，稿件 L103 的 `% SRC:` 溯源注释里带 `\ref{tab:falsefix}` ⇒ 该表被当成「正文首次提及」，凭空造出 4 处乱序告警。判据改为同时剥注释（保留行数、行号不漂），实测真乱序为 **0**，22 张表散文口径一致。
- 投稿材料与稿件同步（GJ 轮）：新增 5 条文献引用（`refs.bib` 78→**83 条**）后重建投稿 PDF——**89→90 页**、83 个 `\bibitem`、0 未定义引用、0 致命错误；`title_page.tex` 的「Manuscript body: 90 pages」与 `SUBMISSION.md` 的页数格 / 条数格同步；投稿包构建走「判据 → 编译 → 判据」三步，前置判据实测抓到 `SUBMISSION.md` 的 `refs.bib` 条数脱节（登记 78 vs 实测 83）并**阻断编译**，改后才产出。
- 批量补图（第十轮）投稿材料三件套同步：图数 8→20（title_page 20 figures 22 tables、SUBMISSION Artwork 行 20 张 + caption 命令 33→45）；实测页数 80→89、`refs.bib` 78 条不变；20 张图全部接入稿件并各归其位——表前图用「`\begin{table}`+`\centering`+`\caption`」三行锚点（插在 table 环境之前），避免 figure 落进 table 环境内触发「Not in outer par mode」。
- 五张图统一 `[!t]` 置顶（GG 轮）：`svjour3` 单栏下 `[t]` 把图顶到附录（实测 `fig:study_design` 落 69 页），`[!t]` 拉回正文（3/22/28/29/34 页）、页数 79→78；投稿材料三件套同步（title_page 4→5 图、77→78 页；SUBMISSION 表头与 Artwork 行）。
- RQ4 的 `tab:reclass` 表还原为第 6 张图 `fig:reclass`（GH 轮）：表格↔图再平衡——`tab:reclass` 是迁移到 LaTeX 时被拍平的「数字墙」，还原堆叠条既完成再平衡又忠实 Typst 原设计；正文与附录 B 引用 `Table~\ref{tab:reclass}` → `Fig.~\ref{fig:reclass}`；投稿材料三件套同步（title_page 6 figures 22 tables；SUBMISSION 表数 23→22、图数 5→6），实测 78 页 / 78 条不变。
- 修复覆盖率审计的判决面不再把「已验证」误报成「缺口」（FD 轮）：审计的判决面是**父进程**的 `coverage.xml`，而 ED 轮那批「可选依赖装上但坏了」的负控制正是在**子进程**里验证的——这些路径确实被验证过，审计却把 4 个文件 9 行报成缺口（判决不可信 ⇒ 无人看）。现引入登记表 `docs/fix_coverage_verified_elsewhere.txt`（语法 `<路径>:<行号> @<内容锚点>  # <理由>`，锚点按**内容**而非行号）：登记在册的行从缺口移出、单列为「已在本进程之外验证」；**失效登记不再参与分类**（fail-closed：登记写错不得变成缺口被豁免），且登记表畸形/失效/缺席 ⇒ 审计 rc=1；未登记的未覆盖行**仍是缺口**（分类不得变成橡皮章）。
- 更新日志门面瘦身（FC 轮）：`CHANGELOG.md` 的 162 行顶破了简洁度棘轮（`tests/test_doc_concision.py`：≤ 160 行）——把 `[Unreleased]` 的 DI–DL 四轮逐条条目移入 `docs/history/CHANGELOG_2026-10-27_batches.md`（**原文逐字保留，未删改**；英文版同目录 `.en.md`），门面只保留近期轮次。
- 投稿材料按实测刷新（DG / DE 轮）：按导出脚本重算 `docs/study/PAPER_CITATION_KEYS.md`（64 行，6 行形态计数随生成器修复变化，读者链全绿）；重建投稿 PDF 70 页、`refs.bib` 79 条 ↔ 79 个 `\bibitem`、0 未定义引用，`PAPER_BUILD.md` 与 `paper/tex/README.md` 的旧读数同步。
- 文档门面与测试锁重写（DD 轮）：README / QUICKSTART / CONTRIBUTING / MODEL_CARD / REPLICATION / docs 核心改为简洁结构，中英同步，旧叙事归档 `docs/history/`；文档锁改结构判据（定位区 / 披露小节 / 行数上限 / 索引完备性），退役逐轮标记与行窗口锁。

### Fixed
- agents 层三处实测缺陷修复（GK 轮）：并行审计探针交付 3 个缺陷，**逐条独立复现**后修复——① 确定性守卫**漏检 `numpy.random`**（别名展开写错了槽位：改的是最外层属性名 ⇒ `np.random.seed` 的限定名被打成 `random.numpy`；族判定用顶层名切分 ⇒ 两段族名 `numpy.random` 永远匹配不上 ⇒ `import numpy` 写法**零检出**，而模块 docstring 明示纳入检测）；② 探针快照定位**拿测试文件的行号去索引目标代码**（探针文件 `{module}_probe.py` 的内容是生成的测试代码，行号与目标模块全文不同源；跨文件守卫的 `startswith(target_module)` 又把它放行 ⇒ 定位到目标里无关的函数并把该指引注入修复提示）；③ 执行器**早退路径（EARLY_RETURN / UNAVAILABLE）漏清实例级沙箱状态** ⇒ 陈旧 obs 让下一次调用即使根本没有沙箱也触发 `sandbox_launch_failure` 启发式，把 `error_info.type` 从 `test_failure` 改写成 `kernel_sandbox_unavailable`（污染失败归因）。新增 13 例回归锁（含 2 例负对照）+ K1–K4 变异锚点（全红）+ 中性对照 0 红；覆盖率 97.59%→**97.60%** 行 / 94.59%→**94.64%** 分支。**诚实性核查**：三处修复都落在归档语料**从未触达**的路径上（工件里 `"kernel_sandbox": false`、`deterministic_guard`/`runtime_probe_snapshot` 零命中）⇒ **论文数字不受影响**。
- 门禁家族图上的门禁数字不再硬编码（GJ 轮）：图脚本把标题、图例与 caption 里的门禁数字**写死成文案**（caption 写「35 blocking, **1** non-blocking」，而入库快照 `totals` 里是 `non_blocking_steps: **2**`⇒ 图上数字与单一事实源漂移，正文附录 G 与图对不上，且没有任何机制会红）；现全部改为从快照派生（`figure_data.load_gate_inventory()` 新增 `totals` 读出 + 家族/盘面自检），并补 2 例锁：caption 的每个数字都等于快照值 + 改快照则 caption 必须跟着变（负对照）。
- 新门禁自身的漏洞由 fresh clone 模拟抓到（GJ 轮）：CI clone 里没有 `paper/`（双盲纪律）⇒ 只有「无稿件分支」可走，而该分支原先只判「落点非空」——**空快照、指向不存在行的落点全部判绿**；已补「落点 ↔ 登记册」语义核验（每行落点必须仍指向该键的真实登记行、且那一行逐字记着该数字）+ 快照行数下界（空/被清空的快照按空目录判红），并补变异锚点 H6 与两例负对照。
- 外部读数登记册补登三处漏登数字（GJ 轮）：稿件里的 `19.71%` / `62.20%`（SWE-ABS）与 `38,083` / `714`（复用证据重放）在官方摘要里**逐字一致**、但登记册**没有对应行** ⇒ 那一格对读者不可复核；已补登并把引文接到官方摘要（引文核验门禁的可核引文 60→**76 条**，摘要逐字命中 73 / 标注正文 3 / **未核 0**），官方摘要快照同步刷新（新增 5 篇 × 按版本存）。
- 新门禁的判据漏洞由变异锚点当场抓到（GJ 轮）：「缺登记」标记的断言原本用**裸子串**判断，而快照页眉的判据说明里也有「缺登记」三字 ⇒ 断言被页眉满足、成了假绿（变异锚点 H4 实测 0 红暴露）；改为断言落在**表行**上，4 个变异锚点现已全部转红 + 中性对照 0 红。
- 引文核验门禁的 `main()` rc 判定路径补锁（FF 轮）：citation-quotes 已接为 CI 阻断步骤，但 `main()` 的失败路径（快照缺席 ⇒ rc=2 / 引文未核 ⇒ rc=1 / 输入坏 ⇒ rc=2）此前**零测试**——CI 跑的就是 main()，函数层测好而 main() 判错则整条门禁成装饰品（FE 收口「新守卫无测试锁」的同型形态剩余面）。新增 7 例端到端锁（未核 rc=1 且点名 / 全核 rc=0 负对照 / 快照缺席与损坏 rc=2 / `--list-ids` / `--refresh --xml-dir` / `--json` 落盘合法）；变异锚点 G7（把未核判定改成 `return 0`）实测转红——变异闭环 6 锚点全红 + 中性对照 0 红。
- 收口并行会话 FE 半成品的三个未闭合缺陷（FE 收口轮）：① **新守卫没有测试锁**——FE 给审计工具加的「未测量 ≠ 零缺口」守卫（作用域内存在未被 coverage 测量的文件 ⇒ rc=1）变异实测**删除守卫后全套测试仍然全绿**（守卫是装饰品）；补 `tests/test_audit_unmeasured_scope_fe.py` 5 例真锁（未测量文件单列不进分母 / CLI 判红 + stderr 点名 / 测量齐全负对照 rc=0），变异闭环 5 锚点全红 + 中性对照 0 红。② **快照去版本键指向旧版**——`refresh_snapshot` 处理同 ID 多版本 entry 时「谁排后面谁覆盖」，`2512.08296` 的去版本键（语义 = 最新版，供未写版本的行兜底）被 v2 entry 覆盖而官方最新版是 v3；改按**版本号取最大**（与 entry 顺序解耦）+ 快照数据回核修正 + 3 例回归锁。③ **快照说明文档撞登记册发现模式**——`EXTERNAL_READINGS_ABSTRACTS.md` 命中 `EXTERNAL_READINGS_*.md` 的 glob，登记册文件数锁红、核验器把它误当登记册扫描；重命名为 `ABSTRACT_SNAPSHOT.md`。
- 「修复新增但从未被执行」的真缺口补成进程内真锁（FD 轮）：用项目自带的 `scripts/tools/audit_fix_coverage.py --base v0.8.0` 复算出整个 1.0.0 轮次区间「新增行中本进程从未执行」16 行，逐处核上下文后收掉 8 条真缺口——① `src/cli/app.py` 守卫的失败分支（FC 轮改成显式 raise 后一行未执行）、② `src/db/mysql_client.py` 同名守卫（此前只在 `-O` 子进程里验证）、③ `src/observability/trace.py` 的**名字耗尽**分支（DX 轮承诺「绝不覆盖旧快照」从未跑到耗尽点）、④ 同文件的**调用方半成品清理**（既有用例把故障注入得更早，该分支从未执行）、⑤ `src/utils/trace_viz.py` 的「非 int（含 bool）→ None」、⑥ `src/datasets/dataset_ult.py` 的「未知子集」（CLI 更早以 rc=2 拒绝，此前无入口执行）、⑦ 崩溃任务的诊断导出**成功**路径（既有用例只断言失败分支）、⑧ 通配符含元字符但指向目录的 rc=2 分支。变异工装 `scripts/tools/fd_mutation_verify.py` 实测 **8 个变异全部转红**、中性对照 0 红、collected 37 稳定。
- champion 守卫不再把「假修复率无观测」读作 0（FC 轮）：`select_champion` 的防「刷 passed」约束原式为 `mean_false_fix <= 0.5`，而 `mean_false_fix` 由 `_mean(arm_false_fix[arm])` 计算——**零样本时返回 0.0**，于是「一条假修复率观测都没有」的臂**空洞通过**该守卫并被选为 champion：**「没测」被读成了「测得 0」**。真值语义在 `experiments/_m1_metrics.py`：`repair_rate` 为 None（无 gold 材料 / gold 套件全 skip / rc==5 / 执行超时）时 `false_fix_rate` 恒为 None，而 `detection_rate` 由**另一条**路径独立计算 ⇒ 「检出率可测、假修复率不可测」真实可达。现要求 `n_false_fix >= 1` 才谈得上守卫，报告新增 `n_false_fix` 披露观测数，Markdown 表格零观测显示「不可测」，未过约束逐臂点名成因。10 例新锁（含 2 例反向对照）。
- 运行期守卫被 `python -O` 静默删除不再只修一处（FC 轮）：FB 轮把 FB 的点修复（`assert_no_credit_coupling`）升级为**类锁**——普查 `src/**` 的全部 `assert`（按**内容锚点**登记，禁行号：行号会随上方插行漂移），登记册只收纯类型收窄、新增未登记项即红，并以 `compile(..., optimize=2)` 的字节码探针证明守卫没被优化器删掉（附负对照）；普查顺带查出**另外两处承重守卫**——`src/cli/app.py::_run_single_task` 与 `src/db/mysql_client.py::cursor` 的 `assert` 在 `-O` 下会退化成 AttributeError（前者正是其注释明写要避免的 NPE 形态），改显式 `if` + `raise AssertionError`，异常类型与消息逐字不变。11 例新锁。
- 防 reward-hacking 的运行期守卫不再被 `python -O` 删除（FB 轮）：`assert_no_credit_coupling` 用 `assert banned not in source` 防止 `OrchestrationSearch` 把 hindsight credit 引入 UCB 臂选择，但优化模式会移除整条断言语句；既有测试只验证当前源码无耦合，从未构造「禁用引用 + `-O`」的负向路径。现改为显式 `if` + `raise AssertionError`，保留公开函数名与异常类型。新增 3 例锁：AST 不得含可删除的 `Assert`、禁用引用必须点名拒绝、真实 `python -O` 子进程仍拒绝；修前 2 红 / 1 绿（优化模式实测放行），修后新增与编排搜索既有测试共 72 例全绿。
- 引用豁免表的键从「行号」改为「行号 + 内容锚点」（FA 轮）：6 条豁免只写 `路径:行号`，任何上方插行都让整表失效——EZ 轮一天内被同一道承重锁抓到三次，只能手工重排数字。现条目形态为 `路径:行号 @锚点`（锚点 = 该行内容的唯一片段），扫描按「行号精确命中 → 锚点命中」两级判定，锚点命中逐条披露「行号已漂移，内容未变」；**内容一改锚点消失即恢复命中、要求重判**，锚点只对同一路径生效；真实清单强制每条带锚点。`load_allowlist` 同时由 `set` 改为有序条目列表（不再静默合并重复）。5 例新锁，两方向实测：插入 2 行 ⇒ 绿 + 6 条披露（旧口径 3 红）；改写 M-5 标题 ⇒ 红 + 3 例红。
- 测试与提交守卫的两处静默分叉不再成立（EZ 轮）：① 语料形状锁的判定面不再取作者机盘面——AR/AQ 三个锁把真实 trace 语料钉成「1,456 份文件 / 9,502 span / 4,368 token 属性 / 逐字段核对 ≥ 3,306」，扫描面却是 `rglob` 的**盘面**——`experiments/results/**` 按 Zenodo 纪律不入库，入库面只有 760 份，而盘面随本地重跑长到 1,495 份 ⇒ 作者机必红；fresh clone 又达不到 `require_full_corpus()` 的 1,456 盘面下界 ⇒ CI 必 skip，同一批断言在两份环境里都不执行。现形状断言只吃入库面（`git ls-files` ∩ 盘面），单一事实源收在 `tests/_corpus_guard.py`（`archived_trace_files()` / `local_extra_trace_files()` / `shape_problem()` / 四个钉值），本地未入库的 735 份语料只跑不变量、不进分母；git 不可用时显式 skip 而不降级到盘面。另设 `AUTHOR_ONLY_LOCKS` 登记表 + AST 普查锁：仍以全归档为前提的 5 个锁逐条写明理由，新增未登记的作者机专属锁即红——「CI 里永不执行」不再能是新增测试的默认形态。7 例新锁（含 3 条变异锚点实测全红），`src/` 零改动 ⇒ 覆盖读数不变。 ② pre-commit 钩子不再在本机恒红：钩子用系统 `python3`（缺 PyYAML），`check_baseline.py` 因此走最小行解析兜底，而该兜底把**每个**非缩进行都当成节起点——顶层标量 `last_verified` / `error_categories` 被读成 `{}`，结构校验恒红 2 项（HEAD 实测：系统解释器 rc=1、venv rc=0）；后果不是少判一项，而是唯一提交路径变成 `--no-verify`，把密钥泄漏 / 仓库卫生 / ruff 三道守卫一起关掉。现兜底按 YAML 语义区分「冒号后有值 = 标量 / 冒号后为空 = 节」、解析抽成 `_parse_baseline_text()` 使其可测，钩子优先选用 `.venv/bin/python3`（与同文件 RUFF 选择逻辑同口径）；5 例新锁（含缺 PyYAML 端到端 rc=0 与钩子接线），变异退回旧解析 ⇒ 4 红。 ③ 远端 CI 在两条「只在 fresh clone 成立」的前置上真红（ec0edce2，3.12/3.13/3.14 同红）：空库 bibtex 判定走仓库 `paper/tex/spbasic.bst`（`paper/` 不入库）⇒ 先报「样式文件缺席」；`check-dataset` 端到端用例把 skip 写在 `rc == 0` 断言之后 ⇒ 无缓存时先判红。现空库判定显式给临时 bst（加「仓库 BST 缺席时结论不变」护栏），数据守卫前移并读 `AITESTER_QUIXBUGS_DATA`（附接线锁）；fresh clone + 空 HOME 复跑 = 2 passed / 1 skipped。 ④ **`v1.0.0` 前移**到本轮收口提交（作者明确同意 force-update 已发布引用）：发布产物与仓库重新一致，`docs/release_freshness_allowlist.txt` 的例外条目随之删除（表为空 = 没有需要承担的落后）；该门的接线锁原本断言「例外表必非空」——与前移后的状态自相矛盾，现改按本地落后数双向判（落后未登记 ⇒ 红；不落后而表非空 ⇒ 红）。
- SPEC 链的「三开关一体」校验不再只查显式键（EY 轮）：`ArmSpec.__post_init__` 用 `if k in self.env` 过滤后比状态，只写一个/两个 `SPEC_*` 键的臂全部通过；而干净基线把缺省键压成 `false`，运行期就是拆开的链——只开 IR 有 `spec_ir` 却没有 compile_rate 与 oracle 判定，只开 oracle 经 `test_plan.logic_analysis` 注入而 IR/DSL 观测恒 `None`，结果无法按「SPEC 链」归因；登记表测试复制同一盲点（`if k in arm.env`）与实现互相认证。现按生效值比较（缺省 = false）、错误消息列出三键生效态，登记表测试改整链判据；11 例新锁（修前 7 red：6 条部分链 + 生效态消息例；4 例负向对照/护栏）。
- 搜索报告的「设计集」分母不再被观测覆盖顶替（EX 轮）：`build_search_report` 把 `rows` 里 distinct `(task, seed)` 写进 `config.n_cells`，而归因 MD 把它标注为「设计集」——预算先到即停或臂提前退出时，同一行自相矛盾（「12 任务 × 3 种子 = 16 cell」），真实分母在工件中不可恢复。现 `config.n_cells` = 设计集唯一 cell 数，新增 `coverage.cells_observed` 披露实触达数，MD 增「覆盖：observed / total cell（pct）」行；5 例锁（4 红→绿 + 1 负向对照），真实 CLI 复核 4 cell 设计集 / 2 cell 覆盖显示 50.0%。
- config.py 声明的键不再有「零读者」（EW 轮）：51 个公开键里 4 个在 `src/` / `experiments/` / `scripts/` 零引用——`ORCHESTRATION_SEARCH_MAX_UNMEASURABLE` 的注释承诺「单臂不可测累计超过上限即退出 UCB 池」，但唯一构造点 `experiments/run_orchestration_search.py` 从不传该参数，构造默认 5 恒生效（设置环境变量不改变任何行为）；`DOCKER_ENABLED` / `DOCKER_IMAGE` 是 `EXECUTOR_USE_DOCKER` / `EXECUTOR_DOCKER_IMAGE` 的幽灵重复（全仓零读者），`DEFAULT_LLM_CONFIG` 是纯死符号。现给实验驱动补 `--max-unmeasurable`（默认读 config）、报告 `config` 披露生效上限，删除三个零读者键及其 `.env.example` / 环境变量登记 / 设计文档引用；6 例新锁（4 红→绿 + 2 负向对照：合成的死键必须被普查抓到、`from config import` 与 `getattr(cfg, ...)` 读法必须被认作消费），`src/` 改动仅报告披露 ⇒ 覆盖读数不变。
- MySQL 连接池的构造契约不再只由 mock 认证（EV 轮）：`MySQLClient.__init__` 把 `timeout` 与 `idle_timeout` 传给 `PooledDB`，但 DBUtils 3.1.2 没有这两个形参——多余关键字被转发给 `pymysql.connect`（同样不认），真实构造/取连接必抛 `TypeError`；既有测试把 `PooledDB` 整体 mock、只断言收到了 `idle_timeout`，等于给不可执行的构造契约发证书。现移除两个无效形参，`MYSQL_POOL_TIMEOUT` 改落到驱动支持的 `connect_timeout`（兑现「建立连接超时」，并披露池耗尽时 `blocking=True` 无获取超时），死连接探测显式声明 `ping=1`；5 例新锁（4 红→绿 + 1 判据负对照），删除认证缺陷的旧 mock 断言。
- 复杂度感知路由不再只在 benchmark harness 激活（EU 轮）：`MODEL_ROUTING_STRATEGY=complexity_aware` 是默认值，但 `complexity_class` 的唯一写入点是 `experiments/run_benchmark.py` 的事后补写，`create_initial_state`（CLI `aitester run` / 编排搜索 / e2e 探针的共同入口）把四个路由字段初始化为 `None`——`APIManager._build_node_list` 的复杂度分支与 `BaseAgent._reorder_api_groups_by_complexity` 在 CLI 下永不触发，`fixed` 与 `complexity_aware` 不可区分。现把评分收敛到 `complexity_router.score_source_complexity` / `score_task_complexity`（单一实现），`create_initial_state` 构造时按策略写入四字段（`fixed` 保持历史 `medium`），benchmark 只传 `task_metadata`（保留 `num_files` 与解析失败时的 `cyclomatic_complexity` 兜底）并删除内联重复实现，编排搜索同步传 metadata；12 例新锁（先红后绿）+ 迁移文件 8 例（原 6 例改为驱动真实共享入口，新增 2 例：解析优先与导入计数异常兜底）。
- 复杂度感知路由不再在多 provider 端点构型下空转（ET 轮）：`src/agents/base_agent.py::_reorder_api_groups_by_complexity` 以 `model_name` 为唯一键建成本表——同一模型挂在多个 provider 端点、各端点 `cost_weight` 不同时后写覆盖先写，所有分组权重恒等，`sorted` 的稳定排序退化为原序，simple / medium / complex 三档全部空转；而 `complexity_router.py` 承诺的正是「同模型不同 provider 端点，或同 provider 不同 cost_weight」，A15 的 `APIManager._cost_weight_for` 也已按实例取成本，两条路由口径分裂。现按实例键 `(base_url, model_name)` 建表，无 `base_url` 的注入配置回退模型级键，未知端点保持 1.0 基准（不继承同模型另一端点成本）。5 例新锁（4 红→绿 + 1 口径护栏）；本机 `.env.local` 只有 1 个 LLM 实例（`len(all_configs) > 1` 不成立、重排函数不会被调用），缺陷仅在文档承诺的多端点构型下激活。
- 双语文档门禁的「H2 骨架按序对齐」不再对翻译文档空转（ES 轮）：`check_bilingual_docs.py` 的 P2 结构化对照把中英 H2 标题归一化后做**字面**比对，翻译标题天然不同——实测 20 对配对中仅 CHANGELOG 有 2 个跨语言相同标题，其余 19 对永不触发；合成「编号章节互换」与「少一章（总数差 1，在 ±2 容差内）」两个样本旧实现均判无漂移。现改用语言无关的骨架指纹：H2 编号序列（"一、"/"1." 折算整数）逐位相等，H2 数相等时逐节比对 H3 小节数；真语料 13 对带编号、20/20 骨架一致（strict 零警告），6 例新锁（含「可比分母 ≥10」反空转锁），`src/` 零改动 ⇒ 覆盖读数不变。
- 布尔开关不再声明不可达的关态（ER 轮）：`e7_evidence_prepass` / `repair_ceiling_analysis` / `repair_review_worksheet` / `repair_sample_selection` 的 `--pool-seeds` 与 `emse_ult_gold_diagnosis` 的 `--with-generated` 都是 `store_true, default=True`——传与不传等价、`--no-*` 不存在，帮助文本却写「默认开」；前者是预注册固定的多种子拼接口径，后者的关态会在 README §2c 渲染成误导性零值（`n_tasks_with_generated=0`）。现按 EQ 先例移除 5 个旗标、把默认语义钉死在调用点（`pool_seeds=True` / 生成门常开），4 个脚本的 `main()` 增加 `argv` 形参使解析面可测；20 例新锁（16 红→绿 + 4 口径护栏，含 `statistical_analysis` 真开关的邻接护栏），`src/` 零改动 ⇒ 覆盖读数不变。
- 模型目录工具的 `add` 子命令与重放脚本的 `--repeat` 不再与实现脱钩（EQ 轮）：`scripts/tools/expand_models.py add --name/--url/--key` 声明了三个必填旗标，`cmd_add` 却读 `args.model_name/base_url/api_key`——文档里的主命令一给旗标就 `AttributeError`（rc=1），从未成功执行过；`experiments/oracle_examples_replay.py --repeat N` 被接受且全程无 `args.repeat` 读取，用户以为做了 N 次确定性验证（同目录三个重放脚本都实现了整批重复 + body digest 比对，本脚本只抄了旗标）。现把三个旗标的 `dest` 对齐 `cmd_add`（CLI 表面不变），删除从未实现的 `--repeat`（同型 `emse_batch5_orchestrator.py --skip-rerun` 因文件被 `.gitignore` 排除、不在跟踪面而不入库）。5 例新锁（2 红→绿 + 3 口径护栏）。
- 批量配置脚本不再用占位符覆盖真实凭证（EP 轮）：生成物 `scripts/tools/generate_batch_config.py` 只为「模型列表为空」设了防覆盖守卫，缺 `*_API_KEY` 或 provider 时仍以 `w` 模式写出 `your-<provider>-api-key-here`、rc=0——现有可用 `.env.local` 会被伪配置替换；usage / argparse 里声明的 `--template` 从不读取（传了静默忽略）。现写入前逐条检查 provider 与对应 API Key，任一缺失即列出原因、rc=1、输出文件原样保留（部分缺 Key 整批拒绝）；删除幽灵开关；在盘脚本与生成模板由测试逐字节对账。7 例新锁（5 红→绿 + 2 口径护栏）。
- 缓存开关的显式关闭拼写不再只在运行时生效（EO 轮）：`AITESTER_LLM_CACHE` / `AITESTER_CACHE_ISOLATE_MODEL` 是 opt-out 开关，运行时走 `env_flag_opt_out`（`false` / `0` / `off` 关），但 `experiments/run_benchmark.py` 三处仍手抄 `!= "0"`——X1 命名空间自设、`cache_enabled`、`cache_isolate_model` 在 `false` / `off` / 大小写空白变体下全部按「开」处理；同一份工件可同时出现 `env_snapshot="false"`、`cache_enabled=true`、`cache_namespace="seed42"`。三处改用 `env_flag_opt_out`，缓存关闭时不再自设命名空间；19 例新锁（12 红→绿 + 7 口径护栏），历史工件一字节不动，`src/` 零改动 ⇒ 覆盖读数不变。
- 批次工件自述的 harness 开关不再与运行时解析脱钩（EN 轮）：`provenance.harness` 用裸 `os.environ.get(...).lower() == "true"` 解析 8 个运行时开关 + 1 个零消费者幻影键，而运行时走 `env_flag` / `env_flag_opt_out`——`EXECUTOR_USE_VENV=yes`、`KERNEL_SANDBOX_ENABLE=on`、`COST_BUDGET_ENABLE=1` 等 8 个实测场景工件自述与生效值相反，`--enable-rag` 时同一工件顶层 `enable_rag=true`、harness 块却 `rag_enabled=false`。现与运行时同一解析器、RAG 披露 `_apply_rag_setting` 生效值；删除运行时零消费者的 `truncation_first` 幻影键。21 例新锁（16 红→绿 + 5 口径护栏）；`src/` 零改动 ⇒ 覆盖读数不变。
- 批次 provenance 的停止原因词表不再与 `StopReason` 枚举脱钩（EM 轮）：harness 披露块承诺「停止规则可复核」，但 `retry_stop_rules.stop_reasons` 是手写 7 值字面量、枚举已 13 值——`recursion_limit`（EJ 起可落盘）、`coverage_stall`（P2-4）等 6 个真实终止原因从未出现在工件自述里，读者会以为 harness 只会以旧 7 值停止。 现由枚举派生（单一事实源），新增值自动进入新批次工件；历史工件一字节不动。6 例新锁（3 红→绿 + 3 口径护栏）；`src/` 零改动 ⇒ 覆盖读数不变。
- P2P 门禁判无效的行不再在失效分布里冒充「运行异常/限流」（EL 轮）：批次汇总承诺 harness_invalid（基线 P2P 不达标）实例「从统计中剔除」，但 `_aggregate_failure_buckets` 只看 `failure_bucket` 是否为空——门禁早退行（从未进入工作流）与真崩溃同形计入 `unclassified_rows`，报告层还把它们写成「无工作流终局状态〔运行异常/限流〕」。
  现单列 `harness_invalid_rows` 并从桶分母剔除（恒等式 total + unclassified_rows + harness_invalid_rows == total_rows），`render_markdown` 分因披露两种排除；逐行四键仍 `None`（不臆造桶）。10 例新锁（8 红→绿 + 2 口径护栏），分母口径变化已在 `MEASUREMENT_INTEGRITY` §105 披露。
- 已知崩溃原因不再与归因列自相矛盾（EK 轮）：EJ 轮把 `GraphRecursionError` 落成结果行 `stop_reason="recursion_limit"` 后，失败分支仍把归因四键硬编码为 `None`——同一行「原因已知、归因未知」，批次聚合继续把这类确定性 harness 崩溃计入 `unclassified_rows`，ADR-0026 的 harness 归因在生产工件里仍不可读。 现让 `_failure_attribution_for_result` 接受已知 `stop_reason`（仅 `final_state=None` 时生效），失败分支四键取归因结果；无原因崩溃仍四键 `None` 并单列。7 例新锁（4 红→绿 + 3 口径护栏），分母口径变化已在 `MEASUREMENT_INTEGRITY` §104 披露。
- 编排硬上界的崩溃不再被折叠成「无终局状态」（EJ 轮）：`StopReason.RECURSION_LIMIT` 与失效分类法的 `recursion_limit → harness/harness_side` 映射（ADR-0026）都在，但全链路无写入点——基准跑批的异常分支把结果行 `stop_reason` 硬编码为 `None`，图递归上限触顶这一**确定性**原因在工件里退化成「状态信息不足」，分类法承诺的 harness 归因永不命中。
  现新增 `stop_reason_for_exception`（仅 `GraphRecursionError` → `recursion_limit`；普通 `RecursionError` 是节点代码缺陷不得冒充），两条异常分支落盘该标签；桶分布分母口径不变（无终局状态仍单列 unclassified_rows）。10 例新锁（8 红→绿 + 2 口径护栏）。
- 单次 LLM 调用的全局预算不再被时钟回拨绕过（EH 轮）：`LLM_CALL_BUDGET_SECONDS`（默认 600s）此前用 `time.time()` 算截止点，NTP 阶跃校正 / VM 快照恢复导致墙钟回拨时截止点随之后移、预算永不触发；且检查只在换模型时进行，同一模型内的重试阶梯（1/2/4s）与 429 退避（最长 30s）越预算后仍会继续发请求（与 `COST_MODEL` 的「不继续发请求」相反）。 现改 monotonic 计时、每次真实请求前复查、429 等待按剩余预算截断，预算耗尽以 `LlmCallBudgetExceeded` 收口。6 例新锁。
- 时间预算异常不再被「预算封顶」读者漏认（EI 轮）：`LlmCallBudgetExceeded` 原为 `RuntimeError` 兄弟类，而 planner / generator / debugger 与 `determine_stop_reason` 只认 `BudgetExceededError`——超时照常降级，但 `budget_exceeded` 永不落盘、`BUDGET_EXCEEDED` 终止原因不可达，`.env.example` 的「触发 5.4 预算封顶」承诺落空。现改为 `BudgetExceededError` 子类（`unit="seconds"`、`consumed=None` 表示未知），三节点与停止原因零改动自动同待遇。7 例新锁。
- 默认开启的安全/质量守卫不再被坏值静默关闭（EG 轮）：venv 沙箱、凭证与 pip 白名单、危险 API、命名契约、注入输出扫描、证据门、P2P 门禁、容器只读/断网共 10 个开关（11 处读取）走正集 `env_flag(name, True)`，`yes` / `enabled` / 拼错 / 空串都会把守卫判关——实测危险补丁被放行、`MYSQL_PASSWORD` 重新进入子进程环境、容器丢掉 `--read-only` 与 `--network=none`。
  现统一改走 `env_flag_opt_out`：仅 `false`/`0`/`off` 关闭，坏值保持开启；默认关的特征/成本开关仍为正集（坏值不得隐式开启）。31 例新锁（24 红→绿 + 7 边界），先红后绿。
- 可选依赖「装上但坏了」不再击穿降级契约（ED 轮）：12 处 `try: import … except ImportError` 只拦缺包，扩展 ABI / 传递依赖冲突抛出的 RuntimeError/OSError 会穿过去（chromadb 损坏时整个 CLI 无法启动）；现在导入期任意异常都降级告警。12 例新锁 + 1 例负控制。
- 读侧「损坏」判定不再停在 JSON 语法层（EE 轮）：15 处 JSON/JSONL 读侧只捕 `json.JSONDecodeError`（只覆盖解码后文本），坏字节（截断多字节 / GBK 保存）在解码期抛 `UnicodeDecodeError`——行级「坏行跳过」变成一行拖垮整份文件，整文件「损坏 → 空值」直接抛出。 行级读侧改二进制逐行严格解码（不吞坏字节），整文件补同口径降级，策略库写侧仍 fail-closed 不覆写。15 例新锁。
- 非有限浮点环境值不再静默改写控制流（EF 轮）：6 处本地解析只捕 `ValueError`，而 `float("nan")` 不抛——
  NaN 夹到上界、`-inf` 夹到下界：语义缓存把无关条目当命中返回、覆盖率停滞恒判、风险中阈值变 1.0 绕过审批、
  失败知识库排序退回插入序、`long_sleep` 守卫失效。解析统一委托 `env_float`（告警 + 默认值），有限值钳制不变。49 例新锁。
- trace 可视化 / 回放的读侧词汇与写侧对齐（EC 轮）：写侧只写 `node` 事件、`passed` 三态与 `token_usage`，读侧却按 `node_end` / `test_passed` / `token_delta` 读——100 份真实轨迹 100% 渲染成「无节点记录 + FAIL」（写侧 100/100 通过）；节点时间轴、三态判定与回放演化现按写侧字段读。12 例新锁；状态通道重登记 2/11 → 3/12。
- 发布新鲜度门禁的例外登记不再「登记即通行」（EB 轮）：登记表头的两条语法承诺——条目必须写理由、条目
  必须对应当前最新 tag——此前只在「最新 tag 未登记」一个分支检查一次；当前 tag 已登记 / tag == HEAD /
  仓库没有 `v*` tag 三种状态下，失效或空理由条目静默通过。现在两类缺陷在任何绿色分支之前统一判红并逐条
  点名（无理由条目先于网络判定，API 不可达时同样生效）。9 例新锁。
- OTel 导出的 span 区间不再落在未来（EA 轮）：node / task_end 的记录时刻是操作**结束**，导出器却把它当起点，每段时长向未来延伸（真实会话实测 task_end 晚于导出时刻一个任务时长）。现在起点 = 记录时刻 − 时长，区间闭合在结束时刻；duration > ts 时裁到 `[0, ts]` 并披露 `span_interval_clamped`。14 例新锁。
- OTel 导出的整任务时长不再恒为 0（DZ 轮）：`record_task_end` 写 `duration_s`（秒）、导出器只读 `duration_ms`，task_end 时长被静默丢成 0。现在按字段名选单位（`duration_s` 优先），坏值给 `duration_s_*`。7 例新锁。
- 追踪会话不再因目录不可建而反噬任务（DY 轮）：`AITESTER_TRACE_DIR` 指向普通文件之下曾抛 `NotADirectoryError`、`run` 把任务改写成崩溃；现在告警后降级为仅内存快照，`duration_s` 也不再只在文件模式下存在。4 例新锁。
- 失败追踪导出的参数与并发落点不再失真（DX 轮）：`limit=0` 曾静默导出全部快照、负数反向切片；
  同一秒内的多次 / 并发导出又共用文件名、后写覆盖先写。现在 0 / 负数抛 `ValueError`，`O_EXCL` + 序号重试、绝不覆盖旧快照。11 例新锁。
- `--dump-trace-on-failure` 的失败态不再静默或反噬任务（DW 轮）：目录创建失败曾把已完成任务改写成崩溃，
  无快照 / 写盘失败又静默。现在三态可区分（`trace_dump_path` / `trace_dump_error` + stderr 原因），崩溃任务同样尝试导出。9 例新锁。
- `doctor` 的 `dataset-check-cli` 探针不再要求已移除的文本（DV 轮）：QuixBugs 现在输出「共加载 N 个任务」+「未提供 quality_report，跳过全量校验」，旧探针把能力缺失报成故障；现接受「通过 / 显式跳过」（缺失即红）。净增 4 例（探针共 6 条）。
- `check-dataset` 查出加载问题不再报成功（DU 轮）：报告非空时只打 warning、退出码仍为 0，与「0 = 无问题」相反；现在报告非空逐项列出并以 1 退出，能力缺失与源码待导出仍为披露；QuixBugs 探针接受「经校验通过 / 显式跳过」。11 例新锁。
- `doctor --json` 的三条出口现在共用 13 键 schema（DT 轮）：内部异常只输出 4 个键、正常 12 个，
  `jq -e '.conclusion == "pass"'` 在崩溃时取不到键。现在崩溃时 `matrix.status` 记 `internal`、
  未采集的聚合记 `null`（未知 ≠ 全 0）、脱敏原因进 `error` 并以 1 退出。13 例新锁。
- 任务崩溃的结果面不再与成功路径不同构（DS 轮）：崩溃结果只有 5 个键、成功有 14 个，`jq '.coverage_ok'` 在崩溃任务上取不到键，
  人读模式把缺键兜底画成「迭代 0」；现在两条路径共用全部键（未知判定显式 `null`），原因写 stderr、迭代列显示 `N/A`；状态通道重登记 47 键 / 99 站点。9 例新锁。
- `run --func` / `check-dataset --subset` 不再把显式空值当作「未提供」（DR 轮）：脚本里
  `--func "$FUNC"` / `--subset "$SUBSET"` 变量未展开时 click 收到 `""`，按 falsy 判定
  等于悄悄放宽口径——`check-dataset examples --subset ""` 实测输出「（子集: 全部）」并
  rc=0，`run … --func ""` 把空串原样交给任务（按函数数消耗 LLM）。现在两者都按用法错误
  rc=2 在加载数据 / 启动任务之前拒绝；省略选项才是「全部」口径。8 例新锁。
- `check-dataset` 的状态图标只有一个来源（DQ 轮）：`info_msg` / `warning_msg` 等助手已自带
  `ℹ ` / `⚠ ` 前缀，六个调用点又手写图标，实测输出 `ℹ   ✓ 加载质量健康`，警告路径会是
  `⚠ ⚠ …`；三处成功事实（单个任务健康 / 全量质量通过 / 源码完整）还用蓝 `ℹ` 冒充成功。
  现在图标由助手唯一提供，成功事实改用 `success_msg`（绿 `✓`），并以 AST 结构锁约束
  `src/` 全部助手调用不得自带图标。15 例新锁。
- `run` 不再把目录当任务、也不再重复执行同一文件（DP 轮）：显式目录 / 特殊文件被
  `glob.glob` 原样收下，任务在 `open()` 处抛 `IsADirectoryError` 后被记成「任务失败」
  （rc=1），用法问题伪装成测试没过；同一文件经显式与通配符重复命中时会重复进入工作流、
  重复消耗 LLM。现在目录 / 特殊文件与「通配符只匹配到目录」按用法错误 rc=2 在启动前
  拒绝，重复目标按绝对路径去重、只跑一次。11 例新锁。
- `run` 的帮助与文档不再宣称不存在的报告面（DO 轮）：help 不再泄漏 rich/Markdown 标记
  （`[bold]…`、`**…**`）；detection / repair / false_fix 改述为基准评估面
  （`experiments/_m1_metrics.py`，需要 gold 材料）并以「不在 CLI 输出中」披露；模块地图
  不再把 M1 记在 `src/measurement/`；批次摘要新增覆盖率三态（达标/未达标/不可测），
  `run --help` 与 api_reference 写明阈值不改变退出码。16 例新锁。
- `check-dataset --subset` 不再静默忽略或静默替换（DN 轮）：不支持子集的数据集（内置示例、QuixBugs、
  BugsInPy、Defects4J、synthetic 等）此前传 `--subset lite` 仍 rc=0 并输出「（子集: lite）」，
  实际加载全量数据；ULT 请求 `lite` 而 `ULT_Lite.jsonl` 缺失时同样静默回退。现在不支持 / 未知子集按
  用法错误 rc=2 拒绝（提示由 `dataset_subset_support` 能力表派生），请求子集未生效时 rc=1 并披露原因；
  `load_dataset` 契约不变（`subset` 仍被接受，ULT 回退新增 `subset_fallback_reason`）。14 例新锁。
- `clean-venv-cache` 的报告不再与磁盘现实脱节（DM 轮）：`shutil.rmtree(..., ignore_errors=True)`
  会吞掉一切删除失败，紧随其后的 `except OSError` 是死分支——实测把缓存目录设为只读后，
  命令仍打印「✓ 已删除 1 个 venv（释放 0.0 MB）」且 rc=0，目录原封不动（旧测试用
  `MagicMock` 让 rmtree 主动抛异常，锁住的是 mock 形态而非真实行为）。现在按目录是否真的
  消失区分 `removed` / `failed`，失败逐项报告并以 rc=1 结束，释放空间只累计真正删掉的目录，
  释放空间不再虚报。同时 `--list-only` 此前静默忽略 `--max-age-days` / `--max-size-mb`，
  预览列出全部条目；现在与清理复用同一判定，输出 `[将删除]` / `[保留]`，预览名单与实删
  名单同源（8 例真实文件系统测试锁，先红后绿；旧 mock 锁按新契约改写）。
- 更早四轮（DI–DL）的逐条记录已归档到 [docs/history/CHANGELOG_2026-10-27_batches.md](docs/history/CHANGELOG_2026-10-27_batches.md)（**原文逐字保留，未删改**；英文版同目录 `.en.md`）。
- 早前各轮（DE / DG / DH）的逐条记录已归档到 [docs/history/CHANGELOG_2026-10-28_batches.md](docs/history/CHANGELOG_2026-10-28_batches.md)（**原文逐字保留，未删改**；英文版同目录 `.en.md`）。

## [1.0.0] - 2026-10-25

### Added
- 复现包 `REPLICATION.md`、`REPRODUCE_SKIP_TESTS` 显式逃生口与零 LLM 复算链。
- 发布判据 ADR-0036；发布新鲜度守卫。

### Changed
- repair 读数采用修正口径 v2（39.31%，57/145 可重放行，gold 独立裁决）；
  历史口径见 `docs/design/repair_caliber_matrix.md`。
- 模型调用默认关闭 thinking、默认开启 JSON 模式（ADR-0031）。

### Fixed
- 修复 `repair=0` 两起测量伪影：patch 字段围栏残留、跨文件任务未物化。
- 文档命令可执行性、引用库可编译性等门禁补链。

### Security
- 敏感/私有路径纳入仓库卫生门禁；`.env*` 与私有目录不得被跟踪。
- git 历史存量泄漏处置见 `docs/security/history_leak_remediation_runbook.md`。

## 更早版本

0.8 / 0.9 系列与更早的逐轮记录见归档（原样保留，链接不保证可达）：
[README（中文）](docs/history/README_2026-10-26_full.md) · [README（英文）](docs/history/README_2026-10-26_full.en.md) ·
[CHANGELOG（中文）](docs/history/CHANGELOG_2026-10-26_full.md) · [CHANGELOG（英文）](docs/history/CHANGELOG_2026-10-26_full.en.md)。
