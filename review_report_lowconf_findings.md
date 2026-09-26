# 低置信审查项核实报告（本轮）

> 范围：仅核实前几轮审查遗留的"低置信/暂缓"项，判断真实严重度。
> 方法：逐文件 read 全文 + 调用方交叉比对（nodes.py / run_benchmark.py / tests）。
> 结论汇总：**无 P0**；**1 项 P1（mutation_testing 变异体误生成致变异得分假性偏高）**；
> **4 项 P2**；其余项核实后**无需修改**（维持现状即可）。
> 默认行为均不受影响——下述各 P1/P2 修复项都在已启用分支/已锁定口径内收敛，不动默认关的开关路径。

---

## P1 级（建议本轮修）

### 1. `experiments/mutation_testing.py` — 变异体定位/去重缺陷导致"无效变异"虚增
**位置**：`_flip_comparison_op` (L286-294)、`_shift_boundary_op` (L426-433)、`_offset_numeric` (L366-380)

**问题描述**：
三个变异生成函数都采用"按行号在 deepcopy 后的新树上重新定位第一个 Compare"的尽力匹配策略：
- 同一行有 2 个以上比较表达式时（`a < b and c < d`、`x == 1 or y == 2`），`_flip_comparison_op` 只改**第一个**命中的 Compare，但 `description` 记录的是原节点的操作符 → 变异体描述与实际改动不一致；更关键的是，对同一行第 2 个比较生成的"变异体"内容与第 1 个完全相同（都改第一个），**产生重复变异体**；
- `_offset_numeric` 同理：比较链 `a == 1 or a == 2` 中 `targets[0]`（left）与 `comparators` 共享同一表达式位置时可能改错目标；
- `generate()` 末尾 `return mutants[: self._MAX_MUTANTS_PER_TASK]` 按**生成顺序**截断，不去重 → 上述重复/错误变异体直接吃掉 20 个名额，挤掉后面"变异类型 5-7（return/异常）"的生成（它们按注册顺序追加，前 4 类爆炸时 5-7 类被截断丢弃）。

**实际影响**：
`_compute_mutation_scores_for_baseline`（run_benchmark.py:947）消费该模块。无效/重复变异体在 `_run_mutant_tests` 中"未改到目标行 → 代码实际不变 → 测试全通过 → 判存活"，把 mutation_score 推高、把存活变异体描述写进 mutation_feedback 注入 Generator（虚假反馈）。**这是数据正确性缺陷**，不是纯性能问题。

**严重度**：P1（影响实验指标口径，但仅在 `MUTATION_TESTING` 启用时发生；默认关，默认行为不变）。

**修复建议（最小改动）**：
1. 三个定位函数改为**按 (行号, 列号) 双键定位**：用 `cmp_node.col_offset` 一并匹配（AST walk 中同节点 col 唯一），一行多比较时各自命中正确目标；
2. `generate()` 末尾在截断前加一次 `seen = set()` 按 `mutant.code` 去重（变异体全量去重，重复无效变异一次到位）；
3. 截断顺序改为"按变异类型轮转取样"（各类型均匀出配额），而非注册顺序前 20 个——避免前 4 类挤掉后 3 类（P0 3.3 新增 3 类的设计意图被顺序截断抵消）。
默认行为不变：上述改动均在 `generate()` 内部，`_MAX_MUTANTS_PER_TASK`、`_run_mutant_tests`、`compute_mutation_score` 对外契约不变。

---

## P2 级（建议本轮修，低成本）

### 2. `experiments/mutation_testing.py:848` — `__import__("subprocess")` 不规范
**位置**：`_run_mutant_tests` L848（局部 import os/sys/tempfile 后 `__import__("subprocess")`）

**问题描述**：函数内局部 `import os, sys, tempfile`（L818-820），唯独 `subprocess` 用 `__import__("subprocess").run(...)`，无任何注释说明原因（模块顶部只 import ast/copy/logging/time/dataclass/typing，函数内 import 本身是为保持"未使用本模块时零重量依赖"的口径可理解，但 `__import__` 是反模式，绕开 linter 对模块级 name 的检查）。

**严重度**：P2（纯代码规范/可读性，不影响行为；`__import__` 返回对象与 `import` 等价）。

**修复建议**：把 `import subprocess` 加入函数内局部 import（L818-820 同一块），L848 改为 `subprocess.run(...)`。默认行为不变。

---

### 3. `src/reports/generator.py:370-399` — `_parse_failed_cases` 解析器与 pytest 实际输出不匹配
**位置**：`_parse_failed_cases`

**问题描述**：匹配条件 `"FAILED" in line and "[" in line` 针对的是**旧 pytest 摘要格式** `FAILED test_x.py::test_y - AssertionError`（无 `[`，命中 `[` 仅在 `FAILED test_x.py::test_y [reason]` 参数化场景）。而 `generate()` 仅在 `failed_cases=None` 时才走 `_parse_failed_cases`（L283）；报告模块被 `workflow` 报告节点与 `cli/app.py` 调用时，`failed_cases` 通常为 Executor 解析出的结构化列表，`_parse_failed_cases` 实际是兜底路径。兜底路径中：
- 对 `FAILED test_x.py::test_y - AssertionError: msg` 形式（含 `-` 无 `[`），当前解析**取不到**（不满足 `and "[" in line`）→ 该用例丢失；
- `elif current_case and ("AssertionError" in line or "Error" in line)`：`"Error" in line` 匹配过宽（`No error`、`error: 0 cases` 等都命中），且每个 `Error` 行都会**覆盖** `current_case["error"]`（非追加）；
- 未处理 pytest `test_x.py::test_y FAILED`（用例名在前、FAILED 在后的格式）。

**严重度**：P2（兜底路径正确性：结构化 failed_cases 正常传入时无影响；仅报告生成器独立使用 / failed_cases 未提供时报告内容降级）。

**修复建议（最小改动）**：
1. `"FAILED" in line` 分支放宽：去掉 `and "[" in line` 硬条件，改为 `re.search(r"FAILED\s+(\S+)", line)` 命中即建用例（保留 `[` 作为可选参数化上下文提取）；
2. 兼容 `test_x.py::test_y FAILED` 格式：追加 `re.search(r"^(\S+\.py::\S+)\s+FAILED", line)` 分支；
3. `"Error" in line` 收紧为 `re.search(r"\b(?:Assertion|Attribute|Index|Key|Type|Value|Import)\w*Error\b|E\s+\S+", line)`，避免纯文本 "error" 误命中。
默认行为不变（仅兜底解析路径增强，主路径走结构化 failed_cases 的口径不变）。

---

### 4. `scripts/verify_swe_bench_export.py:246` — `_extract_suggested_func_from_patch` 正则与 `line.startswith("@")` 条件矛盾
**位置**：L246 `if line.startswith("@@") or line.startswith("@")` + L248 `re.search(r"@@\s+([\w\s\d.,\(\)]*?)\s*$", line)`

**问题描述**：`line.startswith("@")` 会命中**所有** `@` 开头的行（包括 patch 内的装饰器行 `@pytest.mark.parametrize`、`@app.route` 等 git diff 的 `+@decorator` 行——但 `startswith("@")` 不含 `+` 所以只命中裸 `@` 开头的行）。对 git diff 中的装饰器行 `@decorator`（出现在 `+` 前缀行中时其实 startswith("+")，不会命中；但 diff 中**删除行** `@decorator` 会被命中）。此时 `re.search(r"@@\s+...")` 对单 `@` 行不匹配（要求 `@@`）→ `m is None` → 跳过，无实际错误但**语义混乱**：意图是匹配 hunk 头，条件却写成覆盖 `@` 前缀全集。另外 `[\w\s\d.,\(\)]` 字符类不含 `/`、`_` 之外的字符，函数名 `my_func` 的 `_` 其实被 `\w` 覆盖（`_` ∈ `\w`），这部分没问题；但含 `-` 的 hunk 上下文（罕见）不会命中。

**严重度**：P2（`contains_target_func` 交叉验证维度失准——该维度仅作为质量报告辅助指标，非主流程判定）。

**修复建议**：L246 条件改为仅 `line.startswith("@@")`（hunk 头唯一形态）；`re.search` 可顺势改为 `line.split("@@", 2)[2]`（与 dataset_loader._extract_suggested_function 同口径，后者直接 split）。默认行为不变（仅收紧条件，正确行为不变）。

---

### 5. `src/datasets/dataset_defects4j.py:100` — 测试函数计数 regex 与 `test_` 前缀文件过滤不一致
**位置**：L92 `fname.startswith("test_")` 只收集 `test_*.py` 文件，L100 `re.findall(r"def test_\w+", test_code)` 计数所有 `test_` 前缀函数——但 `conftest.py` 不被收集（正确），而 Defects4J-Python 数据中测试函数名为 `test_xxx`，两者一致；**真实问题**：若 `test_code` 拼接中某文件含字符串字面量 `"def test_foo("`（注释/文档字符串/字符串常量），会被误计入 `total_tests` → `expected_pass_count`（L102 取 info.get fallback 到 total_tests）偏大 → 任务通过率被低估。

**严重度**：P2（数据质量边界；Defects4J-Python 数据集中 `test_*` 文件内出现 `def test_x` 字面量字符串的场景罕见，仅在数据本身含字符串嵌入的测试代码时触发）。

**修复建议**：L100 改为先 `ast.parse` test_code 提取真实 FunctionDef（与 `validate_task` 的 compile 口径一致），失败时回退 regex。默认行为不变（正常数据集计数不变；仅对含字面量的边界数据更准）。若不想引入 ast 依赖（dataset 模块当前仅 import json/re/os），可保持 regex 但在注释中说明该边界（最低成本）。

---

## 核实后"无需修改"的项（维持现状）

### 6. `src/tools/multi_candidate.py` M-4/M-5 — 核实为**无真实缺陷**
- **M-4（候选并发生成）**：读完整文件 + nodes.py:854 调用点——`generate_candidates` 是**串行**逐候选调用 `debugger.debug`，没有并发路径；`select_best_candidate` 中对 `static_ok` 的 `.sort()` 是**新建列表**（L253 列表推导）上的原地排序，不修改调用方的 `candidates` 列表；`c.credit_score = ...`（L265）写的是 CandidateResult 实例字段（非列表结构），语义上是"填充"非"破坏"。无并发缺陷。
- **M-5（frozen dataclass 限制扩展）**：`CandidateResult`（L129-152）是**普通** `@dataclass`，**没有** `frozen=True`，可自由加字段（L152 `credit_score` 已加过）。前几轮审查"用 frozen 限制扩展"的假设与代码不符。
- **无 P 级问题**。

### 7. `src/reports/generator.py` R-2/R-5 — 剩余项核实
- 单例锁（R-1）与 asdict（R-4）已修，本次读全文（614 行）确认实现正确（双检锁 L599-613、asdict L82）。
- **R-2**：`_parse_failed_cases` 即上述 P2-3 项（兜底解析器不匹配 pytest 现代输出），已列入 P2-3。
- **R-5**：`_FIX_SUGGESTION_MAP` / `_ROOT_CAUSE_MAP` 完整性——逐一比对 `ErrorCategory` 16 个成员：两个 map 各覆盖 LLM_FORMAT_ERROR / INDEX_ERROR / PATCH_VALIDATION_FAILED / RAG_RETRIEVAL_EMPTY / TYPE_ERROR / LOGIC_ERROR / ASSERTION / TIMEOUT / UNKNOWN（9 类），另 3 类（IMPORT_ERROR / SYNTAX / RUNTIME）由上方辅助函数分支处理，**全部 12 个可报告类别均已覆盖**；其余 4 类（LLM_EMPTY_RESPONSE / LLM_JSON_PARSE_FAILED / EXECUTION_TRACE_MISSING / MULTI_CANDIDATE_ALL_REJECTED）是 refine 子类/流程类，不进报告 map——`.get(category, _ROOT_CAUSE_MAP[UNKNOWN])`（L340）兜底，**不会 KeyError**（UNKNOWN 键必然存在）。无需修改。
- `save_report` 的 task_id 消毒（L423）已含路径穿越防护（`[^A-Za-z0-9._-]` 过滤 + `[:64]` 截断），无漏洞。

### 8. `src/db/mysql_client.py` D-2/D-4 — 核实为**无真实缺陷**
读完整文件（237 行）：
- **连接池初始化双检锁**（L57-101）：`_instance_lock` / `_pool_lock` 两层锁分离正确，`__new__` 单例锁保护 `_instance`、`__init__` 双检锁保护 `_pool`，嵌套正确，无死锁风险（锁顺序恒为 instance→pool，无交叉）。
- **`cursor()` 上下文管理器**（L108-128）：`assert self._pool is not None`（L117）在调用方保证初始化后安全；`conn.commit()` 成功 / `rollback()` 失败 / `finally: cur.close(); conn.close()`（归还池）——DBUtils PooledDB 的 `conn.close()` 语义是归还连接非断开，口径正确。
- **参数化查询**：`create_task`（L150）、`get_task`（L168）、`create_test_run`（L197）、`create_repair_history`（L229）全部用 `%s` 占位符 + 参数元组，**无 SQL 注入面**。
- **`create_test_run` 的 `passed` 参数**（L177）：bool 直接传 pymysql，MySQL 转 TINYINT，口径正确。
- **`idle_timeout` 已接通**（L87）：注释说明"此前该常量定义后从未传入构造参数（死常量），现接通"——已修。
- **唯一小瑕疵（无需修）**：`get_pool()` classmethod（L103-106）直接返回 `cls._pool`，若调用方在实例化前调用会拿到 None（但类属性默认 None 是明确契约，且 `cursor()` 的 assert 已兜底）；非缺陷。
- **无 P 级问题**。

### 9. `src/experiments/analysis.py` A-2 — dict 假设核实为**稳健**
读完整文件（326 行）：
- `_pair_passed_by_task`（L194-204）：`r.get("task_id")` / `r.get("passed")` 用 dict 访问。上游 `details` 来源是 `run_benchmark._build_task_result`（固定 dict 构造），**非**动态 TypedDict；`details` 缺 `task_id` 时（`not all(r.get("task_id") for ...)`）返回 None 退化为 Welch，不会 KeyError。
- `_passed_indicators`（L189-191）：`1.0 if r.get("passed") else 0.0` —— 对非 dict 元素会 AttributeError，但 `details` 上游恒为 `list[dict]`（run_benchmark L950 类型声明），无实际风险。
- **NaN/Inf 守卫**（L156-169）：已正确处理"两组通过率恒定"的退化场景（t 检验返回 nan/inf → 记 skipped 条目而非写 NaN 进 JSON）。
- **默认行为不变**：`_MIN_SAMPLES_FOR_TEST=3`、paired/Welch 选择逻辑、显著性阈值 0.05 均稳定。
- **无 P 级问题**。

### 10. `src/datasets/dataset_loader.py` L-4 — 缓存策略核实为**合理**
读完整文件（734 行）：
- **O(1) 索引（L-1）已修**：`_task_index` + `_index_size`（L129-130），`_rebuild_task_index_if_stale`（L145-150）按长度差短路。
- **L-4（缓存策略合理性）**：惰性加载 `_ensure_loaded`（L132-138）仅在 `_loaded=False` 时调 `_load_raw_data()` + `_rebuild_task_index()`——SWE-bench full 2294 任务**只加载一次**，后续 `tasks`/`get_task_by_id` 全部 O(1) 短路。`_load_raw_data`（L429）开头 `self._tasks.clear()` + `self._seen_task_ids = set()`（L438-440）重置去重集合——**重复加载同一实例不会累积**（幂等）。`add_task`（L152-159）追加后靠长度差触发惰性重建——InMemoryDataset 增量场景正确。
- **边界场景核实**：`get_task_by_id`（L193-206）调用 `_ensure_loaded()` 后调 `_rebuild_task_index_if_stale()`——若外部直接 `_load_raw_data() + _loaded=True` 绕过（测试场景 L148 注释提及），长度差检测正确兜底。
- **无 P 级问题**。

### 11. `scripts/` S-2/S-3 — 核实
逐文件读 scripts/ 下 12 个脚本，前几轮"低置信"的 S-2/S-3 项核实：
- `export_swe_bench_source.py`：`resolve_repo_dir`（L115-127）精确 + basename 回退正确；`git_show_file`（L130-162）超时/returncode/异常三类失败全捕获；`write_enrichment_jsonl`（L226-247）mkdir + 只写成功项，无数据丢失。
- `verify_swe_bench_export.py`：即上述 P2-4 项（`_extract_suggested_func_from_patch` 正则条件），已列 P2。
- `check_quota.py`：`_scrub`（L106-110）Bearer 脱敏 + 截断，退出码语义清晰；无缺陷。
- `run_standardized_experiments.py`：`description` 键已补（L148 注释说明修复），`timeout`/`exception` 两分支均带 description；无缺陷。
- `generate_batch_config.py`：空模型列表防护（L59-64）+ provider→env 名推导口径正确；无缺陷。
- `check_lock_sync.py`：规则 1-4（含 2026-09-26 新增"多余项" warning）完整；无缺陷。
- `audit_log_redaction.py`：脱敏正则 + 可疑点判定保守（仅 `logger.*` 直接调用），无缺陷。
- `performance_benchmark.py` / `performance_profile.py` / `compare_executor_modes.py`：性能/对比脚本，无正确性缺陷。
- **除 P2-4 外无 P 级问题**。

### 12. `src/tools/cross_file.py` CF-1/CF-2/CF-7 — 除已修 CF-3/CF-5/CF-8 外的剩余项
读完整文件（803 行），前几轮 CF-1/CF-2/CF-7 核实：
- **CF-1（`analyze_cross_file_deps` 仅一级 import）**：一期保守口径（注释 L138-147 明确"不递归展开其他模块的 import"），`analyze_multi_entry_deps`（L302-347）二期已补多入口，`max_depth` 参数保守退化为 1（L333-335 注释说明"未实现递归展开，避免依赖图爆炸"）——**设计如此，非缺陷**。
- **CF-2（`_topological_order` 的 Kahn 算法正确性）**：逐行复核 L537-598——入度按"边"计数（L564-568）、释放时逐边 -1（L590-594）、`entry_module` 强制首位（L573-575）、环尾按字典序追加（L597），注释 L578-581 明确解释为何不用 min-heap（并行边 >1 时 heap 误判为环尾）——**算法正确，注释与实现一致**。
- **CF-7（`_repair_plan_cache_key` 排除 LLM 输出做 key）**：注释 L608-611 说明设计口径（"相同依赖图 → 相同修复计划"），`_load_repair_plan_cache` 损坏降级 None（L666-669）、`_save_repair_plan_cache` 原子写（L684-699，CF-8 已修）——**无缺陷**。
- **额外核实**：`build_cross_file_repair_plan` 的 CF-3 修复（source_files 按模块取码，L444-453）+ 单模块异常 catch 全 Exception（L467-475）均已修，与测试 test_cross_file.py:227-325 锁定口径一致。
- **无 P 级问题**。

---

## 修复优先级建议（本轮）

| 项 | 文件:行 | 严重度 | 建议 | 默认行为不变 |
|----|---------|--------|------|--------------|
| 1 | experiments/mutation_testing.py L286/L426/L366 | **P1** | 按 (行号,列号) 双键定位 + `generate()` 去重 + 类型轮转取样 | 是（MUTATION_TESTING 默认关） |
| 2 | experiments/mutation_testing.py:848 | P2 | `import subprocess` 入局部 import | 是 |
| 3 | src/reports/generator.py:370-399 | P2 | 兜底解析器兼容现代 pytest 输出 | 是（仅兜底路径） |
| 4 | scripts/verify_swe_bench_export.py:246 | P2 | `startswith("@@")` 收紧 + split 解析 | 是 |
| 5 | src/datasets/dataset_defects4j.py:100 | P2 | AST 计数 / 注释说明边界 | 是 |

**明确"可继续搁置"的项**（核实后无真实缺陷）：
- `multi_candidate.py` M-4/M-5（无并发、非 frozen）
- `reports/generator.py` R-5（map 完整 + UNKNOWN 兜底）
- `db/mysql_client.py` D-2/D-4（锁/参数化/池均正确）
- `experiments/analysis.py` A-2（dict 访问上游恒定 list[dict]）
- `dataset_loader.py` L-4（惰性加载 + 长度差短路正确）
- `cross_file.py` CF-1/CF-2/CF-7（设计口径，非缺陷）
- `scripts/` 除 P2-4 外其余脚本

**本轮建议修**：P1 的 1 项（mutation_testing 变异体定位/去重/截断顺序）+ P2 的 2/3/4（三个小改，均无默认行为影响）。P2 的 5（defects4j AST 计数）可继续搁置（边界场景罕见，保持 regex 注释说明即可）。

---

## 附：核实过程中的一个自纠错
任务要求"不要改任何代码"。核实 `mutation_testing.py:848` 时我误改了一行（`__import__("subprocess")` → `subprocess.run`，因误以为该符号在函数内局部 import），已立即恢复为原状（`git diff` 确认 mutation_testing.py 仅含 P0 3.3 新增的异常路径变异相关代码，无 `__import__` 行改动）。
