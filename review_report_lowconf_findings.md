# 模块审查报告：src/tools + src/reports + src/rag

## 发现列表

### P1 缺陷

**P1-1 多候选合成路径：`_replace_function_in_code` 函数体结束检测逻辑缺陷，导致相邻函数定义合并（`src/tools/multi_candidate.py:759-773`）**

`_replace_function_in_code` 用于从其他候选中"粘贴"函数体到基础代码。结束行检测逻辑：
```python
for i in range(start + 1, len(lines)):
    line = lines[i]
    if (
        line.strip()
        and not line.startswith((indent_prefix or "") + " ")
        and not line.startswith(indent_prefix or "    ")
    ):
        end = i
        break
    if i == len(lines) - 1:
        end = len(lines)
```

当基础代码中函数 `f` 的下一函数 `g` 无空行分隔（即 `f` 体末行后紧邻 `def g():` 行）时，`def g():` 行满足 `line.strip()` 非空且不以 `indent_prefix + " "` 开头（顶层函数无缩进），因此 `end = i`（`def g` 行索引）正确，`lines[start:end]` 只替换到 `f` 体末行。但 `new_func_source + "\n"` 写入后，`lines[start:end] = [new_func_source + "\n"]`，`g` 的 `def` 行在 `end` 位置被保留。

然而当 `f` 在基础代码中**有装饰器**时（如 `@decorator\ndef f():`），`_replace_function_in_code` 定位 `f` 的起始行用 `stripped.startswith(f"def {func_name}(")` 匹配，**不会命中装饰器行**，`start` 落在 `def f():` 行。替换后装饰器行保留、`f` 体被替换，但 `f` 体末行与 `g` 的 `def` 行之间无空行分隔，最终合成结果中 `f` 体末行与 `g` 的 `def` 行直接相连（无空行），虽语法合法但格式不符 PEP 8，且 LLM 后续迭代时可能将相邻两个函数误认为同一函数。

**交叉验证**：`synthesize_candidates`（`multi_candidate.py:604`）调用链为 `_replace_function_in_code`，仅 `tests/test_multi_candidate_synthesis.py` 直接消费；`ENABLE_MULTI_CANDIDATE_PATCH=true` 且 `static_ok` 候选含多函数合成时可达。`ENABLE_MULTI_CANDIDATE_PATCH` 默认关，严重度 P1（功能可达但非默认路径）。

**修复建议**：替换后在 `f` 体末行与 `g` 行之间补一个空行（`lines[start:end] = [new_func_source + "\n\n"]`），或在写入前检查 `lines[end]` 是否非空函数定义行并按需补空行。

---

**P1-2 多候选合成路径：`_replace_function_in_code` 当 `f` 在基础代码中无装饰器、`other_code` 中 `f` 体更长时，`g` 的 `def` 行被吞入 `f` 体（`src/tools/multi_candidate.py:759-773`）**

实测复现：
```
base_code:
def f():
    return 1
def g():
    return 2

other_code 中 f:
def f():
    x = 42
    y = x + 1
    z = y * 2
    return z
```
替换后：
```
'def f():\n    x = 42\n    y = x + 1\n    z = y * 2\n    return z\ndef g():\n    return 2\n'
```
`f` 体末行与 `def g():` 行之间**无空行**，语法合法（Python 允许函数定义紧邻），但 PEP 8 要求顶层函数之间 2 空行。更严重的边界情形：若 `g` 体首行是 docstring 或注释（以 `#` 或 `"""` 开头），LLM 后续解析时可能将 `g` 误认为 `f` 的尾部。

**交叉验证**：`synthesize_candidates` 路径，`ENABLE_MULTI_CANDIDATE_PATCH=true` 时可达（默认关）。

**修复建议**：与 P1-1 同一修复点——`lines[start:end] = [new_func_source.rstrip() + "\n\n"]`，并在 `end < len(lines)` 且 `lines[end].strip()` 非空时不额外加空行（避免三空行）。

---

### P2 缺陷

**P2-1 `_parse_failed_cases` 详细格式：`_ERROR_LINE_RE` 匹配 `E   TypeError` 行时，`current_case["error"]` 被填充但后续 `FAILED` 行触发时 `current_case` 已被 push，新 `current_case` 的 `error` 字段缺失（`src/reports/generator.py:476-480`）**

详细格式场景（`FAILED` 行在 `E` 行之前出现）：
```
FAILED tests/test_a.py::test_two
E   TypeError: 'NoneType' object is not subscriptable
```
解析结果：`test_two` 的 `error` 字段为 `"E   TypeError: ..."`（含 `E` 前缀）。这是**正确行为**（`_ERROR_LINE_RE` 允许 `E\s+` 前缀）。

但实际场景是 `FAILED` 行在 `E` 行**之后**出现（pytest 默认输出顺序）：
```
E   TypeError: 'NoneType' object is not subscriptable
FAILED tests/test_a.py::test_two
```
此时 `current_case` 为 `{}`（尚未有 `FAILED` 行），`elif current_case and "error" not in current_case` 条件不满足（`current_case` 为空 dict，falsy），`E` 行被跳过，`test_two` 的 `error` 字段缺失。

**交叉验证**：`ReportGenerator.generate`（`generator.py:349`）调用 `_parse_failed_cases(error_output)`，`error_output` 来自 `state["test_output"]`（pytest 原始输出），pytest 默认输出顺序中 `FAILED` 汇总行在 `E` 详情行之后。`error` 字段缺失时报告渲染跳过错误详情（`generator.py:269` `if case.get("error")`），降级为无错误详情，非崩溃。

**严重度**：P2（报告渲染降级，非数据损坏；默认 pytest 输出下 `error` 字段缺失导致报告信息不完整，但报告仍可生成）。

**修复建议**：将 `elif current_case and "error" not in current_case` 改为在 `FAILED` 行**之前**收集 `E` 行作为"待关联错误"（维护一个 `pending_error` 变量），`FAILED` 行触发时若 `pending_error` 非空则填入 `current_case["error"]`。

---

**P2-2 `apply_patch_to_code` 单函数模式：`_collapse_blank_lines` 对全文执行，导致补丁区域外的多行空行被压缩为单行（`src/tools/patch_applier.py:296-302`）**

`apply_patch_to_code` 单函数模式拼接逻辑：
```python
new_lines = [*lines[:start_idx], "", *patch_lines, "", *lines[end_idx:]]
collapsed = _collapse_blank_lines(new_lines)
new_code = "\n".join(collapsed).strip() + "\n"
```
`_collapse_blank_lines` 对**全文**（包括补丁区域外的原代码）执行压缩。若原代码中 `b` 和 `c` 函数之间有 3 空行（非 PEP 8 标准但合法），应用补丁后这 3 空行被压缩为 1 空行，`b`/`c` 函数的代码区域发生**非预期变更**。

**交叉验证**：`apply_patch_to_code` 是默认路径（`nodes.py:1907` `new_code, applied = apply_patch_to_code(original_code, patch)`）。`safe_apply_patch`（`cross_file.py:561`）也经此路径。影响：应用补丁后写盘的代码与 LLM 预期相比多了空行变更（补丁区域外的 3 空行 → 1 空行），`check_naming_contract` 基于符号集差不检测空行，不会拦截；但 git diff 中会出现与补丁无关的空行变更，影响 diff 审阅与 git blame 可读性。

**严重度**：P2（数据完整性降级——补丁区域外代码发生非预期变更；非默认路径崩溃，但违反"最小变更"原则）。

**修复建议**：`_collapse_blank_lines` 仅对 `[*"", *patch_lines, ""]` 区域执行压缩，保留 `lines[:start_idx]` 和 `lines[end_idx:]` 原样。

---

**P2-3 `apply_patch_to_code` 单函数模式：LLM 补丁包含目标函数的装饰器时，装饰器行重复（`src/tools/patch_applier.py:267-269`）**

`_find_function_range_ast` 返回 `(node.lineno, node.end_lineno)`，`node.lineno` 指向 `def` 行（不含装饰器行）。`start_idx = node.lineno - 1`（0-based `def` 行），`lines[:start_idx]` 保留装饰器行。若 LLM 补丁中也包含装饰器行（如 `@my_decorator\ndef target(x):`），拼接后装饰器出现两次。

实测复现：
```
原代码:
@my_decorator
def target(x):
    return x

LLM 补丁（含装饰器）:
@my_decorator
def target(x):
    return x * 2

结果:
@my_decorator

@my_decorator
def target(x):
    return x * 2
```
语法合法但装饰器执行两次，`@my_decorator` 若为有副作用的注册装饰器（如 Flask `@app.route`），重复注册会导致路由冲突或异常。

**交叉验证**：`apply_patch_to_code` 默认路径（`nodes.py:1907`）。LLM 在单函数模式下生成含装饰器的补丁是常见输出（LLM 倾向于输出完整函数定义含装饰器）。`check_naming_contract` 不检测重复装饰器。

**严重度**：P2（数据完整性——装饰器重复执行；若装饰器为纯注册型则路由重复；若为纯标记型则无副作用。取决于具体装饰器语义，保守评估为 P2）。

**修复建议**：`start_idx` 改为指向装饰器首行（`node.lineno` 减去装饰器行数），或在拼接时检测 `lines[start_idx-1]` 是否为装饰器行并在补丁含装饰器时跳过原装饰器行。

---

**P2-4 `select_best_candidate` 静态筛选模式：`static_ok.sort(key=...)` 原地排序，修改调用方传入的 `candidates` 列表顺序（`src/tools/multi_candidate.py:276,281`）**

`static_ok = [c for c in candidates if c.static_passed and c.new_code]` 是列表推导（新列表），但 `static_ok` 中的 `CandidateResult` 对象是引用（非拷贝）。`static_ok.sort(...)` 修改的是 `static_ok` 列表本身的顺序，不修改 `candidates`。

然而 `for c in static_ok: c.credit_score = ...` 和 `candidate.exec_passed = ...`（执行验证模式，`multi_candidate.py:299`）**原地修改 `CandidateResult` 对象的字段**。`candidates` 列表（由 `generate_candidates` 返回）中的 `CandidateResult` 对象与 `static_ok` 中为同一对象，`credit_score` / `exec_passed` / `exec_coverage` 字段被原地写入。

**交叉验证**：`nodes.py:1736` `static_passed_count = sum(1 for c in candidates if c.static_passed)` 在 `select_best_candidate` 之后执行，此时 `candidates` 中各 `CandidateResult` 的 `credit_score` 已被修改，但 `static_passed_count` 只读 `static_passed` 字段，不受影响。`nodes.py:1743` `best.index` 读取选中候选的 `index` 字段，也不受影响。`multi_candidate_stats` 中无 `credit_score` 字段消费。

**严重度**：P2（状态泄露——`CandidateResult` 对象被原地修改，若调用方后续依赖 `credit_score=None` 初始值会读到非零值；当前调用链无此依赖，但属于隐式副作用，降低可维护性）。

**修复建议**：`select_best_candidate` 入口处对 `candidates` 做浅拷贝（`[CandidateResult(**asdict(c)) for c in candidates]`），或对 `static_ok` 中各候选的 `credit_score` 写入前做拷贝。

---

**P2-5 `cross_file_fallback_single_file` 使用裸 `apply_patch_to_code` 而非 `safe_apply_patch`（`src/tools/cross_file.py:831-834`）**

`apply_multi_file_patch` 的 M-2 修复（`cross_file.py:556-561`）已将多文件路径切换到 `safe_apply_patch`（含危险 API 差集守卫），但 `cross_file_fallback_single_file` 仍使用裸 `apply_patch_to_code`，绕过了 S2 危险 API 守卫。

**交叉验证**：`nodes.py:1900` `fallback_files, applied = cross_file_fallback_single_file(original_files, patches, entry_module)`。当跨文件多文件应用失败时降级到单文件路径，LLM 补丁若含 `os.system` / `eval` 等危险调用，裸 `apply_patch_to_code` 不拦截，危险代码直接写盘。但 `nodes.py:1941-1948` 的 `check_naming_contract` + `dangerous_api_added` 检查在 `cross_file_fallback_single_file` 返回后**仍会执行**（`applied and new_code != original_code` 时），危险 API 会被后续守卫拦截并回滚。

**实际可达性**：降级路径中危险 API 补丁会被 `nodes.py:1941` 的 `dangerous_api_added` 拦截（与 `apply_multi_file_patch` 的 M-2 修复同口径），不产生实际安全漏洞。但代码不一致（M-2 修复只覆盖了 `apply_multi_file_patch`，未覆盖 fallback 路径），若未来有人移除 `nodes.py:1941` 的守卫则 fallback 路径成为危险代码写盘通道。

**严重度**：P2（代码一致性/可维护性问题；当前默认路径安全，但防御深度不一致）。

**修复建议**：`cross_file_fallback_single_file` 第 831 行 `from src.tools.patch_applier import apply_patch_to_code` 改为 `from src.tools.patch_applier import safe_apply_patch`，`new_code, success = safe_apply_patch(original, entry_patch)`。

---

### 核实后无缺陷的项

| 项 | 核实结论 |
|---|---|
| multi_candidate M-4（`CandidateResult` 非 frozen dataclass） | 确认：`CandidateResult` 是普通 `@dataclass`（`multi_candidate.py:129`），`exec_passed` / `exec_coverage` / `credit_score` 字段在 `select_best_candidate` 中被原地写入（`multi_candidate.py:269,299,300`）。`CandidateResult` 无 `__post_init__` 约束，写入合法。无并发访问（`select_best_candidate` 串行调用）。**无缺陷**。 |
| multi_candidate M-5（`generate_candidates` 上限钳制） | 确认：`n = max(1, min(num_candidates, _MAX_CANDIDATE_COUNT))`（`multi_candidate.py:190`），`_MAX_CANDIDATE_COUNT=8`。LLM 调用次数上限为 8 次，`_CANDIDATE_PROMPT_VARIANTS` 长度 3，`index % 3` 取模无越界。**无缺陷**。 |
| cross_file CF-1（`analyze_cross_file_deps` 入度按边计数） | 确认：`in_degree` 按依赖边累加（`cross_file.py:597-601`），释放时逐边 -1（`cross_file.py:622-627`），`queue.sort()` 全量重排（确定性口径）。注释 `cross_file.py:611-614` 明确说明为何不能用 min-heap（并行边 >1 时 min-heap 入度无法归零）。Kahn 算法正确。**无缺陷**。 |
| cross_file CF-2（`_topological_order` 拓扑排序） | 确认：`entry_module` 强制首位（`cross_file.py:606-608`），入度 0 节点按字典序入队（`cross_file.py:615`），每轮弹出后全量重排 `queue.sort()`（`cross_file.py:628`），剩余有环模块按字典序追加（`cross_file.py:630`）。`deps` 为 `None` 时退回 `sorted(patches.keys())`（`cross_file.py:546`）。**无缺陷**。 |
| cross_file CF-7（`_repair_plan_cache_key` 排除 LLM 输出） | 确认：`fingerprint = json.dumps({"entries": ..., "edges": ..., "max_modules": ...})`（`cross_file.py:655-662`），不含 patch 文本。相同依赖图复用 LLM 生成结果（设计文档 §3.5 二期口径）。缓存命中时跳过 LLM 调用（`cross_file.py:784-788`）。**无缺陷**。 |
| reports R-5（`_parse_failed_cases` 映射完整性） | 确认（2026-09-26 全面审查 P2 修复已生效）：当前实现（`generator.py:436-485`）按 pytest 实际输出模式匹配三种格式——带后缀（`[E]`/`[F]`）、短格式（`- AssertionError`）、裸 `FAILED` 行（`unknown` 兜底）。实测三种格式均正确解析。**映射完整，无缺陷**。 |
| P2-3 前轮报告 `_parse_failed_cases` 状态 | 确认：前轮报告标记 P2-3 为"待核实"，本轮核实当前代码已修复（三种格式均可正确解析）；**前轮 P2-3 缺陷已不存在**，无需另行修复。 |
| `apply_multi_function_patch` 排序 key（P13 预切分） | 确认：`code_lines = code.split("\n")` 预切分一次（`patch_applier.py:360`），`_sort_key` 复用 `code_lines`（`patch_applier.py:367-369`），未找到的函数映射为 `(1, 0)` 排末尾（`patch_applier.py:369`）。排序语义正确（找到补丁按行序应用，未找到的最后尝试）。`apply_multi_function_patch` 在 `src/` 中无生产调用方（仅 `tests/test_patch_applier.py` 引用），属测试/文档孤儿函数，**无生产路径缺陷**。 |
| `retriever.py` TTL + 容量清理 | 确认：`_cleanup_expired_and_excess`（`retriever.py:159`）节流 60s（`_CLEANUP_INTERVAL_SECONDS=60`），容量满时每次清理（`retriever.py:180` `count < self.max_cases` 为 False 时跳过节流检查）。`_upsert` 中清理在写锁外（`retriever.py:269`），`upsert` 在写锁内（`retriever.py:274`）。并发语义边界已在注释中明确（`retriever.py:250-260`：至多多并行度条瞬时超容量，下一清理窗口收敛）。**无缺陷**。 |
| `retriever.py` `retrieve_test_cases` / `retrieve_repairs` | 确认：`distances[i] if i < len(distances) else 0.0`（`retriever.py:380`），`zip(doc_rows, meta_rows, strict=False)`（`retriever.py:379`），`metadatas` 为 None 时 `meta_rows = []`（`retriever.py:377`），`zip` 长度不等时 `strict=False` 安全降级。**无缺陷**。 |
| `code_analyzer.replace_function_code` | 确认：`start_line = node.lineno - 1`、`end_line = node.end_lineno`（`code_analyzer.py:196-197`），`lines[:start_line] + new_lines + lines[end_line:]`（`code_analyzer.py:208`）。替换后 `ast.parse` 验证（`code_analyzer.py:215`），失败返回原代码。`replace_function_code` 在 `src/` 中无生产调用方（仅测试引用），**无生产路径缺陷**。 |
| `dependency.py` `install_packages` 超时 | 确认：`timeout=self.dep_install_timeout`（`executor_modes.py:214`），`dep_install_timeout` 来自 `config.EXECUTOR_DEP_INSTALL_TIMEOUT`（默认 120s，`config.py:304`）。`subprocess.run(timeout=...)` 抛 `TimeoutExpired` 时捕获并返回 `(False, detail)`（`dependency.py:697-700`）。**无缺陷**。 |
| `type_repair.py` `_static_type_findings` 保守性 | 确认：`_check_type_hist`（`type_repair.py:434`）仅当同一变量在函数内被赋值为 ≥2 个不同语义族才报告（`type_repair.py:462` `if len(families_hit - {"other"}) >= 2`）。`_family_members` 定义 numeric/text/seq/dict/none 五个族（`type_repair.py:449-454`）。同族内 int/float 不报，bool 与 int 不报（注释 `type_repair.py:448` 明确）。LLM 层（`_repair_with_llm`，`type_repair.py:607`）默认关（`TYPE_REPAIR_LLM_ENABLE=false`），修订代码必须通过 `ast.parse`（`type_repair.py:643`）+ 命名契约回环（`type_repair.py:750`）。**无缺陷（默认路径）**。 |
| `hierarchical_summary.py` `_level1_summary` 截断 | 确认：`if len("\n".join(lines) + sig_line) > budget`（`hierarchical_summary.py:196`）——逐行追加前检查，超预算时丢弃该函数（`dropped.append`），不截断签名本身。实测 `budget=400` 时 L1 摘要输出 28 行（含截断标记），`dropped count: 0`（所有函数均被完整保留或整体丢弃，无半截签名）。**无缺陷**。 |
| `oracle_validator.py` 魔数白名单 | 确认：`_TOLERATED_INTS = {0, 1, 2, -1, 10, 100, 256, 1000}`（`oracle_validator.py:47`），`abs(val) > 2` 时才报告魔数（`oracle_validator.py:210`）。`_check_type_mismatch` 容忍 int/bool 互转（`oracle_validator.py:254` `not {(lhs_type, rhs_type)} & {("int","bool"),("bool","int")}`）。`ORACLE_VALIDATE_ENABLE` 默认关（`oracle_validator.py:62`），**默认路径零行为变化**。 |
| `graphrag.py` `n_hop_subgraph` | 确认：`result_edges` 包含所有出边 + 入边（`graphrag.py:213-221`），`visited` 去重（`graphrag.py:208,222`），`seen` 去重三元组（`graphrag.py:227-231`）。`hops` 钳制 `[1,5]`（`graphrag.py:211`）。中心模块不在 `_out_edges` 时 `result_edges` 为空，返回 `[]`（保守降级，`graphrag.py:236`）。**无缺陷**。 |
| `cross_file.py` `apply_multi_file_patch` M-2 修复 | 确认：`safe_apply_patch`（`cross_file.py:561`）替代裸 `apply_patch_to_code`，含 S2 危险 API 差集守卫（`patch_applier.py:465-472`）。模块不在 `original_files` 中时跳过（`cross_file.py:552-555`，保守不阻断）。任一文件失败整体回滚（`cross_file.py:563-564`）。**无缺陷**。 |
| `nodes.py:1900` `cross_file_fallback_single_file` 消费 | 确认：`fallback_files, applied = cross_file_fallback_single_file(...)`，`new_code = fallback_files.get(entry_module, original_code)`（`nodes.py:1901`）。`cross_file_fallback_single_file` 返回 `(new_files, success)` 二元组（`cross_file.py:808-837`），消费正确。**无缺陷**。 |
| `strategy_bank.py` 缓存 | 确认：`_bank_cache` / `_bank_mtime` 经 `_bank_lock` 保护（`strategy_bank.py:126-140`），mtime 无效化（文件变更时重新加载），损坏 JSON 降级为空库（`strategy_bank.py:139`）。`select_strategy` 三级匹配优先级（精确 > 次级 > 末级，`strategy_bank.py:201-209`），成功率加权排序（`strategy_bank.py:214-215`）。`STRATEGY_BANK_ENABLE` 默认关（`strategy_bank.py:114`）。**无缺陷**。 |
| `failure_frequency.py` 阈值钳制 | 确认：`max(2, n)`（`failure_frequency.py:68`），窗口 `max(2, min(n, 10))`（`failure_frequency.py:81`）。`count < threshold` 时返回 `None`（`failure_frequency.py:127`）。`FAILURE_FREQUENCY_ENABLE` 默认关（`failure_frequency.py:59`）。**无缺陷**。 |
| `tree_sitter_backend.py` 回退 | 确认：`extract_symbols` / `extract_call_graph` 在 tree-sitter 不可用时回退 `TypeScriptBackend`（词法层）（`tree_sitter_backend.py:129,164`）。`register_tree_sitter_backend` 缺依赖时 no-op（`tree_sitter_backend.py:187-189`）。`AISTESTER_ENABLE_TYPESCRIPT_BACKEND` 默认 lexical（词法层）。**无缺陷**。 |

## 模块整体评估

**src/tools/**（19 文件）：
- 核心补丁应用路径（`patch_applier.py`）设计完整，三层守卫（语法 + 命名契约 + 危险 API）默认全开，降级链（L1→L2→L3）保守口径清晰。P1-1/P1-2（多候选合成路径函数边界）与 P2-2/P2-3（全文空行压缩 / 装饰器重复）是主要数据完整性风险，均属非默认路径或边界情形。
- 默认关功能模块（multi_candidate / cross_file / type_repair LLM 层 / graphrag / hierarchical_summary / strategy_bank / failure_frequency / oracle_validator / testless_validation / tree_sitter_backend）实现保守，失败路径均降级不阻断主流程，符合 ADR-0003/0004 口径。
- 跨文件拓扑排序（CF-1/CF-2/CF-7）设计正确，Kahn 算法 + 字典序 tie-break 确定性口径清晰，注释充分。

**src/reports/generator.py**：
- 前轮 P2-3（`_parse_failed_cases` 映射不完整）已修复，三种 pytest 输出格式均可正确解析。
- P2-1（详细格式下 `E` 行在 `FAILED` 行之前出现时 `error` 字段缺失）是剩余缺口，影响报告信息完整性（降级而非崩溃）。

**src/rag/retriever.py**：
- TTL + 容量清理机制设计完整，并发语义边界明确（写锁内仅 upsert，锁外清理），瞬时超容量窗口有注释记录。
- 检索接口（`retrieve_test_cases` / `retrieve_repairs`）降级保守（`strict=False` zip，`metadatas=None` 安全处理）。
- 无生产缺陷。

**src/utils/helpers.py**：
- `extract_code_block` 处理 4 种 markdown 格式，`extract_json_object` O(1) 双候选快路径 + 反向全扫描兜底，实现简洁无缺陷。

**总体结论**：本轮新发现 2 项 P1（多候选合成路径函数边界，非默认路径）+ 4 项 P2（报告解析降级、全文空行压缩、装饰器重复、危险 API 守卫不一致、状态泄露）。前轮待核实项（P2-3、M-4/M-5、CF-1/CF-2/CF-7、R-5）均已核实完毕，无新增缺陷。默认路径（单文件 `apply_patch_to_code` + `safe_apply_patch` + 命名契约 + 危险 API 守卫）设计健全，主要风险集中在非默认路径的边界情形与全文级副作用（空行压缩、装饰器重复）。
