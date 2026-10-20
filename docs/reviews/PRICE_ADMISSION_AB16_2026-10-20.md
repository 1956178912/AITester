# AB-16：价目条目的准入域（2026-10-20）

> 零 LLM、$0。本轮处置 AB-15 §5.2 交来的**数字域与形状域**一族。AB-13 收的是"能不能计价"、
> AB-14 收的是"这笔钱是不是美元"、AB-15 收的是"拒绝的呈现与归因"；本轮收的是两者共同的上游——
> **"什么算一个价格数字、什么算一张合格条目"在仓内写了五套**（生产路径、spec、report、ext、
> analyze + statistical 的只读版），同一张条目在一处计价、在第二处被拒、在第三处崩溃，
> 而三处账面各自正常。
> 判据链：AB-9（静默缩分母）→ AB-10（缺席不得报成零命中）→ AB-11（缺席的三种形状）→
> AB-12（0 实例要连覆盖面一起锁）→ AB-13（字段名里的单位要参与判定）→
> AB-14（判定只写一遍）→ AB-15（拒绝要有拒绝的形状，归因要与判定同源）→
> **AB-16（准入域一处写一遍）**。
>
> 本轮 `src/` 有改动（新增共享谓词 `price_block_reason` / `entry_block_reason`，删除两处本地实现），
> 真批次（全 USD、有效数字）读数与受保护工件**零改变**，由锁而非措辞执行；未处置的十一项边界见 §5。

## 1. 前置读数（`/tmp/ab16_probe.py` P0–P7 前置跑 + AB-15 分册 §5.1–§5.4，只读 + 只写 tmp）

| 编号 | 测的事 | 改前实测 |
|---|---|---|
| R1 | 数字域·spec（P1） | `in=True → 3.0`、`"1.0" → 3.0`、`-1.0 → 1.0`、`[1.0]` 抛 `TypeError`、`nan`/`inf` 编进金额——`float()` 直收，`bool` 当 1 |
| R2 | 数字域·report（P2a） | 同型：`True → 3.0`、`-1.0 → 1.0`、`[1.0]` 抛 `TypeError`、`nan`/`inf` 累成非有限 `total_usd` |
| R3 | 数字域·ext（P3） | AB-15 已拦 `bool`；`"1.0"`/`[1.0]` 仍抛 `TypeError`、负价仍照乘（实测 `-1.0 → 0.03405354789272031`，AB-15 §5.2）；空条目与 `null` 价折成 0.0 部分和 |
| R4 | 形状域·四站点同一条目（P7） | 非对象条目 `5`：spec/ext/analyze 读 `currency_unreachable:int`、report 读 `entry_not_object:int`；空条目 `{}`：spec/report 读 `entry_empty`、analyze 读 `currency_absent`、ext 折成 0.0 部分和——四处四种结论 |
| R5 | 生产路径（P5） | `_as_non_negative_float` 收下 `nan`/`inf`（`inf < 0` 为假）⇒ `estimate_usd` 记账 `(nan, "price_table:m")` / `inf` 美元 |
| R6 | statistical（只读版） | `_model_is_priced` 自写 `isinstance + p >= 0`：`inf >= 0` 为真 ⇒ 非有限价被当作"已计价" |
| R7 | spec `models` 容器（P6） | 键缺席 / `null` / `[]` / `""` → `model_unregistered`；`"abc"` / `5` / `["x"]` → 在 `models.get` 上抛 `AttributeError`（`spec_examples_generator.py:335`） |
| R8 | 真表审计（P0） | deepseek-flash `usd 0.3/1.2`（批次实际唯一用到）、agnes-3.0-flash `usd` 价 `null/null`、qwen-long `other:CNY 0.5/2.0` |

R1–R7 是探针**前置跑**（改前代码）的记录。AB-13 起的各轮改动都堆叠在同一未提交工作树上，
"AB-16 改前"状态已不在 git 里，不能由现树复算——复算通道是探针**当前输出**（改后读数）
与本表、AB-15 分册 §5 的逐条记录。

R8 是"改而不动读数"的前提：真批次读到的是 deepseek-flash 的 USD 有效数字，收紧数字域后它仍是
唯一可计价条目；池化成本 `1.447277 / 0.260967 / 0.541408`、总额 `2.249652` 与 ext 三臂读数
因此逐位不变（§4.4）。

## 2. 处置口径

1. **数字域只写一遍**（`src/budget/pricing.py::price_block_reason`）：一个输入只得到一条机制，
   优先级**缺席 > 类型 > 负数 > 非有限**——任一为 `None`（含键缺席）→ `price_null`；
   `bool` 单列一档（它是 `int` 的子类）、其余非 `int|float` 按类型名排序聚合 →
   `price_not_a_number:bool/str` 这一类；任一 `< 0`（含 `-inf`——它确实小于零）→ `price_negative`；
   `nan` / `+inf`（排序后聚合，如 `price_not_finite:inf/nan`）→ 非有限档；可用 → None。
   AB-15b 在 analyze 首写的既有码逐条保持（`-inf` 仍是 `price_negative`），
   `nan` 与 `+inf` 是新收的档。
2. **条目域只写一遍**（`src/budget/pricing.py::entry_block_reason`）：优先级**形状 → 空 → 币种 → 数字**——
   非对象 → `entry_not_object:<T>`；空条目 → `entry_empty`（"什么都没有"比"没写单位"更准确）；
   币种经 `currency_block_reason(currency_status(entry))`；价格数字经 `price_block_reason`。
   判定顺序与既有站点逐条保持，站点只负责计数与格式化。
3. **六处消费点接线**：
   - 生产 `pricing._usd_prices`：`is_usd_entry` 之后接共享谓词，删除本地 `_as_non_negative_float`
     （`nan`/`inf` 从"记账非有限金额"改"不可计价"；回退链与 `estimate_usd` 语义不变）；
   - `spec_examples_generator._price_admission`：保留 spec 特有的哨兵（只有省略形参才读盘）与容器处理，
     条目级判定收口；两条改前崩溃通道收成点名——真值非对象 `models` 落 `models_not_object:<T>`
     （改前在 `models.get` 上抛 `AttributeError`）；非对象**条目**与 report 统一读
     `entry_not_object:<T>`（改前 spec/ext/analyze 读 `currency_unreachable:<T>`）；
   - `emse_stats_report.cost_effectiveness_block`：数字域接共享谓词；对可达状态逐码不变，
     坏数字从"`float()` 收下计价"改"按机制剔除"，`[1.0]` 等不再抛 `TypeError`；
   - `emse_stats_extensions._cost_per_task`：空条目与 `null` 价从"未计价"（0.0 部分和）改归**拒绝**
     （"登记了却用不了"≠"没登记"）；非对象条目统一读 `entry_not_object:<T>`；任一份额被拒 ⇒
     `usd_per_task=None`、机制名进 note（`计价被拒：<code>←<模型>`）；未登记模型仍走旧
     "部分和 + note"口径（§5.7）；
   - `analyze_t1_b2_main_batch`：删除本地 `_price_reject_reason`，`add_cost` 接 `entry_block_reason`
     （`{} → entry_empty`、非对象 → `entry_not_object:<T>`）；真零仍是真实金额、不是拒绝（AB-15 判据）；
   - `statistical_analysis._model_is_priced`：接共享谓词；唯一读数变化 = `inf` 从"已计价"改"不计价"
     （`nan`/负数/`bool`/非数改前即不计价，逐位保持）；桶级词汇 `missing_models` 不动（§5.5）。
4. **真批次与受保护工件零改变**：R8 前提 + 锁执行（§4.4）；P-1 归档工件不重生成（§5.10）。
5. **拒绝形状与归因规则继承 AB-15 不动**：`—（无法估算：<机制计数>）`、披露键只在真拒绝时写入、
   `_format_reason_counts` 扁平与嵌套两种形状、ext 渲染 `None → —（无金额）`。

## 3. 与既有断言相撞时的裁决

四处既有断言改写，全部是**接线锁**（断言"站点自己实现了哪套词汇"）——共享谓词替换后旧断言指向的
本地实现已删除；断言的**行为期望**（逐码读数）仍由 AB-15/AB-16 两代锁逐条锁定，
接线锁改为指向新事实源：

1. `test_experiments_cost_rejection_ab15.py::TestSpecGeneratorAdmission::test_registered_boundary_truthy_non_object_models_still_crashes`
   → `..._now_named`（:274）：被断言的边界被本轮**收编**——改前锁"仍崩"，现在锁"点名 + 不计价"；
   同文件 `test_registered_boundary_falsy_models_is_silent_none`（:267）不动（假值三形状的既有口径
   保持，§5.1）。
2. `TestEmseExtensionsCostPerTask::test_site_uses_the_shared_vocabulary`（:558）：断言由旧词汇改为
   `entry_block_reason` 出现在 ext 源码。
3. `TestEmseReportReasonConsolidation::test_site_imports_the_shared_vocabulary`（:603）：同上，report。
4. `test_experiments_currency_caliber_ab14.py::TestCallSitesWired::test_experiment_sites_import_the_predicate`（:630）：
   改为按文件声明期望——statistical 要 `price_block_reason` + `currency_status`，spec/report/analyze
   要 `entry_block_reason`。

一处**登记不修**：`tests/test_ae_batch.py:125` 的第二套缺省美元口径（AB-15 §5.6 延续，见 §5.8）。

一处**勘误**：AB-15 分册 §7 的"相关存量 551 passed"与 §4.3 的 421 矛盾（残留笔误）；
AB-16 轮复算实测 **421 passed / 1 warning**，已就地更正并标注。
另：AB-15 分册 §5.1/§5.2 的边界本轮已处置，已在原分册就地标注（§5.2 的"需单独一轮"即本轮）。

## 4. 验证

### 4.1 新锁

`tests/test_experiments_price_admission_ab16.py` **148 例**，十三组：

- 共享词汇导出面：`__all__` 两项俱在、`entry_block_reason` 源码确实复用
  `currency_block_reason(currency_status(...))` 而非重写币种域；
- `price_block_reason` 16 例数字矩阵 + 类型聚合排序（`bool/str`）+ 零价与真数可入；
- 优先级组：缺席 > 类型 > 负数 > 非有限（`-inf` 落 `price_negative`，`nan`/`+inf` 才落非有限）；
- `entry_block_reason` 17 例条目矩阵 + 优先级（形状先于币种与数字、空先于缺单位、币种先于数字）；
- 生产路径：`_usd_prices` 矩阵、`estimate_usd` 拒 `nan`/`inf`（改前 `nan` 会记账）、
  真表 deepseek `(0.3, 1.2)` 与 agnes/qwen 不可计价、死实现 `_as_non_negative_float` 已删；
- spec：坏数字不崩不计价、`models` 真值非对象点名 vs 假值旧边界、`price_table_not_object:list`、
  非对象条目 `entry_not_object:int`、判定与归因同源、真表 1.5 / `price_null` / `currency_not_usd:CNY`；
- report：坏数字剔除不崩、可达码逐位不变、形状点名、未登记独立、有效条目 3.0、真条目 1.5；
- ext：真三臂逐位、坏数字 `计价被拒：<code>←deepseek-flash`、空条目/`null` 价改归拒绝、
  非对象条目、未登记仍 `usd == 0.0` + `未计价模型：['deepseek-flash']`、零价 0.0、渲染 `$0.0000`；
- analyze：数字矩阵逐码保持、`{} → entry_empty`、`5 → entry_not_object:int`、有效 3.0、零价非拒绝、
  真池化逐位 + 总额、不新增披露键、真渲染、CNY 整批拒绝不出总额；
- oracle：坏/空/非对象条目带机制名、有效条目不留键、渲染无 `$nan`/`$inf`/`$None`；
- statistical：`_model_is_priced` 矩阵（`inf` 改前收下、现不计价）+ 真表读数 +
  `cost_analysis` 的 `inf` 落 missing / 有效条目落 priced；
- 一处写一遍：`def price_block_reason(` / `def entry_block_reason(` 全仓各恰 1 次、
  四个站点 import 共享谓词、死词汇 `_as_non_negative_float` / `_price_reject_reason` 不复活、
  `currency_block_reason` 不再出现在 report/ext；
- 受保护工件：P-1 归档 `估算成本 **$0.006195**` 仍在、真表数值未动。

### 4.2 变异验证

`/tmp/ab16_mutate.py`，**21 处锚点逐处转红**，红例数依次
`7 / 12 / 13 / 21 / 1 / 29 / 8 / 6 / 5 / 1 / 10 / 3 / 12 / 11 / 1 / 11 / 10 / 10 / 9 / 3 / 12`；
每处变异前后 **collected 恒为 148**（无 `ImportError` / 语法红），写盘前 `compile()`，
跑完原字节还原并核对 sha256（绝不用 `git checkout` / `git stash`）；**行为中性对照 2 处 0 红**。

### 4.3 全量与覆盖率

- 相关存量 + 两代拒绝锁共十二份文件 **678 例全绿**（§7 命令逐字可复算，本机 8.84s）。
- 登记前预跑：**10256 passed / 1 failed / 5 skipped / 173.05s**（collected 10262；
  带覆盖率口径 179.50s），唯一失败 = 基线守卫本身（`BASELINE.yaml` 尚未刷新，属预期）。
- 刷新 `BASELINE.yaml` 后确认跑：**10257 passed / 5 skipped / 0 failed / 176.35s / rc=0**。
- 覆盖率（`COVERAGE_FILE=.coverage.ci … --cov=src --cov-branch`）：
  行 **18419/18944 = 97.2287%**、分支 **6638/7076 = 93.8101%**；
  较 AB-15（18403/18928、6626/7064）**+16 行 / +12 弧**，新增部分全部在
  `src/budget/pricing.py` 且 100% 被新锁执行；未覆盖行 **525** 与偏弧 **438** 逐位不变。
  按 `docs/MEASUREMENT_INTEGRITY.md` §14：读数的变化与不变都不作缺陷与否的佐证，
  佐证是改动面文件清单。

### 4.4 受保护读数

- 真批次池化成本 `{aitester: 1.447277, plain_llm: 0.260967, plain_llm_df: 0.541408}`、
  总额 `2.249652` 与逐 seed 成本由锁逐位断言；
- 真批次载荷不新增披露键（全 USD 已登记、数字有效）；
- ext 三臂 `$/task` 与 `total_usd` 六个受保护读数逐位复现；
- statistical 真表 `cost_analysis` 的 priced / missing 读数不变；
- 归档 P-1 README 未重生成（`估算成本 **$0.006195**` 仍在、行数 > 200）。

## 5. 未处置（登记）

1. **spec 假值非对象 `models` 仍读"未登记"**：`[]` / `null` / 键缺席 / `""` 在
   `spec_examples_generator.py:340-344` 落 `model_unregistered`；真值非对象本轮已点名
   `models_not_object:<T>`（§2.3），但"容器没写"与"容器形状错"在**假值**上仍合并。
   改它会动 `_price_admission` 的返回域，需单独一轮（AB-14 §5.1 部分延续）。
   **AB-17（2026-10-20）即该单独一轮**：`models_layer` 对键在值非对象**真假一律**点名
   `models_not_object:<T>`，键缺席点名 `models_key_absent`、空对象保持静默——
   四形状各自有名（见 `TABLE_ADMISSION_AB17_2026-10-20.md` §2.1/§2.2）。
2. **`run_b8_injection.py` 聚合脚本仍自持一套数字门**：`run_b8_injection.py:675` 用
   `isinstance(..., (int, float))` 收价——`bool`（`int` 的子类）、`nan`/`inf`、负价都是该式的真值
   被收下；币种字段只被原样抄进 `price_meta`，不参与判定。该脚本产出
   `cost_usd_standard_price` 与 README 成本行；本轮只登记、未接线。
3. **ext 的 `_load(PRICE_TABLE)["models"]` 仍会 `KeyError`**：价目文件缺 `models` 键时
   `emse_stats_extensions.py:234` 直接抛 `KeyError`，不做形状点名；按既有形状域保留。
   **AB-17（2026-10-20）已处置**：`_load_price_models` 接 `table_read_reason` + `models_layer`，
   七种坏全崩的通道消失；`_load` 自持 `is_file()` 守卫造成的目录读法差异记录在案
   （见 `TABLE_ADMISSION_AB17_2026-10-20.md` §2.5）。
4. **report 与 spec 对条目值 `null` 仍读"未登记"**：`table.get(model)` 取到 `None` 时与
   "键缺席"合并（`emse_stats_report.py:571-574`、`spec_examples_generator.py:346-347`）。
   "没登记"与"登记了 null"是两种事实（AB-11 判据），当前站点没有这条入口。
   **AB-17（2026-10-20）已处置**：检索层 `.get` 的 `is None` 判定改 `not in`（spec / report /
   ext / analyze 四处）——值 `null` 落 `entry_not_object:NoneType`、键缺席落
   `model_unregistered`（见 `TABLE_ADMISSION_AB17_2026-10-20.md` §2.3）。
5. **statistical 桶级词汇 `missing_models` 未分"未登记 / 域不合格"**：`cost_analysis` 的桶只回答
   "缺哪些模型"；本轮把 `inf` 价从 priced 挪到 missing，但桶名不区分两种事实（AB-15 §5.5 延续）。
6. **`price_block_reason` 对非 `int|float` 的真数一律拒**：`Decimal("1.0")`、`numpy.float64`
   等落 `price_not_a_number:<T>`。仓内价目表是 JSON 载入（只产生 `int`/`float`），
   当前无站点吃到这类值；若将来价目从别处注入需再判。
7. **ext 未登记模型仍是 `0.0` 部分和 + note**：`_cost_per_task` 对 `prices.get(m)` 缺席的模型
   只记 `unpriced` 并继续累加其余份额；新锁显式锁定这一旧口径。"拒绝"与"未登记"是两种事实，
   本轮只保证前者不产生金额（AB-15 §5.4 延续）。
8. **测试侧第二套口径**：`tests/test_ae_batch.py:125` 的 `entry.get("currency", "USD")`
   是测试自己造的缺省美元（AB-15 §5.6 延续）。
9. **`pricing.load_price_table()` 仍静默过滤非 dict 条目**（`src/budget/pricing.py:76-77`；
   AB-13/AB-15 §5.7 延续）——"丢掉了几条"仍没有观测面。
   **AB-17（2026-10-20）已处置**：`src` 与 `statistical_analysis` 两处 `isinstance(v, dict)`
   过滤删除，坏条目原样交出、由下游 `entry_block_reason` 点名
   （见 `TABLE_ADMISSION_AB17_2026-10-20.md` §2.1/§2.3）。
10. **P-1 归档 README 不是渲染器产物**：归档 251 行、当前渲染器 64 行；本轮只锁"未重写"，
    不把它当成可再生成工件（AB-15 §5.9 延续）。
11. **`statistical_report_e2*.md` 的 86 / 88 行陈旧差值未消除**（AB-15 §5.8 延续）：
    本轮未复算、未重写。

## 6. 不得据本册引用

- 不得引用"价目准入域已在全仓统一"：§5.1–§5.6 的通道仍各自为政（假值容器、聚合脚本、
  `KeyError` 通道、null 值条目、桶词汇、非 `int|float` 真数）。
- 不得引用"未登记与拒绝已全局分开"：§5.7 的 ext 部分和仍在。
- 不得引用"价目表读取已不丢条目"：§5.9 的非 dict 条目仍静默过滤。
- 不得引用"P-1 工件可由当前渲染器再生成"：§5.10 的 64 vs 251 行。
- 不得引用"入库统计报告可逐位复现"：§5.11 的 86 / 88 行差值未消除。
- 本册的读数都可以用 §7 的命令复算；`/tmp` 探针与变异脚本不是入库工件，
  不得据此声称"仓库自带这些脚本"。

## 7. 复算命令

```bash
# 新锁（148 passed）
.venv/bin/python -m pytest tests/test_experiments_price_admission_ab16.py -q --no-cov

# 相关存量 + 两代拒绝锁（678 passed / 1 warning，8.84s）
.venv/bin/python -m pytest tests/test_experiments_price_admission_ab16.py \
  tests/test_experiments_cost_rejection_ab15.py tests/test_emse_stats_report.py \
  tests/test_experiments_price_table_ab13.py tests/test_experiments_currency_caliber_ab14.py \
  tests/test_experiments_absent_vs_zero_ab12.py tests/test_experiments_absent_vs_zero_ab11.py \
  tests/test_experiments_price_table_ab12e.py tests/test_oracle_examples.py \
  tests/test_ae_batch.py tests/test_an_batch.py tests/test_analyze_t1_b2_manual_sections.py \
  -q --no-cov

# §1/§5 边界读数（本地探针，不写仓库；现输出 = 改后读数，改前读数见 §1 表与 AB-15 分册 §5）
.venv/bin/python /tmp/ab16_probe.py

# 变异验证（21 锚点 + 2 中性对照；脚本自行还原原字节）
.venv/bin/python /tmp/ab16_mutate.py

# 全量与覆盖率（收口口径）
COVERAGE_FILE=.coverage.ci .venv/bin/python -m pytest tests/ -n 4 --dist loadfile \
  --cov=src --cov-branch --cov-report=term-missing --cov-report=xml
```

P-1 归档 README 受保护，**不得**用当前渲染器覆盖（现有锁 `TestProtectedArtifactsUnchanged` 执行）。