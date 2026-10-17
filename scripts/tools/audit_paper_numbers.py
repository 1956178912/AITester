#!/usr/bin/env python3
"""Q11（2026-10-17 独立评审 §3/§10）：EMSE 论文草稿的"数字 ↔ SRC 证据"一致性审计。

## 为什么需要它

独立评审 Q11：`paper/draft.typ` **不在 git（.gitignore 排除）**，正文中的百分比 /
DOI / 成本 / 样本量数字仅抽查了 3 处 `// SRC:` 注释；评审要求"投稿前必须完成全文
数字对账（建议用 `check_artifact_doc_consistency.py` 同口径扩展至 paper/），重点
核验论文中所有百分比/DOI/成本数字的 SRC 注释完整性"。本工具即该审计的本地实现。

## 检查项

1. **数字声明覆盖率**：识别 draft.typ 中的数字声明（百分比 / 货币 / p 值 / `n=`
   / `x/y` 比例 / DOI），判断其是否处在某条 `// SRC:` 注释的覆盖窗口（默认 ±12 行）
   内；输出未覆盖清单与逐节覆盖率。
2. **SRC 引用有效性**：解析每条 `// SRC:` 中的引用 token：
   - 仓库内路径（含 `/` 或以已知扩展名结尾）必须存在（文件或目录）；
   - `docs/adr/ADR-00XX` / 裸 `ADR-00XX` 必须能在 `docs/adr/` 找到对应编号文件；
   - `BASELINE.yaml#a.b.c` 形式的键必须能在 YAML 中解析；
   - 其余视为说明性文字（忽略）。
3. **引文卫生**：draft 引用的 `@key` 必须存在于 `refs.bib`；每条 bib 条目必须有
   note 含 DOI 或 arXiv（录入纪律：未核验字段留 TODO）；DOI 去重与格式校验；
   未被引用的 bib 条目作为 warning 列出。
4. **TODO 清单**：列出 draft/bib 中所有 `TODO` 标记（投稿前清零项）。

## 口径与边界

- **本地工具，非 CI**：`paper/` 不入库，本工具在 paper 缺失时直接 exit 0（CI 安全）；
  `make paper-audit` 供投稿前本地执行。
- 数字识别的启发式**不是**语义解析：可能漏报（如文字化数字 "three seeds"）与误报
  （如公式里的常数）；报告须人工复核，工具只给出"待对账清单 + 客观引用有效性"。
- 覆盖率是**块级近似**（SRC 窗口），不代表每条数字逐条被引用——投稿纪律仍要求
  关键数字逐条可追溯到工件。

用法：
    python scripts/tools/audit_paper_numbers.py
    python scripts/tools/audit_paper_numbers.py --json out.json --md out.md
    python scripts/tools/audit_paper_numbers.py --strict          # 引用无效/覆盖率不达标 → exit 1
    python scripts/tools/audit_paper_numbers.py --window 15 --min-coverage 0.8
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PAPER_DIR = PROJECT_ROOT / "paper"
DEFAULT_DRAFT = "draft.typ"
DEFAULT_BIB = "refs.bib"
DEFAULT_WINDOW = 12
DEFAULT_MIN_COVERAGE = 0.8

# 数字声明识别（启发式；报告附匹配片段供人工复核）
_NUMERIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("percentage", re.compile(r"\d+(?:\.\d+)?\s*%")),
    # 货币：`$` 前不得紧邻字母/数字（排除 Typst 数学 `2$times$2` 的误报）
    ("currency", re.compile(r"(?<![A-Za-z0-9])\$\s?\d[\d,]*(?:\.\d+)?")),
    ("p_value", re.compile(r"\bp\s*(?:[=~<>]|approx)\s*\d")),
    ("sample_size", re.compile(r"\bn\s*=\s*\d+")),
    ("ratio", re.compile(r"\b\d+/\d+\b")),
    ("doi", re.compile(r"\b10\.\d{4,}/[^\s,;)\]]+")),
    ("count", re.compile(r"\b\d+\s+(?:tasks|programs|tests|pairs|batches|seeds|functions|calibers|artifacts)\b", re.I)),
)

# DOI 在 bib note 中的识别
_BIB_DOI_RE = re.compile(r"10\.\d{4,}/[^\s;,'\"}]+")
_BIB_ARXIV_RE = re.compile(r"arXiv:\s*\d{4}\.\d{4,5}")
_BIB_ENTRY_RE = re.compile(r"^@([a-zA-Z]+)\{([^,]+),")
_CITE_RE = re.compile(r"@([a-zA-Z][a-zA-Z0-9_]+)")
_ADR_RE = re.compile(r"ADR-(\d{4})", re.I)
_PATH_TOKEN_RE = re.compile(
    r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.*%{}-]+)+|(?:[A-Za-z0-9_.-]+\.(?:md|json|yaml|yml|py|typ|cff|txt))"
)
_KNOWN_EXT = (".md", ".json", ".yaml", ".yml", ".py", ".typ", ".cff", ".txt")


def _load_yaml_mapping(path: Path) -> dict[str, Any] | None:
    """尽力加载 YAML（pyyaml 缺失/解析失败 → None，不阻断审计）。"""
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:  # pragma: no cover - 环境缺 pyyaml 时保守降级
        return None


def _resolve_dotted(data: Any, dotted: str) -> bool:
    """在嵌套 mapping 中解析点分键（`benchmark.docstring_anchor.decision.verdict`）。"""
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False
    return True


def find_src_lines(lines: list[str]) -> list[int]:
    """返回含 `// SRC:` 注释的行号（0-based）。"""
    return [i for i, line in enumerate(lines) if "// SRC:" in line]


def _scrub_typst_math(text: str) -> str:
    """Typst 数学模式预处理：**刻意保留**数学模式内的数字。

    论文的统计量大量写在数学模式里（`$p approx 2.8 times 10^(-12)$`、
    `$n=261$`、`$minus$25.7 pp`），若剥除数学模式会系统性漏报关键声明；
    因此本函数只做恒等返回，保留为显式"不改写"口径（未来若需排除公式常数
    在此集中实现，便于审计口径可追溯）。
    """
    return text


def detect_numeric_claims(lines: list[str]) -> list[dict[str, Any]]:
    """逐行识别数字声明；每行最多归并为一条声明（kind = 首个命中类别）。"""
    claims: list[dict[str, Any]] = []
    for idx, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if "// SRC:" in raw:
            continue
        for kind, pattern in _NUMERIC_PATTERNS:
            match = pattern.search(_scrub_typst_math(raw))
            if match:
                claims.append(
                    {
                        "line": idx + 1,
                        "kind": kind,
                        "match": match.group(0),
                        "snippet": stripped[:160],
                    }
                )
                break
    return claims


_CITATION_RE = re.compile(r"@([a-zA-Z][a-zA-Z0-9_]+)")
_CITATION_PSEUDO_KEYS = frozenset({"sec", "tab", "fig", "eq"})


def _paragraph_citations(lines: list[str]) -> list[set[str]]:
    """按"段落块"（连续非空行，含表格/figure 块）归集正文引文 key。

    依据：论文每个数字声明所在段落的引文即为该声明的合法外部来源——
    引用可以出现在段落开头（如 "Zhao et al. (@zhao2026…) quantify …"），
    其后若干行数字共享同一来源；用 ±N 行窗口会系统性漏判段落级引用。
    """
    blocks: list[set[str]] = []
    current: set[str] = set()
    for raw in lines:
        if raw.strip():
            for key in _CITATION_RE.findall(raw):
                if key not in _CITATION_PSEUDO_KEYS:
                    current.add(key)
        else:
            blocks.append(current)
            current = set()
    blocks.append(current)
    return blocks


def _citations_for_line(blocks: list[set[str]], lines: list[str], line0: int) -> list[str]:
    """定位声明行所属段落块的引文 key 列表（块内顺序去重）。"""
    block_idx = 0
    for idx in range(min(line0, len(lines) - 1)):
        if not lines[idx].strip():
            block_idx += 1
    return sorted(blocks[block_idx]) if block_idx < len(blocks) else []


def compute_coverage(
    claims: list[dict[str, Any]], src_lines: list[int], window: int, draft_lines: list[str] | None = None
) -> dict[str, Any]:
    """计算覆盖：SRC 窗口覆盖 + 正文引文覆盖（外部文献数字的合法来源）。

    区分两类来源（投稿纪律）：
      - **内部工件数字** → 必须被 `// SRC:` 覆盖；
      - **外部文献数字** → 由 `@citation`（refs.bib 一手核验条目）覆盖即可；
      - 两者皆无 → 未覆盖（待对账）。
    """
    covered: list[dict[str, Any]] = []
    covered_citation: list[dict[str, Any]] = []
    uncovered: list[dict[str, Any]] = []
    blocks = _paragraph_citations(draft_lines) if draft_lines is not None else []
    for claim in claims:
        line0 = claim["line"] - 1
        nearest = min(src_lines, key=lambda s: abs(s - line0)) if src_lines else None
        distance = abs(nearest - line0) if nearest is not None else None
        citations = _citations_for_line(blocks, draft_lines, line0) if draft_lines is not None else []
        claim = dict(
            claim,
            nearest_src_line=(nearest + 1) if nearest is not None else None,
            distance=distance,
            citations=citations,
        )
        if distance is not None and distance <= window:
            covered.append(claim)
        elif citations:
            covered_citation.append(claim)
        else:
            uncovered.append(claim)
    total = len(claims)
    return {
        "total_claims": total,
        "covered_src_claims": len(covered),
        "src_coverage_ratio": (len(covered) / total) if total else 1.0,
        "covered_citation_claims": len(covered_citation),
        "traceable_claims": len(covered) + len(covered_citation),
        "traceable_ratio": ((len(covered) + len(covered_citation)) / total) if total else 1.0,
        "window_lines": window,
        "uncovered": uncovered,
        "citation_covered": covered_citation,
    }


def _iter_src_tokens(lines: list[str]) -> list[tuple[int, str]]:
    """提取 SRC 注释中的引用 token：`(行号 1-based, token 原文)`。"""
    tokens: list[tuple[int, str]] = []
    for idx, raw in enumerate(lines):
        if "// SRC:" not in raw:
            continue
        text = raw.split("// SRC:", 1)[1]
        for token in re.split(r"[;,\s]+", text):
            token = token.strip().strip(";,.()[]{}\"'")
            if token:
                tokens.append((idx + 1, token))
    return tokens


def validate_src_tokens(tokens: list[tuple[int, str]], root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """校验 SRC 引用有效性；返回 (引用明细, 违规描述列表)。"""
    details: list[dict[str, Any]] = []
    failures: list[str] = []
    baseline_cache: dict[str, dict[str, Any] | None] = {}

    for line_no, token in tokens:
        kind = "prose"
        ok: bool | None = None

        # BASELINE.yaml#a.b.c
        if "#" in token and token.split("#", 1)[0].endswith((".yaml", ".yml")):
            path_part, key_part = token.split("#", 1)
            kind = "yaml_key"
            path = root / path_part
            if not path.exists():
                ok = False
                failures.append(f"L{line_no}: SRC 引用文件不存在：{path_part}")
            else:
                if path_part not in baseline_cache:
                    baseline_cache[path_part] = _load_yaml_mapping(path)
                data = baseline_cache[path_part]
                if data is None:
                    ok = None  # 无法解析 → 不判失败（降级）
                elif not _resolve_dotted(data, key_part):
                    ok = False
                    failures.append(f"L{line_no}: SRC 键不存在：{path_part}#{key_part}")
                else:
                    ok = True
        # ADR-00XX（含 docs/adr/ADR-00XX 形式）
        elif (m := _ADR_RE.search(token)) is not None:
            kind = "adr"
            prefix = f"{int(m.group(1)):04d}"
            adr_dir = root / "docs" / "adr"
            matches = sorted(adr_dir.glob(f"{prefix}-*")) if adr_dir.is_dir() else []
            ok = bool(matches)
            if not ok:
                failures.append(f"L{line_no}: SRC ADR 引用不存在：{token}")
        # 仓库内路径（含 / 或以已知扩展名结尾）
        elif ("/" in token or token.endswith(_KNOWN_EXT)) and not token.startswith(("http://", "https://")):
            kind = "path"
            path = root / token
            # 容忍目录 + 通配（`emse_*`）；历史 SRC 口径可能相对 experiments/results/
            candidates = [path, root / "experiments" / "results" / token]
            if any(ch in token for ch in "*?["):
                ok = False
                for cand in candidates:
                    parent = cand.parent if cand.suffix else cand
                    if parent.exists():
                        ok = True
                        break
            else:
                ok = any(cand.exists() for cand in candidates)
            if not ok:
                failures.append(f"L{line_no}: SRC 引用路径不存在：{token}")
        # 数字编号（如 0031/0032）在 ADR 语境下忽略
        if kind != "prose":
            details.append({"line": line_no, "token": token, "kind": kind, "ok": ok})
    return details, failures


def audit_bib(bib_path: Path, draft_text: str) -> dict[str, Any]:
    """引文卫生审计：被引 key 存在、bib 条目 DOI/arXiv 齐备、重复/未引用。"""
    result: dict[str, Any] = {
        "bib_exists": bib_path.exists(),
        "entries": [],
        "cited_keys": sorted({k for k in _CITE_RE.findall(draft_text) if k not in {"sec", "tab", "fig", "eq"}}),
        "missing_keys": [],
        "entries_without_identifier": [],
        "duplicate_dois": [],
        "unused_entries": [],
        "failures": [],
    }
    if not bib_path.exists():
        result["failures"].append(f"bib 文件不存在：{bib_path}")
        result["missing_keys"] = result["cited_keys"]
        return result

    text = bib_path.read_text(encoding="utf-8")
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        if (m := _BIB_ENTRY_RE.match(line.strip())) is not None:
            if current is not None:
                entries.append(current)
            current = {"type": m.group(1), "key": m.group(2), "raw": [line.strip()]}
        elif current is not None:
            current["raw"].append(line)
    if current is not None:
        entries.append(current)

    doi_owner: dict[str, list[str]] = {}
    keys: set[str] = set()
    for entry in entries:
        raw = "\n".join(entry["raw"])
        keys.add(entry["key"])
        dois = _BIB_DOI_RE.findall(raw)
        arxiv = bool(_BIB_ARXIV_RE.search(raw))
        for doi in dois:
            doi_owner.setdefault(doi.rstrip("."), []).append(entry["key"])
        has_id = bool(dois) or arxiv
        has_todo = "TODO" in raw
        result["entries"].append(
            {
                "key": entry["key"],
                "type": entry["type"],
                "dois": dois,
                "arxiv": arxiv,
                "has_identifier": has_id,
                "pending_todo": (not has_id) and has_todo,
            }
        )
        if not has_id:
            result["entries_without_identifier"].append(entry["key"])
            if not has_todo:
                result["failures"].append(f"bib 条目 {entry['key']} 缺少 DOI/arXiv 标识（录入纪律要求至少其一或 TODO）")
    result["duplicate_dois"] = {doi: owners for doi, owners in doi_owner.items() if len(owners) > 1}
    cited = set(result["cited_keys"])
    result["missing_keys"] = sorted(cited - keys)
    result["unused_entries"] = sorted(keys - cited)
    for key in result["missing_keys"]:
        result["failures"].append(f"正文引用 @{key} 不在 refs.bib 中")
    for key in result["entries_without_identifier"]:
        result.setdefault("warnings", []).append(f"bib 条目 {key} 缺少 DOI/arXiv 标识（TODO 挂起项，投稿前回填或降级）")
    for doi, owners in result["duplicate_dois"].items():
        result["failures"].append(f"DOI 重复：{doi} 同时出现在 {owners}")
    return result


def find_todos(lines: list[str], bib_text: str) -> list[dict[str, Any]]:
    """列出 draft/bib 中的 TODO 标记（投稿前清零项）。"""
    todos: list[dict[str, Any]] = []
    for idx, raw in enumerate(lines):
        if "TODO" in raw:
            todos.append({"file": "draft.typ", "line": idx + 1, "snippet": raw.strip()[:180]})
    for idx, raw in enumerate(bib_text.splitlines()):
        if "TODO" in raw:
            todos.append({"file": "refs.bib", "line": idx + 1, "snippet": raw.strip()[:180]})
    return todos


def per_section_coverage(
    draft_lines: list[str], claims: list[dict[str, Any]], src_lines: list[int], window: int
) -> list[dict[str, Any]]:
    """按 `= ` 一级标题统计覆盖率（帮助定位最缺 SRC 的章节）。"""
    headings: list[tuple[int, str]] = [
        (i, line[2:].strip()) for i, line in enumerate(draft_lines) if line.startswith("= ")
    ]
    if not headings:
        return []
    sections: list[dict[str, Any]] = []
    bounds = [i for i, _ in headings] + [len(draft_lines)]
    for pos, (start, title) in enumerate(headings):
        end = bounds[pos + 1]
        section_claims = [c for c in claims if start <= c["line"] - 1 < end]
        local_src = [s for s in src_lines if start <= s < end]
        cov = compute_coverage(section_claims, local_src, window, draft_lines)
        sections.append(
            {
                "title": title,
                "start_line": start + 1,
                "claims": cov["total_claims"],
                "covered": cov["covered_src_claims"],
                "citation_covered": cov["covered_citation_claims"],
                "traceable": cov["traceable_claims"],
                "coverage_ratio": cov["traceable_ratio"],
            }
        )
    return sections


def build_audit(paper_dir: Path, window: int) -> dict[str, Any]:
    """执行完整审计并返回结构化结果（供 CLI/测试复用）。"""
    draft_path = paper_dir / DEFAULT_DRAFT
    bib_path = paper_dir / DEFAULT_BIB
    if not draft_path.exists():
        return {
            "paper_present": False,
            "paper_dir": str(paper_dir),
            "note": "paper/draft.typ 不存在（paper/ 按 .gitignore 排除；CI/无本地论文稿时跳过）",
            "failures": [],
        }
    draft_text = draft_path.read_text(encoding="utf-8")
    lines = draft_text.splitlines()
    src_lines = find_src_lines(lines)
    claims = detect_numeric_claims(lines)
    coverage = compute_coverage(claims, src_lines, window, lines)
    _, src_failures = validate_src_tokens(_iter_src_tokens(lines), PROJECT_ROOT)
    bib = audit_bib(bib_path, draft_text)
    todos = find_todos(lines, bib_path.read_text(encoding="utf-8") if bib_path.exists() else "")
    return {
        "paper_present": True,
        "paper_dir": str(paper_dir),
        "draft": str(draft_path),
        "bib_path": str(bib_path),
        "window_lines": window,
        "src_lines": [i + 1 for i in src_lines],
        "src_count": len(src_lines),
        "coverage": coverage,
        "sections": per_section_coverage(lines, claims, src_lines, window),
        "src_reference_failures": src_failures,
        "bib": bib,
        "todos": todos,
        "failures": src_failures + list(bib.get("failures", [])),
    }


def render_markdown(audit: dict[str, Any]) -> str:
    """把审计结果渲染为 Markdown 报告。"""
    if not audit.get("paper_present"):
        return "# 论文数字-SRC 一致性审计\n\npaper/draft.typ 不存在，跳过（本地工具）。\n"
    src_failures = audit["src_reference_failures"]
    bib = audit["bib"]
    cov = audit["coverage"]
    lines: list[str] = [
        "# 论文数字-SRC 一致性审计（Q11，2026-10-17 独立评审）",
        "",
        "> 工具：`scripts/tools/audit_paper_numbers.py`（本地工具，paper/ 不入库）",
        f"> 输入：`{audit['draft']}` / `{audit['bib_path']}`；SRC 窗口 ±{audit['window_lines']} 行",
        "",
        "## 1. 数字声明覆盖率（块级近似）",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 识别到的数字声明 | {cov['total_claims']} |",
        f"| SRC 窗口覆盖（内部工件数字） | {cov['covered_src_claims']} |",
        f"| 正文引文覆盖（外部文献数字） | {cov['covered_citation_claims']} |",
        f"| **综合可追溯率** | **{cov['traceable_ratio']:.1%}** |",
        f"| 仅 SRC 覆盖率 | {cov['src_coverage_ratio']:.1%} |",
        f"| `// SRC:` 注释数 | {audit['src_count']} |",
        "",
        "### 逐节覆盖率",
        "",
        "| 章节 | 起始行 | 声明数 | SRC 覆盖 | 引文覆盖 | 综合可追溯率 |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend(
        f"| {sec['title']} | {sec['start_line']} | {sec['claims']} | {sec['covered']} | "
        f"{sec['citation_covered']} | {sec['coverage_ratio']:.1%} |"
        for sec in audit.get("sections", [])
    )
    lines += ["", "### 未覆盖的数字声明（待对账清单）", ""]
    if cov["uncovered"]:
        lines += ["| 行 | 类别 | 片段 | 最近 SRC 行 | 距离 |", "|---|---|---|---|---|"]
        for claim in cov["uncovered"]:
            snippet = claim["snippet"].replace("|", "\\|")
            lines.append(
                f"| {claim['line']} | {claim['kind']} | `{snippet}` | {claim['nearest_src_line']} | {claim['distance']} |"
            )
    else:
        lines.append("（无）")

    lines += ["", "## 2. SRC 引用有效性", ""]
    if src_failures:
        lines += [f"- ❌ {item}" for item in src_failures]
    else:
        lines.append("- ✅ 全部 SRC 引用（路径 / ADR / BASELINE 键）可解析")

    lines += ["", "## 3. 引文卫生", ""]
    lines += [
        f"- 正文引用 key：{len(bib['cited_keys'])} 个",
        f"- bib 条目：{len(bib['entries'])} 个",
        f"- 缺失条目（正文引用但 bib 没有）：{bib['missing_keys'] or '无'}",
        f"- 缺 DOI/arXiv 的条目（含 TODO 挂起）：{bib['entries_without_identifier'] or '无'}",
        f"- 重复 DOI：{bib['duplicate_dois'] or '无'}",
        f"- 未被正文引用的条目（warning）：{bib['unused_entries'] or '无'}",
    ]
    lines += ["", "## 4. TODO（投稿前清零）", ""]
    if audit["todos"]:
        lines += [f"- {t['file']}:{t['line']} — `{t['snippet']}`" for t in audit["todos"]]
    else:
        lines.append("（无）")
    lines += [
        "",
        "## 5. 边界",
        "",
        "- 数字识别为启发式（漏报/误报均可能），未覆盖清单须人工复核；",
        "- 覆盖率为块级近似，不等于逐条数字均已逐项追溯；",
        "- 本报告为本地审计工件（paper/ 不入库），不接入 CI。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="论文 draft.typ 数字-SRC 一致性审计（本地工具，Q11）")
    parser.add_argument("--paper-dir", default=str(DEFAULT_PAPER_DIR), help="论文目录（默认 paper/）")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW, help="SRC 覆盖窗口（行，默认 12）")
    parser.add_argument("--json", default=None, help="审计 JSON 输出路径（可选）")
    parser.add_argument("--md", default=None, help="审计 Markdown 报告输出路径（可选）")
    parser.add_argument("--strict", action="store_true", help="引用无效或覆盖率低于阈值 → exit 1")
    parser.add_argument(
        "--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE, help="strict 模式下最低覆盖率（默认 0.8）"
    )
    args = parser.parse_args(argv)

    paper_dir = Path(args.paper_dir)
    if not paper_dir.is_absolute():
        paper_dir = (PROJECT_ROOT / paper_dir).resolve()
    audit = build_audit(paper_dir, args.window)
    if not audit.get("paper_present"):
        print(f"[paper-audit] {audit['note']}")
        return 0

    coverage = audit["coverage"]
    print(
        f"[paper-audit] 数字声明 {coverage['total_claims']} 条：SRC 覆盖 "
        f"{coverage['covered_src_claims']} 条（{coverage['src_coverage_ratio']:.1%}），"
        f"正文引文覆盖 {coverage['covered_citation_claims']} 条，"
        f"综合可追溯率 {coverage['traceable_ratio']:.1%}；"
        f"SRC 注释 {audit['src_count']} 条；引用无效 {len(audit['src_reference_failures'])} 项；"
        f"引文问题 {len(audit['bib']['failures'])} 项；TODO {len(audit['todos'])} 项"
    )
    if coverage["uncovered"]:
        print("[paper-audit] 未覆盖数字声明（前 10 条）：")
        for claim in coverage["uncovered"][:10]:
            print(f"  L{claim['line']} [{claim['kind']}] {claim['snippet']}")
    for failure in audit["failures"]:
        print(f"[paper-audit] ❌ {failure}")

    if args.json:
        Path(args.json).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[paper-audit] JSON 已写入 {args.json}")
    if args.md:
        Path(args.md).write_text(render_markdown(audit), encoding="utf-8")
        print(f"[paper-audit] Markdown 已写入 {args.md}")

    if args.strict:
        problems = list(audit["failures"])
        if coverage["traceable_ratio"] < args.min_coverage:
            problems.append(f"数字声明综合可追溯率 {coverage['traceable_ratio']:.1%} < 阈值 {args.min_coverage:.0%}")
        if problems:
            print(f"[paper-audit] strict 失败：{len(problems)} 项")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
