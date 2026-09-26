# P0 改进批次实施清单（2026-09-25 续）

> 对应实验数据缺口（SWE-bench 0/20、合成集统计已覆盖但真实集 A/B 缺失）与
> `docs/assessment_2026-09-25_improvement_directions.md` 的改进路线。
> 本批次落地 13 项 P0 改进，全部默认行为兼容（默认参数回退历史口径，显式开启才启用新能力）。

## 改动一览（13 项）

### 1. 1.1 分层代码压缩（函数级切片 + 调用链深度）
- **新增** `src/tools/code_analyzer.py::extract_function_context(source_code, func_name, depth=2, max_chars=3000)`：
  委托 `extract_focused_code()`，函数不存在或源码不可解析时返回 None（交由字符级兜底）。
- **修改** `src/tools/code_context.py`：
  - 新增 `_closure_names(focus, top_level_funcs, depth)`：BFS 构建焦点函数的调用链闭包
    （depth=1 直接依赖，depth>=2 逐层展开被调函数自身依赖），key 集即"保留哪些函数"的完整集合。
  - `extract_focused_code()` 新增 `depth` 参数（默认 1 保持历史行为）；
    `_trim_focus_related` / `_apply_focus_budget` 接受 `depth` 透传。
- **修改** `src/agents/base_agent.py::truncate_code(code, max_chars=None, focus_function=None, focus_depth=None)`：
  新增 `focus_depth` 参数（读 `CODE_FOCUS_DEPTH` 环境变量，默认 1）；
  `_CODE_MAX_CHARS` 改读 `CODE_MAX_CHARS` 环境变量（默认 3000）。
- **配置**：`CODE_FOCUS_DEPTH`（默认 1）/ `CODE_MAX_CHARS`（默认 3000）。

### 2. 1.2 复杂度感知路由（固定 Agnes 3.0-flash 多 provider 端点）
- **新增** `src/api/complexity_router.py`：
  - `ComplexityScore` dataclass（score / class_name / breakdown）；
  - `compute_complexity_score(lines, num_files, num_deps, cyclomatic_complexity)`：
    四维归一化（阈值由 `ROUTING_COMPLEXITY_LINES_NORM` 等环境变量可配），
    评分 <0.35 → simple / <0.70 → medium / >=0.70 → complex；
  - `complexity_class_to_routing_hints(class)`：返回路由提示
    （`max_candidates` / `extra_iteration` / `context_budget` / `hint_text`）；
  - `routing_enabled()` / `routing_strategy()`：读 `MODEL_ROUTING_STRATEGY`（默认 complexity_aware）。
- **修改** `src/api/api_manager.py`：
  - `_build_node_list(model, complexity_class)` 新签名；
  - `_select_node_by_complexity(complexity_class)`：按 cost_weight 排序 APIHealth 节点
    （complex → 高 cost_weight 在前，simple → 低 cost_weight 在前）；
  - `call()` 从 kwargs 提取 `complexity_class` 透传。
- **修改** `src/agents/base_agent.py::_call_llm(..., complexity_class=None)`：
  complexity_class 非 None 且多 provider 时调用 `_reorder_api_groups_by_complexity` 重排 API 组。
- **修改** `src/graph/state.py`：新增 `complexity_class` / `complexity_score` /
  `complexity_breakdown` / `routing_hints` 字段 + `create_initial_state` 初始化。
- **修改** `experiments/run_benchmark.py`：在 `create_initial_state` 后计算复杂度评分并写入 state。

### 3. 1.3 补丁命名契约验证（默认开启）
- **修改** `src/tools/patch_applier.py`：
  - `_collect_module_level_symbols(code)`：AST 提取模块级符号（函数/类/__all__/注册装饰器/模块级常量）；
  - `check_naming_contract(original_code, patched_code) -> (bool, list[str])`：
    对比前后符号，返回 (通过, 缺失符号列表)；
  - `safe_apply_patch_contract(code, patch, enforce_contract=True)`：
    在 `safe_apply_patch` 之上叠加命名契约检查。
- **修改** `src/graph/nodes.py::_patch_applier_node`：`PATCH_CONTRACT_CHECK=true`（默认）
  时在写盘前调用 `check_naming_contract`，缺失符号则拒绝补丁并记录到 repair_history。
- **修改** `src/agents/debugger.py::debug()`：prompt 注入 `_CONTRACT_CONSTRAINT`
  （"不得修改或删除以下符号……"），从生成侧降低违约概率。

### 4. 2.1 合成数据集分层难度
- **修改** `src/datasets/synthetic_dataset.py`：
  - `SyntheticDataset.__init__(task_count, seed, subset, difficulty="mixed", **kwargs)`：
    新增 `difficulty` 参数（mixed / level1 / level2 / level3 / level4）；
  - 新增 `BUG_PATTERNS_LEVEL2`（多函数交互缺陷）/ `CROSS_FILE_PATTERNS`（跨文件双模块）/
    `BUG_PATTERNS_LEVEL4`（边界+异常隐蔽缺陷）模板库；
  - `_difficulty_sequence()` / `_pick_pattern()` / `_load_raw_data()` 按难度生成任务；
  - Level 3 任务 metadata 含 `is_cross_file=True` / `module_a_code` / `target_module` /
    `fixed_module_b_code` / `num_files=2`。
- **修改** `experiments/run_benchmark.py`：CLI 新增 `--difficulty` 选项（仅对 synthetic 生效），
  `run_benchmark()` 新增 `difficulty="mixed"` 参数透传到 `SyntheticDataset`。

### 5. 2.2 跨文件合成任务构造
- Level 3 任务由 `CROSS_FILE_PATTERNS` 双模块模板生成（见 §4），
  `instance_code=module_b_code`（含缺陷的被调方），`metadata.module_a_code` 传入口模块，
  修复需改 module_b 接口 → 验证跨文件修复架构（协调器-提议者，依赖边 module_a → module_b）。

### 6. 2.3 SWE-bench 源码导出质量验证
- **新增** `scripts/verify_swe_bench_export.py`：
  - `verify_enrichment_file(enrichment_path, instances_path=None, min_lines=5)`：
    5 维度验证（非空 / 行数 / Python 语法 / 目标函数存在 / 目标文件路径匹配）；
  - `build_quality_report(verifications)`：输出 `pass_rate` / `by_label` /
    `failed_instances` / `avg_line_count` 结构化报告；
  - CLI：`--enrichment`（必填）/ `--instances`（可选，交叉验证）/ `--output`（JSON 路径）/
    `--min-lines`（行数阈值，默认 5）。

### 7. 3.1 RAG A/B 对比实验脚本
- **新增** `experiments/rag_ab_experiment.py`：
  - `_run_benchmark_once(...)`：调用 `run_benchmark.py` 两次（RAG ON / RAG OFF）；
  - `compare_ab(rag_on_records, rag_off_records)`：配对分析 token / 成功率 / 迭代 / 耗时，
    Welch t-test + Mann-Whitney U + Cohen's d 统计检验（与 0.7 报告同口径），
    按错误类型分组分析 RAG 收益（哪类错误在 RAG ON 下显著减少）；
  - CLI：`--dataset` / `--task-count` / `--seed` / `--output-dir` / `--baseline` /
    `--analyze-only`（读已有结果 JSON 直接统计，跳过实验运行）/
    `--results-rag-on` / `--results-rag-off`。
  - 输出：`rag_ab_report.json`（含 interpretation 自动解读）。

### 8. 3.2 多候选自适应触发
- **修改** `src/graph/nodes.py::_select_multi_candidate_patch(state, original_code, iteration=0)`：
  新增 `iteration` 参数；`MULTI_CANDIDATE_TRIGGER_STRATEGY=adaptive`（默认）时仅当
  `iteration >= 1` 且 `error_category ∈ {assertion, runtime, logic_error, index_error}`
  （困难类别）才启用多候选；简单任务 / 早期迭代保持单候选省 token。
  设 `always` 回退历史口径（每次失败都启用）。

### 9. 3.3 变异体难度升级
- **修改** `experiments/mutation_testing.py`：
  - 新增 `_ReturnEmptyTransformer`（return X → return 空容器，`return_empty` 变异体）；
  - 新增 `_RemoveRaiseTransformer`（删除 raise 语句，`exception_remove` 变异体）；
  - 新增 `_ExceptionTypeTransformer`（异常类型替换，`exception_type_swap` 变异体）；
  - `MutationGenerator.generate()` 扩展 `return_empty` / `exception_remove` / `exception_type_swap`
    三类，总变异体类型从 5 扩至 7（operator_flip / boolean_negation / numeric_offset /
    boundary_shift / return_void / return_empty / exception_remove / exception_type_swap）；
  - 修复 `_find_mutable_comparison_nodes` 与 `_OPERATOR_FLIP_MAP` 合并 bug。

### 10. 4.1 错误分类子类 + 响应格式重试
- **修改** `src/agents/error_classifier.py`：
  - `ErrorCategory` 新增 `LLM_EMPTY_RESPONSE` / `LLM_JSON_PARSE_FAILED`
    （从 `LLM_FORMAT_ERROR` 拆出的两个精确子类，14 类 → 16 类）；
  - `ErrorClassifier.classify_llm_response(raw_response)` 新方法：
    直接分析 LLM 原始响应（空 → LLM_EMPTY_RESPONSE；非空但 JSON 提取失败 →
    LLM_JSON_PARSE_FAILED；正常 → LLM_FORMAT_ERROR）；
  - `_FIX_STRATEGIES` 新增两个子类的独立修复策略（更严格 prompt 重试 /
    记录原始响应片段到 failure_knowledge_base.json）。
- **修改** `src/agents/debugger.py::debug()`：检测到格式异常时用更严格 prompt
  自动重试一次（`_strict_retry_query` 附加 JSON 输出格式约束），仍失败则降级到宽松 JSON 提取。

### 11. 4.2 追踪层默认启用
- **修改** `experiments/run_benchmark.py`：入口处若 `AITESTER_TRACE_DIR` 未设（或为空），
  自动设为 `<output_dir>/traces/`（默认启用追踪层）；节点级 JSONL 记录（输入长度、
  输出长度、token、耗时、路由决策）随工作流执行自动追加到 `<task_uuid>.trace.jsonl`。
  设 `AITESTER_TRACE_DIR=`（空串）显式关闭。

### 12. 4.3 venv 按仓库复用
- **修改** `src/agents/executor_repo.py::RepoExecutor`：
  - 新增 `venv_reuse_by_repo: bool = False` 参数；
  - `_repo_venv_dir(repo_url, repo_dir)`：计算仓库级共享 venv 路径
    （`<env_root>/<repo>/_shared_venv/`）；
  - `_dep_fingerprint(repo_dir)`：计算依赖指纹（SHA256 of requirements*.txt +
    pyproject.toml + setup.py + setup.cfg）；
  - `setup()` 在 `venv_reuse_by_repo=True` 时：依赖指纹未变 → 复用共享 venv
    （跳过 pip install -e），仅写环境标记；依赖指纹变更 → 重新 pip install -e 并更新指纹；
  - `_venv_python(env_dir, repo_url, repo_dir)`：按 `venv_reuse_by_repo` 解析共享 venv 路径；
  - `_run_fail_to_pass` / `_run_pass_to_pass` / `_run_test_nodes` 新增 `repo_url` 参数
    透传到 `_venv_python`。

### 13. 文档与测试同步
- **修改** `README.md`：错误分类 14→16 类 + 新增 §5.21 P0 改进批次（13 项）+
  更新"最新优化"/"最近改动"行。
- **修改** `.env.example`：新增 P0 批次环境变量（CODE_FOCUS_DEPTH / CODE_MAX_CHARS /
  MODEL_ROUTING_STRATEGY / ROUTING_COMPLEXITY_*_NORM / PATCH_CONTRACT_CHECK /
  MULTI_CANDIDATE_TRIGGER_STRATEGY / SWE_REPO_VENV_REUSE_BY_REPO）+
  AITESTER_TRACE_DIR 默认启用说明。
- **修改** `tests/test_error_classifier.py`：枚举 14→16 类断言 + P0 4.1 子类存在性校验。
- **修改** `tests/test_synthetic_dataset.py`：difficulty 分层测试 + 跨文件 Level 3 结构校验。
- **修改** `tests/test_workflow_extended.py`：多候选自适应策略环境变量（`MULTI_CANDIDATE_TRIGGER_STRATEGY=always` 历史口径）+
  `_select_multi_candidate_patch` 签名（`iteration` 参数）。
- **修改** `tests/test_executor_repo.py`：`_run_test_nodes` mock 签名（`repo_url` 参数）。

## 验证
- 全量回归：`python3 -m pytest tests/ -q` → **1667 passed, 47 skipped**（同基线）
- 受影响子集：
  - test_base_agent（40）/ test_code_context（18）/ test_error_classifier（77）/
  - test_debugger（38）/ test_workflow_extended（37）/ test_executor_repo（17）/
  - test_synthetic_dataset（5）/ test_api_manager + extended（152）/ test_code_analyzer（17）

## 已知限制
- **1.2 复杂度路由**：`complexity_class` 经 `state["complexity_class"]` 写入但
  planner / generator / debugger 节点尚未消费（路由效果当前经
  `base_agent._reorder_api_groups_by_complexity` 的 env-var 驱动重排实现，
  state 字段供未来节点级消费预留）。
- **4.2 追踪层默认启用**：`run_benchmark.py` 入口处设置 `AITESTER_TRACE_DIR` 环境变量，
  若用户已显式设置（含空串）则不覆盖。追踪目录默认在 `<output_dir>/traces/`，
  需与结果 JSON 同目录管理。
- **4.3 venv 按仓库复用**：仅对 `REPO_LEVEL_EXECUTION=true` + `SWE_REPO_VENV_ISOLATION=true`
  的 SWE-bench 仓库级验证场景生效；合成集 / examples 无仓库环境，永不命中。
