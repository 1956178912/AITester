# AN 轮：token 聚合读端也只认一种读数——写盘、可信报告、旧批次兜底不得各算一遍（2026-10-21，零 LLM）

**范围**：`experiments/run_benchmark._aggregate_token_metrics`（写盘 `token_metrics`
的唯一来源）、`experiments/trusted_verification.arm_trusted_metrics`（离线可信报告 /
CLI）、`experiments/analysis_parts/rag_analysis._token_metrics_from_details`（旧版
JSON 兜底，被 `analyze_results` 消费）。行级策略迁入生产者模块
`src/budget/token_usage.row_token_reading`，新增多行聚合
`aggregate_row_token_usage`；`statistical_analysis._row_cost_tokens` 改为
`row_token_reading` 的别名（AM 既有锁零改写）。

**结论**：AI（ext 聚合口）、AL（报告 §4.1）、AM（成本表）都已按行级值域收口，
但**三处聚合读取器**仍在用 `(r.get("token_usage") or {}).get(..., 0)` 逐字段求和：
非对象真值行 `.get` 崩、`bool` 记 1、`float` 记小数、`str` 抛 `TypeError`、负数
得到负总量、`nan` 得到非有限读数；`cache_hits=-3` 编出 **−300%** 命中率；行内
`total_tokens` 与 `in+out` 矛盾时 `run_benchmark` 取 110、`trusted_verification`
取 999——同一事实两个读数；缺 `total_tokens` 的行在可信报告里直接记 0。处置后：
整键缺席 / `None` 保持 AE2 历史 0；在场读不动 ⇒ 三个总量一律 `None`（不给部分和）；
`llm_calls` 独立计数；拆分矛盾只披露、总量仍取行内真值；缓存走 `cache_totals`。
真批次 783 行 / 9 臂逐位不变，全仓 11197 行普查坏 / 部分 / 矛盾 **0 行**。
**38 例新锁 + 15/15 变异锚点转红 + 1 个中性对照 0 红**。

---

## 1. 缺陷定义

改前三处消费端的行级求和（`experiments/`）：

```python
# run_benchmark._aggregate_token_metrics
total_input = sum((r.get("token_usage") or {}).get("input_tokens", 0) for r in bl_results)
total_output = sum((r.get("token_usage") or {}).get("output_tokens", 0) for r in bl_results)
total_calls = sum((r.get("token_usage") or {}).get("llm_calls", 0) for r in bl_results)
total_cache_hits = sum((r.get("token_usage") or {}).get("cache_hits", 0) for r in bl_results)
total_cache_avoided = sum((r.get("token_usage") or {}).get("cache_avoided_tokens", 0) for r in bl_results)
...
"total_tokens": total_input + total_output,          # 行内 total_tokens 被忽略
"cache_hit_rate_pct": round(total_cache_hits / (total_cache_hits + total_calls) * 100, 2)

# trusted_verification.arm_trusted_metrics
cache_hits = sum((r.get("token_usage") or {}).get("cache_hits", 0) for r in rows)
total_tokens = sum((r.get("token_usage") or {}).get("total_tokens", 0) for r in rows)
llm_calls = sum((r.get("token_usage") or {}).get("llm_calls", 0) for r in rows)

# rag_analysis._token_metrics_from_details
total_input = sum((r.get("token_usage") or {}).get("input_tokens", 0) for r in details)
total_output = sum((r.get("token_usage") or {}).get("output_tokens", 0) for r in details)
"total_tokens": total_input + total_output,
```

| 观测（合成行） | 改前读数 | 根因 |
|---|---|---|
| `token_usage=["x"]`（真值非对象） | `AttributeError`，整臂聚合崩溃 | `or {}` 只挡假值 |
| `token_usage=[]`（假值非对象） | 静默当空对象 ⇒ 0 | 同上，假值与"无记账"混同 |
| `input_tokens=True` | 按 **1** 计入 | `sum` 不判值域 |
| `input_tokens=1.5` | 按 **1.5** 计入 | 同上 |
| `input_tokens="100"` | `TypeError` | `+=` 无类型门 |
| `input_tokens=-5` | 总量变负 | 无负数门 |
| `total_tokens=nan` | 总量 / 均值变 `nan` | 无非有限门 |
| `cache_hits=-3`、`llm_calls=0` | 命中率 **−300%** | 分母只挡 `== 0` |
| 行内 `total_tokens=999`、`in+out=110` | `run_benchmark` 记 **110**；`trusted_verification` 记 **999** | 同一事实两个读数 |
| 行内缺 `total_tokens`、in/out 均为 10 | `trusted_verification` 记 **0**（run_benchmark 记 20） | 缺席与零混同 |
| `cache_hits` 只在部分行出现 | 缺失行按 0 拼出部分和，命中率照算 | 半套 schema 无阻断 |
| `cache_hits="3"` | `TypeError`（run_benchmark）/ 部分和（rag） | 无值域门 |

要点：**同一行 token 记录在写盘、可信报告、旧批次兜底三处有三种命运**。
AI / AL / AM 已经把成本侧与报告侧的"读不动 ⇒ `None` + 机制名"定死，聚合侧却仍是
Python 真值兜底：`or 0` 把"读不动"翻译成"读到了 0"，`total_input + total_output`
把行内总量翻译成"拆分和"，`sum(...)` 把 bool / 小数 / 负数照单全收。写盘
`token_metrics` 是后续所有报告的成本输入，可信报告与 CLI 是对外读数——这里的
折零与双读数会直接进入结论，且不会在源批次里留下任何痕迹。

## 2. 处置

### 2.1 行级读数迁入生产者模块

`src/budget/token_usage.row_token_reading(row)` 承接 AM 的 `_row_cost_tokens`
语义（唯一判定）：

| 行形态 | 读数 | 说明 |
|---|---|---|
| `token_usage` 整键缺席 / `None` | `absent=True`，三元组 `(0,0,0)` | AE2 历史口径；AK 下界披露负责说明 |
| 三元组全为 0，或现存字段全为 0 | `(0,0,0)` | 显式零行，不是读不动 |
| `total_tokens` 缺席，in/out 双全且合法 | `(inp+out, inp, out)` | 总量可由拆分核验 |
| 字段在场却是 `bool` / `float` / `str` / `nan` / 负数 | `counts=None` + 机制名 | 在场坏值不折 0 |
| 任一现存字段为正、且三元组有缺项 | `counts=None` + 机制名 | 缺项不是 0，不给部分和 |
| `token_usage` 非对象 | `counts=None` + `token_usage_not_object:<T>` | 不再靠 `or {}` 静默当空 |

`statistical_analysis._row_cost_tokens = row_token_reading`（`experiments/statistical_analysis.py:1072`）：
成本表与聚合读端**同一份策略**，本文件不再持有第二份实现。AM / AL / AI 的既有
测试零改写。

### 2.2 多行聚合：三个总量共命运，`llm_calls` 独立

`src/budget/token_usage.aggregate_row_token_usage(rows)`（`src/budget/token_usage.py:429`）：

| 情形 | input / output / total | `llm_calls` | 缓存 | 披露键 |
|---|---|---|---|---|
| 全部行可读 | 求和 | 求和 | 走 `cache_totals` | 无 |
| 任一行三元组读不动 | **三者均 `None`**（不给部分和） | 仍可独立求和 | 走 `cache_totals` | `n_token_unreadable_rows` + `token_reading_reasons` |
| `llm_calls` 在场坏值 | 不受连坐 | `None` | 走 `cache_totals` | 同上（机制名同表） |
| 行内 `total ≠ in+out` | 总量仍可读（两者各自定义） | 求和 | 走 `cache_totals` | `n_token_split_mismatch_rows` + `contradiction_reasons`（码 `token_split_mismatch`） |
| 整批旧 schema 无缓存字段 | 正常 | 正常 | `present=False` ⇒ 消费端历史 0 | 无 |
| 缓存半套 schema / 坏值 / 非对象行 | 正常 | 正常 | `hits` / `avoided` 均 `None` | `cache_reading_reasons`（消费端写入） |

- **读不动是总量级阻断**：`None` 不是 0；消费端不得用 `0` 或部分和替代。
- **矛盾是披露级事实**：聚合层没有金额可废，token 总量仍可信；AM 的金额级阻断
  发生在成本侧，不在此处重复。
- **`llm_calls` 与 token 三元组是两个独立事实**：坏调用数只废调用数，不废 token；
  非对象行例外——它同时让调用数不可读（类型信息已在三元组机制码里）。
- 披露键只在真发生时写入 ⇒ 干净批次的返回域逐键不变。

### 2.3 三个消费端

| 消费端 | 接线 | 读不动时 | 旧 schema |
|---|---|---|---|
| `run_benchmark._aggregate_token_metrics` | `agg = aggregate_row_token_usage(bl_results)` | 三个总量 / 命中率 / 未缓存理论值 / 均值与占比为 `None` | 缓存按历史 0 |
| `trusted_verification.arm_trusted_metrics` | 同上 | 同上；新增返回 `"llm_calls"` | 缓存按历史 0 |
| `rag_analysis._token_metrics_from_details` | 同上，保持五键契约 | 三元组与均值为 `None` | 无缓存键（五键契约） |

`trusted_verification` 的 CLI 分母同时修复：改前打印
`（命中 {cache_hits} / 调用 {cache_hits} + 真实）`——分母是字面文本，不是数；
现在指标返回 `llm_calls`，打印 `（命中 1 / 真实调用 4）`。

## 3. 真批次证据

三份主批 JSON（`experiments/results/main_batch/benchmark_synthetic_20261006_{140906,151907,164357}.json`，
3 臂 × 87 行 = **783 行 / 9 臂**）逐行普查：所有计数字段为 int、行内
`in+out=total`、无缓存键 ⇒ AN 不触发任何阻断。

- 复算三臂 `token_metrics` 与落盘值逐键相等（每个臂 5 键）；9 臂读数与改前逐位
  相同；旧 schema 缓存 `present=False` ⇒ `total_cache_hits` / `avoided` 仍为 0，
  `cache_hit_rate_pct` 仍为 0.0。
- 全仓扫描（`experiments/results/` 全部批次 JSON）：**11197 行 / 337 臂**；
  `token_usage` 整键缺席 **1218 行**（89 臂含缺席行，仍按历史 0）、在场坏值 /
  部分三元组 / 拆分矛盾 **0 行**。
- 受 `SHA256SUMS` 保护的归档与原始批次 JSON **一份未改写**：本轮只读复算。

## 4. 回归锁

`tests/test_token_usage_aggregate_an.py`：**38 例**（collected）。

| 组 | 例数 | 覆盖 |
|---|---|---|
| `TestRowTokenReadingShared` | 6 | 别名同一性、整键缺席 / `null`、全零 / 全缺、total 缺席而 in/out 双全、在场坏值 |
| `TestAggregateRowTokenUsage` | 16 | 缺席行、非对象、坏值参数化（bool / float / str / 负数 / nan）、部分正值、零行不污染、矛盾披露、坏调用、坏缓存、半套 schema、缓存缺席、非对象缓存 |
| `TestRunBenchmarkTokenMetrics` | 7 | 干净行逐键不变、非对象不崩且总量 `None`、坏三元组只废 token、矛盾披露、坏缓存只废缓存、旧 schema 零读数、真批次 783 行 / 9 臂与落盘逐键相等 |
| `TestTrustedVerificationMetrics` | 5 | 干净行不变、非对象返回 `None`、矛盾取行内真值、坏缓存只废缓存、CLI 打印「命中 1 / 真实调用 4」 |
| `TestRagAnalysisFallback` | 4 | 干净旧 JSON 五键契约、读不动 `None` + 披露、矛盾披露但总量保留、缺席行历史 0 |

真批次组在缺工件时 `pytest.fail`，不静默 skip。

## 5. 变异验证

基线：`src/budget/token_usage.py`，
sha256 `eb05efa376841a488c2d7b16102934ef9ddf30fcf236f6b7448209623ae7de6f`；
目标集 collected 恒 **210**。每个锚点：替换 → `compile()` 预校验 → 写回 → 跑目标集
（`-x`，记录首个失败）→ **sha256 原字节还原**（不用 `git checkout` / `git stash`）
→ 断言还原后 sha256 相同。

| 锚点 | 回退的语义 | 结果 |
|---|---|---|
| M0 中性注释对照 | 只改一行注释 | 绿（对照有效） |
| M1 缺席分支 | 整键缺席返回 `counts=None` + `token_usage_absent` | 红 |
| M2 零行例外 | 全零判定放宽为 `>= 0`，部分零行被当可读 | 红 |
| M3 total 缺席对 | 删去「total 缺席而 in/out 双全可读」 | 红 |
| M4 拆分矛盾 | 删去 `in+out != total` 的披露 | 红 |
| M5 调用值域 | `count_reason` 改恒 `None`，坏 `llm_calls` 静默入账 | 红 |
| M6 非对象调用 | 删去非对象行对调用数与缓存的阻断 | 红 |
| M7 token 阻断门 | 三元组不按 `tokens_readable` 置 `None`，输出部分和 | 红 |
| M8 调用阻断门 | `llm_calls` 不按 `calls_readable` 置 `None` | 红 |
| M9 非对象缓存 | 删去 `non_object_reasons` 对缓存的合并 | 红 |
| M10 旧 schema 缓存 | `run_benchmark` 无条件取 `cache["hits"]`（旧 schema 得 `None`） | 红 |
| M11 矛盾披露键 | `run_benchmark` 不写 `n_token_split_mismatch_rows` | 红 |
| M12 命中率阻断 | 命中率不判 `None`，`None` 参与除法 | 红 |
| M13 可信报告键名 | `llm_calls` 改名为 `cache_calls`（CLI 读数错位） | 红 |
| M14 CLI 分母 | 退回「命中 + 真实」字面文本 | 红 |
| M15 旧批次均值 | 总量不可读时均值折 0 | 红 |

15/15 非中性锚点全部转红；M0 证明测试对纯注释改动不敏感。还原后目标集
210 passed，sha256 与基线逐字节相同。

## 6. 收口读数

- 登记前一跑：`make test-cov` → **10722 passed / 1 failed / 5 skipped**，
  176.35s；唯一失败 = 基线守卫自身（BASELINE 仍写 10685，实收 collected 10728
  − 声明 10685 = 43 > 6 容差）。
- 刷新 `BASELINE.yaml` 后收口确认跑：**10723 passed / 5 skipped / 0 failed、
  176.40s、rc=0**。
- collected **10728** = passed **10723** + skipped 5 + failed 0
  （= AM 的 10685 + 38）。
- 覆盖率（`--cov=src --cov-branch`）：**18662/19186 行 = 97.2688%**、
  **6765/7202 弧 = 93.9322%**；未覆盖 **524**、缺弧 **437**、`coverage report`
  偏弧读数 **383**。
  - 分母较 AM +77 行 / +38 弧 = `row_token_reading` +
    `aggregate_row_token_usage`；覆盖同步 +77 / +38（新行全部被锁执行）。
  - 未覆盖行 524 与缺弧 437 与 AM 逐位相同，不作回收或退化主张。偏弧读数
    383（AM 437）与缺弧是不同口径：一个分支可半缺↔全缺而缺弧总数不变，本轮
    **不**据此声称回收存量偏弧。
  - 十项核心模块行覆盖与三项核心路由分支覆盖按同一份 `coverage.xml` 复算
    全部不变（base_agent 98.51 / api_manager 99.24 / dataset_loader 97.28 /
    graph_nodes 99.88 / code_analyzer 99.38 / planner 99.09 / dependency 96.26 /
    multi_candidate 98.67 / cross_file 92.98 / rag_retriever 98.10；routing
    99.17 / 96.49 / 100.00）。
- 登记前一跑与确认跑覆盖率逐位相同；两次墙钟差 0.05s 不作性能主张。
- 收口期自纠：初版汇总曾把 `coverage report` 的偏弧数当作"已覆盖弧"
  （`(7202−383)/7202 = 94.68%`），与 `coverage.xml` 根节点
  `branches-covered=6765` 不符；已按根节点口径改为 **93.93%**，并在正文
  明确「偏弧 ≠ 缺弧」。同一自纠也阻止了把偏弧下降 54 写成"回收"。
- **门禁实测（单独跑 `make gates`，不与其他命令重叠）**：`rc=0`，墙钟
  **183.00s**；链内 pytest（`-n 4 --dist loadfile`，**不带 `--cov`**，与本节
  带覆盖率口径的读数不可互换）**10723 passed / 5 skipped / 0 failed、177.88s**
  （collected 10728）；`ruff check` All checks passed、`ruff format --check .`
  **908 files already formatted**、mypy `Success: no issues found in 135 source
  files`；双语文档 0 警告 / 0 失败；文档链接 strict **156 份文件 / 666 条链接 /
  0 错误 / 0 警告**；env-budget 253/253 登记；`check_baseline` 结构校验与
  `check_baseline_numbers` 均通过；状态通道 134 文件通过；env-snapshot 84/84
  覆盖、缺失 0；JSON 契约 7/7；JSON strict **7273 工件 = 7271 严格 + 2 路径
  豁免 + 0 违规、300 源文件 0 写入点违规**；报告↔工件对账 [OK]（不一致 0；
  T-10 严格 29 行 / 25 可测，宽松 62 / 55；登记册 §1 覆盖率 ±0.20pp 相符）；
  零断言 **432 测试文件 / 0 违规**。
- 首跑两例失败是**本轮登记引入的真实缺陷、被门禁当场抓获**：① 登记册 AN 行
  表格 4 格对 3 列表头（GFM 静默丢格，`test_markdown_table_integrity` 捕获）；
  ② README「最新优化」行残留「10685 passed / 0 failed」字面计数
  （`check_baseline_numbers` 捕获）；两处修复后按同一命令连跑确认 **rc=0**
  （10723 / 5 / 0、177.88s）。
- 回填门禁读数后为验证末次文档改写又复跑一次（单独跑、无并发）：**rc=0**、
  墙钟 **180.88s**、链内 **10723 / 5 / 0、175.90s**、文档链接 strict 0 错误、
  双语文档 0 警告——末态与回填读数一致。

## 7. 边界（不得引用为「token 聚合读端已全仓闭合」）

1. **整键缺席仍按 0**：`token_usage` 缺席 / `None` 是 AE2 的历史口径；这类行
   不是"免费"，是否披露由 AK 的 `cost_caliber=recorded_lower_bound` 负责。
2. **拆分矛盾不废 token 总量**：聚合层只披露 `token_split_mismatch`；若下游需要
   "矛盾即不可计价"，由成本侧（AM）负责，不在本层重复阻断。
3. **`llm_calls` 与 token 三元组独立**：坏调用数不连坐 token；非对象行是例外
   （调用数同时不可读，机制码由三元组读取器给出）。
4. **旧 schema 缓存仍按 0**：整批无缓存键 ⇒ `present=False` ⇒ 消费端历史 0；
   半套 schema / 坏值才让命中与避免为 `None`。
5. **聚合层没有金额**：AN 不判断价目、币种或 `$/task`；成本结论仍由
   AH / AM / AB 系列口径负责。
6. **真批次干净不证明未来批次干净**：AN 保证的是读不动时不给数字，不是源端
   不再产生坏值；生成端（实验脚本写入）不在本轮范围。
7. **同族未处置读取器**（已登记、不在本轮改动面）：`compare_failures.py`、
   `convergence_analysis.py`、`model_gradient.py`、`otel_export.py` 以及归档
   `_helpers` 提取脚本仍持有各自的宽松读取；不得据本轮声称全仓聚合读端已统一。
8. **`run_benchmark` 的呈现层未改**：本轮回填的是写盘 `token_metrics` 的读数；
   README / 报告如何渲染这些 `None` 不在本轮范围（无 `None` 时文本不变）。
9. **本轮的 `src/` 改动**：`src/budget/token_usage.py`（+`row_token_reading`，
   +`aggregate_row_token_usage`；+77 行 / +38 弧）；三个消费端的改动都在
   `experiments/`，不在覆盖率分母内，由其 38 例锁与变异验证佐证，不由覆盖率佐证。

## 8. 复算命令

```bash
# 目标集（210 collected：AN 38 + AM / run_benchmark / trusted / analysis 受影集合）
.venv/bin/python -m pytest \
  tests/test_token_usage_aggregate_an.py \
  tests/test_cost_aggregate_token_reading_am.py \
  tests/test_run_benchmark.py \
  tests/test_trusted_verification.py \
  tests/test_experiments_analysis.py -q

# 变异验证（逐锚点回退 → compile → 跑锁 → sha256 原字节还原）
.venv/bin/python /tmp/an_mutation.py

# 真批次 783 行 / 9 臂复算（测试内真路径组）
.venv/bin/python -m pytest tests/test_token_usage_aggregate_an.py -q -k real_main_batch

# 全量 + 覆盖率（CI 同口径；不与 make gates 重叠）
make test-cov
```

`/tmp/an_mutation.py` 是本次运行的临时脚本（不入库）；复算时以本文件第 3、5 节的
读数与锚点描述为准。
