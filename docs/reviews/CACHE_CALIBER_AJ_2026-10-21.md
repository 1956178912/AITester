# AJ 轮：缓存命中是第三种记账状态——不是记账断裂，也不是免费（2026-10-21，零 LLM）

**范围**：生产者 `src/budget/token_usage.record_cache_hit_usage` 写入的
`cache_hits` / `cache_avoided_tokens` 在所有成本读端的消费——
`experiments/statistical_analysis.py`（S11 `token_accounting_sanity` +
`cost_analysis`）、`experiments/emse_stats_report.py`（`cost_block` /
`cost_effectiveness_block` / 成本章节渲染）、
`experiments/emse_stats_extensions.py`（`_cost_per_task`）。

**结论**：两个缓存字段此前**只有写、没有读**。缓存密集臂因"真实 token 为 0 的行
占比达到阈值"被 S11 判 `NOT_COMPUTABLE`；纯缓存臂的成本行只剩一句无因的
"（缺: ）"。本轮把缓存读数收口到生产者模块的共享读取器（`cache_caliber` 判单行、
`cache_totals` 判一臂），缓存证据算"有记账"，坏值 / 半套 schema 不留部分和；
避免 token 只披露、不折算金额。真批次 QuixBugs / ULT / examples 三臂从
"不可计算 / 无因"变为"可计算 + 命中与避免 token 披露"；主批旧 schema 返回域、
note 与受保护工件逐字节不变。**68 例新锁 + 19/19 变异锚点转红**。

---

## 1. 缺陷定义

缓存命中不产生真实 API 消耗：`record_cache_hit_usage` 只累加
`cache_hits` / `cache_avoided_tokens`，**不调用** `record_usage`，因此该行的
`input_tokens` / `output_tokens` / `total_tokens` 为 0 是正确读数。改前所有成本
读端都只看真实 token，于是把"命中"读成"没有记账"：

| 观测 | 改前读数 | 根因 |
|---|---|---|
| QuixBugs df 臂：50/50 行带缓存字段、64 次命中、123644 avoided | S11 `computable=False`、`n_without_accounting=50` | 命中行真实 token 为 0，被当成记账断裂 |
| ULT df 臂：20 行命中、39 次命中、89249 avoided | 成本行 `priced=False`、备注无因"（缺: ）" | 行级零 token 全是缓存命中，被读成"零 / 未计价" |
| examples df 臂：2 行命中、2 次命中、3387 avoided | `NOT_COMPUTABLE` | 同上，缓存密集臂被整体拒绝 |
| 主批 261 行/臂（旧 schema，无缓存键） | 正常 | 没有缓存字段，读端无从区分 |

要点：**0 是真的 0，但不是免费**。avoided token 是"若未命中会消耗"的反事实
计量，不是支出；把它加进 `$/task` 会虚构金额，把它当 0 又会低报缓存收益。
它是第三种记账状态，必须单独披露。

## 2. 处置

共享读取器收口到生产者模块 `src/budget/token_usage.py`：

```python
_CACHE_FIELDS = ("cache_hits", "cache_avoided_tokens")

def count_reason(value, field):    # AI 轮迁入：token 三元组与缓存字段共用的值域谓词
def cache_caliber(usage):          # 单行：present / complete / hits / avoided / evidence / reasons / missing
def cache_totals(usages):          # 一臂：n_rows / n_rows_with_fields / n_hit_rows / hits / avoided / reasons / missing
```

`experiments/emse_stats_extensions.token_count_reason` 保留为别名，AI 的锁与
调用点不需要改写。四个消费点：

| 消费点 | 接入后行为 |
|---|---|
| S11 `_row_has_token_accounting` | 合法且正向的缓存字段（`evidence`）→ 该行算"有记账" |
| S11 `token_accounting_sanity` | `n_cache_hit_rows` 只在 schema 在场时返回；理由追加"缓存命中已为 N 行提供记账"（N > 0） |
| `cost_analysis` | 缓存字段在场才写 `cache_hits` / `cache_avoided_tokens` / `cache_rows` / `cache_hit_rows`；不完整时加 `cache_reading_reasons`；纯缓存臂给 `unpriced_row_reason="cache_hit_no_api_spend"` |
| `emse_stats_report` | 两个成本块同源披露；成本章节按臂渲染缓存口径行、§4 的 sanity 单元格与 §4.1 的真实消耗提示 |
| ext `_cost_per_task` | `_cache_note` 追加到四条返回路径的 note；旧 schema 的 note 逐字不变 |

机制词汇（沿用 token 计数的同一套）：

- 字段缺席 / 坏值：`token_field_absent:<field>` /
  `token_not_count:<field>:<T>` / `token_not_finite:<field>` /
  `token_negative:<field>`；
- 一臂不完整 ⇒ `hits` / `avoided` 均为 `None`，机制名按行计数留在
  `reasons` / `missing`，**不留部分和**；
- 纯缓存臂的成因：`cache_hit_no_api_spend`（只在真实消耗确为 0、无已计价 /
  未计价模型、缓存读数完整且确有命中行时给出）；
- 披露键：`cache_hits` / `cache_avoided_tokens` / `cache_rows` /
  `cache_hit_rows` / `cache_reading_reasons`。

两条口径纪律：

1. **第三态不得与另外两态混同**：缓存命中既不是记账断裂（真实消耗 0 是对的），
   也不是免费（avoided token 是反事实）；`$/task` 始终是真实花费口径。
2. **值域坏不得读成"没有缓存"**：负命中数、字符串、`nan` 等进 `reasons` 且不参与
   `evidence`，既不救 S11，也不产生部分和。

## 3. 真批次证据

| 批次 · 臂 | 行数 | 命中行 | hits | avoided | S11 | 成本读数 |
|---|---|---|---|---|---|---|
| QuixBugs df | 50 | 50 | 64 | 123644 | `computable=True`、`n_without_accounting=0` | `priced=True`（2 行真实调用可计价） |
| ULT df | 20 | 20 | 39 | 89249 | `computable=True` | `unpriced_row_reason="cache_hit_no_api_spend"` |
| examples df | — | 2 | 2 | 3387 | `computable=True` | 无未计价成因 |
| 主批三臂（旧 schema） | 261 / 臂 | 0 | — | — | 键集不变 | 三臂读数逐位不变 |

主批（旧 schema）的 ext 读数不变：

| 臂 | tokens/task | `$/task` |
|---|---|---|
| aitester | 26114.854406130267 | `0.025884977011494247` |
| plain_llm | 3209.44061302682 | `0.003358973563218391` |
| plain_llm_df | 4223.103448275862 | `0.004543231034482759` |

`results/emse_stats_extensions_20261016/STATS_EXTENSIONS.json` 与当前
`build_report()` 逐字段相等；README 未重写。主批三臂的 `cost_analysis` 返回键集
与 AI 轮登记的 14 键逐项相同，S11 返回键集为 5 键——两类旧 schema 由锁逐键固定。

## 4. 回归锁

新增 `tests/test_experiments_cache_caliber_aj.py` **68 例**：

| 组 | 例数 | 覆盖 |
|---|---|---|
| `TestSharedCountPredicate` | 17 | `count_reason` 别名同一性；非负整数 / bool / 负数 / float / 非有限 / 非数字值域 |
| `TestRowCacheCaliber` | 10 | 字段全缺 / 全零 / 仅命中 / 仅避免 / 坏值 / 半套 schema / 非对象形状 |
| `TestArmCacheTotals` | 7 | 无 schema 惰性；空臂；真零；逐行求和；坏值废整臂；半套 schema；非对象行 |
| `TestS11CacheEvidence` | 7 | 纯缓存臂可计算；QuixBugs 50 行真实形状；旧 schema 理由逐字不变；坏值 / 零命中不救；仍断裂的臂照报；空臂不写键 |
| `TestCostAnalysisCache` | 6 | 旧 schema 14 键域；恰好 4 个缓存键；纯缓存成因；真实消耗与缓存混合计价；不完整废读数；零缓存不背锅 |
| `TestCostReportCache` | 5 | 旧 schema 无缓存章节；命中 / 避免渲染；不再 `NOT_COMPUTABLE`；不完整披露；行级成因文案 |
| `TestEmseReportCache` | 8 | 两个成本块旧 schema 键域；缓存键；纯缓存可计算；渲染门控；`NOT_COMPUTABLE` 缓存说明 |
| `TestExtensionsCacheNote` | 4 | 旧 note 不含"缓存"；缓存 note；坏值机制；归档 `STATS_EXTENSIONS.json` 相等 |
| `TestRealCacheArms` | 4 | examples / QuixBugs / ULT 三条真批次字面量；主批旧 schema 键集与读数不动 |

既有 14 个成本 / 报告锁文件（`test_cluster_robust_stats.py`、
`test_emse_stats_report.py`、`test_experiments_token_domain_ai.py` 等）**零改写**，
全部在新口径下保持绿色。

## 5. 变异验证

目标集 4 个源文件（token_usage / statistical_analysis / emse_stats_report /
emse_stats_extensions），基线 sha256 记录后逐锚点回退，写盘前 `compile()` 预校验，
还原后断言原字节（`a43cb716…` / `10262a03…` / `29a8a074…` / `81ba376a…`），
collected 恒 298。

| 锚点 | 回退内容 | 转红例数 |
|---|---|---|
| M1 | 缓存字段永不识别 | 38 |
| M2 | 零命中也算证据 | 10 |
| M3 | 跳过缓存值域判定 | 10 |
| M4 | 半套 schema 也算完整 | 11 |
| M5 | 不完整也给部分和 | 6 |
| M6 | 命中行数按字段行计 | 6 |
| M7 | S11 不采信缓存证据 | 10 |
| M8 | 旧 schema 也带 `n_cache_hit_rows` | 4 |
| M9 | 断裂原因不提缓存救回行 | 2 |
| M10 | 旧 schema 也带缓存键 | 3 |
| M11 | 零命中也给缓存成因 | 1 |
| M12 | 成本章节不渲染缓存口径 | 3 |
| M13 | 缓存成因混入行级混算 | 1 |
| M14 | 报告块无条件加缓存键 | 3 |
| M15 | 报告 §4 不渲染缓存行 | 1 |
| M16 | ext note 不披露缓存 | 2 |
| M17 | ext 读取器丢缓存汇总 | 2 |
| M18 | §4 不标缓存命中行 | 1 |
| M19 | §4.1 不提醒真实消耗口径 | 1 |

**19/19 行为锚点转红，无幸存者**；中性文档串对照 rc=0 / failed=0；每次还原后
sha256 与基线逐字节相同。

## 6. 收口读数

- 登记前一跑（`make test-cov`，xdist -n 4 loadfile + `--cov`）：
  **10542 passed / 1 failed / 5 skipped**，collected **10548**，175.54s。
  唯一失败 = 基线守卫自身（BASELINE 尚未刷新；实收 10548 − 声明 10475 = 73 > 6 容差）。
- 净增 **68 例**（collected 10480 → 10548）。
- 收口确认跑（同一命令，BASELINE 刷新后）：
  **10543 passed / 5 skipped / 0 failed**，collected **10548**，**179.94s**，rc=0。
  较登记前一跑多的 1 例 = 基线守卫由红转绿，不是新用例。
- 覆盖率（同一份 `coverage.xml`，取确认跑）：行 **18553/19077 = 97.2532%**、
  分支 **6707/7144 = 93.8830%**。分母较 AI +62 行 / +32 弧 =
  `src/budget/token_usage.py` 的共享读取器与迁入的 `count_reason`；
  该文件 131 条语句执行 130 条（99.24%）、21 个条件分支 97.62%，
  唯一未覆盖行 175 为 `attach_usage` 既有登记分支。未覆盖行 524、偏弧 437
  （与 AI 逐位相同）。预登记一跑曾读 18554/19077 与 6708/7144（97.2585% /
  93.8970%），确认跑较之 −1 行 / −1 弧，落在已登记 ±2 行 / ±1 弧抖动域内——
  两种读数均不作"回收/退化"主张；10 项核心模块逐项复算全部不变。
- `make gates` 全链（单独跑、不与其它命令重叠）：
  **rc=0**，墙钟 **178.74s**；链内 pytest **10543 passed / 5 skipped / 0 failed**、
  **173.67s**（不带 `--cov`）。链内各门禁均通过：lint / format / typecheck /
  docs-check（双语 0 警告 0 失败、链接 640 条 0 错误 0 警告）/ env-budget /
  baseline-check / state-contract / env-snapshot / model-fingerprint /
  tool-versions / json-contract-sites / json-strict（工件 7273 份违规 0）/
  artifact-doc-consistency（含登记册覆盖率 ±0.20pp 对账）/ zero-assert
  （428 个测试文件、零断言用例 0）。

## 7. 边界（不得引用为「缓存口径已全仓闭合」）

1. **`$/task` 不含 avoided token**：把 avoided 折算进金额会虚构支出；本轮只披露
   命中次数与避免 token，若要"无缓存理论成本"，须另立口径并披露换算假设。
2. **avoided token 无模型归因**：`record_cache_hit_usage` 接收 `model` 但不写
   `by_model`（避免污染真实消耗归因），因此无法按模型价目折算避免金额。
3. **S11 仍是行级零 token 占比启发式**：缓存证据只能救"合法且正向"的命中行；
   命中数为 0 且 avoided 为 0 的行不提供证据；阈值 0.5 不变。
4. **部分和一律不出现**：任一命中行缓存字段坏 / 缺，整臂 `hits` / `avoided`
   为 `None` 并点名机制；不完整读数不得与完整读数混引。
5. **schema 代次按行判定**：无缓存字段的行不计入 `cache_rows`、也不记为缺失；
   混合 schema 臂的披露会显示 `P/Q` 行带字段，但合计只覆盖带字段的行——
   不得把该合计读成整臂合计。
6. **同一字段两种形状**：`cache_hits > 0` 且 `avoided = 0`（LRU 快路径）是合法
   读数——命中率可算、避免成本不可算；不得据 avoided=0 推断"没有节省"。
7. **纯缓存成因只在严格前件下给出**：`cost is None`、无已计价 / 未计价模型、
   缓存读数完整、确有命中行、真实 in/out 为 0、无未归因 token，六项同时成立才
   写 `cache_hit_no_api_spend`；其它无金额情形仍按各自机制报。
8. **披露键只在 schema 在场时出现**：旧批次（主批 / E6 / E4）的返回域、报告文本
   与受保护工件逐字节不变；引用新键前先确认批次 schema 代次。
9. **非对象 `token_usage` 行不进缓存汇总**：`cache_totals` 跳过非 dict 行；
   这些行的值域问题仍由 AI 的 token 读取器处理，不得读成"缓存已覆盖全部行"。
10. **真批次读数变化是缓存口径的历史欠账**：QuixBugs / ULT / examples 的
    `NOT_COMPUTABLE` 与无因备注是改前行为；历史报告不重写，差值以本分册登记。

## 8. 复算命令

```bash
# 目标集（68 例）
.venv/bin/python -m pytest tests/test_experiments_cache_caliber_aj.py -q

# 真批次缓存读数（三条批次的 df 臂）
.venv/bin/python - <<'PY'
import json
from pathlib import Path

from experiments import statistical_analysis as sa

root = Path.cwd()
price = json.loads((root / "experiments/price_table.json").read_text(encoding="utf-8"))
for rel in (
    "experiments/results/benchmark_examples_20261012_160629.json",
    "experiments/results/emse_d1_quixbugs_ab_20261013/benchmark_quixbugs_20261013_155145.json",
    "experiments/results/emse_ult_dfsmoke_20261017/benchmark_ult_20261017_100932.json",
):
    data = json.loads((root / rel).read_text(encoding="utf-8"))
    rows = {"plain_llm_df": list(data["results"]["plain_llm_df"]["details"])}
    sanity = sa.token_accounting_sanity(rows["plain_llm_df"])
    out = sa.cost_analysis(rows, price)[0]
    print(rel.split("/")[-1], sanity["computable"], sanity.get("n_cache_hit_rows"),
          out.get("cache_hits"), out.get("cache_avoided_tokens"),
          out.get("unpriced_row_reason"))
PY

# 全量 + 覆盖率（CI 同口径）
make test-cov
```
