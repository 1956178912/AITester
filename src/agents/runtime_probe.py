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
    - 开关开启后，在 pytest 执行失败时，经**子进程**一次性探针采集
      "失败帧"的运行时快照（变量名 → 值，限深度与大小）：
      在独立 python 子进程中执行 test_code，异常抛出时刻读
      exc.__traceback__ 帧链（异常栈即精确的失败时刻帧栈，零 trace 开销），
      而非历史实现的 sys.settrace exception 事件（CPython 语义下函数体
      异常不向被调帧传播 exception 事件，实测 frames 恒空——2026-09-29
      修复）。2026-09-29 审查修复（S1 安全）：历史实现在主进程内子线程
      exec(compile(test_code)) 执行 LLM 生成代码——无资源/权限限制且
      join(timeout) 超时后线程不可 kill（死循环/挂起代码存活至进程
      退出），与 Docker/venv 执行链路"隔离+脱敏"的设计目标不一致。
      现改为 subprocess.run + credential_scrub.scrub_os_environ（与
      executor_runtime 同口径）：超时真正可 kill、凭证不外泄、写/网络
      副作用被进程退出回收；
    - 探针是**纯观测层**：快照采集失败（帧不可取 / 变量不可序列化 /
      子进程不可用）时静默降级（返回 None），不阻断 pytest 执行主流程；
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

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from typing import Any

from src.utils.credential_scrub import scrub_os_environ

logger = logging.getLogger(__name__)

# 探针上限常量（避免 prompt 爆炸）
_MAX_PROBE_FRAMES = 3  # 最多捕获的栈帧数（从最内层向外）
_MAX_PROBE_VALUE_CHARS = 200  # 单个变量值序列化后的最大字符数（超出截断）
_MAX_PROBE_VARS_PER_FRAME = 20  # 每帧最多捕获的局部变量数（按值大小排序取前 N）

# 子进程探针执行上限（秒）：被测代码死循环时超时 kill（替代历史子线程
# join(60) 不可 kill 线程口径；20s 对"失败时刻快照"足够——正常探针
# 毫秒级完成，20s 内未完成即判定挂起，静默降级）
_PROBE_SUBPROCESS_TIMEOUT = 20


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


# 子进程 runner 源码（模板）：在独立进程中 exec 被测 test_code 文件并
# 逐用例调用 test_*，异常抛出时刻读 exc.__traceback__ 帧链采集局部变量，
# 结果写 JSON 输出目录。占位符 @@MAX_FRAMES@@ / @@MAX_VARS@@ /
# @@MAX_CHARS@@ 经 _probe_runner_source 的 replace 注入（模板含 Python
# 字面花括号，不用 str.format 以免冲突）。
_PROBE_RUNNER_TEMPLATE = """\
import json
import os
import sys

_probe_file, _out_dir = sys.argv[1], sys.argv[2]
_MAX_FRAMES, _MAX_VARS, _MAX_CHARS = @@MAX_FRAMES@@, @@MAX_VARS@@, @@MAX_CHARS@@


def _ser(v):
    try:
        t = repr(v)
    except Exception:
        t = f"<unrepr-able: {type(v).__name__}>"
    return t if len(t) <= _MAX_CHARS else t[:_MAX_CHARS] + "…"


def _loc(fr):
    try:
        raw = dict(fr)
    except Exception:
        raw = {}
    out = {}
    for n, v in raw.items():
        if n.startswith("_") or n in ("self", "cls"):
            continue
        out[n] = _ser(v)
    o = sorted(out.items(), key=lambda kv: len(kv[1]))
    return dict(o[:_MAX_VARS])


def _cap(exc):
    # 取最内层异常帧（抛出点，即异常发生处的函数体/顶层帧）——与历史
    # _exception_frames(exc, ...) 的 reversed(chain) 口径一致（历史实现
    # 保留 probe_file 帧 = 抛出点 + exec 顶层帧；runner 内 exec 的帧
    # co_filename 同为 probe 文件，由父进程 target_module 过滤统一口径）。
    tb = exc.__traceback__
    inner = None
    while tb is not None:
        inner = tb
        tb = tb.tb_next
    if inner is None:
        return None
    f = inner.tb_frame
    try:
        fn = f.f_code.co_name
        fl = f.f_code.co_filename or ""
    except Exception:
        fn, fl = "?", _probe_file
    try:
        loc = _loc(f.f_locals)
    except Exception:
        loc = {}
    return {"function": fn, "file": fl, "line": inner.tb_lineno, "locals": loc}


def main():
    frames = []
    # 探针语义（与历史口径一致）：test_code 含 test_* 用例且至少一个
    # 抛出异常 → 捕获抛出帧；顶层异常（exec 阶段：assert/import 失败）
    # 同样是"失败时刻"观测点（历史实现的顶层 except 也记帧）→ 捕获最内层
    # 帧；全部通过且无顶层异常 → 空快照（父进程判定 None）。
    _toplevel = False
    try:
        with open(_probe_file, encoding="utf-8") as _fh:
            _src = _fh.read()
        # 被测代码在独立 ns 中 exec（与历史"主进程子线程 exec"语义一致：
        # test_* 函数在该 ns 中定义，函数帧 co_filename = 探针文件，
        # locals 归属精确）
        _ns = {"__name__": "_aitester_probe_module"}
        exec(compile(_src, _probe_file, "exec"), _ns)
    except BaseException as _top:
        # exec 阶段顶层异常（顶层 assert / import 失败）：记最内层抛出帧
        _toplevel = True
        _fr = _cap(_top)
        if _fr:
            frames.append(_fr)
    if not _toplevel:
        # exec 成功（含顶层 test_* 调用未触发的场景）：逐个调用 test_*，
        # 单用例异常 = 失败时刻观测点
        for _n, _o in list(_ns.items()):
            if _n.startswith("test_") and callable(_o):
                try:
                    _o()
                except BaseException as _e:
                    _fr = _cap(_e)
                    if _fr:
                        frames.append(_fr)
    # 截帧：保留最内层 _MAX_FRAMES 帧（frames 按 append 序 = 最内层在前，
    # 与历史 _exception_frames 的 reversed 语义对齐）
    frames = frames[:_MAX_FRAMES]
    os.makedirs(_out_dir, exist_ok=True)
    with open(os.path.join(_out_dir, "frames.json"), "w", encoding="utf-8") as _fh:
        json.dump({"frames": frames}, _fh)


main()
"""


def _probe_runner_source() -> str:
    """渲染子进程 runner 源码（常量注入上限参数，无动态内容）。

    用 replace 而非 str.format（模板内 JSON/Python 字面花括号与 format
    冲突）：占位符 @@MAX_FRAMES@@ / @@MAX_VARS@@ / @@MAX_CHARS@@。
    """
    return (
        _PROBE_RUNNER_TEMPLATE.replace("@@MAX_FRAMES@@", str(_MAX_PROBE_FRAMES))
        .replace("@@MAX_VARS@@", str(_MAX_PROBE_VARS_PER_FRAME))
        .replace("@@MAX_CHARS@@", str(_MAX_PROBE_VALUE_CHARS))
    )


def capture_failure_snapshot(
    test_code: str,
    target_module: str | None = None,
) -> dict[str, Any] | None:
    """一次性探针：在**子进程**中执行 test_code，捕获异常抛出时刻的栈帧局部变量快照。

    实现口径（保守、纯观测）：
    - 仅当 RUNTIME_PROBE_ENABLE=true 时由调用方（_executor_node）调用；
    - 经独立 python 子进程（subprocess.run + credential_scrub.scrub_os_environ
      凭证脱敏 + cwd 沙箱目录）执行 test_code，**异常抛出时刻**读
      exc.__traceback__ 帧链采集局部变量（异常栈即精确的失败时刻帧栈，
      零 trace 开销，且 locals 可靠）；帧快照经 JSON 文件从子进程传回
      （子进程 stdout 可能含被测代码输出，不可靠，故走文件通道）；
      探针自身用 try/except 包裹，任何异常静默降级返回 None；
    - 子进程执行 + 20s 上限（_PROBE_SUBPROCESS_TIMEOUT）：被测代码死循环
      时超时真正 kill（threading.join 不可 kill 线程的历史口径已由
      subprocess 超时 + 进程回收替代）；超时/环境故障静默降级 None。

    Args:
        test_code: 要执行的 pytest 测试代码字符串（已含 import 与 sys.path 注入）。
        target_module: 被测模块名（用于过滤快照仅保留目标模块相关帧，可选）。

    Returns:
        运行时快照字典；执行成功 / 探针失败 / 无异常帧时返回 None。
    """
    # 把 test_code 写入临时文件执行（与 executor_sandboxed 同口径），
    # 以便探针拿到真实帧（直接 exec 字符串代码的帧 locals 不可靠）
    tmp_dir = tempfile.mkdtemp(prefix="aitester_probe_")
    probe_file = os.path.join(tmp_dir, f"{target_module or 'probe'}_probe.py")
    try:
        with open(probe_file, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(test_code))

        # 子进程 runner（经 sys.executable 独立进程执行，隔离 LLM 代码
        # 副作用；S1 安全：替代历史"主进程子线程 exec"口径——子线程
        # join(60) 超时不可 kill、LLM 代码可在主进程写任意文件/发网络，
        # 子进程 + 脱敏环境 + 超时 kill 封堵该执行向量）
        runner_file = os.path.join(tmp_dir, "_probe_runner.py")
        with open(runner_file, "w", encoding="utf-8") as f:
            f.write(_probe_runner_source())

        # 输出帧目录（子进程写 frames.json；父进程读；与 runner 同处沙箱目录）
        frames_dir = os.path.join(tmp_dir, "_probe_out")

        # 子进程执行：凭证脱敏（credential_scrub 动态模式含 LLM_N 全家族）
        # + cwd 指向沙箱目录（test_code 的 import 相对路径在此解析）
        # + 20s 上限（超时真正 kill，替代历史 thread.join 不可 kill 口径）
        # 脱敏环境含 PYTHONPATH（被测代码的 import 解析依赖），子进程据此
        # 继承路径；LLM 凭证类变量（LLM_N_API_KEY 等全家族）已剔除。
        env = scrub_os_environ()
        try:
            proc = subprocess.run(
                [sys.executable, runner_file, probe_file, frames_dir],
                capture_output=True,
                text=True,
                timeout=_PROBE_SUBPROCESS_TIMEOUT,
                cwd=tmp_dir,
                env=env,
            )
        except subprocess.TimeoutExpired:
            # 被测代码死循环：子进程被 kill（与 venv/docker 执行链路同口径），
            # 静默降级——探针是纯观测层，不阻断主流程
            logger.debug(
                "运行时探针子进程超时（>%ds，被测代码可能死循环），降级为 None",
                _PROBE_SUBPROCESS_TIMEOUT,
            )
            return None
        except OSError as e:
            logger.debug("运行时探针子进程启动失败（降级为 None，不阻断修复）: %s", e)
            return None

        # 子进程退出码非 0（runner 自身故障，非被测代码异常）：降级 None。
        # runner 对被测代码异常做兜底拦截（main 顶层 except），正常观测
        # 路径退出码恒 0。
        if proc.returncode != 0:
            logger.debug(
                "运行时探针子进程异常退出（rc=%s），降级为 None",
                proc.returncode,
            )
            return None

        # 读回帧快照（子进程写 frames.json；文件缺失/损坏时降级）
        frames: list[dict[str, Any]] = []
        try:
            with open(os.path.join(frames_dir, "frames.json"), encoding="utf-8") as fh:
                frames = json.load(fh).get("frames") or []
        except (OSError, json.JSONDecodeError, TypeError):
            frames = []

        # target_module 过滤（历史口径：探针文件即被测代码载体，按 probe
        # 文件绝对路径匹配帧；与子线程实现保持一致）
        if target_module:
            probe_abs = os.path.abspath(probe_file)
            frames = [fr for fr in frames if os.path.abspath(fr.get("file") or "") == probe_abs]

        if not frames:
            # 无异常帧（测试全过 / 探针降级）→ 返回 None
            return None
        return {"success": True, "error": "", "frames": frames}

    except Exception as e:
        # 探针自身故障静默降级（纯观测层，不阻断主流程）
        logger.debug("运行时探针采集失败（降级为 None，不阻断修复）: %s", e)
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)  # ignore_errors=True 已吸收 OSError


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
