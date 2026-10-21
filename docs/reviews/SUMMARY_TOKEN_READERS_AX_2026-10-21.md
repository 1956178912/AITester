# AX 轮：基准/全栈汇总的呈现与聚合读点（2026-10-21，零 LLM）

**范围**：三处仍把聚合 `token_metrics` 原值直出的汇总读点——

- `experiments/run_benchmark.py` 跑完后的终端 Token 效率两行（`%d` / `%.2f`）；
- `experiments/run_full_stack_swe_bench_pro.py` G8 Markdown 的"总 token"列；
- `experiments/summarize_full_stack.py` 的逐基线 token 均值。

**结论**：改前一次**完整基准**可以在收尾汇总处因上游合法写入的 `None`
抛 `TypeError`；全栈表遇到 `null` / 非对象直接崩或把坏值原样印出；
汇总均值把真值非对象变成整份中止、把假值非对象静默跳过、把
bool / 数字字符串 / 负数 / `nan` / `inf` 收进均值。处置后三处统一接共享
`token_metric_reading`：呈现层读不动落 `不可读` 并点名机制（不折 0、
不原值直出、不中止整轮）；均值缺席块沿历史跳过，任一在场块不可读 ⇒
该基线 `None` + `avg_total_tokens_reason`（不给部分均值），不连坐其他
基线。**48 例新锁 + 8/8 变异锚点转红 + 0 逃逸**；真语料递归 324 个
`token_metrics` 键（246 个 `results.<baseline>` 汇总块 + 78 个嵌套形状）
零坏值，246 个汇总块终端文本逐字不变（6 个 PREFLIGHT 嵌套块缺
`avg_tokens_per_task`，不参与该对照）、全栈干净行逐字节
不变、四基线均值逐位复现。确认跑 **11174 passed / 5 skipped /
0 failed、177.06s、rc=0**。**未提交。**

---

## 1. 缺陷定义

### 1.1 终端汇总（`run_benchmark`）

改前活路径在整轮基准结束后执行：

```python
tm = baseline_result.get("token_metrics", {})
logger.info(
    "  [%s] Token效率: 总tokens=%d, 平均每任务tokens=%.2f, LLM调用次数=%d",
    baseline,
    tm["total_tokens"],
    tm["avg_tokens_per_task"],
    tm["total_llm_calls"],
)
```

AN 的聚合读取器与 AT 的写入口已经把"上游拒绝"表达为**字段在场、值为
`None`**。`%d` / `%.2f` 没有 `None` 输入域：一个合法拒绝会让一次已经
跑完的基准在汇总处抛 `TypeError`，此前的任务结果与耗时全部无法落盘。

### 1.2 全栈 Markdown 表（`run_full_stack_swe_bench_pro`）

改前逐基线直接取字段：

```python
tm = bl.get("token_metrics", {})
lines.append(f"| {baseline} | ... | {tm.get('total_tokens')} |")
```

`null` 与非对象不是键缺席，`bl.get("token_metrics", {})` 兜不住：
`null` 在 `.get` 上抛 `AttributeError`，非对象同样崩；bool / 数字字符串 /
负数 / 小数则原样进入 Markdown，读者无法区分"观测值"与"坏载荷"。

### 1.3 逐基线均值（`summarize_full_stack`）

改前：

```python
tm = bl.get("token_metrics") or {}
if tm.get("total_tokens") is not None:
    per_baseline_tokens[baseline].append(float(tm["total_tokens"]))
```

四类后果：

1. **真值非对象中止整份汇总**：`"abc"` / `True` / `["x"]` 让 `.get` 抛
   `AttributeError`，逐基线均值与同一份汇总里的成功率、失败类别全部丢失。
2. **假值非对象被静默跳过**：`[]` / `""` / `0` 被 `or {}` 改写，坏载荷
   冒充"没有 metrics"，从分母里消失。
3. **值域缺失**：`True` 当 1、数字字符串、小数、负数、`nan` / `inf` 全部
   进入 `float()`；一份坏块可以污染整个基线均值。
4. **部分均值**：若跳过坏块继续平均，剩余可读值会给出一个"看似完整"的
   数字，掩盖同一基线里存在不可读观测这件事。

## 2. 真语料测量（只读探针，改前/改后同一口径）

扫描 `experiments/results/`（只读，不重写任何归档或原始批次）：

| 观测 | 实测 |
|---|---|
| 顶层 `benchmark_*.json` | **64** 份 |
| 顶层逐基线块 | **92** 个 = **58** 个 `token_metrics` 缺席 + **34** 个 dict 块 |
| 顶层 dict 块 `total_tokens` | **34 / 34** 为 int，负数 **0** |
| 递归全部结果 JSON 的 `token_metrics` 键（所有出现） | **324**（全部为 dict） |
| 其中 `results.<baseline>` 汇总块 | **246** |
| 其余嵌套形状（`per_seed` / `items` / `arms` / `harness_smoke` / PREFLIGHT 等） | **78**（其中 6 个 PREFLIGHT 旧基线块缺 `avg_tokens_per_task`） |
| 非对象 / `null` / 坏计数 | **0** |

干净路径的独立复算：

| 复算 | 结果 |
|---|---|
| 终端 Token 效率文本（246 个 `results.<baseline>` 汇总块） | **246 / 246** 逐字不变（6 个 PREFLIGHT 嵌套块缺字段，不参与该对照） |
| 全栈表干净行 | **逐字节相同** |
| 四基线均值（独立重算） | aitester **140990.071**、plain_llm **29061.077**、plain_llm_df **1668.0**、single_agent **112225.833**，逐位一致且无 `avg_total_tokens_reason` |

旧表达式与新实现的现场对照：

| 输入 | 改前 | 改后 |
|---|---|---|
| 三字段全 `None`（上游拒绝） | `TypeError` / 表崩 | 文本 `不可读` + 机制名；均值 `None` + 理由 |
| `token_metrics=None` | 终端 `TypeError`；表 `0`（仅表） | 终端 / 表按 AE2 历史 0；均值沿历史跳过 |
| `total_tokens` 字段缺席 | 终端 `KeyError` | 历史 0（呈现）/ 跳过（均值） |
| `{"total_tokens": true}` | 终端 `TypeError`；表印 `True`；均值折 1.0 | `不可读` + `token_not_count:total_tokens:bool` |
| `{"total_tokens": "100"}` | 同上 / 表印 `100` / 均值 100.0 | `不可读` + `token_not_count:...:str` |
| `{"total_tokens": -5}` | 表印 `-5`；均值 -5.0 | `不可读` + `token_negative:total_tokens` |
| `{"total_tokens": nan}` / `inf` | 表印 `nan` / `inf`；均值非有限 | `不可读` + `token_not_finite:total_tokens` |
| `"abc"` / `["x"]` / `0`（整份非对象） | 终端 / 表 / 均值崩或改写 | `不可读` + `token_metrics_not_object:<T>`；均值不给部分均值 |

口径说明：缺陷是**边界潜伏**而非存量污染——历史工件恰好都是干净对象，
所以本轮不回填历史数据；修复目标是让未来任何一次拒绝 / 坏形状 / 坏计数
都**可披露、不可崩、不可改写成小一号的事实**。

## 3. 处置

### 3.1 终端：先读数、再格式化

新助手 `_token_efficiency_texts(metrics)` 返回 `(日志行主体, 进度行主体,
机制名列表)`：

- `total_tokens` / `total_llm_calls` 走整数口径，`avg_tokens_per_task`
  走 `allow_float=True`；
- 三个字段各自判定，机制名去重；一个字段坏不连坐其它字段；
- 可读 → 保持历史 `%d` / `%.2f` / f-string 文本逐字不变；
- 不可读 → 该字段渲染 `不可读`，日志另发 `warning` 列机制名，**不中止
  整轮、不折 0**；
- 缺席 / `null` 整份 metrics 仍按 AE2 历史 0。

### 3.2 全栈表：坏单元只废自己

新助手 `_render_baseline_table(summary)`：

- 每个基线独立读取 `token_metric_reading(bl.get("token_metrics"),
  "total_tokens")`；
- 可读 / 缺席 / `null` 按历史输出数字（缺席与 `null` 是 AE2 历史 0）；
- 在场坏形状或坏值落 `| 不可读 |`，并在表后追加
  `> <baseline> 的总 token 不可读（机制…）`；
- 一个基线坏不中止整张表，其余基线与成功率、覆盖率、迭代三列照常输出。

### 3.3 均值：不折 0、不给部分和

- 只收共享谓词认可的有限非负计数；
- **缺席块沿历史口径跳过**（旧 `or {}` 行为），不把缺席折成 0；
- **在场块不可读 ⇒ 该基线 `avg_total_tokens=None` +
  `avg_total_tokens_reason`（机制名去重后以 `|` 拼接）**，不再用剩余
  可读值给部分均值；
- 不可读只废该基线的 token 均值：`total_tasks`、`passed_count`、
  `success_rate`、错误桶、迭代与耗时全部照常；
- 其他基线互不连坐；干净语料的键集与值逐位不变。

### 3.4 为什么呈现可以折 0、均值不可以

呈现层的历史契约是"缺席读 0"（AE2），读者看到的是单份载荷的一个单元；
均值是**跨块聚合**，任何一份在场块读不动都意味着这个均值没有完整分母，
继续平均就是部分和冒充完整事实。三处沿用同一共享读取器、各自保持
历史聚合口径，不引入第二套判定。

## 4. 回归锁

`tests/test_token_usage_summary_ax.py`：5 个测试类，参数化展开 **48 例**。

| 类 | 例数 | 覆盖 |
|---|---|---|
| `TestRunBenchmarkTokenEfficiencyTexts` | 10 | 干净文本逐字、上游 `None` 不崩、缺席历史 0、六种坏计数、三机制去重 |
| `TestFullStackMarkdownTokenCell` | 17 | 干净行、`null` 历史 0、七种坏形状、七种坏值、字段缺席历史 0 |
| `TestSummarizeFullStackTokenAverage` | 17 | 均值 150.0、缺席跳过、在场 0 计入、六种非对象不中止其他统计、七种坏值不给部分均值、跨基线隔离 |
| `TestRealCorpusCleanPath` | 1 | 顶层 64 份 / 34 个 token 块独立重算均值逐位复现 |
| `TestSourceLocks` | 3 | 三个读点不得回退到宽松读取（函数体锁，跳过 docstring） |

受影响面只读复核：`tests/test_experiments_ab_scaffolds.py`、
`tests/test_token_usage_reports_ap.py`、`tests/test_cost_usage_readers_aw.py`
均通过。

## 5. 变异验证

8 个真实锚点；逐锚点：写入变异 → `compile()` → 跑 48 例 →
sha256 原字节还原。基线 48 passed，collected 恒 48，还原后 48 passed。

| 锚点 | 变异 | 红数 |
|---|---|---|
| M1-C-raw-total | 终端 `total_tokens` 回退原值直出 | 8 |
| M2-C-avg-fixed2 | 终端均值绕过读数直接 `:.2f` | 9 |
| M3-C-reasons-empty | 终端不可读不再给机制名 | 8 |
| M4-FS-cell-raw | 全栈表单元格回退原值 | 14 |
| M5-FS-loose-shape | 全栈表放大形状判定（非对象当缺席） | 17 |
| M6-FS-note-dropped | 全栈表删除不可读注记 | 14 |
| M7-SF-partial-mean | 均值跳过坏块继续平均（部分和） | 13 |
| M8-SF-absent-as-zero | 均值把缺席块折 0 | 2 |

**8/8 锚点转红，0 逃逸。** 还原后源文件与测试文件逐字节一致
（`summarize_full_stack.py` sha256 `d16baf38…bdb4`、
`run_full_stack_swe_bench_pro.py` `eaaff310…48d3`、
`run_benchmark.py` `1abb8691…d65`、测试文件 `a40b3954…bd6`）。

## 6. 收口读数

- 登记前一跑（不带 `--cov`）：**11173 passed / 1 failed / 5 skipped、
  176.17s**；collected **11179**；唯一失败 = BASELINE 数字守卫（仍写
  11126，实收 − 声明 = 53 > 6 容差）。同口径覆盖率跑
  **11173 passed / 1 failed / 5 skipped、181.50s**（同一通过数、同一守卫）。
- 覆盖率（`coverage.xml` root 口径）：**19002 / 19528 行 = 97.3064%**、
  **6960 / 7396 弧 = 94.1049%**；未覆盖 **526** 行、缺弧 **436**，
  与 AW 逐位相同（本轮 `src/` 零改动，改动面在 `experiments/` + 测试 + 文档）。
- 十项核心模块：**0 项变动**（base_agent 98.53、api_manager 99.24、
  dataset_loader 97.28、graph_nodes 99.88、code_analyzer 99.38、planner
  99.09、dependency 96.26、multi_candidate 98.67、cross_file 92.98、
  rag_retriever 98.10）；核心路由三项分支逐位不变（graph_workflow 99.17、
  error_classifier 96.49、graph_state 100.00）。
- 确认跑（刷新 BASELINE 后）：**11174 passed / 5 skipped / 0 failed、
  177.06s、rc=0**（collected 11179）。
- 门禁（单独跑 `make gates`，不与其他命令重叠；首跑在
  `ruff format --check .` 转红——本轮手册的 Python 围栏需折行，按
  `ruff format` 修正手册后全链重跑）：**rc=0**；墙钟 **182.84s**；
  链内 pytest **11174 passed / 5 skipped / 0 failed、177.56s**
  （36 warnings；collected 11179）；`ruff format --check .` **928 files**、
  mypy **135** 源文件、双语文档 0 警告 / 0 失败、文档链接 strict
  **166 份 / 703 条 / 0 错误 0 警告**、env-budget 253/253、状态通道 134
  文件、env-snapshot 84/84、tool-versions OK、JSON 契约 7/7、JSON strict
  **7273 工件 0 违规 / 300 源文件 0 写入点违规**、报告↔工件对账 [OK]、
  零断言 **442 文件 / 0 违规**。
- 回填门禁读数后验证跑（再次单独 `make gates`，不与其他命令重叠）：
  **rc=0**；墙钟 **184.44s**；链内 **11174 passed / 5 skipped / 0 failed、
  179.25s**（36 warnings；collected 11179）；其余读数与首跑一致（ruff
  format **928 files**、mypy **135** 源文件、文档链接 **166 份 / 703 条 /
  0 错误**、零断言 **442 文件 / 0 违规**、JSON strict 7273 工件 0 违规）。

## 7. 边界（不得引用为「token 读数已在所有汇总面闭合」）

1. **只覆盖三个汇总读点**：仓内其他脚本、shell 批跑器与归档 `_helpers`
   仍可自行读取 token 字段；本轮不触碰受保护工件。
2. **呈现折 0 只限缺席 / `null`**：在场坏值一律 `不可读` + 机制名；
   读者不得把 `不可读` 当成 0 或免费。
3. **均值 `None` 是"该基线无完整分母"**：不是"没有 token"，也不是 0；
   对外引用必须同时看 `avg_total_tokens_reason`。
4. **成功率与均值独立**：token 不可读不影响 `total_tasks` /
   `passed_count` / `success_rate` / 错误桶 / 迭代 / 耗时。
5. **终端 warning 不是失败**：基准照常完成并落盘；warning 只披露
   哪几个读数不可判定。
6. **真实语料零坏值不等于修复无价值**：324 个键零坏值与 246 个汇总块终端文本不变只证明干净路径不变；
   坏形状路径由 48 例锁与 8 个变异锚点证明。
7. **未调用 `--write`**：入库报告与原始批次零改动，本轮未重写任何
   `SHA256SUMS` 保护的归档或原始批次 JSON。

## 8. 复算命令

```bash
# 目标锁（48 collected）
.venv/bin/python -m pytest tests/test_token_usage_summary_ax.py -q

# 受影响面（只读复核）
.venv/bin/python -m pytest tests/test_experiments_ab_scaffolds.py \
  tests/test_token_usage_reports_ap.py tests/test_cost_usage_readers_aw.py -q

# 全量 + 覆盖率（CI 同口径；不与 make gates 重叠）
make test-cov

# 确认跑（BASELINE 刷新后）
make test

# 门禁（最后单独跑，绝不与其他命令重叠）
make gates
```
