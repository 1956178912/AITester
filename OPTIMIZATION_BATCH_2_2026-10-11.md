# 2026-10-11 全面优化批次·第二批（run_with_timeout 全量接线）

> 批次定位：孤儿子进程风险面清零。本批次把全仓剩余 9 处裸 `subprocess.run(timeout=)`
> 调用点统一接到 `run_with_timeout`（`src/utils/process_utils.py`），并同步迁移所有
> 受影响 mock 点、加固 `run_with_timeout` 契约。零行为变化（超时口径逐字不变）、
> 零 LLM 调用、零新增测试用例（纯 mock 点迁移）。

## 1. 根因回顾（2026-10-09 批后挂死事故）

裸 `subprocess.run(timeout=...)` 在 `communicate()` 阶段等待管道 EOF。当被测代码
（LLM 生成的补丁 / 回归测试 / docker 容器命令）派生**孙进程**且孙进程持有管道写端
时，主进程被 `timeout` kill 后孙进程仍存活并持有写端 → `communicate()` 永久阻塞。
2026-10-09 审计实证：3 个孤儿进程存活 16.5h。

`run_with_timeout` 的解法：
- **文件后端**（stdout/stderr 写临时文件而非 PIPE）→ 不存在"等 EOF"阻塞；
- **`start_new_session=True`** → 子进程独立进程组；
- **`killpg` 整树终止** → 超时/异常时按进程组 SIGTERM/SIGKILL，孙进程一并回收；
- **有界 drain** → `killpg` 后给一个很短的等待拿最终退出码，拿不到也保证函数
  返回（`CompletedProcess` 子类，附 `timed_out` 标记）。

本批次前已接线：`executor_runtime`、`venv` 缓存链、`sandbox` 部分链路。
**本批次消除剩余 9 处**（下表）。

## 2. 接线清单（9 处）

| 调用点 | 文件 | 超时口径（与历史逐字一致） |
|---|---|---|
| `_run_probe` / `_run_tests_on_code` | `src/measurement/mdo.py` | 超时 → 返回 `None`（原 TimeoutExpired → 降级 None） |
| P2P 回归（LLM pytest） | `src/tools/patch_rollback.py` | 超时 → `regression_failed`（fail_closed）/ `regression_error` |
| `create_venv`（venv + pip 自举） | `src/tools/dependency.py` | 超时 → `RuntimeError("venv 创建超时…")` |
| `install_packages` | `src/tools/dependency.py` | 超时 → 保守降级 |
| mypy 层 + 导入冒烟层 | `src/tools/testless_validation.py` | 超时 → 构造 TimeoutExpired 进既有 except（保留 infra_degraded 三态） |
| pyright 后端调用 | `src/tools/type_repair.py` | 超时 → 空 findings（历史降级分支同口径） |
| docker run 调用 | `src/agents/executor_modes.py` | `raise_on_timeout=True` → 历史 TimeoutExpired 异常口径（except 分支不变） |
| 测量调用 | `src/agents/fl_spectral.py` | 超时 → 返回 `None`（保留 TimeoutExpired 兜底分支兼容 mock） |
| 探针 runner 调用 | `src/agents/runtime_probe.py` | 超时 → 静默降级 `None`（纯观测层，不阻断主流程） |
| 中心 `_run()` helper | `src/agents/executor_repo.py` | 超时 → `returncode=124` 哨兵（原分支逐字一致）；M3 swebench runner 同步收敛到 `_run()` |

> 注：上表 9 行中 mdo / dependency / executor_repo 各自含 1–2 个调用点，合计
> 覆盖 9 处裸调用；其余 6 行各 1 处。

## 3. 契约加固（`run_with_timeout` 本身）

- **`timeout=0` / 负值 / `None` 归一为"不设超时"**：此前 `Popen.wait(timeout=0)`
  立即抛 TimeoutExpired → 误触发整树 kill，与历史调用点（`executor_repo._run` /
  `patch_rollback`）以 `timeout=0` 表达"本调用不额外设上限"的语义冲突。现 0/None
  归一为等待至进程自然退出，负值保守归一（不臆测调用意图）。
- **新增 `capture_output` 透明兼容参数**：裸 `subprocess.run(capture_output=True)`
  调用位迁移时参数可直接透传（本实现文件后端承接输出，参数被忽略）。零行为影响，
  仅为接线平滑（`testless_validation` 的 mypy/导入冒烟层沿用原 `capture_output=True` 写法）。

## 4. mock 点迁移（接线点即 mock 点）

测试统一改为 `patch("src.utils.process_utils.run_with_timeout")`，fake 结果补
`timed_out` 属性：

- `tests/test_dependency.py` / `test_dependency_edge_cases.py`（venv 创建/超时）
- `tests/test_type_repair_more_branches.py` / `test_roadmap_gaps_g1_g2_g3.py`（pyright）
- `tests/test_testless_validation.py`（mypy + 导入冒烟；超时 mock 由
  `side_effect=TimeoutExpired` 迁移为 `timed_out=True` fake，OSError 口径保留）
- `tests/test_runtime_probe.py`（`_fake_run` 迁移，fake 补 `timed_out`）
- `tests/test_executor_docker.py` / `test_sandbox_hardening.py`（docker CLI）
- `tests/test_executor_repo_pure_logic.py`（`_run` 124 哨兵 + bytes 解码兜底）

清理 4 处 `subprocess` 未用 import（`runtime_probe` / `dependency` /
`patch_rollback` / `type_repair`）+ 测试侧 1 处（`test_dependency_edge_cases`）。

## 5. 治理盘点结论（零代码变更）

### 5.1 `checksum_results.py` 定位

确认为**独立入口**（与 `check_swe_bench_pro_ready` 同档）：需 `--write`/`--verify`
参数，默认无参即 fail，故**不纳入本地门禁循环**（`make gates` 不含此步）。CI 仅在
`main_batch` 工件目录以 `--verify` 显式调用（`.github/workflows/ci.yml`）；`Makefile`
未接线。维持现状，文档化此口径。

### 5.2 `r4_batches/SHA256SUMS` 清单陈旧（预存缺口，非本批次引入）

该清单提交于 `7f25408`（R4/R2 批次），早于 `r4_batches/README.md` 与
`replay_r4_ab_arm_a_v2.md` 两个文件入库；`.gitignore` 白名单有意放行
`r4_batches/**`，故 `--verify` 报 2 项"清单外新增"。修复路径（**需显式授权**，因
禁改清单含 `experiments/results/**`）：

```bash
python scripts/gates/checksum_results.py \
  --results-dir experiments/results/r4_batches --write
git add experiments/results/r4_batches/SHA256SUMS
```

本批次不改工件。

## 6. 验证结果

| 项 | 结果 |
|---|---|
| 全量 `pytest tests/`（顺序） | **5485 passed / 3 skipped / 1 xfailed / 0 failed**（194.54s） |
| 收集数 | 5489（不变——纯 mock 点迁移，零新增/删除用例） |
| `ruff check src/ config.py experiments/ tests/ scripts/` | 全绿 |
| `mypy src/ config.py` | 0 错误（125 源文件） |
| 本地门禁循环（18 项） | 全绿（`check_swe_bench_pro_ready` / `checksum_results` 为独立入口，按档不在循环内） |
| `check_bilingual_docs --strict` | 绿 |
| `check_baseline` / `check_baseline_numbers` | 绿（`suite_seconds` 已按顺序实测 195s 刷新） |

## 7. 与历史批次的边界

- **本批次范围**：仅孤儿子进程风险面清零 + mock 迁移 + 契约加固 + 治理盘点结论。
- **未纳入本批次**（遗留待办，按原节奏另批处理）：
  - T1d oracle 绑定类型问题（`_precondition_witness_binding` z3 witness 缺失时退化
    字面绑定 `a,b=0,0` 对容器参数可能类型不匹配；下一瓶颈 = 签名推导字面量类型）；
  - P0-5 伪重复去重（实验层，2wk）；
  - P1-6 DSL 扩展（6-8wk）；
  - P1-9 沙箱默认档（4wk）；
  - P2-1 外部基准接通（6-8wk）。

## 8. 变更文件清单

### src（接线 + 契约加固）
- `src/utils/process_utils.py`（`timeout=0` 归一 + `capture_output` 兼容参数 + docstring）
- `src/measurement/mdo.py`
- `src/tools/patch_rollback.py`
- `src/tools/dependency.py`
- `src/tools/testless_validation.py`
- `src/tools/type_repair.py`
- `src/agents/executor_modes.py`
- `src/agents/fl_spectral.py`
- `src/agents/runtime_probe.py`
- `src/agents/executor_repo.py`

### tests（mock 点迁移）
- `tests/test_dependency.py`
- `tests/test_dependency_edge_cases.py`
- `tests/test_type_repair_more_branches.py`
- `tests/test_roadmap_gaps_g1_g2_g3.py`
- `tests/test_testless_validation.py`
- `tests/test_runtime_probe.py`
- `tests/test_executor_docker.py`
- `tests/test_sandbox_hardening.py`
- `tests/test_executor_repo_pure_logic.py`

### 文档 / 基线
- `BASELINE.yaml`（`last_verified` / `suite_seconds` / `mypy_source_files` 刷新）
- `CHANGELOG.md` / `CHANGELOG.en.md`（本批次条目）
- 本报告
