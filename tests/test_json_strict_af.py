"""AF 轮（2026-10-20）：严格 JSON 落盘回归锁。

缺陷族：Python `json.dumps` 默认 `allow_nan=True`，把 NaN / ±Infinity 写成裸
`NaN` / `Infinity`。Python 自己能读回，但这不是 RFC 8259 合法 JSON，严格解析器
（jq / Go / Rust serde / JS `JSON.parse`）会拒绝——生产端静默写出、消费端读不动。

本文件锁四个面：
1. `strict_json_dumps` 的路径点名与拒绝（含嵌套、dict 键、多指针）；
2. `atomic_write_json` / `run_b8._write_json` / `run_b8._Injection._record` 的
   fail-closed（不落盘、不覆盖旧内容、不留半行）；
3. trace 的"少记不误记"（含非有限浮点的记录整条丢弃，文件仍严格可解析）；
4. 全仓门禁 `scripts/gates/check_json_strict.py`：受控工件严格解析 + 源码
   JSON 文件写入点必须显式 `allow_nan=False`（含对真实仓跑一次）。

另锁 AE §5.6 的计量教训：文本里出现 "NaN" ≠ JSON 裸 token——字符串内的
同名文本合法且常见，grep 计数不能当作"非严格工件"证据。
"""

from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from experiments import run_b8_injection as b8
from experiments.run_b8_injection import _Injection
from src.observability.trace import (
    TraceSession,
    dump_recent_to,
    memory_buffer_snapshot,
    reset_memory_buffer,
    reset_trace_file_locks,
)
from src.utils.atomic_io import atomic_write_json
from src.utils.json_strict import NonFiniteJSONError, nonfinite_pointers, strict_json_dumps

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GATE_PATH = _REPO_ROOT / "scripts" / "gates" / "check_json_strict.py"
_spec = importlib.util.spec_from_file_location("check_json_strict", _GATE_PATH)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def _reject(token: str) -> Any:
    raise AssertionError(f"非标准 JSON token: {token}")


def _strict_loads(text: str) -> Any:
    return json.loads(text, parse_constant=_reject)


def _strict_loads_lines(path: Path) -> list[Any]:
    return [_strict_loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture(autouse=True)
def _isolated_trace(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AITESTER_TRACE_DIR", raising=False)
    reset_trace_file_locks()
    reset_memory_buffer()
    yield
    reset_trace_file_locks()
    reset_memory_buffer()


# ─── 1. 序列化器：拒绝 + 路径点名 ───────────────────────────────────────────


class TestStrictJsonDumps:
    def test_finite_payload_roundtrips_without_escaping_unicode(self):
        payload = {"中文": "值", "n": 1.5, "items": [True, None, "x"]}
        text = strict_json_dumps(payload, indent=2)
        assert _strict_loads(text) == payload
        assert "中文" in text

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_top_level_non_finite_rejected_with_pointer(self, value: float):
        with pytest.raises(NonFiniteJSONError) as excinfo:
            strict_json_dumps({"value": value})
        assert excinfo.value.pointers == ("$.value",)
        assert "$.value" in str(excinfo.value)

    def test_nested_pointer_names_list_and_dict(self):
        payload = {"arms": [{"cost": 1.0}, {"cost": float("inf")}]}
        assert nonfinite_pointers(payload) == ["$.arms[1].cost"]

    def test_dict_key_non_finite_is_named(self):
        payload = {float("nan"): {"ok": 1}}
        pointers = nonfinite_pointers(payload)
        assert len(pointers) == 1
        assert "<key" in pointers[0]

    def test_multiple_pointers_all_reported(self):
        payload = {"a": float("nan"), "b": [1, float("-inf")], "c": float("inf")}
        pointers = nonfinite_pointers(payload)
        assert pointers == ["$.a", "$.b[1]", "$.c"]
        with pytest.raises(NonFiniteJSONError) as excinfo:
            strict_json_dumps(payload)
        assert excinfo.value.pointers == ("$.a", "$.b[1]", "$.c")
        assert all(p in str(excinfo.value) for p in ("$.a", "$.b[1]", "$.c"))

    def test_many_pointers_truncated_with_total_count(self):
        payload = {f"k{i}": float("nan") for i in range(7)}
        with pytest.raises(NonFiniteJSONError) as excinfo:
            strict_json_dumps(payload)
        assert excinfo.value.pointers == tuple(f"$.k{i}" for i in range(7))
        assert "等 7 处" in str(excinfo.value), "截断显示但总数必须完整"

    def test_shared_or_cyclic_containers_do_not_hang(self):
        shared = [float("nan")]
        payload: dict[str, Any] = {"a": shared, "b": shared}
        assert nonfinite_pointers(payload) == ["$.a[0]"]
        cyclic: dict[str, Any] = {}
        cyclic["self"] = cyclic
        assert nonfinite_pointers(cyclic) == []

    def test_negative_control_lenient_parser_accepts_bare_tokens(self):
        # 这正是缺口：Python 读得回，所以只靠 json.loads 结构守卫发现不了。
        assert json.loads('{"v": NaN}')["v"] != json.loads('{"v": NaN}')["v"]
        with pytest.raises(AssertionError):
            _strict_loads('{"v": NaN}')

    def test_token_inside_string_is_legal_and_not_flagged(self):
        # AE §5.6 的"68 份"来自文本 grep；字符串内的 "NaN / Infinity" 是合法 JSON。
        payload = {"diagnosis": "x 为 NaN / inf，函数名 test_sqrt_positive_infinity"}
        text = strict_json_dumps(payload, indent=2)
        assert "x 为 NaN / inf" in text, "字符串内的 NaN 文本应原样保留，不被转义或删除"
        assert "test_sqrt_positive_infinity" in text
        assert _strict_loads(text) == payload, "文本中出现 NaN 不构成非严格 JSON"


# ─── 2. 原子写 / run_b8 写入口：fail-closed ─────────────────────────────────


class TestAtomicWriteJsonStrict:
    def test_non_finite_raises_and_does_not_touch_existing_target(self, tmp_path: Path):
        target = tmp_path / "keep.json"
        target.write_text('{"old": 1}', encoding="utf-8")
        with pytest.raises(NonFiniteJSONError):
            atomic_write_json(str(target), {"v": float("nan")})
        assert target.read_text(encoding="utf-8") == '{"old": 1}'
        assert not list(tmp_path.glob(".aitester_tmp_*"))

    def test_finite_payload_written_and_strictly_parseable(self, tmp_path: Path):
        target = tmp_path / "ok.json"
        atomic_write_json(str(target), {"v": 1.5})
        assert _strict_loads(target.read_text(encoding="utf-8")) == {"v": 1.5}


class TestRunB8WriterStrict:
    def test_write_json_rejects_non_finite_without_creating_file(self, tmp_path: Path):
        target = tmp_path / "out" / "REPORT.json"
        with pytest.raises(NonFiniteJSONError) as excinfo:
            b8._write_json(target, {"cost": float("inf")})
        assert excinfo.value.pointers == ("$.cost",)
        assert not target.exists()

    def test_write_json_finite_payload_strictly_parseable(self, tmp_path: Path):
        target = tmp_path / "out" / "REPORT.json"
        b8._write_json(target, {"cost": 0.0})
        assert _strict_loads(target.read_text(encoding="utf-8")) == {"cost": 0.0}

    def test_record_rejects_non_finite_without_partial_line(self, tmp_path: Path):
        injection = _Injection("on", inject_rounds=1, out_dir=tmp_path)
        with pytest.raises(NonFiniteJSONError):
            injection._record({"event": "node", "elapsed": float("nan")})
        records_path = tmp_path / "injection_records_on.jsonl"
        assert records_path.read_text(encoding="utf-8") == "", "含非有限浮点的记录不得留下半行"

    def test_record_finite_line_is_strict(self, tmp_path: Path):
        injection = _Injection("on", inject_rounds=1, out_dir=tmp_path)
        injection._record({"event": "node", "elapsed": 0.25})
        lines = _strict_loads_lines(tmp_path / "injection_records_on.jsonl")
        assert lines == [{"event": "node", "elapsed": 0.25, "arm": "on"}]


# ─── 3. trace：少记不误记 ───────────────────────────────────────────────────


class TestTraceStrictJsonl:
    def test_non_finite_record_is_dropped_and_file_stays_strict(self, tmp_path: Path, caplog):
        session = TraceSession("nan_task", trace_directory=str(tmp_path))
        with caplog.at_level(logging.WARNING, logger="src.observability.trace"):
            session.record_node("executor", output_summary={"duration_ms": float("nan")})
        path = tmp_path / "nan_task.trace.jsonl"
        records = _strict_loads_lines(path)
        assert [r["event"] for r in records] == ["task_start"], "含非有限浮点的 node 记录必须整条丢弃"
        assert "丢弃本条" in caplog.text

    def test_dump_recent_drops_non_finite_record_but_keeps_marker(self, tmp_path: Path, caplog):
        memory_buffer_snapshot("t-bad", [{"event": "node", "task": "t-bad", "v": float("inf")}])
        with caplog.at_level(logging.WARNING, logger="src.observability.trace"):
            path = dump_recent_to(str(tmp_path))
        assert path is not None
        records = _strict_loads_lines(Path(path))
        assert [r["event"] for r in records] == ["snapshot_task"], "坏记录丢弃，快照边界标记保留"
        assert "丢弃该行" in caplog.text

    def test_finite_record_still_written(self, tmp_path: Path):
        session = TraceSession("ok_task", trace_directory=str(tmp_path))
        session.record_node("executor", output_summary={"duration_ms": 12.5})
        records = _strict_loads_lines(tmp_path / "ok_task.trace.jsonl")
        assert [r["event"] for r in records] == ["task_start", "node"]


# ─── 4. 全仓门禁 ───────────────────────────────────────────────────────────


def _seed_allowlist(root: Path) -> None:
    for rel in gate._ALLOWLIST:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"event": "truncated\n', encoding="utf-8")


def _write_valid_fixture(root: Path) -> None:
    (root / "ok.json").write_text('{"v": 1}', encoding="utf-8")
    (root / "ok.jsonl").write_text('{"v": 1}\n{"v": 2}\n', encoding="utf-8")
    (root / "ok_sink.py").write_text(
        "import json\nwith open('out.json', 'w') as f:\n    json.dump({'v': 1}, f, allow_nan=False)\n",
        encoding="utf-8",
    )


class TestStrictJsonGate:
    def test_real_repo_passes(self, capsys):
        """源码/工件任一回归（如某写入点丢掉 allow_nan=False）本用例即红。"""
        assert gate.main([]) == 0
        out = capsys.readouterr().out
        assert "违规 0" in out

    def test_fixture_passes_with_valid_artifacts_and_sinks(self, tmp_path: Path):
        _seed_allowlist(tmp_path)
        _write_valid_fixture(tmp_path)
        assert gate.main(["--root", str(tmp_path)]) == 0

    def test_bare_nan_artifact_fails_and_names_file(self, tmp_path: Path, capsys):
        _seed_allowlist(tmp_path)
        _write_valid_fixture(tmp_path)
        (tmp_path / "bad.json").write_text('{"v": NaN}', encoding="utf-8")
        assert gate.main(["--root", str(tmp_path)]) == 1
        out = capsys.readouterr().out
        assert "bad.json" in out and "NaN" in out

    def test_nan_text_inside_string_is_not_flagged(self, tmp_path: Path):
        """AE §5.6 计量教训的机器化：文本 grep 会把字符串内的 NaN 计成违规。"""
        _seed_allowlist(tmp_path)
        _write_valid_fixture(tmp_path)
        (tmp_path / "mentions.json").write_text(
            '{"diagnosis": "x 为 NaN / Infinity，函数 test_sqrt_positive_infinity"}',
            encoding="utf-8",
        )
        assert gate.main(["--root", str(tmp_path)]) == 0

    def test_truncated_jsonl_line_fails_with_line_number(self, tmp_path: Path, capsys):
        _seed_allowlist(tmp_path)
        _write_valid_fixture(tmp_path)
        (tmp_path / "bad.jsonl").write_text('{"v": 1}\n{"v": "unterminated\n', encoding="utf-8")
        assert gate.main(["--root", str(tmp_path)]) == 1
        out = capsys.readouterr().out
        assert "bad.jsonl" in out and "line 2" in out

    def test_source_sink_without_allow_nan_fails(self, tmp_path: Path, capsys):
        _seed_allowlist(tmp_path)
        _write_valid_fixture(tmp_path)
        (tmp_path / "bad_sink.py").write_text(
            "import json\nwith open('x.json', 'w') as f:\n    json.dump({'v': 1}, f)\n",
            encoding="utf-8",
        )
        assert gate.main(["--root", str(tmp_path)]) == 1
        out = capsys.readouterr().out
        assert "bad_sink.py" in out and "allow_nan" in out

    def test_allowlist_drift_when_file_becomes_strict(self, tmp_path: Path, capsys):
        _seed_allowlist(tmp_path)
        _write_valid_fixture(tmp_path)
        first = next(iter(gate._ALLOWLIST))
        (tmp_path / first).write_text("{}\n", encoding="utf-8")
        assert gate.main(["--root", str(tmp_path)]) == 1
        out = capsys.readouterr().out
        assert "豁免漂移" in out and first in out

    def test_empty_root_fails_instead_of_vacuous_pass(self, tmp_path: Path, capsys):
        assert gate.main(["--root", str(tmp_path)]) == 1
        out = capsys.readouterr().out
        assert "空集合" in out
