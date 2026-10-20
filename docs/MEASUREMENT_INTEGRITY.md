# 测量完整性：口径分叉的五种形态与修复方法论

最后更新：2026-10-20（**AB-13 轮：新增 §16——字段名里的单位不是实现约束，直到实现参与判定**：`emse_stats_report.py` 输出 `total_usd` / `usd_per_detection` / `$/task`，字段名把单位写死，实现里**没有一行读过 `currency`**；前置探针用一条 `qwen-long`（盘上真表登记 CNY 0.5 / 2.0）的合成行实测得 `total_usd=2.5`、`n_priced_rows=1` 并印在"总 $"列——**人民币被累加成美元且账面完全正常**（分母非空、单价非空、无任何不可计价披露）。同节另立两条：改口径撞上旧断言时**先裁决旧期望、改后必须仍测它声称的东西**（`test_zero_detection_no_division` 补 `currency` 后仍须加 `n_priced_rows == 1 and total_usd > 0`，否则分子为 0 时该例根本没走到除零守卫——§15"删掉守卫仍全绿有两种原因"出现在**测试夹具层**的同型问题）、**关掉一条尚未发生的通道必须同时锁"真批次不受影响"与"闸门不是空转"**（783 行单 USD 模型 ⇒ 入库读数 0 行改变，但同一个 0 也是"闸门可能从没执行过"的嫌疑，故覆盖面下界与 CNY/null 两模型对照写进断言）。**两套币种口径并存未统一**（`statistical_analysis.py:991` 缺省视为 USD），不得引用为"成本口径已全仓统一"。AB-12 轮：新增 §15——**0 实例要连测量覆盖面一起锁**：AB-12c 的前置普查第一版
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
| ③（ADR-0029，2026-10-08，本起为该 ADR 新发现） | **跨文件任务未物化**：合成跨文件任务（Level 3 / 3.5）的 gold test_cases 直接 `import module_a/module_b/module_c`（模块名中性化、不重写），历史单文件判分口径只物化 `{task_id末段}.py` | **判分口径**（只写目标模块单文件）vs **任务真实结构口径**（按 metadata 物化完整伴生模块树，被测目标模块内容 = `target_code` 三态统一规则、伴生模块取缺陷原版，与 `run_benchmark._write_cross_file_modules` 同口径） | 伴生模块缺失 → 收集错误 rc=2 → 跨文件行 repair 系统性 0；R2 评审量化；连带可观测 `false_fix` 被抬升（**R4-A 6/8 行 = 1.0**）与 detection 偏低 | **六批次**（R4-A、E2×2、R-P0-2×3）跨文件行 repair 系统性 0；修复后跨文件行由恒 0 变为可测：**25 跨文件行中 11 行 correct**（并非全部可判 1.0——说明跨文件任务本身更难，伪影只是擦除了本可测信号）；口径链更新：R-P0-2 **35.86% → 39.31%（57/145）**、E1/E2 **48.11% → 54.72%（58/106）**、R4-A **44.4%（8/18）→ 55.6%（10/18）**；连带污染"修正口径"数字（ADR-0027 的 35.9%/48.1% 仍含系统性零行） | 新增 `_prepare_cross_file_test_tree`（按 metadata 物化完整模块树；顶层模块直接落 `{name}.py`；PYTHONPATH 覆盖 tmpdir）；`_run_pytest_in_tmp(..., task_metadata=...)` 四入口透传上下文、优先消费显式信号（`is_cross_file=True` / `source=="quixbugs"`）；空补丁语义对齐（`return 0.0`，消除"缺陷原码恰好过 gold → 误判 1.0"边界假阳性）；新增 `tests/test_m1_cross_file_metric.py` / `tests/test_m1_dispatch_heuristic.py`；新增**口径矩阵纪律** `docs/design/repair_caliber_matrix.md` | `experiments/results/main_batch/corrected_report_v2.md`（v2 定案）与 `experiments/results/r4_batches/replay_r4_ab_arm_a_v2.md`；复算入口 `make corrected-metrics` / `experiments/repair_replay.py`（零 LLM） | **是**（对受影响数字）：v1 的 35.86% / 48.11% 被降级为"修正前下界"，对外材料一律替换为 v2 或显式标注下界；主批次检测/修复的**定性方向**不变 |
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
`experiments/results/emse_misguided_20261017/`。

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
描述性、无显著性推断。工件：`experiments/results/emse_oracle_quality_20261017/`
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
工件 `experiments/results/emse_oracle_independent_judging_20261017/`）：
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
`experiments/results/emse_oracle_instrument_hardening_20261017/`；墙钟 279.9s）：
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
`experiments/results/p_round_oracle_examples_20261018/`（raw + norm 双报告、ATTRIBUTION、
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
`experiments/results/q_round_examples_ab_20261018/`（101 项 SHA verify）。

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
工件 `experiments/results/t_round_oracle_k3_20261018/`（22 项 SHA verify）。

**T-3b SMT 见证层首个专项评估批（2026-10-18，零 LLM）**：A-18/Q7 此前是"实现在场、
评估缺席"。本批 QuixBugs 41 缺陷程序、锚表内容寻址 50/50 命中、z3-solver 5.1.0、
per-clause 5s，产出 184 条非空评估子句的逐子句审计：**sat 19 / unsat 0 / unknown 0 /
timeout 0 / error 165**；`smt_witness_rate` 均值 0.088531、`smt_timeout_rate` 0.0
→ 机制层 **pass**（层在工作、超时有界、桶可逐子句复算）。**但 reach_rate 仅 0.103261**
——瓶颈不在求解器（到达求解器的 19 条 19/19 全 sat），而在"材料未达求解器"；
错误归因给出最大单项 **`result_alias_not_reached`=110 条（66%）**：SpecIR 表达式通道
后件写 `result`，而 `spec_smt` 后件自由变量域只有 `r`（见 §T-3c）。该批不做
detection 关联（中位数二分退化，低桶为空）——**只报告"无对照"**，MDE≈16.57pp 已披露。
工件 `experiments/results/t_round_smt_witness_20261018/`（7 项 SHA verify）。

**T-3c `result`/`r` 别名缺口修复（2026-10-18）**：T-3b 的错误归因直接定位到
`src/specs/spec_smt.py::_collect_post_constraints` 的自由变量域缺口——表达式通道后件
普遍引用 `result`，而该层只认 `r`，导致 110 条子句**保守未达求解器**（不是求解失败）。
修复（token 感知 AST 归一：仅当 `result` 不在签名参数中时把后件/不变式 `Name(id="result")`
改写为 `r`，解析失败保守回退；参数名确为 `result` 时不归一）后零 LLM 复跑，见
`experiments/results/t_round_smt_witness_aliasfix_20261018/`。**口径纪律**：T-3b 旧批保留为
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
指纹 pinned）以分离推理预算与协议开关两个因素。工件 `experiments/results/t_round_b2_main_batch_20261018/`
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
详见 `docs/reviews/EXPERIMENTS_JSON_DOMAIN_AB9_2026-10-20.md`。

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
详见 `docs/reviews/ABSENT_VS_ZERO_AB10_2026-10-20.md`。

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
`docs/reviews/ABSENT_VS_ZERO_AB11_2026-10-20.md`。
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
"qwen-long":        {"input_per_mtok": 0.5, "output_per_mtok": 2.0, "currency": "CNY"}
"deepseek-flash":   {"input_per_mtok": 0.3, "output_per_mtok": 1.2, "currency": "USD"}
```

前置探针（`/tmp/ab13_probe2.py` R4）用一条 `qwen-long` 的合成行实测：
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
  从没执行过**的嫌疑，所以另立两例：`qwen-long`（CNY）与 `agnes-3.0-flash`（价格为 null）
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
本轮**实测坐实但登记不修**，见 `docs/reviews/CURRENCY_SINGLE_SOURCE_AB14_2026-10-20.md` §5；
**本节的这两句在初稿里写错过两处**（函数名 `oracle_examples_replay.compute_cost_usd` 全仓 0 命中，
以及"`models` 非对象一律崩"），均在收口前由 `/tmp/ab15_probe.py` 复算推翻并就地更正——
**登记"未处置站点"本身也要带可复算的函数名与形状清单**，散文式记忆不是证据；
不得引用"入库统计报告已可逐位复现"——`statistical_report_e2.md` / `_e2_iter.md` 与现码输出分别差
**86 / 88 行**，且该差值在本轮改前改后完全相同（陈旧于本轮之前，成因是 S11 与 BH-FDR 节晚于生成）。

## 18. 附：AB-15 轮（2026-10-20）拒绝不是一种读数 — 被拒绝的金额不得披着金额的形状，归因必须是判定的另一半

AB-14 把"这笔钱是不是美元"的判定收成一遍，但**判定收口不等于下游的呈现与归因也收口**。
本轮前置实测坐实三条通道，它们都不是"判错"，而是**判对之后又在下游把拒绝改写成了金额形状**：

- `oracle_examples_replay.render_readme` 对 `estimated_cost_usd=None` 无条件加 `$` ⇒ 未登记模型与
  `qwen-long`（CNY）都印 `**$None**`，真零消费印 `**$0.0**`——两者共用同一个美元前缀，
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
`docs/reviews/COST_REJECTION_RENDERING_AB15_2026-10-20.md` §5 / §7。

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
  USD `0.3/1.2`，agnes 价 `null`，qwen CNY）⇒ 收紧数字域后池化
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
逐项边界与复算命令见 `docs/reviews/PRICE_ADMISSION_AB16_2026-10-20.md` §5 / §7。

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
`docs/reviews/TABLE_ADMISSION_AB17_2026-10-20.md` §5 / §7。

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
  同形，且都渲染成 `0.0000 (***)`。本仓另一处 `1.0 - _normal_cdf(z)`
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
（都显示 "0.0000 (***)"）。现非零且 |v| < 1e-4 → `{:.2e}`；精确 0.0 仍印
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
