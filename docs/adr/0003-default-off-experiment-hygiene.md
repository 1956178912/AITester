# ADR-0003: 默认行为不变原则（实验口径收敛）

- 日期：2026-09（贯穿所有改进批次）
- 状态：已采纳（Accepted，项目级工程惯例）
- 关联：全部新模块（`patch_postprocess.py` / `cost_budget.py` /
  `semantic_cache.py` / `control_flow.py` / `event_bus.py` /
  `multi_candidate.py` / `cross_file.py` 等）

## 背景（Context）

AITester 是**实验科学系统**——每次功能改动都要 A/B 对比
（ON vs OFF 同数据集同模型）。如果新功能默认改变行为（如默认开启
多候选补丁、默认开语义缓存），则历史实验数据（1937 测试基线、
SWE-bench 0/7 测量、50 任务合成实验快照）与新数据不可比，
"改了什么"变成混淆变量。

## 决策（Decision）

**所有新能力默认关闭**（或默认观测层，零路由影响）：

- 环境变量开关（`*_ENABLE`）在**调用期读取**（非 import 期），
  测试可 `monkeypatch.setenv` 切换，保留消融能力；
- 新模块默认行为 = 历史行为（`PATCH_RESAMPLE_ENABLE=false`、
  `SEMANTIC_CACHE_ENABLE=false`、`COST_BUDGET_ENABLE=false`、
  `IMPORT_REPAIR_ENABLE=false`、`CONTRACT_ALIAS_ENABLE=false`）；
- 唯一的"默认开启"例外是**纯观测层**（如 `EMPTY_PATCH_GUARD=true`
  只打标签不改代码、`EVENT_BUS_ENABLE=true` 纯旁路不改路由、
  `execution_trace` 默认常开）——观测层零行为变化；
- 新后处理层（1.1）与契约守卫（1.3）是"修复层"与"拒绝层"的
  互补关系，P2/P3 修复层默认关，1.3 守卫默认开（历史口径，
  修复层启用时守卫仍为最终拒绝层）。

## 后果（Consequences）

**正面**：

- 历史实验数据可复现——所有改进批次的 CHANGELOG 头部都声明
  "默认行为不变"，基线（1937 测试 / 94% 覆盖率）在改进前后
  可对比；
- 消融开关可独立开关每个能力（CI 可跑"全 OFF"回归 + "全 ON"
  性能基准两套口径）。

**负面 / 已知代价**：

- 用户首次使用需显式开启各开关（学习成本）——通过
  `.env.example` 注释 + `QUICKSTART.md` + `docs/api_reference.md`
  开关表缓解；
- 默认关闭意味着默认性能/成本是最差配置（如 5.4 预算上限默认
  关 = 任务可能烧爆 token）——这是"保守"与"最优"的取舍，
  文档明确标注哪些场景应开启。
