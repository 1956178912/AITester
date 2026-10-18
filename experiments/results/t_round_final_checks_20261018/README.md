# T 轮收尾检查（2026-10-18）

> 提交态（T 轮四个 commit 之后）的最终门禁/探针/自检证据汇总。所有命令零 LLM
> （`doctor`/`e2e-probe` 零 LLM 子集；含 LLM 探针的全量矩阵报告另存 `e2e_probe_t_round_20261018/`），
> 本目录只存**可复算的输出摘要与日志**，不重复存放探针 JSON。

## 1. 检查清单与结果

见 `GATES.md`（逐项命令 + 结果摘要）与 `logs/`（原始输出）。

## 2. 全量测试

- `full_suite_cov.log`：**8929 passed / 5 skipped / 0 failed**（`pytest tests/ -n 4 --dist loadfile --cov=src --cov-branch`，
  COVERAGE_FILE 隔离；总行覆盖 17481/18106=96.55%、分支 6274/6762=92.78%）。
- 注：本日志在**最终提交后**的干净树状态生成（`check_artifacts_tracked` 的 `*_round_*` 扫描面要求本目录已入库）。

## 3. 口径

- 覆盖率/测试计数为**当前提交态实测**，与 BASELINE `tests`/`coverage` 节一致；
- 环境相关跳过（5 例）与 12 个真实 LLM 探针的 skip（零 LLM 子集）均为预期，不是失败；
- 任何失败都必须在本文件"结果"节如实记录，不得只存通过部分的日志。
