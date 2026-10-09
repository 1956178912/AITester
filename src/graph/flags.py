"""功能开关辅助函数（S7 拆分自 nodes.py，2026-10-08 R3）。

集中所有 `_xxx_enabled` / `_xxx_max` / `_xxx_temperature` 开关读取函数
（纯 os.getenv 读取，被多个节点函数共享）。nodes.py 通过
`from .flags import ...` re-export，保持 `from src.graph.nodes import _xxx_enabled`
等历史导入路径与 workflow.py 的 re-export 逐字节不变。
"""

from __future__ import annotations

import os


def _patch_resample_enabled() -> bool:
    """2.2 改进：补丁后处理重采样开关（PATCH_RESAMPLE_ENABLE=true 时启用，默认 false）。

    启用后 _patch_applier_node 在应用失败时触发 apply_patch_with_resample
    （AST 验证 + 负面反馈重采样，最多 PATCH_RESAMPLE_MAX 次），仍失败则
    把该轮标记为 patch_syntax_invalid（refine_failure_category 消费）。
    默认关闭保持历史单补丁口径（不产生额外 LLM 调用）。
    """
    return os.getenv("PATCH_RESAMPLE_ENABLE", "false").lower() == "true"


def _patch_resample_max() -> int:
    """2.2 改进：重采样上限（PATCH_RESAMPLE_MAX，默认 2，与 2.2 口径一致）。

    上限 0/负数视为 0（单次应用即放弃，等价历史口径）；上限过高时钳到 5
    （防止 LLM token 空烧，--parallel 场景累积）。
    """
    try:
        n = int(os.getenv("PATCH_RESAMPLE_MAX", "2"))
    except ValueError:
        n = 2
    return max(0, min(n, 5))


def _patch_resample_temperature() -> float | None:
    """2.2 改进：重采样 LLM 温度（1.3 降级链档位温度优先；未读到时 None →
    沿用 config.TEMPERATURE 默认口径）。

    读 patch_applier._current_context_tier() 的档位温度——被符号守卫拒绝
    后自动降级到的档位（0.2/0.1/0.0），越严档位温度越低，重采样也按该
    温度走（与"降级层用更严格采样"的 1.3 口径一致）。
    """
    try:
        from src.tools.patch_applier import _current_context_tier

        _name, _idx, temp = _current_context_tier()
        return temp
    except Exception:
        return None


def _oracle_enhance_enabled() -> bool:
    """P0 测试预言增强开关（ORACLE_ENHANCE_ENABLE=true 时启用，默认 false）。

    启用后 _planner_node 在 Planner 产出 logic_analysis 后追加一次
    OracleEnhancerAgent.enhance() 调用：对每个 test_case 做规约驱动
    预言推理，追加 oracle / oracle_source / oracle_confidence 字段，
    下游 Generator 经 _build_query 的 json.dumps(test_plan) 自然消费。
    默认关闭保持历史实验口径不变（Planner → Generator 零变化）。
    """
    return os.getenv("ORACLE_ENHANCE_ENABLE", "false").lower() == "true"


def _failure_frequency_enabled() -> bool:
    """ANNEAL-lite 故障频率策略切换开关（FAILURE_FREQUENCY_ENABLE=true 时启用，默认 false）。

    启用后 _debugger_node 在每轮修复前检测同一 error_category 是否在
    近期迭代中反复出现（≥ 阈值），高频时注入强化策略提示（如"优先启用
    oracle_enhancer / runtime_probe"），引导 LLM 换更强的修复路径而非
    继续用同一策略碰运气。零 LLM 成本（纯配置级策略映射表查询）。
    默认关闭保持历史修复口径不变（_debugger_node 零变化）。
    """
    return os.getenv("FAILURE_FREQUENCY_ENABLE", "false").lower() == "true"


def _oracle_validate_enabled() -> bool:
    """AST 级断言一致性检查开关（ORACLE_VALIDATE_ENABLE=true 时启用，默认 false）。

    启用后 _generator_node 在生成测试代码后做 AST 静态分析（零 LLM 成本），
    识别恒真断言 / 魔数断言 / 类型不一致三类疑点，写入
    state["oracle_findings"] 供实验分析消费（观测层，不阻断主流程）。
    默认关闭保持历史口径不变（_generator_node 零变化）。
    """
    return os.getenv("ORACLE_VALIDATE_ENABLE", "false").lower() == "true"


def _runtime_probe_enabled() -> bool:
    """P0 运行时探针开关（RUNTIME_PROBE_ENABLE=true 时启用，默认 false）。

    启用后 _executor_node 在测试失败时经 sys.settrace 一次性探针捕获
    "失败时刻局部变量快照"，写入 state["runtime_probe_snapshot"]；
    _debugger_node 读取后把探针片段注入修复 prompt（运行时证据替代
    静态猜测，提升仓库级修复质量）。默认关闭保持历史实验口径不变。
    """
    return os.getenv("RUNTIME_PROBE_ENABLE", "false").lower() == "true"


def _probe_snapshot_locate_enabled() -> bool:
    """P1 探针快照第二定位源开关（PROBE_SNAPSHOT_LOCATE_ENABLE=true 时启用，默认 false）。

    2026-10 改进（A/B 阴性结果驱动）：位置感知 A/B 定位命中 0/30，根因是
    assertion 主导的失败无 traceback 行号，_locate_repair_focus 的
    context.line 恒 None 而降级全文件修复。本开关启用后，_debugger_node
    把结构化探针快照（非渲染文本）透传给 debugger，使定位阶段可用
    快照最内层帧（_locate_repair_focus_from_probe）作为第二定位源。
    纯静态（零 LLM 成本）；需同时启用 RUNTIME_PROBE_ENABLE（快照来源）
    与 POSITION_AWARE_REPAIR_ENABLE（定位消费方）才产生实际效果，
    任一缺失时 probe_snapshot=None，debugger 走历史降级口径。
    """
    return os.getenv("PROBE_SNAPSHOT_LOCATE_ENABLE", "false").lower() == "true"


def _branch_coverage_inject_enabled() -> bool:
    """O3（2026-09-29 审查 P1）：分支覆盖率注入层开关
    （BRANCH_COVERAGE_INJECT_ENABLE=true 时启用，默认 false 历史口径）。

    启用后 _executor_node 在本地 / venv 沙箱执行完成后，用 coverage 模块
    （subprocess 同解释器，独立临时数据文件）对 (target_file,
    generated_test) 做 branch=True 测量，解析 coverage.json 的
    missing_branches，写入 state["branch_coverage"]；_generator_node
    读取后把"未覆盖分支清单"渲染为 prompt 注入段落，引导下一轮
    生成针对性补充边界值 / 异常路径 / 短路分支用例。
    纯观测层（不阻断主流程）；测量失败 / coverage 不可用 / Docker 链路
    时 branch_coverage=None，历史口径不变。
    """
    return os.getenv("BRANCH_COVERAGE_INJECT_ENABLE", "false").lower() in ("true", "1", "on")


def _boundary_triplets_enabled() -> bool:
    """M10（2026-09-29 审查 P0）：确定性边界锚点注入层开关
    （BOUNDARY_TRIPLETS_ENABLE=true 时启用，默认 false 历史口径）。

    启用后 _generator_node 在 agent.generate 调用前，经
    derive_boundary_triplets 从 target_code 的 AST 分支条件推导
    边界三元组（零 LLM 成本，纯 AST 静态分析），渲染为 prompt
    注入段落（boundary_triplets_section），引导 LLM 使用确定性
    边界值作为测试输入（提升 boundary_shift 变异 kill rate）。
    纯观测层（不阻断主流程）；AST 解析失败 / 无边界条件时
    boundary_triplets_section=None，prompt 与历史逐字节一致。
    """
    return os.getenv("BOUNDARY_TRIPLETS_ENABLE", "false").lower() in ("true", "1", "on")


def _flaky_check_enabled() -> bool:
    """R35/R31（2026-09-30 独立审查 P0）：flaky 门禁开关
    （FLAKY_CHECK_ENABLE=true 时启用，默认 false 保持历史口径）。

    启用后 _executor_node 对**失败轮**做重复执行一致性检测（默认 3 次，
    稳定性口径设 30），既有 pass 又有 fail → flaky（test_passed 保守记
    False + flaky_detected 标记，统计层 flaky fraction 消费）。纯 subprocess
    （LLM 缓存命中下零成本）；仅失败轮触发。
    """
    return os.getenv("FLAKY_CHECK_ENABLE", "false").lower() in ("true", "1", "on")


def _spec_ir_enabled() -> bool:
    """R7（2026-09-30 独立审查 P0）：SpecIR 可执行规约 IR 开关
    （SPEC_IR_ENABLE=true 时启用，默认 false 保持历史口径）。

    启用后 _planner_node 在 Planner 产出 logic_analysis 后，经
    parse_logic_analysis + validate_spec_ir 把自然语言规约解析为
    可执行 SpecIR IR（追加字段 spec_ir，不修改 test_plan 既有结构），
    供实验层统计"SpecIR 覆盖率 / oracle 转换率 / 规约变异杀死率"。
    保守：解析失败 / 无规约材料 → spec_ir=None（纯观测，不阻断主流程）。
    """
    return os.getenv("SPEC_IR_ENABLE", "false").lower() in ("true", "1", "on")


def _spec_ir_dsl_enabled() -> bool:
    """A-01（2026-10-04 系统审查 P0）：SpecIR v2 受限表达式 DSL 层开关
    （SPEC_IR_DSL_ENABLE=true 时启用，默认 false，与 R7 主开关独立）。

    启用后 _planner_node 在 SpecIR 解析（或独立解析）之后，对 pre/post/
    invariant 子句做"可编译率"判定（spec_compile_rate）+ NL 溯源清单
    （spec_provenance），写入 state 纯观测字段（不参与路由）——把
    "逻辑驱动"主张从不可证伪升级为"可编译规约占比"可测量量。
    纯静态零 LLM / 零子进程，失败路径保守返回 0.0 / []（不阻断主流程）。
    """
    return os.getenv("SPEC_IR_DSL_ENABLE", "false").lower() in ("true", "1", "on")


def _spec_oracle_exec_enabled() -> bool:
    """R1c（2026-10-05 审查 P0）：确定性规约 oracle 执行接线开关。

    SPEC_ORACLE_EXEC_ENABLE=true 时启用（默认 false，历史口径零变化）：
    _generator_node 在 LLM 测试生成后，把 spec_ir_v2.compile_spec_oracle
    的产物（签名感知绑定，R1b）追加到 generated_test 尾部**并列**执行——
    LLM 生成的测试通过 ≠ 规约 oracle 通过，后者的失败是"逻辑驱动"通道
    的确定性检出（修复审查指出的"compile_spec_oracle 全仓无调用点，
    可执行规约从未进入执行链"死代码缺口）。

    规约材料来源（两级降级）：
    1. state["spec_ir"]（SPEC_IR_ENABLE=true 时 _planner_node 已写入）；
    2. 未启用 R7 主开关时现场解析 test_plan.logic_analysis（与 DSL 层
       的独立降级口径一致）。
    编译失败 / 无可编译子句 / 产物自检失败 → 不追加（保守，零注入）。
    """
    return os.getenv("SPEC_ORACLE_EXEC_ENABLE", "false").lower() in ("true", "1", "on")


def _fl_spectral_enabled() -> bool:
    """O2（2026-09-29 审查 P1）：谱系故障定位开关。

    R8（2026-09-30 独立审查 N7，P1）起**默认开启**（FL_SPECTRAL_ENABLE
    缺省视为 "true"）：谱系定位是零 LLM 成本的纯数据测量（subprocess +
    coverage 行级 Ochiai），且是 R33 证据门 "sbfl" 证据等级的数据源。
    显式设 FL_SPECTRAL_ENABLE=false 可退回"关闭"口径（消融对照组）。

    启用后 _debugger_node 在 agent.debug 调用前，经 measure_fl_spectral_focus
    对 (target_file, target_code, generated_test, failed_cases) 做一次
    Ochiai Top-k 测量（零 LLM 成本，subprocess + coverage 行级），把
    "Top-k 可疑行 + Ochiai 分数"渲染为定位先验段落注入修复 prompt。
    保守降级：测量失败 / coverage 不可用 / 无失败用例 / Docker 链路时
    fl_spectral_focus=None，定位先验段落为空串，prompt 与历史逐字节一致。
    """
    return os.getenv("FL_SPECTRAL_ENABLE", "true").lower() in ("true", "1", "on")


def _context_tier_downgrade_enabled() -> bool:
    """1.3 改进：分层压缩降级链开关（CONTEXT_TIER_DOWNGRADE_ENABLE=true 时
    启用，默认 false）。

    启用后 _patch_applier_node 的命名契约守卫拒绝补丁时，调
    advance_context_tier() 推进档位并把 (档位名, 缺失符号) 写入
    state["_1_3_contract_feedback"]——下一轮 _debugger_node 读到该反馈
    后按"更高约束"的上下文（补丁配方保留 / 签名+import 极简）+ 更低温度
    重新生成。默认关闭时仅记录缺失符号（state["_1_3_contract_missing"]），
    不动档位（保持历史单补丁口径）。
    """
    return os.getenv("CONTEXT_TIER_DOWNGRADE_ENABLE", "false").lower() == "true"


def _repo_core_protection_enabled() -> bool:
    """仓库核心路径保护开关（PATCH_PROTECT_REPO_CORE，默认 true）。

    与同文件其他开关（_patch_resample_enabled / _context_tier_downgrade_enabled
    等）同口径：默认值经 .lower() 统一大小写判定，"0" / "false" / "FALSE"
    等价（历史实现 not in ("0", "false", "False") 大小写敏感，"FALSE" 被
    误判为启用——保守方向错误的 bug，2026-09-29 审查 R3 修正）。
    """
    return os.getenv("PATCH_PROTECT_REPO_CORE", "1").lower() not in ("0", "false")


def _agent_reuse_enabled() -> bool:
    """Agent 实例复用开关（AITESTER_AGENT_REUSE，默认启用，历史口径不变）。"""
    return os.getenv("AITESTER_AGENT_REUSE", "1") != "0"


__all__ = [
    "_agent_reuse_enabled",
    "_boundary_triplets_enabled",
    "_branch_coverage_inject_enabled",
    "_context_tier_downgrade_enabled",
    "_failure_frequency_enabled",
    "_fl_spectral_enabled",
    "_flaky_check_enabled",
    "_oracle_enhance_enabled",
    "_oracle_validate_enabled",
    "_patch_resample_enabled",
    "_patch_resample_max",
    "_patch_resample_temperature",
    "_probe_snapshot_locate_enabled",
    "_repo_core_protection_enabled",
    "_runtime_probe_enabled",
    "_spec_ir_dsl_enabled",
    "_spec_ir_enabled",
    "_spec_oracle_exec_enabled",
]
