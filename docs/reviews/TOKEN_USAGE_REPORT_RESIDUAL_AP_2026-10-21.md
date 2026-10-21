# AP 轮：五处报告侧聚合 token 汇总也只认一种读数——池化、冒烟、A/B、分组均值、成本表不得各算一遍（2026-10-21，零 LLM）

**范围**：`experiments/analyze_t1_b2_main_batch.build_report/render_*`（逐 seed 池化、
批次合计、README/基线片段）、`experiments/run_b8_injection._write_readme`（冒烟合计、
主批表与 §9 合计）、`experiments/rag_ab_experiment._parse_task_record/compare_ab`
（逐记录解析、配对统计与解读）、`experiments/analysis_parts/rag_analysis._rag_token_efficiency`
（分组均值与比值；渲染由 `experiments/analyze_results.py` 消费）、
`experiments/analyze_results.render_markdown`（成本表 Token 效率行与 RAG Token 段）。
生产者模块 `src/budget/token_usage` 新增**聚合 metric 口径**共享读取器
`token_metric_reading` + `sum_token_metric_values`。

**结论**：AO 收口了三个**行级 / 报告级总量**读端，但写盘 `token_metrics` 的**聚合对象**
仍有五个消费端各自做 Python 真值折叠：`tm.get(...) or 0`（t1_b2 池化）、
`int(... or 0)` / `.get("total_tokens", 0) + ...`（b8 README）、
`token_usage.get("total_tokens", 0)` + `_mean`（rag_ab 解析与统计）、
`_safe_float(... or 0)`（RAG 分组均值）、`t.get(..., 0)`（成本表）。同一个坏字段在五个
读端分别表现为静默 0、字面量 `None`、崩溃、伪均值或假"无显著差异"。处置后：聚合对象
交共享读取器，字段缺席按历史 0、字段在场 `None` 是**上游已拒绝**而不是零、计数走唯一
值域 `count_reason`、派生均值只收有限非负 int/float；聚合求和任一行不可读 ⇒ 整列
`None`（不给部分和）。真工件复算：t1_b2 三臂池化 **2629059 / 310018 / 643952**、
b8 **83246 / 113638**、rag_ab 20+20 对与主批表 **2544615 / 284317 / 404268** 全部逐位
不变。**67 例新锁 + 33/33 变异锚点转红 + 0 逃逸**。

---

## 1. 缺陷定义

改前五处消费端的读取（`experiments/`，均为 AP 前原文）：

```python
# analyze_t1_b2_main_batch.build_report（逐 seed 池化 + 批次合计）
tm = st["token_metrics"] or {}
tokens["in"] += tm.get("total_input_tokens") or 0
tokens["total"] += tm.get("total_tokens") or 0
total_tokens = sum(v["tokens"]["total"] for v in pooled.values())

# run_b8_injection._write_readme（冒烟合计 + 主批表 + §9）
smoke_tokens = sum(int((row.get("token_metrics") or {}).get("total_tokens") or 0) for row in smoke)
... on["token_metrics"].get("total_tokens") ...
... on["token_metrics"].get("total_tokens", 0) + off["token_metrics"].get("total_tokens", 0) ...

# rag_ab_experiment（逐记录解析 + 配对统计）
token_usage = record.get("token_usage") or {}
tokens_total = token_usage.get("total_tokens", 0)
t_tok, p_tok = _welch_ttest(on_tokens, off_tokens)   # 直接吃 tokens_total
d_tok = _cohens_d(on_tokens, off_tokens)

# analysis_parts.rag_analysis._rag_token_efficiency（分组均值 + 比值）
avg_tokens = round(sum(_safe_float((r.get("token_usage") or {}).get("total_tokens", 0) or 0) for r in rows) / n, 2)
token_delta_ratio = round(rag_stat["avg_tokens"] / no_rag_stat["avg_tokens"], 4) if no_rag_stat["avg_tokens"] else None

# analyze_results.render_markdown（成本表 + RAG 段）
f"| {baseline} | {t.get('total_tokens', 0)} | {t.get('total_input_tokens', 0)} ..."
f"| {baseline} | {g.get('tasks', 0)} | {g.get('avg_tokens', 0)} ..."
```

| 观测（合成行） | 改前读数 | 根因 |
|---|---|---|
| t1_b2：`token_metrics=None` | 该 seed 四字段各 **0** | `or {}` 把"无记账"与"上游拒绝"同形 |
| t1_b2：`token_metrics=[]` | 静默 **0** | 假值非对象被 `or {}` 吞掉 |
| t1_b2：`token_metrics="oops"` | `AttributeError`，整份批次报告崩 | truthy 非对象仍走 `.get` |
| t1_b2：`total_tokens=True` / `10.7` | 记 **1** / **10.7** | 无类型门；bool 是 int，float 被收下 |
| t1_b2：`total_tokens="100"` | `TypeError`，整份报告崩 | `int + str` 无类型门 |
| t1_b2：`total_tokens=-5` | 池化总量被 **拉低** | 无负数门 |
| t1_b2：`total_tokens=nan` / `inf` | 池化总量变 nan / inf | 无非有限门 |
| t1_b2：某臂总量 nan，批次合计 | 合计 nan | `sum` 无有限门 |
| b8：冒烟 `total_tokens=True` / `10.7` / `"100"` | 记 **1 / 10 / 100** | `int()` 收 bool、截断 float、解析 str |
| b8：冒烟 `"10.7"` / `nan` / `inf` | `ValueError` / `ValueError` / `OverflowError`，README 不生成 | `int()` 无值域门 |
| b8：冒烟 `token_metrics="oops"` | `AttributeError` | truthy 非对象仍走 `.get` |
| b8：主批表字段为 `None` | 印字面量 **`None`** | `.get` 无拒绝分支 |
| b8：§9 一侧 `None` / 两侧 str | `TypeError` 或字符串拼接 | `+` 无类型门 |
| rag_ab：`token_usage="oops"` | `AttributeError`，解析崩 | `or {}` 只挡假值 |
| rag_ab：`total_tokens=None` | `None` 进 `_mean` ⇒ `TypeError`，统计崩 | 拒绝值未在入口处置 |
| rag_ab：`total_tokens="100"` / `True` / `-5` / nan | 进统计为 str / 1 / −5 / nan | 无类型、负数、有限门 |
| rag_ab：token 为 nan | p 值为 nan ⇒ `p < 0.05` 为假，输出 **"无显著差异"** | nan 被当成"不显著" |
| rag_analysis：`total_tokens="100"` / `True` / `"abc"` | 均值收 **100.0 / 1.0 / 0.0** | `_safe_float` 强转、解析失败归 0 |
| rag_analysis：`total_tokens=-50` / nan | 负值 / nan 进入均值与比值 | 无负数、有限门 |
| rag_analysis：`token_usage="oops"` | `AttributeError`，整份分析崩 | `or {}` 只挡假值 |
| analyze_results：字段在场 `None` | 表格印字面量 **`None`** | `.get(..., 0)` 只挡缺席 |
| analyze_results：`token_metrics="oops"` | `AttributeError`，报告崩 | 无对象门 |
| analyze_results：`"100"` / `nan` / `inf` | 原样印 **100 / nan / inf** | 无值域门，字符串冒充数字 |
| analyze_results：RAG 组均值 nan | 印 `nan`；比值 nan | 无有限门 |

要点：**同一个"聚合 token_metrics 字段"事实在五个消费端有五种命运**。AQ 前的这一族
不能复用 AO 的 `row_total_token_reading`：那个读取器读 `details[]` 的嵌套
`token_usage`，把整键缺席 / `None` 当历史 0；聚合 `token_metrics` 里的 `None` 是
**上游 AN/AO 已经拒绝**的结果（写侧 `run_benchmark._aggregate_token_metrics` 只在
坏行时写 `None`），把它当"缺席 0"会二次吞掉拒绝。两种对象、两种问法，需要第三个
读取器；**值域仍只有 `count_reason` 一个**。

## 2. 处置

### 2.1 聚合 metric 口径共享读取器

`src/budget/token_usage.token_metric_reading(metrics, key, *, allow_float=False)`
（`src/budget/token_usage.py:631`）：

| 聚合对象形态 | `value` | `absent` | 披露 |
|---|---|---|---|
| 整份 metrics 为 `None` | `0` | `True` | 无（AE2 历史口径） |
| 整份 metrics 非对象 | `None` | `False` | `token_metrics_not_object:<T>` |
| 字段缺席 | `0` | `True` | 无（旧 schema 口径） |
| 字段在场 `None` | `None` | `False` | `token_metric_unreadable:<key>`（上游拒绝） |
| 计数字段在场 bool / str / 负数 / nan / inf | `None` | `False` | `count_reason` 机制名 |
| `allow_float=True`：有限非负 int/float | 该值 | `False` | 无 |
| `allow_float=True`：bool / 非有限 / 非数字 / 负数 | `None` | `False` | `token_not_number` / `token_not_finite` / `token_negative` |

`sum_token_metric_values(metrics, key)`（`src/budget/token_usage.py:675`）：
`{value, n_readable, n_absent, n_unreadable, reasons}`。任一份不可读 ⇒
`value=None`（**不给部分和**）；缺席 / `None` 整份按历史 0 且计 `n_absent`；
机制名按份累计并排序。

与 AO / AN 读取器的分工（不得互换）：

| 读取器 | 输入 | 缺席口径 | 在场 `None` 口径 |
|---|---|---|---|
| `row_token_reading`（AN） | 行级 `token_usage` 三元组（成本计价） | 历史 0 | 不可读（成本不可计价） |
| `row_total_token_reading`（AO） | 行级 `token_usage` 总量（报告展示） | 历史 0 | 不可读 |
| `token_metric_reading`（AP） | 写盘聚合 `token_metrics` 字段 | 历史 0 | **上游已拒绝**，不可读 |

### 2.2 五个消费端

| 消费端 | 接线 | 读不动时 | 旧 schema |
|---|---|---|---|
| `analyze_t1_b2_main_batch.build_report`（池化 `:649`、合计 `:850`） | 逐字段 `sum_token_metric_values`；`tokens` 取 `reading["value"]`；批次合计任一侧 `None` ⇒ `None` | 该字段整列 `None`；`token_reading_reasons` / `token_unreadable_arms` 披露；渲染「不可读」 | metrics / 字段缺席仍历史 0；干净读数逐位不变 |
| `run_b8_injection._write_readme`（`:952` / `:971`） | 冒烟 `sum_token_metric_values`；主批表 `_token_metric_text`；§9 两侧任一不可读 ⇒「不可读」 | 表格「不可读」+ `token 读数不可用` 注（机制×次数）；成本列仍按标准价上界 | 缺席字段历史 0 |
| `rag_ab_experiment._parse_task_record` / `compare_ab`（`:158` / `:249`） | 解析走 `row_total_token_reading`；配对任一侧不可读 ⇒ 统计门关闭 | 均值/标准差/差值/百分比/检验量全部 `None`；`n_token_unreadable_records` + 机制名；解读「不可判定」；CLI 印「不可读」 | 整键缺席 / `None` 历史 0（该行可读） |
| `rag_analysis._rag_token_efficiency`（`:147`） | 组内逐行 `row_total_token_reading`；任一行不可读 ⇒ 组均值 `None` | `n_token_unreadable_rows` + `token_reading_reasons`；比值 `None` | 缺席行仍历史 0；干净组五键逐位不变 |
| `analyze_results.render_markdown`（`:292` / RAG 段） | 五字段逐项 `token_metric_reading`（均值 `allow_float=True`）；RAG 组均值 `None` ⇒ 拒绝 | 单元格「不可读」+ `Token 读数不可判定` 注；比值 `N/A` | 缺席 / `None` 整份 metrics 历史 0 |

呈现层不再替读取层兜底：`不可读` / `N/A` / `0` 三种外形分别对应"在场读不动" /
"派生比值不可算" / "读到零"。b8 的成本列与 rag_ab 的迭代/耗时统计不受 token 拒绝牵连
（不同事实不同门）。

## 3. 真工件证据

只读复算（未改写任何归档或原始批次 JSON）：

- **t1_b2 主批**：`aitester` `{in 1897326, out 731733, total 2629059, calls 983}`、
  `plain_llm` `{123394, 186624, 310018, 271}`、`plain_llm_df` `{257038, 386914, 643952, 508}`；
  成本合计 **3583029** tokens。README 人工段之外的生成行与 `BASELINE_FRAGMENT`
  逐字节一致。
- **b8**（`s_round_b8_injection_20261018`）：on **83246 / 58 calls**、off
  **113638 / 82 calls**；冒烟合计 **64415**、主批合计 **196884**；成本
  **$0.033032 / $0.107292**；README 可复现且逐字节一致。
- **rag_ab_synthetic**：20 + 20 条记录，配对均值 **4345.6 / 3088.3**、
  Δ **−1257.3**；原始 details 的分组均值 **4345.65 / 3088.35**、比值 **1.4071**。
- **rag_lvl25h_n40**：配对均值 **4197.4 / 1558.3**、Δ **−2639.1**；原始 details
  的分组均值 **4197.38 / 1558.28**、比值 **2.6936**。
- **主批成本表**：`aitester 2544615 | 565287 | 1979328 | 396 | 29248.45`、
  `plain_llm 284317 | 46496 | 237821 | 96 | 3268.01`、
  `plain_llm_df 404268 | 52595 | 351673 | 87 | 4646.76`。

**已登记的陈旧差值（不改写工件）**：`experiments/results/rag_ab_synthetic/rag_ab_report.json`
的统计量早于 2026-10-01 的统计修复——报告存 `p_welch=0.29198 / u=113.5 /
p_mw=1.0`，同一份原始 details 复算为 `0.298675 / 286.5 / 0.019944`；
`rag_lvl25h_n40` 存 `p=2.4e-05`、复算 `6.7e-05`。本轮只把这类文件当**输入读数**，
不据此重写报告，也不把报告存量数字当成"本轮复算值"。

## 4. 回归锁

`tests/test_token_usage_reports_ap.py`：**67 例**（collected）。

| 组 | 例数 | 覆盖 |
|---|---|---|
| `TestTokenMetricReading` | 20 | 缺席整份/字段历史 0、在场 0、在场 `None` 拒绝、计数坏值参数化、非对象参数化、`allow_float` 收/拒参数化 |
| `TestSumTokenMetricValues` | 5 | 干净求和、缺席计 0、任一不可读阻断部分和、非对象、空输入、机制计数 |
| `TestT1B2PooledTokens` | 6 | 真批三臂复算、`不可读` 渲染、基线片段、坏池化阻断批次合计、源码锁（共享求和） |
| `TestB8Readme` | 4 | `_token_metric_text` 干净/坏值、真 README 逐字节复现、主批不可读渲染、源码锁 |
| `TestRagAbParse` | 8 | 缺席历史 0、total-only / in-out-only、坏值参数化（含机制名） |
| `TestRagAbCompare` | 6 | 干净对比不变、不可读阻断统计、bool 不记 1、负数不入均值、真合成批、源码锁（scipy 前有门） |
| `TestRagTokenEfficiency` | 10 | 干净组不变、坏组参数化、缺席历史 0、零分母、真批次混合组、源码锁（不再 `_safe_float`） |
| `TestAnalyzeResultsTables` | 8 | 真批 token 表不变、`None`/非对象/坏均值拒绝、RAG 段两侧拒绝、源码锁 |

另按新口径改写 `tests/test_2026_09_27_review_round10.py` 的 1 例旧锁：字符串 token
不再静默归 0，而是该组 `avg_tokens=None`、`n_token_unreadable_rows=1`、
`token_reading_reasons={"token_not_count:total_tokens:str": 1}`，对照组整键缺席仍
历史 0，比值 `None`。真工件组在缺文件时 `pytest.fail`，不静默 skip。

## 5. 变异验证

基线 sha256（AP 末态）：`src/budget/token_usage.py` `73b5aefe…e18b1`、
`experiments/analyze_t1_b2_main_batch.py` `4d4d2393…e6921`、
`experiments/run_b8_injection.py` `26b95f85…e7e77e`、
`experiments/rag_ab_experiment.py` `bd280564…fe992e`、
`experiments/analysis_parts/rag_analysis.py` `c5abf41b…1dd69`、
`experiments/analyze_results.py` `99084e6a…34c0b`；目标集 collected 恒 **67**。
每个锚点：精确一次替换 → `compile()` 预校验 → 写回 → 跑目标集（`-x`）→
**sha256 原字节还原**（不用 `git checkout` / `git stash`）。

| 组 | 锚点 | 结果 |
|---|---|---|
| 共享读取器（7） | `metric-null-fold`、`metric-bool-accepted`、`metric-nonfinite-accepted`、`metric-negative-accepted`、`metric-nonobject-crash`、`metric-absent-unreadable`、`sum-partial-sum` | 7/7 红 |
| t1_b2（5） | `t1-fold-value`、`t1-fold-report-total`、`t1-tokens-text`、`t1-readme-tokens-cell`、`t1-cost-text` | 5/5 红 |
| b8（5） | `b8-metric-text-fold`、`b8-smoke-fold`、`b8-main-fold`、`b8-note-suppressed`、`b8-table-bypass` | 5/5 红 |
| rag_ab（6） | `ragab-parse-raw`、`ragab-gate-open`、`ragab-gate-bypass`、`ragab-avg-fold`、`ragab-interp-branch`、`ragab-disclosure-suppressed` | 6/6 红 |
| RAG 分组（4） | `rag-unreadable-empty`、`rag-avg-fold`、`rag-ratio-unguarded`、`rag-raw-usage` | 4/4 红 |
| 成本表（6） | `ar-cell-raw`、`ar-notes-suppressed`、`ar-avg-no-float`、`ar-rag-avg-fold`、`ar-rag-no-rag-avg-fold`、`ar-rag-note-suppressed` | 6/6 红 |

合计 **33/33 非中性锚点转红、0 逃逸**；还原后目标集 **67 passed**，七个文件 sha256
与基线逐字节相同。

**收口期自纠（首轮逃逸）**：`ar-rag-avg-fold` 初版只让「无 RAG 组」不可读，变异
「RAG 组均值折 0」仍 rc=0——测试形状没有覆盖被变异的分支。补
`test_rag_section_unreadable_rag_group_renders_refusal`（RAG 组不可读）后转红，并
新增锚点 `ar-rag-no-rag-avg-fold` 反向覆盖另一侧。**教训同 AO：变异逃逸先怀疑测试
形状，不要先怀疑锚点无效。**

## 6. 收口读数

- 登记前一跑：`make test-cov` → **10841 passed / 1 failed / 5 skipped**，
  177.20s；唯一失败 = 基线守卫自身（BASELINE 仍写 10775，实收 10847 − 声明
  10775 = 72 > 6 容差）。
- **覆盖自审**：`coverage.xml` 复算 **18760/19284 行 = 97.2827%**、
  **6825/7262 弧 = 93.9824%**；`budget/token_usage.py` 唯一未覆盖行仍是既有
  175，两个新函数的全部语句与判定弧均被执行。分母较 AO **+43 行 / +28 弧**，
  覆盖同步 **+43/+28**；未覆盖 **524**、缺弧 **437** 与 AO 逐位相同，不作回收或
  退化主张；`coverage report` 偏弧 **383** 与缺弧是不同口径。
- 刷新 `BASELINE.yaml`（10842 / 18760·19284 / 6825·7262）后确认跑：
  **10842 passed / 5 skipped / 0 failed、178.84s、rc=0**；collected **10847**
  = passed 10842 + skipped 5（= AO 的 10780 + AP 的 67）。
- 十项核心模块行覆盖与三项核心路由分支覆盖按同一份 `coverage.xml` 复算全部不变
  （base_agent 98.51 / api_manager 99.24 / dataset_loader 97.28 / graph_nodes 99.88 /
  code_analyzer 99.38 / planner 99.09 / dependency 96.26 / multi_candidate 98.67 /
  cross_file 92.98 / rag_retriever 98.10；routing 99.17 / 96.49 / 100.00）。
- **门禁实测（两次单独跑 `make gates`，均不与其他命令重叠）**：两次均 `rc=0`；墙钟 **183s / 182s**；链内 pytest（`-n 4 --dist loadfile`，**不带 `--cov`**，与本轮带覆盖率读数不可互换）**10842 passed / 5 skipped / 0 failed、177.46s / 176.97s**（collected 10847；两次墙钟差 1s 不作性能主张）；回填两次读数后为验证末次文档改写又单独复跑一次：`rc=0`、墙钟 **184s**、链内 **179.57s**——末态与回填读数同口径（墙钟抖动 ±2s 不作性能主张）。`ruff check` All checks passed、`ruff format --check .` **912 files already formatted**、mypy `Success: no issues found in 135 source files`；双语文档 0 警告 / 0 失败；文档链接 strict **158 份文件 / 672 条链接 / 0 错误 / 0 警告**；env-budget 253/253 登记；`check_baseline` 结构校验与 `check_baseline_numbers` 均通过；状态通道 134 文件通过；env-snapshot 84/84 覆盖、缺失 0；JSON 契约 7/7；JSON strict **7273 工件 = 7271 严格 + 2 路径豁免 + 0 违规、300 源文件 0 写入点违规**；报告↔工件对账 [OK]（不一致 0；T-10 严格 29 行 / 25 可测，宽松 62 / 55；状态登记册覆盖率对账相符）；零断言 **434 测试文件 / 0 违规**。
- 本轮 `src/` 改动只有 `src/budget/token_usage.py`（+`token_metric_reading`，
  +`sum_token_metric_values`；+43 行 / +28 弧）；五个消费端都在 `experiments/`，
  不在 `--cov=src` 分母内，由其 67 例锁与 33 个变异锚点佐证。

## 7. 边界（不得引用为「报告侧 token 汇总已全仓闭合」）

1. **聚合 `None` 不是缺席**：`token_metrics` 字段在场为 `None` 表示上游 AN/AO 已
   拒绝该字段，必须继续不可读；只有整份 metrics / 字段**缺席**才按 AE2 历史 0。
2. **历史 0 不等于免费**：缺席行的真实成本口径由 AK 的
   `cost_caliber=recorded_lower_bound` 负责，本轮不改变该结论。
3. **不给部分和**：`sum_token_metric_values` 任一份不可读即整列 `None`；不得据
   `n_readable` 自行拼部分和当总量。
4. **`allow_float` 只给派生均值**：`avg_tokens_per_task` 可收有限非负 float；
   计数字段仍走 `count_reason`，不得用 `allow_float` 放宽计数。
5. **token 门不牵连其他统计**：b8 成本列仍是标准价上界；rag_ab 的迭代/耗时统计
   不受 token 不可读影响；token 统计不可判定 ≠ RAG 无效果。
6. **陈旧报告统计量不重写**：`rag_ab_synthetic` 与 `rag_lvl25h_n40` 的报告文件早于
   统计修复，本轮只登记差值；不得把报告存量 `p` 值引用为 AP 复算值。
7. **同族未处置读取器（AQ 候选）**：`src/observability/otel_export.py:72-79` 仍把
   token 字段直接写入 OTel 属性，没有值域门；`scripts/tools/e2e_probes_workflow.py::_usage_metric`
   已自带门（不在本轮范围）。不得据本轮声称全仓 token 读端已统一。
   > 勘误（AP，2026-10-21）：AO 手册 §7.7 与登记册对应行写的
   > `experiments/otel_export.py` **路径不存在**，实际文件是
   > `src/observability/otel_export.py`；语义（同族未处置）不变。
8. **干净工件零改变不证明未来批次干净**：AP 保证的是读不动时不给数字，不是源端
   不再产生坏值；生成端（实验脚本写入）不在本轮范围。

## 8. 复算命令

```bash
# 目标集（67 collected）
.venv/bin/python -m pytest tests/test_token_usage_reports_ap.py -q

# 含受影响旧锁
.venv/bin/python -m pytest \
  tests/test_token_usage_reports_ap.py \
  tests/test_2026_09_27_review_round10.py \
  tests/test_token_usage_report_ao.py \
  tests/test_token_usage_aggregate_an.py -q

# 变异验证（逐锚点回退 → compile → 跑锁 → sha256 原字节还原）
.venv/bin/python /tmp/ap_mutation.py

# 全量 + 覆盖率（CI 同口径；不与 make gates 重叠）
make test-cov
```

`/tmp/ap_mutation.py` 是本次运行的临时脚本（不入库）；复算时以本文件第 3、5、6 节的
读数与锚点描述为准。
