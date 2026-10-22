# BJ 轮：AST 断言一致性检查的「读不懂 ⇒ 无疑点」收口（2026-10-22，零 LLM）

**范围**：`src/tools/oracle_validator.py` 的 `check_assertions`（Generator 产出后的
AST 级断言一致性检查，`ORACLE_VALIDATE_ENABLE` 默认关）与其唯一生产消费点
`src/graph/nodes.py::_run_generator_postchecks` / `_generator_node`；状态通道声明在
`src/graph/state.py`。词表与聚合函数沿用单一事实源 `src/utils/check_status.py`
（BG→BI 已上收，本轮是第 4 个消费点）。

这是 F03 静态侧的第 7 个形态：BD/BE/BF/BC 收口 pytest 的 `rc==0`，BG 收口外部检查器
的**空 findings**，BH 收口校验层的 `passed=True`，BI 收口写盘前守卫的**空结果**，本轮
收口**疑点列表为空**——`findings=[]` 同时是"扫过且无疑点"、"输入为空"、"测试文本读不懂
（从未扫描）"、"被测代码读不懂 ⇒ 类型推断通道哑火"四种成因的返回值。

**结论**：`check_assertions` 新增可选 `outcome_sink`，逐腿追加
`{check, status, reason}`（腿次 `assertion_consistency` + `target_type_inference`），
消费点以 **worst-of** 聚合（两腿相互独立 ⇒ 最差者优先，方向与 BI 同、与 BG 反），发布
状态通道 `oracle_check_status` / `oracle_check_outcomes`（TypedDict 显式声明 + 默认
`None`）。**判定值与判定方向逐字节不变**：不剥围栏、不把"读不懂 ⇒ 零疑点"翻成"读不懂
⇒ 拒绝"；语料 10855 条产物 old-vs-new 判定比对 0 差异。**63 例新锁 + 变异 23 锚点全红
+ 中性对照 0 红**（collected 全程一致、sha256 原字节还原；逐项读数见 §5）。

---

## 1. 缺陷：空疑点列表的四义与 O4 盲区（改前实测）

改前读数取自 `git show HEAD:src/tools/oracle_validator.py` 与
`git show HEAD:src/graph/nodes.py` 的直接调用（Python 3.14.6，零 LLM，非推断）。
消费点 `_run_generator_postchecks(state, generated_test)` 的输入形状与读数：

| 输入形状（`target_code` 恒为 `def f(a): return 1`） | 改前 `oracle_findings` / `tautological_count` / `o4_triggered` | 问题 |
|---|---|---|
| 干净产物 `assert f(1) == 1` | `[] / 0 / False` | 基准腿：这是唯一的真证据形态 |
| **围栏整块产物** `` ```python `` + `assert True` + `` ``` `` | `[] / 0 / False` | **假干净主锚点**：块内就是恒真断言，但 AST 读不懂整块 ⇒ 从未扫描，O4 不触发 |
| 真语法错误产物 `def f(:` | `[] / 0 / False` | 与"干净"逐字节同值 |
| 空产物 | `[] / 0 / False`（`and generated_test` 短路，`check_assertions` 根本未被调用） | 与"干净"同值，且连"没跑过"都不点名 |
| 真恒真断言 `assert True` | `['tautological'] / 1 / True` | 唯一能让 O4（强制重生成）动作的形态 |

前三行与第四行**返回值逐字节相同**，这就是缺陷本身：O4"恒真断言 ⇒ 标 `test_defect` ⇒
路由回 Generator 重生成"是 generator 侧唯一的写侧路径，它对读不懂的产物**恒不触发**。

被测侧（`target_code`）同型且更静默：

| 输入形状 | 改前 | 问题 |
|---|---|---|
| `target_code` 读不懂（`def f(:`）而测试侧可解析 | 疑点照常产出，但 `type_mismatch` 通道恒哑火（`except SyntaxError: pass` ⇒ 推断表空） | "类型都一致"与"类型推断层根本没建立"同值 |
| `target_code` 为 `None` / `""` | 同上 | 未提供被测码与"提供了但读不懂"同值 |
| 含孤立代理位的产物（`x = '\ud800'`） | `ast.parse` 抛 `UnicodeEncodeError`（`SyntaxError` 之外的 `ValueError` 子类）**抛穿** `check_assertions` | 只捕 `SyntaxError` ⇒ 观测层把主流程打断（BH/BI 同型缺陷） |

---

## 2. 处置：逐腿 sink + 最差者优先 + 通道发布

### 2.1 两条腿与取值矩阵

| `check` | `status` | `reason` | 含义（读法） |
|---|---|---|---|
| `assertion_consistency` | `ok` | `assertions_checked` | 扫过了，产物里确有 assert 语句 ⇒ 空列表是"无疑点"证据 |
|  | `ok` | `no_assert_statements` | 扫过了，产物里一条 assert 都没有 ⇒ "无疑点"成立但要与上一条分开统计 |
|  | `disabled` | `empty_input` | 输入为空/纯空白 ⇒ 没东西可扫 |
|  | `error` | `unparseable_test:fenced_block` | 剥掉前导空白后以 ```` ``` ```` 开头 ⇒ 传输层伪影，从未扫描 |
|  | `error` | `unparseable_test:syntax` | 产物本身语法缺陷 ⇒ 从未扫描 |
| `target_type_inference` | `ok` | `target_parsed` | 被测侧读通了，推断表已建立 |
|  | `disabled` | `target_not_provided` | 未提供被测码 ⇒ 类型推断按设计不参与 |
|  | `error` | `unparseable_target` | 被测侧读不懂 ⇒ `type_mismatch` 通道哑火 |

三条口径写在实现里：

1. **盲区早退不记第二条腿**（`return []` 前不存在被测侧比较，记了就是假陈述）；
2. **围栏归因判据是"剥掉前导空白后以围栏开头"**，不是"正文里出现过围栏"——后者会把
   模型答的一段带代码块的解释也算成传输层伪影（实测语料里正好有这 1 条边界样本）；
3. **解析面收敛到 `parses_as_module`**：这是本轮唯一披露的行为变化——孤立代理位不再
   抛穿，按"读不懂"处理，与 BH/BI 逐字同口径（§4 有锁、§5 有反向锚点）。

### 2.2 消费点聚合与通道

`_run_generator_postchecks` 的三分支：开关关 ⇒ `disabled:oracle_validate_disabled`；
开关开但无生成内容 ⇒ `disabled:no_generated_test`；否则调用 `check_assertions` 并透传
sink。聚合走 `worst_check_status`（默认 `error`，"一条腿都没记"不能读成"都验过了"），
`status != ok` 时 warning 逐腿点名 `check=status:reason`。返回值键集合从 7 键固定扩到
9 键（新增两键恒在），`_generator_node` 恒发布到 state：

- `oracle_check_status: str | None`、`oracle_check_outcomes: list[dict] | None`；
- `oracle_findings` 仍**只在非空时**写键（旧口径逐字节不变，盲区形态由新键承担）；
- 两个键在 `AITesterState` 显式声明并默认 `None`——未声明键会被 LangGraph 静默丢弃
  （AK4 的门禁 `scripts/gates/check_state_contract.py` 实测 136 个文件通过）。

**命名撞车回避**（实测而非猜）：实验侧 `experiments/oracle_quality_replay.py:1254`
已用 `oracle_status` 表示**规约 oracle** 臂的 `task["oracle"]["status"]`。本轮新键取名
`oracle_check_status`，并加一条锁声明两者不是同一字段（§4）。

### 2.3 判定不变性（"只补披露"的边界）

明确**不做**的事，全部有反向锚点：

- 不剥围栏再解析（那会把 72 条盲区产物变成疑点源 ⇒ 改 findings 计数 ⇒ 改 O4 判定）；
- 不把"读不懂 ⇒ 零疑点"翻成"读不懂 ⇒ 拒绝/重生成"（方向变更会连带改写历史读数语义）；
- 不让 sink 参与判定：`outcome_sink=None` 时返回契约逐字节不变（BI 同款可选参数）。

---

## 3. 真语料测量（本轮重测，非沿用笔记）

复算命令 `scripts/tools/bj_corpus_probe.py`（只读、零 LLM），口径 = 递归
`experiments/results/**/*.json` 全树里任一层出现的 `generated_test` 字符串，逐条喂给
现版 `check_assertions` 并统计 sink：

```
json_files=1702 parsed=1594 读取失败=108（{'JSONDecodeError': 108}）
ORACLE_VALIDATE_ENABLE=true 归档=57（其 generated_test 站点=2486）
generated_test 站点合计=10855
assertion_consistency 腿分布：
  ok:assertions_checked = 10671
  disabled:empty_input = 77
  error:unparseable_test:fenced_block = 72
  ok:no_assert_statements = 31
  error:unparseable_test:syntax = 4
有疑点站点（findings 非空）=7866
开关开启归档中的不可测量站点（本轮 O4 盲区）=1
  盲区样本：/Users/wangchenyu/Workspace/AITester/experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_201928.json error:unparseable_test:fenced_block
归档内 target_code 字符串=1（其中读不懂=1）
target_type_inference 腿分布：disabled:target_not_provided = 10702
```

**采集口径补两句**：(a) 上面这份输出是修复 §6 第 8 条之后在干净树上**重跑**得到的，
逐位与首轮登记值相同——首轮登记为真，但当时那份脚本恰好在那一个分支上跑不通；
(b) stderr 另有 2 行 `<unknown>:15: SyntaxWarning: "\d" is an invalid escape sequence`
——那是解析归档里生成的测试文本（未闭合的 `\d`）时的解释器噪声，不进 stdout、不进任何
读数分母，点名是为了避免被误读成探针自身报错。

四条读数值得单独点名：

1. **153 条盲区/空输入**（77 + 72 + 4）占 10855 的 1.41%，其中 76 条是"读不懂"。
   这 76 条在旧口径里全部伪装成"扫过且无疑点"，与 10671 条真扫过的返回值逐字节相同。
2. **开关开启的 57 份归档里恰有 1 个盲区站点** —— 本轮的 O4 盲区在生产读数里的真实
   规模是 1 例，不是"一批"。登记这个 1 是为了防止把 §1 的表格读成生产频率。站点已由
   探针点名（见上：`emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_201928.json`，
   归因 `error:unparseable_test:fenced_block`），不是只给了一个计数。
3. **`target_code` 与 `generated_test` 在归档里不共位**（全树仅 1 条 `target_code`
   字符串，且它本身读不懂）⇒ 被测侧那条腿**没有历史读数可回填**，其可达性证据只有
   代码路径（消费点恒传 `state["target_code"]`）与单元锁。这是 §7 的边界，不是本轮已
   收口的部分。**算术自洽核对**（同一份输出内部对账，不需要再跑）：第二条腿只记
   `disabled:target_not_provided = 10702`，而 10855 − 153（盲区/空输入不记第二腿）
   = 10702 逐条对上 ⇒ 那 1 条 `target_code` 字符串**不在任何 `generated_test` 站点上**，
   `error:unparseable_target` 在语料里是 **0 实例**（按名登记，不写成"已排除"）。
4. 顺带实测：`oracle_findings` / `tautological_count` / `o4_triggered` 三个键在 1594
   份可解析归档里出现 **0 次** ⇒ 新通道零历史回填；同时也说明这条观测腿的产出**从未
   进入任何已登记读数**（含那 57 份声明开启的归档）。

**判定不变性比对**（同一脚本族，HEAD 版与现版直调）：HEAD 版 `check_assertions` 与
现版在全部 10855 条语料上 `repr(findings)` 逐条比对，**差异 0 条**；异常面
`crashes_old=0 / crashes_new=0`（语料里没有孤立代理位样本，故 §1 第 3 行的抛穿缺陷在
历史归档中 0 实例，仍按缺陷收口）。

---

## 4. 回归锁（`tests/test_bj_oracle_unmeasurable.py`，63 例）

| 组 | 例数 | 锁住什么 |
|---|---|---|
| §1 词表与单一事实源 | 4 | 三个 status 常量与 `check_status` **同一对象**；oracle 模块内不得出现 status 裸字面量（第二套词表）；逐腿 status 全在 `CHECK_STATUS_VOCABULARY` 内；可解析性面与 BH/BI 共用（代理位、空字节） |
| §2 测试侧腿 | 12 | 空/纯空白 ⇒ `disabled:empty_input`；围栏 ⇒ `error:fenced_block`；正文中间出现围栏 ⇒ `error:syntax`；真语法错误、空字节、孤立代理位各自点名；有 assert ⇒ `ok:assertions_checked`，无 assert ⇒ `ok:no_assert_statements`；腿序与"盲区只记一条腿"；`sink=None` 零开销 |
| §3 被测侧腿 | 8 | 未提供 ⇒ `disabled:target_not_provided`；读不懂 ⇒ `error:unparseable_target`；py2 被测码、孤立代理位被测码；纯空白被测码算"读通了"（`ast.parse` 成功）这一口径也锁死 |
| §4 判定不变性 | 17 | 8 组盲区/退化输入**全部返回同一个 `[]`**；不剥围栏（并证明"剥了就会多出 1 条疑点"）；带 sink 与不带 sink 的 findings 逐条相等；三类疑点仍可检出；被测侧盲区照旧哑火 `type_mismatch`；"空 + 双 ok"才是无疑点证据 |
| §5 消费侧聚合 | 12 | 开关关 / 无产物 ⇒ 两个不同 `disabled` reason 不合并；围栏产物 ⇒ `error` 且 `tautological_count=0`、`o4_triggered=False`；被测侧盲区把聚合拉成 `error` 但疑点与 O4 判定不动；worst-of 与 any-ok 两个方向同时锁（与 BG 反向）；9 键固定集；产物逐字节不变；返回的 outcomes 是副本 |
| §6 通道发布 | 7 | 默认关也恒写 `oracle_check_status="disabled"`（但 `oracle_findings` 仍不写键——旧口径逐字节不变）；开关开 + 盲区 ⇒ `error` 且不发 O4 信号；降级 warning 逐腿点名 `check=status:reason`；`ok` 时不发 warning |
| §7 state 通道 | 3 | 两键在 `AITesterState.__annotations__` 内；`create_initial_state` 默认 `None`；与实验侧 `oracle_status` 不撞名 |

---

## 5. 变异验证（`scripts/tools/bj_mutation_verify.py`，23 锚点 + 1 中性对照）

执行口径（一次连续运行，全量 24 个条目）：

- **基线**：干净树上 14 份测试文件 **collected=501**；本轮补测的同命令基线复跑
  `rc=0 / 501 passed / 0 failed / 33.49s / 2 warnings`（harness 首跑基线行被管道截断，
  故这条是还原后的独立复跑，两者都是"未变异树"）；harness 在基线不绿时直接 abort，
  首跑能走到 M24 也即基线为绿的旁证。
- **每个变异体的三道检查**：写入前 `compile()` 通过（无 SYNTAX-ERROR）、写入前后
  `collect_count` 与基线一致（无 COLLECTED-DRIFT）、`finally` 里按 sha256 断言原字节还原
  （无还原失配）。整轮 harness **退出码 0** ⇒ 24 个条目全部走到，没有 ANCHOR-ERROR。
  下表逐项读数取自这**一次**连续运行；后来那次为补基线行而重启的全量运行在 M7 被中止
  （§6 第 7 条），其残留已手工还原并复验，**不影响本表**——因为首跑的 M7 在退出码 0
  的路径上已完成 sha256 还原。
- **collected 全程 501**（含 M24 中性对照），逐锚点 `rc`/`red` 如下：

| 锚点 | 类 | 变异含义（反向锚点所防的口径） | rc | red |
|---|---|---|---|---|
| M1-blind-test-looks-measured | 披露 | 读不懂 ⇒ 从未扫描，却记 `ok` | 1 | 9 |
| M2-empty-input-looks-ok | 披露 | 空输入被记成可测量 | 1 | 2 |
| M3-blind-test-not-disclosed-at-all | 披露 | 读不懂整条不点名（回到 BJ 前的沉默） | 1 | 9 |
| M4-no-assert-reason-collapsed | 披露 | "扫过有断言"与"扫过无断言"两种 reason 合一 | 1 | 1 |
| M5-measured-leg-looks-unmeasured | 披露 | 真扫过了却记 `disabled`（反向：把"无疑点"读成"没检查"） | 1 | 11 |
| M6-blind-target-looks-measured | 披露 | 被测侧哑火却记 `ok` | 1 | 5 |
| M7-no-target-looks-ok | 披露 | 没给被测代码被记成"类型推断量过了" | 1 | 3 |
| M8-target-leg-dropped-when-absent | 披露 | 未提供被测码时不记第二腿 | 1 | 3 |
| M9-fence-attribution-lost | 归因 | 围栏归因并入泛化 `syntax`：传输伪影 vs 产物缺陷分界消失 | 1 | 3 |
| M10-fence-attribution-too-broad | 归因 | 判据放宽成"正文出现过围栏"（§6 第 2 条那 1 条边界样本） | 1 | 1 |
| M11-warning-reason-dropped | 归因 | 降级 warning 丢逐腿明细 ⇒ 只说"不可测量"不说是哪条腿 | 1 | 2 |
| M12-parsability-narrows-to-syntax-error | 聚合 | 只捕 `SyntaxError` ⇒ 孤立代理位抛穿（BH/BI 同型） | 1 | 8 |
| M13-precedence-ok-wins | 聚合 | 独立检查改成 ok 优先（即 BG 的方向） | 1 | 8 |
| M14-switch-off-not-disclosed | 消费侧 | 开关关闭不点名 | 1 | 2 |
| M15-no-generated-reason-merged | 消费侧 | 无产物与开关关共用一个 reason | 1 | 1 |
| M16-degradation-warning-dropped | 消费侧 | 降级不发 warning（读数在，运维看不见） | 1 | 2 |
| M17-leg-details-not-returned | 消费侧 | 逐腿明细不并入返回值 ⇒ 通道只剩聚合标量 | 1 | **50** |
| M18-aggregate-hardcoded-ok | 消费侧 | worst-of 结果硬写死 `ok` | 1 | 8 |
| M19-channel-details-not-published | 通道 | `_generator_node` 不把明细写进 state 更新 | 1 | 1 |
| M20-channel-default-dropped | 通道 | `create_initial_state` 通道默认值缺失 | 1 | 1 |
| M21-judgment-flip-strip-fence | 判定 | 剥围栏再解析 ⇒ 盲区产物开始产出疑点（本轮明确不做） | 1 | 7 |
| M22-judgment-flip-blind-raises | 判定 | 读不懂改成抛穿 ⇒ "不阻断主流程"方向翻转 | 1 | **20** |
| M23-judgment-flip-returns-sink | 判定 | 把披露列表当判定返回 ⇒ sink 污染返回契约 | 1 | 1 |
| M24-control-wording | 对照 | 仅改注释措辞（测试代码→测试文本），不动判据 | **0** | **0** |

两张最宽的网值得单独点名，因为它们证明"锁不是只锁新文件"：

- **M17（50 红）**删掉返回值里的逐腿明细键，除新锁外还打掉既有
  `tests/test_nodes_j4_generator_sections.py::TestInjectionGuardLeg` 等消费侧断言
  （9 键固定集一旦变形，`src/` 侧的旧契约测试立刻红）；
- **M22（20 红）**把盲区输入的"保守返回空"翻成抛穿，首个点名测试就是
  `tests/test_oracle_validator.py::test_syntax_error_test_code`（旧文件里既有"语法错误
  返回空"的口径锁），说明 §2.3 的判定不变性由**改前就存在**的测试共同守着，
  不只是本轮新锁。
- M24 反向证明"注释措辞不构成锚点"：0 红 = 未把无关文本写进判据。

---

## 6. 踩坑与自纠（本轮实测发生的，不是设想）

1. **并发测量读到变异体**（第一贵）：语料探针与变异验证 harness 同时在跑时，
   探针在 `src/` 被临时改写的窗口里 import 了变异版 `check_assertions`，打印出物理上
   不可能的组合 `{'status': 'disabled', 'reason': 'assertions_checked'}`——那正是变异体
   M5（把 `disabled` 与 `ok` 的 reason 拼错通道）的指纹。当场停掉探针、丢弃该份输出，
   §3 的读数全部在干净树上重跑取得。**口径**：变异验证会改写 `src/`，因此任何只读探针
   /不变性比对都不得与它并行；本轮 §3 与 §5 严格串行。
2. **围栏归因判据改窄，语料读数 73 → 72**：第一版按"正文里出现过 ```` ``` ```` 标记"判
   传输层伪影，把模型答案中间带代码块的解释也算了进去，同时还会把"围栏在读懂的产物里"
   误标。改为"剥掉前导空白后以围栏开头"后重测得 72，另有 4 条归
   `unparseable_test:syntax`。该 1 条差额已用**不 import `src/`** 的第二套口径独立复核
   （`scripts/tools/bj_discriminator_crosscheck.py`：直接用最标准库 `ast.parse` 复现
   `parses_as_module` 的判定面，两种判据并排计数；因此它可以在变异验证运行期间安全
   重跑）：`sites=10855 unparsable=76 strict_fenced=72 loose_fenced=73 loose_only=1
   syntax_strict=4`——`loose_only=1` 就是那条边界样本。§2.1 第 2 条口径就是这条教训
   写进实现。
3. **新键与实验侧撞名**：拟用的 `oracle_status` 经 grep 实测已被
   `experiments/oracle_quality_replay.py:1254` 用作**规约 oracle** 臂的
   `task["oracle"]["status"]`（完全不同的语义）。若沿用，同一份 state/归档里两个
   "oracle 状态"将无法区分。已改名 `oracle_check_status` / `oracle_check_outcomes`
   并加锁声明两者不同一（§4 §7 组）。
4. **探针差点把 `"false"` 读成开关开启**：归档里的开关值是 JSON 字符串，
   Python 的 `bool("false")` 恒真 ⇒ 第一版"开关开启归档数"被系统性高估。改为
   `_truthy()` 折叠（`1/true/yes/on` 才算真，其余为假）后重测，§3 登记的是修正后
   读数（57 份），**旧读数已作废、未登记、也不参与任何换算**。
5. **两处锁的预期写错（错在锁，不在被测码）**：
   (a) 以为盲区早退也会记第二条腿，断言 `["error", "ok"]` 实际是 `["error"]`——这正是
   §2.1 第 1 条"盲区不记第二腿"的口径，锁按实现改；
   (b) 把 `assert f([3, 1, 2]) == 1` 当"干净产物"，但它触发 `magic_number` 疑点
   （列表字面量里的 `3` 不在 `_TOLERATED_INTS`）⇒ 节点级"干净"用例换成真干净的
   `_CLEAN_TEST`。两条都记：预期要按判据推，不能按直觉写。
6. **消费点保持 `state["target_code"]` 直取**：三分支里的 `elif not generated_test`
   短路必须排在调用之前——它保证开关开着但没有产物时不会去碰 `state["target_code"]`，
   因此本轮**没有新增 KeyError 访问面**（改前该短路也存在，只是不点名）。
7. **为了取"基线行"而重启 harness，反而留下了活的变异体（本轮代价最大的一条）**：
   首跑用 `... | tail -70` 采集，基线行被截断（管道既丢读数又违反"不要用管道接
   `make`/harness"的既有口径）。为补这条读数我直接重启了**全量** harness——它跑到 M7
   时被中止，而 `SIGKILL` 不执行 `finally`，于是 M7 的变异文本留在
   `src/tools/oracle_validator.py:148`。发现方式不是自我印象，而是顺手的全仓
   `# mutation` 标记扫描：`src/` 命中 1 处，逐行核对确认它就是 M7 的变异串；按 harness
   的还原语义（写回锚点原行，不用 `git checkout`/`git stash`）手工还原后，同命令基线
   复跑 `501 passed / 0 failed`、`ruff check` + `ruff format --check` 归零，四个被变异
   文件的 sha256/字节数留档。**三条口径由此固定**：(a) 只需基线时绝不再跑全量 harness，
   直接跑 harness 用的那条 pytest 命令即可（34s）；(b) harness 输出必须落文件后再
   grep，不接管道；(c) 中止过任何会改写 `src/` 的脚本，下一步动作是**扫描残留**
   （`# mutation` 标记 + 定向回归），而不是继续登记。
8. **"声称可重跑"的复算脚本自己跑不通（`make gates` 才暴露）**：为了把 §3 第 2 条那
   1 个盲区站点**点名**（而不是只给一个计数），我给探针加了样本路径收集，写成了
   `if len(enabled_blind_paths) < 5: enabled_blind_paths.append(...)`，却没有声明这个
   列表。`make gates` 在 lint 步骤就转红——`ruff check .` 在
   `scripts/tools/bj_corpus_probe.py:136` 报
   `F821 Undefined name 'enabled_blind_paths'`——链在 0s 处退出，因此**当时没有任何
   gates 读数可引**。三点值得记：
   (a) 崩溃点是 `if file_enabled and head["status"] != "ok"` 分支内侧，也就是说脚本在
   **没有盲区站点的输入上跑得通**、只在真实语料那 1 条上 `NameError`——"我跑过"和
   "登记的那条口径跑得通"不是一回事；
   (b) `scripts/tools/` 下的分析脚本不被任何测试 import，因此静态检查是挡在读者与
   跑不通的复算命令之间的**唯一**一道门；把它写成"可逐条重跑"就是把自己的可信度押在
   lint 上；
   (c) 登记读数来自**改动前的文件态**：首轮 §3 的 10855 / 10702 / 57 / 1 都是真测的，
   但发布的那份脚本复现不出来——这类"读数真、复现路径断"的缺陷比读数错更隐蔽。
   修完列表初始化后已在干净树上**重跑**（§3 采集口径补句），逐位相同；口径由此加一条：
   **凡登记为"可重跑"的脚本，最后一次编辑之后必须再跑一次**，不能沿用编辑前的输出。
9. **把"还没发生的终跑读数"写进了登记（写错后当场撤回）**：§9 写完复验跑之后，接着按
   BI 手册的形制补"终跑 + 子集复验"两条，rc / 墙钟 / 链内用时全部"照例"写了具体数字——
   而那一次链**一次都还没跑**。这不是笔误而是形制陷阱：上一轮的模板里有这几条、本轮
   也必然会有这几条，于是"补全形状"的手比"先跑再写"的手快。发现后已删回，改为一条显式
   声明"这条链还没跑，因此本节不写它的读数"；等终跑真实发生之后，才把 rc 与两个用时
   写进 §9。**口径**：读数只能是过去式；凡模板位置需要将来才产生的数字，先写"尚未执行"
   这句话本身，也不要写"预计约 N 秒"。

---

## 7. 边界与未收口部分（按名登记，不写成"已排除"）

1. **O4 对读不懂的产物仍然不触发**。本轮只把"没量过"变成可测量读数，
   `tautological_count` / `o4_triggered` 的判定值逐字节不变（§2.3 反向锚点 + §5 判定类
   变异）。语料里开关开启归档的盲区站点实测 **1 例**（§3 第 2 条）——是否要把它翻成
   "强制重生成"是判定方向变更，需另行设计，不在本轮。
2. **被测侧腿无归档证据**：`error:unparseable_target` 在 10855 条语料上 **0 实例**，
   可达性只有代码路径 + 单元锁（§3 第 3 条的算术自洽）。
3. **剥围栏的根因在生成侧，不在本轮**：围栏整块是"生成器把 ```` ```python ```` 块原样
   返回"的传输层伪影（72 条）。真正的修复位置是产出清洗或解析前的规范化；那会改变
   findings 计数与 O4 判定，属于判定变更，本轮明确不做。
4. **分析侧同名异味是另一套实现**：`experiments/analysis_parts/convergence_analysis.py`
   的 `_smell_task_has_smell`（`:91`）用文本启发（`"assert " in stripped`、正则取
   `== <int>`）而非 AST，因此它的文本段在围栏产物上照样命中；但其 AST 段（eager_test /
   lack_of_cohesion，`:173-176`）`ast.parse` 失败时 `tree = None` 直接跳过、**不点名**。
   跳过面与本轮语料口径同为那 76 条读不懂产物。分析侧不属于 `src/` 生产判定面，
   本轮未收口、也未测量其登记读数。
5. **开关默认关**：`ORACLE_VALIDATE_ENABLE` 未设时生产恒走
   `disabled:oracle_validate_disabled`（通道仍发布，只是恒 `disabled`）。
6. **108 份 JSON 读不懂的归档**未计入语料分母（`json_files=1702 / parsed=1594`），
   失败按异常类型点名（`{'JSONDecodeError': 108}`），不是静默 `except: continue`。
7. **`check_assertions` 的第二套词表风险已锁但没有静态门禁**：§4 §1 组锁的是"模块内
   不得出现 status 裸字面量"（测试期断言源码文本），非 `scripts/gates/` 的仓库级门禁。

---

## 8. 复算命令（零 LLM、零写入、可逐条重跑）

```bash
# 1) 本轮 63 例新锁（先看 collected=63，再看 rc）
.venv/bin/python -m pytest tests/test_bj_oracle_unmeasurable.py -q --collect-only | tail -2
.venv/bin/python -m pytest tests/test_bj_oracle_unmeasurable.py -q -p no:cacheprovider

# 2) 邻近面（oracle 直调 + generator 消费 + 状态契约 + BG/BI 同族，共 501 例）
.venv/bin/python -m pytest tests/test_oracle_validator.py \
  tests/test_oracle_validator_branches.py tests/test_nodes_j4_generator_sections.py \
  tests/test_state_contract_guard.py tests/test_bi_static_precheck_unmeasurable.py -q

# 3) §3 语料读数（必须在干净树上跑，禁止与变异验证并行——见 §6 第 1 条）
.venv/bin/python scripts/tools/bj_corpus_probe.py

# 3b) §6 第 2 条的差额复核（不 import src/，随时可跑）
.venv/bin/python scripts/tools/bj_discriminator_crosscheck.py

# 4) §5 变异验证：23 锚点 + 1 中性对照（会临时改写 src/，结束按 sha256 原字节还原）
.venv/bin/python scripts/tools/bj_mutation_verify.py            # 全量
.venv/bin/python scripts/tools/bj_mutation_verify.py M21 M22 M23 # 判定类单独复跑

# 5) 门禁链（最后、单独跑，不要接管道——见项目口径）
start=$(date +%s); make gates > /tmp/gates.log 2>&1; rc=$?; echo "rc=$rc elapsed=$(( $(date +%s) - start ))s"
```

---

## 9. 收口批注（2026-10-22）

- 登记前（含 `--cov`，走 `make test-cov`）一跑：**11616 passed / 1 failed /
  5 skipped、59 warnings、197.48s**（collected **11622**，4 workers；链外
  `rc=2`，`make: *** [test-cov] Error 1`）。唯一失败 = 基线守卫
  `tests/test_2026_10_10_optimization_batch.py::TestBaselineNumbersConsistency::test_tests_and_mypy_are_current`
  ——`BASELINE.yaml` 当时仍声明 BI 的 11554，实收 − 声明 = **68 > 6 容差**。除它之外
  零失败，正是"判定没动、只补披露"的第一层证据；该守卫也是本轮**唯一**因登记滞后而
  转红的用例，不是产品缺陷。
- 覆盖率登记口径：**19272/19793 行 = 97.3678%**、**7072/7504 弧 = 94.2431%**（取
  `coverage.xml` root 的 `lines-covered/lines-valid`、`branches-covered/branches-valid`
  复算；终端 `TOTAL` 行的 `96%` 是 coverage.py 把语句与分支合并后的口径，不可当登记值
  引用）。分母 +23 行 / +8 弧、覆盖 +25 行 / +8 弧 ⇒ **新增弧全部被 63 例锁执行**；
  未覆盖 523 → **521**（−2，恰落在既有 ±2 行抖动域边缘，不作回收主张）；缺弧
  **432 → 432 逐位不变**。两位小数与 BI 同为 97.37 / 94.24——**同值不证明 `src/` 未动**，
  只说明本轮无退化。
- 逐文件（同一次登记前跑，`--cov-branch`）：`src/tools/oracle_validator.py`
  **128/134 行 = 95.52%**、弧 **80/88 = 90.91%**，**6 条未覆盖行逐行定位**：261 / 269
  属 `_is_tautological_assert` 的 `x and not x` 恒假分支、332 属 `_check_magic_numbers`、
  370 / 375 属 `_check_type_mismatch`、413 属 `_infer_expr_type`——**全部是改前既有的
  启发式辅助**，本轮新增的两腿 status 与归因分支无一未覆盖；`src/graph/nodes.py`
  **851/852 行 = 99.88%**、弧 **323/326 = 99.08%**（BI 839/840、319/322 → +12 行 / +4 弧，
  两位小数不变）；`src/graph/state.py` **125/125 行 + 2/2 弧 = 100%**；
  `src/utils/check_status.py` **43/43 行 + 18/18 弧 = 100%**（本轮零改动，只是第 4 个
  消费点）；BI 面 `patch_applier.py` 476/490 行、218/232 弧与 `type_repair.py`
  408/412 行、210/222 弧、BH 面 `testless_validation.py` 160/162 行、44/44 弧**均 0 变动**。
- 确认跑（无 `--cov`，单独执行、不与其他 pytest / 文档编辑重叠）：xdist
  `-n 4 --dist loadfile` **11617 passed / 5 skipped / 0 failed、192.77s、rc=0**
  （collected **11622** = 11617 + 5 + 0，与登记前同一采集面；63 warnings；墙钟 194s）。
  **同一份树的串行对照**：**11617 passed / 5 skipped / 0 failed、521.41s、rc=0**
  （86 warnings）。两者计数逐位相同、用时差 2.7 倍**完全来自并行度** ⇒ 登记与引用时
  用时口径必须写明并行度，否则同一棵树会有两个"全量用时"。
- 变异复跑与 BI 的**口径差异**（本轮有意变更，非疏漏）：全量 harness **只跑一次**
  （24 条目连续运行、`rc=0`、collected 全程 **501**），另跑一次 harness 内那条 pytest
  命令取基线行（`rc=0 / 501 passed / 0 failed / 33.49s`），**不做** BI 那样的"登记文本
  收口后再全量复跑"。理由就是 §6 第 7 条：为补一行基线而重启全量 harness 的代价（变异体
  留在 `src/`）高于它补回的读数。还原证据改由三处共同背书——每条目 `finally` 的 sha256
  原字节断言、收口时全仓 `# mutation` 标记扫描（`src/` 命中 1 处，核对为
  `src/graph/workflow.py:487` 的 `mutation_advisor` 边注释，非残留）、`git status` 只余
  本轮 intended 改动。
- 复算脚本自身的收口（§6 第 8 条的处置）：语料探针在 2026-10-22 修复列表初始化后
  **重跑一次**，§3 全部读数逐位复现（1702/1594/108、57 份归档 / 2486 站点、10855 站点、
  10671 / 77 / 72 / 31 / 4、findings 非空 7866、盲区 1、`target_not_provided` 10702），
  并把那 **1 个盲区站点路径**打印出来点名；`ruff check` 与 `ruff format --check` 对该脚本
  归零。因该修复只动 `scripts/tools/`，`src/` 与 `tests/` 未变，其后的门禁链内 pytest
  即同一采集面的复跑，未再单独重跑确认跑。
- 静态面：`ruff check .` 全过；`ruff format --check .` **965 份已格式化**（BI 960 →
  **+5** = BJ 手册 / 新锁 / 变异脚本 / 语料探针 / 差额复核脚本，逐一对上）；mypy
  `Success: no issues found in 137 source files`（与 BI 同值，本轮未新增 `src/` 文件）。
- 门禁实测（第一次跑通的那次，单独执行、不与其他 pytest / 文档编辑重叠）：**rc=0**、
  墙钟 **198s**；链内 pytest（`-n 4 --dist loadfile`、**不带 `--cov`**，与带覆盖率读数
  不可互换）**11617 passed / 5 skipped / 0 failed、192.51s**（54 warnings；collected
  **11622**）。其余链步：双语文档 **0 警告 / 0 失败**；文档链接 strict **178 份文件
  （docs 159 / examples 4 / root 15）/ 830 条链接（内部 821 / 外链 9）/ 0 错误 / 0 警告**
  （BI 177/822 → +1 份手册 / +8 条）；env-budget **253/253** 无未登记新增；
  `check_baseline` 结构校验与数字漂移检查通过；状态通道 **136 个文件**无未声明键读写
  （与 BI 同值）；env-snapshot **84 开关 / 115 键 / 缺失 0**（扫描面同 136 文件）；
  model-fingerprint 近期无新批次，通过；工具版本一致（mypy 1.15.0 / ruff 0.16.3）；
  JSON 契约 **7/7** 调用点一致（文档数量表述 9 处全 [OK]）；严格 JSON **7274 份工件**
  （7272 严格 + 2 历史豁免 + 0 违规）、**304 份**源码写入点 0 违规——与 BI 同值，
  旁证本轮两只只读脚本**确实零写入**；报告→工件对账 [OK]（三臂不一致 0 项；T-10 严格
  29 行 / 25 可测、宽松 62 / 55；登记册 §1 覆盖率对账与 `coverage.xml` 实测相符，
  容差 ±0.20pp）；零断言 **454 份测试文件 / 0 违规**（BI 453 → +1 = BJ 锁文件）。
- 这条门禁读数**之前**还有一次 `rc=2` 的链外失败：`make gates` 在 lint 步 0s 退出、
  `ruff check .` 报 2 处 `F821`（§6 第 8 条）。**当时没有任何 gates 读数可引**，
  本册与双语登记文本也都没有引用过那次失败的"链"——它只作为缺陷与教训登记。
- 复验跑（§9 首条门禁读数落盘之后、双语 README / CHANGELOG / INDEX / 登记册的门禁句
  尚未补写之时，单独再跑一次 `make gates`）：**rc=0**、墙钟 **198s**、链内
  **11617 passed / 5 skipped / 0 failed、192.46s**（13 warnings；collected **11622**）。
  两跑之间**只有**墙钟、链内用时与 warnings 计数动过：把分步输出（非逐用例行）各取
  90 行、归一化时间与 warnings 计数后 `diff` **为空**——`965 份已格式化`、mypy 137 源
  文件、双语 0 警告 / 0 失败、文档链接 178/830/0 错误、env-budget 253/253、状态通道
  136 文件、env-snapshot 84 开关缺失 0、工具版本 OK、JSON 契约 7/7、7274 份工件
  0 违规 / 304 份写入点 0 违规、三臂对账 [OK] + 登记册覆盖率对账 [OK]、454 份测试文件
  0 违规**逐项相同**。warnings 计数（54 → 13）随 worker 分发顺序变化，属抖动，不作主张。
- 终跑（双语 README / CHANGELOG / INDEX / 登记册 / BASELINE 的门禁句与本册 §9 前数条
  回填之后，再单独跑一次 `make gates`，不与其他 pytest / 文档编辑重叠）：**rc=0**、
  墙钟 **197s**、链内 **11617 passed / 5 skipped / 0 failed、192.06s**（66 warnings；
  collected **11622**）。三跑之间**必须写清"逐行相同"的行数口径**：滤掉逐用例行与非
  读数行后每次得到 **88 行**门禁分步读数，归一化用时与 warnings 计数后**三跑逐行相同**
  （`diff` 空）；若把 pytest 的警告噪声行一起算，首两跑各 90 行相同、终跑 88 行——差的
  2 行是 `<unknown>:2: SyntaxWarning: invalid decimal literal`，由 worker 分发决定，
  **不属于门禁读数**，所以"90 行逐行相同"只对前两跑成立，终跑的等值主张一律按 88 行口径写。
- 本条与上一条写入后，剩下的改动只有双语 / 登记册 / BASELINE 里同一句终跑读数；它由下
  一条的门禁子集复验。**本节任何 rc / 用时都来自已经发生的链**——§6 第 9 条记的就是
  本条在真实跑之前曾被"照例"写出、发现后删除的现场。
- 子集复验（终跑之后只动门禁句，便直接跑会读到这些文本的那几道门禁，各自 `rc=0`）：
  `check_bilingual_docs.py --strict` **0 警告 / 0 失败**；`check_doc_links.py --strict`
  **178 份（docs 159 / examples 4 / root 15）/ 830 条（内部 821 / 外链 9）/ 0 错误 /
  0 警告**；`check_baseline.py` 结构校验通过；`check_baseline_numbers.py` 数字漂移通过；
  `check_zero_assert_tests.py` **454 份 / 0 违规**；`ruff check .` 全过、
  `ruff format --check .` **965 份已格式化**；文档锁子集
  `tests/test_ao_batch.py` + `tests/test_check_doc_links.py` +
  `tests/test_check_baseline_numbers.py` + `tests/test_markdown_table_integrity.py` +
  `tests/test_artifact_doc_consistency_gate.py` + `tests/test_audit_paper_numbers.py`
  **155 passed / 0 failed（5.01s、1 warning）**；基线数字一致性
  `TestBaselineNumbersConsistency` **3 passed**（`BASELINE.yaml` 声明 11617 与实收对齐，
  slack = skipped 5 + xfailed 0 + 1）。子集不含链内全量 pytest——它复验的是"这段文字
  改了之后门禁还读不读得动"，全量主张由上面三次 `make gates` 背书。
- 本轮改动全部未提交，未推送（工作区随收口提交一并入库；提交需另行授权）。

