"""
CLI _run_single_task 回归测试：验证 CLI 选项经 state 贯通到工作流。

回归背景：
- 此前 --timeout 传入 _run_single_task 后未被使用，Executor 直接读环境变量；
- --coverage-threshold 校验后从未参与结果判定。
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _invoke_single_task(
    tmp_path, coverage_report: float | None = 85.0, **cli_kwargs
) -> tuple[dict, dict, MagicMock]:
    """调用 _run_single_task 并 mock 工作流构建。

    Args:
        tmp_path: pytest 临时目录（创建被测文件）。
        coverage_report: 模拟工作流最终 state 中的覆盖率值（注入 mock 返回值）。
        cli_kwargs: 覆盖 _run_single_task 的 CLI 参数默认值
            （func/max_iterations/timeout/coverage_threshold/output_json）。

    Returns:
        (result 字典, 注入 state, mock_graph)。
    """
    from src.cli import app as cli_app

    target_file = tmp_path / "calc.py"
    target_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    defaults = dict(func="add", max_iterations=3, timeout=42, coverage_threshold=80.0, output_json=True)
    defaults.update(cli_kwargs)

    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "test_passed": True,
        "coverage_report": coverage_report,
        "iteration": 1,
        "diagnosis": None,
        "error_category": None,
    }
    with patch("src.cli.app.build_workflow", return_value=mock_graph):
        result = cli_app._run_single_task(str(target_file), **defaults)
    state = mock_graph.invoke.call_args[0][0]
    return result, state, mock_graph


class TestRunSingleTaskStatePropagation:
    """测试 CLI 选项经 state 传递到工作流。"""

    def test_timeout_propagated_to_state(self, tmp_path):
        """--timeout 值应写入 state['execution_timeout']。"""
        _, state, _ = _invoke_single_task(tmp_path, timeout=99)
        assert state["execution_timeout"] == 99

    def test_coverage_threshold_propagated_to_state(self, tmp_path):
        """--coverage-threshold 值应写入 state['coverage_threshold']。"""
        _, state, _ = _invoke_single_task(tmp_path, coverage_threshold=60.0)
        assert state["coverage_threshold"] == 60.0

    def test_coverage_ok_true_when_above_threshold(self, tmp_path):
        """覆盖率 85% ≥ 阈值 80% → coverage_ok=True。"""
        result, _, _ = _invoke_single_task(tmp_path, coverage_report=85.0, coverage_threshold=80.0)
        assert result["coverage"] == 85.0
        assert result["coverage_ok"] is True

    def test_coverage_ok_false_when_below_threshold(self, tmp_path):
        """覆盖率 50% < 阈值 80% → coverage_ok=False。"""
        result, _, _ = _invoke_single_task(tmp_path, coverage_report=50.0, coverage_threshold=80.0)
        assert result["coverage_ok"] is False

    def test_coverage_ok_none_when_no_coverage(self, tmp_path):
        """无覆盖率数据时 coverage_ok 为 None（未知，不误判）。"""
        result, _, _ = _invoke_single_task(tmp_path, coverage_report=None, coverage_threshold=80.0)
        assert result["coverage"] is None
        assert result["coverage_ok"] is None

    def test_result_includes_threshold_field(self, tmp_path):
        """结果字典包含 coverage_threshold 字段，便于 JSON 消费方判定。"""
        result, _, _ = _invoke_single_task(tmp_path, coverage_threshold=75.0)
        assert result["coverage_threshold"] == 75.0
