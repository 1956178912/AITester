"""O2 谱系故障定位（src/agents/fl_spectral.py）单元测试。

背景：2026-09-29 批次新增的模块（R8 起 FL_SPECTRAL_ENABLE 默认开启）
落地时零测试覆盖——`agents/fl_spectral.py` 19 个分支在 coverage.xml
中全部未覆盖，是本批次总分支覆盖从 77% 跌至 73% 的主因之一。
本文件覆盖：开关解析 / Ochiai 打分 / Top-k 排序 / prompt 注入段落 /
measure_fl_spectral_focus 的降级与真实测量路径（2026-10-02 审查修复）。
"""

from __future__ import annotations

import textwrap

import pytest

from src.agents.fl_spectral import (
    _measure_timeout,
    _ochiai_score,
    _top_k,
    build_fl_spectral_prompt_section,
    compute_ochiai_scores,
    fl_spectral_enabled,
    measure_fl_spectral_focus,
    rank_top_k,
)


class TestSwitches:
    """开关与参数解析（默认 false / 默认 5 / 默认 60s 历史口径）。"""

    def test_enabled_default_true(self, monkeypatch):
        # R8（2026-09-30 独立审查 N7，P1）：FL_SPECTRAL_ENABLE 起默认开启
        # （缺省视为 "true"）；显式设 "false" 可退回"关闭"口径（消融对照组）。
        monkeypatch.delenv("FL_SPECTRAL_ENABLE", raising=False)
        assert fl_spectral_enabled() is True

    @pytest.mark.parametrize("value", ["true", "TRUE", "1", "on"])
    def test_enabled_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("FL_SPECTRAL_ENABLE", value)
        assert fl_spectral_enabled() is True

    def test_enabled_false_value(self, monkeypatch):
        monkeypatch.setenv("FL_SPECTRAL_ENABLE", "false")
        assert fl_spectral_enabled() is False

    def test_top_k_default_and_override(self, monkeypatch):
        monkeypatch.delenv("FL_SPECTRAL_TOP_K", raising=False)
        assert _top_k() == 5
        monkeypatch.setenv("FL_SPECTRAL_TOP_K", "3")
        assert _top_k() == 3

    def test_top_k_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("FL_SPECTRAL_TOP_K", "not-a-number")
        assert _top_k() == 5

    def test_measure_timeout_default_and_invalid(self, monkeypatch):
        monkeypatch.delenv("FL_SPECTRAL_TIMEOUT", raising=False)
        assert _measure_timeout() == 60
        monkeypatch.setenv("FL_SPECTRAL_TIMEOUT", "10")
        assert _measure_timeout() == 10
        monkeypatch.setenv("FL_SPECTRAL_TIMEOUT", "abc")
        assert _measure_timeout() == 60


class TestOchiaiScore:
    """_ochiai_score 公式与边界。"""

    def test_zero_hits_returns_zero(self):
        assert _ochiai_score(0, 0) == 0.0

    def test_failed_only(self):
        # n_df=1, n_pf=0 → (1/sqrt(1))/1 = 1.0
        assert _ochiai_score(1, 0) == 1.0

    def test_both_hits(self):
        # n_df=1, n_pf=1 → (1/sqrt(2))/2 ≈ 0.353553
        assert abs(_ochiai_score(1, 1) - 0.353553) < 1e-5

    def test_score_always_in_unit_interval(self):
        for n_df in range(0, 6):
            for n_pf in range(0, 6):
                s = _ochiai_score(n_df, n_pf)
                assert 0.0 <= s <= 1.0, f"_ochiai_score({n_df},{n_pf})={s} 越界"


class TestComputeOchiaiScores:
    """compute_ochiai_scores 候选集与打分口径。"""

    def test_empty_failed_returns_empty(self):
        assert compute_ochiai_scores([], [1, 2]) == {}

    def test_default_candidates_union(self):
        scores = compute_ochiai_scores([1, 2], [2, 3])
        assert set(scores) == {1, 2, 3}

    def test_explicit_candidates(self):
        scores = compute_ochiai_scores([10], [], all_candidate_lines=[10, 20])
        assert set(scores) == {10, 20}
        assert scores[20] == 0.0  # 未被执行的行无证据 → 0 分

    def test_empty_candidate_set_returns_empty(self):
        # all_candidate_lines 显式空列表 → falsy → 回退 union（非空）
        scores = compute_ochiai_scores([5], [], all_candidate_lines=[])
        assert set(scores) == {5}

    def test_failed_line_scores_higher_than_passed_only(self):
        scores = compute_ochiai_scores([7], [8, 9], all_candidate_lines=[7, 8])
        assert scores[7] > scores[8], "失败命中行应排在仅通过命中行之前"


class TestRankTopK:
    """rank_top_k 排序与 tie-break。"""

    def test_k_none_returns_all_sorted(self):
        out = rank_top_k({3: 0.1, 1: 0.9, 2: 0.5})
        assert [o["line"] for o in out] == [1, 2, 3]

    def test_top_k_limit(self):
        out = rank_top_k({1: 0.9, 2: 0.5, 3: 0.1}, k=2)
        assert len(out) == 2
        assert out[0]["line"] == 1

    def test_tie_break_by_line_ascending(self):
        out = rank_top_k({5: 0.5, 2: 0.5, 9: 0.5}, k=3)
        assert [o["line"] for o in out] == [2, 5, 9]

    def test_k_zero_returns_empty(self):
        assert rank_top_k({1: 0.9}, k=0) == []

    def test_negative_k_clamped_to_zero(self):
        assert rank_top_k({1: 0.9}, k=-3) == []

    def test_empty_scores(self):
        assert rank_top_k({}, k=5) == []


class TestPromptSection:
    """build_fl_spectral_prompt_section 注入段落（保守口径）。"""

    def test_none_returns_empty(self):
        assert build_fl_spectral_prompt_section(None) == ""

    def test_empty_top_k_returns_empty(self):
        assert build_fl_spectral_prompt_section({"top_k": []}) == ""

    def test_renders_lines_and_instruction(self):
        text = build_fl_spectral_prompt_section({"top_k": [{"line": 12, "score": 0.75}]})
        assert "第 12 行" in text
        assert "Ochiai" in text
        assert "可疑行" in text


class TestMeasureFlSpectralFocus:
    """measure_fl_spectral_focus 降级路径 + 真实测量路径。"""

    def test_none_failed_cases_returns_none(self, tmp_path):
        assert measure_fl_spectral_focus("x.py", "pass", "def test(): pass", failed_cases=None) is None

    def test_empty_failed_cases_returns_none(self, tmp_path):
        assert measure_fl_spectral_focus("x.py", "pass", "def test(): pass", failed_cases=[]) is None

    def test_empty_test_code_returns_none(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        assert measure_fl_spectral_focus(str(target), "pass", "   ", failed_cases=[{"name": "t"}]) is None

    def test_missing_target_file_returns_none(self, tmp_path):
        missing = tmp_path / "nope.py"
        assert measure_fl_spectral_focus(str(missing), "pass", "def test(): pass", failed_cases=[{"name": "t"}]) is None

    def test_real_measurement_ranks_executed_lines(self, tmp_path):
        """真实测量：缺陷模块 + 失败测试 → 返回 Top-k 且行号在候选内。"""
        target = tmp_path / "calc_mod.py"
        target.write_text(
            textwrap.dedent(
                """
                def divide(a, b):
                    if b == 0:
                        raise ValueError("no")
                    return a / b

                def test_bad():
                    assert divide(1, 0) == 1
                """
            ).strip(),
            encoding="utf-8",
        )
        # 修正测试：调用被测函数但断言失败（确保执行到缺陷行）
        test_code = textwrap.dedent(
            """
            from calc_mod import divide

            def test_fails():
                assert divide(1, 0) == 42
            """
        ).strip()
        # 让 import 可解析（measure 默认 cwd=target 所在目录）
        result = measure_fl_spectral_focus(
            str(target),
            target.read_text(encoding="utf-8"),
            test_code,
            failed_cases=[{"name": "test_fails", "error": "assert"}],
            module_name="calc_mod",
        )
        assert result is not None, "真实测量应成功（coverage + pytest 子进程）"
        assert result["target_module"] == "calc_mod"
        assert result["top_k"], "Top-k 不应为空"
        assert result["failed_lines"] > 0
        top_lines = {item["line"] for item in result["top_k"]}
        assert top_lines & {1, 2, 3, 4}, "缺陷相关行应进入候选"
