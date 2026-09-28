"""
结构化可观测性追踪层（P1：实验分析结构化数据）。

背景（4.1）：
    实验分析目前只能从日志文本与结果 JSON 反推"某个智能体在某个任务上
    做了什么决策、花了多少 token 与耗时"。日志是给人看的（会被脱敏、
    会被采样），无法支撑逐智能体的结构化回放。

    本模块以 JSONL（每行一个 JSON 对象）追加式记录每个工作流的
    "任务级"事件，供实验分析直接消费：
    - 每个智能体节点的输入摘要 / 输出摘要 / 决策结果；
    - 每任务的 token 消耗与墙钟耗时；
    - 工作流路由决策（debug / done / regenerate）。

设计约束：
    - 纯新增、默认关闭：仅当环境变量 AITESTER_TRACE_DIR 显式设置时
      才写盘（未设置 → 全部 no-op），对现有实验/CLI 流程零侵入、
      零性能税（开关判断 O(1)，关闭路径不产生 I/O）。
    - 线程安全：--parallel 模式多工作线程并发记录同一 JSONL 文件，
      单条记录 append + flush 在锁内完成（JSONL 追加原子性依赖
      POSIX write 对 O_APPEND 的单次调用保证）。
    - 敏感信息脱敏：所有写入文本统一过 mask_sensitive_info，
      与日志脱敏口径一致（4.1 与 1.1 同源）。
    - 写盘失败不阻断主流程：任何 I/O 异常仅记 warning（追踪是
      旁路观测层，观测失败不应改变被测系统行为）。

使用方式（benchmark 入口 / 工作流节点）：
    from src.observability.trace import TraceSession

    if TraceSession.enabled():
        session = TraceSession(task_id, trace_dir, config_flags)
        session.record_node("planner", output_summary=..., decision="plan_complete")
        session.record_task_end(passed=True)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, ClassVar

logger = logging.getLogger(__name__)

# ─── 追踪开关 ─────────────────────────────────────────────────────────────────
# 仅当 AITESTER_TRACE_DIR 显式设置为非空路径时启用（默认关闭）。
# 每次调用读取环境变量，便于测试用 monkeypatch.setenv 动态切换
# （与 base_agent._llm_cache_enabled 同机制，避免模块导入期固化）。
_TRACE_ENV_VAR = "AITESTER_TRACE_DIR"


def trace_dir() -> str | None:
    """返回追踪输出目录；未启用时返回 None。

    Returns:
        环境变量 AITESTER_TRACE_DIR 的裁剪后值；未设置/空串时为 None。
    """
    raw = os.environ.get(_TRACE_ENV_VAR, "")
    return raw.strip() or None


def trace_enabled() -> bool:
    """是否启用结构化追踪（AITESTER_TRACE_DIR 非空）。"""
    return trace_dir() is not None


# ─── 输入/输出摘要截断 ────────────────────────────────────────────────────────
# 单字段摘要最大字符数：JSONL 单行若携带完整 prompt/代码（数千~数万字符），
# 回放文件会迅速膨胀且 90% 信息对"决策分析"无价值。截断保留头尾各半，
# 与 base_agent._CODE_MAX_CHARS 的取舍口径一致（来源：实验分析实用经验）。
_FIELD_MAX_CHARS = 2000


def _summarize(value: Any) -> Any:
    """生成单字段的可 JSON 序列化摘要（长文本截断、嵌套结构原样保留）。

    Args:
        value: 任意值。

    Returns:
        str（> 阈值时截断为 "头…尾"）或原值（非 str / 短文本 / 容器）。
    """
    if isinstance(value, str) and len(value) > _FIELD_MAX_CHARS:
        head_len = _FIELD_MAX_CHARS // 2
        head = value[:head_len]
        tail = value[-(_FIELD_MAX_CHARS - head_len) :]
        return f"{head}…[truncated {len(value) - _FIELD_MAX_CHARS} chars]…{tail}"
    return value


class TraceSession:
    """单任务的结构化追踪会话（JSONL 追加式记录）。

    一个工作流任务对应一个 TraceSession：start 时写 task_start 事件
    并打点墙钟起点，每个节点结束时 record_node，任务收尾 record_task_end
    （携带 token_usage 快照与耗时）。

    线程模型：
        - 同进程内多个 TraceSession 实例并发写同一文件时安全
          （_file_locks 按路径全局互斥）；
        - 同一实例的并发调用同样安全（记录追加在锁内）。

    属性:
        task_id: 任务标识（写入每条记录的 "task" 字段）。
        trace_dir: 输出目录（文件名为 <task_id>.trace.jsonl）。
        file_path: 实际 JSONL 文件完整路径。
    """

    # 按文件路径全局互斥的锁注册表：同一 JSONL 文件的追加串行化
    # （threading.Lock 本身轻量，文件数 = 任务数，可忽略）
    _file_locks: ClassVar[dict[str, threading.Lock]] = {}
    _file_locks_guard = threading.Lock()

    @classmethod
    def _lock_for(cls, path: str) -> threading.Lock:
        with cls._file_locks_guard:
            lock = cls._file_locks.get(path)
            if lock is None:
                lock = threading.Lock()
                cls._file_locks[path] = lock
            return lock

    @staticmethod
    def enabled() -> bool:
        """追踪是否启用（AITESTER_TRACE_DIR 非空时启用）。"""
        return trace_enabled()

    def __init__(
        self, task_id: str, trace_directory: str | None = None, task_meta: dict[str, Any] | None = None
    ) -> None:
        """初始化追踪会话（未启用时所有记录方法 no-op）。

        Args:
            task_id: 任务标识（JSONL 文件名与记录字段均用它）。
            trace_directory: 输出目录，None 时读环境变量；
                目录不存在时自动创建，创建失败降级为 no-op（不阻断主流程）。
            task_meta: 任务级静态元数据（如 target_file、func、dataset），
                随 task_start 事件落盘。
        """
        directory = trace_directory if trace_directory is not None else trace_dir()
        self.task_id = task_id
        self.records: list[dict[str, Any]] = []  # 内存视角：供失败诊断快照（不落盘）
        self._enabled = directory is not None
        self._file_path: str | None = None
        self._started_at: float | None = None
        if self._enabled and directory is not None:
            os.makedirs(directory, exist_ok=True)
            safe_task = "".join(c if c.isalnum() or c in "-_." else "_" for c in task_id) or "task"
            self._file_path = os.path.join(directory, f"{safe_task}.trace.jsonl")
            self._started_at = time.time()
            self._append(
                {
                    "event": "task_start",
                    "task": task_id,
                    "ts": self._started_at,
                    "meta": {k: _summarize(v) for k, v in (task_meta or {}).items()},
                }
            )

    def _append(self, record: dict[str, Any]) -> None:
        """向 JSONL 追加一条记录（锁内追加，失败仅 warning 不抛出）。

        同时把记录存进内存视角 self.records（供失败诊断快照消费；
        纯内存累积，不产生 I/O；未启用文件追踪时 _append 仍累积 records，
        使"最小化节点快照"在常规使用下也可复盘）。
        """
        self.records.append(record)
        if not self._enabled or self._file_path is None:
            return
        # 敏感信息脱敏（与日志口径一致）：追踪文件同样不得落凭证。
        # 摘要口径收敛（0.10）：task_start 的 meta 已在构造时逐值 _summarize，
        # record_node 的 output 与 task_end 的 extra 亦在入口处摘要——
        # 此处不再二次摘要 meta（旧版浅拷贝 + 重建 meta dict 是冗余深处理），
        # 记录对象本身只读序列化，无副作用。
        # 异常路径拆分（此前 except 同时吞 json.dumps 失败与脱敏 import 失败，
        # 记录静默丢弃且无任何告警——观测层失败应可察觉）：序列化失败即丢弃
        # 本条（记 warning），脱敏 import 失败则降级原样写入（不阻断主流程）。
        try:
            line = json.dumps(record, ensure_ascii=False, default=str)
        except Exception as e:
            # 自定义对象 __str__ 抛异常等场景：记录无法序列化，记 warning 后放弃
            logger.warning("追踪记录序列化失败（丢弃本条）: %s", e)
            return
        try:
            from src.utils.logging_utils import mask_sensitive_info

            line = mask_sensitive_info(line)
        except Exception:
            # 脱敏不可用（理论上不会：纯标准库模块）时原样写入，
            # 不阻断观测层主流程（与 logging_utils 三级降级末档同口径）
            pass
        lock = self._lock_for(self._file_path)
        try:
            with lock, open(self._file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as e:
            # 追踪是旁路观测层：写盘失败不改变被测系统行为
            logger.warning("追踪记录写盘失败（忽略）: %s", e)

    def record_node(
        self,
        node: str,
        output_summary: Any = None,
        decision: str | None = None,
        duration_ms: float | None = None,
        iteration: int | None = None,
        input_summary: Any = None,
        token_usage: dict[str, Any] | None = None,
        decision_reason: str | None = None,
        strategy_selected: str | None = None,
        budget_remaining: int | float | None = None,
    ) -> None:
        """记录一次智能体节点的输入输出与决策结果（4.1 核心事件）。

        P1 执行感知可观测性升级：新增 input_summary / token_usage /
        decision_reason / strategy_selected / budget_remaining 五个
        结构化决策路径字段，供失败分析与策略银行挖掘消费。所有新字段
        均为可选（缺省不写入 record），历史调用方零变化；仅当显式传入
        时才出现在 JSONL 记录中（"按需扩展"口径，与 ADR-0003 一致）。

        Args:
            node: 节点名（planner / generator / executor / debugger /
                patch_applier / _should_debug 等）。
            output_summary: 输出摘要（长文本自动截断为头尾各半）。
            decision: 该节点的路由/决策标签（如 "debug" / "done" /
                "regenerate" / "test_passed"），供决策路径分析。
            duration_ms: 节点墙钟耗时（毫秒，可选）。
            iteration: 当前修复迭代轮次（可选）。
            input_summary: 输入摘要（本节点消费的关键 state 字段，可选）。
            token_usage: 本节点 LLM 调用的 token 消耗快照（可选，
                由调用方经 token_usage.get_usage().as_dict() 提取增量）。
            decision_reason: 决策原因的自然语言说明（可选，如
                "error_category=assertion, iteration>=max → done"）。
            strategy_selected: 本节点选中的修复/生成策略标签（可选，
                如 "multi_candidate" / "single_patch" / "regenerate"）。
            budget_remaining: 本节点执行前的 LLM 预算余量（可选，
                来自 cost_budget.get_budget_stats()["remaining_tokens"]；
                预算未启用时调用方传 None，不写入 record）。
        """
        record: dict[str, Any] = {
            "event": "node",
            "task": self.task_id,
            "node": node,
            "ts": time.time(),
        }
        if output_summary is not None:
            record["output"] = _summarize(output_summary)
        if decision is not None:
            record["decision"] = decision
        if duration_ms is not None:
            record["duration_ms"] = round(duration_ms, 2)
        if iteration is not None:
            record["iteration"] = iteration
        # P1 执行感知可观测性升级：结构化决策路径字段（按需扩展，缺省不写入）
        if input_summary is not None:
            record["input"] = _summarize(input_summary)
        if token_usage is not None:
            record["token_usage"] = token_usage
        if decision_reason is not None:
            record["decision_reason"] = decision_reason
        if strategy_selected is not None:
            record["strategy_selected"] = strategy_selected
        if budget_remaining is not None:
            record["budget_remaining"] = budget_remaining
        self._append(record)

    def record_task_end(
        self,
        passed: bool | None,
        token_usage: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """记录任务收尾事件：结果、token 消耗与总耗时（4.1 效率指标）。

        Args:
            passed: 任务最终是否通过测试（None 表示任务中途崩溃）。
            token_usage: token_usage.get_usage().as_dict() 快照，
                记录逐任务的输入/输出 token、LLM 调用次数与分模型消耗。
            extra: 附加字段（如 rag_stats、coverage 汇总）。
        """
        record: dict[str, Any] = {
            "event": "task_end",
            "task": self.task_id,
            "ts": time.time(),
            "passed": passed,
        }
        if self._started_at is not None:
            record["duration_s"] = round(time.time() - self._started_at, 2)
        if token_usage:
            record["token_usage"] = token_usage
        if extra:
            for key, value in extra.items():
                record[key] = _summarize(value)
        self._append(record)


def reset_trace_file_locks() -> None:
    """清空文件锁注册表（仅供测试隔离，避免跨用例锁泄漏）。"""
    with TraceSession._file_locks_guard:
        TraceSession._file_locks.clear()


# ─── 内存快照缓冲（默认启用、不落盘）──────────────────────────────────────
# 结构化追踪"全 no-op 默认关闭"限制了常规使用下非预期失败的复盘能力：
# 未设 AITESTER_TRACE_DIR 时用户缺少节点决策 / token / 耗时数据。
# 本缓冲在**追踪未启用**时，进程级保留最近 N 次任务的关键节点快照
# （纯内存、不落盘、零 I/O），失败时经 dump_recent_to 写成临时 JSONL 供诊断。
# 设计约束：默认行为不变（不落盘、不影响性能）；--dump-trace-on-failure
# 仅在任务失败时把内存快照写入临时文件（诊断出口）。

_MEMORY_BUFFER_CAPACITY = 64  # 进程级保留的最近任务快照数（环形覆盖）
_memory_ring: list[dict[str, Any]] = []
_memory_ring_lock = threading.Lock()


def _memory_buffer_enabled() -> bool:
    """内存快照缓冲开关（TRACE_MEMORY_BUFFER_ENABLE，默认 true 保守启用）。

    未设 AITESTER_TRACE_DIR 时缓冲生效；已启用文件追踪时缓冲仍运行
    （快照口径独立于落盘追踪，供失败诊断复用）。设 false 完全关闭
    缓冲（零内存开销，回退历史"全 no-op"口径）。
    """
    return os.getenv("TRACE_MEMORY_BUFFER_ENABLE", "true").strip().lower() in ("true", "1", "on")


def memory_buffer_snapshot(task_id: str, records: list[dict[str, Any]]) -> None:
    """把一次任务的追踪记录快照入进程级环形缓冲（不落盘，默认启用）。

    Args:
        task_id: 任务标识（快照字典的 "task" 字段）。
        records: 该任务的追踪记录列表（task_start / node / task_end 事件 dict，
            通常为 TraceSession 已序列化的记录；空列表表示无记录可快照）。
    """
    if not _memory_buffer_enabled():
        return
    with _memory_ring_lock:
        snapshot = {"task": task_id, "ts": time.time(), "records": list(records)}
        _memory_ring.append(snapshot)
        overflow = len(_memory_ring) - _MEMORY_BUFFER_CAPACITY
        if overflow > 0:
            del _memory_ring[:overflow]


def reset_memory_buffer() -> None:
    """清空进程级内存快照缓冲（仅供测试隔离）。"""
    with _memory_ring_lock:
        _memory_ring.clear()


def dump_recent_to(target_dir: str, limit: int | None = None) -> str | None:
    """把进程级内存快照写入目标目录（失败诊断出口，需显式调用才落盘）。

    非默认行为：仅当 CLI --dump-trace-on-failure 在任务失败时调用，
    快照写 <target_dir>/<ts>_failed_trace.jsonl。

    Args:
        target_dir: 输出目录（自动创建，创建失败返回 None）。
        limit: 写入的最近任务快照数（None = 全部保留，默认全部）。

    Returns:
        写盘的 JSONL 文件完整路径；无快照可写或写盘失败时返回 None。
    """
    with _memory_ring_lock:
        if not _memory_ring:
            return None
        recent = list(_memory_ring)
    if limit is not None:
        recent = recent[-limit:]
    os.makedirs(target_dir, exist_ok=True)
    import time as _time

    filename = f"{int(_time.time())}_failed_trace.jsonl"
    path = os.path.join(target_dir, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            for snap in recent:
                for record in snap.get("records", []):
                    f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                # 快照级收尾标记（非 TraceSession 事件，供诊断区分任务边界）
                f.write(
                    json.dumps(
                        {"event": "snapshot_task", "task": snap.get("task"), "ts": snap.get("ts")},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    except OSError as e:
        logger.warning("内存快照写盘失败（忽略）: %s", e)
        return None
    return path
