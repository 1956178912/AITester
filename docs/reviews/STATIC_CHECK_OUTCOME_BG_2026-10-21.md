# BG 轮：静态类型检查的「不可测量 → 假干净」收口（2026-10-21，零 LLM）

**范围**：`src/tools/type_repair.py` 的两个检查器后端
（`_run_mypy_findings` / `_run_pyright_findings`）与静态层聚合
（`type_repair_layer`），以及观测键在 `src/graph/state.py`、
`src/agents/debugger.py`、`src/graph/debugger.py`、
`src/tools/deterministic_repair.py` 的接线。这是 F03 缺陷族的相邻形态：
pytest 侧的「rc==0 不等于有效通过」收口于 BA–BF，本轮处理**外部静态
检查器**侧的同类问题——**检查器没跑成时，返回空 findings 与"检查完成且
零疑点"不可区分**。

**结论**：三态收口为四值（`ok` / `disabled` / `unavailable` / `error`），
每次检查器尝试经 `outcome_sink` 记录 `{backend, status, reason}`，静态层
聚合为 `static_check_status` / `static_check_outcomes` 并随 debugger 结果
写入图状态。`status != "ok"` 时 `findings=[]` / `mypy_findings_count=0`
**不再是"无类型问题"的证据**。**25 例新锁 + 变异 8 锚点全红
（1/3/1/2/1/1/3/2）+ 中性对照 0 红**；真语料 **170/170 份归档结果
`TYPE_CHECK_ENABLE` 均为 `null`**，开关默认关闭 ⇒ 历史读数零影响、
零回填。**未提交**（随收口提交一并入库）。

---

## 1. 缺陷：四条被折成同一个 0 的返回路径

改前两个检查器在下列路径一律 `return []`：

| # | 触发 | 改前返回 | 改前读数 |
|---|---|---|---|
| 1 | `TYPE_CHECK_ENABLE` 关 / 后端未选中 / 空输入 | `[]` | `mypy_findings_count=0` |
| 2 | 工具未安装（`ImportError` / CLI 与包均缺席） | `[]` | 同上 |
| 3 | 工具在但没跑成：超时、崩溃、退出码异常 | `[]` | 同上 |
| 4 | 工具跑完但报告不可信：空 stdout、JSON 损坏、缺 `generalDiagnostics` | `[]` | 同上 |
| 5 | 工具跑成且确实零疑点 | `[]` | 同上 |

第 5 行是唯一可以当证据的 0；第 3/4 行说明**本轮没有任何可信的类型
证据**，但在旧实现里与第 5 行逐字节相同。下游只能在
`mypy_findings_count == 0` 上做推断——"检查器崩了"被读成"补丁类型干净"。
pyright 更宽：`--outputjson` 报告结构损坏（非对象 / 缺
`generalDiagnostics`）时，旧代码 `report.get(...) or []` 静默当作空诊断，
连文本兜底都不会触发。

## 2. 处置：outcome_sink + 四值聚合

### 2.1 状态语义

| status | 含义 | 空 findings 可否作证据 |
|---|---|---|
| `ok` | 检查器执行完成且报告结构可信 | **可以**（"检查完成且零疑点"） |
| `disabled` | 开关关 / 后端未选中 / 输入为空：按设计未检查 | 不可以（未检查） |
| `unavailable` | 工具未安装：预期降级 | 不可以（不代表干净） |
| `error` | 工具在但未产出可信报告（超时/崩溃/rc 异常/报告损坏） | **不可以**（不可测量） |

聚合顺序：**任一 `ok` ⇒ `ok`；否则 `error` > `unavailable` > `disabled`**。
"任一 ok"保证 pyright 失败后回退 mypy 成功时整体仍可测量；`error` 优先于
`unavailable` 保证"一个工具缺席 + 另一个工具崩了"不会被读成"只是没装"。

### 2.2 逐点判定

| 后端 / 路径 | 判定 | reason |
|---|---|---|
| mypy 开关关 / 空输入 | `disabled` | `type_check_disabled` / `empty_input` |
| mypy 未安装 | `unavailable` | `mypy_not_installed` |
| mypy rc 0 / 1 | `ok`（0=无错误、1=有错误，均为可信报告） | — |
| mypy rc >= 2 | `error` | `mypy_rc_<n>` |
| mypy 异常 | `error` | `mypy_exception` |
| pyright 开关关 / 后端未选中 / 空输入 | `disabled` | `type_check_disabled` / `backend_not_selected` / `empty_input` |
| pyright CLI 与包均缺席 | `unavailable` | `pyright_not_found` |
| pyright 超时 | `error`（优先于其他判定） | `pyright_timeout` |
| pyright rc 非 0/1（含 `None`） | `error` | `pyright_rc_<n>` |
| pyright 空 stdout | `error` | `pyright_empty_output` |
| pyright JSON 损坏 / 非对象 | `error` | `pyright_invalid_json` |
| pyright 缺 `generalDiagnostics` | `error` | `pyright_missing_diagnostics` |
| pyright 报告可信 | `ok` | — |
| pyright 异常 | `error` | `pyright_exception` |

`generalDiagnostics` 缺失被单列：pyright `--outputjson` 恒含该键（零诊断
也是 `[]`），缺失/类型错误说明报告结构不可信，不能当作"无诊断"。

### 2.3 行为差异

- **findings 不丢**：pyright 超时/rc 异常但已解析出诊断时，原诊断仍进入
  `findings`；文本兜底同样保留。但只有 `ok` 才允许把**空** findings 当
  证据——"有疑点"与"可信地没有疑点"是两件事。
- **warning 可审计**：聚合为 `error` 时静态层发一条 warning，点名
  `backend=status:reason`，日志里不再需要靠猜。
- **观测键必须声明**：`static_check_status` / `static_check_outcomes` 在
  `State` TypedDict 显式声明，否则 LangGraph 静默丢弃（M14 的同一坑）；
  `deterministic_repair` 的确定性结果补齐同键，保持 `debug()` 键集合口径。
- **早退路径也有状态**：`type_repair_layer` 在 `if not findings: return
  result` 之前构造 result，因此**空 findings 的"假干净"路径本身携带
  status**——这正是本轮要观测的路径。

## 3. 真语料测量（改前 / 改后）

### 3.1 开关默认关闭，归档零影响

`_static_type_check_enabled()` 走 `env_flag("TYPE_CHECK_ENABLE")`，默认
`false`。全仓普查：

- 生产/实验代码中只有 `experiments/run_benchmark.py:4359` 把该键列入
  **环境快照**（provenance），没有批次配置把它置 true；
- `experiments/results/` 下 **170 份归档结果**的 `"TYPE_CHECK_ENABLE"`
  值全部为 `null`（`grep -rho '"TYPE_CHECK_ENABLE": [^,}]*'` 汇总：
  `170 "TYPE_CHECK_ENABLE": null`）；
- 启用该开关的路径只在单元测试里以 mock 检查器出现，不调用真实 LLM。

因此改前 / 改后在真实语料上的类型层读数均为"未启用"；本轮新增的是
**未启用时的可区分状态**（`disabled` + reason），而不是重算历史数字。

### 3.2 改后默认路径读数

开关关闭时静态层结果为 `static_check_status="disabled"`、
`static_check_outcomes=[{"backend":"mypy","status":"disabled",
"reason":"type_check_disabled"}]`，`mypy_findings_count=0` 保留历史口径。
任何实验若把 `mypy_findings_count=0` 与 `static_check_status="ok"` 配对
读取，才能主张"检查完成且无类型疑点"。

## 4. 回归锁

`tests/test_bg_static_check_outcome.py`（**25 例**）：

- `TestMypyOutcome`（7）：开关关 / 空输入 → disabled；未安装 →
  unavailable；rc>=2 → error；异常 → error；rc1 → ok；rc0 → ok。
- `TestPyrightOutcome`（12）：超时 → error；rc 2/3/−9（参数化 3 例）→
  error；空 stdout / JSON 损坏 / 非对象 / 缺键 → error；干净报告 → ok；
  rc1 带诊断 → ok；文本兜底有 finding 但**不** ok；不可用 → unavailable。
- `TestLayerAggregation`（4）：**核心假干净锁**——检查器异常时
  `findings==[]`、`mypy_findings_count==0`，但 `static_check_status=="error"`
  且 outcomes 为 `[{"backend":"mypy","status":"error",
  "reason":"mypy_exception"}]`，同时捕获"静态类型层不可测量" warning；
  pyright error + mypy ok → 整体 ok（outcomes 顺序 `pyright, mypy`）；开关
  关闭 → disabled。
- `TestStateObservationKeys`（2）：TypedDict 声明两键；
  `create_initial_state` 默认 `None`（区分"本轮未执行"与"执行了但 error"）。

受影响面（type_repair / debugger / state 相邻套件）全绿；既有
`tests/test_type_repair_more_branches.py` 的 pyright mock 保持
`returncode=0` / `timed_out=False` 的干净口径，新增状态判定不改变旧断言。
`tests/test_batch_iv.py` 的 `debug()` 键集合契约补入两键（用例数不变，
防止新键在下游被静默丢弃）。

## 5. 变异验证

`scripts/tools/bg_mutation_verify.py`：8 锚点 + 1 中性对照。纪律：干净
副本先全绿（25 collected）、逐锚点 `compile()` + collected 数核对、跑完
按 sha256 原字节还原（不用 git checkout / stash）。

| 锚点 | 红数 | 被谁抓住 |
|---|---:|---|
| M1 pyright 超时门关闭 | 1 | `test_timeout_records_error` |
| M2 pyright rc 门关闭（恒真） | 3 | rc 2/3/−9 三条参数化 |
| M3 空 stdout 判成干净 | 1 | `test_empty_output_records_error` |
| M4 JSON 损坏不记 report_error | 2 | JSON 损坏 + 文本兜底不 ok |
| M5 缺 `generalDiagnostics` 被接受 | 1 | `test_missing_diagnostics_key_records_error` |
| M6 mypy rc 门关闭（恒真） | 1 | `test_fatal_exit_code_records_error` |
| M7 mypy 异常记成 ok | 3 | 异常 outcome 断言 + 层聚合 error + warning |
| M8 聚合隐藏 error | 2 | 层聚合 error + warning |
| M9 中性对照（仅改措辞） | 0 | 必须存活 |

collected 数全程 **25**（每个变异体），sha256 还原断言通过。

## 6. 踩坑与自纠

- **早退顺序决定锁能否成立。** 若把 `static_check_status` 只写进
  "有 findings 才走"的深分支，最需要观测的空 findings 路径反而没有状态，
  核心锁会立即红。result 必须先构造（含状态）再早退。
- **rc 语义按后端分别定义。** mypy rc1 = 有错误、pyright rc1 = 有诊断，
  两者都是可信报告；统一写成 `rc==0` 会把"检查器正常报告了疑点"误判为
  不可测量。反过来 `None`（拿不到返回码）必须 fail-closed 记 error。
- **文本兜底不是 ok 通道。** 从损坏的 JSON 输出里仍可能解析出诊断行；
  findings 要保留，但这条路径不能把空结果升级成"检查完成"。
- **状态键不声明会被静默丢弃。** M14 已记录 LangGraph 对未声明键的行为；
  BG 的两个键同时补进 TypedDict 与初始状态，并由
  `TestStateObservationKeys` 锁住。
- **中性对照必须存活。** M9 只改状态语义注释的措辞，不改任何判据；它
  转红说明锁在断言实现细节而不是行为。
- **格式化会改锚点字节。** 收口前的 `ruff format` 若触及被锚定的行，
  变异脚本会报 `ANCHOR-ERROR`（不是"红"）。按新字节更新锚点并重跑，
  以"锚点转红"为准。

## 7. 边界（不得引用为「类型检查已整体可测量」）

- 本轮只改 `type_repair` 的检查器与静态层聚合；**AST 启发式层
  `_static_type_findings` 未改**——它是纯本地规则，空结果本身有语义。
- `static_check_status` 目前是**观测键，不是阻断策略**：本轮没有让
  `error` 阻断修复主流程。下游若要用它决策，必须显式读取，不能继续只看
  `mypy_findings_count`。
- `src/tools/testless_validation.py` 的 mypy 层是**另一条**校验探针
  （`TESTLESS_MYPY_ENABLE`，缺依赖时 `infra_degraded=True`），不写
  `mypy_findings_count`，本轮不改。
- 检查器仍按既有白名单过滤低置信度规则；"ok 且零疑点"只覆盖白名单内的
  规则，不外推为"类型完全正确"。
- pyright 回退 mypy 的条件仍是"pyright 没有产出任何 findings"；pyright
  报 error 但解析出疑点时保留其 findings、不重复跑 mypy（避免双份证据）。

## 8. 复算命令

```bash
.venv/bin/python -m pytest tests/test_bg_static_check_outcome.py -q
.venv/bin/python scripts/tools/bg_mutation_verify.py
.venv/bin/python -m pytest tests/test_type_repair_more_branches.py \
  tests/test_type_repair_branches.py tests/test_debugger.py -q
grep -rho '"TYPE_CHECK_ENABLE": [^,}]*' experiments/results | sort | uniq -c
```

## 9. 收口批注（2026-10-21）

- 确认跑（无 `--cov`）：**11452 passed / 5 skipped / 0 failed、
  213.25s、rc=0**（collected **11457** = 11452 + 5 + 0）。
- 覆盖率跑：**11449 passed / 3 failed / 5 skipped、202.57s**
  （collected 11457）。三处失败：基线守卫（登记前仍写 11427）、
  `debug()` 键集合契约（补两键后转绿）、prompt card（debugger 行号
  位移，`make prompt-artifacts` 重新生成后转绿；工件在 gitignored 的
  `experiments/results/prompt_artifacts_2026-10-15/`）。行
  **19111/19637 = 97.3214%**、弧 **7006/7442 = 94.1414%**；未覆盖
  526 / 缺弧 436 与 BF 逐位相同，新增 56 行 / 24 弧全部被 BG 锁执行。
- `make gates` 全链 **rc=0**（单独执行、不与其他 pytest 重叠）：`ruff
  check .` 全过；`ruff format --check .` **953 份已格式化**；mypy
  **136 源文件零问题**；链内 pytest **11452 passed / 5 skipped /
  0 failed、196.30s**（11457 items、15 warnings）；双语文档 0 警告 /
  0 失败；文档链接 175 份 / 806 条 / 0 错误 / 0 警告；env-budget
  253 开关全部登记；基线结构校验与数字漂移检查通过；状态通道 135
  文件无未声明键；env-snapshot 84 开关 / 115 键 / 缺失 0；
  model-fingerprint（无新批次）通过；工具版本一致；JSON 契约 7 个
  调用点一致；严格 JSON 7274 份工件（7272 严格 + 2 历史豁免 + 0
  违规）、304 份源码写入点 0 违规；报告→工件对账通过；零断言 451
  份测试文件 0 违规。
- 本轮改动全部未提交，未推送（工作区随收口提交一并入库）。
