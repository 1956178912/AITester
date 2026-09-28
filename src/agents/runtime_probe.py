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
    - 开关开启后，在 pytest 执行失败时，经 `sys.settrace` 注入的
      **一次性探针**（非全量 trace，仅捕获异常抛出时刻的局部变量）
      采集"失败帧"的运行时快照（变量名 → 值，限深度与大小），
      经 `build_probe_prompt_section` 渲染为 prompt 片段注入 DebuggerAgent；
    - 探针是**纯观测层**：快照采集失败（trace 异常 / 变量不可序列化）
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

    跳过模块名 / 构建时的临时符号（_ 前缀 / 单字符循环变量），避免无价值条目。
    """
    try:
        raw_locals: dict[str, Any] = dict(frame.f_locals)
    except Exception:
        return {}
    # 过滤：_ 前缀符号 / 单字符变量（循环变量噪声）/ 内置名
    filtered: dict[str, str] = {}
    for name, value in raw_locals.items():
        if name.startswith("_") or len(name) == 1:
            continue
        if name in ("self", "cls"):
            continue
        filtered[name] = _serialize_value(value)
    # 按值长度排序取前 N（短值优先，大对象后置截断）
    ordered = sorted(filtered.items(), key=lambda kv: len(kv[1]))
    return dict(ordered[:_MAX_PROBE_VARS_PER_FRAME])


def capture_failure_snapshot(
    test_code: str,
    target_module: str | None = None,
) -> dict[str, Any] | None:
    """一次性探针：执行 test_code，捕获异常抛出时刻的栈帧局部变量快照。

    实现口径（保守、纯观测）：
    - 仅当 RUNTIME_PROBE_ENABLE=true 时由调用方（_executor_node）调用；
    - 经 sys.settrace 注入探针，**只在异常抛出帧**采集 locals（非全量 trace，
      避免性能税）；探针本身用 try/except 包裹，任何异常静默降级返回 None；
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
        # 在子线程里执行（避免污染主线程的 sys.settrace 状态；
        # 探针在子线程内 settrace → 执行 → unsetrace，主线程零影响）
        captured: dict[str, Any] = {"success": False, "error": "", "frames": []}

        def _probe_run() -> None:
            import sys as _sys

            probe_active = {"flag": False}

            def _trace_func(frame, event, arg):
                # 2026-09-29 修复：sys.settrace 回调返回 None（系统默认 trace 回调，
                # 逐事件追踪）而非 frame 对象——此前 `return frame` 把 frame 当作
                # 局部 trace 回调注入，与 exec / 内置调用路径冲突
                # （TypeError: 'frame' object is not callable）。保守口径：返回 None
                # 让解释器保留逐事件追踪（性能税可接受：探针仅在 RUNTIME_PROBE_ENABLE
                # =true 时启用，且执行的是被测测试代码而非 LLM 调用热路径）。
                if (
                    event == "exception"
                    and probe_active["flag"]
                    and len(captured["frames"]) < _MAX_PROBE_FRAMES
                    and (not target_module or f"{target_module}.py" in (frame.f_code.co_filename or ""))
                ):
                    # 异常帧：采集局部变量快照。
                    # 过滤：仅保留目标模块相关帧（target_module 为文件名子串匹配）
                    # 注意 frame.f_code.co_filename 是绝对路径，target_module 是
                    # 模块名；保守：仅当 filename 含 module 名时保留
                    captured["frames"].append(
                        {
                            "function": frame.f_code.co_name,
                            "file": frame.f_code.co_filename,
                            "line": frame.f_lineno,
                            "locals": _capture_frame_locals(frame),
                        }
                    )

            probe_active["flag"] = True
            _sys.settrace(_trace_func)
            try:
                # 直接执行测试模块（import 而非 exec，让 pytest 风格函数被定义）。
                # 2026-09-29 修复：在 settrace 上下文中不能直接调用
                # importlib.util.spec_from_file_location（其内部调用了
                # 会触发 trace 回调的 C 函数，且 _trace_func 返回 frame 对象
                # 与 importlib 内部逻辑冲突 → TypeError: 'frame' object is
                # not callable）。改为用 exec() 在模块命名空间执行 test_code，
                # 异常帧的 locals 仍可被 _capture_frame_locals 正确采集
                # （exec 的帧 f_locals 就是传入的 globals dict 本身）。
                _module_ns: dict[str, Any] = {"__name__": "_aitester_probe_module"}
                exec(compile(test_code, probe_file, "exec"), _module_ns)
                # 执行所有 test_* 函数（与 pytest -k 全量同口径，简单保守）
                for _name, _obj in list(_module_ns.items()):
                    if _name.startswith("test_") and callable(_obj):
                        with contextlib_suppress():
                            _obj()  # 探针仅采集异常帧，不关心单用例结果
            finally:
                _sys.settrace(None)
                probe_active["flag"] = False
            captured["success"] = True

        # 子线程执行（避免 settrace 污染主线程；join 等待完成）
        import threading

        t = threading.Thread(target=_probe_run, daemon=True)
        t.start()
        t.join(timeout=60)  # 60s 上限（探针不应超过单任务执行超时的 2 倍）

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
