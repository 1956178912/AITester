# AB-15：成本拒绝的呈现与归因（2026-10-20）

> 零 LLM、$0。本轮处置 AB-14 §5 交来的**成本拒绝**一族。AB-13 收的是"能不能计价"、
> AB-14 收的是"这笔钱是不是美元"，本轮收的是两件被留在下游的事：
> **被拒绝的金额不得披着金额的形状出现**（`$None` / 折叠出来的 `$0.0` / 部分和冒充全额），
> 并且**"为什么没有金额"必须与判定同源**（同一笔拒绝不得在两份报告里点名不同，也不得不留名）。
> 判据链：AB-9（静默缩分母）→ AB-10（缺席不得报成零命中）→ AB-11（缺席的三种形状）→
> AB-12（0 实例要连覆盖面一起锁）→ AB-13（字段名里的单位要参与判定）→
> AB-14（判定只写一遍）→ **AB-15（拒绝要有拒绝的形状，归因要与判定同源）**。
>
> 本轮 `src/` 有改动（只新增共享机制名词汇与前缀无歧义的常量，不改既有判定），
> 真批次读数与受保护工件**零改变**，由锁而非措辞执行；未处置的十项边界见 §5。

## 1. 前置读数（`/tmp/ab15_probe.py`、`/tmp/ab15_probe2.py`、`/tmp/ab15_probe4.py`，只读 + 只写 tmp）

| 编号 | 测的事 | 改前实测 |
|---|---|---|
| R1 | `oracle_examples_replay.render_readme` 对 `estimated_cost_usd=None` | 未登记模型与 `qwen-long`（CNY）都落 **`**$None**`**，真零消费落 `**$0.0**`——"无法估算"与"确实没花钱"共用同一个美元前缀，且没有一行说清是哪条机制 |
| R2 | `analyze_t1_b2_main_batch` 的池化聚合 | AB-14 的门在逐 seed 层把拒绝写成 `None`，聚合却用 `cost += st["cost_usd"] or 0.0` 折回金额形状 ⇒ 整臂"没能计价"与"确实没花钱"在报告里同为 `$0.0`，token 数一字不变 |
| R3 | `emse_stats_extensions._cost_per_task`（**第六处**币种盲点） | 把真表里批次实际用到的 `deepseek-flash` 改标 `CNY`，`usd_per_task` **逐位不变**（实测 `0.025884977011494247`）——与 AB-13c/AB-14c 同型，AB-14 的站点清单漏掉了这一处 |
| R4 | 拒绝的**归因**词汇 | 收口判定之后又被抄了三遍：`emse_stats_report` 自派 if/elif 链、`statistical_analysis` 用另一套桶名、`oracle_examples_replay` 连名字都没有；`spec_examples_generator` 的"算不算得出钱"与"为什么算不出"是两段独立代码，可各自漂移 |
| R5 | 价目**数字域**（三站点，`/tmp/ab15_probe4.py` P1–P3） | spec 与 report：`True→3.0`、`"1.0"→3.0`、`-1.0→1.0`、`[1.0]` 抛 `TypeError`；ext：`True` 被本轮新闸拦下，`"1.0"` / `[1.0]` 抛 `TypeError`，`-1.0→0.03405354789272031`——三处对"什么算数"各有一套域 |
| R6 | spec 的 `models` 形状域（P4） | 键缺席 / `null` / `[]` → `model_unregistered`；`"abc"` / `5` / `["x"]` → 在 `models.get` 上抛 `AttributeError`（`spec_examples_generator.py:334-335`） |
| R7 | `pricing.load_price_table()` 的条目过滤（P5） | 非 dict 条目**静默过滤**：输入一条合法条目 + 一条坏条目，读回只有合法那条，坏条目无痕消失（`src/budget/pricing.py:76-77`） |
| R8 | ARCHIVED P-1 工件与当前渲染器（P6） | 归档 README **251 行**（含 `估算成本 **$0.006195**`），当前 `render_readme` 输出 **64 行**——该 README 是手写富文本，不是渲染器产物；本轮**不重生成**它 |

R8 与真批次读数（池化成本 `1.447277 / 0.260967 / 0.541408`、总额 `2.249652`；
ext 三臂 `0.025884977011494247 / 0.003358973563218391 / 0.004543231034482759`）是本轮
"改而不重写"的前提：所有拒绝分支只在**真拒绝**时改变输出，真表每条目都登记 `USD`。

## 2. 处置口径

1. **机制名只写一遍**（`src/budget/pricing.py`）：
   `currency_block_reason(status)` 把 `currency_status` 的读数翻译成报告可用的原因码——
   `usd → None`；`absent` / `null` / `blank → currency_absent`；
   `other:<NORM> → currency_not_usd:<NORM>`；`not_string:<T> → currency_not_usd:not_string:<T>`；
   其余（含 `entry_not_object:<T>`）→ `currency_unreachable:<T>`。
   `CURRENCY_UNDETERMINED_STATUSES` 把"没登记单位"的三种**原样**显式登记下来；
   `currency_status` 仍保持三者互不相同（AB-11 判据），合并只发生在**报告原因码**这一层。
   站点只负责计数与格式化，不再各抄一套词汇。
2. **判定与归因同源**（`spec_examples_generator`）：
   `_price_admission(model, price_table) -> (entry, reason)` 是 `estimate_cost_usd` 与
   `price_block_reason_for` 的唯一判定；调用方只有在金额为 `None` 时才取原因，两者不可能分叉。
   形状域与哨兵语义逐条保持：显式 `None` → `price_table_null`、非对象价目 →
   `price_table_not_object:<T>`、未登记 → `model_unregistered`、空条目 → `entry_empty`、
   价目数字为 `null` → `price_null`。真值非对象的 `models` 仍抛 `AttributeError`（§5.1）。
3. **拒绝不得披着金额的形状**：
   - `oracle_examples_replay`：`generation_summary` 只在 `cost is None` 时写
     `cost_unpriced_reason`（与上面同一个 `_price_admission`）；README 渲染写
     `**无法估算（<机制>）**`，不再出现 `$None`，而 `0.0` 仍是 `**$0.0**`。
   - `analyze_t1_b2_main_batch`：新增 `_price_reject_reason`（`price_null` /
     `price_not_a_number:<types>` / `price_negative`，`bool` 单列一档，因为它是 `int` 的子类）；
     `add_cost` 拒绝时写 `cost_unpriced_reason`；池化时逐 seed 保留 `None`，
     `n_seeds_unpriced` 与 `unpriced_reasons` 只在真拒绝时写入，`cost_usd` 在任一 seed 被拒时为 `None`；
     批次层 `actual_est_usd` 在任一臂被拒时为 `None`，`unpriced_arms` 只在真拒绝时写入。
     渲染统一走 `_usd_text`：`None → —（无法估算：<机制计数>）`，数字保持历史形状。
     `_format_reason_counts` 扁平化 `{code:n}` 与 `{arm:{code:n}}` 两种形状——否则报告会落
     `aitester×{'currency_not_usd:CNY': 3}` 这种被 Python 字典字面量包住的"原因"。
   - `emse_stats_extensions._cost_per_task`：接入共享谓词；被拒份额按机制点名后跳过，
     **任一份额被拒 ⇒ `usd_per_task=None`**（部分和不得冒充全额），机制名写进 `usd_note`；
     表格对 `None` 渲染 `—（无金额）`，不再对 `None` 做 `:.4f`。`bool` 价单列一档
     （改前 `true` 被当作单价 `1` 乘进金额）。**未登记模型仍走既有"部分和 + note"口径**
     （§5.4），本轮只把"拒绝"与"未登记"分开。
   - `emse_stats_report`：改用共享词汇替换本文件自派的 if/elif 链；`n_unpriceable_reasons`
     只在真剔除时写入，渲染行的机制点名只在真发生时追加。对可达状态逐码不变
     （`entry_not_object` 在形状分支已被拦下，走不到币种分支）。
4. **披露键只在真拒绝时写入**：真批次的载荷（池化成本、逐 seed 成本、统计报告成本节）
   因此逐字节不变；P-1 归档工件不重生成（§5.9）。
5. **"无法估算"与"机制未记录"分开**：`oracle_examples_replay` 与 `_usd_text` 在拿不到原因时
   写"机制未记录"，不猜一个原因，也不把缺失说成"零消费"。

## 3. 与既有断言相撞时的裁决

本轮**没有**既有断言需要改输入或放宽：

- `tests/test_emse_stats_report.py` 与 `tests/test_experiments_price_table_ab13.py` 对
  `currency_absent` / `currency_not_usd:*` 的既有期望在新共享词汇下逐码不变；共享词汇对
  可达状态给出的就是这些码（`entry_not_object` 仍由形状分支先拦）。
- `tests/test_experiments_currency_caliber_ab14.py` 对 `add_cost` 的 `cost_usd is None`
  期望不变；本轮只**新增** `cost_unpriced_reason`，不改变该字段。
- `tests/test_emse_stats_report.py::test_real_data_usd_per_task_matches_baseline` 的
  真工件读数不变（ext 与 report 两条路径互不影响）。

一处**登记不修**：`tests/test_ae_batch.py:125` 在测试侧用
`entry.get("currency", "USD")` 给自己造了第二套口径。改它要连带核对同文件全部成本例的期望值，
且它不在产品路径上；登记见 §5.6。

## 4. 验证

### 4.1 新锁

`tests/test_experiments_cost_rejection_ab15.py` **109 例**，九组：

- 词汇表：`usd` 无阻断、七族状态各有命名原因、三个"没登记单位"的写法在状态层互异而在原因层合并、
  `entry_not_object` 不与 `not_string` 合并；
- spec 准入：判定与归因同源（同输入同结论）、显式 `None` 不回头读盘、省略形参才读盘、
  边界形状；
- oracle 渲染：`$None` 不再出现、CNY 与未登记模型各带机制、`0.0` 仍是真实金额、
  机制未记录时明写"未记录"；
- 批次成本门：价目数字域、`bool` 与字符串同时点名、拒绝保留 `None`、真零不是拒绝；
- 原因计数渲染：扁平与嵌套两种形状、排序、`None` 不猜原因、正数保持前缀契约；
- 端到端：真批次池化/逐 seed 成本逐位相同、真批次不新增披露键、CNY 整批不出总额且三臂
  `{"currency_not_usd:CNY": 3}`、缺币种落 `currency_absent`、渲染无 `$None` 与无 Python 字典字面量；
- ext：三臂真实读数逐位相同、CNY/缺币种不再累加成美元、`bool` 拒绝、非对象条目点名、
  未登记模型保持旧口径、渲染不把 `None` 当浮点；
- report：共享词汇、披露键只在真剔除时写入；
- 接线与工件：源码接线、P-1 归档 README 未被重写（`估算成本 **$0.006195**` 仍在、行数 > 200）。

### 4.2 变异验证

`/tmp/ab15_mutate.py`，**27 处锚点逐处转红**，红例数依次
`5 / 19 / 6 / 2 / 5 / 2 / 6 / 12 / 3 / 3 / 3 / 6 / 2 / 6 / 3 / 4 / 3 / 1 / 3 / 1 / 4 / 2 / 4 / 5 / 1 / 3 / 3`；
每处变异前后 **collected 恒为 109**（无 `ImportError` / 语法红），
写盘前 `compile()`，跑完原字节还原并核对 sha256；**行为中性对照 0 红**。

### 4.3 全量与覆盖率

- 相关存量测试按接线面选取的十份文件 **421 例全绿**（§7 的命令逐字可复算）。
- 登记前预跑：**10108 passed / 1 failed / 5 skipped / 181.66s**（collected 10114），
  唯一失败 = 基线守卫本身（`BASELINE.yaml` 尚未刷新，属预期）。
- 刷新 `BASELINE.yaml` 后确认跑：**10109 passed / 5 skipped / 0 failed / 180.55s / rc=0**。
- 覆盖率（`COVERAGE_FILE=.coverage.ci … --cov=src --cov-branch`）：
  行 **18403/18928 = 97.2263%**、分支 **6626/7064 = 93.7995%**；
  较 AB-14（18391/18916、6618/7056）**+12 行 / +8 弧**，新增部分全部在
  `src/budget/pricing.py` 且 100% 被新锁执行；未覆盖行 **525** 与偏弧 **438** 逐位不变。
  按 `docs/MEASUREMENT_INTEGRITY.md` §14：读数的变化与不变都不作缺陷与否的佐证，
  佐证是改动面文件清单。

### 4.4 受保护读数

- 真批次池化成本 `{aitester: 1.447277, plain_llm: 0.260967, plain_llm_df: 0.541408}`、
  总额 `2.249652` 与逐 seed 成本由锁逐位断言；
- 真批次载荷不新增 `cost_unpriced_reason` / `n_seeds_unpriced` / `unpriced_reasons` /
  `unpriced_arms` 键（全 USD 已登记）；
- ext 三臂 `$/task` 与 `total_usd` 六个受保护读数逐位复现；
- 归档 P-1 README 未重生成；
- 入库 `statistical_report_e2*.md` 用改后代码在 `/tmp` 复算，与归档的差异仍是**改前即存在**的
  **86 / 88 行**（生成时间行归一后按 `<` / `>` 统计），AB-15 未改变差值。

## 5. 未处置（登记）

1. **spec 真值非对象 `models` 仍崩**：`{"models": "abc"}` / `5` / `["x"]` 在
   `spec_examples_generator.py:335` 的 `models.get(model)` 抛 `AttributeError`；
   `[]` / `null` / 键缺席则静默落 `model_unregistered`。AB-14 已登记，本轮按既有形状域保留，
   未改（改它会改变 `_price_admission` 的返回域）。
   **AB-16（2026-10-20）已处置**：真值非对象改点名 `models_not_object:<T>`、不再崩；
   假值四形状仍按"未登记"读（见 `PRICE_ADMISSION_AB16_2026-10-20.md` §2.3 与 §5.1）。
2. **三站点价目数字域不一致**：spec 与 report 只拦 `None`，`True`/`"1.0"`/`-1.0` 被
   `float()` 收下（`-1.0` 在 spec/report 会得到金额 `1.0`），list 抛 `TypeError`；
   ext 拦 `bool`，但 `"1.0"`/`[1.0]` 仍抛 `TypeError`、负价仍计价
   （实测 `-1.0 → 0.03405354789272031`）。统一数字域会改变既有读数，需单独一轮。
   **AB-16（2026-10-20）即该单独一轮**：数字域已收口到 `src.budget.pricing.price_block_reason`
   （见 `PRICE_ADMISSION_AB16_2026-10-20.md`）；本节读数保留为改前记录，真批次读数零改变。
3. **report 的 `total_usd` 仍是部分和**：混合行（USD + CNY）实测
   `total_usd=2.0, n_priced_rows=1, n_unpriceable_rows=1, {"currency_not_usd:CNY": 1}`
   ——有机制披露，但字段本身仍是"可计价行之和"，不标注"这只是部分和"。
4. **ext 未登记模型仍是 `0.0` 部分和 + note**：`_cost_per_task` 对 `prices.get(m)` 缺席的模型
   只记 `unpriced` 并继续累加其余份额；新锁显式锁定这一旧口径（`test_unregistered_model_remains_a_partial_sum_with_a_note`）。
   "拒绝"与"未登记"是两种事实，本轮只保证前者不产生金额。
   **AH（2026-10-20）已处置**：未登记 / 无归因 / 归因不闭合 / 零任务分母一律 `usd_per_task=None`
   并在 note 点名机制；上述旧锁改写为 `test_unregistered_model_is_no_amount_not_a_zero_partial_sum`，
   真批次三臂读数 0 行改变（`docs/reviews/COST_COMPLETENESS_AH_2026-10-20.md`）。
5. **`statistical_analysis.py:1333` 的 `（缺: ）`**：`missing_models` 为空时仍渲染为
   "未计价——（缺: ）"，空清单无归因；同节 `$/task` 标题也没有机制点名行。AB-14 登记，未处置。
6. **测试侧第二套口径**：`tests/test_ae_batch.py:125` 的 `entry.get("currency", "USD")`
   是测试自己造的缺省美元；产品侧已不再这样做，但该断言仍是"缺席即美元"。
7. **`pricing.load_price_table()` 静默过滤非 dict 条目**（`src/budget/pricing.py:76-77`）：
   输入一条合法 + 一条坏条目，读回只剩合法那条，坏条目无痕消失（P5）。读侧返回值口径不动是
   AB-13/AB-14 的约定，但"丢掉了几条"目前没有观测面。
8. **入库统计报告自述逐位可复现已失效**：`statistical_report_e2.md` / `_e2_iter.md` 与现码输出
   差 86 / 88 行，差值陈旧于 AB-15 之前（S11 与 BH-FDR 节晚于生成）；本轮只复算、不重写。
   **AE 轮（2026-10-20）更新**：同一口径在当前树复算为 **94 / 100 行**（canonical 110 → **122**）；
   把 `_fmt_stat_num` 回退为 AD-1 之前渲染即逐位回到 86 / 88 / 110 ⇒ 增量 100% 来自 AD-1 的
   科学计数法渲染。受 `SHA256SUMS` 保护的归档仍不重写，只更新登记数字与成因
   （见 `COST_ADMISSION_AE_2026-10-20.md` §4）。
9. **P-1 归档 README 不是渲染器产物**：归档 251 行、当前渲染器 64 行；归档含手写富文本与
   `$0.006195`。本轮只锁"未重写"，不把它当成可再生成工件。
10. **机制层合并 `absent` / `null` / `blank`**：`currency_status` 保留三者互异，
    `currency_block_reason` 在报告层统一为 `currency_absent`。这是为"为什么没有金额"给出
    一条可检索原因的设计；若将来需要区分"键没写 / 写了 null / 写了空白"，
    原始状态仍在，但当前没有站点渲染它。

## 6. 不得据本册引用

- 不得引用"所有成本拒绝都已如实呈现"：§5.1–§5.5 的站点仍会崩溃、仍会产出部分和，
  或仍留空归因。
- 不得引用"三站点数字域已统一"：§5.2 的三套域互不相同。
- 不得引用"入库统计报告可逐位复现"：§5.8 的 86 / 88 行差值未消除。
- 不得引用"P-1 工件可由当前渲染器再生成"：§5.9 的 64 vs 251 行。
- 不得引用"价目表读取已不丢条目"：§5.7 的非 dict 条目仍静默过滤。
- 本册的读数都可以用 §7 的命令复算；`/tmp` 探针不是入库工件，不得据此声称"仓库自带该脚本"。

## 7. 复算命令

```bash
# 新锁（109 passed）
.venv/bin/python -m pytest tests/test_experiments_cost_rejection_ab15.py -q --no-cov

# 相关存量（421 passed；2026-10-20 AB-16 轮勘误：本节此前残留笔误 "551 passed"，
# 与 §4.3 的 421 矛盾；十份文件命令本机复算 = 421 passed / 1 warning，已就地更正）
.venv/bin/python -m pytest tests/test_emse_stats_report.py tests/test_experiments_price_table_ab13.py \
  tests/test_experiments_currency_caliber_ab14.py tests/test_experiments_absent_vs_zero_ab12.py \
  tests/test_experiments_absent_vs_zero_ab11.py tests/test_experiments_price_table_ab12e.py \
  tests/test_oracle_examples.py tests/test_ae_batch.py tests/test_an_batch.py \
  tests/test_analyze_t1_b2_manual_sections.py -q --no-cov

# §5 边界读数（本地探针，不写仓库）
.venv/bin/python /tmp/ab15_probe4.py

# 变异验证（27 锚点 + 中性对照；脚本自行还原原字节）
.venv/bin/python /tmp/ab15_mutate.py

# 全量与覆盖率（收口口径）
COVERAGE_FILE=.coverage.ci .venv/bin/python -m pytest tests/ -n 4 --dist loadfile \
  --cov=src --cov-branch --cov-report=term-missing --cov-report=xml
```

P-6 的归档 README 对照可直接读
`experiments/results/.../P-1` 目录下的 README（见 `/tmp/ab15_probe4.py` 的路径常量）；
该文件受保护，**不得**用当前渲染器覆盖。
