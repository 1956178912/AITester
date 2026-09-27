# ADR-0014: 分支覆盖率门槛上调（总 85% / 核心修复路由模块 90%）

## 状态

已接受（2026-09-29 批次落地；门槛收紧，CI 门禁同步）

## 背景

外部数据支撑：

- 任务关键软件标准（RTCA DO-178C）要求 100% 分支覆盖；行业实践
  （特斯拉车载控制器）以"分支覆盖 ≥90% 方可合并"作为阻断策略。
- 本仓 `scripts/check_branch_coverage.py`（8. 批次）原有口径：总门槛
  79%（实测 79.56% 的保守值）+ 核心路由模块 85%。
- 2026-09-28 改进批次后实测：总 79.56%、`graph/workflow.py` 90.48%、
  `agents/error_classifier.py` 88.46%（< 90% 目标）、`state` /
  `tracing` 100%。
- 本仓是**修复框架**（条件路由密集：`_should_debug` /
  `refine_failure_category` / 多候选触发），分支覆盖不足意味着
  "达上限 × 关键词命中 × 再生成上限"交叉场景长期未被测试——
  修复质量的瓶颈区。

## 决策

`scripts/check_branch_coverage.py` 门槛分两级（单一来源，
CI 门禁 + 本地脚本同口径）：

| 层级 | 模块 | 旧门槛 | 新门槛 |
|---|---|---|---|
| 总门槛 | 全仓 `--cov-branch` | 79% | **85%** |
| 严格核心 | `graph/workflow.py`、`agents/error_classifier.py` | 85% | **90%** |
| 普通核心 | `graph/state.py`、`graph/tracing.py` | 85% | 85%（不变） |

配套补全（本批次内）：
- `tests/test_error_classifier_combinations.py`：refine 交叉场景、
  L2 注入三态、全类别策略查表、LLM 响应分类边界——把
  `error_classifier.py` 分支覆盖从 88.46% 补过 90% 严格门槛；
- `tests/test_branch_coverage_gates.py`：门槛常量同步断言
  （`_TOTAL_THRESHOLD==0.85`、`_STRICT_CORE_THRESHOLD==0.90`），
  防脚本与测试口径漂移；
- 脚本同时修复 `src/` 前缀 filename 归一（部分 coverage 版本把
  模块路径写成 `src/graph/workflow.py`，旧解析 0% 误报）。

## 后果

- 正面：修复路由密集区的交叉场景获得 CI 阻断级保障；"实测值→
  门槛"的保守上调节奏（79% → 85% 总 / 90% 严格）与组合测试
  补全同批推进，门禁转红即可定位缺口模块。
- 负面：门槛收紧后，任何删测试 / 加复杂分支未补测试的合并会被
  CI 阻断（预期行为）；总门槛 85% 依赖全仓组合测试持续补全，
  短期 CI 门禁对总分支的校验以 `coverage.xml` 实测为准。
- 后续：85% → 90% 总门槛、90% → 95% 严格门槛的进一步上调
  待组合测试补全节奏跟上（每批次回填实测值）。

## 参考

- 改进建议 3.1（分支覆盖率门槛）；
- 8. 批次（核心路由模块门槛守卫原始设计）；
- `tests/test_branch_coverage_gates.py`、`tests/test_error_classifier_combinations.py`。
