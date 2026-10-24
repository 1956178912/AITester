"""修复覆盖率缺口审计（2026-10-19，零 LLM）——审计发现的未覆盖分支回归锁。

## 审计方法

以 `ff15a2f`（V 轮修复起点）为基线，取 `git diff ff15a2f HEAD -- src/` 的
新增行，与全量测试的 `coverage.xml` 行集合求交，找出**修复新增但从未被任何
测试执行过**的代码行（552 行新增可执行行中 37 行未执行，6.70%）。逐行人工
分类后，把其中属于 P1 修复**核心契约**的三组缺口补成回归锁。

## 为什么这些缺口危险

前两轮第三方评审（`73481bb` → A07/A09/A10）暴露的复发模式是"修复覆盖主路径、
漏掉分支路径"：接口存在、主流程有测试，但某个分支一旦回退，**全套 9000+
测试无一告警**。本文件的三个用例针对的正是这类分支，且每个都经过变异验证
（抹掉目标分支后用例必红）。

## 纪律

零 LLM、零网络、零真实等待；凭证类分支一律用 fake 客户端或纯函数直测。
"""

from __future__ import annotations

import hashlib
import os
from types import SimpleNamespace
from typing import Any

import pytest

from src.agents import base_agent
from src.agents.base_agent import BaseAgent
from src.api.api_manager import APIManager, LLMConfig
from src.budget.cost_budget import BudgetExceededError


def _agent() -> BaseAgent:
    return BaseAgent(system_prompt="你是单元测试用智能体。")


# ═══════════════════════════════════════════════════════════════════════════
#  缺口 1：A11 跨模型故障转移前的预算复查（base_agent.py:1022-1023）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestA11BudgetRecheckBeforeFailover:
    """A11（P1）有两层预算复查，此前只有第一层有测试。

    - 第一层：`pre_retry_check=_raise_if_budget_exceeded` 传入重试器，
      只在**同模型重试前**触发（需 `max_retries > 0`）——既有
      `test_budget_rechecked_before_retry` 覆盖此层；
    - 第二层：`for model` 故障转移循环顶部的 `if is_budget_exceeded()`，
      **跨模型切换前**触发——本类覆盖，此前零 hits。

    变异验证（2026-10-19）：把第二层条件改为恒假后，
    `test_budget_rechecked_before_retry` 仍然通过（它走的是第一层），
    仅本类用例变红——说明第一层的测试无法保护第二层。
    """

    def test_budget_rechecked_before_cross_model_failover(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """第一个模型失败后预算耗尽 → 抛 BudgetExceededError，不得切换下一个模型。"""
        configs = [
            ("key-1", "https://api.example.com/v1", "model-1"),
            ("key-2", "https://api.example.com/v1", "model-2"),
        ]
        invoked_models: list[str] = []

        def _make_client(model_name: str) -> SimpleNamespace:
            def _invoke(messages: Any, **kwargs: Any) -> Any:
                invoked_models.append(model_name)
                raise RuntimeError("网络抖动（非预算错误）")

            return SimpleNamespace(invoke=_invoke)

        monkeypatch.setattr(base_agent, "_get_all_api_configs", lambda: list(configs))
        monkeypatch.setattr(
            base_agent,
            "_get_or_create_chat_client",
            lambda model_name, *a, **k: _make_client(model_name),
        )
        # 第一个模型被尝试过之后即视为预算超限（模拟其 usage 已记账并耗尽预算）
        monkeypatch.setattr("src.budget.cost_budget.is_budget_exceeded", lambda: len(invoked_models) >= 1)
        monkeypatch.setattr(
            "src.budget.cost_budget.get_budget_stats",
            lambda: {"consumed_tokens": 5000, "token_limit": 1000, "unit": "tokens"},
        )

        agent = _agent()
        with pytest.raises(BudgetExceededError):
            agent._call_llm("预算问题", max_retries=0)

        assert invoked_models == ["model-1"], "预算超限后不得切换第二个模型"


# ═══════════════════════════════════════════════════════════════════════════
#  缺口 2：A15 同端点不同 key 的实例 ID 后缀（api_manager.py:239-240）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestA15EndpointIdSuffix:
    """A15（P1）的端点实例 ID 只由 base_url 派生（避免凭证进节点键）。

    因此"同 model、同 base_url、不同 api_key"（配额轮询的常见配置）会算出
    **相同**实例 ID，第二个实例必须退化为 `<id>#2`。既有 A15 测试全部使用
    不同 base_url（digest 天然不同），该后缀分支从未被执行。

    变异验证（2026-10-19）：把 `while key in self.health_nodes` 改为恒假后，
    两个实例塌缩为一个（`len(keys) == 1`），仅本类用例变红。
    """

    @staticmethod
    def _empty_mgr() -> APIManager:
        from unittest.mock import patch

        with patch("src.api.api_manager.LLM_CONFIGS", []):
            return APIManager(enable_health_checker=False)

    def test_same_model_same_endpoint_different_key_gets_suffix(self) -> None:
        mgr = self._empty_mgr()
        mgr.add_node(LLMConfig("key-a", "https://same.example.com/v1", "shared-model"))
        mgr.add_node(LLMConfig("key-b", "https://same.example.com/v1", "shared-model"))

        keys = list(mgr.health_nodes)
        assert len(keys) == 2, "同端点不同 key 的两个实例都必须保留"
        assert any(key.endswith("#2") for key in keys), "实例 ID 冲突必须以 #2 后缀去重"
        assert len(mgr.get_all_nodes()) == 2


# ═══════════════════════════════════════════════════════════════════════════
#  缺口 3：A09 旧格式缓存键的键材料逐字节复刻（base_agent.py:361, 370）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestA09LegacyCacheKeyMaterial:
    """A09（P1）保留"旧格式只读回退"，前提是能用旧公式重算出旧文件名。

    键材料（prompt + system + temperature + jm1 + m<model> + ns<namespace>）
    一旦漏项、多项或顺序变化，升级后**所有历史缓存都命中不到**——表现为
    重复计费，而功能测试全绿（新键路径工作正常）。故此处锁到 md5 前 16 位。

    变异验证（2026-10-19）：抹掉 `jm1` 与 `ns` 两个材料分支后，
    本类两个用例同时变红。
    """

    @staticmethod
    def _expected_name(key_material: str) -> str:
        return hashlib.md5(key_material.encode("utf-8")).hexdigest()[:16] + ".json"

    @pytest.fixture(autouse=True)
    def _clean_cache_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """清空会影响旧键材料的开关，避免宿主环境串味。"""
        monkeypatch.delenv("AITESTER_CACHE_NAMESPACE", raising=False)
        # env_flag_opt_out 语义下"设置即关闭"——显式设 1 表示不做模型隔离
        monkeypatch.setenv("AITESTER_CACHE_ISOLATE_MODEL", "1")

    def test_material_is_byte_exact(self) -> None:
        path = base_agent._legacy_cache_file("问题", "系统", None, False)
        assert os.path.basename(path) == self._expected_name("问题\x00系统")

        # temperature 显式参与（None 时不追加，0.0 时仍追加）
        path_t = base_agent._legacy_cache_file("问题", "系统", 0.2, False)
        assert os.path.basename(path_t) == self._expected_name("问题\x00系统\x00t0.2")

        # json_mode=True 追加 jm1
        path_j = base_agent._legacy_cache_file("问题", "系统", None, True)
        assert os.path.basename(path_j) == self._expected_name("问题\x00系统\x00jm1")

    def test_namespace_participates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        baseline = base_agent._legacy_cache_file("问题", "系统", None, False)

        monkeypatch.setenv("AITESTER_CACHE_NAMESPACE", "team-x")
        with_ns = base_agent._legacy_cache_file("问题", "系统", None, False)
        assert with_ns != baseline
        assert os.path.basename(with_ns) == self._expected_name("问题\x00系统\x00nsteam-x")

        # 空白 namespace 视为未设置（strip 后为空）
        monkeypatch.setenv("AITESTER_CACHE_NAMESPACE", "   ")
        assert base_agent._legacy_cache_file("问题", "系统", None, False) == baseline
