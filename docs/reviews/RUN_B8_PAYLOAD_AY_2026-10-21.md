# AY 轮：run_b8 载荷形状保留与成本拒绝路径（2026-10-21，零 LLM）

**范围**：`experiments/run_b8_injection.py` 的两处读取层——

- `_load_arm`：单臂批次 JSON 的 `token_metrics` 搬运；
- `_load_harness_smoke`：四条跑前冒烟行的 `token_metrics` 搬运与成本读数。

**结论**：两处仍用 `rd.get("token_metrics") or {}` 归一。假值非对象
（`[]` / `""` / `0` / `False`）被改写成 `{}`，`_arm_summary` 于是把
"载荷坏了"读成"没有 metrics"：成本报 **$0.0** 且无机制名，入库
`REPORT.json` 也丢失原始坏形状；冒烟行同一归一让载荷存 `{}`（成本在
改写前已算出，行内金额对、形状已丢）。处置后读取层原样搬运
`token_metrics`，金额判定只在 `_cost_usd` 一处：假值非对象同样得到
`None` + `token_metrics_not_object:<T>`，不折成历史 0；干净 dict 与
历史 0 口径不变。**27 例新锁 + 6/6 变异锚点转红 + 0 逃逸**；真批次
两臂与四行冒烟成本及载荷逐位复现。确认跑 **11201 passed / 5 skipped /
0 failed、177.62s、rc=0**。**未提交。**

---

## 1. 缺陷定义

### 1.1 单臂读取（`_load_arm`）

改前：

```python
"token_metrics": rd.get("token_metrics") or {},
```

`or {}` 把两类完全不同的输入压成同一个结果：

| 输入 | 语义 | 改前结果 |
|---|---|---|
| 键缺席 | 旧 schema 没写 | `{}`（正确，历史 0） |
| `null` | 上游显式无 metrics | `{}`（历史 0，口径可接受） |
| `[]` / `""` / `0` / `False` | **载荷坏了** | `{}`——冒充"没有 metrics" |
| `"abc"` / `True` / `[1]` | 载荷坏了 | 原值透传，`_cost_usd` 拒绝 |

假值非对象是最危险的一类：它既不是 `null`，也不是对象，却被静默
改写成"没有观测"。同一份坏载荷在 `_arm_summary` 里得到
`$0.0` 且 `cost_usd_standard_price_reasons` 缺席——读者无法区分
"这次真的没花钱"与"这次的成本读不出来"。

### 1.2 冒烟行（`_load_harness_smoke`）

改前先做成本读数、再把归一后的值写进行：

```python
tm = rd.get("token_metrics") or {}
cost, cost_reasons = _cost_usd(tm, price_in, price_out)
...
"token_metrics": tm,
```

因此冒烟行的**金额**走的是 `{}`（历史 0），而坏形状信息在写入前
已经丢失；后续任何按行复核、导出或重算都无法知道原始载荷是什么。
这不是"金额算错"，而是**证据链断裂**：`REPORT.json` 记录的事实比
输入少一层。

### 1.3 与 AW 的同一缺陷族

AW 轮收口 `analyze_t1_b2_main_batch.arm_stats` 时已确立口径：整份
`token_metrics` 原样保留，交下游 `add_cost` 与池化读取器判定；不得在
读取层用 `or {}` 改写形状。run_b8 的两处读取层是同一族在另一条
生产路径上的残留。

## 2. 真语料测量（只读探针）

扫描 `experiments/results/s_round_b8_injection_20261018/`（只读，不重写
任何归档或原始批次）：

| 观测 | 实测 |
|---|---|
| 批次内 JSON 文件 | **14** 份 |
| `benchmark_*.json` | **6** 份 |
| 递归 `token_metrics` 键（所有出现） | **12**（全部为 dict） |
| `null` / 非对象 / 坏计数 | **0** |

干净路径独立复算（`REPORT.json`，价格 0.3 / 1.2 USD/Mtok）：

| 复算 | 结果 |
|---|---|
| 两臂成本 on / off | **0.046531** / **0.060761**，逐位复现 |
| 两臂 `token_metrics` | 逐位相同（on 83246 tokens / 58 calls；off 113638 / 82） |
| 四行冒烟成本 | **0.007456 / 0.008501 / 0.007356 / 0.009719**，逐位复现 |
| 四行冒烟 `token_metrics` | 逐位相同（14395 / 16293 / 14292 / 19435 tokens） |

旧表达式与新实现的现场对照：

| 输入 | 改前 | 改后 |
|---|---|---|
| 键缺席 | `{}` → 成本 0.0 | `None` → 成本 0.0（AE2 历史 0） |
| `null` | `{}` → 成本 0.0 | `None` → 成本 0.0（AE2 历史 0） |
| `[]` / `""` / `0` / `False` | `{}` → 成本 **0.0**，无机制名 | 原值 → 成本 **None** + `token_metrics_not_object:<T>` |
| `"abc"` / `True` / `[1]` | 原值 → 成本 None + 机制名 | 同左（不变） |
| 干净 dict | 逐位透传 | 逐位透传（不变） |

口径说明：缺陷是**边界潜伏**而非存量污染——真批次 12 个键全是干净
dict，所以本轮不回填历史数据；修复目标是让未来任何一份坏形状都
**可披露、不可改写成小一号的事实**。

## 3. 处置

### 3.1 读取层只搬运，不判定

`_load_arm` 改为：

```python
"token_metrics": rd.get("token_metrics"),
```

`_load_harness_smoke` 改为先取原值、再交给同一个成本读数器：

```python
tm = rd.get("token_metrics")
cost, cost_reasons = _cost_usd(tm, price_in, price_out)
...
"token_metrics": tm,
```

两处都不再出现 `or {}`。缺席与 `null` 自然落 `None`，非对象保持原类型
与原值，干净 dict 逐位不变。

### 3.2 金额判定只留一处

`_cost_usd` 的既有口径不变：

- `None`（缺席 / `null`）→ `0.0` + 无机制名（AE2 历史 0）；
- 其他非对象（含假值非对象）→ `None` +
  `token_metrics_not_object:<T>`；
- 对象内逐字段过 `token_metric_reading`，任一不可读 ⇒ 整笔
  `None`（不给部分和）。

读取层不再做第二套判定，避免"上游已经知道坏了、下游却看不到"。

### 3.3 为什么不在读取层折 0

读取层的职责是**保真**：把工件里的事实原样交给决策层。`or {}` 看似
"给个安全默认值"，实际是把"观测到坏载荷"改写成"没有观测"——这是
在证据链最早的一环制造虚假事实。历史 0 的语义只属于缺席 / `null`，
必须由持有值域谓词的 `_cost_usd` 统一给出，不能在搬运时提前折叠。

## 4. 回归锁

`tests/test_run_b8_payload_ay.py`：5 个测试类，参数化展开 **27 例**。

| 类 | 例数 | 覆盖 |
|---|---|---|
| `TestLoadArmPreservesPayload` | 11 | 八种原值类型（含四种假值非对象）的值与类型保留、`null` 保持 `None`、键缺席保持 `None`、干净 dict 不变 |
| `TestArmSummaryCostUsesRawPayload` | 7 | 四种假值非对象 ⇒ 成本 `None` + 精确机制名；`null` / 缺席 ⇒ 历史 0 且无机制名；干净 dict ⇒ 3.0 |
| `TestHarnessSmokePreservesPayload` | 6 | 四种假值非对象在冒烟行内保留原值且成本 `None`；缺席 ⇒ `None` + 历史 0；干净 dict ⇒ 1.0 |
| `TestRealB8Corpus` | 1 | `REPORT.json` 两臂成本与载荷、四行冒烟成本与载荷逐位复现 |
| `TestSourceLocks` | 2 | `_load_arm` 函数体不得回退 `or {}`；冒烟行必须用同一个 `tm` 做成本与存储 |

受影响面只读复核：`tests/test_cost_usage_readers_au.py` 与
`tests/test_run_b8_payload_ay.py` 合并跑 **89 passed**。

## 5. 变异验证

6 个真实锚点；逐锚点：写入变异 → `compile()` → 跑 27 例 →
sha256 原字节还原。基线 27 passed，collected 恒 27，还原后 27 passed。

| 锚点 | 变异 | 红数 |
|---|---|---|
| M1-load-arm-or-empty | `_load_arm` 回退 `rd.get("token_metrics") or {}` | 13 |
| M2-smoke-local-or-empty | 冒烟读取局部 `tm` 回退 `or {}` | 6 |
| M3-cost-falsey-zero | `_cost_usd` 把假值非对象并入 `None` 历史 0 | 8 |
| M4-smoke-row-or-empty | 冒烟行存储回退 `tm or {}` | 5 |
| M5-arm-summary-or-empty | `_arm_summary` 回退 `loaded["token_metrics"] or {}` | 6 |
| M6-cost-nonobject-zero | 非对象成本读成 `0.0` 且不披露 | 8 |

**6/6 锚点转红，0 逃逸。** 还原后源文件与测试文件逐字节一致
（`run_b8_injection.py` sha256 `4e9fc8c5…c74568`）。

## 6. 收口读数

- 登记前一跑（不带 `--cov`）：**11200 passed / 1 failed / 5 skipped、
  177.62s**；collected **11206**；唯一失败 = BASELINE 数字守卫（仍写
  11174，实收 − 声明 = 32 > 6 容差）。同口径覆盖率跑
  **11200 passed / 1 failed / 5 skipped、182.50s**（同一通过数、同一守卫）。
- 覆盖率（`coverage.xml` root 口径）：**19003 / 19528 行 = 97.3116%**、
  **6961 / 7396 弧 = 94.1184%**；未覆盖 **525** 行、缺弧 **435**。
  较 AX **+1 行 / +1 弧**，落在既有 ±2 行抖动域；本轮 `src/` 零改动，
  改动面在 `experiments/` + 测试 + 文档，覆盖率分母不测 experiments。
- 十项核心模块：**0 项变动**（base_agent 98.53、api_manager 99.24、
  dataset_loader 97.28、graph_nodes 99.88、code_analyzer 99.38、planner
  99.09、dependency 96.26、multi_candidate 98.67、cross_file 92.98、
  rag_retriever 98.10）；核心路由三项分支逐位不变（graph_workflow 99.17、
  error_classifier 96.49、graph_state 100.00）。
- 确认跑（刷新 BASELINE 后）：**11201 passed / 5 skipped / 0 failed、
  177.62s、rc=0**（collected 11206）。
- 门禁（单独跑 `make gates`，不与其他命令重叠）：**rc=0**；墙钟
  **183.82s**；链内 pytest **11201 passed / 5 skipped / 0 failed、
  178.67s**（42 warnings；collected 11206）；`ruff check` All checks
  passed、`ruff format --check .` **930 files**、mypy **135** 源文件、
  双语文档 0 警告 / 0 失败、文档链接 strict **167 份 / 706 条 / 0 错误
  0 警告**、env-budget 253/253、状态通道 134 文件、env-snapshot 84/84、
  tool-versions OK、JSON 契约 7/7、JSON strict **7273 工件 0 违规 /
  300 源文件 0 写入点违规**、报告↔工件对账 [OK]、零断言 **443 文件 /
  0 违规**。
- 回填门禁读数后验证跑（再次单独 `make gates`，不与其他命令重叠）：
  **rc=0**、墙钟 **185.01s**、链内 **11201 passed / 5 skipped / 0 failed、
  179.87s**（39 warnings；collected 11206）；其余门禁读数与首跑一致
  （ruff format 930 files、mypy 135 源文件、文档链接 167 份 / 706 条 /
  0 错误、env-budget 253/253、状态通道 134、env-snapshot 84/84、
  JSON 契约 7/7、JSON strict 7273 工件 0 违规、报告↔工件对账 [OK]、
  零断言 443 测试文件 / 0 违规）。

## 7. 边界（不得引用为「run_b8 载荷已在所有面保真」）

1. **只覆盖两处读取层**：批次内其它字段（`details` / `provenance` /
   注入记录）仍按各自既有口径读取；本轮不扩张成"工件读取全面保真"。
2. **只覆盖 run_b8**：仓内其他脚本、shell 批跑器与归档 `_helpers` 仍可
   自行读取 `token_metrics`；本轮不触碰受保护工件。
3. **历史 0 只限缺席 / `null`**：假值非对象、真值非对象与坏计数一律
   `None` + 机制名；读者不得把 `None` 当成 0 或免费。
4. **读取层不判定值域**：`_load_arm` 保留原值后，若未来有消费者绕过
   `_cost_usd` 直接读字段，仍可能自行宽松处理；本轮的保证止于
   `token_metrics` 的形状不被改写。
5. **真实语料零坏值不等于修复无价值**：12 个键零坏值与两臂四行逐位
   复现只证明干净路径不变；坏形状路径由 27 例锁与 6 个变异锚点证明。
6. **未调用 `--write`**：入库报告与原始批次零改动，本轮未重写任何
   `SHA256SUMS` 保护的归档或原始批次 JSON。

## 8. 复算命令

```bash
# 目标锁（27 collected）
.venv/bin/python -m pytest tests/test_run_b8_payload_ay.py -q

# 受影响面（只读复核）
.venv/bin/python -m pytest tests/test_cost_usage_readers_au.py \
  tests/test_run_b8_payload_ay.py -q

# 全量 + 覆盖率（CI 同口径；不与 make gates 重叠）
make test-cov

# 确认跑（BASELINE 刷新后）
make test

# 门禁（最后单独跑，绝不与其他命令重叠）
make gates
```
