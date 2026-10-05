"""原子文件写入工具（U4，2026-10-05 系统性审查落地）。

背景（2026-10-05 独立系统性审查）：
    仓内多处"读-改-写"型落盘此前直接 open(..., "w") 写入——进程崩溃 /
    磁盘满 / 并发交错时会产生**半写文件**（strategy_bank 的策略库 JSON、
    config_manager 的 .env.local 均为实际案例）。半写 JSON 会让下一次
    json.load 直接抛 JSONDecodeError，半写 .env 会让配置静默错乱。

本模块提供统一原子写口径（与 LLM 缓存 / patch_rollback.save_snapshot_json
的 tmp + os.replace 模式同源，收敛为单一实现）：
    - 先写同目录临时文件（同文件系统保证 os.replace 原子性）；
    - os.replace 原子替换目标（POSIX rename 语义：读者要么看到旧完整
      内容、要么看到新完整内容，不存在中间态）；
    - 失败时清理临时文件（不残留 .tmp 垃圾）；
    - 默认收敛权限到 0600（写的是配置/统计类文件，可能含敏感端点信息；
      与 llm_client 缓存文件 0600 口径一致）。

线程安全口径：单次 atomic_write_* 调用内原子；多线程对**同一目标路径**
的读-改-写仍需调用方持锁串行化（本模块不解决 lost-update，只解决
"半写文件"）。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any

logger = logging.getLogger(__name__)


def atomic_write_text(path: str, content: str, *, mode: int | None = 0o600) -> None:
    """原子写文本文件（临时文件 + os.replace，失败清理临时文件）。

    Args:
        path: 目标文件路径（父目录必须已存在，由调用方负责 makedirs）。
        content: 要写入的文本内容。
        mode: 写入后收敛的权限（None = 不改权限；默认 0600，对齐
            llm_client 缓存文件口径）。

    Raises:
        OSError: 临时文件创建 / 替换失败时向上抛（由调用方决定降级口径）。
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd = -1
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".aitester_tmp_", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = -1  # fdopen 接管后由 with 负责关闭
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
        tmp_path = None  # 替换成功，无需清理
    finally:
        # fd 未被 fdopen 接管（mkstemp 后异常）→ 手动关闭
        if fd >= 0:
            os.close(fd)
        # 任一步失败 → 清理临时文件（目标文件保持旧完整内容）
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.debug("U4 atomic_write 临时文件清理失败（忽略）: %s", tmp_path)


def atomic_write_json(path: str, obj: Any, *, indent: int = 2, mode: int | None = 0o600) -> None:
    """原子写 JSON 文件（ensure_ascii=False + atomic_write_text）。

    Args:
        path: 目标文件路径。
        obj: 可 JSON 序列化对象。
        indent: json.dump 缩进（默认 2，与仓内既有落盘风格一致）。
        mode: 同 atomic_write_text。
    """
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=indent), mode=mode)


__all__ = ["atomic_write_json", "atomic_write_text"]
