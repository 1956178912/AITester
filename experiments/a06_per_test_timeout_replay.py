#!/usr/bin/env python3
"""A-06 重放工具：per-test 超时对"缺陷实现不终止"任务的判分影响（零 LLM）。

背景（独立评审 A-06，2026-10-17）：
    QuixBugs 41 缺陷程序口径有 4 个任务的**缺陷实现本身不终止**
    （bitcount 的 `n ^= n - 1` 等）——历史判分（整套餐 120s 墙钟）下，
    生成测试在 buggy 侧被墙钟超时整体击杀 → detection=None 被剔除
    （fail-closed 正确但损失可判定样本）。本工具用存量批次工件的
    `generated_test` + `task_metadata.fixed` + vendored 缺陷代码
    （`data/quixbugs/python_programs/`）做**单变量重放**：唯一变量是
    M1_PER_TEST_TIMEOUT（per-test 超时），量化 None → 可判定的转换。

口径纪律：
    - 重放结论**不 retroactively 改写历史批次数字**（历史批次无该开关，
      混口径会破坏可比性）；本工具产出的是"若当时开启该开关"的反事实
      判分，供新批次启用前的影响评估；
    - 判分完全走 `_m1_metrics._run_pytest_in_tmp`（同一函数、同一 F2P
      三段判定的输入），未重实现判分逻辑。

用法（仓库根）：
    .venv/bin/python3 experiments/a06_per_test_timeout_replay.py \
        --batch experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json \
        --arm aitester --per-test 2 --wall 90 \
        --out experiments/results/emse_a06_replay_20261017/replay.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments import _m1_metrics as m1  # noqa: E402

_DEFAULT_TARGETS = ("bitcount", "sqrt", "wrap", "find_first_in_sorted")


def _load_batch(path: Path, arm: str) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["results"][arm]["details"]
    return {str(r.get("task_id")): r for r in rows}


def replay_task(row: dict[str, Any], program: str, per_test: int, wall: int) -> dict[str, Any]:
    """单任务重放：返回两侧 rc 与 F2P 反事实判定。"""
    md = row.get("task_metadata") or {}
    gen = row.get("generated_test") or ""
    fixed = md.get("fixed") or ""
    buggy_path = _REPO_ROOT / "data" / "quixbugs" / "python_programs" / f"{program}.py"
    out: dict[str, Any] = {
        "program": program,
        "historical_detection": row.get("detection_rate"),
        "buggy_rc": None,
        "fixed_rc": None,
        "counterfactual_detection": None,
        "buggy_source_available": buggy_path.exists(),
    }
    if not gen or not fixed or not buggy_path.exists():
        return out
    buggy = buggy_path.read_text(encoding="utf-8")
    res_b = m1._run_pytest_in_tmp(gen, buggy, program, timeout=wall, task_metadata=md, per_test_timeout=per_test)
    res_f = m1._run_pytest_in_tmp(gen, fixed, program, timeout=wall, task_metadata=md, per_test_timeout=per_test)
    out["buggy_rc"] = res_b[0] if res_b else None
    out["fixed_rc"] = res_f[0] if res_f else None
    b, f = out["buggy_rc"], out["fixed_rc"]
    # F2P 三段判定的反事实（buggy 红 ∧ fixed 绿 ∧ 无收集错误）。
    # 收集错误由调用方判定的输出标记决定——重放只报 rc，完整三段判定
    # 以 M1 模块为准；此处 rc 组合已足以区分 None→可判定转换。
    if b is None or f is None:
        out["counterfactual_detection"] = None
    elif b != 0 and f == 0:
        out["counterfactual_detection"] = 1.0
    else:
        out["counterfactual_detection"] = 0.0
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A-06 per-test 超时重放（零 LLM）")
    parser.add_argument("--batch", required=True, help="批次 JSON（含 results.<arm>.details）")
    parser.add_argument("--arm", default="aitester")
    parser.add_argument("--per-test", type=int, default=2, help="per-test 超时（秒）")
    parser.add_argument("--wall", type=int, default=90, help="整套餐墙钟超时（秒）")
    parser.add_argument("--tasks", default=",".join(_DEFAULT_TARGETS), help="逗号分隔的程序名（默认四不终止任务）")
    parser.add_argument("--out", default=None, help="输出 JSON 路径（缺省仅打印）")
    args = parser.parse_args(argv)

    rows = _load_batch(Path(args.batch), args.arm)
    programs = [t.strip() for t in args.tasks.split(",") if t.strip()]
    results = []
    for program in programs:
        tid = f"quixbugs__{program}"
        row = rows.get(tid)
        if row is None:
            results.append({"program": program, "error": "task not in batch"})
            continue
        results.append(replay_task(row, program, args.per_test, args.wall))
        print(
            f"{program}: historical={results[-1]['historical_detection']} "
            f"buggy_rc={results[-1]['buggy_rc']} fixed_rc={results[-1]['fixed_rc']} "
            f"counterfactual={results[-1]['counterfactual_detection']}"
        )
    payload = {
        "batch": args.batch,
        "arm": args.arm,
        "per_test_timeout_s": args.per_test,
        "wall_timeout_s": args.wall,
        "results": results,
        "note": "反事实判分，不 retroactively 改写历史批次数字（口径纪律）",
    }
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        print(f"written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
