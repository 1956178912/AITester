"""env_flag / env_int 单一事实源单测（2026-10-16 C 轮去重 + F 轮加固）。

锁定口径：
1. 与历史惯用法 ``os.getenv(NAME, "false").lower() in ("true","1","on")``
   的**逐字节行为等价**（未设置→默认；已设置→接受集判定；空串→False）；
2. 空白容忍（项目新开关多数惯例，见 env_utils docstring 披露）；
3. 扩展集必须显式声明（"yes" 不在默认集——防口径隐式分裂）；
4. 大小写不敏感；
5. F 轮：``env_int`` 与 ``config.py::_parse_int_env`` 同口径（坏值/越界记
   WARNING 回退，绝不抛异常），且三处模块级常量在坏值下仍可导入。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.utils.env_utils import env_flag, env_int


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


@pytest.mark.unit
class TestEnvInt:
    """env_int 容错口径（与 config.py::_parse_int_env 逐条对齐）。"""

    def test_unset_returns_default(self, monkeypatch):
        monkeypatch.delenv("AITESTER_TEST_INT", raising=False)
        assert env_int("AITESTER_TEST_INT", 7) == 7

    def test_empty_string_returns_default(self, monkeypatch):
        monkeypatch.setenv("AITESTER_TEST_INT", "   ")
        assert env_int("AITESTER_TEST_INT", 7) == 7

    def test_valid_value_with_whitespace(self, monkeypatch):
        monkeypatch.setenv("AITESTER_TEST_INT", " 42 ")
        assert env_int("AITESTER_TEST_INT", 7) == 42

    def test_negative_value_preserved_without_bounds(self, monkeypatch):
        # 行为等价纪律：不传 lo/hi 时不做任何钳制（与裸 int() 对合法值同结果）
        monkeypatch.setenv("AITESTER_TEST_INT", "-3")
        assert env_int("AITESTER_TEST_INT", 7) == -3

    @pytest.mark.parametrize("raw", ["abc", "1.5", "0x10", "true", "12abc", "-", "+"])
    def test_bad_values_fall_back_never_raise(self, monkeypatch, raw):
        monkeypatch.setenv("AITESTER_TEST_INT", raw)
        assert env_int("AITESTER_TEST_INT", 7) == 7

    def test_bad_value_logs_warning(self, monkeypatch, caplog):
        monkeypatch.setenv("AITESTER_TEST_INT", "abc")
        with caplog.at_level(logging.WARNING, logger="src.utils.env_utils"):
            assert env_int("AITESTER_TEST_INT", 7) == 7
        assert "AITESTER_TEST_INT" in caplog.text
        assert "不是合法整数" in caplog.text

    def test_below_lo_falls_back(self, monkeypatch):
        monkeypatch.setenv("AITESTER_TEST_INT", "0")
        assert env_int("AITESTER_TEST_INT", 7, lo=1) == 7

    def test_above_hi_falls_back(self, monkeypatch):
        monkeypatch.setenv("AITESTER_TEST_INT", "99")
        assert env_int("AITESTER_TEST_INT", 7, hi=50) == 7

    def test_in_range_kept(self, monkeypatch):
        monkeypatch.setenv("AITESTER_TEST_INT", "30")
        assert env_int("AITESTER_TEST_INT", 7, lo=1, hi=50) == 30

    def test_out_of_range_logs_warning(self, monkeypatch, caplog):
        monkeypatch.setenv("AITESTER_TEST_INT", "99")
        with caplog.at_level(logging.WARNING, logger="src.utils.env_utils"):
            assert env_int("AITESTER_TEST_INT", 7, hi=50) == 7
        assert "超出范围" in caplog.text


@pytest.mark.unit
class TestModuleLevelNumericEnvHardening:
    """F 轮缺陷锁：三处模块级常量在坏值下必须仍可导入（此前 import 期崩溃）。

    缺陷形态：``_CFG_SUMMARY_MAX_CHARS = int(os.getenv(...))`` 等在**模块级**
    求值，``CFG_SUMMARY_MAX_CHARS=abc`` 会让 ``import src.tools.control_flow``
    直接抛 ValueError；而该模块被 planner.py 顶层导入，故障面向上扩散。
    本测试在子进程里以三个坏值同时导入两个模块，锁定"坏值 → WARNING + 回退
    默认值 + 导入成功"。
    """

    def test_bad_numeric_env_does_not_break_import(self):
        repo = Path(__file__).resolve().parents[1]
        code = (
            "import src.tools.control_flow as cf\n"
            "import src.graph.nodes as nd\n"
            "assert cf._CFG_SUMMARY_MAX_CHARS == 1500, cf._CFG_SUMMARY_MAX_CHARS\n"
            "assert cf._PATH_MAX_DEFAULT == 32, cf._PATH_MAX_DEFAULT\n"
            "assert nd.CODE_FOCUS_DEPTH == 1, nd.CODE_FOCUS_DEPTH\n"
            "print('OK')\n"
        )
        env = {
            **os.environ,  # 保留 HOME 等（config.py 的缓存目录解析依赖）
            "CFG_SUMMARY_MAX_CHARS": "abc",
            "PATH_ENUM_MAX_PATHS": "not-a-number",
            "CODE_FOCUS_DEPTH": "",
        }
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        assert proc.returncode == 0, proc.stderr[-800:]
        assert "OK" in proc.stdout
