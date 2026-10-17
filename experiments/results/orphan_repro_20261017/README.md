# M-3 证据：`m1_metrics` 孤儿 pytest 根因定位 + 最小复现 + 修复（2026-10-17）

> **性质**：根因调查与修复证据（M 轮 T8 / M-3）。零 LLM、零网络、确定性可复跑；
> 仅含本机进程表/临时目录观测，不含任何密钥。
> **结论**：L 轮 PID 57034 孤儿事件 = **`run_with_timeout` 父进程死亡缺口**
> （调用方被外部 SIGKILL 时 `start_new_session` 的子进程不被回收），
> **不是**"超时路径直接 SIGKILL、无 SIGTERM 宽限"（候选 A）导致的——
> 该事件里超时分支从未执行。修复 = 超时路径两段式终止（SIGTERM 宽限→SIGKILL 清扫）
> + `run_with_timeout(orphan_guard=True)` 父死亡看门狗；M1 嵌套 pytest 已启用。

## 0. 证据文件

| 文件 | 内容 |
|---|---|
| `evidence_l_batch_leftovers.log` | L 轮批次现场残留（只读采集）：m1 tmpdir + 同秒 proc tmpdir + 历史 `aitester_proc_*` 残留清单 |
| `run_minimal_repro.py` | 最小复现脚本（同一脚本可跑 pre-fix / post-fix，自动判读前后差异；S1–S4 四场景） |
| `repro_before.log` / `repro_before.json` | **修复前**（HEAD 版 `process_utils.py` + `_m1_metrics.py`）实跑结果：2 个场景复现孤儿 |
| `repro_after.log` / `repro_after.json` | **修复后**实跑结果：0 个场景复现孤儿；SIGTERM 宽限实测 |
| `SHA256SUMS` | 本目录文件完整性清单 |

复跑命令（低 CPU，建议窗口期 `nice -n 15`）：

```bash
nice -n 15 .venv/bin/python experiments/results/orphan_repro_20261017/run_minimal_repro.py \
  --out experiments/results/orphan_repro_20261017/repro_after.json
```

## 1. 现场证据链（L 轮 PID 57034，先于任何代码改动采集）

L 轮正式批 2026-10-17 18:36 出现 `ppid=1` 的孤儿：
`pytest -q --no-header -p no:cacheprovider /var/folders/.../T/aitester_m1_bitcount_*/python_testcases/test_bitcount.py`
（PID 57034，~98% CPU，age 9m42s，bitcount 缺陷实现死循环家族）。

**强证据 1：M1 判分 tmpdir + `run_with_timeout` 文件后端 tmpdir 同秒出生且都未清理。**

```
birth=2026-10-17 18:36:02  /var/folders/.../T/aitester_m1_bitcount_07q05sj_     （M1 判分 tmpdir）
birth=2026-10-17 18:36:02  /var/folders/.../T/aitester_proc__v8n618p          （run_with_timeout 文件后端 tmpdir）
  stdout 大小 = 1 字节，内容 = "."（18:36:03 写入 ⇒ pytest 已启动并跑过 1 条测试）
```

两条路径的 `finally` 清理都**未执行**（`_run_pytest_in_tmp` 的 `shutil.rmtree(tmpdir)`
与 `run_with_timeout` 的 `finally: shutil.rmtree(tmpdir)`）——正常返回/异常/超时
三种分支都会清理，因此**唯一可能是调用进程在超时分支之前被外部异常杀死**
（SIGKILL / 崩溃 / harness 杀进程），随后其 `start_new_session` 的 pytest 子进程
被 init(launchd) 收养（ppid=1）继续空转。

**强证据 2：调用链不存在中间 subprocess 包装进程**（排除"中间进程被外层 killpg"路径）：

- `run_main_batch.py` 是 `run_benchmark.py` 的**进程内薄壳**（`import experiments.run_benchmark as rb`）；
- M1 三指标在批进程内同步调用（`_build_task_result` → `_compute_detection_rate` →
  `experiments/_m1_metrics.py::_run_pytest_in_tmp` → `src/utils/process_utils.run_with_timeout`）；
- 全仓 `aitester_m1_` 前缀只出现在 `_m1_metrics._run_pytest_in_tmp`（`tempfile.mkdtemp`），
  没有第二层 python 包装。
⇒ L 轮事件中 pytest 的**直接父进程**就是调用 M1 判分的进程；其被杀 → 子进程孤儿。

**佐证 3：历史残留 `aitester_proc_*` 目录 24 个**（本机 `TMPDIR`），每次 = 某调用进程
在子进程运行中被异常杀死的痕迹，时间点与已知事件吻合（`evidence_l_batch_leftovers.log`）：

- `2026-10-17 18:14:46 / 18:14:57`：DEF-1 误跑被终止（pilot README OBS-5 记录的
  "2 个子进程被 init 收养"）——同一机制；
- `2026-10-17 18:36:02`：L 轮孤儿事件；
- `2026-10-17 20:27 / 20:42`：晚间其它实验/测试命令被中断；
- 另有 10-11 起多个历史点（含 K 轮 10-17 09:53 前后，当时观测到 2 进程 × ~7h CPU）。

## 2. 最小复现（`run_minimal_repro.py`，pre-fix 实跑）

修复前（HEAD）实跑 `repro_before.log`：

| 场景 | 构造 | pre-fix 实测 | post-fix 实测 |
|---|---|---|---|
| **S1 父进程 SIGKILL**（L 批签名；真实入口 `_run_pytest_in_tmp`） | 父进程起嵌套 pytest（挂死）→ `kill -9 父PID`（不 kill 进程组） | 嵌套 pytest **ppid=1 存活**（PID 97377，etime 00:03）；m1/proc tmpdir 残留 4 个 | **0 存活**：看门狗在父死 0.1s 级检测并 killpg 回收 |
| **S2 A→B→C 外层超时**（任务书骨架） | A=`run_with_timeout(B, timeout=1.5)`；B（新会话）内部起嵌套 pytest（新会话） | A 超时返回 `timed_out=True`；C **ppid=1 存活**（PID 97439） | **0 存活**：B 死 → B 起的命令看门狗 killpg 回收 C |
| **S3 SIGTERM 宽限**（仅 post-fix 参数存在可测） | 子进程忽略 / 响应 SIGTERM | pre-fix 无此参数（跳过） | 忽略：`timed_out=True`、耗时 **1.433s**（≈timeout 1.0 + grace 0.4）；响应：耗时 **1.033s**（宽限内退出） |
| **S4 子进程自建新会话**（残余风险边界） | 孙进程 `start_new_session=True` 后逃逸 | 1 个自建会话孙进程存活（ppid=1） | **仍 1 个**（已知边界：进程组信号结构上到不了新会话进程） |

汇总：`repro_before.json.leaked_scenarios = 2` → `repro_after.json.leaked_scenarios = 0`
（S4 为主动披露的边界，不计入"修复目标场景"；S1/S2 的 tmpdir 残留是"父进程已死、
无人可清理"的预期副产物，见 §5 残余风险 3）。

**候选机制判定**：

- **候选 A（`_terminate_process_group` 直接 SIGKILL、无 SIGTERM 宽限）= 证伪为根因**：
  L 轮事件里超时分支从未执行（两个 tmpdir 同秒残留为证）；S1 显示父进程在 spawn
  后约 1s 内死亡，120s/60s 超时门根本没到；S2 进一步证明"外层超时 killpg 中间进程"
  时，中间进程用 `start_new_session` 起的子进程**不受 killpg 影响**（无论先 SIGTERM
  还是先 SIGKILL，只要中间进程没有清理子进程的 handler）。
- **候选 B（中间包装进程 SIGTERM handler）= 无落点**：M1 判分链路无中间 subprocess
  包装进程（见 §1 强证据 2）。修复改为在 `run_with_timeout` 内部引入**看门狗监督
  进程**（`orphan_guard=True`）承担"父死回收"职责，等价于把"handler 责任"落到
  执行原语层、对调用方透明。
- **候选 C（批后只读巡检/清理兜底）= 不足但保留为运行期兜底**：L 轮孤儿在被发现前
  已烧 9m42s CPU，且 K-6 巡检器 600s 年龄窗口在 582s 时未触发（漏报）；批后处理
  可长达 1h（L 轮 df 臂后处理 ≈54m），巡检无法阻止"父死即孤儿"。因此**不作为根因
  修复**；`scripts/tools/detect_orphan_procs.py` 已有 `--min-age`（默认 600 兼容），
  本任务补 CLI 回归测试，批次窗口建议 `--min-age 60`（见 §6 登记册建议）。

## 3. 修复（最小改动，2 个源文件 + 测试）

### 3.1 `src/utils/process_utils.py`

1. **超时路径两段式终止**（`_terminate_process_group`）：
   - `killpg(SIGTERM)` → 最多等 `terminate_grace` 秒（默认 `_TERMINATE_GRACE_SECONDS=0.5`，
     可经 `run_with_timeout(terminate_grace=...)` 覆盖，归一 `[0, 10]`；响应 SIGTERM
     的进程提前结束等待）→ **总是**再 `killpg(SIGKILL)` 清扫（含"组长已退出、组内仍有
     成员"形态）；任何 getpgid/killpg 失败回退 `proc.kill()`。
   - 超时语义逐位不变：`timed_out=True`、`returncode=-9`、文件后端输出、保证返回。
2. **父死亡看门狗**（`run_with_timeout(orphan_guard=True)`，默认关、按调用点启用）：
   - 先起监督进程（`python -c <内联脚本>`，同样在 `start_new_session` 的新会话/新进程组），
     监督进程再起真实命令（**同一进程组**）；
   - 监督进程每 0.1s 检查 `os.getppid() != 原始父 PID`，一旦父进程消亡立即
     `killpg(SIGKILL)` 回收命令进程组并以 143 退出；命令正常退出则透传其退出码
     （被信号杀死归一 128+signum）；
   - 超时路径由既有 `killpg` 一次回收"看门狗+命令"两层，语义不变；`stdout`/`stderr`/
     `cwd`/`env`/`text` 全部透传，`CompletedProcess.args` 仍为原命令；
   - `orphan_guard` 与 `preexec_fn` 不能同用（看门狗无法转发任意 Python 钩子），
     同时给出会 fail-closed 抛 `ValueError`（执行器链路用 `preexec_fn`，未启用看门狗，
     行为不变）。

### 3.2 `experiments/_m1_metrics.py`

`_run_pytest_in_tmp` 的嵌套 pytest 调用增加 `orphan_guard=True`（本次 L 轮实测泄漏点），
并在注释中记录 M-3 根因与边界：嵌套 pytest 命令自身不建新会话，看门狗对
"调用方被外部杀死"这一真实缺口全覆盖。零行为变化面：命令、env、超时、判分口径不变。

### 3.3 语义不变 / 不挂死保证（why 不破坏既有契约）

- 超时返回形状与值不变（`timed_out=True`、`-9`）；文件后端（非管道）不变 → 不会挂死；
- 两段式终止只在超时路径增加"≤grace 的优雅等待 + 无条件 SIGKILL 清扫"——
  整树终止覆盖面**不缩小**（清扫对"组长已退出但组内残留"同样生效）；
- 看门狗只在 `orphan_guard=True` 调用点生效（当前仅 M1 嵌套 pytest），其它 49 处
  `run_with_timeout` 调用行为逐位不变；`CompletedProcess.args` 保持原命令可审计。

## 4. 回归测试（新增 ≥10 例）

`tests/test_orphan_repro_20261017.py`（新，23 passed）：

| 类别 | 用例 |
|---|---|
| 复现/证伪（真子进程） | `test_sigkill_parent_leaves_orphan_without_guard`（无保护复现 ppid=1 孤儿）；`test_outer_timeout_without_guard_leaves_nested_orphan`（候选 A 覆盖不到中间进程新会话子进程）；`test_sigkill_parent_is_reaped_by_orphan_guard`、`test_outer_timeout_reaps_nested_with_guard`（修复锁） |
| SIGTERM 宽限 | 响应 SIGTERM 宽限内退出、忽略 SIGTERM 必被 SIGKILL、`grace=0` 历史快速口径、组内孙进程被两段式终止清扫 |
| 看门狗契约 | stdout/stderr/rc 透传、cwd/env/text、`args` 为原命令、`preexec_fn` 冲突 fail-closed、信号退出码归一 128+n、超时语义不变、进程树两层形态（父→看门狗→命令，同进程组） |
| 非僵尸进程判定 | `test_zombie_is_not_counted_as_live`（未 wait 子进程僵尸必须与存活区分；macOS 僵尸 command 变 `<defunct>`，故按 pid 查 stat）、`test_killed_orphan_disappears_not_just_zombifies` |
| 参数/接线 | `terminate_grace` 归一（None/负值/超上限）、M1 `_run_pytest_in_tmp` 透传 `orphan_guard=True` 接线锁 |

`tests/test_detect_orphan_procs.py` 追加 2 例：`--min-age` 默认 600（500s 龄期默认不报，
复现 L 轮 582s 漏报口径）、显式 `--min-age 60` 命中共进入 JSON 报告（批次窗口口径）。

验证命令与结果：

```bash
nice -n 15 .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_process_utils.py tests/test_detect_orphan_procs.py tests/test_orphan_repro_20261017.py \
  tests/test_p0_hardening_2026_10_11.py tests/test_process_and_candidate_matrix.py \
  tests/test_m1_metric_semantics.py tests/test_m1_packaged_tests.py tests/test_m1_dispatch_heuristic.py \
  tests/test_m1_cross_file_metric.py tests/test_m1_packaged_missing_support.py \
  tests/test_nested_pytest_env_convergence.py tests/test_detection_gates_matrix.py tests/test_mdo_metrics.py
# → 253 passed（0 failed；含既有 process_utils 超时/整树终止/文件后端/孤儿回归全部绿）

.venv/bin/ruff check src/utils/process_utils.py experiments/_m1_metrics.py \
  tests/test_orphan_repro_20261017.py tests/test_detect_orphan_procs.py   # All checks passed
.venv/bin/ruff format --check（同上 4 文件）                              # 4 files already formatted
.venv/bin/mypy src/utils/process_utils.py                                # Success: no issues found
```

## 5. 残余风险（如实披露）

1. **命令自身再 `start_new_session=True` 的子进程仍会逃逸**（复现 S4）：任何进程组
   信号结构上都到不了新会话进程；M1 嵌套 pytest 不进入该形态（pytest 不建新会话），
   但若未来有插件/被测代码 fork+setsid，看门狗覆盖不到。需在调用点避免该形态或
   依赖巡检兜底。
2. **父进程死亡瞬间的有界窗口**：看门狗 0.1s 轮询，父死到子进程被回收存在 <0.2s
   窗口（子进程可能短暂 ppid=1，但随即被杀，不构成小时级 CPU 泄漏）。
3. **tmpdir 残留（无 CPU 影响）**：父进程被 SIGKILL 时其 m1/proc tmpdir 无人生还
   清理（L 轮现场与 S1 复现均如此）——小文件残留，不影响正确性；系统 TMPDIR
   定期清理可回收。若要零残留需把 tmpdir 生命周期交给看门狗（本轮不做，超出最小修复）。
4. **其它嵌套 pytest 调用点未启用看门狗**：`experiments/mutation_testing.py`
   （K 轮 `test_mutant.py` 孤儿路径）、`src/tools/branch_coverage_inject.py`、
   `src/agents/fl_spectral.py`、`src/agents/runtime_probe.py`、`src/tools/patch_rollback.py`
   等 48 处 `run_with_timeout` 调用行为未变；这些路径若有同类"父进程被外部杀"风险，
   可逐点加 `orphan_guard=True`（一行；写域外，建议 Lead 分派或后续轮次统一）。
5. **巡检器仍是最后防线**：默认 `--min-age 600` 对"刚泄漏"的进程（如 L 轮 582s）
   漏报——批次窗口巡检用 `--min-age 60`（脚本参数已存在，本任务补了 CLI 回归测试）。
6. 平台注记：看门狗检测 `os.getppid() != 原始父 PID`，macOS(launchd) 与 Linux(init/subreaper)
   均成立（不依赖 ppid 恰好为 1）；`start_new_session`/killpg 均为 POSIX 语义，Windows 不支持。

## 6. 登记册建议条目文本（供 Lead 并入 `docs/PROJECT_STATUS_REGISTER.md` §4）

> **M 轮已收口（运行期卫生）** ~~`m1_metrics` 路径孤儿 pytest 根因未定位~~ → **根因定位并修复（M-3）**：
> L 轮 PID 57034（ppid=1、~98% CPU、9m42s）根因 = **`run_with_timeout` 父进程死亡缺口**——
> 调用方进程在超时分支之前被外部异常杀死后，其 `start_new_session` 的嵌套 pytest 不被
> 回收（现场证据：m1 判分 tmpdir 与 run_with_timeout 文件后端 tmpdir **同秒出生且
> finally 均未执行**；调用链无中间 subprocess 包装进程）。**"超时直接 SIGKILL 无 SIGTERM
> 宽限"被证伪为根因**（事件中超时分支从未执行；最小复现 A→B→C 亦证明 killpg 覆盖不到
> 中间进程新会话子进程）。修复：`process_utils._terminate_process_group` 改两段式终止
> （SIGTERM 宽限 0.5s 可配→SIGKILL 清扫，整树终止语义不变）+ `run_with_timeout(orphan_guard=True)`
> 父死亡看门狗（监督进程与命令同进程组，父死 0.1s 级 killpg 回收），M1 嵌套 pytest 已启用；
> 回归 25 例（23 新 + 2 detector CLI）；复现 before/after：孤儿场景 2→0（残余边界：
> 自建新会话孙进程、tmpdir 残留、其它 48 处 run_with_timeout 未启用，见
> `experiments/results/orphan_repro_20261017/README.md` §5）。

## 7. 附件 sha256

见本目录 `SHA256SUMS`（`shasum -a 256 -c SHA256SUMS` 复算）。
