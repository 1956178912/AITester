"""BN（2026-10-22）：状态通道在落盘边界被丢弃 —— 归位锁。

缺陷族（BH→BM 系列第 6 面）。BH/BI/BJ/BG 把"读不懂 ⇒ 判优"收成四值 status，
BL 接消费侧双读、BM 接实验/报告读侧——**判定侧与消费侧都读得到 status，落盘边界
一个都没登记**。改前实测（`scripts/tools/bn_dump_boundary_probe.py`，Python 3.14.6，
零 LLM）：

1. **两道落盘边界都把 5 种运行时态折成 1 种落盘形状**：`static_check_*` /
   `safety_check_*` / `oracle_check_*`（status + outcomes 共 6 键）既不在
   `_dump_state_artifacts` 的白名单、也不在 `_build_task_result` 的任何一个 return
   分支 ⇒ ok（检查完成且零疑点）/ error（检查崩了）/ unavailable（依赖没装）/
   disabled（按设计未检查）/ 键不存在 五种情形落盘字节**逐字节同形**
   （raw 工件恒 558 字节）。
2. **`contract_status` 半落盘**：结果行两分支都写了，raw 白名单却没有——
   同一通道在两道边界口径不一。
3. **归档普查给出 0 次出现**：`scripts/tools/bn_archive_status_census.py` 扫
   1700 个 JSON（raw 环节级 1121）+ 9096 条 JSONL 轨迹行，上述 7 个键
   **0 命中 / 0 文件**⇒ 前五轮补的披露只活在内存里，事后不可复核。

修复口径：**只做归位，不改判定**。新增键纯观测，`passed` / `coverage` /
`error_category` / `stop_reason` / `risk_summary` 打分与方向逐字节不变；
磁盘上的历史工件一个字节没动（普查口径不变即证据），新批次默认档落 null、
写入了落真实取值。门禁 `scripts/gates/check_status_persistence.py` 把"声明面 ⊆
落盘面"钉成棘轮，豁免清单为空。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import experiments.run_benchmark as rb
from src.datasets.dataset_loader import BenchmarkTask
from src.graph.state import AITesterState
from src.utils.check_status import CHECK_STATUS_VOCABULARY

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: state.py 声明的全部 status/outcomes 通道（本轮归位面）
CHANNELS: tuple[str, ...] = (
    "contract_status",
    "static_check_status",
    "static_check_outcomes",
    "safety_check_status",
    "safety_check_outcomes",
    "oracle_check_status",
    "oracle_check_outcomes",
    "detection_first_status",
    "edit_intent_status",
    "deterministic_repair_status",
)
#: 本轮补进**结果行**的六键（contract_status 此前已在行里）
ROW_CHANNELS: tuple[str, ...] = CHANNELS[1:7]
#: 四值词汇的 status 键（其余三个通道另有取值域，只做透传，不套四值口径）
FOUR_VALUED_STATUS: tuple[str, ...] = ("static_check_status", "safety_check_status", "oracle_check_status")
STATUSES: tuple[str, ...] = ("ok", "error", "unavailable", "disabled")
ABSENT = "absent"

JUDGING_KEYS: tuple[str, ...] = (
    "test_passed",
    "coverage",
    "iterations",
    "diagnosis",
    "error_category",
    "patch",
    "test_plan",
    "generated_test",
)

_PATCH = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n"
_BASE_STATE: dict[str, Any] = {
    "test_plan": "plan",
    "generated_test": "def test_x():\n    assert 1\n",
    "diagnosis": "",
    "error_category": "",
    "patch": _PATCH,
    "test_passed": True,
    "iteration": 1,
    "coverage_report": 0.5,
    "rag_stats": None,
    "position_aware_focus": None,
    "repo_verification": None,
    "cross_file_deps": None,
    "testless_validation": None,
    "deterministic_guard_report": None,
    "m10_leaf_fallback": None,
}


def _outcomes(status: str) -> list[dict[str, Any]]:
    return [{"backend": "mypy", "status": status, "reason": "unrecognized arguments" if status == "error" else ""}]


def _state(status: str | None, *, channels: tuple[str, ...] = CHANNELS) -> dict[str, Any]:
    """同一份运行结果，只让 channels 携带 status；status=None 表示这些键根本不存在。"""
    state = dict(_BASE_STATE)
    if status is None:
        return state
    for key in channels:
        state[key] = _outcomes(status) if key.endswith("_outcomes") else status
    return state


def _task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id="lock__task",
        repo_name="lock/task",
        problem_statement="fix a bug",
        instance_code="def f():\n    return 1\n",
        test_code="def test_f():\n    assert f() == 1\n",
        expected_pass_count=0,
        total_test_count=1,
        metadata={"source": "bn-lock"},
    )


def _dump(tmp_path: Path, state: dict[str, Any]) -> dict[str, Any]:
    task = SimpleNamespace(task_id="lock__task", metadata={"difficulty": "easy"})
    rb._dump_state_artifacts(str(tmp_path), task, "aitester", state)
    return json.loads((tmp_path / "raw" / "lock__task" / "aitester.json").read_text(encoding="utf-8"))


def _dump_bytes(tmp_path: Path, state: dict[str, Any]) -> bytes:
    task = SimpleNamespace(task_id="lock__task", metadata={"difficulty": "easy"})
    rb._dump_state_artifacts(str(tmp_path), task, "aitester", state)
    return (tmp_path / "raw" / "lock__task" / "aitester.json").read_bytes()


def _row(state: dict[str, Any] | None) -> dict[str, Any]:
    return rb._build_task_result(_task(), 1.0, final_state=state)


def _load_gate() -> Any:
    """以 importlib 加载 scripts/gates/check_status_persistence.py（scripts 非包）。"""
    spec = importlib.util.spec_from_file_location(
        "check_status_persistence_under_test",
        PROJECT_ROOT / "scripts" / "gates" / "check_status_persistence.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(PROJECT_ROOT))
    return module


@pytest.fixture(scope="module")
def gate() -> Any:
    return _load_gate()


# ─── 一、声明面与归位面必须对上 ──────────────────────────────────────────


class TestDeclaredSurface:
    """声明面本身不能被写成空集——门禁与测试都从它出发，空面 = 假绿。"""

    def test_declared_channels_are_exactly_the_ten(self) -> None:
        declared = sorted(k for k in AITesterState.__annotations__ if k.endswith(("_status", "_outcomes")))
        assert declared == sorted(CHANNELS), f"AITesterState 的 status/outcomes 通道面漂移：{declared}"

    def test_gate_declared_surface_matches(self, gate: Any) -> None:
        assert gate.declared_channels() == sorted(CHANNELS)

    def test_row_channels_are_the_six_without_contract(self) -> None:
        assert CHANNELS[1:7] == ROW_CHANNELS and "contract_status" not in ROW_CHANNELS


# ─── 二、raw 落盘边界（`_dump_state_artifacts` 白名单）──────────────────


class TestDumpWhitelist:
    """十键必须进白名单：默认档在场且为 null，写入后逐值透传。"""

    def test_default_mode_keys_present_and_null(self, tmp_path: Path) -> None:
        data = _dump(tmp_path, {})
        for key in CHANNELS:
            assert key in data, f"工件缺键 {key}（白名单未登记 → 通道写进 state 即被丢弃）"
            assert data[key] is None

    @pytest.mark.parametrize("key", CHANNELS)
    def test_channel_passes_through_verbatim(self, tmp_path: Path, key: str) -> None:
        state = _state("error", channels=(key,))
        data = _dump(tmp_path, state)
        assert data[key] == state[key]

    @pytest.mark.parametrize("status", STATUSES)
    def test_status_does_not_move_judging_fields(self, tmp_path: Path, status: str) -> None:
        """归位只加键：判定与产物字段在四值之间逐字节不动。"""
        baseline = _dump(tmp_path, _state("ok"))
        current = _dump(tmp_path, _state(status))
        for key in JUDGING_KEYS:
            assert current[key] == baseline[key], f"status={status} 改动了判定字段 {key}"

    def test_five_runtime_states_are_five_artifact_shapes(self, tmp_path: Path) -> None:
        """折叠已解除：改前 5 态 → 1 种 558 字节形状，改后逐态可辨。"""
        blobs = {}
        for status in STATUSES:
            blobs[status] = _dump_bytes(tmp_path, _state(status))
        blobs[ABSENT] = _dump_bytes(tmp_path, _state(None))
        assert len({blob for blob in blobs.values()}) == 5, f"仍有运行时态被折成同形：{list(blobs)}"

    @pytest.mark.parametrize(
        ("left", "right"),
        [("ok", "error"), ("ok", "unavailable"), ("ok", "disabled"), ("error", "unavailable")],
    )
    def test_pairwise_status_is_distinguishable(self, tmp_path: Path, left: str, right: str) -> None:
        assert _dump_bytes(tmp_path, _state(left)) != _dump_bytes(tmp_path, _state(right))

    def test_outcomes_round_trip_as_json(self, tmp_path: Path) -> None:
        state = _state("error", channels=("static_check_outcomes", "oracle_check_outcomes"))
        data = _dump(tmp_path, state)
        assert data["static_check_outcomes"] == _outcomes("error")
        assert data["oracle_check_outcomes"] == _outcomes("error")


# ─── 三、结果行边界（`_build_task_result` 两分支）───────────────────────


class TestResultRow:
    """六键在成功分支取终态、失败分支以 None 占位，键集合同构不破坏。"""

    @pytest.mark.parametrize("key", ROW_CHANNELS)
    def test_success_branch_carries_channel(self, key: str) -> None:
        state = _state("unavailable", channels=(key,))
        assert _row(state)[key] == state[key]

    @pytest.mark.parametrize("key", ROW_CHANNELS)
    def test_failure_branch_uses_none_placeholder(self, key: str) -> None:
        row = _row(None)
        assert key in row, f"失败分支缺键 {key}（两分支键集合不同构）"
        assert row[key] is None

    def test_both_branches_keep_key_set_symmetry(self) -> None:
        success = _row(_state("ok"))
        failure = _row(None)
        assert set(success) == set(failure)
        assert set(ROW_CHANNELS) <= set(success)

    @pytest.mark.parametrize("status", STATUSES)
    def test_row_judging_fields_invariant_to_new_channels(self, status: str) -> None:
        """行侧同口径：只动新落的六键，判分字段与 risk_summary 都不动
        （contract 腿在两份 state 里都不存在，故两侧同为 None，不构成差异源）。"""
        baseline = _row(_state("ok", channels=ROW_CHANNELS))
        current = _row(_state(status, channels=ROW_CHANNELS))
        for key in ("passed", "coverage", "iterations", "error_category", "stop_reason", "harness_invalid"):
            assert current[key] == baseline[key], f"status={status} 改动了行判定字段 {key}"
        assert current["risk_summary"] == baseline["risk_summary"]

    def test_row_shapes_now_differ_per_runtime_state(self) -> None:
        rows = {status: repr(_row(_state(status))) for status in STATUSES}
        rows[ABSENT] = repr(_row(_state(None)))
        assert len(set(rows.values())) == 5

    def test_contract_channel_still_reaches_both_branches(self) -> None:
        assert _row(_state("error", channels=("contract_status",)))["contract_status"] == "error"
        assert _row(None)["contract_status"] is None


# ─── 四、词表口径：四值通道不得写进行侧当新词汇 ─────────────────────────


class TestVocabularyCaliber:
    def test_four_valued_channels_use_the_shared_vocabulary(self, tmp_path: Path) -> None:
        for key in FOUR_VALUED_STATUS:
            for status in STATUSES:
                data = _dump(tmp_path, _state(status, channels=(key,)))
                assert data[key] in CHECK_STATUS_VOCABULARY

    def test_non_vocabulary_channels_are_pass_through_only(self) -> None:
        """detection_first / edit_intent / deterministic_repair 另有取值域，
        归位只做透传，绝不套四值口径改写（否则与 BM 的读侧判定打架）。"""
        for key in ("detection_first_status", "edit_intent_status", "deterministic_repair_status"):
            state = _BASE_STATE | {key: "measured"}
            assert _row(state)[key] == "measured"
            assert _row(None)[key] is None


# ─── 五、棘轮门禁本体 ────────────────────────────────────────────────────


class TestPersistenceRatchet:
    def test_surfaces_are_three_and_all_cover_declared(self, gate: Any) -> None:
        surfaces = gate.persisted_keys(gate.RUN_BENCHMARK)
        assert "raw_artifact" in surfaces
        assert len([name for name in surfaces if name.startswith("result_row@")]) == 2
        for name, keys in surfaces.items():
            for channel in CHANNELS:
                assert channel in keys, f"{name} 未登记 {channel}"

    def test_gate_exits_zero_on_current_tree(self, gate: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["check_status_persistence.py"])
        assert gate.main() is None

    def test_gate_blocks_an_unpersisted_new_channel(self, gate: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """新通道只声明不落盘 ⇒ 直接红（这正是本轮之前缺的那道闸）。"""
        monkeypatch.setattr(sys, "argv", ["check_status_persistence.py"])
        monkeypatch.setattr(gate, "declared_channels", lambda: [*sorted(CHANNELS), "brand_new_check_status"])
        with pytest.raises(SystemExit) as excinfo:
            gate.main()
        assert excinfo.value.code == 1

    def test_gate_blocks_channel_missing_from_a_single_branch(self, gate: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """只在一支登记也算违规：逐分支判定，不按并集放行。"""
        surfaces = gate.persisted_keys(gate.RUN_BENCHMARK)
        row_names = sorted(name for name in surfaces if name.startswith("result_row@"))
        assert len(row_names) == 2
        monkeypatch.setattr(
            gate, "persisted_keys", lambda _p: {row_names[0]: set(surfaces[row_names[0]]) - {"static_check_status"}}
        )
        monkeypatch.setattr(sys, "argv", ["check_status_persistence.py"])
        with pytest.raises(SystemExit) as excinfo:
            gate.main()
        assert excinfo.value.code == 1

    def test_cli_runs_green(self) -> None:
        proc = subprocess.run(
            [sys.executable, "scripts/gates/check_status_persistence.py"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "审计通过" in proc.stdout

    def test_cli_list_mode_reports_declared_surface(self) -> None:
        proc = subprocess.run(
            [sys.executable, "scripts/gates/check_status_persistence.py", "--list"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        for channel in CHANNELS:
            assert channel in proc.stdout


# ─── 六、接线锁：门禁说"CI 阻断项"，就必须真的在链里 ────────────────────


class TestWiring:
    def test_makefile_has_the_target_and_the_gates_prerequisite(self) -> None:
        makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
        assert "status-persistence:" in makefile
        gates_line = next(line for line in makefile.splitlines() if line.startswith("gates:"))
        # 只看依赖段（## 之前）：整行含注释，注释里本来就写着 status-persistence，
        # 拿整行判定会让"从依赖里摘掉门禁"这种变异活下来（BN 变异验证实测 SURVIVED）。
        prerequisites = gates_line.split("##")[0]
        assert "status-persistence" in prerequisites, "门禁未挂进 gates 依赖段（只在注释里出现不算接线）"
        assert "scripts/gates/check_status_persistence.py" in makefile

    def test_ci_workflow_invokes_the_gate(self) -> None:
        ci = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "scripts/gates/check_status_persistence.py" in ci

    def test_phony_lists_the_target(self) -> None:
        makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
        phony = next(line for line in makefile.splitlines() if line.startswith(".PHONY:"))
        assert "status-persistence" in phony
