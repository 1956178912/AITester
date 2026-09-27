"""
P2 #10: LLM 输出格式异常注入测试组。

覆盖三类高频异常场景（不依赖真实 LLM，纯确定性注入 + 解析层断言）：
1. **空响应 / 截断响应**：LLM 返回空串 / 纯空白 / JSON 中途截断——
   `classify_llm_response` 应识别为 LLM_EMPTY_RESPONSE（空/空白）或
   LLM_JSON_PARSE_FAILED（非空但无法提取 JSON）；
2. **字段缺失 / 无效 patch 语义**：JSON 可解析但缺 `patch` / `root_cause`
   字段，或 `patch` 为空 / 非字符串 / 无效 diff——
   `extract_json_object` 正常解析后，下游 Debugger 走保守降级（空 patch →
   下游"无补丁"分支，不崩溃、不阻断实验循环）；
3. **markdown 包裹 / 前后自然语言**：合法 JSON 被 ```json 代码块或自然语言
   前后缀包裹——`extract_json_object` 应正确剥离并解析。

设计口径（与 P0 4.1 响应格式重试、P2 JSON 提取降级一致）：
- 纯数据 / 解析层测试，零 LLM 调用；
- 断言的是"解析层 + 分类器"的确定性行为，不触碰网络与 token；
- 无效 patch 语义的降级断言经 patch_applier 的 sanitize 层
  （test_patch_postprocess.py 已覆盖空壳检测；本文件补"JSON 解析成功但
  patch 字段语义无效"的组合场景）。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.error_classifier import (
    ErrorCategory,
    ErrorClassifier,
)
from src.utils.helpers import extract_json_object


# ─── 1. 空响应 / 截断响应 ─────────────────────────────────────────────────
class TestEmptyAndTruncatedResponses:
    """LLM 空响应 / 截断响应注入。"""

    def test_classify_empty_string(self):
        assert ErrorClassifier.classify_llm_response("") == ErrorCategory.LLM_EMPTY_RESPONSE

    def test_classify_whitespace_only(self):
        assert ErrorClassifier.classify_llm_response("   \n\t  ") == ErrorCategory.LLM_EMPTY_RESPONSE

    def test_classify_truncated_json(self):
        """JSON 中途截断（括号未闭合）→ LLM_JSON_PARSE_FAILED（非空但无法提取）。"""
        truncated = '{"root_cause": "missing return", "error_category": "logic", "patch": "'
        assert ErrorClassifier.classify_llm_response(truncated) == ErrorCategory.LLM_JSON_PARSE_FAILED

    def test_classify_natural_language_only(self):
        """纯自然语言（无任何 {}）→ LLM_JSON_PARSE_FAILED。"""
        assert (
            ErrorClassifier.classify_llm_response("I cannot generate a patch for this code.")
            == ErrorCategory.LLM_JSON_PARSE_FAILED
        )

    def test_classify_valid_json(self):
        """合法 JSON → 非 LLM 异常类别（解析成功，走正常分类）。"""
        valid = json.dumps({"root_cause": "x", "error_category": "assertion", "patch": "..."})
        result = ErrorClassifier.classify_llm_response(valid)
        assert result not in (ErrorCategory.LLM_EMPTY_RESPONSE, ErrorCategory.LLM_JSON_PARSE_FAILED)

    def test_extract_json_truncated_raises(self):
        """截断 JSON 经 extract_json_object → 抛 JSONDecodeError（下游降级空 patch）。"""
        truncated = '{"patch": "diff"  // 截断，括号未闭合'
        with pytest.raises(json.JSONDecodeError):
            extract_json_object(truncated)


# ─── 2. 字段缺失 / 无效 patch 语义 ────────────────────────────────────────
class TestFieldMissingAndInvalidPatch:
    """JSON 可解析但字段缺失 / patch 语义无效。"""

    def test_valid_json_missing_patch_field(self):
        """JSON 成功解析但无 patch 键 → 下游 .get("patch", "") 取空串。"""
        text = json.dumps({"root_cause": "missing return", "error_category": "logic"})
        result = extract_json_object(text)
        assert isinstance(result, dict)
        # 下游 Debugger 用 result.get("patch", "") → 空 patch（保守降级，不崩溃）
        assert result.get("patch", "") == ""

    def test_empty_patch_string(self):
        text = json.dumps({"root_cause": "x", "error_category": "runtime", "patch": ""})
        result = extract_json_object(text)
        assert result["patch"] == ""

    def test_non_string_patch(self):
        """patch 字段为 dict / list（语义无效）→ 仍正常解析（下游按字符串处理时降级）。"""
        text = json.dumps({"patch": {"not": "a string"}})
        result = extract_json_object(text)
        # 解析层不校验类型（保持宽松）；下游 patch_applier sanitize 层负责
        # 字符串化 / 空壳检测（test_patch_postprocess.py 覆盖）
        assert result["patch"] == {"not": "a string"}

    def test_null_patch(self):
        text = json.dumps({"patch": None})
        result = extract_json_object(text)
        assert result["patch"] is None
        # 下游 .get("patch", "") 对 None 值取 None；sanitize 层归一为 ""

    def test_all_fields_present_and_valid(self):
        text = json.dumps(
            {
                "root_cause": "missing None check",
                "error_category": "assertion",
                "fix_strategy": "add boundary check",
                "patch": "--- a/x.py\n+++ b/x.py\n@@\n+if x is None: return 0",
            }
        )
        result = extract_json_object(text)
        assert result["error_category"] == "assertion"
        assert "None" in result["patch"]

    def test_invalid_diff_semantics_still_parses(self):
        """patch 内容非合法 diff（纯文本）→ 解析层不校验 diff 语法（宽松），
        下游 apply_patch 失败走保守降级（保留原代码）。"""
        text = json.dumps({"patch": "this is not a valid unified diff at all"})
        result = extract_json_object(text)
        assert result["patch"] == "this is not a valid unified diff at all"


# ─── 3. markdown 包裹 / 前后自然语言 ──────────────────────────────────────
class TestMarkdownWrappedJson:
    """合法 JSON 被 markdown 代码块 / 自然语言包裹。"""

    def test_json_code_fence_strip(self):
        text = '```json\n{"patch": "x", "error_category": "syntax"}\n```'
        result = extract_json_object(text)
        assert result["error_category"] == "syntax"

    def test_bare_backtick_strip(self):
        text = '```\n{"patch": "y"}\n```'
        result = extract_json_object(text)
        assert result["patch"] == "y"

    def test_natural_language_prefix_suffix(self):
        text = 'Here is the result:\n{"root_cause": "z", "patch": "w"}\nHope this helps.'
        result = extract_json_object(text)
        assert result["root_cause"] == "z"

    def test_markdown_wrapped_truncated_json(self):
        """markdown 包裹 + 截断 JSON → JSONDecodeError（前后缀剥离后仍截断）。"""
        text = '```json\n{"patch": "broken\n```'
        with pytest.raises(json.JSONDecodeError):
            extract_json_object(text)

    def test_extract_classify_valid_markdown_json(self):
        """markdown 包裹合法 JSON → classify_llm_response 非 LLM 异常类别。"""
        text = '```json\n{"error_category": "timeout", "patch": ""}\n```'
        result = ErrorClassifier.classify_llm_response(text)
        assert result not in (ErrorCategory.LLM_EMPTY_RESPONSE, ErrorCategory.LLM_JSON_PARSE_FAILED)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
