# ADR-0028: 修复引擎批次 XIV——FL Top-k 约束观测门 + Self-Repair Trap 观测器（外部报告净新增收割）

- **日期**：2026-10-07
- **状态**：已采纳（两项均为观测层；阻断 / 策略档 Proposed 待预注册）
- **关联模块**：`src/agents/fault_localizer.py`、`src/tools/self_repair_trap.py`、
  `src/graph/state.py`、`src/graph/nodes.py`、`experiments/run_benchmark.py`、
  `docs/design/frame_lifetime_trace.md`

## 背景

第三份外部"前沿对齐审查报告"（对标 TDFlow / TwinMem-Agent /
PhoenixRepair / RGFL / ADI，P0×3+P1×5+P2×3）经对照评估（决策日志
2026-10-07 条目）：诊断基准多处停留在批次 I–XIII 之前的口径，约四成
已覆盖或已立项，**净新增五条**——①FL Top-k 硬约束门（排 A/B 后）、
②test-file-path 冲突检测、③Self-Repair Trap 检测器、④ADI Frame
Lifetime Trace 作 Debugger 拆分批设计输入、⑤PatchDiff 式差分行为
测试（E7 定案后）。

本批次按"观测层先行"（AN2 / ADR-0020 先例）收割其中可离线落地部分，
其余按既定纪律处置（见"决策"④⑤）。

## 决策

1. **①FL Top-k 约束观测门**（判定核纯函数，结果行透出）：
   - `patch_changed_functions(buggy, patched)`：补丁变更函数集合——
     与 `gold_changed_functions` 同一 AST 归属口径（共享
     `_functions_containing_lines`），差异 = **insert 段锚定 buggy 侧
     i1**（纯插入型修复在 gold 口径下是空集合，约束门必须计入）；
   - `fl_constraint_verdict(loc, changed)`：定位 Top-3 候选（叶子名
     归一去重，与 `localization_rank_metrics` 同口径；旧 schema 单候选
     退化）与变更集合求交——`hit`（含 hit_rank）/`miss`/None；
   - 结果行 `fl_constraint_verdict` / `fl_constraint_hit_rank` /
     `fl_constraint_changed_functions`（成功分支实算、失败分支
     None/None/[] 占位；观测层零行为影响，passed 历史口径不变）；
   - **阻断档 Proposed（判据建议稿，转正前须按修正基线预注册修订）**：
     miss 行 correct 率显著低于 hit 行 ∧ A/B 确认不压制 correct 补丁
     ∧ `"<module>"` 级 miss（纯 import/模块级变更）设豁免。
2. **③Self-Repair Trap 观测器**（DCAware 风险口径，零 LLM）：
   - 数据面：`_generator_node` 每次产出测试后追加质量快照至
     `state["oracle_quality_history"]`（断言数/测试函数数/可解析性/
     变异分〔mutation_feedback 可用时〕；空测试不落）；
   - 判定核：`detect_self_repair_trap` 三信号——
     `assert_count_declining`（≥3 可解析快照末两段连续下降）/
     `assertion_collapse`（先有断言后归零，最新快照须可解析）/
     `mutation_score_declining`（≥2 个非 None 且末 < 首；稀疏缺失
     不进判定，AN2 口径）；
   - 结果行 `self_repair_trap_suspected` / `self_repair_trap_signals` +
     `oracle_quality_history`（一并透出供离线复算）；策略切换
     （如强制切 ORACLE_CONTEXT_TIER=minimal 重生成）刻意不做，
     待 A/B 数据与预注册判据。
3. **④Frame Lifetime Trace 设计输入**：`docs/design/frame_lifetime_trace.md`
   （ADI FSE 2026 对齐；63.8% 锚点已核验，报告其余数字标 [未核验]；
   激活门槛 = Debugger 拆分批立项时评审，不预埋开关——ADR-0003）。
4. **②回收（AF 纪律）**：报告 P1-5"test-file-path 冲突检测"在 repo
   模式**已覆盖**——M2 测试文件保护（2026-09-29，`_TEST_PATH_RE`
   覆盖 tests/testing/test_*.py/*_test.py/conftest.py 及 `+++ b/` 新建
   文件形态，O35 补裸 `test.py` 与 `*_tests/` 目录漏检；`executor_repo.
   _apply_llm_patch` 预检拒绝）；repo 模式无生成测试落盘点（grep 实证
   `executor_repo` 零 `generated_test` 引用），攻击面完整闭合。评估
   阶段"三信号不含此项"的判断仅适用于单文件模式——单文件模式下
   补丁只作用于 target_code，无测试路径表面。
5. **⑤延后登记**：PatchDiff 式自动差分行为测试等 E7 人工比对定案后
   评估（E7 worksheet 已有逐行 diff 素材；自动化扩展勿提前立项）。

## 后果

- 结果行新增六键（metrics_schema 同步）；存量批次 JSON 可经
  `_fl_constraint_result` / `_self_repair_trap_result` 离线补算
  （patch / llm_localization 均已持久化，repair_replay 同型）；
- `oracle_quality_history` 为首个**序列型**观测 state 键（列表逐份
  追加，LangGraph 键级替换语义在 generator 单写点下安全）；
- FL 约束门把 ADR-0024"生成侧主导"从分层推断细化为行级可验证命题，
  为第二阶段"编辑意图通道消费定位"（ADR-0018）提供直接证据链；
- Self-Repair Trap 观测为 ORACLE_CONTEXT_TIER 消融（ADR-0025）与
  "恰好一次门参数修正"重跑提供退化预警面。

## 已知局限与演进方向

- **整文件重写补丁下约束门近乎恒 hit**（变更集合 ≈ 全文件函数，无
  约束力）——约束力集中在局部编辑通道；该"hit 率"本身即是"补丁
  局部化程度"的观测量（A/B 消费）；
- `"<module>"` 级变更记 miss 属口径内事实，阻断档须设豁免（判据
  建议稿已含）；
- insert 锚定取 buggy 侧 i1，跨函数边界插入存在粗粒度过归属（记入
  判定核 docstring）；
- 演进：Debugger 拆分批立项时吸收 ④（frame lifetime trace）与约束
  门阻断档；Trap 策略档随 ADR-0025 消融一并设计。
