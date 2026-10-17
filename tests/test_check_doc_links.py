#!/usr/bin/env python3
"""文档链接完整性门禁（`scripts/gates/check_doc_links.py`）的回归锁定。

锁定八件事（2026-10-17 WP-C 文档完整性批次）：

1. **文件链接**：相对/绝对（仓库根）路径、父目录路径、目录链接、百分号编码、
   图片、符号链接都要按"目标存在"判定；缺失即 error；
2. **大小写精确校验**：`Docs/Foo.md` 写法在 macOS 本地能解析、在 Linux/CI
   上 404——门禁必须在本地就报出来（防"本地绿、CI 红"）；
3. **行锚**：`#L24` / `#L24-L30` 只校验目标文件存在，不校验行号内容；
4. **锚点**：近似 GitHub slug（v2 口径，含 CJK 标题与全角标点、重复标题
   `-1` 后缀、行内 code / 链接标题归一化）；ASCII 锚点未命中是 error，
   含 CJK 的未命中降级 warning；
5. **代码区**：fenced code block 与 inline code 里的示例链接一律忽略；
   链接解析支持引用式 `[text][label]` 与块引用续行包裹的跨行链接；
6. **外链零网络**：`http(s)` / `mailto` / 其他 scheme 只统计不请求、不判失败；
7. **allowlist**：命中记 `[allow]`（不阻断 `--strict`），但每行必须带理由，
   无理由的豁免本身是 error；
8. **fail-closed**：扫描面为空必须失败（`--allow-empty` 显式放行），并锁定
   "当前真实仓库零坏链"与可枚举复算的统计口径。

测试全部在 `tmp_path` 构造的临时仓库上跑（除 `TestCurrentRepo` 直接扫真实
仓库），零网络。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

_GATE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "gates" / "check_doc_links.py"
_spec = importlib.util.spec_from_file_location("_doc_links_gate", _GATE_PATH)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
sys.modules["_doc_links_gate"] = gate
_spec.loader.exec_module(gate)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clear_listdir_cache():
    """每个用例前后清空目录项缓存（同一 tmp_path 内多次写入后再扫的场景）。"""
    gate._LISTDIR_CACHE.clear()
    yield
    gate._LISTDIR_CACHE.clear()


def _write(root: Path, rel: str, text: str) -> Path:
    """在 tmp 仓库写一个文件（自动建父目录）。"""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _scan(root: Path, **kwargs) -> gate.ScanResult:
    """扫临时仓库（默认自动读取 root/docs/link_check_allowlist.txt）。"""
    return gate.scan(root=root, **kwargs)


# ---------------------------------------------------------------------------
# 1. 文件链接
# ---------------------------------------------------------------------------


class TestFileLinks:
    def test_good_relative_file_link(self, tmp_path):
        _write(tmp_path, "README.md", "见 [文档](docs/a.md)。\n")
        _write(tmp_path, "docs/a.md", "# A\n")
        result = _scan(tmp_path)
        assert result.errors == []
        assert result.stats.file_links == 1
        assert result.stats.internal_links == 1

    def test_missing_relative_file_is_error(self, tmp_path):
        _write(tmp_path, "README.md", "见 [文档](docs/missing.md)。\n")
        result = _scan(tmp_path)
        assert len(result.errors) == 1
        assert "目标不存在" in result.errors[0].message
        assert result.errors[0].source == "README.md"
        assert result.errors[0].line == 1

    def test_parent_dir_relative_link(self, tmp_path):
        _write(tmp_path, "docs/a.md", "[根 README](../README.md)\n")
        _write(tmp_path, "README.md", "# root\n")
        assert _scan(tmp_path).errors == []

    def test_root_absolute_link(self, tmp_path):
        """`/docs/b.md` 按仓库根解析（不是文件系统根）。"""
        _write(tmp_path, "README.md", "[b](/docs/b.md)\n")
        _write(tmp_path, "docs/b.md", "# B\n")
        assert _scan(tmp_path).errors == []

    def test_directory_link_allowed(self, tmp_path):
        _write(tmp_path, "README.md", "[门禁目录](scripts/gates/)\n")
        _write(tmp_path, "scripts/gates/x.py", "# placeholder\n")
        result = _scan(tmp_path)
        assert result.errors == []
        assert result.stats.directory_links == 1

    def test_percent_encoded_target(self, tmp_path):
        _write(tmp_path, "README.md", "[含空格](docs/with%20space.md)\n")
        _write(tmp_path, "docs/with space.md", "# space\n")
        assert _scan(tmp_path).errors == []

    def test_case_mismatch_is_error(self, tmp_path):
        """`foo.md` vs 实际 `Foo.md`：必须报错（macOS 本地可解析、CI 上 404）。"""
        _write(tmp_path, "README.md", "[大小写](docs/foo.md)\n")
        _write(tmp_path, "docs/Foo.md", "# Foo\n")
        result = _scan(tmp_path)
        assert len(result.errors) == 1
        assert result.errors[0].target == "docs/foo.md"

    def test_image_target_checked(self, tmp_path):
        _write(tmp_path, "README.md", "![图](../images/pic.png)\n")
        result = _scan(tmp_path)
        assert len(result.errors) == 1
        assert result.stats.image_links == 1

    def test_image_target_ok(self, tmp_path):
        _write(tmp_path, "README.md", "![图](images/pic.png)\n")
        _write(tmp_path, "images/pic.png", "binary")
        result = _scan(tmp_path)
        assert result.errors == []
        assert result.stats.image_links == 1
        assert result.stats.file_links == 1

    @pytest.mark.skipif(not hasattr(os, "symlink"), reason="平台不支持符号链接")
    def test_symlink_target_ok(self, tmp_path):
        """符号链接名按原样存在即通过（macOS 符号链接场景）。"""
        _write(tmp_path, "real.md", "# real\n")
        _write(tmp_path, "README.md", "[别名](alias.md)\n")
        os.symlink(tmp_path / "real.md", tmp_path / "alias.md")
        assert _scan(tmp_path).errors == []


# ---------------------------------------------------------------------------
# 2. 行锚（只校验文件存在）
# ---------------------------------------------------------------------------


class TestLineAnchors:
    def test_line_anchor_only_checks_file_existence(self, tmp_path):
        """`x.py#L999`：文件存在即通过（行号越界不判失败，口径见 docstring）。"""
        _write(tmp_path, "README.md", "[入口](src/x.py#L999)\n")
        _write(tmp_path, "src/x.py", "print(1)\n")
        result = _scan(tmp_path)
        assert result.errors == []
        assert result.stats.line_anchor_links == 1

    def test_line_range_anchor(self, tmp_path):
        _write(tmp_path, "README.md", "[区间](src/x.py#L10-L20)\n")
        _write(tmp_path, "src/x.py", "print(1)\n")
        result = _scan(tmp_path)
        assert result.errors == []
        assert result.stats.line_anchor_links == 1

    def test_line_anchor_missing_file_is_error(self, tmp_path):
        _write(tmp_path, "README.md", "[入口](src/nope.py#L24)\n")
        result = _scan(tmp_path)
        assert len(result.errors) == 1
        assert "目标不存在" in result.errors[0].message


# ---------------------------------------------------------------------------
# 3. 锚点（近似 GitHub slug）
# ---------------------------------------------------------------------------


class TestAnchors:
    def test_same_file_anchor_hit(self, tmp_path):
        _write(tmp_path, "README.md", "# 标题\n\n目录：[跳转](#标题)\n")
        result = _scan(tmp_path)
        assert result.errors == []
        assert result.stats.anchor_links == 1

    def test_ascii_anchor_miss_is_error(self, tmp_path):
        _write(tmp_path, "README.md", "# Title\n\n[坏锚](#NoSuchAnchor)\n")
        result = _scan(tmp_path)
        assert len(result.errors) == 1
        assert "锚点未命中" in result.errors[0].message

    def test_cjk_heading_slug_follows_github_v2(self, tmp_path):
        """`## 一、背景` → slug `一背景`（Unicode 标点 `、` 被删除）。"""
        _write(tmp_path, "README.md", "# 文档\n\n## 一、背景\n\n[回跳](#一背景)\n")
        result = _scan(tmp_path)
        assert result.errors == []
        assert result.stats.anchor_links == 1

    def test_cjk_fullwidth_punctuation_in_heading(self, tmp_path):
        """全角括号被删除：`## 8. 双通道（谱系 + LLM）` → `8-双通道谱系--llm`。"""
        _write(tmp_path, "README.md", "# 文档\n\n## 8. 双通道（谱系 + LLM）\n\n[§8](#8-双通道谱系--llm)\n")
        assert _scan(tmp_path).errors == []

    def test_cjk_anchor_miss_is_warning_not_error(self, tmp_path):
        _write(tmp_path, "README.md", "# 文档\n\n[坏锚](#不存在的标题)\n")
        result = _scan(tmp_path)
        assert result.errors == []
        assert len(result.warnings) == 1
        assert "含 CJK" in result.warnings[0].message

    def test_duplicate_heading_gets_numeric_suffix(self, tmp_path):
        _write(tmp_path, "README.md", "# 文档\n\n## Foo\n\n## Foo\n\n[第二个](#foo-1)\n")
        assert _scan(tmp_path).errors == []

    def test_cross_file_anchor(self, tmp_path):
        _write(tmp_path, "README.md", "[跨文件](docs/a.md#设计)\n")
        _write(tmp_path, "docs/a.md", "# 设计\n")
        result = _scan(tmp_path)
        assert result.errors == []
        assert result.stats.anchor_links == 1

    def test_heading_with_inline_code_slug(self, tmp_path):
        """`## `foo` bar` → slug `foo-bar`（行内 code 内容进 slug，反引号不进）。"""
        _write(tmp_path, "README.md", "# 文档\n\n## `foo` bar\n\n[跳](#foo-bar)\n")
        assert _scan(tmp_path).errors == []

    def test_heading_with_link_text_slug(self, tmp_path):
        """标题里的 Markdown 链接按"渲染后文本"算 slug（不含 URL）。"""
        _write(tmp_path, "README.md", "# 文档\n\n## [设计文档](https://example.com/x)\n\n[跳](#设计文档)\n")
        assert _scan(tmp_path).errors == []

    def test_non_markdown_target_anchor_is_warning(self, tmp_path):
        """`.py#L24` 是行锚（通过）；`.py#some-anchor` 无法静态校验 → warning。"""
        _write(tmp_path, "README.md", "[代码](src/x.py#some-anchor)\n")
        _write(tmp_path, "src/x.py", "print(1)\n")
        result = _scan(tmp_path)
        assert result.errors == []
        assert len(result.warnings) == 1
        assert result.stats.unverifiable_anchor_links == 1


# ---------------------------------------------------------------------------
# 4. 代码区忽略
# ---------------------------------------------------------------------------


class TestCodeRegionsIgnored:
    def test_fenced_code_block_links_ignored(self, tmp_path):
        text = "# 文档\n\n```markdown\n[示例](does/not/exist.md)\n```\n\n~~~\n[另一个](nope.md)\n~~~\n"
        _write(tmp_path, "README.md", text)
        result = _scan(tmp_path)
        assert result.errors == []
        assert result.stats.links_total == 0

    def test_inline_code_links_ignored(self, tmp_path):
        _write(tmp_path, "README.md", "写法：`[示例](does/not/exist.md)` 与 ``[x](nope.md)``。\n")
        result = _scan(tmp_path)
        assert result.errors == []
        assert result.stats.links_total == 0

    def test_links_outside_code_still_checked(self, tmp_path):
        text = "`[示例](fake.md)`\n\n真实链接：[缺](missing.md)\n"
        _write(tmp_path, "README.md", text)
        result = _scan(tmp_path)
        assert len(result.errors) == 1
        assert result.errors[0].target == "missing.md"

    def test_reference_style_link_checked(self, tmp_path):
        _write(tmp_path, "README.md", "见 [设计][design]。\n\n[design]: docs/b.md\n")
        _write(tmp_path, "docs/b.md", "# B\n")
        result = _scan(tmp_path)
        assert result.errors == []
        assert result.stats.internal_links == 1

    def test_reference_style_link_broken_is_error(self, tmp_path):
        _write(tmp_path, "README.md", "[设计][design]\n\n[design]: docs/nope.md\n")
        assert len(_scan(tmp_path).errors) == 1

    def test_multiline_link_wrapped_in_blockquote(self, tmp_path):
        """跨行链接（块引用续行包裹）：`[x](\\n> path)` 必须能解析。"""
        _write(tmp_path, "README.md", "> 参见 [设计](\n> docs/design.md) 口径。\n")
        _write(tmp_path, "docs/design.md", "# design\n")
        result = _scan(tmp_path)
        assert result.errors == []
        assert result.stats.internal_links == 1


# ---------------------------------------------------------------------------
# 5. 外链（只统计不请求）
# ---------------------------------------------------------------------------


class TestExternalLinks:
    def test_external_links_counted_not_failed(self, tmp_path):
        text = "[A](https://example.com/a) [B](http://example.com/b) [C](mailto:x@example.com) [D](ftp://x/y)\n"
        _write(tmp_path, "README.md", text)
        result = _scan(tmp_path)
        assert result.errors == []
        assert result.stats.external_links == 4
        assert result.stats.internal_links == 0

    def test_autolink_counted_external(self, tmp_path):
        _write(tmp_path, "README.md", "自动链接 <https://example.com/x>。\n")
        result = _scan(tmp_path)
        assert result.errors == []
        assert result.stats.links_total == 1
        assert result.stats.external_links == 1


# ---------------------------------------------------------------------------
# 6. 扫描面与排除面
# ---------------------------------------------------------------------------


class TestScanSurface:
    def test_scan_surface_and_exclusions(self, tmp_path):
        """根 md / docs / examples 扫描；CHANGELOG 与 docs/history / 其他目录不扫。"""
        _write(tmp_path, "README.md", "[ok](docs/a.md)\n")
        _write(tmp_path, "docs/a.md", "# A\n")
        _write(tmp_path, "examples/e.md", "# E\n")
        _write(tmp_path, "CHANGELOG.md", "[坏](missing_changelog.md)\n")
        _write(tmp_path, "CHANGELOG.en.md", "[坏](missing_changelog_en.md)\n")
        _write(tmp_path, "docs/history/h.md", "[坏](missing_history.md)\n")
        _write(tmp_path, "other/o.md", "[坏](missing_other.md)\n")
        result = _scan(tmp_path)
        assert result.errors == []
        assert result.stats.files == 3
        assert result.stats.files_by_area == {"root": 1, "docs": 1, "examples": 1}

    def test_excluded_area_still_checked_as_target(self, tmp_path):
        """排除面不作为 source，但作为链接目标仍要被校验（缺文件仍报错）。"""
        _write(tmp_path, "docs/a.md", "[变更日志](../CHANGELOG.md)\n")
        result = _scan(tmp_path)
        assert len(result.errors) == 1
        _write(tmp_path, "CHANGELOG.md", "# Changelog\n")
        gate._LISTDIR_CACHE.clear()
        assert _scan(tmp_path).errors == []


# ---------------------------------------------------------------------------
# 7. allowlist
# ---------------------------------------------------------------------------


class TestAllowlist:
    def test_allowlist_suppresses_error_and_strict_passes(self, tmp_path):
        _write(tmp_path, "docs/a.md", "[历史工件](missing.md)\n")
        _write(
            tmp_path,
            "docs/link_check_allowlist.txt",
            "docs/a.md:missing.md  # 该工件未入库，仅为历史快照引用\n",
        )
        result = _scan(tmp_path)
        assert result.errors == []
        assert len(result.warnings) == 1
        assert result.warnings[0].allowlisted is True
        assert "历史快照" in result.warnings[0].reason
        assert result.stats.allowlist_hits == 1
        assert result.strict_warnings == []
        assert gate.main(["--root", str(tmp_path), "--strict"]) == 0

    def test_allowlist_requires_reason(self, tmp_path):
        """无理由的豁免是 error（豁免是有成本承诺，必须写清理由）。"""
        _write(tmp_path, "docs/a.md", "[历史工件](missing.md)\n")
        _write(tmp_path, "docs/link_check_allowlist.txt", "docs/a.md:missing.md\n")
        result = _scan(tmp_path)
        assert len(result.errors) == 1
        assert "缺少理由" in result.errors[0].message

    def test_allowlist_key_must_match_source_and_target(self, tmp_path):
        _write(tmp_path, "docs/a.md", "[历史工件](missing.md)\n")
        _write(tmp_path, "docs/link_check_allowlist.txt", "docs/other.md:missing.md  # 不匹配的键\n")
        result = _scan(tmp_path)
        assert len(result.errors) == 1
        assert result.stats.allowlist_hits == 0


# ---------------------------------------------------------------------------
# 8. 统计、JSON 与退出码
# ---------------------------------------------------------------------------


class TestStatsAndJson:
    def test_stats_are_recomputable(self, tmp_path):
        text = (
            "# 文档\n\n## title\n\n"
            "[文件](b.md) [外链](https://example.com) ![图](pic.png) "
            "[锚点](#title) [行锚](b.md#L3) [目录](sub/)\n"
        )
        _write(tmp_path, "README.md", text)
        _write(tmp_path, "b.md", "# B\n")
        _write(tmp_path, "pic.png", "binary")
        _write(tmp_path, "sub/x.txt", "x")
        result = _scan(tmp_path)
        stats = result.stats
        assert stats.links_total == 6
        assert stats.internal_links == 5
        assert stats.external_links == 1
        assert stats.links_total == stats.internal_links + stats.external_links
        assert stats.image_links == 1
        assert stats.file_links == 2  # b.md + pic.png
        assert stats.directory_links == 1
        assert stats.anchor_links == 1
        assert stats.line_anchor_links == 1

    def test_json_output_schema_and_exit_zero(self, tmp_path, capsys):
        _write(tmp_path, "README.md", "[ok](docs/a.md)\n")
        _write(tmp_path, "docs/a.md", "# A\n")
        code = gate.main(["--root", str(tmp_path), "--json"])
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        for key in (
            "root",
            "scanned_files",
            "files_by_area",
            "links_total",
            "internal_links",
            "external_links",
            "image_links",
            "file_links",
            "directory_links",
            "anchor_links",
            "line_anchor_links",
            "allowlist_hits",
            "errors",
            "warnings",
            "ok",
        ):
            assert key in payload
        assert payload["scanned_files"] == 2
        assert payload["ok"] is True
        assert payload["errors"] == []

    def test_json_exit_code_on_error(self, tmp_path, capsys):
        _write(tmp_path, "README.md", "[坏](missing.md)\n")
        code = gate.main(["--root", str(tmp_path), "--json"])
        assert code == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False
        assert len(payload["errors"]) == 1

    def test_non_strict_passes_warning(self, tmp_path):
        _write(tmp_path, "README.md", "# 文档\n\n[坏锚](#不存在的标题)\n")
        assert gate.main(["--root", str(tmp_path)]) == 0

    def test_strict_fails_on_warning(self, tmp_path, capsys):
        _write(tmp_path, "README.md", "# 文档\n\n[坏锚](#不存在的标题)\n")
        assert gate.main(["--root", str(tmp_path), "--strict"]) == 1
        assert "strict" in capsys.readouterr().out


class TestFailClosed:
    def test_empty_scan_surface_fails(self, tmp_path):
        """扫描面为空必须失败——防文档被误删 / glob 写错导致门禁静默通过。"""
        assert gate.main(["--root", str(tmp_path)]) == 1

    def test_allow_empty_flag(self, tmp_path):
        assert gate.main(["--root", str(tmp_path), "--allow-empty"]) == 0

    def test_main_without_root_scans_real_repo(self, capsys):
        code = gate.main([])
        assert code == 0
        assert "文档链接完整性检查通过" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 9. 当前真实仓库回归锁定
# ---------------------------------------------------------------------------


class TestCurrentRepo:
    def test_current_repo_has_zero_broken_links(self):
        """扫描面内坏链清零（修复后回归锁定；新增坏链会让本用例变红）。"""
        result = gate.scan()
        assert result.errors == [], f"文档坏链: {[(e.source, e.line, e.target) for e in result.errors]}"
        assert result.strict_warnings == []

    def test_current_repo_scan_surface_sanity(self):
        """扫描面规模下限：门禁必须真的扫到全部文档（防退化为空扫）。"""
        result = gate.scan()
        assert result.stats.files >= 100
        assert result.stats.links_total >= 400
        assert result.stats.external_links >= 1
        assert result.stats.files_by_area.get("root", 0) >= 10
        assert result.stats.files_by_area.get("docs", 0) >= 80
        assert result.stats.files_by_area.get("examples", 0) >= 4

    def test_scan_surface_excludes_changelog_sources(self):
        result = gate.scan()
        scanned = gate.iter_doc_files(PROJECT_ROOT)
        rels = {p.relative_to(PROJECT_ROOT).as_posix() for p in scanned}
        assert "CHANGELOG.md" not in rels
        assert "CHANGELOG.en.md" not in rels
        assert not any(rel.startswith("docs/history/") for rel in rels)
        assert "README.md" in rels
        assert "docs/INDEX.md" in rels
        # 扫描数 = 目录枚举数（统计口径可枚举复算）
        assert result.stats.files == len(rels)
