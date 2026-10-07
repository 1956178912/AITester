"""
全局状态定义模块：所有智能体之间通过此状态传递信息。

使用 TypedDict 确保类型安全，字段说明详见类文档字符串。
新增 error_category、rag_references 字段支持分层修复和检索增强生成。
"""

from __future__ import annotations

import os
from typing import Any, TypedDict


class AITesterState(TypedDict, total=False):
    """
    多智能体工作流的全局状态。

    该 TypedDict 定义了工作流中所有节点共享的状态字段。
    使用 total=False 表示所有字段均为可选（可在不同阶段逐步填充）。

    字段含义详解：

    ── 任务标识 ──────────────────────────────────────────────
    task_uuid (str):
        数据库任务主键，用于记录实验数据。
        格式通常为 "<filename>_<function>_<timestamp>"，便于日志追踪。

    ── 输入信息 ──────────────────────────────────────────────
    target_file (str):
        被测代码文件路径（绝对路径或相对于项目根目录的路径）。
        Executor 使用此路径设置 PYTHONPATH 并写入补丁文件。

    target_function (str | None):
        指定被测函数名。若为 None，则测试文件中所有函数。
        用于 -k 参数过滤 pytest 运行。

    module_name (str):
        模块文件名（不含 .py 后缀），用于生成正确的 import 语句。
        例如：target_file="examples/calculator.py" → module_name="calculator"

    target_code (str):
        被测代码全文（字符串形式）。
        首次从文件读取，后续迭代中可能被补丁更新。

    ── Planner 输出 ──────────────────────────────────────────
    test_plan (Dict[str, Any] | None):
        PlannerAgent 输出的测试计划，包含：
        - function_name: 目标函数名
        - logic_analysis: 输入域/输出域/前置条件/后置条件/边界情况
        - test_cases: 测试用例列表

    ── Generator 输出 ────────────────────────────────────────
    generated_test (str | None):
        GeneratorAgent 生成的 pytest 测试代码字符串。
        Executor 将此代码写入临时文件后执行。

    ── Executor 输出 ─────────────────────────────────────────
    test_passed (bool | None):
        测试是否全部通过（returncode == 0）。

    test_output (str | None):
        pytest 完整输出文本（stdout + stderr），用于诊断失败原因。

    coverage_report (float | None):
        代码覆盖率百分比（0-100），从 pytest-cov 输出的 TOTAL 行解析。

    failed_cases (List[Dict[str, str]] | None):
        失败用例列表，每项为 {"name": str, "error": str}。
        由 _parse_failed_cases 从 pytest 输出中提取。

    ── Debugger 输出 ─────────────────────────────────────────
    diagnosis (str | None):
        DebuggerAgent 的根因分析文本（中文描述）。

    error_category (str | None):
        错误类型枚举字符串，取值：
        "syntax" | "runtime" | "assertion" | "timeout" | "unknown"

    patch (str | None):
        DebuggerAgent 生成的修复代码（含 ```python 标记）。
        PatchApplier 将其应用到原代码并写入文件。

    ── 迭代控制 ──────────────────────────────────────────────
    iteration (int):
        当前修复迭代次数（从 0 开始）。
        每次进入 debugger → patch_applier 循环后递增。

    max_iterations (int):
        最大迭代次数（来自 config.MAX_ITERATIONS，默认 3）。
        达到此值后 _should_debug 返回 "done" 结束流程。

    regeneration_count (int):
        触发 "regenerate"（重新生成测试代码）的次数（从 0 开始）。
        达到最大迭代后，若诊断指向测试生成错误，_should_debug 会路由回
        generator 重新生成；为避免 generator↔executor 无限乒乓（旧 diagnosis
        关键词反复命中导致每轮都再生成，最终撞上 LangGraph recursion_limit），
        该计数在每次再生成时 +1，达到上限（workflow._MAX_REGENERATIONS）后
        _should_debug 不再路由 regenerate 而是返回 "done"。

    ─── 执行控制（可选，由 CLI 注入）──────────────────────────────
    execution_timeout (int | None):
        单次测试执行的超时秒数（CLI --timeout 注入）。
        未提供时 Executor 回退到 config.EXECUTION_TIMEOUT。

    coverage_threshold (float | None):
        覆盖率达标阈值百分比（CLI --coverage-threshold 注入）。
        未提供时 CLI 汇总输出使用 config.COVERAGE_THRESHOLD。

    repair_history (List[Dict[str, Any]]):
        每次修复的详情记录，每项含：
        - iteration: 迭代编号
        - diagnosis: 根因分析
        - error_category: 错误类型
        - patch_applied: 补丁是否成功应用

    execution_trace (List[Dict[str, Any]]):
        3.2 执行反馈轨迹：每次 Executor 执行的记录（3.2 默认常开，
        始终写入；纯观测层，不影响修复流程），每项含：
        - iteration: 迭代编号
        - passed: 测试是否通过
        - coverage_delta: 相对上一轮覆盖率的增减（首轮为 None）
        - elapsed_seconds: 本节点墙钟耗时
        - reward_signals: 多维度奖励信号 {correctness / efficiency /
          simplicity}（保守线性归一，供未来执行反馈 RL 训练备料；
          仅记录观测，不参与工作流路由）

    ── RAG 检索结果 ──────────────────────────────────────────
    rag_references (List[Dict[str, Any]] | None):
        RAG 检索到的相似历史案例列表。
        Generator 和 Debugger 各自使用不同的检索查询。

    rag_stats (List[Dict[str, Any]] | None):
        RAG 检索质量指标累计（P1：消融实验单独报告检索质量）。
        每项为 {"kind": "test_cases"|"repairs", "results": int,
                "max_similarity": float | None, "avg_similarity": float | None}，
        由 Generator/Debugger 节点在检索后追加。
    """

    # 任务标识
    task_uuid: str
    # 输入信息
    target_file: str
    target_function: str | None
    module_name: str
    target_code: str
    # Planner 输出
    test_plan: dict[str, Any] | None
    # Generator 输出
    generated_test: str | None
    # Executor 输出
    test_passed: bool | None
    test_output: str | None
    coverage_report: float | None
    failed_cases: list[dict[str, str]] | None
    # Debugger 输出
    diagnosis: str | None
    error_category: str | None
    patch: str | None
    # P2 注入扫描（2026-10 批次·续二）：输入侧 detect_prompt_injection
    # 在 _generator_node 消费的"任务文本"上命中的注入特征名列表（如
    # ["directive_override"]）。INJECTION_GUARD_ENABLE=false（默认）时恒
    # 空列表；非空时 _generator_node 经 build_injection_warning 追加系统侧
    # 警示（OWASP ASI "检测+隔离"口径，只警示不自动阻断）。供
    # agent_telemetry 的 injection_detected 模式消费（trace 写入）。
    injection_findings: list[str]
    # 迭代控制
    iteration: int
    max_iterations: int
    regeneration_count: int
    # M5（2026-09-29 审查 P0）：测试重生成假通过标记。_executor_node 在
    # "本节点由再生成路由进入（regeneration_count > 0）且本轮 test_passed=True"
    # 时写入 True。此时源码未被修复（regenerate 路由不经过 debugger/patch_applier），
    # 测试重生成后通过不等于缺陷被处理——经典 oracle-from-implementation 假成功。
    # 该标记为纯观测（不参与路由），供评估层把该类任务归入"未验证假通过"。
    # 缺省 None = 本任务未触发再生成路径（历史口径不变）。
    test_regenerated_pass_unverified: bool | None
    # W3（2026-10-05 审查落地·检出优先协议，DETECTION_FIRST_ENABLE 默认关）：
    # 首轮（iteration==0，被测代码未修复）执行是否出现过红灯（测试失败）。
    # True = 测试曾让缺陷代码变红（检出潜势）；False = 首轮全绿（未检出）；
    # None = 开关关闭 / 执行器未运行（历史口径不变）。由 _executor_node 写入。
    detection_first_red_seen: bool | None
    # W3 终态标注（纯观测，评估层消费）：开关开启且最终 test_passed=True 时——
    # "red_then_green" = 曾红后绿（先检出再修复的完整链路）；
    # "all_green_unverified" = 从未变红即通过（弱测试假成功，评估层应归入
    # 未验证而非修复成功）；None = 开关关闭（历史口径不变）。
    detection_first_status: str | None
    # ── AC2（2026-10-06 第十轮审查 T-P0-4）：检出优先协议双门观测/材料 ──
    # gold_fixed_code：gold 修复代码全文（合成任务由 run_benchmark 从任务
    #   材料管道注入；真实任务恒 None）。**评估/门禁专用材料，严禁注入
    #   任何 agent prompt**（test_visible_to_system 卫生口径）。
    gold_fixed_code: str | None
    # original_target_code：任务起始 buggy 原码快照（create_initial_state
    #   写入）——红回归门对照原码 + 补丁前后 target_code 变化判定。
    original_target_code: str | None
    # red_witness_test_code：红证人测试快照（iteration==0 首轮红时由
    #   _executor_node 写入；过红判定为 over_red 时不写——见 detection_gates）。
    red_witness_test_code: str | None
    # specificity_gate_verdict：门①终审（"specific_red" / "over_red" /
    #   "unavailable"；DETECTION_SPECIFICITY_GATE_ENABLE=true 时写）。
    specificity_gate_verdict: str | None
    # red_regression_violation：门②违规标记（True = 再生成抹红被门拦截
    #   并恢复红证人；RED_REGRESSION_GATE_ENABLE=true 时写）。
    red_regression_violation: bool | None
    # 2026-09-29 审查 P0（StopReason 统一停止条件）：工作流终止原因枚举值
    # （"test_passed" / "max_iterations" / "skip_debugger_repair_invalid" /
    # "test_defect_regeneration_cap" / "test_gen_diagnosis_early" /
    # "test_gen_diagnosis" / "budget_exceeded" / "regression_detected" /
    # "recursion_limit" / "unknown"）。由 determine_stop_reason 单点判定，
    # 路由函数在返回 "done" 时写入 state["stop_reason"]（纯观测，不参与
    # 路由），供实验层"终止原因分布可解释"消费。缺省 None = 未终止
    # （历史口径不变）。
    stop_reason: str | None
    repair_history: list[dict[str, Any]]
    # 3.2 执行反馈轨迹（默认常开：纯观测层，随 executor 节点追加）
    execution_trace: list[dict[str, Any]]
    # 执行控制（可选，由 CLI 注入）
    execution_timeout: int | None
    coverage_threshold: float | None
    # RAG 检索结果
    rag_references: list[dict[str, Any]] | None
    # RAG 检索质量指标累计（P1）
    rag_stats: list[dict[str, Any]] | None
    # 3.5 跨文件修复计划（CROSS_FILE_ENABLE=true 时由 cross_file_analyzer 节点写入）
    cross_file_deps: list[dict[str, Any]] | None
    cross_file_plan: dict[str, Any] | None
    # P0 1.1 分层代码压缩（跨文件调用链上下文）：CROSS_FILE_ENABLE=true 且
    # 存在依赖边时由 cross_file_analyzer 节点写入：{module_name: focused_code}
    # （extract_function_context 按 CODE_FOCUS_DEPTH 层调用链截取，替代整模块
    # 全文注入 prompt）；None = 单文件任务 / 未启用跨文件
    cross_file_contexts: dict[str, str] | None
    # P0 1.2 复杂度感知路由（MODEL_ROUTING_STRATEGY=complexity_aware）：
    # run_benchmark 按任务代码行数 / import 数量 / 圈复杂度计算复杂度分数，
    # 写入 state 供 LLM 调用路径选择对应档位 LLM 实例。
    # complexity_class: "simple" | "medium" | "complex"（routing_enabled() 时）
    # complexity_score: [0, 1] 综合分数
    # complexity_breakdown: 各维度归一化分量
    # routing_hints: {"max_candidates", "extra_iteration", "context_budget", "hint_text"}
    complexity_class: str | None
    complexity_score: float | None
    complexity_breakdown: dict[str, Any] | None
    routing_hints: dict[str, Any] | None
    # 1.2 变异反馈闭环（MutGen 式）：上一轮变异测试的存活变异体信息
    # {survived_mutants: list[str], mutation_score: float}
    # 由 run_benchmark 变异评估后写入，Generator 再生成时消费；None 表示无反馈
    mutation_feedback: dict[str, Any] | None
    # 5.2 多候选补丁统计（ENABLE_MULTI_CANDIDATE_PATCH=true 时由 patch_applier 写入）：
    # {"candidates": N, "static_passed": M, "exec_validated": bool, "selected": int | None}
    multi_candidate_stats: dict[str, Any] | None
    # 3.2 改进：执行反馈驱动的动态迭代策略建议（由 executor 节点写入，
    # 纯观测层：基于前几轮覆盖率趋势建议"降低温度/切换修复视角"，
    # 供未来 Debugger 消费；当前仅记录不改变路由）
    iteration_strategy_suggestion: str | None
    # 3.1 双向代码-测试诊断结果（BIDIRECTIONAL_DIAGNOSIS_ENABLE=true 时由
    # debugger 节点写入）：implementation_defect（实现缺陷）/ test_defect（测试缺陷）
    defect_type: str | None
    # 3.1 Review Agent 判定依据文本（defect_type 的补充说明）
    review_reason: str | None
    # 3.3 位置感知迭代修复定位结果（POSITION_AWARE_REPAIR_ENABLE=true 时由
    # debugger 节点写入）：{"focused": bool, "function_name": str | None,
    # "line": int | None, "hint": str}；未启用/无法定位时 focused=False, hint=""
    position_aware_focus: dict[str, Any] | None
    # 2.3 复现测试专项生成结果（REPRO_TEST_ENABLE=true 时由 generator 节点写入）：
    # 覆盖缺陷触发路径的复现测试代码（先失败后通过）
    repro_test: str | None
    # P0 仓库级验证结果（REPO_LEVEL_EXECUTION=true 时由 run_benchmark 写入）：
    # 仓库环境内 gold 测试实测的 {passed, fail_to_pass, pass_to_pass, ...} 汇总；
    # 2026-09-26 全面审查：此前由 benchmark 在 invoke 后 set 到 final_state 但
    # 未声明于 TypedDict（守护测试 test_state_schema_guard 会漏报），现显式声明
    repo_verification: dict[str, Any] | None
    # 三、双向诊断节点（DIAGNOSIS_NODE_ENABLE=true 时由 _diagnosis_node 写入）：
    # 标记 defect_type 的判定来源（"diagnosis_node" = 工作流级 DiagnosisNode；
    # 缺省/None = 历史口径，由 _debugger_node 内联 BIDIRECTIONAL_DIAGNOSIS_ENABLE
    # 完成诊断），供实验区分"工作流级显式诊断"与"debugger 内联诊断"两条路径
    diagnosis_source: str | None
    # 2.1 PAGENT 风格类型修复层：_debugger_node 写入的静态类型疑点列表
    # （每项 {file, line, message, kind}；LLM 层修订成功时 patch 已被替换，
    # 疑点仍保留供实验分析消费）
    type_repair_findings: list[dict[str, Any]] | None
    # M14（2026-09-29 审查 P0）：TYPE_CHECK_ENABLE=true 时 _debugger_node 写入的
    # mypy 静态层疑点数（原为 4 键之一，未在 TypedDict 声明 → LangGraph 静默
    # 丢弃，导致 TYPE_CHECK_ENABLE 的效果永远无法被度量）。缺省 0 = 未启用 /
    # 未安装 mypy。
    mypy_findings_count: int | None
    # M14：1.3 分层压缩降级链本轮是否因契约拒绝反馈而收紧了上下文
    # （原 4 键之一，声明缺失被丢弃）。缺省 False = 未触发降级。
    downgrade_triggered: bool | None
    # M14：1.3 分层压缩降级链档位名（原 4 键之一，声明缺失被丢弃）。
    # 缺省 None = 未触发降级。
    downgrade_tier: str | None
    # 3.2 对抗性推理：_debugger_node 写入的 LLM 输出对抗性校验结果
    # （原 4 键之一，声明缺失被丢弃；缺省 {"scenarios_checked":0,
    # "all_passed":False} = 未运行 / 未启用）。
    adversarial_check: dict[str, Any] | None
    # P2 并行专家池（EXPERT_POOL_ENABLE=true 时 _debugger_node 写入）：
    # 专家池元数据 {dimensions_consulted, verified_count, winner_dimension,
    # agreed_dimensions, expert_pool_applied, expert_pool_winner,
    # synthesized, debate_revise, debate_top_k}。缺省 None = 未启用专家池。
    # M14（2026-09-29 审查 P0）：expert_pool_meta 此前为节点内死局部变量，
    # 6 处赋值从未并入返回 dict，该假设不可证伪；现显式声明并入 state。
    expert_pool_meta: dict[str, Any] | None
    # 1.3 改进（命名契约 AST 符号守卫）：_patch_applier_node 被契约检查拒绝时
    # 写入本轮缺失的模块级符号列表（check_naming_contract 口径）；None = 本轮
    # 无契约拒绝。供 1.3 分层降级链（advance_context_tier）与实验分析消费
    # （"5/7 任务破坏 sqlfluff 插件命名契约"场景的直接可观测信号）
    contract_missing_symbols: list[str] | None
    # 2.2 改进（补丁后处理重采样）：_patch_applier_node 的
    # apply_patch_with_resample 统计 {ast_valid, resampled, resample_count,
    # success, tiered_context: 1.3 降级链档位名}；None = 未启用重采样
    # （历史单补丁口径）
    patch_resample_stats: dict[str, Any] | None
    # 2.2 改进（patch_syntax_invalid 标记）：重采样耗尽仍失败时 _patch_applier_node
    # 写入的 True 标志；refine_failure_category 把该轮 error_category 归一为
    # PATCH_SYNTAX_INVALID（"补丁语法反复损坏"场景的失败知识库口径）
    patch_syntax_invalid_flag: bool | None
    # A-03（2026-10-04 系统审查 P0）：快照/P2P 全量回归/失败自动回滚协议
    # 观测字段（_patch_applier_node 写入，纯观测不参与路由，默认关时恒为
    # not_enabled 值，零默认行为变化；PATCH_SNAPSHOT_ROLLBACK_ENABLE=true 启用）。
    # patch_rollback_verdict: verified / regression_failed / no_oracle /
    #   regression_error / apply_failed / not_enabled
    # patch_rolled_back: bool（True = 本轮补丁已被 P2P 回归失败自动回滚）
    patch_rollback_verdict: str | None
    patch_rolled_back: bool | None
    # 1.3 分层压缩降级链（_patch_applier_node → _debugger_node 跨轮透传）：
    # 上一轮补丁被命名契约符号守卫拒绝后写入的档位反馈
    # {"tier": 档位名, "missing_symbols": 缺失符号列表}；_debugger_node 读取后
    # 按"更高约束"档位重建上下文。None = 未触发（行为与历史完全一致）。
    # 该键由 _patch_applier_node 写入并经 LangGraph 通道传递给下一轮
    # _debugger_node（节点纯函数更新字典，不在原地改写共享状态）
    contract_reject_feedback: dict[str, Any] | None
    # 1.1 LLM 输出后处理层标签（_patch_applier_node 单文件分支写入）：
    # 本轮补丁经 patch_postprocess.sanitize_patch 处理的标签列表，取值
    # "empty_patch"（P1 空壳检测命中，EMPTY_LLM_PATCH 场景可观测）/
    # "imports_repaired"（P2 导入断裂回填生效）/
    # "contract_aliases_restored"（P3 契约符号别名回填生效）。
    # 默认 None = 后处理层未运行（多候选/跨文件分支或异常保守跳过）。
    postprocess_labels: list[str] | None
    # 2.1 P1 改进（错误分类 → 修复策略显式映射）：_debugger_node 写入的
    # 结构化策略标签（get_recommended_fix_strategy 的 strategy 字段，
    # 如 "add_boundary_check" / "regenerate_strict_json"），供实验分析
    # "哪类错误走了哪条修复路径"消费。None = 本轮未运行 debugger。
    fix_strategy_tag: str | None
    # P1-6（2026-10-05 独立审查）：任务问题描述（SWE-bench issue 文本 /
    # 合成任务 description）——注入防护的外部可控文本主源（此前
    # nodes.state.get("problem_statement") 读未声明键恒 None，静默死读）。
    # None = 调用方未提供（CLI 单文件场景）。
    problem_statement: str | None
    # P1-6：CLI 自定义任务描述（预留通道，当前无写入方，读取合法恒 None）。
    task_description: str | None
    # P2-4（2026-10-05 独立审查）：本轮错误分类置信度（0.2/0.5/0.9 分层，
    # error_classifier.classify_with_confidence 产出，debugger 经返回 dict
    # 透传写入）。消费方：risk_approval 三因子风险的"错误置信度"因子
    # （此前恒 None 占位，置信度因子按保守高风险计）。None = 未运行
    # debugger / 旧路径未产出。
    error_confidence: float | None
    # Z1（2026-10-06 审查修复）：策略银行提示文本（_debugger_node 经
    # _select_strategy 检出的 prompt_hint，STRATEGY_BANK_ENABLE=true 时
    # 写入）。该文本是给下一轮 debugger prompt 的策略提示——此前被直接
    # 拼进 patch 代码（自然语言混入代码，只能靠下游 AST 守卫兜底拒绝），
    # 现独立入 state：观测（哪些错误类别命中了策略）+ 后续 prompt 注入
    # 的挂点。None = 开关关 / 无匹配策略（默认关时恒 None，键集合同构）。
    strategy_bank_hint: str | None
    # P2-4：人工审批决策记录（M12 risk_approval interrupt 的 resume 值消费
    # 结果：{"resume_value", "approved", "risk_level"}）。此前 resume 值仅判
    # None 不消费，审批决策丢失。None = 未触发人工审批。
    risk_approval_decision: dict[str, Any] | None
    # 2.1 P1 改进：推荐动作类别（llm_resample / repair_code / repair_test /
    # investigate_infra），修复路由分支选择的 coarse 标签。None 同上。
    fix_strategy_action: str | None
    # 4. 失败知识库闭环（落点 B）：_debugger_node 是否注入了失败知识库同类
    # 案例提示（FAILURE_KB_ENABLE=true 且当前 error_category 匹配知识库条目
    # 时为 True，经 kb_debugger_snippet 追加到 prompt 尾部）。供
    # analyze_results.py 统计"哪些任务走了 KB 增强路径"（效果验证 ⑤）。
    # 默认 None = 未注入（开关关 / 知识库缺失 / 无匹配条目，历史口径不变）。
    kb_prompt_snippet_applied: bool | None
    # P0 测试预言增强（ORACLE_ENHANCE_ENABLE=true 时由 _planner_node 写入）：
    # 本次增强是否成功注入 oracle 字段（False = 保守降级保留原 test_cases）。
    # 供实验分析"预言增强触发率 / 弱预言占比"消费；默认 None = 未启用开关。
    oracle_enhanced: bool | None
    # R7（2026-09-30 独立审查 P0）：SpecIR 可执行规约 IR（SPEC_IR_ENABLE=true
    # 时由 _planner_node 经 parse_logic_analysis 解析后写入）：
    # {schema_version, source, function_name, preconditions, postconditions,
    #  invariants, boundaries[], oracle_kind, findings[]}；None = 未启用 /
    # 解析失败 / 无规约材料（纯观测，不阻断主流程）。
    # 供实验层"SpecIR 覆盖率 / oracle 转换率 / 规约变异杀死率"消费。
    spec_ir: dict[str, Any] | None
    # A-01（2026-10-04 系统审查 P0）：SpecIR v2 DSL 层——"逻辑驱动"主张的
    # 可测量内核（SPEC_IR_DSL_ENABLE=true 时由 _planner_node 写入，默认关
    # 时 None，历史口径零变化）：
    # - spec_compile_rate: 规约子句可编译率 ∈ [0.0, 1.0]（受限表达式 DSL +
    #   白名单判定，纯静态零 LLM）；0.0 = 无规约材料 / 全部 NL 不可机器化
    #   （可证伪口径："逻辑驱动"实际贡献 = 可编译率，而非 100% 宣称）；
    # - spec_provenance: 不可机器化的 NL 子句清单（"未验证"溯源，与可编译
    #   子句的确定性 oracle 形成"可证伪 + 不可证伪"双清单）。
    # 供 M1 指标层与实验层（SpecIR ON/OFF 对照的"可编译规约占比"门槛）消费。
    spec_compile_rate: float | None
    spec_provenance: list[str] | None
    # AC1（2026-10-06 第十轮审查 T-P0-2）：表达式通道覆盖率——LLM 把 NL
    # 规约形式化为 *_expr 子句的占比（与 spec_compile_rate 的"编译器
    # 接受率"正交：rate×coverage = NL 子句最终可确定性执行占比；
    # SPEC_IR_DSL_ENABLE=true 时由 _planner_node 写入，默认关恒 None）。
    spec_expr_coverage: float | None
    # R1c（2026-10-05 审查 P0）：确定性规约 oracle 注入标记（SPEC_ORACLE_EXEC_ENABLE=true
    # 时由 _generator_node 写入）——spec_ir_v2.compile_spec_oracle 的产物（签名感知绑定，
    # R1b）追加到 generated_test 尾部与 LLM 测试**并列**执行：LLM 测试通过 ≠ 规约 oracle
    # 通过，后者的失败是"逻辑驱动"通道的确定性检出（计入 detection 观测）。
    # None/False = 未启用 / 无可编译子句 / 编译产物自检失败（默认关，历史口径零变化）。
    spec_oracle_injected: bool | None
    # R16（2026-10-05 审查 P1）：流氓 agent 行为监控 findings
    # （ROGUE_MONITOR_ENABLE=true 时由 _executor_node 每轮写入）。非空 =
    # 某核心 agent 触发 z-score / 熵 / 能力违规信号（只报警不熔断，
    # 隔离/升级由调用方决定）。None = 未启用 / 无 finding。
    rogue_findings: list[dict[str, Any]] | None
    # R35/R31（2026-09-30 独立审查 P0）：flaky 门禁标记（FLAKY_CHECK_ENABLE=true
    # 时由 _executor_node 对失败轮做重复执行一致性检测后写入）：
    # flaky_detected = 既有 pass 又有 fail（测试不稳定，test_passed 保守记 False）；
    # flaky_pass_count / flaky_total_count 供统计层 flaky fraction 消费；
    # flaky_unverified = True 时该轮结果不可信（M1 指标按"不可测"处理）。
    # 默认 None / False（未启用 / 未检测 / 稳定失败）。
    flaky_detected: bool | None
    flaky_pass_count: int | None
    flaky_total_count: int | None
    flaky_unverified: bool | None
    # P0 运行时探针快照（RUNTIME_PROBE_ENABLE=true 时由 _executor_node 在测试
    # 失败时写入）：sys.settrace 一次性探针捕获的"失败时刻局部变量快照"
    # {"success": bool, "error": str, "frames": [{function, file, line, locals}]}；
    # 供 _debugger_node 渲染为 prompt 片段注入修复上下文（运行时证据替代
    # 静态猜测）。None = 探针未触发 / 降级 / 开关关；历史口径不变。
    runtime_probe_snapshot: dict[str, Any] | None
    # P0 运行时探针注入层观测标志（_debugger_node 写入；RUNTIME_PROBE_ENABLE
    # 默认关 / 快照为 None 时恒 False，历史口径不变）
    probe_section_applied: bool | None
    # AST 级断言一致性检查疑点（ORACLE_VALIDATE_ENABLE=true 时由 _generator_node
    # 写入）：check_assertions() 产出的疑点列表（每项 {type, line, message,
    # suggestion}）；None = 开关关 / 无生成内容 / 无疑点（历史口径不变）。
    # 供实验分析"恒真断言占比 / 魔数断言占比"消费（观测层，不参与路由）。
    oracle_findings: list[dict[str, Any]] | None
    # ANNEAL-lite 故障频率强化提示注入标志（FAILURE_FREQUENCY_ENABLE=true 且
    # 高频故障检测命中时 _debugger_node 写入 True）：供实验分析"哪些任务
    # 走了故障频率强化路径"消费。None = 开关关 / 非高频（历史口径不变）。
    failure_frequency_applied: bool | None
    # O3（2026-09-29 审查 P1）：分支覆盖率测量结果（BRANCH_COVERAGE_INJECT_ENABLE=true
    # 时由 _executor_node 在本地 / venv 沙箱执行完成后写入）：coverage 模块
    # branch=True 独立测量产物，含 {"branch_coverage": float, "total_branches": int,
    # "covered_branches": int, "missing_branches": [{"line": int, "to": int}, ...],
    # "target_module": str}；None = 开关关 / 测量失败 / coverage 不可用 /
    # Docker 链路（历史口径不变）。供 _generator_node 渲染未覆盖分支清单
    # 注入 prompt，以及实验分析"未覆盖分支数随迭代收敛曲线"消费。
    branch_coverage: dict[str, Any] | None
    # O2（2026-09-29 审查 P1）：谱系故障定位 Top-k 结果（FL_SPECTRAL_ENABLE=true
    # 时由 _debugger_node 经 measure_fl_spectral_focus 测量后写入）：Ochiai
    # 打分产物，含 {"top_k": [{"line": int, "score": float}, ...],
    # "total_candidates": int, "failed_lines": int, "target_module": str}；
    # None = 开关关 / 测量失败 / 无失败用例（历史口径不变）。
    # 供 _debugger_node 渲染定位先验段落注入修复 prompt（O2 谱系定位），
    # 以及实验分析"FL@k 指标"消费。
    fl_spectral_focus: dict[str, Any] | None
    # 修复引擎第一阶段（2026-10-07 范式转向）：RGFL 式 LLM 推理定位结果
    # （FaultLocalizerAgent.localize 产出，_debugger_node 写入）：结构化
    # {"function_name", "line_start", "line_end", "confidence", "reasoning"}；
    # None = 开关关 / LLM 失败 / JSON 解析失败 / 无失败用例（历史口径
    # 不变）。实验层消费：函数级命中指标 localization_hit_function
    # （与 gold 变更函数集合比对，局部化独立指标口径）。
    llm_localization: dict[str, Any] | None
    # M6（2026-09-29 审查 P0）：补丁写盘前快照的内部通道键（节点间传递，
    # 不出现在 workflow 输入/输出）。_safe_write_patch 在写盘前把原始代码
    # shutil.copy2 到 tempfile 目录，记入 _last_patch_snapshot（路径）+
    # _last_patch_iteration（迭代编号）；_rollback_last_patch 读取快照原子
    # 写回 target_file 后清除这两个键。
    _last_patch_snapshot: str | None
    _last_patch_iteration: int | None
    # O35（2026-09-30 全面审查 P1）：以下三个键此前由节点 update dict 写入但
    # **未在本 TypedDict 声明**——LangGraph 按 schema 白名单收敛节点返回值，
    # 未声明键被静默丢弃（实测 langgraph 1.2.11：node 返回 {"a":1,
    # "undeclared": "x"} → 下一状态只有 {"a":1}，无任何告警）。后果：
    # O6 确定性守卫报告 / O6 testless 四层验证结果 / M6 回滚标记永远到不了
    # final_state，实验分析读到的恒是 None。现补声明（与 M14 补
    # expert_pool_meta 同一修复模式）。
    # 确定性守卫报告（DETERMINISTIC_GUARD_ENABLE=true 时 _generator_node
    # 写入；开关默认关时恒 None）。
    deterministic_guard_report: dict[str, Any] | None
    # testless 四层验证结果（TESTLESS_VALIDATION_ENABLE=true 且补丁写盘后
    # _patch_applier_node 写入；开关默认关时恒 None）。
    testless_validation: dict[str, Any] | None
    # M6 坏补丁回滚标记：_executor_node 判定本轮失败并成功从快照恢复
    # 源码时置 True（纯观测，供"回滚成功率"统计）。None = 未触发回滚。
    last_patch_rolled_back: bool | None
    # C10（2026-10-05 系统审查 P1）：验证门修复案例暂存。_patch_applier_node
    # 写盘成功时暂存 {original_code, patch, error_category}（节点间通道键），
    # _executor_node 验证通过（test_passed=True）时才经 add_repair 入库、
    # 随即置 None 消费；失败/回滚轮置 None 丢弃——此前 _debugger_node 每轮
    # 无条件入库未验证补丁，失败补丁会成为后续任务的"参考修复案例"
    # （记忆污染）。None = 无待验证补丁。
    last_applied_repair: dict[str, Any] | None
    # 5.4 预算封顶标记：任一节点捕获 BudgetExceededError 时置 True，
    # 供 determine_stop_reason 的 BUDGET_EXCEEDED 分支与实验分析消费。
    # 此前该分支读 state.get("budget_exceeded") 但全仓无写入点 + 键未声明
    # → 分支不可达，预算封顶任务恒被标成 max_iterations。None = 未超限。
    budget_exceeded: bool | None
    # 回归检测标记（P2P 门禁 / regression 检测写入点预留）：determine_stop_reason
    # 的 REGRESSION_DETECTED 分支读取。声明后写入方不再被静默丢弃；
    # None = 未检测到回归（当前无写入方，分支保持保守不可达）。
    regression_detected: bool | None
    # P0（2026-09-30 独立审查 N9/R33）：源码补丁证据门（src/tools/patch_evidence.py）。
    # patch_evidence_gate_enabled()（默认 true）时 _patch_applier_node 在写盘后
    # 立即以"gold / sbfl / keyword / none"判级：等级不足（keyword/none）拒绝
    # 写盘（2026-10-05 独立审查对齐：恢复磁盘原文件 + patch_applied=False，
    # 源码保持原样）并把本键置 True——"源码被改但无规格/gold/谱系定位依据"
    # 的轮次标记，供实验分析"源码腐蚀风险"消费（R33 验证指标：该计数 = 0）。
    # None = 证据门未触发（opt-out 或被拒轮次未发生），历史口径不变。
    source_patched_unverified: bool | None
    # P0（R33）：本轮补丁的确定性证据等级（"gold" / "sbfl" / "keyword" /
    # "none"），_patch_applier_node 写盘前经 patch_evidence.assess_patch_
    # evidence 计算并写入（纯观测，证据门 opt-out 时仍记录供消融对照）。
    # None = 本轮无补丁 / 未计算。
    patch_evidence_level: str | None


def create_initial_state(
    task_uuid: str,
    target_file: str,
    target_code: str,
    max_iterations: int,
    module_name: str | None = None,
    target_function: str | None = None,
    problem_statement: str | None = None,
    task_description: str | None = None,
    execution_timeout: int | None = None,
    coverage_threshold: float | None = None,
) -> AITesterState:
    """
    创建初始工作流状态的唯一工厂函数。

    此前 CLI（cli/app.py）与 benchmark（experiments/run_benchmark.py）
    各自手写一份初始化字典，TypedDict 新增字段时两处易漂移
    （如 3.5 批次的 cross_file_* 字段仅由节点写入，初始字典不补即缺键，
    后续节点 ``state.get("cross_file_plan")`` 永远 None 而难察觉）。
    收敛为本单一构造点后，新增字段只改一处。

    Args:
        task_uuid: 任务标识（CLI 为 "<file>_<func>_<ts>"，benchmark 为 task_id）。
        target_file: 被测代码文件路径。
        target_code: 被测代码全文。
        max_iterations: 最大修复迭代次数。
        module_name: 模块文件名（不含 .py）；None 时按 target_file 推导
            （``os.path.splitext(os.path.basename(target_file))[0]``）。
        target_function: 指定被测函数名；None 表示测试全部函数。
        execution_timeout: 单次测试执行超时秒数（CLI 注入）；None 时
            Executor 回退 config.EXECUTION_TIMEOUT。
        coverage_threshold: 覆盖率达标阈值百分比（CLI 注入）；None 时
            CLI 汇总回退 config.COVERAGE_THRESHOLD。

    Returns:
        完整初始化的 AITesterState，所有 TypedDict 字段均显式赋值
        （未提供的可选项为 None，列表项为初始空值）。
    """
    if module_name is None:
        module_name = os.path.splitext(os.path.basename(target_file))[0]

    return AITesterState(
        # 任务标识
        task_uuid=task_uuid,
        # 输入信息
        target_file=target_file,
        target_function=target_function,
        module_name=module_name,
        target_code=target_code,
        # AC2（2026-10-06 第十轮审查 T-P0-4）：任务起始 buggy 原码快照
        # （红回归门对照材料；gold_fixed_code 由 run_benchmark 按任务材料
        # 单独注入，此处保持 None）
        original_target_code=target_code,
        # Planner 输出
        test_plan=None,
        # Generator 输出
        generated_test=None,
        # Executor 输出
        test_passed=None,
        test_output=None,
        coverage_report=None,
        failed_cases=None,
        # Debugger 输出
        diagnosis=None,
        error_category=None,
        patch=None,
        # P2 注入扫描（2026-10 批次·续二）：输入侧 detect_prompt_injection
        # 命中的注入特征名列表；INJECTION_GUARD_ENABLE 默认关时恒空列表。
        injection_findings=[],
        # 迭代控制
        iteration=0,
        max_iterations=max_iterations,
        regeneration_count=0,
        # M5（2026-09-29 审查 P0）：测试重生成假通过标记（缺省 None = 未触发再生成路径）
        test_regenerated_pass_unverified=None,
        # W3（2026-10-05 审查落地·检出优先协议）：首轮红灯/终态标注（缺省 None =
        # 开关关闭或执行器未运行，历史口径不变；DETECTION_FIRST_ENABLE=true 时
        # 由 _executor_node 写入）
        detection_first_red_seen=None,
        detection_first_status=None,
        # AC2（2026-10-06 第十轮审查 T-P0-4）：双门材料/观测默认 None
        gold_fixed_code=None,
        red_witness_test_code=None,
        specificity_gate_verdict=None,
        red_regression_violation=None,
        # 2026-09-29 审查 P0（StopReason 统一停止条件）：终止原因（缺省 None = 未终止）
        stop_reason=None,
        repair_history=[],
        # 3.2 执行反馈轨迹（随 executor 节点追加，初始空列表）
        execution_trace=[],
        # 执行控制（可选，由 CLI 注入）
        execution_timeout=execution_timeout,
        coverage_threshold=coverage_threshold,
        # RAG 检索结果
        rag_references=None,
        rag_stats=None,
        # 3.5 跨文件修复计划
        cross_file_deps=None,
        cross_file_plan=None,
        # P0 1.1 跨文件调用链上下文（由 cross_file_analyzer 节点按需写入）
        cross_file_contexts=None,
        # P0 1.2 复杂度感知路由（routing_enabled() 时由 run_benchmark 写入）
        complexity_class=None,
        complexity_score=None,
        complexity_breakdown=None,
        routing_hints=None,
        # 1.2 变异反馈闭环（默认 None，由 run_benchmark 变异评估后注入）
        mutation_feedback=None,
        # 5.2 多候选补丁统计（默认 None，启用多候选时由 patch_applier 节点写入）
        multi_candidate_stats=None,
        # 3.2 改进：迭代策略建议（默认 None，executor 节点写入观测层建议）
        iteration_strategy_suggestion=None,
        # 3.1 双向诊断结果（默认 None，启用双向诊断时由 debugger 节点写入）
        defect_type=None,
        review_reason=None,
        # 2.3 复现测试生成结果（默认 None，启用复现测试生成时由 generator 节点写入）
        repro_test=None,
        # 3.3 位置感知修复定位结果（默认 None，启用时由 debugger 节点写入）
        position_aware_focus=None,
        # P0 仓库级验证结果（默认 None，REPO_LEVEL_EXECUTION=true 时由
        # run_benchmark 在 invoke 后写入；2026-09-26 全面审查补声明）
        repo_verification=None,
        # 三、双向诊断节点来源标记（默认 None，DIAGNOSIS_NODE_ENABLE=true 时
        # 由 _diagnosis_node 写入 "diagnosis_node"）
        diagnosis_source=None,
        # 2.1 PAGENT 风格类型修复层疑点（默认 None，_debugger_node 写入）
        type_repair_findings=None,
        # M14（2026-09-29 审查 P0）：TYPE_CHECK_ENABLE 观测键 + 降级链键 +
        # 对抗性推理键 + 专家池元数据（原 4 键未在 TypedDict 声明 → LangGraph
        # 静默丢弃；expert_pool_meta 原为节点内死局部变量，现并入 state）
        mypy_findings_count=None,
        downgrade_triggered=None,
        downgrade_tier=None,
        adversarial_check=None,
        expert_pool_meta=None,
        # 1.3 命名契约符号守卫（默认 None，_patch_applier_node 契约拒绝时写入）
        contract_missing_symbols=None,
        # 2.2 补丁后处理重采样统计（默认 None，未启用重采样时为 None）
        patch_resample_stats=None,
        # 1.1 LLM 输出后处理层标签（默认 None，单文件分支运行后处理层时写入）
        postprocess_labels=None,
        # 2.1 P1 改进：结构化修复策略标签（默认 None，_debugger_node 写入）
        fix_strategy_tag=None,
        fix_strategy_action=None,
        # P2-4（2026-10-05 独立审查）：错误分类置信度（默认 None，debugger 写入）
        error_confidence=None,
        # Z1（2026-10-06 审查修复）：策略银行提示文本（默认 None，debugger
        # 两条检索路径写入；开关关时恒 None）
        strategy_bank_hint=None,
        # P1-6：任务问题描述（benchmark 传入，CLI 默认 None）
        problem_statement=problem_statement,
        task_description=task_description,
        # P2-4：人工审批决策记录（默认 None，risk_approval interrupt resume
        # 消费后写入——闭环决策入 state，此前 resume 值仅判 None 不消费）
        risk_approval_decision=None,
        # 2.2 patch_syntax_invalid 标记（默认 None，重采样耗尽时置 True）
        patch_syntax_invalid_flag=None,
        # A-03（2026-10-04 系统审查 P0）：快照/P2P 回归/自动回滚协议观测字段
        # （默认关时 _patch_applier_node 写 not_enabled 值，零默认行为变化）
        patch_rollback_verdict=None,
        patch_rolled_back=None,
        # 1.3 分层压缩降级链档位反馈（默认 None，_patch_applier_node 契约拒绝
        # 且 CONTEXT_TIER_DOWNGRADE_ENABLE=true 时写入，透传给 _debugger_node）
        contract_reject_feedback=None,
        # 4. 失败知识库闭环落点 B 观测标志（默认 None，_debugger_node 注入
        # KB 片段时置 True；FAILURE_KB_ENABLE 默认关时恒 None，历史口径不变）
        kb_prompt_snippet_applied=None,
        # P0 测试预言增强观测标志（默认 None，ORACLE_ENHANCE_ENABLE=true 时
        # 由 _planner_node 写入 True/False；开关默认关时恒 None，历史口径不变）
        oracle_enhanced=None,
        # R7（2026-09-30 独立审查 P0）：SpecIR 默认 None（未启用 / 解析失败）
        spec_ir=None,
        # A-01（2026-10-04 系统审查 P0）：SpecIR v2 DSL 层默认 None
        # （SPEC_IR_DSL_ENABLE 默认关；_planner_node 启用时写入 float / list）
        spec_compile_rate=None,
        spec_provenance=None,
        # AC1（2026-10-06 第十轮审查 T-P0-2）：表达式通道覆盖率默认 None
        spec_expr_coverage=None,
        spec_oracle_injected=None,
        rogue_findings=None,
        # R35/R31（2026-09-30 独立审查 P0）：flaky 门禁默认未检测
        flaky_detected=None,
        flaky_pass_count=None,
        flaky_total_count=None,
        flaky_unverified=None,
        # P0 运行时探针快照（默认 None，RUNTIME_PROBE_ENABLE=true 时由
        # _executor_node 在测试失败时写入；开关默认关时恒 None，历史口径不变）
        runtime_probe_snapshot=None,
        # P0 运行时探针注入层观测标志（默认 None，_debugger_node 写入；
        # RUNTIME_PROBE_ENABLE 默认关时恒 None，历史口径不变）
        probe_section_applied=None,
        # AST 级断言一致性检查疑点（默认 None，ORACLE_VALIDATE_ENABLE=true 时
        # 由 _generator_node 写入疑点列表；开关默认关时恒 None，历史口径不变）
        oracle_findings=None,
        # ANNEAL-lite 故障频率强化提示是否注入（默认 None，FAILURE_FREQUENCY_ENABLE
        # =true 且高频故障检测命中时 _debugger_node 写入 True；开关默认关时恒 None）
        failure_frequency_applied=None,
        # O3（2026-09-29 审查 P1）：分支覆盖率测量结果（默认 None，
        # BRANCH_COVERAGE_INJECT_ENABLE=true 时由 _executor_node 写入；
        # 开关默认关时恒 None，历史口径不变）
        branch_coverage=None,
        # O2（2026-09-29 审查 P1）：谱系故障定位 Top-k 结果（默认 None，
        # FL_SPECTRAL_ENABLE=true 时由 _debugger_node 写入；
        # 开关默认关时恒 None，历史口径不变）
        fl_spectral_focus=None,
        llm_localization=None,
        # M6（2026-09-29 审查 P0）：补丁写盘前快照内部通道键（节点间传递，
        # 不出现在 workflow 输入/输出）。_safe_write_patch 写盘前写入，
        # _rollback_last_patch 读取后清除。缺省 None = 本轮无快照。
        _last_patch_snapshot=None,
        _last_patch_iteration=None,
        # O35（2026-09-30 全面审查 P1）：三个"声明缺失即被 LangGraph 静默丢弃"
        # 的观测键补初始值（见 AITesterState 对应字段注释）。
        deterministic_guard_report=None,
        testless_validation=None,
        last_patch_rolled_back=None,
        # C10：验证门修复案例暂存（见 TypedDict 注释；None = 无待验证补丁）
        last_applied_repair=None,
        # 5.4 预算封顶标记 / 回归检测标记（determine_stop_reason 消费）
        budget_exceeded=None,
        regression_detected=None,
        # P0（2026-09-30 独立审查 N9/R33）：源码补丁证据门（缺省 None = 未触发）
        source_patched_unverified=None,
        patch_evidence_level=None,
    )
