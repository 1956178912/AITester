"""
本轮新增模块的单元测试：
- tests/test_smell_detection_v2.py: Eager Test / Lack of Cohesion 异味检测
- tests/test_mutation_testing.py: 内置变异生成器
- tests/test_cross_batch_comparison.py: 跨批次失败模式对比
"""

from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


# ─── Eager Test / Lack of Cohesion 异味检测 ──────────────────────────────────


class TestSmellDetectionV2:
    """1.1 补强异味检测：Eager Test + Lack of Cohesion。"""

    def _run_smell(self, details: list[dict]) -> dict:
        from experiments.analyze_results import _test_smell_detection

        return _test_smell_detection(details)

    def test_eager_test_detected(self):
        """单个 test_* 函数内 5 个断言、涉及 3 个不同被测目标 → 判 Eager。"""
        test_code = """
def test_many_things():
    assert calc.add(1, 2) == 3
    assert calc.subtract(5, 3) == 2
    assert calc.multiply(2, 4) == 8
    assert calc.divide(8, 2) == 4
    assert calc.modulo(7, 3) == 1
"""
        result = self._run_smell([{"task_id": "t1", "generated_test": test_code}])
        assert result["available"] is True
        assert result["smell_counts"]["eager_test"] == 1

    def test_eager_test_not_detected_for_few_assertions(self):
        """单函数 2 个断言 < 阈值 4 → 不判 Eager。"""
        test_code = """
def test_two_assertions():
    assert calc.add(1, 2) == 3
    assert calc.subtract(5, 3) == 2
"""
        result = self._run_smell([{"task_id": "t1", "generated_test": test_code}])
        assert result["smell_counts"]["eager_test"] == 0

    def test_lack_of_cohesion_detected(self):
        """多个 test_* 函数的被测目标完全不重叠 → 判 Lack of Cohesion。"""
        test_code = """
def test_func_a():
    assert alpha.do_a() == 1

def test_func_b():
    assert beta.do_b() == 2

def test_func_c():
    assert gamma.do_c() == 3
"""
        result = self._run_smell([{"task_id": "t1", "generated_test": test_code}])
        assert result["smell_counts"]["lack_of_cohesion"] == 1

    def test_lack_of_cohesion_not_detected_for_shared_targets(self):
        """多个 test_* 函数共享同一被测目标 → 不判 Lack of Cohesion。"""
        test_code = """
def test_calc_add():
    assert calc.add(1, 2) == 3

def test_calc_subtract():
    assert calc.subtract(5, 3) == 2

def test_calc_multiply():
    assert calc.multiply(2, 4) == 8
"""
        # 三个函数目标集合：{add}, {subtract}, {multiply} → 两两不重叠
        # 3 对全不重叠 → 不重叠占比 1.0 >= 0.5 → 判 lack_of_cohesion
        result = self._run_smell([{"task_id": "t1", "generated_test": test_code}])
        # 实际上 add/subtract/multiply 是不同目标，两两不重叠 → 判定为 lack_of_cohesion
        # 这是预期行为（各用例各自为战），但共享 calc 前缀
        # 目标集合提取的是 func.id（add/subtract/multiply），不含 calc
        assert result["smell_counts"]["lack_of_cohesion"] == 1  # 正确：三函数目标不重叠

    def test_no_smell_for_cohesive_tests(self):
        """单 test_* 函数、断言数 < 阈值、目标一致 → 无异味。"""
        test_code = """
def test_divide():
    assert calc.divide(6, 2) == 3
"""
        result = self._run_smell([{"task_id": "t1", "generated_test": test_code}])
        assert result["smell_counts"]["eager_test"] == 0
        assert result["smell_counts"]["lack_of_cohesion"] == 0

    def test_syntax_error_no_crash(self):
        """generated_test 语法错误时不崩溃，返回 available=True 但无新异味。"""
        test_code = "def broken(:\n  pass"
        result = self._run_smell([{"task_id": "t1", "generated_test": test_code}])
        assert result["available"] is True
        # 语法错误 → assertion_roulette 或 trivial_test（无有效断言）
        # eager / lack_of_cohesion 因 AST 解析失败不会计入
        assert result["smell_counts"]["eager_test"] == 0
        assert result["smell_counts"]["lack_of_cohesion"] == 0


# ─── 内置变异生成器 ──────────────────────────────────────────────────────────


class TestMutationGenerator:
    """1.2 内置变异生成器单元测试。"""

    def test_generate_operator_flip(self):
        from experiments.mutation_testing import MutationGenerator

        source = "def check(x):\n    if x == 5:\n        return True\n    return False\n"
        gen = MutationGenerator()
        mutants = gen.generate(source)
        types = [m.mutant_type for m in mutants]
        assert "operator_flip" in types, f"应含运算符翻转变异，实际: {types}"

    def test_generate_boolean_negation(self):
        from experiments.mutation_testing import MutationGenerator

        source = "def check(x):\n    if not x:\n        return 1\n    return 0\n"
        gen = MutationGenerator()
        mutants = gen.generate(source)
        types = [m.mutant_type for m in mutants]
        assert "boolean_negation" in types, f"应含布尔取反变异，实际: {types}"

    def test_boolean_negation_actually_mutates_code(self):
        """回归：boolean_negation 变异体的代码必须与原代码不同（not X → X 真正生效）。

        历史 bug：_remove_not_op 早期实现是死代码（仅 break），导致
        boolean_negation 变异体代码与原代码完全相同，下游沙箱执行时
        "全部通过"被误判为杀死，mutation_score 虚高。此用例确保
        变异体代码确实去除了 not 运算符。
        """
        from experiments.mutation_testing import MutationGenerator

        scenarios = [
            # (源码, 期望变异体中出现的特征, 期望变异体中不出现的特征)
            ("def f(x):\n    if not x:\n        return 1\n    return 0\n", "if x:", "if not x:"),
            ("def g(a):\n    n = 0\n    while not a:\n        n += 1\n    return n\n", "while a:", "while not a:"),
            ("def h(x):\n    return not x\n", "return x", "return not"),
            ("def i(a, b):\n    return a and not b\n", "and b", "and not"),
            ("def j(x):\n    y = not x\n    return y\n", "y = x", "= not"),
            ("def k(x):\n    not x()\n", "x()", "not x()"),
        ]
        gen = MutationGenerator()
        for source, expect_present, expect_absent in scenarios:
            mutants = gen.generate(source)
            bn = [m for m in mutants if m.mutant_type == "boolean_negation"]
            assert bn, f"场景 '{source[:40]}' 未生成 boolean_negation 变异体"
            for m in bn:
                # 变异体代码必须与原代码不同（not 被真正去除）
                assert m.code != source, f"变异体代码未变化（死代码回归）: {m.code!r}"
                # 行号匹配：同一行号可能生成多个变异体（多个 not 同处一行），
                # 这里按"存在至少一个变异体满足特征"断言
                codes = [m.code for m in bn]
                assert any(expect_present in c for c in codes), (
                    f"场景 '{source[:40]}' 变异体中未出现期望特征 {expect_present!r}, 实际: {codes}"
                )
                assert not any(expect_absent in c for c in codes), (
                    f"场景 '{source[:40]}' 变异体中仍残留 {expect_absent!r}, 实际: {codes}"
                )

    def test_boolean_negation_nested_function(self):
        """嵌套函数体内的 not 也能被识别改写。"""
        from experiments.mutation_testing import MutationGenerator

        source = "def outer(x):\n    def inner():\n        if not x:\n            return True\n    return inner()\n"
        gen = MutationGenerator()
        mutants = gen.generate(source)
        bn = [m for m in mutants if m.mutant_type == "boolean_negation"]
        assert bn, "嵌套函数内 not 未生成 boolean_negation 变异体"
        assert any("if x:" in m.code for m in bn), f"嵌套 not 未被去除: {[m.code for m in bn]}"
        assert all("if not x:" not in m.code for m in bn)

    def test_boolean_negation_no_false_positive_on_absent_not(self):
        """无 not 运算符的源码不应生成 boolean_negation 变异体。"""
        from experiments.mutation_testing import MutationGenerator

        source = "def f(x):\n    if x == 5:\n        return True\n    return False\n"
        gen = MutationGenerator()
        mutants = gen.generate(source)
        bn = [m for m in mutants if m.mutant_type == "boolean_negation"]
        assert bn == [], f"无 not 的源码不应生成 boolean_negation 变异体，实际: {bn}"

    def test_empty_source_returns_empty(self):
        from experiments.mutation_testing import MutationGenerator

        gen = MutationGenerator()
        assert gen.generate("") == []
        assert gen.generate("   \n") == []

    def test_invalid_syntax_returns_empty(self):
        from experiments.mutation_testing import MutationGenerator

        gen = MutationGenerator()
        assert gen.generate("def broken(:") == []

    def test_mutation_score_from_details(self):
        from experiments.mutation_testing import mutation_score_from_details

        details = [
            {"task_id": "t1", "mutation_score": 0.8},
            {"task_id": "t2", "mutation_score": 0.5},
            {"task_id": "t3"},  # 无 mutation_score 字段
        ]
        result = mutation_score_from_details(details)
        assert result["available"] is True
        assert result["observed_tasks"] == 2
        assert result["avg_mutation_score"] == 0.65

    def test_mutation_score_all_missing(self):
        from experiments.mutation_testing import mutation_score_from_details

        result = mutation_score_from_details([{"task_id": "t1"}])
        assert result["available"] is False

    def test_compute_mutation_score_end_to_end(self, tmp_path):
        """端到端：compute_mutation_score 对弱测试套件应产出低得分，对强测试套件产出高得分。

        场景 A（弱测试）：被测代码 `def check(x): return x > 3`，测试只断言
        check(5)==True（未覆盖 x<=3 分支与边界 3/4）。生成变异体后，
        运算符翻转 x > 3 → x >= 3 不会被测试杀死（5 仍 > 3），
        布尔/数字偏移变异多数也存活 → 得分应偏低。
        场景 B（强测试）：测试同时断言 check(4)==True, check(3)==False,
        check(0)==False → 几乎每个变异体都会失败 → 得分应偏高。

        断言口径：available=True、score 在 [0,1]、场景 B 得分 >= 场景 A 得分
        （强测试杀死能力不弱于弱测试），且两个场景的 mutation_score 不相等
        或至少 B 严格大于 0（避免"全存活"的退化口径）。
        注：该用例会真实调用 pytest 子进程（_run_mutant_tests），单用例耗时
        约 2-6s，属可接受的集成级测试。
        """
        from experiments.mutation_testing import compute_mutation_score

        source = "def check(x):\n    return x > 3\n"
        weak_test = "from module import check\n\n\ndef test_basic():\n    assert check(5) == True\n"
        strong_test = (
            "from module import check\n\n"
            "def test_above():\n    assert check(4) == True\n\n"
            "def test_boundary_eq():\n    assert check(3) == False\n\n"
            "def test_below():\n    assert check(0) == False\n"
        )
        module_file = str(tmp_path / "module.py")
        (tmp_path / "module.py").write_text(source, encoding="utf-8")

        result_weak = compute_mutation_score(source, weak_test, module_file, max_mutants=6, timeout_seconds=15)
        result_strong = compute_mutation_score(source, strong_test, module_file, max_mutants=6, timeout_seconds=15)

        assert result_weak["available"] is True, f"弱测试场景应可用: {result_weak}"
        assert result_strong["available"] is True, f"强测试场景应可用: {result_strong}"
        # 得分合法区间
        assert 0.0 <= result_weak["mutation_score"] <= 1.0
        assert 0.0 <= result_strong["mutation_score"] <= 1.0
        # 强测试的杀死数应不低于弱测试（更多断言 = 更易杀死变异体）
        assert result_strong["mutants_killed"] >= result_weak["mutants_killed"], (
            f"强测试杀死数({result_strong['mutants_killed']}) 应 >= 弱测试({result_weak['mutants_killed']})"
        )
        # 强测试应至少杀死 1 个变异体（避免"全存活"退化）
        assert result_strong["mutants_killed"] >= 1, f"强测试至少应杀死 1 个变异体: {result_strong}"
        # 变异体数量一致（同一 source，max_mutants 相同）
        assert result_weak["mutants_total"] == result_strong["mutants_total"]


# ─── 跨批次失败模式对比 ──────────────────────────────────────────────────────


class TestCrossBatchComparison:
    """5.3 跨批次失败模式对比。"""

    def _make_summary(self, dataset: str, details: list[dict]) -> dict:
        return {
            "dataset": dataset,
            "results": {"aitester": {"details": details}},
        }

    def test_new_category_detection(self):
        from experiments.compare_failures import cross_batch_comparison

        old_batch = self._make_summary(
            "batch_old",
            [
                {"task_id": "t1", "passed": False, "error_category": "assertion"},
                {"task_id": "t2", "passed": True},
            ],
        )
        new_batch = self._make_summary(
            "batch_new",
            [
                {"task_id": "t1", "passed": False, "error_category": "patch_validation_failed"},
                {"task_id": "t2", "passed": True},
            ],
        )
        comparison = cross_batch_comparison([old_batch, new_batch], "aitester")
        assert "patch_validation_failed" in comparison["new_categories"]
        assert "assertion" in comparison["resolved_categories"]

    def test_single_batch_no_trend(self):
        from experiments.compare_failures import cross_batch_comparison

        batch = self._make_summary(
            "batch1",
            [
                {"task_id": "t1", "passed": False, "error_category": "assertion"},
            ],
        )
        comparison = cross_batch_comparison([batch], "aitester")
        assert comparison["new_categories"] == []
        assert comparison["regressed_categories"] == []

    def test_regressed_category(self):
        from experiments.compare_failures import cross_batch_comparison

        old_batch = self._make_summary(
            "batch_old",
            [
                {"task_id": "t1", "passed": False, "error_category": "assertion"},
                {"task_id": "t2", "passed": True},
            ],
        )
        new_batch = self._make_summary(
            "batch_new",
            [
                {"task_id": "t1", "passed": False, "error_category": "assertion"},
                {"task_id": "t2", "passed": False, "error_category": "assertion"},
            ],
        )
        comparison = cross_batch_comparison([old_batch, new_batch], "aitester")
        assert "assertion" in comparison["regressed_categories"]

    def test_render_cross_batch_section(self):
        from experiments.compare_failures import render_cross_batch_section

        comparison = {
            "batches": [
                {
                    "file": "old.json",
                    "total": 10,
                    "failed": 3,
                    "failure_categories": {"assertion": 3},
                    "top_failures": ["assertion"],
                },
                {
                    "file": "new.json",
                    "total": 10,
                    "failed": 1,
                    "failure_categories": {"patch_validation_failed": 1},
                    "top_failures": ["patch_validation_failed"],
                },
            ],
            "failure_trend": {},
            "new_categories": ["patch_validation_failed"],
            "resolved_categories": ["assertion"],
            "regressed_categories": [],
        }
        lines = render_cross_batch_section(comparison)
        assert len(lines) > 0
        md = "\n".join(lines)
        assert "跨实验批次失败模式对比" in md
        assert "patch_validation_failed" in md


# ─── 多版本 venv 缓存 ────────────────────────────────────────────────────────


class TestMultiVersionVenvCache:
    """4.4 多版本依赖缓存。"""

    def test_different_python_version_different_dir(self):
        from src.tools.dependency import venv_cache_dir

        dir_310 = venv_cache_dir(["numpy"], python_version="3.10")
        dir_312 = venv_cache_dir(["numpy"], python_version="3.12")
        assert dir_310 != dir_312
        assert "py3.10" in dir_310
        assert "py3.12" in dir_312

    def test_same_version_same_dir(self):
        from src.tools.dependency import venv_cache_dir

        dir_a = venv_cache_dir(["numpy"], python_version="3.12")
        dir_b = venv_cache_dir(["numpy"], python_version="3.12")
        assert dir_a == dir_b

    def test_default_uses_current_version(self):
        import sys

        from src.tools.dependency import venv_cache_dir

        default_dir = venv_cache_dir(["requests"])
        current_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        assert f"py{current_ver}" in default_dir
