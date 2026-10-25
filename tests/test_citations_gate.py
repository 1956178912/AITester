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


def test_allowlist_keys_are_well_formed(real_allowlist_entries):
    """每条 entry 为 `相对路径:行号`，且路径部分真实存在。"""
    for key in real_allowlist_entries:
        assert _KEY_RE.match(key), f"键形态非法：{key!r}"
        rel, _, lineno = key.rpartition(":")
        assert (PROJECT_ROOT / rel).is_file(), f"键指向的文件不存在：{rel}"
        assert int(lineno) >= 1


def test_allowlist_entries_are_all_load_bearing(gate, real_allowlist_entries):
    """无陈旧条目：每条登记都必须出现在「不放宽」的实测命中集里。

    行号漂移 ⇒ 登记不再命中 ⇒ 本锁红（命中会重现，不会静默失效）。
    """
    findings = gate.scan_traceability(gate.collect_files([]), allowlist=set())
    hit_keys = {f.split(": ", 1)[0] for f in findings}
    stale = sorted(set(real_allowlist_entries) - hit_keys)
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
    target = f"{doc}:3"
    assert gate.scan_traceability([doc], allowlist={target}) == []
    assert gate.scan_traceability([doc], allowlist={f"{doc}:99"}) != []


def test_load_allowlist_silently_merges_duplicates(gate, tmp_path):
    """`load_allowlist` 返回 set——重复键被静默合并（= 重复登记不可见的原因）。

    本锁把这个语义钉住：正因如此，entry 行的原始重复只能由
    `test_allowlist_raw_entries_have_no_duplicates` 从文件面抓住。
    """
    p = tmp_path / "allow.txt"
    p.write_text("# 注释\n\ndocs/a.md:1\ndocs/a.md:1\ndocs/b.md:2\n", encoding="utf-8")
    assert gate.load_allowlist(p) == {"docs/a.md:1", "docs/b.md:2"}


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
