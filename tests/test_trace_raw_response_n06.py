"""N06 原始 LLM 响应归档契约锁（开关默认关 / 开启不截断 / 关闭整体忽略）。"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

tr = importlib.import_module("src.observability.trace")


@pytest.fixture()
def _tracer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AITESTER_TRACE_DIR", str(tmp_path))
    tr.reset_trace_file_locks()
    tracer = tr.TraceSession(task_id="n06__demo") if hasattr(tr, "TraceSession") else None
    if tracer is None:  # 类名兜底：模块按 gettrace/工厂形态提供则跳过
        pytest.skip("TraceSession 形态变化，需更新本锁的构造方式")
    yield tracer, tmp_path
    tr.reset_trace_file_locks()


def _read_lines(tmp_path: Path) -> list[dict]:
    out = []
    for f in Path(tmp_path).rglob("*.jsonl"):
        out.extend(json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip())
    return out


def test_default_off_ignores_raw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """默认关：即使调用方传原文也不落盘（体积/合规默认）。"""
    monkeypatch.setenv("AITESTER_TRACE_DIR", str(tmp_path))
    monkeypatch.delenv("AITESTER_TRACE_RAW_RESPONSE_ENABLE", raising=False)
    tr.reset_trace_file_locks()
    tracer = tr.TraceSession(task_id="n06__off")
    tracer.record_node("generator", output_summary="ok", raw_llm_response="RAW" * 500)
    recs = _read_lines(tmp_path)
    assert recs, "node 事件应落盘"
    assert all("raw_llm_response" not in r for r in recs)


def test_enabled_writes_verbatim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """开启后响应**不截断**落盘（_summarize 的头尾截断不得作用于该字段）。

    语义边界（N06 冻结口径）：归档的是**过凭证脱敏后的完整响应**——
    mask_sensitive_info 与全仓日志同源，凭证形态内容照常打码（安全边界
    优先于逐字节保真）；"不截断"指长文本头尾截断不作用于该字段。
    """
    monkeypatch.setenv("AITESTER_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITESTER_TRACE_RAW_RESPONSE_ENABLE", "true")
    tr.reset_trace_file_locks()
    tracer = tr.TraceSession(task_id="n06__on")
    body = "\n".join(f"def helper_{i}(x):\n    return x + {i}" for i in range(400))
    tracer.record_node("generator", output_summary="ok", raw_llm_response=body)
    recs = _read_lines(tmp_path)
    hit = [r for r in recs if "raw_llm_response" in r]
    assert hit and hit[0]["raw_llm_response"] == body, "非凭证长文本必须逐字节保留"


def test_enabled_still_redacts_credential_shapes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """凭证形态内容即使走 raw 通道也必须打码（脱敏边界优先）。"""
    monkeypatch.setenv("AITESTER_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITESTER_TRACE_RAW_RESPONSE_ENABLE", "true")
    tr.reset_trace_file_locks()
    tracer = tr.TraceSession(task_id="n06__redact")
    tracer.record_node("generator", output_summary="ok", raw_llm_response="key=sk-PLACEHOLDER_VALUE_1234")
    recs = _read_lines(tmp_path)
    hit = [r for r in recs if "raw_llm_response" in r]
    assert hit, "raw 字段应落盘"
    assert "sk-PLACEHOLDER_VALUE_1234" not in hit[0]["raw_llm_response"], "凭证形态必须被打码"


def test_enabled_but_absent_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """开启但调用方未传 → 不写该键（按需扩展口径：键缺省不出现）。"""
    monkeypatch.setenv("AITESTER_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITESTER_TRACE_RAW_RESPONSE_ENABLE", "true")
    tr.reset_trace_file_locks()
    tracer = tr.TraceSession(task_id="n06__absent")
    tracer.record_node("generator", output_summary="ok")
    recs = _read_lines(tmp_path)
    assert recs and all("raw_llm_response" not in r for r in recs)
