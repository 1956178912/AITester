"""atomic_io 原子写工具测试（U4，2026-10-05 系统性审查落地）。

锁定 src/utils/atomic_io.py 的三条契约：
1. 完整性：写入后内容/权限正确，无临时文件残留；
2. 原子性：os.replace 语义（目标恒为完整旧内容或完整新内容）；
3. 并发：多线程同目标写不产生半写文件（串行化由调用方锁保证，此处
   验证压力下文件恒可解析）。
"""

from __future__ import annotations

import contextlib
import json
import threading

from src.utils.atomic_io import atomic_write_json, atomic_write_text


class TestAtomicWriteText:
    def test_writes_content_and_no_tmp_left(self, tmp_path):
        """写入后内容正确，且同目录无 .aitester_tmp_ 残留。"""
        target = tmp_path / "out.txt"
        atomic_write_text(str(target), "hello 原子写")
        assert target.read_text(encoding="utf-8") == "hello 原子写"
        assert not list(tmp_path.glob(".aitester_tmp_*")), "临时文件未清理"

    def test_overwrite_replaces_completely(self, tmp_path):
        """覆盖写：旧内容被完整替换（无截断/拼接）。"""
        target = tmp_path / "out.txt"
        atomic_write_text(str(target), "A" * 5000)
        atomic_write_text(str(target), "B")
        assert target.read_text(encoding="utf-8") == "B"

    def test_mode_default_0600(self, tmp_path):
        """默认权限收敛 0600（含敏感内容的配置文件口径）。"""
        target = tmp_path / "secret.env"
        atomic_write_text(str(target), "KEY=1")
        assert (target.stat().st_mode & 0o777) == 0o600

    def test_custom_mode_respected(self, tmp_path):
        """显式 mode=0o644 生效（非敏感文件的共享口径）。"""
        target = tmp_path / "shared.txt"
        atomic_write_text(str(target), "x", mode=0o644)
        assert (target.stat().st_mode & 0o777) == 0o644

    def test_replace_is_atomic_under_reader(self, tmp_path):
        """读者视角原子性：替换过程中读到的要么是旧完整内容要么是新完整内容。"""
        target = tmp_path / "atomic.txt"
        atomic_write_text(str(target), "OLD" * 100)
        atomic_write_text(str(target), "NEW" * 100)
        content = target.read_text(encoding="utf-8")
        assert content in ("OLD" * 100, "NEW" * 100), "读到中间态（原子性被破坏）"

    def test_failure_cleans_tmp(self, tmp_path, monkeypatch):
        """os.replace 失败时清理临时文件，目标保持旧内容。"""
        target = tmp_path / "keep.txt"
        atomic_write_text(str(target), "old-content")
        import src.utils.atomic_io as mod

        def _boom(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(mod.os, "replace", _boom)
        with contextlib.suppress(OSError):
            atomic_write_text(str(target), "new-content")
        assert target.read_text(encoding="utf-8") == "old-content", "替换失败后目标被破坏"
        assert not list(tmp_path.glob(".aitester_tmp_*")), "失败后临时文件未清理"


class TestAtomicWriteJson:
    def test_json_roundtrip(self, tmp_path):
        """JSON 往返一致（ensure_ascii=False 中文不转义）。"""
        target = tmp_path / "data.json"
        obj = {"中文键": "值", "n": 3, "items": ["a", "b"]}
        atomic_write_json(str(target), obj)
        assert json.loads(target.read_text(encoding="utf-8")) == obj
        assert "中文键" in target.read_text(encoding="utf-8")

    def test_unserializable_raises_and_cleans(self, tmp_path):
        """不可序列化对象抛 TypeError 且无临时残留。"""
        target = tmp_path / "bad.json"
        with contextlib.suppress(TypeError):
            atomic_write_json(str(target), {"x": object()})
        assert not list(tmp_path.glob(".aitester_tmp_*"))


class TestConcurrentWrites:
    def test_parallel_writers_produce_parseable_file(self, tmp_path):
        """8 线程并发写同一目标：每次写完读到的都是完整 JSON（压力护栏）。"""
        target = tmp_path / "counter.json"
        atomic_write_json(str(target), {"writer": -1})
        errors: list[str] = []
        lock = threading.Lock()

        def _writer(i: int) -> None:
            for round_no in range(20):
                try:
                    atomic_write_json(str(target), {"writer": i, "round": round_no})
                    data = json.loads(target.read_text(encoding="utf-8"))
                    if "writer" not in data:
                        with lock:
                            errors.append(f"读不到 writer 键 (r{round_no})")
                except (json.JSONDecodeError, OSError) as e:
                    with lock:
                        errors.append(f"{type(e).__name__}: {e}")

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, f"并发写产生中间态: {errors[:3]}"

    def test_parallel_distinct_targets(self, tmp_path):
        """8 线程各写各的目标：全部完整落盘（无交叉污染）。"""

        def _writer(i: int) -> None:
            atomic_write_json(str(tmp_path / f"w{i}.json"), {"idx": i})

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for i in range(8):
            data = json.loads((tmp_path / f"w{i}.json").read_text(encoding="utf-8"))
            assert data == {"idx": i}
        assert not list(tmp_path.glob(".aitester_tmp_*"))
