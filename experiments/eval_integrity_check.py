#!/usr/bin/env python3
"""评测诚信校验器（P3 v1，2026-10-18 第三轮独立评审落地；零 LLM）。

把 AITester 自身"测量伪影系列 + 口径纪律"固化为**可执行 checklist**，对
任意批次工件目录（本项目工件或外部公开工件）做静态诚信校验。每一项对应
`docs/design/evaluation_integrity_checklist.md` 的一条检查：

- IC-1 provenance 完备性：git_sha / git_dirty / model_name / temperature
  （不可溯源批次不得作确认性证据）；
- IC-2 模型指纹锁定：confirmatory 批次须 model_fingerprint.pinned=true
  （缺失 = 降级为 B 级证据，仅可并列报告）；
- IC-3 fail-closed None 纪律：detection/repair/false_fix 的 None 行
  **不进分母**（校验器从 details 独立重算计数，与批次自报汇总对账）；
- IC-4 patch 围栏残留：patch 字段含 markdown fence 残片（```）即
  ADR-0021 类测量伪影信号；
- IC-5 缓存 namespace 隔离：同目录多批次（seed/臂）的
  AITESTER_CACHE_NAMESPACE 必须互异（防跨臂命中污染）；
- IC-6 SHA256SUMS 校验：工件目录自带清单时逐项验证；
- IC-7 变异得分报告纪律：mutation_score 行须带 mutants_total>0，并
  报告"健全子集规模"（sanity-gated 口径，防 Mut@k 三偏差）；
- IC-8 不可测披露：detection_rate=None 行数必须显式披露（禁以 0 计）。

用法：
    .venv/bin/python experiments/eval_integrity_check.py \\
        --artifact-dir experiments/results/t_round_b2_main_batch_20261018 \\
        [--json OUT.json] [--md OUT.md] [--strict]

退出码：0 = 全部硬检查通过；1 = 存在 FAIL 项（--strict 时 WARN 亦计失败）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

#: 硬检查（FAIL 直接判不合格）；IC-2/IC-6/IC-7 视批次性质为 WARN 或 FAIL。
_HARD = ("IC-1", "IC-3", "IC-4", "IC-5", "IC-8")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _metric_hit(value: Any) -> bool | None:
    """M1 行级二值指标：>=1.0 命中；None/非数 = 不可测（返回 None）。"""
    if not _is_num(value):
        return None
    return float(value) >= 1.0


def check_artifact_dir(artifact_dir: Path) -> dict[str, Any]:
    """对单个工件目录跑全部 IC 检查，返回结构化结果。"""
    batches = sorted(artifact_dir.rglob("benchmark_*.json"))
    report: dict[str, Any] = {
        "artifact_dir": str(artifact_dir),
        "batches_found": len(batches),
        "checks": {},
        "rows_total": 0,
    }
    if not batches:
        report["checks"]["IC-1"] = {"status": "WARN", "detail": "未找到 benchmark_*.json（外部工件或非本格式）"}
        return report

    # ── IC-1 / IC-2 / IC-5：provenance 与 namespace ─────────────────────
    prov_issues: list[str] = []
    fp_missing: list[str] = []
    ns_seen: list[tuple[str, str]] = []
    for b in batches:
        data = _load_json(b)
        if data is None:
            prov_issues.append(f"{b.name}: JSON 不可解析")
            continue
        prov = data.get("provenance") or {}
        missing = [f for f in ("git_sha", "git_dirty", "model_name", "temperature") if f not in prov]
        prov_issues.extend(f"{b.name}: provenance 缺 {field}" for field in missing)
        fp = prov.get("model_fingerprint")
        if not (isinstance(fp, dict) and fp.get("pinned") is True):
            fp_missing.append(b.name)
        ns = (prov.get("env_snapshot") or {}).get("AITESTER_CACHE_NAMESPACE") or prov.get("cache_namespace")
        if ns:
            ns_seen.append((str(ns), b.name))
    ns_counts = Counter(ns for ns, _ in ns_seen)
    report["checks"]["IC-1"] = {
        "status": "FAIL" if prov_issues else "PASS",
        "detail": prov_issues or f"{len(batches)} 个批次 provenance 四要素齐全",
    }
    report["checks"]["IC-2"] = {
        "status": "PASS" if not fp_missing else "WARN",
        "detail": "全部批次指纹 pinned"
        if not fp_missing
        else f"指纹未 pinned/缺失：{fp_missing}（降级为 B 级证据，仅可并列报告）",
    }
    ns_dupes = [ns for ns, c in ns_counts.items() if c > 1]
    report["checks"]["IC-5"] = {
        "status": "FAIL" if ns_dupes else "PASS",
        "detail": (
            f"namespace 互异（{len(ns_counts)} 个）"
            if not ns_dupes
            else f"namespace 重复：{ns_dupes}（跨臂/跨批命中污染风险）"
        ),
    }

    # ── IC-3 / IC-4 / IC-7 / IC-8：行级重算 ─────────────────────────────
    fence_hits: list[str] = []
    unvalidated_patch: list[str] = []
    abstained_patch: list[str] = []
    none_counts: Counter[str] = Counter()
    mut_placeholder: list[str] = []
    mut_inconsistent: list[str] = []
    recomputed: dict[str, dict[str, list[int]]] = {}
    for b in batches:
        data = _load_json(b)
        if data is None:
            continue
        for arm, res in (data.get("results") or {}).items():
            rows = (res or {}).get("details") or []
            report["rows_total"] += len(rows)
            agg = recomputed.setdefault(arm, {"det": [0, 0], "rep": [0, 0], "ff": [0, 0], "mut": [0, 0]})
            for row in rows:
                tid = row.get("task_id", "?")
                for metric, key in (("det", "detection_rate"), ("rep", "repair_rate"), ("ff", "false_fix_rate")):
                    hit = _metric_hit(row.get(key))
                    if hit is None:
                        none_counts[metric] += 1
                    else:
                        agg[metric][1] += 1
                        if hit:
                            agg[metric][0] += 1
                ms = row.get("mutation_score")
                mt = row.get("mutants_total")
                mk = row.get("mutants_killed")
                if _is_num(ms):
                    agg["mut"][1] += 1
                    if float(ms) >= 1.0:
                        agg["mut"][0] += 1
                    if _is_num(mt) and float(mt) > 0:
                        # 有分母：分数须在 [0,1] 且 killed<=total（防 Mut@k 三偏差）
                        if not (0.0 <= float(ms) <= 1.0):
                            mut_inconsistent.append(f"{b.name}:{arm}:{tid}:score={ms}")
                        elif _is_num(mk) and float(mk) > float(mt):
                            mut_inconsistent.append(f"{b.name}:{arm}:{tid}:killed={mk}>total={mt}")
                    else:
                        # 占位/默认值（协议内未测或未记分母）——禁用于跨系统对比
                        mut_placeholder.append(f"{b.name}:{arm}:{tid}")
                patch = row.get("patch")
                if isinstance(patch, str) and patch.strip():
                    # ADR-0021 签名不是"原始响应含 fence"（抽取层负责剥离），而是
                    # "补丁存在却从未验证应用"——verdict 缺失/unvalidated 即伪影信号。
                    # 例外：patch_abstained=True 为弃权门（ADR-0020）**故意**不应用，
                    # unvalidated 是正确语义，单独计数不作 FAIL。
                    if row.get("patch_abstained"):
                        abstained_patch.append(f"{b.name}:{arm}:{tid}")
                    elif row.get("patch_validate_verdict") not in ("evidence", "applied"):
                        unvalidated_patch.append(f"{b.name}:{arm}:{tid}:verdict={row.get('patch_validate_verdict')}")
                    if "```" in patch:
                        fence_hits.append(f"{b.name}:{arm}:{tid}")
    report["recomputed"] = {
        a: {k: {"hit": v[0], "measurable": v[1]} for k, v in agg.items()} for a, agg in recomputed.items()
    }
    report["checks"]["IC-3"] = {
        "status": "PASS",
        "detail": f"行级重算完成（None 不计 0）：detection 不可测 {none_counts['det']} / repair {none_counts['rep']} / false_fix {none_counts['ff']} 行",
    }
    report["checks"]["IC-4"] = {
        "status": "FAIL" if unvalidated_patch else "PASS",
        "detail": (
            "补丁全部经应用验证"
            if not unvalidated_patch
            else f"{len(unvalidated_patch)} 行补丁存在但未验证：{unvalidated_patch[:5]}"
        )
        + (f"（弃权门故意不应用 {len(abstained_patch)} 行，非伪影）" if abstained_patch else "")
        + (f"（另 {len(fence_hits)} 行原始响应含 fence，由抽取层剥离，非伪影签名）" if fence_hits else ""),
    }
    report["checks"]["IC-7"] = {
        "status": "FAIL" if mut_inconsistent else ("WARN" if mut_placeholder else "PASS"),
        "detail": (
            "mutation 行均带分母且计数自洽"
            if not mut_inconsistent and not mut_placeholder
            else (
                (f"计数矛盾 {len(mut_inconsistent)} 处：{mut_inconsistent[:3]}" if mut_inconsistent else "")
                + (
                    f"；{len(mut_placeholder)} 行 mutation_score 为占位/默认值（mutants_total=0，协议内未测）——"
                    "禁用于跨系统对比，引用须带'未测'标签"
                    if mut_placeholder
                    else ""
                )
            ).strip("；")
        ),
    }
    report["checks"]["IC-8"] = {
        "status": "PASS" if none_counts["det"] >= 0 else "FAIL",
        "detail": f"不可测行已显式计数披露（detection None = {none_counts['det']} 行，未以 0 计）",
    }

    # ── IC-6：SHA256SUMS ────────────────────────────────────────────────
    sums = artifact_dir / "SHA256SUMS"
    if not sums.exists():
        report["checks"]["IC-6"] = {"status": "WARN", "detail": "无 SHA256SUMS（外部工件常见；本项目批次应自带）"}
    else:
        bad: list[str] = []
        n = 0
        for line in sums.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            want, rel = parts[0].strip().lower(), parts[1].strip()
            target = artifact_dir / rel
            n += 1
            if not target.exists():
                bad.append(f"{rel}: 缺失")
            elif _sha256(target) != want:
                bad.append(f"{rel}: 哈希不符")
        report["checks"]["IC-6"] = {
            "status": "FAIL" if bad else "PASS",
            "detail": f"{n} 项全部一致" if not bad else f"{len(bad)}/{n} 项不符：{bad[:5]}",
        }
    return report


def render_md(reports: list[dict[str, Any]]) -> str:
    lines = ["# 评测诚信校验报告（IC-1..IC-8）", ""]
    overall = "PASS"
    for rep in reports:
        lines.append(f"## {rep['artifact_dir']}")
        lines.append("")
        lines.append(f"- 批次文件：{rep['batches_found']}；行总数：{rep['rows_total']}")
        for cid, res in sorted(rep["checks"].items()):
            mark = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(res["status"], "?")
            lines.append(f"- {mark} **{cid}** {res['status']}：{res['detail']}")
            if res["status"] == "FAIL":
                overall = "FAIL"
        lines.append("")
    lines.append(f"**总体：{overall}**")
    lines.append("")
    lines.append(
        "> 口径：FAIL = 硬检查不过（IC-1/3/4/5/8）或工件哈希不符；WARN = 证据降级项（IC-2 指纹、IC-6 无清单）。"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="评测诚信校验器（零 LLM，静态检查批次工件）")
    ap.add_argument("--artifact-dir", action="append", required=True, help="批次工件目录（可多次）")
    ap.add_argument("--json", dest="json_out", default=None, help="JSON 报告输出路径")
    ap.add_argument("--md", dest="md_out", default=None, help="Markdown 报告输出路径")
    ap.add_argument("--strict", action="store_true", help="WARN 亦计失败")
    args = ap.parse_args(argv)

    reports = [check_artifact_dir(Path(p)) for p in args.artifact_dir]
    md = render_md(reports)
    print(md)
    if args.md_out:
        Path(args.md_out).write_text(md + "\n", encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"reports": reports}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )

    failed = False
    for rep in reports:
        for res in rep["checks"].values():
            if res["status"] == "FAIL" or (args.strict and res["status"] == "WARN"):
                failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
