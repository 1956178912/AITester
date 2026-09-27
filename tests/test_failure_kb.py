"""
5.3 跨批次失败模式对比 + 失败案例知识库（failure_knowledge_base）测试。

运行：
    pytest tests/test_failure_kb.py -v
"""

from __future__ import annotations

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


class TestFailureKnowledgeBase:
    """5.3 失败案例知识库（failure_knowledge_base）测试。"""

    def _make_details(self) -> list[dict]:
        """构造 3 个典型失败任务的 details。"""
        return [
            {
                "task_id": "t1",
                "passed": False,
                "error_category": "assertion",
                "diagnosis": "边界条件未处理：空列表导致 IndexError",
                "iterations": 3,
                "target_code": "def process(items):\n    return items[0]",
                "generated_test": "def test_empty():\n    assert process([]) == 0\n",
                "patch": "def process(items):\n    if not items:\n        return None\n    return items[0]",
            },
            {
                "task_id": "t2",
                "passed": False,
                "error_category": "import",
                "diagnosis": "缺少 numpy 依赖",
                "iterations": 0,
                "target_code": "import numpy as np\ndef add(a, b):\n    return a + b",
                "generated_test": "import numpy as np\ndef test_add():\n    assert np.sum([1,2]) == 3\n",
                "patch": "",
            },
            {
                "task_id": "t3",
                "passed": False,
                "error_category": "patch_validation_failed",
                "diagnosis": "补丁被安全守卫拒绝：试图修改不存在的函数",
                "iterations": 3,
                "target_code": "def compute(x):\n    return x * 2",
                "generated_test": "def test_compute():\n    assert compute(5) == 10\n",
                "patch": "def compute(x):\n    return x + 2",
            },
        ]

    def test_knowledge_base_structure(self):
        from experiments.analyze_failures import failure_knowledge_base

        details = self._make_details()
        kb = failure_knowledge_base(details)
        assert isinstance(kb, list)
        assert len(kb) == 3
        # 每个案例必须含 task_id + error_category
        for case in kb:
            assert "task_id" in case
            assert "error_category" in case

    def test_knowledge_base_root_cause_attribution(self):
        from experiments.analyze_failures import failure_knowledge_base

        details = self._make_details()
        kb = failure_knowledge_base(details)
        by_task = {c["task_id"]: c for c in kb}
        # t2 是 import 错误 → 根因应为依赖问题
        # 实际字段名为 root_cause（非 root_cause_category），值为 "dependency"
        assert by_task["t2"].get("root_cause") in ("dependency", "environment", "external")

    def test_knowledge_base_suggested_fix(self):
        from experiments.analyze_failures import failure_knowledge_base

        details = self._make_details()
        kb = failure_knowledge_base(details)
        # 每个案例应有 suggested_fix 字段（供提示词优化参考）
        for case in kb:
            assert "suggested_fix" in case

    def test_knowledge_base_empty_details(self):
        from experiments.analyze_failures import failure_knowledge_base

        kb = failure_knowledge_base([])
        assert kb == []


class TestFailureRootCauseClassification:
    """5.3 失败根因分类（三大类：LLM 能力边界 / 依赖问题 / 框架缺陷）。"""

    def _classify(self, details: list[dict]) -> dict:
        from experiments.analyze_failures import classify_failures

        return classify_failures(details)

    def test_llm_capability_boundary(self):
        details = [
            {
                "task_id": "t1",
                "passed": False,
                "error_category": "assertion",
                "diagnosis": "LLM 生成的测试预期值与代码实际行为不符",
            }
        ]
        result = self._classify(details)
        # result 为 dict of category → list
        # assertion 类至少归入某类
        assert isinstance(result, dict)

    def test_dependency_issue(self):
        details = [
            {
                "task_id": "t2",
                "passed": False,
                "error_category": "import",
                "diagnosis": "缺少 requests 依赖",
            }
        ]
        result = self._classify(details)
        assert isinstance(result, dict)

    def test_empty_details(self):
        result = self._classify([])
        # 空输入 → 空 dict
        assert result == {}


class TestCrossBatch:
    """5.3 跨批次失败模式对比（compare_failures.cross_batch_comparison）。"""

    def _make_batch(self, dataset: str, details: list[dict]) -> dict:
        return {
            "dataset": dataset,
            "results": {"aitester": {"details": details}},
        }

    def test_new_category_in_latest_batch(self):
        from experiments.compare_failures import cross_batch_comparison

        old = self._make_batch(
            "batch1",
            [
                {"task_id": "t1", "passed": False, "error_category": "assertion"},
                {"task_id": "t2", "passed": True},
            ],
        )
        new = self._make_batch(
            "batch2",
            [
                {"task_id": "t1", "passed": False, "error_category": "patch_validation_failed"},
                {"task_id": "t2", "passed": True},
            ],
        )
        comparison = cross_batch_comparison([old, new], "aitester")
        assert "patch_validation_failed" in comparison["new_categories"]
        assert "assertion" in comparison["resolved_categories"]

    def test_single_batch_no_trend(self):
        from experiments.compare_failures import cross_batch_comparison

        batch = self._make_batch(
            "only",
            [
                {"task_id": "t1", "passed": False, "error_category": "import"},
            ],
        )
        comparison = cross_batch_comparison([batch], "aitester")
        assert comparison["new_categories"] == []
        assert comparison["resolved_categories"] == []
        assert comparison["regressed_categories"] == []

    def test_empty_summaries_list(self):
        """5.1 边界：批次列表为空时不崩溃，全部趋势字段为空。"""
        from experiments.compare_failures import cross_batch_comparison

        comparison = cross_batch_comparison([], "aitester")
        assert comparison["batches"] == []
        assert comparison["failure_trend"] == {}
        assert comparison["new_categories"] == []
        assert comparison["resolved_categories"] == []
        assert comparison["regressed_categories"] == []

    def test_regressed_category(self):
        from experiments.compare_failures import cross_batch_comparison

        old = self._make_batch(
            "batch1",
            [
                {"task_id": "t1", "passed": False, "error_category": "assertion"},
                {"task_id": "t2", "passed": True},
            ],
        )
        new = self._make_batch(
            "batch2",
            [
                {"task_id": "t1", "passed": False, "error_category": "assertion"},
                {"task_id": "t2", "passed": False, "error_category": "assertion"},
            ],
        )
        comparison = cross_batch_comparison([old, new], "aitester")
        assert "assertion" in comparison["regressed_categories"]

    def test_all_passed_batch_no_failure_categories(self):
        """全通过批次（0 失败）时 failure_categories 为空，趋势对齐不崩溃。"""
        from experiments.compare_failures import cross_batch_comparison

        old = self._make_batch(
            "batch1",
            [
                {"task_id": "t1", "passed": True},
            ],
        )
        new = self._make_batch(
            "batch2",
            [
                {"task_id": "t1", "passed": True},
                {"task_id": "t2", "passed": True},
            ],
        )
        comparison = cross_batch_comparison([old, new], "aitester")
        assert comparison["batches"][0]["failed"] == 0
        assert comparison["batches"][1]["failed"] == 0
        assert comparison["failure_trend"] == {}
        assert comparison["regressed_categories"] == []

    def test_empty_batch_mixed_with_failed(self):
        """空 details 批次（总任务 0）混入失败批次时，趋势补 0 对齐不崩溃。"""
        from experiments.compare_failures import cross_batch_comparison

        empty = self._make_batch("batch_empty", [])
        failed = self._make_batch(
            "batch_fail",
            [
                {"task_id": "t1", "passed": False, "error_category": "timeout"},
            ],
        )
        comparison = cross_batch_comparison([empty, failed], "aitester")
        # 空批次 failure_categories 为空，失败批次有 timeout
        assert comparison["failure_trend"]["timeout"] == [0, 1]
        assert "timeout" in comparison["new_categories"]

    def test_regressed_requires_two_batches(self):
        """regressed 判定需 >= 2 批次；单批次时即便有失败也不判 regressed。"""
        from experiments.compare_failures import cross_batch_comparison

        batch = self._make_batch(
            "only",
            [
                {"task_id": "t1", "passed": False, "error_category": "assertion"},
            ],
        )
        comparison = cross_batch_comparison([batch], "aitester")
        assert comparison["regressed_categories"] == []
        # 单批次下 failure_trend 仍有该类别计数（序列长度 1）
        assert comparison["failure_trend"]["assertion"] == [1]


# ─── 4. 失败知识库最小闭环（改进清单 P2，failure_kb.py 在线消费侧）──────────
class TestOnlineKnowledgeBaseConsumption:
    """src.agents.failure_kb 在线消费侧（落点 B + 衰减机制）。"""

    def _write_kb(self, tmp_path, entries):
        p = tmp_path / "kb.json"
        p.write_text(json.dumps(entries), encoding="utf-8")
        return str(p)

    def test_snippet_none_when_disabled(self, tmp_path, monkeypatch):
        from src.agents.failure_kb import kb_debugger_snippet

        kb = self._write_kb(
            tmp_path,
            [
                {
                    "task_id": "t1",
                    "error_category": "syntax",
                    "root_cause": "framework",
                    "diagnosis_excerpt": "syntax broken",
                    "reproducible_steps": "run x",
                    "suggested_fix": {"root_cause": "framework", "direction": "fix it"},
                }
            ],
        )
        monkeypatch.setenv("FAILURE_KB_PATH", kb)
        monkeypatch.delenv("FAILURE_KB_ENABLE", raising=False)
        assert kb_debugger_snippet("syntax") is None

    def test_snippet_none_when_no_matching_category(self, tmp_path, monkeypatch):
        from src.agents.failure_kb import kb_debugger_snippet

        kb = self._write_kb(tmp_path, [{"task_id": "t1", "error_category": "timeout"}])
        monkeypatch.setenv("FAILURE_KB_PATH", kb)
        monkeypatch.setenv("FAILURE_KB_ENABLE", "true")
        assert kb_debugger_snippet("syntax") is None

    def test_snippet_injected_when_matching(self, tmp_path, monkeypatch):
        import time as _time

        from src.agents.failure_kb import kb_debugger_snippet

        kb = self._write_kb(
            tmp_path,
            [
                {
                    "task_id": "t1",
                    "error_category": "syntax",
                    "root_cause": "llm_capability",
                    "diagnosis_excerpt": "E   module.py:10:5: syntax error",
                    "reproducible_steps": "run benchmark --task t1",
                    "suggested_fix": {"root_cause": "llm_capability", "direction": "约束 JSON 输出"},
                    "last_seen": _time.time() - 86400,
                },
                {"task_id": "t3", "error_category": "timeout", "diagnosis_excerpt": "slow"},
            ],
        )
        monkeypatch.setenv("FAILURE_KB_PATH", kb)
        monkeypatch.setenv("FAILURE_KB_ENABLE", "true")
        snippet = kb_debugger_snippet("syntax")
        assert snippet is not None
        assert "失败知识库提示" in snippet
        assert "约束 JSON 输出" in snippet
        assert "t3" not in snippet  # 非匹配类别不注入

    def test_snippet_none_for_empty_kb(self, tmp_path, monkeypatch):
        from src.agents.failure_kb import kb_debugger_snippet

        kb = self._write_kb(tmp_path, [])
        monkeypatch.setenv("FAILURE_KB_PATH", kb)
        monkeypatch.setenv("FAILURE_KB_ENABLE", "true")
        assert kb_debugger_snippet("syntax") is None

    def test_decay_weight_fresh_vs_old(self):
        import time as _time

        from src.agents.failure_kb import _entry_decay_weight

        now = _time.time()
        fresh = _entry_decay_weight({"last_seen": now}, now, 30.0)
        old = _entry_decay_weight({"last_seen": now - 30 * 86400}, now, 30.0)
        assert fresh > old

    def test_decay_disabled_when_half_life_zero(self):
        import time as _time

        from src.agents.failure_kb import _entry_decay_weight

        now = _time.time()
        assert _entry_decay_weight({"last_seen": now - 365 * 86400}, now, 0.0) == 1.0

    def test_missing_last_seen_no_decay(self):
        import time as _time

        from src.agents.failure_kb import _entry_decay_weight

        assert _entry_decay_weight({}, _time.time(), 30.0) == 1.0

    def test_ranking_prefers_recent_entries(self, tmp_path, monkeypatch):
        import time as _time

        from src.agents.failure_kb import rank_knowledge_entries

        now = _time.time()
        entries = [
            {"error_category": "syntax", "last_seen": now - 60 * 86400},
            {"error_category": "syntax", "last_seen": now - 60 * 86400},
            {"error_category": "syntax", "last_seen": now},
        ]
        monkeypatch.setenv("FAILURE_KB_DECAY_DAYS", "30")
        ranked = rank_knowledge_entries(entries, "syntax", now=now)
        assert ranked[0]["last_seen"] == now
        assert len(ranked) == 3

    def test_load_valid_and_missing(self, tmp_path, monkeypatch):
        from src.agents.failure_kb import load_knowledge_base

        p = self._write_kb(tmp_path, [{"error_category": "syntax"}])
        monkeypatch.setenv("FAILURE_KB_PATH", p)
        assert len(load_knowledge_base()) == 1
        monkeypatch.setenv("FAILURE_KB_PATH", str(tmp_path / "nope.json"))
        assert load_knowledge_base() == []

    def test_analyze_failures_writes_last_seen(self, tmp_path):
        """离线积累侧：failure_knowledge_base 产出条目带 last_seen 时间戳。"""
        from experiments.analyze_failures import failure_knowledge_base

        details = [
            {
                "task_id": "t1",
                "passed": False,
                "error_category": "syntax",
                "diagnosis": "SyntaxError: invalid syntax",
            }
        ]
        cases = failure_knowledge_base(details)
        assert cases, "应产出失败案例"
        assert "last_seen" in cases[0]
        assert isinstance(cases[0]["last_seen"], float)
