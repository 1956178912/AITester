"""R5（2026-10-05 审查建议）：变异检出率（mutation detection rate）——测试有效性客观指标。

背景：
    主批次显示生成测试 detection_rate=2%、false_fix=90%——生成的测试大多
    检不出缺陷。变异检出率（SWE-Mutation 2026 口径）提供测试有效性的
    客观裁决：生成的测试在 **gold 修复代码** 上必须全绿（测试本身有效），
    且在其 AST 变异体上变红的比例越高，说明测试真正校验了代码语义，
    而非"跑通了但什么都没断言"的弱测试。

    与 mutation_testing.compute_mutation_score 的区别：
    - mutation_score：对**原始（缺陷）代码**做变异，度量"生成测试杀死
      缺陷代码变异体"的比例（生成器视角的故障覆盖）；
    - mutation_detection_rate（本模块）：对 **gold 修复代码**做变异，
      度量"测试在正确实现的行为扰动下变红"的比例（SWE-Mutation 口径的
      测试有效性：先证测试在正确代码上有效，再看它能否察觉行为变化）。

设计约束（与 _m1_metrics 同口径，保守、零 LLM）：
    - 纯子进程实现：复用 _m1_metrics._run_pytest_in_tmp 的 pytest 执行
      口径与 _looks_like_test_execution_error 的收集错误判据，不引入
      任何 LLM 调用与新依赖；
    - 变异体生成复用 mutation_testing.MutationGenerator（运算符翻转 /
      布尔取反 / 数字偏移 / 边界替换 / 返回值变异 / 异常路径变异等）；
    - 变异体被检出 = pytest rc != 0 且**非**收集错误（rc >= 2 或
      "errors during collection" / "no tests were run" / "SyntaxError"
      等特征不算检出——套件根本没跑起来，不能归功于测试的检出能力）；
    - fixed 基线不绿（rc != 0，含收集错误）或无变异体时 rate=None +
      skipped=True（测试本身坏则无法裁决，保守 None，不误报 0）；
    - 单变异体超时 / IO 异常按"存活"计（不夸大检出率，与
      mutation_testing._run_mutant_tests 的保守口径一致）；
    - 变异体多于 n_mutants 时按 seed 随机采样（跨运行可复现，消除
      "固定截断取前 N 个同质变异体"的采样偏置）。
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

from experiments._m1_metrics import _looks_like_test_execution_error, _run_pytest_in_tmp
from experiments.mutation_testing import MutationGenerator

logger = logging.getLogger(__name__)


def _mutant_detected(returncode: int, output: str) -> bool:
    """判定一次"变异体 + 生成测试"的 pytest 运行是否构成检出。

    判据（与 _m1_metrics 的收集错误口径一致）：
    - rc == 0（全绿）→ 未检出（存活：测试未察觉行为扰动）；
    - rc != 0 且非收集错误 → 检出（测试跑起来了且断言失败）；
    - rc != 0 但属收集错误（rc >= 2 或显式标记命中）→ 未检出
      （套件没跑起来，不构成有效检出信号）。

    Args:
        returncode: pytest 子进程退出码。
        output: pytest stdout + stderr 拼接文本（标记匹配用）。

    Returns:
        是否构成检出。
    """
    if returncode == 0:
        return False
    return not _looks_like_test_execution_error(returncode, output)


def mutation_detection_rate(
    fixed_code: str,
    test_code: str,
    module_name: str,
    n_mutants: int = 5,
    timeout_per_run: int = 30,
    seed: int = 42,
) -> dict[str, Any]:
    """计算生成测试在 gold fixed 代码变异体上的检出率（SWE-Mutation 口径）。

    流程：
        1. 基线段：test_code 在 fixed_code 上跑 pytest，必须全绿（rc == 0
           且无收集错误）；不绿 → 测试本身坏则无法裁决 → rate=None +
           skipped=True（保守不误报）；
        2. 变异段：MutationGenerator 对 fixed_code 生成 AST 变异体，多于
           n_mutants 时按 seed 随机采样（可复现），不足时用实际可得数；
        3. 裁决段：逐个变异体写盘 + 子进程 pytest：rc != 0 且非收集错误
           → 检出（杀死）；超时 / IO 异常按存活计（保守不夸大）。

    Args:
        fixed_code: gold 修复后的完整模块源码（变异基底）。
        test_code: 生成的测试代码（import module_name）。
        module_name: 被测模块名（沙箱写盘文件名，须与 test_code 的
            import 名一致，口径同 _m1_metrics._run_pytest_in_tmp）。
        n_mutants: 最多评估的变异体数量（默认 5，控制子进程执行时间；
            可得变异体不足时用实际数）。
        timeout_per_run: 单次 pytest 子进程超时（秒）。
        seed: 变异体随机采样种子（固定 seed 产物可复现）。

    Returns:
        {"rate": float | None, "mutants_total": int, "mutants_killed": int,
         "skipped": bool, "skip_reason": str, "elapsed_seconds": float}
        skipped=True 时 rate=None 且 skip_reason 给出原因（输入材料缺失 /
        fixed 基线不绿 / 无变异体 / n_mutants 无效）。
    """
    t0 = time.time()

    def _skip(reason: str) -> dict[str, Any]:
        """构造保守跳过返回（rate=None，测试坏 / 材料缺时不误报 0）。"""
        return {
            "rate": None,
            "mutants_total": 0,
            "mutants_killed": 0,
            "skipped": True,
            "skip_reason": reason,
            "elapsed_seconds": round(time.time() - t0, 2),
        }

    if not (fixed_code or "").strip() or not (test_code or "").strip() or not (module_name or "").strip():
        return _skip("输入材料缺失（fixed_code / test_code / module_name 为空）")
    if n_mutants < 1:
        return _skip("n_mutants 无效（需正整数）")

    # 1. 基线段：测试必须在 gold fixed 代码上全绿（rc == 0 且无收集错误），
    #    否则"变异体上变红"无意义（恒失败 / 坏测试也会让一切变红）
    baseline = _run_pytest_in_tmp(test_code, fixed_code, module_name, timeout=timeout_per_run)
    if baseline is None:
        return _skip("fixed 基线执行超时或异常，无法裁决")
    base_rc, base_out, base_err = baseline
    if base_rc != 0 or _looks_like_test_execution_error(base_rc, base_out + "\n" + base_err):
        return _skip(f"测试在 gold fixed 代码上不绿（rc={base_rc}），测试本身坏则无法裁决")

    # 2. 变异段：复用内置 AST 变异器（7 类变异 + 代码级去重 + 均匀截断）
    all_mutants = MutationGenerator().generate(fixed_code)
    if not all_mutants:
        return _skip("fixed 代码无可变异语句（0 个变异体）")
    # 多于 n_mutants 时按 seed 随机采样（跨运行可复现），不足时用实际可得数
    selected = random.Random(seed).sample(all_mutants, n_mutants) if len(all_mutants) > n_mutants else list(all_mutants)

    # 3. 裁决段：检出 = rc != 0 且非收集错误；超时按存活计
    killed = 0
    for mutant in selected:
        run = _run_pytest_in_tmp(test_code, mutant.code, module_name, timeout=timeout_per_run)
        if run is None:
            continue  # 超时 / IO 异常：保守按存活（不夸大检出率）
        rc, out, err = run
        if _mutant_detected(rc, out + "\n" + err):
            killed += 1

    rate = round(killed / len(selected), 4)
    elapsed = round(time.time() - t0, 2)
    logger.info(
        "变异检出率[%s]: %d/%d 检出，rate=%.4f，耗时 %.1fs（seed=%d）",
        module_name,
        killed,
        len(selected),
        rate,
        elapsed,
        seed,
    )
    return {
        "rate": rate,
        "mutants_total": len(selected),
        "mutants_killed": killed,
        "skipped": False,
        "skip_reason": "",
        "elapsed_seconds": elapsed,
    }
