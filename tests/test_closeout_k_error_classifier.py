"""KB 覆盖率收口：`src/agents/error_classifier.py` 的上下文提取 / 解释文本分支。

动机：error_classifier 补口前 16 行未覆盖，缺口集中在**错误上下文提取的降级
匹配分支**——`file.py:line:col` 语法格式、pytest `E path.py:line:col` 紧凑格式、
`--tb=short` 帧行（完整 traceback 被省略时的定位来源）。这些分支决定"位置感知
修复"能否拿到行号；未覆盖时一旦 LLM/pytest 输出形态变化，定位会静默降级为
全文件修复而无人察觉。

纪律：纯字符串/纯数据路径，零 LLM、零网络、零文件系统。
"""

from __future__ import annotations

import json

import pytest

from src.agents.error_classifier import ErrorCategory, ErrorClassifier, SyntaxSubtype


@pytest.mark.unit
class TestConfidenceCombinedPath:
    """classify_with_confidence 的 _combined 预合并入参路径。"""

    def test_precombined_text_skips_resplicing(self):
        classifier = ErrorClassifier()
        result = classifier.classify_with_confidence(
            "这段输入应被忽略",
            _combined="AssertionError: assert add(1, 2) == 4",
        )
        assert result.category == ErrorCategory.ASSERTION
        assert result.confidence == pytest.approx(0.9)
        # _combined 优先：被忽略的入参文本不参与分类
        assert "这段输入应被忽略" not in result.explanation


@pytest.mark.unit
class TestExplanationStateRefinement:
    """状态细化类别的解释文本分支（已知 17 类之外的枚举值）。"""

    def test_state_refinement_category_gets_generic_explanation(self):
        classifier = ErrorClassifier()
        text = classifier._build_explanation(
            ErrorCategory.LLM_EMPTY_RESPONSE,
            0.9,
            "rule_empty_response",
            False,
            "",
            None,
        )
        assert "状态细化类别 llm_empty_response" in text
        assert "置信度 0.90" in text


@pytest.mark.unit
class TestErrorContextExtraction:
    """三种语法/帧格式的行列号提取（位置感知修复的输入口径）。"""

    def test_syntax_error_file_line_col_format(self):
        context = ErrorClassifier().extract_error_context(
            "mymodule.py:12:5: invalid syntax",
            [],
        )
        assert context.filename == "mymodule.py"
        assert context.line == 12
        assert context.column == 5
        assert context.subtype == SyntaxSubtype.SYNTAX_ERROR

    def test_pytest_compact_syntax_format(self):
        """pytest `E   path/file.py:line:col` 紧凑格式（无完整 File 帧）。"""
        # 注意：不带尾随 ": 文本"，否则会先命中 file.py:line:col 分支
        context = ErrorClassifier().extract_error_context(
            "E   mymodule.py:7:3",
            [],
        )
        assert context.line == 7
        assert context.column == 3
        assert context.subtype == SyntaxSubtype.SYNTAX_ERROR

    def test_short_traceback_frames_pick_deepest_frame(self):
        """--tb=short 帧行：取最后一个匹配帧（被测模块帧在调用栈末尾）。"""
        output = "test_target.py:10: in test_add\nmymodule.py:6: in get_option\n"
        context = ErrorClassifier().extract_error_context(output, [])
        assert context.filename == "mymodule.py"
        assert context.line == 6
        assert context.subtype is None, "--tb=short 分支只定位、不改错误分类口径"


@pytest.mark.unit
class TestClassifyLlmResponseGuards:
    """P0 4.1 响应格式分类：空响应 / JSON 解析失败 / 正常。"""

    def test_empty_response_is_llm_empty_response(self):
        assert ErrorClassifier.classify_llm_response("   \n") == ErrorCategory.LLM_EMPTY_RESPONSE

    def test_unparseable_response_is_json_parse_failed(self):
        assert ErrorClassifier.classify_llm_response("这不是 JSON") == ErrorCategory.LLM_JSON_PARSE_FAILED

    def test_normal_json_is_format_error_category(self):
        """可解析 JSON → 归 LLM_FORMAT_ERROR（保留"格式异常大类"历史语义）。"""
        raw = json.dumps({"root_cause": "x", "patch": "```python\npass\n```"})
        assert ErrorClassifier.classify_llm_response(raw) == ErrorCategory.LLM_FORMAT_ERROR

    def test_none_extraction_defensive_guard(self, monkeypatch: pytest.MonkeyPatch):
        """防御性守卫：提取器返回 None（现实现走 raise）时按 JSON 解析失败处理。

        注释说明：当前 helpers.extract_json_object 失败必抛 JSONDecodeError，
        该 None 分支是历史契约的防御性兜底；用 monkeypatch 钉住守卫口径，
        避免未来提取器改为"静默返回 None"时静默产出错误类别。
        """
        monkeypatch.setattr("src.utils.helpers.extract_json_object", lambda text: None)
        assert ErrorClassifier.classify_llm_response("{}") == ErrorCategory.LLM_JSON_PARSE_FAILED
