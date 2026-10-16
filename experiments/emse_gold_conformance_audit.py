#!/usr/bin/env python3
"""emse_gold_conformance_audit.py — 基准 gold 材料自洽性审计（零 LLM，2026-10-15 批次九）。

背景（批次九测量有效性发现，EMSE 投稿口径）：
    M1 三段判定（`detection_rate`）要求生成套件在 **gold 修复代码** 上
    `rc == 0` 才可能判为检出（`experiments/_m1_metrics.py::_compute_detection_rate`）。
    因此「**gold 材料自身在其 gold 目标代码上通过**」是整个 detection /
    repair / false_fix 度量族的**隐含前提**。此前从未对三项基准做过该前提
    的端到端审计，而批次八已在 ULT 侧发现官方 gold 71/71 不一致（gold 参照
    作废）。本脚本把该审计推广到**三项基准全体**，零 LLM 可复算。

已发现的缺陷（本脚本的判别式输出，见 RESULTS）：
    1. **synthetic 模板 `import45_shadow_builtin` 的 gold 套件永不通过**
       （`src/datasets/synthetic_dataset.py`）：模板 gold 测试内含
       **函数体内**的 `import import45_shadow_builtin as m`，而
       `_neutralize_gold_imports()` 的**行级**正则
       （`^(\\s*import )<pattern>(\\s*$)`）要求模块 token 后即行尾，
       `... as m` 尾巴使其**不匹配** ⇒ 模块名未被中性化重写为
       `task_XXXX` ⇒ `ModuleNotFoundError` ⇒ gold 套件恒红 ⇒ 该任务在
       `detection_rate` 口径下**结构性不可检出**（不是能力问题）。
       影响面：主批次 R-P0-2（synthetic n=87 × 3 种子）中 25/261 任务
       （9.6%），且**偏向压低 aitester**（该任务上 aitester 检出 0/23，
       plain_llm_df 19/25）。
    2. **QuixBugs gold 材料可用性上限**：50 程序中 31 个程序的官方测试经
       `load_testdata.load_json_testcases` 读取 `json_testcases/<prog>.json`，
       而该目录在上游仓库仅含 31 个 json（且不含全部程序）⇒ 环境变量
       `AITESTER_QUIXBUGS_DATA` 未配置时该 31 任务在 `_packaged_support_ready`
       fail-closed 记 None；配置后仍因缺 json 而收集失败（rc=2）⇒ 记为
       不可测（不误报 0）。加上 9 个 `<prog>_test` 驱动程序无官方测试材料，
       QuixBugs50 的 detection 可测上限 = 35 任务（= M4 四臂实测 N=35，吻合）。
    3. **ULT gold**：官方 `test_list` 在物化目标代码上 71/71 失败，归因诊断
       见 `experiments/emse_ult_gold_diagnosis.py`（独立脚本）。

零 LLM 纪律：本脚本只读数据集加载器材料（本地克隆 / 生成器模板）并在临时
目录内运行 pytest，**不触发任何 LLM 调用**，不改动任何数据集材料（基准冻结：
归档批次工件依赖逐字节相同的任务材料，修正须另立版本与重跑）。

用法：
    AITESTER_QUIXBUGS_DATA=~/.cache/aitester/quixbugs \\
        python experiments/emse_gold_conformance_audit.py --out experiments/results/emse_gold_conformance_20261015
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments._m1_metrics import (  # noqa: E402
    _extract_gold_material,
    _gold_fixed_code,
    _needs_quixbugs_support,
    _run_pytest_in_tmp,
)
from src.utils.atomic_io import atomic_write_json  # noqa: E402

RUN_TIMEOUT_S = 30

# synthetic 主批次口径（R-P0-2 预注册：n=87 × 3 种子 × max_pattern_repeat=2）
SYNTH_SEEDS: tuple[int, ...] = (42, 43, 44)
SYNTH_TASK_COUNT = 87
SYNTH_MAX_PATTERN_REPEAT = 2

# 显式判别式：gold 套件中残留的「模板名形态」import（中性化未生效的指纹）。
# 只认 import 行首形态，避免正文同名词误报（与 _neutralize_gold_imports 同口径）。
_STALE_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_]\w*)\b", re.MULTILINE)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _classify_failure(out: str, err: str, rc: int | None) -> str:
    """gold 套件失败签名分类（判别式，逐条可复核）。"""
    blob = f"{out}\n{err}"
    if "ERROR collecting" in blob or rc == 2:
        if "No module named" in blob:
            m = re.search(r"No module named '([^']+)'", blob)
            return f"collection_error:missing_module:{m.group(1) if m else '?'}"
        if "FileNotFoundError" in blob:
            return "collection_error:missing_fixture_file"
        return "collection_error:other"
    if rc == 5 or "no tests ran" in blob:
        return "no_tests_collected"
    if "FAILED" in blob:
        return "assertion_failure"
    return "other"


# 合法 import token（非「模板残留」）：标准库/第三方 + 项目物化辅助件。
# 注意 `python_programs` / `correct_python_programs` 是 QuixBugs 官方测试的
# **规范包结构导入**（`from python_programs.<prog> import <fn>`），不是残留。
_ALLOWED_IMPORT_TOKENS: frozenset[str] = frozenset(
    {
        "pytest",
        "os",
        "sys",
        "re",
        "json",
        "math",
        "random",
        "itertools",
        "functools",
        "collections",
        "typing",
        "string",
        "copy",
        "time",
        "logging",
        "datetime",
        "io",
        "load_testdata",
        "module_a",
        "module_b",
        "module_c",
        "python_programs",
        "correct_python_programs",
    }
)


def _stale_import_modules(test_code: str, module_name: str) -> list[str]:
    """gold 测试中 import 了「非本人模块名」且非合法辅助件的 token 列表。

    判别式用途：把 synthetic 的**模板残留**（`import45_shadow_builtin` ——
    `_neutralize_gold_imports` 行级正则因 `... as m` 尾巴未匹配 ⇒ 模块名未
    中性化）与合法导入（标准库 / node / load_testdata / module_a-c /
    python_programs 包结构 / 本人中性名）区分开。
    """
    allowed = _ALLOWED_IMPORT_TOKENS | {module_name}
    found: list[str] = []
    for tok in _STALE_IMPORT_RE.findall(test_code or ""):
        if tok in allowed or tok.startswith("task_"):
            continue
        found.append(tok)
    return sorted(set(found))


def _audit_one(tag: str, task: Any) -> dict[str, Any]:
    """单任务 gold 自洽性判定（gold 套件 vs gold 目标代码）。"""
    md = dict(getattr(task, "metadata", None) or {})
    module_name = str(getattr(task, "task_id", "")).split("__")[-1]
    mat = _extract_gold_material(task)
    gold = (md.get("test_cases") or "").strip()
    fixed = _gold_fixed_code(task)
    rec: dict[str, Any] = {
        "set": tag,
        "task_id": str(getattr(task, "task_id", "")),
        "cross_file": bool(md.get("is_cross_file")),
        "needs_quixbugs_support": bool(_needs_quixbugs_support(gold)),
        "stale_imports": _stale_import_modules(gold, module_name),
    }
    if not gold or not fixed.strip():
        rec["status"] = "material_missing"
        rec["missing"] = [k for k, v in (("test_cases", gold), ("fixed", fixed)) if not v.strip()]
        return rec
    res = _run_pytest_in_tmp(
        gold,
        fixed,
        mat[0] if mat else module_name,
        task_metadata=md,
        timeout=RUN_TIMEOUT_S,
    )
    if res is None:
        rec["status"] = "unmeasurable"
        rec["reason"] = "fail-closed（辅助材料缺失 / 超时）"
        return rec
    rc, out, err = res
    rec["rc"] = rc
    rec["status"] = "pass" if rc == 0 else "fail"
    if rc != 0:
        rec["failure_class"] = _classify_failure(out or "", err or "", rc)
        rec["tail"] = (out or "").strip().splitlines()[-1][:120] if (out or "").strip() else ""
    return rec


def audit_synthetic() -> list[dict[str, Any]]:
    from src.datasets.synthetic_dataset import SyntheticDataset

    rows: list[dict[str, Any]] = []
    for seed in SYNTH_SEEDS:
        ds = SyntheticDataset(
            task_count=SYNTH_TASK_COUNT,
            seed=seed,
            max_pattern_repeat=SYNTH_MAX_PATTERN_REPEAT,
        )
        ds._ensure_loaded()  # 加载器公开面无 load()；与归档批次同口径
        for task in ds.tasks:
            rec = _audit_one("synthetic", task)
            rec["seed"] = seed
            rows.append(rec)
        print(f"[synthetic] seed {seed} 完成（{len(ds.tasks)} 任务）", flush=True)
    return rows


def audit_quixbugs() -> list[dict[str, Any]]:
    from src.datasets.dataset_realbugs import QuixBugsDataset

    ds = QuixBugsDataset()
    ds._ensure_loaded()
    rows = [_audit_one("quixbugs", task) for task in ds.tasks]
    print(f"[quixbugs] 完成（{len(rows)} 任务）", flush=True)
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """分组汇总（口径：status × set / seed；漏洞签名 Top-N）。"""
    out: dict[str, Any] = {}
    groups: dict[str, list[dict[str, Any]]] = {}
    for rec in rows:
        key = rec["set"] if rec["set"] != "synthetic" else f"synthetic_seed{rec.get('seed')}"
        groups.setdefault(key, []).append(rec)
    groups["ALL"] = rows
    for key, items in groups.items():
        out[key] = {
            "n": len(items),
            "status": dict(Counter(r["status"] for r in items)),
            "failure_classes": dict(
                Counter(r.get("failure_class", "") for r in items if r["status"] == "fail").most_common()
            ),
            "stale_import_tasks": [r["task_id"] for r in items if r["status"] == "fail" and r.get("stale_imports")],
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPO / "experiments/results/emse_gold_conformance_20261015"))
    ap.add_argument("--skip-quixbugs", action="store_true", help="只审 synthetic（快速通道）")
    ap.add_argument("--skip-synthetic", action="store_true", help="只审 QuixBugs")
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    if not args.skip_synthetic:
        rows.extend(audit_synthetic())
    if not args.skip_quixbugs:
        rows.extend(audit_quixbugs())

    report = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "caliber": {
            "predicate": "gold test_cases 在 gold fixed 目标代码上 rc==0（30s 界）",
            "timeout_s": RUN_TIMEOUT_S,
            "synthetic": {
                "n": SYNTH_TASK_COUNT,
                "seeds": list(SYNTH_SEEDS),
                "max_pattern_repeat": SYNTH_MAX_PATTERN_REPEAT,
            },
            "note": "零 LLM；只读数据集材料；不改动基准（冻结）",
        },
        "summary": summarize(rows),
        "rows": rows,
    }
    json_path = out_dir / "GOLD_CONFORMANCE.json"
    atomic_write_json(json_path, report, indent=1, mode=0o644)

    # 人类可读摘要
    lines = ["# 基准 gold 材料自洽性审计（零 LLM）", ""]
    for key, blk in report["summary"].items():
        lines.append(f"## {key}（n={blk['n']}）")
        lines.append(f"- status: {blk['status']}")
        if blk["failure_classes"]:
            lines.append(f"- 失败签名: {blk['failure_classes']}")
        if blk["stale_import_tasks"]:
            lines.append(f"- 模板残留 import 任务: {len(blk['stale_import_tasks'])} 例")
        lines.append("")
    (out_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")

    sums = out_dir / "SHA256SUMS.txt"
    sums.write_text(
        "".join(f"{_sha256(p)}  {p.name}\n" for p in (json_path, out_dir / "README.md")),
        encoding="utf-8",
    )

    print(json.dumps(report["summary"], ensure_ascii=False, indent=1))
    print(f"\n工件: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
