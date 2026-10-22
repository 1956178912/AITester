# BK 轮：`ast.parse` 守卫的捕获面棘轮——"读不懂"有两种异常，逐点收敛永远收不完（2026-10-22，零 LLM，$0）

**范围**：``src/`` 里所有"在 `try` 中调 `ast.parse`"的守卫站点——本轮收敛 **13 处**
（`tools/deterministic_repair.py` 3 / `tools/cross_file.py` 2 / `tools/patch_intent.py` 2 /
`tools/multi_candidate.py` 5 / `graph/expert_pool.py` 1），三个发布点把逐腿读数写进观测键
（`graph/debugger.py:389-390` 确定性分支、`graph/debugger.py:721-722` 专家池分支、
`agents/debugger.py:690-693` 编辑意图），并新增**仓库级阻断门禁**
`scripts/gates/check_ast_parse_guards.py`（接 `make gates` 新目标 `ast-guards` 与 ci.yml 独立步骤）。
共享口径沿用 BI 的单一事实源 `src/utils/check_status.py`（本轮把捕获面常量
`AST_UNREADABLE_ERRORS`、形态归因 `unparseable_shape()`、文案 `parse_error_text()`、
可解析性判定 `parses_as_module()` 上收进该模块：43 行 → **65 行 / 22 弧**）。

**结论**：单腿守卫（只捕 `SyntaxError`）在 Python 3.14.6 上会被**孤立代理位**文本抛出的
`UnicodeEncodeError`（`ValueError` 子类）**抛穿到调用方**；而对已经降级的分支，"读不懂"
又被折叠进带判定含义的空结果。本轮把两件事分开收口：**捕获面**收敛为共享常量，
**折叠形态**要么当轮换掉（13 处接 `outcome_sink`）、要么按 `(站点数, 折叠形态)` 计额度
登记（19 条 / 20 站点），并由棘轮阻断"再写一个新单腿守卫"。**判定值逐字节不变**：
11 个判定面 × 14607 条输入 = **160677 项对账、UNEXPECTED 0**（41 条是本轮修掉的抛穿腿，
全部来自人工形态栅格，归档语料 **0 实例**）。**55 例新锁 + 变异 13 锚点全击杀
（红数 24/15/1/2/1/5/2/2/1/1/1/5/1）+ 中性对照 0 红**；`git status` 无残留、门禁自测
`rc=0`。**未提交**（随收口提交一并入库）。

---

## 1. 缺陷：同一个"读不懂"有两副面孔

### 1.1 抛穿面（守卫捕不住）

`ast.parse` 不只抛 `SyntaxError`。本轮在同一解释器（Python 3.14.6）实测四类"读不懂"：

| 输入形态 | `ast.parse` 实际抛出 | 单腿守卫（`except SyntaxError`） | 是否新增腿 |
|---|---|---|---|
| 真语法错 `def f(:` | `SyntaxError` | 接住 | 否 |
| null 字节 `x = 1\x00` | `SyntaxError`（"source code string cannot contain null bytes"） | 接住 | **否**——BJ 曾怀疑它是第二条腿，实测归 `SyntaxError` 本体 |
| 围栏块 / 截断围栏 / git diff | `SyntaxError` | 接住 | 否 |
| **孤立代理位** `x = '\ud800'` | **`UnicodeEncodeError`**（`ValueError` 子类） | **抛穿到调用方** | **是**——本轮唯一的新腿 |

"新腿只有一条"不等于"影响只有一条"：抛穿点的调用方是节点级函数，抛穿即整节点崩。
实测最直白的一处是 `multi_candidate.static_validate_patch`（现 `:132-141`）：候选补丁含代理位时，
旧版把 `UnicodeEncodeError` 一路抛给 `_debugger_node`，**修复节点直接失败**，连"这个候选不合格"
都没写下来。

### 1.2 折叠面（捕住了但把事实抹平）

已经降级的分支把"读不懂"折进**带判定含义**的空结果——读数侧分不清"干净"与"没读出来"。
本轮开工普查得到的存量形态（逐条来自 `EXEMPT` 额度表，见 §2.2）：折叠成 `[]`（断言/函数/类清单）、
`set()`（顶层名字集）、原码 + `False`（布尔位复用）、`None`（定位缺位）、合成名 `func{N}`、
整模块视为变更 `{'<module>'}`、三键全空 dict、`tree = None`、以及**换口径不回退**
（AST 计数失败 ⇒ 回落 regex，分母换了但读数不标注）。

### 1.3 为什么必须上门禁，而不是继续逐点改

BG 改 `type_repair`、BH 改 `testless_validation`、BI 改两道写盘前守卫、BJ 改 `oracle_validator`、
本轮改 5 个模块 13 处——**每轮收一个模块，永远收不完**，而且新代码随时可以再写一个单腿守卫
且无人拦截。BJ 手册 §7 已把这条按名登记为候选，本轮就是它的兑现：口径本身不变
（仍是 `check_status` 那一个事实源），**变的是"谁守护它"**——从"下一轮想起来再说"变成
"提交前 `make gates` 直接红"。

---

## 2. 处置：捕获面收敛 + 折叠面按额度登记（判定不动）

### 2.1 单一事实源（四条口径）

1. **捕获面**：`AST_UNREADABLE_ERRORS = (SyntaxError, ValueError)`——按**族**收而不是按
   具体异常名列举，`ValueError` 族成员不止 `UnicodeEncodeError`（本轮实测确认 null 字节
   走 `SyntaxError`，但 `ValueError: source code string cannot contain null bytes` 在别的
   入口同样存在），逐名列举就是下一轮缺陷。
2. **形态归因**：`unparseable_shape(text)` → `fenced_block` / `git_diff` / `undecodable` / `syntax`
   四值。**判据是"这段文本本来是不是 Python"**：围栏与 diff 是传输层伪影，`undecodable`
   是编码层，`syntax` 才是产物缺陷；把 `undecodable` 折进 `syntax`（变异锚点 M2 反向锁的
   正是这个）就等于宣称"编码问题=代码写错了"。
3. **文案**：`parse_error_text(exc)`——`UnicodeEncodeError` 的 message 带 codec 细节，
   `SyntaxError` 带行列；统一入口才不会各写各的。
4. **聚合方向**：`worst_check_status(statuses, default=CHECK_ERROR)`——**一条腿都没记录 ⇒ `error`**。
   这与 BG 的独立检查层同向、与"任一后端量过就算数"（`any_measurable_status`）反向；
   变异锚点 M3 锁的就是这个默认值被改成 `ok`（空读数自称干净）。

### 2.2 13 处收敛 + 20 处按额度登记

本轮收敛的站点（键 = `文件::函数`，与门禁同构）：

| 模块 | 站点 | 收敛前的折叠 / 抛穿 | 收敛后 |
|---|---|---|---|
| `tools/deterministic_repair.py` | `_top_level_names` / `_insert_import` / `attempt_deterministic_repair` | 代理位目标码抛穿；读不懂 ⇒ `set()` / 原码 | `target_readability` + `candidate_validation` 两腿 `{check,status,reason}` |
| `tools/cross_file.py` | `analyze_cross_file_deps` / `_collect_reverse_deps` | 读不懂 ⇒ 空依赖图（与"无依赖"同值） | `entry_readability` 腿，reason 带形态 |
| `tools/patch_intent.py` | `apply_edit_intents` ×2 | 原文读不懂 ⇒ 锚点计数 0 ⇒ "整体拒绝"却不说是为什么 | `original_readability` / `edit_application` 腿 |
| `tools/multi_candidate.py` | `static_validate_patch` / `_func_signatures` / `synthesize_candidates` ×3 | **抛穿整节点**（§1.1）；合成结果读不懂 ⇒ 折成"单候选回退" | `patch_validation` / `synthesis_result_readability` 腿，折叠方向仍是保守拒绝 |
| `graph/expert_pool.py` | `_normalize_patch_for_voting` | 读不懂 ⇒ 回退 `ast.dump` 之外的原文本（投票口径换掉不标注） | 腿记录 + `cross_validate` 逐候选腿发布 |

未收敛的 20 站点进入 `EXEMPT`（**只允许变短**的额度表），每条登记 `(站点数, 折叠形态)`，
例如 `tools/code_analyzer.py::replace_function_code = (2, "读不懂⇒(原码, False)")`、
`tools/testless_validation.py::_top_level_defs = (1, "读不懂⇒部分名字集")`、
`agents/generator.py::_extract_existing_assertions = (1, "读不懂⇒[]")`、
`datasets/dataset_ult.py::_first_function_name = (1, "读不懂⇒合成名 func{N}（归档 4805 站点 0 实例）")`。
**豁免的是"这条分支现在折叠成了什么"这一事实，不是"这里可以永远不看"**：命中数为 0
（条目失效）或少于登记数（条目偏大）同样失败。

### 2.3 判定不变性（本轮的承诺面）

- **返回值**：所有已返回的输入（读得懂 / 抛 `SyntaxError` 的读不懂）返回值 `repr` 逐字节不变；
  `outcome_sink` 是侧信道（`list.append`），默认 `None` ⇒ 生产路径零开销、零新键。
- **抛穿腿**：旧版抛 `ValueError` 族的输入，本轮改成**保守拒绝 + 披露**（`static_validate_patch`
  仍返回 `False`）。方向是 fail-closed，**不新增任何放行**——"崩溃"不是判定，把它换成
  "测出来不合格并且说清为什么不合格"才是本轮的处置。
- **发布点**：`check_status` / `check_outcomes` 随分支结果写入观测键；聚合值取自真实腿
  （M10 把它硬写成 `ok`、M11 把腿清空，两条都红）。

---

## 3. 测量（改前 / 改后，全部实测）

### 3.1 棘轮自测——同一把尺子量两棵树

| 树态 | 扫描文件 | `ast.parse` try 站点 | 未覆盖 ValueError 族 | 违规 | 豁免命中 | EXEMPT 条目 |
|---|---|---|---|---|---|---|
| **HEAD 导出**（`git archive` 的 `src/` + 现 `check_status.py`） | 135 | **79** | **35** | **15** | 20 | 19 |
| **现工作树**（干净，无变异） | **136** | **78** | **20** | **0** | **20** | **19** |

四条读数需要各自的算式：

1. **HEAD 的 15 条违规逐条点名**，恰是 BK 的 13 处 + BJ 的 2 处
   （`tools/oracle_validator.py::check_assertions:92 / :104`）⇒ **35 − 15 = 20** 与现树读数对上，
   "本轮收敛 13 处"不是自述而是门禁复算。
2. **79 → 78 的 1 站点差额已按 `(文件, 函数)` 多重集逐项对账**（同一门禁的 `scan` 复跑）：
   `oracle_validator.py::check_assertions` HEAD 2 → 现 0（BJ 把内联 try 换成 `parses_as_module()`），
   `testless_validation.py::_unparseable_side` HEAD 0 → 现 1（BH/BI 新增的站点）。
   2 − 1 全落在 **BJ/BH 的未提交栈**上，**与 BK 无关**——不写"已排除"，写清是哪两处。
3. **文件数 135 → 136** 同理：现树比 HEAD 多两个未跟踪新模块
   （`src/utils/check_status.py` BI、`src/utils/pytest_output.py` BE/BF 段），导出树里我手工补入了
   `check_status.py`（门禁 import 它才能解析共享常量的运行时取值），故 135 = HEAD 的 134 + 1。
4. **extras（`--all`，仅报告不阻断）**：`experiments/` + `scripts/` 合计 **169 文件 / 45 站点 / 26 未覆盖**。
   其中 1 条是"无 handler 的裸 try"（`experiments/emse_dsl_diag3.py:214`），2 条把
   `UnicodeDecodeError` 当腿（`scripts/gates/check_env_snapshot_keys.py:271::collect_env_sites`、
   `check_json_strict.py:164::_scan_source`）——拦不住 `UnicodeEncodeError`，属同族缺陷的另一半。
   （这两处行号比 §6 第 1 条的普查读数各小 1：普查按 `except` 子句行计、守卫按 `try` 行计。）

### 3.2 判定不变性对账（`scripts/tools/bk_judgment_invariance.py`）

用 `git show HEAD:<path>` 把受比模块的改前版本落到临时包 `headpkg`，同进程内对同一批输入
分别调用新旧函数、直接比 `repr`（不比摘要——§6 第 3 条）。

- **输入面**：人工形态栅格 **11** 条（空 / 纯空白 / 真语法错 / 闭合围栏 / 截断围栏 / git diff 全文 /
  仅 hunk 头 / null 字节 / 孤立代理位 / 代理位锚点 / 代理位 NameError 目标 / 围栏+代理位）
  \+ 归档代码串 **14596** 条（`experiments/results/**/*.json` 的 `patch` / `generated_test` /
  `test_patch` / `code` / `target_code`），合计 **14607** 条输入。
- **判定面 11 个**：`attempt_deterministic_repair`、`_top_level_names`、`_insert_import`、
  `analyze_cross_file_deps`、`_collect_reverse_deps`、`_normalize_patch_for_voting`、`cross_validate`、
  `apply_edit_intents`、`static_validate_patch`、`_extract_modified_regions`、`synthesize_candidates`。
- **读数**（一次连续运行，墙钟 64s，由日志"创建→末次写入"时间戳推得）：

| 项 | 值 | 含义 |
|---|---|---|
| 对账项 | **160677** | 11 × 14607 |
| identical | **160636** | 新旧返回值逐字相同 |
| escape_fixed | **41** | 旧版抛 `ValueError` 族、新版返回 ⇒ 本轮修掉的抛穿腿 |
| both_raised | **0** | 两侧同抛非 `SyntaxError`（对账盲区）——本轮为零 |
| UNEXPECTED | **0** | 脚本对"判定变了"的承诺面，非零即 `rc=1` |
| rc | **0** | |

- **41 条抛穿腿的构成**：9 个函数 × 4 个代理位形态 = 36，加 `static_validate_patch` 3 条
  （代理位锚点 / 代理位 NameError / 围栏+代理位）、`apply_edit_intents` 2 条（代理位锚点 / 围栏+代理位）
  = 41，与逐条点名行逐一对上。**归档 14596 条输入贡献 0 条**——四形态全带 `shape:` 前缀。
  这就是 §7 第 3 条的边界：**抛穿腿在生产语料里没有历史实例**，可达性证据只有形态栅格与单元锁。
- **基线归因核验**（登记前复算）：HEAD 是 BC 收口提交，其下压着 BD→BJ **七轮未提交栈**，
  所以"HEAD-vs-现"必须逐文件确认没混进旧轮次。实测：受比五模块的 HEAD 版对
  `check_status|outcome_sink` 提及 **0 次**（现树 9–16 次）⇒ 这些文件的共享口径接线全属 BK；
  唯一例外是 `deterministic_repair.py` 带着 BG 的键回填（`static_check_status` / `static_check_outcomes`
  = `None`，现 `:284-285`），而它落在 **`build_deterministic_debug_result`**，不在 11 个被比函数之列
  ⇒ 对账项的归因仍限于 BK。

---

## 4. 回归锁（`tests/test_bk_ast_guard_capture.py`，55 例）

| 组 | 例数 | 锁住什么 |
|---|---|---|
| `TestCaptureSurface` | 4 | 四类"读不懂"在 3.14.6 的真实抛出类型（代理位 ⇒ `UnicodeEncodeError`、null 字节 ⇒ `SyntaxError`）；`AST_UNREADABLE_ERRORS` 是族不是名；锁与门禁共用同一常量对象 |
| `TestUnparseableShape` | 7 | 四形态各归各位；`undecodable` 不折进 `syntax`；仅 hunk 头的差异也算 `git_diff`；纯空白算"读得懂"；`parse_error_text` 两类异常都有文案 |
| `TestDeterministicRepairDisclosure` | 6 | 目标码读不懂 ⇒ `target_readability=error` 带形态；候选读不懂 ⇒ `candidate_validation=error`；空目标另有 `disabled` reason；`sink=None` 零开销；返回值逐字不变 |
| `TestCrossFileDisclosure` | 5 | 入口读不懂 ⇒ `entry_readability`，且**不冒充"无依赖"**；反向依赖腿同口径；返回值形状不变 |
| `TestExpertPoolDisclosure` | 5 | 投票归一化腿逐候选记录；聚合取 worst；`ast.dump` 回退不再无标注 |
| `TestPatchIntentDisclosure` | 5 | 原文读不懂 vs 锚点不命中两种拒绝可分；`edit_application` 腿计数口径；返回值不变 |
| `TestMultiCandidateDisclosure` | 9 | `static_validate_patch` 的 `ValueError` 腿**真的会触发**（不是写了个拦不住的 except）；代理位补丁 ⇒ 保守拒绝且披露；单候选读不懂 ⇒ fail-closed 而非崩溃；合成结果腿；三处 `synthesize_candidates` 站点各一条 |
| `TestBjBkReasonCaliber` | 2 | BJ 的 `unparseable_*` reason 词表与本轮同源（不出现第二套词表） |
| `TestPublisherLegs` | 5 | 三个发布点都写 `check_status` + `check_outcomes`；腿为空 ⇒ 聚合 `error`（M3 的方向）；发布的腿是副本不是同一对象 |
| `TestCaptureRatchetGate` | 7 | 现树在登记分母下绿（136/78/20/0/20/19 逐项锁）；新增单腿守卫 ⇒ 违规；超额站点 ⇒ 违规；条目失效 ⇒ 违规；条目偏大 ⇒ 违规；`--all` 面只报告不改退出码；豁免键与 `scan()` 同构 |

---

## 5. 变异验证（`scripts/tools/bk_mutation_verify.py`，13 锚点 + 1 中性对照）

执行口径（一次连续运行，14 个条目，墙钟 54s 由日志时间戳推得）：

- **基线**：未变异树上 `tests/test_bk_ast_guard_capture.py` + 受影响既有文件
  **collected=55 / rc=0 / 0 红**。
- **每个变异体三道检查**：写入前 `compile()` 通过、写入前后 `collect_count` 与基线一致、
  `finally` 里按 sha256 断言原字节还原。**collected 逐锚点 55–104 变化**（锚点附带
  受影响测试文件，如 M8 拉入 `tests/test_process_and_candidate_matrix.py` ⇒ 104），
  这与 BJ 的"collected 全程恒定"是**不同口径**——本轮的每锚点集合是显式声明的，
  因此棘轮只锁"同一锚点变异前后 collected 不变"，不锁跨锚点相等。
- 整轮 **KILLED=13 / 未击杀=0 / 残留=0**（`# bk-mutation` 标记全仓扫描为空），
  运行前后树态 sha256 一致、门禁自测仍 `rc=0`。

| 锚点 | 类 | 变异含义（反向锚点所防的口径） | rc | red | collected | 点名测试（首两条） |
|---|---|---|---|---|---|---|
| M1-capture-surface-narrowed-to-syntax-only | 捕获面 | 共享常量缩回单腿 ⇒ `ValueError` 族重新抛穿 | 1 | **24** | 88 | `TestPublisherLegs::test_edit_intent_publisher_writes_both_keys`、`TestCaptureRatchetGate::test_src_current_state_is_green_at_registered_denominators` |
| M2-shape-undecodable-folded-into-syntax | 归因 | 编码问题记成语法问题 ⇒ 两类成因合一 | 1 | **15** | 55 | `TestPublisherLegs::test_expert_pool_branch_publishes_per_candidate_legs`、`TestPublisherLegs::test_edit_intent_publisher_writes_both_keys` |
| M3-worst-status-empty-default-looks-clean | 聚合 | 一条腿都没记 ⇒ 自称 `ok` | 1 | 1 | 55 | `TestPublisherLegs::test_empty_sink_aggregates_to_error_default` |
| M4-deterministic-target-unreadable-claims-ok | 披露 | 目标码读不懂自称干净 | 1 | 2 | 73 | `TestDeterministicRepairDisclosure::test_unreadable_target_discloses_shape` |
| M5-cross-file-entry-unreadable-claims-ok | 披露 | 入口读不懂自称干净 | 1 | 1 | 100 | `TestCrossFileDisclosure::test_unreadable_entry_returns_empty_and_discloses` |
| M6-expert-pool-normalization-single-leg-restored | 捕获面 | 投票归一化拆回单腿（棘轮必须点名） | 1 | 5 | 68 | `TestPublisherLegs::test_expert_pool_branch_publishes_per_candidate_legs`、`TestCaptureRatchetGate::test_src_current_state_is_green_at_registered_denominators` |
| M7-patch-intent-original-unreadable-claims-ok | 披露 | 原文读不懂自称干净 | 1 | 2 | 79 | `TestPatchIntentDisclosure::test_unreadable_original_but_readable_result_discloses_both` |
| M8-static-gate-value-error-leg-never-fires | 抛穿 | `except ValueError` 换成拦不住的 `UnicodeDecodeError` | 1 | 2 | 104 | `TestMultiCandidateDisclosure::test_static_validate_patch_folds_undecodable_instead_of_escaping` |
| M9-synthesis-result-unreadable-claims-ok | 披露 | 合成结果读不懂自称干净 | 1 | 1 | 64 | `TestMultiCandidateDisclosure::test_single_unreadable_candidate_fails_closed_instead_of_crashing` |
| M10-expert-pool-published-status-hardcoded-ok | 发布 | 聚合值硬写 `ok`（不再来自真实腿） | 1 | 1 | 88 | `TestPublisherLegs::test_expert_pool_branch_publishes_per_candidate_legs` |
| M11-expert-pool-published-legs-emptied | 发布 | 只留聚合不留腿 ⇒ 无法逐腿核对 | 1 | 1 | 88 | 同上 |
| M12-ratchet-covers-predicate-always-true | 棘轮 | "任何 handler 都算覆盖"⇒ 空转 | 1 | **5** | 55 | `TestCaptureRatchetGate::test_over_quota_site_inside_exempted_function_is_caught`、`test_gate_covers_every_exempt_key_with_a_real_site` |
| M13-ratchet-exempt-quota-unenforced | 棘轮 | 额度不参与判定 ⇒ 超额站点静默放行 | 1 | 1 | 55 | `TestCaptureRatchetGate::test_over_quota_site_inside_exempted_function_is_caught` |
| N0-neutral-comment-wording-only | 对照 | 仅改注释措辞，不动判据 | **0** | **0** | 55 | —（0 红 = 没把无关文本写进判据） |

两张最宽的网：

- **M1（24 红）**把常量缩回单腿，除新锁外同时打掉既有 `tests/test_multi_candidate.py`
  ——**"捕获面"这一条不只由新文件守着**；
- **M12（5 红）**让棘轮判定恒真，首个点名的是"每个豁免键都必须有真实站点命中"，
  说明门禁**自己的自检面**也在锁里（否则门禁红、测试绿是不可发现的假绿）。

---

## 6. 踩坑与自纠（本轮实测发生的，不是设想）

1. **开工普查的口径不可复现，且与守卫口径不同**（第一贵）。普查脚本报
   "全仓 125 站点 / 64 单腿 / src 35"，第二版同一棵树报 **60** 单腿（差 4：两版对
   `except Exception`、裸 `except`、`except _PARSE_ERRORS`、`except _Untranslatable|Exception`
   的算法一致，但对 `experiments/analyze_t1_b2_main_batch.py:83` 与
   `scripts/tools/bj_discriminator_crosscheck.py:48` 的归类不同）。守卫按 **try 站点**计、
   按"能否接住整个 `ValueError` 族"判，得到 `src/` **78 / 35**（HEAD）与 **78 / 20**（现树）。
   **处置**：普查数字不进登记，守卫 docstring 写明"以本守卫自测数为准"，差值不强行归因。
   教训：**同一棵树有两套分母时，登记的必须是"能被别人复算的那一套"**，而不是最早跑出来的那套。
2. **HEAD 不等于"本轮之前"**。判定不变性对账以 `git show HEAD:` 为基线，但 HEAD 是 BC 收口提交，
   其下压着 BD→BJ **七轮未提交栈**；不逐文件核实就把旧轮次的改动当本轮差异（或反过来）。
   本轮的核验法（可复算）：受比模块的 HEAD 版 grep `check_status|outcome_sink` 命中 **0 次**，
   现树命中 9–16 次 ⇒ 共享口径接线全属 BK；唯一混入项（BG 的 `static_check_*` 键回填）
   按函数名定位到**未参与对账**的 `build_deterministic_debug_result`。**凡用 Git 当"改前基线"，
   都要先证明基线里没夹带别人**。
3. **第一版对账脚本比"摘要"而不是比"值"，把噪声读成 1343 项缺陷**。那一版把 920 份仓内 `.py`
   当输入、跨进程打印 16 位摘要比对，输出 `UNEXPECTED = 1343` 且含 `both_raised = 1`
   （`UnicodeEncodeError->KeyError: ['cross_validate']`——调用面少传参）。对其中一条被点名项
   （`_top_level_names` @ `config.py`）做最小复现（同一输入分别 exec HEAD 函数体与现函数体、
   同进程比 `repr`）⇒ **identical**。处置：输入面改为"形态栅格 + 归档代码串"、比较改成同进程
   `repr` 原文、把 `cross_validate` 的调用面写对（`object.__new__` + 显式 kwargs），
   最终 `both_raised = 0 / UNEXPECTED = 0`。该版脚本已删除，机制无法逐行复核，
   因此这里只登记**可复核的两点**：被点名项最小复现相同、现行口径归零。**口径**：
   跨进程/跨版本比摘要的对账，随机化会把噪声读成缺陷；对账必须同进程、比值本身。
4. **Prompt Card 被本轮自己的 +19 行打断**（唯一一条真实失败）。BK 在
   `src/agents/debugger.py:683-693` 的接线插在卡 §3 已登记调用点 643 与 744 **之间**，
   行号整体后移 ⇒ `tests/test_prompt_artifacts_gate.py::TestPromptCard::test_repo_card_is_current`
   转红（`make test-cov` 里第二条失败）。`make prompt-artifacts` 重生成后该文件 21 例全绿。
   **口径**：改任何"卡里登记了行号"的源文件，必须同批重跑生成器；这条门只在全量跑与
   `make gates` 里咬人，定向跑不出来。
5. **基线守卫按惯例转红**（登记滞后，非产品缺陷）：`BASELINE.yaml` 当时仍写 11617，
   实收 collected 11677 ⇒ 差 **60 > 6** 容差（守卫比 collected，与 BJ 的 68 同口径——
   **不要**用 passed 11670 减出 53 这种"看着更小"的数）。pass 1 刷新后归零。
6. **`both_raised` 是这类对账的天然盲区**：新旧两侧同样 `TypeError` 会被读成"等价"。
   本轮把它**单独计数并打印异常种类**（`both_raised = 0`），而不是塞进 `identical`——
   整批同类就是调用面写错的信号（§6 第 3 条那次 `KeyError` 就是这么露出来的）。
7. **变异 harness 与只读探针严格串行**（沿用 BJ 的口径，本轮留了时间戳证据）：
   判定不变性对账 05:46:21→05:47:25，变异验证 05:47:25→05:48:19，**两次运行首尾相接、
   无重叠**；对账必须在"未变异树"上跑，否则 import 到变异体（BJ 已实测过一次假读数）。
   本轮还额外做了**运行后残留扫描**（`# bk-mutation` 全仓命中 0）与门禁自测复跑（`rc=0`）。
8. **zsh 的三条口径本轮各踩一次**：(a) 未匹配的 glob 让**整条命令行**中止
   （`ls /tmp/bk_*.log /tmp/*bk*.txt` 因第二段无匹配而什么都没列出，第一轮排查据此误判"日志没了"）；
   (b) `${PIPESTATUS[0]}` 在 zsh 里不可用 ⇒ 长输出落文件再 `grep`，退出码取 `rc=$?`；
   (c) **zsh 默认不对变量做词分割**——`FILES="a.py b.py …"; pytest $FILES` 把整串当成一个路径，
   得到 **collected 0 items**（不是"测试全过"，是**一条也没跑**）。本轮复算邻近面时先中了这条，
   改成把文件名直接写进命令（或 `$(...)` 现展）才拿到 collected 644。**0 collected 必须是失败**，
   不能读成"这一组没影响"。

---

## 7. 边界与未收口部分（按名登记，不写成"已排除"）

1. **20 处折叠站点未收敛**，改为 `EXEMPT` 额度按名登记（19 条 / 20 站点，形态见 §2.2）。
   它们的共同点是折叠方向已经保守（拒绝 / 降级 / 缺位），缺的是"披露"，
   需要各自的腿名与 reason 设计——一轮做完 20 处会把"判定不变"的承诺稀释成 20 个判据改动。
2. **`experiments/` + `scripts/` 的 169 文件 / 45 站点 / 26 未覆盖只报告不阻断**。
   分析侧不是 `src/` 生产判定面；把它们接进阻断口径需要另定"研究脚本的读不懂该不该红"。
3. **`ValueError` 族腿在归档语料 0 实例**（14596 条输入贡献 0 条抛穿腿）。
   可达性证据只有形态栅格 + 单元锁；不能把 §1.1 的表读成生产频率。
4. **`specs/spec_smt.py:534 / :748` 的 `_Untranslatable|Exception`**：守卫按"能接住 `Exception`
   即合格"放行，但其语义是"翻译不可用"而非"读读懂不懂"，**没有**并入 AST 披露通道。
5. **`parses_as_module()` 与直调 `ast.parse(code)` 的 mode 口径未统一**：前者按 module 解析、
   某些消费点历史上按表达式解析。本轮只在守卫处沿用 `parses_as_module`，未全量核对 78 站点。
6. **`outcome_sink=None` 是默认**：不传 sink 的调用面零开销，但**也不产生任何读数**。
   本轮只保证三个发布点传了 sink；其余调用点（含分析脚本）仍是"静默保守"。
7. **门禁的红只覆盖 `src/`**：新增单腿守卫若写在 `experiments/`，本轮不会拦（见第 2 条）。
8. **棘轮的"折叠形态"是文字登记，不是机器判据**：`EXEMPT` 的第二元描述形态，
   门禁只校站点数与命中数，不会验证"这里折出来的真是 `[]`"。

---

## 8. 复算命令（零 LLM、零写入、可逐条重跑）

```bash
# 1) 本轮 55 例新锁（先看 collected=55，再看 rc）
.venv/bin/python -m pytest tests/test_bk_ast_guard_capture.py -q --collect-only -o addopts="" | tail -2
.venv/bin/python -m pytest tests/test_bk_ast_guard_capture.py -q -p no:cacheprovider

# 2) 邻近面（多候选 / 专家池 / 交叉文件 / debugger 分支 / 工作流，23 文件 **collected 644**）
.venv/bin/python -m pytest tests/test_2026_09_26_review_optimizations.py \
  tests/test_branch_coverage_fill.py tests/test_branch_coverage_gates.py \
  tests/test_closeout_k_multi_candidate.py tests/test_debugger_node_branches.py \
  tests/test_e2e_probes_workflow.py tests/test_error_classifier_combinations.py \
  tests/test_error_classifier_new_categories.py tests/test_experiments_ab_scaffolds.py \
  tests/test_expert_pool.py tests/test_g8_g2_g4_g5_g6_g7_g1.py tests/test_multi_candidate.py \
  tests/test_multi_candidate_batch13.py tests/test_multi_candidate_branches.py \
  tests/test_multi_candidate_synthesis.py tests/test_nodes_j4_patch_applier.py \
  tests/test_nodes_refactor_20261019_contracts.py tests/test_observability_enhanced.py \
  tests/test_patch_localized.py tests/test_process_and_candidate_matrix.py \
  tests/test_roadmap_gaps.py tests/test_strategy_bank.py tests/test_workflow_extended.py \
  -q -p no:cacheprovider
#    注意：zsh **不做词分割**——把上面这串文件名先存进变量再 `$FILES` 展开，会得到
#    "collected 0 items"（整串被当成一个路径）。本轮实测踩过，见 §6 第 8 条。

# 3) 捕获面棘轮自测：现树（应 rc=0，136/78/20/0/20/19）
.venv/bin/python scripts/gates/check_ast_parse_guards.py

# 3b) 同一把尺子量 HEAD 导出（应 rc=1、未覆盖=35、违规=15 = BK13 + BJ2）
rm -rf /tmp/bk_head_verify && mkdir -p /tmp/bk_head_verify/scripts/gates
cp -R /tmp/bk_head/src /tmp/bk_head_verify/ && cp src/utils/check_status.py /tmp/bk_head_verify/src/utils/
cp scripts/gates/check_ast_parse_guards.py /tmp/bk_head_verify/scripts/gates/
.venv/bin/python /tmp/bk_head_verify/scripts/gates/check_ast_parse_guards.py

# 3c) 仅报告面（experiments/ + scripts/）
.venv/bin/python scripts/gates/check_ast_parse_guards.py --all | tail -1

# 4) §3.2 判定不变性对账（必须在干净树上跑，禁止与变异验证并行——见 §6 第 7 条）
.venv/bin/python scripts/tools/bk_judgment_invariance.py

# 5) §5 变异验证：13 锚点 + 1 中性对照（会临时改写 src/，finally 按 sha256 还原）
.venv/bin/python scripts/tools/bk_mutation_verify.py            # 全量
.venv/bin/python scripts/tools/bk_mutation_verify.py M1 M8 M12  # 单锚点复跑
# 中止过就必须扫残留，再看门禁自测：
grep -rn "# bk-mutation" src/ scripts/ ; .venv/bin/python scripts/gates/check_ast_parse_guards.py

# 6) 门禁链（最后、单独跑，不要接管道——见项目口径）
start=$(date +%s); make gates > /tmp/bk_gates.log 2>&1; rc=$?; echo "rc=$rc elapsed=$(( $(date +%s) - start ))s"
```

---

## 9. 收口批注（2026-10-22）

- 登记前（含 `--cov`，走 `make test-cov`）一跑：**11670 passed / 2 failed / 5 skipped、
  31 warnings、196.40s**（collected **11677**，4 workers；链外 `rc=2`，`make: *** [test-cov]
  Error 1`；墙钟 198s 由日志时间戳推得）。两条失败点名：① 基线守卫
  `tests/test_2026_10_10_optimization_batch.py::TestBaselineNumbersConsistency::test_tests_and_mypy_are_current`
  （`BASELINE.yaml` 当时仍写 11617，实收 collected 11677 − 声明 = **60 > 6** 容差）；② Prompt Card 陈旧
  `tests/test_prompt_artifacts_gate.py::TestPromptCard::test_repo_card_is_current`（§6 第 4 条）。
  除这两条外零失败——"判定没动、只补披露"的第一层证据。
- 覆盖率登记口径：**19363/19874 行 = 97.4300%**、**7093/7520 弧 = 94.3200%**（取 `coverage.xml`
  root 的 `lines-covered/lines-valid`、`branches-covered/branches-valid` 复算；终端 `TOTAL` 行的
  合并口径不可当登记值）。分母 +81 行 / +16 弧、覆盖 +91 行 / +21 弧 ⇒ 未覆盖 **521 → 511（−10）**、
  缺弧 **432 → 427**。两者都**超出既有 ±2 行抖动域**，按改善登记但**不作逐行/逐弧回收主张**：
  新增判定路径自身被锁执行是 −10 的下界来源，历史缺行未逐行定位，"至多回收 5 条历史偏弧"
  这类换算不写。十项核心模块逐文件复算 **2 项变动**（`multi_candidate` 296/300 → **311/313 = 99.36%**、
  `cross_file` 278/299 → **293/309 = 94.82%**，两者分母都因本轮 sink 参数与披露分支增长），其余 8 项逐位相同；
  三项核心路由分支 **0 变动**（graph_workflow 119/120 = 99.17 / error_classifier 110/114 = 96.49，
  键为 `agents/error_classifier.py` / graph_state 2/2 = 100.00）。
- 逐文件（同一次登记前跑，`--cov-branch`）：`src/utils/check_status.py` **65/65 行 + 22/22 弧 = 100%**
  （BI 43/18 → BK 65/22，本轮上收的四个共享函数无一未覆盖）；`src/tools/multi_candidate.py`
  **311/313 行**、弧 **117/124 = 94.35%**；`src/tools/cross_file.py` **293/309 行**、弧
  **123/140 = 87.86%**；`src/tools/patch_intent.py` **63/63 行 + 18/18 弧 = 100%**；
  `src/graph/expert_pool.py` **181/198 行**、弧 **47/60**；`src/tools/deterministic_repair.py`
  **113/114 行**、弧 **42/44**。**未覆盖行与本轮新增行的交集为空**（按 `git diff -U0` 逐文件核对）：
  `multi_candidate` 缺行 800 / 832、`deterministic_repair` 153、`cross_file` 含 303 / 691 / 771 / 808
  共 16 行、`expert_pool` 含 272 / 517 / 529–530 / 558 共 17 行——**全部是改前既有分支**。
  `graph_nodes` 851/852 与 `oracle_validator` 128/134（缺行 261 / 269 / 332 / 370 / 375 / 413）与 BJ 逐位相同。
- 确认跑（无 `--cov`，单独执行、不与其他 pytest / 文档编辑重叠）：xdist `-n 4 --dist loadfile`
  **11672 passed / 5 skipped / 0 failed、191.76s、rc=0**（collected **11677** = 11672 + 5 + 0，
  与登记前同一采集面；45 warnings；墙钟 192s）。**串行对照本轮未重跑**——BJ 已实测同一棵树
  （11622 items）串行 521.41s vs xdist 192.77s，2.7 倍差完全来自并行度，故引用本轮用时时
  必须写明"xdist 4 worker"，不可与串行值互比。
- 变异与对账两份读数的采集次序见 §6 第 7 条（时间戳首尾相接，全轮 `# bk-mutation` 残留 0）。
- 静态面：`ruff check .` 全过；mypy `Success: no issues found in 137 source files`（与 BJ 同值，
  本轮未在 `src/` 新增文件——门禁脚本在 `scripts/gates/`，不在 mypy 扫描面）。
- **`make gates` 首跑**：**rc=0**、墙钟 **242s**（`date +%s` 在同一 shell 里成对采集：
  `1792621829` → `1792622071`）。这与上面 192s 那种「由日志创建→末次写入时间戳推得」的墙钟**不同源**，
  所以本条可以作用时主张，上一条只能作旁证。链内 pytest（xdist `-n 4 --dist loadfile`、不带 `--cov`）
  **11672 passed / 5 skipped / 0 failed、193.90s (0:03:13)**，collected **11677**（与确认跑同一采集面）、
  **47 warnings**。
- 链共 **18 步命令 / 16 个 make 目标**（`docs-check` 与 `baseline-check` 各含 2 个脚本），逐步读数：
  `ruff check` 全过；`ruff format --check` **970 files already formatted**；mypy **137 source files** 零问题；
  双语 `--strict` **0 警告 / 0 失败**；文档链接 `--strict` **179 份 / 838 条 / 0 错误 0 警告**；
  env-budget **253/253**；BASELINE 结构 + 数字漂移两检通过；状态通道 **136 文件**无未声明键读写；
  env-snapshot **84 开关 / 缺失 0 / 豁免 0**（快照 115 键）；model-fingerprint「近期无新批次可验」
  （S29 口径，不是跳过）；工具版本 OK（mypy 1.15.0 / ruff 0.16.3）；JSON 契约**口径 A 7/7 +
  文档表述 9 处全 `[OK]`**；严格 JSON **7274 份 = 7272 严格 + 2 历史截断豁免 + 0 违规 /
  304 份源码写入点 0 违规**；三臂工件对账 `[OK]` + T-10 严格 29 行 / 25 可测（宽松 62 / 55）+
  **登记册覆盖率对账 `[OK]`（容差 ±0.20pp）**；零断言 **455 份测试文件 / 0 违规**（BJ 454 → +1 = 本轮锁文件）；
  本轮新门 `ast-guards` **136 文件 / 78 站点 / 未覆盖 20 / 违规 0 / 豁免命中 20 / EXEMPT 19 ⇒ PASS**。
  **链内这条门禁读数与 §3 的链外自测逐位相同**——同一棵树、同一把尺子、两个独立进程，这是本轮棘轮
  能接 CI 阻断的最小证据；链内它没有因 §8 的 HEAD 导出复测而改变（那是一次链外操作）。
- **45 ↔ 47 warnings 属抖动，不是本轮新增**：确认跑与链内两跑的 warnings summary 逐行 `diff`，
  唯一差异是 `tests/test_spec_expr_property.py::test_compilable_implies_expression_form` 的
  `<unknown>:2: SyntaxWarning: invalid decimal literal` 两条（hypothesis 反例输入决定，worker 分发影响
  其是否进汇总），其余逐项相同。登记口径固定取**确认跑 45**；链内 47 只记录、不换算成「新增警告」。
- **链内 193.90s 与确认跑 191.76s 之差 +2.14s** 是同并行度、同采集面下的抖动，不作主张；两值都
  **不可**与串行口径互比（§6 第 6 条）。本册的分步读数行数口径写明为 **47 行** = pytest 汇总行之后、
  非空、非命令回显（`.venv/bin/python scripts/gates/…` 14 行）、非 `# ` 注释（3 行）、并去掉链尾那行由
  命令包装写出的 `rc=0` 标注（它是退出码，不是某个门禁自己的输出）。BJ 册记的 88/90 行用的是另一套
  过滤规则（含 pytest 段内的读数行），两个行数**定义不同、不可互比**，本册不据此声称「比 BJ 少 41 行」。
- **终跑（上面那条首跑读数落盘、双语 README / CHANGELOG / INDEX / 登记册 / BASELINE 的门禁句
  全部回填之后，再单独跑一次 `make gates`，不与其他 pytest / 文档编辑重叠）**：**rc=0**、墙钟
  **198s**（同一 shell 里 `date +%s` 成对采集：`1792622592` → `1792622790`）、链内 pytest
  **11672 passed / 5 skipped / 0 failed、192.95s (0:03:12)**（**44 warnings**；`4 workers
  [11677 items]`，与首跑同一采集面）。两跑之间**只有 pytest 段动过**：链尾 47 行门禁分步读数
  **逐字节相同**（`difflib` 原始 diff **0 行**，连归一化都不需要）；链首 6 行（`ruff check` /
  `ruff format --check` / mypy 三对）也逐字节相同；日志从汇总行往前少 4 行（23399 → 23395）、
  warnings 47 → 44，两处差额同源——`tests/test_spec_expr_property.py` 的 hypothesis
  `SyntaxWarning: invalid decimal literal` 组由 39 条变 38 条，外加它的重复标题行。
- **三跑 warnings 定档**：确认跑 45 / 首跑 47 / 终跑 44，采集面恒为 11677、pass/skip 恒为
  11672/5。所以 warnings **不参与任何登记主张**，登记口径固定取确认跑；三跑之间可比的是
  采集面、pass/skip 与门禁分步读数，不可比的是用时与警告计数。
- 本节写入之后，剩下的改动只有双语 / 登记册 / BASELINE 里这同一句终跑读数；它由文档锁子集
  （`check_bilingual_docs --strict`、`check_doc_links --strict`、`check_baseline`、
  `check_baseline_numbers`、`tests/test_markdown_table_integrity.py`、`tests/test_ao_batch.py`）
  复验，**不再另起门禁链**——本节的每个 rc / 用时都来自已经发生的链。
