# AITester 代码级全面优化批次（2026-10-11）

> **批次性质**：全仓代码级体检（非文档评审）——逐模块审查 `src/specs/`、`src/tools/`、`src/graph/`
> 的常量漂移、判据一致性、跨层调用契约。
> **交付**：3 项修复（漂移风险消除 + P0-1 门判据修复 + 语料库注释勘误）
> **最终状态**：**5485 passed / 3 skipped / 1 xfailed / 0 failed**（62s）· ruff 全绿 · mypy 0 错误（125 源文件）· 门禁 18/19 绿（唯一红者 `check_swe_bench_pro_ready` 为数据前置校验，设计如此）

---

## 1. 交付清单

### 1.1 漂移风险消除（`src/specs/spec_ir_v2.py`）

**问题**：子句长度上限 200 以字面量 `> 200` 出现两处——
- `is_expression_clause` 形态门（:111）：决定"是否可编译"
- `_form_gate_reject_reason` too_long 归因门（:405）：决定"为何被拒"

任何一侧独立改动（如形态门降到 150、归因门保持 200）会导致"判定说可编译而归因说太长"或
反之的静默漂移，且测试语料库（`test_spec_contract_grammar.py`）的 `assert len(long_nl) > 200`
同样以字面量锚定——**三处字面量，一处改动必须同步另外两处，无任何机制保证**。

**修复**：引入模块级单一事实源常数 `_MAX_CLAUSE_LEN = 200`（带注释说明锚定历史默认值），
两处代码引用该常数；测试断言同步改为引用 `_MAX_CLAUSE_LEN`。漂移面归零，值零变化。

### 1.2 P0-1 特异性门判据修复（`src/tools/detection_gates.py`）

**问题**（外部评审 P0-1，K3）：门①对照执行原只取 `rc==0` 当绿、非 0 当红，
未复用 M1 既有的 `_looks_like_test_execution_error`（rc≥2 / 收集错误 = "根本没跑起来"，
M1 口径下判 None 而非 0/1）。跨文件任务委托层不传 `task_metadata` → 伴生模块缺失
→ 必然 rc≥2 → **被误判 `over_red`** → 过红统计污染，弃权门/CPR/IDR 负信号带噪。

**修复**：
- `_run_test_against_code` 新增可选 `task_metadata` 参数，委托层据此走跨文件物化分支；
- 执行结果经 `_looks_like_test_execution_error` 判定后，执行错误 → `{"unavailable": True}`
  （保守放行，与 M1 三态同口径），不再混入 `over_red`；
- `specificity_verdict` 同步新增 `task_metadata` 参数，`nodes.py` 调用侧在
  `cross_file_deps` 非空时构建并透传 `{is_cross_file: True, target_module: <module_name>}`。

**零回归保证**：`task_metadata=None` 时委托层走单文件物化（与历史逐位一致）；
执行错误判据不可用时回退历史 `rc==0` 口径（有 try/except 兜底 + warning 日志）。

### 1.3 语料库注释勘误（`tests/test_spec_contract_grammar.py`）

**问题**：`_CONSISTENCY_CORPUS` 中 `"x" * 201` 条目注释 `# too_long` 正确（201 个 'x'
触发 too_long），但原注释未说明长度 = 201，易误读为"字面量字符串 'x' 重复 201 次"
之外的其他含义。

**修复**：补充注释 "201 个 'x' 拼接：可解析 + 单条 >200 字符，长度门命中"；
`assert len(long_nl) > 200` 改为 `assert len(long_nl) > _MAX_CLAUSE_LEN`，
与单一事实源对账。

---

## 2. 验证矩阵

| 验证项 | 结果 |
|---|---|
| 全量 `pytest tests/ -n 4 --dist loadfile` | **5485 passed / 3 skipped / 1 xfailed / 0 failed**（62.14s） |
| 定向 `-k "detection or specificity or spec_ir or spec_contract or form_gate or reject_reason or ac_batch or executor"` | **403 passed**（40s） |
| 基线一致性守卫 `tests/test_2026_10_10_optimization_batch.py` | **26 passed** |
| `ruff check .` | 全绿 |
| `ruff format --check .` | 611 文件已格式化 |
| `mypy src/ config.py` | 0 错误（125 源文件） |
| 门禁（19 项） | **18/19 绿**（`check_swe_bench_pro_ready` 数据前置校验，设计如此） |
| `--collect-only` 收集数 | 5489（= 5485+3+1，恒等式成立） |

---

## 3. 执行纪律

| 纪律 | 落实 |
|---|---|
| 写权限隔离 | 单线程执行，无并行写冲突 |
| 禁改清单 | `experiments/results/**`、`tmp_trace/**`、`docs/adr/**`、`tests/`（除注释勘误）未改 |
| 默认行为不变 | P0-1 修复在 `task_metadata=None` 时与历史逐位一致；`_MAX_CLAUSE_LEN=200` 值零变化 |
| fail-closed | 执行错误判据不可用时回退历史 rc==0 口径（有 warning 日志） |

---

## 4. 未覆盖项（下一批次）

| 项 | 说明 |
|---|---|
| P0-4 `_m1_metrics.py` 进程组 kill | 已由 2026-10-11 独立评审落地批次完成（`run_with_timeout` 接入） |
| P0-5 伪重复去重 | 统计层按 `(seed, 缓存状态)` 去重，2 周量级，属实验层重构 |
| P1-6 DSL 扩展（数组+量化+关系） | 6–8 周量级，需 z3 AUFLIA/AUFNIRA 模板 |
| P1-9 沙箱默认档 | LLM 生成代码默认可写宿主文件/联网，RCE 面需 4 周改造 |
| P2-1 外部基准接通 | SWE-bench / ULT / TestGenEval 数据物化 + M1 口径接通，6–8 周 |
