"""S-3 多采样示例自一致性过滤器测试（K=2 spec-only 采样求交；零真实 LLM）。

覆盖：
1. **键归一**：dict 键序无关、ensure_ascii=False、list/tuple 经 JSON 等价、
   int/float 不合并（保守策略）、非法示例键为空串。
2. **求交**：两采样一致保留；只出现一次丢弃并审计 present_in_samples；
   样本内重复只算一次；≤max_examples 截断且顺序取首采样；k=1 退化全部保留。
3. **生成包装**：两采样响应一致 → ok；不相交 → empty；单样本非法 JSON/异常/
   全失败 → 降级并记录原因；每采样 cache namespace 区分 sample_idx 且外层
   env 恢复；usage_totals 汇总；确定性（同输入两次调用的交集顺序稳定）。
4. **不破坏单采样 API**：``generate_spec_examples`` 返回结构与既有契约一致
   （无 samples/audit 新增键）。
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

import experiments.spec_examples_generator as gen


def _resp(examples: list[Any]) -> str:
    return json.dumps({"examples": examples}, ensure_ascii=False)


def _mock_sequence(monkeypatch: pytest.MonkeyPatch, responses: list[str]) -> dict[str, list[Any]]:
    """mock 单次 LLM：按调用序返回 responses（超出则重复最后一个）；记录 env。"""
    calls: dict[str, list[Any]] = {"responses": [], "namespaces": [], "prompts": []}

    def fake(prompt: str, temperature: float = 0.0) -> str:
        calls["prompts"].append(prompt)
        calls["namespaces"].append(os.environ.get("AITESTER_CACHE_NAMESPACE", ""))
        calls["responses"].append(responses[min(len(calls["responses"]), len(responses) - 1)])
        return calls["responses"][-1]

    monkeypatch.setattr(gen, "_call_examples_llm", fake)
    return calls


# ═══ 1. 键归一 ═════════════════════════════════════════════════════════════
class TestNormalizeKey:
    def test_dict_key_order_irrelevant(self) -> None:
        a = gen.normalize_example_key({"input": {"a": 1, "b": 2}, "expected": 3})
        b = gen.normalize_example_key({"expected": 3, "input": {"b": 2, "a": 1}})
        assert a == b

    def test_unicode_not_escaped(self) -> None:
        key = gen.normalize_example_key({"input": ["中文"], "expected": "值"})
        assert "中文" in key and "\\u" not in key

    def test_int_float_not_merged(self) -> None:
        """保守策略：1 与 1.0 JSON 文本不同 → 不同键（交集更严）。"""
        assert gen.normalize_example_key({"input": [1], "expected": 2}) != gen.normalize_example_key(
            {"input": [1.0], "expected": 2.0}
        )

    def test_tuple_list_equivalent(self) -> None:
        """JSON 序列化把 tuple 写成 array：tuple/list 视为同一示例（文档口径）。"""
        assert gen.normalize_example_key({"input": (1, 2), "expected": 3}) == gen.normalize_example_key(
            {"input": [1, 2], "expected": 3}
        )

    def test_invalid_example_key_empty(self) -> None:
        assert gen.normalize_example_key({"bad": 1}) == ""
        assert gen.normalize_example_key("not-dict") == ""


# ═══ 2. 求交 ═══════════════════════════════════════════════════════════════
class TestIntersection:
    def test_common_examples_kept(self) -> None:
        sample0 = [{"input": [1], "expected": 2}, {"input": [2], "expected": 4}]
        sample1 = [{"input": [2], "expected": 4}, {"input": [3], "expected": 6}]
        intersection, audit = gen.intersect_examples([sample0, sample1])
        assert intersection == [{"input": [2], "expected": 4}]
        assert audit["n_examples_intersection"] == 1
        assert audit["n_dropped_non_intersection"] == 2

    def test_dropped_audit_present_in_samples(self) -> None:
        sample0 = [{"input": [1], "expected": 2}]
        sample1 = [{"input": [9], "expected": 9}]
        _intersection, audit = gen.intersect_examples([sample0, sample1])
        dropped = {json.dumps(item["input"]): item for item in audit["dropped"]}
        assert dropped["[1]"]["present_in_samples"] == [0]
        assert dropped["[9]"]["present_in_samples"] == [1]

    def test_duplicate_within_sample_counted_once(self) -> None:
        example = {"input": [1], "expected": 2}
        sample0 = [example, dict(example)]
        sample1: list[dict[str, Any]] = []
        intersection, audit = gen.intersect_examples([sample0, sample1])
        assert intersection == []
        assert audit["n_dropped_non_intersection"] == 1
        assert audit["dropped"][0]["present_in_samples"] == [0]

    def test_cap_max_examples_order_from_first_sample(self) -> None:
        shared = [{"input": [i], "expected": i + 1} for i in range(5)]
        intersection, audit = gen.intersect_examples([shared, shared], max_examples=3)
        assert intersection == shared[:3]
        assert audit["n_examples_intersection_before_cap"] == 5
        assert audit["n_examples_intersection"] == 3

    def test_k1_degenerate_keeps_all_unique(self) -> None:
        sample = [{"input": [1], "expected": 2}, {"input": [1], "expected": 2}, {"input": [2], "expected": 3}]
        intersection, audit = gen.intersect_examples([sample], k=1)
        assert intersection == [{"input": [1], "expected": 2}, {"input": [2], "expected": 3}]
        assert audit["threshold"] == 1

    def test_audit_keys_stable(self) -> None:
        _i, audit = gen.intersect_examples([[{"input": [1], "expected": 2}]], k=2)
        assert set(audit) == {
            "k",
            "threshold",
            "key_normalization",
            "per_sample_counts",
            "n_samples",
            "n_samples_ok",
            "n_examples_union",
            "n_examples_intersection",
            "n_examples_intersection_before_cap",
            "n_dropped_non_intersection",
            "dropped",
        }


# ═══ 3. 生成包装（mock LLM） ═══════════════════════════════════════════════
class TestGenerateMultisample:
    def test_identical_samples_intersect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        examples = [{"input": [2, 3], "expected": 5}]
        _mock_sequence(monkeypatch, [_resp(examples), _resp(examples)])
        record = gen.generate_examples_multisample({"function_name": "add"}, signature_params=["a", "b"])
        assert record["status"] == "ok"
        assert record["examples"] == examples
        assert len(record["samples"]) == 2
        assert record["audit"]["per_sample_counts"] == [1, 1]

    def test_disjoint_samples_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_sequence(
            monkeypatch,
            [
                _resp([{"input": [1], "expected": 2}]),
                _resp([{"input": [9], "expected": 9}]),
            ],
        )
        record = gen.generate_examples_multisample({"function_name": "f"})
        assert record["status"] == "empty"
        assert record["examples"] == []
        assert record["audit"]["n_examples_intersection"] == 0

    def test_partial_invalid_json_degrades(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_sequence(monkeypatch, ["not-json", _resp([{"input": [1], "expected": 2}])])
        record = gen.generate_examples_multisample({"function_name": "f"})
        assert record["status"] == "empty"
        assert record["examples"] == []
        assert record["audit"]["sample_reasons"][0] == "json_parse_error"

    def test_one_llm_error_degrades(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def fake(prompt: str, temperature: float = 0.0) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("network down")
            return _resp([{"input": [1], "expected": 2}])

        monkeypatch.setattr(gen, "_call_examples_llm", fake)
        record = gen.generate_examples_multisample({"function_name": "f"})
        assert record["status"] == "empty"
        assert "llm_error:RuntimeError" in str(record["audit"]["sample_reasons"][0])

    def test_all_errors_status_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake(prompt: str, temperature: float = 0.0) -> str:
            raise RuntimeError("down")

        monkeypatch.setattr(gen, "_call_examples_llm", fake)
        record = gen.generate_examples_multisample({"function_name": "f"})
        assert record["status"] == "error"
        assert record["examples"] == []

    def test_k1_degenerate_returns_single_sample_examples(self, monkeypatch: pytest.MonkeyPatch) -> None:
        examples = [{"input": [i], "expected": i} for i in range(5)]
        _mock_sequence(monkeypatch, [_resp(examples[:3])])
        record = gen.generate_examples_multisample({"function_name": "f"}, k=1, max_examples=3)
        assert record["k"] == 1
        assert record["examples"] == examples[:3]
        assert len(record["samples"]) == 1

    def test_max_examples_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        shared = [{"input": [i], "expected": i} for i in range(4)]
        _mock_sequence(monkeypatch, [_resp(shared), _resp(shared)])
        record = gen.generate_examples_multisample({"function_name": "f"}, max_examples=2)
        assert len(record["examples"]) == 2

    def test_sample_cache_namespaces_distinct(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AITESTER_CACHE_NAMESPACE", "outer")
        examples = [{"input": [1], "expected": 2}]
        calls = _mock_sequence(monkeypatch, [_resp(examples), _resp(examples)])
        gen.generate_examples_multisample({"function_name": "f"}, cache_namespace="base")
        assert calls["namespaces"][0].endswith(":sample0")
        assert calls["namespaces"][1].endswith(":sample1")
        assert "base" in calls["namespaces"][0]
        assert os.environ.get("AITESTER_CACHE_NAMESPACE") == "outer"

    def test_usage_totals(self, monkeypatch: pytest.MonkeyPatch) -> None:
        snapshots = iter(
            [
                {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "llm_calls": 0,
                    "cache_hits": 0,
                    "cache_avoided_tokens": 0,
                },
                {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                    "llm_calls": 1,
                    "cache_hits": 0,
                    "cache_avoided_tokens": 0,
                },
                {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                    "llm_calls": 1,
                    "cache_hits": 0,
                    "cache_avoided_tokens": 0,
                },
                {
                    "input_tokens": 220,
                    "output_tokens": 90,
                    "total_tokens": 310,
                    "llm_calls": 2,
                    "cache_hits": 0,
                    "cache_avoided_tokens": 0,
                },
            ]
        )
        monkeypatch.setattr(gen, "_usage_snapshot", lambda: next(snapshots))
        _mock_sequence(
            monkeypatch,
            [
                _resp([{"input": [1], "expected": 2}]),
                _resp([{"input": [1], "expected": 2}]),
            ],
        )
        record = gen.generate_examples_multisample({"function_name": "f"})
        assert record["usage_totals"]["llm_calls"] == 2
        assert record["usage_totals"]["input_tokens"] == 220

    def test_deterministic_intersection_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sample0 = [{"input": [2], "expected": 2}, {"input": [1], "expected": 1}]
        sample1 = [{"input": [1], "expected": 1}, {"input": [2], "expected": 2}]
        _mock_sequence(monkeypatch, [_resp(sample0), _resp(sample1)])
        first = gen.generate_examples_multisample({"function_name": "f"})
        _mock_sequence(monkeypatch, [_resp(sample0), _resp(sample1)])
        second = gen.generate_examples_multisample({"function_name": "f"})
        assert first["examples"] == second["examples"] == [{"input": [2], "expected": 2}, {"input": [1], "expected": 1}]

    def test_strict_schema_invalid_dropped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        valid = {"input": [1], "expected": 2}
        payload = [valid, {"bad": 1}, {"input": 1}]
        _mock_sequence(monkeypatch, [_resp(payload), _resp(payload)])
        record = gen.generate_examples_multisample({"function_name": "f"})
        assert record["examples"] == [valid]


# ═══ 4. 单采样 API 不破坏 ═══════════════════════════════════════════════════
def test_single_sample_api_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    examples = [{"input": [1], "expected": 2}]
    _mock_sequence(monkeypatch, [_resp(examples)])
    record = gen.generate_spec_examples({"function_name": "f"}, signature_params=["x"])
    assert record["status"] == "ok"
    assert record["examples"] == examples
    # 单采样 API 契约未变：不新增 samples/audit 键
    assert "samples" not in record and "audit" not in record
    assert set(record) >= {"status", "examples", "reason", "prompt_sha256", "usage", "wall_s", "task_id"}
