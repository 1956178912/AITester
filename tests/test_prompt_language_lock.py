#!/usr/bin/env python3
"""提示词语言锁：任何流向 LLM 的文本必须是英文（2026-11-04 用户第 13 条指令）。

背景：提示词与代码库语言不一致会引入一个未被记录的混淆变量——模型对中文指令
与英文代码的响应，和纯英文 prompt 不同，而该差异不体现在任何被对照的开关上。
因此"全英文提示词"必须是一条可执行的锁，而不是一次性清理。

覆盖面 = 注入通道的全部构造器（核心 system prompt 由 `prompt-artifacts` 哈希锁
单独锁定）。断言只针对**本项目生成的框架文本**：数据集内容（被测代码、人类
docstring、LLM 回显的 reasoning）原样透传，不在本锁管辖内。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

#: 中日韩统一表意文字（含扩展 A）；全角标点与中文引号一并视为非英文框架文本
_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_FULLWIDTH = re.compile(r"[　-〿＀-￯]")

pytestmark = pytest.mark.unit


def _assert_english(text: str, surface: str) -> None:
    """断言构造出的 prompt 文本不含中文（指出首个命中位置便于定位）。"""
    if not text:
        return
    hits = [(m.start(), m.group(0)) for m in _CJK.finditer(text)]
    assert not hits, (
        f"{surface} 含 {len(hits)} 处中文字符，首个在 offset {hits[0][0]}：{hits[0][1]!r}\n---\n{text[:400]}"
    )
    # 全角标点同样禁止：`：`/`（）` 是中文段的指纹，留着一个就等于留着一类漂移
    fw = [(m.start(), m.group(0)) for m in _FULLWIDTH.finditer(text)]
    assert not fw, f"{surface} 含 {len(fw)} 处全角标点，首个：{fw[0][1]!r}"


# ─── 核心 system prompt（与 prompt-artifacts 清单同源，这里做语言面复核）────────


def test_registered_system_prompts_are_english() -> None:
    from src.prompts import templates

    names = [
        "PLANNER_SYSTEM_PROMPT",
        "GENERATOR_SYSTEM_PROMPT",
        "DEBUGGER_SYSTEM_PROMPT",
        "ORACLE_ENHANCER_SYSTEM_PROMPT",
        "SPEC_EXPR_CONTRACT_SECTION",
    ]
    surfaces = {f"templates.{name}": getattr(templates, name, None) for name in names}
    # 缺席/改名不再是"跳过"：本例必须先证明清单真的取到了文本，才谈得上判语言
    assert not _empty_surfaces(surfaces), f"注册名缺席或为空 ⇒ 语言锁未判：{_empty_surfaces(surfaces)}"
    for name, value in surfaces.items():
        _assert_english(value, name)


def test_nodes_intervention_sections_are_english(monkeypatch: pytest.MonkeyPatch) -> None:
    """detection-first / over-red 干预段（prompt-artifacts 已锁哈希，这里锁语言）。

    本例此前用 `getattr(nodes, "_DETECTION_FIRST_SECTION", None)` 找**模块常量**，
    而这两段其实是 `_detection_first_section(state)` / `_over_red_section(state)`
    两个函数的返回值——三个名字全部 getattr 到 None，`isinstance(value, str)` 把
    它们静默滤掉，一条也没判（假绿，由零断言门在本次首读时抓出）。名字清单现按
    写入端（函数）取，开关与路由判据打桩为真，只判返回文本的语言。
    """
    from src.graph import nodes

    monkeypatch.setattr(nodes, "_detection_first_section_enabled", lambda: True, raising=True)
    monkeypatch.setattr(nodes, "_over_red_section_enabled", lambda: True, raising=True)
    monkeypatch.setattr(nodes, "_detection_first_regenerate_entry", lambda _state: True, raising=True)
    monkeypatch.setattr(nodes, "_specificity_over_red_regenerate_entry", lambda _state: True, raising=True)
    state: dict[str, Any] = {"test_passed": True}
    surfaces = {
        "nodes._detection_first_section": nodes._detection_first_section(state),
        "nodes._over_red_section": nodes._over_red_section(state),
    }
    assert not _empty_surfaces(surfaces), f"干预段缺席 ⇒ 语言锁未判：{_empty_surfaces(surfaces)}"
    for name, value in surfaces.items():
        _assert_english(value, name)


# ─── 注入型段落构造器：逐个覆盖其分支 ────────────────────────────────────────

_SPEC_MATERIAL: dict[str, Any] = {
    "function_name": "add",
    "human_spec": "Input: two ints\nOutput: their sum",
    "logic_analysis": {
        # fixture 数据用 ASCII：本锁测的是构造器自己生成的框架文本，
        # 数据若为 ASCII，则任何中文命中必然来自脚手架。
        "preconditions": ["a and b are ints"],
        "postconditions": ["result equals the sum"],
        "invariants": ["order independent"],
        "edge_cases": ["either argument is 0"],
        "preconditions_expr": ["isinstance(a, int)"],
        "postconditions_expr": ["result == a + b"],
        "invariants_expr": [],
    },
}
_SPEC_CODE = 'def add(a: int, b: int) -> int:\n    """Return the sum of a and b."""\n    return a - b\n'


def test_spec_first_sections() -> None:
    from src.tools.spec_first import build_spec_augment_section, build_spec_replace_section

    for builder in (build_spec_replace_section, build_spec_augment_section):
        section = builder(_SPEC_MATERIAL, _SPEC_CODE, "mathops", "add")
        assert section, f"{builder.__name__} 返回空串，本用例形同虚设"
        _assert_english(section, builder.__name__)
        for token in (
            "[Spec-",
            "Function signature: ",
            "Module under test: ",
            "[Documented contract (docstring)]",
            "[Natural-language specification",
            "[Executable specification",
            "- Precondition: ",
            "- Postcondition (executable): ",
            "[Generation discipline",
        ):
            assert token in section, f"{builder.__name__} 缺框架标记 {token!r}"


def _empty_surfaces(surfaces: dict[str, Any]) -> list[str]:
    """返回空/纯空白/缺席的片段名——空片段会让 `_assert_english` 直接返回，等于该处不判。"""
    return sorted(name for name, text in surfaces.items() if not (text or "").strip())


def test_control_flow_and_path_sections() -> None:
    from src.tools.control_flow import (
        analyze_control_flow,
        build_cfg_prompt_section,
        build_paths_prompt_section,
        enumerate_paths,
    )

    source = (
        "def f(xs, n):\n"
        "    if n > 0:\n"
        "        for x in xs:\n"
        "            if x:\n"
        "                print(x)\n"
        "    else:\n"
        "        raise ValueError('neg')\n"
        "    return n\n"
    )
    cfg = analyze_control_flow(source, "f")
    paths = enumerate_paths(source)
    # 简单函数的降级分支也要英文
    simple = analyze_control_flow("def g():\n    return 1\n", "g")
    surfaces = {
        "cfg.path_hint": str(cfg.get("path_hint", "")),
        "build_cfg_prompt_section": build_cfg_prompt_section(cfg),
        "build_paths_prompt_section": build_paths_prompt_section(paths),
        "cfg.path_hint(simple)": str(simple.get("path_hint", "")),
    }
    for name, text in surfaces.items():
        _assert_english(text, name)
    assert not _empty_surfaces(surfaces), f"空片段使语言锁形同虚设：{_empty_surfaces(surfaces)}"


def test_logic_spec_and_boundary_sections() -> None:
    from src.tools.logic_spec import (
        build_boundary_triplets_section,
        build_logic_spec_findings_section,
        derive_boundary_triplets,
        validate_logic_spec,
    )

    _assert_english(build_logic_spec_findings_section(validate_logic_spec(None)), "logic_spec.findings")
    _assert_english(
        build_logic_spec_findings_section(validate_logic_spec({"input_domain": "x"})),
        "logic_spec.findings(partial)",
    )
    triplets_src = "def f(x):\n    if x > 3:\n        return 1\n    if x < 0:\n        return 2\n    return 0\n"
    triplets = derive_boundary_triplets(triplets_src, "f")
    assert triplets, "边界三元组为空，本用例形同虚设"
    _assert_english(build_boundary_triplets_section(triplets), "logic_spec.boundaries")


def test_feedback_compression_and_operation_map() -> None:
    from src.tools.feedback_compression import build_feedback_compression_section
    from src.tools.operation_map import build_operation_map, build_operation_map_section

    compressed = {
        "error_category": "assertion",
        "failed_tests": ["test_a", "test_b"],
        "target_lines": [{"lineno": 3, "origin": "traceback", "source": "stmt"}],
        "survived_mutants": ["line 3: > → >= (boundary shift)"],
        "mutation_score": 0.4,
    }
    opmap = build_operation_map("def f(x):\n    return x + 1\n\nclass C: pass\n\nLIMIT = 3\n")
    surfaces = {
        "feedback_compression": build_feedback_compression_section(compressed),
        "operation_map": build_operation_map_section(opmap),
    }
    for name, text in surfaces.items():
        _assert_english(text, name)
    assert not _empty_surfaces(surfaces), f"空片段使语言锁形同虚设：{_empty_surfaces(surfaces)}"


def test_branch_coverage_and_localized_edit_sections() -> None:
    from src.tools.branch_coverage_inject import build_branch_coverage_prompt_section
    from src.tools.patch_localized import build_localized_edit_section

    coverage = {"branch_coverage": 40.0, "missing_branches": [{"line": 2, "to": 5}, {"line": 7}]}
    loc = {
        "function_name": "mod.f",
        "line_start": 4,
        "line_end": 6,
        "reasoning": "off-by-one on the loop bound",
        "candidates": [
            {"function_name": "mod.f", "line_start": 4, "line_end": 6, "confidence": 0.9},
            {"function_name": "mod.g", "line_start": 9, "line_end": 9, "confidence": 0.4},
        ],
    }
    surfaces = {
        "branch_coverage": build_branch_coverage_prompt_section(coverage),
        "patch_localized": build_localized_edit_section(loc),
    }
    for name, text in surfaces.items():
        _assert_english(text, name)
    assert not _empty_surfaces(surfaces), f"空片段使语言锁形同虚设：{_empty_surfaces(surfaces)}"


def test_mutation_runtime_probe_and_localization_sections() -> None:
    from src.agents.fault_localizer import build_localization_prompt_section
    from src.agents.runtime_probe import build_probe_prompt_section
    from src.graph.mutation_advisor import build_mutation_prompt_section

    feedback = {"survived_mutants": ["line 3: 1 → 0 (constant replacement)"], "mutation_score": 0.25}
    snapshot = {"frames": [{"function": "f", "file": "m.py", "line": 3, "locals": {"n": 5}}]}
    loc_info = {"function_name": "f", "line_start": 2, "line_end": 3, "confidence": 0.8, "reasoning": "x"}
    surfaces = {
        "mutation_advisor": build_mutation_prompt_section(feedback),
        "runtime_probe": build_probe_prompt_section(snapshot),
        "fault_localizer.section": build_localization_prompt_section(loc_info),
    }
    for name, text in surfaces.items():
        _assert_english(text, name)
    assert not _empty_surfaces(surfaces), f"空片段使语言锁形同虚设：{_empty_surfaces(surfaces)}"


def test_graphrag_and_multi_candidate_sections() -> None:
    from src.tools.graphrag import build_graphrag_prompt_section
    from src.tools.multi_candidate import candidate_variant_prompt

    result = {
        "subgraph": [{"source_module": "a", "symbol": "f", "target_module": "b", "call_line": 3}],
        "text_snippets": ["snippet"],
        "anchor_symbols": [("a", "f")],
    }
    surfaces = {"graphrag": build_graphrag_prompt_section(result)}
    # 第 4 个复用取模变体，也要覆盖
    surfaces.update({f"multi_candidate.variant{index}": candidate_variant_prompt(index, 3) for index in range(4)})
    for name, text in surfaces.items():
        _assert_english(text, name)
    assert not _empty_surfaces(surfaces), f"空片段使语言锁形同虚设：{_empty_surfaces(surfaces)}"


def test_failure_kb_snippet_is_english(tmp_path: Path) -> None:
    from src.agents.failure_kb import kb_debugger_snippet

    path = tmp_path / "kb.json"
    path.write_text(
        json.dumps(
            [
                {
                    "error_category": "assertion",
                    # fixture 数据用 ASCII：命中中文必然来自片段脚手架
                    "problem": "assertion copies the implementation",
                    "root_cause": "oracle-from-implementation",
                    "fix": "derive the expected value from the specification",
                    "verification": "red then green pair",
                    "occurrences": 3,
                    "last_seen": 1_760_000_000,
                }
            ]
        ),
        encoding="utf-8",
    )
    import os

    os.environ["FAILURE_KB_ENABLE"] = "true"
    os.environ["FAILURE_KB_PATH"] = str(path)
    try:
        snippet = kb_debugger_snippet("assertion")
    finally:
        os.environ.pop("FAILURE_KB_ENABLE", None)
        os.environ.pop("FAILURE_KB_PATH", None)
    assert snippet, "KB 片段未生成，本用例形同虚设"
    _assert_english(snippet, "failure_kb")


def test_spec_refine_prompt_is_english() -> None:
    from src.specs import spec_refine

    builder = getattr(spec_refine, "_build_refine_prompt", None)
    assert callable(builder), "spec_refine._build_refine_prompt 不存在，本用例形同虚设"
    prompt = builder(
        "def f(x):\n    return x\n",
        {"preconditions": ["x > 0"], "postconditions": ["r == x"], "invariants": []},
        {"precondition": {"status": "unsat"}, "postcondition": {"status": "sat"}},
    )
    _assert_english(prompt, "spec_refine.prompt")


def test_mutation_operator_descriptions_are_english() -> None:
    """存活变异体描述经 `f"{i}. {desc}"` 原样进入 Generator prompt，故属提示词面。"""
    sys.path.insert(0, str(PROJECT_ROOT))
    from experiments.mutation_testing import MutationGenerator

    source = (
        "def f(xs, n):\n"
        "    total = 0\n"
        "    for x in xs:\n"
        "        if n > 3 and x != 2:\n"
        "            total = total + x\n"
        "        else:\n"
        "            raise ValueError(xs)\n"
        "    return total\n"
    )
    mutants = MutationGenerator().generate(source)
    assert mutants, "变异体生成为空，本用例形同虚设（换样本或检查 MutationGenerator.generate 签名）"
    seen_types: set[str] = set()
    for mutant in mutants:
        seen_types.add(str(mutant.mutant_type))
        _assert_english(str(mutant.description), f"mutant[{mutant.mutant_type}]")
    # 覆盖到的算子族要足够广，否则这条锁只测了一两个分支
    assert len(seen_types) >= 4, f"仅覆盖 {sorted(seen_types)}，样本不足以锁住算子描述面"
