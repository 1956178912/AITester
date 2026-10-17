# 测量完整性：口径分叉的五种形态与修复方法论

最后更新：2026-10-17（M 轮：新增 §6——**确定性 oracle 的未校验注入 + 判分耦合**
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

**背景（预注册口径）**：df_spec 双臂实验（`docs/emse/EMSE_DF_SPEC_PREREG_2026-10-16.md`）
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
