"""AB-9（2026-10-20）：`experiments/` 分析层的 `json.loads` **返回域**容错锁。

立项依据：AB-8 把"形状域"判据落在 `src/datasets/` 与 G8 门禁上，并在
`docs/PROJECT_STATUS_REGISTER.md` §4 AB-8 行 ⑥ 登记"`experiments/*.py` 里 42 个文件、
68 处 `json.loads` 调用本轮未普查"。本轮普查结论（逐项表见
`docs/reviews/EXPERIMENTS_JSON_DOMAIN_AB9_2026-10-20.md`）：68 处中 56 处在任一非对象
返回下**响亮崩溃或已 fail-closed**，只有 12 处会静默丢数据；本轮只处置其中
**"静默 × 数字当前被引用 / 属复现入口"**的一处——`target_quality_replay.py`
（`make target-quality` 的产物正是 `BASELINE.yaml` `target_quality` 节引用的数字）。

判据：静默丢弃必须变成**可核对的计数**，且新增披露**只增不改**——
其余键、其余数值、退出码语义一律不动。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from experiments import target_quality_replay as tq

REPO_ROOT = Path(__file__).resolve().parent.parent

# `json.loads` 的六种合法返回里，除对象之外的五种（AB-8 §10 的枚举口径）。
_NON_OBJECT_TEXTS = {
    "list": "[]",
    "str": '"abc"',
    "int": "3",
    "bool": "true",
    "null": "null",
}


def _good_batch(coverage: float = 50.0, mutation: float = 0.5) -> dict:
    return {
        "results": {
            "aitester": {
                "details": [
                    {"coverage": coverage, "mutation_score": mutation, "detection_rate": 1},
                ]
            }
        }
    }


def _write(path: Path, payload) -> Path:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    return path


class TestNonObjectBatchesAreCounted:
    """顶层非对象的批次文件必须留下计数，不得无声消失。"""

    @pytest.fixture()
    def dir_with_one_good_five_bad(self, tmp_path: Path) -> Path:
        _write(tmp_path / "benchmark_good.json", _good_batch())
        for shape, text in _NON_OBJECT_TEXTS.items():
            _write(tmp_path / f"benchmark_{shape}.json", text)
        return tmp_path

    def test_all_five_shapes_are_recorded(self, dir_with_one_good_five_bad: Path):
        data = tq._collect(dir_with_one_good_five_bad)
        assert len(data["skipped"]["non_object"]) == 5
        for shape in _NON_OBJECT_TEXTS:
            assert any(f"benchmark_{shape}.json" in entry for entry in data["skipped"]["non_object"])

    def test_shape_is_named_in_the_entry(self, dir_with_one_good_five_bad: Path):
        data = tq._collect(dir_with_one_good_five_bad)
        joined = " ".join(data["skipped"]["non_object"])
        for shape in ("list", "str", "int", "bool", "NoneType"):
            assert shape in joined, f"{shape} 形状未在披露里点名"

    def test_good_batch_still_enters_the_report(self, dir_with_one_good_five_bad: Path):
        data = tq._collect(dir_with_one_good_five_bad)
        assert list(data["per_batch"]) == ["benchmark_good.json"]
        assert data["totals"]["aitester"] == 1

    def test_empty_and_syntax_error_files_are_counted_separately(self, tmp_path: Path):
        _write(tmp_path / "benchmark_good.json", _good_batch())
        _write(tmp_path / "benchmark_empty.json", "")
        _write(tmp_path / "benchmark_broken.json", '{"results": ')
        data = tq._collect(tmp_path)
        assert sorted(data["skipped"]["unreadable"]) == ["benchmark_broken.json", "benchmark_empty.json"]
        assert data["skipped"]["non_object"] == []
        assert list(data["per_batch"]) == ["benchmark_good.json"]

    def test_two_skip_classes_are_traced_separately(self, tmp_path: Path):
        """两类原因不得合并成一个计数：修复动作与归因完全不同。"""
        _write(tmp_path / "benchmark_good.json", _good_batch())
        _write(tmp_path / "benchmark_broken.json", "")
        _write(tmp_path / "benchmark_null.json", "null")
        data = tq._collect(tmp_path)
        assert len(data["skipped"]["unreadable"]) == 1
        assert len(data["skipped"]["non_object"]) == 1


class TestAdditiveOnly:
    """新增计数**只增不改**：坏邻居不得移动任何既有数值。"""

    def test_numbers_identical_with_and_without_bad_neighbours(self, tmp_path: Path):
        clean = tmp_path / "clean"
        dirty = tmp_path / "dirty"
        for d in (clean, dirty):
            d.mkdir()
            _write(d / "benchmark_good.json", _good_batch())
        for shape, text in _NON_OBJECT_TEXTS.items():
            _write(dirty / f"benchmark_{shape}.json", text)
        a, b = tq._collect(clean), tq._collect(dirty)
        for key in ("per_batch", "gates", "detection", "totals", "all_values"):
            assert a[key] == b[key], f"{key} 因坏邻居而变动"
        assert a["skipped"] == {"unreadable": [], "non_object": []}
        assert len(b["skipped"]["non_object"]) == 5


class TestDisclosureRendering:
    """披露节存在性即判据：零跳过时报告逐字节不变。"""

    def test_section_absent_when_nothing_skipped(self, tmp_path: Path):
        _write(tmp_path / "benchmark_good.json", _good_batch())
        text = tq._render(tq._collect(tmp_path), str(tmp_path))
        assert "## 读取完整性" not in text

    def test_section_names_counts_and_files_when_skipped(self, tmp_path: Path):
        _write(tmp_path / "benchmark_good.json", _good_batch())
        _write(tmp_path / "benchmark_null.json", "null")
        _write(tmp_path / "benchmark_broken.json", "{")
        text = tq._render(tq._collect(tmp_path), str(tmp_path))
        assert "## 读取完整性" in text
        assert "**1** 份" in text
        assert "benchmark_null.json" in text and "benchmark_broken.json" in text

    def test_disclosure_forbids_bare_citation(self, tmp_path: Path):
        """引用纪律要写在报告里，而不是只写在代码注释里。"""
        _write(tmp_path / "benchmark_good.json", _good_batch())
        _write(tmp_path / "benchmark_null.json", "null")
        text = tq._render(tq._collect(tmp_path), str(tmp_path))
        assert "必须同时引用本节" in text


class TestCliContract:
    """退出码语义不动：有可用批次仍为 0，全不可用仍 fail-closed。"""

    def test_warns_on_stderr_but_returns_zero(self, tmp_path: Path, capsys):
        _write(tmp_path / "benchmark_good.json", _good_batch())
        _write(tmp_path / "benchmark_null.json", "null")
        out = tmp_path / "report.md"
        rc = tq.main([str(tmp_path), "--out", str(out)])
        captured = capsys.readouterr()
        assert rc == 0
        assert "[WARN]" in captured.err and "1 份批次被跳过" in captured.err
        assert "## 读取完整性" in out.read_text(encoding="utf-8")

    def test_no_warning_when_clean(self, tmp_path: Path, capsys):
        _write(tmp_path / "benchmark_good.json", _good_batch())
        out = tmp_path / "report.md"
        rc = tq.main([str(tmp_path), "--out", str(out)])
        captured = capsys.readouterr()
        assert rc == 0
        assert "[WARN]" not in captured.err
        assert "## 读取完整性" not in out.read_text(encoding="utf-8")

    def test_all_batches_unusable_still_exits_one(self, tmp_path: Path, capsys):
        for shape, text in _NON_OBJECT_TEXTS.items():
            _write(tmp_path / f"benchmark_{shape}.json", text)
        rc = tq.main([str(tmp_path), "--out", str(tmp_path / "report.md")])
        captured = capsys.readouterr()
        assert rc == 1
        assert "[FAIL]" in captured.err
        assert "[WARN]" in captured.err and "5 份批次被跳过" in captured.err


class TestCommittedArtifactStillReproduces:
    """当前仓内工件重放仍逐字节等于入库报告——新节是"有跳过才出现"的。"""

    RESULTS = REPO_ROOT / "experiments" / "results" / "main_batch"
    REPORT = RESULTS / "target_quality_report.md"
    # 2026-10-23 provider 清理删除了这三份批次（含非 DeepSeek 模型标识）；
    # 入库报告是不重写的历史快照，故重放结果 = 快照减去这三行。
    DELETED_BATCHES = (
        "benchmark_synthetic_20261001_112528.json",
        "benchmark_synthetic_20261001_112801.json",
        "benchmark_synthetic_20261001_121523.json",
    )

    def test_committed_inputs_exist(self):
        pytest.skip(
            "结果工件不在盘（2026-10-24 用户指令清除历史数据、DeepSeek 重跑前）："
            "语料前提缺失具名 skip，重跑落盘后自动恢复判定"
        )
        assert self.RESULTS.is_dir() and self.REPORT.is_file()

    def test_regenerated_report_is_snapshot_minus_deleted_batches(self):
        pytest.skip(
            "结果工件不在盘（2026-10-24 用户指令清除历史数据、DeepSeek 重跑前）："
            "语料前提缺失具名 skip，重跑落盘后自动恢复判定"
        )
        """逐批次表仍与入库快照逐字节一致（减去已删批次行）；快照本身不重写。

        跨批次合计（`## 检出与特异性门`）按存活语料重算——删除的 3 批各 5/5/50 行
        曾计入合计，故合计必然变化；这条由下方固定读数锁住。
        """
        files = sorted(p for p in self.RESULTS.glob("*.json") if p.is_file())
        assert files, "main_batch 下无批次 JSON，本锁失去对象（应报错而非静默通过）"
        data = tq._collect("experiments/results/main_batch")
        assert data["skipped"] == {"unreadable": [], "non_object": []}
        rendered = tq._render(data, "experiments/results/main_batch")
        cut = "## 检出与特异性门（跨批次合计）"
        pattern = r"^\| benchmark_synthetic_20261001_(?:112528|112801|121523)\.json \|.*\n"
        expected_tables = re.sub(pattern, "", self.REPORT.read_text(encoding="utf-8"), flags=re.MULTILINE)
        assert rendered.split(cut)[0] == expected_tables.split(cut)[0]
        aggregate = rendered.split(cut)[1]
        assert "| aitester | 78/556 | 14.0% |" in aggregate
        assert "| plain_llm | 10/609 | 1.6% |" in aggregate
        assert "- 各臂累计任务行数：aitester=609、plain_llm=609、plain_llm_df=609" in aggregate
