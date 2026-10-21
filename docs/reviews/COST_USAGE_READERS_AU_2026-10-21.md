# AU 轮：实验侧成本/用量聚合器的值域与部分和（2026-10-21，零 LLM）

**范围**：三个仍在实验侧**直接汇总 token / 成本**的活路径——

- `experiments/spec_examples_generator.py`：`estimate_cost_usd`、
  `generate_examples_multisample` 的 `usage_totals`、`_usage_delta`；
- `experiments/oracle_examples_replay.py`：`generation_summary` 及其 README 渲染；
- `experiments/run_b8_injection.py`：`_cost_usd`、`_arm_summary`、
  `_load_harness_smoke`、`aggregate` 的 `cost_total_usd` 与 README 成本呈现。

这三处是 AI–AT 各轮**没有覆盖到的实验侧读端**：读端收口集中在
`src/budget/token_usage.py` 的共享读取器与报告侧调用点，而实验脚本仍各自
`int(... or 0)` / `float(... or 0)`。本轮把它们的金额与计数读数接回同一套
值域，并让 `None`（读不动）沿聚合链传播到工件与呈现，而不是折成 0。

**结论**：改前三个聚合器都把"未知"改写成一个数：`None` 折 0（免费）、
部分和冒充全额、bool / 小数 / 数字字符串被收下、负数与 `nan` / `inf` 进入
金额、AT 的写拒绝标记在汇总里完全消失、README 把 `None` 印成 `$None`。
处置后：金额所需的每个 token 字段过共享 `count_reason` /
`token_metric_reading`；缺席才是历史 0，读取失败给 `None` + 机制名；任一
字段不可读 ⇒ 整笔金额与 token 三元组不可读（不给部分和）；
`llm_calls` / `cache_hits` 等事件计数独立判定；写拒绝标记在场时整行不可读；
`cost_total_usd` 与含冒烟的总额任一侧未知即 `None`，机制名合并披露；
渲染器把未知呈现为「不可读 / 无法估算（机制）」，不披金额或数字形状。
**62 例新锁 + 7/7 变异锚点转红 + 0 逃逸**；真实语料只读复算 **37/37**
b8 成本与 **6/6** generation 成本逐位一致；确认跑
**11085 passed / 5 skipped / 0 failed、180.59s、rc=0**。**未提交。**

---

## 1. 缺陷定义

改前活路径（AU 前原文，均位于 `experiments/`）：

```text
# spec_examples_generator.estimate_cost_usd
input_tokens = float(usage.get("input_tokens", 0) or 0)
output_tokens = float(usage.get("output_tokens", 0) or 0)

# spec_examples_generator.generate_examples_multisample
for key in usage_totals:
    usage_totals[key] += int(usage.get(key, 0) or 0)

# spec_examples_generator._usage_delta
return {key: int(after.get(key, 0) or 0) - int(before.get(key, 0) or 0)
        for key in keys}

# oracle_examples_replay.generation_summary
usages = [g.get("usage") or {} for g in generations]
input_tokens = sum(int(u.get("input_tokens", 0) or 0) for u in usages)
output_tokens = sum(int(u.get("output_tokens", 0) or 0) for u in usages)
llm_calls = sum(int(u.get("llm_calls", 0) or 0) for u in usages)
cache_hits = sum(int(u.get("cache_hits", 0) or 0) for u in usages)

# run_b8_injection._cost_usd
return round(
    float(tm.get("total_input_tokens") or 0) / 1e6 * price_in
    + float(tm.get("total_output_tokens") or 0) / 1e6 * price_out,
    6,
)

# run_b8_injection._write_readme
smoke_tokens = sum(int((row.get("token_metrics") or {}).get("total_tokens") or 0)
                   for row in smoke)
smoke_cost = round(sum(float(row.get("cost_usd_standard_price") or 0.0)
                       for row in smoke), 6)
grand_cost = round(float(v["cost_total_usd"]) + smoke_cost, 6)
```

五类后果：

1. **未知被读成免费 / 零**：`None`（上游拒绝、写入被拒、字段未采到）经
   `or 0` 变成 0；报告读起来像"完整且为零"，而不是"没有观测"。
2. **部分和冒充全额**：`estimate_cost_usd` 里输入侧未知、输出侧可读时仍
   只用输出侧计价；`generation_summary` 一行坏值只让该行贡献 0，其余照加。
3. **坏值被改写成合法数**：`True` 记 1、`10.7` 截成 10、`"12"` 收成 12；
   负数与 `nan` / `inf` 进入金额，产出负金额或非有限金额。
4. **AT 写拒绝标记不可见**：`token_write_reasons` / `cache_write_reasons`
   从未被这三个聚合器读取；一个已声明"只收到部分和"的行仍被全额计价。
5. **呈现层把未知写成数字形状**：`$None`、`None tokens`、把冒烟成本
   `or 0.0` 后相加得到"总额"，读者无法区分"算过且为 0"与"根本算不出"。
   另有一类硬失败：不可解析字符串让 `float()` 抛 `ValueError`，整次生成中断。

## 2. 真语料测量（只读探针，改前/改后同一口径）

扫描 `experiments/results/**/*.json`（只读，不重写任何归档或原始批次）：

| 观测 | 实测 |
|---|---|
| JSON 文件 | **1701**（可解析 **1593**；108 份为历史截断/非完整 JSON，未改动） |
| `token_usage` 对象 | **10629**，坏值 **0**、在场 `null` **0** |
| `token_metrics` 对象 | **324**，坏值 **0**、在场 `null` **0** |
| `usage_totals` 汇总对象 | **60**（2 个文件），坏值 **0**、在场 `null` **0** |
| `generation` 汇总 | **6**（6 个文件），坏值 **0**、在场 `null` **0** |
| 写拒绝披露键 | **0** |
| `(token_metrics, cost_usd_standard_price)` 配对 | **37** |

只读复算（新读取器跑旧工件，不写回）：

| 复算 | 结果 |
|---|---|
| `run_b8_injection._cost_usd` 按默认标准价重算 37 组 | **37/37 与已落盘金额逐位相同** |
| `spec_examples_generator.estimate_cost_usd` 重算 6 份 generation 成本 | **6/6 相同**（1 份 `deepseek-flash` = `0.006195`；5 份 `model=unknown` 两侧同为 `None`） |

口径说明：缺陷是**边界潜伏**而非存量污染——历史工件恰好都是干净的，
所以本轮不需要、也不得回填历史数据；修复目标是让未来任何一次坏读数都
**可披露、不可读成小一号的和**。

旧表达式与新实现的现场对照（`deepseek-flash`，价目
`input $0.3/Mtok`、`output $1.2/Mtok`；旧值为逐字复刻改前表达式所得）：

| usage | 改前 | 改后 |
|---|---|---|
| `{input:1000, output:200}` | `0.00054` | `0.00054` |
| `{input:null, output:200}` | `0.00024`（只计输出侧） | `None` + `token_metric_unreadable:input_tokens` |
| `{input:null, output:1000000}` | `$1.2`（全额输出侧） | `None` |
| `{input:true, output:200}` | `0.00024`（bool 当 1） | `None` + `token_not_count:input_tokens:bool` |
| `{input:"12", output:200}` | `0.000244`（字符串当 12） | `None` + `token_not_count:input_tokens:str` |
| `{input:-5, output:200}` | `0.000238`（负输入） | `None` + `token_negative:input_tokens` |
| `{input:nan, output:200}` | `nan` | `None` + `token_not_finite:input_tokens` |
| `{input:5, output:inf}` | `inf` | `None` + `token_not_finite:output_tokens` |
| `{input:"abc", output:200}` | 抛 `ValueError` | `None` + `token_not_count:input_tokens:str` |

## 3. 处置

### 3.1 金额：`estimate_cost_usd` 共用同一个值域门

- 拆出 `usage_block_reason_for(usage)`：非对象 usage、AT 的
  `token_write_reasons` 标记、六类坏 token 值各给机制名；可读 → `None`。
- `estimate_cost_usd` 先判价目（既有 `_price_admission`），再判 usage；
  任一侧不可读 → `None`，**不计算部分和**。
- 新增 `cost_block_reason(model, usage, price_table)`：金额为 `None` 时
  调用方用它取得**唯一**归因，价目机制优先；避免"判定说 usage 坏了、
  归因却报价目"的分叉。

### 3.2 `generation_summary`：token 三元组整体可读性

- 改接 `aggregate_row_token_usage`：input / output / total 任一不可读 ⇒
  三列同 `None`；`llm_calls` 独立读数（它是事件事实，不因 token 坏值连坐）。
- 命中列用新增的 `cache_hits_reading`（见 3.3），不因 avoided 列缺席连坐。
- 金额只在 input / output 都可读时计算；否则 `cost_unpriced_reason` 取
  **具体坏值机制**（`token_field_absent:` 前缀的机制只在没有更具体原因时
  兜底），同时 `token_reading_reasons` 保留完整机制计数。
- 每任务 `llm_calls` 改走 `token_metric_reading`；非对象 usage → `None`。
- README 渲染新增 `_reading_text`：`None` 印「不可读」，不再印 `None` 或 0。

### 3.3 多样本汇总与命中列

`generate_examples_multisample` 的 `usage_totals` 改接
`aggregate_row_token_usage`；命中列改接 `cache_hits_reading`：

- 只依赖 `cache_hits` 本列——旧工件甚至只带这一列，不能让
  `cache_avoided_tokens` 缺席把可读命中数折成 `None`；
- 命中列坏值 / 在场 `null` / 非对象 usage / AT 的
  `cache_write_reasons` 标记任一在场 ⇒ `hits=None` + 机制名；
- 披露键 `usage_reasons` / `cache_reasons` 只在真发生时写入，干净返回域
  逐键不变。

### 3.4 `_usage_delta`：差值与写拒绝标记

- 差值两侧都过 `token_metric_reading`；任一侧读不动 ⇒ 该键 `None`，
  机制进入 `usage_delta_reasons`（不写 0）。
- AT 的两类写拒绝标记按**累计差值**带走（`_marker_delta`）：只带本次新增、
  0/坏计数不写键；上游汇总因此能看见"这次调用的量未知"。
- 干净路径的键集与数值逐位不变。

### 3.5 `run_b8_injection`：金额 `None` 传播与呈现

- `_cost_usd` 返回 `(金额, 机制名计数)`：逐个字段过
  `token_metric_reading`；缺席仍是历史 0；任一字段不可读 ⇒ `None`；
  非对象 `token_metrics`（非 `None`）整份不可读；`None` 仍按历史 0
  （"没有任何 metrics"哨兵）。
- `_arm_summary` / `_load_harness_smoke` 只在真拒绝时写
  `cost_usd_standard_price_reasons`。
- `aggregate` 的 `cost_total_usd`：两臂任一 `None` ⇒ `None`，并把两臂
  机制合并进 `verdict.cost_total_reasons`。
- README：表格成本用 `_cost_text`（`None` → `—（无法估算：机制×次数）`），
  冒烟/主批/含冒烟总额同口径；token 读数沿用 AP 的共享聚合；额外披露
  `token 读数不可用` 注记。`$None` 不再出现。

### 3.6 按新口径改写旧锁

`tests/test_experiments_cost_rejection_ab15.py` 的
`test_oracle_attaches_reason_only_on_rejection` 原本断言
`"if cost is None:"`；AU 把判据源改为 `cost_reason`（金额与归因同源）。
锁改为断言 `price_block_reason_for` 调用、`if cost_reason is not None:`
与 `summary["cost_unpriced_reason"] = cost_reason`，**用例数不变**，
锁的语义（只在真拒绝时披露）保持不变。

## 4. 回归锁

`tests/test_cost_usage_readers_au.py`：41 个测试函数，参数化展开 **62 例**。

| 类 | 例数 | 覆盖 |
|---|---|---|
| `TestEstimateCostUsageDomain` | 30 | 干净/零/缺席、null 两侧、bool·float·negative·nan·inf·str 各侧、非对象 usage、AT 标记、机制名、价目优先、`cost_block_reason` 同源 |
| `TestUsageDelta` | 5 | 干净差值、不可读快照、两类写拒绝标记差值、零差值不写键 |
| `TestGenerationSummary` | 8 | 干净汇总、写拒绝标记、坏 input、坏 calls 不连坐 tokens、非对象 usage、缓存标记只阻断命中列、价目优先、逐任务 calls 值域 |
| `TestMultisampleUsageTotals` | 2 | 干净汇总不变、单样本标记阻断总量 |
| `TestOracleReadingRendering` | 1 | `None` 渲染为「不可读」、0 仍渲染为 `0` |
| `TestRunB8CostReading` | 13 | 干净/缺席、7 类坏 metric、非对象、机制键条件写入、冒烟金额、`_cost_text` 不披美元形状 |
| `TestNoLooseCostFoldRegression` | 3 | 三处源码不得再出现 `or 0` 宽松折数（按函数源码扫描） |

受影响面只读复核：`tests/test_experiments_cost_rejection_ab15.py`
（改写 1 例，净 0）、`tests/test_experiments_currency_caliber_ab14.py`、
`tests/test_experiments_price_admission_ab16.py`、
`tests/test_experiments_table_admission_ab17.py`、`tests/test_emse_stats_report.py`
等既有锁均通过。

## 5. 变异验证

7 个真实锚点；逐锚点：写入变异 → `compile()` → 跑 62 例 →
sha256 原字节还原。基线 62 passed，collected 恒 62，还原后 62 passed。

| 锚点 | 变异 | 红数 |
|---|---|---|
| M1 | `estimate_cost_usd` 删除 usage 值域门（回到 `or 0` 折数） | 1 |
| M2 | `cache_hits_reading` 命中列坏值仍累加 | 1 |
| M3 | `generation_summary` token 三元组折 0 | 3 |
| M4 | `_reading_text(None)` 返回字符串 `None`（数字形状） | 1 |
| M5 | `_cost_usd` 对不可读字段折 0 | 9 |
| M6 | `_cost_text(None)` 仍返回 `$…` 形状 | 1 |
| M7 | `_arm_summary` 丢弃 `cost_usd_standard_price_reasons` | 1 |

**7/7 锚点转红，0 逃逸。** 还原后源文件与测试文件逐字节一致（sha256）。

## 6. 收口读数

- 登记前一跑（带 `--cov`）：**11084 passed / 1 failed / 5 skipped、179.18s**；
  collected **11090**；唯一失败 = BASELINE 数字守卫（仍写 11023，
  实收 − 声明 = 67 > 6 容差）。
- 覆盖率（`coverage.xml` root 口径）：**19002 / 19528 行 = 97.3064%**、
  **6960 / 7396 弧 = 94.1049%**；未覆盖 **526** 行、缺弧 **436**，与 AT
  逐位相同（本轮 `src/` 零改动，改动面在 `experiments/` + 测试 + 文档）。
- 十项核心模块：**0 项变动**（base_agent 98.53、api_manager 99.24、
  dataset_loader 97.28、graph_nodes 99.88、code_analyzer 99.38、planner
  99.09、dependency 96.26、multi_candidate 98.67、cross_file 92.98、
  rag_retriever 98.10）；核心路由三项逐位不变（graph_workflow 99.17、
  error_classifier 96.49、graph_state 100.00）。
- 确认跑（刷新 BASELINE 后）：**11085 passed / 5 skipped / 0 failed、
  180.59s、rc=0**（collected 11090）。
- 门禁（单独跑 `make gates`，不与其他命令重叠）：**`rc=0`、墙钟 181.33s**；链内 pytest（`-n 4 --dist loadfile`，不带 `--cov`，与带覆盖率读数不可互换）**11085 passed / 5 skipped / 0 failed、176.24s**（38 warnings；collected 11090）；ruff check 通过、ruff format **922 files**、mypy 135 源文件 0 错；双语文档 0 警告；文档链接 strict **163 份文件 / 692 条链接 / 0 错误**；env-budget 253/253；状态通道 134 文件；env-snapshot 84/84；JSON 契约 7/7；JSON strict 7273 工件 0 违规；报告↔工件对账 [OK]；零断言 **439 测试文件 / 0 违规**。
- 回填门禁读数后验证跑（再次单独 `make gates`，不与其他命令重叠）：**rc=0、墙钟 183.01s**；链内 pytest **11085 passed / 5 skipped / 0 failed、177.85s**（110 warnings；collected 11090）；其余门禁读数与首跑一致（ruff format 922 文件、mypy 135、文档链接 163/692/0、env-budget 253/253、状态 134、env-snapshot 84/84、JSON 契约 7/7、JSON strict 7273/0、对账 [OK]、零断言 439/0）。

## 7. 边界（不得引用为「成本/用量口径已全仓闭合」）

1. **只覆盖这三个实验侧聚合器**：仓内其他脚本若自行读取 token 字段仍可绕过；
   本轮没有做全仓普查式改写。
2. **`cache_hits_reading` 只回答命中列**：`cache_avoided_tokens` 仍不在
   多样本 / generation 汇总的返回域内；命中数可读不等于缓存金额口径完整。
3. **`_cost_usd` 对 `None` 仍返回 0**：这是"完全没有 metrics"的历史哨兵，
   与"metrics 在场但读不动"（`None` + 机制）是两种事实；不得把两者互换。
4. **`_usage_delta` 无存量工件**：缺陷由合成行触发并锁住；标记差值只带
   本次新增，不还原被拒绝的真实 token 数。
5. **真实语料零坏值不等于修复无价值**：37/37 与 6/6 的复算只证明干净路径
   不变；坏值路径由 62 例锁与 7 个变异锚点证明。
6. **金额与事件计数分离**：`llm_calls` / `cache_hits` 保留是观测事实，
   不代表这次调用的 token 可计价；报表必须看 `*_reasons`。
7. **归因优先级是价目先于 usage**：`cost_unpriced_reason` 只给一个机制名，
   usage 机制仍在 `token_reading_reasons` / `cache_reading_reasons` 里；
   不要把单键归因读成"只有价目问题"。
8. **呈现层不是机器字段**：「不可读 / 无法估算」是 README 文案；下游应读
   `None` 与原因映射，不应解析中文短语。
9. **历史工件不回填**：入库报告保留原文本；本轮只读复算，不重写任何
   `SHA256SUMS` 保护的归档或原始批次 JSON。

## 8. 登记勘误（AB-17 ②）

`docs/PROJECT_STATUS_REGISTER.md` 的 AB-17 行 ② 仍写着
"`run_b8_injection.py` 聚合仍自持一套数字门（`isinstance(..., (int, float))`
收价）"。该状态在 **AE 轮（2026-10-20）已被处置**：run_b8 的价目条目级准入
改接共享谓词，AG 轮进一步把表级缺席也委托给 `pricing.model_entry_reason`；
AU 时点源码中不存在该本地数字门。本行是**过期快照**，按登记纪律补日期化
勘误、不改写 AB-17 原文；引用 run_b8 价目准入时必须带 AE/AG 更正。

## 9. 复算命令

```bash
# 目标锁（62 collected）
.venv/bin/python -m pytest tests/test_cost_usage_readers_au.py -q

# 受影响面（只读复核）
.venv/bin/python -m pytest tests/test_experiments_cost_rejection_ab15.py \
  tests/test_experiments_currency_caliber_ab14.py \
  tests/test_experiments_price_admission_ab16.py \
  tests/test_experiments_table_admission_ab17.py -q

# 全量 + 覆盖率（CI 同口径；不与 make gates 重叠）
make test-cov

# 确认跑（BASELINE 刷新后）
make test

# 门禁（最后单独跑，绝不与其他命令重叠）
make gates
```
