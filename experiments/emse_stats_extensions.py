#!/usr/bin/env python3
"""emse_stats_extensions.py — 统计报告规范补强（第十九轮评审 A-15，2026-10-16，零 LLM）。

背景（EMSE 投稿前三项统计规范缺口）：
    1. **Wilson CI 缺失**：所有检出率/修复率此前只报点估计。EMSE 审稿人通常
       要求置信区间；小样本（QuixBugs n=37/41）下 Wilson 区间比 naive
       正态近似宽得多，直接影响"差异是否稳健"的判读；
    2. **效应量缺失**：McNemar 只报 χ²/p，未报 Cohen's g（不一致对幅度）
       与 odds ratio（方向与强度）；
    3. **成本无区间**：$/task 只报点估计，未报 bootstrap CI——成本对比
       （aitester 6.2× 于 df）是论文核心论点之一，需要不确定性量化。

口径（诚实纪律）：
    - 只消费已归档原始工件（main_batch R-P0-2 三种子 / E6 / E4），零 LLM、
      零网络、纯 stdlib（math/random/json），保证任何环境可复算；
    - bootstrap 种子固定 42、次数 10000，结果逐位可复现；
    - Wilson / Cohen's g / OR 为确定性计算；bootstrap 为随机但种子化；
    - $/task 换算假设在报告中显式披露（价目表 + 聚合 in/out 比例），
      不与 token/task 混为一谈。

用法：
    python -m experiments.emse_stats_extensions            # 全量计算 + 写工件
    python -m experiments.emse_stats_extensions --stdout   # 只打印不落盘
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

from src.utils.atomic_io import atomic_write_json

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# AB-15a（2026-10-20）：币种判定与机制名的唯一事实源在 `src.budget.pricing`。
from src.budget.pricing import entry_block_reason, models_layer, table_read_reason  # noqa: E402

# ─── 输入工件（R-P0-2 当前口径三种子 + E6 对照 + E4 修正结算）──────────────
MAIN_BATCH_FILES = [
    "experiments/results/main_batch/benchmark_synthetic_20261006_140906.json",  # seed 42
    "experiments/results/main_batch/benchmark_synthetic_20261006_151907.json",  # seed 43
    "experiments/results/main_batch/benchmark_synthetic_20261006_164357.json",  # seed 44
]
E6_FILE = "experiments/results/e6_a1_batches/e6_control_seed42/benchmark_synthetic_20261009_181758.json"
E4_FILES = {
    "aitester": "experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json",
    "plain_llm_df": "experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/plain_llm_df.json",
}
PRICE_TABLE = "experiments/price_table.json"

BOOTSTRAP_N = 10_000
BOOTSTRAP_SEED = 42
Z95 = 1.959963985  # 双尾 95% 正态分位数（比 1.96 精确，避免手抄常数漂移）


# ─── 纯函数（单测锁定）────────────────────────────────────────────────────


def wilson_ci(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """二项比例的 Wilson score 区间（小样本下比正态近似稳健）。

    Args:
        successes: 成功次数（如检出任务数）。
        n: 总次数（非 None 口径分母）。
        z: 正态分位数（默认 95% 双尾）。

    Returns:
        (下界, 上界)，均在 [0, 1]；n <= 0 时返回 (0.0, 0.0)（fail-closed）。
    """
    if n <= 0:
        return (0.0, 0.0)
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def cohens_g(n10: int, n01: int) -> float:
    """McNemar 不一致对的 Cohen's g = |b - c| / (b + c)（0 = 无差异，1 = 完全一边倒）。"""
    total = n10 + n01
    if total == 0:
        return 0.0
    return abs(n10 - n01) / total


def odds_ratio_ci(n10: int, n01: int, z: float = Z95) -> tuple[float, float, float]:
    """不一致对 odds ratio（b/c）与对数正态 CI。

    b 或 c 为 0 时用 Haldane-Anscombe 修正（+0.5）避免除零/无限；
    CI 跨 1 与 McNemar p>=0.05 同向（不一致对检验的口径等价物）。
    """
    b, c = n10 + 0.5, n01 + 0.5
    or_point = b / c
    se = math.sqrt(1 / b + 1 / c)
    lo = math.exp(math.log(or_point) - z * se)
    hi = math.exp(math.log(or_point) + z * se)
    return (or_point, lo, hi)


def binom_exact_two_sided(k: int, n: int, p: float = 0.5) -> float:
    """二项分布精确双尾 p 值（McNemar 精确检验；纯 stdlib，不依赖 scipy）。

    口径：两尾概率之和（min 尾 ×2 与全尾枚举的较保守者取小，防超 1）。
    """
    if n == 0:
        return 1.0

    def pmf(i: int) -> float:
        return math.comb(n, i) * (p**i) * ((1 - p) ** (n - i))

    prob_k = pmf(k)
    tail = sum(pmf(i) for i in range(n + 1) if pmf(i) <= prob_k + 1e-12)
    return min(1.0, tail)


def paired_bootstrap_diff_ci(
    pairs: list[tuple[float, float]],
    n_boot: int = BOOTSTRAP_N,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """配对 bootstrap：对 (a_i, b_i) 任务对重抽样，返回 mean(a-b) 的 95% 分位 CI。

    配对重抽样保持任务级依赖结构（同任务两臂结果相关），比独立重抽样
    两个比例更贴合 McNemar 的配对口径。

    性能（2026-10-16 C 轮优化）：重抽样用 ``rng.choices(pairs, k=n)`` 单次
    调用替代逐元素 ``randrange``——cProfile 显示后者占全脚本 75% 耗时
    （1400 万次 randrange → _randbelow_with_getrandbits），实测 **4.6×**。
    ``sum`` 从左到右累加，与旧逐元素循环浮点次序一致（仅 RNG 流不同，
    CI 数值有种子级抖动，工件随本次优化重新生成）。
    """
    if not pairs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(pairs)
    diffs = [sum(a - b for a, b in rng.choices(pairs, k=n)) / n for _ in range(n_boot)]
    diffs.sort()
    lo = diffs[max(0, int(0.025 * n_boot))]
    hi = diffs[min(n_boot - 1, int(0.975 * n_boot))]
    return (lo, hi)


# ─── 工件读取 ──────────────────────────────────────────────────────────────


# ─── 工件读取（进程内缓存）─────────────────────────────────────────────────

_LOAD_CACHE: dict[str, dict[str, Any]] = {}


def _load(rel: str) -> dict[str, Any]:
    """读取并解析输入工件（**只读**；进程内按路径缓存，同文件多次消费只解析一次）。

    2026-10-16 C 轮优化：主流程曾对同批 ~2.3MB JSON 重复解析（token 汇总与
    by_model 汇总各一遍、成本 bootstrap 再一遍）。缓存后零行为变化——调用方
    均只读；**返回对象不得原地修改**（跨调用共享）。
    """
    p = _REPO_ROOT / rel
    key = str(p)
    cached = _LOAD_CACHE.get(key)
    if cached is not None:
        return cached
    if not p.is_file():
        raise FileNotFoundError(f"输入工件缺失：{rel}")
    data = json.loads(p.read_text(encoding="utf-8"))
    _LOAD_CACHE[key] = data
    return data


def _arm_detection_rows(data: dict[str, Any], arm: str) -> list[dict[str, Any]]:
    return data["results"][arm]["details"]


def _paired_detection(rows_a: list[dict[str, Any]], rows_b: list[dict[str, Any]]) -> tuple[int, int, int]:
    """返回 (n10, n01, n_paired)：a=1,b=0 / a=0,b=1 / 可配对数（detection_rate 均非 None）。"""
    map_b = {r["task_id"]: r.get("detection_rate") for r in rows_b}
    n10 = n01 = n_paired = 0
    for ra in rows_a:
        va = ra.get("detection_rate")
        vb = map_b.get(ra["task_id"])
        if va is None or vb is None:
            continue
        n_paired += 1
        if va == 1 and vb == 0:
            n10 += 1
        elif va == 0 and vb == 1:
            n01 += 1
    return n10, n01, n_paired


def _arm_totals(files: list[str], arm: str) -> tuple[int, int]:
    """汇总（检出数, 非 None 分母）跨多文件。"""
    ones = total = 0
    for rel in files:
        for r in _arm_detection_rows(_load(rel), arm):
            v = r.get("detection_rate")
            if v is not None:
                total += 1
                ones += 1 if v == 1 else 0
    return ones, total


def _load_price_models() -> tuple[dict[str, Any] | None, str | None]:
    """价目表 `models` 层：`(models, None)` 或 `(None, 机制名)`（AB-17）。

    改前本文件写的是 `_load(PRICE_TABLE)["models"]`——同一份坏表在这里的结局是**直接崩**：
    缺文件抛 `FileNotFoundError`、语法错抛 `JSONDecodeError`、缺 `models` 键抛 `KeyError`、
    顶层非对象抛 `TypeError` 或 `AttributeError`，七处读点里唯一一处连空表降级都没有。
    现走共享事实源：读取失败 → `table_read_reason`，形状 → `models_layer`，不崩也无痕。
    """
    try:
        data = _load(PRICE_TABLE)
    except (OSError, ValueError) as exc:
        return None, table_read_reason(exc)
    models, reason = models_layer(data)
    if reason is not None:
        return None, reason
    return models, None


def _cost_per_task(files: list[str], arm: str) -> tuple[float, float | None, str]:
    """每任务 token 与 $/task 点估计。

    $ 换算假设（显式披露）：按该臂聚合 input:output 比例 × deepseek-flash
    峰时全价（价目表登记口径）；多模型臂按各模型 token 占比加权（价目缺失
    的模型不计入 $，只计 token）。返回 (tokens_per_task, usd_per_task, note)。

    AB-15a（2026-10-20）：改前这里读 `input_per_mtok` / `output_per_mtok` 却**从不看币种**
    ——把批次实际用到的模型在价目表里改标 `CNY`，`usd_per_task` 逐位不变
    （实测 0.025884977011494247），即 AB-13c/AB-14c 同型缺陷在本仓的**第六处**、AB-14 漏接的
    一处。现接共享谓词与共享机制名（`src.budget.pricing`），被拒的份额按机制点名后跳过——
    与本函数既有的"价目缺失的模型不计入 $，只计 token + 在换算假设列点名"同一套约定；但币种/
    形状/`bool` 这一类**拒绝**不留部分和：只要有份额被拒，`usd_per_task` 就是 None（与站点 g
    的 `analyze_t1_b2_main_batch` 同一条规则）——"这个数少算了哪些模型"与"这个数的单位根本
    不成立"是两件事。真表三条目里批次实际用到的只有 `deepseek-flash`（USD）⇒ 读数与受保护
    报告字节一字不变。

    AB-16（2026-10-20）：条目级准入收口到 `entry_block_reason`——空条目与 `null` 价从
    "未计价"（0.0 部分和）改归"拒绝"（登记了却用不了，不等于"没登记"）；非对象条目改名为
    形状事实 `entry_not_object:<T>`（与 report 一致）；`"1.0"`/`[1.0]`/`{}` 不再抛
    TypeError，负价/`nan`/`inf` 不再照乘。真表读数一字不变。

    AB-17（2026-10-20）：表级读取收口到 `_load_price_models` 的共享判定——改前
    `_load(PRICE_TABLE)["models"]` 对同一份坏表直接崩（六种异常），现在坏表落
    `(tpt, None, "价目表不可用（<机制名>）…")`：不崩、不静默用内置价、$/task 无金额；
    条目检索从 `prices.get(m)` 的 `is None` 改 `not in`——"值 null"不再被读成"未登记"。
    """
    prices, table_reason = _load_price_models()
    tok = inp = out = 0
    n_tasks = 0
    for rel in files:
        data = _load(rel)
        n_tasks += data["total_tasks"]
        for r in _arm_detection_rows(data, arm):
            tu = r.get("token_usage") or {}
            tok += tu.get("total_tokens", 0) or 0
            inp += tu.get("input_tokens", 0) or 0
            out += tu.get("output_tokens", 0) or 0
    if n_tasks == 0:
        return (0.0, 0.0, "无任务")
    tpt = tok / n_tasks
    if prices is None:
        # AB-17：坏表不许崩、也不许静默——token 读数照常，$/task 无金额并点名机制。
        return (tpt, None, f"价目表不可用（{table_reason}）⇒ $/task 无金额（不是 0）")
    # 价目加权（按 by_model token 占比；未登记价目模型跳过并披露）
    model_tok: dict[str, int] = {}
    for rel in files:
        data = _load(rel)
        for r in _arm_detection_rows(data, arm):
            for m, t in (r.get("token_usage") or {}).get("by_model", {}).items():
                model_tok[m] = model_tok.get(m, 0) + (t or 0)
    usd = 0.0
    unpriced = []
    blocked: dict[str, list[str]] = {}
    for m, t in model_tok.items():
        if m not in prices:
            # 改前口径不变："价目表没登记这个模型"记为未计价（诚实降级），不算币种事件。
            # AB-17：改前这里 `prices.get(m)` 的 `is None` 把"值为 null"也读进这个桶；
            # 现在值 null 交条目谓词读 `entry_not_object:NoneType`（AB-11 判据）。
            unpriced.append(m)
            continue
        pr = prices[m]
        # AB-15a 币种 + AB-16 条目准入（形状 → 空 → 币种 → 数字）都取自共享事实源。
        # 改前这里：非对象条目在 `pr.get` 上抛 AttributeError、`"1.0"`/`[1.0]` 抛 TypeError、
        # 负价/`nan`/`inf` 照乘进 `usd`、空条目与 `null` 价折成"未计价"（0.0 部分和）。
        # 现在只留一条诚实降级（"没登记"），其余一律按机制点名并放弃部分和。
        reason = entry_block_reason(pr)
        if reason is not None:
            blocked.setdefault(reason, []).append(m)
            continue
        pi, po = pr["input_per_mtok"], pr["output_per_mtok"]
        share = t / max(tok, 1)
        # 价目为每百万 token 单价 → /1e6 换算为每 token；in/out 比例用该臂聚合口径
        usd += share * tpt * (pi * (inp / max(tok, 1)) + po * (out / max(tok, 1))) / 1_000_000
    note = f"价目加权（in:out={inp}:{out}）；未计价模型：{unpriced or '无'}"
    if blocked:
        note += "；计价被拒：" + "；".join(
            f"{code}←{'、'.join(sorted(models))}" for code, models in sorted(blocked.items())
        )
    # 任一份额被拒 ⇒ $/task 没有金额（部分和不得冒充全额），机制名留在 note 里。
    return (tpt, None if blocked else usd, note)


def _bootstrap_cost_ci(
    files: list[str], arm: str, n_boot: int = BOOTSTRAP_N, seed: int = BOOTSTRAP_SEED
) -> tuple[float, float]:
    """每任务 token 均值的任务级 bootstrap 95% CI（种子化）。

    性能（2026-10-16 C 轮优化）：同 :func:`paired_bootstrap_diff_ci`，
    逐元素 randrange → ``rng.choices(rows, k=n)``（实测 4.6×）。
    """
    rows: list[int] = [
        (r.get("token_usage") or {}).get("total_tokens", 0) or 0
        for rel in files
        for r in _arm_detection_rows(_load(rel), arm)
    ]
    if not rows:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(rows)
    means = sorted(sum(rng.choices(rows, k=n)) / n for _ in range(n_boot))
    return (means[max(0, int(0.025 * n_boot))], means[min(n_boot - 1, int(0.975 * n_boot))])


# ─── 主流程 ────────────────────────────────────────────────────────────────


def build_report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "caliber": "Wilson CI / Cohen's g / OR / 配对 bootstrap（第十九轮评审 A-15）",
        "bootstrap": {"n": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED, "z95": Z95},
        "inputs": {"main_batch": MAIN_BATCH_FILES, "e6": E6_FILE, "e4": E4_FILES},
        "arms": {},
        "comparisons": {},
    }

    # 1) R-P0-2 三臂（当前口径：三种子合并）
    for arm in ["aitester", "plain_llm", "plain_llm_df"]:
        ones, total = _arm_totals(MAIN_BATCH_FILES, arm)
        lo, hi = wilson_ci(ones, total)
        tpt, usd, note = _cost_per_task(MAIN_BATCH_FILES, arm)
        clo, chi = _bootstrap_cost_ci(MAIN_BATCH_FILES, arm)
        report["arms"][f"rp02_{arm}"] = {
            "detection": {"killed": ones, "denominator": total, "rate": ones / max(total, 1), "wilson95": [lo, hi]},
            "tokens_per_task": tpt,
            "tokens_per_task_bootstrap95": [clo, chi],
            "usd_per_task": usd,
            "usd_note": note,
        }

    # 2) 配对对比（McNemar + g + OR + 精确 p + bootstrap diff CI）
    def _compare(label: str, files_a: list[str], arm_a: str, files_b: list[str], arm_b: str) -> None:
        """配对对比。files_a/files_b 分侧给出（E4 为单臂文件，两侧不同）。"""
        n10 = n01 = 0
        pairs: list[tuple[float, float]] = []
        for rel_a, rel_b in zip(files_a, files_b, strict=True):  # 两侧文件一一对应（单臂工件分侧给出）
            data_a, data_b = _load(rel_a), _load(rel_b)
            ra = {r["task_id"]: r.get("detection_rate") for r in _arm_detection_rows(data_a, arm_a)}
            rb = {r["task_id"]: r.get("detection_rate") for r in _arm_detection_rows(data_b, arm_b)}
            for tid, va in ra.items():
                vb = rb.get(tid)
                if va is None or vb is None:
                    continue
                pairs.append((float(va), float(vb)))
                if va == 1 and vb == 0:
                    n10 += 1
                elif va == 0 and vb == 1:
                    n01 += 1
        g = cohens_g(n10, n01)
        or_pt, or_lo, or_hi = odds_ratio_ci(n10, n01)
        p_exact = binom_exact_two_sided(min(n10, n01), n10 + n01)
        dlo, dhi = paired_bootstrap_diff_ci(pairs)
        ka, ta = sum(1 for a, _ in pairs if a == 1), len(pairs)
        kb, tb = sum(1 for _, b in pairs if b == 1), len(pairs)
        report["comparisons"][label] = {
            "arm_a": arm_a,
            "arm_b": arm_b,
            "n10_a_only": n10,
            "n01_b_only": n01,
            "n_paired": len(pairs),
            "cohens_g": g,
            "odds_ratio": {"point": or_pt, "ci95": [or_lo, or_hi]},
            "mcnemar_exact_p": p_exact,
            "paired_bootstrap_diff95": [dlo, dhi],
            "rate_a": ka / max(ta, 1),
            "rate_b": kb / max(tb, 1),
        }

    _compare("rp02_aitester_vs_df", MAIN_BATCH_FILES, "aitester", MAIN_BATCH_FILES, "plain_llm_df")
    _compare("rp02_df_vs_plain_llm", MAIN_BATCH_FILES, "plain_llm_df", MAIN_BATCH_FILES, "plain_llm")
    _compare("e6_aitester_vs_df", [E6_FILE], "aitester", [E6_FILE], "plain_llm_df")
    _compare(
        "e4_aitester_vs_df",
        [E4_FILES["aitester"]],
        "aitester",
        [E4_FILES["plain_llm_df"]],
        "plain_llm_df",
    )

    # 3) E4 修复率（repair_rate 口径）+ QuixBugs 双臂 Wilson
    for arm, rel in E4_FILES.items():
        rows = _arm_detection_rows(_load(rel), arm)
        det = [r for r in rows if r.get("detection_rate") is not None]
        det1 = [r for r in det if r.get("detection_rate") == 1]
        rep = [r for r in rows if r.get("repair_rate") is not None]
        rep1 = [r for r in rep if r.get("repair_rate") == 1]
        report["arms"][f"e4_{arm}"] = {
            "detection": {
                "killed": len(det1),
                "denominator": len(det),
                "rate": len(det1) / max(len(det), 1),
                "wilson95": list(wilson_ci(len(det1), len(det))),
            },
            "repair": {
                "killed": len(rep1),
                "denominator": len(rep),
                "rate": len(rep1) / max(len(rep), 1),
                "wilson95": list(wilson_ci(len(rep1), len(rep))),
            },
        }

    # 4) E6 三臂 Wilson
    for arm in ["aitester", "plain_llm", "plain_llm_df"]:
        rows = _arm_detection_rows(_load(E6_FILE), arm)
        det = [r for r in rows if r.get("detection_rate") is not None]
        det1 = [r for r in det if r.get("detection_rate") == 1]
        report["arms"][f"e6_{arm}"] = {
            "detection": {
                "killed": len(det1),
                "denominator": len(det),
                "rate": len(det1) / max(len(det), 1),
                "wilson95": list(wilson_ci(len(det1), len(det))),
            },
        }
    return report


def render_markdown(rep: dict[str, Any]) -> str:
    lines = [
        "# 统计报告规范补强（Wilson CI / 效应量 / 成本 bootstrap）",
        "",
        f"- 口径：{rep['caliber']}",
        f"- bootstrap：n={rep['bootstrap']['n']}，seed={rep['bootstrap']['seed']}（逐位可复现）",
        "- 输入：R-P0-2 三种子（261 任务/臂口径）+ E6 对照 + E4 QuixBugs 修正结算（零 LLM 重算）",
        "",
        "## 1. 各臂点估计 + Wilson 95% CI",
        "",
        "| 臂 | 指标 | k/n | 点估计 | Wilson 95% CI |",
        "|---|---|---|---|---|",
    ]
    for name, blk in rep["arms"].items():
        for metric in ("detection", "repair"):
            if metric in blk:
                d = blk[metric]
                lines.append(
                    f"| {name} | {metric} | {d['killed']}/{d['denominator']} | "
                    f"{d['rate'] * 100:.2f}% | [{d['wilson95'][0] * 100:.2f}%, {d['wilson95'][1] * 100:.2f}%] |"
                )
    lines += [
        "",
        "## 2. 配对对比（McNemar 精确检验 + Cohen's g + OR + bootstrap diff CI）",
        "",
        "| 对比 | n10(a only) | n01(b only) | rate_a | rate_b | Cohen's g | OR [95% CI] | 精确 p | bootstrap Δ [95% CI] |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, c in rep["comparisons"].items():
        lines.append(
            f"| {name} | {c['n10_a_only']} | {c['n01_b_only']} | {c['rate_a'] * 100:.2f}% | "
            f"{c['rate_b'] * 100:.2f}% | {c['cohens_g']:.3f} | "
            f"{c['odds_ratio']['point']:.3f} [{c['odds_ratio']['ci95'][0]:.3f}, {c['odds_ratio']['ci95'][1]:.3f}] | "
            f"{c['mcnemar_exact_p']:.4g} | "
            f"[{c['paired_bootstrap_diff95'][0] * 100:+.2f}pp, {c['paired_bootstrap_diff95'][1] * 100:+.2f}pp] |"
        )
    lines += [
        "",
        "## 3. 成本（token/task + $/task 点估计 + bootstrap CI）",
        "",
        "| 臂 | tokens/task | tokens/task 95% CI | $/task | 换算假设 |",
        "|---|---|---|---|---|",
    ]
    for name, blk in rep["arms"].items():
        if "tokens_per_task" in blk:
            lo, hi = blk["tokens_per_task_bootstrap95"]
            # AB-15a：被拒的金额不得挂 `$`（改前这里对 None 直接 `:.4f` 崩，而只要聚合出
            # 数字就照原样印成全额）。机制名在同行"换算假设"列里点名。
            usd_cell = f"${blk['usd_per_task']:.4f}" if blk["usd_per_task"] is not None else "—（无金额）"
            lines.append(
                f"| {name} | {blk['tokens_per_task']:.0f} | [{lo:.0f}, {hi:.0f}] | {usd_cell} | {blk['usd_note']} |"
            )
    lines += [
        "",
        "## 4. 口径纪律",
        "",
        "- Wilson CI 为 Wilson score 区间（小样本稳健）；不与 naive 正态近似混用；",
        "- Cohen's g 仅用 McNemar 不一致对（b/c），与 OR 互为方向/强度表述；",
        "- bootstrap 为任务级重抽样（配对结构保持），种子 42，10k 次；",
        "- 表中 rate_a / rate_b 为**配对子集**口径（denominator = n_paired），与第 1 节",
        "  全分母口径（如 df 44.83% @261）可能不同，引用时须区分；",
        "- n01=0 时 OR 经 Haldane-Anscombe +0.5 修正，CI 上界极大属正确行为",
        "  （零不一致对 = 点估计无穷方向的保守截断），不得解读为「效应不显著」；",
        "- $/task 换算假设见各行 note（价目表官方登记口径，峰时全价保守上界）；",
        "- 本工件所有数字可由 `python -m experiments.emse_stats_extensions` 零 LLM 逐位复算。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="统计报告规范补强（Wilson CI / 效应量 / 成本 bootstrap）")
    parser.add_argument("--stdout", action="store_true", help="只打印 markdown，不落盘")
    parser.add_argument("--out-dir", default="experiments/results/emse_stats_extensions_20261016")
    args = parser.parse_args(argv)

    rep = build_report()
    md = render_markdown(rep)
    if args.stdout:
        print(md)
        return 0
    out = _REPO_ROOT / args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out / "STATS_EXTENSIONS.json", rep, indent=2, mode=0o644)
    (out / "README.md").write_text(md, encoding="utf-8")
    print(f"工件已写入：{out}")
    print(md[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
