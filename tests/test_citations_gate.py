"""CJ 轮：引用核验门 `scripts/gates/check_citations.py` 及其豁免登记面的回归锁。

为什么这些锁必须存在（改前实测，2026-10-25）：
- v0.8.0 数据换代补登记时，12 条豁免键**登记了两遍**（24 行 entry），且文件内
  2026-10-16 写下的「现状：**零豁免**」声明未随补登记更新——登记面失实；
  而 `load_allowlist` 返回 **set**（重复键静默合并），此前全仓没有任何
  测试/门禁读这份清单，重复与失实声明对所有读者不可见；
- 豁免键的**陈旧条目**同样无读者：行号漂移后登记不再命中，没有任何东西计红
  （对照 registration-consistency 门的「条目已失效计红」规则，本登记面
  此前只有「充分性」读者——门自身，没有「承重性」读者）。

分组：A 真实树登记面 5 例（只读真仓库）/ B 合成面判定逻辑 6 例（tmp 合成文本）。
纪律：零 LLM、$0；A 组不写任何仓库文件。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_GATE_SCRIPT = PROJECT_ROOT / "scripts" / "gates" / "check_citations.py"
_ALLOWLIST = PROJECT_ROOT / "docs" / "citation_allowlist.txt"

_KEY_RE = re.compile(r"^[^\s:#]+:\d+$")


def _load_gate():
    spec = importlib.util.spec_from_file_location("aitester_check_citations", _GATE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


@pytest.fixture(scope="module")
def real_allowlist_entries() -> list[str]:
    """真实豁免清单的 entry 行（去注释/空行，**保留重复**）。"""
    out: list[str] = []
    for raw in _ALLOWLIST.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


# ══ A 真实树登记面（只读）══════════════════════════════════════════════


def test_allowlist_raw_entries_have_no_duplicates(gate, real_allowlist_entries):
    """entry 行数 == 去重后行数——直接锁 2026-10-25 的 24 行/12 键重复登记。"""
    assert real_allowlist_entries, "豁免清单不应为空（现状为 12 条登记）"
    assert len(real_allowlist_entries) == len(set(real_allowlist_entries)), (
        f"豁免清单存在重复键：{sorted(k for k in set(real_allowlist_entries) if real_allowlist_entries.count(k) > 1)}"
    )


def test_allowlist_keys_are_well_formed(gate, real_allowlist_entries):
    """每条 entry 解析得出路径/行号，且**必须带内容锚点**（FA 轮起）。

    FA 之前只有 `相对路径:行号`：行号一漂移整表失效（EZ 轮一天内被抓三次）。
    锚点把键从「位置」改成「内容」；这条锁要求真实清单里每条都写锚点，
    不允许回退到纯行号。
    """
    for raw in real_allowlist_entries:
        entry = gate.parse_allow_entry(raw)
        assert entry.line >= 1, f"键形态非法：{raw!r}"
        assert (PROJECT_ROOT / entry.path).is_file(), f"键指向的文件不存在：{entry.path}"
        assert entry.anchor, f"缺少内容锚点（行号不再单独承重）：{raw!r}"
        assert " @" not in entry.anchor, f"锚点内不得再含分隔符：{raw!r}"


def test_load_allowlist_returns_structured_entries(gate):
    """`load_allowlist()` 返回结构体而不是裸字符串——否则锚点无处安放。"""
    entries = gate.load_allowlist(None)
    assert entries, "真实豁免清单不应为空"
    assert all(isinstance(e, gate.AllowEntry) for e in entries)
    assert all(e.anchor for e in entries), "真实清单里应全部带锚点"


def test_allowlist_entries_are_all_load_bearing(gate, real_allowlist_entries):
    """无陈旧条目：每条登记都必须仍能压住一处真实命中。

    判定面与门禁一致：行号命中 **或** 锚点出现在命中行文本里（内容锚点）。
    内容被替换 ⇒ 锚点消失 ⇒ 本锁红（要求重新判定）；仅行号漂移 ⇒ 仍承重。
    """
    findings = gate.scan_traceability(gate.collect_files([]), allowlist=[])
    hit_keys = {f.split(": ", 1)[0] for f in findings}
    hit_texts = [f.split(": ", 1)[1] for f in findings if ": " in f]
    stale = []
    for raw in real_allowlist_entries:
        entry = gate.parse_allow_entry(raw)
        if entry.key in hit_keys:
            continue
        if entry.anchor and any(entry.anchor in text for text in hit_texts):
            continue
        stale.append(raw)
    assert not stale, f"陈旧豁免条目（不再命中，应删除或重新判定）：{stale}"


def test_scan_with_real_allowlist_is_clean(gate):
    """充分性：挂上真实豁免清单后，扫描面零命中（= 门当前的绿）。"""
    allow = gate.load_allowlist(None)
    assert allow, "真实豁免清单不应为空"
    findings = gate.scan_traceability(gate.collect_files([]), allowlist=allow)
    assert findings == [], f"真实豁免清单未覆盖的命中：{findings}"


def test_registration_claim_matches_entry_count(real_allowlist_entries):
    """文件内「现状…**N 条登记**」声明与实况条数一致（防声明失实）。"""
    text = _ALLOWLIST.read_text(encoding="utf-8")
    m = re.search(r"现状（[^）]+）：\*\*(\d+) 条登记", text)
    assert m, "豁免清单缺少「现状…N 条登记」声明行"
    assert int(m.group(1)) == len(real_allowlist_entries), (
        f"声明 {m.group(1)} 条 vs 实况 {len(real_allowlist_entries)} 条"
    )


# ══ B 合成面判定逻辑（tmp 文本）════════════════════════════════════════


def _write(tmp_path: Path, name: str, lines: list[str]) -> Path:
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_numeric_venue_tone_without_traceable_is_flagged(gate, tmp_path):
    """数值 + venue + 文献口吻、邻域无可追溯标识 ⇒ 命中。"""
    doc = _write(
        tmp_path,
        "synthetic.md",
        [
            "# 合成文档",
            "",
            "CANDOR（ICST 2026）one-shot 88.35% 的修复结果由该论文报告。",
            "",
            "后续行无可追溯标识。",
        ],
    )
    findings = gate.scan_traceability([doc], allowlist=set())
    assert findings, "应收敛到该合成命中"
    assert any("synthetic.md" in f for f in findings)


def test_traceable_identifier_in_neighborhood_clears(gate, tmp_path):
    """±3 行邻域内出现 DOI ⇒ 不命中（邻域口径）。"""
    doc = _write(
        tmp_path,
        "synthetic.md",
        [
            "# 合成文档",
            "DOI:10.1109/ICST69053.2026.00040",
            "",
            "CANDOR（ICST 2026）one-shot 88.35% 的修复结果由该论文报告。",
            "",
            "尾行。",
        ],
    )
    assert gate.scan_traceability([doc], allowlist=set()) == []


def test_self_metric_line_is_exempt(gate, tmp_path):
    """项目自身指标行（aitester / BASELINE.yaml 等）直接豁免。"""
    doc = _write(
        tmp_path,
        "synthetic.md",
        [
            "# 合成文档",
            "",
            "aitester 在 ASE 2026 基准上达到 97.4% 覆盖率。",
        ],
    )
    assert gate.scan_traceability([doc], allowlist=set()) == []


def test_allowlist_suppresses_only_the_named_key(gate, tmp_path):
    """豁免只压被点名的键；点名别的行号不生效。"""
    doc = _write(
        tmp_path,
        "synthetic.md",
        [
            "# 合成文档",
            "",
            "CANDOR（ICST 2026）one-shot 88.35% 的修复结果由该论文报告。",
        ],
    )
    exact = gate.parse_allow_entry(f"{doc}:3")
    wrong_line = gate.parse_allow_entry(f"{doc}:99")
    assert gate.scan_traceability([doc], allowlist=[exact]) == []
    assert gate.scan_traceability([doc], allowlist=[wrong_line]) != []


def test_load_allowlist_preserves_duplicates_and_parses_anchors(gate, tmp_path):
    """`load_allowlist` **不再**静默合并重复，且解析出锚点（FA 轮语义变更）。

    旧语义是返回 `set`：重复键被静默合并——那正是「重复登记对读者不可见」的
    根因。现在返回有序条目列表：重复会被
    `test_allowlist_raw_entries_have_no_duplicates` 从文件面抓住，锚点也有处安放。
    """
    p = tmp_path / "allow.txt"
    p.write_text(
        "# 注释\n\ndocs/a.md:1 @标题甲\ndocs/a.md:1 @标题甲\ndocs/b.md:2\n",
        encoding="utf-8",
    )
    entries = gate.load_allowlist(p)
    assert [e.key for e in entries] == ["docs/a.md:1", "docs/a.md:1", "docs/b.md:2"]
    assert entries[0].anchor == "标题甲"
    assert entries[2].anchor is None


def test_collect_files_excludes_internal_manuals(gate):
    """内部参考手册（EXCLUDE_RELS）不进受检面——排除规则有读者。"""
    rels = {p.relative_to(PROJECT_ROOT).as_posix() for p in gate.collect_files([])}
    excluded_present = sorted(gate.EXCLUDE_RELS & rels)
    assert excluded_present == [], f"被排除文件仍进了受检面：{excluded_present}"


def test_out_of_root_file_does_not_crash_gate(gate, tmp_path):
    """仓库外文件（`--files` 绝对路径）不崩栈、正常出具判定（CJ 轮真 bug 修复锁）。

    改前实测：`scan_traceability` 与 main 的离线清单段对仓库外文件调
    `relative_to(PROJECT_ROOT)` 抛**未捕获 ValueError**——`collect_files` 容忍
    仓库外路径（去重键有兜底），扫描段却没有，一条仓库外 `--files` 即整门崩栈。
    改后：判定正常出（本例 1 处命中 ⇒ rc=1）。
    """
    doc = _write(
        tmp_path,
        "outside.md",
        [
            "# 仓库外合成文档",
            "",
            "CANDOR（ICST 2026）one-shot 88.35% 的修复结果由该论文报告。",
        ],
    )
    assert gate.main(["--files", str(doc), "--traceability"]) == 1


def test_out_of_root_clean_file_passes(gate, tmp_path):
    """仓库外干净文件（邻域带 DOI）⇒ rc=0——崩栈修复不只是把红变崩。"""
    doc = _write(
        tmp_path,
        "outside_clean.md",
        [
            "# 仓库外合成文档",
            "DOI:10.1109/ICST69053.2026.00040",
            "",
            "CANDOR（ICST 2026）one-shot 88.35% 的修复结果由该论文报告。",
        ],
    )
    assert gate.main(["--files", str(doc), "--traceability"]) == 0


# ══ C 内容锚点面（FA 轮：键从「位置」改为「内容」）══════════════════════

_FILLER = "填充行（不触发判据）"


def _claim_doc(tmp_path: Path, *, filler: int = 0, claim: str | None = None) -> Path:
    claim = claim or "CANDOR（ICST 2026）one-shot 88.35% 的修复结果由该论文报告。"
    return _write(tmp_path, "anchor.md", ["# 合成文档", *([_FILLER] * filler), claim])


def test_anchor_survives_line_drift_and_discloses_it(gate, tmp_path):
    """锚点命中：行号漂移后仍豁免，且**必须披露**「按锚点命中」（漂移可见）。"""
    doc = _claim_doc(tmp_path, filler=12)
    drifted = gate.parse_allow_entry(f"{doc}:2 @one-shot 88.35% 的修复结果")
    drift: list[str] = []
    assert gate.scan_traceability([doc], allowlist=[drifted], drift_report=drift) == []
    assert drift and "88.35%" in drift[0], f"漂移必须披露：{drift}"

    exact = gate.parse_allow_entry(f"{doc}:14 @one-shot 88.35% 的修复结果")
    no_drift: list[str] = []
    assert gate.scan_traceability([doc], allowlist=[exact], drift_report=no_drift) == []
    assert no_drift == [], f"行号精确命中不应记为漂移：{no_drift}"


def test_line_only_entry_does_not_survive_drift(gate, tmp_path):
    """负向对照：只写行号的条目在漂移后**不再**豁免（锚点才是漂移的承重件）。"""
    doc = _claim_doc(tmp_path, filler=12)
    line_only = gate.parse_allow_entry(f"{doc}:2")
    assert gate.scan_traceability([doc], allowlist=[line_only]) != []


def test_anchor_does_not_survive_content_change(gate, tmp_path):
    """纪律不放松：内容被改写 ⇒ 锚点消失 ⇒ 恢复命中，要求重新判定。

    口径：**同一行号**仍是硬命中（向后兼容，见 `test_allowlist_suppresses_only_the_named_key`）。
    所以「内容变了」这件事要在**行号也变了**（真实改稿的形态：上方插入 + 本行重写）时
    才由锚点判出——这正是要锁的场景。
    """
    doc = _claim_doc(tmp_path, filler=5)
    stale_anchor = gate.parse_allow_entry(f"{doc}:2 @另一篇论文（ICSE 2026）报告的 91.20%")
    assert gate.scan_traceability([doc], allowlist=[stale_anchor]) != []


def test_anchor_is_scoped_to_its_own_path(gate, tmp_path):
    """锚点只在登记的那份文件里生效——跨文件同名文本不得被顺带豁免。"""
    allowed = _claim_doc(tmp_path)
    other = _write(
        tmp_path, "other.md", ["# 另一份文档", _FILLER, allowed.read_text(encoding="utf-8").splitlines()[-1]]
    )
    entry = gate.parse_allow_entry(f"{allowed}:3 @one-shot 88.35% 的修复结果")
    assert gate.scan_traceability([allowed], allowlist=[entry]) == []
    assert gate.scan_traceability([other], allowlist=[entry]) != []
