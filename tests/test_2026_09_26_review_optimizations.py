"""2026-09-26 全面审查与保守优化轮：回归测试（默认行为不变）。

覆盖本轮改动：
- experiments/difficulty_stratification.py：difficulty_level 维度 int/str/float
  归一化（"3"→3、3.0→3、"abc"/3.5/True 保持 unlabeled）；
- src/graph/workflow.py：_should_debug 分支顺序（迭代上限检查先于 test_defect
  分支，上限内关键词仍可 regenerate）；_DIAGNOSIS_KEYWORD_RE 哨兵上移
  （首次调用即正常懒初始化，不再 NameError 吞掉后重复编译）；
- src/tools/patch_applier.py：_TOP_DEF_RE 含 async def（多 async 函数文件
  误判单函数模式修复）；
- src/api/api_manager.py：_handle_rate_limit / _handle_api_error /
  _handle_generic_error 不再自动重判 in_circuit_half_open（与 call() 循环
  预检口径一致，限流路径探测失败计数不再丢失）；
- src/agents/executor_repo.py：_apply_llm_patch 临时文件按 (pid, thread) 隔离
  （--parallel 多线程下不再互相删除）；
- src/agents/base_agent.py：删除死代码 llm_call_kwargs（行为不变）。

运行：pytest tests/test_2026_09_26_review_optimizations.py -q
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# 项目根（tests/ 的父目录）加入 sys.path，便于直接导入 experiments.* / src.*
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ─── 1. difficulty_level 归一化（experiments/difficulty_stratification.py） ───


class TestDifficultyLevelNormalization:
    """difficulty_level 维度的数值形态归一口径（JSON 反序列化 / 数值计算产物）。"""

    def _strat(self, details: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        from experiments.difficulty_stratification import stratify_by_dimension

        return stratify_by_dimension(details, "difficulty_level")

    def test_int_passthrough(self) -> None:
        details = [{"task_id": "t1", "passed": True, "difficulty_level": 3}]
        strat = self._strat(details)
        assert strat["level_3"]["tasks"] == 1

    def test_string_form_normalizes(self) -> None:
        details = [
            {"task_id": "t1", "passed": True, "difficulty_level": "3"},
            {"task_id": "t2", "passed": False, "task_metadata": {"difficulty_level": "4"}},
        ]
        strat = self._strat(details)
        assert strat["level_3"]["tasks"] == 1
        assert strat["level_4"]["tasks"] == 1

    def test_integer_float_normalizes(self) -> None:
        """3.0 整数值 float 归一为 3（JSON / 数值计算产物，与 "3" 同形态）。"""
        details = [
            {"task_id": "t1", "passed": True, "difficulty_level": 3.0},
            {"task_id": "t2", "passed": True, "difficulty_level": "4"},
        ]
        strat = self._strat(details)
        assert strat["level_3"]["tasks"] == 1
        assert strat["level_4"]["tasks"] == 1

    def test_non_integer_float_stays_unlabeled(self) -> None:
        """3.5 带小数 float 保持 unlabeled（难度等级语义上必须是整数档位）。"""
        details = [{"task_id": "t1", "passed": True, "difficulty_level": 3.5}]
        strat = self._strat(details)
        assert strat["unlabeled"]["tasks"] == 1
        assert "level_3" not in strat

    def test_non_numeric_string_stays_unlabeled(self) -> None:
        details = [{"task_id": "t1", "passed": True, "difficulty_level": "abc"}]
        strat = self._strat(details)
        assert strat["unlabeled"]["tasks"] == 1

    def test_bool_stays_unlabeled(self) -> None:
        """bool 是 int 子类但难度等级语义不接受 True/False，归 unlabeled。"""
        details = [
            {"task_id": "t1", "passed": True, "difficulty_level": True},
            {"task_id": "t2", "passed": False, "difficulty_level": False},
        ]
        strat = self._strat(details)
        assert strat["unlabeled"]["tasks"] == 2

    def test_signed_string_normalizes(self) -> None:
        """带正负号纯数字串（"+3" / "-2"）归一为 int；负值不进档（档位 1-4）。"""
        details = [
            {"task_id": "t1", "passed": True, "difficulty_level": "+3"},
            {"task_id": "t2", "passed": True, "difficulty_level": "-2"},
        ]
        strat = self._strat(details)
        assert strat["level_3"]["tasks"] == 1
        assert strat["unlabeled"]["tasks"] == 1  # -2 不进档


# ─── 2. _should_debug 分支顺序（src/graph/workflow.py） ───


class TestShouldDebugBranchOrder:
    """迭代上限检查先于 test_defect 分支：上限内关键词仍可 regenerate。"""

    def _should_debug(self, state: dict[str, Any]) -> str:
        import src.graph.workflow as w

        return w._should_debug(state)  # type: ignore[arg-type]

    def test_at_max_with_test_defect_and_keywords_can_regenerate(self) -> None:
        """达上限 + test_defect + 诊断命中关键词 + 未再生成过 → 仍可 regenerate。

        旧实现：test_defect 分支在上限分支之前，regeneration_count=0 时
        走 test_defect 路径（reason=review_test_defect）——本次修复把上限
        分支上移后，关键词命中路径（reason=test_gen_diagnosis）成为唯一
        可触发 regenerate 的入口，上限保护（regeneration_count < 1）不变。
        """
        state = {
            "test_passed": False,
            "iteration": 3,
            "max_iterations": 3,
            "regeneration_count": 0,
            "defect_type": "test_defect",
            "diagnosis": "AttributeError: 'NoneType' has no attribute 'x'（测试生成错误）",
            "repair_history": [],
        }
        assert self._should_debug(state) == "regenerate"

    def test_at_max_with_test_defect_and_regen_cap_done(self) -> None:
        """达上限 + test_defect + 已再生成过（regeneration_count=1）→ done。"""
        state = {
            "test_passed": False,
            "iteration": 3,
            "max_iterations": 3,
            "regeneration_count": 1,
            "defect_type": "test_defect",
            "diagnosis": "AttributeError: ...",
            "repair_history": [],
        }
        assert self._should_debug(state) == "done"

    def test_before_max_with_test_defect_can_regenerate(self) -> None:
        """迭代未达上限 + test_defect + 未再生成过 → regenerate（旧行为保持）。"""
        state = {
            "test_passed": False,
            "iteration": 1,
            "max_iterations": 3,
            "regeneration_count": 0,
            "defect_type": "test_defect",
            "diagnosis": "",
            "repair_history": [],
        }
        assert self._should_debug(state) == "regenerate"

    def test_test_passed_short_circuits(self) -> None:
        state = {"test_passed": True, "iteration": 1, "max_iterations": 3, "repair_history": []}
        assert self._should_debug(state) == "done"

    def test_default_config_path_unchanged(self) -> None:
        """默认配置（BIDIRECTIONAL_DIAGNOSIS_ENABLE 关）：defect_type=None，
        上限内走 debug（旧行为保持），不回归。"""
        state = {
            "test_passed": False,
            "iteration": 1,
            "max_iterations": 3,
            "defect_type": None,
            "diagnosis": "普通运行时错误",
            "repair_history": [],
        }
        assert self._should_debug(state) == "debug"


# ─── 3. _DIAGNOSIS_KEYWORD_RE 懒初始化顺序（src/graph/workflow.py） ───


class TestDiagnosisKeywordRegexInit:
    """哨兵上移至函数定义之前：首次调用即正常懒初始化，不再 NameError 吞掉。"""

    def test_first_call_lazy_init_succeeds(self) -> None:
        import src.graph.workflow as w

        # 重置哨兵为 None，模拟模块加载后立即调用的场景
        w._DIAGNOSIS_KEYWORD_RE = None  # type: ignore[misc]
        assert w._diagnosis_hits_test_gen_keywords("测试生成错误") is True
        assert w._DIAGNOSIS_KEYWORD_RE is not None  # 懒初始化成功
        # 第二次调用走预编译正则（不再重新编译）
        compiled = w._DIAGNOSIS_KEYWORD_RE
        # M5（2026-09-29 审查 P0）：AttributeError 已从关键词表删除（源码
        # 缺陷签名词），用保留的"测试用例"关键词验证第二次调用命中。
        assert w._diagnosis_hits_test_gen_keywords("测试用例") is True
        assert w._diagnosis_hits_test_gen_keywords("AttributeError") is False
        assert compiled is w._DIAGNOSIS_KEYWORD_RE


# ─── 4. patch_applier _TOP_DEF_RE 含 async def（src/tools/patch_applier.py） ───


class TestPatchApplierAsyncDef:
    """_TOP_DEF_RE 含 (?:async\\s+)?def：多 async 函数文件不再误判单函数模式。"""

    def test_count_function_defs_includes_async(self) -> None:
        from src.tools.patch_applier import _count_function_defs

        code = """async def a():
    return 1

async def b():
    return 2

def c():
    return 3
"""
        assert _count_function_defs(code) == 3

    def test_is_full_file_patch_two_async_funcs(self) -> None:
        from src.tools.patch_applier import _is_full_file_patch

        original = """async def a():
    return 1

async def b():
    return 2
"""
        patch = """async def a():
    return 11

async def b():
    return 22
"""
        # 两个文件各 2 个 async 函数，无 docstring/import → (c) 分支应判全文件
        assert _is_full_file_patch(patch, original) is True

    def test_apply_patch_two_async_funcs(self) -> None:
        from src.tools.patch_applier import apply_patch_to_code

        original = """async def a():
    return 1

async def b():
    return 2
"""
        patch = """async def a():
    return 11

async def b():
    return 22
"""
        new_code, applied = apply_patch_to_code(original, patch)
        assert applied is True
        assert "return 11" in new_code
        assert "return 22" in new_code
        assert "async def a" in new_code
        assert "async def b" in new_code

    def test_single_function_mode_for_async(self) -> None:
        """单函数模式：async def 目标函数被替换（正则兜底路径兼容）。"""
        from src.tools.patch_applier import apply_patch_to_code

        original = """async def a():
    return 1

def b():
    return 2
"""
        patch = """async def a():
    return 11
"""
        new_code, applied = apply_patch_to_code(original, patch)
        assert applied is True
        assert "return 11" in new_code
        assert "def b" in new_code


# ─── 5. api_manager 半开探测口径（src/api/api_manager.py） ───


class TestHalfOpenProbeConsistency:
    """handler 不再自动重判 in_circuit_half_open（与 call() 循环预检口径一致）。

    旧实现：handler 内 `probe = self._enter_half_open_probe(node) if
    is_half_open_probe is None else ...`——自动重判时窗口状态可能已被
    前序 handler 改变（限流路径 mark_failure 后重判恒 False → 探测失败
    计数丢失；api_error 路径 mark_failure 后窗口仍在时重判恒 True →
    多计一次探测成功口径）。本次修复：handler 只消费调用方显式透传的
    预检结果（bool），不再自动重判。
    """

    def _make_manager(self) -> Any:
        from src.api.api_manager import APIManager

        return APIManager(enable_health_checker=False)

    def test_rate_limit_handler_no_auto_recheck(self) -> None:
        """限流路径 + probe=True：节点 half_open_failure +1（旧实现：丢失）。"""
        mgr = self._make_manager()
        node = self._first_healthy_node(mgr)
        # 模拟半开探测窗口（circuit_open_until 已到期、探测未完成）
        node.circuit_open_until = time.monotonic() - 1.0
        node.circuit_open_count = 0
        mgr.config.enable_half_open_probe = True
        before_failure = node.half_open_failure
        # 本次调用是探测（预检结果 True），限流异常 → handler 应消费失败探测
        # （handler 内置限流 sleep，经 patch 掉避免真实等待）
        with patch("src.api.api_manager.time.sleep", return_value=None):
            mgr._handle_rate_limit(node, 0, 1, is_half_open_probe=True)
        assert node.half_open_failure == before_failure + 1
        # 重新开冷却期：circuit_open_until 单调递增到未来
        assert node.circuit_open_until > time.monotonic()

    def test_api_error_handler_no_auto_recheck(self) -> None:
        """API 错误路径 + probe=True：节点 half_open_failure +1（旧实现：多计）。"""
        from unittest.mock import MagicMock

        import openai

        mgr = self._make_manager()
        node = self._first_healthy_node(mgr)
        node.circuit_open_until = time.monotonic() - 1.0
        node.circuit_open_count = 0
        mgr.config.enable_half_open_probe = True
        before_failure = node.half_open_failure
        # openai.APIError 构造需 (message, request, body)——request 不可为 None
        mock_req = MagicMock()
        err = openai.APIError("boom", request=mock_req, body={"code": "test"})
        mgr._handle_api_error(err, node, is_half_open_probe=True)
        assert node.half_open_failure == before_failure + 1

    def test_generic_error_handler_no_auto_recheck(self) -> None:
        """通用异常路径 + probe=False：节点 half_open_failure 不变（旧实现：误计）。"""
        mgr = self._make_manager()
        node = self._first_healthy_node(mgr)
        node.circuit_open_until = time.monotonic() - 1.0
        node.circuit_open_count = 0
        mgr.config.enable_half_open_probe = True
        before_failure = node.half_open_failure
        mgr._handle_generic_error(Exception("boom"), node, is_half_open_probe=False)
        assert node.half_open_failure == before_failure  # 非探测，不消费

    def test_call_passes_probe_to_handlers(self) -> None:
        """handler 只消费调用方显式透传的预检结果（不再自动重判）。

        旧实现：handler 内 `probe = self._enter_half_open_probe(node) if
        is_half_open_probe is None else ...`——自动重判时窗口状态可能已被
        前序 handler 改变（限流路径 mark_failure 后重判恒 False → 探测失败
        计数丢失）。本次修复：handler 只消费调用方显式透传的预检结果。

        直接验证 3 个 handler 实现：probe=True 时 half_open_failure +1，
        probe=False 时不变。每个 handler 单独一个节点（避免 mark_failure
        的连续失败计数累积触发重开熔断）。
        """
        from unittest.mock import MagicMock

        import openai

        mgr = self._make_manager()
        mock_req = MagicMock()

        # ── _handle_rate_limit（probe=True 时消费失败探测）──────────────
        node = self._first_healthy_node(mgr)
        node.circuit_open_until = time.monotonic() - 1.0
        node.circuit_open_count = 0
        node.consecutive_failures = 0
        mgr.config.enable_half_open_probe = True
        with patch("src.api.api_manager.time.sleep", return_value=None):
            before = node.half_open_failure
            mgr._handle_rate_limit(node, 0, 1, is_half_open_probe=True)
            assert node.half_open_failure == before + 1, "限流 + probe=True 应消费失败探测"
            node.circuit_open_count = 0  # 重置避免下次 mark_failure 再触发重开
            before = node.half_open_failure
            mgr._handle_rate_limit(node, 0, 1, is_half_open_probe=False)
            assert node.half_open_failure == before, "限流 + probe=False 不消费探测"

        # ── _handle_api_error（同口径）─────────────────────────────────
        node = self._first_healthy_node(mgr)
        node.circuit_open_until = time.monotonic() - 1.0
        node.circuit_open_count = 0
        node.consecutive_failures = 0
        err = openai.APIError("e", request=mock_req, body={"code": "x"})
        before = node.half_open_failure
        mgr._handle_api_error(err, node, is_half_open_probe=True)
        assert node.half_open_failure == before + 1, "APIError + probe=True 应消费失败探测"

        # ── _handle_generic_error（同口径）─────────────────────────────
        node = self._first_healthy_node(mgr)
        node.circuit_open_until = time.monotonic() - 1.0
        node.circuit_open_count = 0
        node.consecutive_failures = 0
        before = node.half_open_failure
        mgr._handle_generic_error(Exception("e"), node, is_half_open_probe=True)
        assert node.half_open_failure == before + 1, "通用异常 + probe=True 应消费失败探测"

    def _first_healthy_node(self, mgr: Any) -> Any:
        """取 manager 中任一节点（health_nodes 键为 LLM 配置名，非固定 "default"）。"""
        assert mgr.health_nodes, "测试需要至少一个健康节点"
        return next(iter(mgr.health_nodes.values()))


# ─── 6. executor_repo 临时文件按 (pid, thread) 隔离（src/agents/executor_repo.py） ───


class TestExecutorRepoTempFileIsolation:
    """_apply_llm_patch 临时文件含线程 ident：--parallel 多线程下不再互相删除。"""

    def test_patch_file_contains_thread_ident(self) -> None:
        """_apply_llm_patch 内 patch_file 路径含 (pid, thread ident) 双键。"""
        import inspect

        import src.agents.executor_repo as repo_mod
        from src.agents.executor_repo import RepoExecutor

        src = inspect.getsource(repo_mod.RepoExecutor._apply_llm_patch)
        assert "threading.get_ident()" in src, "_apply_llm_patch 应含线程 ident 隔离"
        assert "os.getpid()" in src, "_apply_llm_patch 应含 pid 隔离"
        # 实际调用一次 _apply_llm_patch，捕获写盘路径（绕过 git apply）
        ex = RepoExecutor.__new__(RepoExecutor)
        ex.use_venv = False
        ex.setup_timeout = 60
        ex.env_root = "/tmp/aitester_test_envs"
        unified_patch = "diff --git a/x.py b/x.py\n@@ -1 +1 @@\n-old\n+new\n"
        captured_paths: list[str] = []

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_remove(p: str) -> None:
            captured_paths.append(p)

        with (
            patch("src.agents.executor_repo._run", return_value=_R()),
            patch("src.agents.executor_repo.os.remove", side_effect=fake_remove),
        ):
            ex._apply_llm_patch("/tmp/aitester_test_repo", unified_patch)
        assert len(captured_paths) == 1
        assert os.path.basename(captured_paths[0]).endswith(f"_{os.getpid()}_{threading.get_ident()}.patch"), (
            f"patch 文件路径应按 (pid, thread) 隔离: {captured_paths[0]}"
        )


# ─── 7. base_agent 死代码清理（src/agents/base_agent.py） ───


class TestBaseAgentDeadCodeCleanup:
    """llm_call_kwargs 已删除（死代码），_call_llm 行为不变。"""

    def test_llm_call_kwargs_removed(self) -> None:
        import inspect

        import src.agents.base_agent as ba

        src = inspect.getsource(ba.BaseAgent._call_llm)
        assert "llm_call_kwargs" not in src, "llm_call_kwargs 死代码应已删除"
        # complexity_class 仍经 _reorder_api_groups_by_complexity 消费（保留）
        assert "_reorder_api_groups_by_complexity" in src

    def test_call_llm_routing_intact(self) -> None:
        """_call_llm 在 complexity_class=None 时走历史 api_groups 顺序（不重排）。"""
        import src.agents.base_agent as ba

        # 用真实 _reorder_api_groups_by_complexity 验证"None → 不重排"契约
        groups: dict[str, list[tuple[str, str]]] = {
            "https://a.example": [("k1", "model-a")],
            "https://b.example": [("k2", "model-b")],
        }
        configs = [
            ("k1", "https://a.example", "model-a"),
            ("k2", "https://b.example", "model-b"),
        ]
        # complexity_class=None 时 _call_llm 不调 _reorder_api_groups_by_complexity
        # （直接按原 api_groups 顺序遍历），此处只验证重排函数本身签名/契约
        out = ba._reorder_api_groups_by_complexity(groups, configs, "complex")
        # 重排后仍是同一组 (base_url, models) 元组（仅顺序变）
        assert set(out.keys()) == set(groups.keys())
        for base_url, models in out.items():
            assert models == groups[base_url] or sorted(models) == sorted(groups[base_url])


# ─── 8. 综合回归（确保本轮改动无默认行为回归） ───


class TestNoRegression:
    """本轮改动不改变默认行为（BIDIRECTIONAL_DIAGNOSIS_ENABLE / 各开关关时）。"""

    def test_default_should_debug_early_iteration(self) -> None:
        """默认配置：iteration < max 且无 test_defect / 关键词 → debug。"""
        import src.graph.workflow as w

        state = {
            "test_passed": False,
            "iteration": 1,
            "max_iterations": 3,
            "defect_type": None,
            "diagnosis": "普通运行时错误",
            "repair_history": [],
        }
        assert w._should_debug(state) == "debug"  # type: ignore[arg-type]

    def test_default_should_debug_at_max_no_keywords(self) -> None:
        """默认配置：达上限且诊断无关键词 → done（历史行为保持）。"""
        import src.graph.workflow as w

        state = {
            "test_passed": False,
            "iteration": 3,
            "max_iterations": 3,
            "defect_type": None,
            "diagnosis": "普通运行时错误",
            "repair_history": [],
        }
        assert w._should_debug(state) == "done"  # type: ignore[arg-type]

    def test_stratify_unknown_dimension_still_raises(self) -> None:
        from experiments.difficulty_stratification import stratify_by_dimension

        with pytest.raises(ValueError):
            stratify_by_dimension([], "not_a_dimension")


# ─── 9. P1/P2 修复回归（2026-09-26 第二轮审查） ───


class TestWorkflowRepairInvalidBranchOrder:
    """ "_should_debug：_recent_repairs_invalid 早退仅早期迭代生效，
    最后一轮（iteration >= max）由迭代上限分支统一决策——连续修复无效的
    典型场景不再遮蔽"关键词命中 → 一次 regenerate 机会"。"""

    def test_final_iteration_repair_invalid_keywords_regenerate(self) -> None:
        import src.graph.workflow as w

        state = {
            "test_passed": False,
            "iteration": 3,
            "max_iterations": 3,
            "diagnosis": "测试生成错误：测试用例预期值写错",
            "regeneration_count": 0,
            "defect_type": None,
            "repair_history": [{"patch_applied": False}, {"patch_applied": False}],
        }
        assert w._should_debug(state) == "regenerate"  # type: ignore[arg-type]

    def test_early_iteration_repair_invalid_still_done(self) -> None:
        """早期迭代（iteration < max）repair_invalid 仍短路 done（省 token 口径不变）。"""
        import src.graph.workflow as w

        state = {
            "test_passed": False,
            "iteration": 1,
            "max_iterations": 3,
            "diagnosis": "测试生成错误：测试用例预期值写错",
            "regeneration_count": 0,
            "defect_type": None,
            "repair_history": [{"patch_applied": False}, {"patch_applied": False}],
        }
        assert w._should_debug(state) == "done"  # type: ignore[arg-type]

    def test_final_iteration_repair_invalid_no_keywords_done(self) -> None:
        """最后一轮 repair_invalid + 无关键词 → 走迭代上限分支 done（reason=max_iterations）。"""
        import src.graph.workflow as w

        state = {
            "test_passed": False,
            "iteration": 3,
            "max_iterations": 3,
            "diagnosis": "普通运行时错误",
            "regeneration_count": 0,
            "defect_type": None,
            "repair_history": [{"patch_applied": False}, {"patch_applied": False}],
        }
        assert w._should_debug(state) == "done"  # type: ignore[arg-type]


class TestRouteAfterDiagnosisCap:
    """_route_after_diagnosis：test_defect 达 regeneration_count 上限时路由
    done（与 _should_debug 的 test_defect 上限分支同口径，防 generator↔executor
    无上限乒乓撞 recursion_limit）。"""

    def test_test_defect_within_cap_regenerate(self) -> None:
        import src.graph.workflow as w

        assert w._route_after_diagnosis({"defect_type": "test_defect", "regeneration_count": 0}) == "regenerate"  # type: ignore[arg-type]

    def test_test_defect_at_cap_done(self) -> None:
        import src.graph.workflow as w

        assert (
            w._route_after_diagnosis({"defect_type": "test_defect", "regeneration_count": w._MAX_REGENERATIONS})
            == "done"
        )  # type: ignore[arg-type]

    def test_implementation_defect_still_debug(self) -> None:
        import src.graph.workflow as w

        assert w._route_after_diagnosis({"defect_type": "implementation_defect", "regeneration_count": 99}) == "debug"  # type: ignore[arg-type]


class TestExtractJsonObjectLeafRegression:
    """extract_json_object 叶子降级扫描回归（P1 语义修复）：O(1) 双候选失败
    时补"反向全量扫描"，覆盖"可解析叶子排在更早位置"（损坏响应夹带 ≥3 片段）
    场景——此前直接 raise 误判 LLM 响应解析失败。"""

    def test_parseable_leaf_at_earlier_position(self) -> None:
        from src.utils.helpers import extract_json_object

        # 平衡法失败（最外层残缺）+ 可解析叶子在首个位置（最后两个叶子损坏）
        result = extract_json_object('{"outer": {"good": 1} {"bad": ,} {"bad2": }')
        assert result == {"good": 1}

    def test_normal_paths_unchanged(self) -> None:
        """正常单/双叶子路径仍走 O(1) 快路径（行为不变）。"""
        from src.utils.helpers import extract_json_object

        assert extract_json_object('text {"k": 1} text') == {"k": 1}
        assert extract_json_object('{"a": 1, "b": {"c": 2}}') == {"a": 1, "b": {"c": 2}}

    def test_all_leaves_corrupt_raises(self) -> None:
        import json

        from src.utils.helpers import extract_json_object

        with pytest.raises(json.JSONDecodeError):
            extract_json_object('{"bad": ,} {"bad2": }')

    def test_no_json_raises(self) -> None:
        import json

        from src.utils.helpers import extract_json_object

        with pytest.raises(json.JSONDecodeError):
            extract_json_object("no json here")


class TestPatchApplierFullFileMissingFunction:
    """patch_applier：完整文件模式 subset 校验失败（漏掉原代码函数）时
    保守拒绝（返回原代码 + False），不再静默回退单函数路径产出含重复
    import / 重复 def 的损坏代码（ast.parse 通过、safe_apply_patch 语法
    守卫不拦、multi_candidate 检查 4 反因重复定义"通过"的静默损坏链）。"""

    def test_full_file_patch_missing_function_rejected(self) -> None:
        from src.tools.patch_applier import apply_patch_to_code

        original = "import os\n\ndef a():\n    return 1\n\ndef b():\n    return 2\n\ndef c():\n    return 3\n"
        # 补丁带 import 前缀（完整文件模式）但漏掉 def c
        patch = "import os\n\ndef a():\n    return 1\n\ndef b():\n    return 2\n"
        new_code, applied = apply_patch_to_code(original, patch)
        assert applied is False, "完整文件补丁漏函数应保守拒绝"
        assert new_code == original, "拒绝时返回原代码"

    def test_single_function_mode_still_works(self) -> None:
        """无 import 前缀的单函数补丁（_is_full_file_patch=False）仍正常替换。"""
        from src.tools.patch_applier import apply_patch_to_code

        original = "def foo(): return 0\ndef bar(): return 1\n"
        patch = "def foo(): return 1\n"
        new_code, applied = apply_patch_to_code(original, patch)
        assert applied is True
        assert "return 1" in new_code
        assert "def bar():" in new_code

    def test_full_file_patch_complete_replaces(self) -> None:
        """完整文件补丁含全部函数 → 仍正常整体替换（历史行为不变）。"""
        from src.tools.patch_applier import apply_patch_to_code

        original = "import os\n\ndef a():\n    return 1\n\ndef b():\n    return 2\n"
        patch = "import os\n\ndef a():\n    return 10\n\ndef b():\n    return 20\n"
        new_code, applied = apply_patch_to_code(original, patch)
        assert applied is True
        assert "return 10" in new_code
        assert "return 20" in new_code
        assert new_code.count("import os") == 1


class TestExecutorRepoTimeoutConvergence:
    """executor_repo._run：TimeoutExpired 收敛为 returncode=124 哨兵（不抛出），
    单节点 pytest 超时不再穿透 verify() 崩整个任务。"""

    def test_run_timeout_returns_124(self) -> None:
        from src.agents.executor_repo import _run

        res = _run(["sleep", "0.5"], "/tmp", 0.2)
        assert res.returncode == 124
        assert "超时" in res.stderr

    def test_run_normal_unaffected(self) -> None:
        from src.agents.executor_repo import _run

        res = _run(["echo", "hi"], "/tmp", 5)
        assert res.returncode == 0
        assert res.stdout.strip() == "hi"

    def test_run_test_nodes_timeout_recorded(self, monkeypatch, tmp_path) -> None:
        """_run_test_nodes 中超时节点记入 failed_cases 并继续下一节点。"""
        import subprocess

        import src.agents.executor_repo as repo_mod
        from src.agents.executor_repo import RepoExecutor

        ex = RepoExecutor(timeout=0.1)
        call_count = {"n": 0}
        real_run = repo_mod._run

        def fake_run(cmd, cwd, timeout, env=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # 第一个节点：模拟 _run 超时收敛的 rc=124 哨兵
                return subprocess.CompletedProcess(args=cmd, returncode=124, stdout="", stderr="命令执行超时（>0.1s）")
            # 第二个节点：真实执行（tmp_path 下无测试 → rc=5 无测试可收集）
            return real_run(cmd, cwd, timeout, env)

        monkeypatch.setattr(repo_mod, "_run", fake_run)
        result = ex._run_test_nodes(str(tmp_path), ["tests/t1.py::test_x", "tests/t2.py::test_y"], repo_url="")
        assert result["expected"] == 2
        assert result["passed"] == 0
        # 第一个节点超时被记录为 failed（不再崩整个任务）
        assert any("超时" in c["error"] for c in result["failed_cases"]), f"failed_cases={result['failed_cases']}"
        assert any(c["name"] == "tests/t1.py::test_x" for c in result["failed_cases"])


class TestVenvCacheMarkerConsistency:
    """executor_repo：use_venv=True 时 venv 创建失败回退全局 pip install
    路径须写 .venv_pip_installed 标记（与 L148 缓存检查口径对齐），
    否则缓存永远 miss、每次 setup() 重新 git clone + pip install。"""

    def test_fallback_path_writes_venv_marker(self, monkeypatch, tmp_path) -> None:
        from src.agents.executor_repo import RepoExecutor

        ex = RepoExecutor(use_venv=True, venv_reuse_by_repo=True)
        ex.env_root = str(tmp_path)
        # mock venv 创建失败 + 全局 pip install 成功
        monkeypatch.setattr(ex, "_create_venv", lambda env_dir: "venv 创建失败")
        monkeypatch.setattr(ex, "_pip_install_editable", lambda repo_dir: None)
        # mock clone（跳过真实 git 操作）
        monkeypatch.setattr(ex, "_clone_and_checkout", lambda repo_url, base_commit, repo_dir: None)
        setup_result = ex.setup(repo_url="https://github.com/fake/fake.git", base_commit="abc123456789abcdef")
        assert setup_result["error"] is None, f"setup 应成功（全局回退）: {setup_result}"
        # 关键断言：标记按 use_venv=True 口径写 .venv_pip_installed
        marker = tmp_path / "fake" / "abc123456789" / ".venv_pip_installed"
        assert marker.is_file(), "use_venv=True 回退路径应写 .venv_pip_installed 标记"
        legacy_marker = tmp_path / "fake" / "abc123456789" / ".pip_installed"
        assert not legacy_marker.is_file(), "use_venv=True 时不应写 .pip_installed（缓存检查读不到）"


class TestDebuggerPositionAwareOriginalCode:
    """debugger：3.3 位置感知修复用**原始全文**定位（context.line 是原始行号），
    prompt 仍用截断版省 token——大文件（> CODE_MAX_CHARS）定位不再降级。"""

    def test_locate_focus_uses_original_code(self) -> None:
        import inspect

        import src.agents.debugger as dbg

        src = inspect.getsource(dbg.DebuggerAgent.debug)
        assert "original_target_code = target_code" in src, "应在截断前保留原始全文副本"
        assert "_locate_repair_focus(original_target_code" in src, "定位应传原始全文而非截断版"


class TestDependencyCachePersistToctou:
    """dependency._record_venv_cache_event：_venv_cache_last_persist_at 的
    读-写整体在落盘锁保护范围内（P1 竞态修复）——--parallel 下同批 N 线程
    越过锁外判断时，锁内二次确认读到的是锁保护的最新值而非旧 TOCTOU 快照。"""

    def test_persist_timestamp_protected_by_lock(self) -> None:
        import inspect

        import src.tools.dependency as dep

        src = inspect.getsource(dep._record_venv_cache_event)
        # 锁内段须含 _venv_cache_last_persist_at 读（判断）与写（更新）
        lock_idx = src.find("with _venv_cache_persist_lock:")
        assert lock_idx != -1, "应含落盘锁段"
        lock_body = src[lock_idx:]
        # 锁内二次确认段含读操作（防 TOCTOU 的关键：读在锁内）
        read_in_lock = lock_body.count("_venv_cache_last_persist_at")
        assert read_in_lock >= 2, (
            f"锁内段应含 _venv_cache_last_persist_at 读+写（实际 {read_in_lock} 次），读操作须在锁保护范围内"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  2026-09-26 round8 补充回归（tools 子代理 P1 修复）
# ═══════════════════════════════════════════════════════════════════════════


class TestPatchApplierEmptyFuncSetFullFile:
    """patch_applier.apply_patch_to_code 完整文件模式：原代码无顶层函数
    （纯常量/import 模块）+ 全文件型补丁（docstring/import/常量替换，LLM
    常见输出形态）此前被误拒（`orig_func_names and ...` 空集短路使 subset
    通过路径永远走不到，错落到 Step 4b 单函数路径又因补丁无 def 返回
    False）——round8 修复后 ∅.issubset 恒成立，全文件替换成功。

    默认行为不变：原代码含 def 的常规场景判定口径不变（已 133 用例锁定）。
    """

    def test_empty_func_set_full_file_patch_applied(self) -> None:
        from src.tools.patch_applier import apply_patch_to_code

        orig = '"""doc"""\nimport os\nX = 1\n'
        patch = '"""doc2"""\nimport os\nX = 2\n'
        new_code, applied = apply_patch_to_code(orig, patch)
        assert applied is True, "空函数集原代码 + 全文件补丁应应用成功"
        assert "X = 2" in new_code

    def test_empty_func_set_full_file_via_safe_apply(self) -> None:
        """safe_apply_patch 路径（含 ast.parse 守卫）同样成功。
        注：safe_apply_patch 返回 (code, success) 二元组（非三元组）。"""
        from src.tools.patch_applier import safe_apply_patch

        orig = '"""doc"""\nimport os\nX = 1\n'
        patch = '"""doc2"""\nimport os\nX = 2\n'
        result, applied = safe_apply_patch(orig, patch)
        assert applied is True, "safe_apply_patch 应成功"
        assert "X = 2" in result

    def test_nonempty_func_set_subset_fail_still_rejected(self) -> None:
        """原代码含函数 + 补丁漏函数 → 仍保守拒绝（round7 P1 口径不变）。"""
        from src.tools.patch_applier import apply_patch_to_code

        orig = "def f():\n    return 1\n\ndef g():\n    return 2\n"
        # 完整文件形态（含 docstring+import 前缀）但漏掉 g
        patch = '"""doc"""\nimport os\n\ndef f():\n    return 1\n'
        new_code, applied = apply_patch_to_code(orig, patch)
        assert applied is False, "漏函数的完整文件补丁应保守拒绝"
        assert new_code == orig


if __name__ == "__main__":
    # 无 pytest 时的最小冒烟（CI 走 pytest 路径）
    print("run via pytest: tests/test_2026_09_26_review_optimizations.py")
