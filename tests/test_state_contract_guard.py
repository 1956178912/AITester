"""P1-6（2026-10-05 独立审查）：状态通道契约静态守卫测试。

锁定：scripts/check_state_contract.py 对"未声明键读写"的捕获能力
（M14 四键 / O35 三键 / problem_statement 死读均属此类——LangGraph
channel 白名单外的键被静默丢弃或恒 None），守卫脚本本身回归即红。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_state_contract import _allowed, _audit_file, _literal_key, declared_state_keys


def _audit(tmp_path: Path, code: str) -> list[tuple[str, int, str, str]]:
    p = tmp_path / "probe.py"
    p.write_text(code, encoding="utf-8")
    return _audit_file(p, declared_state_keys())


class TestStateContractGuard:
    def test_declared_keys_loaded(self):
        keys = declared_state_keys()
        assert {"target_code", "error_category", "task_uuid"} <= keys, "核心通道键必须可加载"
        assert "error_confidence" in keys and "risk_approval_decision" in keys, "P2-4 新键必须已声明"
        assert "problem_statement" in keys, "P1-6 死读修复键必须已声明"

    def test_write_undeclared_key_caught(self, tmp_path):
        code = 'def n(state):\n    state["undeclared_xyz"] = 1\n'
        v = _audit(tmp_path, code)
        assert any(kind == "write" and key == "undeclared_xyz" for _, _, kind, key in v)

    def test_get_undeclared_key_caught(self, tmp_path):
        code = 'def n(state):\n    return state.get("undeclared_abc")\n'
        v = _audit(tmp_path, code)
        assert any(kind == "get" and key == "undeclared_abc" for _, _, kind, key in v)

    def test_read_undeclared_key_caught(self, tmp_path):
        code = 'def n(state):\n    return state["undeclared_read"]\n'
        v = _audit(tmp_path, code)
        assert any(kind == "read" and key == "undeclared_read" for _, _, kind, key in v)

    def test_declared_and_underscore_keys_exempt(self, tmp_path):
        code = (
            "def n(state):\n"
            '    state["target_code"] = "x"  # 已声明\n'
            '    state["_internal_tmp"] = {}  # 临时键约定\n'
            '    _ = state.get("error_category")\n'
        )
        assert _audit(tmp_path, code) == []

    def test_dynamic_and_non_state_ignored(self, tmp_path):
        code = (
            "def n(state, other):\n"
            "    key = compute()\n"
            '    other["undeclared_xyz"] = 1  # 非 state 变量\n'
            "    state[key] = 2  # 动态键不审计\n"
            '    cfg = {"undeclared_abc": 1}  # 字面量 dict\n'
        )
        assert _audit(tmp_path, code) == []

    def test_literal_key_helper(self):
        import ast as _ast

        node = _ast.parse('d["k"]').body[0].value
        assert _literal_key(node.slice) == "k"
        node2 = _ast.parse("d[i]").body[0].value
        assert _literal_key(node2.slice) is None

    def test_allowed_semantics(self):
        declared = declared_state_keys()
        assert _allowed("target_code", declared)
        assert _allowed("_1_3_contract_missing", declared)
        assert not _allowed("undeclared_xyz", declared)
