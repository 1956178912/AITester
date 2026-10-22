# BN 轮：状态通道运行时披露、归档工件里 0 出现——落盘边界的「读法」归位（2026-10-22，零 LLM，$0）

> 系列位置：BH→BM「读不懂 ⇒ 判优」系列的**第 6 面**。前五轮把四值 `status` 补到了生产侧（BH/BI/BJ）、
> 判定侧（BL）和实验/报告读侧（BM），本轮问的是一个更靠前的问题：**这些通道到底有没有落盘**。
> 答案是三道都不落——`src/graph/state.py::AITesterState` 声明的 10 个 `_status` / `_outcomes` 通道里，
> 7 个既不在 raw 工件白名单、也不在结果行的对应分支里，归档普查（1700 份 JSON + 9096 行 JSONL）
> 里这 7 个键**一次都没出现过**。判据范围 = 都做（两道落盘边界的全部声明通道）。
> 口径：判定值与判定方向逐字节不变，纯披露归位；历史工件一个字节不改。

---

## 1. 缺陷：两道落盘边界把「检查完成且零疑点」和「检查崩了 / 没跑」折成同一串字节

### 1.1 raw 工件白名单不含任何检查通道

`experiments/run_benchmark.py:868` 的 `_dump_state_artifacts` 按**白名单**把环节级状态写进
`<output>/raw/<task_id>/<baseline>.json`。本轮之前白名单里有 `test_plan` / `generated_test` / `diagnosis` /
`patch` / `test_passed` / `m10_leaf_fallback` 等，**没有任何一个 `_status` / `_outcomes` 键**。
于是 BH→BL 四轮辛苦建立的四值词汇（`ok` / `disabled` / `unavailable` / `error`）只活在进程内存里：

| 运行时状态 | 语义 | 改前落盘字节 |
| --- | --- | --- |
| `ok` + 空 findings | 检查完成且零疑点 | 558 字节 |
| `error` + 空 findings | 检查崩了 / 后端拒绝启动 | 558 字节（逐字节相同） |
| `unavailable` | 依赖没装 | 558 字节 |
| `disabled` | 按设计未检查 | 558 字节 |
| 键不存在 | 本轮之前的历史批次 / 从未发布 | 558 字节 |

**5 种运行时状态 → 1 种归档形状**。BL 引入 `status_for_check` 时明写的「无记录 ⇒ `None`，绝不默认 `ok`」
在判定侧生效，但归档侧根本没有该字段可供重放——事后要复算「这条 `findings=[]` 是干净还是崩了」，
只能靠 `error_category` 这类间接痕迹猜。

### 1.2 结果行的「5 态 → 5 形状」是 `contract_status` 一人撑出来的假象

`experiments/run_benchmark.py:1813` 的 `_build_task_result` 是另一道边界（成功/失败两个 `return` 分支）。
合测时它看起来**完全健康**：5 种运行时状态给出 5 种不同行形状。逐通道拆开测才发现形状差异全部由
BM 刚接上的 `contract_status` 一条腿携带：

| 通道组 | 改前 raw 工件 | 改前结果行 |
| --- | --- | --- |
| `static_check_status` + `static_check_outcomes` | 1 形状（折） | 1 形状（折） |
| `safety_check_status` + `safety_check_outcomes` | 1 形状（折） | 1 形状（折） |
| `oracle_check_status` + `oracle_check_outcomes` | 1 形状（折） | 1 形状（折） |
| `contract_status` | 1 形状（折） | 5 形状（BM 已在场） |

失败分支同理：改前 3135 字符里只有 `contract_status` 一键是状态通道。
**教训：合测的形状数只反映「在场且携带差异的键」，任何一个已登记键都能撑起形状数 ⇒ 可达性探针必须逐通道测。**

### 1.3 归档普查：7 个键 0 次出现

`scripts/tools/bn_archive_status_census.py` 扫存量归档（只读）：**1700 份 JSON**（其中 raw 工件 1121 份）
+ **9096 行 JSONL** 轨迹行，7 个通道键（`contract_status` / static / safety / oracle 各 `status`+`outcomes`）
命中 **0 次、0 个文件**。这不是「值为 null」——是键不存在，连「本轮之前没有这个概念」都无法与
「有概念但没落盘」区分。

### 1.4 为什么这是「第 6 面」而不是收尾工作

前五轮的处置都停在**判定**与**读数**层面，落盘层面只在 BL 之后零星补过 `contract_status` 一条腿。
一个披露如果没有第二道字节出口，它对事后审计等于零：本轮把「披露」从「进程内可读」推到「工件可重放」。

---

## 2. 处置：只做归位，三处新增，判定面零改动

| 站点 | 处置 | 判据是否改变 |
| --- | --- | --- |
| `_dump_state_artifacts` 白名单 | 新增 10 键（全部声明通道），`final_state.get(...)` 原值透传（`experiments/run_benchmark.py:936-945`） | 否 |
| `_build_task_result` 成功分支 | 新增 6 键（static / safety / oracle 的 `status`+`outcomes`） | 否 |
| `_build_task_result` 失败分支 | 同 6 键以 `None` 占位，保持两分支**键集合同构** | 否 |
| 新门 `scripts/gates/check_status_persistence.py` | 声明面（`AITesterState.__annotations__` 里后缀 `_status` / `_outcomes`）⊆ **每一个**落盘面；**豁免额度为空** | — |
| 接线 | Makefile 新增 `status-persistence` 目标并挂进 `gates` 依赖段；ci.yml 新增独立阻断步骤 | — |

默认档语义（本轮之后新批次）：通道未写入 ⇒ 落 `null`；写入了 ⇒ 落真实取值。历史工件不回写，
所以 0 出现仍是 0 出现——本轮只保证**新批次可复核**。

门禁的取舍与 BK 棘轮同族但更严：BK 的 `EXEMPT` 是**会收缩的存量额度**，BN 直接**空额度**——
声明了通道却不落盘，在这个仓库里没有「存量豁免」这个概念可言。`**helper(...)` 展开只在能被静态
解析时计入覆盖，解析不出来的 spread 一律不算：宁可假红，不可假绿。

---

## 3. 测量（全部实测；Python 3.14.6，零 LLM）

### 3.1 分通道可达性探针（`scripts/tools/bn_dump_boundary_probe.py`）

同一份 state、只改 status 通道取值（`ok` / `error` / `unavailable` / `disabled` / 键不存在），
比较落盘字节与行 `repr`。①只写 `tempfile.mkdtemp()`，运行结束即删；②全程内存。

| 边界 | 改前 | 改后 |
| --- | --- | --- |
| ① raw 工件 | 5 态 → **1 形状**（558 字节），工件中通道键：无 | 5 态 → **5 形状**（1117 / 1204 / 1180 / 1159 / 880 字节） |
| ② 结果行（成功分支） | 5 态 → 5 形状，但只有 `contract_status` 携带差异 | 5 态 → 5 形状（3619 / 3709 / 3691 / 3667 / 3478 字符），逐通道 5/5 |
| ③ 逐通道矩阵 | static / safety / oracle = 工件 1 / 行 1；contract = 工件 1 / 行 5 | 四组全部 **5 / 5** |
| ④ 失败分支 | 3135 字符含 `contract_status` 1 键 | 3315 字符含状态通道 **7 键** |

### 3.2 归档普查（只读，改前改后各跑一次）

1700 份 JSON（raw 1121）+ 9096 行 JSONL：7 个键 **0 命中 / 0 文件**，改后不变——
本轮改动不可能影响历史归档，这也是「零影响」的正证（不是「没跑出差异」的反证）。

### 3.3 棘轮门自测读数

```
声明 10 个通道，落盘面 3 处（raw 白名单 + 结果行 2 个分支）全覆盖
```
`--list` 口径：raw 白名单 28 键、两个行面各 104 键（`**_cross_file_audit_fields(...)` 可静态解析，已计入）。
红路径实测：① monkeypatch 一个假通道进声明面 ⇒ 门红；② 从任一分支删一键 ⇒ 门红。

### 3.4 本轮实测的覆盖率与判读数

- 预登记跑（含 `--cov`）：collected **11795** → 11789 passed / 1 failed / 5 skipped，215.89s，51 warnings，rc=2；
  唯一红 = 基线数对账守卫（`BASELINE.yaml` 当时仍写 11736，实收 − 声明 = 59 > 6 容差），刷新后消失。
- 覆盖率：`coverage.xml` root 19393/19904 行 = 97.43%、7105/7532 弧 = 94.33%，13 项逐模块读数按本轮工件复算
  与 BM 登记逐项相同。⚠️ 相同读数**不证明** `src/` 零改动——该主张的依据是 BN 改动面清单
  （`experiments/` + `scripts/` + `tests/` + Makefile + ci.yml + docs，不含 `src/`）。
- 刷新后确认跑（`make test`，**不带 `--cov`**）：collected **11795**（`4 workers [11795 items]`，与预登记同一采集面）
  → **11790 passed / 5 skipped / 0 failed、210.55s、24 warnings、rc=0**；墙钟 **212s**（`date +%s` 成对采集 1792641590→1792641802）。
  警告总数两跑 51 / 24 只登记现值、未逐条归因（`--cov` 与不带的口径差本身就会改变警告集合）。

---

## 4. 回归锁（`tests/test_bn_status_persistence.py`，54 例）

| 节 | 例数 | 断言的是什么 |
| --- | --- | --- |
| 一 `TestDeclaredSurface` | 3 | 声明面确有 10 个通道；四值词汇只覆盖四值通道；三条非四值通道只透传 |
| 二 `TestDumpWhitelist` | 21 | 10 键逐键进白名单；5 态落盘逐态可辨（含两两不同）；`_outcomes` 原样 JSON 往返；status 不移动判定字段 |
| 三 `TestResultRow` | 19 | 成功分支逐键携带通道值；失败分支同键 `None` 占位；两分支键集合同构；判分字段（`test_passed` 等）不因 status 改变 |
| 四 `TestVocabularyCaliber` | 2 | 落盘值与 `CHECK_STATUS_VOCABULARY` 一致；「无键」与「值为 null」仍是两个不同形状（第二次被折叠的那条口径） |
| 五 `TestPersistenceRatchet` | 6 | 门模块可加载；当前树绿；假通道注入 ⇒ 红；删任一分支一键 ⇒ 红；`--list` 面可读；CLI 退出码 |
| 六 `TestWiring` | 3 | Makefile 有目标；**`gates` 依赖段**（非注释）含 `status-persistence`；ci.yml 有独立步骤且 `if: matrix.python-version == '3.14'` |

既有断言只改写一处：`tests/test_run_benchmark.py::TestDumpStateArtifactsObservationKeys::test_key_set_is_stable`
的期望键集 +10。该例本来就是「字段漂移钉」——新增键必须显式登记，它红是机制在起作用，不是回归。

---

## 5. 变异验证（`scripts/tools/bn_mutation_verify.py`，24 锚点 + 1 中性对照）

基线先全绿（collected=54），再逐锚点改写、逐锚点比对采集面，`finally` 按 sha256 原字节还原。

| 组 | 锚点 | 结果 |
| --- | --- | --- |
| D | raw 白名单逐键删除 × 10 | 全红 |
| R | 成功分支逐键删除 × 6 | 全红 |
| F | 失败分支逐键删除 × 6 | 全红 |
| G1 | 门的 `CHANNEL_SUFFIXES` 丢掉 `_outcomes`（声明面退化） | 红 |
| W1 | 门从 `make gates` 依赖段摘除 | 红 |
| M-control | 只改注释措辞（语义中性） | **SURVIVED（要求 0 红）** |

复跑读数：**击杀 24 / 24，采集面逐锚点恒 collected=54，中性对照 0 红，`# mutation:` 残留 0，墙钟 129s**
（`date +%s` 成对采集 1792641307→1792641436，rc=0）。

---

## 6. 踩坑与自纠（本轮实测发生的）

1. **合测掩盖分通道折档**（见 §1.2）：探针最初的「边界形状计数」给结果行报了「5 → 5」，
   据此差点判「行边界无缺陷」。改成逐通道测才暴露三对通道全折。形状数不是通道数的代理。
2. **变异锚点互为子串**：`"static_check_status": final_state.get(...)` 在 raw（12 空格缩进）与
   行分支（12/8 空格混排）多处同字面，首轮 8 个锚点 `ANCHOR-ERROR`（命中数 > 1）。
   解法：锚点前置 `\n` 把缩进层锁死。
3. **接线锁假绿**：W1 第一轮 SURVIVED——我断言的是整条 `gates:` 行，而该行的 `##` 注释里也写着
   目标名，摘掉依赖段仍然「命中」。改成只断言 `##` 之前的依赖段。
   **这两条都是锁缺陷，不是实现缺陷**；按项目口径记录，不改动被验代码。
4. **残留扫描误报**：`# mutation` 会在仓库既有文本里命中（`mutation-det-correlation:`、`# mutation_feedback`），
   标记收紧为带冒号的 `# mutation:` 后残留 0。
5. **`ast.AnnAssign` 取属性**：声明面普查起手写了 `t.target.id`，`AnnAssign` 的 target 本身就是 `Name`，
   应为 `t.id`——AST 扫描器第一次运行即 `AttributeError`。
6. **zsh 不分词**：`pytest $FILES` 把整串当一个路径，`collected 0 items` 假绿；须 `${=FILES}`。
   （BM 手册已登记过同一条，本轮复现，说明它还没变成肌肉记忆。）
7. **macOS 无 `timeout`**：给探针加超时把命令包在 `timeout` 里，rc=127。用工具的 `run_in_background` + 轮询。

---

## 7. 边界与未收口部分（按名登记，不写成「已排除」）

1. **raw 工件只在 `save_state` 为真时写出**（`experiments/run_benchmark.py:2975` / `:3004`，默认 `False`，
   `run_main_batch.py` 从不传）⇒ 默认批次里事后唯一可复核面是**结果行**。本轮把两道边界都补齐，
   但没有改「默认不落 raw」这个开关口径。
2. **trace 的 `record_node` 为 opt-in**：状态通道是否进轨迹取决于轨迹开关，不在本轮面内。
3. **`validation_status` 在已落盘的 `testless_validation` 父键内**：可达但需下钻嵌套字典；
   门的白名单口径按顶层键判定，故该键不计入「未落盘」。
4. **三条非四值通道只透传**（`detection_first_status` / `edit_intent_status` / `deterministic_repair_status`）：
   取值域不是 `ok`/`disabled`/`unavailable`/`error`，本轮只保证它们落盘，不接入 `status_for_check` 判档。
5. **门对 `**helper(...)` 的解析是静态的**：解析不出来的 spread 不计入覆盖（宁可假红）；
   若将来把行构造改成动态拼装，门会红而不是绿——这是有意的失效方向。
6. **历史归档不回填**：1700 份 JSON / 9096 行 JSONL 的 0 出现保持原样，「本轮之前无法复核」是永久事实。
7. `experiments/` 与 `scripts/` 的 `ast.parse` 守卫面在 BK 门里仍是**只报告不阻断**。

---

## 8. 复算命令（零 LLM、零写入、可逐条重跑）

```bash
# 1) 本轮 54 例新锁（先看 collected=54，再看 rc）
.venv/bin/python -m pytest tests/test_bn_status_persistence.py -q

# 2) 两道落盘边界的邻近面（既有锁，含字段漂移钉）
.venv/bin/python -m pytest tests/test_run_benchmark.py -q

# 3) 分通道可达性探针（只写 tempfile.mkdtemp()，运行结束即删）
.venv/bin/python scripts/tools/bn_dump_boundary_probe.py

# 4) 归档普查（只读）
.venv/bin/python scripts/tools/bn_archive_status_census.py

# 5) 棘轮门自测（rc=0 为全覆盖；--list 看三面键集）
.venv/bin/python scripts/gates/check_status_persistence.py
.venv/bin/python scripts/gates/check_status_persistence.py --list

# 6) 变异验证：24 锚点 + 1 中性对照（会临时改写 experiments/ 与 Makefile，finally 按 sha256 还原）
#    中止过就必须扫残留，并复跑 §1 的 54 例：
.venv/bin/python scripts/tools/bn_mutation_verify.py
grep -rn "# mutation:" experiments/ scripts/ Makefile || echo "残留 0"

# 7) 文档锁子集（回填前后各跑一次）
.venv/bin/python -m pytest -q tests/test_markdown_table_integrity.py tests/test_ao_batch.py

# 8) 门禁链（最后、单独跑，不接管道）
make gates
```

---

## 9. 收口批注（2026-10-22）

**首跑（回填前、单独执行、不接管道）**：`rc=0`，墙钟 **200s**（`date +%s` 成对采集 `start=1792642182` → `end=1792642382`）。

链组成**实测**：**19 步命令 / 17 个 make 目标**（`gates` 的 prerequisites 数出 17，日志中被 make 回显的命令行数出 19；较 BM 轮的 18 步 / 16 目标各 +1，正是本轮补入的 `status-persistence`）。这不是 BM 值 +1 的推算，是两条独立计数相减。

链内 pytest（`-n 4 --dist loadfile`、不带 `--cov`）：`4 workers [11795 items]` → **11790 passed / 5 skipped / 0 failed in 195.15s**，**72 warnings**。与确认跑（210.55s、24 warnings）同一采集面、同一判绿方向；两跑的告警来源都只有 `test_spec_expr_property`（hypothesis）与 `test_branch_coverage_fill` 两处，聚合条目 6 / 7 条，计数差 72 − 24 只落在同一组内，未逐条归因。

链尾分步读数（首跑）：

| 步骤 | 读数 |
| --- | --- |
| `ruff format --check .` | **986 files already formatted**（BM 链内 980，+6 = 本轮新增 1 门 + 3 普查/变异脚本 + 1 测试锁 + 1 份手册） |
| `mypy src/ config.py` | **Success: no issues found in 137 source files** |
| 双语配对 / 文档链接 | 0 警告 0 失败 / 182 份文件、869 条链接、0 错误 0 警告 |
| 环境开关 / 状态契约 / env-snapshot | 253 唯一 253 已登记 / 136 文件无未声明键 / 84 开关全覆、缺失 0 |
| 严格 JSON | 工件 **7274** 份 = 严格 7272 + 登记豁免 2 + 违规 0；源码 304 份写入点违规 0 |
| 零断言 | 扫描 **458** 个测试文件，0 例（BM 457，+1 = 本轮测试锁文件） |
| `ast-guards` | 136 文件 / 78 站点 / 未覆盖 20 / 违规 0 / 豁免命中 20 / EXEMPT 19（与 BK 轮起逐位相同） |
| **`status-persistence`（本轮新门）** | 声明 **10** 个通道，落盘面 **3** 处（raw 白名单 + 结果行 2 个分支）全覆盖，rc=0 |

另一项独立佐证：以 `st_mtime > 1792638431`（BM 首跑结束时刻）对全仓 `.py`/`.md` 做普查，命中 18 个文件全部落在 `experiments/`、`scripts/`、`tests/`、`docs/`、双语登记与本手册，**`src/` 命中 0** —— 把「`src/` 零改动、故覆盖率与 BM 逐位相同」从推断升级为一次可复算的写入面普查。

**终跑（回填后、单独执行）**：`rc=0`，墙钟 **198s**（`start=1792642633` → `end=1792642831`），同为 **19 步命令 / 17 个 make 目标**；链内 `4 workers [11795 items]` → **11790 passed / 5 skipped / 0 failed in 192.68s**、**33 warnings**。两跑日志滤去 xdist 逐例进度行后 `diff` 只剩两处差异：首跑多出一条 `<unknown>:2: SyntaxWarning: invalid decimal literal`，以及 pytest 自身汇总计时行（195.15s / 72 warnings ↔ 192.68s / 33 warnings）——**门禁读数逐项相同**，说明回填文本既没把任何门禁推到红，也没让任何读数移动。四次全量跑（登记前 51 / 确认 24 / 首跑 72 / 终跑 33）的告警来源始终只有 `test_spec_expr_property`（hypothesis）与 `test_branch_coverage_fill` 两处，差值只落在同一组内，未逐条归因。

**未跑第三链**：终跑之后只回填门禁读数（本手册、`BASELINE.yaml` 的 `local_gates_target` 行、登记册 §1 全量测试行），最终树与终跑之间的差异面仅是这些文本，不含 `src/` / `tests/` / `scripts/` / `experiments/` 一行。


