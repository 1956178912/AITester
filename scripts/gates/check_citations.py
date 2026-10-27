#!/usr/bin/env python3
"""G15（2026-10-05 优化批次·T4）：文档引用真实性核验（arXiv / DOI）。

背景：
    仓库根有 5 份 2023-2026 前沿基线综述 MD（APR/FORMAL_METHODS/FRONTIER/
    MULTIAGENT/MULTI_AGENT_LLM_SE），docs/ 另有设计文档。其中的 arXiv 编号
    与 DOI 全部靠人工维护——编号抄错 / 论文撤稿 / 版本号笔误均无机器守卫。

本脚本两档口径：
    默认（离线清单）：抽取全部 arXiv:XXXX.XXXXX / arxiv.org/abs/XXXX.XXXXX /
        DOI 10.x/… 引用并去重排序输出（供人工核对与 CI 工件归档）；
    --online：对 arxiv.org/abs/<id> 与 doi.org/<doi> 发起 HEAD/GET 存在性
        核验（urllib，5s 超时，3xx 重定向视为存在）。任一 404/410 →
        退出码 1（--strict 时；默认 --online 即 strict，--no-strict 降为警告）。

诚实口径（防过度宣称）：
    - "存在性核验"≠"内容正确性核验"：HEAD 200 只证明该编号有论文，
      不证明引用处的论断忠实于原文；
    - 网络失败（超时 / DNS / 限流）与"不存在"严格区分：前者记
      network_error 不判失败（外部依赖抖动不得阻断 CI），后者才 fail。

用法：
    python3 scripts/gates/check_citations.py                 # 离线清单
    python3 scripts/gates/check_citations.py --online        # 在线核验（默认 strict）
    python3 scripts/gates/check_citations.py --online --no-strict
    python3 scripts/gates/check_citations.py --files README.md docs/adr/0001.md
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 默认扫描面。
#
# 2026-10-10 独立审查修复（P0-0 ④）：此前 `DEFAULT_GLOBS: list[str] = []` ——
# 原 5 份根目录前沿基线综述（*_BASELINE_2023-2026.md）在 2026-10-09 清理批次
# 被删除后，扫描面归零 → 脚本**恒定打印 WARN 并 exit 0**，而 ci.yml 又用
# `--no-strict` + `continue-on-error` + `|| echo` 三层放水 → **该门禁从未
# 真正阻断过任何东西**（"存在但不 fail-closed"的典型样本）。
#
# 现改为扫描**真正承载对外引用的文档**：README 双语 / 模型卡 / 数据卡 /
# 预注册 / 设计文档 / 全部 ADR。这些文件里的 arXiv/DOI 编号抄错、
# 版本号笔误、引用被替换都会被抓出来。
DEFAULT_GLOBS: list[str] = [
    "README.md",
    "README.en.md",
    "MODEL_CARD.md",
    "MODEL_CARD.en.md",
    "docs/DATA_CARD.md",
    "docs/DATA_CARD.en.md",
    "docs/preregistration.md",
    "docs/preregistration.en.md",
    "docs/design/*.md",
    "docs/adr/*.md",
    "docs/*.md",
]

# 明确排除：内部参考手册与失败分析（其"百分比"是内部统计或口径阈值，
# 不承载外部文献引用的追溯义务）。README/卡片/预注册/设计/ADR 仍受检。
EXCLUDE_RELS: frozenset[str] = frozenset(
    {
        "docs/api_reference.md",
        "docs/api_reference.en.md",
        "docs/failure_analysis.md",
        "docs/failure_analysis.en.md",
        "docs/troubleshooting.md",
        "docs/performance_guide.md",
        "docs/performance_guide.en.md",
        "docs/usage_examples.md",
        "docs/usage_examples.en.md",
        "docs/threat_model.md",
        "docs/threat_model.en.md",
    }
)

# 豁免清单（人工登记"确认非外部引用"的行），每行 `相对路径:行号`。
DEFAULT_ALLOWLIST = Path("docs/citation_allowlist.txt")

# 含"数值型外部引用"的行须带可追溯标识（DOI / arXiv / URL）。
# 机械门禁**不能**判断归属是否正确（那需人工核验），但能保证
# "每条数值型引用都带得走"，把"错误归属"从隐蔽变为可查出。
TRACEABLE_RE = re.compile(
    r"(?:doi\s*[:=]|DOI\s*[:=]|arXiv\s*[:：]|arxiv\.org|10\.\d{4,9}/|https?://[\w.-]+\.[a-z]{2,})",
    re.IGNORECASE,
)
NUMERIC_REF_RE = re.compile(r"(?:\d+(?:\.\d+)?\s*%|\b0\.\d{2,}\b|\b\d{2,3}\s*/\s*\d{2,3}\b)")
# "数值型外部引用"的行级线索：**收紧口径**以压误报。
# 只报"该行同时出现 venue 名 与 文献口吻词"的行——例如
# "CANDOR（ICST 2026，one-shot 88.35%…）"。仅出现 venue 名（如
# "对比 EvoSuite/Defects4J"）或仅出现百分比（内部指标）都不报。
VENUE_RE = re.compile(
    r"(ICSE|FSE|ASE|ISSTA|ICST|TOSEM|TSE|PACMSE|ICLR|NeurIPS|ACL|APSEC|IJCAI|"
    r"EACL|OSDI|SOSP|CAV|TACAS|arXiv|IEEE|ACM|workshop|Companion|NeurIPS|USENIX)",
    re.IGNORECASE,
)
# 文献口吻词：表明该行在陈述"某篇外部工作报告了某个数值"
PAPER_TONE_RE = re.compile(
    r"(et al\.|预印本|论文|文献|该研究|该文|实证研究|独立复现|复现研究|报告|声称|提出|证明|"
    r"DOI|venue|发表于|received|reports?|propose[sd]?|achiev(?:es|ed))",
    re.IGNORECASE,
)
SELF_METRIC_RE = re.compile(
    r"(BASELINE\.yaml|本项目|本系统|aitester|plain_llm|detection|repair_rate|false_fix|"
    r"覆盖率|检出率|n_eff|McNemar|BH-FDR|ROPE|CI\[)",
    re.IGNORECASE,
)

ARXIV_ID_RE = re.compile(r"\b(?:arXiv:|arxiv\.org/abs/)(\d{4}\.\d{4,5})(?:v\d+)?\b", re.IGNORECASE)
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>\]\)，。；]+)")

_TIMEOUT_S = 5.0
# arXiv 对高频 HEAD 有限流：小 sleep + 单次重试
_RETRY_ONCE_HOSTS = ("arxiv.org",)


def _rel(path: Path) -> str:
    """相对仓库根的 posix 路径；仓库外文件退回绝对路径（与 collect_files 同口径）。

    2026-10-25 CJ 轮修复：`scan_traceability` 此前对仓库外文件直接调
    `path.relative_to(PROJECT_ROOT)` 抛**未捕获的 ValueError**——`collect_files`
    对 `--files /abs/outside.md` 是容忍的（去重键有 try 兜底），扫描段却没有，
    一条仓库外 `--files` 就能让整门崩栈而不是出具判定。
    """
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def collect_files(extra_files: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in dict.fromkeys(DEFAULT_GLOBS):
        if pattern:
            files.extend(sorted(PROJECT_ROOT.glob(pattern)))
    for name in extra_files:
        p = Path(name) if Path(name).is_absolute() else PROJECT_ROOT / name
        if p.is_file():
            files.append(p)
        else:
            print(f"[WARN] 指定文件不存在，跳过：{p}")
    # 去重保序 + 排除内部参考手册
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in files:
        rel = _rel(p)
        if rel in EXCLUDE_RELS:
            continue
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


ANCHOR_SEP = " @"


class AllowEntry(NamedTuple):
    """一条豁免登记：`相对路径:行号` 或 `相对路径:行号 @内容锚点`。

    EZ 轮之前只有行号——任何在它上方插行的文档改动都会让整表失效（本轮之前
    同一道承重锁在一天内报了三轮）。锚点是该行内容的唯一片段：**行号漂移时
    按锚点仍能命中，内容一变则锚点失效、必须重新判定**——把「键」从位置改成
    内容，同时保留「内容变了就得重看」这条纪律。
    """

    key: str
    path: str
    line: int
    anchor: str | None


def parse_allow_entry(raw: str) -> AllowEntry:
    """解析一条登记。形态非法时 line=0（由调用方判红），不在解析层抛异常。"""
    body, _, anchor = raw.partition(ANCHOR_SEP)
    body = body.strip()
    anchor = anchor.strip() or None
    rel, _, lineno = body.rpartition(":")
    return AllowEntry(key=body, path=rel, line=int(lineno) if lineno.isdigit() else 0, anchor=anchor)


def load_allowlist(path: Path | None) -> list[AllowEntry]:
    """读取豁免清单（每行 `相对路径:行号[@锚点]`，`#` 开头为注释）。"""
    target = path if path is not None else PROJECT_ROOT / DEFAULT_ALLOWLIST
    if not target.exists():
        return []
    out: list[AllowEntry] = []
    for raw in target.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(parse_allow_entry(line))
    return out


def extract_refs(text: str) -> tuple[set[str], set[str]]:
    arxiv_ids = {m.group(1) for m in ARXIV_ID_RE.finditer(text)}
    dois = {m.group(1).rstrip(".,;)") for m in DOI_RE.finditer(text)}
    return arxiv_ids, dois


def check_url_exists(url: str) -> tuple[str, str]:
    """返回 (status, detail)，status ∈ {"ok", "missing", "network_error"}。

    S310 豁免口径：url 仅由脚本内硬编码的 https:// 前缀 + 从文档提取的
    arXiv 编号 / DOI 拼接（extract_refs 产物不含 scheme），无用户可控
    协议面——file:// / 自定义 scheme 不可达。
    """
    req = urllib.request.Request(  # noqa: S310 —— https 硬编码前缀，见 docstring
        url, method="HEAD", headers={"User-Agent": "aitester-citation-check/1.0"}
    )
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:  # noqa: S310 —— 同上
                if resp.status < 400:
                    return "ok", f"HTTP {resp.status}"
                if resp.status in (404, 410):
                    return "missing", f"HTTP {resp.status}"
                # 403/429 等：换 GET 再试一次（部分站点禁 HEAD）
                break
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return "missing", f"HTTP {e.code}"
            if attempt == 2:
                return "network_error", f"HTTPError {e.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == 2:
                return "network_error", repr(e)[:120]
    # HEAD 被拒 → 降级 GET（Range 最小读）
    try:
        req_get = urllib.request.Request(  # noqa: S310 —— 同上（https 硬编码前缀）
            url, headers={"User-Agent": "aitester-citation-check/1.0", "Range": "bytes=0-0"}
        )
        with urllib.request.urlopen(req_get, timeout=_TIMEOUT_S) as resp:  # noqa: S310 —— 同上
            return ("ok" if resp.status < 400 else "missing"), f"GET HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return ("missing" if e.code in (404, 410) else "network_error"), f"GET HTTPError {e.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return "network_error", repr(e)[:120]


def _entry_matches(entry: AllowEntry, rel: str, lineno: int, text: str) -> str | None:
    """一条登记是否覆盖本行：返回 "line" / "anchor" / None。

    行号精确命中优先；锚点命中其次（行号已漂移，内容仍是当初判定的那行）。
    锚点**不是**宽匹配：它必须原样出现在行内，且只对登记的同一路径生效。
    """
    if entry.key == f"{rel}:{lineno}":
        return "line"
    if entry.anchor and entry.path == rel and entry.anchor in text:
        return "anchor"
    return None


def scan_traceability(
    files: list[Path],
    window: int = 3,
    allowlist: list[AllowEntry] | None = None,
    drift_report: list[str] | None = None,
) -> list[str]:
    """检查"数值型外部引用"是否在**邻域**内带可追溯标识（DOI / arXiv / URL）。

    只做机械可判定的那一半：**可追溯性**。归属正确性仍需人工核验
    （例：2026-10-10 审查发现 README 把 IEEE 复现研究的结果挂到了
    "CANDOR, ICST 2026" 名下——见 `REVIEW_2026_FRONTIER.md` §3.6）。

    口径说明（控制误报）：
    - 采用 **±window 行邻域** 而非单行：真实引用常把"系统（venue 年份，" 与
      "DOI: …）"分写在两行（本项目 README 的双语段落即如此）；
    - **收紧扣**：只报"同一行**同时**出现 venue 名 **与** 文献口吻词"的行
      （如 "CANDOR（ICST 2026，one-shot 88.35%…）"）。只出现 venue 名
      （"对比 EvoSuite/Defects4J"）或只出现百分比（内部指标）都不报；
    - 项目自身指标行（含 aitester / detection / BASELINE.yaml 等）直接豁免；
    - 剩余误报用 `docs/citation_allowlist.txt` 逐条豁免（每行 `相对路径:行号 @内容锚点`），
      豁免即等于**人工已判定"该行不是外部引用"**，因此是有成本的承诺，
      不应无脑批量加入。
    """
    findings: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:  # pragma: no cover - 保守降级
            findings.append(f"{_rel(path)}: 不可读 ({e})")
            continue
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            if not NUMERIC_REF_RE.search(line):
                continue
            if SELF_METRIC_RE.search(line):
                continue
            if not (VENUE_RE.search(line) and PAPER_TONE_RE.search(line)):
                continue
            lo = max(0, idx - window)
            hi = min(len(lines), idx + window + 1)
            if any(TRACEABLE_RE.search(lines[j]) for j in range(lo, hi)):
                continue
            key = f"{_rel(path)}:{idx + 1}"
            text = line.strip()
            if allowlist:
                matched: tuple[AllowEntry, str] | None = None
                for entry in allowlist:
                    how = _entry_matches(entry, _rel(path), idx + 1, text)
                    if how:
                        matched = (entry, how)
                        break
                if matched is not None:
                    entry, how = matched
                    if how == "anchor" and drift_report is not None:
                        drift_report.append(
                            f"{entry.key} 按锚点「{entry.anchor}」命中第 {idx + 1} 行（行号已漂移，内容未变）"
                        )
                    continue
            findings.append(f"{key}: {text[:160]}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="文档 arXiv/DOI 引用核验")
    parser.add_argument("--online", action="store_true", help="在线存在性核验（默认仅离线清单）")
    parser.add_argument(
        "--no-strict", action="store_true", help="在线模式下 missing 降为警告（默认 missing 即退出码 1）"
    )
    parser.add_argument("--files", nargs="*", default=[], help="附加扫描文件（相对仓库根或绝对路径）")
    parser.add_argument(
        "--traceability",
        action="store_true",
        help="额外检查：数值型外部引用是否带 DOI/arXiv/URL（机械可判定的一半）",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="扫描面为空时视为通过（默认：为空即 FAIL——防门禁因文件被删而静默失效）",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        help=f"豁免清单路径（默认 {DEFAULT_ALLOWLIST}；每行 `相对路径:行号`）",
    )
    args = parser.parse_args(argv)

    files = collect_files(args.files)
    if not files:
        # 2026-10-10 修复：此前为空时 exit 0 → 门禁随文档删除而静默失效。
        msg = "[FAIL] 未找到任何扫描目标（DEFAULT_GLOBS 无命中且未指定 --files）" + (
            "——门禁失效，请检查目标文档是否被误删" if not args.allow_empty else ""
        )
        print(msg)
        return 0 if args.allow_empty else 1

    all_arxiv: set[str] = set()
    all_dois: set[str] = set()
    for path in files:
        arxiv_ids, dois = extract_refs(path.read_text(encoding="utf-8", errors="replace"))
        all_arxiv |= arxiv_ids
        all_dois |= dois
        print(f"[INFO] {_rel(path)}: arXiv×{len(arxiv_ids)} DOI×{len(dois)}")

    print(f"\n[INFO] 去重后引用：arXiv×{len(all_arxiv)} DOI×{len(all_dois)}")
    for aid in sorted(all_arxiv):
        print(f"  arXiv:{aid}")
    for doi in sorted(all_dois):
        print(f"  DOI:{doi}")

    if args.traceability:
        allowlist = load_allowlist(args.allowlist)
        drift: list[str] = []
        trace_findings = scan_traceability(files, allowlist=allowlist, drift_report=drift)
        if trace_findings:
            print(f"\n[FAIL] 可追溯性检查：{len(trace_findings)} 处数值型外部引用缺少 DOI/arXiv/URL")
            for item in trace_findings:
                print(f"  {item}")
            print(
                "\n修复：为该引用补 DOI / arXiv ID / URL；无法追溯的引用应删除（口径见 REVIEW_2026_FRONTIER.md §3.6）。"
            )
            return 1
        print("\n[INFO] 可追溯性检查通过：未发现缺标识的数值型外部引用。")
        if drift:
            print(f"[INFO] 另有 {len(drift)} 条豁免按内容锚点命中（行号已漂移，内容未变）：")
            for item in drift:
                print(f"  - {item}")

    if not args.online:
        return 0

    print("\n[INFO] 在线核验（存在性，非内容正确性）……")
    missing: list[str] = []
    for aid in sorted(all_arxiv):
        status, detail = check_url_exists(f"https://arxiv.org/abs/{aid}")
        print(f"  arXiv:{aid} -> {status} ({detail})")
        if status == "missing":
            missing.append(f"arXiv:{aid}")
    for doi in sorted(all_dois):
        status, detail = check_url_exists(f"https://doi.org/{doi}")
        print(f"  DOI:{doi} -> {status} ({detail})")
        if status == "missing":
            missing.append(f"DOI:{doi}")

    if missing:
        if args.no_strict:
            print(f"[WARN] 疑似失效引用（--no-strict，不阻断）：{', '.join(missing)}")
            return 0
        print(f"[FAIL] 疑似失效引用：{', '.join(missing)}")
        return 1
    print("[INFO] 在线核验完成：无 missing（network_error 不计失败）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
