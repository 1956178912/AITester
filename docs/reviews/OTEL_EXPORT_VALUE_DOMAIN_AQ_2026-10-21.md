# AQ 轮：OTel 导出器只导出可核验的数值——坏 token 不泄漏、坏时间戳不炸整份文件（2026-10-21，零 LLM）

**范围**：`src/observability/otel_export.py` 的 `_record_to_span` / `export_trace_jsonl`
（`trace.jsonl` → OTel GenAI 语义约定 span）。本轮收口导出边界上的**数值值域**：
token 三元组（`gen_ai.usage.input_tokens / output_tokens / total_tokens`）、
`ts` / `duration_ms` 的纳秒换算、`budget_remaining` / `iteration` 两个数值自定义属性，
以及非对象 `token_usage` 的静默丢失。

**结论**：导出器过去把记录里的数值**原样**写进 span 属性——bool / 字符串 / 小数 /
负数 / `nan` / `inf` / 容器都能进入 `gen_ai.usage.*`；`ts` / `duration_ms` 为非有限
float 时 `int()` 直接抛错，**整份文件的导出中止**（而同文件里的损坏 JSONL 行却是
跳过的）；非对象 `token_usage` 被静默降级成"没有 token 属性"，读不动与历史缺席
不可区分。处置后：token 计数复用生产者模块唯一的 `count_reason`；时间戳 / duration /
budget_remaining 只接受有限非负数，坏值回落到既有 0 哨兵；iteration 复用计数谓词；
坏值不导出原值，机制名按处理顺序逗号拼进 `aitester.export_value_reasons`。
**61 例新锁 + 12/12 变异锚点转红 + 0 逃逸**。真实 trace 全量 9086 文件 /
129058 span 零披露、token 属性全 int、时间戳全非负 int；18 份稳定文件改前改后
逐字不变。**未提交。**

---

## 1. 缺陷定义

改前核心读取（`src/observability/otel_export.py:72-79`，AQ 前原文）：

```python
token_usage = record.get("token_usage")
if isinstance(token_usage, dict):
    if token_usage.get("input_tokens") is not None:
        attributes["gen_ai.usage.input_tokens"] = token_usage["input_tokens"]
    if token_usage.get("output_tokens") is not None:
        attributes["gen_ai.usage.output_tokens"] = token_usage["output_tokens"]
    if token_usage.get("total_tokens") is not None:
        attributes["gen_ai.usage.total_tokens"] = token_usage["total_tokens"]
...
ts = record.get("ts")
start_ns = int(float(ts) * 1e9) if isinstance(ts, (int, float)) else 0
duration_ms = record.get("duration_ms")
duration_ns = int(float(duration_ms) * 1e6) if isinstance(duration_ms, (int, float)) else 0
```

合成记录实测（`_record_to_span`，AQ 前）：

| 观测（合成记录） | 改前读数 | 根因 |
|---|---|---|
| token 三元组 `10/20/30` | 三个 `gen_ai.usage.*` = int | 干净路径（保留） |
| token `true/false/true` | 属性 = `true/false/true` | 无 bool 门；bool 是 int 子类 |
| token `"10"/"20"/"30"` | 属性 = 字符串 | 无类型门 |
| token `10.0/20.5/30.0` | 属性 = float | 无整数门 |
| token `-1/-20/-30` | 属性 = 负 int | 无负数门 |
| token `nan/nan/nan` | 属性 = **NaN** | 无有限门；NaN 不是合法 OTLP JSON 数值 |
| token `inf/inf/inf` | 属性 = **Infinity** | 同上 |
| token `[1]/{a:1}/"x"` | 属性 = 容器原样 | 无类型门 |
| token `{"input_tokens": 10}` | 只导出 input（缺字段不出现） | 逐字段语义（**保留**） |
| token 三字段全 `None` | 三个属性都不出现、**无披露** | 在场 `None` 被 `is not None` 静默吞掉 |
| `token_usage="oops"` / `[1,2]` | 无 token 属性、**无披露** | 非对象被 `isinstance` 静默丢弃 |
| `ts=True` | `start_time_unix_nano=1000000000` | bool 当 1 秒 |
| `ts="1.5"` / `None` | `0` | 既有 0 哨兵（非数字不换算；**保留**，改后补披露） |
| `ts=nan` | `ValueError: cannot convert float NaN to integer`，**整文件导出中止** | 先 `float()` 再 `int()`，无非有限门 |
| `ts=inf` | `OverflowError: cannot convert float infinity to integer` | 同上 |
| `duration_ms=nan` / `inf` | `ValueError` / `OverflowError`，整文件中止 | 同上 |
| `ts=1e308` | `int(inf)` 崩溃 | 缩放后溢出未判 |
| `budget_remaining=nan` | 属性 = **NaN** | 数值自定义属性无值域门 |
| `iteration="3"` | 属性 = 字符串 `"3"` | 同上 |

要点：**同一个"记录里的数值"事实在导出边界有三种命运**——原样泄漏、静默丢弃、
整文件崩溃。损坏 JSONL 行已经被跳过（`except json.JSONDecodeError: continue`），
但"JSON 可解析、数值不可用"的记录没有同一套处置。

真实语料普查（只读，`/tmp/aq_probe3.py`）：9086 份 `.trace.jsonl` / 129062 行 /
5 行 JSON 错误 / 129058 个导出 span。9045 条 `token_usage` 记录（全部在 `task_end`）
只有两种键集：4662 条带 `by_model/cache_avoided_tokens/cache_hits/input_tokens/
llm_calls/output_tokens/total_tokens`，4383 条不带缓存字段；三计数与 `llm_calls`
**全部是 int、零坏值、零非对象**。`ts` 129057 条全为有限 float；`duration_ms`
44992 条有限 float、84065 条缺席；`iteration` 45288 条 int、`decision` 110926 条
str、`task` 129057 条 str；`budget_remaining` / `strategy_selected` /
`stop_reason` / `decision_reason` 真实语料 **0 条**。5 处 `NaN` 字面量均在
`output` 文本内（不进入 span 属性）。因此本轮是**潜在缺陷轮**：真实语料零实例，
但导出边界对坏值没有任何门。

## 2. 处置

### 2.1 三个私有判定器（同文件，复用共享谓词）

| 判定器 | 位置 | 输入 | 接受 | 拒绝机制名 |
|---|---|---|---|---|
| `_token_attributes` | `otel_export.py:60` | `token_usage` 任意值 | 逐字段非负 int（`count_reason`） | 字段在场 `None` / bool / float / str / 容器 ⇒ `token_not_count:<field>:<T>`；`nan`/`inf` ⇒ `token_not_finite:<field>`；负数 ⇒ `token_negative:<field>`；非对象整键 ⇒ `token_usage_not_object:<T>` |
| `_timestamp_ns` | `otel_export.py:79` | `ts` / `duration_ms` + 缩放因子 | 有限非负 int/float | bool / 非数字 ⇒ `<field>_not_number:<T>`；非有限 ⇒ `<field>_not_finite`；负数 ⇒ `<field>_negative`；缩放溢出 / 巨大整数 ⇒ `<field>_out_of_range` |
| `_numeric_attribute` | `otel_export.py:100` | `budget_remaining` 任意值 | 有限非负 int/float | bool / 非数字 ⇒ `budget_remaining_not_number:<T>`；非有限 ⇒ `budget_remaining_not_finite`；负数 ⇒ `budget_remaining_negative` |

`iteration` 直接复用 `count_reason(value, "iteration")`（循环次数是非负整数），
因此其机制名沿用共享词汇的 `token_not_count:iteration:<T>` / `token_negative:iteration`。

### 2.2 `_record_to_span` 的接线

| 记录形态 | 改后行为 | 披露 |
|---|---|---|
| `token_usage` 键缺席 / `null` | 不导出 token 属性 | 无（历史缺席；生产者从不写 `null`） |
| `token_usage` 非对象 | 不导出 token 属性 | `token_usage_not_object:<T>` |
| 三字段干净 | 三个 int 属性逐字导出 | 无 |
| 某字段坏、其余干净 | 只导出干净字段；坏字段不导出原值 | 该字段机制名（不牵连兄弟字段） |
| 字段缺席 | 不导出该字段 | 无（部分 schema 合法） |
| `ts` / `duration_ms` 干净 | 纳秒换算（保持改前 `int(float(v) * scale)`） | 无 |
| `ts` / `duration_ms` 缺席 / `null` | `0` 哨兵 | 无（既有语义） |
| `ts` / `duration_ms` 坏值 | `0` 哨兵，**不再抛异常** | `<field>_*` 机制名 |
| `budget_remaining` / `iteration` 缺席 / `null` | 不导出 | 无 |
| `budget_remaining` / `iteration` 干净 | 原值导出（int/float；iteration 仅 int） | 无 |
| `budget_remaining` / `iteration` 坏值 | 不导出 | 机制名 |
| 任一披露存在 | 追加 `aitester.export_value_reasons` | 机制名按 **ts → duration_ms → token（input/output/total）→ budget_remaining → iteration** 逗号拼接 |

字符串自定义属性（`decision` / `decision_reason` / `strategy_selected` /
`stop_reason` / `task`）本轮保持原样——AQ 缺陷族是**数值**值域，不把字符串族
混进来。干净记录的属性键序、类型与数值均与改前逐字一致。

## 3. 真工件证据

- **改前/改后快照**：18 份稳定 `trace.jsonl`（两类 token schema 各取样；记录自带
  `span_id`，避免 UUID 派生干扰）共 174 个 span，按 `(name, start, duration, attrs)`
  比较 **0 处不一致**。
- **全量真实语料**：9086 份文件 → **129058 个 span**；`aitester.export_value_reasons`
  **0 个实例**；`gen_ai.usage.*` 共 **27135** 个属性（9045 条记录 × 3）全部为 int
  且非负；`start_time_unix_nano` / `duration_unix_nano` 全部为非负 int。
- **真实 token 回读**：逐文件取 `task_end` 的原始 `token_usage`，与导出 span 的三个
  `gen_ai.usage.*` 属性逐字段比对，**≥27000 个字段一致**（测试内计数锁 27135）。
- **端到端 JSON 合法性**：含 `nan` / `inf` / 坏 token / 坏 iteration 的记录导出后，
  `json.dumps(spans, allow_nan=False)` 成功——NaN/Inf 不再泄漏到序列化层。
- **未改写任何归档或原始批次 JSON**；真实语料只读。

## 4. 回归锁

`tests/test_otel_export_value_domain_aq.py`：**61 例**（collected）。

| 组 | 例数 | 覆盖 |
|---|---|---|
| `TestTokenValueDomain` | 20 | 干净三元组、缺席/null、部分 schema、在场 `None`、bool、str、有限小数、负数、非有限参数化、容器参数化、非对象参数化、坏字段不牵连兄弟 |
| `TestTimestampValueDomain` | 17 | float/int 换算、缺席为 0、非有限 ts/duration 参数化、负数、bool、非数字参数化、缩放溢出、巨大整数、NaN 时间戳不中止整文件 |
| `TestNumericCustomAttributes` | 14 | budget int/float/0、budget 坏值参数化（bool/str/负/nan/inf）、iteration int/0、iteration 坏值参数化（bool/float/str/负）、缺席无披露 |
| `TestReasonAggregation` | 3 | 跨字段机制名顺序、干净记录无披露属性、披露属性为字符串 |
| `TestHelperUnits` | 3 | 三个判定器的直接单元形状 |
| `TestExportEndToEnd` | 4 | 坏值仍可 `allow_nan=False` 序列化、干净导出无披露、全量真实语料普查、真实 token 回读 |

同时把 `tests/test_p2_1_otel_export.py` 的头部口径补为 7 条（新增 AQ 值域条目），
并在"无 token_usage 不导出"用例追加一条"同时无披露属性"断言（不改用例数）。

## 5. 变异验证

基线目标集 **61 passed**；每个锚点：精确一次替换 → `compile()` 预校验 →
跑目标集 → **sha256 原字节还原**（不用 `git checkout` / `git stash`）。

| 锚点 | 变异 | 结果 |
|---|---|---|
| M1 | token 谓词旁路（`reason=None`） | 14 failed |
| M2 | 非对象 token 静默（返回空披露） | 4 failed |
| M3 | 非有限 ts 门移除 | 8 failed |
| M4 | 缩放后非有限门移除（崩溃路径） | 1 failed |
| M5 | 负时间戳门移除 | 2 failed |
| M6 | bool 时间戳门移除 | 1 failed |
| M7 | 巨大整数 Overflow 不兜底 | 1 failed |
| M8 | 负预算门移除 | 2 failed |
| M9 | iteration 谓词旁路 | 5 failed |
| M10 | 披露属性不写 | 42 failed |
| M11 | 纳秒换算放大 1000× | 3 failed |
| M12 | token 属性映射冲突（total → output） | 6 failed |

合计 **12/12 转红、0 存活**；还原后目标集 **61 passed**、文件 sha256 与基线逐字节相同。

## 6. 收口读数

- 登记前一跑：`make test-cov` → **10902 passed / 1 failed / 5 skipped**，
  178.81s；唯一失败 = 基线守卫自身（BASELINE 仍写 10842，实收 10908 − 声明
  10842 = 66 > 6 容差）。
- **覆盖自审**（`coverage.xml` root 口径，与 AP 同口径）：**18819/19343 行 =
  97.2910%**、**6862/7296 弧 = 94.0515%**。分母较 AP **+59 行 / +34 弧**，正好等于
  `otel_export.py` 新增的数值判定面；覆盖 **+59/+37**（+34 新弧全覆盖 + 3 个既有
  偏弧转全覆盖）。未覆盖行 **524** 与 AP 逐位相同；缺弧 **434**（AP 437）；
  `coverage report` 偏弧 **380** 与缺弧是不同口径。
- `src/observability/otel_export.py`：131 行 / 未覆盖 1（既有空行 `continue`）；
  72 分支点 / 3 偏（205、223、245）。对照跑（忽略 AQ 新测试文件）为
  112/131 行、54/72 分支点——**AQ 锁贡献 +18 行 / +15 分支点**。
- `src/budget/token_usage.py`：338 行 / 唯一未覆盖仍是既有 175；160 分支点 /
  1 偏（174）——与 AP 相同，未被本轮改动。
- 十项核心模块行覆盖与三项核心路由分支覆盖按同一份 `coverage.xml` 复算全部不变
  （base_agent 98.51 / api_manager 99.24 / dataset_loader 97.28 / graph_nodes 99.88 /
  code_analyzer 99.38 / planner 99.09 / dependency 96.26 / multi_candidate 98.67 /
  cross_file 92.98 / rag_retriever 98.10；routing 99.17 / 96.49 / 100.00）。
- 刷新 `BASELINE.yaml`（10903 / 18819·19343 / 6862·7296）后确认跑：
  **10903 passed / 5 skipped / 0 failed、178.10s、rc=0**；collected **10908**
  = passed 10903 + skipped 5（= AP 的 10847 + AQ 的 61）。
- **门禁实测（两次单独跑 `make gates`，均不与其他命令重叠）**：两次均 `rc=0`；
  墙钟 **181s / 183s**（181.38s / 183.00s）；链内 pytest（`-n 4 --dist loadfile`，
  **不带 `--cov`**，与带覆盖率读数不可互换）**10903 passed / 5 skipped /
  0 failed、176.37s / 178.16s**（26 / 24 warnings；collected 10908）；
  `ruff check` All checks passed、`ruff format --check .`
  **914 files already formatted**、mypy `Success: no issues found in 135 source files`；
  双语文档 0 警告 / 0 失败；文档链接 strict **159 份文件 / 676 条链接 / 0 错误 /
  0 警告**；env-budget 253/253 登记；`check_baseline` 结构校验与
  `check_baseline_numbers` 均通过；状态通道 134 文件通过；env-snapshot 84/84
  覆盖、缺失 0；tool-versions OK；JSON 契约 7/7；JSON strict **7273 工件 =
  7271 严格 + 2 路径豁免 + 0 违规、300 源文件 0 写入点违规**；报告↔工件对账
  [OK]（不一致 0；T-10 严格 29 行 / 25 可测，宽松 62 / 55；状态登记册覆盖率
  对账相符）；零断言 **435 测试文件 / 0 违规**（第二次复跑即回填后验证跑；
  两次 collected 相同，墙钟差 2s 不作性能主张）。

## 7. 边界（不得引用为「OTel 导出值域已全仓闭合」）

1. **0 是既有哨兵，不是有效时间**：非有限 / 负 / 溢出的 `ts` / `duration_ms` 回落
   到既有 0，同时由 `aitester.export_value_reasons` 点名。需要拒绝损坏 span 的
   消费方必须读披露属性，不能只看 `start_time_unix_nano == 0`（缺席记录也是 0）。
2. **无披露 ≠ 值已核验**：`token_usage` 缺席 / `null` 是历史缺席（无属性、无披露）；
   字段缺席也不披露。披露属性只表示"遇到并拒绝了坏值"，不是完整性证书。
3. **逐字段导出的既有口径不变**：部分三元组只导出在场且可读的字段；本轮**不**要求
   token 三元组齐全（成本口径的 `row_token_counts` 才要求三项齐全）。缺字段不得
   读成 0——它只是没有被导出。
4. **不做算术一致性判定**：`total_tokens` 与 `input+output` 不符时仍按记录分别
   导出；矛盾披露是报告层 `row_total_token_reading` 的职责，不在导出边界重复。
5. **字符串属性族不在本轮**：`decision` / `decision_reason` / `strategy_selected` /
   `stop_reason` / `task` 仍原样导出；非字符串值未设门。不得据本轮声称"所有
   OTel 属性都已值域收口"。
6. **iteration 的机制名前缀**：复用 `count_reason` 后写作
   `token_not_count:iteration:<T>`；前缀是共享计数谓词的历史词汇，不代表 iteration
   是 token 字段。
7. **潜在缺陷轮**：真实 9045 条 token 记录与全部时间戳零坏值；本轮保证的是
   "坏值不再泄漏 / 不再炸文件 / 不再静默"，不是"源端不再产生坏值"。生成端
   （会写 `trace.jsonl` 的调用方）不在本轮范围。
8. **披露属性是增量自定义属性**：干净导出逐字不变；新增属性只在有坏值时出现，
   消费方不得把"没有该属性"当作"记录已校验"。
9. **覆盖口径**：登记值取 `coverage.xml` root（6862/7296）；`coverage report`
   偏弧 380 是另一口径，不得混用。

## 8. 复算命令

```bash
# 目标集（61 collected）
.venv/bin/python -m pytest tests/test_otel_export_value_domain_aq.py -q

# 含受影响旧锁
.venv/bin/python -m pytest \
  tests/test_otel_export_value_domain_aq.py \
  tests/test_p2_1_otel_export.py \
  tests/test_small_gaps_closeout.py -q

# 变异验证（逐锚点回退 → compile → 跑锁 → sha256 原字节还原）
.venv/bin/python /tmp/aq_mutation.py

# 全量 + 覆盖率（CI 同口径；不与 make gates 重叠）
make test-cov
```

`/tmp/aq_mutation.py`、`/tmp/aq_probe2.py`、`/tmp/aq_probe3.py` 是本次运行的临时脚本
（不入库）；复算时以本文件第 1、3、5、6 节的读数与锚点描述为准。
