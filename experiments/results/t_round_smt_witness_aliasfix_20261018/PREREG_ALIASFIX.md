# T3c 预注册（跑批前冻结）：spec_smt 后件 `result`→`r` 别名缺口修复 + 零 LLM 复跑见证批

- **冻结时间**：2026-10-18 09:12（+0800），在**复跑批次任何逐子句求解调用之前**落盘。
- **性质**：语义正确性修复的**批后复验**（单臂观测，无对照臂；A/B 为"同一批次口径下
  pre-fix 归档基线 vs post-fix 复跑"，非随机对照试验）。
- **依据**：T3b 机制发现（`experiments/results/t_round_smt_witness_20261018/`）+
  Lead task-5；设计依据仍为 `docs/design/smt_witness_batch_plan.md`。
- **预算**：零 LLM（0 次 LLM 调用、0 USD、不联网）。
- **锚点**：git HEAD `a93c1f60ee31b9582e0146f73e3038e6ce0f01a1`。

## 1. 修复内容（冻结；只改 `src/specs/spec_smt.py`）

T3b 归因：后件/不变式子句普遍写 `result`（SpecIR 表达式通道契约），而
`spec_smt._collect_post_constraints` 自由变量域只有 `{"r"}` → 含 `result` 的子句在
`_infer_sorts` 的"自由名必须属于域"门被整体保守拒绝（T3b：pre-fix 批 110/166 条
expr error 子句，占 66%，`result_alias_not_reached`）。

修复（只动后件/不变式组，前件路径零变化）：
1. `_ResultAliasNormalizer(ast.NodeTransformer)`：只把表达式树中的
   `Name(id="result")` 改写为 `Name(id="r")`（字符串字面量 / 属性名 / 关键字参数名
   不命中——token 感知，非子串替换）；
2. 触发条件：**`result` 不在签名参数中**；参数名确实叫 `result` 时**不归一**
   （保持历史行为：`result` 是输入变量）；
3. 排序推断/翻译使用归一后文本；`usable_bool` 保留**原始子句文本**（可解释性，
   UNSAT 告警绑定用户原句）；
4. 解析失败 / `ast.unparse` 异常 → 保守回退原文；无 `result` 出现 → 原样返回
   （`r` 形式子句逐位不变）；
5. 白名单拒绝 / 非表达式子句仍走既有保守拒绝路径（归一不放行坏子句）。

## 2. 复跑口径（冻结，与 T3b 逐项同口径）

| 项 | 冻结值 |
|---|---|
| 任务清单 | T3b 同源：`emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json::results.plain_llm_df_spec.details`（50 行；**主判定集 = 41 缺陷程序**，9 个 `*_test` 驱动仅扩展披露） |
| 材料 | `emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json` 内容寻址查表（sha256 校验），与 T3b 同一锚表/同一源码根 |
| 子句通道 | SpecExpr `*_expr` 优先 / NL 回退（同 `_select_compile_channels` 口径）；单子句单 spec 喂 `check_precondition_vacuity` / `check_postcondition_consistency` |
| 参数 | `SPEC_SMT_TIMEOUT_MS=5000`；`unknown` 且墙钟 ≥0.9×timeout → `timeout`；`skipped` → `error/not_reached`；异常 → `error/solver_exception` |
| 判据 | 与 T3b 完全相同的 status 枚举/映射、D1=非空评估子句、`witness_rate=sat/D1`、`reach_rate=reached/D1`、`timeout_rate=timeout/reached` |
| 运行器 | `experiments/results/t_round_smt_witness_aliasfix_20261018/_helpers/run_aliasfix_batch.py`（复用 T3b 运行器纯函数，未改 T3b 脚本；脚本 sha256 入 PREFLIGHT） |
| T3b 目录 | **只读、不修改**：复跑前后按 T3b `SHA256SUMS` 校验其工件 sha256 未变（PREFLIGHT 记录 `t3b_untouched`）；T3b 结论（pre-fix 基线）不重写 |

## 3. 判定规则（跑前冻结，跑后不得改）

**C1 修复有效性（主判据）**：主判定集（41）上，post-fix 复跑
`status_totals_pooled.sat` **>** pre-fix 归档 **19** 且 `clauses_reached_pooled` **>** **19**
（即别名归一确实把子句送达求解器，而非只改分类）。

**C2 别名子句去向可审计（硬判据）**：T3b pre-fix 批中标记为
`error_kind="not_reached"` 且子句含 `Name result` 的逐子句行（all50=**110**、
primary=**104**），按 `(task_id, clause_sha256_16, clause_index)` 与 post-fix 复跑
逐行连接：**matched=110 / unmatched=0**；去向分解
`{sat, unsat, unknown, timeout, error+reason}` 之和 == 110（primary 之和对 == 104）。
其中"纯别名"子集（旧批文本特征无 call/subscript/attr；primary=**13**）要求
**≥1 条**变为 `reached`（预期 13 条中大多数 → sat）；含其它不可翻译构造的子句
（call/subscript/attr）预期仍为 `error/untranslatable_*`，如实计数。

**C3 语义安全 guard（任一触发 → 停止并报告，不硬推）**：
1. post-fix 复跑 `solver_exception` 计数 > 0；
2. post-fix 复跑单子句 `unsat` 计数 > pre-fix 归档 0（单子句自相矛盾若出现须逐条
   绑定子句文本并判定是"真实 finding"还是"归一错改"）；
3. 全组一致性探针（expr 通道 post+inv 作为约束组）：post-fix 出现 `unsat` 任务数
   > pre-fix 模拟 0；若出现且可逐子句绑定真实矛盾 → 作为 finding 披露并暂停
   进一步解释（不判修复失败），>2 个任务 → 停止并报告；
4. 定向回归 `pytest tests/test_smt_witness_batch.py tests/test_spec_smt_result_alias.py
   tests/test_spec_smt.py tests/test_spec_smt_matrix.py tests/test_spec_smt_more_branches.py
   tests/test_spec_postconsistency.py tests/test_spec_refine.py tests/test_spec_ir_v2.py -q`
   非全绿。

**C4 逐子句复算（硬判据）**：K 行逐子句重聚合 == TASK_LEVEL 任务行 == 池化桶计数（0 mismatch）。

**C5 T3c 不改 T3b 结论**：T3b 目录 sha256 未变；T3b 的机制层 pass / 关联层无对照结论
**按 pre-fix 口径保留**，T3c 只报告 post-fix 数字并注明"post-fix 口径应引用 T3c"。

## 4. 预期（跑前声明，仅供事后偏差披露，不参与判定）

- 单子句可解数 19 → 预期约 32（+13 条纯别名字句；含 call/subscript/attr 的
  子句仍不可翻译）；
- `reach_rate` 0.103261 → 预期约 0.17（D1 不变 184）；
- `unsat`/`timeout`/`unknown` 预期仍为 0（单子句公式极小；前次批实测 timeout=0）；
- 110 条别名去向预期：sat ≈ 13-19 条（纯别名 + 少量可翻译混合），其余
  `error/untranslatable_call|subscript|attribute`；
- 全组一致性探针预期：pre-fix 39 skipped / 2 empty → post-fix 37 skipped / 2 sat
  （**跑前风险预检已做**：仅 expr 通道全组一致性探针，未运行逐子句批次；0 unsat）。

## 5. 零 LLM / 范围 / 纪律

- 0 次 LLM 调用、0 USD、不联网；只读本地工件与本地源码；
- 只改 `src/specs/spec_smt.py` + 新测试 `tests/test_spec_smt_result_alias.py` +
  本结果目录；不碰 docs/BASELINE/CHANGELOG/登记册；不 git commit；
- 禁止全量 pytest（B2 主批次在跑，CPU 争用会污染测量）；只跑冻结的定向测试集；
- 若修复后出现语义风险（C3 任一）→ **立即停止并报告**，不硬推。

## 6. 产物

`experiments/results/t_round_smt_witness_aliasfix_20261018/` 下：
`PREREG_ALIASFIX.md`（本文件）、`PREFLIGHT.json`、`PER_CLAUSE.jsonl`、
`TASK_LEVEL.json`、`ANALYSIS_REPORT.json`、`COMPARISON.json`、`README.md`、
`RUN_SUMMARY.log`、`SHA256SUMS`（生成后 `--verify`）。
