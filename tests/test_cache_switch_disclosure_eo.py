"""EO 轮：缓存开关的显式关闭拼写必须同时兑现于工件自述与 X1 命名空间。

缺陷族（EN 收口后的下一个"承诺/实现分裂点"，落点是**缓存开关的治理面**）：
`AITESTER_LLM_CACHE` 与 `AITESTER_CACHE_ISOLATE_MODEL` 是 opt-out 型开关
（默认开，显式 `false` / `0` / `off` 关闭），运行时读的是
`src/utils/env_utils.py` 的 :func:`env_flag_opt_out`
（`src/agents/llm_client.py::_llm_cache_enabled` / `src/agents/base_agent.py`），
但 `experiments/run_benchmark.py` 有三处仍手抄 ``os.environ.get(NAME, "1") != "0"``：

1. X1 命名空间自设门（行 ~4311）：缓存已关时仍判"开"，自动写入
   ``AITESTER_CACHE_NAMESPACE=seed<N>`` 并打印"缓存命名空间"日志——
   命名空间隔离是为缓存服务的，缓存关闭时这条自设与其日志都是虚假事实；
2. ``provenance.cache_enabled``（行 ~4846）：工件自述缓存开启；
3. ``provenance.cache_isolate_model``（行 ~4847）：工件自述跨模型隔离开启。

根因调查（零 LLM 离线批次，每场景独立进程，10 个场景；见
docs/MEASUREMENT_INTEGRITY.md 第 108 节）：``false`` / ``off`` / ``FALSE`` /
`` Off `` 四种显式关闭拼写下运行时均判关，工件与命名空间却按"开"处理——
`cache_enabled` 4 个场景、`cache_isolate_model` 3 个场景、X1 命名空间
3 个场景分裂；``0`` / 未设置 / 默认开三组对照一致。最尖锐的一种是
**同一份工件自相矛盾**：``env_snapshot.AITESTER_LLM_CACHE = "false"``，
而 ``cache_enabled = true`` 且 ``cache_namespace = "seed42"``。

修法口径：三处改用与运行时同一解析器 :func:`env_flag_opt_out`——只有
``false`` / ``0`` / ``off``（大小写与空白容忍）算关。缓存开关的运行时语义、
批次执行逻辑、历史工件一字节不动。
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from typing import Any, ClassVar

import pytest

import experiments.run_benchmark as rb
from src.utils.env_utils import env_flag_opt_out

_CACHE_KEYS = (
    "AITESTER_LLM_CACHE",
    "AITESTER_CACHE_ISOLATE_MODEL",
    "AITESTER_CACHE_NAMESPACE",
)

#: 运行时 ``env_flag_opt_out`` 认定的关闭拼写（大小写与空白另测）
_OFF_SPELLINGS = ("false", "off", " FALSE ", "Off")


class _OfflineAPI:
    """`src.api.api_manager` 替身：任何调用直接抛错（零网络，批次只留 error 行）。"""

    instances: ClassVar[list[Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        type(self).instances.append(self)

    def call(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("offline-stub")


class _StubDataset:
    """空任务批次替身：`size` 非 0 以避开"空数据集 ⇒ 降级内置 examples"分支。"""

    size = 1
    tasks: ClassVar[list[Any]] = []
    strict_skipped_task_ids: ClassVar[list[str]] = []


@pytest.fixture()
def offline_batch(monkeypatch: pytest.MonkeyPatch):
    """零 LLM、零网络的 run_benchmark 环境。

    ``run_benchmark`` 的 X1 门会直接写 ``os.environ["AITESTER_CACHE_NAMESPACE"]``
    （不经 monkeypatch 记录），故 fixture 自行快照/恢复本族三个键，避免
    命名空间泄漏到后续用例。
    """

    def _run(tmp_path: Path, **kwargs: Any) -> dict[str, Any]:
        saved = {key: os.environ.get(key) for key in _CACHE_KEYS}
        fake_module = types.ModuleType("src.api.api_manager")
        fake_module.APIManager = _OfflineAPI  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "src.api.api_manager", fake_module)
        monkeypatch.setattr(rb, "load_dataset", lambda *a, **k: _StubDataset())
        try:
            summary = rb.run_benchmark(
                dataset_name="swe_bench",
                baselines=["plain_llm"],
                output_dir=str(tmp_path),
                parallel=1,
                seed=42,
                **kwargs,
            )
            # 批次返回前捕获 X1 门的实际写入值（finally 会恢复进程环境）
            _run.last_namespace = os.environ.get("AITESTER_CACHE_NAMESPACE")
            return summary
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    _run.last_namespace = None
    return _run


def _provenance(summary: dict[str, Any]) -> dict[str, Any]:
    return summary["provenance"]


def _runtime_cache_enabled() -> bool:
    from src.agents import llm_client

    llm_client.clear_llm_cache_option_memory()
    return llm_client._llm_cache_enabled()


def _clear_cache_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _CACHE_KEYS:
        monkeypatch.delenv(key, raising=False)


# ═══ 1. provenance.cache_enabled ══════════════════════════════════════════


class TestCacheEnabledDisclosure:
    """``AITESTER_LLM_CACHE`` 的显式关闭拼写必须让工件自述为关。"""

    @pytest.mark.parametrize("raw", _OFF_SPELLINGS)
    def test_disable_spellings_disclosed_as_off(self, offline_batch, tmp_path, monkeypatch, raw):
        """``false`` / ``off`` / 大小写与空白：运行时关，工件必须同口径。"""
        monkeypatch.setenv("AITESTER_LLM_CACHE", raw)
        summary = offline_batch(tmp_path)
        provenance = _provenance(summary)
        assert provenance["cache_enabled"] is False
        assert provenance["cache_enabled"] == _runtime_cache_enabled()

    def test_zero_spelling_still_off(self, offline_batch, tmp_path, monkeypatch):
        """历史唯一可用的 ``0`` 保持不变（护栏）。"""
        monkeypatch.setenv("AITESTER_LLM_CACHE", "0")
        summary = offline_batch(tmp_path)
        assert _provenance(summary)["cache_enabled"] is False

    def test_unset_defaults_on(self, offline_batch, tmp_path, monkeypatch):
        """未设置 → 默认开（护栏：不得把"未设置"误判成关）。"""
        _clear_cache_env(monkeypatch)
        summary = offline_batch(tmp_path)
        assert _provenance(summary)["cache_enabled"] is True

    def test_snapshot_and_boolean_do_not_contradict(self, offline_batch, tmp_path, monkeypatch):
        """同一份工件的原始快照与布尔判定不得互相打脸。"""
        monkeypatch.setenv("AITESTER_LLM_CACHE", "off")
        summary = offline_batch(tmp_path)
        provenance = _provenance(summary)
        assert provenance["env_snapshot"]["AITESTER_LLM_CACHE"] == "off"
        assert provenance["cache_enabled"] is False


# ═══ 2. provenance.cache_isolate_model ════════════════════════════════════


class TestIsolateModelDisclosure:
    """``AITESTER_CACHE_ISOLATE_MODEL`` 同属 opt-out 开关，自述须同口径。"""

    @pytest.mark.parametrize("raw", _OFF_SPELLINGS)
    def test_disable_spellings_disclosed_as_off(self, offline_batch, tmp_path, monkeypatch, raw):
        """运行时 :func:`env_flag_opt_out` 判关，工件自述必须一致。"""
        monkeypatch.setenv("AITESTER_CACHE_ISOLATE_MODEL", raw)
        summary = offline_batch(tmp_path)
        provenance = _provenance(summary)
        expected = env_flag_opt_out("AITESTER_CACHE_ISOLATE_MODEL")
        assert expected is False
        assert provenance["cache_isolate_model"] is False
        assert provenance["cache_isolate_model"] == expected

    def test_zero_spelling_still_off(self, offline_batch, tmp_path, monkeypatch):
        """``0`` 保持不变（护栏）。"""
        monkeypatch.setenv("AITESTER_CACHE_ISOLATE_MODEL", "0")
        summary = offline_batch(tmp_path)
        assert _provenance(summary)["cache_isolate_model"] is False

    def test_unset_defaults_on(self, offline_batch, tmp_path, monkeypatch):
        """未设置 → 默认开（护栏）。"""
        _clear_cache_env(monkeypatch)
        summary = offline_batch(tmp_path)
        assert _provenance(summary)["cache_isolate_model"] is True


# ═══ 3. X1 缓存命名空间自设门 ══════════════════════════════════════════════


class TestX1NamespaceGate:
    """缓存关闭时不得自设命名空间，也不得在工件里留下虚假隔离证据。"""

    @pytest.mark.parametrize("raw", ("false", "off", " FALSE "))
    def test_no_namespace_when_cache_disabled(self, offline_batch, tmp_path, monkeypatch, raw):
        """缓存已关 → 无缓存可串，命名空间自设与工件字段都应为空。"""
        _clear_cache_env(monkeypatch)
        monkeypatch.setenv("AITESTER_LLM_CACHE", raw)
        summary = offline_batch(tmp_path)
        provenance = _provenance(summary)
        assert offline_batch.last_namespace is None
        assert provenance["cache_namespace"] is None

    def test_namespace_autoset_when_cache_enabled(self, offline_batch, tmp_path, monkeypatch):
        """X1 原承诺保持：缓存开启且未显式设命名空间 → 自动 seed<N>（护栏）。"""
        _clear_cache_env(monkeypatch)
        summary = offline_batch(tmp_path)
        provenance = _provenance(summary)
        assert offline_batch.last_namespace == "seed42"
        assert provenance["cache_namespace"] == "seed42"

    def test_zero_disables_without_namespace(self, offline_batch, tmp_path, monkeypatch):
        """``0`` 关闭时同样不自设（护栏：历史唯一拼写不得回归）。"""
        _clear_cache_env(monkeypatch)
        monkeypatch.setenv("AITESTER_LLM_CACHE", "0")
        summary = offline_batch(tmp_path)
        assert offline_batch.last_namespace is None
        assert _provenance(summary)["cache_namespace"] is None

    def test_explicit_namespace_preserved_when_cache_disabled(self, offline_batch, tmp_path, monkeypatch):
        """用户显式命名空间不得被改写（护栏：只停止自设，不清理显式值）。"""
        _clear_cache_env(monkeypatch)
        monkeypatch.setenv("AITESTER_LLM_CACHE", "false")
        monkeypatch.setenv("AITESTER_CACHE_NAMESPACE", "outer")
        summary = offline_batch(tmp_path)
        assert offline_batch.last_namespace == "outer"
        assert _provenance(summary)["cache_namespace"] == "outer"
