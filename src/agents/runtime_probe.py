"""
运行时探针采集层（Runtime Probe，默认关）。

背景（P0 跨文件修复引擎突破方向）：
    当前 DebuggerAgent 生成补丁时仅依赖静态信息（test_output / traceback /
    failed_cases）与 RAG 参考，缺少"关键变量在失败时刻的运行时快照"。
    2026 年 TraceRepair 等框架引入 Probe Agent 捕获运行时证据，
    使修复 Agent 能基于"变量实际值"而非"静态分析猜测"生成候选补丁，
    显著提升仓库级修复质量（文档 assessment §2.2 记录的"0/7 单源任务"
    缺口正是缺少运行时证据的典型症状）。

设计约束（与 ADR-0003 默认关 + ADR-0004 零默认依赖口径一致）：
    - `RUNTIME_PROBE_ENABLE=false`（默认）时，本模块零行为变化：
      Executor 执行路径与历史逐字节一致；
    - 开关开启后，在 pytest 执行失败时，经子线程一次性探针采集
      "失败帧"的运行时快照（变量名 → 值，限深度与大小）：
      在子线程执行 test_code，异常抛出时刻读 exc.__traceback__ 帧链
      （异常栈即精确的失败时刻帧栈，零 trace 开销），而非历史实现的
      sys.settrace exception 事件（CPython 语义下函数体异常不向被调帧
      传播 exception 事件，实测 frames 恒空——2026-09-29 修复）；
      快照经 `build_probe_prompt_section` 渲染为 prompt 片段注入 DebuggerAgent；
    - 探针是**纯观测层**：快照采集失败（帧不可取 / 变量不可序列化）
      时静默降级（返回 None），不阻断 pytest 执行主流程；
    - 快照条目数与单值大小均有上限（_MAX_PROBE_FRAMES / _MAX_PROBE_VALUE_CHARS），
      避免大对象 / 循环引用导致 prompt 爆炸。

使用方式（executor 节点 / executor_runtime 集成）：
    from src.agents.runtime_probe import (
        runtime_probe_enabled,
        capture_failure_snapshot,
        build_probe_prompt_section,
    )

    if runtime_probe_enabled():
        snapshot = capture_failure_snapshot(test_code, target_module)
        probe_section = build_probe_prompt_section(snapshot)
        # 把 probe_section 追加到 debugger prompt 尾部
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# 探针上限常量（避免 prompt 爆炸）
_MAX_PROBE_FRAMES = 3  # 最多捕获的栈帧数（从最内层向外）
_MAX_PROBE_VALUE_CHARS = 200  # 单个变量值序列化后的最大字符数（超出截断）
_MAX_PROBE_VARS_PER_FRAME = 20  # 每帧最多捕获的局部变量数（按值大小排序取前 N）


def runtime_probe_enabled() -> bool:
    """运行时探针开关（RUNTIME_PROBE_ENABLE=true 时启用，默认 false）。"""
    return os.getenv("RUNTIME_PROBE_ENABLE", "false").lower() == "true"


def _serialize_value(value: Any) -> str:
    """把变量值序列化为可注入 prompt 的短字符串（保守截断，防 prompt 爆炸）。"""
    try:
        text = repr(value)
    except Exception:
        text = f"<unrepr-able: {type(value).__name__}>"
    if len(text) > _MAX_PROBE_VALUE_CHARS:
        text = text[:_MAX_PROBE_VALUE_CHARS] + f"…[truncated {len(text) - _MAX_PROBE_VALUE_CHARS} chars]"
    return text


def _capture_frame_locals(frame: Any) -> dict[str, str]:
    """从栈帧提取局部变量快照（按值大小排序取前 _MAX_PROBE_VARS_PER_FRAME 个）。

    跳过模块名 / 构建时的临时符号（_ 前缀 / __builtins__ 等模块级注入键），
    避免无价值条目。函数级帧的 f_locals 只含真实局部变量（含单字符变量
    如 x/y/z——测试代码中最常见的断言变量），全部保留。
    2026-09-29 修复：历史实现额外过滤了单字符变量（"循环变量噪声"口径），
    但 x/y/z 正是断言失败时刻最关键的观测变量，过滤后快照恒空。
    """
    try:
        raw_locals: dict[str, Any] = dict(frame.f_locals)
    except Exception:
        return {}
    # 过滤：_ 前缀符号（含 __name__ / __builtins__ / __spec__ 等模块级注入键）
    # / 内置名（self / cls）
    filtered: dict[str, str] = {}
    for name, value in raw_locals.items():
        if name.startswith("_"):
            continue
        if name in ("self", "cls"):
            continue
        filtered[name] = _serialize_value(value)
    # 按值长度排序取前 N（短值优先，大对象后置截断）
    ordered = sorted(filtered.items(), key=lambda kv: len(kv[1]))
    return dict(ordered[:_MAX_PROBE_VARS_PER_FRAME])


def _exception_frames(exc: BaseException, limit: int, probe_file_path: str = "") -> list[dict[str, Any]]:
    """从异常的 __traceback__ 帧链提取失败时刻快照（最内层 → 外层，限 limit 帧）。

    2026-09-29 实现口径：异常栈本身就是"失败时刻"的精确帧栈（比逐事件
    trace 的 exception 事件更可靠——后者在函数体异常时不传播到被调帧）。
    返回结构与历史快照一致：[{"function", "file", "line", "locals"}]。

    过滤探针自身帧（runtime_probe.py 内部调用帧）：探针是纯观测层，
    自身帧的 locals（exc / captured / probe_file 等）对被测代码的修复
    分析无价值，反而污染 prompt 证据。

    行号口径：用 traceback 帧对象的 tb_lineno（异常传播时 CPython 记录的
    该帧精确行号），而非 frame.f_lineno——后者在帧已退出后停在
    函数体末尾/最后一条指令，不是异常抛出行（如 test_fails 内
    assert 在 line 5 失败，f_lineno 报 7）。

    帧遍历语义（2026-09-29 审查修复）：__traceback__ 链自抛出点起向上
    （被调方在前）。快照口径为"从最内层（抛出点）向外"，故 reversed(chain)。
    limit 预算仅消耗**非 probe_file 帧**（即外层调用帧，如
    capture_failure_snapshot / _probe_run 等）；probe_file 的帧（抛出点
    与 exec 顶层帧）全部保留——这是"失败时刻"的最关键观测帧。

    此前实现按 co_filename == abspath(__file__) 过滤探针自身帧，但
    __file__ 指向 runtime_probe.py，而 exec(compile(test_code, probe_file))
    产生的帧 co_filename 是 probe_file（路径与 __file__ 不同）→ 该过滤
    对 probe_file 帧永不命中，limit 被 3 帧中的 2 个 probe_file 帧消耗，
    外层观测帧仅 1 个。现改为 limit 预算仅消耗非 probe_file 帧，
    probe_file 帧全部保留（最内层抛出点 → 外层 exec 顶层帧），
    调用方仍以 _MAX_PROBE_FRAMES=3 为默认参数（对外契约不变）。
    """
    frames: list[dict[str, Any]] = []
    probe_path = probe_file_path
    # __traceback__ 链从最外层（抛出点）到最内层（被调帧），
    # 快照口径为"从最内层向外"（被调帧在前，抛出点在后），故反转
    chain: list[Any] = []
    tb = exc.__traceback__
    while tb is not None:
        chain.append(tb)
        tb = tb.tb_next
    kept = 0
    for tb in reversed(chain):
        frame = tb.tb_frame
        co_filename = frame.f_code.co_filename or ""
        # 非探针帧才消耗 limit 预算（内层探针帧保留但不计数）
        is_probe_frame = bool(probe_path and os.path.abspath(co_filename) == os.path.abspath(probe_path))
        if not is_probe_frame:
            if kept >= limit:
                break
            kept += 1
        frames.append(
            {
                "function": frame.f_code.co_name,
                "file": co_filename,
                "line": tb.tb_lineno,
                "locals": _capture_frame_locals(frame),
            }
        )
    return frames


def capture_failure_snapshot(
    test_code: str,
    target_module: str | None = None,
) -> dict[str, Any] | None:
    """一次性探针：执行 test_code，捕获异常抛出时刻的栈帧局部变量快照。

    实现口径（保守、纯观测）：
    - 仅当 RUNTIME_PROBE_ENABLE=true 时由调用方（_executor_node）调用；
    - 经子线程 exec 执行 test_code，**异常抛出时刻**用 exc.__traceback__ 帧链
      采集局部变量（非逐事件全量 trace——历史实现用 sys.settrace 的 exception
      事件采帧，但该事件在"函数体内抛异常"时不会传播到被调帧（CPython 逐事件
      追踪语义），实测 frames 恒空；__traceback__ 帧链直接给出完整异常栈，
      零 trace 开销且 locals 可靠）；探针自身用 try/except 包裹，
      任何异常静默降级返回 None；
    - 快照结构：{"success": bool, "error": str, "frames": [{"function", "file",
      "line", "locals": {name: value_str}}]}（从最内层向外最多 _MAX_PROBE_FRAMES 帧）。

    Args:
        test_code: 要执行的 pytest 测试代码字符串（已含 import 与 sys.path 注入）。
        target_module: 被测模块名（用于过滤快照仅保留目标模块相关帧，可选）。

    Returns:
        运行时快照字典；执行成功 / 探针失败 / 无异常帧时返回 None。
    """
    import tempfile
    import textwrap

    # 把 test_code 写入临时文件执行（与 executor_sandboxed 同口径），
    # 以便探针拿到真实帧（直接 exec 字符串代码的帧 locals 不可靠）
    tmp_dir = tempfile.mkdtemp(prefix="aitester_probe_")
    probe_file = os.path.join(tmp_dir, f"{target_module or 'probe'}_probe.py")
    try:
        with open(probe_file, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(test_code))
        # 在子线程里执行（隔离探针的 exec 命名空间副作用；主线程零影响）
        captured: dict[str, Any] = {"success": False, "error": "", "frames": []}

        def _probe_run() -> None:
            # 执行 test_code（import 风格：exec 在模块命名空间，让 test_* 函数被定义），
            # 随后逐个调用 test_* 函数（与 pytest -k 全量同口径，简单保守）。
            #
            # 2026-09-29 修复：放弃 sys.settrace 的 exception 事件采帧——
            # CPython 的逐事件追踪语义下，函数体内抛出的异常不会向被调帧
            # 传播 "exception" trace 事件（trace 回调仅在 call 边界接管，
            # 内部异常直接落到调用者的 except），实测该探针 frames 恒空
            # （P0 运行时探针实际从未生效）。改为在捕获异常时直接读
            # exc.__traceback__ 帧链（异常栈本身就是精确的失败时刻帧栈，
            # 零 trace 开销，且 f_locals 在该时刻完整可取）。
            def _capture_exception_frames(exc: BaseException) -> None:
                """异常 = 失败时刻观测点（正常观测路径）：
                从 exc.__traceback__ 链采集最内层 _MAX_PROBE_FRAMES 帧，
                按 target_module 过滤（不匹配时帧被丢弃 → 保守降级 None）。"""
                if target_module:
                    # 模块过滤口径（2026-09-29 修复）：probe 文件命名为
                    # "{target_module}_probe.py"（历史口径），被测代码帧的
                    # co_filename 即该 probe 文件路径。历史实现的过滤条件
                    # "{target_module}.py" 子串匹配与 probe 文件命名
                    # （"probe_module.py" 不是 "probe_module_probe.py" 的子串）
                    # 永不匹配 → 指定 target_module 时帧被全部丢弃（探针恒
                    # None）。改为直接匹配 probe 文件本身。
                    probe_file_path = os.path.abspath(probe_file)
                    # limit 预算按 probe_file 帧过滤（传入 probe_file_path 让
                    # _exception_frames 保留 probe 帧而不消耗外层 limit）
                    all_frames = _exception_frames(exc, _MAX_PROBE_FRAMES, probe_file_path)
                    frames = [f for f in all_frames if os.path.abspath(f["file"] or "") == probe_file_path]
                else:
                    # 无过滤：保留全部异常帧（最内层 → 外层）；limit 预算仅对
                    # 非 probe_file 帧消耗（probe_file 帧全部保留）
                    frames = _exception_frames(exc, _MAX_PROBE_FRAMES, os.path.abspath(probe_file))
                if frames:
                    captured["frames"].extend(frames)

            # 探针异常拦截（正常观测路径）：_probe_run 内部任何未处理异常
            # （含 exec 顶层异常 / 采帧自身故障）都必须在此兜底拦截，
            # 否则子线程带未处理异常退出 → 解释器打印 "Exception in thread"
            # 噪音（pytest 转 PytestUnhandledThreadExceptionWarning），
            # 且 captured["success"] 保持 False → 快照被误判为探针失败
            _module_ns: dict[str, Any] = {"__name__": "_aitester_probe_module"}
            try:
                # exec 顶层异常（import 失败 / 顶层语句失败）同样是失败时刻观测点
                exec(compile(test_code, probe_file, "exec"), _module_ns)
                # 逐个调用 test_* 函数（与 pytest -k 全量同口径，简单保守）
                for _name, _obj in list(_module_ns.items()):
                    if _name.startswith("test_") and callable(_obj):
                        try:
                            _obj()  # 探针不关心单用例结果
                        except BaseException as exc:
                            _capture_exception_frames(exc)
                        # 捕获后即结束该用例观测（与 pytest 逐用例隔离同口径）
            except BaseException as exc:
                # 顶层异常拦截（正常观测路径）：必须拦截，否则子线程带未处理
                # 异常退出 → 解释器打印 "Exception in thread" 噪音
                # （pytest 转 PytestUnhandledThreadExceptionWarning）
                _capture_exception_frames(exc)
            # 探针执行路径走通（无论异常是否发生）即置位 success
            captured["success"] = True

        # 子线程执行（隔离 exec 的命名空间副作用；join 等待完成）
        import threading

        t = threading.Thread(target=_probe_run, daemon=True)
        t.start()
        t.join(timeout=60)  # 60s 上限（探针不应超过单任务执行超时的 2 倍）
        if t.is_alive():
            # 探针超时（被测代码死循环）：静默降级
            return None

        if not captured["success"]:
            return None
        # 无异常帧（测试全过）→ 无需探针（探针是"失败时刻快照"，成功时 None）
        if not captured["frames"]:
            return None
        return captured

    except Exception as e:
        # 探针自身故障静默降级（纯观测层，不阻断主流程）
        logger.debug("运行时探针采集失败（降级为 None，不阻断修复）: %s", e)
        return None
    finally:
        import shutil

        with contextlib_suppress():
            shutil.rmtree(tmp_dir, ignore_errors=True)


def contextlib_suppress() -> Any:
    """contextlib.suppress(OSError) 的惰性导入包装（避免模块顶层 import 开销）。"""
    import contextlib

    return contextlib.suppress(OSError)


def build_probe_prompt_section(snapshot: dict[str, Any] | None) -> str:
    """把运行时探针快照渲染为 prompt 片段（注入 DebuggerAgent prompt 尾部）。

    快照为 None / 无有效帧时返回空串（调用方不追加，历史口径不变）。
    """
    if not snapshot or not snapshot.get("frames"):
        return ""
    lines = ["\n\n【运行时探针快照（RUNTIME_PROBE）】以下是测试失败时刻的局部变量实际值（从最内层帧向外）："]
    for i, frame in enumerate(snapshot["frames"], start=1):
        lines.append(f"  帧 {i}: `{frame.get('function')}` @ {frame.get('file')}:{frame.get('line')}")
        for var_name, var_value in (frame.get("locals") or {}).items():
            lines.append(f"    {var_name} = {var_value}")
    lines.append("请基于上述运行时证据（而非静态猜测）定位根因并生成修复补丁。")
    return "\n".join(lines)
