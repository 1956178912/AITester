"""ULT（UnLeakedTestbench）基准加载器行为锁（W4b，2026-10-10）。

锁定三组行为：
1. manifest JSONL 解析（正常任务 / 缺失字段 / 空 source_code 跳过）；
2. task_id 末段中性化（非标识符函数名回退 AST 首个顶层函数）；
3. 工厂注册（load_dataset("ult") / "unleaked_testbench" 别名 + 无 gold tests 语义）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.datasets.dataset_loader import load_dataset


def _write_manifest(tmp_path: Path, rows: list[dict]) -> str:
    path = tmp_path / "ult_manifest.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return str(path)


class TestULTLoader:
    def test_loads_valid_task(self, tmp_path: pytest.TempPathFactory) -> None:
        _write_manifest(
            tmp_path,  # type: ignore[arg-type]
            [
                {
                    "function_name": "resolve_path",
                    "source_code": "def resolve_path(a, b):\n    return a\n",
                    "cyclomatic_complexity": 14,
                }
            ],
        )
        ds = load_dataset("ult", data_dir=str(tmp_path))
        assert ds.size == 1
        task = ds.tasks[0]
        assert task.task_id == "ult__resolve_path"
        assert task.instance_code == "def resolve_path(a, b):\n    return a\n"
        assert task.test_code == ""  # ULT 官方不发布 ground-truth tests
        assert task.metadata["source"] == "ult"
        assert task.metadata["no_gold_tests"] is True
        assert task.metadata["cyclomatic_complexity"] == 14
        assert task.metadata["suggested_function"] == "resolve_path"

    def test_missing_manifest_returns_empty(self, tmp_path: pytest.TempPathFactory) -> None:
        ds = load_dataset("ult", data_dir=str(tmp_path))
        assert ds.size == 0

    def test_empty_source_code_skipped(self, tmp_path: pytest.TempPathFactory) -> None:
        _write_manifest(
            tmp_path,  # type: ignore[arg-type]
            [
                {"function_name": "good", "source_code": "def good():\n    return 1\n"},
                {"function_name": "empty", "source_code": ""},
                {"function_name": "missing", "source_code": None},
            ],
        )
        ds = load_dataset("ult", data_dir=str(tmp_path))
        assert ds.size == 1
        assert ds.tasks[0].task_id == "ult__good"

    def test_non_identifier_name_falls_back_to_ast(self, tmp_path: pytest.TempPathFactory) -> None:
        """函数名非标识符时回退到 AST 首个顶层函数名。"""
        _write_manifest(
            tmp_path,  # type: ignore[arg-type]
            [{"function_name": "123bad name!", "source_code": "def actual_fn(x):\n    return x\n"}],
        )
        ds = load_dataset("ult", data_dir=str(tmp_path))
        assert ds.size == 1
        assert ds.tasks[0].task_id == "ult__actual_fn"

    def test_alias_registration(self, tmp_path: pytest.TempPathFactory) -> None:
        _write_manifest(
            tmp_path,  # type: ignore[arg-type]
            [{"function_name": "f", "source_code": "def f():\n    return 1\n"}],
        )
        for name in ("ult", "unleaked_testbench"):
            ds = load_dataset(name, data_dir=str(tmp_path))
            assert ds.size == 1, name
            assert ds.tasks[0].metadata["source"] == "ult"

    def test_invalid_complexity_is_none(self, tmp_path: pytest.TempPathFactory) -> None:
        _write_manifest(
            tmp_path,  # type: ignore[arg-type]
            [{"function_name": "f", "source_code": "def f():\n    return 1\n", "cyclomatic_complexity": "high"}],
        )
        ds = load_dataset("ult", data_dir=str(tmp_path))
        assert ds.tasks[0].metadata["cyclomatic_complexity"] is None
