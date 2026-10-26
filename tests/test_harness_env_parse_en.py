"""EN 轮：`provenance.harness` 自述的开关必须与运行时生效值同口径。

缺陷族（EM 收口后的下一个"承诺/实现分裂点"，落点是**工件自述的读法**）：
R56 的 harness 块承诺读者可据此复核"这次跑批到底开了什么"（执行隔离档位 /
上下文策略 / 重试停止规则），但该块对 8 个布尔开关用手抄的
``os.environ.get(NAME, default).lower() == "true"`` 解析，而运行时读的是
``src/utils/env_utils.py`` 的 :func:`env_flag` / :func:`env_flag_opt_out`：

- ``env_flag`` 接受 ``true`` / ``1`` / ``on``（大小写与空白容忍）；
- ``env_flag_opt_out``（EG 轮起 ``EXECUTOR_USE_VENV`` 的口径）只有
  ``false`` / ``0`` / ``off`` 算关，其余一律开。

根因调查（零 LLM 离线批次，12 个场景，见 docs/MEASUREMENT_INTEGRITY.md 第 107 节）：

1. ``EXECUTOR_USE_VENV=yes`` —— 运行时 ``config.EXECUTOR_USE_VENV=True``
   （venv 沙箱开着），工件自述 ``use_venv=false``；
2. ``KERNEL_SANDBOX_ENABLE=on`` / ``EXECUTOR_AUTO_INSTALL_DEPS=1`` /
   ``CONTEXT_TIER_DOWNGRADE_ENABLE=1`` / ``BRANCH_COVERAGE_INJECT_ENABLE=1`` /
   ``COST_BUDGET_ENABLE=1`` —— 运行时各访问器全部 True，工件自述全 false；
3. ``ENABLE_RAG=1`` —— ``config.ENABLE_RAG=True`` 且同工件顶层的
   ``summary["enable_rag"]=true``，harness 块却自述 ``rag_enabled=false``
   （**同一份工件内部自相矛盾**）；
4. ``--enable-rag``（CLI）—— :func:`experiments.run_benchmark._apply_rag_setting`
   直接改写 ``src.graph.workflow.ENABLE_RAG``，不写环境变量，harness 块重读
   环境变量仍是 false，而顶层 ``summary["enable_rag"]=true``；
5. ``TRUNCATION_FIRST_ENABLE`` —— 该键只出现在 harness 块，全仓零消费点
   （``src/`` / ``config.py`` / 文档均无读取方），是自述面虚构的开关。

修法口径（与 EM 同族：自述面回到单一事实源）：

- 布尔开关经 ``env_flag`` / ``env_flag_opt_out`` 解析（与运行时同一函数）；
- ``rag_enabled`` 不再重读环境变量，直接披露 ``_apply_rag_setting`` 的**生效值**
  （与顶层 ``enable_rag`` 同源，CLI/环境两条路径都对得上）；
- 删除 ``truncation_first`` 幻影键——自述不宣称不存在的开关。

判定方向一律不动：开关本身的运行时语义、批次执行逻辑、历史工件一字节不动。
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any, ClassVar

import pytest

import experiments.run_benchmark as rb
from src.agents.kernel_sandbox import kernel_sandbox_enabled
from src.budget.cost_budget import _budget_enabled
from src.graph import flags
from src.tools.branch_coverage_inject import branch_coverage_inject_enabled

_CONTEXT_KEYS = (
    "rag_enabled",
    "context_tier_downgrade",
    "branch_coverage_inject",
)
_ISOLATION_KEYS = ("use_venv", "use_docker", "kernel_sandbox", "auto_install_deps")


class _OfflineAPI:
    """`src.api.api_manager` 替身：任何调用直接抛错（零网络，批次只留 error 行）。"""

    instances: ClassVar[list[Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        type(self).instances.append(self)

    def call(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("offline-stub")


class _StubDataset:
    """空任务批次替身：``size`` 非 0 以避开"空数据集 ⇒ 降级内置 examples"分支。"""

    size = 1
    tasks: ClassVar[list[Any]] = []
    strict_skipped_task_ids: ClassVar[list[str]] = []


@pytest.fixture()
def offline_batch(monkeypatch: pytest.MonkeyPatch):
    """零 LLM、零网络的 run_benchmark 环境（同 EM/BO 两轮测试口径）。"""

    def _run(tmp_path: Path, **kwargs: Any) -> dict[str, Any]:
        fake_module = types.ModuleType("src.api.api_manager")
        fake_module.APIManager = _OfflineAPI  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "src.api.api_manager", fake_module)
        monkeypatch.setenv("AITESTER_LLM_CACHE", "0")
        monkeypatch.setattr(rb, "load_dataset", lambda *a, **k: _StubDataset())
        return rb.run_benchmark(
            dataset_name="swe_bench",
            baselines=["plain_llm"],
            output_dir=str(tmp_path),
            parallel=1,
            **kwargs,
        )

    return _run


def _harness(summary: dict[str, Any]) -> dict[str, Any]:
    return summary["provenance"]["harness"]


# ═══ 1. opt-out 口径：EXECUTOR_USE_VENV ════════════════════════════════════


class TestVenvOptOutDisclosure:
    """``EXECUTOR_USE_VENV`` 是 opt-out 开关（EG 轮迁移），自述必须同口径。"""

    def test_yes_disclosed_as_true(self, offline_batch, tmp_path, monkeypatch):
        """``yes`` 不在关闭集 → 运行时开；手抄 ``== "true"`` 会自述 false。"""
        monkeypatch.setenv("EXECUTOR_USE_VENV", "yes")
        summary = offline_batch(tmp_path)
        assert _harness(summary)["execution_isolation"]["use_venv"] is True

    def test_off_disclosed_as_false(self, offline_batch, tmp_path, monkeypatch):
        """``off`` 在关闭集 → 运行时关（守护：修复不得把显式关闭读成开）。"""
        monkeypatch.setenv("EXECUTOR_USE_VENV", "off")
        summary = offline_batch(tmp_path)
        assert _harness(summary)["execution_isolation"]["use_venv"] is False

    def test_unset_defaults_to_true(self, offline_batch, tmp_path, monkeypatch):
        """未设置 → 默认开（R10 起 venv 沙箱默认档位）。"""
        monkeypatch.delenv("EXECUTOR_USE_VENV", raising=False)
        summary = offline_batch(tmp_path)
        assert _harness(summary)["execution_isolation"]["use_venv"] is True


# ═══ 2. env_flag 正集口径：真值字面量必须与运行时访问器一致 ════════════════


class TestEnvFlagDisclosure:
    """``1`` / ``on`` 是运行时真值；披露必须同值。"""

    @pytest.mark.parametrize(
        ("env_name", "group", "field", "runtime_reader"),
        [
            ("KERNEL_SANDBOX_ENABLE", "execution_isolation", "kernel_sandbox", kernel_sandbox_enabled),
            (
                "CONTEXT_TIER_DOWNGRADE_ENABLE",
                "context_strategy",
                "context_tier_downgrade",
                flags._context_tier_downgrade_enabled,
            ),
            (
                "BRANCH_COVERAGE_INJECT_ENABLE",
                "context_strategy",
                "branch_coverage_inject",
                branch_coverage_inject_enabled,
            ),
        ],
    )
    @pytest.mark.parametrize("raw", ["1", "on", " TRUE "])
    def test_truthy_literals_match_runtime_reader(
        self, offline_batch, tmp_path, monkeypatch, env_name, group, field, runtime_reader, raw
    ):
        monkeypatch.setenv(env_name, raw)
        summary = offline_batch(tmp_path)
        harness = _harness(summary)
        assert harness[group][field] is True
        assert harness[group][field] == runtime_reader()

    def test_auto_install_deps_1_disclosed_true(self, offline_batch, tmp_path, monkeypatch):
        monkeypatch.setenv("EXECUTOR_AUTO_INSTALL_DEPS", "1")
        summary = offline_batch(tmp_path)
        assert _harness(summary)["execution_isolation"]["auto_install_deps"] is True

    def test_cost_budget_1_disclosed_true(self, offline_batch, tmp_path, monkeypatch):
        monkeypatch.setenv("COST_BUDGET_ENABLE", "1")
        summary = offline_batch(tmp_path)
        assert _harness(summary)["retry_stop_rules"]["cost_budget_enabled"] is True
        assert _harness(summary)["retry_stop_rules"]["cost_budget_enabled"] == _budget_enabled()

    def test_docker_true_control_disclosed_true(self, offline_batch, tmp_path, monkeypatch):
        """控制组：``true`` 两种解析都认——修复不得改变这条既有披露。"""
        monkeypatch.setenv("EXECUTOR_USE_DOCKER", "true")
        summary = offline_batch(tmp_path)
        assert _harness(summary)["execution_isolation"]["use_docker"] is True


# ═══ 3. RAG：披露生效值，不重读环境变量 ════════════════════════════════════


class TestRagEffectiveDisclosure:
    """CLI 开关只改 workflow 模块全局；自述必须跟生效值走。"""

    def test_cli_enable_rag_disclosed_true(self, offline_batch, tmp_path, monkeypatch):
        """``--enable-rag`` 路径：顶层 enable_rag=true，harness 不得自述 false。"""
        monkeypatch.setenv("ENABLE_RAG", "false")
        summary = offline_batch(tmp_path, enable_rag=True)
        assert summary["enable_rag"] is True
        assert _harness(summary)["context_strategy"]["rag_enabled"] is True

    def test_workflow_effective_value_disclosed(self, offline_batch, tmp_path, monkeypatch):
        """有效值来自 ``src.graph.workflow.ENABLE_RAG``（_apply_rag_setting(None)）。"""
        import src.graph.workflow as wf

        monkeypatch.setattr(wf, "ENABLE_RAG", True)
        monkeypatch.delenv("ENABLE_RAG", raising=False)
        summary = offline_batch(tmp_path)
        assert summary["enable_rag"] is True
        assert _harness(summary)["context_strategy"]["rag_enabled"] is True

    def test_cli_disable_rag_disclosed_false(self, offline_batch, tmp_path, monkeypatch):
        """守护：显式 ``--no-rag`` 时自述 false（方向不被修反）。"""
        monkeypatch.setenv("ENABLE_RAG", "true")
        summary = offline_batch(tmp_path, enable_rag=False)
        assert summary["enable_rag"] is False
        assert _harness(summary)["context_strategy"]["rag_enabled"] is False
        # env 与生效值故意相反：披露必须站生效值一侧


# ═══ 4. 幻影键与类型/落盘面 ════════════════════════════════════════════════


class TestPhantomSwitchRemoved:
    """自述不得宣称运行时零消费者的开关。"""

    def test_truncation_first_not_disclosed(self, offline_batch, tmp_path, monkeypatch):
        """``TRUNCATION_FIRST_ENABLE`` 全仓零读取方 → 工件不应披露该档位。"""
        monkeypatch.setenv("TRUNCATION_FIRST_ENABLE", "true")
        summary = offline_batch(tmp_path)
        assert "truncation_first" not in _harness(summary)["context_strategy"]


class TestDisclosureShape:
    """披露值必须是严格 bool，且内存态与落盘态一致。"""

    def test_all_switch_values_are_strict_bools(self, offline_batch, tmp_path, monkeypatch):
        monkeypatch.setenv("EXECUTOR_USE_VENV", "yes")
        monkeypatch.setenv("KERNEL_SANDBOX_ENABLE", "on")
        summary = offline_batch(tmp_path)
        harness = _harness(summary)
        for key in _ISOLATION_KEYS:
            assert type(harness["execution_isolation"][key]) is bool
        for key in _CONTEXT_KEYS:
            assert type(harness["context_strategy"][key]) is bool
        assert type(harness["retry_stop_rules"]["cost_budget_enabled"]) is bool

    def test_on_disk_harness_matches_memory(self, offline_batch, tmp_path, monkeypatch):
        monkeypatch.setenv("EXECUTOR_USE_VENV", "yes")
        monkeypatch.setenv("COST_BUDGET_ENABLE", "1")
        summary = offline_batch(tmp_path, enable_rag=True)
        out = next(tmp_path.glob("benchmark_*.json"))
        on_disk = json.loads(out.read_text(encoding="utf-8"))["provenance"]["harness"]
        assert on_disk == _harness(summary)
