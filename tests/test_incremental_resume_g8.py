"""过夜跑批断点续跑的回归锁（2026-11-01 G8 全量 178 卡死事故）。

覆盖 run_benchmark.py 新增三 helper 的判据：
- _append_incremental_result：空结果不落盘；落盘行 flush+fsync；
- _load_incremental_results：半行损坏（击杀瞬间截断）按行忽略；
  空 results 行与坏 JSON 行不进恢复集合；后行覆盖防御重复行；
- _parse_skip_task_ids：env 缺省=空集；逗号分隔 + 空白容错。

锁纪律（记忆 #9/#13）：判据落结构化单元，不用裸子串断言。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.run_benchmark import (
    _append_incremental_result,
    _load_incremental_results,
    _parse_skip_task_ids,
)


def test_append_then_load_roundtrip(tmp_path: Path) -> None:
    """非空结果 append → load 往返一致。"""
    _append_incremental_result(str(tmp_path), "task_a", {"aitester": {"detected": True, "elapsed_seconds": 1.5}})
    _append_incremental_result(str(tmp_path), "task_b", {"aitester": {"detected": False, "elapsed_seconds": 2.0}})
    done = _load_incremental_results(str(tmp_path))
    assert set(done) == {"task_a", "task_b"}
    assert done["task_a"]["aitester"]["detected"] is True
    assert done["task_b"]["aitester"]["elapsed_seconds"] == 2.0


def test_append_skips_empty_results(tmp_path: Path) -> None:
    """空 task_results（异常未产出）不落盘——恢复时自然重跑该任务。"""
    _append_incremental_result(str(tmp_path), "task_a", {})
    assert not (tmp_path / "INCREMENTAL_RESULTS.jsonl").exists()
    assert _load_incremental_results(str(tmp_path)) == {}


def test_load_ignores_truncated_and_malformed_lines(tmp_path: Path) -> None:
    """半行（击杀瞬间截断）与坏 JSON 行按行忽略，好行不受影响。"""
    good = json.dumps({"task_id": "task_a", "results": {"aitester": {"detected": True}}}, ensure_ascii=False)
    truncated = '{"task_id": "task_b", "resul'  # 击杀截断的半行
    broken = "{not-json}}"
    empty_results = json.dumps({"task_id": "task_c", "results": {}}, ensure_ascii=False)
    path = tmp_path / "INCREMENTAL_RESULTS.jsonl"
    path.write_text("\n".join([good, truncated, broken, empty_results]) + "\n", encoding="utf-8")
    done = _load_incremental_results(str(tmp_path))
    assert set(done) == {"task_a"}


def test_load_last_line_wins_on_duplicate_task_id(tmp_path: Path) -> None:
    """同一 task_id 重复出现时后行覆盖（防御性语义）。"""
    first = json.dumps({"task_id": "task_a", "results": {"aitester": {"v": 1}}}, ensure_ascii=False)
    second = json.dumps({"task_id": "task_a", "results": {"aitester": {"v": 2}}}, ensure_ascii=False)
    (tmp_path / "INCREMENTAL_RESULTS.jsonl").write_text(first + "\n" + second + "\n", encoding="utf-8")
    done = _load_incremental_results(str(tmp_path))
    assert done["task_a"]["aitester"]["v"] == 2


def test_parse_skip_ids_env_missing_empty_and_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """env 缺省=空集；逗号分隔 + 首尾空白容错；空片段剔除。"""
    monkeypatch.delenv("AITESTER_SKIP_TASK_IDS", raising=False)
    assert _parse_skip_task_ids() == set()
    monkeypatch.setenv("AITESTER_SKIP_TASK_IDS", " task_x , task_y,,task_z ")
    assert _parse_skip_task_ids() == {"task_x", "task_y", "task_z"}
    monkeypatch.setenv("AITESTER_SKIP_TASK_IDS", "")
    assert _parse_skip_task_ids() == set()


def test_append_line_is_self_contained_jsonl(tmp_path: Path) -> None:
    """每行是完整 JSON 对象（击杀时最多损失最后一行，不破坏前面行）。"""
    _append_incremental_result(str(tmp_path), "task_a", {"aitester": {"v": 1}})
    _append_incremental_result(str(tmp_path), "task_b", {"aitester": {"v": 2}})
    lines = (tmp_path / "INCREMENTAL_RESULTS.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["task_id"] == "task_a"
    assert json.loads(lines[1])["task_id"] == "task_b"


def test_append_sanitizes_nonfinite_to_null(tmp_path: Path) -> None:
    """非有限浮点（NaN/Inf）落盘前折 null（缺测语义）——append 不抛
    ValueError（单任务级数据问题不得放大成整批跑批中断），恢复端
    读回 None 不影响其余字段（2026-11-02 CI AF 门禁修复，B1 批
    _sanitize_nonfinite 范式对齐）。"""
    _append_incremental_result(
        str(tmp_path),
        "task_nan",
        {"aitester": {"score": float("nan"), "elapsed_seconds": float("inf"), "neg": float("-inf"), "v": 1}},
    )
    lines = (tmp_path / "INCREMENTAL_RESULTS.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])  # json.loads 默认接受 NaN/Infinity；行内若残留会原样解析
    results = rec["results"]["aitester"]
    assert results["score"] is None
    assert results["elapsed_seconds"] is None
    assert results["neg"] is None
    assert results["v"] == 1
    # 严格 JSON 判据（AF 门禁语义）：无裸 NaN/Infinity 字面量残留
    for token in ("NaN", "Infinity"):
        assert token not in lines[0]


def test_append_uses_strict_json_writer(tmp_path: Path) -> None:
    """写入点显式 allow_nan=False（AF 门禁 AST 级判据的运行时对称锁）：
    传入含非有限浮点的 results 时行内不出现 NaN/Infinity 字面量，
    且与 sanitize 语义（折 null）一致。"""
    _append_incremental_result(str(tmp_path), "task_inf", {"probe": {"a": float("inf"), "b": [float("nan")]}})
    line = (tmp_path / "INCREMENTAL_RESULTS.jsonl").read_text(encoding="utf-8").strip()
    rec = json.loads(line)
    assert rec["results"]["probe"]["a"] is None
    assert rec["results"]["probe"]["b"] == [None]
    assert "NaN" not in line and "Infinity" not in line
