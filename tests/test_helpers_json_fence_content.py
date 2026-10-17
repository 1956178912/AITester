"""K 轮（2026-10-17）JSON 提取：围栏清洗不得改写字符串内容（确定性回归锁）。

背景（真缺陷，非测试问题）：
    ``extract_json_object`` / ``extract_json_array`` 的历史清洗链用
    ``re.compile(r"```")`` **无条件删除全文任意位置的三连反引号**。合法 JSON
    的字符串值里一旦出现反引号（LLM 输出补丁/命令/代码片段时极常见），内容
    会被静默改写：

        {"cmd": "```bash\\nls\\n```"}  →  {"cmd": "bash\\nls\\n"}
        {"```": null}                 →  {"": null}

    解析仍然"成功"，但下游拿到的是被篡改的数据——比解析失败更危险，因为
    所有调用方都只看"有没有抛 JSONDecodeError"，不会复核字符串内容。

发现路径：
    由 ``tests/test_helpers_json_property.py`` 的围栏直通性质（hypothesis
    300 例）随机生成 ``{'```': None}`` 后命中。该反例随种子出现，单次全量
    全绿不代表不变式成立，故本文件用**确定性**用例把口径钉死（项目 H5 批次
    同一方法论：模糊测试发现 → 确定性回归锁）。

修复口径（对应 ``src/utils/helpers.py`` 模块头部 K 轮说明）：
    1. 原始文本先行快路径：合法 JSON 未清洗即解析，内容零改写；
    2. 围栏只在行首剥离，修复档的兜底输入不再删除字符串内容中的反引号。
"""

from __future__ import annotations

import json

import pytest

from src.utils.helpers import (
    extract_json_array,
    extract_json_object,
    was_leaf_fallback_used,
)

# 含反引号的字符串值：单反引号 / 三连反引号 / 围栏语言标记
_BACKTICK_VALUES: list[str] = [
    "```",
    "```bash\nls -la\n```",
    "```json",
    "use `pip install` here",
    "a```b",
]


def _fenced(payload: str) -> str:
    """按 LLM 常见围栏形态包裹 payload。"""
    return f"```json\n{payload}\n```"


# ─── A. 对象：反引号内容直通 ─────────────────────────────────────────────


class TestObjectBacktickPreservation:
    @pytest.mark.parametrize("value", _BACKTICK_VALUES)
    def test_triple_backtick_in_value_plain(self, value: str) -> None:
        """未围栏 JSON 的字符串值原样保留（历史缺陷：反引号被删）。"""
        obj = {"key": value, "n": 1}
        assert extract_json_object(json.dumps(obj)) == obj

    @pytest.mark.parametrize("value", _BACKTICK_VALUES)
    def test_triple_backtick_in_value_fenced(self, value: str) -> None:
        """markdown 围栏包裹后字符串值仍原样保留。"""
        obj = {"key": value, "n": 1}
        assert extract_json_object(_fenced(json.dumps(obj))) == obj

    def test_backtick_key_preserved_property_counterexample(self) -> None:
        """property 测试反例的最小形式：``{"```": null}`` 不得变成 ``{"": null}``。"""
        assert extract_json_object('{"```": null}') == {"```": None}
        assert extract_json_object(_fenced('{"```": null}')) == {"```": None}

    def test_backtick_json_marker_content_preserved(self) -> None:
        """字符串内容里的 "```json" 不被当成围栏删除。"""
        obj = {"nested": "```json", "cmd": "```bash\npytest -q\n```"}
        assert extract_json_object(_fenced(json.dumps(obj))) == obj

    def test_natural_language_wrapping_with_backticks(self) -> None:
        """前后自然语言 + 围栏 + 反引号内容：三者叠加仍零改写。"""
        obj = {"patch": "```diff\n--- a\n+++ b\n```"}
        text = f"这里是结果：\n{_fenced(json.dumps(obj))}\n希望有帮助。"
        assert extract_json_object(text) == obj


# ─── B. 数组：反引号内容直通 ─────────────────────────────────────────────


class TestArrayBacktickPreservation:
    @pytest.mark.parametrize("value", _BACKTICK_VALUES)
    def test_triple_backtick_in_array_plain(self, value: str) -> None:
        arr = [value, "plain", 3]
        assert extract_json_array(json.dumps(arr)) == arr

    @pytest.mark.parametrize("value", _BACKTICK_VALUES)
    def test_triple_backtick_in_array_fenced(self, value: str) -> None:
        arr = [value, "plain", 3]
        assert extract_json_array(_fenced(json.dumps(arr))) == arr


# ─── C. 修复档：内容保留与历史修复能力并存 ───────────────────────────────


class TestRepairPathPreservesContent:
    """修复档（尾随逗号等）仍需工作，且改写范围限于语法修复本身。"""

    @pytest.mark.parametrize("fenced", [False, True])
    def test_trailing_comma_repair_keeps_backtick_value(self, fenced: bool) -> None:
        """尾随逗号修复后，字符串值中的反引号必须仍在。"""
        payload = '{"a": "x```y", "b": 2,}'
        text = _fenced(payload) if fenced else payload
        assert extract_json_object(text) == {"a": "x```y", "b": 2}

    def test_unquoted_python_literal_repair_keeps_backtick_value(self) -> None:
        """未加引号 Python 字面量修复（True/None）不误删反引号内容。"""
        payload = '{"a": "v```w", "ok": True, "none": None}'
        assert extract_json_object(payload) == {"a": "v```w", "ok": True, "none": None}

    def test_multi_object_back_to_back_keeps_content(self) -> None:
        """多对象背靠背（D1 修复档 2）取首个，且首个内容完整。"""
        text = '{"a": "```bash"} {"b": "```json"}'
        assert extract_json_object(text) == {"a": "```bash"}


# ─── D. 观测哨兵：快路径成功不得误报叶子回退 ─────────────────────────────


class TestLeafFallbackSentinelWithBackticks:
    def test_raw_fast_path_does_not_set_leaf_fallback(self) -> None:
        """快路径直解析成功属于正常档，``was_leaf_fallback_used()`` 必须为 False。"""
        obj = {"cmd": "```bash\nls\n```"}
        assert extract_json_object(_fenced(json.dumps(obj))) == obj
        assert was_leaf_fallback_used() is False

    def test_leaf_fallback_still_fires_on_truncated_outer_object(self) -> None:
        """既有叶子回退能力不受本轮修复影响（回归保护）。"""
        text = '{"outer": {"inner": 1}, "broken": '
        result = extract_json_object(text)
        # 外层残缺 → 返回最内层片段，且哨兵置位（历史口径）
        assert result == {"inner": 1}
        assert was_leaf_fallback_used() is True
