"""
position_aware_focus A/B 对比实验脚本（评估 2026-09-25 §3.3 剩余工作）。

用途：
    跑 position_aware_focus（位置感知迭代修复）ON/OFF 对比，
    分析"先定位后补丁"策略对修复成功率 / 修复轮次 / 定位正确率
    的影响，为论文提供实验数据。

设计口径（保守、零 LLM 成本）：
    - ON 组：`POSITION_AWARE_REPAIR_ENABLE=true`（先定位后补丁，
      traceback 行号 + AST 定位"包围异常行的最短区间函数"）；
    - OFF 组：`POSITION_AWARE_REPAIR_ENABLE=false`（历史全文件修复口径）；
    - 指标：成功率 delta + 平均迭代 delta + 定位正确率
      （state["position_aware_focus"]["function_name"] 命中
      gold suggested_function 的比例，仅 ON 组有意义）；
    - 输出 Markdown 汇总（供论文引用）+ JSON 原始数据。

2026-10 改进（A/B 阴性结果驱动）：
    - 新增 --difficulty 参数（默认 "level2.5"）：此前硬编码 "mixed"，
      混合难度下 assertion 类缺陷占比高、traceback 行号缺失，位置感知
      定位阶段从未被激活（定位命中 0/30）。level2.5 数据集（运行时
      异常缺陷库：IndexError/KeyError/AttributeError/TypeError）保证
      每个任务失败时携带 traceback 帧行号，使定位阶段可被激活。
    - 定位正确率金标准：SyntheticDataset 已写入 metadata["suggested_function"]
      （缺陷所在函数），_locate_accuracy 据此计算命中比例。

BO（2026-10-22）读侧口径：
    raw/<task_id>/aitester.json 由 `--save-state` 决定存不存在，而改前
    "raw 目录缺席 / 任务件缺席 / 件不可读 / 没有 position_aware_focus 键"
    四种**没测到**都返回 0.0，与"测了、确实一次没命中"逐字节同形（复放见
    scripts/tools/bo_raw_readside_fold_probe.py C 段：四腿塌成同一个 0.0）。
    第五种折叠更隐蔽：BN 起白名单恒写 focus 键，值为 null = 定位环节没记录，
    改前只要该行有修复轮次/补丁就**进分母记成一次未命中**（"没测"折进"测了且
    跑偏"，压低读数）。现由 _locate_stats 给出分档（grade + 跳过明细），
    _locate_accuracy 保留为兼容层：可计算给百分数，不可计算给既有的 -1.0 档，
    绝不再用 0.0 冒充读数。
    口径改动不动历史：C2 段普查 8 个归档臂 236 行环节件——键不存在 0 例、
    值 null 156 例、有内容 80 例，而 156 例 null **全部**既无 iterations 也无
    patch（本就落"未激活"剔除腿），故八臂读数与跳过明细逐位相同。

使用方式：
    # 在 level2.5（运行时异常缺陷）上跑位置感知 A/B（推荐，定位可激活）
    python experiments/position_aware_ab.py --dataset synthetic --task-count 30 --difficulty level2.5
    # 历史口径（mixed 难度，定位大概率不激活，仅作对照）
    python experiments/position_aware_ab.py --dataset synthetic --task-count 30 --difficulty mixed
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run_one_arm(
    dataset_name: str,
    task_limit: int | None,
    task_count: int | None,
    subset: str | None,
    output_dir: str,
    position_aware_on: bool,
    difficulty: str = "level2.5",
) -> dict[str, Any]:
    """跑一组（位置感知 ON 或 OFF）benchmark，返回汇总 dict。

    Args:
        dataset_name: 数据集名。
        task_limit: 任务数上限。
        task_count: 合成数据集任务数。
        subset: 数据子集。
        output_dir: 结果输出目录。
        position_aware_on: 是否启用位置感知修复。
        difficulty: 合成数据集难度级别（默认 level2.5，运行时异常缺陷库）。

    Returns:
        benchmark 汇总 dict。
    """
    from experiments.run_benchmark import run_benchmark

    prev = os.environ.get("POSITION_AWARE_REPAIR_ENABLE")
    try:
        os.environ["POSITION_AWARE_REPAIR_ENABLE"] = "true" if position_aware_on else "false"
        summary = run_benchmark(
            dataset_name=dataset_name,
            subset=subset,
            baselines=["aitester"],
            output_dir=output_dir,
            verbose=False,
            task_limit=task_limit,
            task_count=task_count,
            parallel=None,
            seed=42,
            enable_rag=False,
            save_state=True,  # 需 save_state 才能拿到 position_aware_focus 状态
            enable_mutation_scoring=False,
            difficulty=difficulty,
        )
    finally:
        if prev is not None:
            os.environ["POSITION_AWARE_REPAIR_ENABLE"] = prev
        else:
            os.environ.pop("POSITION_AWARE_REPAIR_ENABLE", None)
    return summary


def _success_rate(summary: dict[str, Any]) -> float:
    """aitester 基线成功率。"""
    for baseline, bl in summary.get("results", {}).items():
        if baseline != "aitester":
            continue
        total = bl.get("total_functions", 0)
        passed = bl.get("passed_count", 0)
        return round(passed / total * 100, 2) if total > 0 else 0.0
    return 0.0


def _avg_iterations(summary: dict[str, Any]) -> float:
    """aitester 基线平均迭代次数。"""
    for baseline, bl in summary.get("results", {}).items():
        if baseline != "aitester":
            continue
        return float(bl.get("avg_iterations") or 0.0)
    return 0.0


# 读数分档 → 人读文本（BO，2026-10-22）。改前"raw 不可用"与"实测 0%"共用同一
# 个 0.0 与同一句 `0.0%`，读者无从区分"定位全都跑偏"与"根本没落盘所以没测"。
# -1.0 这个数值档是既有的「不可计算」（历史只表示"未激活"），本轮由 grade 细分
# 语义，数值档本身不改（scripts/tools/bo_raw_readside_fold_probe.py C 段实测：
# 8 个归档臂的 raw 里 position_aware_focus 键全部在场，故新口径重放逐位相同）。
_GRADE_TEXT = {
    "measured": None,
    "not_repaired": "未激活（无修复轮次）",
    "focus_key_absent": "不可计算（环节件里没有 position_aware_focus 键）",
    "focus_not_recorded": "不可计算（position_aware_focus 落的是 null：定位环节没记录，"
    "但该行确有修复轮次/补丁 ⇒ 不能记成实测未命中）",
    "state_file_absent": "不可计算（raw/<task_id>/aitester.json 不存在）",
    "state_unreadable": "不可计算（环节级工件不可读）",
    "raw_dir_absent": "不可计算（raw 目录缺席：跑批未加 --save-state 或 raw 未随归档留存）",
    "details_unavailable": "不可计算（批次 JSON 里没有可遍历的 details）",
    "no_samples": "不可计算（details 为空）",
    "row_unusable": "不可计算（details 行不含可用 task_id）",
}


def _locate_stats(output_dir: str, summary: dict[str, Any]) -> dict[str, Any]:
    """定位命中率的读数面 + 覆盖度自证（BO，2026-10-22）。

    分母只收"确有定位证据"的任务：raw 件不可用、`position_aware_focus` 键不
    存在、无修复轮次，一律**不进分母也不记为未命中**，而是按原因计数。缺席
    只做披露，不做归因（也不做"0%"）。

    Returns:
        `{"grade", "accuracy_pct", "n_details", "n_used", "n_hit", "skipped":{}}`；
        grade == "measured" 时 accuracy_pct 为百分数，否则为 -1.0（不可计算），
        具体为何不可计算由 grade 点名。
    """
    skipped: Counter[str] = Counter()
    stats: dict[str, Any] = {
        "grade": "measured",
        "accuracy_pct": -1.0,
        "n_details": 0,
        "n_used": 0,
        "n_hit": 0,
        "skipped": skipped,
    }
    raw_dir = os.path.join(output_dir, "raw")
    if not os.path.isdir(raw_dir):
        stats["grade"] = "raw_dir_absent"
        return stats
    # 逐 task 读取：details 是 aitester 基线结果列表（每项含 task_id）；
    # 兼容 details 缺失 / 非 list 两种旧 JSON 形态（不可计算，不崩溃、不冒充 0%）。
    details = summary.get("results", {}).get("aitester", {}).get("details")
    if not isinstance(details, list):
        stats["grade"] = "details_unavailable"
        return stats
    stats["n_details"] = len(details)
    if not details:
        stats["grade"] = "no_samples"
        return stats
    total = 0
    hit = 0
    for row in details:
        if not isinstance(row, dict):
            skipped["row_unusable"] += 1
            continue
        task_id = row.get("task_id")
        if not task_id:
            skipped["row_unusable"] += 1
            continue
        state_file = os.path.join(raw_dir, task_id, "aitester.json")
        if not os.path.exists(state_file):
            skipped["state_file_absent"] += 1
            continue
        try:
            with open(state_file, encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            skipped["state_unreadable"] += 1
            continue
        if not isinstance(state, dict):
            skipped["state_unreadable"] += 1
            continue
        # BO：BN 起 raw 白名单恒写该键，"键在"不等于"记录过"。键不存在、值为
        # null 都是定位环节根本没留证据 ⇒ 不进分母、不记为未命中。
        if "position_aware_focus" not in state:
            skipped["focus_key_absent"] += 1
            continue
        focus = state.get("position_aware_focus")
        # 2026-10 改进：区分"定位未执行"（无修复轮次/开关关闭，focused 缺失且
        # iterations=0）与"定位激活但未命中"（focused=False 但 iterations>0）——
        # 后者计入分母，前者剔除。"无修复"口径：iterations=0/None 且无 patch。
        _repaired = bool(row.get("iterations")) or bool(row.get("patch"))
        if focus is None:
            # 未修复行仍按既有"未激活"口径剔除（归档八臂的跳过明细因此逐字节同形：
            # 236 行里 156 行该键为 null，这些行全部既无 iterations 也无 patch）；
            # **已修复却无记录**的行改前会落到下面进分母、被计成一次实测未命中
            # （"没测"折进"测了且跑偏"，压低定位读数），现单独点名。
            skipped["not_repaired" if not _repaired else "focus_not_recorded"] += 1
            continue
        if (not focus or not focus.get("focused")) and not _repaired:
            skipped["not_repaired"] += 1
            continue
        total += 1
        # 2026-10 改进：gold 定位目标两级取值——
        # 1. 优先 state["task_metadata"]["suggested_function"]（任务级 gold）；
        # 2. 缺失时取 summary 行内嵌的 task_metadata（run_benchmark 的
        #    details 项），兼容 save_state 未携带 task_metadata 的旧布局。
        gold = (state.get("task_metadata") or {}).get("suggested_function")
        if not gold:
            gold = (row.get("task_metadata") or {}).get("suggested_function")
        located = focus.get("function_name")
        if gold and located and located == gold and focus.get("focused"):
            hit += 1
    stats["n_used"] = total
    stats["n_hit"] = hit
    stats["skipped"] = dict(skipped)
    if total == 0:
        # 无激活样本：命中率为"不可计算"档（-1.0），grade 点名是哪一种缺席。
        # 优先级显式列出（不靠 _GRADE_TEXT 的字典序）：件级缺席比键级缺席更根本。
        for reason in (
            "state_file_absent",
            "state_unreadable",
            "focus_key_absent",
            "focus_not_recorded",
            "row_unusable",
            "not_repaired",
        ):
            if skipped.get(reason):
                stats["grade"] = reason
                break
        else:
            stats["grade"] = "no_samples"
        return stats
    stats["grade"] = "measured"
    stats["accuracy_pct"] = round(hit / total * 100, 2)
    return stats


def _locate_accuracy(output_dir: str, summary: dict[str, Any]) -> float:
    """定位正确率兼容层：命中 gold suggested_function 的百分数，不可计算时 -1.0。

    仅 ON 组有意义（OFF 组 position_aware_focus 恒 focused=False，正确率 0.0）。
    读数由 raw/<task_id>/aitester.json 提供——**为何**读不到请用 `_locate_stats`，
    本层刻意把九种"不可计算"压成一个数，只为不拆既有消费方。
    """
    return _locate_stats(output_dir, summary)["accuracy_pct"]


def _locate_text(stats: dict[str, Any]) -> str:
    """定位读数渲染：可计算给百分数，不可计算点名是哪一种缺席。"""
    grade = stats.get("grade", "measured")
    if grade == "measured":
        return f"{stats.get('accuracy_pct')}%"
    skipped = stats.get("skipped") or {}
    reason = _GRADE_TEXT.get(grade, "不可计算（环节级工件不可用）")
    if grade == "not_repaired":
        return reason
    return f"{reason}；分母 {stats.get('n_used', 0)} 例 / 跳过 {sum(skipped.values())} 例"


def _render_markdown(
    on_summary: dict[str, Any],
    off_summary: dict[str, Any],
    on_dir: str,
    off_dir: str,
    output_dir: str,
    difficulty: str = "level2.5",
) -> str:
    """渲染位置感知 A/B 对比 Markdown。"""
    on_rate = _success_rate(on_summary)
    off_rate = _success_rate(off_summary)
    on_iter = _avg_iterations(on_summary)
    off_iter = _avg_iterations(off_summary)
    on_stats = _locate_stats(on_dir, on_summary)
    off_stats = _locate_stats(off_dir, off_summary)
    on_locate = on_stats["accuracy_pct"]
    off_locate = off_stats["accuracy_pct"]
    rate_delta = round(on_rate - off_rate, 2)
    iter_delta = round(on_iter - off_iter, 2)
    # 2026-10 改进：定位命中率 -1 表示"不可计算"（无激活样本，或环节级工件
    # 不可用），渲染层按 grade 点名具体是哪一种，不再统一显示成 0%。
    on_locate_txt = _locate_text(on_stats)
    off_locate_txt = _locate_text(off_stats)

    lines = [
        "# position_aware_focus A/B 对比汇总",
        "",
        f"- 数据集: {on_summary.get('dataset', '?')} (subset={on_summary.get('subset', 'None')})",
        f"- 难度: {difficulty}（level2.5 = 运行时异常缺陷库，定位阶段可被激活）",
        f"- ON 组（位置感知启用）成功率: {on_rate}%",
        f"- OFF 组（位置感知关闭）成功率: {off_rate}%",
        f"- 成功率 delta (ON - OFF): {rate_delta:+.2f}pp",
        f"- 平均迭代 ON: {on_iter:.2f} / OFF: {off_iter:.2f}（delta {iter_delta:+.2f}）",
        f"- 定位正确率（ON 组 focused 命中 gold function）: {on_locate_txt}",
        f"- 定位正确率（OFF 组，恒 0 或未激活）: {off_locate_txt}",
        f"- 定位读数覆盖度 ON: 分母 {on_stats['n_used']} 例 / details {on_stats['n_details']} 例，跳过 {on_stats['skipped']}",
        f"- 定位读数覆盖度 OFF: 分母 {off_stats['n_used']} 例 / details {off_stats['n_details']} 例，跳过 {off_stats['skipped']}",
        "",
        "## 解读",
        "",
    ]
    if rate_delta > 0:
        lines.append(f"- 位置感知修复带来 {rate_delta:+.2f}pp 成功率提升。")
    elif rate_delta < 0:
        lines.append(f"- 位置感知修复导致 {abs(rate_delta):.2f}pp 成功率下降（需排查定位误判）。")
    else:
        lines.append("- 位置感知修复未改变成功率（样本量小时结论保守解读）。")
    if iter_delta < 0:
        lines.append(f"- 平均迭代下降 {abs(iter_delta):.2f}（定位正确时减少无效修复轮次）。")
    elif iter_delta > 0:
        lines.append(f"- 平均迭代上升 {iter_delta:.2f}（定位引入额外定位开销或误判）。")

    md_path = os.path.join(output_dir, "position_aware_ab_summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    json_path = os.path.join(output_dir, "position_aware_ab_raw.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "difficulty": difficulty,
                "on": {
                    "success_rate": on_rate,
                    "avg_iterations": on_iter,
                    "locate_accuracy_pct": on_locate,
                    # BO（2026-10-22）：读数之外带上"这批读数到底覆盖了多少任务"——
                    # locate_accuracy_pct 单独一个数无法自证它是测出来的还是没测到。
                    "locate": on_stats,
                },
                "off": {
                    "success_rate": off_rate,
                    "avg_iterations": off_iter,
                    "locate_accuracy_pct": off_locate,
                    "locate": off_stats,
                },
                "rate_delta_pp": rate_delta,
                "iter_delta": iter_delta,
            },
            f,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    print(f"[A/B] 汇总已写入: {md_path}")
    print(f"[A/B] 原始数据: {json_path}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="position_aware_focus A/B 对比实验")
    parser.add_argument("--dataset", default="examples", help="数据集名称（默认 examples）")
    parser.add_argument("--subset", default=None, help="数据子集")
    parser.add_argument("--task-limit", type=int, default=None, help="每组任务数上限")
    parser.add_argument("--task-count", type=int, default=None, help="合成数据集任务数")
    parser.add_argument(
        "--difficulty",
        default="level2.5",
        help="合成数据集难度级别（默认 level2.5：运行时异常缺陷库，定位阶段可被激活；"
        "level2.5-hard：困难运行时异常库（缺陷藏更深，小样本首跑即修复的天花板已抬高）；"
        "mixed 为历史口径，定位大概率不激活）",
    )
    parser.add_argument(
        "--output-dir", default=os.path.join(PROJECT_ROOT, "experiments", "results"), help="结果输出目录"
    )
    args = parser.parse_args()

    on_dir = os.path.join(args.output_dir, "position_aware_on")
    off_dir = os.path.join(args.output_dir, "position_aware_off")
    os.makedirs(on_dir, exist_ok=True)
    os.makedirs(off_dir, exist_ok=True)

    print(f"[A/B] 数据集 {args.dataset} 难度 {args.difficulty}，跑 OFF 组（位置感知关闭，历史全文件修复口径）...")
    off_summary = _run_one_arm(
        dataset_name=args.dataset,
        task_limit=args.task_limit,
        task_count=args.task_count,
        subset=args.subset,
        output_dir=off_dir,
        position_aware_on=False,
        difficulty=args.difficulty,
    )

    print("[A/B] 跑 ON 组（位置感知启用）...")
    on_summary = _run_one_arm(
        dataset_name=args.dataset,
        task_limit=args.task_limit,
        task_count=args.task_count,
        subset=args.subset,
        output_dir=on_dir,
        position_aware_on=True,
        difficulty=args.difficulty,
    )

    _render_markdown(on_summary, off_summary, on_dir, off_dir, args.output_dir, difficulty=args.difficulty)
    return 0


if __name__ == "__main__":
    sys.exit(main())
