# ADR-0015：检出优先协议（DETECTION_FIRST_ENABLE，默认关）

- 状态：已采纳（2026-10-05 W 批次落地）
- 关联模块：`config.py`（`detection_first_enabled()`）、`src/graph/workflow.py`（`_should_debug` 路由）、`src/graph/nodes.py`（`_executor_node` 观测写入 / `_generator_node` 强化段落与再生成计数）、`src/agents/generator.py`（`detection_first_section`）、`src/graph/state.py`（`detection_first_red_seen` / `detection_first_status`）、`experiments/run_benchmark.py`（结果行透出）

## 背景与问题

主批次（`experiments/results/main_batch/benchmark_synthetic_20261001_121523.json`）诚实指标实证：

- `false_fix_rate = 89.8%`——"passed"的成功信号是**自产测试在未修复的缺陷代码上通过**；
- 修复循环因此被奖励生成"能让测试通过"的弱测试，而不是"能让缺陷代码变红"的强测试；
- 诚实指标下与 plain_llm 无显著差异（detection 2.0% vs 2.0%，McNemar p=0.4795）。

根因是**奖励错位**（oracle 自指）：成功判定 `test_passed` 由系统自己生成的测试给出，无任何"缺陷被检出"的前置要求。

## 决策

新增检出优先协议（"先红后绿"），环境变量 `DETECTION_FIRST_ENABLE`（默认 false，遵守 ADR-0003 默认行为不变原则）：

1. **首轮红灯观测**（`_executor_node`）：`iteration==0`（被测代码未修复）的每次执行写入
   `detection_first_red_seen = not passed`（True = 测试曾让缺陷代码变红）。
2. **路由**（`_should_debug`）：首轮全绿（`test_passed=True ∧ iteration==0 ∧ 未曾红`）且再生成预算
   未用尽（`regeneration_count < _MAX_REGENERATIONS`）时，**不把全绿当成功**，路由 `regenerate`
   （reason=detection_first_all_green），逼 Generator 产出更强的测试。
3. **强化段落**（`_generator_node` → `GeneratorAgent.generate(detection_first_section=...)`）：
   注入"先红后绿"指令——断言期望值必须来自问题语义（数学定律/规约），禁止放松断言换取通过、
   禁止重写被测函数；并按第 4 类再生成入口 +1 `regeneration_count`（防 executor↔generator 乒乓，
   与 O4 恒真断言路径同类上限保护）。
4. **终态标注**（纯观测）：开关开启且最终通过时写 `detection_first_status`：
   - `red_then_green`：先检出（红）再修复（绿）的完整链路；
   - `all_green_unverified`：从未变红即通过（弱测试假成功）——**评估层不得计为检出/修复成功**。
5. **结果透出**：`run_benchmark` 结果行新增 `detection_first_red_seen` / `detection_first_status`
   两键（默认关时恒 None，键集合同构）。

## 与 M5（test_regenerated_pass_unverified）的关系

M5 标记"再生成后通过 = 假通过"，是**观测层**；本协议是**行为层**——主动再生成更强的测试并把
"从未红过"从不可见变成一等公民字段。两者互补：M5 说明再生成通道存在假成功风险，本协议的强化
段落通过"禁止放松断言"约束该通道的滥用。

## 后果

- 正面：把成功信号与"缺陷被检出"对齐，直指 false_fix 89.8% 的根因；开启后可在不引入 gold 的
  前提下（红-on-original 是 F2P 的"buggy 红"半段，无需 gold 材料）在线改善测试有效性。
- 代价：开启后首轮全绿任务多一次 Generator 调用（+1 LLM call / 任务上限）。
- 风险与缓解：LLM 可能为"变红"而写过苛断言（把正确行为判错）——由修复轮独立验证
  （Debugger 修代码而非改测试 + 命名契约/危险 API 静态门）与 flaky 门禁兜底；
  该风险的量化（开启前后 detection/mutation_detection/false_fix 三指标对比）属于
  实验层后续工作（强模型 + 多种子复跑）。
- 默认关闭：历史批次口径零变化；开启属显式实验行为（与 SPEC_ORACLE_EXEC_ENABLE 等
  "主张配置档"开关同口径，可经 `AITESTER_PROFILE=logic` 组合）。

## 修订记录

- **2026-10-05 X/Y 批次修订**（Amended）：
  1. **plain_llm_df 归因基线**（X1/P0-3）：本协议可叠加到 plain_llm 上运行
     （`build_workflow(allow_regeneration=True)` 新拓扑 + 线程级覆盖
     `config.set_detection_first_thread_override`）——隔离"协议提示词效应"
     与"多智能体编排效应"，强模型下 plain_llm 追平时可归因。
  2. **终态标注第三值 red_not_repaired**（Y1）：原实现仅在 test_passed=True
     时写终态，"全绿→再生成→变红→终止"轨迹下 exec1 的 all_green_unverified
     残留为终值，与 red_seen=True 矛盾（plain_llm_df 真实冒烟发现，trace:
     PASS→regenerate→FAIL→done）。现按 (passed, red_seen) 三值推导
     （`_derive_detection_first_status`）：red_then_green /
     all_green_unverified / **red_not_repaired**（检出成功但未修复——
     plain_llm_df 正常终态，评估层 detection 口径应计数，不得因
     passed=False 丢弃）。
  3. **regeneration_count 透出**（Y1）：结果行新增 `regeneration_count`
     键，量化协议的 +1 LLM call 成本（协议关时恒 None，键集合同构）。
  4. **首份真实运行证据**：2026-10-05 examples/calculator_divide 冒烟
     （free 档模型，工件 /tmp 一次性未入库）：弱测试全绿 → 协议触发再生成
     → 第二版测试检出除零缺陷（红）。协议链路（路由/强化段落/计数/观测
     字段）全链路验证通过；正式量化仍待强模型主批次（P0-1 生死实验）。
  5. **2026-10-06 AA 批次修订**：logic 档预设（`_PROFILE_PRESETS["logic"]`，
     定义于本 ADR 落地之前的 O1 批次）补注入 `DETECTION_FIRST_ENABLE=true`——
     本 ADR"可经 `AITESTER_PROFILE=logic` 组合"的口径由此在配置层成立
     （`tests/test_aa_batch.py::TestLogicProfileDetectionFirst` 锁定）；
     默认档（fast / 不设 PROFILE）零变化。
