"""外部读数登记册的行级判据（CP 轮）。

`docs/study/EXTERNAL_READINGS_2026-10-25.md` 的每行形如 `| 键 | 读数 | 原文表述 | 出处 |`。
旧口径下这几列之间没有可执行的一致性判据，于是出现两类「看起来登记了、其实没有引文支撑」
的行（CP 轮实测）：

1. `shu2026agentworld` 的 CCE 0.320 写进「读数」，但「原文表述」抄的是 arXiv **摘要**里的
   指标定义句——摘要里没有 0.320（该读数出自全文 §3 / Table 2）。读数与引文不是同一句话。
2. `tufano2026specops` 的 p 值行「原文表述」写成自指 `McNemar p-values quoted above`，
   两个 p 值没有任何逐字引文。

判据：
- **多位数与小数**（`\\d{2,}` / `\\d+\\.\\d+`，含千分位）必须在同一行的「原文表述」里逐字
  出现；比较前只去掉千分位逗号（`7,950` ≡ `7950`），不做其他归一。
- 「原文表述」不得是自指（`quoted above` 一类必须内联原句）。
- 单位数（3 个代理 / 5 维度）不判：原文常写成英文数词，判它只会制造豁免噪音。
  `ten` / `thirteen` 两条按名豁免，且**豁免表只允许变短**——未被用到即判红。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REGISTER_DIR = Path(__file__).resolve().parents[1] / "docs" / "study"
_REGISTER_FILES = sorted(REGISTER_DIR.glob("EXTERNAL_READINGS_*.md"))
# 读者按**文件名发现**登记册：新一轮若新建一份，下面的「恰有一份」测试当场红，
# 不会出现「锁还在读上一代登记册、新登记册无人校验」的静默过期。
REGISTER = _REGISTER_FILES[0] if _REGISTER_FILES else REGISTER_DIR / "EXTERNAL_READINGS_2026-10-25.md"

_ROW = re.compile(r"^\|\s*`(?P<key>[A-Za-z0-9_]+)`\s*\|(?P<reading>.+?)\|(?P<quote>.+?)\|(?P<source>.+?)\|\s*$")
_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d{2,}")
_SELF_REFERENCE = re.compile(r"quoted above|as quoted above|as above", re.IGNORECASE)
_ARXIV = re.compile(r"arXiv:(\d{4}\.\d{4,5})(v\d+)?")
_PUBLISHER_DOI = re.compile(r"10\.(?!48550/)\d{4,}/")

#: 原文用英文数词写出的读数：只收这一类，且每条必须给理由；表只允许变短。
SPELLED_OUT_EXEMPTIONS: dict[tuple[str, str], str] = {
    ("shin2026rag", "10"): "原文写 ten were confirmed",
    ("zhao2026coverage", "13"): "原文写 Across thirteen model setups",
}


def _rows() -> list[tuple[int, str, str, str, str]]:
    """(行号, 键, 读数, 原文表述, 出处)——只为真表行返回，表头与分隔行自然落空。"""
    rows: list[tuple[int, str, str, str, str]] = []
    for lineno, line in enumerate(REGISTER.read_text(encoding="utf-8").splitlines(), start=1):
        match = _ROW.match(line)
        if match:
            rows.append((lineno, match["key"], match["reading"], match["quote"], match["source"]))
    return rows


_ROWS = _rows()


def _numbers(text: str) -> list[str]:
    return _NUMBER.findall(text)


def _absent_numbers(row: tuple[int, str, str, str, str]) -> list[str]:
    """该行读数里未在本行原文表述中逐字出现的数字（千分位逗号不计）。"""
    _, _, reading, quote, _ = row
    haystack = quote.replace(",", "")
    return [token for token in _numbers(reading) if token.replace(",", "") not in haystack]


def test_exactly_one_register_file() -> None:
    """登记册按文件名发现：两份就要当场红，否则锁会静默地只读上一代。"""
    names = [path.name for path in _REGISTER_FILES]
    assert len(names) == 1, f"期望恰有一份 `EXTERNAL_READINGS_*.md`，实测 {names}"


def test_register_is_parsed_and_complete() -> None:
    """解析面塌了要当场红——否则下面的参数化会静默地「零用例通过」。"""
    assert len(_ROWS) >= 30, f"登记册只解析到 {len(_ROWS)} 行"
    assert len({row[1] for row in _ROWS}) >= 15, "登记的文献键少于 15 个"
    for lineno, key, reading, quote, source in _ROWS:
        assert reading.strip(), f"第 {lineno} 行 {key}：读数列为空"
        assert quote.strip(), f"第 {lineno} 行 {key}：原文表述列为空"
        assert source.strip(), f"第 {lineno} 行 {key}：出处列为空"


@pytest.mark.parametrize(
    "row",
    _ROWS,
    ids=[f"{row[1]}-L{row[0]}" for row in _ROWS],
)
def test_reading_number_appears_in_its_own_quote(row: tuple[int, str, str, str, str]) -> None:
    """读数与引文必须是同一句话：多位数/小数逐字出现在本行引文里。"""
    lineno, key, _, _, _ = row
    missing = [token for token in _absent_numbers(row) if (key, token) not in SPELLED_OUT_EXEMPTIONS]
    assert not missing, (
        f"第 {lineno} 行 {key}：读数 {missing} 在本行「原文表述」里找不到——"
        "读数与引文不是同一句话（摘要级引文抄不了全文读数）"
    )


def test_arxiv_rows_state_their_version() -> None:
    """只以 arXiv 标识为出处的行必须写版本（vN），且一个读数只能对应一个版本。

    为什么需要：`kim2026scaling` 曾把 v2 摘要的 R²=0.524 与 v3 的 260 配置写在同一行，
    出处只列「v1…v3」——按最新版核对找不到该 R²，按旧版核对又对不上配置数。
    **「一手」必须连版本一起说**；有出版商 DOI（10.1145/… / 10.1109/…）的行按定稿口径，
    不强制 arXiv 版本。
    """
    offenders = []
    for lineno, key, _reading, _quote, source in _ROWS:
        if _PUBLISHER_DOI.search(source):
            continue
        ids = _ARXIV.findall(source)
        if not ids:
            continue
        versions = {version for _pid, version in ids if version}
        missing = [pid for pid, version in ids if not version]
        if missing or len(versions) > 1:
            offenders.append((lineno, key, missing, sorted(versions)))
    assert offenders == [], f"arXiv 行必须写且只写一个版本（缺版本 / 多版本）：{offenders}"


def test_quotes_are_not_self_referential() -> None:
    """带数字的行不能只写「同上/见上」：自指等于没有引文。"""
    offenders = [
        (lineno, key) for lineno, key, reading, quote, _ in _ROWS if _numbers(reading) and _SELF_REFERENCE.search(quote)
    ]
    assert offenders == [], f"这些行的原文表述是自指：{offenders}"


def test_quotes_are_verbatim() -> None:
    """原文表述必须是引文（带引号），否则「抄录」无从核对。"""
    offenders = [(lineno, key) for lineno, key, _, quote, _ in _ROWS if '"' not in quote]
    assert offenders == [], f"这些行的原文表述没有引号：{offenders}"


def test_spelled_out_exemptions_match_reality() -> None:
    """豁免必须逐条在实况里仍然成立，且不得出现死条目（棘轮：只许变短）。"""
    observed = {(row[1], token) for row in _ROWS for token in _absent_numbers(row)}
    declared = set(SPELLED_OUT_EXEMPTIONS)
    assert declared - observed == set(), f"豁免表有死条目（实况已不需要）：{sorted(declared - observed)}"
    assert observed - declared == set(), (
        f"这些读数没有引文支撑又没登记豁免：{sorted(observed - declared)}——要么内联原句，要么按名豁免并给理由"
    )
    assert all(reason.strip() for reason in SPELLED_OUT_EXEMPTIONS.values()), "豁免必须写理由"
