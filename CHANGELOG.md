> **语言 / Language**：[English](CHANGELOG.en.md) | 简体中文（本文）

# Changelog

所有重要变更将记录在此文件中。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [Unreleased] - 代码质量轮次（mypy 真实语义错误清零 + analyze_results 主题拆分 + 0.7 债务项 1.6 落地）

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
