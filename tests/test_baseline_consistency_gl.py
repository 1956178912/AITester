"""GL 轮（2026-11-04）：`check_baseline.py --verify` 一致性支路的对账口径。

原实现把 **collected**（全量收集数）与 **total_passed**（链内通过数）两个不同的量
放在一起比，再给 ±2% 容差吸收口径差。语料撤回后 skip 合法地升到 collected 的 2.2%，
于是"把 total_passed 如实写成实测值"反而被守卫判红——要绿只能虚报 passed。
本轮改为同一量逐位对账 + 声明面自洽，并给这条此前**零覆盖**的支路补锁。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts.gates import check_baseline as gate

# 13,488 + 0 + 303 + 0 == 13,791（GL 收口实测，隔离临时根一跑）
_CONSISTENT = {
    "tests": {
        "total_passed": 13488,
        "total_failed": 0,
        "total_skipped": 303,
        "total_xfailed": 0,
        "collected": 13791,
    }
}


def _patch(monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any], measured: int | None) -> None:
    monkeypatch.setattr(gate, "_load_baseline", lambda: baseline, raising=True)
    monkeypatch.setattr(gate, "measure_full_suite", lambda: measured, raising=True)


class TestCollectedExactReconciliation:
    def test_measured_collected_equal_declared(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch, _CONSISTENT, 13791)
        assert gate.check_consistency() == []

    def test_off_by_one_collected_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """±2% 容差时代 1 例漂移无声通过；现在逐位对账。"""
        _patch(monkeypatch, _CONSISTENT, 13792)
        failures = gate.check_consistency()
        assert len(failures) == 1
        assert "逐位相等" in failures[0]
        assert "13791" in failures[0] and "13792" in failures[0]

    def test_honest_passed_below_collected_is_not_a_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """本轮修掉的假红本体：skip 占比 2.2% 时如实登记必须判绿。"""
        _patch(monkeypatch, _CONSISTENT, 13791)
        assert (13791 - 13488) / 13791 > 0.02, "前提：示例本身就是旧口径下的超容差样本"
        assert gate.check_consistency() == []

    def test_declared_counts_must_sum_to_collected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        baseline = {
            "tests": {
                "total_passed": 13791,
                "total_failed": 0,
                "total_skipped": 0,
                "total_xfailed": 0,
                "collected": 13791,
            }
        }
        _patch(monkeypatch, baseline, 13791)
        assert gate.check_consistency() == []
        # 把 skipped 改成 303 而 collected 不动 ⇒ 结果计数之和超出 collected
        baseline["tests"]["total_skipped"] = 303
        failures = gate.check_consistency()
        assert len(failures) == 1
        assert "不自洽" in failures[0]

    def test_missing_collected_key_fails_instead_of_silence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`collected` 缺席不得回退到旧的 total_passed 比对——那是"缺席与通过同形"。"""
        baseline = {"tests": {k: v for k, v in _CONSISTENT["tests"].items() if k != "collected"}}
        _patch(monkeypatch, baseline, 13791)
        failures = gate.check_consistency()
        assert len(failures) == 1
        assert "collected" in failures[0]

    def test_negative_count_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        baseline = {"tests": dict(_CONSISTENT["tests"], total_skipped=-1)}
        _patch(monkeypatch, baseline, 13791)
        failures = gate.check_consistency()
        assert len(failures) == 1
        assert "非非负整数" in failures[0]

    def test_unmeasurable_collection_still_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch, _CONSISTENT, None)
        failures = gate.check_consistency()
        assert len(failures) == 1
        assert "无法校验" in failures[0]


class TestNoToleranceConstantLeft:
    def test_tolerance_constant_is_gone(self) -> None:
        """旧口径的 ±2% 常量随口径一起删除，避免下一轮又被"恢复容差"。"""
        assert not hasattr(gate, "_MEASURE_TOLERANCE")
        text = (Path(gate.__file__)).read_text(encoding="utf-8")
        assert "_MEASURE_TOLERANCE" not in text
        assert "±2%" in text, "docstring 仍须留旧口径的历史说明"


class TestDuplicateKeyGuard:
    """重复键守卫：本轮自己写出来过一次的缺陷（YAML 静默取最后一次）。"""

    def test_current_baseline_has_no_duplicate_keys(self) -> None:
        assert gate._duplicate_keys(gate.BASELINE_PATH.read_text(encoding="utf-8")) == []

    def test_nested_duplicate_is_named_by_path(self) -> None:
        found = gate._duplicate_keys("tests:\n  suite_seconds: 144\n  suite_seconds: 153\n")
        assert found == ["tests.suite_seconds"], found

    def test_same_key_under_different_parents_is_not_a_duplicate(self) -> None:
        text = "a:\n  total: 1\nb:\n  total: 2\n"
        assert gate._duplicate_keys(text) == []

    def test_list_items_with_repeated_inner_keys_are_not_flagged(self) -> None:
        """序列里每一项都有 `name` 键是正常形状，不能误判成重复键。"""
        assert gate._duplicate_keys("items:\n  - name: x\n  - name: y\n") == []

    def test_scope_limit_duplicates_inside_a_list_item_are_not_judged(self) -> None:
        """写出不判的范围：行扫描对序列元素内部的同名键一律放行（宁漏不误红）。

        本守卫针对的是映射层的静默覆盖（本轮真实踩到的形态）；序列内部的重复键
        仍需 PyYAML 或更完整的解析才能判，这里明确不覆盖，免得被当成全覆盖。
        """
        assert gate._duplicate_keys("items:\n  - k:\n      a: 1\n      a: 2\n") == []

    def test_structure_check_reddens_on_a_duplicated_baseline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = tmp_path / "BASELINE.yaml"
        baseline.write_text(
            'version: "1"\nlast_verified: "2026-11-04"\ntests:\n  total_passed: 1\n  total_passed: 2\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(gate, "BASELINE_PATH", baseline, raising=True)
        failures = gate.check_structure()
        assert any("重复键" in f and "tests.total_passed" in f for f in failures), failures

    def test_parsing_hides_the_overwritten_key(self) -> None:
        """正控：解析后只剩最后一个值——所以这件事只能由结构检查来管。"""
        import yaml

        parsed = yaml.safe_load("tests:\n  suite_seconds: 144\n  suite_seconds: 153\n")
        assert parsed["tests"]["suite_seconds"] == 153  # 读 dict 的校验永远看不到被覆盖的那个
