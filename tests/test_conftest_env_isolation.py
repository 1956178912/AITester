"""H 轮（2026-10-16）：tests/conftest.py 的档位预设 env 隔离兜底 —— 回归锁定。

被测缺陷（实测复现，非推演）：``config._apply_profile_presets()`` 在 import 期用
``os.environ.setdefault`` 注入档位开关，既绕过 monkeypatch 追踪也没有 teardown。
两处测试文件各自手抄还原清单，均已过期，导致 6 个键跨测试残留：

    {'SPEC_SMT_ENABLE': 'true', 'LOGIC_SPEC_STRICT_FALLBACK_ENABLE': 'true',
     'DETECTION_SPECIFICITY_GATE_ENABLE': 'true', 'RED_REGRESSION_GATE_ENABLE': 'true',
     'FL_SPECTRAL_ENABLE': 'true', 'MUTATION_ADVISOR_ENABLE': 'true'}

后果：后续测试走进"档位开启"分支 → **覆盖率测量非确定**（同一份源码连跑三次
src/graph/nodes.py 得 0.7776 / 0.7862 / 0.7776，总行覆盖在 92.94–92.96% 漂移，
登记册逐位对账无法收敛）；漂移全部落在特异性门块内 6 行。

本文件锁两件事：①兜底 fixture 的键集必须覆盖**全部**档位预设（新增开关自动纳入，
不需要任何人记得改测试）；②fixture 真的把注入还原掉。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator

import pytest

from config import _PROFILE_PRESETS
from tests.conftest import _PRESET_ENV_KEYS, _isolate_profile_presets

_PROBE_KEY = "DETECTION_SPECIFICITY_GATE_ENABLE"


def _underlying_fixture() -> Callable[[], Iterator[None]]:
    """取出 fixture 装饰器底下的裸生成器函数（直接驱动 setup/teardown）。

    pytest 9 暴露 ``__wrapped__`` 与 ``_fixture_function``。两者都拿不到时
    **报错而不是跳过**——静默跳过会让本文件长期假绿（G 轮 G1/G2 同类教训）。
    """
    fn = getattr(_isolate_profile_presets, "__wrapped__", None) or getattr(
        _isolate_profile_presets, "_fixture_function", None
    )
    assert fn is not None, "无法取得 _isolate_profile_presets 的裸函数（pytest 内部 API 变更？）"
    return fn


@pytest.mark.unit
class TestPresetKeySetCoverage:
    def test_every_profile_preset_key_is_in_the_restore_net(self) -> None:
        """任一档位的任一键都必须在兜底还原集里（漂移即红）。"""
        for profile, presets in _PROFILE_PRESETS.items():
            missing = set(presets) - _PRESET_ENV_KEYS
            assert not missing, f"AITESTER_PROFILE={profile} 的键未被 conftest 兜底覆盖：{sorted(missing)}"

    def test_profile_switch_itself_is_covered(self) -> None:
        """AITESTER_PROFILE 自身也在还原集内（它是注入的触发键）。"""
        assert "AITESTER_PROFILE" in _PRESET_ENV_KEYS

    def test_restore_net_has_no_unknown_keys(self) -> None:
        """反向：兜底集不得含凭空键（防"抄一份更大的清单"式假覆盖）。"""
        known = {"AITESTER_PROFILE", *(k for presets in _PROFILE_PRESETS.values() for k in presets)}
        assert set(_PRESET_ENV_KEYS) == known


@pytest.mark.unit
class TestFixtureRestoresInjection:
    def test_injection_during_test_is_reverted_at_teardown(self) -> None:
        """setup 之后注入的键，teardown 必须抹掉（setdefault 泄漏的正解）。"""
        assert os.environ.get(_PROBE_KEY) is None, "宿主环境已设该键，本用例前提不成立"
        gen = _underlying_fixture()()
        next(gen)  # setup：快照（此时键不存在）
        try:
            os.environ[_PROBE_KEY] = "true"  # 模拟 _apply_profile_presets 注入
            assert os.environ[_PROBE_KEY] == "true"
        finally:
            with pytest.raises(StopIteration):
                next(gen)  # teardown：还原
            os.environ.pop(_PROBE_KEY, None)  # 兜底：断言失败时也不留残留
        assert os.environ.get(_PROBE_KEY) is None

    def test_preexisting_value_is_restored_not_deleted(self) -> None:
        """会话启动前就存在的值必须原样还原（只清注入，不清宿主配置）。"""
        gen_factory = _underlying_fixture()
        os.environ[_PROBE_KEY] = "false"
        try:
            gen = gen_factory()
            next(gen)  # setup：快照到 "false"
            os.environ[_PROBE_KEY] = "true"  # 注入覆盖
            with pytest.raises(StopIteration):
                next(gen)
            assert os.environ.get(_PROBE_KEY) == "false"
        finally:
            os.environ.pop(_PROBE_KEY, None)

    def test_all_preset_keys_reverted_in_one_pass(self) -> None:
        """全档位键一次性注入后，teardown 归零（等价于 logic 档跑完的残留面）。"""
        injected = [k for k in sorted(_PRESET_ENV_KEYS) if os.environ.get(k) is None]
        gen = _underlying_fixture()()
        next(gen)
        try:
            for key in injected:
                os.environ[key] = "true"
        finally:
            with pytest.raises(StopIteration):
                next(gen)
            for key in injected:
                os.environ.pop(key, None)
        residue = {k: os.environ[k] for k in injected if os.environ.get(k) is not None}
        assert not residue, f"还原不完整：{residue}"
