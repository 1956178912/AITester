"""tools/multi_candidate 执行验证 / 信用因子 / 候选数钳制分支补齐（2026-10-02 批次·十三）。

锁定批次·五（test_multi_candidate_branches.py）之后仍缺失的纯逻辑分支
（零真实 LLM / 零网络 / mock 执行器）：
- select_best_candidate 静态模式信用排序 / 奖励预测器重排 / 执行验证回退
  （全部执行失败 → None / 选通过且覆盖最高 / 单候选异常不中断）
- line_level_credit_scores 执行因子三分支（None→1.0 / 通过→1.0 /
  失败有覆盖→0.5 / 失败零覆盖→0.0）+ changed_line_count 缓存复用
- multi_candidate_count 上下限钳制 + 非法值回退
- candidate_variant_prompt 循环取模（复用变体）
"""

from __future__ import annotations

from unittest.mock import MagicMock

# ─── select_best_candidate 静态 / 执行验证分支 ────────────────────────────


class TestSelectBestCandidateBranches:
    _ORIG = "def f():\n    return 1\n"

    def _cand(self, idx, new_code, **kw):
        from src.tools.multi_candidate import CandidateResult

        return CandidateResult(index=idx, patch="", new_code=new_code, static_passed=True, **kw)

    def test_no_static_ok_returns_none(self):
        from src.tools.multi_candidate import CandidateResult, select_best_candidate

        cand = CandidateResult(index=0, patch="", static_passed=False)
        assert select_best_candidate([cand], self._ORIG) is None

    def test_static_mode_picks_least_change(self):
        """静态模式：改动最小者信用高，胜出。"""
        from src.tools.multi_candidate import select_best_candidate

        c0 = self._cand(0, "def f():\n    return 2\n")  # 改动小
        c1 = self._cand(1, "def f():\n    x = 9\n    y = 8\n    z = 7\n    return x + y + z\n")  # 改动大
        out = select_best_candidate([c1, c0], self._ORIG)
        assert out is not None
        assert out.index == 0

    def test_static_mode_reward_predictor_disabled_keeps_credit(self, monkeypatch):
        """奖励预测器关闭时按信用排序（不走趋势重排分支）。"""
        from src.tools.multi_candidate import select_best_candidate

        monkeypatch.delenv("REWARD_PREDICTOR_ENABLE", raising=False)
        c0 = self._cand(0, "def f():\n    return 2\n")
        out = select_best_candidate([c0], self._ORIG)
        assert out is not None

    def test_static_mode_reward_predictor_reorders(self, monkeypatch):
        """奖励预测器启用 + 有 execution_trace → 走趋势重排分支。"""
        from src.tools.multi_candidate import select_best_candidate

        monkeypatch.setenv("REWARD_PREDICTOR_ENABLE", "true")
        c0 = self._cand(0, "def f():\n    return 2\n")
        out = select_best_candidate([c0], self._ORIG, execution_trace=[{"coverage_delta": 0.1}])
        assert out is not None

    def test_exec_validation_all_failed_returns_none(self, monkeypatch):
        """执行验证全部候选未通过测试 → 返回 None（回退单补丁路径，round9 P1 守卫）。"""
        from src.tools.multi_candidate import select_best_candidate

        monkeypatch.delenv("REWARD_PREDICTOR_ENABLE", raising=False)
        c0 = self._cand(0, "def f():\n    return 2\n")
        fake_executor = MagicMock()
        fake_executor.execute.return_value = {"passed": False, "coverage": 10.0}
        out = select_best_candidate(
            [c0],
            self._ORIG,
            test_code="def test_x():\n    assert 1\n",
            target_file="/tmp/aitester_mc_probe_xyz.py",
            use_execution_validation=True,
            executor=fake_executor,
        )
        assert out is None

    def test_exec_validation_picks_highest_coverage(self, monkeypatch):
        """执行验证通过：选通过且覆盖率最高者。"""
        from src.tools.multi_candidate import select_best_candidate

        monkeypatch.delenv("REWARD_PREDICTOR_ENABLE", raising=False)
        c0 = self._cand(0, "def f():\n    return 2\n")
        c1 = self._cand(1, "def f():\n    x = 5\n    return x + 1\n")

        def _exec(test_code, target_file, target_function=None):
            with open(target_file, encoding="utf-8") as fh:
                content = fh.read()
            # 候选 1（含 "x = 5"）覆盖率更高且通过 → 应胜出
            if "x = 5" in content:
                return {"passed": True, "coverage": 80.0}
            return {"passed": True, "coverage": 40.0}

        fake_executor = MagicMock()
        fake_executor.execute.side_effect = _exec
        out = select_best_candidate(
            [c0, c1],
            self._ORIG,
            test_code="def test_x():\n    assert 1\n",
            target_file="/tmp/aitester_mc_probe_target.py",
            use_execution_validation=True,
            executor=fake_executor,
        )
        assert out is not None
        assert out.index == 1

    def test_exec_validation_exception_continues(self, monkeypatch):
        """单候选执行异常不中断其余候选（全部异常 → 无通过 → None）。"""
        from src.tools.multi_candidate import select_best_candidate

        monkeypatch.delenv("REWARD_PREDICTOR_ENABLE", raising=False)
        c0 = self._cand(0, "def f():\n    return 2\n")
        fake_executor = MagicMock()
        fake_executor.execute.side_effect = RuntimeError("boom")
        out = select_best_candidate(
            [c0],
            self._ORIG,
            test_code="def test_x():\n    assert 1\n",
            target_file="/tmp/aitester_mc_probe_xyz.py",
            use_execution_validation=True,
            executor=fake_executor,
        )
        assert out is None


# ─── line_level_credit_scores 执行因子分支 ────────────────────────────────


class TestLineLevelCreditFactorBranches:
    _ORIG = "def f():\n    return 1\n\ndef g():\n    return 2\n\ndef h():\n    return 3\n"

    def _patch(self, idx: int, exec_passed=None, exec_coverage=None):
        """补丁只改 f 返回值（保持 g/h）→ 函数定义数不变，改动行占比低（>0 信用）。"""
        from src.tools.multi_candidate import CandidateResult

        return CandidateResult(
            index=idx,
            patch="def f():\n    return 99\n",
            new_code="def f():\n    return 99\n\ndef g():\n    return 2\n\ndef h():\n    return 3\n",
            static_passed=True,
            exec_passed=exec_passed,
            exec_coverage=exec_coverage,
        )

    def test_not_executed_factor_1_0(self):
        """exec_passed=None（纯静态）→ 执行因子 1.0。"""
        from src.tools.multi_candidate import line_level_credit_scores

        cand = self._patch(0)
        out = line_level_credit_scores(self._ORIG, [cand])
        assert out["best_candidate_index"] == 0
        assert out["best_credit"] is not None
        assert out["candidates"][0]["credit_score"] > 0

    def test_exec_passed_factor_1_0(self):
        """exec_passed=True → 执行因子 1.0（信用 > 0）。"""
        from src.tools.multi_candidate import line_level_credit_scores

        cand = self._patch(0, exec_passed=True, exec_coverage=50.0)
        out = line_level_credit_scores(self._ORIG, [cand])
        assert out["candidates"][0]["exec_passed"] is True
        assert out["candidates"][0]["credit_score"] > 0

    def test_exec_failed_with_coverage_factor_0_5(self):
        """exec_passed=False 且 coverage>0 → 执行因子 0.5（信用 > 全 0 因子）。"""
        from src.tools.multi_candidate import line_level_credit_scores

        cand = self._patch(0, exec_passed=False, exec_coverage=30.0)
        out = line_level_credit_scores(self._ORIG, [cand])
        assert out["candidates"][0]["credit_score"] > 0

    def test_exec_failed_zero_coverage_factor_0(self):
        """exec_passed=False 且 coverage=0 → 执行因子 0.0（信用 0）。"""
        from src.tools.multi_candidate import line_level_credit_scores

        cand = self._patch(0, exec_passed=False, exec_coverage=0.0)
        out = line_level_credit_scores(self._ORIG, [cand])
        assert out["candidates"][0]["credit_score"] == 0.0

    def test_changed_line_count_cache_reused(self):
        """changed_line_count 已缓存 → 直接复用（不重算 diff）。"""
        from src.tools.multi_candidate import line_level_credit_scores

        cand = self._patch(0)
        cand.changed_line_count = 7
        out = line_level_credit_scores(self._ORIG, [cand])
        assert out["candidates"][0]["modified_line_count"] == 7

    def test_no_static_passed_best_none(self):
        """无静态通过候选 → best_candidate_index / best_credit 均 None。"""
        from src.tools.multi_candidate import CandidateResult, line_level_credit_scores

        cand = CandidateResult(index=0, patch="", static_passed=False)
        out = line_level_credit_scores(self._ORIG, [cand])
        assert out["best_candidate_index"] is None
        assert out["best_credit"] is None


# ─── multi_candidate_count 上下限钳制 + 非法值回退 ────────────────────────


class TestMultiCandidateCountClampBranches:
    def test_default(self, monkeypatch):
        from src.tools.multi_candidate import multi_candidate_count

        monkeypatch.delenv("MULTI_CANDIDATE_COUNT", raising=False)
        assert multi_candidate_count() == 3

    def test_clamped_to_max(self, monkeypatch):
        from src.tools.multi_candidate import multi_candidate_count

        monkeypatch.setenv("MULTI_CANDIDATE_COUNT", "99")
        assert multi_candidate_count() == 8  # 上限 8

    def test_clamped_to_min(self, monkeypatch):
        from src.tools.multi_candidate import multi_candidate_count

        monkeypatch.setenv("MULTI_CANDIDATE_COUNT", "0")
        assert multi_candidate_count() == 1  # 下限 1

    def test_invalid_value_falls_back(self, monkeypatch):
        from src.tools.multi_candidate import multi_candidate_count

        monkeypatch.setenv("MULTI_CANDIDATE_COUNT", "not_a_number")
        assert multi_candidate_count() == 3  # 非整数回退默认


# ─── candidate_variant_prompt 循环取模 ────────────────────────────────────


class TestCandidateVariantWrapBranches:
    def test_index_beyond_variants_reuses(self):
        """index 超出变体数（3）时取模循环复用变体 0。"""
        from src.tools.multi_candidate import candidate_variant_prompt

        v0 = candidate_variant_prompt(0, 8)
        v3 = candidate_variant_prompt(3, 8)  # 3 % 3 == 0
        assert v0.split("】")[-1] == v3.split("】")[-1]
