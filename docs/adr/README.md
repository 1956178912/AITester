# ADR 索引（Architecture Decision Records）

> 维护说明：新增 ADR 时在此表追加一行（编号递增 + 状态 + 一句话摘要 + 关联模块）。
> ADR 正文位于本目录（`docs/adr/`），编号 `NNNN-<slug>.md`。
> 算法设计文档 `docs/algorithm_design.md` 的"相关 ADR"列与此索引保持同步。

| 编号 | 标题 | 状态 | 一句话摘要 | 关联模块 |
|------|------|------|-----------|---------|
| [0001](0001-langgraph-state-graph.md) | 选用 LangGraph StateGraph 作为工作流编排引擎 | 已采纳 | 用带条件回边的循环 DAG 表达多智能体循环修复路径，而非线性 pipeline | `src/graph/workflow.py`、`nodes.py`、`state.py` |
| [0002](0002-error-classifier-rules.md) | 错误分类器采用纯规则匹配（不消耗 LLM token） | 已采纳 | 17 类正则优先级链 + 状态细化层；2026-09-28 批次叠加置信度分层（L1 规则 + L2 协议预留） | `src/agents/error_classifier.py` |
| [0003](0003-default-off-experiment-hygiene.md) | 默认行为不变原则（实验口径收敛） | 已采纳 | 全部新能力以"默认关 + 独立开关"落地，保证 A/B 对比（ON vs OFF）历史口径不变 | 全部新模块（`patch_postprocess.py` 等） |
| [0004](0004-zero-default-deps.md) | 零默认外部依赖（可选依赖透明降级） | 已采纳 | 核心能力只依赖 langgraph/openai/pytest；可选增强（chromadb/onnxruntime/mypy 等）缺失时透明降级 | `requirements.txt`、`src/utils/embedding_utils.py` |
| [0005](0005-node-degradation.md) | 节点异常降级兜底（工作流不崩溃） | 已采纳 | 各节点捕获 LLM 调用 / 缓存 / 预算异常并降级，避免 LangGraph 整图中断 | `src/graph/nodes.py`、`src/agents/base_agent.py` |
| [0011](0011-llm-cache-user-isolation.md) | LLM 缓存用户隔离与创建者归属 | 已采纳 | `creator_uid` 字段写入 + 读侧 `cache_creator_ok()` 归属校验，封堵跨用户 / 跨 CI 步骤投毒面；`AITESTER_CACHE_CREATOR` 多租户逻辑隔离 | `src/agents/llm_client.py` |
| [0012](0012-prompt-injection-defense.md) | Prompt Injection 防御层（输入检测 + 补丁安全校验） | 已采纳 | 输入侧 4 类特征检测 + 输出侧 5 类危险操作静态校验，纯正则零 LLM 成本，默认关 | `src/agents/injection_guard.py` |
| [0013](0013-classifier-explanability.md) | 错误分类可解释性字段与修复策略追踪链 | 已采纳 | `ClassificationResult.explanation` 命中特征 / 置信度口径 / 兜底标注，四环节追踪链闭环，零 LLM 成本 | `src/agents/error_classifier.py` |
| [0014](0014-branch-coverage-gates.md) | 分支覆盖率门槛上调（总 85% / 核心修复路由模块 90%） | 已采纳 | 总门槛 79%→85% + 核心修复路由模块 90% 严格门槛；总分支率改用加权聚合修复口径漂移 | `scripts/check_branch_coverage.py`、`tests/test_workflow_combinations.py` |
| [0015](0015-detection-first-protocol.md) | 检出优先协议（DETECTION_FIRST_ENABLE，默认关） | 已采纳 | "先红后绿"成功口径：首轮全绿不再视为成功，路由一次再生成强化测试；终态标注 red_then_green / all_green_unverified | `config.py`、`src/graph/workflow.py`、`nodes.py`、`src/agents/generator.py` |
| [0016](0016-orchestration-container-repositioning.md) | 编排定位重述：可消融容器 + 检出优先轻量管线 | 已采纳 | 生死实验（−28pp vs 纯提示协议、8.1× token）实证编排净负后，增益主张收缩为检出优先协议 +43pp；双门（特异性门/红回归门）为协议层扩展；修复循环测试文件锁定；AK 补修复上限归因（patch 产出 94%/plausible 47%/correct 0） | `src/tools/detection_gates.py`、`src/graph/workflow.py`、`experiments/statistical_analysis.py`、`experiments/repair_ceiling_analysis.py` |
| [0017](0017-repair-engine-pivot.md) | 修复引擎范式转向（局部化 → 合成 → 验证） | 已采纳 | E2 定案（门削过红 65%/抹红 93%、H2c 编排结构性劣后确立、FL@1 35.8%）+ repair 全线 0 后用户拍板转向修复引擎路线；独立 FaultLocalizer 落地（谱系 + RGFL 推理双通道，只定位不修复，保守降级 None）；局部化独立指标 `localization_hit_function`；`FAULT_LOCALIZER_ENABLE` 默认开（ADR-0003 显式例外，消融对照经同开关保留） | `src/agents/fault_localizer.py`、`src/agents/fl_spectral.py`、`src/graph/nodes.py`、`experiments/run_benchmark.py` |
| [0018](0018-edit-intent-deterministic-landing.md) | 结构化编辑意图 + 确定性落盘 | 已采纳（默认关，A/B 后转正） | diff 静默错应用实证（2609.00227：宽容 diff ~1/7 错应用；Diff-XYZ：search/replace 最优）+ 整文件替换伪影（E7 工作表）→ LLM 产 edit_intents（唯一锚点 search/replace，多 Hunk 每处一条）、确定性引擎校验落盘（锚点唯一性 + 原子性 + AST 门），成功替换整文件 patch、失败原子回落；`EDIT_INTENT_ENABLE` 默认关（ADR-0003）；随批修复 AC2 过红再生成入口计数漏计（E2 触顶根因通道） | `src/tools/patch_intent.py`、`src/agents/debugger.py`、`src/graph/nodes.py`、`experiments/run_benchmark.py` |
| [0019](0019-deterministic-repair-first.md) | 确定性优先修复路由 | 已采纳（默认关，A/B 后转正） | 修复循环对 syntax/import/name-error 类失败整轮进 LLM 而其中一部分有零 token 确定性修法（PAGENT 针对性确定性层挽回 22.8% 类型失败；2606.26978 成本调度）→ 三个保守变换器（缺 import 推断〔标准库白名单〕/ 导入别名回填〔唯一嫌疑〕/ tab 缩进归一）+ AST 验证门；`DETERMINISTIC_REPAIR_FIRST_ENABLE` 默认关，开启时首修复轮先走路由、命中即跳过该轮 LLM，`deterministic_repair_status` 非 None 哨兵防重试（每任务至多一次）、无效自然回落 LLM | `src/tools/deterministic_repair.py`、`src/graph/nodes.py`、`src/graph/state.py`、`experiments/run_benchmark.py` |
| [0020](0020-patch-abstain-gate.md) | 补丁弃权门（观测层先行） | 已采纳（观测层）；阻断档 Proposed | IDR 27.78%（72% plausible-but-wrong 零负信号通过）+ Abstain-and-Validate +39pp → 五信号判定核（M5 假通过/全程全绿未检出/终审过红/证据 none/写盘未验证，纯函数零 LLM）；观测层结果行 `patch_abstained`/`patch_abstain_signals`（passed 历史口径零变化）+ CPR/IDR 弃权视角节（存量回放首测：passed 压制 392/443=88.5%、精确率 1.0——无 gold 运行时重构 false-fix 类）；阻断档（回滚+终态 abstained）待 A/B 按预注册判据转正 | `src/tools/patch_abstain.py`、`experiments/run_benchmark.py`、`experiments/cpr_idr_report.py` |
| [0021](0021-repair-zero-measurement-artifact.md) | repair=0 围栏伪影定案（测量口径修复 + 存量重放） | 已采纳 | patch 透出口径（可含围栏约定）≠ 执行口径（写盘清理）分叉：274/274 带补丁行 `python\n` 残留使 M1 独立裁决 100% 失败 → "repair 全线 0"系伪影；修正重放 266 可重放行 correct=103（38.7%，E2 双种子 44–48%）；`normalize_patch_text()` 单一权威清理 + `_target_code_after_patch` 对齐 + `experiments/repair_replay.py`（`make repair-replay`）+ 负向后瞻加固；ADR-0017 动机勘误（转向不撤销、第二阶段优先级重排） | `src/tools/patch_applier.py`、`experiments/_m1_metrics.py`、`experiments/repair_replay.py` |
| [0022](0022-test-hacking-guard.md) | test-hacking 确定性守卫（观测层） | 已采纳（观测层）；阻断档 Proposed | 自生成测试验收下作弊补丁（硬编码输入分支/断言删除/吞异常）零负信号通过（IDR 同族缺口）→ AST 差集三信号检测核（零 LLM，原有结构零误报）；结果行 `test_hacking_suspected`/`test_hacking_signals`（passed 零变化，AN2 先例）；阻断档 A/B 判据 = 误伤率 ≤ 阈值 ∧ false_fix 富集 | `src/tools/patch_test_hacking.py`、`experiments/run_benchmark.py` |
| [0023](0023-eval-report-pass-at-k-cost-solved-contamination.md) | 评估报告口径收口（pass@k / $/solved / 污染视角） | 已采纳（呈现性增补） | 第十七轮审查建议 11/14/22 → pass@k（HumanEval 无偏估计，同 task 跨批次 = 轮次，k 不足诚实截断）+ $/solved（对齐 $/resolved，correct=0 诚实未定义）+ 污染视角（行级三维分级按臂聚合 + 含污染 vs 干净对照）；三节入统计报告并携带 ADR-0021 伪影披露 | `experiments/statistical_analysis.py` |
| [0024](0024-counterfactual-fl-upper-bound.md) | 反事实 FL 上界分析（存量分解 + gold 注入臂） | 已采纳（回放已出数；运行时臂默认关） | FL×correct 2×2 分解定位瓶颈——**首测（53 行）：P(correct\|FL命中)=15.8% < P(correct\|FL未命中)=64.7%（负相关）→ FL 瓶颈假设首测修正，生成侧主导（FL 命中组 84% 修不好），整文件重写对定位信号消费弱**；运行时臂 FL_GOLD_INJECTION_ENABLE（gold 函数构造定位，跳过 LLM，AC2 卫生口径显式例外登记） | `experiments/cf_upper_bound.py`、`src/agents/fault_localizer.py` |
| [0025](0025-oracle-context-ablation-tier.md) | oracle 生成上下文消融档 ORACLE_CONTEXT_TIER | 已采纳（默认 full，A/B 后再议） | ASE 2025"额外上下文无边际收益"实证 → minimal 档剥离四增强段（分支覆盖/AST 边界锚点/蜕变/差分），target_code 仍注入（测试骨架必需）；A/B 协议：同任务集 × 两档比较 spec_compile_rate/mutation/token | `src/tools/logic_spec.py`、`src/graph/nodes.py` |
| [0026](0026-interaction-centric-failure-attribution.md) | 交互中心失败归因（edge × fault_side 增补） | 已采纳 | "Model or Harness?"交互中心分类方向 → 终局桶增补 interaction_attribution（回归门拦截=harness 侧与补丁质量=model 侧显式区分；收敛行不冒充归因）；修复动作指向列入渲染；MAST 式桶分布保留跨臂职能 | `src/observability/failure_taxonomy.py` |
| [0027](0027-corrected-caliber-re-estimation.md) | 修正口径重估收口（false_fix/CPR/弃权精确率 + 归因解混杂） | 已采纳 | ADR-0021 勘误义务执行：`make corrected-metrics` 四节重估——R-P0-2 修正 repair 35.9%、E1/E2 48.1%、早期 10-01 批 0/15 系真零（false_fix=89.8% 证据维持）；修正 false_fix 87.2% 非平凡；CPR 84.3% 与弃权精确率 86.0% 首次有真实分母（阻断档判据 ①② 落地，潜在误伤 15.7% 须先预注册）；bug_type 分层解混杂通过（负相关层内成立，ADR-0024 生成侧主导结论加固）；README 中英/prereg 中英/BASELINE 随勘误（AL5 锁推进） | `experiments/corrected_metrics.py`、`experiments/repair_replay.py` |
| [0028](0028-fl-constraint-gate-self-repair-trap.md) | 修复引擎批次 XIV——FL Top-k 约束观测门 + Self-Repair Trap 观测器（外部报告净新增收割） | 已采纳（观测层）；阻断/策略档 Proposed | 第三份外部报告对照评估净新增五条的离线收割——①`patch_changed_functions`（补丁变更函数集合，insert 锚定）+ `fl_constraint_verdict`（Top-3 候选与变更集合求交，hit_rank 分层）→ 结果行三键，ADR-0024"生成侧主导"行级可验证；③`oracle_quality_history` 快照序列 + `detect_self_repair_trap` 三信号（DCAware 口径）→ 结果行三键；④Frame Lifetime Trace 设计输入（docs/design，激活门槛=Debugger 拆分批立项）；②test-file-path 回收（M2+O35 已覆盖）；⑤PatchDiff 延后（E7 定案后） | `src/agents/fault_localizer.py`、`src/tools/self_repair_trap.py`、`src/graph/nodes.py`、`experiments/run_benchmark.py`、`docs/design/frame_lifetime_trace.md` |

## 状态约定

- **已采纳（Accepted）**：决策已落地，模块行为以此为准；
- **已废弃（Deprecated）**：被后续 ADR 取代，保留历史记录；
- **已取代（Superseded by NNNN）**：指向取代它的 ADR；
- **提案中（Proposed）**：待评审。

## 维护惯例

1. 新增 ADR 用下一个可用编号（当前 0001–0005、0011–0028 已用 → 下一个
   0029；0006–0010 为历史保留段——AL 批次经 git 历史核实**从未被使用**
   （`git log --diff-filter=A` 零命中），为避免与外部引用错位不再回收，
   新 ADR 勿占用该段）；
2. 文件命名 `NNNN-<kebab-slug>.md`；
3. 正文结构：`# ADR-NNNN: 标题` + 元信息（日期 / 状态 / 关联模块）+
   背景 / 决策 / 后果 / 已知局限与演进方向；
4. 落地改动须在 ADR"已知局限与演进方向"或本索引标注批次日期；
5. `docs/algorithm_design.md` 的"相关 ADR"列须与本表同步（新增 ADR 时
   评估是否影响算法设计映射表）。
