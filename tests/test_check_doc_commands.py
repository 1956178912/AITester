#!/usr/bin/env python3
"""`scripts/gates/check_doc_commands.py` 的回归锁定（CU 轮，2026-10-26）。

## 为什么需要它

CS 轮实测抓到一处**登记面失实**：引用键快照写着「重跑导出脚本」，而**那个脚本并不存在**
——文档指向不存在的工件，维护者按文档操作必然落空。CK 轮同型（`CITATION.cff` 写
「已备：zenodo_metadata.json」，该文件不在盘）。这类失实没有任何机制能发现：链接检查器
只查 markdown 链接，不查代码块里的命令。

CU 轮把它变成可执行判据，并在固化过程中把两类**误报**也变成判据的一部分：

1. 英文散文里的 "make the same direction" / "make sure the `target_file` path is correct"
   ——不是命令；
2. `> ` 引言块里的内容——那是 Markdown 引用，不是 shell 提示符。

测试用 tmp_path 微型仓库夹具，不依赖真实文档。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gates" / "check_doc_commands.py"
_spec = importlib.util.spec_from_file_location("_check_doc_commands", _SCRIPT)
assert _spec and _spec.loader
doc_mod = importlib.util.module_from_spec(_spec)
sys.modules["_check_doc_commands"] = doc_mod
_spec.loader.exec_module(doc_mod)


def _make_repo(tmp_path: Path, readme: str, makefile: str = "lint:\n\techo lint\n") -> Path:
    root = tmp_path / "repo"
    (root / "scripts" / "tools").mkdir(parents=True)
    (root / "scripts" / "tools" / "real_tool.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "Makefile").write_text(makefile, encoding="utf-8")
    (root / "README.md").write_text(readme, encoding="utf-8")
    return root


def test_existing_refs_pass(tmp_path):
    root = _make_repo(
        tmp_path,
        "# T\n\n```bash\npython scripts/tools/real_tool.py\nmake lint\n```\n",
    )
    result = doc_mod.check(root)
    assert result["missing"] == [], result["missing"]
    assert result["checked"] >= 2


def test_missing_script_is_reported(tmp_path):
    root = _make_repo(
        tmp_path,
        "# T\n\n```bash\npython scripts/tools/ghost.py\n```\n",
    )
    result = doc_mod.check(root)
    assert [m["kind"] for m in result["missing"]] == ["script"], result["missing"]
    assert "ghost.py" in result["missing"][0]["ref"]


def test_missing_make_target_is_reported(tmp_path):
    root = _make_repo(
        tmp_path,
        "# T\n\n```bash\nmake no-such-target\n```\n",
    )
    result = doc_mod.check(root)
    assert [m["kind"] for m in result["missing"]] == ["make-target"], result["missing"]
    assert result["missing"][0]["ref"] == "make no-such-target"


def test_prose_with_make_is_not_a_command(tmp_path):
    """英文散文里的 "make the same direction" / "make sure ..." 不是命令。"""
    root = _make_repo(
        tmp_path,
        "# T\n\nSeveral 2026 studies reach the same direction. **Fix**: make sure the "
        "`target_file` path is correct, or check the module configuration.\n",
    )
    result = doc_mod.check(root)
    assert result["missing"] == [], result["missing"]


def test_blockquote_line_is_not_a_command(tmp_path):
    """`> ` 引言块不是 shell 提示符——里面的 make 不算命令。"""
    root = _make_repo(
        tmp_path,
        "> Last updated: 2026-10-26 (**CT round: several studies reach the same direction**)\n",
    )
    result = doc_mod.check(root)
    assert result["missing"] == [], result["missing"]


def test_make_with_flags_reports_full_target(tmp_path):
    """`make <target> --flag`：目标名要完整取出，且存在的目标带 flag 不该被报。"""
    root = _make_repo(
        tmp_path,
        "# T\n\n```bash\nmake lint --strict\nmake no-such-target --strict\n```\n",
        makefile="lint:\n\techo lint\n",
    )
    result = doc_mod.check(root)
    assert [m["ref"] for m in result["missing"]] == ["make no-such-target"], result["missing"]


def test_glued_heading_is_reported(tmp_path):
    """标题粘在上一段末尾（不在行首）⇒ ATX 标题根本不会生效 ⇒ 判红。

    CV 轮实测到一处真实粘连：CU 轮补记的标题被粘在上一段末尾，整节被渲染成
    上一段的延续。
    """
    root = _make_repo(tmp_path, "# T\n")
    readme = root / "README.md"
    readme.write_text("段落末尾### 粘连标题\n", encoding="utf-8")
    problems = doc_mod._heading_structure_problems(readme)
    assert problems, "行内粘连的标题未被报出"
    assert problems[0]["kind"] == "heading-not-at-line-start", problems


def test_heading_without_blank_line_before_is_only_disclosed(tmp_path):
    """标题在行首但前一行不是空行 ⇒ **只披露，不阻断**。

    GitHub 仍会把它渲染成标题（只是段落与标题之间没有分隔）；真正让渲染失效的是
    「标题不在行首」。CV 轮第一版判据把这一形态当阻断，负例不红——阻断条件必须
    对准失效的那一种形态。
    """
    root = _make_repo(tmp_path, "# T\n")
    readme = root / "README.md"
    readme.write_text("段落末尾\n## 标题\n", encoding="utf-8")
    problems = doc_mod._heading_structure_problems(readme)
    assert problems == [], "前无空行不应阻断"
    assert doc_mod._LAST_DISCLOSURES, "前无空行应记入披露级问题"
    assert doc_mod._LAST_DISCLOSURES[0]["kind"] == "heading-no-blank-before", doc_mod._LAST_DISCLOSURES


def test_hash_comment_inside_code_fence_is_not_a_heading(tmp_path):
    """代码围栏内的 `#` 注释不是标题（bash 注释以 # 开头）。"""
    root = _make_repo(tmp_path, "# T\n")
    readme = root / "README.md"
    readme.write_text("```bash\n# a normal shell comment\n## not a heading\n```\n", encoding="utf-8")
    assert doc_mod._heading_structure_problems(readme) == []


def test_inline_code_hash_is_not_a_heading(tmp_path):
    """行内代码里的 `##` 不是标题。"""
    root = _make_repo(tmp_path, "# T\n")
    readme = root / "README.md"
    readme.write_text("见 `## 14` 一节。\n", encoding="utf-8")
    assert doc_mod._heading_structure_problems(readme) == []


def test_scanner_finds_the_real_documents():
    """扫描面塌了要当场红——否则判据会在空集上「零用例通过」。"""
    root = doc_mod.PROJECT_ROOT
    files = doc_mod._doc_files(root)
    names = {p.name for p in files}
    assert "README.md" in names, names
    assert len(files) >= 6, len(files)


def test_real_repository_has_no_broken_refs():
    """真树：文档引用的脚本与 make 目标必须全部存在。

    DD 轮（2026-10-26）文档重写后实测 checked=15（旧门面中的长命令清单随叙事
    一并退役）。下限按实测 −20% 设为 12：防扫描面塌陷，不防命令密度下降。
    """
    result = doc_mod.check(doc_mod.PROJECT_ROOT)
    assert result["missing"] == [], result["missing"]
    assert result["checked"] >= 12, result["checked"]


def test_main_exit_codes(tmp_path, capsys):
    root = _make_repo(tmp_path, "# T\n\n```bash\nmake ghost\n```\n")
    assert doc_mod.main(["--root", str(root)]) == 1
    assert "ghost" in capsys.readouterr().out
