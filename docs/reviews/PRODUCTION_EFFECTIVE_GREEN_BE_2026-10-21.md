# BE 轮：生产路径的六处 rc==0 判绿收口（2026-10-21，零 LLM）

**范围**：`src/tools/detection_gates.py`、`src/agents/executor.py`、
`src/agents/executor_modes.py`（venv 沙箱 + Docker 两条路径）、
`src/agents/executor_repo.py`、`src/tools/patch_rollback.py`，以及
`src/agents/executor_runtime.py` 的 A16 尝试证据。这是 F03 缺陷族
（pytest 对全 skip / xfail / xpass / deselect 的套件同样返回 `rc==0`
且摘要 `passed==0`）在**生产路径**的剩余收口；BA / BB / BC / BD 已
收口 M1、experiments 侧消费点与 MDO。

**结论**：六处判绿点全部接入共享有效通过证据；A16 尝试记录新增
`effective_pass`，flaky 的 fail→pass 只认有效通过。新增
`run_has_effective_pass(rc, output)` 作为执行级唯一入口（`rc==0` 且摘要
有真实 `passed`、0 个 `failed`），`build_no_effective_pass_info` 提供
与断言失败区分的诊断。**40 例新锁 + 变异 8 锚点全红
（3/1/1/1/2/2/1/33）+ 中性对照 0 红**；登记前一跑 **11406 passed /
1 failed / 5 skipped、213.44s、collected 11412**（唯一失败 = 基线守卫）；
刷新后确认跑 **11407 passed / 5 skipped / 0 failed、199.06s、rc=0**
（collected 11412）；行覆盖 **19055/19581 = 97.3147%**、分支
**6982/7418 = 94.1224%**（未覆盖 526 / 缺弧 436 与 BD 逐位相同）。
`make gates` 全链 rc=0（见文末收口批注）。**未提交**（随收口提交一并
入库）。

---

## 1. 六处判绿点 + 一处尝试证据

| # | 位置 | 旧判据 | 风险 |
|---|---|---|---|
| 1 | `detection_gates._run_test_against_code` | `rc==0 ⇒ green` | fixed 侧全 skip 被记成"缺陷已修复"，门①误判为缺陷特异 |
| 2 | `executor.py`（本地执行） | `last_result.returncode == 0 ⇒ passed` | 修复迭代把空套件记成修复正确，进入下一轮 |
| 3 | `executor_modes.execute_sandboxed`（venv） | 同上 | 沙箱路径同缺陷 |
| 4 | `executor_modes.execute_docker` | `result.returncode == 0 ⇒ passed` | 容器路径同缺陷 |
| 5 | `executor_repo._run_test_nodes` | `rc==0 ⇒ passed_count += 1` | `failed_cases` 为空 ⇒ `f2p_all` / `p2p_no_regression` 被空套件骗过 |
| 6 | `patch_rollback.run_p2p_regression` | `rc==0 ⇒ verdict="verified"` | "补丁安全"没有任何断言证据；fail-closed 模式下也不会回滚 |
| 7 | `executor_runtime` A16 尝试记录 | `passed = rc==0 且未超时` | "首败、次全 skip"被记成 fail→pass，制造假 flaky |

改后统一口径：**至少 1 个真实 `passed` 且 0 个 `failed`**；部分 skip
与真实 passed 并存仍算有效通过；摘要不可解析（空输出 / 自定义运行器）
不算有效通过（fail-closed）。`rc != 0`（含 `None`）恒 False，既有失败
口径不变。

## 2. 逐点处置与行为差异

| # | 位置 | 改后行为 |
|---|---|---|
| 1 | 检测门 | `rc==0` 且无有效通过 ⇒ `{"green": False, "unavailable": True}`，**不记 over_red**；门①语义是"buggy 红 + fixed 绿 = 缺陷特异"，fixed 侧没有断言执行时两侧证据都不存在，保守放行到历史路由 |
| 2 | 本地执行器 | `passed=False` + `error_info.type="no_effective_pass"`（不是 `test_failure`，避免 Debugger 按"代码有缺陷"方向空转） |
| 3 | venv 沙箱 | 同 #2；`execution_attempts` / `flaky_fail_then_pass` 字段保持原样 |
| 4 | Docker | 同 #2 |
| 5 | 仓库节点 | 该节点记入 `failed_cases`（错误文案含"无有效通过（rc=0，摘要无 passed / 全 skip）"与输出尾部）；`passed_count` 不增 |
| 6 | P2P 回归 | 默认 `regression_error`（不误杀好补丁），`fail_closed=True` 时 `regression_failed`（触发回滚）；结果附 `no_effective_pass=True` |
| 7 | 尝试证据 | 新增 `effective_pass` 字段（JSON 可序列化）；`observed_fail_then_pass` 优先读它，旧记录无该键时回退 `passed`；重试层仍按执行层 `rc==0` 停止（all-skip 重跑不会变成有效通过，重复执行只会制造噪声），有效通过由调用方终态裁决 |

行为不变面（逐位保持）：

- 干净通过（真实 `passed`）⇒ 六处仍判通过 / green / verified；
- **部分 skip + 真实 passed** ⇒ 仍算有效通过（六处一致）；
- `rc==1` 断言失败仍记失败 / red / `regression_failed`；
- 执行错误（收集 / 语法 / 信号）优先级不变：检测门先走执行错误分支，
  P2P 先处理 `rc>=2` 与异常，本地执行器仍用 `build_error_info`；
- executor 的 `passed` 是**对外行为变化**（全 skip 从 True 变 False），
  这是本轮的修复目标而非回归；`output` / `coverage` / `failed_cases`
  的形状不变，只新增 `error_info.type`；
- 检测门返回结构只新增既有键的取值组合（`green=False` + `unavailable=True`），
  消费方的 `unavailable` 路由不变。

## 3. 真语料测量（只读静态扫描）

对 `experiments/results/**/*.json` 的 `results.<arm>.details` 逐行扫描：

| 口径 | 实测 |
|---|---|
| 任务行 | **11197** |
| `passed=True` / `passed=False` | **5884** / **5313** |
| 无 `generated_test` 的行 | **1541**（其中 passed **635**） |
| 有 `generated_test` 的行 | **9656** |
| 静态分类：无 skip 标记 | **9556** |
| 静态分类：部分 skip 标记 | **30** |
| 静态分类：不可解析 | **63**（其中 passed **0**） |
| 静态分类：无测试函数 | **7**（其中 passed **0**） |
| 静态分类：全 skip（函数级 / 模块级） | **0** |
| 含 skip 标记的行 / 其中 passed | **408** / **145** |
| passed 且静态无 skip 标记 / 部分 skip | **5243** / **6** |
| `repo_verification` 行 / 其中 passed | **50** / **0** |
| `patch_rollback` verdict 归档键 | **不存在**（无法逐行复算） |

**静态适用面为零**：有 `generated_test` 且 passed 的 5249 行里，没有任何
一行被静态分类为"所有测试函数都无条件 skip / 模块级 pytestmark 全
skip"；6 行"部分 skip"仍含真实通过，按新口径保持 passed。50 条
`repo_verification` 全部 failed，本来就不在"假 green"通道上。P2P 回归
默认关（`PATCH_SNAPSHOT_ROLLBACK_ENABLE` 默认 false），且归档不保存
verdict，无法逐行核验。

**限制（不得略过）**：归档不保存逐行 pytest 原始 stdout，上述只是对
`generated_test` 的静态代理，不是运行时结果的证明；无法解析 / 无测试
函数 / 无生成测试的行分别按上表单列。历史归档**零回填**：不重跑 LLM
批次、不改写任何 JSON / `SHA256SUMS`。

## 4. 回归锁

`tests/test_production_effective_green_be.py`：**40 例**（零 LLM）。

| 类 | 例数 | 覆盖 |
|---|---|---|
| `TestSharedPredicate` | 16 | `run_has_effective_pass` 的 11 个参数化语义（真实 passed / 部分 skip / 全 skip / xfail / xpass / deselect / 空输出 / pass+failed / rc≠0 / rc=None）+ 5 个模块的源码导入锁 |
| `TestDetectionGateEffectivePass` | 5 | 全 skip ⇒ unavailable、部分 skip ⇒ green、特异性裁决把 skip 记 unavailable、执行错误优先级、**真实 pytest 运行期 skip** 端到端 |
| `TestExecutorLocalEffectivePass` | 3 | 全 skip ⇒ passed=False + error_info.type；真实通过；部分 skip+pass |
| `TestExecutorSandboxEffectivePass` | 2 | venv 沙箱全 skip / 真实通过 |
| `TestExecutorDockerEffectivePass` | 2 | Docker 全 skip / 真实通过 |
| `TestRepoTestNodesEffectivePass` | 4 | 全 skip 节点记失败；真实通过 / 部分 skip 仍计数；真实 pytest 运行期 skip |
| `TestPatchRollbackEffectivePass` | 3 | 默认 `regression_error`；fail-closed ⇒ `regression_failed`；部分 skip+pass ⇒ verified（含真实 pytest） |
| `TestExecutionAttemptEffectivePass` | 4 | `effective_pass` 记录、全 skip 不制造 fail→pass、重试在 rc==0 停止、超时不算通过 |
| `TestNoEffectivePassInfo` | 1 | 诊断载荷类型 / 摘要计数 / 与 `test_failure` 区分 |

既有测试夹具同步保真（断言不变）：`test_detection_gates_matrix.py`、
`test_executor_sandbox.py`、`test_executor_repo_runner_flow.py`、
`test_untrusted_exec_env.py` 的替身输出由 `"ok"` / 空串改为真实
`"1 passed in 0.01s"` 摘要行。

## 5. 变异验证

8 个真实锚点 + 1 个中性对照；脚本
`scripts/tools/be_mutation_verify.py`：基线干净副本 **40 passed**；
逐锚点读取原字节 → 写入变异 → `compile()` → 收集数核对 → 跑受影响面 →
sha256 校验后按原字节还原（绝不用 `git checkout` / `git stash`）。

| 锚点 | 变异 | 红数 |
|---|---|---|
| M1-detection-gate-effective-guard-off | 检测门守卫恒假 | **3** |
| M2-executor-local-effective-guard-off | 本地执行器改回 rc==0 | **1** |
| M3-executor-sandbox-effective-guard-off | venv 沙箱改回 rc==0 | **1** |
| M4-executor-docker-effective-guard-off | Docker 改回 rc==0 | **1** |
| M5-repo-node-effective-guard-off | 仓库节点改回 rc==0 | **2** |
| M6-p2p-effective-guard-off | P2P 改回 rc==0 | **2** |
| M7-attempt-flaky-evidence-uses-rc | 尝试证据只认 rc | **1** |
| M8-shared-predicate-always-true | 共享谓词恒真 | **33** |
| M9-control-comment-wording | 仅改注释用词 | **0（SURVIVED）** |

## 6. 踩坑与自纠

1. **夹具不保真会制造假失败**：新判据上线后，5 个既有测试因替身返回
   `"ok"` / 空输出而失败。它们不是生产缺陷，而是替身没有 pytest 摘要；
   补上 `"1 passed in 0.01s"` 后断言与用例数不变。判据：**替身必须
   保真到判据依赖的字段，否则"测试红了"可能只是替身不像**。
2. **重试层不追 rc==0 之后的有效通过**：run_pytest_with_retry 仍在
   `rc==0` 停止。全 skip 重跑不会变成有效通过，继续重试只会制造
   flaky 噪声；有效通过判定交给调用方按 `effective_pass` / 共享谓词
   终态裁决。判据：**控制流的收敛条件与证据的判定口径要分开**。
3. **导入顺序是静态门禁的一部分**：`executor_runtime` 首次把
   `pytest_output` 放在 `process_utils` 之前触发 ruff I001；按字母序
   调整后 check / format / mypy 全绿。判据：**新增共享依赖后先跑
   静态门禁，不要等全量**。
4. **非 F03 的 rc==0 不能硬套谓词**：`testless_validation.py:165` 是
   mypy 返回码（0 = 无类型错误），`:283` 是导入冒烟返回码（0 = import
   成功），二者不是 pytest 套件判据。本轮**不接**有效通过谓词，按
   dated errata 登记，防止下一次"全仓普查 rc==0"把它们误收口。

## 7. 边界（不得引用为「生产路径所有 rc==0 均已收口」）

1. **只收口 pytest 套件判绿点**：`testless_validation` 的 mypy /
   导入冒烟两处是工具专用返回码（errata，见 §6.4）；`dependency.py`
   的 pip 返回码、git 命令返回码等非 pytest 执行点不在 F03 语义内，
   本轮不动。
2. **检测门把无有效通过记 `unavailable`，不是 `over_red`**：fixed 侧
   空套件不能证明"补丁过宽"，沿用既有 unavailable 路由；这是保守
   放行，不是 green。
3. **executor `passed` 语义变化是修复本身**：全 skip 从 True 变 False；
   下游若把 `passed` 当"进程成功"使用需改读 `returncode` 或
   `execution_attempts`。本轮只改判据，不追改所有展示层。
4. **P2P 默认不误杀**：非 fail-closed 模式下无有效通过记
   `regression_error`（不自动回滚）；只有显式 fail-closed 才记
   `regression_failed`。该开关默认 false。
5. **语料是静态代理**：归档不保存逐行 pytest stdout，无法证明历史
   运行期零 all-skip；"静态适用面为零"只说明生成测试文本里没有
   可判定的全 skip 结构，不能反推每次执行都有真实 passed。
6. **历史零回填**：不重跑、不回填、不改写归档 JSON / `SHA256SUMS`。

## 8. 复算命令

```bash
# 目标锁（40 collected）
.venv/bin/python -m pytest tests/test_production_effective_green_be.py -q

# 受影响面（执行器 / 检测门 / P2P / MDO 与 BA-BD 消费点）
.venv/bin/python -m pytest tests/test_production_effective_green_be.py \
  tests/test_detection_gates_matrix.py tests/test_executor_sandbox.py \
  tests/test_executor_repo_runner_flow.py tests/test_untrusted_exec_env.py \
  tests/test_mdo_effective_green_bd.py tests/test_effective_green_ba.py \
  tests/test_effective_green_consumers_bb.py \
  tests/test_misguided_replay_effective_green_bc.py -q

# 变异验证（8 锚点 + 1 个中性对照；可传名字前缀过滤，如 M1 M6）
.venv/bin/python scripts/tools/be_mutation_verify.py

# 确认跑（无覆盖率，xdist 同口径）
make test

# 门禁（CI 同口径；不与 make test 重叠）
make gates
```

## 9. 收口批注（2026-10-21，实测）

`make gates` **全链 rc=0**，墙钟 **216s**（`start=$(date +%s); make gates >
/tmp/gates_be.log 2>&1; rc=$?`，不接管道、与 `make test` 不重叠）。链内
读数：

- `ruff check .`：All checks passed；
- `ruff format --check .`：**947 files already formatted**；
- `mypy src/ config.py`：**Success: no issues found in 136 source files**；
- 链内 pytest（`-n 4 --dist loadfile`）：**11412 items / 11407 passed /
  5 skipped / 0 failed，210.12s**；
- 严格 JSON 门禁 / 文档链接 / 双语文档 / 基线 / 工件对账：全部
  `[OK]`，0 错误 0 警告。

此前的确认跑（`make test`，无 `--cov`）11407 passed / 5 skipped /
0 failed、199.06s、rc=0；两次运行 passed/skipped 逐项一致。覆盖率读数
（`coverage.xml` 根属性，来自带 `--cov` 的登记前运行）：行
19055/19581 = 97.3147%、弧 6982/7418 = 94.1224%。全部改动仍未提交。
