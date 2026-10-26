"""ER 轮（2026-10-27）：CLI 布尔开关的关态不可达。

5 处 ``action="store_true", default=True`` 的开关只有一种取值：帮助文本写着
"默认开"暗示可以关，但传旗标与不传等价，``--no-*`` 又不存在。其中 4 个
``--pool-seeds`` 是 E7 / 修复上限分析的多种子拼接口径（预注册固定开），
gold 诊断的 ``--with-generated`` 供 README §2c 无条件渲染的生成门使用——
关态一旦可达反而会渲染误导性零值。

本轮按 EQ 先例移除旗标、把默认语义钉死在调用点；下面的锁防止"读起来可关、
实际不可关"的声明回流，同时守住邻接 ``statistical_analysis`` 中真正可关的
``--pool-seeds``。
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from experiments import (
    e7_evidence_prepass,
    emse_ult_gold_diagnosis,
    repair_ceiling_analysis,
    repair_review_worksheet,
    repair_sample_selection,
    statistical_analysis,
)

_PIPELINE_MODULES: tuple[Any, ...] = (
    e7_evidence_prepass,
    repair_ceiling_analysis,
    repair_review_worksheet,
    repair_sample_selection,
)
_PIPELINE_IDS = [m.__name__.rsplit(".", 1)[-1] for m in _PIPELINE_MODULES]


class _LoaderSentinel(RuntimeError):
    """捕获 loader / 上游加载调用后立刻中断 main，避免触达真实工件。"""


@pytest.mark.parametrize("module", _PIPELINE_MODULES, ids=_PIPELINE_IDS)
def test_pool_seeds_flag_is_rejected(module: Any) -> None:
    with pytest.raises(SystemExit) as excinfo:
        module.main(["--pool-seeds"])
    assert excinfo.value.code == 2


@pytest.mark.parametrize("module", _PIPELINE_MODULES, ids=_PIPELINE_IDS)
def test_help_no_longer_advertises_pool_seeds(module: Any, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        module.main(["--help"])
    assert excinfo.value.code == 0
    help_text = capsys.readouterr().out
    assert "--pool-seeds" not in help_text
    assert "--results-dir" in help_text


@pytest.mark.parametrize("module", _PIPELINE_MODULES, ids=_PIPELINE_IDS)
def test_main_still_pools_seeds(module: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_loader(results_dir: str, batch_files: Any = None, **kwargs: Any) -> Any:
        captured["results_dir"] = results_dir
        captured["batch_files"] = batch_files
        captured["kwargs"] = kwargs
        raise _LoaderSentinel

    monkeypatch.setattr(module, "load_experiment_results_with_sources", fake_loader)
    with pytest.raises(_LoaderSentinel):
        module.main([])
    assert captured["kwargs"]["pool_seeds"] is True
    assert captured["kwargs"]["allow_schema_mixed"] is False


@pytest.mark.parametrize("module", _PIPELINE_MODULES, ids=_PIPELINE_IDS)
def test_usage_docstring_does_not_advertise_pool_seeds(module: Any) -> None:
    assert "--pool-seeds" not in (module.__doc__ or "")


def test_with_generated_flag_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: Any, **kwargs: Any) -> Any:
        raise _LoaderSentinel

    monkeypatch.setattr(emse_ult_gold_diagnosis, "_load_upstream_array", boom)
    with pytest.raises(SystemExit) as excinfo:
        emse_ult_gold_diagnosis.main(["--with-generated"])
    assert excinfo.value.code == 2


def test_gold_diagnosis_help_drops_with_generated_keeps_other_switches(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        emse_ult_gold_diagnosis.main(["--help"])
    assert excinfo.value.code == 0
    help_text = capsys.readouterr().out
    assert "--with-generated" not in help_text
    assert "--keep-tmp" in help_text
    assert "--limit" in help_text


def test_gold_diagnosis_generated_gate_is_always_on() -> None:
    """README §2c 无条件渲染生成门：运行路径不得读取 args.with_generated。"""
    assert "args.with_generated" not in inspect.getsource(emse_ult_gold_diagnosis.main)


def test_statistical_analysis_real_pool_seeds_switch_untouched() -> None:
    """邻接护栏：真开关的关态可达（default False），本轮清理不得误伤。"""
    src = inspect.getsource(statistical_analysis.main)
    assert '"--pool-seeds"' in src
    assert "pool_seeds=args.pool_seeds" in src
