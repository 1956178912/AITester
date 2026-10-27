"""FD 轮（2026-10-27）：修复覆盖率审计的判决面必须区分「真缺口」与「已在本进程之外验证」。

## 为什么需要它

`scripts/tools/audit_fix_coverage.py` 的判决面是**父进程**的 `coverage.xml`。
而 ED 轮那批「可选依赖装上但坏了」的负控制是在**子进程**里跑的
（`tests/test_optional_backend_broken_ed.py` 用 `builtins.__import__` 替换，
把目标包变成 RuntimeError 后验证降级契约）——子进程的执行对父进程 coverage
**不可见**。于是审计把**已验证**的 9 行（datasets / chromadb / hypothesis / z3
的导入期降级分支）报成「修复新增但从未被测试执行」。

判决不可信 ⇒ 无人看。该工具自己的 docstring 记着它「长期无人跑」的主因就是
输出是噪声（CS 轮修了基线，但没修这个盲区）。

## 判据

1. **登记表**（`docs/fix_coverage_verified_elsewhere.txt`）：语法
   `<路径>:<行号> @<内容锚点>  # <理由>`；每条必须写理由；锚点在该文件里消失 ⇒
   登记**失效**（内容改了 = 契约可能变了，必须重新判定）。
2. **分类**：登记在册的未覆盖行从「缺口」移出，单列为「已在本进程之外验证」；
   **未登记**的未覆盖行仍是缺口（分类不得变成橡皮章）。
3. **失效判红**：登记表畸形或失效 ⇒ 审计 rc=1（登记完整性是判决的输入）。
4. **锚点不用行号当键**：行号会随上方插行漂移（FA 轮为此付过代价）。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "audit_fix_coverage.py"
_spec = importlib.util.spec_from_file_location("_audit_fix_coverage", _SCRIPT)
assert _spec and _spec.loader
fix_mod = importlib.util.module_from_spec(_spec)
sys.modules["_audit_fix_coverage"] = fix_mod
_spec.loader.exec_module(fix_mod)

REAL_REGISTRY = Path(__file__).resolve().parents[1] / "docs" / "fix_coverage_verified_elsewhere.txt"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _make_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """造一个两提交的微型仓库：src/a.py 第 1 行被覆盖、第 2 行未被覆盖。"""
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
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "second")
    second = _git(root, "rev-parse", "HEAD")
    return root, first, second


def _coverage_xml(root: Path, *, covered: dict[int, int]) -> Path:
    """写一份最小 coverage.xml：`src/a.py` 的行命中数由 covered 决定。"""
    lines = "".join(f'<line number="{n}" hits="{h}"/>' for n, h in sorted(covered.items()))
    xml = root / "coverage.xml"
    xml.write_text(
        '<?xml version="1.0" ?>\n'
        '<coverage line-rate="0.5" branch-rate="1.0">\n'
        "  <packages><package><classes>\n"
        '    <class filename="a.py"><lines>' + lines + "</lines></class>\n"
        "  </classes></package></packages>\n"
        "</coverage>\n",
        encoding="utf-8",
    )
    return xml


class TestRealRegistry:
    """仓库内的真登记表（`docs/fix_coverage_verified_elsewhere.txt`）。"""

    def test_registry_file_exists_and_parses(self) -> None:
        assert REAL_REGISTRY.is_file(), "登记表缺席——判决将无法区分「已验证」与「缺口」"
        entries, errors = fix_mod.load_registry(REAL_REGISTRY)
        assert errors == [], f"登记表畸形：{errors}"
        assert entries, "登记表为空 ⇒ 没有任何路径被登记"

    def test_every_entry_has_a_reason(self) -> None:
        entries, _errors = fix_mod.load_registry(REAL_REGISTRY)
        for (rel, ln), (_anchor, reason) in entries.items():
            assert reason.strip(), f"{rel}:{ln} 缺理由"

    def test_every_entry_anchor_still_exists(self) -> None:
        """锚点内容必须仍在该文件里——内容被改写 ⇒ 登记失效，必须重新判定。"""
        entries, _errors = fix_mod.load_registry(REAL_REGISTRY)
        for (rel, ln), (anchor, _reason) in entries.items():
            target = REPO_ROOT / rel
            assert target.is_file(), f"{rel}:{ln} 登记指向的文件不存在"
            assert anchor in target.read_text(encoding="utf-8"), f"{rel}:{ln} 的锚点已消失（登记失效）"

    def test_registry_entries_are_unique_and_in_src(self) -> None:
        entries, _errors = fix_mod.load_registry(REAL_REGISTRY)
        for rel, ln in entries:
            assert rel.startswith("src/"), f"{rel} 不在审计范围（src/）内"
            assert ln > 0


class TestClassification:
    """分类行为：登记在册 ⇒ 不计缺口；未登记 ⇒ 仍是缺口。"""

    def test_registered_line_is_classified_as_verified_not_gap(self, tmp_path: Path) -> None:
        root, first, _second = _make_repo(tmp_path)
        xml = _coverage_xml(root, covered={1: 1, 2: 0, 3: 0})
        registry = tmp_path / "registry.txt"
        registry.write_text("src/a.py:3 @z = 3  # 在子进程里验证过\n", encoding="utf-8")

        result = fix_mod.audit(first, xml, root, "src/", registry_path=registry)

        assert result["total_verified_elsewhere"] == 1
        assert result["total_uncovered"] == 1, "登记的那一行不得计入缺口"
        assert result["registry_stale"] == []
        item = next(f for f in result["files"] if f["file"] == "src/a.py")
        assert item["missing_lines"] == [2]
        assert item["verified_lines"] == [3]

    def test_unregistered_line_is_still_a_gap(self, tmp_path: Path) -> None:
        """负对照：分类不得把真缺口藏起来。"""
        root, first, _second = _make_repo(tmp_path)
        xml = _coverage_xml(root, covered={1: 1, 2: 0, 3: 0})
        registry = tmp_path / "registry.txt"
        registry.write_text("src/a.py:3 @z = 3  # 在子进程里验证过\n", encoding="utf-8")

        result = fix_mod.audit(first, xml, root, "src/", registry_path=registry)

        assert 2 in next(f for f in result["files"] if f["file"] == "src/a.py")["missing_lines"]

    def test_no_registry_keeps_all_gaps(self, tmp_path: Path) -> None:
        """未启用登记表（None）⇒ 行为与改前一致（全部未覆盖行都是缺口）。"""
        root, first, _second = _make_repo(tmp_path)
        xml = _coverage_xml(root, covered={1: 1, 2: 0, 3: 0})

        result = fix_mod.audit(first, xml, root, "src/", registry_path=None)

        assert result["total_verified_elsewhere"] == 0
        assert result["total_uncovered"] == 2


class TestRegistryIntegrity:
    """登记完整性：畸形或失效 ⇒ 判决不可信 ⇒ 必须判红。"""

    def test_missing_registry_file_is_an_error(self, tmp_path: Path) -> None:
        root, first, _second = _make_repo(tmp_path)
        xml = _coverage_xml(root, covered={1: 1, 2: 0, 3: 0})

        result = fix_mod.audit(first, xml, root, "src/", registry_path=tmp_path / "absent.txt")

        assert result["registry_errors"], "登记表缺席必须被点名（判决的输入没了）"

    def test_malformed_line_is_an_error(self, tmp_path: Path) -> None:
        registry = tmp_path / "registry.txt"
        registry.write_text("src/a.py 3 缺少 @锚点 与 # 理由\n", encoding="utf-8")
        _entries, errors = fix_mod.load_registry(registry)
        assert errors and "语法不符" in errors[0]

    def test_missing_reason_is_an_error(self, tmp_path: Path) -> None:
        registry = tmp_path / "registry.txt"
        registry.write_text("src/a.py:3 @z = 3\n", encoding="utf-8")
        _entries, errors = fix_mod.load_registry(registry)
        assert errors and "缺少理由" in errors[0]

    def test_duplicate_entry_is_an_error(self, tmp_path: Path) -> None:
        registry = tmp_path / "registry.txt"
        registry.write_text("src/a.py:3 @z = 3  # 理由\nsrc/a.py:3 @z = 3  # 另一条理由\n", encoding="utf-8")
        _entries, errors = fix_mod.load_registry(registry)
        assert errors and "重复" in errors[0]

    def test_stale_entry_is_detected(self, tmp_path: Path) -> None:
        """锚点内容已消失 ⇒ 登记失效（内容改了 = 契约可能变了，必须重新判定）。"""
        root, first, _second = _make_repo(tmp_path)
        xml = _coverage_xml(root, covered={1: 1, 2: 0, 3: 0})
        registry = tmp_path / "registry.txt"
        registry.write_text("src/a.py:3 @这段内容不存在  # 理由\n", encoding="utf-8")

        result = fix_mod.audit(first, xml, root, "src/", registry_path=registry)

        assert result["registry_stale"], "锚点消失必须被判定为登记失效"
        assert result["total_verified_elsewhere"] == 0, "失效登记不得继续把缺口藏起来"

    def test_render_discloses_verified_and_stale(self, tmp_path: Path) -> None:
        root, first, _second = _make_repo(tmp_path)
        xml = _coverage_xml(root, covered={1: 1, 2: 0, 3: 0})
        registry = tmp_path / "registry.txt"
        registry.write_text("src/a.py:3 @z = 3  # 在子进程里验证过\n", encoding="utf-8")

        result = fix_mod.audit(first, xml, root, "src/", registry_path=registry)
        text = fix_mod.render(result)

        assert "已在本进程之外验证" in text
        assert "src/a.py" in text
