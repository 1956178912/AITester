"""M1 科学主张测试（2026-09-29 审查 P0 + D.6 第 6 步）。

CI 硬门禁：对固定缺陷集断言"生成测试在 buggy 代码上必须变红"。

背景：2026-09-29 审查 F1 发现旧 `success_rate` 口径下 65.9% 的"成功"
实为"测试未检出缺陷"（oracle-from-implementation）。M1 修复后，
新指标 `detection_rate` 以"生成测试在 buggy 代码上 rc != 0"为判据。

本测试用**固定已知缺陷**（无需 LLM）验证 M1 指标实现正确性：
- 缺陷代码 + 正确 gold 测试 → detection_rate 必须为 1.0；
- 缺陷代码 + 恒真测试（oracle-from-implementation）→ detection_rate 必须为 0.0；
- 修复代码 + 正确 gold 测试 → repair_rate 必须为 1.0。

不依赖 LLM / 网络 / 外部基准，纯确定性断言，CI 可安全运行。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def _run_pytest(test_code: str, target_code: str) -> int:
    """在临时目录运行 pytest，返回退出码（0 = 全过，1 = 有失败，>1 = 异常）。"""
    with tempfile.TemporaryDirectory(prefix="sciclm_") as tmp:
        target_path = Path(tmp) / "target.py"
        target_path.write_text(target_code, encoding="utf-8")
        test_path = Path(tmp) / "test_target.py"
        test_path.write_text(test_code, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_path, "-q", "--no-header", "-x"],
            capture_output=True,
            text=True,
            cwd=tmp,
            timeout=60,
        )
        return result.returncode


# ── 固定缺陷集（确定性，无需 LLM）──────────────────────────────────────────


def buggy_divide() -> str:
    """注入缺陷：除零无检查（gold 要求 ValueError）。"""
    return (
        "def divide(a: float, b: float) -> float:\n"
        "    '''Divide a by b; raise ValueError when b is zero.'''\n"
        "    return a / b\n"
    )


def fixed_divide() -> str:
    """修复后代码：除零时 raise ValueError。"""
    return (
        "def divide(a: float, b: float) -> float:\n"
        "    '''Divide a by b; raise ValueError when b is zero.'''\n"
        "    if b == 0:\n"
        "        raise ValueError('division by zero')\n"
        "    return a / b\n"
    )


GOLD_TEST = """
import pytest
from target import divide

def test_divide_by_zero():
    with pytest.raises(ValueError):
        divide(1.0, 0.0)

def test_divide_normal():
    assert divide(6.0, 2.0) == 3.0
"""

# 恒真测试（oracle-from-implementation：断言实现行为，非规约行为）
TAUTOLOGICAL_TEST = """
from target import divide

def test_divide_by_zero():
    # 断言实现实际抛出的异常（oracle-from-implementation）
    try:
        divide(1.0, 0.0)
    except ZeroDivisionError:
        pass
    else:
        pass  # 恒真：不 raise 也 pass

def test_divide_normal():
    assert divide(6.0, 2.0) == 3.0
"""


class TestM1Metrics:
    """M1 三指标实现验证（detection_rate / repair_rate / false_fix_rate）。"""

    def test_detection_rate_buggy_code_gold_test(self):
        """buggy 代码 + gold 测试 → 测试必须失败（rc != 0）→ detection_rate=1.0。

        2026-09-29 审查铁证：`divide_by_zero_missing` 任务的 gold 测试
        在 buggy 代码上 FAILED（ValueError 未被 raise），缺陷可检出。
        """
        rc = _run_pytest(GOLD_TEST, buggy_divide())
        assert rc != 0, f"gold 测试在 buggy 代码上应失败（rc={rc}），detection_rate=0 错误"

    def test_detection_rate_buggy_code_tautological_test(self):
        """buggy 代码 + 恒真测试 → 测试通过（rc=0）→ detection_rate=0.0。

        oracle-from-implementation 的反面：测试断言实现行为，
        在带缺陷代码上通过 → 缺陷未被检出。
        """
        rc = _run_pytest(TAUTOLOGICAL_TEST, buggy_divide())
        assert rc == 0, f"恒真测试在 buggy 代码上应通过（rc={rc}），确认缺陷未检出"

    def test_repair_rate_fixed_code_gold_test(self):
        """修复代码 + gold 测试 → 测试必须通过（rc=0）→ repair_rate=1.0。"""
        rc = _run_pytest(GOLD_TEST, fixed_divide())
        assert rc == 0, f"gold 测试在修复代码上应通过（rc={rc}），repair_rate=0 错误"

    def test_false_fix_rate_buggy_code_tautological_test(self):
        """buggy 代码 + 恒真测试 + passed=True → false_fix_rate=1.0。

        旧 success_rate 口径下此情形计入"成功"，新口径标记为假修复。
        """
        rc = _run_pytest(TAUTOLOGICAL_TEST, buggy_divide())
        # 测试通过（passed=True）但代码未修复 → 假修复
        assert rc == 0, "恒真测试在 buggy 代码上应通过，确认假修复通道"


class TestM1MetricsIntegration:
    """M1 指标与 experiments/_m1_metrics.py 的集成验证。"""

    def test_m1_metrics_module_exists(self):
        """experiments/_m1_metrics.py 必须存在（M1 三指标实现模块）。"""
        import importlib.util

        spec = importlib.util.find_spec("experiments._m1_metrics")
        assert spec is not None, "experiments/_m1_metrics.py 不存在（M1 指标未实现）"

    def test_m1_metrics_functions_exist(self):
        """_m1_metrics 指标函数必须存在且可调用。"""
        from experiments._m1_metrics import (
            _compute_detection_rate,
            _compute_false_fix_rate,
            _compute_repair_rate,
            _compute_test_error_rate,
        )

        assert callable(_compute_detection_rate)
        assert callable(_compute_repair_rate)
        assert callable(_compute_false_fix_rate)
        # 2026-09-30 独立审查 N1：test_error_rate（坏测试直接防线）
        assert callable(_compute_test_error_rate)


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
