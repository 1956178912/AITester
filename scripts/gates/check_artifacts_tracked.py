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
    - 豁免登记本身受审计（CA 轮 2026-10-23）：目录消失 / 已全部入库 /
      目录为空 / 不可读 / 登记名不在扫描面内均判漂移并阻断；通过时逐条
      披露每条豁免遮蔽多少未入库工件（此前豁免只在抑制报错时被读取，
      遮蔽量与失效登记均不可见）。

用法：
    python scripts/gates/check_artifacts_tracked.py          # 审计，违规 exit 1
    python scripts/gates/check_artifacts_tracked.py --list   # 打印清单

CI 接线：ci.yml test 作业（仅 3.14 档，工件与 Python 版本无关）。
本地注意：工作树未提交时本守卫会红（这是预期——本地用 make gates
不含本步，入库前的强制项由 CI 承担）。
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
from pathlib import Path
from typing import NamedTuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# "报告 → 证据工件"引用链清单（相对仓库根）。新增引用新工件时同步登记。
MANIFEST: tuple[str, ...] = (
    # CI 轮第三批（2026-10-24）：用户指令清除 experiments/results/ 全部历史数据
    # （DeepSeek 重跑前），MANIFEST 全部条目随文件一并删除（「文件消失 ⇒ 删登记」，
    # 与 model-fingerprint 预指纹豁免表同逻辑）；机制保留，重跑生成新工件后
    # 由新的证据登记重建本表。
)

# 证据目录覆盖扫描的显式豁免登记（相对 experiments/results/）。
# 口径：冒烟批次 / 被更新批次取代 / 结论性数字经聚合报告入库的原始数据，
# 按项目"本地件"惯例保留工作树——但必须**显式登记理由**，禁止静默缺席
# （独立评审 A-04： silent gap 曾使四批旗舰工件脱离 git 而无人察觉）。
# T 轮（2026-10-18）扩展：扫描面从 emse_* 扩到所有轮次证据目录
# （`*_round_*`，如 q_round_/r_round_/s_round_/t_round_）——历史教训是
# "每次新轮次命名一种前缀，硬编码清单就再漏一次"。
# CA 轮（2026-10-23）：豁免只在"抑制报错"时被读取，从未被审计是否仍然
# 需要——登记过期（目录消失 / 已全部入库）与登记遮蔽量此前均不可见。
# 现由 exemption_coverage() 单源统计、exemption_drift_failures() 判漂移，
# 并删除本轮实测失效的两条（目录已不存在 / 53 个文件已全部入库）。
EVIDENCE_DIR_EXEMPTIONS: dict[str, str] = {
    # CI 轮第三批（2026-10-24）原表随数据清除清空；以下为 DeepSeek 重跑期新批：
    # 证据性批次但按用户口径暂不提交（工作树携带 CA-CI 轮未提交改动）；
    # 提交入库后「已全部入库」漂移判定会自动提醒移除这些登记。
    "emse_docstring_anchor_20261017": "2026-10-24 DeepSeek 重跑期材料目录（正式批被干净树门禁阻断，残留锚表批材料）；未提交 @experiments/run_docstring_anchor_batch.sh",
    "emse_docstring_augment_20261017": "2026-10-24 重跑期目录（正式批被干净树门禁阻断，preflight 残留）；未提交 @experiments/run_augment_batch.sh",
    "emse_oracle_enabled_validation_20261017": "2026-10-24 重跑期目录（材料探针 compiled_empty 阻断，PREFLIGHT 残留）；未提交 @experiments/run_oracle_validation_batch.sh",
    "emse_spec_anchor_20261016": "2026-10-24 自 LLM 缓存零成本重建的锚表；未提交 @experiments/build_spec_anchor_table.py",
    "p_round_b8_ablation_20261018": "2026-10-24 DeepSeek 重跑批（重跑 PREREG 已落盘）；未提交 @experiments/run_b8_ablation.sh",
}

# 向后兼容别名（T 轮前仅扫 emse_*；既有测试/调用方仍可用旧名）。
STUDY_DIR_EXEMPTIONS = EVIDENCE_DIR_EXEMPTIONS

# 证据目录扫描面（experiments/results/ 下按 glob 匹配；新增轮次前缀须在此登记，
# 否则下一轮证据目录又成静默缺口——T 轮把"新增前缀登记"本身变成必须动作）。
EVIDENCE_DIR_GLOBS: tuple[str, ...] = ("emse_*", "*_round_*")


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


class ExemptionCoverage(NamedTuple):
    """单条豁免登记的可审计状态（遮蔽量与是否仍然需要，同源计数）。

    用 NamedTuple 而非 dataclass：本模块被两个历史测试以
    `spec_from_file_location` 动态加载（模块未登记进 sys.modules），
    dataclass 在 Python 3.14 上会在装饰期访问 `sys.modules[cls.__module__]`
    而 AttributeError——门禁模块的可导入性是测试契约的一部分。
    """

    name: str
    status: str  # ok / missing / unreadable / empty / fully_tracked
    in_scan_surface: bool
    total_files: int
    tracked_files: int
    detail: str = ""

    @property
    def hidden_files(self) -> int:
        return self.total_files - self.tracked_files


def _in_scan_surface(name: str) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in EVIDENCE_DIR_GLOBS)


def exemption_coverage() -> list[ExemptionCoverage]:
    """统计每条豁免实际遮蔽多少未入库工件，并判定登记是否仍然有效。

    豁免此前只在"抑制报错"分支被读取（`if name in EVIDENCE_DIR_EXEMPTIONS:
    continue`），于是三种失效形态都无声：①目录已消失，登记成死条目；②目录
    已全部入库，豁免不再抑制任何东西；③登记名不在扫描面内，豁免永不生效。
    此外"豁免遮挡了多少未入库工件"本身从不披露——门禁通过时无法分辨
    "没有豁免"与"豁免遮蔽了上百个文件"。
    """
    results_root = PROJECT_ROOT / "experiments/results"
    rows: list[ExemptionCoverage] = []
    for name in sorted(EVIDENCE_DIR_EXEMPTIONS):
        surface = _in_scan_surface(name)
        directory = results_root / name
        if not directory.is_dir():
            rows.append(ExemptionCoverage(name, "missing", surface, 0, 0, "目录不存在"))
            continue
        try:
            files = sorted(path for path in directory.rglob("*") if path.is_file())
        except OSError as exc:  # 目录存在但不可遍历：豁免不可复核
            rows.append(ExemptionCoverage(name, "unreadable", surface, 0, 0, str(exc)))
            continue
        if not files:
            rows.append(ExemptionCoverage(name, "empty", surface, 0, 0, "目录内无文件"))
            continue
        rels = [path.relative_to(PROJECT_ROOT).as_posix() for path in files]
        ls = subprocess.run(["git", "ls-files", "--", *rels], cwd=PROJECT_ROOT, capture_output=True, text=True)
        if ls.returncode != 0:
            rows.append(
                ExemptionCoverage(name, "unreadable", surface, len(files), 0, f"git ls-files 失败: {ls.stderr.strip()}")
            )
            continue
        tracked = {line for line in ls.stdout.splitlines() if line.strip()}
        status = "fully_tracked" if len(tracked) == len(files) else "ok"
        rows.append(ExemptionCoverage(name, status, surface, len(files), len(tracked)))
    return rows


def exemption_drift_failures(rows: list[ExemptionCoverage] | None = None) -> list[tuple[str, str]]:
    """登记漂移：死条目 / 已全入库 / 目录为空 / 不可读 / 不在扫描面 → 失败。

    漂移与"是否存在未入库目录"独立判定（先于空扫描面分支），否则一个
    experiments/results 缺失的检出环境会让所有登记同时失去审计。
    """
    rows = exemption_coverage() if rows is None else rows
    failures: list[tuple[str, str]] = []
    for row in rows:
        if not row.in_scan_surface:
            failures.append((row.name, "豁免漂移（登记名不在 EVIDENCE_DIR_GLOBS 扫描面内，豁免永不生效）"))
        if row.status == "missing":
            failures.append((row.name, "豁免漂移（目录已不存在，登记应移除）"))
        elif row.status == "unreadable":
            failures.append((row.name, f"豁免漂移（无法审计：{row.detail}）"))
        elif row.status == "empty":
            failures.append((row.name, "豁免漂移（目录内无文件，豁免不遮蔽任何工件）"))
        elif row.status == "fully_tracked":
            failures.append((row.name, f"豁免漂移（{row.total_files}/{row.total_files} 个文件已全部入库，应移除登记）"))
    return failures


def _scan_evidence_dirs() -> list[tuple[str, str]]:
    """覆盖扫描：`experiments/results/` 下轮次证据目录必须入库或显式豁免。

    防"新结果目录静默缺席"复发（独立评审 A-04：四批旗舰工件曾 0 跟踪而无任何门禁察觉——
    MANIFEST 是硬编码白名单，天然不覆盖未来目录；T 轮进一步发现单靠
    `emse_*` 前缀也会漏掉 `q/r/s/t_round_*` 新命名）。

    口径：目录内**至少一个**文件被 git 跟踪即通过（可再生物/日志/缓存不入库
    是项目既有惯例）；整目录 0 跟踪才报错并要求 add -f 或登记豁免。
    """
    offenders: list[tuple[str, str]] = []
    results_root = PROJECT_ROOT / "experiments/results"
    if not results_root.is_dir():
        return offenders
    seen: set[str] = set()
    for pattern in EVIDENCE_DIR_GLOBS:
        for child in sorted(results_root.glob(pattern)):
            if not child.is_dir():
                continue
            rel = child.relative_to(PROJECT_ROOT).as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            name = child.name
            if name in EVIDENCE_DIR_EXEMPTIONS:
                continue
            ls = subprocess.run(["git", "ls-files", "--", rel], cwd=PROJECT_ROOT, capture_output=True, text=True)
            if ls.returncode != 0:
                offenders.append((rel, f"git ls-files 失败: {ls.stderr.strip()}"))
                continue
            if not ls.stdout.strip():
                offenders.append(
                    (
                        rel,
                        "整个目录 0 git 跟踪。若为证据性批次：git add -f 后提交；"
                        "若为冒烟/被取代批次：在 EVIDENCE_DIR_EXEMPTIONS 显式登记理由",
                    )
                )
    return offenders


def _scan_emse_dirs() -> list[tuple[str, str]]:
    """向后兼容别名：等价于 `_scan_evidence_dirs()`（仅 emse_* 时代的历史名）。"""
    return _scan_evidence_dirs()


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

    evidence_offenders = _scan_evidence_dirs()
    offenders.extend(evidence_offenders)

    coverage = exemption_coverage()
    drift = exemption_drift_failures(coverage)

    if offenders or drift:
        if offenders:
            print(f"✗ {len(offenders)} 个关键工件/目录未入库（引用链断裂，CI 阻断）：")
            for rel, reason in offenders:
                print(f"  - {rel}: {reason}")
            print("修复：git add <路径> 并随本批提交（预注册时间顺序审计的前提）。")
        if drift:
            print(f"✗ {len(drift)} 条证据目录豁免登记漂移（登记与实物不符，CI 阻断）：")
            for name, reason in drift:
                print(f"  - {name}: {reason}")
            print("修复：删除失效登记，或在 experiments/results/ 恢复对应目录后复核理由。")
        return 1
    print(
        f"✓ {len(MANIFEST)}/{len(MANIFEST)} 关键工件均已入库；"
        f"证据目录覆盖扫描通过（{'/'.join(EVIDENCE_DIR_GLOBS)}，引用链完整）"
    )
    active = [row for row in coverage if row.status == "ok"]
    hidden_total = sum(row.hidden_files for row in active)
    for row in active:
        print(f"  [EXEMPT] {row.name}: 遮蔽未入库工件 {row.hidden_files}/{row.total_files}")
    print(f"  豁免披露：{len(active)} 项有效登记共遮蔽未入库工件 {hidden_total} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
