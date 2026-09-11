"""日志脱敏工具模块单元测试。

覆盖 mask_sensitive_info 的各模式命中/不命中分支、SensitiveFilter 与
SensitiveFormatter 的行为，以及 redact_dict 对字典的脱敏。
"""

import logging

from src.utils.logging_utils import (
    SensitiveFilter,
    SensitiveFormatter,
    mask_sensitive_info,
    redact_dict,
)


class TestMaskSensitiveInfo:
    """mask_sensitive_info 的各敏感模式覆盖测试。"""

    def test_sk_prefixed_key_redacted(self):
        """sk- 前缀 API Key（字母数字）被脱敏。"""
        assert "sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ123" not in mask_sensitive_info(
            "called sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ123 ok"
        )
        assert "<REDACTED_API_KEY>" in mask_sensitive_info("called sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ123 ok")

    def test_sk_with_dots_and_hyphens_redacted(self):
        """带点号段 / 连字符的 sk- key（如 sk-ws-H.EPIHIXL...）被脱敏。"""
        key = "sk-ws-H.EPIHIXL.Cq2j.MEYCIQDEoLbIemidFUPx58FBK9WvWVXUYKv0x1vBXLXgNuC3hwIhAM7S0LecBrT9hDRcSkDUkEftU0XSvOplvLdp-Wg7pU-s"
        result = mask_sensitive_info(f"using {key} now")
        assert key not in result
        assert "<REDACTED_API_KEY>" in result

    def test_lowercase_hex_key_redacted(self):
        """无 sk- 前缀的小写十六进制长串（>=32 位）被脱敏。"""
        key = "e2b08862968b41408b272d8acfaaaaaaaa"
        result = mask_sensitive_info(f"token is {key} end")
        assert key not in result
        assert "<REDACTED_KEY>" in result

    def test_key_value_pair_redacted(self):
        """key= / token= 等赋值形式被脱敏。"""
        result = mask_sensitive_info("request with key=abcd123456efgh completed")
        assert "abcd123456efgh" not in result
        assert "key=<REDACTED>" in result

    def test_jwt_redacted(self):
        """JWT Token 被脱敏。"""
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.dozjgNryPXTJyjW8T1YwsR"
        result = mask_sensitive_info(f"auth {jwt} done")
        assert jwt not in result
        assert "<REDACTED_JWT>" in result

    def test_normal_text_unchanged(self):
        """普通文本（无敏感模式）保持不变。"""
        text = "测试生成 3 个用例，通过率 100%，平均覆盖率 91%。"
        assert mask_sensitive_info(text) == text

    def test_empty_and_none_returned(self):
        """空串返回空串；None 返回空串。"""
        assert mask_sensitive_info("") == ""
        assert mask_sensitive_info(None) == ""

    def test_short_sk_not_redacted(self):
        """sk- 后不足 20 字符的短串不视为密钥，保持原样。"""
        assert "sk-short" in mask_sensitive_info("api sk-short here")

    def test_short_hex_not_redacted(self):
        """不足 32 字符的十六进制串不脱敏（避免误伤普通 hash 前缀）。"""
        short_hex = "e2b08862968b4140"  # 16 字符
        assert short_hex in mask_sensitive_info(f"id {short_hex} end")


class TestSensitiveFilter:
    """SensitiveFilter 行为测试。"""

    def test_filter_masks_formatted_message(self):
        """record.msg 中的密钥经 filter 后脱敏，args 置 None。"""
        logger = logging.getLogger("test_filter_mask")
        filt = SensitiveFilter()
        key = "sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ123"
        # makeRecord(name, level, fn, lno, msg, args, exc_info, stack_info)
        record = logger.makeRecord(logger.name, logging.INFO, "t.py", 1, "call %s", (key,), None, None)
        assert filt.filter(record) is True
        assert key not in record.getMessage()
        assert record.args is None

    def test_filter_passes_unmaskable_text(self):
        """普通消息 filter 原样放行。"""
        logger = logging.getLogger("test_filter_plain")
        record = logger.makeRecord(logger.name, logging.INFO, "t.py", 1, "plain", (), None, None)
        assert SensitiveFilter().filter(record) is True
        assert record.getMessage() == "plain"


class TestSensitiveFormatter:
    """SensitiveFormatter 行为测试（对完整格式化行脱敏）。"""

    def test_formatter_masks_full_line(self):
        """格式化后的完整行脱敏（msg 与 args 分离存放时仍能命中）。"""
        logger = logging.getLogger("test_formatter_mask")
        formatter = SensitiveFormatter("%(message)s")
        key = "sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ123"
        record = logging.LogRecord(
            name=logger.name,
            level=logging.ERROR,
            pathname="t.py",
            lineno=1,
            msg="failed with key %s",
            args=(key,),
            exc_info=None,
        )
        out = formatter.format(record)
        assert key not in out
        assert "<REDACTED_API_KEY>" in out


class TestRedactDict:
    """redact_dict 对字典值的脱敏测试。"""

    def test_string_values_redacted(self):
        """字符串值中的密钥被脱敏。"""
        key = "sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ123"
        result = redact_dict({"api_key": key, "model": "test"})
        assert key not in result["api_key"]
        assert result["model"] == "test"

    def test_non_string_values_kept(self):
        """非字符串值保持原样。"""
        result = redact_dict({"count": 3, "ratio": 0.5, "ok": True})
        assert result == {"count": 3, "ratio": 0.5, "ok": True}
