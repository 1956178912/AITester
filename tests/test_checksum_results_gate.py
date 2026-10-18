#!/usr/bin/env python3
"""实验结果工件校验门禁（`scripts/gates/checksum_results.py`）的回归锁定。

锁定三件事（2026-10-16 修复：fresh clone 下 U1 门禁因 `.mimosa` 点目录
条目必然报"缺失"——本地因文件在盘而不可见）：

1. **隐藏路径不参加校验**：点文件与点目录内的文件都不写入清单
   （不入库的本地工装状态不得污染 CI 校验）；
2. **真校验真的会失败**：缺失 / 清单外新增 / 哈希不符三类问题都必须报错；
3. **write → verify 往返一致**且重复 write 清单稳定（确定性）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_GATE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "gates" / "checksum_results.py"
_spec = importlib.util.spec_from_file_location("_checksum_gate", _GATE_PATH)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
sys.modules["_checksum_gate"] = gate
_spec.loader.exec_module(gate)


def _make_tree(root: Path) -> None:
    """构造含普通文件 + 隐藏文件 + 隐藏目录（.mimosa 场景）的迷你结果目录。"""
    (root / "a.json").write_text('{"a": 1}', encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "b.txt").write_text("b", encoding="utf-8")
    (root / ".hidden.json").write_text("h", encoding="utf-8")
    hidden_dir = root / ".mimosa" / "hook-state"
    hidden_dir.mkdir(parents=True)
    (hidden_dir / "sess.json").write_text("s", encoding="utf-8")


class TestCollectExclusions:
    def test_hidden_paths_are_excluded(self, tmp_path: Path):
        _make_tree(tmp_path)
        files = gate._collect(tmp_path, tmp_path / gate.MANIFEST_NAME)
        rels = sorted(p.relative_to(tmp_path).as_posix() for p in files)
        assert rels == ["a.json", "sub/b.txt"]

    def test_manifest_itself_is_excluded(self, tmp_path: Path):
        _make_tree(tmp_path)
        manifest = tmp_path / gate.MANIFEST_NAME
        manifest.write_text("", encoding="utf-8")
        files = gate._collect(tmp_path, manifest)
        assert manifest not in files


class TestWriteVerifyRoundTrip:
    def test_write_then_verify_passes(self, tmp_path: Path):
        _make_tree(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        manifest_text = (tmp_path / gate.MANIFEST_NAME).read_text(encoding="utf-8")
        assert ".mimosa" not in manifest_text
        assert ".hidden.json" not in manifest_text
        assert gate.verify_manifest(tmp_path) == 0

    def test_hidden_files_present_locally_do_not_fail_verify(self, tmp_path: Path):
        """本地存在 .mimosa 点目录（fresh clone 不会有的场景）不得报'清单外新增'。"""
        _make_tree(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        # 再写一个点目录内文件，verify 仍须通过（收集端已排除）
        (tmp_path / ".mimosa" / "hook-state" / "sess2.json").write_text("s2", encoding="utf-8")
        assert gate.verify_manifest(tmp_path) == 0

    def test_missing_recorded_file_fails(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        _make_tree(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        (tmp_path / "a.json").unlink()
        assert gate.verify_manifest(tmp_path) == 1
        assert "缺失" in capsys.readouterr().out

    def test_extra_unrecorded_file_fails(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        _make_tree(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        (tmp_path / "new.json").write_text("n", encoding="utf-8")
        assert gate.verify_manifest(tmp_path) == 1
        assert "清单外新增" in capsys.readouterr().out

    def test_tampered_hash_fails(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        _make_tree(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        (tmp_path / "a.json").write_text('{"a": 2}', encoding="utf-8")
        assert gate.verify_manifest(tmp_path) == 1
        assert "哈希不符" in capsys.readouterr().out

    def test_repeated_write_is_deterministic(self, tmp_path: Path):
        _make_tree(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        first = (tmp_path / gate.MANIFEST_NAME).read_text(encoding="utf-8")
        assert gate.write_manifest(tmp_path) == 0
        second = (tmp_path / gate.MANIFEST_NAME).read_text(encoding="utf-8")
        assert first == second

    def test_verify_without_manifest_fails(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        _make_tree(tmp_path)
        assert gate.verify_manifest(tmp_path) == 1
        assert "清单不存在" in capsys.readouterr().out


class TestManifestPathNormalization:
    """T 轮（2026-10-18，审计 P2-14）：外部工具生成的路径写法必须可校验。

    实测触发：`emse_docstring_anchor_20261017/SHA256SUMS` 由 `shasum` 以 `./x`
    形式生成，`--verify` 把 165 条全部误判"缺失 + 清单外新增"，而
    `shasum -a 256 -c` 165/165 OK——同一份事实两种工具两种结论。
    """

    def _rewrite_manifest(self, root: Path, transform) -> None:
        manifest = root / gate.MANIFEST_NAME
        lines = manifest.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines:
            digest, _, rel = line.partition("  ")
            out.append(f"{digest}  {transform(rel)}")
        manifest.write_text("\n".join(out) + "\n", encoding="utf-8")

    def test_dot_slash_prefix_verifies(self, tmp_path: Path):
        _make_tree(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        self._rewrite_manifest(tmp_path, lambda rel: f"./{rel}")
        assert gate.verify_manifest(tmp_path) == 0

    def test_asterisk_binary_marker_verifies(self, tmp_path: Path):
        _make_tree(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        self._rewrite_manifest(tmp_path, lambda rel: f"*{rel}")
        assert gate.verify_manifest(tmp_path) == 0

    def test_windows_backslash_verifies(self, tmp_path: Path):
        _make_tree(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        self._rewrite_manifest(tmp_path, lambda rel: rel.replace("/", "\\"))
        assert gate.verify_manifest(tmp_path) == 0

    def test_still_detects_missing_after_normalization(self, tmp_path: Path):
        """归一化不得把真缺失洗白。"""
        _make_tree(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        self._rewrite_manifest(tmp_path, lambda rel: f"./{rel}")
        (tmp_path / "a.json").unlink()
        assert gate.verify_manifest(tmp_path) == 1
