# AM 轮：成本表聚合的行级 token 读取也须同一值域——呈现层不得替聚合层兜底（2026-10-21，零 LLM）

**范围**：`experiments/statistical_analysis.py` 的 `cost_analysis`（成本表 / `$/task` /
`$/solved` 的唯一聚合口）、`_row_has_token_accounting`（S11 证据判定）、
`_cost_report_lines` / `_token_reading_note_lines`（呈现）；归因判定体迁入
`src/budget/token_usage.by_model_reason`，报告侧 `emse_stats_report._attribution_reason`
改为委托同一谓词（本地函数名保留，AL 既有锁零改写）。

**结论**：ext 聚合口（AI）与报告 §4.1（AL）都已按行级值域收口，但**成本表聚合**
仍用 `tu.get(...) or 0` 把在场坏值折成可计价数字：`True` 收下当 1、`1.5` 参与计价、
`nan`/`inf` 产出非有限金额、负数抵减总量、正值行缺 input/output 按 0 计价编出
**$0**；`by_model` 键/值不做值域判定、求和不符仍照单计价；S11 又把 `True` / `100.0` /
负数读成"有记账"证据，放行断裂臂。处置后：三元组读不动 ⇒ 该臂 token 总量、归因、
`unattributed_tokens` 与金额一律 `None`/空（不给部分和）；拆分与归因矛盾 ⇒ token
总量仍可读、只废金额；两类事实分别写 `n_token_unreadable_rows` +
`token_reading_reasons` 与 `n_token_money_blocked_rows` + `token_money_reasons`。
真批次 783 行全部 int 自洽 ⇒ 三臂读数与返回域逐键不变。**64 例新锁 + 10/10 变异
锚点转红 + 1 个中性对照 0 红**。

---

## 1. 缺陷定义

改前 `cost_analysis` 的行级循环（`experiments/statistical_analysis.py`）：

```python
tu = row.get("token_usage") or {}
inp = tu.get("input_tokens") or 0  # ① 坏值/False/"" 一律折 0
out = tu.get("output_tokens") or 0
total = tu.get("total_tokens") or inp + out
input_total += inp  # ② "100" 直接让 += 崩溃
output_total += out
bm = tu.get("by_model") or {}
for model_name, tokens in bm.items():  # ③ 键/值不做值域判定
    by_model[model_name] = by_model.get(model_name, 0) + tokens
```

以及 S11 的正向证据判定：

```python
if isinstance(value, (int, float)) and value > 0:  # bool / 1.5 / inf 都收
    return True
```

| 观测（合成行 / 真批次普查） | 改前读数 | 根因 |
|---|---|---|
| `input_tokens=True` / `1.5` / `"100"` / `-5` / `nan` / `inf` | 分别按 1 / 1.5 计价、`+=` 崩溃、负数抵减、非有限金额 | ① `or 0` 只挡假值，不挡在场坏值；无值域判定 |
| `total_tokens=99, input=1, output=2` | 按 1/2 计价，拆分矛盾不披露 | 无拆分一致性检查 |
| 正 token 行缺 `input_tokens` / `output_tokens` | 缺项按 0 计价 ⇒ 金额编出 **$0**（"免费"假象） | 缺席与零不分（AE2 的历史口径只对整键缺席成立） |
| `by_model={"m": True}` / `{"m": -5}` / `{1: 10}` | 按 1 / -5 求和、`1` 被 `str()` 混入模型名 | ③ 键/值无值域判定 |
| `by_model={"m": 5}, total=99` | 按 5 计价，`Σby_model ≠ total` 不披露 | 无归因闭合检查 |
| `by_model="str"`（正 token） | 静默 `continue`，金额漏行且无机制名 | 归因只认 dict，其余无声跳过 |
| 单臂混入一行 `input_tokens="100"` | 聚合前崩溃（`TypeError`）；或整臂部分和 | ① 无"读不动整臂不给数字"的阻断层 |
| S11：`{"input_tokens": True}` / `{"total_tokens": 100.0}` / 负数 | 判为"有记账"，放行该臂成本行 | 证据值域用 `isinstance((int, float))`，非计数也是证据 |

要点：**同一行 token 记录在三个消费点有三种命运**。ext（AI）与报告 §4.1（AL）
已经"读不动 ⇒ `None` + 机制名"，成本表却仍在用 Python 真值兜底——`or 0` 把
"读不动"翻译成"读到了 0"，`isinstance(float)` 把非计数翻译成记账。成本表是
`$/task` 与 `$/solved` 的唯一来源，这里的折零会直接进入对外成本结论。

## 2. 处置

### 2.1 行级读取：共享值域 + 缺席兼容

`_row_cost_tokens` 以 `src.budget.token_usage.row_token_counts`（AL 迁入）为值域
来源，只额外保留 AE2 的缺席口径：

| 行形态 | 读数 | 说明 |
|---|---|---|
| `token_usage` 整键缺席 / `None` | `absent=True`，三元组 `(0,0,0)` | AE2 历史口径；AK 下界披露负责说明这些行 |
| 三元组全为 0，或现存字段全为 0（其余缺席） | `(0,0,0)` | 显式零行，不是读不动 |
| `total_tokens` 缺席，input/output 双全且合法 | `(inp+out, inp, out)` | 成本只需拆分；总量可由拆分导出 |
| 字段在场却是 `bool` / `float` / `str` / `nan` / `inf` / 负数 | `counts=None` + 机制名 | 在场坏值不折 0 |
| 任一现存字段为正、且三元组有缺项 | `counts=None` + 机制名 | 缺项不是 0，不得输出部分和 |
| `token_usage` 非对象 | `counts=None` + `token_usage_not_object:<T>` | 不再靠 `or {}` 静默当空 |

### 2.2 两级阻断

| 情形 | token 总量 / `by_model` / `unattributed_tokens` | 金额 | 披露键 |
|---|---|---|---|
| 任一行读不动 | 一律 `None` / 空（整臂不给部分和） | `None` | `n_token_unreadable_rows` + `token_reading_reasons` |
| `in + out != total` | 该行已计入总量（可读） | `None` | `n_token_money_blocked_rows` + `token_money_reasons`（码 `token_split_mismatch`） |
| `by_model` 非对象且键在场 | 可读 | `None` | 同上（码 `by_model_not_object:<T>`） |
| `by_model` 键非字符串 / 值非计数 / 求和≠总量 | 可读 | `None` | 同上（码 `by_model_key_not_str:<T>` / `token_not_count:...` / `token_negative:...` / `by_model_sum_mismatch`） |
| `by_model` 缺席 / 空（正 token） | 可读，计入 `unattributed_tokens` | 只丢该行金额（既有口径） | 无新增键 |

- **读不动是总量级阻断**：`None` 不是 0；呈现层显示 `—`，不得输出局部和。
- **矛盾是金额级阻断**：token 总量仍可信，金额没有可信输入；`n_tasks` 分母不变。
- 归因矛盾在 **`total == 0` 时同样阻断金额**：`by_model` 声称有 token 而行内
  三元组为 0，按 0 计价会编出"免费"。报告侧（AL）零总量仍放行，这一处分歧是
  有意的，已写进共享谓词的调用约定。
- 披露键只在真发生时写入 ⇒ 真批次与旧批次返回域逐键不变。

### 2.3 共享归因谓词

`by_model_reason(by_model, total)` 迁入 `src/budget/token_usage.py`：键必须是
字符串、值必须是 `count_reason` 认的计数、求和必须等于总量。成本表直接调用；
报告侧本地 `_attribution_reason` 改为一行委托，函数名与调用点不变。
**同一行归因在两个消费点不再有两种判定。**

### 2.4 S11 证据值域

`_row_has_token_accounting` 的三个计数字段改走 `count_reason`：`None` 不算证据，
`True` / `1.5` / `nan` / `inf` / 负数 / 字符串同样不算；`by_model` 分支还要求
键是字符串、值是计数。S11 的 **50% 阈值与 `n_without_accounting` 计数口径不变**
——本轮收紧的是"什么算证据"，不是"多少算断裂"。

### 2.5 呈现

- token 单元格为 `None` 时渲染 `—`（不折 0、不写 `None`）。
- 新增"token 读数缺口（AM）"清单：读不动与只废金额分两条点名，各带机制名与行数。
- AM 阻断臂**不并入**"只差价目"的未计价注——前者修读取，后者补价目，修补方式不同。
- 无价目时标题仅在 AM 键在场时改为"成本不可计算"；S11 单独断裂仍走既有
  "价目未登记"路径（既有锁锁定，见边界）。

### 2.6 返回域

新增键仅在真发生时出现：`n_token_unreadable_rows` / `token_reading_reasons` /
`n_token_money_blocked_rows` / `token_money_reasons`。读不动时既有键的**值**变为
`None`/空，但键集合不变；真批次 783 行全部干净，返回域与 `/tmp/am_before.json`
逐键相同。

## 3. 真批次证据

三份主批 JSON（261 行 × 3 臂 = 783 行）逐行普查：全部计数字段为 int、
`in + out == total`、`Σby_model == total` ⇒ AM 不触发任何阻断。

| 臂 | input | output | cost | cost/task | 其他 |
|---|---|---|---|---|---|
| `aitester` | 1,581,326 | 5,234,651 | 6.755979000000001 | 0.025884977011494257 | — |
| `plain_llm` | 142,783 | 694,881 | 0.8766921 | 0.0033589735632183907 | — |
| `plain_llm_df` | 152,103 | 950,127 | 1.1857833 | 0.004543231034482759 | `cost_caliber=recorded_lower_bound`；`token_zero_rows=35`、`token_zero_output_rows=35` |

`/tmp/am_measure.py` 与改前快照 `/tmp/am_before.json` 逐臂比较：三臂
`identical=True`，且无任何 AM 披露键。报告侧真实批次同样无 AM note。

## 4. 回归锁

`tests/test_cost_aggregate_token_reading_am.py`：**64 例**（collected）。

| 组 | 例数 | 覆盖 |
|---|---|---|
| `TestByModelPredicate` | 9 | 共享谓词：干净 / 非字符串键 / 值域 / 求和 / 报告与成本表同判定 |
| `TestValueDomainUnreadable` | 11 | 非对象、在场坏值、整臂置空、单坏行污染整臂 |
| `TestAbsentCompatibility` | 4 | 整键缺席 / `None` 按 0、无 AM 键；全零与部分零三元组 |
| `TestPartialTriple` | 6 | 正 token + 缺项读不动；total 缺席而 in/out 双全可计价 |
| `TestMoneyOnlyBlocking` | 11 | 拆分矛盾 / 归因矛盾 / 零总量坏归因 / 缺归因与非对象归因的区别 |
| `TestS11EvidenceDomain` | 11 | bool / float / 负数 / 字符串不算证据；合法 int 仍算；缓存值域 |
| `TestRendering` | 9 | `—` 单元格、缺口清单、只差价目排除、标题切换、干净臂文本不变 |
| `TestRealMainBatch` | 3 | 783 行全可读自洽、三臂读数不变、报告无 AM note |

按新口径改写的旧锁（均为**夹具自身违反新值域**，不是断言放松）：

- `tests/test_experiments_cost_attribution_ag.py`：`_arm` 夹具原先 `by_model`
  合计 1M 而行内总量 2M，改为逐模型 2M 且总量按行数缩放；"无归因保持无键"用例
  改用完全可读的无 `by_model` 行；"无观测早退文本"用例改用全零三元组，保留历史
  "价目未登记"/"（无 token 观测）"文本。
- `tests/test_experiments_currency_caliber_ab14.py`：分桶夹具的 in/out 原各 1M
  而 total 4M，改为各 2M 使拆分自洽。
- `tests/test_emse_stats_report.py`：`_row` 的 `tokens / 3` 产出 float，
  `_row_has_token_accounting` 起 float 不再算计数；改为整数
  `input = tokens // 3`、`output = tokens - input`，调用点字面量同步改 int。

## 5. 变异验证

基线：`experiments/statistical_analysis.py`，
sha256 `55909737ecefb5a519f924b8f0afc8d97814edb20b559ee430de85877675fc77`，
184,960 bytes；目标集 collected 恒 **188**。每个锚点：替换 → `compile()` →
写回 → 跑目标集 → **sha256 原字节还原**（不用 `git checkout` / `git stash`）→
断言还原后 sha256 相同。

| 锚点 | 回退的语义 | 转红例数 | 结果 |
|---|---|---|---|
| M0 中性注释对照 | 只改 docstring 文字 | 0 | 绿（对照有效） |
| M1 值域退回 `or 0` | dict 直接 `raw.get(...) or 0` | 19 | 红 |
| M2 部分三元组折 0 | 缺项补 0 后照常计价 | 5 | 红 |
| M3 去掉拆分一致性检查 | 删 `in + out != total` 阻断 | 5 | 红 |
| M4 跳过归因校验 | `attribution_reason = None` | 7 | 红 |
| M5 零总量坏归因放行 | 非对象 `by_model` 仅 `basis > 0` 才阻断 | 1 | 红 |
| M6 S11 证据退回宽松值域 | `isinstance(value, (int, float))` | 3 | 红 |
| M6b S11 归因证据退回宽松值域 | 同上，`by_model` 分支 | 2 | 红 |
| M7a 呈现层 `None` 折字符串 | `str(None)` 替代 `—` | 2 | 红 |
| M7b 未计价注混入阻断臂 | 删 AM 排除条件 | 1 | 红 |
| M8 标题不认 AM 缺口 | 删 `accounting_broken` 条件 | 2 | 红 |

10/10 非中性锚点全部转红；M0 证明测试对纯注释改动不敏感。还原后目标集
188 passed，sha256 与基线逐字节相同。

## 6. 收口读数

- 登记前一跑：`make test-cov` → **10684 passed / 1 failed / 5 skipped**，
  177.60s；唯一失败 = 基线守卫自身（BASELINE 仍写 10621，实收 collected 10690
  − 声明 10621 = 69 > 6 容差）。
- 刷新 `BASELINE.yaml` 后收口确认跑：**10685 passed / 5 skipped / 0 failed、
  177.94s、rc=0**。
- collected **10690**（passed 10685 / skipped 5 / failed 0）。
- 覆盖率（`--cov=src --cov-branch`）：**18585/19109 行 = 97.2579%**、
  **6727/7164 弧 = 93.9001%**；未覆盖 524、偏弧 437。
  - 分母较 AL +10 行 / +8 弧 = `by_model_reason`；覆盖 +10 行 / +8 弧（新锁
    全部执行）⇒ 未覆盖行与偏弧与 AL 逐位相同，不作回收或退化主张。
  - 十项核心模块行覆盖与三项核心路由分支覆盖按同一份 `coverage.xml` 复算
    全部不变（base_agent 98.51 / api_manager 99.24 / dataset_loader 97.28 /
    graph_nodes 99.88 / code_analyzer 99.38 / planner 99.09 / dependency 96.26 /
    multi_candidate 98.67 / cross_file 92.98 / rag_retriever 98.10；routing
    99.17 / 96.49 / 100.00）。
- 登记前一跑与确认跑覆盖率逐位相同；两次墙钟差 0.34s 不作性能主张。
- 收口期自纠四处（如实登记，不改任何读数）：① `BASELINE.yaml` 的 AM 用例
  分组数是先写的估计值（归因谓词 6 / 值域 12 / …），按 `--collect-only` 复算后
  更正为 **9 / 11 / 4 / 6 / 11 / 11 / 9 / 3**（合计 64）——沿用"登记数字必须
  复算、不得从上一轮推算"的纪律；② `BASELINE.yaml` 的两处 AM 失败注沿用了
  AL 的 `collected 10626`，与实际实收 **10690** 不符，已删去该陈旧片段（差值
  69 的计算本身正确）；③ `by_model_reason` 的 docstring 原写"调用方只在
  `total > 0` 时阻断"，与成本表零总量坏归因阻断金额的新语义不符，已改为分别
  写明报告侧与聚合侧的调用策略；④ 本分册的代码块被
  `ruff format --check .` 判 `1 file would be reformatted`，格式化后转绿；
  文件数 904 → **906**（+ 新增测试文件 + 本分册）。
- **门禁实测（单独跑 `make gates`，不与其他命令重叠）**：**rc=0**；链内
  pytest **10685 passed / 5 skipped / 0 failed**（collected 10690，174.04s）、
  ruff `All checks passed!` + **906 files already formatted**、mypy **135**
  源文件 0 错、双语文档 0 警告 0 失败、文档链接 155 文件 / 660 链接
  0 错误 / 0 需处理警告、env-budget 253/253、基线结构与数字守卫通过、
  状态通道 134 文件无未声明键读写、env-snapshot 115 键 / 缺失 0、
  工具版本一致、JSON 契约 7 处 / 9 文档、严格 JSON 7273 份
  （严格 7271 + 豁免 2 + 违规 0）/ 300 份源码 0 违规、报告→工件对账 `[OK]`、
  零断言 **431** 个测试文件 0 违规。总墙钟未单独计时（链内 pytest 174.04s
  为主项），不以未测数字冒充。

## 7. 边界（不得引用为「成本表 token 口径已全仓闭合」）

1. **整键缺席仍按 0**：`token_usage` 缺席 / `None` 是 AE2 的历史口径，AM 不改变；
   这类行不是"免费"，是否披露由 AK 的 `cost_caliber=recorded_lower_bound` 负责。
2. **S11 阈值未动**：50% 断裂线、`n_without_accounting` 计数口径、`NOT_COMPUTABLE`
   呈现均为既有语义；AM 只收紧"什么算正向证据"。
3. **无价目时的标题仍分两套**：仅当 AM 缺口键在场才用"成本不可计算"；
   S11 单独断裂且无价目时仍走"价目未登记"（既有锁锁定），不得据 AM 声称该文案
   已统一。
4. **金额级阻断只保 token 总量**：`n_tasks` / `input_tokens` / `output_tokens`
   可读时仍输出；不保证 `$/task` 可算，也不把 token 总量称作"已核实花费"。
5. **多价目 / 多币种边界不变**：AB-14 / AG 的 `mixed_currencies` /
   `mixed_price_pairs` / `unpriced_model_reasons` 口径未改；AM 只在该层之前
   增加行级读取阻断。
6. **真批次干净不证明未来批次干净**：AM 保证的是读不动时不给数字，不是源端
   不再产生坏值；生成端（实验脚本写入）不在本轮范围。
7. **报告侧零总坏归因仍放行**：AL 的 `total > 0` 条件未改；成本表对零总坏归因
   阻断金额是更严的一侧，两者有意不同。
8. **缓存口径不变**：AJ 的缓存证据判定与 AK 下界排除规则未改；S11 的缓存证据
   值域沿用 AJ，AM 只加了 bool 值域用例。
9. **`unattributed_tokens` 只在可读时给出**：读不动臂为 `None`，不是 0；
   "没有归因"与"读不动"仍是两种事实。
10. **本轮的 `src/` 改动**：`src/budget/token_usage.py`（+`by_model_reason`，
    +10 行 / +8 弧）；`experiments/` 不在覆盖率分母内，其改动由 64 例锁与变异
    验证佐证，不由覆盖率佐证。

## 8. 复算命令

```bash
# 目标集（64 例；另含 AG / AK / AL 受影响的 124 例共 188 例）
.venv/bin/python -m pytest \
  tests/test_cost_aggregate_token_reading_am.py \
  tests/test_experiments_cost_attribution_ag.py \
  tests/test_partial_accounting_ak.py \
  tests/test_report_token_reading_al.py -q

# 真批次三臂读数与改前快照逐键比较
PYTHONPATH=. .venv/bin/python /tmp/am_measure.py

# 变异验证（逐锚点回退 → compile → 跑锁 → sha256 原字节还原）
.venv/bin/python /tmp/am_mutation.py

# 全量 + 覆盖率（CI 同口径；不与 make gates 重叠）
make test-cov
```

`/tmp/am_measure.py` 与 `/tmp/am_mutation.py` 是本次运行的临时脚本（不入库）；
复算时以本文件第 3、5 节的读数与锚点描述为准。
