# AI 轮：token 计数也有值域——不完整的 token 和不是 token 读数（2026-10-21，零 LLM）

**范围**：AH §7 第 1~3 条（`docs/reviews/COST_COMPLETENESS_AH_2026-10-20.md` §7 的
`tokens_per_task` 两态 / `by_model` 形状域 / `input+output` 与 `total_tokens` 一致性）——
`experiments/emse_stats_extensions.py` 的 `_cost_per_task` 与 `_bootstrap_cost_ci`
两个消费点。

**结论**：AH 把"三种不完整的和"判在金额侧，但读入侧仍是 `sum += value or 0`。
本轮把"一行 token 记账算什么"收成一次读取：**三个非负整数**；形状/缺席/类型/负数/非有限
任一不成立 ⇒ 整臂 `tokens/task` 与 `$/task` 均 `None` 并点名机制。行级
`input+output != total_tokens` 与 `by_model` 读不动只废金额（token 总数仍可读）。
**真批次三臂读数逐位不变**（`26114.854406130267 / 3209.44061302682 / 4223.103448275862`；
`$/task` `0.025884977011494247 / 0.003358973563218391 / 0.004543231034482759`），
受保护归档未重写。63 例新锁 + **18/18 变异锚点转红**；AH 旧锁改写 1 例（净 0 例）。

---

## 1. 缺陷定义

改前一行 token 记账直接 `sum += value or 0`，`_cost_per_task` 与 `_bootstrap_cost_ci`
各读一遍。合成批次实测：

| 构造 | 改前 `tokens/task` | 改前 `$/task` | 改前结局 |
|---|---|---|---|
| `total_tokens: "100"` | 崩溃 | 崩溃 | `TypeError`（字符串相加） |
| `token_usage: []` / `"x"` / `5` | 崩溃 | 崩溃 | 真值非对象在 `.get` 上 `AttributeError` |
| `total_tokens: true` | 1（`True` 当 1） | 按 1 token 计价 | 布尔被当计数 |
| `total_tokens: -5` | 负数 | 负金额 | 负数进入和与单价 |
| `total_tokens: inf` | `inf` | `nan` | 占比成 `nan`；`inf != inf` 为假，AH 闭合检查放行 |
| `token_usage` 缺席 / `{}`，但 in/out 有数 | `0.0` | `0.0` 或部分和 | 键缺席经 `or {}` 折成"零 token" |
| `total_tokens` 缺席、in/out 有数 | `0.0` | 0.0 | 分母在、分子被吞 |
| `by_model: []` / `"x"` | token 可读 | 崩溃 | `.items()` / `.get` 抛异常 |
| `by_model: {5: 100}` | token 可读 | 金额混入 | 非字符串键不拦截 |
| `by_model: {"m": "100"}` | token 可读 | 崩溃 | 字符串在 `+=` 上 `TypeError` |
| 行级 `in+out != total_tokens` | token 可读 | 按错误分母计价 | 无任何判定 |
| `n_tasks == 0` | `0.0` | `0.0` | 没有分母仍给出"每任务读数" |

真批次三臂的 `token_usage` 全部合法且 `by_model` 合计闭合，所以改前读数没有暴露这条缺陷
——它是构造性缺口，不是已发生的错账。

## 2. 处置

新增四个助手（`experiments/emse_stats_extensions.py`）：

```python
_TOKEN_FIELDS = ("total_tokens", "input_tokens", "output_tokens")

def token_count_reason(value, field):        # bool / 非有限 / 非 int / 负数 → 机制名
def _row_token_counts(row):                  # (total, in, out) 或 (None, [机制名])
def _reason_summary(reasons):                # "code←n 行；…"
def _read_tokens(files, arm):                # 计数 + 归因 + 值域一次判完
```

机制词汇：

- 整臂（`value_reasons` 非空 ⇒ `tokens/task` 与 `$/task` 均 `None`）：
  `token_usage_absent` / `token_usage_not_object:<T>` / `token_field_absent:<field>` /
  `token_not_count:<field>:<T>` / `token_not_finite:<field>` / `token_negative:<field>`；
- 只废金额（token 总数仍可读）：
  `token_split_mismatch:<in+out>/<total>` / `by_model_not_object:<T>` /
  `by_model_key_not_string:<T>` / `token_not_count:by_model:<T>`。

两条口径纪律：

1. **缺席不是零**：`token_usage` 缺席 / 为 `null` / 空对象 / 缺字段，四种形状各自点名；
   真零必须显式写三个 0。
2. **提示必须指向真缺陷**（AG 纪律）：`by_model` 在场但读不动时不再同时报
   `no_model_attribution`——否则照提示去补 `by_model` 也不会变绿。

`tokens_per_task` 改为 `float | None`（AH §7 第 1 条一并处置：无任务 ⇒ `None`）；
`_bootstrap_cost_ci` 与 `_cost_per_task` 共用 `_read_tokens`，返回值改
`tuple[float, float] | None`；渲染侧 `tpt_cell` 为 `—（无 token 读数）`、`ci_cell` 为 `—`。
`build_report` 的 `tokens_per_task_bootstrap95` 相应可写 `null`。

## 3. 真批次不变量

| 臂 | tokens/task | bootstrap 95% CI | `$/task` |
|---|---|---|---|
| aitester | 26114.854406130267 | (24226.310344827587, 28086.015325670498) | `0.025884977011494247` |
| plain_llm | 3209.44061302682 | (2964.015325670498, 3474.2337164750957) | `0.003358973563218391` |
| plain_llm_df | 4223.103448275862 | (3822.942528735632, 4642.52490421456) | `0.004543231034482759` |

三臂读数由锁执行（同时与受保护 `STATS_EXTENSIONS.json` 逐字段比较）。
`results/emse_stats_extensions_20261016/` 的 JSON / README / `SHA256SUMS` **一字未动**：
当前 `build_report()` 的 JSON 与归档差 0；渲染 Markdown 只多 §4 四行口径，
归档按"不重写历史工件"处置，差值登记在册。

## 4. 回归锁

新增 `tests/test_experiments_token_domain_ai.py` **63 例**：

| 组 | 例数 | 覆盖 |
|---|---|---|
| `TestTokenCountDomain` | 16 | 合法非负整数（0 / 100 / 2^53）；bool ×2；负数；float ×2；非有限 ×2；非数字 ×4 |
| `TestRowTokenCounts` | 7 | 合法三元组；`token_usage` 缺席；非对象 ×4；空对象三字段全缺；`total_tokens` 缺席 |
| `TestCostPerTaskValueDomain` | 15 | 非对象 / 缺席 / 缺字段不再读成 0；坏计数逐类点名；一行坏值废整臂；负数不出负金额；`inf` 不穿闭合检查 |
| `TestAttributionValueDomain` | 12 | `by_model` 非对象保留 token 废金额；值域坏 ×4；非字符串键；行级 split ×4；两行 split 独立计数 |
| `TestZeroAndDenominator` | 2 | 真零仍是真实 0；零任务两项都无读数 |
| `TestBootstrap` | 7 | 坏读数无 CI ×4；非有限不进 CI；零任务无 CI；真零 `(0,0)`；真批次 CI 逐位相同 |
| `TestRender` | 2 | `None` 不渲染成 0；口径节写明值域与闭合 |
| `TestRealBatchInvariants` | 2 | 真批次形状合法且闭合；三臂读数与受保护工件逐字段相同 |

旧锁改写（登记口径变更，非改锁迁就失败）：

- `test_experiments_cost_completeness_ah.py::test_zero_tasks_has_no_denominator`：
  `tpt == 0.0` → `tpt is None`，注释指向 AH §7 第 1 条。

## 5. 变异验证

目标集 2 文件（AI 63 + AH 15），基线 **78 passed / collected 78**；每次写盘前
`compile()`，还原后 sha256 断言源文件原字节（`ecb52fe7…`），collected 恒 78。

| 锚点 | 回退内容 | 转红例数 |
|---|---|---|
| M1 | 移除 bool 分支 | 4 |
| M2 | 移除非有限分支 | 7 |
| M3 | 移除非 int 分支 | 11 |
| M4 | 移除负数分支 | 3 |
| M5 | `token_usage` 缺席改报非对象 | 2 |
| M6 | `token_usage` 非对象改报缺席 | 8 |
| M7 | 字段缺席改报整对象缺席 | 3 |
| M8 | 移除行级 split 校验 | 3 |
| M9 | `by_model` 非对象改报键类型 | 3 |
| M10 | 键非字符串改报非对象 | 1 |
| M11 | `by_model` 值域绕过谓词 | 6 |
| M12 | 移除整臂值域早退 | 14 |
| M13 | 零任务 `tokens/task` 退回 0.0 | 2 |
| M14 | 读不动的 `by_model` 也报 `no_model_attribution` | 3 |
| M15 | split 不进入金额阻断 | 3 |
| M16 | `by_model` 值域不进入金额阻断 | 9 |
| M17 | bootstrap 不再拒绝坏读数 | 4 |
| M18 | `None` token 读数渲染成 0 | 1 |
| N1 | 只改 docstring（行为中性对照） | 0 |

**18/18 行为锚点转红**，中性对照 0 红，collected 恒 78。

## 6. 收口读数

- 登记前一跑（`make test-cov`，xdist -n 4 loadfile + `--cov`）：
  **10474 passed / 1 failed / 5 skipped**，collected **10480**，177.20s。
  唯一失败 = 基线守卫自身（BASELINE 尚未刷新；实收 10480 − 声明 10417 = 63 > 6 容差）。
- 收口确认跑（同命令）：**10475 passed / 5 skipped / 0 failed、rc=0**，177.44s。
  净增 63 例（collected 10417 → 10480）。
- 覆盖率（同一份 `coverage.xml`）：行 **18491/19015 = 97.2443%**、
  分支 **6675/7112 = 93.8555%**，与 AH **逐位相同**。本轮 `src/` + `config.py` 零改动
  （改动面 = `experiments/emse_stats_extensions.py` + 1 个新测试文件 + 1 个既有测试文件
  + 文档），同值不作佐证，佐证一律用改动面清单。
- 静态检查：`ruff check .` 通过；`ruff format --check .` **897 files already formatted**
  （AH 的 896 未计入本轮新文件，收口实测更正）；`mypy src/ config.py`
  **135 source files，0 issues**。
- `make gates` 全链**单独复跑 rc=0**（墙钟 **179s**，链内 **10475 passed / 5 skipped /
  0 failed**，174.74s，xdist -n 4 loadfile，不带 `--cov`——与上面的覆盖率口径不可互换引用）。
  首跑被 `test_markdown_table_integrity` 如实抓红：本轮写入 `docs/INDEX.md` 的 AI 行把
  `float | None` / `tuple | None` 的裸竖线放进了表格单元格（GFM 切格后单元格数 2 ≠ 4、
  尾格被丢弃），转义为 `\|` 后转绿——与本轮主题同型（源码里写全了，渲染出来读不到），
  自纠如实登记。`json-strict`（工件 7273 份 = 严格 7271 + 2 份 A20 豁免、违规 0；
  源码 300 份、写入点违规 0）、`artifact-doc-consistency`（§1 覆盖率声明与
  `coverage.xml` 相符，容差 ±0.20pp）、零断言（**427** 个测试文件 0 违规）、
  双语文档 / 文档链接 / 基线 / env / 状态契约全部通过；AO3 英文 README 头部行锁
  按维护约定推进至 "AI round"。

## 7. 边界（不得引用为「token 读数已全仓闭合」）

1. **`statistical_analysis.cost_analysis`（S11）仍是行级 0 口径**：缺 `token_usage`
   的行仍计 0 token 并进任务数分母，只在呈现层插 `NOT_COMPUTABLE`（AE2 历史口径）。
   本轮只改 `experiments/emse_stats_extensions.py`，两套口径并存，不得混引。
2. **`token_usage: {}` 从 0.0 改为整臂无读数**（三个 `token_field_absent`）：
   空对象 = 三个字段都没记录，不是"零 token"；真零必须显式写三个 0。
   这是相对 AH 的行为变化，引用旧读数前先看批次是否含空对象。
3. **真零 + 无 `by_model` 仍是 `0.0` 金额**：`tok == 0` 时 AH 的
   `no_model_attribution` 不触发（`tok > 0` 为假），`$/task` 为 0.0——
   "没有 token 可漏计"的豁免态不变，不得读成"已拒绝所有无 `by_model` 情形"。
4. **`tokens/task` 与 `$/task` 的三态不同步**：行级 split 或 `by_model` 值域坏时
   token 总数仍可读、金额为 `None`；不得因金额 `None` 就说"token 强度不可用"，反之亦然。
5. **`token_count_reason` 只收 `int`**：`Decimal` / `numpy.int64` 等真数落
   `token_not_count:<T>`；仓内批次经 JSON 载入只会产生 `int`，其它注入点将来接入需另判。
6. **`_reason_summary` 是自由文本**：机制名按码排序、以 `code←n 行` 串进 note，
   没有结构化披露键，机读须解析字符串（AH ⑥ 延续）。
7. **bootstrap 的 `(0.0, 0.0)` 不是"已验证为零"**：`n_tasks > 0` 但没有任何检测行时
   返回 `(0.0, 0.0)`；`None` 只表示 token 读数不可用或无分母，两者都不是区间估计。
8. **真批次 0 行改变是实测不是性质**：三臂全是合法非负整数且 `by_model` 合计闭合；
   换批次 / 换生产者即可能走到新机制。
9. **受保护归档不重写**：`results/emse_stats_extensions_20261016/` 的 JSON 与 README
   一字未动，当前渲染器对 README 多出 §4 四行口径——只锁"未重写"，不回写历史措辞。
10. **未覆盖面**：`by_model` 键非字符串只在合成 dict 可达（JSON 对象键恒为字符串），
    锁存在但真路径无实例；不得读成"真实批次已测过非字符串键"。

## 8. 复算命令

```bash
# 目标集（AI 63 + AH 15，共 78 例）
.venv/bin/python -m pytest tests/test_experiments_token_domain_ai.py \
  tests/test_experiments_cost_completeness_ah.py -q

# 真批次三臂读数与 CI
.venv/bin/python - <<'PY'
from experiments import emse_stats_extensions as ext
for arm in ("aitester", "plain_llm", "plain_llm_df"):
    print(arm, ext._cost_per_task(ext.MAIN_BATCH_FILES, arm))
    print(arm, "CI", ext._bootstrap_cost_ci(ext.MAIN_BATCH_FILES, arm))
PY

# 全量 + 覆盖率（CI 同口径）
make test-cov
```
