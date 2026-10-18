# U 轮收尾检查（2026-10-18）

> 提交态（U 轮收口批次）的最终门禁/测试/覆盖率证据汇总。所有命令零 LLM；本目录只存
> **可复算的输出摘要与日志**，不重复存放批次工件（U 轮无新 LLM 批次）。

## 1. 检查清单与结果

见 `GATES.md`（25 项门禁逐项命令与结果）与 `logs/`（原始输出，含 `gate_results.tsv`）。

## 2. 全量测试与覆盖率

- `full_suite_cov.log`：**8956 passed / 5 skipped / 0 failed**（collected **8961**；
  `pytest tests/ -n 4 --dist loadfile --cov=src --cov-branch`，**176.43s**；COVERAGE_FILE 隔离）。
- 覆盖率：总行 **17506/18131 = 96.55%**、总分支 **6282/6770 = 92.79%**；
  `coverage_ratchet.py --check` 通过（水位 96.40 / 92.50，余量 +0.15pp / +0.29pp）；
  `check_branch_coverage.py coverage.xml` 通过。
- 与文档一致性：`BASELINE.yaml` `tests`/`coverage`、`docs/PROJECT_STATUS_REGISTER.md` §1、
  `CHANGELOG.md` / `CHANGELOG.en.md` U 轮 Verification 与本次日志逐位一致
  （登记册覆盖率声明经 `check_artifact_doc_consistency.py` 对账复核）。
- 注：上一轮（T 轮）收尾日志见 `t_round_final_checks_20261018/`；本目录为 U 轮最终态。

## 3. 口径

- 环境 = 本机正常环境（无沙箱 broker/ps 限制；5 skipped 为预期：可选依赖等），与 CI 3.14 档同口径；
  沙箱宿主口径 8942 passed / 19 skipped / 0 failed（774.71s，见 BASELINE `tests.total_failed` 注释）。
- U 轮为**零 LLM** 批次：无新增实验数据与 LLM 花费（A-01/A-02/A-04 需预算/人力的项不在本轮范围）。
- 任何失败必须在本文件"结果"节如实记录，不得只存通过部分的日志。
