# AT 轮：token 写入口的值域契约与拒绝披露（2026-10-21，零 LLM）

**范围**：token 计数的**写入口**——`record_usage` / `record_cache_hit_usage` /
`_record_response_usage` / 缓存命中路径读取文件 `tokens`——以及写拒绝在
落盘、读端、OTel 导出上的披露链路。AI–AP 轮已把**读端**值域收口；本轮补的是
"坏值根本不该以被改写的形态进入累计器"。

**结论**：改前写入口无值域约束：`record_usage(True, 5)` 把 bool 当 1 收下，
`10.7` 让总量变成小数，`-5` / `nan` / `inf` 直接毒化累计器，`"100"` 抛
`TypeError` 且整次调用丢失；`_record_response_usage` 用 `int(... or 0)` 静默
截断/吞错；缓存命中路径用 `int(... or 0)` 读文件 `tokens`，坏记账值会让一次
**有效缓存命中**退化成真实 LLM 调用。处置后：两个写入口共享 `count_reason`，
坏值**整次拒绝**（不给部分和），`llm_calls` / `cache_hits` 事件计数照常 +1，
机制名只在真发生时经 `as_dict` 落盘；读端与 OTel 导出把写拒绝标记读成不可读，
部分和不得冒充全额。**62 例新锁 + 19/19 变异锚点转红 + 0 逃逸**；确认跑
**11023 passed / 5 skipped / 0 failed**。**未提交。**

---

## 1. 缺陷定义

改前写入路径（`src/budget/token_usage.py` / `src/agents/llm_client.py` /
`src/agents/base_agent.py`，AT 前原文）：

```text
# budget/token_usage.py：直接累加，无值域判定
def record_usage(input_tokens, output_tokens, model=""):
    usage = _current_usage()
    with _usage_lock:
        usage.llm_calls += 1
        usage.input_tokens += input_tokens      # True→1；10.7→float；nan→毒化
        usage.output_tokens += output_tokens
        usage.total_tokens += input_tokens + output_tokens
        ...

def record_cache_hit_usage(avoided_tokens, model=""):
    usage = _current_usage()
    with _usage_lock:
        usage.cache_hits += 1                   # 先 +1，再在 += 上抛错 → 半截写入
        usage.cache_avoided_tokens += avoided_tokens

# agents/llm_client.py：int 归一
input_tokens = int(usage.get("input_tokens", ...) or 0)
output_tokens = int(usage.get("output_tokens", ...) or 0)

# agents/base_agent.py：缓存文件 tokens 也 int 归一
_cached_tokens = int(cached_data.get("tokens", 0) or 0)
```

三层后果：

1. **静默改写**：bool / 小数被当成计数收下，累计器总量变成小数；`"100"` 在
   写入口抛错，调用确实发生过却连 `llm_calls` 都不记；
2. **部分和冒充全额**：缓存 avoided 先 `cache_hits += 1`，再在坏值上抛错，
   留下"命中一次、avoided 未知"的半截状态；读端无法区分"未知"与"0"；
3. **为记账字段付一次调用费**：缓存文件里的 `tokens` 是**记账副产品**，坏值
   本应只影响成本口径，却因 `int()` 抛错让整次命中退化成真实 LLM 调用。

## 2. 真语料测量（只读探针，改前）

扫描 `experiments/results/**/*.json`（只读，不重写任何归档或原始批次）：

| 观测 | 实测 |
|---|---|
| JSON 文件 | **1701**（可解析 **1593**） |
| `token_usage` 对象 | **10629** |
| `token_metrics` 对象 | **324** |
| 值域坏值（bool / 小数 / 负数 / 非有限 / 字符串） | **0** |
| 写拒绝披露键 | **0** |
| `total ≠ input + output` 矛盾行 | **0** |

口径说明：缺陷是**边界潜伏**而非存量污染——历史工件恰好都是干净的，所以
本轮不需要、也不得回填历史数据；修复目标是让未来任何一次坏写入都**可披露、
不可读成小一号的和**。

## 3. 处置

### 3.1 写入口共享值域谓词

`record_usage` / `record_cache_hit_usage` 都用 `count_reason` 判定（非负整数；
bool / 小数 / 字符串 / 负数 / 非有限都拒绝）。关键语义：

- **整次拒绝**：input / output 任一坏值 ⇒ 本次两个计数都不累加，不给部分和；
- **事件计数保留**：调用 / 命中确实发生过，`llm_calls` / `cache_hits` 照常 +1；
- **机制计数**：拒绝原因写进 `token_write_reasons` / `cache_write_reasons`
  （机制名 → 次数）；
- **非字符串 model**：计数照收，但不并入 `by_model`（读端本就不认非字符串键），
  同类只告警一次。

### 3.2 披露键的条件落盘

`TokenUsage.as_dict()` 保持原 7 键 payload，只有拒绝真发生时追加
`token_write_reasons` / `cache_write_reasons`：

```text
payload = {input_tokens, output_tokens, total_tokens, llm_calls,
           cache_hits, cache_avoided_tokens, by_model}
if self.token_write_reasons:  payload["token_write_reasons"] = ...
if self.cache_write_reasons:  payload["cache_write_reasons"] = ...
```

干净批次 schema 逐字不变（真批次 783 行复算与已落值一致）；`merge()` 同步聚合
两类机制计数，跨线程聚合不丢披露。

### 3.3 响应归一与 fail-closed

`_record_response_usage` 不再 `int()` 归一：

- 缺席 / `null` 仍按历史 0（保持旧 provider 口径）；
- 其余原值交写入口判定；拒绝时预算开关开启则 fail-closed（O14 既有口径），
  关闭则披露后继续；
- `_record_response_usage` 在收到响应后**立即**记账（A11），拒绝不影响这条时序。

### 3.4 缓存路径：坏记账值不毁命中

缓存命中路径把 `tokens` 原值传给写入口（不再 int 归一）：

- 坏 `tokens` ⇒ 仍返回缓存响应，`cache_hits = 1`，avoided 不累加，
  `cache_write_reasons` 披露；
- 真实调用前后用 `write_rejection_count()` 判部分和：本次调用发生过任一写拒绝
  ⇒ 缓存文件 `tokens` 记 `null`（未知），命中侧按披露处理，不把部分和当全额；
- 文件里 `tokens` 键**缺席**仍是历史 0；**在场 `null`** 表示"上次记账未知"。

### 3.5 读端把写拒绝标记读成不可读

- `row_token_counts` / `row_token_reading`：标记在场 ⇒ 三元组不可读，机制名以
  `token_write_rejected:` 前缀返回；连"全 0 部分字段按历史零行读"的回退也禁用；
- `row_total_token_reading`：在场且合法的 `total_tokens` 也不得读取；
- `cache_caliber`：`present` 认标记，`complete=False`，命中数可读、avoided 未知；
- OTel `_token_attributes`：标记在场 ⇒ 整组 token 属性不导出，机制名披露。

## 4. 回归锁

`tests/test_token_write_domain_at.py`（**62 例**）：

| 类 | 例数 | 覆盖 |
|---|---|---|
| `TestRecordUsageWriteDomain` | 15 | 合法对累加 / 坏 input·坏 output·双坏 / 计数累计 / 非字符串 model / 空与合法 model / schema 逐字 / JSON 安全 / merge |
| `TestRecordCacheHitWriteDomain` | 11 | 合法与零值 / 6 类坏 avoided / 干净 schema / 披露 / merge |
| `TestWriteRejectionCount` | 2 | 真实 + 缓存两类写拒绝都计数；合法写入不增 |
| `TestResponseUsageNormalization` | 12 | 干净 dict / 两个 null 字段分别归零 / 坏值无异常 / 数字字符串 / 对象属性 / 预算开 fail-closed / 预算关披露后继续 |
| `TestWriteMarkerReadSide` | 11 | 干净行不变 / 行级与总量拒绝 / 标记零行不折零 / 聚合 / 缓存口径与聚合 / 标记独在 / 畸形标记披露 |
| `TestOtelExportWriteMarker` | 2 | 标记快照不导出 token 属性 / 干净快照不变 |
| `TestCachePathRawTokens` | 7 | 合法 tokens 往返 / 5 类坏 tokens 仍命中并披露 / 调用中写拒绝 → `tokens: null` |
| `TestRealCorpusHasNoWriteMarkers` | 2 | 真批次 783 行零标记 / 聚合无披露键 |

受影响面只读复核：`tests/test_base_agent_extended.py`、`tests/test_token_usage_aggregate_an.py`、
`tests/test_otel_export_value_domain_aq.py`、`tests/test_otel_export_identifier_domain_ar.py`、
`tests/test_p2_1_otel_export.py`、`tests/test_cost_*` 等既有锁（合计 537 + 185 例）
均通过，未改写断言。

## 5. 变异验证

19 个真实锚点；逐锚点：写入变异 → `compile()` → 跑 62 例 →
sha256 原字节还原。基线 62 passed，collected 恒 62，还原后 62 passed。

| 锚点 | 变异 | 红数 |
|---|---|---|
| M1 | `record_usage` 不判值域 | 22 |
| M2 | 拒绝时仍写入计数（部分和） | 15 |
| M3 | 拒绝时不再计 `llm_calls` | 16 |
| M4 | 非字符串 model 并入 `by_model` | 1 |
| M5 | 缓存拒绝时仍累加 avoided | 14 |
| M6 | `write_rejection_count` 漏掉缓存标记 | 1 |
| M7 | `as_dict` 无条件落盘披露键 | 2 |
| M8 | `merge` 不聚合写拒绝 | 1 |
| M9 | 标记计数 0 也当有效披露 | 1 |
| M10 | 非对象标记静默忽略 | 1 |
| M11 | `cache_caliber` 的 `present` 不认标记 | 1 |
| M12 | `row_token_counts` 忽略标记 | 4 |
| M13 | 零回退吞掉标记行 | 1 |
| M14 | `row_total_token_reading` 忽略标记 | 2 |
| M15 | `_call_tokens` 把部分和当全额 | 1 |
| M16 | OTel 导出忽略标记 | 1 |
| M17 | 缓存 `tokens` 重新 int 归一 | 5 |
| M18 | 响应拒绝不再 fail-closed | 1 |
| M19 | output `None` 不再归零 | 1 |

**19/19 锚点转红，0 逃逸。** 自审发现两处锁缺口并在变异前补齐：
`write_rejection_count` 的缓存分量原本无直接锁（M6 会逃逸）；`llm_client.py:382`
的 output-null 归零分支在本轮首跑覆盖率中未被任何锁执行（M19 与扩写后的
`test_none_fields_keep_historical_zero` 补齐）。还原后源文件 sha256：

```text
8cb9c98dd76c3799f710538e1cbeeefcd8f2e2615cc324cf93beda39785b8f53  src/budget/token_usage.py
3e4e8516425f7b470480bb2e3457e2970d99a6529df0f779dd2d50765c663178  src/agents/base_agent.py
59f8094aab4eb68d9596d556aa9cb6f8a52702ed0aecdc5056f6ba550149a8e2  src/agents/llm_client.py
d4f173f87b2dfb10fe883ad829ed586b706c420968654ae4c24eb0218cda7a52  src/observability/otel_export.py
769243deeee739fde7219623f70cf56f82a7d4788d4af67b9d460cec77cf13d9  src/graph/token_usage.py
```

## 6. 收口读数

- 登记前一跑（带 `--cov`）：**11022 passed / 1 failed / 5 skipped、183.38s**；
  collected **11028**；唯一失败 = BASELINE 数字守卫（仍写 10961，
  实收 − 声明 = 67 > 6 容差）。
- 行覆盖：**19002 / 19528 = 97.3064%**（两位小数 97.31）；较 AS
  18908/19434 分母 +94、覆盖 +94；未覆盖 **526** 不变。
- 分支覆盖：**6960 / 7396 = 94.1049%**（两位小数 94.10）；较 AS
  6906/7342 分母 +54、覆盖 +54；缺弧 **436** 不变。
- 十项核心模块：**1 项变动**——base_agent 98.51 → **98.53**（401/407；
  branch 97.79% 不变）；其余 9 项逐位不变。
- 逐文件：`token_usage.py` 416/417（99.76%）、`llm_client.py` 307/309（99.35%）、
  `base_agent.py` 401/407（98.53%）、`otel_export.py` 212/215（98.60%）、
  `graph/token_usage.py` 3/3（100%）。
- 确认跑（刷新 BASELINE 后）：**11023 passed / 5 skipped / 0 failed、
  182.75s、rc=0**（collected 11028）。
- 门禁（单独跑 `make gates`，不与其他命令重叠）：**`rc=0`、墙钟 183.98s**；
  链内 pytest（`-n 4 --dist loadfile`，不带 `--cov`，与带覆盖率读数不可互换）
  **11023 passed / 5 skipped / 0 failed、178.76s**（28 warnings；collected 11028）；
  ruff `920 files already formatted`；mypy 135 源文件 0 错；双语文档 0 警告 / 0 失败；
  文档链接 strict **162 份文件 / 688 条链接 / 0 错误 / 0 警告**；env-budget 253/253；
  状态通道 134 文件；env-snapshot 84/84；tool-versions OK；JSON 契约 7/7；
  JSON strict **7273 工件 = 7271 严格 + 2 路径豁免 + 0 违规**、300 源文件 0 写入点违规；
  报告↔工件对账 [OK]（T-10 严格 29 行 / 25 可测，宽松 62 / 55）；
  零断言 **438 测试文件 / 0 违规**。
- 回填后验证跑：**rc=0、墙钟 179.30s**；链内 **11023 passed / 5 skipped /
  0 failed、178.21s**（31 warnings；同一 collected 11028）。
  门禁链内 28 warnings 与验证跑 31 warnings 的差异来自 xdist 调度顺序，
  不影响任何计数。

`coverage report` 终端的偏弧读数（`BrPart`）与 `coverage.xml` root 的缺弧
（valid − covered）是不同口径；本轮只引用后者（436）。

## 7. 边界（不得引用为「token 记账已全仓闭合」）

1. **只覆盖仓内写入口**：`record_usage` / `record_cache_hit_usage` 与它们的
   三个调用点；外部脚本若直接改 `TokenUsage` 字段仍绕过判定。
2. **拒绝量不可还原**：标记只说明"有一次写入被拒绝"，不记录坏值本身；
   被拒绝的真实 token 数未知，成本只能按"不可读"处理。
3. **标记不是回填**：历史工件零标记保持原样；不得据此声称历史批次已审计。
4. **`tokens: null` 是一种新状态**：在场 `null` = 上次记账未知；缺席仍是历史 0。
   旧读者若把 `null` 当 0，会少算缓存 avoided——仓内读取器已收口，外部消费者
   需自行适配。
5. **事件计数与金额口径分离**：`llm_calls` / `cache_hits` 保留是**观测事实**，
   不代表这次调用的 token 可计价；报表必须看标记。
6. **fail-closed 受预算开关控制**：预算关闭时拒绝只披露不抛错（历史兼容），
   不能把"没抛错"理解为"记账成功"。
7. **非字符串 model 只跳过归因**：token 计数仍收下，`by_model` 缺席；
   这不是写拒绝，不会产生标记。
8. **`write_rejection_count` 是线程局部**：跨线程共享累计器时，判据只覆盖
   当前线程的写拒绝；缓存误判方向是"漏判 null"而不是"把完整和记成未知"。
9. **`orchestration_search._as_count_int` 未改**：搜索 harness 的 cell 观测字段
   不是报告金额口径，仍按既定值域读取；本轮不把标记语义扩散到该字段。

## 8. 复算命令

```bash
# 目标锁（62 collected）
.venv/bin/python -m pytest tests/test_token_write_domain_at.py -q

# 受影响面（只读复核）
.venv/bin/python -m pytest tests/test_base_agent_extended.py tests/test_token_usage_aggregate_an.py \
  tests/test_otel_export_value_domain_aq.py tests/test_otel_export_identifier_domain_ar.py \
  tests/test_p2_1_otel_export.py -q

# 全量 + 覆盖率（CI 同口径；不与 make gates 重叠）
make test-cov

# 确认跑（BASELINE 刷新后）
make test

# 门禁（最后单独跑，绝不与其他命令重叠）
make gates
```
