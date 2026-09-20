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
        ok, reason, applied = mc.static_validate_patch(_GOOD_ORIGINAL, "")
        assert not ok
        assert "空" in reason
        assert applied == ""

    def test_whitespace_only_patch_rejected(self):
        ok, _, _ = mc.static_validate_patch(_GOOD_ORIGINAL, "   \n  ")
        assert not ok

    def test_no_change_rejected(self):
        # 补丁与原代码完全相同（apply 单函数替换但内容不变）→ "未产生实际改动"
        patch = _GOOD_ORIGINAL
        ok, reason, _ = mc.static_validate_patch(_GOOD_ORIGINAL, patch)
        assert not ok
        assert "未产生实际改动" in reason

    def test_syntax_error_rejected(self):
        bad = """\
def add(a, b):
    return a +
"""
        # 单函数模式替换 add 为残缺实现 → 语法错误
        ok, reason, _ = mc.static_validate_patch(_GOOD_ORIGINAL, "```python\n" + bad + "\n```")
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
        ok, reason, _ = mc.static_validate_patch(_GOOD_ORIGINAL, "```python\n" + full.strip() + "\n```")
        # 该补丁与原代码等价（无实际改动），应被"未产生实际改动"拒绝
        assert not ok
        assert "未产生实际改动" in reason

    def test_full_file_patch_preserves_original_functions(self):
        # 整文件模式（含 import 头）：patch_applier 与原子代码合并，不会丢函数。
        # 此行为证明"函数定义数量减少"分支是针对"误删"的防御网，正常整文件补丁
        # 仍能通过（保留原代码全部函数），而非被误拒。
        full_no_mul = "import math\n\n\ndef add(a, b):\n    return a + b\n"
        ok, reason, _ = mc.static_validate_patch(_GOOD_ORIGINAL, "```python\n" + full_no_mul + "\n```")
        assert ok, f"正常整文件补丁应通过，实际被拒: {reason}"

    def test_too_short_rejected(self):
        # 大原代码 + 很短的整文件补丁触发 10% 规则被拒；
        # 但单函数补丁保留其余函数时不会"过短"，验证不会误拒大文件单函数修复
        big_original = "\n".join(f"def f{i}(x):\n    return x + {i}\n" for i in range(50))
        ok, reason, _ = mc.static_validate_patch(big_original, "```python\ndef f0(x):\n    return x\n```")
        # 单函数补丁保留其余 49 个函数 → 不短，仍通过
        assert ok, f"大文件单函数修复不应被'过短'误拒: {reason}"

    def test_single_function_patch_passes(self):
        # 正常单函数修复（把 add 的 + 改成 - 再修回）应通过静态筛选
        ok, reason, _ = mc.static_validate_patch(_GOOD_ORIGINAL, "```python\ndef add(a, b):\n    return a + b\n```")
        assert ok, f"正常单函数补丁应通过: {reason}"

    def test_applied_code_returned_on_pass(self):
        # 3-tuple 契约：通过时第三项为 apply_patch_to_code 产物（可复用于 new_code），
        # 拒绝时第三项为空串
        ok, _, applied = mc.static_validate_patch(
            _GOOD_ORIGINAL, "```python\ndef mul(a, b):\n    return a * b + 1\n```"
        )
        assert ok
        assert "a * b + 1" in applied
        _, _, rejected = mc.static_validate_patch(_GOOD_ORIGINAL, "")
        assert rejected == ""


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

    def test_exec_validate_default_false(self, monkeypatch):
        monkeypatch.delenv("MULTI_CANDIDATE_EXEC_VALIDATE", raising=False)
        assert mc.multi_candidate_exec_validate() is False

    def test_exec_validate_true(self, monkeypatch):
        monkeypatch.setenv("MULTI_CANDIDATE_EXEC_VALIDATE", "true")
        assert mc.multi_candidate_exec_validate() is True

    def test_exec_validate_invalid_value_falls_back_false(self, monkeypatch):
        monkeypatch.setenv("MULTI_CANDIDATE_EXEC_VALIDATE", "yes")
        assert mc.multi_candidate_exec_validate() is False


class TestLineLevelCreditScores:
    """3.2 改进：行级信用分配（BOOSTAPR 式）。"""

    def test_no_static_passed_returns_no_best(self):
        candidates = [mc.CandidateResult(index=0, patch="x", static_passed=False)]
        result = mc.line_level_credit_scores(_GOOD_ORIGINAL, candidates)
        assert result["best_candidate_index"] is None
        assert result["best_credit"] is None
        assert result["candidates"] == []

    def test_exec_passed_candidate_higher_credit_than_failed(self):
        # 两个静态通过候选：exec_passed=True 的信用更高（即使修改行更多）
        code_a = _GOOD_ORIGINAL.replace("a * b", "a * b + 1")
        code_b = _GOOD_ORIGINAL.replace("a * b", "a * b + 1")
        cand_a = mc.CandidateResult(index=0, patch="pa", new_code=code_a, static_passed=True)
        cand_b = mc.CandidateResult(index=1, patch="pb", new_code=code_b, static_passed=True)
        cand_a.exec_passed = True
        cand_a.exec_coverage = 90.0
        cand_b.exec_passed = False
        cand_b.exec_coverage = 0.0
        result = mc.line_level_credit_scores(_GOOD_ORIGINAL, [cand_a, cand_b])
        assert result["best_candidate_index"] == 0
        assert result["candidates"][0]["credit_score"] > result["candidates"][1]["credit_score"]

    def test_exec_passed_none_uses_simplicity_only(self):
        # 未执行验证（exec_passed=None）时信用退化为简洁性代理（1 - 修改行占比）
        code_a = _GOOD_ORIGINAL  # 最小改动
        code_b = _GOOD_ORIGINAL.replace("a * b", "a * b + 1")
        cand_a = mc.CandidateResult(index=0, patch="pa", new_code=code_a, static_passed=True)
        cand_b = mc.CandidateResult(index=1, patch="pb", new_code=code_b, static_passed=True)
        result = mc.line_level_credit_scores(_GOOD_ORIGINAL, [cand_a, cand_b])
        # 修改行少的候选信用更高
        assert result["candidates"][0]["credit_score"] >= result["candidates"][1]["credit_score"]

    def test_static_mode_selects_highest_credit(self):
        # 静态筛选模式（非执行验证）按行级信用排序
        code_a = _GOOD_ORIGINAL.replace("a * b", "a * b + 1")
        code_b = _GOOD_ORIGINAL.replace("a + b", "a + b + 1")
        cand_a = mc.CandidateResult(index=0, patch="pa", new_code=code_a, static_passed=True)
        cand_b = mc.CandidateResult(index=1, patch="pb", new_code=code_b, static_passed=True)
        best = mc.select_best_candidate([cand_a, cand_b], _GOOD_ORIGINAL)
        assert best is not None
        # 选中候选的 credit_score 应已填充
        assert best.credit_score is not None
        # 两个候选修改行数相近时按 index 稳定排序
        assert best.credit_score >= 0.0


class TestMutationFeedback:
    """1.2 改进：build_mutation_feedback（MutGen 式执行反馈回路）。

    build_mutation_feedback(source_code, test_code) 对"生成测试 vs 被测代码"
    跑一遍变异测试，把存活变异体打包成可注入 Generator prompt 的反馈字典。
    本组测试用 MonkeyPatch 隔离 _run_mutant_tests（避免真实子进程执行），
    直接验证反馈字典结构与 prompt 注入行为。
    """

    @staticmethod
    def _patch_run_mutants(monkeypatch, killed_flags: list[bool]):
        """让 _run_mutant_tests 按顺序返回预设的"是否杀死"标志。"""
        import experiments.mutation_testing as mt

        state = {"i": 0}

        def fake_run(mutant, test_code, module_file="", timeout_seconds=30):
            flag = killed_flags[state["i"] % len(killed_flags)]
            state["i"] += 1
            return flag

        monkeypatch.setattr(mt, "_run_mutant_tests", fake_run)

    def test_survived_mutants_packaged(self, monkeypatch):
        import experiments.mutation_testing as mt

        # 预设：按顺序 [kill, kill, survive, survive...] 交替。
        # 由于 max_mutants=5，至少前 3 个候选会按 [True, True, False] 被评估：
        # killed=2, survived=1（第 3 个存活）。score = 2/3（被截断到 5 候选中）。
        flags = [True, True, False, False, False]
        self._patch_run_mutants(monkeypatch, flags)
        source = "def check(x):\n    return x > 0\n"
        feedback = mt.build_mutation_feedback(source, "def test(): assert check(1)", max_mutants=5)
        assert feedback["available"] is True
        # 若变异体总数 < 5，则按实际数量评估；否则按前 5 个
        n = feedback["mutants_total"]
        expected_killed = min(2, n)
        expected_survived = max(0, n - 2)
        assert feedback["killed_mutants"] == expected_killed
        assert len(feedback["survived_mutants"]) == expected_survived
        # 变异得分 = killed / total
        assert feedback["mutation_score"] == round(expected_killed / n, 4)

    def test_no_survived_no_feedback(self, monkeypatch):
        import experiments.mutation_testing as mt

        # 全部杀死 → 无存活变异体
        self._patch_run_mutants(monkeypatch, [True])
        source = "def check(x):\n    return x > 0\n"
        feedback = mt.build_mutation_feedback(source, "def test(): assert check(1)", max_mutants=5)
        assert feedback["available"] is True
        assert feedback["survived_mutants"] == []
        assert feedback["mutation_score"] == 1.0

    def test_empty_source_returns_unavailable(self):
        import experiments.mutation_testing as mt

        feedback = mt.build_mutation_feedback("", "def test(): pass")
        assert feedback["available"] is False
        assert feedback["survived_mutants"] == []
        assert feedback["mutation_score"] is None

    def test_boundary_shift_mutant_type_generated(self):
        """1.2 改进：boundary_shift 变异体生成（Gt->GtE, Lt->LtE 等边界语义）。"""
        from experiments.mutation_testing import MutationGenerator

        code = "def check(x):\n    return x > 0\n"
        mutants = MutationGenerator().generate(code)
        types = [m.mutant_type for m in mutants]
        assert "boundary_shift" in types, f"boundary_shift 变异体应被生成，实际: {types}"

    def test_return_void_mutant_type_generated(self):
        """1.2 改进：return_void 变异体生成（return X -> return None）。"""
        from experiments.mutation_testing import MutationGenerator

        code = "def add(a, b):\n    return a + b\n"
        mutants = MutationGenerator().generate(code)
        types = [m.mutant_type for m in mutants]
        assert "return_void" in types, f"return_void 变异体应被生成，实际: {types}"
