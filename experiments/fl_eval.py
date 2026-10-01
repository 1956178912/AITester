"""
N6（2026-09-29 审查 P2）：FL 真值评测——用 golden_patch 做 ground truth，
输出 FL@k / MRR，使谱系故障定位（O2 fl_spectral）的阴性 A/B 可归因。

历史口径：O2 的 fl_spectral 模块能算 Ochiai Top-k 可疑函数，但**没有真值
对照**——"Top-1 命中 golden 函数" 的比例无法度量，阴性 A/B（fl_spectral
on vs off 对修复率的影响）无法归因到定位质量。

本模块提供：
- `evaluate_fl_spectral(top_k, golden_functions, all_functions)`:
  纯数据评测函数（零 LLM / 零 subprocess），接受 Ochiai 排序结果与
  golden patch 触及的函数名集合，输出 FL@k 命中数 / MRR / 命中率。
- `compute_fl_metrics_from_state(state, k=5)`:
  从工作流 final_state 提取 fl_spectral_focus（O2 写入）+
  golden_patch（task_metadata 或 state 字段），自动计算 FL@k/MRR，
  写入 state["fl_metrics"]（纯观测，不改路由）。

验收指标（N6）：FL@1/5/10 + MRR 可在 experiments/analyze_results.py
按 golden_patch 有无分组输出；阴性 A/B（fl_spectral on/off）的
MRR 差异可归因到定位质量而非修复策略。

用法：
    from experiments.fl_eval import evaluate_fl_spectral
    result = evaluate_fl_spectral(
        top_k=["calc_total", "calc_tax", "apply_discount"],
        golden_functions={"calc_tax"},
        all_functions=["calc_total", "calc_tax", "apply_discount", "render"],
        k_values=(1, 5, 10),
    )
    # result = {"FL@1": 0, "FL@5": 1, "FL@10": 1, "MRR": 0.5, ...}
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "compute_fl_metrics_from_state",
    "evaluate_fl_spectral",
]


def evaluate_fl_spectral(
    top_k: list[str],
    golden_functions: set[str] | list[str],
    all_functions: list[str] | None = None,
    k_values: tuple[int, ...] = (1, 5, 10),
) -> dict[str, Any]:
    """纯数据 FL 评测：Ochiai Top-k 排序 vs golden patch 触及函数。

    指标口径（与 SBFL 文献一致）：
    - FL@k：Top-k 内命中 golden 函数的数量（0..min(k, |golden|)）；
    - MRR（Mean Reciprocal Rank）：1/首个命中位置（0-based +1）；
      无命中 = 0.0；
    - hit_rate：|Top-k ∩ golden| / |golden|（golden 非空时）；
    - precision@k：|Top-k ∩ golden| / k（k ≤ |top_k| 时）。

    本函数是纯数据函数（零 LLM / 零 subprocess），可在 experiments/
    analyze_results.py 中对每个任务的 fl_spectral_focus 批量调用。

    Args:
        top_k: Ochiai 排序后的函数名列表（index 0 = 最可疑）。
            由 O2 fl_spectral.measure_fl_spectral_focus 产出。
        golden_functions: golden patch 触及的函数名集合（真值）。
            来源：task_metadata["golden_patch_functions"]（SWE-bench 场景
            从 gold diff 解析）或 state["golden_patch_functions"]。
            支持 set / list（内部转 set）。
        all_functions: 被测模块全部函数名（可选，用于计算召回率；
            None 时跳过 recall 指标）。
        k_values: 要输出的 FL@k 档位（默认 1/5/10）。

    Returns:
        指标 dict：
        - "FL@{k}": 每个 k 档位命中的 golden 函数数（int）；
        - "MRR": 首个命中的倒数排名（float，无命中 = 0.0）；
        - "hit_rate": |Top-k_max ∩ golden| / |golden|（float，golden 空 = 0.0）；
        - "precision@{k}": |Top-k ∩ golden| / k（每个 k 档位）；
        - "recall": |Top-|top_k| ∩ golden| / |golden|（all_functions 非 None 时）；
        - "top_k_len": 实际 Top-k 长度；
        - "golden_count": golden 函数数。
    """
    _golden_set = set(golden_functions) if golden_functions else set()
    _top_set = set(top_k)
    _hit_count_in_top = len(_top_set & _golden_set)
    result: dict[str, Any] = {
        "top_k_len": len(top_k),
        "golden_count": len(_golden_set),
    }

    # MRR：首个命中位置（1-based 倒数）；无命中 = 0.0
    mrr = 0.0
    if _golden_set:
        for i, fn in enumerate(top_k):
            if fn in _golden_set:
                mrr = 1.0 / (i + 1)
                break
    result["MRR"] = mrr

    # 各 k 档位指标
    _max_k = max(k_values) if k_values else 1
    _top_k_max = top_k[:_max_k]
    _hit_in_max = len(set(_top_k_max) & _golden_set)
    for k in k_values:
        _top_k_slice = top_k[:k]
        _hits = len(set(_top_k_slice) & _golden_set)
        result[f"FL@{k}"] = _hits
        result[f"precision@{k}"] = (_hits / k) if k > 0 else 0.0
    result["hit_rate"] = (_hit_in_max / len(_golden_set)) if _golden_set else 0.0

    # 召回率（all_functions 提供时）
    if all_functions is not None:
        _all_set = set(all_functions)
        result["recall"] = (len(_top_set & _golden_set) / len(_golden_set)) if _golden_set else 0.0
    return result


def compute_fl_metrics_from_state(
    state: dict[str, Any], k_values: tuple[int, ...] = (1, 5, 10)
) -> dict[str, Any] | None:
    """从工作流 final_state 提取 O2 fl_spectral_focus + golden 真值，
    计算 FL 指标（纯数据，零 LLM）。

    提取路径（按优先级）：
    1. state["fl_spectral_focus"]（O2 _debugger_node 写入，含
       "suspicious_functions": [{name, score, rank}, ...]）；
    2. state["golden_patch_functions"]（task_metadata 透传或
       实验层预置的 golden patch 触及函数名列表）；
    3. state["all_functions"]（被测模块全部函数名，可选）。

    任一关键输入缺失（fl_spectral_focus 为空 / golden 为空）时返回
    None（调用方按"指标不可用"处理，历史口径零变化）。

    Args:
        state: 工作流 final_state 字典。
        k_values: FL@k 档位（默认 1/5/10）。

    Returns:
        指标 dict（evaluate_fl_spectral 输出 + 输入元数据），或 None。
    """
    _fl_focus = state.get("fl_spectral_focus")
    if not _fl_focus:
        return None
    # O2 fl_spectral_focus 结构：{"suspicious_functions": [...], "top_k": int, ...}
    _susp = _fl_focus.get("suspicious_functions") or []
    if not _susp:
        return None
    _top_k = [item.get("name", "") for item in _susp if item.get("name")]
    _golden = state.get("golden_patch_functions")
    if not _golden:
        return None
    _all_fns = state.get("all_functions")

    _metrics = evaluate_fl_spectral(
        top_k=_top_k,
        golden_functions=set(_golden) if isinstance(_golden, list) else _golden,
        all_functions=_all_fns,
        k_values=k_values,
    )
    # 附加输入元数据（供实验层分组）
    _metrics["fl_spectral_top_k"] = _fl_focus.get("top_k")
    _metrics["golden_functions"] = list(_golden) if isinstance(_golden, (set, list)) else []
    return _metrics
