#!/usr/bin/env python3
"""emse_testlevel_detection.py — QuixBugs **测试级**检出画像（零 LLM，批次九/2026-10-15）。

动机（为什么需要这份工件）
------------------------------------------------------------------
全项目的头条检出指标 `detection_rate`（见 experiments/_m1_metrics.py
`_compute_detection_rate`）是**任务级二值**：生成套件在缺陷代码上 rc≠0、
在 gold 修复代码上 rc=0、且两侧无收集/语法错误 → 1.0，否则 0.0。
这个口径有两个结构性盲点：

1. **不可分解**：1.0 与 1.0 无法区分「整套 20 个测试里有 19 个对缺陷免疫、
   只有 1 个恰好命中」和「整套测试都在检同一缺陷」。整篇论文的配对样本
   N=35（M4 主分析）建立在该二值之上；
2. **信息量被丢弃**：同一批归档工件里其实**逐测试**的 pass/fail 全都在
   手——只是历史链路只取了退出码。

本脚本把同一批归档生成套件在**缺陷代码**与**gold 修复代码**两侧各跑一次，
按 pytest node id 逐测试分类，给出：

    f2p（buggy 失败 ∧ fixed 通过）  = 真正的缺陷探测器
    p2p（两侧都通过）              = 盲测/刻画性测试（零检出信号）
    f2f（两侧都失败）              = 在**正确代码**上即失败 → 生成缺陷
    p2f（buggy 通过 ∧ fixed 失败）  = 反向/可疑
    other                          = 单侧不可用（收集错误/超时/缺失 node id/跳过）

并回答三个问题：(a) 任务级「检出」里有多少是**单个测试函数**扛下来的；
(b) 盲测质量占比多大；(c) 把观测单位从任务换成测试函数后，M4 的配对
功效/结论是否改变。

口径（逐条可复算）
------------------------------------------------------------------
1. **执行口径 = `_m1_metrics._run_pytest_in_tmp` 的 packaged 分支**：物化
   `python_programs/{module}.py` + 根目录 `{module}.py` 双布局、复制
   `node.py`/`load_testdata.py`/`json_testcases`、注入
   `pytest.use_correct=False` prelude，PYTHONPATH=tmpdir:python_testcases。
   即：与 detection_rate 判分**同一条物化链路**，只把结果从「退出码」细化到
   「逐 node id 结果」（`-v -rA` 文本 + 一个只做记录的 pytest 插件 JSONL，
   两路解析互为交叉校验）。
2. **gold 材料**：任务集经 `src.datasets.dataset_realbugs.QuixBugsDataset`
   加载；模块名/gold 代码分别复用 `_m1_metrics._extract_gold_material` /
   `_gold_fixed_code`（单一事实源）。仅 `metadata.test_cases` 与
   `metadata.fixed` **均非空**的任务进入口径（QuixBugs 50 个程序里 41 个
   有官方 gold 材料；9 个 `*_test` 伪程序无 gold，逐源显式排除并计数）。
3. **上限 30s/次**（与 emse_test_sanity_audit.py 同口径）。超时 = 不可测
   （`other`），**不**计为 f2p；buggy 侧挂死单独计数披露（下游可自行决定
   是否算「检出」）。
4. 任务级二值 `task_level_reproduced` 由本次运行复算（三段判据复用
   `_looks_like_test_execution_error`），并与归档 `detection_rate` 对账；
   两者不一致处逐条列出（不静默）。
5. 统计量复用既有单一事实源：`emse_quixbugs_specir_expand.py`
   （mcnemar_exact_p / bayes_factor_10 / mde_two_proportion / build_analysis）
   与 `emse_optimization.py`（mcnemar_chi2_cc / mde_paired_pp /
   bayes_factor_discordant / power_at_delta），不另写一套公式。

零 LLM 纪律：只读归档 JSON 工件 + 本地 pytest 子进程，无任何网络/LLM 调用；
不写归档批次文件，只写 `--out` 目录。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments._m1_metrics import (  # noqa: E402
    _extract_gold_material,
    _gold_fixed_code,
    _looks_like_test_execution_error,
    _needs_quixbugs_support,
    _packaged_support_ready,
    _prepare_packaged_test_tree,
)
from experiments.emse_optimization import (  # noqa: E402
    bayes_factor_discordant,
    mcnemar_chi2_cc,
    mde_paired_pp,
    power_at_delta,
)
from experiments.emse_quixbugs_specir_expand import (  # noqa: E402
    bayes_factor_10,
    build_analysis,
    extract_cache_namespace,
    map_arm_paths,
    mcnemar_exact_p,
    mde_two_proportion,
    verdict,
)

CAP_SECONDS = 30
CLASSES: tuple[str, ...] = ("f2p", "p2p", "f2f", "p2f", "other")

BATCH5_PATH = REPO / "experiments/results/emse_spec_ir_quixbugs_20261013/benchmark_quixbugs_20261014_005101.json"
EXPAND_DIR = REPO / "experiments/results/emse_quixbugs_specir_expand_20261014"
DEFAULT_OUT = REPO / "experiments/results/emse_testlevel_detection_20261015"
QUIXBUGS_ROOT = Path(os.getenv("AITESTER_QUIXBUGS_DATA") or (Path.home() / ".cache/aitester/quixbugs"))

# 臂字母 → 报告标签（A/C = specir；B/D = NL；C/D = A/B 的跨批次复跑）
_ARM_LABELS: dict[str, str] = {
    "A": "arm_A_specir",
    "B": "arm_B_nl",
    "C": "arm_C_specir_repeat",
    "D": "arm_D_nl_repeat",
}
_ARM_ROLE: dict[str, str] = {"A": "specir", "B": "nl", "C": "specir_repeat", "D": "nl_repeat"}

# 只做记录、不改变执行的 pytest 插件：把每个 node id 的每个 phase 结果写成 JSONL。
# 与 -v 文本解析互为交叉校验（两路不一致即报错，不静默二选一）。
_PLUGIN_SRC = '''"""DSH test-level outcome recorder (report-only pytest plugin)."""
import json
import os

_PATH = os.environ.get("DSH_OUTCOME_JSONL", "")


def pytest_runtest_logreport(report):
    if not _PATH:
        return
    with open(_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "nodeid": report.nodeid,
            "when": report.when,
            "outcome": report.outcome,
        }) + "\\n")
'''

# -v 正文行形如：python_testcases/test_x.py::test_y[1] PASSED [ 12%]
_VERBOSE_LINE_RE = re.compile(r"^(?P<node>\S+?::\S+?)\s+(?P<out>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b")
_VERBOSE_OUTCOME: dict[str, str] = {
    "PASSED": "pass",
    "FAILED": "fail",
    "ERROR": "error",
    "SKIPPED": "skip",
    "XFAIL": "skip",  # 预期失败：rc 不受影响，按"无信号"处理
    "XPASS": "pass",
}


# ─── 小工具 ────────────────────────────────────────────────────────────
def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _quantile(sorted_vals: list[float], q: float) -> float | None:
    """线性插值分位数（numpy 默认口径；空列表 → None）。"""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return round(float(sorted_vals[0]), 4)
    pos = q * (len(sorted_vals) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return round(float(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac), 4)


def _dist_summary(vals: list[float]) -> dict[str, Any]:
    if not vals:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None, "q1": None, "q3": None}
    s = sorted(vals)
    return {
        "n": len(s),
        "mean": round(sum(s) / len(s), 4),
        "median": _quantile(s, 0.5),
        "min": round(float(s[0]), 4),
        "max": round(float(s[-1]), 4),
        "q1": _quantile(s, 0.25),
        "q3": _quantile(s, 0.75),
    }


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _rank_abs(diffs: list[float]) -> list[float]:
    """|diff| 的平均秩（并列取平均秩，Wilcoxon 标准处理）。"""
    abses = [abs(d) for d in diffs]
    order = sorted(range(len(abses)), key=lambda i: abses[i])
    ranks = [0.0] * len(abses)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and abses[order[j + 1]] == abses[order[i]]:
            j += 1
        avg = (i + j + 2) / 2.0  # 名次 i+1 .. j+1 的均值
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def wilcoxon_signed_rank(diffs: list[float]) -> dict[str, Any]:
    """配对 Wilcoxon 符号秩检验（零差丢弃；平均秩 + 精确零分布 DP + 正态近似）。

    精确零分布：W+ = Σ r_i·X_i，X_i iid Bernoulli(0.5)；用"双倍秩"整数化
    平均秩（0.5 步长），DP 精确枚举子集和（n≤41 时计数 ≤ 2^41，float 可
    精确表示整数 ≤ 2^53）。双侧 p = 2·P(W+ ≤ min(w, total−w))，截断 1.0。
    """
    d = [x for x in diffs if x != 0]
    n = len(d)
    if n == 0:
        return {"n_nonzero": 0, "w_plus": None, "p_exact": None, "p_normal_approx": None, "note": "全为零差"}
    ranks = _rank_abs(d)
    r2 = [round(2 * r) for r in ranks]
    total2 = sum(r2)
    dp = [0.0] * (total2 + 1)
    dp[0] = 1.0
    for r in r2:
        for s in range(total2, r - 1, -1):
            if dp[s - r]:
                dp[s] += dp[s - r]
    w_plus2 = sum(r for r, x in zip(r2, d, strict=False) if x > 0)
    lo = min(w_plus2, total2 - w_plus2)
    p_exact = min(2.0 * sum(dp[: lo + 1]) / (2.0**n), 1.0)
    mean = sum(ranks) / 2.0
    var = sum(r * r for r in ranks) / 4.0
    w_plus = w_plus2 / 2.0
    z = (abs(w_plus - mean) - 0.5) / math.sqrt(var) if var > 0 else 0.0
    return {
        "n_nonzero": n,
        "n_zero_diff": len(diffs) - n,
        "w_plus": round(w_plus, 2),
        "p_exact": round(p_exact, 4),
        "p_normal_approx": round(min(2.0 * (1.0 - _normal_cdf(max(z, 0.0))), 1.0), 4),
    }


# ─── 工件发现 ──────────────────────────────────────────────────────────
def discover_sources(only: list[str] | None = None) -> list[dict[str, Any]]:
    """返回 5 个来源（batch5 + 4 个 M4 臂），按臂字母的 cache namespace 判定。"""
    sources: list[dict[str, Any]] = []
    if BATCH5_PATH.is_file():
        sources.append(
            {
                "label": "quixbugs50_batch5",
                "kind": "batch5",
                "path": BATCH5_PATH,
                "arm_letter": "",
                "cache_namespace": "",
            }
        )
    expand_files = sorted(EXPAND_DIR.glob("benchmark_quixbugs_2026101*.json"))
    for letter, path in sorted(map_arm_paths(expand_files).items()):
        sources.append(
            {
                "label": _ARM_LABELS.get(letter, f"arm_{letter}"),
                "kind": "arm",
                "path": path,
                "arm_letter": letter,
                "cache_namespace": extract_cache_namespace(path),
            }
        )
    if only:
        keep = {s.strip() for s in only}
        sources = [
            s
            for s in sources
            if s["label"] in keep or s["arm_letter"] in keep or ("batch5" in keep and s["kind"] == "batch5")
        ]
    for s in sources:
        s["sha256"] = _sha256_file(s["path"])
    return sources


def load_gold_tasks() -> tuple[dict[str, Any], dict[str, Any]]:
    """加载 QuixBugsDataset → {task_id: task}（仅 gold 材料齐备者）+ 统计信息。"""
    from src.datasets.dataset_realbugs import QuixBugsDataset

    ds = QuixBugsDataset()
    tasks = list(getattr(ds, "tasks", []) or [])
    eligible: dict[str, Any] = {}
    excluded: list[str] = []
    for t in tasks:
        md = getattr(t, "metadata", None) or {}
        if (md.get("test_cases") or "").strip() and (md.get("fixed") or "").strip():
            eligible[str(t.task_id)] = t
        else:
            excluded.append(str(t.task_id))
    info = {
        "dataset": "quixbugs",
        "data_dir": str(getattr(ds, "data_dir", "")),
        "n_tasks_loaded": len(tasks),
        "n_tasks_gold_eligible": len(eligible),
        "n_tasks_excluded_no_gold": len(excluded),
        "excluded_task_ids": sorted(excluded),
    }
    return eligible, info


# ─── 执行 + 解析 ───────────────────────────────────────────────────────
def _norm_nodeid(raw: str, module: str) -> str:
    """node id 归一为 `test_{module}.py::...`（去 tmpdir 绝对路径，跨运行可比）。"""
    marker = f"test_{module}.py::"
    idx = raw.find(marker)
    if idx >= 0:
        return raw[idx:]
    if "::" in raw:
        return f"test_{module}.py::" + raw.split("::", 1)[1]
    return raw


def _fold_plugin_records(path: Path, module: str) -> dict[str, str]:
    """插件 JSONL → {归一 node id: pass|fail|error|skip}（按 phase 归并）。"""
    phases: dict[str, dict[str, str]] = {}
    if not path.is_file():
        return {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        node = _norm_nodeid(str(rec.get("nodeid") or ""), module)
        if not node:
            continue
        phases.setdefault(node, {})[str(rec.get("when") or "")] = str(rec.get("outcome") or "")
    out: dict[str, str] = {}
    for node, ph in phases.items():
        if ph.get("setup") == "failed" or "call" not in ph:
            out[node] = "error"
        elif ph["call"] == "skipped":
            out[node] = "skip"
        elif ph["call"] == "failed":
            out[node] = "fail"
        elif ph["call"] == "passed":
            out[node] = "error" if ph.get("teardown") == "failed" else "pass"
        else:
            out[node] = "error"
    return out


def _parse_verbose(stdout: str, module: str) -> dict[str, str]:
    """-v 正文行 → {归一 node id: pass|fail|error|skip}（交叉校验用）。"""
    out: dict[str, str] = {}
    for line in (stdout or "").splitlines():
        m = _VERBOSE_LINE_RE.match(line.strip())
        if not m:
            continue
        node = _norm_nodeid(m.group("node"), module)
        out[node] = _VERBOSE_OUTCOME.get(m.group("out"), "error")
    return out


def run_side(
    module: str,
    target_code: str,
    test_code: str,
    *,
    cap_seconds: int,
    keep_stdout: bool = True,
) -> dict[str, Any]:
    """物化（packaged 分支，与 _run_pytest_in_tmp 同链路）并跑一次 pytest。"""
    from src.utils.process_utils import run_with_timeout

    tmpdir = tempfile.mkdtemp(prefix=f"tl_{module}_")
    try:
        test_path, pythonpath = _prepare_packaged_test_tree(tmpdir, target_code, test_code, module)
        plugin_path = Path(tmpdir) / "_dsh_outcomes.py"
        plugin_path.write_text(_PLUGIN_SRC, encoding="utf-8")
        jsonl = Path(tmpdir) / "outcomes.jsonl"
        env = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONPATH": pythonpath,
            "DSH_OUTCOME_JSONL": str(jsonl),
            "COLUMNS": "200",
        }
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            test_path,
            "-v",
            "--tb=no",
            "-rA",
            "-p",
            "no:cacheprovider",
            "-p",
            "_dsh_outcomes",
            "--no-header",
            "--color=no",
        ]
        t0 = time.time()
        res = run_with_timeout(cmd, timeout=cap_seconds, cwd=tmpdir, text=True, logger_name="testlevel", env=env)
        wall = round(time.time() - t0, 2)
        stdout = res.stdout or ""
        stderr = res.stderr or ""
        timed_out = bool(getattr(res, "timed_out", False))
        rc = None if timed_out else res.returncode
        plugin_map = _fold_plugin_records(jsonl, module)
        verbose_map = _parse_verbose(stdout, module)
        shared = set(plugin_map) & set(verbose_map)
        mismatch = sorted(n for n in shared if plugin_map[n] != verbose_map[n])
        if plugin_map:
            parser = "plugin+verbose" if verbose_map else "plugin"
        elif verbose_map:
            parser = "verbose_fallback"
        else:
            parser = "none"
        rec: dict[str, Any] = {
            "rc": rc,
            "timed_out": timed_out,
            "wall_s": wall,
            "parser": parser,
            "n_nodeids": len(plugin_map) if plugin_map else len(verbose_map),
            "n_nodeids_plugin": len(plugin_map),
            "n_nodeids_verbose": len(verbose_map),
            "parse_agree_n": len(shared),
            "parse_mismatch": mismatch,
            "outcomes": plugin_map or verbose_map,
            "exec_error_heuristic": _looks_like_test_execution_error(
                -9 if timed_out else int(res.returncode), stdout + "\n" + stderr
            ),
            "stdout_sha256": _sha256_text(stdout),
            "stdout_tail": "\n".join(stdout.strip().splitlines()[-12:])[:2000],
            "stderr_tail": "\n".join(stderr.strip().splitlines()[-6:])[:1200],
            "stdout": stdout if keep_stdout else "",
        }
        return rec
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


def _n_ast_test_defs(code: str) -> int:
    """AST 计数 test_* 函数定义（含类方法；语法错误 → -1）。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return -1
    return sum(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_") for n in ast.walk(tree)
    )


def classify_tests(
    module: str, buggy: dict[str, Any], fixed: dict[str, Any]
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """逐测试分类（只用 node id 两侧都出现的测试进四分类，其余记 other）。"""
    b_map = buggy.get("outcomes") or {}
    f_map = fixed.get("outcomes") or {}
    b_usable = bool(b_map) and not buggy["timed_out"]
    f_usable = bool(f_map) and not fixed["timed_out"]
    if not b_usable or not f_usable:
        rows = [
            {
                "node": node,
                "buggy": b_map.get(node, "unavailable"),
                "fixed": f_map.get(node, "unavailable"),
                "cls": "other",
            }
            for node in sorted(set(b_map) | set(f_map))
        ]
        return rows, {"f2p": 0, "p2p": 0, "f2f": 0, "p2f": 0, "other": len(rows)}
    rows = []
    counts = {c: 0 for c in CLASSES}
    for node in sorted(set(b_map) | set(f_map)):
        b = b_map.get(node)
        f = f_map.get(node)
        if b is None or f is None or b == "skip" or f == "skip":
            cls = "other"
        else:
            b_fail = b in ("fail", "error")
            f_fail = f in ("fail", "error")
            if b_fail and not f_fail:
                cls = "f2p"
            elif not b_fail and not f_fail:
                cls = "p2p"
            elif b_fail and f_fail:
                cls = "f2f"
            else:
                cls = "p2f"
        counts[cls] += 1
        rows.append({"node": node, "buggy": b or "unavailable", "fixed": f or "unavailable", "cls": cls})
    return rows, counts


def suite_class(
    counts: dict[str, int], buggy: dict[str, Any], fixed: dict[str, Any], rows: list[dict[str, str]]
) -> str:
    """套件级标签（互斥，判定顺序固定）。"""
    if buggy["timed_out"] or fixed["timed_out"]:
        return "timeout"
    if not rows:
        return "no_pertest_data"
    if counts["f2p"] > 0 and counts["f2f"] == 0:
        return "detecting_clean"
    if counts["f2p"] > 0 and counts["f2f"] > 0:
        return "detecting_invalid"
    if counts["f2p"] == 0 and counts["f2f"] == 0:
        return "blind_clean"
    return "invalid_only"


# ─── 单源跑批 ──────────────────────────────────────────────────────────
def run_source(
    source: dict[str, Any],
    gold: dict[str, Any],
    *,
    cap_seconds: int,
    progress: bool = True,
    limit: int = 0,
) -> dict[str, Any]:
    """跑一个来源（batch5 / 某臂）的全部 gold-eligible 任务，返回逐任务记录。"""
    data = json.loads(source["path"].read_text(encoding="utf-8"))
    rows = data["results"]["aitester"]["details"]
    if limit > 0:
        rows = [r for r in rows if str(r.get("task_id") or "") in gold][:limit]
    recs: list[dict[str, Any]] = []
    skipped_no_gold: list[str] = []
    t_start = time.time()
    n_done = 0
    for row in rows:
        tid = str(row.get("task_id") or "")
        if tid not in gold:
            skipped_no_gold.append(tid)
            continue
        task = gold[tid]
        module, gold_tests, _fixed_raw = _extract_gold_material(task) or ("", "", "")
        fixed_code = _gold_fixed_code(task)
        buggy_code = str(getattr(task, "instance_code", "") or "")
        gen_test = str(row.get("generated_test") or "")
        archived_md = row.get("task_metadata") or {}
        rec: dict[str, Any] = {
            "set": source["label"],
            "arm_letter": source["arm_letter"],
            "task_id": tid,
            "module": module,
            "archived_detection_rate": row.get("detection_rate"),
            "archived_stop_reason": row.get("stop_reason"),
            "n_generated_test_chars": len(gen_test),
            "n_ast_test_defs": _n_ast_test_defs(gen_test) if gen_test.strip() else 0,
            "material_ok": bool(module.strip() and gen_test.strip() and buggy_code.strip() and fixed_code.strip()),
            "material_mismatch": {
                "archived_fixed_vs_dataset_fixed": _sha256_text(str(archived_md.get("fixed") or "").strip())
                != _sha256_text(str((getattr(task, "metadata", {}) or {}).get("fixed") or "").strip()),
                "archived_gold_tests_vs_dataset": _sha256_text(str(archived_md.get("test_cases") or "").strip())
                != _sha256_text(gold_tests.strip()),
            },
            "needs_quixbugs_support": _needs_quixbugs_support(gen_test),
        }
        if not rec["material_ok"]:
            rec.update(
                {
                    "suite_class": "material_missing",
                    "counts": {c: 0 for c in CLASSES},
                    "n_classifiable": 0,
                    "n_union": 0,
                    "n_only_buggy": 0,
                    "n_only_fixed": 0,
                    "tests": [],
                    "buggy": {"rc": None, "timed_out": False, "wall_s": 0.0, "n_nodeids": 0},
                    "fixed": {"rc": None, "timed_out": False, "wall_s": 0.0, "n_nodeids": 0},
                    "task_level_reproduced": None,
                    "f2p_call_phase": 0,
                    "f2p_setup_teardown_error": 0,
                }
            )
            recs.append(rec)
            continue

        buggy = run_side(module, buggy_code, gen_test, cap_seconds=cap_seconds)
        fixed = run_side(module, fixed_code, gen_test, cap_seconds=cap_seconds)
        tests, counts = classify_tests(module, buggy, fixed)
        b_map = buggy.get("outcomes") or {}
        n_classifiable = sum(1 for t in tests if t["cls"] != "other")
        # f2p 的 buggy 侧相位：call 相位失败（断言失败**或**被测代码抛出的未捕获异常，
        # 如 IndexError/TypeError）vs setup/teardown 异常（夹具/清理阶段失败）
        f2p_assert = sum(1 for t in tests if t["cls"] == "f2p" and b_map.get(t["node"]) == "fail")
        f2p_err = sum(1 for t in tests if t["cls"] == "f2p" and b_map.get(t["node"]) == "error")
        # 任务级三段判据复算（与 _compute_detection_rate 逐字同规则）
        reproduced: float | None
        if buggy["timed_out"] or fixed["timed_out"]:
            reproduced = None
        else:
            b_rc = int(buggy["rc"])
            f_rc = int(fixed["rc"])
            # 与 _compute_detection_rate 同规则（执行错误判据用**全量**输出算出的
            # exec_error_heuristic，不用被截断的 tail）
            if b_rc == 0 or buggy["exec_error_heuristic"] or f_rc != 0 or fixed["exec_error_heuristic"]:
                reproduced = 0.0
            else:
                reproduced = 1.0

        rec.update(
            {
                "suite_class": suite_class(counts, buggy, fixed, tests),
                "counts": counts,
                "n_classifiable": n_classifiable,
                "n_union": len(tests),
                "n_only_buggy": sum(1 for t in tests if t["buggy"] != "unavailable" and t["fixed"] == "unavailable"),
                "n_only_fixed": sum(1 for t in tests if t["fixed"] != "unavailable" and t["buggy"] == "unavailable"),
                "tests": tests,
                "buggy": {
                    k: buggy[k]
                    for k in (
                        "rc",
                        "timed_out",
                        "wall_s",
                        "parser",
                        "n_nodeids_plugin",
                        "n_nodeids_verbose",
                        "parse_agree_n",
                        "parse_mismatch",
                        "exec_error_heuristic",
                        "stdout_sha256",
                        "stdout_tail",
                    )
                },
                "fixed": {
                    k: fixed[k]
                    for k in (
                        "rc",
                        "timed_out",
                        "wall_s",
                        "parser",
                        "n_nodeids_plugin",
                        "n_nodeids_verbose",
                        "parse_agree_n",
                        "parse_mismatch",
                        "exec_error_heuristic",
                        "stdout_sha256",
                        "stdout_tail",
                    )
                },
                "buggy_stdout": buggy.get("stdout", ""),
                "fixed_stdout": fixed.get("stdout", ""),
                "task_level_reproduced": reproduced,
                "f2p_call_phase": f2p_assert,
                "f2p_setup_teardown_error": f2p_err,
            }
        )
        recs.append(rec)
        n_done += 1
        if progress:
            print(
                f"[tl] {source['label']} {n_done}/{len(gold)} {tid}: "
                f"buggy rc={buggy['rc']}{' TO' if buggy['timed_out'] else ''} "
                f"fixed rc={fixed['rc']}{' TO' if fixed['timed_out'] else ''} | "
                f"f2p={counts['f2p']} p2p={counts['p2p']} f2f={counts['f2f']} p2f={counts['p2f']} other={counts['other']} | "
                f"{rec['suite_class']}",
                flush=True,
            )

    return {
        "source": {k: v for k, v in source.items() if k != "path"} | {"path": str(source["path"])},
        "n_rows": len(rows),
        "skipped_no_gold": sorted(skipped_no_gold),
        "wall_s": round(time.time() - t_start, 1),
        "tasks": recs,
    }


# ─── 聚合指标（Step 2）────────────────────────────────────────────────
def aggregate_source(run: dict[str, Any]) -> dict[str, Any]:
    """单源聚合：计数、比率、分布、换算表、对账、无数据任务清单。"""
    ran = [t for t in run["tasks"] if t["suite_class"] != "material_missing"]
    totals = {c: sum(t["counts"][c] for t in ran) for c in CLASSES}
    n_classifiable = sum(t["n_classifiable"] for t in ran)
    n_union = sum(t["n_union"] for t in ran)
    det1 = [t for t in ran if t["archived_detection_rate"] == 1.0]
    conv_hist = {"0": 0, "1": 0, "2": 0, "3+": 0}
    for t in det1:
        n = t["counts"]["f2p"]
        conv_hist["0" if n == 0 else "1" if n == 1 else "2" if n == 2 else "3+"] += 1
    per_task_frac = [t["counts"]["f2p"] / t["n_classifiable"] for t in ran if t["n_classifiable"] > 0]
    reconciliation: dict[str, int] = {}
    disagreements: list[dict[str, Any]] = []
    for t in ran:
        pair = f"{t['archived_detection_rate']}->{t['task_level_reproduced']}"
        reconciliation[pair] = reconciliation.get(pair, 0) + 1
        a, r = t["archived_detection_rate"], t["task_level_reproduced"]
        if (a is None) != (r is None) or (a is not None and r is not None and float(a) != float(r)):
            disagreements.append(
                {
                    "task_id": t["task_id"],
                    "archived": a,
                    "reproduced": r,
                    "buggy_rc": t["buggy"]["rc"],
                    "fixed_rc": t["fixed"]["rc"],
                    "buggy_timed_out": t["buggy"]["timed_out"],
                    "fixed_timed_out": t["fixed"]["timed_out"],
                    "counts": t["counts"],
                    "archived_stop_reason": t["archived_stop_reason"],
                }
            )
    no_pertest = [t["task_id"] for t in ran if t["n_union"] == 0]
    det1_zero_f2p = [t["task_id"] for t in det1 if t["counts"]["f2p"] == 0]
    parse_mismatch_total = sum(len(t["buggy"]["parse_mismatch"]) + len(t["fixed"]["parse_mismatch"]) for t in ran)
    agree = sum(t["buggy"]["parse_agree_n"] + t["fixed"]["parse_agree_n"] for t in ran)
    return {
        "label": run["source"]["label"],
        "kind": run["source"]["kind"],
        "arm_letter": run["source"]["arm_letter"],
        "cache_namespace": run["source"]["cache_namespace"],
        "path": run["source"]["path"],
        "sha256": run["source"]["sha256"],
        "n_rows_in_artifact": run["n_rows"],
        "n_tasks_gold_eligible": len(run["tasks"]),
        "n_suites_run": len(ran),
        "n_tasks_skipped_no_gold": len(run["skipped_no_gold"]),
        "wall_s": run["wall_s"],
        "suite_class_counts": {
            k: sum(1 for t in ran if t["suite_class"] == k) for k in sorted({t["suite_class"] for t in ran})
        },
        "class_totals": totals,
        "n_classifiable_total": n_classifiable,
        "n_union_total": n_union,
        "n_only_buggy": sum(t["n_only_buggy"] for t in ran),
        "n_only_fixed": sum(t["n_only_fixed"] for t in ran),
        "pooled_f2p_rate": round(totals["f2p"] / n_classifiable, 4) if n_classifiable else None,
        "pooled_f2p_rate_union_denom": round(totals["f2p"] / n_union, 4) if n_union else None,
        "pooled_p2p_rate": round(totals["p2p"] / n_classifiable, 4) if n_classifiable else None,
        "pooled_f2f_rate": round(totals["f2f"] / n_classifiable, 4) if n_classifiable else None,
        "pooled_p2f_rate": round(totals["p2f"] / n_classifiable, 4) if n_classifiable else None,
        "per_task_f2p_fraction": _dist_summary(per_task_frac),
        "per_task_f2p_fraction_histogram": {
            "0": sum(1 for v in per_task_frac if v == 0),
            "(0,0.25]": sum(1 for v in per_task_frac if 0 < v <= 0.25),
            "(0.25,0.5]": sum(1 for v in per_task_frac if 0.25 < v <= 0.5),
            "(0.5,0.75]": sum(1 for v in per_task_frac if 0.5 < v <= 0.75),
            "(0.75,1]": sum(1 for v in per_task_frac if v > 0.75),
        },
        "per_task_f2p_count": _dist_summary([float(t["counts"]["f2p"]) for t in ran]),
        "per_task_classifiable_count": _dist_summary([float(t["n_classifiable"]) for t in ran]),
        "per_task_ast_defs": _dist_summary([float(t["n_ast_test_defs"]) for t in ran]),
        "detection_conversion": {
            "n_archived_detection_1": len(det1),
            "f2p_count_distribution": conv_hist,
            "n_single_test_carried": conv_hist["1"],
            "n_multi_test": conv_hist["2"] + conv_hist["3+"],
            "n_det1_but_zero_f2p": det1_zero_f2p,
            "f2p_mean_among_det1": round(sum(t["counts"]["f2p"] for t in det1) / len(det1), 4) if det1 else None,
            "f2p_total_among_det1": sum(t["counts"]["f2p"] for t in det1),
            "classifiable_total_among_det1": sum(t["n_classifiable"] for t in det1),
        },
        "blind_mass": {
            "p2p": totals["p2p"],
            "f2p": totals["f2p"],
            "p2p_over_classifiable": round(totals["p2p"] / n_classifiable, 4) if n_classifiable else None,
            "p2p_over_p2p_plus_f2p": round(totals["p2p"] / (totals["p2p"] + totals["f2p"]), 4)
            if (totals["p2p"] + totals["f2p"])
            else None,
        },
        "invalid_mass": {
            "f2f": totals["f2f"],
            "f2f_over_classifiable": round(totals["f2f"] / n_classifiable, 4) if n_classifiable else None,
            "n_suites_with_f2f": sum(1 for t in ran if t["counts"]["f2f"] > 0),
            "f2f_total_over_suites": round(totals["f2f"] / len(ran), 4) if ran else None,
            "n_suites_green_on_fixed_rc0": sum(1 for t in ran if t["fixed"]["rc"] == 0),
            "suite_green_rate_on_fixed": round(sum(1 for t in ran if t["fixed"]["rc"] == 0) / len(ran), 4)
            if ran
            else None,
            "n_suites_green_on_buggy_rc0": sum(1 for t in ran if t["buggy"]["rc"] == 0),
            "suite_green_rate_on_buggy": round(sum(1 for t in ran if t["buggy"]["rc"] == 0) / len(ran), 4)
            if ran
            else None,
        },
        "inverted_mass": {
            "p2f": totals["p2f"],
            "n_suites_with_p2f": sum(1 for t in ran if t["counts"]["p2f"] > 0),
        },
        "f2p_phase_split": {
            "call_phase_failed_on_buggy": sum(t.get("f2p_call_phase", t.get("f2p_assertion_level", 0)) for t in ran),
            "setup_or_teardown_error_on_buggy": sum(
                t.get("f2p_setup_teardown_error", t.get("f2p_error_level", 0)) for t in ran
            ),
        },
        "timeouts": {
            "buggy": [t["task_id"] for t in ran if t["buggy"]["timed_out"]],
            "fixed": [t["task_id"] for t in ran if t["fixed"]["timed_out"]],
            "either": [t["task_id"] for t in ran if t["buggy"]["timed_out"] or t["fixed"]["timed_out"]],
            "n_sides_timed_out": sum(1 for t in ran if t["buggy"]["timed_out"] or t["fixed"]["timed_out"]),
        },
        "no_pertest_data_task_ids": no_pertest,
        "n_no_pertest_data": len(no_pertest),
        "task_level_reconciliation": {
            "counts": reconciliation,
            "n_agree": sum(v for k, v in reconciliation.items() if k.split("->")[0] == k.split("->")[1]),
            "n_disagree": len(disagreements),
            "disagreements": disagreements,
        },
        "parser_crosscheck": {
            "n_plugin_verbose_agreements": agree,
            "n_mismatches": parse_mismatch_total,
            "n_sides_verbose_fallback": sum(
                1
                for t in ran
                if t["buggy"]["parser"] == "verbose_fallback" or t["fixed"]["parser"] == "verbose_fallback"
            ),
            "n_sides_no_parser": sum(
                1 for t in ran if t["buggy"]["parser"] == "none" or t["fixed"]["parser"] == "none"
            ),
        },
        "material_mismatch_task_ids": [t["task_id"] for t in ran if any(t["material_mismatch"].values())],
    }


def aggregate_pooled(runs: list[dict[str, Any]], per_source: list[dict[str, Any]]) -> dict[str, Any]:
    """全部来源合并（去重键 = (来源标签, task_id)；五个来源任务是同一批 41 个）。"""
    all_tasks = [t for r in runs for t in r["tasks"] if t["suite_class"] != "material_missing"]
    totals = {c: sum(t["counts"][c] for t in all_tasks) for c in CLASSES}
    n_classifiable = sum(t["n_classifiable"] for t in all_tasks)
    n_union = sum(t["n_union"] for t in all_tasks)
    det1 = [t for t in all_tasks if t["archived_detection_rate"] == 1.0]
    conv = {"0": 0, "1": 0, "2": 0, "3+": 0}
    for t in det1:
        n = t["counts"]["f2p"]
        conv["0" if n == 0 else "1" if n == 1 else "2" if n == 2 else "3+"] += 1
    frac = [t["counts"]["f2p"] / t["n_classifiable"] for t in all_tasks if t["n_classifiable"] > 0]
    return {
        "n_sources": len(runs),
        "n_suites_run": len(all_tasks),
        "suite_class_counts": {
            k: sum(1 for t in all_tasks if t["suite_class"] == k) for k in sorted({t["suite_class"] for t in all_tasks})
        },
        "class_totals": totals,
        "n_classifiable_total": n_classifiable,
        "n_union_total": n_union,
        "n_only_buggy": sum(t["n_only_buggy"] for t in all_tasks),
        "n_only_fixed": sum(t["n_only_fixed"] for t in all_tasks),
        "pooled_f2p_rate": round(totals["f2p"] / n_classifiable, 4) if n_classifiable else None,
        "pooled_f2p_rate_union_denom": round(totals["f2p"] / n_union, 4) if n_union else None,
        "pooled_p2p_rate": round(totals["p2p"] / n_classifiable, 4) if n_classifiable else None,
        "pooled_f2f_rate": round(totals["f2f"] / n_classifiable, 4) if n_classifiable else None,
        "pooled_p2f_rate": round(totals["p2f"] / n_classifiable, 4) if n_classifiable else None,
        "per_task_f2p_fraction": _dist_summary(frac),
        "per_task_f2p_fraction_histogram": {
            "0": sum(1 for v in frac if v == 0),
            "(0,0.25]": sum(1 for v in frac if 0 < v <= 0.25),
            "(0.25,0.5]": sum(1 for v in frac if 0.25 < v <= 0.5),
            "(0.5,0.75]": sum(1 for v in frac if 0.5 < v <= 0.75),
            "(0.75,1]": sum(1 for v in frac if v > 0.75),
        },
        "detection_conversion": {
            "n_archived_detection_1": len(det1),
            "f2p_count_distribution": conv,
            "n_single_test_carried": conv["1"],
            "n_multi_test": conv["2"] + conv["3+"],
            "n_det1_but_zero_f2p": [t["task_id"] for t in det1 if t["counts"]["f2p"] == 0],
            "f2p_mean_among_det1": round(sum(t["counts"]["f2p"] for t in det1) / len(det1), 4) if det1 else None,
            "f2p_total_among_det1": sum(t["counts"]["f2p"] for t in det1),
            "classifiable_total_among_det1": sum(t["n_classifiable"] for t in det1),
        },
        "blind_mass": {
            "p2p": totals["p2p"],
            "f2p": totals["f2p"],
            "p2p_over_classifiable": round(totals["p2p"] / n_classifiable, 4) if n_classifiable else None,
            "p2p_over_p2p_plus_f2p": round(totals["p2p"] / (totals["p2p"] + totals["f2p"]), 4)
            if (totals["p2p"] + totals["f2p"])
            else None,
        },
        "invalid_mass": {
            "f2f": totals["f2f"],
            "f2f_over_classifiable": round(totals["f2f"] / n_classifiable, 4) if n_classifiable else None,
            "n_suites_with_f2f": sum(1 for t in all_tasks if t["counts"]["f2f"] > 0),
            "n_suites_green_on_fixed_rc0": sum(1 for t in all_tasks if t["fixed"]["rc"] == 0),
            "suite_green_rate_on_fixed": round(sum(1 for t in all_tasks if t["fixed"]["rc"] == 0) / len(all_tasks), 4)
            if all_tasks
            else None,
            "n_suites_green_on_buggy_rc0": sum(1 for t in all_tasks if t["buggy"]["rc"] == 0),
            "suite_green_rate_on_buggy": round(sum(1 for t in all_tasks if t["buggy"]["rc"] == 0) / len(all_tasks), 4)
            if all_tasks
            else None,
        },
        "inverted_mass": {
            "p2f": totals["p2f"],
            "n_suites_with_p2f": sum(1 for t in all_tasks if t["counts"]["p2f"] > 0),
        },
        "f2p_phase_split": {
            "call_phase_failed_on_buggy": sum(
                t.get("f2p_call_phase", t.get("f2p_assertion_level", 0)) for t in all_tasks
            ),
            "setup_or_teardown_error_on_buggy": sum(
                t.get("f2p_setup_teardown_error", t.get("f2p_error_level", 0)) for t in all_tasks
            ),
        },
        "timeouts": {
            "buggy": sorted({t["task_id"] for t in all_tasks if t["buggy"]["timed_out"]}),
            "fixed": sorted({t["task_id"] for t in all_tasks if t["fixed"]["timed_out"]}),
            "n_sides_timed_out": sum(1 for t in all_tasks if t["buggy"]["timed_out"] or t["fixed"]["timed_out"]),
        },
        "n_no_pertest_data": sum(1 for t in all_tasks if t["n_union"] == 0),
        "no_pertest_data_task_ids": sorted({t["task_id"] for t in all_tasks if t["n_union"] == 0}),
        "parser_crosscheck": {
            "n_plugin_verbose_agreements": sum(
                t["buggy"]["parse_agree_n"] + t["fixed"]["parse_agree_n"] for t in all_tasks
            ),
            "n_mismatches": sum(
                len(t["buggy"]["parse_mismatch"]) + len(t["fixed"]["parse_mismatch"]) for t in all_tasks
            ),
            "n_sides_verbose_fallback": sum(
                1
                for t in all_tasks
                if t["buggy"]["parser"] == "verbose_fallback" or t["fixed"]["parser"] == "verbose_fallback"
            ),
            "n_sides_no_parser": sum(
                1 for t in all_tasks if t["buggy"]["parser"] == "none" or t["fixed"]["parser"] == "none"
            ),
        },
        "task_level_reconciliation": {
            "counts": _merge_reconciliation(all_tasks),
            "n_disagree": sum(
                1
                for t in all_tasks
                if (t["archived_detection_rate"] is None) != (t["task_level_reproduced"] is None)
                or (
                    t["archived_detection_rate"] is not None
                    and t["task_level_reproduced"] is not None
                    and float(t["archived_detection_rate"]) != float(t["task_level_reproduced"])
                )
            ),
        },
        "per_source_f2p_rate": {a["label"]: a["pooled_f2p_rate"] for a in per_source},
        "per_source_detection_conversion": {a["label"]: a["detection_conversion"] for a in per_source},
    }


def _merge_reconciliation(all_tasks: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in all_tasks:
        key = f"{t['archived_detection_rate']}->{t['task_level_reproduced']}"
        out[key] = out.get(key, 0) + 1
    return out


# ─── 统计（Step 3）────────────────────────────────────────────────────
def _suite_index(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {t["task_id"]: t for t in run["tasks"] if t["suite_class"] != "material_missing"}


def testlevel_pair(run_x: dict[str, Any], run_y: dict[str, Any], label_x: str, label_y: str) -> dict[str, Any]:
    """测试级配对（按归一 node id；同一任务内配对，node id 已含模块文件名故天然任务隔离）。"""
    ix, iy = _suite_index(run_x), _suite_index(run_y)
    common = sorted(set(ix) & set(iy))
    b_pos = b_neg = both = neither = 0
    n_shared = n_x_only = n_y_only = n_dropped = 0
    per_task: list[dict[str, Any]] = []
    for tid in common:
        tx, ty = ix[tid], iy[tid]
        cx = {t["node"]: t["cls"] for t in tx["tests"]}
        cy = {t["node"]: t["cls"] for t in ty["tests"]}
        shared = sorted(set(cx) & set(cy))
        n_shared += len(shared)
        n_x_only += len(set(cx) - set(cy))
        n_y_only += len(set(cy) - set(cx))
        cnt_x = cnt_y = 0
        for node in shared:
            cls_x, cls_y = cx[node], cy[node]
            if cls_x == "other" or cls_y == "other":
                # 任一侧不可分类 → 不进配对分母（严格口径；other 计数单列披露）
                n_dropped += 1
                continue
            fx = cls_x == "f2p"
            fy = cls_y == "f2p"
            cnt_x += int(fx)
            cnt_y += int(fy)
            if fx and not fy:
                b_pos += 1
            elif fy and not fx:
                b_neg += 1
            elif fx and fy:
                both += 1
            else:
                neither += 1
        per_task.append(
            {
                "task_id": tid,
                "n_classifiable_x": tx["n_classifiable"],
                "n_classifiable_y": ty["n_classifiable"],
                "f2p_x": tx["counts"]["f2p"],
                "f2p_y": ty["counts"]["f2p"],
                "shared_nodes": len(shared),
                "shared_f2p_x": cnt_x,
                "shared_f2p_y": cnt_y,
                "delta_f2p_count": tx["counts"]["f2p"] - ty["counts"]["f2p"],
                "frac_x": round(tx["counts"]["f2p"] / tx["n_classifiable"], 4) if tx["n_classifiable"] else None,
                "frac_y": round(ty["counts"]["f2p"] / ty["n_classifiable"], 4) if ty["n_classifiable"] else None,
                "det_x": tx["archived_detection_rate"],
                "det_y": ty["archived_detection_rate"],
            }
        )
    n_pairs = b_pos + b_neg + both + neither
    delta_pp = (b_pos - b_neg) / n_pairs * 100 if n_pairs else 0.0
    psi = (b_pos + b_neg) / n_pairs if n_pairs else 0.0
    p = mcnemar_exact_p(b_pos, b_neg)
    bf_expand = bayes_factor_10(b_pos, b_neg)
    bf_opt = bayes_factor_discordant(b_pos, b_neg)
    return {
        "pair": f"{label_x} vs {label_y}",
        "n_tasks_paired": len(common),
        "n_test_nodeids_shared": n_shared,
        "n_nodeids_x_only": n_x_only,
        "n_nodeids_y_only": n_y_only,
        "n_shared_dropped_other": n_dropped,
        "n_pairs_testlevel": n_pairs,
        "b_pos_x_only_f2p": b_pos,
        "b_neg_y_only_f2p": b_neg,
        "both_f2p": both,
        "neither_f2p": neither,
        "ratio": f"{b_pos}:{b_neg}",
        "delta_pp": round(delta_pp, 2),
        "psi_discordance": round(psi, 4),
        "p_mcnemar_exact": round(p, 4),
        "p_chi2_cc": round(mcnemar_chi2_cc(b_pos, b_neg), 4),
        "bf10_expand": bf_expand,
        "bf10_optimization": bf_opt["bf10_jeffreys"],
        "bf_verdict": bf_opt["verdict"],
        "mde_two_proportion_pp": mde_two_proportion(n_pairs),
        "mde_paired_pp": round(mde_paired_pp(n_pairs, psi), 2) if mde_paired_pp(n_pairs, psi) is not None else None,
        "verdict_rule": verdict({"p_value": round(p, 4), "delta_pp": round(delta_pp, 2)}),
        "per_task": per_task,
    }


def task_clustered_pair(run_x: dict[str, Any], run_y: dict[str, Any], label_x: str, label_y: str) -> dict[str, Any]:
    """任务聚类变体：每任务 = 一个观测单位（防伪重复）。"""
    ix, iy = _suite_index(run_x), _suite_index(run_y)
    common = sorted(set(ix) & set(iy))
    dcount: list[float] = []
    dfrac: list[float] = []
    b_pos = b_neg = 0
    for tid in common:
        nx, ny = ix[tid]["counts"]["f2p"], iy[tid]["counts"]["f2p"]
        dcount.append(float(nx - ny))
        if nx > ny:
            b_pos += 1
        elif ny > nx:
            b_neg += 1
        if ix[tid]["n_classifiable"] and iy[tid]["n_classifiable"]:
            dfrac.append(
                ix[tid]["counts"]["f2p"] / ix[tid]["n_classifiable"]
                - iy[tid]["counts"]["f2p"] / iy[tid]["n_classifiable"]
            )
    wil = wilcoxon_signed_rank(dcount)
    n_tasks = len(common)
    sign_p = mcnemar_exact_p(b_pos, b_neg)
    return {
        "pair": f"{label_x} vs {label_y}",
        "n_tasks": n_tasks,
        "sum_f2p_x": sum(ix[t]["counts"]["f2p"] for t in common),
        "sum_f2p_y": sum(iy[t]["counts"]["f2p"] for t in common),
        "n_tasks_more_f2p_x": b_pos,
        "n_tasks_more_f2p_y": b_neg,
        "n_tasks_tied": n_tasks - b_pos - b_neg,
        "mean_delta_f2p_count": round(sum(dcount) / len(dcount), 4) if dcount else None,
        "mean_delta_f2p_fraction": round(sum(dfrac) / len(dfrac), 4) if dfrac else None,
        "sign_test_mcnemar_exact_p": round(sign_p, 4),
        "wilcoxon": wil,
    }


def _mcnemar_from_maps(
    map_x: dict[str, float | None], map_y: dict[str, float | None], label_x: str, label_y: str
) -> dict[str, Any]:
    """由 {task_id: 二值/None} 映射做**标准口径**配对（双方非 None），返回 McNemar 族统计。"""
    common = sorted(set(map_x) & set(map_y))
    b_pos = b_neg = 0
    n_pairs = 0
    for tid in common:
        x, y = map_x[tid], map_y[tid]
        if x is None or y is None:
            continue
        n_pairs += 1
        x1, y1 = int(float(x) == 1.0), int(float(y) == 1.0)
        if x1 and not y1:
            b_pos += 1
        elif y1 and not x1:
            b_neg += 1
    delta = (b_pos - b_neg) / n_pairs * 100 if n_pairs else 0.0
    p = mcnemar_exact_p(b_pos, b_neg)
    return {
        "pair": f"{label_x} vs {label_y}",
        "n_pairs": n_pairs,
        "b_pos_x_only": b_pos,
        "b_neg_y_only": b_neg,
        "ratio": f"{b_pos}:{b_neg}",
        "delta_pp": round(delta, 2),
        "p_value": round(p, 4),
        "bf10": bayes_factor_10(b_pos, b_neg),
        "mde_pp": mde_two_proportion(n_pairs),
        "verdict": verdict({"p_value": round(p, 4), "delta_pp": round(delta, 2)}),
    }


def hang_sensitivity(runs: list[dict[str, Any]], arm_letters: tuple[str, ...] = ("A", "B", "C", "D")) -> dict[str, Any]:
    """敏感性分析（替代口径，非主口径）：把「buggy 侧挂死 ∧ fixed 侧全绿」记为检出。

    背景：主口径沿用 detection_rate 的三段判据，buggy 侧 30s 不终止 → 不可测
    （None）。但"套件在缺陷代码上死循环、在修复代码上通过"在另一种同样合理的
    口径下就是**检出**（红色信号来自缺陷）。本函数量化该口径切换对 M4 配对结论
    的影响，用来暴露任务级二值口径 + N=35 的脆弱性；**不改变**主口径任何数字。
    """
    alt_maps: dict[str, dict[str, float | None]] = {}
    flips: dict[str, list[str]] = {}
    for r in runs:
        letter = r["source"]["arm_letter"]
        label = r["source"]["label"]
        m: dict[str, float | None] = {}
        fl: list[str] = []
        for t in r["tasks"]:
            if t["suite_class"] == "material_missing":
                continue
            hang_detect = (
                bool(t["buggy"]["timed_out"])
                and not bool(t["fixed"]["timed_out"])
                and t["fixed"]["rc"] == 0
                and not bool(t["fixed"]["exec_error_heuristic"])
            )
            if hang_detect:
                fl.append(t["task_id"])
            m[t["task_id"]] = 1.0 if hang_detect else t["task_level_reproduced"]
        flips[label] = sorted(fl)
        if letter:
            alt_maps[letter] = m
    contrasts: list[dict[str, Any]] = []
    pairs = [("A", "B"), ("C", "D")]
    for x, y in pairs:
        if x in alt_maps and y in alt_maps:
            contrasts.append(_mcnemar_from_maps(alt_maps[x], alt_maps[y], f"{x}_alt", f"{y}_alt"))
    if all(k in alt_maps for k in arm_letters):
        merged_x = dict(alt_maps["A"])
        merged_x.update({f"{k}_rep": v for k, v in alt_maps["C"].items()})
        merged_y = dict(alt_maps["B"])
        merged_y.update({f"{k}_rep": v for k, v in alt_maps["D"].items()})
        contrasts.append(_mcnemar_from_maps(merged_x, merged_y, "AC_alt", "BD_alt"))
    return {
        "caliber": "替代口径（敏感性）：buggy 侧 30s 挂死 ∧ fixed 侧 rc=0 且无执行错误 → 记检出 1.0；其余同主口径",
        "n_flip_tasks_per_source": {k: len(v) for k, v in flips.items()},
        "flip_task_ids_per_source": flips,
        "contrasts": contrasts,
    }


def load_reused_report(path: Path, sources: list[dict[str, Any]], gold_info: dict[str, Any]) -> dict[str, Any]:
    """从既有 TESTLEVEL_DETECTION.json 重建 runs（仅供 --reuse-json 重算分析/渲染）。"""
    prev = json.loads(path.read_text(encoding="utf-8"))
    by_set: dict[str, list[dict[str, Any]]] = {}
    for t in prev.get("tasks", []):
        by_set.setdefault(str(t.get("set")), []).append(t)
    agg_by_label = {a["label"]: a for a in prev.get("aggregates", {}).get("per_source", [])}
    raw_by_key: dict[tuple[str, str], dict[str, Any]] = {
        (str(hc.get("set")), str(hc.get("task_id"))): hc for hc in prev.get("handcheck", [])
    }
    runs: list[dict[str, Any]] = []
    for s in sources:
        tasks = by_set.get(s["label"], [])
        agg = agg_by_label.get(s["label"], {})
        runs.append(
            {
                "source": {**{k: v for k, v in s.items() if k != "path"}, "path": str(s["path"])},
                "n_rows": int(agg.get("n_rows_in_artifact", len(tasks))),
                "skipped_no_gold": list(gold_info.get("excluded_task_ids", [])),
                "wall_s": float(agg.get("wall_s", 0.0)),
                "tasks": tasks,
                "handcheck_raw": raw_by_key,
            }
        )
    return {
        "runs": runs,
        "wall_clock_total_s": float(prev.get("meta", {}).get("wall_clock_total_s", 0.0)),
        "prev_meta": {
            "cmdline": prev.get("meta", {}).get("sweep_cmdline") or prev.get("meta", {}).get("cmdline", ""),
            "n_pytest_runs": prev.get("meta", {}).get("n_pytest_runs"),
            "cap_seconds": prev.get("meta", {}).get("cap_seconds"),
            "jobs": prev.get("meta", {}).get("jobs"),
            "generated_at_local": prev.get("meta", {}).get("generated_at_local", ""),
        },
    }


def mde_table(n_task_pairs: int, n_test_pairs: int, psi_task: float, psi_test: float) -> dict[str, Any]:
    """任务级 vs 测试级 MDE（口径并列：两比例近似 + 配对近似）。"""
    return {
        "task_level": {
            "n_pairs": n_task_pairs,
            "mde_two_proportion_pp": mde_two_proportion(n_task_pairs),
            "psi_discordance": round(psi_task, 4),
            "mde_paired_pp": round(mde_paired_pp(n_task_pairs, psi_task), 2)
            if mde_paired_pp(n_task_pairs, psi_task) is not None
            else None,
            "power_at_observed_delta_8pp": round(power_at_delta(8.0, n_task_pairs, psi_task) or 0.0, 4)
            if power_at_delta(8.0, n_task_pairs, psi_task) is not None
            else None,
        },
        "test_level": {
            "n_pairs": n_test_pairs,
            "mde_two_proportion_pp": mde_two_proportion(n_test_pairs),
            "psi_discordance": round(psi_test, 4),
            "mde_paired_pp": round(mde_paired_pp(n_test_pairs, psi_test), 2)
            if mde_paired_pp(n_test_pairs, psi_test) is not None
            else None,
            "power_at_observed_delta_8pp": round(power_at_delta(8.0, n_test_pairs, psi_test) or 0.0, 4)
            if power_at_delta(8.0, n_test_pairs, psi_test) is not None
            else None,
        },
    }


# ─── 手工核验证据 ──────────────────────────────────────────────────────
def select_handcheck(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """确定性选取手工核验样本：(1) batch5 中 f2p 最多者；(2) batch5 中首个 f2f>0 者；(3) 首个超时者。"""
    b5 = [t for t in tasks if t["set"] == "quixbugs50_batch5"]
    out: list[dict[str, Any]] = []
    if b5:
        best = sorted(b5, key=lambda t: (-t["counts"]["f2p"], t["task_id"]))[0]
        out.append({"rule": "batch5 中 f2p 计数最大（并列取 task_id 最小）", "task": best})
        f2f_cases = sorted([t for t in b5 if t["counts"]["f2f"] > 0], key=lambda t: t["task_id"])
        if f2f_cases:
            out.append({"rule": "batch5 中 task_id 最小的 f2f>0 套件", "task": f2f_cases[0]})
        to_cases = sorted([t for t in b5 if t["suite_class"] == "timeout"], key=lambda t: t["task_id"])
        if to_cases:
            out.append({"rule": "batch5 中 task_id 最小的超时套件", "task": to_cases[0]})
    return out


_PYTEST_SUMMARY_RE = re.compile(r"(\d+)\s+(failed|passed|error|errors|skipped|xfailed|xpassed|deselected)")
# R2：pytest 汇总行尾部耗时（`in 0.09s` / `in 1.23s`）——运行时时延，
# 不可复现，渲染前归一化为 `<t>`（工件复现性要求）。
_ELAPSED_RE = re.compile(r"\bin \d+(?:\.\d+)?s\b")


def independent_check(
    handcheck: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    gold: dict[str, Any],
    *,
    cap_seconds: int,
) -> dict[str, Any]:
    """独立复核（不走本脚本的插件/文本解析器）：重跑手工核验任务，直接读 **pytest 自己的汇总行**。

    对照口径：pytest 汇总行给出的 (failed, passed) 必须等于工件逐测试表在该侧推出的
    (fail+error, pass) 计数。超时套件在两侧都会再次超时（记 `reproduced_timeout`），
    其部分 node 数据不参与对照（工件对超时套件一律记 `other`，本就不产生 f2p）。
    """
    from src.utils.process_utils import run_with_timeout

    out: dict[str, Any] = {}
    src_by_label = {s["label"]: s for s in sources}
    for hc in handcheck:
        t = hc["task"]
        label, tid = t["set"], t["task_id"]
        src = src_by_label.get(label)
        task = gold.get(tid)
        if src is None or task is None:
            continue
        rows = json.loads(Path(src["path"]).read_text(encoding="utf-8"))["results"]["aitester"]["details"]
        row = next((r for r in rows if r.get("task_id") == tid), None)
        mat = _extract_gold_material(task)
        module = mat[0] if mat else ""
        if row is None or not module:
            continue
        entry: dict[str, Any] = {"task_id": tid, "set": label, "sides": {}}
        for side, code in (("buggy", str(getattr(task, "instance_code", "") or "")), ("fixed", _gold_fixed_code(task))):
            tmpdir = tempfile.mkdtemp(prefix=f"indep_{module}_")
            try:
                test_path, pythonpath = _prepare_packaged_test_tree(
                    tmpdir, code, str(row.get("generated_test") or ""), module
                )
                env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": pythonpath, "COLUMNS": "200"}
                res = run_with_timeout(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        test_path,
                        "-v",
                        "--tb=no",
                        "-p",
                        "no:cacheprovider",
                        "--no-header",
                        "--color=no",
                    ],
                    timeout=cap_seconds,
                    cwd=tmpdir,
                    text=True,
                    logger_name="testlevel_indep",
                    env=env,
                )
                stdout = res.stdout or ""
                timed_out = bool(getattr(res, "timed_out", False))
                last = next((ln for ln in reversed(stdout.strip().splitlines()) if ln.strip()), "")
                counted = {m.group(2): int(m.group(1)) for m in _PYTEST_SUMMARY_RE.finditer(last)}
                artifact_fail = None if timed_out else sum(1 for r in t["tests"] if r[side] in ("fail", "error"))
                artifact_pass = None if timed_out else sum(1 for r in t["tests"] if r[side] == "pass")
                pytest_fail = counted.get("failed", 0) + counted.get("error", 0) + counted.get("errors", 0)
                pytest_pass = counted.get("passed", 0)
                entry["sides"][side] = {
                    "rc": None if timed_out else res.returncode,
                    "timed_out": timed_out,
                    # R2（2026-10-15）：pytest 汇总行尾部的 `in 0.09s` 是运行时时延，
                    # **本质不可复现**（同机两次运行即不同）⇒ 渲染前归一化为 `<t>`，
                    # 使本件的独立复核表在重复运行下逐字节稳定（工件复现性硬要求）。
                    # 计数（failed/passed）不受影响，仍是实测值。
                    "pytest_summary_line": (
                        "(超时终止，无 pytest 汇总行)" if timed_out else _ELAPSED_RE.sub("in <t>s", last.strip())[:160]
                    ),
                    "last_output_line_before_kill": last.strip()[:160] if timed_out else "",
                    "pytest_counts": counted,
                    "artifact_pass": artifact_pass,
                    "artifact_fail": artifact_fail,
                    "match": None if timed_out else bool(pytest_pass == artifact_pass and pytest_fail == artifact_fail),
                }
            finally:
                import shutil

                shutil.rmtree(tmpdir, ignore_errors=True)
        both = entry["sides"]
        entry["verdict"] = (
            "reproduced_timeout"
            if all(both[s]["timed_out"] for s in both)
            else ("match" if all(both[s].get("match") for s in both) else "MISMATCH")
        )
        out[f"{label}/{tid}"] = entry
        print(
            f"[tl] 独立复核 {label}/{tid}: {entry['verdict']} "
            f"(buggy rc={both['buggy']['rc']}, fixed rc={both['fixed']['rc']})",
            flush=True,
        )
    return out


def render_handcheck(hc: dict[str, Any], max_lines: int = 60) -> list[str]:
    """把一次手工核验渲染成「原始输出 ↔ 逐测试分类」并排证据。"""
    t = hc["task"]
    lines = [
        f"### {t['set']} / `{t['task_id']}`（选取规则：{hc['rule']}）",
        "",
        f"- 归档 detection_rate = `{t['archived_detection_rate']}`；本次复算 = `{t['task_level_reproduced']}`；"
        f"suite_class = `{t['suite_class']}`",
        f"- buggy 侧：rc={t['buggy']['rc']} timed_out={t['buggy']['timed_out']} "
        f"node ids={t['buggy']['n_nodeids_plugin']}（-v 解析={t['buggy']['n_nodeids_verbose']}）"
        f" 解析器={t['buggy']['parser']}",
        f"- fixed 侧：rc={t['fixed']['rc']} timed_out={t['fixed']['timed_out']} "
        f"node ids={t['fixed']['n_nodeids_plugin']}（-v 解析={t['fixed']['n_nodeids_verbose']}）"
        f" 解析器={t['fixed']['parser']}",
        "",
        f"**原始 `pytest -v` 输出（buggy 侧，节选末尾 {max_lines} 行）**：",
        "",
        "```text",
    ]
    lines += [ln for ln in t["buggy_stdout"].strip().splitlines()[-max_lines:]]
    lines += ["```", "", f"**原始 `pytest -v` 输出（fixed 侧，节选末尾 {max_lines} 行）**：", "", "```text"]
    lines += [ln for ln in t["fixed_stdout"].strip().splitlines()[-max_lines:]]
    lines += [
        "```",
        "",
        "**解析后的逐测试分类（node id / buggy / fixed / class）**：",
        "",
        "| node id | buggy | fixed | class |",
        "|---|---|---|---|",
    ]
    for r in t["tests"]:
        lines.append(f"| `{r['node']}` | {r['buggy']} | {r['fixed']} | **{r['cls']}** |")
    lines.append("")
    return lines


# ─── 报告落盘 ──────────────────────────────────────────────────────────
def _fmt(v: Any) -> str:
    return "`unmeasured`" if v is None else f"{v}"


def _render_suite_size_confound(report: dict[str, Any]) -> list[str]:
    """§4.6：任务聚类「计数 vs 占比」方向不一致的根因 = 套件规模混淆（measured）。

    背景：§4.3 的 primary 对比出现「Δf2p(计数) = +0.17（SpecExpr 多）vs Δf2p(占比)
    = −0.029（NL 多）」的方向不一致。本函数从逐任务计数导出可核验解释：
    两臂**生成的测试数量**本身不同（SpecExpr 臂系统性更多）⇒ 计数尺度结构上偏向
    生成量大的臂，不代表检出能力更强。故跨臂比较**不得**以 f2p 绝对计数作因变量。

    全部量由 report["tasks"]（measured）导出，零新增测量 —— 渲染即可复算。
    """
    by_set: dict[str, dict[str, tuple[int, int]]] = {}
    for t in report["tasks"]:
        if t.get("suite_class") == "material_missing":
            continue
        c = t.get("counts") or {}
        n_class = sum(c.get(k, 0) for k in ("f2p", "p2p", "f2f", "p2f"))
        by_set.setdefault(str(t.get("set")), {})[str(t.get("task_id"))] = (n_class, c.get("f2p", 0))
    pairs = [("arm_A_specir", "arm_B_nl"), ("arm_C_specir_repeat", "arm_D_nl_repeat")]
    out: list[str] = [
        "§4.3 表中 primary 对比出现「计数方向为正（SpecExpr 多）vs 占比方向为负（NL 多）」",
        "的不一致。本节由逐任务计数导出其根因：**套件规模（生成测试数量）差异造成的混淆**，",
        "不是度量矛盾。",
        "",
    ]
    for x, y in pairs:
        if x not in by_set or y not in by_set:
            continue
        common = sorted(set(by_set[x]) & set(by_set[y]))
        if not common:
            continue
        nx = sum(by_set[x][k][0] for k in common)
        ny = sum(by_set[y][k][0] for k in common)
        fx = sum(by_set[x][k][1] for k in common)
        fy = sum(by_set[y][k][1] for k in common)
        d_count = [by_set[x][k][1] - by_set[y][k][1] for k in common if by_set[x][k][0] and by_set[y][k][0]]
        d_frac = [
            by_set[x][k][1] / by_set[x][k][0] - by_set[y][k][1] / by_set[y][k][0]
            for k in common
            if by_set[x][k][0] and by_set[y][k][0]
        ]
        mean = lambda v: (sum(v) / len(v)) if v else 0.0  # noqa: E731
        n_more_y = sum(1 for v in d_frac if v < 0)
        n_more_x = sum(1 for v in d_frac if v > 0)
        out += [
            f"**{x} vs {y}**（共同 {len(common)} 任务）",
            "",
            f"| 量 | {x} | {y} | 差 |",
            "|---|---|---|---|",
            f"| 可分类测试总数 | **{nx}** | **{ny}** | {nx - ny:+d}（**{(nx / ny - 1) * 100:+.1f}%**） |",
            f"| 每任务平均可分类测试数 | **{nx / len(common):.1f}** | **{ny / len(common):.1f}** | {(nx - ny) / len(common):+.1f} |",
            f"| Σf2p（计数尺度） | {fx} | {fy} | {fx - fy:+d} |",
            f"| f2p 率（归一后） | **{fx / nx:.4f}** | **{fy / ny:.4f}** | **{(fx / nx - fy / ny) * 100:+.2f}pp** |",
            f"| Δf2p 逐任务均值 | 计数 **{mean(d_count):+.4f}** | 占比 **{mean(d_frac):+.4f}** | "
            f"占比口径下 NL 更多 {n_more_y} : SpecExpr 更多 {n_more_x} |",
            "",
        ]
    out += [
        "",
        "> 读法：计数尺度比较的是「两臂各自生成的测试数量」，而两臂**生成量本身不同**",
        "> （primary 对 A 比 B 多 +15.7%；repeat 对 C 比 D 少 −1.8%）⇒ 计数口径被套件规模",
        "> 混淆，**其方向可随生成量差异而翻转**（primary 对即由 +0.19 翻为 −0.03），不等于",
        "> 检出能力差异；按规模归一后两对同向（均无正效应，NL 略高）。因此原「primary 任务",
        "> 聚类方向反向」的表述**不成立**。",
        "",
        "> **对论文的措辞要求**：跨臂比较**不得**使用「f2p 绝对计数」作因变量（未控生成量）；",
        "> 若报告计数，必须同时给出可分类测试总数或改用占比/率。§4.3 的 Δf2p(计数) 列仅作",
        "> 描述性补充，判定以占比与任务级二值口径为准。",
        "",
    ]
    return out


def render_readme(report: dict[str, Any], sources: list[dict[str, Any]], cmdline: str) -> str:
    agg = report["aggregates"]["per_source"]
    pooled = report["aggregates"]["pooled"]
    ts = report["testlevel_stats"]
    lines: list[str] = [
        "# QuixBugs 测试级检出画像（TESTLEVEL_DETECTION，2026-10-15 批次九）",
        "",
        "> 零 LLM：只读归档 benchmark JSON + 本地 pytest 子进程；无网络/LLM 调用。",
        "> 本目录三件套：`README.md`（方法学+表格+核验证据）、`TESTLEVEL_DETECTION.json`（机器可读）、",
        "> `SHA256SUMS.txt`（`shasum -a 256` 前两件）。",
        "",
        "## 0. 口径标签（全文一致）",
        "",
        "| 标签 | 含义 |",
        "|---|---|",
        "| `measured` | 本次本地 pytest 运行直接观测到的计数/比率（可复算） |",
        "| `computed` | 由 measured 计数经精确闭式公式推导（McNemar 精确 p、δ、贝叶斯因子） |",
        "| `estimated` | 模型近似（MDE、功效：正态近似；BF 依赖 Jeffreys 先验模型） |",
        "| `unmeasured` | 本次无法测量（超时/无 gold 材料/无逐测试数据），**不填 0** |",
        "",
        "判定口径（逐测试，互斥）：`f2p` = buggy 侧失败 ∧ fixed 侧通过；`p2p` = 两侧通过；",
        "`f2f` = 两侧失败；`p2f` = buggy 通过 ∧ fixed 失败；`other` = 单侧不可用",
        "（收集错误 / 超时 / node id 缺失 / skipped）。",
        "「失败」含 call 相位断言失败与 setup/teardown 异常（相位细分见 §3.6）。",
        "",
        "## 1. 方法与命令",
        "",
        f"1. 任务集 = `src.datasets.dataset_realbugs.QuixBugsDataset()`（`{report['meta']['gold_root']}`）；",
        "   仅 `metadata.test_cases` ∧ `metadata.fixed` 均非空者进入口径：",
        f"   **{report['meta']['gold_info']['n_tasks_gold_eligible']} / {report['meta']['gold_info']['n_tasks_loaded']}** 个任务",
        f"（排除 {report['meta']['gold_info']['n_tasks_excluded_no_gold']} 个无 gold 材料程序："
        + ", ".join(f"`{x}`" for x in report["meta"]["gold_info"]["excluded_task_ids"][:3])
        + " …）。",
        "2. 材料派生复用单一事实源：模块名 ← `_m1_metrics._extract_gold_material`；gold 代码 ← `_gold_fixed_code`；",
        "   缺陷代码 ← `task.instance_code`；生成套件 ← 归档行 `generated_test`。",
        "3. 物化 = `_m1_metrics._prepare_packaged_test_tree`（packaged 分支，与 `_run_pytest_in_tmp` 判分链路逐字同口径：",
        "   双布局模块 + `node.py`/`load_testdata.py`/`json_testcases` + `pytest.use_correct=False` prelude）。",
        "4. 同一套件跑两次：`pytest <test> -v --tb=no -rA -p no:cacheprovider -p _dsh_outcomes`，",
        "   一次对缺陷代码、一次对 gold 修复代码；`_dsh_outcomes` 是**只做记录**的插件（逐 phase 写 JSONL）。",
        "   两路解析（插件 JSONL + `-v` 文本）交叉校验，不一致即暴露（见 §3.6）。",
        f"5. 每次运行上限 `{report['meta']['cap_seconds']}s`（与 `emse_test_sanity_audit.py` 同口径）；超时 = 不可测。",
        "",
        "复现命令：",
        "",
        "```bash",
        f"{cmdline}",
        "```",
        "",
        "（脚本内部子进程命令行即上表第 4 步；逐套件哈希/计数见 JSON `tasks[].buggy.stdout_sha256`。）",
        *(
            [
                "",
                "本件为**分析重算**（`--reuse-json`：不重跑 pytest，只重算聚合/统计/渲染；",
                "全部 measured 字段来自上面那条完整跑批命令的工件）：",
                "",
                "```bash",
                f"{report['meta']['cmdline']}",
                "```",
            ]
            if report["meta"].get("reuse_json")
            else []
        ),
        "",
        "### 1.1 来源工件（本次实际使用，含 sha256）",
        "",
        "| 来源 | 角色 | 工件 | sha256（前 16） | cache_namespace | 归档行数 | gold 合资格 | 实跑套件 | 跳过(无 gold) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s, a in zip(sources, agg, strict=True):
        lines.append(
            f"| `{s['label']}` | {s['kind']} | `{Path(s['path']).name}` | `{s['sha256'][:16]}` | "
            f"`{s['cache_namespace'] or '-'}` | {a['n_rows_in_artifact']} | {a['n_tasks_gold_eligible']} | "
            f"{a['n_suites_run']} | {a['n_tasks_skipped_no_gold']} |"
        )
    lines += [
        "",
        f"合计：**{pooled['n_sources']} 个来源 × {agg[0]['n_tasks_gold_eligible']} 个 gold-eligible 任务 = "
        f"{pooled['n_suites_run']} 个套件 × 2 侧 = {pooled['n_suites_run'] * 2} 次 pytest 运行**；"
        f"总墙钟 {report['meta']['wall_clock_total_s']}s。",
        "",
        "## 2. 执行总览（measured）",
        "",
        "| 来源 | 套件 | detecting_clean | detecting_invalid | blind_clean | invalid_only | timeout | no_pertest_data | buggy 超时 | fixed 超时 | 无可解析逐测试数据的任务数 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    keymap = [
        ("detecting_clean", "detecting_clean"),
        ("detecting_invalid", "detecting_invalid"),
        ("blind_clean", "blind_clean"),
        ("invalid_only", "invalid_only"),
        ("timeout", "timeout"),
        ("no_pertest_data", "no_pertest_data"),
    ]
    for a in [*agg, pooled_proxy(pooled)]:
        sc = a.get("suite_class_counts", {})
        lines.append(
            f"| `{a['label']}` | {a['n_suites_run']} | "
            + " | ".join(str(sc.get(k, 0)) for k, _ in keymap)
            + f" | {len(a['timeouts']['buggy'])} | {len(a['timeouts']['fixed'])} | {a['n_no_pertest_data']} |"
        )
    lines += [
        "",
        "> 套件级标签（互斥，判定顺序：timeout → no_pertest_data → 四分类）：",
        "> `detecting_clean` = f2p≥1 且 f2f=0；`detecting_invalid` = f2p≥1 且 f2f≥1；",
        "> `blind_clean` = f2p=0 且 f2f=0（可能含 p2f/other）；`invalid_only` = f2p=0 且 f2f≥1；",
        "> `timeout` = 任一侧 30s 未终结；`no_pertest_data` = 两侧都跑完但至少一侧无任何可解析 node id。",
        "> **注意**：`detecting_clean` 只排除 f2f，**不等价于** task-level `detection_rate`=1.0——",
        "> 后者还要求 fixed 侧 rc=0，因此 p2f>0（在修复代码上反而失败）的套件仍可能落进 `detecting_clean`。",
        "> 反向成立：det=1.0 的套件必然是 `detecting_clean` 且 f2f=p2f=0（下表 §3.4 的 f2p=0 异常清单为空即此校验）。",
        "",
        "## 3. Step 2 指标（显式分母）",
        "",
        "### 3.1 测试级 F2P 率",
        "",
        "| 来源 | f2p | 可分类测试 n（两侧都出现） | 池化 F2P 率（f2p/n） | 并集分母 n | 并集口径 F2P 率 | 单侧仅 buggy | 单侧仅 fixed |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for a in [*agg, pooled_proxy(pooled)]:
        lines.append(
            f"| `{a['label']}` | {a['class_totals']['f2p']} | {a['n_classifiable_total']} | "
            f"{_fmt(a['pooled_f2p_rate'])} | {a['n_union_total']} | {_fmt(a['pooled_f2p_rate_union_denom'])} | "
            f"{a.get('n_only_buggy', 'unmeasured')} | {a.get('n_only_fixed', 'unmeasured')} |"
        )
    pt = pooled["per_task_f2p_fraction"]
    lines += [
        "",
        f"逐任务 F2P 占比（`f2p / 可分类测试数`，pooled 全部 {pt['n']} 个套件中可分类者）："
        f"mean={_fmt(pt['mean'])}，median={_fmt(pt['median'])}，Q1={_fmt(pt['q1'])}，Q3={_fmt(pt['q3'])}，"
        f"min={_fmt(pt['min'])}，max={_fmt(pt['max'])}。",
        "",
        "占比直方图（pooled，measured）：",
        "",
        "| 区间 | 套件数 |",
        "|---|---|",
    ]
    for k, v in pooled["per_task_f2p_fraction_histogram"].items():
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "### 3.2 盲测质量（blind mass，measured）",
        "",
        "| 来源 | p2p | f2p | p2p/可分类 | p2p/(p2p+f2p) |",
        "|---|---|---|---|---|",
    ]
    for a in [*agg, pooled_proxy(pooled)]:
        bm = a["blind_mass"]
        lines.append(
            f"| `{a['label']}` | {bm['p2p']} | {bm['f2p']} | {_fmt(bm['p2p_over_classifiable'])} | "
            f"{_fmt(bm['p2p_over_p2p_plus_f2p'])} |"
        )
    lines += [
        "",
        "### 3.3 无效质量（invalid mass：在**正确代码**上失败的测试）",
        "",
        "| 来源 | f2f | f2f/可分类 | f2f>0 的套件数 | 套件在 fixed 上 rc=0（绿） | 套件绿率(fixed) | 套件在 buggy 上 rc=0 | p2f（反向） | p2f>0 套件数 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for a in [*agg, pooled_proxy(pooled)]:
        im = a["invalid_mass"]
        iv = a["inverted_mass"]
        lines.append(
            f"| `{a['label']}` | {im['f2f']} | {_fmt(im['f2f_over_classifiable'])} | {im['n_suites_with_f2f']} | "
            f"{im['n_suites_green_on_fixed_rc0']} | {_fmt(im['suite_green_rate_on_fixed'])} | "
            f"{im['n_suites_green_on_buggy_rc0']} | {iv['p2f']} | {iv['n_suites_with_p2f']} |"
        )
    lines += [
        "",
        "> 对照 `emse_test_sanity_20261015/SANITY_AUDIT.json`（**扁平物化**口径，仅 fixed 侧、30s）：",
        "> batch5 生成套件 30 pass / 17 fail / 3 nonterminate。本件用 packaged 物化（detection_rate 的判分链路），",
        "> 两者差异只可能来自物化口径与超时口径，逐任务对账见 §5。",
        "",
        "### 3.4 任务级检出的测试级换算（headline，measured）",
        "",
        "对**归档 `detection_rate` = 1.0** 的套件，统计其 f2p 测试函数个数分布：",
        "",
        "| 来源 | det=1.0 套件数 | f2p=0 | **f2p=1（单测试扛下）** | f2p=2 | f2p≥3 | det1 内 f2p 合计 | det1 内可分类测试合计 | det1 内平均 f2p |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for a in [*agg, pooled_proxy(pooled)]:
        dc = a["detection_conversion"]
        h = dc["f2p_count_distribution"]
        lines.append(
            f"| `{a['label']}` | {dc['n_archived_detection_1']} | {h['0']} | **{h['1']}** | {h['2']} | {h['3+']} | "
            f"{dc['f2p_total_among_det1']} | {dc['classifiable_total_among_det1']} | {_fmt(dc['f2p_mean_among_det1'])} |"
        )
    pooled_dc = pooled["detection_conversion"]
    lines += [
        "",
        f'**headline：{pooled_dc["n_archived_detection_1"]} 个任务级"检出"中，'
        f"{pooled_dc['n_single_test_carried']} 个（"
        f"{round(pooled_dc['n_single_test_carried'] / pooled_dc['n_archived_detection_1'] * 100, 1) if pooled_dc['n_archived_detection_1'] else 'unmeasured'}%）"
        f"由 1 个测试函数扛下，{pooled_dc['n_multi_test']} 个由 ≥2 个测试函数支撑**（pooled，measured）。",
        "",
        f"- det=1.0 套件里 f2p=0 的异常情况：{pooled_dc['n_det1_but_zero_f2p'] or '无'}（应为空——若非空即口径矛盾，需调查）。",
        f"- det=1.0 套件的 f2p 占其可分类测试总数："
        f"{pooled_dc['f2p_total_among_det1']}/{pooled_dc['classifiable_total_among_det1']} = "
        f"{(round(pooled_dc['f2p_total_among_det1'] / pooled_dc['classifiable_total_among_det1'], 4) if pooled_dc['classifiable_total_among_det1'] else 'unmeasured')}。",
        "",
        "### 3.5 f2p 的相位细分（buggy 侧 call 相位 vs setup/teardown 相位，measured）",
        "",
        "| 来源 | f2p（buggy 侧 call 相位失败：断言失败或测试体内未捕获异常） | f2p（buggy 侧 setup/teardown 异常） |",
        "|---|---|---|",
    ]
    for a in [*agg, pooled_proxy(pooled)]:
        ps = a["f2p_phase_split"]
        lines.append(
            f"| `{a['label']}` | {ps['call_phase_failed_on_buggy']} | {ps['setup_or_teardown_error_on_buggy']} |"
        )
    lines += [
        "",
        "> 「call 相位失败」= pytest 在测试函数体内记录 `failed`：既含 `assert` 失败，也含被测缺陷代码",
        "> 直接抛出的未捕获异常（如 `IndexError`/`TypeError`）——两者都是真实的缺陷触发路径。",
        "> setup/teardown 相位异常单列（夹具/清理阶段失败，与测试体断言无关）。",
        "> 本件未保存失败消息 → 「纯断言失败」这一更细的子类**unmeasured**（不猜）。",
        "",
        "### 3.6 解析与数据完整性（measured）",
        "",
        "| 来源 | 插件/-v 双路一致条数 | 不一致条数 | -v 回退侧数 | 无解析器侧数 | 超时（任一侧） | 无可解析逐测试数据的任务 |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in [*agg, pooled_proxy(pooled)]:
        pc = a.get(
            "parser_crosscheck",
            {
                "n_plugin_verbose_agreements": "unmeasured",
                "n_mismatches": "unmeasured",
                "n_sides_verbose_fallback": "unmeasured",
                "n_sides_no_parser": "unmeasured",
            },
        )
        lines.append(
            f"| `{a['label']}` | {pc['n_plugin_verbose_agreements']} | {pc['n_mismatches']} | "
            f"{pc['n_sides_verbose_fallback']} | {pc['n_sides_no_parser']} | {a['timeouts']['n_sides_timed_out']} | "
            f"{a['n_no_pertest_data']} |"
        )
    lines += [
        "",
        "## 4. Step 3：任务级 vs 测试级配对功效",
        "",
        "### 4.1 任务级（复现既有结论，computed）",
        "",
        "复用 `experiments/emse_quixbugs_specir_expand.py::build_analysis`（同一实现，非另写）：",
        "",
        "| 对比 | n | 仅 specir 检出 | 仅 NL 检出 | δ(pp) | McNemar 精确 p | BF10(Jeffreys) | MDE(pp, 两比例) | 判定 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for key, row in ts["task_level"].items():
        lines.append(
            f"| {row.get('pair', key)} | {row['n_pairs']} | {row['b_pos_specir_only']} | {row['b_neg_nl_only']} | "
            f"{row['delta_pp']} | {row['p_value']} | {row['bf10']} | {row['mde_pp']} | `{row['verdict']}` |"
        )
    lines += [
        "",
        "### 4.2 测试级配对（按 node id 配对，computed）",
        "",
        "| 对比 | 配对任务数 | 共享 node id | X 独有 | Y 独有 | 因 other 丢弃 | 配对数 n | 仅 X f2p | 仅 Y f2p | 双侧 f2p | 都不 f2p | δ(pp) | p(McNemar 精确) | BF10 | MDE(pp) | 判定 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in ts["test_level"]:
        lines.append(
            f"| {row['pair']} | {row['n_tasks_paired']} | {row['n_test_nodeids_shared']} | {row['n_nodeids_x_only']} | "
            f"{row['n_nodeids_y_only']} | {row['n_shared_dropped_other']} | {row['n_pairs_testlevel']} | "
            f"{row['b_pos_x_only_f2p']} | {row['b_neg_y_only_f2p']} | {row['both_f2p']} | {row['neither_f2p']} | "
            f"{row['delta_pp']} | {row['p_mcnemar_exact']} | {row['bf10_expand']} | {row['mde_two_proportion_pp']} | "
            f"`{row['verdict_rule']}` |"
        )
    lines += [
        "",
        "**读法（关键）**：测试级「共享 node id」极少——两个臂是**独立生成**的测试套件，",
        "函数名大多不同，因此按 node id 严格配对会丢掉绝大部分观测（配对 n 远小于双臂测试总数）。",
        "这不是 bug，而是「测试级配对」这一口径的**固有代价**，也正是必须同时给任务聚类变体的原因。",
        "",
        "### 4.3 任务聚类变体（每任务一个观测单位，防伪重复，computed）",
        "",
        "| 对比 | 任务 n | Σf2p(X) | Σf2p(Y) | X 更多的任务 | Y 更多的任务 | 并列 | 平均 Δf2p(计数) | 平均 Δf2p(占比) | 符号检验(McNemar 精确) p | Wilcoxon 精确 p | Wilcoxon 正态近似 p |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in ts["task_clustered"]:
        w = row["wilcoxon"]
        lines.append(
            f"| {row['pair']} | {row['n_tasks']} | {row['sum_f2p_x']} | {row['sum_f2p_y']} | {row['n_tasks_more_f2p_x']} | "
            f"{row['n_tasks_more_f2p_y']} | {row['n_tasks_tied']} | {_fmt(row['mean_delta_f2p_count'])} | "
            f"{_fmt(row['mean_delta_f2p_fraction'])} | {row['sign_test_mcnemar_exact_p']} | {_fmt(w.get('p_exact'))} | "
            f"{_fmt(w.get('p_normal_approx'))} |"
        )
    mt = ts["mde"]
    lines += [
        "",
        "### 4.4 MDE 对照（estimated：正态近似模型）",
        "",
        "| 层级 | n | ψ（不一致率） | MDE 两比例(pp) | MDE 配对(pp) | 8pp 处功效 |",
        "|---|---|---|---|---|---|",
        f"| 任务级（primary A vs B） | {mt['task_level']['n_pairs']} | {mt['task_level']['psi_discordance']} | "
        f"{mt['task_level']['mde_two_proportion_pp']} | {mt['task_level']['mde_paired_pp']} | "
        f"{mt['task_level']['power_at_observed_delta_8pp']} |",
        f"| 测试级（primary A vs B，按 node id） | {mt['test_level']['n_pairs']} | {mt['test_level']['psi_discordance']} | "
        f"{mt['test_level']['mde_two_proportion_pp']} | {mt['test_level']['mde_paired_pp']} | "
        f"{mt['test_level']['power_at_observed_delta_8pp']} |",
        f"| 测试级（任务聚类：n=任务数） | {mt['task_clustered_n_pairs']} | {mt['task_clustered_psi']} | "
        f"{mt['task_clustered_mde_two_proportion_pp']} | - | - |",
        "",
        "### 4.5 替代口径敏感性：buggy 侧挂死算不算检出（computed，非主口径）",
        "",
        f"{ts['hang_sensitivity']['caliber']}",
        "",
        "| 对比（替代口径） | n | 仅 X 检出 | 仅 Y 检出 | δ(pp) | McNemar 精确 p | BF10 | MDE(pp) | 判定 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in ts["hang_sensitivity"]["contrasts"]:
        lines.append(
            f"| {c['pair']} | {c['n_pairs']} | {c['b_pos_x_only']} | {c['b_neg_y_only']} | {c['delta_pp']} | "
            f"{c['p_value']} | {c['bf10']} | {c['mde_pp']} | `{c['verdict']}` |"
        )
    lines += [
        "",
        "被该口径翻转的任务（逐源，均为「buggy 侧 30s 挂死、fixed 侧全绿」）：",
        "",
        "| 来源 | 数量 | task_id |",
        "|---|---|---|",
    ]
    for label, ids in ts["hang_sensitivity"]["flip_task_ids_per_source"].items():
        lines.append(f"| `{label}` | {len(ids)} | {', '.join('`' + x + '`' for x in ids) if ids else '（无）'} |")
    lines += [
        "",
        "> 读法：主口径下这 1 个任务/源（`quixbugs__find_first_in_sorted`）因 buggy 侧挂死被判 `None`，",
        "> 从而**整体退出配对样本**（n=35 而非 41）；若改判为检出，配对 n 与 δ/p 都会变化。",
        "> 这说明任务级配对结论不仅样本小，而且**对「不可测」的记法敏感**；替代口径仅供敏感性披露，",
        "> 不作为本件或论文的主口径。",
        "",
        "### 4.6 任务聚类「计数 vs 占比」方向不一致的根因：**套件规模混淆**（measured）",
        "",
    ]
    lines += _render_suite_size_confound(report)
    lines += [
        "### 4.7 结论（逐条标注支撑口径）",
        "",
    ]
    lines += [f"- {x}" for x in ts["conclusions"]]
    lines += [
        "",
        "## 5. 任务级检测率复算对账（measured vs 归档）",
        "",
        "三段判据（`_compute_detection_rate` 同规则）在本次运行上复算，与归档 `detection_rate` 逐任务对账：",
        "",
        "| 来源 | 归档→复算（1.0→1.0） | (0.0→0.0) | (None→None) | 其他组合 | 不一致 |",
        "|---|---|---|---|---|---|",
    ]
    for a in agg:
        c = a["task_level_reconciliation"]["counts"]
        lines.append(
            f"| `{a['label']}` | {c.get('1.0->1.0', 0)} | {c.get('0.0->0.0', 0)} | {c.get('None->None', 0)} | "
            f"{sum(v for k, v in c.items() if k not in ('1.0->1.0', '0.0->0.0', 'None->None'))} | "
            f"{a['task_level_reconciliation']['n_disagree']} |"
        )
    lines += ["", "不一致逐条（若为空表则完全一致）：", ""]
    any_dis = [a for a in agg if a["task_level_reconciliation"]["n_disagree"]]
    if not any_dis:
        lines.append("（无）")
    else:
        lines += [
            "| 来源 | task_id | 归档 | 复算 | buggy rc | fixed rc | buggy 超时 | fixed 超时 | f2p/p2p/f2f/p2f/other | 归档 stop_reason |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for a in any_dis:
            for d in a["task_level_reconciliation"]["disagreements"]:
                cc = d["counts"]
                lines.append(
                    f"| `{a['label']}` | `{d['task_id']}` | {d['archived']} | {d['reproduced']} | {d['buggy_rc']} | "
                    f"{d['fixed_rc']} | {d['buggy_timed_out']} | {d['fixed_timed_out']} | "
                    f"{cc['f2p']}/{cc['p2p']}/{cc['f2f']}/{cc['p2f']}/{cc['other']} | `{d['archived_stop_reason']}` |"
                )
    lines += ["", "### 5.1 无逐测试数据的任务（不静默丢弃）", ""]
    for a in agg:
        lines.append(
            f"- `{a['label']}`：{a['n_no_pertest_data']} 个 —— "
            + (
                ", ".join(f"`{x}`" for x in a["no_pertest_data_task_ids"])
                if a["no_pertest_data_task_ids"]
                else "（无）"
            )
        )
    lines += ["", "## 6. 手工核验证据（原始输出 ↔ 解析结果并排）", ""]
    lines += report["handcheck_md"]
    lines += [
        "## 7. 局限与未测量项（诚实清单）",
        "",
    ]
    lines += [f"- {x}" for x in report["caveats"]]
    lines += [
        "",
        "## 8. 机器可读字段",
        "",
        "`TESTLEVEL_DETECTION.json`：`meta`（来源/sha256/口径/墙钟）、`aggregates.per_source`、`aggregates.pooled`、",
        "`tasks`（逐套件逐测试分类 + 双路解析计数 + stdout 哈希）、`testlevel_stats`、`handcheck`（含原始 -v 输出）。",
        "",
    ]
    return "\n".join(lines) + "\n"


def pooled_proxy(pooled: dict[str, Any]) -> dict[str, Any]:
    """把 pooled 聚合适配成与 per_source 同形的行（缺失字段用 unmeasured 占位）。"""
    out = dict(pooled)
    out.setdefault("label", "pooled_all_sources")
    out.setdefault("suite_class_counts", {})
    out.setdefault("n_only_buggy", None)
    out.setdefault("n_only_fixed", None)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--out", default=str(DEFAULT_OUT), help="输出目录（README.md / TESTLEVEL_DETECTION.json / SHA256SUMS.txt）"
    )
    ap.add_argument("--cap-seconds", type=int, default=CAP_SECONDS, help="单次 pytest 运行墙钟上限（秒）")
    ap.add_argument("--sources", default=None, help="只跑指定来源（逗号分隔：quixbugs50_batch5 / A / B / C / D）")
    ap.add_argument("--jobs", type=int, default=1, help="并发来源数（默认 1=串行确定性口径；>1 仅影响墙钟）")
    ap.add_argument("--limit", type=int, default=0, help="调试用：每源最多跑 N 个任务（默认 0=全量；正式跑批必须为 0）")
    ap.add_argument(
        "--independent-check",
        action="store_true",
        help="对手工核验任务做独立复跑（不用本脚本解析器，直接读 pytest 自身汇总行）并写入工件",
    )
    ap.add_argument(
        "--reuse-json",
        default=None,
        help="只重算分析/渲染（不跑 pytest）：复用既有 TESTLEVEL_DETECTION.json 的 measured 字段",
    )
    args = ap.parse_args(argv)

    if QUIXBUGS_ROOT.is_dir():
        os.environ.setdefault("AITESTER_QUIXBUGS_DATA", str(QUIXBUGS_ROOT))
    support_ready, support_reason = _packaged_support_ready()

    only = [s for s in (args.sources or "").split(",") if s.strip()] or None
    sources = discover_sources(only)
    if not sources:
        print("[tl] ✗ 未发现任何来源工件", file=sys.stderr)
        return 1
    gold, gold_info = load_gold_tasks()
    if not gold:
        print("[tl] ✗ QuixBugs gold 任务为空（检查 AITESTER_QUIXBUGS_DATA）", file=sys.stderr)
        return 1
    import pytest as _pytest

    t0 = time.time()
    runs: list[dict[str, Any]] = []
    if args.reuse_json:
        # 只重算分析（不跑 pytest）：从既有工件重建 runs（供新增分析/渲染口径复算，
        # 全部数字仍源自该工件内记录的 measured 字段；pytest 运行数不重算）
        reused = load_reused_report(Path(args.reuse_json), sources, gold_info)
        runs = reused["runs"]
        wall_total = reused["wall_clock_total_s"]
        sweep_cmdline = reused["prev_meta"]["cmdline"] or _cmdline()
        print(f"[tl] --reuse-json：复用 {args.reuse_json}（{len(runs)} 个来源，不跑 pytest）", flush=True)
    elif args.jobs > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            runs = list(ex.map(lambda s: run_source(s, gold, cap_seconds=args.cap_seconds, limit=args.limit), sources))
    else:
        for s in sources:
            print(f"[tl] === 来源 {s['label']}（{s['path'].name}）===", flush=True)
            runs.append(run_source(s, gold, cap_seconds=args.cap_seconds, limit=args.limit))
    if not args.reuse_json:
        wall_total = round(time.time() - t0, 1)
        sweep_cmdline = _cmdline()

    per_source = [aggregate_source(r) for r in runs]
    pooled = aggregate_pooled(runs, per_source)

    # Step 3：任务级（复用既有实现）+ 测试级 + 任务聚类
    arm_runs = {r["source"]["arm_letter"]: r for r in runs if r["source"]["arm_letter"]}
    task_level: dict[str, Any] = {}
    if {"A", "B"} <= set(arm_runs):
        analysis = build_analysis(
            Path(arm_runs["A"]["source"]["path"]),
            Path(arm_runs["B"]["source"]["path"]),
            Path(arm_runs["C"]["source"]["path"]) if "C" in arm_runs else None,
            Path(arm_runs["D"]["source"]["path"]) if "D" in arm_runs else None,
        )
        for key in ("primary", "repeat", "merged"):
            if key in analysis:
                row = dict(analysis[key])
                row["pair"] = {
                    "primary": "task-level primary（A specir vs B NL）",
                    "repeat": "task-level repeat（C specir vs D NL）",
                    "merged": "task-level merged（A∪C vs B∪D）",
                }[key]
                row["verdict"] = (
                    analysis["verdict"]
                    if key == "primary"
                    else (analysis.get("merged_verdict") if key == "merged" else verdict(row))
                )
                task_level[key] = row

    test_level: list[dict[str, Any]] = []
    task_clustered: list[dict[str, Any]] = []
    if {"A", "B"} <= set(arm_runs):
        test_level.append(testlevel_pair(arm_runs["A"], arm_runs["B"], "A_specir", "B_nl"))
        task_clustered.append(task_clustered_pair(arm_runs["A"], arm_runs["B"], "A_specir", "B_nl"))
    if {"C", "D"} <= set(arm_runs):
        test_level.append(testlevel_pair(arm_runs["C"], arm_runs["D"], "C_specir_repeat", "D_nl_repeat"))
        task_clustered.append(task_clustered_pair(arm_runs["C"], arm_runs["D"], "C_specir_repeat", "D_nl_repeat"))
    if len(test_level) == 2:
        merged = {
            "pair": "test-level merged（A∪C vs B∪D，分层合并）",
            "n_tasks_paired": test_level[0]["n_tasks_paired"] + test_level[1]["n_tasks_paired"],
            "n_test_nodeids_shared": test_level[0]["n_test_nodeids_shared"] + test_level[1]["n_test_nodeids_shared"],
            "n_nodeids_x_only": test_level[0]["n_nodeids_x_only"] + test_level[1]["n_nodeids_x_only"],
            "n_nodeids_y_only": test_level[0]["n_nodeids_y_only"] + test_level[1]["n_nodeids_y_only"],
            "n_shared_dropped_other": test_level[0]["n_shared_dropped_other"] + test_level[1]["n_shared_dropped_other"],
            "n_pairs_testlevel": test_level[0]["n_pairs_testlevel"] + test_level[1]["n_pairs_testlevel"],
            "b_pos_x_only_f2p": test_level[0]["b_pos_x_only_f2p"] + test_level[1]["b_pos_x_only_f2p"],
            "b_neg_y_only_f2p": test_level[0]["b_neg_y_only_f2p"] + test_level[1]["b_neg_y_only_f2p"],
            "both_f2p": test_level[0]["both_f2p"] + test_level[1]["both_f2p"],
            "neither_f2p": test_level[0]["neither_f2p"] + test_level[1]["neither_f2p"],
            "per_task": test_level[0]["per_task"] + test_level[1]["per_task"],
        }
        merged["ratio"] = f"{merged['b_pos_x_only_f2p']}:{merged['b_neg_y_only_f2p']}"
        npairs = merged["n_pairs_testlevel"]
        merged["delta_pp"] = (
            round((merged["b_pos_x_only_f2p"] - merged["b_neg_y_only_f2p"]) / npairs * 100, 2) if npairs else None
        )
        psi = (merged["b_pos_x_only_f2p"] + merged["b_neg_y_only_f2p"]) / npairs if npairs else 0.0
        merged["psi_discordance"] = round(psi, 4)
        merged["p_mcnemar_exact"] = round(mcnemar_exact_p(merged["b_pos_x_only_f2p"], merged["b_neg_y_only_f2p"]), 4)
        merged["p_chi2_cc"] = round(mcnemar_chi2_cc(merged["b_pos_x_only_f2p"], merged["b_neg_y_only_f2p"]), 4)
        merged["bf10_expand"] = bayes_factor_10(merged["b_pos_x_only_f2p"], merged["b_neg_y_only_f2p"])
        merged["bf10_optimization"] = bayes_factor_discordant(merged["b_pos_x_only_f2p"], merged["b_neg_y_only_f2p"])[
            "bf10_jeffreys"
        ]
        merged["bf_verdict"] = bayes_factor_discordant(merged["b_pos_x_only_f2p"], merged["b_neg_y_only_f2p"])[
            "verdict"
        ]
        merged["mde_two_proportion_pp"] = mde_two_proportion(npairs)
        merged["mde_paired_pp"] = (
            round(mde_paired_pp(npairs, psi), 2) if mde_paired_pp(npairs, psi) is not None else None
        )
        merged["verdict_rule"] = verdict({"p_value": merged["p_mcnemar_exact"], "delta_pp": merged["delta_pp"] or 0.0})
        test_level.append(merged)
        # 任务聚类合并 = 两次复跑的配对单位相加（任务被复跑两次，故 n=2×35）
        tc0, tc1 = task_clustered[0], task_clustered[1]
        merged_tc = {
            "pair": "task-clustered merged（A∪C vs B∪D）",
            "n_tasks": tc0["n_tasks"] + tc1["n_tasks"],
            "sum_f2p_x": tc0["sum_f2p_x"] + tc1["sum_f2p_x"],
            "sum_f2p_y": tc0["sum_f2p_y"] + tc1["sum_f2p_y"],
            "n_tasks_more_f2p_x": tc0["n_tasks_more_f2p_x"] + tc1["n_tasks_more_f2p_x"],
            "n_tasks_more_f2p_y": tc0["n_tasks_more_f2p_y"] + tc1["n_tasks_more_f2p_y"],
            "n_tasks_tied": tc0["n_tasks_tied"] + tc1["n_tasks_tied"],
            "mean_delta_f2p_count": round(
                (tc0["mean_delta_f2p_count"] * tc0["n_tasks"] + tc1["mean_delta_f2p_count"] * tc1["n_tasks"])
                / (tc0["n_tasks"] + tc1["n_tasks"]),
                4,
            ),
            "mean_delta_f2p_fraction": round((tc0["mean_delta_f2p_fraction"] + tc1["mean_delta_f2p_fraction"]) / 2, 4),
            "sign_test_mcnemar_exact_p": round(
                mcnemar_exact_p(
                    tc0["n_tasks_more_f2p_x"] + tc1["n_tasks_more_f2p_x"],
                    tc0["n_tasks_more_f2p_y"] + tc1["n_tasks_more_f2p_y"],
                ),
                4,
            ),
            "wilcoxon": {
                "note": "复跑两层各自的 Wilcoxon 结果见上表；合并层不重复做（同一任务两次测量非独立，合并会低估方差）",
                "n_nonzero": None,
                "n_zero_diff": None,
                "w_plus": None,
                "p_exact": None,
                "p_normal_approx": None,
                "p_exact_primary": tc0["wilcoxon"]["p_exact"],
                "p_exact_repeat": tc1["wilcoxon"]["p_exact"],
            },
        }
        task_clustered.append(merged_tc)

    primary_task = task_level.get("primary", {})
    primary_test = next((r for r in test_level if r["pair"].startswith("A_specir")), {})
    tc_primary = task_clustered[0] if task_clustered else {}
    mde = mde_table(
        int(primary_task.get("n_pairs") or 0),
        int(primary_test.get("n_pairs_testlevel") or 0),
        float(primary_task.get("b_pos_specir_only", 0) + primary_task.get("b_neg_nl_only", 0))
        / max(int(primary_task.get("n_pairs") or 1), 1),
        float(primary_test.get("psi_discordance") or 0.0),
    )
    mde["task_clustered_n_pairs"] = tc_primary.get("n_tasks")
    mde["task_clustered_psi"] = None
    mde["task_clustered_mde_two_proportion_pp"] = mde_two_proportion(int(tc_primary.get("n_tasks") or 0))
    mde["task_clustered_psi"] = "unmeasured（任务级计数非二值，ψ 无对应定义）"

    conclusions = _build_conclusions(task_level, test_level, task_clustered, pooled, mde, per_source)
    hang = hang_sensitivity(runs)
    conclusions.append(
        "（computed·替代口径敏感性）把「buggy 侧挂死 ∧ fixed 侧全绿」也记为检出后，"
        + "；".join(
            f"{c['pair']} → {c['ratio']}（n={c['n_pairs']}，δ={c['delta_pp']}pp，p={c['p_value']}，`{c['verdict']}`）"
            for c in hang["contrasts"]
        )
        + f"；此类任务逐源：{ {k: v for k, v in hang['flip_task_ids_per_source'].items()} }。"
    )
    tasks_public = []
    for r in runs:
        for t in r["tasks"]:
            row = {k: v for k, v in t.items() if k not in ("buggy_stdout", "fixed_stdout")}
            tasks_public.append(row)

    handcheck = select_handcheck([t for r in runs for t in r["tasks"]])
    raw_lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for r in runs:
        for hc_raw in (r.get("handcheck_raw") or {}).values():
            raw_lookup[(str(hc_raw.get("set")), str(hc_raw.get("task_id")))] = hc_raw
    for hc in handcheck:
        t = hc["task"]
        if not t.get("buggy_stdout") and not t.get("fixed_stdout"):
            src_raw = raw_lookup.get((t["set"], t["task_id"]), {})
            t["buggy_stdout"] = src_raw.get("buggy_stdout", "")
            t["fixed_stdout"] = src_raw.get("fixed_stdout", "")
    indep = independent_check(handcheck, sources, gold, cap_seconds=args.cap_seconds) if args.independent_check else {}
    handcheck_md: list[str] = []
    for hc in handcheck:
        handcheck_md += render_handcheck(hc, max_lines=60)
    if indep:
        handcheck_md += [
            "### 6.1 独立复核（重跑 + 读 pytest 自身汇总行，不走本脚本解析器）",
            "",
            "| 任务 | buggy rc | buggy pytest 汇总行 | 工件 buggy(pass/fail) | fixed rc | fixed pytest 汇总行 | 工件 fixed(pass/fail) | 判定 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for key, e in indep.items():
            b, f = e["sides"]["buggy"], e["sides"]["fixed"]
            handcheck_md.append(
                f"| `{key}` | {_fmt(b['rc'])} | `{b['pytest_summary_line']}` | "
                f"{_fmt(b['artifact_pass'])}/{_fmt(b['artifact_fail'])} | {_fmt(f['rc'])} | "
                f"`{f['pytest_summary_line']}` | {_fmt(f['artifact_pass'])}/{_fmt(f['artifact_fail'])} | "
                f"**{e['verdict']}** |"
            )
        handcheck_md += [
            "",
            "> `match` = pytest 自身汇总行计数与工件逐测试表推出的该侧 (pass, fail+error) 逐位相等；",
            "> `reproduced_timeout` = 两侧再次在 30s 上限超时（超时套件在工件中一律记 `other`，不产生 f2p）。",
            "",
        ]

    caveats = _build_caveats(per_source, pooled, runs, support_ready, support_reason, args)
    meta = {
        "script": str(Path(__file__).resolve()),
        "argv": sys.argv[1:],
        "cmdline": _cmdline(),
        "sweep_cmdline": sweep_cmdline,
        "reuse_json": args.reuse_json or "",
        "generated_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "cap_seconds": args.cap_seconds,
        "jobs": args.jobs,
        "python": sys.version.split()[0],
        "pytest_version": getattr(_pytest, "__version__", "unknown"),
        "gold_root": str(QUIXBUGS_ROOT),
        "gold_info": gold_info,
        "quixbugs_support_ready": support_ready,
        "quixbugs_support_reason": support_reason,
        "wall_clock_total_s": wall_total,
        "wall_clock_per_source_s": {r["source"]["label"]: r["wall_s"] for r in runs},
        "n_pytest_runs": sum(2 * a["n_suites_run"] for a in per_source),
        "independent_check_enabled": bool(args.independent_check),
        "n_independent_check_runs": len(indep) * 2,
        "sources": [{**{k: v for k, v in s.items() if k != "path"}, "path": str(s["path"])} for s in sources],
    }
    report: dict[str, Any] = {
        "meta": meta,
        "aggregates": {"per_source": per_source, "pooled": pooled},
        "tasks": tasks_public,
        "testlevel_stats": {
            "task_level": task_level,
            "test_level": test_level,
            "task_clustered": task_clustered,
            "mde": mde,
            "hang_sensitivity": hang,
            "conclusions": conclusions,
        },
        "handcheck": [
            {
                "rule": hc["rule"],
                "set": hc["task"]["set"],
                "task_id": hc["task"]["task_id"],
                "suite_class": hc["task"]["suite_class"],
                "archived_detection_rate": hc["task"]["archived_detection_rate"],
                "task_level_reproduced": hc["task"]["task_level_reproduced"],
                "counts": hc["task"]["counts"],
                "buggy": hc["task"]["buggy"],
                "fixed": hc["task"]["fixed"],
                "tests": hc["task"]["tests"],
                "buggy_stdout": hc["task"]["buggy_stdout"],
                "fixed_stdout": hc["task"]["fixed_stdout"],
            }
            for hc in handcheck
        ],
        "handcheck_md": handcheck_md,
        "handcheck_independent_check": indep,
        "caveats": caveats,
        "metric_labels": {
            "measured": "本次 pytest 运行直接观测",
            "computed": "由 measured 计数精确推导",
            "estimated": "模型近似（MDE/功效/先验模型）",
            "unmeasured": "本次无法测量（不填 0）",
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "TESTLEVEL_DETECTION.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    readme_path = out_dir / "README.md"
    readme_path.write_text(render_readme(report, sources, meta["sweep_cmdline"]), encoding="utf-8")
    sums = subprocess.run(
        ["shasum", "-a", "256", readme_path.name, json_path.name],
        cwd=str(out_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    (out_dir / "SHA256SUMS.txt").write_text(sums.stdout, encoding="utf-8")

    print(f"\n[tl] 完成：{json_path}")
    print(
        f"[tl] 墙钟 {wall_total}s，pytest 运行 {meta['n_pytest_runs']} 次，超时侧 "
        f"{pooled['timeouts']['n_sides_timed_out']}，无逐测试数据任务 {pooled['n_no_pertest_data']}"
    )
    print(
        f"[tl] headline：det=1.0 套件 {pooled['detection_conversion']['n_archived_detection_1']} 个，其中单测试扛下 "
        f"{pooled['detection_conversion']['n_single_test_carried']} 个"
    )
    for c in conclusions:
        print(f"[tl] 结论：{c}")
    return 0


def _cmdline() -> str:
    return (
        "AITESTER_QUIXBUGS_DATA=~/.cache/aitester/quixbugs .venv/bin/python experiments/emse_testlevel_detection.py "
        + " ".join(sys.argv[1:])
    )


def _build_conclusions(
    task_level: dict[str, Any],
    test_level: list[dict[str, Any]],
    task_clustered: list[dict[str, Any]],
    pooled: dict[str, Any],
    mde: dict[str, Any],
    per_source: list[dict[str, Any]],
) -> list[str]:
    out: list[str] = []
    dc = pooled["detection_conversion"]
    n1 = dc["n_archived_detection_1"]
    if n1:
        out.append(
            f"（measured）pooled {n1} 个任务级检出中 {dc['n_single_test_carried']} 个"
            f"（{round(dc['n_single_test_carried'] / n1 * 100, 1)}%）由**单个**测试函数扛下；"
            f"det1 套件平均 f2p = {dc['f2p_mean_among_det1']}（占其可分类测试 "
            f"{round(dc['f2p_total_among_det1'] / dc['classifiable_total_among_det1'] * 100, 2) if dc['classifiable_total_among_det1'] else 'unmeasured'}%）。"
        )
    out.append(
        f"（measured）pooled 盲测质量 p2p={pooled['blind_mass']['p2p']} vs f2p={pooled['blind_mass']['f2p']}："
        f"{round(pooled['blind_mass']['p2p_over_p2p_plus_f2p'] * 100, 2) if pooled['blind_mass']['p2p_over_p2p_plus_f2p'] is not None else 'unmeasured'}% "
        f"的（p2p+f2p）测试不携带任何缺陷检出信号；f2f（在正确代码上失败）率 "
        f"{pooled['invalid_mass']['f2f_over_classifiable']}。"
    )
    tp = task_level.get("primary", {})
    if tp:
        out.append(
            f"（computed）任务级 primary 复现：{tp['ratio']}，n={tp['n_pairs']}，δ={tp['delta_pp']}pp，"
            f"p={tp['p_value']}，BF10={tp['bf10']} → 判定 `{tp.get('verdict')}`（与既有结论一致）。"
        )
    out.extend(
        f"（computed）测试级 {row['pair']}：共享 node id {row['n_test_nodeids_shared']}（X 独有 {row['n_nodeids_x_only']}、"
        f"Y 独有 {row['n_nodeids_y_only']}），严格配对数 n={row['n_pairs_testlevel']}，"
        f"{row['ratio']}，δ={row['delta_pp']}pp，p={row['p_mcnemar_exact']}，BF10={row['bf10_expand']} → `{row['verdict_rule']}`。"
        for row in test_level
    )
    for row in task_clustered:
        w = row["wilcoxon"]
        out.append(
            f"（computed）任务聚类 {row['pair']}：n={row['n_tasks']} 任务，X/Y 更多 f2p 的任务数 "
            f"{row['n_tasks_more_f2p_x']}/{row['n_tasks_more_f2p_y']}（并列 {row['n_tasks_tied']}），"
            f"符号检验 p={row['sign_test_mcnemar_exact_p']}，Wilcoxon 精确 p={w.get('p_exact')}，"
            f"平均 Δf2p(计数)={row['mean_delta_f2p_count']}。"
        )
    out.append(
        f"（estimated）MDE 对照：任务级 n={mde['task_level']['n_pairs']} → {mde['task_level']['mde_two_proportion_pp']}pp"
        f"（配对近似 {mde['task_level']['mde_paired_pp']}pp）；测试级严格配对 n={mde['test_level']['n_pairs']} → "
        f"{mde['test_level']['mde_two_proportion_pp']}pp；任务聚类 n={mde['task_clustered_n_pairs']} → "
        f"{mde['task_clustered_mde_two_proportion_pp']}pp。"
    )
    out.append(
        "（口径提示）测试级严格配对把「两臂各自生成的测试函数」按同名 node id 对齐，共享率极低，"
        "其 n 远小于测试总数；因此**任务聚类结论优先于测试级严格配对结论**，"
        "测试级配对只作为「同名测试函数在同任务上的行为差异」这一窄口径的补充证据。"
    )
    return out


def _build_caveats(
    per_source: list[dict[str, Any]],
    pooled: dict[str, Any],
    runs: list[dict[str, Any]],
    support_ready: bool,
    support_reason: str,
    args: argparse.Namespace,
) -> list[str]:
    cav: list[str] = []
    to_b = pooled["timeouts"]["buggy"]
    to_f = pooled["timeouts"]["fixed"]
    cav.append(
        f"30s 上限口径（与 emse_test_sanity_audit.py 同）：任一侧超时 → 该套件记 `other`/`timeout`，"
        f"**不**计入 f2p（超时套件清单见 JSON `aggregates`）。pooled buggy 侧超时 {len(to_b)} 个任务"
        f"（{', '.join(to_b) if to_b else '无'}）；fixed 侧超时 {len(to_f)} 个（{', '.join(to_f) if to_f else '无'}）。"
        "buggy 侧挂死是「套件在缺陷代码上不终止」——是否算检出取决于口径选择，本件保守记 other 并单列。"
    )
    cav.append(
        "归档 `detection_rate` 的判分链路用 120s 上限（`_run_pytest_in_tmp` 默认），本件用 30s；"
        "因此本件复算的 `task_level_reproduced` 与归档值在**慢任务**上可能不同，差异逐条列于 README §5，不静默。"
    )
    cav.append(
        "`test_level` 三种口径互不替代：(a) 测试级严格配对（按 node id，n 小）；(b) 任务聚类（n=任务数，"
        "防伪重复）；(c) 各臂边际 f2p 率（不配对）。三者的 p/δ 不可混引。"
    )
    cav.append(
        "逐测试分类的「失败」含 call 相位断言失败与 setup/teardown 异常；相位细分见 §3.5，"
        "§3.5 的「call 相位失败」含断言失败**与**测试体内未捕获异常（被测缺陷代码直接抛出的 "
        "IndexError/TypeError 等）——两者都是真实的缺陷触发路径；setup/teardown 异常单列。"
        "若审稿人只想看断言失败，需按失败消息二次过滤（本件 JSON 只存相位级，不存失败消息 → 该细分 unmeasured）。"
    )
    cav.append(
        "两路解析交叉校验：插件 JSONL 为主，`-v` 文本为辅；两侧不一致条数 "
        f"{sum(a['parser_crosscheck']['n_mismatches'] for a in per_source)}（0 = 完全一致）。"
    )
    cav.append(
        "9 个 `quixbugs__*_test` 伪程序（QuixBugs `python_programs/*_test.py`）无官方 gold 材料，"
        "逐源排除（每源 9 个），不计入任何分母。"
    )
    cav.append(
        f"QuixBugs 辅助模块（node.py / load_testdata.py / json_testcases）就绪={support_ready}"
        + (f"（原因：{support_reason}）" if not support_ready else "")
        + "；依赖辅助模块的套件数见 JSON `tasks[].needs_quixbugs_support`。"
    )
    if args.jobs > 1:
        cav.append(
            f"--jobs={args.jobs}：并发只影响墙钟，每个套件仍为独立子进程 + 独立 30s 墙钟上限；"
            "但并发下的墙钟上限可能使「边缘慢」套件超时（本批超时均为死循环，已由 fixed/buggy 双侧表现佐证）。"
        )
    cav.append(
        "未测量项（`unmeasured`）：无 gold 材料任务的测试级分类、超时套件内部的逐测试结果、"
        "以及各臂「未归档套件」（归档工件只含每任务最终套件——迭代中间产物不在口径内）。"
    )
    cav.append(
        "本件只覆盖 QuixBugs（唯一同时具备 defect 版 / gold 修复版 / 官方测试的基准）；"
        "ULT 生成套件无 buggy 侧（replace 口径）故**不可**做双侧测试级分类——明确记为 unmeasured，不猜。"
    )
    return cav


if __name__ == "__main__":
    raise SystemExit(main())
