"""P1-6（2026-10-05 独立审查）：状态通道契约静态守卫测试。

锁定：scripts/gates/check_state_contract.py 对"未声明键读写"的捕获能力
（M14 四键 / O35 三键 / problem_statement 死读均属此类——LangGraph
channel 白名单外的键被静默丢弃或恒 None），守卫脚本本身回归即红。

G3（2026-10-16）增补 TestScanSurface：门禁的**扫描面**同样是失效面——
旧口径只硬编码 nodes.py / workflow.py 两个文件，真实的读侧断链在图外
（observability/failure_taxonomy.py 读顶层 logic_degraded），门禁因此对着
缺陷全绿。现锁住"整个 src/ 树都必须在扫描面内"（132 文件 / 0.15s）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.gates.check_state_contract import (
    PROJECT_ROOT,
    _allowed,
    _audit_file,
    _literal_key,
    _rel,
    declared_state_keys,
    scan_files,
)


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


class TestScanSurface:
    """G3（2026-10-16）：扫描面本身也是门禁的失效面——面太窄 = 假绿。

    旧口径硬编码 `("src/graph/nodes.py", "src/graph/workflow.py")` 两个文件，
    而脚本 docstring 自称扫 `src/graph/*.py`；真实的读侧断链
    （failure_taxonomy 读顶层 `logic_degraded`，写侧只写进 test_plan 内部且键未声明）
    恰好落在扫描面之外 → 门禁对着缺陷全绿。
    """

    def test_whole_src_tree_is_scanned(self):
        scanned = set(scan_files())
        on_disk = set((PROJECT_ROOT / "src").rglob("*.py"))
        assert on_disk == scanned, f"扫描面与 src/ 实际文件不一致：{sorted(on_disk ^ scanned)[:5]}"
        assert len(scanned) > 100, f"扫描面异常收窄（{len(scanned)} 个文件）——glob 失效即假绿"

    def test_known_state_readers_are_scanned(self):
        rels = {_rel(p) for p in scan_files()}
        for expected in (
            "src/graph/nodes.py",  # 旧扫描面（写侧）
            "src/graph/workflow.py",
            "src/observability/failure_taxonomy.py",  # G3 断链所在（图外读侧）
            "src/agents/debugger.py",  # 图外状态消费方（旧扫描面完全未覆盖）
        ):
            assert expected in rels, f"{expected} 不在扫描面内"

    def test_real_repo_audit_is_clean(self):
        """扩容后的扫描面在真实仓库上必须零违规（否则扩容即转红）。"""
        declared = declared_state_keys()
        violations = [v for p in scan_files() for v in _audit_file(p, declared)]
        assert violations == []

    def test_g3_defect_is_caught_when_key_undeclared(self):
        """回归锁：把 `logic_degraded` 从声明集里去掉（还原修复前），门禁必须报出读侧。"""
        declared = declared_state_keys() - {"logic_degraded"}
        target = PROJECT_ROOT / "src" / "observability" / "failure_taxonomy.py"
        violations = _audit_file(target, declared)
        assert any(kind == "get" and key == "logic_degraded" for _, _, kind, key in violations), violations

    def test_rel_falls_back_outside_repo(self):
        assert _rel(PROJECT_ROOT / "README.md") == "README.md"
        outside = Path("/tmp/not-in-repo.py")
        assert _rel(outside) == str(outside)
