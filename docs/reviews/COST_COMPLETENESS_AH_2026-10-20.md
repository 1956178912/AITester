# AH 轮：$/task 只在完整覆盖且归因闭合时才是金额（2026-10-20，零 LLM）

**范围**：AE 评审 §5「登记未修 / 口径边界」第 1 条（候选 B，AE §5.1）——
`experiments/emse_stats_extensions._cost_per_task` 对"价目表没登记"仍走"部分和 + note"，
且 `by_model` 缺失 / 合计不闭合 / 无任务分母时照样给出 `0.0`。

**结论**：`usd_per_task` 只有在**价目覆盖全部 `by_model` token 且 token 归因闭合**时才给金额；
其余一律 `None` 并在 note 点名机制。**真批次三臂读数逐位不变**
（`0.025884977011494247 / 0.003358973563218391 / 0.004543231034482759`）。
15 例新锁 + **6/6 变异锚点转红**；AB-15 / AB-16 / AB-17 三个旧锁按新口径改写（净 0 例）。

---

## 1. 缺陷定义

改前只有"被拒绝的份额"（币种 / 条目形状 / 价格域）不给金额；"没登记"和"归因不完整"
仍以金额形状出现。合成批次（`total_tasks=1`、100 token）实测：

| 构造 | 改前 `usd_per_task` | 改前 note 的误导点 |
|---|---|---|
| 全部模型未登记 | `0.0` | 只说"未计价模型：['deepseek-flash']"，0.0 读作"没花钱" |
| 已登记 + 未登记混合 | `3.2999999999999996e-05` | 部分和冒充全额 |
| 有 token 但无 `by_model` | `0.0` | 同时声称"未计价模型：无"，掩盖归因缺口 |
| `by_model` 合计 0 / `total_tokens` 100 | `0.0` | 按错误分母算出的和 |
| `total_tasks=0` | `0.0` | 没有分母，仍给出"每任务金额" |
| 有任务但零 token 行 | `0.0` | 与"确实零消耗"同形（本轮判为完整零，保留） |

真批次三臂的 `by_model` 合计与 `total_tokens` **逐位相等**（delta 0），所以改前读数没有
暴露这条缺陷——它是构造性缺口，不是已发生的错账。

## 2. 处置

`_cost_per_task` 在聚合 `by_model` 后先判定归因完整性：

```python
model_tok_sum = sum(model_tok.values())
attribution = None
if tok > 0 and not model_tok:
    attribution = "no_model_attribution"
elif model_tok and model_tok_sum != tok:
    attribution = f"token_attribution_mismatch:{model_tok_sum}/{tok}"
```

- 未登记模型不再跳过计价后继续求和：进入 `gaps`，机制名 `model_unregistered←<模型>`；
- `gaps` 非空或 `blocked` 非空 ⇒ `usd_per_task=None`，note 追加
  `；无金额机制：… ⇒ $/task 无金额（不是 0）`；
- `n_tasks == 0` ⇒ `(0.0, None, "无任务 ⇒ $/task 无金额（不是 0）")`；
- `tok == 0` 且 `by_model` 为空 / 合计为 0 ⇒ `0.0` 仍是完整和（没有可漏计的份额）；
- 既有 `计价被拒：<code>←<模型>` 段保持不变，两类机制同名同形。

机制词汇与报告侧 `emse_stats_report.cost_effectiveness_block` 的 `model_unregistered`
一致（新锁跨文件断言，防漂移）。

渲染侧无需新分支（AB-15a 起 `None` 已印 `—（无金额）`），只在"口径纪律"节补一条
完整性要求。注意：真实批次没有任何机制，note 文本也逐字节不变。

## 3. 真批次不变量

| 臂 | tokens/task | `by_model` 合计 | `total_tokens` | `usd_per_task` |
|---|---|---|---|---|
| aitester | 26114.854406130267 | 6815977 | 6815977 | `0.025884977011494247` |
| plain_llm | 3209.44061302682 | 837664 | 837664 | `0.003358973563218391` |
| plain_llm_df | 4223.103448275862 | 1102230 | 1102230 | `0.004543231034482759` |

三臂 note 均为 `价目加权（in:out=…）；未计价模型：无`，与改前逐字节相同。
受 `SHA256SUMS` 保护的 `STATS_EXTENSIONS.json` / `.md` 与 P-1 归档 README 均未重写。

## 4. 回归锁

新增 `tests/test_experiments_cost_completeness_ah.py` **15 例**：

| 组 | 例数 | 覆盖 |
|---|---|---|
| `TestIncompleteSumsAreNotAmounts` | 10 | 全未登记；混合；无 `by_model`（键缺席 / 空对象）；合计不符（90/100、0/100、100/0）；真零 ×2；无任务；完整覆盖仍给金额 |
| `TestRealBatchUnchanged` | 2 | 三臂读数逐位相同；三臂归因闭合（delta 0） |
| `TestRenderAndVocabulary` | 3 | `None` 渲染为 `—（无金额）`；口径纪律写明完整性要求；`model_unregistered` 与报告侧同词 |

旧锁改写（登记口径变更，非改锁迁就失败）：

- `test_experiments_cost_rejection_ab15.py::test_unregistered_model_is_no_amount_not_a_zero_partial_sum`：
  `usd == 0.0` → `usd is None`，增断言 `model_unregistered←deepseek-flash`；
- `test_experiments_price_admission_ab16.py::test_unregistered_model_is_no_amount_not_a_partial_sum`：
  同上，保留"未登记 ≠ 计价被拒"的区分；
- `test_experiments_table_admission_ab17.py::test_ext_null_entry_is_rejected_not_unregistered`：
  键缺席从"仍有金额"改为"无金额 + `model_unregistered`"，与值 `null` 的
  `entry_not_object:NoneType` 仍可区分。

## 5. 变异验证

目标集 4 文件（AH + AB-15/16/17），基线 **298 passed / collected 298**；每次写盘前
`compile()`，还原后 sha256 断言源文件原字节、4 个测试文件 sha 未变。

| 锚点 | 回退内容 | 转红例数 |
|---|---|---|
| ah1 | 无任务分母退回 `0.0` | 1 |
| ah2 | 无 `by_model` 归因退回 `0.0` | 2 |
| ah3 | `by_model` 合计不闭合不再点名 | 3 |
| ah4 | 未登记 / 归因缺口不再阻断金额 | 10 |
| ah5 | `no_model_attribution` 改名 | 2 |
| ah6 | note 不再点名机制 | 10 |
| ctrl_h | 只改文档串（行为中性对照） | 0 |

**6/6 行为锚点转红**，collected 恒 298；对照 0 红。

## 6. 收口读数

- 登记前一跑（`make test-cov`，xdist -n 4 loadfile + `--cov`）：
  **10411 passed / 1 failed / 5 skipped**，collected **10417**，176.83s。
  唯一失败 = 基线守卫自身（BASELINE 尚未刷新；实收 10417 − 声明 10397 = 20 > 6 容差）。
- 收口确认跑（同命令）：**10412 passed / 5 skipped / 0 failed、rc=0**，177.80s。
  净增 15 例（collected 10402 → 10417）。
- 覆盖率（同一份 `coverage.xml`）：行 **18491/19015 = 97.2443%**、
  分支 **6675/7112 = 93.8555%**，与 AG **逐位相同**。本轮 `src/` 零改动
  （改动面 = `experiments/emse_stats_extensions.py` + 4 个测试文件 + 文档），
  同值不作佐证，佐证一律用改动面清单。
- ruff check / ruff format --check 本轮全部通过。
- `make gates` 全链**单独复跑三次均 rc=0**（首跑墙钟 **178s** / 链内 **173.61s**；
  终态树复跑 **180s** / **174.40s**；末次记账后验收跑 **189s** / **182.16s**，
  三次链内均 **10412 passed / 5 skipped / 0 failed**，xdist -n 4 loadfile，
  不带 `--cov`——与上面的覆盖率口径不可互换引用）；
  `json-strict`（工件 7273 份 = 严格 7271 + 2 份 A20 豁免、违规 0；
  源码 300 份、写入点违规 0）、`artifact-doc-consistency`（§1 覆盖率声明与
  `coverage.xml` 相符）、零断言（**426** 个测试文件 0 违规）、双语文档 / 文档链接 /
  基线 / env / 状态契约全部通过；AO3 英文 README 头部行锁按既定维护约定推进至
  "AH round"。（终态树复跑跨零点至 2026-10-21 00:00；本轮日期按主体实测日
  2026-10-20 登记，同 AB 轮"跨零点收口"先例。）

## 7. 边界（不得引用为「$/task 已全仓可信」）

1. **`tokens_per_task` 未同步改三态**：`n_tasks == 0` 时 token/task 仍返回 `0.0`
   （返回值类型保持 `float`），本轮只收口美元金额；note 已写明"无任务"。
2. **`by_model` 形状坏仍会崩**：`by_model` 为 `null` / 非对象时 `.items()` 抛异常，
   不在 AH 判据内（AH 只判键缺席、合计不符）；登记待后续轮次。
3. **只核对 `by_model` 合计 vs `total_tokens`**：`input_tokens + output_tokens` 与
   `total_tokens` 是否自洽不在本轮判据内。
4. **"未登记"仅指键缺席**：值 `null` / 非对象条目走 AB-16/17 的条目谓词，
   机制名不同但同样不产生金额；两条路径都不得被读成"没花钱"。
5. **`tok == 0` 不拒绝**：零 token 的完整和是真实 `0.0`；若上游漏记 token，
   这里无法与"确实零消耗"区分，本轮不臆造第三条判据。
6. **note 的旧 `未计价模型：…` 段保留**：新增机制段是追加披露，不替换旧词；
   读者不得只看旧段就断言"没有缺口"。
7. **归档报告不重写**：真批次 note 与金额逐字节不变由锁执行；历史报告不回写。

## 8. 复算命令

```bash
# 目标集（AH 15 + 三处旧锁，共 298 例）
.venv/bin/python -m pytest tests/test_experiments_cost_completeness_ah.py \
  tests/test_experiments_cost_rejection_ab15.py \
  tests/test_experiments_price_admission_ab16.py \
  tests/test_experiments_table_admission_ab17.py -q

# 真批次三臂读数
.venv/bin/python - <<'PY'
from experiments import emse_stats_extensions as ext
for arm in ("aitester", "plain_llm", "plain_llm_df"):
    print(arm, ext._cost_per_task(ext.MAIN_BATCH_FILES, arm))
PY

# 全量 + 覆盖率（CI 同口径）
make test-cov
```
