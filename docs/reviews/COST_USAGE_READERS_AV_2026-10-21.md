# AV 轮：T1/B2 分析侧成本入口的值域与未知金额形状（2026-10-21，零 LLM）

**范围**：`experiments/analyze_t1_b2_main_batch.py` 的两处活路径——

- `add_cost`：T1/B2 主批逐 seed 成本（真实批次 18 个读数：9 新 + 9 原）；
- `render_baseline_fragment` / `render_readme`：把分析载荷落成 BASELINE 片段与
  分析 README 时的 token / 金额呈现。

AU 轮收口了实验侧三个聚合器（`estimate_cost_usd` / `generation_summary` /
`run_b8._cost_usd`），但这个分析脚本仍自持一套 token 折叠：`add_cost` 用
`stats.get("token_metrics") or {}` + `tm.get(...) or 0` 直接计价；片段渲染把
`None` 印成 YAML 字符串 `None`。本轮把这两处接回共享值域与 YAML 标量形状。

**结论**：改前 `add_cost` 把上游 `token_metrics` 的 `None`（AN 的拒绝）折成 0，
单侧未知变成部分和；`True` 当 1、小数进金额、负数编出负成本、`nan` / `inf`
进入报告、字符串让整次分析抛 `TypeError`、非对象在 `.get` 上抛
`AttributeError`。片段渲染把未知金额写成 `cost_usd: None` / `actual_est_usd:
None`（YAML 里是**字符串**），未知 token 写成 `tokens: None`。处置后：
两个 token 字段过共享 `token_metric_reading`——整份 `token_metrics` 缺席 /
`null` / 空对象仍按历史 0（AE2 口径不变），字段**在场**却读不动 ⇒
`cost_usd=None` + `cost_unpriced_reason`（机制名去重后以 `|` 拼接），不给
部分和；YAML 未知金额一律落 `null`（`_yaml_scalar`），未知 token 落
`不可读`（`_tokens_text`）。**19 例新锁 + 6/6 变异锚点转红 + 0 逃逸**；
真实批次 **18/18** 逐 seed 成本只读复算逐位一致，入库
`BASELINE_FRAGMENT.yaml` 与当前渲染逐字节相同；确认跑
**11104 passed / 5 skipped / 0 failed、181.21s、rc=0**。**未提交。**

---

## 1. 缺陷定义

改前活路径（AV 前原文，`experiments/analyze_t1_b2_main_batch.py`）：

```text
# add_cost
tm = stats.get("token_metrics") or {}
tin = tm.get("total_input_tokens") or 0
tout = tm.get("total_output_tokens") or 0
stats["cost_usd"] = round((tin * p_in + tout * p_out) / 1e6, 6)

# render_baseline_fragment（逐臂行与批次 cost 行）
tokens: {(p.get('tokens') or {}).get('total')}, cost_usd: {p.get('cost_usd')}
cost: {{actual_est_usd: {c.get('actual_est_usd')}, total_tokens: {c.get('total_tokens')},
        preflight_estimate_usd: {c.get('preflight_estimate_usd')}, ...}}
```

五类后果：

1. **未知被读成零**：上游 `token_metrics` 的 `None` 经 `or {}` 变成空对象、
   再经 `or 0` 变成 0；报告读起来像"算过且为零"。
2. **部分和冒充全额**：输入侧未知、输出侧可读时仍按输出侧计价——旧表达式
   在 `input=None, output=200` 下给出 `0.00024`。
3. **坏值被改写成合法数**：`True` 记 1、小数直接相乘、负数编出负金额、
   `nan` / `inf` 产出非有限金额；字符串让整次分析抛 `TypeError`。
4. **硬失败**：`token_metrics` 为非对象真值（如 `"abc"`）时 `.get` 抛
   `AttributeError`，整份报告无法生成。
5. **YAML 形状错误**：未知金额印成 `None`，`yaml.safe_load` 读回的是字符串
   `"None"` 而不是 `null`；未知 token 同样印成 `None`，下游无法区分
   "未知"与"真的有个叫 None 的字符串值"。

## 2. 真语料测量（只读探针，改前/改后同一口径）

只读扫描 `experiments/results/t_round_b2_main_batch_20261018/`（受 `SHA256SUMS`
保护，本轮不重写）：

| 观测 | 实测 |
|---|---|
| `ANALYSIS_REPORT.json` 逐 seed 成本条目 | **18**（9 新 + 9 原） |
| 用新 `add_cost` 只读复算 | **18/18 与已落盘 `cost_usd` 逐位相同** |
| 入库 `BASELINE_FRAGMENT.yaml` vs 当前渲染 | **逐字节相同** |
| 真实批次坏 `token_metrics` / 写拒绝标记 | **0**（干净路径） |

旧表达式与新实现的现场对照（价目 `input $0.3/Mtok`、`output $1.2/Mtok`；
旧值为逐字复刻改前表达式所得）：

| `token_metrics` | 改前 | 改后 |
|---|---|---|
| `{in:12, out:34}` | `4.4e-05` | `4.4e-05` |
| 整键缺席 / `null` / `{}` | `0.0` | `0.0`（历史 0，无原因键） |
| `{in:null, out:200}` | `0.00024`（只计输出侧） | `None` + `token_metric_unreadable:total_input_tokens` |
| `{in:true, out:200}` | `0.00024`（bool 当 1） | `None` + `token_not_count:total_input_tokens:bool` |
| `{in:"12", out:200}` | 抛 `TypeError` | `None` + `token_not_count:total_input_tokens:str` |
| `{in:1.5, out:200}` | 小数金额 | `None` + `token_not_count:total_input_tokens:float` |
| `{in:-5, out:200}` | 负金额 | `None` + `token_negative:total_input_tokens` |
| `{in:nan, out:200}` | `nan` | `None` + `token_not_finite:total_input_tokens` |
| `{in:5, out:inf}` | `inf` | `None` + `token_not_finite:total_output_tokens` |
| `"abc"` | 抛 `AttributeError` | `None` + `token_metrics_not_object:str` |

口径说明：缺陷是**边界潜伏**而非存量污染——真实批次恰好干净，因此本轮不
回填历史数据；修复目标是让未来任何坏读数**可披露、不可读成小一号的和**。

## 3. 处置

### 3.1 `add_cost`：两个 token 字段共用一个值域门

- 逐字段调 `token_metric_reading(stats.get("token_metrics"), key)`：
  整份 metrics 缺席 / `null` / 非对象时，读取器返回历史 0（AE2）；
  字段在场却读不动（`null` / bool / 字符串 / 小数 / 负数 / 非有限 /
  非对象）时 `value=None` 并带机制名。
- 任一字段 `value is None` ⇒ 不计算金额，机制名按字段顺序去重后以 `|`
  拼接写入 `cost_unpriced_reason`；价目拒绝仍优先（沿用既有分支）。
- 两个字段都可读 ⇒ 沿用原公式与原 `round(..., 6)`，干净读数逐位不变。

### 3.2 片段与 README：未知不再是数字形状

- 新增 `_yaml_scalar(value)`：`None` → `null`，其余 → `str(value)`；
  `render_baseline_fragment` 的逐臂 `cost_usd` 与批次 `actual_est_usd` /
  `preflight_estimate_usd` / `amended_estimate_usd` / `budget_usd` 全部改走它。
- token 总量改走 `_tokens_text`：`None` → `不可读`；片段逐臂 `tokens`、
  批次 `total_tokens` 与 `render_readme` 的 `tokens=` 同口径。
- 干净载荷的片段逐字节不变（真实入库片段与当前渲染相同）。

### 3.3 不变的部分

- 整份 `token_metrics` 缺席 / `null` / `{}` 仍按历史 0 计价——这是 AE2 与
  上游 AN 的既定口径，"没有 metrics"与"metrics 在场但读不动"是两种事实。
- 价目判定顺序不变：表级 `price_reason` 优先于条目级 `entry_block_reason`，
  两者都通过后才看 token。
- 金额舍入与公式不变；受保护工件不重写。

## 4. 回归锁

`tests/test_cost_usage_readers_av.py`：19 例。

| 类 | 例数 | 覆盖 |
|---|---|---|
| `TestAddCostTokenDomain` | 15 | 干净计价；整键缺席 / `null` / `{}` 历史 0；两侧 `null`；bool / str / float / 负数 / nan / inf 六类坏值；非对象一次点名；两侧同坏按字段顺序拼接；`arm_stats` 集成 |
| `TestBaselineFragmentMoneyShapes` | 4 | 五处金额 `null` 且无 `None` 字面量；`yaml.safe_load` 读回 `None`；真实片段逐字节相同；18/18 逐 seed 复算 |

受影响面只读复核：`tests/test_experiments_cost_rejection_ab15.py`、
`tests/test_cost_usage_readers_au.py`、`tests/test_emse_stats_report.py` 等
既有锁均通过。

## 5. 变异验证

6 个真实锚点；逐锚点：写入变异 → `compile()` → 跑 19 例 →
sha256 原字节还原。基线 19 passed，collected 恒 19，还原后 19 passed。

| 锚点 | 变异 | 红数 |
|---|---|---|
| M1 | 删除 `add_cost` 的 token 值域门（坏值直接进金额） | 11 |
| M2 | 回到 `tm.get(...) or 0` 折数 | 11 |
| M3 | 机制名不去重（两侧同坏时重复拼接） | 1 |
| M4 | `_yaml_scalar` 退回 `str(value)` | 2 |
| M5 | 逐臂 `cost_usd` 渲染退回原样 | 2 |
| M6 | 批次金额渲染退回原样 | 2 |

**6/6 锚点转红，0 逃逸。** 还原后源文件与测试文件逐字节一致（sha256）。

## 6. 收口读数

- 登记前一跑（带 `--cov`）：**11103 passed / 1 failed / 5 skipped、180.43s**；
  collected **11109**；唯一失败 = BASELINE 数字守卫（仍写 11085，
  实收 − 声明 = 24 > 6 容差）。
- 覆盖率（`coverage.xml` root 口径）：**19002 / 19528 行 = 97.3064%**、
  **6960 / 7396 弧 = 94.1049%**；未覆盖 **526** 行、缺弧 **436**，与 AU
  逐位相同（本轮 `src/` 零改动，改动面在 `experiments/` + 测试 + 文档）。
- 十项核心模块：**0 项变动**（base_agent 98.53、api_manager 99.24、
  dataset_loader 97.28、graph_nodes 99.88、code_analyzer 99.38、planner
  99.09、dependency 96.26、multi_candidate 98.67、cross_file 92.98、
  rag_retriever 98.10）；核心路由三项逐位不变（graph_workflow 99.17、
  error_classifier 96.49、graph_state 100.00）。
- 确认跑（刷新 BASELINE 后）：**11104 passed / 5 skipped / 0 failed、
  181.21s、rc=0**（collected 11109）。
- 门禁（首跑即含文档表格丢格失败后修正重跑；单独跑 `make gates`，不与其他命令重叠）：
  **`rc=0`、墙钟 182.98s**；链内 pytest（`-n 4 --dist loadfile`，不带 `--cov`）
  **11104 passed / 5 skipped / 0 failed、177.95s**（31 warnings；collected 11109）；
  ruff check 通过、ruff format **924 files**、mypy 135 源文件 0 错；双语文档 0 警告；
  文档链接 strict **164 份文件 / 696 条链接 / 0 错误**；env-budget 253/253；
  状态通道 134 文件；env-snapshot 84/84；JSON 契约 7/7；JSON strict 7273 工件
  0 违规；报告↔工件对账 [OK]；零断言 **440 测试文件 / 0 违规**。
- 首跑门禁转红一处（GFM 表格丢格）：新增的 INDEX/登记册表格行在行内代码里带裸
  竖线，渲染器会把尾格丢掉；改为「以竖线拼接」措辞并去掉登记册边界的多余第 4 格后，
  `tests/test_markdown_table_integrity.py` 29 passed，重跑全链转绿。
- 回填门禁读数后验证跑（再次单独 `make gates`，不与其他命令重叠）：**rc=0、墙钟 183.47s**；
  链内 pytest **11104 passed / 5 skipped / 0 failed、178.43s**（30 warnings；collected 11109）；
  其余门禁读数与首跑一致（ruff format 924 文件、mypy 135、文档链接 164/696/0、
  env-budget 253/253、状态通道 134、env-snapshot 84/84、JSON 契约 7/7、
  JSON strict 7273 工件 0 违规、报告↔工件对账 [OK]、零断言 440/0）。

## 7. 边界（不得引用为「成本/用量口径已全仓闭合」）

1. **只覆盖这个分析脚本的两处路径**：仓内 shell 批跑器
   （`run_docstring_anchor_batch.sh`、`run_oracle_validation_batch.sh`、
   `run_augment_batch.sh`、`run_s1_decision.sh`、`run_q_examples_ab.sh`、
   `run_r1_repro.sh`、`run_b8_ablation.sh`）仍各自用 shell / heredoc 的
   `or 0` 汇总 token；它们无测试面、输出受保护，本轮不改。
2. **`arm_stats` 的 `calls` 仍是原值**：`tm.get("total_llm_calls")` 未过值域，
   因为它是逐 seed 的原始负载字段，改动会影响载荷形状；本轮只收口
   `add_cost` 与金额呈现。
3. **整份 metrics 缺席仍是历史 0**：这是 AE2 的口径，不是"成本为零"的
   结论；下游不得把 0 读成"无花费证据"或"免费"。
4. **`cost_unpriced_reason` 是多机制拼接**：两侧同坏时以 `|` 连接；
   消费者应拆分读取，不得把它当单一机制名。
5. **YAML `null` 是机器形状**：人类可读文本用「不可读 / 无法估算（机制）」，
   下游应读 `None` 与原因映射，不应解析中文短语。
6. **真实语料干净不等于修复无价值**：18/18 与逐字节相同只证明干净路径
   不变；坏值路径由 19 例锁与 6 个变异锚点证明。
7. **未调用 `--write`**：本轮只读复算与渲染函数对照，没有重写任何
   `SHA256SUMS` 保护的归档或原始批次 JSON。

## 8. 复算命令

```bash
# 目标锁（19 collected）
.venv/bin/python -m pytest tests/test_cost_usage_readers_av.py -q

# 受影响面（只读复核）
.venv/bin/python -m pytest tests/test_experiments_cost_rejection_ab15.py \
  tests/test_cost_usage_readers_au.py tests/test_emse_stats_report.py -q

# 全量 + 覆盖率（CI 同口径；不与 make gates 重叠）
make test-cov

# 门禁（最后单独跑，绝不与其他命令重叠）
make gates
```
