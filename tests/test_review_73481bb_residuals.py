"""2026-10-18 第三方复核报告（提交 73481bb）三项 P1 残留的最小反例回归。

评审报告结论：P0=0、P1=3，均为原问题未修复的子场景（报告 §G/§H/§P）：

- **A07** 模板敏感性入口仍"先跳过 None 再后写覆盖"，与规范的
  "最新记录先占位、再排除 None"契约分叉（报告 §G A07、§M3）；
- **A09** 语义缓存分区材料不含 `system_prompt`，不同角色可跨 system
  复用响应（报告 §G A09、§M2）；
- **A10** 线程指定端点恰为全局列表已有项时直接早退，分配未生效
  （报告 §G A10、§M1）。

本文件按报告给出的最小输入形状构造反例，修复前静态可判定失败、修复后
逐项通过；同时覆盖修复建议里的相邻形状（同 seed 重跑、多 system 调用级
回归、同 base_url 多模型、复杂度路由与显式分配的优先级）。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


# ─── A07：最新记录选择契约 ────────────────────────────────────────────────────


def _row(task_id: str, detection: float | None, pattern: str = "p1") -> dict[str, Any]:
    """构造行级结果（字段形状与 benchmark details 一致）。"""
    return {"task_id": task_id, "detection_rate": detection, "task_metadata": {"pattern_name": pattern}}


def test_a07_template_branch_matches_pair_by_task_contract() -> None:
    """报告 §M3 反例：最新 None 的 t1 必须整体排除，t2 取最新 1 → discordant 2:1。"""
    from experiments.statistical_analysis import _pair_by_task, template_cluster_sensitivity

    rows_a = [
        _row("t1", None),
        _row("t2", 1.0),
        _row("t3", 0.0, "p2"),
        _row("t4", 1.0, "p2"),
        # 旧批次（同 task_id 重复）：最新记录在前
        _row("t1", 0.0),
        _row("t2", 0.0),
    ]
    rows_b = [_row("t1", 1.0), _row("t2", 0.0), _row("t3", 1.0, "p2"), _row("t4", 0.0, "p2")]

    paired_a, paired_b, common = _pair_by_task(rows_a, rows_b, field="detection_rate")
    assert common == ["t2", "t3", "t4"], "最新 None 必须占位排除，不得由旧 0 顶替"
    assert paired_a == [1, 0, 1] and paired_b == [0, 1, 0]

    md = template_cluster_sensitivity(rows_a, rows_b, "A", "B")
    assert "discordant 2:1" in md, "模板分支必须与 _pair_by_task 同口径（修复前为 1:2）"


def test_a07_template_metadata_uses_latest_row() -> None:
    """模板归属取最新行的 pattern_name；旧行元数据不得覆盖（修复前 k=3）。"""
    from experiments.statistical_analysis import template_cluster_sensitivity

    rows_a = [
        _row("t1", 1.0, "new1"),
        _row("t2", 0.0, "new1"),
        _row("t3", 1.0, "new2"),
        _row("t4", 0.0, "new2"),
        _row("t1", 0.0, "old"),  # 旧批次：若被采用会把簇数抬到 3
    ]
    rows_b = [
        _row("t1", 0.0, "new1"),
        _row("t2", 1.0, "new1"),
        _row("t3", 0.0, "new2"),
        _row("t4", 1.0, "new2"),
    ]
    md = template_cluster_sensitivity(rows_a, rows_b, "A", "B")
    assert "k=2 模板簇" in md, f"模板元数据必须取最新行（修复前 k=3）：{md}"


def test_a07_shared_helper_marks_duplicates_and_excludes_none() -> None:
    """共享原语：首见占位、None 在去重后排除、缺 task_id 的行不参与配对。"""
    from experiments._row_pairing import latest_binary_by_task, latest_rows_by_task

    rows = [_row("t1", None, "new"), _row("t1", 1.0, "old"), _row("t2", 0.0), {"detection_rate": 1.0}]
    latest = latest_rows_by_task(rows)
    assert set(latest) == {"t1", "t2"}
    assert latest["t1"]["task_metadata"]["pattern_name"] == "new"

    binary, latest_rows = latest_binary_by_task(rows, field="detection_rate")
    assert binary == {"t2": 0}, "最新 t1 不可测 → 整体不可测（不回退旧 1.0）"
    assert latest_rows["t1"] is rows[0]


def test_a07_bayesian_and_template_agree_on_latest_none() -> None:
    """贝叶斯配对与模板分支共用同一原语：最新 None 两侧都不计入分母。"""
    from experiments.bayesian_paired import paired_contingency

    rows_a = [_row("t1", None), _row("t1", 1.0), _row("t2", 1.0)]
    rows_b = [_row("t1", 1.0), _row("t2", 1.0)]
    counts = paired_contingency(rows_a, rows_b, field="detection_rate")
    assert counts["n_common"] == 1, f"t1 最新不可测 → 分母只剩 t2：{counts}"
    assert counts["n11"] == 1


# ─── A09：语义分区必须含 system 身份 ──────────────────────────────────────────


def test_a09_identity_carries_system_digest() -> None:
    """身份版本升级到 v3：system 摘要进入材料，指纹随 system 分离。"""
    from src.agents import base_agent as ba
    from src.agents.llm_client import request_identity_fingerprint

    identity_a = ba._effective_request_identity(None, False, None, "system A")
    identity_b = ba._effective_request_identity(None, False, None, "system B")

    assert identity_a["v"] == 3
    assert identity_a["system"] and identity_a["system"] != identity_b["system"]
    assert request_identity_fingerprint(identity_a) != request_identity_fingerprint(identity_b)
    # 无 system 材料时显式为 None（不伪造空串摘要）
    assert ba._effective_request_identity(None, False)["system"] is None


def test_a09_cross_system_semantic_lookup_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    """报告 §M2 反例：同 user prompt、不同 system，语义索引不得跨分区命中。"""
    import src.utils.embedding_utils as embedding_utils
    from src.agents import base_agent as ba
    from src.agents import semantic_cache as sc
    from src.agents.llm_client import request_identity_fingerprint

    monkeypatch.setenv("SEMANTIC_CACHE_ENABLE", "true")
    monkeypatch.setattr(embedding_utils, "embed_text", lambda _text: [1.0, 0.0])
    monkeypatch.setattr(ba, "_get_all_api_configs", lambda: [("fake", "https://a.invalid/v1", "m")])
    monkeypatch.setattr(ba, "_openai_extra_body", lambda: {"thinking": {"type": "disabled"}})

    identity_a = ba._effective_request_identity(None, False, None, "system A")
    identity_b = ba._effective_request_identity(None, False, None, "system B")
    fp_a = request_identity_fingerprint(identity_a)
    fp_b = request_identity_fingerprint(identity_b)

    file_a = ba._exact_cache_file(identity_a, "same user prompt", "system A")
    file_b = ba._exact_cache_file(identity_b, "same user prompt", "system B")
    assert file_a != file_b, "精确缓存文件本就按 system 分离"

    index = sc.SemanticCacheIndex()
    index.upsert(file_a, "same user prompt", "response from A", identity_key=fp_a)
    with patch.object(sc, "get_semantic_index", return_value=index):
        assert sc.find_semantic_cache(file_b, "same user prompt", identity_key=fp_b) is None, (
            "A09：不同 system 必须未命中（修复前 system 不进指纹，相似度 1 直接命中 A）"
        )
        # 同 system 仍可命中——证明修复不是"全禁"语义缓存
        assert sc.find_semantic_cache(file_a, "same user prompt", identity_key=fp_a) == (
            file_a,
            "response from A",
        )


def test_a09_two_agents_different_system_do_not_share_response(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """调用级回归：两个不同 system 的 BaseAgent 对同一 user prompt 各调用一次。"""
    import src.utils.embedding_utils as embedding_utils
    from src.agents import base_agent as ba
    from src.agents import semantic_cache as sc
    from src.agents.llm_client import clear_llm_cache_option_memory

    cache_dir = tmp_path / "llm-cache"
    cache_dir.mkdir()
    monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
    monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("SEMANTIC_CACHE_ENABLE", "true")
    monkeypatch.delenv("AITESTER_CACHE_NAMESPACE", raising=False)
    monkeypatch.setattr(embedding_utils, "embed_text", lambda _text: [1.0, 0.0])
    monkeypatch.setattr(ba, "_get_all_api_configs", lambda: [("fake", "https://a.invalid/v1", "m")])
    monkeypatch.setattr(ba, "_openai_extra_body", lambda: {"thinking": {"type": "disabled"}})
    monkeypatch.setattr(sc, "_last_rebuild_ts", 0.0)
    sc.reset_semantic_index()
    ba.clear_llm_lru_cache()
    clear_llm_cache_option_memory()

    with patch("src.agents.base_agent._get_or_create_chat_client", lambda *a, **k: SimpleNamespace()):
        agent_a = ba.BaseAgent("system A")
        agent_b = ba.BaseAgent("system B")

    calls: list[str] = []

    def _fake_call(self, user_message, *args, **kwargs):
        calls.append(self.system_prompt)
        return f"response from {self.system_prompt}"

    monkeypatch.setattr(ba.BaseAgent, "_call_llm", _fake_call)
    try:
        assert agent_a._call_llm_with_cache("same user prompt") == "response from system A"
        assert agent_b._call_llm_with_cache("same user prompt") == "response from system B"
        assert calls == ["system A", "system B"], "不同 system 不得共享缓存/语义响应"
    finally:
        ba.clear_llm_lru_cache()
        sc.reset_semantic_index()
        clear_llm_cache_option_memory()


# ─── A10：显式任务分配优先 ────────────────────────────────────────────────────


def _set_thread(monkeypatch: pytest.MonkeyPatch, api_key: str, base_url: str, model: str) -> None:
    from src.agents import llm_client as lc

    monkeypatch.setattr(lc._thread_local, "api_key", api_key, raising=False)
    monkeypatch.setattr(lc._thread_local, "base_url", base_url, raising=False)
    monkeypatch.setattr(lc._thread_local, "model_name", model, raising=False)


def test_a10_global_override_is_promoted(monkeypatch: pytest.MonkeyPatch) -> None:
    """报告 §M1 反例：全局 [A, B]，线程指定 B → 链首必须是 B，A 保留为后备。"""
    from config import LLMConfig
    from src.agents import llm_client as lc

    cfg_a = LLMConfig("fake-a", "https://a.invalid/v1", "model-a")
    cfg_b = LLMConfig("fake-b", "https://b.invalid/v1", "model-b")
    monkeypatch.setattr(lc, "LLM_CONFIGS", [cfg_a, cfg_b])
    _set_thread(monkeypatch, cfg_b.api_key, cfg_b.base_url, cfg_b.model_name)

    got = lc._get_all_api_configs()
    assert got == [
        ("fake-b", "https://b.invalid/v1", "model-b"),
        ("fake-a", "https://a.invalid/v1", "model-a"),
    ], f"A10：全局已有 B 时必须提到首位（修复前直接早退为 [A, B]）：{got}"


def test_a10_same_base_url_different_model_is_reordered(monkeypatch: pytest.MonkeyPatch) -> None:
    """同 base_url 多模型：指定第二个模型时组内也要提到首位。"""
    from config import LLMConfig
    from src.agents import llm_client as lc

    cfg_1 = LLMConfig("k", "https://shared.invalid/v1", "model-1")
    cfg_2 = LLMConfig("k", "https://shared.invalid/v1", "model-2")
    monkeypatch.setattr(lc, "LLM_CONFIGS", [cfg_1, cfg_2])
    _set_thread(monkeypatch, "k", "https://shared.invalid/v1", "model-2")

    assert [m for _k, _u, m in lc._get_all_api_configs()] == ["model-2", "model-1"]


def test_a10_production_first_request_is_thread_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """真实调用链：全局 [A, B]、分配 B 时首个被创建的客户端必须是 B。"""
    from config import LLMConfig
    from src.agents import base_agent as ba
    from src.agents import llm_client as lc

    cfg_a = LLMConfig("fake-a", "https://a.invalid/v1", "model-a")
    cfg_b = LLMConfig("fake-b", "https://b.invalid/v1", "model-b")
    monkeypatch.setattr(lc, "LLM_CONFIGS", [cfg_a, cfg_b])
    monkeypatch.setattr("config.LLM_CONFIGS", [cfg_a, cfg_b])
    _set_thread(monkeypatch, cfg_b.api_key, cfg_b.base_url, cfg_b.model_name)
    monkeypatch.setenv("AITESTER_LLM_CACHE", "0")

    created: list[tuple[str, str, str]] = []

    def _client(model_name, _temperature, api_key, base_url):
        created.append((api_key, base_url, model_name))
        return SimpleNamespace(
            invoke=lambda messages, **kwargs: SimpleNamespace(
                content="ok",
                response_metadata={"finish_reason": "stop"},
                usage_metadata=None,
            )
        )

    monkeypatch.setattr(ba, "_get_or_create_chat_client", _client)
    agent = ba.BaseAgent("sys prompt")
    created.clear()
    assert agent._call_llm("hello", max_retries=0) == "ok"
    assert created and created[0] == ("fake-b", "https://b.invalid/v1", "model-b"), (
        f"A10：首个请求必须走显式分配 B（实际 {created}）"
    )


def test_a10_explicit_assignment_wins_over_complexity_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    """优先级契约：显式分配 > 复杂度路由 > 全局顺序（complex 档不得把 A 提前）。"""
    from config import LLMConfig
    from src.agents import base_agent as ba
    from src.agents import llm_client as lc

    cfg_a = LLMConfig("fake-a", "https://a.invalid/v1", "model-a", cost_weight=3.0)
    cfg_b = LLMConfig("fake-b", "https://b.invalid/v1", "model-b", cost_weight=0.5)
    monkeypatch.setattr(lc, "LLM_CONFIGS", [cfg_a, cfg_b])
    monkeypatch.setattr("config.LLM_CONFIGS", [cfg_a, cfg_b])
    _set_thread(monkeypatch, cfg_b.api_key, cfg_b.base_url, cfg_b.model_name)
    monkeypatch.setenv("AITESTER_LLM_CACHE", "0")

    created: list[tuple[str, str, str]] = []

    def _client(model_name, _temperature, api_key, base_url):
        created.append((api_key, base_url, model_name))
        return SimpleNamespace(
            invoke=lambda messages, **kwargs: SimpleNamespace(
                content="ok",
                response_metadata={"finish_reason": "stop"},
                usage_metadata=None,
            )
        )

    monkeypatch.setattr(ba, "_get_or_create_chat_client", _client)
    agent = ba.BaseAgent("sys prompt")
    created.clear()
    # complex 档按 cost_weight 会把 A 排前；显式分配 B 必须仍居首
    assert agent._call_llm("hello", max_retries=0, complexity_class="complex") == "ok"
    assert created and created[0] == ("fake-b", "https://b.invalid/v1", "model-b"), (
        f"显式分配必须优先于复杂度重排（实际 {created}）"
    )


def test_a10_pin_helper_keeps_group_and_intra_group_order() -> None:
    """钉住函数的纯逻辑：组移到首位、组内 override 居首、原字典不变。"""
    from src.agents.base_agent import _pin_thread_api_group

    groups = {
        "https://a.invalid/v1": [("fake-a", "model-a")],
        "https://b.invalid/v1": [("fake-b", "model-b1"), ("fake-b", "model-b2")],
    }
    pinned = _pin_thread_api_group(groups, ("fake-b", "https://b.invalid/v1", "model-b2"))
    assert list(pinned) == ["https://b.invalid/v1", "https://a.invalid/v1"]
    assert pinned["https://b.invalid/v1"] == [("fake-b", "model-b2"), ("fake-b", "model-b1")]
    # 原字典不被修改（纯函数）
    assert list(groups) == ["https://a.invalid/v1", "https://b.invalid/v1"]
    assert groups["https://b.invalid/v1"][0] == ("fake-b", "model-b1")
    # 半截/无覆盖 → 原序返回
    assert _pin_thread_api_group(groups, None) is groups
    assert _pin_thread_api_group(groups, ("k", "", "m")) is groups
    # 防御分支：override 完整但其 base_url 组不在链中 → 原序返回（不注入新组）
    orphan = ("fake-z", "https://z.invalid/v1", "model-z")
    assert _pin_thread_api_group(groups, orphan) is groups
