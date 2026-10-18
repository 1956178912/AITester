# T4 / T 轮 2026-10-18：语义修复批次（A-19 抢占优先级 + 回滚 verdict schema + 预检探针修复 + D3b 处置）

> 执行者：T4（semantic-fixes）；工作根：`/Users/wangchenyu/Workspace/AITester`（main，未 commit）。
> 共享任务：task-3。写入范围：`src/graph/workflow.py`、`src/graph/state.py`、
> `scripts/tools/run_preflight.py`、`experiments/run_benchmark.py`（**范围外，见 §7.1**）、
> `tests/`、`scripts/tools/e2e_probes_logic.py`（Lead 追加授权）、
> `experiments/run_t4_a19_revalidation.sh`、本结果目录。未跑真实 LLM 主批（留 Lead 切点执行）。

## 0. 摘要

| # | 交付 | 状态 | 关键证据 |
|---|---|---|---|
| 1 | **A-19 抢占优先级修复**：默认闸协议下 repair-invalid 与停滞窗口同迭代收敛时，停滞判定优先（仅 `COVERAGE_STALL_DETECT_ENABLE=true`；默认关逐位零变化） | ✅ 完成 | 改动前黄金行为表 18 行逐位一致；`tests/test_t_round_semantic_fixes.py` 34 例；复验脚本 + PREREG + 零 LLM 判定自测 4/4 |
| 2 | **回滚 verdict schema**：结果行新增 `patch_rollback_verdict` / `patch_rolled_back`（成功分支 state 投影、失败分支 `(None, False)`，纯观测） | ✅ 完成 | 双分支键集合同构（93 键）+ 三态投影 + JSON 落盘测试；e2e 探针 `logic-rollback-schema-fields` pass |
| 3 | **`run_preflight.py::quota_probe` 不存在符号修复**：`LLMClient` ImportError → 真实可用探测（`import config` → `_get_llm_config` → `_get_or_create_chat_client` → `.invoke`） | ✅ 完成 | 修复前实测 ImportError（日志已存）；修复后真实 `--check-quota` = `ok=True`（1 次真实调用）；monkeypatch 回归 7 例零真实调用 |
| 4 | **D3b 跨文件接线** | ✅ 按纪律只出设计+预注册（不硬改） | `D3B_DESIGN_AND_PREREG_DRAFT.md`：定位到下游消费点（debugger `_resolve_target_module`）⇒ 接线必改 LLM 调用/路由 |
| 5 | **新功能 e2e 探针（Lead 追加）**：`logic-stagnation-precedence` / `logic-rollback-schema-fields` | ✅ 完成 | 探针注册 66→68；`--group logic` 20 探针 19 pass / 1 skip（LLM 探针）/ 0 fail；负控 2 例 |

## 1. A-19 抢占优先级修复（`src/graph/workflow.py`）

### 1.1 缺陷（S-2 登记，本批落地）

生产默认协议（`PATCH_EVIDENCE_GATE_ENABLE=true`）下证据门反复拒绝写盘 →
`repair_history` 连续 `patch_applied=False`；`repair-invalid` 与停滞窗口
（K=2 轮 `|coverage_delta|<eps`）在**同一迭代**收敛。修复前 `_should_debug`
的 repair-invalid 分支先 `return done`，函数末尾的停滞短路永不执行 ——
ON 臂的 `coverage_stall` 只是 `determine_stop_reason` 的**标签兜底**：

- S-2 默认闸冒烟实测（`experiments/results/s_round_b8_injection_20261018/_harness_smoke/log_smoke_on.log`）：
  stall 日志 **0** 条、"连续多次修复无效" **2** 条，但 stop_reason 仍是 `coverage_stall`；
- 即 A-19 在默认协议下"只改标签、不省迭代"（ON/OFF 均 iterations=2）。

### 1.2 改动（最小、开关受限）

`src/graph/workflow.py::_should_debug`：把 repair-invalid 分支拆为
`_repair_invalid_hit`，命中时若 `_coverage_stall_enabled()` 且
`_coverage_stall_detected(state)` 为真 → **停滞优先**（日志写"同迭代优先于
repair-invalid"、`stop_reason=coverage_stall`、trace 打点 `preempted=skip_debugger_repair_invalid`）；
否则走历史 repair-invalid 分支。函数末尾原停滞短路保留（非平局路径）。

- **仅当停滞开关 ON 生效**：OFF（默认、未设 env）时 `_coverage_stall_enabled()` 恒 False
  → 守卫不可达，路由/标签/日志与历史逐位一致。
- **不改变迭代数**：平局止于同一迭代，本修复**不承诺**迭代节省（省迭代收益仍来自
  gate-off 场景的尾部短路）。README/PREREG 均以此为准，禁止外推为收益。
- 同步更新：`_should_debug` docstring（路由顺序含停滞优先）、P2-4 模块注释、
  末尾停滞短路注释、`StopReason.COVERAGE_STALL` 说明；`src/graph/state.py`
  `stop_reason` 注释补 `coverage_stall`（纯注释同步，无行为）。

### 1.3 零行为证据（改动前黄金表）

| 项 | 值 |
|---|---|
| 生成器（**改动前**运行） | `_evidence/gen_off_golden_table.py`（零 LLM） |
| 冻结表 | `_evidence/off_golden_table_before.json`（18 行状态矩阵） |
| sha256 | `591c93d8f8facb346ff72923d7914b45500316c5b2587b1d2cd685d718231f94` |
| 表内容 | 每行：env 覆盖 / state / `decision` / `stop_reason` / 变更键集合 / `_trace_node` 调用序列 / 日志文案 |
| 修复后比对 | `tests/test_t_round_semantic_fixes.py::TestOffGoldenTable` 18 行 **全部一致** |

矩阵覆盖：test_passed / budget / regression / test_defect 再生成与上限 /
repair-invalid（早期、达上限）/ 关键词 regenerate（早期、上限已满）/ 停滞 trace
（OFF 下与无停滞 trace 行为一致）/ 增长 trace / 检出优先 / 特异性门。
即"默认关路径逐位零变化"由**改前生成、改后比对**锁定，非事后自证。

### 1.4 ON 语义测试（`tests/test_t_round_semantic_fixes.py::TestA19PriorityPreemption`）

- 平局 + ON：`done` + `stop_reason=coverage_stall` + 日志为停滞优先文案（且无
  "连续多次修复无效"）+ trace 含 `preempted`；**迭代数不变**（ON/OFF 均 iteration=2）；
- 平局 + OFF：`done` + `skip_debugger_repair_invalid` + 历史日志（零变化）；
- 平局 + ON 但覆盖率仍显著变化（不判停滞）：repair-invalid 语义不被改写；
- 非平局 + ON（无 repair-invalid）：尾部停滞短路照旧；
- 范围限定：ping 局中排在 repair-invalid 之前的特异性门再生成不被抢占；
- 结构锁：守卫条件必须与 `_repair_invalid_hit` 合取、且位于 repair-invalid 主体之前。

### 1.5 真实 LLM 复验（脚本/预注册已就绪，**执行留 Lead**）

| 文件 | 说明 |
|---|---|
| [`../../run_t4_a19_revalidation.sh`](../../run_t4_a19_revalidation.sh) | 复用 S-2 注入 harness，两臂并发、**默认证据门**（不设 `--extra-env PATCH_EVIDENCE_GATE_ENABLE=false`），唯一差异=停滞开关；跑后零 LLM 判定写 `ANALYSIS.json` |
| `A19_REVALIDATION_PREREG.md` | 跑前冻结预注册（sha256 `83a8a645732efe6fddb168227e8efbb0833dfc0fd136057030350126bc31368c`）；判据 P1 分支归属 / P2 默认关零变化 / P3 **零迭代节省（负向预注册）** / P4 harness 有效性 |
| `_evidence/selftest_revalidation_analysis.sh` | 用**构造工件**自测脚本判定逻辑：4/4（正例→confirmed_priority；修复前工件→not_confirmed；Δ≠0→unexpected_delta；注入缺失→not_confirmed） |
| `_evidence/revalidation_analysis_selftest.log` | 自测输出（零 LLM） |

用法（Lead 在干净切点 worktree 上）：

```bash
bash experiments/run_t4_a19_revalidation.sh \
  --root <干净切点 worktree> --expect-sha <cutpoint-sha> \
  --out experiments/results/t_round_a19_default_gate_20261018 \
  --tasks 10 --seed 42 --parallel 4 --inject-rounds 3
# 预检（零 LLM，允许脏树）：加 --dry-run；严格判定：加 --strict
```

预期（预注册）：P1 满足（ON 臂 10 次停滞优先日志）、P2 满足、P3 **Δ=0**、
P4 满足 → `confirmed_priority`。预算上界 **≤$0.15**（参考 S-2 冒烟 ≈$0.08）。
**本目录未执行真实 LLM 复验**（纪律：留 Lead 切点批次；本批期间 B2 主批次在跑）。

## 2. 回滚 verdict 结果行 schema（O 轮登记项落地）

### 2.1 改动

`experiments/run_benchmark.py::_build_task_result`（**列于任务写入范围之外，见 §7.1**）：

- 成功分支：`"patch_rollback_verdict": final_state.get("patch_rollback_verdict")`、
  `"patch_rolled_back": final_state.get("patch_rolled_back")`（纯投影，不参与路由；
  写盘源点仍是 `src/graph/nodes.py::_patch_applier_node`，未改）；
- 失败分支（无 final_state）：`patch_rollback_verdict=None`（不可判定/未执行）、
  `patch_rolled_back=False`（明确未发生回滚）。

**语义表**（写入行注释）：`verified / regression_failed / no_oracle / regression_error /
apply_failed / not_enabled`；`None` = 本轮未走 patch_applier（无补丁/未进修复环，
与 `not_enabled`"开关关"区分）；`True` = P2P 回归失败且磁盘恢复成功；`False` = 执行但未回滚。

### 2.2 测试证据（`tests/test_t_round_semantic_fixes.py::TestRollbackVerdictRowSchema`）

- 成功行投影（`regression_failed`/`True`）；`not_enabled`/`False`；无键状态 → `None/None`；
- 失败行占位 `(None, False)`；成功/失败**键集合同构**（93 键 = 93 键）；
- JSON 落盘验证：`json.dumps({"details":[row]})` 写文件再读回，两键保真。

e2e 探针 `logic-rollback-schema-fields`（见 §5）执行同一组断言（isolated 子进程）→ pass。

## 3. 预检探针缺陷修复（`scripts/tools/run_preflight.py::quota_probe`）

### 3.1 缺陷与修复

旧实现 `from src.agents.llm_client import LLMClient` 引用**不存在的符号**
（该模块只有 `_get_llm_config()` / `_get_or_create_chat_client()`）→ `--check-quota`
恒 ImportError → `skipped=True` → strict 模式下"配额闸自身坏了"阻断一切批次前置闸
（B2/T1 批次实证）。

修复（最小真实路径，与 BaseAgent 同一入口）：
`import config`（触发 .env/.env.local 加载）→ `_get_llm_config()` 取
`(api_key, base_url, model_name)` → `_get_or_create_chat_client(model, 0.0, api_key, base_url)`
→ `.invoke("Reply with the single token: OK")`。三态语义保持：
无凭证/配置不完整 → `skipped=True`；调用异常 → `ok=False, skipped=False`；
成功 → `ok=True`。附带把凭证检查移到 config 加载之后（开发者直接跑也能识别 .env.local）。

### 3.2 修复前后实测

| 项 | 修复前（`git show HEAD:` 原文件复跑） | 修复后 |
|---|---|---|
| 命令 | `run_preflight.py --check-quota --strict`（导出 .env.local LLM_1_*，不打印值） | 同左 |
| 配额探测输出 | `{'ok': False, 'skipped': True, 'reason': '导入 LLMClient 失败：ImportError'}` | `{'ok': True, 'skipped': False, 'response_prefix': 'OK', 'model': 'deepseek-flash'}` |
| 阻断项 | 含"配额/连通性探测未通过：导入 LLMClient 失败：ImportError" | 无配额项（仅剩工作树 dirty / 预算未配置项=本次 ad-hoc 调用预期） |
| 证据 | `_evidence/preflight_before_fix_check_quota.log` | `_evidence/preflight_after_fix_check_quota.log`（**真实 1 次 LLM 调用**，本批唯一真实调用） |

### 3.3 零真实调用回归（`tests/test_batch_quota_preflight.py::TestQuotaProbe`，7 例）

AST 级回归锁（不得再 import `LLMClient`，且真实模块确无该符号）、
无凭证 skipped、成功路径经 `_get_llm_config`/`_get_or_create_chat_client`
（断言入参 model/temperature=0.0/key/base_url 与 prompt）、配置不完整 skipped、
调用异常 `ok=False+skipped=False`、非 OK 回复 `ok=False`、strict 下探测失败仍退出码 1。

## 4. D3b 跨文件接线处置（设计+预注册，不实跑）

详见 [`D3B_DESIGN_AND_PREREG_DRAFT.md`](D3B_DESIGN_AND_PREREG_DRAFT.md)。核心判定：

- `build_cross_file_repair_plan` 在 `src/graph/` **零调用点**（本批 grep 复核）；
  但 `cross_file_plan` **已有下游消费者**：`debugger._resolve_target_module`
  在跨文件任务下读 `cross_file_plan.target_modules[0]` 改 debugger 的 target_module
  → prompt 与定位/修复路由必变；且 builder 本身按模块数（≤`CROSS_FILE_MAX_MODULES`=5）
  **增发 LLM 调用**。
- 因此**不满足**"默认关接线且 ON 不改 LLM 调用/修复路由"判据 → 按纪律**不硬改**，
  产出下一步两阶段方案（`CROSS_FILE_PLAN_BUILD_ENABLE` + `CROSS_FILE_PLAN_CONSUME_ENABLE`
  双开关分阶段）+ 同批 A/B 预注册草案（含判据/预算/披露要点）。
- 现状保持：`cross_file_plan` 仍为 `None` 占位（O 轮登记状态，非静默失败）。

## 5. 新功能 e2e 探针（Lead 追加，N 轮纪律）

`scripts/tools/e2e_probes_logic.py` 新增 2 个零 LLM 探针并在 `PROBES` 注册：

| 探针名 | 断言 | 实测 |
|---|---|---|
| `logic-stagnation-precedence` | (a) 默认关：repair-invalid 平局 → `done`/`skip_debugger_repair_invalid`（历史一致）；(b) ON 且停滞判定真 → `done`/`coverage_stall`；env 用后恢复 | **PASS**（1.5s） |
| `logic-rollback-schema-fields` | 成功/失败两分支键集合同构、均含两键；成功投影 `regression_failed/True`、`not_enabled/False`、未执行 `None/None`；失败 `None/False`；可 JSON 落盘 | **PASS**（2.0s） |

**计数影响：探针矩阵 66 → 68**（`--list` 行数；logic 组 18 → 20）。
注：Lead 给的 `--list | grep -c probe` 在现状下恒 0（探针名不含字面 "probe"，
kebab 命名如 `logic-...`），故计数以 `--list | wc -l` 为准。

实测（`_evidence/e2e_probes_t4.log`）：

```
--name 定向：pass=2 fail=0 error=0 skip=0（共 2）
--group logic：pass=19 fail=0 error=0 skip=1（共 20；skip=唯一 LLM 探针 logic-profile-spec-fields，符合零 LLM 纪律）
```

同时把两个探针加入 `tests/test_e2e_probes_logic.py` 的 pass 清单，并新增 2 例
"探针的探针"负控（停滞判定打坏 → fail；结果行两键被剥掉 → fail）——确保新探针
不会"永远绿"。

## 6. 验证命令与结果（定向，未跑全量 pytest，避免污染 B2 批次）

```bash
# 定向单测（217 passed）
.venv/bin/python -m pytest tests/test_t_round_semantic_fixes.py tests/test_batch_quota_preflight.py \
  tests/test_e2e_probes_logic.py tests/test_p_round_stagnation_wiring.py \
  tests/test_p2_4_coverage_stall.py tests/test_run_benchmark.py tests/test_workflow.py -q
# 行 schema 相关既有测试（235 passed，改动初期已跑：batch_v/ab/am/oracle_independent/mdo/batch_xiv/docstring_augment）
.venv/bin/ruff check <changed files>            # All checks passed
.venv/bin/ruff format --check <changed files>   # 6 files already formatted
.venv/bin/mypy src/graph/workflow.py src/graph/state.py scripts/tools/run_preflight.py  # Success
bash -n experiments/run_t4_a19_revalidation.sh  # 语法 OK；--dry-run 通过
.venv/bin/python scripts/tools/e2e_probe.py --group logic   # 19 pass / 1 skip / 0 fail
```

证据日志：`_evidence/pytest_targeted_final.log`、`_evidence/e2e_probes_t4.log`、
`_evidence/revalidation_analysis_selftest.log`、`_evidence/preflight_*.log`。

## 7. 残余风险与登记项

### 7.1 写入范围说明（需 Lead 知晓）

- **`experiments/run_benchmark.py` 不在 task-3 声明写入范围内**，但任务明确要求
  "结果行新增两键（从 state/executor 投影）"——该文件是**唯一**结果行构造点
  （`_build_task_result` 单一构造点），故做了 +16 行纯投影改动（成功/失败双分支），
  不碰任何计算/路由逻辑。若 Lead 判定越界，回滚方式：删两处各两行 + 对应测试即可。
- Lead 追加授权的 `scripts/tools/e2e_probes_logic.py` 已按追加要求处理（可加探针、
  不改既有探针语义；既有探针零改动，仅新增函数/注册/文档串）。

### 7.2 残余风险

1. **零迭代节省是预注册预期，不是缺陷**：本修复只改终止归因（分支归属），
   真实 LLM 复验 P3 若出现 Δ≠0 → `unexpected_delta`，须调查不得当收益；
2. **复验的日志归属判据依赖文案匹配**（"同迭代优先于 repair-invalid"）：若切点后
   文案被改动，P1/P2 日志计数会失真（脚本与代码注释同口径，已在 PREREG 披露）；
3. **样本量**：复验 n=10、单 seed、单模型、fast 档；只做机制验证，不外推能力收益；
4. **默认闸协议下证据门拒绝写盘**是 repair-invalid 触发源（实验机制），
   触发频率不代表自然任务分布（S-2 已披露）；
5. 真实 LLM 复验**未执行**（留 Lead 切点批次），本 README 不含任何真实 LLM 结论。

### 7.3 登记项（下一轮）

- D3b 接线按 `D3B_DESIGN_AND_PREREG_DRAFT.md` 分两阶段（构建/消费双开关）+ 同批 A/B；
- `PATCH_SNAPSHOT_ROLLBACK_ENABLE` 默认 false → 默认批次两键恒 `not_enabled/False`
  （行 schema 已可追溯）；真实回滚语义覆盖依赖开启该开关的批次（A-03 协议）；
- 探针矩阵由 66→68，Lead 同步 `BASELINE`/feature_matrix（本批不碰 docs）。

### 7.4 工件与入库提示

本目录位于 `experiments/results/**`（gitignored）；T 轮 `check_artifacts_tracked`
门禁已扩展到 `*_round_*` 目录 → **入库需 `git add -f`**（或由 Lead 在
MANIFEST/豁免登记里显式处置）。待入库新增文件：
`experiments/run_t4_a19_revalidation.sh`、`tests/test_t_round_semantic_fixes.py`、
本结果目录全部文件。

## 8. 工件清单

| 文件 | 说明 |
|---|---|
| `README.md` | 本文件 |
| `A19_REVALIDATION_PREREG.md` | A-19 默认协议真实 LLM 复验预注册（跑前冻结，sha256 见 §1.5） |
| `D3B_DESIGN_AND_PREREG_DRAFT.md` | D3b 设计与预注册草案（不实跑） |
| `_evidence/off_golden_table_before.json` | 改动前冻结的 OFF 黄金行为表（18 行，sha256 见 §1.3） |
| `_evidence/gen_off_golden_table.py` | 黄金表生成器（零 LLM，可复跑核对） |
| `_evidence/selftest_revalidation_analysis.sh` | 复验脚本判定逻辑零 LLM 自测（4 夹具） |
| `_evidence/revalidation_analysis_selftest.log` | 自测输出 |
| `_evidence/preflight_before_fix_check_quota.log` | 修复前真实复跑（ImportError 实证） |
| `_evidence/preflight_after_fix_check_quota.log` | 修复后真实 `--check-quota`（1 次真实调用，ok=True） |
| `_evidence/pytest_targeted_final.log` | 定向 pytest 最终结果（217 passed） |
| `_evidence/e2e_probes_t4.log` | 探针计数 + 两个新探针 + group logic 输出 |
| `SHA256SUMS` | 本目录工件校验（`shasum -a 256 -c SHA256SUMS`） |
