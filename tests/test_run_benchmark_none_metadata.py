"""run_benchmark 复杂度路由 int(metadata.get(...)) 的 None 兜底回归测试。

2026-10-12 ULT 实跑批次勘误（SPEC_REPLACE_AB_SCALE87_REPORT §4.1）：
官方 ULT_Lite 记录**不含** cyclomatic_complexity 字段，dataset_ult 加载器
写出的 metadata 该键为显式 None（键存在但值 None）。run_benchmark 复杂度
路由（routing_enabled() 默认 True，strategy=complexity_aware）此前调用
``int(task.metadata.get("cyclomatic_complexity", 1))``——
``dict.get(key, default)`` 在**键存在**时返回 None（而非 default）→
``int(None)`` 抛 TypeError → 每个 ULT 任务在任务函数入口即崩，
46 任务全崩（首轮实跑 0 完成）。

本测试锁死修复后的 4 处 ``int(metadata.get(key) or default)`` 兜底行为：
metadata 含 ``cyclomatic_complexity=None``（或键缺失）时，任务构造链路
不再崩溃，且复杂度评分正常产出 complexity_class。

测试方式（零 LLM 成本）：
- 直接驱动 ``run_single_task`` 的 metadata→int 路径太昂贵（会跑 LLM）。
- 改用一个**轻量探针函数**复刻 4 处兜底调用（与 run_benchmark.py:
  1821/1835/1858/1865 同构），断言：
  1. metadata 键缺失 → 走 default；
  2. metadata 键存在但 None → 走 default（``or`` 兜底，**非** ``.get``
     默认值）；
  3. metadata 键存在且 int → 原值。
  并额外断言 run_benchmark 模块本身已含 4 处 ``or`` 兜底源码（源码级
  守卫，防未来重构回退到 ``.get(key, default)``）。
"""

from __future__ import annotations

import pathlib


# 复刻 run_benchmark.py 复杂度路由 4 处兜底调用（与源码同构）。
# _route_int_get(metadata, key, default) 等价于修复后的
# int(metadata.get(key) or default) 单点抽取，供 3 态行为断言。
def _route_int_get(metadata: dict, key: str, default: int) -> int:
    """等价 run_benchmark 复杂度路由兜底：键缺失/键存在但 None 均回退 default。"""
    return int(metadata.get(key) or default)


def _probe_all_four(metadata: dict) -> dict:
    """复刻 run_benchmark.py:1821/1835/1858/1865 的 4 处兜底调用。"""
    return {
        "num_files": _route_int_get(metadata, "num_files", 1),
        "cc_primary": _route_int_get(metadata, "cyclomatic_complexity", 1),
        "cc_fallback": _route_int_get(metadata, "cyclomatic_complexity", 1),
        "num_imports": _route_int_get(metadata, "num_imports", 0),
    }


class TestNoneMetadataKeyFallback:
    """metadata 键"存在但 None"态的 int() 兜底回归。"""

    def test_key_absent_uses_default(self) -> None:
        """键缺失 → 走 default（.get 返回 None，or default 兜底）。"""
        out = _probe_all_four({})
        assert out["num_files"] == 1
        assert out["cc_primary"] == 1
        assert out["cc_fallback"] == 1
        assert out["num_imports"] == 0

    def test_key_present_none_uses_default(self) -> None:
        """键存在但 None → 走 default（关键回归点：.get(key, d) 会返回
        None 而非 d，int(None) 崩；or 兜底修复后走 d）。"""
        out = _probe_all_four(
            {
                "num_files": None,
                "cyclomatic_complexity": None,
                "num_imports": None,
            }
        )
        assert out["num_files"] == 1
        assert out["cc_primary"] == 1
        assert out["cc_fallback"] == 1
        assert out["num_imports"] == 0

    def test_key_present_int_kept(self) -> None:
        """键存在且为 int → 原值保留（or 短路）。"""
        out = _probe_all_four(
            {
                "num_files": 3,
                "cyclomatic_complexity": 17,
                "num_imports": 5,
            }
        )
        assert out["num_files"] == 3
        assert out["cc_primary"] == 17
        assert out["cc_fallback"] == 17
        assert out["num_imports"] == 5

    def test_ult_like_metadata_does_not_raise(self) -> None:
        """模拟 ULT_Lite 加载器产出的 metadata（cyclomatic_complexity 显式
        None，无 num_files / num_imports 键）—— 全链路 int() 不抛。"""
        ult_like_md = {
            "source": "ult",
            "function_name": "fn",
            "cyclomatic_complexity": None,  # 官方 ULT_Lite 无该字段 → 加载器写 None
            "test_cases": "import fn\n\ndef test_1():\n    assert fn() == 1\n",
            "fixed": "def fn():\n    return 1\n",
            "gold_tests_raw": "assert fn() == 1",
            "no_gold_tests": False,
            "mutation_primary_metric": True,
            "suggested_function": "fn",
            "is_cross_file": False,
        }
        # 不抛异常即通过（修复前 int(None) 在此链路崩溃）
        out = _probe_all_four(ult_like_md)
        assert out["cc_primary"] == 1
        assert out["num_files"] == 1


class TestRunBenchmarkSourceGuards:
    """源码级守卫：run_benchmark.py 含 4 处 `or default` 兜底，且不再残留
    旧的 ``int(task.metadata.get("cyclomatic_complexity", 1))`` 形态。

    防未来重构回退（回归测试锁死"修复已落地且未被改回"）。
    """

    def _source(self) -> str:
        """读取 experiments/run_benchmark.py 源码（不 import，避免
        run_benchmark 顶层副作用 / 依赖 LLM 客户端初始化）。"""
        here = pathlib.Path(__file__).resolve()
        repo_root = here.parents[1]
        return (repo_root / "experiments" / "run_benchmark.py").read_text(encoding="utf-8")

    def test_no_bare_int_metadata_get_cyclomatic_default(self) -> None:
        """残留旧形态 `int(task.metadata.get("cyclomatic_complexity", 1))`
        即崩溃形态，必须 0 命中。"""
        src = self._source()
        assert 'int(task.metadata.get("cyclomatic_complexity", 1))' not in src
        assert 'int(task.metadata.get("num_files", 1))' not in src
        assert 'int(task.metadata.get("num_imports", 0))' not in src

    def test_four_or_fallbacks_present(self) -> None:
        """4 处 `or default` 兜底必须在位（num_files×1 / cyclomatic×2 /
        num_imports×1）。"""
        src = self._source()
        assert 'int(task.metadata.get("num_files") or 1)' in src
        assert src.count('int(task.metadata.get("cyclomatic_complexity") or 1)') == 2
        assert 'int(task.metadata.get("num_imports") or 0)' in src
