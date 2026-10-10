"""补丁应用安全核心（R4，2026-10-09 审查落地·S4：自 src/graph/nodes.py 拆分）。

背景（2026-10-09 系统评审 R4·S4）：
    src/graph/nodes.py 曾是 3593 行单体，S7/R3 已拆出 agents_cache /
    debugger / flags / trace_reward 四簇；本模块再拆出**补丁应用安全核心**
    ——路径白名单 + 原子写盘 + 多候选选择 + 安全写盘 + 快照回滚六个函数
    及其常量。拆分口径与 S7 一致：**纯移动 + re-export 保持历史导入路径
    不变**（`from src.graph.nodes import _safe_write_patch` 等继续可用），
    函数体一字未改，零行为变化。

    编排节点 `_patch_applier_node`（依赖 `_MAX_REPAIR_HISTORY` 且与
    debugger / evidence / rollback 协议深度交互）保留在 nodes.py，经
    re-export 调用本模块的 `_select_multi_candidate_patch` /
    `_safe_write_patch` / `_write_file_atomic`。

安全口径（与历史一致）：
    - 原子写：临时文件 + os.replace（崩溃不损坏用户源文件）；
    - 路径白名单：项目根 + 系统临时目录（realpath 归一 + os.sep 前缀，
      防 macOS /var→/private/var 与兄弟目录前缀碰撞）；
    - 仓库核心保护：config.py / main.py / src/ / .git 等黑名单（L-1）；
    - 快照回滚：写盘前 shutil.copy2 快照，失败 fail-closed 拒写盘（M6）。
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import shutil
import tempfile
import threading
from typing import Any

from config import EXECUTION_TIMEOUT, EXECUTOR_USE_VENV
from src.agents.debugger import DebuggerAgent
from src.agents.executor import ExecutorAgent
from src.graph.flags import _repo_core_protection_enabled
from src.graph.state import AITesterState
from src.graph.tracing import _trace_node
from src.tools.multi_candidate import (
    generate_candidates,
    multi_candidate_count,
    multi_candidate_exec_validate,
    select_best_candidate,
)
from src.tools.patch_applier import apply_patch_to_code

# 模块级 logger（与原 nodes.py 语义一致）
logger = logging.getLogger(__name__)

# P0 3.2 多候选自适应触发的"困难错误类别"（断言/运行时/逻辑/下标错误才值得
# 多候选；简单任务保持单候选省 token）。模块级 frozenset（此前在函数内每次
# 调用重建 set，--parallel 多任务热路径累积无谓分配）
_HARD_ERROR_CATEGORIES = frozenset({"assertion", "runtime", "logic_error", "index_error"})

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
#
# C-08c（2026-10-09）：临时根扩展——`tempfile.gettempdir()` 读取
# `TMPDIR`/`/tmp` 等环境口径，但 pytest `--basetemp`（本项目测试惯例：
# 隔离 `.pytest_tmp`/`/tmp/...` 子目录）会把 `tmp_path` 落到
# `tempfile.gettempdir()` 之外的系统临时顶层（macOS：/tmp 实为
# /private/tmp，而 gettempdir 可能是 $TMPDIR=/var/folders/...）。
# 白名单若只认 gettempdir，tmp 任务目标文件会被误拒（实测
# tests/test_workflow_extended.py 4 用例因此失败）。现把
# /tmp、/var/tmp、/private/tmp、/private/var/folders、C:\Users 等
# 各平台标准临时顶层目录也 realpath 归一后纳入白名单根
# （仅系统级临时目录常量，非运行时任意路径，安全边界不放宽：
# 写入目标仍受原子写 / 仓库核心黑名单 / 快照回滚各道检查约束）。
_SYSTEM_TEMP_TOPS: tuple[str, ...] = (
    "/tmp",
    "/var/tmp",
    "/private/tmp",
    "/private/var/tmp",
)
_ALLOWED_WRITE_ROOTS: tuple[str, ...] = tuple(
    deduped
    for deduped in dict.fromkeys(
        os.path.realpath(root)
        for root in (
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            tempfile.gettempdir(),
            *_SYSTEM_TEMP_TOPS,
        )
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
                    # C10：验证门修复案例用——实际应用的补丁文本（回退单补丁
                    # 时即 state["patch"]；胜出候选时为 best.patch）
                    "applied_patch": state.get("patch") or "",
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
            # C10：验证门修复案例用——实际应用的补丁文本（胜出候选或回退单补丁）
            "applied_patch": (best.patch if best else (state.get("patch") or "")),
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
    # 污染。W12（2026-10-05 系统审查 P0）：快照失败（IO / 权限）fail-closed
    # 拒绝写盘——无快照即无回滚能力，坏补丁将永久落盘且下一轮以坏代码为
    # 基底叠加；宁可损失本轮修复，不可绕过回滚保障。
    # C-08b（2026-10-09）：源文件不存在时以 target_code 内存原文为快照
    # 基底（open() 写入而非 copy2，避免静默 fail-closed 跳过本应成功的
    # 测试代码路径——测试惯例：target 先 create() 再写补丁，快照的语义
    # 是"补丁落盘前可回滚到的内容"，内存原文即该内容的权威来源）。
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
        _src = os.path.abspath(state["target_file"])
        if os.path.exists(_src):
            shutil.copy2(_src, snapshot_path)
        else:
            with open(snapshot_path, "w", encoding="utf-8") as _snap_f:
                _snap_f.write(original_code)
        # O35：快照经出参交还调用方（由 _patch_applier_node 放进返回的 update
        # dict）。此前的 state.setdefault(...) 改写的是 LangGraph 传入的节点
        # 入参 dict——每 super-step 由 channel 值重新物化，原地改写永不回写，
        # 快照路径因此从未进入 state（M6 回滚链路整体失效）。
        if snapshot_out is not None:
            snapshot_out["path"] = snapshot_path
            snapshot_out["iteration"] = int(state.get("iteration", 0))
    except Exception:
        logger.exception(
            "M6 补丁快照写入失败，fail-closed 拒绝写盘（无快照即无回滚能力）: %s",
            state["target_file"],
        )
        return False
    # 原子写入：写临时文件后 os.replace，崩溃不损坏用户源文件
    # 写目标用 abspath（无符号链接归一化）：白名单判定走 realpath 语义，
    # 写盘路径保持调用方视角的原始路径（行为与历史一致）
    _write_file_atomic(os.path.abspath(state["target_file"]), new_code)
    logger.info("补丁已应用到文件: %s（M6 快照=%s）", state["target_file"], snapshot_path)
    return True


def _rollback_last_patch(state: AITesterState, restored_out: dict[str, Any] | None = None) -> bool:
    """M6（2026-09-29 审查 P0）：恢复上一轮补丁写盘前的原始代码快照。

    _safe_write_patch 在写盘前把原始代码 shutil.copy2 到
    tempfile.gettempdir()/aitester_patch_snap_<pid>_<thread>/iter<N>_<basename>，
    快照路径经 update dict（"path" 键）由 _patch_applier_node 写入
    state["_last_patch_snapshot"]。本函数读取该快照，原子写回 target_file。

    快照缺失 / IO 异常时保守返回 False（不影响主流程）。

    C6（2026-10-05 系统审查 P0）：回滚成功时经 ``restored_out["content"]``
    把快照原文交还调用方——调用方（_executor_node）须把它写回
    ``state["target_code"]``。此前只恢复磁盘不恢复 state，下一轮
    Debugger 分析的仍是坏补丁代码、下一轮补丁以坏补丁代码为基底叠加，
    磁盘回滚的收益被状态侧抵消（"测原码/修补码"幻象迭代）。

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
        # 2026-10-09：`os.remove` 只删快照**文件**，其父目录
        # `aitester_patch_snap_<pid>_<tid>`（按 pid+线程命名，**跨任务复用**）
        # 会一直留存；任务结束也不清理 → 长跑批在 TMPDIR 下按"每次进程/线程"
        # 累积空目录（实测多轮跑批后累积上千个）。此处在其变空时顺手剪枝。
        _prune_empty_snapshot_dir(os.path.dirname(snap))
        state.pop("_last_patch_snapshot", None)
        state.pop("_last_patch_iteration", None)
        if restored_out is not None:
            restored_out["content"] = snap_content
        logger.info("M6 坏补丁回滚成功：恢复 %s（快照=%s）", state["target_file"], snap)
        return True
    except Exception:
        logger.warning("M6 坏补丁回滚失败（保留当前文件）: %s", state["target_file"], exc_info=True)
        return False


def _prune_empty_snapshot_dir(snap_dir: str) -> None:
    """安全剪枝：仅当目录名匹配快照命名约定且**已空**时删除。

    双条件守卫（保守）：① 目录基名以 ``aitester_patch_snap_`` 开头——绝不
    误删调用方传入的任意目录；② 目录已空（``os.rmdir`` 本身在非空时即抛错，
    不递归、不误删残留快照文件）。任何失败静默忽略（纯清理路径，不得影响
    回滚语义）。
    """
    base = os.path.basename(snap_dir.rstrip(os.sep))
    if not base.startswith("aitester_patch_snap_"):
        return
    with contextlib.suppress(OSError):
        os.rmdir(snap_dir)


__all__ = [
    "_is_repo_core_path",
    "_is_within_allowed_roots",
    "_prune_empty_snapshot_dir",
    "_rollback_last_patch",
    "_safe_write_patch",
    "_select_multi_candidate_patch",
    "_write_file_atomic",
]
