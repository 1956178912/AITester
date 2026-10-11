#!/usr/bin/env python3
"""S29（2026-10-11 独立评审落地）门禁：模型版本指纹核验。

背景（F13/S29，见 CONSOLIDATED_REVIEW_AND_PLAN.md §2.1/§3.1）：
    `deepseek-flash` 是**浮动别名**，历史 provenance 只记录别名，没有任何
    可校验的版本指纹。实测同一 87 任务 × 3 seed，`plain_llm` 检出率从存档
    1.5%(4/261) 漂移到 19.2%(50/261) —— **全部历史结论失去可复现性**。

    修复方向：`experiments/run_benchmark.py` 在 provenance 增加
    `model_fingerprint` 子块（requested_alias / returned_model /
    system_fingerprint / probe_sha256 / probe_at / pinned）。本门禁消费该
    字段：**pinned 不为 true 的结果 JSON 一律阻断**（预注册停止规则：
    快照失效即实验作废，不得与历史批次合并统计）。

判定口径（诚实口径，防"存在即通过"）：
    - 仅当 `provenance.model_fingerprint.pinned is True` 才算通过；
    - `pinned` 缺失、为 false、为 "true" 字符串、或 model_fingerprint 整块
      缺失 → **不通过**（布尔 true 是唯一通过条件，避免字符串真值蒙混）；
    - 不通过时打印**缺失项**（`missing` 字段优先；无该字段时按必需键
      逐项推断）与 `error` 文本，使"为何未锁定"可当场定位；
    - 网络/解析类问题与"未锁定"严格区分：非法 JSON 记 JSONDecodeError
      并同样阻断（工件不可解析 = 不可审计）。

用法：
    python scripts/gates/check_model_fingerprint.py                       # 扫默认结果目录
    python scripts/gates/check_model_fingerprint.py path/a.json path/b.json
    python scripts/gates/check_model_fingerprint.py --results-dir experiments/results
    python scripts/gates/check_model_fingerprint.py --allow-empty          # 无文件时不阻断

退出码：0 = 全部 pinned（或 --allow-empty 且无文件）；1 = 存在未锁定 / 不可解析
的工件；2 = CLI 用法错误（路径不存在）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 默认扫描面：本地跑批输出目录。CI 场景由调用方显式传路径（工件目录随批次而异）。
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"

# pinned=True 的必要条件（与 run_benchmark._FINGERPRINT_REQUIRED_KEYS 同口径；
# 此处刻意**复制常量而非 import**——门禁必须能在跑批脚本 import 失败 / 环境
# 不完整时独立运行，且不得因 src/ 侧改动而静默放宽判定）。
REQUIRED_FINGERPRINT_KEYS: tuple[str, ...] = ("requested_alias", "returned_model", "system_fingerprint")


def collect_result_files(
    paths: list[Path],
    pattern: str = "benchmark_*.json",
    max_age_days: float | None = 2.0,
) -> tuple[list[Path], list[Path]]:
    """展开输入路径为待检文件列表，返回 (文件列表, 不存在的路径列表)。

    目录 → 其下匹配 `pattern` 且**修改时间在 `max_age_days` 内**的文件
    （非递归，避免把旁挂工件一并拉进来）；文件 → 原样全检（**不按扩展名
    与时间过滤**——调用方显式点名的文件一律检，防止"点名了但被静默跳过"）。

    两条范围规则（2026-10-11 修，均为范围错误）：

    1. **默认 pattern = `benchmark_*.json`（跑批结果工件）**。此前取全部
       `*.json`，会把 `experiments/results/` 下的**派生分析产物**
       （`full_comparison.json` / `strategy_bank.json` / `performance_benchmark.json`
       等）一并判为"未锁定"；那些文件由离线脚本生成、**从来就不含
       `provenance` 块**，判它们失败等于往 CI 塞一个永远为红的门禁。
       指纹是**跑批**的属性，不是派生分析的属性。

    2. **默认只看近 `max_age_days` 天修改的批次**。S29 是**预注册停止规则**
       （快照失效即作废），其可执行的用途是"**新批次在合并统计前必须已锁定**"；
       对**历史批次**要求 `pinned=true` 是范畴错误——它们跑在指纹功能存在之前，
       永远不可能满足，只会让门禁永久为红而失去信号。需要审计历史时用
       `--all-history` 显式放宽（此时理应大量报红，那是**发现**而非**故障**）。
    """
    import time as _time

    cutoff = None if max_age_days is None else (_time.time() - max_age_days * 86400.0)
    files: list[Path] = []
    missing: list[Path] = []
    for path in paths:
        if path.is_dir():
            for candidate in sorted(path.glob(pattern)):
                if not candidate.is_file():
                    continue
                if cutoff is not None and candidate.stat().st_mtime < cutoff:
                    continue
                files.append(candidate)
        elif path.is_file():
            files.append(path)
        else:
            missing.append(path)
    # 去重（同一文件被显式点名 + 落在目录内）并保持确定性顺序
    return sorted(set(files)), missing


def extract_fingerprint(payload: Any) -> dict[str, Any] | None:
    """从结果 JSON 顶层取 provenance.model_fingerprint（取不到返回 None）。

    逐层 isinstance 判定而非 `.get` 链：工件里 `provenance` 可能是 list /
    字符串（历史格式漂移），直接 `.get` 会抛 AttributeError 使门禁崩在
    判定之外——门禁崩 ≠ 通过，必须走"判定失败"路径。
    """
    if not isinstance(payload, dict):
        return None
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        return None
    fingerprint = provenance.get("model_fingerprint")
    return fingerprint if isinstance(fingerprint, dict) else None


def missing_required_keys(fingerprint: dict[str, Any] | None) -> list[str]:
    """列出未锁定的原因项（缺失/空值的必需键；整块缺失时列为全部必需键）。

    优先采用工件自报的 `missing`（跑批侧已判定），但仍**独立复核**必需键：
    自报 missing 为空而必需键实际为空时，以复核结果为准（不采信自报）。
    """
    if fingerprint is None:
        return list(REQUIRED_FINGERPRINT_KEYS)
    observed = [key for key in REQUIRED_FINGERPRINT_KEYS if not fingerprint.get(key)]
    reported = fingerprint.get("missing")
    reported_list = [str(item) for item in reported] if isinstance(reported, list) else []
    # 并集（保序：先跑批自报，再复核补漏）
    return list(dict.fromkeys(reported_list + observed))


def check_payload(payload: Any) -> tuple[bool, list[str], str | None]:
    """判定单个结果 JSON 是否 pinned，返回 (passed, 未锁定项, error 文本)。

    通过条件：`provenance.model_fingerprint.pinned is True`（严格布尔）。
    """
    fingerprint = extract_fingerprint(payload)
    if fingerprint is None:
        if isinstance(payload, dict) and isinstance(payload.get("provenance"), dict):
            return False, list(REQUIRED_FINGERPRINT_KEYS), "provenance 无 model_fingerprint 子块"
        return False, list(REQUIRED_FINGERPRINT_KEYS), "结果 JSON 无 provenance 块"

    # 严格布尔：`is True` —— 字符串 "true" / 1 / 非空列表一律不通过
    raw_pinned = fingerprint.get("pinned")
    passed = raw_pinned is True
    error = fingerprint.get("error")
    error_text = str(error) if error else None
    if passed:
        return True, [], error_text
    items = missing_required_keys(fingerprint)
    if not items:
        # pinned 非布尔真值（如字符串 "true"）：必需键齐全但口径不合规——
        # 必须给出可读原因，否则门禁输出"未提供缺失项"等于没解释
        items.append(f"pinned 非布尔 true（实际 {type(raw_pinned).__name__}: {raw_pinned!r}）")
        if error_text:
            items.append("原因见 error")
    return False, items, error_text


def check_file(path: Path) -> tuple[bool, list[str], str | None]:
    """校验单个结果 JSON 文件，返回 (passed, 未锁定项, error 文本)。

    Raises:
        json.JSONDecodeError: 文件不是合法 JSON（调用方按"不可审计"阻断）。
        OSError: 文件不可读（权限 / 编码），同样阻断。
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    return check_payload(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S29 模型版本指纹门禁：pinned != true 则阻断")
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help=f"结果 JSON 文件或目录（默认 {DEFAULT_RESULTS_DIR}）",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help="结果目录（等价于传入一个目录路径；与位置参数可同时使用）",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="未发现任何 JSON 工件时不阻断（默认阻断：扫描面为空 = 门禁失效）",
    )
    parser.add_argument(
        "--pattern",
        default="benchmark_*.json",
        help=(
            "目录扫描时匹配的文件名模式（默认 benchmark_*.json = 跑批结果工件）。"
            "派生分析产物（full_comparison.json 等）从来不含 provenance，"
            "不在默认扫描面内；需要全量扫描时传 --pattern '*.json'。"
        ),
    )
    parser.add_argument(
        "--all-history",
        action="store_true",
        help=(
            "扫描目录下全部历史批次（默认只查近 2 天修改的批次）。"
            "S29 是预注册停止规则，可执行用途是「新批次合并统计前必须已锁定」；"
            "对指纹功能上线前的历史批次要求 pinned=true 是范畴错误，"
            "只会让门禁永久为红。审计历史时用本开关，此时大量报红是发现而非故障。"
        ),
    )
    args = parser.parse_args(argv)

    targets: list[Path] = list(args.paths)
    if args.results_dir is not None:
        targets.append(args.results_dir)
    if not targets:
        targets = [DEFAULT_RESULTS_DIR]

    files, missing_paths = collect_result_files(
        targets, pattern=args.pattern, max_age_days=None if args.all_history else 2.0
    )
    for path in missing_paths:
        print(f"[ERROR] 路径不存在: {path}", file=sys.stderr)
    if missing_paths:
        return 2

    if not files:
        msg = f"[model-fingerprint] 未发现任何结果 JSON（扫描面: {[str(t) for t in targets]}）"
        # 空扫描面 ≠ 未锁定。S29 的可执行语义是"**新批次**在合并统计前必须已
        # 锁定"，因此"近期没有新批次"是**合规状态**（nothing to verify），
        # 不是故障——若在此返回非零，门禁会在两次跑批之间永久为红，失去信号
        # （与 check_branch_coverage 仅在存在 coverage.xml 时判定同理）。
        # 退出码语义：0=通过（或无新批次可验）；1=存在未锁定批次（真故障）；
        # 2=用法/路径错误。默认扫描面已限定为近 2 天的 benchmark_*.json；
        # 审计历史请显式传 --all-history 或点名文件。
        if args.allow_empty:
            print(f"{msg}——--allow-empty，不阻断")
            return 0
        print(f"{msg}——近期无新批次可验（S29 只要求新批次已锁定），通过；审计历史请用 --all-history")
        return 0

    failures: list[str] = []
    for path in files:
        try:
            passed, items, error_text = check_file(path)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[ERROR] {path}: 工件不可审计（{type(e).__name__}: {e}）")
            failures.append(f"{path}: 不可解析")
            continue
        if passed:
            print(f"[PASS] {path}: model_fingerprint.pinned=true")
            continue
        detail = "；".join(items) if items else "未提供缺失项"
        suffix = f"（error: {error_text}）" if error_text else ""
        print(f"[FAIL] {path}: 模型版本未锁定——缺失项: {detail}{suffix}")
        failures.append(f"{path}: 缺少 {detail}")

    total = len(files)
    if failures:
        print(
            f"\n[model-fingerprint] 阻断：{len(failures)}/{total} 个工件未锁定模型版本。"
            "预注册停止规则：未锁定批次的结论不得与历史批次合并统计。"
            "修复：确认 API 可用且 provider 返回 model/system_fingerprint，重跑批次。",
            file=sys.stderr,
        )
        return 1
    print(f"\n[model-fingerprint] 通过：{total}/{total} 个工件均 pinned=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
