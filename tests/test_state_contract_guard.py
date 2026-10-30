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
    _walk_channel_usage,
    channel_coverage,
    coverage_lines,
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


class TestChannelCoverage:
    """CB 轮（2026-10-23）：判定面覆盖必须与成功语句同时出现。

    旧成功语句「无未声明键读写」把「判过且干净」与「压根没看」说成同一件事：
    判定面只有就地赋值 + `state.get/state[]` 字面读写，而 LangGraph 的规范写侧
    是节点返回局部更新 dict（CB 轮实测 45 键 / 95 站点；DS 轮后 47 键 / 99 站点）——
    正是 docstring 背景里 M14 / O35 静默丢弃事故的路径。本轮只披露、不动判定。
    """

    def test_declared_matches_runtime_annotations(self):
        cov = channel_coverage()
        assert cov.declared == tuple(sorted(declared_state_keys()))

    def test_real_repo_coverage_numbers(self):
        """真实仓库读数快照：数字变动即须重跑普查并重登记（棘轮式可见）。

        其余读数为 CB 轮普查值；update dict / 未触及为 DS 轮重登记值
        （44 → 46 未审计）。update dict 计的是字面出现，CLI 结果 dict 与状态
        节点更新同形，`coverage_threshold` / `max_iterations` 的 4 个站点来自
        `src/cli/app.py::_make_task_error_result`，不是状态写。EC 轮
        `src/utils/trace_viz.py::replay_trace` 把轨迹的 `passed` 映射进
        `state["test_passed"]`（读侧词汇对齐写侧）⇒ 就地赋值 2 键 / 11 站点
        → 3 键 / 12 站点，`test_passed` 同时进入两条写路径 ⇒ 未审计 46 → 45。
        """
        cov = channel_coverage()
        assert len(cov.declared) == 118
        # 353 → 354（B1 批 2026-10-30 复算）：4a9512e3 在
        # `src/graph/workflow.py::_should_debug` 加 `state.get("task_uuid")`
        # 读点（tge__ 前缀豁免，TestGenEval 口径修复）⇒ 读站点 +1、键集不变。
        assert (len(cov.read_keys), cov.read_sites) == (57, 354)
        assert (len(cov.inplace_write_keys), cov.inplace_write_sites) == (3, 12)
        assert (len(cov.update_write_keys), cov.update_write_sites) == (47, 99)
        assert (len(cov.untouched), len(cov.untouched_elsewhere), len(cov.untouched_nowhere)) == (34, 33, 1)
        assert (cov.temp_keys, cov.temp_sites, cov.dynamic_sites, cov.undeclared_sites) == (2, 2, 1, 0)

    def test_written_keys_union_and_unaudited_gap(self):
        """两条写路径互不包含：`gold_fixed_code` 只有就地写（orchestration_search.py），
        规范 update dict 侧从不写它——审计面看得见、LangGraph 写侧看不见，反之亦然。"""
        cov = channel_coverage()
        assert set(cov.written_keys) == set(cov.inplace_write_keys) | set(cov.update_write_keys)
        assert set(cov.unaudited_write_keys) == set(cov.update_write_keys) - set(cov.inplace_write_keys)
        assert cov.inplace_write_keys == ("gold_fixed_code", "stop_reason", "test_passed")
        assert "gold_fixed_code" not in cov.update_write_keys
        assert "stop_reason" in cov.update_write_keys
        assert len(cov.unaudited_write_keys) == 45
        # DS 轮新增的不可归属噪声：CLI 结果 dict 里的两个声明键
        assert {"coverage_threshold", "max_iterations"} <= set(cov.update_write_keys)

    def test_untouched_reconciles_with_sets(self):
        cov = channel_coverage()
        expected = (
            {k for k in cov.declared if not k.startswith("_")}
            - set(cov.read_keys)
            - set(cov.inplace_write_keys)
            - set(cov.update_write_keys)
        )
        assert set(cov.untouched) == expected

    def test_untouched_partition_is_complete_and_disjoint(self):
        cov = channel_coverage()
        assert set(cov.untouched_elsewhere) | set(cov.untouched_nowhere) == set(cov.untouched)
        assert not set(cov.untouched_elsewhere) & set(cov.untouched_nowhere)

    def test_dead_declaration_is_named(self):
        """唯一全仓零字面的声明键必须在披露里点名（不是计数摊销掉）。"""
        assert channel_coverage().untouched_nowhere == ("failure_frequency_applied",)

    def test_apparatus_self_reference_does_not_clear_dead_key(self):
        """CB 实测的自指缺陷：门禁 docstring 与守卫测试都写了死键字面。

        若把测量装置算作「别处还有出现」，untouched_nowhere 会由 1 变 0——
        门禁用自己的披露文本把自己的结论证伪。装置提到键名是披露/断言，不是消费者。
        """
        from scripts.gates.check_state_contract import _apparatus_paths, _outside_literal_blob

        rel = {p.relative_to(PROJECT_ROOT).as_posix() for p in _apparatus_paths()}
        assert "scripts/gates/check_state_contract.py" in rel
        assert "tests/test_state_contract_guard.py" in rel
        assert "tests/test_ao_batch.py" not in rel, "排除面不得扩大到无关测试"
        assert "failure_frequency_applied" not in _outside_literal_blob()

    def test_imports_module_matches_only_exact_module(self):
        import ast

        from scripts.gates.check_state_contract import _imports_module

        dotted = "scripts.gates.check_state_contract"
        assert _imports_module(ast.parse(f"from {dotted} import x"), dotted)
        assert _imports_module(ast.parse(f"import {dotted}"), dotted)
        assert _imports_module(ast.parse("from scripts.gates import check_state_contract"), dotted)
        assert not _imports_module(ast.parse("from scripts.gates import other"), dotted)
        assert not _imports_module(ast.parse("import scripts.gates.check_state_contract_v2"), dotted)

    def test_dead_declaration_comment_still_claims_writer(self):
        """锁定发现本身：声明处注释承诺 `_debugger_node 写入 True`，而全仓零写者。"""
        state_py = (PROJECT_ROOT / "src" / "graph" / "state.py").read_text(encoding="utf-8")
        assert "failure_frequency_applied" in state_py
        assert "_debugger_node 写入 True" in state_py
        cov = channel_coverage()
        assert "failure_frequency_applied" in cov.untouched
        for other in (PROJECT_ROOT / "src").rglob("*.py"):
            if other.name == "state.py":
                continue
            assert "failure_frequency_applied" not in other.read_text(encoding="utf-8"), other

    def test_update_dict_counted_on_probe(self, tmp_path):
        probe = tmp_path / "probe.py"
        probe.write_text(
            'def n(state):\n    state.update({"target_code": 1})\n    return {"error_category": 2}\n',
            encoding="utf-8",
        )
        usage = _walk_channel_usage([probe], {"target_code", "error_category"})
        assert usage.update == {"target_code": 1, "error_category": 1}
        assert sum(usage.read.values()) == 0 and sum(usage.inplace.values()) == 0

    def test_update_dict_foreign_keys_not_attributed(self, tmp_path):
        probe = tmp_path / "probe.py"
        probe.write_text(
            'def helper(state):\n    return {"status": 1, "passed": 2}\n',
            encoding="utf-8",
        )
        usage = _walk_channel_usage([probe], {"target_code"})
        assert usage.foreign_update == 2
        assert sum(usage.update.values()) == 0

    def test_read_inplace_temp_dynamic_counted_separately(self, tmp_path):
        probe = tmp_path / "probe.py"
        probe.write_text(
            "def n(state, k):\n"
            '    state["target_code"] = "x"\n'
            '    _ = state.get("error_category")\n'
            '    state["_tmp"] = 1\n'
            "    state[k] = 2\n"
            '    state["undeclared_z"] = 3\n'
            '    _ = state.get("undeclared_y")\n',
            encoding="utf-8",
        )
        usage = _walk_channel_usage([probe], {"target_code", "error_category"})
        assert usage.inplace == {"target_code": 1}
        assert usage.read == {"error_category": 1}
        assert usage.temp == {"_tmp": 1}
        assert usage.dynamic_sites == 1
        assert usage.undeclared_sites == 2

    def test_update_dicts_are_disclosed_not_judged(self, tmp_path):
        """边界锁：update dict 只披露不判定——否则辅助函数的普通 dict 会被误判。"""
        probe = tmp_path / "probe.py"
        probe.write_text(
            'def helper(state):\n    return {"not_a_state_key": 1}\n',
            encoding="utf-8",
        )
        assert _audit_file(probe, declared_state_keys()) == []

    def test_coverage_cli_prints_key_table(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "gates" / "check_state_contract.py"), "--coverage"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "状态通道逐键覆盖" in result.stdout
        assert "failure_frequency_applied: 0 / 0 / 0" in result.stdout
        assert "审计面披露：声明 118 键" in result.stdout

    def test_success_message_carries_disclosure(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "gates" / "check_state_contract.py")],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        assert lines[0].startswith("状态通道契约审计通过")
        assert any("审计面披露" in ln for ln in lines)
        assert any("update dict 47 键 / 99 站点" in ln for ln in lines)
        assert any("failure_frequency_applied" in ln for ln in lines)

    def test_coverage_lines_are_stable(self):
        cov = channel_coverage()
        lines = coverage_lines(cov)
        assert len(lines) == 4
        assert all(ln.startswith("  ") for ln in lines)

    def test_module_loads_without_sys_modules_registration(self):
        """NamedTuple 而不是 dataclass：历史加载器不登记 sys.modules（CA 轮教训）。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_state_contract_unregistered",
            PROJECT_ROOT / "scripts" / "gates" / "check_state_contract.py",
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cov = module.channel_coverage()
        assert len(cov.declared) == 118
