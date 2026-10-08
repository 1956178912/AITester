#!/usr/bin/env python3
"""AK3（2026-10-06 第十二轮审查 R1）：主批次工件 git 入库守卫。

背景：
    R-P0-2 生死实验的批次工件（3 种子 JSON、两统计报告、MAST 分布
    报告、SHA256SUMS）与预注册文档曾长期处于 untracked 状态——
    statistical_report_3seed_pooled.md 曾声称"git_dirty=False"而工件
    实测 git_dirty=true，且 preregistration.md:24-25 的时间顺序审计
    条款（"入库 commit 必须早于"）在工件未入库时不可执行。本守卫
    把"关键工件必须入库"转为 CI 阻断项：报告引用的每一个证据工件
    都必须被 git 跟踪，否则引用链（报告 → 工件 → commit 时间序）
    断裂。

口径：
    - MANIFEST 为"报告直接引用的证据工件"白名单（新增报告引用新
      工件时同步登记——漏登记属新缺口，可在测试中锁定清单长度）；
    - 只做 git ls-files 存在性判定（零网络、纯本地，秒级）；
    - 文件缺失 / 未跟踪 / 被 .gitignore 忽略分别报错（忽略 = 永远
      不可能入库，需先修 .gitignore 白名单）。

用法：
    python scripts/check_artifacts_tracked.py          # 审计，违规 exit 1
    python scripts/check_artifacts_tracked.py --list   # 打印清单

CI 接线：ci.yml test 作业（仅 3.14 档，工件与 Python 版本无关）。
本地注意：工作树未提交时本守卫会红（这是预期——本地用 make gates
不含本步，入库前的强制项由 CI 承担）。
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# "报告 → 证据工件"引用链清单（相对仓库根）。新增引用新工件时同步登记。
MANIFEST: tuple[str, ...] = (
    # R-P0-2 生死实验三种子批次（statistical_report_3seed_pooled.md 数据来源）
    "experiments/results/main_batch/benchmark_synthetic_20261006_140906.json",
    "experiments/results/main_batch/benchmark_synthetic_20261006_151907.json",
    "experiments/results/main_batch/benchmark_synthetic_20261006_164357.json",
    # canonical 与 pooled 统计报告 + MAST 分布 + 修复上限归因（AK1 新增）
    "experiments/results/main_batch/statistical_report.md",
    "experiments/results/main_batch/statistical_report_3seed_pooled.md",
    "experiments/results/main_batch/mast_distribution_report.md",
    "experiments/results/main_batch/repair_ceiling_report.md",
    # E7 修复上限人工复核工件（AO5 候选清单 + AP1 工作表；AQ 批登记——
    # prereg 双语 E7 节引用的复核入口，入库前本守卫本地预期红）
    "experiments/results/main_batch/e7_repair_sample_candidates.md",
    "experiments/results/main_batch/e7_review_worksheet.md",
    # 完整性锚点与成本价目（$/task 口径依赖）
    "experiments/results/main_batch/SHA256SUMS",
    "experiments/price_table.json",
    # R14（2026-10-08 R2）：R4 / QuixBugs 存量批次入库（口径矩阵与勘误引用的
    # 证据链——此前全部滞留 /tmp，易失且违反预注册工件条款）
    "experiments/results/r4_batches/README.md",
    "experiments/results/r4_batches/SHA256SUMS",
    "experiments/results/r4_batches/r4_ab_arm_a/benchmark_synthetic_20261008_133303.json",
    "experiments/results/r4_batches/r4_ab_arm_b/benchmark_synthetic_20261008_134156.json",
    "experiments/results/r4_batches/r4_synth_arm_b2/benchmark_synthetic_20261008_161508.json",
    "experiments/results/r4_batches/r4_qb_arm_a/benchmark_quixbugs_20261008_165558.json",
    "experiments/results/r4_batches/r4_qb_arm_b/benchmark_quixbugs_20261008_165603.json",
    "experiments/results/r4_batches/loc_test_quix/benchmark_quixbugs_20261007_195728.json",
    # 预注册（时间顺序审计条款的执行前提）
    "docs/preregistration.md",
    "docs/preregistration.en.md",
)


def _is_tracked(path: Path) -> tuple[bool, str]:
    """返回 (是否被 git 跟踪, 状态说明)。缺失 / 未跟踪 / 被忽略分别可辨。"""
    if not path.exists():
        return False, "文件不存在（路径拼写错误或未生成）"
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    ls = subprocess.run(["git", "ls-files", "--", rel], cwd=PROJECT_ROOT, capture_output=True, text=True)
    if ls.returncode != 0:
        return False, f"git ls-files 失败: {ls.stderr.strip()}"
    if ls.stdout.strip():
        return True, ""
    check_ignore = subprocess.run(["git", "check-ignore", "-q", rel], cwd=PROJECT_ROOT, capture_output=True, text=True)
    if check_ignore.returncode == 0:
        return False, "被 .gitignore 忽略（永远无法入库——先修白名单）"
    return False, "存在于工作区但未被 git 跟踪（git add 后提交）"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="主批次工件 git 入库守卫（AK3）")
    parser.add_argument("--list", action="store_true", help="仅打印清单后退出")
    args = parser.parse_args(argv)

    if args.list:
        for rel in MANIFEST:
            print(rel)
        return 0

    offenders: list[tuple[str, str]] = []
    for rel in MANIFEST:
        tracked, reason = _is_tracked(PROJECT_ROOT / rel)
        if not tracked:
            offenders.append((rel, reason))

    if offenders:
        print(f"✗ {len(offenders)}/{len(MANIFEST)} 个关键工件未入库（引用链断裂，CI 阻断）：")
        for rel, reason in offenders:
            print(f"  - {rel}: {reason}")
        print("修复：git add <路径> 并随本批提交（预注册时间顺序审计的前提）。")
        return 1
    print(f"✓ {len(MANIFEST)}/{len(MANIFEST)} 关键工件均已入库（引用链完整）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
