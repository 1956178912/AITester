# 测量完整性：口径分叉的五种形态与修复方法论

最后更新：2026-10-25（**CL 轮：新增 §83——CI 步骤顺序是树状态的一部分（fresh clone 验证必须回放树变异步骤：本地全绿/CI 全红的差异不是代码，是快照步骤写在 pytest 前造成的 +1 计数漂移）；归因面自身会骗人（诊断 grep 锚行首，xdist 的 `[gwN]` 前缀行整份漏捕 ⇒ 「无失败用例行」假象）；步骤顺序是可锁的（快照步骤序号 > pytest 步骤序号，变异验证红）**。修复 = 快照生成/上传移至 test 作业最末端 + 诊断 grep 容前缀 + 1 例顺序锁。此前 **CK 轮：新增 §82——数据换代必须复盘「描述语料的文档」（代码面有门禁、散文面没有；REPLICATION.md 15 处失效引用靠路径复扫当机械判据）；在库文件里的假声明与未登记声明同族（CITATION.cff「归档元数据已备」指向从未存在的文件）；编辑引入的失实只能靠复扫发现——本轮 §7 编辑把假声明抄进 REPLICATION.md，被收尾前的复扫当场抓住，复扫是编辑流程的组成部分；「运行为产」与「在盘工件」必须在文档里分开标注（charts 类路径不标注则复扫永远 miss）**。新增 `docs/adr/0036-v1-release-criteria.md`（1.0.0 判据）与 REPLICATION.md 四节重写。此前 **CJ 轮：新增 §81——登记面可以没有读者，而 set 语义会把重复登记吞掉（12 条豁免键写两遍 = 24 行，`load_allowlist` 返回 set 静默合并，门照绿；文件内「现状：零豁免」声明未随补登记更新 ⇒ 声明与内容双向失实，而全仓没有任何测试/门禁读这份清单）；一致性守卫的 slack 只查总量不查拆分（`798d8c72` 实测 12,491/254 vs BASELINE 登记 12,458/287，collected − passed ≈ skipped 恒等在 slack 内成立 ⇒ 33/33 的拆分漂移不可见）；行锁的误绿可靠历史链续命（AO3 锁钉 `**CH round:` 而头部已至 CI 轮，历史链 `Previously **CH round:` 让断言恒真，误绿存续两轮）；fail-crash 不是 fail-closed（`collect_files` 容忍仓库外 `--files` 路径、扫描段 `relative_to` 抛未捕获 `ValueError` ⇒ `_rel()` 兜底——容错路径只做一半比不容忍更危险）；`[SKIP]` 是披露不是红灯（复算链退出码只由 FAILED 命令数 + SHA256SUMS 失败数决定）**。新增 `tests/test_citations_gate.py` **13** 例锁（真实树登记面 5 + 合成面 8）+ `check_citations.py` `_rel()` 真 bug 修复 + 豁免清单 24 行 → 12 键去重；变异 **3+1**（重复键 2 红 / 陈旧行号 3 红 / 回退 `_rel` 3 红 / 中性对照 0 红）。此前 **CH 轮：新增 §79——「受检面 = N」必须为「N 里某个成员读不到」配一条红（首版把在盘门的源码缺席与不可解析都折叠成「没有 argparse」，M38 存活才逼出来，补两档 fail-closed；披露是均值不是判据）；一条断言只能钉一行（M68：同一段文本在 `[OK]` 行与通过行都出现，删掉通过行的数字没有任何断言变红）；「无读者 0」这类绿可以由 token 命中撑起（CG 判读者活性、本门判 dest 活性：改前两条判据档开关被 ci.yml 真实传入而 dest 从不被读）；代理态说的是「保证来源不在自己身上」（`required=True` 互斥组里的 `--verify` 今天等价、摘掉 `required=` 或加第三个模式就静默失效 ⇒ 四态加分母自校验，代理与死都记红）；等价区写清单而不凑锚点（M06 连同另 5 处共 6 处）；崩溃式扇出不等于锁定度（M53 红 32 例里多数是 KeyError）；反子串判据的第一次误用，受检对象是写它的人（本门 docstring 提到 `vars(args)` 就被自己判成不可判）；静态判据必须登记自己的误读方向（注释里的 `args.x` 会被算成一次读，是假绿方向；本轮普查现值 0）；不设豁免表是一项口径选择（装饰性开关只有接线或删除）**。新增 `scripts/gates/check_flag_effect.py`（`make gates` 新目标 `flag-effect`，五档判定 + 三行 `[SURFACE]` + 「本门复算 == BASELINE == §1」三处同值对账）、99 例锁、75 锚点变异工装（全红 + 中性对照 N01 0 红、collected 逐锚点恒 99、墙钟 334s）与两条写侧接线；分母恒等式 **73 = 活 73 + 代理 0 + 死 0 + 不可判 0**。此前 **CG 轮：新增 §78——判据按结构不按子串（一条 YAML 注释能造出已进基线的「非阻断 3」，子串 3/26 vs 结构 2/27；调用点全文正则 32 vs 只数非注释行 30）；注释不是登记面（只改行尾注释等于没改）；「在链上」≠「以同一口径在链上」（两两比得 3 处不对称、只比一对得 1；OR 语义替缺席的一侧说谎）；「不阻断」有三层，最后一层是 shell（`continue-on-error` 是步骤属性键、`set +e` 对后续命令一直生效、`if`/`&&`/`||` 抑制非零）；读者判据的松紧本身就是口径（宽松 52/0 无读者 vs 严格 33）；判据档记红、呈现档记数，分母恒等式逼出占位值（`passed_flags` 71 → 14）；一条锁看似覆盖不代表碰到实现（M59 存活 → 补 e18）；改前实测必须绑定一棵可重建的树（69/31/9 与 71/33/10 两棵，差值恰为本门自身的 `--list` 与 `--quiet`）；预登记跑绿不等于终跑绿，且 GFM 表格连行内代码段里的竖线也照样切格（第一次终跑 rc=2 正红在本轮自己写的登记面：3 列表头被读成 8 格 / 4 格）**。新增 `scripts/gates/check_invocation_caliber.py`（`make gates` 新目标 `invocation-caliber`，五面判定 + 15 条机器可读登记表 + 六行 `[SURFACE]` 口径披露）、66 例锁、70 锚点变异工装（全红 + 中性对照 N01 0 红、collected 逐锚点恒 66、墙钟 424s）；分母恒等式 **71 = 传过 14 + 代码锁 26 + 登记 9 + 判据档 0 + 呈现 22**。此前 **CF 轮：新增 §77——登记面的手写数字必须有可解析的声明位并被就地复算（登记 **999** / HEAD 干净树复算 **1037** / 工作树 **1050**，跨约 14 轮无人复算）；被指认为权威源的那一节自己也要有读者（`BASELINE.yaml` `gates` 三个键在全仓 Python 里读者 **0**）；清单要么双向对账、要么承认自己只挡一个方向（在盘 78 份分册里 5 份不在清单上）；装饰性编号会被当计数用（zh §2.2 编号 `[6…20, 22, 21, 23]` 而条目只有 18 个）；解析子进程输出必须锚定摘要行（本门初版把 `ruff format --check` 的 diff 正文当摘要，把 1047 读成 5）；「有人查」本身是需要被查的事实**。此前 **CE 轮：新增 §76——脚本执行口径 ≠ 进程内 import 口径（`sys.path[0] = scripts/gates` 会让围栏整条静默退化成 `[SKIP]`，54 例锁全绿也照不出）；成功语句的分母必须自带口径，且披露要落在每一条输出路径；判据的外部权威要 import 不要复制常量**。此前 **CD 轮：新增 §75——删除语料会让派生读数与锁判据同时失效；读数必须按存盘语料重算并同时登记改前/改后，锁的判据应从「规模下界」换成「内容不变」，删除面必须把外部证据与泄露防线与运行时支持分开**。此前 **BZ 轮：新增 §70——测试契约锁定的工件必须入库（AK3 原则从报告引用扩展到测试契约，408 个 / 5.9 MB）；前提不成立必须显式 skip 带实测读数（语料面 / 历史切点 / 双盲三类，CI 绿 ≠ 锁在 CI 执行过）；`abs=0.0` 只适用于精确可表示的值（非 0.5 logsumexp 的跨平台末位差改相对容差）；有修复就升级不登记豁免（45 漏洞清零）；覆盖率读数有 ±1 行 / ±1 弧的跑批间噪声带**。此前 **BY 轮：新增 §69——分析集流量账的读侧收口：载入行数不是 n、整份剔除与行内折叠是两种剔除、扫描面之外还有结果文件、字段 None 不是 0；`## 数据来源` 只列纳入文件**。此前 **BX 轮：新增 §68——写而不读键池最后两键的读侧收口：`enabled=False` 占位不是「全部低风险」，键缺席不是低风险，`mdo_crash_rate` 五层输入域与 `None`/`0` 同形，`mdo_pool_floor_ok=False` 是两义键，crash 全池分母不可与 MDR 可评估分母互换**。此前 **BW 轮：新增 §67——判定值齐备不等于分母可见：同一精确率有存储 / 并集 / gold 三个分母，报告只印一个就是把口径选择藏起来；`None`（plausible=0）是「算不出」，不是「算出零」；「验证通过」不得在读侧覆盖「验证输入全归档为空」；环比用时要先证同并行度**——补丁接收链的 `patch_precision` / 两证据键 / `patch_abstain_signals` / `patch_validated` 自写入起报告面读端 0，归档 257 批次 / 11197 行里精确率 45.6048%（存储）/ 50.7483%（并集）/ 57.9198%（gold）、抑制精确率 93.9753%（gold 分母）/ 93.1122%（全部分母）、验证输入仅 `patch_evidence_level` 1007 行可达。此前 **BV 轮：新增 §66——「没看」与「判干净」只能由写侧区分：披露可行性先看判定输入是否落盘（落盘 ⇒ 纯读侧披露；不落盘 ⇒ 必须写侧增量，不能照搬「判定核一处不动」）、桶的个数由行内材料决定（不知道的不得塞进最近的桶）、首轮变异存活的三种不同处置（字面量契约锁 / 不对称夹具 / 删掉按构造恒真的假标记）、锚点必须与 `ruff format` 后的字节对齐**——批次 VIII / XIV 两份判定核自写入起报告面读端 **0**：判定核四种早退与「三信号都跑过且零命中」同形（5915 行分不清）、FL 六种早退 + 异常共用一个 `not_evaluable`（4442/5935）；归档 257 批次 / 11197 行里 hack 判 True **20** 行（12 硬编码输入分支 + 8 新增吞异常）从未出现在任何报告面，FL hit 1487 / miss 6 / not_evaluable 4442 ⇒ hit 比 **99.60%**，而 3+ 变更函数档仅 **1.9%** ⇒ ADR-0028 登记的整文件重写成因不足以解释该比值。处置：判定核增返 `status`（五档、两侧解析拆独立 try）+ 结果行落 `test_hacking_status` / `fl_constraint_reason` + 单一事实源 `experiments/_verdict_silence.py` + `detector_silence_stats` 读侧（四来源分列、推断明写下界）+ 报告新章节（hack 9 列 / FL 11 列 + 两条脚注）；判定值与方向一处不动。87 例新锁 + 2 处旧契约改写；变异 58 锚点全红 + 中性对照 N01 0 红（首轮 V04 / P11 / S03 三项存活就地处置）；沙箱确认跑 12257 / 19 / 0、218.94s / rc=0（正常口径 12271 / 5 / 0、collected 12276）；覆盖率 **19538/20052 = 97.4367%** / **7150/7584 = 94.2774%**。此前 **BU 轮：新增 §65——判据的"零"要拆档：没喂 / 喂了判干净 / 证据进不了门是三种事实、先同进程重跑对账再决定动判定还是动叙述、"未红"要落到具体锚点（恒等替换 / 双重限制 / 无人消费列数是三种不同故障）、红数 −1 不等于存活、手册里的"实测"必须先在真语料上跑通、同一普查给出两个读数时按自洽选口径**——Self-Repair Trap 判定核三信号的最少点数门槛（declining 3 / collapse 2 / score 2）在归档里从未披露：5935 行判定值全为 `False`，其中 **3200** 行只有 1 个历史点、declining 与 score 两信号在**整个归档里可达域各 0 行**、另有 **531** 行历史确有连续下降却进不了门；同进程重跑对账 0 处不一致 ⇒ 判定核与所有行的值、方向一处不动，只把四档输入供给 + 三域可达 + 域外下降 + 对账接到报告面（`experiments/_trap_input_domain.py` 为单一事实源，门槛文案一律读常量）。61 锚点 + 1 中性对照终跑全红；首轮 6 项未红逐项归因：U18 恒等替换（撤锚留码）、U30 双重封顶（改单点落地）、U54 列数无人消费（补 13 列单元格锁）、U49 / U50 / U53 系锚点文本非法、变异根本没写进去。另登记 §62–§64（BR / BS / BT 三轮）未滚动本行的存量漂移，本轮不代其补写叙述。此前 **BQ 轮：新增 §61——披露链的最后一环是读者不是字节、门禁跑在脏树上 ≠ 跑在入库后、读数差值必须归因到测量面、锚点的生命周期在 format 之后、渲染层字符串锁要按内容 disambiguate**——「报告读侧把四个 status 通道当作不存在」的收口：BN 落盘的结果行四键在 184 个 .py 里行读者 = 0（BM 接的是生产侧透传不是报告面读者），新助手 `check_leg_analysis._check_leg_measurability`（四通道 × 七档 + 三条恒等式）+ `analyze_results` 新章节 + `run_main_batch` 摘要行，判定值与方向一处不动；顺带收口 BP 批次遗留的 json-strict 存量红（门禁只扫已跟踪文件的盲区，干净树复跑转绿）。此前 **BP 轮：新增 §60——恒等式的成立条件写在实现里没写在断言里、探针与真语料可以共享同一个盲区、红数不能反推覆盖面、两消费者各折一档时只有等式能发现、静默的最高形态是整节消失**——「统计对照面把「这一行没记录污染级别」折成沉默」的收口；**BO 轮：新增 §59——全文子串断言把 100% 读成 0%、锚点可击杀性是锁的属性要先证、写入面普查的阈值时刻决定它归谁、数值分档与文本分档是两条独立测量、重定向里的块缓冲不是「没在跑」**——「raw 落盘面的读侧把三种缺席折成实测」的收口；**BN 轮：新增 §58——形状数不是通道数的代理、变异锚点互为子串、整行断言的假绿接线锁、残留标记与生产文本撞车、静态棘轮的失效方向要显式选择、补齐边界不等于打开开关**——「状态通道运行时披露、归档工件里 0 出现」的落盘归位；——「状态通道运行时披露、归档工件里 0 出现」的落盘归位；**BM 轮：新增 §57——复算入口落在会话临时目录就只是转引、同一个打印块里可以有两套分母、新档位必须同时落在内层与包装器、分布读数要连环境开关一起登记、「无键」与「值为 `null`」第二次被折成同一档**——「实验/报告读侧把『没测成 / 崩了』折成取值域最有利一档」的收口；**BL 轮：新增 §56——量具中途换口径就不能相减、用被测集合自身遍历的锁是自证循环、变异体存活要先证可达、归档里的 `None` 不是空列表、继承的四位小数必须重算**——「发布侧写了、判定侧没读」的消费侧双读收口；**BK 轮：新增 §55——同一棵树有两套分母时登记能被复算的那一套、拿 Git 当改前基线要先证明它没夹带别人、对账必须同进程比值而不是比摘要：`ast.parse`「读不懂」的逃逸与折叠**；本轮收口的是折叠链上的**第四个面**（BH 代理层的 `passed`、BI 守卫的返回值、BJ 检查器的 `findings` 列表、BK 的**解析守卫本身**）：13 处 `ast.parse` 站点的捕获面按**异常家族**收敛到 `AST_UNREADABLE_ERRORS = (SyntaxError, ValueError)`（3.14.6 实测：只有孤立代理位抛 `UnicodeEncodeError`，真语法错误 / 空字节 / 围栏整块 / git diff 都抛 `SyntaxError` 本体 ⇒ 新增腿恰好 1 条，而它从 `src/tools/multi_candidate.py::static_validate_patch` 抛穿时最坏可崩整个 `_debugger_node`），折叠侧改出带 `status` 的披露，另新增按 `try` 站点计数的捕获面棘轮门禁 `scripts/gates/check_ast_parse_guards.py`（`EXEMPT` 是只减不增的额度表：空捕获 / 新单腿守卫 / 超额度 / 条目失效 / 条目偏大各成一类失败）。判定不变性由 **160677 项同进程 `repr` 对账**背书（identical 160636 + escape_fixed 41、both_raised 0、UNEXPECTED 0）。此前 §54 **BJ 轮**（`check_assertions` 的四义 `findings=[]` 接一条可选 `outcome_sink` + worst-of 聚合、盲区早退不记第二腿、围栏归因的两种写法在 10855 条真语料上差 1 条并点名、共享键名先 grep 查重，判定值逐字节不变由三条判定翻转锚点背书）、§53 **BI 轮**（写盘前两道守卫把"从未比较"折进 `(True, [])`：可选 sink + worst-of 聚合 + 两个判定翻转锚点给"判定不动"配观测面、未声明键会被 LangGraph 静默丢弃）、§52 **BH 轮**（G5 testless 四层的"不可测量 → 验证通过"）、§51 **BG 轮**（mypy / pyright 空结果四值化）、§50 **BF 轮**（self-mutation 与模板验证器的 rc==0 判绿）、§49 **BE 轮**（生产路径六处判绿点）、§48 **BD 轮**（MDO 基线不可测 ⇒ 整体不可测、无证据变异体不进分母）、§47 **BC 轮**（对账工具的反方向论证：归档值是历史快照，重放不得为"永远 match"而保留旧口径）、§46 **BB 轮**（experiments 侧 11 处判绿点收口）、§45 **BA 轮**（`_suite_has_effective_pass` 四处消费点）；更早 2026-10-20 **AB-13 轮：新增 §16——字段名里的单位不是实现约束，直到实现参与判定**：`emse_stats_report.py` 输出 `total_usd` / `usd_per_detection` / `$/task`，字段名把单位写死，实现里**没有一行读过 `currency`**；前置探针用一条 CNY 计价模型（当时盘上真表登记 CNY 0.5 / 2.0，条目已随 2026-10-23 provider 清理删除）的合成行实测得 `total_usd=2.5`、`n_priced_rows=1` 并印在"总 $"列——**人民币被累加成美元且账面完全正常**（分母非空、单价非空、无任何不可计价披露）。同节另立两条：改口径撞上旧断言时**先裁决旧期望、改后必须仍测它声称的东西**（`test_zero_detection_no_division` 补 `currency` 后仍须加 `n_priced_rows == 1 and total_usd > 0`，否则分子为 0 时该例根本没走到除零守卫——§15"删掉守卫仍全绿有两种原因"出现在**测试夹具层**的同型问题）、**关掉一条尚未发生的通道必须同时锁"真批次不受影响"与"闸门不是空转"**（783 行单 USD 模型 ⇒ 入库读数 0 行改变，但同一个 0 也是"闸门可能从没执行过"的嫌疑，故覆盖面下界与 CNY/null 两模型对照写进断言）。**两套币种口径并存未统一**（`statistical_analysis.py:991` 缺省视为 USD），不得引用为"成本口径已全仓统一"。AB-12 轮：新增 §15——**0 实例要连测量覆盖面一起锁**：AB-12c 的前置普查第一版
把 trace 目录的父目录当扫描根，`main_batch/traces` 的 2007 个文件一个没打开却照样报"非对象行 0"；
修正覆盖面为 138 目录 / 8539 文件 / 125270 行后仍是 0，但"没扫到"与"扫了没有"必须靠断言里的覆盖面
下界区分。同节另立三条：变异锚点 0 红可能是测试输入把守卫遮住（c4 的 `task_start`）、同册内两条陈述
冲突时以盘上为准且**没有锁的那句作废**（AB-11 §4 的 `cmp 相同` 已被实测撤销）、预期红数订高不等于缺锁。**§14.1 补记**：站点 d 的确定性锁已随 AB-12a 交付（`src/utils/process_utils.py` 一行未改，四锚分别 5 / 1 / 1 / 5 红 + 只改文案对照 0 红），刷新后连跑两次全量口径 18371/18896 行、6606/7044 弧两次同值——登记为 **2/2 跑未见抖动**的观测，不是抖动上界已消除的证明；同树复跑若再现 ±2 行即为该锁未闭合的信号。
此前 AB-11 轮：新增 §14——**同值不是证据**：`make gates` 的 `format` 门抓到本轮reason 字符串写成两段隐式拼接，`ruff format` 后同一条 `src/` 树全量连跑两次实测 **18371 → 18369 →
18371 行 / 6606 → 6605 → 6606 弧**（passed/skipped/failed/collected 三跑全同），抖动源是
`src/utils/process_utils.py:638-642` 那条没有确定性锁的 `killpg(SIGKILL)` 竞态兜底分支；故"覆盖率
逐位相同"与"分母不变"都不再作 `src/` 零改动的佐证，佐证改用改动面文件清单，该分支继续登记且不得用
pragma 掩盖。又新增 §13——**缺席有三种，挤在一个桶里就只剩一种**：同一字段被
"真的没触发 / 生产者没写这个键 / 工件读不动"共用时报告只会说"零命中"；"无法核验"的原因本身也是
一个读数，四种失败机制塌成一句"git show 失败"照样是错读数；整份作废是合法口径，**无痕**作废才是
缺陷（全仓普查 9086 个 trace 文件里 5 个损坏、44 条记录无痕）。另登记一条方法学自纠：变异锚点
写坏导致 `ImportError` 时"有红"不等于"有锁"，靠收集数相等前置检查识破。此前 AB-10 轮：新增 §12——
**缺席/读不动不得报成"零命中/一致/未要求"**：上游
读不到时把本地 gold 包装后自我比对，归一化让一致性**恒真**且此时零份上游数据被读到；改它之前先量
真路径（200/3909 行全保留、71/71 任务走上游分支），这条普查才是入库工件能保持逐字节不变的前提。
此前 AB-9 轮：新增 §11——**同族判据换一层必须重述**：AB-8 的返回域普查搬到
`experiments/` 层 68 处 `json.loads` 上，读数分四类（42 响亮崩溃 / 9 已 fail-closed / 5 崩溃被
上层吞掉但留痕 / 12 静默丢数据），而分析侧的正确处置是给"跳过几份"做计数披露、不是给 68 处补
`isinstance`——后者把崩溃换成静默，方向相反。此前 AB-8 轮：新增 §10——**容错分支的覆盖面按"解析器返回域"枚举**，`json.loads`
六种合法返回里的五种非对象行让六个位置整批崩溃或静默零生效，另如实登记两处自我捕获：一处路径
推断被一次性探测否证、第一轮变异验证脚本因 `-k` 匹配零条而报"七处全红"实为空转。此前
2026-10-20 AB-7 轮新增 §9（校验器口径 ≠ 消费者口径时的"绿"本身是伪影））。此前
2026-10-17（M 轮：新增 §6——**确定性 oracle 的未校验注入 + 判分耦合**
（A-05 零 LLM 重放：oracle 76% 假阳、0 正确检出、混入同文件判分抹掉 14/22 个既有
LLM 检出）。L 轮：新增 §5——**代理指标的构念效度失效**（over_red proxy ≠
misguided 构念；df_spec 机制假设被逐测试操作化检验撤回）。K 轮：新增第 ⑤ 起——
**变异生成器**的无效变异体（identity / 语法非法）；此前的 2026-10-15 EMSE 批次把前四起
合并为"测量口径分叉"方法论章，逐起给出分叉的两种口径、检测方式、影响量级、修复、
可重放证据与结论是否翻转）

> **性质**：单语文档（中文），无英文配对——本文是**过程与口径记录**（审计/协议类），
> 按 `scripts/gates/check_bilingual_docs.py` 的维护约定登记豁免（见该文件
> `_EXEMPT_NO_EN`，2026-10-15 条目）。
>
> **可执行版本**：`docs/design/evaluation_integrity_checklist.md`（IC-1..IC-8 工件级静态诚信检查，零 LLM；配套校验器 `experiments/eval_integrity_check.py`；跑批后 / 对外引用前 / 跨批对比前必跑）。
>
> **证据纪律**：表内每个数字均取自下列决策记录 / 实测记录原文，未做二次换算；凡原文未给出
> 的数字一律留空或标注"原文未给"，不以估算填充：
> `docs/adr/0021-repair-zero-measurement-artifact.md`、
> `docs/adr/0029-measurement-artifact-cross-file-and-packaged-import.md`、
> `docs/adr/0033-packaged-test-tree-flat-import-artifact.md`、
> `docs/preregistration.md` §"第四起测量伪影修正与 E4 重结算"（2026-10-10）；
> ⑤ 取自 K 轮 self-mutation 批次实测（`tests/test_mutation_generator_validity.py`
> 的确定性反例 + `experiments/mutation_testing.py` 的修复 diff，2026-10-17）。

---

## 1. 五起伪影总表

| 起 | 伪影 | 分叉的两种口径 | 检测方式 | 影响量级 | 修复 | 可重放证据 | 结论是否翻转 |
|----|------|----------------|----------|----------|------|------------|--------------|
| ①（ADR-0021，2026-10-07） | patch 字段**围栏残留**：`state["patch"]` 保存 LLM JSON 原始值，可含 ` ```python ` 围栏 / `python:` 前缀（类型修复层与编辑意图通道甚至**主动构造围栏形态**） | **测量/透出口径**（M1 独立裁决 `_target_code_after_patch` 与结果行透出**直接消费原始值，未经清理**）vs **写盘执行口径**（`apply_patch_to_code` Step 1/2 负责清理） | ①受染面扫描：10 个主批次工件 **274/274（100%）带补丁行的 patch 字段以 `"python\n"` 围栏残留开头**（对照组 `generated_test` 字段 **974/974 全干净**——仅 debugger 的 patch 通道受染）；②决定性重放（2026-10-07，本地 pytest，零 LLM）：原样执行 **0/106 通过**，与写盘同口径清理后 **51/106 通过** | "repair 全线 0"的最大单一成分是测量层伪影；全量重放（10 批次 × aitester 臂）可重放 266 行（patch ∧ gold test_cases 双非空），**修正 correct = 103、修正 repair_rate = 38.7%**；E2 双种子批稳定 **44.4%–53.8%**；后续进入 v2 口径链后 R-P0-2 由 **35.86%（52/145）→ 39.31%（57/145）** | `patch_applier.normalize_patch_text()` 收敛为**单一权威**（= `extract_code_block` + python 前缀剥离，幂等），`apply_patch_to_code` 改为调用它（行为等价重构）；`_m1_metrics._target_code_after_patch` 完整文件分支经清理后返回；`_PYTHON_PREFIX_RE` 补 `(?!\w)` 负向后瞻（旧正则会把 `python_x = 1` 剥成 `_x = 1`）；新增存量重放工具 `experiments/repair_replay.py`（零 LLM）+ `Makefile::repair-replay`；19 项测试锁 | `python -m experiments.repair_replay experiments/results/main_batch --arm aitester` → 266 可重放 / 103 correct / 38.7%（ADR-0021 §验证）；v2 增量见 `docs/design/repair_caliber_matrix.md` §2 | **是**。"repair 全线 0"被定案为伪影主导，真实修复率在主批次存量上约 38.7%；ADR-0017 的动机随之勘误（但范式转向**不因此撤销**——其余动机未受影响，且第二阶段优先级排序改变：从"从零破冰"变为"38.7% → 提升"，见 ADR-0021 §"ADR-0017 动机勘误"） |
| ②（ADR-0029，2026-10-08） | **包结构 import**：`_run_pytest_in_tmp` 单文件口径 vs QuixBugs 官方测试依赖辅助模块（`from node import Node`）、包结构（`from python_programs.<module> import <name>`）与 `pytest.use_correct` | **判分口径**（历史只在 tmp 写 `{module}.py` + `test_{module}.py`）vs **上游真实依赖口径**（辅助模块 + 包结构 + 官方 conftest 机制齐备） | R2 系统性评审独立发现并量化；判分口径下上述 import 全部 `ModuleNotFoundError` → pytest 收集错误（rc=2） | 修复前 QuixBugs A/B 两臂 repair **均 0/50**；**9 个通过官方测试的正确补丁被误判 repair=0**；修复后 **A=37/50（可测 37/41）、B=36/50（36/41）** | 判分器按显式信号分派（`source=="quixbugs"` → 包结构物化；子串 `"python_programs" in test_code` 仅在 metadata 缺省时作兼容回退，`detection_gates.py:85` 委托调用不传 metadata → 行为逐位不变）；**fail-closed（R16）**：需要辅助模块而 `AITESTER_QUIXBUGS_DATA` 或辅助文件缺失 → 记 **None + logger.warning**（语义从"不误报"改为"不漏报"）；pytest `rc==5`（no tests collected）并入执行错误判定、repair 侧记 None，`rc==2` 在 repair 侧保留 0.0（补丁使目标模块不可导入 = 修复失败，属有意口径）；新增 `tests/test_m1_packaged_missing_support.py` 等 M-suite | QuixBugs 数字经独立重放**逐位确认 37/41 & 36/41**（ADR-0029 §后果；口径矩阵 ④/⑧，其中 ⑧ 标注 R27 修复后"逐位不变"） | **部分翻转**——QuixBugs 侧"真实基准 repair 系统性 0"被推翻（0/50 → 37/50 量级，其中 9 个正确补丁曾被误判）；对合成主批次的结论**无影响**（该路径不经过包结构分派） |
| ③（ADR-0029，2026-10-08，本起为该 ADR 新发现） | **跨文件任务未物化**：合成跨文件任务（Level 3 / 3.5）的 gold test_cases 直接 `import module_a/module_b/module_c`（模块名中性化、不重写），历史单文件判分口径只物化 `{task_id末段}.py` | **判分口径**（只写目标模块单文件）vs **任务真实结构口径**（按 metadata 物化完整伴生模块树，被测目标模块内容 = `target_code` 三态统一规则、伴生模块取缺陷原版，与 `run_benchmark._write_cross_file_modules` 同口径） | 伴生模块缺失 → 收集错误 rc=2 → 跨文件行 repair 系统性 0；R2 评审量化；连带可观测 `false_fix` 被抬升（**R4-A 6/8 行 = 1.0**）与 detection 偏低 | **六批次**（R4-A、E2×2、R-P0-2×3）跨文件行 repair 系统性 0；修复后跨文件行由恒 0 变为可测：**25 跨文件行中 11 行 correct**（并非全部可判 1.0——说明跨文件任务本身更难，伪影只是擦除了本可测信号）；口径链更新：R-P0-2 **35.86% → 39.31%（57/145）**、E1/E2 **48.11% → 54.72%（58/106）**、R4-A **44.4%（8/18）→ 55.6%（10/18）**；连带污染"修正口径"数字（ADR-0027 的 35.9%/48.1% 仍含系统性零行） | 新增 `_prepare_cross_file_test_tree`（按 metadata 物化完整模块树；顶层模块直接落 `{name}.py`；PYTHONPATH 覆盖 tmpdir）；`_run_pytest_in_tmp(..., task_metadata=...)` 四入口透传上下文、优先消费显式信号（`is_cross_file=True` / `source=="quixbugs"`）；空补丁语义对齐（`return 0.0`，消除"缺陷原码恰好过 gold → 误判 1.0"边界假阳性）；新增 `tests/test_m1_cross_file_metric.py` / `tests/test_m1_dispatch_heuristic.py`；新增**口径矩阵纪律** `docs/design/repair_caliber_matrix.md` | `（工件已清除）`（v2 定案）与 `（工件已清除）`；复算入口 `make corrected-metrics` / `experiments/repair_replay.py`（零 LLM） | **是**（对受影响数字）：v1 的 35.86% / 48.11% 被降级为"修正前下界"，对外材料一律替换为 v2 或显式标注下界；主批次检测/修复的**定性方向**不变 |
| ④（ADR-0033，2026-10-10 修复 / 2026-10-15 补登记为 ADR；原始记录见 `docs/preregistration.md` §"第四起测量伪影修正与 E4 重结算"） | **判分树包结构 vs 平铺 import**：M1 判分树由 `_prepare_packaged_test_tree` 构造，只提供 QuixBugs 式 `python_programs/{module}.py`；生产执行沙箱把被测模块**平铺**写成 `{module}.py` | **判分树布局口径**（包结构）vs **生产执行沙箱布局口径**（平铺）——Generator 写出的扁平 import（如 `from bitcount import bitcount`）**在它自己的生成环境里是正确的**，送进判分树则一律 `ModuleNotFoundError` → rc=2 → 三段判定第 3 条不成立 → `detection_rate = 0.0` | 零 LLM 决定性证据：12 任务子集 9 个缺陷程序，修复前 **9/9 在 buggy 与 fixed 两侧均 rc=2**；**同一批工件仅改判分树布局 → F2P 检出 0/7 → 6/7**；E4 重结算（单变量：同协议、同 cache namespace 复用原响应） | 主指标 `detection_rate` 在整批任务上**构造性恒为 0**（不是偏低，是结构性不可测）；E4 重结算（41 缺陷程序口径）：`aitester` **17/37 = 45.9%**（修正前 0/41 = 0.0%，token/task 16,038）vs `plain_llm_df` **31/37 = 83.8%**（token/task 1,905）；配对 McNemar（修正前 vs 修正后，aitester）不一致对 17、χ²=15.059、**p=1.042e-04**，2×2：**n10=17、n01=0**（单向翻转，无反向证据）；配对 McNemar（两臂）不一致对 14、χ²=12.071、**p=0.0005** | **双布局物化**：判分树 tmpdir 根同时写一份 `{module}.py`，与包结构 `python_programs/{module}.py` 并存，使两种 import 均可解析；**三段判定逐字未改、口径未放松**（恒失败测试在新布局下同样得 `detection=0.0`，已加回归测试锁定）；物化布局权威定义收敛到 `src/datasets/synthetic_dataset.py`（判分树与执行沙箱从同一布局约定派生）；本起进入口径矩阵——跨批次 detection 引用必须标注是否含本修复 | `docs/preregistration.md` §"第四起测量伪影修正与 E4 重结算"（含零 LLM 验证与 E4 重结算表）；ADR-0033 §背景/§后果；口径矩阵第 ⑨ 行的 detection 侧 | **否**（方向未变）——修正后 `aitester` 45.9% **仍显著低于** `plain_llm_df` 83.8%（p=0.0005），"编排净负贡献"不依赖本伪影；但"aitester 检出率 0%"这一**数值主张被推翻**（构造性不可测 → 可测） |
|
| ⑤（K 轮，2026-10-17；发现于 self-mutation 批次实测） | **变异体池含不可执行 / 零改动变异体**：仓库内自建变异生成器 `experiments/mutation_testing.py` 的两类假变异体——(a) **identity**：`_generate_numeric_offset` 对 Compare 中**任意** Constant 登记 `const X → +1`，但 `_offset_numeric` 只偏移 int/float（`x is None` / `s == "abc"` 产出 AST 与源码相同的变异体）；字符串置换对原文 `'x'` 的置换值 `"x" * 1` 仍等于 `'x'`；(b) **语法非法**：`_gen_subscript_negate` 对 Slice 下标 unparse 出 `x[-(a:b) - 1]`，不可执行 | **变异体池口径**（生成即登记：分母 = 全部生成的变异体）vs **可执行单点改动口径**（分母 = 语法合法 且 AST 与源码不同 的变异体） | ① 独立构建的 self-mutation 驱动器对每个变异体做 `ast.parse` + AST 级 identity 校验（零 LLM，`scripts/tools/self_mutation.py`）；② `src/` 语料静态面量化：非数值比较常量 **668 处**、Slice 下标 **268 处**（缺陷的可触达面）；③ 修复前实测：`src/utils/helpers.py` 的 `_gen_subscript_negate` 单文件产出 **5 个语法非法**变异体；`env_utils` / `helpers` / `atomic_io` 每模块各 **1 个 identity**（`None` / 字符串常量比较） | 方向为**系统压低** mutation_score（不是抬高）：identity 变异体在任何测试套件下恒存活；语法非法变异体执行期 pytest **rc=2**（收集失败），而 `_run_mutant_tests` 的保守口径把 `rc∈{2,5,超时}` 记作**存活**——生成器缺陷被记成"测试未捕获"。存量工件的 `mutation_score` / MDO 口径指标因此是**旧口径下界**；偏差幅度需按批次重算才能定量（本轮**未重算**，如实登记） | ① 数值偏移：仅 int/float（排除 bool）+ AST 级变化校验；② 字符串置换值强制 ≠ 原值；③ 下标取反跳过 Slice；④ `_emit` 通用语法守卫（`ast.parse(new_code)` 失败即丢弃），把"变异体池 = 可执行单点改动"钉成不变量 | `tests/test_mutation_generator_validity.py`（16 例：不变量 × 语料 / 四缺陷点确定性反例 / 语法守卫）；复跑 `pytest tests/test_mutation_operators_v3.py tests/test_mutation_generator_validity.py -q`（零 LLM） | **否（方向）**：主指标 detection / repair 的结论不依赖该生成器；但**数值主张须降级**——受影响的只有**仓库自建生成器**口径（MDO / 合成批次 per-task `mutation_score`），**不含** cosmic-ray 口径的 QuixBugs Mut@k **0.9396**（该数字由外部 cosmic-ray 8.7.0 计算，见 `experiments/emse_quixbugs_mutk_full.py` / ULT adapter）。存量受染指标一律标注"旧口径下界"，不得与修复后重算值混池 |
**读法（强制）**：五起伪影同族——**"意图口径 ≠ 执行口径"**（ADR-0029 §背景原话），
且每一起的修复都遵循同一治理模式：**先把分叉的判据函数化为单一权威，再让判分/测量
路径与执行路径从同一权威派生**，最后用零 LLM 重放锁定。①之后是
`normalize_patch_text()`，②③之后是显式 dispatch + fail-closed，④之后是同一布局源，⑤之后是**生成器自校验**（产物必须可执行且非零改动）——把同一纪律推进到**评估工具自身**。
ADR-0033 §后果把该模式写成显式检查项："**凡'分叉的判分/执行路径'必产伪影**"。

**残留风险（原文登记的，不得省略）**：

- ADR-0029 §已知局限：metadata 畸形（缺模块名、字段冲突、`is_cross_file` 与模块树不一致）
  时物化可能产出不完整模块树 → rc==2 → repair 侧记 **0.0**——该行会被记为"修复失败"
  而非"不可测"；物化前置 fail-closed 校验**尚未实现**（列入待立项）。当前数据集生成器
  不产出该形态（8/8 探针全过）。
- ADR-0033 §代价与残余风险：双布局使判分树内同名模块出现两份，**不同 import 风格可能
  解析到不同文件**——当前两者内容同源、未在任何批次触发，属结构性隐患；双布局一致性
  守卫（内容等价断言）与"单一布局源"重构均未做。
- ADR-0033 §已知局限 3：修复前历史批次的 detection 值在未来文档中须一律标注
  **"修复前下界"**，不得与修复后批次混池。
- ADR-0033 §代价与残余风险末条：本 ADR 为**补登记**（修复与验证发生于 2026-10-10，
  ADR 落盘于 2026-10-15），时间序证据以 `docs/preregistration.md` 该节与批次工件为准。

---

## 2. 为什么这是方法学贡献而非技术细节

**第一，它给出了一个可迁移的失效定律，而不是一个 bug 修复。** 五起伪影的机制各不相同
（文本清理、import 解析、模块物化、目录布局），但**失效形态完全相同**：测量/判分路径
与生产/执行路径各有一套"如何理解这份材料"的口径，二者分叉时，测量层记录的不是被测
系统的能力，而是分叉本身。ADR-0029 §背景与 ADR-0033 §后果都把这句写成了项目级检查项。

**第二，它量化了"不修会错到什么程度"，且量级足以改变结论。** ①使主批次 repair 从
"全线 0"变为 38.7%（`docs/adr/0021-repair-zero-measurement-artifact.md`）；②使 9 个
**正确**补丁被记为失败（`docs/adr/0029-measurement-artifact-cross-file-and-packaged-import.md`）；
③使六批次跨文件行系统性 0、并抬升 false_fix（同文件）；④使主指标 `detection_rate`
**构造性恒为 0**——不是偏低，而是结构性不可测（`docs/adr/0033-packaged-test-tree-flat-import-artifact.md`）。
在 ④ 的情形下，如果不做布局 A/B，任何"本系统检不出缺陷"的结论都是关于**判分树**的
陈述，而不是关于**系统**的陈述。

**第三，它同时给出了"结论是否翻转"的判据。** 五起里只有①②③改变了数值结论的定性
（①"repair 不是零"、②"QuixBugs 不是零"、③"跨文件行不是零"），④改变了数值但**没有**
改变方向（45.9% 仍显著低于 83.8%，p=0.0005）。这正是方法学章节需要的结构：伪影治理
的目标不是"把所有数字改大"，而是让每个数字都**知道自己属于哪条口径**——因此配套产出
是 `docs/design/repair_caliber_matrix.md` 的"引用纪律"（编制口径编号、禁止 all-task 与
M1 可测口径混用、禁止引用未修正的跨文件零行数字）。

**第四，它把"修复"做成可重放的，而不是靠重跑。** ①提供 `experiments/repair_replay.py`
（零 LLM，读存量 JSON 重放）；②提供 fail-closed 语义变更与 M-suite 回归；③提供
`corrected_report_v2.md` / `replay_r4_ab_arm_a_v2.md`；④提供"同一批工件仅改判分树布局"
的单变量对照与 E4 重结算（同协议、同 cache namespace 复用原响应）。审稿人因此可以
**不消耗任何 LLM 配额**复核每一起伪影的量级——这是可判性的关键。

---

## 3. 如何作为论文 §Measurement Integrity 呈现

建议按"定律 → 证据 → 纪律 → 影响"四段写，且**五起并列成一张表**（即本文 §1），
不要拆成四个零散的技术脚注：

1. **开篇给定律**（1 段）：测量口径与执行口径的分叉必然产出伪影；本文报告同一研究
   项目中五次独立复现，机制各异而失效形态相同。引 ADR-0029 §背景原文与 ADR-0033 §后果
   的显式检查项。
2. **主表给五起证据**（本文 §1 的八列）：每起必须同时给出**两种口径**（分叉在哪里）、
   **零 LLM 检测方式**（受染面扫描 / 布局 A/B / 重放）、**影响量级**（分子的绝对值与
   分母定义）、**可重放入口**。表中的 274/274、0/106 → 51/106、9 个正确补丁被误判、
   25 行中 11 行 correct、0/7 → 6/7、17/37 = 45.9% vs 31/37 = 83.8%（p=0.0005）
   都是"可被审稿人当场复核"的锚点，不要只写百分比。
3. **纪律段**（1 段）：单一权威函数；显式 dispatch 契约（禁止依赖测试文本子串）；
   fail-closed（"没跑起来"记 None，不得静默记 0）；口径矩阵 + 引用必须带标签；
   凡修复必须附带"修复后结论是否翻转"的判定。
4. **影响段**（1 段，必须诚实）：修复**不总是**让数字变大或让主张变强——④纠正了
   `aitester` 的 detection 数值，但**强化**了"编排净负贡献"这一负面结论；①纠正后
   repair 基线重置为 38.7%，反而把研究目标从"破零"改成"提升"。把这段写清楚，等于向
   审稿人证明这套治理不是"往有利方向调数字"。
5. **Limitations 交叉引用**：把 §1 末尾登记的残余风险（畸形 metadata 记 0.0、
   双布局同名模块、修复前 detection 为下界、ADR-0033 为补登记）原样搬进 Limitations，
   并在 Methods 里说明"跨批次 detection 引用一律带修复标签"。

---

## 4. 引用纪律与不可核验事项

1. **口径标签强制**：任何 repair / false_fix / detection 数字必须携带
   `docs/design/repair_caliber_matrix.md` §1 的口径编号（repair ①–⑨；false_fix 见该文件
   "false_fix 口径（权威落点）"节的 ⑩⑪）或同时给出
   "分子/分母 + oracle + 数据集 + 臂 + 种子 + 开关 + 工件路径 + 可复算命令"。
2. **禁止混池**：修复前批次的 detection 值（下界）不得与修复后批次混池（ADR-0033
   §决策 4 与 §已知局限 3）；all-task 与 M1 可测口径不得互换陈述（ADR-0029 §决策 6）。
3. **本文未做独立复算**：§1 表中所有数字均**逐字取自**五份来源文件，本次未重跑
   `experiments/repair_replay.py` 或判分树布局 A/B（那需要本地数据目录与 pytest 环境，
   且属对既有定案的重放，非本文档职责）。若需第三方复核，请按"可重放证据"列的入口
   在干净树上复算——五起均为零 LLM 入口。
4. **⑤ 的可重算范围**：修复只改变**未来**计算；存量批次的 `mutation_score` /
   MDO 指标需重跑才更新，本轮未重算，故一律按"旧口径下界"标注。若论文/MDO
   报告引用这些指标，必须同时说明"生成器已修复，修复后重算可能上移"。
5. **数字未在来源中给出者一律留空**：例如第 ④ 起修正前的 token/task 对比只引
   `16,038`（修正后 aitester）与 `1,905`（df），不推算修正前的成本。

---

## 5. 附：代理指标的构念效度失效（非伪影，2026-10-17 L 轮）

> **与 §1 五起伪影的区别**：五起都是"同一材料被两条路径按不同口径理解"的**口径分叉**；
> 本节是另一种失效——口径本身一致，但**代理指标（proxy）与它声称代理的构念不重叠**。
> 处置方式不同：伪影靠"单一权威 + 零 LLM 重放"修复；代理失效靠**把构念按外部文献
> 操作化后重新测量**，并撤回基于 proxy 的机制主张。

**背景（预注册口径）**：df_spec 双臂实验（`docs/study/DF_SPEC_PREREG_2026-10-16.md`）
把"over_red 占比相对下降 ≥30%"声明为**机制侧描述性信号**，并明确标注
`as-proxy，不作机制证明`——机制假设为"锚材料 = Planner 对缺陷代码的再描述 → 约一半
概率把缺陷行为固化成预期（misguidance）"。

**L 轮测量（零 LLM 重放，`experiments/misguided_metrics.py`）**：按 Zhao, Zhou & Cohen
（ISSTA 2026, DOI 10.1145/3832204）的操作化，对批次工件里的 `generated_test` 逐测试
在缺陷版 / 修复版两侧各跑一次 pytest（junitxml 逐测试结果），四分类为
`effective = buggy 败 ∧ fixed 过`、`misguided = buggy 过 ∧ fixed 败`、
`both_pass`、`both_fail`；超时/收集失败/import 失败**单列**、不进可分类分母。

| 臂 | 可分类测试 | effective | misguided | both_pass | both_fail | timeout |
|---|---|---|---|---|---|---|
| df（对照） | 776（收集 834） | **44.72%**（347） | **1.29%**（10） | 52.71% | 1.29% | 56 |
| df_spec（处理） | 1213（收集 1336） | **32.07%**（389） | **0.74%**（9） | 55.15% | **12.04%** | 122 |

主分析集 = 40 个有缺陷信号的缺陷程序（41 口径剔除 `node`：其 `test_cases` 实为辅助类
源码、无 `test_*`，buggy==fixed 无缺陷信号）；9 个 `*_test` 驱动任务两臂均结构跳过；
`--repeat 2` 两次报告 body digest 完全相同（确定性）；与归档 `detection_rate` /
`specificity_gate_verdict` 的交叉校验 **0 不一致**（唯一差异可由 per-test 超时口径与
`node` 无缺陷信号完整解释）。

**结论（两处失效，均如实登记）**：

1. **方向失效**：over_red 占比的变化（df 22.5% → df_spec 46.0%）不能读作 misguidance
   上升——严格操作化下 misguided 占比反而**略降**（1.29% → 0.74%，绝对数 10 vs 9，
   集中在 4 个任务，量级不足以作强主张）。
2. **归因失效**：df_spec 的负结果（detection −25.7pp）在逐测试分解下由
   **both_fail +10.75pp** 承担（其中 78% 集中在 3 个任务），即伤害形态更像
   "契约/期望值失真 → 正确实现也过不了"（过约束），而非"断言缺陷行为"（misguidance）。
   两臂"含 effective 测试的任务数"相同（37/40）——df_spec 不是写不出有效测试，而是
   套件混入更多无效测试，拖垮**任务级二值**判定（整文件在 fixed 上变绿）。这是任务级
   detection 的**聚合盲点**，不是生成能力全面退化。

**对既有主张的处置**：df_spec 预注册的机制侧 proxy 信号**撤回**（预注册同时产出的
主判定 `not_confirmed` 不受影响——它只依赖 detection 与 McNemar）；"锚=缺陷再描述→
misguided 固化"在严格操作化下**未获支持**，后续材料不得再以 over_red 升降作为
misguidance 证据。新度量工具与完整报告（输入 sha256、逐任务逐测试明细、限制）：
`experiments/misguided_metrics.py`、`docs/design/misguided_effective_metric.md`、
`（工件已清除）`。

**限制（不得省略）**：单模型（deepseek-flash）/ 单基准（QuixBugs）/ 单批次（df_spec
2026-10-16 工件）的描述性证据；生成测试的全局状态与收集顺序未隔离；官方金测试不参与
四分类；超时测试单列（与 A-06 "超时记红"的判分口径有意不同）；`node` 无缺陷信号已剔除
并披露。**该结论不得外推为"所有规格锚路线无 misguidance 风险"**——它只说明本批次
df_spec 臂的伤害形态不是 misguidance。

---

## 6. 附：确定性 oracle 的"未校验注入 + 判分耦合"（2026-10-17 M 轮）

> **与 §1 五起伪影、§5 代理失效的区别**：五起是"同一材料被两条路径按不同口径理解"的
> 口径分叉；§5 是 proxy 与构念不重叠；本节是**测量仪器自身未校验收** + **判分对象
> 耦合**——确定性 oracle（机器生成的断言）在注入前未验证其正确性，且与 LLM 测试
> **混在同一 pytest 文件**里共同决定任务级判定。二者叠加，使一个"零 LLM 的确定性
> 检出通道"在证据上表现为**净损伤**。

**背景（设计意图 vs 实现）**：`src/specs/spec_ir_v2.compile_spec_oracle` 把 SpecExpr
可编译子句编译成确定性断言，`src/graph/nodes._append_spec_oracle_to_test_with_verdict`
把它**追加到 LLM 生成测试的同一文件尾部**；设计注释称"与 LLM 测试**并列**执行"
（`SPEC_ORACLE_EXEC_ENABLE`，默认关，历史批次恒未启用）。"并列"在语义上指两通道
独立判读，但实现是同一文件、同一次 pytest 会话、同一个任务级二值判定。

**M 轮测量（零 LLM 重放，`experiments/oracle_quality_replay.py`）**：取 df_spec 双臂
归档批次，用**生产注入函数原样调用**（state 由锚表重建：`test_plan={function_name,
logic_analysis}`、`target_function`、`module_name`、`target_code`；锚表 sha256
`3e90b2ad…` 校验，QuixBugs 内容寻址命中 50/50），再按逐测试 buggy/fixed 分类：

| 项 | 数值 |
|---|---|
| 注入率（50 行） | attempted 49 / **injected 38（76.0%）** / compiled_empty 11 / not_attempted 1 |
| oracle 四分类（分母 38 条可分类 oracle 测试） | **correct 0 / fp 29（76.32%）/ silent 9（23.68%）/ misguided 0** |
| 假阳主因 | fixed 侧异常 27 条：**TypeError 24**、AttributeError 2、ZeroDivisionError 1（+断言失败 2）——编译器对缺失输入的 0 字面量绑定使 oracle 在**正确实现**上崩溃 |
| 任务级检出贡献（40 缺陷程序口径，配对） | df_spec 归档 54.29% → LLM-only 重放 50.00% → oracle 混入后 **10.53%**（Δ−36.84pp；lost 14 / none 20 / preserved 4 / **added 0**）；df 对照 77.78% → 77.50% → **18.42%**（Δ−57.89pp；lost 22 / none 9 / preserved 7） |
| 交叉校验 | 归档 detection/`spec_oracle_verdict` 复现 **0 mismatch**（50/50）；四分类两臂完全相同（oracle 与 LLM 测试内容无关） |

**结论（两条独立缺陷，均需处置）**：

1. **仪器未自校验**：确定性 oracle 在"正确实现"上的失败率 76%，且 0 条正确检出——
   确定性通道当前**不是**"LLM 之外的机器锚点"，而是把编译层绑定错误转成了断言的
   假阳性。生产上 `SPEC_ORACLE_EXEC_ENABLE` 默认关，因此**历史批次数字不受影响**；
   但任何"打开该开关能提升检出"的预期在现有实现下不成立（先修仪器）。
2. **判分对象耦合**：oracle 测试与 LLM 测试同文件，oracle 在 fixed 侧失败会让**整文件
   fixed 判定失败** → 任务级 detection 被抹掉（实测 lost 14/22 个 LLM 已有检出）。
   修复方向（下一轮，需预注册）：oracle 测试**独立文件独立判读**——LLM-suite verdict
   与 oracle verdict 分开产出、分别报告；oracle 失败不得改写 LLM 检出结论。在修复
   并验证前，`SPEC_ORACLE_EXEC_ENABLE` 保持默认关且不得用于能力主张。

**口径纪律（不得省略）**：本节数字是**仅锚表材料重建 state** 的受控反事实
（无 Planner 现场 `spec_ir` / `boundary_triplets`），是该材料条件下的**质量下界**，
不是 LLM 生成能力指标，也不与 TestAgent / Tratto / TOGLL 的 oracle 数字横向对比；
描述性、无显著性推断。工件：`（工件已清除）`
（输入 sha256、命令、分母、失败类型逐类披露、0 mismatch 交叉校验）。

**N-3 处置（2026-10-17，A-05 后续修复）**：两条缺陷**分治**——

- **① 接线缺口（P0，结构性）已修复**：`_append_spec_oracle_to_test_with_verdict`
  材料源扩展为 `spec_ir → test_plan.logic_analysis → spec_anchor.logic_analysis →
  spec_anchor.human_spec`。此前生产 df_spec/doc/union/augment 类臂（Planner 关闭、
  只有 `spec_anchor`）的 oracle 注入**永远 not_attempted**——即"注入率"本身
  也被接线缺口人为压低。人类 docstring 锚**不强行编译**，如实记
  `not_attempted_human_spec_only`；另有 `not_attempted_missing_target` /
  `not_attempted_anchor_unparseable` 两个可审计原因（既有 verdict 值逐字不变）。
- **② 判分对象耦合已修复**：`detection_rate` 语义收敛为 **LLM-suite**
  （pytest `-k` 排除 `test_specir_v2_oracle` / `test_specir_v2_smt_witness`）；
  oracle 测试独立 `-k` 运行并以 `oracle_suite_verdict` ∈
  correct/fp/silent/misguided/unavailable 单列（超时/收集错误 → unavailable，
  fail-closed）。oracle 失败**不再改写** LLM 检出结论。默认开关关闭时零行为
  差异（命令逐位不变、零额外子进程）；口径变更**只影响未来批次**，历史工件
  JSON 不改写，引用历史 detection 须标注"混判旧口径"。

**零 LLM 重放验证**（`experiments/oracle_quality_replay.py --independent-judging`；
工件 `（工件已清除）`）：
state 只带 `spec_anchor`（复刻生产臂形态，同时验证接线修复），直接调用生产
`_m1_metrics` 判分链，`M1_PER_TEST_TIMEOUT=1s` 对齐 M-2 重放。结果：两臂
LLM-suite detection **20/40 = 50.00% / 31/40 = 77.50%** 与 M-2 基线**逐位一致**
（逐任务 match 40 + both_none 9 + replay_none 1（node 无 gold），**mismatch 0**）；
oracle 独立四分类（38 个注入任务）仍为 **correct 0 / fp 29 / silent 9 /
misguided 0 / unavailable 2**，与 M-2 逐任务类别 match 38/38。**判分修复不改变
"oracle 通道当前净负"的质量结论，只让它可被独立测量**——质量改进（编译器绑定
自校验 / 假阳治理）仍是下一轮任务。真 LLM 单任务冒烟（`smoke/`，df_spec 臂 +
`SPEC_ORACLE_EXEC_ENABLE=true`，find_in_sorted，1 次调用 2423 tokens）直接演示：
同一生成测试 **LLM-suite detection=1.0 而 legacy 混判=0.0**（oracle verdict=fp
抹掉了既有检出）——验证性，不作证据。

**O-1 仪器处置（2026-10-18，A-05 后续"仪器治疗"）**：M-2/N-3 已把 §6 的两条缺陷
分开——判分耦合由 N-3 修（独立判读），**仪器未自校验**由 O-1 修（崩溃安全 +
前件校验输入）。O-1 修复 `compile_spec_oracle` 产物：① 执行体（绑定/前件/
调用/后件）包 `try`，`AssertionError` 原样 re-raise、其余 `Exception` →
`pytest.skip("oracle-unavailable: <ExcType>: ...")`（不静默 pass、不伪装 fail；
BaseException/超时不吞）；② 有 boundaries 时按序用受限安全求值
（`spec_smt.safe_eval_clause`，白名单 AST、零 eval/exec）筛选满足全部可机检
前件的候选；全部被拒 → SMT 见证兜底；仍无 → 带
`pytest.skip("oracle-unavailable: no-valid-input")` 的保守骨架（不臆造输入、
不产假断言）；③ `_m1_metrics` 把 pytest skipped 记 `oracle_suite_verdict=
unavailable`（不混入 fp/silent），replay 四分类新增
`fp_breakdown`（`fp_assertion_fail` / `instrument_error` / 未归因）、
`skipped_count`、`skip_reason_counts`（旧四分类键兼容）。

**零 LLM before/after 重放**（df_spec 双臂，工件
`（工件已清除）`；墙钟 279.9s）：
before（M-2 工件）fp **29** = `fp_assertion_fail` **2** + `instrument_error`
**27**（TypeError 24 / AttributeError 2 / ZeroDivisionError 1），可分类分母 38；
after：fp **2**（仅断言型，保留）、`instrument_error` **0**、
**skipped 27**（`oracle-unavailable: TypeError` 24 / AttributeError 2 /
ZeroDivisionError 1，与 before 异常类型逐类一致）、可分类分母 **11**、
correct **0→0**、silent 9→9。生产独立判读路径（N-3 模式）复核：40 口径
`oracle_suite_verdict` = unavailable 29 / fp 2 / silent 9 / correct 0，
LLM-suite detection 与 M-2 逐位一致（20/40=50.00%、31/40=77.50%，mismatch 0）。

**对 M-2/N-3 结论的修正（诚实披露）**：原记录"oracle 混判抹掉 14/22 个 LLM
检出"**主要成分是仪器伪影**——那些 lost 任务绝大多数是崩溃型 oracle 在 fixed
侧恒红；加固后混判 lost 降至 **1/2**，oracle-augmented 40 口径 detection 由
10.53%/18.42% 升至 44.74%/71.05%。这**不是**检出能力提升（LLM-suite detection
不变 50.00%/77.50%、correct 仍 0）：原"净损伤"量级被仪器缺陷放大，剩余
lost 1/2 才是断言型 fp 的语义质量信号；"判分耦合"缺陷本身（N-3 已修）仍会
让断言型 fp 改写混判检出，独立判读是正确修法。

**口径纪律（长期有效）**：这是**仪器治疗，不是检出能力提升**——correct 仍 0
（语义质量治理另立项）；修复只让"崩溃/前件违反"从"假阳判定"变为"不可用
（skipped/unavailable）"单列。**加固后可分类分母由 38 降为 11**：引用 oracle
占比必须同时给分母与 skipped 数，禁止与加固前数字混池；历史批次（开关默认
关）数字不受影响。残余风险：harness 只捕获 `Exception` 子类（段错误等由外层
subprocess 兜底）；skip 暴露而非修复编译器绑定缺陷；NL 前件仍不可机检；
`nodes._spec_oracle_verdict_after_run` 对"oracle 全 skip"轮次可能记
injected_and_passed 的风险**已在 O 轮配套修复**：输出显式出现 oracle `SKIPPED`
行时保留未决态 `injected`（不臆测 passed），与独立判读
`oracle_suite_verdict=unavailable` 对齐（`tests/test_oracle_instrument_safety.py`
3 例锁定正常 passed/全 skip/失败三态）。


**P-1 示例通道口径（2026-10-18，探索性）**：O-1 之后 oracle 仪器可判定（fp 29→2），
但 correct 仍 0——断言不触达缺陷行为。P-1 增加"规格可执行示例"通道：LLM **spec-only**
（不发送缺陷代码）生成 concrete examples → `compile_spec_oracle` 逐示例断言
`assert f(args…) == expected`（repr 字面量、零 eval/exec、O-1 崩溃安全 harness）。
df_spec 归档 20 任务 A/B：correct **0→6**（真实检出，逐例核验 fixed 全过、buggy 至少
一例败）、同引入 fp 3（全表示型）+ misguided 2（LLM 示例期望值幻觉），精确率 42.9%；
P-1.1 返回表示归一（tuple/generator→list）后 **fp 3→0、correct 6→8、精确率 61.5%、
错误率 15.4%**（分母 13；2 幻觉仍存在、flatten 转 unavailable）。**口径纪律**：这是
**探索性机制证据**（n=20、单次生成/重放、spec-only），不得作为"oracle 生产可用"或
"检出能力提升"的能力主张；引用必须同时给分母/精确率/错误率/生成方式；生产接线与
示例自校验需下一轮同批 A/B + 预注册。工件
`（工件已清除）`（raw + norm 双报告、ATTRIBUTION、
SHA256SUMS）。

**Q-1/Q-2 示例通道路径口径（2026-10-18，生产接线 + 预注册 A/B）**：P-1 证明示例通道
"在受控重放中有检出能力但不提升净质量"；Q-1 把它接入生产（`SPEC_ORACLE_EXAMPLES_ENABLE`
默认关、双门 ∧ oracle exec；Planner 契约段只在开启时追加，关闭时 prompt 逐字节不变；
无 Planner 臂 +1 次 spec-only 生成调用；行字段 `spec_oracle_examples_source/count` 可审计）。
Q-2 在干净切点 `a48a53f` 上做**预注册同批二臂 A/B**（A=oracle 开/示例关 vs B=oracle 开/
示例关；aitester logic QuixBugs 20 任务；判定规则跑前冻结：oracle-correct 新增 Δ≥2 ∧
LLM-suite 非劣 ∧ McNemar 单侧 p<0.05，否则 not_confirmed；MDE/小样本/单次运行披露）。
**口径纪律**：Q-2 结论只覆盖"该切点/该任务子集/单次运行"；引用必须给两臂分母、
oracle verdict 分布（correct/fp/silent/misguided/unavailable）、LLM-suite 一致性与判定
三判据；不得把重放机制的 correct 增益直接移植为生产能力主张。**事故披露**：准备期
零 LLM 自测误用真实模式（TOCTOU）导致两臂意外真实调用约 4min，无数据可用，粗估
$0.15–0.20，已归档 `_incident_unintended_llm_launch_20261018/`（禁止作为证据），并加固
runner（dirty=0/PREREG 冻结/--preflight-only/TOCTOU sha 复核）。

**Q-2 结果（2026-10-18，预注册 A/B）**：`not_confirmed`——oracle-correct 新增
**Δ=+6**（A 0→B 6，McNemar b=6/c=0，单侧 p=0.015625），但 LLM-suite detection
A **15/15=100%** vs B **12/15=80%**（δ=−20pp），**非劣判据失败**（3 任务
detect_cycle/hanoi/knapsack A=1→B=0）。两臂 20 行、exit=0、成本 $0.275878；
`spec_oracle_examples_source` A none×20 / B planner×17,none×3（count mean 2.25）。
**处置**：生产开关保持默认关；下一轮先复核 detection 下降是 trade-off 还是单次
重跑噪声（换 seed/复跑/检查 examples 是否经 Planner 契约改动下游行为）再决定是否
生产化；在此之前不得引用"示例通道提升检出"作为能力主张（本批只证明"能增加
oracle-correct 任务"同时**伴随** LLM-suite 下降）。工件
`（工件已清除）`（101 项 SHA verify）。

**R-1/R-2/R-3 口径（2026-10-18）**：Q-2 的 −20pp LLM-suite 下降需要先区分"真实
trade-off vs 单次噪声"。R-1 先做**零 LLM 诊断**：Q-2 两臂 20/20 任务 generated_test
均不同（test-name Jaccard 均值 0.197、gt_len 相对差 0.217），3 个损失任务差异幅度
与全量同级（0.189/0.445）→ 结构性 trade-off 证据不足，候选机制以 LLM 非确定性为主
（结果行不落 test_plan 原对象，只能间接推断）；随后用 **seed-43 预注册复现批**
（判定规则跑前冻结：B_det<A_det 且损失 ≥10pp → `reproducible_tradeoff`，否则
`not_reproduced`）。**结果**：A/B detection 均 **13/15=86.67%**（loss=0.0pp<10pp）→
**`not_reproduced`**，Q-2 的 −20pp 视为单次运行噪声；而 **oracle-correct +6 两 seed
可复现**（A 0→B 6，McNemar p=0.015625）。→ 处置：仍不自动生产化（保守），下一轮
3 臂（关/开 + 更多 seed）复核 + hanoi 类"契约段改变修复轨迹"机制归因。**R-2 口径**：示例自校验过滤器在 90 条 P-1 示例上 **dropped=0**
（2 例幻觉未被命中——锚后置子句只编码 isinstance/>=0 类约束）→ 判定"未达有效过滤、
非高风险"；引用时必须给过滤统计与"规约表达力是根因"的结论，不得声称过滤器解决
示例质量问题。**R-3 口径**：`postprocess_wall` 为**每基线样本**粒度（n_tasks=该阶段
被计时基线数，非任务数），`timed_out_tasks` 当前恒 0，仅用于观测不可当任务级超时
证据；hook 为纯观测，历史 summary 字段逐项不变。

**S-2/S-3/S-1 口径（2026-10-18）**：**A-19 停滞检测**：P-2 的 B8 消融因首轮全绿无触发；S-2 用
**实验层确定性失败注入**（前 3 轮强制失败 + coverage 沿用上轮，生产文件零 diff）构造可触发场景，
stagnation ON/OFF 两臂（唯一差异=开关）实测：on **10/10** 触发、iterations **1.8**；off **0/10**、
iterations **3.0**；配对 Δ=1.2 轮 → `confirmed`。**但必须同时披露**：生产默认协议
（`PATCH_EVIDENCE_GATE_ENABLE=true`）下 repair-invalid 同迭代抢占 → on/off 均 iterations=2，
A-19 **只改标签不省迭代**；引用时须给"注入协议/默认协议"两种口径，不得笼统称"停滞检测缩短
迭代"。**S-3 多采样自一致性**：K=2 精确求交在 20 任务上排除 **2/2** 幻觉期望，但零 LLM 重放
correct **8→3（−5）** → 判定「高风险，默认关」；不得把"清掉幻觉"单独引用为质量提升，必须同时
给出 correct 损失与判定。**S-1 3-seed 决策**：seed42/43/44 合并（Δ 均 **+6**；loss 20/0/0pp）、按预注册规则
（enable_candidate = Δ≥5 in ≥2/3 seeds ∧ loss ≤5pp in ≥2/3 seeds）→ **`enable_candidate`**；
该结论仅为**决策支持**，生产开关默认关、enabling 需另行变更+回归，不得当作能力主张。
seed42 的 −20pp 维持"单次运行噪声"归因（R-1 not_reproduced + S-1 复核 0pp）。

## 7. 附：T 轮（2026-10-18）仪器自检与"一致地错"

> T 轮在真实 LLM 配额开放后做三件事：① 把 S 轮多采样家族的 K=3 变体做完（预注册判定）；
> ② 给 z3 SMT 见证层补首个专项评估批（A-18/Q7），并由其错误归因驱动一次真实语义修复；
> ③ 给跑批仪器本身做审计——本轮的三个缺陷都不是"模型能力"问题，而是**测量/仪器**问题，
> 按本文件体例登记（引用时必须与工件同引）。

**T-3 示例通道 K=3 多数一致 + canonical input（2026-10-18）**：自由采样多采样家族前两轮
（P-1.1 norm 单采样 correct 8；S-3 K=2 精确求交 correct 3）之后，T-3 用 K=3+≥2/3 多数一致
+ canonical input 约束（60 次 spec-only 调用，$0.020577，20 任务）把跨采样重叠从
S-3 的 union 67→交集 43（保留率 64%）提升到 **union 57→交集 55（保留率 96.5%）**——
"一致性过滤器召回代价过高"的机制在 canonical 约束下**不再成立**；但零 LLM 重放
correct 仍 **8→5（损失 3）**，且 **`knapsack` 出现 3/3 一致的新幻觉**（`(1,[[1,1]])→0`，
正确应为 1）→ 判定 **`high_risk_default_off`**。方法学结论：**"自洽 ≠ 正确"**；
多数一致只能过滤"不稳定错误"，对"稳定的错误"无效；结合 R-2（后置子句过滤器 0 命中）
与 S-3（精确求交杀真检出），四轮证据共同指向**规约表达力**是示例质量瓶颈，
而非某个过滤器实现——下一步应按收益做"示例级独立核验（LLM 二次核验 expected 与规格）"
与"canonical 模板保留非平凡判别样例"，不得再以"清掉 N 个幻觉"单独作质量提升主张。
工件 `（工件已清除）`（22 项 SHA verify）。

**T-3b SMT 见证层首个专项评估批（2026-10-18，零 LLM）**：A-18/Q7 此前是"实现在场、
评估缺席"。本批 QuixBugs 41 缺陷程序、锚表内容寻址 50/50 命中、z3-solver 5.1.0、
per-clause 5s，产出 184 条非空评估子句的逐子句审计：**sat 19 / unsat 0 / unknown 0 /
timeout 0 / error 165**；`smt_witness_rate` 均值 0.088531、`smt_timeout_rate` 0.0
→ 机制层 **pass**（层在工作、超时有界、桶可逐子句复算）。**但 reach_rate 仅 0.103261**
——瓶颈不在求解器（到达求解器的 19 条 19/19 全 sat），而在"材料未达求解器"；
错误归因给出最大单项 **`result_alias_not_reached`=110 条（66%）**：SpecIR 表达式通道
后件写 `result`，而 `spec_smt` 后件自由变量域只有 `r`（见 §T-3c）。该批不做
detection 关联（中位数二分退化，低桶为空）——**只报告"无对照"**，MDE≈16.57pp 已披露。
工件 `（工件已清除）`（7 项 SHA verify）。

**T-3c `result`/`r` 别名缺口修复（2026-10-18）**：T-3b 的错误归因直接定位到
`src/specs/spec_smt.py::_collect_post_constraints` 的自由变量域缺口——表达式通道后件
普遍引用 `result`，而该层只认 `r`，导致 110 条子句**保守未达求解器**（不是求解失败）。
修复（token 感知 AST 归一：仅当 `result` 不在签名参数中时把后件/不变式 `Name(id="result")`
改写为 `r`，解析失败保守回退；参数名确为 `result` 时不归一）后零 LLM 复跑，见
`（工件已清除）`。**口径纪律**：T-3b 旧批保留为
**pre-fix 基线**（不得删除/改写）；T-3c 是新配置批次，两者并列引用；logic 档启用 SMT 的
批次在 T 轮之后 reach 提升属**行为变更**（仅对之前被保守跳过的子句新增判定，
不改变已判定子句的结果），跨 T 轮批次不得混池。

**T-4a `run_preflight.py --check-quota` 的"闸自身坏了"（2026-10-18）**：批次前置闸的
配额探测 `quota_probe()` 引用**不存在的符号** `src.agents.llm_client.LLMClient` →
`--check-quota` 恒 `ImportError`、结果为 `skipped=True`；strict 语义下这会让**任何**
批次前置闸失败（B2 主批次实证：第一次启动被自身闸阻断）。修复改用真实调用入口
（`import config` → `_get_llm_config()` → `_get_or_create_chat_client()` → `.invoke()`），
三态语义不变（无凭证 skipped / 异常 ok=False / 成功 ok=True），修复后真实探测
`ok=True`（1 次调用）+ 7 例 monkeypatch 回归。教训与 H2/G6 同型：**"闸判绿"不等于
"闸在工作"——安全/前置检查自身必须有正负控**；本次修复把"导入面回归锁"写进测试
（不得再 import 该符号）。

**T-4b 跑前成本估算的 input/output 份额误设（2026-10-18）**：B2 跑前估算用"input 占 76%"
的统一假设（沿用 S-1/R-1 的短批口径）得 ≈$4.5；而 R-P0-2 三批实测 `token_metrics`
的 input/output 是 **22%/78%**（output 单价 4× input）→ 正确上界应为 ≈$8.8。修正件在
seed42 完成前落盘（`t_round_b2_main_batch_20261018/PREREG_AMENDMENT_cost_estimate.md`），
判据未改、批次未中止；最终实测成本按本批 `token_metrics` 分别计价。教训：跑前成本估算
必须从历史批次的 `token_metrics` 实算份额推导，**不得用统一 input share 假设**——
份额误设可直接造成 2× 低估。

**T-5a 探针矩阵"去重丢弃"假绿（2026-10-18）**：`feature_matrix.probes_total=66` 与三个
探针模块实际注册 **68** 不符——`observability-trace-redaction` / `observability-event-bus`
同时注册于 platform 与 workflow 两个模块，运行器按 name 去重时把第二份记入
`load_errors` 后**静默丢弃**，报告仍显示 66/66 pass（与 G6 "缺席与通过同形"同型）。
修复：workflow 模块不再重复注册（保留同名函数供单测直调）；探针矩阵 66→68（含 T 轮
新增 2 个 e2e 探针）、重跑后按实测刷新 BASELINE/文档。教训：**"注册数 > 可执行数"必须
是失败信号**，不能只记 load_errors 而继续判绿。

**T-5b SHA256SUMS 路径写法与工具不兼容（2026-10-18）**：`emse_docstring_anchor_20261017/`
的清单由 `shasum` 以 `./` 前缀生成，仓内 `checksum_results.py --verify` 把 165 条全部
误判"缺失 + 清单外新增"，而 `shasum -a 256 -c` 165/165 OK——**同一事实两种工具两种结论**，
且被登记册当作"165 条校验通过"引用。修复：verify 端归一 `./` 前缀、`*` 二进制标记与
Windows 反斜杠（新增 4 例回归含"真缺失仍报错"负控）。教训：清单格式不是"谁生成都行"，
跨工具互操作必须在工具里归一，而不是在文档里注记。

**T-1 B2 锁指纹复现批：头条批次在当前协议下不可复现（2026-10-18）**：R-P0-2 头条批（`b533cff`，旧批 10/10
`git_dirty=true`、0/10 有 `model_fingerprint`）在干净切点 + 指纹 pinned + 预注册下重跑（3 seed×3 臂×87 任务，
783 task-runs，$2.249652）：**§1.1 硬门槛三 seed 全过**，但预注册判定 **`not_reproduced`**——pooled detection
aitester **3.07%** / plain_llm **11.88%** / df **28.35%**（R1 排序 `df>aitester>plain` 失败；R3 0/3 seed），
而 **R2（aitester vs df δ=−25.29pp，b/c=4/70，bootstrap CI [−31.0,−19.5]pp）仍成立且显著**。
**漂移定位（非因果证明，两条已核实的确定性差异 + 一条全局证据）**：
① logic 档自 R-P0-2 切点新增 5 个行为开关（specificity/red-regression gates、FL-spectral、mutation-advisor、
strict-fallback）；
② **R-P0-2 切点的 `llm_client` 尚无 `LLM_THINKING_MODE` 开关**（`git merge-base --is-ancestor` 实测该开关更晚加入、
非祖先）⇒ 旧批按模型**默认推理模式**运行、新批显式 disabled；token 证据：旧批 output 占比 **78.6%**
（2,276k in / 6,880k out，总 8.76M）vs 新批 **36.4%**（2,278k in / 1,305k out，总 3.58M）——**新旧不是同一推理模式的重跑**；
③ `plain_llm` 是单次提示臂、logic 档新开关不改变其生成路径，却从旧批 **1.53%** 变为新批 **11.88%**
⇒ 存在**全局性因素**（推理模式/服务端行为/测量路径），交叉批差异**不能全部归因于协议开关**。
**方法学结论**：① 旧批头条数字**对协议版本/推理模式敏感**，对外引用必须带批名 + 协议/推理模式标签，严禁与新批混池；
② "同批对照"是唯一可辩护的配对方式（与 Q5 一致）；③ 本批可作为**当前协议下的新基线**供后续批内比较；
④ 下一轮立项 **{thinking on/off} × {R-P0-2 legacy profile / current profile} 2×2 消融**（干净切点、固定 task 集、
指纹 pinned）以分离推理预算与协议开关两个因素。工件 `（工件已清除）`
（README §0.6 / ANALYSIS_REPORT 的 `profile_preset_drift` / SHA 804 项）。

## 8. 附：AA 轮（2026-10-19）"绿"可以是调度产物 — 跨文件进程级状态依赖

> 与 §7 同源的一类失效：**测试/门禁仪器自身**的问题，不是被测对象的问题。本轮零 LLM、$0。

**症状**：AA 轮收口全量（`make test-cov`，口径 `-n 4 --dist loadfile`）出现唯一一例失败
`tests/test_llm_oms_leaf_fallback.py::test_normal_path_sentinel_false`；同一文件单独跑 6/6 绿，
且**本轮此前的收口跑也是绿的**。

**机制（实测复现，不是推测）**：该用例第一条断言读的是 `src/utils/helpers._LEAF_FALLBACK_ACTIVE`
——模块级全局，只在 `extract_json_object` **入口**清零。断言发生在任何调用**之前**，因此它实际
断言的是"本进程此前没有走过叶子降级档"：一个**跨文件前提**，而不是被测契约。把污染源文件和
本文件配到同一进程即可 100% 复现，两处实测在案的污染源：`tests/test_helpers_20261019_branches.py`
（AA-5 本轮新增，末例停在 `True`）与 `tests/test_helpers_json_fence_content.py`（存量同形）。
**"此前全绿"是调度运气**：新增一个测试文件改变了 xdist 的 loadfile 分配，把一个一直存在的
顺序依赖显式化成红——不是新缺陷被引入，是旧假设被观测到。

**处置**：给 `tests/test_llm_oms_leaf_fallback.py` 补 autouse 复位 fixture（入口把全局钉成
`False`、**出口还原发现时的值**——既不假设别的文件停在哪，也不替别的文件收拾残局），并加
1 例**进程内污染重放**锁：该用例故意以 `True` 结尾，紧随其后的入口断言之所以绿完全依赖
fixture。**变异验证**：仅取消 fixture 注册 → `1 failed, 6 passed`（红在这条入口断言）；还原 →
`7 passed`。修复后四种配对顺序（两个污染源×前后序 + 三文件连跑 106 例）全绿。

**可推广判据**：任何"读进程级/模块级可变全局"的断言，只有在**同一次调用之后立即读**、
或**测试自己先把状态钉住**时才是契约；其余情形要么是顺序依赖（迟早红），要么是把
"我恰好排在前面"误当成不变式。同类先例：W 轮修掉的两处全局状态泄漏（见 `BASELINE.yaml`
`tests.total_failed` 注）——本轮的差别只是"泄漏方"与"读取方"分处两个文件，因此单文件永远测不出。

**同类面已穷举（AA-8 附带核查，非抽样）**：以 AST 扫 `src/`，判据取"函数体只有单一
`return`、且返回的是本模块内被 `global` 改写过的模块级变量"的公开 reader——命中 **4 个**：
`get_manager`（`src/api/api_manager.py:1240`）、`get_rag_retriever`（`src/graph/rag.py:64`）、
`get_report_generator`（`src/reports/generator.py:754`）、`was_leaf_fallback_used`
（`src/utils/helpers.py:689`）。前三个是单例工厂，其测试侧调用点在断言**之前**都显式钉住状态
（`tests/test_workflow.py:602-605`、`tests/test_branch_coverage_gates.py:232-235` 保存/还原 +
置位），符合上面的判据；**唯一未钉住的读取点就是 AA-8 这一处**，故本类问题到此收口，
不需要再造一个"全量重置 fixture"。复算入口（六行，无需新工件）：

```python
import ast, pathlib

mut = {
    t
    for f in pathlib.Path("src").rglob("*.py")
    for n in ast.walk(ast.parse(f.read_text(encoding="utf-8")))
    if isinstance(n, ast.Global)
    for t in n.names
}
print(
    [
        (str(f), fn.name, r.value.id)
        for f in pathlib.Path("src").rglob("*.py")
        for fn in ast.parse(f.read_text(encoding="utf-8")).body
        if isinstance(fn, ast.FunctionDef) and not fn.name.startswith("_")
        for r in [s for s in fn.body if isinstance(s, ast.Return)]
        if len([s for s in fn.body if isinstance(s, ast.Return)]) == 1
        and isinstance(r.value, ast.Name)
        and r.value.id in mut
    ]
)
```

## 9. 附：AB-7 轮（2026-10-20）"校验器给的绿，不等于消费者给的绿" — 文档表格静默丢格

> 与 §7/§8 同类：**判据仪器自身**的问题。本轮零 LLM、$0，`src/` 零变更。

**症状**：README 中英「安全审查」行、本仓测试清单行、状态登记册「门禁总数」与 J-4 行、预注册册
E4 行——共 **6 行**在 GitHub 上渲染时**整格消失**，而源码看起来什么都不缺。登记册那一格是
「验证入口」列的整列内容。

**机制**：GFM 切表格单元格**不认行内代码**——行内代码里的裸竖线照样把行切开；切完后若一行
的格数**超过表头列数**，渲染器把超出的尾格**直接丢弃**（钳到表头宽度）。本轮三类竖线来源：
shell 管道、正则交替、绝对值记号。盲区成因：G16 门禁只校验链接/锚点可达性，从来没有
"渲染后内容是否还在"这一判据。

**第二轮机制（更值得记的一课）**：第一轮修复用 **markdown-it** 做参考实现校验，结论是"已修好"；
但 GitHub 走 cmark-gfm——它按竖线前**连续反斜杠 run 的奇偶**判定转义，"两个反斜杠 + 竖线"
在 markdown-it 眼里是转义、在 GitHub 眼里仍是切格竖线。**两个实现对同一份文本结论相反**，
而我信了手里那个。判据：*校验器与消费者的口径不一致时，"校验通过"本身就是伪影*——
被校验的对象没变，变的是我用谁来判。

**处置**：判定器按 **GitHub（cmark-gfm）口径**实现，并把这条分歧单独钉成语义锁
`test_even_backslashes_before_pipe_still_splits_on_github`；另设一例与 markdown-it 逐行对照
（141 份活文档结论完全一致，该包非本项目声明依赖，缺席即 skip）。机检
`tests/test_markdown_table_integrity.py` 29 例：判定语义 8 + 当前仓库零丢格与扫描面非空 2 +
6 行修复的「宽度对账 + 还原转义必红」12 + 冻结面清单/棘轮/排除面 6 + 对照 1。
两处 fail-closed：活文档面塌缩（< 80 份）即红，不许把"没东西可扫"当全绿；修复行的定位改用
**唯一锚文本**——本轮内行号就漂过一次（§3.2 插行把登记册那行从 243 推到 244），旧写法靠
"行号自证"当场自曝，但锁本身应当不因文档增删而需要维护。

**判据的作用面须如实登记**：本锁只管「行格数 > 表头列数」这一个方向（少格只补空格，属外观）；
只管**有表头 + 分隔行**的块——缺表头的竖线块（本册 §4 首个空行之后的登记块即此形状）渲染为
段落、内容不丢，判定器如实不报。冻结面 `docs/history/` 5 行 + `experiments/results/` 4 行 = 9 行
按逐文件清单登记、只许缩不许扩（两处目录受 SHA256SUMS 保护，改写即破坏校验门）。

**可推广判据**：写任何"文档 ↔ 工件"类判据之前，先回答**消费者是谁**（GitHub 渲染 / 本地
mkdocs / 纯文本阅读），并拿该消费者的真实实现或规则做对照；只与自己写的检测器一致 = 自证。
另一条：草稿数字必须现算复核——本轮冻结面初稿凭记忆写 12 行、用例数写 27 例，二者都与实测
（9 行、29 例）不符，均在登记前被现算纠正。

**引用纪律**：不得引用"全仓 markdown 表格已全部合规"；可引用的口径是"**活文档**零丢格 +
冻结面 9 行如实登记"。

---

## 10. 附：AB-8 轮（2026-10-20）容错分支的覆盖面按"解析器返回域"枚举，不按"我想到的坏输入"

AB-5（同日的前一轮）给数据集适配层补了 24 例坏输入锁，判据写的是"坏行要留下痕迹、不得
中止整批"。本轮把同一族输入再推一步——`json.loads` 合法返回**六种**值（对象、数组、字符串、
数字、布尔、null），AB-5 只测了"解析失败"和"对象里缺主键"两种。用一次性探测脚本把五种合法
非对象行（`[]` / `null` / `"abc"` / `3` / `true`）逐一喂进生产函数后，同一条判据在**五个入口**上
是**未满足**的——产品侧三处读取器与门禁两处（它们都直接对 `json.loads` 的结果取 `.get` 或
`{**data}`）；加上主键域那一处，本轮共**六个缺陷位置**。

**症状**：一行 `[]` 让整批加载抛出 `AttributeError: 'list' object has no attribute 'get'`。
这不是"少一条任务"，是**整个数据集通道不可用**；G8 门禁更荒诞——它的文档声明"退出码 1 表示
数据未就绪"，实际是崩溃：Python 崩溃码恰好也是 1，所以阻塞看起来"生效"，但调用方
`experiments/run_full_stack_swe_bench_pro.py` 拿不到任何报告，只有一段 traceback。

**根因**：同一处假设被复制了六份——"解析成功就意味着那是个对象，主键就意味着那是字符串"。
按 `except JSONDecodeError` 分支的存在来推断"这一行已经安全"是错的：JSONDecodeError 只覆盖语法损坏，
不覆盖语义形状。

**同族的第二类**：主键。`{"instance_id": [1]}` 让映射写入处抛 `TypeError: cannot use 'list'
as a dict key`；而 `{"instance_id": 3}` / `{"instance_id": true}` **不崩**，键写成 int/bool
存进映射，下游按字符串主键查表永不命中——补充文件看起来加载成功（日志还写着"已加载 N 条
记录"），实际整份零生效。这一类与 AB-5 修的 falsy 主键（null / 空串 / 0）同族，但危害不同：
falsy 主键当时是**静默丢弃**，非字符串主键是**静默存活**。

**第六处不是我提前想到的，是锁跑红之后才定位到的**：端到端那一例
`test_int_key_never_reaches_the_enrichment_lookup` 实测红，traceback 落在
`dataset_loader.py:696` 的 `"__" in task_id`，报错 `TypeError: argument of type 'int' is not a
container or iterable`——案例集原本只按"整行不是对象"设计，漏了"行是对象但主键不是字符串"
这一层。

**处置**：六处统一对齐本项目**已有**的写法——`dataset_ult.py::_load_raw_data:222` 早在
`if not isinstance(raw_row, dict): skipped += 1; continue`（本轮核对时它已是正确形状，
所以这一处不需要修改）；门禁主循环按它自己 `unparsed_` 分支的先例把畸形行计入
`total_tasks` 与问题清单，保持 fail-closed，只把崩溃换成有痕迹的报告。
`_load_enrichment` 与 G8 的补充文件加载按类别计数、结束时各汇总一条 warning（三类痕迹：
非对象行、缺主键行、主键是列表或字典行）；返回值仍为 `dict[str, dict]`，键域收窄为 `str`。

**一处枚举被探测否证（注意否证它的不是锁）**：`dataset_ult._iter_records` 的 JSONL 分支
`yield json.loads(line)` 未过滤，据此我写下"`[]` 会被原样 `yield` 出来"的断言。同一个探测脚本
给出相反结果：`[]` 那一份文件返回**空**——该函数**开头**就把首行以 `[` 起始的整个文件识别为
JSON 数组，而数组分支早就有 `isinstance(row, dict)` 过滤，于是 `[]` 那一行根本走不到 JSONL 分支。
但另外四种（`null` / `"abc"` / `3` / `true`）**确实被原样 yield**（探测值 `[None]` / `['abc']` /
`[3]` / `[True]`），ULT 通道不崩只是因为消费者在 `dataset_ult.py:222` 把它们过滤掉了。
教训两层：其一，按代码形状推断执行路径不等于路径真的被走到，推断必须在写完后实测一次；
其二，同一份坏输入在不同格式假设上性质不同——`[]` 在 JSONL 分支是"非对象记录"，在数组分支是
"整份文件是个空数组"。本锁文件里因此**没有** ULT 用例：`dataset_ult` 的这条形状域是靠一次性
探测确认的，不得引用成"ULT 分支已被回归锁覆盖"。

**另一条更该记的：本轮空转的是验证工具本身**。第一轮变异验证报"7 处守卫全部必红"，它一个东西
都没测到——脚本用 `-k "<中文标签>"` 过滤用例，而标签不是用例名，**匹配零条**；pytest 以
"47 deselected"非零退出，脚本把"退出码非零"当成"变红"。这正是 AB-5 收紧判据时点名的
"绿着但空转的锁"，只不过这次空转的是用来证明锁不空转的那段脚本。第二轮改法：不带过滤跑整个
文件，要求基线 0 failed、每处变异 `failed >= 1`，并打印**具体变红的用例名**逐项核对是否是对应
守卫的那几条；文件还原用 sha256 断言字节一致（工作树有大量未提交变更，绝不能用 `git checkout`）。

**可推广判据**：容错分支的覆盖面要按**"解析器能产出几种值"**枚举，不按"我遇到过哪几种坏
输入"枚举；同一族判据应当复用现成口径而不是新设计。本轮六个缺陷位置的正确写法在仓库里早已存在
（`dataset_ult` 的 `isinstance` 过滤、门禁的 `unparsed_` 分支），缺的只是一致性检查。再加一条：
**验证工具自己的判据必须能失败**——"基线必须全绿 + 每个变异必须点名变红了哪一条"，否则它给出的
"全部必红"没有任何含义。汇总类 warning 不得跨类别复用同名信息（三类痕迹各指一类），这一条现在有锁：
`test_three_bad_classes_are_traced_separately` 与 `test_each_category_is_counted_separately`。

**引用纪律**：AB-5 那句"坏行只作废那一行、不中止整批"在 2026-10-19 登记时**只对已测的两类
形状成立**；本轮之后才对整个 `json.loads` 返回域成立——但**只到形状域**，字段值域（例如
`FAIL_TO_PASS` 里放 `null` 元素）本轮一例未测。引用该判据时应指明"含非对象行与非字符串主键"，
不得引用"数据集适配层的坏输入容错已完备"——`swe_bench_{full,lite,mini}` 三个子集文件在盘上
仍是 **0 字节**（登记册 §4 AB 轮行 ①），本轮所有案例都是 `tmp_path` 现写的坏输入，不能替代
"真实数据集跑通"的证据。

## 11. 附：AB-9 轮（2026-10-20）同族判据换一层要重述 — 分析侧"响亮崩溃可接受，静默缩分母才是缺陷"

**为什么会走偏**：AB-8 的结论一旦成立，下一步看起来是机械的——把返回域普查扩到 `experiments/`，
再给每一处 `json.loads` 补形状守卫。本轮先把普查做完、再决定处置，结论方向相反：**68 处调用点里
42 处在任一非对象返回下响亮崩溃**（`AttributeError` / `TypeError` 一路上抛到 `main`，非零退出、
不产报告），9 处已显式判形状并给出可读错误或 `exit 1`，5 处崩溃被上层 `except` 吞掉但已在报告里
留痕，只有 **12 处**是"至少一种形状下不抛、只让数据消失"。若照机械结论给 68 处补 `isinstance`，
等于把 42 处"能被发现的失败"改写成"发现不了的数字"。

**判据按读者位置定**：产品侧的坏输入让**一条数据通道**整批不可用或静默零生效，用户看到的是"配了
但没生效"；分析侧的坏批次让**表格的分母**少几份，而逐批次表与池化区间照出，读者看到的是"数字正常"。
前者要修的是"别整批死"，后者要修的是"别悄悄少算"。12 处静默点内部还要再分一类：**已有显式
`isinstance` 且带计数或原因码**的刻意静默（6 处）与其余 6 处（本轮处置 1 处、登记下一轮 5 处）
不是一回事，前者不改。

**处置那 1 处时新增一条硬约束**：AB-8 门禁的先例是"只增键、既有键与数值一个不动"，本轮被改的
`target_quality_replay.py`（入口 `make target-quality`）产出的报告落在 `results/main_batch` 这个
**SHA256SUMS 保护目录**内、数字又被 `BASELINE.yaml` `target_quality` 节引用，于是"只增不改"这句
承诺的验证方式只能是**逐字节复现**——锁里对盘上 10 份批次（实测跳过 0 份）重放 `_render`
并与入库报告逐字节比对，且先断言输入文件确实存在，否则空目录会让这条锁空转给出"通过"。

**顺带照出来的两条与"形状"无关的读数**：其一，`experiments/` 顶层只有两份人写 JSON
（`price_table.json` 与 `injection_benchmark_samples.json`），实测都不在任何 `SHA256SUMS` 之下，
前者是其中唯一"多消费者"的一份，5 处读取全部无形状保护（本轮不动，因后果全是响亮崩溃），
其中 `spec_examples_generator.py:277` 在**付费 LLM 重放之后**才崩——同形状的风险在不同调用点上
代价并不对称；后者单消费者，五种形状实测同样响亮崩溃，值域也未判（`{"positive_input": null}`
实测 `TypeError`），崩在测试收集期。其二，扩展名 `.jsonl` 在本仓不等于行分隔：`ULT.jsonl` /
`ULT_Lite.jsonl` 首字符是 `[`，按整份 JSON 数组读。

**可推广判据**：一条缺陷族跨层复用时，**判据要按"谁在读这个工件、读不到会怎样"重述一遍**，
不能把上一轮的修法直接平移；普查的产出是**分类**而不是处置清单。

**引用纪律**：本轮未逐处复核 42 处响亮崩溃的退出码与消息是否一致（只读数到"一路上抛到 `main`"），
也未处置其余 11 处静默点。因此不得引用"`experiments/` 层 JSON 返回域已收口"；可引用的口径只有
"68 处已逐处读数分类，12 处静默点已列名，其中 1 处已改为计数披露并带 14 例变异验证锁（6 处锚点
逐处删除全部转红），其余 11 处按机制登记"。字段值域仍未测，与 AB-8 边界 ① 同形。
详见 EXPERIMENTS_JSON_DOMAIN_AB9_2026-10-20（分册已删除）。

## 12. 附：AB-10 轮（2026-10-20）缺席与读不动不得报成"零命中/一致/未要求"

**这一轮窄在哪里**：AB-9 的分类里还剩 5 处登记站点，其中 3 处属于同一机制——读取失败后
**代码继续往下走，并在报告里给出一个正向读数**。它比"静默缩分母"更糟一档：缩分母只是少算，
这里是把"没读到"翻译成"读到了、且结论成立"。本轮把这一族写成判据：**缺席 / 读不动** 必须表现为
**报错**或**显式的"无法核验"**，绝不允许表现为 **零命中 / 一致 / 未要求**。

**第一条实测：恒真的自我比对**。上游工件读不到时，脚本会把本地归档 gold 包装成"官方测试"再与
本地 gold 归一比对。`_normalize_test_body` 剥掉 `def` 行、其余逐行 strip，包装与原文在这一步同构，
所以比对**恒真**——实测 `upstream_bodies_equal = True`，而此时一份上游数据都没读到。AB-9 把这条
写成推测（"拿本地 gold 和自己比并报一致性"），本轮由复算坐实。**教训形状**：一致性字段最危险的
失效不是报 False，而是**在没有对照物时报 True**——False 至少看起来像结论，True 会被下游直接引用。

**第二条实测：改它之前先量真路径走不走**。盘上两份上游数组实测顶层 `list` 分别长 200 与 3909，
逐行 `isinstance(dict)` 后 **全部保留、丢 0 行**；项目侧 71 条任务按 `code` 对齐后
**71/71 命中上游 `tests` 分支，0 条走包装分支**。这条普查决定了本轮能不能既修恒真路径、
又让受 `SHA256SUMS` 保护的入库工件**逐字节不变**——0 条走该分支 ⇒ 新增的"无法核验"取值在真数据上
不触发。反过来说，它只在缓存缺失或形状坏掉时才出现，而那时它恰好产出最像结论的错读数：
**罕见路径 + 高置信读数**是这类缺陷的指纹，别因为它跑不到就不管。

**第三条：复现 README 的两个开关不在命令行上**。入库报告要求逐字节复现，两轮才对上：
第一轮只给 `--supplement`，4c 节整段缺失（21 行差异）——**4c 的开关是"某个工件在不在输出目录"，
不是 CLI 参数**；第二轮发现 `--from-json` 会**就地重写**它读的那份 JSON，于是复算必须先复制出去，
全程只碰 `/tmp`。**口径**：渲染器里"文件在不在"式开关，等价于把一份数据变成一节段落，
这种开关本身就该被披露——本轮改为在原文位置写"本节未渲染 = 工件缺席，不等于该测量没做过"。

**可推广判据**：凡是"读不到就返回空集合 / 空字符串 / False"的读取函数，要按**调用方拿它做什么**
分类：拿它做**存在性判定**的（"有没有该测试"），空值会被读成"没有"，必须 fail-closed；
拿它做**比对左值**的（"和官方一不一致"），空值会被读成"一致"，必须返回三态里的第三态。
两者都不能靠加 `isinstance` 解决——那只挡形状，挡不住"形状对但内容为空"。

**引用纪律**：本轮处置 12 处静默点中的 2 处（AB-9 处置 1 处，刻意静默 6 处不改，**还剩 3 处登记**），
且只核了 `_load_upstream_array` 的 4 个调用点。因此不得引用"`experiments/` 层 JSON 返回域已收口"、
"上游工件缺失时相关脚本一定会失败"或"`upstream_bodies_equal` 从未被误报"——最后这条的否定证据
只是本轮一次实测普查（71/71 命中上游分支），不是长期性质。包装分支的标签
`ULT_Lite.jsonl:test_list(wrapped)` 里数据来源实为本地归档 gold，属措辞不准，本轮已在代码注释写清
但**没动标签字符串**（改名不影响任何读数，不该混进这一轮的 diff）。
详见 ABSENT_VS_ZERO_AB10_2026-10-20（分册已删除）。

## 13. 附：AB-11 轮（2026-10-20）缺席有三种，挤在一个桶里就只剩一种

**这一轮窄在哪里**：AB-10 写下"缺席/读不动不得报成零命中"之后，剩下 3 处登记站点看起来都"已经
披露了"——它们确实抛了 `available=False`、确实打了 WARN、确实数了 `damaged`。逐处复算后发现失效
点比 AB-10 更细一层：**同一个字段被三种事实共用，而三者对结论的方向相反**。

**第一种塌缩：一个字段三种缺席**。`spec_augment_applied` 里生产者显式写下的 `null`（真的没触发）、
详情行根本没这个键（上一代生产者没写）、第二遍原始读取失败（工件读不动）三者都落进 `none` 桶，
于是报告说"增广零命中"。三态改造的判据不是"多加两个枚举值"，而是：**每个取值只能回答一个问题**——
`none` 回答"触发没有"，`key_absent` 回答"生产者写没写这个字段"，`audit_unreadable` 回答"我们能不能
知道"。实测盘上 df 臂 50/50 行键在且为 `null`，所以改造后入库读数逐字节不变、`key_absent` 与
`audit_unreadable` 在真路径 0 实例——**0 实例恰恰是必须分桶的理由**：不分桶时它们永远是 0，
谁也不会去看一个 0 的桶；一旦非 0，它会被读成"零命中"。

**第二种塌缩：披露的形对了，内容是假的**。`_profile_presets` 有四种失败机制（`git show`、
`ast.parse`、`ast.literal_eval`、找不到赋值），全部返回同一个 `{}`，而调用方把原因**写死**成
"git show config.py 失败"。这段代码看起来完全符合 AB-10 的判据（它确实报了"无法核验"），
但三种与 git 无关的故障被统一报成 git 故障——排查的人会去查 git，而真凶是 AST。**"无法核验"的原因
本身是一个读数**：写错它和写错一个百分比一样是错的读数，只是没人会给它跑数值校验。同一函数里
`old.get(profile) or {}` 更直接：档位不存在与档位存在且两边逐键相同**同形**，都渲染成"无漂移"——
这是"缺席被翻译成一个正面读数"的最后一个未登记变体。

**第三种塌缩：作废是一个读数，不是一件事后细节**。`parse_trace_file` 读到坏行返回 `None`，
调用方把整个文件塞进 `arms["unknown"]["damaged"]` 后 `continue`：一个 `meta.baseline` 写着臂名、
文件名也带臂名的文件，仅仅因为坏在第 5 行就被归成"不知道哪个臂"，而它坏行之前已经解析出的
5–16 条记录**一个字节都没留下**。全仓普查（148 个 `*/traces`、9086 个 trace 文件）实测
5 个损坏文件、合计 **44 条记录被无痕作废**。**整份作废是一个合法的口径选择**（判定分母不因损坏
而膨胀），**无痕作废才是缺陷**——所以处置不是"改成部分采用"，而是归臂口径与完好文件一致、
并把被作废的量写成披露行。改前改后对 5 个损坏目录做"旧逻辑 vs 新逻辑"复刻：逐臂
`files` / `pattern_files` / `category_files` 全等，只有 `damaged` 从 `unknown` 搬回自己的臂。

**顺带照出的一条：入库声明也会因输入增长而变假**。`main_batch/mast_distribution_report.md`
写"963 个 trace 文件……可用本脚本逐位复算"，同一脚本对同一目录今天实跑给出 **2007 个文件**——
差值是报告落盘后补写进目录的 trace。这句话当年是真的，现在仍然是同一串字节，所以它变成了假的。
本轮不改写受 `SHA256SUMS` 保护的工件，改为把 staleness 锁成一个用例。**口径**：任何"可复算"声明
都隐含一份输入快照；复算失败的原因可能不在算法侧，而在输入侧，而工件本身不会告诉你哪一侧动了。

**一条关于验证方法自己的教训**：变异脚本 c4 锚点第一版把 `continue` 插进原 `if` 块，留下孤儿缩进
⇒ 整个测试文件 `ImportError`、收集数 86→41。如果脚本只要求"删掉守卫后有红"，这条会被记成
"7 例转红，锁成立"——实际上被测代码根本没跑起来。**"变异前后收集数相等"这条前置检查存在的意义
就是防这种假红**（AB-8 登记过 `-k` 匹配零条导致的"全绿空转"，AB-10 把它具体化为收集数比对，
本轮它防的是语法崩）；本轮另加 `compile()` 预校验，让"锚点写坏"在跑 pytest 之前就被点名。
**判据**：变异脚本要拒绝的不仅是"删守卫仍全绿"，
还有"删守卫导致整文件无法收集"。

**引用纪律**：本轮处置完 AB-9 表中标"下一轮"的 3 行，但**不得**引用"AB-9 那三行已全部收口"——
`analyze_t1_b2_main_batch.py` 那一行原文列了**三件**机制，本轮**0 件处置**——`(x or {})`
降空对象、`GATES.json` 缺席渲染成 `gates_all_pass: FAIL`（缺失被当成**不通过**，方向保守但仍是把
缺席读成一个数）、宽 `except Exception: continue` 把一对种子从配对比较里静默摘掉。本轮真正改的是
同一文件里的**另一站点**（profile 预设读取），该行原文从未列过它，所以"本行部分由 AB-11 处置"是
归因错位，收口时已就地撤销。三件与站点 c 那件收口后逐个实测均 **0 实例**：该目录 11 份 JSON 0 份
读不动；3 份种子批次顶层均为对象、`results` 为非空对象且三臂全在场（`or {}` 不改变任何一个）；
`GATES.json` 实为对象且 `all_pass=true`；原批次目录 glob 命中 10 份、解析成功 10 份、被 except 摘掉
0 份、三 seed 配对无缺席；9086 个 trace 文件里非对象行 0；`mast_trace_analysis.py` 那一行原文指的是
**非对象行仍计入分母**，本轮实测盘上 0 实例、未处置、继续登记；重复 `task_id` 缩分母发生在
**共享 loader** 里，本轮只在 augment 侧命名披露，没动共享 loader。详见
ABSENT_VS_ZERO_AB11_2026-10-20（分册已删除）。
## 14. 附：AB-11 轮（2026-10-20）同值不是证据 — 覆盖率读数在同一条树上抖 ±2 行 / ±1 弧

AB-11 收口时先按前几轮的老写法，把 `coverage.xml` 复算 18371/18896 行、6606/7044 弧与前几轮**逐位
相同**登记成"`src/` 零改动"的佐证。随后 `make gates` 的 `format` 门抓到本轮新增的 reason 字符串写成
两段隐式拼接、须 `ruff format`；格式化后又连跑两次全量口径，**同一条 `src/` 树**得到三个读数：

| 跑次 | 结果 | 耗时 | 行覆盖 | 分支弧 |
| --- | --- | --- | --- | --- |
| 收口确认跑（格式化前） | 9683 passed / 5 skipped / 0 failed | 169.63s | 18371/18896 | 6606/7044 |
| 格式化后跑 1 | 9683 passed / 5 skipped / 0 failed | 171.14s | **18369**/18896 | **6605**/7044 |
| 格式化后跑 2 | 9683 passed / 5 skipped / 0 failed | 170.46s | 18371/18896 | 6606/7044 |

三跑的 passed / skipped / failed / collected 全同，只有覆盖率读数动。逐行比对两次的 term-missing 表，
唯一变动的文件是 `src/utils/process_utils.py`：低读那一跑少 641-642 两行、多 1 条未覆盖弧。定位到
638-642：`os.killpg(pgid, SIGKILL)` 抛错后 `if proc.poll() is None:` 回退 `proc.kill()` 的分支——同
函数邻近的 613 / 616 / 626 都带 `# pragma: no cover`，唯独这条没有；隔离跑 3 个相关测试文件 6/6 命中，
带 `-n 4 --dist loadfile` 的全量跑偶发漏命中。**这是一条负载相关的竞态路径，与本轮改动无关。**

**判据（本轮新立三条）**：

- **同值不是证据**。"这轮和上轮数字一样"只证明两次观测同值，不证明被观测对象没动。要证"`src/` 零
  改动"，用的是**改动面文件清单**；覆盖率同值最多算一次观测记录。
- **覆盖率总读数有非零抖动下界**。登记口径应写成"读数为 X，同树复跑观测到 X±2 行 / X±1 弧"，并点名
  抖动来源。历史上各轮写的"逐位相同即佐证"自此**只按观测理解**，不作推断前提。
- **"分母不变"同样是弱证据**。本轮分母 18896 行三跑全同，但同值的是**语句总数**：一次等行数的改写
  （删一行注释、加一行注释）分母不动、覆盖行数照变。所以"分母不变"最多排除"增删语句"，不排除"改动
  内容"；`src/` 是否被动过，仍然只能看改动面文件清单（`git diff --stat` 在本树大量未提交时不可靠，
  故本轮用的是逐文件核对）。
- **抖动源要登记不要抹平**。给 `process_utils.py:638-642` 补 `# pragma: no cover` 能让读数变稳，但那
  正是本项目禁止的"用注释藏掉会说实话的分支"；正确做法是补一条确定性锁（已列为下一轮候选）。

**引用纪律**：不得据本节引用"覆盖率已无抖动"或"覆盖率同值可作零改动佐证"；可引用的是"该竞态分支已
定位、隔离可复现、全量偶发漏命中，抖动下界 ±2 行 / ±1 弧已写入 `BASELINE.yaml` 覆盖率行注释"。

### 14.1 站点 d 已由 AB-12a 处置（2026-10-20 补记，`src/` 零改动）

上面判据第四条写的"正确做法是补一条确定性锁（已列为下一轮候选）"已在 **AB-12a** 落地：
`tests/test_windows_process_termination.py::TestPosixSigkillFallback` 5 例——`ProcessLookupError` /
`PermissionError` / `OSError` 三种抛出各一例、"组长已退出（`poll()` 非 None）不得再补 `kill()`"反向弧、
"兜底 `kill()` 自己抛 `OSError` 不外漏"抑制弧。**`src/utils/process_utils.py` 一行未改**，这条分支仍按
真话参与覆盖率口径，没有用 `# pragma: no cover` 把它藏掉。

判据照旧是"删掉守卫必红"，只是作用对象从"本轮新写的守卫"换成"既有分支本体"：变异基线 collected=21
全绿，删掉整段兜底 **5 红**、把 `if proc.poll() is None` 改成无条件 **1 红**、去掉 `contextlib.suppress`
**1 红**、拆掉整段 `try/except` 让 SIGKILL 失败直接上抛 **5 红**，"只改 debug 文案"的行为中性对照
**0 红**（收集数 21 全程保持、sha256 断言字节还原——本树大量未提交，绝不用 `git checkout` 回滚）。

复测：AB-12 刷新 BASELINE 后**连跑两次**全量口径，18371/18896 行、6606/7044 弧**两次同值**
（177.96s / 180.48s，两跑均 9825 passed / 5 skipped / 0 failed、rc=0）。

**登记性质（观测不写成证明）**：本轮是 **2/2 跑未见抖动**，而 AB-11 的低读出现在 3 跑中的 1 跑——两次
同值不构成"抖动上界已消除"的证明，只构成"该竞态分支不再决定读数"的机制论证（它现在由确定性锁执行）。
故 §14 前三条判据**继续有效**：覆盖率同值仍不作 `src/` 零改动的佐证，"分母不变"仍只排除增删语句。
反过来，**若日后同树复跑再现 ±2 行 / ±1 弧，即为这条锁未真正闭合的信号**，应回到本节重查，而不是把
登记值改成新读数。

## 15. 附：AB-12 轮（2026-10-20）0 实例要连测量覆盖面一起锁 — 漏扫的探针也给出干净的 0

AB-12c 改造 `experiments/mast_trace_analysis.py` 之前先做只读普查（"可解析但不是对象的 trace 行"
在盘上有几例）。第一版探针打印：

```
扫描目录数=129 文件数=783 行总数=5964 读不动=0
非对象但可解析的行数=0 类型分布={}
```

按这句就可以写"0 实例，改造不动任何入库读数"。**但它是漏扫出来的 0**：探针写的是
`{p.parent for p in ROOT.glob("experiments/results/**/traces*") if p.is_dir()}`——取的是 trace
目录的**父目录**，于是默认分析目录 `main_batch/traces` 一个目录的 2007 个文件全没被打开。
第二版以目录本身为根，同口径给出 138 目录 / 8539 文件 / 125270 非空行 / 非对象行 0。

**测量工具犯了它要测的那个错**：代码把"整份都是非对象行"读成"真的没有事件"，探针把"没扫到"
读成"没有实例"。二者同构，所以这条只能靠**把覆盖面写进断言**才发现，不靠"看着合理"。

**判据（本轮新立四条）**：

- **普查类读数与覆盖面下界同句登记**。`tests/test_experiments_mast_nonobject_ab12.py`
  `test_repo_wide_non_object_census_is_zero_and_instrument_covered` 同时断言
  `目录数 >= 138`、`文件数 >= 8539`、`非对象行 == 0`；覆盖面回落先红，不允许用漏扫的 0 顶替普查的 0。
- **变异验证会反查测试自身的假阳性覆盖**。锚点 c4（撤销"损坏优先于形状不合"的判定）第一次跑出
  **0 红**——不是守卫多余，是测试输入里多放了一条 `task_start`，`not records` 先为假，把被测守卫
  整个遮住。换成"整份都是非对象行 + 一个坏行"后该锚点 1 红。**"删掉守卫仍然全绿"有两种原因**：
  守卫真的冗余，或测试根本没走到它；两者都必须点名用例后才能下结论。
- **同一册内两条陈述冲突时以盘上为准，没有锁的那句作废**。AB-11 册 §4 写"站点 c 的 `/tmp` 复算与
  入库报告 `cmp` 相同"，§5 又写"报告 963、实跑 2007、逐位复算声明失效"。AB-12c 复跑证实**§4 是
  过度声明**（第 3 行第 123 字符即不同）。差别只在 §5 有一条锁、§4 一句没有任何断言撑着——
  自此"逐字节相同"这类话必须指名是哪条锁在跑，否则就地降级为"未验证"。
- **预期红数订高不是缺锁**。首轮 7 处 `[MISS]` 全部是把真路径组也计进候选所致；逐处下调为实测值后
  每处仍 ≥1 红且逐处打印变红用例名。反过来，把阈值写成 1 蒙过也算自欺——阈值下调必须与用例名同印。
- **披露自身的计数也要划分**（AB-12d）。共享 loader 把"无主键行"按五种机制分开记，第一版让不可哈希
  键同时进 `not_string` 与 `unhashable`——5 行报成 6 行。这不是排版问题：分桶数字正是读者拿来判断
  "这个臂到底有几行"的，虚增与混同是同一类错读的两个方向。锚点 d5 专打"一行进两个桶"，
  锁是 `test_the_five_buckets_partition_the_rows_so_counts_are_not_inflated`。
- **0 实例的桶必须由合成语料压等式**（AB-12d）。普查把 glob 命中分成 `judged / empty_details /
  other_schema / unreadable` 四桶并断言四桶之和 == 命中数；真批次里 `unreadable` 与"无可用臂"两桶
  **各 0 例**，所以把它们的记账行删掉，真路径那条等式照样平（242+2+2+0 == 246）——d11 首轮 0 红
  就是这个原因。补一份四桶全非空的合成语料后同一锚点 1 红。**覆盖面下界只锁"扫了多少"，
  锁不住"出局的那几份有没有被点名"**，后者要靠能把每个桶都撑开的输入。

**引用纪律**：不得据本节引用"全仓 trace 无形状问题"作为其他结论的佐证（普查面仅
`experiments/results/**/traces*` 里的 `*.trace.jsonl`，且只覆盖形状与可读性，不覆盖语义）；
可引用的是"138 目录 / 8539 文件 / 125270 行实测非对象行 0，覆盖面已写入断言下界"。

## 16. 附：AB-13 轮（2026-10-20）字段名里的单位不是实现约束 — 币种不参与判定，人民币就被累加成美元

`experiments/emse_stats_report.py` 的成本块输出 `total_usd`、`usd_per_detection`、`$/task`。
字段名把单位写死了，实现里却**没有一行看过 `currency`**：价目表条目长这样——

```
"<某 CNY 计价模型>": {"input_per_mtok": 0.5, "output_per_mtok": 2.0, "currency": "CNY"}
"deepseek-flash":   {"input_per_mtok": 0.3, "output_per_mtok": 1.2, "currency": "USD"}
```

前置探针（`/tmp/ab13_probe2.py` R4）用一条上述 CNY 模型的合成行实测：
`total_usd = 2.5`、`n_priced_rows = 1`、报告表格里它印在"总 $"那一列。
**人民币价格被当作美元累加，而且账面看起来完全正常**——分母非空、单价非空、没有任何不可计价披露。
这不是"精度差一点"：`usd_per_detection` 是本轮成本-效果主张的分子，币种错一次就整体错一个汇率。

判据链走到这里换了对象：AB-9…AB-12 处置的是**返回域**（坏输入进来怎么办），本轮的缺陷在
**声明与判定脱钩**（字段名声称的东西，实现根本不检查）。

**判据（本轮新立三条）**：

- **单位/币种由字段名声称时，实现必须参与判定**。锚点 c1（删掉币种闸门）转红 4 例、
  c2（把缺席默认成 `USD`）转红 2 例。默认成任何一种单位都不行：`currency` 键缺席记
  `currency_absent`，与 `currency_not_usd:CNY` 分桶——"没写币种"与"写了不是美元"是两件事，
  前者连汇率方向都无法判断。仓内 `statistical_analysis.py:991` 是**另一条口径**（缺省视为 USD
  并随行输出 `currency`），本轮不统一：那个字段名不声称美元。分歧本身登记入册，不得写成"已统一"。
- **改口径撞上旧断言时，先裁决旧期望，改后必须让该例仍测它声称的东西**。币种闸门一上，
  `tests/test_emse_stats_report.py` 两例立刻红——它们的合成条目不写 `currency`，新口径下从
  "计价成功"退化成"根本没计价"。裁决是**旧期望本身不对**（不写币种就该算无法核验），
  于是改输入而非放宽断言。但 `test_zero_detection_no_division` 补完 `currency` 还不够：
  它声称的是"检出为 0 不除零"，而分子为 0 时 `usd_per_detection` 为 `None` **与守卫无关**，
  该例会在"根本没走到守卫"的状态下报绿。故另加 `n_priced_rows == 1 and total_usd > 0`。
  这是 AB-12c §15 那条"删掉守卫仍全绿有两种原因"出现在**测试夹具层**的同型问题。
- **关掉一条尚未发生的通道，必须同时锁"真批次不受影响"和"闸门不是空转"**。真批次三臂 783 行
  只用 `deepseek-flash`（USD 已登记），`n_unpriceable` 全 0 ⇒ 闸门对入库读数改变 0 行，这是
  "修而不重写 `SHA256SUMS` 保护工件"的全部依据（R6）。但"0 行受影响"同时也是一条**闸门可能
  从没执行过**的嫌疑，所以另立两例：一条 CNY 计价模型与一条价格为 null 的模型
  压住分桶，覆盖面下界 `行数 >= 783`、`文件数 == 3`、`实际用到的模型 ⊆ 已登记 USD 模型` 写进断言。

**引用纪律**：不得据本节引用"成本口径已全仓统一"（两套口径并存）、"真批次成本被改过"
（受保护读数逐位不变）、"币种闸门提升了任何读数"（它只收窄 `total_usd` 的准入，真批次 0 行受影响）。
可引用的是"`total_usd` 的准入现在要求条目显式登记 `currency: USD`，非 USD 与币种缺席一律计不可计价
并按机制点名"。

## 17. 附：AB-14 轮（2026-10-20）判定只写一遍 — 同一个"是不是美元"仓内写了四遍且互不相同，第五遍干脆没写

AB-13 把 `total_usd` 那一处的币种闸门立起来时，顺手在处置第 3 条写了"仓内另有口径、本轮不统一"。
本轮就是那句"另有口径"的账：**同一个判断在五处被写出来，前四遍互不相同，第五遍根本没写**。
前置探针（`/tmp/ab14_probe.py`、`/tmp/ab14_probe2.py`，只读 + 只写 tmp）逐处实测：

| 站点 | 改前写法 | 实测读数 |
|---|---|---|
| `src/budget/pricing.py` | `entry.get("currency", "USD")` | 键缺席**默认成美元**；同处值为 `null` 时不计价 ⇒ 一个站点给两种缺席两个相反结论 |
| `experiments/statistical_analysis.py`（`cost_analysis`） | `models[m].get("currency") or "USD"` | 键缺席 / `null` / `""` **三种事实一律印成 "USD"**；币种集合大小写敏感，`USD` 与 `usd` 并存 ⇒ 整臂成本 `None` 而 `missing_models` 为空 ⇒ 报告落一行"未计价——（缺: ）"（无因）；币种是 `123` 时原样流进声明为 `str` 的单元格，是 `["USD"]` 时 `set` 推导抛 `TypeError` ⇒ CLI 退出码 1、**整份统计报告不产出** |
| `experiments/spec_examples_generator.py` | `str(entry.get("currency") or "").upper()` | 缺席一律剔除（与上面两处相反）；**不 strip** ⇒ `" USD "` 被剔；条目不是对象时 `.get` 直接崩在计费路径 |
| `experiments/emse_stats_report.py` | 同上 + `startswith` 判定 | 同上，且非 USD 与缺席共用归因词汇 |
| `experiments/analyze_t1_b2_main_batch.py`（`add_cost`） | **从不读 `currency`** | 非 USD（或没登记单位）的价目被原样累加进名为 `cost_usd` 的字段——与 AB-13c 同型，但这里连"判错"都算不上，是**没判** |

**判据（本轮新立三条）**：

- **判定只写一遍，站点差异只允许出现在"有没有地方把单位写出来"**。共享谓词落在
  `src/budget.pricing.currency_status`，值域七族（`absent` / `null` / `blank` / `usd` /
  `other:<NORM>` / `not_string:<T>` / `entry_not_object:<T>`），13 个输入落 **9 个互不相同的读数**
  （显式集合相等断言，不是"数量等于 9"）。可呈现性另立 `currency_label`：`usd` → `USD`、
  `other:<NORM>` → `<NORM>`、其余 → `None`。于是带币种列的统计报告**可以**对 `other:CNY` 计价
  但标签必须是归一化后的 `CNY`；单一美元列的 `total_usd` / `cost_usd` 对非 USD 一律剔除。
  两处处置不同而判定相同——**不许**反过来（用"币种不可判定"的输入去推一个单位名）。
- **"这条 term 看起来多余"不能代替锁，也不能代替删除的理由**。变异验证第一版 19 处锚点里
  `cost_analysis` 闸门上的 `not currency_blocked` **0 红**：币种不可判定的状态同时让 `labels`
  变空，`len(labels) == 1` 已经先挡住了。逐条推演才找到唯一能单独触发它的输入——一个模型登记
  `USD`、另一个没写单位，且两者价目数字一字相同（`missing` 空、`labels` 大小恰为 1），
  补这条混臂用例后该锚转红 1 例。判据：**答不出"哪条输入只有它能挡"，就是没有锁**；
  这条与 §15"0 实例要连覆盖面一起锁"、AB-13"改口径撞上旧断言"是同族，但方向相反——
  前两者问"红够不够"，本条问"红是不是必然"。
- **形状错传按机制点名，但返回值口径一字不动**。`cost_analysis` 要 `{"models": …}` 包装体，
  改前三条形状通道静默塌成空表 ⇒ 把**其实已登记**的模型列进 `missing_models`，报告据"价目未登记"
  的口径让人去补一份本来就补好了的价目表（AB-11 归因错位）。现三条通道各印一条 WARN 且都点名
  "这是形状问题，不是'价目未登记'"；`{}` 与 `{"models": {}}` 保持静默——空对象没有形状可说，
  "真的没登记"与"传错了形状"才分得开。

**覆盖率读数这轮换了性质**：AB-8…AB-13 连续五轮 `src/` 零改动，同值只能按 §14 当观测；
本轮 `src/budget/pricing.py` 首次被改（+20 语句 / +12 弧），实测 18371 → **18391** 行、
6606 → **6618** 弧（新增部分 100% 被锁执行，未覆盖行数 **525** 与偏弧 **438** 均逐位不变）。
§14 的口径反过来同样成立：**读数变化也不是缺陷的证据**，佐证一律是改动面文件清单。

**引用纪律**：不得据本节引用"全仓币种口径已统一"——`oracle_examples_replay.py:581` 的
`render_readme` 把"无法估算"直接印成 **`$None`**（实测：未登记模型与 CNY 模型都落 `$None`，
而真零消费落 `$0.0`，两者共用同一个美元前缀、没有任何机制归因行），
`spec_examples_generator` 的 `{"models": <真值非对象>}` 崩溃通道（实测 `[]` / `null` / 键缺席
静默返回 `None`，只有 `'abc'` / `5` 抛 `AttributeError`，落点 `spec_examples_generator.py:337`）
本轮**实测坐实但登记不修**，见 CURRENCY_SINGLE_SOURCE_AB14_2026-10-20（分册已删除） §5；
**本节的这两句在初稿里写错过两处**（函数名 `oracle_examples_replay.compute_cost_usd` 全仓 0 命中，
以及"`models` 非对象一律崩"），均在收口前由 `/tmp/ab15_probe.py` 复算推翻并就地更正——
**登记"未处置站点"本身也要带可复算的函数名与形状清单**，散文式记忆不是证据；
不得引用"入库统计报告已可逐位复现"——`statistical_report_e2.md` / `_e2_iter.md` 与现码输出分别差
**86 / 88 行**，且该差值在本轮改前改后完全相同（陈旧于本轮之前，成因是 S11 与 BH-FDR 节晚于生成）。

## 18. 附：AB-15 轮（2026-10-20）拒绝不是一种读数 — 被拒绝的金额不得披着金额的形状，归因必须是判定的另一半

AB-14 把"这笔钱是不是美元"的判定收成一遍，但**判定收口不等于下游的呈现与归因也收口**。
本轮前置实测坐实三条通道，它们都不是"判错"，而是**判对之后又在下游把拒绝改写成了金额形状**：

- `oracle_examples_replay.render_readme` 对 `estimated_cost_usd=None` 无条件加 `$` ⇒ 未登记模型与
  该 CNY 计价模型都印 `**$None**`，真零消费印 `**$0.0**`——两者共用同一个美元前缀，
  且没有一行说清是哪条机制；
- `analyze_t1_b2_main_batch` 的池化用 `cost += st["cost_usd"] or 0.0`，把逐 seed 层已经写对的
  `None` 又折回 `0.0` ⇒ "整臂没能计价"与"确实没花钱"在报告里同形，token 数一字不变；
- `emse_stats_extensions._cost_per_task` 是 AB-14 漏掉的**第六处**币种盲点：它读单价却从不读
  `currency`，把真表模型改标 `CNY` 后 `usd_per_task` 逐位不变（实测 `0.025884977011494247`）。

**判据（本轮新立三条）**：

- **拒绝要有拒绝的形状**。`None` 不得落 `$`、不得折成 `0.0`、部分和不得冒充全额：
  `oracle` 渲染 `**无法估算（<机制>）**`，批次/ext 在任一份额被拒时返回 `None` 而不是"其余份额之和"，
  只有真实数字才保留历史金额形状（`0.0` 仍是 `$0.0`）。"无法估算"与"确实没花钱"是两件事，
  报告必须让它们不同形；拿不到原因时写"机制未记录"，不猜一个。
- **归因必须是判定的另一半，不是另一段代码**。判"算不算得出钱"与答"为什么算不出"共用
  `spec_examples_generator._price_admission`；跨站点的机制名共用
  `src/budget/pricing.currency_block_reason` 与 `CURRENCY_UNDETERMINED_STATUSES`。
  改前三处各抄一套词汇（report 的 if/elif、`statistical_analysis` 的桶名、oracle 干脆没有归因），
  同一笔拒绝在两份报告里点名不同——这与 AB-11 的"归因塌缩"同族，只是方向相反：
  前者是**多个事实挤进一个桶**，这里是**一个事实被拆成多套名字**。
- **单源判定不会自动重连所有消费者，消费者清单要按行为枚举**。AB-14 用 `currency` 的
  grep/清单找站点，漏掉了"读价目但从不读币种"的 `_cost_per_task`——它不含 `currency` 字样，
  因此任何按关键字列站点的方法都看不见它。本轮的探针按**行为**枚举：改价目表里的币种，
  看哪个下游读数逐位不变。判据：**"判定只写一遍"的完成标准是"所有消费者都接过去"，
  而消费者的证据只能是行为探针，不是 grep 命中数**。
- **披露键只在真拒绝时写入**，因此真批次载荷逐字节不变；受保护工件（P-1 README、
  入库统计报告）不重写。改前/改后对入库报告的差异仍是既有的 86 / 88 行，只复算不重写。
- 变异验证沿用既有纪律：27 处锚点逐处转红、collected 恒 109、中性对照 0 红、
  写盘前 `compile()`、跑后原字节还原并核对 sha256。覆盖率读数本轮 +12 行 / +8 弧，
  但按 §14，**变化与不变都不作佐证**，佐证是改动面文件清单（`src/budget/pricing.py` 新增
  机制词汇，六个实验侧文件接线）。

**引用纪律**：不得据本节引用"所有成本拒绝都已如实呈现"——spec 的真值非对象 `models` 仍抛
`AttributeError`（`spec_examples_generator.py:335`），三站点的价目数字域仍不一致（`True` /
`"1.0"` / 负价 / list 各有不同结局），report 的 `total_usd` 与 ext 的未登记模型仍会给出部分和，
`statistical_analysis.py:1333` 仍留 `（缺: ）` 空归因；十项边界与复算命令见
COST_REJECTION_RENDERING_AB15_2026-10-20（分册已删除） §5 / §7。

## 19. 附：AB-16 轮（2026-10-20）准入域一处写一遍 — "能不能 `float()`" 不是"这张条目能不能计价"

AB-13 收"能不能计价"、AB-14 收"这笔钱是不是美元"、AB-15 收"拒绝的呈现与归因"，但三者共同的
上游——**"什么算一个价格数字、什么算一张合格条目"——在仓内写了五套**（生产路径、spec、report、
ext、analyze + statistical 的只读版）。前置普查的读数不是"某处判错"，而是**同一张条目在每处得到
不同结论，且各处的账面都正常**：

- 数字域：`float()` 直收让 `True → 3.0`（`bool` 是 `int` 的子类）、`"1.0" → 3.0`、
  `-1.0 → 1.0`（编出负数金额）、`[1.0]` 抛 `TypeError`（是崩溃，不是拒绝）、`nan` / `inf` 累成
  非有限金额；生产路径的 `_as_non_negative_float` 也收下 `nan`/`inf`（`inf < 0` 为假）
  ⇒ 实测记账 `(nan, "price_table:m")`；
- 形状域：同一条目 `5` 在 spec/ext/analyze 读 `currency_unreachable:int`、在 report 读
  `entry_not_object:int`；空条目 `{}` 在 spec/report 读 `entry_empty`、在 analyze 读
  `currency_absent`、在 ext 折成 0.0 部分和——**四处四种结论**；
- 只读侧：`statistical_analysis._model_is_priced` 自写 `isinstance + p >= 0`，`inf >= 0` 为真
  ⇒ 非有限价在配对检验里被当作"已计价"。

**判据（本轮新立三条）**：

- **准入判定的返回值是机制名，不是布尔**。"能不能用"与"为什么不能用"必须是同一个函数的同一次
  判定：`price_block_reason`（缺席 > 类型 > 负数 > 非有限）与 `entry_block_reason`
  （形状 → 空 → 币种 → 数字）收在 `src/budget/pricing.py`，六处消费点只负责计数与格式化。
  检验形式是**同一输入、各站点同一机制名**；站点间允许的差异只剩"拒绝之后怎么呈现"
  （AB-14 已立的规则）。
- **机制名必须描述事实，而不是描述检查路径**。`bool` 单列一档（它是 `int` 的子类，不是数字）；
  `-inf` 落 `price_negative` 而不是非有限——它确实小于零（AB-15b 的既有码逐条保持）；
  `nan` / `+inf` 才是本轮新收的 `price_not_finite:*`。优先级顺序本身也是事实：`{}` 是
  "什么都没有"，比"没写单位"更准确，故 `entry_empty` 先于 `currency_absent`。
- **"一处写一遍"的完成标准再次是"消费者全部接线 + 本地词汇删除"**（§18 已立；本轮的价值是它
  第二次以行为枚举而非关键字命中来执行）：六处消费点由接线锁执行（源码禁本地实现），删掉
  `_as_non_negative_float` 与 `_price_reject_reason` 两处本地词汇；`spec_examples_generator`
  把真值非对象 `models` 从抛 `AttributeError` 改为点名 `models_not_object:<T>`——**崩溃改点名的
  前提是点名有消费面**（同一公共入口 `price_block_reason_for` 读得到，由锁执行），否则只是把
  一种静默换成另一种。
- **"改判定而读数不动"需要可复算前提，不是愿望**：真表审计（批次唯一用到的 deepseek-flash 登记
  USD `0.3/1.2`；另两条条目为价 `null` 与 CNY 计价，均已随 2026-10-23 清理删除）⇒ 收紧数字域后池化
  `1.447277 / 0.260967 / 0.541408`、总额 `2.249652` 与 ext 三臂读数逐位不变，由锁执行。
- 变异验证沿用既有纪律：21 处锚点逐处转红（红例数
  `7/12/13/21/1/29/8/6/5/1/10/3/12/11/1/11/10/10/9/3/12`），collected 恒 148、中性对照 2 处 0 红、
  写盘前 `compile()`、跑后原字节还原并核对 sha256。覆盖率读数本轮 +16 行 / +12 弧，按 §14
  **变化与不变都不作佐证**，佐证是改动面文件清单（`src/budget/pricing.py` 新增两谓词，
  六个实验侧文件接线）。

**引用纪律**：不得据本节引用"准入域已完全统一"——十一项边界只登记不修：spec 假值非对象
`models` 仍读 `model_unregistered`、`run_b8_injection.py:675` 仍自持数字门（`bool`/`nan`/`inf`/
负价收下、币种原样抄进 `price_meta`）、ext 的 `_load(PRICE_TABLE)["models"]` 缺键仍 KeyError、
report/spec 条目值 `null` 仍并"未登记"、statistical 的 `missing_models` 桶未分档、
`price_block_reason` 拒 `Decimal` 等真数、ext 未登记模型仍 0.0 部分和、
`tests/test_ae_batch.py:125` 测试侧仍缺省美元、`load_price_table()` 仍静默过滤非 dict 条目、
P-1 归档 README 非渲染器产物、`statistical_report_e2*.md` 的 86 / 88 行陈旧差值未复算；
逐项边界与复算命令见 PRICE_ADMISSION_AB16_2026-10-20（分册已删除） §5 / §7。

## 20. 附：AB-17 轮（2026-10-20）表级读侧准入一处写一遍 — "读得动 JSON" 不是"这是一张表"

AB-13 收"能不能计价"、AB-14 收"是不是美元"、AB-15 收"拒绝的呈现与归因"、AB-16 收
"什么算一张合格条目"，但四者共同的上游——**"这个文件读出来算不算一张表"（文件 → `models`
层）——在七个读点各写一套**（缓存包装、spec、report、ext、statistical、analyze、run_b8）。
前置普查（五消费方 × 14 变体）的读数不是"某处判错"，而是**同一份坏表在每处得到不同记法、
且各处的账面都正常**：

- `src` 缓存包装：顶层 list / null / 空对象 / 缺键 / models 为 list·str·null 七种不同坏
  全读同一句「结构不符（缺 models dict）」——**"键在、值为 `null`"与"根本没有这张表"并写**；
- `ext`：七种坏**全部直接崩**（FileNotFoundError / JSONDecodeError / TypeError ×2 /
  KeyError ×2 / AttributeError ×3），是七处里唯一连空表降级都没有的；
- `report`：六个互不相同的中文短语只在 stderr，归因全落 `model_unregistered`——
  "文件不在"被读成"模型没登记"；
- `spec`：文件级只进日志、`models` 层 pass-through 原样交出；
- `statistical`：文件路径全程无痕、参数路径另一套短语——**同一种坏，两条路径两种读法**；
- `run_b8`：`is_file()` 前置守卫静默退回内置价，报告读起来与"根本没给价目表"同形；
- 检索层：`.get(model)` 的 `is None` 让"键缺席"与"值 null"共用一句 `model_unregistered`。

**判据（本轮新立四条）**：

- **文件级失败按事实分族，不按"哪一段代码拦到了"**：`table_read_reason` 只回答三种事实——
  `FileNotFoundError` → `price_table_file_missing`（文件不在）；`ValueError` 族（含
  `JSONDecodeError` 与 `UnicodeDecodeError`，两者都是"这份内容不是那张表"）→
  `price_table_json_invalid:<T>`；其余（`IsADirectoryError` / `PermissionError` 等）→
  `price_table_file_unreadable:<T>`。改前七处各拦不同异常集（report 拦三类、spec 只拦
  `OSError`/`JSONDecodeError`、两个 CLI 干脆不拦）⇒ 同一份坏文件得到崩溃/静默两种结局。
- **`(None, None)` 是合法读数**：文件内容就是 `null` 时，"读到了东西"与"没读到"必须由
  reason 承担——调用方不得用 `data is None` 判读取失败（AB-12e 同型判据的再一例）。
- **空对象没有形状可说**：`{}` 与 `{"models": {}}` 在任何读点零留痕、读出"真的没登记"
  （沿用 statistical AB-14 已注册口径）；非空对象缺键是 `models_key_absent`（键缺席 ≠
  值为 `null`，AB-11 判据在容器层的再一例）；键在值非对象**真假一律**
  `models_not_object:<T>`——改前假值（`[]` / `null`）被 `or {}` 折进"未登记"桶。
- **过滤即静默丢事实**：`isinstance(v, dict)` 过滤让非对象条目无声消失，读起来与"没登记"
  同形；现原样交出、由下游 `entry_block_reason` 点名（复用 AB-16 立的词汇）。
- **"谁做的判定谁点名"——判定可以分层，点名必须同源**：spec 加载器对 `models` 层
  pass-through（文件级失败在加载器点名，`models` 层形状在消费点点名，两处读出同一个码）；
  ext 的 `_load` 自持 `is_file()` 守卫（目录被它的读取器读成"缺失"，其余六个读点读
  `price_table_file_unreadable:IsADirectoryError`）。两处是**设计性读法差异，记录在案并由
  锁锁定**，而不是硬统一成一种——统一会改变既有读取器的语义。
- **"改判定而读数不动"需要可复算前提**：run_b8 的 `table_reason` 披露键只在表真不可用时
  写入 ⇒ 真表聚合的 `price` 元数据与受保护目录既有 `REPORT.json` 的 `price` **逐字段
  相等**（聚合一律在 tmp 副本上跑，绝不改写真实目录）；池化 `1.447277 / 0.260967 /
  0.541408`、总额 `2.249652` 与 ext 三臂 `$/task` 逐位不变，由锁执行。
- 变异验证沿用既有纪律：8 处锚点逐处转红（红例数 `14/7/5/1/1/3/1/4`，M1 形状假值回静默 /
  M2 删文件缺席分支 / M3 收窄 JSON 异常捕获 / M4·M5 缺席-null 并回 / M6 统计侧形状披露静默 /
  M7 run_b8 恢复 `is_file()` 守卫 / M8 空对象改点名），collected 恒 484、写盘前 `compile()`、
  跑后原字节还原并核对 sha256（**绝不用** `git checkout` / `git stash`）。覆盖率读数本轮
  +20 行 / +15 弧（18419/18944 → 18439/18963、6638/7076 → 6653/7090），未覆盖行 524 =
  525 − 1、偏弧 437 = 438 − 1（差额由 pricing.py 一项对账：141 语句 2 未覆盖〔397–398
  `invalid_usage` 早退存量〕、66 弧 0 偏弧；其余文件合计净差 0，未逐个复算）；按 §14
  **变化与不变都不作佐证**，佐证是改动面文件清单（`src/budget/pricing.py` 新增四助手，
  六处实验侧读点接线）。收口确认跑 10283 passed / 5 skipped / 0 failed、185.04s、rc=0，
  `coverage.xml` 复算两次同值。

**引用纪律**：不得据本节引用"价目表读取已全仓统一"——九项边界只登记不修：statistical 桶级
词汇 `missing_models` 未分档、`run_b8_injection` 仍自持数字门（`bool`/`nan`/`inf`/负价收下）、
ext `_load` `is_file()` 守卫的两套目录机制码（设计性）、spec 加载器 models 层 pass-through
（设计性）、ext 未登记模型仍 0.0 部分和、`price_block_reason` 拒 `Decimal` 等真数、
`tests/test_ae_batch.py:125` 测试侧兜底、P-1 归档 README 非渲染器产物、
`statistical_report_e2*.md` 的 86 / 88 行陈旧差值未消除；逐项边界与复算命令见
TABLE_ADMISSION_AB17_2026-10-20（分册已删除） §5 / §7。

## 21. 附：AC 轮（2026-10-20）"1 − cdf" 不是 p 值 — 尾部浮点精度与"报告数字无法从生产路径复算"

Z 轮（F01）把 BH q 改成标准算法并全量重算引用值，收口报告与 pooled 勘误节引用
plain_llm_df vs plain_llm 的"原始 p = 5.890715e-26、标准 q = 1.767215e-25"。
AC 轮独立复算（只读原始 JSON + scipy，不 import 项目统计代码）发现：**这两个数字
当时无法从生产代码路径复算**——`mcnemar_test` 以 `1.0 - chi2.cdf(x, df=1)` 计算 p，
而 float64 相对 1 的机器精度约 2.2e-16，`1.0 - cdf` 在 p ≲ 6e-17（χ² ≳ 71）时
**恒等于 1.0 → p 静默变为精确 0.0**（实测 χ²=111.00885 旧路径 p=0.0、BH q=0.0）。
Z 轮回归锁（`test_review_20261019_stats.py`）锁的是精确值，但走的是测试内
`math.erfc(√(χ²/2))` 助手——生产 `mcnemar_test` 从未在主批数据上被执行。
这是"逻辑有测试、接线无测试"（A06/A07/A09/A10 同型盲区）在数值层的又一例：
**锁锁住了助手的正确性，没锁住生产路径会返回什么**。

**判据（本轮新立三条）**：

- **尾部 p 值用生存函数，不用补集**：`p = chi2.sf(x, df=1)`（df=1 时等价于
  `erfc(√(x/2))`，纯 math 亦可）。凡"1 − CDF"模式在 p < ~1e-16 时必然下溢为 0.0——
  静默的 0.0 与真实的 0.0（p 恰为 0 不可能，但 q 公式会把它算成 0）在账面上
  同形，且都渲染成 `0.0000 (\*\*\*)`。本仓另一处 `1.0 - _normal_cdf(z)`
  （`emse_testlevel_detection.py` 的 `p_normal_approx`）同模式，但该字段
  `round(..., 4)` 显示且主口径是精确 DP 枚举 ⇒ 登记不修。
  **勘误（2026-10-20 AD 轮）**：该"登记不修"已被 AD-2 撤销——
  `emse_testlevel_detection._normal_cdf` 已删除，改 erfc 生存函数
  `_normal_sf(z)=0.5·erfc(z/√2)`（可显示区间读数逐位不变，改动消除的是
  下溢模式本身），见 §22；
- **测试里的"真值"必须经过生产入口**：复算链的真值可以独立实现（erfc / 暴力
  参考），但至少要有一条断言把生产函数本身在该数据上的返回值钉住——否则
  "报告引用的数字"与"代码会算出的数字"会在无人察觉时分叉。
- **`pytest.approx` 的默认 `abs=1e-12` 会让 0.0 冒充小数**：对 1e-25 量级的
  真值，`approx(x, rel=1e-5)` 因默认绝对容差 1e-12 会让"下溢的 0.0"**通过**。
  小量级断言一律 `abs=0.0`（纯相对比较）；这是 AC 轮回归锁第一版变异验证
  "生产真值用例不转红"的根因。

**影响面实测**：χ²≤48.79 的两行 detection 比较与全部 repair 比较不受影响
（1−cdf 与 sf 在 p≥1e-14 区间相对误差 <1e-12）；canonical `statistical_report.md`
的 passed 表 χ²=123.1419 行同款下溢（p 0.0000 → 精确 ≈1.4e-28），因渲染格式
`{:.4f}` 报告显示与结论不变——**p 值量级的显示精度**（`{:.4f}` 把 1e-28 印成
0.0000）当时留待后续轮次；该显示精度已由 AD-1（`_fmt_stat_num` 非零小量级改
`{:.2e}`）处置，见 §22。

## 22. 附：AD 轮（2026-10-20）"0.0000" 不是量级 — 渲染层的精度丢失与同族模式普查

AC-1 修的是"算错的 p"（`1−cdf` 下溢为 0.0）；AD 轮顺着同一条缺陷类做两件事：
处置渲染层的同款丢失，并把模式普查做全。

**AD-1（渲染层）**：`_fmt_stat_num` 的 `{:.4f}` 把 |v| < 5e-5 的非零值一律印成
"0.0000"。这意味着即使 p 值算对了，**读者也无法从账面区分"精确的极小值"与
"精度丢失"**——AC-1 修复前 p=5.890715e-26 与真实的 0.0 在报告里同形
（都显示 "0.0000 (\*\*\*)"）。现非零且 |v| < 1e-4 → `{:.2e}`；精确 0.0 仍印
"0.0000"（零是合法统计值：χ²=0 / 无不一致对 / 无成本）。判据：
**渲染格式不得销毁量级；"显示成 0"与"就是 0"必须可区分**。

**AD-2（同族补集模式）**：`emse_testlevel_detection` 的 `1.0 - _normal_cdf(z)`
与 AC-1 同型（z ≳ 8.2 时 `1.0 - cdf` 静默变 0.0），改 erfc 生存函数
`0.5·erfc(z/√2)`。该字段 `round(..., 4)` 显示、无数字消费者，可显示区间读数
逐位不变——**改的是模式，不是读数**。

**普查结论（四类模式逐点判定）**：补集 `1−prod`（pass@k，下溢时真值即 1.0
到机器精度）、乘积 `p·(1−p)`（Wilson，非补集）、除法 `(po−pe)/(1−pe)`
（Cohen's κ，pe≥1 有守卫）、`exp(log 差)`（BF10，下溢到 0 是 intended 语义）、
`inv_cdf(1−α/2)`（α 常量不接近 1）、协议 0/1 值浮点相等（生产者只写字面量
1.0/0.0/None，全仓一致习语）、两遍法方差（数值稳定）——均良性，不动作。
**教训的形状**：一个缺陷类抓到一处后，值得把同族模式普查完再收轮；
"良性"判定也要逐点给证据（读生产者/读值域/读守卫），不凭模式名推断。

## 23. 附：AE 轮（2026-10-20）"分析层的准入域"与"登记数字的口径"

AB-16/AB-17 把价目的条目级与表级准入收进 `src.budget.pricing` 之后，AE 轮的前置普查
仍找到两类"域不在共享事实源里"的点位，以及一条关于**登记数字**的方法学。

**① 测试侧的域也是域。** `tests/test_ae_batch.py` 的价目 schema 断言自持一套比生产**更宽**的域：
`entry.get("currency", "USD")` 给币种缺席造缺省美元（生产 `currency_status` 读 `absent`），
`isinstance(value, (int, float)) and value >= 0` 放行 `inf`（生产 `price_block_reason` 读
`price_not_finite:inf`）。后果不是"测试写得不够好"：删掉真表 `deepseek-flash` 条目的
`currency` 键后该断言仍绿，而生产主批 `priced` 由 3/4 降到 0/4——**测试的防护力与它声称的
口径脱节**。判据：任何校验"数据合格"的断言都应调用生产谓词，不得重新实现一个更宽的版本。

**② 拒绝路径"不产生金额"不是全仓规则。** `run_b8_injection.aggregate` 的成本列是
"标准价上界"口径（表级失败同样兜底内置价，AB-17 锁定），故条目级拒绝也按内置价兜底
并披露——这与 AB-15"被拒绝的金额不得披着金额的形状"不矛盾：兜底数字是**另一个来源的
上界估计**、不是被拒绝的那个价，且必须由 `entry_reason` + 渲染层披露行承担归因。
判据：先确定该字段的口径（实际上界 / 实测金额 / 不产生），再决定拒绝时是 `None`
还是"带披露的兜底值"。

**③ 登记数字的口径会随渲染变化。** AB-15/AB-16 登记的"入库 e2 报告差 86 / 88 行"在
AD-1 把 p/q 渲染从 `0.0000` 改成科学计数法后变为 **94 / 100**（canonical 110 → 122）。
归因对拍：仅把 `_fmt_stat_num` 回退为旧渲染即可逐位回到 86 / 88 / 110 ⇒ 差值未消除，
只是同样几处单元格换了写法。判据：**登记"差值 N 行"时必须同时登记度量口径与复算方式**；
渲染层一改，登记数字要跟着改，不能把"数字变大"误读成"报告质量下降"。

另：本轮拒绝路径的机制码来自共享谓词（`model_unregistered` 由调用点补），
故"没登记"与"登记了但读不出"仍分得开——这是 AB-11 判据在分析层的最后一次接线。

## 24. 附：AF 轮（2026-10-20）文本里出现 "NaN" 不是"工件含裸 NaN" — grep 计数不是严格解析，写入口的两层判据

AE §5.6 记「`experiments/results/` 下 68 份 JSON 在文本中含裸 `NaN` / `Nan` / `Infinity`
token」，据此宣称"全仓存在非 RFC-8259 工件"。AF 复测把这句话拆成两个不同的命题：

**① grep 计数测的是"文本里出现这个字符串"，严格解析测的是"这个 token 是否作为值出现"。**
用 `json.loads(..., parse_constant=拒绝)` 解析全部 7273 份受控工件，**违规 0 份**；那 68/69
份文件里命中的字样全在**字符串值内部**（测试名 `test_sqrt_positive_infinity`、诊断文本
"x 为 NaN"），是合法 JSON 文本。判据：**任何"工件不合格"的主张必须由解析器给出，
不能由 grep 给出**；同理，"字符串里含 NaN 字样"不构成需要清洗的数据语义缺陷。

**② 真正成立的缺口在写入口，而不在存量工件。** `json.dumps` 默认 `allow_nan=True`，
`nan`/`±inf` 会被写成裸 `NaN`/`Infinity`：Python 自己的 `json.loads` 能读回，jq / Go /
Rust serde / JS `JSON.parse` 拒绝——**生产端静默写出、消费端读不动**，中间没有失败信号。
处置不是全仓清洗，而是把边界钉在写入口，且判据分两层：

- **调用点层**：所有文件写入点的 `json.dump(s)` 必须显式 `allow_nan=False`（门禁做 AST
  扫描：`json.dump` 与处于 `write`/`writelines`/`write_text`/`atomic_write_text`/
  `stdout.write` 实参链内的 `json.dumps`）——本轮 39 份源码 41 个直写点补齐；
- **序列化器层**：中心写盘路径统一走 `strict_json_dumps`（先递归定位非有限值并抛
  `NonFiniteJSONError`，带 JSON 路径），`allow_nan=False` 只作第二道防线。

**③ 失败语义要按"这一笔写的是什么"分别决定，不能一律抛错也不能一律丢弃。**
`atomic_write_json` 的失败必须发生在临时文件创建之前（旧目标不被触碰）；
`run_b8._write_json` 与 `_Injection._record` 直接失败（记录含非有限值即上游缺陷）；
`trace` 是旁路观测层，保持"少记不误记"——坏记录整条丢弃并告警，**文件本身仍逐行严格
可解析**。判据：严格化不是"到处 raise"，而是让每个写入点在其既有语义下不可能写出坏行。

**④ 豁免面必须带漂移检测。** 2 份 A20 历史截断轨迹是非严格 JSONL 且受保护不可重写，
按**逐路径**豁免登记；门禁同时断言"豁免文件一旦变得严格可解析就报红"——否则豁免会
悄悄扩大成永久漏洞。空扫描集合（没扫到工件 / 没扫到源码）直接失败，防止门禁空转。

**⑤ 自捕获登记：本轮新引入的真实缺陷被既有门禁当场抓住。** CI 步骤 `name` 写成
`Check strict JSON (AF: ...)`，冒号后空格未加引号 → YAML `ScannerError`，`test_ci_yaml_parses`
在登记前一跑即转红；加引号后转绿。判据：**新增 CI 步骤必须跑一次全量确认**，
"文件已写入"不等于"工作流可解析"。

## 25. 附：AG 轮（2026-10-20）"未登记"不是"未计价" — 桶名不是分类，提示语必须与判定同源

AB 系列已经把"是不是美元"（AB-14）、"拒绝怎么呈现与归因"（AB-15）、"什么算合格条目"
（AB-16）、"什么算一张表"（AB-17）各自收成一条判据，但下游的**桶**仍在合并不同事实：
`statistical_analysis.cost_analysis` 把"表里没这个键""价目域不合格""条目形状坏"一起
放进 `missing_models`，把形状码放进名为"币种"的桶；全未计价时无条件教读者去补
`input_per_mtok` / `output_per_mtok`——**按提示补完仍然不可计价**。AG 的判据是：

**① 归因是判定的另一半，必须由同一个谓词产出。** 桶的划分不能再由消费点各写一套
if/elif；`cost_analysis` 的机制索引直接调用 `pricing.model_entry_reason`（键缺席 →
`model_unregistered`，其余交 `entry_block_reason`），站点只负责计数与格式化。
判据：**同一个拒绝在两张报告里点名不同的机制，是缺陷而不是措辞差异。**

**② 桶名必须与桶内事实一一对应。** `missing_models` 只留真键缺席；AB-14 的币种词汇
只进 `unpriced_currency_models`；其余（形状 / 价目域 / 行级）进 `unpriced_model_reasons`
或 `unpriced_row_reason`。三个桶互斥且并集覆盖索引——有锁断言分区关系，而不是
"看起来分开了"。判据：**桶可以少，但不能名不副实；改名就是改口径，必须登记。**

**③ 提示语是接口。** 全未计价早退分支不再统一说"补价目字段"：价目域问题说价目域，
形状问题说形状，币种问题说币种，行级混算说行级；纯未登记 / 无 token 观测保持
旧四行逐字不变。判据：**读者按报告提示操作后仍不可计价，就是报告在说谎。**

**④ "0 行改变"是实测，不是性质。** 真批次 522 行只用 `deepseek-flash`（USD 已登记），
非 USD / 坏形状 / 坏价目在盘上 0 实例，所以本轮对受保护报告的输出改变 0 行；
换模型或换价目表就会走到新分桶。判据：**不得把"当前工件 0 命中"读成"该机制不存在"。**

**⑤ 只增不改的返回域需要引用纪律。** 披露键只在真发生时写入：键缺席 = "当时没有
该机制实例"，不是"该机制不存在"；对外引用"哪些模型没计价"必须读
`unpriced_model_reasons`，不能继续读已收窄的 `missing_models`。判据：**键的缺席与
键值为空是两种事实，契约写在锁里，不在读者记忆里。**

## 26. 附：AH 轮（2026-10-20）"不完整的和"不是金额 — 分母、覆盖与归因闭合，缺一项就没有 $/task

AG 把"为什么没金额"的**归因**收成一条判据；AH 收的是同一判据在**金额本身**上的前提：
`emse_stats_extensions._cost_per_task` 只问了"这个模型在不在价目表里"，没问"这个和是不是完整"。
于是四种"不完整"都得到金额形状：价目缺模型时的部分和、`by_model` 缺席却 `tok>0`、`by_model`
合计 ≠ `total_tokens`、零任务分母返回 `0.0`。判据有三条：

**① 一个 `$/task` 数字成立的前提是三个闭合条件同时成立**：价目覆盖 `by_model` 的**全部**
token、`by_model` 合计 = `total_tokens`、`n_tasks > 0`。缺任一项，正确读数是"没有金额"，
不是"金额为零"；部分和冒充全额与 AB-15 的"拒绝披着金额形状"同型。判据：**分母不成立时，
任何数字都是编造。**

**② "没有金额"必须点名是哪一项不闭合。** 未登记 → `model_unregistered←<sorted models>`；
`tok>0` 但 `by_model` 缺席/空 → `no_model_attribution`；合计不等 →
`token_attribution_mismatch:<by_model合计>/<total_tokens>`；零分母 → `无任务 ⇒ $/task 无金额（不是 0）`。
四条与 AB-15 的 `计价被拒：<code>←<models>` 并存，互不吞并。判据：**机制名是读数的单位，
不是附注。**

**③ `0.0` 只有一种合法来源：确实没有 token 可少算**（`tok == 0`）。此时 0 是真实读数；
零任务不等于"没花钱"，它是"每任务"这个比率没有定义域。判据：**零分子与零分母不能共用一个 0。**

**④ 真批次 0 行改变是实测，不是性质。** 三臂 `by_model` 合计恰好 = `total_tokens`
（6815977 / 837664 / 1102230，delta 0），所以受保护读数逐位不变；换批次或换归因生产者
就可能走到新机制，不得把"当前 0 实例"读成"这条路径不存在"。判据同 AG ④。

**⑤ 变异纪律照旧**：6/6 行为锚点转红（红 1/2/3/10/2/10），注释型中性对照 0 红，
collected 恒 298，写盘前 `compile()`、sha256 原字节还原。判据：**"有红"不等于"有锁"，
"0 红"也不等于"冗余"——两者都要有对照与收集数守卫。**

## 27. 附：AI 轮（2026-10-21）"不完整的 token 和"不是 token 读数 — 值域、缺席与形状，缺一项就没有 tokens/task

AH 判的是**金额**的和是否完整；AI 判的是**和本身**：`emse_stats_extensions` 读入侧仍是
`sum += value or 0`，同一个 `token_usage` 在 `_cost_per_task` 与 `_bootstrap_cost_ci`
各读一遍，坏值一边崩溃、一边把 `inf`/`nan` 带进 CI。判据如下：

**① 一行 token 记账成立的前提是三个非负整数**（`total_tokens` / `input_tokens` /
`output_tokens`）。`token_usage` 缺席、为 `null`、为空对象、缺字段、非对象，或字段是
bool / 小数 / 字符串 / 负数 / 非有限，正确读数都是"没有 token 读数"（`None`），
不是 `0`，也不是部分和。判据：**分母在而分子被吞，读出的 0 是编造。**

**② 两级读数不同步是设计，不是矛盾。** 整臂值域问题（`value_reasons`）同时废
`tokens/task` 与 `$/task`；行级 `in+out ≠ total_tokens` 与 `by_model` 形状/键/值域问题
只废金额——`total_tokens` 本身仍是可读的计数。判据：**"金额不可用"不蕴含"token 强度
不可用"，反之亦然；引用时必须说清是哪一级。**

**③ 提示语必须指向真缺陷**（AG 纪律的延伸）：`by_model` 在场但读不动时，若同时报
`no_model_attribution`，读者按提示去补 `by_model` 也不会变绿。只有真的没有 `by_model`
（键缺席 / 空对象）才报无归因。判据：**提示语与判定同源；读者照做后仍不成立，
就是提示在说谎。**

**④ 真零与缺席是两种事实。** 三个显式 0 是真实读数（`tokens/task=0.0`，`tok==0` 时
金额 0.0 也可成立）；`token_usage: {}` 是三个字段都没记录，整臂无读数。
判据：**"没写"不得经 `or {}` / `or 0` 翻译成"写了零"。**

**⑤ 真批次 0 行改变是实测，不是性质。** 三臂 `token_usage` 全部合法且 `by_model`
合计闭合，所以受保护读数（tokens/task、$/task、bootstrap CI）逐位不变；换批次或换
生产者就可能走到新机制。判据同 AG ④ / AH ④：**当前 0 实例不是路径不存在的证明。**

**⑥ 变异纪律照旧**：18/18 行为锚点转红（红 4/7/11/3/2/8/3/3/3/1/6/14/2/3/3/9/4/1），
注释型中性对照 0 红，collected 恒 78，写盘前 `compile()`、sha256 原字节还原。
判据：**"有红"不等于"有锁"，"0 红"也不等于"冗余"。**

## 28. 附：AJ 轮（2026-10-21）"缓存命中"是第三种记账状态 — 不是断裂，也不是免费

AI 判的是 token 读数的**值域**；AJ 判的是真实消耗为 0 时**另一种事实**：
`record_cache_hit_usage` 只写 `cache_hits` / `cache_avoided_tokens`，不调用
`record_usage`——命中行的 `input/output/total_tokens` 为 0 是正确读数，但所有成本
读端只看见 0，于是把它读成"记账断裂"或"零 / 未计价"。判据如下：

**① 0 是真的 0，但不是免费。** 命中不产生真实 API 支出，所以 `$/task` 记 0 是对的；
`cache_avoided_tokens` 是"若未命中会消耗"的反事实计量，把它加进支出会虚构金额，
把它当 0 又会低报缓存收益。判据：**真实消耗、避免消耗、记账断裂是三种事实；
一种读数不得兼任另外两种。**

**② 缓存证据必须同时合法且正向。** `cache_hits > 0` 或
`cache_avoided_tokens > 0`（非负整数）才为"该行有记账"提供证据；
`cache_hits = -1` / `"2"` / `nan` / 半套 schema 既不算证据，也不被读成"没有缓存"，
而是按 `token_field_absent` / `token_not_count` / `token_not_finite` /
`token_negative` 点名。判据：**"读不动"不是"没有"，坏值也不得被静默折成 0。**

**③ 部分和不得冒充一臂合计。** 任一命中行的缓存字段坏 / 缺，整臂
`hits` / `avoided` 都是 `None`，机制名按行计数留在 `reasons` / `missing`；
只有 schema 在场且全部合法时才给合计。混合 schema 臂只汇总带字段的行，披露里的
`P/Q` 行数把覆盖范围写出来。判据：**一个数少算了哪些行，必须与这个数同时可读。**

**④ "没有金额"的成因必须与判定同源。** 纯缓存臂在严格六前件下才写
`cache_hit_no_api_spend`（`cost is None`、无已计价 / 未计价模型、缓存读数完整、
确有命中行、真实 in/out 为 0、无未归因 token）；避免 token 不写 `by_model`，
因此不能折算避免金额，只能披露 token。判据：**能算 token 不等于能算钱；
换算假设缺失时不给金额。**

**⑤ 旧 schema 必须逐字节不变，新 schema 必须改变读数。** 主批 / E6 / E4 没有缓存
键，返回域、note、受保护工件一字不动（三臂 ext 读数逐位相同）；三条缓存密集臂
（QuixBugs 50 行命中、ULT 20 行、examples 2 行）则从 `NOT_COMPUTABLE` / 无因
「（缺: ）」转为可计算并披露——**读数的改变本身就是本轮要交付的证据**，不是回归。
判据：**新口径只在 schema 支持的批次上生效；把新读数套到旧批次上是伪造。**

**⑥ 变异纪律照旧**：19/19 行为锚点转红（红 38/10/10/11/6/6/10/4/2/3/1/3/1/3/1/2/2/1/1），
中性对照 0 红，collected 恒 298，写盘前 `compile()`、sha256 原字节还原。
判据：**"有红"不等于"有锁"，"0 红"也不等于冗余。**

## 29. 附：AK 轮（2026-10-21）"少数无记账行"不是免费，也不是精确值 — 阈值单侧通过时成本读数是已记录下界

S11 用一个阈值回答两个问题：无记账行占比 ≥ 50% ⇒ `NOT_COMPUTABLE`，否则成本照算。
但"没有断裂"不等于"记账完整"——主批 `plain_llm_df` 35/261 行（13.4%）token 三元组
全 0、`llm_calls=0`，却都有 `generated_test`（3 行还检出成功）。这些行以 0 进入金额
分子、仍占任务分母，`$/task` 与 `$/solved` 被按精确值渲染。判据如下：

**① 阈值只挡断裂，不挡部分记账。** `computable=True` 的含义是"记账没有断裂到
无法计算"，不是"分子覆盖了所有任务"。判据：**一个布尔判定不能替代对分子覆盖面的披露。**

**② 下界与精确值同形时，必须显式声明。** 行级数学口径（缺 `token_usage` 按 0 计、
行仍进分母）是 AE2 锁定的历史口径，本轮不改；但不披露就等于把"已记录花费的下界"
当精确均值发布。判据：**同形的两个量必须靠文字标签区分，不能靠读者推断。**

**③ "有产出"必须由字段定义，不能由推断定义。** AK 只认 `generated_test` 为非空
字符串，不猜 `patch` / `diagnosis` 等修复侧字段；因此 `n_zero_output_rows` 是下界中的
下界，不得读成"所有有工作痕迹的行"。判据：**判定词的外延要写死在代码里，并登记它没覆盖什么。**

**④ 三层呈现必须同源。** 同一个事实（S11 子集、成本行口径、报告与 ext note）只有一套
计数来源；`cost_caliber` 只在成本确有数字且无记账行 >0 时写入，全记账臂与旧 schema
返回域一字不动。判据：**披露的触发条件必须与判定同源，不能"有数字就加注"。**

**⑤ 缓存行不落在下界里。** AJ 的合法缓存证据行真实 token 为 0 是正确读数，不是
记账缺失；AK 的两个计数都排除缓存证据行，纯缓存臂不会被误标"有产出无花费记录"。
判据：**同一个 0 可以有两种成因，成因不同则不得进入同一计数。**

**⑥ 两套零计数不得互证。** S11 的 `n_zero_output_rows` 收"无记账且 `generated_test`
非空"的行；ext 的 `n_zero_rows` 只收"显式三元组全 0 且无缓存证据"的行。主批 df 臂
两处同为 35，但定义不同、合成输入可不同。判据：**数值相同不等于口径相同。**

**⑦ 变异纪律照旧**：4/4 行为锚点转红（红 3/5/3/1），中性对照 0 红，collected 恒 89，
写盘前 `compile()`、sha256 原字节还原。判据：**"有红"不等于"有锁"，"0 红"也不等于冗余。**

## 30. 附：AL 轮（2026-10-21）"同一行 token 记录"不能有两个读数 — 报告侧 `or 0` 不是值域

AI 把 ext 的行级 token 值域收成"三个非负整数，缺一项就没有 tokens/task"；但
`emse_stats_report.cost_effectiveness_block` 仍在用 `usage.get("input_tokens") or 0`
自算一遍。同一行在 ext 读不动、在报告 §4.1 却被折成 0 并计价；`token_usage` 非对象
的行还在检出计数之前被 `continue`，检出分母随记账好坏缩水。判据如下：

**① 同一事实只应有一个读取器。** 值域判定写两遍就必然漂移：报告这一份更宽松，
因为 `or 0` 把"读不动"伪装成"读到了 0"。判据：**读取器归生产模块，消费点只消费判定结果。**

**② 读不动是总量级阻断，矛盾是金额级阻断。** 三元组任一字段坏 ⇒ token 总量、总 $
和两个比值全部 `None`（不给部分和）；`in+out != total`、`by_model` 缺失或合计不符 ⇒
token 总量仍可读、只撤金额。判据：**两种缺陷的可信面不同，阻断范围必须不同。**

**③ 检出分母不得随 token 可读性缩水。** 检出是 `detection_rate` 的事实，token 是
花费的事实；读不动的行仍进检出分母，`detection_rate=None` 仍不进可测分母。判据：
**一个字段的缺失不得改变另一个字段的分母。**

**④ 缓存零行不是记账缺口。** 合法且正向的缓存证据解释的真实零消耗沿用 AJ 口径，
不计入 AK 下界；缓存字段坏值 / 零命中仍是零记账行。判据：**同一个 0 的成因不同，
不得进入同一计数。**

**⑤ 披露键只在真发生时写入。** 干净臂与旧 schema 批次返回域逐键不变；AL 键的
存在性即"该类行是否存在"，不得用键缺席推断其他结论。判据：**披露面只增不改，
且触发条件与判定同源。**

**⑥ 真批次零改变不等于修复无价值。** 783 行恰好全部干净（坏拆分 / 坏归因 0 行），
所以三臂读数逐位不变；缺陷由合成行分别触发并锁住。判据：**"没触发"不是"没缺陷"，
锁定必须能构造出触发条件。**

**⑦ 变异纪律照旧**：6/6 行为锚点转红（红 3/1/15/14/8/2），中性对照 0 红，
collected 恒 57，写盘前 `compile()`、sha256 原字节还原。判据：**"有红"不等于"有锁"，
"0 红"也不等于冗余。**

## 31. 附：AM 轮（2026-10-21）"在场坏值"不是 0 — 成本表聚合的 `or 0` 折零与 false $0

AI 收口了 ext 的行级值域、AL 收口了报告 §4.1，但 `statistical_analysis.cost_analysis`
——`$/task` 与 `$/solved` 的唯一聚合口——仍用 `tu.get(...) or 0` 自算一遍。同一行
token 记录在三个消费点有三种命运：ext / 报告已"读不动 ⇒ `None` + 机制名"，成本表
却把在场坏值翻译成"读到了 0"。判据如下：

**① 缺席与在场坏值不是一回事。** 整键缺席 / `None` 沿用 AE2 的历史 0（由 AK 下界
披露）；字段在场却是 `bool` / `float` / `str` / `nan` / `inf` / 负数，是**读不动**，
必须给 `None` 并点名机制。判据：**"没有记录"与"记录坏了"进入不同分支，前者不能
被后者借道。**

**② 正 token + 缺项不得输出部分和。** `total` 为正而 input/output 缺一项时，按 0
计价会编出 `$0`（"免费"假象）；缺项不是 0，整臂 token 总量也不得给部分和。例外：
只有 `total` 缺席而 in/out 双全时，可按 `in+out` 读（成本只需拆分）。判据：
**部分和不进入任何对外读数，包括 token 总量。**

**③ 读不动是总量级阻断，矛盾是金额级阻断。** 与 AL 同一分层：读不动 ⇒ 整臂
token 总量、`by_model`、`unattributed_tokens` 与金额一律 `None`/空；`in+out≠total`、
`by_model` 键/值/求和矛盾 ⇒ token 总量仍可读、只废金额。两类事实分别写
`token_reading_reasons` 与 `token_money_reasons`。判据：**两种缺陷的可信面不同，
阻断范围必须不同，披露也不能混桶。**

**④ 零总量坏归因同样废金额。** `by_model` 声称有 token 而行内三元组为 0 时，按 0
计价会编出"免费"；报告侧（AL）零总量放行，成本表这一侧更严是有意的，分歧写进
共享谓词的调用约定。判据：**同一谓词可以有两种调用策略，但差异必须写下来，
不能靠调用点各猜一遍。**

**⑤ 同一判定只写一遍。** `by_model` 的键域 / 值域 / 求和判定迁入
`src/budget/token_usage.by_model_reason`，成本表直接调用、报告侧一行委托。判据：
**判定写两遍就必然漂移，哪怕今天字面相同。**

**⑥ S11 只认计数作证据。** `True` / `1.5` / `nan` / `inf` / 负数 / 字符串不是"有
记账"；证据值域改走 `count_reason`。阈值（50%）与 `n_without_accounting` 计数
口径不动。判据：**证据的值域与断裂的阈值是两件事，不得一起改。**

**⑦ 呈现层不得替聚合层兜底。** 读不动的单元格显示 `—`；AM 阻断臂不进"只差价目"
清单（修读取 ≠ 补价目）；标题只在 AM 键在场时改为"成本不可计算"。判据：**同一种
"没有数字"的外形，背后可能是三种成因，提示语必须与判定同源。**

**⑧ 真批次零改变不等于修复无价值。** 783 行全部 int、逐行 `in+out=total`、
`Σby_model=total`，所以三臂读数与返回域逐键不变（`identical=True`）；缺陷由合成行
分别触发并锁住。判据：**"没触发"不是"没缺陷"。**

**⑨ 变异纪律照旧**：10/10 行为锚点转红（红 19/5/5/7/1/3/2/1/2），另有 1 个中性
注释对照 0 红，collected 恒 188，写盘前 `compile()`、sha256 原字节还原。判据：
**"有红"不等于"有锁"，"0 红"也不等于冗余。**

## 32. 附：AN 轮（2026-10-21）"读不动"不是零 — 三个 token 聚合读端的部分和

AM 把行级策略收进 `row_token_reading` 之后，三个**聚合读端**仍各自用
`(r.get("token_usage") or {}).get(..., 0)` 求一遍：`run_benchmark` 的写盘
`token_metrics`、`trusted_verification` 的离线报告、`rag_analysis` 的旧 JSON 回退。
同一个坏行在三个消费点分别表现为崩溃、静默 0、负总量或矛盾读数。判据如下：

**① 聚合不是第二次读取，同一事实只能有一种读数。** AM 的行级值域迁入生产者模块
`src/budget/token_usage.row_token_reading`，聚合统一走 `aggregate_row_token_usage`；
`statistical_analysis` 只保留别名。判据：**同一行 token 记账在四个消费点有四种
命运，就是四处各自实现了一遍判定。**

**② 缺席与在场坏值分道。** 整键缺席 / `null` 沿用 AE2 历史 0，并计入
`n_absent_rows`（可披露）；字段在场却是 bool / float / str / nan / inf / 负数，
或正 token 下三元组缺项 ⇒ 三元组**全部** `None`，不给部分和。判据：**"没有记录"
可以按历史口径读 0，"记录坏了"不行——两者混同就是把坏值伪装成零。**

**③ token 总量与调用数各自判定。** 坏 `llm_calls` 只让调用数不可读，不连坐 token；
非对象行是例外（调用数同时不可读，机制码由三元组读取器给出）。判据：**可读性
按事实分，不按行打包。**

**④ 拆分矛盾只披露、不阻断 token 总量。** `in+out != total` 时总量仍可信（两个
来源都读得动，只是互相矛盾），写 `n_token_split_mismatch_rows`；聚合层没有金额，
"矛盾即不可计价"由成本侧（AM）负责。判据：**阻断范围与可信面一致，不在读端
替金额端做决定。**

**⑤ 缓存旧 schema 与半套 schema 是两种事实。** 整批没有缓存键 ⇒ `present=False`
⇒ 消费端历史 0；半套 / 坏值 / 非对象 ⇒ `hits` / `avoided` 均为 `None` 并点名机制。
判据：**"这批没记缓存"不是"缓存读数为零"，"记了一半"更不是。**

**⑥ 呈现层的分母必须是真数字。** 旧 CLI 印「命中 X / 调用 X + 真实」，分母是字面
文本而不是调用数；现在报告键带 `llm_calls`、CLI 打印真实分母。判据：**一个从未
参与除法的字符串不能出现在比值的位置。**

**⑦ 真批次零改变是实测不是性质。** 主批 783 行 / 9 臂全部 int 且自洽、缓存 schema
缺席，重算 `token_metrics` 五键逐臂逐位不变；全仓 11197 行 / 337 臂里 1218 行缺席
（按历史 0）、0 坏值 / 0 部分 / 0 矛盾。判据：**干净语料不证明未来语料干净，
只证明本轮改动对存量读数零影响。**

**⑧ 覆盖率口径不得把偏弧当已覆盖弧。** 本轮初次汇总用
`(7202−383)/7202 = 94.68%`，把 `coverage report` 的"半缺分支"计数当成已覆盖弧；
`coverage.xml` 根节点是 `branches-covered=6765` ⇒ **93.93%**。已按根节点更正，
并明确 383（偏弧）与 437（缺弧）是不同口径——偏弧下降不构成回收主张。判据：
**同一份覆盖率有多个口径时，只认与 `branches-covered/valid` 同源的那一个。**

**⑨ 变异纪律照旧**：15/15 行为锚点转红，另有 1 个中性注释对照 0 红，collected
恒 210，写盘前 `compile()`、sha256 原字节还原。判据：**"有红"不等于"有锁"，
"0 红"也不等于冗余。**

## 33. 附：AO 轮（2026-10-21）报告总量也有值域 — 档位、翻转对比、收敛曲线的三种折叠

AN 的共享读取器按成本口径要求 in/out 才能计价，**报告只展示总量**时不应复用同一
判据（旧 JSON 常见 total-only，强行复用会让合法行不可读）。但值域仍只有一个：
三个报告读端不得各自 `int(... or 0)` / `_safe_float(... or 0)`。判据如下：

**① 一个事实一种读数，两种问法两个读取器。** 成本要三元组（`row_token_reading`），
报告要总量（`row_total_token_reading`）；两者共用 `count_reason` 值域。判据：
**问法不同可以有两个入口，值域不同就会有两种真相。**

**② 总量在场且合法即可读。** `{"total_tokens": 200}` 是合法旧 schema，不因
in/out 缺席被否定；`total` 与 in/out 双全且不符只披露 `contradiction`，不阻断
（报告层没有金额可废）。判据：**能核验的拆分用于披露，不能核验的拆分不用于否定。**

**③ 聚合任一行不可读 ⇒ 总量 `None`。** 不给部分和；缺席 / `null` 仍按历史 0
并计 `n_absent_rows`。判据：**部分和会披着总量的形状进入结论，宁可没有数字。**

**④ 收敛曲线的"不可读"与"没有数据"是两件事。** 无 token 数据按历史 0 保持
`available=True`；在场读不动 ⇒ `available=False`、`rounds={}` + 机制名。判据：
**不能用 0 伪造一条曲线，也不能把"没记"当成"记坏了"。**

**⑤ 只扫描使用面。** 逐轮坏值只在曲线实际使用的 `min(iterations, 3)` 以内阻断；
未使用轮次的坏值不冒充缺陷。判据：**判定范围与消费范围一致。**

**⑥ 呈现层三种外形对应三种成因。** 「不可读」= 在场读不动，`?` = 整键缺席，
`0` = 读到零；合计不可读时**不判**性价比倒挂。判据：**提示语与判定同源，
读端不替聚合兜底。**

**⑦ 真批次零改变是实测不是性质。** 244 文件 / 322 臂 / 10659 行中
`token_usage` 只有三种形状（5315 完整三元组 / 4366 带缓存 / 978 缺席），
非对象 / 坏值 / 缺 total / 拆分不符 **0 行**，逐轮详情臂 **0**，9 臂新旧差 **0**。
判据：**干净语料只证明本轮对存量零影响，不证明未来语料干净。**

**⑧ 覆盖率自纠：新行无锁执行会被复算抓出。** 登记前一跑 18716/19241 行，
`token_usage.py:406`（`total` 缺席且在场字段坏值的机制名落账）无锁执行；补 1 例
后确认跑 18717/19241（新行与新弧全部被锁执行），未覆盖 524 / 缺弧 437 与 AN
逐位相同。判据：**"新行都覆盖了"要按 `coverage.xml` 逐行复算，不能按直觉断言。**

**⑨ 变异纪律照旧**：16/16 行为锚点转红，另有 1 个中性 docstring 对照 0 红，
collected 恒 192，写盘前 `compile()`、sha256 原字节还原。M14 首轮逃逸的根因是
**测试形状**（坏值放在 `iterations` 元素而非 `tokens` 字段），改参数后转红。
判据：**变异逃逸先怀疑测试形状，不要先怀疑锚点无效。**

## 34. 附：AP 轮（2026-10-21）聚合对象也有三种"空" — 缺席、拒绝、读到零不能共用一个 0

AO 收口了行级总量读端（`row_total_token_reading`），但写盘 `token_metrics` 的**聚合对象**
仍有五个消费端各自折叠。聚合对象里的 `None` 与行级 `token_usage` 的缺席**不是同一种空**：
前者是上游 AN/AO 已拒绝（写侧只在坏行时写 `None`），后者是历史无记账。判据如下：

**① 两种对象、三个读取器、一个值域。** 成本计价走 `row_token_reading`（要三元组），
行级报告总量走 `row_total_token_reading`（total-only 可读），聚合对象走
`token_metric_reading`（字段缺席历史 0、在场 `None` 是拒绝）。三个入口可以不同，
值域必须同源（`count_reason`）。判据：**问法可以分叉，拒绝不能分叉。**

**② 聚合 `None` 必须继续不可读。** `token_metrics["total_tokens"]=None` 是写侧对坏行的
拒绝结果，不是"没有记账"；若消费端再折 0，等于把 AN/AO 的拒绝二次吞掉。判据：
**上游已经说不，读端不得替它改口。**

**③ 不给部分和。** 逐 seed 池化 / 冒烟合计 / 多份 metrics 求和时，任一份不可读即整列
`None`，机制名与不可读份数随载荷披露；缺席份仍按历史 0 且单独计数。判据：**部分和穿着总量的形状进入结论，比没有数字更危险。**

**④ 派生均值与计数是两种值域。** `avg_tokens_per_task` 可走 `allow_float=True`
（有限非负 int/float）；`total_tokens` / `total_llm_calls` 仍只收非负 int。判据：**放宽派生的分母不等于放宽计数。**

**⑤ 统计门在进入统计库之前。** rag_ab 的任一侧 `tokens_total=None` ⇒ 均值、标准差、
差值、百分比与 Welch/Mann-Whitney/Cohen's d **全部** `None`，解读写"不可判定"；
不得把 `None` 送进 `_mean` 崩掉，也不得把 nan 当成 `p ≥ 0.05` 报"无显著差异"。
判据：**没算统计量 ≠ 统计量不显著。**

**⑥ 三种呈现外形对应三种成因。** 「不可读」= 在场读不动；`N/A` = 派生比值无法计算；
`0` = 读到零（或缺席的历史口径）。b8 成本列与 rag_ab 的迭代/耗时不受 token 门牵连。
判据：**一个门只管一种事实。**

**⑦ 干净工件零改变是实测不是性质。** t1_b2 `2629059 / 310018 / 643952`、
b8 `83246 / 113638`、rag_ab 20+20 对与主批表 `2544615 / 284317 / 404268`
逐位不变；但 `rag_ab_synthetic` / `rag_lvl25h_n40` 的报告统计量早于 2026-10-01
统计修复（如 `p_welch 0.29198` vs 复算 `0.298675`），只登记差值、不重写工件。
判据：**存量零影响不等于存量数字都对。**

**⑧ 覆盖自审按 `coverage.xml` 逐行复算。** 本轮新增 +43 行 / +28 弧全部被执行
（18760/19284 = 97.2827%、6825/7262 = 93.9824%），未覆盖 524 / 缺弧 437 与 AO
逐位相同；`budget/token_usage.py` 唯一未覆盖行仍是既有 175。判据：**"新行都覆盖"
要拿逐行读数作证，不能拿总数相等作证。**

**⑨ 变异纪律照旧**：33/33 锚点转红、0 逃逸，collected 恒 67，写盘前 `compile()`、
sha256 原字节还原。`ar-rag-avg-fold` 首轮逃逸的根因是**测试形状**（只让无 RAG 组
不可读，未覆盖 RAG 组折叠），补 RAG 组用例并反向加锚后转红。判据：**变异逃逸先
怀疑测试形状，不要先怀疑锚点无效。**

## 35. 附：AQ 轮（2026-10-21）导出边界也要值域 — 坏值不泄漏、坏时间戳不炸文件、静默丢弃要披露

报告读端收口之后，最后一个同族读端是 `src/observability/otel_export.py`：它把
`trace.jsonl` 转成 OTel span，token / 时间戳 / 数值自定义属性都直接取自记录。
导出是**系统边界**（外部 JSONL 进、OTel 结构出），不是展示层。判据如下：

**① 一个谓词管计数，一个值域管时间。** token 三元组与 iteration 复用生产者模块的
`count_reason`（非负整数；bool / 小数 / 非有限 / 字符串都不是计数）；`ts` /
`duration_s` / `duration_ms` / `budget_remaining` 是时间或金额类数值，只收有限非负
int/float；duration 的单位由字段名决定（`duration_s` 秒 / `duration_ms` 毫秒），
两者并存时 `duration_s` 优先。判据：**计数与度量可以是两种值域，但同一类事实只能有一个判定入口。**

**② 坏值不导出原值。** bool / str / 有限小数（计数字段）/ 负数 / `nan` / `inf` /
容器一律不写进 `gen_ai.usage.*`，机制名披露；一个坏字段不牵连同记录的其他干净字段。
NaN/Inf 不是合法 OTLP JSON 数值，原样导出等于把非法载荷推给下游。判据：**导出器
的职责是拒绝，不是替上游解释。**

**③ 时间戳坏值回落 0，不中止整份文件。** 改前 `int(float(nan) * 1e9)` 会抛
`ValueError`/`OverflowError`，一条坏记录让 129058 个 span 全不产出；同文件的损坏
JSONL 行却是跳过的。改后非有限 / 负 / 缩放溢出 / 巨大整数都回落既有 0 哨兵并由
披露属性点名。判据：**同类坏数据的两种命运必须收敛为一种。**

**④ 0 是"不可用"不是"有效"。** 缺席的 `ts` / `duration_s` / `duration_ms` 本来就用
0；坏值也回落 0。需要拒绝损坏 span 的消费方必须读 `aitester.export_value_reasons`，
不能只看 0。判据：**哨兵值只能表示不可用，不能表示已校验。**

**⑤ 静默丢弃要披露；历史缺席不披露。** `token_usage` 键缺席 / `null` 是历史缺席
（无属性、无披露）；非对象整键、字段在场 `None` 或坏值是读不动，必须给机制名。
判据：**"没有"与"读不动"在导出结构里也要可区分。**

**⑥ 披露有确定形状。** 机制名按 **ts → duration（`duration_s` 优先，其次
`duration_ms`）→ 区间锚点（`span_interval_clamped`）→ token（input/output/total）→
budget_remaining → iteration** 的处理顺序逗号拼进
`aitester.export_value_reasons`；无坏值时不出现该属性。判据：**披露属性本身也是
契约，顺序与键名由锁固定，不能靠字典迭代偶然。**

**⑦ 干净导出逐字不变是实测。** 18 份稳定 trace / 174 个 span 改前改后 0 处不一致；
全量 9086 文件 / 129058 span 零披露、27135 个 token 属性全 int、时间戳全非负 int。
逐字段导出、部分三元组合法、不做 total=in+out 算术判定、字符串属性族不设门——
这些都是本轮明确保留的边界。判据：**"收口"不是把导出语义一并改掉。**

**⑧ 变异要覆盖崩溃路径与词汇。** 12/12 锚点转红、0 存活：谓词旁路、非对象静默、
非有限门、缩放溢出、负值、bool、巨大整数 Overflow、budget、iteration、披露属性、
换算公式、属性映射。只测"坏值被拒绝"不够，还要测"拒绝的理由与顺序"。判据：
**同一门的多层防御要各有锚点，不能只测最后一层。**

**⑨ 覆盖自审按分母增量认领改动面。** 本轮 `otel_export.py` 新增 +59 行 / +34 弧，
`coverage.xml` root 口径 18819/19343 = 97.2910%、6862/7296 = 94.0515%，覆盖
+59/+37；未覆盖行 524 与 AP 逐位相同，核心十项与路由三项不变。`coverage report`
偏弧 380 与缺弧 434 是不同口径，不得混用。判据：**先看分母增量是否等于改动面，
再看覆盖增量；总数相等或移动都不单独作证。**

**⑩ 单位是字段的属性，不是导出器的猜测（DZ 轮，2026-10-26）。** ①~⑥ 的 duration
口径此前只覆盖 `duration_ms`（node 事件字段），而 `TraceSession.record_task_end`
写的是 `duration_s`（秒）——task_end root span 的时长恒 0 且无机制名。现按字段名
选单位并让 `duration_s` 优先（task_end 的 `extra` 注入 `duration_ms` 不得改写任务级
时长）；坏值机制名为 `duration_s_*`，披露顺序仍在 `ts` 之后、token 之前。判据：
**生产者与导出器对同一事实的字段名必须由锁对齐，不能靠字段名相似推断。**

**⑪ 记录时刻是操作的结束，区间起点要由时长反推（EA 轮，2026-10-27）。** DZ 让
task_end 的时长接上了，但 `ts` 仍被一律当作 span 起点：`record_node` /
`record_task_end` 都在操作**完成时**取 `time.time()`（duration 从 `t0` 起算），
于是每段时长向未来延伸——真实会话实测 planner span 结束比导出时刻晚 99ms、
task_end 晚 419ms（整整一个任务时长），父子区间不闭合。现在 `task_start` 的
`ts` 是起点、不位移；node / task_end 有可用 duration 时 `start = ts - duration`，
区间闭合在记录时刻；ts 不可用（0 哨兵）不位移；duration > ts 自相矛盾时以结束
时刻为准裁到 `[0, ts]` 并披露 `span_interval_clamped`。判据：**同一字段在不同
事件里可以有不同语义，但"起点"只能由该事件的语义给出，不能由字段名想当然。**

## 36. 附：AR 轮（2026-10-21）导出的标识先合法再谈稳定 — 单 trace、32/16 位 hex、确定性派生

AQ 收口数值值域后，`otel_export.py` 的标识仍直接取自记录。导出是 OTel 结构的生产
边界，标识不是"随便一个字符串"：格式、单 trace、parent 闭合、重复导出一致都是
消费方的前提。判据如下：

**① 标识按消费方规范先校验，再谈稳定。** OTel 要求 trace_id 为 32 位小写 hex、
span_id 为 16 位小写 hex、parent 必须指向同 trace 内的 span。改前 `run_id` 原样当
trace_id（真实 16 位）、`span_id` 原样导出（真实 12 位）、大写 / 非 hex / 全零均可
通过。判据：**"生产者写的是什么"不等于"导出器可以交付什么"。**

**② 一个文件一个 trace。** 改前 `task_start` 无 `run_id` 时用随机 uuid32，node 又用
自己的 `run_id`（16 位）覆盖 trace_id，于是同一文件出现两个 trace，root 与子 span
的 parent 跨 trace。实测 **8002 个文件多 trace、61188 条 parent 断链**。现在文件级
trace_id 由首个可规范化 `run_id` → 首个非法非空字符串哈希 → 路径哈希确定；记录级
`run_id` 只做一致性披露（`run_id_mismatch`），不拆 trace。判据：**parent 的作用域
是 trace，文件级字段不得被记录级字段悄悄改写。**

**③ 缺失 / 非法标识要确定性派生，不得随机。** 改前每次导出 uuid 兜底，同一文件
两次导出的 span id 不同（**9086/9086 文件不稳定**），跨渲染器无法对齐。现在派生值
为 `SHA-256("aitester-span:{trace}:{index}:{attempt}")[:16]`（trace 为
`SHA-256("aitester-trace:{seed}")[:32]`），输入固定则输出固定。判据：**可复现是
导出器的性质，不是调用方的运气。**

**④ 短 hex 规范化要明说，不能悄悄改写。** 短 hex 左补零、大写折小写是接受路径，
不是"原样保留"；非字符串 / 空串 / 非 hex / 超宽 / 全零是拒绝路径，不导出原值并按
字段点名（`*_not_string:<T>` / `*_invalid_format`）。判据：**规范化的方向必须写进
契约，否则消费方无法判断 id 是否可比。**

**⑤ 冲突要处置且留痕。** 同 trace 内 `span_id` 重复时保留首次、后者改派生，并把
`span_id_duplicate` 追加在既有披露之后（不覆盖此前机制名）。判据：**重复标识是
上游事实，导出器只能保证结构合法，不能假装没发生。**

**⑥ 字符串属性也只收字符串。** `decision` / `decision_reason` /
`strategy_selected` / `stop_reason` / `task` 与 node 名只导出 `str`；非字符串按字段
披露，node 空串回退 `"node"`。字符串门与数值门同理：**类型不是值的装饰，是值的
前提。**

**⑦ 本轮改变干净导出的标识是设计，不是回归。** 标识规范化 / 派生正是缺陷修复；
干净记录的属性（数值与字符串）与改前一致，但 id 会变。回归判据改为"同一文件重复
导出逐字相同"（9086/9086 通过），而不是"与 AR 前逐字相同"。判据：**修复改变了
什么，回归就该断言什么。**

**⑧ 披露顺序是契约。** `run_id → span_id → name → ts → duration → token →
string attrs → budget_remaining → iteration → task`；AQ 的数值机制名与 0 哨兵语义
不变。判据：**新增一族披露不能打乱既有族的顺序。**

**⑨ 变异要覆盖"合法化"的每一层。** 16/16 锚点转红、0 存活：大小写、补零、全零、
hex / 超宽、非字符串、文件种子、文件 trace、记录 trace、派生输入、node 名、空名、
字符串属性、task、机制名顺序、重复处置、披露覆盖。判据：**接受路径与拒绝路径
要各有锚点，只测拒绝不够。**

**⑩ 覆盖自审按分母增量认领改动面。** 本轮 `otel_export.py` 新增 +81 行 / +42 弧，
`coverage.xml` root 口径 **18898/19424 = 97.2912%**、**6902/7338 = 94.0605%**；
未覆盖 526 行（+2 = 两处 SHA-256 全零防御循环，结构性不可达）、缺弧 436（+2 同源），
核心十项与路由三项不变。判据：**新增行要逐行被锁执行，分母增量要与改动面相等；
读取相等或移动都不单独作证。**

## 37. 附：AS 轮（2026-10-21）生产端标识先写对 — 32/16 位、root、parent 指向

AR 在导出端把标识规范化、缺失派生、单 trace 收口之后，生产端仍是 16/12 位标识、
`task_start`/`task_end` 无标识、`parent_span_id` 从未出现。导出端的补零与派生只能
掩盖上游缺陷，不能替代生产端契约。判据如下：

**① 生产端按消费方规范写标识，导出端不得长期替它兜底。** `TraceSession` 的
`run_id` 改为 32 位小写 hex、`span_id` / root 改为 16 位；真实语料 61188 条 node
（16/12 位）、9085 条 task_start / 9046 条 task_end（无标识）、`parent_span_id` 0 次即为缺陷
证据。判据：**"导出后合法"不等于"记录时合法"。**

**② root 必须由生产端写，且文件与内存模式一致。** `task_start` 在两种模式都进入
`records`：没有 root，子事件的 parent 就悬空，内存快照无法复原一条完整 trace。
判据：**父子关系是记录的性质，不是导出器按文件推断出来的。**

**③ parent 指向 root 是一层契约，不是任意拓扑。** node 与 task_end 的
`parent_span_id` 都是 session root；本轮不表达节点嵌套，也不允许调用方指定 parent。
判据：**先保证可解析的父子链，再谈更复杂的 span 拓扑。**

**④ 标识宽度改变会撞上通用脱敏，必须按结构字段精确豁免。** 32 位 hex 命中
`mask_sensitive_info` 的长十六进制密钥规则，`run_id` 会落盘成 `<REDACTED_KEY>`。
豁免以"字段名 + `fullmatch` 形状"双精确匹配，普通文本里的同值 hex 仍脱敏；全局
脱敏规则不变。判据：**为结构字段开口子时，口子不能扩成"整条记录免检"。**

**⑤ 纯内存模式新增一条 task_start 是设计变更，不是回归。** `records` 现在以
root 开头；依赖"第一条是 node"的消费方需适配。判据：**修复改变了什么，回归就
断言什么；对未改的消费方要显式复核。**

**⑥ 历史语料不回填。** 9086 个文件、49738 条无标识 node 是历史事实；本轮只修
生产端。引用旧 trace 的派生 id 时仍须注明"派生 ≠ 观测"（AR 边界 ②）。判据：
**修复的生效边界是"新写入"，不是"旧工件"。**

**⑦ 导出端零改动是本轮的验收面。** 生产端写对标识后，AR 导出器应直接得到单
trace、合法 32/16 位、parent 全在文件内、无 synthetic root、无披露；端到端锁
断言 span_id / parent 与原始记录逐条一致、两次导出逐字相等。判据：**上游修好后，
下游的兜底路径应当自然不被触发。**

**⑧ 变异要覆盖"每一层标识 + 豁免"。** 18/18 锚点转红、0 存活：run_id / root
宽度、task_start 两键、node/task_end 三键、parent 方向与取值、span 复用/常量、
内存 root、脱敏豁免、run_id 33 位；M0 中性对照 0 红。判据：**接受路径、拒绝
路径与"不写"路径都要有锚点。**

**⑨ 覆盖自审按分母增量认领改动面。** 本轮 `trace.py` 新增 +10 行 / +4 弧，
`coverage.xml` root 口径 **18908/19434 = 97.2934%**、**6906/7342 = 94.0616%**；
未覆盖 526、缺弧 436 与 AR 逐位相同；`trace.py` 181 statements / 58 branches /
0 miss / 0 partial = 100%。判据：**新增行要逐行被锁执行；相等或移动的读数不
单独作证。**

## 38. 附：AT 轮（2026-10-21）写入口的坏值不是小一号的和 — 整次拒绝、机制披露、读端不可读

AI–AP 轮把 token 计数的**读端**逐层收口后，写入口仍然没有值域约束：bool 当 1、
小数进总量、负数 / `nan` / `inf` 毒化累计器、字符串让整次调用丢失；响应归一与
缓存 `tokens` 又各自 `int(... or 0)` 把坏值改写或吞掉。读端再严，也救不回一个
在入口就被改写的事实。判据如下：

**① 写入口与读端必须共用同一个值域谓词。** 两个写入口都走
`src.budget.token_usage.count_reason`（非负整数；bool / 小数 / 字符串 / 负数 /
非有限都拒绝），不在写侧另写一套。判据：**同一事实只应有一处判定；读端收口
不能替代写端收口。**

**② 坏值整次拒绝，不给部分和。** input / output 任一坏值 ⇒ 本次两个计数都
不累加；缓存 avoided 坏 ⇒ avoided 不累加。判据：**"收下一半"比"全部不收"
更危险——部分和会被下游当成全额。**

**③ 事件计数与金额口径分离。** 调用 / 命中确实发生过，`llm_calls` /
`cache_hits` 照常 +1；被拒绝的是计数金额，不是事件本身。判据：**观测事实
（发生了多少次）与可计价事实（消耗了多少 token）是两件事。**

**④ 披露键只在真发生时落盘。** `TokenUsage.as_dict()` 的 7 键 payload 逐字
不变，`token_write_reasons` / `cache_write_reasons` 仅在非空时追加；`merge()`
聚合两类机制。判据：**干净工件的 schema 不因新增披露能力而改变；条件的
"条件"必须被锁住。**

**⑤ 读端见到标记必须判不可读，零回退也不能吞。** 行级三元组、报告级总量、
缓存口径、OTel 导出都把 `token_write_rejected:` / `cache_write_rejected:`
读成不可读；`row_token_reading` 的"全 0 部分字段按历史零行读"回退在标记在场
时禁用。判据：**标记行的零只是已收下部分的和，不能借零回退洗白。**

**⑥ 记账副产品不得毁掉一次有效缓存命中。** 缓存文件的 `tokens` 原值传给写
入口；坏值仍返回缓存响应、命中计数保留、机制披露；调用前后用
`write_rejection_count()` 判部分和，本次调用含写拒绝则 `tokens` 记 `null`。
判据：**成本字段读不动时，正确方向是"未知"，不是"再付一次真实调用"。**

**⑦ 拒绝不能静默。** 预算开启时 `_record_response_usage` fail-closed
（O14 既有口径），关闭时记录可见 warning 并披露后继续；同类机制只告警一次。
判据：**兼容历史行为不等于允许无声失败；至少要在工件里留下机制名。**

**⑧ 非字符串 model 只跳过归因，不制造写拒绝。** token 计数仍收下，
`by_model` 不并入（读端本就不认非字符串键）；这不是坏 token 值，不应让整行
不可读。判据：**拒绝面要精确到"哪一类值坏了"，不能扩大化。**

**⑨ 变异要覆盖接受 / 拒绝 / 披露 / 读端 / 缓存五层。** 19/19 锚点转红、
0 逃逸：值域判定、部分和、事件计数、`by_model`、缓存 avoided、写拒绝计数、
条件落盘、merge、畸形标记、缓存口径 present、行级 / 总量读端、零回退、
`_call_tokens` 判据、OTel 导出、缓存 int 归一、fail-closed、output-null 归一。
自审补齐两处锁缺口（`write_rejection_count` 缓存分量、`llm_client.py:382`
的 output-null 分支）。判据：**先证明锁会红，再声称行为被锁住。**

**⑩ 覆盖自审按分母增量认领改动面；历史工件不回填。** 本轮新增 +94 行 /
+54 弧全部被锁执行：`coverage.xml` root 口径 **19002/19528 = 97.3064%**、
**6960/7396 = 94.1049%**；未覆盖 526、缺弧 436 与 AS 逐位相同；十项核心模块
1 项变动（base_agent 98.51 → 98.53）。真批次 783 行零标记，历史工件保持原样。
判据：**新增行逐行有锁；旧工件零标记是历史事实，不是已审计证明。**

## 39. 附：AU 轮（2026-10-21）实验侧的未知不是零 — 部分和、写拒绝标记与 `$None`

AI–AT 各轮把共享读取器和报告侧读端逐层收口后，实验侧仍有三个活聚合器
自己折数：`estimate_cost_usd`、`generation_summary` / `usage_totals`、
`run_b8._cost_usd`。它们共同的错误不是"算错了一个数"，而是**把读不动
改写成 0 或半个和**。判据如下：

**① 未知不是零。** `None`（上游拒绝、写入被拒、字段未采到）经
`int(... or 0)` / `float(... or 0)` 变成免费或零 token；报告读起来像
"完整且为零"。判据：**缺席是历史 0，在场不可读必须给 `None` + 机制名，
两者不得共用一条路径。**

**② 部分和不是全额。** 输入侧未知、输出侧可读时仍按输出侧计价，是
"把能算的那一半当成全部"。判据：**金额所需的每个字段都可读才给数字；
任一字段不可读 ⇒ 整笔 `None`。**

**③ 事件计数与金额分离。** `llm_calls` / `cache_hits` 是"发生过多少次"的
观测事实，不因 token 字段坏值连坐；反之，事件计数可读也不代表 token 可
计价。判据：**两类事实各自判定，不用一个坏值互相污染。**

**④ 写拒绝标记必须传到聚合层。** AT 的 `token_write_reasons` /
`cache_write_reasons` 说明"已收下的只是部分和"；聚合器若无视标记，仍会
把部分和全额计价。判据：**上游声明的不可读性，下游不得静默丢弃。**

**⑤ 命中列只依赖本列。** 多样本汇总只报告 `cache_hits`，旧工件可能不带
`cache_avoided_tokens`；用要求两列的缓存口径会让可读命中数折成 `None`。
判据：**读取器的依赖面要精确到"这一列"，不能用金额口径替代事件口径。**
同时，真在场但坏的命中列、非对象 usage、缓存写拒绝标记仍必须阻断。

**⑥ 金额与归因同源。** `estimate_cost_usd` 返回 `None` 时，调用方必须能
通过 `cost_block_reason` 得到同一次判定的机制名；价目优先、usage 机制
保留在汇总披露里。判据：**判定与解释不能各走一套分支，否则会出现
"说 usage 坏了、归因却报价目"的分叉。**

**⑦ 总额的 `None` 要传播。** 两臂成本任一未知，`cost_total_usd` 就是
`None`；含冒烟的总额再叠一层。机制名合并不丢。判据：**和的上游有一个
未知，和本身就不能是数字；合并披露不能只留一侧。**

**⑧ 呈现层不得披数字形状。** `$None`、`None tokens` 与 `or 0.0` 的冒烟
合计都会让"算不出"看起来像"算过"。判据：**机器字段用 `None`，人类可读
文本用「不可读 / 无法估算（机制）」，两者都不伪装成数值。**

**⑨ 变异要覆盖三条聚合器与"空路径"。** 7/7 锚点转红、0 逃逸：usage 门、
命中列、token 三元组、渲染、`_cost_usd`、`_cost_text`、机制键写入。
基线 62 passed、collected 恒 62、写盘前 `compile()`、sha256 字节还原。
判据：**先证明锁会红，再声称行为被锁住；"干净路径不变"也需要锁。**

**⑩ 真实语料只读复算，历史工件不回填。** 1701 份 JSON 中 `token_usage`
10629 / `token_metrics` 324 / `usage_totals` 60 / `generation` 6，坏值与
在场 `null` 均为 0、写拒绝标记 0；用新读取器只读复算 37/37 b8 成本与
6/6 generation 成本逐位一致。判据：**零坏值是历史事实，不是"不会再坏"的
证明；干净读数不变与坏值路径被锁是两项独立证据。**

**⑪ 登记勘误按日期追加。** AB-17 行 ② 的"run_b8 仍自持数字门"在 AE 轮
已处置、AG 轮进一步委托表级谓词；本轮按登记纪律补日期化勘误，不改写
原文。判据：**过期登记是证据链的一部分，更正应可追溯，不应抹掉。**

## 40. 附：AV 轮（2026-10-21）分析侧的成本入口同样有值域 — 单侧未知不是部分和，未知金额不是字符串 `None`

AU 轮收口实验侧三个聚合器后，T1/B2 分析脚本仍自持一套折叠：
`add_cost` 用 `stats.get("token_metrics") or {}` + `tm.get(...) or 0` 直接
计价，片段渲染把 `None` 印成 YAML 字符串 `None`。判据如下：

**① 单侧未知不是部分和。** 输入侧 `None`、输出侧可读时，旧表达式只按
输出侧计价（`input=None, output=200` → `0.00024`）。判据：**金额所需的
每个字段都可读才给数字；任一字段不可读 ⇒ 整笔 `None`。**

**② 在场坏值不得被乘法改写成合法数。** `True` 当 1、小数直接相乘、负数
编出负金额、`nan` / `inf` 进入报告；字符串抛 `TypeError`，非对象在
`.get` 上抛 `AttributeError`。判据：**值域判定先于算术；坏值只产生机制
名，不产生数字。**

**③ 整份缺席仍按历史 0。** 整键缺席 / `null` / `{}` 是"没有 metrics"
的 AE2 哨兵，与"metrics 在场但读不动"是两种事实。判据：**缺席与不可读
不得共用一条路径，也不得互换。**

**④ 机制名要带字段与类型且保序去重。** 两侧同坏时按字段顺序（input →
output）拼接，重复机制名只留一次。判据：**披露必须可定位到字段与原因，
且不得因重复而膨胀。**

**⑤ YAML 未知标量落 `null`。** `cost_usd: None` 在 YAML 里是字符串，
`yaml.safe_load` 读回 `"None"`；未知金额必须是 `null`。判据：**机器可读
字段的形状属于契约，不是排版偏好。**

**⑥ 人类文本用「不可读」。** token 总量未知在表格 / README 中落
`不可读`，不落 `None` 或 0。判据：**机器字段用 `None`，人类可读文本用
「不可读」，两者都不伪装成数值。**

**⑦ 呈现与计算同源。** 片段与 README 由同一份报告渲染；金额为 `None`
时两个出口必须同时给出未知形状。判据：**不得在一个出口修好、另一个
出口继续印 `None`。**

**⑧ 真实语料只读复算，历史工件不回填。** 18/18 逐 seed 成本逐位一致、
入库片段逐字节相同，受 `SHA256SUMS` 保护的工件不重写。判据：**干净读数
不变与坏值路径被锁是两项独立证据；零坏值是历史事实，不是"不会再坏"。**

**⑨ 边界要写清。** shell 批跑器与 `arm_stats` 的 `calls` 原始负载仍未
收口；本轮只声明分析脚本的 `add_cost` 与金额呈现。判据：**收口范围按
路径点名，不得扩张成"全仓已闭合"。**

## 41. 附：AW 轮（2026-10-21）载荷形状先于字段判定 — 坏形状不中止分析，事件计数也要值域

AV 轮收口 `add_cost` 后，同一份 `token_metrics` 在进入金额门之前仍先经过
`arm_stats`：`tm = res.get("token_metrics") or {}` 让真值非对象留给 `.get`
抛 `AttributeError`（整批分析中止）、假值非对象被静默改写成 `{}`（"载荷坏
了"冒充"没有 metrics"）；`"calls": tm.get("total_llm_calls")` 把事件计数
原值直出。判据如下：

**① 形状判定先于字段读取。** `"abc"` / `True` / `[]` / `""` 都是非对象，
不得由 `.get` 抛错、也不得被 `or {}` 改写。判据：**先判形状，再取字段；
两种真假值走同一条拒绝路径。**

**② 原样保留胜过就地归一。** `arm_stats` 不再改写 `token_metrics`，交给
下游 `add_cost` 与池化读取器用同一套共享值域判定。判据：**一处归一不得
替换另一处的判定；载荷形状属于上游事实，本函数只保证"不崩、不改写"。**

**③ 事件计数同样有值域。** `calls` 交 `token_metric_reading`：整份
`token_metrics` 缺席 / `null` / 字段缺席按 AE2 历史 0；字段在场却读不动
（bool / 数字字符串 / 小数 / 负数 / 非有限 / `null`）⇒ `None` +
`calls_reason`。判据：**事件计数是计数，不是"原样透传"的免检通道。**

**④ 计数与金额互不连坐。** `calls` 坏而 token 干净时金额仍可算；
token 坏而 `calls` 干净时 `calls` 仍可读。判据：**一项不可读只废它自己
的读数，不得牵连另一项。**

**⑤ 披露按条件写入。** `calls_reason` 只在 `calls=None` 时出现，机制名
去重后以竖线拼接；干净载荷的返回域逐字不变。判据：**无坏值不新增键，
有坏值必须可定位。**

**⑥ 真实语料只读复算。** 324/324 逐臂读数干净；T1/B2 入库报告 **18/18**
逐位复现、原始批次新臂 **9/9** 复现，重算 `ANALYSIS_REPORT.json`
**逐字节相同**（35542 字节）。判据：**干净读数不变与坏值路径被锁是两项
独立证据。**

**⑦ 历史工件不回填。** 未调用 `--write`，受 `SHA256SUMS` 保护的归档与
原始批次 JSON 零改动。判据：**收口修的是生产路径，不是历史文件。**

**⑧ 零坏值是历史事实。** 324/324 干净不证明未来批次干净；坏形状路径由
22 例锁与 6 个变异锚点证明。判据：**不得用"真语料没坏"替代值域判定。**

**⑨ 边界按路径点名。** 本轮只覆盖 `arm_stats` 一个入口；逐 seed `calls`
不是呈现字段，shell 批跑器与归档脚本仍可自行读取。判据：**收口范围不得
扩张成"成本/用量口径已全仓闭合"。**

## 42. 附：AX 轮（2026-10-21）呈现可以折历史 0，均值不可以 — 三处汇总读点的拒绝、坏形状与部分和

AW 轮收口逐臂统计后，基准与全栈汇总仍有三个读点把聚合 `token_metrics`
原值直出：终端 Token 效率两行（`%d` / `%.2f`）、G8 Markdown 的"总 token"
列、逐基线均值（`or {}` + `float()`）。判据如下：

**① 拒绝不是格式化输入。** AN/AT 把"上游拒绝"表达为字段在场、值为
`None`；`%d` / `%.2f` 没有 `None` 输入域，一次已经跑完的基准会在收尾
抛 `TypeError`。判据：**呈现前先读数，格式化不得直接消费聚合对象。**

**② 形状先于字段，真假值同路。** `null` / 非对象不是键缺席：
`bl.get("token_metrics", {})` 兜不住 `null`，`"abc"` / `True` / `[]` 也
不得由 `.get` 抛错或被 `or {}` 改写。判据：**先判形状，再取字段；
真值非对象与假值非对象走同一条不可读路径。**

**③ 呈现层的坏单元只废自己。** 终端一个字段不可读只把该字段渲染为
`不可读` 并披露机制，同一行其余字段照常；全栈表一个基线不可读只废该
单元格并加注记，整张表继续。判据：**一个坏读数不中止整轮、不连坐同一
载荷的其它字段或其它基线。**

**④ 缺席仍按 AE2 读历史 0。** 整份 `token_metrics` 缺席 / `null`、字段
缺席在呈现层仍读 0；只有在场坏值才 `不可读`。判据：**不得把"旧 schema
没写"升级为坏值，也不得把坏值降级为 0。**

**⑤ 均值跨块聚合，不许缺席折 0。** 逐基线均值的历史口径是跳过缺席块
（旧 `or {}` 行为）；把缺席折 0 会让"没有观测"稀释分母。判据：**呈现层
的 0 不能平移到聚合层。**

**⑥ 在场坏值不给部分和。** 任一在场块不可读 ⇒ 该基线
`avg_total_tokens=None` + `avg_total_tokens_reason`（机制名去重后以 `|`
拼接），不再用剩余可读值平均。判据：**分母不完整时，没有均值优于部分
均值。**

**⑦ token 不可读不连坐任务统计。** `total_tasks` / `passed_count` /
`success_rate` / 错误桶 / 迭代 / 耗时与 token 均值各自独立；一个基线坏
也不污染另一个基线。判据：**一项不可读只废它自己的读数。**

**⑧ 干净路径逐字/逐位不变。** 真语料顶层 64 份 `benchmark_*.json` 的
34 个 token 块、递归 324 个 `token_metrics` 键（246 个 `results.<baseline>`
汇总块 + 78 个嵌套形状）零坏值；246 个汇总块终端文本逐字不变（6 个
PREFLIGHT 嵌套块缺 `avg_tokens_per_task`，不参与该对照）、全栈干净
行逐字节不变、四基线均值逐位复现。判据：**干净读数不变与坏值路径被锁
是两项独立证据。**

**⑨ 历史工件不回填。** 未调用 `--write`，受 `SHA256SUMS` 保护的归档与
原始批次 JSON 零改动。判据：**收口修的是生产路径，不是历史文件。**

## 43. 附：AY 轮（2026-10-21）读取层保真，判定层收口 — run_b8 载荷形状与成本拒绝路径

AW 轮收口 `arm_stats` 后，`experiments/run_b8_injection.py` 的两处读取层
仍用 `rd.get("token_metrics") or {}` 归一：`_load_arm` 把假值非对象
（`[]` / `""` / `0` / `False`）改写成 `{}`，`_arm_summary` 于是把"载荷
坏了"读成"没有 metrics"，成本报 `$0.0` 且无机制名；`_load_harness_smoke`
同一归一让冒烟行存 `{}`，成本虽在改写前算出，载荷证据已丢失。判据如下：

**① 读取层只搬运，不判定。** 读取层的职责是保真：缺席 / `null` 落
`None`，非对象保持原类型与原值，干净 dict 逐位不变。判据：**不得在
证据链最早的一环把"观测到坏载荷"改写成"没有观测"。**

**② 假值与真值非对象同路。** `[]` / `""` / `0` / `False` 与 `"abc"` /
`True` 都是"在场但形状不对"，必须走同一条不可读路径。判据：**`or {}`
的真值/假值分叉是形状判定的漏洞，不是安全默认值。**

**③ 历史 0 只属于缺席 / `null`。** 成本语义由 `_cost_usd` 统一给出：
缺席 / `null` → `0.0`；其他非对象 → `None` +
`token_metrics_not_object:<T>`；对象内任一字段不可读 → 整笔 `None`，
不给部分和。判据：**不得把坏形状降级为 0，也不得把旧 schema 的缺席
升级为坏值。**

**④ 一个事实只有一个判定点。** 读取层保留原值后，金额判定只在
`_cost_usd` 一处；读取层不再做第二套值域判断。判据：**重复判定会让
上游已经知道的坏形状在下游消失。**

**⑤ 冒烟行既要金额也要证据。** 行内同时保留 `token_metrics` 原值与
`cost_usd_standard_price` 读数；两者由同一个 `tm` 派生，不得一个用
原值、一个用归一值。判据：**成本可复算的前提是原始载荷还在。**

**⑥ 干净路径逐位不变。** 真批次 14 份 JSON / 12 个 `token_metrics` 键
全部为 dict；`REPORT.json` 两臂成本 0.046531 / 0.060761 与四行冒烟
0.007456 / 0.008501 / 0.007356 / 0.009719 及各自载荷逐位复现。判据：
**保真修复不得改变干净语料的任何一位。**

**⑦ 坏形状路径由锁与变异证明。** 27 例锁覆盖读取、逐臂成本、冒烟行、
真批次与源码锁；6/6 变异锚点转红（13/6/8/5/6/8），0 逃逸，sha256 原
字节还原。判据：**真语料没坏不能替代坏值路径的锁。**

**⑧ 历史工件不回填。** 未调用 `--write`，受 `SHA256SUMS` 保护的归档与
原始批次 JSON 零改动。判据：**收口修的是生产路径，不是历史文件。**

**⑨ 边界按路径点名。** 本轮只覆盖 `_load_arm` 与 `_load_harness_smoke`
的 `token_metrics`；批次内其它字段、其他脚本与 shell 批跑器仍按各自
口径读取。判据：**收口范围不得扩张成"run_b8 工件读取全面保真"。**

## 44. 附：AZ 轮（2026-10-21）量纲与尾部不得被实现改写 — Cohen's g 是 0–0.5，精确 p 不是 epsilon 的下界

`experiments/emse_stats_extensions.py` 的两个统计量与其声称的口径不一致。
`cohens_g` 返回 `abs(n10−n01)/(n10+n01)`，即 **2g**（范围 0–1），而
Cohen's g 的标准口径（effectsize：`P = max(b,c)/(b+c)`，`g = P − 0.5`）
展开为 `abs(b−c)/(2*(b+c))`，范围 0–0.5。`binom_exact_two_sided` 对
`p=0.5` 用浮点 `pmf <= prob_k + 1e-12` 比较；`1e-12` 容差把整条低于
容差的尾部收进分子，113/0 的 **1.926e-34** 被抬成 ~**1.93e-12**——抬高
22 个数量级。判据如下：

**① 效应量的量纲由定义决定，不由数据范围决定。** 2g 在完全一边倒时
取 1.0，标准 g 只能取 0.5；把 2g 当 g 引用会把幅度系统性高估一倍。
判据：**任何效应量必须能对其标准刻度给出上界，且实现必须满足该上界。**

**② 精确检验不得引入 epsilon 容差。** 概率序双侧的定义是
`Σ_{pmf(i) ≤ pmf(k)} pmf(i)`；加容差等于把"小于容差"改写为"等于
prob_k"，尾部越极端，绝对误差越大。判据：**对称二项尾可用整数权重
`math.comb` 精确比较，没有理由为浮点比较留容差。**

**③ 极端尾的位数是结论的一部分。** 1.93e-12 与 1.926e-34 在"是否
可能偶然出现"的判读上不是同一个陈述；前者已接近常见报告精度下限，
后者是"在本设计下几乎不可能"。判据：**不得以"反正都远小于 0.05"
为由保留被抬高的尾部。**

**④ 非对称概率要按概率序，不按简单一侧乘二。** `p != 0.5` 分支保留
概率序双侧（累加所有 `pmf(i) <= pmf(k)` 的结局），不能退化成
`2 × min(左尾, 右尾)`；例如 `k=0, n=10, p=0.1` 的概率序双侧为
`1 − pmf(1) = 0.612579511`，不是 0.3486784402。判据：**定义写在哪，
实现就必须和它逐字一致。**

**⑤ 受保护工件不原地重写。** 20261016 归档受 `SHA256SUMS` 保护，
`STATS_EXTENSIONS.json`（`785edd76…56f021`）与 `README.md`
（`9762d9ae…cd85599`）零改动；修正值重发到 20261021 新目录，两代
目录同时可校验。判据：**历史证据与当前读数可以并存，不能互相覆盖。**

**⑥ 引用链必须与实现同批更新。** 论文 `g = 0.739` → 0.370、EMSE 骨架
区间 `0.74–1.00` → `0.37–0.50`、复现包工件路径与 X 轮勘误（0.7391 是
2g，不是 Cliff's δ）同批修正。判据：**只改代码不改引用，等于把错误
留在论文里。**

**⑦ 旧读数只保留、不回填。** 四个已登记对比之外的批次若调用过旧函数，
其历史值仍是 2g / 抬升 p；本轮不做全仓历史回填，后续引用须重新复算。
判据：**"修了函数"不等于"所有历史数字自动变对"。**

**⑧ 锁与变异证明两条路径。** 17 例新锁覆盖真批次读数、受保护归档、
重发件、复现接线、渲染口径与引用传播；扩展测试净增 4 例覆盖恒等式、
上界、epsilon 尾部与非 0.5 概率序。M1（回退 2g）11 红、M2（回退 epsilon）
4 红，收集数恒 107，sha256 原字节还原、中性对照全绿。判据：**红数要
能对上消费该定义的具体用例，不能只报"有红"。**

## 45. 附：BA 轮（2026-10-21）rc==0 不是有效通过 — 全 skip / xfail 的套件没有断言执行

pytest 对"没有任何断言执行"的套件同样返回 `rc==0`：全 skip / xfail /
xpass / deselect 的摘要行里 `passed==0`。M1 的 detection（F2P 第二段）
与 repair（gold 侧）只看 `rc`，把这种运行计成有效 green；`repair_replay`
给出 `correct`，`mutation_detection` 把"测试没跑"误报成"测试没有检出力"
（`rate=0.0`）。最小复现：buggy 侧 `rc=1 / 1 failed`、fixed 侧
`rc=0 / 1 skipped` → 旧 detection 返回 **1.0**。判据如下：

**① 退出码不是通过证据。** `rc==0` 同时覆盖"全部断言通过"和"一个断言
都没执行"。判据：**有效 green 必须解析 pytest 摘要行——至少 1 个
`passed` 且 0 个 `failed`；摘要不可解析按不通过处理（fail-closed）。**

**② 部分 skip 仍是有效通过。** 审查报告明确警告"部分 skip 可以与有效
断言通过并存"，因此不能把"任何 skip → 不可用"直接套到 M1：只拒绝
`passed==0`。判据：**`1 passed, 1 skipped` 是有效通过；`1 skipped` 不是。**

**③ 不可测要返回不可测，不是 0 或 1。** detection 的 fixed 侧无有效
通过 → `None`；repair 的 gold 侧 → `None`；重放 → `unverifiable`；变异
基线 → `skipped=True` / `rate=None`。判据：**"没跑起来"既不是检出、
也不是未检出、更不是"测试没有检出力"。**

**④ 同一判定只写一遍。** 新增共享谓词 `_suite_has_effective_pass`，
四个消费点接入，源码锁断言各消费者确实调用它。判据：**新增同义判定
必须先在仓内 grep 既有实现（`_suite_run_verdict` 已区分 skip），不得
各写一份。**

**⑤ 静态适用不等于已证实假阳性。** 全仓 246 份归档、9358 条含生成测试
的行中，非 oracle 且含标记的 114 条、detection=1.0 的 12 条；12 条均为
条件性 skip，无模块级全 skip。判据：**不重跑 LLM、不回填历史读数，
只声称机制已收口，不声称历史行已被证实为假阳性。**

**⑥ 边界必须写明。** `misguided_metrics` 的重放对账与
`emse_gold_conformance_audit` 仍以原始 `exec_rc == 0` 判绿，同一通道在
这些工具中保留（BA 轮时点口径）；本条已由后续轮次收口——`emse_gold_conformance_audit` 由 **BB 轮**改为 gold 全 skip ⇒ `unverifiable`，`misguided_metrics` 三处由 **BC 轮**接有效通过（见 §46 / §47），历史正文不回写。判据：**不得把"四个生产
消费点已收口"引用为"全仓所有 rc==0 判定均已收口"。**

**⑦ 锁与变异证明两条路径。** 35 例新锁覆盖纯谓词、四条消费路径与真语料
静态面；变异锚点覆盖"谓词恒真 / 谓词丢 failed 分支 / 四处守卫各自
失效"与一个中性对照，收集数恒定、sha256 原字节还原。判据：**每条
消费路径都要有能单独转红的锚点，不能用一个总锚点代替。**

## 46. 附：BB 轮（2026-10-21）判据要传播到每一个消费点 — experiments 侧 11 处 rc==0 判绿点收口

BA 轮把"有效 green"判据写进共享谓词并接入四个 M1 同源消费点，同时在
手册 §7 登记了两个**未收口**的剩余消费点。BB 轮先把登记册当索引，再对
`experiments/` 全仓普查 `rc == 0` / `returncode == 0` 判绿点（Grep 枚举
后逐点读上下文分类），确认同一缺陷族还分布在 **11 处**，逐一接入共享
谓词或同步其口径。

**① 普查要先分类再动手。** `rc==0` 判绿点分三类：pytest 套件判定
（本轮收口 11 处）、非套件子进程成功（`git rev-parse` / pip / 补丁应用
/ harness 退出码——与断言执行无关，不动）、以及已有等价证据的
（`compile_exec_metrics` 的 `--collect-only` 带 `n_nodes>0`，不动）。
判据：**"同一个bug族"不等于"同一个修法"；每个点先证明它是套件判定。**

**② 收口不是把值改成 None 就完了，要看汇总口径怎么吃这个值。**
`emse_gold_conformance_audit` 的 status 进 Counter（新增桶即可）；
`emse_ult_dfsmoke_accuracy` 的 accuracy 分子分母要重新定义（不可测行
既不进分子也不进分母，与 material_missing 同口径）；
`emse_ult_gold_diagnosis` 的归因函数要加早退——否则 all-skip 运行会
顺着"全败且无 bucket"的兜底分支被误归因成签名不匹配。
判据：**新增 fail-closed 状态时必须逐消费点追"这个值往下怎么被吃"。**

**③ 对账工具与生产路径要单独轮次。** `misguided_metrics` 三处重放
对账改判据会动 match/mismatch 标签语义（需先评估归档影响）；
`src/` 生产路径（`detection_gates` / `executor*` / `testless_validation`）
与主循环耦合、回归面不同。本轮明确保留并登记，不在大批次里顺手改。
判据：**保留口径必须显式登记为"不得引用为已收口"。**

**④ 内部 API 形状变更，消费点普查必须包含 tests/。** 为让剪枝判据
拿到输出，`gold_consistency_pruning._run_suite` 从返回 `int`（rc）改为
`(rc, output)`；第一轮普查只扫了 `experiments/`+`src/`，漏掉
`tests/test_nested_pytest_env_convergence.py` 的调用位——登记前一跑
（基线守卫之外）恰好抓到它转红。判据：**改返回形状 = 改公开契约，
grep 面必须含 `tests/` 与 `scripts/`。**

**⑤ 变异验证的锚点要与"消费点"对齐，而不是与"改动行"对齐。**
11 个真实锚点逐一对应一处收口（红数 2/2/2/1/2/2/2/2/2/2/1），加一个
只改注释用词的中性对照（0 红）——证明红数来自行为变异而非文本差异。
中性对照第一稿选错（改 `rec["reason"]` 文案被测试锁定），改用注释。
判据：**中性对照必须选真正不被任何断言观察的点。**

**⑥ 静态适用面为零也要写。** 246 份归档零模块级全 skip ⇒ 本轮
fail-closed 分支对历史读数零影响。判据：**"机制已收口"与"历史读数
已修正"是两句不同的话；后者需要重跑，本轮没有做。**

## 47. 附：BC 轮（2026-10-21）对账工具的反方向论证——为什么要改"为了对账而保留的口径"

BA 轮把 `misguided_metrics` 的重放判绿登记为"保留原口径"，理由是会动
归档对账标签。BC 轮用三条论证推翻该保留，并给出处置模式：

**① 对账工具的价值恰在于用当前口径复算。** 归档值是历史快照；重放若
沿用旧口径，对账永远 match，工具退化为"复读机"。判据修正后产生的
mismatch 必须带**可解释归因**（本轮新增"口径修正"分支：
"归档按旧口径记数（fixed 侧 rc==0 但全 skip/xfail/deselect，无有效通过）；
重放按 BA/BC 有效通过口径记 None"），而不是被吞掉。判据：**保留口径
前先问"这个工具是复读机还是审计仪"。**

**② 没有证据时不得指控归档。** `_verdict_agreement` 对"fixed rc==0 但
无有效通过"记 `not_applicable` 而非 `mismatch`——既不能确认"转绿"
（specific_red 的期望）也不能确认"仍红"（over_red 的期望）。判据：
**对账标签的三值（match/mismatch/not_applicable）里，不可判定必须
有独立值，不得默认落入任何一方。**

**③ 判据顺序是口径的一部分。** 初稿把 fixed 有效通过检查放在 buggy 侧
判据之前，"两侧都 all-skip"（buggy rc==0）会返回 None 而非 0.0——与
`_m1_metrics` 的顺序（buggy rc==0 → 0.0 优先）不一致。顺序差异在
单测里才暴露。判据：**跨模块同族判据要逐条对齐顺序，不能只对齐结论。**

**④ 迟发跳过不得覆盖更具体的归因。** 全 skip 任务在逐测试分类后走
`no_classifiable_tests` 结构跳过，`_skip` 原会用通用文案覆盖已写下的
口径修正归因。改为"已有具体归因则不覆盖"（早发跳过路径行为不变）。
判据：**归因文案的写入要有优先级，具体优于通用。**

**⑤ 证据源要跟工具既有产物对齐。** 本工具不保留 pytest 摘要行原文，
有效通过判据因此以逐测试 outcomes 为主证据（junit 对 xpass 记 pass 与
摘要行谓词有已知差异，语料零命中，登记不混用），并为 `run_side` 补留
摘要行作回退证据——该字段只进内部判定，报告 body schema 不变。
判据：**新增证据字段先问"会不会进报告/摘要"，会进的要按 schema 变更
流程走，不会进的要显式声明内部性并被测试锁定。**

## 48. 附：BD 轮（2026-10-21）测量指标内部也有 rc==0 判绿——基线不可测就整体不可测，无证据的变异体不进分母

BA / BB / BC 把「rc==0 不是有效通过」传播到了 M1 与 experiments 侧
消费点，但 **MDO（政策无关变异判别力）本身的两个判绿点从未接过谓词**。
这是"按消费目录普查"留下的盲区：测量指标实现不是消费点，而是判据的
生产者。缺陷形态与 F03 同族，代价是把"测试没跑"写成 `measured` 的
MDR=0——一个看起来最保守、实际上没有证据的数字。

**① 基线无有效通过 ⇒ 整体不可测，且要短路在昂贵步骤之前。** 全 skip
基线在变异体上同样全 skip，逐个跑探针/测试只会得到一组同义反复的
rc==0。守卫必须放在 `_is_execution_error` 与 rc 判据之后、行为探针与
变异体循环之前：放太前会把 `rc=5`（无测试收集）改判成 `no_effective_pass`，
与既有执行错误口径冲突；放太后会白跑子进程。判据：**不可测的判定要在
"开始花钱/花时间"之前完成，顺序本身要被测试锁定。**

**② 无断言执行的变异体不是"未判别"，是"无证据"。** 把 skip 留在
MTR/MDR 分母会让 MDR 被无证据样本压低；把它记成 `crashed` 又会污染
CRASH。正确处置是第三种状态：`no_effective_pass`，排除出分母并单列
披露（`mdo_no_effective_pass`）；全部如此 ⇒ `not_measurable`
（`mutant_runs_no_effective_pass`）。判据：**分母只收"有证据"的样本；
排除量必须可数、可读、可复算。**

**③ 谓词只写一遍，位置要跟依赖方向一致。** 原先谓词在
`experiments/_m1_metrics.py`，`src/measurement/mdo.py` 无法反向依赖
experiments。BD 把它上移到 `src/utils/pytest_output.py`，`_m1_metrics`
保留同名别名（同一对象），既有约 20 个消费点与源码锁零改动。判据：
**共享判据的模块位置由依赖方向决定；别名必须是同一对象，并用
`is` 锁住，而不是复制一份"同口径"实现。**

**④ 真实 pytest 的 module-level skip 返回 rc=5，不是 rc=0。** 端到端
夹具若用 `pytest.skip(..., allow_module_level=True)`，走的是既有
"无测试收集"执行错误分支，根本到不了新守卫；必须用运行期
`pytest.skip(...)`（rc=0，摘要 `1 skipped`）才能复现缺陷。判据：
**端到端锁要打印并核对真实退出码与摘要，不能凭"我用了 skip"假定 rc==0。**

**⑤ 语料适用面为零不等于机制不存在。** 624 条 available 的 MDO 行
MDR 全为正（530 条 `mdo_raw.mdr>0` + 94 条 flat `mdr>0`），130 条含
skip 标记的 available 行 MDR 也为正——历史归档零影响，且部分 skip 与
真实通过并存的口径边界被语料支持。但归档不保存基线原文，无法据
"MDR 为正"反推每条基线；机制由合成最小复现、真实 pytest 端到端与
变异锚点共同证明。判据：**"历史读数不变"是影响面陈述，不是缺陷不存在
的证明；两者要分开登记。**

## 49. 附：BE 轮（2026-10-21）判据的生产者也会漏收口——空套件不是"修复正确"，也不是"补丁安全"

BA–BD 按"消费目录"逐层收口了 M1、experiments 与 MDO 的 `rc==0` 判绿，
但**判据的生产者**——检测门、执行器三条路径、仓库节点、P2P 回归——
仍以裸 `rc` 记 green。这是普查方法的盲区：先按调用方找点，漏掉了
"自己给出 verdict 的组件"。六处缺陷同形：全 skip / xfail / deselect
的套件 rc 同样是 0，于是空套件被记成"修复正确 / 补丁安全"。

**① 判据的生产者与消费者要分开普查。** 消费者的任务是"读对别人的
verdict"；生产者的任务是"给出 verdict"。只扫消费点会漏掉最上游的
六处。判据：**收口一个缺陷族时，按"谁给出这个字段"和"谁消费这个
字段"两条轴各扫一遍。**

**② 无有效通过不等于 over_red。** 检测门①的语义是"buggy 红 + fixed
绿 = 缺陷特异"；fixed 侧全 skip 时两侧证据都不存在，记 over_red 会
把"没跑起来"误判成"补丁过宽"。正确处置是沿用 `unavailable` 路由，
保守放行而非判绿。判据：**证据缺失的处置要服从该判据的语义，不能
一律 fail-closed 到"红"。**

**③ 重试控制流可以看 rc，flaky 证据不可以。** 重试层在 rc==0 停止
是控制流收敛（all-skip 重跑不会变成有效通过，继续重试只制造噪声）；
但 `observed_fail_then_pass` 必须只认 `effective_pass`，否则"首败、
次全 skip"会被记成 fail→pass，把不稳定误诊成 flaky。判据：**
控制流的停止条件与证据的判定口径是两件事，不能共用一个布尔。**

**④ 替身必须保真到判据依赖的字段。** 新判据上线后 5 个既有测试因
替身返回 `"ok"` / 空输出而失败——不是生产缺陷，而是替身没有 pytest
摘要。补上真实摘要行后断言与用例数不变。判据：**夹具替身的最小
保真集 = 判据实际读取的字段，不是"看起来像输出"。**

**⑤ 非 F03 的 rc==0 不得硬套谓词。** `testless_validation.py:165` 是
mypy 返回码（0 = 无类型错误），`:283` 是导入冒烟返回码（0 = import
成功），二者不是 pytest 套件判据。本轮按 dated errata 登记而不接线；
否则"全仓普查 rc==0"会把工具专用返回码误收口成 fail-closed，制造
新的误判。判据：**共享谓词只适用于语义相同的判据；语义不同的
rc==0 要逐点登记例外，而不是复制谓词。**

## 50. 附：BF 轮（2026-10-21）工具链的判据有两副面孔——基线问"测量有效吗"，变异体问"被杀死吗"

BA–BE 收口了 M1、experiments、MDO 与生产路径，但 `scripts/tools/` 里
两处仍以裸 `rc==0` 判绿：`self_mutation.py` 的 preflight 基线与变异体
分类、`verify_synthetic_templates.py` 的 buggy / fixed 两侧。这是
"按目录普查"的边界之外——两处不是产品代码，也不是分析报告，而是
**测量工具自身的判据**。工具骗自己，比产品骗用户更难被发现：它的
输出正是别人用来判断"代码有没有被测试覆盖"的证据。

**① 同一个 rc 在不同位置承担不同命题。** 基线门的 `rc==0` 问的是
"这次测量有效吗"，变异体的 `rc==0` 问的是"这个变异体被杀死了吗"，
模板 fixed 侧的 `rc==0` 问的是"gold 材料自洽吗"。三处此前共用一句
`rc==0`，但空套件对三个命题的答案分别是"无效 / 未杀死 / 未证明"，
绝不能记成"有效 / 存活 / 自洽"。判据：**接线共享谓词前先写清该点
的命题；谓词相同，命题不同的处置（阻断 / invalid / 违规）必须分开。**

**② invalid 不是 survived，分数分母要如实披露。** 全 skip 的变异体
此前记 `survived`，方向上是"保守"（压低分数），但归因是假的：分数
低会被读成"测试检出力不足"，而事实是"这一枪没打响"。改后记
`invalid` + `no_effective_pass:<counts>` 并排除出分母，同时保留
invalid 计数供读者判断测量覆盖面。判据：**"保守的错误读数"仍是
错误读数；排除项与分母变化必须与判定同源披露。**

**③ 嵌入谓词时不得丢掉外围门。** `run_has_effective_pass(rc, output)`
只看 rc 与摘要，不含超时标记。两处调用都写成
`run_has_effective_pass(...) and not timed_out`：否则"超时前已打印
passed"会被记成绿。判据：**共享谓词回答且只回答它命名的那一问；
它与超时、异常、取消等外围条件的关系由调用点显式写出。**

**④ 改前 / 改后逐位相同是预期，不是巧合，也不是"改动无效"。** 真实
输入都带真实 `passed`，新旧口径在合法输入上必须给出同一读数
（80 变异体行逐行相等、模板 50/50 通过）。本轮修的是"空套件被记成
存活 / 自洽"的假读数通道，不是重算真实分数。判据：**零影响是影响面
陈述；它的成立依赖"输入里没有缺陷样本"，与"缺陷不存在"无关。**

**⑤ 既有矩阵测试的签名迁移是口径变更，不是新锁。** 旧矩阵里
`rc==0 ⇒ survived` 的行不带摘要——它们自己就在验证旧缺陷。迁移后
rc==0 的 survived 行补真实摘要，其余行可传空输出保持原判据；用例数
不变。判据：**判据变更时，先找出"编码了旧口径的既有断言"并按新
口径重写；把它们当回归锁保留，等于把缺陷钉进测试。**

## 51. 附：BG 轮（2026-10-21）空结果不是结论——检查器没跑成时，零疑点不能被"读"出来

`_run_mypy_findings` / `_run_pyright_findings` 的历史实现把所有非
正常路径都收进一个空列表：开关关、工具没装、超时、崩溃、退出码
异常、报告结构损坏，以及"确实检查完且零疑点"。静态层再把它折成
`mypy_findings_count=0`。于是四种完全不同的测量状态共用一个 0，
"检查器没跑成"可以一路被读成"补丁类型干净"。这是 F03 缺陷族在
外部检查器上的同构形态——BA–BF 收口的是 pytest 摘要，BG 收口的是
检查器执行本身。

**① findings 的语义依附于执行判定，不能独立成立。** 空 findings
只有在 `status=ok`（工具跑完且报告可信）时才是"无类型问题"的证据；
`disabled` / `unavailable` / `error` 下的空结果分别表示"未检查 /
不能检查 / 检查不可信"。判据：**任何"没有发现"的结论都必须先
回答"检查执行了吗、执行可信吗"；把这两个问题省略，零就变成了
结论。**

**② 退出码语义按工具定义，不能统一写成 rc==0。** mypy 的 rc=1
表示"检查完成且有错误"，pyright 的 rc=1 表示"检查完成且有诊断"，
两者都是可信报告；统一要求 rc==0 会把"检查器正常报告了疑点"误判
为不可测量。反过来，拿不到返回码（`None`）必须 fail-closed 记
`error`。判据：**rc 是工具契约的一部分，先查该工具对每个码的定义，
再决定它证明什么。**

**③ 报告结构也是契约。** pyright `--outputjson` 恒含
`generalDiagnostics`（零诊断也是 `[]`）；缺键/非列表说明报告不可信，
不能 `or []` 当作空诊断。文本兜底可以从损坏输出里救出诊断行，但
救出 findings 不等于检查完成——这条路径不能把空结果升级成 `ok`。
判据：**解析失败时的"尽量恢复"与判定失败时的"降低证据等级"要
同时发生；只做前者就是把损坏读成干净。**

**④ 聚合要有优先级，回退要有出口。** 任一 `ok` ⇒ `ok`（pyright
失败后 mypy 成功仍可测量）；否则 `error` > `unavailable` >
`disabled`——一个工具缺席不能让另一个工具的崩溃被读成"只是没装"。
判据：**聚合规则要同时回答"哪次尝试算数"与"全部失败时最坏状态是
什么"，缺一不可。**

**⑤ 观测键要在早退之前写入，并且必须被声明。** 最需要观测的恰是
空 findings 的假干净路径；若状态只写进"有 findings"的深分支，核心
锁会红。键还必须在 State TypedDict 声明，否则 LangGraph 静默丢弃
（M14 的同一坑）。判据：**可观测性要覆盖失败路径本身；只在成功
路径写入的状态，等于没有状态。**

**⑥ 开关默认关时的"零影响"是影响面陈述，不是缺陷不存在的证明。**
`TYPE_CHECK_ENABLE` 默认关，170/170 份归档结果该键均为 `null`，
所以历史读数不变；这只说明本轮没有改写已有数字，不说明旧路径在
启用时不会给出假干净。判据：**零影响与零缺陷必须分开表述；前者
依赖"输入没走到该路径"，后者需要路径本身被锁验证。**

## 52. 附：BH 轮（2026-10-21）不可测量不是验证通过——四层代理里，"没测成"与"测完无缺陷"共用一个 passed

`src/tools/testless_validation.py` 的四层（AST 符号守卫 / mypy /
命名契约 / 导入冒烟）每层只回 `passed`，顶层再把
`not passed` 收集成 `failed_layers`。于是"原文不可解析所以没得比"、
"`PATCH_CONTRACT_CHECK=false` 恒放行"、"mypy 命令行参数写法错误导致
每次都用法错误"、"解释器起不来"与"这一层真的验过且无疑点"在下游
逐字同形；`src/graph/nodes.py` 的消费点和模块 docstring 都按"验证
通过"读它。这是 F03 族在**执行无关验证层**上的形态——BD–BF 收口的
是 pytest 摘要、BG 收口的是检查器执行，BH 收口的是"代理层是否真的
做过比较"。

**① 根因可能在 argv 里，不在判据里。** mypy 层长期传
`--silent-imports`；mypy 1.15.0 已移除该拼写（只认
`--follow-imports=silent`），于是每次调用 `rc=2` +
`unrecognized arguments`，旧代码把这一行当**被测代码的疑点**，对任何
输入都返回"mypy 发现 1 处问题"——该层从未检查过一行代码，还把工具
链失败记成代码缺陷。判据：**判据全绿不代表该层执行过；先验证
"工具以什么参数、在什么解释器上被调用"，再谈它的返回值证明什么。**
锁的形态也因此是两条：argv 断言（含"不得再出现旧拼写"）+ 真 mypy
端到端双向（干净代码 ⇒ 可信通过、类型错误代码 ⇒ 可信有疑点）。

**② 同一套状态词汇不等于同一个聚合方向。** BH 沿用 BG 的
`ok / disabled / unavailable / error` 词表，但聚合相反：BG 的两个
后端是同一检查的可替换实现，任一 `ok` ⇒ 整体可测量；BH 的四层是
彼此独立的检查，任一层不可测量 ⇒ 整体验证不完整，故取最差者
（`error` > `unavailable` > `disabled` > `ok`）。判据：**聚合规则由
"这些结果之间是什么关系"决定，不由词汇表决定；照搬上游聚合方向会
让"一层没测"被另一层的 `ok` 洗白。**

**③ `passed` 与 `status` 必须分开改，否则会把已披露的降级改成新缺陷。**
本轮只把**未披露**的假干净翻成 fail-closed（mypy `rc ∉ {0,1}`、
`rc=1` 却解析不出疑点行、AST/命名契约输入无法解析）；**已披露**的
降级（层开关关、mypy 未安装、超时、`OSError`、危险 API 拒跑）保持
原 `passed` 不动，只补 `status`/`reason`。判据：**"补披露"与"改判定"
是两件事；一次性把两者都改成 False，等于用本轮的口径修订去改写
历史上已协商好的保守跳过语义。**

**④ 转录勘误要当场登记，且错在转录不在测量。** `branch_total_pct`
落笔前按工作笔记写 94.89〔7081/7462〕，复算 `coverage.xml` root
属性得 `branches-covered=7027` ⇒ 真值 94.1705%，笔记里的 7081 在
工件中不存在。判据：**任何写进登记的数字都要回到工件复算一次；
发现不一致时先怀疑抄写，再怀疑测量，并把纠正留在原处而不是悄悄
改写。**

**⑤ 改写既有断言必须点名披露。**
`tests/test_testless_validation.py::TestAstSymbolGuard::test_syntax_error_degrades`
原断言 `passed is True` 锁的正是本轮收口的假干净。保留它，新锁永远
红；悄悄改它，看起来像"为了让测试过而动测试"。本轮按新口径重写并
在登记中说明（用例数不变）。判据：**判据变更时，凡是"编码了旧口径
的既有断言"都要列出来逐条说明为什么按新口径重写——这是口径修订，
不是测试失效。**

**⑥ "默认关 ⇒ 历史零影响"不说明该层没有缺陷。** 本轮重测（不沿用
笔记）：`TESTLESS_VALIDATION_ENABLE` 出现在 **100** 份归档 JSON、
共 **107** 处取值**全为 `null`**；`testless_validation` 载荷键只在
**2** 份归档出现且**均为 `null`**；`failed_layers` /
`infra_degraded` / `validation_status` / `degraded_layers` 在
**1702** 份归档中出现 **0** 次。普查口径也必须登记——首测把 17 份
`.log` 一起计入得 128 处 / 117 份，按 `*.json` 收窄后才是 107 / 100。
判据：**"零影响"依赖"输入没走到该路径"，与"路径本身无缺陷"无关；
两者分开表述，且计数必须带采集口径。**

## 53. 附：BI 轮（2026-10-22）四义返回值是折叠，判定不动的宣称要有观测面——写盘前两道守卫的"读不懂"收口

`src/tools/patch_applier` 的两道写盘前守卫（`check_naming_contract` 的
`(True, [])` 与 `dangerous_api_added` 的空差集）各自表示两件以上事实：
"比较过、没被删 / 没新增"、"原文读不懂所以从未比较"、"补丁读不懂而原文零
模块符号"、`PATCH_CONTRACT_CHECK=false` 恒放行。消费点
`src/graph/nodes.py::_check_patch_safety` 四种一律读成"守卫通过"，补丁前
原文是当前解释器不接受的语法（py2 `print`）时，删除模块级常量的补丁
`applied=True` 直通写盘、零条 warning。这是 BH 同一折叠的 **source 侧**
形态：BH 收口代理层的 `passed`，BI 收口守卫的返回值。

**① 折叠的识别判据是"取值个数少于事实个数"。** 不必逐条读实现找证据：
数一数同一个返回值有几种读法，只要多于一种就是折叠。BI 的 `(True, [])`
有四种读法，`dangerous_api_added` 返回空集合有两种（"没得比"与"比过没新增"），
两者在归档记录里都只留下 `contract_missing_symbols: null`。判据：**先问
"这个返回值能被读成几件事"，再问"要不要加 status"。**

**② 声称"判定不动"，变异面里就必须有一条"动了判定"的锚点。** 本轮
19 个锚点中 17 个是披露类（把不可测量重新记成 ok、删掉点名、撤掉通道键），
但披露类全红只证明披露代码被锁住了，**不证明判定没变**。M18
（原文读不懂 ⇒ 改成拒绝）与 M19（危险 API 差集丢掉基线集合）是判定翻转锚点，
它们必须红，否则"只补沉默 ⇒ 披露"这句话没有观测面。判据：**处置口径里每条
"不改 X"的宣称，都要配一个"改 X"的锚点；否则它只是散文。**

**③ 词表可以上收单一事实源，聚合方向不可以——并把"不可"写成断言。**
`src/utils/check_status.py` 统一了四值字面量与优先级常量，但
`worst_check_status`（独立检查 ⇒ 最差者胜）与 `any_measurable_status`
（可替换后端 ⇒ 任一 ok 即 ok）两个函数并存，且有锁断言二者在同一输入
集合上给出不同结论、并各自断言未知值的默认（`error` vs `disabled`）。
判据：**统一词汇是收敛，统一聚合方向会造出新的假干净；两者不同之处要
钉成断言，否则后续轮次会"顺手合并"。**

**④ 当"能不能读"成为判据，先实测解释器对该判据的返回域。**
`parses_as_module` 按 `(SyntaxError, ValueError)` 判定，三条实测事实把它
钉住：Python 3.14.6 对空字节抛 **`SyntaxError`**（"source code string
cannot contain null bytes"）——docstring 第一版按常识写成 `ValueError`，
被 `test_null_byte_is_syntax_error_not_value_error` 当场否证并勘误；
孤立代理位（surrogateescape 读非 UTF-8 文件所得）让 `ast.parse` 抛
`UnicodeEncodeError`，它是 `ValueError` 子类，只捕 `SyntaxError` 会从守卫
里抛穿；`ast.parse("")` **成功**，所以空输入是"可解析但没内容"，必须单列
`disabled:empty_input`，不能塞进"读不懂"。判据：**解释器版本相关的事实
要带版本登记，且必须由锁执行一次而不是写在注释里；"空"与"读不懂"是两种
输入状态，混在一起会同时丢两侧语义。**

**⑤ "零回填"要分清"不必"与"不可"。** BI 属于不可：归档里
`contract_missing_symbols` 有 **8865** 处取值（**8853** 处 `null`），
但归档不保存补丁前原文（`target_code` **1** 处 / `patch` **11101** 处），
向前重算缺的是输入本身。BD–BH 多数属于不必（开关默认关、历史读数不走该
路径）。判据：**说清缺的是哪个字段，下一轮才不会把同一条回填再试一次；
"不可"同时意味着新键的历史值只能是 `null`，不得被读成"当时检查过且干净"。**

**⑥ 可达性要在真实消费点复现，不在单元里推断。** 本轮把 HEAD 的
`nodes.py` 取出来 exec 并调用真实 `_check_patch_safety`：改前
`applied=True` / `const_kept=False` / `outcomes=None` / 零 warning；改后
判定逐字节相同，只多两条 warning 与两条记录。判据：**source 侧守卫的后果
发生在写盘路径上；只在守卫函数上演示"返回值有歧义"，不等于证明缺陷可达，
两者要各自给证据。**

## 54. 附：BJ 轮（2026-10-22）"读不懂"有两种异常、盲区不记第二腿、共享键名先查重——oracle 验证层的四义 findings

`src/tools/oracle_validator.py::check_assertions` 把四件事折成同一个
`findings=[]`：扫过且无疑点、输入为空、测试文本读不懂（从未扫描）、被测代码
读不懂 ⇒ 类型推断通道哑火。消费点 `_run_generator_postchecks` 一律读成
"无疑点"，于是 O4（恒真断言 ⇒ 标 `test_defect` ⇒ 路由回 Generator 重生成）
对读不懂的产物**恒不触发**——它是 generator 侧唯一的写侧路径。这是 BI 同一
折叠的**第三个消费面**：BH 收口代理层的 `passed`、BI 收口守卫的返回值、BJ
收口检查器的 `findings` 列表。

**① "读不懂"的捕获面本身就是判据，两种写法不等价。** 旧实现只捕
`SyntaxError`；含孤立代理位的产物经 `surrogateescape` 读入后 `ast.parse`
抛 `UnicodeEncodeError`——它是 `ValueError` 的子类、不是 `SyntaxError` 的，
于是一把坏输入从观测层**抛穿**到调用方。本轮把解析面收敛到
`parses_as_module`（捕 `(SyntaxError, ValueError)`，`src/utils/check_status.py`
单一事实源），这也是本轮**唯一**的行为变化。判据：**凡"输入读不懂"的分支，
先问守卫的捕获列表与共享解析谓词是不是同一份；不是就有抛穿。** 异常族要实测
而不是背文档：本轮同批实测的另外两条是空字节属 `SyntaxError`（首版 docstring
写错，被锁否证后当场勘误），而 `ast.parse("")` **成功** ⇒ 空输入只能是
`disabled:empty_input`，不许混进"读不懂"。

**② 归因口径的两种自然写法，差额要在真语料上测出来并点名。** 围栏整块产物
的归因判据可以是"剥前导空白后以三反引号开头"（strict），也可以是"正文里
出现过三反引号"（loose）——10855 条 `generated_test` 上两口径差 **1 条**
（`strict=72 / loose=73 / loose_only=1`），且由
`scripts/tools/bj_discriminator_crosscheck.py` 独立复核。该脚本**不 import
`src/`**（纯 stdlib），因此与变异验证脚本改写 `src/` 的窗口互不污染。判据：
**当"归因"由一个字符串判据产生，就要给出该判据的另一种写法、两者的差额和
那一条实例；否则归因只是命名。**

**③ 盲区早退不记第二腿——披露通道只记发生过的比较。** 未传 `target_code`
时类型推断腿**从未运行**，所以只记 `disabled:target_not_provided`；若顺手
补一条 `ok:target_parsed`，就是把"没得比"写成"比过且没问题"。代价是腿次
集合随输入形状变化（一条或两条），消费侧与锁都要按这个真实形状写，不得假设
固定两条腿。语料对账因此可逐条闭合：第二腿 **10702** = 10855 − 153（盲区/
空输入不记第二腿的条数）。判据：**"没发生的比较不留记录"与 BH 的"已披露的
降级保持判定不动"同源——都在拒绝让沉默变成证据。**

**④ 新状态键发布前 grep 全仓：同名字段比缺字段更糟。** `oracle_status`
早已被 `experiments/oracle_quality_replay.py:1254` 用作**规约** oracle 的
状态，语义与本轮无关；若复用同名，跨模块聚合会把两种 oracle 折成一个读数。
本轮改用 `oracle_check_status` / `oracle_check_outcomes`，并上锁断言两者
不是同一字段。判据：**跨模块状态键的名字是命名空间，落笔前先查该名是否已被
别的测量占用；查名结果要进手册，不能只留在脑子里。**

**⑤ 最贵的一条：并发测量读到变异体。** 语料探针与变异验证 harness 同时在跑时，
探针在 `src/` 被临时改写的窗口里 import 了变异版 `check_assertions`，打印出
物理上不可能的组合 `{'status': 'disabled', 'reason': 'assertions_checked'}`
——那正是变异体 M5 的指纹，读数作废、且作废的读数一度进了手册。三条固定
规则：**（a）改写 `src/` 的验证脚本独占运行**，语料探针与全量回归一律串行；
**（b）harness 输出落文件、不走管道**——本轮首跑基线行被管道尾部截断，为了
补这一行重跑整批，直接引出下一条；**（c）杀掉任何改写 `src/` 的脚本之后，
下一个动作是全仓标记扫描**（`SIGKILL` 绕过 `finally`，还原不会发生）。本轮
据此在 `src/tools/oracle_validator.py:148` 发现残留的 `# mutation` 变异体，
按字节手工还原（不使用 `git checkout` / `git stash`），再跑 501 例基线 +
mypy + ruff 确认。扫描本身会有假阳性（`src/graph/workflow.py` 的合法
`# mutation_advisor` 注释），所以命中标记后**逐个读源码**再判定。

**⑥ "声称可重跑"的复算脚本自己跑不通，而且只在真实语料那一条上崩。** 为了把
语料里那 1 个盲区站点**点名**，探针加了样本路径收集，却漏了列表初始化；它只在
`file_enabled and status != "ok"` 分支内侧取用未定义名——**在没有盲区站点的输入上
跑得通，在登记的那条口径上 `NameError`**。登记读数本身来自改动前的文件态、是真测的，
但发布出去的复现路径是断的：这类"读数真、复现断"比读数错更隐蔽，因为它只在读者
照着跑的时候暴露。发现者是 `make gates` 的 lint 步（`F821`，链在 0s 退出）——
`scripts/tools/` 下的分析脚本不被任何测试 import，**静态检查是读者与跑不通的复算命令
之间唯一一道门**。判据：**凡写进手册标为"可重跑"的脚本，最后一次编辑之后必须再跑
一次**；修完初始化后本轮已重跑，§3 读数逐位复现。

**⑦ 差点把"还没发生的终跑读数"写进登记（写后当场撤回）。** §9 抄上一轮手册的形制，
在复验跑之后接着补"终跑 + 子集复验"两条，rc、墙钟、链内用时全按"照例会有"写成具体
数字，而那条链一次都没跑过。触发条件不是记忆差而是**模板压力**：模板里有这个位置、
本轮也必然会有，于是补形状的手快过先跑再写的手。发现后删回，改留一条显式声明
"这条链还没跑，本节不写它的读数"；终跑真实发生之后才把 rc 与用时写进去。判据：
**登记里的 rc 与用时只能是过去式**；模板位置需要将来
才产生的数字时，写"待跑"两个字，不写"约 N 秒"、不写"预计"。同轮还坐实了这条口径的
另一面：那次 `rc=2` 的 lint 失败**只作为缺陷登记**，双语 README / CHANGELOG / INDEX /
登记册的门禁句在真跑通之前一个数字也没引用过。

## 55. 附：BK 轮（2026-10-22）两套分母、夹带的 Git 基线、比摘要而不是比值的对账——`ast.parse` 读不懂的逃逸与折叠

BH 收口代理层的 `passed`、BI 收口守卫的返回值、BJ 收口检查器的 `findings` 列表，
BK 收口的是**解析守卫本身**：`src/` 里 13 处 `ast.parse` 站点。实测把「读不懂」拆成两副
面孔——**逃逸**（只有孤立代理位抛 `UnicodeEncodeError`，`ValueError` 子类、不是
`SyntaxError`，单腿守卫放它抛穿调用方）与**折叠**（降级分支把读不懂并进可判定的空值：
`[]` / `set()` / 原样返回旧码 / `ok=True` / `{'<module>'}` / 合成 `func{N}` / 正则兜底）。
本轮的教训不在产品判据，全在**测量层自己**：分母、基线、对账口径、用时来源。

**① 同一棵树可以有两套分母，登记的那一套必须能被别人复算。** 开工普查脚本报"全仓 125 站点
/ 64 单腿 / `src` 35"，第二版对同一棵树报 **60** 单腿。两版对 `except Exception`、裸
`except`、模块级常量元组的展开算法一致，分歧只在两处边界输入的归类。守卫按 **`try` 站点**计、
按"能否接住整个 `ValueError` 族"判，得到 `src/` **78 / 35**（HEAD）与 **78 / 20**（现树）。
处置：普查数字**不进登记**，守卫 docstring 写明"以本守卫自测数为准"，差值不强行归因。判据：
**登记的分母要绑定一条可复算命令**；两套数对不上就各自点名，不取平均、不"以早期为准"。

**② `HEAD` 不等于"本轮之前"，快照也不一定是快照。** 判定不变性对账以 `git show HEAD:` 为
改前基线，但 HEAD 是 BC 收口提交，其下压着 BD→BJ **七轮未提交栈**。本轮的核验法（可复算）：
受比模块的 HEAD 版 grep 共享符号命中 **0 次**、现树命中 9–16 次 ⇒ 共享口径接线全属 BK；
唯一混入项按函数名定位到**未参与对账**的 `build_deterministic_debug_result`。同轮还差点犯了
循环校验：把 `/tmp/bk_head` 当"改前快照"，实际它是 **HEAD 导出**（不含 `check_status.py`），
于是"快照 == HEAD"自证通过却什么也没证明。改为让**门禁自己**去量一份 HEAD 导出
（135 文件 / 79 站点 / 35 未覆盖 / 15 违规），才拿到独立读数，且 15 = 13 BK + 2 BJ ⇒
35 − 15 = 20 与现树闭合。判据：**凡用 Git 当改前基线，先证明基线里没夹带别人；
用来当基线的目录，先证明它的产生方式。**

**③ 对账要比值本身，不要比值的摘要——否则噪声会被读成 1343 项缺陷。** 第一版脚本把 920 份
仓内 `.py` 当输入、跨进程打印 16 位摘要比对，输出 `UNEXPECTED = 1343` 且含 `both_raised = 1`
（`UnicodeEncodeError->KeyError: ['cross_validate']`，实为调用面少传参）。对被点名项做最小复现
（同一输入分别 exec HEAD 函数体与现函数体、**同进程**比 `repr`）⇒ **identical**。处置：输入面
改成"形态栅格 + 归档代码串"、比较改成同进程 `repr` 原文、调用面写对
（`object.__new__` + 显式 kwargs），最终 `both_raised = 0 / UNEXPECTED = 0`。旧脚本已删除、
其机制无法逐行复核，所以这里**只登记可复核的两点**：被点名项最小复现相同、现行口径归零。

**④ `both_raised` 是这类对账的天然盲区，必须单独计数。** 新旧两侧同样抛 `TypeError`
会被读成"等价"。本轮把它从 `identical` 里拆出来单列并打印异常种类（结果 0），
而不是塞进"相同"——**整批同类抛异常**就是调用面写错的信号，第 ③ 条那次 `KeyError`
正是这样露出来的。

**⑤ 标为"可重跑"的复算命令，最后一次编辑之后必须再跑一次；`collected 0` 必须是失败。**
复算邻近面时把 23 个文件名先存进 zsh 变量再 `$FILES` 展开，得到 **collected 0 items**
（zsh 默认不对变量做词分割，整串被当成一个路径）——这不是"这一组没影响"，
是**一条也没跑**。改成把文件名直接写进命令行，才拿到 collected 644 / 644 passed。
同轮另踩两条 zsh 口径：未匹配的 glob 让**整条命令行**中止
（`ls /tmp/bk_*.log /tmp/*bk*.txt` 因第二段无匹配而什么都没列出，据此一度误判"日志没了"）；
`${PIPESTATUS[0]}` 在 zsh 不可用 ⇒ 长输出落文件再 `grep`，退出码取 `rc=$?`。

**⑥ 用时只能带自己的口径出场。** 确认跑 191.76s 是 xdist `-n 4 --dist loadfile`；
**同树串行对照本轮未重跑**（BJ 在同一棵树上实测 521.41s vs 192.77s，2.7× 全来自并行度），
所以登记明写"只与 BJ/BI/BH 的 xdist 4-worker 口径可比"。墙钟 192s 由日志
「创建→末次写入」时间戳推得，不是 `date +%s` 成对采集 ⇒ 只作旁证，不作用时主张。
判据：**没有实测的对照就不写"与上一轮可比"，来源不同的数字不写进同一句话；
登记里的 rc 与用时只能是过去式**（本轮手册 §9 在链跑通之前写的是"`make gates` 尚未执行"，
跑通之前不引用它的任何读数；链跑通后该句改为过去式，其墙钟 242s 另取 `date +%s` 成对采集，
与「日志时间戳推得」的 192s 分列两个来源，不写进同一句话）。

**⑦ 改"卡里登记了行号"的源文件，必须同批重跑生成器。** BK 在
`src/agents/debugger.py:683-693` 的接线插在 Prompt Card §3 已登记调用点 643 与 744 **之间**，
行号整体后移 ⇒ `tests/test_prompt_artifacts_gate.py::TestPromptCard::test_repo_card_is_current`
转红（`make test-cov` 里唯一的非基线失败）。`make prompt-artifacts` 重生成后该文件 21 例全绿。
这条门只在 `make test-cov` / `make gates` 里咬人，**定向跑不出来**。

**⑧ 棘轮的合格判据要按异常家族，不按名字。** `AST_UNREADABLE_ERRORS = (SyntaxError, ValueError)`
而不是点名 `UnicodeEncodeError`：按名登记会漏当下未列出的子类，解释器之后新增的子类也会漏；
门禁对 handler 的判据是"能否接住整个 `ValueError` 族"（`issubclass(ValueError, cls)`，
并解析模块级常量与共享常量本身）。豁免面同一口径，但要清楚**它买到的是披露不是修复**：
`EXEMPT` 第二元是折叠形态的**文字**登记，门禁只校站点数与命中数，不会验证"这里折出来的真是
`[]`"——所以 20 处未收敛站点按名进册、边界另写八条，不写成"已排除"。

**⑨ 变异 harness 的口径换了，上一轮的锁语义就不能沿用。** BJ 的 collected 全程恒定 501，
BK 每个锚点显式声明受影响测试文件，collected 逐锚点 **55–104** 变化（M8 拉入
`tests/test_process_and_candidate_matrix.py` ⇒ 104）。于是本轮的棘轮只锁
"**同一锚点**变异前后 collected 相等"，不锁跨锚点相等；三道检查（写入前 `compile()` 通过、
collected 与基线一致、`finally` 按 sha256 断言原字节还原）与运行后全仓标记扫描照旧
（KILLED=13 / 未击杀 0 / 残留 0）。判据：**口径变了就重写锁的语义**，沿用上一轮的
"恒定"会把真实变化读成回归。

## 56. 附：BL 轮（2026-10-22）量具中途换口径、自证循环的锁、不可达的变异体——发布侧写了、判定侧没读

BH 收口代理层的 `passed`、BI 收口守卫返回值、BJ 收口 `findings` 列表、BK 收口解析守卫本身，
四轮都收在**发布侧**：把 status 写进观测键。BL 量的是那句一直没验过的前提——**判定侧读不读**。
实测：`contract_status` / `static_check_status` / `safety_check_status` / `oracle_check_status` 的
**键名判定读点改前全是 0**，`assess_task_risk` 形参表里没有 `contract_status`。字段是廉价品，
读者才是收口。本轮的教训有**五条**全在**测量层自己**（①②③⑥⑦），一条在归档取值（④）。

**① 中途换量具，改前/改后的差值就掺了仪器变更——只能登记现值，或重跑改前。**
普查脚本对 `contract_status` 报过三组数：A（改前、未按 `(文件,行号,键,构造)` 去重）3/2/0，
d（已接线、仍无逐键对账）6/5/1，e 起（构造归类修正）6/4/1。三组都"对同一棵树成立"，
但 A 与 e 之间既换了尺又改了码，**相减得到的 1/2/1 没有任何含义**。处置：登记里只保留三种
口径无关的对比——形参面（`assess_task_risk` 是否接收该参数，False → True）、调用点实参面
（`graph/debugger.py:909`/`:918` 是否带 `contract_status` 实参，0 → 1）、A2 变量判定读点
（不经去重：`static_check_status` 0 → 2、`oracle_check_status` 0 → 1）。键名普查只登记改后值 +
"每键：计数 == 印出的读点行"的对账行（`对账 = True`）。判据：**换尺就重跑改前；重跑不了就
只登记现值，并写明不可相减。**

**② 用被测集合自身遍历的锁是量具的自证循环。** 第一版写 `for key in at._UNMEASURABLE_STATUS_KEYS:
assert 命中`——删掉一个通道键名，这条锁跟着变短而不是变红（变异 M11 因此存活）。处置：加一条
**字面量集合**断言 `set(at._UNMEASURABLE_STATUS_KEYS) == {5 个字面量}`，遍历只作为逐键行为验证。
同族错误在 BK 也出现过（门禁自测用守卫自己的常量表当期望）。判据：**凡"覆盖全部 X"的断言，
X 必须以字面量钉死；从被测对象里取 X，等于让被测对象给自己打分。**

**③ 变异体存活有两种原因：锁不够，或者那个组合根本不可达。** 为"单腿 ≠ 聚合"先写的语料是
"契约腿 ok + 危险 API 腿 error"，M17 存活——查下去发现该组合在 `safe_apply_patch` 路径上**不可达**：
函数入口的 `ast.parse(new_code)` 硬闸先把不可解析输入拦掉，走不到守卫。可达的非对称形状是
"开关关掉契约腿（`disabled`）+ 原文不可解析（聚合值 `error`）"，须从真实环境变量出发构造。
处置：补一例真语料（`monkeypatch.setenv("PATCH_CONTRACT_CHECK", "false")` + py2 原文），
M17 由存活转击杀。判据：**先证可达，再谈锁的强度；在单元里凭想象拼出来的组合，
杀不掉变异只是因为它没有输入能触发。**

**④ 归档里的 `None` 不是 `[]`，把"没记录"当"没测成"会整批改判历史行。**
`contract_missing_symbols` 在 1594 份可解析归档里出现 **8865** 次，其中 **8853 是 `None`**、
非空只有 12 条。若新读者按"键缺席/取值 None ⇒ 不可测量"写，这批历史行会被整批命中失败模式，
而"键全缺席"其实是"这条腿当时还不存在"。处置：词汇表把 `None` 与 `error` 分成两种读法
（前者"本轮没做这条腿"，后者"这条腿没测成"），`_pattern_check_unmeasurable` 只对
`error` / `unavailable` 命中，并锁一例"归档形状（键全缺席）⇒ 不命中"。判据：
**新读者必须先过归档零影响探针——五个 status 键在 1702 文件里出现 0 次，才是"历史读数不变"的证据。**

**⑤ 继承来的四位小数要重算，别当事实抄。** BK 登记 `19363/19874 = 97.4300%`、
`7093/7520 = 94.3200%`；BL 复算除得值 **97.4288%** / **94.3218%**（两位小数同为 97.43 / 94.32，
判读不变，故不构成回归，但"97.4300%"是把两位小数补零冒充四位小数）。处置：BASELINE 与登记册
的 BK 段各加一条勘误，BL 起四位小数一律写除得值。判据：**引用上一轮数字 = 重新除一次；
算不出来就写明是转引，不补零。**

**⑥ 共享工件的读数归「最后覆盖它的那次跑」；两条红先查工件产出者。** 确认跑带 `--cov` 没带 `--cov-branch`，把仓库根
`coverage.xml` 覆盖成 `branches-valid=0` 版本；下一次 `make test-cov` 里**读这份工件**的两条对账例起手就撞上无分支数据
⇒ rc=2。这两条红**长得像产品回归**（同一文件、同一断言、上一跑还全绿），实际是仪器读取顺序问题：`coverage.xml` 是全仓
共享、后跑覆盖的单例工件。判据：**跑任何"读工件"的测试之前先确认工件由同口径命令产出**（`make test-cov` 的
`--cov-branch` + `COVERAGE_FILE` 隔离），手工快跑要么另指工件路径，要么跑完立刻同口径重生成；裁决顺序是
「产出者 → 时间戳 → 才轮到产品」。

**⑦ 键值来源跑含红时，宁可不改值，也不让最终树落在校验它的链之外。** `suite_seconds` 取自 11703 passed / 1 failed 的
预登记跑，注释里明写「不得引用为全绿用时」，并把三个全绿用时按口径分列（209.29s 含 `--cov`、链内 207.16s / 208.34s
不带 `--cov`）。把键改成 209 只需一行，但那会让 `BASELINE.yaml` 的**取值**落在终跑之后被改——本轮登记的是
「终跑之后差异面只有文本」，改值就自毁这条声明。判据：**登记一致性优先于键值美观；要改值就重跑链，不改值就在同一
注释里写明来源与引用禁区。**

## 57. 附：BM 轮（2026-10-22）复算入口在 /tmp、栅格读数随语义腿开关漂移——实验读侧把"崩了"折成最有利一档

BH 收代理层的 `passed`、BI 收守卫的返回值、BJ 收 `findings` 列表、BK 收解析守卫本身、BL 收**判定侧读不读**。
BM 量的是 BL 登记边界里明写没做的那块——**`experiments/` 的读端**。三处站点把"检测没发生 / 检测崩了"折成
取值域里**最有利**的一档：崩溃腿 `return "low"`（`low` 在下游**就是**干净组）、BL 写到结果行的
`contract_status` 没人读、`_print_r4_summary` 的分子只数 `== 1.0` 而分母是**全部行**。本轮教训有**七条**，
其中**三条在收口阶段被自己的复算当场打出来**（①⑥⑦）——量具不入仓，这三条就永远是散文。

**① 红数必须与产生它的采集面一起登记，"恒 32"这类省事的概括要先复测。**
本轮初稿按变异脚本的**基线**打印（`collected=32`）写成"采集面恒 32"。BM 变异 9 锚点复测：M1 杀 8 红、
采集面 **83**；M2 杀 3 红、面 **91**；M3–M10 才是 32。同一条"3 红 / 8 红"的判读，脱离 collected 就没有意义。处置：锚点表逐行登记
`(锚点, collected, 红数, 被谁打死)`，并复跑三次（墙钟 75s / 75s / 76s，红数逐次相同）。判据：
**登记任何一个计数时，同时登记产生它的采集面/口径；概括句（"恒"、"都是"）必须自己重测一遍再写。**

**② 分母要按函数体普查——同一个打印块里可以并存两套分母。**
`run_main_batch._print_r4_summary` 的 R4/N1 分子数的是 `== 1.0` 的行，分母用的是 `len(rows)`：未测行按
"没回归"计分，`0.0%` 恰好好读成"零回归"。按文件 grep `len(` / `sum(` 看不到这种形状——两处都在同一个
`print` 里，各自的局部名不同。处置：分子/分母逐语句配对登记，`k=0` 时打印"不可测（无可测行）（可测 0/3）"
而不是 `0.0%`。判据：**普查分母要落到"这一句话的分子是谁、分母是谁"，不能落到"这个文件有没有除法"。**

**③ 换分母读出的新数，不得与历史值相减。**
`test_error_rate` 在 11197 行里可测 7206 ⇒ 现口径 7.3% vs 可测口径 **11.3%**；`single_agent` 一行
6.7% vs **94.0%**（50 行可测里 47 行 `=1.0`，旧口径把 647 行未测算进分母）。`regression_rate` 更彻底：
11197 行里可测 **0** 行（8012 `None` + 3185 缺键），P2P 材料行与"写了键"的行**交集为空** ⇒ 恒 `0.0%` 是
结构性的，不是"测出来零回归"。处置：两值各带分母定义并列登记，明写不可相减。判据：
**任何"改前 X% → 改后 Y%"的句式，先证明 X 与 Y 同分母；不同分母就写成两个读数，不写成变化量。**

**④ 新档位必须同时落在内层与包装器，否则同一个缺陷在"已修"的幌子下存活。**
`_combined_risk_level` 早在 O22 就为"异常一律 fail-open 归 low"引入 `unknown`，docstring 逐字写着这件事；
包装器 `_compute_contamination_risk_level` 的 `except Exception: return "low"` 一直没跟，于是"崩了"在归档里
读成"干净"。判据：**给取值域加一档，就按（内层判定 / 包装器 / 消费侧 / 归档）四面普查该档的产生与排除点；
只在其中一面出现的档位 = 没修完。**

**⑤ 复算入口落在会话临时目录，登记的只是转引——把量具入库才会暴露口径问题。**
手册 §8 初稿的复算命令指向 `/tmp/bm/probe5.py` / `probe6.py` / `probe7.py`。收口时三件入库
`scripts/tools/bm_crash_leg_reachability.py`、`bm_archive_level_patch_census.py`、
`bm_readside_denominator_census.py`（去掉探针自带的绝对路径 `sys.path.insert`，改按 `__file__` 上溯仓库根；
合并"同一读数两处测量"）。入库当场抓出两条：⑥ 的开关依赖与 ⑦ 的 `null` 折档。判据：
**登记的每个读数要么有仓内可跑的复算入口，要么明写"转引，不可复算"；会话临时目录里的脚本不算入口。**

**⑥ 分布读数依赖环境开关——同一把尺在两种语义腿口径下给出两种档位分布。**
入库复跑第一次给出 `{'high':1,'low':9,'unknown':5}`，与登记的 `{'high':1,'medium':2,'low':7,'unknown':5}`
差两行。原因不是代码变了：原测跑在 `EMBEDDING_BACKEND=none`（词袋余弦代理）下，默认嵌入口径把两行
`medium` 改判 `low`。崩溃腿 **5/15 命中**与**"判优(low) 且来自崩溃腿 = []"**在两个口径下逐条不变，
所以结论不依赖开关，但**分布数字依赖**。处置：脚本改为两种口径各跑一遍并分别打印，手册 §3.1 写明测于哪个开关。
判据：**登记一个分布/百分比时，同时登记它依赖的环境开关；复算脚本自己把开关钉住，不靠运行者的 shell。**

**⑦ 「无键」与「键在值为 `null`」第二次被折成同一档——§56 ④ 的判据在本轮自己的探针里没被执行。**
归档普查的分类函数写的是 `if pt is None: pk = "<absent>"`，于是手册 §3.2 登记成"low 中 685 行**无 `patch` 键**、
not_applicable 中 5563 无键"。复测：8865 行里**真正缺键 0 行**，那 6248 行是 `patch: null`。这与 §56 ④
（`None` 不是缺席，把"没记录"当"没测成"会整批改判历史行）是同一个错误，隔一轮在自己工具里复发。处置：
分类函数按（缺键 / `null` / 空值 / 有值）四档，手册就地加勘误。判据：
**探针里的分类标签不允许两合一；`is None` 与 `not in` 必须分成两个桶，否则"键不存在"与"值为 null"在报告里同形。**

**⑧ 把九轮叙事折进「当前基线」那一行，等于把历史计数搬进门禁射程——漂移守卫当场拦人。**
README 的 `**最新优化**` 行自 BC 之后未再轮换（BD→BL 只刷新了头部引言与登记册），BM 轮换时把 9 轮的收口句
一次折叠进去，其中 BL / BH / BE 三段各带一句**当时**的确认跑计数（`11704 passed / 5 skipped / 0 failed` 形态）。
`scripts/gates/check_baseline_numbers.py` 的射程是「`## 测试状态` 到下一个 `##`」，那一行正在射程内，于是双语各
2 处、共 4 处历史计数被判硬编码残留。处置：行内改写成 `11704 例通过 / 5 例跳过 / 零失败`（EN
`11704 cases green / 5 skipped / no failures`），当前口径仍只指向 BASELINE.yaml；头部引言（`## 测试状态` 之外）
保留原句式不动。判据：**把历史叙事写进"会被门禁扫描的容器"之前，先读该门禁的射程定义（从哪个标题到哪个标题、
豁免哪些章节），再按其正则自检一次。**同一射程检查还顺手解释了另一件事：本轮第一次拼接 README 行时锚点
`hits=2`——头部引言与表行含同一句 BL 叙事，`expect=1` 的断言把"两处同文"变成结构化信号而不是静默改错地方。
## 60. 附：BP 轮（2026-10-22）恒等式的成立条件写在实现里、没写在断言里；归档恰好没有反例

BP 把「这一行没记录污染级别」从沉默里取出来，分档只花了两小时，**口径怎么定**花得更久，而教训都在口径上。

**① 探针与真语料可以共享同一个盲区。** `value_blank` 初版写 `not level.strip()`——看起来更"完备"
（空白串也确实"没记录"什么）。它让恒等式 `view.unknown == 真 unknown 行数 + cross.unobserved_total`
在含空白串的语料上差 1，因为批次 IX 侧 `" "` 是真值、自成一档。本地全绿、归档探针全绿——
因为**归档恰好 0 行空白串**。"实测无一例反证"不等于"该判据无条件成立"：当反例的唯一来源是
我自己没造的那一类输入时，探针的通过是**样本面的通过**，不是**语义面的成立**。处置：判据收窄为
`level == ""`（与上游消费侧对齐优先于语义直觉），并把恒等式**写成断言**而不是留在注释里
（`TestTwoConsumersReconcile` 15 例 + 参数化双臂），另钉 `test_whitespace_level_is_observed_not_absent`。

**② 「0 红」有两种成因，红数不能反推覆盖面。** P14（无可对照臂时本节消失）首跑 0 红，
第一眼像"锚点已被别的锁间接覆盖"。真相是：所有渲染用例都至少留了一个可对照臂，
`if contam_cross_rows or silent_cross_arms:` 与 `if contam_cross_rows:` 在那些输入下同形。
把该锚点的语义**写成一例**（全部臂都不可对照）之后击杀。推论：判断"已被覆盖"必须能指出是哪一例，
指不出就是没锁。

**③ 同一批行、两种去向 = 两表之差无处可减。** 折叠类缺陷最隐蔽的形态不是"读成 0"，而是
**两个消费者各折一档、渲染层同时引用两者**：`excluded` 按①的三档合计加，脚注却按②的 `unknown` 解释。
这类缺陷只能靠**跨消费者恒等式**发现——单看任何一个消费者都自洽。登记：凡"同一份数据被两处各自折算"
的面，验证预算应花在等式上，而不是花在各自的分档例上。

**④ 顺序失误要如实登记，不能因为"跑过"就当确认跑。** 确认跑早于 `BASELINE.yaml` 刷新执行，
带着基线守卫那一红跑完 203s。它登记为「刷新前跑」并补跑真正的确认跑（11922 / 5 / 0、195.48s / rc=0）。
两跑 collected 同为 11927，passed 差 1——差值正是那一红，这条对账本身也是证据。

**⑤ 静默的最高形态是整节消失。** 122 臂 `available=False` 时 5.3 节**一个字都不写**，
读者只能把"这一节没跑"与"跑了但没数据"读成同一件事。分档之后的最省写法是保留节、
把"为什么没有数"写成一行——本轮的全表无差值披露（"≥0.2 / ≤0.2 判据在这批数据上无从应用"）就是这一行。

**⑥ 归档 0 实例的腿仍要建，但要写清它是为谁的。** `value_null`/`value_blank`/`other_falsy` 三档
在归档 0 命中，与 BN 的 `DEP_INPUT_NULL` 同类：**为新批次与外部工件而准备**，不得登记为"已验证的分布"。

（不复现 = 无证据：本轮四条恒等式全部写成可重跑的 `--collect-only` 62 例；复算命令见分册 §8。）

## 59. 附：BO 轮（2026-10-22）全文子串断言把 100% 读成 0%、锚点可击杀性要先证、写入面普查的阈值时刻决定它归谁——读侧把缺席折成实测

BH 收代理层的 `passed`、BI 收守卫返回值、BJ 收 `findings` 列表、BK 收解析守卫本身、BL 收判定侧读不读、
BM 收实验/报告读侧折到哪一档、BN 收**披露有没有落盘**。BO 量的是落盘之后的另一半：**落下来的字节被读成了什么**。
实测五处站点共同写法是 `state.get(key) or []` + `len(...) == 0`，加上一个自己不落盘的开关（`--save-state`）。
本轮教训有**六条**，其中①②③⑥是本轮自己的量具与锁当场打出来的。

**① 全文子串断言会被同族数字吞掉——`"0.0%"` 是 `"100.0%"` 的子串。**
渲染层锁初版在报告全文里搜 `"0.0%"` 判"缺席档已印出"，而 ON 臂的合法读数 `100.0%` 让断言恒真。
改成**逐行判**（`on_line.endswith(": 100.0%")`，OFF 行既不含 `%` 也不含 `0.0`）。
判据：**"文本里没有 X / 有 X"这类断言，先问 X 会不会是某个更长 token 的子串；渲染层的锁要断整行或整字段。**

**② 锚点可击杀性是**锁**的属性，跑验证器之前必须先证。**
`P5`（删掉 `_GRADE_TEXT["focus_not_recorded"]` 这条档的文本）第一轮 SURVIVED：渲染层写的是
`.get(grade, 兜底)`，删条目照样渲染出一句唯一文本。补「措辞点名 null」+「九档两两不同」两条锁之后转红。
判据：**"把披露退回沉默"的锚点要在被测层有唯一可读出口；先加锁再跑，否则"全红"只是筛掉不可击杀锚点之后的结果。**

**③ 锚点唯一性事前普查，比事后 `ANCHOR-ERROR` 便宜一个数量级。**
BN 栽过一次（同键不同缩进 ⇒ 8 个锚点报错）。本轮改为跑验证器**之前**对 24 个锚点逐个 `count()`，
发现 `return None, "unreadable"` 命中 2 次（两臂同函数），换成两行锚点后运行期 **0 次 ANCHOR-ERROR**。

**④ 写入面普查的阈值时刻决定这批文件算谁的。**
用 `st_mtime > 上一轮链终跑结束秒` 做"本轮 `src/` 零改动"的正证时，亚秒过冲把上一轮**回填的 CHANGELOG/README**
扫了进来（12 个文件，全是 `.md`），差点写成"本轮改了 12 份文档"。阈值改到上一轮终跑之后的一个明确时刻后得 **9** 个文件、
`src/` 命中 0。判据：**阈值要登记成具体 epoch 并说明它为什么晚于上一轮的全部写入，否则"写入面"主张不可复算。**

**⑤ 数值分档与文本分档是两条独立测量——只修一条仍然同形。**
四条不可计算腿改前 `0.0` 与"实测 0%"同数值、`_locate_text` 又同印 `0.0%`。本轮探针分别打印
"数值同形"与"文本同形"两个布尔（改前 True/True，改后 False/False）。判据：
**折叠发生在几个层（数值 / 文本 / 键集合），复算就要测几个出口；一个层的分开只证明那一层。**

**⑥ 重定向到文件 = 块缓冲："没有输出"不等于"没有跑"。**
变异 harness 的 stdout 重定向进日志时，运行期 `wc -c` 恒 0，进程退出才一次性落盘（BJ 是 `| tail` 版，本轮是文件版）。
同一条纪律因此换了个形态复现：**长 harness 的进度只能由退出码判定；不要在它运行期间编辑它正在按 sha256 核对的文件。**

另记一条口径层面的：**"这个开关没开"与"这个开关的状态没被记录"是两件事**。
`save_state` 默认关是**口径**（`run_main_batch.py` 从不传，raw 因此不存在），本轮没有改它；
改的是"事后无法判断当初开没开"——归档普查给的证据是 246 份批次 JSON 里该值 0 出现、
provenance 15 个键里没有它，而磁盘 34 个 `raw/` 目录只有 88 份文件入库。
把开关态写进 provenance 是**买新批次的可复核性**，不是让历史批次变得可复核（那是永久事实，按名登记）。

## 58. 附：BN 轮（2026-10-22）形状数不是通道数的代理、锚点互为子串、整行断言的假绿接线锁——披露没有第二道字节出口

BH 收代理层的 `passed`、BI 收守卫的返回值、BJ 收 `findings` 列表、BK 收解析守卫本身、BL 收判定侧读不读、
BM 收实验/报告读侧折到哪一档。BN 量的是这六轮共同的前提假设：**披露得落盘**。实测三道都不落——
raw 白名单不含任何检查通道（5 种运行时状态 → 1 种 558 字节形状），结果行只有 `contract_status` 一条腿，
存量归档里 7 个键 0 命中。本轮教训有**六条**，其中**四条是本轮自己的量具与锁当场打出来的**（①②③④）。

**① 边界形状数不是通道数的代理——合测会把折档藏起来。**
探针初版把 4 个 status 通道一次写进同一份 state 再数落盘形状，结果行报出「5 态 → 5 形状」，
据此几乎判该行边界无缺陷。改成逐通道单独测才看清：那 5 个形状全部由 `contract_status`（BM 刚接上的那条腿）
携带，static / safety / oracle 三对通道在行里仍是 1 形状。判据：**可达性探针的采集单位是"通道"，不是"边界"；
合测的形状数只证明"至少有一个键在场且携带差异"，它对其它通道是否被折叠保持沉默。**

**② 同一句字面在两处出现＝变异锚点互为子串，改写会命中错站点。**
`"static_check_status": final_state.get("static_check_status"),` 在 raw 白名单与结果行分支都出现，
只是缩进不同。首轮 8 个锚点报 `ANCHOR-ERROR`（命中数 > 1）。处置：锚点前置 `\n` 把缩进层锁死。
判据：**变异锚点必须按"整行 + 缩进"构造，不按"键名字面"构造；`count != 1` 是结构信号，不能靠 `replace(..., 1)` 绕过。**

**③ 断言整行会把注释里的同名词算进去——接线锁当场假绿。**
W1 把 `status-persistence` 从 `make gates` 的**依赖段**摘除后仍 SURVIVED，因为我断言的是整条 `gates:` 行，
而该行的 `##` 注释里也写着目标名。改为只断言 `##` 之前的依赖段。**这是锁缺陷，不是实现缺陷**，按 BM 手册
§6 同一条纪律就地登记。判据：**"X 已接进 Y"的锁必须断言 Y 的判定段（依赖列表、命令列表），
不能断言包含 Y 的整行文本——注释、说明、历史记录都会让断言恒真。**

**④ 残留标记必须与生产文本无歧义，否则"零残留"是假数。**
初版扫描 `# mutation` 命中仓库既有文本（`mutation-det-correlation:`、`# mutation_feedback`），
把「还原干净」读成「有残留」。标记收紧为带冒号的 `# mutation:` 后残留 0。判据：
**残留标记要选一个在生产文本里不可能合法出现的字面，并在首轮就打印命中清单核对，而不是只看计数。**

**⑤ 棘轮的失效方向要显式选择：解析不出的展开宁可不计入。**
`_build_task_result` 的两分支里有一处 `**_cross_file_audit_fields(final_state)` 展开，AST 静态解析能还原其
`return` 键集才算覆盖；还原不了的 spread 一律**不计入**。这与 BK 的收缩额度不同——BN 的 `EXEMPT` 为空：
"声明了却不落盘"没有存量豁免可言。判据：**给静态门禁选择失效方向并写进 docstring：假红（将来重构会咬人）
可选，假绿（新通道静默不落盘）不可选。**

**⑥ 补齐边界不等于打开开关——"默认不落 raw"是口径，不是遗漏。**
`_dump_state_artifacts` 只在 `save_state` 为真时被调用（`experiments/run_benchmark.py:2975` / `:3004`，
默认 `False`，`run_main_batch.py` 从不传）。本轮把两道边界都补齐，但没有改这个开关：默认批次事后唯一可复核面
仍是**结果行**。判据：**登记"未收口"时要区分"没做"与"按口径不做"，前者是待办，后者需要写清依据行号，
否则下一轮会把口径变更当成缺陷修复顺手做掉。**

## 61. 附：BQ 轮（2026-10-22）披露链的最后一环是读者不是字节、门禁跑在脏树上 ≠ 跑在入库后、读数差值必须归因到测量面——报告面把四个 status 通道当作不存在

BG 收代理层的 `passed`、BI 收守卫的返回值、BJ 收 `findings`、BK 收解析守卫、BL 收判定侧读不读、
BM 收实验读侧折到哪一档、BN 收落盘、BO 收 raw 读侧、BP 收统计对照面。BQ 量的是这条链的**最后一环**：
**落盘的字节有没有读者**。实测：BN 把四通道写进结果行两分支与 raw 白名单之后，`experiments/` +
`scripts/` 184 个 `.py` 里从 details 行读这四个键的消费者 = **0**——BM 给 `contract_status` 接的是
**state 读**（生产侧透传），不是报告面行读者。本轮教训有**五条**，其中**三条是本轮自己的量具与锁
当场打出来的**（②③④）。

**① 「写了没人读」要按读法分类计数，不能按键名出现次数计数。**
探针初版把 `.get(key)` / 下标 / 比较一律算"读点"，`final_state.get("static_check_status")`
（持久化写路径）与假想中的 `row.get(...)`（报告面消费者）被记进同一桶，读点读数虚高。
改为按**接收者**分流（`final_state` / `state` / `_post` 等 = state 读；其余 = 行读）后才得到
"行读 = 0"这个真读数。判据：**读者普查的单位是"读法"（从哪里读、读进哪个判定），不是"键名出现"；
同一键名的生产侧透传与报告面消费必须分开计数，否则"没人读"会被自己的普查掩盖。**

**② 门禁跑在脏树上 ≠ 跑在入库后的树上——git ls-files 类门禁对未跟踪文件结构性盲扫。**
本轮首跑意外抓到 `test_json_strict_af.py::test_real_repo_passes` 红，根因是 BD→BP 批次
（b44a1aad）入库的 `scripts/tools/bo_raw_readside_fold_probe.py` 两个宽松 `json.dumps` 写点：
AF 轮的严格 JSON 门禁按 `git ls-files` 只扫**已跟踪**文件，而该文件在批次自己的门禁跑时还未提交
⇒ 脏树上的绿是盲区里的绿，BP 收口「门禁全绿」的声明与 HEAD 实测分裂。干净 worktree 复现存证、
修复两处 `allow_nan=False` 后转绿。判据：**"门禁全绿"的声明必须锚定一次干净树（提交后）的跑；
脏树跑绿只覆盖已跟踪面。新增文件所属轮次要把"提交后复跑门禁链"写进收口步骤——本轮因此改为
先提交代码批次、再在干净树上跑链（两跑各 233s、19 步 rc=0）。**

**③ 读数差值必须归因到测量面，不能一句"src/ 零改动"带过。**
本轮弧覆盖较 BP **−2**（7105 → 7103）。三跑分解：BP 会话 7105 → 本会话排除 BQ 锁文件 7104
（−1：沙箱 skip 19 vs BP 会话 5，能力探测用例未执行）→ 本会话含 BQ 锁文件 7103（−1：
`--dist loadfile` 分组变化对顺序相关分支的影响）。同执行集两次复跑逐位相同（7103/7103）。
判据：**"src/ 零改动 ⇒ 覆盖率逐位相同"是**主张**不是**机制**——执行集（skip 集 / 测试文件集 /
xdist 分组）任何一个变化都会移动读数；差值超抖动域时要做归因实验（排除变量重跑），
把差值分解到测量面上再登记。**

**④ 锚点必须在 format 之后写——`ruff format` 的重排会让锚点静默失配。**
本轮先写 17 个变异锚点、后跑 `ruff format`，三处锚点因换排重列失配（`precheck` 报 count=0）。
BF 轮同型（M5 旧字符串失配）。判据：**锚点的生命周期在 format 之后开始；format 前置的轮次
必须复跑 precheck 并把"format 后锚点复验"写进变异脚本的用法注释。**

**⑤ 两个章节可以渲染同一句「本节未列出 N 个基线」——锁要按内容 disambiguate。**
BP 的 5.3 章节与 BQ 的新章节同款句式，首版锁 `next(ln for ln in ... if ln.startswith("> 本节未列出"))`
抓到了 BP 章节的行（`no_level_recorded`），按「四通道全部未记录」内容过滤后才命中 BQ 章节。
判据：**渲染层的字符串锁要带足以区分同册其它章节的内容特征；`startswith` 级别的定位在
多章节同句式时必然抓错行。**

---

## 62. 附：BR 轮（2026-10-22）契约修复先与"旧契约测试"对账、沙箱 skip 数不是环境噪声、隔离级别是执行链属性——第三方集中复审 27 项收口

**① 修一个契约缺陷，必然要与"锁着缺陷行为"的既有测试对账。**
本轮 27 项中有 5 条既有测试在修复后转红，且红得**正确**：AM 的两条锁的是"缺归因不阻断全额"
（正是 N04 要改的行为）、AG 的一条锁"无归因不新增键"、BK 的一条锁 `src` 的 78 个 AST 站点读数。
处置不是把实现改回缺陷，而是逐条按新契约改写并在用例里写明"历史口径是什么、为什么现在反过来"；
BK 的总数从 78 更新到 79 时同时说明新增站点直接吃共享 `AST_UNREADABLE_ERRORS`、EXEMPT 与命中数不变。
判据：**新增锁的数量不能只看新文件；必须先跑全量，把"因修复而红的旧锁"当成待审清单，逐条给出保留/改写理由。**

**② 沙箱 skip 数不是环境噪声，而是与规范口径不同的分母。**
同一份树：规范口径 collected 12069 = passed 12064 + skipped 5；本会话沙箱实测 12050 / 19 / 0。
差 14 全是环境能力 skip，`check_baseline_numbers` 的 slack 按"skipped(5)"设计（容差 6），
所以沙箱跑必红、规范跑必绿。把 12050 直接写进 BASELINE 会让下一次沙箱跑"看起来绿"，
而把 12064 写成 12050 则会让 CI 判过期。判据：**collected 可以跨口径对齐，passed/skipped 不可以；
登记时必须两口径并列并标明换算关系（本处 19 = 5 + 14）。**

**③ 探针的隔离级别是"执行链属性"，不是模块属性。**
同一个 `runtime_probe.py`，在主执行走 local 时回宿主跑是原级重放，在主执行走 docker/kernel
或被隔离拒绝后回宿主跑就是降级执行——模块自身看不出区别，必须由调用方把 backend 传进来。
把档位做成显式参数（而不是读环境或猜配置）带来两个好处：拒绝路径可被测试直接注入
（5 个后端 × 断言"不启动子进程"），且 trace 能区分 `probe_blocked`（按契约拒绝）与
`probe_degraded`（探针自身故障）。判据：**凡是"同一代码在不同执行链下安全性不同"的模块，
隔离级别必须作为输入显式传递，不能在模块内部推断。**

---

## 63. 附：BS 轮（2026-10-22）口径必须写进配置，不能只靠调用参数——同一命令行的两种 coverage 格式

**① 同一个 `--cov-branch`，控制进程与 worker 写出的数据格式不同，直到 combine 才报错。**
`pytest --cov=src --cov-branch -n 4` 实测：`.coverage`（控制进程）`line_bits=1 / arc=0`，
四个 `.coverage.*`（worker）`line_bits=0 / arc=2438…23136`；`coverage combine` 抛
`Can't combine branch coverage data with statement data`，整轮覆盖率不可得。
根因不是命令写错，而是**分支口径只由 CLI 开关传递**：xdist 控制器 / 子进程没有这个
参数，coverage 按配置默认（语句）写盘。数据文件的 `line_bits` 与 `arc` 表是唯一可核对
的证据——日志只会给一句 URL，不指向"谁写错了格式"。

**判据：任何"工件格式 / 统计口径"标志位，若只由调用方传参，必须同时写进配置并在测试里锁。**
只在命令行传的参数对"非该入口"不可见；不同入口写出不可合并的工件时，失败点会远离
根因（本轮失败在 combine，根因在 pyproject 缺 `[tool.coverage.run] branch`）。

**② 棘轮的"余量够"不等于"可以抬水位"（AA-4 复述）。**
本轮行余量 1.04pp、分支余量 1.78pp，均超过 0.5pp 步长，但水位仍取 CI ubuntu 口径、
不上调：本地 macOS 与 ubuntu 的分支差实测 0.13pp，用本地余量抬水位会让 CI 必红。
判据：**水位是跨平台契约，不是本地读数；余量只用来判断"是否需要人工去 CI 侧确认"。**

---

## 64. 附：BT 轮（2026-10-22）检查点的值必须来自真实路径；只写不读不叫检查点；缺键与错标要分开

**① 检查点字段的值必须从"这条数据实际怎么验收"推出，不能按状态猜。**
`oracle_type` / `test_visible_to_system` 的写入端把可见性硬编码 `True`、类型恒为
`generated_test`；而 SWE-bench 的 `passed` 被 `executor_repo.verify` 的 gold
FAIL_TO_PASS 覆盖（gold 测试不进入任何 prompt）。后果：任何新的仓库级批次都会
声称"验收用的是生成测试、系统看得见测试"——两个断言都与事实相反。
判据：**凡描述"证据来源"的字段，必须由产生该证据的分支赋值**（本轮改为
`_oracle_descriptor(task, baseline, state)` 在五个构造点显式传入），不得在共享
构造器里写常量。

**② 只写不读的键不是检查点，是日志。**
归档 8012 行写了这两个键，全仓读端为 0；报告面无法回答"这批数字的验收信号是
什么"。判据：**新增一个"检查点/披露"键时，必须同时给出至少一个读端（报告章节、
守卫或聚合统计）**，否则它只是把事实埋进 JSON。读端还要能点名"不一致"
（本轮：repo 行必须 gold + 不可见），否则读者仍要逐行翻。

**③ 历史"缺键"与"错标"必须分开陈述。**
本轮归档里 8012 行全 `generated_test/True`——这对 R52 之后的**本地**批次是正确的；
50 行 repo 记录全部早于 R52、两键为 `(None, None)`（缺键，不是错标）。因此本项
的历史影响是 **0 条错误声明**，修的是"下一次会说错"。
判据：**不得把"字段缺失"写成"历史数据错了"，也不得因为"历史没错"就不修写入端**；
报告必须同时给出"归档分布"与"历史影响"两行，让读者能区分 retroactive error 与
prospective risk。

**④ 修折叠的那只手，会在自己的新读端把同一个折叠重造一遍——而且方向是加重指控。**
`oracle_provenance_stats` 第一版对 repo 行只问「是否 gold + 不可见」，于是归档 50 条
**两键全缺**的记录被折成 50 条不一致——正是本轮 §1 刚写下的「缺键 ≠ 错标」的反面。
危险不止于不对称：把"从没说过话的行"判成"说了假话的行"，指控方向是**加重**的，
读者会据此认为历史批次伪造了验收声明。判据：**新增分档时，先问"这一档的反面是谁"，
并把本轮自己刚立的口径当成对读端的一条断言来测**（本轮改为 `repo_rows_unrecorded` /
`repo_rows_consistent` / `n_violations` 三档 + 恒等式，并把归档 50 条缺键行钉成
`50/50/0/0`——用真工件而不是夹具来验口径）。另注意"缺一个键"与"缺两个键"不同义：
只记录一个键属**不完整声明**，仍计入不一致。

**⑤ 锚点预检证得了"唯一命中"，证不了"那一格在被断言"。** T44（把 `repo 缺声明` 列
抹成常量 `0`）首轮存活，根因不在实现而在夹具：只放"一致 + 违规"两行时该格**真为 0**，
`{pv.get('repo_rows_unrecorded', 0)}` 换成 `0` 是恒等操作。这是 §60②「0 红有两种成因」
的同族复现，但多出一条可操作判据：**预检只数命中次数，看不见输入面**；因此每个
"某列/某格"锚点必须能指出是哪一例让它取**非零**值并出现在期望串里，
指不出就是恒等锚点（本轮补第三类输入后期望行变为
`| aitester | 1 | 0 | 1 | 1 | 0 | 3 | 3 | 1 | 1 | 1 |`，锚点转红 `red=1`）。
"48/48 全红"这个数字本身不含这类信息。

**⑥ 滚动式文档里"条目在场"不等于"条目有内容"——空标题是最省力的假绿。**
回填门禁读数时量到：`CHANGELOG.md` / `CHANGELOG.en.md` 的 BP 段落**只有标题**，下一个
`## [Unreleased]` 直接跟在它后面，正文一个字都没有；`git log -S` 见该标题由 `c236cada`
插入且自始为空，已随 BS 入库。现有门禁查的是 H2 **标题序列**中英一致（`check_bilingual_docs.py`），
空标题两侧同形 ⇒ 一路 rc=0。这与本轮 §64② 是同一族的两面：**写了没人读**是读端缺失，
**有标题没正文**是写端只写了目录。判据：**滚动式登记文档每补一个轮次条目，除"标题在场"外
必须断言"该标题与下一个同级标题之间存在正文"**；只在文档面靠肉眼对账，等于没有对账。

（④ 的两档判据与 50 条缺键归档实钉、⑤ 的 11 列期望串，均可在
`tests/test_oracle_provenance_bt.py` 逐例重跑；①–③ 的归档分布见分册 §4 的可重跑命令。）

---

## 65. 附：BU 轮（2026-10-23）判据的"零"要拆档：没喂、喂了判干净、证据进不了门是三种事实；"未红"要分到具体那一条锚点上

**① 计数型判据报 0，必须先问"这一档被喂到输入了吗"，再问"喂到了是不是真干净"。**
`src/tools/self_repair_trap.py` 的三个信号各带最少点数门槛（declining ≥3 在 :104、
collapse ≥2 在 :106、score ≥2 在 :113）。归档 5935 行判定值全为 `False`、信号恒 `[]`——
报告面上这一个读数同时兼容三种事实：**3200** 行只有 1 个历史点（进不了任何门）、**2723** 行
进得了 collapse 门且确实判干净、declining 与 score 两个信号**在整个归档里从没拿到过输入**
（可达域各 0 行）。另有第四种：**531** 行历史确有连续下降，只是点数 <3——**证据存在、判据看不见**。
判据：**任何"0 例 / 无告警"上报告时，必须并列"该判据在真实语料上被喂到输入的行数"**，
按"未记录 / 形状不符 / 欠最少点数 / 达最少点数"分档；分档不写出来，读者无法区分
"判定核说没有"与"判定核没被问"，而后者的正确处置是补跑批，不是记录一个零。

**② 先做同进程重跑对账，再决定动判定还是动叙述——否则会把"没人读"修成"改答案"。**
本轮把判定核在同一进程重跑于归档历史、与行内已写值逐值对照：判定不一致 **0**、信号不一致 **0**、
重跑异常 **0**、读不懂 **0**（`reconciled=True`）。失败面在叙述（缺分档披露），不在算术。
判据：**发现"零 / 沉默"类缺陷时先证伪"算错了"，再改叙述**，且验收线写成
**历史行的值与方向逐位不变、只新增读端**。这与 §64②、BH 系列同族：那只手若去"顺手修正"判定值，
历史读数被静默改写、而报告里再看不出它被改过——这是本系列最贵的一种破坏。

**③ "未红"要落到具体锚点：恒等替换、双重限制、无人消费列数是三种不同故障。**
首轮 62 个锚点 56 红、6 项未红，逐项归因后才可修：
- **U18 存活 = 恒等替换**。想删 `two_point_decline_outside_domain` 的 `input_bucket(...) !=
  BUCKET_FLOOR_REACHED` 门，但该谓词已含 `2 <= len(counts)` 下界、而 `BUCKET_FLOOR_REACHED`
  恰是 `len >= GLOBAL_MIN_POINTS = 2`——删掉得到的仍是同一集合，**任何测试都区分不了**。
  处置：撤锚点、留代码、把撤回理由就地写进锚点表（`scripts/tools/bu_mutation_verify.py:172-174`），
  不为凑红数保留；号段跳号（U17→U19）必须自带说明，否则数锚点的人会以为丢了一条。
- **U30 存活 = 同一限制写在两处**。`mismatches` 同时在循环内 `len(mismatches) < 20` 与返回处
  `[:20]` 封顶 ⇒ 删任一处都不改行为。判据：**限制行为单点落地**；改为只在返回处封顶后，
  「只点名漂移行」（U29）与「封顶 20」（U30）各自可杀。
- **U54 存活 = 结构属性没人消费**。表头掉一列，行仍按旧列数产出，Markdown 看起来照样成形。
  补 `test_bu_table_rows_share_one_cell_count`（4 行 × 13 列单元格数一致）后终跑 `red=1`。
判据合起来一句：**红数只说明锁消费了这次改动，不说明这次改动本来可被区分**；因此每个锚点
登记时要能指出"哪一例、取什么非平凡输入"让它可杀，指不出就是恒等锚点（§60② / BT §6⑤ 的第三次复现）。

**④ 红数 −1 与红数 0 是两类故障，别并成"存活"。**
U49 / U50 / U53 首轮报 **SYNTAX-ERROR**：替换文本以 `\"""`（五引号）收尾，在 f-string 里非法，
harness 在 `compile()` 之前就失败——**变异根本没写进文件**。判据：**"判据没被断言"（补断言）与
"锚点是坏字符串"（改锚点，合法写法是 `"""...\"""` 四引号或改用三单引号字面量）必须分列**；
并成一类会把修法指向完全错误的对面。本轮能分开归因，靠的是 harness 写盘前 `compile()`、
终态按原字节 sha256 还原、以及 `# mutation: ` 残留扫描为 0——三者缺一，"没写进去"就无从证明。

**⑤ 手册里的"实测"，必须先在同一条命令上跑通真语料。**
§4 普查命令首版直接对 `d.get("results")` 取 `.values()`，而归档里存在 `results` 为 **list** 的
文件，`AttributeError` 当场中断（1702 份 JSON 里只有 257 份是批次文件）。判据与 BT §6③ 同族、
这是第二次：**夹具绿不构成"实测"**，复现命令的验收是"在 `experiments/results/` 上退出码 0
且吐出报告里那几个数"。

**⑥ 同一普查给出两个数时，选口径的依据是自洽，不是先后。**
"0 个非 `None` 变异分数的行数"在两处不同：早先探针把 12 行形状不符排除在分数统计之外（**5680**），
§4 命令按"键在场即计入"处理（`mutation_scores(None)` 返回空序列 ⇒ **5692**）。本轮以 5692 为准，
依据是它与分母自洽：5692 + 243 = 5935 = 有判定行数；并在 §1 括注 12 行的去向。
判据：**不得让两个数并存而不中翻译**——归因留给读者，等于把口径藏回注释。

（①–② 的分档与对账读数可用分册 §4 的普查命令重跑；③–④ 的逐锚点红名、撤回注与终跑 61 锚点
全红 + 对照 0 红见 `scripts/tools/bu_mutation_verify.py`；③ 的列数锁与 ② 的期望串在
`tests/test_trap_input_domain_bu.py` 逐例重跑。）

## 66. 附：BV 轮（2026-10-23）「没看」与「判干净」只能由写侧区分；按构造恒真的标记不是检查点

**① 同一族缺陷有两种修法，取决于「判定输入是否落盘」。**
BU 轮收口 Self-Repair Trap 时"判定核一处不动"能成立，是因为判定输入
（`oracle_quality_history`）已经跟着结果行落盘——读侧可以把它重放一遍、重新分档。
BV 轮面对的这两族不是：test-hacking 判定核要的是**原码与补丁后代码**，行里只有
`patch`、没有 `instance_code`，解析失败发生在哪一侧也无从得知；FL 约束门的
「无原码 / 无候选 / 异常」三个早退在行里同样没有痕迹。于是读侧再怎么努力也只能
给下界。判据：**披露可行性先看输入是否落盘**——输入落盘 ⇒ 纯读侧披露（BU）；
不落盘 ⇒ 必须写侧增量（BV 的 `test_hacking_status` / `fl_constraint_reason`），
不能拿"上一轮没改生产代码"当纪律照搬。

**② 桶的个数由行内材料决定，不由"想要几档"决定。**
FL 的六种早退里只有三种能从历史行反推（无补丁 / 无定位 / 变更集合为空），另三种
（无原码 / 无候选 / 异常）必须在报告面落 `inferred_unattributed` 并明写"下界"。
把不知道的塞进最近的桶是造数；把推断值与记录值并成一列，则等于让读者以为
"历史行也记录了成因"。

**③ 首轮变异三处存活，三种不同处置——"存活"不是一句"已登记"就完了。**
- **V04 常量改名存活**：`no_candidates → no_candidate`。模块内所有比较都走常量，
  改名在代码面上自洽、任何行为断言都看不见它。补的是**字面量契约锁**——成因名会
  落进结果行 JSON，改名等于改工件契约，这条只能靠字面量钉。
- **P11 两列互换存活**：夹具里"记录成因 : 推断成因"恰好 1:1，交换是**恒等操作**。
  补的是**不对称夹具**（2:1）。与 BU U18 同族：对称夹具会让整类变异失明。
- **S03 把"恒等式为真"硬编码 True 存活**：四档、两支都由同一个循环里的分支赋值
  ⇒ 恒等式**按构造恒真**，这个标记不是检查点。处置是**删字段**，恒等式改由测试
  直接断言。这是 §64 的镜像——§64 讲"检查点的值必须来自真实分支"，本条讲
  "由同一次赋值算出来的两个量互等，也不是检查点"。**删掉一个假检查点与补一条
  锁，价值同级。**

**④ 锚点必须与 `ruff format` 之后的字节对齐。**
本轮 58 个锚点（+1 中性对照）的 precheck 一次通过，是因为锚点写在格式化之后；BH / BF 两轮都吃过
"format 重排 ⇒ 锚点失配 ⇒ 计数 0 ⇒ 静默跳过"的亏。precheck 的 `count != 1` 是这条
纪律唯一的前置拦截，不能省。

（BV 轮终跑：**58 锚点全部转红 + 对照 0 红**，逐锚点红名见
`scripts/tools/bv_mutation_verify.py` 的 SUMMARY 段；①②③ 的分档与对账读数可用
分册 §4 的普查命令重跑——`--segment a` 全归档分档 / `--segment b` 键池复核
（6 键 / 34943 行）/ `--segment c` 四个具名冻结批次逐档核对。）

## 67. 附：BW 轮（2026-10-23）判定值齐备不等于分母可见；「算不出」不是「算出零」；验证通过不得覆盖验证输入为空

补丁从「写盘成功」到「gold 判正确」是一条多门链，每一门都在结果行里留下判定值。
BW 量的是这些判定值**下游的读者**：`patch_precision`（8012 行）、两证据键（4044 行）、
`patch_abstain_signals`（5935 行）自写入起报告面读端为 0，`patch_validated` /
`patch_validate_verdict`（4044 行）只有测试读者。缺的不是值，是**分母**。

**① 同一个精确率有三个分母，报告只印一个就是把口径选择藏起来。**
存储口径 45.6048%（607/1331）、并集口径 50.7483%（746/1470）、gold 口径 57.9198%
（607/1048）相差 12.32pp。任何"精确率"读数不带分母标签都不可引用；三个数也**不得相减**
——它们回答的是三个不同问题（接受集里对的占比 / 接受或判对的并集里对的占比 / 有 gold
材料且接受的行里对的占比）。

**② `None` 是「算不出」，不是「算出零」。**
`patch_precision` 在 plausible=0 时写 `None`；读侧若用 `or 0` 归一，就把"这一批没有任何
接受样本"读成"精确率 0%"，而 0% 恰好是最坏读数——缺席被翻译成了最强的负面结论。BW 的
读侧只在 `plausible == 0` 时返回 `None` 并单独计数，0.0 仅表示"有接受样本且全错"。

**③ 可测量性有两层：输入可达域与判定结果。**
验证族 4044 行里只有 `patch_evidence_level` 有可达输入（1007 行）；`repo_verification` /
`deterministic_repair_status` 在整个归档**零行输入**。于是"验证通过"这个读数在本语料上
不能区分三种事实：验证跑过且干净、验证没有可用输入、验证从没跑。报告必须把输入可达域
与判定结果并列披露；"输入为空"不是"已排除"。

**④ 首轮变异四项存活，四种不同处置——存活不是一句「已登记」。**
- **S19 无直接读者**：选择性风险的恒等式只在 stats 里成立，报告值没有断言 ⇒ 补恒等式断言。
- **P13 变异串落在字面量内**：改写字符串内容不改变渲染（因为替换文本仍在引号里）⇒ 锚点改成
  整行改写、注释落在字面量外。
- **P15 报告初始值被统计自愈**：报告初始化后又被 `setdefault` 填满，删一项不生效 ⇒ 锚点移到
  脚注的 join 循环，测试收窄到该片段。
- **M03 对称夹具**：`n_recorded == n_passed` 时"分母用 passed"与"分母用 recorded"恒等 ⇒
  补不对称用例（1/2 vs 1/3）。与 BU U18、BV P11 同族：对称夹具让整类变异失明。

**⑤ 用时要先证同并行度。**
本轮预登记跑 600.17s 是**单进程**口径；BV 的 218.94s 是 `-n 4 --dist loadfile` 沙箱口径。
两者不可互比，登记只写本轮口径，不作"变慢"结论。

（BW 轮终跑：**68 锚点 = 67 变异 + 1 中性对照全红 / 对照 0 红**，collected 逐锚点恒 94，
逐锚点红名见 `scripts/tools/bw_mutation_verify.py` 的 SUMMARY 段；①②③ 的读数可用
`scripts/tools/bw_patch_acceptance_census.py --segment a|b|c` 重跑——A 段键池 2 键 /
12908 行，B 段 257 批次 / 11197 行逐位复算，C 段五个具名冻结批次逐档核对。）

## 68. 附：BX 轮（2026-10-23）通道关闭不是全低风险；键缺席不是低风险；五层输入域共用一个 `None`；两义键只能分解不能重定义

BU 普查的 13 键 / 76,488 行「只写不读」池，经 BV（41,545 行）与 BW（22,035 行）
之后只剩 `risk_summary`（8,864 行）与 `mdo_crash_rate`（4,044 行）。两者在报告面
读端为 **0**，而且不是「值不可信」——值是忠实的，沉默在**分母与输入域**上。

**① `enabled=False` 是通道关闭的占位，不是「全部低风险」。**
全归档 8,864 行 `risk_summary` 全部 `enabled=False`，`risk_level` / `approval_action` /
`risk_score` 非空 **0** 行。任何读侧若把 `level=None` 归一成 `low`，整份归档会得到
「零高风险」的假读数；`pause_requested=False` 同理——通道关闭时它恒为 False，
不构成「判定无需暂停」。只有 `enabled is True` 的行才有可读级别。

**② 键缺席与低风险是两件事；`contract_status` 在场 0 行是「无证据」，不是「已确认」。**
2,333 行早于该键落盘，必须单列「键缺席」，不得并进 `enabled=False`。
`contract_status`（BL 起才写入）在 8,864 行在场记录里一次也没出现 ⇒
「缺失符号为空可不可信」在归档上**没有证据**；写成已确认是把缺席当通过。

**③ 五层输入域共用一个 `None`，而 crash 的分母是全池 `n`。**
未跑 2,312 / 材料缺 122 / 不可测 986 / 暂定池 530 / 实测 94，合计 = 键在场 4,044。
只有 94 行有规范值（79 行实测零崩溃、15 行非零，池化 15/3,200 = 0.46875%）。
`mdo_crash_rate` 的分母是**全池 `n`**（含 `non_terminating` / `probe_invalid` /
`no_effective_pass`），与 MTR/MDR 的**可评估**分母不同；可评估计数五键
（`mdo_status` / `mdo_evaluable` / `mdo_non_terminating` / `mdo_probe_invalid` /
`mdo_no_effective_pass`）在归档 **0 行在场** ⇒ 可评估分母无法复算，
crash 率不得与 MDR 相除或相减。把 `None` 读成 0、把暂定池并进实测，
都会改写分母。

**④ `mdo_pool_floor_ok=False` 是两义键，只能分解不能重定义。**
1,516 行 = 暂定池 **530** + 不可测 **986**；后者是 `MDOResult` 的默认值，
**不是池不足**。直接按该键筛「池不足」会多算 986 行。暂定池的原始值在未读的
`mdo_raw`（530 行，12/7,190 = 0.1669%），与规范值 94 行是两个口径，
**不合并、不求和、不求平均**。

**⑤ 本轮自纠与变异——形状对不齐先改锚点，不反推期望。**
`level_nonnull` 初版对全部行取非空，会把 disabled 行的残留级别读成「可读」，
改为只统计 `enabled is True`；`contract_status` 夹具期望少算一行、pause 桶与
表列数先于实跑手算错——三处都在跑之前按夹具重算纠正，**不以测试输出反推期望**。
变异 **44 锚点 = 43 变异 + 1 中性对照全红 / 对照 0 红**，collected 逐锚点恒 102，
sha256 原字节还原，`# mutation: ` 残留 0。

（BX 轮终跑：读数可用 `scripts/tools/bx_residual_keys_census.py --segment a|b|c`
重跑——A 段零读者池 **0 键 / 0 行**、闭合 41,545 + 22,035 + 12,908 = 76,488；
B 段 257 批次 / 11,197 行逐位复算；C 段三个具名冻结批次逐档核对。逐锚点红名见
`scripts/tools/bx_mutation_verify.py` 的 SUMMARY 段。）

## 69. 附：BY 轮（2026-10-23）载入行数不是 n；整份剔除与行内折叠是两种剔除；扫描面之外还有结果文件；字段 None 不是 0

报告 `## 数据来源` 只列纳入文件，而加载器在此之前有四层文件级剔除，载入之后
还有一层行级去重。读者看到「110 份 / n=561」时，前面的 3,649 行怎么消失的、
7,010 行怎么变成 561 的，报告面一个数都没有。

**① 载入 7,010 行不是 n。**
扫描 246 份 / 10,659 行 → 数据集外 886 行、schema 2,463 行、未登记基线 300 行
→ 载入 7,010 行；`latest_rows_by_task` 折叠 **6,449 行（91.997%）**，唯一
task 行 **561**。把 7,010 当 n 会放大样本量 12.5 倍；Hurlbert（1984）的伪重复
定义要求 n 只数独立观测单元，折叠本身没错，折叠量必须披露。

**② 整份剔除与行内折叠是两段，不能合成一个「排除数」。**
PRISMA 2020 流程图要求逐阶段数量 + 排除理由，且流程图与正文/结果表逐一对账；
文件级剔除（数据集 77 份 / 886 行、schema 59 份 / 2,463 行）与行级折叠
（未登记基线 300 行、重复 6,449 行）分列，否则读者无法核对自己看到的
110 份清单之前丢了哪些文件、丢在哪一层。

**③ 扫描面之外还有结果文件，且混批口径是另一个分母。**
全归档带 `results` 的 JSON 257 份 / 11,197 行，其中 13 份 / 538 行不叫
`benchmark_*`，连扫描面都没进；`--allow-schema-mixed` 的 169 份 / 9,473 行
与默认口径相差恰为 schema 层 2,463 行。两个口径不可相减，非 benchmark 命名的
文件不可并入扫描面。

**④ 字段 None 不是 0，且混批会改变可测行数。**
唯一行 561 里 `detection_rate` 45 行不可测、`repair_rate` 52 行不可测；
它们不进配对分母、不折成 0 参与均值。混批口径下不可测行升到 463 / 470，
换口径读出的可测率不得与默认口径相减。

**⑤ 本轮自纠与变异——锚点以格式化后的原字节为准。**
`{"results": []}` 的归层期望初版写成 schema（实际加载器先因形状不合法整份失败
⇒ `load_error`）；C 段 `ast.literal_eval` 读不了夹具里的模块常量；A 段把局部
赋值当成读者；B 段拿 4 键视图比 2 键期望；C 段给被剔除批次留了 `included` 键；
F26 存活暴露逐基线字段没断言（补断言 + F41）；F33 锚点被 `ruff format` 折叠后
失配（锚点必须是格式化后的精确子串）；`archive_universe` 的 `except: continue`
触发 S112（加 `# noqa: S112` 并写明盘点只数可解析文件）。变异 **46 锚点
= 45 变异 + 1 中性对照全红 / 对照 0 红**，collected 逐锚点恒 27，sha256 原字节
还原，`# mutation: ` 残留 0。

（BY 轮终跑：读数可用 `scripts/tools/by_analysis_flow_census.py --segment a|b|c`
重跑——A 段接线与 `src/` 零命中；B 段 246 份 / 10,659 行逐层复算、三层对账
（10,659 − 886 − 2,463 − 300 = 7,010；7,010 = 561 + 6,449；9,473 − 7,010
= 2,463）成立；C 段五个具名冻结批次 5/5。逐锚点红名见
`scripts/tools/by_mutation_verify.py` 的 SUMMARY 段。）

## 70. 附：BZ 轮（2026-10-23）测试契约锁定的工件必须入库；前提不成立必须显式 skip 带读数；`abs=0.0` 只适用于精确可表示的值

BZ 轮收口的是**测量环境本身的可见性**：CI 三族红（test 3.12/3.13 的 32 例失败、
3.14 作业 30min 超时、Security 的 pip-audit 45 漏洞）此前在本地全量绿的面纱下
静默了近一周（10-19 起 push run 全红，而 README「已知失败」行写着「CI 全绿」）。
五条纪律：

**① 测试契约锁定的工件必须入库——AK3 原则从「报告引用」扩展到「测试契约」。**
29 例测试把具体归档文件/目录写进契约（pinned 批次、损坏 trace 目录、逐位复现的
报告），工件却被 `experiments/results/**` 排除 ⇒ fresh clone（CI）里
FileNotFoundError 全红，本地因工件在盘而不可见。这与 AK3 门只覆盖「报告直接
引用的证据工件」是同一缺陷族的两个面；处置按 main_batch / r4_batches 惯例逐层
negation 放行（408 个 / 5.9 MB）。**普查必须两种路径写法都覆盖，闭环必须以实况
（失败清单）为准，不能以普查集合（期望）闭环**——首轮 AST 普查漏采不带
`experiments/results/` 前缀的 `DET1_ROWS` 式写法，二轮验证剩 9 红才补 2 个文件。

**② 前提不成立 ⇒ 显式 skip 且理由带实测读数，不得折叠成失败、也不得折叠成通过。**
三类前提在 fresh clone 里不成立：语料面普查（扫描面下界以全归档校准：246 份 /
138 目录 / 8539 trace / 129058 span）、历史切点对账（`git show <历史 rev>`，shallow
clone 必败）、双盲纪律不入库的文件（paper / 投稿骨架）。它们的失败形态是
AssertionError / FileNotFoundError——把「环境里没有」报成「锁被打破」；`tests/
_corpus_guard.py`（单一事实源）统一改为 `pytest.skip` 且理由带读数
（`benchmark_*.json 107/246、traces* 目录 84/138、trace 文件 6759/8539`、
`历史切点 b533cff1c316 不在场（shallow clone）`、`.gitignore:119 双盲纪律`）。
**CI 绿 ≠ 这些锁在 CI 执行过**——skipped 计数与理由必须可核。

**③ `abs=0.0` 只适用于精确可表示的值。** 非 0.5 精确二项走 `lgamma`/`log`/`exp`
的 logsumexp，macOS Accelerate 与 Linux glibc 末位可差 1-2 ULP ⇒ `abs=0.0` 的
逐位断言在 CI 红、在 macOS 绿（跨平台不可复现的「幽灵红」）。改 `rel=1e-12`；
p=0.5 整数权重分支与全并列早退（1.0）保持 `abs=0.0`——那些值精确可表示。
**量级极小的值用纯相对比较（AC 轮纪律），跨平台求和用相对容差，两端都不适用
绝对 epsilon。**

**④ 有修复就升级，不登记豁免。** pip-audit 的 45 个漏洞（pillow 35 / aiohttp 8 /
certifi 1 / otel-api 1）全部有上游修复 ⇒ 按 ci.yml 既定治理升级（lock 132 → 133
外科式增量，不用 `pip freeze` 全量重生成——venv 185 包与锁本就有既有漂移）；
chromadb 5 条豁免不动（上游仍无修复）。**豁免登记表只收「暂时无法修复」，
能修不修是把治理表当成垃圾桶。**

**⑤ 覆盖率读数有 ±1 行 / ±1 弧的跑批间噪声带。** 同树同命令两次覆盖率跑批：
19538/20052 vs 19539/20052、7150/7584 vs 7151/7584（cost_budget.py 在两跑间
99.35% ↔ 98.7% 翻转）——xdist 合并口径的既有抖动（BS 轮「两种口径」的余波）。
登记值取与既有口径逐位相同的抽样；±0.20pp 对账容差内波动不归因、不外推。
**「文档数字必须来自工件」与「工件数字有噪声带」并存时，登记口径 + 噪声带
必须同时写明。**

（BZ 轮归因路径：失败清单逐字取自 check-run 注解 API（ci.yml 诊断步骤的
`::error` 注解，公开可读、无需 admin）；fresh clone 模拟 = `git clone --depth 1`
+ CI 同环境变量；pip-audit 用 CI 同版本 2.10.1 同豁免清单本地复现。复现命令见
CI_RED_ATTRIBUTION_BZ_2026-10-23（分册已删除） §4。）

## 71. 附：BZ 轮补遗（2026-10-23）门禁判定必须由内容决定，不能由 checkout 的文件系统状态决定；豁免是登记项，不是默认放行

模型指纹门禁把「近 2 天 mtime 的 `benchmark_*.json`」当作新批次，而
`actions/checkout` 把所有工件 mtime 刷成当下——同一份工件在作者机上是「历史」、
在 CI 上是「新」。于是为 BY 测试契约入库的预指纹历史批次（2,219 B，无
`provenance` 块）在每次 checkout 上都被要求 `pinned=true`，而它永远不可能满足。
更早的「0 秒通过」也不是证据：那时顶层 `benchmark_*.json` 尚未入库，扫描面为空，
而空扫描面在语义上是合规状态（nothing to verify）。**「没跑」与「跑过且干净」
在门禁输出上同形**——这正是本系列从 BH 起一直收的那一族，只是这次它落在
门禁自己的判定输入上。

**① 判定输入必须与工件内容绑定，不能与机器状态绑定。** mtime 是文件系统元数据，
checkout / 解包 / 复制都会改写它；用 mtime 区分「新批次」在本地成立、在 CI 不成立。
本轮没有把口径改成按 `provenance` 判定（那会让所有无 provenance 的新批次一起
漏检），而是把「已知的预指纹历史工件」按名登记——**并把这条边界写进分册 §5**，
不假装口径已经统一。

**② 豁免登记表要能被审计，否则它就是静默放行。** 与 json-strict 的 `_ALLOWLIST`
同纪律：每条带理由、打印 `[EXEMPT]`、仍计入总数并单列「另有 N 个按名豁免」；
漂移检查三向（文件消失 = 豁免失去对象；已 `pinned=true` = 豁免不再需要；
不可解析 = 豁免不能把坏工件变成干净）。**漂移必须先于「无新批次」判定**——
登记项失效与扫描面是否为空无关，任何机器状态都必须可观测。

**③ 豁免只作用于登记的那一份。** 同目录另一份未锁定批次照常阻断（有锁），
条目数在测试里锁成 1：扩大豁免必须同时改测试，让扩张落在评审面上。豁免表
能兜住的是「登记项失效」，兜不住「把新批次加进表」——后者只能是评审纪律。

**④ 一个守卫没有直接读者，就等于没锁。** 首轮变异把 `_rel_key` 的
`relative_to` 根改错，全部锁仍绿：登记表漂移检查直接遍历登记键、不经过
`_rel_key`，而豁免锁的键又用同一个被改函数生成，两边一起漂。补「`_rel_key`
对绝对路径与仓库相对路径都收敛到登记键」的锁后整轮复跑（不是只跑该锚点）。
**「测试红了」也不一定是断言失败**：补遗的在途测试调用了从未定义的辅助函数，
2 例红 + `ruff` F821——测试自己没接上，和被测代码坏了，在报告面上都是「红」。

（归因与复现见 CI_RED_ATTRIBUTION_BZ_2026-10-23（分册已删除） §2.8 / §3.4 / §4；
变异工装 `scripts/tools/bz_mutation_verify.py`，12 锚点 + 1 中性对照。）

## 72. 附：CA 轮（2026-10-23）豁免登记只被查询、不被审计时，它就是静默放行；遮蔽量本身是一等读数

`check_artifacts_tracked.py` 的豁免表只有一处读者：`if name in EVIDENCE_DIR_EXEMPTIONS:
continue`。于是「这条豁免是否仍然需要」与「它到底遮蔽了多少未入库工件」两件事，
在整个门禁里都没有观察点。改前实测：16 条登记里 1 条目录已不存在、1 条 53/53 已全部
入库；其余 14 条遮蔽 **155 / 158** 个未入库工件，而门禁打印 `✓ 188/188 …引用链完整`。
**「没有豁免」与「豁免遮蔽了 155 个文件」在输出上同形**——这是本系列「读不懂 ⇒ 沉默」
落在豁免登记自己身上的一副面孔。

**① 豁免不是默认放行，是登记项；登记项必须自己可审计。** 与 BZ 补遗的
`_PRE_FINGERPRINT_EXEMPT` 同纪律，但多一层：BZ 只做了「三向漂移」（文件消失 / 已
pinned / 不可审计），CA 把漂移扩到登记的五种失效形态——目录不存在、目录已全部入库
（豁免不再抑制任何东西）、目录为空（不遮蔽任何工件）、不可读（不可复核）、登记名
不在扫描面内（`_scan_evidence_dirs` 根本走不到那条 `if`，豁免永不生效）。**「豁免
永不生效」和「豁免生效且干净」同样无声。**

**② 遮蔽量是一等读数，不是实现细节。** 通过时逐条打 `[EXEMPT] <name>: 遮蔽未入库
工件 h/total`，再打一行汇总；端到端锁解析这两行并与 `exemption_coverage()` 的重算值
比对——**披露不得与数据分叉**。只写「已豁免」的通过输出，让读者无法判断这张表是在
承载 3 个冒烟文件还是 155 个。

**③ 漂移判定必须与「扫描面是否为空」解耦。** 空扫描面（`experiments/results` 不在
检出环境里）在语义上是合规状态，但登记项是否失效与扫描面无关；把漂移挂在扫描结果
后面，等于让一个不存在的目录替所有登记作证。漂移在 `main()` 里与未入库清单并列。

**④ 删失效登记不改变判定，但删之前要证明「差为 0」。** 两条被删登记的移除前后门禁
输出逐字相同（`✓ 188/188`）：一条目录不存在（不在扫描面上）、一条 53/53 已入库
（本来就过「至少一个文件被跟踪」）。**「删掉一条不改变任何读数」正是它早该被删的
证明**，不是删得太随意的辩护。

**⑤ 新代码在「测试自己的加载路径」下也必须可导入。** 第一版用 `@dataclass(frozen=True)`，
而两个历史测试以 `spec_from_file_location` 动态加载模块却不登记 `sys.modules`——
Python 3.14 的 `dataclasses._is_type` 访问 `sys.modules[cls.__module__]` 得到 `None`，
`AttributeError`。**门禁模块的导入方式是被多个旧测试共享的契约**；本轮改用
`NamedTuple` 并把「无登记动态加载」锁成用例。变异的对应锚点（M16）证明这条锁会红。

**⑥ 继承态要在报告里分开写。** 同一跑里的 3 例红来自工作树中在途的 R05 改动与它
未对齐的旧 mock，不是本轮引入；覆盖率分母 +24 行也来自继承的 `src/` 改动。
「本轮零改动」只能用于本轮真的没碰的东西，且必须写明分母为什么动了。

（分册与复现见 GATE_WAIVER_STALENESS_CA_2026-10-23（分册已删除）；变异工装
`scripts/tools/ca_mutation_verify.py`，16 锚点 + 1 中性对照。）

## 73. 附：CB 轮（2026-10-23）成功语句的判定面必须与语句同宽；不可判的写路径只披露；零引用声明必须点名

`check_state_contract.py` 打印「136 个文件无未声明键读写」，而判定面只有就地赋值
（**2 键 / 11 站点**）与 `state.get/state[]` 字面读（57 键 / 353 站点）。LangGraph
的**规范写侧**——节点返回更新 dict `return {"k": v}`——实测 **45 键 / 95 站点**
完全在判定面之外，而该门禁 docstring 点名的 M14 / O35 静默丢弃事故正是这条路。
**「判过且干净」与「压根没看」在同一句成功语句下无法区分。**

**① 成功语句只能声明判定面覆盖到的东西。** 通过时追加四行披露：声明键数、三向覆盖
（读 / 就地写 / update dict 写）、未触及键的二分（有字面 / 零字面）、面外计数
（临时键 / 动态键 / 未声明键 / update dict 中不可归属的非声明键）。判定与成功/失败
口径一处不动——披露是加法，不是放宽或收紧。

**② 不可静态归属的写路径只披露、不判定，并把这条边界锁成用例。** 要判 update dict
就需要「哪些 dict 是状态更新」，而全仓 `return {...}` 里有 **898 个**键不在声明集，
绝大多数是辅助函数的普通 section dict；按「首参数名为 state」试判会把 `_build_*_sections`
整批误判。误报不能靠调阈值消除（辅助函数与节点签名同形），故只给 45 键 / 95 站点的
可见性，并用 `test_update_dicts_are_disclosed_not_judged` 锁住「不得顺手判定」。

**③ 零引用声明必须点名，不能计数摊销。** 118 个声明键里 35 个不在审计面；其中 34 个
在扫描面之外有字面（只是不在判定面），1 个全仓零字面：`failure_frequency_applied`。
它的声明注释写着「`_debugger_node` 写入 True」，实际 `_debugger_node` 只把生成的提示
文本拼进 prompt（`src/graph/debugger.py:501`），从不写该键；`None` 又被注释解释为
「开关关 / 非高频」——**「功能没开」与「功能开了但标志从未写入」在数据上同形**，
而按声明消费该键的实验分析只会读到缺省值。这条与特性开关治理里的「零代码引用开关」
同形（Code References / `stale-flag-detector`）：声明表要能报出「没人引用」。

**④ 「未触及」不等于「没人用」，判别只能是弱判据。** 二分依据是扫描面之外是否出现
带引号字面；文本级判据会把注释里的字面也算作出现，因此它只能支撑「零字面」这一强
结论，不能反推「有字面即有消费」。零字面一侧逐名列出，不并入计数。

**⑤ 新加的披露会进入被测文本——先划装置边界。** 首版实现把门禁 docstring 里的死键
字面与守卫测试的断言字面算作「别处有出现」，`untouched_nowhere` 由 1 变 0：
**门禁用自己的披露文本把自己的结论证伪**。凡要「点名」的披露都会污染「是否被提到」
的判据，修法不是改措辞，而是用 `_apparatus_paths()` 排除测量装置（本模块 + 直接
import 本模块的测试模块，模块级精确匹配）后再分类，并用两条锁固定（装置集合 +
面外文本不含死键）。

**⑥ 覆盖率同值要归因到测量面，不许含糊。** `coverage.xml` root `sources` 实测只有
`src/`，CB 改动全在 `src/` 之外，因此行 / 弧与 CA **逐位相同是结构性的**；同理，
「数字没动」也不能读成「没有改动」。与 CA 的「继承态 +24 行」相对：那里分母动了要
说明为什么动，这里分母不可能动也要说明为什么不可能动。

**⑦ 新类型沿用可导入性契约。** `ChannelCoverage` 与 CA 的 `ExemptionCoverage` 一样用
`NamedTuple`：模块存在不登记 `sys.modules` 的动态加载路径，`@dataclass` 在
Python 3.14 会 `AttributeError`。本轮把「无登记加载 + 取覆盖读数」锁成用例（变异
锚点 M16 证明它会红）。

（分册与复现见 STATE_CHANNEL_AUDIT_SURFACE_CB_2026-10-23（分册已删除）；变异工装
`scripts/tools/cb_mutation_verify.py`，18 锚点 + 1 中性对照。）

**⑧ DS 轮（2026-10-26）重登记——CLI 结果 dict 进入 update dict 计数。** 崩溃任务
结果与成功结果键集合同构后，`src/cli/app.py::_make_task_error_result` 直接返回的结果
dict 让 `coverage_threshold` / `max_iterations` 两个字面声明键被计入 update dict：
45 键 / 95 站点 → **47 键 / 99 站点**，未触及 35 → **34**（33 有字面 / 1 零字面），
未审计 44 → **46**。新增的 2 键 / 4 站点是 CLI 呈现层的普通结果 dict，**不是状态节点
写**——正是本节 ② 所说「普通 dict 与状态更新同形、不可静态归属」的已知噪声。按棘轮
契约（`test_real_repo_coverage_numbers` 数字变动即重跑普查并重登记），本轮只重登记
读数并把噪声来源写进门禁 docstring 与用例，判定面、成功/失败口径一处未改。同轮
`coverage.xml` 的 line / branch 分母因 `src/cli/` 改动而动，属正常非继承态。

## 74. 附：CC 轮（2026-10-23）mock 的输出形态必须是真实输出的形态；围栏提取不认 JSON 转义换行；"有调用"不等于"能成功"

19 面真实 LLM 覆盖扫里，`patch_resample` 是唯一"有 LLM 调用却结构上不可能成功"的面：
1 次调用、80 in / 80 out，而 `resampled` 恒 `False`。根因不在模型，在**回调与
prompt 的契约错位**——`DebuggerAgent` 的 system prompt 要求 JSON 输出，真跑返回
`{"root_cause":…,"patch":"```python…```"}` 信封；回调却把整段信封交给
`extract_code_block`，其围栏正则要求**真实换行**，而 JSON 信封里的换行是字面
`\` + `n`，匹配不到，回退分支把整段 JSON 当补丁返回。`safe_apply_patch` 也拦不住：
JSON 对象字面量恰好是合法的 Python 表达式（dict 字面量），只有
`check_naming_contract` 会因为缺少原模块级符号而拒绝。

**① 单元 mock 必须复刻真实输出的形态，否则测试面与生产面不同形。** 该回调的 5 条
降级路径用例全部把 `_call_llm_with_cache` mock 成裸代码块，于是"mock 的世界"里
围栏永远匹配得到，缺陷完全落在测试面之外。新增的回归锁用 `json.dumps` 构造**带
转义换行**的信封，锁的就是"真跑形态"这一层。

**② 提取器的失败是静默的，必须有第二道结构判定。** `extract_code_block` 匹配不到
围栏时返回 `text.strip()`，而不是空值或异常；调用方若不区分"真代码块"与"回退原文"，
就会把任意文本当成补丁送进后续校验。本轮不改提取器（回退语义被其他路径依赖），
而是在回调里先解信封，让回退只在**非信封**时发生。

**③ "调用次数 > 0"不能当作通路可用。** 修复前的读数 `calls=1` 看起来正常，
只有把 `resampled / success / new_code_has_fix` 一起读才能看出结构性失效；
覆盖报告据此把"有调用"与"能成功"分列，而不是用一个调用计数代替两者。

**④ 解信封只认 `patch` 非空字符串，边界必须登记。** 顶层数组、其他字段名、
多候选数组仍走原文提取并大概率失败——这条通路本轮只证明了真跑观测到的单一形态，
不能外推为"所有 Debugger 输出形态都已覆盖"。

（分册与复现见 PATCH_RESAMPLE_ENVELOPE_CC_2026-10-23（分册已删除）；变异工装
`scripts/tools/cc_mutation_verify.py`，3 锚点 + 1 中性对照。）

## 75. 附：CD 轮（2026-10-23）删除语料会让派生读数与锁判据同时失效；"规模下界"不是"内容不变"

本轮按用户指令把运行时与文档面收敛到「仅保留 DeepSeek 官方」，连带删除 **330 个入库结果文件**
（3 份批次 JSON + 327 份 trace——这 327 份里都有非 DeepSeek 模型的调用记录，留着等于让仓库继续
自称支持已被移除的 provider）。删除动作本身是干净的，问题在于**读数与锁都是对旧语料取的**：
删除之后，任何一次"照旧运行"都会给出与登记册不一致的数字，而任何一条"规模下界"断言都会因为
规模变小而假红。

**① 派生读数必须按存盘语料重算，并且改前 / 改后同表登记。** 受影响的读数：mutation×detection
表的批次文件数 **10 → 7**、detection 可测 n **605/658/571 → 556/609/571**、率 **13.06/1.67/48.86%
→ 14.03/1.64/48.86%**（分子不变、分母缩小——所以"率上升"不是改善，是分母变了）、trace 语料
**9086 → 8763**、span **129058 → 126408**、`gen_ai.usage.*` 属性 **27135 → 26166**。分层均值、
Δ均值、Pearson、Spearman 逐格不变：被删批次没有改变分层结构。把这些成对写进 CHANGELOG 与本册，
是为了让后续读者能分辨"读数移动"与"行为改变"。

**② "规模下界"不是"内容不变"——判据要跟着不变量换。** AB14 的
`test_protected_reports_not_rewritten` 原本断言 `SHA256SUMS` 有 ≥ 2000 行，用"登记表还算大"
来近似"受保护报告没被改写"。清理后登记表 1869 行，这条断言直接假红。换成**逐字节比对**——
解析 `SHA256SUMS` 拿到两份受保护报告的登记摘要，与盘上文件 sha256 直接相等——语义从"够大"
跳到"未改写"，更严，且不随语料规模移动。同理，AR/AQ 的文件数 / span 数 / 属性数是**精确等式**，
本轮按复测值重写并注明日期与成因（不是放宽：等式仍然是等式，只是常数换成了复测值）。

**③ 删除面必须区分"运行时支持"与"外部证据 / 防线"。** 三类是明确保留的：第三方**文献引用**
（论文、榜单、外部适配器数字——它们是外部证据，不是本仓的运行时能力）、**凭证脱敏拒绝名单**
（`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` 及编号变体——DeepSeek 经 OpenAI 兼容协议调用，删掉这些
模式等于关掉泄露防线）、以及**仍带历史模型名的 3 份入库工件**（改写即篡改证据，按"历史读数"
对待并登记）。这条边界如果只写"删掉所有非 DeepSeek 字样"，会顺手把防线和证据一起删掉。

**④ 删了工件，悬空引用就不是文案问题，而是可运行性问题。** 被删批次在文档里的引用要分两类
处置：**可运行示例**改指存盘批次；**历史叙述**原地补日期注记（"该批工件已于 2026-10-23 清理
删除，读数保留为决策登记"）。测试夹具里的合成文件名与 `DELETED_BATCHES` 元组不动——它们不是
归档引用，而是"历史批次已经不在"这一事实的锁。

（复现：`make mutation-det-correlation`；`SHA256SUMS` 校验 1869/1869；语料守卫三值
239 / 138 / 8216 不变。）

## 76. 附：CE 轮（2026-10-23）脚本执行口径 ≠ 进程内 import 口径；成功语句的分母必须自带口径

本轮把 `scripts/gates/check_model_fingerprint.py` 从「只判 `pinned is True`」补上两条可比性
围栏（别名与返回模型不符 / 别名已不被运行面支持）与四行 `[SURFACE]` 受检面披露，另新增 19 例锁
（35 → 54）、33 锚点变异工装（全红 + 中性对照 0 红）。过程中立了三条可推广的规矩。

**① 「测试里 import 得到」不证明「门禁现场 import 得到」。** 首版围栏在函数内
`from src.config.config_generator import COMMON_MODELS`：进程内测试把模块当文件加载、仓库根已在
`sys.path` 上，import 成功；而 `make model-fingerprint` 以脚本方式执行时 `sys.path[0] = scripts/gates`、
仓库根不在路径上 ⇒ `ModuleNotFoundError` ⇒ 别名对账整条退化成 `[SKIP]`。**54 例锁全绿，围栏在真实
使用现场一次都没跑过。** 处置不只是补 `sys.path.insert(0, PROJECT_ROOT)`：还补了一条用子进程跑真实入口、
断言 stdout 不含 `[SKIP]` 且含 `运行时模型集 ['deepseek-flash']` 的锁，以及两个锚点
（M24「不补 `sys.path`」、M11「alias 对账行删除」）。规矩：**凡门禁模块内从仓库根起的 import，
必须有一条以脚本口径执行的锁**——这与 CC 轮「mock 的输出形态必须是真实形态」同族，只是把对象从
被测函数的返回值换成了被测函数的**执行环境**。

**② 静默退化的形态是「少判」，不是「报错」。** `import` 失败返回空集合 + 成因，方向上是对的
（不冒充可用），但它产出的仍是 rc=0；如果打印侧不点名，「围栏跑过且干净」与「前提不成立所以没跑」
在退出码上同形——这正是 BH→BT 系列「不可读折成沉默」的门禁版本。所以 `[SKIP]` 必须带成因、
且**不依赖注册表的那条围栏照常生效**（有专门锁）。

**③ 成功语句的分母必须自带口径，且披露要落在每一条输出路径。** 门禁打印「通过：1/1 个受检工件」，
分母实际是「近 2 天 mtime ∩ 默认目录非递归」（实测窗口内 2 / 豁免 1 ⇒ 实检 1），而 benchmark 语料
在盘递归 **239** / 入库 **107** / 顶层非递归 **64**、结构面 **122 / 87 / 85**——两个数量级的差距在
输出里是 0 比特。规矩与 CB §73 连成一条：**分母要么与判定面同宽，要么把口径随句子一起打印**；
本轮把 `[SURFACE]` 四行同时接在成功、报红、空窗口、`--allow-empty` 四条输出路径上（M07–M10 各删一处
验锚点），因为只在一处打印等于把「干净」与「没扫」重新做成同形。附带一条口径诚实性：`入库 107` 是
`git ls-files` 的**索引**口径，与「在盘可读」差 7（上一轮尚未提交的删除），这个差要写进 docstring，
否则下一轮会把 107 读成 107 份可复核工件。

**④ 判据的外部权威要 import，不要复制常量。** 复制 provider / 模型名单的版本会在下一次运行面收敛时
悄悄失真，而本轮缺口②（别名不被支持）恰恰在 CD 轮把运行面收敛为单别名 `deepseek-flash` 之后才第一次
可判定——「合法集合」曾经模糊，本身就是这个缺陷能长期存活的原因。做法：权威源名字本身进输出
（`src.config.config_generator.COMMON_MODELS`），取不到时报三类成因而不是返回空集合。

**⑤ 披露不等于判定，也不等于覆盖。** 语料侧 `unsupported_alias` / `alias_mismatch_true` 只披露不判定
（历史批次不能重跑，判红等于改史）；窗口口径未扩大（2 份 `pinned=false` 仍在窗口外、非递归面外）。
把这两条写进登记册 §4 的边界行，是为了防止下一轮把「披露在场」读成「保证在场」。

（复现：`.venv/bin/python scripts/gates/check_model_fingerprint.py` 打印 4 行 `[SURFACE]` 且 rc=0；
`make model-fingerprint` 的 stdout 不含 `[SKIP]`；
`.venv/bin/python -m pytest tests/test_model_fingerprint.py -q` = 54 passed；
`.venv/bin/python scripts/tools/ce_mutation_verify.py` = 33 锚点全红 + 对照 0 红、collected 逐锚点恒 54、
墙钟 441s；`grep -n "alias_mismatch" scripts/gates/check_model_fingerprint.py` 在改前的门禁本体是 0 命中，
而写侧在 HEAD `experiments/run_benchmark.py:3838/3840/3852`。）

## 77. 附：CF 轮（2026-10-24）登记面的派生数字没有读者；指认权威源不等于权威源被读；清单要么双向要么承认单向

本轮新增 `scripts/gates/check_registration_consistency.py`：把登记册 §1 括号里 15 个「当前口径」数字
拆成自算权威（9 门禁面 + 2 静态面，现场复算）与 BASELINE 权威（`tests.passed` / `failed` / `skipped` /
`collected`，逐键回读），并判定分册清单双向覆盖、§2.2 编号连续、被引用工件的拥有者活性与本门自身接线。
另加 46 例锁、38 锚点变异工装。过程中立了七条可推广的规矩。

**① 手写数字要么由生成器写，要么必须被复算对账。** `已格式化` 一格 BQ 轮手写 **999**，跨 BR…CE 约 14 轮
无人复算；本轮在 HEAD 干净树复算得 **1037**，收口实测 **1050**——三代数字同时活在同一张表里，
而门禁不读它。全仓 grep 显示 `BASELINE.yaml` 的 `gates` 节在被写入的当轮就有 **0** 个 Python 读者。
规矩：登记面数字的作者可以是人，读者必须不是人；写进登记册的每一个数都要说出复算它的命令，否则它只是
一个装饰。

**② 指认权威源不是终点：权威源自己要有读者。** 登记册原文写着「权威口径 = `BASELINE.yaml`」，
这句话本身是可信的，但它指向的那一节从来没有被任何门禁读过——「有权威」与「权威被引用」是两个事实，
只有后者能让漂移变红。所以本轮把「被引用」也做成判定项：`check_owner_liveness` 要求声明里点名的
拥有者文件在盘、锚点在位、且仍挂在 `make` 链或 `ci.yml` 上。

**③ 清单要么双向，要么承认单向。** 盘→清单（每个分册必须在 INDEX 出现）本轮判定；
清单→盘（INDEX 点名的文件必须存在）由既有 `check_doc_links.py` 判，两处都不留空。
改前普查：在盘 **78** 份，zh §3.5 登记 **77** 行（漏 1 份，X 轮分册自 2026-10-19 起漏 5 天）、en §3.5 登记 **74** 行（漏 4 份）；本轮收口时盘 **79** / git 索引 **74**（差 5 = 五份尚未提交）。单向清单只能证明「写的时候数过」，不能证明「现在还一致」。

**④ 装饰性编号会被当计数用。** zh §2.2 的条目号在 18 条目上是 `[6…19, 20, 22, 21, 23]`——CC / CB 两行写反、缺 24，而读者会把末尾的「23」读成「已有 23 份评审」，实际只有 18 份。纯装饰的编号一旦被引用就成了计数证据。要么由生成器产出，要么判定连续性；本轮判连续性（逐条 +1），并把 CC/CB 对调、CF 落在 **24**（收口 19 条目，连续 6…24）。

**⑤ 解析子进程输出必须锚定摘要行。** `已格式化` 的权威值取自 `ruff format --check .` 的末行摘要，
但该命令在有 diff 时会把整段正文一起打到 stdout（实测 2100 字符），正文里完全可能出现
「2 files would be reformatted, 3 files already formatted」这种与摘要同形的句子——首版对整个输出做
全串 `search`，把当时的 **1047** 读成 **5**（报错方向对、口径彻底错）。`_summary_line()` 只取最后一条
非空行，配锁 `test_ruff_diff_body_is_not_read_as_summary` 与锚点 **M33**（`summary-takes-first-line`）。

**⑥ 「有人查」本身是需要被查的事实。** 本门最后判定自身接线：`invoked_by_chain` 在 `make_gate_deps` 展开出的
`gates:` 前置目标体内命中 `registration-consistency`，**或**在 `ci.yml` 文本内命中——两者皆断才红
（本地跑与 CI clone 跑任一路活着都算已接线）。
接线是本轮最容易「写完门禁忘记接线」的一步，而它恰好是①～⑤全部生效的前提。

**⑦ 无锁的披露读数会在收口之后继续漂移。** 括号外裸数字是「只披露不判定」的面，本轮三行〔当前口径〕落盘时门禁打印 **811**，
把终跑读数回填进 §1 三行之后同一处命令打印 **830**——而 830 没有任何锁（唯一的锁断言合成夹具「裸数字 1 个」）。规矩：
终跑与读数回填之后，凡引用过披露读数的地方都要复跑打印它的那条命令；改动就写成谱系（改前 788 → 括号落盘 811 → 终读 830），
不要留一个只有当时才成立的单点数。登记面自己也要被再读一遍：本轮三处把「代码里的判据」写成了记忆里的判据
（接线被写成三处缺一即红，实为 `make` 链**或** `ci.yml`；漏传 `root` 的症状被写成空索引，实为读到真仓 78 份而全绿；
M36/M38 的处置被写成拆判据，实为各补一条直接锁），全部由收口后逐条对回代码与分册才查出。详见分册 §6⑦。

（复现：`.venv/bin/python scripts/gates/check_registration_consistency.py` rc=0，stdout 打印 15 行 `[OK]` 逐项对账
与 6 行 `[SURFACE]`（3 行权威口径注记：门禁盘 30 / 索引 29、mypy 面未真跑、分册在盘 79 / 索引 74；
3 行判定面披露，含「括号外裸数字 830 个按历史快照叙述处理、不判定」——此数无锁、随 §1 任何编辑变动：
三行括号落盘时打印 811，终跑读数回填 §1 后打印 830）；
报红路径同样打印 3 行判定面披露在 stderr（专门一例锁 `err.count("[SURFACE]") == 3`）；
`.venv/bin/python -m pytest tests/test_registration_readers_cf.py -q` = 46 passed；
`.venv/bin/python scripts/tools/cf_mutation_verify.py` = 38 锚点全红 + 对照 0 红、collected 逐锚点恒 44、
墙钟 82s；改前复跑同一门禁 28 项红，其中 8 项是 BASELINE 缺键（含新增的 `tests.collected`）、
14 项是「未登记当前口径键」。）

## 78. 附：CG 轮（2026-10-24）判据按结构不按子串；「在场」不等于「同口径」；读者判据的松紧本身就是口径

本轮新增 `scripts/gates/check_invocation_caliber.py`：把 `make` 链与两份 workflow 的调用口径放进同一张表
逐项对账——调用面归属、跨面开关（按**有效值**）、阻断性三层、开关读者活性四类、登记表与分母恒等式自校验。
另加 66 例锁、70 锚点变异工装、15 条机器可读登记表。过程中立了九条可推广的规矩。

**① 判据按结构，不按子串——一条注释可以造出一个已进基线的数。** CF 门的非阻断判据对整个步骤文本做
子串搜索，于是 ci.yml 注释里那句「改 `continue-on-error: true`」被当成当前键：**非阻断 3 / 阻断 26**（子串）
vs **2 / 27**（结构），而 3 已经在 `BASELINE.yaml` 与登记册 §1 里。规矩：任何「从 YAML / Markdown 里找证据」
的判据必须先声明它在读**哪一层**——键层（缩进、注释、层级）还是正文层；把两层混在一次 `search` 里，
读者以为自己在看结构，实际在看文本。同一病灶的第二处是调用点计数：全文正则 **32** vs 只数非注释行 **30**。

**② 注释不是登记面。** 收口时我把 `non_blocking_steps` 等新值只改在 BASELINE 的**行尾注释**里，键值没动，
于是本门的交叉核对继续报「= 3，结构复算 = 2」。这与本轮病灶 ①② 完全同构：只有键值本身会被复算，
写进注释的数字等于没写。同理，「两处理由只写在 Makefile 与 perf.yml 的注释里」正是跨面开关不对称能长期
存活的原因——**注释解释过去，登记面约束现在**。

**③ 门禁「在链上」和「以同一口径在链上」是两个判据。** CF 门答前者（在场性），本族缺的是后者：同一脚本
在 `make gates` 与 ci.yml 上的命令行从不对账（所有面两两比得 **3** 处不对称，只比一对得 **1**——
两两全集才是判据面）；`check_prompt_artifacts` 不在本地链上而 CI 又裸跑不带严格档，于是「已接线」为真
而「强制」为假。规矩：接线判定若用 OR（本地链**或** CI 任一即算活着），就必须另判「两侧口径是否相同」，
否则 OR 语义会替缺席的一侧说谎。

**④ 「不阻断」有三层，最后一层是 shell。** GitHub Actions 把 `continue-on-error` 定义成步骤级**属性键**，
社区实践把「步骤级 `continue-on-error: true`」直接列为风险——被抑制的步骤让工作流看起来是绿的；
Bash 的 `set +e` 则是关闭 errexit **对后续命令一直生效**，要恢复须显式 `set -e`，而被 `if` / `&&` / `||`
测试的命令其非零退出本就被忽略。本轮首版只认「与门禁同一行」的 `set +e`，M05/M67 双双存活——
**区块级写法是文档里的标准写法，漏掉它等于把最常见的兜底放过**。补状态推进后，`set -e` 回补之后跑的门禁
仍算阻断，这条方向性判据单独有锁（d04/d05/d06）与锚点（M67/M68）。

**⑤ 读者判据的松紧本身就是口径。** 「谁传这个开关」若允许「文件里出现过这个 token」回答，宽松规则得
**52 有锁 / 0 无读者**，收紧成「同一文件既出现该开关、又点名这道门」才露出 **33** 条从未有读者的开关。
「0 条无读者」听起来比「33 条」干净，其实是把判定面取消了。规矩：分类判据要同时登记**两档松紧的读数**，
并让读者集合可复算（本轮用 `_reader_index` 扫 `tests/**` 与 `scripts/`+`experiments/`，**排除** `scripts/gates`
以免门禁自己的 docstring 成为自己的读者）。

**⑥ 判据档记红、呈现档记数；分母恒等式负责逼出占位值。** 71 个声明开关里，改变退出码语义的那一档
（`--strict` / `--verify` / `--allow-empty` / `--list` …）无读者必须红，只缩范围或改呈现的那一档只登记计数——
一律记红会把人推去放松判据，一律不记红等于没判。本轮 `passed_flags` 一度被写成占位 **71**（把声明数抄成
传过数），正是 `声明 = 传过 + 代码锁 + 登记 + 判据档 + 呈现` 这条自校验把它逼回 **14**。

**⑦ 一条锁看似覆盖，不代表它碰到了实现。** M59（§1 同名行折叠 `setdefault(...).append(...)` → 后者胜）
在第二轮仍存活：e16 造的两行标签**不同**，字典本来就有两个键，折叠与否都判得到。补 e18（标签逐字相同、
漂移放在**前一行**）才咬住。这是「红数扇出 ≠ 判据数」的反面：断言里出现了关键词，不等于断言执行了那条分支。

**⑧ 改前实测必须绑定一棵可重建的树。** 门禁 docstring 首版写「①~⑩ 取自同一棵未提交树」，但 ⑥ 的在盘 **30**
要求那棵没有本门脚本，⑦ 的声明 **71** 要求那棵**有**——一句读起来自洽的话把两个不同分母焊在一起，
下一轮照它复算会永远差 1 条。实做两棵树（改前树 = 移除本轮四个新文件并回退接线：69 / 31 / 判据档 **9**；
中间态树 = 改前树 + 本门脚本：71 / 33 / 判据档 **10**）后每个数都落位，差值恰为本门自身的 `--list` 与 `--quiet`。
规矩：改前读数要么全来自一棵能被脚本重建的树，要么逐行标注它取自哪一棵；分册 §4 C 段给出构建脚本，
任何人可复跑。（复现：`.venv/bin/python scripts/gates/check_invocation_caliber.py` rc=0，stdout 打印 39 行 `[OK]`
（13 项调用口径 + 13 项 BASELINE 交叉核对 + 接线 / 归属 / 阻断各项）与 6 行 `[SURFACE]`（3 行判定面 +
3 行口径注记，其中「判据归属」那一行明写同一个数由本门与 CF 门两条独立实现复算）；
`.venv/bin/python -m pytest tests/test_invocation_caliber_cg.py -q` = 66 passed（单跑 3.46s）；
`.venv/bin/python scripts/tools/cg_mutation_verify.py` = 70 锚点全红 + 中性对照 N01 0 红、collected 逐锚点恒 66、
`# mutation:` 残留 0、墙钟 424s（单进程串行口径）；改前实测的两棵树由分册 §4 C 段脚本重建，
⑥ 与 ⑦ 的分母差（30 vs 31 在盘、69 vs 71 声明）即本门自身是否在盘。）

**顺带收口的存量面（本轮量到、就地补齐，不在上面八条之内）**：BP §6⑤ 立的粗体配对口径是「单逻辑行 + 剔除行内代码后看奇偶」，
并按它登记过六份登记面「全部为偶、当前零缺陷」。本轮把同一条判据从**聚合档**挪到**结构档**——按 `此前 **` / `Previously **`
切出轮次段、要求每段在自己内部配对——量到 **15 处**段内为奇（`README.en.md` 2：BO 43 / BN 11；`docs/INDEX.en.md` 3：CB 1 / BO 43 /
BN 11；`docs/INDEX.md` 1：CB 1；`CHANGELOG.md` 1：CD 13；`CHANGELOG.en.md` 4：CD 11 / BP 47 / BO 43 / BN 11；
`docs/PROJECT_STATUS_REGISTER.md` 4：CG 49 / CF 33 / CE 25 / CD 31）。形状学要点：**BO 段 43 与 BN 段 11 各自为奇、成对落在同一条
整行里**，所以整行读数一直是偶——聚合口径把两处错配读成零处，与 ①（子串 vs 结构）、⑤（读者判据的松紧）是同一个失效方向：
判据切得越粗，缺陷越能在读数里活着。处置只补配对标记、一个字内容不改；复算后八份滚动行「奇段」为空。
同批否证一句既有登记：「登记册每轮 3 个标记、奇偶逐轮翻转」——3 个 / 段本身就是加粗跨段延续，不是写法（该文件自己的老写法是
4 个 / 段）。未收口：配对判据仍无门禁，做成门禁要先定义可机读口径（哪些行算单逻辑行、`>` 续行与表格单元怎么算、`__` 与 `**`
是否同族），口径没定义就跑第一版会把几百行合法跨行粗体报成红，重演 ①。复算命令见 CG 分册 §4 F 段。

**⑨ 终跑抓到的写侧错字，位置就在本轮刚写的登记面里——「预登记跑绿」不构成「终跑绿」的证据。**
CG 的第一次终跑停在 `test`（rc=2，1 failed / 12649 passed / 5 skipped / 223.18s，其后 14 个目标一个没跑），报红的不是本轮新
判据而是既有表格完整性锁 `test_live_docs_have_zero_content_loss_rows`：GFM 在表格里**连行内代码段里的竖线也照样切格**，
于是登记册 §1「调用口径」那行在 3 列表头下被读成 **8 格**（5 条竖线来自 `` `ls … | wc -l` `` 与两处 `` `||` ``）、§4.1 的 CG 边界行被读成
**4 格**（我把「本轮落地」那句写成了第四列）。处置：5 条竖线转义、1 处误写的列分隔改 prose，复算活文档丢格行为 **0**、
该锁 29 例全绿。三条规矩：**一**，登记文本在预登记跑之后才落盘，所以两步都不能省，收口顺序不是冗余；
**二**，同一张表格行有两个正交判据（粗体奇偶 vs 格宽），扫过其中一个不等于表格面收干净了；
**三**，格宽判据的判定面只含「被 GFM 认作表格的行」——登记册按围栏感知普查有 **21** 个 `|` 块、其中 **14** 块（**120** 行）
没有紧邻的表头/分隔行（每行之间空了一行，GitHub 渲染成带竖线的段落），这 120 行**永远不会红**，
且删掉其中一处空行也不会让它进入判定面（并入的那块同样没有表头）。规矩：判据红/绿之前先问「它有没有在看这一块」。

## 79. 附：CH 轮（2026-10-24）「受检面 = N」必须为「N 里某个成员读不到」配一条红；一条断言只能钉一行；dest 活性与读者活性是两个判定量

本轮新增 `scripts/gates/check_flag_effect.py`（553 行）：把「命令行上传了这个开关」与「这个开关在源码里接了线」
拆成两个判定量——CG 判读者活性，本门判 dest 活性，共用同一个 `(门禁, 开关)` 分母、两条独立实现各自复算再对账。
另加 99 例锁、75 锚点变异工装、两条写侧接线、BASELINE `flag_effect` 节 9 键。过程中立了九条可推广的规矩。

**① 每写一条「受检面 = N」的披露，就要为「N 里某一个成员读不到」写一条红。** 本门首版的循环里是
`if src is None: continue` 与 `except SyntaxError: continue`：一个进了 `disk_scripts` 分母、却读不到
`scripts/gates/<stem>.py` 的门禁，对全部判据的贡献是 0 且**不留痕**；语法坏掉的源码被折叠成「没有 argparse」，
与真没有开关的门禁同形。于是 `[SURFACE]` 那句「在盘门禁 32 道逐 (门禁, 开关) 复算」对那一道门是假话——
**披露是均值，不是判据**。这是 BH→BT 那一族「不可读即沉默」的形状，而它长在本轮正在给别人判活性的那门身上：
首轮变异 M38 存活才把它逼出来（同批补 M76 与两档 fail-closed 各一例锁）。规矩：不可读、不可解析、缺席，
都必须是一档显式的红，不能退化成「本次没看到」。

**② 一条断言只能钉一行。** M68 删的是通过行里的数字，而锁断言写的是
`assert f"死开关 {counts['dead_flags']}、代理开关 {counts['proxy_flags']}…全为 0" in out`——同一段文本
**同时出现在 `[OK]` 行和通过行**，`in out` 由 `[OK]` 行满足，于是删掉通过行的数字没有任何断言变红。
这不是等价变异（等价的意思是「行为逐字不变」），是**断言歧义**：`in out` 证明的是「这句话在某处出现过」，
不是「这一句还在」。改成三条各自钉死（`[OK]` 行 / 通过行的数字段 / 收口句「四态分母自校验成立」）后 M68 红 1 例。

**③ 「无读者 0」这类绿可以由 token 命中撑起。** CG 判定四把「调用面出现该开关」算作读者，于是
「判据档无读者 **0**」为真；而改前实测有 **2** 条判据档开关的 `dest` 在整个模块从不被读（`--warn-only`、`--verify`），
且**都被 ci.yml 真实传入**。「有人传它」与「它改变行为」之间还差一层 dest 活性——凡遇「活性/覆盖率」类绿数，
先问它是**哪一层的活性**：在场、被传、被读、被读后真去选分支，是四件事。

**④ 代理态的意义是「保证来源不在自己身上」，不是「现在错了」。** `checksum_results` 的 `--verify` 与 `--write`
同处 `required=True` 的互斥组，组内兄弟被读 2 次、它自己被读 **0** 次：今天的行为与按它调度**等价**，
但等价性由那个组担保。一旦有人摘掉 `required=` 或往组里加第三个模式，它立刻和新模式一起落进 `else` 分支——
命令行写着「校验」，跑的是别的。所以本轮用**四态**（活 / 代理 / 死 / 不可判）而不是「活/死」两态，
并让 `声明 = 四态之和` 成为自校验；把代理写成死会丢掉风险方向，把代理并进活则等于取消判定。
两态都记红、都不给豁免，修法要么让 dest 真去选分支，要么删掉开关。

**⑤ 等价区要写清单，不要用锚点凑数。** M06 把声明准入的 `--` 前缀过滤放松成「任意字符串 token」，跑出 **0 红**：
`_flag_of` / `_dest_of` 各自还要求 `--` 前缀，两条都返 `None` 就被 `if flag and dest` 丢掉——不进任何数、
任何输出、任何红。它与 CG 轮 `_locked_flags` 的 `if flag in specs` 是同一处置：**记进等价清单、删锚点不删代码**。
本轮工装 docstring 连同 M06 共列 **6** 处逐一核对过的等价区。这条清单本身就是产出：它说明「哪些代码删了也没人发现」，
而这类地方恰恰是下一轮最容易长出新 bug 的地方。

**⑥ 崩溃式扇出 ≠ 锁定度。** 最大扇出 M53（把 `counts` 初始化里的 `me_groups` 键摘掉）红 **32** 例，
但其中绝大多数是 `KeyError`——凡调用 `judge_effect` 的用例都被击穿。它证明的是「32 例都执行到 `judge_effect`」，
**不是**「32 例都断言了 `me_groups` 这个值」；真断言那个值的只有三条锁。红数是扇出，
读红数的人必须再问一层「红的是断言还是异常」，否则一个键名笔误看起来像整面被锁。

**⑦ 反子串判据的第一次误用，受检对象是写它的人。** `_escape_reads` 首版按子串搜 `vars(args)`，
于是把 docstring 里**讲**这个写法的门禁判成不可判——第一个命中者就是本门自己（docstring 第 ④ 行就写着这些字面量）。
锁 `test_docstring_mention_is_not_an_escape` 当场红。凡「从文本里找证据」的判据都得先答：
我读的是**结构层**（AST 节点、键、缩进）还是**文本层**（子串、正则）？拿子串当结构，判据就会把「提到过」读成「做过」——
这与 §78① 是同一条规矩的第二实例。

**⑧ 静态判据必须登记自己的误读方向。** 本门的读计数是「排除声明行区间 + 正则」，不是数据流分析：
注释里的 `args.x` 会被算成一次读 ⇒ 判成**活**（假绿方向），而挤进声明同一行的使用会被漏读 ⇒ 判成**死**（假红方向）。
本轮按分册 §4 G 段普查「只被注释命中的活」= **0** 条，所以现树 73 条「活」无一靠注释撑起——但这条只能靠纪律复算，
没有判据。规矩：判据放松或收紧时，把「哪种形状会被误读成好结果」写进边界，并且当场量一次它的现值。

**⑨ 不设豁免表是一项口径选择，不是省事。** ⑤ 那类「help 自述与默认行为一致」的装饰性开关，
如果给一张豁免表，等于把「没人接线的开关」变成可申请的常态，下一轮的「死开关 0」就变成「登记得足够多」。
本轮因此**只接线或删除**，登记表一行未加；对照 CG 轮「33 条呈现档逐条豁免会把登记表变成橡皮章」是同一条顾虑。
（复现：`.venv/bin/python scripts/gates/check_flag_effect.py` rc=0，stdout 16 行 = **10** 项 `[OK]`（1 项开关有效性 +
9 项「本门复算 == BASELINE == §1」三处同值）+ **3** 行 `[SURFACE]`；`--list` 打印 **73** 行逐项表且不判定；
`.venv/bin/python -m pytest tests/test_flag_effect_ch.py -q` = **99 passed**（单跑 1.82s）；
`.venv/bin/python scripts/tools/ch_mutation_verify.py` = **75 锚点全红 + 中性对照 N01 0 红**、collected 逐锚点恒 **99**、
`# mutation:` 残留 **0**、墙钟 **334s**；改前那两条按分册 §4 A 段用 `git show HEAD:` 重建 HEAD 版本源码后
`flag_effect_map` 复算，`--verify` 落「代理」、`--warn-only` 落「死」；现树八数（在盘 32 / 有 argparse 25 / 声明 73 /
活 73 / 代理 0 / 死 0 / 不可判 0 / 互斥必填组 1）由本门、CG 门与 §1 行三处独立给出。）

## 85. 附：CQ 轮（2026-10-25）没人看的红等于噪声；固定阈值先归因到映射面；版本也是一种口径

**① 定时作业的红没有读者，就只是噪声源。** `mutation.yml` 自 2026-10-19 首次运行即红
（阈值步 rc=1），full patrol（report-only）全绿；`perf.yml` 此前连续三次红。两者同一形状：
**红的是判据步，绿的是报告步，而没有人看原因**。判据：任何 schedule 作业的红要么在
CHANGELOG 有一条归因、要么有issue；否则它训练出来的只是"忽略"。本轮把"上线即红"当缺陷
处理，而不是当背景。

**② 固定阈值的红，先归因到"哪个函数的测试没进门禁的映射面"。** 本地按作业原样复现
**0.7467 < 0.85**（env 40/55 = 0.7273、atomic 16/20 = 0.8000）。根因不是阈值：
`postprocess_warn_seconds`（2026-10-18 新增）的测试不在 `--test-map` 面里——自动发现只匹配
`test_<stem>.py`，**新函数写在别的文件名下，门禁永远看不见**（15 个 env 存活体里 10 个落在
该函数）。补 21 例口径/边界测试后 **68/75 = 0.9067** 转绿，**阈值未动**。反例判据：若先调低
阈值，"新代码没有测试"就被永久合法化，而分数还会看起来"恢复了"。

**③ 等价变异体是分母噪声，必须按名证明而不是按感觉豁免。** 剩余 7 个存活体里 3 个可证明
等价：`os.path.dirname(os.path.abspath(...)) or "."` 的 `"."` 在 abspath 语义下**不可达**；
对已存在的 fd 而言 `os.fdopen(fd, "x")` 与 `"w"` **语义相同**（本机实测写出成功）。两条都
写进 `docs/design/self_mutation_harness.md` §9.1，**未声称等价的 4 条继续披露**——
「等价」是一个需要证明的谓词，不是一个可以用来让分数好看的标签。

**④ 版本也是一种口径。** 外部读数登记册的 `kim2026scaling` 行把 v2 摘要的 R²=0.524 与 v3 的
260 配置混排、出处只写"v1…v3"；「版本冲突」注还把「260 配置 / 6 基准」判成二手博客的错、
把「180 / 4」当成一手——方向反了。一手复核三版（v1 / v2 / v3 摘要 + v3 全文）：
v3 = **260 配置 / 6 基准 / R² 0.373（0.413）**；180/4 是 v3 全文里"带完整成本追踪的子集"；
0.524 只在 v2；45% / 17.2x / 4.4x / −39%…−70% 在 v3 全文仍在。处置：按版本拆行、正文改
"260 over six benchmarks（180 带完整成本追踪）"，行级锁新增**「只以 arXiv 标识为出处的行
必须带且只带一个版本」**（变异验证：改回旧写法 ⇒ 1 例红）。

**⑤ 同族位次**：CM「路径存在 ≠ 数字在工件里」→ CJ「set 语义吞掉重复登记」→ CP「摘要缺席
≠ 原文缺席」→ CQ「版本缺席 ≠ 同一版本」。四者的共同形状是**把一个坐标压成另一个坐标**：
路径/集合/摘要/版本各自都不是内容本身，而判定必须落在内容那一层。

（复现：`.venv/bin/python scripts/tools/self_mutation.py --files src/utils/env_utils.py,src/utils/atomic_io.py
--workers 2 --max-mutants 60 --fail-under 0.85 --test-map …` = **0.9067 / rc=0**；
`.venv/bin/python -m pytest tests/test_external_readings_rows.py -q` = **46 passed**；
`.venv/bin/python scripts/tools/audit_paper_numbers.py --strict` = rc=0、223 声明 / 211 SRC。）

## 84. 附：CP 轮（2026-10-25）「摘要里没有」不是「原文里没有」；索引缺席不是事实缺席；读数与引文必须是同一句话

**① 两列之间没有判据，就等于两列各自为政。** `docs/study/EXTERNAL_READINGS_2026-10-25.md`
每行是 `| 键 | 读数 | 原文表述 | 出处 |`。旧口径下没有任何判定读「读数」与「原文表述」的关系，
于是两行读作「已登记」而实际没有引文支撑：

| 行 | 缺陷形状 | 实况 |
|---|---|---|
| `shu2026agentworld` CCE 0.320 | 「读数」是全文数字，**「原文表述」抄的是摘要里的指标定义句**（摘要不含 0.320） | 读数出自全文 §3 / Table 2 |
| `tufano2026specops` 0.0352 / 0.0034 | 「原文表述」写成自指 `McNemar p-values quoted above` | 两个 p 值在本行没有任何逐字引文 |

两行都通过当时的全部门禁——**没有门读这两列的关系**，与 CJ 轮「登记面可以没有读者」同族。

**② 一手核验里存在两种「缺席」，都不能外推成「不存在」。**

- **摘要缺席 ≠ 原文缺席**：0.320 不在 arXiv 摘要，但在全文 §3 与 Table 2
  （"CCE ranges from 0.125 (DeepSeek) to 0.320 (Gemini)"）；附录 Table 6 给跨 judge
  稳健性（0.320 / 0.338 / 0.330）。摘要级检索只能回答「摘要里有没有」。
- **索引缺席 ≠ 事实缺席**：OpenReview 以标题检索无记录，但 arXiv 元数据的 Comments 字段写
  "Accepted at COLM 2026"（作者提交的元数据），项目主页同址声明。处置 = 书目仍以
  `@misc` + eprint 登记、**不写 `booktitle`**（单一来源不生成正式会议条目），正文按 v1 引用，
  并把两个「查不到」分别改写成「哪一层查不到」。

**③ 判据：把「同一句话」变成可执行的行级锁。** `tests/test_external_readings_rows.py`
（**42 例**）五条判据：多位数与小数必须在同行「原文表述」里逐字出现（千分位逗号不计）；
引文不得自指；引文必须是带引号的抄录；英文数词（`ten` / `thirteen`）按名豁免且
**豁免表只允许变短**（死条目即红）；**登记册按文件名发现且必须恰有一份**——新开一份
登记册时锁当场红，不会出现「锁还在读上一代、新登记册无人校验」的静默过期。变异验证
（原字节还原）：

- 把 CCE 行改回摘要定义句 ⇒ **2 例红**，断言逐字给出 `读数 ['0.320','0.125','0.320']
  在本行「原文表述」里找不到——读数与引文不是同一句话`；
- 把 p 值行改回 `McNemar p-values quoted above` ⇒ **4 例红**（数字缺失 / 自指 / 非引文 / 豁免对账）。

**④ 论文侧同轮补齐三处 SRC 落点**（导言 zhao 两行、导言 konstantinou 行、RQ4 tufano 行）：
`paper-audit --strict` 读数 **223 条声明 / SRC 覆盖 205 → 211（91.9% → 94.6%）/ 数字存在性
核实 9 → 12 / 不可判 6 → 3 / 查无 13（披露：撤回世代与派生量）/ 引用无效 0**。三处「不可判」
全都只是 SRC 注释落在 ±12 行窗口之外——**「不可判」不是可以长期挂账的桶**，补注释即转「核实」。
同轮改正文两处措辞：`peaks at 0.320` → 「四模型区间 0.125–0.320、最佳模型 0.320」（原文未主张
峰值）；`these seven studies` → `eight`（同段实际引用 8 篇）。

**⑤ 同族位次**：CM「路径存在 ≠ 数字在工件里」→ CJ「set 语义吞掉重复登记」→ 本轮
「摘要/索引的缺席被当成事实缺席」。三者共同形状是**把「我没看到」写成「它不存在」**；
三次修复都不是「更小心」，而是给两层之间加一条可执行判据。

（复现：`.venv/bin/python -m pytest tests/test_external_readings_rows.py -q` = **42 passed**；
`env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND`
后同命令需 `--basetemp`；`.venv/bin/python scripts/tools/audit_paper_numbers.py --strict` = rc=0、
末行读数见 ④。）

## 83. 附：CL 轮（2026-10-25）CI 步骤顺序是树状态的一部分；归因面自身会骗人

**① fresh clone 验证必须回放树变异步骤。** BZ 轮的 fresh clone 闭环（31 红 → 0 红）验证的是
「干净检出的树」；CI 的树在 pytest 之前被「Generate static-check snapshot」步骤写入
`docs/history/static_report_<日期>.md`——该文件计入 ruff 格式化面（+1），登记门禁
（由 pytest 内两条真树锁执行）复算 976 ≠ BASELINE 975 ⇒ CI 三档全红而本地全绿。
**本地绿与 CI 红的差异从来不只是代码，可以是步骤顺序造成的树状态差。** 两条规矩：
(a) 任何「往树里写文件」的 CI 步骤必须排在所有读树判定步骤之后（含 `if: failure()` 的
诊断重跑——它同样执行真树锁，快照在盘会让它误报）；(b) fresh clone 验证要么完整回放
CI 步骤序列，要么至少回放其中的树变异步骤。

**② 归因面自身会骗人：锚定行首的 grep 漏掉带前缀的失败行。** 诊断步骤
`grep -E '^(FAILED|ERROR)'` 在 xdist（`-n 4 --dist loadfile`）下漏捕 `[gwN] FAILED ...`
行 ⇒ 3.14 档输出「无失败用例行，可能是收集错误或崩溃」的假象（真实失败与 3.12/3.13
同族）。**一个只覆盖部分输出形态的捕获器，会把「没抓到」报告成「没发生」**——与
MEASUREMENT_INTEGRITY 全册同一条主线的第 N 个实例（折叠成最 favorable 值）。
处置：锚 `(FAILED|ERROR) tests/` 而非行首。

**③ 步骤顺序是可锁的。** 回归锁 = 断言快照生成步骤在 ci.yml 里的序号大于 pytest 步骤
（`tests/test_registration_readers_cf.py` 新增 1 例；变异验证：把两步换回旧顺序 ⇒ 锁红）。
顺序类不变量没有自然读者——YAML 不会因为排错而语法失败，只有锁能让它红。

## 83. 附：CM 轮（2026-10-25）「路径存在」不是「数字在工件里」；「没清单」不是「跳过」；登记面自己也会把两件事折成一件

**① 可追溯率 100% 可以是「每条数字都有一条 SRC 注释」，而不是「每条数字都在所指工件里」。**
论文附录 E 的成本表（26,114.9 tokens/task、$0.025885、35-of-261）来自**已撤回**的 261 行池
（`emse_stats_extensions_20261021`，commit `d5bda23e`），SRC 却指向在盘的
`emse_stats_extensions_20261025/`——该工件只有 n=20/36/41 的单批臂，**一条也对不上**。
`paper-audit --strict` 全程绿，因为它只判路径存在。**存在性冒充内容**，与代码侧
「字段写了没人读」「状态通道写了没人读」同族，只是发生在论文面。
处置：论文改 historical + 落点撤回索引表 W-1（冻结原值）+ `// SRC-CHECK: strict`；
审计器新增块级数字存在性判据。**边界**：p 值 / CI / z 常数是派生量，不字面存盘，
只作披露——判据按**块**（一段/一表）判「一条都不在工件里」，不按条判，否则会把
派生统计量全部误杀。

**② 「没清单」被读成「跳过」，完整性就在 0 份受检文件时也是绿的。**
6 条校验清单里 5 条目录已撤回、唯一在盘目录没有 `SHA256SUMS`，报告输出
「0 通过 / 0 失败 / 6 跳过」——三个数都在描述一件从未发生的事。
四态化后（`ok` / `FAILED` / 在盘无清单=FAILED / `absent` 披露）实测 8 目录 / 401 文件通过。
**「缺席」与「未检」必须分开**：前者是事实（目录被撤回），后者是缺陷（有东西却没清单）。

**③ 登记面的一行也会把两个事实折成一个。**
ADR-0036 的 A5 ① 写「fixed 臂 53/261 行无 token 记录」，实测是两个不同事实：
fixed **材料**缺口 53/261（影响过红机制分析上限 69/88，`CHANGELOG.md` 2026-10-13 条）
与 df 臂 **token 记账**下界 35/261（`STATS_EXTENSIONS.json` 的 `usd_note`）。
发布判据自己折叠了两个分母，说明「写进登记面」不是终点——登记面也要有读侧。
处置：ADR 加 dated errata，论文两处分别披露（Threats / 附录 E caption）。

## 83. 附：CN 轮（2026-10-25）生成式排版工具的验收必须在**渲染结果**上做；换权威源必须同时换审计对象

**事故形状（两件，同一根因）。**

① CM 轮的投稿稿由 `paper/typ2tex.py` 从 Typst 生成。验收只看三件事：编译退出码 0、
「0 个未定义引用/文献」、页数 52。三条都满足，于是判「投稿版就绪」。CN 轮改用原生
LaTeX 时把 PDF 抽成文本，才发现生成器把 **20 处 `// SRC:` 溯源注释当正文印进了 PDF**
（表 3 图注里直接印着 `// SRC: b1_lite_20261025/`，插在 "(single seed, 50 tasks per
cell…)" 中间），另有 **22 处 Typst 列表标记 `+ `/`- ` 原样输出**、**2 处图注被内嵌
SRC 片段切成病句**、**5/19 张表溢出页宽（最重 215pt，sha256 列被裁）**。

为什么退出码看不见：这些都不是 LaTeX 错误。`//` 在正文里是合法字符，`+` 是合法字符，
超宽表格只是 overfull hbox 警告——**生成器把「源语言里是注释/标记」的东西降级成了
「目标语言里是内容」**，编译器没有任何理由报错。

② 同期还发现：审计器（`audit_paper_numbers.py`）写死读 `paper/draft.typ`。若只把权威源
换成 `manuscript.tex` 而不改审计器，`--strict` 会继续对着旧稿报绿——**审错文件比不审更糟**，
因为它把「没审」包装成「审过了」。

**处置（可复用的判据）。**

1. **渲染面验收**：生成式排版（Typst→LaTeX、Markdown→PDF、HTML→DOCX）的验收必须包含
   一次「产物文本抽取 + 源语言记号黑名单」检查。本轮的实测判据：PDF 文本中
   `// SRC` 出现次数必须为 0（唯一白名单是真实 URL `https://`），`^+ ` / `^- ` 行首
   标记必须为 0。实测 20→0、22→0。
2. **换源必换审计对象，并用测试锁住**：`select_draft()` 显式实现「显式指定 >
   `tex/manuscript.tex` > `draft.typ`」，`test_latex_manuscript_is_audited_by_default`
   构造「两份稿同时存在」的合成仓，断言审计读的是 `.tex`。没有这条接线锁，
   选稿优先级只是一句注释。
3. **注释语法要跨语言对齐**：`// SRC:` ↔ `% SRC:`、`\%` 归一化、`\citet` 引文覆盖、
   `\_` 路径反转义（不转义会产出 **30 条假红**）、`26/50` 这类读数注解要排除在路径校验外。
   每一类都补了测试，共 6 例。
4. **排版也要有量化上限**：表格溢出从最大 215pt 降到 91pt（改成 booktabs + 条件缩放
   `\resizebox{\ifdim\width>\linewidth\linewidth\else\width\fi}{!}{…}`），
   剩余溢出全部来自正文里不可断的长 token（`t_round_..._20261018`），已如实登记在
   `paper/tex/README.md` §6，不再声称「排版无告警」。

**教训一句话**：编译器只保证「语法合法」，不保证「语义没被降级」。任何「A 格式转 B 格式」
的产物，验收面必须包含 B 的读者实际看到的东西；而任何「换权威源」的动作，必须同时回答
「谁在读旧源」，否则绿是错位的。

## 82. 附：CK 轮（2026-10-25）数据换代必须复盘「描述语料的文档」；编辑引入的失实只能靠复扫发现

**① 代码面有门禁，散文面没有。** v0.8.0 数据换代（2026-10-24 撤回 239 批 / 重建 27 批）
复盘了 CHANGELOG / README / 登记册 / BASELINE，**没有复盘描述语料本身的文档**：REPLICATION.md
引用的 15 个路径（`main_batch/` 6 处、`charts/` 4 处、`analysis/SHA256SUMS`、
`test_output.log`、`emse_ult_specir_probe_20261014` 2 处）全部不在盘。机械判据 = **路径复扫**：
把文档里 `experiments/results/…` 的引用逐个 `Path.exists()`，miss 即候选失效项。规矩：**每次语料
换代（增/删/撤批次）都要对「引用语料路径的文档」跑一次复扫**——文档是语料的登记面，语料动了
它不动，就是下一轮 CI 红的素材。

**② 在库文件里的假声明，与未登记声明同族。** `CITATION.cff` 第 5 行写「归档元数据已备：
`experiments/results/zenodo_metadata.json`」——实测该文件不在盘、`git log --all` 亦无此路径。
它不是遗漏（漏登记）而是**多了一句承诺**：比事实多一句话，比事实少一句话同样失真。检测它靠的
还是复扫（引用路径存在性），不是语义审查。

**③ 编辑引入的失实只能靠复扫发现，不能靠记忆。** 本轮 §7 编辑一度把上述假声明原样抄进
REPLICATION.md（「已备」二字顺着读起来完全自然），收尾前的路径复扫当场抓住。规矩：
**复扫是编辑流程的组成部分，不是可选步骤**——凡文档编辑涉及路径/数字，落笔后必须复扫一遍；
本轮两次实例（抄进来的假声明、CITATION.cff 原件）都是复扫抓住的，没有一例是「记得」发现的。

**④ 「运行为产」与「在盘工件」必须分开标注。** 复扫的剩余 9 处 miss 全是运行为产
（`charts/*` / `benchmark_*` / `test_output.log` 由 `reproduce.sh` Step 5/6 现场生成）或已标
历史口径的主批次——不标注的话，这类路径每一轮复扫都会 miss，噪声会淹掉真失效。标注之后，
「不在盘」才重新变成一个可判定的信号。

## 81. 附：CJ 轮（2026-10-25）登记面可以没有读者——set 语义吞掉重复登记；一致性 slack 只查总量不查拆分；行锁误绿可靠历史链续命

**① 登记面自己可以没有读者，而集合语义会把重复吞掉。** v0.8.0 数据换代时 12 条引用豁免键**登记了两遍**（24 行 entry），
`load_allowlist` 返回 `set`、重复键静默合并 ⇒ 门禁照绿；同时文件内 2026-10-16 写下的「现状：**零豁免**」声明未随
补登记更新——**声明与内容双向失实**，且全仓没有任何测试/门禁读这份清单（唯一的读者是门自己，只做成员判定）。
规矩：**每一份自称「有成本的承诺」的登记面，至少要有一个读者数它的原始行**（去重前行数 == 去重后行数）；
「充分性」读者（门：清单压得住全部命中）不等于「承重性」读者（每条登记都还真实命中）——后者防陈旧登记，
前者只防漏。本轮补的 5 例真实树锁正是这两个方向 + 声明条数==实况。（复现：重复一行 → `test_allowlist_raw_entries_have_no_duplicates`
与声明锁 2 红；把某键行号改漂移 → 承重锁 + 充分性锁 + 全仓扫描联动 3 红。）

**② 一致性守卫的 slack 吸收拆分漂移。** `798d8c72`（v0.8.0 后迭代）提交信息实测 **12,491 passed / 254 skipped**，
BASELINE 仍写 **12,458 / 287**：守卫只查「实收 collected − 声明 passed ≤ slack(288)」，12745 − 12458 = 287 ≈ skipped 287
恒等成立 ⇒ passed/skipped 之间 **33/33** 的拆分漂移（语料冻结后守卫面移动）在两个登记值里都看不出来。
规矩：**拆分类登记（passed/skipped/failed）必须同源同跑刷新**；只靠总量恒等的「一致性」是拆分维度的盲区。

**③ 行锁的误绿可靠历史链续命——且可以续两轮。** AO3 行锁断言 `"**CH round:" in README_EN_HEAD`，而头部在 CI 轮
已推进至 `**CI round:`——历史链里的 `Previously **CH round:` 让断言恒真（BC 轮 docstring 记载过的 BR/BS 同形态，
记载了仍复发）。CI 轮与 `798d8c72` 两轮全量跑批均绿 ⇒「测试绿」同样不外推「行锁在钉最新轮次」。
规矩：行锁必须钉**带唯一标记的最新项**（`**X round:` 前缀，历史链一律 `Previously **X round:` 永不命中），
且**换头部与推进锁必须同轮完成**——本轮补推进时才发现误绿已存续两轮。

**④ fail-crash 不是 fail-closed：容错路径只做一半，比不容忍更危险。** `check_citations.py` 的 `collect_files`
对仓库外路径有 try 兜底（去重键退回绝对路径），扫描段却直接 `path.relative_to(PROJECT_ROOT)` 抛**未捕获
`ValueError`**——一条 `--files /abs/outside.md` 即让整门崩栈而不是出具判定（CH 轮「读不懂就静默」的镜像：
那边把不可读折叠成通过，这边把不可读升级成崩溃；显式红优于两者）。处置 = `_rel()` 与 `collect_files` 同一口径。
（复现：`python3 scripts/gates/check_citations.py --files /tmp/x.md --traceability` 改前 rc= traceback、改后 rc=1 命中计红；
`test_out_of_root_file_does_not_crash_gate` / `test_out_of_root_clean_file_passes` 两例锁死两态。）

**⑤ `[SKIP]` 是披露不是红灯。** 复算链（`reproduce_zero_llm.py`）源工件随数据清除撤回后，缺席支路改显式
`[SKIP]`（探针 + 三态 ok/FAILED/skipped），退出码只由「FAILED 命令数 + SHA256SUMS 失败数」决定：
可复算性受损是事实，写成FAILED是谎报，静默 ok 是隐瞒，第三态是唯一的诚实。

## 80. 附：CI 轮（2026-10-24）收口声明必须绑定一次真跑；门禁绿不能外推为测试绿；同一个数不留两份

**①「收口实测」先于收口跑被写下——预期值冒充实测值。** CH 轮把「收口实测 12,749 passed / 0 failed」写进
BASELINE 与 §1 时，收口跑从未发生；三个可复核旁证：`suite_seconds: 221` 注首句仍明写「本键取 **CG 轮终跑**」、
CH 分册 §3 明写「读数在收口跑之后回填」且全仓无该回填、无 CG 轮那样的 date 成对采集指纹。CI 轮全量实测
**12,745 passed / 4 failed**——四条 CG 真树锁硬编码的分母字面量在 CH 移动分母后无人刷新。规矩：**写进登记面的
实测数字必须能指出它来自哪一次跑**（时间戳成对采集或落盘的终端输出）；跑还没发生就读数留空位，
「回填」这个动作本身没有判据时，空位就是唯一的诚实。

**② 门禁绿 ≠ 测试绿。** 四条锁红着的整个周期里 `make invocation-caliber` 与 `make flag-effect` 全绿——门对账的是
已刷新的 BASELINE，锁对账的是没刷新的字面量；「门禁全绿」这句话的覆盖面不含测试锁，**全量 pytest 是它们唯一的
读者**。这与 BZ 轮 fresh clone 31 红（工件在盘被 gitignore 排除）是同一条教训的两个实例：任何一层的绿
都只对自己的对账对象负责，不得外推。

**③ 同一个数不留两份（AB14 单一事实源的第三实例）。** BASELINE 与测试锁各持一份分母，写侧动分母时只刷了其一
——先过期的必然是没人对账的那份。处置 = 真树锁期望值一律读 BASELINE（与门同一权威源、另一条实现路径），
「下一轮改分母忘了刷锁」这一族在结构上不可再现：门与锁同指 BASELINE，BASELINE 与树不符时两者同红。
保留的字面量只有「性质锁」（faces 5 / 幽灵 0 / 兜底动态 1-1 / 判据档无读者 0）——性质不随增删一道门移动，
分母会。

**④ 半真的归因比全假更难发现。** CH 的「七红随登记落盘消失」对其中 3 例（动态读者）是真的，恰好让 4 例
不可能消失的（硬编码不读登记文本）看起来也消失了。归因句必须逐例可验证；「大多数成立」不能外推成「全部成立」。
（复现：`.venv/bin/python -m pytest tests/test_invocation_caliber_cg.py -q` = **66 passed**（改前 62 passed /
4 failed，collected 恒 66）；`.venv/bin/python scripts/tools/cg_mutation_verify.py` = **70 锚点全红 + 中性对照
N01 0 红**、`# mutation:` 残留 0；逐项报告 CLOSING_TREE_SPLIT_CI_2026-10-24（分册已删除）。）

## 86. 附：CR 轮（2026-10-25）编译退出码 0 不是「排版正确」；判据要反映真实世界而不是逼人造假；「一手」必须连抓取面一起说

**① 编译成功 ≠ PDF 正确：缺字符警告不看就等于没有。** 本轮编译论文时 tectonic 报
`could not represent character "档" (0x6863) in font "ec-lmr10"` 与 `manuscript.bbl:14:
Missing character`，而**编译退出码是 0**。根因：`refs.bib` 两个条目的 `note` 写中文，
`note` 进 `.bbl`、`.bbl` 被 `\bibitem` 原样排版，Latin Modern 没有中文字形 ⇒ PDF 的参考
文献处留下缺字符。此前 180 轮没人看见，因为大家只核对「0 未定义引用/文献」，而缺字符
**不影响退出码**——这是「未执行的步骤不算绿灯」的同型：没人读的那类输出等于不存在。
处置不是「以后记得看警告」（靠人），而是把「不可排版的字符」变成**可执行判据**：
审计器新增「可排版文本不得含 CJK」（LaTeX 与 BibTeX 都按 `%` 截断注释，`\%` 是转义
不算注释起点）。复验：重编译后缺字符警告**归零**（PDF 272.40 KiB、55 页、0 未定义引用）。
**一般化：任何「绿」都只对它自己的判据负责；判据没覆盖的失败模式会以「没人看的红」
的形态长期潜伏。**

**② 判据要能反映真实世界——否则它会逼人造假。** 原判据要求每条 bib 条目「至少带 DOI
或 arXiv，否则必须留 TODO」。一手核验 PMLR 官方页（v306/liu26ct.html）确认该记录
**根本不分配 DOI**（PMLR 以 `PMLR 306:77728-77771, 2026` 形态引用）——于是这条判据
对 PMLR 出版物是**伪要求**：它逼作者写一个不存在的 TODO，或编一个并不存在的 DOI。
顺带发现该条目原有 note「DOI 未登记」本身就是**失实表述**（暗示存在一个待登记的 DOI）。
处置：判据承认第三种正当标识 `publisher={PMLR}`（只在 publisher 命中时生效，不放宽到
其它出版物），条目据官方 BibTeX 补齐 pages / publisher / month / url。**判据的失败模式
不只是漏判，还包括逼出假数据——「让条目变绿」与「让条目为真」必须分开。**

**③「一手」必须连抓取面一起说。** 核验 arXiv:2610.11835 时首次抓的是 **HTML 全文页**
（`arxiv.org/html/<id>v1`），抄回的「摘要」混入 `longtable` / `latex` 等 LaTeX 宏名；
同时某二手中文解读给出另一组数字（60,780 变异体 / 58.6% / 54.0% / 16.0% / 16.9%），
与官方摘要**不是同一组**（官方摘要里没有这些数，且两边的指标定义不同：摘要说
"reveal faults"，二手说「真抓到」）。处置：一律以官方 Atom API 的 `summary` 字段为准，
二手那组登记在 §6「来源冲突（留存）」并**禁止入正文**。教训：**arXiv 的「摘要」有三处**
（abs 页 HTML / abs 页 PDF / API `summary`），抓错面会抄进不存在的句子；「一手」这个
标签必须同时说清来源与抓取面，正如「版本」必须一起说（CQ 轮 §85）。

**④ 行锁指向会在历史链里反复出现的旧轮次名 ⇒ 锁恒绿（误绿）。** AO3 行锁断言
`"**CM round:" in README_EN_HEAD`，而双语头部早已推进到 CN 轮——该字面此时**只命中历史链**
里的 `Previously **CM round:`，断言照样通过。CP/CQ 两轮都没推进这把锁，于是它静默绿了
两天。处置：断言推进到带冒号的最新标记 `"**CR round:"`（唯一命中），并把 CP/CQ 未推进
的存量漂移写进锁的 docstring。**行锁必须钉「唯一最新的标记」，不能钉「某个曾经出现过的
标记」——历史链会让后者永远成立。**

**⑤ 奇偶判据只能当粗筛，不能当判据。** 修 §① 时顺手发现 CHANGELOG 全文 `**` 计数为奇，
按段落定位到 3 处（zh）/ 2 处（en）——其中两处是**合法嵌套强调**
（`**外层 *内层* 收尾**`）造成的**误报**，真正的问题只有「孤立的 `***`（显著性星号）会
吞掉后续的 `**` 作闭合标记」这一类。判据因此写成「剥离行内代码后，前后均非字母非星号的
`***`」——精确、无误报，且不误伤合法嵌套强调与 `` `***` `` 行内代码。
**统计量（奇偶计数）当判据前，先问它在合法用法下会不会假阳性；会，就必须换成形态判据。**

## 87. 附：CS 轮（2026-10-26）文档指向的脚本必须存在；「没人跑」的工具要先查默认口径；判据里写死会漂移的数字 = 静默过期点

**① 文档指向一个不存在的工件 = 登记面失实，且它会诱导手改。** CR 轮新建
`docs/study/PAPER_CITATION_KEYS.md` 作为三向读者链的入库承重面，文档里写「重跑导出脚本
并覆盖本文件」——**而那个脚本并不存在**（与 CK 轮 `CITATION.cff`「已备：
zenodo_metadata.json」同型）。危害不止于「文档不准确」：正文改动后维护者按文档操作必然
落空 ⇒ 只能手改快照 ⇒ 快照与正文漂移时锁会红，**却没有可复现的修复路径**——锁变成了
「只告诉你坏了，但不告诉你怎么修」。处置：生成过程固化为入库工具
`scripts/tools/export_paper_citation_keys.py`，快照成为**纯函数输出**（**不能含生成日期**：
日期每次都变会让逐字节比对必然失效）；`--check` 只校验不写入（rc=0/1 可直接进 CI）；
`make paper-citation-keys` 与脚本清单同轮接线——**新工具不给读者，它自己就是下一个只写不读**。
9 例新锁（含「在盘快照必须等于脚本重算结果」）。教训：**每写一句「请重跑 X」，
就要问 X 在不在库里；不在，就把它写出来。**

**② 投稿前的人工清单会过期，而且没有任何机制能发现它过期。** `paper/SUBMISSION.md` 是
投稿前最后一道人工检查清单，审稿人看到的正是这张表。CS 轮体检发现它四处脱节：页数写 54
（实测 `xdv` 55 / PDF 57）、表数写 22（实测 19——**CN 轮时就已经是 19**，说明这张表从未随稿
更新）、TODO 标记写 14 处（实测 18）、refs.bib 标识口径漏了 `publisher={PMLR}`。它脱节
这么久没被发现，是因为**人工清单的读者是人，而人不会去逐条复算**。处置：数据按实测校正
（每项写明口径来源）；审计器新增「**投稿包自洽**」判定面——声明的页数/表数/TODO 数必须等于
**源文件实测值**（页数取 `xdv` 日志；日志不在场则披露跳过而非判红；同一项出现两个不同声明
⇒ 判红）；7 例新锁。教训：**任何「人会在投稿前核对一遍」的清单，都要有机器可执行的对账面**，
否则它只是一份会腐烂的文档。

**③ 没人跑的工具，先查它的默认口径还成立吗——别急着给它加读者。** 普查 `scripts/tools/`
的读者面（测试 / Makefile / CI 三者皆无）发现 39 个「无读者」工具。其中
`scripts/tools/audit_fix_coverage.py` 是为捕捉「修复覆盖主路径、漏掉分支路径」这类复发模式
专门写的，却**从未被跑过**——原因不是没人关心，而是它的默认 `--base` 写死在 V 轮起点
`ff15a2f`（距今 50+ 轮）⇒ 默认跑出来的「新增行」几乎覆盖整个 `src/`，输出是「整仓未覆盖」的
**噪声**（实测：几十个文件的未覆盖计数全为 0 命中）。**一个默认口径已失效的工具，给它接上
读者只会制造噪声读者。** 处置：默认基线改为 `auto` = **最近一次改动审计范围的提交**
（`git log -1 -- pathspec`，即「本次修复」的语义化起点），解析不出时明确报错、**绝不静默
回落到某个写死的历史提交**；5 例新锁；接进 `make fix-coverage`。按新口径实测当前 HEAD：
`src/` 修复新增 0 行、未执行 0 行（0.00%）——自 CM 轮以来 `src/` 无改动。
另 32 个无读者工具是各轮一次性 `*_mutation_verify.py`（结论已进登记册与报告，属**证据留存**
而非活代码），不接入链（会让链长无意义地膨胀）。教训：**「只写不读」的判定要分层**——
一次性诊断脚本的读者是它留下的结论，活代码的读者必须是可执行的门或测试。

**④ 判据里写死一个会漂移的数字 = 给判据设了一个静默过期点。** ADR-0036 的 A1 写「门禁链
**20 步**干净树 rc=0」——那是 CM 轮时的链长（现已 31 步）。判据里的数字一旦会随门禁增删
而变，它就会在某一天悄悄过期，而**判据看起来仍然成立**（数字还是那个数字，只是过时了）。
处置：判据改为「门禁链干净树 rc=0」并指向权威源（门禁自检报告与状态登记册 §1），步数不再
写死；A2 读数刷新并注明最新读数以 `BASELINE.yaml` `tests` 节为单一事实源。教训：**判据要
写「性质」不写「刻度」**；需要引用刻度时，指向单一事实源而不是抄一份。

**⑤ 「一手」之外还要说「哪个面」。** 本轮延续 CR 轮的教训：文献核验必须说清抓取面
（abs 页 HTML / abs 页 PDF / API `summary`），二手来源常给冲突数字；而本轮三条失实都是
**同一形状**——某个维护动作被写成了「请重跑 X」/「表格 N 项」/「共 M 处」，但**被指向的
东西并不存在或已经变了**。一般化：**凡是文档里出现的数字与路径，都要问「它的权威源现在
是什么」，而不是问「它当时是多少」**；能自动算出来的，就让工具算并把工具入库。

## 88. 附：CT 轮（2026-10-26）数一个数之前先说清口径；「grep 零命中」与「东西不存在」隔着一次工具校正

**① 一个说不清口径的数字，文档里写了也无法核验。** 本轮两次试算同一个摘要得到 231 与 244
两个值——差异来自**摘要段里那行 `% SRC:` 溯源注释被当成正文**（稿件把 `% SRC:` 放在
`\end{abstract}` 之前；不去注释就会把路径与文件名算进词数，实测多算 29 词）。这直接决定了
「摘要是否超投稿上限」这个结论：原稿在严格口径下只剩 **3 词**余量（247/250），压缩后
240（余量 10）。处置：判据显式写出口径（先剥离 `%` 注释行；常规口径连字符算 1 词、严格口径
拆开），新增 `abstract_word_counts()` 与 5 例单测把口径钉死；**双口径上限**都进判据（严格
口径 > 250 ⇒ 红；余量 < 5 词 ⇒ 披露）。教训：**统计量的判据必须连口径一起写**，否则下一次
实现会数出另一个数，而两个数都没有错——错的是没人说得清用的是哪个。

**② 判据的覆盖面要对着「读者先读哪份」排。** CS 轮新立的「投稿包自洽」判据查了
`SUBMISSION.md` 的页数 / 表数 / TODO 数，却**没查 `title_page.tex`**——而审稿人先读的是
title page，于是盲区正好落在最要紧的那份文件上（其「54 pages」「236 words」两处都失实）。
处置：判据扩展到 title page 与投稿包的摘要词数声明；4 条变异各红、中性对照绿。教训：
**「已有一个对账机制」不等于「要核对的东西都被对账了」**；新增一份要核对的材料时，
判据的覆盖面必须同步扩。

**③「grep 零命中」与「东西不存在」之间隔着一次工具校正——把零命中当结论，会把「已治理」
误报成「裸奔」。** 本轮 `pip-audit -r requirements.lock` 报 5 条 chromadb 漏洞，我据此判定
「CI 里没有 pip-audit、没有 `--ignore-vuln`、豁免表指向不存在的执行面」——**这是检索错误**：
用了 BSD grep 的 `\|`（字面竖线；仓内检索必须用 Grep 工具）。用 Grep 工具复核：`pip-audit==2.10.1`
就在 security 作业里（R10 转阻断），两遍扫描都带 4 个 `--ignore-vuln`，与登记表逐条一致 ⇒
**4 个 CVE 属已登记豁免，无新漏洞**。教训有两条：**①** 记忆里已经写过的工具陷阱
（BSD grep 不支持 `\|`）**仍会复发**——写进 MEMORY 不等于生效，必须在每次检索时选择工具；
**②** 「未发现」与「不存在」是两件事，把前者当后者会制造**假紧急**（本轮差点把已治理的
供应链面误报成裸奔，并据此规划了一整套接入工作）。一般化：**任何以「零命中」为依据的负面
结论，都必须用第二种工具复核一次**。

**④ 初判被推翻要如实登记，不要只在脑子里改口。** 同一轮里我还怀疑投稿信用的是撤回世代的
旧数字（60.0% / 80.6% / 「three independent batches」），逐条回查稿件后发现**全部一致**
（稿件摘要与正文都是这组数，且已对撤回批次做 historical 标注）——初判被证伪。两处证伪都写进
CHANGELOG 的 CT 轮节：**自我纠错本身是交付物的一部分**，读者据此能判断哪些结论有证据、
哪些曾被推翻。

## 89. 附：CU 轮（2026-10-26）「文档指向不存在的工件」要有判据；新门禁在入库前 CI 拿不到

**① 文档里出现的工件引用必须机器可判。** CS 轮抓到引用键快照写着「重跑导出脚本」而脚本不存在；
CK 轮同型（`CITATION.cff` 写「已备：zenodo_metadata.json」而文件不在盘）。两次都靠**人读到了
才发现**，而「读到了才发现」不是机制。CU 轮把它固化为门禁 `scripts/gates/check_doc_commands.py`
（进 CI 阻断链）：文档中出现的 `scripts/....py` 路径必须存在，`make <target>` 的 target 必须是
Makefile 里的真实目标。**口径必须收紧到不误报**——本轮开发时实测两类误报并写进判据：英文散文
里的 "make the same direction" / "make sure the `target_file` path is correct" 不是命令；`> `
引言块不是 shell 提示符。故只认「代码块内或行首且形态是命令」的行，`make` 必须是整行形态
（target 后只允许 flag）。9 例锁 + 负例自检（两个失效引用被精确报出、存在的目标带 flag 不误报）。

**② 写完门禁 ≠ CI 有了门禁。** 门禁自检在本轮明确报出：「盘 33 / 索引 32，未跟踪 1 个 ⇒ 读作
『本轮未提交』，CI clone 拿不到这些」。这解释了为什么「我把门禁写好了」与「CI 现在会拦」是两
件事：**未入库的文件在 CI 的 clone 里根本不存在**。新门禁必须同轮提交，且门禁索引（登记册
§1 的门禁总数行）必须同步推进——本轮因此连带刷新了 7 个口径数字（门禁脚本 32→33、ci唯一门禁
30→31、ci调用点 33→34、门禁步骤 31→32、阻断步骤 29→30、make目标 20→21、make命令 22→23），
这正是「口径跟着变更走」的连锁成本，也是 ADR-0036 把「步数」从判据里拿掉的原因（刻度会漂）。

**③ 阴性结论也要留证。** 首次全量体检（39 份文档、124 处引用）**零失效**——这条「什么都没坏」
的结论与「抓到 3 处」同样有价值：它说明本仓的文档引用面是健康的，而这个健康此前**没有被任何
工件记录过**（因为没人扫）。固化后，每次提交都会重跑这条体检，「健康」才成为可持续的状态，
而不是一次性的运气。

## 90. 附：CV 轮（2026-10-26）前人已把你的口径说成共识时，要主动让渡而不是回避；不入库的工件之间的同步必须判据化

**① novelty 受到威胁时的正确动作是「主动让渡 + 换战场」，不是回避也不是硬扛。** 上一轮检索到
一篇 2026-10 的综述，它把本稿的核心区分（覆盖率 / 与参考一致 / 检出需求违反 = 三类不同证据）
表述成**领域共识**，且其研究议程首项就是 independent oracle assessment；同时另有一篇在安全域
实证了本稿的 false-fix 现象，还有一篇论证了检出的结构性天花板。三者若不出现在投稿信里，
审稿人自己查到更糟；若写进去而不划界，等于自认 novelty 不足。CV 轮的做法：在投稿信新增
「What this study adds, given the current literature」段，**先如实列出同向工作并主动让渡两项
主张**（不主张区分是新的、不主张现象是首次观察），再明确本稿的增量只有四项且都可核查（成功
定义固定下分开计价 / 两种口径 + 声明率 / 装置同等审计 / 零模型调用复算），收尾把评判锚定在
窄主张上。**一般化：审稿人不会因为你让渡而拒稿，但会因为你含糊而质疑；把「我们不主张什么」
写清楚，反而让「我们主张什么」变得可信。**

**② 不入库的工件之间，同步必须判据化，否则手工同步只保一轮。** `paper/` 按双盲纪律不入库 ⇒
改正文**不会**自动带动投稿信；CV 轮之前只手工同步过一次，下一轮必然漂。处置：审计器新增
「投稿信引文一致性」判定面——投稿信里出现的每个 `arXiv:` 号必须（a）在 `refs.bib` 有条目、
（b）该条目的键被正文引用；任一不满足即判红。4 例锁 + 两条变异各红、中性对照绿。
**一般化：只要两个工件之间存在「应当一致」的关系，而它们又都不在版本控制里，就必须有一条
可执行判据把这条关系钉住；手工同步的保质期等于下一次有人记得改它之前。**

**③ 编辑脚本的失败路径必须与写入路径隔离。** CV 轮插入 CHANGELOG 时锚点文本与文件实际文本
差了两个词（「教训落地」vs「教训的落地」、「投稿信/正文前沿同步」vs「投稿信/正文同步」）⇒
断言失败、整段静默不落盘；而同一轮里判据只写了一半就被中断，`main()` 未消费新判定面 ⇒
**门禁会「通过」但根本没检查**。两处都靠「负例 rc=1」才暴露。**一般化：插入类脚本必须
「先断言、后写盘」，且写完必须用负例验证判据真的被触发——「脚本没报错」不等于「改动生效」。**

## 91. 附：CW 轮（2026-10-26）检索只盯最新窗口，会漏掉已经占位的前人工作；被占位后要主动让渡并换战场

**① 检索的时窗本身就是一种盲区，必须回溯对账。** 连续两轮检索都只盯「最新窗口」
（10 月下旬），结果漏掉了 2026 年 9/10 月已发表、且**直接把本稿核心论断表述成领域共识**
的工作（arXiv:2610.05001 综述、arXiv:2609.12012 综述），以及**在安全域实证了本稿
false-fix 现象**的工作（arXiv:2610.06163）。本轮按「扫 2026 全年 cs.SE 6,500 条 + 13,822 条
候选池去重后 981 条高相关候选逐篇判读」做完回溯后，又补回 12 篇未收录工作。**教训：增量检索
只保证「不漏最新」，不保证「不漏已占位」；「前沿领先」的完整性要求把「领域实际」与「登记册已有」
做一次对账，而不只是继续往后搜。**

**② 已被前人占位时的正确动作是「主动让渡 + 换战场」，不是回避也不是硬扛。** 处置有三处且必须
同步：正文 Related Work 补段并写明「we claim neither observation as ours」；Introduction 的
贡献引导句从「我们的贡献是……」改成「**我们的贡献不是新的观察**，而是**在分母层面的分解**」；
投稿信点名四篇被占位文献并把增量限定为「上述工作都没有报告的那一项」。**一般化：审稿人不会因为
你让渡而拒稿，但会因为你含糊而质疑；「我们不主张什么」写清楚，「我们主张什么」反而更可信。**

**③ 回溯对账的覆盖缺口必须如实披露，不能让「没搜到」冒充「不存在」。** 本轮 DBLP / ACM DL /
IEEE 官方页被代理拦截（DBLP API 四次重试均返回 HTML 而非 JSON），非 arXiv 渠道的 2026 年论文
只能通过 arXiv comment 字段间接覆盖 ⇒ 仍可能存在仅在 ACM DL / IEEE Xplore 上线、未同步 arXiv
的 9/10 月论文未被覆盖。**这必须写进登记册（§9.1「覆盖缺口」小节），而不是让读者以为检索是
穷尽的。**

**④ 判据换了一种输入格式后，必须复查它是否还覆盖新格式。** CW 轮的正文一次引入 8 个新引键，
审计器的「引用无效」项却**一声不吭**——只有投稿信那两条脱节被报出。根因：`audit_bib` 的引用键
只从 **Typst 风格**的 `@key` 提取，而 LaTeX 的 `\citep{key}` / `\citet{key}` 走的正则只用于
段落级引文覆盖计算，**从未参与 bib 存在性检查** ⇒ 「正文引用了尚不存在的文献」长期不可见
（那一轮 PDF 里那 8 处实际渲染成 `?`）。处置：引用键改为两套格式的**并集**；修好后立刻报出
「引文问题 8 项」。**一般化：判据的输入格式随稿式变化（Typst → LaTeX）时，原有判据是否还覆盖
新格式，必须主动复查——「换了稿式」不只换了渲染，也换了判据的输入。**

**⑤ 「编译成功」与「产物正确」是两件事，两处缺陷叠加才让问题暴露。** CW 轮给 `refs.bib` 加十条后，
本地 PDF 的参考文献仍是旧的（新引用渲染成 `?`）。逐项排查后定位到 **tectonic 0.15 的增量编译不采用
bibtex 刚生成的 bbl**（每次报 `internal consistency problem when checking if manuscript.bbl
changed`）；已排除磁盘 bbl 缺失、bibtex 未执行、缓存未清、输出目录陈旧、`--reruns`/`--hide`/`--pass`
各种组合、内容未变导致增量跳过。**而真正让「产物错误」被看见的，是同轮修掉的另一个缺陷——审计器
的 LaTeX 引用键口径盲区（§91④）：若那条判据存在，「正文引用了 refs.bib 里没有的文献」当场就会红，
不必等到看 PDF。** 两个缺陷叠加 ⇒ 一个遮住了另一个。**一般化：给产物的「正确性」配一条可执行判据，
比每次人工比对产物便宜得多；判据缺失时，工具缺陷会伪装成内容问题。**

## 92. 附：CX 轮（2026-10-26）**「取不到就跳过」的判据等于没有判据**；测量源必须与声明同口径、同一次产物

**① 判据里「取不到测量值 ⇒ 披露跳过」的那条分支，会把「缺测量」伪装成「无差异」。** CS 轮定的
页数口径是「从 `tex/manuscript.log` 取 `Output written on … (N pages`；取不到 ⇒ 披露跳过，不判红」。
CX 轮实测：**这道判据一次也没红过**——tectonic 的日志里根本没有那一行（它写的是 `.xdv`），
所以每次都走跳过分支；而场上的日志恰是**一次失败构建**的残留
（`Fatal error occurred, no output PDF file produced!`），于是一个**失败产物被当成了
「测量源在场」**。后果：`paper/SUBMISSION.md` 里「`manuscript.pdf` | 55」这个数，从 CS 轮写下起
**没有任何机制在核**；真LaTeX（TeX Live 2026）编译出来的实测值是 **62 页**。
处置：口径换成**PDF 口径**（pdftex 自报的那行），并加四道守卫——失败构建 / 非 PDF 产物 /
日志与 PDF 字节数不等 / 构建产物早于任一输入源。**一般化：判据的「跳过分支」必须被一条
「拿不到就判红」的路径接管，否则它只是一段装饰代码；而跳过分支本身要有负例（rc=1）钉住，
否则它会安静地吃掉所有真实失败。**

**② 声明值与实测值必须同口径，不同口径的两个数不能互相校验。** DVI/xdv 页数与投稿 PDF 页数
不是同一口径——xdv 是 DVI 页数，PDF 阶段还会追加。拿 xdv 页数去核 PDF 页数，
「一致」也只是两个不同量的巧合。**一般化：写判据前先问「这两个数是同一个东西吗」；
口径不同就换源，而不是换比较方式。**

**③ 「日志在、产物在」不等于「是同一次产物」。** 光看两者都存在，仍可能是两代：日志里的
字节数与磁盘上 PDF 的实际字节数一比即知（511245 vs 别的东西）。**一般化：给测量源加一个
「同一次产物」的指纹（字节数 / 校验和），否则「有日志有产物」这种在场性检查形同虚设。**

**④ 过期产物比没有产物更危险。** 输入源比构建产物新 ⇒ PDF 对应旧稿，页数声明是旧的；
但只要产物「在场」，在场性检查就会放行。**一般化：任何基于构建产物的断言都要带新鲜度检查
（mtime / 哈希），「在场」与「新鲜」是两件事。**

**⑤ 换构建工具链时，先确认「产物里有没有你要的那行输出」——工具的日志格式是判据的输入契约。**
本轮打通真LaTeX 时连踩四层静默失败：tectonic 0.15 增量编译不采用刚生成的 bbl（§91）；
`tlmgr --usermode` 因缺 `texmf-local/tlpkg/texlive.tlpdb` 直接失败；usermode 装出来的文件落在
`texmf-local/texmf-dist/…` 而 `TEXMFHOME` 的搜索路径是 `texmf-local/tex/latex//`（**装上了但找不到**）；
`svjour3.cls` 需要的 `grfext` / `cover_letter` 需要的 `enumitem` 在 TinyTeX 最小安装里缺失。
每一层都是「命令成功退出但没做你以为的事」。**一般化：工具链的每一层都要单独验一次
（文件在不在、搜得到搜不到、编译产物对不对），不要指望端到端一次成功就是对的——
尤其当判据的输入恰好来自该工具的日志格式时。**

**⑥ 文档里每一个手写数字都是候选失实点，能实测的就不该手写。** 本轮实测抓到五处：
页数 55→62、投稿信页数 2→3、`refs.bib` 条数 35→56（CW 轮加十条后对照表未更新）、
`paper/tex/README.md` 的「55 页 / 25 条 / 236 词」。**一般化：手写数字的失实率与它的
「看起来像对的」程度成反比——越是「显而易见的小数字」，越没人复核；凡是能被实测的数字，
就要么让判据去核，要么干脆别写死。**

**⑦ 仓库卫生也要有判据：临时/缓存产物进版本库是沉默的。** 本轮实测抓到 CW 轮的一次 pytest
运行把 `--basetemp` 落在仓库内的 `.tmp_pytest/`，而 `.gitignore` 只登记了 `.pytest_tmp/` 与
`.pytest_tmp*/`——**模式不覆盖它** ⇒ 12 个 pytest 临时文件（含 `.lock` 与 `pytest-current`
**符号链接**）被提交进仓库并随 v1.0.0 发布。处置：新增门禁 `check_repo_hygiene.py`
（按**路径分量**判定，不按后缀——`experiments/results/` 下的 `.log` 是故意入库的证据工件，
`docs/tmp_trace_notes.md` 也不该被误伤）。**一般化：`.gitignore` 是**模式集合**，不是
「排除目录」的直觉；每新增一种临时目录名，都要单独登记并用 `git check-ignore` 逐条验证，
否则「我以为忽略了」和「真的忽略了」之间会差一个通配符。**

## 93. 附：CY 轮（2026-10-26）**「修好了」不等于「验证过」**；定时作业是一条没人看的链；检索要按论断族召回

**① 一道修复若从未在目标环境里跑过，它就只是「代码看起来对」。** 本轮实测：`perf.yml` 的
定时作业 2026-10-11 / 10-18 / 10-25 **连续三次红**（根因是 `BaseAgent` 构造期要凭据，
定时作业环境没有 `.env`），而 CO 轮的修复（`2d594419`）**晚于最后一次红** ⇒ 那次修复
**从未被远端跑过**；下一次定时触发要等到 2026-11-01。`mutation.yml` 同理（10-19 红，
CQ 轮修复更晚）。**一般化：「修好了」这个判断必须绑定一次真跑；而**能手动触发的工作流
就该手动触发一次**（`workflow_dispatch`），不要把验证推给一个按周触发的定时器。
本轮手动派发后：perf 绿、mutation 仍红——**后者暴露了一个全新的缺陷（见④）**，这就是
「不真跑就不知道」的价值。**

**② 一个作业的结论是「所有步骤的合取」——只看结论会把缺陷归错位置。** mutation 作业红，
第一直觉是「门禁没过」；实际**门禁步骤是绿的**（`score=0.9067 > 0.85`，与 CQ 轮的预测
逐位一致），红的是那个被注释成「report-only」的**全量巡检**步骤。**一般化：归因必须
落到步骤级（`jobs[].steps[]`），作业级结论只说明「有一条链断了」，不说明「哪条链」。**

**③ 「report-only / 非阻断」若只用 `if: always()` 实现，作业结论照样会变红。**
`if: always()` 的含义是「前一步失败也照样跑」，不是「失败不影响结论」；该步骤退出码非 0
时整个作业仍是 failure。**一般化：「非阻断」必须显式（`continue-on-error` 或捕获退出码），
否则它只是「不影响门禁判定」，不影响**作业结论**——而作业结论正是巡检者唯一看的东西。**

**④ 沙箱副本的完整性是「收集期」的前置条件，缺一个包就让整批测量失效。**
自变异 harness 的沙箱只复制 `src/` + `config.py` + 目标测试文件，而
`tests/test_helpers_tier_replay.py` 里有 `from experiments import helpers_tier_replay`
⇒ 副本里**收集期**就 `ModuleNotFoundError`（rc=2）⇒ baseline 判红 ⇒ 该模块的测量被判
无效并**中止整个巡检**。**收集期错误与断言失败是两个类**：前者连一个测试都没跑，
它不会出现在「跑了 N 个、挂了 M 个」的读数里，只会表现为「这一项没有读数」。
**一般化：凡是把工作树搬进临时环境跑的装置，搬进去的必须是**依赖闭包**——
本项目的闭包是 `src/` + `experiments/` 的**源码**（`.py`），而不是 `src/` 本身；
`results/` 是 32 MB 运行工件、不属于代码，不进副本。**

**⑤ 检索的召回必须按「论断族」而不是「领域词」来设计。** CW 轮做了「2026 全年回溯」，
但**只扫了 cs.SE**，且用领域词（test generation / mutation / SWE-bench）加权；本轮在
同一窗口（10-19～10-26，120 条新投稿）里逐条判读，抓到 **8 篇与本稿论断关系比 CW 轮
选中的十篇更近**的论文，其中**两篇的主分类根本不在 cs.SE**（cs.CR / cs.CV）⇒ 它们
**结构上不可能**被 CW 轮的扫描覆盖。**一般化：「回溯对账」这个说法会掩盖它其实只覆盖
了一个分类、一个词族；登记册必须**逐轮写明扫描的分类集合与检索词**，否则「全年已扫」
会被读成「全年已覆盖」。**

**⑥ 判据要**先跑**再编译——判据的存在不等于判据被执行过。** 本轮给 `refs.bib` 加八条时
把中文写进了 `note`（沿用了登记册里的中文写法），**直接编译**⇒ LaTeX 报 8 处
`Unicode character … not set up for use with LaTeX`，参考文献区缺字形；
而 CR 轮的「可排版文本不得含 CJK」判据**一次就抓到 8/8**。**一般化：改稿的顺序必须是
「先跑判据 → 再编译」；判据是可执行的，但它不会自己执行——把判据放在编译之后跑，
等于没有判据（它只能告诉你产物坏了，不能阻止产物坏）。**

**⑦ 「TLS 证书链失败」不是「网络不可达」，把它当环境性前提就会静默降级。** 本轮新门禁
用 Python `urllib` 调 GitHub API，在本机（macOS + 企业代理）抛
`CERTIFICATE_VERIFY_FAILED`——Python 的默认 SSL context 与 `certifi` 的 CA 包**都不含
代理签发的 CA**，而 `curl` 走系统钥匙串所以能用。若把这判成「环境性前提 ⇒ [SKIP]」，
这道门在本机就会**永远沉默**。**一般化：判据降级为 [SKIP] 之前要先区分「真的没网」
与「我的客户端不信任这个证书」；能用系统信任链验证（curl / keychain）就不要用自带 CA 包的
客户端。**

**⑧ 判据自己的设计缺陷也会制造假红，而假红会让人开始忽略这道门。** 本轮新写的
`check_scheduled_workflows.py` 初版把「更新的手动运行**还在跑**」判成**红**（因为它不是
「成功」）。结果：作者手动派发验证修复期间，CI 的这道门步骤**无理由变红**（本轮实撞一次：
mutation 派发还在跑，CI 就被拉红）。**「作者正在验证修复」与「修复没验证过」是两件事**：
前者是**结论待定**，应按 `[SKIP]` 披露（带 run 号与它已运行时长），不是判红；而手动运行一旦
**跑完并失败**，下一次运行就会看到「更新的手动运行 = failure」⇒ 判红，**不漏**。已改并补
2 例锁（一条钉「在飞 ⇒ 跳过」，一条钉「跑完失败 ⇒ 红」）。**一般化：门禁的判定必须区分
「结论」与「尚无结论」；把「尚无结论」判成失败，会让人学会忽略这道门——那比这道门缺席更糟。**

## 94. 附：CZ 轮（2026-10-26）**同一类错误连犯两轮** ⇒ 判据必须进**流程**；**已发布的产物**与仓库当前状态不是同一件事

**① 判据是可执行的，不是自动的——同一个错误连犯两轮，必须把它变成流程的第一步。**
CY 轮与 CZ 轮**连续两轮**把中文写进 `refs.bib` 的 `note`（登记册里那句「无出版商 DOI」
被顺手带进了 bib），两次都是**先编译、后跑判据**：LaTeX 报
`Unicode character … not set up for use with LaTeX`，参考文献处缺字形。CR 轮的
「可排版文本不得含 CJK」判据两次都**最终抓到**（8/8）——判据没坏，是**顺序**坏了：
判据放在编译之后，就只能告诉你产物坏了，不能阻止产物坏。**处置**：新增
`scripts/tools/build_paper.sh`（`make paper-build`），把顺序固化成
**① 前置判据 → ② 编译 → ③ 后置判据**：前置判据红 ⇒ **拒绝编译**（不产出坏产物）；
后置判据红 ⇒ 退出码 1 并打印需要更新的读数（构建可能改变页数/文献数 ⇒ 投稿包在数字
对齐前**不算完成**）。脚本的**顺序本身**被 `tests/test_build_paper_script_cz.py`（6 例）
锁住，且断言用的是**剥离注释后的可执行行**——脚本头部注释里就写着「先跑判据 → 再编译」，
不剥离就会把注释当成代码（**「注释不是调用」的同型陷阱**）。
**一般化：判据的正确性不等于判据的**位置**；一个判据放在流程的错误位置上，
它的价值随位置一起错位。凡是「同一个错误出现过两次」的地方，就该把判据嵌进流程，
而不是加进待办清单。**

**② 「已发布的 1.0.0」与「仓库当前的 1.0.0」可能不是同一件事，而这件事原本没人能看见。**
本轮实测：`v1.0.0` tag 指向 `dc8285d3`，而 main 已到 `23b35b00`——**36 个提交**没有
进入「已发布的 1.0.0」，其中包含 perf 定时作业的构造期凭据修复、自变异 harness 的
沙箱依赖闭包修复、投稿页数测量源的四道守卫、仓库卫生与定时作业巡检两道新门禁，
以及 CW/CY/CZ 三轮的文献与 novelty 收窄。`release.yml` 由 `v*` tag push 触发并
检出被标记的提交 ⇒ **tag 指向的树就是发布产物的来源** ⇒ tag 落后 = 发布的产物缺修复。
「要不要前移 tag」是**作者的决定**（force-update 会改写已发布引用，属外部动作），
所以这道门**不能**自作主张改 tag；但它**必须**让这个事实**在 CI 里可见**——
处置：新增门禁 `check_release_freshness.py`，落后且**已登记**（
`docs/release_freshness_allowlist.txt`，逐条写理由）⇒ 绿但**必须打印落后多少个提交**；
未登记 ⇒ 红；登记的 tag 不再对应当前最新 tag ⇒ **例外已失效** ⇒ 红。
**一般化：「发布」是一个**独立于「仓库」的状态**，它有自己的真相源（tag），而两者的
差距**没有任何天然机制会报警**。凡是「发布动作」与「开发动作」分离的流程，都要有
一道「发布产物是否包含最新修复」的判据。**

**③ 检索的召回要按「论断族」，但**扫描范围**也要按分类集合逐轮写明。** CZ 轮按 12 条
「论断族」检索式 × **cs.SE ∪ cs.CR ∪ cs.CV** × 2026 全年扫出 **817 篇**唯一候选
（对被 100 条截断的三个族翻页到深度 300），剔除已登记的 57 篇后逐条判读，抓到**八篇**
新文献——其中**三篇直接占位本稿的核心现象**（`tao2026execcritic` 逐字写出「同一轨迹
写补丁与测试 ⇒ 错误互相印证 ⇒ 虚假信心」并给出冻结测试的解法；
`kim2026coherencecollapse` 用 16,758 条轨迹**分解**出「60–69% 的失败是到达并编辑了
正确函数却仍产出错误补丁」；`bhat2026benchmarkingbenchmarks` 给出四个基准族 18.5% 的
评测器—人工错配率）。**一般化：一次「全年回溯」只证明**当年、该分类、该词族**被扫过；
每轮都必须在登记册里**逐条写明扫描的分类集合与检索式**，否则「已回溯」会被读成
「已覆盖」。CY 轮就栽在这里：它的回溯**只扫 cs.SE**（自陈），而本轮最同题的两篇
主分类在 cs.CR / cs.CV ⇒ **结构上不可达**。**

**④ 「覆盖缺口」要写**真实根因**，否则读者会以为「再试一次」就能关闭。** 登记册此前的
措辞是「DBLP / ACM DL / IEEE 官方页被代理拦截」。CZ 轮实测更正：**不是代理拦截**，
而是 **DBLP 自己的反机器人挑战**（Anubis）——`dblp.org`、`dblp.uni-trier.de`、
`dblp.dagstuhl.de` 三个入口**一律返回 HTTP 202 + 「Making sure you're not a bot!」的
HTML**（不是 JSON），`dblp2.uni-trier.de` 返回 401。⇒ 这是 DBLP 公开 API 的**常驻属性**，
不是本环境的临时故障 ⇒ 该缺口**无法通过重试关闭**，只能如实披露。
**一般化：覆盖缺口的登记要写「根因 + 它是不是可重试」；把「常驻限制」写成「临时故障」，
会让下一个人白花时间重试。**

**⑤ 登记表的语法承诺要有判定侧的读者，且必须在任何绿色之前生效（EB 轮，2026-10-27）。**
CZ 建门时，脚本文档与登记表表头写了两条语法承诺：例外必须写理由；条目必须对应当前
最新 tag，否则记「例外已失效」。EB 轮实测：这两条在判定侧的读者一个为零、一个是部分——
「理由非空」没有任何代码读；「失效条目 ⇒ 红」只在**最新 tag 未登记**那条红色路径上
可达。于是三种状态下登记表语法完全不判：① 当前 tag 已登记、表里另有失效条目（先命中
`if tag_name in allowlist:` 的绿色返回）；② tag == HEAD（更早的绿色出口）；③ 仓库没有
任何 `v*` tag（`[SKIP]` 出口）。一张只增不减的登记表可以让 CI 永远绿——「登记即通行」
正是 CZ 想禁止的那件事，只是换了个入口。**处置**：`_reason_problems`（纯本地，先于
网络判定）与 `_stale_problems`（tag 解析后、任何绿色 / 跳过之前）两类缺陷**累积后一次
列出**（只报一类会让人以为清理完了）；GitHub API 不可达仍按既有环境策略 `[SKIP]`，
但无理由条目离线也红。9 例新锁（判定面 6 / 既有绿色与跳过契约 3）；真树实测 `v1.0.0`
有理由且就是最新 tag ⇒ 仍绿，已登记例外的「落后 45 个提交」照常打印。
**一般化：写进表头 / 文档的规则，如果没有一支在每个出口之前执行的读者，那它就只是
注释；例外登记的有效期属于判定侧的事实，不能留给人工核对。同一张登记表的两类缺陷
必须一次跑全部点名——修复只关掉其中一类，等于让人以为清理完了。**

## 95. 附：DE 轮（2026-10-26）**注释语法是文件类型的属性**；**新鲜度判据放在构建之前会锁死构建**

**① 「注释」不是一种语法，而是三种——按文件后缀取规则，不能一套正则走全仓。**
本仓同时存在 TeX、Typst 与 BibTeX 三种可排版文本，而它们的注释语义互不兼容：

- TeX：`%` 到行尾是注释，但 `\%` 是字面百分号（**反斜杠奇偶**：`\\%` 才是注释起点）；
- Typst：`//` 到行尾、`/* … */` 可嵌套；字符串、反引号 raw、`https://` 里的 `//` 不是注释；
- BibTeX：只有**字段值括号外**的 `%` 才是注释；`note={100% pass@1}` 是字面量；
  字段值里的 `\"` 是 LaTeX 变音符，**不是字符串边界**。

旧读侧按「TeX 的 `%`」一刀切：Typst 稿的 `// TODO` 没有被剥掉、`% TODO` 反而被剥掉；
BibTeX 侧则把 `author={Sch{\"a}fer}` 的转义引号当成字符串起点，于是**紧随条目的
`% 中文注释` 被算进上一条目的字段值**，审计器报「bib 条目含中文字符」——查进去
根本没有中文（DE 轮真树实测：`refs.bib` 从假红转绿）。**一般化：解析器的「注释」概念
必须和它读的文件格式绑定；一个跨格式共用的正则，在每种格式上都只对一半。**

**② 新鲜度判据放在构建之前，会把「重建」这个动作本身判红。**
`build_paper.sh` 的三步顺序是「前置判据 → 编译 → 后置判据」，而前置判据调用的是完整的
`audit --strict`，其中包含「任一输入源比构建日志新 ⇒ 产物已过期」。这条判据对**构建后**
是对的，对**构建前**是自指悖论：只要改了 `refs.bib`，前置判据必红 ⇒ 脚本拒绝编译 ⇒
那一步永远修不好它抱怨的东西。DE 轮真树实测：改完 bib 后 `make paper-build` 在第一步
即退出。**处置**：新增 `--pre-build` 档，构建前只跳过页数/字节数对账（并披露跳过），
CJK / 引用 / SRC / 覆盖率等源侧判据照常阻断；构建后的完整 `--strict` 仍逐项核对产物。
**一般化：判据要区分「源侧事实」与「产物侧事实」；把产物侧的新鲜度判据放在产物生成之前，
等于让流程自己把自己锁死。**

## 96. 附：EC 轮（2026-10-27）**读侧词汇不是自选的**；测试夹具自造词汇会与读侧一起错；三态不得折叠成布尔

**① 读侧的词汇表必须以写侧的实际产出为准，不能照抄另一套系统的字段名。**
本仓的结构化追踪写侧只有一支：`TraceSession`（`src/observability/trace.py`）。它落盘的事件
只有三种（`task_start` / `node` / `task_end`），任务结果字段是 `passed`（True / False /
None 三态），节点 token 快照是 `token_usage.total_tokens`。读侧 `src/utils/trace_viz.py`
却按另一套词汇读：节点事件集合写成 `node_start` / `node_end` / `planner` / `executor`
等七个名字，结果字段读 `test_passed`，token 读 `token_delta` / `tokens`。EC 轮真树实测
（`experiments/results/cross_file_ab_level3` 的 100 份真实轨迹）：**100/100** 张任务卡渲染
成「无节点记录」，**100/100** 打 FAIL 徽章——而写侧这 100 个任务全部 `passed: true`；
400 条 `node` 事件没有一条进入时间轴。渲染不报错，只是把「有」画成「无」、把「通过」画成
「失败」，所以没有任何门禁会红。

**② 写侧与读侧「互相印证」的测试，可能是一起错。**
上述词汇在测试里同样存在：`tests/test_new_modules_2026_09_28.py` 的夹具直接构造
`event: "node_end"` / `test_passed` / `token_delta` 记录喂给渲染器，断言「PASS 出现在 HTML
里」——而真实轨迹里这三个词一个都不出现。测试与读侧共用同一套自造词汇，于是全绿；写侧
（`TraceSession`）在测试里缺席。**处置**：EC 轮的 12 例新锁全部用**写侧真实产出**构造轨迹
（`TraceSession.record_node` / `record_task_end` 落盘后渲染），并单列一例反向锁：外来的
`node_end` 事件不得被当成节点记录——读侧只认写侧的事件名。

**③ 三态不得折叠成布尔，缺席不得冒充失败。**
写侧的 `passed` 有三个值：True / False / None（None 在 `record_task_end` 文档里就是
「任务中途崩溃」）；整份轨迹没有 `task_end`（被截断）连值都没有。旧读侧用
`any(… and test_passed)` 得到一个布尔，于是崩溃与截断都落进 FAIL。现在徽章按三态渲染：
True=PASS、False=FAIL、None 或缺 `task_end`=CRASH（汇总口径相应改为「通过 / 未通过」）。
节点计数同理：旧版汇总把 `task_start` / `task_end` 一起算进「节点记录」，卡片上的
「节点数」却恒为 0；现在两处都只数 `node` 事件。回放的状态演化也改为读 `passed`
（state 的规范键是 `test_passed`），真轨迹的 `state_snapshot` 不再为空。

**一般化：读侧的词汇表属于写侧的契约，不是读侧的自选项；测试夹具必须取自写侧产出，
否则测试只是和读侧互相印证。多值结果（True / False / None / 缺失）要按原样渲染——
把「崩溃」折叠成「失败」、把「截断」猜成「失败」，都是让观测层说谎。**

## 97. 附：ED 轮（2026-10-27）**「可选」依赖的失败面不止「缺包」**；守卫按能力判据而非异常类型；不可观测的降级不得记成修复

**① `except ImportError` 只覆盖了可选依赖的一半失败面。**
可选依赖的文档承诺是「不可用时降级」。但「不可用」有两种形态：没装（ImportError）
与装了但坏（扩展 ABI 不匹配、传递依赖版本冲突、共享库缺失——RuntimeError / OSError /
ValueError）。本仓 12 处可选导入守卫只捕 ImportError，第二种形态会直接穿透。
真树复现（子进程把目标包替换成 RuntimeError 后导入消费者）：**12/12 全部逃逸**；
最重的是 chromadb——`src/rag/retriever.py` 的导入失败沿 `src.cli.app → src/graph/workflow
→ src/graph/rag → src/rag/retriever` 冒泡，**整个 CLI 无法启动**，而文档承诺的是
「RAG 增强跳过」。这不是退出码或文案问题，是「可选」被写成了「必需」。

**② 判据是「该依赖是否还能提供能力」，不是「异常的类型」。**
修法：12 处守卫改为 `except Exception as exc` + 告警，保留原降级值（False / None / []）；
数据集下载入口保留 `ImportError` 的公开契约，但用 `__cause__` 链上真实导入异常——
「没装」与「装坏了」在 traceback 里可区分，而不是都提示 `pip install datasets`。
负控制（必需依赖 click 损坏）仍照常抛出，防止修复退化成吞掉一切导入错误。

**③ 修不改变可观测行为的站点不纳入修复，登记为排除项。**
`src/cli/output.py` 的 rich 守卫看似同类，但 rich 是 httpx 的硬导入
（`httpx/_main.py` `import rich.console`），httpx 的 `__init__` 只对 ImportError 降级；
任何 `src.cli.*` 导入都先经 `src/cli/__init__ → app → langgraph → langchain → httpx`，
本层捕获 Exception 也救不回 CLI。**处置**：不改该守卫、不出测试锁，在排除项里写明上游证据。
同时排除：stdlib 平台差异（`resource`）、必需依赖（`langgraph.checkpoint.memory`）、
内部生成模块（`src.config.config_generator`）、已被外层 `except Exception` 覆盖的
torch 导入。**一般化：缺陷族按「失败面」枚举，但修复范围按「能否改变可观测行为」收敛；
把不可观测的防御性改动记成修复，与把缺包写成可用一样，都是让登记册说谎。**

## 98. 附：EE 轮（2026-10-27）**「损坏」不止坏 JSON**；`json.JSONDecodeError` 只覆盖解码后的文本；行级隔离要隔离到解码之前

**① 读侧的损坏判据停在了解码之后。**
15 处 JSON/JSONL 读侧的异常处理写成 `except json.JSONDecodeError`（部分另捕 OSError），
但 `JSONDecodeError` 是 `json.loads` 对**已解码字符串**的报错。字节层损坏——部分写入
截断的多字节字符、编辑器以 GBK 保存、坏扇区——在更早的**解码步骤**抛
`UnicodeDecodeError`（⊂ `ValueError`，与 `JSONDecodeError` 无继承关系），完全不在
捕获域内。文档承诺的「坏行跳过、其余照常」「损坏 → 空列表 / 空库 / 跳过」因此只对
坏 JSON 成立，对坏字节失效。真树复现（每处写一行 `b"\xff\xfe"` 后调用公开入口）：
**15/15 全部抛出**。最重的两处——SWE-bench 主数据与 ULT manifest——一行坏字节让整份
基准加载中断；策略库写侧更危险：读不懂的库文件本应 fail-closed 不覆写，坏字节却
绕过了该判据直接抛出（本次未覆写是巧合，不是契约）。

**② 行级隔离必须隔离在解码之前。**
文本模式的 `for line in f` 在进入行内 `try` 之前解码，迭代器一旦解码失败即报废，
行内再多的 `except` 也救不回同一文件的后续行。**修法**：行级读侧改为二进制读
（`open(..., "rb")`）+ 逐行 `raw.decode("utf-8")`，解码失败与 `JSONDecodeError` 同口径
跳过并留痕行号。**不用 `errors="replace"`**——替换字符可能把坏字节洗成一份能被
`json.loads` 接受的错数据（静默串味），观测层的「跳过」必须可解释为「这段没读」，
而不是「读成另一个东西」。整文件读侧（info.json / 知识库 / 策略库 / 报告扫描 /
RAG 兜底材料）是单一 JSON 文档，无从按行隔离 ⇒ 把 `UnicodeDecodeError` 加入处理器
元组，走文档承诺的降级值；策略库写侧据此保持「读不懂 ⇒ 原文件原样保留」。

**③ 测试夹具必须与生产读取模式同构。**
BR 轮的 5 个 OTel 用例用 `mock_open(read_data=str)` 模拟文件——生产改二进制读后，
mock 仍返回 `str`，用例以 `AttributeError` 失败。这不是实现回归，而是**夹具没有
建模读取模式**：mock 掩盖了「文本模式在解码期崩溃」这一被测属性。处置：改用真实
临时文件（断言不变），并在用例里写明理由。**一般化：被测行为依赖 I/O 模式（文本 /
二进制、严格 / 替换解码）时，内存 mock 的默认形态会与被测口径脱节；用真实文件，
或让 mock 显式建模模式。** 同轮排除：已捕 `ValueError` 的读侧（mdo / cross_file /
dependency / semantic_cache——`UnicodeDecodeError` 已被覆盖）、子进程自产临时文件
（fl_spectral / branch_coverage_inject）、必需配置的 fail-fast 读侧
（config_generator）、解析字符串而非文件的调用。**修 15 处、锁 15 例（ULT 数组分支与
rag 持久化源各单列一例，其余逐一对应），不把「已覆盖」的站点记成修复。**

## 99. 附：EF 轮（2026-10-27）**非有限浮点是「解析成功」的坏值**；`float("nan")` 不抛 `ValueError`；`min/max` 会把 NaN 洗成边界值

**① 只捕 `ValueError` 的浮点解析把 NaN/±inf 当成了合法读数。**
`src/` 里 6 处本地浮点环境解析（deterministic_guard / semantic_cache ×2 /
workflow / risk_approval / failure_kb）写成 `float(os.getenv(..., default))` 外加
`except ValueError`。但 `float("nan")` / `float("inf")` / `float("1e999")`
**不抛异常**——它们是「解析成功」的坏值，异常处理器根本不会触发。紧接着的
`max(lo, min(hi, value))` 又不传播 NaN：`min(1.0, nan)` 比较为假返回 1.0、
`max(0.0, nan)` 返回 0.0，于是 NaN 被**静默洗成边界值**，与「用户显式设了极值」
不可区分。未夹取的三处（守卫睡眠阈值、覆盖率 eps、衰减半衰期）则把 NaN 原样带进比较与幂运算。
真树复现（逐站设值后调用公开入口，HEAD 全红）：`SEMANTIC_CACHE_THRESHOLD=-inf`
→ 阈值夹成 0.0、**任意相似度都算命中**（实测返回了无关缓存条目）；`=nan` → 夹成
1.0、缓存静默失效。`SEMANTIC_FALSE_POSITIVE_SAMPLING=nan` → 夹成 1.0、**每次命中
都触发误报复核 LLM**。`COVERAGE_STALL_EPS=nan` → `abs(delta) >= nan` 恒 False、
**停滞恒判**（delta 5.0 的正常轮被判停滞）。`RISK_THRESHOLD_MEDIUM=nan` → 夹成
1.0、`risk_score >= 1.0` 不可达、medium 级**永不出现**（实测 medium → low）。
`DETERMINISTIC_GUARD` 睡眠阈值 NaN/inf → `arg_val > threshold` 恒 False、
**long_sleep 规则静默失效**。`FAILURE_KB_DECAY_DAYS=nan` → `0.5 ** (age/nan)` 得
NaN，`score <= 0` 恒 False、排序键不可比，**知识库排序退回插入序**（旧条目排到新条目之前）。

**② 非有限判定必须与钳制分离，且判定在钳制之前。**
项目已有统一的 `env_float`（`src/utils/env_utils.py`）：未设/空白 → 默认值、
非数字 → 告警 + 默认值、**非有限（NaN/±inf）→ 告警 + 默认值**、越界 → 告警 + 默认值。
`config._parse_float_env` 早已带 `math.isfinite` 守卫，6 处本地实现是**旁路**。
修法：解析统一委托 `env_float`，**钳制语义留给调用方**——`risk_approval._env_float`
保留「有限值越界取边界」的既有契约（与 `env_float` 的「越界回退默认值」刻意不同），
只把**解析**换成委托；`feedback_compression._clamp_env_int` 只读整数、无 NaN 面，不动。
顺序不可颠倒：若先钳制再判非有限，NaN 已变成边界值，判定永远看不到它。

**③ 非有限修复必须同时锁「有限口径不变」与「告警可观测」。**
只测「NaN → 默认值」会漏掉两类回归：（a）顺手把钳制改成回退默认值——`RISK_THRESHOLD_*`
设 5 会从 1.0 变成默认值，这是把一种静默换成另一种；（b）把非有限值静默吞掉——修复
成本行，读者仍不知道自己的环境变量没生效。故三组锁并列：非有限值 ×6 字面量 ×6 站点
回退默认值；有限值钳制/取用回归锁（越界取边界、区间内原样生效）；WARNING 含变量名与
「非有限值」字样。**同轮排除**：已委托 `env_float` 的调用点、`config._parse_float_env`
（已有 isfinite 守卫）、`feedback_compression`（整数解析无 NaN 面）。审计闭合复扫
`src/` + `config.py` 的 `float(` 环境解析，剩余未受护站点 0。**修 6 处、锁 49 例
（6 站点 × 6 非有限字面量 + 2 例有限口径回归 + 7 例行为后果 + 4 例告警文本），
不把「已受护」的站点记成修复。**

## 100. 附：EG 轮（2026-10-27）**默认开启的守卫被正集解析静默判关**；「设 false 可退回」不等于「坏值也退回」

**① 默认开启 ≠ 正集解析。**
`env_flag(name, True)` 的 `True` 只是**未设置**时的默认值；变量一旦被设置，判定完全交给正集
（`true`/`1`/`on`），其余一律 False。于是 `PATCH_DANGEROUS_API_GUARD=yes`、
`CREDENTIAL_SCRUB_WHITELIST_ENABLE=enabled`、`EXECUTOR_USE_VENV=ture`（拼错）甚至空串
（`VAR=` 在 shell 脚本里很常见）都会把**安全守卫关掉**，而各站点 docstring 承诺的只是
「设 false 可显式退回」——坏值不在承诺内，却与显式关闭走了同一分支。HEAD 真树复现
（逐站设坏值后调用公开入口，全红）：`safe_apply_patch` 接受新引入 `os.system` 的补丁；
`scrub_os_environ()` 返回的环境里仍有 `MYSQL_PASSWORD`（白名单退回黑名单）；
`suggest_package_names` 返回任意未知名；`check_naming_contract` 对删除模块级符号的补丁
返回 `(True, [])`；`check_llm_patch_safety` 对危险补丁返回 `[]`；证据门开关读成 False；
Docker 命令丢掉 `--read-only` 与 `--network=none`；`config.EXECUTOR_USE_VENV` /
`SWE_BENCH_P2P_GATE_ENABLE` 在导入期绑定为 False。

**② 守卫用负集（fail-closed），特征/成本开关保留正集。**
J-2 已引入 `env_flag_opt_out`（未设 → 开；`false`/`0`/`off` → 关；其余含坏值 → 开）。
本轮把 10 个默认开启的守卫开关（11 处读取）迁过去：`EXECUTOR_USE_VENV`、
`SWE_BENCH_P2P_GATE_ENABLE`、`CREDENTIAL_SCRUB_WHITELIST_ENABLE`、
`PIP_PACKAGE_WHITELIST_ENABLE`、`PATCH_DANGEROUS_API_GUARD`、`PATCH_CONTRACT_CHECK`
（patch_applier 与 testless 两处消费点）、`INJECTION_GUARD_OUTPUT_ENABLE`、
`PATCH_EVIDENCE_GATE_ENABLE`、`DOCKER_READ_ONLY`、`DOCKER_DEFAULT_NETWORK_NONE`。
方向判据是「坏值误判的后果」：守卫被误关 = 危险补丁落盘 / 凭证进子进程 / 隔离降级；
特征被误开 = 拼错也会启动后台健康检查（真实消耗 API 配额）或实验特性。故后者
（`ENABLE_PLANNER`、`ENABLE_DEBUGGER`、`API_CIRCUIT_BACKOFF`、`API_HEALTH_CHECKER_ENABLE`、
`FL_SPECTRAL_ENABLE`、`FAULT_LOCALIZER_ENABLE`、`POSITION_AWARE_REPAIR_ENABLE`、
`TRACE_MEMORY_BUFFER_ENABLE`）保持正集，坏值不隐式开启；`POSITION_AWARE_REPAIR_ENABLE`
的 docstring 仍写「默认 false」而代码默认 true（文档漂移，另行处置，不改语义）；
testless 的 `_layer_enabled` 层开关关闭会在 status 通道显式披露（VALIDATION_DISABLED），
同属边界外。**不把「默认开」当成「都是守卫」。**

**③ 迁移必须同步三类外部锁。**
守卫口径变化会打到三类非行为锁：（a）源码文本锁——`tests/test_review_20261019_repro.py`
直接断言 `env_flag("EXECUTOR_USE_VENV", True)` 出现在 `config.py`；（b）变异锚点——
`scripts/tools/bh_mutation_verify.py` 的 M6 用该行原文作字符串锚点，源码一改即失配
（同步后重跑整套 harness：11 变异全红、中性对照 0 红、collected 73 不变）；
（c）旧测试 docstring 把缺陷写成契约（`TestSafetySwitchTruthyCaliber` 的
「（及垃圾值）才关闭」）——改为「垃圾值保持开启」，并保留 `true`/`1`/`on` 与
`false`/`0`/`off` 双向锁。**同轮排除**：J-2 已迁移的 11 处负集站点、上述特征/成本开关、
`_layer_enabled`、`json_output_mode_enabled`（自定义负集，语义已等价）。
**修 10 个开关 / 11 处读取，锁 31 例（24 红→绿 + 7 边界：显式关闭 ×4、
config 显式关闭、特征/诊断开关正集 ×2），不把「默认开」的站点记成修复。**

## 101. 附：EH 轮（2026-10-27）**单次 LLM 全局预算的两处兑现缺口**；「有截止点」不等于「截止点会到」

**① 墙钟截止点会被回拨整体挪走。**
`LLM_CALL_BUDGET_SECONDS` 的承诺是「故障转移 × 模型 × 重试整段超限即快速失败」（`config.py`），
实现却用 `deadline = time.time() + 预算` 且用 `time.time()` 判定。墙钟不是单调量：NTP 阶跃校正、
VM 快照恢复、笔记本改时间都会把它往回拨，截止点随之后移——预算**永不触发**，恰是 0.7 债务项 2.2
要防的「单任务卡死整个跑批」。真树复现：假 monotonic 在「建客户端」阶段推进 11s（预算 10s）、
墙钟冻结在 1000.0，旧实现 `time.time()` 永远越不过 1010（`DID NOT RAISE`，请求照发）。
口径不是新立的：`src/api/api_health.py` 早已把熔断冷却定为 monotonic，并写明「不受系统时间回拨影响」。

**② 只在换模型时检查，退避阶段越预算仍发请求。**
截止检查位于模型循环顶部。同一模型内的重试阶梯（1/2/4s）与 429 退避（固定 `min(Retry-After, 30s)`）
都不看预算：预算 5s 时，退避 1+2+4s 已耗到 7s，第 4 次请求照样发出；最后一个模型耗尽预算时，
最终抛的还是「已尝试所有 API」，预算信号被淹没。这与 `COST_MODEL` 的「超限快速失败，**不继续发请求**」
直接冲突。真树复现：预算 5s + 固定失败 → 旧实现发满 4 次请求（`invoke == 4`）；429 场景固定 `sleep(30)`。

**③ 修法：计时源 + 判定粒度 + 信号类型三处一起改。**
（a）`deadline` 改 `time.monotonic()`；（b）判定下沉到 `_invoke_openai` 入口（每次真实请求前）与
重试器 `pre_retry_check`（退避前），429 等待按「剩余预算」截断，全 API 失败收口前再复查一次；
（c）预算耗尽抛 `LlmCallBudgetExceeded`（RuntimeError 子类，保持既有调用方捕获面），并加入
`non_retryable_exceptions`——预算信号不得被退避重试当瞬态故障吞掉。**同轮排除**：跨进程缓存 TTL
（`_lru_negatives` / `semantic_cache`）、文件 mtime 清理与落盘节流仍用墙钟——它们要么需要跨进程
持久化（monotonic 无跨进程语义），要么与被比较的 mtime 同源；`duration_ms` 等**读数**不改，
本轮只碰**行为门控**的截止判定。**修 1 处截止判定（3 个检查点 + 1 处等待截断），
锁 6 例（5 红→绿 + 1 预算内回归），不把 TTL/读数站点记成修复。**

## 102. 附：EI 轮（2026-10-27）**时间预算的降级面兑现了、判定面没有**；「快速失败」不等于「被记成预算封顶」

**① 新信号落在既有捕获面之外。**
EH 引入的 `LlmCallBudgetExceeded` 被建成 `RuntimeError` 的**兄弟类**。编排层的预算封顶读者
全部以 `isinstance(e, BudgetExceededError)` 为唯一判据：`_planner_node`（默认计划 +
`logic_degraded`）、`_generator_node`（空测试 + `budget_exceeded`）、`_debugger_node`
（`error_category="budget_exceeded"` + 空补丁），以及 `determine_stop_reason` 经
`state["budget_exceeded"]` 产出 `BUDGET_EXCEEDED`。超时异常在三个节点都被更宽的
`except RuntimeError` 接住，降级产物与 token/USD 超限**肉眼相同**，但标记一个都没写：
工件把「时间预算止损」记成「未知故障」，`BUDGET_EXCEEDED` 终止原因永久不可达，
`.env.example` 的「触发 5.4 预算封顶」承诺落空。

**② 红因逐节点可辨。**
真树预修：planner / generator 的更新字典缺 `budget_exceeded`（`KeyError`），debugger 落
`error_category="unknown"`，planner 降级结果经 `determine_stop_reason` 返回
`MAX_ITERATIONS` 而非 `BUDGET_EXCEEDED`；构造签名也不接受 `limit`（`TypeError`）、
`.limit` 属性不存在（`AttributeError`）。7 例新锁全红，红因各自指向「标记缺席」而非 fixture。

**③ 修法：改继承，不动读者。**
`class LlmCallBudgetExceeded(BudgetExceededError)`，自定义 `__init__(message, *, limit=None)`
经 `RuntimeError.__init__` 绕过父类数值模板（本类**没有**可报的已消耗秒数，`consumed=None`
表示未知），属性按父类字段形状暴露（`unit="seconds"`、`limit=配置值`）；raise 点传
`limit=LLM_CALL_BUDGET_SECONDS`。三个节点与停止原因的判定代码**零改动**自动同待遇——
这正是「读者只认父类」应有的扩展方式。**同轮排除**：不改 `non_retryable_exceptions`
的冗余双元组（保留 EH 的显式语义）、不新增 state 键、不把 `BudgetAccountingError` 等
已继承者重登记。**修 1 处继承关系（1 个类 + 1 个 raise 点），锁 7 例（7 红→绿）。**
