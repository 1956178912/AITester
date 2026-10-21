"""AY（2026-10-21）：run_b8 载荷装配不得改写 ``token_metrics`` 形状。

AW 收口 ``arm_stats`` 后，同一缺陷族仍在 ``run_b8_injection`` 的工件读取处：
``rd.get("token_metrics") or {}`` 把假值非对象（``[]`` / ``""`` / ``0`` /
``False``）改写成 ``{}``，下游 ``_cost_usd`` 于是把"载荷坏了"读成"没有
metrics"——成本报 ``$0.0`` 且无机制名；``REPORT.json`` 也丢失原始坏形状。
真值非对象（``"abc"`` / ``True``）虽能触发拒绝，但存储端同样不做形状保证。

锁的口径：

- 读取层原样保留 ``token_metrics``：缺席 / ``null`` 保持 ``None``，非对象
  保持原值（类型与值都不变），干净 dict 逐位不变；
- 金额判定只在 ``_cost_usd`` 一处：假值非对象同样得到 ``None`` +
  ``token_metrics_not_object:<T>``，不得折成历史 0；
- 冒烟行既保留原始载荷，也保留既有成本读数（干净路径逐位复现
  ``REPORT.json`` 的 on/off 两臂与四条冒烟行）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from experiments import run_b8_injection as rb8

_ROOT = Path(__file__).resolve().parents[1]
_B8_ROOT = _ROOT / "experiments/results/s_round_b8_injection_20261018"


def _write_batch(arm_dir: Path, token_metrics: Any = None, *, include_key: bool = True) -> Path:
    arm_dir.mkdir(parents=True)
    row: dict[str, Any] = {"details": []}
    if include_key:
        row["token_metrics"] = token_metrics
    (arm_dir / "benchmark_ay.json").write_text(
        json.dumps({"results": {"on": row}}),
        encoding="utf-8",
    )
    return arm_dir


_FALSEY_NON_OBJECTS = [
    ([], "token_metrics_not_object:list"),
    ("", "token_metrics_not_object:str"),
    (0, "token_metrics_not_object:int"),
    (False, "token_metrics_not_object:bool"),
]


class TestLoadArmPreservesPayload:
    """读取层只搬运载荷，不做 ``or {}`` 归一。"""

    @pytest.mark.parametrize("raw", [[], "", 0, False, "abc", True, [1], {"x": 1}])
    def test_payload_value_and_type_preserved(self, tmp_path: Path, raw: Any) -> None:
        loaded = rb8._load_arm(_write_batch(tmp_path / "arm_on", raw))
        assert type(loaded["token_metrics"]) is type(raw)
        assert loaded["token_metrics"] == raw

    def test_present_null_stays_none(self, tmp_path: Path) -> None:
        loaded = rb8._load_arm(_write_batch(tmp_path / "arm_on", None))
        assert loaded["token_metrics"] is None

    def test_absent_payload_stays_none(self, tmp_path: Path) -> None:
        loaded = rb8._load_arm(_write_batch(tmp_path / "arm_on", include_key=False))
        assert loaded["token_metrics"] is None

    def test_clean_dict_unchanged(self, tmp_path: Path) -> None:
        raw = {"total_input_tokens": 1_000_000, "total_output_tokens": 2_000_000}
        loaded = rb8._load_arm(_write_batch(tmp_path / "arm_on", raw))
        assert loaded["token_metrics"] == raw


class TestArmSummaryCostUsesRawPayload:
    """假值非对象必须走到拒绝路径，而不是折成免费。"""

    @pytest.mark.parametrize(("raw", "code"), _FALSEY_NON_OBJECTS)
    def test_falsey_non_object_is_unpriced(self, tmp_path: Path, raw: Any, code: str) -> None:
        loaded = rb8._load_arm(_write_batch(tmp_path / "arm_on", raw))
        summary = rb8._arm_summary(loaded, 1.0, 2.0)
        assert type(summary["token_metrics"]) is type(raw)
        assert summary["cost_usd_standard_price"] is None
        assert summary["cost_usd_standard_price_reasons"] == {code: 1}

    def test_present_null_is_historical_zero(self, tmp_path: Path) -> None:
        loaded = rb8._load_arm(_write_batch(tmp_path / "arm_on", None))
        summary = rb8._arm_summary(loaded, 1.0, 2.0)
        assert summary["token_metrics"] is None
        assert summary["cost_usd_standard_price"] == 0.0
        assert "cost_usd_standard_price_reasons" not in summary

    def test_absent_payload_is_historical_zero(self, tmp_path: Path) -> None:
        loaded = rb8._load_arm(_write_batch(tmp_path / "arm_on", include_key=False))
        summary = rb8._arm_summary(loaded, 1.0, 2.0)
        assert summary["token_metrics"] is None
        assert summary["cost_usd_standard_price"] == 0.0
        assert "cost_usd_standard_price_reasons" not in summary

    def test_clean_payload_cost_unchanged(self, tmp_path: Path) -> None:
        raw = {"total_input_tokens": 1_000_000, "total_output_tokens": 1_000_000}
        loaded = rb8._load_arm(_write_batch(tmp_path / "arm_on", raw))
        summary = rb8._arm_summary(loaded, 1.0, 2.0)
        assert summary["token_metrics"] == raw
        assert summary["cost_usd_standard_price"] == 3.0
        assert "cost_usd_standard_price_reasons" not in summary


class TestHarnessSmokePreservesPayload:
    """冒烟行同样保留原始载荷；成本读数沿用拒绝路径。"""

    @pytest.mark.parametrize(("raw", "code"), _FALSEY_NON_OBJECTS)
    def test_falsey_non_object_preserved_and_unpriced(self, tmp_path: Path, raw: Any, code: str) -> None:
        _write_batch(tmp_path / "_harness_smoke" / "arm_on", raw)
        rows = rb8._load_harness_smoke(tmp_path, 1.0, 2.0)
        assert len(rows) == 1
        assert type(rows[0]["token_metrics"]) is type(raw)
        assert rows[0]["token_metrics"] == raw
        assert rows[0]["cost_usd_standard_price"] is None
        assert rows[0]["cost_usd_standard_price_reasons"] == {code: 1}

    def test_absent_payload_stays_none(self, tmp_path: Path) -> None:
        _write_batch(tmp_path / "_harness_smoke" / "arm_on", include_key=False)
        rows = rb8._load_harness_smoke(tmp_path, 1.0, 2.0)
        assert rows[0]["token_metrics"] is None
        assert rows[0]["cost_usd_standard_price"] == 0.0
        assert "cost_usd_standard_price_reasons" not in rows[0]

    def test_clean_payload_unchanged(self, tmp_path: Path) -> None:
        raw = {"total_input_tokens": 1_000_000, "total_output_tokens": 0}
        _write_batch(tmp_path / "_harness_smoke" / "arm_on", raw)
        rows = rb8._load_harness_smoke(tmp_path, 1.0, 2.0)
        assert rows[0]["token_metrics"] == raw
        assert rows[0]["cost_usd_standard_price"] == 1.0
        assert "cost_usd_standard_price_reasons" not in rows[0]


class TestRealB8Corpus:
    """真批次干净路径逐位复现：两臂成本 + 四条冒烟行。"""

    def test_arms_and_smoke_reproduce_report(self) -> None:
        report = json.loads((_B8_ROOT / "REPORT.json").read_text(encoding="utf-8"))
        price_in = report["price"]["input_per_mtok"]
        price_out = report["price"]["output_per_mtok"]

        for arm in ("on", "off"):
            loaded = rb8._load_arm(_B8_ROOT / f"arm_{arm}")
            summary = rb8._arm_summary(loaded, price_in, price_out)
            expected = report["arms"][arm]
            assert summary["token_metrics"] == expected["token_metrics"]
            assert summary["cost_usd_standard_price"] == expected["cost_usd_standard_price"]
            assert "cost_usd_standard_price_reasons" not in summary

        rows = rb8._load_harness_smoke(_B8_ROOT, price_in, price_out)
        expected_rows = {(row["setting"], row["arm"]): row for row in report["harness_smoke"]}
        assert len(rows) == len(expected_rows) == 4
        for row in rows:
            expected = expected_rows[(row["setting"], row["arm"])]
            assert row["token_metrics"] == expected["token_metrics"]
            assert row["cost_usd_standard_price"] == expected["cost_usd_standard_price"]
            assert "cost_usd_standard_price_reasons" not in row


class TestSourceLocks:
    """源码锁：读取层不得回退到 ``or {}`` 归一。"""

    def test_no_or_empty_normalization(self) -> None:
        import inspect

        source = (_ROOT / "experiments/run_b8_injection.py").read_text(encoding="utf-8")
        assert 'rd.get("token_metrics") or {}' not in source
        body = inspect.getsource(rb8._load_arm).split('"""', 2)[-1]
        assert '"token_metrics": rd.get("token_metrics")' in body

    def test_smoke_row_uses_same_raw_reading(self) -> None:
        import inspect

        body = inspect.getsource(rb8._load_harness_smoke).split('"""', 2)[-1]
        assert 'tm = rd.get("token_metrics")' in body
        assert "_cost_usd(tm," in body
        assert '"token_metrics": tm' in body
