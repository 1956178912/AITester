"""A20（2026-10-18 第三方审查，P2）：轨迹 JSONL 结构完整性回归。

评审证据：`experiments/results/emse_ult_specir_probe_20261014/traces/
ult__string_contrast_aitester_1791954227.trace.jsonl` 第 10 行为非法 JSON
（未闭合字符串，第 201 列起，行尾停在 `min(s, key=<REDACTED>`）。

根因（两处叠加）：
1. `TraceSession._append` 先把记录 `json.dumps` 成单行 JSON，再对**整行**
   调用文本脱敏 `mask_sensitive_info`；
2. `logging_utils._SENSITIVE_PATTERNS[3]` 的 `key=<value>` 模式旧值字符类为
   `.{8,}`（贪婪、不排除引号/花括号），在 JSON 行上会一路吃到行尾并把
   闭合引号/花括号吞进匹配，替换后行变成未闭合字符串。

修复口径（本文件锁定）：
- 脱敏模式值字符类排除空白与 JSON 结构/转义字符，匹配结束于 token 边界；
- `TraceSession` / `dump_recent_to` 改为**先结构感知脱敏、再序列化**，
  写盘前 `json.loads` 结构守卫；
- 落盘 JSONL 每一行都必须是合法 JSON 对象，且凭证仍被脱敏。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.observability import trace as trace_mod
from src.observability.trace import (
    TraceSession,
    dump_recent_to,
    memory_buffer_snapshot,
    reset_memory_buffer,
    reset_trace_file_locks,
)
from src.utils.logging_utils import mask_sensitive_info


@pytest.fixture(autouse=True)
def _isolated_trace(monkeypatch):
    """隔离 AITESTER_TRACE_DIR 与进程级文件锁/内存缓冲（用例互不影响）。"""
    monkeypatch.delenv("AITESTER_TRACE_DIR", raising=False)
    reset_trace_file_locks()
    reset_memory_buffer()
    yield
    reset_trace_file_locks()
    reset_memory_buffer()


def _read_lines(path) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def _assert_every_line_is_json_object(path) -> list[dict]:
    records = []
    for number, line in enumerate(_read_lines(path), 1):
        assert line.strip(), f"第 {number} 行为空行"
        try:
            record = json.loads(line)
        except json.JSONDecodeError as e:  # pragma: no cover - 失败时给出可读诊断
            raise AssertionError(f"第 {number} 行不是合法 JSON：{e.msg}（col={e.colno}）；行尾={line[-80:]!r}") from e
        assert isinstance(record, dict), f"第 {number} 行不是 JSON 对象"
        records.append(record)
    return records


#: 评审损坏行同型诊断文本：`key=` 赋值出现在行内且其值 >= 8 字符。
_DIAGNOSIS_TEXT = (
    "函数 `string_contrast` 存在多处逻辑缺陷：\n\n"
    "1. 第 2 行过滤掉 None 导致长度不一致。\n\n"
    "2. 第 4 行：`min(s, key=some_identifier)` 的键函数与上面过滤后的列表错位。"
)


class TestMaskJsonStructuralSafety:
    """脱敏模式本身不得破坏 JSON 结构（修复第 2 处根因）。"""

    def test_key_assignment_in_serialized_json_stays_parseable(self):
        line = json.dumps({"event": "node", "output": {"root_cause": _DIAGNOSIS_TEXT}}, ensure_ascii=False)
        masked = mask_sensitive_info(line)
        record = json.loads(masked)  # 旧模式在这里抛 JSONDecodeError
        assert record["event"] == "node"
        # 凭证 token 仍被脱敏；值之后的 JSON 结构（闭合引号/花括号）保留
        assert "some_identifier" not in masked
        assert "key=<REDACTED>" in masked

    def test_quoted_assignment_value_in_json_stays_parseable(self):
        line = json.dumps({"output": 'config has key="placeholderSecret123" set'}, ensure_ascii=False)
        masked = mask_sensitive_info(line)
        record = json.loads(masked)
        assert "placeholderSecret123" not in masked
        assert "key=" in record["output"]

    @pytest.mark.parametrize(
        "text",
        [
            "min(s, key=some_identifier)",
            "end of line key=supersecretvalue",
            'x key="abcdefghijk"',
            "y secret=abcdefgh123456",
            "z password=SuperSecret123 tail",
        ],
    )
    def test_mask_is_json_safe_for_assignment_shapes(self, text):
        line = json.dumps({"output": {"root_cause": text}}, ensure_ascii=False)
        masked = mask_sensitive_info(line)
        # 1) 脱敏后整行仍必须是合法 JSON（旧贪婪模式会吞掉行尾闭合引号/花括号）
        record = json.loads(masked)
        assert set(record) == {"output"}
        assert isinstance(record["output"]["root_cause"], str)
        # 2) 凭证值仍被脱敏（不因收紧字符类而漏报）
        assert "<REDACTED" in masked
        # 3) JSON 闭合结构被保留：序列化后可 re-parse（等价于 1 的强化断言）
        assert (
            json.loads(json.dumps(record, ensure_ascii=False))["output"]["root_cause"] == record["output"]["root_cause"]
        )


class TestTraceSessionJsonlIntegrity:
    """TraceSession 落盘 JSONL 逐行合法 + 脱敏仍生效（修复第 1 处根因）。"""

    def test_diagnostic_with_key_assignment_produces_valid_jsonl(self, tmp_path):
        session = TraceSession("task_key_assign", trace_directory=str(tmp_path))
        session.record_node("debugger", output_summary={"root_cause": _DIAGNOSIS_TEXT})
        path = tmp_path / "task_key_assign.trace.jsonl"
        records = _assert_every_line_is_json_object(path)
        content = path.read_text(encoding="utf-8")
        assert "some_identifier" not in content
        assert "key=<REDACTED>" in content
        assert [r["event"] for r in records] == ["task_start", "node"]

    def test_long_diagnosis_text_truncated_before_redaction_still_valid(self, tmp_path):
        """超过 2000 字符的诊断文本（含 key= 赋值）先摘要截断再脱敏，仍须合法。"""
        long_text = ("缺陷说明 " * 600) + " min(s, key=some_identifier)"
        session = TraceSession("task_long", trace_directory=str(tmp_path))
        session.record_node("debugger", output_summary={"root_cause": long_text})
        records = _assert_every_line_is_json_object(tmp_path / "task_long.trace.jsonl")
        assert records[-1]["event"] == "node"

    def test_nested_credential_keys_still_redacted_and_valid(self, tmp_path):
        """嵌套映射键上的凭证（by_model sk-*）必须脱敏且行仍合法（历史契约）。"""
        session = TraceSession("task_nested", trace_directory=str(tmp_path))
        session.record_task_end(
            True,
            token_usage={"total_tokens": 1, "by_model": {"sk-ws-ABCDEFGH1234567890xy": 1}},
        )
        path = tmp_path / "task_nested.trace.jsonl"
        _assert_every_line_is_json_object(path)
        content = path.read_text(encoding="utf-8")
        assert "sk-ws-ABCDEFGH1234567890xy" not in content
        assert "<REDACTED_API_KEY>" in content

    def test_all_events_valid_json_across_full_sequence(self, tmp_path):
        session = TraceSession("task_seq", trace_directory=str(tmp_path), task_meta={"func": "f", "x": 1})
        session.record_node("planner", decision="plan_complete", input_summary={"note": "key=abcdefgh123456"})
        session.record_node("generator", output_summary={"patch": "-a\n+b"}, iteration=1)
        session.record_node("executor", output_summary={"stderr": "token=abcdefgh123456 failed"}, decision="debug")
        session.record_task_end(False, token_usage={"total_tokens": 3}, extra={"rag_stats": {"hits": 1}})
        records = _assert_every_line_is_json_object(tmp_path / "task_seq.trace.jsonl")
        assert [r["event"] for r in records] == ["task_start", "node", "node", "node", "task_end"]


class TestFailedTraceDumpIntegrity:
    """失败诊断出口（dump_recent_to）同样不得写坏 JSONL 行。"""

    def test_dump_redacts_and_keeps_jsonl_valid(self, tmp_path):
        # 内存缓冲保存的是原始记录（未经写盘脱敏），出口必须自行脱敏
        records = [
            {"event": "node", "task": "t1", "output": {"root_cause": _DIAGNOSIS_TEXT}},
            {"event": "node", "task": "t1", "output": {"error": "token=abcdefgh123456"}},
            {"event": "task_end", "task": "t1"},
        ]
        memory_buffer_snapshot("t1", records)
        path = dump_recent_to(str(tmp_path))
        assert path is not None
        out_records = _assert_every_line_is_json_object(path)
        content = Path(path).read_text(encoding="utf-8")
        assert "some_identifier" not in content
        assert "abcdefgh123456" not in content
        # 最后一条为快照边界标记
        assert out_records[-1]["event"] == "snapshot_task"

    def test_dump_with_unserializable_object_does_not_emit_bad_line(self, tmp_path):
        class _Weird:
            def __str__(self) -> str:  # json.dumps(default=str) 走这里
                return "weird-object key=abcdefgh123456"

        memory_buffer_snapshot("t2", [{"event": "node", "obj": _Weird()}])
        path = dump_recent_to(str(tmp_path))
        assert path is not None
        content = Path(path).read_text(encoding="utf-8")
        _assert_every_line_is_json_object(path)
        assert "abcdefgh123456" not in content


class TestRedactRecordHelper:
    """`_redact_record` 单元契约（结构不变、原对象不被修改）。"""

    def test_returns_new_structure_and_does_not_mutate_input(self):
        original = {"event": "node", "output": {"text": "key=abcdefgh123456"}, "n": 1}
        redacted = trace_mod._redact_record(original)
        assert redacted is not original
        assert original["output"]["text"] == "key=abcdefgh123456"
        assert "abcdefgh123456" not in redacted["output"]["text"]
        assert redacted["n"] == 1

    def test_non_string_objects_become_redacted_strings(self):
        class _Weird:
            def __str__(self) -> str:
                return "token=abcdefgh123456"

        redacted = trace_mod._redact_record({"obj": _Weird()})
        assert isinstance(redacted["obj"], str)
        assert "abcdefgh123456" not in redacted["obj"]


# ═══════════════════════════════════════════════════════════════════════════
#  2026-10-19 Y 轮审计补口：三处降级守卫此前零执行
# ═══════════════════════════════════════════════════════════════════════════
#
# 审计来源：`ff15a2f`→HEAD 的逐行覆盖率审计显示，A20 的三处"坏行不落盘"
# 守卫（`trace.py:147-149` / `260-262` / `469-471`）虽然存在且被注释详述，
# 却**从未被任何测试执行**。既有 `test_dump_with_unserializable_object_*`
# 名不副实：它的 `_Weird.__str__` 正常返回字符串，走的是"成功序列化"路径，
# 并没有触发丢弃分支；真正的触发条件是 `__str__` 自己抛异常。


class TestA20DegradationGuards:
    """A20 三级降级链：结构脱敏失败 → 原样序列化 → 序列化失败 → 丢弃该行。

    这条链的设计目标是"宁可少一条观测记录，也不写坏行污染整份轨迹"。
    任何一环被回退，坏行都可能落盘，而既有测试仍全绿。
    """

    def test_redact_record_degrades_to_raw_when_masking_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """第 1 级：`_redact_json_value` 抛异常 → 原样返回入参（不阻断写入）。"""

        def _boom(value, mask):
            raise RuntimeError("脱敏原语故障")

        monkeypatch.setattr(trace_mod, "_redact_json_value", _boom)
        record = {"event": "node", "text": "key=abcdefgh123456"}
        assert trace_mod._redact_record(record) is record, "脱敏失败须原样返回同一对象（不复制、不改写）"

    def test_append_drops_line_failing_structure_guard(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """第 2 级：`json.dumps` 成功但 `json.loads` 失败 → 丢弃该行，文件不落盘。

        正常情况下 dumps 的产物必然可 loads，故这是"序列化链路被上游破坏"的
        兜底断言；用替身 json 强制它失败，锁定"不合法即丢弃、绝不写坏行"。
        """

        class _FakeJson:
            dumps = staticmethod(json.dumps)

            @staticmethod
            def loads(text: str):
                raise ValueError("模拟结构损坏")

        monkeypatch.setattr(trace_mod, "json", _FakeJson)
        TraceSession("guard-task", trace_directory=str(tmp_path))

        path = tmp_path / "guard-task.trace.jsonl"
        assert not path.exists(), "结构守卫未拦住：坏行已落盘"

    def test_dump_skips_record_whose_str_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """第 3 级：`json.dumps(default=str)` 因 `__str__` 抛异常而失败 → 跳过该行。

        `_redact_record` 在此被替身为恒等函数，使坏对象**直达**序列化步骤，
        从而精确验证 `dump_recent_to` 自身的丢弃分支（而非上游降级兜住）。
        """

        class _Unstringable:
            def __str__(self) -> str:
                raise RuntimeError("无法字符串化")

        monkeypatch.setattr(trace_mod, "_redact_record", lambda record: record)
        reset_memory_buffer()
        memory_buffer_snapshot(
            "t-good",
            [{"event": "node", "payload": "正常记录"}],
        )
        memory_buffer_snapshot(
            "t-bad",
            [{"event": "node", "payload": _Unstringable()}],
        )

        path = dump_recent_to(str(tmp_path))
        assert path is not None
        records = _assert_every_line_is_json_object(path)
        payloads = [r.get("payload") for r in records if r.get("event") == "node"]
        assert payloads == ["正常记录"], "坏行必须被丢弃，好行必须保留"
