"""env_flag / env_flag_opt_out / env_int / env_float 单一事实源单测（C 轮去重 + F 轮加固 + J 轮补口）。

锁定口径：
1. 与历史惯用法 ``os.getenv(NAME, "false").lower() in ("true","1","on")``
   的**逐字节行为等价**（未设置→默认；已设置→接受集判定；空串→False）；
2. 空白容忍（项目新开关多数惯例，见 env_utils docstring 披露）；
3. 扩展集必须显式声明（"yes" 不在默认集——防口径隐式分裂）；
4. 大小写不敏感；
5. F 轮：``env_int`` 与 ``config.py::_parse_int_env`` 同口径（坏值/越界记
   WARNING 回退，绝不抛异常），且三处模块级常量在坏值下仍可导入；
6. J-1d：``env_float`` 与 ``config._parse_float_env`` 逐条对齐，**含 NaN/±inf
   非有限值回退**（只做范围检查会让坏阈值静默穿透）；J-1d 站点级锁定 5 处
   rlimit 数值开关在垃圾值下不抛异常、不静默归零；
7. J-2：``env_flag_opt_out`` 负集 + fail-closed（垃圾值保持启用），且 6 个
   已收敛站点对同一取值结果**逐值一致**——这是布尔口径统一的真正产物。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.utils.env_utils import env_flag, env_flag_opt_out, env_float, env_int, postprocess_warn_seconds


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
class TestEnvFlagOptOut:
    """env_flag_opt_out 负集口径：显式关闭才算关，其余一切值保持启用。

    与 :class:`TestEnvFlagEquivalence` 的唯一口径分歧在**垃圾值方向**：
    正集口径把 ``=ture`` 读成 False（对守卫类开关等于"拼错一个字母即静默
    关掉保护"），负集口径把它读成 True（G 轮为守卫类开关定的 fail-closed 调）。
    """

    @pytest.mark.parametrize("raw", ["false", "FALSE", "False", "0", "off", "OFF", " 0 ", " false \n"])
    def test_off_set_values_disable(self, monkeypatch, raw):
        # 关闭集 = ("false", "0", "off")，与 _DEFAULT_TRUE 逐项对偶；大小写不敏感 + 空白容忍
        monkeypatch.setenv("AITESTER_TEST_OPT_OUT", raw)
        assert env_flag_opt_out("AITESTER_TEST_OPT_OUT") is False

    @pytest.mark.parametrize("raw", ["ture", "tru", "no", "disable", "disabled", "2", "falsey", "1", "true", "on"])
    def test_garbage_and_non_off_values_keep_enabled(self, monkeypatch, raw):
        # fail-closed 方向：拼错的关闭值**不会**关掉守卫（与 env_flag 的关键分歧）
        monkeypatch.setenv("AITESTER_TEST_OPT_OUT", raw)
        assert env_flag_opt_out("AITESTER_TEST_OPT_OUT") is True

    def test_unset_is_enabled(self, monkeypatch):
        monkeypatch.delenv("AITESTER_TEST_OPT_OUT", raising=False)
        assert env_flag_opt_out("AITESTER_TEST_OPT_OUT") is True

    def test_empty_string_stays_enabled_matches_legacy_caliber(self, monkeypatch):
        # 显式空串不是关闭意图 → 保持启用。此点与**被替换前的主流手写口径**
        # （`not in ("0", "false", ...)`）逐字节一致，故非行为变更；与 env_flag
        # 的"空串→False"相反，属两类开关的天然分歧。
        monkeypatch.setenv("AITESTER_TEST_OPT_OUT", "")
        assert env_flag_opt_out("AITESTER_TEST_OPT_OUT") is True

    def test_returns_bool_type(self, monkeypatch):
        monkeypatch.setenv("AITESTER_TEST_OPT_OUT", "false")
        assert isinstance(env_flag_opt_out("AITESTER_TEST_OPT_OUT"), bool)

    def test_off_values_replaces_default_not_extends(self, monkeypatch):
        # 自定义关闭集是**替换**而非并集：传 ("no",) 后 "false" 不再算关闭
        monkeypatch.setenv("AITESTER_TEST_OPT_OUT", "no")
        assert env_flag_opt_out("AITESTER_TEST_OPT_OUT", off_values=("no",)) is False
        monkeypatch.setenv("AITESTER_TEST_OPT_OUT", "false")
        assert env_flag_opt_out("AITESTER_TEST_OPT_OUT", off_values=("no",)) is True

    def test_no_default_keyword(self):
        # 刻意不提供 default 参数：默认关的开关应改用 env_flag，
        # 否则 opt-out 语义（"未设置即启用"）被参数化为可选，等于没有开关。
        import inspect

        assert "default" not in inspect.signature(env_flag_opt_out).parameters


#: J-2 收敛后的 opt-out 开关站点（环境变量名 → 访问器 dotted path）。
#: 全仓 11 处调用点中，此处逐站点锁定有独立访问器的 7 处；另 3 处嵌在带副作用
#: 的流程里、无独立访问器：src/graph/agents_cache.py::_get_or_create_executor_agent、
#: src/agents/base_agent.py::_call_llm_with_cache、src/agents/executor_repo.py::verify。
_J2_OPT_OUT_SITES: list[tuple[str, str]] = [
    ("CFG_ANALYSIS_ENABLE", "src.tools.control_flow.cfg_analysis_enabled"),
    ("CONTEST_AST_SCAN_ENABLE", "src.tools.dependency.conftest_ast_scan_enabled"),
    ("EMPTY_PATCH_GUARD", "src.tools.patch_postprocess._empty_patch_guard_enabled"),
    ("PATCH_PROTECT_REPO_CORE", "src.graph.flags._repo_core_protection_enabled"),
    ("AITESTER_AGENT_REUSE", "src.graph.flags._agent_reuse_enabled"),
    ("EVENT_BUS_ENABLE", "src.graph.event_bus._event_bus_enabled"),
    ("DETECTION_FIRST_SECTION_ENABLE", "src.graph.nodes._detection_first_section_enabled"),
]


def _accessor(dotted: str):
    module_path, fn_name = dotted.rsplit(".", 1)
    return getattr(__import__(module_path, fromlist=[fn_name]), fn_name)


@pytest.mark.unit
class TestJ2OptOutSitesUniformCaliber:
    """J-2 的**真正产物**不是"都调 helper"，而是"同一句意图在不同开关上结果相同"。

    收敛前 11 处各抄一份负集，接受集互不相同（``("false","0")`` / ``("0","false")`` /
    ``("false","0","off")`` / 单值 ``"false"`` / 单值 ``"0"``，且 4 处漏 ``.lower()``）。
    下列测试把"跨站点逐值一致"钉成回归锁——任何一方再手写口径即红。
    """

    def test_site_count_matches_convergence(self):
        # 11 处收敛调用点中可独立取样的 7 处；少于 7 说明有站点被静默回退成手写口径
        assert len(_J2_OPT_OUT_SITES) == 7

    @pytest.mark.parametrize("env_name,dotted", _J2_OPT_OUT_SITES)
    def test_unset_enables(self, monkeypatch, env_name, dotted):
        monkeypatch.delenv(env_name, raising=False)
        assert _accessor(dotted)() is True

    @pytest.mark.parametrize("raw", ["false", "0", "OFF", " false "])
    @pytest.mark.parametrize("env_name,dotted", _J2_OPT_OUT_SITES)
    def test_explicit_off_disables_every_site(self, monkeypatch, env_name, dotted, raw):
        monkeypatch.setenv(env_name, raw)
        assert _accessor(dotted)() is False

    @pytest.mark.parametrize("raw", ["ture", "no", "", "1"])
    @pytest.mark.parametrize("env_name,dotted", _J2_OPT_OUT_SITES)
    def test_non_off_keeps_every_site_enabled(self, monkeypatch, env_name, dotted, raw):
        monkeypatch.setenv(env_name, raw)
        assert _accessor(dotted)() is True

    @pytest.mark.parametrize(
        "raw",
        ["", " ", "0", "1", "2", "no", "yes", "off", "OFF", "on", "true", "false", "FALSE", "ture", "None"],
    )
    def test_caliber_identical_across_sites(self, monkeypatch, raw):
        names = [n for n, _ in _J2_OPT_OUT_SITES]
        outcomes = []
        for env_name, dotted in _J2_OPT_OUT_SITES:
            monkeypatch.setenv(env_name, raw)
            outcomes.append(_accessor(dotted)())
        assert len(set(outcomes)) == 1, f"值 {raw!r} 在站点间口径分裂：{dict(zip(names, outcomes, strict=True))}"

    def test_two_legacy_misreads_now_honored(self, monkeypatch):
        # 收敛前的两个真实"显式关闭被静默忽略"：EMPTY_PATCH_GUARD 只认 "false"
        # （`=0` 无效），AITESTER_LLM_CACHE 只认 "0"（`=false` 无效）。
        from src.agents.llm_client import clear_llm_cache_option_memory

        monkeypatch.setenv("EMPTY_PATCH_GUARD", "0")
        assert _accessor("src.tools.patch_postprocess._empty_patch_guard_enabled")() is False
        clear_llm_cache_option_memory()
        monkeypatch.setenv("AITESTER_LLM_CACHE", "false")
        try:
            assert _accessor("src.agents.llm_client._llm_cache_enabled")() is False
        finally:
            clear_llm_cache_option_memory()


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
class TestEnvFloat:
    """env_float 容错口径（与 config.py::_parse_float_env 逐条对齐，含非有限值回退）。"""

    def test_unset_and_blank_return_default(self, monkeypatch):
        monkeypatch.delenv("AITESTER_TEST_FLT", raising=False)
        assert env_float("AITESTER_TEST_FLT", 0.95) == 0.95
        monkeypatch.setenv("AITESTER_TEST_FLT", "  ")
        assert env_float("AITESTER_TEST_FLT", 0.95) == 0.95

    def test_valid_and_integer_looked_value(self, monkeypatch):
        monkeypatch.setenv("AITESTER_TEST_FLT", " 2 ")
        assert env_float("AITESTER_TEST_FLT", 0.95) == 2.0

    @pytest.mark.parametrize("raw", ["abc", "0.92.1", "1e", "--0.5", "true", "2,5"])
    def test_bad_values_fall_back_never_raise(self, monkeypatch, raw):
        monkeypatch.setenv("AITESTER_TEST_FLT", raw)
        assert env_float("AITESTER_TEST_FLT", 0.95) == 0.95

    @pytest.mark.parametrize("raw", ["nan", "-nan", "inf", "-inf", "Infinity"])
    def test_non_finite_falls_back(self, monkeypatch, raw):
        """非有限值必须回退：nan 参与任何 </> 比较恒 False，越界检查拦不住它。"""
        monkeypatch.setenv("AITESTER_TEST_FLT", raw)
        assert env_float("AITESTER_TEST_FLT", 0.95) == 0.95

    def test_non_finite_and_bad_value_log_warning(self, monkeypatch, caplog):
        monkeypatch.setenv("AITESTER_TEST_FLT", "nan")
        with caplog.at_level(logging.WARNING, logger="src.utils.env_utils"):
            env_float("AITESTER_TEST_FLT", 0.95)
        assert "非有限值" in caplog.text
        caplog.clear()
        monkeypatch.setenv("AITESTER_TEST_FLT", "abc")
        with caplog.at_level(logging.WARNING, logger="src.utils.env_utils"):
            env_float("AITESTER_TEST_FLT", 0.95)
        assert "不是合法浮点数" in caplog.text

    def test_out_of_range_falls_back_in_range_kept(self, monkeypatch):
        monkeypatch.setenv("AITESTER_TEST_FLT", "1.5")
        assert env_float("AITESTER_TEST_FLT", 0.95, lo=0.0, hi=1.0) == 0.95
        monkeypatch.setenv("AITESTER_TEST_FLT", "0.4")
        assert env_float("AITESTER_TEST_FLT", 0.95, lo=0.0, hi=1.0) == 0.4

    def test_bounds_none_side_unlimited(self, monkeypatch):
        """lo/hi 单侧省略时另一侧不限制——不传 bounds 即与裸 float() 同结果。"""
        monkeypatch.setenv("AITESTER_TEST_FLT", "-100")
        assert env_float("AITESTER_TEST_FLT", 0.95, hi=1.0) == -100.0
        monkeypatch.setenv("AITESTER_TEST_FLT", "-100")
        assert env_float("AITESTER_TEST_FLT", 0.95, lo=0.0) == 0.95


@pytest.mark.unit
class TestJ1dBareNumericSites:
    """J-1d 缺陷锁：原裸 int()/float() 的站点在坏值下不得再抛。

    根因（比"崩溃"更糟的形态）：`_make_resource_preexec_fn()` 位于判分路径的
    `try:` 内，坏值抛的 ValueError 会被同处的 `except Exception` 吞成
    ("UNAVAILABLE", …)——整批执行判分静默归零，日志只剩"第 N 次执行失败"。
    """

    _RLIMIT_ENVS = (
        "EXECUTOR_RLIMIT_CPU",
        "EXECUTOR_RLIMIT_AS_MB",
        "EXECUTOR_RLIMIT_NPROC",
        "EXECUTOR_RLIMIT_FSIZE_MB",
        "EXECUTOR_RLIMIT_NOFILE",
    )

    @pytest.mark.parametrize("raw", ["30s", "", "abc", "-1", "nan", "1e999"])
    def test_rlimit_factory_never_raises_on_garbage(self, monkeypatch, raw):
        import src.agents.executor_runtime as er

        for name in self._RLIMIT_ENVS:
            monkeypatch.setenv(name, raw)
        fn = er._make_resource_preexec_fn()  # 此前：ValueError（负值另伪装成 SubprocessError）
        assert fn is None or callable(fn)

    def test_rlimit_garbage_falls_back_to_restrictive_defaults(self, monkeypatch):
        resource = pytest.importorskip("resource")
        import src.agents.executor_runtime as er

        if er._make_resource_preexec_fn() is None:
            pytest.skip("非 POSIX：无 resource 模块（历史口径）")
        monkeypatch.setenv("EXECUTOR_RLIMIT_CPU", "30s")
        monkeypatch.setenv("EXECUTOR_RLIMIT_NPROC", "-1")
        monkeypatch.setenv("EXECUTOR_RLIMIT_AS_MB", "512")
        monkeypatch.setattr(er, "_IS_DARWIN", False)
        recorded: dict[str, tuple[int, int]] = {}
        names = {
            resource.RLIMIT_CPU: "CPU",
            resource.RLIMIT_AS: "AS",
            resource.RLIMIT_NPROC: "NPROC",
            resource.RLIMIT_FSIZE: "FSIZE",
            resource.RLIMIT_NOFILE: "NOFILE",
        }
        fn = er._make_resource_preexec_fn()
        assert fn is not None

        def _spy(which, lim):
            recorded[names.get(which, str(which))] = lim

        with patch.object(resource, "setrlimit", side_effect=_spy):
            fn()
        assert recorded["CPU"] == (300, 300), "坏值必须回退默认上限，不得静默放宽"
        assert recorded["NPROC"] == (512, 512)
        assert recorded["AS"] == (512 * 1024 * 1024, 512 * 1024 * 1024)


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


@pytest.mark.unit
class TestPostprocessWarnSeconds:
    """Q-3 `postprocess_warn_seconds` 的取值口径（CQ 轮补）。

    为什么补在**这个文件**：每周自变异门禁（`.github/workflows/mutation.yml`）的
    `--test-map` 把 `src/utils/env_utils.py` 映射到 `tests/test_env_utils.py` +
    `tests/test_self_mutation_targets.py`，自动发现只匹配 `test_<stem>.py`。
    该函数 2026-10-18 加入时没有任何测试落在这个映射面里——门禁从上线起就红
    （实测 env_utils 0.7273 / atomic_io 0.8000、合计 0.7467 < 0.85），
    其中 10 个存活变异体全部落在本函数与它读取的环境变量名上。

    口径（与 `build_postprocess_wall` 的 `warn_s` 一致）：未设置 / 空串 / 全空白 /
    非数值 / NaN / ±inf / ≤0 → `default`；合法正有限数 → 该值。
    """

    ENV = "AITESTER_POSTPROCESS_WARN_S"

    def test_unset_returns_builtin_default(self, monkeypatch):
        monkeypatch.delenv(self.ENV, raising=False)
        assert postprocess_warn_seconds() == 600.0

    def test_unset_honours_caller_default(self, monkeypatch):
        """调用方显式给 default 时必须回它——而不是硬编码 600。"""
        monkeypatch.delenv(self.ENV, raising=False)
        assert postprocess_warn_seconds(default=42.5) == 42.5

    @pytest.mark.parametrize("raw", ["", "   ", "abc", "NaN", "nan", "inf", "-inf", "0", "-1", "0.0"])
    def test_bad_values_fall_back_to_caller_default(self, monkeypatch, raw):
        monkeypatch.setenv(self.ENV, raw)
        assert postprocess_warn_seconds(default=42.5) == 42.5

    @pytest.mark.parametrize(
        "raw,expected", [("300", 300.0), ("120.5", 120.5), (" 120 ", 120.0), ("1e3", 1000.0), ("0.5", 0.5)]
    )
    def test_valid_positive_values_pass_through(self, monkeypatch, raw, expected):
        monkeypatch.setenv(self.ENV, raw)
        assert postprocess_warn_seconds(default=42.5) == expected

    def test_env_name_literal_is_the_contract(self, monkeypatch):
        """名字本身是契约：常量被改名/改字面量后，带字面量名的环境变量必须仍被读到。"""
        monkeypatch.delenv(self.ENV, raising=False)
        monkeypatch.setenv("AITESTER_POSTPROCESS_WARN_S", "777")
        assert postprocess_warn_seconds() == 777.0
