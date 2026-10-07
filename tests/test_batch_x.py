"""修复引擎批次 X（2026-10-07）：反事实 FL 上界测试锁（ADR-0024）。

锁定三组行为：
1. build_gold_injection_localization（gold 函数 → 同构定位构造器）：
   行范围/置信度/反事实臂标注、无 gold 降级、函数不可定位降级；
2. gold_injection_enabled 默认关（ADR-0003）+ nodes 接线优先级
   （gold 注入开关优先于 FAULT_LOCALIZER_ENABLE 的源码契约）；
3. cf_upper_bound 归因分解数学（2×2 单元、fl_at_1 回退口径、
   条件概率、报告关键行）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.fault_localizer import (
    build_gold_injection_localization,
    gold_injection_enabled,
)

BUGGY = "def add(a, b):\n    return a - b\n\ndef mul(a, b):\n    return a * b\n"
FIXED = "def add(a, b):\n    return a + b\n\ndef mul(a, b):\n    return a * b\n"


class TestGoldInjectionLocalization:
    def test_builds_from_gold_diff(self) -> None:
        loc = build_gold_injection_localization(BUGGY, FIXED)
        assert loc is not None
        assert loc["function_name"] == "add"
        assert (loc["line_start"], loc["line_end"]) == (1, 2)
        assert loc["confidence"] == 1.0
        assert "反事实臂" in loc["reasoning"]
        assert loc["candidates"][0]["function_name"] == "add"

    def test_no_gold_material_none(self) -> None:
        assert build_gold_injection_localization(BUGGY, "") is None
        assert build_gold_injection_localization("", FIXED) is None

    def test_identical_codes_none(self) -> None:
        # 无 diff 行 → gold 函数集合空 → None
        assert build_gold_injection_localization(BUGGY, BUGGY) is None

    def test_module_level_change_none(self) -> None:
        # diff 行归属模块级（"<module>"，无函数可定位）→ None
        target = "x = 1\ny = 2\n"
        fixed = "x = 1\ny = 3\n"
        assert build_gold_injection_localization(target, fixed) is None

    def test_unparseable_target_none(self) -> None:
        assert build_gold_injection_localization("def f(:\n", FIXED) is None

    def test_switch_default_off(self) -> None:
        assert gold_injection_enabled() is False

    def test_nodes_wiring_priority_contract(self) -> None:
        # 源码契约：gold 注入分支必须先于 fault_localizer_enabled 分支
        src = Path("src/graph/nodes.py").read_text(encoding="utf-8")
        assert "build_gold_injection_localization as _build_gold_loc" in src
        assert 'if _gold_inj_on() and state.get("gold_fixed_code"):' in src
        assert "elif _fl_enabled():" in src


class TestCfUpperBoundDecomposition:
    @staticmethod
    def _row(task_id: str, patch: str, fl_hit, fl_source: str = "localization_hit_function") -> dict:
        row = {
            "task_id": f"synthetic__{task_id}",
            "patch": patch,
            "patch_correct": 0,
            "task_metadata": {
                "source": "synthetic",
                "test_cases": f"from {task_id} import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
                "fixed": "",
            },
        }
        if fl_source == "localization_hit_function":
            row["localization_hit_function"] = fl_hit
        else:
            row["fl_at_k"] = {"fl_at_1": 1.0 if fl_hit else 0.0}
        return row

    def _batch(self, tmp_path: Path) -> Path:
        good = "def add(a, b):\n    return a + b\n"
        bad = "def add(a, b):\n    return a - b\n"
        details = [
            self._row("m_hit_ok", good, True),  # a 双对
            self._row("m_hit_bad", bad, True),  # b 生成侧瓶颈
            self._row("m_miss_ok", good, False),  # c 碰巧修对
            self._row("m_miss_bad", bad, False),  # d 定位侧瓶颈
            self._row("m_spectral_ok", good, True, fl_source="fl_at_1_spectral"),
            self._row("m_nofl", good, None),  # 跳过（FL 不可测）
        ]
        batch = {"results": {"aitester": {"details": details}}}
        p = tmp_path / "benchmark_synthetic_cf.json"
        p.write_text(json.dumps(batch), encoding="utf-8")
        return p

    def test_decompose_cells_and_sources(self, tmp_path) -> None:
        from experiments.cf_upper_bound import decompose_batch

        r = decompose_batch(self._batch(tmp_path), "aitester", timeout=60)
        assert r["cells"] == {"a_both": 2, "b_gen_bottleneck": 1, "c_lucky": 1, "d_fl_bottleneck": 1}
        assert r["skipped"] == 1
        assert r["fl_sources"]["localization_hit_function"] == 4
        assert r["fl_sources"]["fl_at_1_spectral"] == 1

    def test_report_ratios(self, tmp_path) -> None:
        from experiments.cf_upper_bound import build_report

        self._batch(tmp_path)
        report = build_report(tmp_path, "aitester", timeout=60)
        # a=2 b=1 c=1 d=1 → P(correct|FL命中)=2/3；实测 repair=3/5
        assert "P(correct | FL 命中) = 0.6667" in report
        assert "0.6" in report

    def test_cli_writes_report(self, tmp_path) -> None:
        from experiments.cf_upper_bound import main as cf_main

        self._batch(tmp_path)
        out = tmp_path / "cf.md"
        rc = cf_main([str(tmp_path), "--arm", "aitester", "--out", str(out)])
        assert rc == 0
        assert "ADR-0024" in out.read_text(encoding="utf-8")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
