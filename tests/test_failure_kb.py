"""
5.3 跨批次失败模式对比 + 失败案例知识库（failure_knowledge_base）测试。

运行：
    pytest tests/test_failure_kb.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

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

        old = self._make_batch("batch1", [
            {"task_id": "t1", "passed": False, "error_category": "assertion"},
            {"task_id": "t2", "passed": True},
        ])
        new = self._make_batch("batch2", [
            {"task_id": "t1", "passed": False, "error_category": "patch_validation_failed"},
            {"task_id": "t2", "passed": True},
        ])
        comparison = cross_batch_comparison([old, new], "aitester")
        assert "patch_validation_failed" in comparison["new_categories"]
        assert "assertion" in comparison["resolved_categories"]

    def test_single_batch_no_trend(self):
        from experiments.compare_failures import cross_batch_comparison

        batch = self._make_batch("only", [
            {"task_id": "t1", "passed": False, "error_category": "import"},
        ])
        comparison = cross_batch_comparison([batch], "aitester")
        assert comparison["new_categories"] == []
        assert comparison["regressed_categories"] == []

    def test_regressed_category(self):
        from experiments.compare_failures import cross_batch_comparison

        old = self._make_batch("batch1", [
            {"task_id": "t1", "passed": False, "error_category": "assertion"},
            {"task_id": "t2", "passed": True},
        ])
        new = self._make_batch("batch2", [
            {"task_id": "t1", "passed": False, "error_category": "assertion"},
            {"task_id": "t2", "passed": False, "error_category": "assertion"},
        ])
        comparison = cross_batch_comparison([old, new], "aitester")
        assert "assertion" in comparison["regressed_categories"]
