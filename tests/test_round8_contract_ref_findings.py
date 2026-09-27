# 2026-09-26 第八轮：契约参照侧参数 + type_repair_findings 状态传播 + 回归守卫

"""本文件锁定本轮两项修复的行为口径（默认行为不变）：

- P1: type_repair_layer 的 enforce_contract_ref 参数
    - 默认 None（契约参照侧 = original_code，删除检测主语义）：
      LLM 修订省略原代码顶层符号 → 拒绝修订；
    - 显式传入"补丁后完整文件"作参照侧：同符号集口径校验
      （参照侧有而修订侧缺 → 拒绝；修订侧含参照侧全集 → 通过）。
- P1: _debugger_node 把 debug() 返回的 type_repair_findings 写入 state
    （此前 schema 有键、节点不写 → 消费侧恒 None）。
- P2: 诊断节点路由 _route_after_diagnosis 的 defect_type 判定（test_defect
  → regenerate，其余 → debug）。
"""

from __future__ import annotations

from src.graph.workflow import _route_after_diagnosis
from src.tools.type_repair import type_repair_layer

_ORIG = (
    "CONST_X = 1\n"
    "\n"
    "def helper():\n"
    '    return "h"\n'
    "\n"
    "def target(x):\n"
    "    if x > 0:\n"
    '        return "pos"\n'
    "    return 0\n"
)


def _patched_from_orig() -> str:
    return _ORIG.replace('"pos"', "1")


def _enable_llm_layer(monkeypatch) -> None:
    monkeypatch.setenv("TYPE_REPAIR_LLM_ENABLE", "true")


class TestTypeRepairContractRef:
    """enforce_contract_ref 参数口径。"""

    def test_default_ref_is_original(self, monkeypatch):
        """不传 enforce_contract_ref：参照侧 = original（删除检测主语义）。

        修订侧省略原代码顶层符号（CONST_X / helper）→ 契约失败、拒绝修订。
        """
        _enable_llm_layer(monkeypatch)
        patched = _patched_from_orig()
        single_func_repair = "def target(x):\n    return 1\n"

        def fake_repair(query, orig, p):
            return single_func_repair

        result = type_repair_layer(_ORIG, patched, llm_repair=fake_repair)
        assert result["repaired"] is False
        assert result["contract_ok"] is False
        assert set(result["missing_symbols"]) == {"CONST_X", "helper"}
        # 保守保留补丁后代码（不引入半修订状态）
        assert result["repaired_code"] == patched

    def test_explicit_ref_is_patch_baseline(self, monkeypatch):
        """传 enforce_contract_ref=patched（补丁后完整文件同符号集口径）。

        修订侧保留参照侧全部符号 → 契约通过、修订生效。
        """
        _enable_llm_layer(monkeypatch)
        patched = _patched_from_orig()
        full_file_repair = patched + "def extra():\n    return 2\n"

        def fake_repair(query, orig, p):
            return full_file_repair

        result = type_repair_layer(_ORIG, patched, llm_repair=fake_repair, enforce_contract_ref=patched)
        assert result["repaired"] is True
        assert result["contract_ok"] is True
        assert result["repaired_code"] == full_file_repair

    def test_explicit_ref_still_rejects_symbol_drop(self, monkeypatch):
        """显式参照侧口径下，修订省略参照侧符号仍拒绝（删除检测不放过）。"""
        _enable_llm_layer(monkeypatch)
        patched = _patched_from_orig()
        drop_repair = "def target(x):\n    return 1\n"

        def fake_repair(query, orig, p):
            return drop_repair

        result = type_repair_layer(_ORIG, patched, llm_repair=fake_repair, enforce_contract_ref=patched)
        assert result["repaired"] is False
        assert set(result["missing_symbols"]) == {"CONST_X", "helper"}


class TestDebuggerNodeTypeRepairFindingsPropagation:
    """_debugger_node 把 debug() 的 type_repair_findings 写入 state。"""

    def test_debugger_node_writes_type_repair_findings(self, monkeypatch):
        import src.graph.nodes as nodes

        monkeypatch.setenv("TYPE_REPAIR_LLM_ENABLE", "true")
        # 静态层必现疑点：total int→str 冲突（与 TestTypeRepairLayer 同口径）
        buggy_code = "def calc(x):\n    total = 0\n    total = 'oops'\n    return total\n"
        fake_debug_result = {
            "root_cause": "type mismatch",
            "error_category": "type_error",
            "fix_strategy": "repair",
            "patch": "```python\n" + buggy_code + "\n```",
            "adversarial_check": {"scenarios_checked": 0, "all_passed": False},
            "defect_type": "implementation_defect",
            "review_reason": "",
            "position_aware_focus": {"focused": False, "function_name": None, "line": None, "hint": ""},
            "type_repair_findings": [{"file": "patched", "line": 3, "message": "m", "kind": "type_mismatch"}],
            "mypy_findings_count": 0,
            "downgrade_triggered": False,
            "downgrade_tier": None,
        }
        monkeypatch.setattr(nodes.DebuggerAgent, "debug", lambda self, **kw: fake_debug_result)

        state = {
            "iteration": 0,
            "target_code": buggy_code,
            "target_file": "calc.py",
            "test_output": "FAILED",
            "failed_cases": [],
            "error_category": "type_error",
        }
        update = nodes._debugger_node(state)
        assert update["type_repair_findings"] == [
            {"file": "patched", "line": 3, "message": "m", "kind": "type_mismatch"}
        ]
        # 2.1 mypy 静态层观测字段（未启用时 0）
        assert update["mypy_findings_count"] == 0
        # 1.3 降级链观测字段（未触发时 False/None）
        assert update["downgrade_triggered"] is False
        assert update["downgrade_tier"] is None

    def test_debugger_node_default_empty_findings(self, monkeypatch):
        """debug() 无该键（历史调用方）时，节点写入空列表而非 None。"""
        import src.graph.nodes as nodes

        fake_debug_result = {
            "root_cause": "unknown",
            "error_category": "unknown",
            "fix_strategy": "",
            "patch": "",
        }
        monkeypatch.setattr(nodes.DebuggerAgent, "debug", lambda self, **kw: fake_debug_result)

        state = {
            "iteration": 0,
            "target_code": "def f():\n    return 1\n",
            "target_file": "f.py",
            "test_output": "FAILED",
            "failed_cases": [],
            "error_category": "unknown",
        }
        update = nodes._debugger_node(state)
        assert update["type_repair_findings"] == []


class TestRouteAfterDiagnosis:
    """_route_after_diagnosis 路由判定。"""

    def test_test_defect_routes_regenerate(self):
        assert _route_after_diagnosis({"defect_type": "test_defect"}) == "regenerate"

    def test_implementation_defect_routes_debug(self):
        assert _route_after_diagnosis({"defect_type": "implementation_defect"}) == "debug"

    def test_missing_defect_type_routes_debug(self):
        assert _route_after_diagnosis({}) == "debug"


if __name__ == "__main__":
    # 无 pytest 时的最小冒烟（CI 走 pytest 路径）
    print("run via pytest: tests/test_round8_contract_ref_findings.py")
