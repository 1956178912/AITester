# AK 轮：少数无记账行不是免费，也不是精确值——成本读数是已记录花费的下界（2026-10-21，零 LLM）

**范围**：S11 的 50% 断裂阈值单侧通过时，成本读端对"少数无记账行"的处理——
`experiments/statistical_analysis.py`（`token_accounting_sanity` /
`cost_analysis` / 成本表与 `$/solved` 渲染）、
`experiments/emse_stats_report.py`（§4 记账单元格 / §4.1 成本-效果块）、
`experiments/emse_stats_extensions.py`（`_read_tokens` / `_cost_per_task`）。

**结论**：S11 只回答"记账是否断裂"（无记账行 ≥ 50% 才拒绝计算），但
`0 < 无记账行 < 50%` 的臂仍会输出成本数字。这些行以 0 进入金额分子、却仍占
任务分母，`$/task` 被按精确值渲染。主批 `plain_llm_df` 实测 35/261 行
（13.4%）token 三元组全 0、`llm_calls=0`，但 `generated_test` 非空——**有产出、
无花费记录**。本轮不改变行级数学口径（AE2 锁定），只把这类读数显式声明为
**已记录花费的下界**：新增 `n_zero_output_rows` 子集、`cost_caliber="recorded_lower_bound"`
与三层呈现披露；≥50% 断裂仍 `NOT_COMPUTABLE`，全记账臂与旧批次返回域、报告文本
逐字节不变。**21 例新锁 + 4/4 变异锚点转红**。

---

## 1. 缺陷定义

改前链路：

1. `token_accounting_sanity` 计算 `zero_share = n_without_accounting / n_rows`；
   `zero_share >= 0.5` ⇒ `computable=False`，否则成本照算。
2. `cost_analysis` 对缺失 `token_usage` 的行按 0 计（AE2 口径），行本身仍进
   `n_tasks` 分母，于是 `cost_per_task = cost / len(rows)`。
3. 成本表、`$/solved`、报告 §4 / §4.1、ext note 都只看到"可计算"，看不到
   "分子里有 N 行是 0、分母却包含它们"。

| 观测（主批三文件合并，261 行） | 改前读数 | 根因 |
|---|---|---|
| `plain_llm_df` 35 行 token 三元组全 0、`llm_calls=0`、`generated_test` 非空 | S11 `computable=True`（13.4% < 50%） | 阈值只挡断裂，不区分"有产出无记录"与"空行" |
| 上述 35 行中 3 行 `detection_rate=1.0` | 成本表 `$/task=0.004543231…` 按精确值渲染 | 检出进分母、金额只含已记录 token |
| 报告 §4.1 | "226 行计价 / 0 行不可计价" | 35 行在计价健全性单元格里消失 |
| `aitester` / `plain_llm` 两臂 | `token_zero_rows=0` | 无此类行，读数不受影响 |

要点：**0 是真的没记录，不等于没干活，也不等于免费**。把这 35 行从分母剔除会
改变检出/任务口径（AE2 明确不允许）；把它们当 0 又会让 `$/task` 看起来像精确
均值。唯一诚实的读法是：`$/task` 与 `$/solved` 是**已记录花费的下界**。

## 2. 处置

### 2.1 S11 子集计数

`token_accounting_sanity` 新增（仅 >0 时写入）：

```python
n_zero_output = sum(1 for r in rows if not _row_has_token_accounting(r) and _row_has_generated_test(r))
out["n_zero_output_rows"] = n_zero_output
```

`_row_has_generated_test` 只认 `generated_test` 为非空字符串——与 S11 原因文本
的实测形态同源，不猜 `patch` / `diagnosis` 等修复侧字段。旧批次无此类行时
返回键集逐键不变。

### 2.2 成本行口径键

`cost_analysis` 在既有 14 键之后：

```python
if accounting.get("n_zero_output_rows"):
    row["token_zero_output_rows"] = accounting["n_zero_output_rows"]
if cost is not None and rows and accounting["computable"] and accounting["n_without_accounting"] > 0:
    row["cost_caliber"] = "recorded_lower_bound"
```

- `token_zero_output_rows` 只在子集 >0 时写入；
- `cost_caliber` 只在**成本确有数字**且无记账行 **>0** 时写入（全记账臂不写）；
- ≥50% 断裂的臂 `computable=False`、`cost=None`，不写 `cost_caliber`，仍由
  `NOT_COMPUTABLE` 接管。

### 2.3 三层呈现

| 位置 | 改后行为 |
|---|---|
| `_cost_report_lines` | 成本表后追加「**成本口径下界（AK）**」节：`N/M 行无 token 记账`、`K 行 generated_test 非空（有产出、无花费记录）`、「已记录花费的下界」「不是精确均值，更不是免费」；计价与不可计价两分支都调用 |
| `$/solved` 行 | 值后追加「（记录下界：N/M 行无 token 记账）」 |
| `emse_stats_report` §4 | 记账单元格追加「其中 K 行 generated_test 非空、有产出无花费记录」 |
| `emse_stats_report` §4.1 | 新增「**零 token 行的成本口径（AK）**」块：逐臂 `N/M 行 token 全 0`，并声明这些行不进 `total_tokens` / `total_usd`、但检出数仍进分母 |
| ext `_cost_per_task` | note 追加「N/M 行 token 全 0，其中 K 行 generated_test 非空（有产出、无花费记录） ⇒ tokens/task 与 $/task 是已记录下界（缺记账行按 0 计），不是免费」；全记账臂旧 note 逐字不变 |

### 2.4 与 AJ 缓存口径的关系

缓存命中行的真实 token 为 0，但带合法且正向的 `cache_hits` / `cache_avoided_tokens`
证据——AJ 已把这类行算作"有记账"。AK 的两个计数（S11 子集与 ext `n_zero_rows`）
都排除缓存证据行，因此纯缓存臂不会被误标成"有产出无花费记录"；缓存收益仍只在
缓存口径节披露，不折算金额。

## 3. 真批次证据

主批三文件合并（`experiments/results/main_batch/benchmark_synthetic_20261006_*.json`）：

| 臂 | 行数 | 无记账行 | 其中有 generated_test | 成本读数 |
|---|---|---|---|---|
| `plain_llm_df` | 261 | 35（13.4%） | 35（3 行 detection=1.0） | `cost=1.1857833`、`$/task=0.004543231034482759`、`cost_caliber="recorded_lower_bound"`、`token_zero_output_rows=35` |
| `aitester` | 261 | 0 | 0 | 键集不变（无 `cost_caliber` / `token_zero_output_rows`） |
| `plain_llm` | 261 | 0 | 0 | 键集不变 |

报告 §4.1 对 `plain_llm_df` 的计价健全性仍为 **226 行计价 / 0 行不可计价**——
这 35 行不是"不可计价"，而是"已计价为 0 但没有记账"；新增的 §4.1 块负责把
这一事实与计价计数分开。ext 三臂读数与受保护归档
`results/emse_stats_extensions_20261016/STATS_EXTENSIONS.json` 逐字段不变；报告
只在新生成时出现 AK 节，历史工件不重写。

## 4. 回归锁

新增 `tests/test_partial_accounting_ak.py` **21 例**：

| 组 | 例数 | 覆盖 |
|---|---|---|
| `TestSanityOutputSubset` | 4 | 有产出零记账计数；无产出行不写键；全记账返回域为旧 5 键；缓存证据行不计入子集 |
| `TestCostCaliber` | 4 | 部分记账写 `cost_caliber` + 子集；全记账无新键；≥50% 断裂无 `cost_caliber`；无产出零记账行仍写下界（它仍是零记账行） |
| `TestCostReportLines` | 2 | 成本表渲染下界文案与行数；全记账不渲染 AK 节 |
| `TestReportSections` | 5 | §4 单元格点名产出子集；`cost_effectiveness_block` 计数；全记账无新键；§4.1 下界块；全记账无 §4.1 块 |
| `TestExtensionsNote` | 3 | 部分记账 note 声明下界；全记账 note 逐字不变；纯缓存零 token 行不落下界 |
| `TestRealMainBatch` | 3 | 主批 `plain_llm_df` 35/261 + `$/task`；另两臂 note 不含下界；§4.1 见 35 行与 226 行计价 |

另按新口径改写 AJ 两处旧锁（`tests/test_experiments_cache_caliber_aj.py`）：

- 归档报告只允许 AK note 差异（其余键逐键相等；df note 以归档 note 为前缀）；
- 单文件主批键域按记账状态断言（df 臂 8 行：`token_zero_output_rows=8`、
  `cost_caliber`、sanity `n_zero_output_rows`；另两臂保持 legacy 键域）。

## 5. 变异验证

目标文件 3 个（`statistical_analysis.py` / `emse_stats_extensions.py` /
`emse_stats_report.py`），基线 sha256 记录后逐锚点回退，写盘前 `compile()` 预校验，
还原后断言原字节，collected 恒 **89**。

| 锚点 | 回退内容 | 转红例数 |
|---|---|---|
| M1 | `_row_has_generated_test` 恒真（任何零记账行都算"有产出"） | 3 |
| M2 | `cost_caliber` 改写成 `"exact"`（下界被标成精确值） | 5 |
| M3 | ext `_zero_token_note` 恒返回空串（note 不披露下界） | 3 |
| M4 | 报告 §4.1 的 `if zero_arms:` 改 `if False:`（整块消失） | 1 |

**4/4 行为锚点转红，无幸存者**；中性注释对照 0 红；每次还原后 sha256 与基线
逐字节相同，restored 跑 89 passed。

## 6. 收口读数

- 登记前一跑（`make test-cov`，xdist -n 4 loadfile + `--cov`）：
  **10563 passed / 1 failed / 5 skipped**，collected **10569**，173s。
  唯一失败 = 基线守卫自身（BASELINE 尚未刷新；实收 10569 − 声明 10543 = 26 > 6 容差）。
- 净增 **21 例**（collected 10548 → 10569）。
- 收口确认跑（同一命令，BASELINE 刷新后）：
  **10564 passed / 5 skipped / 0 failed**，collected **10569**，**177.85s**，rc=0。
  较登记前一跑多的 1 例 = 基线守卫由红转绿，不是新用例。
- 覆盖率（同一份 `coverage.xml`，取确认跑）：行 **18554/19077 = 97.2559%**、
  分支 **6708/7144 = 93.8970%**。分母与 AJ 逐位相同（19077 行 / 7144 弧），
  覆盖 +1 行 / +1 弧，未覆盖行 **523**（AJ 524）、偏弧 **436**（AJ 437），
  落在已登记 ±2 行 / ±1 弧抖动域内——不作"回收/退化"主张；10 项核心模块行覆盖
  与三项核心路由分支覆盖按同一份 `coverage.xml` 逐项复算全部不变。
  本轮 `src/` 零改动（改动面 = 3 个 `experiments/` 脚本 + 1 个新测试文件 +
  2 个既有测试文件 + 文档），同值/差值均不作佐证，佐证一律用改动面清单。
- **门禁实测（单独跑 `make gates`，不与其他命令重叠）**：第一次跑 **rc=2**，
  链内 pytest **10563 passed / 1 failed / 5 skipped**（174.71s），唯一失败 =
  `test_check_baseline_numbers`——本轮 README「最新优化」行把
  `10564 passed / 5 skipped / 0 failed` 写进了 `## 测试状态` 当前基线块，触发
  既有的"当前基线块零硬编码"守卫（4 条：中英各 passed / failed 两项）。改法 =
  这两处改为"全量测试零失败（读数见 BASELINE.yaml `tests` 节）"，与既往轮次
  写法一致；**这是本轮自己引入、又被既有门禁当场抓住的真实文档缺陷，如实登记**。
  修复后第二次跑 **rc=0**，墙钟 **2:59.53**（351.53s user / 60.42s system），
  链内 pytest **10564 passed / 5 skipped / 0 failed**（174.57s、collected 10569）；
  ruff `All checks passed!` + `902 files already formatted`、mypy **135** 源文件
  0 错、严格 JSON 门禁 7273 份工件（严格 7271 + 豁免 2 + 违规 0）/ 300 份源码
  写入点 0 违规、报告→工件对账 `[OK]`、零断言扫描 429 个测试文件 0 违规，
  基线守卫转绿。两次跑读数与登记值一致，无新增失败。

## 7. 边界（不得引用为「成本口径已全仓闭合」）

1. **下界不是精确值**：`$/task` 与 `$/solved` 的分子只含已记录 token，分母是全部
   任务；下界与精确值同形，差额只能靠补齐记账后重跑消除。
2. **下界也不是免费**：35 行有 `generated_test` 产出，缺的是花费记录，不是工作。
3. **行级数学口径不变**：缺 `token_usage` 仍按 0 计、行仍进任务数分母（AE2 锁定）；
   本轮只增加披露，不改分子分母。
4. **S11 阈值不变**：`zero_share >= 0.5` 仍判 `NOT_COMPUTABLE`；AK 只处理阈值
   单侧通过的部分记账臂，不把断裂臂"救"成下界。
5. **"有产出"只认 `generated_test`**：非空字符串才算；`patch` / `diagnosis` 等
   修复侧字段不在判定内，因此 `n_zero_output_rows` 是下界中的下界，不得读成
   "所有有工作痕迹的行"。
6. **缓存行不落下界**：合法缓存证据行由 AJ 解释；纯缓存臂的 0 不是记账缺失。
7. **旧批次返回域不变**：全记账臂与旧 schema 批次不写新键、报告文本逐字不变；
   引用 `cost_caliber` / `token_zero_output_rows` 前先确认臂的记账状态。
8. **§4.1 的计价计数不是记账计数**：226 行计价 / 0 行不可计价与"35 行零记账"
   正交——前者说价目覆盖，后者说花费记录；两者不得互相替代。
9. **报告工件不重写**：AK 节只在新报告生成时出现；受 `SHA256SUMS` 保护的归档保
   留原文本，差值以本分册登记。
10. **数字精度不因下界变化**：`0.004543231034482759` 仍是该口径下的完整浮点读数，
    下界语义不改变其位数或舍入。

## 8. 复算命令

```bash
# 目标集与受影响旧锁（89 例）
.venv/bin/python -m pytest -q tests/test_partial_accounting_ak.py \
  tests/test_experiments_cache_caliber_aj.py

# 真批次部分记账读数
.venv/bin/python - <<'PY'
import json
from pathlib import Path

from experiments import statistical_analysis as sa

root = Path.cwd()
merged = {}
for p in sorted((root / "experiments/results/main_batch").glob("benchmark_synthetic_20261006_*.json")):
    data = json.loads(p.read_text(encoding="utf-8"))
    for arm, block in data["results"].items():
        merged.setdefault(arm, []).extend(block["details"])
price = json.loads((root / "experiments/price_table.json").read_text(encoding="utf-8"))
for row in sa.cost_analysis(merged, price):
    print(row["baseline"], row["n_tasks"], row["token_zero_rows"],
          row.get("token_zero_output_rows"), row.get("cost_caliber"),
          row["cost_per_task"])
PY

# 全量 + 覆盖率（CI 同口径）
make test-cov
```
