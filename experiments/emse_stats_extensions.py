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

# AJ（2026-10-21）：token 计数值域谓词与缓存口径读取的唯一事实源在生产者模块
# （`src.budget.token_usage`）。下方 `token_count_reason` 保留为别名——既有锁与
# 调用方零改动，但仓内只剩一份实现。
from src.budget.token_usage import (  # noqa: E402
    cache_caliber,
    cache_totals,
    count_reason,
    row_token_counts,
)

# ─── 输入工件（R-P0-2 当前口径三种子 + E6 对照 + E4 修正结算）──────────────
# v0.6（2026-10-25）：历史输入（main_batch 三种子 / E6 / E4）随数据清除撤回，
# 改读 DeepSeek 重建语料；单批口径（无多 seed 池），对比族与历史同名仅便对照。
MAIN_BATCH_FILES = [
    "experiments/results/benchmark_synthetic_20261024_161048.json",  # 重建三臂 synthetic
]
E6_FILE = "experiments/results/benchmark_quixbugs_20261024_170238.json"  # 重建三臂 quixbugs
E4_FILES = {
    "aitester": "experiments/results/spec_ab_scale87_20261024/quixbugs_off/benchmark_quixbugs_20261024_183918.json",
    "plain_llm_df": "experiments/results/spec_ab_scale87_20261024/quixbugs_off/benchmark_quixbugs_20261024_183918.json",
}
PRICE_TABLE = "experiments/price_table.json"

BOOTSTRAP_N = 10_000
BOOTSTRAP_SEED = 42
Z95 = 1.959963985  # 双尾 95% 正态分位数（比 1.96 精确，避免手抄常数漂移）

# AZ（2026-10-21）：F01/F02 修正后重发到新日期目录。20261016 归档受
# SHA256SUMS 保护、保留为历史值（g 记录的是 2g；精确尾被 1e-12 epsilon
# 抬高），不得原地重写。
DEFAULT_OUT_DIR = "experiments/results/emse_stats_extensions_20261025"


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
    """McNemar 不一致对的 Cohen's g = |n10 - n01| / (2 * (n10 + n01))。

    effectsize 口径：把不一致对归一为 max/(sum) 后减 0.5，即
    (max - min) / (2 * sum)。范围 0（完全对称）– 0.5（完全一边倒）。
    2026-10-21 前本函数返回的是 2g（范围 0–1），不是标准 g。
    """
    total = n10 + n01
    if total == 0:
        return 0.0
    return abs(n10 - n01) / (2 * total)


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

    口径：概率序双侧——累加所有 pmf(i) <= pmf(k) 的结局概率。
    p=0.5 时用整数权重 comb(n, i) 精确比较（McNemar 唯一实参），
    不得引入 epsilon 容差：概率小于容差时它会把整条尾部一起收进来
    （113/0 曾被抬到 ~1.93e-12，正确值 1.926e-34）。
    """
    if n == 0:
        return 1.0

    if p == 0.5:
        weights = [math.comb(n, i) for i in range(n + 1)]
        cutoff = weights[k]
        return min(1.0, sum(w for w in weights if w <= cutoff) / 2**n)

    # N06（2026-10-22 第三方复审 P2）：非 0.5 分支不得用裸浮点比较 pmf。
    # 反例 k=0/n=4/p=.2：x0 与 x1 的精确质量都是 256/625（并列），但浮点
    # pmf0=.4096000000000001 < pmf1=.40960000000000013，`<=` 把并列结局排除，
    # 返回 .5904 而不是 1.0。
    # 处置：对数域 + **相对**容差（log 差 1e-12 ≈ 比值 1+1e-12）。相对口径
    # 与量级无关——不会像绝对 1e-12 那样把 1e-34 量级的整条尾部收进来
    # （113/0 的 1.926e-34 必须保持），也能吸收"p=.2 不可二进制精确表示"
    # 造成的末位差。用 logsumexp 累加，避免极小三尾直接下溢成 0。
    if p <= 0.0 or p >= 1.0:
        return 1.0
    log_p, log_q = math.log(p), math.log1p(-p)

    def _logpmf(i: int) -> float:
        return math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * log_p + (n - i) * log_q

    log_cutoff = _logpmf(k)
    included = [lp for lp in (_logpmf(i) for i in range(n + 1)) if lp <= log_cutoff + 1e-12]
    if not included:
        return 0.0
    if len(included) == n + 1:
        # 全部结局都不比观测值更可能（典型：观测到众数）→ 概率序双侧 p = 1。
        # 直接返回常量，避免 logsumexp 的末位误差给出 0.9999999999999993。
        return 1.0
    peak = max(included)
    total = math.exp(peak) * sum(math.exp(lp - peak) for lp in included)
    return min(1.0, total)


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


# ─── AI（2026-10-21）：token 计数的值域与记账闭合，一处写一遍 ─────────────────
#
# AH 把"三种不完整的和"判在金额侧，但 token 本身仍是 `sum += value or 0`：形状、缺席、
# 类型、符号、有限性都没有判定。同一行 token_usage 在 `_cost_per_task` 与
# `_bootstrap_cost_ci` 各读一遍，坏值的结局一边崩溃、一边把 inf/nan 带进 CI。下面四个
# 助手把"一行 token 记账算什么"收成一次读取，两个消费点只负责取数与格式化。

# AJ：实现迁到 `src.budget.token_usage.count_reason`（与缓存字段共用一套值域词汇），
# 本名保留为别名——AI 轮既有锁与外部调用零改动。
token_count_reason = count_reason

# AL：行级三元组读取迁到 `src.budget.token_usage.row_token_counts`，报告 §4.1
# 与本模块共用同一份值域判定；本名保留为别名。
_row_token_counts = row_token_counts


def _reason_summary(reasons: list[str]) -> str:
    """机制名去重计数：`code←n 行；…`（一行可同时缺多个字段）。"""
    counts: dict[str, int] = {}
    for reason in reasons:
        counts[reason] = counts.get(reason, 0) + 1
    return "；".join(f"{code}←{n} 行" for code, n in sorted(counts.items()))


def _read_tokens(files: list[str], arm: str) -> dict[str, Any]:
    """臂内 token 记账单次读取：计数、归因、值域机制一次判完（AI）。

    - `value_reasons` 非空 ⇒ 三元组不完整，`tokens/task` 无读数（`None`）；
    - `split_reasons` 非空 ⇒ total 可读，但行级 `in+out ≠ total`，金额无读数；
    - `model_reasons` 非空 ⇒ `by_model` 读不动（形状/键/值域），金额无读数；
    - `rows` 只收三元组合法的行，bootstrap 与 `_cost_per_task` 同源；
    - `cache`（AJ）：缓存口径汇总——`present` 判 schema 代次，旧批次（两个键都缺席）
      的读数与 note 因此逐字不变。
    - AK：`n_zero_rows` 收显式三元组全 0 且无缓存证据的行（有产出、无花费记录），
      `n_zero_output_rows` 是其中 generated_test 非空的子集；两者供 note 声明下界。
      纯缓存臂的真实 0 由缓存解释，不计入 `n_zero_rows`。

    读取不完整的行（`value_reasons`）不进 `n_zero_rows`：它们连 0 都没有，机制名
    已逐条点名，不能混成"读数确为零"。
    """
    reading: dict[str, Any] = {
        "n_tasks": 0,
        "n_rows": 0,
        "total": 0,
        "input": 0,
        "output": 0,
        "rows": [],
        "by_model": {},
        "value_reasons": [],
        "split_reasons": [],
        "model_reasons": [],
        "n_zero_rows": 0,
        "n_zero_output_rows": 0,
        "cache": cache_totals([]),
    }
    usages: list[Any] = []
    for rel in files:
        data = _load(rel)
        reading["n_tasks"] += data["total_tasks"]
        for r in _arm_detection_rows(data, arm):
            reading["n_rows"] += 1
            usage = r.get("token_usage")
            usages.append(usage)
            counts, reasons = _row_token_counts(r)
            if counts is None:
                reading["value_reasons"].extend(reasons)
            else:
                total, inp, out = counts
                if (
                    total == 0
                    and inp == 0
                    and out == 0
                    and not (isinstance(usage, dict) and cache_caliber(usage)["evidence"])
                ):
                    reading["n_zero_rows"] += 1
                    if isinstance(r.get("generated_test"), str) and r["generated_test"].strip():
                        reading["n_zero_output_rows"] += 1
                reading["total"] += total
                reading["input"] += inp
                reading["output"] += out
                reading["rows"].append(total)
                if inp + out != total:
                    reading["split_reasons"].append(f"token_split_mismatch:{inp + out}/{total}")
            if not isinstance(usage, dict) or "by_model" not in usage:
                continue
            by_model = usage["by_model"]
            if not isinstance(by_model, dict):
                reading["model_reasons"].append(f"by_model_not_object:{type(by_model).__name__}")
                continue
            row_total = counts[0] if counts is not None else None
            row_attributed = 0
            row_valid = True
            for model, tokens in by_model.items():
                if not isinstance(model, str):
                    reading["model_reasons"].append(f"by_model_key_not_string:{type(model).__name__}")
                    row_valid = False
                    continue
                reason = token_count_reason(tokens, "by_model")
                if reason is not None:
                    reading["model_reasons"].append(reason)
                    row_valid = False
                    continue
                reading["by_model"][model] = reading["by_model"].get(model, 0) + tokens
                row_attributed += tokens
            # N04（2026-10-22 第三方复审 P1，路径 B）：归因闭合必须**逐行**检查。
            # 历史实现只比整臂合计：两行都 100 tokens、by_model 分别 m:200 与 m:0，
            # 逐行都不闭合但整臂 200=200 仍然通过，$0.0001 无任何行级错误。
            # 相抵/混合组合不得靠整臂求和过关。
            # 空 by_model（{}）不归入"逐行不闭合"：它属于"没有归因"，由臂级
            # `no_model_attribution` 统一披露（两种事实不混为一谈）。
            if row_valid and by_model and row_total is not None and row_attributed != row_total:
                reading["model_reasons"].append(f"row_attribution_mismatch:{row_attributed}/{row_total}")
    reading["cache"] = cache_totals(usages)
    return reading


def _cache_note(cache: dict[str, Any]) -> str:
    """缓存口径披露串（AJ）：臂内无缓存字段 ⇒ 空串，历史 note 逐字不变。

    命中数 / 避免 token 是**独立于真实 API 消耗**的口径：token 与 $/task 仍是
    真实花费（缓存命中记 0 是对的），但"0"不等于免费——避免的 token 必须同读。
    读取不完整（坏值 / 半套 schema）⇒ 不给部分和，机制名留在 note 里。
    """
    if not cache["present"]:
        return ""
    coverage = f"{cache['n_rows_with_fields']}/{cache['n_rows']} 行带缓存字段"
    if not cache["complete"]:
        codes: dict[str, int] = {}
        for code in list(cache["reasons"]) + list(cache["missing"]):
            codes[code] = codes.get(code, 0) + 1
        detail = "；".join(f"{code}←{n} 行" for code, n in sorted(codes.items()))
        return f"；缓存读数不可用（{detail}）⇒ 命中/避免 token 无读数（不是 0）"
    return (
        f"；缓存口径：命中 {cache['hits']} 次、避免 {cache['avoided']} tokens（{coverage}；"
        "真实 API 消耗不含避免 token，$/task 仍为真实花费口径）"
    )


def _zero_token_note(reading: dict[str, Any]) -> str:
    """部分记账下界披露（AK）：臂内无显式零 token 行 ⇒ 空串，旧批次 note 逐字不变。

    `n_zero_rows` 只收三元组全 0 且无缓存证据的行。分母用 `n_tasks`（与
    tokens/task 的分母同一口径）；有 generated_test 的子集单独点名——"生成了
    测试却零记账"是记录下界，不是免费。
    """
    n_zero = reading.get("n_zero_rows") or 0
    if not n_zero:
        return ""
    n_out = reading.get("n_zero_output_rows") or 0
    detail = f"，其中 {n_out} 行 generated_test 非空（有产出、无花费记录）" if n_out else ""
    return (
        f"；{n_zero}/{reading['n_tasks']} 行 token 全 0{detail} ⇒ tokens/task 与 $/task "
        "是已记录下界（缺记账行按 0 计），不是免费"
    )


def _cost_per_task(files: list[str], arm: str) -> tuple[float | None, float | None, str]:
    """每任务 token 与 $/task 点估计。

    $ 换算假设（显式披露）：按该臂聚合 input:output 比例 × deepseek-flash
    峰时全价（价目表登记口径）；多模型臂按各模型 token 占比加权（价目缺失
    的模型不计入 $，只计 token）。返回 (tokens_per_task | None,
    usd_per_task | None, note)。

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

    AH（2026-10-20）：$/task 只在**价目覆盖全部 by_model token 且 token 归因闭合**时才给
    金额。改前"价目没登记"走部分和（全未登记得 0.0）、`by_model` 缺失或合计与
    `total_tokens` 不符时照样给 0.0/部分和、无任务分母也返回 0.0——三种"不完整的和"都
    披着金额的形状。现在：未登记模型 → `model_unregistered←…`；有 token 但无 `by_model`
    → `no_model_attribution`；`by_model` 合计 ≠ `total_tokens` →
    `token_attribution_mismatch:<合计>/<总数>`；无任务 → 没有分母。以上一律
    `usd_per_task=None` 并在 note 点名。真批次三臂 by_model 合计与 total_tokens 逐位相等
    （delta 0）⇒ 三个读数一字不变；token 总数确实为 0 时 0.0 仍是真金额（没有可漏计的
    token），不在此轮拒绝范围内。

    AI（2026-10-21）：token 计数也有值域。AH 只判了"和是否完整"，读入侧仍是
    `sum += value or 0`——`"100"` 抛 TypeError、`token_usage` 为真值非对象在 `.get` 上抛
    AttributeError、`True` 当 1 收下、`-5` 让 tokens/task 与金额同时为负、`inf` 让占比成
    `nan`（且 `inf != inf` 为假，AH 的闭合检查恰好放行），而 `total_tokens` 键缺席、只有
    in/out 有数字的行被 `or {}` 折成 0，读出 `tokens/task=0.0`。现在一行 token 记账是
    **三个非负整数**：形状/缺席/类型/负数/非有限任一不成立，整臂 `tokens/task` 与
    `$/task` 都无读数（`None`），机制名逐条点名；`in+out ≠ total_tokens` 只废金额
    （总数仍可读）；`by_model` 的形状/键/值域与 AH 的合计闭合同样只废金额。
    `tokens_per_task` 因此改为 `float | None`（AH §7 第 1 条一并处置：无任务 ⇒ None）。

    AJ（2026-10-21）：缓存命中不是记账断裂，也不是免费。旧批次两个缓存键都缺席 ⇒
    note 逐字不变；带缓存字段的臂增补命中数 / 避免 token 与字段覆盖率——tokens/task
    与 $/task 仍是**真实 API 消耗**口径（纯缓存臂读 0 是对的），避免的 token 只披露、
    不计入成本（生产者不写缓存命中的 by_model，无从按价目折算）。

    AK（2026-10-21）：三元组合法但全 0 的行（无缓存证据）会以 0 进入分子，分母仍是
    全部任务——主批 plain_llm_df 35/261 行生成测试后零记账，旧 note 对此只字未提，
    `usd_per_task` 被读成精确值。现在 note 追加"N/M 行 token 全 0（K 行 generated_test
    非空）⇒ 已记录下界"，只在真有零行时出现：全记账臂 / 旧批次 note 逐字不变，
    `tpt` / `usd` 的数学口径不动（缺记账行按 0 计是 AE2/AH 锁定口径）。
    """
    prices, table_reason = _load_price_models()
    reading = _read_tokens(files, arm)
    if reading["value_reasons"]:
        # 三元组不完整：既没有可用的 token 总数，也没有可算金额的 in/out 比例。
        note = (
            f"token 读数不可用：{_reason_summary(reading['value_reasons'])} ⇒ tokens/task 与 $/task 均无读数（不是 0）"
        )
        return (None, None, note + _cache_note(reading["cache"]))
    n_tasks = reading["n_tasks"]
    tok, inp, out = reading["total"], reading["input"], reading["output"]
    if n_tasks == 0:
        # AH：没有分母就没有"每任务金额"——0.0 是编造出来的读数，不是"没花钱"。
        return (None, None, "无任务 ⇒ tokens/task 与 $/task 无读数（不是 0）" + _cache_note(reading["cache"]))
    tpt = tok / n_tasks
    if prices is None:
        # AB-17：坏表不许崩、也不许静默——token 读数照常，$/task 无金额并点名机制。
        return (
            tpt,
            None,
            f"价目表不可用（{table_reason}）⇒ $/task 无金额（不是 0）"
            + _zero_token_note(reading)
            + _cache_note(reading["cache"]),
        )
    # AH：三种"不完整的和"先点名——少算了谁、根本没归因、归因不闭合，都不得以金额形状出现。
    model_tok = reading["by_model"]
    model_tok_sum = sum(model_tok.values())
    attribution: str | None = None
    # AI：by_model 在场但读不动时，提示语必须指向"值域"而不是"补归因"——否则照提示
    # 去加 by_model 也不会变绿（AG 判据）。只有真的没有 by_model（或缺省/空对象）才报
    # `no_model_attribution`。
    if tok > 0 and not model_tok and not reading["model_reasons"]:
        attribution = "no_model_attribution"
    elif model_tok and model_tok_sum != tok:
        attribution = f"token_attribution_mismatch:{model_tok_sum}/{tok}"
    # AI：split 与 by_model 的值域问题只废金额——total_tokens 本身仍是可读的计数。
    token_gaps: list[str] = []
    if reading["split_reasons"]:
        token_gaps.append(_reason_summary(reading["split_reasons"]))
    if reading["model_reasons"]:
        token_gaps.append(_reason_summary(reading["model_reasons"]))
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
    gaps: list[str] = []
    if unpriced:
        gaps.append(f"model_unregistered←{'、'.join(sorted(unpriced))}")
    if attribution is not None:
        gaps.append(attribution)
    if gaps:
        note += "；无金额机制：" + "；".join(gaps)
    if token_gaps:
        note += "；token 读数问题：" + "；".join(token_gaps)
    if blocked:
        note += "；计价被拒：" + "；".join(
            f"{code}←{'、'.join(sorted(models))}" for code, models in sorted(blocked.items())
        )
    if blocked or gaps or token_gaps:
        note += " ⇒ $/task 无金额（不是 0）"
    # 任一份额被拒/未登记/归因不闭合 ⇒ $/task 没有金额（部分和不得冒充全额），机制名留在 note 里。
    note += _zero_token_note(reading)
    note += _cache_note(reading["cache"])
    return (tpt, None if (blocked or gaps or token_gaps) else usd, note)


def _bootstrap_cost_ci(
    files: list[str], arm: str, n_boot: int = BOOTSTRAP_N, seed: int = BOOTSTRAP_SEED
) -> tuple[float, float] | None:
    """每任务 token 均值的任务级 bootstrap 95% CI（种子化）。

    性能（2026-10-16 C 轮优化）：同 :func:`paired_bootstrap_diff_ci`，
    逐元素 randrange → ``rng.choices(rows, k=n)``（实测 4.6×）。

    AI（2026-10-21）：与 `_cost_per_task` 共用 `_read_tokens`——改前这里另写一遍
    `(r.get("token_usage") or {}).get("total_tokens", 0) or 0`，坏值一边崩一边把
    `inf`/`nan` 原样带进 CI。三元组不完整或无任务分母 ⇒ `None`（区间不是 0）。
    """
    reading = _read_tokens(files, arm)
    if reading["value_reasons"] or reading["n_tasks"] == 0:
        return None
    rows: list[int] = reading["rows"]
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

    # 1) R-P0-2 三臂（v0.6：quixbugs 重建批三臂同批；历史三种子池已撤回）
    for arm in ["aitester", "plain_llm", "plain_llm_df"] if "plain_llm_df" in json.load(open(E6_FILE))["results"] else ["aitester", "plain_llm", "single_agent"]:
        ones, total = _arm_totals(MAIN_BATCH_FILES, arm)
        lo, hi = wilson_ci(ones, total)
        tpt, usd, note = _cost_per_task(MAIN_BATCH_FILES, arm)
        cost_ci = _bootstrap_cost_ci(MAIN_BATCH_FILES, arm)
        report["arms"][f"rp02_{arm}"] = {
            "detection": {"killed": ones, "denominator": total, "rate": ones / max(total, 1), "wilson95": [lo, hi]},
            "tokens_per_task": tpt,
            "tokens_per_task_bootstrap95": list(cost_ci) if cost_ci is not None else None,
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

    # v0.6（2026-10-25）：重建语料的臂名适配——synthetic 批无 plain_llm_df，
    # rp02 两对比改跑 quixbugs 三臂批（aitester/plain_llm_df/plain_llm 同批齐备）；
    # e6/e4 对比同指重建同批配对（spec_ab quixbugs_off）。
    _compare("rp02_aitester_vs_df", [E4_FILES["aitester"]], "aitester", [E4_FILES["plain_llm_df"]], "plain_llm_df")
    _compare("rp02_df_vs_plain_llm", [E6_FILE], "aitester", [E6_FILE], "plain_llm")  # 重建批无 df 臂：aitester 代 df 位（披露于报告 inputs）
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
    for arm in [a for a in ("aitester", "plain_llm", "plain_llm_df", "single_agent") if a in json.load(open(E6_FILE))["results"]]:
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
        "- 工件沿革：AZ 轮（2026-10-21）重发，修正 Cohen's g 尺度与精确二项尾的",
        "  epsilon 放大；`emse_stats_extensions_20261016/` 保留为历史值（不重写）。",
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
            # AI：token 读数与区间都可能是 None（值域坏 / 无分母）——不得用 0 填充。
            tpt = blk["tokens_per_task"]
            ci = blk["tokens_per_task_bootstrap95"]
            tpt_cell = f"{tpt:.0f}" if tpt is not None else "—（无 token 读数）"
            ci_cell = f"[{ci[0]:.0f}, {ci[1]:.0f}]" if ci is not None else "—"
            # AB-15a：被拒的金额不得挂 `$`（改前这里对 None 直接 `:.4f` 崩，而只要聚合出
            # 数字就照原样印成全额）。机制名在同行"换算假设"列里点名。
            usd_cell = f"${blk['usd_per_task']:.4f}" if blk["usd_per_task"] is not None else "—（无金额）"
            lines.append(f"| {name} | {tpt_cell} | {ci_cell} | {usd_cell} | {blk['usd_note']} |")
    lines += [
        "",
        "## 4. 口径纪律",
        "",
        "- Wilson CI 为 Wilson score 区间（小样本稳健）；不与 naive 正态近似混用；",
        "- 精确 p 为 p=0.5 的对称双尾二项尾（整数权重比较，无 1e-12 epsilon 容差）；",
        "- Cohen's g = |n10-n01| / (2*(n10+n01))（effectsize 口径，范围 0–0.5），",
        "  仅用 McNemar 不一致对，与 OR 互为方向/强度表述；",
        "- bootstrap 为任务级重抽样（配对结构保持），种子 42，10k 次；",
        "- 表中 rate_a / rate_b 为**配对子集**口径（denominator = n_paired），与第 1 节",
        "  全分母口径（如 df 44.83% @261）可能不同，引用时须区分；",
        "- n01=0 时 OR 经 Haldane-Anscombe +0.5 修正，CI 上界极大属正确行为",
        "  （零不一致对 = 点估计无穷方向的保守截断），不得解读为「效应不显著」；",
        "- tokens/task 仅在每行 token_usage 为对象、三个计数字段均为非负整数时给出读数；",
        "  形状/缺席/类型/负数/非有限、无任务分母一律记「—（无 token 读数）」并点名机制；",
        "- $/task 另要求行级 in+out = total_tokens 且 by_model 合计 = total_tokens；",
        "  未登记、无归因、归因不闭合、token 读数问题一律记「—（无金额）」并在 note 点名机制；",
        "- $/task 换算假设见各行 note（价目表官方登记口径，峰时全价保守上界）；",
        "- 本工件所有数字可由 `python -m experiments.emse_stats_extensions` 零 LLM 逐位复算。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="统计报告规范补强（Wilson CI / 效应量 / 成本 bootstrap）")
    parser.add_argument("--stdout", action="store_true", help="只打印 markdown，不落盘")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
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
