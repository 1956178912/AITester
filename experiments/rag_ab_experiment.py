"""P0 3.1：RAG A/B 对比实验（--enable-rag vs --no-rag）。

目的：
    此前 RAG 功能已实现（src/observability/rag.py + nodes.py 检索注入）
    但默认关闭且未纳入主实验，无 A/B 数据支撑"RAG 是否有效"的论文主张。
    本脚本自动化执行 RAG 开关 A/B 对比，产出结构化数据：

    1. 按任务统计：
       - 成功率（RAG ON vs OFF）
       - 平均 token 消耗（input/output/total）
       - 平均迭代轮次
       - 平均耗时
    2. 按错误类型分组（RAG ON 时 RAG_RETRIEVAL_EMPTY 的比例；
       RAG OFF 时 LLM_FORMAT_ERROR / UNKNOWN 的比例）：
       - 哪类错误在 RAG ON 下显著减少（RAG 收益）
       - 哪类错误在 RAG ON 下无变化（RAG 无效场景）
    3. 配对 t-test + Mann-Whitney U + Cohen's d（与 0.7 统计报告同口径）

使用方式：
    # 在合成数据集 20 个任务上跑 RAG ON vs RAG OFF
    python experiments/rag_ab_experiment.py \
        --dataset synthetic --task-count 20 --task-limit 20 \
        --seed 42 --output-dir experiments/results/rag_ab_$(date +%Y%m%d)

    # 在 SWE-bench lite 上跑（需 enrichment 文件）
    export SWE_BENCH_ENRICHMENT=~/Workspace/AITester/data/swe_bench_lite_enriched.jsonl
    python experiments/rag_ab_experiment.py \
        --dataset swe_bench --subset lite --task-count 20 \
        --seed 42 --output-dir experiments/results/rag_ab_swe

    # 仅分析已有结果（跳过实验运行，直接读两个结果 JSON 做统计）
    python experiments/rag_ab_experiment.py \
        --analyze-only \
        --results-rag-on experiments/results/rag_ab_xxx/rag_on.json \
        --results-rag-off experiments/results/rag_ab_xxx/rag_off.json
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import click

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

# ─── 统计工具（与 0.7 报告同口径）──────────────────────────────────────────


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _var(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _mean(vals)
    return sum((x - m) ** 2 for x in vals) / (len(vals) - 1)


def _std(vals: list[float]) -> float:
    return _var(vals) ** 0.5


def _welch_ttest(a: list[float], b: list[float]) -> tuple[float, float]:
    """Welch's t-test（不假设方差齐性），返回 (t_stat, p_value)。"""
    if len(a) < 2 or len(b) < 2:
        return 0.0, 1.0
    ta, tb = _mean(a), _mean(b)
    va, vb = _var(a), _var(b)
    na, nb = len(a), len(b)
    se = ((va / na) + (vb / nb)) ** 0.5
    if se == 0:
        return 0.0, 1.0
    t = (ta - tb) / se
    df = ((va / na + vb / nb) ** 2) / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    # p 值近似（df >= 30 时 Z 近似）
    from math import erf, sqrt

    p = 1.0 - erf(abs(t) / sqrt(2.0))
    if df < 30:
        p *= (1.0 + 1.0 / (4.0 * df)) ** -0.5
    return t, min(p, 1.0)


def _mann_whitney_u(a: list[float], b: list[float]) -> tuple[float, float]:
    """Mann-Whitney U 检验（秩和检验），返回 (U_stat, p_value)。"""
    if len(a) < 1 or len(b) < 1:
        return 0.0, 1.0
    combined = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    n1, n2 = len(a), len(b)
    ranks: list[float] = [0.0] * (n1 + n2)
    i = 0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1
    r1 = sum(ranks[k] for k in range(n1 + n2) if combined[k][1] == 0)
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    u = min(u1, u2)
    mu = n1 * n2 / 2.0
    sigma = (n1 * n2 * (n1 + n2 + 1) / 12.0) ** 0.5
    if sigma == 0:
        return u, 1.0
    z = (u - mu) / sigma
    from math import erf, sqrt

    p = 2.0 * (1.0 - 0.5 * (1.0 + erf(z / sqrt(2.0))))
    return u, min(max(p, 0.0), 1.0)


def _cohens_d(a: list[float], b: list[float]) -> float:
    """Cohen's d（pooled SD，独立样本效应量）。"""
    if not a or not b:
        return 0.0
    na, nb = len(a), len(b)
    pooled = (((na - 1) * _var(a) + (nb - 1) * _var(b)) / (na + nb - 2)) ** 0.5
    if pooled == 0:
        return 0.0
    return (_mean(a) - _mean(b)) / pooled


# ─── 结果解析 ───────────────────────────────────────────────────────────────


def _parse_task_record(record: dict) -> dict[str, Any]:
    """从 run_benchmark 的 details[] 单条记录提取结构化指标。

    2026-09-26 全面审查（P0 正确性修复）：此前读取的字段名（tokens_total /
    total_tests / passed_count / duration_s / failure_category）与
    run_benchmark._build_task_result 实际产出的键（token_usage /
    elapsed_seconds / iterations / passed / error_category）零交集——全部
    .get 落到默认值（token≡0、duration≡0、failure_category≡"none"），
    RAG A/B 报告的 token 收益 / 耗时 / 错误分布三大结论恒为假数据。
    现按真实键读取：
    - tokens_total ← record["token_usage"]["total_tokens"]（嵌套 dict）；
    - duration_s   ← record["elapsed_seconds"]；
    - failure_category ← record["error_category"]（run_benchmark 用
      refine_final_error_category 产出；通过任务为 "none"）；
    - total_tests / passed_count：run_benchmark 结果不含该二字段（只含
      passed/coverage），置 0 保持返回键集合同构（下游未消费这两个键）。
    """
    task_id = record.get("task_id", "")
    passed = record.get("passed", False)
    total_tests = record.get("total_tests", 0)
    passed_count = record.get("passed_count", 0)
    # token_usage: {"input_tokens":..., "output_tokens":..., "total_tokens":..., "llm_calls":...}
    token_usage = record.get("token_usage") or {}
    tokens_total = token_usage.get("total_tokens", 0)
    iterations = record.get("iterations", 0)
    duration_s = record.get("elapsed_seconds", 0.0)
    # 错误类型：run_benchmark 真实键为 error_category；通过任务为 "none"
    failure_category = record.get("error_category") or ("none" if passed else "unknown")
    return {
        "task_id": task_id,
        "passed": bool(passed),
        "total_tests": total_tests,
        "passed_count": passed_count,
        "tokens_total": tokens_total,
        "iterations": iterations,
        "duration_s": duration_s,
        "failure_category": failure_category,
    }


def _load_results(result_path: str) -> list[dict[str, Any]]:
    """读取 run_benchmark 产出的结果 JSON，提取 per-task 指标列表。

    run_benchmark 输出结构：
        {"results": {<baseline>: {"details": [...]}, ...}, ...}
    也兼容扁平结构（{"details": [...]} 或 {"results": [...]}）便于
    --analyze-only 模式直接指向 details 数组所在对象。
    """
    p = Path(result_path)
    if not p.exists():
        logger.warning("结果文件不存在: %s", p)
        return []
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    # 结构 1：run_benchmark 标准输出 {"results": {baseline: {"details": [...]}}}
    results_map = data.get("results")
    if isinstance(results_map, dict):
        # 取第一个基线的 details（A/B 实验通常只跑一个基线）
        for bl_data in results_map.values():
            if isinstance(bl_data, dict) and isinstance(bl_data.get("details"), list):
                return [_parse_task_record(d) for d in bl_data["details"] if isinstance(d, dict)]
    # 结构 2：扁平 details / results 数组
    details = data.get("details", data.get("results"))
    if isinstance(details, list):
        return [_parse_task_record(d) for d in details if isinstance(d, dict)]
    logger.warning("结果文件结构无法识别: %s", p)
    return []


# ─── 对比分析 ───────────────────────────────────────────────────────────────


def _group_by_failure(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """按 failure_category 分组。"""
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        cat = r.get("failure_category", "none")
        groups.setdefault(cat, []).append(r)
    return groups


def _failure_rate(records: list[dict[str, Any]]) -> float:
    """未通过任务占比。"""
    if not records:
        return 0.0
    failed = sum(1 for r in records if not r.get("passed", False))
    return failed / len(records)


def compare_ab(
    rag_on_records: list[dict[str, Any]],
    rag_off_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """RAG A/B 对比分析（token/成功率/迭代/错误类型分布 + 统计检验）。"""
    # 配对（按 task_id 匹配）
    on_by_id = {r["task_id"]: r for r in rag_on_records}
    off_by_id = {r["task_id"]: r for r in rag_off_records}
    paired_ids = [tid for tid in on_by_id if tid in off_by_id]

    # 各指标列表
    on_tokens = [on_by_id[t]["tokens_total"] for t in paired_ids]
    off_tokens = [off_by_id[t]["tokens_total"] for t in paired_ids]
    on_iters = [on_by_id[t]["iterations"] for t in paired_ids]
    off_iters = [off_by_id[t]["iterations"] for t in paired_ids]
    on_dur = [on_by_id[t]["duration_s"] for t in paired_ids]
    off_dur = [off_by_id[t]["duration_s"] for t in paired_ids]

    # 成功率
    on_pass = sum(1 for t in paired_ids if on_by_id[t]["passed"])
    off_pass = sum(1 for t in paired_ids if off_by_id[t]["passed"])
    n = len(paired_ids)

    # 错误类型分布
    on_groups = _group_by_failure(rag_on_records)
    off_groups = _group_by_failure(rag_off_records)

    # RAG 收益分析（哪类错误在 RAG ON 下显著减少）
    error_category_shift: dict[str, dict[str, float]] = {}
    for cat in set(list(on_groups.keys()) + list(off_groups.keys())):
        on_n = len(on_groups.get(cat, []))
        off_n = len(off_groups.get(cat, []))
        on_rate = on_n / max(len(rag_on_records), 1)
        off_rate = off_n / max(len(rag_off_records), 1)
        error_category_shift[cat] = {
            "rag_on_count": on_n,
            "rag_off_count": off_n,
            "rag_on_rate": round(on_rate, 4),
            "rag_off_rate": round(off_rate, 4),
            "delta": round(off_rate - on_rate, 4),  # 正值 = RAG 减少该错误类型
        }

    # RAG 检索有效性（仅 RAG ON 组）
    rag_retrieval_empty = len(on_groups.get("rag_retrieval_empty", []))
    rag_effective_rate = (n - rag_retrieval_empty) / max(n, 1) if n else 0.0

    # 统计检验（token / 迭代 / 耗时）
    t_tok, p_tok = _welch_ttest(on_tokens, off_tokens)
    u_tok, pu_tok = _mann_whitney_u(on_tokens, off_tokens)
    d_tok = _cohens_d(on_tokens, off_tokens)

    t_it, p_it = _welch_ttest(on_iters, off_iters)
    u_it, pu_it = _mann_whitney_u(on_iters, off_iters)
    d_it = _cohens_d(on_iters, off_iters)

    report: dict[str, Any] = {
        "paired_tasks": n,
        "rag_on": {
            "success_rate": round(on_pass / max(n, 1), 4),
            "avg_tokens": round(_mean(on_tokens), 1),
            "std_tokens": round(_std(on_tokens), 1),
            "avg_iterations": round(_mean(on_iters), 2),
            "avg_duration_s": round(_mean(on_dur), 1),
            "failure_distribution": {k: len(v) for k, v in on_groups.items()},
            "rag_retrieval_empty_count": rag_retrieval_empty,
            "rag_effective_rate": round(rag_effective_rate, 4),
        },
        "rag_off": {
            "success_rate": round(off_pass / max(n, 1), 4),
            "avg_tokens": round(_mean(off_tokens), 1),
            "std_tokens": round(_std(off_tokens), 1),
            "avg_iterations": round(_mean(off_iters), 2),
            "avg_duration_s": round(_mean(off_dur), 1),
            "failure_distribution": {k: len(v) for k, v in off_groups.items()},
        },
        "token_saving": {
            "delta_avg": round(_mean(off_tokens) - _mean(on_tokens), 1),
            "delta_pct": round(((_mean(off_tokens) - _mean(on_tokens)) / max(_mean(off_tokens), 1)) * 100, 2),
            "t_stat": round(t_tok, 4),
            "p_value_welch": round(p_tok, 6),
            "u_stat": round(u_tok, 2),
            "p_value_mann_whitney": round(pu_tok, 6),
            "cohens_d": round(d_tok, 4),
        },
        "iteration_saving": {
            "delta_avg": round(_mean(off_iters) - _mean(on_iters), 2),
            "t_stat": round(t_it, 4),
            "p_value_welch": round(p_it, 6),
            "u_stat": round(u_it, 2),
            "p_value_mann_whitney": round(pu_it, 6),
            "cohens_d": round(d_it, 4),
        },
        "error_category_shift": error_category_shift,
        "interpretation": {},
    }

    # 自动解读
    interp: dict[str, str] = {}
    if p_tok < 0.05:
        interp["token"] = (
            f"RAG ON 平均节省 {report['token_saving']['delta_avg']} tokens "
            f"({report['token_saving']['delta_pct']}%)，p={p_tok:.4f}（显著）"
        )
    else:
        interp["token"] = f"RAG ON token 消耗与 RAG OFF 无显著差异（p={p_tok:.4f}）"

    if p_it < 0.05:
        interp["iteration"] = f"RAG ON 平均减少 {report['iteration_saving']['delta_avg']} 轮迭代，p={p_it:.4f}（显著）"
    else:
        interp["iteration"] = f"RAG ON 迭代轮次与 RAG OFF 无显著差异（p={p_it:.4f}）"

    improved = [cat for cat, v in error_category_shift.items() if v["delta"] > 0.05]
    if improved:
        interp["error_reduction"] = f"RAG 显著减少的错误类型：{improved}"
    else:
        interp["error_reduction"] = "RAG 未显著减少任何错误类型"

    report["interpretation"] = interp
    return report


# ─── 实验执行（调用 run_benchmark 两次：RAG ON / RAG OFF）────────────────────


def _run_benchmark_once(
    dataset_name: str,
    subset: str | None,
    task_count: int,
    task_limit: int | None,
    seed: int,
    enable_rag: bool,
    output_dir: str,
    baseline: str,
    sub_run_dir: str | None = None,
) -> str:
    """调用 run_benchmark 一次（RAG ON 或 OFF），返回结果 JSON 路径。

    2026-09-26 全面审查（P1 正确性）：新增 sub_run_dir 参数——RAG ON / OFF
    两次运行各自写入独立子目录（<output_dir>/rag_on、<output_dir>/rag_off），
    再按 mtime 取该子目录内最新 benchmark_*.json。此前两次共用同一
    output_dir，若恰好在同一秒内先后写出（时间戳 %Y%m%d_%H%M%S 精度仅秒级），
    mtime 相同 → sorted [-1] 可能拿到另一组的结果，A/B 互相污染。
    sub_run_dir=None 时退回历史口径（直接在 output_dir 查找，兼容旧调用）。
    """
    env = os.environ.copy()
    # RAG 开关
    env["ENABLE_RAG"] = "true" if enable_rag else "false"
    # 确保 trace 层默认开启（P0 4.2）
    if not env.get("AITESTER_TRACE_DIR"):
        env["AITESTER_TRACE_DIR"] = str(Path(output_dir) / "traces")

    # 本次运行的结果目录（独立子目录避免 ON/OFF mtime 碰撞）
    run_dir = sub_run_dir or output_dir
    Path(run_dir).mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "experiments" / "run_benchmark.py"),
        "--dataset",
        dataset_name,
        "--baselines",
        baseline,
        "--task-count",
        str(task_count),
        "--seed",
        str(seed),
        "--output-dir",
        run_dir,
    ]
    if subset:
        cmd += ["--subset", subset]
    if task_limit:
        cmd += ["--task-limit", str(task_limit)]

    logger.info("运行 RAG %s benchmark: %s", "ON" if enable_rag else "OFF", " ".join(cmd))
    t0 = time.time()
    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=7200,
    )
    elapsed = time.time() - t0
    if proc.returncode != 0:
        logger.warning("benchmark 返回非零 (%d)，输出末尾:\n%s", proc.returncode, (proc.stdout or "")[-2000:])
    else:
        logger.info("benchmark 完成（%.1fs）", elapsed)
    # run_benchmark 写出带时间戳文件名 benchmark_<dataset>_<ts>.json；
    # 在结果目录中找最新的 benchmark_*.json（按 mtime 排序）。
    # 2026-09-26 全面审查：优先在 sub_run_dir（本次运行专属子目录）内查找，
    # 避免 ON/OFF 共用 output_dir 时 mtime 碰撞互相污染；sub_run_dir 无结果
    # 时回退 output_dir（兼容旧布局）。
    search_dir = Path(sub_run_dir) if sub_run_dir else Path(output_dir)
    candidates = sorted(
        (p for p in search_dir.glob("benchmark_*.json")),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates and sub_run_dir:
        candidates = sorted(
            (p for p in Path(output_dir).glob("benchmark_*.json")),
            key=lambda p: p.stat().st_mtime,
        )
    if candidates:
        return str(candidates[-1])
    logger.warning("未找到结果文件（benchmark_*.json in %s），返回占位路径", search_dir)
    return str(search_dir / "benchmark_missing.json")


@click.command()
@click.option("--dataset", "-d", default="synthetic", help="数据集名称（默认 synthetic）")
@click.option("--subset", "-s", default=None, help="数据子集（SWE-bench lite/full）")
@click.option("--task-count", "-c", default=20, type=int, help="合成数据集任务数量（默认 20）")
@click.option("--task-limit", "-n", default=None, type=int, help="限制运行任务数量")
@click.option("--seed", default=42, type=int, help="随机种子（默认 42）")
@click.option("--output-dir", "-o", default="experiments/results/rag_ab", help="结果输出目录")
@click.option("--baseline", "-b", default="aitester", help="基线方法（默认 aitester）")
@click.option(
    "--analyze-only",
    is_flag=True,
    help="仅分析已有结果（跳过实验运行，读两个结果 JSON 做统计）",
)
@click.option("--results-rag-on", default=None, help="--analyze-only 时 RAG ON 结果 JSON 路径")
@click.option("--results-rag-off", default=None, help="--analyze-only 时 RAG OFF 结果 JSON 路径")
def main(
    dataset: str,
    subset: str | None,
    task_count: int,
    task_limit: int | None,
    seed: int,
    output_dir: str,
    baseline: str,
    analyze_only: bool,
    results_rag_on: str | None,
    results_rag_off: str | None,
) -> None:
    """P0 3.1：RAG A/B 对比实验（--enable-rag vs --no-rag，记录 token/成功率/迭代，
    按错误类型分析 RAG 收益，输出 t-test/Mann-Whitney U/Cohen's d 统计检验）。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    os.makedirs(output_dir, exist_ok=True)

    if analyze_only:
        if not results_rag_on or not results_rag_off:
            click.echo("错误：--analyze-only 需同时指定 --results-rag-on 和 --results-rag-off", err=True)
            sys.exit(1)
        on_records = _load_results(results_rag_on)
        off_records = _load_results(results_rag_off)
    else:
        # 执行 RAG ON / RAG OFF 两次 benchmark
        # 2026-09-26 全面审查：各自写入独立子目录（rag_on / rag_off），
        # 避免共用 output_dir 时同一秒内写出导致 mtime 碰撞互相污染
        on_path = _run_benchmark_once(
            dataset,
            subset,
            task_count,
            task_limit,
            seed,
            True,
            output_dir,
            baseline,
            sub_run_dir=str(Path(output_dir) / "rag_on"),
        )
        off_path = _run_benchmark_once(
            dataset,
            subset,
            task_count,
            task_limit,
            seed,
            False,
            output_dir,
            baseline,
            sub_run_dir=str(Path(output_dir) / "rag_off"),
        )
        on_records = _load_results(on_path)
        off_records = _load_results(off_path)
        logger.info("RAG ON 结果: %d 条 | RAG OFF 结果: %d 条", len(on_records), len(off_records))

    if not on_records or not off_records:
        click.echo("错误：至少有一组 RAG 结果缺失，无法对比分析", err=True)
        sys.exit(1)

    report = compare_ab(on_records, off_records)

    # 写报告
    report_path = Path(output_dir) / "rag_ab_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 打印摘要
    print("\nP0 3.1 RAG A/B 对比实验结果：")
    print(f"  配对任务数: {report['paired_tasks']}")
    print(
        f"  RAG ON:  成功率={report['rag_on']['success_rate']:.2f}  "
        f"avg_tokens={report['rag_on']['avg_tokens']:.0f}  "
        f"avg_iters={report['rag_on']['avg_iterations']:.1f}  "
        f"RAG effective={report['rag_on']['rag_effective_rate']:.2f}"
    )
    print(
        f"  RAG OFF: 成功率={report['rag_off']['success_rate']:.2f}  "
        f"avg_tokens={report['rag_off']['avg_tokens']:.0f}  "
        f"avg_iters={report['rag_off']['avg_iterations']:.1f}"
    )
    print(
        f"\n  Token 节省: Δavg={report['token_saving']['delta_avg']} "
        f"({report['token_saving']['delta_pct']}%)  "
        f"p_welch={report['token_saving']['p_value_welch']:.4f}  "
        f"p_MWU={report['token_saving']['p_value_mann_whitney']:.4f}  "
        f"Cohen's d={report['token_saving']['cohens_d']:.3f}"
    )
    print(
        f"\n  迭代节省: Δavg={report['iteration_saving']['delta_avg']}  "
        f"p_welch={report['iteration_saving']['p_value_welch']:.4f}  "
        f"Cohen's d={report['iteration_saving']['cohens_d']:.3f}"
    )
    print("\n  错误类型偏移（RAG 收益）:")
    for cat, v in report["error_category_shift"].items():
        if v["delta"] != 0:
            print(f"    {cat}: RAG ON={v['rag_on_count']}, RAG OFF={v['rag_off_count']}, Δrate={v['delta']:+.4f}")
    print("\n  解读:")
    for key, txt in report["interpretation"].items():
        print(f"    [{key}] {txt}")
    print(f"\n完整报告: {report_path}")


if __name__ == "__main__":
    main()
