"""P2 一期：观测级行粒度压缩（src/tools/feedback_compression.py）单元测试。

背景（A/B 阴性结果驱动的 token 成本优化）：
    完整编排臂每任务 token 26.1k vs 检出优先协议臂 4.2k（6.2× 开销）。
    一期方案：Debugger→Generator 的反馈只传「失败测试涉及的源代码行 +
    错误类型 + 存活变异体摘要」（arXiv:2605.15315 行级压缩口径）。

本文件覆盖（零真实 LLM / 零网络；_generator_node 经 mock
get_or_create_agent 隔离，generate() 经 mock _call_llm_with_cache 隔离）：
    A. 开关与体积参数解析（默认 false / truthy / falsy / 非法值 / 钳制区间）
    B. build_compressed_feedback：
       - traceback / probe / fl_spectral 三路候选行定位、优先级与去重
       - 跨文件保护（traceback 帧 basename 与 target_module 不符则丢弃）
       - 源码回填与越界守卫（保留行号记录、source 空串）
       - 失败测试 / 存活变异体截断、mutation_score 透传
       - 降级路径（空 state / 仅 error_category / 无实质内容 → None）
       - 体积上界（行数 / 每行字符）
    C. build_feedback_compression_section：
       - 关键信息不丢（错误类型 / 行号+源码 / 变异摘要 / 得分）
       - None / 空 → 空串；section_chars 回填；总字符上限硬截断
    D. _generator_node 接线门控：
       - 默认关零变化（feedback_compression_section=None + update 恒 None）
       - 开启注入（段落含关键信息 + state 持久化 + section_chars 一致）
       - ORACLE_CONTEXT_TIER=minimal 消融档不注入
    E. generator.generate() 注入与门控（None 不注入 / 非空追加）
    F. state schema 守卫（compressed_feedback 已声明 + 初始 None，
       防 O35「未声明键被 LangGraph 静默丢弃」回归）
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.tools.feedback_compression import (
    _line_chars,
    _max_lines,
    _max_mutants,
    _max_section_chars,
    _max_tests,
    _mutant_chars,
    build_compressed_feedback,
    build_feedback_compression_section,
    feedback_compression_enabled,
)

# ─── 测试数据（4 行被测代码 + pytest 失败输出夹具）─────────────────────────

_TARGET_CODE = "def divide(a, b):\n    if b == 0:\n        raise ValueError('zero')\n    return a / b\n"

# 完整帧 traceback：最深层帧指向被测模块 /repo/mod.py 第 3 行
_TRACEBACK_OUTPUT = (
    "FAILED test_mod.py::test_divide_by_zero - ValueError: zero\n"
    "============================== short test summary info ===============================\n"
    "Traceback (most recent call last):\n"
    '  File "test_mod.py", line 8, in test_divide_by_zero\n'
    "    divide(1, 0)\n"
    '  File "/repo/mod.py", line 3, in divide\n'
    "    raise ValueError('zero')\n"
    "ValueError: zero\n"
)

# 跨文件场景：最深层帧在第三方库（decoder.py），与被测模块 mod 不符
_CROSS_FILE_OUTPUT = (
    "FAILED test_mod.py::test_x - AttributeError: 'NoneType' object has no attribute 'decode'\n"
    '  File "test_mod.py", line 8, in test_x\n'
    '  File "/usr/lib/python3.14/json/decoder.py", line 337, in decode\n'
)

# 越界场景：traceback 行号 99 超出 4 行被测代码
_OUT_OF_RANGE_OUTPUT = (
    "FAILED test_mod.py::test_x - ValueError: zero\n"
    '  File "test_mod.py", line 8, in test_x\n'
    '  File "/repo/mod.py", line 99, in divide\n'
)


def _base_state(**overrides):
    """构造最小可压缩 state（含失败用例；无 traceback / 快照 / 变异反馈）。"""
    state = {
        "target_code": _TARGET_CODE,
        "module_name": "mod",
        "failed_cases": [
            {"name": "test_divide_by_zero", "error": "ValueError: zero"},
            {"name": "test_divide_negative", "error": "AssertionError: expected -1"},
        ],
    }
    state.update(overrides)
    return state


def _probe_snapshot(line: int = 4) -> dict:
    """运行时探针快照（frames[0] = 异常抛出点帧，与 _locate_repair_focus_from_probe 同口径）。"""
    return {
        "success": True,
        "error": "",
        "frames": [
            {"function": "divide", "file": "/repo/mod.py", "line": line, "locals": {"a": "1", "b": "0"}},
        ],
    }


def _fl_focus(*lines_with_scores) -> dict:
    """FL_spectral Top-k 产物（分数降序）。"""
    return {
        "top_k": [{"line": ln, "score": sc} for ln, sc in lines_with_scores],
        "total_candidates": len(lines_with_scores),
    }


# ─── A. 开关与体积参数解析 ─────────────────────────────────────────────────


class TestSwitches:
    """开关解析（默认 false / truthy / falsy）。"""

    def test_enabled_default_false(self, monkeypatch):
        monkeypatch.delenv("FEEDBACK_COMPRESSION_ENABLE", raising=False)
        assert feedback_compression_enabled() is False

    @pytest.mark.parametrize("value", ["true", "TRUE", "1", "on"])
    def test_enabled_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("FEEDBACK_COMPRESSION_ENABLE", value)
        assert feedback_compression_enabled() is True

    @pytest.mark.parametrize("value", ["false", "FALSE", "0", "off", "no", ""])
    def test_enabled_falsy_values(self, monkeypatch, value):
        monkeypatch.setenv("FEEDBACK_COMPRESSION_ENABLE", value)
        assert feedback_compression_enabled() is False


_ALL_PARAM_ENVS = (
    "FEEDBACK_COMPRESSION_MAX_LINES",
    "FEEDBACK_COMPRESSION_LINE_CHARS",
    "FEEDBACK_COMPRESSION_MAX_MUTANTS",
    "FEEDBACK_COMPRESSION_MUTANT_CHARS",
    "FEEDBACK_COMPRESSION_MAX_TESTS",
    "FEEDBACK_COMPRESSION_MAX_CHARS",
)


class TestParamParsing:
    """体积参数默认值 / 非法值回退 / 钳制区间。"""

    def test_defaults(self, monkeypatch):
        for env in _ALL_PARAM_ENVS:
            monkeypatch.delenv(env, raising=False)
        assert _max_lines() == 8
        assert _line_chars() == 200
        assert _max_mutants() == 5
        assert _max_tests() == 3
        assert _max_section_chars() == 4000

    @pytest.mark.parametrize("env", _ALL_PARAM_ENVS)
    def test_invalid_value_falls_back_to_default(self, monkeypatch, env):
        monkeypatch.setenv(env, "abc")
        # 非法值一律回退默认值（与项目既有 _xxx_max 助手同口径）
        assert _clamp_for(env) == _default_for(env)

    def test_clamped_high(self, monkeypatch):
        monkeypatch.setenv("FEEDBACK_COMPRESSION_MAX_LINES", "999")
        monkeypatch.setenv("FEEDBACK_COMPRESSION_MAX_TESTS", "99")
        monkeypatch.setenv("FEEDBACK_COMPRESSION_MAX_CHARS", "99999")
        assert _max_lines() == 50  # 钳制到 [1, 50] 上界
        assert _max_tests() == 10  # 钳制到 [0, 10] 上界
        assert _max_section_chars() == 20000  # 钳制到 [500, 20000] 上界

    def test_clamped_low(self, monkeypatch):
        monkeypatch.setenv("FEEDBACK_COMPRESSION_MAX_LINES", "0")
        monkeypatch.setenv("FEEDBACK_COMPRESSION_MAX_TESTS", "-5")
        monkeypatch.setenv("FEEDBACK_COMPRESSION_MAX_MUTANTS", "0")
        monkeypatch.setenv("FEEDBACK_COMPRESSION_MAX_CHARS", "100")
        assert _max_lines() == 1  # 钳制到 [1, 50] 下界（防「只传一个行号」的信息损失）
        assert _max_tests() == 0  # [0, 10] 下界 = 允许关闭失败测试名
        assert _max_mutants() == 0  # [0, 20] 下界 = 允许关闭变异摘要
        assert _max_section_chars() == 500  # 钳制到 [500, 20000] 下界


def _default_for(env: str) -> int:
    """参数默认值表（与模块常量一一对应，防钳制测试漂移）。"""
    return {
        "FEEDBACK_COMPRESSION_MAX_LINES": 8,
        "FEEDBACK_COMPRESSION_LINE_CHARS": 200,
        "FEEDBACK_COMPRESSION_MAX_MUTANTS": 5,
        "FEEDBACK_COMPRESSION_MUTANT_CHARS": 120,
        "FEEDBACK_COMPRESSION_MAX_TESTS": 3,
        "FEEDBACK_COMPRESSION_MAX_CHARS": 4000,
    }[env]


def _clamp_for(env: str) -> int:
    """env 名 → 对应解析函数（防测试与模块常量漂移）。"""
    return {
        "FEEDBACK_COMPRESSION_MAX_LINES": _max_lines,
        "FEEDBACK_COMPRESSION_LINE_CHARS": _line_chars,
        "FEEDBACK_COMPRESSION_MAX_MUTANTS": _max_mutants,
        "FEEDBACK_COMPRESSION_MUTANT_CHARS": _mutant_chars,
        "FEEDBACK_COMPRESSION_MAX_TESTS": _max_tests,
        "FEEDBACK_COMPRESSION_MAX_CHARS": _max_section_chars,
    }[env]()


# ─── B. build_compressed_feedback ──────────────────────────────────────────


class TestBuildCompressedFeedback:
    """压缩反馈构建：候选行定位 / 跨文件保护 / 截断 / 降级。"""

    def test_traceback_path_locates_target_module_frame(self):
        out = build_compressed_feedback(_base_state(test_output=_TRACEBACK_OUTPUT))
        assert out is not None
        lines = out["target_lines"]
        assert len(lines) == 1
        assert lines[0]["lineno"] == 3
        assert lines[0]["origin"] == "traceback"
        assert lines[0]["source"] == "        raise ValueError('zero')"
        assert out["failed_tests"] == ["test_divide_by_zero", "test_divide_negative"]
        assert out["error_category"] == "unknown"  # state 无 error_category 时保守缺省
        assert out["survived_mutants"] == []
        assert out["mutation_score"] is None

    def test_probe_path_throw_point(self):
        out = build_compressed_feedback(_base_state(runtime_probe_snapshot=_probe_snapshot(4)))
        assert out is not None
        lines = out["target_lines"]
        assert len(lines) == 1
        assert lines[0]["lineno"] == 4
        assert lines[0]["origin"] == "probe"
        assert lines[0]["source"] == "    return a / b"

    def test_fl_spectral_path_multiple_lines(self):
        out = build_compressed_feedback(_base_state(fl_spectral_focus=_fl_focus((2, 0.9), (4, 0.5))))
        assert out is not None
        lines = out["target_lines"]
        assert [item["lineno"] for item in lines] == [2, 4]  # 按行号升序展示
        assert {item["origin"] for item in lines} == {"fl_spectral"}
        assert lines[0]["source"] == "    if b == 0:"

    def test_three_paths_coexist_with_priority_dedup(self):
        """probe / FL / traceback 三路并存；probe 对重复行先到先得，行号升序展示。"""
        state = _base_state(
            test_output=_TRACEBACK_OUTPUT,
            runtime_probe_snapshot=_probe_snapshot(4),
            fl_spectral_focus=_fl_focus((2, 0.9), (4, 0.5)),
        )
        out = build_compressed_feedback(state)
        by_line = {item["lineno"]: item for item in out["target_lines"]}
        assert set(by_line) == {2, 3, 4}
        assert by_line[4]["origin"] == "probe"  # probe 先于 fl_spectral 收集，去重胜出
        assert by_line[2]["origin"] == "fl_spectral"
        assert by_line[3]["origin"] == "traceback"

    def test_cross_file_protection_drops_foreign_frame(self):
        """最深层帧在第三方库（basename 与 target_module 不符）→ 丢弃该候选行。"""
        out = build_compressed_feedback(_base_state(test_output=_CROSS_FILE_OUTPUT))
        assert out is not None
        assert out["target_lines"] == []  # 宁缺勿误：不定位到第三方库帧
        assert out["failed_tests"]  # 其余字段照常提取（保守降级而非整体放弃）

    def test_line_out_of_range_keeps_record_with_empty_source(self):
        """行号越界（观测与当前代码不同版本）→ 保留行号记录、source 空串，不崩。"""
        out = build_compressed_feedback(_base_state(test_output=_OUT_OF_RANGE_OUTPUT))
        assert out is not None
        assert out["target_lines"] == [{"lineno": 99, "source": "", "origin": "traceback"}]

    def test_empty_target_code_yields_empty_source(self):
        out = build_compressed_feedback(_base_state(target_code="", test_output=_TRACEBACK_OUTPUT))
        assert out is not None
        assert out["target_lines"][0]["source"] == ""

    def test_failed_tests_capped_at_max(self):
        cases = [{"name": f"test_{i}", "error": "e"} for i in range(6)]
        out = build_compressed_feedback(_base_state(failed_cases=cases))
        assert out["failed_tests"] == ["test_0", "test_1", "test_2"]

    def test_mutation_summary_capped_and_truncated(self):
        long_desc = "x" * 300
        feedback = {
            "available": True,
            "survived_mutants": [
                long_desc,
                "return a / b 改写为 return a（return_void）",
                "d2",
                "d3",
                "d4",
                "d5",
                "d6",
            ],
            "mutation_score": 0.4,
        }
        out = build_compressed_feedback(_base_state(mutation_feedback=feedback))
        assert len(out["survived_mutants"]) == 5  # 默认上限 5 条
        assert out["survived_mutants"][0] == "x" * 120  # 单条截断至 120 字符
        assert out["mutation_score"] == 0.4  # 得分透传不截断

    def test_error_category_passthrough(self):
        out = build_compressed_feedback(_base_state(error_category="assertion"))
        assert out["error_category"] == "assertion"

    def test_mutation_score_bool_not_treated_as_number(self):
        """mutation_score=True（异常值）不应被当成 1.0 透传（bool 是 int 子类）。"""
        out = build_compressed_feedback(
            _base_state(mutation_feedback={"survived_mutants": ["m"], "mutation_score": True})
        )
        assert out["mutation_score"] is None

    def test_degrade_empty_state_returns_none(self):
        assert build_compressed_feedback({}) is None

    def test_degrade_only_error_category_returns_none(self):
        """仅错误类型无实质内容（无失败测试 / 无涉及行 / 无变异摘要）→ 不注入。"""
        assert build_compressed_feedback({"error_category": "assertion"}) is None

    def test_degrade_malformed_snapshot_no_crash(self):
        """快照结构畸形（frames 非 list / 首帧非 dict）→ 静默跳过该路，不崩。"""
        state = _base_state(runtime_probe_snapshot={"frames": "not-a-list"})
        out = build_compressed_feedback(state)
        assert out is not None and out["target_lines"] == []
        state2 = _base_state(runtime_probe_snapshot={"frames": ["not-a-dict"]})
        out2 = build_compressed_feedback(state2)
        assert out2 is not None and out2["target_lines"] == []

    def test_max_lines_truncation(self, monkeypatch):
        monkeypatch.setenv("FEEDBACK_COMPRESSION_MAX_LINES", "2")
        state = _base_state(fl_spectral_focus=_fl_focus((2, 0.9), (4, 0.8), (1, 0.7)))
        out = build_compressed_feedback(state)
        assert [item["lineno"] for item in out["target_lines"]] == [1, 2]  # 升序后截断

    def test_line_chars_truncation(self, monkeypatch):
        monkeypatch.setenv("FEEDBACK_COMPRESSION_LINE_CHARS", "20")
        state = _base_state(fl_spectral_focus=_fl_focus((3, 0.9)))
        out = build_compressed_feedback(state)
        # 源码行 "        raise ValueError('zero')" 截断至前 20 字符
        assert out["target_lines"][0]["source"] == "        raise ValueE"
        assert len(out["target_lines"][0]["source"]) == 20

    def test_line_chars_clamped_to_floor(self, monkeypatch):
        """LINE_CHARS 下限 20：配置 5（低于下限）→ 钳制为 20，防「只传几个字符」的信息损失。"""
        monkeypatch.setenv("FEEDBACK_COMPRESSION_LINE_CHARS", "5")
        state = _base_state(fl_spectral_focus=_fl_focus((3, 0.9)))
        out = build_compressed_feedback(state)
        assert len(out["target_lines"][0]["source"]) == 20


# ─── C. build_feedback_compression_section ─────────────────────────────────


class TestBuildSection:
    """渲染：关键信息不丢 / 空输入 / section_chars 回填 / 总字符上限。"""

    def test_none_and_empty_return_empty(self):
        assert build_feedback_compression_section(None) == ""
        assert build_feedback_compression_section({}) == ""

    def test_key_info_preserved(self):
        """关键信息四断言：错误类型 / 失败测试 / 行号+源码 / 变异摘要+得分。"""
        compressed = build_compressed_feedback(
            _base_state(
                test_output=_TRACEBACK_OUTPUT,
                error_category="runtime",
                mutation_feedback={
                    "survived_mutants": ["return a / b 改写为 return a（return_void）"],
                    "mutation_score": 0.4,
                },
            )
        )
        section = build_feedback_compression_section(compressed)
        assert "错误类型：runtime" in section
        assert "test_divide_by_zero" in section
        assert "第 3 行" in section
        assert "raise ValueError('zero')" in section
        assert "涉及源代码行" in section
        assert "存活变异体摘要" in section
        assert "return a / b 改写为 return a（return_void）" in section
        assert "当前变异得分 0.4" in section
        # section_chars 回填 = 实际渲染字符数（观测字段，实验层量上界用）
        assert compressed["section_chars"] == len(section)

    def test_default_bounds_within_max_chars(self):
        """默认参数下段落不超过 FEEDBACK_COMPRESSION_MAX_CHARS=4000。"""
        compressed = build_compressed_feedback(
            _base_state(
                test_output=_TRACEBACK_OUTPUT,
                fl_spectral_focus=_fl_focus(*[(i, 1.0 - i / 100) for i in range(1, 9)]),
                mutation_feedback={"survived_mutants": [f"m{i}" for i in range(8)], "mutation_score": 0.4},
            )
        )
        section = build_feedback_compression_section(compressed)
        assert 0 < len(section) <= 4000

    def test_total_chars_cap_hard_truncates(self, monkeypatch):
        """极端配置下段落总字符硬截断（≤ 上限，省略号标记）。"""
        monkeypatch.setenv("FEEDBACK_COMPRESSION_MAX_CHARS", "500")
        compressed = {
            "schema_version": 1,
            "error_category": "runtime",
            "failed_tests": ["t1", "t2", "t3"],
            "target_lines": [{"lineno": i, "source": "s" * 200, "origin": "fl_spectral"} for i in range(1, 9)],
            "survived_mutants": ["m" * 120 for _ in range(5)],
            "mutation_score": 0.4,
            "section_chars": 0,
        }
        section = build_feedback_compression_section(compressed)
        assert len(section) == 500
        assert section.endswith("…")
        assert compressed["section_chars"] == 500

    def test_empty_lists_render_header_only(self):
        """无行无变异（仅失败测试）时仍渲染头部与失败测试（信息不丢）。"""
        compressed = build_compressed_feedback(_base_state(test_output=_CROSS_FILE_OUTPUT))
        section = build_feedback_compression_section(compressed)
        assert "【压缩反馈（观测级行粒度压缩）】" in section
        assert "涉及源代码行" not in section
        assert "存活变异体摘要" not in section


# ─── D. _generator_node 接线门控 ───────────────────────────────────────────


def _node_state(**overrides) -> dict:
    """_generator_node 的最小 state（含失败观测，供压缩通道提取）。"""
    state = {
        "target_code": _TARGET_CODE,
        "target_function": "divide",
        "module_name": "mod",
        "iteration": 0,
        "max_iterations": 3,
        "failed_cases": [{"name": "test_divide_by_zero", "error": "ValueError: zero"}],
        "test_output": _TRACEBACK_OUTPUT,
        "error_category": "runtime",
    }
    state.update(overrides)
    return state


def _run_generator_node(monkeypatch, state: dict):
    """跑 _generator_node（Agent 全 mock），捕获传给 generate 的 kwargs 与 update。"""
    from src.graph import nodes as _nodes

    captured: dict = {}

    class _FakeAgent:
        def generate(self, *args, **kwargs):
            captured.update(kwargs)
            return "def test_x():\n    assert True\n"

    monkeypatch.setattr(_nodes, "get_or_create_agent", lambda cls: _FakeAgent())
    update = _nodes._generator_node(state)
    return captured, update


class TestGeneratorNodeWiring:
    """_generator_node 接线：默认关零变化 / 开启注入 / minimal 消融档。"""

    def test_default_off_zero_change(self, monkeypatch):
        """默认关（ADR-0003）：generate 不收段落，update 恒 None（历史口径零变化）。"""
        monkeypatch.delenv("FEEDBACK_COMPRESSION_ENABLE", raising=False)
        captured, update = _run_generator_node(monkeypatch, _node_state())
        assert captured.get("feedback_compression_section") is None
        assert update.get("compressed_feedback") is None

    def test_enabled_injects_and_persists(self, monkeypatch):
        monkeypatch.setenv("FEEDBACK_COMPRESSION_ENABLE", "true")
        captured, update = _run_generator_node(monkeypatch, _node_state())
        section = captured.get("feedback_compression_section")
        assert section
        assert "【压缩反馈（观测级行粒度压缩）】" in section
        assert "错误类型：runtime" in section
        assert "第 3 行" in section
        persisted = update.get("compressed_feedback")
        assert persisted is not None
        assert persisted["section_chars"] == len(section)

    def test_ctx_minimal_ablation_no_injection(self, monkeypatch):
        """ORACLE_CONTEXT_TIER=minimal 消融档：增强段全剥离，不注入（与 O3 同口径）。"""
        monkeypatch.setenv("FEEDBACK_COMPRESSION_ENABLE", "true")
        monkeypatch.setenv("ORACLE_CONTEXT_TIER", "minimal")
        captured, update = _run_generator_node(monkeypatch, _node_state())
        assert captured.get("feedback_compression_section") is None
        assert update.get("compressed_feedback") is None

    def test_enabled_but_no_failure_observation_no_injection(self, monkeypatch):
        """开启但无失败观测（无失败用例 / 无 traceback / 无变异反馈）→ 保守不注入。

        段落值为 None / 空串均属「不注入」（generate() 对空串不追加 query，
        与 O3 分支覆盖段落同一口径），此处锁定 falsy 即可。
        """
        monkeypatch.setenv("FEEDBACK_COMPRESSION_ENABLE", "true")
        state = _node_state(failed_cases=[], test_output="all tests passed\n", error_category=None)
        captured, update = _run_generator_node(monkeypatch, state)
        assert not captured.get("feedback_compression_section")
        assert update.get("compressed_feedback") is None


# ─── E. generator.generate() 注入与门控 ────────────────────────────────────


def _real_gen_with_mocked_llm():
    """真实 GeneratorAgent + mock LLM（与 tests/test_generator_pure_logic.py 同口径）。"""
    from src.agents.generator import GeneratorAgent

    gen = GeneratorAgent()
    gen._call_llm_with_cache = MagicMock(return_value="raw")
    gen._extract_python_code = MagicMock(return_value="def test_x():\n    pass\n")
    gen._validate_parametrize = MagicMock(return_value=True)
    gen._fix_import_module = MagicMock(side_effect=lambda c, m: c)
    return gen


class TestGenerateInjection:
    """generate() 的压缩反馈段落注入与门控（默认 None 不注入）。"""

    def test_none_section_not_injected(self):
        gen = _real_gen_with_mocked_llm()
        gen.generate({"name": "t"}, "code", "m", None, feedback_compression_section=None)
        called_query = gen._call_llm_with_cache.call_args[0][0]
        assert "压缩反馈" not in called_query

    def test_empty_string_section_not_injected(self):
        gen = _real_gen_with_mocked_llm()
        gen.generate({"name": "t"}, "code", "m", None, feedback_compression_section="")
        called_query = gen._call_llm_with_cache.call_args[0][0]
        assert "压缩反馈" not in called_query

    def test_section_appended_to_query(self):
        gen = _real_gen_with_mocked_llm()
        gen.generate(
            {"name": "t"}, "code", "m", None, feedback_compression_section="【压缩反馈（观测级行粒度压缩）】第 3 行"
        )
        called_query = gen._call_llm_with_cache.call_args[0][0]
        assert "【压缩反馈（观测级行粒度压缩）】第 3 行" in called_query


# ─── F. state schema 守卫 ──────────────────────────────────────────────────


class TestStateSchemaGuard:
    """compressed_feedback 必须显式声明于 TypedDict 且初始 None（O35 静默丢弃教训）。"""

    def test_declared_in_typeddict(self):
        from src.graph.state import AITesterState

        assert "compressed_feedback" in AITesterState.__annotations__

    def test_initial_state_none(self):
        from src.graph.state import create_initial_state

        state = create_initial_state(
            task_uuid="t",
            target_file="/tmp/mod.py",
            target_code=_TARGET_CODE,
            max_iterations=3,
        )
        assert state["compressed_feedback"] is None
