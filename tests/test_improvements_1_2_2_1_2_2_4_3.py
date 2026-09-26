"""P0 1.2 / 2.1 / 2.2 / 4.3 新增功能单元测试。

覆盖：
- code_analyzer.preserve_patch_ingredients + render_patch_ingredient_context
- code_context 的契约块追加（focus_function 存在时）
- type_repair.type_repair_layer（静态层 + LLM 层 + 契约回环）
- patch_applier.apply_patch_with_resample（AST 验证 + 重采样）
- synthetic_difficulty.generate_synthetic_task（Level 1-4）
- difficulty_stratification 的 difficulty_level 维度
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ast

from src.tools.code_analyzer import (
    preserve_patch_ingredients,
    render_patch_ingredient_context,
)

# ─── P0 1.2 补丁配方保留 ─────────────────────────────────────────────────────


class TestPreservePatchIngredients:
    """preserve_patch_ingredients 成分识别。"""

    def test_basic_ingredients(self):
        """基础成分识别：import / 常量 / 注册符号 / 目标 AST。"""
        source = (
            "import os\n"
            "from collections import OrderedDict\n"
            "__all__ = ['make_widget', 'register_widget']\n"
            "MAX_RETRY = 3\n"
            "@register\n"
            "def make_widget(name):\n"
            "    return name.upper()\n"
            "def register_widget(name):\n"
            "    return name\n"
        )
        ing = preserve_patch_ingredients(source, target_func="make_widget")
        assert ing["parsed"] is True
        assert "import os" in ing["imports"]
        assert "OrderedDict" in ing["imports"]
        assert "make_widget" in ing["exports"]
        assert "register_widget" in ing["exports"]
        assert "MAX_RETRY" in ing["module_constants"]
        # 注册装饰器识别
        assert "make_widget" in ing["register_symbols"]
        # 目标函数完整 AST
        assert "def make_widget(name):" in ing["target_ast"]
        assert "return name.upper()" in ing["target_ast"]

    def test_no_focus(self):
        """无目标函数：仅模块级契约成分。"""
        source = "import json\nCONST = 1\ndef foo():\n    return 1\n"
        ing = preserve_patch_ingredients(source)
        assert ing["parsed"] is True
        assert ing["target_ast"] == ""
        assert ing["called_signatures"] == []
        assert "CONST" in ing["module_constants"]

    def test_unparseable_source(self):
        """不可解析源码：保守返回空值（parsed=False）。"""
        ing = preserve_patch_ingredients("def broken(:\n")
        assert ing["parsed"] is False
        assert ing["target_ast"] == ""
        assert ing["imports"] == ""

    def test_empty_source(self):
        """空源码：各字段空值。"""
        ing = preserve_patch_ingredients("")
        assert ing["parsed"] is False
        assert ing["exports"] == []

    def test_called_signatures(self):
        """目标函数调用同模块函数时提取调用签名（仅 def 行，不含函数体）。"""
        source = "def helper(x):\n    return x * 2\ndef main(a, b):\n    return helper(a) + helper(b)\n"
        ing = preserve_patch_ingredients(source, target_func="main")
        # main 调用了 helper → 应提取 helper 的签名行（def helper(x):）
        assert len(ing["called_signatures"]) == 1
        assert "def helper(x):" in ing["called_signatures"][0]
        # 签名不含函数体
        assert "return x * 2" not in ing["called_signatures"][0]

    def test_render_block(self):
        """render_patch_ingredient_context 渲染契约块。"""
        source = "import os\n__all__ = ['foo']\n@register\ndef foo():\n    return 1\ndef bar():\n    return foo()\n"
        ing = preserve_patch_ingredients(source, target_func="foo")
        block = render_patch_ingredient_context(ing)
        assert block.startswith("[PATCH_INGREDIENTS]")
        assert "import os" in block
        assert "exports: foo" in block
        assert "register_symbols: foo" in block
        assert "target_ast:" in block
        # bar 是 foo 调用方（非被调方）→ 不在 called_signatures
        assert "called_signatures" not in block

    def test_render_empty(self):
        """空成分渲染为空串。"""
        assert render_patch_ingredient_context({}) == ""
        assert render_patch_ingredient_context(None) == ""
        # 全空字段（parsed=False 场景）
        ing = preserve_patch_ingredients("def x(:\n")
        assert render_patch_ingredient_context(ing) == ""


# ─── P0 1.2 code_context 契约块追加 ──────────────────────────────────────────


class TestCodeContextContractBlock:
    """extract_focused_code_detail 在焦点存在时追加 [PATCH_INGREDIENTS]。"""

    def test_contract_block_appended_when_focus_exists(self):
        from src.tools.code_context import extract_focused_code_detail

        source = "import json\ndef helper(v):\n    return v + 1\ndef target(a):\n    return helper(a)\n"
        # 大预算：不会触发字符级兜底，但焦点存在 → 追加契约块
        result, focus_resolved = extract_focused_code_detail(source, focus_function="target", max_chars=3000, depth=1)
        assert focus_resolved is True
        assert "[PATCH_INGREDIENTS]" in result
        assert "import json" in result

    def test_no_contract_block_without_focus(self):
        from src.tools.code_context import extract_focused_code_detail

        source = "def a():\n    pass\n\ndef b():\n    pass\n"
        result, focus_resolved = extract_focused_code_detail(source, focus_function=None, max_chars=3000)
        # 无焦点 → 不追加契约块
        assert focus_resolved is False
        assert "[PATCH_INGREDIENTS]" not in result

    def test_unparseable_source_no_contract_block(self):
        from src.tools.code_context import extract_focused_code_detail

        bad = "def broken(:\n"
        result, focus_resolved = extract_focused_code_detail(bad, focus_function="broken", max_chars=3000)
        assert focus_resolved is False
        assert result == bad
        assert "[PATCH_INGREDIENTS]" not in result


# ─── 2.1 PAGENT 风格类型修复层 ────────────────────────────────────────────────


class TestTypeRepairLayer:
    """type_repair_layer 静态层 + LLM 层 + 契约回环。"""

    def test_static_findings_type_mismatch(self):
        from src.tools.type_repair import type_repair_layer

        original = "def calc(x):\n    total = 0\n    total = total + 1\n    return total\n"
        # 补丁后代码：total 先 int 后 str（类型冲突）
        patched = "def calc(x):\n    total = 0\n    total = 'oops'\n    return total\n"
        result = type_repair_layer(original, patched)
        # 静态层应识别出类型疑点（total 在函数内 int → str 冲突）
        assert isinstance(result["findings"], list)
        assert result["repaired"] is False  # LLM 层未启用（默认关）
        assert result["repaired_code"] == patched

    def test_no_findings_clean_code(self):
        from src.tools.type_repair import type_repair_layer

        original = "def add(a, b):\n    return a + b\n"
        patched = "def add(a, b):\n    total = 0\n    total = total + a\n    return total + b\n"
        result = type_repair_layer(original, patched)
        # 干净代码不应有类型疑点
        assert result["findings"] == []
        assert result["repaired"] is False

    def test_llm_layer_with_contract_rollback(self):
        """LLM 层修订破坏命名契约时应回滚（保留原补丁）。"""
        import os

        from src.tools.type_repair import type_repair_layer

        # 临时启用 LLM 层（通过 mock llm_repair 回调）
        original = (
            "import json\n"
            "@register\n"
            "def make_widget(name):\n"
            "    return name\n"
            "def process(name):\n"
            "    w = make_widget(name)\n"
            "    total = 0\n"
            "    total = 'x'\n"
            "    return total\n"
        )
        # 修订代码删除了 make_widget（契约破坏）
        bad_repaired = "def process(name):\n    return 1\n"

        def fake_repair(query, orig, patched):
            return bad_repaired

        # monkeypatch 环境变量启用 LLM 层
        old = os.environ.get("TYPE_REPAIR_LLM_ENABLE")
        os.environ["TYPE_REPAIR_LLM_ENABLE"] = "true"
        try:
            result = type_repair_layer(original, original, llm_repair=fake_repair, enforce_contract=True)
        finally:
            if old is not None:
                os.environ["TYPE_REPAIR_LLM_ENABLE"] = old
            else:
                os.environ.pop("TYPE_REPAIR_LLM_ENABLE", None)
        # 契约破坏 → 拒绝修订
        assert result["repaired"] is False
        assert result["contract_ok"] is False
        assert "make_widget" in result["missing_symbols"]
        # 保留原代码
        assert result["repaired_code"] == original

    def test_llm_layer_success(self):
        """LLM 层修订成功且契约通过（原代码与补丁代码相同 → 契约必然通过）。"""
        import os

        from src.tools.type_repair import type_repair_layer

        # original == patched：契约检查 original vs 修订码，修订码保留 process 符号
        shared = "def process(name):\n    total = 0\n    total = 'x'\n    return total\n"
        good_repaired = "def process(name):\n    total = 0\n    total = total + 1\n    return total\n"

        def fake_repair(query, orig, patched):
            return good_repaired

        old = os.environ.get("TYPE_REPAIR_LLM_ENABLE")
        os.environ["TYPE_REPAIR_LLM_ENABLE"] = "true"
        try:
            # original == patched == shared（静态层识别 total int→str 冲突）
            result = type_repair_layer(shared, shared, llm_repair=fake_repair, enforce_contract=True)
        finally:
            if old is not None:
                os.environ["TYPE_REPAIR_LLM_ENABLE"] = old
            else:
                os.environ.pop("TYPE_REPAIR_LLM_ENABLE", None)
        # 修订成功（契约通过：process 符号保留）
        assert result["repaired"] is True
        assert result["repaired_code"] == good_repaired
        assert result["contract_ok"] is True

    def test_llm_repair_invalid_syntax_rejected(self):
        """LLM 修订产出语法非法代码 → 拒绝修订。"""
        import os

        from src.tools.type_repair import type_repair_layer

        original = "def process(name):\n    total = 0\n    total = 'x'\n    return total\n"

        def fake_repair(query, orig, patched):
            return "def broken(:\n"  # 语法错误

        old = os.environ.get("TYPE_REPAIR_LLM_ENABLE")
        os.environ["TYPE_REPAIR_LLM_ENABLE"] = "true"
        try:
            result = type_repair_layer(original, original, llm_repair=fake_repair, enforce_contract=True)
        finally:
            if old is not None:
                os.environ["TYPE_REPAIR_LLM_ENABLE"] = old
            else:
                os.environ.pop("TYPE_REPAIR_LLM_ENABLE", None)
        assert result["repaired"] is False
        assert result["repaired_code"] == original

    def test_undefined_attr_finding(self):
        """补丁引用原代码不存在的顶层名称 → undefined_attr 疑点。"""
        from src.tools.type_repair import type_repair_layer

        original = "def known():\n    return 1\n"
        # 补丁新增代码引用了原代码没有的 helper 函数
        patched = "def known():\n    return helper_missing(1)\ndef other():\n    return 2\n"
        result = type_repair_layer(original, patched)
        # 应识别出 helper_missing 未定义疑点
        kinds = [f["kind"] for f in result["findings"]]
        assert "undefined_attr" in kinds


# ─── 2.2 补丁后处理重采样策略 ─────────────────────────────────────────────────


class TestPatchResample:
    """apply_patch_with_resample：AST 验证 + 失败重采样。"""

    def test_first_attempt_valid(self):
        from src.tools.patch_applier import apply_patch_with_resample

        original = "def foo():\n    return 1\n"
        patch = "def foo():\n    return 2\n"
        code, applied, stats = apply_patch_with_resample(original, patch)
        assert applied is True
        assert "return 2" in code
        assert stats["ast_valid"] is True
        assert stats["resampled"] is False
        assert stats["success"] is True

    def test_first_attempt_invalid_no_resample_fn(self):
        """首尝试 AST 不合法且未注入 resample_fn → 保留原代码。"""
        from src.tools.patch_applier import apply_patch_with_resample

        original = "def foo():\n    return 1\n"
        # 无法应用的补丁（函数名不匹配）
        code, applied, stats = apply_patch_with_resample(original, "def nonexistent():\n    return 1\n")
        # 单函数模式找不到 nonexistent → apply 失败
        assert applied is False
        assert code == original
        assert stats["resampled"] is False
        assert stats["success"] is False

    def test_resample_success(self):
        """首尝试失败 → 重采样回调产出合法补丁 → 成功。"""
        from src.tools.patch_applier import apply_patch_with_resample

        original = "def foo():\n    return 1\n"
        # 第一次给的补丁无法应用
        bad_patch = "def bar():\n    return 1\n"
        calls = {"n": 0}

        def fake_resample(query, orig, patch, ast_error):
            calls["n"] += 1
            # 第一次重采样返回能应用的合法补丁
            return "def foo():\n    return 42\n"

        code, applied, stats = apply_patch_with_resample(
            original, bad_patch, resample_fn=fake_resample, max_resamples=1
        )
        assert applied is True
        assert "return 42" in code
        assert stats["resampled"] is True
        assert stats["resample_count"] == 1
        assert stats["success"] is True
        assert calls["n"] == 1

    def test_resample_exhausted(self):
        """重采样用尽仍失败 → 保留原代码。"""
        from src.tools.patch_applier import apply_patch_with_resample

        original = "def foo():\n    return 1\n"
        bad_patch = "def bar():\n    return 1\n"
        calls = {"n": 0}

        def fake_resample(query, orig, patch, ast_error):
            calls["n"] += 1
            return "def bar():\n    return 1\n"  # 始终无法应用

        code, applied, stats = apply_patch_with_resample(
            original, bad_patch, resample_fn=fake_resample, max_resamples=2
        )
        assert applied is False
        assert code == original
        assert stats["resample_count"] == 2
        assert calls["n"] == 2

    def test_resample_syntax_error_feedback(self):
        """首尝试应用成功但 AST 不合法 → 重采样修正语法。"""
        from src.tools.patch_applier import apply_patch_with_resample

        original = "def foo():\n    return 1\n"
        # 补丁应用后产生语法错误（完整文件模式，补丁本身语法坏）
        bad_patch = '''"""docstring"""
def foo(
    return 1
'''
        calls = {"n": 0}

        def fake_resample(query, orig, patch, ast_error):
            calls["n"] += 1
            # 确认 ast_error 信息被注入
            assert "语法" in ast_error or "无法" in ast_error
            return "def foo():\n    return 2\n"

        code, _applied, stats = apply_patch_with_resample(
            original, bad_patch, resample_fn=fake_resample, max_resamples=1
        )
        assert stats["resampled"] is True
        assert stats["success"] is True
        assert "return 2" in code


# ─── 4.3 多层难度合成任务生成器 ───────────────────────────────────────────────


class TestSyntheticDifficulty:
    """generate_synthetic_task（Level 1-4）。"""

    def test_level1_syntax_valid(self):
        from experiments.synthetic_difficulty import generate_synthetic_task

        task = generate_synthetic_task(1)
        assert task.level == 1
        assert "syn_L1_" in task.task_id
        ast.parse(task.target_code)  # 语法合法
        assert task.target_function == "price_item"

    def test_level2_multi_func(self):
        from experiments.synthetic_difficulty import generate_synthetic_task

        task = generate_synthetic_task(2)
        assert task.level == 2
        # 两个函数都存在
        assert "def parse_record" in task.target_code
        assert "def compute_fee" in task.target_code
        ast.parse(task.target_code)

    def test_level3_cross_file(self):
        from experiments.synthetic_difficulty import generate_synthetic_task

        task = generate_synthetic_task(3)
        assert task.level == 3
        # 跨文件：extra_modules 含 utils
        assert "utils" in task.extra_modules
        assert task.cross_file_deps
        dep = task.cross_file_deps[0]
        assert dep["source_module"] == "entry"
        assert dep["target_module"] == "utils"
        assert dep["symbol"] == "validate_id"
        ast.parse(task.target_code)
        ast.parse(task.extra_modules["utils"])

    def test_level4_boundary(self):
        from experiments.synthetic_difficulty import generate_synthetic_task

        task = generate_synthetic_task(4)
        assert task.level == 4
        ast.parse(task.target_code)
        assert task.target_function == "safe_div"

    def test_invalid_level_raises(self):
        import pytest

        from experiments.synthetic_difficulty import generate_synthetic_task

        with pytest.raises(ValueError):
            generate_synthetic_task(5)

    def test_suite_generation(self):
        from experiments.synthetic_difficulty import generate_synthetic_suite, summarize_suite

        tasks = generate_synthetic_suite(counts={1: 2, 2: 1, 3: 1, 4: 1}, seed=42)
        summary = summarize_suite(tasks)
        assert summary["total"] == 5
        assert summary["by_level"]["1"] == 2
        assert summary["by_level"]["2"] == 1
        assert summary["with_cross_file"] == 1
        assert summary["with_multi_func"] == 1

    def test_suite_reproducible(self):
        from experiments.synthetic_difficulty import generate_synthetic_suite

        t1 = generate_synthetic_suite(counts={1: 2, 2: 2}, seed=123)
        t2 = generate_synthetic_suite(counts={1: 2, 2: 2}, seed=123)
        assert [x.task_id for x in t1] == [x.task_id for x in t2]
        assert [x.target_code for x in t1] == [x.target_code for x in t2]


# ─── 4.3 difficulty_level 分层维度 ───────────────────────────────────────────


class TestDifficultyLevelDimension:
    """stratify_by_dimension 的 difficulty_level 维度。"""

    def test_difficulty_level_buckets(self):
        from experiments.difficulty_stratification import stratify_by_dimension

        details = [
            {"task_id": "t1", "passed": True, "difficulty_level": 1},
            {"task_id": "t2", "passed": False, "difficulty_level": 2},
            {"task_id": "t3", "passed": True, "difficulty_level": 3},
            {"task_id": "t4", "passed": False, "difficulty_level": 4},
            {"task_id": "t5", "passed": True},  # 未标注
        ]
        strat = stratify_by_dimension(details, "difficulty_level")
        assert strat["level_1"]["tasks"] == 1
        assert strat["level_1"]["passed"] == 1
        assert strat["level_2"]["tasks"] == 1
        assert strat["level_3"]["tasks"] == 1
        assert strat["level_4"]["tasks"] == 1
        assert strat["unlabeled"]["tasks"] == 1
        assert strat["unlabeled"]["passed"] == 1

    def test_difficulty_level_from_metadata(self):
        from experiments.difficulty_stratification import stratify_by_dimension

        details = [
            {"task_id": "t1", "passed": True, "task_metadata": {"difficulty_level": 3}},
        ]
        strat = stratify_by_dimension(details, "difficulty_level")
        assert strat["level_3"]["tasks"] == 1

    def test_difficulty_level_string_form_normalizes(self):
        """JSON 反序列化后 difficulty_level 为字符串形态（"3"）时仍归入对应档。

        2026-09-26 修复守卫：此前 `in (1, 2, 3, 4)` 直接判 int，字符串
        形态全部落入 "unlabeled"（4.3 难度分层指标失真）；现纯数字 str
        归一为 int。整数值 float（3.0）与 "3" 同为 JSON/数值计算产物，
        一并归一（仅 1.0-4.0 有档位语义，其余整数值 float 不进档）；
        非数字 str / 带小数 float / bool 保持 "unlabeled"（保守口径）。
        """
        from experiments.difficulty_stratification import stratify_by_dimension

        details = [
            {"task_id": "t1", "passed": True, "difficulty_level": "3"},
            {"task_id": "t2", "passed": False, "task_metadata": {"difficulty_level": "4"}},
            {"task_id": "t3", "passed": True, "difficulty_level": "abc"},
            {"task_id": "t4", "passed": True, "difficulty_level": 3.0},
            {"task_id": "t5", "passed": True, "difficulty_level": 3.5},
            {"task_id": "t6", "passed": True, "difficulty_level": True},
        ]
        strat = stratify_by_dimension(details, "difficulty_level")
        assert strat["level_3"]["tasks"] == 2  # "3" + 3.0
        assert strat["level_4"]["tasks"] == 1  # "4"
        assert strat["unlabeled"]["tasks"] == 3  # "abc" / 3.5 / True

    def test_unknown_dimension_raises(self):
        import pytest

        from experiments.difficulty_stratification import stratify_by_dimension

        with pytest.raises(ValueError):
            stratify_by_dimension([], "not_a_dimension")
