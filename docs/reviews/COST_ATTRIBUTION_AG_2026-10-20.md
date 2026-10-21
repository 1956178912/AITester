# AG 轮：未计价归因收口到单一机制索引（2026-10-20，零 LLM）

**范围**：AE 评审 §5「登记未修 / 口径边界」第 2 条（候选 C）——
`statistical_analysis.cost_analysis` 的 `missing_models` 桶把三种事实混在一个名字下，
修复建议与成因不对应。

**结论**：未计价归因收口为**单一机制索引**，三个披露桶全部由共享谓词派生且互斥；
呈现层按机制给建议。**真批次读数 0 行改变**（522 行、模型集 `{"deepseek-flash"}`）。
46 例新锁 + **15/15 变异锚点转红**；AB-14 / AB-16 / AB-17 三个旧锁按新口径改写（净 0 例）。

---

## 1. 缺陷定义

改前 `cost_analysis` 的披露桶只有两个，桶名与内容不对应（AE §5.2 前置实测）：

| 改前事实 | 落进哪个桶 | 后果 |
|---|---|---|
| 模型键在表里缺席 | `missing_models` | 正确 |
| 键在、价格域坏（`price_null` / `bool` / `str` / 负 / `nan` / `inf`） | `missing_models` | 冒充「没登记」 |
| 键在、条目不是对象 / 空条目 | `unpriced_currency_models` | 落进名为「币种」的桶 |
| 币种不可判定 / 非 USD | `unpriced_currency_models` | 正确，但与形状码混用 |
| 条目都可用、跨币种或跨价目组合不得求和 | 无 | 读者只看到 `（缺: ）` |

全未计价早退分支统一教读者「在价目表补 `input_per_mtok` / `output_per_mtok`」——
对价格域坏值是对的，对币种缺席、条目形状坏、行级混算都是**补错字段也不会变绿**。
本轮只改归因与呈现，不改变任何已有金额。

## 2. 共享谓词 `model_entry_reason`

`src/budget/pricing.py` 新增：

```python
def model_entry_reason(models, model, *, allow_non_usd=False) -> str | None:
    if model not in models:
        return "model_unregistered"
    return entry_block_reason(models[model], allow_non_usd=allow_non_usd)
```

- **键缺席**是表级事实，`entry_block_reason` 看不见；名字只在这里写一遍。
- 值 `null` **不是**键缺席：仍走 `entry_not_object:NoneType`（AB-17 判据）。
- `allow_non_usd=True` 只放行**可判定的非 USD**（`other:<NORM>`，成本表带币种列，
  按登记单位原样计价）；`absent` / `null` / `blank` / `not_string` 仍拒——
  没有单位就无法说这笔钱是什么。
- `run_b8_injection._price_entry_reason` 的本地 `model not in table` 分支删除，
  改为纯委托；两个站点从此得到同一个读数。

机制码优先级不变：**表缺席 > 条目形状 > 空条目 > 币种 > 价格数字**。

## 3. 三个披露桶 + 行级归因

| 键 | 内容 | 写入条件 |
|---|---|---|
| `missing_models` | **只含** `model_unregistered` | 非空 |
| `unpriced_currency_models` | 币种维状态（AB-14 词汇原样保留） | 非空 |
| `unpriced_model_reasons` | 完整机制图（模型 → 共享谓词码） | 非空 |
| `unpriced_row_reason` | `mixed_currencies:<L1/L2>` / `mixed_price_pairs` | 条目全可用但组合不可求和 |

- `missing` / 币种 / `others`（形状、空条目、价格域）三桶**互斥且并集为完整索引**。
- `unpriced_row_reason` 是**另一种事实**：「条目都读得出，但设计上不得求和」，
  不是条目缺陷，不得与前三桶混为一谈。
- 披露键只在非空时写入 ⇒ 可计价行（含真批次全部行）返回域逐键不变；返回域只增不改。

## 4. 呈现层按机制分支

- **纯未登记 / 无 token 观测**：旧四行逐行不变（`**价目未登记**` + 待计价模型 +
  补齐方式）。受保护报告文本因此不动。
- **存在真机制**（币种 / 形状 / 价格域 / 行级）：
  - 标题改 `**成本不可计算**`，不再声称「未登记」；
  - `**未计价机制**` 逐基线列出「模型（码）」；
  - 修法按码族给：`entry_*` → 修条目形状 / 空条目；`price_*` → 补缺键 /
    修类型 / 符号 / 有限性；`mixed_*` → 拆分后分别报告；
  - 只有确实存在 `missing_models` 时才打印「补齐方式（仅针对未登记模型）」。
- 币种维继续由 AB-14 的 `**币种不可判定**` 块点名，块内措辞不变。
- 逐行未计价注：历史「缺 / 币种不可判定」段保留，追加
  `；未计价机制: 模型（码）` 与 `；行级: mixed_*`；机制为 0 时仍是历史 `（缺: ）`。

## 5. 真批次不变量

| 项 | 实测 |
|---|---|
| 来源批次 | 2（`benchmark_synthetic_20261007_170147.json` / `_161053.json`） |
| 加载行数 | 522（aitester 174 / plain_llm 174 / plain_llm_df 174 / single_agent 0） |
| 模型集 | `{"deepseek-flash"}` |
| aitester 成本 | 0.8273823 USD（逐位不变） |
| 披露键 | 任何行均不新增 `unpriced_model_reasons` / `unpriced_currency_models` / `unpriced_row_reason` |
| 成本单元格 | 行文本 `aitester / 174 / 662361 / 523895 / 0.0048 / USD`（六个单元格逐格相同，整行逐字节相同） |
| 未计价注 | `注：1 个基线未计价——single_agent（缺: ）。` 逐字节相同 |
| 单位提醒 | 不出现（真批次无非 USD 计价行） |

`plain_llm` / `plain_llm_df` 的 `priced=False` 来自 S11 token 记账断裂，不在未计价注里
（注只收 `token_accounting_ok=True` 的行），本轮未改动该口径。

## 6. 回归锁与变异验证

新增 `tests/test_experiments_cost_attribution_ag.py` **46 例**：

| 组 | 例数 | 覆盖 |
|---|---|---|
| `TestSharedModelEntryReason` | 7 | 缺席 vs null vs 空；默认 USD-only；`allow_non_usd` 放行 CNY 但仍拒不可判定；不吞价格域；run_b8 委托同码；全仓单一定义 |
| `TestCostAnalysisMechanismIndex` | 22 | 未登记只进 `missing_models`；价格域矩阵（null/inf/nan/负/bool/str）；形状矩阵；币种状态；币种优先于价格；CNY 可计价；三桶分区；干净路径无键 |
| `TestRowLevelReasons` | 4 | 混币种 / 混价目 / 标签排序 / 同价不误报 |
| `TestRenderingByMechanism` | 10 | 纯未登记与无观测旧文本；形状 / 价格 / 币种 / 行级早退建议；部分未计价注；行级；旧币种段 |
| `TestRealBatchInvariants` | 3 | 真实 522 行读数与文本不变量 |

旧锁改写（登记口径变更，非改锁迁就失败）：

- `test_experiments_currency_caliber_ab14.py::test_price_missing_and_currency_missing_are_not_merged`：
  `missing_models == []`，价格码改读 `unpriced_model_reasons`；
- `test_experiments_price_admission_ab16.py::...not_a_price`：
  `missing_models == []`，`inf` 码改读机制图；
- `test_experiments_table_admission_ab17.py`：run_b8 接线断言改为
  `from src.budget.pricing import load_table_models, model_entry_reason`。

两处「旧锁的旧断言本身在 AG 后就是错的」如实登记：它们锁的是旧桶口径，
不是行为退化。

**变异验证**（目标集 5 文件，基线 365 passed / collected 365；每次写盘前 `compile()`，
还原后 sha256 断言原字节）：

| 锚点 | 回退内容 | 转红例数 |
|---|---|---|
| M1 | `missing` 回退为整个未计价集合 | 25 |
| M2 | 币种桶收全部非空机制码 | 23 |
| M3 | `cost_analysis` 丢掉 `allow_non_usd` | 11 |
| M4 | `allow_non_usd` 参数失效 | 13 |
| M5 | `allow_non_usd` 放行不可判定币种 | 20 |
| M6 | 删行级混币种归因 | 4 |
| M7 | 删行级混价目归因 | 1 |
| M8 | 不写 `unpriced_model_reasons` | 24 |
| M9 | 逐行注重复渲染币种码 | 2 |
| M10 | 早退标题永远走旧分支 | 5 |
| M11 | 早退不渲染机制块 | 3 |
| M12 | 未登记建议无条件打印 | 3 |
| M13 | run_b8 回退本地缺席分支 | 22 |
| M14 | 行级混价目闸门放宽 | 1 |
| M15 | null 条目并入未登记 | 3 |
| N1 | 只改注释（行为中性对照） | 0 |

**15/15 行为锚点转红**，collected 恒 365，基线全绿，三文件 sha256 原字节还原；
N1 中性对照 0 红，证明转红来自行为而非注释噪声。

## 7. 收口读数

- 登记前一跑（`pytest tests/ -n 4 --dist loadfile --cov=src --cov-branch`）：
  **10396 passed / 1 failed / 5 skipped**，collected **10402**，186.08s。
  唯一失败 = 基线守卫自身（BASELINE 尚未刷新；实收 10402 − 声明 10351 = 51 > 6 容差）。
- 收口确认跑（同命令）：**10397 passed / 5 skipped / 0 failed、rc=0**，178.78s。
  净增 46 例（collected 10356 → 10402）。
- 覆盖率（同一份 `coverage.xml`）：行 **18491/19015 = 97.2443%**、
  分支 **6675/7112 = 93.8555%**。`pricing.py` 新增 6 语句 / 2 弧**全部被锁执行**
  （`if` 两向 2/2）。未覆盖行 524（较 AF +1）、偏弧 437（+1）不在新增行、
  10 项核心模块逐项复算不变，落在已登记 ±2 行 / ±1 弧抖动域——**不作回收或退化主张**。
- ruff check / ruff format --check / mypy 本轮全部通过（含 `PERF401` 的 `list.extend` 修正）。
- `make gates` 全链**单独复跑 rc=0**（墙钟 **178s**）：链内 pytest **10397 passed /
  5 skipped / 0 failed、173.32s**（xdist -n 4 loadfile，不带 `--cov`——与上面的覆盖率
  口径不可互换引用）；`json-strict`（7273 工件 / 300 源文件、违规 0）、
  `artifact-doc-consistency`（§1 覆盖率声明与 `coverage.xml` 相符）、零断言（425 个
  测试文件 0 违规）全绿；AO3 英文 README 头部行锁按既定维护约定推进至 "AG round"。

## 8. 边界（不得引用为「未计价归因已全仓统一」）

1. **行级归因只在所有已用模型条目可用时成立**：若同臂还有未登记 / 坏条目模型，
   先报条目机制，`mixed_*` 不出现——条目缺陷优先，修完后才可能暴露行级混算。
   这是「一次只回答一个最上游成因」，不是遗漏，但读者不得据此断言「没有混算」。
2. **`missing_models` 语义变窄**：只表示「表里没有该模型键」。仓内消费点已全部改读
   新键（逐文件 grep 仅剩渲染器自身）；外部脚本若把 `missing_models` 当「全部未计价」
   会少读——该键是返回域的一部分，语义变更按本册登记，不再回退。
3. **`allow_non_usd` 不是「忽略币种」**：仅 `other:<NORM>` 放行；
   `not_string:<T>` 与不可判定币种仍拒，因为无法确定单位。
4. **`unpriced_currency_models` 是机制图的币种视图**，不是独立事实源；
   两者同源但用途不同（前者兼容 AB-14 词汇，后者给全机制）。
5. **建议是码族级的**：给出修法不等于保证修完即可计价（修完价格域后可能才暴露行级混算）。
6. **旧 `（缺: ）` 前缀保留**：只有非未登记机制时该段为空，读作「无键缺席」，
   不是「没有原因」——原因在紧随其后的 `；未计价机制:` 段。
7. **归档报告不重写**：真批次文本不变量由锁执行；历史报告中的旧措辞不回写，
   本轮的 `**成本不可计算**` 只出现在新生成报告。
8. **`run_b8` 的内置价兜底语义未变**：拒绝路径仍产出标准价上界数字（AE §5.8），
   AG 只统一了「为什么拒绝」的名字，不改变该脚本的成本口径。

## 9. 复算命令

```bash
# 目标集（AG 46 + AB-14/16/17 与 AE 锁，共 365 例）
.venv/bin/python -m pytest tests/test_experiments_cost_attribution_ag.py \
  tests/test_experiments_currency_caliber_ab14.py \
  tests/test_experiments_price_admission_ab16.py \
  tests/test_experiments_table_admission_ab17.py \
  tests/test_experiments_cost_admission_ae.py -q

# 真批次读数复算
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from experiments import statistical_analysis as sa
root = Path(".")
data, _ = sa.load_experiment_results_with_sources(
    str(root / "experiments" / "results"),
    ["main_batch/benchmark_synthetic_20261007_170147.json",
     "main_batch/benchmark_synthetic_20261007_161053.json"],
    pool_seeds=True,
)
table = json.loads((root / "experiments" / "price_table.json").read_text())
for row in sa.cost_analysis(data, table):
    print(row["baseline"], row["n_tasks"], row["cost"], row["currency"],
          row["missing_models"], row.get("unpriced_model_reasons"))
PY

# 全量 + 覆盖率（CI 同口径）
COVERAGE_FILE=.coverage.ci .venv/bin/python -m pytest tests/ -n 4 --dist loadfile \
  --cov=src --cov-branch --cov-report=term-missing --cov-report=xml
```
