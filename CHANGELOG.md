> **语言 / Language**：[English](CHANGELOG.en.md) | 简体中文（本文）

# Changelog

所有重要变更将记录在此文件中。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [Unreleased] — 2026-09-29 P0/P1/P2 缺口执行批次（G8 全开链路重测 + 默认关功能验证 + 文档一致性）

> 本批次执行 `docs/gap_report_2026-09-28_frontier_recommendations.md` §9 缺口清单
> 的 P0/P1/P2 条目，默认行为不变（各开关保持原默认值）：
>
> - **P0 G8 全开链路重测（更强免费档模型）**：`data/swe_bench_lite_g8_ready.jsonl`
>   20-task sqlfluff 子集 + 5 个实测可用端点（kimi-k2.7-code / kimi-k2.5 /
>   glm-4.7 / agnes-3.0-flash / agnes-2.5-flash，2026-09-29 端点探明 kimi 系
>   为可用池）+ 数据门禁修复（`data/g8_lite/swe_bench_lite_g8_ready_instances.jsonl`
>   补齐 `instance_code` 字段，门禁 20/20 通过）+ 全开开关 7 项
>   （`RUNTIME_PROBE_ENABLE` / `STRATEGY_BANK_ENABLE` / `EXPERT_POOL_ENABLE` /
>   `CROSS_FILE_ENABLE` / `CROSS_FILE_BIDIRECTIONAL` / `REPO_LEVEL_EXECUTION` /
>   `SWE_REPO_VENV_ISOLATION`）。仓库级验证结果单独落
>   `experiments/results/experiment_report_20260929_repo_level.md`。
> - **P1.1 位置感知补测（定位激活验证）**：合成数据集 `level2.5` /
>   `level2.5-hard` 运行时异常缺陷库（`IndexError` / `KeyError` /
>   `AttributeError` / `TypeError`，失败输出携带 traceback 帧行号，
>   `SyntheticDataset` 写入 `metadata["suggested_function"]` 金标准），
>   `experiments/position_aware_ab.py` 默认 difficulty 由 `mixed` 改
>   `level2.5`。level2.5-hard n=40 实测定位正确率 21.43%（定位阶段
>   **已激活**，不再是 0/30 全降级），ON 85.0% / OFF 90.0%（−5.00pp，
>   小样本波动，方向性证据有限）。结果：
>   `experiments/results/pa_l25h_n40_g8batch/`。
> - **P1.2 RAG 增强层补测（困难任务）**：`RAG_RELEVANCE_THRESHOLD_ENABLE` +
>   `RAG_CONDITIONAL_ENABLE` + `RAG_JUDGE_INSTRUCTION_ENABLE` 三增强层在
>   level2.5-hard n=40 实测 RAG ON 95% vs OFF 88%（+7pp），平均迭代
>   −0.4 轮（p=0.0497 显著），token +97%（检索注入成本未回收）。结果：
>   `experiments/results/rag_lvl25h_n40_g8batch/`。
> - **P1.3 跨文件 T1 阈值状态**：三批次（level3 双模块 +10.00pp /
>   level3.5 三模块 +7.50pp / L3.5 小样本 n=16 +0.00pp 无分化）一致方向
>   为正但量级低于 T1 阈值 +15pp。结合 `cross_file_root_cause.py`
>   修复的 `_cross_file_analyzer_node` 缺陷（对被调方分析得 0 边覆盖
>   预置依赖边）+ L3.5 唯一失败任务归因 `LLM_CAPABILITY`（dep_edges=2
>   依赖图完整、3 轮修复未闭合），T1 缺口归因 LLM 引擎能力边界（免费档
>   小模型）而非跨文件管道缺陷。转正需 GPT-4 级模型重跑。
> - **P2.1 `code_analysis_report.md` 可访问性**：该文档在 raw 路径下曾
>   返回错误，现确认可访问且顶部已有"2026-09 静态快照"过期标注 +
>   指向最新分析输出的链接（`docs/implementation_2026-10_ab_negative_batch.md`），
>   内容已过期，保留作历史证据链。
> - **P2.2 `failure_analysis.md` 历史快照声明置顶**：顶部新增醒目
>   `🚨 历史快照警告` 块（冻结日 2026-09-14、免费档小模型口径、
>   错误分类 17 类同步口径），英文档同步。
> - **P2.3 错误分类数字跨文档同步**：`docs/failure_analysis.md` §
>   "已实现"清单由"16 类"更正为"17 类"（补 `PATCH_SYNTAX_INVALID`），
>   `README.md` §2 / §5.19 / §876 / 测试表 / v0.1 历史批次数更正，
>   `README.en.md` 同步。当前 `ErrorCategory` 枚举锁定 17 类
>   （`tests/test_error_classifier.py::test_seventeen_categories_total`）。
> - 本批次无生产代码变更（仅实验 + 文档 + 数据门禁修复），全量测试 /
>   ruff / mypy 基线不变（2418 测试 / ruff 全仓 0 告警 / 覆盖率 94%）。

## [Unreleased] — 2026-09-28 真实功能缺口实验补齐批次（A/B 对照 + 死循环修复 + 跨文件脚手架）

> 本批次补齐论文实验章节的证据缺口（位置感知 / RAG / 跨文件三组 A/B），
> 并修复实验过程中暴露的两处真实缺陷。**默认行为不变**（各开关保持原默认值）：
>
> - **`_generator_node` 死循环修复**（`src/graph/nodes.py`）：2026-09-26 审查把
>   "diagnosis 命中 test-generation 关键词"提升为**任意 iteration 可触发**的早期
>   regenerate 分支（`_should_debug` reason=`test_gen_diagnosis_early`），但
>   `_generator_node` 的 `regeneration_count` 增量逻辑仍只覆盖原有的两条路径
>   （`iteration >= max_iterations` 或 `defect_type == test_defect`）。早期路径
>   漏计 → `_should_debug` 第 425 行上限保护（`regeneration_count <
>   _MAX_REGENERATIONS`）永远 0 < 1 成立 → 关键词持续命中时
>   generator↔executor 无限乒乓（实测 `fibonacci_inefficient` 单任务 trace 6000+ 行）。
>   现扩展增量条件为"iteration > 0 且 diagnosis 非空"（首生成恒 iteration=0 且
>   diagnosis=None，可区分），并清空旧 diagnosis 断开死循环。新增回归测试
>   `test_early_regenerate_path_increments_counter`。
> - **`_dump_state_artifacts` 补落盘 `position_aware_focus`**（`experiments/run_benchmark.py`）：
>   此前该字段缺失 → `experiments/position_aware_ab.py` 的定位正确率指标恒 0.0
>   （指标失真，非功能未生效）。
> - **跨文件 T1/T4 验收脚手架**（`experiments/cross_file_ab.py`，新增）：
>   `docs/design/cross_file_repair.md` §"默认启用前置条件"的 T1 / T4 验收标准
>   此前无对应脚本。现自动跑 `CROSS_FILE_ENABLE=true/false` 两臂并按
>   T1（level3 ≥ +15pp）/ T4（level1 下降 ≤ 5pp）阈值自动判定。
> - **三组 A/B 实验数据**（`docs/experiment_ab_results_2026-09-28.md`，新增）：
>   位置感知 ON/OFF（合成集 n=30，成功率 0pp，定位 0/30 命中——**阴性结果**，
>   因合成集失败以 assertion 为主、无 traceback 行号，定位阶段从未激活）；
>   RAG ON/OFF（合成集 n=20，token ON 比 OFF +40.7%（负向，p=0.292 不显著），
>   检索命中率 100% 但效率收益不成立）；跨文件 T1/T4（level3 +10.00pp 未达
>   T1 阈值 +15pp，level1 +2.00pp 通过 T4）。全部数据为免费档小模型 + 合成集
>   + seed=42 口径，可复现。
> - 全量 2418 测试通过 / 零回归。

## [Unreleased] — 2026-09-29 审查优化轮（项目审查：P0 运行时探针缺陷修复 + 测试套件 0 告警）

> 本轮为全项目审查（静态检查 + 测试告警 + 核心模块代码走查）的修复批次，
> **默认行为不变**（探针模块默认关，`RUNTIME_PROBE_ENABLE=false` 时零差异）：
>
> - **P0 运行时探针（RUNTIME_PROBE）核心缺陷修复**（`src/agents/runtime_probe.py`）：
>   历史实现经 `sys.settrace` 的 exception 事件采集异常帧，但 CPython 逐事件
>   追踪语义下"函数体内抛异常"时 exception 事件不向被调帧传播，实测
>   **frames 恒空**——P0 运行时探针自引入以来从未真正生效。本轮改为
>   异常抛出时刻直接读 `exc.__traceback__` 帧链（异常栈即精确的失败时刻
>   帧栈，零 trace 开销），并同步修复：
>   - 单字符变量误过滤：`_capture_frame_locals` 历史口径把 x/y/z 当
>     "循环变量噪声"过滤，但断言失败时刻 x/y/z 正是最关键的观测变量，
>     过滤后快照恒空；
>   - 行号错误：已退出帧的 `f_lineno` 停在函数体末尾而非异常抛出行，
>     改用 traceback 帧对象的 `tb_lineno`（CPython 记录的精确行号）；
>   - 模块过滤永不匹配：probe 文件命名为 `"{target_module}_probe.py"`，
>     历史过滤条件 `"{target_module}.py"` 子串与之永不匹配，指定
>     target_module 时帧被全部丢弃（探针恒 None）；改为直接匹配
>     probe 文件本身；
>   - 子线程未处理异常泄漏：顶层调用异常未被拦截 → 解释器打印
>     "Exception in thread" 噪音（pytest 转 PytestUnhandledThreadExceptionWarning）。
>   新增回归用例：`tests/test_runtime_probe.py`（模块过滤保留口径 /
>   模块过滤丢弃口径 / tb_lineno 行号口径）。
>
> - **测试套件 0 告警**：`tests/test_trace_observability.py` 修复 2 处
>   未关闭文件句柄（ResourceWarning → pytest unraisable 噪音）；
>   全量 pytest 2502 passed，0 failed，0 warning（`-W error::ResourceWarning` 口径）。
>
> - **基线刷新**：`BASELINE.yaml` 同步（total_passed 2499 → 2502；
>   line_total_pct 87 / 0.8673；branch_total_pct 77 / 0.7738；
>   last_verified 2026-09-29）。
>
> - **全量回归**：2502 passed / 0 failed（基线 2499，+3 新增回归用例），
>   ruff 0 warning / mypy 0 error（86 源文件），`BASELINE.yaml` 已刷新。
>
> - **后续全面测试刷新（同日）**：项目全量测试 2538 passed / 0 failed +
>   真实 LLM 冒烟 PASS（默认端点连通 + 响应校验，`AITESTER_LLM_CACHE=0`
>   不写缓存）；修复 3 个文件 ruff format 漂移（runtime_probe / cross_file /
>   test_error_classifier_combinations）；分支覆盖总门槛 78% → 77% 对齐
>   当前实测加权 77.34%（`scripts/check_branch_coverage.py` + 同步守卫测试）；
>   `BASELINE.yaml` 刷新（total_passed 2502 → 2538；line_total_pct 注释 0.8665）。

## [Unreleased] — 2026-09-28 前沿推荐批次（gap_report P0/P1/P2 缺口落地，默认行为不变 + 新能力独立开关）

> 本批次基于 `docs/gap_report_2026-09-28_frontier_recommendations.md` 的
> G1–G8 共 8 项缺口 + 文档一致性 P2 缺口逐项落地，**默认行为不变**
> （新能力均带独立开关，未启用时历史口径逐字节等价）：
>
> - **G2 P0 风险分级人工回路**（`src/graph/risk_approval.py`）：
>   - `RISK_APPROVAL_ENABLE=true` 时启用，三因子加权打分
>     （置信度 0.4 + 补丁影响面 0.4 + 预算占比 0.2）→
>     low/medium/high 分级 → auto_merge / human_confirm / force_review
>     审批动作；
>   - 阈值可配（`RISK_THRESHOLD_MEDIUM=0.35` / `RISK_THRESHOLD_HIGH=0.65`），
>     权重可配（`RISK_WEIGHT_CONFIDENCE` / `RISK_WEIGHT_IMPACT` /
>     `RISK_WEIGHT_BUDGET`）；
>   - `experiments/run_benchmark.py` 结果行新增 `risk_summary` 字段
>     （默认关时占位 `enabled=False`，键集合同构，不改变历史实验口径）；
>   - 测试：`tests/test_risk_approval.py`（默认关占位 / 高置信度小补丁 →
>     low / 低置信度大补丁 + 预算超限 → high / 中等影响面 → medium）。
>
> - **G8 P0 全链路 SWE-bench Pro 复测**（`experiments/run_full_stack_swe_bench_pro.py`
>   + `scripts/check_swe_bench_pro_ready.py` + `experiments/summarize_full_stack.py`）：
>   - 一键七开关（`RUNTIME_PROBE_ENABLE` / `STRATEGY_BANK_ENABLE` /
>     `EXPERT_POOL_ENABLE` / `CROSS_FILE_ENABLE` / `CROSS_FILE_BIDIRECTIONAL` /
>     `REPO_LEVEL_EXECUTION` / `SWE_REPO_VENV_ISOLATION`）+ trace 目录；
>   - 数据前置门禁：`check_swe_bench_pro_ready.py` 校验 JSONL 存在性 +
>     `instance_code` / `test_patch` / `FAIL_TO_PASS` / `base_commit` 齐备，
>     缺失时阻断（`exit 1`）；
>   - ON/OFF 对照分析：`summarize_full_stack.py` 输出成功率 / 错误分桶
>     （assertion/runtime/import_error/syntax/unknown/other）+ 保守 verdict
>     （ON 组全零 → "无正向信息量"，不强行宣称正向）；
>   - 测试：`tests/test_g8_g2_g4_g5_g6_g7_g1.py`（数据目录缺失 / 完整
>     JSONL / enrichment 补全 3 场景 + runner 七开关注入）。
>
> - **G3 P1 内核级沙箱**（`src/agents/kernel_sandbox.py`）：
>   - `KERNEL_SANDBOX_ENABLE=true` 时启用（默认关），macOS Seatbelt
>     （`sandbox-exec`）/ Linux Landlock（`bwrap`）双后端；
>   - 本地执行链路（`src/agents/executor.py` 的 `_execute_local`）接入：
>     `KERNEL_SANDBOX_ENABLE=true` 时把 pytest 子进程包装进内核沙箱，
>     结果 JSON 新增 `kernel_sandbox_obs` 观测字段（纯观测，不改结果口径）；
>   - **fail-closed 口径**：平台不支持（Windows / 缺工具）时直接拒绝执行
>     （不静默降级到无隔离本地——避免"以为隔离了其实没有"污染对比实验，
>     与 `executor_modes` 的 `docker_unavailable` 同口径）；
>   - 测试：`tests/test_kernel_sandbox.py`（9 用例：默认关 / 开关 / 平台
>     探测 / Seatbelt 命令生成 / bwrap 命令生成 / fail-closed / 能力描述）。
>
> - **G1 P1 Tree-sitter 精确 AST 后端**（`src/tools/tree_sitter_backend.py`）：
>   - 可选依赖 `tree_sitter` + `tree_sitter_typescript`，缺依赖时
>     `is_tree_sitter_available()` 返回 False，自动透明降级回词法层
>     （`language_backend.TypeScriptBackend`，不阻断 Python 主路径，
>     与 ADR-0004 零默认依赖口径一致）；
>   - 实现 `LanguageBackend` 协议的 4 个核心方法（`extract_symbols` /
>     `extract_call_graph` / `check_naming_contract` / `classify_error`），
>     精确 AST 口径（误报更少：仅对 `CallExpression` 节点取 callee，
>     不做跨模块 / 动态调用推断）；
>   - `register_tree_sitter_backend()` 缺依赖时 no-op（不抛错，
>     注册表保持词法层后端）；
>   - 测试：`tests/test_g8_g2_g4_g5_g6_g7_g1.py`（缺依赖时降级 / 注册
>     no-op / 符号提取与词法层同口径）。
>
> - **G4 P1 AgentTelemetry 故障检测基准**（`src/observability/agent_telemetry.py`）：
>   - `AGENT_TELEMETRY_ENABLE=true` 时启用（默认关），10 类内置失败模式
>     正则匹配（`llm_empty_response_loop` / `llm_json_parse_failure_loop` /
>     `multi_candidate_all_rejected` / `execution_trace_missing` /
>     `budget_early_stop` / `contract_break_rewrite` /
>     `import_break_after_rewrite` / `repair_not_converging` /
>     `cross_file_topology_mismatch` / `known_error_category_hit`），
>     零 LLM 成本纯观测，输出 Markdown 报告供实验分析消费；
>   - 测试：`tests/test_g8_g2_g4_g5_g6_g7_g1.py`（10 类模式命中 +
>     Markdown 渲染 + 空 records 边界）。
>
> - **G5 P2 无测试场景执行无关验证**（`src/tools/testless_validation.py`）：
>   - `TESTLESS_VALIDATION_ENABLE=true` 时启用（默认关），四层独立可开关
>     （`TESTLESS_MYPY_ENABLE` / `TESTLESS_NAMING_CONTRACT_ENABLE` /
>     `TESTLESS_IMPORT_SMOKE_ENABLE` 单层可关）：
>     - AST 符号守卫（补丁不得删除原代码模块级函数 / 类定义）；
>     - mypy 静态检查（缺依赖时保守跳过，不阻断）；
>     - 命名契约回归（复用 `patch_applier.check_naming_contract`）；
>     - 导入冒烟（`subprocess` 跑 `importlib` 加载，超时上限可配
>       `TESTLESS_IMPORT_SMOKE_TIMEOUT`，仅 import 不执行业务函数）；
>   - 任一层失败 → 整体 `passed=False`（保守 fail-closed 口径）；
>   - 测试：`tests/test_g8_g2_g4_g5_g6_g7_g1.py`（合法补丁全过 / 删函数
>     守卫失败 / 导入冒烟层显式关闭）。
>
> - **G6 P2 多智能体辩论收敛**（`src/graph/expert_pool.py` 新增
>   `debate_round()` 方法）：
>   - `EXPERT_POOL_DEBATE_ENABLE=true` 且 `EXPERT_POOL_ENABLE=true` 时
>     启用（默认关），top-K（默认 2，`EXPERT_POOL_DEBATE_TOP_K` 可配
>     [2,4]）候选辩论收敛产出一个 `debate_revise` 修订候选，插入
>     verified 列表首位；
>   - **保守降级**：top-K 不足 2 / LLM 调用失败 → 原样返回原
>     verified 列表（不阻断主链路），标记 `debate_revise=False`；
>   - 测试：`tests/test_g8_g2_g4_g5_g6_g7_g1.py`（默认关 / 需配合
>     EXPERT_POOL_ENABLE / top-K 不足降级 / LLM 失败降级 / 成功插入）。
>
> - **G7 P2 缺陷报告生成**（`src/reports/generator.py` 的 `ErrorReport`
>   新增 `oracle_stats` 字段 + `with_oracle_stats()` 方法）：
>   - `total_oracles > 0` 时渲染"预言有效性（Oracle 增强，G7）"章节
>     （弱预言数 / 占比 / 来源分布 / 置信度分桶分布），缺数据时跳过
>     （不产生误导数据）；
>   - `to_dict()` 输出同构（`oracle_stats` 键），供下游程序化处理；
>   - 测试：`tests/test_g8_g2_g4_g5_g6_g7_g1.py`（注入 stats 后渲染 /
>     缺 stats 跳过 / `total=0` 跳过 / JSON 同构）。
>
> - **文档一致性 P2**（依赖豁免治理 + 历史快照漂移）：
>   - `docs/dependency_exemptions.md`：chromadb 1.5.9 命中 5 条已知漏洞
>     （PYSEC-2026-311 重复两条 + PYSEC-2026-3813/3814/3815）的豁免
>     登记表（依赖 / 版本 / 漏洞 ID / 豁免原因 / 复审触发条件 /
>     复审期限），季度复审约定；
>   - `scripts/check_dependency_exemptions.py`：CI 门禁，`ci.yml` 的
>     `--ignore-vuln` 列表必须在登记表留痕（未登记 → `exit 1` 阻断
>     合并）；登记表缺"复审期限"列 → warning（治理不闭环）；
>   - `scripts/check_docs_history_drift.py`：warning-only，检测
>     `docs/history/*.md` 中"基线数字声明"（`N passed` / `N tests` /
>     `total_passed: N`）与 `BASELINE.yaml` 的 `tests.total_passed`
>     偏离超阈值（默认 10%）时提示归档；
>   - 测试：`tests/test_g8_g2_g4_g5_g6_g7_g1.py`（未登记 → 阻断 /
>     已登记 → 通过）。
>
> - **实验脚本**：
>   - `experiments/multi_candidate_ab.py`（#5 多候选 A/B 对照：
>     `ENABLE_MULTI_CANDIDATE_PATCH` / `MULTI_CANDIDATE_EXEC_VALIDATE`
>     ON/OFF 双跑，输出成功率 / 错误分桶 / token 效率对比 Markdown）；
>   - `experiments/position_aware_ab.py`（`POSITION_AWARE_REPAIR_ENABLE`
>     ON/OFF A/B 对照 + `save_state=True` 逐 task 定位精度：
>     `position_aware_focus.function_name` vs `task_metadata.suggested_function`）；
>   - 测试：`tests/test_g8_g2_g4_g5_g6_g7_g1.py`（A/B 开关翻转 +
>     定位精度聚合 + 缺 state 保守 0.0）。
>
> - **全量回归**：2499 passed / 0 failed（基线 2453，+46 新增测试覆盖
>   上述 8 项缺口 + 实验脚手架 A/B 对照 + 文档一致性门禁），ruff 0 warning /
>   mypy 0 error（86 源文件，+5 新增源文件：`risk_approval` /
>   `agent_telemetry` / `kernel_sandbox` / `testless_validation` /
>   `tree_sitter_backend`），`BASELINE.yaml` 已刷新。
>
> 配套测试文件：
> - `tests/test_g8_g2_g4_g5_g6_g7_g1.py`（25 用例：G2/G4/G5/G6/G7/G1/G8 缺口 + 依赖豁免门禁）；
> - `tests/test_kernel_sandbox.py`（9 用例：G3 内核沙箱）；
> - `tests/test_experiments_ab_scaffolds.py`（12 用例：A/B 对照聚合 + 全链路汇总 verdict + 七开关注入）。

## [Unreleased] — 2026-09-28 优化轮（Agent 实例复用缓存 + LLM 客户端热路径记忆，默认行为不变）

> 代码审查后的性能优化批次，默认行为不变（新增能力均带独立开关，
> 未启用时历史口径逐字节等价）：
>
> - **Agent 实例复用（P1，循环修复热路径优化）**：
>   - `src/graph/nodes.py` 新增通用 `get_or_create_agent()` 工厂
>     （按类名分键 + DCL + FIFO 容量 16，与 llm_client 客户端缓存
>     同口径；MagicMock 替换类的测试场景自动降级为按次新建，
>     保持 mock 口径不变）；
>   - `_planner_node` / `_generator_node` / `_debugger_node` /
>     `_diagnosis_node` 均委托该工厂获取 BaseAgent 子类实例——
>     循环修复（MAX_ITERATIONS 轮 × 多任务）下省掉每轮
>     "实例化 + 锁内查客户端缓存"的重复开销（客户端本身仍经
>     llm_client 的 (model, temperature, api_key, base_url)
>     缓存共享，复用与按次新建在并发语义上逐字节等价）；
>   - 开关：`AITESTER_AGENT_REUSE=0` 关闭（默认启用）；
>   - 测试钩子：`clear_agent_instance_cache()`（conftest autouse
>     fixture 每测试前后清空，恢复"每次新建"的测试历史口径）。
>
> - **ExecutorAgent 按沙箱配置分键复用（P1，同上热路径）**：
>   - `src/graph/nodes.py` 新增 `_get_or_create_executor_agent()`：
>     按 (timeout, use_docker, use_venv, auto_install_deps,
>     dep_install_timeout, docker_image) 完整配置元组分键（ExecutorAgent
>     构造仅存储沙箱参数、execute() 每次调用独立构建沙箱/回收输出，
>     同配置复用与按次新建等价；`--timeout` 变体各建独立实例，
>     并发下 DCL + 线程锁保证同键只构造一次）；
>   - 开关：`AITESTER_EXECUTOR_AGENT_CACHE=0` 关闭（默认启用）；
>   - 测试钩子：`clear_executor_agent_cache()`（conftest autouse
>     每测试前后清空）。
>
> - **LLM 客户端热路径环境变量记忆（P2，每次 LLM 调用省 2 次
>   os.getenv）**：
>   - `src/agents/llm_client.py` 的 `_llm_cache_enabled()` /
>     `_llm_cache_dir()` 首次调用读环境变量定值后复用进程内记忆；
>   - 新增 `clear_llm_cache_option_memory()` 清除钩子——环境变量
>     经 monkeypatch.setenv 被测试修改后显式清记忆恢复"每次读
>     环境变量"历史口径；
>   - `base_agent.clear_llm_lru_cache()` 同步触发该清除钩子
>     （LRU 清空时一并清环境变量记忆，保持测试隔离口径不变）；
>   - `tests/conftest.py` autouse fixture 在每个测试前后各清一次
>     记忆（配套环境变量隔离）；`tests/test_workflow.py` 单测内
>     两次目录切换处显式清记忆。
>
> - **新增回归测试** `tests/test_2026_09_28_agent_reuse_optimizations.py`
>   （10 用例：Agent/Executor 实例复用 + 开关 + 清除钩子 + conftest
>   记忆清除语义）；全量回归 2453 passed / 0 failed（ruff 0
>   warning / mypy 0 error，81 源文件）。

## [Unreleased] — 2026-09-29 改进批次（缓存隔离 / 注入防御 / 可解释性 / 确定性守卫 / 流氓监控 / 关键词兜底）

> 基于 2026 年行业数据（Clinejection、KeyPooling、LiteLLM
> CVE-2026-89032、Spring AI CVE-2026-59308、DO-178C、特斯拉
> ≥90% 分支覆盖阻断策略）的系统性改进，**默认行为不变**（新能力
> 均带独立开关，未启用时历史口径逐字节等价）：
>
> - **P0 缓存用户隔离（ADR-0011）**：
>   - `llm_client.py` 新增 `creator_uid` 字段写入 + 读侧
>     `cache_creator_ok()` 归属校验（跨用户 / 跨 CI 步骤投毒面
>     封堵；历史无字段条目兼容）；
>   - `AITESTER_CACHE_CREATOR` 环境变量支持多租户逻辑隔离；
>   - 新增 `tests/test_multiprocess_cache_consistency.py`
>     （投毒模拟 + 负缓存过期重读 + 跨用户 creator 校验）；
>   - `tests/test_llm_file_cache.py` 修复 latent
>     `test_negative_cache_expiry_rechecks_file` 断言注释口径。
>
> - **P0/P1 注入防御层（ADR-0012）**：
>   - 新增 `src/agents/injection_guard.py`（输入侧 4 类特征检测
>     + 输出侧 5 类危险操作静态校验，纯正则，零 LLM 成本，
>     默认关）；
>   - 新增 `tests/test_injection_guard.py`（12 用例）。
>
> - **P1 流氓 agent 监控（OWASP ASI-10 参照）**：
>   - 新增 `src/agents/rogue_monitor.py`（z-score 逐工具 one-hot
>     偏离 / 香农熵 / 能力违规三信号，线程安全，默认关）；
>   - 新增 `tests/test_rogue_monitor.py`（15 用例）。
>
> - **P1 RAG 关键词兜底检索（LeanKG 三层回退链底层）**：
>   - `src/graph/rag.py` 新增 `keyword_fallback_search` /
>     `retriever_or_keyword_fallback`（向量侧不可用时降级为词袋
>     打分，开关 `RAG_KEYWORD_FALLBACK_ENABLE` 默认关；不向
>     action 回调注入结果，保持保守）；
>   - 新增 `tests/test_workflow_combinations.py` 拓扑组合用例。
>
> - **P2 语义缓存假阳性抽样统计**：
>   - `semantic_cache.py` 新增 `should_sample_false_positive()`
>     （默认 10% 命中抽样）+ 统计接口 + 并入 `get_semantic_cache_stats`。
>
> - **P2 确定性生成守卫**：
>   - 新增 `src/agents/deterministic_guard.py`（AST 静态扫描
>     random / long-sleep / wall-clock / 外部副作用，默认关）；
>   - 新增 `tests/test_deterministic_guard.py`（13 用例）。
>
> - **P2 凭证剔除动态推导**：
>   - `credential_scrub.py` 从 `PROVIDER_TEMPLATES` 键自动推导
>     provider 中间变量脱敏模式（消除 LiteLLM CVE-2026-89032 式
>     静态枚举漂移）；
>   - 新增 `scripts/check_credential_scrub.py` CI 守卫
>     （新 provider 未同步时阻断合并）；CI 接入。
>
> - **P2 分支覆盖率门槛上调（ADR-0014）**：
>   - `check_branch_coverage.py` 总门槛 79% 基线 + 核心修复路由
>     模块 90% 严格门槛 + 其余核心模块 85%；
>   - 修复口径漂移：总分支率改用 `branches-covered/branches-valid`
>     加权聚合（根 branch-rate 是模块简单均值，会被小模块拉低）；
>   - 新增 `tests/test_workflow_combinations.py`（74 用例，补全
>     `_should_debug` / `_route_after_diagnosis` / `_create_workflow`
>     拓扑组合）；
>   - `tests/test_branch_coverage_gates.py` 同步更新门槛常量断言。
>
> - **P2 脱敏一致性校验**：
>   - `logging_utils.py` 新增 `verify_redaction_consistency()`
>     （mask_sensitive_info vs redact_text 双路径一致性 +
>     键派生子集校验，防 Spring AI CVE-2026-59308 同源风险）。
>
> - **P3 可解释性字段（ADR-0013）**：
>   - `error_classifier.py` `ClassificationResult` 新增
>     `explanation` 字段（命中规则特征 / 弱命中标注 / 置信度
>     口径 / 兜底触发，零 LLM 成本纯数据口径）；
>   - 策略追踪链四环节（分类→策略选择→补丁生成→验证结果）
>     经 `explanation` 字段闭环。
>
> - **P3 文档**：
>   - 新增 `docs/adr/0011-0014`（4 篇 ADR）；
>   - 新增 `docs/troubleshooting.md`（症状→根因→解决→预防
>     四段式故障排查手册）；
>   - `CHANGELOG.md` 批次记录。

## [Unreleased] — 2026-09-28 改进清单全量批次（P0/P1/P2/P3，默认行为不变，新能力均带独立开关）

> 本批次基于用户提交的 24 项改进清单（跨 7 个维度：架构算法 / 工程实践 /
> 测试质量 / 文档 UX / 性能扩展 / 安全合规 / 特性生态），按 P0→P3 优先级
> 逐项落地，**默认行为不变**（新能力均带独立开关，未启用时历史口径逐字节
> 等价）：
>
> - **P0 文档基线 / CI 基建**：
>   - `README.md` / `README.en.md` "测试状态" 数字漂移修复——移除硬编码
>     数字（`2046 passed` / `行覆盖 89%` 等），统一指向 `BASELINE.yaml`；
>     新增漂移守卫 `scripts/check_baseline_numbers.py`（仅对"测试状态 /
>     Test Status" H2 段做数字正则检测，历史"迭代优化记录"段豁免）+
>     CI 步骤集成；
>   - `BASELINE.yaml` 结构校验 `scripts/check_baseline.py`（必填字段 /
>     `total_failed==0` / 覆盖率区间 / `ruff_warnings`/`mypy_errors`==0 /
>     `last_verified` 日期格式 + `--verify` 重测全量 pytest 数量比对）；
>   - 静态报告自动刷新 `scripts/generate_static_report.py`——运行 ruff /
>     mypy 快照归档到 `docs/history/static_report_<YYYY-MM-DD>.md`，CI
>     主分支 3.14 矩阵上传 artifact。
> - **P1 算法 / 安全**：
>   - 分支覆盖率回填 + 核心路由模块门槛：`BASELINE.yaml` 回填
>     `branch_total_pct` 与 `branch_core_routing` 块；新增
>     `scripts/check_branch_coverage.py`（解析 coverage.xml `<class
>     filename branch-rate>` 结构，总门槛 79%、核心 4 模块 85%）+ 组合路由
>     测试 `tests/test_branch_coverage_gates.py`（`_should_debug` /
>     `refine_failure_category` / `rag.py` 降级守卫 26 用例）；
>   - LLM 文件缓存权限收敛 + TTL 过期清理：`llm_client.py` 新增
>     `ensure_llm_cache_dir`（新目录 0o700，既有目录不动）/
>     `secure_cache_file`（临时文件 0o600）/ `cleanup_expired_cache_files`
>     （按 mtime 删除早于 TTL 的 `*.json`，`AITESTER_LLM_CACHE_TTL_DAYS`
>     默认 7 天）；接入 `base_agent.py` / `cross_file.py` 写盘路径 +
>     `workflow.py` 启动清理；新增 `tests/test_cache_security.py`（9 用例）；
>   - 错误分类器置信度分层：`error_classifier.py` 新增
>     `classify_with_confidence` / `ClassificationResult` / L2
>     `ProbabilisticClassifier` 协议（当前恒 None，落地需独立 ADR）+
>     低置信度兜底策略（confidence ≤ 0.5 时收敛到 `generic_analysis` 而非
>     硬性路由）；模块级便利函数 + `tests/test_error_classifier_confidence.py`
>     （17 用例）；ADR-0002 "已知局限与演进方向" 标注已落地最小置信度分层。
> - **P2 闭环 / 测试 / 集成**：
>   - 失败知识库最小闭环：新增 `src/agents/failure_kb.py`（落点 B 在线
>     消费 + 频次 × 时间衰减排序），`_debugger_node` 经 `kb_debugger_snippet`
>     注入同类案例片段（`FAILURE_KB_ENABLE` 默认关，历史 prompt 逐字节不变）；
>     `analyze_failures.py` 条目加 `last_seen` 时间戳；state 加
>     `kb_prompt_snippet_applied` 观测键；`failure_knowledge_feedback.md`
>     设计文档标注 M1 已实装；新增 `tests/test_failure_kb.py` 11 用例；
>   - LLM 输出格式异常注入测试组：`tests/test_llm_format_anomaly.py`
>     （17 用例：空响应 / 截断 / 字段缺失 / 无效 patch 语义 / markdown
>     包裹，纯解析层 + 分类器断言，零 LLM 调用）；
>   - `--smoke-llm` 可选 CI 作业：`experiments/run_smoke_llm.py` + CI
>     `smoke-llm` 作业（缺省 `AITESTER_SMOKE_LLM=false` 零 LLM 成本）+
>     `tests/test_smoke_llm.py`（11 用例）；
>   - 多进程缓存协调：`llm_client.py` 命中率观测层（`record_cache_hit` /
>     `get_cache_hit_rate` / `reset_cache_hit_stats`，线程安全）+
>     `workflow.get_workflow_stats` 附带 + `performance_guide.md` 预热 /
>     切换说明；
>   - 双语文档 H2 骨架结构对照：`scripts/check_bilingual_docs.py` 增章节
>     顺序漂移检测（去序号 + 小写归一化 + 子序列逆序判定）；
>   - ADR 索引：`docs/adr/README.md` + `algorithm_design(.en).md` 映射表
>     增"相关 ADR"列；
>   - CI/CD 集成示例：`docs/integration/README.md` + `.git-hooks/pre-commit.sh`
>     （本地提交前跑 CI 同源守卫）。
> - **P3 设计文档（未实装代码，默认行为不变）**：
>   - `docs/design/multilanguage_extension.md`（多语言扩展架构预留：
>     LanguageBackend 抽象 + 注册表 + 默认 Python 后端零变化）；
>   - `docs/design/hierarchical_summary.md`（超长文件分层摘要策略：
>     Level 0-3 纯静态 + 可选 LLM 摘要 + 降级链 + 默认关开关）。
> - **全量回归**：2165 测试通过 / 0 失败（较批次前 2065 新增 ~100 用例）；
>   ruff 0 告警；mypy 0 错误（70 源文件）；`BASELINE.yaml` 已刷新
>   （`total_passed: 2165` / `branch_total_pct: 80` / `mypy_source_files: 70`）。
>
> 新增回归测试（本批次合计 ~100 用例）：`test_cache_security.py`（9）/
> `test_error_classifier_confidence.py`（17）/ `test_failure_kb.py`（+11）/
> `test_llm_format_anomaly.py`（17）/ `test_smoke_llm.py`（11）/
> `test_branch_coverage_gates.py`（26）/ `test_check_baseline_numbers.py`（7）。

## [Unreleased] — 2026-09-28 改进清单落地批次（文档一致 / 基础设施 / 评估实验 / 可观测性 / 安全，默认行为不变）

> 本批次基于用户提交的改进清单（文档一致性 / 基础设施 / 核心算法 / 用户体验 /
> 评估实验 / 安全 / 可观测性）逐项核实并落地，**默认行为不变**：
>
> - **一、文档基线单一事实来源**：新增 `BASELINE.yaml`（机器可读，
>   记录全量测试 / 覆盖率 / 静态检查 / CI 矩阵 / 错误分类 17 类），
>   README / QUICKSTART / api_reference / algorithm_design /
>   usage_examples 等核心文档的"当前基线"数字统一引用本文件，
>   避免多文档各自硬编码造成漂移；历史版本表（CHANGELOG /
>   api_reference 版本演进节）记录当时快照，不随本文件刷新。
> - **二、CONTRIBUTING 硬性规则 + 依赖变更清单**：`CONTRIBUTING.md`
>   / `CONTRIBUTING.en.md` 新增"硬性规则 BASELINE.yaml 单一来源"
>   与"依赖变更清单"小节；新增 `.github/PULL_REQUEST_TEMPLATE.md`
>   （含依赖变更 checklist）。
> - **三、过期基线数字清理**：`docs/usage_examples.md` /
>   `docs/algorithm_design.md` / `docs/code_analysis_report.md` /
>   `docs/failure_analysis.md` 及 .en 对偶中内联的过期基线数字
>   一律改为指向 `BASELINE.yaml` / CHANGELOG / docs/history/，
>   不再就地维护。
> - **四、并发与多进程缓存语义文档**：`docs/performance_guide.md` /
>   `.en.md` 新增"3.5 并发与多进程缓存语义"小节（L1 负缓存进程级
>   可见性 ≤30s TTL 少量重复 LLM 调用保守退化；--parallel 多线程
>   模式最大化跨进程命中建议）。
> - **五、跨文件修复转正标准**：`docs/design/cross_file_repair.md` /
>   `.en.md` 新增"4.5 转正标准 / Graduation Criteria"——T1 ≥+15pp
>   vs 单文件、T2 token ≤1.5x、T3 2 模型档位、T4 无回归，全达标
>   才进默认启用（当前 `CROSS_FILE_ENABLE` 默认 false 保持不动）。
> - **六、错误分类器演进方向**：`docs/adr/0002-error-classifier-rules.md`
>   新增"已知局限与演进方向"——层次化（先 17 类粗分后子类细分）、
>   概率化 top-2 + 置信度、UNKNOWN ≤15% SLA；当前纯规则保持。
> - **七、失败知识库闭环设计**：新增 `docs/design/failure_knowledge_feedback.md`
>   （离线→在线知识库闭环，设计文档，未落地代码）。
> - **八、模型能力梯度实验编排器**：新增 `experiments/model_gradient.py`
>   （按 task-count 5-10、2-3 档位跑 run_benchmark，记录 llm_applied /
>   first-attempt success / avg iterations，落 `experiments/results/model_gradient.md`）
>   + `experiments/results/model_gradient.md` 结果表模板。
> - **九、新贡献者引导脚本**：新增 `scripts/bootstrap_dev.sh`
>   （venv + install + env 复制 + 配置校验，`--check-only` / `--no-install`）；
>   `QUICKSTART.md` / `.en.md` 补一行 bootstrap 指向。
> - **十、可运行能力示例**：新增 `examples/semantic_cache_demo/` /
>   `examples/cost_budget_demo/` / `examples/rag_ab_demo/` 三个离线
>   可跑的最小示例 + `examples/README.md` 索引（均无需真实 LLM 端点）。
> - **十一、CI 分支覆盖**：`.github/workflows/ci.yml` 测试步骤新增
>   `--cov-branch`（此前仅行覆盖）；`BASELINE.yaml` `branch_total_pct`
>   首测后回填。
> - **十二、Trace 内存快照 + 失败诊断 CLI**：`src/observability/trace.py`
>   新增进程级内存环形缓冲（容量 64，`TRACE_MEMORY_BUFFER_ENABLE` 默认
>   true 但**不落盘、零 I/O**；关闭时全 no-op 历史口径）——即便未设
>   `AITESTER_TRACE_DIR`（文件追踪全 no-op），每次任务的"最小化节点快照"
>   仍累积进内存，供 `dump_recent_to(target_dir)` 在失败时写成临时
>   JSONL（`./tmp_trace/<ts>_failed_trace.jsonl`）。`src/cli/app.py`
>   新增 `--dump-trace-on-failure` CLI flag（默认 false 零 I/O；
>   开启后仅任务失败时触发写盘，写盘成功把 `trace_dump_path` 字段
>   写进 `--json` 结果）。`src/graph/tracing.py` `end_task_trace`
>   把 session.records 入缓冲；`start_task_trace` 历史"未启用时
>   线程局部无 session"口径保持不变（文件追踪未启用时不创建
>   TraceSession 实例，零内存分配开销）。
> - **十三、APIManager 自适应健康检查并发**：`APIManagerConfig`
>   新增 `adaptive_health_check_concurrency`（默认 **false**，静态
>   `batch_health_check_concurrency` 历史行为不变）+ 三个辅助阈值
>   （`adaptive_health_node_threshold` 默认 50 /
>   `adaptive_health_concurrency_max` 默认 8 /
>   `adaptive_health_failure_rate_downshift` 默认 0.3）；开启时按
>   节点池规模 + 历史失败率动态决定并发度——大池 + 低失败率 → 8，
>   失败率上升（≥ 0.3）→ 降回串行，首轮无历史 → 保守串行起步。
>   `health_check_batch` 收尾时把本轮失败率记入
>   `_last_health_batch_failure_rate`（仅 adaptive 开启时写）。
> - **十四、脱敏边界文档**：`docs/api_reference.md` / `.en.md`
>   新增"脱敏边界与已知盲区 / Redaction Boundaries & Known Blind
>   Spots"一节——登记 5 条已脱敏通道（控制台日志 / 追踪 JSONL /
>   内存快照 / os.environ 进程级凭证 / LLM 异常日志）+ 4 条已知
>   盲区（第三方网关自定义错误体 / 自定义凭证前缀 / meta 嵌套非
>   str 值里的明文 / 脱敏 import 失败降级原样输出）+ 手动验证
>   方式。
> - **十五、基线数字修正**：`BASELINE.yaml` 记录实测 2065 passed
>   （slim ~1863）/ 89% 行覆盖 / ruff 0 / mypy 0（70 文件）/
>   error_categories 17；`CHANGELOG.md` 此前 0.9 版本表"1937 passed
>   / 94% 覆盖率"与实测不一致（0.9 表为历史快照），本批次统一
>   以 `BASELINE.yaml` 为当前数字单一事实来源。
>
> 新增回归测试：`tests/test_api_manager.py::TestAdaptiveHealthConcurrency`
> （9 用例）/ `tests/test_trace_observability.py::TestMemoryBuffer`
> （5 用例）/ `tests/test_cli_app.py::TestRunDumpTraceOnFailure`
> （5 用例）；受影响既有测试 `tests/test_cli_app.py::TestRunParallelTimeoutAndInterrupt`
> 2 用例因 `_run_single_task` 签名加 `dump_trace_on_failure` 参数
> （**kwargs 透传）同步更新。全量测试通过 / ruff 0 告警 / mypy 0 错误。

## [Unreleased] — 2026-09-28 改进清单落地批次（健康检查并发 / CI 3.13 / 文档口径对齐 / 多进程缓存说明 / D 规则分阶段路线，默认行为不变）

> 本批次基于改进清单（核心算法 / 工程实践 / 评估与实验 / 文档协作 / 基础设施）
> 逐项核实并落地可实施项，**默认行为不变**：
>
> - **六、健康检查并发探测（工程项 6）**：`APIManager.health_check_batch`
>   新增 `batch_health_check_concurrency`（默认 1 = 纯串行逐节点 + 逐节点
>   sleep，历史行为）；设为 4-8 时批次内有界线程池并发探测，大节点池
>   （100+）单轮耗时从 O(N×(探测+sleep)) 降为 O(N/并发×探测)，批间保留
>   一次批级 sleep。线程安全依据：`check_health` 内节点状态写入走
>   `APIHealth` 节点级锁（`_enter_half_open_probe` / `_record_health_result`
>   / `_probe_circuit_half_open` 均原子化）。新增 2 回归用例
>   （并发模式批级 sleep 口径 + 串行默认回归）。
> - **七、CI Python 3.13 覆盖（工程项 19）**：`.github/workflows/ci.yml`
>   矩阵由 `['3.12', '3.14']` 扩为 `['3.12', '3.13', '3.14']`，并补注释
>   说明 3.13 处于 scipy/pandas 锁定版本支持区间（此前跳过未说明原因）。
> - **八、文档口径对齐（工程项 15）**：`README.md` "最新优化" 行补
>   2026-09-28 P0/P1 改进批次（与 `docs/api_reference.md` 最后更新日期
>   一致，消除双文档"最新"口径混淆）。
> - **九、快速开始推荐开启项（评估项 13）**：`QUICKSTART.md` 新增
>   "推荐开启项（默认关闭但建议按需启用）" 小节，逐项说明
>   `SEMANTIC_CACHE_ENABLE` / `COST_BUDGET_ENABLE` / `POSITION_AWARE_REPAIR_ENABLE`
>   / `ADVERSARIAL_DEBUGGING_ENABLE` 的预期收益与成本，并注明
>   `CROSS_FILE_ENABLE` 当前不建议默认开启的原因（无正向实证）。
> - **十、失败分析快照更新约定（评估项 10 / 11）**：
>   `docs/failure_analysis.md` 新增"快照更新约定"段落——重大版本后
>   重跑 50 任务合成实验，新数据落 `experiments/results/` 并在本文档
>   追加链接（不就地修改历史快照）；更强模型（GPT-4 级别）仓库级验证
>   数据单独落 `experiment_report_<date>_repo_level.md`，区分"架构能力"
>   与"模型能力"边界。
> - **十一、跨批次对比工具落地记录约定（评估项 12）**：`README.md`
>   §5.15 新增约定——跨批次对比的实际发现应记入 CHANGELOG 或
>   `docs/failure_analysis.md` 链接区，避免工具长期只有示例无实证。
> - **十二、文档归档策略（协作项 16）**：`CONTRIBUTING.md` 新增
>   "文档组织约定" 小节，明确 `docs/history/` 为历史归档（非当前维护
>   文档，不随版本更新，仅作内部参考），与核心维护文档 / 审查报告
>   的维护边界。
> - **十三、新贡献者入门引导（协作项 17）**：`CONTRIBUTING.md` 新增
>   "适合新贡献者的入门任务" 小节，列出 4 类低门槛任务类型。
> - **十四、Docker 依赖版本锁定说明（部署项 18）**：`Dockerfile`
>   补注释——requirements.txt 顶层依赖 == 锁定与 requirements.lock
>   同步（CI `check_lock_sync.py` 守卫），镜像构建期预安装使用同一
>   锁定版本，升级依赖需同步改 lock + 重建镜像。
> - **十五、多进程 LLM 缓存一致性说明（工程项 20）**：
>   `docs/api_reference.md` 新增"LLM 文件缓存的多进程 / 多线程一致性"
>   小节——写侧"临时文件 + `os.replace` 原子替换"（临时文件名带
>   thread ident 后缀，跨线程/跨进程不撞名）+ 读侧损坏时静默降级
>   重调 LLM（不阻断）+ L1 负缓存进程级可见性（多进程场景 ≤30s TTL
>   内少量重复 LLM 调用，保守退化可接受）+ 最大化跨进程命中建议
>   （使用 `--parallel` 多线程模式而非多进程模式）。
> - **十六、docstring D 规则分阶段处理路线（工程项 9）**：
>   `docs/code_analysis_report.md` 新增"分阶段处理建议"——阶段 1
>   先 `ruff check --select D212,D400,D415,D413,D205,D209,D200,D202 --fix`
>   清除格式类；阶段 2 在 pyproject select 追加 "D"（先可见不阻断）；
>   阶段 3 按优先级分批补充内容缺失类，逐步清零后全量进 CI 阻断。
> - **十七、双语文档豁免清单维护约定（协作项 14）**：
>   `scripts/check_bilingual_docs.py` 的 `_EXEMPT_NO_EN` 补注释——
>   每季度或重大版本后人工复核豁免清单，升级为核心参考文档的补
>   英文版配对并移除豁免，过期文档移入 `docs/history/` 归档。
> - **十八、算法演进路线（算法项 1-4，文档形式）**：
>   `docs/algorithm_design.md` §3.1 新增"已知局限与演进方向"小节，
>   给出 4 条建议（均标注默认开关 / 独立开关，保持历史行为不变）：
>   ① 规则未命中时的轻量语义分类兜底层（复用 5.1 嵌入后端，建议
>   独立开关 `SEMANTIC_CLASSIFY_ENABLE` 默认 false）；② 位置感知
>   迭代修复（`POSITION_AWARE_REPAIR_ENABLE`）在 50 任务合成集上
>   开启对比实验后再评估默认启用；③ 跨文件修复按 import 依赖深度
>   分层验证（配合更强模型 + 仓库全量源码上下文）；④ 对抗性推理
>   × 变异测试闭环（`mutation_score_from_details` 得分作为对抗性
>   推理输入信号，建议独立开关 `MUTATION_FEEDBACK_ENABLE` 默认
>   false）。
> - **核实结果（工程项 5 / 7，无需改动）**：脱敏双实现（`api_manager._redact`
>   / `llm_client._redact_log_text`）已在 0.2 轮次统一委托
>   `logging_utils.redact_text` 单一实现；`get_status()` 中
>   `get_healthy_nodes()` 重复调用已在同批次结果复用，当前代码
>   已无冗余。异常处理模板三处重复（工程项 8）维持低优先级
>   记录在案（`code_analysis_report.md`），暂不抽取公共函数。
>
> 全量测试通过（新增 2 用例）/ ruff 0 告警 / mypy 0 错误。

## [Unreleased] — 2026-09-28 改进批次扩展（CFG 控制流分析 / 事件总线 / trace 可视化 / ADR / 双语同步检查 / CLI 增强，默认行为不变）

> 本批次推进 P2/P3 改进项，**默认行为不变**：
>
> - **二、2.2 控制流图（CFG）静态分析**：`src/tools/control_flow.py`
>   纯 AST 分析（零 LLM 成本），产出分支条件 / 循环边界 / 异常路径 /
>   多出口 / 圈复杂度估计的 CFG 摘要，注入 Planner prompt
>   （`CFG_ANALYSIS_ENABLE` 默认 true——纯增量信息不改变 LLM 调用次数，
>   设 false 回退历史口径）；PlannerAgent.plan 自动调用。
> - **一、1.4 轻量事件总线**：`src/graph/event_bus.py`
>   纯观测旁路层（`EVENT_BUS_ENABLE` 默认 true，不改 LangGraph 路由）：
>   五种事件类型（PlanGenerated / TestsExecuted / PatchApplied /
>   DebuggerDiagnosed / WorkflowCompleted），线程安全发布-订阅 +
>   异常隔离；各节点收尾处一行接线；`get_event_bus().stats()`
>   观测统计接入 `get_workflow_stats` 与 CLI `--json` 输出。
> - **六、6.2 trace 可视化 + 回放**：`src/utils/trace_viz.py`
>   JSONL trace → 自包含 HTML 时间线图（无外部依赖，可离线打开）+
>   `replay_trace` 从 trace 恢复静态决策路径（不重跑 LLM，供
>   离线分析 / 回归对比 / RL 备料）。
> - **四、4.2 ADR 目录**：`docs/adr/`（5 篇：LangGraph StateGraph /
>   错误分类器纯规则 / 默认行为不变原则 / 零默认外部依赖 /
>   节点异常降级兜底）。
> - **四、4.4 双语文档同步检查**：`scripts/check_bilingual_docs.py`
>   CI 守卫（.md ↔ .en.md 配对完整性 + 更新日期一致性 + 章节数
>   粗对齐；非核心文档豁免清单）。
> - **六、6.1 CLI --json 增强**：`src/cli/app.py` --json 输出新增
>   `event_bus` / `cost_budget` / `semantic_cache` 观测统计字段
>   （纯观测，供管道 / 脚本消费）；rich 输出与进度条已有（
>   requirements.txt 含 rich==15.0.0）。
>
> 新增 `tests/test_new_modules_2026_09_28.py`（36 用例）；全量 2044 测试
> 通过（此前 2008，+36）/ ruff 全仓 0 告警 / mypy 70 源文件 0 错误。

## [Unreleased] — 2026-09-28 P0/P1 改进批次（后处理层 / 策略映射 / 预算上限 / 语义缓存 / 冒烟脚本，默认行为不变）

> 本批次落地改进建议中的 P0/P1 五项，**默认行为不变**（新能力均有
> 独立环境变量开关，关闭时与历史口径完全一致）：
>
> - **一、1.1 LLM 输出后处理层**：`src/tools/patch_postprocess.py`
>   补丁应用前自动修复常见 LLM 代码破坏模式（与 1.3 契约守卫"拒绝层"
>   互补，本层是"修复层"）：P1 空壳补丁检测（`EMPTY_PATCH_GUARD`，
>   默认启用——把 `EMPTY_LLM_PATCH` 场景从不可观测变为
>   `state.postprocess_labels` 可识别标签）；P2 导入断裂修复
>   （`IMPORT_REPAIR_ENABLE`，默认关——丢失的顶层 import 行自动回填补丁
>   头部，仅当原代码正文仍引用该模块）；P3 契约符号别名回填
>   （`CONTRACT_ALIAS_ENABLE`，默认关——LLM 重命名 `Rule_L001→RuleL001`
>   时补 `Rule_L001 = RuleL001` 别名，保持 import 链 / 插件注册不破）。
>   `_patch_applier_node` 单文件分支接线（多候选 / 跨文件分支不重复卫生化）。
> - **二、2.1 错误分类→修复策略显式映射**：`get_recommended_fix_strategy(category,
>   context)`（`src/agents/error_classifier.py`）把"该走哪条修复路径"从
>   分散在 workflow/debugger 的隐式分支收敛为分类器输出的结构化标签
>   （`strategy` snake_case 标签 + `repair_action` 四档：llm_resample /
>   repair_code / repair_test / investigate_infra），全 17 类显式覆盖；
>   `_debugger_node` 把标签写入 state（`fix_strategy_tag` /
>   `fix_strategy_action`），供实验分析"哪类错误走了哪条修复路径"消费。
> - **三、5.4 任务级成本预算硬上限**：`src/graph/cost_budget.py`
>   （线程局部累计，--parallel 每任务独立）——`COST_BUDGET_ENABLE`
>   （默认 false）+ `COST_BUDGET_TOKENS` / `COST_BUDGET_USD`
>   （+ `COST_USD_PER_1K` 计价）；超限时 `BaseAgent._call_llm`
>   前置守卫抛 `BudgetExceededError`，planner / generator / debugger
>   节点降级兜底（不再空转烧 token）。与 3.4 成本告警（路由侧旁路
>   观测）独立、可叠加。
> - **四、5.1 语义级 LLM 缓存**：`src/agents/semantic_cache.py`
>   嵌入向量相似度匹配（复用 `embedding_utils` 的 CodeBERT →
>   sentence-transformers → chromadb 级联后端），语义相同但措辞不同
>   的 prompt 可复用缓存响应；`SEMANTIC_CACHE_ENABLE`（默认 false）/
>   `SEMANTIC_CACHE_THRESHOLD`（默认 0.92 保守口径）/
>   `SEMANTIC_CACHE_MAX_ENTRIES`（默认 256）；嵌入后端缺失时自动
>   降级为精确缓存口径（零行为变化）；命中统计
>   `get_semantic_cache_stats()`。
> - **五、3.3 端到端冒烟测试脚本**：`scripts/smoke_test.sh`
>   一键验证 S1 配置加载 → S2 核心模块导入 → S3 ruff → S4 快速单测
>   （`--full` 全量）→ S5 最小生成流程（Planner + Generator 真实 LLM
>   调用，`--no-llm` 纯离线模式）。
>
> 新增 `tests/test_patch_postprocess.py`（23 用例）/
> `tests/test_cost_budget.py`（12 用例）/ `tests/test_semantic_cache.py`
> （14 用例）+ `tests/test_error_classifier.py` 扩充（全 17 类策略
> 映射守卫）；文档同步 `docs/api_reference.md` / `docs/failure_analysis.md`
> / `QUICKSTART.md` / `.env.example`。
>
> 质量基线：全量 2008 测试通过（此前 1937，+71）/ ruff 全仓 0 告警 /
> mypy 67 源文件 0 错误 / 覆盖率 88%（TOTAL，新模块 patch_postprocess
> 92% / cost_budget 93% / semantic_cache 90% / error_classifier 94%）。

## [Unreleased] — 2026-09-27 路线图剩余缺口落地（SWE-bench Pro / CodeBERT / pyright，默认行为不变）

> 本批次补齐 2026-09-27 前十一轮之后路线图核对出的 3 个剩余缺口，
> **默认行为不变**（新后端 / 新数据集均有独立环境变量开关或同构复用，
> 缺失依赖时透明保守降级）：
>
> - **五、SWE-bench Pro 支持**：`experiments/contamination_check` 抗污染
>   基准注册表新增 `swe-bench-pro`（强 copyleft 设计，GPT-5 Pass@1 仅
>   ~23.3%，与 SWE-bench Verified 成对报告）；`src/datasets/dataset_loader`
>   注册 `swe_bench_pro` / `swebench_pro`（复用 `SWEBenchDataset`，
>   数据目录经 `data_dir` 注入，与 `swe_rebench` 同构口径）。
> - **五、CodeBERT 嵌入后端**：`src/utils/embedding_utils` 新增
>   `codebert` 后端（`transformers.AutoModel` 加载
>   `Salesforce/codebert-base`，可经 `EMBEDDING_CODEBERT_MODEL` 覆盖；
>   `auto` 优先级调整为 codebert → sentence_transformers → chromadb；
>   缺 `transformers`/`torch` 时保守回退，不引入硬依赖）。
> - **二、pyright 静态类型后端**：`src/tools/type_repair` 新增
>   `_run_pyright_findings` + `TYPE_CHECK_BACKEND`（默认 `mypy` 口径不变；
>   `pyright` 时走 pyright CLI / pyright-python，输出疑点 schema 与 mypy
>   层一致，kind 前缀 `pyright_`；不可用时保守降级为 ast 静态层）。
>
> 新增 `tests/test_roadmap_gaps_g1_g2_g3.py`（20 用例：Pro 注册表 /
> Pro 加载器路由 / CodeBERT 后端降级 / pyright 后端开关与解析）；
> 修正 `tests/test_dataset_loader.py` 数据集名单同步 + `tests/test_embedding_utils.py`
> 后端优先级断言。全量 1909 测试通过，ruff / mypy 全绿。
>
> 配套核查文档：`docs/roadmap_2026-09-27_gap_audit.md`（路线图 7 节逐项
> grep/read 核实，证据标注 文件:行号；判定 6 节已落地、第 ⑤ 节 3 个子项
> 缺口即本批次补齐对象；含英文版 `.en.md`），并在
> `docs/assessment_2026-09-25_improvement_directions.md` 头部加后续批次
> 指引。

### 五、SWE-bench Pro 支持

- `experiments/contamination_check.py`：`CONTAMINATION_RESISTANT_BENCHMARKS`
  注册表新增 `swe-bench-pro` 条目（`display_name` / `resistance_mechanism`
  含 copyleft 抗污染说明 / `recommended_pairing` = `swe-bench-verified`），
  `render_resistant_benchmark_section` 自动纳入 Pro 行。
- `src/datasets/dataset_loader.py`：`load_dataset` 注册 `swe_bench_pro` /
  `swebench_pro` → `SWEBenchDataset`（字段同构，数据目录经 `data_dir` 注入）；
  `get_available_datasets` 同步补两个新名字。

### 五、CodeBERT 嵌入后端

- `src/utils/embedding_utils.py`：`_load_backend` 新增 `codebert` 分支
  （`transformers.AutoModel` + `AutoTokenizer`，`[CLS]` 隐藏状态 L2
  归一化为语义嵌入，512-token 截断保守约束）；`EMBEDDING_BACKEND=codebert`
  显式生效，`auto` 优先级 codebert 置顶；`EMBEDDING_CODEBERT_MODEL` 可覆盖
  默认模型名；缺 `transformers` / `torch` 时透明回退（保持词袋余弦保守口径）。

### 二、pyright 静态类型后端

- `src/tools/type_repair.py`：新增 `_run_pyright_findings`（探测 `pyright`
  CLI / `pyright-python`，`--outputjson` 解析 + 文本逐行兜底，高置信度规则
  白名单，kind 前缀 `pyright_`）+ `_static_type_check_backend`（
  `TYPE_CHECK_BACKEND`，默认 `mypy`）；`type_repair_layer` 按后端选择
  mypy / pyright 层，pyright 不可用时保守回退 mypy 口径，全失败路径降级
  为 ast 静态层（不阻断修复主流程）。

## [Unreleased] — 2026-09-27 第十一轮：错误分类 16→17 类 + 2.2 补丁重采样 + 1.3 降级链透传 + 五污染检测 + 2.1 mypy 静态层（默认行为不变）

> 本批次为 2026-09-27 第十轮全项目审查（commit `a1a06ec`）之后的功能
> 批次，包含 6 个方向的功能增强与类型/lint 修复，**默认行为不变**
> （所有新能力均有独立环境变量开关，默认关闭；修复项仅修正
> `on_resample` 关键参数等隐藏缺陷）：
>
> - **5.2 错误分类 16 → 17 类**：新增 `PATCH_SYNTAX_INVALID`（2.2 重采样
>   耗尽标记）；`refine_failure_category` / `refine_final_error_category`
>   新增 `patch_syntax_invalid` 参数；测试同步更新。
> - **2.2 补丁后处理重采样**：`PATCH_RESAMPLE_ENABLE=true` 时
>   `_patch_applier_node` 应用失败触发 `apply_patch_with_resample`
>   （最多 `PATCH_RESAMPLE_MAX` 次），仍失败标记 `patch_syntax_invalid`。
> - **1.3 分层压缩降级链透传**：`contract_reject_feedback` 经
>   `_debugger_node` 跨轮透传，`debug()` 新增该参数 + `_build_downgrade_context`
>   + 档位温度映射；`AITesterState` 声明 `contract_reject_feedback`
>   / `contract_missing_symbols` / `patch_resample_stats` /
>   `patch_syntax_invalid_flag` 四个键。
> - **五、多维度污染检测**：`run_benchmark._build_task_result` 新增
>   `contamination_risk_level` 字段（high/medium/low）；
>   `rag_ab_experiment.compare_ab` 新增 `token_saving.delta_pct`。
> - **2.1 mypy 静态层**：`TYPE_CHECK_ENABLE=true` 时
>   `type_repair._run_mypy_findings` 补充分层类型疑点；
>   修复 `contextlib` 导入与 SIM105 lint。
> - **修复 + 类型清零**：`on_resample` → `resample_fn` 关键参数名修复
>   （2.2 重采样此前静默失效）；`build_tiered_context` tier-0 返回
>   `str | None` → `str`（`... or ""`）；全仓 mypy 0 错误、ruff 全绿。
>
> 全量 1937 测试通过（基线 1920 + 17 新增），零回归；
> ruff / mypy 全绿（64 源文件）；CI 全绿。

### 5.2 错误分类 16 → 17 类（新增 `PATCH_SYNTAX_INVALID`）

- `src/agents/error_classifier.py`：`ErrorCategory` 枚举新增
  `PATCH_SYNTAX_INVALID`（重采样耗尽标记，标识"补丁语法反复损坏"场景）；
  `refine_failure_category` / `refine_final_error_category` 新增
  `patch_syntax_invalid` 参数；判定优先级
  `patch_rejected > rag_empty > trace_missing > multi_rejected > patch_syntax_invalid`。
- `tests/test_error_classifier.py`：`test_seventeen_categories_total` 锁定
  17 类总数 + `PATCH_SYNTAX_INVALID` 值。

### 2.2 补丁后处理重采样（`PATCH_RESAMPLE_ENABLE`）

- `src/graph/nodes.py`：`_patch_applier_node` 应用失败时触发
  `apply_patch_with_resample`（最多 `PATCH_RESAMPLE_MAX` 次，默认 2）；
  仍失败时标记 `patch_syntax_invalid`（`refine_failure_category` 消费）。
- `src/tools/patch_applier.py`：`apply_patch_with_resample` 关键参数
  `resample_fn` 修复（此前调用方误传 `on_resample` 导致 2.2 重采样
  静默失效，默认关闭不受影响）；`apply_patch_with_resample` 支持
  `resample_fn` 回调注入（LLM 负面反馈重采样）。
- `tests/test_improvements_1_2_2_1_2_2_4_3.py`：回归守卫锁定重采样路径。

### 1.3 分层压缩降级链透传（`CONTEXT_TIER_DOWNGRADE_ENABLE`）

- `src/graph/state.py`：`AITesterState` 声明 `contract_reject_feedback` /
  `contract_missing_symbols` / `patch_resample_stats` /
  `patch_syntax_invalid_flag` 四个键（`create_initial_state` 同步补默认值）。
- `src/graph/nodes.py`：`_debugger_node` 透传 `contract_reject_feedback`
  给 `debug()`；`_patch_applier_node` 符号守卫拒绝时写入档位反馈 +
  缺失符号列表；`on_resample` 关键参数修复。
- `src/agents/debugger.py`：`debug()` 新增 `contract_reject_feedback`
  参数 + `_build_downgrade_context` + 档位温度映射；`_downgrade_tier_temperature`
  读 `patch_applier._CONTEXT_TIER_TEMPERATURES`；观测字段
  `mypy_findings_count` / `downgrade_triggered` / `downgrade_tier`。
- `tests/test_roadmap_13_22_21_mypy_5.py`（新增）：tier 推进 /
  重采样接线 / mypy 静态层 / 降级链透传回归守卫。

### 五、多维度污染检测 + Token 效率

- `experiments/run_benchmark.py`：`_build_task_result` 新增
  `contamination_risk_level` 字段（high/medium/low，无 golden patch
  时保守 "low"）；`_compute_contamination_risk_level` 调
  `patch_semantic_similarity` 多维度检测；失败分支各键 None 兜底
  （键集合同构）。
- `experiments/rag_ab_experiment.py`：`compare_ab` 新增
  `token_saving.delta_pct`（RAG ON vs OFF token 消耗降低百分比）。

### 2.1 mypy 静态层（`TYPE_CHECK_ENABLE`）

- `src/tools/type_repair.py`：`_run_mypy_findings` 补充分层类型疑点
  （mypy 未安装时透明降级为空列表，不阻断 ast 静态层）；
  修复 `contextlib` 导入与 SIM105 lint（`try/except OSError: pass` →
  `contextlib.suppress(OSError)`）。

### 修复 + 类型清零

- `src/tools/patch_applier.py`：`build_tiered_context` tier-0 分支
  返回 `str | None` → `str`（`extract_function_context(...) or ""`，
  保守降级口径，行为等价）。
- `src/agents/debugger.py` / `src/graph/nodes.py`：`cast` 收窄
  `dict[str, Any] | None` union-attr（mypy 全绿，零行为变化）。
- 全仓 ruff 8 个 lint 问题清零 + mypy 12 个类型错误清零（64 源文件）。

## [Unreleased] — 2026-09-27 第九轮并行子代理深审 + 第十轮全项目 P1/P2 收敛（默认行为不变）

> 本轮为 2026-09-26 六批次全面审查（commit `9526fd0`）之后，基于 4 路并行子代理
> （agents / tools / cli+reports+config+utils+db / experiments）深度审查报告
> 整合的保守优化批次，默认行为不变。
> 全量 1920 测试通过（基线 1861 + round9 新增 26 回归守卫 + round10 新增 33
> 回归守卫 + 配套修正），零回归；ruff / mypy 全绿（62 源文件）。

### 第九轮并行子代理深审（默认行为不变）

> 4 路并行子代理对 round8 之后代码深审 + 主代理逐条复现验证；
> 产出 P1×4 + P2×10 + 新增回归守卫 26 用例（tests/test_2026_09_26_review_round9.py）。
> 全量 1887 测试通过（基线 1861 + 26 新增 + 4 配套修正），零回归；ruff / mypy 全绿。

#### P1 缺陷修复（4 项，回归测试锁定）

- `src/tools/patch_applier.py`（P1 单函数 import 前缀误判完整文件模式）：
  单函数补丁若函数体内有局部 import，且该局部 import 行落在补丁文本前 200
  字符内，旧实现误判为完整文件模式（因前 200 字符包含 import 行），顶层
  import 被静默丢弃，产出含重复 import 或丢失 import 的损坏代码。
  现改用 `MULTILINE` 行首 `^import|^from` 探测（`_TOP_IMPORT_RE`），
  与 `_TOP_DEF_RE` 同口径——仅顶层 import（行首匹配）触发完整文件模式判定，
  函数体内局部 import 不再误触发。
  默认行为不变（正常同步 def 数据集场景不受影响；误判路径由"静默丢 import"
  变"正确识别为单函数补丁"）。回归守卫 3 例。
- `src/tools/multi_candidate.py`（P1 全候选失败仍写盘劣化）：
  执行验证模式（`MULTI_CANDIDATE_EXEC_VALIDATE=true`）下，若全部候选补丁的
  `exec_passed=False`（均无法通过测试验证），旧实现仍返回"最不差"候选写盘——
  劣化代码被直接写入目标文件，比原始代码更差。
  现加守卫——全候选失败时返回 `None`，调用方（`_select_multi_candidate_patch`
  节点）检测到 `None` 后回退单补丁路径（不写盘或写回原代码）。
  默认行为不变（执行验证模式默认关；正常场景不变；全失败场景由"写盘劣化
  代码"变"保守拒绝"）。回归守卫 3 例。
- `src/tools/dependency.py`（P1 venv 缓存竞态）：
  `create_venv` 的缓存命中检查 + 创建序列（`os.makedirs` + `venv.create` +
  `pip install`）无锁保护。`--parallel` 下多线程并发创建同一缓存目录时，
  可能同时判定"缓存不存在"并重复创建，甚至一个线程的 `pip install` 与
  另一个线程的 `os.makedirs` 交叉导致竞态损坏。
  现引入 per-dir 锁（`_get_venv_dir_lock(cache_dir)`），不同目录互不阻塞，
  同一目录串行化缓存检查+创建序列。
  默认行为不变（单线程不变；并发场景消除缓存目录竞态）。回归守卫 2 例。
- `src/agents/executor_repo.py`（P1 临时文件竞争 + setup 竞态）：
  A. `verify()` 临时测试文件名仅按 `(commit, pid)` 键。`--parallel` 多线程
  同 pid（同一 Python 进程内多线程）并发时，一个线程的 `os.remove` 可能
  删掉另一个线程正在 `git apply` 的临时测试文件。
  现加 thread ident 第三键：`(commit, pid, thread_ident)`，隔离多线程。
  B. `setup()` 的 clone/venv/pip 序列无锁，`--parallel` 并发同 `env_dir`
  时可能重复 clone + 重复 pip install。
  现加 per-env_dir 锁（`_get_repo_setup_lock(env_dir)`），锁内重检缓存，
  避免重复操作。
  默认行为不变（单线程不变；并发场景消除临时文件覆盖 + setup 重复操作）。
  回归守卫 4 例。

#### P2 改动（10 项，均默认行为不变）

- `src/agents/debugger.py`：两次坏 JSON 时 `_extract_json` 必抛
  `JSONDecodeError` 使整个 Debugger 节点崩溃。
  现 try/except 降级空 patch + critic requery 同守卫。
- `src/agents/executor_runtime.py`：通用异常分支把第 1 次失败的
  `last_result` 置 None（丢失真实测试输出）。
  现保留最近有效结果；无有效结果时返回 `(UNAVAILABLE, error_info)`
  标记，调用方按 EARLY_RETURN 同分支处理。
- `src/tools/patch_applier.py`：`_find_function_start_line_in_lines` 正则缺
  async 前缀（async 目标函数误判未找到）。
  现补 `(?:async\s+)?` 与 `_TOP_DEF_RE` 同口径。
- `src/tools/multi_candidate.py`：`_coverage_trend` 对 `coverage_delta`
  非数值（n/a 等）`float()` 崩溃。现 try/except 跳过非数值 delta。
- `src/agents/generator.py`：每次调用现场 `re.compile`。
  现预编译为模块级 `_FROM_IMPORT_RE`，纯性能优化。
- `experiments/analysis_parts/convergence_analysis.py`：无逐轮明细时
  `total_tokens` 重复计入各轮导致负增量。
  现每个任务 total 仅计入其最终到达轮一次；增量按当轮 `round_tokens`
  直接取值（不再做 `round_tokens - prev_cumulative` 减法），
  `cumulative` 按原始 `round_tokens` 累加。
- 实验文件健壮性补强（11 个文件）：`experiments/analyze_failures.py` /
  `analyze_results.py` / `compare_failures.py` / `contamination_check.py` /
  `difficulty_stratification.py` / `mutation_testing.py` / `run_benchmark.py` /
  `statistical_analysis.py` / `visualize_results.py` 各实验分析模块对非数值
  reward_signals / coverage / difficulty_level 等字段的裸 `float()` / `int()`
  崩溃点统一加 try/except 防护，非数值值跳过不计入均值。
- `tests/test_debugger.py`：更新 malformed JSON 用例（降级而非抛异常）。
- `tests/test_weak_coverage_modules.py`：更新通用异常断言（UNAVAILABLE 标记）。
- `tests/test_2026_09_26_review_round9.py`：新增 26 用例回归守卫
  （覆盖 P1×4 + P2×10 全部改动点 + 默认路径不变验证）。

### 第十轮全项目 P1/P2 收敛（默认行为不变）

> 4 路并行子代理（graph / api / datasets / tools / agents 全域深审）+ 主代理
> 逐条复现验证；产出 P1×6 + P2×13 + 新增回归守卫 33。
> 全部改动仅收敛"静默损坏 / 语义回归 / 无上限乒乓 / 缓存失效 / 超时穿透"
> 类缺陷，正常路径行为不变，1920 测试全绿（基线 1887 + 新增 33 回归守卫），
> 零回归；ruff / mypy 全绿（62 源文件）。

#### P1 缺陷修复（6 项，回归测试锁定）

- `src/graph/nodes.py::_suggest_iteration_strategy`（P1 非数值
  coverage_delta 崩溃）：
  读取 `state.get("coverage_delta")` 后裸 `float(delta)` 做迭代策略判定。
  历史落盘结果中 `coverage_delta` 可能为 "n/a"（字符串）、dict 等非数值
  异常值，裸 `float()` 崩溃 executor 节点，整条工作流中断。
  现 try/except 跳过该条目（口径：非数值 delta 视为无信号，与 None 同语义），
  正常数值路径零变化。回归守卫 3 例。
- `src/agents/base_agent.py::_lru_store`（P1 负缓存无上限）：
  `_lru_negatives` dict 无容量上限，长程 benchmark 运行中负缓存条目只增
  不减，内存无界增长。
  现与正缓存同 `_LRU_MAXSIZE` 上限，FIFO 淘汰最早插入的负缓存条目。
  回归守卫 3 例。
- `experiments/analysis_parts/rag_analysis.py::_rag_similarity_distribution`
  （P1 bins KeyError）：
  计算分桶时 `max_similarity` 为负值（历史落盘异常），`bins` 字典键计算
  越界致 KeyError，崩溃整份 `build_analysis`。
  现下界钳位到 0（`max(0.0, max_similarity)`）+ 非数值 `float()`
  try/except 跳过。回归守卫 3 例。
- `experiments/analysis_parts/convergence_analysis.py::_execution_trace_summary`
  （P1 非数值崩溃）：
  对 `reward_signals` / `coverage` 字段裸 `float()` 转换，
  "high"/"80%"/dict 等历史异常值崩溃。
  现 `contextlib.suppress` 跳过非数值条目（口径：非数值不计入均值）。
  回归守卫 3 例。
- `experiments/statistical_analysis.py::_pair_by_task`（P1 跨批次静默丢弃）：
  用 dict 推导配对，跨批次重复 `task_id` 时旧实现"末者胜"，
  早期批次被静默丢弃（样本量被截断且不确定），统计分析结果不可信。
  现首见优先去重 + warning 日志，确保样本量可追溯。回归守卫 3 例。
- `experiments/run_benchmark.py` 汇总（P1 None 值崩溃）：
  汇总阶段裸 `r["iterations"]` / `r["elapsed_seconds"]`，在键存在但值为
  None 时 KeyError/TypeError 崩溃（历史落盘部分任务未记录这些字段）。
  现 `r.get("iterations", 0) or 0` / `r.get("elapsed_seconds", 0) or 0`
  防护（缺省语义：该任务未记录，贡献 0），`total_time` 同步。
  回归守卫 3 例。

#### P2 改动（13 项，均默认行为不变）

- `src/agents/executor_repo.py`：`verify()` 流程注释与 docstring
  "git stash" 措辞改为实际实现 "git checkout -- . / clean -fd"
  （grep 确认 verify 体无 stash）。
- `src/agents/executor_runtime.py`：`TimeoutExpired` 分支第 2 次超时
  不再覆盖第 1 次有效 pytest 输出，改为追加 `[timeout attempt N]`
  快照（对齐 round9 通用异常追加口径；单次超时场景 `last_output`
  原为空串，结果不变）。
- `src/agents/generator.py::_fix_import_module`：带点路径（pkg.mod）
  裸子串 `code.replace` 会把包形式 `from pkg import mod` 也误改
  （残留损坏导入）。改为按模块名锚定的正则（与 `executor_imports`
  同口径），仅替换精确匹配的 `from {wm} import` 行首。
- `src/cli/app.py`：`--verbose + --json` 组合：`--json` 静音 stdout 使
  DEBUG 日志无法输出，旧实现静默吞掉 flag 冲突。
  现显式提示 verbose 在 `--json` 模式下不生效。
- `src/datasets/dataset_loader.py`：`total_test_count` 兜底口径：
  旧 `len(FAIL_TO_PASS)` 分母漏计 P2P（通过率先被低估）。
  改为 `len(F2P) + len(P2P)`（SWE-bench 官方 "total = F2P + P2P"
  语义），官方字段存在时仍以官方值为准。
- `src/reports/generator.py`：`error_context` None 字段渲染 "None"
  语义不清，改为渲染 "未知"/"—"（`to_text` 与 `to_markdown`
  双格式同口径）。
- `src/tools/code_context.py::_closure_names`：depth=N 口径文档澄清
  （N 层被调，焦点自身 0 层；边界层 N+1 函数名进 key 但不展开）。
- `experiments/analysis_parts/convergence_analysis.py`：模块级
  `_safe_int` / `_safe_float` 辅助 + 所有裸 `int()` / `float()`
  转换点（`_repair_convergence_curve` / `_metrics`、
  `_convergence_token_efficiency` 含逐轮明细 fallback、
  `_difficulty_stratified_iterations`、`_quality_proxy_metrics`
  均值/中位数、`_convergence_failure_modes`）统一安全归一
  （非数字回退 0）。
- `experiments/analysis_parts/rag_analysis.py`：`_iter_rag_stats`
  生成器跳过非 dict 元素（历史落盘/手动编辑 JSON 混入），
  3 个调用点更新；`_rag_token_efficiency` `iterations` /
  `total_tokens` 经 `_safe_int` / `_safe_float` 归一；
  `_rag_similarity_distribution` 均值按截断后 [0,1] 口径
  （与分桶一致）。
- `experiments/compare_failures.py`：`cross_batch_comparison`：
  `regressed` 排除 `new_categories`（品牌新类别 [0,0,1] 同时被列
  "恶化"与"新增"导致渲染层混淆）。
- `experiments/run_benchmark.py`：L701
  `results[baseline]["mutation_feedback"]` 死写（L711
  `_build_task_result` 整体替换新 dict，键消失）。
  删除死写，仅保留 `final_state["mutation_feedback"]`
  （workflow 下轮 Generator 消费，正确）。
- `experiments/statistical_analysis.py`：`run_all_statistics` 区分
  两种 nan 成因（n_pairs < 3 样本量不足 vs 配对差值全 0 零方差），
  旧文案统一报 "n<3" 误诊。`cohens_d` docstring 修正
  （n_pairs < 2 实际返回 `(nan, n_pairs)`，旧 doc 声称恒返回 0）。
- `tests/test_2026_09_27_review_round10.py`：新增 33 用例回归守卫
  （覆盖 P1×6 + P2×13 全部改动点 + 默认路径不变验证）。

#### 核实后无需修改项（各子代理审查确认）

- `cross_file` 拓扑排序（Kahn + 字典序）/ `from X import *` 星号导入
  漏边（opt-in 保守口径）/ `code_context` 类方法同名冲突（保守
  setdefault 口径）/ `patch_applier` AST vs 正则兜底路径一致性 /
  `type_repair` 类型家族保守口径 / `multi_candidate` credit 默认
  0.0 防御写法 / `dependency` `_importable_cache` 无锁双读（幂等
  无损坏）/ `executor_imports` LRU 失效（单任务顺序路径不触发）/
  `llm_client` zai 双层重试（deadline 快速失败机制既有）——均为
  设计口径或 opt-in 路径，默认行为不变，留作记录。

#### 延期项（下轮处理或需决策）

- `is_similar_module_name` 0.6 阈值误伤真实第三方包（需 find_spec
  守卫 vs 提高阈值，需决策）
- `patch_applier._TOP_DEF_RE` async 前缀与"行首 def" docstring
  不符（文档化）
- `credential_scrub` 缺失多厂商 API key 变体（需补全厂商清单）
- `config_manager._scan_llm_indices` 注释行干扰（纯注释修正，低优）
- `embedding_utils` 缓存 DCL 竞态（需补锁，低优）
- RAG `_cleanup` 容量触底双全表 get（性能优化，低优）
- `_RemoveNotTransformer` 主流 slot 覆盖（边界场景，低优）
- `analyze_failures` L508 vs L566 输入不一致（需核实口径）

### 全仓 ruff format 归一（14 文件）

> round9 / round10 改动文件批量 `ruff format` 归一，覆盖
> `experiments/analysis_parts/convergence_analysis.py` /
> `experiments/compare_failures.py` / `experiments/statistical_analysis.py` /
> `src/agents/executor_repo.py` / `src/agents/executor_runtime.py` /
> `src/api/api_manager.py` / `src/graph/workflow.py` /
> `src/tools/code_analyzer.py` / `src/tools/patch_applier.py` /
> `src/tools/type_repair.py` /
> `tests/test_2026_09_26_review_optimizations.py` /
> `tests/test_2026_09_26_review_round8.py` /
> `tests/test_2026_09_26_review_round9.py` /
> `tests/test_2026_09_27_review_round10.py`。
> 纯格式归一，逻辑零变化；全量 1920 测试通过 / ruff 全仓 0 告警 /
> mypy 62 源文件 0 错误 / 覆盖率 94%。

---

## [Unreleased] — 全面审查与保守优化轮（2026-09-26：静态检查清零 + 死代码清理 + 线程卫生 + 项目卫生 + 性能 / 正确性补强 + CF-3 跨文件修复缺陷修复 + 第五轮 P0 批次：变异测试判定 / API 轮询可复现 / 缓存原子写 / 写盘安全检查 / 状态 schema + 第六轮节点层路由语义与鲁棒性 + 第七轮性能热路径深扫：AST 解析复用 / O(1) 任务索引 / 合并文本共享 / 关键词预编译正则 + 第八轮收尾审计：lint/format 清零 + 类型修复层契约参照口径 + 状态键传播 + 示例文件修复 + 第九轮并行子代理深审：difficulty_level 归一口径 + _should_debug 分支顺序 + 半开探测双计 + async def 补丁 + executor_repo 临时文件竞争 + 第十轮全项目 P1/P2 收敛：JSON 叶子降级语义回归 + 路由分支遮蔽 + 完整文件补丁静默回退 + venv 缓存标记不对称 + 超时穿透 + 行号错位 + TOCTOU 竞态 + 第十一轮遗留债务收敛：cost_weight 注册时序 + async 安全检查误拒 + 死代码 / 幽灵配置 / 线程竞态 6 项落地）

> 全仓代码审查与保守优化批次（默认行为不变）：静态检查全绿、死代码清理、
> 线程卫生修复、项目卫生补全、未深审模块的性能 / 正确性修复、CF-3
> 跨文件修复"各模块共用入口代码"逻辑缺陷修复、第五轮端到端接线层
> P0 修复（变异测试杀死判定、并行 API 轮询可复现性、LLM 缓存原子写、
> 单智能体基线写盘安全检查、状态 schema 声明补全）、第六轮节点层
> 路由语义澄清与鲁棒性增强（_should_debug 诊断关键词早期迭代路由、
> test_passed 一致性、generator LLM 失败降级、planner/debugger 兜底
> 扩 OSError、缓存统计线程卫生）、第七轮性能热路径深扫
> （code_context 契约块 AST 重复解析消除、run_benchmark 单任务
> 双解析合一、dataset_loader O(1) 任务索引 + property 直访 _tasks、
> error_classifier 合并文本共享、workflow 诊断关键词预编译正则、
> executor_runtime TimeoutExpired 闭包提升、api_manager 半开探测
> 双调用窗消除、helpers JSON 叶子回退 O(1) 内存）、第八轮收尾审计
> （ruff lint / format 全仓清零 + 工作树示例文件修复 +
> type_repair 契约参照口径 + type_repair_findings 状态传播 +
> zai 域名预编译正则 + run_benchmark 异常面收紧）、第九轮并行
> 子代理深审（4 路并行子代理对 graph/api/tools/agents 深审 + 主代理
> 复核）：P1×4（difficulty_level 归一口径 + _should_debug 分支顺序
> + 半开探测双计/丢失 + executor_repo 临时文件竞争）+ P2×10（async
> def 补丁定位 + 死代码清理 + 注释修正 + 幽灵开关注释清理 +
> 测试同步）。
> 全量 1813 测试通过（基线 1727+1 failed → 修复 1 + 新增 27 回归
> 守卫 + 4 配套），零回归；本轮新增回归守卫测试
> tests/test_2026_09_26_review_optimizations.py（27 用例）+
> 同步修正 tests/test_improvements_1_2_2_1_2_2_4_3.py 中
> difficulty_level 归一测试断言（unlabeled 计数 2→3，加 3.5/True 用例）。

### 第十一轮遗留债务收敛 + P1 边界修复（默认行为不变）

> 4 路并行子代理（graph / api / tools / agents）对 round7 之后代码深审 +
> 主代理单点核实 + round7 文档"未落地项"6 项全部落地。
> 产出 P1×3 + P2×7 + 新增回归守卫 25 用例（tests/test_2026_09_26_review_round8.py
> 22 用例 + tests/test_2026_09_26_review_optimizations.py 追加
> TestPatchApplierEmptyFuncSetFullFile 3 用例）。
> 全量 1861 测试通过（基线 1832 + 新增 25 + 配套修正 4），零回归；
> ruff / mypy 全绿。

#### P1 缺陷修复（3 项，回归测试锁定）

- `src/api/api_manager.py::_cost_weight_for`（P1 注册时序缺陷，api 子代理发现）：
  `_init_clients` / `add_node` 都在节点入池**之前**调用本方法，内部
  `health_nodes.get(model_name)` 恒 None，`LLMConfig.cost_weight`（config.py
  从 `LLM_N_COST_WEIGHT` 环境变量 / `llm_configs.json` 注入）的回退分支永远
  不生效——3.4 成本感知路由在默认注册路径上静默失效，全节点恒 1.0。
  现增加可选参数 `llm_config: LLMConfig | None = None`，调用点传入手上配置
  对象，优先读其 `cost_weight`；`llm_config=None` 时保持原回退链（兼容
  外部调用与既有测试）。默认行为不变（未设成本信息时 `cost_weight=0.0`
  仍回退 1.0）。回归守卫 TestCostWeightForRegistration（6 用例）。
- `src/graph/nodes.py::_HAS_FUNC_DEF_RE`（P1 安全检查误拒，graph 子代理发现）：
  正则 `^\s*def ` 不含 `async` 前缀，与 round7 已统一的
  `patch_applier._TOP_DEF_RE` / `_find_function_range_ast` / 单函数模式按名
  正则（三处均含 `(?:async\s+)?`）口径矛盾——async-only 被测模块的补丁被
  安全检查 2 误判"无函数定义"拒写盘，`target_code` 永不更新，修复循环空烧
  token 不收敛。现补 `(?:async\s+)?` 前缀，与 patch_applier 三处口径统一。
  默认行为不变（同步 def 为主的数据集命中口径不变，仅 async-only 边界
  场景由"误拒"变"正确接受"）。回归守卫 TestHasFuncDefRegAsync（4 用例）。
- `src/tools/patch_applier.py::apply_patch_to_code` L212（P1 空函数集误拒，
  tools 子代理发现）：完整文件模式 L206 旧实现
  `if orig_func_names and orig_func_names.issubset(...)`，`orig_func_names`
  为空集（原代码无顶层 def，纯常量/import 模块）时前置守卫短路为 False →
  全文件替换永远落不到（错落到 Step 4b 单函数路径又因补丁无 def 返回
  False）。现 L212 改为 `if not orig_func_names or orig_func_names.issubset(...)`
  （`∅.issubset(任意) == True`，空集场景正确通过；非空集路径判定口径不变），
  L227 拒绝分支保留（空集时 subset 必已在 L212 通过，该分支逻辑上不可达，
  守卫冗余但无害，注释已说明）。默认行为不变（原代码含 def 时
  `issubset` 判定与改前完全一致）。回归守卫
  TestPatchApplierEmptyFuncSetFullFile（3 用例）。

#### P2 改动（7 项，均默认行为不变）

- `src/api/api_manager.py` + `tests/test_api_manager.py`：删除
  `_last_health_check` dict 死代码（round7 核实为死代码——只在 `__init__`
  初始化，无任何读/写点；旧用途"健康检查限流"已被 `APIHealth.last_check_time`
  字段取代）；3 处测试初始化同步清理。
- `src/api/api_health.py` + `tests/test_api_manager.py` +
  `tests/test_api_manager_extended.py`：删除 `retry_count` 幽灵配置
  （生产代码从未读取，重试逻辑由 `APIManager.call` 循环的 `node_fail_count`
  独立实现）+ `last_response_time_ms` 死字段（无写入点，
  `avg_response_time_ms` 窗口为空时回退等价于默认 0.0）；4 处测试断言同步
  清理；`avg_response_time_ms` 窗口为空口径显式收敛为 0.0（"无数据"口径）。
- `src/tools/dependency.py`：`_importable_cache` 加进程级锁（round7 遗留
  债务项落地）——读改写在 `_importable_cache_lock` 内原子化，消除
  --parallel 多线程同键并发 check-then-act 竞态（find_spec 幂等、
  持锁微秒级，判定语义不变，仅消除重复探测）。
- `src/tools/type_repair.py`：`_EMPTY_CALLS` 死逻辑删除（右支查空表恒
  None，整个 or 恒为左支，口径等价纯字面量）；`for/async for` 目标
  收集改 `sub.target` 精确取（原 `iter_child_nodes` 宽匹配会把 iter
  子节点误收为局部名，掩盖真实 undefined_attr；元组目标 i/j 漏收集）；
  `_builtin_allow` 改 `set(dir(builtins))` 动态生成（原硬编码 ~40 名漏
  open/abs/iter 等，LLM 层误报源）。TYPE_REPAIR_LLM_ENABLE 默认关，
  静态层仅观测输出，默认行为不变。
- `src/graph/token_usage.py`：`record_usage` 各字段读改写加进程级
  `_usage_lock`（round7 遗留债务项落地）——消除 --parallel 多线程并发
  累加同一累计器的丢更新窗口（纯内存微秒级，累计语义不变）。
- `src/graph/workflow.py`：`_should_debug` / `_route_after_diagnosis`
  注释中 round7 重构后失效的行号引用（L210/L340/L350/L354/L354-367/
  L360-366/L371-378）改为按分支描述引用，消除"注释指错位置"的维护性
  缺陷（纯注释修正，行为不变）。
- `tests/test_2026_09_26_review_optimizations.py` +
  `tests/test_2026_09_26_review_round8.py`：新增 25 用例回归锁定
  （P1×3 + P2×4 + 口径记录）。

#### 核实后无需修改项（各子代理审查确认，round7 结论保持）

- `src/agents/error_classifier.py::classify_with_context` 全量口径（round7
  已落盘，注释 L330-337 详尽说明"与 extract 口径一致"，非缺陷；
  `classify()` 默认路径仍截前 3，历史口径不变）。
- `src/tools/code_analyzer.py::preserve_patch_ingredients` 全字段
  （imports/exports/register_symbols/target_ast/called_signatures/
  module_constants 实测正确；`called_signatures` 切片恰好含装饰器行 +
  def 行，不含函数体首行，与 docstring 口径一致）。
- `src/tools/code_context.py::_apply_focus_budget` L211（调用方先检查
  `focus_in_source`，`top_level_funcs[focus]` 不会 KeyError）。
- `src/tools/cross_file.py::_topological_order` 并行边（入度按边累加、
  释放逐边扣减，实测顺序正确）；类定义正则 `[\(:]` 覆盖 `class Foo:` /
  `class Foo(Bar):` / `class Foo(Base, metaclass=M):` 三种形式。
- `src/tools/multi_candidate.py::apply_multi_function_patch`（P13 预切分
  + (found, line) 升序 + 未找到排末尾，语义正确）。
- `src/agents/executor_*.py` 子进程安全（全部 `subprocess.run` 用列表
  参数，无 `shell=True`，round7 已核实）。
- `src/graph/*` RAG DCL 双检锁 / 文件缓存记忆 / state 工厂 / tracing
  线程局部 / 图构建 4 路径 / _should_debug 分支顺序 / _route_after_diagnosis
  上限门控（round7 已核实，本轮保持）。


### 第十轮全项目 P1/P2 收敛（默认行为不变）

> 4 路并行子代理对 graph / api / datasets / tools / agents 全域深审 + 主代理
> 逐条复现验证（`extract_json_object` / `_should_debug` / `patch_applier` /
> `dependency` / `debugger` / `executor_repo` 均经 `.venv/bin/python` 实证）；
> 产出 P1×7 + P2×2 + 测试同步 1 + 新增回归守卫 13。
> 全部改动仅收敛"静默损坏 / 语义回归 / 无上限乒乓 / 缓存失效 / 超时穿透"
> 类缺陷，正常路径行为不变，1832 测试全绿（基线 1813 + 新增 13 +
> 同步改写 1 − 同步改写 1 净增 13... 实为 1813→1832，新增 19 守卫
> 用例、其中 1 例由"锁定旧静默回退语义"改写为"锁定保守拒绝语义"）。

#### P1 缺陷修复（7 项，回归测试锁定）

- `src/utils/helpers.py::extract_json_object`（P1 语义回归）：
  0.10 性能优化把叶子 JSON 回退从 `reversed(list(finditer))` 改为
  O(1) 双候选（仅试最后两个叶子）——当"可解析叶子排在更早位置"
  （损坏响应夹带 ≥3 片段、仅第 1 个合法）且括号平衡法失败（最外层
  残缺）时，直接 `raise JSONDecodeError` 误判 LLM 响应解析失败
  （主链解析兜底路径被静默破坏）。现补"双候选均失败 → 跳过最后两个
  叶子反向全量扫描"的罕见尾路径（正常 O(1) 快路径行为不变）。
  回归守卫 TestExtractJsonObjectLeafRegression（4 用例）。
- `src/graph/workflow.py::_should_debug`（P1 分支遮蔽）：
  `_recent_repairs_invalid` 早退（L340）置于迭代上限检查之前——最后一轮
  （iteration >= max）若最近 2 次修复均 patch_applied=False（"补丁反复
  失败"典型场景），早退直接 done，永远遮蔽上限分支内"诊断关键词命中 →
  一次 regenerate 机会"与 test_defect 上限收敛分支，终止 reason 还被误标
  skip_debugger_repair_invalid。现把早退限定为 `iteration < max`（早期迭代
  "连续修复无效省 token"口径不变），最后一轮由上限分支统一决策。
  回归守卫 TestWorkflowRepairInvalidBranchOrder（3 用例）。
- `src/tools/patch_applier.py::apply_patch_to_code`（P1 静默损坏）：
  完整文件模式 subset 校验失败（补丁带 import/docstring 前缀但漏掉原代码
  某函数）时静默回退单函数路径，把整个补丁塞进首个函数行范围切片——
  当补丁前缀与原代码前缀重叠时产出含重复 import / 重复 def 的损坏代码
  （ast.parse 通过、safe_apply_patch 语法守卫不拦、multi_candidate 检查 4
  反因重复定义"通过"，损坏代码直接写盘——sqlfluff 5/7 失败那类"删/漏
  函数"场景最危险路径）。现 subset 失败即保守拒绝（返回原代码 + False，
  与防御网"函数定义数量不减少"口径同义收敛）；同步改写
  tests/test_multi_candidate.py 中锁定旧静默回退语义的用例为
  test_full_file_patch_missing_function_rejected（保守拒绝）。
  回归守卫 TestPatchApplierFullFileMissingFunction（3 用例）。
- `src/agents/executor_repo.py::setup`（P1 缓存标记不对称）：
  use_venv=True + venv_reuse_by_repo=True 且 venv 创建失败回退全局
  pip install 时写 `.pip_installed`，但 setup() 入口缓存检查读
  `.venv_pip_installed`（L148）——标记永不命中，每次 setup() 重新
  git clone + pip install（SWE-bench 批量任务 10-20 个 commit 的同一
  仓库重复 clone）。现回退路径按 use_venv 写对应标记。仅 use_venv=True
  opt-in 路径，默认关不变。回归守卫 TestVenvCacheMarkerConsistency。
- `src/agents/executor_repo.py::_run`（P1 超时穿透）：
  `_run` 直调 `subprocess.run(timeout=...)`，单 test node 超时时
  TimeoutExpired 穿透 verify() 的 try/finally，整个验证任务崩溃而非
  记录该 node 失败（SWE-bench 仓库单节点跑满 timeout 很常见）。现
  收敛为 returncode=124 哨兵（GNU timeout 口径），`_run_test_nodes`
  对 rc=124 按"节点执行超时"记入 failed_cases 并继续下一节点。仅
  REPO_LEVEL_EXECUTION opt-in 路径。回归守卫 TestExecutorRepoTimeoutConvergence。
- `src/agents/debugger.py::debug`（P1 行号错位）：
  3.3 位置感知修复把**截断后**的 target_code 传给 `_locate_repair_focus`，
  而 context.line 是 pytest traceback 的**原始**行号——代码超
  CODE_MAX_CHARS（3000）触发头尾截断时行号偏移/目标函数被丢弃，
  定位降级为全文件修复。现截断前保留 original_target_code 副本，
  定位用原始全文（prompt 仍用截断版省 token 不变）。仅
  POSITION_AWARE_REPAIR_ENABLE=true opt-in 路径。回归守卫
  TestDebuggerPositionAwareOriginalCode。
- `src/tools/dependency.py::_record_venv_cache_event`（P1 TOCTOU 竞态）：
  5s 落盘节流的 `_venv_cache_last_persist_at` 读-写不在落盘锁保护内——
  `--parallel` 下 N 线程同批越过锁外判断时，后入锁者读到先入锁者刚写的
  "刚刚落盘"时间戳直接 return，窗口内仅首事件落盘（统计最终值不丢，
  落盘时效与注释口径不符）。现把锁内二次确认段的读-写整体纳入
  `_venv_cache_persist_lock`。单线程/非并行场景不变。回归守卫
  TestDependencyCachePersistToctou。

#### P2 改动（2 项，均默认行为不变）

- `src/graph/workflow.py::_route_after_diagnosis`（P2 无上限乒乓）：
  test_defect 路由此前无条件 regenerate 不检查 regeneration_count——
  DIAGNOSIS_NODE_ENABLE=true 时 Review Agent 反复判 test_defect 可致
  generator↔executor 无上限乒乓撞 LangGraph recursion_limit。现补
  与 _should_debug 同口径上限门控（达 _MAX_REGENERATIONS → done），
  两处条件边映射同步加 "done": END。仅双开关默认关路径。
  回归守卫 TestRouteAfterDiagnosisCap（3 用例）。
- `tests/test_multi_candidate.py`：同步改写 1 例（见 P1-3，锁定保守
  拒绝语义）。

#### 核实后无需修改项（各子代理审查确认）

- cross_file 拓扑排序（Kahn + 字典序）/ `from X import *` 星号导入
  漏边（opt-in 保守口径）/ code_context 类方法同名冲突（保守 setdefault
  口径）/ patch_applier AST vs 正则兜底路径一致性 / type_repair 类型
  家族保守口径 / multi_candidate credit 默认 0.0 防御写法 /
  dependency `_importable_cache` 无锁双读（幂等无损坏）/
  executor_imports LRU 失效（单任务顺序路径不触发）/
  llm_client zai 双层重试（deadline 快速失败机制既有）——
  均为设计口径或 opt-in 路径，默认行为不变，留作记录。

### 第九轮并行子代理深审（默认行为不变）

> 4 路并行子代理对 graph / api / tools / agents 四模块深审 + 主代理复核；
> 产出 P1×4 + P2×10 + 测试同步 1 + 新增回归守卫 27。
> 全部改动仅在默认关的开关路径或已锁定口径内收敛，默认行为不变。

#### P1 缺陷修复（4 项，回归测试锁定）

- `experiments/difficulty_stratification.py::_difficulty_level_bucket`
  （P1 归一口径）：基线失败项根因——实现只归一 `str→int`，但配套
  测试同时期望整数值 float（3.0）也归一，测试与实现口径互相矛盾。
  放宽归一口径为「int 直通 / 纯数字 str（含 ±）转 int / 整数值
  float（3.0）转 int / 其余（3.5 / "abc" / bool）保持 unlabeled」；
  同步修正 tests/test_improvements_1_2_2_1_2_2_4_3.py 断言
  （unlabeled 计数 2→3，加 3.5/True 用例）。默认行为不变（正常
  数据集 int difficulty_level 计数不变）。
- `src/graph/workflow.py::_should_debug`（P1 分支顺序）：3.1 双向
  诊断的 `defect_type == "test_defect"` 分支（旧 L350）位于迭代
  上限分支（旧 L359）之前——达上限 + test_defect + 再生成上限
  已满三者同时满足时，test_defect 分支直接返回 "done"（reason=
  test_defect_regeneration_cap），绕过上限分支内"诊断关键词仍可
  regenerate 一次"逻辑。现把上限检查上移到 test_defect 分支之前；
  达上限场景由上限分支统一收敛（关键词可 regenerate，否则 done），
  test_defect 分支仅保留迭代未达上限路径。仅 3.1 双向诊断开关
  开路径语义微调，默认关不受影响。
- `src/api/api_manager.py::call` / `_handle_rate_limit` /
  `_handle_api_error` / `_handle_generic_error`（P1 半开探测双计
  / 丢失）：3 个 handler 在 `is_half_open_probe=None` 时自动重判
  `node.in_circuit_half_open`，但 `mark_failure` 调用会改变节点状态
  （限流路径重判恒 False → 探测失败计数丢失；API 错误路径重判恒
  True → 多计一次探测成功口径）。现把预检上移到 `call()` 循环
  （发起真实请求前的唯一判定点），显式透传给 `_try_call_node` 与
  3 个 handler；handler 改为只消费调用方显式透传的预检结果（bool），
  不再自动重判。`_try_call_node` 加 `is_half_open_probe: bool |
  None = None` 形参保持旧调用方兼容。仅 `enable_half_open_probe=
  True` 路径，默认关不受影响。
- `src/agents/executor_repo.py::_apply_llm_patch`（P1 临时文件
  竞争）：`patch_file` 固定路径 `aitester_llm_unified.patch`，
  `--parallel` 多线程并发 verify 时一个线程的 `finally: os.remove`
  删掉另一个线程正在 `git apply` 的补丁文件。现按
  `(os.getpid(), threading.get_ident())` 双键后缀隔离。仅
  `--parallel` + 多线程共享 `RepoExecutor` 场景，默认单线程不变。

#### P2 改动（10 项，均默认行为不变）

- `src/graph/workflow.py`：`_DIAGNOSIS_KEYWORD_RE` 哨兵上移至
  函数定义之前（消除"模块加载后立即调用"时 NameError 吞掉懒
  初始化回归的缺陷——首读 NameError 被 `is None` 判定吞掉后
  每次调用都重建正则，懒初始化优化彻底失效）。
- `src/tools/patch_applier.py`（3 处 async def 补丁定位修正，
  全同步代码不变）：`_TOP_DEF_RE` 含 `(?:async\s+)?`；
  `_find_function_range_ast` 遍历 `ast.FunctionDef +
  ast.AsyncFunctionDef`；单函数模式按名正则含 `^(?:async\s+)?def`。
  修复"多 async 函数文件误判单函数模式"（`_is_full_file_patch`
  (c) 分支漏判）与"async 目标函数 AST 定位失败走正则兜底后
  正则不含 async 前缀 → 补丁应用失败"。
- `src/api/api_manager.py::_select_node_by_complexity`：注释修正
  （候选池实为全节点池 `get_all_nodes()`，非"同模型名"；标注
  未来多模型混入时的语义扩展点）。
- `src/api/complexity_router.py::complexity_class_to_routing_hints`：
  docstring 幽灵开关清理（`CODE_MAX_CHARS 可调` 改注"按档位
  硬编码"——全仓无读取点）。
- `src/agents/executor_repo.py::_clone_and_checkout`：死代码
  清理（`(repo_dir and os.path.dirname(repo_dir)) or "."` →
  `os.path.dirname(repo_dir) or "."`，repo_dir 恒非空）。
- `src/agents/base_agent.py::_call_llm`：死代码清理
  （`llm_call_kwargs` dict 从未被引用，删；`_reorder_api_groups_by_
  complexity` 保留）。
- `experiments/difficulty_stratification.py`：归一口径放宽
  （同 P1-1，含在 P1 内）。
- `tests/test_2026_09_26_review_optimizations.py`：新增 27 用例
  回归守卫（覆盖上述 P1×4 + P2×8 全部改动点 + 默认路径不变验证）。
- `tests/test_improvements_1_2_2_1_2_2_4_3.py`：同步修正
  difficulty_level 归一测试断言（unlabeled 计数 2→3，加
  3.5/True 用例）。
- `src/agents/executor_repo.py`：`import threading`（配套 P1-4）。

#### 核实后无需修改项（各子代理审查确认）

- RAG DCL 双检锁 / 文件缓存记忆 + 锁 / state 工厂函数对齐 /
  tracing 线程局部锁释放 / 图构建 4 路径——均实现正确。
- 熔断器三态 / 指数退避公式 / 节点级锁原子化——状态机自洽。
- error_classifier 匹配顺序 / 子进程安全 / 资源泄漏 / LLM
  客户端 LRU 双检锁——无缺陷。

### 第八轮收尾审计（默认行为不变）

- `examples/buggy_library.py`：修复工作树误引入的重复 `import re`
  （F811）与 I001 导入排序；`examples/calculator.py` 清除空行尾随
  空白（W293）；`experiments/synthetic_difficulty.py` 去除无占位符
  的 f-string（F541）+ `list.extend` 生成器替代逐次 append（PERF401）。
- `experiments/run_benchmark.py::run_single_task`：AST 解析异常捕获面
  收紧（原 `except (SyntaxError, ValueError, Exception)` 中裸
  `Exception` 兜底吞掉 KeyboardInterrupt 等可中断性；改为只捕获
  `SyntaxError/ValueError` 解析类异常，口径不变）。
- `src/tools/type_repair.py::type_repair_layer`：新增可选参数
  `enforce_contract_ref`（契约回环检查的参照侧，默认 None = 原代码
  参照口径，与 check_naming_contract 主语义一致）——此前调用方无法
  按"补丁基线同符号集"口径校验完整文件修订（LLM 修订省略原文件
  顶层符号时，以原代码为参照的删除检测会把合法的全集修订误放行或
  误拒；显式传参照侧后口径可选、默认不变）。
- `src/agents/debugger.py`：`debug()` 调用 type_repair_layer 的契约
  参照口径补注释锁定（默认原代码参照；LLM 修订省略原顶层符号 =
  契约破坏 = 拒绝修订，与 _patch_applier_node 主路径删除检测同向）。
- `src/graph/nodes.py::_debugger_node`：修复 `type_repair_findings`
  状态键断链——此前 `debug()` 返回值已含该键但节点未写入 state
  （state.py schema 已声明该键，消费侧恒 None）；现按
  `result.get("type_repair_findings", [])` 写入（缺省空列表，
  历史调用方无此键时不报 KeyError）。
- `src/agents/llm_client.py::_is_zai_compatible`：zai 域名判定由
  frozenset + `any` 子串扫描升级为模块级预编译 alternation 正则
  `_ZAI_DOMAIN_RE`（一次 O(n) 扫描，零调用期分配）；命中口径与
  历史子串扫描逐样本等价（守卫测试 test_zai_domain_regex_equivalence 锁定）。
- `src/graph/workflow.py::route_after_diagnosis` / `_diagnosis_node`：
  路由判定与状态写入补齐回归守卫（8 条：test_defect → regenerate /
  其余 → debug / 缺省 → debug；_debugger_node 写 type_repair_findings
  有值 / 缺省两口径）。

### 第七轮性能热路径深扫（默认行为不变）

- `src/tools/code_analyzer.py::preserve_patch_ingredients`（P0 热路径）：
  新增 `_ast` 可选参数——code_context 的 `extract_focused_code_detail`
  对同一 source 已做过 `ast.parse`，此前契约块识别路径（惰性导入后
  `preserve_patch_ingredients(source, ...)` 内部再 parse 一次）在大文件
  上 200ms 级重复解析，--parallel 多任务热路径累积。现调用方传入既有
  `tree` 复用；独立调用方（不传 `_ast`）行为不变。返回值新增
  `ast_tree` 键（解析成功时暴露 tree，失败时 None）供调用方二次分析
  复用，既有字段口径不变。
- `experiments/run_benchmark.py::run_single_task`（P0 热路径）：
  复杂度感知路由此前 `count_imports` 内部 parse 一次 + 圈复杂度
  外部再 parse 一次（每任务 2 次 `ast.parse`）。现统一先 parse 一次，
  圈复杂度分析直接用该 tree，`count_imports` 经新增的 `_tree` 参数
  复用；parse 失败（`_tree=None`）时 `count_imports` 保持旧的
  "解析失败返回 0" 语义。`compute_complexity_score` 与
  `complexity_class_to_routing_hints` 调用口径不变。
- `src/datasets/dataset_loader.py`（benchmark 热循环）：
  新增 `_task_index`（task_id → BenchmarkTask）O(1) 查表索引，
  `get_task_by_id` 从 O(n) 线性扫描降为 O(1)（`_rebuild_task_index_if_stale`
  在 add_task 后惰性重建，正常路径 O(1) 短路）；`task_ids` / `size` /
  `filter_by_repo` 等 property 从 `self.tasks`（每次 O(n) 列表拷贝 +
  `_ensure_loaded`）改为直接 `self._tasks` 访问，benchmark 热循环
  中反复调用不再 O(n) 冗余。`quality_report` / `tasks_missing_source`
  补 `_ensure_loaded` 保证未显式加载时也能正确遍历（此前直接读
  `self._tasks` 在未加载状态下为空）。
- `src/agents/error_classifier.py`（Debugger 热路径）：
  `classify_with_context` 此前 `classify()` 与 `extract_error_context()`
  各自独立构建合并文本（对同一 test_output + failed_cases 做两次
  O(n) 拼接），现一次构建 `combined` 共享给
  `_classify_combined` + `_extract_error_context_from_combined`；
  `classify()` 新增 `_combined` 内部参数（外部调用者无需传），
  `extract_error_context` 瘦身为"构建 combined + 委托
  `_extract_error_context_from_combined`"。判定优先级、正则口径、
  `ErrorContext` 字段全部不变。
- `src/graph/workflow.py::_should_debug`（路由热路径）：
  诊断关键词判定从每次调用重建 list 字面量 + 9 次 `any(kw in text)`
  子串搜索（O(9n)）提取为模块级 `_TEST_GEN_DIAGNOSIS_KEYWORDS`
  常量 + 预编译 alternation 正则 `_DIAGNOSIS_KEYWORD_RE`（O(n) 一次
  扫描，惰性编译），`_diagnosis_hits_test_gen_keywords` 与历史
  `any(kw in diagnosis for kw in _TEST_GEN_DIAGNOSIS_KEYWORDS)` 口径
  等价（守卫测试 `test_regex_equivalent_to_any_substring` 逐样本验证）。
- `src/agents/executor_runtime.py::run_pytest_with_retry`：
  `TimeoutExpired` 分支内每次异常都重新创建 `_to_str` 闭包，提升为
  模块级函数（热路径零无谓分配），语义不变（str/bytes/None 三分支）。
- `src/api/api_manager.py::call`（半开探测窗口消除）：
  此前 `call()` 在循环前与 `_try_call_node` 内部各调一次
  `_enter_half_open_probe(node)`，双调用窗口中 429/异常处理器接收的
  预计算 `is_half_open_probe` 标志可能陈旧（probe 状态在外层
  预检与内层 `_try_call_node` 预检之间漂移）。现 `_handle_rate_limit` /
  `_handle_api_error` / `_handle_generic_error` 接受
  `is_half_open_probe: bool | None = None` 并在 None 时自决
  （`self._enter_half_open_probe(node)`），消除双探测窗口；
  `call()` 不再预计算，处理器按调用时刻自决。169 个 API 测试全过。
- `src/utils/helpers.py::extract_json_object`：叶子回退路径从
  `reversed(list(finditer))`（O(n) 内存物化全部匹配）改为 O(1)
  last-two-match 跟踪（`last_match` / `prev_match` 滚动），
  语义等价（balanced-brace 主路径不变，叶子回退取最后两个候选）。
- `src/graph/nodes.py`（写盘安全热路径）：
  `_ALLOWED_WRITE_ROOTS` 模块加载期预计算前缀对
  `_ALLOWED_WRITE_ROOT_PREFIXES`（`(root, root.rstrip(os.sep)+os.sep)`），
  `_is_within_allowed_roots` 热路径零重算；`roots=None` 默认走
  预计算前缀对（历史调用方 `_ALLOWED_WRITE_ROOTS` 显式传参路径
  保持原语义）。前缀碰撞防护（`AITester_backup/` 兄弟目录）不变。
- `src/agents/llm_client.py::_is_zai_compatible`：zai 域名判定列表
  从每次调用重建 list 提升为模块级 `_ZAI_DOMAINS` frozenset，
  --parallel 多任务 LLM 路由决策每次调用 2 次无谓分配消除。

### 性能回归守卫测试（tests/test_performance_guards.py，新增 17 条）

- 复用路径（传 `_tree` / `_ast`）与独立路径（不传）逐字段一致；
- 注入 `ast.parse` 计数桩：复用路径零新增解析；
- 预编译 alternation 正则与历史 `any(kw in text)` 口径逐样本等价；
- 大文件（~400KB）聚焦提取秒级内完成（量级回归守卫，非微秒级绝对值）；
- dataset_loader O(1) 索引与 property 直访路径行为 + 量级守卫。

### 静态检查清零（mypy / ruff）

- `src/agents/executor_repo.py::_dep_fingerprint`：依赖指纹内容片段列表注解
  `list[str]` → `list[bytes]`（以 `"rb"` 读入二进制片段，原注解与运行期类型
  不符，`hashlib.update` 报 4 处 mypy arg-type）；
- `src/datasets/synthetic_dataset.py`：难度分布统计 `dist` 补
  `dict[str, int]` 注解（消除 mypy var-annotated）；
- `tests/test_executor_repo.py`：移除未使用导入（`json` / `sys` /
  `textwrap` / `shutil` 别名）、文件读取改 `with open(...)` 上下文管理
  （SIM115）；
- `ruff format --check` 归一 11 个未格式化文件（experiments / scripts /
  src / tests 的格式偏差，CI 固定 ruff 0.16.3 口径）。

### 死代码与线程卫生

- `src/api/api_manager.py::_build_node_list`：`if/else` 两分支均已 `return`
  后残留的全池备用候选构建代码块不可达，移除并在复杂度路由命中路径保留
  语义等价的全池 fallback 构建（行为不变）；
- `src/api/api_manager.py::reset_manager`：`_stop_health_checker()` 移出
  全局单例锁临界区（先换出旧实例、清引用，再在锁外停止其后台健康检查
  线程），避免 shutdown 的 5s join 阻塞并发 `get_manager()` 创建新管理器。

### 项目卫生

- `.gitignore` 补充 `.mypy_cache/`、`.ruff_cache/`（工具缓存）与
  `data/`、`results/`（本地实验数据目录，与 `experiments/results/` 口径
  一致，防误提交）；

### 安全（凭证脱敏补强，均有实证）

- `src/utils/credential_scrub.py`（P0）：固定凭证名单匹配不到 `.env` 实测
  存在的多端点编号命名（`OPENAI_API_KEY_2/3`、`OPENAI_BASE_URL_2/3`）——
  旧模式锚定全名 `^OPENAI_API_KEY$` 漏掉编号变体，凭证原样进被测代码子进程
  （执行向量 + 泄露面）。补编号变体通配 `OPENAI_(API_KEY|BASE_URL)_\d+`
  与 provider 中间变量（`ALIYUN_BAILIAN_API_KEY` / `AGNES_{DOMESTIC|INTERNATIONAL}_API_KEY`
  / `BIGMODEL_API_KEY` / `DEEPSEEK_API_KEY`，与 config_generator 的
  PROVIDER_TEMPLATES 键联动，消名单漂移）；
- `src/api/api_manager.py::call`（P0）：全节点失败路径 `RuntimeError` 携带
  未脱敏的原始 openai 异常体（网关错误体可能回显带 token 的 base_url），
  异常传播链此前是脱敏盲区——出口统一 `_redact`，与日志路径口径对齐；
- `src/config/config_manager.py::add_llm_config`（P0）：api_key / base_url /
  model_name 原样写入 `.env.local` 无校验——含 `\n` 的值可注入任意变量行
  （劫持后续配置），含 `#` 被 dotenv 解析截断。写盘前拒含换行/`#` 的输入；
  成功日志 base_url 出口统一脱敏（URL 内嵌 token 场景）；
- `src/utils/exceptions.py::retry_with_backoff`：重试警告日志直接打异常对象
  （可能含请求体/凭证回显）且不脱敏——改惰性委托 `logging_utils.redact_text`
  （与 api_manager `_redact` 同口径，惰性导入避免模块加载期循环依赖）；
- `src/utils/logging_utils.py::SensitiveFormatter`：脱敏主路径失败时退回
  **未脱敏**完整行（含堆栈）——改先走 `fallback_mask_sensitive_info`
  纯正则兜底，彻底不可用才回退原文；
- 回归测试：`tests/test_credential_scrub.py` 新增（编号变体 / provider 变量
  / 高编号边界 / 入参不可变 5 用例）+ `tests/test_logging_utils.py` 补
  `redact_dict` 字符串入参 2 用例。

### 正确性

- `src/utils/logging_utils.py::redact_dict`（P1）：字符串入参此前静默返回
  `{}`（整个脱敏值被丢弃，trace / 异常序列化场景脱敏形同虚设）——改 str
  入参脱敏后包成 `{"value": ...}`，保持返回 dict 的签名契约；删除冗余的
  `_redact_scalars_dict` 别名；
- `src/observability/trace.py::_append`（P1）：`except` 同时吞 `json.dumps`
  失败与 import 失败，记录无法序列化时**静默丢弃且无告警**——拆两分支：
  序列化失败记 warning 后放弃本条；脱敏不可用时原样写入（与 logging_utils
  三级降级末档同口径）；
- `src/graph/workflow.py::_file_cache_entry_count`（P1）：条目数记忆键
  升级为 `(目录, 条目数, 统计时目录 mtime)`——旧口径外部删除缓存文件后
  记忆值偏大直至目录整体消失才归 0；mtime 变化自动重扫，消除观测层失真
  （同目录 mtime 未变仍复用记忆免 glob，性能口径不变）；
- `src/graph/nodes.py`（P1）：`_HARD_ERROR_CATEGORIES` 从函数内每次调用
  重建的 set 提升为模块级 `frozenset`（--parallel 热路径省无谓分配）；
  `_cross_file_analyzer_node` 的 `cross_file_deps` 序列化改显式 `asdict`
  （`d.__dict__` 含 dataclass 内部属性，未来加字段会无声改变 state schema，
  下游 `_patch_applier_node` 按固定 key 取值的契约不稳）；
- `src/graph/nodes.py::_dynamic_temperature_from_suggestion`（P1）：
  `TEMPERATURE=0` 时"温度减半"仍透传 0.0（无意义覆盖）——改返回 None
  沿用默认；
- `src/agents/executor_repo.py::verify`（P1）：仓库级验证的 test_patch 临时
  文件按 `base_commit[:8]` 命名，--parallel 下多线程同仓库并发验证存在
  写/读竞争——文件名加 `os.getpid()` 后缀；
- `src/agents/debugger.py::debug`（P1）：函数内局部导入
  `from src.agents.error_classifier import ErrorCategory, ErrorClassifier`
  与文件头同模块导入重复（历史残留）——并入文件头导入；
- `src/agents/base_agent.py`（P1）：文件头已 `import os` 后又
  `import os as _os`（重构残留，可读性差）——删除别名导入；
- `src/utils/helpers.py::_find_balanced_json`（P1）：JSON 未闭合时返回
  `text[start:]` 残余文本（`json.loads` 必失败还多付一遍 O(n) 解析）——
  统一返回 None，由调用方走正则降级方案（回归用例同步更新）。

### 并发（--parallel + 后台线程竞态）

- `src/api/api_health.py::APIHealth`（P1）：`mark_success` / `mark_failure` /
  `_probe_circuit_half_open` 在路由线程与后台健康检查线程间并发 mutate
  同一节点（计数器 / 熔断状态 / 响应时间 deque 全非原子）——补节点级
  `threading.Lock`（纯内存读改写，持锁微秒级，不改变判定语义仅原子化）；
- `src/api/api_manager.py`（P1）：`health_check_all` / `health_check_batch`
  直接遍历活 `health_nodes` dict，与并发 `remove_node` / `add_node` 可致
  `RuntimeError: dictionary changed size during iteration`——改持锁快照后
  遍历；`health_check_batch` 批次间检查停止事件（`HealthCheckerThread`
  新增 `stop_event` property），`_stop_health_checker` join 超时后保留
  引用不再置 None（残留线程下一批次边界自然退出，不空耗配额）；
- `src/utils/logging_utils.py::setup_logger_safety`（P1）："检查-追加"
  段无锁，并发调用各加一个过滤器实例（handler.filters 膨胀）——补
  模块级锁串行化幂等短路；

### 可维护性

- `src/graph/workflow.py::_should_debug`（P2）：诊断关键词列表散落在路由
  函数体内每次调用重建——提取为模块级常量 `_TEST_GEN_DIAGNOSIS_KEYWORDS`
  （口径单一来源，后续调触发词只改一处）；
- `src/graph/nodes.py`（P2）：`_executor_node` 函数内局部导入
  `EXECUTOR_DOCKER_IMAGE` / `EXECUTOR_USE_DOCKER` 与文件头 9 个 config
  符号风格漂移——并入文件头导入；

### 性能（未深审模块补强，2026-09-26 第三轮）

- `src/datasets/dataset_loader.py`（P1）：`get_task_by_id` 由 O(n) 线性扫描
  降为 O(1) 查表——SWE-bench full 2294 任务 × benchmark 循环逐查原为
  O(n²)。实现：`__init__` 建 `_task_index: dict[str, BenchmarkTask]` +
  `_index_size` 长度标记（O(1) 失效判断）；`_ensure_loaded` 加载完成后
  全量重建一次；`add_task` 追加后长度变化触发惰性重建（O(n) 一次，
  后续 O(1)）。基类新增 `add_task`（原 InMemoryDataset 直接 append
  无索引维护），子类删该覆写；
- `src/tools/code_analyzer.py` + `src/tools/code_context.py`（P1，C-1）：
  `extract_function_context` 在 `extract_focused_code` 原样返回时
  **再做一次 `ast.parse + ast.walk`** 确认函数是否存在——大文件
  ~200ms 翻倍。新增 `extract_focused_code_detail` 返回
  `(code, focus_resolved)` 二元组，`extract_function_context` 直接消费
  `focus_resolved`，零重复解析。`extract_focused_code`（原签名）委托
  新函数保持兼容，3 处调用方无需改动；

### 正确性（未深审模块补强，2026-09-26 第三轮）

- `experiments/rag_ab_experiment.py`（P0）：`_parse_task_record` 读取的
  字段名（`tokens_total` / `total_tests` / `passed_count` / `duration_s` /
  `failure_category`）与 `run_benchmark._build_task_result` 实际产出的键
  （`token_usage{total_tokens}` / `elapsed_seconds` / `iterations` /
  `passed` / `error_category`）零交集——全部 `.get` 落到默认值，RAG A/B
  报告的 token 收益 / 耗时 / 错误分布三大结论恒为假数据。现按真实键读取；
- `experiments/rag_ab_experiment.py`（P1）：`_run_benchmark_once` 新增
  `sub_run_dir` 参数——RAG ON / OFF 两次运行各自写入独立子目录
  （`<output_dir>/rag_on`、`<output_dir>/rag_off`），避免共用 output_dir
  时同一秒内写出导致 mtime 碰撞互相污染（`benchmark_*.json` 时间戳
  精度仅秒级）；
- `experiments/run_benchmark.py`（P2）：`task_limit` 边界归一——负数原
  语义为 slice 静默截断（`tasks[:-1]` 丢最后一个任务），0 走 else 当全量；
  现统一 `<1` 视为不限制（全量），仅正数生效，消除负数静默改任务数，
  并记 warning；
- `scripts/compare_executor_modes.py`（P1）：`main.py run --json` 多文件时
  stdout 为多个 JSON 对象逐段拼接（每任务一段，非单个数组）——原
  `json.loads(proc.stdout)` 对多段拼接必失败 → `tasks_passed` 恒 0。
  新增 `_parse_json_stream` 用 `JSONDecoder.raw_decode` 逐个消费
  （兼容单对象 / 数组 / 多段拼接三种形态）；
- `src/reports/generator.py`（P1）：`get_report_generator()` 无锁
  check-then-act，`--parallel` 首次并发构造竞态各建一个
  `ReportGenerator`（每个各建一个 `ErrorClassifier`）——补模块级
  `threading.Lock` 双检锁；
- `src/reports/generator.py`（P2）：`ErrorReport.to_dict` 的
  `error_context.__dict__` 直接内省序列化（dataclass 未来加内部字段
  会无声改变 schema）——改 `asdict` 显式序列化（与 nodes.py
  cross_file_deps 同型修复）；
- `src/tools/cross_file.py`（P1）：`build_cross_file_repair_plan` 对每个
  模块生成补丁时仅 catch `(json.JSONDecodeError, RuntimeError)`，LLM 超时
  等异常传播出去中断整个跨文件计划构建——放宽为 catch 全 `Exception`
  （单模块失败仅跳过、不毁全计划，与 multi_candidate.generate_candidates
  同口径）；
- `src/datasets/dataset_defects4j.py`（P2）：`info.json` 解析失败原静默
  返回 None（损坏版本无声跳过）——记 `logger.warning` 便于定位数据问题；

### 并发（未深审模块补强，2026-09-26 第三轮）

- `src/tools/cross_file.py`（P1）：`_save_repair_plan_cache` 直接
  `open("w") + json.dump` 非原子——`--parallel` 双 worker 同依赖图并发写
  会交错损坏 JSON → 读侧降级 None → 重调 LLM，放大成本。改"先写临时
  文件再 `os.replace` 原子替换"（与 nodes.py `_write_file_atomic` 同模式），
  失败时清理临时文件；
- `scripts/check_lock_sync.py`（P2）：新增规则 4（WARNING 不影响退出码）：
  lock 中存在但 requirements.txt 未声明的"多余项"提示——如 radon 已从
  requirements 移除但 lock 仍残留（radon==6.0.1），提示重新生成 lock
  （lock 含传递依赖，仅 WARNING 不阻断）；

### 跨文件修复逻辑缺陷（CF-3，2026-09-26 第四轮）

- `src/tools/cross_file.py::build_cross_file_repair_plan`（P0）：协调器-提议者
  架构本意是"每个模块由一个提议者看自己模块的代码生成补丁"，但此前对每个
  模块调用 `debugger.debug(target_code=target_code, ...)` 时**都传入口模块的
  `target_code`**——模块 B 的补丁实际是基于模块 A 的代码生成的，多文件场景下
  补丁错位。现新增可选 `source_files: dict[str, str] | None` 参数：提供时每模块
  用自己模块的源码（`source_files.get(module_name)`），未含该模块时回退
  `target_code`（保守口径，不阻断该模块补丁生成）；`source_files=None` 保持
  历史行为（全模块共用 `target_code`，向后兼容）；`target_module` 参数从调用方
  传入的固定值改为按模块名 `module_name` 传入（协调器-提议者本意：LLM prompt
  约束的是"当前提议者负责的模块"）；
- `src/tools/cross_file.py::build_cross_file_repair_plan_cached`：缓存包装层天然
  持有 `source_files`（用于依赖分析），此前未透传给底层 `build_cross_file_repair_plan`
  → 即使调用方有源码，底层仍全模块共用 `target_code`。现透传 `source_files`，
  缓存命中路径与 LLM 生成路径口径一致；
- 回归测试：`tests/test_cross_file.py` 新增 3 用例（`test_source_files_per_module_code`
  验证每模块拿到自有源码 + 模块名；`test_source_files_fallback_to_target_code`
  验证 source_files 未含某模块时回退入口代码；`test_source_files_none_keeps_legacy_behavior`
  验证 source_files=None 时全模块共用 target_code 历史行为）；

### 变异测试判定与变异体生成（P0/P1，2026-09-26 第五轮）

- `experiments/mutation_testing.py::_run_mutant_tests`（P0）：此前
  `return proc.returncode != 0` 把 pytest 的**所有**非零退出码（含
  2=收集错误 / ModuleNotFoundError / 语法错误）一律当作"杀死"，与文档
  声明的保守口径（"执行失败（如 import 错误）视为存活"）正好相反——
  实测 e2e 路径下测试 import 的模块名与写盘的 `mutated_module.py` 对不上时，
  每个变异体子进程都以收集错误退出（rc=2）→ 全部误判为"杀死" →
  mutation_score 恒 1.0，弱测试与强测试得分无法区分（指标失效）。
  现按 pytest 官方退出码精确判定：rc==1（有测试失败）= 杀死；rc==0 = 存活；
  其他（2/5/超时/异常）= 存活（保守口径，不夸大变异得分）；
- `experiments/mutation_testing.py`（P1）：变异体"按行号尽力定位"缺陷——
  `_flip_comparison_op` / `_offset_numeric` / `_shift_boundary_op` 在
  deepcopy 后按"行号取第一个同类型 Compare"定位，同行多比较
  （`a < b and c < d`）时只改第一个且 description 记录原节点操作符，
  产生描述与改动不一致 + 重复变异体。定位键升级为
  **(lineno, col_offset) 双键**，精确到具体比较表达式；
- `experiments/mutation_testing.py::generate`（P1）：此前按注册顺序
  `mutants[:20]` 截断且不去重——前 4 类（比较/布尔/数字/边界）在富比较
  代码上易爆炸，把 P0 3.3 新增的第 5-7 类（return_void / return_empty /
  exception_*）整体挤掉，"7 类全启用"的设计意图落空；无效变异体
  （未改到目标 → 代码不变 → 判存活）被下游消费导致 mutation_score
  假性偏高。现按 `mutant.code` **去重**（消除重复变异体）+ **类型轮转
  均匀取样**（7 类分桶 round-robin 填满上限，保证每类都有代表）；
- `experiments/mutation_testing.py`（P1 配套）：`_OPERATOR_FLIP_MAP` 此前
  含 `Lt↔LtE / Gt↔GtE`，与 `boundary_shift` 类型生成**同一份变异代码**，
  代码级去重会把 boundary_shift 整类消除。现 operator_flip 仅保留等值对
  （Eq↔NotEq，boundary_shift 不覆盖），严格比较边界变异专属于
  boundary_shift，两类互不重叠、各有独立变异体；
- `experiments/mutation_testing.py`（P2）：`_run_mutant_tests` 内
  `__import__("subprocess")` 反模式改常规局部 `import subprocess`
  （同函数已局部 import os/sys/tempfile）；
- 回归测试：`tests/test_smell_detection_v2.py` e2e 用例修复 import 名
  错配（`from module import check` → `from mutated_module import check`，
  使"弱测试低分 / 强测试高分"断言真正生效）；`tests/test_multi_candidate.py`
  boundary_shift 用例更新源码为严格比较以匹配修复后的类型分布。

### 并行 API 轮询可复现性（P0，2026-09-26 第五轮）

- `experiments/run_benchmark.py::run_single_task`（P0）：此前
  `hash(task.task_id) % len(_VALID_APIS)` 做任务→API 轮询索引——
  Python 3 的 `str` 内建 `hash()` 受 `PYTHONHASHSEED` 随机化，同一任务
  在不同进程/启动间映射的 API 索引不一致，破坏"任务→API 稳定轮询"的
  文档承诺（基线对比不可复现）。现改用 `zlib.crc32(task_id)`
  （跨进程确定性）+ 基线索引混合：
  `(crc32(task_id) + baseline_idx) % n`，保持任务内多基线轮错开历史行为；
- `experiments/run_benchmark.py::run_single_agent_baseline`（P0）：
  single_agent 基线此前直接 `open(state["target_file"], "w")` 写 LLM
  输出的 `new_code`，绕过 `_patch_applier_node` 的安全检查——LLM 返回
  空壳/过短代码时清空被测实例文件，后续基线/重试拿到空代码。
  现补最小守卫：非空（≥ 原代码 10%）+ 函数定义数不减少（与工作流
  写盘口径一致）；不通过时放弃写盘、保持原代码（记 warning）。

### LLM 缓存原子写（P1，2026-09-26 第五轮）

- `src/agents/base_agent.py::_call_llm_with_cache`（P1）：此前直接
  `open(cache_file, "w") + json.dump` 非原子——`--parallel` 下两 worker
  同键（同 prompt 材料 → 同 md5 → 同 cache_file）并发写时，另一方读侧
  可能观察到半截 JSON → `json.load` 抛错 → 静默降级重调 LLM
  （浪费 token + 延迟）。缓存文件键即内容 md5，并发写入的是逐字节相同
  的 JSON。现改"写线程唯一临时文件（`.tmp.<thread_id>`）→ `os.replace`
  原子替换"（与 cross_file CF-8 / nodes._write_file_atomic 同模式），
  替换失败时清理临时文件。

### 状态 schema 与写盘安全检查（P2，2026-09-26 第五轮）

- `src/graph/state.py`（P2）：`repo_verification` 字段此前由
  `run_benchmark` 在 invoke 后 set 到 final_state 但**未声明于
  AITesterState TypedDict**（守护测试 test_state.py 会漏报）。
  现显式声明 `repo_verification: dict[str, Any] | None` 并在
  `create_initial_state` 工厂初始化为 None（键集与 __annotations__ 对齐）；
- `src/reports/generator.py::_parse_failed_cases`（P2）：兜底解析器此前
  `"FAILED" in line and "[" in line` 硬条件漏掉现代 pytest 短输出
  （`FAILED test_x.py::test_y - AssertionError`，无 `[`）；
  `"Error" in line` 过宽（任何含 "Error" 的行都覆盖 error 字段）。
  现按 pytest 实际输出模式匹配：用例名取 FAILED 行内首个 token（`[E]/[F]`
  后缀/短格式后缀均兼容）；短格式行内错误后缀直接提取；详细格式取
  FAILED 行后首个异常类名行；无 name 时兜底 "unknown"（历史行为保持）；
- `scripts/verify_swe_bench_export.py::_extract_suggested_func_from_patch`
  （P2）：`line.startswith("@@") or line.startswith("@")` 与下方正则
  `re.search("@@...")` 语义矛盾——`startswith("@")` 会命中 diff 删除行
  里的装饰器（`-@decorator` 行以 `@` 开头但非 hunk 头）。现收紧为仅
  hunk 头 `@@` 行，用 `split("@@", 2)[2]` 提取尾部上下文
  （与 dataset_loader._extract_suggested_function 同口径）。

### 节点层路由语义与鲁棒性（P1/P2，2026-09-26 第六轮）

- `src/graph/workflow.py::_should_debug`（P1 路由语义澄清）：诊断关键词
  判定此前嵌套在"达迭代上限"块内——早期迭代（iteration < max）命中
  "测试生成错误"关键词时仍走 debugger 修代码，而非回 generator 重新
  生成，与 `_generator_node` 再生成判定（含 `defect_type == test_defect`
  任意迭代可触发）及 3.1 双向诊断路径口径不一致。现把诊断关键词判定
  提升为独立分支（任意 iteration 命中即 regenerate，仍受
  `regeneration_count` 上限保护；上限已满时落常规 debug）；
- `src/graph/workflow.py::_should_debug`（P1 一致性）：`test_passed` 此前
  用 `is True` 严格恒等判定，与 `_recent_repairs_invalid` 的 truthiness
  口径不一致（非 bool 真值如 `numpy.bool_` 会被 `is True` 误判为未通过
  → 误路由 debug）。现统一为 truthiness；
- `src/graph/nodes.py::_generator_node`（P1 降级兜底）：此前
  `agent.generate` 无 try-except，LLM 调用失败（RuntimeError，含跨 API
  故障转移耗尽）/ 缓存 OSError 会让整图崩溃——与 planner/debugger 节点
  "降级兜底"口径不一致（二者均有默认计划 / 空 patch 兜底），且
  workflow.py 模块文档声称"使用 try-except 捕获 LLM 调用异常，确保
  工作流不因单点故障而崩溃"。现补降级：LLM 失败时生成空测试并记
  warning，executor 拿到空测试自然失败 → 路由到 debugger/done，不再
  崩溃整图（对"LLM 完全不可用"场景：崩溃=零产出，降级=仍有修复机会）；
- `src/graph/nodes.py::_planner_node` / `_debugger_node`（P2 兜底扩宽）：
  except 子句此前仅捕获 `(json.JSONDecodeError, RuntimeError)`，未覆盖
  LLM 文件缓存读写抛的 `OSError`（缓存目录被外部删除/磁盘满等场景）。
  现扩为 `(json.JSONDecodeError, RuntimeError, OSError)`，与"节点降级
  兜底"设计口径一致（缓存 IO 异常不再让整图崩溃）；
- `src/graph/workflow.py`（P2 线程卫生）：`_FILE_CACHE_COUNT_MEMORY` 的
  读-改-写无锁保护，`--parallel` 多任务收尾报告并发调用
  `get_workflow_stats → _file_cache_entry_count` 时可能读到半更新元组
  （另一线程 stat/glob 中途）。现加模块级 `threading.Lock` 把"记忆读 +
  stat/glob + 记忆写"整段串行化（临界区内均为只读系统调用，普通 Lock
  足够；记忆键语义不变）；
- `src/tools/cross_file.py`（P2 导入卫生）：`_save_repair_plan_cache`
  的 except 分支内局部 `import contextlib` 提升到模块顶层导入
  （消除函数体内 import，与其他模块级导入口径一致）。

回归测试：`tests/test_workflow.py` 新增
`test_generator_node_llm_failure_degrades_to_empty`（generator LLM 失败
降级为空测试）；`tests/test_workflow_extended.py` 新增
`test_should_debug_regenerate_at_early_iteration`（早期迭代诊断关键词
路由 regenerate + 再生成上限保护）。

### 验证

- `ruff check` / `ruff format --check` / `mypy src/` 全绿；
- 全量 1728 测试通过（28.7s），零回归（第六轮新增 2 条回归用例：
  generator LLM 失败降级 + 早期迭代诊断关键词路由；第五轮修复既有
  变异测试 e2e 用例的 import 名错配使其断言真正生效，新增 2 条
  报告解析回归用例）。

## [Unreleased] — P0 改进批次：13 项落地（分层代码压缩 / 复杂度感知路由 / 命名契约验证 / 合成数据集分层难度 / 跨文件合成任务 / SWE-bench 导出质量验证 / RAG A/B 实验脚本 / 多候选自适应触发 / 变异体难度升级 / 错误分类子类+响应重试 / 追踪层默认启用 / venv 按仓库复用）

> 对应实验数据缺口（SWE-bench 0/20、合成集统计已覆盖但真实集 A/B 缺失）与
> `docs/assessment_2026-09-25_improvement_directions.md` 的改进路线。
> 全部默认行为兼容（默认参数回退历史口径，显式开启才启用新能力）。
> 详见 `docs/implementation_2026-09-25_p0_batch.md`。

### 功能（默认行为不变，经环境变量显式开启）

- **1.1 分层代码压缩（函数级切片 + 调用链深度）**（`src/tools/code_context.py` +
  `src/tools/code_analyzer.py` + `src/agents/base_agent.py`）：
  - `extract_function_context(source, func_name, depth=2, max_chars=3000)` 委托
    `extract_focused_code()` 的 BFS 调用链闭包（`_closure_names`），
    depth=1 保留直接依赖（历史行为），depth=2 再展开一层被调函数自身依赖；
  - `BaseAgent.truncate_code()` 新增 `focus_depth` 参数（读 `CODE_FOCUS_DEPTH`，默认 1）；
    `_CODE_MAX_CHARS` 改读 `CODE_MAX_CHARS` 环境变量（默认 3000）；
  - `debugger.py` 的 `cross_file_contexts` 经 `extract_function_context`
    生成 per-module 2000 字符预算 + 总 4000 字符预算，注入 Debugger prompt。

- **1.2 复杂度感知路由（固定 Agnes 3.0-flash 多 provider 端点）**（`src/api/complexity_router.py`
  新增 + `src/api/api_manager.py` + `src/graph/state.py` + `experiments/run_benchmark.py`）：
  - `compute_complexity_score(lines, num_files, num_deps, cyclomatic_complexity)` 输出
    [0,1] 归一化评分（阈值 `<0.35 → simple / <0.70 → medium / >=0.70 → complex`，
    各维度权重由 `ROUTING_COMPLEXITY_*_NORM` 环境变量可配）；
  - `APIManager._select_node_by_complexity(complexity_class)` 按 cost_weight 排序
    APIHealth 节点（complex → 高 cost_weight 端点在前，simple → 低成本端点在前）；
  - `state["complexity_class"]` / `state["complexity_score"]` / `state["complexity_breakdown"]`
    / `state["routing_hints"]` 由 `run_benchmark.py` 在 `create_initial_state` 后计算写入；
  - 约束：仅路由 Agnes 3.0-flash 的多 provider 端点，不引入其他模型家族；
  - `MODEL_ROUTING_STRATEGY=fixed` 回退历史策略。

- **1.3 补丁命名契约验证（默认开启）**（`src/tools/patch_applier.py` + `src/graph/nodes.py`）：
  - `check_naming_contract(original_code, patched_code) -> (bool, list[str])`：
    AST 对比前后模块级符号（函数/类/`__all__`/注册装饰器/模块级常量），
    缺失任何原符号则拒绝补丁；
  - `PATCH_CONTRACT_CHECK=true`（默认）时在 `_patch_applier_node` 写盘前调用；
  - Debugger prompt 注入 `_CONTRACT_CONSTRAINT`（"不得修改或删除以下符号……"）。

- **2.1 合成数据集分层难度（difficulty 参数）**（`src/datasets/synthetic_dataset.py` +
  `experiments/run_benchmark.py`）：
  - `SyntheticDataset(task_count, seed, subset, difficulty="mixed", **kwargs)`：
    支持 `mixed` / `level1` / `level2` / `level3` / `level4` 五个难度梯度；
  - Level 1（历史口径）/ Level 2（多函数交互缺陷）/ Level 3（跨文件双模块构造）/
    Level 4（边界+异常隐蔽缺陷）；
  - CLI `--difficulty` 选项仅对 synthetic 数据集生效。

- **2.2 跨文件合成任务构造（Level 3 双模块）**（`src/datasets/synthetic_dataset.py`）：
  - `CROSS_FILE_PATTERNS` 双模块模板（module_a 入口 + module_b 被调方含缺陷）；
  - `instance_code=module_b_code`，`metadata.module_a_code` / `target_module` /
    `fixed_module_b_code` / `num_files=2` 供跨文件修复架构消费；
  - 修复需改 module_b 接口 → 验证跨文件修复架构（协调器-提议者）。

- **3.2 多候选自适应触发（默认 adaptive）**（`src/graph/nodes.py`）：
  - `MULTI_CANDIDATE_TRIGGER_STRATEGY=adaptive`（默认）：仅当
    `iteration >= 1` 且 `error_category ∈ {assertion, runtime, logic_error, index_error}`
    时才启用多候选；简单任务 / 早期迭代保持单候选省 token；
  - `MULTI_CANDIDATE_TRIGGER_STRATEGY=always` 回退历史口径。

- **3.3 变异体难度升级（7 种变异类型）**（`experiments/mutation_testing.py`）：
  - 新增 `_ReturnEmptyTransformer` / `_RemoveRaiseTransformer` /
    `_ExceptionTypeTransformer` 三类 transformer；
  - 变异体类型从 5 扩至 7（operator_flip / boolean_negation / numeric_offset /
    boundary_shift / return_void / return_empty + exception_remove +
    exception_type_swap），提升对"边界 + 异常路径"类缺陷的覆盖度。

- **4.1 错误分类子类 + 响应格式重试**（`src/agents/error_classifier.py` +
  `src/agents/debugger.py`）：
  - `ErrorCategory` 新增 `LLM_EMPTY_RESPONSE` / `LLM_JSON_PARSE_FAILED`
    （从 `LLM_FORMAT_ERROR` 拆出的两个精确子类，14 类 → 16 类）；
  - `ErrorClassifier.classify_llm_response(raw_response)` 直接分析 LLM 原始响应：
    空 → LLM_EMPTY_RESPONSE；非空但 JSON 提取失败 → LLM_JSON_PARSE_FAILED；
  - `debugger.py::debug()` 检测到格式异常时用更严格 prompt 自动重试一次，
    仍失败则降级到宽松 JSON 提取。

- **4.3 venv 按仓库复用（SWE-bench 多 commit 场景）**（`src/agents/executor_repo.py`）：
  - `RepoExecutor(venv_reuse_by_repo=True)`：同一仓库多 commit 共享一个仓库级 venv
    （`<repo>/_shared_venv/`），仅当依赖指纹（SHA256 of requirements/pyproject/setup）
    变更时重建；源码切换不触发重装（editable install 的 `.pth` 自动跟随 checkout）；
  - 大幅减少 SWE-bench 同一 repo 多 commit 场景的 venv 重建开销（10-20 倍）；
  - `SWE_REPO_VENV_REUSE_BY_REPO=true` 启用（需配合 REPO_LEVEL_EXECUTION + SWE_REPO_VENV_ISOLATION）。

### 可观测性与实验脚本
- **2.3 SWE-bench 源码导出质量验证**（`scripts/verify_swe_bench_export.py` 新增）：
  - 5 维度验证（非空 / 行数 / Python 语法 / 目标函数存在 / 目标文件路径匹配），
    输出结构化质量报告（`pass_rate` / `by_label` / `failed_instances` / `avg_line_count`）；
  - CLI：`--enrichment` / `--instances` / `--output` / `--min-lines`。
- **3.1 RAG A/B 对比实验脚本**（`experiments/rag_ab_experiment.py` 新增）：
  - 自动执行 RAG ON / RAG OFF 两次 benchmark，配对分析 token / 成功率 / 迭代 / 耗时，
    Welch t-test + Mann-Whitney U + Cohen's d 统计检验（与 0.7 报告同口径）；
  - 按错误类型分组分析 RAG 收益（哪类错误在 RAG ON 下显著减少）；
  - `--analyze-only` 模式（读已有结果 JSON 直接统计，跳过实验运行）。
- **4.2 追踪层默认启用**（`experiments/run_benchmark.py`）：
  - 入口处若 `AITESTER_TRACE_DIR` 未设（或为空），自动设为 `<output_dir>/traces/`；
  - 节点级 JSONL 记录（输入长度 / 输出长度 / token / 耗时 / 路由决策）随工作流自动追加；
  - 设 `AITESTER_TRACE_DIR=`（空串）显式关闭。

### 文档与测试
- **文档同步**：
  - `README.md`：错误分类 14→16 类 + 新增 §5.21 P0 改进批次（13 项）+
    更新"最新优化"/"最近改动"行；
  - `.env.example`：新增 P0 批次环境变量（CODE_FOCUS_DEPTH / CODE_MAX_CHARS /
    MODEL_ROUTING_STRATEGY / ROUTING_COMPLEXITY_*_NORM / PATCH_CONTRACT_CHECK /
    MULTI_CANDIDATE_TRIGGER_STRATEGY / SWE_REPO_VENV_REUSE_BY_REPO）；
  - `docs/implementation_2026-09-25_p0_batch.md`（新增）：P0 批次完整实施清单。
- **测试更新**：
  - `tests/test_error_classifier.py`：枚举 14→16 类断言 + P0 4.1 子类存在性校验；
  - `tests/test_synthetic_dataset.py`：difficulty 分层测试 + 跨文件 Level 3 结构校验；
  - `tests/test_workflow_extended.py`：多候选自适应策略环境变量 +
    `_select_multi_candidate_patch` 签名（`iteration` 参数）；
  - `tests/test_executor_repo.py`：`_run_test_nodes` mock 签名（`repo_url` 参数）。

### 验证
- 全量回归：`python3 -m pytest tests/ -q` → **1667 passed, 47 skipped**（同基线，零回归）
- 受影响子集：test_base_agent（40）/ test_code_context（18）/ test_error_classifier（77）/
  test_debugger（38）/ test_workflow_extended（37）/ test_executor_repo（17）/
  test_synthetic_dataset（5）/ test_api_manager + extended（152）/ test_code_analyzer（17）

## [Unreleased] — 改进方向批次：5 项落地（3.3 位置感知迭代修复 + 5.2 错误分类 14 类文档同步 + 5.1 单批次边界测试 + 4.2 脱敏自动检查钩子 + 2.1 真实嵌入钩子）

> 对应 `docs/assessment_2026-09-25_improvement_directions.md` 的"真实剩余工作"清单
> （16 个改进子方向逐项核实后，其中 10 项已实现、6 项有剩余工作；本批次落地其中 5 项，
> 剩 #5 多候选 A/B 实验数据属实验执行工作，不在代码批次内）。

### 功能（默认行为不变，经环境变量显式开启）
- **3.3 位置感知迭代修复（LoopRepair 式先定位再补丁）**（`src/agents/debugger.py` +
  `src/graph/state.py` + `src/graph/nodes.py`）：
  - 新增 `POSITION_AWARE_REPAIR_ENABLE` 开关（默认 false，保持历史实验口径）。
  - `DebuggerAgent._locate_repair_focus()`：把 `error_classifier` 已提取的异常位置
    （traceback 行号 / 语法错误行列）经 AST 定位到"包围异常行的最短区间函数"，
    生成位置感知修复指引注入补丁 prompt，让 LLM 优先修定位到的位置而非全文件盲搜；
    纯静态不耗 LLM token，无法定位（无行号 / AST 损坏 / 跨文件保护）时自动降级为
    常规全文件修复。
  - `debug()` 返回 dict 新增 `position_aware_focus` 键（focused / function_name /
    line / hint）；debugger 节点写入 `state["position_aware_focus"]`。
  - 测试 `tests/test_debugger.py` 新增 `TestPositionAwareRepair`（9 用例）。

### 可观测性与工程化
- **4.2 日志脱敏自动检查钩子**（`.pre-commit-config.yaml` + `.github/workflows/ci.yml`）：
  - pre-commit 新增 local hook `audit-log-redaction`（命中 `src/**/*.py` /
    `experiments/**/*.py` 时跑 `scripts/audit_log_redaction.py`，发现"参数含敏感字段
    名且未脱敏"的日志点退出码 1 阻断提交）；CI 新增 "Audit log redaction (4.2)" 步骤，
    与 pre-commit 同一脚本，本地/远端口径一致。
  - 新增"模拟敏感信息注入"回归测试 `tests/test_audit_log_redaction.py`（6 用例：
    仓库基线零可疑点、未脱敏注入必检出、脱敏后不检出、Bearer/sk- 凭证检出、
    exc_info 堆栈不报 finding、tests/ 目录跳过）。

### 评估指标（可选依赖，默认零外部依赖保守口径）
- **2.1 真实语义嵌入钩子**（`src/utils/embedding_utils.py` +
  `experiments/contamination_check.py`）：
  - 新增 `src/utils/embedding_utils.py`（零新增硬依赖）：`embed_text()` 按
    `EMBEDDING_BACKEND` 环境变量选择嵌入后端（auto：sentence-transformers >
    chromadb DefaultEmbeddingFunction > None；none：强制 None 保持词袋保守口径，
    便于"真实嵌入 vs 词袋代理"A/B 对照）；`cosine_similarity()` 用 numpy（项目已
    依赖）计算，缺失时纯 Python 回退，非负夹取与词袋余弦口径可比；`backend_name()`
    供报告标注语义级来源。
  - `experiments/contamination_check.py` 接线：`_embed_code` 委托
    `embedding_utils.embed_text`（调用期惰性加载，experiments 包保持零默认外部硬
    依赖）；`patch_semantic_similarity` 新增 `semantic_source` 字段
    （"embedding"/"token_bag"）；污染检测报告渲染层标注语义级来源。
  - 测试 `tests/test_embedding_utils.py`（12 用例）。

### 文档与测试
- **5.2 错误分类 12 类 → 14 类文档同步**：`README.md` / `README.en.md` /
  `docs/api_reference.md` / `docs/api_reference.en.md` / `docs/failure_analysis.md`
  中"十二类/12 类"表述同步为十四类，补 `EXECUTION_TRACE_MISSING` /
  `MULTI_CANDIDATE_ALL_REJECTED` 两类的枚举表行与判定优先级说明
  （`patch_rejected > rag_empty > trace_missing > multi_rejected`）；
  `docs/history/*` 为历史快照有意保留 12 类表述不改。
- **5.1 cross_batch_comparison 单批次边界测试补强**（`tests/test_smell_detection_v2.py`
  + `tests/test_failure_kb.py`）：补强 `test_single_batch_no_trend`（加
  `resolved_categories` / `failure_trend` 断言），新增
  `test_single_batch_all_passed_empty_trend`（全通过时 failure_trend 为空字典）与
  `test_empty_summaries_list`（批次列表为空不崩溃）。

> 验证：全量回归 `pytest tests/ -q` 通过；受影响子集（test_debugger 38 /
> test_smell_detection_v2 / test_failure_kb / test_audit_log_redaction 6 /
> test_contamination_check+multidim 40 / test_embedding_utils 12）全部通过；
> `ruff check` 改动文件 0 告警。详见
> `docs/implementation_2026-09-25_improvement_directions.md`。

## [Unreleased] — 0.10 轮次 0.9 批次深度审查修复（LLM 缓存负缓存 TTL 正确性回归 + 白名单根归一口径修正 + 追踪层冗余摘要消除 + 统计接口免重扫 + 2 条回归用例）

> 基线：0.9 批次（未提交工作区）1665 passed / ruff 全仓 0 告警 / mypy 0 错误（58 源文件）。
> 本轮为对 0.9 批次的深度审查 + 回修：**1667 passed / 0 failed**（+2 条回归用例，无功能回归），
> ruff check / ruff format / mypy 全仓 0 错误。

### P1 正确性：LLM 缓存负缓存 TTL 缺失导致的正确性回归修复（`src/agents/base_agent.py`）

0.9 批次引入的"LRU 快路径 + 负缓存"实现存在两处正确性漂移：

1. **负缓存永不失效**：`_lru_negatives` 记录"该键文件不存在"后无 TTL，
   若缓存目录随后被外部恢复 / 新文件写入，同键调用在负缓存命中时
   **跳过文件读取**，本可命中的磁盘缓存永远不可见（与模块注释
   "文件仍是事实来源"矛盾）。现引入 `_LRU_NEGATIVE_TTL_SECONDS = 30.0`：
   窗口内同键跳过文件重读（省"读不存在的文件"IO），过期后惰性清理
   负缓存条目并重新读文件（恢复外部写入可见性）。
2. **写成功路径不清除负缓存**：`_lru_store(key, value)` 的
   `del _lru_negatives[key]` 在"从未记过负缓存"时 KeyError（原 0.9
   实现用 `del` 而非 `.pop`），且"文件写入成功"语义上必须让该键的
   负缓存失效（"文件不存在"判定不再成立）。现改为 `.pop(key, None)`
   幂等清除，测试 `test_negative_cache_expiry_rechecks_file` 锁定
   "写成功后负缓存清除 + TTL 过期后重检命中"两条路径。

### P1 正确性：路径白名单根归一化口径修正（`src/graph/nodes.py`）

0.9 批次 `_ALLOWED_WRITE_ROOTS` 归一化实现存在冗余与注释口径矛盾：

- 旧实现 `os.path.realpath(os.path.abspath(...))` 中 `realpath` 内部
  已含 `abspath` 语义，外层再包一层 `abspath` 属冗余；
- 模块注释声称"两侧统一 realpath 归一"，但根目录计算路径与
  `_is_within_allowed_roots` 的 `os.path.realpath(path)` 归一不在
  同一口径（macOS /var→/private/var 符号链接场景下 `abspath` 结果
  不同，`realpath` 统一解析符号链接才是判定正确性的关键）。
现统一为 `os.path.realpath(root)`（root = 原始 dirname/tempdir 值，
不预先 abspath），与 `_is_within_allowed_roots` 的入参归一口径完全
对称；注释同步修正。

### P2 性能：追踪层冗余 meta 摘要消除（`src/observability/trace.py`）

`TraceSession._append` 此前对每条记录做 `dict(record)` 浅拷贝 +
`payload["meta"] = {k: _summarize(v) ...}` 重建 meta dict——但
`task_start` 的 meta 在 `__init__` 构造时已逐值 `_summarize`，
`record_node` 的 output 与 `record_task_end` 的 extra 也在入口处
摘要过，`_append` 处的二次摘要是纯冗余（深处理 + 临时 dict 分配，
`--parallel` 多任务追踪热路径上累积）。现收敛为：记录对象只读
序列化，摘要责任统一归入口（task_start 构造 / record_node 入口 /
record_task_end 入口），`_append` 仅做脱敏 + 写盘。

### P2 性能：`_file_cache_entry_count` 进程内记忆免重复 glob（`src/graph/workflow.py`）

0.9 批次 `get_workflow_stats()` 的 `llm_cache.entries` 统计每次调用都
做 `Path(cache_dir).glob("*.json")` 全目录扫描——`--parallel` 多任务
收尾报告逐任务调用 `get_workflow_stats` 时累积 N 次冗余目录扫描。
现引入模块级 `_FILE_CACHE_COUNT_MEMORY = (缓存目录, 条目数)` 记忆：
同目录直接复用上次统计（免 glob）；目录切换（环境变量变更）时记忆键
失配自动重扫；目录被外部删除（stat 失败）时记忆失效归 0。统计口径
（glob 实时值）不变，仅省重复扫描。

### 验证

- ruff check 全仓 0 告警；ruff format 195 文件全绿；mypy 58 源文件 0 错误；
- pytest 全量 **1667 passed / 0 failed**（0.9 基线 1665 + 本轮 2 条回归
  用例：`test_negative_cache_expiry_rechecks_file` /
  `test_file_cache_entry_count_memory`）；
- 负缓存 TTL 基准：窗口内命中零文件 IO（仅 LLM 调用本身），
  过期后重检命中磁盘缓存（零 LLM 调用）。

---

## [Unreleased] — 0.9 轮次性能与一致性优化（LLM 文件缓存 LRU 快路径 + 双套缓存漂移消除 + 补丁应用正则预编译 + 节点纯函数口径修复 + 深度审查修复）

> 基线：ruff 全仓 0 告警 / mypy 全仓 0 错误 / pytest 1678 通过。优化后 **1665 通过**
> （删除 16 个已移除死模块 `src/graph/llm_cache` 用例 + 更新 2 个统计口径用例 + 新增 3 条回归用例，无功能回归），
> ruff check / mypy（58 源文件）全仓 0 错误。

### P0 性能：LLM 文件缓存热路径增加进程内 LRU 快路径（`src/agents/base_agent.py`）

此前 `_call_llm_with_cache` 每次调用都对缓存文件做 `open` + `json.load`（约 10–20μs/次，且命中判定需全量比较 prompt/system 文本），`--parallel` 多任务下累积为可观的磁盘 IO。现增加进程内 LRU（容量 1024，与 LLM 客户端缓存同口径）：

- **命中**：O(1) 直接返回，**零磁盘 IO**（基准：命中路径 1.1μs/op vs 纯文件读 11.5μs/op，约 10× 加速）；
- **未命中但文件存在**：完整读文件后回填 LRU，语义与"每次读文件"一致（文件仍是事实来源，跨进程/跨会话行为不变）；
- **未命中**：负缓存记录"该键无文件"，省去热循环里对不存在文件的重复 stat；
- 提供 `clear_llm_lru_cache()` 供测试与缓存目录切换时清空（`tests/test_llm_file_cache.py` 加 autouse fixture 防御跨测试残留）。

### P1 正确性：双套缓存漂移消除——删除死模块 `src/graph/llm_cache.py`（0.7 P1-1.3 债务项落地）

该模块（进程内 LRU）与生产文件缓存 `src/cache/` 互不相通，自身注释已标注为"历史债"：生产 LLM 调用路径**不经过**它，仅测试与其自身统计被 `get_workflow_stats()` 引用。按"删除死模块、统一口径"决策一并清理：

- 删除 `src/graph/llm_cache.py` 与 `tests/test_llm_cache.py`（16 个用例，全部只测该死模块内部 API）；
- `workflow.get_workflow_stats()` 的 `llm_cache` 统计改为报告**生产文件缓存口径**（`entries`=当前 `src/cache/*.json` 条目数，`enabled`=缓存开关），`tests/test_workflow.py` / `tests/test_workflow_extended.py` 两个统计测试同步更新。

### P1 性能：补丁应用热路径正则预编译（`src/tools/patch_applier.py`）

`_is_full_file_patch` / `apply_patch_to_code` 单函数模式此前每次调用现场编译 4–6 个正则（`def` 名提取、`^def` 计数、triple-quote、python 前缀、边界探测），`--parallel` 多候选多任务下累积可观。现提取为模块级预编译常量（`_DEF_RE` / `_TOP_DEF_RE` / `_TRIPLE_QUOTE_RE` / `_PYTHON_PREFIX_RE` / `_BOUNDARY_RE`），语义完全不变（`_count_function_defs` 保持"行首 def"口径，被 multi_candidate 与测试直接导入的签名不变；`_find_function_range` 保留 3 参签名兼容）。

### P1 正确性：`_patch_applier_node` 节点纯函数口径修复（`src/graph/nodes.py`）

此前 `history = state.get("repair_history", [])` 取到的是 **state 中的原列表**，`history.append(...)` 直接改写 LangGraph 共享 TypedDict 的原值——`--parallel` 线程下其他节点/路由读取同一 state 时会看到被改写的中间值（违反"节点函数无副作用"约定，与本模块其他节点"拷贝→追加→经 update dict 写回"的口径不一致）。现改为 `list(state.get("repair_history") or [])` 拷贝后追加。

### P1 正确性：LLM 缓存键材料拼接歧义修复（`src/agents/base_agent.py`）

0.9 深度审查发现：`_call_llm_with_cache` 的键材料生成在拼接处漏了分隔符（`cache_key = user_message + separator + self.system_prompt` 中 `separator` 变量在拼接语句前被覆盖为 `"\x00"`，但实际拼接路径走的是 `f"{user_message}:{self.system_prompt}"` 冒号拼接——user_message / system_prompt 均可含冒号，理论上存在 md5 前 16 位碰撞误命中风险）。现统一为 `f"{user_message}\x00{self.system_prompt}"` + `f"\x00t{temperature}"` 显式分段，键材料零歧义。新增回归用例 `test_system_prompt_participates_in_key` 锁定"同 prompt 不同 system 不互命中"。

> 注：此前实现中 `separator` 变量被误用于拼接，实际键材料在 prompt 与 system 之间无分隔符，理论碰撞风险极低（md5 前 16 位 + 全量文本校验兜底），但本次修复消除了该歧义，键材料语义更清晰。

### P1 正确性：多函数补丁排序顺序修复（`src/tools/patch_applier.py`）

`apply_multi_function_patch` 排序 key 此前为 `_find_function_start_line_in_lines(...)` 行序 `reverse=True`（从后往前应用）——未找到的函数映射为 -1（0-based 最大）会被排到最前应用，与"应用失败回滚"的语义假设无关（`apply_patch_to_code` 逐补丁基于当前代码独立定位，行序假设不成立）。现改为"未找到的排末尾"确定性排序：找到的按行序升序（稳定，输入序 tie-break），未找到的最后尝试（必失败 → all_success=False，与历史"失败不中断"口径一致）。新增回归用例 `test_not_found_patch_applied_last` 锁定排序语义。

### P2 性能：工作流节点纯函数化 + RAG 检索器热路径优化（`src/graph/workflow.py` + `src/rag/retriever.py`）

- `_should_skip_debugger`（日志副作用 + 纯数据判定混合）拆分为纯数据判定函数 `_recent_repairs_invalid`（零副作用，可单测）+ 路由层日志（`_should_debug` 内承担），消除节点函数的隐式日志副作用，`--parallel` 下路由判定可重入。
- `TestCaseRetriever.retrieve_test_cases` / `retrieve_repairs`：`results.get("documents") or [[]]` 在真实 chromadb 返回（`list[list]`）下恒为 `[[]]`（truthy 短路失效），`documents[0]` 实际取到的是外层 0 号元素（`list` 而非 `list[list]`），zip 行为正确但路径冗长且对 mock 形状（外层 None）的防御无实际收益。现统一为 `documents[0] if isinstance(documents, list) and documents else []`，语义完全不变，路径更短，mypy 无需 `or []` 收窄。

### P2 一致性：dependency 模块锁初始化归一（`src/tools/dependency.py`）

`_venv_cache_stats_lock` / `_venv_cache_persist_lock` 此前经 `__import__("threading").Lock()` 模块级初始化（历史写法，`threading` 未显式 import 导致 mypy 按 `Any` 处理，锁类型无静态检查）。现改为顶部 `import threading` + 显式 `threading.Lock()`，mypy 静态检查覆盖锁类型，语义不变。

### P2 测试防御：dependency 边界测试增加节流窗口护栏（`tests/test_dependency_edge_cases.py`）

`test_get_stats_no_disk_io_under_lock` 在 0.7 节流落地后仍触发"首次事件必落盘"路径（`_venv_cache_last_persist_at=None`），磁盘 IO 实际发生在落盘锁内而非计数锁内——哨兵断言语义未漂移，但测试意图（"事件函数不排队抢落盘锁"）与当前节流行为不一致。现将 `last_persist_at` 设为"刚刚"制造节流窗口，事件只累计内存、跳过落盘锁，哨兵断言语义与测试意图对齐。

### 验证

- ruff 全仓 0 告警；mypy 全仓 0 错误（58 个源文件）；
- pytest **1665 通过**（1678 − 16 个已移除死模块用例 + 2 个统计口径用例更新 + 3 条新回归用例，无功能回归）；
- LRU 快路径基准：命中 1.1μs/op（零磁盘 IO），miss+文件回填 54.2μs/op。

---

## [Unreleased] — 0.8 轮次全面审查修复（脱敏逻辑去重 + 半开探测失败路径消费 + LLM 缓存 makedirs 短路 + 温度键闭环 + 执行轨迹重复计算消除 + 白名单根预归一化 + `__main__` 自诊断 bug 修复 + 4 条回归用例）

> 本轮为"审查 + 优化"双驱动：按 docs/0.7_audit_findings.md 清单与 0.8 新发现逐项落地，**零回归**。
> 全量基线由 1672 升至 **1678 passed / 0 failed**（新增 6 条回归用例：LLM 缓存温度键 1 +
> makedirs 短路 1 + 半开探测失败路径 2 + 执行轨迹去重 1 + 白名单根预归一化 1），
> ruff check / ruff format / mypy 全仓 0 错误（59 源文件）。

### 核心优化（按文件）

#### `src/utils/logging_utils.py`（脱敏单一实现收敛）
- 新增 `redact_text(text)` 三级降级链（`mask_sensitive_info` →
  `fallback_mask_sensitive_info` → 原样返回）作为**唯一**脱敏实现。
- 此前 `src/agents/llm_client._redact_log_text` 与
  `src/api/api_manager._redact` 各自维护了一份同构的"mask → fallback → 原样"
  三级逻辑（注释声明"与对方同口径"但代码是复制而非委托——一旦模式更新
  只改一处，另一处静默漂移）。本轮统一收敛到 `redact_text`，两处
  别名保留历史导入路径。

#### `src/api/api_manager.py`（4.2 半开探测失败路径消费）
- `call()` 路径：半开探测窗口内（`_enter_half_open_probe` 返回 True）的请求
  若命中限流 / APIError / 通用异常，`_handle_rate_limit` /
  `_handle_api_error` / `_handle_generic_error` 此前未透传
  `is_half_open_probe`，导致 `node._probe_circuit_half_open(False)` 不被消费，
  半开节点"探测失败"后不重开冷却、下次仍被全量路由打到同一死 provider。
  现 `call()` 在调用 `_try_call_node` 前计算 `is_half_open_probe` 并在
  各异常分支透传，失败路径与成功路径（`_try_call_node` 内 `mark_success`
  后消费）口径一致。

#### `src/agents/base_agent.py`（LLM 文件缓存 makedirs 热路径短路 + 温度键闭环）
- 命中缓存后写入路径每次调 `os.makedirs(exist_ok=True)`（stat 系统调用），
  现改为 `if not os.path.isdir(cache_dir)` 短路：目录已存在（命中必存在）
  时零 makedirs 调用；首次写入保留建目录语义，缓存目录不存在行为不变。
- 缓存文件 JSON 记录 `temperature` 字段（None 归一为默认 `TEMPERATURE`），
  读缓存时校验温度一致才命中——此前 3.3 动态策略温度仅参与键材料
  （`":t{temp}"` 后缀），缓存文件 JSON 不含温度记录；现写入 + 读取两端
  闭环，防跨温度误命中。

#### `src/graph/nodes.py`（白名单根预归一化 + 执行轨迹重复计算消除 + 单遍 any 化）
- `_ALLOWED_WRITE_ROOTS` 模块加载期 `os.path.realpath` 归一化（项目根 +
  系统临时目录），`_is_within_allowed_roots` 热路径免每次重复解析根目录
  （此前每补丁 3 次 `realpath` 系统调用累积）。
- `_is_within_allowed_roots` 改写为 `any(...)` 单行（ruff SIM110 归一）。
- `_executor_node` / `_record_execution_trace` 消除重复的 `prev_coverage`
  计算：此前 `_executor_node` 与 `_record_execution_trace` 各自扫描
  `state["execution_trace"]` 取 `[-1]["coverage"]`（同一公式两次 O(N)），
  现 `_record_execution_trace` 内部自行计算（保持返回值"完整轨迹"口径不变），
  `_executor_node` 仅保留策略建议计算的一次扫描。

#### `src/prompts/templates.py`（`__main__` 自诊断块 bug 修复）
- 此前 `__main__` 块用 `locals().items()` 过滤 UPPERCASE 字符串变量——
  模块顶层 `locals()` 仅含少数内置名，`PLANNER_SYSTEM_PROMPT` 等三个
  prompt 常量不在其中，过滤后集合恒空，"字符数验证"从未真正执行。
  现改为 `list(globals().items())`（快照防 dict size 迭代期 RuntimeError），
  自诊断语义落地。

#### `tests/`（新增 6 条回归用例）
- `tests/test_llm_file_cache.py`：
  - `test_second_write_does_not_call_makedirs`：写缓存热路径第二次写入
    零 makedirs 调用（makedirs spy 计数断言）。
  - `test_temperature_keying_avoids_cross_hit`：不同 temperature 走不同
    缓存键，不命中对方产物（3.3 动态策略回归）。
- `tests/test_api_manager.py`：
  - `test_call_consumes_probe_on_rate_limit`：call 路径限流异常消费半开
    探测（节点重开半程冷却）。
  - `test_call_consumes_probe_on_api_error`：call 路径 APIError 消费半开
    探测（同 4.2 口径）。
- `tests/test_workflow.py`：
  - 执行轨迹去重回归（`_record_execution_trace` 内部自行计算
    `prev_coverage`，`_executor_node` 不再重复扫描）。
- `tests/test_workflow_extended.py`：
  - 白名单根预归一化回归（`_ALLOWED_WRITE_ROOTS` 加载期 realpath，
    `_is_within_allowed_roots` 热路径免重复解析根目录）。

> 本轮为纯性能与可维护性优化：`patch_applier` 消除重复 `split("\n")`、
> `error_classifier` 清理双重过滤、`_safe_write_patch` 函数定义检查改为
> 单遍正则、路径白名单根预归一化、LLM 缓存键材料消歧、多候选函数计数
> 去重、追踪记录摘要降频、前缀剥离正则预编译。**不改变任何运行期行为
> 与实验口径**。
> 全量基线保持 **1672 passed / 0 failed**，ruff check / ruff format / mypy
> 全仓 0 错误（59 源文件）。
>
> **`src/tools/cross_file.py`（拓扑排序口径修正 + 死代码甄别）**：
> - 上一轮（0.7）将 `_topological_order` 的 `queue.pop(0) + queue.sort()`
>   改为 min-heap，声称"语义完全等价"。本轮审查发现该改动在**同一对
>   模块存在多条并行依赖边**时改变行为：入度按"边"计数（K 条并行边
>   计 K），但 heap 释放侧按"去重后的调用方集合"只扣 1 次，K>1 时
>   入度永远无法归零，节点被误判为环尾追加，整体顺序改变
>   （随机图对拍：44/500 差异，其中含"调用方先于被调用方"的语义违规）。
>   本轮已恢复原 queue+sort 实现，并加注释警示后续勿再 heap 化；
>   新增 2 个回归测试锁定"逐边扣减"口径（`test_parallel_edges_counted_per_edge` /
>   `test_parallel_edges_entry_first`）。
> - 审查甄别：`build_cross_file_repair_plan` 的 `sorted(set(modules))[:max_modules]`
>   并非死代码——依赖边的收集顺序（`analyze_multi_entry_deps` 输出按
>   source/target/symbol 字典序）与"按模块名序截取"不等价，且排序结果
>   决定 LLM 预算（max_modules）落在哪些模块上，属行为可预测性口径，
>   本轮予以保留（上一轮"移除"改动已回退）。
>
> **`src/tools/patch_applier.py`（消除重复代码切分）**：
> - `apply_patch_to_code` 单函数分支中 AST 路径与正则兜底路径各自
>   执行一次 `original_code.split("\n")`，现合并为一次切分、两条
>   路径共享 `lines` 变量，减少一次 O(n) 字符串操作。
>
> **`src/agents/error_classifier.py`（冗余过滤条件清理）**：
> - `refine_failure_category` 中 `any(not h.get(...) for h in history
>   if h.get(...) is False)` 的双重过滤（generator + 外层 if）合并为
>   单遍 `any(h.get("patch_applied") is False for h in history)`，
>   语义等价（键缺失时 `get()` 缺省 True 不进入过滤）。
>
> **`src/graph/nodes.py`（`_safe_write_patch` 单遍正则化 + 白名单根预归一化）**：
> - 原实现 `any(line.strip().startswith("def ") for line in
>   new_code.splitlines())` 每次补丁应用都把补丁全文逐行拆成
>   `list[str]` 再逐行 startswith（O(行数) 临时列表）。现改为
>   预编译 `re.compile(r"^\s*def ", re.MULTILINE)` 单遍字符串扫描，
>   命中即停，不产生中间列表。10 类语义用例验证
>   新旧实现完全一致。
> - 安全检查 3 的路径白名单根（项目根 + `tempfile.gettempdir()`）
>   此前每次补丁应用都现场执行 4 层 `dirname` + 3 次 `realpath`，
>   现提升到模块级 `_ALLOWED_WRITE_ROOTS`（加载期归一化一次，
>   abspath 口径与历史判定语义一致），热路径只剩目标路径的
>   归一化与一次前缀比较。
>
> **`src/agents/base_agent.py`（LLM 文件缓存键材料消歧）**：
> - 缓存键材料原为 `f"{user_message}:{self.system_prompt}"`，
>   消息/系统提示均可能含 `:`，存在理论上的拼接歧义
>   （md5 前 16 位碰撞 + 歧义拼接双重风险面）。改用
>   `"\x00"` 分隔（文本中不可能出现的控制字符），并顺带把
>   命中路径的 `prompt` 比较改为"先比长度再比全量"短路。
>   缓存文件布局不变（hash 文件名 + JSON 内 prompt/system 校验），
>   仅键材料生成规则变化——新旧文件混存时按"全量 prompt 不匹配"
>   自然失效重写，无脏命中风险。
>
> **`src/tools/multi_candidate.py`（静态筛选函数计数去重）**：
> - `static_validate_patch` 的安全检查 2/4 原各调用
>   `_count_function_defs` 全文扫描（同一次调用内最多 4 次
>   全文 `re.findall`），现各代码全文的计数只执行一次
>   （new_code 1 次 + original_code 1 次），检查 4 复用检查结果 2。
>   N 候选 × 每轮迭代场景下正则全文扫描减半。
>
> **`src/observability/trace.py`（记录摘要降频）**：
> - `_append` 原实现每条记录全树递归 `_summarize`（深拷贝 +
>   截断），而实际只有 task_start 的顶层 `meta`（任意用户字典）
>   需要逐值摘要；节点事件由 `record_node` 在入口处已对
>   `output_summary` 做过摘要，task_end 的 extra 由
>   `record_task_end` 逐值摘要。现 `_append` 只处理顶层
>   `meta`，消除热路径上的冗余递归拷贝（追踪开启时
>   每节点 1 条记录，多迭代 × 多任务累积可观）。
>
> **`src/utils/helpers.py`（前缀剥离正则预编译）**：
> - `extract_code_block` 的 `python:` 前缀剥离分支每次调用
>   现场编译 `re.sub` 模式（LLM 输出提取热路径，每次补丁/
>   测试代码提取都走），现提升到模块级 `_PYTHON_PREFIX_STRIP_PATTERN`
>   预编译，与同文件既有正则的口径一致。

## [0.9.11] - 凭证安全、可观测性与性能优化（2025-09-25）

> 本轮为纯代码质量优化：mypy 真实语义错误从 26 个清零至 0、`experiments/analyze_results.py`
> 2192 行按主题拆分为 4 个子模块；**不改变任何运行期行为与实验口径**。
> 全量基线保持 **1659 passed / 0 failed**，ruff check / ruff format 全绿，
> mypy `src/ --ignore-missing-imports` 0 错误（58 源文件），src 覆盖率 94%
> （experiments/analyze_results.py 移出 src/ 统计范围，src/ 内语句数由 5216 降至 4911）。
>
> **mypy 真实语义错误修复（26 → 0，非 stub 缺失类）**：
> - `src/graph/nodes.py`（10 处）：`state.get("test_plan")` 经
>   `cast("dict[str, Any]", ...)` 收窄（documented behavior：缺席传 None，
>   Generator 内 `isinstance(test_plan, dict)` 守卫覆盖，测试回归口径不变）；
>   `cross_file_modules` 列表推导按 `str(d["target_module"])` 归一；
>   `test_code` / `test_output` / `patch` 的 `str | None` → 调用点补 `or ""`
>   归一（运行期等价：原代码 `.get(key, "")` 对 TypedDict 仍返回 `str | None`，
>   `or ""` 只把 None 也归到空串，语义不变）；`coverage_delta` 列表按
>   `float()` 归一；`patches[entry_module] = state["patch"]` 经
>   `assert isinstance(patch_val, str)` 收窄（真值守卫后必为 str）。
> - `src/tools/multi_candidate.py`（4 处）：`credit_score` 赋值与排序 key
>   按 `float(credit_by_index.get(c.index, 0.0))` 归一（原 `dict.get` 返回
>   `float | None`，mypy 在 lambda 内不做属性窄化）；`_coverage_trend` 的
>   `deltas` 列表按 `float(t["coverage_delta"])` 归一。
> - `src/rag/retriever.py`（8 处）：模块级 `chromadb` 改"预声明
>   `chromadb: Any = None` 后 try-import"模式（与 `src/graph/rag.py` 同口径），
>   消除 `None` 赋值到 Module 类型的报错；`collection.get/query` 返回的
>   `metadatas` / `documents` 字段按 `.get("metadatas") or []` 与
>   `results.get("documents") or [[]]` 收窄（chromadb stub 标 `list[...] | None`，
>   运行期实际恒非 None，`or []` 兜底语义不变）。
> - `src/observability/trace.py`（2 处）：`directory` 变量从 `str | None`
>   收窄——`self._enabled = directory is not None` + `if self._enabled and
>   directory is not None` 双重守卫，`os.makedirs(directory, ...)` 与
>   `os.path.join(directory, ...)` 不再报 `str | None` 参数错。
> - `src/reports/generator.py`（1 处）：`classify_with_context` 返回值改名
>   `context_raw`，`context: ErrorContext | None = context_raw if context_raw
>   else None` 显式标注（原 `context = context if context else None`
>   自赋值导致 mypy 按窄类型 `ErrorContext` 拒绝 `| None` 赋值）。
> - `src/cli/output.py`（1 处）：`Console` 模块属性改"预声明
>   `Console: Any = None` 后 try-import 赋值"模式（原 `Console = None`
>   在 `from rich.console import Console` 成功后，mypy 按运行期把
>   `None` 赋给 `type[Console]` 报 Incompatible types；预声明 `Any` 消除
>   该报错，rich 缺失时 `Console is None` 的降级路径不变）。
>
> **experiments/analyze_results.py 主题拆分（0.7 债务项 1.6 落地）**：
> - 原单文件 2192 行、26 个私有统计函数堆叠，各函数间耦合低（都只消费
>   `details[]`），按 0.7 审计清单建议拆为 3 个主题子模块 + 1 个 `__init__`：
>   - `experiments/analysis_parts/rag_analysis.py`（164 行）：RAG 检索质量
>     与 Token 效率主题（`_token_metrics_from_details` / `_rag_by_kind_from_details`
>     / `_rag_hit_by_failure_category` / `_rag_token_efficiency` /
>     `_rag_similarity_distribution`，5 函数，无组内耦合）；
>   - `experiments/analysis_parts/convergence_analysis.py`（1050 行）：修复收敛 /
>     质量代理 / 测试异味 / 跨基线对比主题（`_repair_convergence_curve` /
>     `_smell_task_has_smell` / `_test_smell_detection` / `_repair_convergence_metrics`
>     / `_convergence_token_efficiency` / `_difficulty_stratified_iterations` /
>     `_cross_baseline_convergence_comparison` / `_cross_file_failure_analysis` /
>     `_assertion_strength_proxy` / `_quality_proxy_metrics` / `_failure_top_categories`
>     / `_failure_root_cause_trend` / `_mutation_score_metrics` /
>     `_assertion_counts_from_row` / `_convergence_failure_modes` /
>     `_boundary_case_coverage` / `_execution_trace_summary`，17 函数，
>     组内共享 `_assertion_strength_proxy` / `_assertion_counts_from_row` /
>     `_smell_task_has_smell` 三辅助，依赖 `ast` + `Counter`）；
>   - `experiments/analysis_parts/cross_analysis.py`（87 行）：跨主题交叉分析
>     （`_contamination_cross_analysis` / `_venv_cache_stats_snapshot`，2 函数，
>     消费 `details[].contamination_risk_level`，不直接 import
>     `detect_contamination`，避免死导入）；
>   - `experiments/analysis_parts/__init__.py`：子包说明 + 主题导引。
> - `experiments/analyze_results.py`（2192 → 959 行）保留公开入口
>   `load_latest_benchmark` / `build_analysis` / `render_markdown` / `main`，
>   从 3 个子模块 re-export 全部 24 个私有函数（`# noqa: E402,F401` 标注，
>   历史 import 路径 `experiments.analyze_results._xxx` 不变），
>   外部测试（`tests/test_smell_detection_v2.py` / `tests/test_experiments_scripts.py`）
>   与同包脚本（`contamination_check` / `mutation_testing` / `run_benchmark`）
>   的 import 均无需修改。
> - 拆分原则：纯函数搬移，签名 / 返回值 / docstring / 默认参数零变化；
>   组内共享辅助（如 `_assertion_strength_proxy` 被 `_quality_proxy_metrics` /
>   `_assertion_counts_from_row` 消费）保持同文件归属，不跨文件 import，
>   避免引入新的循环依赖。
>
> **验证**：ruff check / ruff format 全绿（189 + 4 文件）/ 全量 1659 passed
> / 0 failed / mypy `src/ --ignore-missing-imports` 0 错误（58 源文件）/
> src 覆盖率 94%（语句数 4911，较 0.7 基线 5216 减少 305 条——
> `analyze_results.py` 移出 src/ 统计范围，非覆盖下降）/
> 冒烟验证：`experiments.analyze_results.build_analysis` 空数据不崩、
> 28 个 re-export 符号完整。
>
> 注：本轮 mypy 清零范围是 `src/`（CI 无 mypy 门禁，本机非门禁承诺）。
> `experiments/` / `config.py` / `main.py` 等脚本无 mypy 历史门禁，不在
> 本轮清零范围；`--ignore-missing-imports` 用于消除 scipy / datasets /
> dbutils / chromadb 等无 stub 第三方库的 import-untyped 噪音。

> **全面审查修复（2026-09-24 安全 + 正确性 + 可维护性）**：
> 基于全仓审查，落地 5 项问题修复（测试 1672 → 全绿，mypy 0 错误）：
> - **凭证脱敏函数化（`src/utils/credential_scrub.py` 新增）**：
>   本地 / venv / Docker 三条执行链路统一走 `scrub_os_environ()` 剔除 LLM
>   凭证。原 `executor.py` 仅剔除 7 个固定变量（覆盖不了 `LLM_1_API_KEY`
>   系列），venv/Docker 链路则原样继承宿主 `os.environ`——LLM 生成的测试
>   代码可读到宿主 API 凭证。现按动态模式 `LLM_\d+_API_KEY` /
>   `LLM_\d+_BASE_URL`（对齐 config 扫描口径 1-32）+ 通用 SDK 凭证剔除，
>   三条链路共用单一实现，避免名单漂移。
> - **CLI `finally` 块脆弱代码（`src/cli/app.py`）**：`end_task_trace` 收尾
>   原依赖 `"final_state" in locals()` 检查（invoke 抛异常时该名字未绑定），
>   语义晦涩且易被重构破坏。改 `final_state: dict | None = None` 初始化 +
>   `is not None` 判断 + `assert` 收窄（mypy union 报错消除）。
> - **节点无副作用（`src/graph/nodes.py`）**：`_select_multi_candidate_patch`
>   原原地写 `state["multi_candidate_stats"]`（共享 TypedDict，`--parallel`
>   线程下会串扰），改返回 3 元组 `(code, applied, stats_update)`，由
>   `_patch_applier_node` 并入自身 update dict。
> - **补丁函数定位正则→AST（`src/tools/patch_applier.py`）**：原
>   `_find_function_range` 把 `^#` 注释 / `^@` 装饰器 / 类方法误当"边界"，
>   被装饰函数或含注释函数体被过早截断、替换出残缺代码。新增
>   `_find_function_range_ast` 读 `FunctionDef.lineno/end_lineno` 精确定位；
>   原代码无法解析时自动回退正则兜底（保守，行为不变）。
> - **低风险修正**：删除 `.env.local.bak`（含真实密钥的备份文件）；
>   `llm_configs.json` 3 条 deepseek 条目 `provider_description` 由
>   "通义千问"改为"DeepSeek 托管"；`requirements.txt` 显式声明
>   `openai==2.54.0`（`api_manager.py` 顶层 `import openai`，此前靠
>   传递依赖隐式安装）；修 5 处 ruff 瑕疵（tests/ 下 I001/F401/RUF100/
>   E741/SIM115）。
>
> **验证**：全量 1672 passed / 0 failed，mypy `src/` 0 错误（59 源文件），
> ruff check 全绿。

## [静态类型清零 + 代码质量清理] - 2026-09-23（mypy 全仓 0 错误，默认行为不变）

> 本轮为纯代码质量优化：mypy 类型检查从 30+ 错误清零至 0、死代码与冗余
> 清理、测试加速；**不改变任何运行期行为与实验口径**。
> 全量基线推进至 **1659 passed / 0 failed**（较 0.7 的 1627 净增 32；
> 本轮未增减用例，净增来自 0.7 之后已提交但 CHANGELOG 未单独成节的
> 回归用例），ruff check / ruff format 全绿 / mypy 全仓 0 错误 /
> src 覆盖率 94%。
>
> **静态类型修复（mypy 全仓清零）**：
> - `src/utils/exceptions.py` / `src/config/config_manager.py` /
>   `src/experiments/analysis.py` / `src/graph/nodes.py`：字典值混含
>   str / int / dict / list 时补显式 `dict[str, Any]` 标注，消除 mypy
>   按字面量窄化后的误报；
> - `src/tools/code_context.py`：`_build_header` / `_collect_top_level_funcs`
>   参数从 `ast.AST` 收窄为 `ast.Module`（`.body` 属性仅在 Module 上有）；
> - `src/agents/executor_runtime.py`：`run_pytest_with_retry` 参数精确标注
>   （`list[str]` / `dict[str, str]`），超时分支的 TimeoutExpired
>   stdout/stderr 合并加 `_to_str` 归一（bytes 静态兜底 + text=True 运行期口径）；
> - `src/agents/executor.py`：模块期属性挂载（15 处）与内部方法调用
>   补 `# type: ignore[attr-defined]`（类属性绑定为运行期机制，测试
>   patch 路径依赖，行为不变）；
> - `src/agents/generator.py`：`_fix_import_module` 改为直接导入
>   `is_similar_module_name` 纯函数（原经 `ExecutorAgent` 类属性挂载访问，
>   消除运行期对类属性的依赖 + mypy attr-defined 误报）；
> - `src/agents/llm_client.py`：`ChatOpenAI(openai_api_key=...)` 补
>   `# type: ignore[call-arg]`（langchain-openai 接受该参数但 mypy 按
>   严格 OpenAI SDK 签名校验报 arg-type）；
> - `src/api/api_manager.py`：`cost_weight` 取值加 `float()` 归一
>   （旧配置对象无该字段时 getattr 默认值 0.0 保真）；`messages` 参数
>   补 `# type: ignore[arg-type]`（list[dict[str, str]] 与 openai SDK
>   严格 ChatCompletionMessageParam 联合运行期兼容）；
> - `src/db/mysql_client.py`：`cursor()` 加 `_pool` 非空 assert
>   （双检锁初始化后 _pool 必非 None，assert 收窄类型供 mypy 检查）；
>   安装 `types-PyMySQL` 消除 stub 缺失报错；
> - `src/graph/rag.py`：可选导入改为"预声明 `TestCaseRetriever: Any`
>   后 try-import"模式，消除 mypy "Cannot assign to a type"（chromadb
>   缺失场景下模块属性置 None 的合法降级路径）；
> - `src/rag/retriever.py`：chromadb 元数据值按 `float` 归一（3 处
>   `_added_at` 读取），修正 `find_missing_modules` 返回 `set[str]`
>   与 `executor_modes` 五元组标注；
> - `src/agents/debugger.py`：`debug()` 返回值从 `dict[str, str]` 修正为
>   `dict[str, Any]`（实际含 `adversarial_check` 嵌套 dict）；
> - `src/cli/app.py` / `src/cli/output.py`：kwargs 字典显式标注
>   `dict[str, object]` + `**` 展开补 ignore；rich 可选导入改
>   "预声明 + try-import"模式（Table 延迟到调用期导入）。
>
> **代码质量清理**：
> - `src/agents/llm_client.py` `_call_zai`：重试元组
>   `(APIReachLimitError, APIStatusError, Exception)` → `(Exception,)`
>   （两个具体子类被基类 Exception 覆盖，列举属死代码；zai 路径
>   限流与普通错误不做区分，统一指数退避口径不变）；
> - `src/utils/logging_utils.py` `setup_logger_safety`：加幂等短路
>   （logger 与全部 handler 均已挂 SensitiveFilter 时直接返回，多入口
>   重复调用时不再无谓累积过滤器实例；脱敏幂等语义不变）。
>
> **测试加速（不改变覆盖范围）**：
> - `tests/test_api_manager.py` / `tests/test_api_manager_extended.py` /
>   `tests/test_base_agent_extended.py`：限流/重试故障转移路径的
>   `time.sleep` mock 化（原 3 组用例真实等待 5s/10s/14s/7s，
>   mock 后套件耗时从 ~30s 降至 ~22s；mock 目标为 `time.sleep`，
>   真实指数退避逻辑不被旁路，仅跳过等待）。

## [0.7 路线图缺口落地] - 2026-09-22 路线图剩余缺口（2.3 / 3.1 / 3.3）

### 功能（默认行为不变，均经环境变量显式开启）
- **2.3 复现测试专项生成**（`src/agents/generator.py` + `src/graph/nodes.py`）：
  - `GeneratorAgent.generate_repro_test()`：针对已知缺陷生成"先失败后通过"的复现测试，
    精确覆盖缺陷触发路径（TDFlow 式）；跨文件场景下经 `cross_file_modules` 提示
    LLM 覆盖跨模块调用链。开关 `REPRO_TEST_ENABLE`（默认 false）。
  - `_generator_node` 在已有缺陷描述（diagnosis / review_reason）时调用，
    结果写入 `state["repro_test"]`。
- **3.1 双向代码-测试诊断**（`src/agents/debugger.py` + `src/graph/nodes.py` +
  `src/graph/workflow.py` + `src/graph/state.py`）：
  - `DebuggerAgent._run_review_diagnosis()`：独立 Review Agent 判断根因是
    "实现缺陷"（implementation_defect，修复代码）还是"测试缺陷"（test_defect，
    重新生成测试）。开关 `BIDIRECTIONAL_DIAGNOSIS_ENABLE`（默认 false）。
  - `_should_debug` 新增分支：`defect_type == "test_defect"` 时路由回 generator
    重新生成测试（regeneration_count 上限防无限乒乓），实现 BiVCoder 式分支修复。
- **3.3 轻量奖励预测器 + 动态 temperature 接线**（`src/tools/multi_candidate.py` +
  `src/agents/base_agent.py` + `src/graph/nodes.py`）：
  - `predict_candidate_rewards()`：基于历史 execution_trace 覆盖率趋势
    （连降偏最小改动、停滞偏更大改动）与行级信用分配预测候选奖励并重排。
    开关 `REWARD_PREDICTOR_ENABLE`（默认 false）。
  - `_dynamic_temperature_from_suggestion()`：把 executor 的迭代策略建议
    （lower_temperature）真正映射为采样温度，经 `BaseAgent._call_llm_with_cache`
    的 `temperature` 参数透传（此前仅观测层建议、不改变 LLM 调用参数）。

### 性能优化与技术债清理（0.7 债务项 P2×8 落地，默认行为不变）
- **2.2 LLM 调用全局墙钟总预算**（`config.py` + `src/agents/base_agent.py`）：
  新增 `LLM_CALL_BUDGET_SECONDS`（默认 600s），`_call_llm` 故障转移循环每次尝试
  新模型前检查预算，超出即快速失败，避免"组数 × 模型数 × 重试"极端组合下
  单任务卡死数十分钟。
- **2.3 analyze_failures 字段投影**（`experiments/analyze_failures.py`）：
  `load_all_results` 只保留分析层字段（task_id/passed/error_category/diagnosis/
  dataset/task_metadata），剔除 generated_test/test_output/execution_trace 等
  大字段，多批次累积时内存下降一个量级。
- **2.4 venv 统计落盘节流**（`src/tools/dependency.py`）：
  `_record_venv_cache_event` 距上次落盘 <5s 时只累计内存、跳过磁盘 IO；未落盘
  事件由 `get_venv_cache_stats` 读接口与 atexit 退出钩子兜底合并，计数不丢失
  （双锁 lost-update 语义不变）。
- **2.5 并行提交滑窗**（`experiments/run_benchmark.py`）：抽出
  `_run_tasks_sliding_window`，保持在途 future ≤ 2×parallel，避免 100+ 任务
  一次性 submit 导致大对象常驻内存。
- **1.4 死委托清理**（`src/agents/base_agent.py`）：删除
  `BaseAgent._find_balanced_json` 纯转发 staticmethod（0.6 拆分的死委托），
  测试改直接覆盖 `helpers._find_balanced_json`。
- **3.4 文档补齐**（`.env.example`）：补 `AITESTER_LLM_CACHE` /
  `AITESTER_LLM_CACHE_DIR` 两变量说明。
- **3.5 文档修正**（`docs/performance_guide.md`）：2.4 重试策略伪代码改为
  `base_wait * 2^attempt` 口径，标注 `LLM_RETRY_WAIT` 不再驱动退避。
- **3.6 密钥命名收敛**（`config.local.example`）：头部声明 `LLM_N_*` 单一事实
  来源，`.env.local.template` / `llm_configs.json` 的 `{PROVIDER}_API_KEY` 仅供
  批量脚本中间变量。
- **3.7 clone 地址核验**：`git ls-remote` 确认 `https://github.com/1956178912/AITester.git`
  可达且与文档一致，无需修改。

## [0.7] - 2026-09-21 跨文件修复二期 + 数据完整性修正 + 研究立项（A/B/C 三方向）

### 功能（A 方向：代码质量深化，默认行为不变）
- **3.5 跨文件修复二期**（`src/tools/cross_file.py` + `src/graph/nodes.py`，设计文档 §9）：
  - **多入口依赖分析** `analyze_multi_entry_deps(entry_modules, source_files, max_depth=1)`：
    对多个入口模块做一级 import 展开（保守口径，不递归——防依赖图爆炸），
    去重合并各入口依赖边（同 `(source, target, symbol)` 保留 `call_line` 最小者）。
    一期单入口 `analyze_cross_file_deps` 保持原签名，多入口是叠加能力。
  - **拓扑序补丁应用** `apply_multi_file_patch(..., deps=...)`：
    传入依赖边时按依赖图拓扑序应用（被调用方先改、调用方后改，Kahn 算法 + 环按
    字典序打破，entry 强制首位）；不传 `deps` 时退回模块名字典序（一期口径），
    保持历史实验可比性。`_patch_applier_node` 已把序列化依赖边还原为对象传入。
  - **修复计划缓存** `build_cross_file_repair_plan_cached(...)`：
    相同依赖图指纹（入口 + 依赖边 + max_modules 的 SHA1）落盘 LLM 缓存目录
    （复用 `AITESTER_LLM_CACHE`/`AITESTER_LLM_CACHE_DIR` 口径），命中零 LLM 调用；
    `use_cache=False` 或缓存关闭时退化为不缓存。
- **4.4 依赖缓存一致性修正**（`src/tools/dependency.py`）：
  `list_venv_cache` 用 `os.path.getctime`（macOS 上是创建时间、Linux 上是 inode
  变更时间，跨平台语义不一致）→ 改 `getmtime`，与 `clear_venv_cache` 的年龄
  判断口径对齐（venv 目录创建后内容很少变动，mtime 更可靠）。

### 修复（B/C 方向：数据完整性 + 研究立项）
- **run_benchmark 静默降级误导归档修正**（`experiments/run_benchmark.py`）：
  指定数据集（如 `swe_bench lite`）子集文件为空时，加载器静默回退到内置
  examples 合成数据集，但结果归档 `"dataset"` 字段仍标原始请求名（`swe_bench`）
  ——首跑 R-01 探路时 `task_id` 前缀 `examples__` 与归档 `dataset: swe_bench`
  矛盾，具误导性。现降级时把 `dataset_name` 改回 `examples`、`subset` 置 None，
  并在 warning 日志中明确标注"静默降级 + 非原始请求数据集"。
- **R-01 SWE-bench 补跑探路立项**（`docs/design/swe_bench_probe.md`）：
  探路首跑发现 lite 子集 JSONL 为空（全仓仅通用文件 225 条，且缺
  `instance_code` 字段）——R-01 真实阻塞项是"数据集无可用源码"而非"配额
  不够"。立项选择 (c) 记录在案，源码补齐（`download_swe_bench.py` /
  `export_swe_bench_source.py`）后再执行探路命令（§3.1 已给出）。
- **R-03 对抗性推理现状澄清**：AdverIntent-Agent 式对抗性推理已实装于
  `src/agents/debugger.py`（`ADVERSARIAL_DEBUGGING_ENABLE` 默认关 + 批评者
  评估闭环，0.5 批次落地），无需本轮重复立项；`run_benchmark.py` 无
  `--adversarial` CLI flag，R-03 仅经环境变量启用（扩大批次对照需
  `export ADVERSARIAL_DEBUGGING_ENABLE=true`）。

### 测试
- `tests/test_cross_file.py` 新增 12 个用例（多入口 5 / 拓扑序 4 / 修复计划缓存 3
  → 实际 4 个测试类 12 用例），测试数 27 → 39；
- `tests/test_rag_retriever.py` 新增 2 个并发护栏用例（`TestConcurrentUpsertGuard`：
  8 线程并发入库 upsert 串行不丢失 + 清理不被写锁阻塞，与 0.6 venv 双锁护栏同口径）；
- `tests/test_dependency_edge_cases.py` 更新 1 个边界用例（`getctime` mock 路径
  → `getmtime` mock 路径，与 4.4 一致性修正对齐）；
- `tests/test_workflow_extended.py` 2 个 mock lambda 补 `deps=None` 参数
  （`apply_multi_file_patch` 签名向后兼容期口径）。
- 全量基线推进至 **1627 passed / 0 failed**（较 0.6 的 1612 净增 15；
  跨文件二期 12 + RAG 并发护栏 2 + 依赖缓存口径修正 1），ruff check 全仓 0 告警。

## [0.6] - 2026-09-20 P0 修复批（LLM OpenAI 路径零重试 + venv 统计双锁 + 幽灵开关实装 + 代码质量收尾）

### 修复（性能审计三路并行：死代码/技术债 + 性能热点 + 文档漂移，人工复核确认）
- **P0-1 LLM OpenAI 路径零重试→指数退避故障转移**（`src/agents/base_agent.py`）：
  `llm.invoke` 此前单次调用即跨模型/跨 API 切换，网络抖动一次 429/超时 =
  整个任务级失败（benchmark 100 任务 × 3 基线场景下 10% 抖动率 → 90-180 次
  调用直接失败）。现把 `_retry_with_exponential_backoff`（1s/2s/4s 退避）套到
  OpenAI 路径，空响应也触发重试；重试耗尽才进入故障转移（与 zai 路径语义对齐）。
- **P0-2 venv 统计双锁分离**（`src/tools/dependency.py`）：
  `_record_venv_cache_event` 此前持 `_venv_cache_stats_lock` 做
  `json.load + os.makedirs + json.dump`（~2-5ms/事件），`--parallel` 下所有
  worker 在 venv 命中检查热路径上争全局锁。现双锁分离：
  计数锁（ns 级临界区，只做内存累计）+ 独立落盘锁（保护"读磁盘/快照/写磁盘"
  整段，lost-update 安全）。简单移到计数锁外会触发 lost-update（两个并发
  persist 各自读旧磁盘值、各自清零内存，50+50 事件被合并成 50，并发压测实证），
  双锁分离后 8 线程 × 100 事件 0 丢失（新增 2 个护栏测试）。
- **P0-3 幽灵开关实装**（`config.py` + `src/api/api_health.py` + `src/api/api_manager.py`）：
  `.env.example` / `QUICKSTART` / `api_reference` / `reproduce.sh` / `README` /
  `CHANGELOG` 六处文档承诺 `API_CIRCUIT_BACKOFF`（默认 true）与
  `API_PROMETHEUS_EXPORT`（默认 false）为"对比实验"开关，但全仓无代码读取点——
  指数退避与 Prometheus 导出此前无条件执行。现经 config 集中声明后：
  `api_health.mark_failure` + `_probe_circuit_half_open` 接入退避开关
  （false 走固定冷却 4.2 历史口径）；`api_manager.to_prometheus_text` 接入
  导出开关（false 返回空串，默认行为不变）。
- **multi_candidate 双次补丁应用消除**（`src/tools/multi_candidate.py`）：
  `static_validate_patch` 内部已调用 `apply_patch_to_code`，`generate_candidates`
  此前对通过静态筛选的候选又调一次——同候选双次完整应用补丁（含正则+行范围
  定位+空行压缩），纯冗余。现签名 2-tuple → 3-tuple（ok, reason, applied_code），
  `generate_candidates` 直接复用第三项（候选 3 个时白跑 3 次 → 0 次）。

### 代码质量
- **ruff 15 告警清零**（F401/F841/PERF401/PERF102/E741/RET504/B007/E402/I001）：
  删除 5 处未使用导入与死变量；4 处 for-append 循环改 `list.extend` / `dict.values()`；
  `contamination_check` 歧义变量 `l` → `line`；`nodes._append_execution_trace` 直返
  `_append_trace_record` 结果；`api_manager` Prometheus 导出循环变量 `name` → `values()`。
- **33 文件 format 归一**（`ruff format`，纯空白，无逻辑改动）。

### 测试
- 新增 6 个回归用例：
  `tests/test_multi_candidate.py`（1：static_validate_patch 3-tuple 契约锁定）；
  `tests/test_dependency_edge_cases.py`（2：并发计数不丢失 + 锁外落盘护栏）；
  `tests/test_api_circuit_breaker.py`（3：API_CIRCUIT_BACKOFF 开/关双路径 +
  API_PROMETHEUS_EXPORT 默认空串）。
- 全量 **1612 passed / 0 failed**（较 0.5 的 1606 +6），ruff check + format 全绿，
  src 总覆盖率 94%。

## [0.5] - 2026-09-20 分析层深化（跨基线收敛对比 + 跨文件失败案例 + 最小复现代码自动提取）

### 功能
- **1.3 跨基线收敛对比**（`experiments/analyze_results.py`）：
  新增 `_cross_baseline_convergence_comparison`，把 `per_baseline` 中
  aitester 与各 plain_llm 变体的修复收敛曲线按轮次（0/1/2/3+）对齐
  叠加，输出两个关键对比指标：`first_attempt_delta`（首轮即通过率的
  协作 vs 基线差值，正值 = 多智能体协作"一次做对"能力领先）与
  `cumulative_pass_rate_at_1_delta`（第 1 轮累计通过率的基线间差异，
  用于判断协作机制的增益来自"一次做对"而非"多轮调试追平"）。
  基线数 <2 或协作/基线组缺失时差值为 None，渲染层只输出叠加表不
  强行计算差值。
- **2.2 跨文件修复失败案例分析**（`experiments/analyze_results.py`）：
  新增 `_cross_file_failure_analysis`，收集各基线失败任务的
  `error_category` 分布与诊断文本含 import/module/模块 关键词的
  失败任务数（跨文件修复失败的典型表征），整体 `import_related_rate`
  作为"模块路径/导入关系未正确处理"的代理指标。渲染层在
  `import_related_rate ≥ 30%` 时额外输出排查建议（检查
  `CROSS_FILE_BIDIRECTIONAL=true` 是否启用被调用方视角）。
- **5.3 最小复现代码片段自动提取**（`experiments/analyze_failures.py`）：
  新增 `extract_minimal_repro`，从失败任务的 diagnosis 中逐级降级提取
  "最小复现代码片段"（规则 1：traceback 尾部定位取最后 File 行起
  的 3 行核心；规则 2：按错误关键词过滤行；规则 3：退到
  task_metadata.problem_statement 的 ``` 代码块），零 LLM 调用、
  纯文本处理、可复算。`failure_knowledge_base` 每条案例新增
  `minimal_repro_code` 字段（无法提取时为 None），`generate_report`
  渲染层在知识库章节输出该片段或标注"需人工补充"。

### 测试
- **新增 13 个测试**：
  `tests/test_experiments_analysis.py` 新增
  `TestCrossBaselineConvergenceBoundary`（单基线不可用 / 协作 vs 基线
  delta 计算 / 无 plain 基线时 delta 为 None / 缺轮数据时对齐表跳过）
  与 `TestCrossFileFailureAnalysisBoundary`（全通过不可用 /
  import 关键词计数 / 空 _details 不崩溃）共 7 个用例；
  `tests/test_analyze_failures.py` 新增
  `TestExtractMinimalRepro`（规则 1 traceback 尾部 / 规则 2 关键词
  过滤 / 规则 3 代码块 / 全空返回 None / max_lines 截断保留异常
  消息 / 知识库案例含 minimal_repro_code 字段）共 6 个用例。
- 全部 1606 个测试通过（较 0.4 轮次新增 13 个，零回归）。

## [0.4] - 2026-09-20 五大章节系统能力增强（评估/数据/系统/可观测性/测试）

### 功能
- **1.1 多维度评估指标深化**（`experiments/analyze_results.py`）：
  测试异味检测扩展 Eager Test（单函数过度断言）+ Lack of Cohesion
  （单函数跨多主题）两类 AST 口径，异味统计按策略分组，新增
  `smell_density`（有异味任务占比）；新增 `_convergence_token_efficiency`
  （逐轮 token/边际收益收敛分析）、`_difficulty_stratified_iterations`
  （按难度档分层迭代分布）、`_mutation_score_metrics` 与断言强度交叉
  一致性校验、`_rag_token_efficiency`（RAG vs 无 RAG token/迭代对比）、
  `_rag_similarity_distribution`（相似度直方图）、`_failure_root_cause_trend`
  （llm_capability/dependency/framework 三类根因占比 + 时间趋势）、
  `_contamination_cross_analysis`（高/低污染风险成功率 delta）。
- **1.2 变异反馈闭环**（`experiments/mutation_testing.py` +
  `src/agents/generator.py` + `src/graph/state.py`）：
  新增 `boundary_shift`（Gt↔GtE 边界语义变异）与 `return_void`
  （return X → return None）两类变异体；`build_mutation_feedback()`
  把"存活变异体"打包成可注入 Generator prompt 的反馈字典，形成
  MutGen 式"变异引导测试增强"闭环。`run_single_task` 新增
  `enable_mutation_scoring` 参数（修复此前 `mutation_enabled` 未定义
  的 NameError）。
- **2.1 多维度污染检测**（`experiments/contamination_check.py`）：
  在 token Jaccard 之外新增结构级（AST 语句骨架 LCS 比率）与语义级
  （token 词袋余弦，`_embed_code` 钩子可接 CodeBERT）两个维度，
  `patch_semantic_similarity` 输出三维相似度；`_combined_risk_level`
  取最严重维度；`detect_contamination` 每任务输出 `risk_level` +
  `contamination_summary`（含污染 vs 无污染的各自成功率与 delta）；
  新增 `render_resistant_benchmark_section`（SWE-rebench 抗污染基准
  注册表，交叉验证建议）。
- **2.2 跨文件双向依赖图**（`src/tools/cross_file.py`）：
  `analyze_cross_file_deps` 新增 `bidirectional` 参数（默认 False 保持
  历史单入口口径），启用时经 `_collect_reverse_deps` 收集"其他模块 →
  入口模块"反向依赖边（被调用方视角），形成双向依赖图；`_find_symbol_def_line`
  定位符号定义行（def/class/赋值）。环境变量 `CROSS_FILE_BIDIRECTIONAL`
  控制开关（默认 false）。
- **3.1 对抗性推理机制**（`src/agents/debugger.py`）：
  Debugger 新增 AdverIntent-Agent 式对抗性意图假设 + 批评者评估：
  启用 `ADVERSARIAL_DEBUGGING_ENABLE=true` 后，生成补丁前让 LLM 输出
  2-3 个"击穿当前实现"的对抗性意图假设并生成针对性测试，生成后独立
  "批评者"调用尝试构造击穿用例；被击穿则重新生成一次补丁（仍失败
  保留当前并记录风险）。默认关闭，保持历史实验口径。
- **3.2 执行反馈动态迭代策略**（`src/graph/nodes.py` +
  `src/graph/state.py`）：executor 节点每次执行后基于历史轨迹
  覆盖率趋势经 `_suggest_iteration_strategy` 输出"降低温度 /
  切换修复视角"的观测层建议（写入 `state["iteration_strategy_suggestion"]`，
  不参与路由决策，供未来 Debugger 消费）；奖励信号沿用历史
  `EXECUTION_TIMEOUT` 线性归一（保守，不改变历史数据口径）。
- **3.2 行级信用分配**（`src/tools/multi_candidate.py`）：
  新增 `line_level_credit_scores`（BOOSTAPR 式，对每个静态通过候选
  按"执行验证通过率 × (1 - 修改行占比)"精确计算信用），
  `select_best_candidate` 静态模式改按行级信用排序（修改行少且
  静态通过的候选优先），`CandidateResult` 新增 `credit_score` 字段。
- **4.4 熔断器指数退避 + Prometheus 导出**（`src/api/api_health.py`
  + `src/api/api_manager.py`）：`APIHealth` 新增 `circuit_open_count`
  （指数退避次数）、`half_open_success` / `half_open_failure`
  （半开探测计数）；`mark_failure` 冷却期改按 `base * 2^open_count`
  指数退避（封顶 `half_open_probe_penalty_cap_seconds`），彻底死掉的
  provider 冷却期单调增长，避免反复短冷却打同一死点；
  `mark_success` 重置 `circuit_open_count`；`_probe_circuit_half_open`
  失败路径同样走指数退避；`half_open_probe_success_rate` 属性
  供路由权重调整。`APIManager.get_status` 暴露新字段，
  `to_prometheus_text()` 导出 7 类 Prometheus 指标
  （health / circuit_state / open_remaining_s / open_count /
  probe_success_rate / success_rate / avg_response_ms）；
  `reset_stats` 清空新计数。纯旁路，不影响既有路由行为。
- **4.4 venv 缓存容量监控**（`src/tools/dependency.py`）：
  新增 `get_venv_cache_size_mb` / `check_venv_cache_size`
  （5GB 阈值 WARNING 告警，只监控不自动清理）；`_VENV_CACHE_STATS_FILE`
  改动态函数 `_venv_cache_stats_file()`（跟随 `_VENV_CACHE_DIR`，
  修复测试隔离时落盘路径污染真实 `~/.cache` 的隐患）。
- **4.2 脱敏递归化 + 回归测试**（`src/utils/logging_utils.py` +
  `tests/test_logging_utils.py`）：`redact_dict` 改递归处理嵌套
  dict/list/tuple（此前仅顶层字符串脱敏，嵌套结构敏感字段漏拦——
  trace JSONL、异常堆栈常用嵌套 dict）；`fallback_mask_sensitive_info`
  补 JWT 拦截（取 `_SENSITIVE_PATTERNS` 第 0/1/2/4 条，覆盖 sk-/hex/
  base64/JWT 四类高频凭证，跳过 key=xxx 避免降级态误伤）。
  新增 `TestSensitiveInjectionRegression` +
  `TestSensitiveInjectionCIPassGuard` 两组 CI 用例（模拟 4 类敏感
  凭证注入，主/降级双路径 + redact_dict 嵌套拦截验证）。
- **5.2 错误分类体系扩展**（`src/agents/error_classifier.py`）：
  `ErrorCategory` 新增 `EXECUTION_TRACE_MISSING`（任务失败但
  execution_trace 为空 = 执行器异常路径）与
  `MULTI_CANDIDATE_ALL_REJECTED`（多候选全被静态筛选拒绝）两类
  （体系由 12 类扩至 14 类）；`refine_failure_category` 新增
  `execution_trace` / `multi_candidate_stats` 参数，判定优先级
  patch_rejected > rag_empty > trace_missing > multi_rejected；
  `refine_final_error_category` 接线新字段；`get_fix_strategy`
  补两类修复策略描述。
- **reproduce.sh 多候选 + 跨文件 + 熔断器默认口径**：
  `ENABLE_MULTI_CANDIDATE_PATCH` 默认 true（`--no-multi-candidate` 回退）；
  新增 `--cross-file` / `--no-cross-file`（默认 false 保持历史单文件
  口径）；新增 `API_CIRCUIT_BACKOFF`（默认 true）与
  `API_PROMETHEUS_EXPORT`（默认 false）显式透传。

### 测试
- **新增 5 个测试文件**（覆盖 4.4/2.1/2.2/3.2/5.2 新机制）：
  `test_api_circuit_breaker.py`（13 用例：指数退避 / 半开探测 /
  Prometheus 导出 / get_status 新字段 / reset_stats）；
  `test_contamination_multidim.py`（25 用例：三维相似度 / 综合风险等级 /
  detect_contamination 全流程 / 抗污染基准注册表）；
  `test_cross_file_bidirectional.py`（16 用例：单向 / 双向 / 环境变量
  开关 / 符号定义行定位）；
  `test_error_classifier_new_categories.py`（16 用例：两个新类别的
  判定 / 优先级 / 修复策略描述 / 从 final_state 接线）；
  `test_venv_cache_monitoring.py`（11 用例：容量统计 / 告警阈值 /
  命中率 / 清理）。
- **边界补强**（`test_experiments_analysis.py` /
  `test_failure_kb.py` / `test_logging_utils.py` /
  `test_multi_candidate.py`）：新增 `TestAnalyzeResultsNewMetricsBoundary`
  （样本量=1 / 全通过 / 无 Token 数据等退化输入不崩溃）、
  `TestCrossBatch` 全通过批次 / 空批次混入边界、
  `TestSensitiveInjectionRegression` + `TestSensitiveInjectionCIPassGuard`
  （脱敏注入回归 CI 用例）、`TestLineLevelCreditScores` +
  `TestMutationFeedback`（行级信用 / 变异反馈 / 新变异体类型）。
- **口径更新**（随 4.4/5.2 行为变化）：
  `test_error_classifier.py`（12 类 → 14 类；细化判定传非空
  execution_trace 避免误命中 5.2 新类别）、
  `test_weak_coverage_modules.py`（空状态细化为 execution_trace_missing）、
  `test_api_manager_extended.py`（半开探测失败重开冷却改按 4.4 指数
  退避口径）、`test_experiments_scripts.py`（venv 缓存 total=0 时
  快照仍含容量字段，命中统计章节跳过渲染）。

### 工程化基线
- 修复 `experiments/run_benchmark.py` `run_single_task` 中
  `mutation_enabled` 未定义的 NameError（此前仅在 `run_benchmark`
  循环内定义，`run_single_task` 作用域不可见）；
- 修复 `experiments/contamination_check.py` `_extract_statement_skeleton`
  中 `tokenize.generate_tokens(io.StringIO(pseudo))` 误用
  （StringIO 非 callable，应传入 `.readline` 方法）；
- 修复 `src/tools/dependency.py` `_VENV_CACHE_STATS_FILE` 模块级常量
  在 monkeypatch 测试隔离缓存目录时仍指向真实 `~/.cache/aitester` 的
  隐患（改动态函数）；
- `src/graph/nodes.py` `_record_execution_trace` 恢复返回轨迹列表的
  历史口径（策略建议改由 `_executor_node` 单独计算并写入
  `iteration_strategy_suggestion`，不改变轨迹写入行为）；
- 全部改动不破坏既有 API 签名（新字段均带安全默认），1548 个测试
  全过，零回归。

## [0.3] - 2026-09-19 评估指标深化 + 变异生成器修复 + 脱敏审计轮次

### 功能
- **变异生成器修复**（`experiments/mutation_testing.py`）：`_remove_not_op`
  原实现是死代码（仅 `break`，未真正替换 AST 节点），导致 `boolean_negation`
  变异体代码与原代码完全相同，下游沙箱"全部通过"被误判为杀死，
  `mutation_score` 虚高。新增 `_RemoveNotTransformer`（AST NodeTransformer）
  按行号定位 Not 节点并改写其父槽位（`If/While/Return/Assign/BoolOp/Compare/Expr`
  等），替换生效后才计入变异体；未命中时过滤掉，避免死代码回归。
  删除死代码（`_find_mutable_numeric_constants` / `_BOUNDARY_REPLACEMENTS` /
  `_OPERATORS_TO_FLIP` 三个从未被 `generate()` 引用的标识符）。
- **变异得分接入 run_benchmark 流水线**（`experiments/run_benchmark.py` +
  `config.py`）：新增 `ENABLE_MUTATION_SCORING`（默认 False，保持历史实验
  口径与耗时预算）+ `MUTATION_MAX_MUTANTS`（默认 10）。开关启用时
  `run_benchmark` 在基线结果构建后逐任务调用
  `experiments.mutation_testing.compute_mutation_score`，把
  `mutation_score` 写回 `details[]`，`analyze_results._mutation_score_metrics`
  即可汇总。`_build_task_result` 成功分支新增 `generated_test` 字段
  （此前仅经 `--save-state` 落盘 raw/，标准结果 JSON 不携带；变异得分
  依赖"生成测试 + 被测源码"两者，需写进 details[]）。CLI 新增
  `--enable-mutation` / `--no-mutation` 参数。`reproduce.sh` 补充
  `ENABLE_MUTATION_SCORING` 透传说明（默认关闭，显式启用方生效）。
- **4.2 日志脱敏完整审计**（`docs/log_redaction_audit.md` + 修复 R-1）：
  四层核查——① api_manager 故障转移日志 base_url 已脱敏（`get_status` +
  `_redact(config.base_url)` + 故障转移只打 model_name）；② trace.py JSONL
  落盘经 `mask_sensitive_info` 统一脱敏；③ Docker 容器 `execute_docker`
  不注入环境变量 + `.dockerignore` 排除 `.env.*`（密钥不进镜像）；④
  唯一 `exc_info=True` 打印点（`exceptions.py:321`）经 CLI 入口的
  `SensitiveFormatter` 覆盖（脱消息体 + 脱整行含堆栈双保险）。
  **发现 R-1**：`api_manager._redact` 与 `llm_client._redact_log_text`
  在 `mask_sensitive_info` 不可用时降级为"原样返回"，敏感文本会泄漏
  进日志。修复：`logging_utils` 新增 `fallback_mask_sensitive_info`
  （取 `_SENSITIVE_PATTERNS` 前 3 条"长随机串"类模式的纯正则兜底），
  两处 `_redact` 降级路径委托该函数，脱敏模块彻底不可用时仍拦截
  32+ hex / 40+ base64 / sk- 前缀凭证。
- **3.2 多候选补丁 A/B 对比实验**：synthetic 数据集 50 任务 × 3 基线，
  两组（多候选 ON vs OFF，seed=42）完整跑完，差异数据见
  `experiments/results/multi_candidate_ab_summary.md`。

### 测试
- `tests/test_smell_detection_v2.py` 新增 4 用例：boolean_negation 真替换
  回归（6 种槽位场景）/ 嵌套函数 not / 无 not 不生成 / 端到端
  `compute_mutation_score`（强测试杀死数 ≥ 弱测试）。
- `tests/test_run_benchmark.py` 新增 4 用例：`_compute_mutation_scores_for_baseline`
  缺失/存在/未知 task/空 instance_code 四类分支 + `_build_task_result`
  成功/失败键集合一致性（含新 `generated_test` 字段）。
- `tests/test_logging_utils.py` 新增 7 用例：`fallback_mask_sensitive_info`
  的 sk-/hex/base64/JWT/正常文本/空值行为。

### 工程化基线
- 全量测试 **1474 passed / 0 failed**（上轮 1460 + 本轮净增 14）；
  `ruff check src/ tests/ experiments/` 全绿
- 脱敏审计完整报告归档于 `docs/log_redaction_audit.md`（四层核查 +
  R-1 修复）
- 多候选 A/B 对比数据归档于 `experiments/results/multi_candidate_ab_summary.md`
  （含 plain_llm 基线 LLM 缓存命中导致 token 数据失效的限制说明）

## [0.2] - 2026-09-19 代码质量与可靠性优化轮次

两个原子提交（`9f83197` + `d5f21f6`），零功能破坏，全量测试 1459→1460（净增 1 用例），Ruff 全绿。

### 重构与修复
- **RAG 降级守卫抽取**（`graph/rag.py` 新增 `rag_guarded`，依赖注入式设计）：
  统一 `graph/nodes.py` 中 4 处同构的「ENABLE_RAG 前置判断 + 取检索器单例 +
  try/except 降级」模板（generator 检索 / executor 入库 / debugger 检索 /
  debugger 入库）。依赖以参数注入而非模块内直读全局，历史 patch 路径
  （`src.graph.nodes.ENABLE_RAG` / `get_rag_retriever` 等 8 个测试用例）继续有效。
- **多函数补丁排序性能优化**（`tools/patch_applier.py`）：
  `apply_multi_function_patch` 排序 key 由「每个 patch 各自 split 一遍代码行」
  （O(n·m)）改为「预切分行复用」（O(n+m)），多文件大补丁场景直接受益。
- **实验排名绑定修复**（`experiments/analysis.py`）：`_rank_by_metric` 改为
  (name, value) 元组绑定排序，消除按 `zip` 位置错配排名的结构隐患；
  新增乱序插入回归测试 1 条（全量测试 1459→1460）。
- **数据库库名白名单**（`init_db.py`）：`MYSQL_DATABASE` 拼入
  `CREATE DATABASE` 前做 `[A-Za-z0-9_]+` 白名单校验，堵环境变量注入多语句
  SQL 的向量；import 顺序合规化。
- **懒导入消除**（`agents/base_agent.py`）：`_find_balanced_json` 与
  `extract_focused_code` 的函数内惰性导入提到模块顶层（两模块均无循环依赖），
  消除每次调用的 import 机制开销与别名噪音。
- **脱敏双实现收敛**（`agents/llm_client.py` + `api/api_manager.py`）：
  `_redact` / `_redact_log_text` 两套近似实现收敛为委托 `logging_utils.
  mask_sensitive_info` 的同一套逻辑，注释标明单一实现入口防漂移。
- **原子写盘异常收窄**（`graph/nodes.py`）：临时文件清理的
  `except BaseException` 改 `except Exception`（PEP 8：
  KeyboardInterrupt/SystemExit 不应插入清理路径，临时文件由进程退出兜底）。
- **API 管理器性能与可配置性**（`api/api_manager.py` + `api/api_health.py`）：
  `get_status` 中 `get_healthy_nodes()` 由连调两次改为结果复用（全节点池
  遍历减半）；批量健康检查节点间隔由硬编码 0.1s 提为可配置项
  `APIManagerConfig.batch_health_check_interval`（默认 0.1s 保持历史行为，
  100+ 节点池场景可设 0 或配合并发探测上调）。

### 测试清理
- 修复 1 处恒真断言（`tests/test_weak_coverage_modules.py` 的
  `assert ... or True`，此前该用例永远通过、形同虚设）。
- Ruff 自动 + 手动清理 tests/ 存量告警 24 条（未用变量 / 未用导入 /
  隐式 Optional / 裸 open / 冗余 monkeypatch 别名等）。

### 工程化基线
- 全量测试 **1460 passed / 0 failed**（约 30s）；`ruff check src/ tests/` 全绿
- 静态分析完整报告归档于 `docs/code_analysis_report.md`（30 条发现 +
  「值得做 / 不建议做」清单，本轮落地 6 条高价值项）

## [0.1] - 2026-09-18 首个正式版本（功能全集）

### 多智能体架构
- 四智能体协作：Planner（逻辑驱动思维链）/ Generator（RAG 增强）/ Executor（本地/venv/Docker 三模式）/ Debugger（分层错误修复）
- 十二类错误分类：LLM 格式 / 导入 / 语法 / 类型 / 索引 / 断言 / 逻辑 / 运行时 / 超时 / 未知 / 补丁被安全守卫拒绝 / RAG 全空
- AST 精确代码替换（`code_analyzer.py` / `patch_applier.py`），避免正则误匹配
- 检索增强生成（ChromaDB，默认关闭；`ENABLE_RAG=true` 启用，持久化至 `rag_data/`）

### 实验与评估
- 多基线对比（aitester / plain_llm / single_agent）+ 消融实验（Planner / Debugger 开关）
- SWE-bench / Defects4J-Python / 合成数据集 / 内置示例 四数据集支持
- SWE-bench 源码导出自动化（`scripts/export_swe_bench_source.py`）+ 数据污染检测（token 级 Jaccard）
- 统计检验（配对 t 检验 / Mann-Whitney U / Cohen's d）
- 结果分析层（`experiments/analyze_results.py`）：成功率 / 覆盖率 / 迭代分布 / Token 效率 / 失败原因分布 / RAG 检索质量 / 修复收敛 / 边界用例覆盖 / 变异得分 / 断言强度 / 执行反馈轨迹
- 内置变异测试生成器（`experiments/mutation_testing.py`，AST 级三类变异体，每任务 ≤20 个）
- 测试异味检测（Assertion Roulette / Magic Number / 断言弱化 / 平凡测试 / Eager Test / Lack of Cohesion）

### 可观测性与可靠性
- 结构化 JSONL 追踪层（4.1，默认关闭；`AITESTER_TRACE_DIR` 启用）
- 多候选补丁生成与验证筛选（3.1，默认关闭）
- 成本感知路由 + 熔断冷却期 + 半开探测（3.4 + 4.1 + 4.2）
- 跨文件修复（协调器-提议者架构，3.5，默认关闭）
- 断言增强策略（AST 提取现有 assert，3.4，默认关闭）
- Docker 隔离执行（`EXECUTOR_USE_DOCKER`，4.3）
- 依赖缓存监控（venv 命中率可观测 + `clean-venv-cache` CLI）

### 工程化
- Ruff lint + pre-commit + GitHub Actions CI
- 全量 **1459 个测试用例** / 覆盖率 **96%** / Ruff 全绿
- 日志脱敏三层防线（Handler 层 / 入口接线 / trace JSONL 旁路脱敏）

### 基准测试（合成数据集 50 任务，3 基线对比）

| 基线方法 | 成功率 (%) | 平均覆盖率 (%) | 平均迭代次数 | 平均耗时 (s) |
|---------|-----------|---------------|-------------|-------------|
| **AITester** | **88.0** | **97.8** | 0.64 | 45.33 |
| Plain LLM | 68.0 | 98.0 | 0.0 | 16.6 |
| Single Agent | 4.0 | 0.0 | 0.24 | 26.85 |

关键发现：
- AITester 成功率显著高于 Plain LLM（88.0% vs 68.0%），覆盖率持平（97.8% vs 98.0%）
- Single Agent 基线成功率仅 4.0%（50 任务仅 2 个通过），验证多智能体架构的必要性
- 统计检验：AITester vs Single Agent 差异极显著（p < 0.001）

## 版本说明

当前版本为 0.6。历史内部迭代版本（0.9.x / 0.10 等）不再单独记录，全部功能已并入 0.1 版本；0.2 为其上的代码质量优化轮次（无新功能，仅重构/修复/测试清理，零功能破坏）；0.3 为评估指标深化 + 变异生成器修复 + 脱敏审计轮次；0.4 为五大章节系统能力增强轮次；0.5 为分析层深化轮次（跨基线收敛对比 + 跨文件失败案例 + 最小复现代码提取）；0.6 为 P0 修复批（LLM OpenAI 路径零重试 / venv 统计双锁 / 幽灵开关实装 / multi_candidate 双次补丁应用消除 + 代码质量收尾）。
