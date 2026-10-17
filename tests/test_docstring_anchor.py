#!/usr/bin/env python3
"""P1（2026-10-17 独立评审 §6 P1 / A-02）：docstring 独立规格锚回归锁定。

锁定四组行为：
1. 模块级人类规格提取（`src/tools/spec_first.py::module_spec_text`）：
   - QuixBugs 风格尾部规格块 / 仅模块 docstring / 多处字面量（尾部优先）/
     无字面量 / 语法错误 / 中文文本 / 函数体内字面量不误取；
   - 真实 QuixBugs 数据：40/41 有 human_spec（`node.py` 缺失，本地数据缺失时跳过）。
2. human_spec 渲染契约（`build_spec_replace_section`）：
   - **金标记**：不带 `human_spec` 键的 Planner 锚材料渲染字符串逐字节不变
     （期望值以固化的完整字面量锁定，不动态 import 旧实现——护住 df_spec
     历史工件的可复现性）；
   - `human_spec` 键在场即材料（空串也进入判定）→ 渲染空/省略但触发 replace；
   - 段落位置在【文档化契约（docstring）】之前，实现代码永不进产物。
3. 锚表构建（`experiments/build_docstring_anchor_table.py`）：
   - 内容寻址键 = sha256(源码.strip())；覆盖统计（41/40 口径）；
   - 确定性（两次运行输出逐字节一致）；缺数据目录/程序数不符 fail-fast；
   - union 模式并入 Planner `logic_analysis`（未命中只保留 human_spec）。
4. 臂接线（`experiments/run_benchmark.py`）：
   - BASELINE_REGISTRY 注册两臂；默认表路径按臂区分；env DOC_ANCHOR_TABLE 覆盖；
   - 命中注入 state["spec_anchor"] + 线程规格覆盖 "replace" + 检出优先覆盖，
     finally 全恢复；表缺失/损坏逐任务回落 df 口径（不 crash）；
   - DOC_ANCHOR_TABLE 已入 `_env_snapshot_keys`（provenance 留痕）；
   - 既有 df_spec 臂默认路径/行为未被改动。

全部测试零 LLM / 零网络 / 确定性（真实数据用例在数据缺失时 skip）。
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.tools.spec_first import (
    build_spec_replace_section,
    module_spec_text,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_QUIXBUGS_DATA = _REPO_ROOT / "data" / "quixbugs"
_PLANNER_ANCHOR_TABLE = _REPO_ROOT / "experiments" / "results" / "emse_spec_anchor_20261016" / "SPEC_ANCHOR_TABLE.json"
_REAL_DATA_AVAILABLE = (_QUIXBUGS_DATA / "python_programs").is_dir() and _PLANNER_ANCHOR_TABLE.is_file()

# ─── 金标记：HEAD（含 df_spec A-10）Planner 锚渲染的完整期望字符串 ────────────
# 本字面量由改动前实现（git show HEAD:src/tools/spec_first.py）生成后固化；
# 测试**不**动态 import 旧版——它锁的是"历史工件可复现性"，不是实现细节。
_GOLDEN_HEADER = [
    "【规格优先模式（Spec-First）：本提示刻意不包含实现代码】",
    "请仅依据以下规约文档与函数签名生成测试。实现细节未知且**不得臆测**——",
    "照猜想中的实现行为写断言（oracle-from-implementation）会系统性抹掉缺陷检出，",
    "是本模式要杜绝的首要失败形态。",
    "",
]
_GOLDEN_CODE = (
    'def add(a: int, b: int) -> int:\n    """Return the sum of a and b."""\n    return a - b  # BUG: should be a + b\n'
)
_GOLDEN_PLANNER_MATERIAL: dict[str, Any] = {
    "function_name": "add",
    "logic_analysis": {
        "preconditions": ["a、b 为整数"],
        "postconditions": ["返回值等于两数之和"],
        "invariants": ["结果与参数顺序无关"],
        "edge_cases": ["任一参数为 0 时返回另一参数"],
        "preconditions_expr": ["isinstance(a, int) and isinstance(b, int)"],
        "postconditions_expr": ["result == a + b"],
        "invariants_expr": [],
    },
}
_GOLDEN_SECTION = "\n".join(
    [
        *_GOLDEN_HEADER,
        "函数签名：def add(a: int, b: int) -> int",
        "被测模块名：mathops（import 必须 `from mathops import ...`）",
        "",
        "【文档化契约（docstring）】",
        "Return the sum of a and b.",
        "",
        "【自然语言规约（期望值的唯一合法来源）】",
        "- 前置条件：a、b 为整数",
        "- 后置条件：返回值等于两数之和",
        "- 不变量：结果与参数顺序无关",
        "- 边界情况：任一参数为 0 时返回另一参数",
        "",
        "【可执行规约（SpecExpr 形式化子句，可直接转写为断言）】",
        "- 前置（可执行）：isinstance(a, int) and isinstance(b, int)",
        "- 后置（可执行）：result == a + b",
        "",
        "【生成纪律】",
        "1. 每个测试必须断言上述规约中可判定的性质（后置 / 不变量 / 边界）；",
        "2. 期望值只能来自规约与 docstring 约定；规约未覆盖的行为禁止臆造具体值——",
        "   改用记录实际行为的探索性断言并在 docstring 标注需人工确认；",
        "3. 输入构造必须满足前置条件（不满足前件的输入应走 pytest.raises 路径或排除）；",
        "4. 不得访问规约与签名之外的属性 / 符号。",
    ]
)
_GOLDEN_DISCIPLINE = [
    "",
    "【生成纪律】",
    "1. 每个测试必须断言上述规约中可判定的性质（后置 / 不变量 / 边界）；",
    "2. 期望值只能来自规约与 docstring 约定；规约未覆盖的行为禁止臆造具体值——",
    "   改用记录实际行为的探索性断言并在 docstring 标注需人工确认；",
    "3. 输入构造必须满足前置条件（不满足前件的输入应走 pytest.raises 路径或排除）；",
    "4. 不得访问规约与签名之外的属性 / 符号。",
]
# 第二个金标记（无 docstring 的 Planner 材料；同样逐字节锁定）
_GOLDEN_SMALL_CODE = "def fn(x):\n    return x - 1\n"
_GOLDEN_SMALL_MATERIAL: dict[str, Any] = {
    "function_name": "fn",
    "logic_analysis": {"postconditions": ["返回 x"], "postconditions_expr": ["result == x"]},
}
_GOLDEN_SMALL_SECTION = "\n".join(
    [
        *_GOLDEN_HEADER,
        "函数签名：def fn(x)",
        "被测模块名：m（import 必须 `from m import ...`）",
        "",
        "【自然语言规约（期望值的唯一合法来源）】",
        "- 后置条件：返回 x",
        "",
        "【可执行规约（SpecExpr 形式化子句，可直接转写为断言）】",
        "- 后置（可执行）：result == x",
        *_GOLDEN_DISCIPLINE,
    ]
)

# ─── 测试夹具：QuixBugs 形态程序 ────────────────────────────────────────────
_TAIL_SPEC = (
    "Bitcount\nbitcount\n\n\nInput:\n    n: a nonnegative int\n\n"
    "Output:\n    The number of 1-bits in the binary encoding of n\n"
)
_PROGRAM_TAIL = (
    "def bitcount(n):\n"
    "    count = 0\n"
    "    while n:\n"
    "        n ^= n - 1\n"
    "        count += 1\n"
    "    return count\n\n\n"
    '"""\n' + _TAIL_SPEC + '"""\n'
)
_PROGRAM_CLASS_ONLY = "class Node:\n    def __init__(self, value=None):\n        self.value = value\n"
_PROGRAM_MODULE_DOCSTRING = '"""Add two ints.\n\nInput: a, b\n"""\n\n\ndef add(a, b):\n    return a - b\n'
_PROGRAM_MULTI_STRING = (
    '"""Module docstring."""\n\n\ndef f(x):\n    """Function docstring."""\n    return x\n\n\n"""Tail spec block."""\n'
)


def _write_program(data_dir: Path, name: str, source: str) -> Path:
    programs = data_dir / "python_programs"
    programs.mkdir(parents=True, exist_ok=True)
    path = programs / name
    path.write_text(source, encoding="utf-8")
    return path


@pytest.fixture()
def quixbugs_dir(tmp_path: Path) -> Path:
    """3 个程序的迷你 QuixBugs 数据目录（尾部规格 / 纯类 / 模块 docstring）。"""
    data = tmp_path / "quixbugs"
    _write_program(data, "bitcount.py", _PROGRAM_TAIL)
    _write_program(data, "node.py", _PROGRAM_CLASS_ONLY)
    _write_program(data, "add.py", _PROGRAM_MODULE_DOCSTRING)
    _write_program(data, "bitcount_test.py", "def test_bitcount():\n    assert True\n")  # 测试驱动，应排除
    return data


def _sha360(source: str) -> str:
    return hashlib.sha256(source.strip().encode("utf-8")).hexdigest()


# ─── 1. module_spec_text 提取边界 ────────────────────────────────────────────
class TestModuleSpecText:
    @pytest.mark.unit
    def test_tail_spec_block_extracted(self) -> None:
        """QuixBugs 形态：函数在前、人类规格块在文件尾部。"""
        assert module_spec_text(_PROGRAM_TAIL) == _TAIL_SPEC.strip()

    @pytest.mark.unit
    def test_module_docstring_fallback(self) -> None:
        """只有首句模块 docstring 时返回它（无尾部块）。"""
        assert module_spec_text(_PROGRAM_MODULE_DOCSTRING) == "Add two ints.\n\nInput: a, b"

    @pytest.mark.unit
    def test_multiple_non_doc_literals_take_tail(self) -> None:
        """多个非首句字面量：取最靠后者（尾部规格块语义）。"""
        source = 'def f():\n    return 1\n\n\n"""FIRST_BLOCK"""\n\n\n"""TAIL_BLOCK"""\n'
        assert module_spec_text(source) == "TAIL_BLOCK"

    @pytest.mark.unit
    def test_module_docstring_plus_tail_prefers_tail(self) -> None:
        """模块 docstring 与尾部规格块并存 → 优先尾部（非首句）。"""
        assert module_spec_text(_PROGRAM_MULTI_STRING) == "Tail spec block."

    @pytest.mark.unit
    def test_no_string_literals_returns_empty(self) -> None:
        assert module_spec_text(_PROGRAM_CLASS_ONLY) == ""
        assert module_spec_text("x = 1\ny = x + 1\n") == ""

    @pytest.mark.unit
    def test_empty_source_returns_empty(self) -> None:
        assert module_spec_text("") == ""

    @pytest.mark.unit
    def test_syntax_error_returns_empty(self) -> None:
        """语法错误 → 空串（无异常泄漏）。"""
        assert module_spec_text("def broken(:\n") == ""
        assert module_spec_text("def f():\n    return\x00 1\n") == ""

    @pytest.mark.unit
    def test_whitespace_only_literals_ignored(self) -> None:
        source = 'def f():\n    return 1\n\n\n"""   """\n\n\n"""   \n\t """\n'
        assert module_spec_text(source) == ""

    @pytest.mark.unit
    def test_function_and_class_body_strings_ignored(self) -> None:
        """函数/类内部字符串不是模块级规格块。"""
        source = 'def f():\n    """FUNCTION_DOC"""\n    return 1\n\n\nclass C:\n    """CLASS_DOC"""\n    pass\n'
        assert module_spec_text(source) == ""

    @pytest.mark.unit
    def test_assignment_string_not_counted(self) -> None:
        """赋值语句里的字符串不是模块级独立字面量语句。"""
        assert module_spec_text('S = "not a spec block"\n') == ""
        assert module_spec_text('S = "x"\n\n\n"""REAL_BLOCK"""\n') == "REAL_BLOCK"

    @pytest.mark.unit
    def test_non_string_constant_ignored(self) -> None:
        assert module_spec_text("42\n") == ""
        assert module_spec_text('42\n\n\n"""SPEC_AFTER_NUMBER"""\n') == "SPEC_AFTER_NUMBER"

    @pytest.mark.unit
    def test_chinese_spec_text_preserved(self) -> None:
        source = 'def f():\n    return 1\n\n\n"""\n输入：\n    x：非负整数\n\n输出：\n    x 的二进制 1 位数\n"""\n'
        spec = module_spec_text(source)
        assert "输入：" in spec
        assert "x：非负整数" in spec
        assert spec.endswith("x 的二进制 1 位数")

    @pytest.mark.unit
    def test_first_statement_string_is_docstring(self) -> None:
        """首条语句即字符串 = 模块 docstring（无尾部块时返回它）。"""
        assert module_spec_text('"""Just a module docstring."""\n\n\ndef f():\n    return 1\n') == (
            "Just a module docstring."
        )

    @pytest.mark.unit
    @pytest.mark.skipif(not _QUIXBUGS_DATA.is_dir(), reason="QuixBugs 数据不在本地（CI 跳过）")
    def test_real_quixbugs_coverage_40_of_41(self) -> None:
        """真实 QuixBugs：40/41 缺陷程序可提取人类规格；唯一缺失 node.py。"""
        programs_dir = _QUIXBUGS_DATA / "python_programs"
        present: list[str] = []
        missing: list[str] = []
        for path in sorted(programs_dir.glob("*.py")):
            if path.name.endswith("_test.py"):
                continue
            (present if module_spec_text(path.read_text(encoding="utf-8")) else missing).append(path.stem)
        assert len(present) + len(missing) == 41
        assert len(present) == 40
        assert missing == ["node"]


# ─── 2. human_spec 渲染契约 ─────────────────────────────────────────────────
class TestHumanSpecRendering:
    @pytest.mark.unit
    def test_golden_planner_material_byte_identical(self) -> None:
        """金标记：不带 human_spec 键的 Planner 锚渲染逐字节不变（历史可复现性）。"""
        section = build_spec_replace_section(
            _GOLDEN_PLANNER_MATERIAL, _GOLDEN_CODE, module_name="mathops", target_function="add"
        )
        assert section == _GOLDEN_SECTION
        assert "独立于实现的规格锚（人类 docstring）" not in section

    @pytest.mark.unit
    def test_golden_planner_material_second_fixture(self) -> None:
        section = build_spec_replace_section(_GOLDEN_SMALL_MATERIAL, _GOLDEN_SMALL_CODE, "m", "fn")
        assert section == _GOLDEN_SMALL_SECTION

    @pytest.mark.unit
    def test_human_spec_rendered_before_docstring(self) -> None:
        """人类规格锚段落位置：函数签名之后、【文档化契约（docstring）】之前。"""
        material = dict(_GOLDEN_PLANNER_MATERIAL)
        material["human_spec"] = "HUMAN_SPEC_MARKER: returns a + b"
        section = build_spec_replace_section(material, _GOLDEN_CODE, "mathops", "add")
        anchor_idx = section.index("【独立于实现的规格锚（人类 docstring）】")
        docstring_idx = section.index("【文档化契约（docstring）】")
        sig_idx = section.index("函数签名：")
        assert sig_idx < anchor_idx < docstring_idx
        assert "HUMAN_SPEC_MARKER: returns a + b" in section
        # 实现代码仍不进产物
        assert "return a - b" not in section

    @pytest.mark.unit
    def test_human_spec_only_material_suffices(self) -> None:
        """只有 human_spec（无 logic/material 其它字段）也可渲染（doc 臂 node.py 外场景）。"""
        material = {"function_name": "fn", "human_spec": "SPEC_ONLY_MARKER"}
        section = build_spec_replace_section(material, "def fn(x):\n    return x\n", "m", "fn")
        assert "SPEC_ONLY_MARKER" in section
        assert "【独立于实现的规格锚（人类 docstring）】" in section

    @pytest.mark.unit
    def test_empty_human_spec_key_enters_material_decision(self) -> None:
        """空串 human_spec 键在场 → 仍算材料（不回落历史"注入代码"口径），但不渲染段落。"""
        material = {"function_name": "node", "human_spec": ""}
        section = build_spec_replace_section(material, _PROGRAM_CLASS_ONLY, "node", "")
        assert section != ""
        assert "【独立于实现的规格锚（人类 docstring）】" not in section
        assert "【规格优先模式" in section
        # 对比：同材料去掉 human_spec 键 → 无材料 → 空串
        bare = {"function_name": "node"}
        assert build_spec_replace_section(bare, _PROGRAM_CLASS_ONLY, "node", "") == ""

    @pytest.mark.unit
    def test_human_spec_none_value_counts_as_key(self) -> None:
        material = {"function_name": "fn", "human_spec": None}
        section = build_spec_replace_section(material, "def fn():\n    return 1\n", "m", "fn")
        assert section != ""
        assert "【独立于实现的规格锚（人类 docstring）】" not in section

    @pytest.mark.unit
    def test_human_spec_whitespace_stripped(self) -> None:
        material = {"function_name": "fn", "human_spec": "   \n  SPEC_TEXT  \n  "}
        section = build_spec_replace_section(material, "def fn():\n    return 1\n", "m", "fn")
        assert "【独立于实现的规格锚（人类 docstring）】\nSPEC_TEXT\n" in section

    @pytest.mark.unit
    def test_human_spec_key_added_does_not_alter_other_sections(self) -> None:
        """新增 human_spec 键只增段、不改变其它段落内容（逐段对比）。"""
        base = build_spec_replace_section(_GOLDEN_PLANNER_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        augmented = build_spec_replace_section(
            {**_GOLDEN_PLANNER_MATERIAL, "human_spec": "ANCHOR"}, _GOLDEN_CODE, "mathops", "add"
        )
        removed = augmented.replace("\n\n【独立于实现的规格锚（人类 docstring）】\nANCHOR", "")
        assert removed == base

    @pytest.mark.unit
    def test_function_body_never_enters_anchor_section(self) -> None:
        material = {"function_name": "add", "human_spec": "SPEC"}
        section = build_spec_replace_section(material, _GOLDEN_CODE, "mathops", "add")
        assert "return a - b" not in section
        assert "BUG" not in section

    @pytest.mark.unit
    def test_doc_anchor_table_entry_renders_via_lookup_contract(self) -> None:
        """doc 锚表条目（human_spec 键）经渲染器产出 anchor 段（端到端契约）。"""
        entry = {"function_name": "bitcount", "human_spec": _TAIL_SPEC.strip(), "source_len": 1, "human_spec_len": 1}
        section = build_spec_replace_section(entry, _PROGRAM_TAIL, "bitcount", "bitcount")
        assert "The number of 1-bits" in section
        assert "def bitcount(n)" in section


# ─── 3. 锚表构建 ────────────────────────────────────────────────────────────
def _builder_module() -> Any:
    return importlib.import_module("experiments.build_docstring_anchor_table")


class TestAnchorTableBuild:
    @pytest.mark.unit
    def test_content_addressed_keys_and_fields(self, quixbugs_dir: Path) -> None:
        build = _builder_module()
        table, stats = build.build_doc_anchor_table(quixbugs_dir, expect_programs=3)
        anchors = table["anchors"]
        assert len(anchors) == 3
        key = _sha360(_PROGRAM_TAIL)
        assert key in anchors
        entry = anchors[key]
        assert entry["human_spec"] == _TAIL_SPEC.strip()
        assert entry["function_name"] == "bitcount"
        assert entry["source_head"] == "def bitcount(n):"
        assert entry["source_len"] == len(_PROGRAM_TAIL)
        assert entry["human_spec_len"] == len(_TAIL_SPEC.strip())
        assert stats["human_spec_present"] == 2  # tail + module docstring
        assert stats["human_spec_missing"] == 1
        assert stats["human_spec_missing_programs"] == ["node"]

    @pytest.mark.unit
    def test_test_driver_files_excluded(self, quixbugs_dir: Path) -> None:
        """`*_test.py`（9 个测试驱动任务）不进 41 缺陷程序锚表。"""
        build = _builder_module()
        table, stats = build.build_doc_anchor_table(quixbugs_dir, expect_programs=3)
        assert stats["programs"] == 3
        assert _sha360("def test_bitcount():\n    assert True\n") not in table["anchors"]

    @pytest.mark.unit
    def test_meta_stats_reported(self, quixbugs_dir: Path) -> None:
        build = _builder_module()
        table, _ = build.build_doc_anchor_table(quixbugs_dir, expect_programs=3)
        meta = table["meta"]
        assert meta["schema"] == 1
        assert meta["mode"] == "doc"
        assert meta["programs"] == 3
        assert meta["table_entries"] == 3
        assert meta["human_spec_present"] == 2
        assert meta["human_spec_missing_programs"] == ["node"]
        assert "planner_table" not in meta

    @pytest.mark.unit
    def test_deterministic_two_runs_byte_identical(self, quixbugs_dir: Path, tmp_path: Path) -> None:
        build = _builder_module()
        out_dir = tmp_path / "out"
        assert build.main(["--data-dir", str(quixbugs_dir), "--out", str(out_dir), "--expect-programs", "3"]) == 0
        out_path = out_dir / build.TABLE_NAME
        first = out_path.read_bytes()
        assert build.main(["--data-dir", str(quixbugs_dir), "--out", str(out_dir), "--expect-programs", "3"]) == 0
        assert out_path.read_bytes() == first

    @pytest.mark.unit
    def test_missing_data_dir_fail_fast(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        build = _builder_module()
        missing = tmp_path / "no_such_quixbugs"
        rc = build.main(["--data-dir", str(missing), "--out", str(tmp_path / "out"), "--expect-programs", "41"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "QuixBugs 数据目录缺失" in err
        assert "AITESTER_QUIXBUGS_DATA" in err
        assert not (tmp_path / "out" / build.TABLE_NAME).exists()

    @pytest.mark.unit
    def test_program_count_mismatch_fail_fast(self, quixbugs_dir: Path) -> None:
        build = _builder_module()
        with pytest.raises(build.AnchorTableError, match="缺陷程序数不符"):
            build.build_doc_anchor_table(quixbugs_dir, expect_programs=41)

    @pytest.mark.unit
    def test_empty_programs_dir_fail_fast(self, tmp_path: Path) -> None:
        build = _builder_module()
        data = tmp_path / "empty"
        (data / "python_programs").mkdir(parents=True)
        with pytest.raises(build.AnchorTableError, match="为空"):
            build.build_doc_anchor_table(data, expect_programs=None)

    @pytest.mark.unit
    def test_function_name_fallbacks(self, tmp_path: Path) -> None:
        build = _builder_module()
        assert build.anchor_function_name("def f(x):\n    return x\n") == "f"
        # 多函数模块：回退首个顶层函数（与数据加载器 suggested_function 同口径）
        multi = "def target(a):\n    return a\n\n\ndef helper(b):\n    return b\n"
        assert build.sole_top_level_function_name(multi) == ""
        assert build.anchor_function_name(multi) == "target"
        # 纯类模块（node.py 形态）→ 空串
        assert build.anchor_function_name(_PROGRAM_CLASS_ONLY) == ""

    @pytest.mark.unit
    def test_union_merges_logic_analysis(self, quixbugs_dir: Path, tmp_path: Path) -> None:
        build = _builder_module()
        planner = {
            "meta": {},
            "anchors": {
                _sha360(_PROGRAM_TAIL): {
                    "function_name": "bitcount",
                    "logic_analysis": {"postconditions_expr": ["result == bin(n).count('1')"]},
                }
            },
        }
        planner_path = tmp_path / "SPEC_ANCHOR_TABLE.json"
        planner_path.write_text(json.dumps(planner), encoding="utf-8")
        table, stats = build.build_doc_anchor_table(quixbugs_dir, planner_table=planner_path, expect_programs=3)
        assert stats["union_matched"] == 1
        assert stats["union_missing"] == 2
        assert stats["union_missing_programs"] == ["add", "node"]
        hit = table["anchors"][_sha360(_PROGRAM_TAIL)]
        assert hit["human_spec"] == _TAIL_SPEC.strip()  # 人类规格仍在
        assert hit["logic_analysis"]["postconditions_expr"] == ["result == bin(n).count('1')"]
        # 未命中者只保留 human_spec（无 logic_analysis 键）
        miss = table["anchors"][_sha360(_PROGRAM_MODULE_DOCSTRING)]
        assert "logic_analysis" not in miss
        assert table["meta"]["mode"] == "union"
        assert table["meta"]["union_matched"] == 1

    @pytest.mark.unit
    def test_union_missing_planner_table_fail_fast(self, quixbugs_dir: Path, tmp_path: Path) -> None:
        build = _builder_module()
        with pytest.raises(build.AnchorTableError, match="Planner 锚表缺失"):
            build.build_doc_anchor_table(quixbugs_dir, planner_table=tmp_path / "nope.json", expect_programs=3)

    @pytest.mark.unit
    def test_union_cli_requires_union_flag(self, quixbugs_dir: Path, tmp_path: Path) -> None:
        build = _builder_module()
        rc = build.main(["--data-dir", str(quixbugs_dir), "--out", str(tmp_path), "--planner-table", "x.json"])
        assert rc == 1

    @pytest.mark.unit
    def test_union_cli_writes_union_artifact(self, quixbugs_dir: Path, tmp_path: Path) -> None:
        build = _builder_module()
        planner_path = tmp_path / "planner.json"
        planner_path.write_text(json.dumps({"anchors": {}}), encoding="utf-8")
        out_dir = tmp_path / "out"
        rc = build.main(
            [
                "--data-dir",
                str(quixbugs_dir),
                "--out",
                str(out_dir),
                "--union",
                "--planner-table",
                str(planner_path),
                "--expect-programs",
                "3",
            ]
        )
        assert rc == 0
        assert (out_dir / build.UNION_TABLE_NAME).is_file()
        assert not (out_dir / build.TABLE_NAME).exists()  # 两套工件互不覆盖

    @pytest.mark.unit
    @pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason="QuixBugs 数据/Planner 锚表不在本地（CI 跳过）")
    def test_real_quixbugs_doc_and_union_tables(self, tmp_path: Path) -> None:
        """真实数据：doc 表 41 条/40 有 human_spec；union 41/41 命中 Planner 子句。"""
        build = _builder_module()
        doc_table, doc_stats = build.build_doc_anchor_table(_QUIXBUGS_DATA)
        assert doc_stats["programs"] == 41
        assert len(doc_table["anchors"]) == 41
        assert doc_stats["human_spec_present"] == 40
        assert doc_stats["human_spec_missing_programs"] == ["node"]
        union_table, union_stats = build.build_doc_anchor_table(_QUIXBUGS_DATA, planner_table=_PLANNER_ANCHOR_TABLE)
        assert union_stats["programs"] == 41
        assert union_stats["union_matched"] == 41
        assert union_stats["union_missing"] == 0
        assert all("logic_analysis" in e for e in union_table["anchors"].values())
        assert all(e["human_spec_len"] == len(e["human_spec"]) for e in doc_table["anchors"].values())


# ─── 4. 臂接线（run_benchmark 两臂）────────────────────────────────────────
def _rb() -> Any:
    return importlib.import_module("experiments.run_benchmark")


class _FakeGraph:
    """记录 invoke 入参与调用期间关键开关状态的假图（与 df_spec 测试同模式）。"""

    def __init__(self, sink: dict[str, Any]) -> None:
        self._sink = sink

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        import config as _cfg
        from src.tools.spec_first import detection_spec_mode

        self._sink["invoke_state"] = dict(state)
        self._sink["spec_mode_during"] = detection_spec_mode()
        self._sink["detection_first_during"] = _cfg.detection_first_enabled()
        return dict(state)


def _make_state(target_code: str) -> dict[str, Any]:
    from src.graph.state import create_initial_state

    state = create_initial_state("u_doc_anchor", "target_mod.py", target_code, 1, module_name="target_mod")
    state["task_id"] = "quixbugs__bitcount"
    return dict(state)


def _write_anchor_table(path: Path, source: str, material: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps({"meta": {}, "anchors": {_sha360(source): material}}),
        encoding="utf-8",
    )
    return path


class TestRunBenchmarkWiring:
    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("arm", "fn_name"),
        [
            ("plain_llm_df_doc", "run_plain_llm_df_doc_baseline"),
            ("plain_llm_df_doc_union", "run_plain_llm_df_doc_union_baseline"),
        ],
    )
    def test_registry_entries_present(self, arm: str, fn_name: str) -> None:
        rb = _rb()
        assert arm in rb.BASELINE_REGISTRY
        assert rb.BASELINE_REGISTRY[arm] is getattr(rb, fn_name)

    @pytest.mark.unit
    def test_default_table_paths_per_arm(self) -> None:
        rb = _rb()
        assert rb._DOC_ANCHOR_TABLE_DEFAULT.endswith(
            "/experiments/results/emse_docstring_anchor_20261017/DOCSTRING_ANCHOR_TABLE.json"
        )
        assert rb._DOC_ANCHOR_TABLE_UNION_DEFAULT.endswith(
            "/experiments/results/emse_docstring_anchor_20261017/DOCSTRING_ANCHOR_TABLE_UNION.json"
        )
        assert rb._DOC_ANCHOR_TABLE_DEFAULT != rb._DOC_ANCHOR_TABLE_UNION_DEFAULT

    @pytest.mark.unit
    def test_existing_df_spec_default_untouched(self) -> None:
        """既有 df_spec 臂默认锚表路径不得被本轮改动。"""
        rb = _rb()
        assert rb._DF_SPEC_ANCHOR_TABLE_DEFAULT.endswith(
            "/experiments/results/emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json"
        )
        assert "plain_llm_df_spec" in rb.BASELINE_REGISTRY

    @pytest.mark.unit
    def test_env_override_applies_to_loader(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rb = _rb()
        source = "def fn(x):\n    return x + 1\n"
        table_path = _write_anchor_table(tmp_path / "t.json", source, {"function_name": "fn", "human_spec": "S"})
        monkeypatch.setenv("DOC_ANCHOR_TABLE", str(table_path))
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_CACHE", {})
        anchors = rb._load_doc_anchor_table(str(tmp_path / "default-would-be.json"))
        assert anchors is not None and _sha360(source) in anchors

    @pytest.mark.unit
    def test_missing_or_corrupt_table_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rb = _rb()
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_CACHE", {})
        monkeypatch.setenv("DOC_ANCHOR_TABLE", str(tmp_path / "nope.json"))
        assert rb._load_doc_anchor_table("also-nope.json") is None
        corrupt = tmp_path / "corrupt.json"
        corrupt.write_text("{broken", encoding="utf-8")
        monkeypatch.setenv("DOC_ANCHOR_TABLE", str(corrupt))
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_CACHE", {})
        assert rb._load_doc_anchor_table("x.json") is None
        wrong_shape = tmp_path / "shape.json"
        wrong_shape.write_text(json.dumps({"anchors": []}), encoding="utf-8")
        monkeypatch.setenv("DOC_ANCHOR_TABLE", str(wrong_shape))
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_CACHE", {})
        assert rb._load_doc_anchor_table("x.json") is None

    @pytest.mark.unit
    def test_lookup_hit_uses_strip_hash(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rb = _rb()
        source = "def fn(x):\n    return x + 1\n"
        material = {"function_name": "fn", "human_spec": "SPEC"}
        table_path = _write_anchor_table(tmp_path / "t.json", source, material)
        monkeypatch.setenv("DOC_ANCHOR_TABLE", str(table_path))
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_CACHE", {})
        assert rb._lookup_doc_anchor({"target_code": f"\n\n{source}\n\n"}, "unused.json") == material
        assert rb._lookup_doc_anchor({"target_code": "def other():\n    return 0\n"}, "unused.json") is None
        assert rb._lookup_doc_anchor({"target_code": ""}, "unused.json") is None

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("baseline_attr", "default_attr"),
        [
            ("run_plain_llm_df_doc_baseline", "_DOC_ANCHOR_TABLE_DEFAULT"),
            ("run_plain_llm_df_doc_union_baseline", "_DOC_ANCHOR_TABLE_UNION_DEFAULT"),
        ],
    )
    def test_arm_hit_injects_anchor_and_restores_flags(
        self,
        baseline_attr: str,
        default_attr: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """命中：invoke 窗口内 state["spec_anchor"]=材料 + replace 模式 + 检出优先；finally 全恢复。"""
        import config as _cfg

        rb = _rb()
        monkeypatch.delenv("DETECTION_SPEC_MODE", raising=False)
        monkeypatch.delenv("DETECTION_FIRST_ENABLE", raising=False)
        monkeypatch.delenv("DOC_ANCHOR_TABLE", raising=False)
        source = "def fn(x):\n    return x + 1\n"
        material = {"function_name": "fn", "human_spec": "SPEC_MARKER"}
        table_path = _write_anchor_table(tmp_path / "t.json", source, material)
        monkeypatch.setattr(rb, default_attr, str(table_path))
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_CACHE", {})
        sink: dict[str, Any] = {}
        monkeypatch.setattr(rb, "build_workflow", lambda **kwargs: _FakeGraph(sink))

        result = getattr(rb, baseline_attr)(_make_state(source))

        assert sink["invoke_state"]["spec_anchor"] == material
        assert sink["spec_mode_during"] == "replace"
        assert sink["detection_first_during"] is True
        # finally 全恢复
        from src.tools.spec_first import detection_spec_mode

        assert detection_spec_mode() == "off"
        assert _cfg.detection_first_enabled() is False
        assert result["spec_anchor"] == material

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "baseline_attr",
        ["run_plain_llm_df_doc_baseline", "run_plain_llm_df_doc_union_baseline"],
    )
    def test_arm_miss_falls_back_without_crash(
        self, baseline_attr: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """表缺失：不注入材料（回落 df 口径）但模式仍 replace（节点渲染空串 → attempted_fallback）。"""
        rb = _rb()
        monkeypatch.delenv("DOC_ANCHOR_TABLE", raising=False)
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_DEFAULT", str(tmp_path / "nope.json"))
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_UNION_DEFAULT", str(tmp_path / "nope.json"))
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_CACHE", {})
        sink: dict[str, Any] = {}
        monkeypatch.setattr(rb, "build_workflow", lambda **kwargs: _FakeGraph(sink))

        getattr(rb, baseline_attr)(_make_state("def unknown():\n    return 0\n"))

        assert sink["invoke_state"]["spec_anchor"] is None  # 回落 df 口径
        assert sink["spec_mode_during"] == "replace"  # 节点渲染空串 → attempted_fallback
        from src.tools.spec_first import detection_spec_mode

        assert detection_spec_mode() == "off"  # finally 恢复

    @pytest.mark.unit
    def test_env_snapshot_includes_doc_anchor_table(self) -> None:
        """DOC_ANCHOR_TABLE 必须入 provenance 快照（第九次同类缺口预防）。"""
        rb = _rb()
        tree = ast.parse(Path(rb.__file__).read_text(encoding="utf-8"))
        keys: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_env_snapshot_keys" for t in node.targets
            ):
                keys = [e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        assert "DOC_ANCHOR_TABLE" in keys
        assert "DF_SPEC_ANCHOR_TABLE" in keys  # 既有键未丢
