# AB-17：价目表表级读侧准入（2026-10-20）

> 零 LLM、$0。本轮处置 AB-16 §5.1 / §5.3 / §5.4 / §5.9 交来的**文件 → `models` 层**一族。
> AB-13 收"能不能计价"、AB-14 收"这笔钱是不是美元"、AB-15 收"拒绝的呈现与归因"、
> AB-16 收"什么算一张合格条目"；本轮收的是三者共同的上游——**"这个文件读出来算不算一张表"
> 在七个读点各写一套、读出七种记法**：同一份坏表在 `src` 只留一句连"键在值为 `null`"
> 也并写的错文案，在 `emse_stats_extensions` 是七处里唯一**连空表降级都没有的直接崩**
> （FileNotFoundError / JSONDecodeError / TypeError / KeyError / AttributeError），
> 在 `emse_stats_report` 六个中文短语只在 stderr，在 `spec_examples_generator` 文件级只进日志，
> 在 `statistical_analysis` 文件路径全程无痕而参数路径另一套短语，两个 CLI
> （`analyze_t1_b2_main_batch` / `run_b8_injection`）半数崩、余下把损坏表读成别的。
> 判据链：AB-9（静默缩分母）→ AB-10（缺席不得报成零命中）→ AB-11（缺席的三种形状）→
> AB-12（0 实例要连覆盖面一起锁）→ AB-13（字段名里的单位要参与判定）→
> AB-14（判定只写一遍）→ AB-15（拒绝要有拒绝的形状）→ AB-16（准入域一处写一遍）→
> **AB-17（表级读侧准入一处写一遍）**。
>
> 本轮 `src/` 有改动（新增四个共享助手 `table_read_reason` / `load_table_json` /
> `models_layer` / `load_table_models`，删除两处 `isinstance(v, dict)` 静默过滤），
> 真批次（真表、有效条目）读数与受保护工件**零改变**，由锁而非措辞执行；
> 未处置的九项边界见 §5。

## 1. 前置读数（`/tmp/ab17_probe.py` 前置普查矩阵：五消费方 × 14 变体，只读 + 只写 tmp）

矩阵全文（改前输出，含 stderr/log 逐行）存于 `/tmp/ab17_prechange_matrix.txt`；
下表是其中的判据行。

| 编号 | 测的事 | 改前实测 |
|---|---|---|
| R1 | `src` 缓存包装（v01–v14） | v03–v09 **七种不同坏**（顶层 list / null / 空对象 / 缺键 / list·str·null 值）全读同一句「价目表 … 结构不符（缺 models dict）」——连"键在、值为 `null`"也并写；v10–v12 静默 `{}` |
| R2 | ext（v01–v14） | v01 RAISE `FileNotFoundError`；v02 RAISE `JSONDecodeError`；v03/v04 RAISE `TypeError`；v05/v06 RAISE `KeyError:'models'`；v07–v09 RAISE `AttributeError`——文件级到形状级七种坏**全部直接崩**；v11 条目 null 折成 `usd=0.0` 部分和 |
| R3 | report（v01–v14） | v01–v09 全落 `model_unregistered`，六个互不相同的中文短语只在 stderr（文件不存在 / 语法错 / 顶层非对象（list/NoneType）/ 缺 models 键 / models 非对象（list/str/NoneType））；v11 条目 null 与键缺席同读 |
| R4 | spec（v01–v14） | v01「读不动（FileNotFoundError…）」、v02「读不动（JSONDecodeError…）」、v03「顶层是 list 而非对象」、v04「顶层是 NoneType 而非对象」只在日志；v05 静默；v06/v07 原样 pass-through + `model_unregistered`；v08 已点名 `models_not_object:str`（AB-16 收编）；v11 条目 null 与键缺席同读 |
| R5 | statistical（v01–v14） | v01/v02 stdout「警告：…加载失败」；v03–v11 **全程无痕**且读成空表（同一份表经参数路径则是另一套中文短语——形状码只落 `unpriced_currency_models`）；v12 空条目 `upc={'m': 'absent'}`（AB-14 币种路径） |
| R6 | run_b8（AB-16 §5.2 记录通道） | `is_file()` 前置守卫：显式给的坏路径**静默**退回内置价，报告里与"根本没给价目表"同形；"文件在、内容坏"则各崩在不同的 `.get` / `json.loads` 上 |
| R7 | 检索层缺席 vs null 混同（内存表直测） | report absent 与 null 同读 `{'model_unregistered': 1}`；spec absent/null/顶层缺 `models` 全 `model_unregistered`；stat 值 null 条目的桶读数与键缺席同形（形状码只进 `unpriced_currency_models`） |
| R8 | 真表控制（五读点） | src/report/statistical 读出三模型映射 `{agnes-3.0-flash, deepseek-flash, qwen-long}`；ext 对未登记 `'m'` `usd=0.0` + note 同改前——"改而不动读数"的前提 |

R1–R7 是探针**前置跑**（改前代码）的记录。AB-13 起的各轮改动都堆叠在同一未提交工作树上，
"AB-17 改前"状态已不在 git 里，不能由现树复算——复算通道是探针**当前输出**（改后读数）
与本表、AB-16 分册 §5 的逐条记录。R8 是"改而不动读数"的前提：真表读出的是
deepseek-flash 等三个有效条目，表级判定收紧后它们仍是同一份映射；池化成本
`1.447277 / 0.260967 / 0.541408`、总额 `2.249652` 与 ext 三臂 `$/task`
因此逐位不变（§4.4）。

## 2. 处置口径

1. **表级判定只写一遍**（`src/budget/pricing.py`，四个助手）：
   - `table_read_reason(exc)`：文件级读取失败 → 三种不同事实三句名——`FileNotFoundError` →
     `price_table_file_missing`；`ValueError` 族（含 `JSONDecodeError` / `UnicodeDecodeError`，
     两者都是"这份内容不是那张表"）→ `price_table_json_invalid:<T>`；其余（`IsADirectoryError` /
     `PermissionError` 等）→ `price_table_file_unreadable:<T>`；
   - `load_table_json(path)`：`(解析结果, None)` 或 `(None, 机制名)`；`(None, None)` 是**合法读数**
     （文件内容就是 `null`）——"两种 `None`"由 reason 承担，调用方不得用 `data is None` 判读取失败
     （AB-12e 同型判据）；
   - `models_layer(data)`：顶层非对象 → `price_table_not_object:<T>`；顶层对象缺 `models` 键：
     **空对象没有形状可说** ⇒ 静默"真的没登记"（沿用 statistical AB-14 已注册口径），
     非空对象 → `models_key_absent`（"键缺席"与"值为 `null`"是两种事实——AB-11 判据）；
     `models` 键在、值为非对象（**真假一律**）→ `models_not_object:<T>`；可用 → **原样交出**：
     非对象条目**不再被静默丢弃**（改前 `src` 与 `statistical_analysis` 各有一处
     `isinstance(v, dict)` 过滤，坏条目无声消失，读起来与"没登记"同形）；
   - `load_table_models(path)`：读文件 → `models` 层一步到位；缓存包装
     `pricing.load_price_table()` 同源接过去。
2. **七处接线**：
   - `src/budget/pricing.py` 缓存包装：`isinstance(v, dict)` 静默过滤删除；文件缺失 / 解析失败 /
     结构不符 → `{}` + 一条带机制码的 warning，与其余六个读点同源；
   - `spec_examples_generator.load_price_table`：文件级判定收口 `load_table_json`（机制码进日志）；
     `models` 层 **pass-through**——"谁做的判定谁点名"，消费点 `_price_admission` 经 `models_layer`
     读出同一个码；假值非对象容器（`[]` / `null`）从并入"未登记"改 `models_not_object:<T>`；
   - `emse_stats_report._load_price_table`：三类 except 与六个中文短语 → 共享码 + 空表 +
     stderr 点名；
   - `emse_stats_extensions`：`_load` 自持 `is_file()` 前置守卫（既有读取器语义，设计性保留，
     见 §2.5）→ 目录读成 `price_table_file_missing`；`_load_price_models()` 接
     `table_read_reason` + `models_layer`——改前七种坏全崩的通道消失；
   - `statistical_analysis`：文件路径与参数路径两条通道共用 `pricing.load_table_json` /
     `pricing.models_layer`；三套中文短语换共享码；`isinstance(v, dict)` 静默过滤移除；
   - `analyze_t1_b2_main_batch._load_price_entry`：`load_table_json` + `models_layer`；
     表级失败 → `(None, 机制名)`，由 `add_cost` 的条目谓词接管**只有表级成功**的情形；
   - `run_b8_injection`：`is_file()` 前置守卫删除 → `load_table_models` 点名，
     `price_meta["table_reason"]` **只在真不可用时写入**（内置价照旧兜底）；
     AB-16 §5.2 登记的②自持数字门**保留**（`isinstance(..., (int, float))`），只加
     `isinstance(row, dict)`——models 层不再过滤后，非对象条目改前会崩在 `row.get` 上。
3. **检索层混同修正**：`.get(model)` 的 `is None` 判定改 `not in`——落在 spec / report / ext /
   analyze 四处：值 `null` → `entry_not_object:NoneType`（经 `entry_block_reason`），
   键真缺席 → `model_unregistered`（AB-11 判据：键缺席 ≠ 值为 null）。
4. **空对象静默 doctrine**：`{}` 与 `{"models": {}}` 在任何读点零留痕、读出"真的没登记"——
   "真的空"与"传错形状"仍分得开。
5. **两处记录在案的读法差异（设计如此，不是同源破坏，新锁显式锁定）**：
   ① spec 的加载器对 `models` 层 pass-through——文件级失败在加载器点名，`models` 层形状
   在消费点点名（"谁做的判定谁点名"）；
   ② ext 的 `_load` 自持 `is_file()` 前置守卫——目录在 ext 读 `price_table_file_missing`，
   其余六个读点经 `load_table_json` 读 `price_table_file_unreadable:IsADirectoryError`；
   两处机制词汇同源，读取器差异如实记录。
6. **真批次与受保护工件零改变**：R8 前提 + 锁执行（§4.4）。

## 3. 与既有断言相撞时的裁决

五个既有锁文件按新口径改写，全部是**词汇接线锁**（断言站点自己实现了哪套中文短语/码），
断言的**行为期望**仍由各代锁逐条锁定；净 0 例：

1. `test_experiments_price_table_ab12e.py`（:103 / :117）：机制断言由中文短语换共享码
   （`price_table_file_missing` / `price_table_json_invalid:JSONDecodeError`）。
2. `test_experiments_price_table_ab13.py`（文件头注 + corpus 六案）：四套中文短语换
   `price_table_file_missing` / `price_table_json_invalid:<T>` / `price_table_not_object:<T>` /
   `models_key_absent` / `models_not_object:<T>`；返回域与静默边界断言不动。
3. `test_experiments_currency_caliber_ab14.py`（:426–:452）：统计侧形状披露断言换共享码
   （`models_key_absent` / `price_table_not_object:list` / `models_not_object:int`）；
   空对象静默与返回域断言不动。
4. `test_experiments_cost_rejection_ab15.py:269`：spec 假值非对象容器由"仍静默、并入未登记"
   改为点名 `models_not_object:<T>`——该断言指向的旧边界被本轮**收编**（AB-16 §5.1 登记）。
5. `test_experiments_price_admission_ab16.py:389`：参数化 `[]` / `None` 的期望由
   `model_unregistered` 改 `models_not_object:list` / `models_not_object:NoneType`；
   `{}` 仍是 `model_unregistered`（空对象静默，逐条保持）。

AB-16 §5.1 / §5.3 / §5.4 / §5.9 登记的四条边界本轮已处置，已在原分册就地标注。

## 4. 验证

### 4.1 新锁

`tests/test_experiments_table_admission_ab17.py` **26 例**，六组：

- 一处写一遍：四个助手全仓各恰 1 次（`def` 计数）、七个读点按文件声明期望 import 共享助手、
  草名 `_price_shape_reason` 不复活、站点不重复定义；
- 九案坏表矩阵（missing / syntax / binary / dir / top_list / top_null / no_models /
  models_list / models_null）：同一份坏表在 pricing / spec / report / statistical / ext /
  analyze 读出**同一个机制码**（含 binary → `price_table_json_invalid:UnicodeDecodeError`）；
  缓存包装同源（missing / models_list 两案）；spec 的 models 层 pass-through 断言
  "原样交出 + 零日志 + 消费点读出同一个码"；
- 空对象静默 doctrine：`{}` / `{"models": {}}` 全站点零留痕；真表在同批站点零留痕；
- 键缺席 vs 值 null：spec / report / ext / analyze 四处，`null` → `entry_not_object:NoneType`、
  键缺席 → `model_unregistered`，两者不共用一个码；
- run_b8 披露键：真表聚合的 `price` 元数据与受保护目录既有 `REPORT.json` 的 `price`
  **逐字段相等**且无 `table_reason` 键（聚合一律在 tmp 副本上跑）；四案机制点名 + 内置价兜底；
- 真表：七个读点读出**同一份** models 映射。

### 4.2 变异验证

`/tmp/ab17_mutate.py`，**8 处锚点逐处转红**，红例数依次 `14 / 7 / 5 / 1 / 1 / 3 / 1 / 4`
（M1 形状假值回静默 / M2 删文件缺席分支 / M3 收窄 JSON 异常捕获 / M4 spec 缺席-null 并回 /
M5 report 缺席-null 并回 / M6 统计侧形状披露静默 / M7 run_b8 恢复 `is_file()` 守卫 /
M8 空对象改点名）；每处变异前后 **collected 恒为 484**（无 `ImportError` / 语法红），
写盘前 `compile()`，跑完原字节还原并核对 sha256（**绝不用** `git checkout` / `git stash`）；
基线 484 passed 全绿、收尾还原后仍 484 passed 全绿。

### 4.3 全量与覆盖率

- 相关存量 + 四代准入锁共十六份文件 **761 例全绿**（§7 命令逐字可复算，本机 8.23s）。
- 登记前预跑：**10282 passed / 1 failed / 5 skipped / 181.15s**（collected 10288；
  带覆盖率口径），唯一失败 = 基线守卫本身（`BASELINE.yaml` 尚未刷新，属预期）。
- 刷新 `BASELINE.yaml` 后确认跑：**10283 passed / 5 skipped / 0 failed / 185.04s / rc=0**
  （coverage.xml 复算与登记**两次同值**）。
- 覆盖率（`COVERAGE_FILE=.coverage_ci … --cov=src --cov-branch`）：
  行 **18439/18963 = 97.2367%**、分支 **6653/7090 = 93.8364%**；
  较 AB-16（18419/18944、6638/7076）**+20 行 / +15 弧**，新增部分全部在
  `src/budget/pricing.py` 且 100% 被新锁执行（并收回 1 行存量——旧 `load_price_table`
  的结构不符 WARN 分支随重写被替换）；未覆盖行 **524** = 525 − 1、偏弧 **437** = 438 − 1
  （差额由 pricing.py 一项对账：141 语句 2 未覆盖〔397–398 `invalid_usage` 早退存量〕、
  66 弧 0 偏弧，其余文件合计净差 0，未逐个复算）；十项核心模块行覆盖与 routing 三项
  逐位不变。
  按 `docs/MEASUREMENT_INTEGRITY.md` §14：读数的变化与不变都不作缺陷与否的佐证，
  佐证是改动面文件清单（`src/budget/pricing.py` + 六处读点 + 测试 + 文档）。

### 4.4 受保护读数

- 真批次池化成本 `{aitester: 1.447277, plain_llm: 0.260967, plain_llm_df: 0.541408}`、
  总额 `2.249652` 由锁逐位断言；
- 真批次载荷不新增披露键、ext 三臂 `$/task`
  `0.025884977011494247 / 0.003358973563218391 / 0.004543231034482759` 逐位复现；
- run_b8 真表聚合的 `price` 元数据与受保护目录既有 `REPORT.json` 的 `price` 逐字段相等
  （聚合在 tmp 副本上跑，真实目录一份未改写）；
- 归档 P-1 README 未重生成（`估算成本 **$0.006195**` 仍在、行数 > 200）。

## 5. 未处置（登记）

1. **statistical 桶级词汇 `missing_models` 未分"未登记 / 域不合格 / 形状坏"**：
   `cost_analysis` 的桶只回答"缺哪些模型"，形状码只进 `unpriced_currency_models`
   （AB-15 §5.5 延续；本轮两条加载通道同源后桶词汇仍未动）。
2. **`run_b8_injection.py` 聚合脚本仍自持一套数字门**（AB-16 §5.2 延续）：
   `isinstance(..., (int, float))` 收价——`bool`（`int` 的子类）、`nan` / `inf`、负价都是
   该式的真值被收下；币种字段只被原样抄进 `price_meta`，不参与判定。本轮只加
   `isinstance(row, dict)`，数字门未接 `price_block_reason`。
3. **ext 的 `_load` `is_file()` 前置守卫 ⇒ 目录两套机制码**（设计性，记录在案）：
   目录在 ext 读 `price_table_file_missing`、其余六个读点读
   `price_table_file_unreadable:IsADirectoryError`；机制词汇同源，读取器语义差异保留（§2.5）。
4. **spec 加载器对 `models` 层 pass-through**（设计性，记录在案）：文件级失败在加载器点名、
   `models` 层形状在消费点点名（"谁做的判定谁点名"，§2.5）；两处各锁各的读法。
5. **ext 未登记模型仍是 `0.0` 部分和 + note**：`_cost_per_task` 对 `prices.get(m)` 缺席的模型
   只记 `unpriced` 并继续累加其余份额（AB-15 §5.4 延续；"拒绝"与"未登记"是两种事实，
   前者不产生金额已锁）。
6. **`price_block_reason` 对非 `int|float` 的真数一律拒**（AB-16 §5.6 延续）：
   `Decimal("1.0")` / `numpy.float64` 落 `price_not_a_number:<T>`；仓内价目表是 JSON 载入，
   当前无站点吃到这类值。
7. **测试侧第二套口径**：`tests/test_ae_batch.py:125` 的 `entry.get("currency", "USD")`
   是测试自己造的缺省美元（AB-15 §5.6 延续）。
8. **P-1 归档 README 不是渲染器产物**：归档 251 行、当前渲染器 64 行；本轮只锁"未重写"
   （AB-15 §5.9 延续）。
9. **`statistical_report_e2*.md` 的 86 / 88 行陈旧差值未消除**（AB-15 §5.8 延续）：
   本轮未复算、未重写。

## 6. 不得据本册引用

- 不得引用"价目表读取已全仓统一"：§5.2–§5.5 的通道仍各自为政（聚合数字门、ext 守卫差异、
  spec pass-through、ext 部分和）。
- 不得引用"未登记与形状错已全局分开"：§5.1 的统计桶仍在；§5.5 的 ext 部分和仍在。
- 不得引用"价目表读取已不丢条目"：`.get` 检索层已分离键缺席与 null 值（§2.3），
  但统计桶词汇（§5.1）尚未区分。
- 不得引用"run_b8 成本已按准入域判定"：§5.2 的自持数字门仍在。
- 不得引用"P-1 工件可由当前渲染器再生成"：§5.8 的 64 vs 251 行。
- 不得引用"入库统计报告可逐位复现"：§5.9 的 86 / 88 行差值未消除。
- 本册的读数都可以用 §7 的命令复算；`/tmp` 探针、矩阵与变异脚本不是入库工件，
  不得据此声称"仓库自带这些脚本"。

## 7. 复算命令

```bash
# 新锁（26 passed）
.venv/bin/python -m pytest tests/test_experiments_table_admission_ab17.py -q --no-cov

# 相关存量 + 四代准入锁（761 passed / 1 warning，8.23s）
.venv/bin/python -m pytest tests/test_experiments_table_admission_ab17.py \
  tests/test_experiments_price_admission_ab16.py tests/test_experiments_cost_rejection_ab15.py \
  tests/test_experiments_currency_caliber_ab14.py tests/test_experiments_price_table_ab13.py \
  tests/test_experiments_price_table_ab12e.py tests/test_experiments_absent_vs_zero_ab12.py \
  tests/test_experiments_absent_vs_zero_ab11.py tests/test_emse_stats_report.py \
  tests/test_emse_stats_extensions.py tests/test_oracle_examples.py tests/test_ae_batch.py \
  tests/test_an_batch.py tests/test_analyze_t1_b2_manual_sections.py \
  tests/test_r14_statistical_protocol.py tests/test_stvr_statistical_analysis.py -q --no-cov

# §1 边界读数（本地探针，不写仓库；现输出 = 改后读数，改前读数见 §1 表与 /tmp 矩阵）
.venv/bin/python /tmp/ab17_probe.py

# 变异验证（8 锚点；脚本自行还原原字节）
.venv/bin/python /tmp/ab17_mutate.py

# 全量与覆盖率（收口口径）
COVERAGE_FILE=.coverage.ci .venv/bin/python -m pytest tests/ -n 4 --dist loadfile \
  --cov=src --cov-branch --cov-report=term-missing --cov-report=xml
```

受保护目录 `experiments/results/s_round_b8_injection_20261018/` **不得**用聚合器对真实目录
运行（`aggregate()` 会重写 `REPORT.json` / README / `SHA256SUMS`）；新锁一律在 tmp 副本上跑。
P-1 归档 README 同样受保护，**不得**用当前渲染器覆盖。