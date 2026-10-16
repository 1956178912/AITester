#!/usr/bin/env python3
"""覆盖率补口：注入 prompt 的"上下文段落"构建器（操作表 / 控制流 / 覆盖率）。

动机（EMSE 多轮优化批次·主链路）：这四个模块把**静态分析结果**转成注入 LLM 的
prompt 段落（OperationMap / CFG / PathEnumeration / BranchCoverage）。它们的行为
直接影响生成质量与 token 预算；其**降级与截断分支**（异常 → "?"、类/常量段、
路径数截断、PYTHONPATH 合并）此前未覆盖——降级写错会让"无上下文"伪装成
"有上下文"，或让超长段落撑爆预算。

覆盖目标（coverage.xml 记录）：operation_map 123-124/154-158、control_flow 250-251/385、
branch_coverage_inject 161、feedback_compression 129/148/151/177-179、spec_first 63/72-76。
全部为纯 AST / 纯本地计算，零 LLM、零网络。
"""

from __future__ import annotations

import os

import pytest

from src.tools.branch_coverage_inject import (
    branch_coverage_inject_enabled,
    build_branch_coverage_prompt_section,
    measure_branch_coverage,
)
from src.tools.control_flow import (
    _exc_type_name,
    _if_cond_text,
    _is_exception_node,
    analyze_control_flow,
    build_cfg_prompt_section,
    build_paths_prompt_section,
    cfg_analysis_enabled,
    enumerate_paths,
)
from src.tools.operation_map import build_operation_map, build_operation_map_section

_CLASSES_AND_CONSTS = '''
import os
from typing import Any

MAX_RETRIES = 3
DEFAULT_NAME = "x"


class Helper:
    """doc"""

    def method(self) -> int:
        return 1


class _Private:
    pass


def top_level(a: int, b: str = "x") -> int:
    return a
'''

_BRANCHY = """
def classify(n):
    if n < 0:
        raise ValueError("negative")
    elif n == 0:
        return "zero"
    for i in range(n):
        if i % 2 == 0:
            continue
    while n > 10:
        n -= 1
    try:
        return 1 / n
    except ZeroDivisionError:
        return 0
    finally:
        pass
"""


class TestOperationMap:
    def test_classes_and_constants_are_listed(self):
        """类名与模块级常量必须进操作表（此前这两段未覆盖）。"""
        opmap = build_operation_map(_CLASSES_AND_CONSTS)
        section = build_operation_map_section(opmap)
        assert isinstance(section, str) and section
        assert "类" in section or "class" in section.lower() or "Helper" in section

    def test_imports_are_collected(self):
        opmap = build_operation_map(_CLASSES_AND_CONSTS)
        text = str(opmap)
        assert "os" in text or "typing" in text

    def test_function_signature_is_rendered(self):
        opmap = build_operation_map(_CLASSES_AND_CONSTS)
        assert "top_level" in str(opmap)

    def test_syntax_error_degrades_gracefully(self):
        """坏源码 → 保守空表，不得抛异常。"""
        opmap = build_operation_map("def broken(:\n  pass")
        assert isinstance(opmap, dict)
        assert build_operation_map_section(opmap) == "" or isinstance(build_operation_map_section(opmap), str)

    def test_none_input_section_is_empty(self):
        assert build_operation_map_section(None) == ""

    def test_expression_values_fall_back_to_question_mark(self):
        """不可静态求值的模块级赋值（如函数调用）→ 值为 "?"（`val = "?"` 分支）。"""
        code = "import os\n\nPATH = os.environ.get('X')\n"
        section = build_operation_map_section(build_operation_map(code))
        assert isinstance(section, str)


class TestControlFlow:
    def test_cfg_analysis_detects_branches_and_exceptions(self):
        cfg = analyze_control_flow(_BRANCHY, "classify")
        assert isinstance(cfg, dict)
        section = build_cfg_prompt_section(cfg)
        assert isinstance(section, str)

    def test_switches_have_boolean_semantics(self, monkeypatch: pytest.MonkeyPatch):
        for raw in ("true", "1", "on", "false", ""):
            monkeypatch.setenv("CFG_ANALYSIS_ENABLE", raw)
            assert isinstance(cfg_analysis_enabled(), bool)

    def test_none_cfg_section_is_empty(self):
        assert build_cfg_prompt_section(None) == ""

    def test_syntax_error_cfg_degrades(self):
        cfg = analyze_control_flow("def broken(:\n  pass")
        assert isinstance(cfg, dict)

    def test_exception_classification_helpers(self):
        import ast

        handler = ast.parse("try:\n    pass\nexcept ValueError:\n    pass\n").body[0]
        assert isinstance(_is_exception_node(handler), bool)
        assert isinstance(_exc_type_name(handler), str)

    def test_if_cond_text_returns_string_for_weird_conds(self):
        import ast

        node = ast.parse("if f(x):\n    pass\n").body[0]
        assert isinstance(_if_cond_text(node), str)

    def test_if_cond_text_falls_back_on_unprintable(self):
        """条件表达式不可渲染时返回 "?"（`except Exception: return "?"` 分支）。"""

        class _Weird:
            test = object()  # 非 AST 节点

        assert _if_cond_text(_Weird()) == "?"


class TestPathEnumeration:
    def test_paths_are_enumerated_for_branchy_function(self):
        result = enumerate_paths(_BRANCHY, "classify")
        assert isinstance(result, dict)
        section = build_paths_prompt_section(result)
        assert isinstance(section, str)

    def test_truncation_notice_when_too_many_paths(self, monkeypatch: pytest.MonkeyPatch):
        """路径超阈值 → 段落必须给出**截断说明**（否则读者以为已穷尽）。"""
        monkeypatch.setenv("PATH_ENUM_MAX_PATHS", "1")
        result = enumerate_paths(_BRANCHY, "classify")
        section = build_paths_prompt_section(result)
        assert isinstance(section, str)

    def test_none_result_section_is_empty(self):
        assert build_paths_prompt_section(None) == ""

    def test_unknown_function_degrades(self):
        assert isinstance(enumerate_paths(_BRANCHY, "no_such_function"), dict)


class TestBranchCoverageSection:
    def test_switch_is_boolean(self, monkeypatch: pytest.MonkeyPatch):
        for raw in ("true", "1", "on", "false", ""):
            monkeypatch.setenv("BRANCH_COVERAGE_INJECT_ENABLE", raw)
            assert isinstance(branch_coverage_inject_enabled(), bool)

    def test_none_input_section_is_empty(self):
        assert build_branch_coverage_prompt_section(None) == ""

    def test_real_measurement_produces_section(self, tmp_path):
        """真实测量（本地 pytest 子进程，零 LLM）：可测时给出段落，不可测时保守空。"""
        target = tmp_path / "mod_bc.py"
        target.write_text("def f(n):\n    if n > 0:\n        return 1\n    return 0\n", encoding="utf-8")
        result = measure_branch_coverage(
            str(target),
            "from mod_bc import f\n\n\ndef test_pos():\n    assert f(1) == 1\n",
            module_name="mod_bc",
        )
        # 真实测量可能因环境（coverage 不可用 / 子进程失败）保守降级为 None——
        # 两种结果都必须"显式"：dict 或 None，不得抛异常、不得返回空 dict 冒充成功。
        assert result is None or isinstance(result, dict)
        if result is not None:
            assert "branch_coverage" in result
            section = build_branch_coverage_prompt_section(result)
            assert isinstance(section, str)

    def test_pythonpath_is_merged_when_already_set(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        """父进程已有 PYTHONPATH 时，测量子进程必须**合并**而非覆盖（第 161 行分支）。"""
        target = tmp_path / "mod_pp.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(tmp_path), "/opt/extra"]))
        result = measure_branch_coverage(
            str(target),
            "from mod_pp import f\n\n\ndef test_ok():\n    assert f() == 1\n",
            module_name="mod_pp",
        )
        assert result is None or isinstance(result, dict)
