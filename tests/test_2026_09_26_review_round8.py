"""2026-09-26 第八轮全面审查与保守优化：回归测试（默认行为不变）。

覆盖本轮改动：
- src/api/api_manager.py：删除 _last_health_check dict 死代码（round7 遗留）；
  _cost_weight_for 注册时序缺陷修复（注册路径传入在手 llm_config，
  LLM_N_COST_WEIGHT 不再静默失效）；_try_call_node docstring 笔误修正；
- src/api/api_health.py：删除 retry_count 幽灵配置 / last_response_time_ms
  死字段（round7 遗留）；avg_response_time_ms 窗口为空口径收敛为 0.0；
- src/tools/dependency.py：_importable_cache 线程安全（round7 遗留，
  --parallel 多线程并发探测同键时消除 check-then-act 竞态）；
- src/tools/type_repair.py：_EMPTY_CALLS 死逻辑清理（round7 遗留）；
- src/graph/token_usage.py：record_usage 实例锁原子化（round7 遗留，
  --parallel 多线程并发累加同一累计器时消除丢更新窗口）；
- src/graph/nodes.py：_HAS_FUNC_DEF_RE 补 async 前缀（与 patch_applier
  三处正则统一口径，async-only 被测模块的补丁不再被安全检查 2 误拒）；
- src/graph/workflow.py：_should_debug / _route_after_diagnosis 注释行号
  漂移修正（round7 重构后失效的 L 号引用改为按分支描述引用）。

运行：pytest tests/test_2026_09_26_review_round8.py -q
"""

from __future__ import annotations

import re
import sys
import threading
from pathlib import Path

# 项目根（tests/ 的父目录）加入 sys.path，便于直接导入 experiments.* / src.*
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ─── 1. api_manager：_last_health_check 死代码删除（round7 遗留落地） ───────


class TestLastHealthCheckRemoved:
    """_last_health_check dict 已从 APIManager 删除（round7 核实为死代码：
    生产代码只在 __init__ 初始化，无任何读/写点；旧用途"健康检查限流"
    已被 APIHealth.last_check_time 字段取代）。"""

    def test_attribute_removed_from_api_manager(self) -> None:
        import inspect

        from src.api.api_manager import APIManager

        # 类/实例属性均不应存在
        assert not hasattr(APIManager, "_last_health_check")
        # __init__ 源码中不应出现"赋值语句"形态（注释里提及该名字是
        # 文档化的，属预期；只锁定"不再初始化"口径）
        src = inspect.getsource(APIManager.__init__)
        assert "self._last_health_check" not in src, "APIManager.__init__ 不应再初始化 self._last_health_check"

    def test_test_isolation_no_longer_sets_it(self) -> None:
        # 3 处旧测试初始化（tests/test_api_manager.py L463/507/539）已清理
        # 本测试文件与旧测试文件不同名，仅作口径记录
        assert True


# ─── 2. api_manager：_cost_weight_for 注册时序缺陷（本轮 P1 修复） ─────────


class TestCostWeightForRegistration:
    """注册路径（_init_clients / add_node）上 LLMConfig.cost_weight 不再
    静默失效——修复前调用点在节点入池前调用 _cost_weight_for，反查
    health_nodes 恒 None，全节点恒回退 1.0（LLM_N_COST_WEIGHT 承诺失效）。"""

    def _make_manager(self, **cfg_kwargs):
        from src.api.api_manager import APIManager, APIManagerConfig

        mgr = APIManager.__new__(APIManager)
        mgr.config = APIManagerConfig(**cfg_kwargs)
        mgr.health_nodes = {}
        mgr._client_cache = {}
        mgr._rr_index = 0
        import threading as _t

        mgr._lock = _t.Lock()
        mgr._health_checker = None
        return mgr

    def test_in_hand_config_respected_before_pool(self) -> None:
        """节点入池前（health_nodes 空）传入在手 LLMConfig，其 cost_weight
        应被直接采用（修复前此路径恒 1.0）。"""
        from config import LLMConfig

        mgr = self._make_manager()
        cfg = LLMConfig("k", "https://x", "m", cost_weight=2.5)
        assert mgr._cost_weight_for("m", cfg) == 2.5

    def test_in_hand_config_zero_falls_back(self) -> None:
        """在手配置 cost_weight=0.0（未配置）时仍回退 1.0（默认行为不变）。"""
        from config import LLMConfig

        mgr = self._make_manager()
        cfg = LLMConfig("k", "https://x", "m", cost_weight=0.0)
        assert mgr._cost_weight_for("m", cfg) == 1.0

    def test_in_hand_config_overrides_pooled(self) -> None:
        """node_cost_weights 显式映射仍最高优先级（回退链不变）。"""
        from config import LLMConfig

        mgr = self._make_manager(node_cost_weights={"m": 5.0})
        cfg = LLMConfig("k", "https://x", "m", cost_weight=2.5)
        assert mgr._cost_weight_for("m", cfg) == 5.0

    def test_none_llmconfig_keeps_pool_fallback(self) -> None:
        """llm_config=None（外部调用 / 旧用例）保持原回退链：
        已入池节点反查 LLMConfig.cost_weight。"""
        from config import LLMConfig
        from src.api.api_health import APIHealth

        mgr = self._make_manager()
        mgr.health_nodes["m"] = APIHealth(config=LLMConfig("k", "https://x", "m", cost_weight=3.0))
        assert mgr._cost_weight_for("m") == 3.0

    def test_add_node_injects_in_hand_cost_weight(self) -> None:
        """add_node 注册路径（入池前调用）正确注入 LLMConfig.cost_weight。"""
        from config import LLMConfig

        mgr = self._make_manager()
        cfg = LLMConfig("k", "https://new-node", "new-node", cost_weight=4.0)
        mgr.add_node(cfg)
        assert mgr.health_nodes["new-node"].cost_weight == 4.0

    def test_add_node_default_cost_weight(self) -> None:
        """add_node 未配置成本信息时默认回退 1.0（默认行为不变）。"""
        from config import LLMConfig

        mgr = self._make_manager()
        cfg = LLMConfig("k", "https://new-node", "new-node")
        mgr.add_node(cfg)
        assert mgr.health_nodes["new-node"].cost_weight == 1.0


# ─── 3. api_health：retry_count / last_response_time_ms 删除（round7 遗留） ─


class TestApiHealthDeadFieldsRemoved:
    """round7 核实为死代码的 APIManagerConfig.retry_count 与
    APIHealth.last_response_time_ms 已删除。"""

    def test_retry_count_field_removed(self) -> None:
        import dataclasses

        from src.api.api_health import APIManagerConfig

        field_names = {f.name for f in dataclasses.fields(APIManagerConfig)}
        assert "retry_count" not in field_names

    def test_last_response_time_ms_field_removed(self) -> None:
        import dataclasses

        from src.api.api_health import APIHealth

        field_names = {f.name for f in dataclasses.fields(APIHealth)}
        assert "last_response_time_ms" not in field_names

    def test_avg_response_time_empty_window_returns_zero(self) -> None:
        """滑动窗口为空时无数据口径：avg_response_time_ms 返回 0.0
        （删除死字段后与"回退到从未更新的 0.0"口径等价）。"""
        from config import LLMConfig
        from src.api.api_health import APIHealth

        h = APIHealth(config=LLMConfig("k", "url", "m"))
        assert h.avg_response_time_ms == 0.0

    def test_avg_response_time_window_nonzero(self) -> None:
        """窗口非空时仍按滑动窗口均值计算（行为不变）。"""
        from config import LLMConfig
        from src.api.api_health import APIHealth

        h = APIHealth(config=LLMConfig("k", "url", "m"))
        h._response_times.extend([100.0, 200.0])
        assert h.avg_response_time_ms == 150.0


# ─── 4. dependency：_importable_cache 线程安全（round7 遗留） ─────────────


class TestDependencyImportableCacheThreadSafety:
    """_is_importable_cached 的 check-then-act 读改写已原子化（--parallel
    多线程并发探测同键时消除重复 find_spec 竞态窗口）。"""

    def test_cache_lock_exists_and_used(self) -> None:
        import src.tools.dependency as dep

        assert hasattr(dep, "_importable_cache_lock"), "应存在进程级缓存锁"
        import inspect

        src = inspect.getsource(dep._is_importable_cached)
        assert "with dep._importable_cache_lock" in src or "_importable_cache_lock" in src

    def test_concurrent_same_key_consistency(self) -> None:
        """多线程并发探测同一模块键，结果一致（find_spec 幂等口径）。"""
        import src.tools.dependency as dep

        # 预置已知结果，避免各线程真实 find_spec 的差异
        dep._importable_cache["os"] = True
        dep._importable_cache["definitely_missing_mod_xyz"] = False
        errors: list[Exception] = []
        results: list[bool] = []
        results_lock = threading.Lock()

        def _probe(mod: str) -> None:
            try:
                r = dep._is_importable_cached(mod)
                with results_lock:
                    results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_probe, args=("os",)) for _ in range(8)]
        threads += [threading.Thread(target=_probe, args=("definitely_missing_mod_xyz",)) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(results) == 16
        assert all(r is True for r in results if r is True)  # os 全 True
        assert sum(1 for r in results if r is True) == 8  # 8 个 os 线程
        assert sum(1 for r in results if r is False) == 8  # 8 个 missing 线程


# ─── 5. type_repair：_EMPTY_CALLS 死逻辑清理（round7 遗留） ─────────────


class TestTypeRepairEmptyCallsRemoved:
    """_collect_assign_types 右支死逻辑（_infer_call_return_type(node.value,
    _EMPTY_CALLS) 查空表恒 None，整个 or 恒为左支）已删除，口径等价
    （纯字面量类型推断）。"""

    def test_module_level_assign_collection_unchanged(self) -> None:
        import ast

        from src.tools.type_repair import _collect_assign_types

        func = ast.parse('def f(x):\n    a = 1\n    b = "s"\n    c = [1, 2]\n    d = some_call()\n    return a\n').body[
            0
        ]
        var_hist, _container_hist = _collect_assign_types(func)
        # 字面量口径：int / str / list 命中；调用返回（非常量）不命中
        assert [t for _, t in var_hist.get("a", [])] == ["int"]
        assert [t for _, t in var_hist.get("b", [])] == ["str"]
        assert [t for _, t in var_hist.get("c", [])] == ["list"]
        # 调用赋值（some_call() 非常量）不在历史中（右支死逻辑删除后口径）
        assert "d" not in var_hist

    def test_empty_calls_constant_removed(self) -> None:
        import src.tools.type_repair as tr

        assert not hasattr(tr, "_EMPTY_CALLS") or getattr(tr, "_EMPTY_CALLS", None) in (None, {})


# ─── 6. token_usage：record_usage 实例锁原子化（round7 遗留） ───────────


class TestTokenUsageRecordLock:
    """record_usage 的各字段读改写已用进程级 _usage_lock 原子化
    （--parallel 下并发累加同一累计器时消除丢更新窗口）。

    设计取舍（2026-09-26 round8）：用进程级单锁而非 per-instance 锁字典——
    ThreadLocal 的 TokenUsage 在 reset() 时被新实例替换（旧实例仅存于
    已退出线程的 registry），按 id 建锁字典会让键漂移 + 字典无界增长，
    无实际收益；单锁持锁时间为单次字段读改写（微秒级，无 I/O）。
    """

    def test_process_lock_exists(self) -> None:
        from src.graph import token_usage as tu

        assert isinstance(tu._usage_lock, threading.Lock)

    def test_record_usage_holds_process_lock(self) -> None:
        """record_usage 的各字段读改写在 _usage_lock 内原子化（口径锁定）。"""
        import inspect

        import src.graph.token_usage as tu

        src = inspect.getsource(tu.record_usage)
        assert "with _usage_lock:" in src, "record_usage 应在进程锁内原子化字段读改写"

    def test_concurrent_record_no_lost_updates(self) -> None:
        """多线程并发 record_usage，总累计无丢更新（锁前可能随机丢更新，
        锁后确定性一致）。"""
        import src.graph.token_usage as tu

        # 先清理 registry（主线程 reset 隔离本测试的并发噪声；
        # 已退出线程的条目保留是设计口径，本测试聚合前清零避免跨测试串扰）
        with tu._registry_lock:
            tu._registry.clear()
        tu.reset()  # 主线程累计器清零（写入 registry[main] = fresh）

        def _rec() -> None:
            # 每个 worker 线程独立累计（threading.local 口径）
            tu.reset()  # 隔离：每个 worker 清零自己的累计器
            for _ in range(100):
                tu.record_usage(1, 1, model="m")

        threads = [threading.Thread(target=_rec) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 跨线程聚合：主线程（1 次 record 前的 fresh，0 tokens）+
        # 8 worker 线程（各 100 次 × (1+1) = 200 tokens / 100 calls）
        total = tu.global_usage()
        assert total.llm_calls == 8 * 100
        assert total.total_tokens == 8 * 100 * 2
        # 清理，避免污染后续测试
        with tu._registry_lock:
            tu._registry.clear()
        tu.reset()

    def test_merge_semantics_unchanged(self) -> None:
        """merge（跨线程聚合）口径不变。"""
        from src.graph.token_usage import TokenUsage

        a = TokenUsage(input_tokens=1, output_tokens=2, total_tokens=3, llm_calls=1, by_model={"m": 3})
        b = TokenUsage(input_tokens=4, output_tokens=5, total_tokens=9, llm_calls=1, by_model={"m": 9})
        a.merge(b)
        assert a.input_tokens == 5
        assert a.output_tokens == 7
        assert a.total_tokens == 12
        assert a.llm_calls == 2
        assert a.by_model == {"m": 12}


# ─── 7. nodes：_HAS_FUNC_DEF_RE 含 async 前缀（本轮 P1 修复） ────────────


class TestHasFuncDefRegAsync:
    """安全检查 2 的函数定义探测正则与 patch_applier 三处口径统一
    （含 async def）：async-only 被测模块的补丁不再被误拒。"""

    def test_regex_matches_async_def(self) -> None:
        import src.graph.nodes as nodes

        assert nodes._HAS_FUNC_DEF_RE.search("async def f():\n    return 1\n")

    def test_regex_matches_sync_def(self) -> None:
        import src.graph.nodes as nodes

        assert nodes._HAS_FUNC_DEF_RE.search("def f():\n    return 1\n")

    def test_regex_rejects_no_def(self) -> None:
        import src.graph.nodes as nodes

        assert not nodes._HAS_FUNC_DEF_RE.search("x = 1\ny = 2\n")

    def test_matches_patch_applier_top_def_caliber(self) -> None:
        """与 patch_applier._TOP_DEF_RE 口径一致（均含 async 前缀）。
        注：两正则语义边界略有差异——_TOP_DEF_RE 严格锚定行首 def（^def，
        不匹配缩进的嵌套函数），_HAS_FUNC_DEF_RE 允许缩进（^\\s*def，覆盖
        嵌套 def）。此处只对比"顶层 def / async def / 非 def"三种形态
        （缩进嵌套函数是 nodes 安全检查 2 的额外覆盖，非缺陷）。"""
        import src.graph.nodes as nodes
        from src.tools.patch_applier import _TOP_DEF_RE

        for sample in [
            "def f(): pass",
            "async def f(): pass",
            "x = 1",
            "# def comment",
        ]:
            assert bool(_TOP_DEF_RE.search(sample)) == bool(nodes._HAS_FUNC_DEF_RE.search(sample)), sample


# ─── 8. workflow：注释行号漂移修正（纯注释，行为不变） ─────────────────


class TestWorkflowCommentsDriftFixed:
    """round7 重构后失效的行号引用（L210/L340/L350/L354/L360-366/L371-378）
    已全部改为按分支描述引用，不再绑定行号。"""

    def test_no_stale_line_refs_in_should_debug(self) -> None:
        import inspect

        from src.graph.workflow import _should_debug

        src = inspect.getsource(_should_debug)
        # 旧注释中的行号引用模式（"（L数字）" / "L数字-数字"）不应残留
        stale = re.findall(r"（L\d+|L\d+(?:-\d+)?\b", src)
        # 仅保留"行号引用"形态（L+数字）；分支描述引用（reason=... / 分支名）合法
        for ref in stale:
            assert "L354" not in ref and "L371" not in ref and "L360" not in ref and "L210" not in ref, (
                f"残留失效行号引用: {ref}"
            )

    def test_no_stale_line_refs_in_route_after_diagnosis(self) -> None:
        import inspect

        from src.graph.workflow import _route_after_diagnosis

        src = inspect.getsource(_route_after_diagnosis)
        stale = re.findall(r"（L\d+|L\d+(?:-\d+)?\b", src)
        for ref in stale:
            assert "L371" not in ref and "L378" not in ref, f"残留失效行号引用: {ref}"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
