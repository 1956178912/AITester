"""DB/DE（2026-10-26）：BibTeX 引用库可编译性守卫的测试锁。

## 为什么这道锁存在

DB 轮给 `paper/tex/refs.bib` 增条目时，在**百分号注释**里写了 `pass@1`
（量子代码基准的指标名）。BibTeX 0.99e 的行为是：**在百分号注释里遇到 at
符号会重新开始扫描条目**，于是 `pass@1` 被读成「条目类型 `1`」，报

    You're missing an entry type---line 659 of file refs.bib

并**跳过该行之后的全部条目**。这个缺陷有三个让它「适合被一道锁钉住」的性质：

1. **不阻断 PDF 生成**：pdflatex 三遍退出码全是 0，PDF 照样产出、0 未定义引用。
   只有 bibtex 的退出码是 2，而 bibtex 只是三遍链的中间一步。
2. **失败是部分成功**：之前的条目照常进 .bbl，之后的条目被丢 ⇒ PDF 少了参考
   文献，却看不出少了哪一条（本轮实测 refs.bib 72→79 条，PDF 少进 1 条）。
3. **修复它的人会再犯**：本轮第一次修复把解释写进注释，注释里又带 at 符号 ⇒
   同一个错误立刻重现。人眼在这里完全不可靠。

## 判据（DE 轮加严）

- 门禁在 refs.bib 干净时 rc=0；
- 注入注释 at 符号陷阱后 rc=1（**真实编译**与**静态扫描**两条通道任一命中即红）；
- 静态扫描覆盖**行内/尾随注释**，但**不**误报字段值里的字面 `%`
  （实测 `note={100% pass@1}` 编译 rc=0）；
- 真实探针用 `\\citation{*}` + **逐键 .bbl 哨兵**证明每个条目都经过样式处理，
  不再用一个虚构 `\\citation{probe}` 制造假绿；
- spbasic.bst 缺席 ⇒ rc=1（不得静默退化到 plain）；
- timeout / OSError 结构化披露，不抛栈；
- refs.bib 缺席时：默认档 rc=0 且按 [SKIP] 披露（双盲纪律优先于 CI 覆盖率）；
  `--require-paper` 档 rc=1（缺席 ≠ 通过）；fresh-clone 行为单独上锁。
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GATE = PROJECT_ROOT / "scripts" / "gates" / "check_bibtex_compilability.py"


def _load_gate():
    """按文件路径加载门禁模块（门禁不在包内，无相对 import）。"""
    spec = importlib.util.spec_from_file_location("check_bibtex_compilability", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass + `from __future__ import annotations` 在动态加载时要求模块
    # 已在 sys.modules 里，否则 dataclasses 解析类型注解会拿到 None。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


def _run(*args: str, cwd: Path = PROJECT_ROOT, script: Path = GATE) -> subprocess.CompletedProcess[str]:
    """跑门禁脚本本体（走 CLI，验证退出码契约）。"""
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )


def _skip_without_bibtex(gate):
    if gate._bibtex_binary() is None:
        pytest.skip("本环境无 bibtex（TeX 发行版缺席）——静态扫描通道仍然生效")


class TestStaticScan:
    """静态扫描：注释区里的 at 符号即命中。"""

    def test_comment_with_at_sign_is_flagged(self, gate):
        hits = gate._static_scan("% 指标名 pass@1 从 0% 抬到 94.1%\n")
        assert len(hits) == 1, hits
        assert hits[0][0] == 1

    def test_clean_comment_is_not_flagged(self, gate):
        assert gate._static_scan("% 评测器设计决定分数：pass at 1 从 0% 抬到 94.1%\n") == []

    def test_at_sign_in_entry_body_is_not_flagged(self, gate):
        """at 符号在**条目体内**是正常的（`@misc{...}`），只有注释区才危险。"""
        text = "@misc{key,\n  title = {X},\n  note = {arXiv:2601.12345}\n}\n"
        assert gate._static_scan(text) == []

    def test_entry_body_at_sign_not_flagged_even_with_percent(self, gate):
        text = "% 头注释\n@misc{key,\n  title = {A},\n  note = {arXiv:2601.12345}\n}\n"
        assert gate._static_scan(text) == []

    def test_indented_comment_is_flagged(self, gate):
        """缩进后的注释同样是注释行——BibTeX 不看缩进。"""
        hits = gate._static_scan("    % 注释里的 pass@1\n")
        assert len(hits) == 1, hits

    def test_at_sign_outside_comment_is_not_flagged(self, gate):
        """非注释行里的 at 符号不归本门禁管（那是 BibTeX 的条目起始符）。"""
        assert gate._static_scan("@misc{key, title={X}}\n") == []

    def test_trailing_comment_after_entry_is_flagged(self, gate):
        """DE 轮：尾随注释同样会触发 BibTeX 重启扫描（实测 rc=2）。"""
        text = "@misc{alpha, title={A}} % pass@1\n@misc{beta, title={B}}\n"
        hits = gate._static_scan(text)
        assert len(hits) == 1, hits
        assert "@" in hits[0][1]

    def test_inline_comment_before_entry_is_flagged(self, gate):
        """DE 轮：非行首的注释区也算（`ignored text % pass@1`，实测 rc=2）。"""
        text = "ignored text % pass@1\n@misc{alpha, title={A}}\n"
        assert len(gate._static_scan(text)) == 1

    def test_comment_inside_entry_is_flagged(self, gate):
        """条目体内、字段之间的 `%` 是注释（实测 bibtex 报 missing field name）。"""
        text = "@misc{alpha,\n  title={A},\n  % pass@1\n  note={n}\n}\n"
        assert len(gate._static_scan(text)) == 1

    def test_percent_inside_braced_field_is_literal(self, gate):
        """字段值括号内的 `%` 是字面量（实测 `note={100% pass@1}` 编译 rc=0）。"""
        text = "@misc{alpha,\n  title={A},\n  note={100% pass@1}\n}\n"
        assert gate._static_scan(text) == []

    def test_percent_inside_quoted_field_is_literal(self, gate):
        """引号值内的 `%` 同样是字面量，不应误报。"""
        text = '@misc{alpha,\n  title={A},\n  note="100% pass@1"\n}\n'
        assert gate._static_scan(text) == []

    def test_escaped_percent_is_not_a_comment(self, gate):
        """`\\%`（奇数反斜杠）是字面百分号，不是注释起点。"""
        assert gate._static_scan(r"\% pass@1" + "\n") == []

    def test_even_backslashes_before_percent_are_a_comment(self, gate):
        """`\\\\%`（偶数反斜杠）里的 `%` 才是注释起点。"""
        assert len(gate._static_scan("\\\\% pass@1\n")) == 1

    def test_non_entry_types_are_not_counted_as_entries(self, gate):
        """@comment / @string / @preamble 不是数据库条目。"""
        text = "@comment{not an entry}\n@string{foo = {bar}}\n@misc{real, title={R}}\n"
        assert gate._entry_keys(text) == ["real"]


class TestRealCompileProbe:
    """真实编译探针：门禁必须**真跑 bibtex**，不靠正则猜测。

    环境守卫（2026-10-31）：探针依赖 `paper/tex/spbasic.bst` 样式文件，
    而 `paper/` 不入库（私有投稿仓）——fresh clone / CI 无此文件时探针
    报 `样式文件缺席`（status=error），3 例全红。与 require_full_corpus
    同款纪律：前提不成立显式 skip 并带原因，不把「没跑」折成「跑过且
    通过」；本地检出（paper/ 在盘）时照常真编译。
    """

    _STYLE_FILE = PROJECT_ROOT / "paper" / "tex" / "spbasic.bst"

    def setup_method(self) -> None:
        if not self._STYLE_FILE.exists():
            pytest.skip(
                "paper/tex/spbasic.bst 缺席（paper/ 不入库，fresh clone/CI 无此文件）——真实编译探针需本地 paper 检出"
            )

    def test_probe_detects_at_sign_trap(self, gate):
        """注入陷阱 ⇒ 探针失败（这是本门禁存在的根本理由）。"""
        _skip_without_bibtex(gate)
        bib = "% 指标 pass@1 从 0% 抬到 94.1%\n@misc{alpha, title={A}}\n"
        result = gate._compile_probe(bib)
        assert result.status == "fail", result
        assert "missing an entry type" in result.output

    def test_probe_passes_clean_bib_with_bbl_sentinel(self, gate):
        """干净 bib：两条真实条目都必须经过样式并进入 .bbl。"""
        _skip_without_bibtex(gate)
        bib = "@misc{alpha, author={A}, title={A}, year={2026}}\n@misc{beta, author={B}, title={B}, year={2026}}\n"
        result = gate._compile_probe(bib)
        assert result.ok, result
        assert (result.entries, result.bibitems) == (2, 2)

    def test_probe_fails_when_a_declared_key_never_reaches_bbl(self, gate, monkeypatch):
        """逐键哨兵必须咬：声明了但 .bbl 里没有的键 ⇒ fail（不是只看退出码）。"""
        _skip_without_bibtex(gate)
        monkeypatch.setattr(gate, "_entry_keys", lambda _text: ["alpha", "ghost"])
        result = gate._compile_probe("@misc{alpha, author={A}, title={A}, year={2026}}\n")
        assert result.status == "fail", result
        assert "ghost" in result.reason

    def test_missing_bst_fails_closed(self, gate, tmp_path):
        """样式缺席不得静默退化到 plain（DE 轮高优先级缺陷）。"""
        result = gate._compile_probe("@misc{alpha, title={A}}\n", bst=tmp_path / "absent.bst")
        assert result.status == "error", result
        assert "样式文件缺席" in result.reason

    def test_empty_bib_is_an_error_not_a_pass(self, gate, tmp_path):
        # EZ 轮（2026-10-27）：旧版不传 bst，走仓库内的 paper/tex/spbasic.bst——
        # fresh clone 没有 paper/（.gitignore 双盲纪律），于是先返回「样式文件缺席」，
        # CI 三个 Python 版本同红。空库判定不该依赖稿件树：显式给一个临时 bst。
        bst = tmp_path / "probe.bst"
        bst.write_text("% minimal bst for the empty-bib path\n", encoding="utf-8")
        result = gate._compile_probe("% only a comment\n", bst=bst)
        assert result.status == "error", result
        assert "没有可探测" in result.reason

    def test_empty_bib_check_does_not_require_paper_tree(self, gate, tmp_path, monkeypatch):
        """护栏：仓库 BST 缺席（= fresh clone）时，空库判定的结论必须不变。"""
        monkeypatch.setattr(gate, "BST", tmp_path / "absent.bst")
        bst = tmp_path / "probe.bst"
        bst.write_text("% minimal bst\n", encoding="utf-8")
        result = gate._compile_probe("% only a comment\n", bst=bst)
        assert result.status == "error", result
        assert "没有可探测" in result.reason

    def test_timeout_is_structured(self, gate, monkeypatch, tmp_path):
        """timeout 不抛栈，转成结构化 error。"""
        bst = tmp_path / "fake.bst"
        bst.write_text("% fake bst\n", encoding="utf-8")
        monkeypatch.setattr(
            gate.subprocess,
            "run",
            lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd="bibtex", timeout=120)),
        )
        result = gate._compile_probe("@misc{alpha, title={A}}\n", bibtex="/bin/true", bst=bst)
        assert result.status == "error", result
        assert "超时" in result.reason

    def test_oserror_is_structured(self, gate, monkeypatch, tmp_path):
        """启动失败不抛栈，转成结构化 error。"""
        bst = tmp_path / "fake.bst"
        bst.write_text("% fake bst\n", encoding="utf-8")

        def _boom(*_a, **_k):
            raise OSError("no such binary")

        monkeypatch.setattr(gate.subprocess, "run", _boom)
        result = gate._compile_probe("@misc{alpha, title={A}}\n", bibtex="/bin/true", bst=bst)
        assert result.status == "error", result
        assert "启动失败" in result.reason


class TestCliContract:
    """退出码契约：默认档与 require-paper 档的差别必须存在。"""

    def test_missing_paper_default_is_skip_and_zero(self, tmp_path, monkeypatch, gate):
        """稿件缺席：默认档 rc=0 且按 [SKIP] 披露（双盲纪律优先于 CI 覆盖率）。"""
        monkeypatch.setattr(gate, "BIB", tmp_path / "absent.bib")
        assert gate.main([]) == 0

    def test_missing_paper_require_flag_is_red(self, tmp_path, monkeypatch, gate):
        """--require-paper：缺席即红（无法验证 ≠ 通过）。"""
        monkeypatch.setattr(gate, "BIB", tmp_path / "absent.bib")
        assert gate.main(["--require-paper"]) == 1

    def test_fresh_clone_default_skips_and_require_paper_red(self, tmp_path):
        """Fresh clone（paper/ 不在场）的**真实 CLI** 行为锁。

        DB 轮的门禁只在 monkeypatch 下测过缺席路径；本例把脚本复制到一棵
        没有 `paper/` 的临时树里跑，证明 CI clone 的行为是
        「默认 rc=0 + [SKIP]」「--require-paper rc=1」，而不是恒绿。
        """
        root = tmp_path / "fresh"
        script = root / "scripts" / "gates" / GATE.name
        script.parent.mkdir(parents=True)
        shutil.copy2(GATE, script)
        default = _run(cwd=root, script=script)
        assert default.returncode == 0, default.stdout + default.stderr
        assert "[SKIP]" in default.stdout and "双盲纪律" in default.stdout
        strict = _run("--require-paper", cwd=root, script=script)
        assert strict.returncode == 1, strict.stdout + strict.stderr

    def test_real_repo_bib_is_clean(self):
        """真实 `paper/tex/refs.bib`（在稿件在场时）必须干净。"""
        if not (PROJECT_ROOT / "paper" / "tex" / "refs.bib").exists():
            pytest.skip("paper/ 不入库（双盲纪律）——判据仅在本地稿件在场时执行")
        result = _run()
        assert result.returncode == 0, result.stdout + result.stderr
        assert "静态扫描" in result.stdout

    def test_list_flag_is_read_and_keeps_verdict(self):
        """`--list` 是**呈现档**：它多打明细，但**不改变退出码**。

        本轮实测：`check_invocation_caliber` 把它归入**判据档**（`--list` 在其
        判据档白名单里），于是「无读者」要记红。此处显式钉住它的行为——
        带 `--list` 与不带的退出码必须一致 ⇒ 证明它不改变判定方向，
        同时让该开关在本文件里**有代码锁**（点名这道门 + 出现该开关）。
        """
        if not (PROJECT_ROOT / "paper" / "tex" / "refs.bib").exists():
            pytest.skip("paper/ 不入库（双盲纪律）——判据仅在本地稿件在场时执行")
        plain = _run()
        listed = _run("--list")
        assert plain.returncode == listed.returncode == 0, (plain.stdout, listed.stdout)
        assert "命中明细结束" in listed.stdout, listed.stdout

    def test_gate_file_exists(self):
        """门禁文件本身必须在场（否则「门禁不存在」与「门禁通过」不可区分）。"""
        assert GATE.exists(), f"门禁缺失：{GATE}"
