"""EY 轮锁：SPEC 链的「三开关一体」校验不得只看显式键。

缺陷（修复前）：`ArmSpec.__post_init__` 的 chain_states 只收集 `k in self.env`
的键，于是 `{SPEC_ORACLE_EXEC_ENABLE: true}`、`{SPEC_IR_ENABLE: true}`、
`{SPEC_IR_ENABLE: true, SPEC_IR_DSL_ENABLE: true}` 全部被接受；而干净基线
（`establish_clean_baseline`）会把缺省键压成 false ⇒ 这些臂实际运行的是拆开
的链。三层各自有独立降级（IR 由 Planner 写入、DSL 可自行重解析
logic_analysis、oracle 四源材料回退），所以后果不是崩溃而是**静默换了测量面**：
只开 IR 写出 `spec_ir`/findings 却没有 compile_rate 与 oracle 判定；只开
oracle 经 `test_plan.logic_analysis` 注入而 IR/DSL 观测恒为 None——臂名宣称
开关的是整条链，结果却无法按链归因。登记表自身的 `test_spec_chain_atomic`
复制了同一盲点（`if k in arm.env`），未来任何部分链臂都会被它发合格证。

锁定口径：一处校验（构造期拒绝）+ 三处负向对照（全开 / 全关 / 不写）。
"""

from __future__ import annotations

import pytest

from src.graph.orchestration_search import (
    ARM_REGISTRY,
    ENV_SPEC_IR,
    ENV_SPEC_IR_DSL,
    ENV_SPEC_ORACLE_EXEC,
    ArmSpec,
    ArmSpecError,
)

_SPEC_KEYS = (ENV_SPEC_IR, ENV_SPEC_IR_DSL, ENV_SPEC_ORACLE_EXEC)


def _arm(env: dict[str, str]) -> ArmSpec:
    return ArmSpec(arm_id="spec_probe", planner=True, debugger=True, env=env)


@pytest.mark.parametrize(
    "env",
    [
        pytest.param({ENV_SPEC_IR: "true"}, id="ir-only"),
        pytest.param({ENV_SPEC_IR_DSL: "true"}, id="dsl-only"),
        pytest.param({ENV_SPEC_ORACLE_EXEC: "true"}, id="oracle-only"),
        pytest.param({ENV_SPEC_IR: "true", ENV_SPEC_IR_DSL: "true"}, id="missing-oracle"),
        pytest.param({ENV_SPEC_IR: "true", ENV_SPEC_ORACLE_EXEC: "true"}, id="missing-dsl"),
        pytest.param({ENV_SPEC_IR_DSL: "true", ENV_SPEC_ORACLE_EXEC: "true"}, id="missing-ir"),
        pytest.param({ENV_SPEC_IR: "true", ENV_SPEC_IR_DSL: "false"}, id="explicit-mixed"),
    ],
)
def test_partial_spec_chain_is_rejected(env: dict[str, str]) -> None:
    with pytest.raises(ArmSpecError, match="SPEC 链"):
        _arm(env)


def test_full_chain_true_is_accepted() -> None:
    arm = _arm({key: "true" for key in _SPEC_KEYS})
    assert arm.env == {key: "true" for key in _SPEC_KEYS}


def test_all_off_and_absent_are_accepted() -> None:
    """负向对照：全关（显式 false）与完全不写都合法——缺省 false 等价于关闭。"""
    assert _arm({key: "false" for key in _SPEC_KEYS}).env == {key: "false" for key in _SPEC_KEYS}
    assert _arm({}).env == {}
    assert _arm({ENV_SPEC_ORACLE_EXEC: "false"}).env == {ENV_SPEC_ORACLE_EXEC: "false"}


def test_error_message_reports_effective_states_including_omitted_keys() -> None:
    """报错须按运行期生效值陈述（缺省键 = false），不能只列显式键或给 None。"""
    with pytest.raises(ArmSpecError) as excinfo:
        _arm({ENV_SPEC_IR: "true"})
    message = str(excinfo.value)
    for key in _SPEC_KEYS:
        assert key in message
    assert "None" not in message


def test_registry_arms_are_atomic_under_clean_baseline() -> None:
    """登记表在干净基线口径下也必须一体（缺省键按 false 补全后比状态）。"""
    for arm in ARM_REGISTRY:
        states = {arm.env.get(key, "false") for key in _SPEC_KEYS}
        assert len(states) == 1, f"{arm.arm_id} 在干净基线下拆开 SPEC 链：{states}"
