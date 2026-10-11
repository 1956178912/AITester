# T-B：Python 与领域机制独立代码审查（AITester）

- 审查对象：`/Users/wangchenyu/Workspace/AITester`，工作树 = HEAD `d9e51df`（2026-10-10 16:28）+ 33 个已修改文件（+1619/−252）+ 25 个未跟踪项（`git status` 实测）。
- 审查方式：直接读代码。项目 README / docs / ADR / 既有评审仅作为"声称"的出处引用，不作为事实来源。所有结论附 `file:line`，均为本次实际打开读到的位置。
- 行号基准：**当前工作树**（非产出批次工件的提交），引用批次工件时另行标注。
- 只跑了只读命令与一个临时复现脚本（`audit_2026/_probe_gate_vs_metric.py`）；未调用任何 LLM，未修改项目任何文件。
- 标注约定：`[实测]` = 本次运行得到的输出；`[读码]` = 代码逐行判读；`[静态推断]` = 由代码路径推导但未执行验证；`未验证` = 无法从代码或实测定论。

---

## 0. 五个指定判定的明确结论（速览）

| 判定 | 结论 | 一句话证据 |
|---|---|---|
| (a) `specific_red`/`over_red` 判定 & 检出率是否计入非特异断言 | **过红不计入检出**；但"非特异"若指"断言不针对缺陷语义、只是碰巧区分两版代码"则**会计入**（无任何断言特异性校验）。**84–94% 覆盖 vs 15.8% 检出主要由"执行覆盖 ≠ 判别力"解释**，分母不同构是次要因素。 | `_m1_metrics.py:529-539`（buggy 绿→0；fixed 红→0）；`executor.py:198` + `executor_output.py:38-66`（覆盖率只统计"执行过"） |
| (b) `spec_compile_rate` 分子/分母 & 逻辑表达力 | 分子=可编译非空子句数，分母=非空子句数；expr 通道优先，NL 回退；无材料返回 **0.0 而非 None**。表达力 = **无量词/无函数/无数组/无关系/无时序的标量算术约束**（z3 QF Bool/Int/Real）。SMT **真在求解**，但只求解"前件可行性/边界极值/前件空洞/后件自洽"，**不做**"实现是否满足后件"。 | `spec_ir_v2.py:668-683, 686-719`；`spec_smt.py:322-388`（翻译算子集）、`:14-24`（能力边界自述）、`:459-549`（Solver/Optimize 真调用） |
| (c) 补丁生成 vs 运行时自修复 | **是离线的自动化程序修复（APR）闭环，不是运行时自修复**。无监控/守护/热加载/故障转移组件；"补丁"= 把整份新源码写回被测文件，验证失败再回滚。 | `patch_io.py:351-455`（写盘）、`:458-504`（回滚）；`main.py`+`src/cli/app.py`（只有批量 CLI，无服务模式）；全仓无 watchdog/supervisor/restart（grep 实测） |
| (d) 执行沙箱强度 | **默认（venv 档）只隔离环境变量与 sys.path，不隔离文件系统、不隔离网络**；内核沙箱默认关，且打开时把 `cwd`(=仓库根) 隐式加入可写路径；`runtime_probe` 执行 LLM 测试代码的子进程**完全没有**内核沙箱接入。 | `executor_modes.py:257-286`；`executor.py:177-188, 237-269`；`kernel_sandbox.py:209-211`；`runtime_probe.py:343-353` |
| (e) LLM 输出→exec/eval/subprocess 注入面 | 主进程**无** `eval`/`exec`/`shell=True`/`os.system`；唯一 `exec` 在 `runtime_probe` 的**子进程 runner 模板**内执行 LLM 测试代码。LLM 补丁落地前有"正则 + AST 危险 API 差集"双通道拦截（默认开）；输入侧 prompt 注入检测默认关。 | `runtime_probe.py:251`；`nodes.py:1759-1814`；`injection_guard.py:51-65`；`rogue_monitor.py:37-39` |

---

## 1. (a) detection-first 协议与特异性门：真实实现

### 1.1 三个不同层各自定义"红"，且判据不一致（本次最重要发现）

| 层 | 定义 | 位置 | 对"没跑起来（收集/语法错误）"的处理 |
|---|---|---|---|
| 环路内执行器 | pytest rc==0 即 passed | `executor.py:286`；`executor_modes.py:486` | 收集错误 → passed=False（红） |
| 运行时特异性门（gate） | 在 gold fixed 上跑：绿=`specific_red`，非 0=`over_red` | `detection_gates.py:96-121`（判定在 `:121`） | **无区分**：收集错误 rc=2 → `over_red` |
| 离线 M1 检出指标 | buggy 红 ∧ fixed 绿 ∧ 两侧无收集/语法错误 | `_m1_metrics.py:473-539`（`:529-539` 三段）；错误判据 `:58-81` | 明确排除：→ 0.0 |

`detection_gates.py:82-93` 声称"与 M1 事后裁决完全同一原语，行为口径一致"（`:21-24` 注释），但**只复用了执行函数，没有复用判定函数**：`_run_test_against_code` 只取 `res[0] == 0` 作为 `green`，从不调用 `_looks_like_test_execution_error`。

**本次实测复现**（`audit_2026/_probe_gate_vs_metric.py`，无 LLM）：

```
--- cross_file_import ---
  _run_pytest_in_tmp rc = 2
  _looks_like_test_execution_error = True
  specificity_verdict = over_red
--- syntax_error ---
  _run_pytest_in_tmp rc = 2
  _looks_like_test_execution_error = True
  specificity_verdict = over_red
```

后果链（全部 [读码]）：
1. `over_red` → `workflow.py:707-719` 路由 `regenerate`，不再进修复循环（消耗 `MAX_REGENERATIONS=1`，`config.py:375`）；
2. `over_red` 行不写红证人（`nodes.py:1441-1442`），后续"曾检出"证据链缺失；
3. `over_red` 是弃权门信号之一（`patch_abstain.py:40-46` 第 3 条）；
4. `over_red` 是 CPR/IDR 负信号（`experiments/cpr_idr_report.py:50`）与四通道 R3"fixed 腿"代理（`four_channel_recompute.py:34, 230-232`）；
5. `BASELINE.yaml:75-78` 用 `specific_red/over_red` 比例作为"−28pp 主机制"的证据——该比例**混入了收集错误/未运行**，作为机制归因过强。

**独立佐证（跨文件任务的系统性误判）**：gate 委托时**不传** `task_metadata`（`detection_gates.py:85-87`），而 `_m1_metrics` 显式分派跨文件物化依赖 `task_metadata["is_cross_file"]`（`:330-333`）。跨文件任务的伴生模块（`module_a/b/c`）在单文件布局下不存在 → `ModuleNotFoundError` → rc=2 → **判 `over_red`**（上表 cross_file_import 即此形态）。`[静态推断 + 实测形态复现]`

**该缺口的边界（避免过度声称，工件级约束，详见 §11.4）**：在 7 批主力工件的可执行行上，gate 与 M1 detection **逐位等价**——`specific_red → det=1.0` 为 206/206，`over_red → det=0.0` 为 244/244。分歧**只落在"根本没跑起来"这一格**（两者都输出"非检出"，故工件层无法区分"真过红"与"从未运行"）。因此本条的正确表述是：**判据分叉使 `over_red` 这一标签不可解释（真非特异 / 未运行混在一起），而不是使检出数字本身被高估**。

### 1.2 检出率是否把非特异断言计入？

- **过红（在 gold fixed 上也红）→ 不计入**：`_m1_metrics.py:533-536` 直接 `return 0.0`。所以"M1 检出率被过红刷高"不成立。
- **但 M1 检出率不检查断言的"特异性"**：全流程没有把 `oracle_validator.check_assertions`（恒真断言检测）接入 M1 判定。该检测本身默认关（`flags.py:79-87` `ORACLE_VALIDATE_ENABLE` 默认 false；logic/scientific 档才开，`config.py:61,72`），且结果是观测层（`nodes.py:974-1019`，O4 用它触发一次再生成，`nodes.py:1015-1019`）。
- 因此"非特异断言"的两种含义要分开：
  - 含义 A：在无缺陷代码上也失败（over_red）→ **不计入**；
  - 含义 B：断言不编码缺陷语义、只是碰巧区分了 buggy 与 gold fixed（例如断言某个被 gold 补丁顺带改变的实现细节；或 `assert f(x) == <魔法值>` 恰好在 buggy 上不成立）→ **计入**，且无任何静态/规约核对拦截。
- 结论：检出率衡量的是**行为判别力（F2P 三段）**，不是"断言正确性/规约符合度"。把它读成"测试质量"会过度解释；把它读成"这套测试能否区分本次缺陷的两版实现"是准确的。

### 1.3 84–94% 覆盖率 vs 15.8% 检出率的解释

三条机制，按贡献排序：

1. **定义差异（主因，[读码]）**：覆盖率来自 `pytest --cov=<target_dir>` 的 TOTAL 行（`executor.py:198`；解析在 `executor_output.py:20,38-66`），**只要求被执行**；检测要求 `buggy_rc != 0 ∧ fixed_rc == 0`（`_m1_metrics.py:529-539`）。测试把被测函数跑一遍、断言恒真或断言与缺陷无关 → 覆盖率可以很高而 `buggy_rc == 0` → 检出 0（`_m1_metrics.py:529-530`）。
2. **分母不同构（次要，[读码]）**：`coverage` 均值分母 = 全部任务（`run_benchmark.py:2674`，缺失按 0），而 detection 分母 = 有 gold 材料且可测的子集（`run_main_batch.py:370-374`；`analyze_results.py:717-745` 逐字段剔除 None）。README 自己的口径是 aitester `38/240` 对 df `117/261`（`README.md:72`）——**两臂分母差 21 行**，代码层没有任何重加权/敏感性校正。`[静态推断]`：分母差异方向（aitester 少 21 行可测）本身不能解释 28pp，但使"15.8%"是条件于可测性的估计。
3. **测量伪影（历史，已被项目自己修复）**：`_m1_metrics.py:157-176` 记录"第四起测量伪影"——判分树只提供包结构布局导致扁平 import 恒 rc=2、detection 构造性为 0；修复为双布局。同类伪影在 `:236-295`（跨文件）、`:125-202`（QuixBugs 辅助模块）各一处。

### 1.4 detection-first 协议与特异性门的开关口径

- `config.py:385-414`：`DETECTION_FIRST_ENABLE` **默认 false**；另有线程级覆盖 `set_detection_first_thread_override`（`config.py:403-413`），被 `run_plain_llm_df_baseline` 强制开启（`run_benchmark.py:412-419`）。
- `config.py:104-105`：`DETECTION_SPECIFICITY_GATE_ENABLE` / `RED_REGRESSION_GATE_ENABLE` 只在 `logic` 档注入 true（`_PROFILE_PRESETS`，`config.py:43-115`）。
- 门只在 `iteration==0` 且 `detection_first_enabled()` 时运行（`nodes.py:1423-1438`），因此**非 logic 档批次根本没有 gate 数据**（全为 None）。
- `over_red` 的再生成强化段落默认**关**（`nodes.py:520-527` `OVER_RED_SECTION_ENABLE` 默认 false），即"过红后再生成"在默认口径下只是"用同一份计划再问一次"（`nodes.py:592-597` 自述）。
- `nodes.py:585-600` 的代码注释把 over_red 部分归因于"缺陷代码不终止而挂起"。**与实现不一致**：fixed 侧超时会让 `_run_pytest_in_tmp` 返回 None（`:380-381`）→ `_run_test_against_code` 返回 None → verdict = `unavailable`（`detection_gates.py:119-120`），**不是** `over_red`；而 buggy 挂起 + fixed 正常终止反而会得到 `specific_red`。真正会产出 `over_red` 的"假红"是**收集/导入错误**（见 1.1 实测）。

---

## 2. (b) 逻辑驱动：`src/specs/*` 的真实表达力与度量定义

### 2.1 `spec_compile_rate` 分子/分母（精确）

`spec_ir_v2.py:668-683`：

```
compiled = 0; total = 0
for clauses, kind in ((pre, "precondition"), (post + inv, "postcondition")):
    for clause in clauses:
        if not clause.strip(): continue        # 空串既不入分子也不入分母
        total += 1
        if _clause_is_compilable(clause, kind, known_names): compiled += 1
return compiled / total if total else 0.0      # 无材料 → 0.0（不是 None）
```

- 通道选择 `_select_compile_channels`（`:644-665`）：`*_expr` 三字段中**任一存在 str 子句**即用 expr 通道（含空串，即"通道存在"），否则回退 NL 通道（`preconditions/postconditions/invariants`）；**两通道不合并**。
- 判定门 `_clause_is_compilable`（`spec_ir_v2.py:267-336`）：形态门（字符白名单 `_EXPR_TOKEN_RE`，`:89`）+ AST 白名单（`_whitelist_check`，`:173`）+ 标识符绑定门 + 产物自检。
- 写入点：`nodes.py:421-449`，仅在 `SPEC_IR_DSL_ENABLE=true` 时计算；`logic`/`scientific` 档注入 true（`config.py:57,67`）。**纯观测字段，不参与路由**（`nodes.py:420`）。
- 正交指标 `spec_expr_coverage`（`:722-734`）= `expr 子句数 / max(NL 子句数, expr 子句数)`，无材料 → None。
- 因此 `spec_compile_rate` 的语义是**"LLM 形式化产物被本仓受限 DSL 接受的比例"**，不是"规格覆盖率"，也不是"逻辑驱动贡献度"。

### 2.2 表达力上限（逐层 [读码]）

| 层 | 支持 | 不支持 |
|---|---|---|
| SpecExpr DSL | 比较、布尔、算术、常量、白名单调用（`len/abs/min/max/round/float/int/str/sorted/any/all/isinstance`，`:63-68`）、容器下标/长度、白名单属性（`value/real/imag`） | 赋值/语句/控制流（`ast.parse(mode="eval")` 拒绝，`:92-140`）、任意函数调用、任意属性链 |
| z3 翻译 | `Bool/Int/Real` 标量、`And/Or/Not`、比较、`+-*/%`、常量、名称（`spec_smt.py:322-388`） | 调用/幂/下标/属性 → **整条子句保守跳过**（`:20-22`、`:88`）。全仓 `src/specs/` 无 `ForAll/Exists/Array/Function/BitVec/String`（grep 实测为空） |

结论：**不是一阶逻辑，也没有关系/时序**。它是"单排序标量上的无量词布尔组合 + 线性算术"，即 QF 片段；名称未做符号化建模（无未解释函数、无数组理论），所有子句都是对同一批标量变量的一阶无量词约束。

### 2.3 SMT 是真求解还是语法检查？

**真求解**（[读码]，调用点为 `z3.Solver()` / `z3.Optimize()`）：
- 前件 SAT 见证 + 边界极值：`spec_smt.py:525-546`（`solver.check() == z3.sat` 取模型；`Optimize().minimize/maximize` 取边界，带 `_OPT_BOUND=10**6` 包围盒与 timeout）。
- 前件空洞（UNSAT）检测：`:559-584`。
- 后件自洽（把 `r` 视为自由变量）UNSAT 检测：`:654+`；组合入口 `check_spec_consistency`（`:693`）。
- 见证还要过 **Python 语义复核**（`:495-517`，受限 AST 求值器，无 `eval`），z3 与 Python 语义分歧的见证被丢弃。
- 预算：`SPEC_SMT_TIMEOUT_MS` 默认 2000、上下限 100–30000（`:73-80`）；`SPEC_SMT_MAX_WITNESSES` 默认 3（`:82-92`）；`used` 上限由 `_max_witnesses` 控制。
- 默认关（`SPEC_SMT_ENABLE` false，`:48-49`）；z3 已进 `requirements.txt:53` / `requirements.lock:130` 并有 CI fail-closed 断言（`ci.yml:183-207`），本机实测 `z3 5.1.0` 可导入。

**明确不做**（模块自述 `:14-24`，与代码一致）：不做"实现是否满足后件"的判定（无实现语义，判了是空话）。

**但后件断言仍是"实现输出 vs 字面约束"**：`compile_spec_oracle` 把后件编译成 `assert <expr>`，`r = func(...)`（`spec_ir_v2.py:419-427, 471-503`）。无边界材料时用**字面量 0 绑定**（`:487-503`），代码自己承认"层 2 的字面量 0 绑定可能本身违反前置条件"（`:457-458`）——这会产出**对无缺陷代码也失败的断言**，即 1.1 意义上的 over_red。默认关（`SPEC_ORACLE_EXEC_ENABLE` 默认 false，`flags.py:185-201`），`logic`/`scientific` 档开。

### 2.4 反例驱动精化（CEGIR）**未接入主链路**

`spec_refine.py:26-28` 自述："本模块是独立可调用能力……**不接入主链路**（Planner/Generator 调用点的接入属后续批次）"。`[读码]` 全仓无 `spec_refine` 的调用点（仅 `spec_refine.py` 自身与 `spec_smt.py` 的 docstring 引用）。所以"检测到矛盾 → 回灌 LLM 修契约"这条闭环在代码层**不存在于运行路径**，只在单元测试里。

### 2.5 逻辑链路的真实端到端形态

```
Planner(LLM) → logic_analysis(JSON)
  → parse_logic_analysis + validate_spec_ir（观测，M10 严格模式默认关；logic_spec.py:51-53）
  → compile_readiness / spec_expr_coverage（纯观测，SPEC_IR_DSL_ENABLE）
  → compile_spec_oracle（SPEC_ORACLE_EXEC_ENABLE）→ 追加 test_specir_v2_oracle 到生成测试尾部（nodes.py:173-227, 253-260）
  → Executor 与 LLM 测试同文件执行 → spec_oracle_verdict 行级判定（nodes.py:263-289）
```
"逻辑驱动"在运行期**确实存在**（oracle 注入 + 判定），但强度受限于：表达式通道接受率（`BASELINE.yaml:70-72` 实测 0.205–0.219）、绑定上下文保守（无边界材料时字面量 0）、SMT 只用于取输入/查自相矛盾、精化闭环未接线。

---

## 3. (c) 补丁生成 vs 运行时自修复

### 3.1 代码层判定：**自动化程序修复（APR）闭环，不是运行时自修复**

- 修复动作 = 把**整份**新源码写回被测文件：`_safe_write_patch`（`patch_io.py:351-455`）经 4 道检查（非空/不短于原码 10%、含函数定义、路径白名单、仓库核心黑名单）后 `_write_file_atomic`（`:201-223`，tempfile + `os.replace`）。
- 验证失败回滚：`_rollback_last_patch`（`:458-504`）从 `tempfile.gettempdir()/aitester_patch_snap_<pid>_<tid>/iterN_<basename>` 恢复快照；快照失败 **fail-closed 拒写**（`:444-449`）。回滚触发在 `nodes.py:1481-1494`（本轮测试失败 + 有快照 + 磁盘与 state 双恢复）。
- 目标文件是**任务的临时副本**：`run_benchmark.py:1576` `tempfile.mkdtemp(prefix=f"aitester_{task.task_id}_")` + `:1602` 写 `instance_file`；跨文件任务同样落在该 tmp 目录（`_write_cross_file_modules`，`:1378, 1611`）。
- 无任何运行时自愈组件：全仓 `grep watchdog|supervisor|self-heal|restart|daemon` 只命中 `api_manager.py:63,1024-1051`（LLM API 健康检查线程，与"修复被测系统"无关）；CLI 只有批量命令（`src/cli/app.py`、`main.py:11`），无 `serve/watch` 模式。
- "自修复"在代码里只出现在三处注释（`self_repair_trap.py:4`、`nodes.py:1079`、`semantic_cache.py:347`），语义都是"迭代修复循环"，不是"运行时恢复"。
- 文档侧已自行收口：`MODEL_CARD.md:15-16`"**自修复为可测量口径而非已证实主张**（AL5 定位收口）"；`README.en.md:50` 仍写 "self-repair exists"。

### 3.2 修复侧的确定性优先与弃权门

- 确定性优先路由：`debugger.py:355-390`（`DETERMINISTIC_REPAIR_FIRST_ENABLE` 默认 **false**，`deterministic_repair.py:87`）；每任务至多一次（`state["deterministic_repair_status"] is None`）。
- 弃权门（ADR-0020）：`patch_abstain.py:40-63`，5 条信号纯推导，**只透出 `patch_abstained` / `patch_abstain_signals`，不做阻断**（`:23-29` 自述"观测层先行，阻断档待 A/B 后转正"）。`[读码]`
- 故障定位：`fault_localizer.py:64` `FAULT_LOCALIZER_ENABLE` **默认 true** → aitester 臂每任务多一次 LLM 调用（定位），而 `plain_llm_df` 臂无此组件（`run_benchmark.py:381-419`）。对照实验的成本/效果归因需注意该不对称。`[读码]`
- 回归保护：`_compute_regression_rate`（`_m1_metrics.py:649-695`）在补丁后跑 gold P2P；`RED_REGRESSION_GATE`（默认关）只处理"抹红"，不做 P2P。

---

## 4. (d) 执行沙箱强度

| 链路 | 默认 | 环境变量 | 文件系统 | 网络 | 进程/资源 |
|---|---|---|---|---|---|
| venv 沙箱（`EXECUTOR_USE_VENV=true` 默认，`config.py:488`） | **默认生效** | `scrub_os_environ()` → 白名单 13 键，**默认 true**（`credential_scrub.py:91-111, 114-122, 211-213`）；`HOME` 在白名单内 | **无隔离**（无 chroot/namespace：`executor_modes.py:257-264` 只改 PYTHONPATH） | **无限制** | 30s 墙钟 + `RLIMIT_CPU/NPROC/FSIZE/NOFILE`（`executor_runtime.py:24-53, 137-170`）+ 进程组 kill（`process_utils.py`） |
| 本地链路（`EXECUTOR_USE_VENV=false`） | 需显式 | 同上（`executor.py:177-183`） | **无隔离**，且 **cwd=仓库根**（`executor.py:154, 271`） | **无限制** | 同上 |
| Docker（`EXECUTOR_USE_DOCKER` 默认 false，`config.py:497`） | 否 | `scrub_os_environ()`（`executor_modes.py:472`） | `--read-only` + `/tmp` tmpfs + 挂载 sandbox_dir（`:435-437, 374-382`） | **默认 `--network=none`**（`DOCKER_DEFAULT_NETWORK_NONE` 默认 true，`:438-442`）；`allowlist` 档实为 bridge、**无容器级出站管控**（`:387-395, 405-416`，项目已诚实化） | `--cpus/--memory/--pids-limit` + `--cap-drop=ALL` + `no-new-privileges`（`:417-437`） |
| 内核沙箱（Seatbelt/bwrap，`KERNEL_SANDBOX_ENABLE` 默认 false） | 否（`safe`/`logic` 档开） | — | Seatbelt profile：`(deny default)` + 放行 `allowed_paths`/`/usr`/`/System`/`/Library`/`/tmp` 读，写仅 `allowed_paths`+`/tmp`；显式 deny `.env*`/`.ssh`/`.aws`（`kernel_sandbox.py:105-142`） | **未放行 network**（注释 `:141`；profile 无 `allow network*`） | `process-fork` + 限定 `process-exec` 子路径（`:135-137`） |

**两个关键削弱点（[读码]）**：

1. `build_sandbox_command` 把 `cwd` 自动追加进 `allowed_paths`（`kernel_sandbox.py:209-211`），而本地链路传 `cwd=project_root`（`executor.py:238`，`project_root` 为仓库根，`:154`）→ **内核沙箱开启时，整个仓库根是可读可写路径**；只有 `.env/.ssh/.aws/llm_configs.json/credentials` 被 deny 读取（`:140`），没有对 `src/` 等源码的写保护（`patch_io.py` 的仓库核心黑名单只作用于**补丁写盘**，不作用于**测试执行**）。
2. `runtime_probe.capture_failure_snapshot` 用子进程执行 LLM 生成的测试代码（`runtime_probe.py:345-353`），env 走 `scrub_os_environ()`（`:343`），但**没有** `kernel_sandbox` 接入：全仓 `kernel_sandbox` 调用点仅 `executor.py:237` 与 `executor_modes.py:143`。同一份代码在 `KERNEL_SANDBOX_ENABLE=true` 时经 executor 被沙箱化，经 probe 则不被沙箱化（`RUNTIME_PROBE_ENABLE` 默认 false，`runtime_probe.py:75`）。
3. 其余 LLM 产物执行面（`testless_validation.py:228-240` 导入冒烟、`:120-140` mypy）同样只有 env 脱敏 + 超时，无内核沙箱；`dependency.py:895-899` 的 `pip install` **未传 `env=`**（继承全量环境，但执行的是 pip 而非 LLM 代码，风险低；`auto_install_deps` 默认 false，`executor.py:74`）。
4. 残余风险（[静态推断]，与项目自己记录的挂死事故同类，`executor.py:204-211`）：M1 判定原语 `_m1_metrics._run_pytest_in_tmp` 仍用裸 `subprocess.run(..., capture_output=True, timeout=timeout)`（`:358-378`），未采用 2026-10-10 引入的 `process_utils.run_with_timeout`（临时文件承接输出）——若被测代码派生"孙进程持管道写端"，`communicate()` 可能不返回，且该原语同时被离线指标与运行时特异性门调用（`detection_gates.py:85-87`）。

---

## 5. (e) LLM 输出→exec/eval/subprocess 注入面

| 面 | 位置 | 现状 |
|---|---|---|
| 主进程 eval/exec | 全仓 grep：`src/` 内唯一 `exec(` 在 `runtime_probe.py:251`（**子进程 runner 模板字符串内**，非主进程）；`dataset_loader.py:396` 的 `compile()` 仅做语法校验（不 exec） | 无主进程蒸煮面 |
| shell 注入 | 全仓 `shell=True` / `os.system` / `os.popen` / `pickle.load` / `yaml.load` grep **为空** | 无 |
| LLM 补丁危险操作（输出侧） | `nodes.py:1759-1814`：AST 差集 `dangerous_api_added`（默认开，`patch_applier.py:483, 896`）+ 正则 `check_llm_patch_safety`（输出侧默认开，`injection_guard.py:56-65`）→ **命中即拒绝应用**（`nodes.py:1811-1814`） | 有拦截 |
| 命名契约（补丁不许删符号） | `nodes.py:1766-1777` `check_naming_contract`，失败拒应用 | 有拦截 |
| Prompt 注入（输入侧） | `injection_guard.py:51-53` `INJECTION_GUARD_ENABLE` **默认 false**；接线在 `nodes.py:839-875`（只写"疑似注入"警示，不阻断——模块自述 `:44-46`） | 默认关，且只标记 |
| 生成测试的副作用（输出侧测试代码） | 无静态拒绝：`deterministic_guard`（随机数/长 sleep/网络/子进程 AST 扫描，`deterministic_guard.py:32-35` 默认 false）与 `oracle_validator`（恒真断言，默认 false）都只是**观测**，不阻断 | 默认关 |
| LLM 输出的代码抽取 | `helpers.extract_code_block` / `patch_applier.normalize_patch_text`（markdown 围栏/`python` 前缀清理，`_m1_metrics.py:395-401` 记录其必要性） | 无执行风险，但**判分口径与执行口径历史上曾分叉**（同处记录） |
| 凭证外泄 | `credential_scrub` 白名单（默认 true）覆盖全部 LLM 代码子进程（executor 三链路 / runtime_probe / testless_validation）；对照明文 `.env`：本机 `.env` 存在（`ls -la` 实测），未被 `.gitignore` 之外机制保护，CI 有 gitleaks 工作树硬门禁（`ci.yml:448-458`）+ 历史扫描（非阻断，`:529-540`，注释自述存在**存量历史泄漏**） | 基本可控，历史泄漏未清 |

---

## 6. 声称 vs 实现对照表

| # | 主张 | 声称出处 | 代码实际 | 判定 | 影响 |
|---|---|---|---|---|---|
| 1 | 门①与 M1"完全同一原语，行为口径一致" | `src/tools/detection_gates.py:21-24` | 只复用了 `_run_pytest_in_tmp`，未复用错误判据（`detection_gates.py:82-93` vs `_m1_metrics.py:58-81, 528-538`）；实测 rc=2 → `over_red` | **不一致** | 过红统计混入未运行/收集错误；路由、弃权信号、R3 代理、−28pp 机制归因受影响 |
| 2 | "检出优先协议让系统先检出再修复" | `config.py:385-414`；`workflow.py:675-719` | 实现存在且可路由；但默认关，且 `over_red` 强化段落默认关（`nodes.py:520-527`），再生成预算 1（`config.py:375`） | **部分一致** | 默认口径与"检出优先"无关；logic 档才生效 |
| 3 | `over_red` = 非特异红（含挂起） | `nodes.py:592-597` | 挂起在 fixed 侧→`unavailable`（`detection_gates.py:116-120`）；实测真正产出 over_red 的是收集/导入错误 | **不一致** | 机制叙事把三类不同证据（挂起/未运行/非特异）混为一类 |
| 4 | "逻辑驱动 = 可编译率" | `nodes.py:415-420`；`BASELINE.yaml:70-74` | 定义与写入点存在（`spec_ir_v2.py:686-719`；`nodes.py:421-449`），默认关、纯观测；实测率 0.205–0.219（工件） | **部分一致** | 主张强度被高估：通过率 ≠ 规约覆盖，且未接精化闭环 |
| 5 | SMT 为"形式化内核" | `ci.yml:183-207`；`spec_smt.py:14-24` | z3 真调用（`Solver/Optimize`），但仅 QF 标量约束、仅前件见证/空洞/后件自洽；**不做**实现-后件验证（模块自述同） | **部分一致** | 论文中若称"形式化验证实现"则不成立 |
| 6 | "自修复系统" | `README.en.md:50`（"self-repair exists"）；`MODEL_CARD.md:15-16`（已收口为"可测量口径"） | 无运行时自愈；只有补丁写盘+回滚（`patch_io.py:351-504`） | **不一致（定位层面）** | 对外定位需限定为 APR/离线修复 |
| 7 | 覆盖率 84–94% 与检出 13–16% 并列披露 | `BASELINE.yaml:58-64` | 两指标定义与分母确实不同（`executor.py:198` vs `_m1_metrics.py:529-539`；分母 `run_benchmark.py:2674` vs `run_main_batch.py:370-374`），注释未点明分母不同构 | **部分一致（数字诚实，归因不足）** | 易被读成"同一批任务的覆盖率 vs 检出率" |
| 8 | 沙箱"隔离执行" | `executor.py:48-59`（模式优先级描述） | venv 档只隔离 env/sys.path；内核沙箱默认关且开启时含仓库根可写；probe 链路未接沙箱 | **部分一致** | "沙箱"一词在 venv 档易被高估；LLM 测试代码默认可写宿主文件、可联网 |
| 9 | 凭证不外泄到被测沙箱 | `credential_scrub.py:23-31` | 白名单默认 true 且被三条链路消费（实测 `executor.py:177-183`、`runtime_probe.py:343`、`testless_validation.py:236`） | **一致** | 但只封环境变量；`HOME` 在白名单内 → `~/.ssh`、`~/.aws` 文件仍可读（内核沙箱档才 deny） |
| 10 | Prompt 注入防御（ADR-0012） | `injection_guard.py` 模块头 | 输入侧默认 false 且仅标记；输出侧默认 true 且**真拦截**（`nodes.py:1811-1814`） | **部分一致** | 输入侧（issue/描述注入）默认无防护 |
| 11 | 弃权门（ADR-0020） | `patch_abstain.py:1-29` | 判定核存在，5 信号纯推导，**只观测不阻断**（自述一致） | **一致（自述即观测层）** | 不能当作"已拦截坏补丁" |
| 12 | 冗余键集/历史兼容（`None` 与 0 区分） | `_m1_metrics.py:6-12` | detection/repair/false_fix 确实以 None 表示不可测（`:497-499, 598-600, 635-639`） | **一致** | 但 `spec_compile_rate` 无材料返回 **0.0**（`spec_ir_v2.py:683`），口径不同 |
| 13 | 主力批次 provenance 可审计 | `run_benchmark.py:2744-2748`（键表）、`:2890-2892`（读取）、`:2928`（写入） | 存量 main_batch 工件 env_snapshot 仅 37 键，`DETECTION_SPECIFICITY_GATE_ENABLE`/`SPEC_IR_DSL_ENABLE`/`SPEC_ORACLE_EXEC_ENABLE` **ABSENT**（非 None）；而结果行有非空 `specificity_gate_verdict` 证明门确实运行 | **不一致（存量工件）** | "逻辑档开了哪些开关"只能从数据反推；键表 2026-10-10 才补齐（`run_benchmark.py:2838-2845`） |

---

## 7. Python 专项诊断表

| 维度 | 问题 | file:line | 严重度 | 修复建议 |
|---|---|---|---|---|
| 类型门禁深度 | `[tool.mypy]` 段**无任何严格设置**（仅一个 overrides 表）；未注解函数体不检查 | `pyproject.toml:232-234, 256` | 中 | `[tool.mypy]` 加 `disallow_untyped_defs=true`（当前 `--disallow-untyped-defs` 实测 10 errors）、`check_untyped_defs=true`、`warn_unused_ignores=true`；命令：`.venv/bin/python -m mypy src/ config.py --disallow-untyped-defs` |
| 类型抑制存量 | `type: ignore` 43 处（src/） | `grep -rn "type: ignore" src/ \| wc -l` → 43 | 低 | 逐簇收窄并启用 `warn_unused_ignores`；`ruff` 已启用 PGH003（`pyproject.toml` select 含 `PGH`） |
| lint/format | `ruff check .` 全绿（0.16.3） | 实测；`ci.yml:305-308` | — | 保持 |
| 本地 format 门禁假红 | `ruff format --check .` 报 21 个文件待格式化，**全部是 `audit_2026/*.py` 审计临时脚本**（非产品代码）；`extend-exclude` 未含该目录 | `pyproject.toml:116` | 低 | `extend-exclude` 增 `"audit_2026"`，或把该目录加入 `.gitignore` |
| CI 门禁真实性 | ruff / mypy / pytest / bandit / pip-audit(顶层+lock) / gitleaks / 覆盖率 ratchet / 工件校验 / env 预算 / state 契约 / 零断言守卫均为**阻断**步骤；version 钉住 | `ci.yml:175-178, 305-321, 422-429, 460-511, 364-385, 227-259` | — | 保持；建议把 `audit_2026` 类临时目录纳入 ignore（同上） |
| 测试规模 | `pytest --collect-only` 实测 **5317 tests collected in 3.58s**（无收集错误） | 实测 | — | 保持 |
| 循环依赖 | `config.py` 顶层只依赖 `dotenv`；`src/graph/*` 用函数内延迟 import 断开环（如 `agents_cache.py:42-44`、`detection_gates.py:85`） | `config.py:20-23` | 低 | 延迟 import 是本仓惯例（`pyproject.toml` 已 ignore PLC0415），可接受 |
| 裸 except | `grep "except:"` 命中 1 处，实为 docstring 文本；无裸 except | `src/tools/code_analyzer.py:109` | — | 无需处理 |
| 静默吞异常 | `except Exception` + 紧邻 `pass` 6 处；`logger.debug` 级吞掉异常多处（探针/覆盖注入/后处理） | `nodes.py:1753-1754`、`runtime_probe.py:395-398` 等 | 低 | 已属"纯观测层不阻断主流程"设计；建议统一 `logger.info` + 计数器便于观测 |
| 测试脆弱性 | 存在以 `inspect.getsource`/源码文本为断言的接线锁（例：`run_main_batch.py:394-398` 注释说明 `tests/test_batch_vi.py` 用 `inspect.getsource(main)` 锁 staging 接线） | `experiments/run_main_batch.py:396-398`（自述）；`tests/` 未逐一读 | 低 | 属"防漂移"有意设计，但会锁死重构；建议改为行为断言 |
| 依赖钉版 | `requirements.txt`/`requirements.lock`/`pyproject` 三方一致性由 `check_lock_sync.py` 守卫；实测通过（有 2 条"lock 有而 txt 无"的传递依赖警告） | 实测；`requirements.txt:53`、`requirements.lock:130` | 低 | 保持；把 yarl/zstandard 的传递依赖说明写入注释以消除警告 |
| 打包 | `dynamic = ["version"]` + `[project.scripts] aitester`；`py.typed` 随包分发 | `pyproject.toml:17, 78-79, 82-84` | — | 无问题（未重跑构建） |
| 供 LLM 用的合成数据集 | 单文件 2532 行、模板字符串内嵌测试代码 | `src/datasets/synthetic_dataset.py`（46558 行总量最大文件） | 低 | 可读性/维护性风险；不影响正确性 |

---

## 8. 领域专项诊断表

| 领域 | 结论 | 关键 file:line | 严重度 |
|---|---|---|---|
| 多智能体编排 | 有真实状态机：`planner → generator → executor →(diagnosis/cross_file)→ debugger → patch_applier → executor`，条件路由与多终止原因齐备（`workflow.py:434-561`、`determine_stop_reason` `:126-190`）；`MAX_ITERATIONS=3`（`config.py:369`）、`MAX_REGENERATIONS=1`（`:375`）、LangGraph `recursion_limit=4*MAX_ITERATIONS+8`（`workflow.py:883-914`）；无 LLM 降级路径 = 无（架构上必需 LLM；`plain_llm` 基线也走同一 generator 节点）。**"多智能体增益"已被自身数据证伪**（`BASELINE.yaml` / `README.md:72`），代码层无机制能反驳该结论 | `workflow.py:126-190, 434-561, 883-914`；`config.py:369-375` | 中（定位问题） |
| 逻辑驱动 | 见 §2：真实但受限（QF 标量、接受率 ~0.21、精化未接线、默认关） | `spec_ir_v2.py:668-719`；`spec_smt.py:14-24`；`spec_refine.py:26-28` | 中 |
| 测试生成 | 生成-执行-再生成-修复闭环完整；防"自指假成功"的多重标记齐备（`test_regenerated_pass_unverified` `nodes.py:1388-1396`、`detection_first_status` `:1407-1413`、红回归门 `:1443-1453`）；但**判别力**由 F2P 三段度量，仅 15.8% | `_m1_metrics.py:473-539` | 中 |
| 自修复 | 不成立（§3）：APR 闭环 + 回滚，无运行时自愈 | `patch_io.py:351-504`；`main.py` | 高（对外定位） |
| 闭环 | 环路存在但修复产出率低：修复率 39.31%（项目自述，工件口径）；`idle`/无补丁行早退记 0（`_m1_metrics.py:607-609`）；`abstain` 只观测不阻断 | `_m1_metrics.py:577-622`；`patch_abstain.py:23-29` | 中 |
| 评估/测量诚实度 | 指标定义清晰、None 与 0 严格区分、逐字段剔除（`analyze_results.py:717-745`）；但 ①门与指标判据分叉（§1.1）②覆盖率与检出率分母不同构且报告未点明（§1.3）③`four_channel_recompute.py:12` 把 detection_rate 标为"断言失败红"，实际含任何异常/崩溃红 ④存量工件 provenance 缺关键开关键（§6 #13） | 同左 | 高（影响 −28pp 归因） |
| 安全 | 输出侧补丁拦截真实（双通道、默认开）；执行侧默认无内核隔离、无网络隔离（§4）；输入侧注入检测默认关；历史 git 泄漏未清（`ci.yml:529-540` 自述） | `nodes.py:1759-1814`；`ci.yml:529-540` | 高 |
| 工程化 | 强（ruff/mypy/CI/门禁/工件校验/包结构）；弱点是 mypy 深度与本地临时目录 lint 假红 | §7 | 低-中 |

---

## 9. 红队：可能推翻核心假设的反例与竞争路线

1. **"多智能体净负贡献"可能被对照设计放大**：`plain_llm_df` 不是"纯 LLM"，而是**强制开启检出优先协议**的基线（`run_benchmark.py:412-419` 线程级 override），且它没有 aitester 的额外 LLM 调用（FAULT_LOCALIZER 默认 true，`fault_localizer.py:64`）与更多提示段。若把"协议 × 编排"做 2×2（而非 2 臂），−28pp 可能部分归因于"协议在单臂上更省 token/更少干扰"。代码层提供了做 2×2 的开关（`DETECTION_FIRST_ENABLE` + `build_workflow(planner,debugger,allow_regeneration)`，`run_benchmark.py:238, 414`），但基线注册表里没有"aitester 关协议"臂（`run_benchmark.py:423-430`）。
2. **"过红 = 非特异断言"这一机制叙事**可被反例推翻：本次实测证明 over_red 至少还包含"测试根本没跑起来"（收集/导入错误，含跨文件任务的系统性形态）。若把 gate 改为与 M1 同判据（排除执行错误），`specific_red/over_red` 比例会变化，`BASELINE.yaml:75-78` 的"近 2/3 非特异过红"结论会被重估（方向：over_red 减少，比例上升或下降取决于 unrunnable 行的归属）。
3. **"覆盖率无鉴别力"的反例**：项目自己引用 Zhao/Zhou/Cohen（ISSTA 2026）的**限定性**结论（`BASELINE.yaml:64`）——回归设定下覆盖+变异可做跨模型比较。若把实验改为"缺陷已注入但不可修复"的对照，覆盖率可能重新获得部分鉴别力。项目已选择"被测代码可能有缺陷"场景，该选择成立但需在论文中显式声明适用域。
4. **"逻辑驱动"可通过提高 DSL 覆盖而非提高表达力获胜**：当前瓶颈是 `spec_expr_coverage ≈ 0.72–0.74` 与 `compile_rate ≈ 0.21`（`BASELINE.yaml:70-74`），两者相乘 ≈ 0.15–0.16 的可执行规约比例。竞争路线（纯 prompt 契约 + 变异反馈）若在同样 token 预算下达到相近的"注入断言数"，则"形式化"这一层的成本收益不成立；项目自己的 E1 门（≥0.3/＜0.2，见 `BASELINE.yaml` E1 叙述）即为该反驳的判定点。
5. **"沙箱已足够"的反例**：默认 venv 档下，LLM 生成的测试代码可读写宿主文件、可联网（§4）。在公开聊天/多租户或 CI 拉取外部 PR 的场景中，这是可被直接利用的 RCE 面；内核沙箱开启后仍保留"仓库根可写"（`kernel_sandbox.py:209-211` + `executor.py:238`）。竞争路线（容器化默认开）在安全维度上严格占优，代价是每任务 ~10s 启动开销。
6. **"修复闭环可收敛"的反例**：`MAX_ITERATIONS=3` + `MAX_REGENERATIONS=1` + 字面量 0 绑定可能违反前件（`spec_ir_v2.py:457-458`）→ 注入的 oracle 断言可能在 buggy/fixed 上都失败，形成"确定性假检出"，反而消耗修复预算。`test_error_rate` 与 `regression_rate` 能观测到部分症状（`_m1_metrics.py:542-574, 649-695`），但默认不阻断。

---

## 10. 缺失 / 不可读 / 未验证说明

| 项 | 状态 |
|---|---|
| `src/specs/spec_ir.py`（v1，15837 B） | 已列目录，未逐行读完；仅通过 `spec_ir_v2.py`/`nodes.py` 的引用与 docstring 判读其角色（v1 产物解析 + 签名提取）。其内部实现细节**未验证** |
| `src/agents/executor_repo.py`（1135 行，仓库级执行） | 未读；SWE-bench repo 级路径的沙箱强度**未验证**（本文 §4 的结论只覆盖 local/venv/docker/probe 四条已读链路） |
| `experiments/run_benchmark.py` 的 `_build_task_result`（:952-1210） | 只读关键字段；`harness_invalid`（P2P 门禁）对分母的最终影响**未验证**（属 claims-auditor 复算范围） |
| 主批次工件与工作树的时序差 | 工件产自 2026-10-06/07 提交；本报告行号基于**当前工作树**（HEAD d9e51df + 33 个修改文件）。行为结论以工作树为准，数字复算以工件为准 |
| 未执行项 | 未跑全量 pytest（仅 `--collect-only`）、未跑 LLM 实验、未跑 Docker 档、未跑 `KERNEL_SANDBOX_ENABLE=true` 实链路（仅读码 + 读 profile 构造） |
| 无法判定 | `pip install` 供应链（`dependency.py:895-899`）在真实网络下的行为；`allowlist` 网络档在宿主防火墙配置下的实际效果 |

---

## 11. 与 Lead 复算的交叉核对（4 条，含代码级归因）

复算脚本：`audit_2026/_crosscheck_lead.py`（只读工件，无 LLM）。文件集 = `experiments/results/main_batch/benchmark_synthetic_2026100[67]_*.json` 共 **7 个**（3×20261006 + 4×20261007），每臂 **609 行**（7×87）。

### 11.1 detection 分子一致；分母需按"None 不计入"修正 → **部分确认**

| 臂 | 行数 | 可测（detection_rate 非 None） | 分子 det=1 | 项目口径（None 剔除） | 统一 /609 |
|---|---|---|---|---|---|
| aitester | 609 | **556**（53 行 None） | **78** ✓ 与 Lead 一致 | **78/556 = 14.0%** | 12.8% |
| plain_llm_df | 609 | **571**（38 行 None） | **279** ✓ 与 Lead 一致 | **279/571 = 48.9%** | 45.8% |
| plain_llm | 609 | 609（0 None） | 10 | 10/609 = 1.6% | 1.6% |

- 项目自身口径就是剔除 None 后作分母：`experiments/run_main_batch.py:370-374`（`m1_meas = [r for r in det if r.get("detection_rate") is not None]`，分母 `len(m1_meas)`）与 `experiments/analyze_results.py:717-745`（"None 不计入分母"逐字段剔除）。
- 结论方向不变（aitester 显著低于 df），但**三臂缺失行数不同（53 / 38 / 0）**，必须逐臂标注分母；统一按行数 609 会同时低估两臂。
- 注意该 7 批集合（14.0% / 48.9%）与 `README.md:72` 的三种子 pooled 口径（`38/240 = 15.8%` vs `117/261 = 44.8%`）是**两个不同文件集**，不可混引。

### 11.2 机制分解：296/609、93（59/34）**完全复现**；"三臂各 46" **未复现** → 定性结论成立但需换证据

| 臂 | 从未红 `all_green_unverified` | 曾红（`red_then_green`+`red_not_repaired`） | det=1 | det \| 曾红 |
|---|---|---|---|---|
| aitester | **296 / 609 = 48.6%** ✓ | 260 / 609 = 42.7% | 78 | **30.0%** |
| plain_llm_df | 15 / 609 = 2.5% | 571 / 609 = 93.8% | 279 | **48.9%** |
| plain_llm | 535 / 609 = 87.9% | 74 / 609 = 12.2% | 10 | 13.5% |

- 复现项：`all_green_unverified` = 296 ✓；其中 **296/296** 满足 `iterations==0` 且 `patch` 为空 ✓；`red_then_green` = 93，其中 det=1 **59** / det=0 **34** ✓（与 Lead 逐一相同）。
- 未复现项："红但非特异（over_red）三臂各自 46" —— 实测 4 个含 gate 数据的 logic 档批次合计：**aitester 66 / plain_llm 38 / df 140**（逐批 18,15,18,15 / 8,11,8,11 / 38,32,38,32），三臂不相等，也无 46；另 3 个非 profile 批次**该键不存在**（见 11.3）。
- 但 Lead 的**定性结论**可由上表以更强的证据支持：aitester 的"从未产生红"比例是 df 的 **19 倍**（48.6% vs 2.5%）。同时**转化率也差 18.9pp**（30.0% vs 48.9%），反事实：只对齐 red 产生率 → 28.1%；只对齐转化率 → 20.9%。故"差距主要来自是否产生红"成立，但"不是红是否特异"过强。

### 11.3 `all_green_unverified` 的确切产生分支（代码级归因）

1. **唯一写入点**：`_executor_node`，且仅当 `detection_first_enabled()`（`src/graph/nodes.py:1407-1413`）；
2. `iteration==0` 时更新**粘性** `detection_first_red_seen = (not passed) or 旧值`（`nodes.py:1408-1409`）；
3. 纯函数判定 `_derive_detection_first_status`（`nodes.py:649-672`）：`passed ∧ ¬red_seen → "all_green_unverified"`；每轮执行后写、LangGraph 后写覆盖 ⇒ 终值即终态（`nodes.py:1410-1413`）；
4. **路由**：首轮全绿（`iteration==0 ∧ ¬red_seen ∧ regeneration_count<1 ∧ execution_trace 非空`）→ `regenerate`（`src/graph/workflow.py:682-699`）；
5. **再生成不递增 iteration**（`iteration` 只在补丁/诊断路径 +1：`nodes.py:1222, 1977, 2141`）⇒ 第二版测试仍在 `iteration==0` 下执行；若第二版在缺陷原码上仍绿，`red_seen` 仍为假，且 `regeneration_count=1` 已达上限（`config.py:375`）→ `_should_debug` 落到 `done`（`workflow.py:674-699`）。
⇒ **296 行 = "初始测试与（至多一次）再生成测试都在缺陷原码上全绿"**：这是**测试生成侧失败（从未产出红）**，与修复能力无关；与 `iterations=0`、`patch` 为空完全自洽。

**"再生成覆盖首轮红"要分两层**（不能混为一谈）：
- **状态层不会忘**：`red_seen` 粘性且只在 `iteration==0` 置位（`nodes.py:1409`），再生成不清除它——所以一旦首轮红过，终态不可能再是 `all_green_unverified`。工件实测无矛盾：7 批三臂 846 行 `all_green_unverified`（296+535+15）**全部** `detection_first_red_seen=False`；三臂红态（`red_then_green`+`red_not_repaired`）合计 890 行（aitester 260 / plain_llm 74 / df 556）**全部** `True`，0 例交叉；
- **指标层会丢证**：`generated_test` 被再生成**整体替换**，而 M1 只重跑最终 `generated_test`（`experiments/_m1_metrics.py:503, 519-526`）⇒ "首轮红 → 再生成 → 变绿" 的行 det=0。**实测 34/609 行（占 `red_then_green` 的 36.6%）**即"抹红"通道。`RED_REGRESSION_GATE`（`src/tools/detection_gates.py:124-162`）正是为其设计，但在本 7 批从未生效（`red_regression_violation` 全 None，见下）。

### 11.4 gate / oracle 字段：一条**不成立**，一条**部分成立** → 逐条标注

| Lead 第 3 条 | 判定 | 实测证据 |
|---|---|---|
| `oracle_type` 全部只有 `generated_test`，无 `enhanced_generated_test` | **确认** | 7 批 × 3 臂全部 `generated_test`。**代码归因**：该标签只看 `ORACLE_ENHANCE_ENABLE` 与 `state["oracle_enhanced"]`（`experiments/run_benchmark.py:582-599`；开关默认 false，`src/graph/flags.py:56-64`；写入点 `_planner_node`，`src/graph/nodes.py:338-399`）——**与 `SPEC_ORACLE_EXEC_ENABLE`（规约 oracle 注入）无关**。故"无 enhanced"**不能**推出"逻辑通道未运行" |
| `red_regression_violation` 609 行全为 None | **确认** | 4 个含该键的批次全 None（另 3 批键不存在）⇒ 红回归门在本 7 批从未触发/未开启 |
| `specificity_gate_verdict` 609 行全为 None、门未生效 | **不成立** | 3 个 2026-10-06 批次（profile=None）**该键不存在**；4 个 2026-10-07 批次（profile=logic）键存在，aitester **106/348 非空**（`specific_red` 40 / `over_red` 66；plain_llm 4/38；df 162/140）。aitester 的 40/66 与 `BASELINE.yaml:76` 逐位一致 ⇒ 门在这 4 批**确实运行**，只是没覆盖全部 7 批 |
| （补充）`spec_oracle_verdict` / `spec_oracle_injected` | **不可判定** | 该键在 7 批结果行中**不存在**（schema 2026-10-10 才加入，`run_benchmark.py:1060-1073` 注释自述）⇒ 这 7 批"规约 oracle 是否注入"无法从工件证明，标"未验证" |

**新增的工件级证据（对 §1.1 有约束力，避免我过度声称）**：gate 判定与 M1 detection 在可执行行上**逐位一致**——
`specific_red → det=1.0` 为 **206/206（100%）**；`over_red → det=0.0` 为 **244/244（100%）**（7 批三臂合计）。即两者在"fixed 侧正常跑出 pytest 结论"时等价；**分歧只发生在"根本没跑起来"这一格**（本次实测 rc=2 → gate 判 `over_red`、M1 判执行错误→0.0）。因为两者在该格都输出"非检出"，工件层无法区分"真过红"与"从未运行"，这正是 §1.1 的口径缺口所在。

### 11.5 真实仓库基准工件：**确认且更强**

- 唯一 swe_bench / swe_bench_pro 工件 23 个（排除 `_superseded_20261010`）：**swe_bench 293 行 + swe_bench_pro 72 行** ✓ 与 Lead 一致；
- 更强的一点：不只 `detection_rate` 全为 None，而是**该键在这些行中根本不存在**（早期 schema）；`instance_code` 空 100%（两个数据集、每个工件、每个臂）。
- 代码级归因：`_compute_detection_rate` 要求 gold 材料非 None（`_m1_metrics.py:499-501`）且 `instance_code` 非空（`:506-508`）；`_extract_gold_material` 对 `source == "swe_bench"` **直接返回 None**（`:430-431`），`_gold_fixed_code` 对 swe_bench 返回 `""`（`:462-463`）⇒ 真实仓库任务在 M1 口径下**结构性不可测**，无论跑得如何。数据集侧对 `instance_code` 兜底为 issue 文本已有质量判定（`src/datasets/dataset_loader.py:394-400`）。
- 影响：SWE-bench / SWE-bench-Pro 的任何"0/20"类结论只在 `passed` 口径下成立，**与 detection/repair 无关**；把它们与合成集 M1 数字并列会误导。

---

## 附：本次实测命令与输出（摘要）

```
.venv/bin/python -m ruff --version                         → ruff 0.16.3
.venv/bin/python -m ruff check src config.py experiments   → All checks passed!
.venv/bin/python -m ruff format --check .                  → 21 files would be reformatted（全部为 audit_2026/*.py 审计脚本）
.venv/bin/python -m mypy --version                         → mypy 1.15.0 (compiled: no)
.venv/bin/python -m mypy src config.py                     → Success: no issues found in 123 source files
.venv/bin/python -m mypy src config.py --disallow-untyped-defs --no-error-summary | grep -c "error:"  → 10
.venv/bin/python -m pytest --collect-only -q               → 5317 tests collected in 3.58s
.venv/bin/python -c "import z3; print(z3.get_version_string())" → 5.1.0
.venv/bin/python scripts/gates/check_lock_sync.py          → 结果：通过（2 条传递依赖警告）
.venv/bin/python scripts/gates/check_env_budget.py --check → 183 个开关，登记 183，通过
.venv/bin/python scripts/gates/check_state_contract.py     → 通过
.venv/bin/python scripts/gates/check_zero_assert_tests.py  → 260 个测试文件，零断言 0
.venv/bin/python audit_2026/_probe_gate_vs_metric.py       → 收集错误 rc=2；specificity_verdict=over_red（两形态）
main_batch 门终审复算（4 份 logic 档工件）: aitester specific_red=40 / over_red=66
   （与 BASELINE.yaml:76 完全一致）；工件 env_snapshot 键数=37，缺 SPEC_IR_DSL_ENABLE 等键（ABSENT）
.venv/bin/python audit_2026/_crosscheck_lead.py            → 7 批/609 行：aitester det 78/556=14.0%（53 None）、
   df 279/571=48.9%（38 None）、plain_llm 10/609；all_green_unverified=296（296/296 iterations=0 且 patch 空）、
   red_then_green=93（det=1 59 / det=0 34）；over_red: aitester 66 / plain_llm 38 / df 140；
   gate×det: specific_red→det=1 206/206、over_red→det=0 244/244；red_regression_violation 全 None
swe_bench 工件普查（23 个唯一文件）: swe_bench 293 行 + pro 72 行；instance_code 空 100%、
   detection_rate 键存在数 0（早期 schema）
```
