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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 默认扫描面：原 5 份根目录前沿基线综述（*_BASELINE_2023-2026.md）与
# docs/frontier-baseline / 审查报告已于 2026-10-09 清理批次删除（见
# CHANGELOG.md R5 批次说明），当前 DEFAULT_GLOBS 无命中时脚本打印 WARN
# 跳过（内置兜底，不产生失败）；需要核验时通过 --files 显式指定。
DEFAULT_GLOBS: list[str] = []

ARXIV_ID_RE = re.compile(r"\b(?:arXiv:|arxiv\.org/abs/)(\d{4}\.\d{4,5})(?:v\d+)?\b", re.IGNORECASE)
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>\]\)，。；]+)")

_TIMEOUT_S = 5.0
# arXiv 对高频 HEAD 有限流：小 sleep + 单次重试
_RETRY_ONCE_HOSTS = ("arxiv.org",)


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
    # 去重保序
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in files:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="文档 arXiv/DOI 引用核验")
    parser.add_argument("--online", action="store_true", help="在线存在性核验（默认仅离线清单）")
    parser.add_argument(
        "--no-strict", action="store_true", help="在线模式下 missing 降为警告（默认 missing 即退出码 1）"
    )
    parser.add_argument("--files", nargs="*", default=[], help="附加扫描文件（相对仓库根或绝对路径）")
    args = parser.parse_args(argv)

    files = collect_files(args.files)
    if not files:
        print("[WARN] 未找到任何扫描目标（DEFAULT_GLOBS 无命中且未指定 --files）")
        return 0

    all_arxiv: set[str] = set()
    all_dois: set[str] = set()
    for path in files:
        arxiv_ids, dois = extract_refs(path.read_text(encoding="utf-8", errors="replace"))
        all_arxiv |= arxiv_ids
        all_dois |= dois
        print(f"[INFO] {path.relative_to(PROJECT_ROOT)}: arXiv×{len(arxiv_ids)} DOI×{len(dois)}")

    print(f"\n[INFO] 去重后引用：arXiv×{len(all_arxiv)} DOI×{len(all_dois)}")
    for aid in sorted(all_arxiv):
        print(f"  arXiv:{aid}")
    for doi in sorted(all_dois):
        print(f"  DOI:{doi}")

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
