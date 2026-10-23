# BV 轮：批次 VIII / XIV 两份判定核的「沉默」从未披露（零 LLM，$0）

登记日 2026-10-23；实测自 2026-10-23 02:2x 起（本机 macOS，Python 3.14.6，pytest 9.1.1）。

## 1. 发现

BU 轮把「只写不读」键池点清（13 键 / 76488 行），并从池里收口了 Self-Repair Trap
两键。池里紧接着的两族是**同一批观测层（ADR-0022 / ADR-0028）的判定核**，自写入起
在报告面**零读者**，而两者的沉默都是「多成因、同取值」：

| 键 | 写入点 | 归档行 | 沉默形态 |
|---|---|---|---|
| `test_hacking_suspected` / `test_hacking_signals` | `run_benchmark.py:2209-2211`（批次 VIII，ADR-0022） | 5935 | 判定核在「无原码 / 无补丁 / 原码解析失败 / 补丁解析失败」时返回 `suspected=False, signals=[]`——与「三信号都跑过且零命中」**完全同形** |
| `fl_constraint_verdict` / `_hit_rank` / `_changed_functions` | `run_benchmark.py:2219-2222`（批次 XIV，ADR-0028） | 5935 | 六种早退（无终局状态 / 无补丁 / 无定位 / 无原码 / 变更集合为空 / 无候选）+ 异常，共用一个 `not_evaluable` |

归档实测（`experiments/results/`：257 份批次文件 / 11197 条结果行；全部读数见 §4 复现命令）：

| 事实 | 数值 |
|---|---|
| hack 有判定键的行 | **5935**（其余 5262 行早于批次 VIII，键缺席） |
| hack 状态已落盘 | **0**（BV 之前没有状态键——所以这 5935 行的「判过没有」无从判断） |
| hack 判 `True` | **20**（`hardcoded_input_branch` 12 + `exception_swallow_added` 8；`assert_weakened` 0） |
| 信号非空行 | **20**（与判 True 同集：判 True ⇔ 至少一个信号） |
| FL 判定值 | `hit` **1487** / `miss` **6** / `not_evaluable` **4442** |
| FL 已求值 | **1493** ⇒ hit 比 **99.60%** |
| FL 未求值成因（按行内材料推断，下界） | 无补丁 **4066** / 无定位 **367** / 变更集合为空 **9** / 不归因 **0** |
| FL 变更函数分档（hit+miss+not_evaluable） | 0 → **4442** / 1 → **958** / 2 → **506** / 3+ → **29** |
| FL hit_rank | `rank_1` **1478** / `rank_2` **9** |
| 两族读端（改前） | row_read：hack 2 / FL 3，**报告面 0**；state_read 0 |
| 只写不读键池（§61① 读法口径） | 改前 **11 键 / 64618 行** → 本两族接入读端后 **6 键 / 34943 行**（34943 + 5 × 5935 = 64618 ✓） |

三条事实值得单独点名：

1. **20 行真实命中从未在任何报告面出现。** 这不是「判定核没响」——它响了 20 次，
   12 次是硬编码输入分支、8 次是新增吞异常。报告面读端为 0 ⇒ 读者只能看到
   「test hacking 没提」，而这句话在归档里同时兼容「0 命中」与「20 命中」。
2. **5915 行的「不怀疑」分不清是判干净还是没看。** 判定核的四个早退分支与「三信号
   都跑过且零命中」返回同一个 `{"suspected": False, "signals": []}`，而输出里没有任何
   字段能区分；批次 VIII 设计时也只落两键。
3. **「约束门」在归档里几乎不区分。** 已求值 1493 行里 hit 1487 / miss 6。ADR-0028
   登记的成因之一是「整文件重写补丁 ⇒ 变更集合 ≈ 全文件函数 ⇒ 判定近乎恒 hit」；
   但归档里 3+ 档只有 29/1493 = 1.9%（1 档 958、2 档 506）——**这条成就不足以解释
   99.6%**。真实含义是：补丁改的函数几乎总落在 Top-k 候选里，而 miss 只有 6 行，
   说明该门在本语料的判别力极低。这句话以前没有任何报告面可说。

## 2. 处置

**判定核（写侧，增量）**：`src/tools/patch_test_hacking.detect_test_hacking` 增返
`status`（`hacking_evaluation_status_names()`：`ok` / `empty_original` / `empty_patch` /
`parse_error_original` / `parse_error_patched`），并把两侧解析拆成两个 try——解析失败要能
归属到**哪一侧**。判定值语义零变化：`ok` 之外仍是 `suspected=False, signals=[]`。

**单一事实源**：新增 `experiments/_verdict_silence.py`

- 键名常量：`HACK_SUSPECTED_KEY` / `HACK_SIGNALS_KEY` / `HACK_STATUS_KEY` /
  `FL_VERDICT_KEY` / `FL_HIT_RANK_KEY` / `FL_CHANGED_KEY` / `FL_REASON_KEY`（:35-74）；
- 词表：`HACK_STATUS_VOCAB`（与判定核逐项一致，测试锁）、`HACK_SIGNAL_NAMES`
  （与 `hacking_signal_names()` 一致）、`FL_VERDICTS`、`FL_REASON_VOCAB`（写侧七档 + `ok`）、
  `FL_INFERRED_VOCAB`（读侧推断四档，**下界**）；
- 读侧原语：`hack_status` / `hack_evaluated` / `hack_signals` / `fl_verdict` /
  `fl_changed_functions` / `infer_fl_reason` / `fl_reason`（返回 `(成因, 来源)`）/
  `fl_evaluated` / `fl_reason_mismatch`。

**写侧（结果行，增量）**：`run_benchmark._test_hacking_result` 透出 `status`；行落
`test_hacking_status`。`_fl_constraint_result` 每条早退带 `reason`（`FL_REASON_*`）；
行落 `fl_constraint_reason`。顺带收口一处重复计算：判定核此前在结果行被**调用两次**
（`suspected` 与 `signals` 各一次 ⇒ AST 差集跑两遍），现单次计算三键共享。

**读端**：`statistical_analysis.detector_silence_stats(rows)` + `detector_silence_summary(data)`——
hack 侧四档（已求值 / 没看 / 状态未记录 / 判定未记录）+ 恒等式 + 信号分布 + 词表外信号点名 +
`n_suspected_without_evaluation`（只在状态**已落盘**且非 `ok` 时点名——历史行状态未记录，
不得算成写侧矛盾）；FL 侧判定值三档 + 成因**按来源分列**（记录 / 推断 / 不适用 / 无判定键）+
恒等式 + hit 比（分母只含已求值）+ hit_rank + 变更函数分档。

**报告面**：`analyze_results.py` :112 以别名 `_detector_silence` 导入，:230 落
`per_baseline.detector_silence`，:1400-1520 新增章节
「批次 VIII/XIV 判定核的沉默分档（BV：`test_hacking_*` / `fl_constraint_*` 的读侧）」——
两张表（hack 9 列 / FL 11 列）+ 每臂行 + `**合计**` 行、沉默臂注、判 True 行点名（样例
封顶 10 个 task_id）、`没看` 注、**约束门判别力注**（按 3+ 档占比二选一：高则与 ADR-0028
登记成因一致，低则明写「该成因不足以解释这个比值」）、成因不一致注 + 两条口径脚注。
`run_main_batch._print_r4_summary` 增一行摘要（与 BQ 检查腿同风格），批次跑完即可见。
**不进入任何判定，不改 passed / repair / 分母，也不给论文数字提供新出口。**

**棘轮**：BQ 的读者数棘轮键集新增 `detector_silence`（只增不删）。

## 3. 验证

### 3.1 测试

| 项 | 读数 |
|---|---|
| BV 新锁 | `tests/test_verdict_silence_bv.py` **87 例**（75 个测试方法 + 参数化展开）全绿 |
| 全量回归 | **12257 passed / 19 skipped / 0 failed**，218.94s（沙箱口径，`-n 4 --dist loadfile`） |
| collected | **12276**（沙箱 12257 + 19 skip；正常口径 = 12271 passed + 5 skipped ⇒ collected 12276，两口径 collected 一致） |
| 旧契约改写 | 2 处：`tests/test_batch_viii.py`（原断言用整字典相等把「没看」锁成「判干净」）、`tests/test_patch_test_hacking.py`（同型）——两处都改为「判定值不变 + 另钉求值状态」 |
| 覆盖率（CI 口径） | 行 **19538/20052 = 97.4367%**（97.44）、弧 **7150/7584 = 94.2774%**（94.28），取自 `coverage.xml` root 口径（`lines-covered` / `branches-covered` 属性）；棘轮 96.40 / 92.50 绿（余量 1.04 / 1.78pp） |
| 覆盖率变动归因 | 相对 BU（行 19526/20040、弧 7150/7582）：**+12 行 / +12 弧**，全部来自 `src/tools/patch_test_hacking.py` 的五状态拆分与两个 try（本轮唯一 `src/` 改动）；未覆盖行 511 → **514**、未覆盖弧 432 → **434**（分母同步 +12 / +2） |

### 3.2 变异

`scripts/tools/bv_mutation_verify.py`：**58 个锚点全部转红 + 中性对照 N01 0 红**（零逃逸），
逐锚点红名见该脚本 SUMMARY 段。纪律：干净树先全绿且 collected 一致（恒 227）→
逐锚点读原字节 → 写变异 → `compile()` → 收集数核对 → 跑受影响面 → **sha256 校验后按原字节还原**
（不用 `git checkout` / `git stash`）。

首轮 **3 项存活**，全部就地处置（非登记了事）：

| 存活锚点 | 存活原因 | 处置 |
|---|---|---|
| V04（常量改名） | `no_candidates → no_candidate`：模块内比较全走常量，代码面自洽，行为断言看不见 | **字面量契约锁**——成因名会落进结果行 JSON，改名等于改工件契约，只能靠字面量钉 |
| P11（两列互换） | 夹具里「记录成因 : 推断成因」恰好 1:1 ⇒ 交换是恒等操作 | **不对称夹具**（2:1）——与 BU U18 同族，对称夹具会让整类变异失明 |
| S03（恒等式标记） | 四档 / 两支都由同一循环内的分支赋值 ⇒ 恒等式按构造恒真，把它硬编码成 `True` 无法被区分 | **删字段**——恒等式改由测试直接断言。删掉一个假检查点与补一条锁，价值同级（§66③） |

### 3.3 门禁

干净树全绿：`ruff check`（All checks passed）/ `ruff format --check`（1020 文件已格式化）/
`mypy src/ config.py`（137 文件，Success）+ 15 项 gate（双语文档 / 文档链接 / env 预算 /
BASELINE 结构 + 数字 / 状态契约 / env 快照 / 模型指纹 / 工具版本 / JSON 契约计数 /
严格 JSON / 报告→工件对账 / 零断言 / ast 守卫棘轮 / 状态落盘可达性）全过。

### 3.4 只读普查三段

`scripts/tools/bv_verdict_silence_census.py --segment a|b|c`：

- **A 段**（全归档 257 批次 / 11197 行）：读数与 §1 表逐位一致；hack 四档恒等式成立
  （0 + 0 + 5935 + 5262 = 11197），FL 成因恒等式成立（recorded 0 + inferred 4442 = not_evaluable 4442）。
- **B 段**（键池复核）：**6 键 / 34943 行**，与期望（11 键 − 5 键；64618 − 5 × 5935 = 34943）**同时**对上。
- **C 段**（四个具名冻结批次逐档核对）：4/4 **OK**，零 DRIFT。

## 4. 复现

```bash
# A. 全归档判定核沉默分档（只读 experiments/results）
.venv/bin/python scripts/tools/bv_verdict_silence_census.py --segment a
# 实测：批次 257 / 行 11197
#   hack 有判定 5935 | 状态已记录 0 | 已求值 0 | 没看 0 | 状态未记录 5935 | 判定未记录 5262
#   判 True 20 / 信号非空 20 / 信号 {hardcoded_input_branch: 12, exception_swallow_added: 8}
#   FL hit 1487 / miss 6 / not_evaluable 4442 | 已求值 1493 | hit 比 0.9960
#   成因来源 {not_applicable: 1493, inferred: 4442, unrecorded_verdict: 5262}
#   成因（推断）{inferred_no_patch: 4066, inferred_no_localization: 367,
#               inferred_no_changed_functions: 9}
#   变更函数分档 {0: 4442, 1: 958, 2: 506, 3+: 29} | hit_rank {rank_1: 1478, rank_2: 9}
.venv/bin/python scripts/tools/bv_verdict_silence_census.py --segment b   # 键池复核：6 键 / 34943 行
.venv/bin/python scripts/tools/bv_verdict_silence_census.py --segment c   # 冻结批次逐档（4/4 OK）

# B. 报告章节（两张表 + 五类注 + 两条脚注）
.venv/bin/python experiments/analyze_results.py --input <batch.json>

# C. 变异验证（58 锚点 + 1 对照）
.venv/bin/python scripts/tools/bv_mutation_verify.py
```

## 5. 未做 / 边界

- **不回填历史行**：5935 行仍没有 `test_hacking_status` / `fl_constraint_reason`；
  报告面把 hack 侧显示为「状态未记录」、FL 侧显示为「成因推断（下界）」，不折成任何一档。
- **不动判定核的判定方向**：`ok` 之外仍 `suspected=False`；`not_evaluable` 仍是
  `not_evaluable`；`hit` / `miss` 口径与 hit_rank 一处不动。
- **不进入任何判定**：分档、hit 比、成因都不改 passed / repair / 分母。
- **推断不是全集**：「无原码 / 无候选 / 异常」三支在历史行里没有痕迹，落
  `inferred_unattributed`；本语料该档为 0，但这是**下界**，不是「没有这三支」。
- **键池其余 6 项未动**（复跑 B 段可点清，合计 34943 行）：`risk_summary`（8864 行）、
  `patch_precision`（8012）、`patch_abstain_signals`（5935）、`patch_plausible_evidence` /
  `patch_plausible_invariant_violation` / `mdo_crash_rate`（各 4044）仍是只写不读——它们是
  BW 轮的候选池。
- **英文索引**：`docs/INDEX.en.md` 的滚动行本轮补 BV；此前 BR / BS / BT 三轮只落在中文
  滚动行，属历史漂移，不代补（分册表本轮补齐 BV 一行）。
- **未跑真实批次**：本轮零 LLM、$0；新批次才会真正产出 `test_hacking_status` /
  `fl_constraint_reason`，归档里这两列将始终是「未记录」——这是设计，不是缺陷。

## 6. 本轮自纠

| # | 自纠项 | 说明 |
|---|---|---|
| ① | **普查脚本的 C 段静默失败** | `PINNED_BATCHES` 是**带注解**赋值（`ast.AnnAssign`），脚本只处理 `ast.Assign` ⇒ 解析失败并打印「解析失败」后 `return`，**不报错、不退出码非零**。四个冻结批次的核对因此从未真正跑过。修法：同时认 `AnnAssign` 与 `Assign`；且 C 段失败改为**显式非零退出**（一个段失败不能让整轮普查看起来跑完了）。 |
| ② | **B 段期望提示写错且不可执行** | 期望写「9 键 / 34943 行」，实测与文档 §5 登记的是 **6 键**（11 − 5 = 6）——提示与事实不符，且只报数字不判定，漂移不会被拦。修法：期望改为「6 键 / 34943 行」并**同时校验键数与行数**（只对行数会漏掉「键被拆/并」的漂移），不符即打印「**漂移**」。 |
| ③ | **锚点数登记与脚本实况不符** | 文档与脚本 docstring 写「60 个锚点」，实况是 **58 变异 + 1 对照**（S03 / S06 两项在首轮处置后已不存在）。修法：脚本 docstring、§66④ 与三处索引登记统一为「58 锚点 + 1 对照」——**登记数字必须来自脚本实况，不能来自首轮的印象**。 |
| ④ | **删掉一个按构造恒真的检查点** | `detector_silence_stats` 曾带 `partition_ok` 字段（四档求和 == 行数），但四档由同一循环内的分支赋值 ⇒ 该恒等式**按构造恒真**，把它硬编码成 `True` 任何变异都杀不掉。处置：**删字段**，恒等式改由测试直接断言（S03 存活项的处置同源）。 |
| ⑤ | **覆盖率弧数解析两次出错** | 第一次把 `condition-coverage="100% (2/2)"` 的百分数当分子（弧数算成 3582150）——**自建解析器不得凭记忆**；第二次累加写错（`at += a2` 应为 `at += b2`）。最终改用 `coverage.xml` **root 属性**（`branches-covered` / `branches-valid`）取权威值，行弧两口径一致。 |
| ⑥ | **zsh glob 无匹配会中止命令链** | `rm -f .coverage.ci .coverage.ci.*` 在 zsh 下因第二个 glob 无匹配而**整条命令失败**（退出码 1），覆盖率跑批根本没启动。改写为不带 glob 的单文件删除后重跑。 |
| ⑦ | **沙箱与正常口径必须分列** | 沙箱跑 **12257 passed / 19 skipped**（19 = 5 + 14 项环境能力 skip），正常口径 **12271 passed / 5 skipped**；两口径 **collected 同为 12276**。登记只写正常口径，文档注明沙箱读数，不混用。 |

**本轮自纠的一句话**：这一轮里有 **三处「看起来跑过了、其实没跑」**——C 段静默失败（解析
不中就 return）、B 段期望写了错数字且不判定、锚点数登记沿用首轮印象。三处的共同形状是
**「失败路径没有非零退出码」**：脚本可以什么都没验，却打印得像验过了。修法统一为
「段失败 ⇒ 显式非零退出」+「期望数字来自脚本实况而非印象」。

