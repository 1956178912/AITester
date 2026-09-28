"""
模型能力梯度实验（3.3 模型能力边界量化分离，Design-only 编排器）。

背景：
    failure_analysis 反复强调"0/7 失败归因基于免费档小模型（agnes-3.0-flash），
    而非架构局限；使用更强模型时失败分类与数量预计显著变化"。本脚本提供一个
    轻量级"模型能力梯度实验"编排器，把"架构能力 vs 模型能力"的边界从定性判断
    变为定量参照。

设计约束（保守，默认不自动执行）：
    - **默认不自动执行**：本脚本是人工触发的编排器（消耗真实 LLM token），
      默认行为不改变任何运行时代码路径；
    - **不新增 LLM 调用路径**：仅编排既有的 `experiments/run_benchmark.py`
      调用（每个模型档位一次 benchmark 批次），记录并汇总三核心指标；
    - **选 5-10 个代表性任务 × 2-3 个模型档位**：代表性任务取自合成数据集
      的难度分层（level2/level3，含跨文件双模块），档位经
      `--tier-models` 显式指定（config 中 cost_weight / model_name 区分的
      2-3 个 LLM_N_* 端点）；
    - **三核心指标**：`llm_applied` 比例、首次修复成功率（iteration==1 且
      passed）、平均迭代次数；结果以表格沉淀到
      `experiments/results/model_gradient.md`。

使用方式（人工触发，需真实 LLM key）：
    # 1. 准备 2-3 个模型档位端点（.env.local 中 LLM_1_* / LLM_2_* / LLM_3_*）
    # 2. 运行梯度实验（--task-count 5-10，--tiers 2-3 个端点名）
    python experiments/model_gradient.py \
        --task-count 8 \
        --tiers agnes-flash,agnes-plus \
        --output-dir experiments/results/model_gradient

    # 档位端点名映射：experiments/model_gradient.py --list-tiers 列出
    # LLM_CONFIGS 中可用的 (model_name, cost_weight) 组合。

结果表沉淀：
    - experiments/results/model_gradient/<run_ts>_per_tier/<tier>.json
      （各档位 benchmark 原始结果）
    - experiments/results/model_gradient/model_gradient.md
      （汇总表 + 指标定义 + 实验口径说明，人工复核后归档）
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import LLM_CONFIGS  # noqa: E402

RESULT_DIR = os.path.join(PROJECT_ROOT, "experiments", "results", "model_gradient")


def _load_tier_configs() -> list[dict[str, int | float | str | None]]:
    """返回 LLM_CONFIGS 中可用的档位信息（model_name + cost_weight + 端点索引）。

    模型"档位"的保守口径：以 `cost_weight`（.env.local 的 LLM_N_COST_WEIGHT
    或 llm_configs.json 注入）区分——低 cost_weight = 免费/低成本档，
    高 cost_weight = 更强/更贵档。同 model_name 多 provider 端点场景下，
    各端点作为独立档位候选。
    """
    tiers: list[dict[str, int | float | str | None]] = []
    for idx, cfg in enumerate(LLM_CONFIGS, start=1):
        tiers.append(
            {
                "index": idx,
                "model_name": str(getattr(cfg, "model_name", None) or "model"),
                "cost_weight": float(getattr(cfg, "cost_weight", 1.0) or 1.0),
                "provider": getattr(cfg, "provider", None),
            }
        )
    return tiers


def _first_attempt_success_rate(details: list[dict[str, object]]) -> float:
    """首次修复成功率：iteration == 1 且 passed 的任务占比（保守口径）。

    无 iteration / passed 字段的历史 JSON 条目按"未记录"跳过，不贡献分母。
    """
    recorded = [d for d in details if isinstance(d.get("iterations"), int) and d.get("passed") is not None]
    if not recorded:
        return 0.0
    first_success = sum(1 for d in recorded if d.get("iterations") == 1 and d.get("passed"))
    return first_success / len(recorded)


def _avg_iterations(details: list[dict[str, object]]) -> float:
    """平均迭代次数（非数值 / 缺失字段跳过，保守口径）。"""
    vals: list[float] = []
    for d in details:
        it = d.get("iterations")
        if isinstance(it, (int, float)):
            vals.append(float(it))
    return (sum(vals) / len(vals)) if vals else 0.0


def _llm_applied_ratio(details: list[dict[str, object]]) -> float | None:
    """`llm_applied` 比例：repo_verification.llm_applied 为 True 的任务占比。

    `repo_verification` 仅在 `--save-state` 落盘的 raw 工件中携带
    （run_benchmark._dump_state_artifacts），标准结果 JSON 的 details[] 不含
    该键——此时返回 None（不适用口径），仅仓库级验证批次（REPO_LEVEL_EXECUTION
    + SWE-bench）经 raw 工件产出该指标。
    """
    marked = [
        d
        for d in details
        if isinstance(d, dict) and isinstance(d.get("repo_verification"), dict)  # type: ignore[union-attr]
    ]
    if not marked:
        return None
    applied = 0
    for d in marked:
        rv = d.get("repo_verification")
        if isinstance(rv, dict) and rv.get("llm_applied") is True:
            applied += 1
    return applied / len(marked)


def _extract_baseline_details(result_json: Path, baseline: str) -> list[dict[str, object]]:
    """从 benchmark 结果 JSON 提取某基线的所有任务 details（缺省键兜底）。"""
    with open(result_json, encoding="utf-8") as f:
        data = json.load(f)
    results = data.get("results", {}) if isinstance(data, dict) else {}
    baseline_data = results.get(baseline, {})
    details = baseline_data.get("details", [])
    return details if isinstance(details, list) else []


def _tier_label(tier: dict[str, int | float | str | None]) -> str:
    """档位标签：model_name + cost_weight（同 model_name 多端点时加 index）。"""
    name = str(tier.get("model_name") or "model")
    weight = tier.get("cost_weight")
    label = f"{name}_cw{weight}" if weight is not None else name
    if len(str(label)) <= 40:
        return label
    return f"tier{tier.get('index')}_{label[:30]}"


def _render_markdown(
    run_ts: str,
    task_count: int,
    dataset: str,
    difficulty: str,
    tier_metrics: list[dict[str, object]],
) -> str:
    """渲染模型梯度汇总表（model_gradient.md）。

    表格含各档位的三核心指标 + 总 token 消耗（若结果 JSON 携带），
    便于"架构 vs 模型"边界的定量参照。
    """
    lines = [
        "# 模型能力梯度实验结果（model_gradient）",
        "",
        f"> 生成时间：{run_ts}",
        f"> 数据集：{dataset}（difficulty={difficulty}，task_count={task_count}）",
        "> 指标定义：",
        "> - **首次修复成功率**：iteration == 1 且 passed 的任务占比（保守口径，未记录 iteration 的任务不入分母）",
        "> - **平均迭代次数**：各任务 iterations 均值（非数值跳过）",
        "> - **llm_applied 比例**：repo_verification.llm_applied 为 True 的任务占比（仅仓库级验证批次，单文件批次 N/A）",
        "> - **总 token 消耗**：该档位全任务的 total_tokens 合计（若结果 JSON 携带）",
        "",
        "| 模型档位 | 首次修复成功率 | 平均迭代次数 | llm_applied 比例 | 总 token 消耗 | 备注 |",
        "|----------|----------------|--------------|------------------|---------------|------|",
    ]
    for m in tier_metrics:
        applied = m.get("llm_applied_ratio")
        applied_str = "N/A" if applied is None else f"{applied:.2%}"
        tokens = m.get("total_tokens")
        tokens_str = str(int(tokens)) if isinstance(tokens, (int, float)) else "N/A"
        note = m.get("note", "")
        lines.append(
            f"| {m.get('tier')} | {m.get('first_success_rate', 0.0):.2%} "
            f"| {m.get('avg_iterations', 0.0):.2f} | {applied_str} | {tokens_str} | {note} |"
        )
    lines += [
        "",
        "## 解读口径",
        "",
        "- 各档位若成功率 / 迭代数 / token 差异显著，说明当前结果受模型能力边界约束（架构能力已到位，瓶颈在引擎）；",
        "- 若各档位指标接近（强模型未带来增益），说明瓶颈在架构 / 数据管道而非模型，应优先改进架构；",
        "- 本表为**定量参照**，不改变各档位的默认开关与历史实验口径。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    """模型能力梯度实验入口（人工触发，不自动执行）。"""
    parser = argparse.ArgumentParser(
        description="模型能力梯度实验编排器：选 5-10 个代表性任务 × 2-3 个模型档位，"
        "记录 llm_applied 比例 / 首次修复成功率 / 平均迭代次数，沉淀 model_gradient.md。"
    )
    parser.add_argument("--task-count", type=int, default=8, help="代表性任务数（建议 5-10）")
    parser.add_argument("--dataset", default="synthetic", help="数据集名（默认 synthetic）")
    parser.add_argument("--difficulty", default="level3", help="难度分层（默认 level3，含跨文件双模块）")
    parser.add_argument("--tiers", default=None, help="档位标签，逗号分隔（按 LLM_CONFIGS 顺序的 index，如 1,2）")
    parser.add_argument("--list-tiers", action="store_true", help="列出可用档位后退出")
    parser.add_argument("--output-dir", default=RESULT_DIR, help="结果输出目录")
    parser.add_argument("--baseline", default="aitester", help="统计基线（默认 aitester）")
    parser.add_argument(
        "--no-run", action="store_true", help="仅汇总已有结果 JSON，不跑新 benchmark（--analyze-only 口径）"
    )
    args = parser.parse_args()

    # ── 列出可用档位 ────────────────────────────────────────────────────────
    if args.list_tiers:
        print("可用模型档位（LLM_CONFIGS 端点，档位以 cost_weight 区分）：")
        for tier in _load_tier_configs():
            print(
                f"  index={tier['index']} model={tier['model_name']} "
                f"cost_weight={tier['cost_weight']} provider={tier['provider']}"
            )
        print("\n用 --tiers 1,2,3 指定档位 index（.env.local 的 LLM_N_* 端点序号）。")
        return 0

    tier_indices = [int(x) for x in args.tiers.split(",") if x.strip()] if args.tiers else []
    if not args.no_run and not tier_indices:
        print("错误：需 --tiers 指定 2-3 个档位 index（或 --no-run 仅汇总）。用 --list-tiers 查看可用档位。")
        return 1
    if not args.no_run and (len(tier_indices) < 2 or len(tier_indices) > 3):
        print("口径建议：--tiers 指定 2-3 个档位（轻量级梯度实验，控制 token 成本）。")
        return 1

    all_tiers = _load_tier_configs()
    tier_map: dict[int, dict[str, int | float | str | None]] = {}
    for t in all_tiers:
        idx = t.get("index")
        if isinstance(idx, int):
            tier_map[idx] = t

    os.makedirs(args.output_dir, exist_ok=True)
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    per_tier_dir = os.path.join(args.output_dir, f"{run_ts}_per_tier")
    os.makedirs(per_tier_dir, exist_ok=True)

    tier_metrics: list[dict[str, object]] = []
    current_tier_json: Path | None = None
    for idx in tier_indices:
        tier_opt = tier_map.get(idx)
        if tier_opt is None:
            print(f"警告：档位 index={idx} 不在 LLM_CONFIGS（共 {len(all_tiers)} 端点），跳过")
            continue
        tier_resolved: dict[str, int | float | str | None] = tier_opt
        label = _tier_label(tier_resolved)
        current_tier_json = Path(per_tier_dir) / f"{label}.json"
        if not args.no_run:
            # 编排既有 run_benchmark：该档位端点经 LLM_N_* 环境变量指定，
            # 其余端点关闭（单档位跑，避免轮询混档）
            print(f"── 跑档位 {label}（index={idx}，task_count={args.task_count}）")
            env = os.environ.copy()
            # 仅保留该档位端点的 LLM_N_* 变量（按 config.py 扫描口径 LLM_N_API_KEY 等）
            for k in list(env.keys()):
                if k.startswith("LLM_") and f"_{idx}_" not in k and not k.startswith(f"LLM_{idx}_"):
                    del env[k]
            cmd = [
                sys.executable,
                os.path.join(PROJECT_ROOT, "experiments", "run_benchmark.py"),
                "--dataset",
                args.dataset,
                "--task-count",
                str(args.task_count),
                "--difficulty",
                args.difficulty,
                "--baselines",
                args.baseline,
                "--output-dir",
                str(Path(per_tier_dir) / f"{label}_out"),
            ]
            proc = subprocess.run(cmd, env=env, cwd=PROJECT_ROOT)
            if proc.returncode != 0:
                print(f"警告：档位 {label} benchmark 退出码 {proc.returncode}，跳过该档位")
                continue
            # run_benchmark 产出 benchmark_*.json，取该 out 目录最新一个
            out_dir = Path(per_tier_dir) / f"{label}_out"
            candidates = sorted(out_dir.glob("benchmark_*.json"))
            if not candidates:
                print(f"警告：档位 {label} 无结果 JSON（{out_dir}），跳过")
                continue
            current_tier_json = candidates[-1]
        elif not current_tier_json.exists():
            # --no-run 口径：结果 JSON 需在 per_tier_dir 预置（<label>.json）
            print(f"警告：--no-run 但 {current_tier_json.name} 不存在，跳过该档位")
            continue

        details = _extract_baseline_details(current_tier_json, args.baseline)
        total_tokens = 0
        for d in details:
            tu = d.get("token_usage")
            if isinstance(tu, dict):
                total_tokens += int(tu.get("total_tokens", 0) or 0)
        m: dict[str, object] = {
            "tier": label,
            "index": idx,
            "first_success_rate": _first_attempt_success_rate(details),
            "avg_iterations": _avg_iterations(details),
            "llm_applied_ratio": _llm_applied_ratio(details),
            "total_tokens": total_tokens,
            "task_count": len(details),
            "source": str(current_tier_json),
        }
        if not args.no_run:
            m["note"] = "本次新跑"
        else:
            m["note"] = "已有结果（--no-run 汇总）"
        tier_metrics.append(m)
        print(f"   ✓ {label}：{m['task_count']} 任务已记录")

    if not tier_metrics:
        print("无有效档位数据（检查 --tiers / .env.local 端点配置）。")
        return 1

    # 沉淀结果表
    md = _render_markdown(run_ts, args.task_count, args.dataset, args.difficulty, tier_metrics)
    md_path = Path(args.output_dir) / "model_gradient.md"
    md_path.write_text(md, encoding="utf-8")
    # 同步一份到 experiments/results/（人工复核后归档口径）
    canonical = Path(os.path.join(PROJECT_ROOT, "experiments", "results", "model_gradient.md"))
    canonical.write_text(md, encoding="utf-8")

    print(f"\n模型梯度汇总已沉淀：{md_path}")
    print(f"归档副本：{canonical}")
    print("请人工复核各档位指标差异后，把结论链接到 docs/failure_analysis.md 快照更新约定处。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
