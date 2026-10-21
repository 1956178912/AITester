# AO 轮：报告级 token 汇总也只认一种读数——档位、翻转对比、收敛曲线不得各算一遍（2026-10-21，零 LLM）

**范围**：`experiments/model_gradient.main`（档位 token 总量与 markdown）、
`experiments/compare_failures.build_report`（翻转任务逐行与合计）、
`experiments/analysis_parts/convergence_analysis._convergence_token_efficiency`
（收敛曲线与边际收益；渲染由 `experiments/analyze_results.py` 消费）。
生产者模块 `src/budget/token_usage` 新增**总量口径**共享读取器
`row_total_token_reading` + `aggregate_row_token_totals`。

**结论**：AN 把成本三元组、AL 把报告 §4.1、AM 把成本表、AI 把 ext 聚合口收口后，
三个**报告级总量**读端仍在各自做 Python 真值折叠：`int(usage.get("total_tokens", 0) or 0)`
（model_gradient）、`(row.get("token_usage") or {}).get("total_tokens", "?")` +
`sum(...)`（compare_failures）、`_safe_float(usage.get("total_tokens", 0) or 0)`
（convergence）。同一个坏行在三个消费点分别表现为静默 0、崩溃、负总量或 nan 曲线。
处置后：总量读数交共享函数，`total_tokens` 在场且合法即可读（旧 total-only schema
不被 in/out 缺席否定）；非对象 / 在场坏值 ⇒ `None` + 机制名，聚合任一行不可读 ⇒
不给部分和；缺席 / `null` 仍按历史 0；拆分矛盾只披露、不阻断总量。真批次
**244 文件 / 322 臂 / 10659 行** 非对象 / 坏值 / 缺 total / 拆分不符 **0 行**、
逐轮详情臂 **0**，9 臂新旧总量差 **0** ⇒ 零实例、真输出逐位不变。
**52 例新锁 + 16/16 变异锚点转红 + 1 个中性对照 0 红**。

---

## 1. 缺陷定义

改前三处消费端的行级读取（`experiments/`，均为 HEAD 原文）：

```python
# model_gradient.main（档位总量）
for d in details:
    tu = d.get("token_usage")
    if isinstance(tu, dict):
        total_tokens += int(tu.get("total_tokens", 0) or 0)

# compare_failures.build_report（逐行 + 合计）
full_tokens = (full_r.get("token_usage") or {}).get("total_tokens", "?")
full_total = sum((i["full"].get("token_usage") or {}).get("total_tokens", 0) for i in inverted)

# convergence_analysis._convergence_token_efficiency（逐轮 + 兜底总量）
usage = r.get("token_usage") or {}
per_round = usage.get("iterations")
round_tokens += _safe_float(per_round[k].get("tokens", 0) or 0)  # 有逐轮明细
round_tokens += _safe_float(usage.get("total_tokens", 0) or 0) / (k + 1)  # 旧 JSON 兜底
```

| 观测（合成行） | 改前读数 | 根因 |
|---|---|---|
| `token_usage="oops"`（model_gradient） | 整行被 `isinstance` 静默跳过 ⇒ 0 | 非对象与"无记账"同形 |
| `total_tokens=True` | 记 **1** | `int()` 收 bool |
| `total_tokens=10.7` | 记 **10**（截断） | `int()` 无值域门 |
| `total_tokens="100"` | 记 **100** | `int("100")` 收 str |
| `total_tokens=-5` | 总量 **−5** | 无负数门 |
| `total_tokens=nan` / `inf` | `ValueError` / `OverflowError`，**整个实验崩** | `int()` 无有限门 |
| 只有 `input_tokens=10, output_tokens=5` | 记 **0**（总量被忽略） | 只认 `total_tokens` |
| `token_usage="oops"`（compare_failures 逐行） | `AttributeError`，**整份报告崩** | `or {}` 只挡假值 |
| `total_tokens="100"`（合计） | `TypeError`，**求和崩** | `sum` 无类型门 |
| `total_tokens=True` / `10.7` / `-5` / `nan` / `inf`（合计） | 折进合计（1 / 10.7 / −5 / nan / inf） | 无值域门 |
| 只有 in/out 的行（逐行） | 显示 `?`、合计按 0 | 缺席与零混同 |
| `token_usage=["x"]`（convergence） | `AttributeError`，整条曲线崩 | `or {}` 只挡假值 |
| 逐轮 `tokens="100"` | `float("100")` 收下 ⇒ **100.0** | `_safe_float` 强转 |
| 逐轮 `tokens=True` | 记 **1.0** | 同上 |
| 逐轮 `tokens=-50` | 负增量被 clamp 0，但**累计量仍被拉低** | 先累加后 clamp |
| 逐轮 `tokens=nan` | nan 进入累计与边际收益 | 无非有限门 |
| `total_tokens` 缺席而 in/out 在场 | 兜底记 **0** | 只认 `total_tokens` |

要点：**同一个"总 token"事实在三个报告读端有三种命运**。AN 的共享读取器
`row_total_token_reading` 不能直接复用成本三元组读取器：成本口径要 in/out 才能
计价，三元组任一在场坏值即整行不可读；报告只展示总量时，旧 JSON 常见的
`{"total_tokens": 200}` 必须可读。若强行复用，round9 既有的 total-only 锁会转红
（本轮开发中实测发生，`KeyError: '0'`）——两种问法需要两个读取器，但**值域只有
一个**（`count_reason`）。

## 2. 处置

### 2.1 总量口径共享读取器

`src/budget/token_usage.row_total_token_reading(row)`（`src/budget/token_usage.py:358`）：

| 行形态 | `total` | 披露 |
|---|---|---|
| `token_usage` 整键缺席 / `null` | `0`（`absent=True`） | 无（历史口径） |
| 非对象 | `None` | `token_usage_not_object:<T>` |
| `total_tokens` 在场且合法 | 该值 | 无；in/out 双全且 `in+out != total` ⇒ `contradiction=True`（**不阻断**） |
| `total_tokens` 在场但 bool / float / str / 负数 / nan / inf | `None` | `token_not_count:*` / `token_negative:*` / `token_not_finite:*` |
| `total_tokens` 缺席，现存字段全 0 / 全缺 | `0` | 无（显式零行） |
| `total_tokens` 缺席，in/out 双全且合法 | `in+out` | 无（可核验） |
| `total_tokens` 缺席，其余部分和 | `None` | `token_field_absent:*` + 在场坏值机制名 |

`aggregate_row_token_totals(rows)`（`src/budget/token_usage.py:417`）：任一行
`total=None` ⇒ 聚合 `total_tokens=None`（**不给部分和**），计
`n_unreadable_rows` + `reading_reasons`；缺席行计 `n_absent_rows` 但仍是历史 0；
拆分矛盾行仍计入总量，只计 `n_contradiction_rows`。

### 2.2 三个消费端

| 消费端 | 接线 | 读不动时 | 旧 schema |
|---|---|---|---|
| `model_gradient._tier_token_metrics`（`experiments/model_gradient.py:137`） | `aggregate_row_token_totals(details)` | 档位 `total_tokens=None`；markdown 单元格「不可读」+ 披露块（`> **token 读数披露**…`） | total-only 可读；缺席历史 0 |
| `compare_failures.build_report`（`_token_cell` / `_token_total_text`，`experiments/compare_failures.py:135/154`） | 逐行 `row_total_token_reading`；合计 `aggregate_row_token_totals` | 单元格「不可读」，合计「不可读（N 行无法读取）」+ 机制行；两个合计任一不可读 ⇒ **不判**性价比倒挂 | 缺席显示 `?`，合计历史 0 |
| `_convergence_token_efficiency`（`experiments/analysis_parts/convergence_analysis.py:371`） | 预扫描：每行 `row_total_token_reading` + 逐轮 `count_reason` | `available=False`、`rounds={}`、`best_marginal_round=None`、`n_token_unreadable_rows` + `token_reading_reasons` | total-only 可读；缺席行历史 0（`available` 仍为 `True`） |

`convergence_analysis` 的逐轮扫描只覆盖**实际使用的轮次索引** `min(iterations, 3)`：
第 4 轮及以后的逐轮记录不参与曲线，也不阻断读数（不在使用面的坏值不冒充缺陷）。
`analyze_results` 的收敛章节在存在阻断基线时输出
``> - `<baseline>` Token 曲线不可读：N 行读数不可用（reasons）。``，
且不再为该基线解释"第几轮最划算"。

呈现层不再替读取层兜底：`不可读` / `?` / `0` 三种外形分别对应
"在场读不动" / "整键缺席" / "读到零"，提示语与判定同源。

## 3. 真批次证据

`experiments/results/**/benchmark_*.json` 全仓普查（只读）：

- **244 文件 / 322 臂 / 10659 行**；`token_usage` 只有 3 种形状：
  **5315** 行完整三元组、**4366** 行带缓存字段、**978** 行整键缺席。
- 非对象 / 在场坏值 / `total_tokens` 缺席而 in/out 部分为正 / 拆分不符：
  **0 行**；逐轮详情臂 **0**（convergence 走兜底路径）。
- 9 个主批臂：旧 `model_gradient` 总量与新聚合逐臂差 **0**；320 个可计算臂的
  收敛曲线全部 `available=True`、`n_token_unreadable_rows=0`。
- 受 `SHA256SUMS` 保护的归档与原始批次 JSON **一份未改写**：本轮只读复算。

## 4. 回归锁

`tests/test_token_usage_report_ao.py`：**52 例**（collected）。

| 组 | 例数 | 覆盖 |
|---|---|---|
| `TestSharedTotalReading` | 19 | total-only 可读、in/out 求和、缺席/null 历史 0、在场坏值参数化（bool/float/str/负数/nan/inf）、非对象、零行、正的部分和不可读（含**坏字段点名**补锁）、矛盾只披露、聚合部分和阻断、真批次零不可读 |
| `TestModelGradientTokenMetrics` | 6 | 干净档位不变、坏行阻断总量、披露键、markdown「不可读」与披露块、旧循环源码锁 |
| `TestCompareFailuresReport` | 8 | 干净报告不变、非对象不崩、坏值/缺席单元格、合计不可读不判倒挂、矛盾披露、机制行、旧局部求和源码锁 |
| `TestConvergenceTokenCurve` | 19 | 缺席仍可用、坏总量参数化、坏逐轮参数化（str/bool/负数/nan/非 dict/缺键）、`iterations` 非 list、未使用轮次不阻断、干净曲线不变 |

真批次组在缺工件时 `pytest.fail`，不静默 skip。

## 5. 变异验证

基线 sha256：`src/budget/token_usage.py` `63f16ba7…04776e6`、
`experiments/model_gradient.py` `32f8976f…9f8e89`、
`experiments/compare_failures.py` `131573c2…c97879`、
`experiments/analysis_parts/convergence_analysis.py` `b5684f6b…9ea480`；
目标集 collected 恒 **192**。每个锚点：替换 → `compile()` 预校验 → 写回 →
跑目标集（`-x`）→ **sha256 原字节还原**（不用 `git checkout` / `git stash`）。

| 锚点 | 回退的语义 | 结果 |
|---|---|---|
| M00 中性注释对照 | 只改一行 docstring | 绿（对照有效） |
| M01 坏 total 收下 | 删去 `total_tokens` 在场坏值的阻断 | 红 |
| M02 total-only 不可读 | 要求 in/out 同在才算可读 | 红 |
| M03 in/out 求和折 0 | 双全合法时返回 0 | 红 |
| M04 非对象折 0 | 非对象返回 `total=0` | 红 |
| M05 缺席改 None | 整键缺席返回 `total=None` | 红 |
| M06 聚合计部分和 | 不可读行仍累加并返回数字 | 红 |
| M07 矛盾不披露 | `contradiction` 恒 False | 红 |
| M08 档位阻断折 0 | `_tier_token_metrics` 把 `None` 折 0 | 红 |
| M09 呈现「N/A」 | markdown 把「不可读」改成「N/A」 | 红 |
| M10 披露块移除 | 不输出 `token 读数披露` | 红 |
| M11 单元格 `?` | compare_failures 把「不可读」改成 `?` | 红 |
| M12 compare 局部求和 | 退回旧 `sum(... or 0)` | 红 |
| M13 convergence 折 0 | 不可读行 `total=0` 且清空 reasons | 红 |
| M14 逐轮机制名丢失 | 删去逐轮 `row_reasons.append(reason)` | 红（首轮逃逸，见下） |
| M15 部分曲线 | 有不可读行仍返回 `rounds` | 红 |
| M16 不可读仍 available | `available` 恒 True | 红 |

16/16 非中性锚点转红；M00 证明测试对纯注释改动不敏感；还原后目标集
192 passed、四个文件 sha256 与基线逐字节相同。

**收口期自纠（M14 首轮逃逸）**：初版参数化把坏值直接放进 `iterations`
（如 `["100"]`），只触发"逐轮条目非 dict"分支，**没有**触发"条目是 dict 但
`tokens` 坏"的分支，M14 因此 rc=0。把参数改成 `[{"tokens": "100"}]` /
`[{"tokens": True}]` / `[{"tokens": -50}]` / `[{"tokens": float("nan")}]` /
`["oops"]` / `[{}]` 后 M14 转红。**教训：变异逃逸先怀疑测试形状，不要先怀疑
锚点无效。**

## 6. 收口读数

- 登记前一跑：`make test-cov` → **10773 passed / 1 failed / 5 skipped**，
  176.61s；唯一失败 = 基线守卫自身（BASELINE 仍写 10723，实收 collected 10779
  − 声明 10723 = 56 > 6 容差）。
- **覆盖自纠**：登记前一跑 `coverage.xml` 复算 18716/19241 行、6796/7234 弧，
  `budget/token_usage.py` 唯一未覆盖新行 = 406（`total` 缺席且在场字段坏值的
  机制名落账）——没有任何锁执行到该分支。补 1 例
  `test_bad_field_without_total_names_the_field`（52 例 = 51 + 1）后重跑。
- 刷新 `BASELINE.yaml` 后收口确认跑：**10775 passed / 5 skipped / 0 failed、
  177.09s、rc=0**；collected **10780** = passed **10775** + skipped 5 + failed 0
  （= AN 的 10723 + 52）。
- 覆盖率（`--cov=src --cov-branch`）：**18717/19241 行 = 97.2766%**、
  **6797/7234 弧 = 93.9591%**；未覆盖 **524**、缺弧 **437**、`coverage report`
  偏弧读数 **383**。
  - 分母较 AN +55 行 / +32 弧 = `row_total_token_reading` +
    `aggregate_row_token_totals`；覆盖同步 +55 / +32（新行与判定弧全部被锁执行；
    `token_usage.py` 294/295，唯一未覆盖行 175 为既有登记分支）。
  - 未覆盖行 524 与缺弧 437 与 AN 逐位相同，不作回收或退化主张。偏弧读数
    383 与缺弧是不同口径，不据此声称回收存量偏弧。
  - 十项核心模块行覆盖与三项核心路由分支覆盖按同一份 `coverage.xml` 复算
    全部不变（base_agent 98.51 / api_manager 99.24 / dataset_loader 97.28 /
    graph_nodes 99.88 / code_analyzer 99.38 / planner 99.09 / dependency 96.26 /
    multi_candidate 98.67 / cross_file 92.98 / rag_retriever 98.10；routing
    99.17 / 96.49 / 100.00）。
- **门禁实测（单独跑 `make gates`，不与其他命令重叠）**：`rc=0`，墙钟
  **180.30s**；链内 pytest（`-n 4 --dist loadfile`，**不带 `--cov`**，与本节
  带覆盖率口径的读数不可互换）**10775 passed / 5 skipped / 0 failed、175.26s**
  （collected 10780）；`ruff check` All checks passed、`ruff format --check .`
  **910 files already formatted**、mypy `Success: no issues found in 135 source
  files`；双语文档 0 警告 / 0 失败；文档链接 strict **157 份文件 / 668 条链接 /
  0 错误 / 0 警告**；env-budget 253/253 登记；`check_baseline` 结构校验与
  `check_baseline_numbers` 均通过；状态通道 134 文件通过；env-snapshot 84/84
  覆盖、缺失 0；JSON 契约 7/7；JSON strict **7273 工件 = 7271 严格 + 2 路径
  豁免 + 0 违规、300 源文件 0 写入点违规**；报告↔工件对账 [OK]（不一致 0；
  T-10 严格 29 行 / 25 可测，宽松 62 / 55）；零断言 **433 测试文件 / 0 违规**。
- 首跑门禁在本轮登记引入的 **Markdown 内嵌代码块**上失败：`ruff format --check .`
  会格式化 `.md` 里的 Python 代码块，AO 手册旧注释对齐多一空格；仅格式化该文件
  后复跑 `rc=0`。这是格式门禁的真实捕获，不是改锁迁就失败。
- 回填门禁读数后为验证末次文档改写又单独复跑一次（无并发）：`rc=0`、墙钟
  **180.90s**、链内 **10775 / 5 / 0、176.09s**、`ruff format` 910 files、mypy
  135 源文件——末态与回填读数一致（两次墙钟差 0.60s 不作性能主张）。
- 本轮 `src/` 有改动（改动面 = `src/budget/token_usage.py` +
  `experiments/model_gradient.py` + `experiments/compare_failures.py` +
  `experiments/analysis_parts/convergence_analysis.py` +
  `experiments/analyze_results.py` + 1 个新测试文件 + 文档）；覆盖率佐证的是
  `src/` 新增读取器，三个 `experiments/` 消费端不在 `--cov=src` 分母内，由其
  52 例锁与变异验证佐证。

## 7. 边界（不得引用为「报告级 token 汇总已全仓闭合」）

1. **整键缺席仍按 0**：`token_usage` 缺席 / `None` 是 AE2 历史口径；这类行
   不是"免费"，是否披露由 AK 的 `cost_caliber=recorded_lower_bound` 负责。
2. **拆分矛盾不废总量**：`total != in+out` 只披露 `n_token_split_mismatch_rows`；
   "矛盾即不可计价"由成本侧（AM）负责。
3. **total-only 可读**：报告只展示总量，`{"total_tokens": 200}` 是合法旧 schema；
   不得据此声称成本口径也可读（成本仍要走 `row_token_reading` 三元组）。
4. **收敛曲线缺席仍 `available=True`**：无 token 数据按历史 0 渲染，是本轮
   **保留**的既有语义；只有"在场读不动"才让曲线不可用。
5. **只扫描使用面**：逐轮坏值只在 `min(iterations, 3)` 以内阻断；第 4 轮及
   以后的记录不进曲线，也不在本轮判定范围。
6. **真批次干净不证明未来批次干净**：AO 保证的是读不动时不给数字，不是源端
   不再产生坏值；生成端（实验脚本写入）不在本轮范围。
7. **同族未处置读取器**（已登记、不在本轮改动面）：`experiments/otel_export.py`
   与归档 `_helpers` 提取脚本仍持有各自的宽松读取；不得据本轮声称全仓报告读端
   已统一。
8. **本轮的 `src/` 改动**：`src/budget/token_usage.py`（+`row_total_token_reading`，
   +`aggregate_row_token_totals`；+55 行 / +32 弧）；三个消费端与渲染改动都在
   `experiments/`，不在覆盖率分母内。

## 8. 复算命令

```bash
# 目标集（192 collected：AO 52 + AN / AM / round9 / round10 受影集合）
.venv/bin/python -m pytest \
  tests/test_token_usage_report_ao.py \
  tests/test_experiments_analysis.py \
  tests/test_2026_09_26_review_round9.py \
  tests/test_2026_09_27_review_round10.py \
  tests/test_token_usage_aggregate_an.py -q

# 变异验证（逐锚点回退 → compile → 跑锁 → sha256 原字节还原）
.venv/bin/python /tmp/ao_mutation.py

# 真批次普查（244 文件 / 322 臂 / 10659 行）+ 三读端合成行
.venv/bin/python /tmp/ao_probe.py

# 全量 + 覆盖率（CI 同口径；不与 make gates 重叠）
make test-cov
```

`/tmp/ao_mutation.py` / `/tmp/ao_probe.py` 是本次运行的临时脚本（不入库）；
复算时以本文件第 3、5、6 节的读数与锚点描述为准。
