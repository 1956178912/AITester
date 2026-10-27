"""FE 轮（2026-10-27）：审计的「未测量 ≠ 零缺口」守卫必须被真锁钉住。

## 为什么需要它

FE 轮给 `scripts/tools/audit_fix_coverage.py` 加了「作用域内存在未被 coverage
测量的文件 ⇒ rc=1」的守卫（改前整片未测量被读成「新增 0 / 未执行 0 / 0.00%」
并以 rc=0 通过——与 FC 轮 champion 守卫「无观测被读作 0」同族）。

但**守卫本身没有配套测试**：变异验证实测，把 `if result.get("total_unmeasured_files")`
改成 `if False`、或把 `unmeasured_files.append(rel)` 换成 `pass` 后，
全套测试**仍然全绿**——守卫是装饰品，删掉无人知晓。本文件把它钉死。

## 判据

1. **audit 层**：coverage.xml 缺某新增文件的条目 ⇒ 该文件单列为「未测量」，
   其新增行**不进分母**（分母只含真被测量的行）；
2. **CLI 层（main）**：作用域内存在未测量文件 ⇒ rc=1 + stderr 点名
   「未测量不等于零缺口」；
3. **负对照**：coverage.xml 覆盖全部新增文件 ⇒ rc=0（守卫不是无条件红）；
4. **render**：未测量清单必须在人类可读输出里单列（不藏在 JSON 里）。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "audit_fix_coverage.py"
_spec = importlib.util.spec_from_file_location("_audit_fix_coverage_fe", _SCRIPT)
assert _spec and _spec.loader
fix_mod = importlib.util.module_from_spec(_spec)
sys.modules["_audit_fix_coverage_fe"] = fix_mod
_spec.loader.exec_module(fix_mod)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _make_repo_with_unmeasured_file(tmp_path: Path) -> tuple[Path, str, Path]:
    """两提交微仓：第二提交既改被测文件、又新增一个 coverage 不会测的文件。

    commit1: ``src/a.py = "x = 1\\n"``
    commit2: ``src/a.py`` 增两行（y=2 / z=3）+ 新增 ``src/b.py``（p=1 / q=2）。
    coverage.xml **只**含 a.py 的行 ⇒ b.py 就是「未测量」文件。
    """
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "first")
    first = _git(root, "rev-parse", "HEAD")
    (root / "src" / "a.py").write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")
    (root / "src" / "b.py").write_text("p = 1\nq = 2\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "second")
    return root, first, None


def _coverage_xml(root: Path, classes: dict[str, dict[int, int]]) -> Path:
    """写最小 coverage.xml：classes = {filename: {行: hits}}。"""
    body = "".join(
        f'    <class filename="{name}"><lines>'
        + "".join(f'<line number="{n}" hits="{h}"/>' for n, h in sorted(lines.items()))
        + "</lines></class>\n"
        for name, lines in classes.items()
    )
    xml = root / "coverage.xml"
    xml.write_text(
        '<?xml version="1.0" ?>\n'
        '<coverage line-rate="0.5" branch-rate="1.0">\n'
        "  <packages><package><classes>\n" + body + "  </classes></package></packages>\n"
        "</coverage>\n",
        encoding="utf-8",
    )
    return xml


class TestAuditLevelUnmeasuredClassification:
    """audit() 的分类行为：未测量文件单列、不进分母。"""

    def test_unmeasured_file_is_listed_not_zeroed(self, tmp_path: Path) -> None:
        """coverage.xml 缺 b.py ⇒ b.py 单列为未测量（不得被记成「新增 0 / 缺口 0」）。"""
        root, first, _ = _make_repo_with_unmeasured_file(tmp_path)
        xml = _coverage_xml(root, {"a.py": {1: 1, 2: 0, 3: 0}})

        result = fix_mod.audit(first, xml, root, "src/", registry_path=None)

        assert result["unmeasured_files"] == ["src/b.py"], "未测量文件必须被点名"
        assert result["total_unmeasured_files"] == 1
        assert result["total_unmeasured_added_lines"] == 2, "b.py 的两行新增从未被测过"

    def test_unmeasured_lines_do_not_enter_the_denominator(self, tmp_path: Path) -> None:
        """分母只含真被测量的行——b.py 的行不得计入 total_added。"""
        root, first, _ = _make_repo_with_unmeasured_file(tmp_path)
        xml = _coverage_xml(root, {"a.py": {1: 1, 2: 0, 3: 0}})

        result = fix_mod.audit(first, xml, root, "src/", registry_path=None)

        # a.py 新增行 2、3 都在 coverage 里；b.py 的 1、2 行不得混进分母。
        assert result["total_added"] == 2, f"分母必须只含被测量的行，实际 {result['total_added']}"
        item_b = next(f for f in result["files"] if f["file"] == "src/b.py")
        assert item_b["unmeasured"] is True
        assert item_b["unmeasured_lines"] == 2
        assert item_b["added"] == 0 and item_b["uncovered"] == 0

    def test_unmeasured_disclosed_in_render(self, tmp_path: Path) -> None:
        """人类可读输出必须单列未测量清单（读者不能只看 JSON）。"""
        root, first, _ = _make_repo_with_unmeasured_file(tmp_path)
        xml = _coverage_xml(root, {"a.py": {1: 1, 2: 0, 3: 0}})

        text = fix_mod.render(fix_mod.audit(first, xml, root, "src/", registry_path=None))

        assert "未被 coverage 测量" in text
        assert "src/b.py" in text
        assert "未计入分母" in text


class TestCliLevelUnmeasuredGuard:
    """main() 的 rc 判定：未测量 ⇒ rc=1（变异锚点 G1）。"""

    def test_unmeasured_file_fails_closed(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """作用域内存在未测量文件 ⇒ rc=1 + stderr 点名「未测量不等于零缺口」。

        变异锚点：把 main() 里的 ``if result.get("total_unmeasured_files"):``
        改成 ``if False:`` 后，本例必须转红（rc 变 0）。
        """
        root, first, _ = _make_repo_with_unmeasured_file(tmp_path)
        xml = _coverage_xml(root, {"a.py": {1: 1, 2: 0, 3: 0}})
        registry = tmp_path / "empty_registry.txt"
        registry.write_text("", encoding="utf-8")

        monkeypatch.setattr(fix_mod, "PROJECT_ROOT", root)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "audit_fix_coverage.py",
                "--base",
                first,
                "--coverage-xml",
                str(xml),
                "--registry",
                str(registry),
            ],
        )
        rc = fix_mod.main()
        err = capsys.readouterr().err

        assert rc == 1, "存在未测量文件必须判红（判决的输入不完整 ⇒ 判决不可信）"
        assert "未被 coverage 测量" in err
        assert "未测量" in err and "零缺口" in err, "报错必须写明「未测量 ≠ 零缺口」"

    def test_fully_measured_scope_passes(self, tmp_path: Path, monkeypatch) -> None:
        """负对照：coverage 覆盖全部新增文件 ⇒ rc=0（守卫不是无条件红）。

        若守卫把「测量齐全」也判红，审计就没法正常收尾——负对照钉住这个方向。
        """
        root, first, _ = _make_repo_with_unmeasured_file(tmp_path)
        xml = _coverage_xml(root, {"a.py": {1: 1, 2: 0, 3: 0}, "b.py": {1: 1, 2: 1}})
        registry = tmp_path / "empty_registry.txt"
        registry.write_text("", encoding="utf-8")

        monkeypatch.setattr(fix_mod, "PROJECT_ROOT", root)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "audit_fix_coverage.py",
                "--base",
                first,
                "--coverage-xml",
                str(xml),
                "--registry",
                str(registry),
            ],
        )
        result = fix_mod.audit(first, xml, root, "src/", registry_path=registry)
        assert result["total_unmeasured_files"] == 0, "测量齐全时不得报未测量"

        rc = fix_mod.main()
        assert rc == 0, f"测量齐全（缺口照报、登记齐全）必须 rc=0，实际 {rc}"
