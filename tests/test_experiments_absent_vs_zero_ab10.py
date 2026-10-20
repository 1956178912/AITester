"""AB-10 回归锁：分析侧"缺席 / 读不动"不得报成"零命中 / 一致 / 未要求"（2026-10-20）。

站点 = `experiments/emse_ult_gold_diagnosis.py`（AB-9 普查登记为"下一轮"的两处 +
顺带同族的补充测量读取）。判据沿用 AB-9：**分析层宁可响亮失败，也不要一个看起来
正常的错数字**；因此本轮的处置方向全是"静默 → 披露或 fail-closed"，没有一处把
崩溃换成静默。

全部用例用 `tmp_path` 合成输入，不读 `~/.cache/aitester/ult_repo`，故 CI 与本机同口径。
判据 = **删掉对应守卫必然转红**（变异验证逐处打印变红用例名）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import pytest

from experiments.emse_ult_gold_diagnosis import (
    _load_json_array,
    _load_supplement,
    _load_upstream_array,
    _official_tests_for,
    _render_section_4c,
    _render_section_4d,
)

SHAPES = {
    "string": '"abc"',
    "number": "3",
    "bool": "true",
    "null": "null",
}


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


class TestUpstreamArrayReturnDomain:
    """`_load_json_array`：顶层类型与逐行形状都要留下痕迹。"""

    def test_object_rows_pass_through(self, tmp_path):
        p = _write(tmp_path, "a.json", '[{"code": "c1"}, {"code": "c2"}]')
        assert _load_json_array(p) == [{"code": "c1"}, {"code": "c2"}]

    def test_empty_array_is_a_genuine_zero_and_stays_silent(self, tmp_path, capsys):
        """空数组 = 真零行，与"读不动"不同形，因此不该有任何 WARN 噪声。"""
        p = _write(tmp_path, "a.json", "[]")
        assert _load_json_array(p) == []
        assert capsys.readouterr().err == ""

    @pytest.mark.parametrize("shape", sorted(SHAPES))
    def test_non_list_top_level_is_loud_not_empty(self, tmp_path, shape, capsys):
        """AB-9 实测：顶层字符串原先被逐字符迭代后静默得 []（三种标量则崩）。"""
        p = _write(tmp_path, f"{shape}.json", SHAPES[shape])
        with pytest.raises(TypeError) as exc:
            _load_json_array(p)
        assert "不是列表" in str(exc.value)
        assert shape in str(exc.value) or p.name in str(exc.value)

    def test_non_object_rows_are_dropped_with_a_count_on_stderr(self, tmp_path, capsys):
        p = _write(tmp_path, "mixed.json", '[1, "x", null, {"code": "keep"}]')
        rows = _load_json_array(p)
        assert rows == [{"code": "keep"}]
        err = capsys.readouterr().err
        assert "[WARN]" in err and "3 行不是对象" in err and "1 行" in err

    def test_all_rows_non_object_reports_zero_kept_rows(self, tmp_path, capsys):
        """整文件都是坏行：分母必须可见，不能与"空数组"同形。"""
        p = _write(tmp_path, "bad.json", "[1, 2, 3]")
        assert _load_json_array(p) == []
        err = capsys.readouterr().err
        assert "3 行不是对象" in err and "0 行" in err


class TestUpstreamAbsentIsNotZeroHit:
    """`_load_upstream_array`：工件缺失/无对象行 ⇒ 无法核验，不是"上游没有该行"。"""

    def test_missing_file_raises_not_empty_list(self, tmp_path):
        p = tmp_path / "absent.json"
        assert not p.exists()
        with pytest.raises(FileNotFoundError) as exc:
            _load_upstream_array(p)
        assert "缺席不等于上游无该行" in str(exc.value)

    def test_file_without_object_rows_raises(self, tmp_path):
        p = _write(tmp_path, "rows.json", '"a string top level"')
        with pytest.raises(TypeError):
            _load_upstream_array(p)

    def test_empty_array_yields_unreadable_error_not_zero_rows(self, tmp_path):
        p = _write(tmp_path, "rows.json", "[]")
        with pytest.raises(ValueError) as exc:
            _load_upstream_array(p)
        assert "读不动" in str(exc.value)

    def test_good_file_returns_rows(self, tmp_path):
        p = _write(tmp_path, "rows.json", '[{"code": "c1"}]')
        assert _load_upstream_array(p) == [{"code": "c1"}]


class TestNoSelfComparison:
    """`_official_tests_for`：没有上游断言时，一致性是"无法核验"，不是 True 也不是 False。"""

    GOLD: ClassVar[list[str]] = ["assert f(1) == 1", "assert f(2) == 2"]

    def test_absent_upstream_row_returns_none_not_true(self):
        _, source, equal = _official_tests_for(self.GOLD, None)
        assert source == "ULT_Lite.jsonl:test_list(wrapped)"
        assert equal is None

    def test_wrapping_is_still_local_gold_so_equality_would_be_trivially_true(self):
        """AB-10 实测：包装体归一后与本地 gold 逐字相同——若不加判据，此处的比对恒真。"""
        tests, _, _ = _official_tests_for(self.GOLD, None)
        from experiments.emse_ult_gold_diagnosis import _normalize_test_body

        assert sorted(_normalize_test_body(t) for t in tests) == sorted(_normalize_test_body(t) for t in self.GOLD)

    def test_upstream_row_without_tests_list_is_not_an_agreement(self):
        _, _, equal = _official_tests_for(self.GOLD, {"code": "c1"})
        assert equal is None

    def test_real_upstream_match_reports_true(self):
        up = {"tests": ["def test_0():\n    assert f(1) == 1", "def test_1():\n    assert f(2) == 2"]}
        tests, source, equal = _official_tests_for(self.GOLD, up)
        assert source == "ULT.jsonl:tests"
        assert equal is True
        assert tests == [str(t) for t in up["tests"]]

    def test_real_upstream_mismatch_reports_false(self):
        up = {"tests": ["def test_0():\n    assert f(1) == 999"]}
        _, _, equal = _official_tests_for(self.GOLD[:1], up)
        assert equal is False


class TestSupplementReader:
    """`_load_supplement`：显式给了 `--supplement` 路径，就不允许当作"未要求补充测量"。"""

    def test_missing_path_raises(self, tmp_path):
        p = tmp_path / "nope.json"
        with pytest.raises(FileNotFoundError) as exc:
            _load_supplement(p)
        assert "缺席不得当作未要求" in str(exc.value)

    @pytest.mark.parametrize("text", ["[]", '"abc"', "3", "true", "null"])
    def test_non_object_top_level_is_loud(self, tmp_path, text):
        """五种非对象返回一律崩（AB-9 判据：响亮可接受，静默缩分母不可）。"""
        p = _write(tmp_path, "sup.json", text)
        with pytest.raises(TypeError):
            _load_supplement(p)

    @pytest.mark.parametrize("text", ["{}", '{"records": []}', '{"records": null}'])
    def test_object_without_records_warns_and_returns_none(self, tmp_path, text, capsys):
        p = _write(tmp_path, "sup.json", text)
        assert _load_supplement(p) is None
        assert "[WARN]" in capsys.readouterr().err

    def test_usable_supplement_is_returned_verbatim(self, tmp_path, capsys):
        payload = {"records": [{"task_id": "t", "runs": {"C+": {"status": "pass"}}}]}
        p = _write(tmp_path, "sup.json", json.dumps(payload))
        assert _load_supplement(p) == payload
        assert capsys.readouterr().err == ""


class TestSectionOmissionIsDisclosed:
    """README 的 §4c/§4d：未渲染的节必须自己说明"为什么没渲染"。"""

    MUTK: ClassVar[dict] = {
        "cosmic_ray_version": "8.7.0",
        "measured": {"official_prelude_module": {"mutation_score": 1.0, "mutants_killed": 17, "mutants_total": 17}},
        "rebasing": {
            "published_specir": {"killed": 847, "total": 1927, "score": 0.439543, "n_tasks": 5},
            "corrected_specir_if_fix_labels_admitted": {
                "killed": 864,
                "total": 1944,
                "score": 0.444444,
                "n_tasks": 6,
            },
            "delta_score": 0.0049,
            "caliber": "arithmetic",
        },
    }

    def test_absent_mutk_artifact_is_named_not_silently_omitted(self, tmp_path):
        out = _render_section_4c(tmp_path / "SUPPLEMENT_GENERATED_MUTK.json")
        text = "\n".join(out)
        assert "4c 节省略" in text and "SUPPLEMENT_GENERATED_MUTK.json" in text
        assert "## 4c." not in text

    def test_present_mutk_artifact_renders_the_numbers(self, tmp_path):
        p = _write(tmp_path, "SUPPLEMENT_GENERATED_MUTK.json", json.dumps(self.MUTK))
        text = "\n".join(_render_section_4c(p))
        assert "## 4c." in text and "0.444444" in text
        assert "省略" not in text

    def test_no_supplement_requested_renders_nothing(self):
        assert _render_section_4d(None) == []

    def test_records_without_cplus_variant_discloses_the_count(self):
        sup = {"records": [{"task_id": "a", "runs": {"C": {}}}, {"task_id": "b", "runs": {}}]}
        text = "\n".join(_render_section_4d(sup))
        assert "4d 节省略" in text and "2 条记录" in text
        assert "## 4d." not in text

    def test_cplus_rows_render_the_table_and_no_omission_note(self):
        sup = {
            "records": [
                {
                    "task_id": "t1",
                    "runs": {"C+": {"status": "pass", "n_passed": 5, "n_failed": 0, "extra_symbols": ["sys"]}},
                }
            ]
        }
        text = "\n".join(_render_section_4d(sup))
        assert "## 4d." in text and "C+ 全过任务数：**1/1**" in text
        assert "省略" not in text

    def test_rows_without_runs_key_are_still_counted_in_the_denominator(self):
        """`"C+" in (r.get("runs") or {})` 的口径：runs 缺失的行不进表，但节仍按可用行渲染。"""
        sup = {"records": [{"task_id": "a"}, {"task_id": "b", "runs": {"C+": {"status": "fail"}}}]}
        text = "\n".join(_render_section_4d(sup))
        assert "## 4d." in text and "C+ 全过任务数：**0/1**" in text
        assert "`a`" not in text


class TestRealPathUnchanged:
    """真工件（盘上补充测量）走的是"全部可核验"路径：不得出现任何省略披露。"""

    REPO = Path(__file__).resolve().parent.parent

    def test_committed_supplement_still_renders_section_4d(self):
        p = self.REPO / "experiments/results/emse_ult_gold_diagnosis_20261015/SUPPLEMENT_CORRECTED_PRELUDE.json"
        if not p.is_file():  # 工件不在树上 → 本锁不适用（显式失败，不空转给"通过"）
            pytest.fail(f"入库补充测量工件缺失：{p}（该锁的意义就是钉住真路径逐字不变）")
        text = "\n".join(_render_section_4d(json.loads(p.read_text(encoding="utf-8"))))
        assert "## 4d." in text and "省略" not in text

    def test_committed_mutk_still_renders_section_4c(self):
        p = self.REPO / "experiments/results/emse_ult_gold_diagnosis_20261015/SUPPLEMENT_GENERATED_MUTK.json"
        if not p.is_file():
            pytest.fail(f"入库 Mut@k 重基工件缺失：{p}")
        text = "\n".join(_render_section_4c(p))
        assert "## 4c." in text and "省略" not in text
