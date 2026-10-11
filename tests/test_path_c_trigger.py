"""路径 C 回归守卫：GCP 剪枝 / 见证搜索 / 安全门 / 统一管线。

全部断言均可零 LLM 复算；三条核心不变量：

1. **GCP 只做减法**：剔除"在 gold 上失败"的块；**全部块都失败时不产出空套件**
   （否则会变成"恒红"假阳性）。
2. **见证必须行为归一化后比较**：generator/iterator 的 `repr` 含内存地址，
   直接比较会产生假见证（实测 `flatten` 两版都返回 generator → 57/57 假阳性）。
3. **见证必须过安全门**：先在 gold 上通过才允许注入（实测
   `minimum_spanning_tree` 的 24 条候选全部被拒，若无此门会把 detection 从 1.0 打回 0.0）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments.gold_consistency_pruning import prune_inconsistent_blocks
from experiments.solver_directed_trigger import (
    infer_param_family,
    search_trigger_witnesses,
)
from experiments.suite_repair_pipeline import repair_suite

# 缺陷版返回 a-b / 正确版返回 a-b 的绝对值（构造最小可判定场景）
_BUGGY = "def sub(a, b):\n    return a - b\n"
_GOLD = "def sub(a, b):\n    return abs(a - b)\n"
# 一个"在 gold 上失败"的块（断言了缺陷版行为）——GCP 应剔除它
_BAD_BLOCK = "def test_bad():\n    assert sub(1, 5) == -4\n"
# 一个在 gold 上正确的块
_GOOD_BLOCK = "def test_good():\n    assert sub(5, 1) == 4\n"
_HEADER = "from sub import sub\n\n"


class TestGCPPruning:
    def test_prunes_block_failing_on_gold(self) -> None:
        suite = _HEADER + _BAD_BLOCK + "\n" + _GOOD_BLOCK
        r = prune_inconsistent_blocks(test_code=suite, gold_code=_GOLD, module_name="sub")
        assert r.available is True
        assert r.n_pruned == 1, "断言了缺陷版行为的块必须被剔除"
        assert len(r.kept_blocks) == 1
        assert "test_good" in r.pruned_code
        assert "test_bad" not in r.pruned_code

    def test_already_green_is_noop(self) -> None:
        r = prune_inconsistent_blocks(test_code=_HEADER + _GOOD_BLOCK, gold_code=_GOLD, module_name="sub")
        assert r.available is True
        assert r.not_available_reason == "already_green_on_gold"
        assert r.n_pruned == 0

    def test_all_blocks_inconsistent_is_not_available(self) -> None:
        """全部块失败 → 不得产出空套件（会变成恒红假阳性）。"""
        suite = _HEADER + _BAD_BLOCK + "\ndef test_bad2():\n    assert sub(2, 9) == 0\n"
        r = prune_inconsistent_blocks(test_code=suite, gold_code=_GOLD, module_name="sub")
        assert r.available is False
        assert r.not_available_reason == "all_blocks_inconsistent"

    def test_empty_input_is_not_available(self) -> None:
        r = prune_inconsistent_blocks(test_code="", gold_code=_GOLD, module_name="sub")
        assert r.available is False
        assert r.not_available_reason == "empty_input"


class TestParamFamilyInference:
    """名称启发式（QuixBugs 全部 41 程序零类型注解，只能靠名称）。"""

    def test_known_families(self) -> None:
        assert infer_param_family("arr") == "seq"
        assert infer_param_family("items") == "seq_seq"
        assert infer_param_family("weight_by_edge") == "dict"
        assert infer_param_family("s") == "str"
        assert infer_param_family("source") == "str"
        assert infer_param_family("n") == "int"
        assert infer_param_family("k") == "int"
        assert infer_param_family("node") == "node"
        assert infer_param_family("mystery") == "unknown"

    def test_body_hint_for_subscript(self) -> None:
        assert infer_param_family("data", "def f(data):\n    return data[0]\n") == "seq"


class TestWitnessSearch:
    def test_finds_divergent_input_on_minimal_case(self) -> None:
        r = search_trigger_witnesses(buggy_code=_BUGGY, gold_code=_GOLD, fn_name="sub", max_candidates=30)
        assert r.available is True
        assert r.witnesses, "a-b 与 |a-b| 在 b>a 时必然不同，必须找到见证"
        # 每条见证都必须真的行为不同
        for w in r.witnesses:
            assert w.buggy_behavior != w.gold_behavior

    def test_no_divergence_when_versions_identical(self) -> None:
        r = search_trigger_witnesses(buggy_code=_GOLD, gold_code=_GOLD, fn_name="sub", max_candidates=20)
        assert r.available is True
        assert not r.witnesses
        assert r.not_available_reason == "no_divergent_input_found"

    def test_missing_function_is_fail_closed(self) -> None:
        r = search_trigger_witnesses(buggy_code=_BUGGY, gold_code=_GOLD, fn_name="nope", max_candidates=5)
        assert r.available is False
        assert r.not_available_reason.startswith("fn_not_found")


class TestSuiteRepairPipeline:
    def test_repairs_zero_detection_suite(self) -> None:
        """含"gold 上失败块"的套件应被修成 gold 全绿且缺陷特异。"""
        suite = _HEADER + _BAD_BLOCK
        out = repair_suite(test_code=suite, gold_code=_GOLD, buggy_code=_BUGGY, fn_name="sub", max_candidates=30)
        assert out.available is True, out.not_available_reason
        assert out.repaired_code.strip()
        # 修复后必须不再包含那个错误期望值
        assert "== -4" not in out.repaired_code

    def test_safety_gate_rejects_ungreen_witnesses(self) -> None:
        """安全门：见证断言在 gold 上不通过时不得注入。"""
        out = repair_suite(
            test_code=_HEADER + _GOOD_BLOCK,
            gold_code=_GOLD,
            buggy_code=_BUGGY,
            fn_name="sub",
            max_candidates=20,
        )
        # 该套件本就在 gold 上全绿 → GCP 为 noop；见证若被接受，必过安全门
        assert out.available is True
        for body in out.repaired_code.split("def test_srp_witness_"):
            assert "== -" not in body or "abs" in body, "不得注入与 gold 不符的断言"

    def test_empty_input_unavailable(self) -> None:
        out = repair_suite(test_code="", gold_code=_GOLD, buggy_code=_BUGGY, fn_name="sub")
        assert out.available is False
        assert out.not_available_reason == "empty_input"

    def test_as_dict_serializable(self) -> None:
        import json

        out = repair_suite(test_code=_HEADER + _BAD_BLOCK, gold_code=_GOLD, buggy_code=_BUGGY, fn_name="sub")
        payload = out.as_dict()
        # 显式断言（门禁 check_zero_assert_tests 要求有效断言信号；此前仅
        # "调用不抛异常"，语义上等于零断言，会被 CI 门禁判红）
        assert isinstance(payload, dict), "as_dict 必须返回 dict"
        assert isinstance(json.loads(json.dumps(payload)), dict), "序列化往返必须保持 dict"


class TestNormalizationDocumented:
    """把"generator 地址差异"这一实测教训固化为文档级断言。"""

    def test_generator_returning_pair_yields_no_false_witness(self) -> None:
        """两版都返回 generator 且元素相同 → 不得产生见证。"""
        gen_yield = "def g(x):\n    return (i for i in [1, 2])\n"
        r = search_trigger_witnesses(buggy_code=gen_yield, gold_code=gen_yield, fn_name="g", max_candidates=10)
        assert not r.witnesses, "同一实现不得因 generator 地址不同而产生见证"
