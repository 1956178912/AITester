# 改进方向逐项核实评估报告

> 评估日期：2026-09-25 ｜ 仓库：AITester（0.7 债务清偿期）
> 方法：对提案 5 大类 16 个子方向逐项 grep/read 代码核实（证据均标注 文件:行号）。
> 结论摘要：**提案中绝大多数改进点已在仓库中实现**（多为 0.5/0.6/0.7 债务项落地）。
> 真正剩余的工作集中在：少量子项的"默认开启/文档同步/测试补强"层面，以及 4-5 个
> 有实际缺口的方向。下文逐项给出 已实现 / 部分实现 / 未实现 判定与证据。

---

## 一、评估指标体系的多维化

### 1.1 测试异味检测的深度集成 —— **基本已实现（含全部三个改进点）**

| 提案改进点 | 现状 | 证据 |
|---|---|---|
| 扩展异味类型（Lack of Cohesion / Eager Test AST 检测） | ✅ 已实现，共 6 类异味 | `experiments/analysis_parts/convergence_analysis.py:148-198`（AST 口径 eager_test / lack_of_cohesion，阈值常量 L58-63） |
| 异味与提示策略的关联分析（按生成策略分组） | ✅ 已实现 | `convergence_analysis.py:239-277`（`smell_counts_by_strategy`，按 `details[].strategy` 分组统计各策略异味密度）；`analyze_results.py:417-429` 渲染"异味 × 策略"交叉表 |
| 异味密度作为独立质量维度纳入标准报告 | ✅ 已实现 | `convergence_analysis.py:272`（`smell_density`）；`analyze_results.py:394-414` 标准报告章节"异味密度 / 含异味任务"列 |

说明：4→6 类的扩展已完成且带 AST 保守判定。未引入 NoseSense 18 种异味（提案措辞为"可作为参考"，非硬性要求）。

### 1.2 变异得分与断言强度的协同报告 —— **基本已实现（含全部三个改进点）**

| 提案改进点 | 现状 | 证据 |
|---|---|---|
| 变异得分反馈纳入生成循环（MutGen 式闭环） | ✅ 已实现 | `experiments/mutation_testing.py:617+`（`build_mutation_feedback` 产出 `survived_mutants`）；`src/graph/state.py:177-179`（`mutation_feedback` state 字段）；`src/graph/nodes.py:202` 注入 Generator；`src/agents/generator.py:344-346` prompt 消费；`experiments/run_benchmark.py:255-260` 存活变异体写回 |
| 变异得分 × 断言强度交叉分析 | ✅ 已实现 | `convergence_analysis.py:796-814`（`mutation_assertion_cross`：高分/低分任务平均断言数对比 + `consistent` 判定） |
| 变异体扩展：条件边界变异 + 返回值变异 | ✅ 已实现，共 5 类 | `mutation_testing.py:365-408`（boundary_shift：`Gt↔GtE / Lt↔LtE`）；`mutation_testing.py:418-440`（return_void：`return X → return None`）；类型注释 L45 含 `"boundary"` |

`ENABLE_MUTATION_SCORING` 默认关闭（保持历史口径，与提案描述一致），`reproduce.sh:199-203` 显式设置时启用。

### 1.3 修复收敛效率指标的深度分析 —— **全部三个改进点已实现**

| 提案改进点 | 现状 | 证据 |
|---|---|---|
| 按任务难度分层的修复迭代分布 | ✅ 已实现 | `convergence_analysis.py:400-432`（`_difficulty_stratified_iterations`，难度档由 `experiments/difficulty_stratification.py` 分档后传入） |
| Token 效率曲线（第几轮边际收益最高） | ✅ 已实现 | `convergence_analysis.py:333-397`（`_convergence_token_efficiency`：逐轮增量 Token / 增量通过率，`best_marginal_round` 字段直接回答"第几轮最划算"） |
| 跨基线收敛对比（aitester vs plain_llm 叠加） | ✅ 已实现 | `convergence_analysis.py:435-512`（`_cross_baseline_convergence_comparison`：轮次对齐累计通过率 + `first_attempt_delta` / `cumulative_pass_rate_at_1_delta` 两个对比指标） |

---

## 二、数据集与基线的可信度

### 2.1 SWE-bench 数据污染检测机制的深化 —— **全部三个改进点已实现（语义级为零依赖近似，非 CodeBERT 嵌入）**

| 提案改进点 | 现状 | 证据 |
|---|---|---|
| 多维度污染检测（语义级 + 结构级） | ✅ 已实现 | `experiments/contamination_check.py:121-280`：结构级 `_detect_ast_skeleton_similarity`（AST 语句骨架 + LCS 比率，L138-209）；语义级 `_detect_semantic_cosine`（词袋余弦，零依赖，L210-231）；`_embed_code` 钩子（L232-246）预留 CodeBERT/sklearn 真实嵌入接入，默认未接入 |
| SWE-rebench 抗污染基准支持 | ✅ 已实现（注册表 + 报告章节，非数据加载器） | `contamination_check.py:465-509`（`render_resistant_benchmark_section` + SWE-rebench 注册表）；`analyze_results.py` 已 import 并渲染该章节 |
| 实验报告自动标注高/中/低污染风险 | ✅ 已实现 | `contamination_check.py:282-297`（`_combined_risk_level`：任一维度 high→high，medium→medium，其余→low）；`detect_contamination` 每任务输出 `risk_level` 字段 |

残余缺口：`_embed_code` 真实嵌入（CodeBERT）为可选钩子、默认 None；若需"真实语义嵌入"需装 sklearn/sentence-transformers 并实现钩子——属可选项，非缺口。

### 2.2 跨文件修复能力的实际启用与验证 —— **功能已实现，"启用"为默认关闭的显式开关**

| 提案改进点 | 现状 | 证据 |
|---|---|---|
| SWE-bench 实验显式启用跨文件修复 + 对比 | ✅ 机制已实现 | `reproduce.sh:89-93`（`--cross-file` 开关 → `CROSS_FILE_ENABLE=true`，默认 false）；启用后 workflow 在 executor→debugger 间插入 `cross_file_analyzer` 节点；失败案例分析见 `convergence_analysis.py:515-573`（`_cross_file_failure_analysis`：跨文件信号占比 + 失败 error_category 分布 + import/module 关键词失败占比） |
| 双向依赖图扩展 | ✅ 已实现 | `src/tools/cross_file.py:50-59`（`cross_file_bidirectional()`，`CROSS_FILE_BIDIRECTIONAL=true` 开关）；L138-219 收集"其他模块 → 入口模块"反向依赖边，双向拓扑序应用补丁；测试 `tests/test_cross_file_bidirectional.py` |
| 跨文件修复失败案例分析 | ✅ 已实现 | 同上 `_cross_file_failure_analysis` |

说明：默认关闭是**有意设计**（保持历史单文件实验口径），提案要求的"显式启用 + 对比"通过 `--cross-file` 可完成，非代码缺口。

**P1 真实数据验证可行性更新（2026-09-25）**：SWE-bench 仓库级验证（P0/P1，`RepoExecutor`）落地后，跨文件真实数据 A/B 的前置条件已明确——数据管道（`SWE_BENCH_ENRICHMENT` 注入真实源码）+ 执行环境（RepoExecutor 仓库级 clone + pip install -e + venv 隔离）+ 补丁管道（`_diff_codes` 改用 `git diff --no-index` 生成可应用 unified diff）已全部修通，LLM 补丁可正确 `git apply` 进真实仓库路径。但 P1 单源任务诊断（7 个单源任务 0/7）显示免费档小模型对真实仓库级代码的修复质量不足（5/7 LLM 重写破坏 sqlfluff 插件命名契约 + 2/7 LLM 空补丁），跨文件任务的 gold patch 跨多源文件（单模块 `instance_code` 视角无法覆盖，跨文件分析器需仓库全量源码上下文），因此**跨文件 A/B（ON vs OFF）在引擎能力突破前无正向信息量（ON/OFF 都会 0/N）**，跨文件收益验证需更强模型 + 仓库全量源码上下文重做。当前跨文件架构已实现并经单元测试验证（`test_cross_file.py` 39 用例），真实数据收益作为"已识别的架构 + 引擎能力边界"如实陈述，不强行跑 0/N 的无信息量 A/B。详见 [experiments/results/experiment_report_20260925.md](../../experiments/results/experiment_report_20260925.md) §7.4 与 [docs/design/cross_file_repair.md](design/cross_file_repair.md) §0。

### 2.3 回归测试生成能力的专项增强 —— **已实现（默认关闭的专项能力）**

- `src/agents/generator.py:211-277`：`generate_repro_test()` TDFlow 式复现测试生成（"先失败后通过"，支持跨模块缺陷触发路径，L277）。
- `src/graph/nodes.py:207-217`：generator 节点在 `REPRO_TEST_ENABLE=true` 且已有缺陷描述时接线。
- `src/graph/state.py:192`：`repro_test` state 字段；`tests/test_roadmap_gaps.py:41-58` 覆盖该能力测试。
- 缺口：无实际缺口；开关默认 false（与全仓"新功能默认关"惯例一致）。

---

## 三、系统能力的增强

### 3.1 双向代码-测试诊断机制 —— **已实现（BiVCoder 式 Review Agent，默认关闭）**

- `src/agents/debugger.py:77-84`（`BIDIRECTIONAL_DIAGNOSIS_ENABLE` 开关）+ L253-270（`_run_review_diagnosis`：独立审查智能体判定 实现缺陷/测试缺陷；测试缺陷时**不生成补丁**、返回 `defect_type="test_defect"`）。
- 分支修复路由：`src/graph/workflow.py:230-241`（`_should_debug` 遇 `test_defect` 路由回 generator 重新生成测试，带重新生成上限）；`src/graph/nodes.py:246-253`。
- 三个提案要素（诊断节点/分支修复/Review Agent）全部落地。

### 3.2 对抗性推理机制 —— **已实现（Code Wars/InfCode 式，默认关闭）**

- `src/agents/debugger.py:65-74`（`ADVERSARIAL_DEBUGGING_ENABLE` 开关）+ L311-355（`_generate_adversarial_intents` 生成对抗性程序意图假设；`_build_adversarial_prompt_section` 为每个假设生成针对性测试）。
- 批评者评估：`src/agents/debugger.py:355-405`（`_run_critic_eval` 独立 LLM 调用构造击穿补丁的对抗用例；被击穿触发一次补丁重新生成，L293-311 主流程）。
- 覆盖提案两要点：对抗性意图推理 + 独立批评者构造击穿测试。

### 3.3 执行反馈驱动的修复策略 —— **已实现（三项全落地）**

| 提案改进点 | 现状 | 证据 |
|---|---|---|
| execution_trace 用于提示优化（轻量奖励预测器筛选候选） | ✅ 已实现 | `src/tools/multi_candidate.py:430-494`（`REWARD_PREDICTOR_ENABLE` 开关；`predict_candidate_rewards` 基于历史 trace 覆盖率趋势 + 静态信用筛选候选）；`_coverage_trend` L439-462 |
| 位置感知迭代修复（先定"优先修复哪里"） | ⚠️ **部分实现** | 有 `focus_function` AST 智能截取（`debugger.py:160-166` 截断定位到焦点函数）与错误定位（`error_classifier.py` 行号提取），但**无独立的"修复位置定位"阶段**（LoopRepair 式的先定位后补丁）。现有定位由错误分类器+焦点函数承担，非显式"位置感知迭代修复" |
| 按前几轮 trace 动态调整 temperature/提示策略 | ✅ 已实现 | `src/graph/nodes.py:491-509`（`_dynamic_temperature_from_suggestion`：覆盖率连降时 temperature 减半，真正接线非观测层）；`src/graph/state.py:183`（`iteration_strategy_suggestion`）；`nodes.py:559-560` |

### 3.4 多候选补丁的默认启用与效果验证 —— **已在 reproduce.sh 默认启用；A/B 与适用边界分析为实验工作**

- `reproduce.sh:43-85`：`ENABLE_MULTI_CANDIDATE_PATCH=true` **已默认启用**（`--no-multi-candidate` 可回退历史口径），`MULTI_CANDIDATE_COUNT` 默认 3。提案"默认启用"诉求已满足。
- 多候选静态筛选：`src/tools/multi_candidate.py:75-130`（`static_validate_patch` 含行数/行数比/危险模式守卫）。
- A/B 对比数据与"适用边界分析（断言/运行时/导入哪类收益最大）"：属**实验执行 + 论文撰写**工作，代码层已就绪（多候选 + 奖励预测器 + `error_classifier` 类别齐全），需跑对比实验产出数据。

### 3.5 熔断器与半开探测的完善 —— **全部两个改进点已实现**

| 提案改进点 | 现状 | 证据 |
|---|---|---|
| 冷却期指数退避（30/60/120/240） | ✅ 已实现 | `src/api/api_health.py:76-84`（`circuit_open_count` + `API_CIRCUIT_BACKOFF` 开关；冷却按 `2^open_count` 指数退避，`_probe_circuit_half_open` 消费；关闭时回退固定 60s 作历史对照） |
| 半开探测成功率统计并用于路由权重 | ✅ 已实现 | `src/api/api_health.py:85-89`（`half_open_success` / `half_open_failure` 计数）；`reproduce.sh:96-98`（`API_CIRCUIT_BACKOFF` / `API_PROMETHEUS_EXPORT` 开关）；`api_manager.py:607`（`to_prometheus_text` 暴露） |

说明：退避序列起点为 60s（非提案的 30s 首冷），但机制完整且可用 `circuit_cooldown_seconds` 配置；`API_PROMETHEUS_EXPORT` 开关亦已实装。

---

## 四、工程化与可观测性

### 4.1 结构化追踪层的主动启用 —— **已实现（含 reproduce.sh 主动启用）**

- `src/observability/trace.py`：`TraceSession` 默认 no-op（仅 `AITESTER_TRACE_DIR` 非空时写盘，零性能税），采集每智能体输入/输出快照、Token 消耗、墙钟耗时、路由决策。
- `reproduce.sh:192-195`：**已显式设置** `AITESTER_TRACE_DIR=experiments/results/traces`（提案"在大规模实验中主动设置"已落地）。
- 缺口：无代码缺口；"Token 消耗明细按节点/按任务"由 trace JSONL 支持，消费端（analyze_results）可进一步挖掘。

### 4.2 日志脱敏的完整审计 —— **审计已完成；自动化脱敏回归测试部分实现**

| 提案改进点 | 现状 | 证据 |
|---|---|---|
| 自动化脱敏回归测试（模拟敏感信息注入） | ✅ 已实现 | `tests/test_logging_utils.py`：`test_filter_passes_unmaskable_text`、`test_filter_survives_broken_getmessage`、`test_formatter_masks_exception_traceback`、`test_mask_idempotent_on_redacted_text` 等，覆盖"绕过脱敏"路径 |
| 定期审计（新增日志输出点自动触发脱敏检查） | ⚠️ **部分实现** | `docs/log_redaction_audit.md` 记录四层审计与 R-1 修复（降级路径 `fallback_mask_sensitive_info`）；但"新增日志点自动触发检查"依赖 pre-commit/CI 钩子——当前 `.pre-commit-config.yaml` 未见针对日志脱敏的自动 hook，属**可选增强** |

### 4.3 依赖缓存的监控与清理 —— **全部三个改进点已实现**

| 提案改进点 | 现状 | 证据 |
|---|---|---|
| 缓存命中率纳入 analyze_results 自动汇总 | ✅ 已实现 | `experiments/analysis_parts/cross_analysis.py:60-83`（`_venv_cache_stats_snapshot` 命中统计 + 容量信息）；`analyze_results.py:218/816-840` 渲染命中率章节与容量告警 |
| 缓存容量告警（超 5GB 输出 WARNING） | ✅ 已实现 | `src/tools/dependency.py:567-611`（`check_venv_cache_size`，阈值 `_VENV_CACHE_SIZE_WARN_MB=5120`，超限 `logger.warning`） |
| 多版本依赖缓存并行支持（依赖组合 + Python 版本） | ✅ 已实现 | `dependency.py:233-254`（`venv_cache_dir` 缓存 key = `md5(python_version | 依赖组合)`，目录名 `py{ver}_{digest}_{label}`） |
| venv 统计双锁分离（锁外落盘） | ✅ 已实现 | `dependency.py:308-313`（`_venv_cache_stats_lock` 计数锁 ns 级 + `_venv_cache_persist_lock` 落盘锁，热路径不排队） |

---

## 五、测试覆盖与代码质量

### 5.1 覆盖率薄弱模块的持续补强 —— **大部分已补强，少量边界测试需确认**

| 提案改进点 | 现状 | 证据 |
|---|---|---|
| analysis.py 统计检验边界（样本量=1/全过/全败） | ✅ 已实现 | `tests/test_weak_coverage_modules3.py:122-141`（`test_paired_t_test_constant_pass_rate_skipped`、`test_insufficient_samples_noted`、`test_missing_baseline_not_crash`） |
| cli/app.py 并发中断与信号处理 | ✅ 已实现 | `tests/test_cli_app.py:462/517`（`test_one_future_keyboardinterrupt_does_not_stop_batch`、`test_all_tasks_succeed_after_partial_interrupt`） |
| compare_failures.cross_batch_comparison 单批次边界 | ⚠️ **需确认** | 现有 `tests/test_smell_detection_v2.py:303` 与 `tests/test_failure_kb.py:163` 均为"单批次无趋势"用例，但需确认 `compare_failures.cross_batch_comparison` **本身**在 `--cross-batch` 仅 1 个文件时的行为测试是否覆盖 |

### 5.2 错误分类的持续细化 —— **全部两类已实现（已达 14 类）**

- `src/agents/error_classifier.py:92-93`：`EXECUTION_TRACE_MISSING` 与 `MULTI_CANDIDATE_ALL_REJECTED` **均已实现**（提案要求新增的两类），由 `refine_failure_category`（L634-700）在任务收尾按状态信号判定，不走文本正则。
- 当前枚举共 **14 类**（文档"12 类"表述滞后），`convergence_analysis.py:727` 已将新类纳入 framework 根因归类。测试 `tests/test_error_classifier_new_categories.py`。

### 5.3 失败分析的深度增强 —— **全部三个改进点已实现**

| 提案改进点 | 现状 | 证据 |
|---|---|---|
| 失败根因时间趋势（跨批次占比变化） | ✅ 已实现 | `convergence_analysis.py:693-758`（`_failure_root_cause_trend`：三等分时段占比 + `trend_by_first_third`）；`experiments/analyze_failures.py:88-191`（`root_cause_classification` + `failure_knowledge_base` 案例知识库） |
| reproducible_steps 自动填充（最小复现代码片段） | ✅ 已实现 | `experiments/analyze_failures.py:200-300`（`extract_minimal_repro` 从 diagnosis/error_category/execution_trace 提取最小复现代码片段 → `minimal_repro_code` 字段，无法提取时 None）；L176/184 写入 `reproducible_steps` |
| 与污染检测交叉分析（高污染 vs 修复成功率） | ✅ 已实现 | `experiments/analysis_parts/cross_analysis.py`（`_contamination_cross_analysis`，按 `risk_level` 分组对比成功率）；`analyze_results.py` import 并渲染 |

---

## 结论与剩余工作清单

### 判定汇总

| 子方向 | 判定 | 剩余工作 |
|---|---|---|
| 1.1 异味 | 已实现 | 无 |
| 1.2 变异 | 已实现 | 无 |
| 1.3 收敛 | 已实现 | 无 |
| 2.1 污染 | 已实现 | （可选）接入真实 CodeBERT 嵌入钩子 |
| 2.2 跨文件 | 已实现 | 无（`--cross-file` 启用即可）；P1 真实数据 A/B 在引擎能力突破前无信息量（见 §2.2 P1 更新） |
| 2.3 回归测试 | 已实现 | 无 |
| 3.1 双向诊断 | 已实现 | 无 |
| 3.2 对抗推理 | 已实现 | 无 |
| 3.3 执行反馈 | 基本已实现 | **位置感知迭代修复（LoopRepair 式先定位后补丁）为真实缺口** |
| 3.4 多候选 | 已实现（默认已开） | 跑 A/B 对比 + 适用边界分析（实验/论文工作） |
| 3.5 熔断 | 已实现 | 无（退避起点 60s 而非 30s，可微调） |
| 4.1 追踪 | 已实现 | 无 |
| 4.2 脱敏 | 基本已实现 | **新增日志点自动脱敏检查（pre-commit/CI hook）为可选增强** |
| 4.3 缓存 | 已实现 | 无 |
| 5.1 覆盖率 | 基本已实现 | 确认 `compare_failures.cross_batch_comparison` 单批次边界测试 |
| 5.2 错误分类 | 已实现（14 类） | 文档"12 类"表述滞后，需同步 |
| 5.3 失败分析 | 已实现 | 无 |

### 真实剩余工作（按价值排序）

1. **3.3 位置感知迭代修复**（真实功能缺口）：在 DebuggerAgent 中增加"先定位应优先修复的位置、再生成补丁"的独立阶段（LoopRepair 思路），而非仅靠错误分类器+焦点函数。
2. **4.2 新增日志点自动脱敏检查**（可选增强）：pre-commit/CI 钩子，扫描新增日志调用是否经 `mask_sensitive_info`，防止新代码路径绕过三层防线。
3. **5.2 文档同步**：`error_classifier.py` 实际 14 类，文档/提案"12 类"表述滞后，需更新 `docs/` 与提案描述。
4. **5.1 边界测试确认**：确认 `compare_failures.cross_batch_comparison` 在 `--cross-batch` 仅 1 个文件时的行为有测试覆盖，缺失则补。
5. **3.4 实验工作**：跑多候选 A/B 对比 + 适用边界（断言/运行时/导入哪类收益最大）分析，产出数据入论文（代码已就绪）。
6. **（可选）2.1 真实嵌入钩子**：实现 `_embed_code` 的 CodeBERT/sentence-transformers 接入（当前为零依赖词袋近似）。

> 说明：除上述 6 项外，提案描述的所有改进点在仓库中均已实现并有对应测试。
> 建议优先级：先做 #1（真实功能缺口）、#3（文档准确性）、#4（测试补强），
> #2/#5/#6 视资源与论文进度安排。
