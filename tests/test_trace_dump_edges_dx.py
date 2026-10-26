"""DX 轮锁：失败诊断导出的参数边界与并发落点。

缺陷族（先红后绿）：
- ``limit=0`` 走 ``recent[-0:]`` 静默导出**全部**快照，负数走 ``recent[2:]``
  反向切片——参数语义与 docstring「最近 N 个」不一致，且无任何披露；
- 文件名只取整秒时间戳：同一秒内的多次 / 并发导出共用同一路径，后写覆盖
  先写（并发压测 4 次调用只剩 1 个文件），诊断证据静默丢失。
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from src.observability.trace import (
    _memory_buffer_enabled,
    dump_recent_to,
    dump_recent_to_with_reason,
    memory_buffer_snapshot,
    reset_memory_buffer,
)

TS = 1700000000


@pytest.fixture(autouse=True)
def _isolated_buffer():
    reset_memory_buffer()
    assert _memory_buffer_enabled(), "本组锁要求内存缓冲启用（默认 true）"
    yield
    reset_memory_buffer()


def _snapshot(task: str) -> None:
    memory_buffer_snapshot(task, [{"event": "node", "task": task}])


def _snapshot_tasks(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return [r["task"] for r in rows if r["event"] == "snapshot_task"]


class TestLimitValidation:
    def test_zero_limit_is_rejected(self, tmp_path):
        _snapshot("t0")
        with pytest.raises(ValueError, match="limit"):
            dump_recent_to_with_reason(str(tmp_path), limit=0)
        assert not list(tmp_path.iterdir()), "非法参数不得留下任何落盘痕迹"

    @pytest.mark.parametrize("bad", [-1, -2, -100])
    def test_negative_limit_is_rejected(self, tmp_path, bad):
        _snapshot("t0")
        with pytest.raises(ValueError, match="limit"):
            dump_recent_to_with_reason(str(tmp_path), limit=bad)
        assert not list(tmp_path.iterdir())

    def test_public_wrapper_also_validates(self, tmp_path):
        _snapshot("t0")
        with pytest.raises(ValueError, match="limit"):
            dump_recent_to(str(tmp_path), limit=0)

    def test_validation_precedes_empty_buffer(self, tmp_path):
        # 参数错误优先于「无快照」状态：空缓冲也必须先报用法错误
        with pytest.raises(ValueError, match="limit"):
            dump_recent_to_with_reason(str(tmp_path), limit=0)

    def test_positive_limit_still_works(self, tmp_path):
        for i in range(3):
            _snapshot(f"t{i}")
        path = dump_recent_to(str(tmp_path), limit=2)
        assert path is not None
        assert _snapshot_tasks(path) == ["t1", "t2"]


class TestUniqueDumpPath:
    def test_same_second_dumps_do_not_overwrite(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("time.time", lambda: float(TS))
        _snapshot("t0")

        first = dump_recent_to(str(tmp_path))
        assert first is not None
        first_bytes = Path(first).read_bytes()
        second = dump_recent_to(str(tmp_path))

        assert second is not None
        assert first != second, "同一秒内的第二次导出必须使用新文件，不得覆盖第一份"
        assert Path(first).read_bytes() == first_bytes, "第一份诊断快照内容不得被改写"
        assert os.path.basename(first) == f"{TS}_failed_trace.jsonl"
        assert os.path.basename(second) == f"{TS}_2_failed_trace.jsonl"

    def test_existing_file_is_preserved(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("time.time", lambda: float(TS))
        _snapshot("t0")
        existing = tmp_path / f"{TS}_failed_trace.jsonl"
        existing.write_text('{"sentinel": "keep"}\n', encoding="utf-8")

        path = dump_recent_to(str(tmp_path))

        assert path is not None
        assert existing.read_text(encoding="utf-8") == '{"sentinel": "keep"}\n'
        assert os.path.basename(path) == f"{TS}_2_failed_trace.jsonl"

    def test_concurrent_dumps_get_distinct_files(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("time.time", lambda: float(TS))
        for i in range(3):
            _snapshot(f"t{i}")
        n = 4
        barrier = threading.Barrier(n)
        paths: list[str] = []
        lock = threading.Lock()

        def worker() -> None:
            barrier.wait()
            path = dump_recent_to(str(tmp_path))
            with lock:
                paths.append(path)

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(p is not None for p in paths)
        assert len(set(paths)) == n, f"{n} 次并发导出必须各自落盘，实际路径：{paths}"
        files = sorted(p for p in tmp_path.iterdir() if p.is_file())
        assert len(files) == n, f"目录内应有 {n} 份快照，实际：{[f.name for f in files]}"
        for path in paths:
            assert _snapshot_tasks(path) == ["t0", "t1", "t2"], "每份快照都必须是完整合法的 JSONL"


class TestWriteFailureCleanup:
    def test_partial_file_is_removed_on_write_failure(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        _snapshot("t0")

        def boom(fd, *args, **kwargs):
            raise OSError("注入写盘失败")

        monkeypatch.setattr(os, "fdopen", boom)
        path, reason = dump_recent_to_with_reason(str(tmp_path))

        assert path is None
        assert reason is not None and "写盘失败" in reason
        assert not list(tmp_path.iterdir()), "写盘失败不得留下空壳 / 半成品文件"
