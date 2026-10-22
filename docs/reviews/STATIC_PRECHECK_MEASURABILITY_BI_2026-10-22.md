# BI 轮：写盘前静态预检的「读不懂 ⇒ 通过」收口（2026-10-22，零 LLM）

**范围**：`src/tools/patch_applier.py` 的两道写盘前守卫——`check_naming_contract`
（P0 1.3 命名契约符号守卫）与 `dangerous_api_added`（S2 危险 API AST 差集）——及其
三个消费点：`src/graph/nodes.py::_check_patch_safety`（真实调用方）、
`_patch_applier_node`（状态通道发布）、`src/tools/type_repair.py::type_repair_layer`
（LLM 修订后的契约回环）。词表与聚合函数上收为单一事实源
`src/utils/check_status.py`。

这是 F03 静态侧的第 6 个形态：BD/BE/BF/BC 收口的是 pytest 的 `rc==0`，BG 收口的是
外部检查器的**空 findings**，BH 收口的是校验层的 `passed=True`，本轮收口的是
**守卫的空结果**——`missing=[]` / `added=[]` / `contract_ok=True` 同时是"比较过且没有
问题"和"根本没读懂输入、从未比较"的返回值。

**结论**：两守卫新增可选 `outcome_sink`，逐条追加 `{check, status, reason}`（status
四值 `ok / disabled / unavailable / error`，与 BG/BH 词表逐字一致）；
`_check_patch_safety` 以 **worst-of** 聚合写入状态通道 `safety_check_status` /
`safety_check_outcomes`；`type_repair_layer` 补 `contract_status` /
`contract_reason` / `contract_outcomes`。**判定值与判定方向逐字节不变**——本轮只把
沉默翻成披露，不把 fail-open 翻成 fail-closed（方向变更会连带改写历史读数语义）。
**50 例新锁 + 变异 19 锚点全红（4/2/1/5/1/5/1/1/4/4/1/2/1/1/1/2/1/4/7）+ 中性对照
0 红**（collected 全程 **452**、sha256 原字节还原）。

---

## 1. 缺陷：空结果的四义与三条假陈述（改前实测）

改前读数取自 `git show HEAD:src/tools/patch_applier.py` 的直接调用（Python 3.14.6，
非推断）；"生产消费点"一行取自 `git show HEAD:src/graph/nodes.py` 的
`_check_patch_safety`：

| 输入形状 | 改前返回 | 问题 |
|---|---|---|
| 原文 py2 `print` 语句（当前解释器不接受）+ 补丁删除模块级常量 `CONST` | `check_naming_contract` → `(True, [])`；`dangerous_api_added` → `[]` | **假干净主锚点**：原符号集为空 ⇒ 从未做过比较，却返回"契约通过" |
| 同上，经真实消费点 `_check_patch_safety` | `applied=True`、落盘代码 `CONST` 已消失、**零条 warning**、`contract_missing_symbols` 保持 `null` | 生产可达：读不懂 ⇒ 写盘，读数与日志都不区分 |
| 原文可解析且含模块符号 + 补丁无法解析（空字节） | `(False, ['CONST', 'f'])` + `命名契约检查失败：补丁删除了 2 个模块级符号 ['CONST', 'f']` | **误归因假陈述**：补丁从未被解析成 AST，"删除"实为"无法确认仍存在"；该文本经 `contract_missing_symbols` 与 1.3 降级链进读数 |
| 原文零模块符号 + 补丁无法解析 | `(False, ['x'])` + `补丁删除了 1 个模块级符号 ['x']` | 同上（旧实现在 `original_symbols` 非空分支里才看不见解析失败） |
| 两侧都读不懂 | `(True, [])` | 与"比较过且无删除"同值 |
| `PATCH_CONTRACT_CHECK=false` | `(True, [])` | 恒放行与"比较过"同值（第 4 义） |
| 任一入参为空串 | `(True, [])` / `[]` | 恒放行，同样无状态维度 |
| 原文读不懂 + 补丁含 `os.system` | `dangerous_api_added` → `['os.system']` | **过度拦截**（保守方向）：基准危险集退化为空 ⇒ 补丁全部命中都算"新增"，也未披露 |

`dangerous_api_added` 与命名契约共用"解析失败 ⇒ 空集"的假设，旧 docstring 称"由
`safe_apply_patch` 的语法校验兜底"——该前提**只在本地链路成立**（G 轮已就同一前提在
repo 片段链路修过一次同型缺陷）。无语法闸门的调用方（如 testless 导入冒烟预检）会把
"读不懂补丁"直接读成"无新增危险 API"。

## 2. 处置：可测量性三态 + 最差者优先 + 通道发布

### 2.1 词表与聚合方向（为什么与 BG 同词表、不同聚合）

| status | 含义 | 空结果可否作"预检通过"的证据 |
|---|---|---|
| `ok` | 两侧都读得懂、比较确实发生 | **可以** |
| `disabled` | 按设计未检查（`PATCH_CONTRACT_CHECK=false` / 入参为空） | 不可以 |
| `unavailable` | 依赖缺席（本轮两守卫是纯标准库 AST ⇒ **不产生该通道**，词表保留以对齐 BG/BH） | 不可以 |
| `error` | 跑了但没读懂输入（`unparseable_original` / `unparseable_patched` / 契约回环异常） | **不可以** |

聚合方向由**结果之间的关系**决定，不能照抄上一轮：

- `_check_patch_safety` 的两道守卫彼此独立 ⇒ **worst-of**
  （`CHECK_STATUS_PRECEDENCE = error > unavailable > disabled > ok`）；
- `type_repair` 的 mypy / pyright 是同一检查的可替换后端 ⇒ **any-ok**
  （BG 口径，`any_measurable_status`，逐字保持不动）。

两个聚合器对**缺省值**的不对称同样是刻意的：`worst_check_status` 空输入与未知
status 都落 `error`（读不懂按不可测量处理，fail-closed），`any_measurable_status`
落 `disabled`（BG 历史口径，本轮以变异 M12 锁住"不得丢失 ok 短路"，不得顺手统一）。

### 2.2 逐点判定

| 路径 | status | reason | 返回值（判定） |
|---|---|---|---|
| 契约 / `PATCH_CONTRACT_CHECK=false` | `disabled` | `patch_contract_check_disabled` | `(True, [])` 不变 |
| 契约 / 任一入参为空 | `disabled` | `empty_input` | `(True, [])` 不变 |
| 契约 / 原文读不懂 | `error` | `unparseable_original` | `(True, [])` 不变 + warning 点名"未做任何符号比较，保守放行" |
| 契约 / 补丁读不懂 + 原文零符号 | `error` | `unparseable_patched` | `(True, [])` 不变 + warning |
| 契约 / 补丁读不懂 + 原文有符号 | `error` | `unparseable_patched` | `(False, missing)` 不变，但文本改为"无法确认仍存在…未做任何符号比较"（**误归因收口**） |
| 契约 / 原文可解析但零模块符号 | `ok` | `no_module_level_symbols` | `(True, [])`（此时"无可删符号"是真证据） |
| 契约 / 正常比较 | `ok` | — | 按差集 |
| 危险 API / 任一入参为空 | `disabled` | `empty_input` | `[]` 不变 |
| 危险 API / 任一侧读不懂 | `error` | `unparseable_patched`（fail-open 侧）/ `unparseable_original`（过度拦截侧） | 差集不变 |
| 危险 API / 正常比较 | `ok` | — | 差集不变 |
| 消费点 / 聚合非 ok | — | — | `safety_check_status` + warning `写盘前静态预检可测量性降级（整体 status=…）` |
| type_repair / 未走到契约回环 | `disabled` | `contract_not_evaluated` | `contract_ok` 口径不变 |
| type_repair / `enforce_contract=False` | `disabled` | `contract_enforcement_disabled` | 同上 |
| type_repair / 回环抛异常 | `error` | `contract_check_exception` | 保守保留原补丁，不变 |

### 2.3 行为差异与连带改动

- **只补披露**：`outcome_sink=None` 时两守卫零开销、返回契约逐字节不变；`patch_applier`
  对外签名向后兼容。
- **新状态通道**：`safety_check_status` / `safety_check_outcomes` 在
  `src/graph/state.py` 的 TypedDict 与 `create_initial_state` 显式声明（默认 `None` =
  本轮未执行）。LangGraph 会静默丢弃未声明键（M14），故两键必须入声明——`M14` /
  `M15` 两个变异就是钉这一点的。
- **读取规则**：`status ∈ {error, disabled}` 时 `missing_symbols` 为空集**不等于**
  "契约成立"；`contract_ok=True` 单独不构成契约证据，必须与 `contract_status` 配对读。
- **边界（不改）**：`safe_apply_patch:454` 的 `except SyntaxError` 兜底、重采样路径
  的两处 `_ck` 调用（无 sink，不可测量时保守 `return None` = 过度拒绝方向）、
  testless 层内 352/394 两处不接 sink——均为既有口径，本轮只登记不重写。

## 3. 真语料测量（本轮重测，非沿用笔记）

- `experiments/results` 下 `.json` **1702** 份，其中 **1594** 份可 `json.loads`；
  108 份不可解析的是 `_superseded_20261010/.../json_testcases/*.json` 逐行 JSON 夹具
  （报错形如 `Extra data: line 2 column 1`），不是损坏工件。
- `contract_missing_symbols`：**172** 份文件、**8865** 处取值 = **8853** 个 `null` +
  **12** 个非空列表 + **0** 个空列表（grep 直读得 8868 处，多出的 3 处落在上述 108 份
  JSONL 内）。⇒ **8853 个 `null` 正是四义折叠在历史读数里的足迹**：改前它们同时表示
  "比较过且无符号被删"、"原文读不懂从未比较"、"补丁读不懂但原文零符号"、"开关关闭
  恒放行"。
- `PATCH_CONTRACT_CHECK` / `PATCH_DANGEROUS_API_GUARD` 在归档 JSON 出现 **0** 处
  ⇒ 历史批次两道守卫都取默认开，本轮新增的 `disabled` 通道在历史工件里无对应读数。
- `safety_check_status` / `safety_check_outcomes` 出现 **0** 处（本轮新键）。
- 归档**不保存补丁前原文**：`target_code` 仅 **1** 处、`patch` **11101** 处
  ⇒ 无法从工件重算"哪些 `null` 属于从未比较"⇒ **历史读数零回填**（要区分只能前向
  用新通道）。

## 4. 回归锁

`tests/test_bi_static_precheck_unmeasurable.py`（**50 例**，含参数化展开）：

- `TestVocabularySingleSource`（7）：BG / BH / BI 三层词表常量与优先级元组**逐字
  相同**、聚合方向互不相同是设计、两个聚合器各自复现 `type_repair` 与 testless 的
  历史判据（防止下一轮"顺手统一"）；
- `TestParsabilityOracle`（6）：`parses_as_module` 把 `SyntaxError` 与 `ValueError`
  同归"读不懂"；空字节在 3.14.6 实测属 `SyntaxError`（不是 `ValueError`）；
  孤立代理位走 `UnicodeEncodeError`（`ValueError` 子类）；空源码可解析；
  `unparseable_side` 原文侧优先；与 testless 私有同型 helper 逐位等价；
- `TestDangerousApiGuardStatus`（8）：sink 缺席形状不变、空输入 `disabled`、
  fail-open 侧 / 过度拦截侧 `error`、正常比较 `ok`、**判定不变锁**（按 HEAD 公式在
  测试内逐字重写旧实现，对语料集逐对新旧 diff）；
- `TestNamingContractStatus`（11）：四义各自 status/reason 分离、误归因文本收口
  （`caplog` 断言不得再出现"补丁删除了 N 个模块级符号"）、
  `no_module_level_symbols` 为 `ok`、开关关闭为 `disabled`、判定不变锁；
- `TestCheckPatchSafetyOutcomes`（6）：真实消费点三种形状（原文盲 / 补丁盲 / 干净
  对照）+ 降级 warning 逐条点名 `check=status:reason` + 独立守卫按最差者优先；
- `TestStateChannel`（4）：`create_initial_state` 两键默认 `None`、节点在原文盲时
  发布 `safety_check_status="error"` 与两条 outcomes、判定不变时仍发布；
- `TestTypeRepairContractDisclosure`（7）：默认值是 `disabled` 而非 `ok`、
  `enforce_contract=False` ⇒ `contract_enforcement_disabled`、回环异常 ⇒ `error` 且
  仍保守保留原补丁、原文盲时 `contract_ok=True` 被点名"不构成契约证据"；
- 模块级 1 例：`safe_apply_patch` 对新引入危险 API 仍回滚（S2 判定方向未被本轮
  披露改动削弱）。

按新口径改写既有断言：**0 条**（`tests/test_patch_applier*` 与
`tests/test_type_repair*` 系列的旧断言锁的是判定值，判定值未变，全部原样通过）。

## 5. 变异验证

`scripts/tools/bi_mutation_verify.py`：**19 锚点 + 1 中性对照**，受影响面 13 个测试
文件。纪律同 BG→BH：干净副本先全绿（`rc=0 red=0`）、collected 全程 **452**、逐锚点
`compile()` 通过才写盘、跑完按 sha256 校验原字节还原（**不用 git checkout / git
stash**，工作区有 19 份未跟踪文件与数百未提交改动）。

| 锚点 | 红 | 被谁抓住（节选） |
|---|---:|---|
| M1 原文盲当作可测量（去 `error` 记录） | 4 | `TestCheckPatchSafetyOutcomes::test_downgrade_warning_names_every_check`、契约回环披露锁 |
| M2 补丁盲拒绝当作可测量 | 2 | `test_patched_blind_with_symbols_rejects_without_misattribution`、shape B |
| M3 补丁盲仍写成"补丁删除了 N 个符号" | 1 | `test_patched_blind_with_symbols_rejects_without_misattribution` |
| M4 原文盲并进"零模块符号"分支 | 5 | 消费点点名锁 + 契约回环锁 |
| M5 `no_module_level_symbols` 归因丢掉 | 1 | `test_no_module_level_symbols_is_measured_pass` |
| M6 危险 API 读不懂不披露 | 5 | shape B + 降级 warning 点名 |
| M7 危险 API 空输入记成 ok | 1 | `test_empty_input_is_disabled_not_ok` |
| M8 契约开关关闭记成 ok | 1 | `test_switch_off_is_disabled` |
| M9 可解析性只捕 `SyntaxError` | 4 | 两守卫的判定不变锁（语料含 `ValueError` 形状） |
| M10 优先级改成 ok 优先 | 4 | 词表单源锁 + `test_independent_checks_aggregate_as_worst` |
| M11 未知 status 默认 ok | 1 | `test_worst_reproduces_testless_layer_aggregation` |
| M12 `any_measurable_status` 丢 ok 短路（BG 口径漂移） | 2 | `test_aggregation_directions_differ_by_design`、BG 复现锁 |
| M13 消费点降级不发 warning | 1 | `test_downgrade_warning_names_every_check` |
| M14 通道两键不发布 | 1 | `TestStateChannel::test_node_publishes_channel_on_blind_original` |
| M15 `create_initial_state` 默认值删掉 | 1 | `test_initial_state_defaults_none` |
| M16 `contract_status` 默认写成 ok | 2 | `test_defaults_are_disabled_not_ok`、`test_enforcement_off_is_disabled_not_ok` |
| M17 回环异常不披露 | 1 | `test_guard_exception_is_error_and_still_conservative` |
| M18 **判定翻转**：原文盲改成拒绝 | 4 | 消费点 shape A + 契约回环"判定仍成立"锁 |
| M19 **判定翻转**：危险差集丢掉基准 | 7 | `TestDangerousApiAdded::test_safe_apply_allows_preexisting_dangerous_calls`、`TestFromImportAliasBypassGuard::test_preexisting_from_import_call_not_flagged_as_new` |
| M20 中性对照（仅注释措辞） | **0** | 必须存活 |

复跑（代码内 BI 标签推进到 2026-10-22 之后）与登记逐字一致：baseline
`rc=0 red=0 collected=452`、19 锚点 4/2/1/5/1/5/1/1/4/4/1/2/1/1/1/2/1/4/7、
M20 存活 0 红、脚本 `rc=0`、墙钟 **181s**、sha256 还原断言全部通过。

## 6. 踩坑与自纠

- **docstring 写错被自己实测纠正**：`parses_as_module` 捕获 `(SyntaxError,
  ValueError)`，初版注释称"空字节按 `ValueError` 落在这里"。3.14.6 实测：空字节是
  **`SyntaxError`**（`source code string cannot contain null bytes`），真正能走到
  `ValueError` 分支的是**孤立代理位**源码（`UnicodeEncodeError`，`ValueError` 子类）。
  判据：**注释里的异常类型也是断言**，落笔前直接 `ast.parse` 试一遍。
- **三条测试期望错，不是代码错**：① `_ORIG_HAS_OS` 夹具只 `import os` 而没有
  `os.system` 调用 ⇒ 危险差集恒空；② shape C 用同一份原码与新码，被
  `_check_patch_safety` 的 `applied and new_code != original_code` 前置条件跳过
  ⇒ 预检根本没跑；③ `static_check_outcomes` 在 BG 口径下"开关关"也**非空**
  （逐后端各记一条 `disabled`）⇒ 断言应校验"全部为 disabled"而不是"为空"。判据：
  新锁先红时先证"输入确实走到目标分支"，再怀疑判据。
- **披露变异之外必须配判定变异**（M18/M19）：本轮的约束是"判定逐字节不变"，只锁
  披露方向会漏掉"顺手把保守放行改成拒绝"这类扩大改动；两条判定翻转变异都按预期转红
  （4 / 7 红），与 §4 的两条"判定不变锁"（在测试内逐字重写 HEAD 公式做新旧 diff）互为
  对偶。
- **词表上收的代价**：三处状态常量原先各自内联字面量，上收 `check_status.py` 后
  必须锁"取值逐字相同"（`TestVocabularySingleSource`），否则下一轮改动会在某一处
  悄悄漂移，而聚合器仍然绿。
- **零点跨班**：本轮代码改动落在 2026-10-22 01:13 之后，登记日按实测时钟取
  2026-10-22；代码内 10 处 BI 标签同步改写，且**保持行数不变** ⇒ 覆盖率分母
  （19770 行 / 7496 弧）不受标签改写影响，已在新一次全量跑中复核。

## 7. 边界（不得引用为"写盘前预检已整体可信"）

- **判定方向没动**：原文读不懂仍然**保守放行**（契约）/ 仍然**过度拦截**（危险差集把
  补丁全部命中算新增）。本轮交付的是"读者能看出这是放行的假设"，不是把放行改成拒绝。
- `safe_apply_patch`（`src/tools/patch_applier.py:454`）的兜底仍是
  `except SyntaxError`：`ValueError` 形状（孤立代理位）在该入口会向上冒泡，本轮不改
  该入口语义。
- 重采样路径的两处 `check_naming_contract` 调用（`src/graph/nodes.py` 内
  `_on_resample` 与重采样后复检）**不接 sink**：不可测量时它们保守 `return None`
  （拒绝方向），因此不构成假干净，但也**没有**可测量性记录。
- `PATCH_DANGEROUS_API_GUARD` 只门控 `safe_apply_patch` 侧；`_check_patch_safety`
  的 AST 差集是无条件调用的（正则通道另有自己的开关）。
- testless 验证四层（BH）里的 AST 守卫与命名契约仍按 BH 口径各自出 status，
  `src/tools/testless_validation.py` 内 352 / 394 两处调用**不接** `patch_applier`
  的 sink——两层的可测量性各说各话，不得合并成"所有静态守卫已统一"。
- `safety_check_status` 是**观测键，不是阻断策略**：图节点不因它拒绝写盘（除守卫本身
  的判定外）。下游要据此决策必须显式读该键。
- 本轮没有触碰执行侧判据（BD–BF 的有效通过谓词）；静态预检可测量 ≠ 补丁修好了缺陷。

## 8. 复算命令

```bash
.venv/bin/python -m pytest tests/test_bi_static_precheck_unmeasurable.py \
  tests/test_patch_applier.py tests/test_patch_applier_remaining_branches.py \
  tests/test_nodes_j4_patch_applier.py tests/test_type_repair_more_branches.py -q
.venv/bin/python scripts/tools/bi_mutation_verify.py
git show HEAD:src/tools/patch_applier.py > /tmp/bi_head_pa.py
git show HEAD:src/graph/nodes.py > /tmp/bi_head_nodes.py
grep -rho --include='*.json' '"contract_missing_symbols": [^,}]*' experiments/results | sort | uniq -c
.venv/bin/python -m mypy src/ config.py
```

后两条把改前版本取出，供 §1 的 HEAD 直调与"判定不变锁"的公式对照复现。

## 9. 收口批注（2026-10-22）

- 登记前（含 `--cov`，走 `make test-cov`）一跑：**11553 passed / 1 failed /
  5 skipped、213.52s**（collected **11559**，4 workers；63 warnings；链外
  `rc=2`）。唯一失败 = 基线守卫：`BASELINE.yaml` 当时仍声明 11504，实收 −
  声明 = 55 > 6 容差——除它之外零失败，正是"判定没动"的第一层证据。
- 覆盖率登记口径：**19247/19770 行 = 97.3546%**、**7064/7496 弧 = 94.2369%**
  （取 `coverage.xml` root 的 `lines-covered/lines-valid`、
  `branches-covered/branches-valid` 复算；终端 `TOTAL` 行的 `96%` 是
  coverage.py 把语句与分支合并后的口径，不可当登记值引用）。分母较 BH 移动
  +92 行 / +34 弧（`check_status.py` 43 行 / 18 弧 + 两守卫与消费点新增的
  分支）；未覆盖 527 → **523**（−4）、缺弧 435 → **432**（−3）。
- 逐文件（同一次登记前跑，`--cov-branch`）：`src/utils/check_status.py`
  **43/43 行 + 18/18 弧 = 100%**；`src/tools/patch_applier.py` **476/490 行 =
  97.14%**、弧 **218/232 = 93.97%**；`src/graph/nodes.py` **839/840 行 =
  99.88%**、弧 **319/322 = 99.07%**；`src/graph/state.py` **123/123 行 + 2/2
  弧 = 100%**；`src/tools/type_repair.py` **408/412 行 = 99.03%**、弧
  **210/222 = 94.59%**；`src/tools/testless_validation.py`（BH 面，本轮零改动）
  160/162 行、弧 44/44 = 100%。十项核心模块登记值 0 变动，`graph_nodes` 两位
  小数仍 99.88（底层由 BH 的 826/827 换到 839/840，同值不同分母，不得引用为
  "回收了多少行"）。
- 确认跑（无 `--cov`，单独执行、不与其他 pytest / 文档编辑重叠）：**11554 passed
  / 5 skipped / 0 failed、212.07s、rc=0**（collected **11559** = 11554 + 5 + 0，
  与登记前同一采集面；35 warnings；墙钟 213s）。
- 变异复跑（`scripts/tools/bi_mutation_verify.py`，登记文本收口前后各跑一次，两次
  读数**完全一致**）：基线 `rc=0 red=0`、**452 passed**（前跑 3.37s / 后跑 3.16s，
  后跑整链墙钟 **165s**、`rc=0`）；M1–M19 **全红**（红数逐项相同
  4/2/1/5/1/5/1/1/4/4/1/2/1/1/1/2/1/4/7）、collected 全程 **452**；M20 中性对照
  `rc=0 red=0`（按设计 SURVIVED）。每处变异先 `compile()` 再写盘、结束后按 sha256
  原字节还原（后跑之后 `git status` 只余本轮 intended 改动）。M18（原文读不懂改为
  拒绝）红 4、M19（危险差集丢掉基线）红 7——"只把沉默翻成披露、判定值与判定方向
  逐字节不变"这句话是由这两个锚点死掉来背书的，不是由叙述背书的。
- mypy：`Success: no issues found in 137 source files`；`ruff check .` 全过、
  `ruff format --check .` **960 份已格式化**（BH 轮 956 → +4 = BI 手册 / 新锁 /
  变异脚本 / `src/utils/check_status.py`）。
- 门禁实测（单独跑 `make gates`，不与其他 pytest / 文档编辑重叠）：
  **rc=0**、墙钟 **217s**；链内 pytest（`-n 4 --dist loadfile`、**不带
  `--cov`**，与带覆盖率读数不可互换）**11554 passed / 5 skipped / 0 failed、
  212.22s**（58 warnings；collected **11559** = 11554 + 5 + 0，与确认跑同一采集面）；
  `ruff check .` 全过、`ruff format --check .` **960 份已格式化**、mypy **137 源文件
  零问题**；双语文档 0 警告 / 0 失败；文档链接 strict **177 份文件（docs 158 /
  examples 4 / root 15）/ 822 条链接（内部 813 / 外链 9）/ 0 错误 / 0 警告**（BH 轮
  176/814 → +1 份 BI 手册 / +8 条链接）；env-budget **253/253** 全部登记；
  `check_baseline` 结构校验与数字漂移检查均通过；状态通道 **136 个文件**无未声明键
  读写（BH 轮 135 → +1 = `src/utils/check_status.py`）；env-snapshot **84 开关 /
  115 键 / 缺失 0**（扫描面同 136 文件）；model-fingerprint 近期无新批次，通过；
  工具版本一致（mypy 1.15.0 / ruff 0.16.3）；JSON 契约 **7/7** 调用点一致（文档数量
  表述 9 处全 [OK]）；严格 JSON **7274 份工件**（7272 严格 + 2 历史豁免 + 0 违规）、
  **304 份**源码写入点 0 违规；报告→工件对账 [OK]（不一致 0；T-10 严格 29 行 / 25
  可测、宽松 62 / 55；登记册 §1 覆盖率对账与 `coverage.xml` 实测相符，容差 ±0.20pp）；
  零断言 **453 份测试文件 / 0 违规**（BH 轮 452 → +1 = BI 锁文件）。
- 回填门禁读数前再单独跑一次 `make gates`（§9 首跑读数落盘后、其余登记文本尚未
  改写时的复验跑）：**rc=0**、墙钟 **208s**、链内 **11554 passed / 5 skipped /
  0 failed、202.03s**（45 warnings；collected 11559）。除墙钟、in-chain 用时与
  warnings 计数外，两跑的门禁读数**逐行相同**（`diff` 过滤 warnings 计数后为空）：
  960 份已格式化、mypy 137 源文件、双语 0 警告 / 0 失败、文档链接 177/822/0 错误、
  env-budget 253/253、状态通道 136 文件、env-snapshot 84 开关缺失 0、工具版本 OK、
  JSON 契约 7/7、7274 份工件 0 违规 / 304 份写入点 0 违规、对账 [OK]、453 份测试
  文件 0 违规。两跑墙钟与 warnings 差仅作抖动，不作性能主张。
- 第三次单独跑（README / CHANGELOG / INDEX / 登记册 / BASELINE 的门禁句已回填，
  本册 §9 末条尚未写入）**rc=0**、墙钟 **200s**、链内 **11554 passed / 5 skipped /
  0 failed、195.21s**（36 warnings；collected 11559）；其余门禁读数与复验跑**逐项一致**。
- 第四次（终跑，覆盖此前写入的全部登记文本）**rc=0**、墙钟 **201s**、链内
  **11554 passed / 5 skipped / 0 failed、195.73s**（8 warnings；collected 11559）；
  同一 `diff` 过滤 warnings 计数后与前三跑**逐行相同**。四跑之间动的只有墙钟、
  in-chain 用时与 warnings 计数（217/212.22/58 → 208/202.03/45 → 200/195.21/36 →
  201/195.73/8），不作性能主张。
- 终跑之后写入的只有标签订正（把 200s / 195.21s 那一跑由"终跑"改称"第三跑"）与
  第三跑 / 终跑读数在 README×2 / CHANGELOG×2 / INDEX×2 / 登记册 / BASELINE 中的补写，
  加上本册 §9 末数条——不含除"终跑读数"之外的新实测断言；故四跑 rc=0 各自覆盖的是
  其写入之前的登记文本，终跑之后的这段改动由下一条的门禁子集复验。
- 子集复验（终跑之后改动只涉及门禁句的标签与读数补写，直接跑会读到这些文本的门禁）：
  `BASELINE.yaml` YAML 解析通过且 `tests.total_passed=11554`；
  `check_bilingual_docs.py --strict` **0 警告 / 0 失败**；`check_doc_links.py --strict`
  **177 份 / 822 条 / 0 错误 / 0 警告**；`check_baseline_numbers.py` 通过；
  `check_zero_assert_tests.py` **453 份 / 0 违规**；`ruff format --check .`
  **960 份已格式化**；`check_artifact_doc_consistency.py` 三臂不一致 0 项 +
  登记册 §1 覆盖率对账 [OK]；文档锁子集 `tests/test_ao_batch.py` 等 8 个文件
  **185 passed / 0 failed**（含基线一致性守卫 `TestBaselineNumbersConsistency`）。
- 本轮改动全部未提交，未推送（工作区随收口提交一并入库）。
