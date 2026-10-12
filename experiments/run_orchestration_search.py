"""编排自动搜索（bandit）实验驱动——P1-A 落地（ADR-0016 后续方向）。

用法（M1 设计集：synthetic 12 任务 × 3 种子，串行，预算双顶）：

    ORCHESTRATION_SEARCH_ENABLE=true \
    python experiments/run_orchestration_search.py \
        --task-count 12 --seeds 42,43,44 --max-pattern-repeat 2

职责（规格 §7，与 src/graph/orchestration_search.py 分工）：
- 数据集加载与 cell 构建（每种子一份 synthetic 数据集 → (task, seed) 单元）；
- 干净基线（全部已知臂 env 键压 false，finally 恢复 ambient 快照）；
- 确定性采样（复用 run_benchmark._apply_deterministic_temperature 三处级联）；
- 结构化追踪目录（AITESTER_TRACE_DIR）与 LLM 缓存命名空间隔离；
- 串行搜索循环（OrchestrationSearch；M1 禁用并行——env 补丁进程全局）；
- Hindsight credit 归因（**仅诊断**：在驱动侧消费信用函数，主循环不引用——
  防 reward hacking，ADR-0016 教训）；
- 落盘：search_result.json（全量数据）+ attribution_report.md（人读报告）。

纪律：
- 主开关 ORCHESTRATION_SEARCH_ENABLE 默认 false——未开启时本驱动拒绝运行
  （退出码 2），对既有实验/CLI 流程零侵入（ADR-0003）；
- 本任务范围内只以桩评估器打通测试路径（见 tests/），不烧真实 LLM 预算；
  Stage-2 确认批（champion vs plain_llm_df，n=87×3）另行走 run_benchmark
  并前置 collect_model_fingerprint 版本钉住（浮动别名前科，S29）。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

# 确保项目根目录在路径中（与 experiments/run_benchmark.py 同口径：直接
# `python experiments/run_orchestration_search.py` 运行时 cwd 不在 sys.path）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.graph.orchestration_search import (  # noqa: E402
    ARM_REGISTRY,
    Cell,
    CellResult,
    OrchestrationSearch,
    SearchBudget,
    attribute_mechanisms,
    establish_clean_baseline,
    hindsight_credits,
    restore_env_snapshot,
    run_arm_cell,
    search_enabled,
)

logger = logging.getLogger(__name__)

# M1 设计集默认口径（与 R-P0-2 对齐：同数据集同 max_pattern_repeat，种子即
# 数据集生成种子；12 任务 × 3 种子 = 36 cell）
_DEFAULT_TASK_COUNT = 12
_DEFAULT_SEEDS = "42,43,44"
_DEFAULT_MAX_PATTERN_REPEAT = 2
_DEFAULT_DIFFICULTY = "mixed"


def _parse_seeds(spec: str) -> list[int]:
    """解析种子列表（"42,43,44" → [42, 43, 44]；坏值整体报错）。"""
    seeds: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            seeds.append(int(part))
        except ValueError as e:
            raise argparse.ArgumentTypeError(f"种子 {part!r} 不是整数（--seeds 形如 '42,43,44'）") from e
    if not seeds:
        raise argparse.ArgumentTypeError("--seeds 不能为空")
    return seeds


def load_design_set_cells(
    *,
    task_count: int,
    seeds: list[int],
    difficulty: str,
    max_pattern_repeat: int | None,
) -> list[Cell]:
    """构建设计集 cell 列表（每种子一份 synthetic 数据集）。

    Args:
        task_count: 每种子任务数（M1 默认 12）。
        seeds: 数据集生成种子列表（M1 默认 {42, 43, 44}）。
        difficulty: 合成数据集分层难度（默认 mixed）。
        max_pattern_repeat: 同池同模板重复上限（None = 历史口径）。

    Returns:
        Cell 列表（长度 = task_count × len(seeds)；(task_id, seed) 唯一）。
    """
    from src.datasets.synthetic_dataset import SyntheticDataset

    cells: list[Cell] = []
    seen: set[tuple[str, int]] = set()
    for seed in seeds:
        dataset = SyntheticDataset(
            task_count=task_count, seed=seed, difficulty=difficulty, max_pattern_repeat=max_pattern_repeat
        )
        for task in dataset.tasks:
            key = (str(task.task_id), seed)
            if key in seen:
                logger.warning("设计集去重：跳过重复 cell (task=%s, seed=%d)", key[0], key[1])
                continue
            seen.add(key)
            cells.append(Cell(task_id=str(task.task_id), seed=seed, task=task))
    logger.info("设计集构建完成：%d 任务/种子 × %d 种子 = %d cell", task_count, len(seeds), len(cells))
    return cells


def _build_attribution(
    captured: dict[tuple[str, str, int], CellResult],
    arms_by_id: dict,
) -> dict[str, dict[str, float]]:
    """Hindsight credit 机制归因（**仅诊断**；驱动侧消费，主循环不引用）。

    Args:
        captured: {(arm_id, task_id, seed): CellResult}（驱动侧 evaluator 捕获）。
        arms_by_id: {arm_id: ArmSpec}（机制激活判定）。

    Returns:
        {机制名: {"count": 出现次数, "mean_credit": 均值, "total_credit": 合计}}。
    """
    per_mechanism: dict[str, list[float]] = defaultdict(list)
    for (arm_id, _task_id, _seed), result in captured.items():
        if not result.trace_records:
            continue
        credits = hindsight_credits(result.trace_records, result.detection)
        mechanism_credits = attribute_mechanisms(result.trace_records, arms_by_id[arm_id], credits)
        for mechanism, credit in mechanism_credits.items():
            per_mechanism[mechanism].append(credit)
    return {
        mechanism: {
            "count": len(values),
            "mean_credit": round(sum(values) / len(values), 6),
            "total_credit": round(sum(values), 6),
        }
        for mechanism, values in sorted(per_mechanism.items())
    }


def _render_attribution_md(report: dict, attribution: dict[str, dict[str, float]], meta: dict) -> str:
    """渲染人读归因报告（markdown）。"""
    lines: list[str] = []
    lines.append(f"# 编排自动搜索归因报告（{meta['run_id']}）")
    lines.append("")
    lines.append("## 实验口径")
    lines.append("")
    lines.append(f"- 设计集：synthetic {meta['task_count']} 任务 × 种子 {meta['seeds']} = {report['config']['n_cells']} cell")
    lines.append(f"- 臂空间：{report['config']['n_arms']} 臂（M1 精选；全因子上界 3072）")
    lines.append(f"- 预算：max_evals={report['budget']['max_evals']} / max_tokens={report['budget']['max_total_tokens']}")
    lines.append(
        f"- 实际：evals={report['budget']['evals_used']} / tokens={report['budget']['tokens_used']}"
        f" / stop_reason={report['budget']['stop_reason']}"
    )
    lines.append(f"- UCB1：c={report['config']['ucb_c']}，search_seed={report['config']['seed']}")
    lines.append(f"- 确定性：serial + temp=0.0 + cache_namespace={meta['cache_namespace']}")
    lines.append("")
    lines.append("## 逐臂结果（主奖励 = M1 detection，gold 独立裁决；None 不进分母）")
    lines.append("")
    lines.append("| 臂 | n可测 | n不可测 | mean detection | SE | mean tokens | mean false_fix | repair_any | 退出原因 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for arm_id, stats in report["arm_stats"].items():
        lines.append(
            f"| {arm_id} | {stats['n_measurable']} | {stats['unmeasurable']} | {stats['mean_detection']:.4f} "
            f"| {stats['se_detection']:.4f} | {stats['mean_tokens']:.0f} | {stats['mean_false_fix']:.4f} "
            f"| {stats['repair_any']} | {stats['excluded_reason'] or '-'} |"
        )
    lines.append("")
    lines.append("## champion 选拔")
    lines.append("")
    lines.append(f"- champion：{report['champion']}")
    lines.append(f"- 依据：{report['champion_reason']}")
    lines.append("- 约束：mean tokens ≤ 2× df_incumbent 且 mean false_fix ≤ 0.5；无臂过约束 = 阴性结果（按 ADR-0016 可发表）")
    lines.append("")
    lines.append("## 机制归因（hindsight credit——**仅诊断，不进臂选择**）")
    lines.append("")
    if attribution:
        lines.append("| 机制 | 出现次数 | mean credit | total credit |")
        lines.append("|---|---|---|---|")
        for mechanism, stats in attribution.items():
            lines.append(f"| {mechanism} | {stats['count']} | {stats['mean_credit']:.4f} | {stats['total_credit']:.4f} |")
    else:
        lines.append("（无 trace 记录可归因——AITESTER_TRACE_DIR 未启用或全部评估无 trace）")
    lines.append("")
    lines.append("## 已知口径说明")
    lines.append("")
    lines.append("- hindsight credit 只回答「哪些机制的步骤在推进问题解决」，**不参与 UCB 臂选择**（防 reward hacking）；")
    lines.append("- 抹红通道（red_then_green ∧ detection=0）中 debugger/patch 步骤仍获 hindsight 正信用——步骤级公式不可见终局抹红，")
    lines.append("  该判据由 final_state 级旗标（detection_first_status / red_regression_violation）单独陈述；")
    lines.append("- detection=None（无 gold 材料/无生成物/执行超时）不进臂统计，但预算计数照记；")
    lines.append("- Stage-2 确认（champion vs plain_llm_df，n=87×3）须前置 collect_model_fingerprint 版本钉住。")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。

    Args:
        argv: 参数列表（None = 读 sys.argv）。

    Returns:
        进程退出码（0 = 正常完成；2 = 主开关未开启）。
    """
    parser = argparse.ArgumentParser(
        prog="run_orchestration_search",
        description="编排自动搜索（bandit）——BOAD 式自动发现编排配置（P1-A / ADR-0016）",
    )
    parser.add_argument("--task-count", type=int, default=_DEFAULT_TASK_COUNT, help="每种子任务数（默认 12）")
    parser.add_argument("--seeds", type=str, default=_DEFAULT_SEEDS, help="数据集生成种子（逗号分隔，默认 '42,43,44'）")
    parser.add_argument("--difficulty", type=str, default=_DEFAULT_DIFFICULTY, help="合成数据集分层难度（默认 mixed）")
    parser.add_argument(
        "--max-pattern-repeat", type=int, default=_DEFAULT_MAX_PATTERN_REPEAT, help="同池同模板重复上限（默认 2；0/负 = 历史口径 None）"
    )
    parser.add_argument("--output-dir", type=str, default="experiments/results", help="结果输出根目录")
    parser.add_argument("--max-evals", type=int, default=None, help="总评估次数硬顶（默认读 config.ORCHESTRATION_SEARCH_MAX_EVALS）")
    parser.add_argument("--max-tokens", type=int, default=None, help="总 token 硬顶（默认读 config.ORCHESTRATION_SEARCH_MAX_TOTAL_TOKENS）")
    parser.add_argument("--ucb-c", type=float, default=None, help="UCB1 探索常数（默认读 config.ORCHESTRATION_SEARCH_UCB_C）")
    parser.add_argument("--search-seed", type=int, default=None, help="搜索种子（默认读 config.ORCHESTRATION_SEARCH_SEED）")
    args = parser.parse_args(argv)

    # 主开关守卫（默认 false：拒绝运行，退出码 2——对既有流程零侵入）
    if not search_enabled():
        print(
            "ORCHESTRATION_SEARCH_ENABLE 未开启（默认 false）——编排自动搜索为实验 harness 能力，"
            "显式设 true 后才允许运行（ADR-0003 默认关口径）"
        )
        return 2

    import config as _config
    from experiments.run_benchmark import _apply_deterministic_temperature

    seeds = _parse_seeds(args.seeds)
    max_pattern_repeat = args.max_pattern_repeat if args.max_pattern_repeat and args.max_pattern_repeat >= 1 else None
    ucb_c = args.ucb_c if args.ucb_c is not None else _config.ORCHESTRATION_SEARCH_UCB_C
    search_seed = args.search_seed if args.search_seed is not None else _config.ORCHESTRATION_SEARCH_SEED
    max_evals = args.max_evals if args.max_evals is not None else _config.ORCHESTRATION_SEARCH_MAX_EVALS
    max_tokens = args.max_tokens if args.max_tokens is not None else _config.ORCHESTRATION_SEARCH_MAX_TOTAL_TOKENS

    # 输出目录与运行标识（缓存命名空间按 search_seed 稳定：同 seed 重跑命中缓存）
    run_id = f"orchestration_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir = os.path.join(args.output_dir, run_id)
    trace_dir = os.path.join(out_dir, "traces")
    cache_namespace = f"orch_search_s{search_seed}"
    os.makedirs(trace_dir, exist_ok=True)

    # 确定性采样（三处级联 temp=0.0，与 R-P0-2 口径一致）
    _apply_deterministic_temperature()
    # 结构化追踪 + 缓存命名空间（搜索专用，不污染其他实验）
    os.environ["AITESTER_TRACE_DIR"] = trace_dir
    os.environ["AITESTER_CACHE_NAMESPACE"] = cache_namespace

    # 干净基线：全部已知臂 env 键压 false（与 ambient profile 解耦），finally 恢复
    env_snapshot = establish_clean_baseline()
    ambient = {
        "AITESTER_PROFILE": os.getenv("AITESTER_PROFILE"),
        "arm_env_ambient": {k: v for k, v in env_snapshot.items()},
        "temperature": os.getenv("TEMPERATURE"),
        "cache_namespace": cache_namespace,
        "trace_dir": trace_dir,
    }
    logger.info("编排搜索启动：%s（臂 %d，预算 evals≤%d / tokens≤%d，UCB c=%.2f，seed=%d）", run_id, len(ARM_REGISTRY), max_evals, max_tokens, ucb_c, search_seed)

    exit_code = 0
    try:
        cells = load_design_set_cells(
            task_count=args.task_count,
            seeds=seeds,
            difficulty=args.difficulty,
            max_pattern_repeat=max_pattern_repeat,
        )
        if not cells:
            # 文案避让：`--task-count` 连字符拼写含 "sk-c" 片段，会触发
            # scripts/gates/audit_log_redaction.py 的 sk- 前缀密钥正则
            # （安全门宁误报勿漏报，故此处用下划线拼写规避而非放宽门禁）
            logger.error("设计集为空——检查任务数（task_count）与种子（seeds）参数")
            return 1

        # 驱动侧 evaluator：真实 LLM 路径 + trace 记录捕获（供归因报告消费）
        captured: dict[tuple[str, str, int], CellResult] = {}

        def _evaluator(arm, cell: Cell) -> CellResult:
            result = run_arm_cell(arm, cell, trace_dir=trace_dir)
            captured[(arm.arm_id, cell.task_id, cell.seed)] = result
            return result

        budget = SearchBudget(max_evals=max_evals, max_total_tokens=max_tokens)
        search = OrchestrationSearch(
            arms=ARM_REGISTRY,
            cells=cells,
            budget=budget,
            ucb_c=ucb_c,
            seed=search_seed,
            evaluator=_evaluator,
            trace_dir=trace_dir,
        )
        started = time.time()
        report = search.run()
        report["provenance"] = {
            "run_id": run_id,
            "task_count": args.task_count,
            "seeds": seeds,
            "difficulty": args.difficulty,
            "max_pattern_repeat": max_pattern_repeat,
            "ambient_env": ambient,
            "wall_time_s": round(time.time() - started, 3),
        }

        # Hindsight credit 归因（仅诊断；驱动侧消费信用函数，主循环不引用）
        arms_by_id = {arm.arm_id: arm for arm in ARM_REGISTRY}
        attribution = _build_attribution(captured, arms_by_id)
        report["mechanism_attribution"] = attribution

        # 落盘：全量数据 JSON + 人读报告 md
        result_path = os.path.join(out_dir, "search_result.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        md_path = os.path.join(out_dir, "attribution_report.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(
                _render_attribution_md(
                    report,
                    attribution,
                    meta={
                        "run_id": run_id,
                        "task_count": args.task_count,
                        "seeds": seeds,
                        "cache_namespace": cache_namespace,
                    },
                )
            )
        logger.info(
            "编排搜索完成：champion=%s（%s）；stop=%s；工件 %s / %s",
            report["champion"],
            report["champion_reason"],
            report["budget"]["stop_reason"],
            result_path,
            md_path,
        )
        print(json.dumps({"champion": report["champion"], "budget": report["budget"], "result": result_path}, ensure_ascii=False))
    except Exception:
        logger.exception("编排搜索执行失败")
        exit_code = 1
    finally:
        restore_env_snapshot(env_snapshot)
        # 注意：TEMPERATURE 三处级联与 AITESTER_TRACE_DIR/CACHE_NAMESPACE 为
        # 进程级设置（实验驱动一次性进程，退出即消散）；env_snapshot 只覆盖
        # 臂开关键（干净基线纪律的恢复范围）
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
