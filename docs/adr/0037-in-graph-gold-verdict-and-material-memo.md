# ADR-0037: 图内 gold 证据裁决与官方测试材料的复用边界

- **状态**：已采纳
- **日期**：2026-11-06（代码落地 2026-11-05，B1 + B10 两轮）
- **关联模块**：`src/tools/patch_evidence.py`、`src/tools/detection_gates.py:189`、
  `src/graph/nodes.py:2604-2606`、`src/graph/state.py`（`official_tests` / `official_test_evidence`）、
  `experiments/run_benchmark.py`（材料注入与工件导出）、`scripts/run_all_tests.py:1613`（口径同源）
- **相关决策**：ADR-0003（默认关的实验卫生纪律）、ADR-0033（判分树包结构 vs 平铺 import）、
  ADR-0020（补丁弃权门）

## 1. 背景

源码补丁证据门（N9 防线）的等级值域是 `gold > sbfl > keyword > none`，门只放行 gold/sbfl。
2026-11-05 最小批暴露：**gold 支在图内永不命中**——`assess_patch_evidence` 的 gold 判据只读
`state["repo_verification"]`，而该键此前只在工作流**结束后**写入、且只走 SWE-bench 仓库级分支。
于是每一轮图内等级只能落在 sbfl（被覆盖率链卡死）/ keyword（非确定）/ none，**正确的源码补丁
按"无证据"被回滚**，这一轮的 LLM 调用因此白付——且从结果行看像"模型没修好"，不是"装置不给证据"。

三条候选路：

| 方案 | 代价 |
|---|---|
| A. 把事后 gold 裁决前移进图内 | 要在图内执行子进程（墙钟、沙箱边界、凭证边界） |
| B. 放宽 keyword 档放行 | 证据语义被稀释——keyword 是诊断文案匹配，不是行为证据 |
| C. 保持回滚，只在分析侧扣除 | 付费浪费留在系统里，读数仍把装置缺陷记成能力缺陷 |

## 2. 决策

选 **A**，并把"证据从哪来"固定为**数据集官方测试**：

1. 等级不足、门正要拒绝时，把该任务的官方测试跑在**打补丁后的源码**上
   （`detection_gates.run_official_tests`）——复用 M1 事后 repair 的**同一执行原语、同一执行错误
   判据、同一"有效通过"谓词**，不新写第二套判分口径；全绿才把等级升为 gold 并放行。
2. **红 / 不可判定 / 无官方测试材料一律仍拒**，不降级成 keyword 放行；材料缺失时门不付子进程成本。
3. gold 答案键（`fixed` / `fixed_module_code`）经**白名单剔除**，不进 state——图内可见的只有
   官方测试与缺陷侧源码，避免把参考答案喂进 prompt（ADR-0012 同侧）。
4. 开关 `PATCH_EVIDENCE_OFFICIAL_TESTS_ENABLE` **默认关**（ADR-0003）：它改变的是证据来源，
   按逐档显式开启；跑批侧由运行器统一置真，与严格口径同源于 `protocol_caliber_env()`。
5. **复用边界（B10）**：只有"结论只取决于测试材料与本机环境"的裁决才可按任务 memo——
   `exec_error` / `runner_unavailable` / `no_effective_pass` / `invalid_module` 四类
   （`patch_evidence._MATERIAL_BLOCKED_REASONS`）；`red` 逐补丁而变、`gold` 意味着门已放行，
   **一律不得 memo**。判据写在集合里而不是写在调用点，避免"看起来无害就缓存"。

## 3. 后果

- **可达性必须先普查再宣称**：quixbugs 节点级可达 40/50；ult 抽检全 red（该面 `fixed` 与
  `instance_code` 逐字相同，是加载器的设计文档化行为，缺陷在消费侧把它当成独立 oracle，见登记册
  B7 轮）；bugsinpy 6 例收集期错误；testgeneval 160 与 swe_bench 223 **无 `test_cases` 材料**——
  这两面需要的是仓库级 gold 执行面，不是把提取器扩宽。
- 真实材料上两模型逐字段一致（`rc=0 / passed=9 / failed=0`）⇒ gold 判定与模型无关，
  这是它作为证据的资格，不是性能主张。
- 默认关时行为逐位不变（开关两侧各有锁）；开档后新增的是**放行支**，不新增拒绝支。
- 观测面：`official_test_evidence`（裁决 + `rc`/`passed`/`failed` 计数）进 raw 工件与结果行，
  失败分支以 `None` 占位保持键集合同构。

## 4. 已知局限与演进方向

- tge / swe_bench 的 gold 仍不可达（需要仓库级执行面，判分树包结构约束同 ADR-0033）。
- memo 的边界按"理由"划，不按"耗时"划：若将来某类 `exec_error` 变成环境瞬时态，
  复用会把它锁一整轮——现由 8 例锁中的三条"不得 memo"反向腿守着，扩集合前先扩锁。
- 门内执行仍是单文件 tmp 树；跨文件任务的官方测试不在本 ADR 覆盖范围内。
