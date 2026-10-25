> **语言 / Language**：[English](README.en.md) | 简体中文（本文）

> **当前版本 1.0.0**（2026-10-25）：测量面收口版——按 `docs/adr/0036-v1-release-criteria.md`，判据 A（测量面前沿 7 项）与判据 C（发布机械 5 项）全部关闭后发布：论文数字审计新增「声明数字必须在所指工件里」的读侧判据（附录 E 成本表据此从错指向改正为 historical + 撤回索引表 W-1，A/B 实证：错指针 rc=1、修正后 rc=0）、复现包完整性从「0 份受检也绿」改为四态（实测 8 目录 / 401 文件通过、5 目录缺席披露、无清单判红）、论文正文补三处必披露（fixed 材料 53/261、合成发生器漂移、scale87 replace≠SpecExpr）、README / MODEL_CARD / REPLICATION 与仓库实况对齐。32 道门禁与测试底座读数见 `BASELINE.yaml`；轮次明细见 `CHANGELOG.md` [1.0.0] 节。
>
> 最后更新：2026-10-25（**CM 轮：1.0.0 发布收口 + 论文数字存在性读侧判据 + 复现包完整性四态**——附录 E 成本表原指向 `emse_stats_extensions_20261025/`，而该工件不含表里的 261 行池读数（26,114.9 / 0.025885 / 35-of-261）：**路径存在、数字不在，审计仍报 100% 可追溯**。处置 = 论文改 historical + 落点 `WITHDRAWN_ARTIFACTS` 表 W-1（冻结原值）+ `// SRC-CHECK: strict` 逐条核对；审计器新增块级数字存在性判据（派生量只披露、strict 块阻断），A/B 实测：错指针 rc=1、修正 rc=0；11 例新锁。复现链完整性改四态（ok / FAILED / 无清单=FAILED / absent 披露），实测 **8 目录 / 401 文件通过 / 0 失败 / 5 目录缺席**，4 例新锁。README/MODEL_CARD 补 1.0.0 已知限制）。此前 **CL 轮：远端 CI 三档全红归因——写在 pytest 前的快照步骤把格式化计数 +1 冲掉登记门禁**——CI「生成静态快照」步骤原排在 pytest 之前，写入的 `docs/history/static_report_<日期>.md` 计入 ruff 格式化面 ⇒ 登记门禁复算 976 ≠ BASELINE 975 ⇒ pytest 内两条真树锁三档全红，本地 fresh clone 全绿；修复 = 快照步骤移至作业最末端（pytest 与诊断重跑之后）+ 诊断 grep 容忍 xdist 前缀 + 步骤顺序回归锁（变异验证：换回旧顺序 ⇒ 锁红）。此前 **CK 轮：复现包与撤回语料对账 + 1.0.0 判据落 ADR-0036**——REPLICATION.md 15 处失效引用（主批次/charts/analysis 随 2026-10-24 数据清除撤回）、§6 校验和清单 69 文件/7,048 条 vs 实测 **4 文件/181 条**、§7 CITATION.cff 版本与行号过期；CITATION.cff 第 5 行「归档元数据已备」实测文件不在盘、git 历史无此路径（在库假声明）改如实待补充。ADR-0036 把「前沿领先的 1.0.0」操作化为 A 测量面 7 项 / B 研究面 4 项（需用户授权，不阻塞）/ C 发布机械 5 项。此前 **CJ 轮：引用豁免登记面补读者 + 复算链源工件缺席显式 [SKIP] + 引用门仓库外文件崩栈修复**——v0.8.0 补登记的 12 条豁免键**登记了两遍**（24 行；`load_allowlist` 返回 set、重复键静默合并 ⇒ 对所有读者不可见）且文件内「现状：零豁免」声明未随补登记更新；新锁 `tests/test_citations_gate.py` **13 例**（真实树登记面 5：原始行无重复 / 键形态 / 全部承重无陈旧 / 充分性 / 声明条数==实况；合成面 8：邻域口径 / 自身指标豁免 / 定向豁免 / set 静默合并语义 / 排除面 / 仓库外两态），变异 3+1（重复键 2 红 / 陈旧行号 3 红 / 回退 `_rel` 3 红 / 中性对照 0 红）；`check_citations.py` 对仓库外 `--files` 绝对路径 `relative_to(PROJECT_ROOT)` 抛未捕获 `ValueError`（`collect_files` 容忍、扫描段不容忍）⇒ `_rel()` 兜底修复；`reproduce_zero_llm.py` 源工件撤回支路改显式 `[SKIP]`（三态 ok/FAILED/skipped，退出码只由 FAILED + SHA256SUMS 失败数决定）。存量勘误两处：`798d8c72` 实测 12,491/254 未刷 BASELINE（一致性守卫 slack 吸收拆分漂移）、AO3 行锁**误绿两轮**（钉 `**CH round:` 而头部已至 CI 轮，被历史链 `Previously **CH round:` 满足）推进至 `**CJ round:`。全量确认跑 **12,490 passed / 268 skipped / 0 failed**（collected 12758）。此前 **CI 轮：收口声明与树分裂——「12749 passed 收口实测」先于收口跑被写下，而那次跑只会显示 4 红**——对 CA–CH 未提交批次全量回归实测 **12,745 passed / 5 skipped / 4 failed**（collected 12754、224.78s），而 BASELINE 与 §1 声称的「CH 轮收口实测 12749 / 0 failed」从未发生（`suite_seconds: 221` 注仍明写「本键取 CG 轮终跑」、CH 分册 §3 明写「之后回填」且无回填、无 date 成对指纹）；四条 CG 真树锁（`tests/test_invocation_caliber_cg.py` r01/r03/r04/r05）硬编码 CG 轮分母字面量（在盘 31 / 链上 17 / 声明 71 / 登记 9 / 结构 28-30-29-30 / 登记表 15 条），CH 写侧移动全部分母（新增 `check_flag_effect.py` + 删一条失效登记 ⇒ 32 / 18 / 73 / 8 / 29-31-30-31 / 14 条）后只刷 BASELINE 与 §1、没刷锁，期间门禁链全程绿（门对账已刷新的 BASELINE）——**门禁绿 ≠ 测试绿**，全量 pytest 是测试锁唯一读者。处置 = 四锁期望值单一事实源化到 BASELINE（`gates`/`invocation` 两节、经 CG 门 `load_baseline_yaml`；r01 保留 CF/CG 双实现相遇断言）+ 性质锁字面量保留（faces 5 / 幽灵 0 / 兜底动态 1-1 / 判据档无读者 0）+ r05 登记表总数字面量删除换「flag-diff 条数 == `invocation.flag_diffs`」互证 + BASELINE 注释链与 §1 追加勘误（历史不回溯改写）；验证 = `pytest tests/test_invocation_caliber_cg.py` **66 passed**（collected 恒 66）+ CG 变异 **70 锚点全红 + 对照 0 红**（`# mutation:` 残留 0）；零门禁改动、零 `src/` 改动、零 LLM、$0；详见 CLOSING_TREE_SPLIT_CI_2026-10-24（分册已删除）。此前 **CH 轮：命令行上传了的开关，有两个从来没被读过——「判据档无读者 0」是真绿但误导**——新增纯读侧门禁 `scripts/gates/check_flag_effect.py`（553 行 / 23 个顶层函数）判 **dest 活性**：CG 判「有没有人传这个开关」（读者活性），本门判「这个开关在源码里接没接线」，同一个 `(门禁, 开关)` 分母、两条独立实现各自复算再对账；四态互斥完备 `活 / 代理 / 死 / 不可判` + 恒等式 `声明 = 活 + 代理 + 死 + 不可判`。改前树（= 工作树移除本轮四个新文件并回退接线）实测 31 道在盘 / 24 道有 argparse / 声明 **71** 个实例里 dest 从不被读 **2** 条 = 死 1（`check_docs_history_drift --warn-only`，调度只读 `args.strict`）+ 代理 1（`checksum_results --verify`，调度只读 `args.write`；当下与按 `--verify` 调度等价，但等价性由 `required=True` 的互斥组担保、不由开关自己担保，全仓这样的组只有 **1** 个），两条**都是判据档**且**都被 ci.yml 真实传入**（改前 744 / 298 行）——CG 把「调用面出现过这个 token」算作读者，于是那条「判据档无读者 0」是真绿但误导：token 有读者，开关没有效果路径；同名开关跨门一边活一边死（`--verify` 在 `check_baseline` 被读 3 次、在 `checksum_results` 读 0 次；71 个实例去重只有 **51** 个唯一名、重名 **11** 组）⇒ 分母必须是组合数而不是开关名；逃逸写法（`vars(args)` / `getattr(args, …)` / `**args` 展开 / `args.__dict__` / `parse_known_args()` / 整包传参）按 AST 结构复算命中 **0**，命中即整门退成**不可判**并计红（按子串搜会把 docstring 里讲这写法的门误判成不可判，本门第一版正是这样）。本门**不设豁免表**：装饰性开关的正当处置只有接线或删除——两条写侧接线后现树在盘 **32** / 有 argparse **25** / 声明 **73** / 活 **73** / 代理 **0** / 死 **0** / 不可判 **0** / 互斥必填组 **1**，CG 侧联动读数随接线移动（31→32、17→18、71→73、代码锁 26→29、登记无读者 9→8，其余八数不动），两条恒等式各自成立（CG `73 = 14 + 29 + 8 + 0 + 22`、CH `73 = 73 + 0 + 0 + 0`）。新增 **99** 例锁 ⇒ collected **12754** = **12749 passed + 5 skipped**；变异工装 `scripts/tools/ch_mutation_verify.py` **75 锚点全红 + 1 中性对照 0 红**（collected 逐锚点恒 99、sha256 原字节还原、墙钟 334s；首轮 3 存活全部就地处置——M38 暴露「读不懂就静默」长在**本轮门禁自己身上**（受检面比判定面多一道门且不留痕），补 fail-closed 两档 + M76；M68 是 `[OK]` 行与通过行共享子串的**断言歧义** ⇒ 一条断言只能钉一行；M06 复核为**等价变异**，删锚点、记进等价清单，连同工装另列 5 处合计 **6** 处等价区；最大扇出 M53 红 **32** 例而多数是 `KeyError` ⇒ 红数是扇出不是判据数）；预登记跑 **12,742 passed / 5 skipped / 7 failed、231.20s / rc=2**（七红 = 基线守卫 + CG 真树四例 + CF 两例，全是登记前状态）；覆盖率行 **19522/20036 = 97.4346%**、弧 **7159/7590 = 94.3215%**（`src/**/*.py` 136 个文件 mtime 晚于 2026-10-24 00:00 命中 **0**、最新 1792766822 与 CG 登记同 epoch ⇒ 继承态；相对 CG 各 −1 行 / −1 弧落在 ±2 抖动带内且与 CE 逐位相同）；零 LLM、$0；规矩入册 `docs/MEASUREMENT_INTEGRITY.md` §79；详见 CH 分册（分册已删除）。此前 **CG 轮：门禁「挂在链上」不等于「以同一口径在跑」**——新增纯读侧门禁 `scripts/gates/check_invocation_caliber.py`，把 `make` 链与 `.github/workflows/{ci,perf}.yml` 的调用口径第一次放在一起对账，改前实测绑定**两棵可重建的树**（改前树 = 工作树移除本轮四个新文件并回退本轮接线；中间态树 = 改前树 + 本门脚本）：① 非阻断判据按**子串**搜步骤正文，CF 门复算 **非阻断 3 / 阻断 26**，按 YAML 结构（步骤级键缩进 8 且非注释行）复算 **2 / 27**（中间态 **2 / 28**）——多出来的那条是 ci.yml 注释里那句「改 `continue-on-error: true`」被当成当前键，而这个数已经进了 `BASELINE.yaml` 与登记册 §1；② 同一脚本跨调用面开关不等从未对账，只比「`make gates` ↔ ci.yml」得 **1** 处、所有面两两比得 **3** 处，其中两处理由只写在 Makefile 与 perf.yml 的**注释**里（注释不会被复算）；③ `check_prompt_artifacts` 不在 `make gates` 链上、CI 又裸跑不带严格档 ⇒「已接线」为真而「强制」为假；④ 不阻断还有第三层：shell 兜底「`||` echo `::warning`」与区块级 `set +e` 生效区（按 `set ±e` 逐行推进状态）；⑤ `$STRICT_FLAG` 由 `workflow_dispatch` 输入注入 ⇒ 静态普查看不见实际口径；⑥ 在盘门禁逐个答「谁在跑它」（改前树 30：链上 16 / ci.yml 28 / perf.yml 1 / 仅 `experiments/` 以 import 调用 1 / 三侧皆无 0）；⑦ 声明开关的读者分四类（调用面传过 / 代码锁 / 登记表 / 无读者）：改前树 **69** 个声明里无读者 **31**（判据档 **9** + 范围与呈现 **22**），中间态 **71 / 33**（判据档 **10**），差值恰是本门自身的 `--list`（判据档）与 `--quiet`（呈现档）；宽松读者规则「文件里出现过这个 token 就算读者」会报「0 条无读者」——那不是干净，是把判定面取消了。处置五条约定：判据按结构不按子串 / 开关相等按**有效值**（`add_argument` 的 `default=` 用 `ast` 就地复算，`--f=v` 与 `--f v` 同解）/ 差异落机器可读登记表 `docs/invocation_caliber_allowlist.txt`（15 条 / 5 类，无理由・畸形・重复・失效・现场找不到・§1 未认领各计红）/ 判据档无读者记红、范围与呈现档记数 / 分母恒等式自校验（收口 **71 = 传过 14 + 代码锁 26 + 登记 9 + 判据档 0 + 呈现 22**）；另加仓库级前提缺失显式 `[SKIP]` 带成因、本门自身接线判定、`[SURFACE]` 六行口径披露，登记册 §1 新增「调用口径（CG 轮）」13 键行与 `BASELINE.yaml` `invocation:` 13 键。零 LLM、$0；新增 66 例锁（除真实树 6 例外全部跑在 tmp 合成调用面上）⇒ collected **12655 = 12650 passed + 5 skipped**；变异 **70 锚点全红 + 1 中性对照 0 红**（三轮处置：首轮 12 存活 = 2 判据缺口 + 9 有判据无锁 + 1 等价变异显式记录，第二轮 1 存活，红数 36×1 / 11×2 / 最高扇出 33，墙钟 424s，collected 逐锚点恒 66）；详见 CG 分册（分册已删除）。此前 **CF 轮：登记面的派生数字与分册清单从未有读者**——`docs/PROJECT_STATUS_REGISTER.md` §1「静态检查」行手写 **999** 文件已格式化，而 HEAD（`00e8c24d`）干净树复算 `ruff format --check .` = **1037**（漂移 **+38**、工作树 **1050**）；「门禁总数」行把口径指给 `BASELINE.yaml` `gates` 节，而该节的三个键在全仓 Python 里读者 **0**（`check_baseline.py` 只看 `static_checks` 的两个 0）；`docs/reviews/` 在盘 **78** 份分册有 **5** 份不在 §3.5 清单上（死链方向一直有门禁，反方向第一次有读者），zh §2.2 编号 `[6…20, 22, 21, 23]` 非连续却被读者当计数用；处置为新增纯读侧门禁 `scripts/gates/check_registration_consistency.py`（823 行）：15 个数字项就地复算对账 +〔当前口径〕可解析声明位 + BASELINE 登记键逐个被读（缺键 / 非整数 / 不等都计红）+ 分册双向清单 + 拥有者活性与本门自身接线，括号外 **830** 个裸数字按历史快照只披露不判定（811 为 §1 括号落盘时读数）；+46 例锁（46 passed）、变异 38 锚点全红 + 中性对照 0 红（零 LLM，$0）；此前 **CE 轮：模型指纹门禁把 `pinned=true` 说成「可比」、把窗口计数说成语料结论**——`scripts/gates/check_model_fingerprint.py` 改前只判 `pinned is True`，三条缺口同一棵树上实测：① `alias_mismatch=true` 门禁侧读者 **0**（写侧三处 HEAD `experiments/run_benchmark.py:3838/3840/3852`，存盘语料 85 个 `False` + 2 个 `None`），而「别名不变、返回模型变了」正是 S29/F13 的原始漂移形态 ⇒ pinned=true 仍 rc=0；② `requested_alias` 已不在运行时模型集（CD 轮收敛为单别名 `deepseek-flash` 后第一次可判定）仍 rc=0；③ 成功语句「通过：1/1 个受检工件」的分母 = 近 2 天 mtime 窗口（实测窗口内 2 / 豁免 1 ⇒ 实检 1），而 benchmark 语料在盘递归 239 / 入库 107 / 顶层非递归 64、结构面 provenance 122 / fingerprint 87 / pinned 85（⇒ 2 份未锁定在窗口外根本不进判定）——「这 1 份干净」与「整个语料干净」同形。处置：两条可比性围栏（`alias_mismatch is True` 严格布尔；`requested_alias` 对账 **import 运行时权威源** `src.config.config_generator.COMMON_MODELS` 而非复制常量，取不到显式 `[SKIP]` 带三类成因）+ `[SURFACE]` 四行口径披露（成功 / 报红 / 空窗口 / `--allow-empty` 四条输出路径全打印；语料侧 alias 读数只披露不判定）。**`pinned` 判定值与方向逐字节不动**。过程事故：首版围栏在 `make model-fingerprint` 脚本口径下 `sys.path[0] = scripts/gates` ⇒ import 失败 ⇒ 整条静默退化成 skip，补 `sys.path.insert(0, PROJECT_ROOT)` 后进程内与脚本两侧同值、围栏与 skip 各设锚点。零 LLM、$0；新增 19 例锁（35 → 54）⇒ collected **12543**，全量 **12538 passed / 5 skipped / 0 failed**，覆盖率 19522/20036 行 = **97.43%**、7159/7590 弧 = **94.32%**，变异 33 锚点全红 + 1 中性对照 0 红。详见 CE 分册（分册已删除）。此前 **CD 轮：运行面与文档面收敛到「仅保留 DeepSeek 官方」，历史归档删除后派生读数按存盘语料重算**——provider 注册表（`PROVIDER_TEMPLATES`）仅剩 `deepseek`，`COMMON_MODELS` 仅 `deepseek-flash`，第三方 SDK 调用路径（域名判定 / 客户端缓存 / 双重试 / temperature 透传）整体移除，价目表与 .env 模板同步；入库历史结果删除 **330 个文件**（3 份批次 JSON + 327 份 trace，均记录非 DeepSeek 模型），`SHA256SUMS` 复算 **1869 项一致**（20,895,308 字节）；派生读数按存盘语料重算：mutation×detection 表 10 → **7** 批、detection 可测 n 回落为配对 n（605→556、658→609）、率 **14.03% / 1.64% / 48.86%**（分层均值、Δ均值与相关系数逐格不变）；trace 语料锁 9086 → **8763** 文件、span 129058 → **126408**、token 属性 27135 → **26166**；语料守卫口径复测 **239 / 138 / 8216** 不变。清理面外保留并写明理由的两类：第三方**文献引用**（论文 / 榜单 / 外部适配器）与**凭证脱敏拒绝名单**（`OPENAI_API_KEY` 等，DeepSeek 走 OpenAI 兼容协议）。零 LLM、$0；collected **12524**，全量 **12519 passed / 5 skipped / 0 failed**，覆盖率 19523/20036 行 = **97.44%**、7160/7590 弧 = **94.33%**。此前 **CC 轮：补丁重采样在真实 LLM 下结构上永不生效——`DebuggerAgent` 的 system prompt 要求 JSON 输出，真跑返回 `{"root_cause":…,"patch":"```python…```"}` 信封，重采样回调却对整段信封调 `extract_code_block`：JSON 转义换行是字面 `\n`，围栏正则匹配不到，整段 JSON 被当作补丁，`check_naming_contract` 必然拒绝，`resampled` 恒 False（真跑 1 调用复现；既有用例全部 mock 成裸代码块，故无锁）。修复：先 `extract_json_object` 解信封取非空 `patch` 字段，非信封才回退原文提取；新增 2 例锁 + 变异 3 锚点全红 / 对照 0 红；修复后 19 面复跑 `resampled=True / success=True`（全 19 面 19 调用 / 12,212 in / 4,344 out / $0.00888）；预登记跑 12,553 passed / 5 skipped / 1 failed、225.11s；终跑（`make gates`）**12,554 passed / 5 skipped / 0 failed、222.37s、rc=0、链墙钟 234.07s**，基线 12,552 → 12,554（行 19572/20086 = 97.4414%、弧 7169/7600 = 94.3289%）**。此前 **CB 轮：状态通道门禁的成功语句大于判定面——判定面只有就地赋值（2 键 / 11 站点）与字面读（57 键 / 353 站点），而 LangGraph 的规范写侧（节点返回更新 dict）45 键 / 95 站点完整落在面外，正是 docstring 自己点名的 M14 / O35 静默丢弃那条路；118 个声明键里35 个未被触及，其中 `failure_frequency_applied` 全仓零字面——声明注释承诺「`_debugger_node` 写入 True」，实际只拼 prompt 不写键，且 `None` 被解释为「开关关」，「没开」与「从没写入」在数据上同形。处置纯读侧：`channel_coverage()` 三向覆盖 + 成功语句后四行披露 + `--coverage` 逐键表，update dict 只披露不判定、`src/` 零改动；并修复自指缺陷（门禁 docstring 与守卫测试里的死键字面曾被当成「别处有出现」，把零字面键从 1 抹成 0）；17 例新锁（13 → 30）+ 变异 18 锚点全红 / 对照 0 红；预登记跑 12,551 passed / 5 skipped / 1 failed、226.95s；终跑（`make gates`）12,552 passed / 5 skipped / 0 failed、226.42s、rc=0，基线 12,535 → 12,552**）。此前 **CA 轮：门禁豁免登记的陈旧与遮蔽从未披露——`EVIDENCE_DIR_EXEMPTIONS` 16 条登记只在压制告警那一刻被查询、从不被审计：2 条已失效（`emse_jsonmode_smoke_20261013` 目录消失、`emse_spec_ir_quixbugs_20261013` 53/53 已全部入库，删登记后门禁输出逐字节不变），存活 14 条在 158 个文件里遮蔽 155 个未入库工件——「一条豁免都没有」与「豁免遮蔽 155 个」在成功输出上同形**。处置纯读侧 + fail-closed：`ExemptionCoverage` 单一事实源（遮蔽量 = 总数 − 已入库，全部登记同批一次 `git ls-files` 解析）+ 五类漂移（目录消失 / 已全部入库 / 目录为空 / 不可读 / 登记名落在扫描面外）与「扫描面为空」解耦并阻断 + 通过时逐条 `[EXEMPT] <dir>: 遮蔽未入库工件 h/total` 与汇总一行；扫描判定口径、判定值与分母一处不动、`src/` 零改动；12 例新锁（21 → 33）+ 变异 16 锚点全红 / 对照 0 红）。此前 **BZ 轮：CI 历史三族红的归因与修复——29 例测试引用的归档工件被 gitignore 排除致 fresh clone 全红、45 个传递依赖漏洞升级清零、跨平台 libm 末位容差**。归档实测：run 39905189493 （head 5eb51607）test 3.12/3.13 在「Run tests with coverage (parallel)」步骤失败、3.14 作业 30min 超时被 cancel、Security 在 pip-audit lock 审计步骤失败；失败清单逐字取自 check-run 注解 API（公开可读），fresh clone 模拟（shallow + CI 同环境变量）复现 31 例——本地全量绿只因工件在盘而被忽略。处置：契约工件入库 408 个 / 5.9 MB（逐层 negation 放行）、语料面 / 历史切点 / 双盲文件三类前提缺失改显式具名 skip（理由带实测读数，不折叠成通过也不折叠成失败）、pillow / aiohttp / certifi / otel 四族升级（45 漏洞全部有上游修复，lock 132 → 133）、test 作业超时 30 → 60。验证：fresh clone 三轮闭环 31 红 → 9 红 → **0 红**（12453 passed / 46 skipped，skip 理由逐条核过）、pip-audit「No known vulnerabilities found, 5 ignored」、本地全量与升级前逐位相同。此前 **BY 轮：报告的「分析集流量」从未披露——`## 数据来源` 只列纳入文件，而加载器在到达该清单前剔除数据集外 886 行、schema 不完备 2,463 行、未登记基线 300 行，载入 7,010 行又被去重折叠 6,449 行（91.997%），配对单元只有 561 个唯一任务行**。归档实测（扫描面 246 份 / 10,659 行；数据集外 77 份 / 886 行；schema 59 份 / 2,463 行；读取/加载失败 0 / 0；未登记 300 行；载入 110 份 / 7,010 行；重复 6,449；唯一 561；字段 None：`passed` 0 / `detection_rate` 45 / `repair_rate` 52；全归档带 `results` 的 JSON 257 份 / 11,197 行，其中非 benchmark 命名 13 份 / 538 行；混批口径 169 份 / 9,473 行、重复 8,494、唯一 979）。处置纯读侧：单一事实源 `experiments/_analysis_flow.py` + `statistical_analysis.analysis_flow_stats` + `## 数据来源` 新子章节（流量表 + 三层对账 + 外部口径脚注）+ 控制台一行，判定值与方向一处不动、`src/` 零改动；**27 例新锁 + 变异 46 锚点 = 45 变异全红 / 对照 0 红**。此前 **BX 轮：写而不读键池最后两键的读侧从未披露——`risk_summary` 全归档 `enabled=False` 占位（`enabled=True` 0、level 非空 0、键缺席 2,333、`contract_status` 在场 0），「通道没开」与「全部低风险」同形；`mdo_crash_rate` 五层输入域（未跑 / 材料缺 / 不可测 / 暂定池 / 实测）共用一个 `None`，`mdo_pool_floor_ok=False` 1,516 行是两义键（暂定池 530 + 默认值 986）**。归档 257 批次 / 11197 行：risk 在场 8,864；crash 五层 2,312 / 122 / 986 / 530 / 94，规范值 94 行（79 零 / 15 非零，池化 15/3,200 = 0.46875%），暂定池原始值 530 行（12/7,190 = 0.1669%）不与实测合并。处置纯读侧：单一事实源 `experiments/_residual_keys.py` + 报告两表新章节 + 批次摘要一行，判定值与方向一处不动、`src/` 零改动；**102 例新锁 + 变异 44 锚点 = 43 变异全红 / 对照 0 红**；键池闭合 41,545 + 22,035 + 12,908 = 76,488，零读者池为空。此前 **BW 轮：补丁接收链的覆盖率与分母从未披露——`patch_precision`（预注册 E3）、`patch_plausible_evidence` / `patch_plausible_invariant_violation`、`patch_abstain_signals`、`patch_validated` / `patch_validate_verdict` 自写入起报告面 0 读者（弃权与验证两族只有测试读者），`None`「算不出」与 `0.0`「算出零」同形**。归档 257 批次 / 11197 行：接受集 1331（16.61%）、存储精确率 45.60% vs 并集 50.75% vs gold 57.92%、选择性风险 54.40%（gold 42.08%）、抑制精确率 93.98%（gold 分母）/ 93.11%（全部分母）、验证输入仅 `patch_evidence_level` 1007 行可达（`repo_verification` / `deterministic_repair_status` 全归档为空）。处置纯读侧：单一事实源 `experiments/_patch_acceptance.py` + 报告四表新章节 + 批次摘要两行，判定值与方向一处不动；**94 例新锁 + 变异 68 锚点全红 / 对照 0 红**。此前 **BV 轮：批次 VIII / XIV 两份判定核的「沉默」从未披露——归档 5935 行里有 20 行 test-hacking 判 True、4442 行 FL 约束门未求值，在任何报告面都不出现**。`test_hacking_suspected` / `_signals`（批次 VIII，ADR-0022）与 `fl_constraint_verdict` / `_hit_rank` / `_changed_functions`（批次 XIV，ADR-0028）自写入起报告面读端 **0**；判定核在「无原码 / 无补丁 / 两侧解析失败」时返回 `suspected=False, signals=[]`，与「三信号都跑过且零命中」**完全同形**（5915 行分不清判干净还是没看），FL 侧六种早退共用一个 `not_evaluable`（4442/5935）。归档 257 批次 / 11197 行实测：hack 判 True **20**（`hardcoded_input_branch` 12 + `exception_swallow_added` 8）从未出现在任何报告面；FL hit 1487 / miss 6 / not_evaluable 4442 ⇒ hit 比 **99.60%**，而 3+ 变更函数档仅 29/1493 = **1.9%** ⇒ **ADR-0028 登记的整文件重写成因不足以解释这个比值**。处置：判定核增返 `status`（五档，两侧解析拆独立 try）+ 结果行落 `test_hacking_status` / `fl_constraint_reason`（六种早退各带独立 reason）+ 单一事实源 `experiments/_verdict_silence.py` + `detector_silence_stats` 读侧（记录 / 推断 / 不适用 / 无判定键四来源分列，推断明写下界）+ 报告新章节（hack 9 列 / FL 11 列 + 判别力注 + 两条脚注）+ 批次摘要一行；**判定值与方向一处不动**。**87 例新锁 + 2 处旧契约改写**；**变异 58 锚点全红 + 中性对照 N01 0 红**（首轮 V04 / P11 / S03 三项存活全部就地处置）；沙箱确认跑 **12257 passed / 19 skipped / 0 failed、218.94s / rc=0**（正常口径 12271 / 5 / 0、collected 12276）；覆盖率行 **19538/20052 = 97.4367%**、弧 **7150/7584 = 94.2774%**。详见 DETECTOR_SILENCE_BV_2026-10-23（分册已删除）。此前 **BU 轮：Self-Repair Trap 判定核的输入可达域从未披露——5935 行恒判「不怀疑」，而两个信号在全归档拿到过 0 行输入**。`self_repair_trap_suspected` / `self_repair_trap_signals` 自批次 XIV（ADR-0028）写入 5935 行、恒为 `False` / `[]`，报告面读端 **0**；判定核三个信号各自的最少点数门槛（3 / 2 / 2）从不写进报告，于是「**3200** 行只有 1 个点、进不了任何门」「**2723** 行进得了 collapse 门且确实判干净」「declining 与 score 全域 **0** 行输入」在报告面上是同一个读数，另有 **531** 行两点连续下降却结构上进不了 ≥3 门、**12** 行 `oracle_quality_history` 为 `None`。同进程把判定核重跑在归档历史上 **0** 处不一致 ⇒ 判定核与任何行的值一处不动，只加分档与对账：单一事实源 `experiments/_trap_input_domain.py`、`statistical_analysis.self_repair_trap_domain_stats` 读侧、`analyze_results` 的 13 列章节（沉默臂 / 空域 / 对账异常三注 + 两条口径脚注，门槛文案读常量）。**79 例新锁**（八类，逐类取自 `--collect-only`）+ **变异 61 锚点全红、中性对照 U63 0 红**（collected 逐锚点恒 339、`# mutation: ` 残留 0、rc=0）；首轮 U18 / U30 / U54 三项存活与 U49 / U50 / U53 三处锚点语法错误全部就地处置。确认跑 **12184 passed / 5 skipped / 0 failed、194.81s / rc=0**（collected 12189；预登记跑 12183 + 5 + 1，唯一红 = 基线守卫）；覆盖率行 19526/20040 = 97.4351%、弧 7150/7582 = 94.3023% 与 BT 逐位相同（`src/` 零改动）。详见 TRAP_INPUT_DOMAIN_BU_2026-10-23（分册已删除）。此前 **BT 轮：验收 oracle 的来源与可见性——写入端说反了，读端为 0**。`oracle_type` / `test_visible_to_system` 自 R52 起写入 **8012** 行，全仓零读取方；写入端还把 SWE-bench 仓库级验收（gold FAIL_TO_PASS，测试**对系统不可见**）标成 `generated_test` + 可见。修法：标签收敛 `experiments/_oracle_provenance.py`（新增 `gold_fail_to_pass`），`_oracle_descriptor(task, baseline, state)` 按基线真实路径取值，**五个结果构造点**全部传入；报告面新增「验收 oracle 来源与可见性」章节（repo 行必须 gold + 不可见，不一致逐条点名）。归档实测：8012 行全 `generated_test/True`、50 行 repo 记录均早于 R52（`(None,None)`，**不是错标**）；历史工件不重写、论文数字不变。**12 例新锁**；collected **12082** = passed **12077** + skipped 5（沙箱 12062 / 19 / 1，唯一失败为基线守卫，回填后绿）；覆盖率逐位不变 19526/20040 = 97.4351% / 7148/7582 = 94.2759%。详见 ORACLE_PROVENANCE_BT_2026-10-22（分册已删除）。此前 **BS 轮：覆盖率工作流在本机跑不通——分支口径只靠 `--cov-branch` 传参**。`pytest --cov=src --cov-branch -n 4` 实测 `DataError: Can't combine branch coverage data with statement data`：`.coverage`（控制进程）lines 1 / arcs 0，四个 worker arcs 2.4k–23k，同一命令行两种口径。修法：`[tool.coverage.run] branch=true` 写进 `pyproject.toml` + 1 例打包测试锁（非 CLI 入口不再写语句数据）。按 CI 口径重跑 **19526/20040 = 97.4351%**（97.44）、分支 **7148/7582 = 94.2759%**（94.28），棘轮 96.40/92.50 绿（余量 1.04 / 1.78pp；AA-4：不在本地 macOS 抬水位）。collected **12070** = passed **12065** + skipped 5（沙箱确认跑 12051 / 19 / 0、202.70s / rc=0）。详见 COVERAGE_CONFIG_BS_2026-10-22（分册已删除）。此前 **BR 轮：第三方集中复审 27 项全部确认为真并收口（零 LLM，$0）**。报告 HEAD `53bbbbd4`，收口 HEAD `f49959b2`；P1=14 / P2=13、P0=0，**零误报**。代码面：探针在 Docker/内核沙箱/隔离拒绝后不再回宿主重执行（N01），目标模块异常帧按真实路径保留（N09）；坏 token 记账在有效预算（env **或** 实例 cap）下锁存 `budget.exceeded` 并抛不可重试的 `BudgetAccountingError`，重试/故障转移/实例 cap 均不可绕过（N02）；E7 合并前校验候选-任务身份，身份互换不再算成 κ=1（N03）；成本逐行归因闭合，未知 token 不再套他行价格（N04，全额 `None` + 可归因小计）；`paired_contrast` 统一共享最新行（N05）；非 0.5 二项并列概率（N06）、零基线 MDE（N07）、标准 diff 识别与 fallback 前缀（N08）、OTel 非对象行隔离（N10）、并发专家缓存改调用作用域计量（N11）；`sys.path` 前缀让位 future/docstring（F04）、P2P 基线与补丁后分离（F05）、pass@k 按程序身份分组（F06）、批次加载原子化（F07）、`--json` 异常任务补错误行（F11）、移除无效的 `ALLOW_UNSANDBOXED` 恢复指引（F12）。流程面：发布绿门改查 `ci.yml` + `head_sha` + 作业全绿，排除自身 in_progress（F08）。文档面：ICST'26 改相对 HITS 的 17.72%/19.80%/20.92%（绝对 +7.52/+5.84/+5.85pp，F09）、ADR0030 收回领域级外推（F10）、分发范围按字段说明（F14）、df 成本 6.2×（F15）、n41 界限 7.3/8.6/12.6%（F16）、复现说明 87 任务口径（F17）、CANDOR v7 ≥21.1pp（F18）、false_fix 可测定义（F19）、双语 API 示例按真实签名（F20）。**77 例新锁**；collected 12069 = passed 12064 + skipped 5（本会话沙箱确认跑 12050 / 19 / 0、537.77s / rc=0）。详见 BR_ROUND_CENTRAL_REVIEW_2026-10-22（分册已删除）。此前 **BQ 轮：报告读侧把四个 status 通道当作不存在——BN 落盘的结果行四键零行读者**。BM 给 `contract_status` 接的是生产侧透传（`final_state→结果行`），报告面（`build_analysis` 30 个指标助手 / `run_main_batch` 摘要块 / `statistical_analysis`）对四键**一个都不读**（探针实测：`experiments/`+`scripts/` 184 个 .py 里行读 = 0；对照组 `contract_missing_symbols` 有 1 个真实行读者 `refresh_patch_field.py:201`）。后果：「这条腿跑过且干净（ok）」与「崩了（error）/ 按设计没跑（disabled）/ 材料缺失（unavailable）/ 没记录（null / absent）」在所有报告面同形——BG→BN 七轮披露链断在最后一步。归档 1702 份 JSON 四键出现 **0**（BN 之后无批次；`contract_missing_symbols` 8865 处为 BL 之前历史行）。处置纯读侧披露、**判定值与方向一处不动**：新助手 `experiments/analysis_parts/check_leg_analysis._check_leg_measurability`（四通道 × 七档计数 + 三条恒等式）+ `analyze_results` 新章节「检查腿可测量性」（沉默臂按名列入「**不是「四腿都干净」**」而非渲染全零表）+ `run_main_batch` 摘要行（未记录明写「不可读作干净」）。**65 例新锁 + 既有 0 例改写**（五套件合跑 219 passed / 0 failed）；变异 **16 锚点全红** + 中性对照 0 红（采集面恒 219）；未新增门禁。**顺带收口存量红**：BD→BP 批次（b44a1aad）入库的 `scripts/tools/bo_raw_readside_fold_probe.py` 两个宽松 `json.dumps` 写点使严格 JSON 门禁在 HEAD 即红（门禁按 `git ls-files` 只扫**已跟踪**文件 ⇒ 入库前的门禁跑盲区；BP 收口「门禁全绿」声明与工件分裂，登记不追改）——补 `allow_nan=False` 两处（合成载荷、零行为变化）后门禁转绿，干净树上门禁链 19 步 rc=0。collected **11992** = passed 11987 + skipped 5（本会话沙箱确认跑实测 11973 / 19 / 0、198.25s / rc=0；沙箱与正常口径不混用）。`src/` 零改动 ⇒ 行覆盖与 BP 逐位相同（19393/19904 = 97.4327%）；弧覆盖 7103/7532 = 94.3043%（较 BP −2，三路归因：沙箱 skip 集 + xdist 重排，均非 `src/` 改动）。详见 CHECK_LEG_READERS_BQ_2026-10-22（分册已删除）。此前 **BP 轮：统计对照面把「这一行没记录污染级别」折成沉默——同一种缺席在两个消费者手里去向不同**。BO 收的是 raw 落盘面的读侧，本轮收同一批 `details` 行在**统计对照面**的读法：`analysis_parts/cross_analysis` 的 `if not level: continue` 对未记录行**一个都不记**，`statistical_analysis.contamination_view_summary` 的 `recorded or "unknown"` 却把它们**并计进 `unknown`**（与「检测跑了但判不了」同一个数），渲染层 5.3 的「未入对照任务」按前者加、脚注却按后一种口径解释前一种。归档实测 **159** 份含键批次文件 / **320** 臂：`key_absent` **2093** 行、值为 null **0** 行、精确空串 **0** 行；**122** 臂整臂无字段 ⇒ `available=False` ⇒ **5.3 节从报告里整节消失，与「这一节没跑」同形**；`high_vs_low_success_delta` 在两档不齐时**键直接缺席**，读者无从分辨「没算」与「算出 0」。处置只加平行披露、**判定值与判定方向一处不动**：缺席分 `key_absent` / `value_null` / `value_blank` / `other_falsy` 四档并给 `n_details` / `unobserved_total`，`available=False` 分 `no_rows` / `no_level_recorded`，delta 落成**显式 `None`** 并由 `delta_missing_buckets` 点名缺哪一档（归档 **198** 个可对照臂 **0** 个有差值：157 双缺、41 缺 high），5.3 表补未记录行数、沉默臂按名点名、`N/A` 单元格写明缺哪一档、全表算不出差时追加「≥0.2 / ≤0.2 判据在这批数据上无从应用」，②侧加 `unknown_of_which_absent`；两消费者恒等式 `view.unknown` = 真 unknown 行数 + `cross.unobserved_total` 在 **320/320** 臂成立。口径修正一处：`value_blank` 只收**精确空串**——空白串在批次 IX 侧是真值、自成一档，划进缺席会让恒等式在含空白串的语料上差 1，而归档恰好 **0** 行空白串，**探针与真归档同盲区、都测不出来**。**62 例新锁**（逐类例数取自 `--collect-only` 实测）+ 既有 92 例 **0 例改写**（四套件合跑 1415 passed / 3 skipped / 0 failed）+ **变异 18 锚点全红、采集面逐锚点恒 collected=154、中性对照 0 红、`# mutation:` 残留 0**；本轮未新增门禁；`src/` 与 `config.py` 写入面命中 **0** ⇒ 覆盖率与 BO/BN/BM 逐位相同（⚠️ 相同读数不证明 `src/` 零改动，依据是写入面普查）。确认跑 **11922 passed / 5 skipped / 0 failed、195.48s / rc=0**（collected **11927**）。详见 BP 手册（分册已删除）。此前 **BO 轮：raw 落盘面的读侧把「没落盘 / 键不在 / 值是 null / 件读坏了」折成实测——而落盘开关态自己也不落盘**。BN 把四值 `status` 落到了盘，本轮量的是消费这些工件的 `experiments/` 读侧五处站点，它们共同的写法是 `x = state.get(key) or []` 再 `len(x) == 0`——「读到空」与「没读到」在同一个 `if` 里。① `--save-state` 决定 raw 存不存在，可实测 **246 份批次 JSON 里该值 0 出现**、provenance 15 个键里没有它，而磁盘 **34** 个 `raw/` 目录只有 **88** 份文件入库、只覆盖 **6** 个批次目录（`.gitignore:172` 忽略 `experiments/results/**`）⇒「没开 / 开了但没随归档留存 / 开了且留存」三种世界事后同一个观察，处置是 provenance 补 `"save_state": bool(save_state)`（只对新批次生效，**不改默认值**）；② `cross_file_root_cause` 把三种缺席折成「实测 0 条依赖边」的 `DEP_GRAPH_INCOMPLETE`——真实批次两臂复放（9 臂 29 例多文件失败）**改前 14 例判定随 raw 目录给不给翻转**、本轮分档后 **18 例**（多出的 4 例是改前两臂同折、翻不出来的键级缺席），`level1` 两臂恒 0 例；现分 `RAW_UNAVAILABLE` / `DEP_INPUT_ABSENT` / `DEP_INPUT_NULL` 三档、`dep_edges` 由 `0` 回 `null`，报告再加 `raw_coverage` / `rule_evidence` / `unreachable_rules` 自证：可达性按**值非 null** 判（BN 起白名单恒写键，「键在场」不再是证据），`ROLLBACK_CONSERVATIVE` / `TOPOLOGICAL_ORDER` 按构造零证据、由报告点名而不是从分布里被读成「没有这种根因」；③ `position_aware_ab` 的四条不可计算腿（raw 目录缺席 / 任务件缺席 / `position_aware_focus` 键缺席 / `details` 不可用）改前与「实测定位全未命中」**数值同形 = True、文本同形 = True**（都是 `0.0`、都印 `0.0%`）——`0.0` 不是保守值，是缺席造出来的读数；现按十档 grade 点名（`-1.0` 沿用既有「不可计算」数值档，不新增取值域），另收一条更窄的折档：`focus=null` 且该行**确有**修复轮次或补丁时，改前会进分母记一次实测未命中；④ `compare_failures` 改前只有**两臂都缺**才有一行披露、损坏 JSON 直接掀翻整份报告、空产物 `{}` 与「件不存在」同一句，现逐臂点名缺席形态、坏件记 `unreadable` 不抛穿、空产物自成一档；⑤ `cross_file_ab` 跑批后提示的根因命令不带 `--raw-dir`，**照抄一次就把 14 例折进结构档**，本轮补上该参数。**判定值与判定方向不变**（缺席只披露，不归因、不拒绝）；真语料零影响实测：八臂定位读数现场复算与归档**逐位相同**（21.43 / 0.0 / 0.0 / 0.0 / 25.0 / 0.0 / −1.0 / −1.0）、236 条 details 形态 = 键在且为空 **156** / 键在且有内容 **80** / 键不存在 **0**、311 份 `aitester.json` 的 `cross_file_deps` = 键不存在 **216** / 非空列表 **95** / 值为 null **0** ⇒ `DEP_INPUT_NULL` 在归档里 0 实例（该腿为 BN 之后的新批次而准备）。**70 例新锁**（逐类例数取自 `--collect-only` 实测）+ 既有 2 例按新口径改写（「保守 `0.0`」→ `-1.0` + grade，用例数不变）+ **变异 23 锚点全红、采集面逐锚点恒 collected=70、中性对照 0 红、`# mutation:` 残留 0**；本轮未新增门禁；`src/` 与 `config.py` 写入面命中 **0** ⇒ 覆盖率与 BN/BM 逐位相同。详见 BO 手册（分册已删除）。此前 **BN 轮：状态通道运行时披露、归档工件里 0 出现——「检查崩了 / 没跑」在字节层与「检查干净」同形**。BH→BM 五轮建立的四值 `status` 只活在内存里：只读探针实测 `experiments/run_benchmark._dump_state_artifacts` 的 raw 白名单把 5 种运行时状态（`ok` / `error` / `unavailable` / `disabled` / 键不存在）折成 1 种 558 字节形状，而 `_build_task_result` 的「5 态 → 5 形状」全靠 BM 刚接上的 `contract_status` 一条腿撑住——**逐通道拆开测**才见 static / safety / oracle 三对通道在两道边界同样折档；存量归档普查（1700 份 JSON〔raw 1121〕+ 9096 行 JSONL）里这 7 个键 **0 命中 / 0 文件**。处置纯归位：白名单 +10 键、结果行两分支各 +6 键（失败分支 `None` 占位保持键集合同构），另加 BK 同族但**豁免额度为空**的新门 `scripts/gates/check_status_persistence.py`（`AITesterState` 声明的 10 个 `_status`/`_outcomes` 通道 ⊆ 每一个落盘面；`**helper(...)` 解析不出就不计入——宁可假红、不可假绿），已接 `make gates` 与 CI 独立阻断步骤。**判定值与判定方向逐字节不变**，历史工件一个字节不改（归档里 0 出现仍是 0 出现，本轮只买新批次的可复核性）。**54 例新锁 + 变异 24 锚点全红（采集面逐锚点恒 collected=54）+ 中性对照仅改注释措辞 0 红、`# mutation:` 残留 0**；确认跑零失败（读数见 BASELINE.yaml）；本轮 `src/` 零改动 ⇒ 覆盖率与 BM 逐位相同（⚠️ 相同读数不证明 `src/` 零改动，该主张的依据是改动面清单）。详见 BN 手册（分册已删除）。此前 **BM 轮：实验/报告读侧把「检测没发生 / 检测崩了」折成取值域最有利一档——崩溃记进「干净组」、未测记进「零回归」**。BL 把双读口径收在 `src/`，登记边界明写 `experiments/` 未做——本轮就是那块：`run_benchmark._compute_contamination_risk_level` 的崩溃腿 `return "low"` 返回的正是取值域里**最有利**的一档，而 `low` 在下游**就是干净组**（`statistical_analysis.contamination_view_summary.clean_n` 与 `analysis_parts/cross_analysis.high_vs_low_success_delta` 的对照基线）；`contract_status` 被 BL 写到实验侧结果行却没人读，`contract_unmeasurable(...)` 披露在实验产出的 `risk_summary` 里恒不出现；`run_main_batch._print_r4_summary` 的 R4/N1 分子只数 `== 1.0`、分母却是**全部行**，未测行按「没回归 / 没测试错误」计分，而 `0.0%` 恰好好读成「零回归」。四处处置全落在「披露 / 归位」侧：崩溃腿 → `unknown`（**修漏不是新设计**——同仓内层 `_combined_risk_level` 早在 O22 就为同一件事引入 `unknown` 并写明「异常时一律 fail-open 归 low」，本轮补的是漏改的包装器）、`contract_status` 透传给 `build_risk_summary`（分数 / 级别 / 因子逐位不变）、R4/N1 分母换成可测行数并印「可测 k/n」（`k=0` 时打印不可测而非 `0.0%`）、5.3 对照表补「未入对照任务」列。**判定值与判定方向不变**：`unknown` 不触发拒绝、不改 `passed`，只是离开干净组；③的分子仍是 `== 1.0` 的行数。真语料三组：崩溃腿可达性栅格 15 条改前 `{'high': 1, 'medium': 2, 'low': 12, 'unknown': 0}`、崩溃腿 5/15 命中且 5/5 折成 `low`，改后 `{'high': 1, 'medium': 2, 'low': 7, 'unknown': 5}`；归档 **8865** 处 `contamination_risk_level` = `not_applicable` 7843 + `low` 1022、非 str 补丁 **0** 行 ⇒ 崩溃腿在归档里 0 实例，①②对历史读数零影响；`regression_rate` 在 11197 行里可测 **0** 行（8012 `None` + 3185 缺键），`test_error_rate` 可测 7206/11197 ⇒ 现口径 7.3% vs 可测口径 **11.3%**（`single_agent` 一行 6.7% vs **94.0%**——换分母读出的新数，不得与历史值相减）。**32 例新锁 + 变异 9 锚点全红（红数 8/3/1/2/2/1/2/1/1）+ 中性对照 M10 0 红**；确认跑 11736 passed / 5 skipped / 0 failed、209.76s / rc=0（37 warnings；collected 11741）；`src/` 本轮零改动 ⇒ 覆盖率与 BL 逐位相同（19393/19904 行 = 97.4327% / 7105/7532 弧 = 94.3309%，未覆盖 511、缺弧 427）。**`make gates` 全链 rc=0**（回填前首跑、回填后终跑，各自单独执行、不与其他 pytest / 文档编辑重叠：两跑 rc=0、18 步命令 / 16 个目标全绿，墙钟 **211s / 213s**（`date +%s` 成对采集）；链内 pytest 为 xdist `-n 4 --dist loadfile` 且**不带 `--cov`**，两跑同判 **11736 passed / 5 skipped / 0 failed**（205.60s / 207.07s；`4 workers [11741 items]`，与确认跑同一采集面；警告总数 50 / 54，差值只落在 `test_spec_expr_property` 的 hypothesis `invalid decimal literal` 组，本轮未逐条归因 ⇒ 只登记两跑现值）；两跑链尾分步读数逐字节相同，`ast-guards` 与 BK 轮起逐位一致）。教训：红数必须与产生它的采集面一起登记（M1=83 / M2=91，「恒 32」那句已被复测否证）、同一个打印块里两套分母正是本轮缺陷的形状学来源、`94.0%` 这类换分母的新数与历史值相减即口径错配。详见 BM 手册（分册已删除）。此前 **BL 轮：发布侧已经带 status、判定侧仍按空值判定——“写了没人读”这一面的收口**。BH→BK 四轮把「读不懂」写进了观测键，但判定侧读不读从未验过：本轮普查实测 `assess_task_risk` 的形参表里没有 `contract_status`，四个 status 通道的**键名判定读点改前全为 0**。处置分三层：按腿取 status（新原语 `status_for_check(outcomes, check)`，`safety_check_status` 是两道独立预检的 worst-of 聚合、不能冒充契约腿；该腿没记录 ⇒ `None`）、消费侧双读（`risk_approval` 四处 + `graph/debugger.py:918` 调用点 + `agents/debugger.py:795` 静态层 + `patch_applier.py:507` S2 —— **只把文本追加进 note，`factor` 与 G2 判定逐字节不动**）、观测侧把 status≠ok 认成失败模式（第 **12** 条 `check_unmeasurable`：5 个 status 通道 × `error`/`unavailable` → MAST `Inadequate verification`，`_flatten_record` 同步抬平 trace 的 `output` 内层键）。发布面四处补齐（`nodes.py` per-leg 通道与 trace 载荷、`run_benchmark.py` 行、`state.py` 声明）。**`None` 与 `error` 必须分读**：归档 1702 文件里 `contract_missing_symbols` 出现 8865 次、其中 **8853 是 `None`**，把「没记录」当「没测成」会整批改判历史行；五个 status 键在归档中出现 **0** 次 ⇒ 历史读数零影响。**32 例新锁 + 变异 22 锚点全红（红数 2/3/1/2/1/3/1/1/1/1/1/3/2/1/1/1/1/1/1/1/1/1）+ 中性对照 0 红**（墙钟 86s、基线 collected=32 全绿、sha256 原字节还原、`# mutation:` 残留 0）；确认跑 11704 passed / 5 skipped / 0 failed、209.29s / rc=0（39 warnings；collected 11709）；覆盖率 **19393/19904 行 = 97.4327%** / **7105/7532 弧 = 94.3309%**，未覆盖 511 与缺弧 427 与 BK 登记**逐位相同**（本轮只回收自己新增的行与弧）。**`make gates` 全链 rc=0**（回填前首跑、回填后终跑，各自单独执行：两跑 rc=0、18 步命令全绿，墙钟 **213s / 214s**；链内 pytest 为 xdist `-n 4 --dist loadfile` 且**不带 `--cov`**：两跑同判 **11704 passed / 5 skipped / 0 failed**（用时 207.16s / 208.34s、warnings 54 / 46，collected 11709），链尾分步读数两跑逐字节相同；链首 ruff 974 文件已格式化、mypy 137 源文件 0 错；`ast-guards` 链内读数 136/78/20/0/20/19 与 BK 轮链外自测逐位相同）。教训：量具中途换口径会让改前/改后差值掺入仪器变更（只登记现值或重跑改前）、用被测集合自身遍历的锁是自证循环（删键跟着变短而不是变红，M11 存活）、不可达的语料组合会让变异假存活（“契约 ok + 危险 API error”在 `safe_apply_patch` 的 `ast.parse` 硬闸下根本触发不了，M17 存活；可达形状是 `disabled` + 聚合 `error`）、继承来的四位小数要重算（BK 的 97.4300% / 94.3200% 除得值实为 97.4288% / 94.3218%，两位小数判读不变）。详见 BL 手册（分册已删除）。此前 **BK 轮：`ast.parse` 守卫的捕获面棘轮——“读不懂”有两种异常，逐点收敛永远收不完**。单腿守卫（只捕 `SyntaxError`）接不住 Python 3.14.6 对**孤立代理位**文本抛出的 `UnicodeEncodeError`（`ValueError` 子类；null 字节抛的仍是 `SyntaxError` 本体，不算新腿），于是异常从“读不懂 ⇒ 降级”分支里**抛穿到调用方**——最直白的一处是 `static_validate_patch`：含代理位的候选补丁把整个 `_debugger_node` 抛崩。已经降级的分支又把“读不懂”折进**带判定含义**的空结果（`[]` / `set()` / 原码 / `ok=True`）。本轮把 5 个模块 **13 处**站点收敛到共享常量 `AST_UNREADABLE_ERRORS`、形态归因走 `unparseable_shape()`（fenced_block / git_diff / undecodable / syntax），13 处经 `outcome_sink` 侧信道披露、三个发布点写 `check_status` / `check_outcomes`，并新增 CI 阻断门禁 `scripts/gates/check_ast_parse_guards.py`（`make gates` 新目标 `ast-guards`）——**同一把尺子复测 HEAD 树**得 79 站点 / 35 单腿 / 违规 15（恰为 BK 13 + BJ 2），现树 136 文件 / 78 站点 / 20 未覆盖 / 违规 0，20 处存量按 `(站点数, 折叠形态)` 计额度且只允许变短。**判定值逐字节不变**：11 个判定面 × 14607 条输入 = 160677 项对账，`identical=160636 / escape_fixed=41 / both_raised=0 / UNEXPECTED=0`，41 条抛穿腿**全部来自人工形态栅格**（归档 14596 条贡献 0 实例）。**55 例新锁 + 变异 13 锚点全击杀（24/15/1/2/1/5/2/2/1/1/1/5/1） + 中性对照 0 红、`# bk-mutation` 残留 0**；全量确认跑 **11672 passed / 5 skipped / 0 failed、191.76s / rc=0**（collected 11677，无 `--cov`）；`make gates` 全链 **rc=0**（首跑墙钟 242s、`date +%s` 成对采集；链内 pytest **11672 passed / 5 skipped / 0 failed、193.90s**、47 warnings、collected 11677 与确认跑同一采集面；新门 `ast-guards` 链内读数与链外自测逐位相同；终跑（门禁句回填后再单独跑）rc=0、墙钟 198s、链内 192.95s / 44 warnings，链尾 47 行分步读数与首跑逐字节相同）。教训：开工普查的两套分母（125 站点 / 64 与 60 单腿）不可复现，登记以守卫自测为准；HEAD 不等于“本轮之前”（其下压着七轮未提交栈），基线归因要逐文件核；本轮自己的 +19 行打断 Prompt Card——改带 prompt 的源文件必须同批重跑生成器。详见 BK 手册（分册已删除）。此前 **BJ 轮：AST 断言一致性检查的「读不懂 ⇒ 无疑点」收口——`check_assertions` 两条腿各自带 status，`findings=[]` 不再单独算“扫过且干净”的证据**。检查器把“扫过且无疑点 / 输入为空 / 测试文本读不懂（从未扫描）/ 被测代码读不懂 ⇒ 类型推断通道哑火”折成同一个返回值。把 HEAD 版本接到真实消费点复现：**围栏整块产物、真语法错误产物、空产物三行与一次真实干净扫描的读数逐字节相同**（`oracle_findings=[] / tautological_count=0 / o4_triggered=False`），而 O4（恒真断言 ⇒ 标 `test_defect` ⇒ 路由回 Generator 重生成）是 generator 侧唯一的写侧路径、对读不懂的产物**恒不触发**；被测侧读不懂时类型推断通道哑火，读数与“类型都一致”相同；含孤立代理位的产物在旧口径下让 `ast.parse` 抛 `UnicodeEncodeError`（`ValueError` 子类而非 `SyntaxError`）**抛穿观测层**。处置：`check_assertions` 新增可选 `outcome_sink`，逐腿追加 `{check, status, reason}`（四值 `ok / disabled / unavailable / error`，沿用 BI 上收的单一事实源 `src/utils/check_status.py`，本轮是其第 4 个消费点）；三条实现口径各上有向锁——**盲区早退不记第二腿**、**围栏归因判据 = 剥前导空白后以三反引号开头**（与“正文里出现过围栏”两种写法在真语料上差 **1 条**，由不 import `src/` 的 `scripts/tools/bj_discriminator_crosscheck.py` 独立复核：`sites=10855 / unparsable=76 / strict=72 / loose=73 / loose_only=1`）、**解析面收敛到 `parses_as_module`**（本轮唯一披露的行为变化）；`_run_generator_postchecks` 按 **worst-of** 聚合（两腿彼此独立 ⇒ 最差者优先，与 BG 的“任一后端 ok ⇒ ok”方向相反，两个方向同时上锁）并写入图状态通道 `oracle_check_status` / `oracle_check_outcomes`（两键在 TypedDict 显式声明、默认 `None`，未声明键会被 LangGraph 静默丢弃；键名经 grep 实测避开 `experiments/oracle_quality_replay.py:1254` 已占用的规约 oracle `oracle_status`，并上锁声明两者不是同一字段）。**判定值与判定方向逐字节不变**：不剥围栏、**没有**把“读不懂 ⇒ 零疑点”翻成拒绝——真语料 10855 条产物 HEAD-vs-现版 `repr(findings)` 逐条比对**0 差异**（`crashes_old=0 / crashes_new=0`）；变异面里专门放三条“判定翻转”锚点，正是为了阻止后续顺手改判定。**63 例新锁 + 变异 23 锚点全红（9/2/9/1/11/5/3/3/3/1/2/8/8/2/1/2/50/8/1/1/7/20/1）+ 中性对照 0 红**（collected 全程 501）；真语料：`generated_test` 站点 **10855** 条 = 真扫过 10671 + 空输入 77 + 围栏块 72 + 无断言 31 + 语法错误 4（其中 76 条“读不懂”旧口径与真扫过逐字节相同），第二腿只记 `disabled:target_not_provided = 10702` = 10855 − 153 ⇒ `error:unparseable_target` 在语料里 **0 实例**（按名登记，不写成“已排除”）；声明开启开关的 **57** 份归档里盲区站点恰 **1** 个；`oracle_findings` / `tautological_count` / `o4_triggered` 在 1594 份可解析归档中出现 **0** 次 ⇒ 新通道零历史读数、零回填；登记前一跑 **11616 passed / 1 failed / 5 skipped、197.48s**（collected 11622；唯一失败 = 基线守卫：实收 11622 − 声明 11554 = 68 > 6 容差）；确认跑 **11617 passed / 5 skipped / 0 failed、192.77s、rc=0**（xdist `-n 4 --dist loadfile`，collected 11622 = 11617 + 5 + 0，与登记前同一采集面；63 warnings；同树串行单进程对照 521.41s / rc=0，用时口径须写明并行度）；覆盖率登记口径 **19272/19793 行 = 97.3678%** / **7072/7504 弧 = 94.2431%**（未覆盖 523 → 521 恰在 ±2 抖动域边缘、缺弧 432 → 432 逐位不变）；mypy **137** 源文件零问题；`make gates` 全链 **rc=0**（首跑墙钟 198s、链内 **11617 passed / 5 skipped / 0 failed、192.51s**、54 warnings、collected 11622；复验跑墙钟 198s、链内 192.46s、13 warnings；两跑各 90 行分步读数在归一化用时与 warnings 计数后 `diff` 为空；终跑（上述全部登记文本回填之后再单独跑一次）rc=0、墙钟 **197s**、链内 **192.06s**、66 warnings，其 88 行门禁分步读数（不含 pytest 警告噪声行）与前两跑逐行相同；此前另有一次在 0s 处停在 lint 步转 `rc=2`，那次没有门禁读数可引）。详见 BJ 手册（分册已删除）。此前 **BI 轮：写盘前两道静态预检的「读不懂 → 通过」收口——`check_naming_contract` 与 `dangerous_api_added` 各自带 status，空结果不再单独算“预检通过”的证据**。两道守卫把“比较过且没有符号被删 / 没有新增危险调用”与“输入读不懂、根本没比较”折成同一个返回值。把 HEAD 版本接到真实消费点复现：**补丁前原文用当前解释器不接受的语法（py2 `print` 语句）时，删除模块级常量 `CONST` 的补丁 `applied=True` 直通写盘、零条 warning**，`contract_missing_symbols` 保持 `null`——与一次真实干净比较的读数逐字节相同；只有补丁侧读不懂时，守卫报“补丁删除了 2 个模块级符号”，一句关于从未发生的比较的假陈述。处置：两守卫新增可选 `outcome_sink`，逐条追加 `{check, status, reason}`（四值 `ok / disabled / unavailable / error`，与 BG 词表逐字相同；词表与聚合函数上收单一事实源 `src/utils/check_status.py`）；`_check_patch_safety` 按 **worst-of** 聚合（两道守卫彼此独立 ⇒ 最差者优先，与 BG 的“任一后端 ok ⇒ ok”方向相反）并写入图状态通道 `safety_check_status` / `safety_check_outcomes`（两键在 TypedDict 显式声明、默认 `None`，未声明键会被 LangGraph 静默丢弃）；`type_repair_layer` 的历史 `contract_ok` 补配 `contract_status` / `contract_reason` / `contract_outcomes`。**判定值与判定方向逐字节不变**：本轮把沉默翻成披露，**没有**把“读不懂 ⇒ 保守放行”翻成拒绝；变异面里专门放两个“判定翻转”锚点，正是为了阻止后续顺手改判定。**50 例新锁 + 变异 19 锚点全红（4/2/1/5/1/5/1/1/4/4/1/2/1/1/1/2/1/4/7）+ 中性对照 0 红**（collected 全程 452）；真语料：`contract_missing_symbols` 在 **172** 份归档 JSON 的 **8865** 处取值中有 **8853** 处是 `null`——正是四义折叠留在历史读数里的足迹——而归档不保存补丁前原文（`target_code` **1** 处对 `patch` **11101** 处）⇒ 无法反向重算，零回填；登记前一跑 **11553 passed / 1 failed / 5 skipped、213.52s**（collected 11559；唯一失败 = 基线守卫：实收 11559 − 声明 11504 = 55 > 6 容差）；确认跑 **11554 passed / 5 skipped / 0 failed、212.07s、rc=0**（collected 11559 = 11554 + 5 + 0，与登记前同一采集面）；覆盖率登记口径 **19247/19770 行 = 97.3546%** / **7064/7496 弧 = 94.2369%**；mypy **137** 源文件零问题；`make gates` 全链 **rc=0**（首跑墙钟 217s、链内 11554 passed / 5 skipped / 0 failed、212.22s；复验跑墙钟 208s、链内 202.03s；第三跑 200s / 195.21s、终跑 201s / 195.73s，四跑 rc=0 且其余门禁读数与首跑逐行相同）。详见 BI 手册（分册已删除）。此前 **BH 轮：G5 testless 验证四层的「不可测量 → 验证通过」收口——每层带 status、顶层取最差层，`passed=True` 不再单独算“验证通过”的证据**。`src/tools/testless_validation.py` 的 AST 符号守卫 / mypy / 命名契约 / 导入冒烟四层把“这层根本没测成”与“这层测完且零缺陷”折成同一个 `passed=True`。**根因实测坐实**：mypy 层长期传 `--silent-imports`（mypy 1.15.0 已无此旗标，实跑 rc=2），干净 / 类型错误 / 语法错误三种输入返回逐字节相同的“mypy 发现 1 处问题”，该层从未真正检查过代码；本轮改传 `--follow-imports=silent` 并以 argv 断言 + 真 mypy 端到端 3 例上锁。处置：每层 `status` 四值 `ok / disabled / unavailable / error`，顶层 `validation_status` 取最差层（error > unavailable > disabled > ok，与 BG 的“任一 ok ⇒ ok”方向相反——四层是独立校验层）+ `degraded_layers`，非 ok 时 warning 点名 `层=status:reason`；只把未披露的假干净翻成 fail-closed，已披露降级（开关关 / 未安装 / 超时 / OSError）的 `passed` 不动；`nodes.py` 消费点补记“不构成验证通过的证据”。真语料 `TESTLESS_VALIDATION_ENABLE` 在 100 份归档 JSON 的 107 处取值全为 `null` ⇒ 历史读数零影响、零回填。**52 例新锁 + 变异 11 锚点全红（7/4/1/5/2/1/8/2/1/1/1）+ 中性对照 0 红**；登记前一跑 11503 passed / 1 failed / 5 skipped、218.93s（collected 11509）；确认跑 **11504 passed / 5 skipped / 0 failed、212.17s、rc=0**；`make gates` 全链 **rc=0**（首跑墙钟 263s、链内 11504 passed / 5 skipped / 0 failed、213.22s；回填读数后验证跑 219s 亦 rc=0）。详见 BH 手册（分册已删除）。此前 **BG 轮：静态类型检查的「不可测量 → 假干净」收口——mypy / pyright 未跑成时不再返回与“零疑点”相同的空结果，空 findings 只有 `status=ok` 才是证据**。`_run_mypy_findings` / `_run_pyright_findings` 旧实现对开关关 / 未安装 / 超时 / 崩溃 / 退出码异常 / 报告损坏一律返回 `[]`，与“检查完成且确实零疑点”不可区分；`mypy_findings_count=0` 把四种状态折成一个 0。每次尝试现经 `outcome_sink` 记录 `{backend,status,reason}`，status 四值 `ok / disabled / unavailable / error`；`type_repair_layer` 聚合为 `static_check_status` / `static_check_outcomes`（任一 ok ⇒ ok，否则 error > unavailable > disabled），error 时发 warning 点名后端与原因，两键随 debugger 写入图状态（TypedDict 显式声明，确定性修复同键）。pyright 的空 stdout / JSON 损坏 / 缺 `generalDiagnostics` / 超时 / rc 非 0/1 均判 error；已解析的疑点保留，但文本兜底不会把空输出升成 ok。真语料：`TYPE_CHECK_ENABLE` 默认关，**170/170** 份归档结果该键均为 `null`，实验侧只在环境快照登记 ⇒ 历史读数零影响、零回填。**25 例新锁 + 变异 8 锚点全红（1/3/1/2/1/1/3/2）+ 中性对照 0 红**；登记前一跑 **11449 passed / 3 failed / 5 skipped、202.57s**（collected 11457；失败 = 基线守卫 + debug 键集合契约 + prompt card，后两者已修正）；行 97.32%（19111/19637）/ 分支 94.14%（7006/7442）。详见 BG 手册（分册已删除）。此前 **BF 轮：脚本工具链 rc==0 判绿收口——self-mutation 与模板验证器接「有效通过」，空套件不再记成存活 / 自洽**。BA–BE 逐层收口 M1 / experiments / MDO / 生产路径后，`scripts/tools/` 仍有两处以裸 `rc==0` 判绿：`self_mutation.py` 的 preflight 基线门（全 skip 基线记绿，其后的变异体不可能被真实杀死）与变异体分类（全 skip / xfail / deselect 的变异体记 `survived`，无证据压低 mutation score），`verify_synthetic_templates.py` 的 buggy / fixed 两侧（全 skip 的 fixed 侧记“gold 自洽”，模板带假证据进检测率分母）。修法：四处统一走 `run_has_effective_pass(rc, output)`（`rc==0` 且至少 1 个真实 passed、0 failed；部分 skip 仍有效；摘要不可解析 fail-closed），超时仍优先判非绿；基线无有效通过记 `baseline_no_effective_pass` 并默认阻断（`--allow-red-baseline` 才继续并标 `measurement_valid=false`），变异体 `classify_result(rc, timed_out, output)` 记 `invalid` + `no_effective_pass:<counts>`（不进分数分母），模板两侧各报“无有效通过”。真语料 self-mutation 80 变异体行逐行相等（score 0.7467 不变）、模板 50/50 通过 ⇒ 历史读数零影响、零回填。**20 例新锁 + 变异 8 锚点全红（2/2/5/1/1/1/2/42）+ 中性对照 0 红**；登记前一跑 **11426 passed / 1 failed / 5 skipped、201.04s**（collected 11432；唯一失败 = 基线守卫）；行 97.31% / 分支 94.12% 与 BE 逐位相同。详见 BF 手册（分册已删除）。此前 **BE 轮：生产路径 rc==0 判绿收口——六处判绿点接「有效通过」，空套件不再记成修复正确**。BA–BD 逐层收口 M1 / experiments / MDO 后，生产路径仍有六处以裸 `rc==0` 判绿：检测门 `_run_test_against_code`、本地执行器、venv 沙箱、Docker、仓库节点、P2P 回归。全 skip / xfail / deselect 的套件 rc 同样是 0，旧实现把它们记成“修复正确 / 补丁安全”：检测门误判缺陷特异、执行器带假 passed 进入下一轮、`failed_cases` 为空骗过 F2P/P2P、P2P 在 fail-closed 下也不回滚。修法：新增 `run_has_effective_pass(rc, output)`（`src/utils/pytest_output.py`）作为执行级唯一判绿入口（`rc==0` 且至少 1 个真实 passed、0 failed；部分 skip 仍有效；摘要不可解析 fail-closed），六处接入；检测门记 `unavailable`（不记 over_red）、执行器新增 `error_info.type=no_effective_pass`、仓库节点记 failed case、P2P 记 `regression_error`（fail-closed 时 `regression_failed`）；A16 尝试记录新增 `effective_pass`，fail→pass 只认有效通过（全 skip 重跑不再制造假 flaky）。真语料 11197 行 / 5884 passed / 静态全 skip 0 / 50 条 repo_verification 全 failed / P2P 归档无 verdict ⇒ 历史读数零影响、零回填。**40 例新锁 + 变异 8 锚点全红（3/1/1/1/2/2/1/33）+ 中性对照 0 红**；确认跑 **11407 passed / 5 skipped / 0 failed、199.06s、rc=0**（collected 11412）；行 97.31% / 分支 94.12%；`make gates` 全链 rc=0。详见 BE 手册（分册已删除）。此前 **BD 轮：测量模块自己的 rc==0 判绿收口——MDO 基线与变异体接“有效通过”，谓词上移单一事实源**。BA–BC 逐层收口 experiments 侧后，`src/measurement/mdo.py` 仍以裸 rc==0 判绿：基线全 skip / xfail / deselect 时同样 rc==0，若不短路则每个变异体也以 rc==0 收场 → measured 且 MDR=0（把“没跑起来”记成判别力）；变异体侧 rc==0 但无有效通过被记成“未判别”，无证据地压低 MDR。修法：基线在 rc!=0 与执行错误判据之后、探针之前短路为 not_measurable（`test_not_green_on_base(no_effective_pass)`）；变异体无有效通过单列 `no_effective_pass` 并排除出 MTR/MDR 分母（披露 `mdo_no_effective_pass`；全部排除 ⇒ `mutant_runs_no_effective_pass`）；计数解析与谓词上移 `src/utils/pytest_output.py` 单一事实源，`_m1_metrics` 以同一对象别名保持约 20 个消费点与既有锁零改动。真语料 4044 条含 MDO 行 / 624 条 available / MDR=0 的 available 行 0 / 模块级全 skip 0 ⇒ 历史读数零影响。**15 例新锁 + 变异 6 锚点全红（8/2/24/21/2/1）+ 中性对照 0 红**；确认跑 **11367 passed / 5 skipped / 0 failed、222.87s、rc=0**（collected 11372）；行 97.31% / 分支 94.11%；`make gates` 全链 rc=0。详见 BD 手册（分册已删除）。此前 **BC 轮：重放对账工具的 rc==0 判绿收口——misguided_metrics 三处任务级判据接“有效通过”**。本模块逐测试四分类早已把 skip 单列为“无 pass/fail 信号”，任务级重放判绿却只看 rc（内部不一致）：`replay_detection` 的 fixed 侧无有效通过 ⇒ `None`（判据顺序与 `_m1_metrics` 对齐）、`replay_fixed_green` 无有效通过 ⇒ 保持 `None`（未演示 green 不是 False）、`_verdict_agreement` 无有效通过 ⇒ `not_applicable`（不记 mismatch 冤枉归档）；新增 `_side_has_effective_pass`（outcomes 优先 + 摘要行回退 + fail-closed）。真语料 350 任务行 / 700 侧零 all-skip-at-runtime ⇒ 历史读数零影响。**35 例新锁 + 变异 5 锚点全红（5/3/4/14/1）+ 中性对照 0 红**；确认跑 **11352 passed / 5 skipped / 0 failed、195.47s、rc=0**（collected 11357）；`make gates` 全链 rc=0。详见 BC 手册（分册已删除）。此前 **BB 轮：rc==0 判绿消费点的剩余收口——experiments 侧 11 处接共享有效通过谓词**。BA 轮建立 `_suite_has_effective_pass` 后，本轮将同一判据传播到 `experiments/` 全部剩余的 pytest 套件判绿点（全仓普查 11 处）：gold 自洽性审计 / 过红 P4 复跑（P5 新模式）/ GCP 块剪枝 / testlevel 任务级判据 / ULT gold 诊断归因 / SRP 见证安全门 / 四个健全性门 / mutation_testing 基线诊断——全 skip / xfail / deselect 的套件（rc==0 但 passed==0）不再计成有效 green，一律 fail-closed。`misguided_metrics` 三处对账与 `src/` 生产路径保留原口径待专门轮次。真语料 246 份归档零模块级全 skip ⇒ 历史读数零影响。**60 例新锁 + 11 变异锚点全红（2/2/2/1/2/2/2/2/2/2/1）+ 中性对照 0 红**；确认跑 **11317 passed / 5 skipped / 0 failed、243.69s、rc=0**（collected 11322）；`make gates` 全链 rc=0。详见 BB 手册（分册已删除）。此前 **BA 轮：rc==0 不是有效通过——全 skip / xfail 的套件没有断言执行**。pytest 对没有任何断言执行的套件同样返回 `rc==0`，旧实现只看 `rc`：detection 的 fixed 侧与 repair 的 gold 侧各有一条假阳性通道（全 skip 也记 1.0），重放工具给出 `correct`，变异检测把"测试没跑"误报成"测试没有检出力"（rate=0.0）。新增共享谓词 `_suite_has_effective_pass`（至少 1 个 passed 且 0 failed；部分 skip 与真实 passed 并存仍有效；摘要不可解析判 False），四处消费点接入，无有效通过一律 fail-closed（None / unverifiable / skipped）。真语料 246 份 benchmark / 9358 条生成测试 / 114 条带标记 / 12 条 detection=1.0（均为条件性标记，无模块级全 skip）、736 份 gold 套件 / 2 份含标记 / 0 份全 skip、4895 条 mutation 行 / 1376 条已测 / 132 条含标记。**35 例新锁 + 6 锚点全红（14/1/3/3/1/2）+ 中性对照 0 红**；登记前 11256 passed / 1 failed / 5 skipped、覆盖率 19002/19528 = 97.3064% / 6960/7396 = 94.1049%（`src/` 零改动）；确认跑 **11257 passed / 5 skipped / 0 failed、204.07s、rc=0**。详见 BA 手册（分册已删除）。此前 **AZ 轮：量纲与尾部不得被实现悄悄改写——Cohen's g 是 0–0.5 不是 2g，精确 p 不得被 epsilon 抬高**。`emse_stats_extensions.cohens_g` 返回 `abs(n10−n01)/(n10+n01)`（2g，0–1），与声称的 Cohen's g（0–0.5）量纲错位；`binom_exact_two_sided` 对 `p=0.5` 带 `1e-12` 容差，把 113/0 的 **1.926e-34** 抬成 ~1.93e-12。现 g 改 effectsize 口径 `abs(n10−n01)/(2*(n10+n01))`，精确尾改整数权重 `math.comb` 精确比较、非 0.5 分支按概率序双侧；真批次读数更正为 g 0.370 / 0.500 / 0.423 / 0.500（原 0.739 / 1.000 / 0.846 / 1.000），p 更正为 1.716e-13 / 1.926e-34（12/80 与 113/0）。受保护归档 20261016 零改写（sha256 复验 OK），修正值重发 20261021；论文 / EMSE 骨架 / 复现包 / X 轮勘误同批改引；21 例新锁 + 变异 M1 11 红 / M2 4 红；确认跑 11222 passed / 5 skipped / 0 failed、187.56s、rc=0。详见 AZ 手册（分册已删除）。此前 **AY 轮：读取层保真、判定层收口——`run_b8` 不得用 `or {}` 改写载荷形状，假值非对象不是免费**。AX 收口三处汇总读点后，`run_b8` 的载荷组装仍以 `or {}` 兜底：`_load_arm` 把假值非对象（`[]` / `""` / `0` / `False`）改写成 `{}`——"载荷坏了"冒充"没有 metrics"，`_arm_summary` 据此报 **$0.0 且无任何机制名**；`_load_harness_smoke` 先用原始载荷算成本、再把行内 `token_metrics` 存成改写后的 `{}`，金额与证据来自两份不同载荷。修法：读取层原样保留载荷（缺席 / `null` 仍是 `None`），成本判定只留在 `_cost_usd` 一个点——历史 0 只限缺席 / `null`，假值非对象与真值非对象走同一条拒绝路径（`None` + `token_metrics_not_object:<T>`）。真语料 14 份 JSON / 6 份 benchmark / 12 个 `token_metrics` 键全为 dict、零坏值；两份臂成本与四行冒烟金额逐位不变，受保护工件不重写；**27 例新锁 + 6/6 变异锚点转红**（红数 13/6/8/5/6/8）；确认跑 11201 passed / 5 skipped / 0 failed。详见 RUN_B8_PAYLOAD_AY_2026-10-21（分册已删除）。此前 **AX 轮：基准/全栈汇总的呈现与聚合读点也有值域——呈现可以折历史 0，均值不可以**。AW 收口逐臂统计后，`run_benchmark` 终端 Token 效率两行仍以 `%d` / `%.2f` 直出聚合对象（上游合法 `None` 让完整基准在收尾抛 `TypeError`），全栈 G8 表 `bl.get("token_metrics", {})` 兜不住 `null` / 非对象且坏值原样印出，`summarize_full_stack` 用 `or {}` + `float()` 求均值（真值非对象中止整份汇总、假值非对象静默跳过、bool/字符串/负数/非有限值进均值）。修法：三处统一接共享 `token_metric_reading`——呈现层缺席 / null 仍是 AE2 历史 0、在场坏值落 `不可读` + 机制名（终端另发 warning，不中止）；均值缺席块沿历史跳过，任一在场块不可读 ⇒ 该基线 `None` + `avg_total_tokens_reason`，不给部分均值、不连坐任务统计与其他基线。真语料 64 份顶层 benchmark / 递归 324 个 `token_metrics` 键（246 个 `results.<baseline>` 汇总块 + 78 个嵌套形状）零坏值；246 个汇总块终端文本、全栈干净行、四基线均值逐位不变（6 个 PREFLIGHT 嵌套块缺 `avg_tokens_per_task`，不参与终端对照）；48 例新锁 + 8/8 变异锚点转红；确认跑 11174 passed / 5 skipped / 0 failed。详见 SUMMARY_TOKEN_READERS_AX_2026-10-21（分册已删除）。此前 **AW 轮：T1/B2 逐臂统计的 `token_metrics` 形状与事件计数也有值域——坏形状不中止分析，事件计数不是免检通道**。AV 收口 `add_cost` 后，`arm_stats` 仍以 `res.get("token_metrics") or {}` 兜底：真值非对象（`"abc"` / `True`）在 `.get` 上抛 `AttributeError` 中止整批分析，假值非对象（`[]` / `""` / `0`）被静默改写成 `{}`——"载荷坏了"冒充"没有 metrics"；`"calls": tm.get("total_llm_calls")` 把事件计数原值直出，bool / 数字字符串 / 小数 / 负数与池化列（`sum_token_metric_values` 会拒绝同一份值）在同一报告里互斥。修法：整份 `token_metrics` 原样保留交下游共享读取器判定；`calls` 过 `token_metric_reading`——缺席 / null metrics / 字段缺席按 AE2 历史 0，字段在场却读不动 ⇒ `None` + `calls_reason`（去重后以竖线拼接，仅非空写入），事件计数与 token 金额互不连坐。真语料 324/324 逐臂读数干净；T1/B2 入库报告 18/18、原始批次新臂 9/9 逐位复现，重算 `ANALYSIS_REPORT.json` 逐字节相同（35542 字节），受保护工件零改动；22 例新锁 + 6/6 变异锚点转红（0 逃逸）。确认跑 11126 passed / 5 skipped / 0 failed、179.21s、rc=0；行 19002/19528 = 97.3064% / 弧 6960/7396 = 94.1049%（`src/` 零改动）。零 LLM、$0。此前 **AV 轮：T1/B2 分析侧的成本入口同样有值域——单侧未知不是部分和，未知金额不是字符串 `None`**。AU 收口实验侧三个聚合器后，`analyze_t1_b2_main_batch.add_cost` 仍用 `stats.get("token_metrics") or {}` + `tm.get(...) or 0` 直接计价：`token_metrics=None` 折 0、`input=None` 仍按输出侧给部分和、`True` 当 1、小数直接相乘、负数编出负金额、`nan`/`inf` 进报告、字符串抛 `TypeError`、非对象抛 `AttributeError`；片段渲染把未知金额印成 YAML 字符串 `None`。修法：两个 token 字段过共享 `token_metric_reading`，整份 metrics 缺席 / `null` / `{}` 仍是历史 0（AE2），字段在场却读不动 ⇒ `cost_usd=None` + 去重后以 `|` 拼接的机制名、不给部分和；YAML 未知金额一律 `null`，未知 token 落 `不可读`。真实批次 18/18 逐 seed 成本只读复算逐位一致、入库片段逐字节相同；**19 例新锁 + 6/6 变异锚点转红**；确认跑 11104 passed / 5 skipped / 0 failed；行 97.31% / 分支 94.10%。此前 AU 轮：**实验侧的成本/用量聚合器也把未知当零——读不动不给数字、部分和不冒充全额**。AI–AT 把共享读取器与报告侧读端收口后，`estimate_cost_usd` / `generation_summary` / `usage_totals` / `run_b8._cost_usd` 仍各自 `int/float(... or 0)`：`None` 变免费、bool/小数/数字字符串被改写、负数与非有限值进金额、AT 写拒绝标记在汇总里消失、总额把一侧未知与另一侧金额相加、README 印 `$None`。修法：金额与计数统一走共享值域，缺席才是历史 0、读不动给 `None` + 机制名，任一字段不可读整笔阻断；事件计数独立；命中列只依赖本列；`cost_total_usd` 与含冒烟总额任一侧未知即 `None` + 合并披露；README 统一「不可读 / 无法估算（机制）」。真语料 37/37 b8 成本与 6/6 generation 成本只读复算一致；**62 例新锁 + 7/7 变异锚点转红**；确认跑 11085 passed / 5 skipped / 0 failed；行 97.31% / 分支 94.10%。此前 AT 轮：**写入侧的 token 计数同样有值域——被拒绝的写入不是零，且必须可追溯**。读端在 AI–AS 各轮把「零 / 缺席 / 读不动」逐层分开后，写入端仍在用 `int(... or 0)` 静默转计数：bool 记 1、float 截断、数字字符串收下、负数进入累计、`nan`/`inf` 与不可解析字符串崩溃；缓存文件的坏 `tokens` 还可能把一次真实缓存命中变成一次真实 LLM 调用。修法：`record_usage` / `record_cache_hit_usage` 统一走共享谓词 `count_reason`，拒绝写入不写计数但 `llm_calls` / `cache_hits` 事件仍 +1，机制名只在非空时写入 `token_write_reasons` / `cache_write_reasons`；读端以 `token_write_rejected:<mech>` / `cache_write_rejected:<mech>` 把整行判为不可读，`otel_export` 不导出 token 属性；`write_rejection_count` 让缓存 `tokens: null` 的「未知」区别于历史缺席。真语料 1701 个 trace 文件 / 10629 条 `token_usage` 零坏值、存量读数逐位不变；**62 例新锁 + 19/19 变异锚点转红**；确认跑 11023 passed / 5 skipped / 0 failed；行 97.31% / 分支 94.10%。此前 AS 轮：**生产端标识先写对——32/16 位、root、parent 指向**。AR 在导出端补上规范化与派生后，`TraceSession` 仍在写 16 位 `run_id`、12 位 `span_id`，`task_start`/`task_end` 无标识，`parent_span_id` 在全语料从未出现；真语料 9086 文件 / 110926 条 node：61188 条带 16/12 位标识、49738 条无标识（全部早于 O7）、9085 条 `task_start` / 9046 条 `task_end` 全无标识、parent 0 次。修法：32 位 `run_id`、16 位 root / 子 span，`task_start` 在文件与内存两种模式都写 root，node/task_end 的 parent 指向 root；结构标识按字段名 + 形状精确豁免通用 32+ hex 脱敏（普通文本长 hex 仍脱敏）。生产端 trace 直接导出为单 trace、无 synthetic root、无披露，两次导出逐字相等；**10 例新锁 + 18/18 变异锚点转红**；确认跑 10961 passed / 5 skipped / 0 failed；行 97.29% / 分支 94.06%。此前 AR 轮：**OTel 导出的标识先合法再谈稳定——单 trace、32/16 位 hex、确定性派生**。`otel_export` 过去把 `run_id` 原样当 `trace_id`（真实 16 位 hex）、`span_id` 原样导出（真实 12 位 hex），都不符合 OTel；缺失标识每次导出生成随机 uuid，node 又拿 `run_id` 覆盖文件级 trace，实测 **8002 个文件出现两个 trace、61188 条 parent 断链、9086/9086 文件重复导出标识不一致**。修法：标识规范化为 32/16 位小写 hex（短 hex 左补零、大小写归一；非字符串/空串/非 hex/超宽/全零不可导出），一个文件一个 trace_id，缺失/非法按 SHA-256 确定性派生，同 trace 内冲突改派生并披露 `span_id_duplicate`，字符串属性只导出 `str`；真实语料 9086 文件 / 129058 span 全部单 trace、标识合规、parent 闭合、零披露、重复导出逐字相同；**48 例新锁 + 16/16 变异锚点转红**。此前 AQ 轮：**OTel 导出边界也要数值值域——坏 token 不泄漏、坏时间戳不炸整份文件、静默丢弃要披露**。`otel_export` 过去把记录数值原样写入 span：bool/str/小数/负数/nan/inf/容器都能进 `gen_ai.usage.*`，非有限 `ts`/`duration_ms` 让 `int()` 抛错并中止整份文件，非对象 `token_usage` 被静默降级成"没有 token 属性"。修法：token 计数复用共享 `count_reason`，时间/duration/budget 只收有限非负数、坏值回落 0 哨兵并点名，iteration 复用计数谓词，机制名写入 `aitester.export_value_reasons`；真实 9086 文件 / 129058 span 零披露、18 份稳定文件逐字不变；61 例新锁 + 12/12 变异锚点转红。此前 AP 轮：**五处报告侧聚合 token 汇总也各持宽松折叠——池化、冒烟、A/B、分组均值、成本表不得各算一遍**。t1_b2 池化 `tm.get(...) or 0` 把在场 `None` 折 0、`True` 记 1、`"100"` 崩、负数拉低总量、nan/inf 传播、非对象崩；b8 README 的 `int(... or 0)` 收 str/bool、截断 float、`"10.7"`/nan/inf 崩，主批表印字面量 `None`、§9 求和 `TypeError`；rag_ab 把 `None`/str 送进 `_mean` 崩、bool/负数当数字、nan 让 `p<0.05` 为假并报"无显著差异"；RAG 分组 `_safe_float` 把 `"100"` 收成 100.0、`True` 收成 1.0、`"abc"` 折 0、负数/nan 入均值；成本表 `.get(..., 0)` 把在场 `None` 印成 `None`。修法：新增**聚合 metric 口径**共享读取器 `token_metric_reading` + `sum_token_metric_values`（缺席历史 0、在场 `None` 是上游已拒绝、计数走 `count_reason`、派生均值 只收有限非负 int/float），五处接线；读不动不给部分和，表格/README/解读渲染「不可读」。真工件读数逐位不变；**67 例新锁 + 33/33 变异锚点转红**；收口 10842 passed / 5 skipped / 0 failed；行 97.28% / 分支 93.98%。此前 AO 轮：**三个报告级 token 汇总读端也各持宽松折叠——档位、翻转对比、收敛曲线不得各算一遍**。`model_gradient` 的 `int(... or 0)`、`compare_failures` 的 `(row.get("token_usage") or {}).get(...)` + `sum`、`convergence_analysis` 的 `_safe_float(... or 0)` 分别把 bool/float/str/负数/nan 折成数字或崩掉整份报告/曲线；现新增总量口径共享读取器 `row_total_token_reading` + `aggregate_row_token_totals`（成本三元组读取器保持 AN 语义；值域仍由 `count_reason` 唯一判定）——total-only 旧 schema 可读、读不动不给部分和、缺席历史 0、拆分矛盾只披露；不可读收敛曲线 `available=False` 不伪造曲线。真批次 244 文件 / 322 臂 / 10659 行零实例、9 臂新旧总量差 0。详见 TOKEN_USAGE_REPORT_AGGREGATE_AO_2026-10-21（分册已删除）。此前 AM 轮：**成本表聚合的行级 token 读取也有值域——呈现层不得替聚合层兜底**。`statistical_analysis.cost_analysis` 改前用 `tu.get(...) or 0`：在场坏值（bool/float/str/负数/nan/inf）折成可计价数字，正 token 行缺 input/output 时按 0 计价编出 $0，`by_model` 键/值无值域判定、求和≠总量仍照单计价，S11 把非计数当记账证据。现改走共享 `row_token_counts`：读不动（非对象/在场坏值/部分三元组）⇒ 该臂 token 总量、归因与金额一律 `None`（`n_token_unreadable_rows` + `token_reading_reasons`）；拆分/归因矛盾 ⇒ token 总量可读、只废金额（`n_token_money_blocked_rows` + `token_money_reasons`）；归因谓词迁入 `src/budget/token_usage.by_model_reason`，报告侧同源委托；S11 证据改走 `count_reason`。真批次 783 行全部 int 自洽 ⇒ 三臂读数与返回域逐位不变；**64 例新锁 + 10/10 变异锚点转红**（中性对照 0 红）；全量 10685 passed / 5 skipped / 0 failed，覆盖率 18585/19109 行 = 97.2579%、6727/7164 弧 = 93.9001%，数字见 [BASELINE.yaml](BASELINE.yaml)。此前 **AL 轮**：**报告侧逐行 token 算术也有值域——一行读不动不是零**。`cost_effectiveness_block` 改前自持第二套行级算术：`usage.get("input_tokens") or 0` 把缺席/null/字符串/bool/负数/nan/inf 折成可计价数字；`token_usage` 缺席或非对象的行在检出计数之前 `continue`，`n_detections` 随 token 可读性缩水；正 token 行缺 `by_model` 归因、`in+out ≠ total`、`Σby_model ≠ total` 时静默逃逸或按矛盾数字计价；缓存命中解释的零消耗还被计入 AK 下界。现报告改读生产模块共享读取器 `src/budget/token_usage.row_token_counts`（ext 以别名保持既有 AI 锁零改动）：三元组读不动 ⇒ `total_tokens` / 总 $ / 两个比值一律 `None`，并披露 `n_token_unreadable_rows` + `token_reading_reasons`；拆分或归因不一致 ⇒ 只废金额（token 总量与 tokens/detection 仍可读，`n_token_money_blocked_rows` + `token_money_reasons`）；检出数只由 `detection_rate` 决定；缓存零行不进 AK 下界计数。真批次 783 行全为干净行（坏拆分 / 坏归因 0 行），三臂总金额 6.755979 / 0.876692 / 1.185783 逐位不变，受保护工件不重写；57 例锁 + 6/6 变异锚点；全量 10621 passed / 5 skipped / 0 failed，覆盖率 18575/19099 行 = 97.2564%、6719/7156 弧 = 93.8932%，读数见 [BASELINE.yaml](BASELINE.yaml)；此前 AK 轮：**少数无记账行不是免费，也不是精确值——成本读数是已记录花费的下界**。主批 plain_llm_df 有 35/261 行 token 三元组全 0、`llm_calls=0`，却生成了 `generated_test`（其中 3 行 `detection_rate=1.0`）；S11 因 13.4% < 50% 判可计算，成本表把 `$/task=0.004543…` 当精确值输出，报告 §4.1 仍显示「226 行计价 / 0 行不可计价」。现在 `token_accounting_sanity` 增 `n_zero_output_rows` 子集（仅 >0 时写入），`cost_analysis` 在成本可算且 `0 < 无记账行` 时写 `cost_caliber="recorded_lower_bound"` + `token_zero_output_rows`；成本表 / $/solved / 报告 §4 / §4.1 / ext note 一律声明「已记录下界、不是免费」（分母仍是全部任务、分子只含已记录花费；行级数学口径不变，AE2 锁定）；≥50% 断裂仍 `NOT_COMPUTABLE`；全记账臂与旧批次返回域、报告文本逐字不变；21 例锁 + 4/4 变异锚点；全量 10564 passed / 5 skipped / 0 failed，读数见 [BASELINE.yaml](BASELINE.yaml)；此前 AJ 轮：缓存命中是第三种记账状态——不是记账断裂，也不是免费。生产者 `record_cache_hit_usage` 早已写 `cache_hits` / `cache_avoided_tokens`，但成本读端从未消费：QuixBugs df 臂 50/50 行命中被 S11 判 `NOT_COMPUTABLE`、ULT df 臂纯缓存被读成无因「（缺: ）」、examples df 臂同被拒。现共享读取器收口到 `src/budget/token_usage`（`cache_caliber` / `cache_totals`；`count_reason` 自 ext 迁入为唯一值域谓词），S11 / `cost_analysis` / 两个报告层 / ext `_cost_per_task` 同源：合法且正向的缓存证据算「有记账」；命中行真实消耗记 0 是对的，但 0 不等于免费；坏值 / 半套 schema 只报 `None` + 机制名（`token_field_absent` / `token_not_count` / `token_not_finite` / `token_negative`），不留部分和；纯缓存臂成因 `cache_hit_no_api_spend`；避免 token 不折算金额。真批次 QuixBugs 64 命中 / 123644 avoided、ULT 39 / 89249、examples 2 / 3387 全部转为可计算并披露；主批旧 schema 返回域与受保护工件逐字节不变；68 例锁 + 19/19 变异锚点；全量 10543 passed / 5 skipped / 0 failed，读数见 [BASELINE.yaml](BASELINE.yaml)；此前 AI 轮：token 计数也有值域——不完整的 token 和不是 token 读数。每行 token 记账必须是三个非负整数（total_tokens / input_tokens / output_tokens）；`token_usage` 非对象、字段非数字/bool/非有限/负数一律让 `tokens/task` 取 `None` 并点名机制（token_usage_absent / token_usage_not_object / token_field_absent / token_not_count / token_not_finite / token_negative），bootstrap CI 同源读取（不再把 inf/nan 带进区间）；行级 `in+out ≠ total_tokens` 与 `by_model` 读不动只废金额（token 总数仍可读，token_split_mismatch / by_model_not_object / by_model_key_not_string）；63 例锁 + 18/18 变异锚点；真批次读数逐位不变、受保护归档不重写；全量 10475 passed / 5 skipped / 0 failed，读数见 [BASELINE.yaml](BASELINE.yaml)；此前 AH 轮：$/task 只在价目覆盖全部 by_model token 且 token 归因闭合时才是金额——全未登记、混合部分和、无 by_model、合计不符、无任务分母一律记「—（无金额）」并点名机制（model_unregistered / no_model_attribution / token_attribution_mismatch）；真批次三臂读数逐位不变（by_model 合计 = total_tokens，delta 0），受保护归档不重写；15 例锁 + 6/6 变异锚点；全量 10412 passed / 5 skipped / 0 failed，读数见 [BASELINE.yaml](BASELINE.yaml)；此前 AG 轮：未计价归因收口到单一机制索引——`cost_analysis` 的 `missing_models` 不再收价格域坏值/形状码（真批次 522 行 0 改变）；共享谓词 `model_entry_reason` 统一 `run_b8` 与报告侧「没登记 vs 读不出」；呈现层按机制给修法（条目形状 / 价格域 / 币种 / 行级），纯未登记与无 token 观测文本逐行不变；46 例锁 + 15/15 变异锚点；全量零失败，读数见 [BASELINE.yaml](BASELINE.yaml)；此前 AF 轮：JSON 落盘收口到 RFC 8259——新增严格序列化原语（路径点名 + fail-closed + 不静默转 null），四条中心写盘路径 + 39 份源码的 41 个直写点补 `allow_nan=False`，新增全仓门禁（工件 7273 份违规 0 + 源码写入点违规 0）并接 `make gates` / CI；同时把 AE §5.6「68 份裸 NaN」更正为文本 grep 假阳性；28 例锁 + 9/9 变异锚点；此前 AE 轮：价目条目准入接共享谓词（`run_b8` 聚合器不再自持数字门——bool/nan/inf/负价/CNY/字符串价/未登记模型一律拒绝并点名机制 + 内置价兜底披露）+ 测试侧价目 schema 域收口 + 入库 e2 报告陈旧差值登记更新（86/88 → 94/100，成因 = AD-1 渲染，受保护工件不重写）——零 LLM、全量测试零失败；此前 AD 轮：统计量渲染量级保持（p=5.89e-26 不再印成 0.0000）+ 正态尾部补集模式消除 + 数值精度丢失模式全仓普查；此前 AC 轮：McNemar p 的 `1−cdf` 浮点下溢修复；此前 Z→AB 批：第四轮第三方全量静态审查 20 项修复收口 + AA 轮覆盖审计与 E7 裁决执行面 + AB-1~17 轮「缺席/零/价目表准入」判据链；详见“最新优化”行与 [CHANGELOG](CHANGELOG.md)）

# AITester：检出优先的测试生成与修复评估（归因）系统

> **导航 / Navigation**：[文档索引（按角色阅读路径）](docs/INDEX.md) | [快速开始](QUICKSTART.md) | [贡献指南](CONTRIBUTING.md) | [复现指南（中文）](REPLICATION.md) | [基线数字单一来源](BASELINE.yaml)

> AITester 是一个以**检出优先协议**为主成功口径的 Python 自动化测试生成与
> 修复**归因评估系统**。核心创新：**检出优先思维链（Detection-first
> CoT，"先红后绿"）** + **分层错误修复机制（Hierarchical Repair）**
> + **Oracle（测试预言）闭环：规约驱动断言增强与缺陷检出导向**。
> **多智能体编排**在本系统中定位为**可消融容器**（非主断言）——E2 双门后
> `aitester vs plain_llm_df` δ=−0.3673 结构性劣后（ADR-0016），故标题与开篇
> 不再以"多智能体"为主表述（叙事对齐 ADR-0016，R26）。
> **为什么不用"手工设计"的多智能体（2026-10-10 修订：三方并列，撤回原"共识"表述）**：
> 项目自身 n=261 生死实验（−28pp，vs 检出优先提示协议 plain_llm_df）之外，
> 2026 年外部证据**方向不一，须并列呈现，不得择一表述为"共识"**：
> **(a) 不利证据**——Carleton 大学荣誉项目复现（Radaideh & Corriveau，*Comparing
> Automated Unit Test Generation Approaches for a Java Library Management System*，
> **非同行评审**，
> report-hub.scs.carleton.ca/projectPage/2872）在 **mutation score** 上报告 one-shot
> Gemini 2.5 Flash **88.35%** vs CANDOR **35.92%**、one-shot GPT-4o **69.90%**
> vs CANDOR **45.63%**；作者自述该结果为**配置效应而非迭代有害**；
> *(更正说明：此前本段把该结果误挂在"CANDOR, ICST 2026"名下，并误标为"IEEE 第三方复现，
> IEEE Xplore 11655121"（该文档号无法验证）；实为 Carleton 大学荣誉项目仓库自报（非同行评审），
> 且 CANDOR 原文并非 ICST 2026。)*
> **(b) 有利证据**——CANDOR 原文（Xu, Wang, Briand, Liu，**TOSEM 2026**，
> DOI 10.1145/3803418）报告多智能体在 line/branch/mutation 上达
> **0.991/0.970/0.980**（HumanEvalJava）；另有 TestAgent（**FSE Companion 2026**，
> DOI 10.1145/3803437.3806428）line **92.34%** / mutation **83.69%**。
> **(c) 迄今最强的负面证据**——ICST 2026 复现研究（Konstantinou, Degiovanni &
> Papadakis，arXiv:2601.09695）在 **6 个完整 Java 仓库 / 393 类 / 3,657 方法**上，
> 用更新 LLM 注入全部工具后证明 **Plain-LLM 49.95/35.33/33.82 全面优于
> HITS/SymPrompt/CoverUp/TestSpark**，且请求数不高于 CoverUp（具体请求数存在
> 11,718/12,264 与 11,815/12,741 两口径，正文定案前暂不引用）。
> 另注：BOAD（**ICLR 2026**，arXiv:2512.23631，IBM Research）为真，但研究对象是
> **仓库级 SWE 任务解决**（定位/编辑/验证子智能体），**不适用于测试生成论证**。
> **因此可辩护的窄主张是**：*手工的、工具特定的编排相对强 LLM 单提示 + 统一修复环，
> 优势有限或无优势*——而非"多智能体范式被击败"。本系统保留编排层作为可消融研究
> 容器，转正判据与 ADR-0016 一致（预算对照下复现正向 detection 增量），
> 后续探索方向为"自动搜索编排 vs 手工编排"对照。
> 诚实披露（AL5，2026-10-08 R2 勘误：ADR-0021 围栏残留 + ADR-0029 跨文件
> 未物化两起测量伪影）：三种子主批次（n=261，gold 独立裁决）实测检出优先
> 提示协议带来决定性检出增益；**repair 经测量口径修正后存量重放 = 39.31%**
> （145 可重放行 correct=57；E1/E2 logic 档 54.72%）——修复能力存在但未达
> 前沿，为当前优化主线（v1 口径 35.86% / 48.11% 系伪影下界；口径矩阵见
> `docs/design/repair_caliber_matrix.md`，修正重估见 `make corrected-metrics`
> / ADR-0027/0029，上限归因见 `repair_ceiling_report.md` / ADR-0016）。

## 测试状态

> **当前基线以 [BASELINE.yaml](BASELINE.yaml) 为准**（机器可读单一事实来源）。
> 全量测试通过、静态检查（ruff / mypy）与行/分支覆盖率等当前数字均**不在此硬编码**，
> 统一以 BASELINE.yaml 对应节（`tests` / `coverage` / `static_checks`）为唯一事实来源，
> 批次落地后由维护流程同步刷新（见 `CONTRIBUTING.md` "文档组织约定"）；
> 下方表格仅描述"状态口径"，具体数值一律指向 BASELINE.yaml，避免多文档各自硬编码造成漂移。

| 指标 | 状态 |
|------|------|
| **总测试数** | ✅ 全量 collected（全量依赖）/ 精简环境（缺 chromadb/matplotlib 时 RAG/可视化用例自动跳过）——当前数值见 [BASELINE.yaml](BASELINE.yaml) `tests` 节（`total_passed` / `slim_environment`） |
| **单元测试** | ✅ 全量通过、零失败（实测耗时与用例数见 [BASELINE.yaml](BASELINE.yaml) `tests` 节 `suite_seconds` / `total_passed` / `total_failed`）；精简环境 `skipif`/`importorskip` 优雅降级，非误报 ERROR |
| **代码覆盖率** | 总行覆盖与分支覆盖见 [BASELINE.yaml](BASELINE.yaml) `coverage` 节（`line_total_pct` / `branch_total_pct`）；核心模块逐文件覆盖率以 CI 最新 `term-missing` 输出为准 |
| **基准指标（诚实口径）** | ⚠️ **术语范围（EMSE 批次 2026-10-15，防审稿误读）**：本项目所有"gold 独立裁决"一律指**判据材料独立**（留出 gold 测试 / gold 补丁），**不含任何人工裁决**——全流程为零 LLM 的**自动化 oracle 判定**；人工复核（E7）为预注册项但**尚未执行**（见 `docs/preregistration.md` E7 节），任何位置不得据此声称人工参与或评分者一致性（无 Kappa）。⚠️ 主批次数字以 [BASELINE.yaml](BASELINE.yaml) `benchmark` 节为唯一事实来源：旧口径 `success`（"生成测试在最终代码上通过"）**不得单独引用**——必须与 M1 三指标（`detection_rate` / `repair_rate` / `false_fix_rate`）并列呈现。当前口径 = R-P0-2 三种子合并（261 任务/臂）：detection plain_llm_df 44.8% > aitester 15.8% > plain_llm 1.5%，**aitester vs df −28pp（编排净负贡献，21 行缺失双界下稳健）**；**repair 修正口径 39.31%**（ADR-0021/0029：历史"全线 0.0%"系 patch 字段围栏残留 + 跨文件任务未物化两起测量伪影，修正重放 57/145 可重放行；E1/E2 logic 档 54.72%；早期 10-01 批 0/15 系真零；漏斗修正：patch 产出 94%/plausible 47%/correct 39.31%；v1 口径 35.86%/48.11% 系伪影下界，口径矩阵见 `docs/design/repair_caliber_matrix.md`，上限归因见 `repair_ceiling_report.md` + ADR-0021/0027/0029）；$/task 0.0259 vs 0.0045（价目表官方登记口径）；定位维度随结果行并列输出——`fl_at_k`（谱系 Top-k 行级命中）与 `localization_hit_function`（LLM 推理定位函数级命中，2026-10-07 修复引擎批次 I 起，与 gold 变更函数集合比对，未定位时键集合同构占位）。历史批（2026-10-01 n=50）false_fix=90.0%（45/50，边际口径，工件复算；历史引用 89.8%）为"假成功通道"证据（ADR-0027 重估：该批修正 repair=0/15 系真零，证据维持成立）；**false_fix 口径矩阵**（权威落点 = `docs/design/repair_caliber_matrix.md` §"false_fix 口径（权威落点）" + `experiments/emse_optimization.py::false_fix_caliber` + 锁定测试 `tests/test_emse_optimization.py`，零 LLM 可复算；历史引用路径 `docs/design/false_fix_caliber_matrix.md` **从未入库**、不可引用）：R-P0-2 主批次边际口径 59.58%（143/240）/ 条件口径 100%（143/143），10 批次 ADR-0027 修正口径 87.16%（380/436，passed 可测行重放）——对外引用必须携带口径标签；SWE-bench Lite（sqlfluff-20）20 次尝试中 7 次完成且全部因 API 429 限流失败、3 次失败、10 次超时——**基础设施故障，无有效能力结论**（不构成负结果证据，列入待复跑清单），与统计检验同样如实披露、不筛选（限流信号计数口径 = 全结构化文本源 run_notes/notes/issues **去重后**统计 `429` 字面量 = 2，分源各 1；issues 中 404 端点错配条目独立记账，见 `（工件已清除）`）|
| **已知失败** | ✅ 0（**正常环境口径**：本地干净树 20 步门禁链 rc=0、全量零失败（当前 passed / skipped / collected 读数见 [BASELINE.yaml](BASELINE.yaml) `tests` 节）。**CI 状态如实披露（CL 轮 2026-10-25）**：2026-10-25 当天 push run（v0.8.0 序列至 e5817c0f）test 3.12/3.13/3.14 曾三档全红——归因为 CI「生成静态快照」步骤排在 pytest 之前，写入的 `docs/history/static_report_<日期>.md` 使 ruff 格式化计数 +1，登记门禁复算漂移（975 vs 976）冲红 pytest 内两条真树锁；已修复（快照步骤移至作业最末端 + 诊断 grep 容忍 xdist 前缀 + 步骤顺序回归锁），**远端确认以 CL 轮修复推送后的新 run 为准**；**CM 轮（2026-10-25）补**：CL 之后连续三次 run（`798d8c72` / `e5817c0f` / `251af095`）在 3.14 档仍红，失败步骤 = 「Verify experiment artifact checksums」——它校验 `experiments/results/main_batch`，而该目录已于 2026-10-24 撤回（fresh clone 中不存在）；本地因工件在盘而看不出。已改为校验当前世代三个在册且有清单的目录（fresh clone 实测 **127 / 3 / 34 项一致**），最终以本推送后的新 run 为准。修复前三档红的注解名单与 A/B 实证见 CHANGELOG CL 轮节；RAG / 数据集下载测试已修复；缺可选依赖时相关用例 `skipif` 跳过而非报错。沙箱宿主口径：broker/ps/嵌套 sandbox 受限环境下曾出现 14-15 例环境能力缺失失败，2026-10-18 已全部归因并按 `skipif`/防御式写法加固——加固后沙箱内复跑零失败（计数见 [BASELINE.yaml](BASELINE.yaml) `tests` 节），归因与口径详见 `tests.total_failed` 注释） |
| **已知限制（1.0.0）** | ⚠️ ① **无人工裁决**：gold 判定全为自动化 oracle，E7 人工复核协议已备但未执行，不得声称人工评分或 Kappa；② **单一模型族**（deepseek-flash 单端点），跨模型外推不成立；③ **多 seed 池未重建**：2026-10-24 撤回的 261 行/臂池未复刻，该口径数字在论文中一律标 historical（冻结读数见 `docs/study/WITHDRAWN_ARTIFACTS_2026-10-24.md` 表 W-1）；④ **合成模板库漂移**（30→50 pattern、6 个模板 gold 修复）⇒ 存量 mutation 值只能以归档工件复算；⑤ **scale87 `replace` 臂 ≠ 完整 SpecExpr 规格优先**，其零对比只界定文档替换变体；⑥ **SWE-bench Lite 无能力结论**（20 次尝试全为 API 429/超时等基础设施故障）；⑦ 研究面待授权项（LLM 配额实验 / D3 全量 Mut@k / 投稿与 DOI）见 `docs/adr/0036-v1-release-criteria.md` §3，不阻塞 1.0.0。 |
| **安全审查** | ✅ 无硬编码密钥（`.env*` / `.env.local.bak` / `.private` 已 gitignore / 删除）；日志脱敏三层防线（Handler 层 SensitiveFilter/Formatter + 入口接线 + trace JSONL 旁路脱敏）；APIManager 日志点就地 `_redact()`（不依赖入口接线，嵌入式安全）；`get_status()` 出口 base_url 脱敏；**三条执行链路（本地/venv/Docker）统一剔除 LLM 凭证（`credential_scrub.scrub_os_environ` 动态模式，覆盖 `LLM_N_API_KEY` 全部编号，封堵生成代码继承宿主凭证的泄露面）**；凭证剔除 P0 补强（2026-09-26：`OPENAI_(API_KEY\|BASE_URL)_\d+` 编号变体 + provider 中间变量（`DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL`，与 config_generator 的 PROVIDER_TEMPLATES 键联动消名单漂移））；脱敏盲区修复（`APIManager.call` 全节点失败异常出口统一 `_redact`、`config_manager.add_llm_config` 拒含换行/`#` 的变量值注入、`retry_with_backoff` 日志惰性脱敏、`SensitiveFormatter` 降级路径先走纯正则兜底）；LLM 文件缓存记录为已知可接受风险（本地可信域，不进 git；缓存写已改原子替换） |
| **最新优化** | ✅ **2026-10-25 CL 轮（零 LLM，$0；远端 CI 三档全红归因与修复，读数见 [BASELINE.yaml](BASELINE.yaml)）**——**CI 树状态差归因**：快照生成步骤原排在 pytest 之前，写入的 `static_report_<日期>.md` 使 ruff 格式化计数 +1 ⇒ 登记门禁复算 976 ≠ BASELINE 975 ⇒ pytest 内两条真树锁（`test_registration_readers_cf.py` TestRealTree）在 3.12/3.13/3.14 三档全红，本地 fresh clone 全绿。归因 = check-run 注解 API（失败清单逐字列名）+ fresh clone A/B（快照在盘 ⇒ 红 2 项「975 vs 976」；移除 ⇒ 绿）。修复 = 快照两步移至 test 作业最末端（pytest 与 `if: failure()` 诊断重跑之后）+ 诊断 grep 容忍 xdist `[gwN]` 前缀（3.14 原漏捕整份清单）+ **步骤顺序回归锁**（变异验证：换回旧顺序 ⇒ 锁红）。此前 **2026-10-25 CK 轮（零 LLM，$0；复现包与撤回语料对账 + 1.0.0 判据 ADR-0036，读数见 [BASELINE.yaml](BASELINE.yaml)）**——**复现包文档未随数据换代复盘**：REPLICATION.md 15 处失效引用（主批次 / charts / analysis 随 2026-10-24 清除撤回）、§6 校验和清单登记 69 文件/7,048 条 vs 实测 **4 文件/181 条**、§7 CITATION.cff 版本与行号过期；CITATION.cff 第 5 行「归档元数据已备」实测不在盘、git 历史无此路径（**在库假声明**）改如实待补充。ADR-0036 把「前沿领先的 1.0.0」操作化：A 测量面 7 项 / B 研究面 4 项（需用户授权，不阻塞）/ C 发布机械 5 项。此前 **2026-10-25 CJ 轮（零 LLM，$0；引用豁免登记面补读者 + 引用门仓库外崩栈修复 + 复算链 [SKIP] 显式化，读数见 [BASELINE.yaml](BASELINE.yaml)）**——**12 条引用豁免键登记了两遍**（24 行；`load_allowlist` 返回 set、重复键静默合并 ⇒ 对所有读者不可见）且文件内「现状：零豁免」声明未随补登记更新；新锁 `tests/test_citations_gate.py` **13 例**锁死登记面（原始行无重复 / 全部承重无陈旧 / 充分性 / 声明条数==实况 + 合成面 8 例），变异 3+1（重复键 2 红 / 陈旧行号 3 红 / 回退 `_rel` 3 红 / 中性对照 0 红）；`check_citations.py` 对仓库外 `--files` 绝对路径 `relative_to(PROJECT_ROOT)` 抛未捕获 `ValueError`（`collect_files` 容忍、扫描段不容忍）⇒ `_rel()` 兜底；`reproduce_zero_llm.py` 源工件撤回支路改显式 `[SKIP]`（退出码只由 FAILED + SHA256SUMS 失败数决定）。存量勘误两处：`798d8c72` 实测 12,491/254 未刷 BASELINE（一致性 slack 吸收拆分漂移）、AO3 行锁误绿两轮推进至 CJ。全量确认跑零失败（collected 12758；读数见 [BASELINE.yaml](BASELINE.yaml) `tests` 节）。此前 **2026-10-23 BZ 轮（零 LLM，$0；CI 三族红归因修复，读数见 [BASELINE.yaml](BASELINE.yaml)）**——**CI 历史三族红归因修复：测试契约工件入库 + 三类前提缺失显式 skip + 45 漏洞升级清零**。run 39905189493（head 5eb51607）test 3.12/3.13 失败清单逐字取自 check-run 注解 API，fresh clone 模拟复现 **31 例**（本地全量绿只因工件在盘被忽略）。处置：①契约工件入库 **408 个 / 5.9 MB**（AST 普查 + 失败清单双闭环，漏采的两种路径写法二轮补入）；②语料面普查（8 例）/ 历史切点（4 例）/ 双盲文件（2 例）改 `tests/_corpus_guard.py` 单一事实源的显式具名 skip（理由带实测读数：benchmark 107/246、trace 6759/8539、缺 b533cff 等）；③非 0.5 精确二项断言 abs=0.0 → rel=1e-12（macOS Accelerate 与 Linux glibc 末位差 1-2 ULP）；④pillow 12.3.0→13.0.0、aiohttp 3.14.3→3.14.4、certifi 2026.7.22→2026.10.19、otel 家族 1.44.0→1.45.1（45 漏洞全有上游修复，lock 132→133，chromadb 5 豁免不动）；⑤test 作业超时 30→60。验证：fresh clone 三轮闭环 **31 红 → 9 红 → 0 红**（46 个 skip 理由逐条核过、零静默）、pip-audit「No known vulnerabilities found, 5 ignored」、本地全量零失败且与升级前逐位相同（读数见 [BASELINE.yaml](BASELINE.yaml)）。此前 **2026-10-23 BY 轮（零 LLM，$0；全量测试零失败，读数见 [BASELINE.yaml](BASELINE.yaml)）**——**报告的「分析集流量」从未披露：`## 数据来源` 只列纳入文件，载入行数不是 n，整份剔除与行内折叠是两种剔除，扫描面之外还有结果文件，字段 None 不是 0**。归档实测（加载器 glob 口径）：扫描 **246 份 / 10,659 行** → 数据集白名单外 **77 份 / 886 行**（`examples` 50 / `swe_bench` 11 / `ult` 6 / `swe_bench_pro` 6 / `o3_cross_file` 2 / 缺失 2）、schema 不完备 **59 份 / 2,463 行**、读取/加载失败 **0 / 0**、未登记基线 **300 行** ⇒ 载入 **110 份 / 7,010 行**；全归档带 `results` 的 JSON 另有 **257 份 / 11,197 行**，其中 **13 份 / 538 行**不叫 `benchmark_*`、连扫描面都没进。同 `task_id` 只留最新批次一行 ⇒ 折叠 **6,449 行（91.997%）**，唯一 task 行 **561** 才是配对单元（把 7,010 当 n 会放大样本量 12.5 倍）；字段 None：`detection_rate` **45** / `repair_rate` **52**（不是 0）。三层对账 `10,659 − 886 − 2,463 − 300 = 7,010`、`7,010 = 561 + 6,449`、`9,473 − 7,010 = 2,463`（混批口径）全部闭合。处置纯读侧（单一事实源 `experiments/_analysis_flow.py` + `## 数据来源` 新子章节「分析集流量」+ 控制台摘要一行），判定值与方向一处不动、`src/` 零改动；**27 例新锁 + 变异 46 锚点 = 45 变异全红 / 对照 0 红**。此前 **2026-10-23 BX 轮（零 LLM，$0；全量测试零失败，读数见 [BASELINE.yaml](BASELINE.yaml)）**——**写而不读键池最后两键的读侧从未披露：`risk_summary` 全归档通道关闭与「全部低风险」同形、`mdo_crash_rate` 五层输入域与 `None`/`0` 同形**。归档 257 批次 / 11197 行：`risk_summary` 在场 8864 行全 `enabled=False`（`enabled=True` 0、`risk_level` 非空 0、键缺席 2333、`contract_status` 在场 0）；`mdo_crash_rate` 五层 = 未跑 2312 / 材料缺 122 / 不可测 986 / 暂定池 530 / 实测 94，规范值 94 行（79 零 / 15 非零，池化 15/3200 = 0.46875%），暂定池原始值 530 行（12/7190 = 0.1669%）不与实测合并；`mdo_pool_floor_ok=False` 1516 行是两义键（暂定池 530 + 默认值 986）。处置纯读侧（单一事实源 + 报告两表 + 摘要一行），判定值与方向一处不动、`src/` 零改动；**102 例新锁 + 变异 44 锚点 = 43 变异全红 / 对照 0 红**；键池闭合 41,545 + 22,035 + 12,908 = 76,488，零读者池为空。此前 **2026-10-23 BW 轮（零 LLM，$0；全量测试零失败，读数见 [BASELINE.yaml](BASELINE.yaml)）**——**补丁接收链的覆盖率与分母从未披露：精确率三口径、弃权四桶、验证输入可达域在任何报告面都不出现**。归档 257 批次 / 11197 行：接受集 1331（16.61%）、存储 45.60% vs 并集 50.75% vs gold 57.92%、选择性风险 54.40%（gold 42.08%）、抑制精确率 93.98%（gold）/ 93.11%（全部）、验证输入仅 `patch_evidence_level` 1007 行可达。处置纯读侧（单一事实源 + 报告四表 + 摘要两行），判定值与方向一处不动；**94 例新锁 + 变异 68 锚点全红 / 对照 0 红**。此前 **2026-10-23 BV 轮（零 LLM，$0；全量测试零失败，读数见 [BASELINE.yaml](BASELINE.yaml)）**——**批次 VIII / XIV 两份判定核的「沉默」从未披露：归档 5935 行里 20 行 test-hacking 判 True（12 硬编码输入分支 + 8 新增吞异常）不出现在任何报告面，FL 约束门六种早退共用一个 `not_evaluable`**。`test_hacking_suspected` / `_signals`（批次 VIII，ADR-0022）与 `fl_constraint_verdict` / `_hit_rank` / `_changed_functions`（批次 XIV，ADR-0028）自写入起报告面读端 **0**；判定核在「无原码 / 无补丁 / 解析失败」时返回 `suspected=False, signals=[]`，与「三信号都跑过且零命中」**同形** ⇒ 5915 行分不清判干净还是没看；FL 侧 `not_evaluable` **4442/5935**，已求值 1493 行 hit **1487** / miss **6**（hit 比 99.60%），而 3+ 变更函数档只占 1.9% ⇒ **ADR-0028 登记的整文件重写成因不足以解释**，该门在本语料几乎不区分。处置：判定核增返 `status`（两侧解析分开归属）、结果行落 `test_hacking_status` / `fl_constraint_reason`、单一事实源 `experiments/_verdict_silence.py`、`detector_silence_stats` 读侧（成因按「记录 / 推断 / 不适用 / 无判定键」分列，推断明写为下界）、报告新章节（hack 9 列 + FL 11 列两张表 + 判别力注 + 两条口径脚注）、批次摘要一行；**判定值与方向一处不动**。**87 例新锁 + 变异 58 锚点全红、中性对照 N01 0 红**，首轮 3 项存活（常量改名 / 对称夹具 / 按构造恒真的标记）分别以字面量锁、不对称夹具、删字段收口。此前 BQ→BU 四轮均为读侧披露收口（四 status 通道 / 验收 oracle 来源 / Trap 输入可达域）。详见 [CHANGELOG.md](CHANGELOG.md)；全部当前数字以 [BASELINE.yaml](BASELINE.yaml) 为单一事实来源 |
| **核心模块覆盖** | ✅ 逐模块行覆盖 / 分支覆盖 / 核心路由门槛以 [BASELINE.yaml](BASELINE.yaml) `coverage.line_core_modules`、`coverage.branch_core_routing` 与 `coverage.line_total_pct` / `branch_total_pct` 为单一事实来源（本行不再硬编码数字——此前硬编码值已随 K 轮收口过期，属"文档低于工件"的存量漂移） |
| **代码规范** | ✅ Ruff 检查全部通过（`ruff check` + `ruff format --check`，CI 固定 0.16.3）+ mypy 全仓 0 错误（源文件数与版本锁定见 [BASELINE.yaml](BASELINE.yaml) `static_checks` 节 `mypy_source_files`）；历轮 lint 清零叙事归档 [CHANGELOG.md](CHANGELOG.md) |
| **历史里程碑（2026-10-07）** | ✅ 修复引擎批次 XIV（历史快照，非当前基线；当前状态见本表"最新优化"行与 [BASELINE.yaml](BASELINE.yaml)）（外部报告净新增收割 ADR-0028——FL Top-k 约束观测门〔`patch_changed_functions` 补丁变更函数集合 × 定位 Top-3 候选求交，hit_rank 分层；结果行 `fl_constraint_verdict`/`fl_constraint_hit_rank`/`fl_constraint_changed_functions` 三键；ADR-0024「生成侧主导」行级可验证〕+ Self-Repair Trap 观测器〔`oracle_quality_history` 逐次质量快照 + `detect_self_repair_trap` 三信号判定核；结果行三键〕+ Frame Lifetime Trace 设计输入〔docs/design/frame_lifetime_trace.md，激活门槛=Debugger 拆分批立项〕+ BASELINE 测试链勘误〔批次 VII–XIII 记录数字预写失真收口〕）；此前同日批次 VII–XIII（repair=0 测量伪影定案〔修正口径 35.9%/48.1%〕+ test-hacking 守卫 + 统计报告三节 + 反事实 FL 上界 + ORACLE_CONTEXT_TIER 消融档 + 交互归因 + 修正口径重估收口，详见 CHANGELOG）；此前同日批次 VI（run_main_batch `--staging-dir` 跑批运营收口——跑前快照输出目录、跑后新工件自动外移保持工作树干净，**多种子顺序跑批第二批不再被干净树门禁拒绝**〔E2 双种子"暂移-恢复"两次手工实操固化；--skip-stats 早退同样外移；路径穿越防御拒 .. 与输出目录内〕+ `make cpr-idr` 报告入口〔IDR/CPR + 弃权视角〕）；此前同日批次 V（ADR-0020：补丁弃权门观测层——五信号判定核 + 结果行 `patch_abstained`/`patch_abstain_signals`；弃权视角存量回放：passed 443 中 392〔88.5%〕将命中、精确率 1.0；阻断档 Proposed 待 A/B）；此前同日批次 IV（ADR-0019：确定性优先修复路由）；此前同日批次 III（ADR-0018：编辑意图落盘 + AC2 计数补漏）；此前同日批次 II（定位 Top-3 + Hit@3/MRR + CPR/IDR〔IDR=27.78%〕）；此前同日批次 I（范式转向修复引擎路线，FaultLocalizer 落地）；此前同日 AS 批次（发行构建链路取证 + PEP 639）；更早批次详见 CHANGELOG；测试数量见 [BASELINE.yaml](BASELINE.yaml) `tests` 节 |

更多详情参见 [CHANGELOG.md](CHANGELOG.md)、[QUICKSTART.md](QUICKSTART.md)、[docs/api_reference.md](docs/api_reference.md)、[docs/usage_examples.md](docs/usage_examples.md)。

## 开发工具

### Lint 与格式化

项目使用 [Ruff](https://docs.astral.sh/ruff/) 进行代码检查和格式化（CI 固定 `0.16.3`，与 `requirements.lock` 一致，避免上游发版导致格式化门禁漂移）：

```bash
# 安装 ruff（固定与 CI 相同的版本）
pip install "ruff==0.16.3"

# 检查代码
ruff check .

# 自动修复可修复的问题
ruff check --fix .

# 格式化代码
ruff format .

# 检查格式化（不修改）
ruff format --check .
```

### Pre-commit Hooks

推荐使用 pre-commit hooks 在提交前自动执行检查：

```bash
# 安装 pre-commit
pip install pre-commit

# 安装 hooks
pre-commit install

# 手动运行所有 hooks
pre-commit run --all-files
```

### CI/CD

项目配置了 GitHub Actions 持续集成，支持：
- 多 Python 版本测试（3.12 / 3.13 / 3.14，与 [BASELINE.yaml](BASELINE.yaml) `python_ci_matrix` 一致；下限由锁定依赖决定：scipy 需 ≥3.12）
- Ruff lint 检查
- pytest 测试 + 覆盖率报告
- 依赖安全扫描（pip-audit；chromadb 1.5.9 命中 5 条已知漏洞（PYSEC-2026-311 重复两条 + PYSEC-2026-3813/3814/3815），因 PyPI 暂无修复版本而显式豁免，详见 ci.yml 注释与 CHANGELOG）
- requirements 与 requirements.lock 一致性校验（scripts/gates/check_lock_sync.py）
- 测试失败诊断注解：测试步骤挂掉时自动把 FAILED/ERROR 用例清单写成 GitHub 注解（check-runs annotations API 可读，无需 admin 下载日志）

### 测试命令

```bash
# 运行所有单元测试（全量用例数与精简环境收集数以 [BASELINE.yaml](BASELINE.yaml) `tests` 节为准）
.venv/bin/python -m pytest tests/ -v

# 运行测试并显示覆盖率
.venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing

# 仅运行工作流集成测试（端到端编排）
.venv/bin/python -m pytest tests/test_workflow.py tests/test_workflow_extended.py -v

# 仅运行数据集加载测试
.venv/bin/python -m pytest tests/test_dataset_loader.py tests/test_dataset_loader_extended.py -v
```

## 快速开始

> **⚠️ 安全执行警告（2026-09-30 独立审查 N8/R10）**：本系统会让 LLM 生成 Python 代码，
> 并**自动执行**这些代码（测试 + 补丁验证）。自 2026-09-30 起，`EXECUTOR_USE_VENV`
> **默认开启**——LLM 生成的代码在隔离 venv 沙箱内运行（venv 缓存于
> `~/.cache/aitester/venvs/`，相同依赖组合任务复用），不再直接落在宿主系统
> Python 环境。
>
> - 如需**显式关闭** venv 沙箱（仅调试 / 无 venv 权限的环境）：
>   `EXECUTOR_USE_VENV=false`。此时 LLM 生成的代码将在宿主环境直接执行——
>   请仅在本机可信、无敏感数据与网络凭证的机器上进行，并配合
>   `KERNEL_SANDBOX_ENABLE=true`（macOS Seatbelt / Linux bwrap，可用时）
>   进一步限制文件系统与网络出口。
> - `EXECUTOR_AUTO_INSTALL_DEPS` 默认**关闭**；开启后 venv 会 `pip install`
>   LLM 推断出的依赖包名——**存在包名幻觉（slopsquatting）攻击面**
>   （USENIX Security 2025 已量化确认：19.7% 代码样本含幻觉包名
>   [待核验]）。包名白名单 `PIP_PACKAGE_WHITELIST_ENABLE` 自 2026-10-09
>   审查修订 C-08 起**默认开启**（R59/S6 守卫：仅白名单内包名放行，
>   未知名默认拒绝，堵供应链向量）；显式设 `false` 退回历史放行口径
>   （仅可信环境调试用）。
> - 更高强度隔离：`EXECUTOR_USE_DOCKER=true`（容器级隔离，需预构建镜像）。

```bash
# 0. 创建虚拟环境（推荐 Python 3.12+；锁定依赖 scipy 要求 ≥3.12）
python3 -m venv .venv
source .venv/bin/activate

# 1. 安装依赖
pip install -r requirements.txt
# 仅 wheel / 非仓库开发安装：运行 Executor 与基准评测请安装执行 extra
# pip install "aitester[execution]"   # pytest + pytest-cov + pytest-timeout
# 默认 pip install aitester 不含执行工具；缺模块时 Executor 返回
# error_info.type=execution_dependency_missing 并提示本命令

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key 等信息

# 2.5 零 LLM 自检（环境/配置 + 全功能探针矩阵零 LLM 子集；不消耗 API 配额）
#     也支持 --json（stdout 纯 JSON）/ --groups budget,executor / --strict
python main.py doctor

# 3. 初始化数据库（可选，如需持久化实验数据）
python init_db.py

# 4. 运行单个文件测试
python main.py run examples/calculator.py --func divide

# 5. 批量基准测试（内置示例数据集，三种基线对比）
python experiments/run_benchmark.py --dataset examples --baselines aitester,plain_llm,single_agent

# 6. 仅运行完整系统 + 限制任务数
python experiments/run_benchmark.py --dataset examples --task-limit 2

# 7. 消融实验：仅启用 Planner
ENABLE_PLANNER=true ENABLE_DEBUGGER=false python experiments/run_benchmark.py --dataset examples

# 8. 运行合成数据集基准测试（无需外部下载，可自定义规模）
python experiments/run_benchmark.py --dataset synthetic --task-count 50 --baselines aitester,plain_llm,single_agent

# 9. 可视化实验结果（含统计显著性检验）
python experiments/visualize_results.py
python experiments/visualize_results.py --results-dir experiments/results/synthetic_full

# 10. 并发执行基准测试（加速多任务处理）
BENCHMARK_PARALLELISM=4 python experiments/run_benchmark.py --dataset synthetic --task-count 20

# 11. 使用 --parallel 参数指定并行度
python experiments/run_benchmark.py --dataset examples --parallel 4

# 12. 使用 --timeout 参数设置全局超时
python main.py run examples/calculator.py --func divide --timeout 120

# 13. 基准结果以 JSON 输出（stdout 直接输出结构化 JSON，无需额外参数）
python experiments/run_benchmark.py --dataset examples
```

## 性能优化说明

### RAG 检索器单例化

系统已实现 RAG 检索器的**懒加载单例模式**，在整个工作流执行期间只初始化一次 ChromaDB 客户端，避免重复加载嵌入模型（约 100MB）和打开向量索引的开销。

**性能收益**：每个任务节省 2-6 秒初始化时间。

**技术实现**：`src/graph/rag.py` 中的 `get_rag_retriever()` 函数（经 `workflow.py` re-export 保持旧导入路径）。

### LLM 文件缓存（省 token）

`base_agent` 的 LLM 调用已接入**持久化文件缓存**（按 `md5(prompt + system_prompt)` 命名的 JSON 文件）。相同输入第二次起直接命中缓存，不再消耗 token——在「免费额度用完即停」的模型供应商下可显著延长可用时长。

- **默认启用**；设环境变量 `AITESTER_LLM_CACHE=0` 可关闭；缓存目录可用 `AITESTER_LLM_CACHE_DIR` 覆盖。
- **缓存目录**（2026-10-05 审查批次起）：默认 `~/.cache/aitester/llm/`（`XDG_CACHE_HOME` 优先）——运行时缓存不再写入源码树 `src/cache/`；需要沿用历史缓存时显式设 `AITESTER_LLM_CACHE_DIR=<repo>/src/cache`。
- **仅缓存成功响应**：调用失败（如 403 额度用尽）不写缓存。
- 缓存是本地优化产物，不提交版本库（目录权限 0700 / 文件 0600，跨用户缓存投毒防护）。

```bash
export AITESTER_LLM_CACHE=0      # 临时关闭缓存（需要"换种思路重生成"时）
rm -rf ~/.cache/aitester/llm     # 清空缓存，让所有 prompt 重新调用 LLM
```

### LLM 客户端复用（连接池共享）

`base_agent` 中的 LLM 客户端现在按配置**复用**，避免每次调用都新建客户端（含底层 HTTP 连接池）：

- **OpenAI 兼容路径**（`ChatOpenAI`）：按 `(model_name, temperature, api_key, base_url)` 缓存，上限 16 个（FIFO 驱逐）。

**性能收益**：同一配置的多次 LLM 调用共享连接池，省去重复建连开销；多任务并发时连接池状态一致、行为更可预测。

**技术实现**：`src/agents/base_agent.py` 的 `_get_or_create_chat_client()`。

### 模型额度探测（scripts/tools/check_quota.py）

探测各已配置模型当前是「存活 / 免费额度用尽(403) / 限流 / key 失效 / 模型不存在」，每个模型仅发 1-token 请求，**不打印任何密钥**：

```bash
.venv/bin/python scripts/tools/check_quota.py                      # 探测 .env.local 已配置的全部 LLM
.venv/bin/python scripts/tools/check_quota.py --provider deepseek  # 扫某 provider 目录全模型
.venv/bin/python scripts/tools/check_quota.py --provider deepseek --models deepseek-flash
.venv/bin/python scripts/tools/check_quota.py --dry-run           # 只列出将探测的目标，不发请求
```

### LLM 调用超时配置

通过 `LLM_TIMEOUT` 配置项控制单次 LLM 调用的超时时间，防止 API 响应过慢导致任务卡死。

```bash
# .env 文件配置
LLM_TIMEOUT=60          # 单次 LLM 调用超时（秒），默认 60
LLM_RETRY_WAIT=30       # LLM 重试等待时间（秒），默认 30
EXECUTION_TIMEOUT=30    # pytest 执行超时（秒），默认 30
```

### LLM 结构化输出加固（JSON Output 与解析层修复，2026-10-14）

按 DeepSeek 官方文档配置的结构化输出加固（ADR-0031；日志归因显示
"执行失败/超时"多为执行器重试与测试侧保护，真实缺陷是结构化解析失败）：

- **`LLM_JSON_MODE`（默认 on）**：七处 JSON 契约调用点（Planner 测试计划 /
  Debugger 补丁·严格重试·批评者·击穿用例·缺陷分类 / FaultLocalizer 定位）绑定官方 JSON Output
  （`response_format={"type":"json_object"}`，保证响应为合法 JSON 字符串）；
  设 `off` 恢复历史逐字节口径（旧批次复现用）。配置入批次 provenance
  `env_snapshot`（可审计）。
- **数值表达式解析修复**：LLM 在 JSON 值位写 Python 数值表达式
  （`10**18` / `10**18+1` / `10_000`）时由解析层受限求值换算为等值 JSON
  数字（无 eval、指数/位数有界、字符串内防护）——修复"叶子回退静默返回
  错误片段"导致的 M10 误诊（LLM 实际输出了完整 JSON）。
- **`finish_reason` 守卫**：响应 `length`（截断）/`insufficient_system_resource`
  （推理资源中断）按可恢复失败重试，不把残缺内容交给下游。

### 并发执行（BENCHMARK_PARALLELISM）

支持多线程并行执行多个 benchmark 任务，显著缩短大批量测试的总耗时。

```bash
# 使用 4 个线程并行执行（环境变量方式）
BENCHMARK_PARALLELISM=4 python experiments/run_benchmark.py --dataset synthetic --task-count 50

# 使用 --parallel 参数（命令行方式）
python experiments/run_benchmark.py --dataset synthetic --task-count 50 --parallel 4

# 串行执行（默认）
python experiments/run_benchmark.py --dataset synthetic --task-count 50
```

**注意**：并发执行需要为每个线程配置独立的 API Key，可通过 `LLM_1_*`, `LLM_2_*` 等多组配置实现 API Key 轮询。

更多细节请参考 [性能调优指南](docs/performance_guide.md)。

### 超时控制（--timeout）

通过 `--timeout` 参数或 `EXECUTION_TIMEOUT` 环境变量控制单次测试执行的超时时间，防止任务卡死。

```bash
# 命令行指定超时（秒）
python main.py run examples/calculator.py --func divide --timeout 120

# 或环境变量方式
EXECUTION_TIMEOUT=120 python main.py run examples/calculator.py --func divide
```

超时后测试被强制终止，状态标记为 `timeout`，Debugger 可针对超时场景进行专项修复。

### JSON 输出（基准结果默认行为）

`run_benchmark.py` 结束时始终将汇总结果以结构化 JSON 打印到 stdout（`--output-dir` 下同时落盘 `benchmark_<数据集>_<时间戳>.json`；加 `--save-state` 时各环节状态另存 `raw/<task_id>/`），可直接管道给 `jq` 等工具做程序化处理。注意：该脚本没有 `--json` 开关——JSON 输出是默认且唯一的结果输出形式。

```bash
# 结构化 JSON 结果直接输出到 stdout
python experiments/run_benchmark.py --dataset examples

# 结合 --output-dir 在目录下保存结果 JSON
python experiments/run_benchmark.py --dataset examples --output-dir ./results
```

JSON 输出包含完整的结果统计、各基线详细数据和性能指标，可直接用于后续分析脚本。

更多细节请参考 [性能调优指南](docs/performance_guide.md)。

## 项目结构

```
AITester/
├── src/                              # 核心源代码
│   ├── agents/                       # 多智能体模块
│   │   ├── base_agent.py             # 智能体基类（LLM 调用 + 文件缓存 + JSON 解析；客户端工厂已拆至 llm_client.py）
│   │   ├── llm_client.py             # LLM 客户端工具函数（ChatOpenAI 工厂 + 模块级连接池缓存，0.1 拆分）
│   │   ├── planner.py                # 测试规划师（含逻辑驱动思维链）
│   │   ├── generator.py              # 测试代码生成器（支持 RAG 增强）
│   │   ├── executor.py               # 测试执行器（类主体 + 本地执行编排；导入修复/结果解析/沙箱与 Docker 模式/子进程基础设施已拆至 executor_* 子模块）
│   │   ├── executor_imports.py       # 导入路径自动修复（模块名提取 / sys.path 注入 / 相似名替换，0.1 拆分）
│   │   ├── executor_modes.py         # venv 沙箱 + Docker 隔离执行模式（0.1 拆分）
│   │   ├── executor_repo.py          # P0 仓库级执行器 RepoExecutor（SWE-bench 官方口径：clone+checkout+pip install -e 环境缓存 + venv 隔离 + gold test_patch 前后 FAIL_TO_PASS/PASS_TO_PASS 实测，默认关）
│   │   ├── executor_output.py        # 执行结果解析（覆盖率 / 失败用例 / 错误信息，0.1 拆分）
│   │   ├── executor_runtime.py       # 子进程运行、重试与临时资源清理（0.1 拆分）
│   │   ├── debugger.py               # 调试修复师（分层错误修复）
│   │   ├── fl_spectral.py            # Ochiai 谱系故障定位（零 LLM，Top-k 可疑行佐证；R8 起）
│   │   ├── fault_localizer.py        # RGFL 式 LLM 推理故障定位（修复引擎第一阶段，只定位不修复；FAULT_LOCALIZER_ENABLE 默认开）
│   │   └── error_classifier.py       # 错误类型分类器（规则匹配）
│   ├── api/                          # API 配置管理
│   │   ├── api_manager.py            # 多 LLM 配置 CRUD（.env.local / llm_configs.json）+ 熔断/路由
│   │   └── api_health.py             # API 健康状态与路由策略数据模型（APIHealth/APIManagerConfig/RotationStrategy）
│   ├── config/                       # 配置管理
│   │   ├── config_manager.py         # LLM 配置增删查
│   │   └── config_generator.py       # .env / llm_configs 模板生成
│   ├── datasets/                     # 数据集加载层
│   │   ├── dataset_loader.py         # SWE-bench 加载器 + 数据模型 / 抽象基类 / 工厂函数（Defects4J 与 InMemory 子类已拆出）
│   │   ├── dataset_defects4j.py      # Defects4J-Python 加载器（0.1 拆分）
│   │   ├── dataset_inmemory.py       # 内置示例数据集（0.1 拆分）
│   │   └── synthetic_dataset.py      # 合成数据集生成器（本地生成）
│   ├── cli/                          # 命令行界面（click 命令组 + rich 输出）
│   │   ├── app.py                    # CLI 命令定义与任务执行
│   │   └── output.py                 # ANSI/Rich 终端输出工具
│   ├── utils/                        # 公共工具
│   │   ├── exceptions.py             # 统一异常层级
│   │   ├── helpers.py                # 正则 / JSON / 代码块提取等工具
│   │   └── logging_utils.py          # 日志工具
│   ├── tools/                        # 工具函数模块
│   │   ├── code_analyzer.py          # AST 代码分析（精确替换，避免正则误匹配）
│   │   ├── patch_applier.py          # 补丁应用（支持完整文件和单函数模式）
│   │   ├── code_context.py           # AST 智能截取（P0 大文件上下文优化）
│   │   ├── dependency.py             # 依赖检测与 venv 缓存管理（P1 执行隔离）+ 4.4 命中率统计/清理
│   │   ├── multi_candidate.py        # 多候选补丁生成与验证筛选（3.1，默认关）
│   │   └── cross_file.py             # 3.5 跨文件修复（协调器-提议者架构，默认关）
│   ├── graph/                        # 工作流编排模块
│   │   ├── workflow.py               # LangGraph 工作流图（支持消融开关；节点注册与 RAG 接线）
│   │   ├── nodes.py                  # 节点函数实现（_planner/_generator/_executor/_cross_file_analyzer + 编排节点；
│   │   │                               大簇已按批次 S7/S4 拆分至 trace_reward/flags/agents_cache/debugger/patch_io，全量 re-export 保持历史导入路径）
│   │   ├── trace_reward.py           # R3 S7：6 纯函数轨迹/奖励/迭代策略（自 nodes.py 拆分，re-export 保留）
│   │   ├── flags.py                  # R3 S7：开关读取函数簇（自 nodes.py 拆分，re-export 保留）
│   │   ├── agents_cache.py           # R3 S7：Executor/通用 Agent 实例复用缓存（自 nodes.py 拆分，re-export 保留）
│   │   ├── debugger.py               # R3 S7：_diagnosis_node/_debugger_node 节点实现（自 nodes.py 拆分，re-export 保留）
│   │   ├── patch_io.py               # R4 S4：补丁应用安全核心（路径白名单 + 原子写盘 + 多候选选择 + 安全写盘 + 快照回滚，自 nodes.py 拆分，re-export 保留）
│   │   ├── rag.py                    # RAG 检索器单例管理（get_rag_retriever，经 workflow.py re-export）
│   │   ├── tracing.py                # 追踪层接线（任务级 JSONL 会话，经 workflow.py re-export）
│   │   ├── state.py                  # 全局状态定义（TypedDict）+ create_initial_state 工厂（单一构造点）
│   │   └── token_usage.py            # 线程局部 LLM token 用量统计（P0 效率指标）
│   ├── observability/                # 结构化可观测性（4.1）
│   │   └── trace.py                  # JSONL 节点级追踪（默认关，AITESTER_TRACE_DIR 启用）
│   ├── prompts/                      # 提示词模板
│   │   └── templates.py              # Planner/Generator/Debugger 系统提示词（PLANNER_SYSTEM_PROMPT 等）
│   ├── db/                           # 数据库模块
│   │   └── mysql_client.py           # MySQL 单例客户端（任务、测试、修复记录）
│   ├── rag/                          # 检索增强生成模块
│   │   └── retriever.py              # ChromaDB 向量检索器（测试用例与修复案例）
│   ├── reports/                      # 报告生成
│   │   └── generator.py             # 实验结果报告
│   └── experiments/                  # 实验分析
│       └── analysis.py               # 统计检验与结果分析
├── experiments/                      # 实验脚本模块
│   ├── run_benchmark.py              # 批量基准测试（多基线对比 + 消融实验 + 公平性 token 输出）
│   ├── visualize_results.py          # 结果可视化（柱状图 + 详细表格 + 统计检验）
│   ├── analyze_results.py            # 结果分析脚本（4.3 + 1.1/1.2/1.3/3.2/4.4：Markdown 汇总 + RAG 自动汇总 + 修复收敛/质量代理指标 + 异味检测 + 变异得分 + 边界覆盖 + 执行轨迹 + 缓存命中率，旧 JSON 兜底）
│   ├── compare_failures.py           # 失败翻转任务对比（Planner/Debugger/环境归因 + 5.3 跨批次失败模式对比）
│   ├── analyze_failures.py           # 失败案例聚类报告（供技术评审使用）
│   ├── mutation_testing.py           # 1.2 内置变异测试生成器（AST 级七类变异体 + mutation_score_from_details 汇总；杀死判定按 pytest 官方退出码精确化，2026-09-26）
│   ├── contamination_check.py        # 2.1 SWE-bench 数据污染检测（token 级 Jaccard 重叠度）
│   ├── difficulty_stratification.py  # 2.2 任务难度分层分析
│   ├── run_large_scale.py            # 大规模实验入口
│   ├── run_statistical_test.py       # 统计检验入口
│   └── statistical_analysis.py       # 统计分析工具
├── reproduce.sh                    # 一键实验复现脚本（quick/full 模式）
├── tests/                            # 单元测试
│   ├── test_code_analyzer.py
│   ├── test_error_classifier.py
│   ├── test_patch_applier.py
│   └── test_dataset_loader.py        # 数据集加载器测试（新增）
├── docs/                             # 文档
│   ├── algorithm_design.md           # 算法设计与理论描述
│   ├── api_reference.md              # API 参考
│   ├── usage_examples.md             # 使用示例
│   ├── performance_guide.md          # 性能调优指南（含性能剖析基准）
│   ├── failure_analysis.md           # 失败案例分析（历史快照）
│   └── history/                      # 归档的历史轮次工作记录
│       ├── optimization_plan.md
│       └── optimization_report.md
├── examples/                         # 示例被测代码（含已知 bug）
│   ├── calculator.py                 # 计算器示例（除零、负数阶乘 bug）
│   ├── buggy_library.py              # 算法库示例（二分查找、排序合并等）
│   └── string_utils.py               # 字符串工具示例（回文、Caesar 密码等）
├── scripts/                          # 仓库级脚本（见 scripts/README.md）
│   ├── gates/                        # CI / pre-commit 阻断项（27 个脚本，`ls scripts/gates/*.py | wc -l` 可复算；ci.yml 硬接 25 个唯一脚本/28 处调用，另 2 个在 perf.yml 等专用工作流）
│   │   ├── check_baseline.py         # BASELINE.yaml 健全性
│   │   ├── check_lock_sync.py        # requirements.txt ↔ requirements.lock 同步
│   │   ├── check_branch_coverage.py  # 核心路由分支覆盖门槛
│   │   └── ...                       # 双语配对 / 引用真实性 / 工件入库 / 覆盖率 ratchet 等
│   └── tools/                        # 运维 / 生成 / 实验辅助（17 个，不阻断）
│       ├── bootstrap_dev.sh          # 开发者环境搭建
│       ├── smoke_test.sh             # 发布前冒烟
│       └── performance_benchmark.py  # 性能基准
├── main.py                           # CLI 入口（薄封装，实现位于 src/cli/）
├── config.py                         # 全局配置（含消融实验开关）
├── init_db.py                        # 数据库初始化脚本
├── setup.py                          # 包管理配置
├── requirements.txt                  # Python 依赖列表
├── Dockerfile                        # Docker 镜像定义
└── .env.example                      # 环境变量模板
```

## 核心方法

### 1. 逻辑驱动思维链（Logic-driven Chain-of-Thought）
Planner 在输出测试计划前，先对函数进行**输入域、输出域、前置条件、后置条件、边界情况**的显式分析，引导 Generator 按逻辑覆盖生成测试用例。

**技术实现**：
- [src/agents/planner.py](src/agents/planner.py) 中的 `PlannerAgent.plan()` 方法
- [src/prompts/templates.py](src/prompts/templates.py) 中的 `PLANNER_SYSTEM_PROMPT`

### 2. 分层错误修复机制（Hierarchical Repair Strategy）
**局部化先行（2026-10-07 修复引擎范式转向）**：修复流程升格为"**局部化 → 合成 → 验证**"三段，局部化从"Debugger 的副产品"升格为可独立量化的第一阶段——谱系通道（Ochiai Top-k，零 LLM）提供行级可疑度佐证，推理通道（RGFL 式 LLM 结构化定位：函数 / 行区间 / 置信度 / 推理依据）只定位不修复，两通道融合后与谱系段落并列注入 Debugger prompt；LLM 失败 / JSON 解析失败保守降级 None，不产出假定位、不阻断修复。局部化质量由独立指标量化：`localization_hit_function`（LLM 定位函数 ∈ gold 变更函数集合）与 `fl_at_k`（谱系行级 Top-k 命中）。

**技术实现**：
- [src/agents/fault_localizer.py](src/agents/fault_localizer.py) 中的 `FaultLocalizerAgent.localize()`（推理定位）与 `gold_changed_functions()` / `localization_hit()`（gold 口径提取与函数级命中判定）
- [src/agents/fl_spectral.py](src/agents/fl_spectral.py) 中的谱系定位测量层（Ochiai Top-k）
- [src/graph/nodes.py](src/graph/nodes.py) 中的 `_debugger_node`（双通道融合接线，定位结果写 `state["llm_localization"]` 供实验层消费）

将测试失败分为十七类：**LLM 响应格式异常（llm_format_error）、LLM 空响应（llm_empty_response，P0 4.1 子类）、LLM JSON 解析失败（llm_json_parse_failed，P0 4.1 子类）、导入失败（import_error）、语法错误（syntax）、类型不匹配（type_error）、索引越界（index_error）、断言失败（assertion）、测试逻辑错误（logic_error）、运行时异常（runtime）、超时（timeout）、未知（unknown）、补丁被安全守卫拒绝（patch_validation_failed）、RAG 检索全空（rag_retrieval_empty）、执行轨迹丢失（execution_trace_missing）、多候选全被静态筛选拒绝（multi_candidate_all_rejected）、补丁语法反复损坏（patch_syntax_invalid，2.2 重采样耗尽标记，2026-09-27 第十一轮新增）**，每类采用差异化修复策略（P2 细化：import/type/logic 三类从旧的五类中拆出；1.2 残余：LLM_FORMAT_ERROR 与 INDEX_ERROR 从 UNKNOWN 拆出；1.1 状态细化：PATCH_VALIDATION_FAILED 与 RAG_RETRIEVAL_EMPTY 为流程状态类；5.2 持续细化：EXECUTION_TRACE_MISSING 与 MULTI_CANDIDATE_ALL_REJECTED 为多候选/轨迹流程类；P0 4.1 子类：LLM_EMPTY_RESPONSE 与 LLM_JSON_PARSE_FAILED 为 LLM_FORMAT_ERROR 的两个精确子类，由 `ErrorClassifier.classify_llm_response()` 在 Debugger 收到 LLM 响应后、JSON 解析前直接分类，命中时用更严格 prompt 重试一次并记录原始响应片段，不走 `classify()` 文本正则，成功任务原样返回）。

**技术实现**：
- [src/agents/error_classifier.py](src/agents/error_classifier.py) 中的 `ErrorClassifier` 类（规则匹配）
- [src/agents/debugger.py](src/agents/debugger.py) 中的 `DebuggerAgent.debug()` 方法
- [src/prompts/templates.py](src/prompts/templates.py) 中的 `DEBUGGER_SYSTEM_PROMPT`

### 3. AST 精确代码替换
使用 `ast` 模块进行函数解析和替换，避免正则表达式在嵌套函数或同名函数场景下的误匹配问题。

**技术实现**：
- [src/tools/code_analyzer.py](src/tools/code_analyzer.py) 中的 `replace_function_code()` 函数
- [src/tools/patch_applier.py](src/tools/patch_applier.py) 中的 `apply_patch_to_code()` 函数

### 4. 检索增强生成（RAG）
使用 ChromaDB 存储历史成功测试用例和修复补丁，在 Generator 和 Debugger 生成前检索相似案例作为参考。

**技术实现**：
- [src/rag/retriever.py](src/rag/retriever.py) 中的 `TestCaseRetriever` 类
- 在 [src/graph/workflow.py](src/graph/workflow.py) 中通过 `ENABLE_RAG` 标志控制启用/禁用

### 5. 多基线对比与消融实验（新增）
支持四种实验配置，一键对比不同组件的贡献：

| 基线名称 | 配置 | 说明 |
|---------|------|------|
| `aitester` | Planner+Debugger 均启用 | 完整多智能体系统 |
| `plain_llm` | Planner+Debugger 均禁用 | 纯 LLM 单次调用基线 |
| `single_agent` | Planner+Debugger 合并为一次调用 | 单智能体对比基线 |

**消融实验开关**（在 [config.py](config.py) 中读取默认值，可通过 `.env` 注入环境变量覆盖；`.env` 已加入 `.gitignore`，不入库）：
```bash
ENABLE_PLANNER=true      # 启用 Planner（默认 true）
ENABLE_DEBUGGER=true     # 启用 Debugger 修复循环（默认 true）
ENABLE_RAG=false         # 启用 RAG 检索增强（默认 false）
```

### 5.1 多候选补丁与验证（3.1，默认关闭）
单补丁"一步走错步步错"的风险：LLM 偶发输出语法残缺/误删函数/改错行时，坏补丁会污染 target_code 并带着错误诊断进入下一轮迭代，白白消耗修复预算。多候选补丁策略在同一轮内生成 N 个候选（视角扰动提示让各候选走不同修复路径：最小改动/根因修复/防御式修复），静态筛选（`ast.parse` 语法 + 函数完整性 + 10% 长度安全）淘汰坏候选，可选执行验证逐候选跑测试选通过率/覆盖率最高者，仅当选中的候选严格优于原代码才提交。

**技术实现**：
- [src/tools/multi_candidate.py](src/tools/multi_candidate.py) 中的 `generate_candidates()` / `select_best_candidate()` / `static_validate_patch()`
- 经 [src/graph/workflow.py](src/graph/workflow.py) 的 `_patch_applier_node` 接入，`ENABLE_MULTI_CANDIDATE_PATCH` 默认 false 保持历史实验口径，无有效候选自动回退单补丁

### 5.2 结构化可观测性（4.1，默认关闭）
JSONL 追加式记录每个任务各智能体节点的输入输出、决策路径（debug/done/regenerate）、token 消耗与墙钟耗时，供实验分析逐智能体重放（日志是给人看的、会被脱敏采样，无法支撑结构化回放）。`AITESTER_TRACE_DIR` 未设时全 no-op 零性能税，已设时按 `<task_uuid>.trace.jsonl` 落盘并过脱敏。

**技术实现**：
- [src/observability/trace.py](src/observability/trace.py) 中的 `TraceSession` 类
- workflow 各节点（planner/generator/executor/debugger/patch_applier/_should_debug）逐节点记录，benchmark 入口与 CLI 在 finally 收尾 task_end

### 5.3 成本感知路由（3.4 + 3.2 阈值可配）
`APIManager` 的 `COST_AWARE` 策略按"成功率 50% + 1/成本 50%"综合评分排序，故障转移时避免把全量流量切到昂贵 provider；转移到 `cost_weight >= 阈值`（`APIManagerConfig.cost_alert_threshold`，默认 2.0，3.2 可配——阈值过低导致误报多时上调如 3.0/5.0，成本敏感度高时下调，无需改代码）的昂贵节点时记 WARNING 成本告警（`cost_alert_enabled` 可关，告警文案打印配置阈值避免误导调参）。`LLMConfig.cost_weight` 经 `LLM_N_COST_WEIGHT` 读取（0.1~1000，未配置默认 0.0=无信息、APIManager 回退 1.0 基准；`APIManagerConfig.node_cost_weights` 支持显式映射覆盖）。

**技术实现**：
- [src/api/api_manager.py](src/api/api_manager.py) 中的 `RotationStrategy.COST_AWARE` / `_select_node_cost_aware()` / 成本告警分支

### 5.4 RAG 纳入主实验（2.3）
`reproduce.sh` 的 RAG 默认口径已随 **W7（2026-10-05 审查落地·阴性证据驱动）改为默认关闭**（RAG A/B 实测 token +40.7% 负向、无成功率增益，见 `docs/experiment_ab_results_2026-09-28.md`）；需对照时显式 `--enable-rag`。`run_benchmark.py` 的 `--no-rag` / `--enable-rag` 参数共同覆盖 `config.ENABLE_RAG`。

### 5.5 结果分析脚本（4.3 + 1.1/1.2 首批指标增强）
`experiments/analyze_results.py` 从 benchmark JSON 提取成功率 / 覆盖率 / 迭代次数分布 / Token 效率 / 按基线失败原因分布（1.2 细化类别可单独计数）/ RAG 检索质量 / 修复收敛效率（首次尝试成功率、成功与失败任务的迭代及耗时统计）/ 多维质量代理（覆盖率与耗时代理、可选 `generated_test` 的断言行数代理、失败类别 Top N），终端打印 Markdown 汇总并写 `analysis_summary.md`；旧 JSON 无 `token_metrics`/`rag_metrics`/`generated_test` 键时自动兜底或降级，不崩。

```bash
# 分析最新一次 benchmark 结果
python experiments/analyze_results.py --results-dir experiments/results

# 分析指定文件
python experiments/analyze_results.py --input experiments/results/benchmark_xxx.json
```

### 5.6 熔断冷却期 + 半开探测（4.1 + 4.2）
`APIManager` 的熔断器在节点连续失败达 `max_consecutive_failures` 后进入冷却期（`APIManagerConfig.circuit_cooldown_seconds`，默认 60s）。冷却期内即使健康检查线程把 `is_healthy` 翻回 True，路由层（`get_healthy_nodes()` 与 `_build_node_list` 备用候选）仍跳过该节点，避免流量重新打回死 provider（浪费时间与 token）；`mark_success` 复位熔断器，`get_status()` 暴露 `circuit_open_remaining_s` 与 `circuit_state`（closed / open / half_open）字段供监控。

4.2 半开探测（默认开，`APIManagerConfig.enable_half_open_probe=True`）：冷却到期后节点不直接恢复全量路由，而是进入"半开"窗口——该节点被纳入路由候选（`in_circuit_half_open`），承载一次探测请求；探测成功闭合熔断器恢复全量路由，失败则重新打开半程冷却期（`min(cooldown/2, half_open_probe_penalty_cap_seconds)`，默认 cap 30s），防止死 provider 被反复打流量。`call()` 与 `check_health()` 的成功 / 各异常分支统一消费探测结果；置 `enable_half_open_probe=False` 退回 4.1 直接放行行为，便于对比实验。

### 5.7 SWE-bench 源码导出自动化（2.1）
官方 SWE-bench JSONL 无 `instance_code` 字段（任务只有 patch 文本）。新增 `scripts/tools/export_swe_bench_source.py` 自动补全：读取已下载的 JSONL，按 patch 的 `+++ b/<path>` 提取首个非测试目标文件，经 `git show <base_commit>:<path>` 只读导出（不污染工作树），输出 `SWE_BENCH_ENRICHMENT` 格式的 enrichment JSONL；支持 `--instance-ids`（逗号或 @文件，配合 check-dataset 输出的缺失列表批量补）、`--dry-run`、`--limit`。`SWEBenchDataset` 新增 `tasks_missing_source()`（识别 instance_code 兜底为 issue 文本的任务）；`check-dataset` 质量报告输出缺失源码的 instance_id 列表与补全指引。

```bash
# 补全全部缺失源码（需 SWE-bench 仓库缓存 + git）
python scripts/tools/export_swe_bench_source.py --dry-run          # 先看导出计划
python scripts/tools/export_swe_bench_source.py --instance-ids @missing_ids.txt
# 加载 enrichment（自动合并到任务的 instance_code）
python main.py check-dataset swe_bench
```

### 5.8 跨文件修复（3.5，默认关闭）
经验观察（**未一手核验**，见 `docs/citation_allowlist.txt`）：真实数据集（SWE-bench / Defects4J）中相当一部分任务需要多文件修改——本项目不以该比例作为论据支撑。协调器-提议者架构：`cross_file_analyzer` 节点（`CROSS_FILE_ENABLE=true` 时启用）在 `executor → debugger` 之间插入，做 AST 跨文件 import 依赖分析，把依赖边写入 `state["cross_file_deps"]`；`_patch_applier_node` 在跨文件分支按拓扑序对多个模块应用补丁（被调用方先改，调用方后改），任一文件应用失败整体回滚（与单文件 `safe_apply_patch` 同口径）。单文件项目自动降级（依赖边为空时 `cross_file_plan=None`，走单文件路径）。

**0.7 二期增强**（`src/tools/cross_file.py`，默认行为不变，以下为新增能力）：
- **多入口依赖分析** `analyze_multi_entry_deps(entry_modules, source_files, max_depth=1)`：对多个入口模块做一级 import 展开（保守口径，不递归——防依赖图爆炸），去重合并各入口的依赖边（同 `(source, target, symbol)` 保留 `call_line` 最小者）。一期单入口 `analyze_cross_file_deps` 保持原签名不变（多入口是叠加能力）。
- **拓扑序补丁应用** `apply_multi_file_patch(..., deps=...)`：传入依赖边时按依赖图拓扑序应用（被调用方先改、调用方后改，Kahn 算法 + 环按字典序打破）；不传 `deps`（None）时退回模块名字典序（一期口径），保持历史实验可比性。
- **修复计划缓存** `build_cross_file_repair_plan_cached(...)`：相同依赖图指纹（入口 + 依赖边 + max_modules 的 SHA1）落盘 LLM 缓存目录（复用 `AITESTER_LLM_CACHE` / `AITESTER_LLM_CACHE_DIR` 口径），命中时零 LLM 调用；`use_cache=False` 或缓存开关关闭时退化为不缓存。

```bash
# 启用跨文件修复（显式设置环境变量）
CROSS_FILE_ENABLE=true CROSS_FILE_MAX_MODULES=5 python main.py run examples/calculator.py
# 默认关闭（历史单文件口径不变）
```

设计文档：[docs/design/cross_file_repair.md](docs/design/cross_file_repair.md)

### 5.9 断言增强策略（3.4，默认关闭）
`GeneratorAgent` 在生成前先 AST 提取被测代码中已有 `assert` 语句（去重，最多 10 条），作为"锚点断言"注入 prompt，引导 LLM 避免断言弱化 / 恒真断言 / 魔数未命名等异味。默认 `false` 保持历史生成口径；启用需显式 `ASSERTION_AUGMENT_ENABLE=true`。

### 5.10 依赖缓存监控（4.4）
`venv` 缓存从"有复用无监控"升级为"命中率可观测 + 可清理"：
- `get_venv_cache_stats()`：进程内累计 hit/create 事件 + 落盘 JSON 跨进程聚合，返回 `hit_rate = hits/(hits+creates)`
- `list_venv_cache()`：列出缓存目录所有 venv（name/path/size_mb/created_at）
- `clear_venv_cache(max_age_days, max_size_mb)`：按年龄/大小过滤清理，均 None 时清空

### 5.11 测试异味检测 / 修复收敛曲线 / 收敛失败模式归因 / 边界用例覆盖 / 变异得分 / 断言强度 AST 增强（1.2/1.3）
`experiments/analyze_results.py` 新增六个保守可复算章节（全部"字段缺失即跳过"，旧 JSON 不崩）：
- **测试异味检测（1.2）**：AST 扫 `details[].generated_test`，识别 Assertion Roulette / Magic Number / 断言弱化 / 平凡测试 4 类异味
- **修复收敛曲线（1.3）**：按迭代轮次 0/1/2/3+ 统计累计通过率与平均耗时，观察"随迭代增加通过率如何变化"
- **收敛失败模式归因（1.2）**：对达到 MAX_ITERATIONS 仍未修复的任务，区分"无法定位根因"（诊断反复同义且从未写盘成功）与"无法生成有效补丁"（补丁写盘成功但测试仍失败 / 被安全守卫反复拒绝）
- **边界用例覆盖（1.3）**：AST 保守判定 `generated_test` 是否覆盖 None / 空字符串 / 空集合 / 0 / -1 / >= / <= 等边界条件，输出各边界类型命中数与覆盖率
- **变异得分（1.3）**：收集 `details[].mutation_score`（外部变异测试器如 mutmut 产出），汇总平均 / 高（>=0.7）/ 低（<0.4）分布；无该字段时跳过章节
- **断言强度 AST 增强（1.3）**：在原有 `assert` 行数统计基础上新增 AST 口径（`ast.parse` + `ast.Assert` 节点计数），输出 `ast_avg_assertions` 与 `ast_parse_failed_tasks`（解析失败任务清单，可交叉异味检测）

旧 JSON 无 `generated_test` / `mutation_score` 字段时自动降级，不崩溃。

### 5.12 失败根因分类与案例知识库（5.3）
`experiments/analyze_failures.py` 新增：
- **失败根因分类**：三大根因（`llm_capability` / `dependency` / `framework`）按 `error_category` + `diagnosis` 关键词保守启发式归类
- **案例知识库**：按 `error_category` 多样性优先选取典型失败案例，结构化为 `（工件已清除）`（含 task_id / root_cause / reproducible_steps / suggested_fix；由本脚本 `-k` 选项生成，属离线派生物、默认不入库）

CLI 新增 `--knowledge-base/-k` 选项控制输出路径。

### 5.13 执行反馈轨迹收集（3.2）
`state.py` 新增 `execution_trace` 字段（list，默认 `[]`，`create_initial_state` 同步初始化），`nodes.py` 的 `_executor_node` 每次执行追加一条记录到 `state["execution_trace"]`：

```
{
  "iteration": int,
  "passed": bool,
  "coverage": float,
  "coverage_delta": float | None,   # 首轮为 None
  "elapsed_seconds": float,
  "reward_signals": {               # 保守线性归一，仅记录观测，不参与路由
    "correctness": 0.0 | 1.0,
    "efficiency": 0.0~1.0,          # 1 - elapsed / EXECUTION_TIMEOUT
    "simplicity": 0.0~1.0           # 1 - elapsed / (EXECUTION_TIMEOUT * 2)
  }
}
```

纯观测层默认常开（不影响修复路由），`run_benchmark.py` 结果行带 `execution_trace`（失败分支 `None` 兜底保持键集合同构）；`analyze_results.py` 新增"执行反馈轨迹汇总（3.2）"章节：统计观测任务数 / 总执行次数 / 平均轮数 / 首轮即通过率 / 末轮 correctness & efficiency 均值 / 首末轮覆盖率趋势（delta）。旧 JSON 无该字段时章节跳过。

> 用途：为未来执行反馈驱动的微调（如 BoostAPR 类方法）备料——每次 benchmark 自动把"通过/失败、覆盖率变化、耗时、多维奖励信号"落进结果 JSON，无需额外执行轨迹采集脚本。

### 5.14 内置变异测试生成器（1.2，2026-09-26 判定口径精确化）
`experiments/mutation_testing.py` 提供 AST 级轻量变异生成器，无需 mutmut 依赖即可产出 mutation_score：

- **七类变异体**：运算符翻转（`_OPERATOR_FLIP_MAP` 仅保留等值对 `Eq`↔`NotEq`，边界语义变异专属 `boundary_shift` 互不重叠）/ 布尔取反（`_RemoveNotTransformer` 改写 `If/While/Return/Assign/BoolOp/Compare/Expr` 槽位的 `not X → X`，仅当真正替换成功才计入变异体，避免死代码）/ 数字常量偏移（比较中常量 `value → value+1`）/ 边界移位（`Gt`↔`GtE`）/ 空返回（`return X → return None`）/ 空容器返回（`return X → return 空容器`）/ 异常路径（`_RemoveRaiseTransformer` 删除 raise + 异常类型替换 `exception_type_swap`）
- **变异体定位精确化（P1，2026-09-26）**：`_flip_comparison_op` / `_offset_numeric` / `_shift_boundary_op` 在 deepcopy 后按 **(lineno, col_offset) 双键**定位目标比较表达式（此前按行号取第一个同类型 `Compare`，同行多比较 `a < b and c < d` 时只改第一个且 description 记录原节点操作符，产生描述与改动不一致 + 重复变异体）；
- **取样策略（P1，2026-09-26）**：`generate()` 按 `mutant.code` **去重**（消除重复变异体）+ **类型轮转均匀取样**（7 类分桶 round-robin 填满上限，保证每类都有代表——此前按注册顺序 `mutants[:20]` 截断会把第 5-7 类整体挤掉）；保守口径：每任务 ≤ 20 个变异体（`_MAX_MUTANTS_PER_TASK`），仅处理纯 Python 函数体；语法错误返回空列表不阻断；
- **杀死判定按 pytest 官方退出码（P0，2026-09-26）**：`_run_mutant_tests` 精确判定 `rc == 1`（有测试失败）= 杀死；`rc == 0` = 存活；其他（2=收集错误 / ModuleNotFoundError / 语法错误 / 5 / 超时 / 异常）= **存活**（保守口径，与文档声明"执行失败视为存活"一致——此前把所有非零退出码一律当"杀死"，实测 e2e 下 import 名错配时每个变异体 rc=2 全误判"杀死"，mutation_score 恒 1.0，弱测试与强测试得分无法区分，指标失效）；
- **`mutation_score_from_details`**：收集 `details[].mutation_score`（0.0-1.0），汇总平均 / 高（>=0.7）/ 低（<0.4）分布；无该字段时 `available=False` 跳过；
- **可选 mutmut 兜底**：系统已安装 mutmut 时优先使用其完整结果，否则回退内置生成器；
- **`run_benchmark` 流水线接线**（`ENABLE_MUTATION_SCORING`，默认关闭）：开关启用时
  `experiments/run_benchmark.py` 在基线结果构建后逐任务调用
  `compute_mutation_score`，把 `mutation_score` 写回 `details[]`，
  `analyze_results._mutation_score_metrics` 即可汇总；`generated_test`
  字段经 `_build_task_result` 写进标准结果 JSON（此前仅经 `--save-state`
  落盘 raw/）。CLI `--enable-mutation` / `--no-mutation` 显式覆盖配置默认。

```python
from experiments.mutation_testing import MutationGenerator, mutation_score_from_details

gen = MutationGenerator()
mutants = gen.generate(target_code)  # 每个 Mutant 可单独跑测试套件
# 统计被杀死比例 → details[].mutation_score
score = mutation_score_from_details(details)  # → {"available": True, "avg_mutation_score": 0.65, ...}
```

```bash
# 启用变异得分的 benchmark（每任务 ≤ MUTATION_MAX_MUTANTS 变异体，耗时显著增加）
ENABLE_MUTATION_SCORING=true MUTATION_MAX_MUTANTS=10 \
    python experiments/run_benchmark.py --dataset examples --baselines aitester
# 或显式 CLI 开关
python experiments/run_benchmark.py --dataset examples --baselines aitester --enable-mutation
```

### 5.15 跨批次失败模式对比（5.3）
`experiments/compare_failures.py` 新增 `cross_batch_comparison` / `render_cross_batch_section`：追踪多个 benchmark JSON 批次间失败模式变化，输出 `new_categories`（新出现）/ `resolved_categories`（已消失）/ `regressed_categories`（数量增长）三类趋势，渲染为"跨实验批次失败模式对比（5.3）"章节。

```bash
# 对比 3 个批次（按时间顺序，旧批次在前）
python experiments/compare_failures.py \
    --results experiments/results/benchmark_synthetic_20260918.json \
    --cross-batch \
        experiments/results/benchmark_synthetic_20260901.json \
        experiments/results/benchmark_synthetic_20260907.json \
    --cross-batch-baseline aitester
```

**落地记录约定（2026-09-28 新增）**：跨批次对比的实际发现（`new_categories` / `resolved_categories` / `regressed_categories` 及对应批次日期）应在跑完多批次后记录到 `CHANGELOG.md` 对应条目或 `docs/failure_analysis.md` 的"快照更新约定"链接区，避免该工具长期只有输出格式示例、缺乏实证。建议每次重大版本发布（新错误分类 / 修复策略批次）后固定跑一次跨批次对比并归档结果 JSON，作为下一版本文档的输入数据。

### 5.16 对抗性推理 + 双向依赖图 + 多维污染检测（3.1 / 2.2 / 2.1，默认关闭）
本轮新增的三项能力，均以环境变量开关默认关闭保持历史实验口径，启用为显式行为：

- **对抗性推理（3.1，`ADVERSARIAL_DEBUGGING_ENABLE`）**：Debugger 在生成补丁前注入 2-3 个"击穿当前实现"的对抗性意图假设（AdverIntent-Agent 式），生成针对性测试；生成后独立"批评者"LLM 调用尝试构造击穿用例；被击穿则把负面反馈注入 prompt 重新生成一次补丁（仍失败保留当前并记录风险）。纯观测层，启用会增加 2-4 次 LLM 调用/修复轮。

```bash
# 启用对抗性推理（显式设置环境变量）
ADVERSARIAL_DEBUGGING_ENABLE=true python main.py run examples/calculator.py
```

- **双向依赖图（2.2，`CROSS_FILE_BIDIRECTIONAL`）**：在 3.5 跨文件修复（§5.8）基础上额外收集"其他模块→entry"反向依赖边（被调用方视角），使修复计划能同步更新调用方模块。需配合 `CROSS_FILE_ENABLE=true` 生效，独立开关保证"跨文件启用 ≠ 双向启用"两级保守。

```bash
# 启用跨文件 + 双向依赖图（两级开关）
CROSS_FILE_ENABLE=true CROSS_FILE_BIDIRECTIONAL=true python main.py run examples/calculator.py
```

- **多维污染检测（2.1）**：在 token Jaccard 之外新增结构级（AST 语句骨架 LCS 比率）与语义级（token 词袋余弦，`_embed_code` 钩子可接 CodeBERT）两个维度，`patch_semantic_similarity` 输出三维相似度；`detect_contamination` 每任务输出 `risk_level`（取最严重维度）+ `contamination_summary`（污染 vs 无污染的各自成功率与 delta）；`render_resistant_benchmark_section` 注册 SWE-rebench 抗污染基准（交叉验证建议）。

```bash
# 多维污染检测（experiments/contamination_check.py）
python experiments/contamination_check.py \
    --gold-patches experiments/results/benchmark_xxx.json \
    --output experiments/results/contamination_report.json
```

### 5.17 熔断器指数退避 + Prometheus 导出（4.4，默认开）
`APIHealth` 的熔断器冷却期改按 `base * 2^open_count` 指数退避（封顶 `half_open_probe_penalty_cap_seconds`）：彻底死掉的 provider 冷却期单调增长（第 1 次 60s → 第 2 次 120s → 第 3 次 240s → …），避免反复短冷却打同一死点；`mark_success` 重置 `circuit_open_count`。`APIManager` 新增 `to_prometheus_text()` 导出 7 类 Prometheus 指标（health / circuit_state / open_remaining_s / open_count / probe_success_rate / success_rate / avg_response_ms）供监控抓取，纯旁路不影响既有路由行为。

```bash
# 启用 Prometheus 导出（显式设置环境变量）
API_PROMETHEUS_EXPORT=true python main.py run examples/calculator.py
# 回退 4.2 固定冷却期口径（便于对比实验）
API_CIRCUIT_BACKOFF=false python main.py run examples/calculator.py
```

### 5.18 多维评估指标深化 + 变异反馈闭环（1.1 / 1.2）
- **多维评估指标**（1.1，`experiments/analyze_results.py`）：测试异味检测扩展 Eager Test + Lack of Cohesion 两类 AST 口径，异味统计按策略分组，新增 `smell_density`（有异味任务占比）；新增收敛 token 效率（逐轮 token/边际收益）、难度分层迭代分布、变异-断言强度交叉一致性校验、RAG vs 无 RAG token/迭代对比 + 相似度直方图、三类失败根因占比与时间趋势、高/低污染风险成功率 delta。
- **变异反馈闭环**（1.2，`experiments/mutation_testing.py` + `src/agents/generator.py`）：新增 `boundary_shift`（Gt↔GtE 边界语义变异）与 `return_void`（return X → return None）两类变异体；`build_mutation_feedback()` 把"存活变异体"打包成可注入 Generator prompt 的反馈字典（MutGen 式"变异引导测试增强"闭环）；`run_benchmark` 的 `--enable-mutation` 开关启用时把反馈写回结果行。

```bash
# 启用变异反馈闭环的 benchmark
ENABLE_MUTATION_SCORING=true MUTATION_MAX_MUTANTS=10 \
    python experiments/run_benchmark.py --dataset examples --baselines aitester --enable-mutation
```

### 5.19 错误分类体系扩展（5.2 + P0 4.1 + 2.2 子类，17 类）
`ErrorCategory` 由 12 类扩至 17 类：5.2 批次新增 `EXECUTION_TRACE_MISSING`（任务失败但 `execution_trace` 为空 = 执行器异常路径）与 `MULTI_CANDIDATE_ALL_REJECTED`（多候选全被静态筛选拒绝）；P0 4.1 批次（2026-09-25 续）再从 `LLM_FORMAT_ERROR` 拆出两个精确子类 `LLM_EMPTY_RESPONSE`（LLM 空响应）与 `LLM_JSON_PARSE_FAILED`（非空但 JSON 提取失败），由 `classify_llm_response()` 在 Debugger 收到 LLM 响应后、JSON 解析前直接分类（占失败样本 75% 的 UNKNOWN 根因之一）；2.2 批次（2026-09-27 第十一轮）新增 `PATCH_SYNTAX_INVALID`（补丁经 2.2 重采样（最多 2 次）后仍语法不合法 / AST 解析失败，由 `apply_patch_with_resample` 统计经 `_patch_applier_node` 写入 `state["error_category"]`），标识"补丁语法反复损坏"场景；`refine_failure_category` 新增 `execution_trace` / `multi_candidate_stats` / `patch_syntax_invalid` 参数，判定优先级 `patch_rejected > rag_empty > trace_missing > multi_rejected > patch_syntax_invalid`；`refine_final_error_category` 接线新字段；`get_fix_strategy` 补各类修复策略描述。

```python
from src.agents.error_classifier import refine_final_error_category

category = refine_final_error_category(final_state)  # → 17 类之一
```

### 5.19.1 补丁后处理重采样（2.2，`PATCH_RESAMPLE_ENABLE`，默认关）
`src/graph/nodes.py` 的 `_patch_applier_node` 应用失败（定位不到目标函数 /
AST 解析不通过）时，若 `PATCH_RESAMPLE_ENABLE=true` 则触发
`apply_patch_with_resample`（`src/tools/patch_applier.py`）：把"负面反馈"
（AST 错误信息 + 1.3 降级链档位温度）回传 Debugger 重新生成补丁，最多
`PATCH_RESAMPLE_MAX`（默认 2）次；仍失败则标记 `patch_syntax_invalid`
（`refine_failure_category` 消费，归一为 `PATCH_SYNTAX_INVALID`），保留原代码。
默认关闭时不产生额外 LLM 调用（历史单补丁口径零回归）。

```bash
# 启用补丁后处理重采样（默认关，显式启用）
PATCH_RESAMPLE_ENABLE=true PATCH_RESAMPLE_MAX=2 python main.py run examples/calculator.py
```

### 5.19.2 分层压缩降级链透传（1.3，`CONTEXT_TIER_DOWNGRADE_ENABLE`，默认关）
`_patch_applier_node` 的命名契约符号守卫（`check_naming_contract`）拒绝补丁时，
若 `CONTEXT_TIER_DOWNGRADE_ENABLE=true` 则调 `advance_context_tier()` 推进
上下文档位（`full_context` → `patch_ingredients` → `minimal`），并把
`(档位名, 缺失符号列表)` 作为 `contract_reject_feedback` 写入
`state`（`AITesterState` 新声明键），经 LangGraph 通道透传给下一轮
`_debugger_node`——后者按"更高约束"的上下文档位 + 更低温度重新生成
（`_build_downgrade_context` + `_downgrade_tier_temperature`），减少"创造性
改写"再破坏命名契约的概率。默认关闭时仅记录缺失符号
（`state["contract_missing_symbols"]`），不动档位（历史单补丁口径）。

```bash
# 启用 1.3 分层压缩降级链（默认关，显式启用）
CONTEXT_TIER_DOWNGRADE_ENABLE=true python main.py run examples/calculator.py
```

### 5.19.3 多维度污染检测（五、`run_benchmark._build_task_result`）
`experiments/run_benchmark.py` 的 `_build_task_result` 新增
`contamination_risk_level` 字段（high/medium/low）：对单任务调
`patch_semantic_similarity`（`experiments/contamination_check.py`）多维度
检测（token Jaccard + AST 语句骨架 LCS + 嵌入余弦/词袋余弦保守代理，
`EMBEDDING_BACKEND` 接入真实嵌入库时自动升级为 CodeBERT 类语义余弦），
综合得出 risk_level（取最严重维度）；无 golden patch 时保守返回 "low"
（无重叠证据，非"完全相同"）。供 `analyze_results` 的
`_contamination_cross_analysis` 消费（区分"含污染样本"与"不含污染样本"
的结果）。`rag_ab_experiment.compare_ab` 新增 `token_saving.delta_pct`
（RAG ON vs OFF token 消耗降低百分比，分母 `max(_mean(off_tokens), 1)`
防除零）。

**〔2026-10-22 BM 轮勘误：上段是 O 轮初稿口径，其中四处已被后续轮次改写；引用本段时以此为准〕**
① **取值域是 5 档而不是 3 档**：`high / medium / low / unknown / not_applicable`（单一事实源
`experiments/contamination_check.py`）。② **无 golden patch（或任一侧补丁为空）返回 `not_applicable`**，
不是保守 `"low"`——N7（2026-10-05 复审）实测合成数据集恒标 `low`，把"检测没有发生"混进了
"检测过且无重叠证据"。③ **检测器抛异常（补丁非 str、依赖导入失败）返回 `unknown`**
（BM 轮，2026-10-22；此前折成 `low`，把崩溃记进
`statistical_analysis.contamination_view_summary` 的干净组）；`unknown` / `not_applicable`
按 ADR-0023 **不入分母**。④ **综合口径自 E8（2026-10-10）起是"佐证原则"而不是"取最严重维度"**：
`structural` 是弱证据（200 组无关补丁配对里它单独把等级升到 medium/high 的比例 38.5%），
不得单独升档；"取 max"只在 `AITESTER_CONTAMINATION_STRICT_MAX=true` 下恢复。详见
BM 手册（分册已删除）。

### 5.19.4 mypy 静态类型检查层（2.1，`TYPE_CHECK_ENABLE`，默认关）
`src/tools/type_repair.py` 新增 `_run_mypy_findings`：`TYPE_CHECK_ENABLE=true`
时对"补丁后代码"跑 mypy 仓库级静态类型分析（PAGENT 混合架构的"仓库级
静态分析"部分），识别"未定义名称 / 参数类型不匹配 / 返回值类型与声明
不一致 / 容器类型混用"等 PAGENT 研究中的"类型/数据结构管理错误"
（占失败补丁 27.19%）；mypy 未安装时透明降级为空列表（不阻断 ast 静态层）；
仅消费高置信度错误类别（`[name-defined, arg-type, return-value,
dict-item, list-item, assignment, operator, index, has-type]`），过滤
"推断失败 / 类型不完整"类低置信度告警。`debugger.py` 的 `debug()` 新增
观测字段 `mypy_findings_count`（未启用 / 未安装时 0）。**BG（2026-10-21）**：
`mypy_findings_count=0` 只有在 `static_check_status="ok"`（检查器确实跑完
且报告可信）时才是"无类型疑点"；开关关 / 未安装 / 超时 / 崩溃 / rc 异常 /
报告损坏分别记 `disabled` / `unavailable` / `error`，逐条原因写入
`static_check_outcomes` 并随 debugger 进入图状态。pyright 后端
（`TYPE_CHECK_BACKEND=pyright`）同一口径。与
`TYPE_REPAIR_LLM_ENABLE`（LLM 层）独立开关，可同时启用（mypy 产出更多
疑点，LLM 层修复面更广）。

```bash
# 启用 mypy 静态类型检查层（默认关，显式启用）
TYPE_CHECK_ENABLE=true python main.py run examples/calculator.py
```

### 5.19.5 检出优先协议（W3，`DETECTION_FIRST_ENABLE`，默认关；ADR-0015）
历史主批次（2026-10-01，n=50）实证 `false_fix_rate=89.8%` 的根因是**奖励自指**：成功信号"自产测试通过"
与"缺陷被检出"无任何关联。检出优先协议（"先红后绿"）对齐两者：

- **首轮红灯观测**（`_executor_node`）：iteration==0（被测代码未修复）的执行写
  `detection_first_red_seen`（任务级粘性——任一轮红过即 True）；
- **路由**（`_should_debug`）：首轮全绿 + 再生成预算未用尽 → 不视为成功，路由
  `regenerate`（reason=detection_first_all_green），Generator 注入强化段落
  （断言期望值必须来自问题语义；禁止放松断言换取通过、禁止重写被测函数）；
- **终态标注**：最终通过时写 `detection_first_status`——`red_then_green`
  （先检出再修复）/ `all_green_unverified`（弱测试假成功，**评估层不得计为
  检出/修复成功**）；结果行透出两键（默认关时恒 None，键集合同构）。

"红-on-original"是 F2P 的"buggy 红"半段，无需 gold 材料即可在线生效——
这是把 `detection_rate` 从评估指标变成运行时奖励信号的最小改动路径。

```bash
# 启用检出优先协议（默认关，显式启用）
DETECTION_FIRST_ENABLE=true python experiments/run_benchmark.py --dataset synthetic --task-count 10 --baselines aitester
```

### 5.20 SWE-bench 仓库级验证（P0/P1，默认关闭）
SWE-bench 官方验证口径是"把 gold `test_patch` 应用到 `base_commit` 检出后跑
`FAIL_TO_PASS`（修复前失败、修复后须全过）+ `PASS_TO_PASS`（不得回归）"。
单临时文件 executor 装不下仓库级代码（模块名断裂 / 依赖未装 / 多源文件
补丁），故独立 `src/agents/executor_repo.py` 承载仓库级执行（默认关，
合成集 / examples 口径零变化）：

- **环境 setup**：`git clone --no-checkout --filter=blob:none` +
  `checkout <base_commit>` + `pip install -e .`（仅仓库 pyproject 依赖），
  按 `(repo, commit12)` 缓存于 `~/.cache/aitester/repo_envs/`
  （`SWE_REPO_ENVS_DIR` 可覆盖），同仓库多任务只 clone/pip 一次。
- **venv 隔离**（`SWE_REPO_VENV_ISOLATION=true`，默认关）：每 commit 环境
  旁建独立 venv，`pip install -e` 装入 venv、pytest 用 venv 的 python 运行，
  与全局 `sys.executable` 解耦。各 repo_env 共享全局 python 时，全局
  site-packages 的 editable 安装指向"最近一次 pip install -e"的 commit 源码，
  跨 commit 任务 `import <repo_pkg>` 会解析到错误版本（实测 sqlfluff
  `BaseSegment` 方法在相邻 commit 存在/缺失不一致 → AttributeError，与
  LLM 补丁无关）。venv 模式下不注入宿主 PYTHONPATH（实测带注入反而
  ImportError），PATH 前置 venv/bin。
- **LLM 补丁映射**：`_normalize_llm_patch` 剥离 LLM 输出的 python 围栏
  （``` 包裹或行首 'python' 标记）还原纯代码正文；`_diff_codes` 经 `git diff
  --no-index` 生成严格 unified diff（difflib 手工拼接在"整文件替换"场景
  产出行计数与 git 解析器不符的 corrupt patch，已修复），`---`/`+++` 头
  重写为 gold 目标文件仓库路径（`_extract_gold_target_relpath` 取官方
  gold patch 首个非测试源文件 b/ 侧路径）→ 映射进真实仓库；两串相同
  （LLM 未改动）返回空串，`FAIL_TO_PASS` 按无补丁实测裁决，不误判通过。
- **Apple Git 2.54 new-file bug 兜底**：本机 `git apply` 对 new-file 补丁
  报 clean 但产出空文件，`_apply_patch_robust` 解析 new-file section
  手动回填，测试文件内容完整。
- **路由**：`REPO_LEVEL_EXECUTION=true` + `task.metadata.source=="swe_bench"`
  + `fail_to_pass/repo_url/base_commit` 齐备 → 仅 aiterster 基线走
  `RepoExecutor.verify`，结果覆盖 `test_passed` 并写 `repo_verification`
  诊断；plain_llm / single_agent 保持原 LLM 生成测试口径（无仓库环境依赖）。
- **单元测试**：`tests/test_executor_repo.py` 17 用例（setup 缓存 /
  verify pass / verify fail / base_not_failing / test_patch_apply_failed /
  基线恢复 / venv 隔离 / LLM 补丁助手 / git diff 可应用性）。

```bash
# 仓库级 SWE-bench 验证（opt-in，默认关）
REPO_LEVEL_EXECUTION=true SWE_REPO_VENV_ISOLATION=true \
  SWE_BENCH_ENRICHMENT=./swe_bench_enrichment.jsonl \
  python experiments/run_benchmark.py --dataset swe_bench --task-limit 10 --baselines aiterster
```

### 5.21 P0 改进批次（2026-09-25 续：13 项落地）
基于 `docs/assessment_2026-09-25_improvement_directions.md` 与实验数据缺口（SWE-bench 0/20、
合成集统计已覆盖但真实集 A/B 缺失），本批次落地 13 项 P0 改进，全部默认行为兼容
（默认参数回退历史口径，显式开启才启用新能力）：

#### 5.21.1 分层代码压缩（1.1）
函数级切片替代整文件截断：`extract_function_context(source, func_name, depth=2)`
（`src/tools/code_analyzer.py`）经 `extract_focused_code()` 的 BFS 调用链闭包
（`_closure_names()`，`src/tools/code_context.py`）保留目标函数 + 直接调用
辅助函数（depth=1）或两层调用链（depth=2）。`BaseAgent.truncate_code()`
新增 `focus_depth` 参数（读 `CODE_FOCUS_DEPTH` 环境变量，默认 1），
`CODE_MAX_CHARS` 可配（默认 3000）。跨文件场景下 `debugger.py` 的
`cross_file_contexts` 经 `extract_function_context(depth=CODE_FOCUS_DEPTH)`
生成 per-module 2000 字符预算 + 总 4000 字符预算，注入 Debugger prompt。

#### 5.21.2 复杂度感知路由（1.2，DeepSeek 官方 deepseek-flash 的多实例档位）
`src/api/complexity_router.py`（新增）：`compute_complexity_score(lines, num_files, num_deps,
cyclomatic_complexity)` 输出 [0,1] 归一化复杂度评分（阈值 `<0.35 → simple` /
`<0.70 → medium` / `>=0.70 → complex`，各维度权重由 `ROUTING_COMPLEXITY_LINES_NORM`
等环境变量可配）；`complexity_class_to_routing_hints(class)` 返回路由提示
（`max_candidates` / `context_budget` / `hint_text`）。`APIManager` 的
`_select_node_by_complexity(complexity_class)` 按 cost_weight 排序 APIHealth 节点
（complex → 高 cost_weight 端点在前，simple → 低 cost_weight 端点在前），
`run_benchmark.py` 在 `create_initial_state` 后计算复杂度评分并写入
`state["complexity_class"]` / `state["complexity_score"]` / `state["complexity_breakdown"]` /
`state["routing_hints"]`。约束：仅在 DeepSeek 官方 deepseek-flash 的多个
LLM 实例档位间路由，不引入其他模型或模型家族。`MODEL_ROUTING_STRATEGY=fixed` 回退历史策略。

#### 5.21.3 补丁命名契约验证（1.3，默认开启）
`src/tools/patch_applier.py` 新增 `check_naming_contract(original_code, patched_code)`：
对比前后模块级符号（函数 / 类 / `__all__` / 注册装饰器 / 模块级常量），
缺失任何原符号则拒绝补丁应用。`_patch_applier_node` 在 `PATCH_CONTRACT_CHECK=true`
（默认 true）时调用；Debugger prompt 注入 `_CONTRACT_CONSTRAINT` 约束
（"不得修改或删除以下符号……"），从生成侧降低违约概率。

#### 5.21.4 合成数据集分层难度（2.1 + 2.2）
`src/datasets/synthetic_dataset.py` 新增 `difficulty` 参数
（`mixed` / `level1` / `level2` / `level3` / `level4`）：
- **Level 1**（历史口径）：单函数简单缺陷
- **Level 2**：多函数交互缺陷（`BUG_PATTERNS_LEVEL2`，需修改 2-3 个函数）
- **Level 3**（跨文件）：双模块构造（`CROSS_FILE_PATTERNS`，module_a 入口 +
  module_b 被调方含缺陷，`metadata.is_cross_file=True` + `module_a_code` +
  `target_module` 供跨文件修复架构消费）
- **Level 4**：边界条件 + 异常路径隐蔽缺陷（`BUG_PATTERNS_LEVEL4`）

`experiments/run_benchmark.py` CLI 新增 `--difficulty` 选项（仅对 synthetic 数据集生效）。

#### 5.21.5 SWE-bench 源码导出质量验证（2.3）
`scripts/tools/verify_swe_bench_export.py`（新增）：对 `SWE_BENCH_ENRICHMENT` JSONL 做
5 维度验证（非空 / 行数 >= 阈值 / Python 语法合法 / 目标函数存在 / 目标文件路径
匹配），输出结构化质量报告（`pass_rate` / `by_label` / `failed_instances` /
`avg_line_count`），CLI `--output` 写 JSON，`--instances` 可选传官方 JSONL 做交叉验证。

```bash
python scripts/tools/verify_swe_bench_export.py \
    --enrichment swe_bench_lite_enrichment.jsonl \  # 由 scripts/tools/export_swe_bench_source.py -o 生成
    --output experiments/results/enrichment_quality_report.json
```

#### 5.21.6 RAG A/B 对比实验脚本（3.1）
`experiments/rag_ab_experiment.py`（新增）：自动执行 RAG ON / RAG OFF 两次
benchmark，配对分析 token / 成功率 / 迭代轮次 / 耗时，Welch t-test +
Mann-Whitney U + Cohen's d 统计检验（与 0.7 及更早报告同口径；该代报告已撤回），按错误类型分组
分析 RAG 收益（哪类错误在 RAG ON 下显著减少），输出
`rag_ab_report.json`。支持 `--analyze-only` 模式（读已有结果 JSON 直接统计，
跳过实验运行）。

```bash
python experiments/rag_ab_experiment.py \
    --dataset synthetic --task-count 20 --seed 42 \
    --output-dir experiments/results/rag_ab_$(date +%Y%m%d)
```

#### 5.21.6b 跨文件修复 T1/T4 验收脚手架（2026-09-28 新增）
`experiments/cross_file_ab.py`（新增）：自动执行 `CROSS_FILE_ENABLE=true` /
`false` 两次 benchmark，配对分析成功率 / 迭代，并按 `docs/design/cross_file_repair.md`
§"默认启用前置条件"的 T1 / T4 验收阈值自动判定（T1：level3 跨文件子集
ON 成功率 - OFF 成功率 ≥ +15pp；T4：level1 单文件子集下降 ≤ 5pp 无回归），
输出 `cross_file_ab_summary.md` + `cross_file_ab_raw.json`。

```bash
# T1（跨文件提升）+ T4（单文件无回归）
python experiments/cross_file_ab.py --dataset synthetic --difficulty level3 --task-count 50
python experiments/cross_file_ab.py --dataset synthetic --difficulty level1 --task-count 50
```

> **配套 A/B 数据汇总**：`docs/experiment_ab_results_2026-09-28.md`（位置感知
> ON/OFF + RAG ON/OFF + 跨文件 T1/T4 三组对照实验的论文级数据与阴性结果标注）。

#### 5.21.7 多候选自适应触发（3.2，默认 adaptive）
`src/graph/nodes.py` 的 `_select_multi_candidate_patch` 新增
`MULTI_CANDIDATE_TRIGGER_STRATEGY`（默认 `adaptive`）：仅当
`iteration >= 1`（首次修复已失败）且 `error_category ∈ {assertion, runtime,
logic_error, index_error}`（困难类别）时才启用多候选；简单任务 / 早期迭代
保持单候选，省 token（避免简单任务 +79% token 的无收益成本）。
设 `MULTI_CANDIDATE_TRIGGER_STRATEGY=always` 回退历史口径。

#### 5.21.8 变异体难度升级（3.3）
`experiments/mutation_testing.py` 新增 3 类变异 transformer：
`_ReturnEmptyTransformer`（return X → return 空容器，7 种变异体类型之一）、
`_RemoveRaiseTransformer`（删除 raise 语句 → 异常路径变异）、
`_ExceptionTypeTransformer`（异常类型替换 → exception_type_swap）。
总变异体类型从 5 扩至 7（operator_flip / boolean_negation / numeric_offset /
boundary_shift / return_void / return_empty + 新增 exception_remove +
exception_type_swap），提升变异得分对"边界 + 异常路径"类缺陷的覆盖度。

#### 5.21.9 错误分类子类 + 响应格式重试（4.1）
`src/agents/error_classifier.py` 新增 `LLM_EMPTY_RESPONSE` 与
`LLM_JSON_PARSE_FAILED` 两个精确子类（从 `LLM_FORMAT_ERROR` 拆出，占 UNKNOWN
75% 的根因之一）：`classify_llm_response(raw_response)` 在 Debugger 收到
LLM 响应后、JSON 解析前直接分类（空响应 → `LLM_EMPTY_RESPONSE`；非空但
JSON 提取失败 → `LLM_JSON_PARSE_FAILED`）；两个子类各配独立修复策略
（更严格 prompt 重试 / 记录原始响应片段到 `failure_knowledge_base.json`（离线知识库，由 experiments/analyze_failures.py 生成））。
`debugger.py` 的 `debug()` 在检测到格式异常时用更严格 prompt 自动重试一次，
仍失败则降级到宽松 JSON 提取。`ErrorCategory` 现共 17 类（由 14 类逐步扩展：5.2 批次 14→16，2.2 批次 16→17，新增 `PATCH_SYNTAX_INVALID`，见 §5.19）。

#### 5.21.10 追踪层默认启用（4.2）
`experiments/run_benchmark.py` 在入口处设置 `AITESTER_TRACE_DIR` 默认值
（`<output_dir>/traces/`，若未显式设置）：节点级 JSONL 记录（输入长度、
输出长度、token、耗时、路由决策）随工作流执行自动追加到
`<task_uuid>.trace.jsonl`，供 SWE-bench 失败根因分析直接消费。
设 `AITESTER_TRACE_DIR=`（空串）显式关闭。

#### 5.21.11 venv 按仓库复用（4.3）
`src/agents/executor_repo.py` 的 `RepoExecutor` 新增 `venv_reuse_by_repo=True`
参数：同一仓库的多个 commit 共享一个仓库级 venv
（`<env_root>/<repo>/_shared_venv/`），**依赖指纹只决定是否重装依赖**
（requirements / pyproject / setup.py 的 SHA256 变更时重建依赖）。
editable 源码绑定则是跨 commit 共享的可变状态：`pip install -e` 写入的是安装时
源码目录的绝对路径（`.pth` / `__editable__` finder），**不会**随 checkout 切换到
目标 commit 源码（F10，2026-10-19 第三方审查：旧表述"源码切换不触发重装、`.pth`
会跟随 checkout"是错误前提，A→B→A 场景会导入 B 的源码）。现行口径：共享 venv
目录下的 `.venv_editable_commit` marker 记录当前绑定 commit，`RepoExecutor` 在
仓库级 venv 锁内校验，仅当 marker ≠ 目标 commit 时重跑一次 `pip install -e .`
重指向并刷新 marker；同 commit 缓存命中零额外安装（性能不变）。
大幅减少 SWE-bench 同一 repo 多 commit 场景的 venv 重建开销（10-20 倍）。
`_dep_fingerprint(repo_dir)` 计算依赖指纹；`_repo_venv_dir(repo_url, repo_dir)`
解析共享 venv 路径。`venv_reuse_by_repo=False`（默认）保持 per-commit 独立 venv。

```bash
# 启用 venv 按仓库复用（需配合 REPO_LEVEL_EXECUTION + SWE_REPO_VENV_ISOLATION）
REPO_LEVEL_EXECUTION=true SWE_REPO_VENV_ISOLATION=true \
SWE_REPO_VENV_REUSE_BY_REPO=true \
  python experiments/run_benchmark.py --dataset swe_bench --task-limit 20 --baselines aitester
```

`SWE_REPO_VENV_REUSE_BY_REPO` 经 `experiments/run_benchmark.py` 消费（F10 补齐接线，
示例开关真实可达；此前全仓无消费点）。

### 5.22 前沿推荐批次（2026-09-28：gap_report P0/P1/P2 缺口 G1–G8 + 2026-09-29 审查优化轮，默认关闭）

#### 5.22.1 P0 运行时探针（`RUNTIME_PROBE_ENABLE`，默认关）
`src/agents/runtime_probe.py`：被测代码抛异常时刻直接读 `exc.__traceback__`
帧链采集精确失败时刻帧栈（零 trace 开销，替代历史 `sys.settrace` exception
事件方案——函数体异常时 exception 事件不向被调帧传播，实测 frames 恒空，
探针自引入以来从未真正生效）。同步修复单字符变量误过滤（x/y/z 断言失败时刻
最关键的观测变量不再被当"循环变量噪声"过滤）、行号错误（已退出帧
`f_lineno` 停在函数体末尾，改用 `tb_lineno`）、模块过滤永不匹配（probe 文件
命名 `"{target_module}_probe.py"` 与历史过滤条件 `"{target_module}.py"` 子串
不匹配，指定 target_module 时帧被全部丢弃）、子线程未处理异常泄漏
（顶层调用异常未被拦截 → "Exception in thread" 噪音）。`RUNTIME_PROBE_ENABLE=false`
（默认）时零差异。测试：`tests/test_runtime_probe.py`（全量通过 / 0 失败 /
0 告警，`-W error::ResourceWarning` 口径；用例数见 [BASELINE.yaml](BASELINE.yaml)）。

#### 5.22.2 G2 风险分级人工回路（`RISK_APPROVAL_ENABLE`，默认关）
`src/graph/risk_approval.py`：三因子加权打分（置信度 0.4 + 补丁影响面 0.4 +
预算占比 0.2）→ low/medium/high 分级 → auto_merge / human_confirm / force_review
审批动作；阈值可配（`RISK_THRESHOLD_MEDIUM=0.35` / `RISK_THRESHOLD_HIGH=0.65`），
权重可配（`RISK_WEIGHT_CONFIDENCE` / `RISK_WEIGHT_IMPACT` / `RISK_WEIGHT_BUDGET`）；
`experiments/run_benchmark.py` 结果行新增 `risk_summary` 字段（默认关时占位
`enabled=False`，键集合同构，不改变历史实验口径）。测试：
`tests/test_risk_approval_matrix.py`。

#### 5.22.3 G3 内核级沙箱（`KERNEL_SANDBOX_ENABLE`，默认关）
`src/agents/kernel_sandbox.py`：macOS Seatbelt（`sandbox-exec`）/ Linux
Landlock（`bwrap`）双后端；平台不支持时 fail-closed 拒绝执行（不静默降级到
无隔离本地，与 Docker 不可用同口径）。本地执行链路接入（`src/agents/executor.py`
`_kernel_sandbox_executable` / `_kernel_sandbox_obs`）。测试：
`tests/test_kernel_sandbox.py`。

#### 5.22.4 G4 AgentTelemetry 故障检测基准（`AGENT_TELEMETRY_ENABLE`，默认关）
`src/observability/agent_telemetry.py`：10 类内置失败模式正则匹配（零 LLM
成本，纯观测层），输出 Markdown 报告供实验分析消费。

#### 5.22.5 G5 无测试场景执行无关验证（`TESTLESS_VALIDATION_ENABLE`，默认关）
`src/tools/testless_validation.py`：四层独立可开关（AST 符号守卫 / mypy 静态检查 /
命名契约回归 / 导入冒烟），任一层失败整体 fail（保守 fail-closed 口径），与 G7
"有测试"场景缺陷有效性判定互补。

#### 5.22.6 G6 多智能体辩论收敛（`EXPERT_POOL_DEBATE_ENABLE`，默认关）
`src/graph/expert_pool.py` 新增 `debate_round()` 方法：top-K（默认 2，
`EXPERT_POOL_DEBATE_TOP_K` [2,4]）候选辩论收敛产出一个 `debate_revise` 修订
候选（需配合 `EXPERT_POOL_ENABLE=true`）；LLM 失败时保守降级回原 verified
列表（不阻断主链路）。

#### 5.22.7 G7 缺陷报告生成（`ErrorReport.oracle_stats`）
`src/reports/generator.py` 的 `ErrorReport` 新增 `oracle_stats` 字段 +
`with_oracle_stats()` 方法：`total_oracles > 0` 时才渲染"预言有效性（Oracle
增强，G7）"章节。

#### 5.22.8 G8 全链路 SWE-bench Pro 复测
`experiments/run_full_stack_swe_bench_pro.py`（一键七开关：
`RUNTIME_PROBE_ENABLE` / `STRATEGY_BANK_ENABLE` / `EXPERT_POOL_ENABLE` /
`CROSS_FILE_ENABLE` / `CROSS_FILE_BIDIRECTIONAL` / `REPO_LEVEL_EXECUTION` /
`SWE_REPO_VENV_ISOLATION`）+ `scripts/gates/check_swe_bench_pro_ready.py`
（数据前置门禁：JSONL 存在性 + `instance_code` / `test_patch` /
`FAIL_TO_PASS` / `base_commit` 齐备校验，缺失时阻断 `exit 1`）+
`experiments/summarize_full_stack.py`（ON/OFF 对照分析：成功率 / 错误分桶
`assertion` / `runtime` / `import_error` / `syntax` / `unknown` / `other` +
保守 verdict，ON 组全零时"无正向信息量"不强行宣称正向）。测试：
`tests/test_g8_g2_g4_g5_g6_g7_g1.py`。

#### 5.22.9 G1 Tree-sitter 精确 AST 后端（可选依赖）
`src/tools/tree_sitter_backend.py`：实现 `LanguageBackend` 4 个核心方法
（精确 AST 口径，误报更少）；`tree_sitter` 为可选依赖，缺时透明降级回
词法层，不阻断 Python 主路径；`pyproject.toml` mypy 配置已声明
`tree_sitter` / `tree_sitter_typescript` ignore_missing_imports。

#### 5.22.10 文档一致性 P2
新增 `docs/dependency_exemptions.md`（chromadb 1.5.9 命中 5 条已知漏洞
PYSEC-2026-311 / PYSEC-2026-3813 / PYSEC-2026-3814 / PYSEC-2026-3815 的
豁免登记表：依赖 / 版本 / 漏洞 ID / 豁免原因 / 复审触发条件 / 复审期限）+
`scripts/gates/check_dependency_exemptions.py`（CI 门禁：`--ignore-vuln` 列表未
在登记表留痕时 `exit 1` 阻断合并）+ `scripts/gates/check_docs_history_drift.py`
（warning-only：检测 `docs/history/*.md` 基线数字漂移超阈值时提示归档，
非阻断门禁）+ `CONTRIBUTING.md` "依赖豁免登记"章节。全量测试通过 / ruff 0 告警 /
mypy 0 错误（新增 5 源文件：risk_approval / agent_telemetry / kernel_sandbox /
testless_validation / tree_sitter_backend；当前数字见 [BASELINE.yaml](BASELINE.yaml)）。


### 6. 标准数据集集成（新增）
通过 `src/datasets/` 子包（`dataset_loader.py` + `synthetic_dataset.py`）支持多种数据集：

```python
from src.datasets import SWEBenchDataset, load_dataset
from src.datasets import SyntheticDataset

# 加载内置示例数据集（无需下载，3 个预定义 bug 任务）
dataset = load_dataset("examples")

# 加载 SWE-bench（需先下载数据）
dataset = SWEBenchDataset(subset="lite")  # 500 个任务
SWEBenchDataset.download_from_huggingface(subset="mini")

# 生成合成数据集（本地生成，无需外部数据）
dataset = SyntheticDataset(task_count=50, seed=42)
```

## 实验复现

### 环境要求
- Python 3.12+（锁定依赖 scipy 要求 ≥3.12）
- MySQL 5.7/8.0（可选，用于持久化实验数据）
- LLM API Key（如 OpenAI、DeepSeek 等）

### 复现步骤
```bash
# 1. 克隆仓库
git clone <repository-url>
cd AITester

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key 等信息

# 4. 初始化数据库（可选）
python init_db.py

# 5. 运行基准测试（内置示例数据集，三种基线对比）
python experiments/run_benchmark.py --dataset examples --baselines aitester,plain_llm,single_agent

# 6. 限制任务数量（快速验证）
python experiments/run_benchmark.py --dataset examples --task-limit 2

# 7. 查看结果
ls experiments/results/
python experiments/visualize_results.py
```

### 运行 SWE-bench 基准（需下载数据）
```bash
# 方式一：从 HuggingFace 下载 lite 子集（约 500 任务）
python -c "from src.datasets import SWEBenchDataset; SWEBenchDataset.download_from_huggingface(subset='lite')"

# 方式二：手动下载后放入 ~/.cache/aitester/swe_bench/swe_bench_instances.jsonl

# 运行 benchmark
python experiments/run_benchmark.py --dataset swe_bench --subset lite --task-limit 10
```

### SWE-bench 加载质量校验与源码补充（P0）

官方 SWE-bench JSONL **不含被测源码字段**（只有 issue 文本 + 修复补丁），
直接跑基准时 LLM 看不到真实代码，结果只能验证流程、不能产生有效修复对比。
用以下两步排查/补全：

```bash
# 1. 校验加载质量（逐任务打印 instance_code/test_code 完整性 + 全量质量报告）
python main.py check-dataset swe_bench --subset lite

# 2. 提供源码补充文件（JSONL，按 instance_id 关联）：
#    {"instance_id": "r/r-1", "instance_code": "def f(): ...", "test_code": "def test_f(): ..."}
#    可通过 git checkout <base_commit> 导出目标文件内容生成
SWE_BENCH_ENRICHMENT=./swe_bench_enrichment.jsonl \
  python experiments/run_benchmark.py --dataset swe_bench --task-limit 10
```

目标函数定位：加载器会从官方 `patch` 的 hunk 头自动提取目标函数名
（`metadata["suggested_function"]`，本地缓存 225 任务实测提取率 96%），
benchmark 用它初始化 `target_function`，驱动 Planner/Generator/Debugger
的 **AST 聚焦截取**——大源文件不再"头尾各半"硬截断，而是保留
import + 目标函数 + 其直接调用的辅助函数（见 `src/tools/code_context.py`）。

### 结果文件说明

基准测试结果保存在 `experiments/results/` 目录下，格式为 JSON：
```
experiments/results/benchmark_<dataset>_<timestamp>.json  # 例：benchmark_examples_20260814_120000.json、benchmark_synthetic_20260814_120000.json
```
该目录已加入 `.gitignore`，不会提交到版本库。

---

## 合成数据集与统计检验

### 合成数据集
AITester 内置了 `SyntheticDataset`，可在不依赖 SWE-bench/Defects4J 的情况下生成任意规模的缺陷任务：
- 10 种预定义 bug 模式（除零、边界条件、逻辑错误等）
- 通过 `--task-count` 控制任务数量（建议 ≥ 50 以满足发表要求）
- 固定 seed 保证结果可复现

### 统计显著性检验
`visualize_results.py` 自动输出：
- **配对 t 检验**：比较基线间通过率的统计显著性
- **Mann-Whitney U 检验**：非参数检验作为补充
- **Cohen's d**：量化效应量大小
- **p 值热力图**：直观展示显著性差异

输出文件：
- `（工件已清除）`
- `（工件已清除）`

---

## 执行隔离与依赖管理（P1）

本地执行默认跑在系统 Python：被测代码 import 的第三方库缺失时测试直接失败，
且无法区分"代码 bug"与"环境缺依赖"，不同任务的依赖还会互相冲突。
开启 venv 沙箱后，每个任务在临时目录 + 按依赖组合缓存的隔离 venv 中执行，
`PYTHONPATH` 仅指向沙箱目录：

```bash
# 隔离 venv 执行（缺失依赖只会被检测记录，测试结果仍正常产出）
EXECUTOR_USE_VENV=true python experiments/run_benchmark.py --dataset swe_bench --task-limit 10

# 执行前自动 pip install 缺失依赖（只装入 venv，不污染系统环境）
EXECUTOR_USE_VENV=true EXECUTOR_AUTO_INSTALL_DEPS=true \
  python experiments/run_benchmark.py --dataset swe_bench --task-limit 10
```

- venv 按"缺失包组合"做磁盘缓存（`~/.cache/aitester/venvs/`），相同依赖的任务复用；
- 缺失依赖会写入结果的 `error_info.missing_dependencies`，由错误分类器归为
  独立的 `import_error` 类别（区别于代码写错语法的 `syntax`）；
- 依赖安装失败时直接提前返回 `dependency_install_failed`，避免测试结果误导分析。

## RAG 检索增强与质量指标（P1）

RAG 默认关闭（`ENABLE_RAG=false`）。开启后 Generator/Debugger 会检索
相似历史案例；检索库持久化到 `rag_data/`（`RAG_PERSIST_PATH` 可配），
**跨实验运行可复用**，TTL 默认 7 天（`RAG_TTL_SECONDS`）：

```bash
# 显式开启 RAG 跑消融实验（检索库跨次运行累积）
python experiments/run_benchmark.py --dataset synthetic --enable-rag

# 查看 RAG 检索质量指标（结果 JSON 的 results.<baseline>.rag_metrics：
# retrievals / hits / hit_rate / avg_max_similarity；JSON 为默认输出，无需开关）
python experiments/run_benchmark.py --dataset synthetic --enable-rag
```

单独评估检索库质量（Hit Rate@k / MRR，针对已知标注查询）：

```python
from src.rag.retriever import TestCaseRetriever

retriever = TestCaseRetriever(persist_path="rag_data")
metrics = retriever.evaluate_retrieval(
    [{"query": "def add(a, b): ...", "expected_id": "<入库时的 doc_id>"}],
    top_k=5,
)
# → {"num_queries": 1, "hits": 1, "hit_rate": 1.0, "mrr": 1.0}
```

## 效率指标与基线对比排查（P0）

每次基准运行自动记录 token 消耗（结果 JSON 的 `results.<baseline>.token_metrics`
与逐任务 `token_usage`），用于"完整系统 vs Plain LLM 性价比"对比。
若发现基线反超，用对比工具定位差异环节：

```bash
# 1. 双基线跑一遍并落盘环节级产物（测试计划/生成代码/诊断/补丁）
python experiments/run_benchmark.py --dataset synthetic \
    --baselines aitester,plain_llm --save-state

# 2. 找出"plain_llm 成功但 aitester 失败"的任务，逐环节对比 + 输出 Markdown 报告
python experiments/compare_failures.py \
    --results experiments/results/benchmark_synthetic_<ts>.json \
    --raw-dir experiments/results/raw --max-tasks 5 \
    --report experiments/results/failure_analysis.md
```

报告会对每个翻转任务给出"疑似环节"提示（Planner 噪声 / Debugger 未收敛 /
环境依赖失败），并汇总 token 对比。

---

## Docker 一键复现

使用 Docker 可以完全隔离执行环境，避免本地依赖冲突。

```bash
# 构建镜像（首次约需 5 分钟，取决于网络速度）
docker build -t aitester:latest .

# 运行 benchmark
# LLM 密钥随 $(pwd) 的 .env.local 一并挂载进容器，无需 -e 传递（旧 OPENAI_API_KEY 变量已废弃）
docker run --rm \
  -v $(pwd):/workspace \
  aitester:latest \
  python experiments/run_benchmark.py --dataset examples --task-limit 1

# 运行单个文件测试
docker run --rm \
  -v $(pwd):/workspace \
  aitester:latest \
  python main.py run examples/calculator.py
```

## 单元测试

```bash
# 运行所有测试（全量用例数以 [BASELINE.yaml](BASELINE.yaml) `tests` 节为准；缺可选依赖时自动 skip 降级）
.venv/bin/python -m pytest tests/ -v

# 运行测试并生成覆盖率报告
.venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing

# 运行指定模块测试
.venv/bin/python -m pytest tests/test_dataset_loader.py -v
```

**测试覆盖模块**（测试文件数与用例数以 [BASELINE.yaml](BASELINE.yaml) `tests` 节为准，此处不硬编码会过期的数字）：

| 测试文件 | 测试函数数 | 覆盖范围 |
|---------|-------|---------|
| `test_api_manager.py` | 79 | API 管理器（轮询/加权随机/健康感知策略、健康线程开关、失败阈值配置接线、4.1 熔断冷却期状态机与路由过滤、1.5 冷却期边界 3 用例、4.1 脱敏接线 2 用例） |
| `test_api_circuit_breaker.py` | 16 | 4.4/0.6 熔断器指数退避（`API_CIRCUIT_BACKOFF` 开/关双路径）+ Prometheus 导出（`API_PROMETHEUS_EXPORT` 默认空串） |
| `test_api_manager_extended.py` | 74 | API 管理器扩展路径（健康恢复、限流标记、4.2 半开探测 TestHalfOpenProbe 12 用例） |
| `test_base_agent.py` | 40 | JSON 提取、代码块提取、客户端复用、AST 智能截取 |
| `test_base_agent_extended.py` | 46 | 指数退避重试、LLM 缓存、LLM 客户端复用 |
| `test_cli_app.py` | 36 | CLI 命令（list-examples/--version/参数校验/parallel/json 边界 + 1.4 超时贯通/并发容错/check-dataset 边界/glob 并发 + 4.4 clean-venv-cache 4 用例 + 5.1 并发中断/信号处理 3 用例） |
| `test_cli_output.py` | 10 | CLI 输出层回归（colorize TTY 双分支、success/error/warning/info 图标与 stdout/stderr 路由、print_rich_table 空列表/缺键兜底/coverage=0.0 不被误判 N/A，O-01 批次） |
| `test_cli_parallel.py` | 10 | 并发派发器 `_dispatch_parallel_tasks` 与 `run` 并发分支回归（rich/无 rich 双路径、逐任务容错、CI 门控 exit 1）（0.1） |
| `test_cli_run.py` | 6 | run 命令编排（超时/覆盖率阈值透传） |
| `test_cli_console_output.py` | 8 | run 非 JSON 控制台摘要（成功/失败/诊断/建议）+ _dispatch_concurrent rich/降级/JSON 静默分支（0.1） |
| `test_code_analyzer.py` | 17 | AST 解析、圈复杂度、代码替换 |
| `test_code_context.py` | 18 | AST 智能截取（P0 大文件上下文） |
| `test_complex_logic.py` | 12 | 复杂业务逻辑（邮箱验证等） |
| `test_config_generator.py` | 26 | LLM 配置生成器模板 |
| `test_config_manager.py` | 35 | 配置管理器（LLM 配置增删，含 P0 写盘前校验：拒含换行/`#` 的变量值注入，5 用例） |
| `test_config.py` | 15 | config.py 默认值与容错解析 |
| `test_core_modules.py` | 19 | 核心模块冒烟（BenchmarkTask / InMemoryDataset / Planner / Executor / DatasetLoader 多类） |
| `test_cost_aware_routing.py` | 13 | 成本感知路由与昂贵 provider 成本告警（3.4 + 3.2 阈值可配 4 用例） |
| `test_credential_scrub.py` | 5 | 2026-09-26 新增：凭证剔除 P0 补强回归（编号变体 `OPENAI_(API_KEY\|BASE_URL)_\d+` / provider 中间变量 / 高编号边界 / 入参不可变 5 用例） |
| `test_dataset_loader.py` | 76 | 数据集加载器（InMemory/SWEBench，O(1) `get_task_by_id` 索引） |
| `test_dataset_loader_extended.py` | 59 | 数据集加载扩展路径（raw 加载/字段校验） |
| `test_dataset_validation.py` | 16 | SWE-bench 加载质量校验与源码补充（P0）+ tasks_missing_source（2.1） |
| `test_debugger.py` | 38 | 错误诊断、RAG 注入、分类透传 |
| `test_contamination_check.py` | 15 | 2.1 数据污染检测（token 提取/Jaccard 重叠度/分级/detect 扫描/渲染章节） |
| `test_contamination_multidim.py` | 25 | 2.1 多维污染检测（结构级 AST 骨架 LCS + 语义级词袋余弦三维相似度 / 综合风险等级 / detect 全流程 / 抗污染基准注册表） |
| `test_dependency.py` | 43 | 依赖检测与 venv 管理（P1）+ 4.4 缓存监控（命中率统计/列表/清理，8 用例） |
| `test_dependency_edge_cases.py` | 18 | 依赖检测边界分支（标准库回退/find_spec 异常/venv 创建超时/OSError 静默降级，0.1 新增） |
| `test_error_classifier.py` | 89 | 十七类错误分类与修复策略映射（P2 细化 + 1.2 残余 + 1.1 状态细化 + 5.2 持续细化 + P0 4.1 子类 + 2.2 批次 `PATCH_SYNTAX_INVALID`：refine_failure_category / test_seventeen_categories_total 1 用例） |
| `test_error_classifier_new_categories.py` | 16 | 5.2 新增两错误类别判定（`EXECUTION_TRACE_MISSING` / `MULTI_CANDIDATE_ALL_REJECTED`，判定优先级 / 修复策略描述 / 从 final_state 接线） |
| `test_exceptions.py` | 33 | 自定义异常类与装饰器 |
| `test_executor.py` | 41 | 覆盖率解析、失败用例解析 |
| `test_executor_docker.py` | 11 | 4.3 Docker 执行模式（不可用诊断/模式开关/docker 优先于 venv/子进程环境凭证剔除 + TestDockerExecutionFlow 容器内执行链路 6 用例 + 沙箱清理兜底） |
| `test_executor_sandbox.py` | 7 | 沙箱执行路径与依赖安装（P1，含 install 失败短路 / 目标文件缺失边界） |
| `test_executor_repo.py` | 17 | P0 仓库级执行器 RepoExecutor（setup 缓存 / verify pass/fail / base_not_failing / test_patch_apply_failed / 基线恢复 / venv 隔离 / LLM 补丁助手 / git diff 可应用性） |
| `test_experiments_analysis.py` | 43 | 实验结果分析（排名/统计）+ 5.1 统计检验边界 5 用例（样本量 <3 / 部分配对缺失 / 单基线 / 脏数据） |
| `test_experiments_scripts.py` | 43 | visualize 结果选择 / 标准化实验返回键 / benchmark 并行度回归（0.1）+ 4.3 analyze_results 纯函数 + 2.3 RAG 自动汇总 + 1.1/1.2 修复收敛与质量代理指标 + 1.2 测试异味检测 + 1.3 修复收敛曲线 + 4.4 依赖缓存命中统计 + 1.2 收敛失败模式归因 / 1.3 边界用例覆盖 / 1.3 变异得分 / 3.2 执行轨迹汇总（14 用例） |
| `test_generator.py` | 27 | parametrize 校验、import 修正、LLM 调用 + 3.4 断言增强（TestAssertionAugmentation：AST 提取现有 assert，默认关，9 用例） |
| `test_llm_file_cache.py` | 8 | LLM 文件缓存命中/失效 + 温度键不互命中 + system_prompt 参与缓存键（0.9 深度审查回归） |
| `test_logging_utils.py` | 38 | 日志脱敏正则（sk- 前缀/带点号分段/无前缀长 hex·base64 三类形态，0.1 脱敏扩展回归）+ 5.1 脱敏边界 5 用例（格式化失败/exc_info 堆栈脱敏/嵌套 dict 口径锁定/幂等/mask 异常回退）+ 2026-09-26 redact_dict 字符串入参 2 用例（str 入参脱敏后包 `{"value":...}` 契约 + 其他标量回空 dict） |
| `test_mysql_client.py` | 13 | MySQL 客户端单例/事务/连接池参数 |
| `test_multi_candidate.py` | 33 | 多候选补丁生成与静态/执行验证筛选（3.1，boundary_shift 用例随 2026-09-26 变异体定位键升级同步更新） |
| `test_packaging.py` | 3 | 打包完整性（子包 __init__ 齐全） |
| `test_patch_applier.py` | 39 | 补丁应用（完整文件/单函数模式）+ 多函数补丁排序顺序（0.9 回归） |
| `test_planner.py` | 5 | PlannerAgent 规划逻辑序列化 |
| `test_prompts_templates.py` | 14 | 三个 system prompt 常量结构契约（关键指令段/错误类别/JSON 输出格式，0.1） |
| `test_rag_metrics.py` | 5 | RAG 检索质量指标 Hit Rate/MRR（P1） |
| `test_rag_retriever.py` | 31 | RAG 检索器增删查清与持久化 |
| `test_report_generator.py` | 50 | 错误报告生成器（含十七类分类分支；2026-09-26 `_parse_failed_cases` pytest 短输出模式匹配 2 用例：短格式行内错误后缀 + 详细格式异常类名行） |
| `test_run_benchmark.py` | 10 | benchmark 结果构造与异常路径回归（0.1 去重重构 + 2.1 patch 字段键集合同构护栏） |
| `test_swe_bench_source_export.py` | 13 | SWE-bench 源码导出脚本（patch 目标文件提取 / enrichment 落盘 / dry-run，2.1） |
| `test_state.py` | 8 | AITesterState 单一构造点工厂（create_initial_state 键集守护 / module_name 推导 / 可变容器隔离，深度重构批次；2026-09-26 补 `repo_verification` 字段声明） |
| `test_viz_significance.py` | 6 | 统计显著性收敛（visualize_results 复用 statistical_analysis 配对原语 / NaN 占位 / 原语引用锁定，深度重构批次） |
| `test_string_utils.py` | 10 | 字符串工具 |
| `test_synthetic_dataset.py` | 5 | 合成数据集生成与确定性验证 |
| `test_token_usage.py` | 9 | token 消耗统计（P0 效率指标） |
| `test_trace_observability.py` | 12 | 结构化 JSONL 追踪层（4.1） |
| `test_venv_cache_monitoring.py` | 11 | 4.4 venv 缓存容量监控（`get_venv_cache_size_mb` / `check_venv_cache_size` 5GB 阈值告警 / 统计文件路径动态化 / 命中率 / 清理） |
| `test_workflow.py` | 38 | 工作流图构建与路由 + 3.5 跨文件修复（CROSS_FILE_ENABLE 启用/禁用路径，2 用例）+ 3.2 执行反馈轨迹（TestExecutionTrace 3 用例：首轮 / 二轮 delta / 缺键容错）+ 2026-09-26 generator LLM 失败降级回归 1 用例 |
| `test_workflow_extended.py` | 44 | 工作流扩展路径（RAG 初始化单例、planner 默认计划去重等）+ 2026-09-26 早期迭代诊断关键词路由 regenerate 回归 1 用例 |
| `test_cross_file.py` | 45 | 3.5 跨文件修复（AST 依赖分析 / 协调器-提议者 / 多文件补丁应用 / 降级单文件 / 序列化 / 二期多入口依赖 / 拓扑序应用 / 修复计划缓存；2026-09-26 CF-3 修复新增 source_files 每模块自有源码 3 用例：per-module / fallback / legacy None 行为） |
| `test_cross_file_bidirectional.py` | 16 | 2.2 跨文件双向依赖图（单向/双向口径 / `CROSS_FILE_BIDIRECTIONAL` 环境变量开关 / 符号定义行定位） |
| `test_analyze_failures.py` | 20 | 5.3 失败根因分类（LLM/依赖/框架三大根因）+ 案例知识库 + CLI --knowledge-base |
| `test_weak_coverage_modules.py` | 16 | 5.1 弱覆盖模块补强（cli_output print_rich_table 边界 / error_classifier 新分类路径 / executor_runtime 清理与重试异常分支） |
| `test_weak_coverage_modules2.py` | 10 | 5.1 弱覆盖模块补强第二轮（config_generator main 入口 / prompts_templates 常量结构 / synthetic_dataset 边界生成） |
| `test_weak_coverage_modules3.py` | 13 | 5.1 弱覆盖模块补强第三轮（trace 写盘失败降级 / analysis 统计检验边界 / error_classifier 分支 / cli_output 非 rich 降级 / prompts __main__） |
| `test_smell_detection_v2.py` | 25 | 1.1 异味检测补强（Eager Test / Lack of Cohesion 触发与不触发 + 语法错误兜底）+ 1.2 变异测试生成器（TestMutationGenerator 9 用例，e2e 杀死判定口径 2026-09-26 精确化后 import 名修复）+ 1.3 变异得分（mutation_score_from_details） |
| `test_failure_kb.py` | 14 | 5.3 失败案例知识库 + 跨批次失败模式对比（failure_knowledge_base 结构化 JSON / cross_batch_comparison 批次趋势 / 三大失败根因） |
| `test_defects4j_smoke.py` | 5 | 3.4 Defects4J-Python 加载器冒烟验证（无数据目录优雅降级 / 完整目录解析 / 字段完整性） |
| `test_g8_g2_g4_g5_g6_g7_g1.py` | 25 | G1–G8 前沿推荐批次缺口单元测试（G2 risk_approval 三因子打分 / G4 agent_telemetry 失败模式匹配 / G5 testless_validation 四层验证 / G6 expert_pool 辩论收敛 / G7 ErrorReport Oracle 章节 / G8 前置数据检查 / G1 tree_sitter 后端降级） |
| `test_kernel_sandbox.py` | 9 | G3 内核级沙箱（macOS Seatbelt / Linux Landlock 双后端 / 平台不支持 fail-closed / 本地执行链路接入） |
| `test_experiments_ab_scaffolds.py` | 12 | A/B 对照聚合 + 全链路汇总 verdict + 七开关注入（`experiments/summarize_full_stack.py`） |
| `test_runtime_probe.py` | 3 | P0 运行时探针回归（模块过滤保留口径 / 模块过滤丢弃口径 / tb_lineno 行号口径，2026-09-29 修复核心缺陷后新增） |

## 配置说明

所有配置项统一在 [config.py](config.py) 中管理，通过 `.env` 和 `.env.local` 文件注入：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `LLM_N_API_KEY` | LLM API 密钥（支持多配置，见 `config.local.example`）| 必填 |
| `LLM_N_BASE_URL` | LLM Base URL | - |
| `LLM_N_MODEL_NAME` | LLM 模型名称 | deepseek-flash |
| `MODEL_NAME` | 向后兼容：默认 LLM 模型名称 | deepseek-flash |
| `MAX_ITERATIONS` | 最大修复迭代次数 | 3 |
| `COVERAGE_THRESHOLD` | 覆盖率阈值 | 80.0 |
| `CROSS_FILE_ENABLE` | 3.5 跨文件修复开关（协调器-提议者架构，默认关） | false |
| `CROSS_FILE_MAX_MODULES` | 3.5 跨文件依赖分析最大模块数 | 5 |
| `CROSS_FILE_BIDIRECTIONAL` | 2.2 跨文件双向依赖图开关（默认 false 保持单入口视角；启用时额外收集"其他模块→entry"反向依赖边，使修复计划能同步更新调用方模块；需配合 CROSS_FILE_ENABLE=true 生效） | false |
| `ADVERSARIAL_DEBUGGING_ENABLE` | 3.1 对抗性推理开关（默认关；启用后 Debugger 生成补丁前注入 2-3 个"击穿当前实现"的对抗性意图假设 + 生成针对性测试，生成后独立批评者评估，被击穿则重生成一次补丁；观测层，不影响主修复路径） | false |
| `ASSERTION_AUGMENT_ENABLE` | 3.4 断言增强策略（AST 提取现有 assert 注入 prompt，默认关） | false |

| `EXECUTION_TIMEOUT` | pytest 执行超时（秒） | 30 |
| `LLM_TIMEOUT` | 单次 LLM 调用超时（秒） | 60 |
| `LLM_JSON_MODE` | JSON Output（DeepSeek 官方，七处 JSON 契约调用点绑定 `response_format=json_object`；**2026-10-14 起默认 on**，设 off 恢复历史逐字节口径；ADR-0031） | on |
| `LLM_RETRY_WAIT` | LLM 重试等待时间（秒） | 30 |
| `ENABLE_PLANNER` | 启用 Planner（消融开关） | true |
| `ENABLE_DEBUGGER` | 启用 Debugger 修复循环（消融开关） | true |
| `ENABLE_RAG` | 启用 RAG 检索增强 | false |
| `RAG_PERSIST_PATH` | RAG 持久化路径（空=内存模式，默认项目根 rag_data/） | rag_data |
| `RAG_COLLECTION_NAME` | RAG ChromaDB 集合名 | aitester_cases |
| `RAG_TTL_SECONDS` | RAG 缓存 TTL（秒，持久化场景默认 7 天） | 604800 |
| `EXECUTOR_USE_VENV` | venv 沙箱隔离执行（依赖隔离，P1；**R10 起默认 true**，设 false 回退宿主环境直跑，仅调试用） | true |
| `FL_SPECTRAL_ENABLE` | O2 谱系故障定位（Ochiai Top-k，零 LLM 成本；**R8 起默认 true**，设 false 作消融对照组） | true |
| `FAULT_LOCALIZER_ENABLE` | 修复引擎第一阶段 RGFL 式 LLM 推理故障定位（局部化 → 合成 → 验证范式，2026-10-07 批次 I；结构化定位〔函数/行区间/置信度〕注入 Debugger prompt 并透出 `localization_hit_function` 指标；失败保守降级 None 不阻断修复；**默认 true**，设 false 退回纯谱系消融口径） | true |
| `SPEC_IR_ENABLE` | R7 SpecIR 可执行规约 IR（logic_analysis 解析 + 边界三元组 → pytest/Hypothesis oracle 编译，纯观测层） | false |
| `SPEC_REFINE_ENABLE` | R4 S1（2026-10-09）：逻辑驱动反例精化开关（`spec_refine.refine_spec_with_counterexample`——规约矛盾反例回灌 LLM **只修正契约（不改代码）** + SMT 复验预算化迭代（CEGIR）；LLM 回调可注入（测试 mock，零真实 LLM）；**默认关**，未接入主链路——调用点接入属后续批次） | false |
| `SPEC_REFINE_MAX_ROUNDS` | R4 S1：反例精化迭代上限（默认 2，下限 0 上限 5；越界值保守回退默认 2；非数字回退 2） | 2 |
| `FLAKY_CHECK_ENABLE` | R35/R31 flaky 门禁（失败轮重复执行一致性检测，flaky 时 test_passed 保守记 False，flaky fraction 入工件） | false |
| `FLAKY_REPEAT_COUNT` | flaky 门禁重复执行次数（默认 3；稳定性口径设 30） | 3 |
| `SWE_BENCH_P2P_GATE_ENABLE` | R46（2026-09-30 独立审查 P0）：SWE-bench 实例可解性前置门禁（**默认 true**——SWE-bench ProMax 实测 ~60% 未解出实例的测试本身有缺陷，开门禁后不可解实例记 `harness_invalid` 剔除，"0 解出"还原为"harness 无效"而非"系统无效"；设 false 消融对照） | true |
| `SWE_BENCH_P2P_GATE_THRESHOLD` | P2P 门禁阈值（基线 PASS_TO_PASS 通过率下限，默认 0.95） | 0.95 |
| `EXECUTOR_AUTO_INSTALL_DEPS` | 执行前自动 pip install 缺失依赖（P1；R59/S6 包名幻觉防护见 `PIP_PACKAGE_WHITELIST_ENABLE`） | false |
| `PIP_PACKAGE_WHITELIST_ENABLE` | R59（2026-09-30 独立审查 P0）/S6：pip 包名白名单守卫（true 时仅白名单内包名放行安装，PEP 503 大小写不敏感；白名单来源 `PIP_PACKAGE_WHITELIST` 逗号分隔或内置 ~40 常用包，未知名默认拒绝，堵 slopsquatting 供应链向量；**自 2026-10-09 审查修订 C-08 起默认 true**，显式设 false 退回历史放行口径） | true |
| `EXECUTOR_DEP_INSTALL_TIMEOUT` | 依赖安装超时（秒） | 120 |
| `AITESTER_VENV_CACHE_DIR` | 4.4 venv 缓存目录覆盖（默认 `~/.cache/aitester/venvs`；配合 `clean-venv-cache` 清理） | 未设 |
| `MYSQL_POOL_MIN_CACHED` | 连接池最小预留连接 | 5 |
| `MYSQL_POOL_MAX_CACHED` | 连接池最大空闲连接 | 10 |
| `MYSQL_POOL_MAX_CONNECTIONS` | 连接池最大连接总数 | 20 |
| `MYSQL_POOL_TIMEOUT` | 获取连接等待超时（秒） | 30 |
| `LLM_N_COST_WEIGHT` | 第 N 个 LLM 的相对成本倍数（3.4 成本感知路由；0.0=未配置，APIManager 回退 1.0 基准） | 1.0 |
| `SWE_BENCH_ENRICHMENT` | SWE-bench 源码补充 JSONL 路径（P0，可选） | 无 |
| `REPO_LEVEL_EXECUTION` | P0 仓库级验证：SWE-bench 任务路由到 RepoExecutor（clone + checkout + pip install -e 环境缓存 + gold test_patch 前后 FAIL_TO_PASS/PASS_TO_PASS 实测），默认关 | false |
| `SWE_REPO_SETUP_TIMEOUT` | 仓库级环境 setup 子进程超时（秒，clone + checkout + pip install -e） | 600 |
| `SWE_REPO_ENVS_DIR` | 仓库环境缓存根目录（(repo, commit) 分目录复用，默认 `~/.cache/aitester/repo_envs`） | 未设 |
| `SWE_REPO_VENV_ISOLATION` | P1 仓库级 venv 隔离（每 commit 旁建独立 venv，pip install -e 装入 venv，pytest 用 venv python；默认关保持已缓存 repo_envs 兼容） | false |
| `BENCHMARK_PARALLELISM` | 批量测试并行度（0=串行） | 0 |
| `TEMPERATURE` | LLM 采样温度 | 0.2 |

## 高级开关（默认全关，按需启用）

以下开关均以环境变量形式提供，默认值保持历史实验口径不变；启用是显式行为。

| 开关 | 默认 | 启用效果 | 关联章节 |
|------|------|---------|----------|
| `ENABLE_MULTI_CANDIDATE_PATCH` | false | 多候选补丁生成与验证筛选（3.1；W7 起 reproduce.sh 默认关闭——A/B 实测成功率 -2pp 且 token +256%；`--multi-candidate` 显式开启） | 5.1 |
| `AITESTER_TRACE_DIR` | 未设（no-op） | 结构化 JSONL 追踪层（4.1；`reproduce.sh` 默认启用至 `（工件已清除）`） | 5.2 |
| `ENABLE_MUTATION_SCORING` | false | 1.2 变异得分评估：benchmark 运行后对每任务"生成测试 vs 被测源码"计算 mutation_score（内置轻量变异生成器，每任务 ≤ `MUTATION_MAX_MUTANTS` 个变异体）；耗时显著增加，默认关闭保持历史口径 | 5.14 |
| `MUTATION_MAX_MUTANTS` | 10 | 1.2 每任务最多评估的变异体数量（需配合 `ENABLE_MUTATION_SCORING=true` 生效） | 5.14 |
| `EXECUTOR_USE_DOCKER` | false | 4.3 Docker 隔离执行（经 docker CLI 在容器内跑 pytest，镜像内置依赖；不可用时返回 `docker_unavailable` 诊断不降级本地） | 5.13 |
| `EXECUTOR_DOCKER_IMAGE` | aitester:latest | 4.3 Docker 执行使用的镜像名（对应仓库根 Dockerfile） | 5.13 |
| `CROSS_FILE_ENABLE` | false | 跨文件修复（协调器-提议者架构，3.5；`reproduce.sh --cross-file` 显式启用） | 5.8 |
| `REPO_LEVEL_EXECUTION` | false | P0 SWE-bench 仓库级验证：SWE-bench 任务路由到 RepoExecutor（clone + checkout + pip install -e 环境缓存 + gold test_patch 前后 FAIL_TO_PASS/PASS_TO_PASS 实测），默认关保持合成集/examples 口径不变 | 5.20 |
| `SWE_REPO_VENV_ISOLATION` | false | P1 仓库级 venv 隔离：每 commit 环境旁建独立 venv（pip install -e 装入 venv，pytest 用 venv python），解决跨 commit 全局 python 环境污染（实测 sqlfluff BaseSegment 方法在相邻 commit 不一致 → AttributeError，与 LLM 补丁无关） | 5.20 |
| `CROSS_FILE_BIDIRECTIONAL` | false | 2.2 跨文件双向依赖图（额外收集"其他模块→entry"反向依赖边，修复计划同步更新调用方；需配合 `CROSS_FILE_ENABLE=true` 生效，独立开关保证"跨文件启用 ≠ 双向启用"两级保守） | 5.8 |
| `ADVERSARIAL_DEBUGGING_ENABLE` | false | 3.1 对抗性推理（AdverIntent 式：生成补丁前注入 2-3 个对抗性意图假设 + 生成针对性测试，生成后独立批评者评估，被击穿则重生成一次；纯观测层，默认关保持历史口径） | 5.16 |
| `DETECTION_FIRST_ENABLE` | false | W3 检出优先协议（ADR-0015，"先红后绿"成功口径：首轮全绿 = 未检出缺陷，触发一次再生成强化测试；终态标注 red_then_green / all_green_unverified，评估层不得把 all_green_unverified 计为检出/修复成功） | 5.19.5 |
| `API_CIRCUIT_BACKOFF` | true | 4.4 API 熔断器指数退避开关（冷却期改按 `base * 2^open_count` 指数增长，彻底死掉的 provider 冷却期单调增长；`reproduce.sh` 显式透传，设 false 回退 4.2 固定冷却期口径便于对比实验） | 5.17 |
| `API_PROMETHEUS_EXPORT` | false | 4.4 Prometheus 指标导出开关（启用后 `APIManager.to_prometheus_text()` 输出 7 类指标供 Prometheus 抓取；纯旁路，不影响既有路由行为；`reproduce.sh` 显式透传） | 5.17 |
| `ASSERTION_AUGMENT_ENABLE` | false | 断言增强策略（AST 提取现有 assert，3.4） | 5.9 |
| `RUNTIME_PROBE_ENABLE` | false | P0 运行时探针：被测代码抛异常时刻采集 `exc.__traceback__` 帧链与局部变量快照（零 trace 开销，2026-09-29 修复核心缺陷后真正生效） | 5.22.1 |
| `KERNEL_SANDBOX_ENABLE` | false | G3 内核级沙箱：macOS Seatbelt（`sandbox-exec`）/ Linux Landlock（`bwrap`）双后端，平台不支持时 fail-closed 拒绝执行（与 Docker 不可用同口径，不静默降级到无隔离本地） | 5.22.3 |
| `AGENT_TELEMETRY_ENABLE` | false | G4 AgentTelemetry 故障检测基准：10 类内置失败模式正则匹配（零 LLM 成本，纯观测），输出 Markdown 报告供实验分析消费 | 5.22.4 |
| `TESTLESS_VALIDATION_ENABLE` | false | G5 无测试场景执行无关验证：四层独立可开关（AST 符号守卫 / mypy 静态检查 / 命名契约回归 / 导入冒烟），任一层失败整体 fail（保守 fail-closed 口径） | 5.22.5 |
| `EXPERT_POOL_DEBATE_ENABLE` | false | G6 多智能体辩论收敛：top-K 候选辩论收敛产出一个 `debate_revise` 修订候选（需配合 `EXPERT_POOL_ENABLE=true`；LLM 失败时保守降级回原 verified 列表，不阻断主链路） | 5.22.6 |
| `RISK_APPROVAL_ENABLE` | false | G2 风险分级人工回路：三因子（置信度 + 补丁影响面 + 预算占比）加权打分 → low/medium/high → auto_merge / human_confirm / force_review | 5.22.2 |

详见 [QUICKSTART.md](QUICKSTART.md) 与 [.env.example](.env.example)。

### 多 LLM 配置支持

系统支持配置多个 LLM Provider，实现 API Key 轮询和高可用：

```bash
# .env.local 配置示例
LLM_1_API_KEY=sk-key-1
LLM_1_BASE_URL=https://api.provider1.com/v1
LLM_1_MODEL_NAME=model-1

LLM_2_API_KEY=sk-key-2
LLM_2_BASE_URL=https://api.provider2.com/v1
LLM_2_MODEL_NAME=model-2
```

代码中使用：
```python
from config import LLM_CONFIGS, DEFAULT_LLM_CONFIG

# 获取所有配置
all_configs: list[LLMConfig] = LLM_CONFIGS
# 获取默认配置（第一个）
default_config: LLMConfig | None = DEFAULT_LLM_CONFIG
```

更多配置详情参见 [docs/api_reference.md](docs/api_reference.md) 和 [config.local.example](config.local.example)。

---

## CLI 命令参考

### `python main.py run` — 运行单个测试任务

```
python main.py run <target_file> [OPTIONS]

参数：
  target_file    被测 Python 文件路径（必须存在）

选项：
  --func, -f          指定被测函数名，不指定则测试全部函数
  --max-iterations    最大修复迭代次数，默认 3
  --coverage-threshold  覆盖率阈值百分比，默认 80.0
  --timeout           pytest 执行超时（秒），覆盖 EXECUTION_TIMEOUT 配置
  --json              以 JSON 格式输出结果（stdout 仅承载纯 JSON，日志/进度条走 stderr，便于管道给 jq）
```

> **退出码**：任一测试任务失败（含任务崩溃）时进程以 `1` 退出，全部通过以 `0` 退出，可在 CI/脚本中当作门控工具使用。

**示例：**
```bash
# 测试单个函数
python main.py run examples/calculator.py --func divide

# 指定最大迭代次数
python main.py run examples/buggy_library.py --func binary_search --max-iterations 5

# JSON 输出结果
python main.py run examples/string_utils.py --func is_palindrome --json
```

### `python experiments/run_benchmark.py` — 批量基准测试

```
python experiments/run_benchmark.py [OPTIONS]

选项：
  --dataset, -d       数据集名称（examples/synthetic/swe_bench/swe_rebench/defects4j_py）
  --subset, -s        数据子集（swe_bench_lite 等）
  --baselines, -b     基线方法列表，逗号分隔（默认：aitester,plain_llm,single_agent）
  --output-dir, -o    结果输出目录（默认：experiments/results）
  --verbose, -v       详细日志输出
  --task-limit, -n    限制运行任务数量
  --task-count, -c    合成数据集任务数量
  --parallel, -p      并行任务数（替代 BENCHMARK_PARALLELISM 环境变量）
  --timeout           全局执行超时（秒）
  --json              JSON 格式输出结果
  --enable-rag        显式开启 RAG 检索增强（P1 消融实验；默认沿用 config.ENABLE_RAG）
  --save-state        环节级状态落盘到 <output-dir>/raw/（P0 基线对比排查用）
```

> **2.1 数据污染检测**：SWE-bench 场景下，结果 JSON 的 `details[].patch`（系统生成补丁）与
> `details[].task_metadata.golden_patch`（官方黄金补丁）会自动送入污染检测。运行分析时可用
> `python experiments/analyze_results.py --golden-patches <json>` 显式传入黄金补丁映射（JSON
> 对象 `{task_id: patch_text}`）；分析报告自动渲染"数据污染检测（2.1）"章节（high/medium 任务
> 列表 + 重叠度分数 + 抗污染基准建议）。

**示例：**
```bash
# 快速验证（2 个任务，单基线）
python experiments/run_benchmark.py --dataset examples --task-limit 2 --baselines aitester

# 并行执行（4 线程，100 个合成任务）
python experiments/run_benchmark.py --dataset synthetic --task-count 100 \
    --baselines aitester,plain_llm,single_agent --parallel 4

# 仅运行 aitester 完整系统（JSON 为默认输出，无需 --json 开关）
python experiments/run_benchmark.py --dataset examples --baselines aitester

# 2.1 抗污染基准（SWE-rebench，需经 AITESTER_SWE_REBENCH_DATA 指向数据目录）
python experiments/run_benchmark.py --dataset swe_rebench --baselines aitester

# 4.3 Docker 隔离执行（需本机 docker + 镜像已构建；容器内零安装开销）
EXECUTOR_USE_DOCKER=true python experiments/run_benchmark.py --dataset examples --baselines aitester
```

### `python main.py list-examples` — 列出示例文件

```
python main.py list-examples
```

### `python main.py clean-venv-cache` — 清理依赖缓存（4.4）

```
python main.py clean-venv-cache [OPTIONS]

选项：
  --max-age-days N    删除 N 天前的 venv（None 表示不按年龄过滤）
  --max-size-mb N     删除超过 N MB 的 venv（None 表示不按大小过滤）
  --list-only, -l     仅列出缓存目录内容（含命中率统计），不删除
```

**示例：**
```bash
# 查看现有缓存与命中率
python main.py clean-venv-cache --list-only

# 删除 30 天前的 venv
python main.py clean-venv-cache --max-age-days 30

# 删除超过 512MB 的 venv
python main.py clean-venv-cache --max-size-mb 512
```

> 缓存目录默认 `~/.cache/aitester/venvs/`，可经 `AITESTER_VENV_CACHE_DIR` 环境变量覆盖（容器/CI 隔离场景指向挂载卷）。

## 数据集说明

| 数据集名称 | 数据来源 | 任务数 | 下载要求 |
|-----------|---------|-------|---------|
| `examples` | 内置示例（calculator/buggy_library/string_utils） | 3 | 无需下载 |
| `synthetic` / `synth` | 本地生成，支持自定义规模 | 可配置 | 无需下载 |
| `swe_bench` | HuggingFace SWE-bench | 500 (lite) | 需调用 download_from_huggingface() |
| `defects4j_python` | Defects4J-Python 数据集 | 可变 | 需手动下载 |
| `swe_rebench` | SWE-rebench 抗污染基准（2.1 数据污染风险应对，字段与 SWE-bench 同构） | 可变 | 需经 `load_dataset("swe_rebench", data_dir=...)` 指向 rebench 数据目录 |

更多细节请参考 [性能调优指南](docs/performance_guide.md)、[API 参考](docs/api_reference.md) 和 [使用示例](docs/usage_examples.md)。

## 技术栈

- **LLM 框架**: LangChain + LangGraph
- **数据库**: MySQL（pymysql 驱动）
- **向量数据库**: ChromaDB（RAG 模块）
- **测试框架**: pytest + pytest-cov
- **命令行**: Click
- **数据集**: SWE-bench / Defects4J-Python（通过 HuggingFace datasets 库加载）
- **可视化**: matplotlib + pandas

## 基准测试结果

### 内置示例数据集（examples，3 个任务）

| 任务 | 状态 | 覆盖率 | 迭代次数 | LLM 调用次数 |
|------|------|--------|----------|-------------|
| `calculator.py::divide` | ✅ PASS | 100% | 0 | 1 |
| `buggy_library.py::binary_search` | ✅ PASS | 100% | 1 | 2（含重试） |
| `string_utils.py::is_palindrome` | ✅ PASS | 75% | 0 | 1 |

**汇总**：成功率 **100%**，平均覆盖率 **91.7%**，平均耗时 **30.1s/任务**。

### 合成数据集实验（50个任务，3种基线对比）

> ⚠️ **数字已过期（2026-09-29 审查订正）**：以下快照使用旧 `success_rate` 口径，
> 审查复算确认约 65.9% 为"测试未检出缺陷"而非"修复成功"（假成功）。
> 新指标（`detection_rate` / `repair_rate` / `false_fix_rate`）已实现（`experiments/_m1_metrics.py`），
> 首次固定 seed 重跑批次产出后，本表将更新为真实数字。
> 历史快照存档于 `（工件已清除）`（未入库）。

> 某次 50 任务运行（3 种基线对比）的旧口径数据快照，仅用于演示多基线方法论，非当前版本性能承诺。

| 基线方法 | 成功率 (%) [旧口径] | 平均覆盖率 (%) | 平均迭代次数 | 平均耗时 (s) |
|---------|-----------|---------------|-------------|-------------|
| **AITester** | **88.0** | **97.8** | 0.64 | 45.33 |
| Plain LLM | 68.0 | 98.0 | 0.0 | 16.6 |
| Single Agent | 4.0 | 0.0 | 0.24 | 26.85 |

**关键发现**（旧口径，待新指标重跑后更新）：
- 旧 `success_rate` 口径下 AITester 高于 Plain LLM（88.0% vs 68.0%），但 2026-09-29 审查确认
  AITester 的 88% 中约 2/3 为假成功（测试在带缺陷代码上通过，缺陷未检出）
- Plain LLM 旧 `success_rate` 口径 100% 假成功（0/50 有效修复）
- 新三指标（`detection_rate` / `repair_rate` / `false_fix_rate`）已实现，
  待固定 seed 重跑批次（`AITESTER_CACHE_ISOLATE_MODEL=1` + `AITESTER_BASELINE_LOAD_BALANCE=0`）产出工件后统一刷新

详细结果参见 `（工件已清除）`（本地保留，不入库；仓库内 `experiments/results/` 仅跟踪占位说明，历史产物经 .gitignore 排除）

### SWE-bench Lite 实验（20个任务）

该批次实验受 API 限流影响，结果未归档到仓库；后续重跑数据以本地私有目录保存（不入库）。

**仓库级验证（P0/P1，2026-09-25）**：用 `RepoExecutor`（`REPO_LEVEL_EXECUTION=true`）
按 SWE-bench 官方口径（gold `test_patch` 前后 FAIL_TO_PASS/PASS_TO_PASS 实测）
验证 lite-20，结果见 `（工件已清除）` §7：

- 数据管道修复（`SWE_BENCH_ENRICHMENT` 注入真实源码）+ 执行环境修复
  （RepoExecutor 仓库级 clone + pip install -e + venv 隔离）+ 补丁管道修复
  （`git diff --no-index` 生成可应用 unified diff）后，SWE-bench 仍 0/20。
- P1 诊断（venv 隔离 + 修复管道后，单源任务 0/7）失败分类：
  5/7 `LLM_BREAKS_IMPORT`（LLM 重写目标文件破坏 sqlfluff 插件命名契约，
  如 `Rule_L027` 类名改坏 → 整个 import 链崩溃）+ 2/7 `EMPTY_LLM_PATCH`
  （LLM 未产出修复）。**管道与环境已全部修通，0/N 是 LLM 引擎修复质量
  边界**（免费档小模型对真实仓库级代码），非管道 / 非环境。
- 跨文件任务（13/20 多源）在引擎能力突破前无正向信息量（ON/OFF 都会
  0/N），跨文件收益验证需更强模型 + 仓库全量源码上下文重做。

论文定位：SWE-bench 0/N 写入"局限性讨论"章节（引擎修复质量边界），
主实验仍用合成数据集（旧 success_rate 口径 88% vs 60% vs 8%；
新 M1 三指标口径待固定 seed 重跑批次产出后统一刷新，见上方过期数字标注）。

### 关键修复记录

- `_validate_parametrize` 由 regex 改为 ast 解析，解决嵌套列表导致参数误判问题
- `_patch_applier_node` 增加安全守卫（非空、≥10% 长度、含函数定义）
- Generator 二次 parametrize 校验，避免 LLM 反复生成相同错误代码


## 常见问题

### Q: 运行时报 `ModuleNotFoundError`

**原因**：测试文件与模块不在同一目录，Python 无法找到被测模块。
**解决**：确保 `target_file` 路径正确，或检查 `module_name` 配置。

### Q: LLM 返回非 JSON 格式

**原因**：模型输出不符合预期格式。
**解决**：检查 `.env.local` 中的 `LLM_N_*` 配置（模型名、Base URL），确保 API Key 有效。

### Q: 覆盖率始终为 0%

**原因**：覆盖率统计文件未生成或路径错误。
**解决**：检查 `pytest-cov` 是否正确安装，确认 `--cov` 参数传递。

### Q: 合成数据集成功率低（< 10%）

**原因**：合成数据集 bug 模式较复杂，单轮修复可能不足以覆盖所有场景。
**解决**：
1. 增加 `MAX_ITERATIONS`（默认 3，可调至 5）
2. 启用 RAG 增强：`ENABLE_RAG=true`
3. 调整模型档位：配置更高能力的 DeepSeek 模型（`LLM_1_MODEL_NAME`，内置默认 `deepseek-flash`）

---

## 技术文档

- [算法设计文档](docs/algorithm_design.md)：核心算法形式化描述
- [失败案例分析](docs/failure_analysis.md)：失败率的根因分析与改进路线图（历史数据快照）
- [性能调优指南](docs/performance_guide.md)：并发执行、RAG 单例化、超时配置、性能剖析基准
- [API 参考文档](docs/api_reference.md)：模块接口说明（含 2026-09-29 审查优化轮：P0 运行时探针缺陷修复口径）
- [使用示例](docs/usage_examples.md)：编程接口与 CLI 用法
- [依赖豁免登记表](docs/dependency_exemptions.md)：pip-audit 漏洞豁免登记（依赖 / 版本 / 漏洞 ID / 豁免原因 / 复审触发条件 / 复审期限）
- [审查轮次记录](CHANGELOG.md)：第六至第十一轮审查与保守优化（P1/P2 缺陷修复 + 回归守卫；见 CHANGELOG「2026-09-26 全面审查与保守优化轮」批次条目；原 docs/review_* 文件已随 P1-9 文档治理删除）
- [高级开关说明](QUICKSTART.md)：结构化追踪 / 多候选补丁 / 成本感知路由 / G1–G8 新能力开关（默认全关，按需启用）
- [历史优化记录](docs/history/optimization_plan.md)：归档的历史轮次优化计划与报告（`docs/history/`，非当前维护文档）

---

## 贡献指南

欢迎贡献代码！请阅读 [贡献指南](CONTRIBUTING.md) 了解如何参与项目开发。

---

## 迭代优化记录

> 本节已归档至 [docs/history/README_iteration_log.md](docs/history/README_iteration_log.md)
> （P1-9：历史批次快照含过期基线数字，按"核心维护文档不硬编码数字"规则整节迁出；
> 当前状态见 [BASELINE.yaml](BASELINE.yaml)，批次脉络见 [CHANGELOG.md](CHANGELOG.md)）。

## 许可证

MIT License
