"""修复引擎批次 IV（2026-10-07，ADR-0019）：确定性优先修复路由行为锁。

锁定四组行为：
1. 三个确定性变换器（缺 import 推断 / 导入别名回填 / tab 缩进归一）——
   命中、保守放弃、验证门；
2. build_deterministic_debug_result 与 debug() 返回键集合同构；
3. 开关缺省（默认关）；
4. _debugger_node 接线存在性（确定性优先门 + 每任务一次哨兵语义）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tools.deterministic_repair import (
    attempt_deterministic_repair,
    build_deterministic_debug_result,
    deterministic_repair_first_enabled,
)

CODE_NO_IMPORT = "def area(r):\n    return math.pi * r * r\n"
CODE_WITH_IMPORT = "import math\n\n\ndef area(r):\n    return math.pi * r * r\n"
NAME_ERROR = "NameError: name 'math' is not defined"


class TestMissingImportInference:
    def test_inserts_stdlib_import(self) -> None:
        result = attempt_deterministic_repair(
            target_code=CODE_NO_IMPORT, test_output=NAME_ERROR, error_category="RUNTIME"
        )
        assert result["attempted"] is True
        assert result["method"] == "missing_import_inference"
        assert result["patch_code"] is not None
        assert "import math" in result["patch_code"]
        assert "math.pi" in result["patch_code"]  # 原码保留

    def test_insert_after_existing_imports(self) -> None:
        code = "import os\n\n\ndef f():\n    return math.floor(1.5)\n"
        result = attempt_deterministic_repair(target_code=code, test_output=NAME_ERROR, error_category="RUNTIME")
        assert result["patch_code"] is not None
        lines = result["patch_code"].splitlines()
        assert lines.index("import math") > lines.index("import os")

    def test_already_imported_skips(self) -> None:
        result = attempt_deterministic_repair(
            target_code=CODE_WITH_IMPORT, test_output=NAME_ERROR, error_category="RUNTIME"
        )
        assert result["patch_code"] is None

    def test_non_stdlib_name_skips(self) -> None:
        result = attempt_deterministic_repair(
            target_code="def f():\n    return mylib.thing()\n",
            test_output="NameError: name 'mylib' is not defined",
            error_category="RUNTIME",
        )
        assert result["attempted"] is False  # 未命中任何变换器（白名单外）

    def test_name_unused_in_target_skips(self) -> None:
        """NameError 的名字在目标代码中未使用（错误源自测试）→ 不动目标。"""
        result = attempt_deterministic_repair(
            target_code="def f(x):\n    return x\n",
            test_output=NAME_ERROR,
            error_category="RUNTIME",
        )
        assert result["attempted"] is False


class TestImportAliasBackfill:
    def test_unique_rename_suspect_backfills(self) -> None:
        code = "class RuleV2:\n    def check(self):\n        return True\n"
        result = attempt_deterministic_repair(
            target_code=code,
            test_output="ImportError: cannot import name 'Rule' from 'mod'",
            error_category="IMPORT_ERROR",
        )
        assert result["method"] == "import_alias_backfill"
        assert result["patch_code"] is not None
        assert "Rule = RuleV2" in result["patch_code"]

    def test_multiple_suspects_conservative_skip(self) -> None:
        code = "class RuleV2:\n    pass\n\n\nclass RuleV3:\n    pass\n"
        result = attempt_deterministic_repair(
            target_code=code,
            test_output="cannot import name 'Rule'",
            error_category="IMPORT_ERROR",
        )
        assert result["patch_code"] is None


class TestTabNormalize:
    def test_tabs_normalized(self) -> None:
        code = "def f():\n\treturn 1\n"
        result = attempt_deterministic_repair(
            target_code=code,
            test_output="IndentationError: inconsistent use of tabs and spaces in indentation",
            error_category="SYNTAX",
        )
        assert result["method"] == "tab_indent_normalize"
        assert result["patch_code"] == "def f():\n    return 1\n"

    def test_no_tabs_skips(self) -> None:
        result = attempt_deterministic_repair(
            target_code="def f():\n    return 1\n",
            test_output="IndentationError: inconsistent use of tabs and spaces in indentation",
            error_category="SYNTAX",
        )
        assert result["attempted"] is False


class TestValidationGateAndRoutes:
    def test_no_matching_transformer(self) -> None:
        result = attempt_deterministic_repair(
            target_code="def f(x):\n    return x - 1\n",
            test_output="AssertionError: assert -1 == 1",
            error_category="ASSERTION",
        )
        assert result == {
            "attempted": False,
            "method": None,
            "reason": "no_matching_transformer",
            "patch_code": None,
            "category": "ASSERTION",
        }

    def test_empty_target(self) -> None:
        result = attempt_deterministic_repair(target_code="  ", test_output=NAME_ERROR, error_category="RUNTIME")
        assert result["reason"] == "empty_target"

    def test_syntax_broken_candidate_rejected(self) -> None:
        """候选破坏语法 → 验证门拒绝（attempted=True 但无补丁）。

        构造：tab 归一生成合法码难以破坏——用缺 import 插入位置构造
        不可解析原码场景：原码本就坏（doc_end 解析失败回落 0）+ 插入后
        仍坏 → validation_failed。此用例锁定"验证门存在"的防御语义。
        """
        result = attempt_deterministic_repair(
            target_code="def broken(:\n    math.pi\n",
            test_output=NAME_ERROR,
            error_category="RUNTIME",
        )
        # 原码不可解析 → 插入后仍不可解析 → 验证门拒绝
        assert result["attempted"] is True
        assert result["patch_code"] is None
        assert result["reason"].startswith("validation_failed")


class TestDebugResultIsomorphism:
    def test_key_set_matches_debug_contract(self) -> None:
        """确定性结果与 DebuggerAgent.debug() 返回键集合同构（下游不缺键）。"""
        result = build_deterministic_debug_result(
            patch_code="x = 1\n",
            method="missing_import_inference",
            reason="produced",
            error_category="RUNTIME",
        )
        expected = {
            "root_cause",
            "error_category",
            "error_confidence",
            "fix_strategy",
            "patch",
            "adversarial_check",
            "defect_type",
            "review_reason",
            "edit_intent_status",
            "position_aware_focus",
            "type_repair_findings",
            "mypy_findings_count",
        }
        assert set(result.keys()) == expected
        assert result["patch"].startswith("```python\n")
        assert result["defect_type"] == "implementation_defect"

    def test_debug_return_keys_covered(self) -> None:
        """与 DebuggerAgent.debug 实际返回键对齐（防漂移——直接读源返回块）。"""
        import inspect

        from src.agents.debugger import DebuggerAgent

        src_text = inspect.getsource(DebuggerAgent.debug)
        for key in ('"root_cause"', '"error_confidence"', '"fix_strategy"', '"adversarial_check"'):
            assert key in src_text
        result = build_deterministic_debug_result(
            patch_code="x = 1\n", method="m", reason="produced", error_category="SYNTAX"
        )
        assert '"edit_intent_status"' in src_text and result["edit_intent_status"] is None


class TestSwitchAndWiring:
    def test_default_off(self, monkeypatch) -> None:
        monkeypatch.delenv("DETERMINISTIC_REPAIR_FIRST_ENABLE", raising=False)
        assert deterministic_repair_first_enabled() is False

    def test_explicit_on(self, monkeypatch) -> None:
        monkeypatch.setenv("DETERMINISTIC_REPAIR_FIRST_ENABLE", "true")
        assert deterministic_repair_first_enabled() is True

    def test_debugger_node_wiring_lock(self) -> None:
        """接线存在性锁：_debugger_node 含确定性优先门与哨兵条件（防误删）。"""
        import inspect

        import src.graph.nodes as nodes

        src_text = inspect.getsource(nodes._debugger_node)
        assert "attempt_deterministic_repair" in src_text
        assert 'state.get("deterministic_repair_status") is None' in src_text  # 每任务一次哨兵
        assert "build_deterministic_debug_result" in src_text

    def test_state_declares_status(self) -> None:
        from src.graph.state import AITesterState, create_initial_state

        state = create_initial_state(task_uuid="t", target_file="m.py", target_code="x = 1\n", max_iterations=3)
        assert state["deterministic_repair_status"] is None
        assert "deterministic_repair_status" in AITesterState.__annotations__
