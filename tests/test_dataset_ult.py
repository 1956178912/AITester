"""ULT（UnLeakedTestbench）基准加载器行为锁（W4b，2026-10-10；2026-10-12 官方仓库一手核验勘误）。

锁定四组行为：
1. manifest 解析（旧 JSONL manifest 兼容 + 官方 JSON 数组格式 + 官方字段名
   func_name/code/tests/test_list 归一化）；
2. task_id 末段中性化（非标识符函数名回退 AST 首个顶层函数）；
3. 官方测试材料记录（tests/test_list 非空 → test_code + gold_tests +
   no_gold_tests=False；缺失/空 → 恒空 + no_gold_tests=True，2026-10-12 勘误）；
4. 工厂注册（load_dataset("ult") / "unleaked_testbench" 别名 +
   subset="lite" → ULT_Lite.jsonl 子集）。
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


def _write_json_array(tmp_path: Path, rows: list[dict]) -> str:
    """官方 ULT.jsonl / ULT_Lite.jsonl 格式：文件名为 .jsonl 但内容为 JSON 数组。"""
    path = tmp_path / "ULT.jsonl"
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
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
        # 无官方测试材料 → 恒空（"诚实不可测"口径）
        assert task.test_code == ""
        assert task.total_test_count == 0
        assert task.metadata["source"] == "ult"
        assert task.metadata["no_gold_tests"] is True
        assert task.metadata["gold_tests"] == []
        assert task.metadata["mutation_primary_metric"] is True
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

    # ── 2026-10-12 官方仓库一手核验：新增行为锁 ──────────────────────────────

    def test_official_json_array_format(self, tmp_path: pytest.TempPathFactory) -> None:
        """官方 ULT.jsonl 为 JSON 数组（非逐行 JSONL），且使用官方字段名
        func_name/code/tests——加载器直接兼容，无需转换。"""
        _write_json_array(
            tmp_path,
            [
                {
                    "func_name": "toTextType",
                    "code": "def toTextType(x):\n    return str(x)\n",
                    "prompt": "Render a type as text.",
                    "task_id": "1",
                    "tests": ["def test_0():\n    assert toTextType(1) == '1'\n"],
                    "cyclomatic_complexity": 3,
                }
            ],
        )
        ds = load_dataset("ult", data_dir=str(tmp_path / "ULT.jsonl"))
        assert ds.size == 1
        task = ds.tasks[0]
        assert task.task_id == "ult__toTextType"
        assert task.instance_code == "def toTextType(x):\n    return str(x)\n"
        assert task.test_code == "def test_0():\n    assert toTextType(1) == '1'\n"
        assert task.total_test_count == 1
        assert task.metadata["no_gold_tests"] is False
        assert task.metadata["gold_tests"] == ["def test_0():\n    assert toTextType(1) == '1'\n"]
        assert task.metadata["cyclomatic_complexity"] == 3
        assert "任务：Render a type as text." in task.problem_statement

    def test_official_tests_as_stringified_json(self, tmp_path: pytest.TempPathFactory) -> None:
        """tests 字段为字符串化 JSON 数组时（部分官方记录形态），归一化为 list[str]。"""
        tests_str = json.dumps(["def test_a():\n    assert True\n"])
        _write_json_array(
            tmp_path,
            [
                {
                    "func_name": "f",
                    "code": "def f():\n    return 1\n",
                    "tests": tests_str,
                }
            ],
        )
        ds = load_dataset("ult", data_dir=str(tmp_path / "ULT.jsonl"))
        assert ds.size == 1
        assert ds.tasks[0].metadata["gold_tests"] == ["def test_a():\n    assert True\n"]

    def test_ult_lite_test_list_field(self, tmp_path: pytest.TempPathFactory) -> None:
        """ULT_Lite.jsonl 使用 test_list 字段（list[str] 断言片段）——归一化为
        官方测试材料，no_gold_tests=False。

        2026-10-12 M1 归一化：test_code 包装为 pytest 函数（import + test_<i>），
        _m1_metrics 可直接判分；原始断言保留在 gold_tests_raw；fixed = 被测
        函数全文（ULT 无缺陷基线）。"""
        _write_json_array(
            tmp_path,
            [
                {
                    "func_name": "is_degree_in_degree_range",
                    "code": "def is_degree_in_degree_range(a, b, c):\n    return True\n",
                    "prompt": "degree check.",
                    "task_id": "10",
                    "test_list": ["assert is_degree_in_degree_range(180, 360, 180) == True"],
                }
            ],
        )
        ds = load_dataset("ult", data_dir=str(tmp_path / "ULT.jsonl"))
        assert ds.size == 1
        task = ds.tasks[0]
        assert task.metadata["no_gold_tests"] is False
        assert task.metadata["gold_tests"] == ["assert is_degree_in_degree_range(180, 360, 180) == True"]
        assert task.total_test_count == 1
        # M1 归一化：test_code 包装为 pytest 函数（from 导入 + test_<i>）
        assert "from is_degree_in_degree_range import is_degree_in_degree_range" in task.test_code
        assert "def test_1" in task.test_code
        # 原始断言保留
        assert task.metadata["gold_tests_raw"] == "assert is_degree_in_degree_range(180, 360, 180) == True"
        # M1 判分材料：test_cases 与 test_code 一致（可判分）
        assert task.metadata["test_cases"] == task.test_code
        # fixed = 被测函数全文（ULT 无缺陷基线）
        assert task.metadata["fixed"] == "def is_degree_in_degree_range(a, b, c):\n    return True\n"

    def test_empty_tests_kept_no_gold(self, tmp_path: pytest.TempPathFactory) -> None:
        """tests 为空 list 时保持"诚实不可测"口径（no_gold_tests=True）。"""
        _write_json_array(
            tmp_path,
            [{"func_name": "f", "code": "def f():\n    return 1\n", "tests": []}],
        )
        ds = load_dataset("ult", data_dir=str(tmp_path / "ULT.jsonl"))
        assert ds.size == 1
        assert ds.tasks[0].metadata["no_gold_tests"] is True
        assert ds.tasks[0].test_code == ""

    def test_subset_lite_prefers_ult_lite_file(self, tmp_path: pytest.TempPathFactory) -> None:
        """subset='lite' 且 data_dir 为目录时优先加载 ULT_Lite.jsonl。"""
        lite_path = tmp_path / "ULT_Lite.jsonl"
        lite_path.write_text(
            json.dumps(
                [
                    {
                        "func_name": "lite_fn",
                        "code": "def lite_fn():\n    return 1\n",
                        "test_list": ["assert lite_fn() == 1"],
                    }
                ]
            ),
            encoding="utf-8",
        )
        # 目录里同时放旧 manifest（证明 subset 优先，而非 fallback）
        _write_manifest(tmp_path, [{"function_name": "full_fn", "source_code": "def full_fn():\n    return 2\n"}])
        ds = load_dataset("ult", subset="lite", data_dir=str(tmp_path))
        assert ds.size == 1
        assert ds.tasks[0].task_id == "ult__lite_fn"

    def test_full_array_with_many_records(self, tmp_path: pytest.TempPathFactory) -> None:
        """多条记录 JSON 数组（模拟官方 3909 条规模的小样本）——逐条任务化。"""
        rows = [
            {"func_name": f"fn_{i}", "code": f"def fn_{i}():\n    return {i}\n", "tests": [f"assert fn_{i}() == {i}"]}
            for i in range(10)
        ]
        _write_json_array(tmp_path, rows)
        ds = load_dataset("ult", data_dir=str(tmp_path / "ULT.jsonl"))
        assert ds.size == 10
        assert all(t.metadata["no_gold_tests"] is False for t in ds.tasks)
