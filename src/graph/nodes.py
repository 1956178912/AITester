"""
工作流节点函数模块。

从 workflow.py 拆分而来（代码可维护性优化）：承载 LangGraph 工作流图的各个
节点实现（Planner / Generator / Executor / Debugger / CrossFileAnalyzer /
PatchApplier）及其辅助函数（路径白名单校验、原子写盘、多候选补丁、Planner
输出校验与默认计划）。图构建与条件路由保留在 workflow.py，通过
`from .nodes import ...` 注册这些节点函数。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
from dataclasses import asdict
from typing import Any, cast

from config import (
    ENABLE_RAG,
    EXECUTION_TIMEOUT,
    EXECUTOR_AUTO_INSTALL_DEPS,
    EXECUTOR_DEP_INSTALL_TIMEOUT,
    EXECUTOR_DOCKER_IMAGE,
    EXECUTOR_USE_DOCKER,
    EXECUTOR_USE_VENV,
    MAX_ITERATIONS,
    TEMPERATURE,
)
from src.agents.debugger import DebuggerAgent
from src.agents.executor import ExecutorAgent
from src.agents.generator import GeneratorAgent, _repro_test_enabled
from src.agents.planner import PlannerAgent
from src.agents.runtime_probe import build_probe_prompt_section
from src.graph.cost_budget import BudgetExceededError
from src.graph.event_bus import (
    PlanGenerated,
    publish_debugger_diagnosed,
    publish_event,
    publish_patch_applied,
    publish_tests_executed,
)
from src.graph.expert_pool import expert_pool_enabled
from src.graph.rag import (
    RAG_MODULE_AVAILABLE,
    TestCaseRetriever,
    _build_rag_stat,
    get_rag_retriever,
    rag_guarded,
)
from src.graph.state import AITesterState
from src.graph.tracing import _trace_node
from src.tools.cross_file import analyze_multi_entry_deps, cross_file_enabled
from src.tools.multi_candidate import (
    generate_candidates,
    multi_candidate_available,
    multi_candidate_count,
    multi_candidate_exec_validate,
    select_best_candidate,
)
from src.tools.patch_applier import apply_patch_to_code

# 模块级 logger，用于记录节点执行过程，便于实验追踪和问题排查
logger = logging.getLogger(__name__)

# 修复历史上限：超过后仅保留最近 N 条，防止长迭代循环占用内存（经验值 5）
_MAX_REPAIR_HISTORY = 5

# P0 3.2 多候选自适应触发的"困难错误类别"（断言/运行时/逻辑/下标错误才值得
# 多候选；简单任务保持单候选省 token）。模块级 frozenset（此前在函数内每次
# 调用重建 set，--parallel 多任务热路径累积无谓分配）
_HARD_ERROR_CATEGORIES = frozenset({"assertion", "runtime", "logic_error", "index_error"})

# P0 1.1 分层代码压缩：调用链展开层数（与 BaseAgent.truncate_code 同口径，
# CODE_FOCUS_DEPTH 环境变量，默认 1；跨文件任务建议 2）
CODE_FOCUS_DEPTH: int = int(os.getenv("CODE_FOCUS_DEPTH", "1"))


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


def _build_failure_frequency_section(state: AITesterState) -> str:
    """构建 ANNEAL-lite 故障频率强化提示片段（FAILURE_FREQUENCY_ENABLE=true 时非空）。

    保守口径：
    - 开关关闭 / repair_history 为空 / 非高频故障时返回空串（prompt 与历史逐字节一致）；
    - 高频故障时返回 failure_frequency.get_escalated_strategy_hint() 产出的强化提示
      （纯配置级策略映射表查询，零 LLM 成本）。
    """
    if not _failure_frequency_enabled():
        return ""
    from src.tools.failure_frequency import detect_high_frequency_failure, get_escalated_strategy_hint

    signal = detect_high_frequency_failure(
        repair_history=state.get("repair_history") or [],
        current_category=state.get("error_category"),
        target_module=state.get("module_name"),
    )
    if signal is None:
        return ""
    hint = get_escalated_strategy_hint(signal)
    if not hint:
        return ""
    logger.info(
        "ANNEAL-lite 故障频率检测：%s 在近 %d 轮中出现（阈值 %d），注入强化策略提示",
        signal.get("category"),
        signal.get("count", 0),
        signal.get("threshold", 2),
    )
    return hint


def _resolve_target_module(state: AITesterState) -> str | None:
    """2026-10 P0（A/B 阴性结果驱动）：解析定位/探针用的 target_module。

    跨文件任务（state 携带 cross_file_deps / cross_file_plan 的 target_modules）
    时，被调方真实模块名是依赖图里的 target_module（如 module_c），而
    state["module_name"] 是 task_id 末段（如 synthetic__xxx__test）——
    两者不一致会导致 _locate_repair_focus 的跨文件保护误判
    "traceback 帧文件名与 target_module 不符"而降级全文件修复
    （L3.5 三模块深链定位无法激活的根因）。

    解析口径（保守，单文件零变化）：
    - 跨文件任务（state.get("cross_file_deps") 非空）且 cross_file_plan
      携带 target_modules（analyze 节点解析出的被调方模块名列表）→
      取首元素；
    - 单文件任务 / 无 cross_file_deps / 无 target_modules → 取
      state["module_name"]（历史口径逐字节不变）。

    Args:
        state: 当前工作流状态。

    Returns:
        定位/探针用的 target_module（str），单文件任务恒为
        state["module_name"]。
    """
    cross_file_deps = state.get("cross_file_deps")
    if cross_file_deps:
        cross_file_plan = state.get("cross_file_plan") or {}
        target_modules = cross_file_plan.get("target_modules") or []
        if target_modules:
            return target_modules[0]
        # cross_file_plan 缺失时（analyze 节点未产出计划），回退到
        # cross_file_deps 里 target_module 字段去重集合的**末元素**
        # （依赖链末位 = 最内层被调用方，如 module_a → module_b → module_c
        # 中的 module_c；缺陷通常在最内层被调用模块）
        target_from_deps = [d.get("target_module") for d in cross_file_deps if d.get("target_module")]
        if target_from_deps:
            return target_from_deps[-1]
    return state.get("module_name")


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


# 安全检查 2 用：函数定义探测正则（re 编译缓存命中，热路径零编译开销）。
# 锚定行首（含缩进行）后的 `def `，与旧的"逐行 startswith('def ')"语义等价
# （行内首 token 非 def 的注释/docstring 不命中，避免误判）。
# 2026-09-26 round8 修正（graph 子代理 P1）：补 `(?:async\s+)?` 前缀，与
# patch_applier._TOP_DEF_RE / _find_function_range_ast / 单函数模式按名正则
# （round7 P2-2/P2-3/P2-4 已统一含 async）同口径——此前 async-only 被测
# 模块（目标代码与 LLM 补丁片段仅含 async def）会被安全检查 2 误判"无
# 函数定义"拒写盘 → target_code 永不更新 → 修复循环空烧 token 不收敛。
# 默认行为不变：同步 def 为主的默认数据集命中口径不变，仅 async-only 边界
# 场景由"误拒"变"正确接受"。
_HAS_FUNC_DEF_RE = re.compile(r"^\s*(?:async\s+)?def ", re.MULTILINE)

# 安全检查 3 用：路径白名单根（项目根目录 + 系统临时目录），模块加载期
# 归一化一次。此前每次补丁应用都现场算 4 层 dirname + 3 次 realpath，
# --parallel 多任务累积为重复的 stat/lstat 系统调用。
# 两侧统一 realpath 归一（realpath 内部已含 abspath 语义，旧实现外层再包一层
# abspath 属冗余已去除）；macOS /var→/private/var 符号链接场景下 realpath
# 归一是白名单判定正确性的关键（见 _is_within_allowed_roots 说明）。
# realpath 结果进程内稳定（符号链接不变），加载期归一化一次，
# 热路径 _is_within_allowed_roots 免每次重复解析根目录。
_ALLOWED_WRITE_ROOTS: tuple[str, ...] = tuple(
    os.path.realpath(root)
    for root in (
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        tempfile.gettempdir(),
    )
)
# 2026-09-26 性能优化：预计算前缀对（root, prefix），避免热路径每次
# 对每个 root 重算 root.rstrip(os.sep) + os.sep。语义不变：
# prefix = root 去末尾 sep 后再加 sep（防 AITester_backup/ 兄弟目录碰撞）。
_ALLOWED_WRITE_ROOT_PREFIXES: tuple[tuple[str, str], ...] = tuple(
    (root, root.rstrip(os.sep) + os.sep) for root in _ALLOWED_WRITE_ROOTS
)

# ─── L-1 安全加固（2026-09-29 审查）：仓库核心路径黑名单 ───────────────────────
# _ALLOWED_WRITE_ROOTS 的根含整个仓库根目录（target_file 可能指向仓库内任意
# 文件）。白名单本身健全（realpath + os.sep 前缀 + macOS 符号链接防护），但
# 边界偏宽：若工作流被诱导把 target_file 指向仓库自身源码（config.py /
# main.py / init_db.py / .git / src/graph 等核心文件），LLM 内容将落进核心
# 文件。下列 basename 黑名单在 _safe_write_patch 安全检查 3 之后追加判定，
# 命中任一即拒绝写入（保守口径：数据集任务 target_file 应指向任务目录，
# 不会命中仓库核心路径；若命中说明上游误配置或注入，阻断比放行更安全）。
# 开关：PATCH_PROTECT_REPO_CORE=0 关闭（默认启用，历史行为变更仅限
# "target_file 指向仓库核心" 这一窄场景，正常任务零影响）。
_PROTECTED_CORE_BASENAMES: frozenset[str] = frozenset(
    {
        "config.py",
        "main.py",
        "init_db.py",
        "setup.py",
        "pyproject.toml",
        "requirements.txt",
        "requirements.lock",
        "llm_configs.json",
        ".git",
    }
)
_PROTECTED_CORE_DIRS: frozenset[str] = frozenset({"src", "scripts", ".github", ".git-hooks"})


def _repo_core_protection_enabled() -> bool:
    """仓库核心路径保护开关（PATCH_PROTECT_REPO_CORE，默认 true）。

    与同文件其他开关（_patch_resample_enabled / _context_tier_downgrade_enabled
    等）同口径：默认值经 .lower() 统一大小写判定，"0" / "false" / "FALSE"
    等价（历史实现 not in ("0", "false", "False") 大小写敏感，"FALSE" 被
    误判为启用——保守方向错误的 bug，2026-09-29 审查 R3 修正）。
    """
    return os.getenv("PATCH_PROTECT_REPO_CORE", "1").lower() not in ("0", "false")


def _is_repo_core_path(path: str, roots: tuple[str, ...] | None = None) -> bool:
    """判断路径是否命中仓库核心文件/目录（L-1 黑名单，basename + 一级目录口径）。

    判定时基于路径相对仓库根目录（_ALLOWED_WRITE_ROOTS[0]）的相对形态：
    ① basename 在 _PROTECTED_CORE_BASENAMES（根目录下的 config.py / main.py
    等核心文件，含 .git 目录本身）；
    ② 相对根目录的第一个路径分量在 _PROTECTED_CORE_DIRS（src/ / scripts/
    / .github/ / .git-hooks/ 一级目录）——LLM 内容不应覆盖仓库自身源码树。
    临时目录（tempfile.gettempdir()）内的路径不在此黑名单作用域
    （数据集沙箱 task_dir 与仓库根解耦，保持历史全临时目录可写口径）。

    Args:
        path: 待判定的文件路径（原始形态，函数内做 realpath 归一）。
        roots: 允许根目录元组；None 时用 _ALLOWED_WRITE_ROOTS。

    Returns:
        True 表示命中核心路径（应拒绝写入），False 表示放行。
    """
    if not _repo_core_protection_enabled():
        return False
    root = (roots or _ALLOWED_WRITE_ROOTS)[0]
    abs_path = os.path.realpath(path)
    # 仅对"位于仓库根内"的路径做黑名单判定；临时目录路径直接放行。
    # 根目录自身（abs_path == root）无"相对分量"，直接放行（黑名单
    # 作用对象是根内的文件/一级目录，非根自身）。
    if abs_path == root:
        return False
    if not abs_path.startswith(root.rstrip(os.sep) + os.sep):
        return False
    rel = os.path.relpath(abs_path, root)
    if rel in _PROTECTED_CORE_BASENAMES:
        return True
    first = rel.split(os.sep)[0]
    return first in _PROTECTED_CORE_DIRS


def _planner_node(state: AITesterState) -> dict[str, Any]:
    """
    PlannerAgent 节点：生成逻辑驱动的结构化测试计划。

    优化：添加输出验证，确保 Planner 返回符合预期的 JSON 结构。
    若验证失败，使用默认计划兜底。

    这是工作流的第一个节点（当 ENABLE_PLANNER=True 时），负责：
    1. 调用 PlannerAgent 对被测代码进行逻辑分析（输入域/输出域/前置-后置条件/边界情况）
    2. 生成包含 logic_analysis 和 test_cases 的结构化测试计划 JSON
    3. 若 LLM 返回格式不良的 JSON，使用默认计划兜底，确保工作流不中断

    设计考虑：
    - 使用 try-except 捕获 LLM 调用失败，避免单点故障导致整个流程崩溃
    - 验证输出结构，确保包含必需的字段（function_name, logic_analysis）
    - 默认计划包含空逻辑分析，下游 Generator 仍可基于目标代码生成测试

    Args:
        state: 当前状态，包含 target_code（被测代码）和 target_function（可选的目标函数名）。

    Returns:
        更新后的状态字典，包含 test_plan 字段（PlannerAgent 输出的测试计划）。
    """
    agent = get_or_create_agent(PlannerAgent)
    t0 = time.time()
    _planner_budget_hit = False  # 5.4 预算封顶标记（O35；正常 / 验证降级路径恒 False）
    try:
        # 调用 Planner 生成测试计划，传入被测代码和可选的目标函数名
        # 若指定了 target_function，Planner 将只分析该函数，缩小分析范围
        test_plan = agent.plan(state["target_code"], state.get("target_function"))
        # 验证输出结构
        if not _validate_planner_output(test_plan):
            logger.warning("Planner 输出结构不完整，使用默认计划")
            test_plan = _get_default_test_plan(state.get("target_function"))
            # M10（2026-09-29 审查 P0）：验证失败走默认计划 → 逻辑驱动路径
            # 实际未发生，标记 logic_degraded=True（纯观测，供实验层区分
            # "逻辑驱动成功"与"降级到默认计划"）。
            test_plan["logic_degraded"] = True
        # P0 测试预言增强（ORACLE_ENHANCE_ENABLE=true 时启用，默认关）：
        # 在 Planner 产出 logic_analysis（规约）后，由独立 LLM 调用对每个
        # test_case 做规约驱动预言推理，追加 oracle / oracle_source /
        # oracle_confidence 字段；下游 Generator 经 _build_query 的
        # json.dumps(test_plan) 自然消费强化断言预言。
        # 保守降级：LLM 失败时保留原 test_cases（oracle_enhanced=False），不阻断生成。
        # 默认关闭时零行为变化（历史口径不变）。
        if _oracle_enhance_enabled():
            from src.agents.oracle_enhancer import OracleEnhancerAgent

            enhancer = OracleEnhancerAgent()
            test_plan = enhancer.enhance(test_plan)
            _oracle_enhanced = bool(test_plan.get("oracle_enhanced"))
            logger.info(
                "P0 测试预言增强：%s（函数=%s，oracle 注入 %d 条）",
                "成功" if _oracle_enhanced else "降级保留原 test_cases",
                test_plan.get("function_name", "unknown"),
                sum(1 for c in test_plan.get("test_cases", []) if c.get("oracle")),
            )
        logger.info("Planner 完成规划，函数=%s", test_plan.get("function_name", "unknown"))
    except (json.JSONDecodeError, RuntimeError, OSError) as e:
        # LLM 调用失败或返回非 JSON 格式时，使用默认计划兜底
        # 这确保了即使 LLM 服务异常，工作流仍可以继续执行（降级模式）
        # 2026-09-26 全面审查：扩捕获 OSError——agent.plan 内部 LLM 文件缓存
        # 读写（_call_llm_with_cache）在缓存目录被外部删除/磁盘满等场景抛
        # OSError，此前未捕获会让整图崩溃（与 debugger 节点同口径兜底）。
        # 复用 _get_default_test_plan（与上方验证失败分支同一构造点）：
        # 其 "or 'unknown'" 兜底比原内联 .get(key, "unknown") 更严格
        # （空串/None 键值也会归一为 "unknown"，语义向成功分支收敛）
        # 5.4 预算封顶：BudgetExceededError（isinstance 判定）同走默认计划兜底，
        # 任务不会因预算异常崩溃（后续迭代前置守卫快速失败，自然收敛）
        _planner_budget_hit = isinstance(e, BudgetExceededError)
        logger.warning(
            "Planner LLM 失败（%s），使用默认计划: %s", "5.4 预算封顶" if _planner_budget_hit else "JSON 解析失败", e
        )
        test_plan = _get_default_test_plan(state.get("target_function"))
        # M10（2026-09-29 审查 P0）：LLM 失败走默认计划 → 逻辑驱动路径
        # 实际未发生，标记 logic_degraded=True（纯观测，供实验层区分
        # "逻辑驱动成功"与"降级到默认计划"）。
        test_plan["logic_degraded"] = True
    _trace_node(
        "planner",
        output_summary={
            "function_name": test_plan.get("function_name"),
            "test_cases": len(test_plan.get("test_cases", [])),
        },
        decision="plan_complete",
        duration_ms=(time.time() - t0) * 1000,
    )
    # 1.4 事件总线接线：PlanGenerated（纯观测，不改路由）
    publish_event(
        PlanGenerated(
            task_uuid=str(state.get("task_uuid", "")),
            function_name=str(test_plan.get("function_name") or ""),
            test_case_count=len(test_plan.get("test_cases", [])),
            iteration=int(state.get("iteration", 0)),
        )
    )
    # 观测层：把"预言增强是否触发"写回 state（供实验分析消费，默认关时不写）
    update: dict[str, Any] = {"test_plan": test_plan}
    if _oracle_enhance_enabled():
        update["oracle_enhanced"] = bool(test_plan.get("oracle_enhanced"))
    # R7（2026-09-30 独立审查 P0）：SpecIR——把 logic_analysis（自然语言规约）
    # + 确定性边界三元组解析为可执行 SpecIR IR，校验 findings 写回 state
    # （SPEC_IR_ENABLE=true 时非空，默认关时 None，历史口径零变化）。
    # 保守：解析/校验失败 → spec_ir=None（不阻断 Planner 主流程）。
    if _spec_ir_enabled():
        from src.specs import parse_logic_analysis, validate_spec_ir
        from src.tools.logic_spec import derive_boundary_triplets

        _spec_ir = parse_logic_analysis(
            test_plan.get("logic_analysis"),
            boundary_triplets=derive_boundary_triplets(state["target_code"], state.get("target_function")),
        )
        if _spec_ir is not None:
            _spec_ir["findings"] = validate_spec_ir(_spec_ir)
        update["spec_ir"] = _spec_ir
    # 5.4 预算封顶标记（O35）：置真后不回退，供 determine_stop_reason 的
    # BUDGET_EXCEEDED 分支与实验分析消费（此前该分支无任何写入点，恒不可达）。
    if _planner_budget_hit:
        update["budget_exceeded"] = True
    return update


def _generator_node(state: AITesterState) -> dict[str, Any]:
    """
    GeneratorAgent 节点：根据测试计划生成 pytest 测试代码。

    本节点的核心职责：
    1. 若 RAG 已启用，先检索相似历史测试用例作为风格参考（检索增强）
    2. 调用 GeneratorAgent 生成完整的 pytest 测试代码字符串
    3. 记录生成结果的长度，便于后续分析和调试

    设计考虑：
    - RAG 检索失败时静默跳过（logger.warning），不影响主流程
    - 若 ENABLE_PLANNER=False，传入 None 作为 test_plan，Generator 将基于裸代码生成

    Args:
        state: 当前状态，包含 test_plan（可选）、target_code、module_name 等字段。

    Returns:
        更新后的状态字典，包含 generated_test（测试代码字符串）和 rag_references（RAG 参考列表）。
    """
    agent = get_or_create_agent(GeneratorAgent)

    # 初始化 RAG 参考列表为 None（默认不使用检索增强）
    # 仅当 RAG 开关开启、模块可用时才进行检索（统一走 rag_guarded 降级守卫，P1 重构）
    # 闭包写回需要外层可变容器（list 包装：Python 闭包内无法 rebinding 外层局部名）
    rag_refs_box: list = [None]

    def _on_retrieve(retriever) -> None:
        # top_k=3 是经验值：太多会增加 prompt 长度，太少可能缺乏代表性
        refs = retriever.retrieve_test_cases(state["target_code"], top_k=3)
        # P2 RAG 相关性评分 + 条件注入（2026-10 改进，A/B 阴性结果驱动）：
        # 生成侧同样做相关性过滤（默认关，历史口径零变化）——低相关案例
        # 反增 token 噪声（ContextSniper 式"先筛选再注入"）
        if refs:
            from src.graph.rag import filter_by_relevance

            refs, _filtered_n, _filter_rate = filter_by_relevance(refs)
        logger.info("RAG 检索到 %d 个相似测试用例", len(refs) if refs else 0)
        rag_refs_box[0] = refs

    rag_guarded(
        "retrieve_test_cases",
        _on_retrieve,
        enabled=ENABLE_RAG,
        module_available=RAG_MODULE_AVAILABLE,
        retriever_cls=TestCaseRetriever,
        get_retriever=get_rag_retriever,
    )
    rag_refs: list | None = rag_refs_box[0]

    # P1：记录本次 RAG 检索的质量指标（命中数/相似度），随状态累计供实验汇总
    update_rag_stat = _build_rag_stat(rag_refs, kind="test_cases")

    # 调用 Generator 生成测试代码
    # 参数说明：
    #   - test_plan: 若启用 Planner 则传入结构化计划，否则为 None（Generator 将自行推断）
    #   - target_code: 被测代码全文，Generator 需要它来理解业务逻辑和生成 import 语句
    #   - module_name: 模块名（不含 .py），用于生成正确的 from X import Y 语句
    #   - rag_references: RAG 检索到的历史案例，用于风格参考（可为 None）
    #   - focus_function: 目标函数名（P0 大文件优化），超长代码时按该函数
    #     做 AST 智能截取，保留目标函数及直接依赖，避免 LLM 看不到完整上下文
    # Planner 缺席时 test_plan 为 None（documented behavior：Generator 基于裸代码自行推断，
    # 见 tests/test_workflow.py::test_generator_node_missing_test_plan_key_no_keyerror 回归口径）。
    # mypy 按 TypedDict 报 dict|None → dict，显式 cast 收窄（运行期传 None，Generator 内
    # isinstance(test_plan, dict) 守卫已覆盖 None 路径，行为不变）
    test_plan = cast("dict[str, Any]", state.get("test_plan"))

    # 2026-09-26 全面审查（P1 降级兜底）：此前 agent.generate 无 try-except，
    # LLM 调用失败（RuntimeError，含跨 API 故障转移耗尽）/ 缓存 OSError 会
    # 直接让整图崩溃——与 planner/debugger 节点"降级兜底"口径不一致（二者
    # 均有默认计划 / 空 patch 兜底），且 workflow.py 文档声称"使用 try-except
    # 捕获 LLM 调用异常，确保工作流不因单点故障而崩溃"。现补降级：LLM 失败时
    # 生成空测试 + 记诊断，executor 拿到空测试自然失败 → 路由到 debugger
    # （修代码）或 done，不再崩溃整图。历史行为是崩溃，新行为是优雅降级——
    # 对"LLM 完全不可用"场景更合理（崩溃 = 零产出，降级 = 仍有修复机会）。
    _generator_budget_hit = False  # 5.4 预算封顶标记（O35；正常路径恒 False）
    try:
        # O3（2026-09-29 审查 P1）：分支覆盖率注入——_executor_node 上一轮测量
        # 的未覆盖分支清单渲染为 prompt 段落（BRANCH_COVERAGE_INJECT_ENABLE=true
        # 时非空，默认关时 None，历史口径零变化）
        _bc_section: str | None = None
        if _branch_coverage_inject_enabled() and state.get("branch_coverage"):
            from src.tools.branch_coverage_inject import build_branch_coverage_prompt_section as _build_bc_section

            _bc_section = _build_bc_section(state.get("branch_coverage"))
        # M10（2026-09-29 审查 P0）：确定性边界锚点——从 target_code 的 AST
        # 分支条件推导边界三元组（零 LLM 成本），渲染为 prompt 段落注入
        # Generator（BOUNDARY_TRIPLETS_ENABLE=true 时非空，默认关时 None，
        # 历史口径零变化）。与 O3 分支覆盖率注入同位（在 generate 调用前
        # 构建，传入 generate 的新参数 boundary_triplets_section）。
        _bt_section: str | None = None
        if _boundary_triplets_enabled():
            from src.tools.logic_spec import build_boundary_triplets_section as _build_bt_section
            from src.tools.logic_spec import derive_boundary_triplets as _derive_bt

            _bt_triplets = _derive_bt(state["target_code"], state.get("target_function"))
            if _bt_triplets:
                _bt_section = _build_bt_section(_bt_triplets)
        generated_test = agent.generate(
            test_plan,  # Planner 节点在图中时必带 test_plan；缺席时为 None，Generator 自行推断
            state["target_code"],
            module_name=state.get("module_name", ""),
            rag_references=rag_refs,
            focus_function=state.get("target_function"),
            # 1.2 改进（MutGen 式变异反馈闭环）：上一轮变异测试的存活变异体注入
            # prompt，引导生成针对"当前未捕获故障"的更强断言（None 时不注入）
            mutation_feedback=state.get("mutation_feedback"),
            # 3.3 改进：执行反馈驱动的动态 temperature（覆盖率连降时减半，None 时不覆盖）
            temperature=_dynamic_temperature_from_suggestion(state.get("iteration_strategy_suggestion")),
            # O12（2026-09-29 审查 P1）：复杂度感知路由——complexity_class 非 None 时
            # 经 _call_llm_with_cache → _call_llm → _reorder_api_groups_by_complexity
            # 按档位重排 API 组（complex → 高成本端点在前），使
            # MODEL_ROUTING_STRATEGY=complexity_aware（默认值）真实生效。
            complexity_class=state.get("complexity_class"),
            # O3（2026-09-29 审查 P1）：未覆盖分支清单提示段落（None 时不注入）
            branch_coverage_section=_bc_section,
            # M10（2026-09-29 审查 P0）：确定性边界锚点提示段落（None 时不注入）
            boundary_triplets_section=_bt_section,
        )
    except (RuntimeError, OSError, json.JSONDecodeError) as e:
        # 5.4 预算封顶：BudgetExceededError（isinstance 判定）快速降级空测试，
        # 后续迭代经 MAX_ITERATIONS 自然收敛（各节点前置预算守卫行为一致）
        if isinstance(e, BudgetExceededError):
            logger.warning("Generator LLM 调用失败（5.4 预算封顶），降级为空测试: %s", e)
        else:
            logger.warning("Generator LLM 调用失败，降级为空测试: %s", e)
        generated_test = ""
        _generator_budget_hit = isinstance(e, BudgetExceededError)

    # 2.3 改进：复现测试专项生成（REPRO_TEST_ENABLE=true 且已有缺陷描述时）。
    # 缺陷描述优先取 diagnosis（上一轮 Debugger 根因分析），跨文件修复场景下
    # 该描述含缺陷触发路径信息；生成覆盖触发路径的复现测试写入 state["repro_test"]。
    repro_test: str | None = None
    defect_description = state.get("diagnosis") or state.get("review_reason") or ""
    if _repro_test_enabled() and defect_description:
        # target_module 缺失/空串时跳过（falsy 过滤保持原语义），非空则纳入跨文件提示
        cross_modules = [
            str(d["target_module"]) for d in (state.get("cross_file_deps") or []) if d.get("target_module")
        ]
        # 2026-10-01 全面审查 P1 修复：2.3 复现测试分支此前无 try/except 兜底——
        # 主生成路径（agent.generate，L546）有 try/except (RuntimeError, OSError,
        # json.JSONDecodeError) 降级为空测试，但 generate_repro_test 走同一条 LLM
        # 调用路径（_call_llm_with_cache，可抛 RuntimeError / BudgetExceededError /
        # OSError / JSONDecodeError），异常直接传播出 _generator_node 崩整图，
        # 与主生成路径的"降级兜底"口径不一致（workflow.py 文档承诺"工作流不因
        # 单点故障崩溃"）。现补同口径 try/except：LLM 失败时 repro_test=None
        # 降级（复现测试缺失不阻断主生成路径，executor 仍走 generated_test）。
        try:
            repro_test = agent.generate_repro_test(
                defect_description=defect_description,
                target_code=state["target_code"],
                module_name=state.get("module_name", ""),
                cross_file_modules=cross_modules or None,
                temperature=_dynamic_temperature_from_suggestion(state.get("iteration_strategy_suggestion")),
            )
        except (RuntimeError, OSError, json.JSONDecodeError) as e:
            if isinstance(e, BudgetExceededError):
                logger.warning("复现测试（2.3）LLM 调用失败（5.4 预算封顶），降级为跳过: %s", e)
            else:
                logger.warning("复现测试（2.3）LLM 调用失败，降级为跳过（不阻断主生成）: %s", e)
            repro_test = None
        logger.info("复现测试（2.3）生成完成，长度=%d", len(repro_test or ""))
    # 记录生成结果长度，便于评估 Generator 的输出质量
    logger.info("Generator 完成测试代码生成，长度=%d", len(generated_test))

    # AST 级断言一致性检查（ORACLE_VALIDATE_ENABLE=true 时启用，默认关）：
    # 纯 AST 静态分析（零 LLM 成本），识别恒真断言 / 魔数断言 / 类型不一致
    # 三类疑点，写入 state["oracle_findings"] 供实验分析消费（观测层，不阻断
    # 主流程）。开关关闭 / 无生成内容时不执行（历史口径不变）。
    oracle_findings: list[dict[str, Any]] = []
    if _oracle_validate_enabled() and generated_test:
        from src.tools.oracle_validator import check_assertions

        oracle_findings = check_assertions(generated_test, state["target_code"])
        if oracle_findings:
            logger.info(
                "AST 断言一致性检查发现 %d 个疑点（类型=%s）",
                len(oracle_findings),
                [f.get("type") for f in oracle_findings],
            )
    # O6（2026-09-29 审查 P1）：确定性守卫（DETERMINISTIC_GUARD_ENABLE=true 时启用，默认关）。
    # 对 LLM 生成的测试代码做非确定性静态扫描（random / time.sleep / wall_clock /
    # 外部副作用），含 finding 的测试文件标记为"非确定性"，供实验层决定是否
    # 入库确定性套件。纯 AST 扫描（零 LLM 成本），不阻断主流程。
    # 开关关闭时 scan_test_file 返回空 findings（is_deterministic 恒 True），
    # 历史口径零变化。
    deterministic_guard_report: Any = None
    if generated_test:
        from src.agents.deterministic_guard import scan_test_file as _scan_det_guard

        _det_report = _scan_det_guard(generated_test, filename=state.get("module_name", "<memory>"))
        if _det_report.findings:
            logger.info(
                "O6 确定性守卫：%d 个非确定性 finding（规则=%s）",
                len(_det_report.findings),
                [f.rule for f in _det_report.findings],
            )
            deterministic_guard_report = _det_report
    # O4（2026-09-29 审查 P1）：恒真断言触发一次强制重生成。
    # tautological>=1 时标记 defect_type=test_defect，路由回 generator
    # 重生成（受 _MAX_REGENERATIONS 上限保护，防死循环）。
    # 开关关闭（ORACLE_VALIDATE_ENABLE=false，默认）时 oracle_findings 恒空，
    # 历史口径零变化。
    _MAX_REGENERATIONS = 1  # 与 workflow._MAX_REGENERATIONS 同口径
    _tautological_count = sum(1 for f in oracle_findings if f.get("type") == "tautological")
    _o4_triggered = (
        _tautological_count >= 1
        and state.get("defect_type") != "test_defect"
        and int(state.get("regeneration_count", 0)) < _MAX_REGENERATIONS
    )

    # N5（2026-09-29 审查 P2）：测试套件断言去重（HYPOTHESIS_ENABLE 同口径，
    # 独立开关 TEST_SUITE_DEDUP_ENABLE 默认 false 保持历史口径）。
    # LLM 生成的测试套件常含大量恒真断言（O4 已识别但无去重）；
    # 本层在 generator 产出后对 test_code 做 AST 级重复断言去除
    # （experiments/test_suite_minimize.dedup_assertions），纯数据
    # 零 LLM 成本，不改变路由 / 开关默认行为。
    if os.getenv("TEST_SUITE_DEDUP_ENABLE", "false").lower() in ("true", "1", "on"):
        from experiments.test_suite_minimize import dedup_assertions as _dedup_assertions

        _deduped_code, _dedup_removed = _dedup_assertions(generated_test)
        if _dedup_removed:
            generated_test = _deduped_code
            logger.info("N5 测试套件断言去重：移除 %d 条重复断言", len(_dedup_removed))

    _trace_node(
        "generator",
        output_summary={"generated_test_len": len(generated_test)},
        decision="regenerated"
        if state.get("iteration", 0) >= state.get("max_iterations", MAX_ITERATIONS)
        else "generated",
    )
    update: dict[str, Any] = {
        "generated_test": generated_test,
        "rag_references": rag_refs,
    }
    # 5.4 预算封顶标记（O35）：Generator 捕获 BudgetExceededError 时置真
    # （planner / debugger 同口径），使 determine_stop_reason 可达 BUDGET_EXCEEDED。
    if _generator_budget_hit or state.get("budget_exceeded"):
        update["budget_exceeded"] = True
    # 2.3 改进：复现测试生成结果（未启用 / 无缺陷描述时保持 None）
    if repro_test:
        update["repro_test"] = repro_test
    # AST 级断言一致性检查（ORACLE_VALIDATE_ENABLE=true 时非空，默认关时零变化）
    if oracle_findings:
        update["oracle_findings"] = oracle_findings
    # O4（2026-09-29 审查 P1）：恒真断言强制重生成——标记 defect_type=test_defect，
    # 触发 _should_debug 的 regenerate 路由（受 regeneration_count 上限保护，防死循环）。
    if _o4_triggered:
        logger.info(
            "O4：恒真断言 %d 条，标记 defect_type=test_defect 触发强制重生成（regeneration_count=%d）",
            _tautological_count,
            state.get("regeneration_count", 0),
        )
        update["defect_type"] = "test_defect"
    # O6（2026-09-29 审查 P1）：确定性守卫报告（DETERMINISTIC_GUARD_ENABLE=true 时非空，默认关时零变化）
    if deterministic_guard_report is not None:
        update["deterministic_guard_report"] = {
            "filename": deterministic_guard_report.filename,
            "findings": [
                {"rule": f.rule, "detail": f.detail, "line": f.line} for f in deterministic_guard_report.findings
            ],
            "is_deterministic": deterministic_guard_report.is_deterministic,
        }
    # O4（2026-09-29 审查 P1）：恒真断言强制重生成路径。
    # _tautological_count >= 1 时已写入 update["defect_type"] = "test_defect"，
    # 下方再生成路径检测的条件 2（state.get("defect_type") == "test_defect"）
    # 读取的是**历史** state（非 update），故须将 O4 触发条件并入再生成路径判定：
    # _tautological_count >= 1 且 regeneration_count 未达上限时，视为再生成路径，
    # +1 计数并清空旧诊断（与 3.1 双向诊断路径同口径，防死循环）。
    # _o4_triggered 已在上方（L658）定义，此处直接引用。
    # 累计 RAG 检索指标（本节点读取后携带历史值，避免后续节点覆盖丢失）
    if update_rag_stat:
        update["rag_stats"] = [*list(state.get("rag_stats") or []), update_rag_stat]
    # 再生成路径检测：判定"本节点是否由 regenerate 路由进入"。
    # 覆盖三类进入方式：
    #   1. _should_debug 路由 "regenerate"（iteration >= max_iterations，诊断指向测试生成错误）；
    #   2. 3.1 双向诊断路由 "regenerate"（defect_type == "test_defect"，Review Agent
    #      判定为测试缺陷，可在任意 iteration 触发）；
    #   3. _should_debug 早期路由 "regenerate"（iteration < max_iterations 且 diagnosis
    #      命中 test-generation 关键词，2026-09-26 审查提升为任意 iteration 可触发的
    #      独立分支，reason=test_gen_diagnosis_early）：特征为 iteration > 0 且
    #      diagnosis 非空（首生成恒 iteration=0 且 diagnosis=None，故可区分）。
    # 此前仅条件 1/2 成立时 +1 计数，条件 3 的早期路径漏计 regeneration_count
    # → _should_debug 第 425 行上限保护（regeneration_count < _MAX_REGENERATIONS）
    # 永远 0 < 1 成立 → 关键词持续命中时 generator↔executor 无限乒乓
    # （实测 fibonacci_inefficient 任务 trace 6000+ 行死循环）。
    # - 首次生成（iteration=0，diagnosis=None）：不改变 regeneration_count，保留原有
    #   diagnosis（尚无修复结论）
    # - 再生成：计数 +1（供 _should_debug 上限判断），并清空上一轮诊断，
    #   避免旧的 diagnosis 关键词在新测试仍失败时再次触发 regenerate（死循环根因）
    if (
        state.get("iteration", 0) >= state.get("max_iterations", MAX_ITERATIONS)
        or state.get("defect_type") == "test_defect"
        or (state.get("iteration", 0) > 0 and state.get("diagnosis") is not None)
        or _o4_triggered
    ):
        update["regeneration_count"] = state.get("regeneration_count", 0) + 1
        update["diagnosis"] = None
        update["error_category"] = None
        # 3.1 双向诊断 + O4：重新生成测试后清空旧判定，避免"test_defect"信号
        # 在下一轮仍触发 regenerate（与 regeneration_count 上限共同防死循环）
        update["defect_type"] = None
        update["review_reason"] = None
    return update


# ─── ExecutorAgent 惰性单例（2026-09-28 性能优化）────────────────────────────
# _executor_node 每轮迭代 new 一个 ExecutorAgent。其构造仅存储沙箱配置
# （timeout/use_docker/use_venv/auto_install_deps/dep_install_timeout/
# docker_image），无内部可变状态：agent.execute() 每次调用独立构建沙箱、
# 运行 pytest、回收输出。沙箱参数全部来自 config 模块常量（进程内不变），
# 仅 execution_timeout 可经 CLI 注入——故按完整参数元组分键缓存实例：
# 同配置复用（省每轮构造 + 日志初始化），不同配置（--timeout 变体）各建一份，
# 并发下 DCL + 线程锁保证同键只构造一次。开关：
# AITESTER_EXECUTOR_AGENT_CACHE=0 关闭（默认启用，行为不变）。
_executor_agent_cache: dict[tuple[Any, ...], ExecutorAgent] = {}
_executor_agent_cache_lock = threading.Lock()


def _get_or_create_executor_agent(
    *,
    timeout: int,
    use_docker: bool,
    use_venv: bool,
    auto_install_deps: bool,
    dep_install_timeout: int,
    docker_image: str,
) -> ExecutorAgent:
    """获取（或创建）按沙箱配置分键复用的 ExecutorAgent 实例。"""
    if os.getenv("AITESTER_EXECUTOR_AGENT_CACHE", "1") == "0":
        return ExecutorAgent(
            timeout=timeout,
            use_docker=use_docker,
            use_venv=use_venv,
            auto_install_deps=auto_install_deps,
            dep_install_timeout=dep_install_timeout,
            docker_image=docker_image,
        )
    key = (timeout, use_docker, use_venv, auto_install_deps, dep_install_timeout, docker_image)
    agent = _executor_agent_cache.get(key)
    if agent is not None:
        return agent
    with _executor_agent_cache_lock:
        agent = _executor_agent_cache.get(key)
        if agent is not None:
            return agent
        agent = ExecutorAgent(
            timeout=timeout,
            use_docker=use_docker,
            use_venv=use_venv,
            auto_install_deps=auto_install_deps,
            dep_install_timeout=dep_install_timeout,
            docker_image=docker_image,
        )
        # 容量保护：键空间实际为"沙箱配置组合数"（远小于 16），超限 FIFO 淘汰
        # （与 llm_client 客户端缓存同口径）
        if len(_executor_agent_cache) >= 16:
            _executor_agent_cache.pop(next(iter(_executor_agent_cache)))
        _executor_agent_cache[key] = agent
    return agent


def clear_executor_agent_cache() -> None:
    """清空 ExecutorAgent 复用缓存（测试 / 配置切换时调用，恢复每次新建口径）。"""
    with _executor_agent_cache_lock:
        _executor_agent_cache.clear()


def _executor_node(state: AITesterState) -> dict[str, Any]:
    """
    ExecutorAgent 节点：执行测试并记录结果。
    测试通过后自动入库（若 RAG 可用且已启用），供后续检索使用。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典，包含 test_passed, test_output, coverage_report, failed_cases。

    超时优先级：state["execution_timeout"]（CLI --timeout 注入）> config.EXECUTION_TIMEOUT。
    此前直接读环境变量原始值，绕过了 config 的范围校验（_validate_timeout），
    导致 CLI --timeout 不生效且非法配置（如 0s）未被兜底。
    3.2 执行反馈轨迹：每次执行经 _record_execution_trace 追加到
    state["execution_trace"]（3.2 默认常开，纯观测层，不参与路由）。
    """
    # CLI 通过 state 注入的执行超时优先，未注入时回退到 config 中已校验的值
    executor_timeout = int(state.get("execution_timeout") or EXECUTION_TIMEOUT)
    t0 = time.time()
    # 隔离沙箱参数（P1 依赖隔离）：默认关闭，保持与历史实验一致；
    # 通过环境变量 EXECUTOR_USE_VENV / EXECUTOR_AUTO_INSTALL_DEPS 开启。
    # 4.3 Docker 隔离执行：EXECUTOR_USE_DOCKER=true 时经 docker CLI 在容器内
    # 跑 pytest（镜像 EXECUTOR_DOCKER_IMAGE，默认 aitester:latest）。
    # （2026-09-26 全面审查：EXECUTOR_DOCKER_IMAGE / EXECUTOR_USE_DOCKER 移入
    # 文件头导入，与同文件其他 config 符号风格一致）
    agent = _get_or_create_executor_agent(
        timeout=executor_timeout,
        use_docker=EXECUTOR_USE_DOCKER,
        use_venv=EXECUTOR_USE_VENV,
        auto_install_deps=EXECUTOR_AUTO_INSTALL_DEPS,
        dep_install_timeout=EXECUTOR_DEP_INSTALL_TIMEOUT,
        docker_image=EXECUTOR_DOCKER_IMAGE,
    )
    result = agent.execute(
        test_code=state["generated_test"] or "",
        target_file=state["target_file"],
        target_function=state.get("target_function"),
    )
    status = "PASS" if result["passed"] else "FAIL"
    logger.info(
        "Executor 完成第 %d 轮测试：%s，覆盖率=%.1f%%，失败用例数=%d",
        state.get("iteration", 0) + 1,
        status,
        result["coverage"],
        len(result["failed_cases"]),
    )
    _trace_node(
        "executor",
        output_summary={
            "passed": result["passed"],
            "coverage": result["coverage"],
            "failed_cases": len(result["failed_cases"]),
        },
        decision=status,
        duration_ms=(time.time() - t0) * 1000,
        iteration=state.get("iteration", 0),
    )

    # 统一走 rag_guarded 降级守卫（P1 重构）：测试通过时入库成功用例
    if result["passed"]:
        rag_guarded(
            "add_case",
            lambda r: r.add_case(
                code=state["target_code"],
                test_code=state["generated_test"],
                passed=True,
                metadata={"function": state.get("target_function"), "coverage": result["coverage"]},
            ),
            enabled=ENABLE_RAG,
            module_available=RAG_MODULE_AVAILABLE,
            retriever_cls=TestCaseRetriever,
            get_retriever=get_rag_retriever,
        )

    # P0 运行时探针采集层（RUNTIME_PROBE_ENABLE=true 时启用，默认关）：
    # 测试失败时，经 sys.settrace 一次性探针捕获"失败时刻局部变量快照"，
    # 写入 state["runtime_probe_snapshot"] 供下一轮 _debugger_node 注入 prompt。
    # 纯观测层：探针失败 / 测试全过时 state["runtime_probe_snapshot"]=None，
    # 历史口径不变。默认关闭时零行为变化。
    runtime_probe_snapshot: dict[str, Any] | None = None
    if not result["passed"] and _runtime_probe_enabled():
        from src.agents.runtime_probe import capture_failure_snapshot

        runtime_probe_snapshot = capture_failure_snapshot(
            test_code=state.get("generated_test") or "",
            target_module=state.get("module_name"),
        )
        _trace_node(
            "runtime_probe",
            output_summary={
                "captured": runtime_probe_snapshot is not None,
                "frames": len((runtime_probe_snapshot or {}).get("frames", [])),
            },
            decision="probe_captured" if runtime_probe_snapshot else "probe_degraded",
            iteration=state.get("iteration", 0),
        )

    # 3.2 执行反馈轨迹：追加本次执行记录（纯观测层，默认常开）。
    # 上一轮覆盖率从入参轨迹前缀直接读（_record_execution_trace 内部再
    # 复制一份轨迹，故此处不预先计算 prev_coverage，避免重复扫描）
    new_trace = _record_execution_trace(
        state,
        passed=result["passed"],
        coverage=result["coverage"],
        elapsed_seconds=round(time.time() - t0, 2),
    )
    # 3.2 改进：基于历史轨迹（含本次）的动态迭代策略建议（观测层，不参与路由）
    prev_coverage = None
    if state.get("execution_trace"):
        prev_coverage = state["execution_trace"][-1].get("coverage")
    coverage_delta = round(result["coverage"] - prev_coverage, 2) if prev_coverage is not None else None
    strategy_suggestion = _suggest_iteration_strategy(new_trace, coverage_delta)

    # 1.4 事件总线接线：TestsExecuted（纯观测，不改路由）
    publish_tests_executed(state, passed=result["passed"], coverage=result["coverage"])

    update: dict[str, Any] = {
        "test_passed": result["passed"],
        "test_output": result["output"],
        "coverage_report": result["coverage"],
        "failed_cases": result["failed_cases"],
        "execution_trace": new_trace,
        "iteration_strategy_suggestion": strategy_suggestion,
    }
    # R35/R31（2026-09-30 独立审查 P0）：flaky 门禁（FLAKY_CHECK_ENABLE=true
    # 时启用，默认关）。对**失败轮**做重复执行一致性检测：同 (target_code,
    # generated_test) 重跑 FLAKY_REPEAT_COUNT 次（默认 3），既有 pass 又有
    # fail → flaky（测试本身不稳定）。flaky 时 test_passed 保守记 False
    # （失败口径：不稳定结果不能作"修复正确"证据），并写 flaky_detected /
    # flaky_pass_count / flaky_total_count（统计层 flaky fraction 消费）。
    # 纯 subprocess（LLM 缓存命中下零成本）；仅失败轮触发（全绿即稳定，免重测）。
    if _flaky_check_enabled() and not result["passed"]:
        from src.agents.flaky_gate import detect_flaky as _detect_flaky

        _flaky = _detect_flaky(
            executor=agent,
            test_code=state.get("generated_test") or "",
            target_file=state.get("target_file") or "",
            target_function=state.get("target_function"),
            base_result=result,
        )
        update["flaky_detected"] = bool(_flaky["flaky"])
        update["flaky_pass_count"] = _flaky["pass_count"]
        update["flaky_total_count"] = _flaky["total"]
        if _flaky["flaky"]:
            logger.warning(
                "R35 flaky 检测：同测试 %d 次执行 %d 通过 / %d 失败（不稳定），test_passed 保守记 False",
                _flaky["total"],
                _flaky["pass_count"],
                _flaky["fail_count"],
            )
            # flaky 轮：结果不可信，保守按失败处理（不作"修复正确"证据）
            update["test_passed"] = False
            update["flaky_unverified"] = True
        else:
            # 全 fail（稳定失败）：结果可信，保留原 test_passed=False
            update["flaky_unverified"] = False
    # P0 运行时探针快照（RUNTIME_PROBE_ENABLE=true 时写入；默认关时不写，
    # 历史口径不变。None 表示探针未触发 / 降级；非 None 时含 frames 列表）
    if _runtime_probe_enabled():
        update["runtime_probe_snapshot"] = runtime_probe_snapshot
    # M5（2026-09-29 审查 P0）：测试重生成假通过标记。
    # 判定：本节点由"再生成"路由进入（regeneration_count > 0，即测试在
    # 当前轮或前轮被重新生成过）且本轮 test_passed=True。此时源码并未被
    # 修复（regenerate 路由不经过 debugger/patch_applier），测试重生成后
    # 通过**不等于缺陷被处理**——这是经典 oracle-from-implementation 假
    # 成功通道。写入 test_regenerated_pass_unverified 标记（纯观测，不改
    # 路由），供评估层把该类任务归入"未验证假通过"而非"修复成功"。
    if result["passed"] and int(state.get("regeneration_count", 0)) > 0:
        update["test_regenerated_pass_unverified"] = True
    # O3（2026-09-29 审查 P1）：分支覆盖率注入层（BRANCH_COVERAGE_INJECT_ENABLE=true
    # 时启用，默认关）。本节点在本地 / venv 沙箱执行完成后，用 coverage 模块
    # （subprocess 同解释器，独立临时数据文件）对 (target_file, generated_test)
    # 做 branch=True 测量，解析 coverage.json 的 missing_branches，写入
    # state["branch_coverage"]。纯观测层（不阻断主流程）；测量失败 / coverage
    # 不可用 / Docker 链路时 branch_coverage=None，历史口径不变。
    # Docker 链路（EXECUTOR_USE_DOCKER=true）暂不支持（O16 单独处理容器内
    # JSON 报告回传），本地 / venv 口径。
    if _branch_coverage_inject_enabled() and not EXECUTOR_USE_DOCKER:
        from src.tools.branch_coverage_inject import measure_branch_coverage as _measure_bc

        _bc_result = _measure_bc(
            target_file=state.get("target_file") or "",
            test_code=state.get("generated_test") or "",
            module_name=state.get("module_name") or "",
        )
        if _bc_result is not None:
            update["branch_coverage"] = _bc_result
    # M6（2026-09-29 审查 P0）：坏补丁失败回滚。
    # 当本轮 executor 判定失败（test_passed=False）且 state 中存在上一轮
    # 补丁快照（_last_patch_snapshot，由 _safe_write_patch 在写盘前写入）时，
    # 恢复原始代码，使修复质量不被坏补丁叠加污染。回滚成功后置
    # last_patch_rolled_back=True（纯观测，不参与路由），供评估层报告
    # "回滚成功率"。回滚失败（IO 异常）不阻断主流程。
    # O35：回滚成功必须经 update dict 把两个快照键清空——_rollback_last_patch
    # 内部的 state.pop 改写的是节点入参 dict，LangGraph 不回写（否则陈旧
    # 快照路径会留在 state，下一轮失败时重复回滚到更早的版本）。
    if not result["passed"]:
        _rolled_back = _rollback_last_patch(state)
        if _rolled_back:
            update["last_patch_rolled_back"] = True
            update["_last_patch_snapshot"] = None
            update["_last_patch_iteration"] = None
    return update


def _record_execution_trace(
    state: AITesterState,
    passed: bool,
    coverage: float,
    elapsed_seconds: float,
) -> list[dict[str, Any]]:
    """3.2 执行反馈轨迹：把本次 Executor 执行追加到 state["execution_trace"]。

    轨迹为纯观测层（默认常开）：每次执行记录"通过/失败、相对上一轮的
    覆盖率变化、墙钟耗时"与保守线性归一的多维奖励信号
    （correctness / efficiency / simplicity），供未来执行反馈驱动的微调
    备料。轨迹不参与工作流路由决策，写入失败不阻断主流程（观测层
    失败不应改变被测系统行为，口径与 tracing 一致）。

    Args:
        state: 当前状态（已含上一轮 execution_trace 前缀）。
        passed: 本次测试是否通过。
        coverage: 本次覆盖率百分比（0-100，未测得时 0.0）。
        elapsed_seconds: 本次 Executor 节点墙钟耗时（秒）。

    Returns:
        追加本次记录后的完整 execution_trace 列表。
    """
    # 上一轮覆盖率从入参轨迹前缀读取（首轮为 None，与调用方口径一致）；
    # 调用方 _executor_node 已用同一公式计算过覆盖变化，此处仅服务
    # 追加的轨迹记录，避免重复全轨迹扫描
    trace = list(state.get("execution_trace") or [])
    prev_coverage = trace[-1].get("coverage") if trace else None
    coverage_delta = round(coverage - prev_coverage, 2) if prev_coverage is not None else None

    # 3.2 改进：基于历史轨迹的动态迭代策略调整——根据前几轮的
    # 覆盖率变化趋势，动态建议后续迭代的 temperature 或提示策略。
    # 保守口径：仅输出"建议"到 state["iteration_strategy_suggestion"]，
    # 不直接改变 LLM 调用参数（温度调整需经 BaseAgent 消费，此处只做观测层建议）。
    # 若前 2 轮覆盖率持续下降（delta < 0 两次），建议"降低 temperature
    # + 收紧提示"（当前路径过于发散）；若覆盖率停滞（delta ≈ 0 两次），
    # 建议"切换修复视角"（如从最小改动切到根因修复）
    # 注意：本函数只负责"追加轨迹"，保持返回轨迹列表的历史口径；
    # 策略建议由调用方（_executor_node）单独经 _suggest_iteration_strategy 计算
    # 并写入 state["iteration_strategy_suggestion"]（观测层，不参与路由）
    return _append_trace_record(
        state,
        trace,
        passed=passed,
        coverage=coverage,
        coverage_delta=coverage_delta,
        elapsed_seconds=elapsed_seconds,
    )


def _append_trace_record(
    state: AITesterState,
    trace: list[dict[str, Any]],
    passed: bool,
    coverage: float,
    coverage_delta: float | None,
    elapsed_seconds: float,
) -> list[dict[str, Any]]:
    """把本次执行记录追加到轨迹列表（3.2 观测层，写入失败不阻断主流程）。"""
    reward_signals = _compute_reward_signals(passed, coverage_delta, elapsed_seconds)
    trace.append(
        {
            "iteration": state.get("iteration", 0),
            "passed": passed,
            "coverage": coverage,
            "coverage_delta": coverage_delta,
            "elapsed_seconds": elapsed_seconds,
            "reward_signals": reward_signals,
        }
    )
    return trace


def _compute_reward_signals(passed: bool, coverage_delta: float | None, elapsed_seconds: float) -> dict[str, float]:
    """计算多维度奖励信号（3.2 保守线性归一，供执行反馈 RL 备料）。

    Args:
        passed: 测试是否通过。
        coverage_delta: 相对上一轮覆盖率变化（首轮为 None）。
        elapsed_seconds: 本次执行耗时（秒）。

    Returns:
        {"correctness": 0.0-1.0, "efficiency": 0.0-1.0,
         "simplicity": 0.0-1.0} 的保守归一奖励信号。
    """
    correctness = 1.0 if passed else 0.0
    # efficiency/simplicity 沿用历史口径（基于 EXECUTION_TIMEOUT 的线性归一），
    # 不改变奖励信号定义（避免影响历史实验数据可比性）
    efficiency = max(0.0, round(1.0 - elapsed_seconds / EXECUTION_TIMEOUT, 3))
    simplicity = max(0.0, round(1.0 - elapsed_seconds / (EXECUTION_TIMEOUT * 2.0), 3))
    return {
        "correctness": round(correctness, 4),
        "efficiency": efficiency,
        "simplicity": simplicity,
    }


def _suggest_iteration_strategy(trace: list[dict[str, Any]], coverage_delta: float | None) -> str | None:
    """3.2 改进：基于历史轨迹动态调整后续迭代策略（纯观测层建议）。

    Args:
        trace: 完整执行轨迹（含本次，已追加）。
        coverage_delta: 本次覆盖率变化。

    Returns:
        策略建议字符串（None 表示无需调整，保持默认）：
        - "lower_temperature": 前 2 轮覆盖率持续下降，建议降低温度收紧提示；
        - "switch_repair_view": 覆盖率停滞 2 轮，建议切换修复视角；
        - "keep": 无需调整。
    """
    if len(trace) < 2:
        return None  # 首轮无历史，不调整
    # 覆盖率 delta 过滤 None 后按 float 归一（trace 中 coverage_delta 可能缺失/非数值）
    # 2026-09-26 round10 P1：非数值 delta（"n/a"/dict 等历史落盘异常值）float()
    # 抛 ValueError 使 executor 节点崩溃 → try/except 跳过该条目（口径：非数值
    # delta 视为无信号，与 None 同语义），默认数值路径零变化
    recent_deltas: list[float] = []
    for t in trace[-3:-1]:
        val = t.get("coverage_delta")
        if val is None:
            continue
        try:
            recent_deltas.append(float(val))
        except (TypeError, ValueError):
            continue
    if not recent_deltas:
        return None
    declining = all(d < 0 for d in recent_deltas[-2:]) if len(recent_deltas) >= 2 else False
    stagnant = all(abs(d) < 0.5 for d in recent_deltas[-2:]) if len(recent_deltas) >= 2 else False
    if declining:
        return "lower_temperature"
    if stagnant:
        return "switch_repair_view"
    return None


def _dynamic_temperature_from_suggestion(suggestion: str | None) -> float | None:
    """3.3 改进：把迭代策略建议映射为动态 temperature（真正接线，非观测层）。

    此前 iteration_strategy_suggestion 仅记录不改变路由（观测层）。本函数
    把建议映射为实际采样温度，供 Generator / Debugger 节点在 LLM 调用时
    透传覆盖（_call_llm_with_cache 的 temperature 参数）：

    - "lower_temperature"：覆盖率连降 → 温度减半（下限 0.0），收紧采样发散；
    - 其他建议 / None：不覆盖（返回 None，沿用 config.TEMPERATURE）。

    Args:
        suggestion: executor 节点写入的迭代策略建议字符串。

    Returns:
        覆盖后的温度（None 表示不覆盖，沿用默认）。
    """
    if suggestion == "lower_temperature":
        # TEMPERATURE=0 时减半仍为 0（无收紧空间）→ 返回 None 沿用默认，
        # 避免"覆盖为 0.0"的无意义透传（2026-09-26 全面审查修复）
        if TEMPERATURE <= 0.0:
            logger.info("动态策略（3.3）：TEMPERATURE 已为 0，无可收紧空间，不覆盖")
            return None
        lowered = round(max(0.0, TEMPERATURE * 0.5), 3)
        logger.info("动态策略（3.3）：覆盖率连降，temperature %.2f → %.2f", TEMPERATURE, lowered)
        return lowered
    return None


# ─── BaseAgent 子类惰性单例复用（2026-09-28 性能优化）────────────────────────
# _debugger_node / _diagnosis_node 每轮迭代都 new 一个 DebuggerAgent()，而
# BaseAgent.__init__ 的实质工作是"查 llm_client 的客户端缓存（或新建
# ChatOpenAI 并锁内插缓存）"——循环修复（MAX_ITERATIONS 轮 × 多任务）下该
# 构造/查表开销线性累积。实例缓存的并发等价性：
# - BaseAgent 实例唯一状态 = self.llm（共享缓存客户端，线程安全）+
#   self.system_prompt（不可变构造参数，实例间同值）；
# - 实例方法不写实例字段（execute/debug 均走模块函数 + 共享缓存），
#   按类键单例与按次新建在任意并发模式下逐字节等价。
# 键 = 类名（str，稳定可哈希）；容量 16 + FIFO 淘汰（与 llm_client 客户端
# 缓存同口径）。开关：AITESTER_AGENT_REUSE=0 关闭（默认启用，行为不变）。
_agent_instance_cache: dict[str, Any] = {}
_agent_instance_cache_lock = threading.Lock()
_MAX_CACHED_AGENTS = 16


def _agent_reuse_enabled() -> bool:
    """Agent 实例复用开关（AITESTER_AGENT_REUSE，默认启用，历史口径不变）。"""
    return os.getenv("AITESTER_AGENT_REUSE", "1") != "0"


def get_or_create_agent(agent_cls: type) -> Any:
    """获取（或创建）复用的 Agent 实例（委托按类名分键的模块级缓存）。

    测试以 MagicMock 替换 agent_cls 时，"复用语义"保持原口径：MagicMock
    自身即被 patch 的"类"（构造/实例行为由 mock 定义），直接调用
    agent_cls() 而不走缓存（避免 mock 实例与真实类共享缓存键）。真实类
    走 DCL + FIFO 缓存路径。
    """
    if not _agent_reuse_enabled():
        return agent_cls()
    # MagicMock / 非类对象（测试 patch 场景）：直接构造，不污染模块缓存
    # （MagicMock 类无 __name__ 属性，构造/实例行为由 mock 定义，跨测试复用
    # 会产生 mock 实例与真实类缓存键错位——与按次新建的历史口径等价）
    if not isinstance(agent_cls, type):
        return agent_cls()
    # 真实类：按类名分键 DCL + FIFO 缓存
    key = agent_cls.__name__
    agent = _agent_instance_cache.get(key)
    if agent is not None:
        return agent
    with _agent_instance_cache_lock:
        agent = _agent_instance_cache.get(key)
        if agent is not None:
            return agent
        agent = agent_cls()
        if len(_agent_instance_cache) >= _MAX_CACHED_AGENTS:
            _agent_instance_cache.pop(next(iter(_agent_instance_cache)))
        _agent_instance_cache[key] = agent
    return agent


def clear_agent_instance_cache() -> None:
    """清空 Agent 实例复用缓存（测试 / 配置切换时调用，恢复每次新建口径）。"""
    with _agent_instance_cache_lock:
        _agent_instance_cache.clear()


def _get_or_create_debugger_agent() -> DebuggerAgent:
    """获取（或创建）复用的 DebuggerAgent 实例（委托 get_or_create_agent）。"""
    agent = get_or_create_agent(DebuggerAgent)
    # 测试以 MagicMock 替换 DebuggerAgent 时（非 type），isinstance 校验不适用
    # 且 get_or_create_agent 已按"非 type → 直接构造"语义返回 mock 实例；
    # 真实类路径才做 isinstance 收窄（mypy 友好），mock 路径直返（测试口径）。
    if not isinstance(DebuggerAgent, type):
        return agent
    assert isinstance(agent, DebuggerAgent)
    return agent


def _diagnosis_node(state: AITesterState) -> dict[str, Any]:
    """三、双向代码-测试诊断节点（BiVCode 式 DiagnosisNode，默认关）。

    在 _debugger_node 之前执行：分析测试失败的根本原因，判断是"代码缺陷"
    还是"测试缺陷"，并把判定结果写入 state 供 _should_debug 路由消费：
    - 代码缺陷（implementation_defect）→ 路由到 _debugger_node 生成补丁；
    - 测试缺陷（test_defect）→ 路由回 generator 重新生成测试。

    复用 DebuggerAgent._run_review_diagnosis（BiVCoder 式 Review Agent），
    不重复 LLM prompt 工程；本节点仅做"路由前诊断 + 状态写入 + 观测追踪"。

    开关：DIAGNOSIS_NODE_ENABLE=true 时启用（默认 false，保持历史实验口径——
    历史路径由 _debugger_node 内部 BIDIRECTIONAL_DIAGNOSIS_ENABLE 完成诊断，
    本节点为工作流级的显式诊断点，二者可叠加但默认都关）。

    观测口径：纯诊断层，不修改 target_code / generated_test；LLM 调用失败时
    保守判定为 implementation_defect（与 _run_review_diagnosis 同口径），
    不因诊断失败阻断修复主流程。

    Args:
        state: 当前工作流状态（含 target_code / test_output / failed_cases /
            error_category 等字段）。

    Returns:
        更新后的状态字典，含 defect_type / review_reason / diagnosis_source。
    """
    agent = _get_or_create_debugger_agent()
    t0 = time.time()
    # 截断超长代码与测试输出（诊断 prompt 的 token 预算与 _debugger_node 同口径）
    from src.agents.base_agent import BaseAgent

    truncated_code = BaseAgent.truncate_code(
        state.get("target_code") or "", focus_function=state.get("target_function")
    )
    truncated_output = BaseAgent.truncate_code(state.get("test_output") or "", max_chars=1500)
    failed_cases = state.get("failed_cases") or []
    error_category = str(state.get("error_category") or "unknown")

    review = agent._run_review_diagnosis(truncated_code, truncated_output, failed_cases, error_category)
    defect_type = review.get("defect_type", "implementation_defect")
    review_reason = review.get("reason", "")
    logger.info("三、双向诊断（DiagnosisNode）判定：%s（%s）", defect_type, review_reason[:80])
    _trace_node(
        "diagnosis",
        output_summary={
            "defect_type": defect_type,
            "review_reason": review_reason[:200],
            "error_category": error_category,
        },
        decision=defect_type,
        duration_ms=(time.time() - t0) * 1000,
        iteration=state.get("iteration", 0),
    )
    return {
        "defect_type": defect_type,
        "review_reason": review_reason,
        # 诊断来源标记（区分工作流级 DiagnosisNode 与 _debugger_node 内联诊断）
        "diagnosis_source": "diagnosis_node",
    }


def _debugger_node(state: AITesterState) -> dict[str, Any]:
    """
    DebuggerAgent 节点：分析失败原因并生成分层修复补丁。
    若 RAG 可用且已启用，检索相似历史修复案例作为参考。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典，包含 diagnosis, error_category, patch。
    """
    agent = _get_or_create_debugger_agent()
    t0 = time.time()

    # 统一走 rag_guarded 降级守卫（P1 重构）：有失败用例时检索相似修复案例
    rag_refs_box: list = [None, 0, 0.0]  # [refs, relevance_filtered, relevance_filter_rate]
    if state.get("failed_cases"):

        def _on_retrieve_repairs(retriever) -> None:
            refs = retriever.retrieve_repairs(
                error_category=state.get("error_category", "unknown"),
                target_code=state["target_code"],
                top_k=2,
            )
            # P2 RAG 相关性评分 + 条件注入（2026-10 改进，A/B 阴性结果驱动）：
            # 1. 相关性阈值过滤：similarity < RAG_RELEVANCE_THRESHOLD 的案例
            #    不注入 prompt（避免"检索到但没用上"的噪声，默认关保持历史口径）；
            # 2. 条件注入门控：仅当有匹配案例时才注入（零结果不占位，默认关）。
            # 两开关均默认 false 时，refs 原样透传，行为与历史逐字节一致。
            if refs:
                from src.graph.rag import filter_by_relevance, should_inject_refs

                refs, _filtered_n, _filter_rate = filter_by_relevance(refs)
                _inject = should_inject_refs(refs, error_category=state.get("error_category"))
                refs = refs if _inject else []
                if not _inject:
                    logger.info(
                        "P2 RAG 条件注入：error_category=%s 无匹配案例，本轮不注入",
                        state.get("error_category"),
                    )
                rag_refs_box[1] = _filtered_n
                rag_refs_box[2] = _filter_rate
            logger.info("RAG 检索到 %d 个相似修复案例", len(refs) if refs else 0)
            rag_refs_box[0] = refs

        rag_guarded(
            "retrieve_repairs",
            _on_retrieve_repairs,
            enabled=ENABLE_RAG,
            module_available=RAG_MODULE_AVAILABLE,
            retriever_cls=TestCaseRetriever,
            get_retriever=get_rag_retriever,
        )
    rag_refs: list | None = rag_refs_box[0]

    try:
        # O2（2026-09-29 审查 P1）：谱系故障定位先验（FL_SPECTRAL_ENABLE=true
        # 时启用，默认关）。在 agent.debug 调用前，经 measure_fl_spectral_focus
        # 对 (target_file, target_code, generated_test, failed_cases) 做一次
        # Ochiai Top-k 测量（零 LLM 成本，subprocess + coverage 行级），
        # 把"Top-k 可疑行 + Ochiai 分数"渲染为定位先验段落注入修复 prompt。
        # 保守降级：测量失败 / coverage 不可用 / 无失败用例 / Docker 链路时
        # fl_spectral_focus=None，定位先验段落为空串，prompt 与历史逐字节一致。
        _fl_section: str = ""
        _fl_focus: dict[str, Any] | None = None
        if _fl_spectral_enabled() and not EXECUTOR_USE_DOCKER and state.get("failed_cases"):
            from src.agents.fl_spectral import (
                build_fl_spectral_prompt_section as _build_fl_section,
            )
            from src.agents.fl_spectral import (
                measure_fl_spectral_focus as _measure_fl,
            )

            _fl_focus = _measure_fl(
                target_file=state.get("target_file") or "",
                target_code=state.get("target_code") or "",
                test_code=state.get("generated_test") or "",
                failed_cases=state.get("failed_cases") or [],
                module_name=state.get("module_name") or "",
            )
            if _fl_focus is not None:
                _fl_section = _build_fl_section(_fl_focus)
                if _fl_section:
                    logger.info(
                        "O2 FL_spectral 定位先验注入：Top-%d 首行=%s",
                        len(_fl_focus.get("top_k", [])),
                        _fl_focus.get("top_k", [{}])[0].get("line"),
                    )
        result = agent.debug(
            target_code=state["target_code"],
            test_output=state.get("test_output") or "",
            failed_cases=state.get("failed_cases") or [],
            rag_references=rag_refs,
            focus_function=state.get("target_function"),
            # 2026-10 P0（A/B 阴性结果驱动）：跨文件任务的定位/探针 target_module
            # 应取 cross_file_plan.target_modules[0]（被调方真实模块名，如 module_c），
            # 而非 state["module_name"]（task_id 末段，如 synthetic__xxx__test）。
            # 单文件任务两者一致（module_name = 被测文件名 stem），行为不变。
            target_module=_resolve_target_module(state),
            # P0 1.1 分层代码压缩：跨文件任务时，把 cross_file_analyzer 构建的
            # 各模块"目标函数 + CODE_FOCUS_DEPTH 层调用链"聚焦上下文注入 prompt，
            # 替代"整模块全文 → 截断后靠猜"的旧口径（纯静态文本，零 LLM token）
            cross_file_contexts=state.get("cross_file_contexts") or None,
            # 3.3 改进：执行反馈驱动的动态 temperature（覆盖率连降时减半，None 时不覆盖）
            temperature=_dynamic_temperature_from_suggestion(state.get("iteration_strategy_suggestion")),
            # 1.3 分层压缩降级链：上一轮补丁被命名契约符号守卫拒绝时
            # （_patch_applier_node 写入 state["contract_reject_feedback"] =
            # {"tier", "missing_symbols"}），本轮按"更高约束"的上下文档位
            # （补丁配方保留 / 签名+import 极简）+ 更低温度重新生成；
            # 未触发时 None（行为与历史完全一致）
            # mypy：AITesterState.get 对 TypedDict 返回 Any/Optional 视
            # 键是否已声明而定，显式 cast 收窄到 debug 期望类型
            contract_reject_feedback=cast("dict[str, Any] | None", state.get("contract_reject_feedback")),
            # P0 运行时探针注入层（RUNTIME_PROBE_ENABLE=true 时启用，默认关）：
            # 上一轮 _executor_node 在测试失败时经 sys.settrace 一次性探针捕获的
            # "失败时刻局部变量快照"，渲染为 prompt 片段注入修复上下文（运行时
            # 证据替代静态猜测，提升仓库级修复质量）。保守降级：快照为 None /
            # 开关关时 probe_section 为空串，prompt 与历史逐字节一致。
            probe_section=(
                build_probe_prompt_section(state.get("runtime_probe_snapshot")) if _runtime_probe_enabled() else ""
            ),
            # P1 探针快照第二定位源（PROBE_SNAPSHOT_LOCATE_ENABLE=true 时启用，默认关）：
            # 把结构化探针快照（非渲染文本）透传给 debugger，使 _locate_repair_focus
            # 在 traceback 行号缺失（assertion 主导失败）时可用快照最内层帧定位。
            # 开关关闭 / 快照缺失时 probe_snapshot=None，debugger 走历史降级口径。
            probe_snapshot=(state.get("runtime_probe_snapshot") if _probe_snapshot_locate_enabled() else None),
            # 2026-10 P0（A/B 阴性结果驱动）：定位/探针 target_module 解析
            # （跨文件任务取 cross_file_plan.target_modules[0]，单文件取 module_name）
            # 注：target_module 已在调用首段传入（_resolve_target_module），
            # 此处不再重复传入——debug 调用的 target_module 即解析后的值。
            # ANNEAL-lite 故障频率强化（FAILURE_FREQUENCY_ENABLE=true 时启用，默认关）：
            # 检测当前 error_category 是否在 repair_history 中反复出现（≥ 阈值），
            # 高频时注入强化策略提示（如"优先启用 oracle_enhancer / runtime_probe"），
            # 引导 LLM 换更强修复路径。零 LLM 成本（纯配置级策略映射表查询）。
            # 默认关闭时 failure_frequency_section 为空串，prompt 与历史逐字节一致。
            failure_frequency_section=_build_failure_frequency_section(state),
            # O2（2026-09-29 审查 P1）：谱系定位先验段落（FL_SPECTRAL_ENABLE=true
            # 时非空；默认关 / 测量失败时为空串，prompt 与历史逐字节一致）
            fl_spectral_section=_fl_section,
        )
    except (json.JSONDecodeError, RuntimeError, OSError) as e:
        # 2026-09-26 全面审查：扩捕获 OSError——agent.debug 内部 LLM 文件缓存
        # 读写（_call_llm_with_cache）在缓存目录被外部删除/磁盘满等场景抛
        # OSError，此前未捕获会让整图崩溃（与 planner 节点同口径兜底）。
        # 5.4 任务级预算硬上限：BudgetExceededError（RuntimeError 子类，
        # 消息含 "LLM 预算耗尽"）捕获后本轮修复跳过，error_category 标记
        # "budget_exceeded"（供实验分析"预算封顶任务数"消费），不再空转
        # 迭代烧 token（后续迭代前置守卫同样快速失败，自然收敛）。
        _is_budget_hit = isinstance(e, BudgetExceededError)
        logger.warning("Debugger 本轮修复跳过: %s%s", e, "（5.4 预算封顶）" if _is_budget_hit else "")
        result = {
            "root_cause": f"JSON 解析失败: {e}",
            "error_category": "budget_exceeded" if _is_budget_hit else "unknown",
            "fix_strategy": "",
            "patch": "",
        }
    logger.info(
        "Debugger 完成第 %d 轮修复：类别=%s，根因=%s",
        state.get("iteration", 0) + 1,
        result.get("error_category", "unknown"),
        result.get("root_cause", "")[:80],
    )
    # 1.4 事件总线接线：DebuggerDiagnosed（含 2.1 修复策略标签，纯观测）
    publish_debugger_diagnosed(state, error_category=result.get("error_category", "unknown"))
    _trace_node(
        "debugger",
        output_summary={
            "error_category": result.get("error_category"),
            "root_cause": result.get("root_cause", "")[:200],
            "patch_len": len(result.get("patch", "")),
            # 3.2 对抗性推理校验结果
            "adversarial_check": result.get("adversarial_check", {}),
            # 3.1 双向诊断结果
            "defect_type": result.get("defect_type"),
        },
        decision=result.get("error_category", "unknown"),
        duration_ms=(time.time() - t0) * 1000,
        iteration=state.get("iteration", 0),
    )

    # P2 并行专家 Agent 池（EXPERT_POOL_ENABLE=true 时启用，默认关）：
    # 在单 Agent 修复路径完成后，先经 ExpertPoolAgent.generate_parallel 并发调用
    # N 个专家子 Agent（各聚焦一个修复维度），再经 cross_validate 做两两一致性
    # 投票（过滤误报候选），取被验证数最高的候选作为本轮补丁。
    # 保守降级：专家池全失败 / 投票无达标候选时，保留单 Agent 路径产出的
    # result["patch"]，不引入劣化。开关默认关时本分支零执行，历史口径不变。
    expert_pool_meta: dict[str, Any] = {}
    # O13（2026-09-29 审查 P1）：策略银行独立于专家池——此前
    # STRATEGY_BANK_ENABLE 嵌套在 if expert_pool_enabled(): 内，单独开启
    # 策略银行（EXPERT_POOL_ENABLE=false）时策略检索永不触发（死开关）。
    # 现拆出独立条件：expert_pool_enabled() 或 strategy_bank_enabled() 时
    # 均检索策略；专家池候选存在时注入胜出候选（原口径）；专家池未启用
    # 时注入单 Agent 补丁（prompt_hint 追加到 result["patch"]）。
    from src.tools.strategy_bank import select_strategy as _select_strategy
    from src.tools.strategy_bank import strategy_bank_enabled as _sb_enabled

    if expert_pool_enabled():
        from src.graph.expert_pool import ExpertPoolAgent

        pool = ExpertPoolAgent()
        candidates = pool.generate_parallel(
            target_code=state["target_code"],
            test_output=state.get("test_output") or "",
            failed_cases=state.get("failed_cases") or [],
            rag_references=rag_refs,
            focus_function=state.get("target_function"),
        )
        verified = pool.cross_validate(candidates, min_agreement=2)
        # G6 多 Agent 辩论收敛（EXPERT_POOL_DEBATE_ENABLE=true 时启用，默认关）：
        # 在 cross_validate 投票结果之上对 top-K 候选做"互辩修订"——
        # 产出一个综合修订版候选（吸收 top-K 共性修复点，规避各自弱点），
        # 修订候选非空时插入 verified 列表首位（优先级最高），不再与
        # top-K 重新投票（修订版是"综合版"，投票口径不适用）。
        # 保守降级：top-K 不足 2 / LLM 调用失败 / 空补丁时返回原 verified
        # 列表（不阻断主链路），标记 debate_revise=False。
        # 默认关时本分支零执行（expert_pool_debate_enabled() 恒 False），
        # 历史 cross_validate 口径不变。
        from src.graph.expert_pool import expert_pool_debate_enabled as _debate_enabled

        if verified and _debate_enabled():
            debate_result = pool.debate_round(
                verified=verified,
                target_code=state["target_code"],
                test_output=state.get("test_output") or "",
                failed_cases=state.get("failed_cases") or [],
                focus_function=state.get("target_function"),
            )
            if debate_result:
                verified = debate_result
                # 辩论胜出候选（修订版或原 top-K 首位）标记
                best_revise = debate_result[0].get("debate_revise", False)
                if best_revise:
                    logger.info("G6 辩论收敛：修订候选插入首位（top-K 综合版）")
                expert_pool_meta["debate_revise"] = best_revise
                expert_pool_meta["debate_top_k"] = len(debate_result) if best_revise else 0
        # 策略银行协同（STRATEGY_BANK_ENABLE=true 时）：按失败签名检索策略，
        # 把策略 prompt_hint 注入胜出候选（零额外 LLM 成本，纯静态映射）
        if verified and _sb_enabled():
            strategy = _select_strategy(
                error_category=state.get("error_category") or "unknown",
                fix_strategy_tag=state.get("fix_strategy_tag"),
                cross_file=bool(state.get("cross_file_deps")),
            )
            if strategy and strategy.get("prompt_hint"):
                verified[0]["patch"] = verified[0]["patch"] + "\n\n" + strategy["prompt_hint"]
        if verified:
            best = verified[0]
            # 专家池胜出候选替换单 Agent 补丁（保守：仅当单 Agent 补丁为空或
            # 专家池候选被更多专家投票通过时才替换）
            if not result.get("patch") or len(verified) >= 2:
                result["patch"] = best["patch"]
                result["expert_pool_winner"] = True
                # M14（2026-09-29 审查 P0）：expert_pool_winner 此前写入 result
                # 但从未并入节点返回 dict（result 的键 ≠ update 的键），现并入
                # expert_pool_meta 供 state 消费。
                expert_pool_meta["expert_pool_winner"] = True
            # 多解合成（PRISM 式，EXPERT_POOL_ENABLE=true 且验证候选 ≥ 2 时）：
            # 对验证通过的多个候选做 AST 级修改区域检测——无重叠时合并为
            # 更完整方案（合成 = "从多个部分正确候选中拼出完整方案"，而非
            # "投票选最好的"）。保守降级：有重叠 / 语法校验失败 / 无多候选
            # 时保留投票胜出候选，不引入劣化。
            if len(verified) >= 2:
                # 合成输入须为"应用后的完整代码"（synthesize_candidates 契约：
                # new_code 参与 AST 区域 diff）。专家池候选自带 new_code 时
                # 直接使用（expert_pool.generate_parallel 已应用补丁）；否则
                # 经 static_validate_patch 应用补丁得到（静态筛选失败的候选
                # 无 new_code，跳过——无有效修改区域可供合成）。
                # 2026-09-30 审查修复：此前误把 c["patch"]（未应用的补丁文本）
                # 当 new_code 传入——补丁文本不是合法源码，区域 diff 全错，
                # 且 result["patch"] 可能被合成出的"非源码"覆盖写盘。
                from src.tools.multi_candidate import CandidateResult
                from src.tools.multi_candidate import static_validate_patch as _static_validate
                from src.tools.multi_candidate import synthesize_candidates as _synth_candidates

                synth_inputs: list[CandidateResult] = []
                for i, c in enumerate(verified):
                    _cp = str(c.get("patch") or "")
                    _applied = c.get("new_code")
                    if not _applied:
                        _sok, _sreason, _applied2 = _static_validate(state["target_code"], _cp)
                        _applied = _applied2 if _sok else None
                    if _applied:
                        synth_inputs.append(CandidateResult(index=i, patch=_cp, new_code=_applied, static_passed=True))
                synth_code, synth_labels = _synth_candidates(state["target_code"], synth_inputs)
                if synth_code:
                    result["patch"] = synth_code
                    result["expert_pool_winner"] = True
                    expert_pool_meta["synthesized"] = True
                    expert_pool_meta["expert_pool_winner"] = True
                    logger.info(
                        "多解合成：合并 %d 个无重叠候选，区域=%s",
                        len(verified),
                        synth_labels,
                    )
            # O35（2026-09-30 全面审查 P2）：此前这里是 `expert_pool_meta = {...}`
            # **整体重绑定**，而同一 if verified 分支上方刚写入的
            # expert_pool_winner / debate_revise / debate_top_k / synthesized
            # 属于旧 dict 对象——重绑定后全部丢失（这些键正是 M14 补声明时
            # 在 state.py 承诺可观测的字段）。改为 update() 原地合并。
            expert_pool_meta.update(
                {
                    "dimensions_consulted": len(candidates),
                    "verified_count": len(verified),
                    "winner_dimension": best.get("dimension"),
                    "agreed_dimensions": best.get("agreed_dimensions", []),
                    "expert_pool_applied": bool(best.get("patch")),
                }
            )
            logger.info(
                "P2 并行专家池：咨询 %d 个专家，投票通过 %d 个候选，胜出维度=%s（被 %d 个专家同意）",
                len(candidates),
                len(verified),
                best.get("dimension"),
                best.get("verified_count", 1),
            )
            _trace_node(
                "expert_pool",
                output_summary={
                    "dimensions_consulted": len(candidates),
                    "verified_count": len(verified),
                    "winner_dimension": best.get("dimension"),
                },
                decision=f"expert_{best.get('dimension')}",
                iteration=state.get("iteration", 0),
            )

    # 统一走 rag_guarded 降级守卫（P1 重构）：入库修复案例
    rag_guarded(
        "add_repair",
        lambda r: r.add_repair(
            original_code=state["target_code"],
            patch=result.get("patch", ""),
            error_category=result.get("error_category", "unknown"),
        ),
        enabled=ENABLE_RAG,
        module_available=RAG_MODULE_AVAILABLE,
        retriever_cls=TestCaseRetriever,
        get_retriever=get_rag_retriever,
    )
    # O13（2026-09-29 审查 P1）：策略银行独立于专家池——专家池未启用时，
    # 若 STRATEGY_BANK_ENABLE=true 仍检索策略并注入单 Agent 补丁
    # （prompt_hint 追加到 result["patch"]，零额外 LLM 成本，纯静态映射）。
    if not expert_pool_enabled() and _sb_enabled():
        _sb_strategy = _select_strategy(
            error_category=state.get("error_category") or "unknown",
            fix_strategy_tag=state.get("fix_strategy_tag"),
            cross_file=bool(state.get("cross_file_deps")),
        )
        if _sb_strategy and _sb_strategy.get("prompt_hint") and result.get("patch"):
            result["patch"] = result["patch"] + "\n\n" + _sb_strategy["prompt_hint"]
            logger.info("O13 策略银行（独立路径）：注入 prompt_hint（error_category=%s）", state.get("error_category"))
    # 显式标注 dict[str, Any]：值类型混含 str / dict（adversarial_check），
    # mypy 按字面量推断为 dict[str, str | dict[str, int]] 导致后续
    # update["rag_stats"] = list[...] 赋值报错
    update: dict[str, Any] = {
        "diagnosis": result["root_cause"],
        "error_category": result.get("error_category", "unknown"),
        "patch": result["patch"],
        # 3.2 对抗性推理：记录 LLM 输出的对抗性校验结果（缺省时为零值）
        "adversarial_check": result.get("adversarial_check", {"scenarios_checked": 0, "all_passed": False}),
        # 3.1 双向诊断结果（未启用时 debug() 恒返回 implementation_defect）
        "defect_type": result.get("defect_type", "implementation_defect"),
        "review_reason": result.get("review_reason", ""),
        # 3.3 位置感知修复定位结果（未启用/无法定位时 focused=False, hint=""）
        "position_aware_focus": result.get(
            "position_aware_focus",
            {"focused": False, "function_name": None, "line": None, "hint": ""},
        ),
        # 2.1 类型修复层疑点（空列表 = 无疑点；LLM 层修订成功时 patch 已替换，
        # 疑点仍保留供实验分析消费。2026-09-26 补传播：此前 debug() 返回值
        # 已含该键但节点未写入 state（schema 有键却无值，消费侧恒 None））
        "type_repair_findings": result.get("type_repair_findings", []),
        # 2.1 mypy 静态层观测（TYPE_CHECK_ENABLE=true 时非 0，未启用/未安装时 0）
        "mypy_findings_count": result.get("mypy_findings_count", 0),
        # 1.3 分层压缩降级链：本轮是否因契约拒绝反馈而收紧了上下文
        # （contract_reject_feedback 非空时 True；实验分析"降级链触发率"消费）
        "downgrade_triggered": result.get("downgrade_triggered", False),
        "downgrade_tier": result.get("downgrade_tier"),
        # 2.1 P1 改进：结构化修复策略标签（错误分类 → 修复路径显式映射，
        # 实验分析"哪类错误走了哪条修复路径"消费；缺省 None = 未产出）
        "fix_strategy_tag": result.get("fix_strategy_tag"),
        "fix_strategy_action": result.get("fix_strategy_action"),
        # 4. 失败知识库闭环落点 B 观测标志（_debugger_node 写入；默认 None，
        # FAILURE_KB_ENABLE 默认关时恒 None，历史口径不变）
        "kb_prompt_snippet_applied": result.get("kb_prompt_snippet_applied"),
        # P0 运行时探针注入层观测标志（_debugger_node 写入；RUNTIME_PROBE_ENABLE
        # 默认关 / 快照为 None 时恒 False，历史口径不变）
        "probe_section_applied": result.get("probe_section_applied"),
        # M14（2026-09-29 审查 P0）：专家池元数据并入 state（原为节点内死局部
        # 变量，6 处赋值从未写入返回 dict → 专家池/辩论假设不可证伪）。
        # 专家池未启用（EXPERT_POOL_ENABLE=false）时 expert_pool_meta 为初始
        # 空 dict，此处写 None 保持历史缺省口径；启用且运行后为结构化元数据。
        "expert_pool_meta": expert_pool_meta or None,
        # O2（2026-09-29 审查 P1）：谱系故障定位 Top-k 结果（FL_SPECTRAL_ENABLE=true
        # 时由 _debugger_node 经 measure_fl_spectral_focus 测量后写入；开关默认关 /
        # 测量失败时恒 None，历史口径不变）。
        "fl_spectral_focus": _fl_focus,
        # 5.4 预算封顶标记（O35）：Debugger 捕获 BudgetExceededError 时
        # error_category 已被置为 "budget_exceeded"（上方 except 分支），
        # 据此写 budget_exceeded=True；已由上游节点置真时同样保持（不回退）。
        # 此前 determine_stop_reason 的 BUDGET_EXCEEDED 分支无任何写入点，
        # 预算封顶任务在结果里恒被标成 max_iterations。
        "budget_exceeded": True
        if result.get("error_category") == "budget_exceeded" or state.get("budget_exceeded")
        else state.get("budget_exceeded"),
        # M14（2026-09-29 审查 P0）：_debugger_node 此前有 4 个返回键未在
        # AITesterState TypedDict 声明（adversarial_check / position_aware_focus
        # / type_repair_findings / mypy_findings_count），LangGraph 静默丢弃
        # 未声明键 → "已实现能力"不可度量。现补齐声明（state.py L227/L244/
        # L249），本行写入保留不变，消除静默丢弃。
    }
    # 累计 RAG 修复检索指标（P1 + P2 相关性观测）
    from src.graph.rag import _build_rag_stat_with_relevance

    repair_stat = _build_rag_stat_with_relevance(
        rag_refs,
        kind="repairs",
        relevance_filtered=rag_refs_box[1],
        relevance_filter_rate=rag_refs_box[2],
    )
    if repair_stat:
        update["rag_stats"] = [*list(state.get("rag_stats") or []), repair_stat]

    # M12（2026-09-29 审查 P0 + D.4-2 修复 2026-10-02）：风险分级人工回路暂停接线。
    # 历史口径：risk_approval.assess_task_risk 产出 risk_level/approval_action
    # 纯数据（JSON 字符串字段），但全仓无消费方把 approval_action 落成
    # LangGraph interrupt_before + checkpoint 的人工暂停。
    # D.4-2 修复：build_risk_summary 此前以 confidence=None / changed_files=None /
    # budget_ratio=None 调用，三因子中两个恒取默认值 → 风险分接近常量，
    # pause_requested 几乎永不触发。现传入真实信号：
    #   - confidence：error_classifier.classify_with_confidence 产出（state 键）
    #   - changed_files：cross_file_deps 长度（跨文件数代理）
    #   - budget_ratio / budget_exceeded：cost_budget.get_budget_stats() 实时值
    # 并配合 workflow.py M12 checkpointer 注入（MemorySaver），interrupt() 可
    # 真正暂停并等待人工 approve/reject（Command(resume=...) 恢复）。
    # 默认关时（RISK_APPROVAL_ENABLE=false）零行为变化（历史口径不变）。
    from src.graph.risk_approval import build_risk_summary as _build_risk_summary
    from src.graph.risk_approval import risk_approval_enabled as _risk_enabled

    if _risk_enabled():
        # M12 D.4-2：传入真实三因子（此前恒 None → 风险分接近常量）
        # error_confidence 尚未声明为 state 键（M14 补全前用 None 占位），
        # 待 error_classifier 置信度写入 state 后可读真实值。
        _confidence_val: float | None = None
        _changed_files_val = len(state.get("cross_file_deps") or []) or None
        _budget_ratio_val: float | None = None
        _budget_exceeded_val: bool | None = None
        try:
            from src.graph.cost_budget import get_budget_stats

            _budget_stats = get_budget_stats()
            # 预算快照键：consumed_tokens / token_limit / consumed_usd / usd_limit
            _token_limit = int(_budget_stats.get("token_limit", 0) or 0)
            _consumed_tokens = int(_budget_stats.get("consumed_tokens", 0) or 0)
            _usd_limit = float(_budget_stats.get("usd_limit", 0.0) or 0.0)
            _consumed_usd = float(_budget_stats.get("consumed_usd", 0.0) or 0.0)
            # 取有值的维度计算 ratio
            if _token_limit > 0:
                _budget_ratio_val = _consumed_tokens / _token_limit
                _budget_exceeded_val = _consumed_tokens >= _token_limit
            elif _usd_limit > 0:
                _budget_ratio_val = _consumed_usd / _usd_limit
                _budget_exceeded_val = _consumed_usd >= _usd_limit
        except (ImportError, Exception):
            pass
        _risk_result = _build_risk_summary(
            confidence=_confidence_val,
            changed_lines=len([ln for ln in (result.get("patch") or "").splitlines() if ln.strip()]),
            changed_files=_changed_files_val,
            contract_missing_symbols=state.get("contract_missing_symbols"),
            full_file_patch=False,
            budget_ratio=_budget_ratio_val,
            budget_exceeded=_budget_exceeded_val,
        )
        if _risk_result.get("pause_requested"):
            from langgraph.types import interrupt  # 延迟导入：默认关时零导入开销

            _resume_value = interrupt(
                {
                    "reason": "M12 risk_approval pause",
                    "risk_level": _risk_result.get("risk_level"),
                    "approval_action": _risk_result.get("approval_action"),
                    "risk_score": _risk_result.get("risk_score"),
                }
            )
            if _resume_value is None:
                logger.warning(
                    "M12 暂停未生效（无 checkpointer），继续工作流（risk_level=%s）",
                    _risk_result.get("risk_level"),
                )
    return update


def _is_within_allowed_roots(path: str, roots: tuple[str, ...] | None = None) -> bool:
    """判断文件路径是否位于任一允许根目录之内（含根目录自身）。

    前缀比较必须带上 os.sep，否则 AITester_backup/ 这类兄弟目录会因
    startswith(project_root) 命中而绕过白名单（前缀碰撞）。

    用 realpath 归一化两侧：macOS 上 /var 是 /private/var 的符号链接，
    pytest 的 tmp_path 与 tempfile.gettempdir() 一侧带 /private 一侧不带，
    abspath 会失配；realpath 统一解析符号链接后再比较。
    _ALLOWED_WRITE_ROOTS 已在模块加载期 realpath 归一化（进程内稳定），
    本函数仅对入参做 realpath，避免热路径重复解析根目录。

    Args:
        path: 待校验的文件路径。
        roots: 允许的根目录元组（已 realpath 归一化）。None 时使用
            模块级 _ALLOWED_WRITE_ROOT_PREFIXES（热路径，零重算开销）。

    Returns:
        True 表示路径位于某根目录内（或即根目录本身）。
    """
    abs_path = os.path.realpath(path)
    if roots is None:
        return any(abs_path == root or abs_path.startswith(prefix) for root, prefix in _ALLOWED_WRITE_ROOT_PREFIXES)
    return any(abs_path == root or abs_path.startswith(root.rstrip(os.sep) + os.sep) for root in roots)


def _cross_file_analyzer_node(state: AITesterState) -> dict[str, Any]:
    """3.5 跨文件修复：分析被测代码的跨文件依赖关系（CROSS_FILE_ENABLE=true 时启用）。

    流程：
        1. 从 state["target_code"] 提取源码；
        2. 调用 analyze_cross_file_deps 做 AST 依赖分析（entry → target 的 import 关系）；
        3. 把依赖边列表写入 state["cross_file_deps"]（供后续节点 / 报告使用）；
        4. 若依赖图为空（单文件项目），写入空列表并降级为单文件模式
           （cross_file_plan 置 None，后续 patch_applier 走单文件路径）。

    设计约束：
        - 默认关闭（CROSS_FILE_ENABLE=false），启用时需显式设置环境变量；
        - 单文件项目自动降级（依赖边为空时 cross_file_plan 保持 None）；
        - 节点不直接生成补丁，仅做"协调器"角色（依赖分析 + 路由决策），
          补丁生成仍由现有 _debugger_node 完成（提议者角色），保持 LLM 调用路径不变。

    Args:
        state: 当前工作流状态（含 target_code / target_file / module_name 等字段）。

    Returns:
        更新后的状态字典，包含 cross_file_deps（依赖边列表，可为空）。
    """
    t0 = time.time()
    entry_module = state.get("module_name") or os.path.basename(state.get("target_file", ""))
    target_code = state.get("target_code", "")

    # 3.5 二期：多入口依赖分析（保守口径：一级展开，不递归——防依赖图爆炸）。
    # 当前 state 中仅 target_code 可用（单入口视角），entry_modules 传 [entry]；
    # 未来扩展多入口时，把其他模块名追加进 entry_modules 即可，节点无需改动。
    source_files: dict[str, str] = {}
    entry_modules: list[str] = []
    if entry_module:
        source_files[entry_module] = target_code
        entry_modules.append(entry_module)
    # 若有其他模块内容（未来扩展），在此追加到 source_files 与 entry_modules

    deps = analyze_multi_entry_deps(entry_modules, source_files)
    _trace_node(
        "cross_file_analyzer",
        output_summary={
            "entry_module": entry_module,
            "dep_edges": len(deps),
        },
        decision="deps_found" if deps else "single_file_fallback",
        duration_ms=(time.time() - t0) * 1000,
        iteration=state.get("iteration", 0),
    )

    # 显式 asdict（而非 d.__dict__）：dataclass 未来加内部字段会无声改变
    # state["cross_file_deps"] 的 schema，下游节点按固定 key 取值的契约
    # （_patch_applier_node :985）保持稳定——2026-09-26 全面审查修复
    #
    # 2026-10 P3（A/B 阴性结果驱动）：跨文件任务预置依赖边（_write_cross_file_state
    # 按 dep_chain 写入 state["cross_file_deps"]）时，本节点只对被调方
    # target_code（如 module_c）做 AST 分析——module_c 是被调方，其 import
    # 方向为反向（不 import 调用方 module_a/b）→ AST 分析 0 条边 → 覆盖预置边。
    # 修复：AST 分析结果为空、且预置边非空时，保留预置边（双向依赖图：被调方
    # 视角缺失的"调用方 → 被调方"反向边由 dep_chain 预置补全）。预置边为空时
    # 维持历史 AST 单视角口径（零行为变化）。
    _preset_deps = state.get("cross_file_deps") or []
    if deps:
        # AST 分析命中 → 用 AST 结果（历史口径）
        # O11（2026-09-29 审查 P1）：显式标记边来源为 AST 推导
        # （区别于 _write_cross_file_state 的 benchmark 层预置边）。
        # "source": "ast_derived" 使实验分析能区分两类边，
        # 跨文件 A/B 结论可外推的前提是两类边均非空。
        _ast_edges = [asdict(d) for d in deps]
        for _edge in _ast_edges:
            _edge["source"] = "ast_derived"
        update: dict[str, Any] = {"cross_file_deps": _ast_edges}
    elif _preset_deps:
        # AST 为空 + 预置边非空 → 保留预置边（双向依赖图反向补全）
        update = {"cross_file_deps": _preset_deps}
        logger.info(
            "3.5 跨文件修复：AST 单视角 0 条边，保留预置依赖边 %d 条"
            "（双向依赖图：被调方视角缺失的调用方反向边由 dep_chain 补全）",
            len(_preset_deps),
        )
    else:
        # 无 AST 边 + 无预置边 → 历史单文件降级口径
        update = {"cross_file_deps": []}

    # ── P0 1.1 分层代码压缩（跨文件调用链上下文）────────────────────────
    # 跨文件任务时，为每个依赖边的 target_module 构建"目标函数 → 被调函数
    # （CODE_FOCUS_DEPTH 层）"的调用链上下文（纯静态、不消耗 LLM token），
    # 写入 state["cross_file_contexts"]：{module_name: focused_code}。
    # 后续 _debugger_node 生成跨文件补丁时把相关模块的聚焦上下文一并注入
    # prompt，替代"整模块全文 → 截断猜"的旧口径。
    if deps:
        from src.tools.code_analyzer import extract_function_context

        focused_contexts: dict[str, str] = {}
        for dep in deps:
            module_src = source_files.get(dep.target_module, "")
            if not module_src:
                continue
            focused = extract_function_context(module_src, dep.symbol, depth=CODE_FOCUS_DEPTH)
            if focused:
                focused_contexts.setdefault(dep.target_module, focused)
        if focused_contexts:
            update["cross_file_contexts"] = focused_contexts
            # L4 逻辑修复（2026-09-29 审查）：source_files 一期仅含 entry
            # 模块（L1349-1351），被依赖模块（dep.target_module）源码未载入
            # → L1382 对非 entry 模块恒 "" 跳过。日志须如实反映"仅 entry
            # 模块生效"，避免高估已构建的模块数（二期扩展跨文件源码载入后
            # 此处可改回全模块口径）。
            logger.info(
                "P0 1.1 跨文件调用链上下文：构建 %d 个模块的聚焦上下文"
                "（depth=%d，当前仅 entry 模块 %s 生效——被依赖模块源码"
                "二期扩展后自动纳入）",
                len(focused_contexts),
                CODE_FOCUS_DEPTH,
                state.get("module_name") or os.path.basename(state.get("target_file") or ""),
            )

    # 单文件项目降级：依赖边为空时不生成跨文件计划（保持单文件路径）
    if not deps:
        logger.info("3.5 跨文件修复：依赖图为空（单文件项目），降级为单文件模式")
        update["cross_file_plan"] = None
    else:
        logger.info("3.5 跨文件修复：发现 %d 条跨文件依赖边", len(deps))
        # 完整修复计划由 _debugger_node 后续生成（协调器-提议者：提议者=debugger）
        update["cross_file_plan"] = None  # 占位，待二期实现完整计划构建
    return update


def _write_file_atomic(path: str, content: str) -> None:
    """先写临时文件再 os.replace 原子替换目标文件。

    直接 open(path, "w") 会先截断再写，中途崩溃会留下被截断的用户源文件；
    原子替换保证任何时刻目标文件要么是旧内容、要么是完整新内容。

    Args:
        path: 目标文件路径。
        content: 要写入的完整内容。
    """
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", prefix=".aitester_", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        # 失败时清理临时文件，避免残留；再把异常抛给调用方。
        # 用 Exception 而非 BaseException（PEP 8）：KeyboardInterrupt/SystemExit
        # 不应插入清理路径，临时文件由进程退出兜底回收
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def _select_multi_candidate_patch(
    state: AITesterState,
    original_code: str,
    iteration: int = 0,
) -> tuple[str, bool, dict[str, Any]]:
    """3.1 多候选补丁：生成 N 候选 + 静态筛选 + 执行验证，返回最优候选。

    无有效候选（全静态拒绝 / 执行全失败）时回退到 state 中的单补丁，
    保证多候选策略不会比原单补丁路径更差（只多不少）。

    5.2 持续细化：把多候选统计放入返回的 update dict
    （candidates / static_passed / exec_validated / selected），供
    refine_failure_category 识别 MULTI_CANDIDATE_ALL_REJECTED 类别。
    经 update dict 传递而非原地写 state（节点函数保持无副作用约定，
    避免 --parallel 线程下共享 TypedDict 串扰）。

    执行验证开关：环境变量 MULTI_CANDIDATE_EXEC_VALIDATE=true 时启用
    逐候选跑测试（成本更高但筛选更准），默认关闭走纯静态筛选。

    P0 3.2 多候选自适应触发（MULTI_CANDIDATE_TRIGGER_STRATEGY）：
    - adaptive（默认）：仅当 iteration >= 1（首次修复已失败）且
      error_category ∈ {assertion, runtime, logic_error, index_error}
      时启用多候选；简单任务 / 早期迭代保持单候选，省 Token。
    - always：历史口径，每次失败都启用多候选。

    Args:
        state: 当前工作流状态（含 target_code / generated_test / failed_cases /
            target_function / module_name 等字段）。
        original_code: 本轮修复的原始被测代码。
        iteration: 当前迭代轮次（从 0 开始），供自适应触发判断。

    Returns:
        (最优候选应用后的代码, 是否成功应用, update dict 含 multi_candidate_stats)。
        回退单补丁时与原 apply_patch_to_code 同口径。
    """
    # P0 3.2 多候选自适应触发（MULTI_CANDIDATE_TRIGGER_STRATEGY=adaptive 时，
    # 仅当"首次修复已失败（iteration >= 1）且错误类型 ∈ 困难类别"才启用；
    # 否则回退单候选，避免简单任务 +79% Token 的无收益成本）
    strategy = os.getenv("MULTI_CANDIDATE_TRIGGER_STRATEGY", "adaptive").strip().lower()
    if strategy == "adaptive":
        error_category = state.get("error_category") or "unknown"
        if iteration < 1 or error_category not in _HARD_ERROR_CATEGORIES:
            logger.info(
                "P0 3.2 多候选自适应触发：iteration=%d error_category=%s 不满足启用条件"
                "（iteration>=1 且 category∈%s），回退单候选",
                iteration,
                error_category,
                _HARD_ERROR_CATEGORIES,
            )
            # 回退单候选路径（与 else 分支同口径）
            new_code, applied = apply_patch_to_code(original_code=original_code, patch=state.get("patch") or "")
            update: dict[str, Any] = {
                "multi_candidate_stats": {
                    "candidates": 1,
                    "static_passed": 1 if applied else 0,
                    "exec_validated": False,
                    "selected": 0 if applied else None,
                    "adaptive_skipped": True,
                    "skip_reason": f"iteration={iteration},category={error_category}",
                }
            }
            return new_code, applied, update

    n = multi_candidate_count()
    debugger = DebuggerAgent()
    candidates = generate_candidates(
        debugger=debugger,
        target_code=original_code,
        test_output=state.get("test_output") or "",
        failed_cases=state.get("failed_cases") or [],
        num_candidates=n,
        focus_function=state.get("target_function"),
        target_module=state.get("module_name"),
    )
    use_exec = multi_candidate_exec_validate()
    executor = ExecutorAgent(timeout=EXECUTION_TIMEOUT, use_venv=EXECUTOR_USE_VENV) if use_exec else None
    best = select_best_candidate(
        candidates=candidates,
        original_code=original_code,
        test_code=state.get("generated_test") or "",
        target_file=state.get("target_file"),
        target_function=state.get("target_function"),
        use_execution_validation=use_exec,
        executor=executor,
        # 3.3 改进：把历史执行反馈轨迹传入，供轻量奖励预测器调节候选排序
        execution_trace=state.get("execution_trace"),
    )
    static_passed_count = sum(1 for c in candidates if c.static_passed)
    _trace_node(
        "multi_candidate",
        output_summary={
            "candidates": len(candidates),
            "static_passed": static_passed_count,
            "exec_validated": use_exec,
            "selected": (best.index if best else None),
        },
        decision=f"selected_{best.index + 1}" if best else "fallback_single",
        iteration=state.get("iteration", 0),
    )
    # 5.2 持续细化：记录多候选统计（供 refine_failure_category 识别
    # MULTI_CANDIDATE_ALL_REJECTED：candidates>0 且 static_passed==0）
    # 走 update dict 而非原地写 state（节点函数应保持无副作用；state 是
    # LangGraph 共享 TypedDict，原地写入在 --parallel 线程下会串扰）
    stats_update: dict[str, Any] = {
        "multi_candidate_stats": {
            "candidates": len(candidates),
            "static_passed": static_passed_count,
            "exec_validated": use_exec,
            "selected": best.index if best else None,
        },
    }
    if best is None:
        # 多候选全部失败 → 回退到单补丁（保持历史行为，不引入劣化）
        logger.info("多候选无有效补丁，回退到单补丁流程")
        code, applied = apply_patch_to_code(original_code=original_code, patch=state.get("patch") or "")
        return code, applied, stats_update
    code, applied = apply_patch_to_code(original_code=original_code, patch=best.patch)
    return code, applied, stats_update


def _safe_write_patch(
    original_code: str,
    new_code: str,
    applied: bool,
    state: AITesterState,
    snapshot_out: dict[str, Any] | None = None,
) -> bool:
    """
    安全检查 + 原子写盘：将新代码写入 state["target_file"]。

    三道安全检查（任一不过则拒绝写入，返回 False）：
    1. 补丁不能是空字符串或比原代码短得多（防止 LLM 返回空文件）；
    2. 补丁必须含至少一个函数定义（防止 LLM 返回无意义内容）；
    3. 目标路径必须在项目根目录或系统临时目录内（防路径穿越），
       且不得命中仓库核心保护清单（L-1 安全加固，防覆盖 config.py /
       main.py / .git / src/ 等仓库自身文件；开关 PATCH_PROTECT_REPO_CORE）。

    Args:
        original_code: 应用补丁前的原始代码（用于长度比较安全检查）。
        new_code: 应用补丁后的新代码。
        applied: 补丁应用是否成功（静态校验通过）。
        state: 当前状态，读取 target_file 与写入路径校验。
        snapshot_out: O35（2026-09-30 全面审查 P1）M6 快照出参——写盘成功时
            回填 ``{"path": ..., "iteration": ...}``。此前本函数把快照路径
            ``state.setdefault(...)`` 进**节点入参 dict**，而 LangGraph 每个
            super-step 都从 channel 值重新物化状态、原地改写入参永不回写
            （实测 langgraph 1.2.11），导致 ``_rollback_last_patch`` 永远读到
            空快照、M6"坏补丁回滚"从未真正执行。现经出参把快照交还调用方，
            由 ``_patch_applier_node`` 放进**返回的 update dict**（合法通道）。

    Returns:
        True 表示代码已写盘，False 表示被安全检查拒绝或补丁未生效。
    """
    if not applied or new_code == original_code:
        return False
    # 安全检查 1：空或过短（长度 < 原代码 10%，防 LLM 返回残缺文件）
    if not new_code or len(new_code) < len(original_code) * 0.1:
        logger.error("补丁内容异常（空或过短），跳过写入: %s", state["target_file"])
        return False
    # 安全检查 2：必须含至少一个函数定义（防 LLM 返回无意义内容）。
    # 单遍字符串扫描（re.search 命中即停，不再把补丁全文逐行拆成
    # list[str] 再逐行 startswith——补丁普遍数百行，每次应用都产生
    # O(行数) 临时列表，--parallel 场景下累积可观）
    if not _HAS_FUNC_DEF_RE.search(new_code):
        logger.error("补丁不含任何函数定义，跳过写入: %s", state["target_file"])
        return False
    # 安全检查 3：路径白名单（项目根目录或系统临时目录，前缀比较带 os.sep 防兄弟目录碰撞）
    # 白名单根在模块加载期归一化（_ALLOWED_WRITE_ROOTS，abspath 与历史判定语义一致）
    target_file_path = os.path.abspath(state["target_file"])
    if not _is_within_allowed_roots(target_file_path):
        logger.error("非法文件路径，拒绝写入: %s", state["target_file"])
        return False
    # 安全检查 4（L-1 安全加固，2026-09-29）：仓库核心路径黑名单——
    # target_file 命中 config.py / main.py / init_db.py / .git / src/ 等
    # 仓库核心文件/目录时拒绝写入（防 LLM 内容覆盖仓库自身源码；
    # 临时目录任务不受影响，开关 PATCH_PROTECT_REPO_CORE 默认开）。
    if _is_repo_core_path(target_file_path):
        logger.error("目标路径命中仓库核心保护清单，拒绝写入: %s", state["target_file"])
        return False
    # M6（2026-09-29 审查 P0）：写盘前快照（shutil.copy2 到 tempfile 目录）。
    # 若后续 executor 判定本补丁失败（test_passed=False），_rollback_last_patch
    # 读取 state["last_patch_snapshot"] 恢复原始代码，使修复质量不被坏补丁
    # 污染。快照失败（IO / 权限）不阻断写盘——历史行为保持，但记 WARNING。
    snapshot_path: str | None = None
    try:
        _snap_dir = os.path.join(
            tempfile.gettempdir(),
            f"aitester_patch_snap_{os.getpid()}_{threading.get_ident()}",
        )
        os.makedirs(_snap_dir, exist_ok=True)
        snapshot_path = os.path.join(
            _snap_dir,
            f"iter{int(state.get('iteration', 0))}_{os.path.basename(state['target_file'])}",
        )
        shutil.copy2(os.path.abspath(state["target_file"]), snapshot_path)
        # O35：快照经出参交还调用方（由 _patch_applier_node 放进返回的 update
        # dict）。此前的 state.setdefault(...) 改写的是 LangGraph 传入的节点
        # 入参 dict——每 super-step 由 channel 值重新物化，原地改写永不回写，
        # 快照路径因此从未进入 state（M6 回滚链路整体失效）。
        if snapshot_out is not None:
            snapshot_out["path"] = snapshot_path
            snapshot_out["iteration"] = int(state.get("iteration", 0))
    except Exception:
        logger.warning("M6 补丁快照写入失败（不影响写盘）: %s", state["target_file"], exc_info=True)
    # 原子写入：写临时文件后 os.replace，崩溃不损坏用户源文件
    # 写目标用 abspath（无符号链接归一化）：白名单判定走 realpath 语义，
    # 写盘路径保持调用方视角的原始路径（行为与历史一致）
    _write_file_atomic(os.path.abspath(state["target_file"]), new_code)
    logger.info("补丁已应用到文件: %s（M6 快照=%s）", state["target_file"], snapshot_path)
    return True


def _rollback_last_patch(state: AITesterState) -> bool:
    """M6（2026-09-29 审查 P0）：恢复上一轮补丁写盘前的原始代码快照。

    _safe_write_patch 在写盘前把原始代码 shutil.copy2 到
    tempfile.gettempdir()/aitester_patch_snap_<pid>_<thread>/iter<N>_<basename>，
    快照路径经 update dict（"path" 键）由 _patch_applier_node 写入
    state["_last_patch_snapshot"]。本函数读取该快照，原子写回 target_file。

    快照缺失 / IO 异常时保守返回 False（不影响主流程）。

    O35：**键清理必须经 update dict**——本函数内 ``state.pop(...)`` 改写的是
    LangGraph 传入的节点入参 dict（每 super-step 从 channel 重新物化），不会
    回写状态。故调用方（_executor_node）回滚成功后须把
    ``_last_patch_snapshot / _last_patch_iteration`` 置 None 一并返回；此处的
    pop 仅作调用方局部字典的即时清理，保留以兼容直连调用（单测 / 内嵌场景）。
    """
    snap = state.get("_last_patch_snapshot")
    if not snap or not os.path.isfile(snap):
        return False
    target = os.path.abspath(state.get("target_file", ""))
    if not target:
        return False
    try:
        with open(snap, encoding="utf-8") as f:
            snap_content = f.read()
        _write_file_atomic(target, snap_content)
        os.remove(snap)
        state.pop("_last_patch_snapshot", None)
        state.pop("_last_patch_iteration", None)
        logger.info("M6 坏补丁回滚成功：恢复 %s（快照=%s）", state["target_file"], snap)
        return True
    except Exception:
        logger.warning("M6 坏补丁回滚失败（保留当前文件）: %s", state["target_file"], exc_info=True)
        return False


def _patch_applier_node(state: AITesterState) -> dict[str, Any]:
    """
    补丁应用节点：将 Debugger 生成的补丁应用到被测代码，并写回文件。
    应用后更新 iteration 计数器，供下次循环使用。

    2.2 补丁后处理重采样（PATCH_RESAMPLE_ENABLE=true，默认关）：应用失败
    （定位不到目标函数 / AST 解析不通过）时，把"负面反馈"回传 Debugger
    重新生成一次（严格 prompt + 1.3 降级链档位收紧温度），最多
    PATCH_RESAMPLE_MAX（默认 2）次；仍失败则把该轮标记为
    patch_syntax_invalid（refine_failure_category 消费）并保留原代码。

    1.3 分层压缩降级链（CONTEXT_TIER_DOWNGRADE_ENABLE=true，默认关）：
    符号守卫（check_naming_contract）拒绝补丁时，调 advance_context_tier()
    推进上下文档位，并把 (档位, 缺失符号) 作为 contract_reject_feedback
    写入 state——下一轮 _debugger_node 读到该反馈后按"更高约束"的
    上下文（补丁配方保留 / 签名+import 极简）+ 更低温度重新生成。
    未启用时（默认）行为与历史完全一致（仅拒绝本轮、不动档位）。

    状态/磁盘一致性：只有当补丁真正写入磁盘成功时，才把 target_code 更新为
    新代码并记录 patch_applied=True；任何一道安全检查（空/过短/无函数定义/
    路径不合法）拒绝写入时，target_code 保持原代码、patch_applied 记 False，
    避免下游 Executor 测旧文件、Debugger 却分析新代码的"幻象迭代"。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典，包含更新后的 target_code 和修复历史。
    """
    original_code = state["target_code"]

    # ── 3.1 多候选补丁分支（ENABLE_MULTI_CANDIDATE_PATCH=true 时启用）──
    # 默认关闭，保持历史单补丁口径。开启时：生成 N 个候选 → 静态筛选 →
    # （可选）执行验证 → 选最优候选作为本轮补丁。任一环节无有效候选时
    # 回退到 state 中已有的单补丁（state["patch"]），不引入劣化。
    # ── 3.5 跨文件修复：cross_file_deps 非空时走多文件补丁路径 ─────────────
    # 多候选分支的额外状态更新（multi_candidate_stats，经 update dict 传递）
    multi_candidate_update: dict[str, Any] = {}
    new_code: str
    applied: bool
    cross_file_deps = state.get("cross_file_deps") or []
    if cross_file_deps and cross_file_enabled():
        # 3.5 跨文件修复分支：按依赖图拓扑序对多个模块应用补丁
        from src.tools.cross_file import CrossFileDependency, apply_multi_file_patch, cross_file_fallback_single_file

        # 把 state 中序列化的依赖边还原为 CrossFileDependency 对象
        # （拓扑序补丁应用需要结构化边信息，被调用方先改、调用方后改）
        dep_objects = [
            CrossFileDependency(
                source_module=d.get("source_module", ""),
                target_module=d.get("target_module", ""),
                symbol=d.get("symbol", ""),
                call_line=int(d.get("call_line", 0)),
                context=d.get("context", ""),
            )
            for d in cross_file_deps
        ]
        # 从 state 收集所有模块的原始代码（当前仅 target_code 可用；
        # 二期扩展后从 source_files 字典读取）
        entry_module = state.get("module_name") or os.path.basename(state.get("target_file", ""))
        original_files = {entry_module: original_code}
        # 多文件补丁：entry_module 用 state["patch"]（当前单补丁路径生成），
        # 其他模块的补丁由 _debugger_node 后续生成（二期）
        patches: dict[str, str] = {}
        if state.get("patch"):
            patch_val = state["patch"]
            assert isinstance(patch_val, str)  # TypedDict 标 str | None，真值守卫后必为 str
            patches[entry_module] = patch_val
        # 尝试多文件应用（传依赖边 → 拓扑序）；失败时降级为单文件
        new_files, applied = apply_multi_file_patch(original_files, patches, entry_module, deps=dep_objects)
        new_code = new_files.get(entry_module, original_code)
        if not applied:
            # 多文件失败 → 降级单文件（保守口径，不引入劣化）
            logger.info("3.5 跨文件补丁应用失败，降级单文件模式")
            # 注意：cross_file_fallback_single_file 返回 (新文件映射, 成功)，
            # 需再取 entry_module 的代码字符串——此前误把整个映射当 new_code，
            # len(dict) 恒为 1，降级补丁永远卡在"过短"安全检查、永远写不进盘
            fallback_files, applied = cross_file_fallback_single_file(original_files, patches, entry_module)
            new_code = fallback_files.get(entry_module, original_code)
    elif multi_candidate_available():
        new_code, applied, multi_candidate_update = _select_multi_candidate_patch(
            state, original_code, iteration=state.get("iteration", 0)
        )
    else:
        new_code, applied = apply_patch_to_code(original_code=original_code, patch=state.get("patch") or "")

    # ── 1.1 LLM 输出后处理层（P1 空壳检测 + P2/P3 卫生化，默认观测口径）──
    # P2 导入回填 / P3 契约别名回填默认关（环境变量控制，见
    # patch_postprocess.postprocess_enabled_flags）；P1 空壳检测默认启用，
    # 仅产出"empty_patch"标签观测（EMPTY_LLM_PATCH 场景从不可观测变为
    # 可识别标签，供 refine_failure_category / 实验分析消费），不改代码。
    # P2/P3 启用时：卫生化结果替换本轮 patch 后重新应用（仅单文件分支；
    # 多候选/跨文件分支的候选池各有独立静态筛选，不重复卫生化）。
    postprocess_labels: list[str] = []
    postprocess_update: dict[str, Any] = {}
    if (not cross_file_deps or not cross_file_enabled()) and not multi_candidate_available():
        try:
            from src.tools.patch_postprocess import postprocess_enabled_flags, sanitize_patch

            _pp_flags = postprocess_enabled_flags()
            _sanitized, _pp_labels = sanitize_patch(original_code, state.get("patch"))
            postprocess_labels = list(_pp_labels)
            if (_pp_flags["import_repair"] or _pp_flags["contract_alias"]) and (
                "imports_repaired" in _pp_labels or "contract_aliases_restored" in _pp_labels
            ):
                # P2/P3 生效：用卫生化后的补丁重新应用单文件路径
                new_code, applied = apply_patch_to_code(original_code=original_code, patch=_sanitized)
            postprocess_update["postprocess_labels"] = postprocess_labels
        except Exception:
            logger.debug("1.1 后处理层执行异常（保守跳过，保持历史口径）", exc_info=True)

    # P0 1.3 命名契约检查：补丁应用前对比修改前后的模块级符号集合
    # （函数/类/__all__/注册装饰器/插件入口点），缺失任何原符号则拒绝应用。
    # 开关 PATCH_CONTRACT_CHECK（默认 true）；设 false 回退历史口径。
    # S2 安全（2026-09-29）：dangerous_api_added 守卫——补丁新引入
    # os.system / subprocess / eval / 网络外连 / 凭证读取时拒绝应用
    # （开关 PATCH_DANGEROUS_API_GUARD，默认 true；与命名契约检查并列）。
    contract_missing: list[str] = []
    _naming_contract: tuple | None = None
    _dangerous_added: list[str] | None = None
    if applied and new_code != original_code:
        from src.tools.patch_applier import check_naming_contract, dangerous_api_added

        _naming_contract = check_naming_contract(original_code, new_code)
        ok, missing = _naming_contract
        # P0-4 性能（2026-10-01）：预计算 AST 危险差集，供下方 S2 双保险复用
        # （同一 (original, new) 输入只算一次，避免重复 ast.parse×2）
        _dangerous_added = dangerous_api_added(original_code, new_code)
        if not ok:
            logger.warning("P0 1.3 命名契约检查失败，拒绝应用补丁：缺失符号 %s", missing)
            applied = False
            new_code = original_code
            contract_missing = list(missing)
            # 1.3 分层压缩降级链：守卫拒绝时推进上下文档位（进程内状态），
            # 并把 (档位名, 缺失符号) 经 state 透传给下一轮 _debugger_node。
            # 开关 CONTEXT_TIER_DOWNGRADE_ENABLE（默认 false，保持历史口径；
            # true 时降级链全链路生效）。
            if _context_tier_downgrade_enabled():
                from src.tools.patch_applier import _current_context_tier, advance_context_tier

                advance_context_tier()
                tier_name, _idx, _temp = _current_context_tier()
                # 临时键：本节点函数内先写入、末尾经 state.pop 取出合并进返回
                # dict（键本身不进入 LangGraph 通道——通道键为
                # contract_reject_feedback，见 1.3 降级链注释）。mypy 无法
                # 对 TypedDict 的临时动态键收窄，故对 state 做窄化 cast。
                _state = cast("dict[str, Any]", state)
                _state["_1_3_contract_feedback"] = {
                    "tier": tier_name,
                    "missing_symbols": contract_missing,
                }
            # mypy：同上，cast 收窄（临时键不入 TypedDict 声明）
            cast("dict[str, Any]", state)["_1_3_contract_missing"] = contract_missing
        if applied:
            # S2 安全双保险（2026-09-29 审查）：危险操作拦截走正则
            # （injection_guard.check_llm_patch_safety，默认开）+ AST 差集
            # （patch_applier.dangerous_api_added，默认开）双通道。
            # 正则 findings 或 AST 差集非空即拒绝（保守不引入半应用状态）。
            from src.agents.injection_guard import check_llm_patch_safety

            _regex_hits = check_llm_patch_safety(new_code)
            # P0-4 性能（2026-10-01）：复用上方已算的 dangerous_api_added 结果，
            # 避免对同一 (original_code, new_code) 重复做 AST 差集（两遍
            # ast.parse×2）
            _added = _dangerous_added if _dangerous_added is not None else dangerous_api_added(original_code, new_code)
            _hits = list(dict.fromkeys(_regex_hits + _added))  # 去重保序
            if _hits:
                logger.warning("S2 危险操作拦截：补丁被拒绝（%s）", "、".join(_hits))
                applied = False
                new_code = original_code

    # ── 2.2 改进：补丁后处理重采样（PATCH_RESAMPLE_ENABLE=true，默认关）──
    # 应用失败（定位不到目标函数 / AST 解析不通过）时，把"负面反馈"回传
    # Debugger 重新生成（严格 prompt + 1.3 降级链档位收紧温度），最多
    # PATCH_RESAMPLE_MAX（默认 2）次；仍失败则把该轮标记为
    # patch_syntax_invalid（refine_failure_category 消费）并保留原代码。
    # 未启用时（默认）行为与历史完全一致，不产生额外 LLM 调用。
    resample_stats: dict[str, Any] | None = None
    if not applied and _patch_resample_enabled():
        from src.agents.debugger import DebuggerAgent
        from src.tools.patch_applier import apply_patch_with_resample

        resampler = DebuggerAgent()

        def _on_resample(query: str, original_code: str, patch: str, ast_error: str) -> str | None:
            """2.2 重采样回调：严格 prompt + 1.3 降级链档位温度重新生成补丁。

            注入"被拒补丁 + AST 错误 + 原始代码片段 + 档位温度"，让 LLM 在
            更高约束下修订。返回的修订补丁已通过静态验证（AST 合法 + 不破坏
            命名契约 + 能成功应用）才返回，否则 None（保守保留原代码）。
            """
            if not patch and not ast_error:
                return None
            # 提取被拒补丁里的 python 代码块（LLM 输出可能带 markdown 包裹）
            from src.utils.helpers import extract_code_block

            _rejected = extract_code_block(patch or "", language="python") or (patch or "")[:1000]
            # 注入 1.3 降级链档位（被符号守卫拒绝后自动降级到的档位）
            from src.tools.patch_applier import _current_context_tier

            _tier_name, _idx, _temp = _current_context_tier()
            strict_prompt = (
                "【补丁语法校验失败反馈】上一轮补丁应用后 AST 解析失败或未能定位到目标函数，"
                f"具体错误：\n{ast_error[:500]}\n\n"
                "请基于同样的错误上下文，重新生成一个语法合法的补丁。"
                "必须保留原文件中所有模块级符号（函数名/类名/__all__/注册装饰器/插件入口点），"
                "只允许修改函数/方法体内部逻辑。用 ```python ... ``` 包裹输出。"
                f"\n\n【当前档位：{_tier_name}（温度 {_temp}）】"
                f"\n【被拒补丁片段】\n```\n{_rejected}\n```\n"
                f"\n【原始代码片段】\n```\n{(original_code or '')[:2000]}\n```"
            )
            try:
                _result = resampler._call_llm_with_cache(strict_prompt, temperature=_patch_resample_temperature())
                _extracted = extract_code_block(_result or "", language="python")
                if not _extracted:
                    return None
                # 二次静态验证：必须能 ast.parse 且不破坏命名契约
                from src.tools.patch_applier import safe_apply_patch

                _try_code, _try_ok = safe_apply_patch(original_code, _extracted)
                if not _try_ok:
                    return None
                # P0-4 性能（2026-10-01）：safe_apply_patch 已对
                # (original_code, _extracted) 做过命名契约 + 危险 API 差集
                # （safe_apply_patch_contract 路径），此处重复调用是纯冗余
                # AST 解析。契约结果已由 safe_apply_patch 把关（_try_ok
                # 非 True 即代表契约/语法/危险 API 任一失败），此处仅保留
                # 契约检查用于收集 missing 符号供日志观测（缺失时保守返回
                # None 与原行为一致）。
                from src.tools.patch_applier import check_naming_contract as _ck

                _contract_ok, _missing = _ck(original_code, _try_code)
                if not _contract_ok:
                    return None
                return _extracted
            except Exception:
                logger.debug("2.2 重采样 LLM 调用失败（保守返回 None，不阻断主流程）", exc_info=True)
                return None

        new_code, applied, resample_stats = apply_patch_with_resample(
            original_code,
            state.get("patch") or "",
            resample_fn=_on_resample,
            max_resamples=_patch_resample_max(),
        )
        if resample_stats.get("resampled"):
            logger.info(
                "2.2 补丁后处理重采样 %d 次，成功=%s",
                resample_stats.get("resample_count", 0),
                resample_stats.get("success", False),
            )
            # 重采样成功后重新走契约检查与写盘路径
            if applied and new_code != original_code:
                from src.tools.patch_applier import check_naming_contract as _ck

                _ok2, _missing2 = _ck(original_code, new_code)
                if not _ok2:
                    logger.warning("2.2 重采样后命名契约仍被破坏（%s），拒绝写盘", _missing2[:5])
                    applied = False
                    new_code = original_code
                    contract_missing = list(_missing2)
            if resample_stats.get("success") is False and resample_stats.get("resampled"):
                # 2.2 标记：重采样耗尽仍失败 → patch_syntax_invalid
                # （refine_failure_category 在任务收尾时消费）
                cast("dict[str, Any]", state)["_2_2_patch_syntax_invalid"] = True

    # 默认视为"未真正写盘"，任何安全检查失败都保持该值。
    # O35（P1）：快照经出参取回（见 _safe_write_patch 的 snapshot_out 注释），
    # 再放进本函数**返回的 update dict**——只有经 update dict 才会被 LangGraph
    # 写回 channel，_rollback_last_patch（下一轮 executor）才读得到快照。
    _snapshot: dict[str, Any] = {}
    written = _safe_write_patch(original_code, new_code, applied, state, snapshot_out=_snapshot)

    # 状态/磁盘一致性：仅写盘成功才更新 target_code，否则保留原代码
    effective_code = new_code if written else original_code

    # 0.8 一致性口径：节点函数保持"纯函数更新字典"（--parallel 线程下
    # LangGraph 共享 TypedDict 不允许原地写）——此前 history.append 直接
    # 改写 state["repair_history"] 原列表（其他节点/路由对同一 state 的读取
    # 会看到被改写的中间值）；现改为拷贝后追加、经 update dict 写回
    history = list(state.get("repair_history") or [])
    history.append(
        {
            "iteration": state.get("iteration", 0) + 1,
            "diagnosis": state.get("diagnosis", ""),
            "error_category": state.get("error_category", "unknown"),
            "patch_applied": written,
        }
    )
    # 限制 repair_history 大小，避免无限增长占用内存（最多保留 _MAX_REPAIR_HISTORY 条）
    if len(history) > _MAX_REPAIR_HISTORY:
        history = history[-_MAX_REPAIR_HISTORY:]
    _trace_node(
        "patch_applier",
        output_summary={"patch_applied": written, "new_code_len": len(effective_code)},
        decision="written" if written else "rejected",
        iteration=state.get("iteration", 0),
    )
    # 1.3 改进：把本轮契约缺失符号（可能来自 2.2 重采样路径）写回 state，
    # 供 refine_failure_category / 实验分析消费（"5/7 任务破坏 sqlfluff
    # 插件命名契约"场景的直接可观测信号）
    contract_update: dict[str, Any] = {}
    # mypy：_1_3_contract_missing 为本节点函数内写入的临时键（不进入
    # AITesterState TypedDict 声明——通道键为 contract_missing_symbols，
    # 见上方 1.3 注释），对 state 做窄化 cast 消除 typeddict-unknown-key
    _state_pop = cast("dict[str, Any]", state)
    _missing_now = _state_pop.pop("_1_3_contract_missing", None) or []
    if _missing_now:
        contract_update["contract_missing_symbols"] = list(_missing_now)
    # 1.3 降级链档位反馈：透传给 _debugger_node（下一轮 debug 按档位收紧上下文）
    feedback_update: dict[str, Any] = {}
    _feedback_now = _state_pop.pop("_1_3_contract_feedback", None)
    if _feedback_now:
        feedback_update["contract_reject_feedback"] = _feedback_now
    # 2.2 重采样统计 + patch_syntax_invalid 标记（refine 消费）
    resample_update: dict[str, Any] = {}
    if resample_stats is not None:
        resample_stats_out = dict(resample_stats)
        from src.tools.patch_applier import _current_context_tier as _tier_fn

        _tier_name_now, _idx_now, _temp_now = _tier_fn()
        resample_stats_out["tiered_context"] = _tier_name_now
        resample_update["patch_resample_stats"] = resample_stats_out
    _syntax_invalid_flag = _state_pop.pop("_2_2_patch_syntax_invalid", False)
    if _syntax_invalid_flag:
        # patch_syntax_invalid 标记写入 error_category（refine_failure_category
        # 会在任务收尾时把 "patch_syntax_invalid" 归一到 PATCH_SYNTAX_INVALID）
        resample_update["error_category"] = "patch_syntax_invalid"
        # L1 逻辑修复（2026-09-29 审查）：同时补写 TypedDict 通道键
        # patch_syntax_invalid_flag（state.py:242 声明，refine_final_error_category
        # 经 final_state.get("patch_syntax_invalid_flag") 消费）——历史实现只写
        # error_category 字符串值，flag 通道恒 False（死通道），5.2 失败细化
        # 仅靠字符串路径兜底可达，与 TypedDict 契约脱节。双通道一致。
        resample_update["patch_syntax_invalid_flag"] = True
    # 1.4 事件总线接线：PatchApplied（含 1.1 后处理标签，纯观测）
    # P0（2026-09-30 独立审查 N9/R33）：源码补丁证据门在写盘**之后**判定
    # （写盘本身仍受命名契约/危险 API 守卫保护；证据门决定"本轮写盘是否
    # 有确定性证据背书"——无证据时把 patch_applied 标记为 False 并置
    # source_patched_unverified=True，供实验分析"源码腐蚀风险"消费。
    # 证据门 opt-out（PATCH_EVIDENCE_GATE_ENABLE=false）时零行为变化，
    # 证据等级仍记录（供消融对照）。
    _evidence_update: dict[str, Any] = {}
    if applied:
        from src.tools.patch_evidence import (
            assess_patch_evidence,
            evidence_allows_write,
            patch_evidence_gate_enabled,
        )

        _ev_level = assess_patch_evidence(cast("dict[str, Any]", state), original_code, effective_code)
        _evidence_update["patch_evidence_level"] = _ev_level
        if patch_evidence_gate_enabled() and not evidence_allows_write(_ev_level):
            # 无 gold / 谱系定位证据 → 本轮写盘不被独立裁决背书，标记为
            # "未验证的源码修改"（源码已在盘上，下一轮 executor 若失败
            # 经 M6 回滚通道恢复原文件；本标记供统计层归因）。
            logger.warning(
                "P0 源码补丁证据门：本轮补丁证据等级=%s（不足 gold/sbfl），"
                "标记 source_patched_unverified（源码腐蚀风险观测）",
                _ev_level,
            )
            _evidence_update["source_patched_unverified"] = True
        else:
            _evidence_update["source_patched_unverified"] = False
    publish_patch_applied(state, applied=written, new_code=effective_code)
    # O6（2026-09-29 审查 P1）：testless 修复验证层（TESTLESS_VALIDATION_ENABLE=true 时启用，默认关）。
    # 补丁应用成功后，经 run_testless_validation 对 (original_code, effective_code)
    # 做四层静态验证（AST 符号守卫 / mypy / 命名契约 / 导入冒烟），
    # 验证结果写入 state["testless_validation"]（纯观测，不阻断主流程）。
    # 开关关闭时零行为变化，历史口径不变。
    testless_validation_result: dict[str, Any] | None = None
    if written:
        from src.tools.testless_validation import run_testless_validation as _run_tlv
        from src.tools.testless_validation import testless_validation_enabled as _tlv_enabled

        if _tlv_enabled():
            try:
                testless_validation_result = _run_tlv(
                    original_code=original_code,
                    patched_code=effective_code,
                    target_module=state.get("module_name", ""),
                )
                if not testless_validation_result.get("passed", True):
                    logger.info(
                        "O6 testless 验证未通过（失败层: %s），标记为观测信号（不阻断主流程）",
                        testless_validation_result.get("failed_layers", []),
                    )
            except Exception:
                logger.debug("O6 testless 验证执行异常（保守跳过，保持历史口径）", exc_info=True)
    _testless_update: dict[str, Any] = {}
    if testless_validation_result is not None:
        _testless_update["testless_validation"] = testless_validation_result
    return {
        "target_code": effective_code,
        "repair_history": history,
        "iteration": state.get("iteration", 0) + 1,
        **multi_candidate_update,
        **contract_update,
        **feedback_update,
        **resample_update,
        **postprocess_update,
        **_testless_update,
        # P0（2026-09-30 独立审查 N9/R33）：源码补丁证据门（证据等级 +
        # 未验证标记，纯观测；opt-out 时 patch_evidence_level 仍记录）
        **_evidence_update,
        # O35（P1）M6 快照经 update dict 落 channel（仅写盘成功时写；
        # 写盘被拒时不写该键，保留上一轮尚待 executor 消费的快照，
        # 避免把"可回滚状态"提前清空）。
        **(
            {"_last_patch_snapshot": _snapshot["path"], "_last_patch_iteration": _snapshot["iteration"]}
            if "path" in _snapshot
            else {}
        ),
    }


def _validate_planner_output(test_plan: dict[str, Any]) -> bool:
    """
    验证 Planner 输出是否符合预期结构。

    检查必需字段：function_name 和 logic_analysis。

    Args:
        test_plan: PlannerAgent 输出的测试计划字典。

    Returns:
        True 表示结构完整，False 表示需要降级使用默认计划。
    """
    if not isinstance(test_plan, dict):
        return False
    # 必需字段检查
    required_keys = ["function_name", "logic_analysis"]
    for key in required_keys:
        if key not in test_plan:
            logger.warning("Planner 输出缺少必需字段: %s", key)
            return False
    # logic_analysis 内部结构验证
    la = test_plan.get("logic_analysis", {})
    return isinstance(la, dict)


def _get_default_test_plan(function_name: str | None) -> dict[str, Any]:
    """
    生成默认测试计划（降级方案）。

    Args:
        function_name: 目标函数名。

    Returns:
        默认测试计划字典。
    """
    return {
        "function_name": function_name or "unknown",
        "description": "自动生成的默认测试计划",
        "logic_analysis": {
            "input_domain": "未知",
            "output_domain": "未知",
            "preconditions": [],
            "postconditions": [],
            "edge_cases": [],
        },
        "test_cases": [],
    }
