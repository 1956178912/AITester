"""对抗式变异循环端到端演示（真实 LLM，零 mock）。

**演示的闭环**（对齐优化方案 v2 §3.2 / P0-1，外部依据 AdverTest ISSTA 2026
DOI 10.1145/3832122 与 arXiv:2607.23002 的机械 oracle 口径）：

    ① LLM 写初始测试 T₀
    ② MDO 度量 T₀ 的 MTR / MDR（基准 = gold 修复后代码）
    ③ AMS（AdversarialMutantSearch）**定向生产真实存活变异体**（客观盲区：
       行为有偏差 ∧ 断言未捕获 ∧ 非崩溃）
    ④ 把盲区清单 + "只补断言、不得改被测代码" 约束交给 LLM → 产出 T₁
    ⑤ 重新度量 T₁，看 MDR 是否上升 / 盲区是否减少
    ⑥ 最多 max_rounds 轮，逐轮落盘

**为什么这是"机械 oracle"**：全部判定（是否行为偏差、是否被断言捕获、是否崩溃）
都由 MDO 的子进程执行决定，**没有任何模型评判另一个模型的输出**——与
arXiv:2607.23002 的预注册实验口径一致。

用法：
    AITESTER_LLM_CACHE=0 .venv/bin/python -m experiments.adversarial_loop_demo \
        --tasks quixbugs__bitcount,quixbugs__flatten,quixbugs__get_factors \
        --rounds 2 --out experiments/results/ams_demo/
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是资深 Python 测试工程师。你只写 pytest 测试代码，"
    "不得修改被测实现。输出必须是可直接执行的完整测试文件，"
    "不要任何解释文字或 markdown 围栏。"
)


def _strip_code(text: str) -> str:
    """从 LLM 输出中提取 Python 代码（去 markdown 围栏）。"""
    if not text:
        return ""
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.S)
    body = m.group(1) if m else text
    return body.strip()


def _generate_tests(agent: Any, *, module: str, fn: str, source: str, extra: str = "") -> str:
    """让 LLM 生成/精化测试（`extra` 为空 = 初始生成；否则为对抗定向精化）。"""
    if extra:
        user = (
            f"下面是当前测试文件与新的**【机械验证过的】盲区清单**。\n\n"
            f"## 当前测试\n```python\n{extra.split('__CURRENT__')[0]}\n```\n\n"
            f"## 盲区清单（已机械验证：确实改变了行为、但你的断言没抓到、且不是崩溃）\n"
            f"{extra.split('__CURRENT__')[1]}\n\n"
            f"## 要求\n"
            f"1. 在**保留所有现有测试**的前提下，**只补充断言**；\n"
            f"2. **不得修改被测实现**（`{module}.py` 只读）；\n"
            f"3. 针对每条盲区，设计能区分该行为偏差的断言（边界值、返回类型/长度、"
            f"短路条件真假两侧、异常路径）；\n"
            f"4. 输出完整测试文件（不是 diff），不要解释。"
        )
    else:
        user = (
            f"请为下面的 Python 实现写一个 pytest 测试文件。\n\n"
            f"## 被测实现（模块名 `{module}`，函数 `{fn}`）\n```python\n{source}\n```\n\n"
            f"## 要求\n"
            f"1. 文件开头写 `from {module} import {fn}`（或 `import {module}`）；\n"
            f"2. 覆盖正常路径、边界值（0/1/空/单元素）、以及你认为容易出错的分支；\n"
            f"3. 断言必须校验**具体返回值**，不要只断言 `is not None`；\n"
            f"4. 只输出测试文件代码，不要解释。"
        )
    return _strip_code(agent._call_llm(user))


def run_task(
    task: Any,
    *,
    rounds: int,
    timeout: int,
    out_dir: Path,
) -> dict[str, Any]:
    """对单个任务执行对抗闭环。"""
    from experiments._m1_metrics import _extract_gold_material, _gold_fixed_code
    from experiments.adversarial_mutation import AdversarialMutantSearch
    from src.agents.base_agent import BaseAgent
    from src.measurement.mdo import compute_mdo

    task_id = str(task.task_id)
    base_code = _gold_fixed_code(task)
    mat = _extract_gold_material(task)
    if not base_code.strip() or mat is None:
        return {"task_id": task_id, "available": False, "reason": "no_gold_material"}
    module, fn = str(mat[0]), str(task.metadata.get("suggested_function") or str(task_id).split("__")[-1])

    agent = BaseAgent(_SYSTEM_PROMPT)
    record: dict[str, Any] = {"task_id": task_id, "module": module, "fn": fn, "rounds": []}

    test_code = _generate_tests(agent, module=module, fn=fn, source=base_code)
    (out_dir / f"{task_id}.round0.test.py").write_text(test_code, encoding="utf-8")

    ams = AdversarialMutantSearch(target_code=base_code, module_name=module, timeout_seconds=timeout)
    for i in range(rounds + 1):
        pool = ams._accepted or None
        mutants = list(pool) if pool else []
        mdo = None
        if mutants:
            r = compute_mdo(
                base_code=base_code, test_code=test_code, module_name=module, mutants=mutants, timeout_seconds=timeout
            )
            mdo = r.as_dict() if r.available else {"mdo_available": False, "reason": r.not_available_reason}
        entry: dict[str, Any] = {"round": i, "mdo_on_accumulated_blindspots": mdo}
        # 首轮先做一次"无盲区"度量（干净基线）
        if i == 0:
            from experiments.mutation_testing import ExtendedMutationGenerator

            base_pool = ExtendedMutationGenerator().generate(base_code)
            r0 = compute_mdo(
                base_code=base_code,
                test_code=test_code,
                module_name=module,
                mutants=base_pool,
                timeout_seconds=timeout,
            )
            entry["mdo_initial_pool"] = (
                r0.as_dict()
                if r0.available
                else {
                    "mdo_available": False,
                    "reason": r0.not_available_reason,
                }
            )
        # 对抗：AMS 针对当前测试生产新盲区
        _accepted, stats = ams.propose_and_filter(test_code)
        entry["ams_round"] = stats
        entry["ams_total_blindspots"] = len(ams._accepted)
        record["rounds"].append(entry)
        logger.info(
            "[%s] round %d：新盲区 %d（累计 %d）｜MDO=%s",
            task_id,
            i,
            stats["accepted"],
            len(ams._accepted),
            entry.get("mdo_on_accumulated_blindspots"),
        )
        if i >= rounds or not ams._accepted:
            break
        # 定向精化：把盲区清单交给 LLM
        section = ams.build_targeting_section()
        if not section:
            break
        test_code = _generate_tests(
            agent,
            module=module,
            fn=fn,
            source=base_code,
            extra=f"{test_code}__CURRENT__{section}",
        )
        (out_dir / f"{task_id}.round{i + 1}.test.py").write_text(test_code, encoding="utf-8")
    record["available"] = True
    record["final_blindspots"] = len(ams._accepted)
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description="对抗式变异循环演示（真实 LLM）")
    ap.add_argument("--tasks", required=True, help="逗号分隔的 task_id（须为单参数函数，便于探针调用）")
    ap.add_argument("--rounds", type=int, default=2, help="对抗轮数（不含初始生成）")
    ap.add_argument("--timeout", type=int, default=25, help="单步子进程超时")
    ap.add_argument("--out", default="experiments/results/ams_demo", help="输出目录")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    os.environ.setdefault("AITESTER_QUIXBUGS_DATA", str(Path("data/quixbugs").resolve()))

    from src.datasets.dataset_realbugs import QuixBugsDataset

    ds = QuixBugsDataset()
    by_id = {t.task_id: t for t in ds.tasks}
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    for tid in [s.strip() for s in args.tasks.split(",") if s.strip()]:
        task = by_id.get(tid)
        if task is None:
            logger.warning("任务不存在：%s", tid)
            continue
        logger.info("=== 对抗闭环：%s ===", tid)
        records.append(run_task(task, rounds=args.rounds, timeout=args.timeout, out_dir=out_dir))

    summary_path = out_dir / "ams_demo_summary.json"
    summary_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 对抗式变异循环演示结果\n", f"- 任务数：{len(records)}；轮数：{args.rounds}\n"]
    lines.append("| 任务 | 初始 MTR | 初始 MDR | 累计盲区 | 最终盲区 | 判定 |")
    lines.append("|---|---|---|---|---|---|")
    for r in records:
        if not r.get("available"):
            lines.append(f"| `{r['task_id']}` | — | — | — | — | 不可用（{r.get('reason')}） |")
            continue
        init = (r["rounds"][0].get("mdo_initial_pool") or {}) if r["rounds"] else {}
        lines.append(
            f"| `{r['task_id']}` | {init.get('mtr')} | {init.get('mdr')} | "
            f"{r['rounds'][0].get('ams_total_blindspots')} | {r.get('final_blindspots')} | — |"
        )
    (out_dir / "ams_demo_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    logger.info("汇总 → %s", summary_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
