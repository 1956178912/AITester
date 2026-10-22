# BL 轮：发布侧已经带 status、判定侧仍按空值判定——"没测成"被读成"测过了且没问题"（2026-10-22，零 LLM，$0）

**范围**：折叠链的**第五个面**。BH→BK 四轮各自收口一个模块的"读不懂 ⇒ 静默"，但都收在**发布侧**：
把 status 写进观测键。BL 轮量的是一句一直没验过的前提——**判定侧到底读不读这个键**。
消费面五处 = `src/graph/risk_approval.py`（`_contract_disclosure:123` + `_impact_factor:142/173` +
`assess_task_risk:202/242` + `build_risk_summary:284/326,352` 两个分支的键集合）、
`src/graph/debugger.py:918`（调用点把通道值取走）、`src/observability/agent_telemetry.py:148-152,198-215,282`
（新增 `check_unmeasurable` 失败模式：5 个 status 通道 × `error`/`unavailable`）、
`src/tools/patch_applier.py:507-511`（S2 危险 API 守卫接 `outcome_sink` 并披露）、
`src/agents/debugger.py:795-803`（静态类型层按 `static_check_status` 披露）。
发布面四处 = `src/graph/nodes.py:2867`（per-leg 通道 `contract_status`）、
`src/graph/nodes.py:1478`（trace 载荷带 `oracle_check_status`）、
`experiments/run_benchmark.py:1869`（成功行带 `contract_status`）、`src/graph/state.py:371`（声明通道）。
地基是 `src/utils/check_status.py:161` 的新原语 `status_for_check(outcomes, check)`。
**判定值与判定方向逐字节不变**：32 例新锁 + 变异 22 锚点全红 + 1 中性对照 0 红。

**结论先说**：`contract_missing_symbols=[]` 在判定侧一直是"契约成立"的证据，而它同时是
"这条腿没做"（`disabled`）、"这条腿读不懂"（`error`）、"这条腿的输入为空"三种成因的**共同承载值**。
BI 轮把 status 发布出来了，但 BL 轮的普查实测：**改前没有任何一个消费函数能接收 `contract_status`**
（探针 B1：`assess_task_risk` 形参表里就没有这个参数）。也就是说四轮下来"读不懂"仍在被读成"没问题"，
只是这次不是因为没人写，而是**写了没人读**。本轮把三件事分开：按腿取 status（聚合值不能冒充单腿）、
消费侧双读（值 + status 才是证据）、观测侧把 status≠ok 认成失败模式。**没有把任何 `error` 翻成拒绝，
也没有把任何一次崩溃翻成静默。**

---

## 1. 缺陷：status 在场，判定侧却没有读者

### 1.1 承载值复用是折叠的最后一环

BD→BK 的口径已经把"检查完成且零疑点"和"检查没做成"在**发布侧**分开了：

```python
record_check_outcome(sink, "naming_contract", CHECK_ERROR, unparseable)  # 读不懂
record_check_outcome(sink, "naming_contract", CHECK_OK)  # 扫过且无疑点
```

两条腿的返回值都是 `[]`（`check_naming_contract` 返回 `(ok, missing)`，`missing` 两种成因下同为 `[]`）。
可测量性走 sink，判定值走返回值——设计本身没错，错在**下游只消费返回值**：

- `risk_approval._impact_factor` 用 `if contract_missing_symbols: 提升影响因子 else: 视作低风险`；
- `build_risk_summary` 落盘 `contract_missing_symbols`，读的人（报告侧、归档侧）同样只看这个键；
- MAST 失败模式里没有任何一条会因为"status=error"而命中——本轮之前 `_PATTERN_DETECTORS` 有 11 条模式，
  没有一条读 status 通道。

### 1.2 实测：改前消费面为零

探针 A（改前，未去重口径）与探针 B1/B4（形参面、调用点实参面，与去重无关）：

| 量 | 改前 | 改后 | 口径可比性 |
|---|---|---|---|
| `assess_task_risk` 形参含 `contract_status` | **False** | True（`risk_approval.py:210`） | 可比（按名核对） |
| `graph/debugger.py` 调用点带 `contract_status` 实参 | 0 处 | 1 处（`:909`/`:918`） | 可比 |
| `build_risk_summary` 落盘键集合带 status | 否 | 是（两分支 `:326` `:352`） | 可比 |
| `contract_status` 键名普查（发布/判定读点/声明） | 3 / 2 / 0 | 6 / 4 / 1 | **不可相减**（见 §3.1 量具勘误） |
| `static_check_status` 变量判定读点（A2） | 0 | **2** | 可比（A2 不经去重） |
| `oracle_check_status` 变量判定读点（A2） | 0 | **1** | 可比 |
| `mypy_findings_count` 变量判定读点（A2） | 1 | 2 | 可比 |

### 1.3 为什么"再补一个 status 字段"不解决问题

前四轮每补一个通道，判定侧的读者数量都没变（`static_check_status` / `safety_check_status` /
`oracle_check_status` 三个通道的**键名判定读点改前全是 0**，见探针 A/final2 同名行）。
字段是廉价的，读者才是收口。本轮因此把工作量放在**读**上，并把"status≠ok"升格成一个可被 MAST
归因的失败模式，而不是又一次"多写一个键"。

---

## 2. 处置：按腿取 status + 消费侧双读（判定不动）

### 2.1 新原语：聚合值不能冒充单腿

`src/utils/check_status.py:161` `status_for_check(outcomes, check)`：只挑 `check` 名匹配的那几条
取最差者；**该腿没记录返回 `None`**。这一步是必须的：`nodes.py` 的 `safety_check_status` 是
命名契约 + 危险 API 两道独立预检的 worst-of 聚合，拿它给契约腿定口径，会把"危险 API 腿读不懂"
错记到契约头上（变异锚点 M17 就是这条：改成用聚合值冒充后，新锁必须变红）。

消费侧读法约定：

| status | 含义 | 空列表能不能当证据 |
|---|---|---|
| `ok` | 做了且可信 | 能 |
| `disabled` | 按开关没做 | 不能（本轮未检查） |
| `unavailable` | 想做做不成（后端缺失/超时） | 不能 |
| `error` | 读不懂 / 自身失败 | 不能（假干净） |
| `None` | 这条腿本轮根本没记录 | 不能，但**不是**"没测成" |

`None` 与 `error` 的区分是本轮的纪律点：把 `None` 也当不可测量，会让"没跑这条腿"的历史行
全部命中失败模式——归档探针 C 正是按这条写的（键全缺席 ⇒ 不命中）。

### 2.2 消费面五处

1. `risk_approval._contract_disclosure(contract_status)`（`:123`）：只在 `status` 非空且 `!= ok` 时
   产出一段 `contract_unmeasurable(<status>): ...` 文本；空/ok ⇒ 空串。
2. `_impact_factor(..., contract_status=None)`（`:142/173`）：把上面的文本**追加进 note**，
   `factor` 一个字节都不动——这是"只披露不改判"的实现约束。
3. `assess_task_risk(..., contract_status=None)`（`:202/242`）：透传；G2 判定不变，另在
   `logger.warning("G2 缺失符号列表不可作证据（判定不变）：%s", ...)` 落一条可观测记录。
4. `build_risk_summary(..., contract_status=None)`（`:284`）：**enabled / disabled 两个分支都写
   `contract_status` 键**（`:326` `:352`）。只在一个分支写等于把"开关关着"这件事变成"键不存在"，
   下一轮又会退化成空值判定（变异锚点 M8）。
5. `graph/debugger.py:918`：调用点 `contract_status=state.get("contract_status")` ——
   没有这一行，前面四处参数全是装饰（变异锚点 M9）。

另外两处读者：
`src/agents/debugger.py:795` 把 `static_check_status not in (None, CHECK_OK)` 变成一条 warning
（此前只有一句注释约定"读 count 要结合 status"，没人执行）；
`src/tools/patch_applier.py:507` 用 `status_for_check(_guard_outcomes, "dangerous_api")` 取本腿
status，非 ok 时披露，`added` 返回值照旧。

### 2.3 观测侧：第 12 条失败模式

`agent_telemetry` 新增 `_UNMEASURABLE_STATUS_KEYS`（5 个通道名）+ `_UNMEASURABLE_STATUSES`
（`error` / `unavailable`）+ `_pattern_check_unmeasurable`，注册为 `"check_unmeasurable"` →
MAST `"Inadequate verification"`。**判定表**（探针 B5，逐条实测）：

```
5 个 status 键全缺席（归档形状）  -> False
全部 ok                          -> False
全部 disabled（按设计未检查）      -> False
contract_status=error            -> True
oracle_check_status=unavailable  -> True
check_status=ERROR（大小写折叠）   -> True
contract_status=None（没记录）     -> False
```

`_flatten_record` 同步把 trace JSONL 的 `output` 内层键抬平，否则这条模式永远读不到
`oracle_check_status`（变异锚点 M14）。

### 2.4 判定不变性承诺

本轮**没有**新增任何"因 status 不好而拒绝补丁 / 降置信 / 改等级"的分支。可核验的方式：
32 例锁里每条披露断言都成对写"文本变了 + 判定值没变"；变异侧反向锁——把披露翻成拒绝
（M6 `factor = max(factor, 0.9)`、M16 S2 翻成拒绝）必须变红，因为锁里钉了
`_impact_factor(..., contract_status=CHECK_ERROR) == _impact_factor(..., contract_status=None)`。

---

## 3. 测量（全部实测，改前/改后分开）

### 3.1 键名读者普查与量具勘误

final2（改后，去重口径 `(文件, 行号, 键, 构造)`，每键印"计数 == 印出的读点行"对账，**对账 = True**）：

```
[contract_status]        发布=6 判定读点=4 转发=0 声明=1
[contract_missing_symbols] 发布=1 判定读点=3 转发=0 声明=1
[static_check_status]    发布=4 判定读点=0 转发=2 声明=1
[safety_check_status]    发布=1 判定读点=0 转发=0 声明=1
[oracle_check_status]    发布=3 判定读点=0 转发=1 声明=1
```

**勘误（登记进廉洁分册 §56）**：探针 A（改前）用未去重口径，`contract_status` 记 3/2/0；
d→e 之间量具又改过一次构造归类，`判定读点` 从 5 到 4。所以这两个键的**改前/改后差值不能直接相减**，
差值里夹着量具变更。可比的只有按名核对的形参面 / 调用点实参面 / A2 变量口径三张表（见 §1.2）。
教训写成纪律：**同一把尺子必须在改前改后各跑一次；中途换尺子就要重新跑改前，否则只登记现值。**

### 3.2 三条腿读法（名字看不到的读者）

- **A2 变量口径**（不经去重）：`static_check_status` 变量判定读点 0 → **2**，
  `oracle_check_status` 0 → **1**，`mypy_findings_count` 1 → **2**。
- **D 形参口径**（`*_status` / `outcome_sink` / `sink` 结尾形参）：读者函数 **22** 个、
  判定读点合计 **76**、其中显式比较 **5**；`status_for_check(...)` 调用点 **2** 处
  （`nodes.py:2867`、`patch_applier.py:507`）。
- **D2 词汇口径**（判定构造里出现 `CHECK_*`，与键名无关）：**58** 个站点，
  按构造 `operator` 12 / `call-arg` 46——绝大多数 `call-arg` 是发布侧把常量交给
  `record_check_outcome`，只有 operator/condition 是真读。
  腿 D/D2 是本轮新增的量具，**改前树未测**，故只登记现值、不作增减主张。

### 3.3 归档零影响判据（`experiments/results/**/*.json`）

口径：递归展开每个 JSON 里的所有 dict；"出现"= 该键在某个 dict 的键集合里出现一次。

```
文件=1702  可解析=1594  解析失败={'JSONDecodeError': 108}
[static_check_status / safety_check_status / oracle_check_status / contract_status / check_status]
                              出现=0（五个键各自）
[contract_missing_symbols]    出现=8865  None=8853  非空=12（len=1 ×9、len=3 ×1、len=5 ×2）
```

五个 status 键在归档里**一次都没出现过** ⇒ 新读者不会重判任何历史行；
`contract_missing_symbols` 的 8865 次出现里 8853 是 `None`（不是空列表）——
"缺失符号为空"这条证据在归档层面几乎从未成立过，这既是本轮读法修正的必要性，
也说明改前改后取值分布逐位相同（同一探针改前后各跑一次，读数一致）⇒ **历史读数零影响**。

### 3.4 回归与覆盖（实测）

- 预登记全量跑 `make test-cov` 同口径（xdist `-n 4 --dist loadfile` + `--cov`）：
  **11703 passed / 1 failed / 5 skipped / 35 warnings，198.00s，collected 11709**。
  唯一红是基线数对账守卫（`BASELINE.yaml` 的 11672 尚未随 32 例新锁刷新），非功能回归。
- 覆盖率：**19393/19904 行 = 97.4327%**（两位小数 97.43）、**7105/7532 弧 = 94.3309%**（两位 94.33）；
  分母 +30 行 / 覆盖 +30 行 ⇒ 未覆盖 **511** 与 BK 登记逐位相同；分母 +12 弧 / 覆盖 +12 弧 ⇒
  缺弧 **427** 逐位相同。本轮新增的按腿取 status、双读披露与失败模式读者全部被锁执行。
- `graph/nodes.py` 852/853 行（99.88%）、branch 323/326（99.08%）；
  +13 行 / +4 弧跨 BD→BL 整条未提交栈，**不作 BL 单独归因**。
- 顺带纠 BK 的两处四位小数：BK 登记写 97.4300% / 94.3200%，按 19363/19874 与 7093/7520 除得值
  应为 **97.4288%** / **94.3218%**（两位小数同为 97.43 / 94.32，判读不变）。BL 起四位小数一律写除得值。
- 确认跑（BASELINE 刷新后）：**11704 passed / 5 skipped / 0 failed、209.29s / rc=0**（39 warnings；collected 11709；命令 `pytest tests/ -n 4 --dist loadfile --cov=src --cov-report=xml`，**不带 `--cov-branch`**）。
- 同轮 `make test-cov` 全口径跑（含 `--cov-branch` 与 `COVERAGE_FILE` 隔离）：**11702 passed / 2 failed / 5 skipped、210.65s / rc=2**。两条失败同属 `tests/test_artifact_doc_consistency_gate.py`，成因是**该跑开始时**仓库根的 `coverage.xml` 还是上一跑落下的无分支数据版本（`branches-valid="0"`），门禁拿它去对 §1 的行/分支声明必然不吻合；单文件复跑 **32 passed**、门禁本体当场 **rc=0**（含「§1 声明 vs `coverage.xml` 实测 ±0.20pp」对账）。**登记为口径事故而非产品回归**：跑与跑之间 `coverage.xml` 是被覆盖写的共享工件，用它做对账的测试必须确认它来自同一次带分支的采集。

---

## 4. 回归锁（`tests/test_bl_status_readers_outcome.py`，32 例）

| 节 | 例数 | 钉什么 |
|---|---|---|
| §1 `TestStatusForCheck` | 5 | 按腿挑、无记录 ⇒ None、非 dict 过滤、缺 status 键 ⇒ error、单腿 ≠ 聚合 |
| §2 `TestRiskApprovalDoubleRead` | 8 | 披露只在 status≠ok 出现、`factor` 逐位不变、两分支键集合、warning 落一条 |
| §3 `TestPublishSide` | 6 | `nodes.py` per-leg 通道、trace 载荷带 oracle status、benchmark 行带 contract_status、state 声明 |
| §4 `TestDangerousApiConsumer` | 5 | S2 取本腿 status、读不懂不冒充"没有新增危险调用"、判定值不变 |
| §5 `TestUnmeasurableFailurePattern` | 5 | 7 行判定表 + **字面量钉死 5 个通道键名**（防自证循环） |
| §6 `TestStaticLayerConsumer` | 3 | `agents/debugger.py` 按 `static_check_status` 披露、ok/None 不披露 |

两处值得单独说的锁：

1. **字面量键集合**（§5）：`assert set(at._UNMEASURABLE_STATUS_KEYS) == {5 个字面量}`。
   改前这条锁写成 `for key in at._UNMEASURABLE_STATUS_KEYS: ...`——用被测集合自己遍历，
   删掉一个键它跟着变短而不是变红（变异 M11 存活的原因）。这是**量具的自证循环**，
   与 §3.1 的勘误同族，登记进廉洁分册。
2. **单腿 ≠ 聚合**（§1/§6）：构造真正可达的非对称形状（`PATCH_CONTRACT_CHECK=false` 使契约腿
   `disabled`，同时原文不可解析使聚合值 `error`），断言 `contract_status != safety_check_status`。
   第一版用"契约 ok + 危险 API error"，那个组合在 `safe_apply_patch` 里**不可达**
   （`ast.parse` 前置硬闸先拦下），于是 M17 存活。

---

## 5. 变异验证（`scripts/tools/bl_mutation_verify.py`，22 锚点 + 1 中性对照）

纪律沿用 BH→BK：基线全绿 → 锚点唯一 → `compile()` → 同锚点 collected 数一致 → 跑受影响面 →
`finally` 按原字节写回并 sha256 断言 → 扫 `# mutation` 残留。**绝不用 `git checkout` / `git stash`。**

22 个锚点覆盖三族：读法族（M1 缺腿当 ok、M2 忽略 `check` 名、M3 无 status 键当 ok、
M5 把 None 当不可测量）、披露族（M4 永不披露、M6 披露翻成改判、M7 消费者 warning 丢失、
M8 只在一个分支写键、M9 调用点不取通道值、M15/M22 静态层分支静默、M16 S2 翻成拒绝、
M18/M19/M20/M21 发布面四处各断一处）、观测族（M10 词表删 `unavailable`、M11 删通道键名、
M12 模式体 `return False`、M13 模式不注册、M14 抬平失效、M17 聚合冒充单腿）。
中性对照 M23 只改注释措辞，必须 0 红。

结果（复跑日志 `/tmp/bl_mut_final.log`，墙钟 86s，基线 `rc=0 / red=0 / collected=32`）：**22/22 击杀、中性对照 `OK-NEUTRAL` 0 红、异常 []**。逐锚点红数 M1→M22 = **2 / 3 / 1 / 2 / 1 / 3 / 1 / 1 / 1 / 1 / 1 / 3 / 2 / 1 / 1 / 1 / 1 / 1 / 1 / 1 / 1 / 1**；最宽三张网是 M2（3，忽略 `check` 名）、M6（3，把披露翻成改判）、M12（3，模式体 `return False`）。`# mutation:` 残留扫描 `src/` **0 命中**，跑后 `tests/test_bl_status_readers_outcome.py` + BI 锁文件 **82 passed**。
首轮 **M17 存活**，根因与修法见 §4 第 2 条与 §6 第 2 条——存活说明语料缺一个可区分样本，
不是变异写坏了。

---

## 6. 踩坑与自纠（本轮实测发生的）

1. **自证循环的量具**：用被测集合自身遍历来"覆盖全部键"，删键不会红。改为字面量集合断言（M11 击杀）。
2. **不可达的变异体**：为"聚合 vs 单腿"先写了 `ok + error` 组合，但该组合在真实调用链上不可达
   （`safe_apply_patch` 的 `ast.parse` 硬闸先拦），M17 因此存活。可达性等价的非对称形状是
   `disabled + error`，须从真实开关出发构造，不能在单元里凭想象。
3. **量具中途换口径**：探针 A 未去重、d→e 改了构造归类，导致改前/改后差值含仪器变更。
   只登记可比表，其余标"不可相减"。
4. **PERF401 + ruff format**：新锁文件两处 `append` 循环被 ruff 指为可推导式；修完必须再跑
   `ruff format`（1 文件被重排）后重跑 31→32 例，别只看 lint rc。
5. **文档字符串里的嵌套 ASCII 引号**：中文行文里写 `'''.` 直接把源码截断——语法错误在 `compile()`
   阶段暴露，但 Edit 的 old_string 已因自动格式化对不上，只能先 grep 定位再改。
6. **归档里 `None` 不是 `[]`**：`contract_missing_symbols` 8865 次出现里 8853 次是 `None`。
   如果新读者把 `None` 也当"不可测量"，历史行会被整批改判——这是 §2.1 那条区分的实证依据。

---

## 7. 边界与未收口部分（按名登记，不写成"已排除"）

1. **只收口五个 status 通道的消费面**：`check_status`（BK 的编辑意图通道）有声明与发布，
   但 §3.1 显示其**键名判定读点仍为 0**；本轮只让它进了 `_UNMEASURABLE_STATUS_KEYS`
   （观测侧有读者，判定侧仍无）。
2. **`safety_check_status` / `oracle_check_status` / `static_check_status` 的判定读点仍为 0**：
   A2 变量口径有读者（2/1/2），但那是模块内部局部变量，不通过键名读取；键名普查看不到别名读者，
   这正是腿 D/D2 存在的理由，也说明"判定读点=0"不等于"没有读者"。
3. **S2 的 patched 侧 `error` 在 `safe_apply_patch` 路径上不可达**（前置 `ast.parse` 硬闸先拦）。
   本轮仍给这条腿配了披露与锁，是为了守卫本身被别处调用时不折叠；不主张该腿在生产路径上有实例。
4. **只有 `oracle_check_status` 真正落到 trace JSONL**：`contract_status` / `static_check_status`
   等通道进 trace 的路径本轮没有补，`check_unmeasurable` 对它们的命中依赖 state → 归档行 → 报告读端，
   而不是 trace。
5. **判定方向仍然一律"披露优先"**：`error` 不会翻成拒绝。若产品口径要"契约腿不可测量即阻断"，
   那是另一轮的决策（要同时动 G2 与门禁），本轮不预判。
6. **`build_risk_summary` 的 disabled 分支写 `contract_status` 但值可能为 `None`**：
   这是"开关关着 + 本轮没记录"的真实形状，读方需按 §2.1 表读；本轮不加"缺键即 error"的推断，
   因为它会把历史行也拖进来（与 §3.3 的零影响判据冲突）。
7. **报告/归档读端未接**：`experiments` 侧读 `contract_missing_symbols` 的脚本仍按空值判定
   （本轮只补了**写侧**带 `contract_status`）。读端收口留给下一轮。

---

## 8. 复算命令（零 LLM、零写入、可逐条重跑）

```bash
# 1) 本轮 32 例新锁（先看 collected=32，再看 rc）
.venv/bin/python -m pytest tests/test_bl_status_readers_outcome.py -q --collect-only
.venv/bin/python -m pytest tests/test_bl_status_readers_outcome.py -q --basetemp=/tmp/pt_bl_lock

# 2) 邻近面（消费/发布两侧既有锁，看 collected 是否 0 漂移）
.venv/bin/python -m pytest tests/test_risk_approval_g2.py tests/test_bi_static_precheck_unmeasurable.py \
  tests/test_bj_oracle_unmeasurable.py tests/test_bk_ast_guard_capture.py \
  tests/test_bg_static_check_outcome.py tests/test_untrusted_exec_env.py -q --basetemp=/tmp/pt_bl_neigh

# 3) 归档零影响探针（1702 文件 / 5 个 status 键出现 0 次）——探针脚本本轮未入库，
#    口径与判据由 tests/test_bl_status_readers_outcome.py 的 test_archive_caliber_never_hits 锁住；
#    重跑请用 §3.3 打印的三条口径（递归展开所有 dict / 计数=键出现次数 / 取值分布按形状归类）。

# 4) 变异验证：22 锚点 + 1 中性对照（会临时改写 src/，finally 按 sha256 还原）
.venv/bin/python scripts/tools/bl_mutation_verify.py 2>&1 | tee /tmp/bl_mut_final.log
#    中止过就必须扫残留，并复跑 §1 的 32 例：
grep -rn "# mutation" src/ scripts/ || echo "无残留"

# 5) 门禁链（最后、单独跑，不要接管道）
start=$(date +%s); make gates > /tmp/bl_gates.log 2>&1; rc=$?; end=$(date +%s)
echo "rc=$rc wall=$((end - start))s"
```

---

## 9. 收口批注（2026-10-22）

**本节的每一条读数都必须在命令实际跑完之后才填写；跑之前本节写"尚未执行"。**

- 确认跑：**11704 passed / 5 skipped / 0 failed、209.29s / rc=0**（39 warnings；collected 11709）。`make test-cov` 全口径跑 210.65s / rc=2，两条失败是 §3.4 记录的 `coverage.xml` 口径事故，单文件复跑 32 例全绿、门禁本体 rc=0。
- 变异复跑：**86s，22/22 击杀**（红数 2/3/1/2/1/3/1/1/1/1/1/3/2/1/1/1/1/1/1/1/1/1），中性对照 0 红，`src/` 残留 0，跑后 82 例锁全绿。
- 覆盖率读数由 **`make test-cov` 全口径跑**（含 `--cov-branch` 与 `COVERAGE_FILE` 隔离）复核：`coverage.xml` root `lines-valid=19904 / lines-covered=19393 / branches-valid=7532 / branches-covered=7105` ⇒ 与 §3.4 登记的预登记跑**逐位相同**（在 ±2 行抖动域内，实测零漂移）；逐文件 `utils/check_status.py` **70/70 行 + 24/24 弧 = 100%**、`graph/risk_approval.py` **124/124 + 42/42 = 100%**、`graph/state.py` 126/126 + 2/2 = 100%、`agents/debugger.py` 351/351（弧 112/120）、`graph/debugger.py` 251/251（弧 86/94）、`observability/agent_telemetry.py` 110/121（11 条未覆盖行是既有其它模式分支 188 / 224-250 / 338 / 345-347，BL 新增的 `_pattern_check_unmeasurable` 198-215 逐行被执行）、`tools/patch_applier.py` 480/494（弧 220/234）、`graph/nodes.py` 852/853（弧 323/326）。
- `ruff format --check .` 文件数：**974 files already formatted**（BL 轮收口实测，较 BK 登记的 970 净增 4，按名核对 = `tests/test_bl_status_readers_outcome.py` + `scripts/tools/bl_status_readers_probe.py` + `scripts/tools/bl_mutation_verify.py` + 本手册）；本手册代码围栏内一处注释对齐由 `ruff format` 就地重排，不新增文件。`ruff check .` 全绿、`mypy src/ config.py` **Success: no issues found in 137 source files**（本轮未在 `src/` 新增文件）。
- `make gates` rc 与墙钟：**两跑 rc=0**、墙钟 **213s / 214s**（各自 `start=$(date +%s)` / `end=$(date +%s)` 成对采集，首跑在本节回填之前、终跑在回填之后，两次都单独执行、不与其他 pytest 或文档编辑重叠；日志 `/tmp/bl_gates.log` 与 `/tmp/bl_gates_final.log`）。链内 **18 步命令全绿**，pytest 步两跑同判 **11704 passed / 5 skipped / 0 failed**（用时 207.16s / 208.34s、warnings 54 / 46；collected 11709；xdist `-n 4 --dist loadfile`、**不带 `--cov`**），链尾分步读数两跑逐字节相同。分步读数：`check_ast_parse_guards.py` 136/78/20/0/20/19（与 BK 链外自测逐位相同）、`check_state_contract.py` 136 文件无未声明键读写、`check_env_budget.py` 253/253、`check_zero_assert_tests.py` 扫描 456 个测试文件零断言 0、`check_artifact_doc_consistency.py` 三条 `[OK]`（含登记册覆盖率对账，`coverage.xml` = 本轮 `make test-cov` 全口径工件）。
- 终跑之后，门禁读数还在 README×2 / CHANGELOG×2 / INDEX×2 / 本节与 `BASELINE.yaml` 注释文本里回填过两轮（第一轮写入首跑读数、第二轮把表述改成"两跑"，并补 `suite_seconds` 的确认跑补记与 `gates.local_gates_target` 的 BL 链内读数；**`BASELINE.yaml` 的键值本身一字未动**，只改注释）：
  未动 `src/`、`tests/`、`scripts/` 任何一行 ⇒ 全量 pytest 的判读数不可能改变，链未在此之后第三次重跑，本册因此
  **不主张"最终树跑过链"**，只主张"最终树与终跑的差异面 = 文档文本"。回填后单独复验文档消费面：`make docs-check`
  **rc=0**（180 份文件 / 846 条链接 / 错误 0 / 警告 0）、`make baseline-check` **rc=0**、`make zero-assert` **rc=0**
  （456 个测试文件、零断言 0）、`make artifact-doc-consistency` **rc=0**、`ruff format --check .` **974 files already
  formatted**、文档锁定向跑 **119 passed / 10.32s**（`test_markdown_table_integrity` + `test_ao_batch` +
  `test_2026_10_10_optimization_batch` + `test_prompt_artifacts_gate` + `test_artifact_doc_consistency_gate`）。
  再把面扩到**所有读文档与 `BASELINE.yaml` 的测试**（`grep -rl "BASELINE.yaml|CHANGELOG|README|docs/INDEX|"
  `PROJECT_STATUS_REGISTER|MEASUREMENT_INTEGRITY` 命中 **38 个文件**）：**1037 passed / 52.43s**
  （`-p no:cacheprovider`、不带 `--cov`）——本轮回填改到的文本只有这些文件会消费。
- **代码面未被改动这一点按 mtime 核对过**：终跑（08:42:10 结束、214s ⇒ 起于 08:38:36）之后，`src/` 最新源文件停在
  08:21:51、`tests/` 最新停在 08:25:19、`scripts/` 最新停在 07:40:25，全部早于终跑 ⇒ 本册"两跑覆盖的就是当前代码树"
  成立，差异面只剩文档与 `BASELINE.yaml` 注释。两跑用的都是**同一棵工作树**，故采集面同为 **collected 11709**
  （`4 workers [11709 items]`）、`coverage.xml` 同为 19393/19904 行与 7105/7532 弧（`lines-valid` / `branches-valid` 逐位相同）。
- 残留检查：`src/` 内 `# mutation:` 标记 0 处、`git status` 无未预期的临时工件入库、全部变更**未提交**（按用户
  指示堆叠在未提交变更上）。
