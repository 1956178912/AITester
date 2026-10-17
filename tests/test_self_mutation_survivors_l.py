"""自身测试套件 L 轮：击杀 K 轮归因中「待补」的 helpers 存活变异体（行为导向）。

背景（`experiments/results/self_mutation_20261017/survivor_attribution.md` §3.4）
-----------------------------------------------------------------------------
K 轮（2026-10-17）把 3 个叶子工具模块的自身变异分数从 0.6419 提到 0.7674
（165/215），剩余 50 个存活中 23 个归为「待补：未构造出可杀输入的防御分支」。
本文件针对这 23 个逐条做**公开行为差分**，其中 11 个可被公开契约区分、11 个
经机制论证 + 差分探测判定为实践等价、1 个（logger.warning 诊断文本）按
「不把内部诊断消息固化为测试契约」原则保留存活（逐条归因见 L 轮报告
`experiments/results/self_mutation_l_round/`）。

口径（纪律）
------------
- 只调用公开 API：``extract_json_object`` / ``extract_json_array`` /
  ``was_leaf_fallback_used``（后者是模块文档承诺的 OMS 可观测性契约）；
- 不读取私有函数、不 monkeypatch 被测实现、不断言具体错误消息全文/随机值；
- 每条断言都是**行为契约**（LLM 畸形输出修复链的公开承诺），在原始源码上绿、
  在对应变异体上红（沙箱逐条预验证，见 L 轮报告 §击杀清单）。

覆盖的变异体（ID 后缀 12 位 sha 前缀，与 self_mutation 报告同源）：
- ``5f59874830d1``：合法空对象必须走直解析、不得被误记为叶子回退；
- ``5f886043809a`` / ``a3ee749e3485``：三层叶子回退的「尾扫」档契约；
- ``cc058e223acc``：解析最终失败时叶子回退哨兵必须复位（不得残留 True）；
- ``608205e3bd2f`` / ``f95a3a18c5c3``：元组键修复必须字符串感知（不碰字符串内容）；
- ``a93688ca6eb0``：字符串感知切分在「空串/转义串」边界仍然正确；
- ``29836f6132a3``：数组路径的数值 Python 表达式修复链；
- ``925bf0576cf6``：数值表达式结果位数上限的边界语义（4096 位）；
- ``396a28db8ca8``：超长单行 Python 表达式保守不评估（文档口径）；
- ``e6b7f907a2b1``：修复用尽后必须抛 ``json.JSONDecodeError``（调用方契约），
  不得泄漏 ``TypeError``。
"""

from __future__ import annotations

import json

import pytest

from src.utils.helpers import extract_json_array, extract_json_object, was_leaf_fallback_used

# 超长单行 Python 字符串表达式（>4096 字符，触发 _quote_python_expressions 的
# max_len 保守口径）。700 项 `"x" + ...` 的单行文本长约 4.2KB。
_OVERLONG_EXPR_TEXT = '{"a": ' + " + ".join(['"x"'] * 700) + "}"

# 4096 位十进制整数：10**4095 恰好 4096 位（边界语义：> 4096 才拒绝修复）。
_HUGE_INT_TEXT = '{"n": 10**4095}'

# 多对象/残片拼接：首对象不可解析、末两个叶子也不可解析，第三新的叶子可解析，
# 用于锁定「叶子回退尾扫档」的公开行为（返回 {'good': 5} 且哨兵置位）。
_TAIL_SCAN_TEXT = '{"outer": {"good": 5} junk} {"bad1": } {"bad2": }'

# 元组键 + 字符串内容含「元组键形状」文本：字符串感知修复的文档反例。
_TUPLE_KEY_STRING_TEXT = '{"desc": "note ,(0,1): pair", (0,1): 5}'


class TestLeafFallbackOmsContract:
    """OMS 叶子回退哨兵（``was_leaf_fallback_used``）的公开可观测契约。"""

    def test_empty_object_via_direct_path_is_not_leaf_fallback(self) -> None:
        """合法空对象能直解析时必须走直解析，不得被误记为叶子回退。

        变异体 ``5f59874830d1``（``_find_balanced_json`` 闭合符被改写）会让
        直解析/括号平衡全部失效，退到叶子档并置位哨兵——下游 M10 归因
        会把「正常提取到空对象」误诊为「提取器回退」，故哨兵值是可观测契约。
        """
        assert extract_json_object("prefix {} suffix") == {}
        assert was_leaf_fallback_used() is False

    def test_fenced_empty_object_is_not_leaf_fallback(self) -> None:
        """带 markdown 围栏的空对象同样不得触发叶子回退哨兵（围栏清洗无损）。"""
        assert extract_json_object("```json\n{}\n```") == {}
        assert was_leaf_fallback_used() is False

    def test_tail_scan_fallback_returns_later_fragment_and_sets_flag(self) -> None:
        """尾扫档契约：最后两个叶子不可解析时返回更早的可解析片段并置哨兵。

        变异体 ``a3ee749e3485``（阈值 ``>2`` 被改成 ``>3``）会让尾扫档不触发
        而整体抛错；``5f886043809a``（哨兵置位改 False）会返回正确片段但
        哨兵恒 False——两者都破坏「返回值 + 可观测标记」这一对公开承诺。
        """
        assert extract_json_object(_TAIL_SCAN_TEXT) == {"good": 5}
        assert was_leaf_fallback_used() is True

    def test_second_newest_leaf_fallback_sets_flag(self) -> None:
        """次新候选档（倒数第二个叶子可解析）同样必须置位哨兵（防回退）。"""
        text = '{"outer": {"good": 5} junk} {"ok": 2} {"bad": }'
        assert extract_json_object(text) == {"ok": 2}
        assert was_leaf_fallback_used() is True

    def test_leaf_flag_resets_when_extraction_ultimately_fails(self) -> None:
        """全部方案失败而抛 ``JSONDecodeError`` 时，哨兵必须复位为 False。

        变异体 ``cc058e223acc``（失败分支的复位被改成 True）会残留哨兵，
        使调用方把「本次解析失败」误读为「发生了叶子回退」。
        """
        with pytest.raises(json.JSONDecodeError):
            extract_json_object('{"a": (0,1): 5}')
        assert was_leaf_fallback_used() is False


class TestTupleKeyStringAwareness:
    """元组键修复的字符串感知（不触碰字符串字面量内容）。"""

    def test_tuple_key_repair_preserves_string_literal_content(self) -> None:
        """键位置的 Python 元组被转成字符串，但字符串**内容**逐字保留。

        变异体 ``608205e3bd2f`` / ``f95a3a18c5c3`` 破坏字符串状态机后，
        会把字符串内部的「元组键形状」文本当成键位置替换，产出不可解析结果。
        """
        assert extract_json_object(_TUPLE_KEY_STRING_TEXT) == {
            "desc": "note ,(0,1): pair",
            "(0,1)": 5,
        }

    def test_fenced_response_tuple_key_repair_preserves_string_content(self) -> None:
        """围栏清洗 + 元组键修复组合路径同样保持字符串内容（真实 LLM 响应形态）。"""
        text = "```json\n" + _TUPLE_KEY_STRING_TEXT + "\n```"
        assert extract_json_object(text) == {"desc": "note ,(0,1): pair", "(0,1)": 5}

    def test_tuple_key_repair_with_empty_first_string(self) -> None:
        """首个字符串为空串或转义串时，字符串状态机仍须正确（空串边界）。

        变异体 ``a93688ca6eb0``（``esc`` 初始值 False→True）会把每个字符串的
        第一个字符当作已转义，空串键因此吞掉后续文本，元组键修复失效。
        """
        assert extract_json_object('{"": 1, (0,1): 5}') == {"": 1, "(0,1)": 5}

    def test_tuple_key_repair_after_escaped_first_string(self) -> None:
        """首个字符串以反斜杠转义开头时，元组键修复链仍须产出正确字典。"""
        text = '{"path": "\\\\server", (0,1): 5}'
        assert extract_json_object(text) == {"path": "\\server", "(0,1)": 5}


class TestNumericExpressionRepair:
    """数值 Python 表达式修复链（``10**18`` / 下划线分隔等 LLM 输出形态）。"""

    def test_numeric_expression_repaired_in_array(self) -> None:
        """数组路径的数值表达式修复：``[2**32]`` → ``[4294967296]``。

        变异体 ``29836f6132a3``（修复候选循环 ``continue``→``break``）在首个
        候选失败后提前终止，数组路径的修复档整体失效。
        """
        assert extract_json_array("[2**32]") == [4294967296]

    def test_numeric_expression_digit_boundary_is_conservative(self) -> None:
        """结果位数边界：恰好 4096 位的整数仍应被修复（严格大于才拒绝）。

        变异体 ``925bf0576cf6``（``>``→``>=``）把边界提前一位，4096 位结果被
        原样保留而 JSON 无法解析，公开行为从「返回字典」退化为抛错。
        """
        assert extract_json_object(_HUGE_INT_TEXT) == {"n": 10**4095}

    def test_overlong_single_line_expression_is_not_evaluated(self) -> None:
        """超过 ``max_len`` 的单行 Python 表达式保守保留，不静默改写。

        文档口径（``_quote_python_expressions`` docstring）：候选必须单行且
        长度 ≤ 4096，超限原样保留交既有降级链——最终应抛 ``JSONDecodeError``
        （诚实失败），而不是把超长表达式求值后截断返回。
        变异体 ``396a28db8ca8``（``or``→``and``）使超限单行表达式被求值。
        """
        with pytest.raises(json.JSONDecodeError):
            extract_json_object(_OVERLONG_EXPR_TEXT)


class TestRepairChainFailureContract:
    """修复链耗尽后的异常类型契约（调用方按 ``json.JSONDecodeError`` 降级）。"""

    def test_bounded_repair_failure_raises_json_decode_error_not_type_error(self) -> None:
        """无法修复的输入必须抛 ``json.JSONDecodeError``，不得泄漏 ``TypeError``。

        变异体 ``e6b7f907a2b1``（``return cur``→``return None``）在修复轮次
        用尽时返回 None，调用方 ``json.loads(None)`` 抛 TypeError 逃逸出去——
        而下游只捕获 ``JSONDecodeError``（nodes.py 默认计划降级路径）。
        """
        with pytest.raises(json.JSONDecodeError):
            extract_json_object("{junk" + ", " * 8 + "}")
