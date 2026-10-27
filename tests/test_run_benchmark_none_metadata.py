"""复杂度评分 metadata 兜底回归（EU 轮迁移到共享评分入口）。

历史：2026-10-12 ULT 实跑批次（SPEC_REPLACE_AB_SCALE87_REPORT §4.1）中，
官方 ULT_Lite 记录不含 cyclomatic_complexity 字段，dataset_ult 加载器写出的
metadata 该键为显式 None；run_benchmark 内联的
``int(task.metadata.get("cyclomatic_complexity", 1))`` 在**键存在**时返回 None
（而非 default）→ ``int(None)`` 抛 TypeError → 每个 ULT 任务在入口即崩。

EU 轮把复杂度评分收敛到 ``complexity_router.score_task_complexity``
（CLI / 搜索 / benchmark 共用的唯一实现），metadata 兜底随之迁移。本文件锁：

1. 键缺失 / 键存在但 None / 键存在且 int 三态；
2. 源码可解析时以源码口径为准（metadata cc 仅作解析失败兜底）；
3. count_imports 异常时回退 metadata num_imports；
4. run_benchmark 委托工厂（传 ``task.metadata``），不再内联评分。
"""

from __future__ import annotations

import pathlib

from src.api.complexity_router import score_task_complexity


def _ult_like_metadata() -> dict:
    """模拟 ULT_Lite 加载器产出的 metadata（cyclomatic_complexity 显式 None）。"""
    return {
        "source": "ult",
        "function_name": "fn",
        "cyclomatic_complexity": None,
        "test_cases": "import fn\n\ndef test_1():\n    assert fn() == 1\n",
        "fixed": "def fn():\n    return 1\n",
        "gold_tests_raw": "assert fn() == 1",
        "no_gold_tests": False,
        "mutation_primary_metric": True,
        "suggested_function": "fn",
        "is_cross_file": False,
    }


class TestNoneMetadataKeyFallback:
    """metadata 键"存在但 None"态不再崩溃，且走默认统计口径。"""

    def test_key_absent_uses_default(self) -> None:
        score = score_task_complexity("def f():\n    return 1\n", {})
        assert score.breakdown["raw_files"] == 1
        assert score.breakdown["raw_cc"] == 1
        assert score.breakdown["raw_deps"] == 0

    def test_key_present_none_uses_default(self) -> None:
        score = score_task_complexity(
            "def f():\n    return 1\n",
            {"num_files": None, "cyclomatic_complexity": None, "num_imports": None},
        )
        assert score.breakdown["raw_files"] == 1
        assert score.breakdown["raw_cc"] == 1
        assert score.breakdown["raw_deps"] == 0

    def test_key_present_int_kept(self, monkeypatch) -> None:
        """可解析源码：num_files 与 num_imports 兜底生效，cc 仍以源码为准。"""
        import src.api.complexity_router as cr

        def _boom(*_a, **_k):
            raise RuntimeError("import 计数失败")

        monkeypatch.setattr(cr, "count_imports", _boom)
        source = "def f():\n    return 1\n" + "\n".join(f"C{i} = {i}" for i in range(498)) + "\n"
        score = score_task_complexity(
            source,
            {"num_files": 3, "cyclomatic_complexity": 17, "num_imports": 5},
        )
        assert score.breakdown["raw_files"] == 3
        assert score.breakdown["raw_cc"] == 1
        assert score.breakdown["raw_deps"] == 5

    def test_ult_like_metadata_does_not_raise(self) -> None:
        """不抛异常即通过（修复前 int(None) 在此链路崩溃）。"""
        score = score_task_complexity("def fn():\n    return 1\n", _ult_like_metadata())
        assert score.complexity_class in {"simple", "medium", "complex"}
        assert score.breakdown["raw_cc"] == 1
        assert score.breakdown["raw_files"] == 1

    def test_parseable_source_ignores_metadata_cc(self) -> None:
        """源码可解析时必须用源码圈复杂度，metadata 仅作解析失败兜底。"""
        score = score_task_complexity("def f():\n    return 1\n", {"cyclomatic_complexity": 25})
        assert score.breakdown["raw_cc"] == 1


class TestRunBenchmarkDelegates:
    """源码级守卫：benchmark 只传 metadata，不允许残留第二份评分实现。"""

    def _source(self) -> str:
        here = pathlib.Path(__file__).resolve()
        return (here.parents[1] / "experiments" / "run_benchmark.py").read_text(encoding="utf-8")

    def test_delegates_metadata_to_factory(self) -> None:
        assert "task_metadata=task.metadata" in self._source()

    def test_no_bare_int_metadata_get_forms(self) -> None:
        src = self._source()
        assert 'int(task.metadata.get("cyclomatic_complexity", 1))' not in src
        assert 'int(task.metadata.get("num_files", 1))' not in src
        assert 'int(task.metadata.get("num_imports", 0))' not in src

    def test_no_inline_scoring(self) -> None:
        src = self._source()
        assert "compute_complexity_score(" not in src
        assert "_count_cc(" not in src
