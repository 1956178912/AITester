"""多采样示例自一致性过滤器测试（S-3 K=2 求交 + T3 K=3 多数一致/canonical；零真实 LLM）。

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
5. **T3（2026-10-18）**：K=3 + majority=2 多数一致（2/3 保留、1/3 丢弃、
   顺序/审计稳定）；majority 参数钳制与默认（None）历史兼容；canonical input
   约束 prompt 变体（默认**逐字节不变**、canonical 追加冻结段落）；canonical
   失败回退判定（K/K 样本非 ok 才回退）与 fail-open。
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


def test_generate_restores_max_output_tokens_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """W 轮连带修复：max_output_tokens 注入必须随调用结束恢复，不留进程级残留。

    修复前缺陷：`generate_spec_examples` 首次调用后
    `LLM_MAX_OUTPUT_TOKENS=512` 永久留在进程环境，改变同进程后续所有
    LLM 调用的请求体与缓存身份（`_effective_request_identity` 读该 env），
    一次示例生成即可污染整批任务的 provenance 口径——xtest 全量跑中该
    泄漏曾使下游"默认包络旧缓存回退"测试按文件配对顺序随机转红。
    """
    # 未显式配置 → 注入值在调用后被移除
    monkeypatch.delenv("LLM_MAX_OUTPUT_TOKENS", raising=False)
    _mock_sequence(monkeypatch, [_resp([{"input": [1], "expected": 2}])])
    record = gen.generate_spec_examples({"function_name": "f"})
    assert record["status"] == "ok"
    assert record["max_output_tokens"] == str(gen.DEFAULT_MAX_OUTPUT_TOKENS), "本次调用内注入值应生效并被记录"
    assert os.environ.get("LLM_MAX_OUTPUT_TOKENS") is None, "调用结束后不得残留注入值（进程级污染）"

    # 显式配置 → 用户设置优先且原样保留
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "999")
    _mock_sequence(monkeypatch, [_resp([{"input": [1], "expected": 2}])])
    gen.generate_spec_examples({"function_name": "f"})
    assert os.environ.get("LLM_MAX_OUTPUT_TOKENS") == "999", "显式配置不得被覆盖或改动"

    # LLM 失败路径同样恢复（finally 分支）
    monkeypatch.delenv("LLM_MAX_OUTPUT_TOKENS", raising=False)

    def _boom(prompt: str, temperature: float = 0.0) -> str:
        raise RuntimeError("network down")

    monkeypatch.setattr(gen, "_call_examples_llm", _boom)
    record = gen.generate_spec_examples({"function_name": "f"})
    assert record["status"] == "error"
    assert os.environ.get("LLM_MAX_OUTPUT_TOKENS") is None, "异常路径也不得残留注入值"


# ═══ 5. T3：K=3 多数一致 + canonical input 约束 ═════════════════════════════
def _ex(inp: Any, exp: Any) -> dict[str, Any]:
    return {"input": inp, "expected": exp}


_EX_A = _ex([1], 2)
_EX_B = _ex([2], 4)
_EX_C = _ex([3], 6)
_EX_D = _ex([4], 8)


class TestMajority:
    """K=3 + majority=2：2/3 一致保留；1/3 丢弃；顺序与审计稳定。"""

    def test_two_of_three_kept_one_dropped(self) -> None:
        sample0 = [_EX_A, _EX_C, _EX_D]
        sample1 = [_EX_A, _EX_B]
        sample2 = [_EX_B, _EX_D]
        intersection, audit = gen.intersect_examples([sample0, sample1, sample2], k=3, majority=2)
        # A 出现在 0/1；B 出现在 1/2；D 出现在 0/2（均 ≥2/3）；C 仅 0 → 丢弃。
        # 保留顺序 = 跨样本首次出现顺序：A(s0) → D(s0) → B(s1)。
        assert intersection == [_EX_A, _EX_D, _EX_B]
        assert audit["k"] == 3 and audit["threshold"] == 2
        assert audit["n_examples_union"] == 4
        assert audit["n_examples_intersection"] == 3
        assert audit["n_dropped_non_intersection"] == 1
        dropped = audit["dropped"][0]
        assert dropped["input"] == [3] and dropped["present_in_samples"] == [0]

    def test_all_three_kept_when_unanimous(self) -> None:
        shared = [_EX_A, _EX_B, _EX_C]
        intersection, audit = gen.intersect_examples([shared, shared, shared], k=3, majority=2)
        assert intersection == shared
        assert audit["n_dropped_non_intersection"] == 0

    def test_one_of_three_only_dropped(self) -> None:
        samples = [[_EX_A], [_EX_B], [_EX_C]]
        intersection, audit = gen.intersect_examples(samples, k=3, majority=2)
        assert intersection == []
        assert audit["n_dropped_non_intersection"] == 3
        assert [d["present_in_samples"] for d in audit["dropped"]] == [[0], [1], [2]]

    def test_majority_three_strict(self) -> None:
        samples = [[_EX_A, _EX_B], [_EX_A, _EX_C], [_EX_A, _EX_B]]
        intersection, audit = gen.intersect_examples(samples, k=3, majority=3)
        assert intersection == [_EX_A]
        assert audit["threshold"] == 3

    def test_majority_clamped(self) -> None:
        samples = [[_EX_A], [_EX_A], [_EX_A]]
        _i, audit_huge = gen.intersect_examples(samples, k=3, majority=99)
        assert audit_huge["threshold"] == 3
        _i2, audit_zero = gen.intersect_examples(samples, k=3, majority=0)
        assert audit_zero["threshold"] == 1

    def test_default_none_matches_legacy_threshold(self) -> None:
        """默认 majority=None：K=2 → 2/2；K≥2 → threshold=2（历史行为）。"""
        samples = [[_EX_A, _EX_B], [_EX_A]]
        legacy, legacy_audit = gen.intersect_examples(samples, k=2)
        explicit, explicit_audit = gen.intersect_examples(samples, k=2, majority=2)
        assert legacy == explicit == [_EX_A]
        assert legacy_audit == explicit_audit
        assert legacy_audit["threshold"] == 2
        # K=3 默认 threshold 仍是 2（旧公式），语义与显式 majority=2 相同
        _i0, audit_k3 = gen.intersect_examples([[_EX_A], [_EX_A], [_EX_B]], k=3)
        _i1, audit_k3_explicit = gen.intersect_examples([[_EX_A], [_EX_A], [_EX_B]], k=3, majority=2)
        assert audit_k3 == audit_k3_explicit
        # 旧 S-3 测试锁定的 audit 键集合在 T3 扩展后保持不变
        assert set(legacy_audit) == {
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

    def test_cap_order_first_appearance(self) -> None:
        shared4 = [_ex([i], i) for i in range(4)]
        samples = [[shared4[0], shared4[1], shared4[2], shared4[3]], [shared4[1]], [shared4[2]]]
        intersection, audit = gen.intersect_examples(samples, k=3, majority=2, max_examples=2)
        # 先 sample0 顺序（0 只出现一次被丢）→ 1、2 保留并截断 2 条
        assert intersection == [shared4[1], shared4[2]]
        assert audit["n_examples_intersection_before_cap"] == 2
        assert audit["n_examples_intersection"] == 2


class TestCanonicalPrompt:
    """canonical input 约束 = 可选 prompt 变体；默认逐字节不变。"""

    @staticmethod
    def _material() -> dict[str, Any]:
        return {"function_name": "add", "postconditions": ["返回值等于两数之和"]}

    def test_canonical_false_prompt_byte_identical(self) -> None:
        """默认 False：与历史 prompt 手工构造逐字节一致。"""
        material = self._material()
        prompt = gen.build_spec_examples_prompt(material, ["a", "b"], max_examples=3)
        expected = (
            "函数名：add\n"
            "参数名（input 列表按此顺序）：a、b\n"
            "最多示例数：3\n\n"
            "规格材料：\n"
            f"{gen._format_material(material)}\n\n"
            '请只输出 JSON：{"examples": [{"input": [...], "expected": ...}]}'
        )
        assert prompt == expected
        assert gen.CANONICAL_INPUT_SECTION not in prompt

    def test_canonical_true_appends_frozen_section_once(self) -> None:
        material = self._material()
        base = gen.build_spec_examples_prompt(material, ["a", "b"], max_examples=3)
        canonical = gen.build_spec_examples_prompt(material, ["a", "b"], max_examples=3, canonical_inputs=True)
        assert canonical.count(gen.CANONICAL_INPUT_SECTION) == 1
        assert canonical == base.replace(
            "\n\n请只输出 JSON",
            f"\n\n{gen.CANONICAL_INPUT_SECTION}\n\n请只输出 JSON",
            1,
        )
        # 冻结文本关键约束（PREREG 口径）
        for token in ("标准输入模板", "整数/浮点参数", "字符串参数", "二维列表参数", "最小合法组合"):
            assert token in gen.CANONICAL_INPUT_SECTION

    def test_canonical_passed_to_llm_and_sha_recorded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _mock_sequence(
            monkeypatch,
            [_resp([_EX_A]), _resp([_EX_A]), _resp([_EX_A]), _resp([_EX_A])],
        )
        record = gen.generate_examples_multisample(
            {"function_name": "f"}, k=3, majority=2, max_examples=3, canonical_inputs=True
        )
        assert record["status"] == "ok" and len(record["samples"]) == 3
        expected_prompt = gen.build_spec_examples_prompt(
            {"function_name": "f"}, None, max_examples=3, canonical_inputs=True
        )
        for prompt in calls["prompts"][:3]:
            assert gen.CANONICAL_INPUT_SECTION in prompt
        assert record["samples"][0]["prompt_sha256"] == gen._sha256_text(expected_prompt)

    def test_default_multisample_keeps_s3_record_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """默认 k=2/majority=None/canonical=False：返回键位与 S-3 相同（无新增键）。"""
        _mock_sequence(monkeypatch, [_resp([_EX_A]), _resp([_EX_A])])
        record = gen.generate_examples_multisample({"function_name": "f"})
        assert set(record) == {
            "task_id",
            "k",
            "status",
            "examples",
            "samples",
            "audit",
            "usage_totals",
            "wall_s",
            "model",
        }
        assert record["examples"] == [_EX_A]
        assert record["audit"]["threshold"] == 2
        # 单采样返回记录也不新增键
        single = gen.generate_spec_examples({"function_name": "f"})
        assert set(single) == {
            "task_id",
            "status",
            "examples",
            "reason",
            "prompt_sha256",
            "prompt_chars",
            "response_sha256",
            "response_chars",
            "usage",
            "wall_s",
            "model",
            "max_output_tokens",
            "cache_namespace",
        }


class TestCanonicalFallback:
    """PREREG 冻结回退判定：3/3 样本非 ok 才回退；单样本失败不回退（fail-open）。"""

    def test_all_not_ok_falls_back(self) -> None:
        assert gen.should_fallback_canonical(
            {"samples": [{"status": "empty"}, {"status": "error"}, {"status": "empty"}]}
        )

    def test_one_ok_no_fallback(self) -> None:
        assert not gen.should_fallback_canonical(
            {"samples": [{"status": "empty"}, {"status": "ok"}, {"status": "error"}]}
        )

    def test_no_samples_no_fallback_fail_open(self) -> None:
        assert not gen.should_fallback_canonical({})
        assert not gen.should_fallback_canonical({"samples": []})
        assert not gen.should_fallback_canonical({"samples": ["bad"]})
        assert not gen.should_fallback_canonical(None)  # type: ignore[arg-type]

    def test_two_of_three_not_ok_falls_back(self) -> None:
        assert gen.should_fallback_canonical(
            {"samples": [{"status": "error"}, {"status": "error"}, {"status": "empty"}]}
        )

    def test_canonical_llm_error_fail_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(prompt: str, temperature: float = 0.0) -> str:
            raise RuntimeError("down")

        monkeypatch.setattr(gen, "_call_examples_llm", boom)
        record = gen.generate_examples_multisample({"function_name": "f"}, k=3, majority=2, canonical_inputs=True)
        assert record["status"] == "error"
        assert record["examples"] == []
        assert gen.should_fallback_canonical(record) is True
