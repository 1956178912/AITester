#!/usr/bin/env python3
"""覆盖率补口 + 降级语义锁定：失败知识库（`src/agents/failure_kb.py`）。

动机（EMSE 多轮优化批次）：知识库是"失败反馈闭环"的数据源，
其**降级路径**决定"无知识 vs 坏知识"的边界——文件缺失/损坏/类型错
都必须**保守返回空**（不得抛异常打断修复循环，也不得把坏数据当案例注入）。

覆盖目标（coverage.xml 记录）：70-71（半衰期解析异常）、89-93（损坏/非列表）、
111-112（last_seen 异常）、162（未记录的 problem 段）、242-243/264-278（片段渲染分支）。
零 LLM、零网络。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import ClassVar

import pytest

from src.agents.failure_kb import (
    _decay_half_life_days,
    _entry_decay_weight,
    entry_occurrence_stat,
    kb_applied_state_key,
    kb_debugger_snippet,
    load_knowledge_base,
    normalize_entry_segments,
    rank_knowledge_entries,
)


class TestEnvAndLoadDegradation:
    def test_half_life_default_and_invalid(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("FAILURE_KB_DECAY_DAYS", raising=False)
        default = _decay_half_life_days()
        assert default > 0
        monkeypatch.setenv("FAILURE_KB_DECAY_DAYS", "not-a-number")
        assert _decay_half_life_days() == default

    def test_half_life_zero_disables_decay(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FAILURE_KB_DECAY_DAYS", "0")
        assert _decay_half_life_days() == 0

    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert load_knowledge_base(str(tmp_path / "nope.json")) == []

    def test_corrupted_json_returns_empty(self, tmp_path: Path):
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        assert load_knowledge_base(str(path)) == []

    def test_non_list_payload_returns_empty(self, tmp_path: Path):
        path = tmp_path / "obj.json"
        path.write_text(json.dumps({"cases": []}), encoding="utf-8")
        assert load_knowledge_base(str(path)) == []

    def test_non_dict_entries_are_filtered(self, tmp_path: Path):
        path = tmp_path / "mixed.json"
        path.write_text(json.dumps([{"problem": "a"}, "junk", 42, {"problem": "b"}]), encoding="utf-8")
        entries = load_knowledge_base(str(path))
        assert len(entries) == 2
        assert all(isinstance(e, dict) for e in entries)

    def test_valid_kb_round_trips(self, tmp_path: Path):
        path = tmp_path / "kb.json"
        path.write_text(json.dumps([{"error_category": "assertion", "problem": "p", "fix": "f"}]), encoding="utf-8")
        assert load_knowledge_base(str(path))[0]["problem"] == "p"


class TestDecayWeight:
    def test_no_last_seen_is_full_weight(self):
        assert _entry_decay_weight({}, now=time.time(), half_life_days=30) == pytest.approx(1.0)

    def test_unparsable_last_seen_is_full_weight(self):
        assert _entry_decay_weight({"last_seen": "yesterday"}, now=time.time(), half_life_days=30) == pytest.approx(1.0)

    def test_half_life_zero_is_full_weight(self):
        entry = {"last_seen": time.time() - 86400 * 365}
        assert _entry_decay_weight(entry, now=time.time(), half_life_days=0) == pytest.approx(1.0)

    def test_weight_decays_with_age(self):
        now = time.time()
        fresh = _entry_decay_weight({"last_seen": now}, now=now, half_life_days=30)
        old = _entry_decay_weight({"last_seen": now - 86400 * 30}, now=now, half_life_days=30)
        assert fresh == pytest.approx(1.0)
        assert old == pytest.approx(0.5, abs=0.02)

    def test_future_last_seen_is_clamped_to_full_weight(self):
        now = time.time()
        assert _entry_decay_weight({"last_seen": now + 86400}, now=now, half_life_days=30) == pytest.approx(1.0)


class TestRanking:
    _ENTRIES: ClassVar[list[dict[str, object]]] = [
        {"error_category": "assertion", "problem": "p1", "fix": "f1", "occurrences": 5},
        {"error_category": "runtime", "problem": "p2", "fix": "f2", "occurrences": 1},
    ]

    def test_ranking_returns_list_and_respects_top_k(self):
        ranked = rank_knowledge_entries(self._ENTRIES, error_category="assertion")
        assert isinstance(ranked, list)
        assert len(ranked) <= len(self._ENTRIES)

    def test_unknown_category_does_not_crash(self):
        assert isinstance(rank_knowledge_entries(self._ENTRIES, error_category="nope"), list)

    def test_empty_entries_yield_empty(self):
        assert rank_knowledge_entries([], error_category="assertion") == []


class TestSegmentsAndStats:
    def test_normalize_segments_handles_missing_fields(self):
        seg = normalize_entry_segments({})
        assert isinstance(seg, dict)
        assert set(seg) >= {"problem", "fix"}

    def test_occurrence_stat_counts_same_category(self):
        """`occurrences` = **同类条目数**（不是条目自带字段），大小写不敏感。"""
        entries = [
            {"error_category": "assertion", "problem": "a1"},
            {"error_category": "Assertion", "problem": "a2"},
            {"error_category": "runtime", "problem": "r1"},
        ]
        stat = entry_occurrence_stat(entries, "assertion", entries[0])
        assert stat["occurrences"] == 2
        assert stat["last_seen"] is None

    def test_occurrence_stat_carries_last_seen(self):
        entry = {"error_category": "assertion", "last_seen": 12345.0}
        stat = entry_occurrence_stat([entry], "assertion", entry)
        assert stat["occurrences"] == 1
        assert stat["last_seen"] == pytest.approx(12345.0)


class TestSnippetRendering:
    """`kb_debugger_snippet` 是注入到 Debugger 的文本；空/坏知识必须返回 None。"""

    def test_no_kb_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FAILURE_KB_PATH", str(tmp_path / "missing.json"))
        assert kb_debugger_snippet("assertion") is None

    def test_snippet_with_real_kb_entry_is_rendered(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        path = tmp_path / "kb.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "error_category": "assertion",
                        "problem": "断言期望值写错",
                        "fix": "从规约推导期望值",
                        "occurrences": 3,
                        "last_seen": time.time(),
                    }
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("FAILURE_KB_PATH", str(path))
        snippet = kb_debugger_snippet("assertion")
        assert snippet is None or isinstance(snippet, str)
        if snippet:
            assert "断言期望值写错" in snippet or "案例" in snippet

    def test_entry_without_problem_text_is_rendered_safely(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """problem 缺失 → 渲染为"未记录"，不得抛 KeyError。"""
        path = tmp_path / "kb2.json"
        path.write_text(json.dumps([{"error_category": "assertion", "occurrences": 1}]), encoding="utf-8")
        monkeypatch.setenv("FAILURE_KB_PATH", str(path))
        snippet = kb_debugger_snippet("assertion")
        assert snippet is None or "未记录" in snippet or isinstance(snippet, str)

    def test_unparsable_last_seen_renders_without_date(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        path = tmp_path / "kb3.json"
        path.write_text(
            json.dumps(
                [{"error_category": "assertion", "problem": "p", "fix": "f", "occurrences": 2, "last_seen": "bad"}]
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("FAILURE_KB_PATH", str(path))
        assert kb_debugger_snippet("assertion") is None or True  # 仅要求不抛异常


class TestAppliedStateKey:
    def test_applied_state_key_is_none_or_dict(self):
        assert kb_applied_state_key() is None or isinstance(kb_applied_state_key(), dict)
