#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WS2 独立指标重算（只读原始工件；不读任何 .md）。

用法：
    python _independent_audit/ws2_recompute.py                 # 全部节
    python _independent_audit/ws2_recompute.py --sections 1,2  # 指定节
    python _independent_audit/ws2_recompute.py --jobs 8        # 重放并发度

纪律
----
1. 本脚本的数据来源**只有**原始工件：benchmark_*.json / traces/*.jsonl /
   *.log / SHA256SUMS / price_table.json / 数据集 jsonl。脚本内不读任何 .md
   （既有报告与 BASELINE.yaml 只作为"被核对的声称值"，写死在 CLAIMS 表里）。
2. 仓库内**只读**：不创建、不修改、不删除仓库内任何文件。
   第 2 节重放会写 pytest 临时工作树，但只写 tempfile.mkdtemp() 目录
   （仓库之外）并在结束后清理。
3. 算不出来就打印「无法重算」+ 原因，不推测填充。

节：
  0  schema 转储
  1  detection（三臂 / R-P0-2 三种子合并）
  2  repair（独立重放：修正口径 vs 原口径）
  3  false_fix（原字段口径 / 修正重放口径 / 历史批）
  4  coverage / mutation_score / spec 指标区间
  5  SWE-bench 外部有效性证据
  6  SHA256SUMS 抽样校验
  7  统计显著性（McNemar + 聚类 + 贝叶斯 Dirichlet）
  8  成本 $/task（价目表）
  9  测试套件收集数/通过数
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import glob
import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # 仅用于交叉核验项目 normalize（非我方数字来源）
MB = ROOT / "experiments" / "results" / "main_batch"
R2_FILES = [
    "benchmark_synthetic_20261006_140906.json",  # seed 42
    "benchmark_synthetic_20261006_151907.json",  # seed 43
    "benchmark_synthetic_20261006_164357.json",  # seed 44
]
E2_FILES = [
    "benchmark_synthetic_20261007_170147.json",
    "benchmark_synthetic_20261007_161053.json",
]
ARMS = ["aitester", "plain_llm", "plain_llm_df"]

# ── 被核对的"声称值"（来自项目 .md / BASELINE.yaml / 任务书；本脚本不读 .md）──
CLAIMS = {
    "det_aitester": 0.158, "det_plain_llm": 0.015, "det_plain_llm_df": 0.448,
    "det_pool_n": 261,
    "repair_corrected": 0.3931, "repair_corrected_num": 57, "repair_corrected_den": 145,
    "repair_v1": 0.3586, "repair_v1_num": 52,
    "repair_e2_corrected": 0.5472, "repair_e2_num": 58, "repair_e2_den": 106,
    "false_fix_main": 0.872, "false_fix_main_num": 380, "false_fix_main_den": 436,
    "false_fix_hist": 0.898,
    "cov_aitester_lo": 84.0, "cov_aitester_hi": 93.6,
    "cov_plain_llm_lo": 86.0, "cov_plain_llm_hi": 97.2,
    "spec_compile": 0.21, "spec_expr": 0.73,
    "cost_aitester": 0.0259, "cost_df": 0.0045,
    "tests_total_passed": 5389, "tests_skipped": 3, "tests_xfailed": 1,
    "delta_e2": -0.3673, "delta_e2_ci": [-0.4552, -0.2785],
    "delta_pool": -0.279, "delta_pool_ci": [-0.348, -0.209],
    "swe_lite20": "0/20",
}

PRICE = None  # 运行时从 price_table.json 载入


# ─────────────────────────── 通用 ───────────────────────────
def hr(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def load(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def batch_files() -> list[Path]:
    return [Path(p) for p in sorted(glob.glob(str(MB / "benchmark_*.json")))]


def rows_of(batch: dict, arm: str) -> list[dict]:
    return ((batch.get("results") or {}).get(arm) or {}).get("details") or []


def frac(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


# ─────────────────────────── 0 schema ───────────────────────────
def sec0() -> None:
    hr("§0 schema（实际看到的字段）")
    f = MB / R2_FILES[0]
    d = load(f)
    print(f"文件示例：{f.relative_to(ROOT)}")
    print("\n[顶层键]")
    for k, v in d.items():
        t = type(v).__name__
        n = f" len={len(v)}" if isinstance(v, (list, dict)) else f" = {v!r}"[:80]
        print(f"  {k:22s} {t}{n}")
    print("\n[results.<arm> 汇总键]")
    for arm, av in d["results"].items():
        print(f"  {arm:14s} {sorted(av.keys())}")
    r0 = rows_of(d, "aitester")[0]
    print(f"\n[details[i] 行键] 共 {len(r0)} 个")
    for k in sorted(r0.keys()):
        v = r0[k]
        t = type(v).__name__
        s = "" if isinstance(v, (dict, list)) else f" = {str(v)[:40]!r}"
        print(f"  {k:32s} {t}{s}")
    print("\n[task_metadata 键（gold 材料所在）]")
    print(" ", sorted((r0.get("task_metadata") or {}).keys()))
    print("\n[检测指标语义（从 experiments/_m1_metrics.py 反推，非 .md）]")
    print("  detection_rate = F2P 三段判定：buggy 上 rc!=0（且非收集/语法错误）")
    print("                   AND gold-fixed 上 rc==0（且非收集/语法错误）→ 1.0，否则 0.0")
    print("  repair_rate    = safe_apply(patch) 后 gold test_cases 跑 rc==0 → 1.0")
    print("  false_fix_rate = passed==True AND repair_rate==0.0 → 1.0")
    print("  test_error_rate= buggy 侧 rc>=2 或收集/语法错误标记 → 1.0")


# ─────────────────────────── 1 detection ───────────────────────────
def _det_counts(det: list[dict]) -> tuple[int, int, int]:
    """返回 (阳性, 可测, 缺失)。detection_rate 为 0/1 或 None。"""
    pos = sum(1 for r in det if r.get("detection_rate") == 1.0)
    miss = sum(1 for r in det if r.get("detection_rate") is None)
    other = sum(1 for r in det if r.get("detection_rate") not in (None, 0.0, 1.0))
    return pos, len(det) - miss, miss + other


def sec1() -> dict:
    hr("§1 detection（R-P0-2 三种子合并）")
    files = [MB / n for n in R2_FILES]
    print("纳入文件（按 seed 42/43/44，n=87 each → 261/臂）：")
    for f in files:
        d = load(f)
        print(f"  {f.name}  seed={d.get('seed')}  total_tasks={d.get('total_tasks')}  arms={list(d['results'])}")

    out: dict[str, Any] = {}
    print("\n[逐文件 detection 阳性/可测]")
    for arm in ARMS:
        per = []
        tp = tm = 0
        for f in files:
            d = load(f)
            pos, meas, miss = _det_counts(rows_of(d, arm))
            per.append((f.name, pos, meas, miss))
            tp += pos
            tm += meas
        out[arm] = {"pos": tp, "measurable": tm, "missing": 261 - tm, "rate_measurable": frac(tp, tm),
                    "rate_261": frac(tp, 261), "per_file": per}
        print(f"  {arm:14s} " + " | ".join(f"{n[-13:-5]}:{p}/{m}" for n, p, m, _ in per))
        print(f"     合计 阳性={tp}  可测={tm}  缺失={261 - tm}  "
              f"率(可测分母)={frac(tp, tm)}  率(261 分母)={frac(tp, 261)}  声称={CLAIMS['det_' + arm]}")

    print("\n[detection 字段是否严格二值]")
    nonbin = 0
    for f in files:
        d = load(f)
        for arm in ARMS:
            for r in rows_of(d, arm):
                v = r.get("detection_rate")
                if v is not None and v not in (0.0, 1.0):
                    nonbin += 1
    print(f"  非 {0,1,None} 的 detection_rate 行数：{nonbin}（0 = 严格二值，分子=计数）")

    print("\n[通过/自指率（对照声称 passed 143/229/7）]")
    for arm in ARMS:
        p = sum(1 for f in files for r in rows_of(load(f), arm) if r.get("passed"))
        print(f"  {arm:14s} passed={p}/261 = {frac(p, 261)}")

    print("\n[detection 与相邻字段的自洽性（反推定义）]")
    for arm in ARMS:
        c = collections.Counter()
        for f in files:
            for r in rows_of(load(f), arm):
                if r.get("detection_rate") is None:
                    c["None"] += 1
                else:
                    c[(r["detection_rate"], bool(r.get("detection_first_red_seen")))] += 1
        print(f"  {arm:14s} (detection_rate, first_red_seen) → {dict(c)}")
    return out


# ─────────────────────────── 2 repair 重放 ───────────────────────────
_FENCE_RE = re.compile(r"^```[A-Za-z0-9_+.\-]*[ \t]*\r?\n(.*?)\r?\n?```[ \t]*$", re.S)
_LANG_RE = re.compile(r"^\s*(?:python[0-9.]*|py)\s*:?[ \t]*\r?\n", re.I)
_DIFF_PREFIXES = ("diff --git", "@@", "---", "+++", "old ", "new ")


def is_diff_form(patch: str) -> bool:
    return bool(patch) and patch.lstrip().startswith(_DIFF_PREFIXES)


def my_normalize(patch: str) -> str:
    """WS2 自写补丁清理（不复用项目函数）：剥 markdown 围栏 + 语言前缀残留。"""
    t = patch.strip()
    m = _FENCE_RE.match(t)
    if m:
        t = m.group(1)
    t = _LANG_RE.sub("", t, count=1)
    return t.strip("\n")


def module_name_of(task_id: str) -> str:
    return task_id.split("__")[-1].replace("-", "_")[:50]


_MODNAME_RE = re.compile(r"^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import|import\s+([A-Za-z_][\w.]*))", re.M)


def imports_of(test_code: str) -> list[str]:
    out = []
    for a, b in _MODNAME_RE.findall(test_code or ""):
        out.append((a or b).split(".")[0])
    return sorted(set(out))


def run_pytest_tree(test_code: str, target_code: str, module_name: str,
                    meta: dict, timeout: int = 60) -> tuple[int | None, str]:
    """WS2 自写重放执行器（不复用 _m1_metrics）：tmp 目录写模块 + gold 测试后跑 pytest。"""
    d = tempfile.mkdtemp(prefix="ws2_replay_")
    try:
        p = Path(d)
        if meta.get("is_cross_file"):
            target_module = str(meta.get("target_module") or "module_b")
            specs = (("module_a_name", "module_a_code"),
                     ("module_b_name", "module_b_code"),
                     ("module_c_name", "module_c_code"))
            written = set()
            for nk, ck in specs:
                name = str(meta.get(nk) or ck[:-5])
                if name == target_module:
                    (p / f"{name}.py").write_text(target_code, encoding="utf-8")
                    written.add(name)
                    continue
                body = str(meta.get(ck) or "")
                if body.strip():
                    (p / f"{name}.py").write_text(body, encoding="utf-8")
                    written.add(name)
            if target_module not in written:
                (p / f"{target_module}.py").write_text(target_code, encoding="utf-8")
            test_path = p / f"test_{target_module}.py"
        else:
            (p / f"{module_name}.py").write_text(target_code, encoding="utf-8")
            test_path = p / f"test_{module_name}.py"
        test_path.write_text(test_code, encoding="utf-8")
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": d}
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", str(test_path)],
            cwd=d, env=env, capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception as e:  # noqa: BLE001
        return None, f"error: {e!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _replay_one(item: tuple) -> dict:
    path, arm, idx = item
    d = load(path)
    r = rows_of(d, arm)[idx]
    patch = str(r.get("patch") or "")
    meta = r.get("task_metadata") or {}
    tc = str(meta.get("test_cases") or "")
    verdict: dict[str, Any] = {
        "file": Path(path).name, "arm": arm, "task_id": r.get("task_id"),
        "passed": bool(r.get("passed")), "old_patch_correct": r.get("patch_correct"),
        "patch_prefix": patch.lstrip()[:12].replace("\n", "\\n"),
        "is_cross_file": bool(meta.get("is_cross_file")),
    }
    if not patch.strip() or not tc.strip():
        verdict["status"] = "skipped_no_material"
        return verdict
    if is_diff_form(patch):
        verdict["status"] = "not_replayable_diff"
        return verdict
    mname = module_name_of(str(r.get("task_id") or ""))
    verdict["module_name"] = mname
    verdict["test_imports"] = imports_of(tc)
    new_code = my_normalize(patch)
    rc, out = run_pytest_tree(tc, new_code, mname, meta)
    if rc is None:
        verdict["status"] = "unverifiable"
        verdict["detail"] = out[:200]
        return verdict
    verdict["status"] = "correct" if rc == 0 else "wrong_patch"
    verdict["rc"] = rc
    verdict["tail"] = out.strip().splitlines()[-1][:160] if out.strip() else ""
    # 原口径对照：不清理（复现围栏残留伪影）
    rc_raw, _ = run_pytest_tree(tc, patch, mname, meta)
    verdict["raw_status"] = None if rc_raw is None else ("correct" if rc_raw == 0 else "wrong_patch")
    # 反事实变体：跨文件任务若按"单文件口径"判分（忽略 metadata 的伴生模块物化）
    # → 用于独立检验「v1 35.86% → v2 39.31% 归因于 R27 跨文件修复」这一说法。
    if meta.get("is_cross_file"):
        rc_sf, _ = run_pytest_tree(tc, new_code, mname, {})
        verdict["singlefile_status"] = None if rc_sf is None else ("correct" if rc_sf == 0 else "wrong_patch")
    # 与项目 normalize 输出比对（交叉核验，不作为我方数字来源）
    try:
        from src.tools.patch_applier import normalize_patch_text
        verdict["norm_matches_project"] = (normalize_patch_text(patch) == new_code)
    except Exception as e:  # noqa: BLE001
        verdict["norm_matches_project"] = f"import_error: {e!r}"
    return verdict


def sec2(jobs: int) -> dict:
    hr("§2 repair 独立重放（修正口径 vs 原口径）")
    files = batch_files()
    print(f"重放范围：{MB.relative_to(ROOT)} 下 {len(files)} 个 benchmark_*.json，臂 aitester")
    print("重放口径（WS2 自写，与本项目修复后口径同构）：")
    print("  patch 非空 ∧ task_metadata.test_cases 非空 ∧ 非 unified diff → 清理围栏后作为整文件代码")
    print("  → 在 tmp 树跑 gold test_cases → pytest rc==0 记 correct；跨文件任务按 metadata 物化伴生模块。")
    items = []
    for f in files:
        d = load(f)
        for i, r in enumerate(rows_of(d, "aitester")):
            if str(r.get("patch") or "").strip():
                items.append((str(f), "aitester", i))
    print(f"\n带补丁行（patch 非空）共 {len(items)} 行，未清理 vs 清理 各跑一次 → {2 * len(items)} 次 pytest，jobs={jobs}")

    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        for v in ex.map(_replay_one, items):
            results.append(v)

    def gen_of(name: str) -> str:
        if "20261006" in name:
            return "R-P0-2(10-06)"
        if "20261007" in name:
            return "E1/E2(10-07)"
        return "早期(10-01)"

    print("\n[逐代际：带补丁 / 可重放 / 修正 correct / 修正 repair / 原口径 correct]")
    agg: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for v in results:
        g = agg[gen_of(v["file"])]
        g[v["status"]] += 1
        g["rows_with_patch"] += 1
        if v.get("raw_status") == "correct":
            g["raw_correct"] += 1
    totals = collections.Counter()
    print(f"  {'代际':14s} {'带补丁':>6s} {'可重放':>6s} {'correct':>8s} {'repair':>8s} {'原口径correct':>12s}")
    for g, c in agg.items():
        replayable = c["correct"] + c["wrong_patch"]
        print(f"  {g:14s} {c['rows_with_patch']:6d} {replayable:6d} {c['correct']:8d} "
              f"{frac(c['correct'], replayable)!s:>8s} {c['raw_correct']:12d}")
        totals.update(c)
    rep = totals["correct"] + totals["wrong_patch"]
    print(f"  {'合计':14s} {totals['rows_with_patch']:6d} {rep:6d} {totals['correct']:8d} "
          f"{frac(totals['correct'], rep)!s:>8s} {totals['raw_correct']:12d}")

    r2 = agg["R-P0-2(10-06)"]
    r2_rep = r2["correct"] + r2["wrong_patch"]
    print(f"\n  R-P0-2 重算 repair = {r2['correct']}/{r2_rep} = {frac(r2['correct'], r2_rep)}  "
          f"（声称 {CLAIMS['repair_corrected']} = {CLAIMS['repair_corrected_num']}/{CLAIMS['repair_corrected_den']}）")
    e2 = agg["E1/E2(10-07)"]
    e2_rep = e2["correct"] + e2["wrong_patch"]
    print(f"  E1/E2 重算 repair = {e2['correct']}/{e2_rep} = {frac(e2['correct'], e2_rep)}  "
          f"（声称 {CLAIMS['repair_e2_corrected']} = {CLAIMS['repair_e2_num']}/{CLAIMS['repair_e2_den']}）")
    print(f"  原口径（不清理围栏）合计 correct = {totals['raw_correct']}（复现'围栏残留压零'伪影）")
    nm_ok = sum(1 for v in results if v.get("norm_matches_project") is True)
    nm_bad = [v.get("norm_matches_project") for v in results if v.get("norm_matches_project") is not True]
    print(f"  我的清理函数与项目 normalize_patch_text 输出**逐字相同**的行数："
          f"{nm_ok}/{sum(1 for v in results if 'norm_matches_project' in v)}"
          f"；不同/异常样本 {nm_bad[:2]}")
    print(f"  状态分布：{dict(totals)}")
    print(f"  补丁首 12 字符分布（围栏残留证据）："
          f"{dict(collections.Counter(v['patch_prefix'] for v in results).most_common(4))}")
    print(f"  跨文件带补丁行：{sum(1 for v in results if v['is_cross_file'])}")

    print("\n[反事实变体：跨文件行按单文件口径判分（检验 v1→v2 的 R27 归因）]")
    for gen, claim_v1, claim_den in (("R-P0-2(10-06)", 52, 145), ("E1/E2(10-07)", 51, 106)):
        sub = [v for v in results if gen_of(v["file"]) == gen]
        v2 = sum(1 for v in sub if v["status"] == "correct")
        v1 = sum(1 for v in sub
                 if (v["status"] == "correct" and not v["is_cross_file"])
                 or v.get("singlefile_status") == "correct")
        den = sum(1 for v in sub if v["status"] in ("correct", "wrong_patch"))
        xf = sum(1 for v in sub if v["is_cross_file"])
        print(f"  {gen}: 跨文件行={xf}  v2(含物化)={v2}/{den}={frac(v2, den)}  "
              f"v1(单文件口径)={v1}/{den}={frac(v1, den)}  "
              f"差值={v2 - v1}  声称 v1={claim_v1}/{claim_den}={frac(claim_v1, claim_den)}")

    # 漏斗：detection_first_red_seen 为 True 的行 = 进入修复循环
    print("\n[修复漏斗（原始字段，R-P0-2 261 行）]")
    files_r2 = [MB / n for n in R2_FILES]
    funnel = collections.Counter()
    for f in files_r2:
        for r in rows_of(load(f), "aitester"):
            if r.get("detection_first_red_seen"):
                funnel["entered_repair"] += 1
                if str(r.get("patch") or "").strip():
                    funnel["patch_produced"] += 1
                if r.get("patch_plausible") == 1:
                    funnel["plausible"] += 1
    print(f"  进入修复循环(first_red_seen)= {funnel['entered_repair']}/261 = {frac(funnel['entered_repair'], 261)}")
    print(f"  patch 产出          = {funnel['patch_produced']}/{funnel['entered_repair']} "
          f"= {frac(funnel['patch_produced'], funnel['entered_repair'])}（声称 94%）")
    print(f"  plausible           = {funnel['plausible']}/{funnel['entered_repair']} "
          f"= {frac(funnel['plausible'], funnel['entered_repair'])}（声称 47%）")
    print(f"  correct（WS2 重放） = {r2['correct']}/{r2_rep} = {frac(r2['correct'], r2_rep)}（声称 39.31%）")
    return {"results": results, "agg": {k: dict(v) for k, v in agg.items()}, "totals": dict(totals)}


# ─────────────────────────── 3 false_fix ───────────────────────────
def sec3(sec2_out: dict) -> None:
    hr("§3 false_fix（原字段口径 / 修正重放口径 / 历史批）")
    print("[A] 原字段口径（逐行 false_fix_rate，R-P0-2 三文件，三臂）")
    files = [MB / n for n in R2_FILES]
    for arm in ARMS:
        ff1 = n = miss = 0
        for f in files:
            for r in rows_of(load(f), arm):
                v = r.get("false_fix_rate")
                if v is None:
                    miss += 1
                else:
                    n += 1
                    ff1 += 1 if v == 1.0 else 0
        print(f"  {arm:14s} false_fix=1 行 {ff1}/{n} = {frac(ff1, n)}  缺失 {miss}")

    print("\n[B] 历史批（benchmark_synthetic_20261001_121523.json, n=50, aitester）")
    d = load(MB / "benchmark_synthetic_20261001_121523.json")
    det = rows_of(d, "aitester")
    passed = [r for r in det if r.get("passed")]
    ff1 = sum(1 for r in det if r.get("false_fix_rate") == 1.0)
    ffmeas = sum(1 for r in det if r.get("false_fix_rate") is not None)
    passed_ff1 = sum(1 for r in passed if r.get("false_fix_rate") == 1.0)
    # 变体：分母 = detection_rate 可测行（89.8% 声称值的可能来源）
    det_meas = [r for r in det if r.get("detection_rate") is not None]
    var_num = sum(1 for r in det_meas if r.get("passed") and r.get("false_fix_rate") == 1.0)
    print(f"  逐行字段：false_fix=1 行 {ff1}/{ffmeas} = {frac(ff1, ffmeas)}")
    print(f"  passed 行 {len(passed)}，其中 false_fix=1 {passed_ff1} → {frac(passed_ff1, len(passed))}")
    print(f"  变体（分母=detection 可测行 {len(det_meas)}，分子=passed∧ff1 {var_num}）= {frac(var_num, len(det_meas))}"
          f"  ← 与声称 {CLAIMS['false_fix_hist']} 对齐/不符")
    print("  注：BASELINE/README 声称 89.8%；逐行字段口径给 90.0%，差异由分母选择造成。")

    print("\n[C] 修正重放口径（passed ∧ 修正 repair != 1.0；分母 = passed ∧ 可测）")
    res = sec2_out["results"]
    verdict = {(v["file"], v["task_id"]): v for v in res}
    files_all = batch_files()
    num = den = 0
    num_r2 = den_r2 = 0
    for f in files_all:
        d = load(f)
        for idx, r in enumerate(rows_of(d, "aitester")):
            tid = r.get("task_id")
            v = verdict.get((f.name, tid))
            if v is None:
                if str(r.get("patch") or "").strip():
                    continue
                corrected_repair = 0.0  # 无补丁 → repair=0，语义正确（非伪影）
            elif v["status"] == "correct":
                corrected_repair = 1.0
            elif v["status"] in ("wrong_patch",):
                corrected_repair = 0.0
            else:
                corrected_repair = None  # 不可测
            if not r.get("passed"):
                continue
            if corrected_repair is None:
                continue
            den += 1
            num += 1 if corrected_repair != 1.0 else 0
            if f.name in R2_FILES:
                den_r2 += 1
                num_r2 += 1 if corrected_repair != 1.0 else 0
    print(f"  全 main_batch（10 文件 669 行）修正 false_fix = {num}/{den} = {frac(num, den)}"
          f"  （声称 {CLAIMS['false_fix_main']} = {CLAIMS['false_fix_main_num']}/{CLAIMS['false_fix_main_den']}）")
    print(f"  仅 R-P0-2 三文件修正 false_fix = {num_r2}/{den_r2} = {frac(num_r2, den_r2)}")


# ─────────────────────────── 4 覆盖/变异/spec ───────────────────────────
def sec4() -> None:
    hr("§4 coverage / mutation_score / spec 指标区间")
    files = batch_files()
    print("[覆盖 avg_coverage（臂汇总字段）与 mutation_score 行均值]")
    print(f"  {'文件':46s} {'arm':13s} {'coverage':>9s} {'mut_mean':>9s} {'mut_n':>6s} {'spec_c':>8s} {'spec_e':>8s}")
    cov: dict[str, list[tuple[str, float]]] = collections.defaultdict(list)
    mut: dict[str, list[tuple[str, float]]] = collections.defaultdict(list)
    for f in files:
        d = load(f)
        for arm, av in d["results"].items():
            det = av["details"]
            c = av.get("avg_coverage")
            mv = [r.get("mutation_score") for r in det if r.get("mutation_score") is not None]
            sc = [r.get("spec_compile_rate") for r in det if r.get("spec_compile_rate") is not None]
            se = [r.get("spec_expr_coverage") for r in det if r.get("spec_expr_coverage") is not None]
            mm = round(sum(mv) / len(mv), 4) if mv else None
            if c is not None:
                cov[arm].append((f.name, c))
            if mm is not None:
                mut[arm].append((f.name, mm))
            print(f"  {f.name[:46]:46s} {arm:13s} {c!s:>9s} {mm!s:>9s} {len(mv):6d} "
                  f"{(round(sum(sc)/len(sc),4) if sc else None)!s:>8s} {(round(sum(se)/len(se),4) if se else None)!s:>8s}")
    print("\n[区间]")
    for arm in ARMS:
        if cov.get(arm):
            lo = min(cov[arm], key=lambda t: t[1]); hi = max(cov[arm], key=lambda t: t[1])
            print(f"  {arm:14s} coverage 区间 [{lo[1]}, {hi[1]}]  最低={lo[0]} 最高={hi[0]}")
        if mut.get(arm):
            lo = min(mut[arm], key=lambda t: t[1]); hi = max(mut[arm], key=lambda t: t[1])
            print(f"  {arm:14s} mutation 区间 [{lo[1]}, {hi[1]}]  最低={lo[0]} 最高={hi[0]}")
    # 排除 n=5 小文件后的覆盖区间
    print("\n[覆盖区间（仅 n>=50 的 8 个文件，排除两个 n=5 小文件）]")
    for arm in ARMS:
        sub = [t for t in cov.get(arm, []) if not re.search(r"20261001_11(2528|2801)", t[0])]
        if sub:
            print(f"  {arm:14s} [{min(v for _, v in sub)}, {max(v for _, v in sub)}]")
    allc = [(f, v) for arm in ARMS for f, v in cov.get(arm, [])]
    print(f"\n  全臂全文件 plain_llm 最低覆盖 = "
          f"{min(cov['plain_llm'], key=lambda t: t[1])}")
    print(f"  声称 target_line_coverage aitester [{CLAIMS['cov_aitester_lo']},{CLAIMS['cov_aitester_hi']}] / "
          f"plain_llm [{CLAIMS['cov_plain_llm_lo']},{CLAIMS['cov_plain_llm_hi']}]")


# ─────────────────────────── 5 SWE-bench ───────────────────────────
def sec5() -> None:
    hr("§5 SWE-bench 外部有效性证据（原始工件）")
    p = ROOT / "experiments" / "results" / "swe_bench_lite_20" / "benchmark_swe_bench_20260818_113525.json"
    d = load(p)
    print(f"[A] 声称 0/20 的主工件：{p.relative_to(ROOT)}")
    print(f"  timestamp={d.get('timestamp')} dataset={d.get('dataset')} subset={d.get('subset')} "
          f"total_tasks={d.get('total_tasks')} baselines={d.get('baselines')}")
    print(f"  顶层键：{sorted(d.keys())}  → 无 provenance / 无 environment（未记录 git_sha、模型、环境）")
    for arm, av in d["results"].items():
        det = av["details"]
        repos = collections.Counter((r.get("task_metadata") or {}).get("repository") or r.get("repo") for r in det)
        errs = collections.Counter(r.get("error_category") for r in det)
        cov = collections.Counter(r.get("coverage") for r in det)
        print(f"  臂 {arm}: total_functions={av.get('total_functions')} passed={av.get('passed_count')} "
              f"success_rate={av.get('success_rate')}")
        print(f"    repository 分布={dict(repos)}")
        print(f"    error_category={dict(errs)}  coverage 分布={dict(cov)}")
        print(f"    instance 全为 sqlfluff：{all(str(r.get('task_id','')).startswith('sqlfluff__') for r in det)}")
        for r in det[:2]:
            print(f"    行例：task_id={r.get('task_id')} repo={r.get('repo')} passed={r.get('passed')} "
                  f"iterations={r.get('iterations')} diagnosis={(r.get('diagnosis') or '')[:70]!r}")

    print("\n[B] 本地数据集缓存（原始 jsonl）——证明数据可得、非网络问题")
    ds = Path.home() / ".cache" / "aitester" / "swe_bench" / "swe_bench_instances.jsonl"
    if ds.exists():
        rows = [json.loads(l) for l in ds.read_text(encoding="utf-8").splitlines() if l.strip()]
        reps = collections.Counter(r.get("repo") for r in rows)
        byid = {r.get("instance_id"): r for r in rows}
        ids20 = [r.get("task_id") for r in load(p)["results"]["aitester"]["details"]]
        print(f"  {ds}  n={len(rows)}  repo 分布={dict(reps)}")
        print(f"  20 个 run 行在数据集中的命中：{sum(1 for i in ids20 if i in byid)}/20")
        one = byid.get(ids20[0]) or {}
        print(f"  例：instance_id={one.get('instance_id')} repo={one.get('repo')} "
              f"base_commit={str(one.get('base_commit'))[:12]} FAIL_TO_PASS={len(one.get('FAIL_TO_PASS') or [])} "
              f"test_patch 长度={len(str(one.get('test_patch') or ''))}")
        print("  → 数据集带真实 repo/base_commit/test_patch，但结果行 repository=unknown")
        print("     ⇒ 未做仓库 checkout，被测代码是坏片段（error_category=syntax），非算法能力测量。")
    else:
        print(f"  未找到 {ds}")

    print("\n[C] 仓库内**全部** SWE-bench 运行（是否存在有效外部证据）")
    files = sorted(glob.glob(str(ROOT / "experiments/results/**/benchmark_swe_bench*.json"), recursive=True))
    best = None
    for f in files:
        d = load(f)
        for arm, av in (d.get("results") or {}).items():
            det = av.get("details") or []
            repos = collections.Counter((r.get("task_metadata") or {}).get("repository") or r.get("repo") for r in det)
            unk = repos.get("unknown", 0)
            print(f"  {str(d.get('timestamp'))[:19]:19s} {Path(f).relative_to(ROOT / 'experiments/results').as_posix()[:50]:50s} "
                  f"{arm:12s} n={len(det):3d} passed={av.get('passed_count')} unknown_repo={unk}/{len(det)}")
            if av.get("passed_count"):
                if best is None or av["passed_count"] > best[1]:
                    best = (f, av["passed_count"], len(det), arm)
    print(f"\n  最高分（仓库内所有 SWE-bench 运行）：{best}")
    print(f"  另有 {ROOT.joinpath('experiments/results/swebench_20_summary.json').relative_to(ROOT)}：")
    s = load(ROOT / "experiments/results" / "swebench_20_summary.json")
    print(f"    attempted={s.get('total_tasks_attempted')} completed={s.get('tasks_completed')} "
          f"failed={s.get('tasks_failed')} timeout={s.get('tasks_timeout')}")
    print(f"    pass_rate={s.get('results_summary', {}).get('pass_rate')!r} "
          f"notes={s.get('results_summary', {}).get('notes')!r}")
    print(f"    issues={s.get('issues')}")


# ─────────────────────────── 6 SHA256SUMS ───────────────────────────
def sec6(sample: int = 20) -> None:
    hr("§6 SHA256SUMS 抽样校验")
    p = MB / "SHA256SUMS"
    lines = [l.rstrip("\n") for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    entries = []
    for l in lines:
        parts = l.split(None, 1)
        if len(parts) == 2:
            entries.append((parts[0], parts[1].strip()))
    print(f"条目总数：{len(entries)}（文件 {p.relative_to(ROOT)}）")
    step = max(1, len(entries) // sample)
    idxs = list(range(0, len(entries), step))[:sample]
    bad = miss = ok = 0
    print(f"\n确定性抽样 {len(idxs)} 条（等距，步长 {step}）：")
    for i in idxs:
        digest, rel = entries[i]
        f = MB / rel
        if not f.exists():
            print(f"  [缺失] {rel}")
            miss += 1
            continue
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        if h == digest:
            ok += 1
        else:
            bad += 1
            print(f"  [不匹配] {rel}\n     记录 {digest}\n     实际 {h}")
    print(f"\n结果：匹配 {ok}/{len(idxs)}，不匹配 {bad}，文件缺失 {miss}")
    exts = collections.Counter(Path(rel).suffix for _, rel in entries)
    tops = collections.Counter(Path(rel).parts[0] for _, rel in entries)
    print(f"条目类型分布 suffix={dict(exts)}  顶层目录={dict(tops)}")


# ─────────────────────────── 7 统计显著性 ───────────────────────────
def mcnemar_exact(b: int, c: int) -> float:
    """双侧精确二项检验（p=0.5），b/c = 两个不一致方向计数。"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def mcnemar_chi2_cc(b: int, c: int) -> float:
    if b + c == 0:
        return 0.0
    return (abs(b - c) - 1) ** 2 / (b + c)


def paired_table(rows_a: dict, rows_b: dict, key) -> tuple[int, int, int, int]:
    """(both, a_only, b_only, neither) 于两臂均可测的共同任务上。"""
    both = a_only = b_only = neither = 0
    for k in set(rows_a) & set(rows_b):
        a, b = rows_a[k], rows_b[k]
        if a is None or b is None:
            continue
        if a and b:
            both += 1
        elif a and not b:
            a_only += 1
        elif b and not a:
            b_only += 1
        else:
            neither += 1
    return both, a_only, b_only, neither


def bayes_delta_dirichlet(both: int, a_only: int, b_only: int, neither: int,
                          draws: int = 200000, seed: int = 20261011) -> dict:
    """Z9 协议复算：4 格均匀 Dirichlet(1,1,1,1) 先验 → δ=p_A−p_B 后验。
    后验均值解析式 = (a_only − b_only)/(n+4)；CI 由 Dirichlet 抽样得到。"""
    n = both + a_only + b_only + neither
    if n == 0:
        return {}
    mean = (a_only - b_only) / (n + 4)
    rng = random.Random(seed)
    alphas = (both + 1, a_only + 1, b_only + 1, neither + 1)
    deltas = []
    for _ in range(draws):
        g = [rng.gammavariate(a, 1.0) for a in alphas]
        s = sum(g)
        p = [x / s for x in g]
        deltas.append((p[1] + p[0]) - (p[2] + p[0]))  # p_A - p_B（both 抵消）
    deltas.sort()
    lo = deltas[int(0.025 * draws)]
    hi = deltas[int(0.975 * draws)]
    # 解析 CI（Beta 边际差，用正态近似仅作参考）
    return {"n": n, "both": both, "a_only": a_only, "b_only": b_only, "neither": neither,
            "mean": round(mean, 4), "ci": [round(lo, 4), round(hi, 4)],
            "p_gt0": round(sum(1 for d in deltas if d > 0) / draws, 4),
            "p_rope": round(sum(1 for d in deltas if abs(d) <= 0.05) / draws, 4),
            "chi2_cc": round(mcnemar_chi2_cc(a_only, b_only), 4),
            "p_exact": mcnemar_exact(a_only, b_only)}


def cluster_bootstrap_ci(rows_a: dict, rows_b: dict, clusters: dict, draws: int = 20000,
                         seed: int = 20261011) -> dict:
    """任务级聚类 bootstrap：以基础 task_id（跨种子同任务）为重采样单位。"""
    pairs = []
    for k in set(rows_a) & set(rows_b):
        a, b = rows_a[k], rows_b[k]
        if a is None or b is None:
            continue
        pairs.append((clusters[k], a - b))
    if not pairs:
        return {}
    by_cluster: dict[str, list[float]] = collections.defaultdict(list)
    for c, d in pairs:
        by_cluster[c].append(d)
    keys = list(by_cluster)
    rng = random.Random(seed)
    obs = sum(d for _, d in pairs) / len(pairs)
    stats = []
    for _ in range(draws):
        s = 0.0
        m = 0
        for _ in range(len(keys)):
            k = keys[rng.randrange(len(keys))]
            for d in by_cluster[k]:
                s += d
                m += 1
        stats.append(s / m if m else 0.0)
    stats.sort()
    return {"n_pairs": len(pairs), "k_clusters": len(keys), "obs_delta": round(obs, 4),
            "ci": [round(stats[int(0.025 * draws)], 4), round(stats[int(0.975 * draws)], 4)]}


def sec7() -> None:
    hr("§7 统计显著性独立重算")

    def collect(files: list[str], arm: str) -> tuple[dict, dict]:
        rows, clus = {}, {}
        for fn in files:
            d = load(MB / fn)
            seed = d.get("seed")
            for r in rows_of(d, arm):
                k = f"s{seed}__{r.get('task_id')}"
                rows[k] = r.get("detection_rate")
                clus[k] = str(r.get("task_id"))
        return rows, clus

    for label, files in (("R-P0-2 三种子合并（20261006 x3）", R2_FILES),
                         ("E2（20261007_170147 + 161053）", E2_FILES)):
        print(f"\n[{label}]")
        data = {arm: collect(files, arm) for arm in ARMS}
        for a, b in (("aitester", "plain_llm_df"), ("aitester", "plain_llm"), ("plain_llm_df", "plain_llm")):
            ra, ca = data[a]
            rb, _ = data[b]
            both, ao, bo, ne = paired_table(ra, rb, None)
            st = bayes_delta_dirichlet(both, ao, bo, ne)
            cb = cluster_bootstrap_ci(ra, rb, ca)
            print(f"  {a} vs {b}:")
            print(f"    共同可测 {st['n']}  列联表(both,a_only,b_only,neither)=({both},{ao},{bo},{ne})")
            print(f"    McNemar χ²(连续性校正)={st['chi2_cc']}  精确二项双侧 p={st['p_exact']:.3g}")
            print(f"    贝叶斯 Dirichlet δ 后验均值={st['mean']}  95%CI={st['ci']}  P(δ>0)={st['p_gt0']}  P(ROPE)={st['p_rope']}")
            print(f"    任务级聚类 bootstrap（k={cb.get('k_clusters')}，20000 次）: δ={cb.get('obs_delta')} CI={cb.get('ci')}")
    print("\n声称：R-P0-2 合并 aitester vs plain_llm_df δ=−0.279 CI[−0.348,−0.209]；"
          "E2 δ=−0.3673 CI[−0.4552,−0.2785]")
    print("方法学说明：δ 后验均值解析式 = (a_only − b_only)/(n+4)（均匀 Dirichlet 先验），")
    print("            CI 由 Dirichlet(计数+1) 抽样 20 万次得到；聚类 bootstrap 以基础 task_id 为重采样单位，")
    print("            处理三种子同名任务的非独立性。")


# ─────────────────────────── 8 成本 ───────────────────────────
def sec8() -> None:
    hr("§8 成本 $/task（价目表 experiments/price_table.json）")
    pt = load(ROOT / "experiments" / "price_table.json")
    print("价目表原始内容：")
    for m, v in pt["models"].items():
        print(f"  {m:20s} in={v.get('input_per_mtok')} out={v.get('output_per_mtok')} "
              f"cur={v.get('currency')} source={v.get('source') or '(空)'} as_of={v.get('as_of') or '(空)'}")
    nulls = [m for m, v in pt["models"].items()
             if v.get("input_per_mtok") is None or v.get("output_per_mtok") is None]
    print(f"  价目为 null / 无官方来源的模型：{nulls}  → 该模型不参与成本计算")
    files = [MB / n for n in R2_FILES]
    print("\n[R-P0-2 三种子 token 汇总与成本]")
    print(f"  {'arm':14s} {'in_tok':>10s} {'out_tok':>10s} {'tot_tok':>10s} {'calls':>7s} "
          f"{'tok/task':>9s} {'$/task':>9s} {'by_model':>28s}")
    for arm in ARMS:
        ti = to = tt = tc = n = 0
        models = collections.Counter()
        for f in files:
            d = load(f)
            av = d["results"][arm]
            tm = av["token_metrics"]
            ti += tm["total_input_tokens"]; to += tm["total_output_tokens"]
            tt += tm["total_tokens"]; tc += tm["total_llm_calls"]; n += av["total_functions"]
            for r in rows_of(d, arm):
                for k, v in ((r.get("token_usage") or {}).get("by_model") or {}).items():
                    models[k] += v
        cost = (ti * 0.3 + to * 1.2) / 1e6
        print(f"  {arm:14s} {ti:10d} {to:10d} {tt:10d} {tc:7d} {tt / n:9.0f} {cost / n:9.5f} {str(dict(models)):>28s}")
    print(f"\n  声称 aitester {CLAIMS['cost_aitester']} / plain_llm_df {CLAIMS['cost_df']}")
    print("  口径：deepseek-flash 仅登记峰时价 in=$0.3/M out=$1.2/M USD；agnes-3.0-flash 为 null 不参与。")
    print("  注：主批次 by_model 全为 deepseek-flash（无 agnes 混用）→ 该批成本不依赖 null 价目。")


# ─────────────────────────── 9 测试套件 ───────────────────────────
def _parse_pytest_summary(txt: str) -> dict:
    out: dict[str, int] = {}
    for line in txt.splitlines():
        if re.search(r"\d+\s+(passed|failed|error|skipped|xfailed|xpassed)", line):
            for m in re.finditer(r"(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed)", line):
                out[m.group(2).rstrip("s")] = int(m.group(1))
            out["_summary_line"] = line.strip()
    return out


def sec9(do_full: bool) -> None:
    hr("§9 测试套件收集数 / 通过数")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q",
                        "-p", "no:cacheprovider", "--no-header"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    coll = None
    for l in reversed((r.stdout or "").strip().splitlines()):
        m = re.search(r"(\d+)\s+tests?\s+collected", l)
        if m:
            coll = int(m.group(1))
            break
    claim_sum = CLAIMS["tests_total_passed"] + CLAIMS["tests_skipped"] + CLAIMS["tests_xfailed"]
    print(f"  pytest --collect-only → 收集 {coll} 个用例（退出码 {r.returncode}）")
    print(f"  BASELINE.yaml 声称：total_passed={CLAIMS['tests_total_passed']} "
          f"skipped={CLAIMS['tests_skipped']} xfailed={CLAIMS['tests_xfailed']} → 三者之和={claim_sum}")
    if coll:
        print(f"  收集数与声称之和之差 = {coll} − {claim_sum} = {coll - claim_sum}")
    if not do_full:
        print("\n  （未跑全量；加 --with-tests 跑全套并解析 passed/skipped/xfailed 实测值）")
        return
    print("\n  正在全量运行测试套件…")
    log = Path(tempfile.gettempdir()) / "ws2_pytest_full_run.log"
    with open(log, "w", encoding="utf-8") as fh:
        rr = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                             "--no-header", f"--basetemp={tempfile.gettempdir()}/ws2_bt"],
                            cwd=ROOT, env=env, stdout=fh, stderr=subprocess.STDOUT, text=True)
    txt = log.read_text(encoding="utf-8")
    s = _parse_pytest_summary(txt)
    print(f"  退出码 {rr.returncode}；摘要行：{s.get('_summary_line')}")
    print(f"  实测 passed={s.get('passed')} skipped={s.get('skipped')} xfailed={s.get('xfailed')} "
          f"failed={s.get('failed')} error={s.get('error')}")
    tot = sum(v for k, v in s.items() if not k.startswith("_") and k != "xpassed")
    print(f"  实测末态合计 = {tot}（收集数 {coll}）")
    print(f"  与声称 total_passed 之差 = {s.get('passed')} − {CLAIMS['tests_total_passed']} "
          f"= {(s.get('passed') or 0) - CLAIMS['tests_total_passed']}")
    print(f"  日志：{log}（仓库外；脚本本身不在仓库内写任何文件）")


# ─────────────────────────── main ───────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="WS2 独立指标重算（只读原始工件）")
    ap.add_argument("--sections", default="0,1,2,3,4,5,6,7,8,9")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--with-tests", action="store_true", help="第 9 节额外全量跑测试套件")
    a = ap.parse_args()
    want = {s.strip() for s in a.sections.split(",") if s.strip()}
    print(f"WS2 独立指标重算  仓库根={ROOT}")
    print(f"节={sorted(want)}  jobs={a.jobs}  只读原始工件（脚本内不读任何 .md）")
    s2 = None
    if "0" in want:
        sec0()
    if "1" in want:
        sec1()
    if "2" in want:
        s2 = sec2(a.jobs)
    if "3" in want:
        if s2 is None:
            print("§3 需要 §2 的重放结果，先跑 §2…")
            s2 = sec2(a.jobs)
        sec3(s2)
    if "4" in want:
        sec4()
    if "5" in want:
        sec5()
    if "6" in want:
        sec6()
    if "7" in want:
        sec7()
    if "8" in want:
        sec8()
    if "9" in want:
        sec9(a.with_tests)
    print("\n完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
