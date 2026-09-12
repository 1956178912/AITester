# Changelog

所有重要变更将记录在此文件中。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [Unreleased] - 待发布（2026-09-14 熔断器半开探测批次：4.2）

### 4.2 熔断器半开探测（src/api/api_manager.py）
- 4.1 熔断器冷却到期后节点直接恢复全量路由，死 provider 会被流量反复打回；本次补齐经典三态（closed / open / half-open）：冷却到期后节点先进入"半开"窗口，仅承载一次探测请求，探测成功才闭合熔断器恢复全量路由，失败则重新打开半程冷却期
- `APIHealth` 新增 `in_circuit_half_open`（冷却已到期、探测未完成）与 `_probe_circuit_half_open()`（成功闭合 / 失败重开）；半开惩罚时长 = `min(cooldown/2, half_open_probe_penalty_cap_seconds)`，默认 cap 30s，防止彻底宕机 provider 冷却期越缩越短
- `get_healthy_nodes()` / `_build_node_list()` 将半开窗口节点纳入路由候选（仅开关启用时），承载探测请求；`call()` 与 `check_health()` 的成功 / 各异常分支统一消费探测结果
- `get_status()` 新增 `circuit_state`（closed / open / half_open）字段，监控与实验分析可直接观测三态
- `APIManagerConfig` 新增 `enable_half_open_probe`（默认 True）与 `half_open_probe_penalty_cap_seconds`（默认 30.0）；置 False 退回 4.1 旧行为，便于对比实验
- 文档同步：`docs/api_reference.md` 版本历史 + 4.1 相关说明更新
- 测试：`tests/test_api_manager_extended.py` 新增 `TestHalfOpenProbe` 12 用例（窗口性质 / 成功闭合 / 失败重开 / 惩罚上限 / no-op 边界 / 开关关闭回退 / call 与 check_health 双路径消费 / get_status 三态）

### 格式归一（docs/design/cross_file_repair.md）
- 3.5 设计文档中 python 代码块（dataclass 注释对齐）触发 ruff format 门禁漂移，统一归一，无逻辑改动

### 全量验证
- `pytest tests/` **1237 passed / 0 failed**（自上一批次 1225 净增 12）
- `ruff check` / `ruff format --check` 全绿

## [Unreleased] - 待发布（2026-09-14 改进清单 G-01~G-04 + 3.4 + 3.5 落地批次）

### 1.2 测试异味检测（analyze_results.py）
- `experiments/analyze_results.py` 新增 `_test_smell_detection()` 纯函数：AST 扫 `details[].generated_test`，检测 4 类 LLM 生成异味——**Assertion Roulette**（无有效断言但非平凡）、**Magic Number**（≥3 个未命名整数字面量且无常量赋值）、**断言弱化**（断言行数较上轮减少）、**平凡测试**（函数体仅 pass / 恒真断言）；旧 JSON 无 `generated_test` 时 `available=False`，渲染跳过章节，零回归面
- Markdown 渲染「测试异味检测（1.2）」章节：按基线输出异味计数 + 含异味任务清单
- 测试：`tests/test_experiments_scripts.py` +3 用例（平凡+roulette / magic number / 无 generated_test 时跳过）

### 1.3 修复收敛曲线（analyze_results.py）
- 新增 `_repair_convergence_curve()` 纯函数：按迭代轮次 0/1/2/3+ 统计"到达任务数 / 累计通过 / 累计通过率 / 累计平均耗时"，观察随迭代增加通过率如何变化；空 baseline 返回 `rounds={}` 不除零
- Markdown 渲染「修复收敛曲线（1.3）」章节
- 测试：`tests/test_experiments_scripts.py` +3 用例（累计通过率单调 / 空 details / 渲染回归）

### 4.4 依赖缓存监控（src/tools/dependency.py）
- 新增 `get_venv_cache_stats()`（命中率统计：进程内累计 hit/create + 落盘 JSON 跨进程聚合，`hit_rate = hits/(hits+creates)`）、`list_venv_cache()`（列出缓存目录所有 venv：name/path/size_mb/created_at）、`clear_venv_cache(max_age_days, max_size_mb)`（按年龄/大小过滤清理，均 None 时清空）
- `create_venv` 复用/新建路径记录 hit/create 事件（命中率可观测）
- 踩坑修复：`threading.Lock` 非可重入，`_record_venv_cache_event` 与 `_persist_cache_stats` 嵌套自锁会挂起进程——改为单一加锁边界（`_persist` 假设调用方已持锁）
- 测试：`tests/test_dependency.py` +8 用例（全量 43）

### 5.3 失败根因分类 + 案例知识库（analyze_failures.py）
- 新增 `root_cause_classification()`：三大根因（`llm_capability` / `dependency` / `framework`）按 `error_category` + `diagnosis` 关键词保守启发式归类，每类最多 3 个代表案例；未命中规则兜底 `llm_capability`
- 新增 `failure_knowledge_base()`：按 `error_category` 多样性优先选取（每类前 2），结构化案例含 `task_id / root_cause / reproducible_steps / suggested_fix`；默认输出到 `experiments/results/failure_knowledge_base.json`
- `generate_report` 新增「5. 失败根因分类」+「6. 失败案例知识库」章节
- CLI 新增 `--knowledge-base/-k` 选项（默认路径 `<results-dir>/failure_knowledge_base.json`）
- 测试：`tests/test_analyze_failures.py`（新，13 用例）

### 3.4 断言增强策略（src/agents/generator.py，默认关）
- 新增 `_extract_existing_assertions()`：AST 提取被测代码中已有 `assert` 语句（去重，最多 10 条），语法错误时保守返回空
- 新增 `_assertion_augment_enabled()`：环境变量 `ASSERTION_AUGMENT_ENABLE=true` 启用（默认 false，保持历史口径）
- `generate()` 在 RAG 注入之后追加「断言增强」段落（仅开关启用且有现有 assert 时），引导 LLM 避免断言弱化 / 恒真断言 / 魔数未命名
- 测试：`tests/test_generator.py` +6 用例（全量 27）

### 3.5 跨文件修复能力（src/tools/cross_file.py + workflow 接线，默认关）
- 新增 `src/tools/cross_file.py`：`CrossFileDependency` / `CrossFileRepairPlan` 数据结构 + `analyze_cross_file_deps`（AST 跨文件 import 依赖分析）+ `build_cross_file_repair_plan`（协调器-提议者：每模块一个提议者，复用现有 DebuggerAgent 调用路径）+ `apply_multi_file_patch`（多文件补丁应用，失败整体回滚）+ `cross_file_fallback_single_file`（单文件降级）
- `src/graph/workflow.py`：`CROSS_FILE_ENABLE=true` 时 `executor → cross_file_analyzer → debugger` 路径；`_patch_applier_node` 跨文件分支（多文件应用 + 失败降级单文件）
- `src/graph/state.py`：新增 `cross_file_deps` / `cross_file_plan` 两个字段
- `config.py`：新增 `CROSS_FILE_ENABLE`（默认 false）+ `CROSS_FILE_MAX_MODULES`（默认 5）+ `ASSERTION_AUGMENT_ENABLE`（默认 false）
- 设计文档 `docs/design/cross_file_repair.md`（方案对比：协调器-提议者 vs 纯 LLM 端到端；数据结构；测试策略；回滚计划；二期扩展）
- 测试：`tests/test_cross_file.py`（新，27 用例）+ `tests/test_workflow.py` +2 用例（workflow 跨文件启用/禁用路径）

### 文档与决策日志
- `OPTIMIZATION_PLAN.md` 新增「改进清单现状核对」章节（已落地 / 真正缺口 / 研究性项 三类分类）
- `docs/design/cross_file_repair.md` 设计文档（3.5）
- 全项目文档同步（README / QUICKSTART / api_reference / usage_examples / .env.example 补 3.4/3.5/4.4 开关说明）

### 全量验证
- `pytest tests/` **1225 passed / 0 failed**（自 1.1/1.2 首批基线 1163 净增 62）
- `ruff check` / `ruff format --check` 全绿

## [Unreleased] - 待发布（2026-09-14 评估指标多维化首批：1.1/1.2 分析层增强）

### 实验（1.1 多维评估 + 1.2 修复收敛效率）
- `experiments/analyze_results.py` 新增两个可回归的聚合章节：`repair_convergence_metrics`（首次尝试成功率、成功/失败任务的迭代 min/avg/median/max、成功任务平均耗时）与 `quality_proxy_metrics`（覆盖率/耗时代理、可选 `generated_test` 的断言行数代理、失败类别 Top N）
- `build_analysis` 与 `render_markdown` 同步渲染「修复收敛效率（1.2）」与「多维质量代理（1.1，保守可复算）」两个 Markdown 章节；旧 JSON 无 `generated_test` / 无 details 时自动降级为 N/A 或跳过章节，不崩溃
- 测试：`tests/test_experiments_scripts.py` +5 用例（收敛指标空/非空、质量代理仅现有字段、断言代理含 `generated_test`、Markdown 渲染回归）
- 文档同步：`README.md`（测试状态/最近改动/测试覆盖表/项目结构说明/5.5 结果分析章节）、`QUICKSTART.md`（高级开关结果分析说明）、`docs/api_reference.md`（版本历史）、`docs/usage_examples.md`（示例 13.5 结构化分析 + 指标口径表）、`docs/performance_guide.md`（派生指标监控说明）、`docs/failure_analysis.md`（状态说明）

全量相关回归：`tests/test_experiments_scripts.py` + `tests/test_run_benchmark.py` 28 passed；`ruff check` / `ruff format --check` 全绿；全量 `pytest tests/` **1163 passed / 0 failed**

## [Unreleased] - 待发布（2026-09-14 全项目文档同步批次 F-01~F-10）

### 文档
- **README 项目结构同步**：结构树补齐 4 处缺失（`src/observability/`、`src/graph/token_usage.py`、`src/tools/` 的 code_context/dependency/multi_candidate、experiments/ 的 run_large_scale/run_statistical_test/statistical_analysis/analyze_failures）；"供论文讨论章节"措辞改"供技术评审"；5.3 成本感知路由补 3.2 阈值可配口径；新增 5.7 SWE-bench 源码导出自动化小节
- **docs/redaction_audit.md C 项缓存路径更正**：LLM 文件缓存实际路径为 `src/cache/`（`_LLM_CACHE_DIR_DEFAULT` 相对 `src/agents/` 解析，`AITESTER_LLM_CACHE_DIR` 可覆盖，已入 `.gitignore`），此前误记为 `~/.cache/aitester/llm_cache/`（"在 HOME 天然不在仓库路径中"的论述不再成立）；"已知可接受风险"结论不变（本地可信域、脱敏与缓存精确命中互斥）
- **docs/performance_guide.md**：`rm -rf .chroma_cache/` 指向不存在目录（chromadb 1.x 持久化在 `rag_data/`），改为 `rm -rf rag_data/` + `RAG_PERSIST_PATH` 覆盖说明；时间戳 2026-08-16→2026-09-14
- **experiments/analyze_failures.py**："供论文讨论"措辞改"供技术评审"；`--output` 默认值由 `docs/paper/failure_analysis.md`（目录已不存在）改为 `experiments/results/failure_analysis.md`（无测试引用该脚本，零回归面）
- **docs/api_reference.md 版本历史**：顶部补 Unreleased（批次②）行（0.9.13 行保留为历史记录）
- **docs/usage_examples.md**：小写 `contributing.md` 引用改 `../CONTRIBUTING.md`；时间戳 2026-09-11→2026-09-14
- **.env.example 3.4 节**：补 3.2 `cost_alert_threshold` 可配说明；`LLM_N_COST_WEIGHT` 数值口径对齐 config.py 实际解析（0.1~1000，未配置默认 0.0=无信息、APIManager 回退 1.0，此前误写 1.0=基准）

全量 **1158 passed / 0 failed**；`ruff check` / `ruff format --check` 全绿；纯文档 + 脚本 docstring 改动，零功能变更

## [Unreleased] - 待发布（2026-09-14 状态细化 + 可配阈值 + 边界补测 + 源码导出 + 脱敏审计批次）

### 错误分类（1.1 状态细化）
- **ErrorCategory 补 2 个状态细化类**：`PATCH_VALIDATION_FAILED`（补丁被 PatchApplier 安全守卫拒绝，repair_history 中 patch_applied=False）与 `RAG_RETRIEVAL_EMPTY`（RAG 启用但任务内全部检索 results==0，标识 RAG 失效场景）。10 文本类 + 2 状态类 = 12 类。新增纯函数 `refine_failure_category()`（任务收尾按 repair_history/rag_stats 信号细化，补丁被拒优先于 RAG 空；成功任务原样返回）；`get_fix_strategy()` 与 `reports/generator.py` 两处 if/elif 链同步补 2 分支；`run_benchmark._build_task_result` 与 CLI `_run_single_task` 在失败任务收尾调用 refine（benchmark 与 CLI 口径一致）
- 测试：`tests/test_error_classifier.py` +9 用例（枚举值 ×3 + refine 判定矩阵 ×6），全量 81

### 成本路由（3.2 阈值可配）
- `APIManagerConfig` 新增 `cost_alert_threshold`（默认沿用模块常量 2.0），`_try_call_node` 告警判断改用配置值——阈值过低导致过多误报时上调（如 3.0/5.0 只告警真正昂贵的 provider），成本敏感度高时下调，无需改代码。告警文案打印配置阈值（避免误导调参）
- 测试：`tests/test_cost_aware_routing.py` +4 用例（默认值回归 ×1 + 上调抑制中等昂贵 ×1 + 下调告警更便宜节点 ×1 + 文案含配置阈值 ×1）

### 测试补强（1.4 / 1.5）
- **熔断冷却期边界（1.5）**：`tests/test_api_manager.py` 新增 `TestCircuitCooldownBoundaries`（3 用例）——冷却到期后节点自动回归路由池（无需 mark_success）、多节点同时冷却时路由整体降级（select_node 返回 None + call 快速失败 + get_status 暴露剩余冷却秒数）、冷却期内新请求不打回冷却节点（流量落健康节点，冷却节点零调用）
- **CLI 参数异常与并发行为（1.4）**：`tests/test_cli_app.py` 新增 3 组 8 用例——`TestRunParallelTimeoutAndInterrupt`（--timeout 贯通到任务、缺省回退 config.EXECUTION_TIMEOUT、单任务超时不阻塞整批且门控 exit 1）、`TestCheckDatasetBoundaries`（无效 dataset 值降级 InMemory 而非崩溃、--limit 负数边界）、`TestGlobInParallelMode`（字面通配符被 click exists 校验拦截的边界语义 + shell 展开后多文件并发按列表全量派发）

### 实验（2.1 / 2.3）
- **SWE-bench 源码导出自动化（2.1）**：新增 `scripts/export_swe_bench_source.py`——读取已下载 JSONL，按 patch 的 `+++ b/<path>` 提取首个非测试目标文件，`git show <base_commit>:<path>` 只读导出（不污染工作树），输出 `SWE_BENCH_ENRICHMENT` 格式 JSONL；支持 `--instance-ids`（逗号或 @文件，配合 check-dataset 输出的缺失列表批量补）、`--dry-run`、`--limit`。`SWEBenchDataset` 新增 `tasks_missing_source()`（识别 instance_code 兜底为 issue 文本的任务）；`check-dataset` 质量报告输出缺失源码的 instance_id 列表与补全指引
- **RAG 指标自动汇总（2.3）**：`experiments/analyze_results.py` 的 RAG 章节新增两个子聚合——按检索类型分解（test_cases vs repairs 各自的检索次数/命中率/相似度，分析哪类检索更有效）与 RAG 命中 × 失败类别交叉表（失败任务按 error_category 分组统计 RAG 命中占比，分析 RAG 对哪类错误修复帮助最大；1.1 细化后 rag_retrieval_empty 单独成组，命中占比必为 0）
- 测试：`tests/test_swe_bench_source_export.py`（新文件 11 用例）、`tests/test_dataset_validation.py` +2、`tests/test_experiments_scripts.py` +4

### 安全（4.1 脱敏审计）
- **脱敏覆盖完整审计**：新增 `docs/redaction_audit.md`（三层防线总览 + 逐出口走查结论）。修复两个真实盲点——(A) `APIManager` 故障转移/健康检查 7 处日志点（str(e) 与 base_url）新增模块级 `_redact()` 就地脱敏，嵌入式使用（examples/第三方集成/单测）不依赖入口接线也安全；(B) `get_status()` 出口对 base_url 脱敏（内嵌 token 的网关 URL 经 print_status_table 直接打印 stdout，绕过 logging handler）。LLM 文件缓存（prompt/response 全文落盘）经评估为本地可信域已知风险，脱敏会破坏缓存精确匹配命中，记录为已知可接受风险与后续可选方案
- 测试：`tests/test_api_manager.py` +2 用例（get_status base_url 脱敏回归 + _redact 助手行为）

### 文档对齐（批次②收尾）
- **README 数据同步**：「测试覆盖模块」主表 9 行用例数与实测 `def test_` 计数漂移同步（test_api_manager 80→77、test_cli_app 30→27、test_cost_aware_routing 14→13、test_dataset_validation 20→22、test_experiments_scripts 23→19、test_swe_bench_source_export 11→13、test_core_modules 29→19、test_executor_sandbox 14→7、test_dataset_loader_extended 73→59，09-14 批次①/② 新增用例后未同步）；"当前 1111 个用例" 更正为 1158（与状态表/全量实测一致）
- **docs/api_reference.md 错误分类 10→12 类**：枚举表补 `patch_validation_failed` / `rag_retrieval_empty` 两状态细化行（1.1），优先级说明补 `refine_failure_category()` 判定口径（批次②同步遗漏）
- **docs/failure_analysis.md 状态说明**：「扩展为 10 类」更正为 12 类（注明批次②补 2 状态细化类）
- **QUICKSTART.md 补 3.2 成本告警阈值可配**（`APIManagerConfig.cost_alert_threshold`，默认 2.0）

全量 **1158 passed / 0 failed**（scipy 精度 2 warning 为退化数据告警，非代码问题）

## [Unreleased] - 待发布（2026-09-14 错误分类细化 + 熔断冷却 + 结果分析批次）

### 错误分类（1.2 残余）
- **ErrorCategory 补 2 类**：新增 `LLM_FORMAT_ERROR`（LLM 响应格式异常：JSON 解析失败 / 截断 / 空响应，此前 75% UNKNOWN 的根因之一）与 `INDEX_ERROR`（索引越界，此前落入 RUNTIME/UNKNOWN 致 Debugger 无法针对性修复）；`classify()` 优先级调整为 LLM_FORMAT_ERROR > IMPORT_ERROR > SYNTAX > TYPE_ERROR > INDEX_ERROR > RUNTIME > ASSERTION/LOGIC_ERROR > TIMEOUT > UNKNOWN（LLM_FORMAT 置最前避免 IndexError 文本中可能出现的 assert 误判）
- `get_fix_strategy()` 补 2 条针对性策略文案（LLM 重生成 / 放宽 JSON 提取；索引越界补边界判断禁吞异常）；`reports/generator.py` 的根因分析与修复建议两处 if/elif 链同步补 2 个分支
- 测试：`tests/test_error_classifier.py` 新增 10 用例（分类正例 ×4、优先级冲突 ×2、枚举值 ×2、修复策略 ×2）

### 可观测性（4.1 残余）
- **APIManager 熔断冷却期**：`APIHealth` 新增 `circuit_open_until` / `circuit_cooldown_seconds` 字段与 `in_circuit_open` 属性（monotonic 时钟判定）；`mark_failure` 达阈值时写入冷却截止时间，`mark_success` 复位熔断器；`get_healthy_nodes()` 与 `_build_node_list` 备用候选统一过滤冷却期内节点（即使健康检查线程把 `is_healthy` 翻回 True 也继续跳过，避免流量重新打回死 provider）；`APIManagerConfig.circuit_cooldown_seconds` 默认 60.0s（`circuit_open_remaining_s` 字段暴露于 `get_status()`）
- 测试：`tests/test_api_manager.py` 新增 9 用例（APIHealth 熔断状态机 ×5、路由层冷却过滤 ×4）

### 实验
- **结果分析脚本（4.3）**：新增 `experiments/analyze_results.py`——从 benchmark JSON 提取成功率 / 覆盖率 / 迭代次数分布 / Token 效率 / 失败原因分布（1.2 细化类别可单独计数）/ RAG 检索质量，终端打印 Markdown 汇总并写 `analysis_summary.md`；兼容旧 JSON（无 token_metrics/rag_metrics 键时从 details 兜底累加）
- **公平性对照输出（2.2）**：`run_benchmark.py` 汇总阶段新增 baseline 级 `failure_category_distribution` 字段，并在 logger 与进度输出中打印各基线"平均每任务 Token / LLM 调用次数"，效率-效果二维对照（不只看成功率）
- 测试：`tests/test_experiments_scripts.py` 新增 6 用例（analyze_results 纯函数 ×5 + 前缀识别 ×1）

全量 **1111 passed / 0 failed**；`ruff check` 全绿

## [Unreleased] - 待发布（2026-09-13 系统功能增强轮次）

### 功能
- **多候选补丁与验证（3.1，默认关闭）**：新增 `src/tools/multi_candidate.py`——Debugger 一轮生成 N 个候选补丁（视角扰动提示，各走不同修复路径），静态筛选（`ast.parse` 语法 + 函数完整性 + 10% 长度安全）淘汰坏候选，可选执行验证（`MULTI_CANDIDATE_EXEC_VALIDATE`）逐候选跑测试选通过率/覆盖率最高者；经 workflow `_patch_applier_node` 接入，`ENABLE_MULTI_CANDIDATE_PATCH` 默认 false 保持历史实验口径，无有效候选自动回退单补丁不引入劣化。新增 `tests/test_multi_candidate.py`（19 用例）

### 可观测性
- **结构化 JSONL 追踪层（4.1，默认关闭）**：新增 `src/observability/trace.py`——以 JSONL 追加式记录每个任务各智能体节点的输入输出、决策路径（debug/done/regenerate）、token 消耗与墙钟耗时；`AITESTER_TRACE_DIR` 未设时全 no-op 零性能税，已设时按 `<task_uuid>.trace.jsonl` 落盘并过脱敏。workflow 节点（planner/generator/executor/debugger/patch_applier/_should_debug）逐节点记录，benchmark 入口与 CLI `_run_single_task` 在 finally 收尾 task_end。新增 `tests/test_trace_observability.py`（12 用例）

### 性能
- **成本感知路由（3.4）**：`APIManager` 新增 `COST_AWARE` 策略（按"成功率 50% + 1/成本 50%"综合评分排序，故障转移避免全量切到昂贵 provider）与成本告警（转移到 `cost_weight>=2.0` 的昂贵节点时记 WARNING，`cost_alert_enabled` 可关）；`LLMConfig` 新增 `cost_weight` 字段（`config.py` 经 `LLM_N_COST_WEIGHT` 读取，未配置默认 0.0=无信息、APIManager 回退 1.0 基准），`APIManagerConfig.node_cost_weights` 支持显式映射。新增 `tests/test_cost_aware_routing.py`（10 用例）

### 实验
- **RAG 纳入主实验（2.3）**：`reproduce.sh` 对合成/内置数据集默认显式 `--enable-rag`（rag_data/ 持久化跨实验复用），`--no-rag` 可回退 config 默认；`run_benchmark.py` 新增 `--no-rag` 参数（与 `--enable-rag` 共同覆盖 `config.ENABLE_RAG`）

### 测试
- **CLI 边界补测（1.5）**：`tests/test_cli_app.py` 新增 `TestRunParallelJsonBoundaries`（6 用例）——单文件+并发走顺序分支、多文件并发降级路径、glob 通配符被 click `exists=True` 解析层拦截（exit 2）、并发全通过/有失败的退出码语义。全量 **1085 passed / 0 failed**；src 总覆盖率 91%；`ruff check` / `ruff format --check` 全绿

## [Unreleased] - 待发布（2026-09-13 文档对齐批次 M-01~M-03）

### 文档
- README「测试覆盖模块」主表 13 处用例数漂移同步（test_api_manager 62→63、test_cli_app 11→15、test_config_manager 29→32、test_dataset_loader_extended 57→62、test_dependency 27→35、test_error_classifier 56→60、test_executor 35→39、test_experiments_analysis 11→15、test_experiments_scripts 8→10、test_generator 21→30、test_mysql_client 12→13、test_patch_applier 36→38、test_workflow 28→30，0.9.11 批次新增 27 回归用例后未同步）；"41 个测试文件" 更正为 44；补 `test_logging_utils.py`（14 用例脱敏回归）行。v0.9/v0.10 历史版本叙事表保留原值
- 全量 **1038 passed / 0 failed**；src 总覆盖率 91%；`ruff check` / `ruff format --check` / lock 同步 / sdist+wheel 构建 / pip-audit（同 CI 豁免）全部通过（纯文档改动，无代码变更，未影响测试集）

## [Unreleased] - 待发布（2026-09-12 优化轮次）

### 文档
- README 核心模块覆盖率数据对齐实测值（logging_utils 83%→88%、cli/app.py 61%→64%，上轮新增 18 用例后漂移未同步）
- README 安全扫描说明对齐 PYSEC 豁免口径（"4 条已知 CVE"→"5 条豁免：PYSEC-2026-311 重复两条 + PYSEC-2026-3813/3814/3815"，与 ci.yml 注释一致）
- QUICKSTART 配置验证步骤措辞修正：`from config import LLM_CONFIGS` 仅校验配置加载（无网络调用），真实连接探测指向 `python scripts/check_quota.py`
- 全量 **1038 passed / 0 failed**；src 总覆盖率 91%；`ruff check` / `ruff format --check` / lock 同步 / sdist+wheel 构建 / pip-audit（同 CI 豁免）全部通过

## [Unreleased] - 待发布（2026-09-11 优化轮次）

### 安全
- **日志脱敏正则扩展**：`src/utils/logging_utils.py` 的 API Key 脱敏模式此前只覆盖 `sk-` 前缀 + 字母数字 20+ 位的密钥；现补充两类此前会绕过脱敏的真实密钥形态——带点号/连字符分段的长 sk- 型（形如 `sk-ws-xxx.yyy...`）与无 `sk-` 前缀的长十六进制（≥32 位）/长 base64（≥40 位）密钥，新增 `tests/test_logging_utils.py`（14 用例，全部使用合成占位符，不引入任何真实密钥）锁定
- **CI 安全门禁豁免同步**：`.github/workflows/ci.yml` 的 pip-audit 豁免清单实测已漂移（本地 9-11 复跑 chromadb==1.5.9 报 `PYSEC-2026-311`×2 + `PYSEC-2026-3813/3814/3815`，旧清单仍豁免 `CVE-2026-45830/45831/45833`）；按实测结果同步 4 条豁免并留注释说明漂移原因，恢复 security job 可信度

### 打包
- **setup.py 补全**：新增 `py_modules=["config"]`（此前 `find_packages()` 不收录根级 `config.py`，正式安装后 `from config import ...` 会 ModuleNotFoundError，核心 CLI/API 入口全部失效）；extras 补 `experiments`（scipy+datasets）与 `ux`（rich+tqdm），dev 补 `pytest-timeout`

### 测试
- 新增 14 个日志脱敏用例 + 4 个 CLI 参数校验用例（--parallel=0 / --max-iterations=0 / --coverage-threshold 越界 / 不存在文件由 click 拦截），全量 **1038 passed / 0 failed**（0.9.11 的 1014 + 本地后续 fix 新增 6 个回归用例 + 本轮 18 个）；src 总覆盖率 91%；`ruff check` / `ruff format --check` / lock 同步校验全部通过

### 文档
- README 移除 v0.9.10 章节中 4 个不存在的测试文件（`test_api_manager_large_scale.py` / `test_error_classifier_improvements.py` / `test_executor_integration.py` / `test_patch_applier_improvements.py` 均为幽灵条目）
- README 用例数/覆盖率数据对齐本轮基线（987/1014 → 1020/1038 分两阶段收敛，最终 1038）；消融实验开关配置位置措辞对齐（config.py 默认值 + `.env` 注入，.env 已 gitignore）
- **优化记录入库**：`OPTIMIZATION_PLAN.md`（阶段 1 优化点全表 16 项 + 实施范围 + 需确认项）与 `OPTIMIZATION_REPORT.md`（阶段 0-5 完整交付记录 + 阶段 4 全量测试实测结果表）新增并提交，作为 0.9.11 优化轮次的可追溯文档；本地 `.env` 的 DOCKER_IMAGE 漂移修正（3.11-slim → 3.12-slim）仅本地生效（`.env` 已 gitignore，无入库影响）

## [0.9.11] - 2026-09-11

### 源码层：import 提取与依赖检测收敛
- **import 提取单一实现（DRY）**：`src/tools/dependency.py` 新增共享实现 `extract_import_module_names`（处理逗号分隔多模块、`as` 别名、尾随注释、相对导入跳过、多行括号导入）；`extract_imported_modules` 委托于它，`executor._extract_imports` 也复用（不再维护本地复制的正则）——此前两份复制的正则 `^import\s+([\w.]+)` 只捕获首个模块，`import numpy, scipy` 会漏掉 `scipy`，缺失依赖逃过检测、venv 少装包导致测试 ImportError
- **标准库判定收紧**：`is_standard_library` 删除死代码 `_FALLBACK_STDLIB` 白名单（Python 3.12+ 下 `sys.stdlib_module_names` 恒存在、该分支不可达，且白名单误将第三方 `pytest` 列为标准库）；权威清单缺失时改为返回 False 交由 `find_spec` 实际探测

### 源码层：执行环境与并发安全
- **executor 项目根纠偏一层**：`project_root` 由 `src/agents/executor.py` 上溯三层到仓库根（与 workflow.py 的 patch 白名单、cli/app.py 的根目录口径一致）；此前上溯两层止于 `src/`，`rglob` 模块搜索看不到 `examples/` 等 src 外目录，import 修复链路对非同名 helper 断裂
- **PYTHONPATH 尾随分隔符防护**：原 PYTHONPATH 未设置时直接拼接会产生 `"<dir>:"` 尾随空段（sys.path 空元素等价 CWD，同名文件可遮蔽第三方库）；现空段过滤后 `os.pathsep.join`，非沙箱与沙箱两条路径统一
- **MySQL 单例双重检查锁定**：`MySQLClient` 类级新增 `_instance_lock` / `_pool_lock`，`__new__` 与 `__init__` 均为"无锁快路径 + 加锁复检"DCL；此前无锁 check-then-set 在并发首次构造下可产生多实例、连接池放大
- **base_agent 缓存统一 DCL**：chat 客户端缓存与 zai 客户端缓存均加锁 + 复检双检锁定；`_get_llm_config` 的 `base_url` 为空时补对称回退 `LLM_CONFIGS[0].base_url`（修复 AttributeError）

### 源码层：容错与语义修正
- **故障转移的模型路由语义**：`APIManager.call` 显式指定 model 时仅主尝试用指定模型，转移到备用节点后改用该节点自身模型名——此前指定模型被逐次沿用，备用 provider 无该模型会逐个 APIError 陪葬，故障转移形同虚设
- **RAG 初始化失败标志粘性化**：`get_rag_retriever` 构造抛异常时置位 `_rag_init_failed`，后续节点调用快路径直接返回 None 不再重试；此前 except 分支把 `_rag_retriever` 置 None（本就是 None，no-op），每个 generator/executor/debugger 节点重复付 2-6s 初始化
- **generator 节点与全局开关解耦**：test_plan 传参改走 `state.get("test_plan")`（缺键传 None 由 Generator 自行推断）；此前 `state["test_plan"] if ENABLE_PLANNER else None` 在 ENABLE_PLANNER 开而图中无 planner 节点时 KeyError
- **add_llm_config 的 index 参数严格化**：显式 index 校验 `index >= 1` 且不与已占用 LLM_N 编号冲突（冲突返回 False）；此前不校验，追加会产出同编号双块，读取时后读覆盖先读行为未定义
- **显著性检验 NaN/Inf 序列化修复**：两组通过率完全恒定（全 1 或全 0）时 scipy 返回 NaN（配对 t 零差值）或 ±Inf（Welch 零方差），`round(float(...))` 会把非标准 token 写进结果 JSON、严格解析器（如 JS JSON.parse）报错；现以 `math.isfinite` 守卫，记一条 `status: "skipped"` 条目而非数字条目（该对比统计上本无"显著性"可言）
- **帧匹配收敛为单一 endswith**：`error_classifier._is_test_side_assertion` 旧三子句（basename 全等 / 模块名全等 / endswith）对 pytest .py 帧前两者是后者子集，收敛为单一 `endswith(f"{target}.py")`（"mycalc.py 误中 calc.py" 的既有限制保留并以回归测试锁定）；删除仅此处使用的 `import os`
- **配置模板环境变量全名**：`generate_env_template` 变量名统一为 `{PROVIDER}_API_KEY` 全名约定（ALIYUN_BAILIAN_API_KEY / AGNES_DOMESTIC_API_KEY / AGNES_INTERNATIONAL_API_KEY / BIGMODEL_API_KEY / DEEPSEEK_API_KEY），与 generate_batch_config 推导规则同源；此前硬编码短名（ALIYUN_API_KEY 等）与 provider 键名失配永远取不到；`.env.local.template` 由生成器自身重新生成
- **死分支与 no-op 清理**：executor 删除不可达的 `if missing_packages and not self.use_venv:` 死分支（`use_venv` 守卫保留供回归测试）；`analyze_failures.py` 删除两个 no-op 列表推导；`.env.example` 删除 DATASET_DEFAULT 幽灵配置块（全仓库零消费者）
- **visualize 汇总表修复**：`write_summary_md` 基线汇总表头此前 5 列 + 3 列拆两行、与 8 列数据行错位；现单一 8 列表头 + 8 分隔符

### 实验/脚本层
- **SWE-bench 下载输出命名统一**：`scripts/download_swe_bench.py` 输出改 `swe_bench_{subset}_instances.jsonl`，与 loader `_resolve_jsonl_paths` 约定一致

### 文档
- README 移除 4 处幽灵 `run_benchmark --json`（benchmark JSON 输出为默认行为、无需该 flag；`main.py run --json` 属 CLI 另一处予以保留）；docs/usage_examples.md 同错修复；docs/api_reference.md 版本表补全 0.9.1-0.9.10

### 测试
- 新增 27 个回归用例：dependency 逗号 import 提取 8 / executor 项目根与 PYTHONPATH 4 / api_manager 模型路由 1 / mysql 并发构造 1 / config_manager index 校验 3 / 显著性 NaN-Inf 守卫 2 / error_classifier 帧匹配 4 / visualize 表对齐 2 / workflow test_plan 解耦与 RAG 粘性标志 2
- 全量 **1014 passed / 0 failed**（0.9.10 的 987 + 27 新增）；src 总覆盖率 91%；`ruff check` / `ruff format --check` / lock 同步校验全部通过
- 有意保留：token_usage 死线程聚合（benchmark 运行结束聚合需要，`test_global_aggregates_threads` 锁定）；`rate_limit_remaining` 字段（8 处测试引用）；error_classifier SYNTAX+IMPORT_ERROR 防御分支

## [0.9.10] - 2026-09-11

### 源码层：CLI 并发派发 DRY 化
- **`run` 并发执行两段同构块合并**：`src/cli/app.py` 的 `run` 命令在 `--parallel>1` 多文件场景下，rich 进度条分支与纯文本降级分支各维护一份"future 提交 + `as_completed` 汇总 + 逐任务容错"同构循环（约 30 行重复），结果结构变化需同步改两处、易漂移；现抽取共享派发器 `_dispatch_parallel_tasks()` 作为单一构造点，两种模式仅进度反馈策略不同，经 `on_progress` / `on_success` 回调注入（rich 推进进度条 / 纯文本打印 `✓ 完成`，`--json` 时静默）；行为保持不变

### 测试
- 新增 `tests/test_cli_parallel.py`（10 个用例）：`_dispatch_parallel_tasks` 全成功 / 单任务异常不中断整批 / `on_success` 仅成功触发且传 basename / `on_progress` 每任务结束触发（含失败）；`_handle_task_exception` 错误结果脱敏与同构键集；`run` 并发分支 rich 可用 / 无 rich / 单文件回退顺序执行 / 失败门控 exit 1 四条端到端路径（mock 工作流）
- 全量 **987 passed / 0 failed**（+10 新增）；cli/app.py 覆盖率 50% → 61%，src 总覆盖率 90% → 91%；`ruff check` / `ruff format --check` 全部通过

## [0.9.9] - 2026-09-11

### 实验/脚本层：误选结果与必崩 KeyError 修复
- **visualize 结果误选修复**：`experiments/visualize_results.py` 的 `load_latest_result` 此前对 results 目录全部 JSON 纯文件名倒序取第一，会误选 `swebench_20_summary.json` / `performance_benchmark.json` / `synthetic_plain_llm_*.json`（'s'/'p' 均排在 'b' 之后），出图实际基于非 benchmark 数据；现仅识别 `benchmark_*` 前缀（与 run_benchmark 命名口径一致），无匹配时回退全量并提示
- **标准化实验必崩 KeyError 修复**：`scripts/run_standardized_experiments.py` 的 `run_experiment` 三个返回分支（success/failed、timeout、error）均无 `description` 键，而 `main()` 写汇总报告时无条件读 `r['description']`，每次运行必 KeyError、EXPERIMENT_SUMMARY.md 永远生成不了；现三个分支都带 description
- **benchmark 并行度配置绕过修复**：`experiments/run_benchmark.py` 的 parallel 缺省值此前 `int(os.getenv("BENCHMARK_PARALLELISM","0"))` 直读原始环境变量，坏值（如 "abc"）直接 ValueError 崩溃且绕过 config 容错；现统一走 `config.BENCHMARK_PARALLELISM`（`_parse_int_env` 容错 + 下限校验）
- **benchmark LLM 回退静默吞错补日志**：`_call_llm_with_fallback` 外层 `except` 此前静默 `continue`，zai 分支重试耗尽 raise、或 zai/openai 客户端构造失败时全链路无日志线索；现补 warning 日志（与 openai 分支既有口径对齐）

### 源码层：死代码与幽灵配置清理
- **executor 死分支删除**：`_execute_sandboxed` 中依赖安装失败/venv 创建失败（`sandbox_error_info` 非 None）已在依赖检测段提前 return，其后"安装失败优先覆盖 error_info"分支恒不可达（变量必为 None），删除死分支、行为不变
- **planner 默认计划去重**：`_planner_node` 的 except 兜底分支此前内联复制一份与 `_get_default_test_plan` 同构的默认计划字典（校验失败分支早已走 helper），双份维护易漂移；现统一走 helper 单一构造点，其 "or 'unknown'" 兜底比原内联 `.get` 默认值更严格（空串/None 键值也归一）
- **generator 死常量删除**：`_MAX_PARAMETIZE_RETRIES = 2` 除 docstring 外无任何代码引用，实际实现 parametrize 校验失败仅重试一次；删除常量并把 docstring 对齐实际行为
- **MySQL 连接池 idle_timeout 接通**：`_POOL_IDLE_TIMEOUT = 600` 定义后从未传入 PooledDB 构造参数（死常量），注释却声称其为 idle_timeout；现接通，空闲连接 600s 回收，防服务端 wait_timeout 断长连接
- **APIManager 幽灵配置接线**：`APIManagerConfig.max_consecutive_failures`（默认 3）定义却从未被 `mark_failure` 消费（节点阈值硬编码 3）；现 APIHealth 新增同名字段（默认 3 保持历史行为），APIManager 构造/add_node 时从 manager 配置注入，`mark_failure` 读自身字段

### 测试
- 新增 14 个回归用例（visualize 前缀过滤 3 / standardized 返回键 4 / benchmark 并行度护栏 1 / planner 去重 2 / mysql idle_timeout 1 / api_manager 幽灵配置 3），全量 **977 passed / 0 failed**；src 总覆盖率 90%；`ruff check` / `ruff format --check` / lock 同步校验全部通过

## [0.9.8] - 2026-09-10

### 工程化：格式门禁恢复与文档漂移修复
- **`ruff format` 门禁恢复**：0.9.7 之后 15 个文件（13 个 .py + README.md / docs/api_reference.md）的换行/空白与 ruff 0.16.3 格式漂移，`ruff format --check` 在 CI lint 步骤转红；统一重新格式化后门禁恢复（纯空白归一，无逻辑改动）
- **README 测试状态表漂移**：用例数停留在 860（0.9.5 旧值），"最新优化"行仍指向 0.9.5；现与实测对齐（963 用例 / src 总覆盖率 90%）

### 重构：benchmark 结果构造去重
- **`run_benchmark` 三处结果字典去重**：`run_single_task` 的成功 / 限流重试 / 异常分支各写一份同构 12 字段结果字典，新增指标（token_metrics 等）需同步改三处、极易漂移；现抽取 `_build_task_result()` 单一构造点（成功路径取 `final_state` 值，失败路径用占位值），并补键集合一致性回归护栏
- **single_agent 基线超时绕过 config 校验**：`ExecutorAgent(timeout=int(os.getenv("EXECUTION_TIMEOUT", "30")))` 直接读环境变量原始值，坏值（如 "abc"）会立即 `ValueError` 崩溃且绕过 [10, 300] 范围校验；现统一走 `config.EXECUTION_TIMEOUT`（容错解析 + 范围校验，与 workflow executor 节点口径一致）

### APIManager 构造副作用收敛
- **后台健康检查线程可关闭**：`APIManager.__init__` 此前无条件启动守护线程，每 60s 对全部节点发起真实 LLM 健康检查请求（消耗 API 配额）；嵌入式使用与单元测试场景构造即产生网络副作用。新增 `enable_health_checker` 参数（默认 True，保持历史行为），测试全部改为 `enable_health_checker=False` 构造，套件内不再产生游离线程

### 性能
- **executor 失败用例解析正则预编译**：`_parse_failed_cases` 每次调用重新 `re.compile`，现移到模块级预编译（与同模块其他正则的"预编译避免重复开销"约定对齐）

### 测试
- 全量 **963 passed**（+6 新增：benchmark 结果构造 4 + 健康线程开关 2），0 skipped；src 总覆盖率 90%；`ruff check` / `ruff format --check` / lock 同步校验全部通过

## [0.9.7] - 2026-09-10

### P0：大文件上下文与数据集质量
- **AST 智能截取（code_context）**：`BaseAgent.truncate_code` 超预算时不再"头尾各半"硬截断，先按焦点函数做 AST 截取（保留 import + 目标函数及其直接依赖的辅助函数，超长函数体首尾截断），仍超预算才回退字符级兜底；Generator/Planner/Debugger 全链路透传 `focus_function`，SWE-bench 任务以官方 patch 提取的 `suggested_function` 初始化 `target_function`
- **SWE-bench 加载质量校验（check-dataset）**：官方 JSONL 不含被测源码字段，`validate_task()`/`quality_report()` 逐任务检查 instance_code 兜底值、源码合法性、test_code 用例与用例数；`_extract_suggested_function()` 从官方 patch hunk 头提取目标函数（本地 225 任务实测提取率 96%）；`_load_enrichment()` 经 `SWE_BENCH_ENRICHMENT` 指定 JSONL 补全源码字段；CLI 新增 `check-dataset` 命令作为排查入口
- **LLM token 用量统计（token_usage）**：线程局部累计 input/output token 并按模型分桶；基准运行前 `reset()`、结束后随结果 JSON 输出 `token_metrics`/`token_usage`，支撑完整系统 vs Plain LLM 性价比对比

### P1：执行隔离与 RAG
- **Executor venv 沙箱**：`EXECUTOR_USE_VENV=true` 时任务在临时沙箱目录 + 按依赖组合磁盘缓存的隔离 venv 中执行 pytest，`PYTHONPATH` 仅指向沙箱目录，任务间依赖互不冲突、不污染系统环境；`EXECUTOR_AUTO_INSTALL_DEPS=true` 自动 pip install 缺失依赖（仅装入 venv）；缺失依赖写入 `error_info.missing_dependencies`，由分类器归为 `import_error`，"环境缺依赖"不再被误判为代码 bug
- **RAG 持久化 + 检索质量指标**：检索库持久化到 `rag_data/`（`RAG_PERSIST_PATH`/`RAG_COLLECTION_NAME`/`RAG_TTL_SECONDS` 可配，TTL 默认 7 天，空路径回退内存模式），跨实验运行可复用；`TestCaseRetriever.evaluate_retrieval()` 提供 Hit Rate@k / MRR；`AITesterState.rag_stats` 累计两次检索（test_cases/repairs）的命中数与相似度，基准结果 JSON 输出 `rag_metrics`

### P2：错误分类细化
- **五类 → 八类**：`IMPORT_ERROR`（从 SYNTAX 拆出：缺依赖与语法写错的修复路径完全不同）、`TYPE_ERROR`（从 RUNTIME 拆出：核对参数与返回类型）、`LOGIC_ERROR`（从 ASSERTION 拆出：断言失败但失败栈未触及被测模块，提示改测试而非盲目改代码）；`classify()` 新增 `target_module` 参数支持 LOGIC_ERROR 判定；修复策略与报告生成器同步补三个新类别分支

### 工程化与安全
- **配置外部化**：MySQL 连接池四参数（`MYSQL_POOL_*`）从 `mysql_client.py` 硬编码迁到 `config.py` 环境变量注入（默认值与历史一致，未配置时行为不变）；执行隔离三参数、RAG 三参数同步入 `.env.example`
- **日志脱敏加固**：`base_agent` 的 LLM 异常文本统一走 `mask_sensitive_info`（含 zai 路径与最终 raise）；`experiments/run_benchmark.py` 入口显式挂载 `setup_logger_safety()`，补齐 experiments 等非 CLI 入口的脱敏盲区
- **benchmark 排查工具链**：`--save-state` 把环节级状态（测试计划/生成代码/诊断/补丁）落盘到 `output_dir/raw/`；新增 `compare_failures.py` 逐环节对比"基线 A 失败但基线 B 成功"的任务并输出 Markdown 报告（疑似环节提示 + token 汇总）
- **文档同步**：`docs/api_reference.md` 更新八类分类表、`focus_function`/`target_module` 参数与新工具模块（CodeContext/Dependency/TokenUsage）；`src/tools/__init__.py` docstring 补全模块清单；README 测试覆盖表与实测用例数对齐（40 文件 / 957 用例）

### 测试
- 新增 6 个测试文件（code_context 11 / dependency 27 / executor_sandbox 7 / dataset_validation 14 / token_usage 9 / rag_metrics 5），合计 40 个测试文件、957 个收集用例，src 总覆盖率 90%

## [0.9.6] - 2026-09-10

### 工作流正确性修复
- **regenerate 路由死循环**：`_should_debug` 在达到最大迭代且诊断命中"测试生成错误"关键词时路由回 generator 重新生成，但旧实现不递增计数、不清 `diagnosis`，关键词反复命中使 generator↔executor 无限乒乓，最终撞上 LangGraph `recursion_limit` 崩掉任务并空烧十几轮 LLM。现 `state` 新增 `regeneration_count`，每次再生成 +1 并清空过期 `diagnosis`/`error_category`，达到 `_MAX_REGENERATIONS`（=1）后 `_should_debug` 返回 "done"。补 3 个回归测试
- **patch_applier 状态/磁盘失步**：安全检查（空/过短/无函数定义/路径不合法）拒绝写盘时，节点仍把 `new_code` 当作 `target_code` 返回并记 `patch_applied=True`，导致下游 Executor 测旧文件、Debugger 分析新代码的"幻象迭代"。现仅写盘成功才更新 `target_code` 并记 `patch_applied=True`，否则保留原代码记 False。补成功/拒绝/过短 3 个用例
- **路径白名单前缀碰撞**：`startswith((project_root, temp_dir))` 缺 `os.sep`，`AITester_backup/` 兄弟目录会命中绕过白名单；现经 `_is_within_allowed_roots` 带 `os.sep` 比较，并用 `realpath` 归一化（macOS `/var`↔`/private/var` 符号链接失配）
- **写盘非原子**：`open("w")` 先截断后写，中途崩溃会损坏用户源文件。现 `_write_file_atomic` 写临时文件后 `os.replace` 原子替换
- **Generator 误改写第三方库 import**：`_fix_import_module` 此前把白名单外的所有 `from X import` 无条件替换为被测模块名（`from numpy import array` 被改坏）。现复用 executor 现成的 `SequenceMatcher` 相似度门控（阈值 0.6，与 `_is_similar_module_name` 同源），仅替换"笔误"级相似名，保留不相似的第三方库

### 安全
- **新增 `.dockerignore`**：`Dockerfile` 的 `COPY . .` 此前会把本地含真实 LLM 密钥的 `.env`/`.env.local`、`.venv/`、`.git/`、`.private/`、各缓存打进镜像。现排除全部敏感/无关内容
- **异常堆栈脱敏盲区**：`SensitiveFilter` 只覆盖 `record.getMessage()`，`exc_info` 的 traceback 经 `formatException` 生成后绕过过滤（`safe_execute` 的 `logger.error(..., exc_info=True)` 是触发点），与模块"异常文本已脱敏"的声明不符。新增 `SensitiveFormatter` 在完整格式化结果（含堆栈）上再脱敏，CLI handler 统一挂载；补 2 个用例
- **JSON error 字段脱敏**：任务异常的 `error` 字段（`str(error)`）经 `click.echo` 走 stdout，脱敏过滤器只覆盖 logging 通道，LLM 异常消息若含 key 会裸奔。现经 `mask_sensitive_info` 脱敏

### 缺陷修复
- **CLI 失败仍 exit 0**：`run` 命令无论成败都返回 0，CI/脚本无法门控。现有任一任务失败（含崩溃产生的错误结果）时 `raise SystemExit(1)`；全通过 exit 0。补 2 个门控用例
- **`--json` 输出被污染**：日志 `StreamHandler(stdout)` 与 rich 进度条同走 stdout，`| jq` 解析必失败。现 JSON 模式经 `_quiet_console_logs()` 临时静音 stdout 控制台 handler（仅改 level、不动 stream，测试友好），rich 进度条走 `Console(stderr=True)`，`stdout` 只承载 JSON
- **Executor 超时丢部分输出**：`TimeoutExpired` 自带部分 stdout/stderr，旧实现返回空串，Debugger 拿不到现场。现合并 `e.output`/`e.stderr` 进 output。补 1 个用例
- **`reproduce.sh` 默认 quick 不限任务**：默认 `MODE="quick"` 但 `TASK_LIMIT=""`，无参运行实际跑不限量任务，与文档"quick=3"矛盾。现默认 `TASK_LIMIT=3`
- **`generate_batch_config.py` 字段名失配**：读 `model.get("name")`，但 `llm_configs.json` 字段是 `model_name`，生成的模型名整列是 `unknown`。现 `model_name` 优先、`name` 兜底
- **ruff `target-version` 漂移**：`pyproject.toml` 写 `py310`，但 `setup.py` `python_requires>=3.12` 且 CI 矩阵下限 3.12。现对齐 `py312`

### 工程化
- **CI 提速与可靠性**：两个 `setup-python` 加 `cache: pip` + `cache-dependency-path: requirements.txt`（省 3-8 分钟/矩阵）；`test`/`security` job 加 `timeout-minutes`（30/10）防长挂；`pip-audit` 锁版本 `==2.10.1`（与"锁版本防漂移"原则一致）

### 测试
- 全量 **870 passed**（+10 新增用例：regenerate 上限 ×1、patch_applier 一致性 ×2、generator 再生成 ×2、generator import 门控 ×1、executor 超时部分输出 ×1、脱敏 ×2、CLI 门控 ×2，其中 1 个为既有断言更新），0 skipped；`ruff check` / `ruff format --check` / lock 同步校验全部通过

## [0.9.5] - 2026-09-10

### 严重缺陷修复
- **`remove_llm_config` 移除模型后密钥行残留**：旧实现逐行 skip 匹配只能命中 `LLM_N_MODEL_NAME` 行，同块的注释行 / `API_KEY` / `BASE_URL` 行残留在 `.env.local`——密钥长期滞留文件、编号仍被占用导致自动分配偏移、`gone_indices` 环境变量清理永不触发。现由 MODEL_NAME 行（行尾精确匹配）识别编号集合后整块移除，补 4 个回归测试（整块移除 / 保留其他模型 / 多编号同名 / partial 名不误删）
- **`src/utils` 缺 `__init__.py`，pip 安装包漏包**：`find_packages()` 只收集含 `__init__.py` 的目录，`src.utils` 不在分发包内，安装后 `from src.utils.helpers import ...` 直接 ImportError（本地靠 PEP 420 命名空间包机制掩盖了问题）。补包标记文件，新增 `tests/test_packaging.py`（文件系统断言，不依赖 setuptools，含子包漂移检测）
- **CLI 日志配置在 Python 3.14 下静默失效**：`logging_utils.setup_logger_safety()` 尾部模块级 `logging.info()` 在 root 无 handler 时触发隐式 `basicConfig()`（附加裸 StreamHandler），使 app.py 后续 `basicConfig`（自定义格式 + FileHandler）整体 no-op——文件日志从未生效。改用模块 logger 记录

### 缺陷修复
- **数值环境变量容错解析**：`MAX_ITERATIONS` / `COVERAGE_THRESHOLD` / `BENCHMARK_PARALLELISM` / `LLM_RETRY_WAIT` / `MYSQL_PORT` / `TEMPERATURE` / `EXECUTION_TIMEOUT` / `LLM_TIMEOUT` 此前 `int()/float(os.getenv(...))` 裸转换，单个坏值（如 `MAX_ITERATIONS=abc`）在 import 期抛 ValueError 让全程序无法启动。新增 `_parse_int_env` / `_parse_float_env`：坏值 / 越界记 WARNING 并回退默认；`COVERAGE_THRESHOLD` 增加 [0,100]、`TEMPERATURE` 增加 [0,2] 范围约束
- **CLI 顺序模式单任务异常中断整批**：`--parallel=1` 多文件场景任一任务异常（文件读取失败 / 工作流崩溃）即整批中断，与并发分支逐任务容错行为不一致。现顺序分支逐任务 try/except，复用统一的 `_make_task_error_result` 追加错误结果后继续；`--timeout` 增加 >=1 校验（负数 / 0 会让 subprocess 立即超时）
- **日志脱敏从未生效 + 实现两处缺陷**：`logging_utils.SensitiveFilter` 此前无入口引用（死模块），脱敏能力实际不存在。现 CLI 入口 `basicConfig` 后调用 `setup_logger_safety()` 挂载过滤器，并修复：(a) logger 级过滤器拦不住子 logger 传播的消息，需同时挂 handler 级；(b) 逐字段 mask 对拆分在 msg 与 args 中的密钥（`logger.info("sk-%s 失效", key)`）无法命中，改为先 `getMessage()` 格式化再整体脱敏

### 重构
- `api_manager`：`_HEALTH_CHECKER_SHUTDOWN_TIMEOUT` 移至使用它的 `APIManager` 类之前定义（原在文件尾，依赖模块级名称晚绑定）
- `reports/generator`：移除只写不读的 `_report_counter` 死属性
- `dataset_loader`：`get_available_datasets` 与 `load_dataset` 的 `dataset_map` 同步（补 `examples` / `synthetic` / `synth` 别名），更新对应测试
- `patch_applier`：3 处循环内逐行 `re.match` 改为循环前预编译
- `error_classifier`：`syntax_keywords` 提升为模块级常量 `_SYNTAX_ERROR_KEYWORDS`（原每次调用重建列表）
- `helpers`：`extract_code_block` 的 ```python 正则预编译；docstring 编号修正
- `cli/app`：`list_examples` 移除非空分支内的死 `else`
- `.env.example`：`BENCHMARK_PARALLELISM` 注释去漂移（并行已实现，非"暂未实现"）；补 `LLM_RETRY_WAIT` 说明

### 测试
- 全量 **860 passed**（+18 新增用例：config_manager 整块移除回归 ×4、packaging ×3、config 容错解析 ×6、CLI 容错 ×3、脱敏接入 ×2），0 skipped；总覆盖率 **90%**（88% → 90%）；`ruff check` / `ruff format --check` / lock 同步校验全部通过

## [0.9.4] - 2026-09-13

### 缺陷修复
- **批量配置生成器环境变量名失配（M20）**：`generate_batch_config.py` 与内嵌模板的 `main()` 硬编码读 `ALIYUN_API_KEY`/`AGNES_API_KEY` 等 4 个环境变量名，但 `generate_config` 按 `{PROVIDER}_API_KEY`（如 `aliyun_bailian → ALIYUN_BAILIAN_API_KEY`）查键，两者永远对不上、只能落占位符。现改为按 models 实际出现的 provider 推导键名（与 `generate_config` 同源），任意 provider 都能取到；根脚本与内嵌模板同步，新增子进程回归测试
- **`analysis.py` 假 t 检验（M15）**：`significance` 字段此前写死 `"t-test (requires scipy)"` 占位文本（从未执行）。现按 per-task `details` 真实计算：`task_id` 配对走 `ttest_rel`，否则 Welch 双样本；样本不足 / 缺 scipy / 无 details 时如实返回 `insufficient_data` / `unavailable`，不再假装检验过；`generate_comparison_report` 增加 Significance Test 节
- **`code_analyzer` 三处失真**：`replace_function_code` 只匹配 `ast.FunctionDef`，`async def` 被静默漏配（`AsyncFunctionDef` 非其子类）；圈复杂度漏算三目表达式 `ast.IfExp`；`BoolOp` 注释与 CPython 实际行为矛盾（链式 `and` 折叠为单节点而非二叉树）；`parse_function_nodes` 文档声称 args 不含 self/cls 但代码从不剔除——三处均已修正

### 重构
- **统计检验双实现收敛**：`experiments/statistical_analysis.py` 与 `run_statistical_test.py` 各有一份近似重复实现，且旧版按位置（min_len 截断）配对——两基线结果顺序不一致时不同任务被错配成一对、t/p 值失真。现统一为按 `task_id` 配对（同一任务在两个基线下各跑一次），规范实现收敛到 `statistical_analysis.py`（论文提交包引用的文件名），`run_statistical_test.py` 退化为薄壳入口；配对逻辑提取为 `_pair_by_task`、效应量改配对差值标准差口径、NaN 分支安全、Markdown 报告 nan 值显示 n/a
- **chromadb 1.x 现代客户端 API 迁移**：`chromadb.Client(Settings(persist_directory=...))` 已弃用，且 `Settings()` 默认 `persist_directory='./chroma'`——"内存模式"（`persist_path=None`）实际会在 CWD 落出持久目录（与 aiterator.log 同类污染）。现 `persist_path` 给定时用 `PersistentClient`、否则 `EphemeralClient` 纯内存，并关闭 `anonymized_telemetry` 避免后台遥测上报

### 性能
- **RAG 清理全表扫描加 60s 节流**：旧行为每次 `add_case`/`add_repair` 都做一次 `collection.get(include=[metadatas])` 全表扫描（O(N)），大缓存长跑累积为 O(N²)。现"容量未满 且 已清理过 且 距上次 <60s"时跳过扫描；容量满（需驱逐）与首次清理仍每次执行，驱逐语义不变；TTL 默认 3600s，最坏 60s 清理延迟对实际过期语义可忽略

### 测试与文档
- 补齐低覆盖模块测试：`planner.py`（42%→，mock `_call_llm_with_cache` 覆盖 `plan()` 四路径 + `LogicAnalysisResult`）、`synthetic_dataset.py`（48%→，触发惰性加载验证结构/seed 可复现/异 seed 差异/取模覆盖）、`code_analyzer.py`（0%→，17 用例）、`analysis.py`（0%→，11 用例）、`cli/app.py`（`list-examples` 正常/缺目录 + `--version`）；`run` 命令为 140 行编排胶水、需重度 mock，本轮未覆盖
- 修正 `plan()` 文档：非 JSON 实际抛 `JSONDecodeError`（`_extract_json` 委托 `extract_json_object`），此前误标为 `RuntimeError`
- **回归**：全量 **842 passed**（+44 新增用例），0 skipped，1 warning（chromadb 内部 DeprecationWarning，第三方库）；总覆盖率 88%；`ruff check` / `ruff format --check` / lock 同步校验全部通过

## [0.9.3] - 2026-09-13

### 配置与实验正确性修复
- **`.env.local` 写入路径与刷新失效**：`config_manager` 此前把 LLM 配置写进 `src/config/.env.local`（模块所在目录），而应用只读根目录 `.env.local`，`add_llm_config`/`remove_llm_config` 重启后全部不生效。现统一写根目录；新增 `config.refresh_llm_configs()` 原地刷新 `LLM_CONFIGS`（导入时快照不会自动更新），删除时同步清理 `os.environ` 中残留的 `LLM_N_*` 变量；自动编号改为扫描文件已占编号取 max+1（编号空洞不再冲突）；重复模型检查覆盖任意编号
- **基线对比有效性**：`build_workflow` 新增 `planner`/`debugger` 参数（None 回落 config 值），`plain_llm` 基线改为直接构建降级图——此前 `importlib.reload` 改的是 `run_benchmark` 命名空间的全局开关，`workflow.py` 重新 `from config import` 后拿到的仍是原值，开关实际未生效（plain_llm 跑的其实是完整管线）；`run_single_task` 每基线 deepcopy 初始 state 并重置磁盘实例文件（single_agent 基线会把修复代码写回 target_file，共享 state 时后续基线从已修复状态起步）；`run_benchmark` 新增 `seed` 参数并透传 `SyntheticDataset`（此前硬编码 42，`--seed` 被静默忽略），结果 JSON 记录 seed
- **SWE-bench 下载/加载路径对齐**：`download_from_huggingface` 此前写 `~/.cache/aitester/swe_bench_instances.jsonl`，加载器却读 `~/.cache/aitester/swe_bench/`，下载完永远找不到。现默认目录对齐加载器 data_dir，文件名带子集标识（mini/lite/full 不再互相覆盖）；加载器按 subset 读专属文件，未指定时合并全部子集文件并按 instance_id 去重；`instance_code` 优先级 `instance_code > base_code > problem_statement` 兜底
- **批量配置生成器数据丢失防护**：`generate_batch_config.py` 及内嵌模板在模型列表为空时以 "w" 模式写 `.env.local` 会抹掉现有全部 LLM 配置，现改为报错退出（新增子进程回归测试）

### 缺陷修复
- **错误报告上下文失效**：`ReportGenerator.generate()` 此前 `classify() + context=None`，ImportError 根因/修复建议分支（依赖 `context.module_name`）是死代码、`error_subtype` 恒为 None。现接 `classify_with_context`，并修复 `context.subtype` 为 None 时的 `.value` 崩溃；`save_report` 对参与文件名拼接的 task_id 做白名单 + 截断消毒（防路径穿越）；分类器 traceback 分支不再给纯运行时错误误标 `SYNTAX_ERROR` 子类型
- **RAG 相似度恒 0.0**：ChromaDB 余弦空间下 distance 不在 metadatas 中，旧 `meta.get("distance", 0.0)` 永远取默认值。现从查询结果 `distances` 字段换算 `similarity = round(1 - distance, 4)`
- **CLI 健壮性**：模块导入期的 `FileHandler("aitester.log")` 在只读 CWD 下 PermissionError 崩溃整个 CLI，现捕获 OSError 降级为仅控制台；覆盖率 0.0 是合法数据，三处 falsy 判断误显示 N/A 改为 `is not None`
- **BaseAgent 客户端复用**：`__init__` 此前每实例新建一个 `ChatOpenAI`（生产调用全走 `_call_llm` 的缓存客户端，`self.llm` 实为占位属性），现改为复用模块级缓存；修正 `_call_zai` docstring（实际所有可重试异常统一 5s 基准退避，旧注释与实现不符）

### 重构
- **`APIManger` → `APIManager`**：类名拼写错误统一重命名（src/api、`__init__` 导出、测试与示例共 6 文件），后台线程名同步更正；1.0 前无外部用户，不做别名兼容；CHANGELOG 历史记录中的旧拼写保留
- **加载 hack 简化**：`api_manager`/`config_manager` 中重复的 `importlib + sys.modules` 别名加载 `config.py` 改为常规 `from config import`（无循环导入风险，且消除两份独立模块实例）
- **CLI 死代码清理**：移除无引用的 `tqdm`/`TQDM_AVAILABLE` 探测块与转导的 `rich.progress` 组件

### 文档与一致性
- **reproduce.sh**：单测 tee 目录前置创建 + pipefail 容错；SWE-bench import 路径修正（`src.datasets.dataset_loader`）；环境校验从废弃的 `OPENAI_API_KEY` 改为 `LLM_1_API_KEY`；Python 3.10+ → 3.12+（锁定依赖 scipy==1.18.0 要求）
- **`.env.example`**：`DOCKER_IMAGE` 3.11-slim → 3.12-slim（与锁定依赖/config.py 默认/Dockerfile 对齐）；`DOCKER_ENABLED` 注释如实说明容器隔离尚未实现（`use_docker` 为保留接口）
- **回归**：全量 **798 passed**（+11 新增用例），0 skipped，1 warning（chromadb 内部 DeprecationWarning，第三方库）；总覆盖率 83%；`ruff check` / `ruff format --check` / lock 同步校验全部通过

## [0.9.2] - 2026-09-09

### CI 门禁修复（主分支恢复全绿）
- **ruff format 门禁转红修复**：主分支 CI 在 "Lint with ruff" 步骤失败（`ruff format --check` 对 `src/agents/base_agent.py`、`src/cli/app.py`、`tests/test_cli_run.py` 三个文件要求重排），全仓库重新执行 `ruff format` 修复
- **CI 固定 ruff 版本**：此前 CI `pip install ruff` 安装最新版，上游发版改变格式化规则时门禁随机转红（2026-09-09 相邻两次 CI 运行结果不一致即此原因）。现固定 `ruff==0.16.3`（与 `requirements.lock` 一致），升级时同步更新 lock
- **补齐 DBUtils 依赖声明**：`src/db/mysql_client.py` 使用 `dbutils.pooled_db.PooledDB`，但 `requirements.txt`/`requirements.lock`/`setup.py` 均未声明——全新环境安装后 `src.db` 模块 ImportError。现补齐 `DBUtils==3.1.2` 并新增 `tests/test_mysql_client.py`（11 个用例，mock 连接池覆盖单例、commit/rollback 与三张表 CRUD）

### 测试质量提升
- **重新启用 LLM 文件缓存 6 个测试**：`test_base_agent_extended.py` 中 6 个以"局部 import os/json 无法 patch"为由 skip 的测试，其 skip 理由在源码重构为模块级 import 后已失效。现通过 `AITESTER_LLM_CACHE`/`AITESTER_LLM_CACHE_DIR` 环境变量实现：缓存未命中、命中、prompt 不匹配、读取损坏 JSON、写入成功、写入异常 6 条路径全覆盖（skip 清零）
- **API 管理器线程卫生测试**：新增 5 个用例（单例一致性、reset 停止健康检查线程、并发 get_manager 单实例、故障转移迁移日志）
- **报告生成器测试补全**：新增 `tests/test_report_generator.py`（44 个用例），`src/reports/generator.py` 覆盖率由 **0% 提升至 100%**。覆盖 ErrorReport 四种序列化（dict/text/markdown/json）全部分支、generate() 五大错误分类路径、根本原因/修复建议的 context 分支（`generate()` 内 context 恒为 None，需直接调用私有方法构造 `ErrorContext` 覆盖）、`_parse_failed_cases` 解析（含 name 兜底为 unknown 的边界）、`save_report` 三格式落盘与单例语义

### 缺陷修复
- **API 管理器后台线程泄漏**：`reset_manager()` 此前只清全局引用，`APIManger` 初始化的后台健康检查守护线程（每 60s 发起真实 LLM 探测）残留，继续对旧实例消耗 API 配额。现 reset 前调用新增的 `_stop_health_checker()` 显式停止并等待线程退出
- **故障转移日志错误**：`_try_call_node` 的 "故障转移成功" 日志此前把**当前**节点名打印两遍（`%s -> %s` 同值），无法看出迁移路径。现经 `prev_model` 参数记录"上一节点 -> 当前节点"
- **单例线程安全**：`get_manager()` 增加双重检查锁，多线程并发只创建一个管理器实例

### 代码质量
- **版本号收敛为单一事实来源**：`src/__init__.py` 新增 `__version__`（0.9.2），`setup.py` 与 CLI `--version` 均从此读取，消除两处硬编码漂移
- **RAG 类 pytest 收集告警**：`TestCaseRetriever` 类名以 Test 开头触发 `PytestCollectionWarning`，加 `__test__ = False` 消除
- **魔数提升**：`workflow._patch_applier_node` 内 `_MAX_REPAIR_HISTORY` 提升为模块级常量（附注释）
- **冗余 import 清理**：`generator._validate_parametrize` 移除方法内重复的 `import ast`（模块顶部已导入）

### 文档与一致性
- **README 测试状态刷新**：测试数 708→787 passed、0 skipped；"最新优化/最近改动" 行同步本轮内容
- **requirements.txt 过时注释修正**：CI Python 矩阵说明 3.10-3.12 → 3.12-3.14；ruff 安装说明改为固定版本
- **回归**：全量 787 passed, 0 skipped, 1 warning（chromadb 内部 DeprecationWarning，第三方库问题）；`ruff check` / `ruff format --check` / lock 同步校验全部通过

## [0.9.1] - 2026-09-09

### CLI 选项失效修复（state 贯通）
- **--timeout 生效**：此前 `run --timeout` 值传入 `_run_single_task` 后从未被使用，Executor 直接读 `os.getenv("EXECUTION_TIMEOUT", "30")`，绕过了 config 的范围校验。现经 state 新增 `execution_timeout` 字段贯通到 `_executor_node`（优先级：state 注入 > config.EXECUTION_TIMEOUT）
- **--coverage-threshold 生效**：此前该选项仅做 0-100 校验后从未参与任何判定。现经 state 新增 `coverage_threshold` 字段贯通，结果字典新增 `coverage_ok`（无覆盖率数据时为 None 不误判）与 `coverage_threshold` 字段，文本摘要展示达标状态

### 缺陷修复
- **LLM 配置加载遇编号空洞中断**：`config._load_llm_configs` 原实现在首个不完整编号处 `break`，删除中间某个 provider（如 LLM_2）会导致后续编号（LLM_3+）静默失效。改为扫描至上限 32 并跳过不完整编号，结果按原编号顺序保持
- **指数退避公式错误**：`base_agent._retry_with_exponential_backoff` 等待时间误写为 `base_wait**attempt`——默认 base_wait=1 时退化为固定 1s（非文档宣称的 1s/2s/4s），zai 路径 base=5 时膨胀为 5s/25s/125s。修正为 `base_wait * 2**attempt`（1s/2s/4s；zai 5s/10s/20s）
- **Executor 导入替换误伤第三方库**：`_apply_import_replacements` 原用未锚定正则对**全部** import 语句做全局替换，测试代码中的 `import numpy` 等第三方库会被错误改写为被测模块名。现按模块名锚定正则，并经相似度门控（SequenceMatcher ≥ 0.6，如 calculater→calculator）仅替换目标模块名的笔误变体；顺带消除未使用的 `_RE_FROM_REPLACE`/`_RE_IMPORT_REPLACE` 模块级正则

### 代码质量
- **CLI 统计去重**：`run` 命令的 total/passed/failed 此前在 JSON/非 JSON 两个分支各算一次，合并为单一计算点
- **异常处理去重**：`_handle_task_exception` 的 `future.exception()` 从两次调用降为一次并记入日志
- **Executor 小优化**：`_build_sys_path_code` 多目录注入不再产生重复 `import sys` 行；`_parse_coverage` 优先只扫描 TOTAL 汇总行（保留全文扫描兜底）
- **回归**：新增 13 个回归测试（CLI state 贯通 6 + Executor 导入保护 3 + 退避公式 1 + 配置空洞容忍 3），全量 721 passed, 6 skipped；ruff 全绿

## [0.9.0] - 2026-09-09

> 说明：0.4.0–0.8.0 时期的迭代工作记录在 README「迭代优化记录」章节，CHANGELOG 未逐版记录；本版本为最近一次版本发布。

### CI 兼容性与安全扫描修复 (2026-09-09)
- **矩阵与锁定版本对齐**：lock 生成自 Python 3.14 开发环境，`scipy==1.18.0` 要求 `>=3.12`、`pandas/matplotlib` 要求 `>=3.11`，原矩阵 3.10/3.11 装不上锁定版本集。矩阵收窄为 `['3.12', '3.14']`（下限 + 开发环境），Codecov 上传条件同步改为 3.14
- **安全扫描迁移**：废弃的 `safety` 工具（`check` 子命令 2024-06 起不再支持，CI 上退出码 64）替换为 PyPA 维护的 `pip-audit`
- **chromadb 漏洞例外（记录在案）**：`chromadb==1.5.9` 命中 PYSEC-2026-311（=CVE-2026-45829）、CVE-2026-45830/45831/45833 共 4 条已知漏洞，PyPI 上无修复版本（1.5.9 即最新），CI 以 `--ignore-vuln` 显式忽略并注释说明；**后续动作：chromadb 发布修复版后立即升级并移除忽略**
- **pytest-timeout 降级 2.5.0→2.4.0**：2.5.0 已被上游 yank（原因 "accidental breaking change (probably)"），此前 lock 误锁了该 yanked 版本。降级为最新未 yank 的 2.4.0（已验证与 pytest 9.1.1 的 `--timeout` 行为正常）；requirements/lock/本地 .venv 三处同步
- **action 版本升级**：`checkout@v4→v5`、`setup-python@v5→v6`（消除 Node.js 20 弃用告警）
- **CI 测试步骤失败根因修复**：本地无 `.env.local` 的干净仿真（仅 mock `LLM_1_*`）复现出唯一失败用例 `test_contains_expected_models`——它硬编码断言模型名含 `qwen/deepseek/agnes/glm`，CI 的 mock 名 `test-model` 不匹配（环境依赖型测试缺陷）。重构为结构校验（模型名与已配置 LLM 一一对应）+ 无真实厂商配置时 `pytest.skip`；dev 环境（真实 `.env.local`）行为不变
- **CI 测试失败诊断注解**：新增 `if: failure()` 诊断步骤，失败时重跑 `pytest -q --tb=no -rf` 提取 FAILED/ERROR 清单并写 `::error` 注解（check-runs annotations API 公开可读，无需 admin 下载日志）；诊断步骤与测试步骤携带同一套 mock env，避免重跑产生假失败

### CI lock 一致性校验 (2026-09-09)
- **新增 lock 同步校验**：`scripts/check_lock_sync.py`（纯 stdlib），校验 `requirements.txt` 中每项依赖都存在于 `requirements.lock` 且 `==` 锁定版本与 lock 一致；CI 新增 "Check lock sync" 步骤，版本脱节即阻断合并
- **验证方式**：故意把 langgraph 版本改成 9.9.9，脚本正确报"版本脱节"并退出码 1；恢复后通过

### 性能优化 (2026-09-09)
- **ChatOpenAI 客户端复用**：`base_agent._call_llm` 此前每次调用都新建 `ChatOpenAI` 实例（底层 httpx 连接池随之重建，无法复用 TCP/TLS 连接）。新增 `_get_or_create_chat_client`，按 `(model, temperature, api_key, base_url)` 缓存实例（上限 16，FIFO 淘汰），进程内复用连接；客户端线程安全，兼容 `--parallel` 并发
- **zai 路径客户端复用**：`_call_zai` 此前每次调用都新建 `ZhipuAiClient`。经核实 `ZhipuAiClient` 继承自 OpenAI SDK 基类、底层共享线程安全的 `httpx.Client`，故新增 `_get_or_create_zai_client`，按 `(api_key, base_url)` 缓存（model 是请求参数不进键）
- **测试隔离**：`tests/test_base_agent_extended.py` 增加 autouse fixture 清理两套客户端缓存，避免 mock 实例跨测试残留；新增 8 个客户端复用单测（ChatOpenAI 4 个 + zai 4 个，后者通过向 `sys.modules` 注入假 `zai` 模块追踪构造次数）
- **回归**：708 passed, 6 skipped

### CLI 拆包与 CI 修复 (2026-09-09)
- **main.py 拆包为 src/cli/**：507 行的 main.py 拆为 `src/cli/app.py`（命令定义与任务执行）+ `src/cli/output.py`（ANSI/Rich 输出工具），main.py 保留为薄入口，`python main.py ...` 与 setup.py 控制台脚本行为不变；`list-examples` 路径定位改为按项目根计算（拆分前用 `__file__` 指向根目录）
- **修复 CI 格式化门禁**：全仓库 `ruff format` 统一（33 个文件，纯格式变更），此前 `ruff format --check` 步骤必然失败
- **CI 安装步骤去重**：`pytest-cov` 已在 requirements.txt 中锁定，移除 CI 中的重复安装行
- **回归**：700 passed, 6 skipped；`python main.py --help` / `list-examples` 冒烟通过

### 依赖治理 (2026-09-09)
- **顶层依赖锁定**：`requirements.txt` 的 18 个顶层依赖由 `>=` 改为 `==`，版本与 `requirements.lock` 同步，保证 CI（Python 3.10-3.12 矩阵）安装可复现
- **补装 CI 缺失插件**：新增 `pytest-timeout==2.5.0`（`pyproject.toml` addopts 的 `--timeout=1200` 依赖它，此前 CI 安装步骤未包含，pytest 会因无法识别 `--timeout` 参数而失败）
- **移除未使用依赖**：`radon` 全项目无 import 引用，从 `requirements.txt` 与 `setup.py` 移除（注释记录备查）
- **修正过期注释**：`requests` 实际被 `scripts/check_quota.py` 使用，原"未直接使用"注释已更正

### 架构重构与性能优化 (2026-09-09 续)
- **模块归类到子包**：`dataset_loader`/`synthetic_dataset` → `src/datasets/`，`api_manager` → `src/api/`，`config_manager`/`config_generator` → `src/config/`，`exceptions` → `src/utils/`，更新全部导入引用
- **LLM 文件缓存接入**：`base_agent._call_llm_with_cache` 正式接入 planner/generator/debugger，相同 prompt 命中缓存省 token；新增开关 `AITESTER_LLM_CACHE` 与目录 `AITESTER_LLM_CACHE_DIR`（默认启用，测试自动隔离）
- **重写 llm_cache**：`src/graph/llm_cache.py` 由空壳改为可用线程安全 LRU，命中率统计准确（可选内存缓存工具）
- **新增额度探测脚本**：`scripts/check_quota.py`，逐个模型 1-token 探测存活/403 额度/限流/key 失效，不打印密钥
- **模型目录更新**：Agnes 国内站 `agnes-2.5-flash` → `agnes-3.0-flash`；默认模型 `LLM_1` 切至 `agnes-3.0-flash`
- **测试修复**：dataset_loader 接口/环境依赖/下载 mock 修复；全量 700 passed, 6 skipped, 0 failed
- **文档**：README/QUICKSTART/docs 同步架构、缓存、脚本与模型；`.gitignore` 增加 `src/cache/`、`.env.local.bak`

### 代码优化 (2026-09-09)
- **提取公共工具模块**：新增 `src/utils/helpers.py`，统一代码块和 JSON 提取逻辑
  - `extract_code_block()`: 从 LLM 输出中提取代码块（支持多种格式）
  - `extract_json_object()`: 从文本中提取 JSON 对象（含括号平衡法）
- **重构 base_agent.py**：移除重复代码，委托调用公共工具函数（-85 行）
- **重构 patch_applier.py**：使用公共工具函数替代 `_extract_patch_code()`（-34 行）
- **优化 workflow.py**：
  - 移除冗余常量 `_DEFAULT_MAX_ITERATIONS`
  - 简化路径安全检查逻辑（使用 tuple 替代 list）
  - 改进类型注解
- **测试修复**：更新测试文件以适配新的导入路径
- **测试结果**：524 passed, 6 skipped（核心模块 100% 通过）

---

### 代码质量优化
- **修复代码规范问题**：全部 E501 (行长度) 和 C901 (复杂度) 问题已修复
- **重构 config_manager.py**：
  - 提取 `_is_model_config_line()` 辅助函数
  - 提取 `_is_model_comment()` 辅助函数
  - 提取 `_find_and_remove_model_block()` 辅助函数
  - 降低 `remove_llm_config()` 复杂度 (11→9)
- **重构 dataset_loader.py**：
  - 提取 `_load_project_version()` 方法
  - 降低 `Defects4JPYDataset._load_raw_data()` 复杂度 (13→9)
- **修复测试文件**：
  - 简化 test_debugger.py 的 sys.path 导入
  - 修复 test_error_classifier.py 的行长度
  - 修复 test_rag_retriever.py 的长列表定义
  - 修复 test_dataset_loader.py 的测试逻辑

### 测试状态
- 总测试数：686
- 通过：551 (核心测试)
- 跳过：6
- 失败：5 (网络超时，数据集下载测试)
- 覆盖率：70% (核心模块 85%+)

### 代码规范
- ✅ Ruff check 全部通过
- ✅ 行长度 ≤ 120 字符
- ✅ 代码复杂度符合要求

---

## [0.3.0] - 2026-08-18

> 说明：本节工作于 2026-08-18 完成，此前一直挂在 [Unreleased] 未随版本发布，2026-09-09 整理时补记为 0.3.0 并随 0.9.0 一并归档。

### 全量功能验证（2026-08-18）
- **测试结果**：873 个测试用例收集，860 通过（98.6%），12 失败（已知边界问题），1 跳过
- **验证范围**：单元测试 + 集成测试 + CLI端到端 + 模块导入 + 实验脚本
- **已通过模块**：
  - CLI：`run`、`list-examples` 命令正常
  - Agent 层：BaseAgent(46)、ExecutorAgent(30)、PlannerAgent(5)、ErrorClassifier(44)、GeneratorAgent(7)、DebuggerAgent(5)
  - 工具层：CodeAnalyzer(12)、PatchApplier(33)
  - 工作流层：workflow(63)、state(5)、llm_cache(24)
  - 集成测试：integration(52)、e2e(34)、examples(90)
  - API 管理器：APIManager(50，含 22 节点大规模测试)
  - RAG 检索器：retriever(16)、report_generator(43)
  - 数据集：dataset_loader_extended(33)、synthetic_dataset(40)
  - 实验脚本：run_benchmark/run_large_scale/visualize_results/statistical_analysis/analyze_failures 全部可用
- **已知失败**：
  - `test_retriever_extended.py` 6 个（Python 3.14 MagicMock 行为变化）
  - `test_base_agent_zai.py` 2 个（API 配额耗尽）
  - `test_dataset_loader.py` 3 个（HuggingFace mock 配置）
  - `test_concurrent_execution_safety` 1 个（随机性，重跑通过）
- **详细报告**：`FUNCTIONAL_VALIDATION_REPORT_20260818.md`（文件已不在仓库中，仅作记录）

### 新增功能
- **API 管理器增强**：新增 `src/api_manager.py` 模块，支持多 Provider 轮询和高可用故障转移
  - 实现轮询、加权随机、健康感知、最快优先四种策略
  - 支持动态节点添加/移除
  - 自动健康检查与故障转移
  - 新增 31 个单元测试覆盖完整功能
- **LLM 缓存机制**：实现 `src/graph/llm_cache.py`，支持 LLM 调用结果缓存
  - 减少重复 API 调用，节省 token 消耗
  - 提供缓存统计接口
- **错误报告生成器**：新增 `src/reports/` 模块，支持将测试失败信息转化为结构化诊断报告
  - 支持文本、JSON、Markdown 三种输出格式
  - 自动分类错误类型（语法/运行时/断言/超时/未知）
  - 生成根本原因分析和修复建议
  - 集成 `ErrorClassifier` 进行错误分类
  - 新增 13 个单元测试覆盖完整功能
- **多 LLM 配置支持**：`LLM_CONFIGS` 列表支持 API Key 轮询和高可用
  - 配置格式：`LLM_N_API_KEY`, `LLM_N_BASE_URL`, `LLM_N_MODEL_NAME`
  - 向后兼容：保留 `MODEL_NAME`, `OPENAI_API_KEY` 等旧变量名

### 代码质量
- **Ruff 代码格式化**：修复 791 个代码风格问题（导入排序、空白行、过时类型注解等）
- **类型注解现代化**：将 `Optional[X]` 替换为 `X | None`，符合 Python 3.10+ 风格

### 工程化改进
- **Ruff Lint 配置**：新增 `pyproject.toml`，配置 ruff 进行代码检查和格式化（替代 flake8 + isort）
- **Pre-commit Hooks**：新增 `.pre-commit-config.yaml`，集成 ruff、mypy、trailing-whitespace 等检查
- **GitHub Actions CI**：新增 `.github/workflows/ci.yml`，支持多 Python 版本测试、lint 检查和安全扫描
- **pytest 配置**：在 `pyproject.toml` 中配置 pytest 参数（测试路径、标记、输出格式）

### 性能优化
- **RAG 检索器单例化**：将 ChromaDB 客户端改为懒加载单例模式（`src/graph/workflow.py`），节省每个任务 2-6 秒初始化时间
- **LLM_TIMEOUT 配置接入**：在 `src/agents/base_agent.py` 中接入 `LLM_TIMEOUT` 配置，防止 LLM 调用卡死
- **并发执行支持**：实现 `BENCHMARK_PARALLELISM` 环境变量驱动的多线程并行基准测试（`experiments/run_benchmark.py`）
- **Parametrize 重试逻辑优化**：修复 `src/agents/generator.py` 中 parametrize 校验失败时使用相同 query 重试的问题，改为追加负面反馈提示
- **Executor 导入路径搜索优化**：限制 `_auto_fix_imports` 的全量 rglob 遍历，优先检查常见路径（`src/`, `lib/`, 当前目录），提升 98.6%

### Bug 修复
- **指数退避重试逻辑**：修复 `src/agents/base_agent.py` 中的重试退避策略
- **路径安全检查**：增强 `src/tools/patch_applier.py` 的路径验证，防止路径遍历攻击
- **模块导入路径搜索优化**：限制 `_auto_fix_imports` 的全量 rglob 遍历，优先检查常见路径（`src/`, `lib/`, 当前目录）

### 文档更新
- **README.md**：添加性能优化说明章节，包括 RAG 单例化、LLM_TIMEOUT 配置、并发执行使用指南
- **README.md**：更新快速开始部分，新增并发执行命令示例
- **README.md**：更新配置说明表格，补充 LLM_TIMEOUT 和 LLM_RETRY_WAIT 配置项
- **README.md**：更新迭代优化记录，添加 v0.10 和 v0.9 变更记录
- **README.md**：更新测试状态表格，反映最新测试结果（696+ passed）
- **CHANGELOG.md**：添加多 LLM 配置支持说明
- **新增文档**：`docs/performance_optimization_report.md`、`docs/report_generator_guide.md`、`API_MANAGER_EXTENSION_GUIDE.md`（该批文件后续已清理出仓库，此处仅作历史记录）
- **迭代报告**：`ITERATION_REPORT_20260818.md`、`FINAL_ITERATION_SUMMARY.md`、`ITERATION_REPORT_ROUND2.md`（该批文件后续已清理出仓库，此处仅作历史记录）
- **架构文档**：更新 `docs/algorithm_design.md`，反映 RAG 单例化改动

## [0.2.0] - 2026-08-17

### 工程化改进
- **Ruff Lint 配置**：新增 `pyproject.toml`，配置 ruff 进行代码检查和格式化
- **Pre-commit Hooks**：新增 `.pre-commit-config.yaml`，集成 ruff、mypy、trailing-whitespace 等检查
- **GitHub Actions CI**：新增 `.github/workflows/ci.yml`，支持多 Python 版本测试、lint 检查和安全扫描
- **pytest 配置**：在 `pyproject.toml` 中配置 pytest 参数（测试路径、标记、输出格式）

### 文档更新
- **README.md**：更新测试状态表格，集成测试已标记为通过（52 passed）
- **README.md**：新增「开发工具」章节，包含 Ruff lint、Pre-commit hooks、CI/CD、测试命令说明
- **CHANGELOG.md**：按 Keep a Changelog 格式规范更新

### 测试状态
- 单元测试：215 passed（含集成测试）
- 无硬编码密钥
- 代码覆盖率 75%（目标 80%+）

---

## [0.1.0] - 2026-08-14

### 新增
- 初始版本发布
- 四智能体协作架构（Planner → Generator → Executor → Debugger）
- 支持 examples、synthetic、swe_bench 三种数据集
- Docker 一键复现支持
- 完整单元测试（185 个用例，17 个测试文件）

---

## 版本说明

- `Unreleased`: 当前开发中功能，尚未正式发布
- 版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)
