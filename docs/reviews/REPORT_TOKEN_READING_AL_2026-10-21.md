# AL 轮：报告侧逐行 token 算术也有值域——一行读不动不是零（2026-10-21，零 LLM）

**范围**：`experiments/emse_stats_report.py` 的 `cost_effectiveness_block`（§4.1
成本-效果块的唯一数据源）及其 §4.1 呈现；共享读取器从
`experiments/emse_stats_extensions.py` 迁入 `src/budget/token_usage.py`（ext 保留
别名，AI 既有锁零改动）。

**结论**：同一行 token 记录在 ext（AI 值域）读不动、在报告 §4.1 却被
`usage.get("input_tokens") or 0` 折成 0 并计价；`token_usage` 缺席或非对象的行在
**检出计数之前**被 `continue`，检出分母随记账好坏缩水；正 token 行缺
`by_model` 归因、`in + out != total`、`Σby_model != total` 时金额静默漏行或按
矛盾数字计价；缓存命中解释的零消耗还被计入 AK 下界。处置后：三元组读不动 ⇒
token 总量、总 $ 与两个比值一律 `None`（不给部分和）；拆分 / 归因不一致 ⇒
**只废金额**（token 总量与 `tokens/detection` 仍可读）；检出数只由
`detection_rate` 决定；缓存证据零行不进 AK 下界。真批次 783 行全部干净 ⇒ 三臂
读数逐位不变。**57 例新锁 + 6/6 变异锚点转红**。

---

## 1. 缺陷定义

改前 `cost_effectiveness_block` 自持第二套行级算术（与 AI 已收口的 ext 读取器
并存）：

```python
for r in rows:
    usage = r.get("token_usage")
    if not isinstance(usage, dict):
        continue  # ① 在检出计数之前就跳过
    tt = usage.get("total_tokens")
    if isinstance(tt, (int, float)) and not isinstance(tt, bool) and tt > 0:
        total_tokens += float(tt)  # ② 缺席/0/负数/字符串/坏值静默当 0
    det = r.get("detection_rate")  # ③ 检出计数在 ① 之后
    ...
    it = usage.get("input_tokens") or 0  # ④ 坏拆分折成 0
    ot = usage.get("output_tokens") or 0
    total_usd += (float(it) * ... + float(ot) * ...) / 1_000_000.0
```

| 观测（合成行 / 真批次普查） | 改前读数 | 根因 |
|---|---|---|
| `token_usage` 缺席 / `null` / 非对象、`detection_rate=1.0` | 该行完全不进 `n_detections` / `n_detection_measurable` | ① 跳过发生在检出计数之前——**检出分母随 token 可读性缩水** |
| `total_tokens=None` / `"abc"` / `-5` / `nan` / `inf` | `total_tokens` 字面 0 或漏行，仍渲染为可读总数 | ② 只有 `>0` 的有限数字被累加，坏值无声消失 |
| `input_tokens=1, output_tokens=2, total_tokens=99` | 按 `1/2` 计价，拆分矛盾不披露 | ④ 无拆分一致性检查 |
| 正 token、`by_model` 缺席 / 空 / 非对象 | 静默 `continue`，金额漏行且无机制名 | 金额归因只认"单键 dict"，其余无声跳过 |
| `by_model={"m": 5}`、`total_tokens=99` | 按 5 计价，`Σby_model` 与 total 不符不披露 | 无归因闭合检查 |
| 显式零三元组 + 合法缓存证据（`cache_hits` / `cache_avoided_tokens`） | 被计入 AK `n_zero_token_rows` | 缓存零行与"无记账零行"混读（违反 AK 边界⑥） |

要点：**报告侧的行级算术必须与生产侧同一值域**。ext 早已按 AI 收口（任一项
读不动 ⇒ `None` + 机制名），报告却用 `or 0` 再算一遍——同一行在两个消费点给出
两种读数，且报告这一份更宽松。检出数不应依赖 token 是否可读：检出是
`detection_rate` 的事实，token 是花费的事实。

## 2. 处置

### 2.1 共享读取器迁入生产模块

`row_token_counts` 自 `experiments/emse_stats_extensions.py` 迁入
`src/budget/token_usage.py`：

```python
def row_token_counts(row):
    if "token_usage" not in row:
        return None, ["token_usage_absent"]
    usage = row["token_usage"]
    if not isinstance(usage, dict):
        return None, [f"token_usage_not_object:{type(usage).__name__}"]
    ...
    if reasons:
        return None, reasons
    total, inp, out = counts
    return (total, inp, out), []
```

ext 保留既有别名（`_row_token_counts = row_token_counts`、
`token_count_reason = count_reason`），AI 的 63 例锁与既有调用零改动。报告不再
自持字段名/值域/缺席判定，只消费 `(counts, reasons)` 二元组。

### 2.2 报告读取与两级阻断

| 情形 | token 总量 | 总 $ | `tokens/detection` | `$/detection` | 披露键 |
|---|---|---|---|---|---|
| 任一行三元组读不动 | `None` | `None` | `None` | `None` | `n_token_unreadable_rows` + `token_reading_reasons` |
| `in+out != total` | 可读（该行 total 仍累加） | `None` | 可读 | `None` | `n_token_money_blocked_rows` + `token_money_reasons` |
| 正 token 但 `by_model` 缺席/空/非对象 | 可读 | `None` | 可读 | `None` | 同上（码：`token_field_absent:by_model` / `by_model_not_object:<T>` / `by_model_empty`） |
| `by_model` 键非字符串 / 值域坏 / 合计不符 | 可读 | `None` | 可读 | `None` | 同上（码：`by_model_key_not_str:<T>` / `token_not_count:<field>:<T>` 等 / `by_model_sum_mismatch`） |
| 多模型行且合计闭合 | 可读 | 只丢该行 | 可读 | 只丢该行 | 既有 `n_unpriceable_reasons: multi_model_row` |
| 单模型未登记 / 条目坏 | 可读 | 只丢该行 | 可读 | 只丢该行 | 既有 `n_unpriceable_reasons` |

- **读不动是总量级阻断**：不给部分和（改前 `or 0` 的 0 会被当成"读到了 0"）；
- **矛盾是金额级阻断**：token 总量仍可信，金额没有可信的输入口径；
- 零 token 行无需 `by_model` 归因（`total=0` 时跳过归因检查）——既有显式零行
  读数不变；
- `n_rows_with_tokens_positive` 仍是 `n_priced + n_unpriceable`，与 AJ 口径一致。

### 2.3 检出分母解耦

检出计数移到 `row_token_counts` 之前，只读 `detection_rate`：

```python
det = r.get("detection_rate")
if det is not None:
    n_detect_measurable += 1
    if det == 1.0:
        n_detections += 1
counts, row_reasons = row_token_counts(r)
```

读不动的行仍进检出分母；`detection_rate=None` 仍不进可测分母。

### 2.4 缓存零行排除

```python
if total == 0 and inp == 0 and out == 0 and not cache_caliber(usage)["evidence"]:
    n_zero_token_rows += 1
    if isinstance(r.get("generated_test"), str) and r["generated_test"].strip():
        n_zero_token_output_rows += 1
```

合法且正向的缓存证据（AJ 口径）解释的真实零消耗不是记账缺口，不计入 AK 下界；
缓存字段存在但无效（坏值 / 零命中）仍是零记账行。

### 2.5 §4.1 呈现

- 不可读 / 被阻断的读数由 `_f(None, nd)` 渲染为 `—`（不额外造 token）；
- 新增 AL 披露块，仅在至少一臂有 `n_token_unreadable_rows` 或
  `n_token_money_blocked_rows` 时出现：逐臂点名"N 行 token 不可读（codes）/
  M 行金额被阻断（codes）"，并声明读不动 ⇒ 总量与两个比值一律 `—`（不给部分和）、
  矛盾 ⇒ token 总量仍可读而金额记 `—`、检出数只由 `detection_rate` 决定；
- 干净臂与纯缓存零行臂不新增任何行（逐行不变）。

### 2.6 返回域

- 读不动：`total_tokens` / `total_usd` / `usd_per_detection` /
  `tokens_per_detection` 为 `None`；
- 金额阻断：`total_usd` / `usd_per_detection` 为 `None`，token 两项保留；
- 新披露键只在真发生对应情形时写入（`n_token_unreadable_rows` /
  `token_reading_reasons` / `n_token_money_blocked_rows` / `token_money_reasons`）；
- 真批次三臂不写任何 AL 键，返回域与改前逐键相同。

## 3. 真批次证据

主批三文件合并（`experiments/results/main_batch/benchmark_synthetic_20261006_*.json`，
3 × 261 = 783 行）：

| 臂 | 行数 | `n_priced_rows` | `total_usd` | AL 披露键 |
|---|---|---|---|---|
| `aitester` | 261 | 261 | 6.755979 | 无 |
| `plain_llm` | 261 | 261 | 0.876692 | 无 |
| `plain_llm_df` | 261 | 226 | 1.185783 | 无（35 行显式零由 AK `n_zero_token_rows` 披露） |

普查结论（前置测量，锁内 `TestRealBatchReadings` 复算）：

- 783 行 token 三元组全部为 int，逐行 `input + output == total_tokens`；
- 单模型行的 `Σby_model == total_tokens`；坏拆分 0 行、坏归因 0 行；
- 主批次无缓存字段（AJ 已登记）；35 行显式零全部带非空 `generated_test`；
- 因此本轮修复对真批次是**潜在缺陷收口**：读数为 0 行改变，受保护工件不重写。

## 4. 回归锁

新增 `tests/test_report_token_reading_al.py` **57 例**：

| 组 | 例数 | 覆盖 |
|---|---|---|
| `TestUnreadableTriple` | 16 | 六类机制码参数化（缺席 / 非对象 / 字段缺席 / 类型 / 非有限 / 负数）；多字段同时坏逐一命名不塌缩；`token_usage` 缺席不是零；单坏行污染总量但不影响已计价行；全可读时不写披露键 |
| `TestDetectionDenominator` | 4 | 无 `token_usage` 行仍进检出分母；坏 token 值不缩分母；`detection_rate=None` 仍不进可测分母；非对象 `token_usage` 行不是"免费跳过" |
| `TestMoneyBlocked` | 18 | 拆分矛盾 / `by_model` 缺席 / 非对象 / 空 / 键非字符串 / 合计不符参数化；token 保留而金额撤下；阻断行不产生部分和；多模型闭合行是 unpriceable 而非 block；未登记模型保持 unpriceable；priced / blocked 计数分离；归因一致时不写键 |
| `TestZeroRowCaliber` | 5 | 显式零行计入并零成本；合法缓存零行不算下界；缓存字段存在但零命中仍是零行；坏缓存值不是正向证据；零行子集只认非空 `generated_test` |
| `TestCleanBatchDomain` | 3 | 干净行读数为精确值；干净返回域为旧键集；显式零行保持旧零读数 |
| `TestRealBatchReadings` | 5 | 三臂无 AL 键；三臂总金额逐位不变；检出分母可由 rows 复算；token 总量可由 rows 复算；35 行显式零全部有产出 |
| `TestRendering` | 6 | 不可读渲染 `—` 不是 0；AL 块点名机制与解耦；金额阻断披露且 token 仍显示；干净臂无 AL 行；缓存零行臂无 AL 行；表格行格数不破 |

ext 侧零改写：`_row_token_counts` / `token_count_reason` 别名保持既有 AI 锁
（63 例）与 AJ 锁（68 例）逐字通过。

## 5. 变异验证

目标文件 `experiments/emse_stats_report.py` + `src/budget/token_usage.py`，
基线 sha256 记录后逐锚点回退，写盘前 `compile()` 预校验，还原后断言原字节，
collected 恒 **57**。

| 锚点 | 回退内容 | 转红例数 |
|---|---|---|
| M1 | 检出计数退回 token 可读性之后（读不动的行不进检出分母） | 3 |
| M2 | 删掉缓存证据零行排除（缓存零行重新计入 AK 下界） | 1 |
| M3 | 读不动时把总量/金额退回 0（恢复 `or 0` 语义） | 15 |
| M4 | 金额阻断不再置 `money_readable=False`（阻断后仍给部分和） | 14 |
| M5 | 跳过 `by_model` 归因校验（坏键 / 坏值 / 合计不符放行） | 8 |
| M6 | 去掉拆分与总量一致性检查（矛盾拆分继续计价） | 2 |

**6/6 行为锚点转红，无幸存者**；中性注释对照 0 红；每次还原后 sha256 与基线
逐字节相同（`7de980bdf58c03c6…`），restored 跑 57 passed。

## 6. 收口读数

- 登记前一跑（`make test-cov`，xdist -n 4 loadfile + `--cov`）：
  **10620 passed / 1 failed / 5 skipped**，collected **10626**，176.08s。
  唯一失败 = 基线守卫自身（BASELINE 尚未刷新；实收 10626 − 声明 10564 = 62 > 6 容差）。
- 净增 **57 例**（collected 10569 → 10626）。
- 收口确认跑（同一命令，BASELINE 刷新后）：
  **10621 passed / 5 skipped / 0 failed**，collected **10626**，**175.84s**，rc=0。
  较登记前一跑多的 1 例 = 基线守卫由红转绿，不是新用例。
- 覆盖率（同一份 `coverage.xml`，取确认跑）：行 **18575/19099 = 97.2564%**、
  分支 **6719/7156 = 93.8932%**。分母较 AK +22 行 / +12 弧，来自
  `row_token_counts` 迁入 `src/`（该文件 152/153 行，唯一未覆盖行 175 为既有
  `attach_usage` 分支）；覆盖 +21 行 / +11 弧，未覆盖行 **524**（AK 523）、
  偏弧 **437**（AK 436），落在已登记 ±2 行 / ±1 弧抖动域内——不作"回收/退化"主张；
  10 项核心模块行覆盖与三项核心路由分支覆盖按同一份 `coverage.xml` 逐项复算全部不变。
- 本轮 `src/` 有改动（改动面 = `src/budget/token_usage.py` +
  `experiments/emse_stats_report.py` + `experiments/emse_stats_extensions.py` +
  `tests/test_report_token_reading_al.py` + `tests/test_ao_batch.py` + 文档），
  佐证一律用改动面清单，同值读数不作"零改动"佐证。
- 收口期自纠三处（如实登记，不改任何读数）：① 中英 README「最新优化」表行的
  「此前」链漏了 AJ 轮（AK 直接接 AI），已各补一句 AJ 摘要；② 本分册 §1 代码块
  被 `ruff format --check .` 判 `1 file would be reformatted`（行尾对齐空格），
  `ruff format` 后转绿；文件数 AK 902 → AL **904**（+ 新增测试文件 + 本分册）；
  ③ 中英 README 的 AL 行把 `10621 passed / 5 skipped / 0 failed` 写进
  `## 测试状态` 当前基线块，被 `check_baseline_numbers.py` 当场抓出（4 处残留），
  改为「全量零失败（读数见 BASELINE.yaml `tests` 节）」后转绿——与 AK 轮同型缺陷，
  说明该守卫在防复发上真实生效。
- **门禁实测（单独跑 `make gates`，不与其他命令重叠）**：**rc=0**，墙钟
  **2:58（178s）**；链内 ruff `All checks passed!` + **904 files already
  formatted**、mypy **135** 源文件 0 错、pytest **10621 passed / 5 skipped /
  0 failed**（collected 10626，173.95s）、双语文档 0 警告 0 失败、文档链接
  0 错误 / 0 需处理警告、env-budget 253/253、基线结构与数字守卫通过、状态通道
  134 文件、env-snapshot 115 键 / 缺失 0、工具版本一致、JSON 契约 7 处 / 9 文档、
  严格 JSON 7273 份（严格 7271 + 豁免 2 + 违规 0）/ 300 份源码 0 违规、
  报告→工件对账 `[OK]`、零断言 430 个测试文件 0 违规。门禁前的定向检查先抓出
  README 基线块硬编码（见自纠 ③），修复后才有本次 rc=0。

## 7. 边界（不得引用为「报告侧 token 口径已全仓闭合」）

1. **读不动是总量级阻断，矛盾是金额级阻断**：前者让 token 总量与两个比值全部
   不可读，后者保留 token 总量。两者不得互换，也不得把任一情形折成部分和。
2. **检出分母与 token 可读性解耦**：检出只认 `detection_rate`；`detection_rate`
   缺席仍不进可测分母——这是既有口径，不是本轮引入的"免费跳过"。
3. **零 token 行仍进检出分母**：显式零行不是"无记账"，也不从任务/检出口径剔除；
   AK 的 `n_zero_token_rows` 也不因本轮改变行级数学口径。
4. **缓存零行不是记账缺口**：只有合法且正向的缓存证据才排除；缓存字段坏值 /
   零命中仍是零记账行（AJ 边界）。
5. **价目侧未改**：多模型行、未登记模型、条目坏仍走既有 `unpriceable` 口径；
   本轮只收口"行级 token 读取"与"金额归因闭合"，不重议价目表准入。
6. **真批次零改变不等于修复无价值**：783 行恰好全部干净，本轮是潜在缺陷收口；
   真实读数逐位不变不能反证缺陷不存在（锁内用合成行分别触发每条机制）。
7. **报告工件不重写**：AL 块只在新报告生成时出现；受 `SHA256SUMS` 保护的归档
   保留原文本，差值以本分册登记。
8. **`n_rows_with_tokens_positive` 语义不变**：仍是 `n_priced + n_unpriceable`，
   不含显式零行，也不含被金额阻断的行；引用前先确认口径。
9. **返回域按键存在性判断**：AL 键只在真发生时写入；不得用"键缺席"推断"没有
   该类行"以外的结论，也不得把干净臂的旧键集当成"AL 未接线"的证据。
10. **未覆盖行 175 是既有分支**：`attach_usage` 的既有登记分支，不是本轮新增
    未覆盖；分母变化来自迁入，不得读成"覆盖率水位下降"。

## 8. 复算命令

```bash
# 目标集（57 例）
.venv/bin/python -m pytest -q tests/test_report_token_reading_al.py

# 真批次三臂读数
.venv/bin/python - <<'PY'
import json
from pathlib import Path

from experiments import emse_stats_report as rep

root = Path.cwd()
merged = {}
for p in sorted((root / "experiments/results/main_batch").glob("benchmark_synthetic_20261006_*.json")):
    data = json.loads(p.read_text(encoding="utf-8"))
    for arm, block in data["results"].items():
        merged.setdefault(arm, []).extend(block["details"])
for arm, rows in merged.items():
    eff = rep.cost_effectiveness_block(rows)
    print(arm, len(rows), eff["n_priced_rows"], eff["total_usd"],
          {k: v for k, v in eff.items() if k.startswith("n_token_")})
PY

# 全量 + 覆盖率（CI 同口径）
make test-cov
```
