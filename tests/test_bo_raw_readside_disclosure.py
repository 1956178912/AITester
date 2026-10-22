"""BO（2026-10-22）：raw 落盘面的读侧把"工件缺席"折成判定值 —— 披露锁。

缺陷族（BH→BN 系列第 7 面，落点是 **raw 读侧** 与 **落盘开关态的可复核性**）。
改前实测（`scripts/tools/bo_raw_readside_fold_probe.py`，Python 3.14.6，零 LLM）：

1. **开关态从不落盘**：`--save-state` 决定 `raw/<task_id>/<baseline>.json` 到底存
   不存在，但 246 份归档批次 JSON 里 `save_state` 类键出现 **0 次**，provenance 的
   15 个键里也没有它；raw 是否随归档留存还是**逐批次**事实（磁盘 34 个 raw/ 目录，
   只有 88 份文件入库，`.gitignore:172` 忽略 `experiments/results/**`）⇒ 事后既不能
   证明"当初没落盘"，也不能证明"落盘了但没归档"。
2. **根因归因由缺席造出**：`cross_file_root_cause._classify_root_cause` 用
   `(state or {}).get("cross_file_deps") or []` 取边，于是"没给 raw""件不存在"
   "件损坏""键根本没写""键写的是 null"五种没测到全塌成 `len([]) == 0` 的一次实测。
   不带 raw 复放 9 臂 29 例失败 ⇒ **14 例**被判 `DEP_GRAPH_INCOMPLETE`（level1 单文件
   对照 0 例）；带 raw 的 `cross_file_ab_level3` 两臂 7/7 失败任务该键根本不存在。
3. **定位读数由缺席造出**：`position_aware_ab._locate_accuracy` 四条"没测到"腿
   （raw 目录缺席 / 任务件缺席 / focus 键缺席 / 件不可读）全部返回 **0.0**，与
   "测了、确实一次没命中"逐字节同形；另有一条更隐蔽——BN 起白名单恒写 focus 键，
   值为 null 时只要该行有 iterations/patch 就**进分母记成一次未命中**。
4. **失败对比报告只披露一半**：`compare_failures` 只在**两臂都缺**时写一行"环节级
   产物缺失"，一臂可读时另一臂的"没落盘/件损坏"渲染成什么都没有（读起来像"那一臂
   确实没有产物"）；一份损坏 raw JSON 直接 `json.load` 抛穿 ⇒ 整份报告中断；
   合法空产物 `{}` 与"件不存在"同形。
5. **推荐命令自拆证据**：`cross_file_ab.py` 打印的后续分析命令不带 `--raw-dir`，
   照它执行就正好落进上面那条折叠。

修复口径（与前六轮同族）：**缺席只做披露，不做归因、不做判定、不做崩溃**。
判定方向一律不动——单文件任务不经结构档、真写过 `[]` 的依赖图照旧判
`DEP_GRAPH_INCOMPLETE`、8 个归档 A/B 臂的定位读数复算逐位相同
（21.43/0.0、0.0/0.0、25.0/0.0、-1.0/-1.0）；磁盘上的历史工件一字节没动，
`save_state` 只对新批次生效。
"""

from __future__ import annotations

import json
import logging
import sys
import types
from pathlib import Path
from typing import Any, ClassVar

import pytest

import experiments.run_benchmark as rb
from experiments.compare_failures import build_report, load_state_artifact, load_state_artifact_status
from experiments.cross_file_root_cause import (
    STRUCTURAL_INPUTS,
    _classify_root_cause,
    _load_state,
    analyze,
)
from experiments.cross_file_root_cause import (
    main as root_cause_main,
)
from experiments.position_aware_ab import (
    _GRADE_TEXT,
    _locate_accuracy,
    _locate_stats,
    _locate_text,
    _render_markdown,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS = PROJECT_ROOT / "experiments" / "results"

#: 归档 PA 批次（探针 C/C2 段的同一批），仅本地留存 ⇒ 缺件即 skip
PA_BATCHES: tuple[str, ...] = (
    "pa_l25h_n40_g8batch",
    "position_aware_synthetic",
    "pa_l25h_n40",
    "position_aware_ab_l25_small",
)

_PATCH = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old-long-enough-line\n+new-long-enough-line\n"


def _multi_row(task_id: str = "synthetic__x_0001", num_files: int = 3) -> dict[str, Any]:
    """一条多文件失败结果行：不经 1/2 两腿，必然落到结构档。"""
    return {
        "task_id": task_id,
        "passed": False,
        "error_category": "assertion",
        "patch": _PATCH,
        "iterations": 2,
        "task_metadata": {"num_files": num_files, "difficulty": "level3"},
    }


def _write_raw(arm_dir: Path, task_id: str, payload: Any, baseline: str = "aitester") -> None:
    d = arm_dir / "raw" / task_id
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{baseline}.json").write_text(
        payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


# ═══ 1. 开关态落盘：--save-state 必须可从批次工件复核 ════════════════════════


class _OfflineAPI:
    """`src.api.api_manager` 替身：任何调用直接抛错（探针只留 error，不发真实请求）。"""

    instances: ClassVar[list[Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        type(self).instances.append(self)

    def call(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        raise RuntimeError("offline-stub")


class _StubDataset:
    """空任务批次替身：`size` 非 0 以避开"空数据集 ⇒ 降级内置 examples"分支。"""

    size = 1
    tasks: ClassVar[list[Any]] = []
    strict_skipped_task_ids: ClassVar[list[str]] = []


@pytest.fixture()
def offline_batch(monkeypatch: pytest.MonkeyPatch):
    """零 LLM、零网络的 run_benchmark 环境（同 tests/test_model_fingerprint.py 口径）。"""

    def _run(tmp_path: Path, **kwargs: Any) -> dict[str, Any]:
        fake_module = types.ModuleType("src.api.api_manager")
        fake_module.APIManager = _OfflineAPI  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "src.api.api_manager", fake_module)
        monkeypatch.setenv("AITESTER_LLM_CACHE", "0")
        monkeypatch.setattr(rb, "load_dataset", lambda *a, **k: _StubDataset())
        return rb.run_benchmark(
            dataset_name="swe_bench",
            baselines=["plain_llm"],
            output_dir=str(tmp_path),
            parallel=1,
            **kwargs,
        )

    return _run


class TestSwitchStateProvenance:
    """`save_state` 进 provenance：值可复核，且只加在 provenance 面。"""

    def test_default_is_recorded_false_in_memory_and_on_disk(self, offline_batch, tmp_path):
        summary = offline_batch(tmp_path)
        assert summary["provenance"]["save_state"] is False
        out = next(tmp_path.glob("benchmark_*.json"))
        on_disk = json.loads(out.read_text(encoding="utf-8"))["provenance"]
        # 工件是审计对象，不是内存态：两侧必须同值
        assert on_disk["save_state"] is False

    def test_switch_on_is_recorded_true(self, offline_batch, tmp_path):
        summary = offline_batch(tmp_path, save_state=True)
        assert summary["provenance"]["save_state"] is True
        out = next(tmp_path.glob("benchmark_*.json"))
        assert json.loads(out.read_text(encoding="utf-8"))["provenance"]["save_state"] is True

    @pytest.mark.parametrize(("given", "expected"), [(1, True), ("", False), (None, False)])
    def test_field_is_a_strict_bool_not_the_raw_argument(self, offline_batch, tmp_path, given, expected):
        """摘掉 `bool(...)` 就让非布尔入参原样进工件（`1 is True` 为假 ⇒ identity 才锁得住）。"""
        summary = offline_batch(tmp_path, save_state=given)
        assert summary["provenance"]["save_state"] is expected

    def test_summary_top_key_surface_unchanged(self, offline_batch, tmp_path):
        """新键只进 provenance，summary 顶层面一个不动（登记册里 16 键是可复核面）。"""
        summary = offline_batch(tmp_path, save_state=True)
        assert "save_state" not in summary
        assert "save_state" in summary["provenance"]


# ═══ 2. cross_file_root_cause：件级/键级缺席与真测空的分级 ═══════════════════


class TestStateReaderStatuses:
    """`_load_state` 的 status 取值域——五种"读不到"不得塌成同一种。"""

    def test_no_raw_dir(self):
        assert _load_state(None, "t") == (None, "no_raw_dir")

    def test_file_absent(self, tmp_path):
        (tmp_path / "t").mkdir()
        assert _load_state(str(tmp_path), "t") == (None, "file_absent")

    def test_corrupt_json_is_unreadable_and_does_not_raise(self, tmp_path):
        _write_raw(tmp_path, "t", "{ not json")
        assert _load_state(str(tmp_path / "raw"), "t") == (None, "unreadable")

    def test_top_level_non_object_is_unreadable(self, tmp_path):
        # 历史手改 / 截断件：顶层是 list 时旧写法会让下游 .get 炸穿。
        _write_raw(tmp_path, "t", [1, 2, 3])
        assert _load_state(str(tmp_path / "raw"), "t") == (None, "unreadable")

    def test_ok_returns_the_dict(self, tmp_path):
        _write_raw(tmp_path, "t", {"cross_file_deps": []})
        state, status = _load_state(str(tmp_path / "raw"), "t")
        assert status == "ok"
        assert state == {"cross_file_deps": []}


class TestRootCauseGrading:
    """结构档判据：只有"节点真写过"才配得上一次归因。"""

    def test_state_none_is_disclosure_not_attribution(self):
        # 改前：RAW_UNAVAILABLE 这一档根本不存在，缺席被折成"实测 0 条边"。
        assert _classify_root_cause(_multi_row(), None) == "RAW_UNAVAILABLE"

    def test_key_absent_is_distinguished_from_file_absent(self):
        assert _classify_root_cause(_multi_row(), {}) == "DEP_INPUT_ABSENT"

    def test_key_present_as_null_is_its_own_leg(self):
        """BN 起白名单恒写该键 ⇒ 键在不等于记录过，null 不能读成 0 条边。"""
        assert _classify_root_cause(_multi_row(), {"cross_file_deps": None}) == "DEP_INPUT_NULL"

    def test_recorded_empty_graph_still_attributes(self):
        # nodes.py:2211 `cross_file_deps: []` = "AST 与预置边都分析过、确实没边"，
        # 这一档必须保持可达，否则就是把真测到的缺陷也一并沉默。
        assert _classify_root_cause(_multi_row(), {"cross_file_deps": []}) == "DEP_GRAPH_INCOMPLETE"

    def test_incomplete_graph_still_attributes(self):
        deps = [{"source_module": "a", "target_module": "b"}]
        assert _classify_root_cause(_multi_row(num_files=3), {"cross_file_deps": deps}) == "DEP_GRAPH_INCOMPLETE"

    def test_complete_graph_reaches_the_capability_bucket(self):
        deps = [
            {"source_module": "a", "target_module": "b"},
            {"source_module": "b", "target_module": "c"},
        ]
        assert _classify_root_cause(_multi_row(num_files=3), {"cross_file_deps": deps}) == "LLM_CAPABILITY"

    def test_single_file_task_never_enters_the_structural_bucket(self):
        """level1 对照（复放实测翻转 0 例）：单文件判定逐位不变。"""
        assert _classify_root_cause(_multi_row(num_files=1), None) == "LLM_CAPABILITY"
        assert _classify_root_cause(_multi_row(num_files=1), {}) == "LLM_CAPABILITY"

    @pytest.mark.parametrize(
        ("row", "expected"),
        [
            ({"task_id": "t", "passed": False, "error_category": "import", "patch": _PATCH}, "LLM_BREAKS_IMPORT"),
            (
                {"task_id": "t", "passed": False, "error_category": "empty_llm_patch", "patch": _PATCH},
                "EMPTY_LLM_PATCH",
            ),
            ({"task_id": "t", "passed": False, "error_category": "assertion", "patch": "short"}, "EMPTY_LLM_PATCH"),
        ],
    )
    def test_result_row_legs_keep_priority_over_the_structural_bucket(self, row, expected):
        row["task_metadata"] = {"num_files": 3}
        assert _classify_root_cause(row, None) == expected


class TestAnalyzeSelfCertification:
    """报告必须自证"这批到底用了多少 raw"、哪些档零证据。"""

    def test_without_raw_no_completion_claim_is_made(self, tmp_path):
        report = analyze([_multi_row("t1"), _multi_row("t2")], None, difficulty="")
        assert report["root_cause_distribution"] == {"RAW_UNAVAILABLE": 2}
        assert "DEP_GRAPH_INCOMPLETE" not in report["root_cause_distribution"]
        cov = report["raw_coverage"]
        assert cov["raw_dir"] is None
        assert cov["by_status"] == {"no_raw_dir": 2}
        assert cov["state_available"] == 0 and cov["state_unavailable"] == 2
        # "没测"写 null，不写 0（那个被折出来的 0 正是判成 DEP_GRAPH_INCOMPLETE 的一步）
        assert [d["dep_edges"] for d in report["details"]] == [None, None]
        assert {d["raw_state_status"] for d in report["details"]} == {"no_raw_dir"}
        assert report["unreachable_rules"] == [
            "DEP_GRAPH_INCOMPLETE",
            "ROLLBACK_CONSERVATIVE",
            "TOPOLOGICAL_ORDER",
        ]

    def test_key_present_but_null_counts_as_no_evidence(self, tmp_path):
        _write_raw(tmp_path, "t1", {"cross_file_deps": None})
        report = analyze([_multi_row("t1")], str(tmp_path / "raw"), difficulty="")
        assert report["root_cause_distribution"] == {"DEP_INPUT_NULL": 1}
        ev = report["rule_evidence"]["cross_file_deps"]
        # 键在场（BN 默认档）与真有取值是两件事，两个计数各说各的
        assert ev["states_with_key"] == 1
        assert ev["states_recorded"] == 0
        assert ev["reachable"] is False
        assert "DEP_GRAPH_INCOMPLETE" in report["unreachable_rules"]
        assert report["details"][0]["dep_edges"] is None

    def test_recorded_edges_make_the_bucket_reachable(self, tmp_path):
        _write_raw(tmp_path, "t1", {"cross_file_deps": []})
        report = analyze([_multi_row("t1")], str(tmp_path / "raw"), difficulty="")
        assert report["root_cause_distribution"] == {"DEP_GRAPH_INCOMPLETE": 1}
        assert report["rule_evidence"]["cross_file_deps"]["reachable"] is True
        assert report["details"][0]["dep_edges"] == 0
        assert "DEP_GRAPH_INCOMPLETE" not in report["unreachable_rules"]

    def test_rollback_and_topology_are_zero_evidence_by_construction(self, tmp_path):
        """两档的输入从未进过 raw 白名单 ⇒ 任何批次都不可达，必须点名。"""
        _write_raw(tmp_path, "t1", {"cross_file_deps": [{"source_module": "a", "target_module": "b"}]})
        report = analyze([_multi_row("t1")], str(tmp_path / "raw"), difficulty="")
        assert report["unreachable_rules"] == ["ROLLBACK_CONSERVATIVE", "TOPOLOGICAL_ORDER"]
        for key in ("per_module_patches", "applied_modules"):
            ev = report["rule_evidence"][key]
            assert ev["states_available"] == 1 and ev["states_with_key"] == 0 and ev["reachable"] is False

    def test_the_unreachable_claim_is_grounded_in_the_dump_whitelist(self, tmp_path):
        """锁住依据本身：落盘边界只透传 cross_file_deps，另两键被丢弃。"""
        task = types.SimpleNamespace(task_id="t1", metadata={"difficulty": "level3"})
        rb._dump_state_artifacts(
            str(tmp_path),
            task,
            "aitester",
            {"cross_file_deps": [], "per_module_patches": {"a": "p"}, "applied_modules": ["a"]},
        )
        data = json.loads((tmp_path / "raw" / "t1" / "aitester.json").read_text(encoding="utf-8"))
        assert "cross_file_deps" in data
        assert set(STRUCTURAL_INPUTS) - set(data) == {"per_module_patches", "applied_modules"}

    def test_mixed_statuses_are_counted_separately(self, tmp_path):
        rows = [_multi_row("ok"), _multi_row("absent"), _multi_row("broken"), _multi_row("nokey")]
        _write_raw(tmp_path, "ok", {"cross_file_deps": [{"source_module": "a", "target_module": "b"}]})
        _write_raw(tmp_path, "broken", "{ not json")
        _write_raw(tmp_path, "nokey", {"patch": "x"})
        report = analyze(rows, str(tmp_path / "raw"), difficulty="")
        assert report["raw_coverage"]["by_status"] == {"ok": 2, "unreadable": 1, "file_absent": 1}
        assert report["raw_coverage"]["state_available"] == 2
        assert report["raw_coverage"]["state_unavailable"] == 2
        assert report["root_cause_distribution"] == {
            "RAW_UNAVAILABLE": 2,  # 件不存在 + 件损坏，两种没测到同名不同数
            "DEP_INPUT_ABSENT": 1,
            "DEP_GRAPH_INCOMPLETE": 1,
        }
        assert {d["task_id"]: d["dep_edges"] for d in report["details"]} == {
            "ok": 1,
            "absent": None,
            "broken": None,
            "nokey": None,
        }

    def test_main_warns_when_no_raw_dir_is_given(self, tmp_path, caplog, monkeypatch):
        """docstring 承诺的降级必须可见：静默换档等于让读者以为做了归因。"""
        results = tmp_path / "benchmark_x.json"
        results.write_text(
            json.dumps({"results": {"aitester": {"details": [dict(_multi_row("t1"))]}}}, ensure_ascii=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            sys, "argv", ["cross_file_root_cause.py", "--results-on", str(results), "--difficulty", "level3"]
        )
        with caplog.at_level(logging.WARNING, logger="experiments.cross_file_root_cause"):
            root_cause_main()
        assert "未提供 --raw-dir" in caplog.text


# ═══ 3. position_aware_ab：定位读数分档，不再用 0.0 冒充没测 ═════════════════


def _pa_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"results": {"aitester": {"details": rows}}}


class TestLocateGrades:
    """四条"没测到"腿 + 一条 null 腿，各自分档；`measured` 是唯一给百分数的档。"""

    def test_raw_dir_absent(self, tmp_path):
        stats = _locate_stats(str(tmp_path / "no_such"), _pa_summary([{"task_id": "t"}]))
        assert (stats["grade"], stats["accuracy_pct"], stats["n_used"]) == ("raw_dir_absent", -1.0, 0)
        assert dict(stats["skipped"]) == {}

    def test_task_artifact_absent(self, tmp_path):
        (tmp_path / "raw").mkdir()
        stats = _locate_stats(str(tmp_path), _pa_summary([{"task_id": "t", "iterations": 2}]))
        assert stats["grade"] == "state_file_absent"
        assert stats["accuracy_pct"] == -1.0 and dict(stats["skipped"]) == {"state_file_absent": 1}

    @pytest.mark.parametrize("payload", ["{ not json", [1, 2, 3]])
    def test_unreadable_artifact_does_not_raise(self, tmp_path, payload):
        _write_raw(tmp_path, "t", payload)
        stats = _locate_stats(str(tmp_path), _pa_summary([{"task_id": "t", "iterations": 2}]))
        assert stats["grade"] == "state_unreadable" and stats["accuracy_pct"] == -1.0

    def test_focus_key_absent_is_not_charged_as_a_miss(self, tmp_path):
        _write_raw(tmp_path, "t", {"task_metadata": {"suggested_function": "divide"}})
        stats = _locate_stats(str(tmp_path), _pa_summary([{"task_id": "t", "iterations": 2}]))
        assert stats["grade"] == "focus_key_absent"
        assert stats["n_used"] == 0  # 改前：进分母记成未命中 ⇒ 读数被压低成 0.0%

    def test_null_focus_on_a_repaired_row_is_not_charged_as_a_miss(self, tmp_path):
        """BN 恒写键 ⇒ 键在值为 null 也算没记录；这条腿改前正是"没测折进测了且跑偏"。"""
        _write_raw(tmp_path, "t", {"position_aware_focus": None})
        repaired = _pa_summary([{"task_id": "t", "iterations": 3, "patch": _PATCH}])
        stats = _locate_stats(str(tmp_path), repaired)
        assert stats["grade"] == "focus_not_recorded" and stats["accuracy_pct"] == -1.0
        assert stats["n_used"] == 0

    def test_null_focus_on_an_unrepaired_row_keeps_the_legacy_bucket(self, tmp_path):
        """归档八臂全靠这条不变才谈得上"读数逐位相同"（156 例 null 全部无轮次无补丁）。"""
        _write_raw(tmp_path, "t", {"position_aware_focus": None})
        stats = _locate_stats(str(tmp_path), _pa_summary([{"task_id": "t"}]))
        assert stats["grade"] == "not_repaired"
        assert dict(stats["skipped"]) == {"not_repaired": 1}

    def test_patch_without_iterations_still_counts_as_repaired(self, tmp_path):
        """轮次与补丁是两个证据：0 轮即返回但带了补丁的行，也算"这轮修过"。"""
        _write_raw(tmp_path, "t", {"position_aware_focus": None})
        stats = _locate_stats(str(tmp_path), _pa_summary([{"task_id": "t", "iterations": 0, "patch": _PATCH}]))
        assert stats["grade"] == "focus_not_recorded"
        assert stats["n_used"] == 0

    def test_recorded_miss_is_a_real_measurement(self, tmp_path):
        _write_raw(
            tmp_path,
            "t",
            {
                "position_aware_focus": {"focused": False, "function_name": "other"},
                "task_metadata": {"suggested_function": "divide"},
            },
        )
        stats = _locate_stats(str(tmp_path), _pa_summary([{"task_id": "t", "iterations": 2}]))
        assert (stats["grade"], stats["accuracy_pct"], stats["n_used"], stats["n_hit"]) == ("measured", 0.0, 1, 0)

    def test_hit_is_measured(self, tmp_path):
        _write_raw(
            tmp_path,
            "t",
            {
                "position_aware_focus": {"focused": True, "function_name": "divide"},
                "task_metadata": {"suggested_function": "divide"},
            },
        )
        stats = _locate_stats(str(tmp_path), _pa_summary([{"task_id": "t", "iterations": 2}]))
        assert (stats["grade"], stats["accuracy_pct"]) == ("measured", 100.0)

    def test_details_face_forms(self, tmp_path):
        (tmp_path / "raw").mkdir()
        assert _locate_stats(str(tmp_path), {})["grade"] == "details_unavailable"
        assert _locate_stats(str(tmp_path), _pa_summary([]))["grade"] == "no_samples"
        assert _locate_stats(str(tmp_path), _pa_summary([{"iterations": 1}]))["grade"] == "row_unusable"

    def test_compat_layer_only_returns_the_number(self, tmp_path):
        """`_locate_accuracy` 是兼容层：不可计算给 -1.0，绝不给 0.0。"""
        assert _locate_accuracy(str(tmp_path / "no_such"), _pa_summary([{"task_id": "t"}])) == -1.0
        stats = _locate_stats(str(tmp_path / "no_such"), _pa_summary([{"task_id": "t"}]))
        assert _locate_accuracy(str(tmp_path / "no_such"), _pa_summary([{"task_id": "t"}])) == stats["accuracy_pct"]

    def test_compatibility_layer_docstring_counts_the_grades(self):
        """文档里"九种"必须等于实现的档位面：改一档就漏一句说明，说明就成假话。"""
        grades = {key for key in _GRADE_TEXT if key != "measured"}
        assert grades == {
            "not_repaired",
            "focus_key_absent",
            "focus_not_recorded",
            "state_file_absent",
            "state_unreadable",
            "raw_dir_absent",
            "details_unavailable",
            "no_samples",
            "row_unusable",
        }
        assert "九种" in (_locate_accuracy.__doc__ or "")

    def test_grade_texts_are_pairwise_distinct(self):
        """九档文本两两不同：删掉任一条都会退回通用句，与别的档撞成同一句话。"""
        texts = [text for key, text in _GRADE_TEXT.items() if key != "measured"]
        assert len(set(texts)) == len(texts), "读数分档文本互相折叠"

    def test_null_leg_text_names_the_null_and_denies_the_miss(self):
        """这一档必须自己说清两件事：落的是 null、且不能记成实测未命中。"""
        text = _GRADE_TEXT["focus_not_recorded"]
        assert "position_aware_focus" in text and "null" in text
        assert "不能记成实测未命中" in text

    def test_absence_legs_outrank_the_key_legs_in_the_priority_order(self, tmp_path):
        """零分母时点名哪一种缺席：件级缺席比键级缺席更根本，顺序不能被字典序顶掉。"""
        _write_raw(tmp_path, "b", {"position_aware_focus": None})
        _write_raw(tmp_path, "c", {"task_metadata": {}})
        stats = _locate_stats(
            str(tmp_path),
            _pa_summary(
                [
                    {"task_id": "b", "iterations": 2},  # focus_not_recorded
                    {"task_id": "c", "iterations": 2},  # focus_key_absent
                    {"task_id": "ghost", "iterations": 2},  # state_file_absent
                ]
            ),
        )
        assert stats["n_used"] == 0
        assert dict(stats["skipped"]) == {"focus_not_recorded": 1, "focus_key_absent": 1, "state_file_absent": 1}
        assert stats["grade"] == "state_file_absent"

    def test_key_absent_outranks_not_recorded(self, tmp_path):
        _write_raw(tmp_path, "b", {"position_aware_focus": None})
        _write_raw(tmp_path, "c", {"task_metadata": {}})
        stats = _locate_stats(
            str(tmp_path), _pa_summary([{"task_id": "b", "iterations": 2}, {"task_id": "c", "iterations": 2}])
        )
        assert stats["grade"] == "focus_key_absent"


class TestLocateRendering:
    def test_every_grade_renders_its_own_text(self, tmp_path):
        (tmp_path / "raw").mkdir()

        def _arm(tid: str, payload: Any, row: dict[str, Any]) -> dict[str, Any]:
            _write_raw(tmp_path, tid, payload)
            return _locate_stats(str(tmp_path), _pa_summary([row]))

        repaired = {"iterations": 2}
        legs = {
            "state_unreadable": _arm("a", "{ not json", {"task_id": "a", **repaired}),
            "focus_key_absent": _arm("b", {"task_metadata": {}}, {"task_id": "b", **repaired}),
            "focus_not_recorded": _arm("c", {"position_aware_focus": None}, {"task_id": "c", **repaired}),
            "not_repaired": _arm("d", {"position_aware_focus": None}, {"task_id": "d"}),
            "measured": _arm(
                "e",
                {
                    "position_aware_focus": {"focused": False, "function_name": "other"},
                    "task_metadata": {"suggested_function": "divide"},
                },
                {"task_id": "e", **repaired},
            ),
            "raw_dir_absent": _locate_stats(str(tmp_path / "no_such"), _pa_summary([{"task_id": "t"}])),
            "state_file_absent": _locate_stats(str(tmp_path), _pa_summary([{"task_id": "ghost", **repaired}])),
            "details_unavailable": _locate_stats(str(tmp_path), {}),
            "no_samples": _locate_stats(str(tmp_path), _pa_summary([])),
            "row_unusable": _locate_stats(str(tmp_path), _pa_summary([repaired])),
        }
        assert {grade for grade, stats in legs.items()} == set(legs)
        assert [stats["grade"] for stats in legs.values()] == list(legs)  # 每档由该档自己代表
        texts = {grade: _locate_text(stats) for grade, stats in legs.items()}
        assert len(set(texts.values())) == len(texts), f"渲染仍互相折叠：{texts}"
        # 只有 measured 档允许出现百分数；其余各档必须点名"为何不可计算"
        assert texts["measured"] == "0.0%"
        for grade, text in texts.items():
            if grade == "measured":
                continue
            assert "%" not in text and "0.0" not in text, f"{grade} 档把没测到渲染成了读数：{text}"

    def test_measured_leg_renders_percent(self, tmp_path):
        _write_raw(
            tmp_path,
            "t",
            {
                "position_aware_focus": {"focused": True, "function_name": "divide"},
                "task_metadata": {"suggested_function": "divide"},
            },
        )
        stats = _locate_stats(str(tmp_path), _pa_summary([{"task_id": "t", "iterations": 2}]))
        assert _locate_text(stats) == "100.0%"

    def test_render_markdown_carries_coverage_and_json_block(self, tmp_path):
        on_dir, off_dir = tmp_path / "on", tmp_path / "off"
        on_dir.mkdir()
        (off_dir / "raw").mkdir(parents=True)  # raw 目录在、任务件不在 ⇒ state_file_absent 档
        _write_raw(
            on_dir,
            "t",
            {
                "position_aware_focus": {"focused": True, "function_name": "divide"},
                "task_metadata": {"suggested_function": "divide"},
            },
        )
        on_summary = {
            "results": {
                "aitester": {"details": [{"task_id": "t", "iterations": 1}], "total_functions": 1, "passed_count": 1}
            }
        }
        off_summary = {
            "results": {
                "aitester": {"details": [{"task_id": "t", "iterations": 1}], "total_functions": 1, "passed_count": 0}
            }
        }
        md = _render_markdown(on_summary, off_summary, str(on_dir), str(off_dir), str(tmp_path))
        locate_lines = [line for line in md.splitlines() if line.startswith("- 定位正确率")]
        # OFF 臂 raw 里根本没有 t 的件 ⇒ 只能声明没测，不能渲染成 0.0%
        assert "- 定位正确率（ON 组 focused 命中 gold function）: 100.0%" in md
        assert (
            "- 定位正确率（OFF 组，恒 0 或未激活）: 不可计算（raw/<task_id>/aitester.json 不存在）"
            "；分母 0 例 / 跳过 1 例" in md
        )
        # 逐行判：整串搜 "0.0%" 会被 ON 行的 "100.0%" 子串命中（本轮实测踩到）
        on_line, off_line = locate_lines
        assert on_line.endswith(": 100.0%")
        assert "%" not in off_line and "0.0" not in off_line
        assert "- 定位读数覆盖度 ON: 分母 1 例 / details 1 例" in md
        raw = json.loads((tmp_path / "position_aware_ab_raw.json").read_text(encoding="utf-8"))
        assert raw["on"]["locate"]["grade"] == "measured"
        assert raw["off"]["locate"]["grade"] == "state_file_absent"
        # 既有消费键不动：数值档仍在，读数与 locate 块并存
        assert raw["on"]["locate_accuracy_pct"] == 100.0
        assert raw["off"]["locate_accuracy_pct"] == -1.0


class TestArchivedReadingsDoNotDrift:
    """口径改动不动历史：归档臂现场复算必须与归档读数逐位相同。"""

    @pytest.mark.parametrize("batch", PA_BATCHES)
    def test_archived_locate_readings_reproduce(self, batch):
        root = RESULTS / batch
        archived_file = root / "position_aware_ab_raw.json"
        if not archived_file.is_file():
            pytest.skip(f"归档批次 {batch} 未入库（`.gitignore:172` 忽略 experiments/results/**），本地无件")
        archived = json.loads(archived_file.read_text(encoding="utf-8"))
        for arm, side in (("position_aware_on", "on"), ("position_aware_off", "off")):
            d = root / arm
            js = sorted(d.glob("benchmark_*.json"))
            if not js:
                pytest.skip(f"归档批次 {batch} 缺 {arm} 的批次 JSON")
            summary = json.loads(js[0].read_text(encoding="utf-8"))
            live = _locate_accuracy(str(d), summary)
            stats = _locate_stats(str(d), summary)
            assert live == archived[side]["locate_accuracy_pct"], f"{batch}/{arm}: {live} ≠ {archived[side]}"
            # 读数之外还要锁住"这读数是怎么来的"：measured 才允许是百分数
            if live < 0:
                assert stats["grade"] != "measured"
                assert stats["n_used"] == 0
            else:
                assert stats["grade"] == "measured"


# ═══ 4. compare_failures：逐臂披露，坏件不炸穿 ═══════════════════════════════

_ROW = {
    "task_id": "t1",
    "error_category": "assertion",
    "patch": _PATCH,
    "iterations": 2,
    "passed": False,
    "token_usage": {"total_tokens": 1},
}


def _inverted() -> list[dict[str, Any]]:
    return [{"task_id": "t1", "full": dict(_ROW), "base": dict(_ROW, passed=True)}]


class TestArtifactStatusReader:
    @pytest.mark.parametrize(
        ("raw_dir", "exists", "payload", "expected"),
        [
            (None, False, None, "no_raw_dir"),
            ("dir", False, None, "file_absent"),
            ("dir", True, "{ not json", "unreadable"),
            ("dir", True, "[1,2]", "unreadable"),
            ("dir", True, {"patch": "x"}, "ok"),
        ],
    )
    def test_status_vocab(self, tmp_path, raw_dir, exists, payload, expected):
        rd = None if raw_dir is None else str(tmp_path / "raw")
        if rd is not None and exists:
            _write_raw(tmp_path, "t1", payload, baseline="aitester")
        artifact, status = load_state_artifact_status(rd, "t1", "aitester")
        assert status == expected
        assert artifact is None or isinstance(artifact, dict)

    def test_corrupt_artifact_never_raises(self, tmp_path):
        # 改前 json.load 直接抛穿 ⇒ 一份坏件让整份报告中断。
        _write_raw(tmp_path, "t1", "{ not json", baseline="aitester")
        assert load_state_artifact_status(str(tmp_path / "raw"), "t1", "aitester")[0] is None
        assert load_state_artifact(str(tmp_path / "raw"), "t1", "aitester") is None

    def test_wrapper_still_returns_readable_artifact(self, tmp_path):
        _write_raw(tmp_path, "t1", {"generated_test": "def t():\n    pass\n"}, baseline="aitester")
        assert load_state_artifact(str(tmp_path / "raw"), "t1", "aitester") == {
            "generated_test": "def t():\n    pass\n"
        }


class TestReportDisclosure:
    def test_header_states_the_evidence_face(self, tmp_path):
        report = build_report(_inverted(), "aitester", "plain_llm", str(tmp_path / "raw"))
        assert f"- 环节级工件目录: `{tmp_path / 'raw'}`" in report
        no_dir = build_report(_inverted(), "aitester", "plain_llm", None)
        assert "- 环节级工件目录: 未提供（下文环节级对比只能声明缺席）" in no_dir

    def test_single_arm_absence_is_disclosed_per_arm(self, tmp_path):
        _write_raw(
            tmp_path, "t1", {"test_plan": {"n": 1}, "generated_test": "def t():\n    pass\n"}, baseline="aitester"
        )
        report = build_report(_inverted(), "aitester", "plain_llm", str(tmp_path / "raw"))
        assert "- plain_llm 环节级工件不可用：该任务的环节件不存在（≠ 该臂无产物）。" in report
        # 可读臂的产物块照常渲染；且不得再写"环节级产物缺失"（改前只有两臂都缺才有一行）
        assert "**aitester 环节产物**" in report
        assert "环节级产物缺失" not in report

    def test_both_arms_absent_keeps_the_original_line_and_adds_shapes(self, tmp_path):
        (tmp_path / "raw" / "t1").mkdir(parents=True)
        report = build_report(_inverted(), "aitester", "plain_llm", str(tmp_path / "raw"))
        # 原文逐字保留（历史消费者按这行找"没落盘"）
        assert "- 环节级产物缺失：请重跑 benchmark 时加 `--save-state`。" in report
        shape = next(line for line in report.splitlines() if line.startswith("- 缺席形态"))
        assert shape == (
            "- 缺席形态（BO 披露，不互相折叠）: aitester=该任务的环节件不存在；plain_llm=该任务的环节件不存在"
        )

    def test_corrupt_and_missing_are_named_differently(self, tmp_path):
        _write_raw(tmp_path, "t1", "{ not json", baseline="aitester")
        _write_raw(tmp_path, "t1", {"generated_test": "def b():\n    pass\n"}, baseline="plain_llm")
        corrupt = build_report(_inverted(), "aitester", "plain_llm", str(tmp_path / "raw"))
        assert "- aitester 环节级工件不可用：环节件不可读（JSON 损坏或顶层非对象）（≠ 该臂无产物）。" in corrupt
        assert "**plain_llm 环节产物**" in corrupt
        no_dir = build_report(_inverted(), "aitester", "plain_llm", None)
        assert "未提供 raw 目录（跑批未加 --save-state）" in no_dir
        assert "环节件不可读" not in no_dir
        # "未提供目录"与"件不存在"是两种缺席，文本不得互撞
        assert no_dir.splitlines() != corrupt.splitlines()

    def test_empty_artifact_is_not_the_same_as_absent_file(self, tmp_path):
        """`{}` 是合法空产物：可读、但没带环节字段 ⇒ 产物块要出现，缺席声明不该出现。"""
        _write_raw(tmp_path, "t1", {}, baseline="plain_llm")
        _write_raw(tmp_path, "t1", {"patch": "p" * 40}, baseline="aitester")
        report = build_report(_inverted(), "aitester", "plain_llm", str(tmp_path / "raw"))
        assert "**plain_llm 环节产物**" in report
        assert "环节级产物缺失" not in report
        assert "环节级工件不可用" not in report

    def test_empty_full_side_artifact_also_renders_its_block(self, tmp_path):
        """两臂同口径：空产物在 full 侧（多一个 RAG/补丁行）也不能被真值判定吞掉。"""
        _write_raw(tmp_path, "t1", {}, baseline="aitester")
        _write_raw(tmp_path, "t1", {"generated_test": "def t():\n    pass\n"}, baseline="plain_llm")
        report = build_report(_inverted(), "aitester", "plain_llm", str(tmp_path / "raw"))
        assert "**aitester 环节产物**" in report
        assert "环节级工件不可用" not in report

    def test_report_survives_a_batch_of_corrupt_artifacts(self, tmp_path):
        rows = []
        for i in range(3):
            tid = f"t{i}"
            _write_raw(tmp_path, tid, "{ truncated", baseline="aitester")
            _write_raw(tmp_path, tid, "{ truncated", baseline="plain_llm")
            rows.append({"task_id": tid, "full": dict(_ROW, task_id=tid), "base": dict(_ROW, task_id=tid, passed=True)})
        report = build_report(rows, "aitester", "plain_llm", str(tmp_path / "raw"))
        assert report.count("环节件不可读") == 6  # 3 任务 × 两臂，一份坏件不再中断整份报告


# ═══ 5. 接线锁：推荐命令不能自己拆掉证据面 ══════════════════════════════════


class TestCrossFileAbCommandWiring:
    """`cross_file_ab.py` 打印的后续命令必须带 --raw-dir（否则照做就落进折叠）。"""

    def test_followup_command_passes_raw_dir(self) -> None:
        source = (PROJECT_ROOT / "experiments" / "cross_file_ab.py").read_text(encoding="utf-8")
        assert "--raw-dir {on_dir}/raw" in source
        assert "须带 --raw-dir" in source

    def test_root_cause_defaults_to_no_raw_and_says_so(self) -> None:
        """脚本自身 --raw-dir 默认 None，因此降级声明必须由 main() 说出来。"""
        source = (PROJECT_ROOT / "experiments" / "cross_file_root_cause.py").read_text(encoding="utf-8")
        assert 'parser.add_argument("--raw-dir", default=None' in source
        assert 'logger.warning("未提供 --raw-dir' in source


class TestNoSilentCrashOnRealArchives:
    """整份 raw 目录不可用时，三个读侧都必须产出可读结论而不是抛穿。"""

    def test_all_three_readers_tolerate_an_empty_evidence_face(self, tmp_path):
        raw = tmp_path / "raw"
        assert analyze([_multi_row("t1")], str(raw), difficulty="")["root_cause_distribution"] == {"RAW_UNAVAILABLE": 1}
        assert _locate_stats(str(tmp_path), _pa_summary([{"task_id": "t1"}]))["grade"] == "raw_dir_absent"
        assert "环节级产物缺失" in build_report(_inverted(), "aitester", "plain_llm", str(raw))

    def test_oserror_on_raw_file_is_unreadable_not_a_traceback(self, tmp_path):
        """件"存在"但打不开（此处用目录占位 ⇒ open() 抛 OSError，权限故障同形）。"""
        for baseline in ("aitester", "plain_llm"):
            (tmp_path / "raw" / "t1" / f"{baseline}.json").mkdir(parents=True)
        assert _load_state(str(tmp_path / "raw"), "t1") == (None, "unreadable")
        assert load_state_artifact_status(str(tmp_path / "raw"), "t1", "aitester") == (None, "unreadable")
        stats = _locate_stats(str(tmp_path), _pa_summary([{"task_id": "t1", "iterations": 1}]))
        assert stats["grade"] == "state_unreadable" and stats["accuracy_pct"] == -1.0
        assert "环节件不可读" in build_report(_inverted(), "aitester", "plain_llm", str(tmp_path / "raw"))
