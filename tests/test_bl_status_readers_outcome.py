"""BL（2026-10-22）：发布侧带 status、判定侧仍按空值判定 —— 消费侧双读收口锁。

缺陷族（F03 的消费侧，BI→BK 把 status 发布出去了，本轮才有人读）。改前实测
（Python 3.14.6，零 LLM，`scripts/tools/bl_status_readers_probe.py`）：

1. **判定侧读者为零**：`src/` 里 11 个 status/outcome 通道中 **8 个判定读点 = 0**
   （`static_check_status` / `static_check_outcomes` / `safety_check_status` /
   `safety_check_outcomes` / `oracle_check_status` / `oracle_check_outcomes` /
   `contract_outcomes` / `check_status` / `check_outcomes`）；其余 3 处
   （`contract_status` ×2、`contract_reason` ×1）都在生产模块 `type_repair`
   内部自读，链路下游无人读。变量普查（A2）同样为 0。
2. **折叠真实发生**：`assess_task_risk` 只收 `contract_missing_symbols`，
   status=ok / disabled / error / 键缺席四行落到**同一个**
   `impact=0.2, risk_level=low, approval_action=auto_merge, risk_score=0.12`
   （探针 B1）——"契约比完且一个不缺"与"契约根本没比成"不可区分。
3. **消费点没接 sink**：`patch_applier` 调用 `dangerous_api_added` 的关键字实参
   为空列表（探针 B4），BI 写的 `error` 记录从未被生产；`contract_status` /
   `contract_reason` / `contract_outcomes` 三个键连 state 通道都没声明。
4. **口径注释无人实现**：`state.py` 写着"读 count 时必须结合
   `static_check_status`（ok 才是检查完成且零疑点）"，`agents/debugger.py`
   的静态层在 `findings=[]` 时整段静默。

修复口径（**判定值逐位不变**，只把沉默换成披露）：新增按腿取 status 的读者原语
`status_for_check`；`assess_task_risk` / `_impact_factor` / `build_risk_summary`
接 `contract_status`（只补 `contract_unmeasurable(...)` 披露，不把 `error` 翻成
`human_confirm`——路由方向变更需 A/B 数据与预注册判据）；`nodes` 发布 per-leg
`contract_status`（恒写，不用 worst-of 拉平）；`patch_applier` S2 守卫接 sink 并
披露；`agents/debugger` 实现 state.py 的口径注释；telemetry 新增
`check_unmeasurable` 失败模式（只认 error / unavailable ⇒ 归档读数零变化）。

归档零影响的判据在 §5：1702 个结果文件里**每个 status 键出现 0 次**，
`check_unmeasurable` 对"键全缺席"恒不命中。
"""

from __future__ import annotations

import ast
import json
import logging
from collections import deque
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import src.tools.patch_applier as pa_mod
from src.agents import debugger as debugger_mod
from src.agents.debugger import DebuggerAgent
from src.graph import nodes as nodes_mod
from src.graph.risk_approval import assess_task_risk, build_risk_summary
from src.graph.state import AITesterState, create_initial_state
from src.observability import agent_telemetry as at
from src.utils import check_status as cs

ROOT = Path(__file__).resolve().parents[1]

# ─── 语料 ────────────────────────────────────────────────────────────────
_CLEAN = "def f() -> int:\n    return 1\n"
_WITH_CONST = "def f() -> int:\n    return 1\n\n\nCONST = 3\n"
#: 单函数模式补丁（只给被改的函数）与其真实应用结果——实测钉住：把整份新代码
#: （含 `CONST = 3`）当单函数补丁喂进去会走 Step 4b 切片，产出重复的 `CONST`，
#: 所以"可测量且干净"的形状只能这样给。
_PATCH_F_ONLY = "def f() -> int:\n    return 2\n"
_APPLIED_F_ONLY = "def f() -> int:\n    return 2\n\nCONST = 3\n"
_BROKEN_PATCHED = "def f(:\n    return CONST\n\n\nCONST = 3\n"
_PY2_PRINT = 'print "x"\n\n\ndef f():\n    return 1\n'
#: Step 4a 全文件模式的可达形状：docstring 开头 ⇒ `_is_full_file_patch` 判真，
#: 补丁整体替换读不懂的原文（单函数模式会把坏行留在合并结果里，够不到 S2 守卫）。
_FULL_FILE_PATCH = '"""doc"""\ndef f():\n    return 2\n'
_LEGACY_ARGS: dict[str, Any] = {
    "confidence": 0.9,
    "changed_lines": 5,
    "changed_files": 1,
    "contract_missing_symbols": [],
    "full_file_patch": False,
    "budget_ratio": None,
    "budget_exceeded": None,
}


def _judgment(assessment: Any) -> tuple[Any, ...]:
    """判定四位（打分 / 级别 / 动作 / 分数）——披露不进这里。"""
    d = assessment.to_dict()
    return (d["factors"].get("impact"), d["risk_level"], d["approval_action"], d["risk_score"])


def _dict_key_symmetry(rel_path: str, paired: tuple[str, str]) -> list[str]:
    """返回 `rel_path` 里含 `paired[0]` 键但缺 `paired[1]` 键的字典字面量所在行号。

    用于锁"发布证据值的每一行都必须同时发布它的读法"——证据键与 status 键成对
    出现在同一个 dict 字面量里（成功行与失败行的键集合因此同构）。
    """
    tree = ast.parse((ROOT / rel_path).read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if paired[0] in keys and paired[1] not in keys:
            offenders.append(f"{rel_path}:{node.lineno}")
    return offenders


def _call_kwargs(rel_path: str, fname: str) -> list[tuple[int, list[str]]]:
    """`rel_path` 里对 `fname(...)` 的每个调用点及其关键字实参名。"""
    tree = ast.parse((ROOT / rel_path).read_text(encoding="utf-8"))
    return [
        (node.lineno, sorted(k.arg or "" for k in node.keywords))
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == fname
    ]


# ═══ 1. 按腿取 status 的读者原语 ═══════════════════════════════════════════


@pytest.mark.unit
class TestStatusForCheck:
    def test_leg_absent_is_none_not_ok(self) -> None:
        """该腿没记录 ⇒ None（"本轮没做这条腿"），绝不能读成 ok 或 error。"""
        assert cs.status_for_check([], "naming_contract") is None
        assert cs.status_for_check(None, "naming_contract") is None
        assert cs.status_for_check([{"check": "dangerous_api", "status": cs.CHECK_OK}], "naming_contract") is None

    def test_leg_worst_of_within_same_check(self) -> None:
        sink = [
            {"check": "dangerous_api", "status": cs.CHECK_OK},
            {"check": "dangerous_api", "status": cs.CHECK_ERROR, "reason": cs.UNPARSEABLE_PATCHED},
        ]
        assert cs.status_for_check(sink, "dangerous_api") == cs.CHECK_ERROR

    def test_legs_do_not_pollute_each_other(self) -> None:
        """本轮的动机：worst-of 聚合会把"危险 API 腿读不懂"记到契约头上。"""
        sink = [
            {"check": "naming_contract", "status": cs.CHECK_OK},
            {"check": "dangerous_api", "status": cs.CHECK_ERROR},
        ]
        assert cs.status_for_check(sink, "naming_contract") == cs.CHECK_OK
        assert cs.status_for_check(sink, "dangerous_api") == cs.CHECK_ERROR
        assert cs.worst_check_status([o["status"] for o in sink]) == cs.CHECK_ERROR

    def test_non_dict_and_statusless_records_are_fail_closed(self) -> None:
        assert cs.status_for_check(["not-a-dict"], "dangerous_api") is None
        assert cs.status_for_check([{"check": "dangerous_api"}], "dangerous_api") == cs.CHECK_ERROR

    def test_vocabulary_values_pass_through_verbatim(self) -> None:
        for value in (cs.CHECK_OK, cs.CHECK_DISABLED, cs.CHECK_UNAVAILABLE, cs.CHECK_ERROR):
            assert cs.status_for_check([{"check": "c", "status": value}], "c") == value


# ═══ 2. 折叠被消掉：判定不变 + 披露可区分 ═══════════════════════════════════


@pytest.mark.unit
class TestRiskApprovalDoubleRead:
    def test_judgment_invariant_over_status_axis(self) -> None:
        """四行（ok / disabled / error / 键缺席）判定四位逐位相同——只补披露不翻路由。"""
        judgments = {
            status: _judgment(assess_task_risk(**{**_LEGACY_ARGS, "contract_status": status}))
            for status in (None, cs.CHECK_OK, cs.CHECK_DISABLED, cs.CHECK_ERROR, cs.CHECK_UNAVAILABLE)
        }
        assert len({judgments[k] for k in judgments}) == 1
        assert judgments[cs.CHECK_ERROR] == (0.2, "low", "auto_merge", 0.12)

    def test_disclosure_distinguishes_unmeasurable_from_clean(self) -> None:
        clean = assess_task_risk(**{**_LEGACY_ARGS, "contract_status": cs.CHECK_OK}).to_dict()
        legacy = assess_task_risk(**_LEGACY_ARGS).to_dict()
        assert not [r for r in clean["reasons"] if str(r).startswith("contract_unmeasurable(")]
        assert not [r for r in legacy["reasons"] if str(r).startswith("contract_unmeasurable(")]
        for status in (cs.CHECK_DISABLED, cs.CHECK_ERROR, cs.CHECK_UNAVAILABLE):
            reasons = assess_task_risk(**{**_LEGACY_ARGS, "contract_status": status}).to_dict()["reasons"]
            note = [r for r in reasons if str(r).startswith(f"contract_unmeasurable({status})")]
            assert note, f"status={status} 必须披露，实际 {reasons}"
            assert "不是「契约成立」的证据" in note[0]

    def test_missing_nonempty_is_unaffected_by_status(self) -> None:
        """有缺失符号时判定与披露都按旧口径走（status 不叠加、不改分）。"""
        args = {**_LEGACY_ARGS, "contract_missing_symbols": ["Rule_L101"]}
        with_ok = assess_task_risk(**{**args, "contract_status": cs.CHECK_OK}).to_dict()
        with_error = assess_task_risk(**{**args, "contract_status": cs.CHECK_ERROR}).to_dict()
        assert _judgment(assess_task_risk(**{**args, "contract_status": cs.CHECK_ERROR})) == (
            0.9,
            "medium",
            "human_confirm",
            pytest.approx(0.4),
        )
        assert with_ok == with_error
        assert not [r for r in with_error["reasons"] if str(r).startswith("contract_unmeasurable(")]

    def test_seven_positional_calls_still_work(self) -> None:
        """历史 7 位位置实参调用面不破（新形参只追加在末尾）。"""
        positional = (0.9, 5, 1, [], False, None, None)
        assert _judgment(assess_task_risk(*positional)) == (0.2, "low", "auto_merge", 0.12)

    def test_disclosure_is_logged_once_judgment_unchanged(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="src.graph.risk_approval"):
            assessment = assess_task_risk(**{**_LEGACY_ARGS, "contract_status": cs.CHECK_ERROR})
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "G2 缺失符号列表不可作证据（判定不变）" in text
        assert "contract_unmeasurable(error)" in text
        assert _judgment(assessment) == (0.2, "low", "auto_merge", 0.12)
        assert assessment.approval_action == "auto_merge", "error 不得翻成人工确认（路由方向变更需 A/B 数据）"

    def test_clean_status_logs_nothing(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="src.graph.risk_approval"):
            assess_task_risk(**{**_LEGACY_ARGS, "contract_status": cs.CHECK_OK})
        assert "不可作证据" not in "\n".join(r.getMessage() for r in caplog.records)

    def test_build_risk_summary_publishes_status_on_both_branches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """开关键集合对称：enabled=False 的占位 dict 也带 contract_status。"""
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "false")
        off = build_risk_summary(0.9, 5, 1, [], False, None, None, contract_status=cs.CHECK_ERROR)
        assert off["enabled"] is False
        assert off["contract_status"] == cs.CHECK_ERROR
        assert off["pause_requested"] is False
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "true")
        on = build_risk_summary(0.9, 5, 1, [], False, None, None, contract_status=cs.CHECK_ERROR)
        assert on["enabled"] is True
        assert on["contract_status"] == cs.CHECK_ERROR
        assert set(on) == set(off), "开关两分支键集合必须同构（docstring 的「同构」承诺由此锁定）"
        assert on["pause_requested"] is False, "auto_merge 不请求暂停"

    def test_real_callsites_feed_status(self) -> None:
        """探针 B4 的收口面：真实调用点必须把 status 一起取走。"""
        ((lineno, kwargs),) = _call_kwargs("src/graph/debugger.py", "_build_risk_summary")
        assert "contract_status" in kwargs, f"{lineno}: 只带列表不带读法 ⇒ 折叠仍在"
        assert "contract_missing_symbols" in kwargs
        ((_lineno, kwargs),) = _call_kwargs("src/graph/risk_approval.py", "assess_task_risk")
        assert "contract_status" in kwargs


# ═══ 3. 发布面：per-leg 通道 + trace + benchmark 行 ═════════════════════════


@pytest.mark.unit
class TestPublishSide:
    def test_state_declares_contract_status_channel(self) -> None:
        assert "contract_status" in AITesterState.__annotations__
        state = create_initial_state(task_uuid="bl-lock", target_file="mod.py", target_code=_CLEAN, max_iterations=1)
        assert state["contract_status"] is None  # type: ignore[typeddict-item]

    def test_node_publishes_per_leg_contract_status(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """真实 `_patch_applier_node`（零 mock 守卫）：契约腿单独落通道，恒写。"""
        target = tmp_path / "mod.py"
        target.write_text(_PY2_PRINT, encoding="utf-8")
        state: dict[str, Any] = {
            "target_code": _PY2_PRINT,
            "patch": "def f():\n    return 2\n",
            "target_file": str(target),
            "module_name": "mod",
            "iteration": 0,
            "error_category": "RUNTIME",
            "diagnosis": "x",
        }
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", "false")
        with patch.object(nodes_mod, "_trace_node"), patch.object(nodes_mod, "publish_patch_applied"):
            update = nodes_mod._patch_applier_node(state)  # type: ignore[arg-type]
        assert update["safety_check_status"] == cs.CHECK_ERROR
        assert "contract_status" in update, "非空才写键 ⇒ 通道缺席与「没做这条腿」不可区分"
        assert update["contract_status"] == cs.status_for_check(update["safety_check_outcomes"], "naming_contract")
        assert update["contract_status"] == cs.CHECK_ERROR

    def test_leg_status_differs_from_aggregate_when_switches_disagree(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """按腿取 status 的全部意义：两条腿不同源时聚合会把「按设计没检查」记成「崩了」。

        实测可达形状：``PATCH_CONTRACT_CHECK=false``（契约腿 disabled）叠加原文读不懂
        （危险 API 腿 error）。此时 ``worst_check_status`` 恒为 error，拿它当契约腿的
        读法就把开关关闭误报成后端崩了——变异 M17（聚合冒充单腿）只有在这一形状下才会红。
        """
        target = tmp_path / "mod.py"
        target.write_text(_PY2_PRINT, encoding="utf-8")
        state: dict[str, Any] = {
            "target_code": _PY2_PRINT,
            "patch": "def f():\n    return 2\n",
            "target_file": str(target),
            "module_name": "mod",
            "iteration": 0,
            "error_category": "RUNTIME",
            "diagnosis": "x",
        }
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", "false")
        monkeypatch.setenv("PATCH_CONTRACT_CHECK", "false")
        with patch.object(nodes_mod, "_trace_node"), patch.object(nodes_mod, "publish_patch_applied"):
            update = nodes_mod._patch_applier_node(state)  # type: ignore[arg-type]
        assert update["contract_status"] == cs.CHECK_DISABLED
        assert update["safety_check_status"] == cs.CHECK_ERROR
        assert update["contract_status"] != update["safety_check_status"], "单腿读法被聚合吞掉 ⇒ 折叠又回来了"
        assert update["contract_status"] == cs.status_for_check(update["safety_check_outcomes"], "naming_contract")

    def test_channel_not_written_when_prechecks_skipped(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        target = tmp_path / "mod.py"
        target.write_text(_CLEAN, encoding="utf-8")
        state: dict[str, Any] = {
            "target_code": _CLEAN,
            "patch": _CLEAN,
            "target_file": str(target),
            "module_name": "mod",
            "iteration": 0,
            "error_category": "RUNTIME",
            "diagnosis": "x",
        }
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", "false")
        with patch.object(nodes_mod, "_trace_node"), patch.object(nodes_mod, "publish_patch_applied"):
            update = nodes_mod._patch_applier_node(state)  # type: ignore[arg-type]
        assert "contract_status" not in update, "本轮没做预检 ⇒ 不得凭空造读数（保持 None）"

    def test_generator_trace_publishes_oracle_status(self) -> None:
        """G4 的唯一真实数据源是 trace JSONL：status 键必须进 `_trace_node` 载荷。"""
        tree = ast.parse((ROOT / "src/graph/nodes.py").read_text(encoding="utf-8"))
        payloads: list[set[str]] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_trace_node"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "generator"
            ):
                payloads.extend(
                    {k.value for k in kw.value.keys if isinstance(k, ast.Constant)}
                    for kw in node.keywords
                    if kw.arg == "output_summary" and isinstance(kw.value, ast.Dict)
                )
        assert payloads, "未找到 generator 的 _trace_node 调用"
        assert any("oracle_check_status" in p for p in payloads), payloads

    def test_benchmark_rows_pair_evidence_with_its_reading(self) -> None:
        assert _dict_key_symmetry("experiments/run_benchmark.py", ("contract_missing_symbols", "contract_status")) == []


# ═══ 4. S2 危险 API 守卫：接上 sink，方向不变 ═══════════════════════════════


@pytest.mark.unit
class TestDangerousApiConsumer:
    def test_guard_sink_reaches_consumer(self) -> None:
        ((_lineno, kwargs),) = _call_kwargs("src/tools/patch_applier.py", "dangerous_api_added")
        assert "outcome_sink" in kwargs, "不接 sink ⇒ BI 写的 error 记录从未被生产"

    def test_unparseable_original_is_disclosed_and_patch_still_applies(self, caplog: pytest.LogCaptureFixture) -> None:
        """实测可达形状：完整文件补丁（docstring 开头）盖住读不懂的原文。

        门序口径（本轮实测得到，不是推断）：`safe_apply_patch` 在守卫之前有
        `ast.parse(new_code)` 硬门（patch_applier.py:481-486），**补丁侧**读不懂
        一律在门前回滚，永远到不了 S2；单函数模式会把坏行留在合并结果里，所以
        "原文读不懂 + 新代码可解析"只有 Step 4a 全文件替换这一种组合够得到。
        """
        with caplog.at_level(logging.WARNING, logger="src.tools.patch_applier"):
            new_code, applied = pa_mod.safe_apply_patch(_PY2_PRINT, _FULL_FILE_PATCH)
        assert applied is True
        assert new_code == _FULL_FILE_PATCH
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "S2 危险 API 守卫不可测量（status=error）" in text
        assert "不是无新增危险调用的证据" in text
        assert cs.UNPARSEABLE_ORIGINAL in text

    def test_broken_patch_is_rejected_before_the_guard(self, caplog: pytest.LogCaptureFixture) -> None:
        """门前拦截：补丁读不懂 ⇒ 回滚 False，S2 不参与（不制造第二条披露路径）。"""
        with caplog.at_level(logging.WARNING, logger="src.tools.patch_applier"):
            new_code, applied = pa_mod.safe_apply_patch(_CLEAN, _BROKEN_PATCHED)
        assert (new_code, applied) == (_CLEAN, False)
        assert "不可测量" not in "\n".join(r.getMessage() for r in caplog.records)

    def test_measurable_clean_patch_logs_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """可测量且干净 ⇒ 零披露（单函数模式：补丁只给被改的函数，尾部由原代码保留）。"""
        with caplog.at_level(logging.WARNING, logger="src.tools.patch_applier"):
            new_code, applied = pa_mod.safe_apply_patch(_WITH_CONST, _PATCH_F_ONLY)
        assert (applied, new_code) == (True, _APPLIED_F_ONLY)
        assert "不可测量" not in "\n".join(r.getMessage() for r in caplog.records)

    def test_sink_shape_per_input(self) -> None:
        cases = (
            ("可读且干净", _CLEAN, _CLEAN, cs.CHECK_OK),
            ("补丁读不懂", _CLEAN, _BROKEN_PATCHED, cs.CHECK_ERROR),
            ("原文读不懂", _PY2_PRINT, _CLEAN, cs.CHECK_ERROR),
            ("空输入", "", _CLEAN, cs.CHECK_DISABLED),
        )
        for label, original, patched, expected in cases:
            sink: list[dict[str, Any]] = []
            assert pa_mod.dangerous_api_added(original, patched, outcome_sink=sink) == []
            assert cs.status_for_check(sink, "dangerous_api") == expected, label


# ═══ 5. telemetry：status 通道的判定侧读者 ══════════════════════════════════


@pytest.mark.unit
class TestUnmeasurableFailurePattern:
    def test_registry_is_consistent(self) -> None:
        assert "check_unmeasurable" in at._FAILURE_PATTERN_NAMES
        assert set(at._PATTERN_DETECTORS) == set(at._FAILURE_PATTERN_NAMES) == set(at._PATTERN_TO_MAST)
        assert len(at._FAILURE_PATTERN_NAMES) == 12
        assert at._PATTERN_TO_MAST["check_unmeasurable"] == "Inadequate verification"

    def test_only_error_and_unavailable_hit(self) -> None:
        assert at._pattern_check_unmeasurable({"contract_status": cs.CHECK_ERROR}) is True
        assert at._pattern_check_unmeasurable({"oracle_check_status": cs.CHECK_UNAVAILABLE}) is True
        assert at._pattern_check_unmeasurable({"check_status": "ERROR"}) is True, "大小写折叠"
        for status in (None, "", cs.CHECK_OK, cs.CHECK_DISABLED):
            rec = {key: status for key in at._UNMEASURABLE_STATUS_KEYS}
            assert at._pattern_check_unmeasurable(rec) is False, f"status={status}"

    def test_every_channel_key_is_covered(self) -> None:
        # 键集合必须按字面钉住：只按 `for key in _UNMEASURABLE_STATUS_KEYS` 自证时，
        # 偷偷删掉一个键不会让任何断言变红（读者与词表同源 ⇒ 循环恒真）。
        assert set(at._UNMEASURABLE_STATUS_KEYS) == {
            "contract_status",
            "safety_check_status",
            "static_check_status",
            "oracle_check_status",
            "check_status",
        }, "5 个消费 trace 的 status 通道缺一不可"
        for key in at._UNMEASURABLE_STATUS_KEYS:
            assert at._pattern_check_unmeasurable({key: cs.CHECK_ERROR}) is True, key

    def test_archive_caliber_never_hits(self) -> None:
        """归档零影响的判据：历史行不带 status 键（探针 C：1702 文件 / 每个键出现 0 次）。

        第 3 条是"未来形状"——键都在但取值 None（本轮 node 未执行时的落盘面），
        同样必须不命中：`None` 是"没做这条腿"，不是"这条腿没测成"。
        """
        records = [
            {"event": "task_end", "task": "a", "contract_missing_symbols": None, "mypy_findings_count": 0},
            {"event": "task_end", "task": "b", "contract_missing_symbols": [], "oracle_findings": []},
            {
                "event": "task_end",
                "task": "c",
                "contract_status": None,
                "static_check_status": None,
                "check_status": None,
            },
        ]
        report = at.match_failure_patterns(records)
        assert report["patterns"]["check_unmeasurable"]["count"] == 0
        assert report["matched_records"] == 0, "历史行不得被本轮新增的读者判成「没测成」"

    def test_real_trace_shape_reaches_the_detector(self) -> None:
        """status 藏在 `output` 内层（trace 落盘形状），`_flatten_record` 必须抬起来。"""
        records = [
            {"event": "node", "task": "t1", "node": "generator", "output": {"oracle_check_status": cs.CHECK_ERROR}},
            {"event": "node", "task": "t2", "node": "generator", "output": {"oracle_check_status": cs.CHECK_OK}},
        ]
        report = at.match_failure_patterns(records)
        assert report["patterns"]["check_unmeasurable"]["count"] == 1
        assert report["patterns"]["check_unmeasurable"]["examples"] == ["t1"]


# ═══ 6. 静态类型层：state.py 口径注释的实现 ═════════════════════════════════

_TARGET_CODE = "def add(a, b):\n    return a - b\n"
_BASE_PATCH = "```python\ndef add(a, b):\n    return a + b\n```"
_TEST_OUTPUT = "AssertionError: assert -1 == 3"
_FAILED_CASES = [{"name": "test_add", "error": "AssertionError: expected 3, got -1"}]


def _reply() -> str:
    return json.dumps(
        {
            "root_cause": "加法实现误用了减法",
            "error_category": "assertion",
            "fix_strategy": "改回加号",
            "patch": _BASE_PATCH,
        },
        ensure_ascii=False,
    )


def _run_debug(monkeypatch: pytest.MonkeyPatch, static_check_status: str | None) -> dict[str, Any]:
    """零 LLM 跑一次 `DebuggerAgent.debug`，把静态层返回值钉成给定 status + 空疑点。"""
    agent = DebuggerAgent()
    queue: deque[str] = deque([_reply()])

    def fake_call(user_message: str, *args: Any, **kwargs: Any) -> str:
        assert queue, "LLM 调用次数超出脚本预设"
        return queue.popleft()

    def fake_type_repair(_original: str, _patched: str) -> dict[str, Any]:
        return {
            "repaired": False,
            "repaired_code": "",
            "findings": [],
            "mypy_findings_count": 0,
            "static_check_status": static_check_status,
            "static_check_outcomes": [
                {"backend": "mypy", "status": static_check_status or cs.CHECK_DISABLED, "reason": "bl-lock"}
            ],
        }

    monkeypatch.setattr(agent, "_call_llm_with_cache", fake_call)
    monkeypatch.setattr(debugger_mod, "type_repair_layer", fake_type_repair)
    return agent.debug(target_code=_TARGET_CODE, test_output=_TEST_OUTPUT, failed_cases=list(_FAILED_CASES))


@pytest.mark.unit
class TestStaticLayerConsumer:
    def test_unmeasurable_status_is_disclosed_when_findings_empty(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="src.agents.debugger"):
            result = _run_debug(monkeypatch, cs.CHECK_ERROR)
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "2.1 静态类型层不可测量（status=error）" in text
        assert "不构成「无类型问题」证据" in text
        assert result["static_check_status"] == cs.CHECK_ERROR
        assert result["type_repair_findings"] == []

    def test_ok_status_is_silent(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="src.agents.debugger"):
            _run_debug(monkeypatch, cs.CHECK_OK)
        assert "静态类型层不可测量" not in "\n".join(r.getMessage() for r in caplog.records)

    def test_patch_is_unchanged_by_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """判定不变：status 只换披露，补丁文本与读数与 ok / 缺席逐字相同。"""
        with_error = _run_debug(monkeypatch, cs.CHECK_ERROR)
        with_ok = _run_debug(monkeypatch, cs.CHECK_OK)
        legacy = _run_debug(monkeypatch, None)
        assert with_error["patch"] == with_ok["patch"] == legacy["patch"] == _BASE_PATCH
        assert with_error["mypy_findings_count"] == with_ok["mypy_findings_count"] == 0
