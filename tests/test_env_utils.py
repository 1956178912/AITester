"""env_flag 单一事实源单测（2026-10-16 C 轮去重）。

锁定口径：
1. 与历史惯用法 ``os.getenv(NAME, "false").lower() in ("true","1","on")``
   的**逐字节行为等价**（未设置→默认；已设置→接受集判定；空串→False）；
2. 空白容忍（项目新开关多数惯例，见 env_utils docstring 披露）；
3. 扩展集必须显式声明（"yes" 不在默认集——防口径隐式分裂）；
4. 大小写不敏感。
"""

from __future__ import annotations

import pytest

from src.utils.env_utils import env_flag


@pytest.mark.unit
class TestEnvFlagEquivalence:
    """与历史惯用法的行为等价性（逐字节）。"""

    def test_unset_returns_default_false(self, monkeypatch):
        monkeypatch.delenv("AITESTER_TEST_FLAG", raising=False)
        assert env_flag("AITESTER_TEST_FLAG") is False

    def test_unset_returns_default_true(self, monkeypatch):
        monkeypatch.delenv("AITESTER_TEST_FLAG", raising=False)
        assert env_flag("AITESTER_TEST_FLAG", True) is True

    @pytest.mark.parametrize("raw", ["true", "TRUE", "True", "1", "on", "ON"])
    def test_canonical_true_values(self, monkeypatch, raw):
        monkeypatch.setenv("AITESTER_TEST_FLAG", raw)
        assert env_flag("AITESTER_TEST_FLAG") is True

    @pytest.mark.parametrize("raw", ["false", "0", "off", "yes", "no", "enabled", "2", "tru"])
    def test_non_true_values_are_false(self, monkeypatch, raw):
        monkeypatch.setenv("AITESTER_TEST_FLAG", raw)
        assert env_flag("AITESTER_TEST_FLAG") is False

    def test_empty_string_is_false_even_with_true_default(self, monkeypatch):
        # 历史惯用法：显式空值 "" 不在接受集 → False（与 default 无关）
        monkeypatch.setenv("AITESTER_TEST_FLAG", "")
        assert env_flag("AITESTER_TEST_FLAG", True) is False

    def test_whitespace_tolerance_documented(self, monkeypatch):
        # 2026-10-16 C 轮统一口径：strip 后判定（项目新开关多数惯例）
        monkeypatch.setenv("AITESTER_TEST_FLAG", "  true \n")
        assert env_flag("AITESTER_TEST_FLAG") is True

    def test_returns_bool_type(self, monkeypatch):
        monkeypatch.setenv("AITESTER_TEST_FLAG", "true")
        assert isinstance(env_flag("AITESTER_TEST_FLAG"), bool)


@pytest.mark.unit
class TestEnvFlagExtraTrue:
    """扩展集必须显式声明。"""

    def test_yes_not_in_default_set(self, monkeypatch):
        # 默认集不收 "yes"——防"某处放宽、某处严"的隐式分裂
        monkeypatch.setenv("AITESTER_TEST_FLAG", "yes")
        assert env_flag("AITESTER_TEST_FLAG") is False

    def test_yes_with_explicit_extra(self, monkeypatch):
        monkeypatch.setenv("AITESTER_TEST_FLAG", "yes")
        assert env_flag("AITESTER_TEST_FLAG", extra_true=("yes",)) is True

    def test_extra_true_tuple_single_element(self, monkeypatch):
        # 单元素必须带逗号（("yes",) 才是元组；("yes") 是字符串会被逐字符展开）
        monkeypatch.setenv("AITESTER_TEST_FLAG", "yes")
        assert env_flag("AITESTER_TEST_FLAG", extra_true=("yes",)) is True

    def test_extra_true_multiple(self, monkeypatch):
        monkeypatch.setenv("AITESTER_TEST_FLAG", "enabled")
        assert env_flag("AITESTER_TEST_FLAG", extra_true=("yes", "enabled")) is True

    def test_default_true_with_extra(self, monkeypatch):
        monkeypatch.delenv("AITESTER_TEST_FLAG", raising=False)
        assert env_flag("AITESTER_TEST_FLAG", True, extra_true=("yes",)) is True
