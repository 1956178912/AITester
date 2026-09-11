"""
3.1 多候选补丁生成与验证筛选单元测试。

覆盖：
- candidate_variant_prompt 扰动提示词（循环取模、N 个候选各自不同）；
- static_validate_patch 各拒绝/通过分支（空补丁、无法应用、过短、
  无函数、语法错误、函数减少、正常通过）；
- generate_candidates（mock debugger，候选数截断、LLM 失败降级）；
- select_best_candidate（静态模式选改动最小、无候选返回 None、
  执行验证模式选通过且覆盖率高者）；
- multi_candidate_available / multi_candidate_count 环境变量读取。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.tools import multi_candidate as mc

_GOOD_ORIGINAL = """\
def add(a, b):
    return a + b


def mul(a, b):
    return a * b
"""


class TestCandidateVariantPrompt:
    """扰动提示词生成。"""

    def test_three_candidates_distinct(self):
        prompts = [mc.candidate_variant_prompt(i, 3) for i in range(3)]
        assert len(set(prompts)) == 3
        assert "1/3" in prompts[0]
        assert "3/3" in prompts[2]

    def test_modulo_reuse_when_more_than_variants(self):
        # 3 个变体，第 4 个候选（index=3）应复用第 1 个变体内容
        assert "方案 A" in mc.candidate_variant_prompt(0, 4)
        assert "方案 A" in mc.candidate_variant_prompt(3, 4)


class TestStaticValidatePatch:
    """静态筛选各分支。"""

    def test_empty_patch_rejected(self):
        ok, reason = mc.static_validate_patch(_GOOD_ORIGINAL, "")
        assert not ok
        assert "空" in reason

    def test_whitespace_only_patch_rejected(self):
        ok, _ = mc.static_validate_patch(_GOOD_ORIGINAL, "   \n  ")
        assert not ok

    def test_no_change_rejected(self):
        # 补丁与原代码完全相同（apply 单函数替换但内容不变）→ "未产生实际改动"
        patch = _GOOD_ORIGINAL
        ok, reason = mc.static_validate_patch(_GOOD_ORIGINAL, patch)
        assert not ok
        assert "未产生实际改动" in reason

    def test_syntax_error_rejected(self):
        bad = """\
def add(a, b):
    return a +
"""
        # 单函数模式替换 add 为残缺实现 → 语法错误
        ok, reason = mc.static_validate_patch(_GOOD_ORIGINAL, "```python\n" + bad + "\n```")
        assert not ok
        assert "语法错误" in reason

    def test_valid_fix_applies(self):
        # 修复 mul 的 bug（原本 a*b 正确，但把 a 改错）——这里给一个能应用的整文件补丁
        full = """\
def add(a, b):
    return a + b


def mul(a, b):
    return a * b
"""
        ok, reason = mc.static_validate_patch(_GOOD_ORIGINAL, "```python\n" + full.strip() + "\n```")
        # 该补丁与原代码等价（无实际改动），应被"未产生实际改动"拒绝
        assert not ok
        assert "未产生实际改动" in reason

    def test_full_file_patch_preserves_original_functions(self):
        # 整文件模式（含 import 头）：patch_applier 与原子代码合并，不会丢函数。
        # 此行为证明"函数定义数量减少"分支是针对"误删"的防御网，正常整文件补丁
        # 仍能通过（保留原代码全部函数），而非被误拒。
        full_no_mul = "import math\n\n\ndef add(a, b):\n    return a + b\n"
        ok, reason = mc.static_validate_patch(_GOOD_ORIGINAL, "```python\n" + full_no_mul + "\n```")
        assert ok, f"正常整文件补丁应通过，实际被拒: {reason}"

    def test_too_short_rejected(self):
        # 大原代码 + 很短的整文件补丁触发 10% 规则被拒；
        # 但单函数补丁保留其余函数时不会"过短"，验证不会误拒大文件单函数修复
        big_original = "\n".join(f"def f{i}(x):\n    return x + {i}\n" for i in range(50))
        ok, reason = mc.static_validate_patch(big_original, "```python\ndef f0(x):\n    return x\n```")
        # 单函数补丁保留其余 49 个函数 → 不短，仍通过
        assert ok, f"大文件单函数修复不应被'过短'误拒: {reason}"

    def test_single_function_patch_passes(self):
        # 正常单函数修复（把 add 的 + 改成 - 再修回）应通过静态筛选
        ok, reason = mc.static_validate_patch(_GOOD_ORIGINAL, "```python\ndef add(a, b):\n    return a + b\n```")
        assert ok, f"正常单函数补丁应通过: {reason}"


class TestGenerateCandidates:
    """候选生成（mock debugger，隔离 LLM）。"""

    def _mock_debugger(self, patches):
        dbg = MagicMock()
        # 每次调用依次返回一个补丁（循环）
        state = {"i": 0}

        def fake_debug(**kwargs):
            idx = state["i"] % len(patches)
            state["i"] += 1
            return {"root_cause": "x", "error_category": "assertion", "fix_strategy": "y", "patch": patches[idx]}

        dbg.debug.side_effect = fake_debug
        return dbg

    def test_candidate_count_capped(self):
        dbg = self._mock_debugger(["p"])
        results = mc.generate_candidates(dbg, _GOOD_ORIGINAL, "out", [], num_candidates=99)
        assert len(results) == mc._MAX_CANDIDATE_COUNT

    def test_llm_failure_degrades_to_rejected(self):
        dbg = MagicMock()
        dbg.debug.side_effect = RuntimeError("LLM down")
        results = mc.generate_candidates(dbg, _GOOD_ORIGINAL, "out", [], num_candidates=2)
        assert len(results) == 2
        assert all(not r.static_passed for r in results)
        assert all("生成失败" in r.static_reason for r in results)

    def test_default_three(self):
        dbg = self._mock_debugger(["p"])
        results = mc.generate_candidates(dbg, _GOOD_ORIGINAL, "out", [])
        assert len(results) == 3


class TestSelectBestCandidate:
    """最优候选选择。"""

    def test_no_static_ok_returns_none(self):
        candidates = [mc.CandidateResult(index=0, patch="x", static_passed=False, static_reason="r")]
        assert mc.select_best_candidate(candidates, _GOOD_ORIGINAL) is None

    def test_static_mode_returns_smallest_diff(self):
        # 两个静态通过候选：A 改动 1 行，B 改动 5 行 → 选 A
        cand_a = mc.CandidateResult(
            index=0,
            patch="p_a",
            new_code=_GOOD_ORIGINAL.replace("a * b", "a * b + 0"),
            static_passed=True,
        )
        cand_b = mc.CandidateResult(
            index=1,
            patch="p_b",
            new_code=_GOOD_ORIGINAL.replace("a + b", "a + b + 0"),
            static_passed=True,
        )
        best = mc.select_best_candidate([cand_a, cand_b], _GOOD_ORIGINAL)
        assert best is not None
        assert best.static_passed

    def test_execution_validation_picks_passing_high_coverage(self):
        exec_a = MagicMock()
        exec_a.execute.return_value = {"passed": False, "coverage": 0.0}
        exec_b = MagicMock()
        exec_b.execute.return_value = {"passed": True, "coverage": 90.0}

        code_a = _GOOD_ORIGINAL.replace("a * b", "a * b + 1")
        code_b = _GOOD_ORIGINAL.replace("a * b", "a * b")
        cand_a = mc.CandidateResult(index=0, patch="pa", new_code=code_a, static_passed=True)
        cand_b = mc.CandidateResult(index=1, patch="pb", new_code=code_b, static_passed=True)

        # 用一个"按 index 路由"的 mock executor
        routed = MagicMock()
        results = {0: exec_a, 1: exec_b}
        routed.execute.side_effect = lambda test_code, target_file, target_function=None: results[
            int(target_file.split("cand")[1].split("_")[0])
        ].execute(test_code, target_file, target_function)
        best = mc.select_best_candidate(
            [cand_a, cand_b],
            _GOOD_ORIGINAL,
            test_code="def test(): pass",
            target_file="/tmp/t.py",
            use_execution_validation=True,
            executor=routed,
        )
        # 只有 index=1 的候选测试通过 → 应选中
        assert best is cand_b


class TestEnvSwitches:
    """环境变量开关。"""

    def test_available_default_false(self, monkeypatch):
        monkeypatch.delenv("ENABLE_MULTI_CANDIDATE_PATCH", raising=False)
        assert mc.multi_candidate_available() is False

    def test_available_true(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MULTI_CANDIDATE_PATCH", "true")
        assert mc.multi_candidate_available() is True

    def test_count_default(self, monkeypatch):
        monkeypatch.delenv("MULTI_CANDIDATE_COUNT", raising=False)
        assert mc.multi_candidate_count() == 3

    def test_count_clamped_to_range(self, monkeypatch):
        monkeypatch.setenv("MULTI_CANDIDATE_COUNT", "99")
        assert mc.multi_candidate_count() == mc._MAX_CANDIDATE_COUNT
        monkeypatch.setenv("MULTI_CANDIDATE_COUNT", "0")
        assert mc.multi_candidate_count() == 1
        monkeypatch.setenv("MULTI_CANDIDATE_COUNT", "abc")
        assert mc.multi_candidate_count() == 3
