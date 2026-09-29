# AITester 前沿建议逐项核查差距报告（2026-09-28）

> 核查对象：用户提供的"九大维度优化建议"（测试预言生成 / 执行感知修复 /
> 多语言扩展 / RAG 与上下文 / 可观测性与缓存 / 并行专家协作 / 安全沙箱 /
> 基准测试与路由）。
> 方法：逐条对照当前代码库与文档核实（证据标注 `文件:行号` 或文档章节），
> 判定 **已实现 / 部分实现 / 未实现**。
> 核查日期：2026-09-28 ｜ 仓库：AITester（2026-09-28 改进批次全量落地之后，
> 全量 2165 测试通过，ruff / mypy 全绿，见 [BASELINE.yaml](../../BASELINE.yaml)）。
> 结论摘要：**九大方向中的核心能力均已有对应模块落地**（多数默认关、
> 带独立开关，遵循 ADR-0003/0004 口径）；剩余缺口集中在少数"未编码"
> 子项上（见下方 §9 缺口清单与优先级矩阵）。

---

## ① 测试预言生成与增强 —— ✅ 已实现

| 建议项 | 现状 | 证据 |
|---|---|---|
| 规约驱动预言增强（JavaOracle 同思路） | ✅ | `src/agents/oracle_enhancer.py`（`OracleEnhancerAgent.enhance`：以 Planner 的 logic_analysis 前置/后置条件 + 边界情况为规约输入，LLM 推理强化断言预言，产出 `oracle` / `oracle_source`（postcondition/edge_case/invariant/unknown）/ `oracle_confidence`，按 case_name 对齐回写，LLM 失败保守降级不阻断主流程） |
| 预言有效性评估（区分"通过"与"有效"） | ✅（观测层口径） | 同上：`oracle_confidence` LLM 自评 0.0–1.0，供实验统计"弱预言占比"；纯观测，不参与路由 |
| 默认关 + 独立开关 | ✅ | `ORACLE_ENHANCE_ENABLE=false`（默认），`oracle_enhance_enabled()` 在 `oracle_enhancer.py:50` |
| 测试用例最小化 / 缺陷报告生成 | ⚠️ 未实现 | 建议项中未单列落地；现有 `reports/generator.py` 覆盖报告生成，但"缺陷报告"维度未接 |

## ② 代码修复：执行感知的仓库级修复 —— ✅ 已实现

| 建议项 | 现状 | 证据 |
|---|---|---|
| 运行时探针采集层（TraceRepair Probe Agent 思路） | ✅ | `src/agents/runtime_probe.py`（`capture_failure_snapshot`：pytest 失败时刻经 `sys.settrace` 一次性探针捕获失败帧局部变量快照，帧数/变量数/值大小双重上限防 prompt 爆炸；`build_probe_prompt_section` 渲染注入 DebuggerAgent；纯观测层，快照失败静默降级；`RUNTIME_PROBE_ENABLE` 默认关） |
| 策略银行（工具调用轨迹挖掘失败签名） | ✅ | `src/tools/strategy_bank.py`（"失败签名 (error_category, fix_strategy_tag, cross_file) → 策略"静态映射 + 预算提示；在线 `select_strategy` 只读，离线 `record_strategy_outcome` 追加累积；与 `failure_kb`（失败案例知识库）构成"案例层 + 策略层"两级反馈；`STRATEGY_BANK_ENABLE` 默认关） |
| 多策略辩论修复（TraceCoder 思路） | ⚠️ 部分 | `strategy_bank.py` 文档明确记录该框架思想为本模块设计依据；但"多 Agent 辩论"本身未实现为独立模块——**近似替代**为 `src/graph/expert_pool.py` 并行专家池 + 交叉验证（见 ⑥），及 `src/tools/multi_candidate.py`（同策略多候选 + 静态筛选 + 奖励预测 `predict_candidate_rewards`）；"辩论"（多候选互辩收敛）为可选增强，未编码 |
| 跨文件修复引擎"真实数据正向收益"验证 | ⚠️ 未验证 | 架构侧（`src/tools/cross_file.py` 依赖分析 + 拓扑序多文件补丁 + 修复计划缓存）已就绪；`docs/assessment_2026-09-25_improvement_directions.md` §2.2 仍记录 7 个单源 SWE-bench 任务 0/7 的引擎能力边界；运行时探针 + 策略银行为默认关，**尚未有开启全链路后的复测数据** |

## ③ 多语言扩展：语言无关架构 —— ✅ 部分实现（Tree-sitter 为可选后端，未接入）

| 建议项 | 现状 | 证据 |
|---|---|---|
| 语言无关分析层（接口契约对齐） | ✅ | `src/tools/language_backend.py`（`LanguageBackend` 协议：`extract_symbols` / `extract_call_graph` / `check_naming_contract`，与 Tree-sitter 后端接口契约对齐；`register_backend` / `get_language_backend` 注册机制；已内置保守词法层 TypeScript 后端，`AITESTER_ENABLE_TYPESCRIPT_BACKEND` 默认关，缺依赖透明降级不阻断 Python 主路径） |
| Tree-sitter 精确 AST 后端 | ❌ 未实现 | 设计文档 `docs/design/multilanguage_extension.md` 将其列为"可选扩展后端"（Design-only）；仓库无任何 `tree_sitter` 依赖引用 |
| 六维语义子分析器（MatchFixAgent 思路） | ❌ 未实现 | 无对应模块 |
| 语言无关补丁应用层 | ✅ | `patch_applier.check_naming_contract` 的拒绝 + 重采样骨架已按"各语言后端实现 `check_naming_contract`"的契约设计（`language_backend.py:21-26`），跨语言守卫可直接复用 |

## ④ RAG 与上下文管理 —— ✅ 已实现（结构化图检索 + 分层压缩均已落地）

| 建议项 | 现状 | 证据 |
|---|---|---|
| GraphRAG（调用/依赖图结构化索引 + 混合检索） | ✅ | `src/tools/graphrag.py`（`GraphRAGIndex` 进程内结构图：从 `cross_file` 依赖边 / 语言后端调用图构建邻接表 + 符号表；`hybrid_retrieve` N 跳子图 + 文本片段 + 符号锚点；`build_graphrag_prompt_section`；零 LLM 成本；`GRAPH_RAG_ENABLE` 默认关，检索失败降级回纯文本 RAG） |
| 轮次间历史上下文压缩（Contextual Memory 思路） | ✅ | `src/tools/hierarchical_summary.py`（Level 0 原文 / Level 1 函数级 / Level 2 模块级 / Level 3 文件级分层摘要 + 降级链，超限才退化为字符截尾；`summarize_code` / `truncate_code_with_summary`；`HIERARCHICAL_SUMMARY_ENABLE` 默认关） |
| Section-Scoped 结构图检索（Blueprint 多仓库分段作用域） | ⚠️ 部分 | GraphRAG 为进程内全局索引，无"多仓库工作区分段作用域 + 后轮次压缩"维度 |
| 多规则潜在推理剪枝（仓库读取 Token 节省） | ⚠️ 未单列 | `hierarchical_summary` + `truncate_code` 三级降级链 + `cost_budget`（任务级 token 预算硬上限，`COST_BUDGET_ENABLE`）已覆盖主要 Token 效率目标；未做"多轮读取剪枝"独立规则引擎 |

## ⑤ 可观测性与成本控制 —— ✅ 已实现（双套缓存统一已完成）

| 建议项 | 现状 | 证据 |
|---|---|---|
| 结构化执行轨迹导出（节点输入/输出/耗时/Token/决策路径） | ✅ | `src/observability/trace.py`（`TraceSession.record_node` 记录 `input_summary` / `output_summary` / `decision` / `decision_reason` / `strategy_selected` / `budget_remaining` / `token_usage` 增量 + 墙钟耗时，JSONL 旁路落盘（`trace_dir()`）；脱敏三层防线；`memory_buffer_snapshot` / `dump_recent_to` 支持失败时 `--dump-trace-on-failure` 快照；`TraceSession` 模块覆盖率 98%） |
| Agent 特有失败模式检测（AgentTelemetry 基准思路） | ⚠️ 未实现 | 无 AgentTelemetry 类基准接入；现有 `rogue_monitor.py` / `injection_guard.py` / `deterministic_guard.py` 覆盖部分 agent 失败模式，但不是"故障检测基准" |
| 双套缓存统一（进程内 LRU 与文件缓存） | ✅ 已完成 | CHANGELOG 0.7 批次："删除死模块 `src/graph/llm_cache.py` 与 `tests/test_llm_cache.py`（16 用例）"；现生产链路单一文件缓存口径（`src/agents/llm_client.py`：`ensure_llm_cache_dir` / 0600 权限 / TTL 清理 `cleanup_expired_cache_files` / 多进程命中率协调 `record_cache_hit` / `get_cache_hit_rate`） |

## ⑥ 多智能体协作架构 —— ✅ 已实现（风险分级人工回路未单列）

| 建议项 | 现状 | 证据 |
|---|---|---|
| 并行专家 Agent 池 | ✅ | `src/graph/expert_pool.py`（`ExpertPoolAgent.generate_parallel`：ThreadPoolExecutor 并发 N 个专家子 Agent，各聚焦边界处理/类型安全/死代码逻辑三维度（`_EXPERT_DIMENSIONS`，N 默认 3、上限 7）；单专家超时/失败保守降级；`EXPERT_POOL_ENABLE` / `EXPERT_POOL_SIZE` / `EXPERT_POOL_TIMEOUT` 默认关） |
| 交叉验证边（多 Agent 互验过滤误报） | ✅ | `ExpertPoolAgent.cross_validate`（AST 归一化 + 两两一致性投票，`verified_count` / `agreed_dimensions`，按"被验证数 + 置信度"排序，`min_agreement` 过滤误报，零额外 LLM 成本，Anthropic Code Review 同口径） |
| MCP 服务器解耦工具 | ❌ 未实现 | 仓库无 MCP 实现（仅文档提及 K11tech 作为参照） |
| 风险分级人工回路（低/中/高风险自动升级） | ❌ 未实现 | 无 `HUMAN_APPROVAL` / 风险分级升级规则模块；现有 `error_classifier.classify_with_confidence` 置信度分层 + L2 协议预留是最近的相邻能力 |

## ⑦ 安全沙箱 —— ✅ 部分实现（容器级网络出口管控已落地；内核级隔离未实现）

| 建议项 | 现状 | 证据 |
|---|---|---|
| venv 隔离 | ✅ | `RepoExecutor` venv 隔离（解决跨 commit 全局 Python 环境污染），`executor_modes.py` 沙箱目录 + `cleanup_sandbox` |
| 容器级隔离 + 网络出口控制 | ✅ | `src/agents/executor_modes.py:292-323`（`_execute_docker`：`DOCKER_NETWORK_ISOLATION=true` → `--network=none` 全断网；`allowlist` 模式 → `DOCKER_NETWORK_ALLOWLIST` host:port 白名单 + bridge（白名单空时保守降级 `--network=none`，注释明确"以为配了出口管控其实全放"是最大敞口）；`docker_network_obs` 观测字段回写） |
| 内核级沙箱（Seatbelt / Landlock / seccomp / gVisor / microVM） | ❌ 未实现 | 全仓无 `seccomp` / `landlock` / `seatbelt` / `gVisor` / `firejail` / `nsjail` 引用 |
| Fail-Closed 治理协议（TOCTOU / harness CVE 类别） | ⚠️ 部分 | `credential_scrub.py`（三条执行链路统一剔除 LLM 凭证，100% 覆盖）与凭证编号变体 P0 补强属同思路纵深，但未形成"跨供应商允许协议" |

## ⑧ 基准测试与路由 —— ✅ 已实现

| 建议项 | 现状 | 证据 |
|---|---|---|
| SWE-bench Pro 高难度评估维度 | ✅ | `src/datasets/dataset_loader.py`（`swe_bench_pro` / `swebench_pro` 注册，复用 `SWEBenchDataset`，`data_dir` 注入）；`src/tools/contamination_check.py`（`CONTAMINATION_RESISTANT_BENCHMARKS` 含 `swe-bench-pro` 条目：强 copyleft 设计 + GPT-5 Pass@1 ~23.3% + `recommended_pairing=swe-bench-verified`） |
| 多维度污染检测（语义/结构/基准） | ✅ | `contamination_check.py`（`_detect_semantic_cosine` CodeBERT 嵌入 + 词袋回退；`_detect_ast_skeleton_similarity` AST 语句序列 LCS；`_combined_risk_level` 三维最严重口径；每任务 `contamination_risk_level` 入 `run_benchmark._build_task_result`） |
| 执行无关的修复验证（PegasusAgent 思路） | ❌ 未实现 | 无 testless 验证模块；修复验证仍以 pytest 执行 + 静态守卫（`patch_postprocess.sanitize_patch` / `static_validate_patch`）为主 |
| 模型路由按复杂度分级 | ✅ | `src/api/complexity_router.py`（四维度复杂度评分 + `simple/medium/complex` 档位 + 路由提示；`MODEL_ROUTING_STRATEGY=complexity_aware` 默认，`fixed` 回退；`APIManager._select_node_by_complexity` 按档位选节点）；最新模型能力数据（2026-03）未内置，路由阈值仍为静态经验值 |

## ⑨ 缓存与 Token 效率（建议单列项） —— ✅ 已实现

| 建议项 | 现状 | 证据 |
|---|---|---|
| LLM 缓存安全（0600 / TTL / 原子写） | ✅ | `llm_client.ensure_llm_cache_dir`（0600）/ `cleanup_expired_cache_files`（TTL）/ 原子替换写（README 安全审查行） |
| 多进程缓存命中率协调 | ✅ | `llm_client.record_cache_hit` / `get_cache_hit_rate` |
| 任务级 token / 费用预算硬上限 | ✅ | `src/graph/cost_budget.py`（`COST_BUDGET_ENABLE`，`cost_budget.get_budget_stats()["remaining_tokens"]` 接入 `TraceSession.record_node` 的 `budget_remaining`） |

---

## 缺口清单（真正未编码部分）

按"是否影响主链路 / 工作量 / 收益"排序：

| # | 缺口 | 所属建议维度 | 缺口性质 | 落地建议 |
|---|---|---|---|---|
| G1 | **Tree-sitter 精确 AST 后端**（语言无关分析层的可选实现） | ③ | 接口契约已就绪，缺一个后端实现 | 在 `language_backend.py` 注册机制下新增 `TreeSitterBackend`（可选依赖 `tree-sitter` + 各语言 grammar，缺依赖透明降级），先接 1 门语言（TS/Go）验证契约 |
| G2 | **风险分级人工回路**（低/中/高风险自动升级规则） | ⑥ | 全新模块 | 基于 `error_classifier.classify_with_confidence` 置信度 + 补丁影响面（`patch_applier` 变更行数/文件数）+ `cost_budget` 消耗，三因子打分定级：低→自动合入，中→人工确认，高→强制审查；CLI 增加 `--approval-mode` |
| G3 | **内核级沙箱**（Seatbelt / Landlock / seccomp） | ⑦ | 全新模块 | 本地（macOS/Linux）执行链路在 Docker 之外增加内核隔离层 + 凭证目录拒绝 + 出口允许列表；作为 `EXECUTOR_SANDBOX_LEVEL=kernel` 独立开关 |
| G4 | **AgentTelemetry 故障检测基准**（Agent 特有失败模式识别） | ⑤ | 全新模块 | 在 `trace.py` JSONL 上建立"失败签名 → 已知模式"匹配器（与 `strategy_bank` 签名同构），产出 Agent 特有失败模式周报 |
| G5 | **执行无关（testless）修复验证** | ⑧ | 全新模块 | 静态层（AST 符号守卫 + mypy + 契约回归）+ 轻量动态层（导入冒烟）组合验证，不依赖测试执行，用于企业级无测试仓库 |
| G6 | **多 Agent 辩论修复**（独立于专家池交叉验证） | ② | 增强 | 在 `expert_pool.cross_validate` 之上增加"互辩收敛"轮次（候选互引对方补丁弱点重新生成 1 轮）；默认关 |
| G7 | **缺陷报告生成**（预言有效性维度的报告出口） | ① | 小 | `reports/generator.py` 增加"弱预言占比 / oracle_confidence 分布"报表节 |
| G8 | **SWE-bench Pro 复测**（开启探针 + 策略银行后验证引擎能力天花板） | ②⑧ | 实验 | 全开 `RUNTIME_PROBE_ENABLE` + `STRATEGY_BANK_ENABLE` + `EXPERT_POOL_ENABLE`，跑 `swe_bench_pro` 数据目录。**2026-10 更新**：数据阻塞已通过 SWE-bench lite（dev split）20-task sqlfluff 子集解决（`data/swe_bench_lite_g8_ready.jsonl`，门禁通过 20/20）；`run_full_stack_swe_bench_pro.py` + `RepoExecutor` 仓库级验证链路已全链路打通（n=3 + n=2 两次复测）。当前结果：免费档 `agnes-3.0-flash` 对真实 sqlfluff 仓库 0% 成功率（全部 `patch_validation_failed`，`llm_applied=False`，FAIL_TO_PASS 基线全挂），失败根因为 LLM 能力边界（非管道缺陷），与 `failure_analysis.md` 0/7 `LLM_BREAKS_IMPORT` 归因一致。**更强模型（GPT-4 级）下数据单独落 `experiments/results/experiment_report_<date>_repo_level.md`**。 |

## 优先级建议矩阵（更新版）

| 优先级 | 缺口 | 预期影响 | 依赖 |
|---|---|---|---|
| P0 | G8 全开链路 Pro 复测（先于 G1，验证现有引擎 + 默认关模块开启后的真实收益） | 把 ② 从"架构就绪"推进到"数据说话"；为路由阈值提供最新数据 | G8 需 Pro 数据目录；其余能力已就绪 |
| P0 | G2 风险分级人工回路 | 自主运行安全兜底；与 `credential_scrub` / `cost_budget` 组合成"可信赖自动化" | 低（复用现有置信度 + 预算信号） |
| P1 | G3 内核级沙箱 | 本地执行链路安全纵深（Docker 出口管控已有，缺内核层） | 中（平台相关：macOS Seatbelt / Linux Landlock+seccomp） |
| P1 | G1 Tree-sitter 后端 | 多语言扩展边际成本下降；契约已对齐 | 中（可选依赖 + 每语言 grammar） |
| P1 | G4 AgentTelemetry 匹配器 | 失败模式规模化调试；喂数据给 `strategy_bank` | 低（纯离线，基于现有 JSONL） |
| P2 | G5 testless 验证 | 企业级无测试仓库场景 | 中 |
| P2 | G6 辩论轮次 / G7 缺陷报告 | 边际收益增强 | 低 |

> 与用户原建议矩阵的差异说明：原矩阵中 P0/P1/P2 的**主体条目在仓库中
> 均已编码完成**（多数默认关、带独立开关，遵循"默认行为不变 + 独立开关"
> 的 ADR-0003/0004 口径）；本报告将优先级矩阵重排为**剩余缺口**视角，
> 并把"全开链路 + SWE-bench Pro 复测"（G8）提为 P0——它是判断
> ②⑦⑧ 方向是否真正产生正向收益的唯一数据入口。

---

*配套证据文件：`docs/roadmap_2026-09-27_gap_audit.md`（前一批七节落地核查）、
`docs/assessment_2026-09-25_improvement_directions.md`（§2.2 引擎能力边界记录）、
`BASELINE.yaml`（当前基线 2165 测试 / 覆盖率 / 静态检查数字）。*
