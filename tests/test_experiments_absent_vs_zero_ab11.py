"""AB-11 回归锁：值域与归属侧的"缺席 / 读不动"不得报成"无漂移 / 零命中 / unknown"（2026-10-20）。

AB-9 普查（`docs/reviews/EXPERIMENTS_JSON_DOMAIN_AB9_2026-10-20.md`）登记、AB-10 撤销
"未普查"后剩下的三处站点，本轮逐处换判据：

- 站点 a `experiments/analyze_t1_b2_main_batch.py`：profile 预设读不到时四种机制
  （git 取不到 / AST 解析不了 / 字面量求值失败 / 赋值缺席）塌缩成同一句话，且
  **档名缺席**曾直接落到"无漂移"分支；
- 站点 b `experiments/emse_docstring_augment_analysis.py`：审计字段"键缺席"与
  "生产者写了 null"同桶，第二遍读不动时整臂静默留在 `none`，报告读作"增广零命中"；
- 站点 c `experiments/mast_trace_analysis.py`：一个坏行让整份 trace 作废且不报作废
  了多少，损坏文件一律归 `unknown` 臂（与同文件渲染出的"计入各臂 damaged"陈述相互
  矛盾）。

判据沿用 AB-9/AB-10：**分析层宁可响亮失败或明写"无法核验"，也不要一个看起来正常的
错数字**。全部改动在真路径上零读数变化——入库工件受 SHA256SUMS 保护，本轮不重写任何
工件，只按"同输入前后等价"复算（见 `TestRealPathInvariants`）。

判据 = **删掉对应守卫必然转红**（变异验证逐处打印变红用例名，sha256 断言字节还原）。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import experiments.analyze_t1_b2_main_batch as t1_mod
import experiments.emse_docstring_augment_analysis as aug_mod
from experiments.analyze_t1_b2_main_batch import _profile_drift, _profile_presets
from tests._corpus_guard import require_history
from experiments.emse_docstring_augment_analysis import (
    AUDIT_KEY_ABSENT,
    AUDIT_UNREADABLE,
    CONTROL_ARM,
    PRIMARY_ARM,
    build_analysis,
    load_augment_rows,
)
from experiments.emse_docstring_augment_analysis import render_markdown as render_aug_md
from experiments.mast_trace_analysis import analyze_traces, parse_trace_file
from experiments.mast_trace_analysis import render_markdown as render_mast_md

_ROOT = Path(__file__).resolve().parents[1]
_AUG_DIR = _ROOT / "experiments/results/emse_docstring_augment_20261017"
_DF_BATCH = _AUG_DIR / "benchmark_quixbugs_20261017_221948.json"
_AUG_BATCH = _AUG_DIR / "benchmark_quixbugs_20261017_221735.json"
_AUG_REPORT = _AUG_DIR / "DF_AUG_REPORT.json"
_AUG_REPORT_MD = _AUG_DIR / "DF_AUG_REPORT.md"
_T1_REPORT = _ROOT / "experiments/results/t_round_b2_main_batch_20261018/ANALYSIS_REPORT.json"
_OLD_REV = "b533cff1c316e8e80db635a1b2946610b211a5b6"
_NEW_REV = "a93c1f60ee31b9582e0146f73e3038e6ce0f01a1"
_MAIN_TRACES = _ROOT / "experiments/results/main_batch/traces"
_MAST_REPORT = _ROOT / "experiments/results/main_batch/mast_distribution_report.md"
# AB-11a 普查里"含损坏 trace"的 5 个入库目录（各 1 个坏行文件；值 = 坏行前已解析记录数）
_DAMAGED_DIRS = {
    "experiments/results/cross_file_ab_level3/cross_file_off/traces": 5,
    "experiments/results/emse_ult_specir_probe_20261014/traces": 9,
    "experiments/results/rag_lvl25h_n40_g8batch/traces": 16,
    "experiments/results/spec_ab_scale87_20261012/ult_lite46_off/traces": 9,
    "experiments/results/spec_ab_scale87_20261012/ult_lite46_replace/traces": 5,
}


def _require(path: Path) -> Path:
    """入库工件必须在场——缺席是环境事实，用 fail 说明"本锁未执行"，不用 skip 蒙数。"""
    if not path.exists():
        pytest.fail(f"入库工件缺失，本锁未执行：{path}")
    return path


def _fake_git(monkeypatch: pytest.MonkeyPatch, stdout: str) -> None:
    """把 `git show <rev>:config.py` 换成给定文本（git 输出即本轮的协作边界）。"""

    def fake_run(*a: Any, **k: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(t1_mod.subprocess, "run", fake_run)


# ─── 站点 a：profile 预设的值域与归因 ───────────────────────────────────────
class TestProfilePresetReturnDomain:
    def test_success_has_empty_reason(self) -> None:
        presets, reason = _profile_presets("HEAD")
        assert presets and "logic" in presets, "HEAD 的 `_PROFILE_PRESETS` 读不到时本锁不成立"
        assert reason == ""

    def test_git_show_failure_names_its_mechanism(self) -> None:
        presets, reason = _profile_presets("0" * 40)
        assert presets == {}
        assert reason.startswith("git_show_failed:"), reason

    def test_ast_parse_failure_names_its_mechanism(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_git(monkeypatch, "def ( unterminated\n")
        presets, reason = _profile_presets("deadbeef")
        assert presets == {}
        assert reason.startswith("ast_parse_failed:"), reason

    def test_literal_eval_failure_names_its_mechanism(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_git(monkeypatch, "def f():\n    return 1\n_PROFILE_PRESETS = f()\n")
        presets, reason = _profile_presets("deadbeef")
        assert presets == {}
        assert reason.startswith("literal_eval_failed:"), reason

    def test_missing_assignment_names_its_mechanism(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_git(monkeypatch, "X = 1\n")
        presets, reason = _profile_presets("deadbeef")
        assert presets == {}
        assert reason == "assignment_not_found", reason

    def test_absent_profile_name_is_not_read_as_no_drift(self) -> None:
        """档名在两侧预设表里都不存在 ⇒ 无法核验，而不是"该档无漂移"。"""
        # BZ 轮：两个历史切点 rev 必须在 git 对象库里——shallow clone
        # （actions/checkout 默认 fetch-depth=1）里 `git show <rev>` 必败，
        # 此时"读不到预设"是环境事实而不是被测行为 ⇒ 显式 skip 并点名缺哪个
        # rev（tests/_corpus_guard.require_history）。
        require_history(_OLD_REV, _NEW_REV)
        out = _profile_drift(_OLD_REV, _NEW_REV, "no_such_profile")
        assert out["available"] is False
        assert "档名缺席不等于该档无漂移" in out["reason"]
        assert "added" not in out and "changed" not in out

    def test_unreadable_side_names_which_rev_and_why(self) -> None:
        out = _profile_drift("deadbeef", _NEW_REV)
        assert out["available"] is False
        assert "deadbee" in out["reason"] and "git_show_failed" in out["reason"]
        assert "不得当作无漂移" in out["reason"]

    def test_real_revs_still_report_drift(self) -> None:
        # BZ 轮：同 test_absent_profile_name_is_not_read_as_no_drift——历史
        # 切点不在对象库（shallow clone）时显式 skip，不把"读不到"折成漂移读数。
        require_history(_OLD_REV, _NEW_REV)
        out = _profile_drift(_OLD_REV, _NEW_REV)
        assert out["available"] is True and out["added"], "R-P0-2 切点起 logic 档确有新增开关"


class TestProfileDriftRendering:
    """两处渲染站点（§0.5.2 正文与 §5 局限条目）都必须把记录下的原因带出来。"""

    def test_section_052_prints_recorded_reason(self) -> None:
        report = _t1_report()
        report["profile_preset_drift"] = {
            "available": False,
            "reason": "档位 'logic' 在旧切点的 `_PROFILE_PRESETS` 里不存在（档名缺席不等于该档无漂移）",
        }
        text = t1_mod.render_readme(report)
        assert "profile 预设漂移无法核验（档位 'logic' 在旧切点的" in text
        assert "（档名缺席不等于该档无漂移））——不得当作无漂移。" in text

    def test_limitation_bullet_prints_recorded_reason(self) -> None:
        report = _t1_report()
        report["profile_preset_drift"] = {"available": False, "reason": "deadbee:git_show_failed:CalledProcessError"}
        text = t1_mod.render_readme(report)
        assert (
            "- profile 预设漂移：**无法核验**（deadbee:git_show_failed:CalledProcessError），不得当作无漂移。" in text
        )

    def test_missing_reason_is_reported_as_unrecorded(self) -> None:
        """旧报告只有 available=False 而无 reason ⇒ 两处都明写"原因未记录"，不冒充核验过。"""
        report = _t1_report()
        report["profile_preset_drift"] = {"available": False}
        text = t1_mod.render_readme(report)
        assert "profile 预设漂移无法核验（原因未记录）——不得当作无漂移。" in text
        assert "- profile 预设漂移：**无法核验**（原因未记录），不得当作无漂移。" in text

    def test_available_drift_is_not_rendered_as_unverifiable(self) -> None:
        report = _t1_report()
        report["profile_preset_drift"] = {"available": True, "added": {"K": "1"}, "profile": "logic"}
        text = t1_mod.render_readme(report)
        assert "无法核验" not in text and "新增 **1** 个行为开关" in text


def _t1_report() -> dict[str, Any]:
    """归档 ANALYSIS_REPORT.json 的内存副本（只读工件；render 不落盘）。"""
    return json.loads(_require(_T1_REPORT).read_text(encoding="utf-8"))


# ─── 站点 b：审计字段的值域三态与读不动留痕 ─────────────────────────────────
def _arm_file(tmp_path: Path, arm: str, details: list[dict[str, Any]]) -> Path:
    path = tmp_path / f"{arm}.json"
    path.write_text(json.dumps({"results": {arm: {"details": details}}}), encoding="utf-8")
    return path


class TestAugmentAuditValueDomain:
    def test_absent_key_null_value_and_product_value_are_three_buckets(self, tmp_path: Path) -> None:
        details = [
            {"task_id": "t_absent", "detection_rate": 1.0},
            {"task_id": "t_null", "detection_rate": 1.0, "spec_augment_applied": None},
            {"task_id": "t_hit", "detection_rate": 1.0, "spec_augment_applied": "attempted_augmented"},
        ]
        rows = load_augment_rows(_arm_file(tmp_path, PRIMARY_ARM, details), PRIMARY_ARM)
        assert rows["t_absent"]["spec_augment_applied"] == AUDIT_KEY_ABSENT
        assert rows["t_null"]["spec_augment_applied"] is None
        assert rows["t_hit"]["spec_augment_applied"] == "attempted_augmented"
        assert aug_mod.domain_stats(rows, "spec_augment_applied") == {
            "attempted_augmented": 1,
            "key_absent": 1,
            "none": 1,
        }

    def test_unreadable_second_pass_marks_rows_and_warns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """第二遍原始读取失败 ⇒ 整臂落 `audit_unreadable` 并 stderr 命名，不再是 `none` 假零命中。"""
        details = [
            {"task_id": f"t{i}", "detection_rate": 1.0, "spec_augment_applied": "attempted_augmented"} for i in range(3)
        ]
        path = _arm_file(tmp_path, PRIMARY_ARM, details)
        calls: list[str] = []

        class _FailingJson:
            JSONDecodeError = json.JSONDecodeError

            @staticmethod
            def loads(text: str, *a: Any, **k: Any) -> Any:
                calls.append("loads")
                raise json.JSONDecodeError("injected", text, 0)

        monkeypatch.setattr(aug_mod, "json", _FailingJson)
        rows = load_augment_rows(path, PRIMARY_ARM)
        assert len(calls) == 1, "注入未命中第二遍读取 ⇒ 本锁没测到目标分支"
        assert [r["spec_augment_applied"] for r in rows.values()] == [AUDIT_UNREADABLE] * 3
        assert aug_mod.domain_stats(rows, "spec_augment_applied") == {"audit_unreadable": 3}
        err = capsys.readouterr().err
        assert "audit_unreadable" in err and "不得读成'增广零命中'" in err
        assert "JSONDecodeError" in err, "兜底须带上机制名"

    def test_duplicate_task_id_warns_about_shrunken_rowset(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        details = [
            {"task_id": "t1", "detection_rate": 1.0, "spec_augment_applied": "attempted_augmented"},
            {"task_id": "t1", "detection_rate": 0.0, "spec_augment_applied": "attempted_fallback"},
        ]
        rows = load_augment_rows(_arm_file(tmp_path, PRIMARY_ARM, details), PRIMARY_ARM)
        assert len(rows) == 1, "重复 task_id 静默缩行集正是本警告要暴露的"
        err = capsys.readouterr().err
        assert "details 行 2 / 回填 2 / 行摘要 1" in err and "行集本身已缩" in err

    def test_non_string_task_id_leaves_row_unreadable(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        details = [{"task_id": 7, "detection_rate": 1.0, "spec_augment_applied": "attempted_augmented"}]
        rows = load_augment_rows(_arm_file(tmp_path, PRIMARY_ARM, details), PRIMARY_ARM)
        assert list(rows) == [7], "行摘要按原始 task_id（此处为 int）建键，补齐按 str 查 ⇒ 永不命中"
        assert [r["spec_augment_applied"] for r in rows.values()] == [AUDIT_UNREADABLE]
        err = capsys.readouterr().err
        assert "其中 1 行未回填" in err

    def test_no_pragma_no_cover_left_in_augment_module(self) -> None:
        """静默兜底改成"有名字的三态"后，不得再用 pragma 把该分支藏出覆盖率。"""
        src = (_ROOT / "experiments/emse_docstring_augment_analysis.py").read_text(encoding="utf-8")
        assert "pragma: no cover" not in src


# ─── 站点 c：损坏 trace 的归臂与作废量披露 ─────────────────────────────────
def _write_trace(path: Path, *, arm: str | None, events: int, broken: bool = False) -> Path:
    lines: list[str] = []
    if arm is not None:
        lines.append(json.dumps({"event": "task_start", "meta": {"dataset_task_id": "t", "baseline": arm}}))
    lines.extend(
        json.dumps({"event": "node", "node": "debugger", "task": "k", "output": {"error_category": f"cat{i}"}})
        for i in range(events)
    )
    if broken:
        lines.append("{not-json")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class TestMastDamageAttribution:
    def test_parse_reports_damage_instead_of_returning_nothing(self, tmp_path: Path) -> None:
        p = _write_trace(tmp_path / "x_aitester_1.trace.jsonl", arm="aitester", events=2, broken=True)
        parsed = parse_trace_file(p)
        assert parsed["damaged"] is True
        assert parsed["damage"] == "JSONDecodeError"
        assert parsed["records_before_damage"] == 3
        assert parsed["arm"] == "aitester"

    def test_clean_file_has_no_damage_flags(self, tmp_path: Path) -> None:
        p = _write_trace(tmp_path / "x_aitester_1.trace.jsonl", arm="aitester", events=1)
        parsed = parse_trace_file(p)
        assert parsed["damaged"] is False and parsed["damage"] is None
        assert parsed["records_before_damage"] == 0

    def test_damaged_file_is_attributed_to_its_arm_not_unknown(self, tmp_path: Path) -> None:
        _write_trace(tmp_path / "a1_aitester_1.trace.jsonl", arm="aitester", events=1)
        _write_trace(tmp_path / "b1_plain_llm_df_2.trace.jsonl", arm=None, events=0, broken=True)
        result = analyze_traces(tmp_path)
        assert result["damaged_files"] == 1
        assert "unknown" not in result["arms"], "文件名可归臂时不得整份落进 unknown"
        assert result["arms"]["plain_llm_df"]["damaged"] == 1
        assert result["arms"]["plain_llm_df"]["files"] == 0

    def test_damaged_records_counted_and_excluded_from_hits(self, tmp_path: Path) -> None:
        _write_trace(tmp_path / "a1_aitester_1.trace.jsonl", arm="aitester", events=1)
        _write_trace(tmp_path / "a2_aitester_2.trace.jsonl", arm="aitester", events=4, broken=True)
        result = analyze_traces(tmp_path)
        assert result["damaged_files_with_records"] == 1
        assert result["damaged_records_before_damage"] == 5, "task_start + 4 事件，坏行前全部作废"
        a = result["arms"]["aitester"]
        assert a["files"] == 1 and a["damaged"] == 1, "损坏文件的记录不得混进有效分母"
        assert sum(a["category_files"].values()) == 1, "命中面只来自完好的那一份"

    def test_disclosure_line_appears_only_when_damaged(self, tmp_path: Path) -> None:
        clean = tmp_path / "clean"
        clean.mkdir()
        _write_trace(clean / "a1_aitester_1.trace.jsonl", arm="aitester", events=1)
        text = "\n".join(render_mast_md(analyze_traces(clean), clean))
        assert "损坏留痕" not in text, "无损坏时不得凭空加披露行（入库报告零变化）"
        dirty = tmp_path / "dirty"
        dirty.mkdir()
        _write_trace(dirty / "a1_aitester_1.trace.jsonl", arm="aitester", events=1, broken=True)
        text = "\n".join(render_mast_md(analyze_traces(dirty), dirty))
        assert "- 损坏留痕：1 个损坏文件在坏行之前已解析出 2 条记录" in text
        assert "损坏计入各臂 damaged，不静默丢弃" in text


class TestRealPathInvariants:
    """真路径不变性：入库工件的读数与本轮改动无关（受 SHA256SUMS 保护，绝不重写）。"""

    def test_augment_audit_buckets_match_committed_report(self, capsys: pytest.CaptureFixture[str]) -> None:
        _require(_DF_BATCH)
        _require(_AUG_BATCH)
        committed = json.loads(_require(_AUG_REPORT).read_text(encoding="utf-8"))
        df_rows = load_augment_rows(_DF_BATCH, CONTROL_ARM)
        aug_rows = load_augment_rows(_AUG_BATCH, PRIMARY_ARM)
        got = {
            "df": aug_mod.domain_stats(df_rows, "spec_augment_applied"),
            "augment": aug_mod.domain_stats(aug_rows, "spec_augment_applied"),
        }
        assert got["df"] == committed["audit"]["spec_augment_applied"]["df"] == {"none": 50}
        assert got["augment"] == committed["audit"]["spec_augment_applied"]["augment"]
        assert AUDIT_KEY_ABSENT not in str(got) and AUDIT_UNREADABLE not in str(got)
        assert capsys.readouterr().err == "", "真工件上不得新产生任何 WARN"

    def test_committed_augment_report_is_reproducible(self) -> None:
        """同输入复算 ⇒ 除两条输入路径外逐字段相同，且 Markdown 逐字相同。"""
        _require(_DF_BATCH)
        _require(_AUG_BATCH)
        committed = json.loads(_require(_AUG_REPORT).read_text(encoding="utf-8"))
        fresh = build_analysis(_DF_BATCH, _AUG_BATCH)
        for entry in committed["inputs"].values():
            entry["path"] = "<normalized>"
        for entry in fresh["inputs"].values():
            entry["path"] = "<normalized>"
        assert fresh == committed
        assert render_aug_md(fresh) == _require(_AUG_REPORT_MD).read_text(encoding="utf-8")

    @pytest.mark.parametrize("rel", sorted(_DAMAGED_DIRS))
    def test_damaged_dir_census(self, rel: str) -> None:
        d = _require(_ROOT / rel)
        result = analyze_traces(d)
        files = list(d.glob("*.trace.jsonl"))
        assert result["total_files"] == len(files)
        assert result["damaged_files"] == 1
        assert result["damaged_files_with_records"] == 1
        assert result["damaged_records_before_damage"] == _DAMAGED_DIRS[rel]
        assert "unknown" not in result["arms"]
        assert sum(v["files"] for v in result["arms"].values()) == len(files) - 1
        assert sum(v["damaged"] for v in result["arms"].values()) == 1
        assert "- 损坏留痕" in "\n".join(render_mast_md(result, d))

    def test_main_batch_traces_have_no_damage_and_no_disclosure(self) -> None:
        _require(_MAIN_TRACES)
        result = analyze_traces(_MAIN_TRACES)
        assert result["damaged_files"] == 0
        assert result["total_files"] == len(list(_MAIN_TRACES.glob("*.trace.jsonl")))
        assert "损坏留痕" not in "\n".join(render_mast_md(result, _MAIN_TRACES))

    def test_committed_mast_report_census_is_stale_and_registered(self) -> None:
        """入库报告写 963 个文件，而该目录现有 trace 更多 ⇒ "逐位复算"陈述已过期（登记，不重写）。"""
        text = _require(_MAST_REPORT).read_text(encoding="utf-8")
        assert "963 个 trace 文件" in text, "入库工件不得就地改，读数应保持登记时快照"
        assert "逐位复算" in text
        assert len(list(_require(_MAIN_TRACES).glob("*.trace.jsonl"))) > 963, "目录回落后须撤销本登记"
