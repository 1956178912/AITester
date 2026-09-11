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
from typing import Any

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
    _file_locks: dict[str, threading.Lock] = {}
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
        self._enabled = bool(directory)
        self._file_path: str | None = None
        self._started_at: float | None = None
        if self._enabled:
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
        """向 JSONL 追加一条记录（锁内追加，失败仅 warning 不抛出）。"""
        if not self._enabled or self._file_path is None:
            return
        # 敏感信息脱敏（与日志口径一致）：追踪文件同样不得落凭证
        try:
            from src.utils.logging_utils import mask_sensitive_info

            line = mask_sensitive_info(json.dumps(record, ensure_ascii=False, default=str))
        except Exception:
            line = json.dumps(record, ensure_ascii=False, default=str)
        lock = self._lock_for(self._file_path)
        try:
            with lock:
                with open(self._file_path, "a", encoding="utf-8") as f:
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
    ) -> None:
        """记录一次智能体节点的输入输出与决策结果（4.1 核心事件）。

        Args:
            node: 节点名（planner / generator / executor / debugger /
                patch_applier / _should_debug 等）。
            output_summary: 输出摘要（长文本自动截断为头尾各半）。
            decision: 该节点的路由/决策标签（如 "debug" / "done" /
                "regenerate" / "test_passed"），供决策路径分析。
            duration_ms: 节点墙钟耗时（毫秒，可选）。
            iteration: 当前修复迭代轮次（可选）。
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
