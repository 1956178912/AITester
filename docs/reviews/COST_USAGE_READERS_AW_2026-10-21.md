# AW 轮：T1/B2 逐臂统计的 `token_metrics` 形状与事件计数（2026-10-21，零 LLM）

**范围**：`experiments/analyze_t1_b2_main_batch.py` 的 `arm_stats`——AV 收口
`add_cost` 之后，同一份载荷在进入金额门之前仍先经过这里：

- `tm = res.get("token_metrics") or {}`：真值非对象留给 `.get` 抛
  `AttributeError`，假值非对象被改写成 `{}`；
- `"calls": tm.get("total_llm_calls")`：事件计数原值直出。

**结论**：改前一个坏形状能让整批分析中止，或把"载荷坏了"悄悄变成
"没有 metrics"；`calls` 的 bool / 数字字符串 / 小数 / 负数与池化列
（走 `sum_token_metric_values` 会拒绝同一份值）在同一报告里互斥。
处置后：`token_metrics` **原样保留**交下游 `add_cost` 与池化读取器判定；
`calls` 走共享 `token_metric_reading`——缺席 / null metrics / 字段缺席按
AE2 历史 0，字段在场读不动 ⇒ `None` + `calls_reason`；事件计数与 token
金额互不连坐。**22 例新锁 + 6/6 变异锚点转红 + 0 逃逸**；真语料
324/324 读数干净，T1/B2 入库报告 **18/18** 逐位复现、原始批次新臂
**9/9** 复现，重算 `ANALYSIS_REPORT.json` **逐字节相同**（35542 字节）。
确认跑 **11126 passed / 5 skipped / 0 failed、179.21s、rc=0**。**未提交。**

---

## 1. 缺陷定义

改前活路径（AW 前原文）：

```python
def arm_stats(batch, arm):
    res = (batch.get("results") or {}).get(arm) or {}
    ...
    tm = res.get("token_metrics") or {}
    return {
        ...
        "token_metrics": tm,
        "cost_usd": None,
        "calls": tm.get("total_llm_calls"),
    }
```

四类后果：

1. **坏形状让整批分析中止**：`token_metrics="abc"` 或 `True` 是真值非对象，
   `or {}` 不生效，`tm.get` 抛 `AttributeError`；`build_report` 逐 seed 逐臂
   调用 `arm_stats`，单个坏臂终止整份报告。
2. **坏形状被改写成"没有观测"**：`[]` / `""` / `0` 是假值非对象，`or {}`
   把载荷换成空对象；下游 `add_cost` 与池化列都按"无 metrics"读成历史 0，
   真实形状（与"生产者写坏"这件事）从报告中消失。
3. **事件计数无值域**：`True` 记 true、`"12"` 记字符串、`10.0` 记小数、
   `-5` 记负数；同一份值进入池化列时被 `token_metric_reading` 拒绝
   （`None` + 机制名）——逐 seed 与池化对同一次读数给出互斥事实。
4. **缺席与不可读塌成一种**：字段缺席时逐 seed `calls=None`，池化按 AE2
   读 0；字段为 `null` 时两者都没有机制名。读者无法区分"旧 schema 没写"
   与"上游拒绝"。

## 2. 真语料测量（只读探针，改前/改后同一口径）

扫描 `experiments/results/**/*.json`（只读，不重写任何归档或原始批次）：

| 观测 | 实测 |
|---|---|
| JSON 文件 | **1701**（可解析 **1593**；108 份为历史截断/非完整 JSON，未改动） |
| `token_metrics` 对象 | **324** |
| `token_metrics` 非对象且非 null | **0** |
| 含 `total_llm_calls` 的对象 | **324 / 324** |
| `total_llm_calls` 坏值（bool/非 int/负数/非有限） | **0** |

T1/B2 批（`experiments/results/t_round_b2_main_batch_20261018`）：

| 复算 | 结果 |
|---|---|
| 入库报告逐 seed 读数 | **18 / 18**（9 新 + 9 原）`calls` 与 `token_metrics` 复现 |
| 原始批次新臂经 `arm_stats` | **9 / 9** `calls` 与 `token_metrics` 复现 |
| 重算 `build_report` 载荷 | **逐字节相同**（35542 字节） |

旧表达式与新实现的现场对照（`calls` 口径；"改前"为逐字复刻旧表达式）：

| `token_metrics` | 改前 | 改后 |
|---|---|---|
| `{"total_llm_calls": 7}` | `7` | `7`（无 `calls_reason`） |
| 键缺席 | `None` | `0`（AE2 历史 0） |
| `None` / `{}` | `None` | `0`（AE2 历史 0） |
| `{"total_llm_calls": None}` | `None`（无归因） | `None` + `token_metric_unreadable:total_llm_calls` |
| `{"total_llm_calls": true}` | `True` | `None` + `token_not_count:total_llm_calls:bool` |
| `{"total_llm_calls": "12"}` | `"12"` | `None` + `token_not_count:total_llm_calls:str` |
| `{"total_llm_calls": 10.0}` | `10.0` | `None` + `token_not_count:total_llm_calls:float` |
| `{"total_llm_calls": -5}` | `-5` | `None` + `token_negative:total_llm_calls` |
| `"abc"`（非对象） | `AttributeError` | `None` + `token_metrics_not_object:str`；载荷原样保留 |
| `[]`（假值非对象） | `None`，载荷被改成 `{}` | `None` + `token_metrics_not_object:list`；载荷仍是 `[]` |
| `True`（非对象） | `AttributeError` | `None` + `token_metrics_not_object:bool` |

口径说明：缺陷是**边界潜伏**而非存量污染——历史工件恰好都是干净对象，
所以本轮不回填历史数据；修复目标是让未来任何一次坏形状/坏计数都
**可披露、不可崩、不可改写成小一号的事实**。

## 3. 处置

### 3.1 形状：不再重写载荷

- `tm = res.get("token_metrics")`（去掉 `or {}`），`stats["token_metrics"]`
  原样返回；缺席键与显式 `null` 都得到 `None`，与 AE2 的"缺席"口径一致。
- 真值非对象由 `token_metric_reading` 给 `token_metrics_not_object:<T>`；
  假值非对象不再被换成 `{}`，池化列与 `add_cost` 看到同一份坏载荷、
  给出同一个机制名。
- 下游读取器本来就能判非对象；本轮的职责只是**不抢先改写、不中途崩溃**。

### 3.2 事件计数：`calls` 接共享计数判定

- `calls = token_metric_reading(tm, "total_llm_calls")`：
  - metrics 缺席 / `null` / `{}` / 字段缺席 ⇒ `0`（AE2 历史口径）；
  - 字段在场为 `null` 或坏值 ⇒ `None` + 机制名（bool / str / float /
    negative / non-finite 各给各的码）；
  - 可读 ⇒ 原整数。
- `calls_reason` **只在真不可读时写入**（单键，无需拼接分隔符）；
  干净路径的键集与值逐位不变。
- 事件计数与 token 金额分离：`calls` 不可读不阻断 `cost_usd`，
  token 坏值也不把可读的 `calls` 连坐。

### 3.3 为什么不是"把 calls 折成 0"

0 是"观测到零次调用"，`None` 是"这个读数读不动"。把坏值折成 0 会让
逐 seed 报告与池化列重新分叉（池化仍报 `None` + 机制），也会让
"调用次数确实为 0"与"没有观测"无法区分。AE2 只允许**缺席**折 0。

## 4. 回归锁

`tests/test_cost_usage_readers_aw.py`：13 个测试函数，参数化展开 **22 例**。

| 类 | 例数 | 覆盖 |
|---|---|---|
| `TestArmStatsCallsDomain` | 19 | 干净读数、metrics 缺席/空、字段缺席、null、bool/str/float/negative/nan/inf、四种非对象形状不崩不改写、与 `add_cost` 同源归因、事件与金额独立性 |
| `TestRealBatchCalls` | 2 | 入库报告 18/18、原始批次新臂 9/9 逐位复现 |
| `TestArmStatsSourceLock` | 1 | 源码不得再有 `or {}` 重写与裸 `tm.get("total_llm_calls")` |

受影响面只读复核：`tests/test_cost_usage_readers_av.py`、
`tests/test_experiments_scripts.py`、`tests/test_experiments_cost_rejection_ab15.py`、
`tests/test_emse_stats_report.py` 均通过（合计 223 例）。

## 5. 变异验证

6 个真实锚点；逐锚点：写入变异 → `compile()` → 跑 22 例 →
sha256 原字节还原。基线 22 passed，collected 恒 22，还原后 22 passed。

| 锚点 | 变异 | 红数 |
|---|---|---|
| M1 | 恢复 `tm = res.get("token_metrics") or {}` | 7 |
| M2 | `calls` 改回非对象保护的裸 `.get`（无值域） | 18 |
| M3 | `"calls": calls["value"] or 0`（不可读折 0） | 12 |
| M4 | 删除 `calls_reason` 写入分支（`if False`） | 13 |
| M5 | 干净路径也写 `calls_reason` | 6 |
| M6 | 非对象载荷改写成 `{}`（不崩但形状消失） | 7 |

**6/6 锚点转红，0 逃逸。** 还原后源文件与测试文件逐字节一致
（源文件 sha256 `793511e6…742d`）。

## 6. 收口读数

- 登记前一跑（带 `--cov`）：**11125 passed / 1 failed / 5 skipped、180.28s**；
  collected **11131**；唯一失败 = BASELINE 数字守卫（仍写 11104，
  实收 − 声明 = 27 > 6 容差）。
- 覆盖率（`coverage.xml` root 口径）：**19002 / 19528 行 = 97.3064%**、
  **6960 / 7396 弧 = 94.1049%**；未覆盖 **526** 行、缺弧 **436**，
  与 AV 逐位相同（本轮 `src/` 零改动，改动面在 `experiments/` + 测试 + 文档）。
- 十项核心模块：**0 项变动**（base_agent 98.53、api_manager 99.24、
  dataset_loader 97.28、graph_nodes 99.88、code_analyzer 99.38、planner
  99.09、dependency 96.26、multi_candidate 98.67、cross_file 92.98、
  rag_retriever 98.10）；核心路由三项分支逐位不变（graph_workflow 99.17、
  error_classifier 96.49、graph_state 100.00）。
- 确认跑（刷新 BASELINE 后）：**11126 passed / 5 skipped / 0 failed、
  179.21s、rc=0**（collected 11131）。
- 门禁（单独跑 `make gates`，不与其他命令重叠）：**rc=0**；链内 pytest
  **11126 passed / 5 skipped / 0 failed、179.23s**（53 warnings；collected
  11131）；`ruff format --check .` **926 files**、mypy **135** 源文件、
  文档链接 strict **165 份 / 700 条 / 0 错误 0 警告**、零断言
  **441 文件 / 0 违规**、JSON strict **7273 工件 0 违规 / 300 源文件
  0 写入点违规**、报告↔工件对账 [OK]。
- 回填门禁读数后验证跑（再次单独 `make gates`，不与其他命令重叠）：
  **rc=0**；链内 **11126 passed / 5 skipped / 0 failed、179.98s**
  （80 warnings；collected 11131）；其余读数与首跑一致（ruff format
  **926 files**、mypy **135** 源文件、文档链接 **165 份 / 700 条 /
  0 错误**、零断言 **441 文件 / 0 违规**）。

## 7. 边界（不得引用为「成本/用量口径已全仓闭合」）

1. **只覆盖 `arm_stats` 这一个入口**：仓内 shell 批跑器与归档
   `_helpers` 脚本仍可自行读 token / calls；本轮不触碰受保护工件。
2. **`calls` 是事件计数**：可读不等于 token 可计价或金额可算；
   报表必须同时看 `calls_reason` 与 `cost_unpriced_reason`。
3. **缺席仍是历史 0**（AE2）：`token_metrics` 缺席 / null / `{}` / 字段缺席
   读 0，不得读成"免费"；只有在场坏值才 `None` + 机制。
4. **非对象载荷原样保留**：下游消费者不得假设 `token_metrics` 一定是 dict，
   必须先走共享读取器；本函数只保证"不崩、不改写"。
5. **逐 seed `calls` 不是呈现字段**：README / YAML 片段不渲染它；本轮修的
   是 `ANALYSIS_REPORT.json` 载荷的事实一致性。
6. **真实语料零坏值不等于修复无价值**：18/18 与 9/9 只证明干净路径不变；
   坏形状路径由 22 例锁与 6 个变异锚点证明。
7. **未调用 `--write`**：入库报告逐字节相同，本轮未重写任何
   `SHA256SUMS` 保护的归档或原始批次 JSON。

## 8. 复算命令

```bash
# 目标锁（22 collected）
.venv/bin/python -m pytest tests/test_cost_usage_readers_aw.py -q

# 受影响面（只读复核）
.venv/bin/python -m pytest tests/test_cost_usage_readers_av.py \
  tests/test_experiments_scripts.py tests/test_experiments_cost_rejection_ab15.py \
  tests/test_emse_stats_report.py -q

# 全量 + 覆盖率（CI 同口径；不与 make gates 重叠）
make test-cov

# 确认跑（BASELINE 刷新后）
make test

# 门禁（最后单独跑，绝不与其他命令重叠）
make gates
```
