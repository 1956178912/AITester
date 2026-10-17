"""KB 覆盖率收口：`src/tools/multi_candidate.py` 的静态门 / 趋势 / 合成降级分支。

动机：multi_candidate 补口前 25 行未覆盖，缺口集中在**"坏候选"处理与多解
合成的失败降级**——静态门三条拒绝理由（过短 / 丢失全部函数 / 函数数减少）、
候选清理的 OSError、覆盖率趋势的非数值 delta、奖励预测器跳过未通过候选、
AST 提取/合成的语法错误回退。多候选策略默认关闭，未覆盖意味着一旦开启，
"坏候选会不会混进写盘路径"从未验证。

纪律：零 LLM / 零网络 / 零真实写盘。静态门用 monkeypatch 替换
`apply_patch_to_code`（直接构造"应用结果"），合成路径用真实 AST 操作 +
必要的失败注入；候选对象用真实 dataclass。
"""

from __future__ import annotations

import ast
import logging

import pytest

from src.tools import multi_candidate as mc
from src.tools.multi_candidate import CandidateResult

_ORIG_TWO_FUNCS = "def a():\n    return 1\n\n\ndef b():\n    return 2\n"
_ORIG_WITH_CONST = "def f():\n    return 1\n"


def _cand(index: int, new_code: str, static_passed: bool = True) -> CandidateResult:
    return CandidateResult(index=index, patch="patch", new_code=new_code, static_passed=static_passed)


@pytest.mark.unit
class TestStaticValidateRejections:
    """static_validate_patch 的四条拒绝理由（应用结果由 fake 直接注入）。"""

    def test_too_short_after_apply(self, monkeypatch: pytest.MonkeyPatch):
        original = "def big():\n" + "    x = 1\n" * 20
        monkeypatch.setattr(mc, "apply_patch_to_code", lambda code, patch: ("def big(): pass\n", True))
        ok, reason, applied = mc.static_validate_patch(original, "patch")
        assert ok is False
        assert "应用后代码过短" in reason
        assert applied == ""

    def test_all_function_defs_lost(self, monkeypatch: pytest.MonkeyPatch):
        original = "def f():\n    return 1\n"
        monkeypatch.setattr(mc, "apply_patch_to_code", lambda code, patch: ("value = 1\n", True))
        ok, reason, _ = mc.static_validate_patch(original, "patch")
        assert ok is False
        assert reason == "应用后代码丢失了全部函数定义"

    def test_function_definition_count_decreased(self, monkeypatch: pytest.MonkeyPatch):
        original = "def f():\n    return 1\n\n\ndef g():\n    return 2\n"
        # 只剩一个函数：长度仍 > 原 10%、仍有函数定义、语法合法 → 命中"函数数减少"
        monkeypatch.setattr(mc, "apply_patch_to_code", lambda code, patch: ("def f():\n    return 1\n", True))
        ok, reason, _ = mc.static_validate_patch(original, "patch")
        assert ok is False
        assert reason == "函数定义数量减少（可能误删其他函数）"


@pytest.mark.unit
class TestCandidateGenerationAndCleanup:
    """候选生成通过路径与临时文件清理的失败降级。"""

    def test_generated_candidate_keeps_applied_code(self, monkeypatch: pytest.MonkeyPatch):
        debugger = type("FakeDebugger", (), {"debug": lambda self, **kwargs: {"patch": "fake-patch"}})()
        monkeypatch.setattr(mc, "static_validate_patch", lambda code, patch: (True, "", "applied-code"))
        candidates = mc.generate_candidates(debugger, "def f(): pass\n", "AssertionError", [], num_candidates=1)
        assert len(candidates) == 1
        assert candidates[0].static_passed is True
        assert candidates[0].new_code == "applied-code"
        assert candidates[0].patch == "fake-patch"

    def test_safe_unlink_oserror_only_warns(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
        monkeypatch.setattr(mc.os.path, "exists", lambda path: True)

        def _boom(path: str) -> None:
            raise OSError("删除失败（模拟）")

        monkeypatch.setattr(mc.os, "unlink", _boom)
        with caplog.at_level(logging.WARNING, logger="src.tools.multi_candidate"):
            mc._safe_unlink("/tmp/候选临时文件.py")
        assert "清理候选临时文件失败" in caplog.text


@pytest.mark.unit
class TestCoverageTrend:
    """覆盖率趋势：None delta 跳过 / 混合方向 → unknown。"""

    def test_none_delta_is_skipped(self):
        trace = [{"coverage_delta": None}, {"coverage_delta": -1.0}, {"coverage_delta": -2.0}]
        assert mc._coverage_trend(trace) == "declining"

    def test_mixed_direction_returns_unknown(self):
        assert mc._coverage_trend([{"coverage_delta": -1.0}, {"coverage_delta": 1.0}]) == "unknown"


@pytest.mark.unit
class TestPredictRewardsSkipsRejected:
    """奖励预测器只评分静态通过且有 new_code 的候选。"""

    def test_rejected_candidate_is_skipped(self):
        rejected = CandidateResult(index=0, patch="p", static_passed=False)
        report = mc.predict_candidate_rewards(_ORIG_WITH_CONST, [rejected])
        assert report["candidates"] == []
        assert report["best_candidate_index"] is None
        assert report["trend"] == "unknown"


@pytest.mark.unit
class TestModifiedRegionsExtraction:
    """AST diff 提取修改区域：新代码语法损坏时按"全部函数被改"保守处理。"""

    def test_syntax_error_in_new_code_returns_old_signatures(self):
        modified = mc._extract_modified_regions(_ORIG_TWO_FUNCS, "def a(:\n    return 1\n")
        assert modified == {"a", "b"}


@pytest.mark.unit
class TestSynthesizeCandidatesDegradation:
    """多解合成（PRISM 式）的失败降级链。"""

    def test_original_code_syntax_error_returns_empty(self):
        candidates = [_cand(0, "def a():\n    return 10\n"), _cand(1, "def b():\n    return 20\n")]
        code, labels = mc.synthesize_candidates("def broken(:\n", candidates)
        assert code == ""
        assert isinstance(labels, list)

    def test_candidate_without_modifications_is_skipped(self):
        base = "def a():\n    return 10\n\n\ndef b():\n    return 2\n"
        unchanged = _cand(1, _ORIG_TWO_FUNCS)
        code, labels = mc.synthesize_candidates(_ORIG_TWO_FUNCS, [_cand(0, base), unchanged])
        assert code == base, "无修改的候选不参与合并（只跳过、不污染基候选）"
        assert labels == ["a", "(无修改)"]

    def test_synthesized_syntax_error_falls_back(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ):
        # 两个候选各只改一个函数（修改区域不相交），合并阶段才可能走到语法校验
        only_a = "def a():\n    return 10\n\n\ndef b():\n    return 2\n"
        only_b = "def a():\n    return 1\n\n\ndef b():\n    return 20\n"

        def _corrupt(lines: list[str], func_name: str, node, source_code: str) -> None:
            lines[:] = ["def broken((\n"]

        monkeypatch.setattr(mc, "_replace_function_in_code", _corrupt)
        with caplog.at_level(logging.WARNING, logger="src.tools.multi_candidate"):
            code, labels = mc.synthesize_candidates(_ORIG_TWO_FUNCS, [_cand(0, only_a), _cand(1, only_b)])
        assert code == ""
        assert "合成后代码语法错误" in caplog.text
        assert labels  # 标签仍返回（观测数据不失真）


@pytest.mark.unit
class TestReplaceFunctionInCodeDegradation:
    """函数体替换的失败降级（不修改 lines、不抛异常）。"""

    def test_get_source_segment_value_error_returns(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(mc.ast, "get_source_segment", lambda *a, **k: (_ for _ in ()).throw(ValueError("AST 损坏")))
        lines = ["def f():\n", "    return 1\n"]
        node = ast.parse("def f():\n    return 1\n").body[0]
        mc._replace_function_in_code(lines, "f", node, "def f():\n    return 1\n")  # type: ignore[arg-type]
        assert lines == ["def f():\n", "    return 1\n"]

    def test_function_not_found_returns_without_change(self):
        source = "def f():\n    return 1\n"
        node = ast.parse(source).body[0]
        lines = ["def other():\n", "    return 2\n"]
        mc._replace_function_in_code(lines, "f", node, source)
        assert lines == ["def other():\n", "    return 2\n"]

    def test_function_body_replaced(self):
        old_lines = ["def f():\n", "    return 1\n", "\n", "def g():\n", "    return 2\n"]
        new_source = "def f():\n    return 100\n"
        node = ast.parse(new_source).body[0]
        mc._replace_function_in_code(old_lines, "f", node, new_source)
        # 替换粒度是"整个函数源码段"（ast.get_source_segment 无尾换行 + 补一个）
        assert old_lines[0] == "def f():\n    return 100\n"
        assert old_lines[1] == "def g():\n"  # 原 f 函数两行被整段替换为一行
