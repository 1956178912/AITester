#!/usr/bin/env python3
"""AP1（2026-10-07 第十五轮审查续·AO5 后续）：E7 修复上限人工复核工作表生成器。

零 LLM 成本：消费与 repair_sample_selection.py 完全相同的抽样（抽样框
patch_plausible=1 修复循环行 → 分层 ceil(fraction)、seed 确定性），为每个
候选行组装"对照式"复核素材，把预注册 E7 的 ~1 人日人工比对压缩为逐节
填表：

- **生成补丁**（patch，整文件替换口径——补丁应用后即补丁正文）；
- **gold fixed**（task_metadata.fixed，参考答案）；
- **gold 官方测试**（task_metadata.test_cases）；
- **最终生成测试**（generated_test，检出裁决者）。

复核判定（预注册 E7 五选一，等价于 repair_sample_selection._REVIEW_RUBRIC）：
equivalent（语义等价，应判 repair——触发口径勘误）/ plausible_overfit /
wrong_location / test_only / incomplete。equivalent 占比 > 0 → repair 口径
存在低估须勘误并给修正上界；= 0 → repair=0 为真零（上限卡在合理性与
gold 正确性）。

判定提示（整文件替换口径）：将 patch 正文与 gold fixed 逐行对照——仅注释/
格式/docstring 差异 → equivalent；改写测试断言而非源码 → test_only；改动
不在缺陷函数/缺陷模式位置 → wrong_location；补丁引入但 gold 未采用的多余
防御分支且不改可观测行为 → plausible_overfit；未消除缺陷触发条件 → incomplete。

用法::

    python experiments/repair_review_worksheet.py \
        --results-dir experiments/results/main_batch \
        --fraction 0.10 --seed 42 \
        --output experiments/results/main_batch/e7_review_worksheet.md

输出：Markdown 工作表（默认 stdout；--output 指定路径时写文件）。
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.repair_sample_selection import (  # noqa: E402
    _DEFAULT_BATCHES,
    _REVIEW_RUBRIC,
    build_sampling_frame,
    select_stratified_sample,
    stratify,
)
from experiments.statistical_analysis import (  # noqa: E402
    load_experiment_results_with_sources,
)

_JUDGMENT_CHOICES = (
    "equivalent",
    "plausible_overfit",
    "wrong_location",
    "test_only",
    "incomplete",
)
_FENCE = "````"  # 四反引号围栏，防代码内容含 ``` 时破栏


def _code_block(lang: str, body: Any) -> str:
    """四反引号围栏代码块（body 为 None/空 → 占位说明行）。"""
    text = str(body) if body not in (None, "") else "（缺失——上游未产出该字段，按 incomplete 口径不受影响，仅记录）"
    return f"{_FENCE}{lang}\n{text}\n{_FENCE}\n"


def _patch_gold_diff(row: dict[str, Any]) -> str:
    """patch 正文 vs gold fixed 的 unified diff（机械对比备料，判定仍属人工）。

    整文件替换口径下 patch 正文即补丁应用后完整文件，与 gold fixed 的
    行级差异就是审阅者的核心判读对象；差异为空 → 逐行一致（大概率
    equivalent，但仍需人工确认语义）。LLM 输出格式伪影（如 patch 首行
    的语言标签）按原样参与 diff——它们本身就是证据的一部分。
    """
    patch_text = str(row.get("patch") or "")
    gold_text = str((row.get("task_metadata") or {}).get("fixed") or "")
    if not patch_text or not gold_text:
        return "（素材缺失，无法生成 diff——按上游字段缺失口径记录）"
    diff_lines = list(
        difflib.unified_diff(
            patch_text.splitlines(),
            gold_text.splitlines(),
            fromfile="patch（补丁应用后）",
            tofile="gold_fixed（参考答案）",
            lineterm="",
        )
    )
    if not diff_lines:
        return "patch 与 gold fixed 逐行一致（unified diff 为空）——大概率 equivalent，仍需人工确认语义等价。"
    return "\n".join(diff_lines)


def render_worksheet(
    selected: list[dict[str, Any]],
    source_files: list[str],
    fraction: float,
    seed: int,
) -> str:
    """E7 复核工作表 Markdown（素材全部来自上游字段，本函数零计算判定）。"""
    lines = [
        "# E7 修复上限人工复核工作表（AP1，2026-10-07）",
        "",
        f"- 数据来源（与 e7_repair_sample_candidates.md 同参同序）：{len(source_files)} 个批次",
        f"- 抽样参数：fraction={fraction:.0%}（每层 ceil 上取整）、seed={seed}（确定性，"
        "与候选清单同 seed 同参复算一致）",
        f"- 判定口径（预注册 E7 五选一）：{_REVIEW_RUBRIC}",
        "- 判定规则：equivalent 占比 > 0 → repair 口径存在低估，须勘误并给出修正后上界；"
        "= 0 → repair=0 为真零（上限卡在合理性与 gold 正确性）",
        '- 整文件替换口径提示：patch 正文即补丁应用后的完整文件——与 gold fixed 逐行对照；差异分类示例见各节"判定提示"',
        "",
    ]
    for idx, row in enumerate(selected, start=1):
        meta = row.get("task_metadata") or {}
        checks = " ".join(f"☐ {choice}" for choice in _JUDGMENT_CHOICES)
        lines += [
            f"## 候选 {idx}：{row.get('task_id')}",
            "",
            f"- 分层（evidence）：{row.get('_stratum')} ｜ stop_reason：{row.get('stop_reason')} "
            f"｜ error_category：{row.get('error_category')} ｜ iterations：{row.get('iterations')}",
            f"- 缺陷模式：{meta.get('pattern_name')}（bug_type={meta.get('bug_type')}，"
            f"difficulty={meta.get('difficulty')}）",
            f"- 人工判定：{checks}",
            "- 判定提示：patch vs gold fixed 逐行对照；仅注释/格式/docstring 差异 → equivalent；"
            "改写测试而非源码 → test_only；改动不在缺陷位置 → wrong_location；"
            "未消除触发条件 → incomplete",
            "",
            "### 生成补丁（patch）",
            _code_block("python", row.get("patch")),
            "### gold fixed（参考答案，task_metadata.fixed）",
            _code_block("python", meta.get("fixed")),
            "### gold 官方测试（task_metadata.test_cases）",
            _code_block("python", meta.get("test_cases")),
            "### 最终生成测试（generated_test，检出裁决者）",
            _code_block("python", row.get("generated_test")),
            "### patch vs gold fixed 逐行差异（AQ1 增补：difflib unified diff，机械对比——判定仍属人工）",
            _code_block("diff", _patch_gold_diff(row)),
        ]
    lines += [
        '复核完成后：把每行判定回填 e7_repair_sample_candidates.md 的"人工判定"列，'
        "按预注册判定规则更新 docs/preregistration.md 执行记录表 E7 行，并追记全局决策日志。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results-dir", default="experiments/results/main_batch")
    parser.add_argument(
        "--batches",
        default=",".join(_DEFAULT_BATCHES),
        help="批次白名单（逗号分隔，相对 results_dir；与候选清单同参）",
    )
    parser.add_argument("--pool-seeds", action="store_true", default=True, help="多种子拼接（默认开）")
    parser.add_argument("--fraction", type=float, default=0.10, help="每层抽样比例（默认 0.10）")
    parser.add_argument("--seed", type=int, default=42, help="确定性抽样种子（默认 42，与候选清单一致）")
    parser.add_argument("--output", default="-", help="输出路径（默认 - = stdout）")
    args = parser.parse_args()

    batch_files = [b.strip() for b in args.batches.split(",") if b.strip()]
    results, source_files = load_experiment_results_with_sources(
        args.results_dir, batch_files, allow_schema_mixed=False, pool_seeds=args.pool_seeds
    )
    aitester_rows = results.get("aitester") or []
    frame = build_sampling_frame(aitester_rows)
    if not frame:
        print("错误：抽样框为空（aitester 臂无 patch_plausible=1 的修复循环行）", file=sys.stderr)
        return 1

    strata = stratify(frame)
    selected = select_stratified_sample(strata, args.fraction, args.seed)
    report = render_worksheet(selected, source_files, args.fraction, args.seed)

    if args.output == "-":
        sys.stdout.write(report)
    else:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"已写入 {args.output}（{len(selected)} 候选节 / {len(frame)} 框行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
