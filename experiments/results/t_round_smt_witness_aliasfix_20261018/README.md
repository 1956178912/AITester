# T3c：spec_smt 后件 `result`→`r` 别名缺口修复 + 零 LLM 复跑见证批

> 修复：`src/specs/spec_smt.py::_collect_post_constraints` token 感知别名归一
> （仅后件/不变式组；签名参数名为 `result` 时不归一；前件路径零变化）。
> 复跑：与 T3b **同任务集/同材料/同通道/同超时/同单子句 API**，差异仅 src 修复。
> 零 LLM（0 调用 / 0 USD / 不联网）；预注册 `PREREG_ALIASFIX.md` 跑前冻结。

## 0. 结论

- **修复有效性（C1–C5 全满足）：`True`**
- C1 可达/可解上升：reached 19 → **27**（+8）；sat 19 → **27**（+8）
- C2 别名字句去向：旧批 alias 子句 all50=**110** / primary=104；matched=**110** / unmatched=**0**；纯别名子集 reached=8/13
- C3 语义安全：solver_exception=0；单子句 unsat 0→0；全组一致性 unsat 任务=0（pass=True）
- C4 逐子句复算：True；C5 T3b 目录未变：True
- **T3b 结论不变**：T3b（`t_round_smt_witness_20261018/`）保留为 **pre-fix 基线**，其机制层 pass / 关联层无对照结论按 pre-fix 口径保留；**post-fix 口径数字以本批为准**。

## 1. 主对比表（主判定集 41；D1=184 不变）

| 指标 | T3b pre-fix | T3c post-fix | Δ |
|---|---:|---:|---:|
| 非空评估子句 D1 | 184 | 184 | +0 |
| 到达求解器子句 reached | 19 | 27 | +8 |
| status `sat` | 19 | 27 | +8 |
| status `unsat` | 0 | 0 | +0 |
| status `unknown` | 0 | 0 | +0 |
| status `timeout` | 0 | 0 | +0 |
| status `error` | 165 | 157 | -8 |
| witness_rate 均值 | 0.088531 | 0.125116 | +3.66pp |
| reach_rate（pooled） | 0.103261 | 0.146739 | +4.35pp |
| timeout_rate（pooled） | 0.0 | 0.0 | — |
| 有见证任务数 | 13/41 | 16/41 | +3 |

## 2. 旧批 110 条 `result_alias_not_reached` 子句去向

- 旧批 alias error 行：all50=**110** / primary=**104**；匹配 unmatched=0

| 口径 | sat | unsat | unknown | timeout | error | reached |
|---|---:|---:|---:|---:|---:|---:|
| all50 | 8 | 0 | 0 | 0 | 102 | 8 |
| primary | 8 | 0 | 0 | 0 | 96 | 8 |

post-fix 仍 error 的归因分解（primary）：

| 原因 | 子句数 |
|---|---:|
| unsupported_call | 84 |
| unsupported_is_in_operator | 6 |
| unsupported_subscript | 6 |

按旧批子句特征分桶（primary）：

| 旧特征桶 | n | sat | unsat | error | reached |
|---|---:|---:|---:|---:|---:|
| alias_only | 13 | 8 | 0 | 5 | 8 |
| call | 61 | 0 | 0 | 61 | 0 |
| call+attr | 4 | 0 | 0 | 4 | 0 |
| call+subscript | 19 | 0 | 0 | 19 | 0 |
| subscript | 7 | 0 | 0 | 7 | 0 |

- 解读：「alias_only」桶（旧批文本无 call/subscript/attr）13 条中 8 条转 reach/sat；其余 5 条使用 `is`/`in` 比较算子（`_translate` 保守算子集不含 Is/IsNot/In/NotIn）→ 仍 error，其阻塞原因是 Compare 算子集而非别名。「call/subscript/attr」桶仍受翻译层保守算子集限制（Call/Subscript/Attribute）——这些不是别名缺口，而是分层能力边界，如实计入。

- **预注册预期偏差披露**：PREREG_ALIASFIX §4 预期 reach≈32（假设 13 条纯别名字句全部可达），实测 **27**（偏差 -5）——原因：13 条 alias_only 中 5 条使用 is / in 比较算子（`_translate` 保守算子集不支持 Is/IsNot/In/NotIn）→ 仍 error；其阻塞原因是 Compare 算子集而非别名。预注册 §4 预期仅用于偏差披露，不参与判定（C1 判据为 > 旧批 19）。

## 3. 语义安全审计（风险 guard）

- solver_exception：0（pass=True）
- 单子句 unsat：pre-fix 0 → post-fix 0（pass=True）
- 全组一致性探针（expr 通道 post+inv 约束组）：pre-fix 模拟 {'skipped': 39} → post-fix {'sat': 2, 'skipped': 37}；新增 unsat 任务=0（pass=True）
- NL 通道（生产 `_collect_post_constraints` 实际消费的键）全组探针：{'skipped': 41} → {'skipped': 41}（生产 NL 通道材料多为中文散文，极少可编译 → 生产行为变化面很小）

## 4. 限制与口径

1. 本批是**同口径 pre/post 复跑对比**（非随机对照试验）；pre-fix 基线为 T3b 归档工件，post-fix 复用同一运行器纯函数，差异仅 `src/specs/spec_smt.py`。
2. 单子句批次口径（每子句单独交公开 API）用于观测可解性；生产全组一致性路径另有 `_infer_sorts` 的「任一无翻译子句 → 整组 skipped」全有全无门，故 post-fix 生产侧实际新增可判定任务极少（见 §3 探针）。
3. 翻译层保守算子集（Call/Subscript/Attribute）未在 T3c 变更：110 条 alias 子句中含这些构造者仍为 error/untranslatable_*，属能力边界而非别名缺口。
4. 关联层（detection）不在 T3c 范围：T3b 已按预注册判为无对照，本批不重新分桶/不做推断。
5. 零 LLM；墙钟 0.134s；z3 5.1.0。

## 5. 复跑

```bash
.venv/bin/python experiments/results/t_round_smt_witness_aliasfix_20261018/_helpers/run_aliasfix_batch.py
python scripts/gates/checksum_results.py --write --results-dir experiments/results/t_round_smt_witness_aliasfix_20261018
python scripts/gates/checksum_results.py --verify --results-dir experiments/results/t_round_smt_witness_aliasfix_20261018
```

## 6. 产物

- `PREREG_ALIASFIX.md`
- `PREFLIGHT.json`
- `PER_CLAUSE.jsonl`
- `TASK_LEVEL.json`
- `ANALYSIS_REPORT.json`
- `COMPARISON.json`
- `README.md`
- `RUN_SUMMARY.log`
- `SHA256SUMS`
- `_helpers/run_aliasfix_batch.py`

