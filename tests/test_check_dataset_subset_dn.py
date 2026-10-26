"""DN 轮：check-dataset 的 --subset 不得在「不支持 / 未生效」时假装已应用。

修复前实测（2026-10-26，真实 CLI 与真实数据目录）：

- ``check-dataset examples --subset lite`` → rc=0，输出「数据集 examples（子集: lite）
  共加载 3 个任务」——而 InMemoryDataset 的文档明确写着 subset「保留接口兼容，
  实际忽略；本数据集无子集概念」；
- ``check-dataset quixbugs --subset lite`` → rc=0，照常加载 50 个任务，同样宣称
  「子集: lite」；
- ULT 请求 ``--subset lite`` 但目录里只有通用 manifest（ULT_Lite.jsonl 缺失）时，
  ``_manifest_path`` 静默回退到通用 manifest，输出仍称「子集: lite」。

本文件锁定修复后的口径：
1. 数据集不支持子集 → 用法错误 rc=2，并列出真正支持 --subset 的数据集；
2. ULT 未知子集名 → 用法错误 rc=2，并列出可选子集；
3. ULT 请求的子集未生效（子集文件缺失 / 数据源为显式文件）→ rc=1 且披露
   「未生效」原因，不再输出冒充的「子集: X」；
4. 子集真正生效时 rc=0 且确实只加载子集文件；
5. ``load_dataset`` 的程序化契约不变（subset 仍被接受），能力表由公开 helper 暴露。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cli import app as cli_app
from src.datasets.dataset_loader import SubsetSupport, dataset_subset_support, load_dataset


def _invoke(*args: str):
    return CliRunner().invoke(cli_app.cli, ["check-dataset", *args])


def _write_manifest(directory: Path, rows: list[dict]) -> None:
    (directory / "ult_manifest.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8"
    )


def _write_subset_file(directory: Path, name: str, func_name: str) -> None:
    (directory / name).write_text(
        json.dumps([{"func_name": func_name, "code": f"def {func_name}():\n    return 1\n", "tests": []}]),
        encoding="utf-8",
    )


class TestUnsupportedDatasetRejectsSubset:
    """没有子集概念的数据集传 --subset 属于用法错误，不能静默忽略。"""

    @pytest.mark.parametrize("dataset", ["examples", "quixbugs", "in_memory"])
    def test_subset_on_dataset_without_subsets_is_usage_error(self, dataset: str) -> None:
        r = _invoke(dataset, "--subset", "lite")
        assert r.exit_code == 2
        assert "不支持子集" in r.output
        # 不能再打印冒充已应用的「子集: lite」
        assert "（子集: lite）" not in r.output

    def test_error_lists_datasets_that_do_support_subset(self) -> None:
        r = _invoke("examples", "--subset", "lite")
        support_lines = [line for line in r.output.splitlines() if "支持 --subset 的数据集" in line]
        assert support_lines, r.output
        listed = support_lines[0]
        assert "swe_bench" in listed
        assert "ult" in listed
        assert "examples" not in listed

    def test_lazy_synthetic_dataset_is_also_rejected(self) -> None:
        """synthetic 走懒加载注册表，能力查询不能漏掉这条路径。"""
        r = _invoke("synthetic", "--subset", "lite")
        assert r.exit_code == 2
        assert "不支持子集" in r.output


class TestUltSubsetHonesty:
    """ULT 支持子集，但未知子集名 / 子集未生效都必须显式报出。"""

    def test_unknown_subset_name_is_usage_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_manifest(tmp_path, [{"function_name": "full_fn", "source_code": "def full_fn():\n    return 2\n"}])
        monkeypatch.setenv("AITESTER_ULT_DATA", str(tmp_path))
        r = _invoke("ult", "--subset", "bogus")
        assert r.exit_code == 2
        assert "不支持子集" in r.output
        assert "lite" in r.output and "full" in r.output

    def test_missing_subset_file_is_disclosed_not_silently_substituted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_manifest(tmp_path, [{"function_name": "full_fn", "source_code": "def full_fn():\n    return 2\n"}])
        monkeypatch.setenv("AITESTER_ULT_DATA", str(tmp_path))
        r = _invoke("ult", "--subset", "lite")
        assert r.exit_code == 1
        assert "未生效" in r.output
        assert "ULT_Lite.jsonl" in r.output
        assert "（子集: lite）" not in r.output

    def test_explicit_file_datasource_conflict_is_disclosed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        file_path = tmp_path / "ULT.jsonl"
        file_path.write_text(
            json.dumps([{"func_name": "fn", "code": "def fn():\n    return 1\n", "tests": []}]),
            encoding="utf-8",
        )
        monkeypatch.setenv("AITESTER_ULT_DATA", str(file_path))
        r = _invoke("ult", "--subset", "lite")
        assert r.exit_code == 1
        assert "未生效" in r.output
        assert "显式文件" in r.output

    def test_honored_subset_still_passes_and_loads_only_that_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_manifest(tmp_path, [{"function_name": "full_fn", "source_code": "def full_fn():\n    return 2\n"}])
        _write_subset_file(tmp_path, "ULT_Lite.jsonl", "lite_fn")
        monkeypatch.setenv("AITESTER_ULT_DATA", str(tmp_path))
        r = _invoke("ult", "--subset", "lite", "--limit", "1")
        assert r.exit_code == 0
        assert "（子集: lite）" in r.output
        assert "ult__lite_fn" in r.output
        assert "ult__full_fn" not in r.output

    def test_loader_records_fallback_reason_for_programmatic_consumers(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, [{"function_name": "full_fn", "source_code": "def full_fn():\n    return 2\n"}])
        ds = load_dataset("ult", subset="lite", data_dir=str(tmp_path))
        assert ds.size == 1  # 回退行为本身保留（程序化调用方契约不变）
        assert ds.subset_fallback_reason is not None
        assert "ULT_Lite.jsonl" in ds.subset_fallback_reason


class TestSubsetCapabilityTable:
    """能力表是唯一事实源：CLI 校验与提示名单都从这里派生。"""

    def test_unsupported_datasets(self) -> None:
        assert dataset_subset_support("examples") == SubsetSupport(False, None)
        assert dataset_subset_support("in_memory") == SubsetSupport(False, None)
        assert dataset_subset_support("SYNTHETIC") == SubsetSupport(False, None)
        assert dataset_subset_support("d4j_py") == SubsetSupport(False, None)

    def test_swe_bench_accepts_any_subset_name(self) -> None:
        # 任意名称都映射为 swe_bench_<subset>_instances.jsonl；文件缺失由加载结果披露
        assert dataset_subset_support("swe-bench") == SubsetSupport(True, None)

    def test_ult_enumerates_official_subsets(self) -> None:
        assert dataset_subset_support("unleaked_testbench") == SubsetSupport(True, frozenset({"lite", "full"}))

    def test_programmatic_load_keeps_accepting_subset(self) -> None:
        ds = load_dataset("in_memory", subset="mini")
        assert ds.size > 0
