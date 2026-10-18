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


class TestNonDistributedExclusions:
    """A18（2026-10-18 第三方审查 P2）：清单只覆盖实际分发文件。

    评审证据：p/r/s 轮清单记录了未分发的 `_helpers/__pycache__/*.pyc`
    （干净检出必然报缺失）。`--write`/`--verify` 统一排除解释器缓存；
    `--exclude` 供调用方排除其他只在本机留档的文件。
    """

    def _add_pycache(self, root: Path) -> None:
        pycache = root / "_helpers" / "__pycache__"
        pycache.mkdir(parents=True)
        (pycache / "analyze.cpython-314.pyc").write_bytes(b"\x00pyc-bytes")
        (root / "legacy.pyc").write_bytes(b"\x00legacy")
        (root / "legacy.pyo").write_bytes(b"\x00legacy2")

    def test_pycache_and_bytecode_excluded_from_write(self, tmp_path: Path):
        _make_tree(tmp_path)
        self._add_pycache(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        manifest_text = (tmp_path / gate.MANIFEST_NAME).read_text(encoding="utf-8")
        assert "__pycache__" not in manifest_text
        assert ".pyc" not in manifest_text
        assert ".pyo" not in manifest_text
        assert gate.verify_manifest(tmp_path) == 0

    def test_pycache_present_locally_does_not_fail_verify(self, tmp_path: Path):
        """本地跑过 helper 生成的 __pycache__ 不得被判"清单外新增"。"""
        _make_tree(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        self._add_pycache(tmp_path)
        assert gate.verify_manifest(tmp_path) == 0

    def test_explicit_exclude_globs(self, tmp_path: Path):
        """--exclude：本机留档、不随包分发的文件（fnmatch 相对路径）。"""
        _make_tree(tmp_path)
        (tmp_path / "local_only.log").write_text("local", encoding="utf-8")
        (tmp_path / "sub" / "debug.local.json").write_text("{}", encoding="utf-8")
        assert gate.write_manifest(tmp_path, excludes=("local_only.log", "sub/*.local.json")) == 0
        manifest_text = (tmp_path / gate.MANIFEST_NAME).read_text(encoding="utf-8")
        assert "local_only.log" not in manifest_text
        assert "debug.local.json" not in manifest_text
        assert "a.json" in manifest_text
        assert gate.verify_manifest(tmp_path, excludes=("local_only.log", "sub/*.local.json")) == 0

    def test_excluded_file_removal_does_not_break_verify(self, tmp_path: Path):
        """沿用排除口径：被排除文件消失后 verify 仍通过（不报缺失）。"""
        _make_tree(tmp_path)
        (tmp_path / "local_only.log").write_text("local", encoding="utf-8")
        excludes = ("local_only.log",)
        assert gate.write_manifest(tmp_path, excludes=excludes) == 0
        (tmp_path / "local_only.log").unlink()
        assert gate.verify_manifest(tmp_path, excludes=excludes) == 0


class TestEolOnlyDiagnostics:
    """A17（2026-10-18 第三方审查 P1）：EOL-only 差异不得误判为内容篡改。

    评审证据：Windows autocrlf=true 检出时 6,974 条清单记录仅"LF 归一化后"
    匹配、0 条内容不符——跨平台换行约定不是篡改。门禁必须：
    - 区分 raw / EOL-only / 内容不符，EOL-only 单独报告（默认不判失败）；
    - `--strict-bytes` 可强制按字节失败；
    - 内容篡改（即使同时换行）仍必须失败。
    """

    def _crlf(self, path: Path) -> None:
        data = path.read_bytes()
        path.write_bytes(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))

    def _make_multiline_tree(self, root: Path) -> None:
        """含多行文本的最小目录（单行文件无法体现换行约定差异）。"""
        (root / "multi.txt").write_bytes(b"line1\nline2\n")
        (root / "a.json").write_bytes(b'{\n  "a": 1\n}\n')

    def test_eol_only_passes_with_explicit_warning(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        self._make_multiline_tree(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        self._crlf(tmp_path / "multi.txt")  # 模拟 Windows autocrlf=true 检出
        assert gate.verify_manifest(tmp_path) == 0
        out = capsys.readouterr().out
        assert "EOL 差异" in out
        assert "EOL-only: multi.txt" in out
        assert "内容不符" not in out
        assert "校验通过" in out

    def test_eol_only_fails_under_strict_bytes(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        self._make_multiline_tree(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        self._crlf(tmp_path / "multi.txt")
        assert gate.verify_manifest(tmp_path, strict_bytes=True) == 1
        assert "strict-bytes" in capsys.readouterr().out

    def test_content_tamper_still_fails_even_with_crlf(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """内容确有变化（即使同时换了行尾）必须以"内容不符"失败。"""
        _make_tree(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        path = tmp_path / "a.json"
        path.write_bytes(b'{"a": 2}\r\n')
        assert gate.verify_manifest(tmp_path) == 1
        out = capsys.readouterr().out
        assert "哈希不符" in out
        assert "非换行差异）: a.json" in out

    def test_lf_against_crlf_manifest_is_also_eol_only(self, tmp_path: Path):
        """反向：清单按 CRLF 生成、检出为 LF（外部 Windows 工具生成的清单）。"""
        (tmp_path / "crlf.txt").write_bytes(b"line1\r\nline2\r\n")
        import hashlib

        digest = hashlib.sha256(b"line1\r\nline2\r\n").hexdigest()
        (tmp_path / gate.MANIFEST_NAME).write_text(f"{digest}  crlf.txt\n", encoding="utf-8")
        (tmp_path / "crlf.txt").write_bytes(b"line1\nline2\n")  # LF 检出
        assert gate.verify_manifest(tmp_path) == 0

    def test_txt_manifest_variant_is_verified(self, tmp_path: Path):
        """外部工具生成的 SHA256SUMS.txt 变体也可经 --verify 校验。"""
        _make_tree(tmp_path)
        assert gate.write_manifest(tmp_path) == 0
        canonical = tmp_path / gate.MANIFEST_NAME
        canonical.rename(tmp_path / "SHA256SUMS.txt")
        assert gate.verify_manifest(tmp_path) == 0
        (tmp_path / "a.json").write_text('{"a": 2}', encoding="utf-8")
        assert gate.verify_manifest(tmp_path) == 1


class TestEvidenceEolPolicy:
    """A17 配套：仓库根 .gitattributes 必须固定证据工件的换行策略。

    只有 `.gitattributes` 把证据目录声明为 `-text`（字节保真），跨平台干净
    检出才能对 SHA256SUMS 按原始字节校验；否则 Windows autocrlf=true 会把
    LF 转成 CRLF，让数千条记录"仅换行匹配"。
    """

    def test_evidence_dirs_are_byte_stable(self):
        attributes = (Path(__file__).resolve().parents[1] / ".gitattributes").read_text(encoding="utf-8")
        rules = [line.strip() for line in attributes.splitlines() if line.strip() and not line.startswith("#")]
        assert "experiments/results/** -text" in rules
        assert "docs/reviews/review_recompute/** -text" in rules
        # 反证：不得用 text/eol 转换规则（会改写历史字节、破坏按字节校验）
        for rule in rules:
            assert not rule.startswith("experiments/results/** text"), rule
            assert not rule.startswith("docs/reviews/review_recompute/** text"), rule
