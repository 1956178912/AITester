# N-4 真实 LLM 重型功能探针（N 轮，2026-10-17）

> **性质**：功能可达性/装配路径探针（真 LLM 执行），目标是找**功能静默失效**
> （字段恒 None / 路径从不进入 / 状态丢失 / 开关不生效）。**不作性能/质量证据**，
> 所有数字仅用于"功能是否真的跑起来"的判定。
>
> **代码快照**：冻结 worktree `/Users/wangchenyu/Workspace/AITester-n4-probe-f194d67`
> （detached HEAD=**`f194d679aaaba1c2fa97ef80fd53dbf47de203a9`**，`git status --porcelain`=0 行；
> 主仓 `AITester` 在跑批期间被并行任务修改，故全部探针在冻结快照上执行、产物写入主仓
> gitignored 的 `experiments/results/e2e_llm_probes_20261017/`）。
> **解释器/依赖**：主仓 `.venv`（Python 3.14.6）、`.env.local` 已复制进快照（gitignored，不产生 dirty）。
> **模型/价目**：deepseek-flash；成本按 `experiments/price_table.json` 标准价（$0.3/M in、$1.2/M out）上界口径。
>
> **预算/墙钟实测**：LLM 冒烟 1 次调用；7 项探针（01–06 真 LLM + 07 blocked）。
> 有效探针总墙钟 **1729s ≈ 28.8min**，总成本（标准价上界）**≈ $0.0463**（预算 $0.5；墙钟上限 90min）。
> 另有两次**中止的重跑尝试**（原因见 §6，成本未精确记账、保守 ≤$0.05），残件归档在 `_aborted_attempt1/`、`_aborted_attempt2/`（未删除）。

## 0. 结论速览

| item | 探针 | 结论 | 关键证据 |
|---|---|---|---|
| 00 | LLM 连通性冒烟 | **pass** | `--require-json` PASS，响应 `2`，2s |
| 01 | logic 档全链路 aitester ×3（QuixBugs） | **pass**（链路全部进入） | trace 节点：planner×3、generator×4、executor×7、debugger×3、patch_applier×3；`spec_compile_rate=1.0/1.0/0.0`、`spec_oracle_injected=True/True/False`、`spec_oracle_verdict=injected/injected/compiled_empty`；行内 diagnosis/patch/repair_history 非空 |
| 02 | RAG 开 aitester ×2 | **pass** | `rag_stats` 非空（含 results/max_similarity）；聚合 `rag_metrics={retrievals:4, hits:1, hit_rate:0.25, avg_max_similarity:0.9176}`；无 chromadb 错误 |
| 03 | 跨文件 synthetic level3 ×2 | **partial / defect（P2，见 D3；审计字段已由 N-5 修复）** | 任务生成正确（difficulty=3、is_cross_file=True、module_a/b/c、num_files=2/3）；但两任务**首轮即绿**（iterations=0、stop=test_passed、detection=0.0）→ `cross_file_analyzer`/多文件补丁路径**从未进入**（trace 无该节点，也无 debugger）；结果行**不含** `cross_file_deps`（审计缺口）；零 LLM stub 复现证明预置边+多文件补丁机制本身可运行（"跨文件补丁：模块 task_0000 应用失败，整体回滚"） |
| 04 | venv 执行器 aitester ×1 | **pass（快路径口径，见 §4）** | provenance `harness.execution_isolation.use_venv=true`；执行日志出现 `/tmp/aitester_sandbox_*/test_generated.py` 沙箱临时目录；本任务无缺失依赖 → venv 缓存未新建（代码快路径，非缺陷） |
| 05a | 预算停止（**USD 路径**） | **DEFECT（P0，见 D1）→ N-5 已修复复验 pass（§7.1）** | （N-4 修复前）`COST_BUDGET_ENABLE=true COST_BUDGET_USD=0.0001 COST_USD_PER_1K=0.3` 下 3 次 LLM 调用、6757 tokens 照常完成；`stop_reason=max_iterations`（非 budget_exceeded）、`token_budget_capped=false`；日志无任何预算告警。（N-5 修复后 `05a_budget_usd_after_fix/`：1 次调用/3242 tok 即触发、`stop_reason=budget_exceeded`、`consumed_usd=$0.001644`） |
| 05b | 预算停止（token 路径阳性对照） | **pass（停止通道可用）** | `COST_BUDGET_TOKENS=100` → 1 次调用后日志 "5.4 任务级预算超限…停止后续 LLM 调用"；行 `stop_reason=budget_exceeded`、`token_budget_capped=true`、Generator 降级为空测试 |
| 06 | safe 档 aitester ×1 | **DEFECT（P0，见 D2）→ N-2 修复、N-5 复验 pass（§7.2）** | （N-4 修复前）env_snapshot 四开关均生效，但 **每次执行 0.02–0.03s 即失败**（coverage=0），diagnosis 含 `sandbox-exec: unexpected symbol argument`（seatbelt 单引号 rc=65）。（N-5 修复后 `06_safe_profile_after_fix/`：`passed=True / coverage=100.0 / stop_reason=test_passed`，日志零 sandbox 错误） |
| 07 | oracle 冒烟（依赖 N-3） | **blocked** | 冻结快照无 `tests/test_oracle_independent_judging.py`、无 `oracle_suite_verdict`/`llm_suite_detection_rate` 接线 → 按任务书记 blocked，**未消耗 LLM 调用** |

> N-5 追补：D1/D2（P0）与 D3 审计字段已修复并复验（§7；真实 LLM 3 次调用 ≈$0.0033）。本表 item 结论保留 N-4 冻结快照口径，修复后状态见 §7。

## 1. 环境 / 方法

- **冻结快照**：`f194d67` 干净 worktree（`PREFLIGHT.json.git.dirty=false`、`dirty_lines=[]`）；每项批次 provenance `git_dirty=false`（见各 item `item_meta.json.batch_files[*].provenance`）。
- **协议**（除 item06 显式 safe 档外）：`AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=1 AITESTER_LLM_CACHE=0`；每项独立 `AITESTER_CACHE_NAMESPACE=e2e_llm_probes_20261017_<item>`、独立 `AITESTER_TRACE_DIR`；顺序执行。
- **探针成本裁剪（如实披露，仅关"非目标后处理测量"，不改 logic 主链路装配）**：`MAX_ITERATIONS=1`、`ENABLE_MUTATION_SCORING=false`、`BRANCH_COVERAGE_INJECT_ENABLE=false`、`MUTATION_ADVISOR_ENABLE=false`。原因：QuixBugs `bitcount` 等"缺陷实现不终止"家族在默认 `MAX_ITERATIONS=3` + 变异/O3 后处理下每任务可达数分钟，7 项顺序探针会超 90min 墙钟；该裁剪不影响本次要验的 planner/generator/executor/debugger/spec_ir/oracle/预算/沙箱装配路径，但**影响 stop_reason 分布**（多行为 `max_iterations`，详见 §3）。
- **运行入口（可复现）**：`experiments/run_e2e_llm_probes.sh`（新增，未 commit；`--root <frozen-worktree> --require-clean-root --dry-run` 可零 LLM 自检）。
- **真 LLM 冒烟**：`AITESTER_SMOKE_LLM=true ... run_smoke_llm.py --require-json` → PASS（响应 `2`）。

## 2. 逐项明细（命令 / 开关 / 墙钟 / tokens / 成本 / 关键字段）

> 数字来自各 `item_meta.json`（批次 JSON → 解析，不手写）；完整命令/环境见各 `run.log` 头部（`ITEM_ENV`/`CMD`）与 `ITEM_RESULTS.json`。

| item | 命令要点 | 开关 | 墙钟(s) | tokens | 成本($) |
|---|---|---|---|---|---|
| 01 | `run_main_batch.py --dataset quixbugs --task-limit 3 --seed 42 --baselines aitester --skip-stats` | profile=logic | 356 | 29,507 | 0.01563 |
| 02 | 同上 `--task-limit 2` | +`ENABLE_RAG=true` | 395 | 20,635 | 0.010637 |
| 03 | `run_benchmark(dataset=synthetic, task_count=2, difficulty=level3, parallel=1, deterministic)`（wrapper） | +`CROSS_FILE_ENABLE=true` | 27 | 15,280 | 0.008253 |
| 04 | 同上 quixbugs `--task-limit 1` | +`EXECUTOR_USE_VENV=true` | 312 | 6,802 | 0.003671 |
| 05a | 同上 quixbugs `--task-limit 1` | +`COST_BUDGET_ENABLE=true COST_BUDGET_USD=0.0001 COST_USD_PER_1K=0.3` | 371 | 6,757 | 0.003651 |
| 05b | 同上 quixbugs `--task-limit 1` | +`COST_BUDGET_ENABLE=true COST_BUDGET_TOKENS=100` | 12 | 3,197 | 0.00159 |
| 06 | 同上 quixbugs `--task-limit 1` | `AITESTER_PROFILE=safe`（覆盖 logic） | 252 | 4,520 | 0.00286 |
| 07 | —（blocked） | — | — | — | — |

### item01（logic 档全链路）关键 state 字段

- trace 节点事件（3 任务合计）：`planner=3, generator=4, executor=7, _should_debug=7, debugger=3, patch_applier=3` → **planner→generator→executor→debugger→patch_applier 全链路真实进入**（非字段占位）。
- 行字段：3/3 行 `diagnosis`、`patch`、`repair_history` 非空；`iterations` 均=1（受 `MAX_ITERATIONS=1` 探针裁剪影响，`stop_reason` 均 `max_iterations`）；`detection_rate` 2/3 为 None（bitcount 与一个 `*_test` 驱动行，None fail-closed 不进分母）；`spec_compile_rate` 1.0/1.0/0.0、`spec_oracle_injected` True/True/False、`spec_oracle_verdict` injected/injected/compiled_empty、`spec_expr_coverage` 1.0/0.6/0.0 → **logic 档 SPEC_IR/DSL/oracle 观测字段真实落盘**。
- 观察（非缺陷）：`P0 源码补丁证据门：本轮补丁证据等级=none（不足 gold/sbfl），已恢复原文件（拒绝写盘，patch_applied=False）` —— 证据门按设计 fail-closed 拒绝写盘（QuixBugs 无 gold/sbfl 证据），不是静默失效；说明 patch_applier 节点被真实调用但写盘被门禁拦截。

### item02（RAG 开）

- `rag_stats` 非空（结构含 `kind/results/max_similarity/avg_similarity`），聚合 `rag_metrics={"retrievals": 4, "hits": 1, "hit_rate": 0.25, "avg_max_similarity": 0.9176}`；无 chromadb/检索异常。注意命中率 25%（1/4）为数据事实，非功能失效。

### item03（跨文件，P2 缺陷 D3）

- 任务生成正确：`task_metadata` 含 `difficulty=3, is_cross_file=True, module_a_name/module_b_name/module_c_name, num_files=2/3, dep_chain`（1 例 `['module_a','module_b','module_c']`、1 例 None+`target_module=module_b`）。
- 但两任务**首轮即绿**：`passed=True, iterations=0, stop_reason=test_passed, detection_rate=0.0`（生成测试在 buggy 版上未变红）；trace 无 `cross_file_analyzer`、无 `debugger` → 跨文件修复/多文件补丁路径**从未进入**。生成测试仅 import/测试 target module（`from task_0000 import aggregate`），未覆盖跨文件调用方缺陷，是首轮即绿的直接原因。
- 结果行**不含** `cross_file_deps`（batch row schema 无该键；仅 `save_state` raw/ 会落盘）→ 跨文件行为在批次工件层面**不可审计**（审计缺口）。
- **零 LLM 最小复现**（证明机制本身可运行、不是坏代码路径）：用冻结快照的 `_write_cross_file_state` + `build_workflow()` + stub LLM 跑 synthetic level3 → 最终 state 保留 `cross_file_deps`（preset 边）、出现 `cross_file_contexts/cross_file_plan`，日志 `跨文件补丁：模块 task_0000 应用失败，整体回滚` → 多文件补丁应用/回滚链路真实存在；本批未进入是因为"测试首轮即绿"（任务/生成交互），而非节点缺失。
- 影响/建议：若 N 轮要验证跨文件修复，需强制首轮失败（更强生成或注入失败测试）并在结果行暴露 `cross_file_deps/cross_file_plan`（或默认 save_state）。

### item04（venv 执行器，快路径口径）

- provenance `harness.execution_isolation.use_venv=true`（开关生效）；日志出现 `/tmp/aitester_sandbox_*/test_generated.py` 沙箱临时目录与 `aitester_sandbox` 清理语义。
- `~/.cache/aitester/venvs/` 在本次运行时间窗内**无新建/更新**：因为本任务无缺失依赖，`_prepare_dependencies` 走"系统解释器 + PYTHONPATH 沙箱"快路径（代码设计），未触发 venv 构建 → 本次仅验证了沙箱执行链路进入，**未验证 venv 构建/安装慢路径**（限制，已披露）。若需验证 venv 构建，应选带第三方依赖的任务或 `EXECUTOR_AUTO_INSTALL_DEPS=true`（本探针未做，避免装包副作用）。

### item05a / 05b（预算停止，D1 对照实验）

| 配置 | 结果 |
|---|---|
| `COST_BUDGET_USD=0.0001` + `COST_USD_PER_1K=0.3` | **未触发**：3 次 LLM 调用、6757 tokens；`stop_reason=max_iterations`、`token_budget_capped=false`；日志无预算告警 |
| `COST_BUDGET_TOKENS=100`（阳性对照） | **正确触发**：日志 "5.4 任务级预算超限：消耗 3197 tokens / $0.0000 >= 上限（tokens=100, usd=0.0000），停止后续 LLM 调用"；行 `stop_reason=budget_exceeded`、`token_budget_capped=true`；Generator 捕获 `BudgetExceededError` 降级为空测试 |

→ 停止通道本身可用（05b）；**USD 预算参数完全不参与记账**（05a；见 D1）。

### item06（safe 档，D2）

- `env_snapshot`：`KERNEL_SANDBOX_ENABLE=true`、`PATCH_SNAPSHOT_ROLLBACK_ENABLE=true`、`INJECTION_GUARD_ENABLE=true`、`ROGUE_MONITOR_ENABLE=true`、`AITESTER_PROFILE=safe` → 档位开关**配置层生效**。
- 运行层：executor 每次调用 **0.02–0.03s 即失败**（正常 pytest ≥0.5s），`coverage=0.0`、`failed_cases=0`；`execution_trace` 两条迭代均如此；日志仅 "第 N 次执行失败，尝试重试..."（无 explicit sandbox 原因）；行 `diagnosis` 记录 `测试输出显示 'sandbox-exec: unexpected symbol argument'，这是 macOS sandbox-exec 工具在解析沙箱配置文件时失败…`。
- **最小复现（零 LLM）**：`KERNEL_SANDBOX_ENABLE=true python -c "...build_sandbox_command(...)..."` → profile 片段 `(allow file-read* (subpath '/private/tmp'))`（**单引号**）→ `sandbox-exec -p <profile> python -c 'print(1)'` → `rc=65`、stderr `sandbox-exec: unexpected symbol argument ... (subpath '/private/tmp')`。
- 结论：`AITESTER_PROFILE=safe` 在 macOS 上**执行链路 100% 不可用**（fail-closed 不裸跑，但功能等于失效，且错误只经 LLM 诊断才可见）。详见 D2。

## 3. 关键"观察 vs 期望"（证据指针）

| # | 观察 | 期望 | 证据 |
|---|---|---|---|
| O1 | `COST_BUDGET_USD` 配置后 USD 记账始终 $0.0000，永不超限 | USD 上限到点即停止后续 LLM 调用（与 token 口径一致） | `05a_budget_usd/item_meta.json` + `run.log`；对照 `05b_budget_tokens/run.log` |
| O2 | `KERNEL_SANDBOX_ENABLE=true` 时每次执行 0.02s 失败；`sandbox-exec: unexpected symbol argument` | seatbelt profile 可被 sandbox-exec 接受并执行 | `06_safe_profile/item_meta.json.rows[0].diagnosis` + 最小复现命令（§4 D2） |
| O3 | synthetic level3 两任务首轮即绿、修复路径不进入；结果行无 `cross_file_deps` | 跨文件任务应可触发 cross_file_analyzer/多文件补丁，且行为字段可审计 | `03_cross_file/*` + trace 节点计数 + stub 复现 |
| O4 | item01 3 任务 `stop_reason=max_iterations`（探针裁剪所致）；2 行 detection=None | 属探针成本裁剪与 QuixBugs 非终止家族的预期交互 | `01_logic_fullchain/item_meta.json`；§1 裁剪披露 |
| O5 | item04 无 venv 新建记录 | 无缺失依赖时按代码走系统解释器快路径 → 预期行为 | `04_venv_executor/item_meta.json.venv_cache_touched_in_window=[]` + 日志沙箱目录 |

## 4. 缺陷清单（文件:行 / 最小复现 / 观察 vs 期望 / 证据）

> 纪律：**未改源码**；以下仅立案，修复由 Lead 分派。代码行号均指冻结快照 `f194d67`。

### D1（P0）`COST_BUDGET_USD` 生产记账路径未接线 → 费用上限永不生效

> **状态（N-5，2026-10-17）：closed**——已修复并真实 LLM 复验（见 §7.1；证据 `05a_budget_usd_after_fix/`）。

- **文件:行**：`src/agents/llm_client.py:366`（`_record_response_usage` 中 `check_budget(consumed_delta_tokens=input_tokens + output_tokens)` **未传** `consumed_delta_usd`）；`src/budget/cost_budget.py:288-299`（`record_usage_and_check(input, output, usd_cost)` 支持 USD，但全仓**生产调用点为零**，仅测试传入）；`src/budget/cost_budget.py:225`（`consumed_usd += consumed_delta_usd` 恒 +0.0）。
- **观察**：`COST_BUDGET_ENABLE=true COST_BUDGET_USD=0.0001 COST_USD_PER_1K=0.3` 跑 1 任务 3 次 LLM 调用、6757 tokens，USD 记账仍 `$0.0000`，无超限、无告警；任务正常完成（`stop_reason=max_iterations`）。
- **期望**：USD 上限按 `COST_USD_PER_1K` 换算后到点触发 `BudgetExceededError`（与 token 路径 05b 同口径）。
- **最小复现**：
  ```bash
  # 冻结快照内（真 LLM，1 任务）
  COST_BUDGET_ENABLE=true COST_BUDGET_USD=0.0001 COST_USD_PER_1K=0.3 \
  AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=1 \
  AITESTER_CACHE_NAMESPACE=n4_d1 \
  .venv/bin/python experiments/run_main_batch.py --dataset quixbugs --task-limit 1 --seed 42 \
    --baselines aitester --output-dir /tmp/n4_d1 --skip-stats
  # → 行 stop_reason=max_iterations（非 budget_exceeded），日志无"预算超限"
  ```
  证据：`05a_budget_usd/`（本目录）与 05b 阳性对照。
- **影响**：批次级成本治理里"USD 口径"是纸面开关——用户以为设了费用上限，实际完全不设防（仅 token 口径可生效）；与 `src/budget/batch_quota.py` 的预检口径也不一致（预检按 USD 评估）。
- **附带**：`budget.consumed_usd` 永远为 0 会让 `check_budget` 日志/观测面失真（"USD 侧未触发"不可区分"没花钱"与"没记账"）。

### D2（P0）`KERNEL_SANDBOX_ENABLE=true` / `AITESTER_PROFILE=safe` 在 macOS 上执行链路 100% 失败（seatbelt profile 单引号语法错误）

> **状态（N-5，2026-10-17）：closed-by-N-2 + 复验通过**——N-2 修复 kernel_sandbox/profile 与执行器接线；N-5 safe 档真实 LLM 复验通过（见 §7.2；证据 `06_safe_profile_after_fix/`）。

- **文件:行**：`src/agents/kernel_sandbox.py:124-126`（`f"(allow file-read* (subpath {path!r}))"` / write 同款）与 `:137`（`process-exec` 同款）——Python `repr()` 输出**单引号**字符串，而 Seatbelt profile（SBPL）字符串字面量只接受**双引号**。
- **观察**：`AITESTER_PROFILE=safe` 下 executor 每次 0.02–0.03s 失败、coverage=0；行 `diagnosis` 记录 `sandbox-exec: unexpected symbol argument`；最小复现（零 LLM）：
  ```bash
  KERNEL_SANDBOX_ENABLE=true .venv/bin/python - <<'PY'
  from src.agents.kernel_sandbox import build_sandbox_command
  cmd, obs = build_sandbox_command(["/usr/bin/python3", "-c", "print(1)"], cwd="/tmp")
  import subprocess; r = subprocess.run(cmd, capture_output=True, text=True)
  print(r.returncode, r.stderr[:400])
  PY
  # → rc=65；stderr: sandbox-exec: unexpected symbol argument ... (subpath '/tmp')
  ```
- **期望**：`sandbox-exec -p <profile>` 正常执行；若平台不支持，应**明确降级/明确报错**（`kernel_sandbox_unavailable`）而不是让每个 executor 调用以 0.02s "测试失败"形态静默重试。
- **影响**：safe 档（安全敏感档）在 macOS 上等于"执行链路不可用"——所有测试执行失败，修复循环失效；且错误仅在 LLM diagnosis 文本中可见（日志只显示"第 N 次执行失败，尝试重试"），消耗 LLM 调用去做"诊断沙箱报错"；`PATCH_SNAPSHOT_ROLLBACK`/`INJECTION_GUARD` 的运行时证据也因此无法在本探针中取得（执行前置即失败）。fail-closed 本身符合设计（未裸跑），但**可用性与可诊断性**都失效。
- **旁注（避免重复立案）**：主仓工作树（本批开始后被并行任务修改）里 `src/agents/kernel_sandbox.py` 的 WIP diff 已写明同因（`repr()` 单引号 → rc=65）并新增 `_sbpl_quote`/解释器放行面/`sandbox_launch_failure` 等修复**未验证**（属其他任务写域；本报告只对冻结快照 `f194d67` 立案）。另：即使修复引号，`_execute_sandboxed` 当前 `allowed_paths=[sandbox_dir, sys.executable]` 对 venv 解释器/框架路径的 exec 放行面可能仍不足（WIP 注释提及 `execvp() ... Operation not permitted`），建议修复后由 N 轮复验 item06。
- **证据**：`06_safe_profile/`（行 diagnosis/execution_trace/日志/env_snapshot）。

### D3（P2）跨文件修复路径：默认生成下不可达 + 结果行审计字段缺失

> **状态（N-5，2026-10-17）：审计字段部分 closed**——结果行新增 `cross_file_enabled`/`cross_file_deps`/`cross_file_plan_present`（成功/失败分支键位一致）；"默认生成下不可达"属生成域设计问题，未在本卡修复（见 §7.3）。

- **文件:行**：`experiments/run_benchmark.py:732`（`cross_file_deps` 仅出现在 `_dump_state_artifacts` 的 **raw/** 落盘 dict；`_build_task_result` 的批次行 **无** 该键 → 批次工件不可审计）；`src/graph/workflow.py:483-517`（`cross_file_analyzer` 只在 executor 失败后的 debug 路由进入，属设计）；`src/graph/nodes.py:1726+`（节点本身正常）。
- **观察**：synthetic level3 ×2 任务 `is_cross_file=True`、`difficulty=3`，但首轮生成测试即绿（iterations=0、stop=test_passed、detection=0.0）→ `cross_file_analyzer`/多文件 `patch_applier` **从未进入**（trace 无该节点）；批次行无 `cross_file_deps`，跨文件状态仅 trace/raw 可见。
- **期望**：跨文件任务应能被探针观测到"依赖图是否注入/多文件补丁是否尝试"；若任务首轮绿导致路径不可达，应在结果行以字段（`cross_file_deps`/`cross_file_plan`）或显式 reason 暴露，而非仅 raw/ 落盘。
- **最小复现**：本目录 `03_cross_file/`（命令/元数据/trace）+ 零 LLM stub 复现（见 §2.3）：预置边与多文件补丁回滚机制本身可运行 → 说明是"路径可达性/审计面"问题，不是机制缺失。
- **影响**：中级——不改变已有主指标数字（跨文件 A/B 已有结论），但 N 轮若要再验跨文件修复，当前探针设计无法直接判定"路径是否工作"；修复方向：结果行透出 `cross_file_deps/plan`（或默认对跨文件任务 `save_state`），并给"首轮绿→修复路径不可达"一个显式审计字段。

### D4（P3，与 D2 同源）沙箱启动失败不可诊断

- 观察：safe 档执行失败时日志仅"第 N 次执行失败，尝试重试..."，`kernel_sandbox_obs`/沙箱 stderr 未进日志或结果行（只被 LLM Debugger 解读进 `diagnosis`）；operator 无法从日志/批次行直接区分"测试失败" vs "沙箱不可用"。
- 期望：`_execute_sandboxed` 早退（kernel_sandbox_unavailable）应写 `error_info.type=kernel_sandbox_unavailable` 并进入结果行/日志（WIP 已有 `sandbox_launch_failure` 方向）。
- 影响：低-中（可诊断性）；与 D2 一并修复更经济。

## 5. 未发现静默失效的路径（pass 证据）

- logic 档全链路（planner/debugger/patch_applier/SPEC_IR/DSL/oracle 观测字段/repair 字段/stop_reason/trace）真实进入并落盘（item01）。
- RAG 检索链路（rag_stats/检索次数/命中率）真实工作（item02）。
- venv 沙箱执行链路进入（item04；快路径口径已披露）。
- token 预算停止通道（positive control）真实工作（item05b）。
- LLM 连通性冒烟（item00）。

## 6. 执行历史（透明披露，含两次中止）

- **attempt#1（主仓工作树，2026-10-17T14:46–14:50Z）**：起动后发现主树被并行任务在途修改（`src/graph/nodes.py`、`experiments/_m1_metrics.py`、`src/agents/kernel_sandbox.py` 等 = 后续 N-2/N-3 正在写的文件，恰是探针要验的路径），且各 item 为独立进程顺序执行，源码中途变化会让证据不可归因 → **主动中止**（约 8min，未产出批次 JSON，无法精确成本记账，保守 ≤$0.05）；残件 `_aborted_attempt1/`。
- **attempt#2（主仓 → 冻结快照首跑，15:02–15:20Z）**：item01 在 QuixBugs `bitcount`（已知"缺陷实现不终止"家族）上反复触发 30s/60s 执行超时，默认迭代/后处理设置下 7 项顺序探针会超 90min 墙钟 → **主动中止**，改为在冻结快照上启用"探针成本裁剪"（§1）重跑；残件 `_aborted_attempt2/`。
- **attempt#3（冻结快照，15:01–15:30Z，正式结果）**：7 项顺序执行完成，总墙钟 **1729s（28.8min）**，总成本 **≈$0.0463**；全部 item 退出码 0（item07 blocked 不消耗）。
- 纪律：未 commit、未改源码、未删除既有工件；中止残件归档未删；跑批期间孤儿进程巡检 `detect_orphan_procs.py --min-age 60` 多次 0 泄漏。
- **产物终检（2026-10-17T15:33Z）**：检出 1 个孤儿 pytest（PID 24159，ppid=1，age 32m33s，100% CPU，命令 `pytest /tmp/tmpo12l918e/test_mutant.py`；起于 attempt#2 中止时被终止父进程遗留的 mutation-testing 子进程，属 M-3 已知族）。已按 M-3 纪律先记录 PID/命令/etime/CPU（`PROC_HYGIENE.md`）再 SIGTERM 清理，复检 0 泄漏。**注意**：中止重跑时对父进程的终止无法保证回收已分离 session 的孙进程，故本轮出现 1 例孤儿（已如实记录/清理，未影响任何探针证据）。

## 7. N-5 修复与复验（2026-10-17）

> 背景：N-4 立案 D1/D2（P0）与 D3（P2）；N-5 由 hardener-dev 在主树执行修复
> + 真实 LLM 复验（≤4 次调用）。所有修复均未 commit（Lead 统一提交），
> 复验证据与 N-4 冻结快照工件**同目录分项存放**（前缀 `*_after_fix/`），不改历史工件。

### 7.1 D1（P0）COST_BUDGET_USD 生产记账未接线 → 已修复并复验

**根因**（与 §4 D1 一致）：`src/agents/llm_client.py::_record_response_usage`
只传 token 增量，`consumed_delta_usd` 恒 0 → `BudgetSnapshot.consumed_usd` 恒 0
→ USD 上限永不触发；`cost_budget.record_usage_and_check(usd_cost=...)` 全仓生产
零调用。

**修复**（diff 摘要）：
1. 新增 `src/budget/pricing.py`：`estimate_usd(model, in_tokens, out_tokens)` 按
   `experiments/price_table.json`（模型级 USD in/out 每百万 token 价）计算 USD；
   价目缺失回退 `COST_USD_PER_1K`；两者皆无返回 `(None,"unpriced")`（**不编造价格**）。
   非 USD 币种（如 qwen-long CNY）不换算，按无美元价目处理（诚实条款）。
2. `src/budget/cost_budget.py`：USD 上限判定去掉历史 `COST_USD_PER_1K > 0` 前置闸
   （该闸 + 生产零 usd 记账共同构成"纸面开关"）；新增进程级审计计数
   `usd_pricing_unavailable_events` + 每模型一次性 WARNING
   `note_usd_pricing_unavailable()`；`BudgetExceededError` USD 口径消息改为
   `$x >= $y`（此前会把 token 数当美元展示）。
3. `src/agents/llm_client.py`：预算启用时计算 USD 增量并走
   `record_usage_and_check(input, output, usd_cost=...)` 生产入口；token 与 USD
   共用同一 `budget.exceeded` 停止通道（`BaseAgent._call_llm` 前置守卫抛
   `BudgetExceededError`）；`COST_BUDGET_ENABLE=false` 零行为差异（不做价目 IO）。
4. `src/agents/base_agent.py::_budget_exceeded_error()`：按生效单位取数
   （usd → consumed_usd/usd_limit），修复 USD 触发时异常消息单位错位。
   （说明：该文件不在 N-5 原始写域清单内，属"错误信息可诊断"要求的最小连带修复。）

**修复前后对照（真实 LLM，同场景 `COST_BUDGET_USD=0.0001 COST_USD_PER_1K=0.3`）**：

| 观测 | N-4 修复前（`05a_budget_usd`，冻结快照 f194d67） | N-5 修复后（`05a_budget_usd_after_fix`，主树） |
|---|---|---|
| LLM 调用/Token | 3 次 / 6757 tok 照常完成 | **1 次 / 3242 tok 即触发** |
| `stop_reason` | `max_iterations` | **`budget_exceeded`** |
| `token_budget_capped` | false | **true** |
| `consumed_usd` | 恒 0（日志无预算告警） | **$0.001644 ≥ cap $0.0001**（日志 `5.4 任务级预算超限：消耗 3242 tokens / $0.001644 >= 上限（tokens=0, usd=0.0001）`） |
| 停止通道 | 未触发 | Generator/Debugger 调用被拒：`LLM 预算耗尽：已消耗 $0.001644 >= 上限 $0.000100（美元口径）` |
| 行 diagnosis | 无预算语义 | `... 已消耗 $0.001644 >= 上限 $0.000100（美元口径）`（单位正确） |

证据：`05a_budget_usd_after_fix/`（`run.log` + `benchmark_quixbugs_*.json` + `item_meta.json`）；
对照：`05a_budget_usd/`（N-4，冻结快照）。token 通道阳性对照（05b）仍通过，未回归。

**回归测试**：`tests/test_n_round_budget_usd.py`（23 例）：价目估算（命中/非 USD/
未登记/缺失文件/坏 JSON/回退价/零与负 token）、预算累计触发（无 per_1k 仍触发、
disabled 零差异、坏 per_1k fail-closed）、生产接线（priced→consumed_usd 非 0 且触发、
token/USD 同停止通道、disabled 不触价目、未计价审计事件+WARNING、回退价、pricing
异常 fail-closed、多 provider 缺价策略、异常消息单位）、既有 `test_cost_budget*`
两处旧口径断言极小化同步（旧 USD 前置闸语义已废弃，测试注释说明）。

### 7.2 D2（P0）safe 档执行链路 → 已由 N-2 修复，N-5 复验通过

**修复归属**：N-2（kernel_sandbox SBPL 双引号/根目录放行/解释器放行面/`.venv`
DENY 正则/错误分类；证据 `../e2e_probe_platform_20261017/`）。本项只做复验。

**复验（真实 LLM 1 次调用；`AITESTER_PROFILE=safe` 最小任务）**：
`AITESTER_PROFILE=safe` + `synthetic__task_0000`（plain_llm_df）：
- env_snapshot 四开关生效：`KERNEL_SANDBOX_ENABLE/PATCH_SNAPSHOT_ROLLBACK_ENABLE/
  INJECTION_GUARD_ENABLE/ROGUE_MONITOR_ENABLE=true`，profile=safe；
- **行 `passed=True` / `coverage=100.0` / `stop_reason=test_passed` / `diagnosis=None`**；
- 日志 **零** `sandbox-exec` 错误 / 零执行超时（N-4 旧快照每 0.02–0.03s 失败、coverage=0、
  diagnosis 含 `sandbox-exec: unexpected symbol argument`）。

证据：`06_safe_profile_after_fix/`（`run.log` + `benchmark_synthetic_*.json` + `item_meta.json`）；
对照：`06_safe_profile/`（N-4，冻结快照）。

### 7.3 D3（P2）跨文件结果行审计字段 → 已修复

**修复**：`experiments/run_benchmark.py::_build_task_result` 成功/失败两分支统一展开
`_cross_file_audit_fields(final_state)`，新增三键（纯观测，不改判分口径）：
`cross_file_enabled`（运行时 CROSS_FILE_ENABLE，异常 None）、
`cross_file_deps`（终态依赖边；失败分支 None）、
`cross_file_plan_present`（终态是否有 cross_file_plan；失败分支 False）。
成功/失败分支键位一致；失败分支不臆造空依赖列表。

**未修部分**：item03 的"默认生成下跨文件修复路径不可达"（LLM 生成任务首轮即绿、
修复循环不进入）属**生成域设计问题**，不在 D3 审计字段修复范围；需另立生成侧任务
（如默认 difficulty≥3 强制造红/强制收集多文件证据）——本卡如实保留。

**工件层前后证据**：
- N-4 旧工件 `03_cross_file/benchmark_*.json` 行内三键**全部缺失**
  （检查 `cross_file_enabled`/`cross_file_deps`/`cross_file_plan_present` → 均 False）；
- N-5 复验工件 `05a_budget_usd_after_fix/` 与 `06_safe_profile_after_fix/` 行内三键**均在场**
  （非跨文件任务：`cross_file_enabled=false`、`cross_file_deps=null`、`cross_file_plan_present=false`）。

**回归测试**：`tests/test_n_round_cross_file_audit.py`（11 例）：helper 默认值/开关
反映/异常降级/成功态 deps+plan/空 plan/脏数据保守 None/不修改 state，成功与失败
分支结果行均含三键且判分字段不变。

### 7.4 复验成本（真实 LLM）

| 项 | 调用 | tokens | 估算成本（deepseek-flash 标准价） |
|---|---|---|---|
| `05a_budget_usd_after_fix` | 1 | 3242（in 2496/out 746） | ≈$0.0016（该次调用即超 USD cap $0.0001；真实花费不因 cap 回滚） |
| `06_safe_profile_after_fix` | 2 | 2125（in 937/out 1188） | ≈$0.0017 |
| 合计 | **3**（≤4 预算内） | 5367 | **≈$0.0033**（≤$0.05 预算内） |

### 7.5 剩余风险

- USD 计价为**价目表标准价估算**（非供应商账单）；缓存命中/错峰价未折减（保守上界）。
- 无美元价目的 provider（未登记/非 USD）不参与 USD 上限判定，仅审计计数+WARNING
  ——"USD 上限未触发"仍可能意为"该 provider 无法计价"，需看
  `usd_pricing_unavailable_events`。
- `COST_BUDGET_ENABLE=true` 但既无 token 上限也无 USD 上限时仍是"不设闸"（历史口径，
  有一次性 WARNING，未改变）。
- D3 只补审计字段；跨文件"默认生成下不可达"待生成侧任务。

## 8. 局限

- **单模型/单数据集/单 seed**（deepseek-flash；QuixBugs + synthetic；seed=42）；功能探针不产生性能/质量结论。
- 探针成本裁剪（MAX_ITERATIONS=1 等）改变了 `stop_reason` 分布与"迭代/修复轮数"字段，不等于生产默认配置；如需生产口径的 stop_reason/修复轮数证据需另跑（成本更高）。
- item03 的"首轮即绿"与生成任务设计/LLM 输出相关；本批未做多次重采样/seed 扫描，不能断言所有 L3 任务都不会进入修复路径。
- item06（N-4）只验证到"执行前置即失败"；**N-5 已在主树复验 safe 档执行链路 passed/coverage=100**（§7.2），但注入守卫/回滚的**运行时拦截行为**仍未构造专门探针（本次仅观测开关生效与执行可用）。
- 成本记账为价目表标准价上界（非账单）；两次中止尝试未精确记账（保守 ≤$0.05，未计入 $0.0463）。
- item07 blocked：oracle 独立判读接线属 N-3，需 N-3 提交后另跑（≤3 调用即可）。

## 9. 复现命令

```bash
# 0) 冻结快照（若已删除可重建）：
git -C /Users/wangchenyu/Workspace/AITester worktree add --detach \
  /Users/wangchenyu/Workspace/AITester-n4-probe-f194d67 f194d67
cp -p /Users/wangchenyu/Workspace/AITester/.env.local \
  /Users/wangchenyu/Workspace/AITester-n4-probe-f194d67/.env.local

# 1) 零 LLM 自检：
bash experiments/run_e2e_llm_probes.sh \
  --root /Users/wangchenyu/Workspace/AITester-n4-probe-f194d67 --require-clean-root --dry-run

# 2) 正式探针（顺序，真 LLM；产物写主仓 results，gitignored）：
bash experiments/run_e2e_llm_probes.sh \
  --root /Users/wangchenyu/Workspace/AITester-n4-probe-f194d67 --require-clean-root

# 3) 关键缺陷最小复现（零 LLM）：
#    D1: 见 §4 D1 命令
#    D2: KERNEL_SANDBOX_ENABLE=true ... build_sandbox_command(...) → sandbox-exec rc=65（§4 D2）
```

## 10. 文件与完整性

| 路径 | 说明 |
|---|---|
| `PREFLIGHT.json` | 代码根/HEAD/dirty、LLM 冒烟、N-3 就绪判定 |
| `ITEM_RESULTS.json` / `.md` | 逐项汇总（脚本直出：tokens/成本/字段 None 计数/trace 节点/日志关键词） |
| `00_llm_smoke/` | 真 LLM 冒烟 log（1 次调用） |
| `01_logic_fullchain/` … `06_safe_profile/` | 每项 `benchmark_*.json` + `run.log` + `traces/` + `item_meta.json`（+ `.rc`） |
| `05a_budget_usd_after_fix/` | N-5 D1 复验（真实 LLM）：USD cap 触发停止通道；`run.log` + `benchmark_*.json` + `item_meta.json` |
| `06_safe_profile_after_fix/` | N-5 D2 复验（真实 LLM）：safe 档执行器 passed=True/coverage=100；`run.log` + `benchmark_*.json` + `item_meta.json` |
| `07_oracle_smoke/item_meta.json` | blocked 记录（N-3 未就绪；未消耗 LLM） |
| `_aborted_attempt1/`、`_aborted_attempt2/` | 两次中止尝试的残件（未删除，见 §6） |
| `_helpers/` | 看门狗/证据抽取/汇总/跨文件 wrapper（runner 生成，随工件归档） |
| `PROC_HYGIENE.md` | 产物终检孤儿 pytest 巡检/人工确认/清理记录（只读巡检→SIGTERM） |
| `SHA256SUMS` | 本目录全部工件 sha256（`shasum -a 256 -c SHA256SUMS`） |

> 交接：D1/D2（P0）与 D3 审计字段已由 N-5 修复/复验（§7，closed）；D3 的"默认生成下跨文件修复不可达"待生成侧任务。N-5 未 commit，修复 diff 见主树工作区。
