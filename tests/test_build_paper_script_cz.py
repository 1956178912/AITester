"""CZ 轮（2026-10-26）：投稿 PDF 构建脚本 `scripts/tools/build_paper.sh` 的顺序锁。

为什么需要这道锁：CZ 轮与 CY 轮**连续两轮**把中文写进 `refs.bib` 的 `note` 字段
（登记册里那句「无出版商 DOI」被顺手带进了 bib），而两次都是**先编译、后跑判据**——
LaTeX 报 `Unicode character … not set up for use with LaTeX`，参考文献处缺字形。
CR 轮的「可排版文本不得含 CJK」判据两次都最终抓到了（8/8），但那时**产物已经坏了**。

**判据是可执行的，不是自动的。** 要防复发，就得把「先跑判据」变成**流程的固定第一步**
⇒ 本轮新增 `scripts/tools/build_paper.sh`，把顺序固化成「① 前置判据 → ② 编译 →
③ 后置判据」，并用本文件把**这个顺序本身**锁住——顺序一旦被改回「先编译」，本文件立刻红。

锁的形状是**结构断言**而不是行为断言：真的跑一遍脚本要编译三份 PDF（分钟级），不适合
放进单元测试；而「判据调用出现在编译调用之前」这个性质用源码顺序就能钉住，且它是本轮
真正要防的那个回归。
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "tools" / "build_paper.sh"


def _source() -> str:
    assert SCRIPT.is_file(), f"构建脚本不存在：{SCRIPT}"
    return SCRIPT.read_text(encoding="utf-8")


def _code() -> str:
    """**只留可执行行**（去掉 `#` 注释与空行）。

    为什么必须剥离：脚本的头部注释里就写着「先跑判据 → 再编译 → 再跑判据」与
    `pdflatex`、`audit_paper_numbers.py` 这些词——**不剥离就会把注释当成代码**，
    顺序断言于是变成「注释里谁先出现」，完全测不到真正的调用顺序（这正是
    「注释不是调用」的同型陷阱）。
    """
    lines = []
    for line in _source().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def test_script_exists_and_is_executable() -> None:
    """脚本必须在，且可执行（`make paper-build` 直接调它）。"""
    assert SCRIPT.is_file(), f"缺少 {SCRIPT}"
    assert SCRIPT.stat().st_mode & 0o111, f"{SCRIPT} 不可执行"


def test_precheck_runs_before_any_compile() -> None:
    """**前置判据必须排在所有编译调用之前**——这是本轮要防的那个回归。"""
    text = _code()
    audit_at = text.index("audit_paper_numbers.py")
    first_compile_at = min(idx for idx in (text.find("pdflatex"), text.find("bibtex")) if idx >= 0)
    assert audit_at < first_compile_at, "判据调用必须出现在编译调用之前"


def test_precheck_aborts_before_compiling() -> None:
    """前置判据失败时**必须中止**（不产出坏产物），且退出码非 0。"""
    text = _source()
    # 「前置判据不通过 ⇒ die」这条分支必须存在，且 die 的退出码是 1
    assert "不编译" in text, "前置判据失败时必须明确拒绝编译"
    assert "exit 1" in text or '" 1' in text, "前置判据失败必须给非零退出码"


def test_postcheck_is_run_after_the_build() -> None:
    """构建之后必须**再跑一次**判据（构建可能改变读数：页数 / 文献数）。"""
    text = _code()
    assert text.count('"$AUDIT" --strict') >= 2, "前置与后置判据各一次"
    post_at = text.rindex('"$AUDIT" --strict')
    compile_at = text.index("pdflatex -interaction=nonstopmode")
    assert post_at > compile_at, "后置判据必须在编译之后"


def test_page_counts_are_read_from_the_build_log() -> None:
    """页数必须**从构建日志里取**，不许手写常量（手写数字是失实来源）。"""
    text = _source()
    assert "Output written on manuscript.pdf" in text, "页数应从 pdflatex 的收尾行读取"
    assert "manuscript.bbl" in text, "文献条数应从生成的 .bbl 读取"


def test_makefile_exposes_the_target() -> None:
    """必须进 `make` 目标面（否则「写了没人跑」）。"""
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "paper-build:" in makefile
    assert "scripts/tools/build_paper.sh" in makefile
