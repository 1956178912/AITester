"""
M3（2026-09-29 审查 P0）：SWE-bench 实例可解性验证脚本。

历史口径：项目自建 SWE-bench harness 的 365 个任务实例全系统解出 0 个，
但 0 的成因是 harness 在基线上就失败（PASS_TO_PASS 期望 131 / 通过 4），
而非模型能力边界。本脚本在**不依赖 LLM** 的前提下验证单个实例是否
"可解"——即 gold patch 应用后 FAIL_TO_PASS 全绿 ∧ PASS_TO_PASS 全绿。

用法（单实例）：
    python scripts/tools/verify_instance_solvable.py \\
        --repo-url <url> --base-commit <sha> \\
        --fail-to-pass "test_foo.py::test_bar" \\
        --pass-to-pass "test_foo.py::test_baz" \\
        --gold-patch-file /path/to/gold.patch \\
        --test-patch-file /path/to/test.patch

用法（批量，从 JSON 任务文件）：
    python scripts/tools/verify_instance_solvable.py --tasks-file experiments/results/.../task.json

退出码：
    0 = 实例可解（gold patch 后 F2P 全绿 ∧ P2P 全绿）
    1 = 实例不可解（基线损坏 / gold patch 未修复 / P2P 回归）
    2 = 环境/参数错误（无法定位仓库环境）

设计约束（与 ADR-0003 默认关口径一致）：
    - 纯数据 + subprocess，零 LLM 成本；
    - 依赖 RepoExecutor.setup 定位缓存环境（与生产链路同口径）；
    - 可解性验证是实验前置门禁：不可解实例应从 benchmark 批次中
      剔除（harness_invalid），而非计入"0 解出"统计。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def verify_single_instance(
    repo_url: str,
    base_commit: str,
    gold_patch: str,
    test_patch: str,
    fail_to_pass: list[str],
    pass_to_pass: list[str],
    p2p_gate_threshold: float = 0.95,
) -> dict:
    """验证单个 SWE-bench 实例的可解性（gold patch 后 F2P 全绿 ∧ P2P 全绿）。

    流程（与 RepoExecutor.verify 同口径，但用 gold patch 代替 LLM patch）：
    1. setup 定位缓存环境；
    2. git checkout -- . + clean -fd（恢复干净基线）；
    3. 应用 test_patch（如有）；
    4. 跑 FAIL_TO_PASS 基线（应全失败，否则 base_not_failing）；
    5. 跑 PASS_TO_PASS 基线（应全过，否则 harness_invalid）；
    6. 应用 gold patch；
    7. 重跑 FAIL_TO_PASS（应全过）+ PASS_TO_PASS（应全过）；
    8. 判定：F2P 全绿 ∧ P2P 全绿 ∧ 基线 P2P ≥ threshold → 可解。

    Returns:
        {"solvable": bool, "error_type": str | None, "details": dict}
    """
    from src.agents.executor_repo import RepoExecutor, _run

    executor = RepoExecutor(timeout=60)
    env = executor.setup(repo_url, base_commit)
    repo_dir = env["workdir"]
    if env["error"] and not os.path.isdir(repo_dir):
        return {"solvable": False, "error_type": "repo_env_setup_failed", "details": {"message": env["error"]}}

    import tempfile
    import threading

    tmp_dir = tempfile.gettempdir()
    test_file = os.path.join(tmp_dir, f"aitester_verify_{base_commit[:8]}_{os.getpid()}_{threading.get_ident()}.patch")
    gold_file = os.path.join(tmp_dir, f"aitester_verify_gold_{base_commit[:8]}_{os.getpid()}.patch")
    try:
        # 1. 恢复干净基线
        _run(["git", "checkout", "--", "."], repo_dir, 60)
        _run(["git", "clean", "-fd", "-x"], repo_dir, 120)

        # 2. 应用 test_patch
        if test_patch and test_patch.strip():
            with open(test_file, "w", encoding="utf-8") as f:
                f.write(test_patch)
            pre_apply = _run(["git", "apply", "--check", test_file], repo_dir, 60)
            if pre_apply.returncode != 0:
                return {
                    "solvable": False,
                    "error_type": "test_patch_apply_failed",
                    "details": {"message": pre_apply.stderr.strip()[:500]},
                }
            executor._apply_patch_robust(repo_dir, test_file)

        # 3. 基线 F2P（应全失败）+ P2P（应全过）
        baseline_f2p = executor._run_fail_to_pass(repo_dir, fail_to_pass, repo_url=repo_url)
        baseline_p2p = (
            executor._run_pass_to_pass(repo_dir, pass_to_pass, repo_url=repo_url)
            if pass_to_pass
            else {"expected": 0, "passed": 0, "failed_cases": []}
        )
        base_f2p_passed = baseline_f2p["expected"] - len(baseline_f2p["failed_cases"])
        base_p2p_rate = (baseline_p2p["passed"] / baseline_p2p["expected"]) if baseline_p2p["expected"] > 0 else 1.0

        # 基线 F2P 全过 → base_not_failing（缺陷不可复现）
        if base_f2p_passed == baseline_f2p["expected"] and baseline_f2p["expected"] > 0:
            return {
                "solvable": False,
                "error_type": "base_not_failing",
                "details": {
                    "message": "FAIL_TO_PASS 在基线上全部通过：缺陷不可复现或任务数据异常",
                    "f2p_baseline_passed": base_f2p_passed,
                    "f2p_expected": baseline_f2p["expected"],
                },
            }

        # 基线 P2P 低于阈值 → harness_invalid（环境本身损坏）
        if baseline_p2p["expected"] > 0 and base_p2p_rate < p2p_gate_threshold:
            return {
                "solvable": False,
                "error_type": "harness_invalid",
                "details": {
                    "message": f"基线 PASS_TO_PASS {baseline_p2p['passed']}/{baseline_p2p['expected']}（{base_p2p_rate:.2%} < {p2p_gate_threshold:.2%}），harness 环境损坏",
                    "p2p_passed": baseline_p2p["passed"],
                    "p2p_expected": baseline_p2p["expected"],
                    "p2p_rate": round(base_p2p_rate, 4),
                    "threshold": p2p_gate_threshold,
                },
            }

        # 4. 应用 gold patch
        if not gold_patch or not gold_patch.strip():
            return {"solvable": False, "error_type": "no_gold_patch", "details": {"message": "未提供 gold patch"}}
        with open(gold_file, "w", encoding="utf-8") as f:
            f.write(gold_patch)
        gold_check = _run(["git", "apply", "--check", gold_file], repo_dir, 60)
        if gold_check.returncode != 0:
            return {
                "solvable": False,
                "error_type": "gold_patch_apply_failed",
                "details": {"message": gold_check.stderr.strip()[:500]},
            }
        executor._apply_patch_robust(repo_dir, gold_file)

        # 5. 重跑 F2P + P2P
        after_f2p = executor._run_fail_to_pass(repo_dir, fail_to_pass, repo_url=repo_url)
        after_p2p = (
            executor._run_pass_to_pass(repo_dir, pass_to_pass, repo_url=repo_url)
            if pass_to_pass
            else {"expected": 0, "passed": 0, "failed_cases": []}
        )
        f2p_all_green = after_f2p["expected"] > 0 and len(after_f2p["failed_cases"]) == 0
        p2p_all_green = (after_p2p["expected"] == 0) or len(after_p2p["failed_cases"]) == 0
        solvable = f2p_all_green and p2p_all_green

        # 6. 恢复干净基线（gold patch 残留清除）
        _run(["git", "checkout", "--", "."], repo_dir, 60)
        _run(["git", "clean", "-fdx"], repo_dir, 120)

        return {
            "solvable": solvable,
            "error_type": None if solvable else ("f2p_not_fixed" if not f2p_all_green else "p2p_regression"),
            "details": {
                "f2p_after_passed": after_f2p["expected"] - len(after_f2p["failed_cases"]),
                "f2p_after_expected": after_f2p["expected"],
                "p2p_after_passed": after_p2p["passed"],
                "p2p_after_expected": after_p2p["expected"],
                "p2p_baseline_rate": round(base_p2p_rate, 4),
            },
        }
    finally:
        for _f in (test_file, gold_file):
            if os.path.isfile(_f):
                os.remove(_f)


def main() -> int:
    parser = argparse.ArgumentParser(description="M3：SWE-bench 实例可解性验证（零 LLM，纯数据 + subprocess）")
    parser.add_argument("--repo-url", default="", help="仓库 URL")
    parser.add_argument("--base-commit", default="", help="基础 commit SHA")
    parser.add_argument("--fail-to-pass", default="", help="FAIL_TO_PASS 测试节点（逗号分隔）")
    parser.add_argument("--pass-to-pass", default="", help="PASS_TO_PASS 测试节点（逗号分隔）")
    parser.add_argument("--gold-patch-file", default="", help="gold patch 文件路径（unified diff）")
    parser.add_argument("--test-patch-file", default="", help="test patch 文件路径（unified diff，可为空）")
    parser.add_argument("--tasks-file", default="", help="批量：JSON 任务文件路径")
    parser.add_argument("--json-output", default=None, help="结果 JSON 输出路径")
    parser.add_argument("--p2p-gate-threshold", type=float, default=0.95, help="基线 P2P 门禁阈值（默认 0.95）")
    args = parser.parse_args()

    results: list[dict] = []

    if args.tasks_file:
        # 批量模式：从 JSON 任务文件逐实例验证
        with open(args.tasks_file, encoding="utf-8") as f:
            tasks = json.load(f)
        if isinstance(tasks, dict):
            tasks = [tasks]
        for task in tasks:
            meta = task.get("metadata") or task
            repo_url = meta.get("repo_url", args.repo_url)
            base_commit = meta.get("base_commit", args.base_commit)
            fail_to_pass = meta.get("fail_to_pass") or (
                [n.strip() for n in args.fail_to_pass.split(",") if n.strip()] if args.fail_to_pass else []
            )
            pass_to_pass = meta.get("pass_to_pass") or (
                [n.strip() for n in args.pass_to_pass.split(",") if n.strip()] if args.pass_to_pass else []
            )
            gold_patch = meta.get("golden_patch") or ""
            test_patch = meta.get("test_patch") or ""
            if not repo_url or not base_commit:
                results.append(
                    {"task_id": task.get("task_id", ""), "solvable": False, "error_type": "missing_repo_url_or_commit"}
                )
                continue
            result = verify_single_instance(
                repo_url=repo_url,
                base_commit=base_commit,
                gold_patch=gold_patch,
                test_patch=test_patch,
                fail_to_pass=fail_to_pass,
                pass_to_pass=pass_to_pass,
                p2p_gate_threshold=args.p2p_gate_threshold,
            )
            result["task_id"] = task.get("task_id", "")
            results.append(result)
    else:
        # 单实例模式
        fail_to_pass = [n.strip() for n in args.fail_to_pass.split(",") if n.strip()]
        pass_to_pass = [n.strip() for n in args.pass_to_pass.split(",") if n.strip()]
        gold_patch = ""
        if args.gold_patch_file:
            with open(args.gold_patch_file, encoding="utf-8") as f:
                gold_patch = f.read()
        test_patch = ""
        if args.test_patch_file:
            with open(args.test_patch_file, encoding="utf-8") as f:
                test_patch = f.read()
        if not args.repo_url or not args.base_commit:
            print("错误：单实例模式需 --repo-url 和 --base-commit")
            return 2
        result = verify_single_instance(
            repo_url=args.repo_url,
            base_commit=args.base_commit,
            gold_patch=gold_patch,
            test_patch=test_patch,
            fail_to_pass=fail_to_pass,
            pass_to_pass=pass_to_pass,
            p2p_gate_threshold=args.p2p_gate_threshold,
        )
        results.append(result)

    # 输出结果
    for r in results:
        status = "✓ 可解" if r["solvable"] else f"✗ 不可解（{r.get('error_type', 'unknown')}）"
        print(f"  {r.get('task_id', 'single')}: {status}")
        if r.get("details"):
            print(f"    {json.dumps(r['details'], ensure_ascii=False, indent=2)}")

    all_solvable = all(r["solvable"] for r in results)
    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8") as f:
            json.dump({"results": results, "all_solvable": all_solvable}, f, ensure_ascii=False, indent=2)
        print(f"\n结果已写入: {args.json_output}")

    return 0 if all_solvable else 1


if __name__ == "__main__":
    sys.exit(main())
