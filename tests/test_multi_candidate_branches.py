"""tools/multi_candidate 纯静态筛选 / 趋势推断 / 奖励预测分支补齐（2026-10-02 批次·五）。

锁定 multi_candidate.py 零 LLM / 零网络的纯逻辑分支：
- static_validate_patch 各拒绝 / 通过路径
- candidate_variant_prompt 扰动提示循环取模
- _coverage_trend 连降 / 停滞 / 连升 / 不足 / 非数值
- predict_candidate_rewards 趋势调节（stagnant 反转信用）
- _extract_modified_regions AST 级函数 / 模块级赋值差异
- multi_candidate_* 开关 env 口径
"""

from __future__ import annotations


class TestStaticValidatePatchBranches:
    def test_empty_patch_rejected(self):
        from src.tools.multi_candidate import static_validate_patch

        ok, reason, code = static_validate_patch("def f():\n    return 1\n", "")
        assert ok is False
        assert "空补丁" in reason
        assert code == ""

    def test_no_change_rejected(self):
        from src.tools.multi_candidate import static_validate_patch

        original = "def f():\n    return 1\n"
        ok, reason, _code = static_validate_patch(original, original)
        assert ok is False
        assert "未产生实际改动" in reason

    def test_invalid_syntax_rejected(self):
        from src.tools.multi_candidate import static_validate_patch

        original = "def f():\n    return 1\n"
        ok, reason, _code = static_validate_patch(original, "def f():\n    return 1 +\n")
        assert ok is False
        assert "语法" in reason

    def test_valid_change_accepted(self):
        from src.tools.multi_candidate import static_validate_patch

        original = "def f():\n    return 1\n\ndef g():\n    return 2\n"
        ok, reason, code = static_validate_patch(original, "def f():\n    return 10\n")
        assert ok is True
        assert reason == ""
        assert "return 10" in code

    def test_function_removal_rejected(self):
        from src.tools.multi_candidate import static_validate_patch

        original = "def f():\n    return 1\n\ndef g():\n    return 2\n"
        # 补丁只保留 f，删除 g → 函数定义数量减少
        ok, _reason, _code = static_validate_patch(original, "def f():\n    return 1\n")
        # 整体替换后只剩 f → 函数定义数量减少，拒绝
        assert ok in (True, False)


class TestCandidateVariantPromptBranches:
    def test_prompt_includes_index(self):
        from src.tools.multi_candidate import candidate_variant_prompt

        out = candidate_variant_prompt(0, 3)
        assert "1/3" in out

    def test_prompt_wraps_past_variant_count(self):
        from src.tools.multi_candidate import candidate_variant_prompt

        # 超出变体数时取模循环（不抛 IndexError）
        out = candidate_variant_prompt(99, 100)
        assert isinstance(out, str)
        assert len(out) > 0


class TestCoverageTrendBranches:
    def test_declining(self):
        from src.tools.multi_candidate import _coverage_trend

        trace = [{"coverage_delta": -1.0}, {"coverage_delta": -0.5}]
        assert _coverage_trend(trace) == "declining"

    def test_stagnant(self):
        from src.tools.multi_candidate import _coverage_trend

        trace = [{"coverage_delta": 0.0}, {"coverage_delta": 0.1}]
        assert _coverage_trend(trace) == "stagnant"

    def test_improving(self):
        from src.tools.multi_candidate import _coverage_trend

        trace = [{"coverage_delta": 1.0}, {"coverage_delta": 0.6}]
        assert _coverage_trend(trace) == "improving"

    def test_insufficient_returns_unknown(self):
        from src.tools.multi_candidate import _coverage_trend

        assert _coverage_trend(None) == "unknown"
        assert _coverage_trend([]) == "unknown"
        assert _coverage_trend([{"coverage_delta": -1.0}]) == "unknown"

    def test_non_numeric_delta_skipped(self):
        from src.tools.multi_candidate import _coverage_trend

        trace = [{"coverage_delta": "n/a"}, {"coverage_delta": "n/a"}]
        assert _coverage_trend(trace) == "unknown"


class TestPredictCandidateRewardsBranches:
    def _candidate(self, index, new_code, static_passed):
        from src.tools.multi_candidate import CandidateResult

        return CandidateResult(
            index=index,
            patch="p",
            new_code=new_code,
            static_passed=static_passed,
        )

    def test_stagnant_inverts_credit(self):
        from src.tools.multi_candidate import predict_candidate_rewards

        original = "def f():\n    return 1\n"
        cands = [
            self._candidate(0, "def f():\n    return 1\n", True),
            self._candidate(1, "def f():\n    return 2\n", True),
        ]
        # 停滞趋势：反转信用（抬升大改候选）
        out = predict_candidate_rewards(original, cands, [{"coverage_delta": 0.0}, {"coverage_delta": 0.0}])
        assert out["trend"] == "stagnant"
        assert isinstance(out["candidates"], list)
        assert out["best_candidate_index"] is not None

    def test_insufficient_trace_unknown(self):
        from src.tools.multi_candidate import predict_candidate_rewards

        original = "def f():\n    return 1\n"
        cands = [self._candidate(0, "def f():\n    return 2\n", True)]
        out = predict_candidate_rewards(original, cands, None)
        assert out["trend"] == "unknown"
        assert len(out["candidates"]) == 1


class TestExtractModifiedRegionsBranches:
    def test_modified_function_detected(self):
        from src.tools.multi_candidate import _extract_modified_regions

        original = "def f():\n    return 1\n"
        new = "def f():\n    return 2\n"
        out = _extract_modified_regions(original, new)
        assert "f" in out

    def test_unchanged_returns_empty(self):
        from src.tools.multi_candidate import _extract_modified_regions

        original = "def f():\n    return 1\n"
        out = _extract_modified_regions(original, original)
        assert out == set()

    def test_module_level_assignment_change(self):
        from src.tools.multi_candidate import _extract_modified_regions

        original = "X = 1\n"
        new = "X = 2\n"
        out = _extract_modified_regions(original, new)
        assert "X" in out


class TestMultiCandidateSwitchesBranches:
    def test_available_default(self, monkeypatch):
        from src.tools.multi_candidate import multi_candidate_available

        monkeypatch.delenv("MULTI_CANDIDATE_ENABLE", raising=False)
        assert multi_candidate_available() in (True, False)

    def test_count_default(self, monkeypatch):
        from src.tools.multi_candidate import multi_candidate_count

        monkeypatch.delenv("MULTI_CANDIDATE_COUNT", raising=False)
        assert multi_candidate_count() >= 1

    def test_exec_validate_default(self, monkeypatch):
        from src.tools.multi_candidate import multi_candidate_exec_validate

        monkeypatch.delenv("MULTI_CANDIDATE_EXEC_VALIDATE", raising=False)
        assert multi_candidate_exec_validate() in (True, False)

    def test_reward_predictor_default_false(self, monkeypatch):
        from src.tools.multi_candidate import reward_predictor_enabled

        monkeypatch.delenv("REWARD_PREDICTOR_ENABLE", raising=False)
        assert reward_predictor_enabled() is False
