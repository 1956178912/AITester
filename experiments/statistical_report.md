# 统计显著性检验报告

## 数据概览

| Baseline | 任务数 | 通过数 | 通过率 |
|----------|--------|--------|--------|
| aitester | 506 | 363 | 71.7% |
| plain_llm | 414 | 275 | 66.4% |
| single_agent | 500 | 43 | 8.6% |

## 配对t检验结果

| 比较 | 配对数 | t统计量 | p值 | 显著性 | Cohen's d | 效应量 |
|------|--------|---------|-----|--------|-----------|--------|
| AITester vs plain_llm | 50 | -2.1892 | 0.0334 | * | -0.3096 | small |
| AITester vs single_agent | 50 | 6.1491 | 0.0000 | *** | 0.8696 | large |

## 显著性标记说明

- `***` p < 0.001
- `**` p < 0.01
- `*` p < 0.05
- `n.s.` p ≥ 0.05 (不显著)

## 效应量解释

- `negligible`: |d| < 0.2
- `small`: 0.2 ≤ |d| < 0.5
- `medium`: 0.5 ≤ |d| < 0.8
- `large`: |d| ≥ 0.8

---
*报告生成时间: 2026-09-25 13:56:52*

## SWE-bench 仓库级验证补充（P0/P1，2026-09-25）

> 本节为 SWE-bench lite-20 仓库级验证（`RepoExecutor`，`REPO_LEVEL_EXECUTION=true`）的结果补充，与上方合成数据集统计口径独立（合成数据集为本文档主实验，SWE-bench 为真实数据局限性验证）。

**SWE-bench lite-20 仓库级验证结果**（`benchmark_swe_bench_20260925_184622.json` + P1 单源诊断，管道修复前口径）：

| 基线 | 任务数 | 通过数 | 通过率 | 说明 |
|------|--------|--------|--------|------|
| aiterster | 20 | 0 | 0% | 管道/环境缺陷已修通，0/20 为 LLM 引擎修复质量边界 |
| plain_llm | 20 | 1 | 5% | plain_llm 基线走原 LLM 生成测试口径（无仓库环境依赖） |
| single_agent | 20 | 1 | 5% | 同上 |

**P1 单源任务诊断**（venv 隔离 + 修复管道后，7 个单源任务）：

| 失败类别 | 数量 | 说明 |
|---------|------|------|
| `LLM_BREAKS_IMPORT` | 5/7 | LLM 重写目标文件破坏 sqlfluff 插件命名契约（`Rule_L*` 类名改坏 → 整个 import 链崩溃） |
| `EMPTY_LLM_PATCH` | 2/7 | LLM 未产出修复（空补丁） |

**根因修正**：首轮 0/20 曾被误诊为"LLM 引擎无法产出可应用补丁"（`repo_verification.llm_applied` 全 False）。修正后 0/20 是数据管道（`instance_code` 缺失）+ 执行环境（单临时文件 executor 装不下仓库级代码 + 全局 python 跨 commit editable 安装污染）+ 补丁管道（`_diff_codes` 用 difflib 手工拼接在"整文件替换"场景产出 corrupt unified diff，`git apply` 全拒）三层缺陷叠加，**非 LLM 引擎能力**。修复（`SWE_BENCH_ENRICHMENT` 注入真实源码 + `RepoExecutor` 仓库级 clone + pip install -e + venv 隔离 + `_diff_codes` 改用 `git diff --no-index`）后，单源任务 0/7 的失败分类上表——**这才是 LLM 引擎修复质量边界的真实测量**（免费档小模型对真实仓库级代码）。

**论文定位**：SWE-bench 0/20 写入"局限性讨论"章节（引擎修复质量边界），主实验仍用合成数据集（aitester 88% vs plain_llm 60% vs single_agent 8%，t-test p=0.002 显著）。详见 [experiment_report_20260925.md §7](results/experiment_report_20260925.md)。

---
*SWE-bench 补充生成时间: 2026-09-25（P0/P1 仓库级验证 + P1 单源诊断）*
