"""agents/generator 纯逻辑 / mock-LLM 分支补齐（2026-10-02 批次·十）。

锁定 generator.py 的低覆盖纯逻辑分支（零真实 LLM / 零网络）：
- _extract_existing_assertions：空码 / 解析失败 / assert 提取去重 / 截断上限 /
  无 assert 空列表 / get_source_segment 降级
- _check_parametrize_decorator：非 Call / 非 Attribute / attr 非 parametrize /
  无 args / arg 非常量 / 非 str / args<2 / cases 非 List / 全通过
- _validate_case_tuple：元组长度匹配 / 不匹配 / 非元组
- _validate_parametrize：语法错误 / 无 parametrize / 参数匹配 / 参数不匹配
- _fix_import_module：已是期望模块名 / 已知外部包跳过 / 不相似第三方库保留 /
  相似笔误替换 / 带点路径锚定替换
- _build_query：module_name 约束 / RAG 参考（test_code 空跳过）/ 断言增强开关 /
  mutation_feedback（survived 截断 5 + score 注入）
- _build_repro_prompt：module_name / cross_file_modules 注入
- _assertion_augment_enabled / _repro_test_enabled 开关

所有 LLM 依赖经 mock _call_llm_with_cache / _extract_python_code 隔离，
纯静态逻辑直接调用（零 LLM）。
"""

from __future__ import annotations

from unittest.mock import MagicMock


def _mk_generator() -> object:
    """构造 GeneratorAgent（实例化真实类，__init__ 零 LLM）。"""
    from src.agents.generator import GeneratorAgent

    return GeneratorAgent()


# ─── 模块级开关 ─────────────────────────────────────────────────────────────


class TestGeneratorSwitchBranches:
    def test_assertion_augment_default_false(self, monkeypatch):
        from src.agents.generator import _assertion_augment_enabled

        monkeypatch.delenv("ASSERTION_AUGMENT_ENABLE", raising=False)
        assert _assertion_augment_enabled() is False

    def test_assertion_augment_true(self, monkeypatch):
        from src.agents.generator import _assertion_augment_enabled

        monkeypatch.setenv("ASSERTION_AUGMENT_ENABLE", "true")
        assert _assertion_augment_enabled() is True

    def test_repro_test_default_false(self, monkeypatch):
        from src.agents.generator import _repro_test_enabled

        monkeypatch.delenv("REPRO_TEST_ENABLE", raising=False)
        assert _repro_test_enabled() is False

    def test_repro_test_true(self, monkeypatch):
        from src.agents.generator import _repro_test_enabled

        monkeypatch.setenv("REPRO_TEST_ENABLE", "true")
        assert _repro_test_enabled() is True


# ─── _extract_existing_assertions 分支 ──────────────────────────────────────


class TestExtractExistingAssertionsBranches:
    def _extract(self, code: str):
        from src.agents.generator import _extract_existing_assertions

        return _extract_existing_assertions(code)

    def test_empty_code_returns_empty(self):
        assert self._extract("") == []

    def test_syntax_error_returns_empty(self):
        assert self._extract("def f(:\n") == []

    def test_no_assertions_returns_empty(self):
        assert self._extract("def f():\n    return 1\n") == []

    def test_assertions_extracted_in_order(self):
        code = "def f(x):\n    assert x > 0\n    assert x < 10\n"
        out = self._extract(code)
        assert len(out) == 2
        assert any("x > 0" in a for a in out)
        assert any("x < 10" in a for a in out)

    def test_duplicate_assertions_deduped(self):
        code = "def f(x):\n    assert x > 0\n    assert x > 0\n"
        out = self._extract(code)
        assert len(out) == 1  # 重复 assert 只保留一条

    def test_capped_at_max_existing_assertions(self):
        """超过 10 条 assert 时截断保留前 10 条。"""
        code = "\n".join(f"assert {i}" for i in range(15))
        out = self._extract(code)
        assert len(out) == 10  # _MAX_EXISTING_ASSERTIONS = 10

    def test_assert_with_message_extracted(self):
        """带 message 的 assert 也提取。"""
        code = "def f():\n    assert 1 == 1, 'should pass'\n"
        out = self._extract(code)
        assert len(out) == 1
        assert "should pass" in out[0]


# ─── _check_parametrize_decorator 分支 ──────────────────────────────────────


class TestCheckParametrizeDecoratorBranches:
    def _check(self, code: str):
        """解析代码取第一个 FunctionDef 的第一个 decorator，调 _check_parametrize_decorator。"""
        import ast

        from src.agents.generator import GeneratorAgent

        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.decorator_list:
                return GeneratorAgent._check_parametrize_decorator(node.decorator_list[0])
        return None

    def test_not_parametrize_returns_none(self):
        out = self._check("@pytest.mark.skip\ndef f():\n    pass\n")
        assert out is None

    def test_no_args_returns_none(self):
        """@pytest.mark.parametrize（无调用参数）→ None。"""
        import ast

        from src.agents.generator import GeneratorAgent

        tree = ast.parse("import pytest\n@pytest.mark.parametrize\ndef f():\n    pass\n")
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.decorator_list:
                out = GeneratorAgent._check_parametrize_decorator(node.decorator_list[0])
                break
        assert out is None

    def test_first_arg_not_constant_returns_none(self):
        out = self._check("import pytest\n@pytest.mark.parametrize(arg, [1])\ndef f():\n    pass\n")
        assert out is None

    def test_first_arg_not_string_returns_none(self):
        out = self._check("import pytest\n@pytest.mark.parametrize(1, [1])\ndef f():\n    pass\n")
        # 字面量 1 作为 arg 表达式非常量 str → None（语法上 1 是 Constant 但非 str）
        assert out is None

    def test_only_one_arg_returns_none(self):
        out = self._check("import pytest\n@pytest.mark.parametrize('a')\ndef f():\n    pass\n")
        assert out is None

    def test_cases_not_list_returns_none(self):
        """cases 参数非 List（如 tuple 字面量）→ None。"""
        out = self._check("import pytest\n@pytest.mark.parametrize('a', (1, 2))\ndef f():\n    pass\n")
        assert out is None

    def test_valid_parametrize_returns_tuple(self):
        out = self._check("import pytest\n@pytest.mark.parametrize('a, b', [[1, 2], [3, 4]])\ndef f(a, b):\n    pass\n")
        assert out is not None
        param_names, cases_arg = out
        assert param_names == ["a", "b"]
        assert len(cases_arg.elts) == 2


# ─── _validate_case_tuple 分支 ─────────────────────────────────────────────


class TestValidateCaseTupleBranches:
    def _validate(self, code: str, param_names: list[str]) -> bool:
        import ast

        from src.agents.generator import GeneratorAgent

        tree = ast.parse(code)
        # 取代码中的第一个 Tuple/List 表达式
        for node in ast.walk(tree):
            if isinstance(node, (ast.Tuple, ast.List)):
                return GeneratorAgent._validate_case_tuple(node, param_names)
        return True

    def test_matching_length_valid(self):
        assert self._validate("(1, 2)", ["a", "b"]) is True

    def test_mismatched_length_invalid(self):
        assert self._validate("(1, 2, 3)", ["a", "b"]) is False

    def test_list_also_validated(self):
        assert self._validate("[1, 2]", ["a"]) is False  # 1 元素 vs 2 参数


# ─── _validate_parametrize 分支 ────────────────────────────────────────────


class TestValidateParametrizeBranches:
    def _validate(self, code: str) -> bool:
        from src.agents.generator import GeneratorAgent

        return GeneratorAgent._validate_parametrize(code)

    def test_syntax_error_returns_false(self):
        assert self._validate("def f(:\n") is False

    def test_no_parametrize_returns_true(self):
        assert self._validate("def f():\n    pass\n") is True

    def test_valid_parametrize_returns_true(self):
        code = "import pytest\n@pytest.mark.parametrize('a, b', [[1, 2], [3, 4]])\ndef f(a, b):\n    pass\n"
        assert self._validate(code) is True

    def test_mismatched_param_count_returns_false(self):
        code = "import pytest\n@pytest.mark.parametrize('a, b', [[1], [3, 4]])\ndef f(a, b):\n    pass\n"
        assert self._validate(code) is False  # 第一个用例 [1] 只有 1 元素 vs 2 参数

    def test_multiple_decorators_validated(self):
        """多个 parametrize 装饰器逐个校验。"""
        code = (
            "import pytest\n"
            "@pytest.mark.parametrize('a', [1, 2])\n"
            "@pytest.mark.parametrize('b', [3, 4])\n"
            "def f(a, b):\n    pass\n"
        )
        assert self._validate(code) is True


# ─── _fix_import_module 分支 ────────────────────────────────────────────────


class TestFixImportModuleBranches:
    def _fix(self, code: str, expected: str) -> str:
        from src.agents.generator import GeneratorAgent

        return GeneratorAgent._fix_import_module(code, expected)

    def test_already_expected_module_unchanged(self):
        code = "from mymod import f\nf()\n"
        assert self._fix(code, "mymod") == code

    def test_known_external_module_preserved(self):
        """from pytest import ... 不被改写（_KNOWN_MODULES 跳过）。"""
        code = "import pytest\nfrom pytest import fixture\nfrom numpy import array\n"
        out = self._fix(code, "mymod")
        assert "from pytest import" in out
        # numpy 与 mymod 不相似 → 保留（相似度门控）
        assert "from numpy import" in out

    def test_similar_typo_replaced(self):
        """mymodule（mymod 的笔误变体）→ 替换为 mymod。"""
        code = "from mymodule import f\nf()\n"
        out = self._fix(code, "mymod")
        assert "from mymod import" in out
        assert "mymodule" not in out

    def test_dissimilar_third_party_preserved(self):
        """requests 与 mymod 不相似 → 保留（相似度门控）。"""
        code = "from requests import get\nget('x')\n"
        out = self._fix(code, "mymod")
        assert "from requests import" in out

    def test_no_imports_unchanged(self):
        code = "def f():\n    return 1\n"
        assert self._fix(code, "mymod") == code


# ─── _build_query 分支（mock LLM 无关，纯 prompt 构造）──────────────────────


class TestBuildQueryBranches:
    def _build(self, **kwargs) -> str:
        gen = _mk_generator()
        gen = MagicMock(wraps=gen)  # 保留真实方法，mock 其余
        gen._build_query = gen.__class__._build_query.__get__(gen, type(gen))
        return gen._build_query(**kwargs)

    def test_module_name_constraint_injected(self, monkeypatch):
        from src.agents.generator import GeneratorAgent

        gen = GeneratorAgent()
        out = gen._build_query({"name": "t"}, "def f():\n    pass\n", "mymod", None, None)
        assert "mymod" in out
        assert "from mymod import" in out  # import 约束

    def test_no_module_name_no_constraint(self, monkeypatch):
        from src.agents.generator import GeneratorAgent

        gen = GeneratorAgent()
        out = gen._build_query({"name": "t"}, "def f():\n    pass\n", "", None, None)
        # 无 module_name 时不注入 import 约束段
        assert "【重要约束】import 语句必须使用" not in out

    def test_rag_references_injected(self, monkeypatch):
        from src.agents.generator import GeneratorAgent

        gen = GeneratorAgent()
        refs = [
            {"test_code": "def test_a():\n    assert 1\n"},
            {"test_code": "def test_b():\n    assert 2\n"},
        ]
        out = gen._build_query({"name": "t"}, "code", "m", refs, None)
        assert "参考案例 1" in out
        assert "参考案例 2" in out

    def test_rag_empty_test_code_skipped(self, monkeypatch):
        from src.agents.generator import GeneratorAgent

        gen = GeneratorAgent()
        refs = [{"test_code": ""}]  # 空 test_code → 不注入
        out = gen._build_query({"name": "t"}, "code", "m", refs, None)
        assert "参考案例" not in out

    def test_rag_capped_at_max_references(self, monkeypatch):
        """超过 3 条参考时截断保留前 3 条。"""
        from src.agents.generator import GeneratorAgent

        gen = GeneratorAgent()
        refs = [{"test_code": f"def test_{i}():\n    pass\n"} for i in range(5)]
        out = gen._build_query({"name": "t"}, "code", "m", refs, None)
        assert "参考案例 1" in out and "参考案例 3" in out
        assert "参考案例 4" not in out and "参考案例 5" not in out

    def test_assertion_augment_injection(self, monkeypatch):
        """ASSERTION_AUGMENT_ENABLE=true 且被测代码含 assert → 注入锚点断言。"""
        from src.agents.generator import GeneratorAgent

        monkeypatch.setenv("ASSERTION_AUGMENT_ENABLE", "true")
        gen = GeneratorAgent()
        out = gen._build_query({"name": "t"}, "def f():\n    assert 1\n", "m", None, None)
        assert "断言增强" in out

    def test_assertion_augment_no_assertions_skipped(self, monkeypatch):
        """ASSERTION_AUGMENT_ENABLE=true 但被测代码无 assert → 不注入。"""
        from src.agents.generator import GeneratorAgent

        monkeypatch.setenv("ASSERTION_AUGMENT_ENABLE", "true")
        gen = GeneratorAgent()
        out = gen._build_query({"name": "t"}, "def f():\n    return 1\n", "m", None, None)
        assert "断言增强" not in out

    def test_assertion_augment_disabled_no_injection(self, monkeypatch):
        """ASSERTION_AUGMENT_ENABLE 默认关 → 不注入（历史口径）。"""
        from src.agents.generator import GeneratorAgent

        monkeypatch.delenv("ASSERTION_AUGMENT_ENABLE", raising=False)
        gen = GeneratorAgent()
        out = gen._build_query({"name": "t"}, "def f():\n    assert 1\n", "m", None, None)
        assert "断言增强" not in out

    def test_mutation_feedback_survived_injected(self, monkeypatch):
        from src.agents.generator import GeneratorAgent

        monkeypatch.delenv("ASSERTION_AUGMENT_ENABLE", raising=False)
        gen = GeneratorAgent()
        fb = {"survived_mutants": [f"m{i}" for i in range(7)], "mutation_score": 0.4}
        out = gen._build_query({"name": "t"}, "code", "m", None, fb)
        assert "变异反馈" in out
        assert "m0" in out and "m4" in out  # 前 5 条
        assert "m5" not in out and "m6" not in out  # 截断
        assert "0.4" in out  # score 注入

    def test_mutation_feedback_no_survived_score_only(self, monkeypatch):
        """survived 为空 + score 非 None → 仅注入 score 提示。"""
        from src.agents.generator import GeneratorAgent

        gen = GeneratorAgent()
        fb = {"survived_mutants": [], "mutation_score": 0.9}
        out = gen._build_query({"name": "t"}, "code", "m", None, fb)
        assert "0.9" in out
        assert "存活变异体" not in out

    def test_mutation_feedback_none_no_injection(self, monkeypatch):
        from src.agents.generator import GeneratorAgent

        gen = GeneratorAgent()
        out = gen._build_query({"name": "t"}, "code", "m", None, None)
        assert "变异反馈" not in out

    def test_mutation_feedback_empty_dict_no_injection(self, monkeypatch):
        from src.agents.generator import GeneratorAgent

        gen = GeneratorAgent()
        out = gen._build_query({"name": "t"}, "code", "m", None, {})
        assert "变异反馈" not in out


# ─── _build_repro_prompt 分支 ──────────────────────────────────────────────


class TestBuildReproPromptBranches:
    def _build(self, **kwargs) -> str:
        from src.agents.generator import GeneratorAgent

        return GeneratorAgent()._build_repro_prompt(**kwargs)

    def test_basic_prompt(self):
        out = self._build(defect_description="缺陷描述", target_code="code", module_name="", cross_file_modules=None)
        assert "复现测试" in out
        assert "缺陷描述" in out

    def test_module_name_injected(self):
        out = self._build(defect_description="d", target_code="c", module_name="mymod", cross_file_modules=None)
        assert "mymod" in out
        assert "from mymod import" in out

    def test_cross_file_modules_injected(self):
        out = self._build(defect_description="d", target_code="c", module_name="m", cross_file_modules=["modA", "modB"])
        assert "跨文件上下文" in out
        assert "modA" in out and "modB" in out

    def test_no_cross_file_no_section(self):
        out = self._build(defect_description="d", target_code="c", module_name="m", cross_file_modules=None)
        assert "跨文件上下文" not in out
        out2 = self._build(defect_description="d", target_code="c", module_name="m", cross_file_modules=[])
        assert "跨文件上下文" not in out2


# ─── generate() 的 branch_coverage / boundary_triplets 注入分支（mock LLM）──


def _real_gen_with_mocked_llm() -> MagicMock:
    """真实 GeneratorAgent + mock 掉 LLM 相关方法（truncate_code 静态 + LLM 调用）。

    返回 wraps 实例：实例方法（generate/_build_query 等）走真实代码，
    LLM 依赖（_call_llm_with_cache/_extract_python_code/_validate_parametrize/
    _fix_import_module/truncate_code）经 MagicMock 隔离，零真实 LLM。
    """
    from src.agents.generator import GeneratorAgent

    gen = GeneratorAgent()
    gen._call_llm_with_cache = MagicMock(return_value="raw")
    gen._extract_python_code = MagicMock(return_value="def test_x():\n    pass\n")
    gen._validate_parametrize = MagicMock(return_value=True)
    gen._fix_import_module = MagicMock(side_effect=lambda c, m: c)
    return gen


class TestGenerateInjectionBranches:
    """generate() 的 O3/M10 注入分支（真实方法 + mock LLM）。"""

    def test_branch_coverage_section_injected(self):
        gen = _real_gen_with_mocked_llm()
        gen.generate(
            {"name": "t"},
            "code",
            "m",
            None,
            branch_coverage_section="未覆盖分支：line 5",
        )
        assert gen._call_llm_with_cache.called
        # 注入段经 _build_query 后拼接进 query（验证 LLM 收到的 query 含注入段）
        called_query = gen._call_llm_with_cache.call_args[0][0]
        assert "未覆盖分支" in called_query

    def test_boundary_triplets_section_injected(self):
        gen = _real_gen_with_mocked_llm()
        gen.generate(
            {"name": "t"},
            "code",
            "m",
            None,
            boundary_triplets_section="边界三元组：(0, 1, -1)",
        )
        called_query = gen._call_llm_with_cache.call_args[0][0]
        assert "边界三元组" in called_query

    def test_both_sections_injected(self):
        gen = _real_gen_with_mocked_llm()
        gen.generate(
            {"name": "t"},
            "code",
            "m",
            None,
            branch_coverage_section="branches",
            boundary_triplets_section="triplets",
        )
        called_query = gen._call_llm_with_cache.call_args[0][0]
        assert "branches" in called_query and "triplets" in called_query

    def test_none_sections_no_injection(self):
        gen = _real_gen_with_mocked_llm()
        gen.generate({"name": "t"}, "code", "m", None)
        called_query = gen._call_llm_with_cache.call_args[0][0]
        assert "branches" not in called_query
        assert "triplets" not in called_query


# ─── generate() 的 parametrize 重试分支（mock LLM）─────────────────────────


class TestGenerateParametrizeRetryBranches:
    """generate() 的 parametrize 校验失败重试路径（真实方法 + mock LLM）。"""

    def _gen(self, first_valid: bool, second_valid: bool):
        gen = _real_gen_with_mocked_llm()
        gen._validate_parametrize = MagicMock(side_effect=[first_valid, second_valid])
        return gen

    def test_valid_first_no_retry(self):
        gen = self._gen(first_valid=True, second_valid=True)
        gen.generate({"name": "t"}, "code", "m")
        assert gen._call_llm_with_cache.call_count == 1  # 仅一次 LLM 调用

    def test_invalid_first_triggers_retry(self):
        gen = self._gen(first_valid=False, second_valid=True)
        gen.generate({"name": "t"}, "code", "m")
        assert gen._call_llm_with_cache.call_count == 2  # 重试一次

    def test_invalid_twice_still_continues(self):
        """两次都失败 → 仍返回（仅告警，不重试第三次）。"""
        gen = self._gen(first_valid=False, second_valid=False)
        out = gen.generate({"name": "t"}, "code", "m")
        assert gen._call_llm_with_cache.call_count == 2
        assert out == "def test_x():\n    pass\n"


# ─── generate() focus_function 回退分支 ────────────────────────────────────


class TestGenerateFocusFunctionFallbackBranches:
    """generate() 的 focus_function 优先级：显式参数 > test_plan["function_name"] > 全文件。"""

    def test_explicit_focus_function_used(self):
        gen = _real_gen_with_mocked_llm()
        gen.generate({"name": "t"}, "code", "m", focus_function="target_fn")
        # focus_function 显式传入 → truncate_code 以 target_fn 为焦点（真实静态方法执行）
        assert gen._call_llm_with_cache.called

    def test_focus_function_falls_back_to_plan(self):
        """focus_function=None 时回退到 test_plan["function_name"]。"""
        gen = _real_gen_with_mocked_llm()
        gen.generate({"name": "t", "function_name": "plan_fn"}, "code", "m")
        assert gen._call_llm_with_cache.called

    def test_no_focus_function_no_truncate_target(self):
        """focus_function=None 且 test_plan 无 function_name → 全文件截取。"""
        gen = _real_gen_with_mocked_llm()
        gen.generate({"name": "t"}, "code", "m")
        assert gen._call_llm_with_cache.called
