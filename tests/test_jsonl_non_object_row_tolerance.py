"""AB-8（2026-10-20）：JSONL **非对象行**与**主键域**的容错回归锁（零 LLM，$0）。

AB-5 给数据集适配层补坏输入锁时立的判据是"坏行只作废那一行、留下痕迹、不得中止整批"。
本轮把同一族输入再推一步：`json.loads` 的合法返回域有六种（对象、数组、字符串、数字、
布尔、null），而 AB-5 只测了"解析失败"与"对象里缺主键"两种。实测五种合法非对象行后，
三处产品侧读取器和 G8 门禁的两处入口都在 `row.get` / `{**data}` 处抛 `AttributeError`——
**症状不是少几条任务，是整条数据通道不可用**。

同族第二类是主键：`{"instance_id": [1]}` 在写映射处抛 `TypeError`（不可哈希），而
`{"instance_id": 3}` **不抛**——键以 int 存进映射，下游按字符串主键查表永不命中，
日志还写着"已加载 N 条记录"。falsy 主键（AB-5 修的那类）是**静默丢弃**，非字符串
主键是**静默存活**，危害方向相反。本轮的处置是**标量主键按 `str()` 归一**（映射键域
与查表侧同源，合并得以生效），列表/字典主键按坏行跳过并留痕。

锁的口径沿用 AB 轮收紧后的判据：**删掉对应守卫必然转红**。每个畸形形状都成批测，
不挑"我想到的那一种"。文件全部由 `tmp_path` 现写，不读用户真实缓存或真实数据集。
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path

import pytest

from src.datasets.dataset_loader import SWEBenchDataset
from src.datasets.dataset_realbugs import BugsInPyDataset

LOGGER_NAME = "src.datasets.dataset_loader"

# json.loads 合法返回域中"不是 JSON 对象"的全部五种形状（null / 数组 / 串 / 整 / 布尔）。
NON_OBJECTS: tuple[str, ...] = ("[]", "null", '"abc"', "3", "true")

_GATE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "gates" / "check_swe_bench_pro_ready.py"


def _gate_module():
    """按文件路径加载门禁脚本（不用 sys.path.insert：那是进程级副作用，AA-8 判据管的就是它）。"""
    spec = importlib.util.spec_from_file_location("check_swe_bench_pro_ready_ab8", _GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _swe_row(index: int) -> str:
    return json.dumps(
        {
            "instance_id": f"org__repo-{index}",
            "repo": "org/repo",
            "problem_statement": f"fix bug {index}",
            "test_patch": "def test_f():\n    assert f() == 1\n",
        }
    )


def _enrich_row(instance_id: object, code: str = "def f():\n    return 2\n") -> str:
    return json.dumps({"instance_id": instance_id, "instance_code": code})


def _bugs_row(index: int) -> str:
    return json.dumps(
        {
            "project": "pytz",
            "bug_id": index,
            "file_path": f"bug{index}.py",
            "buggy_code": "def g():\n    return 1\n",
            "fixed_code": "def g():\n    return 2\n",
            "test_code": "def test_g():\n    assert g() == 2\n",
        }
    )


def _raw_key_row(raw_key: str, code: str = "x") -> str:
    """主键按 JSON 片段原样拼接：参数要能表达 `3` / `true` / `[1]` / `{"a": 1}`
    这些非字符串形状，走 `json.dumps` 就先把它们变成字符串了。"""
    return f'{{"instance_id": {raw_key}, "instance_code": "{code}"}}'


def _write(path: Path, lines: list[str]) -> str:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _records(caplog: pytest.LogCaptureFixture, needle: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if needle in r.getMessage()]


@pytest.mark.unit
class TestSweEnrichmentNonObjectRows:
    """补充文件侧：五种非对象行都必须只作废该行。"""

    @pytest.mark.parametrize("bad", NON_OBJECTS)
    def test_each_non_object_shape_degrades_instead_of_raising(self, tmp_path: Path, bad: str) -> None:
        path = _write(tmp_path / "enrich.jsonl", [bad])
        assert SWEBenchDataset._load_enrichment(path) == {}

    def test_non_object_rows_do_not_kill_the_good_ones(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "enrich.jsonl",
            [_enrich_row("a"), *NON_OBJECTS, _enrich_row("b")],
        )
        assert set(SWEBenchDataset._load_enrichment(path)) == {"a", "b"}

    def test_non_object_rows_leave_one_bounded_trace(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """五条坏行 → 恰好一条汇总 warning（与 AB-5 的缺主键类同口径，不逐行刷屏）。"""
        path = _write(tmp_path / "enrich.jsonl", list(NON_OBJECTS))
        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            SWEBenchDataset._load_enrichment(path)
        hits = _records(caplog, "不是 JSON 对象")
        assert len(hits) == 1, "汇总一条：逐行刷屏会淹没信号，静默丢弃则毫无痕迹"
        assert "5 行" in hits[0]


@pytest.mark.unit
class TestSweEnrichmentPrimaryKeyDomain:
    """主键侧：映射键域必须是 str，标量按 `str()` 归一、列表/字典按坏行跳过。"""

    @pytest.mark.parametrize("bad_key", ["[1]", '{"a": 1}'])
    def test_unhashable_primary_key_does_not_abort_the_file(self, tmp_path: Path, bad_key: str) -> None:
        path = _write(tmp_path / "enrich.jsonl", [_raw_key_row(bad_key)])
        assert SWEBenchDataset._load_enrichment(path) == {}

    @pytest.mark.parametrize("raw_key,expected", [("3", "3"), ("true", "True"), ("1.5", "1.5")])
    def test_scalar_primary_keys_are_normalized_into_the_mapping(
        self, tmp_path: Path, raw_key: str, expected: str
    ) -> None:
        """标量主键**合并而不是丢弃**：丢弃等于"补充文件配了但零生效"，
        而 `str(3) == "3"` 与主数据侧的查表口径同源，合并才是用户想要的结果。"""
        path = _write(tmp_path / "enrich.jsonl", [_raw_key_row(raw_key)])
        assert set(SWEBenchDataset._load_enrichment(path)) == {expected}

    def test_int_key_reaches_the_enrichment_lookup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """端到端：主文件与补充文件都写 int 主键时，补充字段必须真的生效。

        这是两侧口径必须一致的证明点——只在一侧 `str()` 会让映射键与查表键错位，
        日志写着"已加载 1 条记录"而合并结果为零。
        """
        import src.datasets.dataset_loader as dl

        enrich = _write(tmp_path / "enrich.jsonl", [_enrich_row(7, code="def f():\n    return 7\n")])
        _write(tmp_path / "swe_bench_x_instances.jsonl", ['{"instance_id": 7, "problem_statement": "issue 7"}'])
        monkeypatch.setattr(dl, "SWE_BENCH_ENRICHMENT", enrich)
        dataset = SWEBenchDataset(data_dir=str(tmp_path))
        dataset._load_raw_data()
        assert len(dataset._tasks) == 1
        assert dataset._tasks[0].task_id == "7"
        assert "return 7" in str(dataset._tasks[0].instance_code)

    @pytest.mark.parametrize("bad_key", ["[1]", '{"a": 1}'])
    def test_container_primary_keys_leave_a_trace(
        self, tmp_path: Path, bad_key: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = _write(tmp_path / "enrich.jsonl", [_raw_key_row(bad_key)])
        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            assert SWEBenchDataset._load_enrichment(path) == {}
        assert len(_records(caplog, "instance_id 是列表或字典")) == 1

    def test_three_bad_classes_are_traced_separately(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """三类坏行各自一条汇总，计数互不串味（同一句话里混两类就无法定位缺口）。"""
        path = _write(
            tmp_path / "enrich.jsonl",
            [
                "[]",
                "null",
                '{"instance_code": "no id"}',
                "{}",
                '{"instance_id": [3]}',
                '{"instance_id": {"a": 4}}',
                _enrich_row("ok"),
            ],
        )
        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            assert set(SWEBenchDataset._load_enrichment(path)) == {"ok"}
        assert len(_records(caplog, "2 行不是 JSON 对象")) == 1
        assert len(_records(caplog, "2 行缺少 instance_id")) == 1
        assert len(_records(caplog, "2 行的 instance_id 是列表或字典")) == 1


@pytest.mark.unit
class TestSweMainDataNonObjectRows:
    """主数据文件侧：此前一行非对象就中断**整批**加载（不是少一条任务）。"""

    @pytest.mark.parametrize("bad", NON_OBJECTS)
    def test_each_non_object_shape_does_not_abort_the_load(self, tmp_path: Path, bad: str) -> None:
        _write(tmp_path / "swe_bench_x_instances.jsonl", [bad])
        dataset = SWEBenchDataset(data_dir=str(tmp_path))
        dataset._load_raw_data()
        assert dataset._tasks == []

    def test_good_rows_interleaved_with_all_bad_shapes_survive(self, tmp_path: Path) -> None:
        _write(tmp_path / "swe_bench_x_instances.jsonl", [_swe_row(1), *NON_OBJECTS, _swe_row(2)])
        dataset = SWEBenchDataset(data_dir=str(tmp_path))
        dataset._load_raw_data()
        assert [t.task_id for t in dataset._tasks] == ["org__repo-1", "org__repo-2"]

    def test_non_scalar_instance_id_falls_back_to_the_line_id(self, tmp_path: Path) -> None:
        """主数据行的 instance_id 为 null / 列表 / 字典时用带行号的兜底 id。

        此前 `"__" in task_id` 直接 TypeError——注意崩溃点在 `_build_task_from_swe_row`
        内部，与本文件其余案例的"解析结果不是对象"是**两个**缺陷位置。
        """
        _write(
            tmp_path / "swe_bench_x_instances.jsonl",
            ['{"instance_id": null, "problem_statement": "a"}', '{"instance_id": [1], "problem_statement": "b"}'],
        )
        dataset = SWEBenchDataset(data_dir=str(tmp_path))
        dataset._load_raw_data()
        assert [t.task_id for t in dataset._tasks] == ["swe_1", "swe_2"]

    def test_each_bad_line_leaves_a_located_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """主数据文件按**逐行含行号**留痕：与本循环既有的解析失败分支同口径。

        补充文件用汇总、这里用逐行——差别是有意的：坏补充文件通常整份作废（一条
        足够定位文件），坏数据行需要在几百行里指认具体是哪一行。
        """
        path = _write(tmp_path / "swe_bench_x_instances.jsonl", ["[]", "null"])
        dataset = SWEBenchDataset(data_dir=str(tmp_path))
        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            dataset._load_raw_data()
        hits = _records(caplog, "记录不是 JSON 对象")
        assert len(hits) == 2
        assert any("第 1 行" in h for h in hits) and any("第 2 行" in h for h in hits)
        assert path in hits[0]


@pytest.mark.unit
class TestBugsInPyNonObjectRows:
    """BugsInPy 侧：非对象行计入既有 skipped，随加载完成的 info 一并报出。"""

    @pytest.mark.parametrize("bad", NON_OBJECTS)
    def test_each_non_object_shape_degrades_to_skipped(self, tmp_path: Path, bad: str) -> None:
        (tmp_path / "bugs_in_py_manifest.jsonl").write_text(bad + "\n", encoding="utf-8")
        dataset = BugsInPyDataset(data_dir=str(tmp_path))
        dataset._load_raw_data()
        assert dataset._tasks == []

    def test_good_rows_survive_and_bad_rows_are_counted(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        _write(tmp_path / "bugs_in_py_manifest.jsonl", [_bugs_row(1), *NON_OBJECTS, _bugs_row(2)])
        dataset = BugsInPyDataset(data_dir=str(tmp_path))
        with caplog.at_level(logging.WARNING, logger="src.datasets.dataset_realbugs"):
            dataset._load_raw_data()
        assert len(dataset._tasks) == 2, "非对象行只作废该行"
        assert len(_records(caplog, "不是 JSON 对象")) == len(NON_OBJECTS)

    def test_skipped_count_reaches_the_final_summary(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """坏行数必须进"跳过 N 行"汇总：只看任务数无法区分"数据本就少"与"被坏行吃掉"。"""
        _write(tmp_path / "bugs_in_py_manifest.jsonl", [_bugs_row(1), *NON_OBJECTS])
        dataset = BugsInPyDataset(data_dir=str(tmp_path))
        with caplog.at_level(logging.INFO, logger="src.datasets.dataset_realbugs"):
            dataset._load_raw_data()
        summary = _records(caplog, "BugsInPy 加载完成")
        assert len(summary) == 1
        assert f"跳过 {len(NON_OBJECTS)} 行" in summary[0]


@pytest.mark.unit
class TestGateEnrichmentStats:
    """门禁补充文件侧：四类坏行此前被整段 `except`/`continue` 静默吞掉。"""

    def test_stats_keys_are_a_fixed_vocabulary(self, tmp_path: Path) -> None:
        gate = _gate_module()
        path = _write(tmp_path / "enrich.jsonl", [_enrich_row("a")])
        _, stats = gate._load_enrichment_paths(path)
        assert set(stats) == {"exists", "loaded", "parse_error", "non_object", "missing_id", "bad_key"}

    @pytest.mark.parametrize("bad", NON_OBJECTS)
    def test_non_object_rows_are_frozen_as_unusable_not_crash(self, tmp_path: Path, bad: str) -> None:
        gate = _gate_module()
        path = _write(tmp_path / "enrich.jsonl", [bad])
        enriched, stats = gate._load_enrichment_paths(path)
        assert enriched == {}
        assert (stats["exists"], stats["loaded"], stats["non_object"]) == (1, 0, 1)

    def test_each_category_is_counted_separately(self, tmp_path: Path) -> None:
        gate = _gate_module()
        path = _write(
            tmp_path / "enrich.jsonl",
            ["{not json", "[]", '{"instance_code": "x"}', '{"instance_id": [3]}', _enrich_row("a")],
        )
        enriched, stats = gate._load_enrichment_paths(path)
        assert set(enriched) == {"a"}
        assert [stats[k] for k in ("parse_error", "non_object", "missing_id", "bad_key")] == [1, 1, 1, 1]
        assert stats["loaded"] == 1

    def test_missing_file_is_distinguishable_from_empty_and_from_all_bad(self, tmp_path: Path) -> None:
        """三种"零条"必须可分辨：门禁声明的阻塞语义要求能区分"没配"与"配了但全废"。"""
        gate = _gate_module()
        empty = _write(tmp_path / "empty.jsonl", [])
        all_bad = _write(tmp_path / "all_bad.jsonl", list(NON_OBJECTS))

        for not_configured in (None, ""):
            _, stats = gate._load_enrichment_paths(not_configured)
            assert stats["exists"] == 0, "未配置：连文件都没有"
        _, stats = gate._load_enrichment_paths(str(tmp_path / "definitely_absent.jsonl"))
        assert stats["exists"] == 0, "配了但路径不存在：与未配置同形，但 loaded 一律为零"
        _, stats = gate._load_enrichment_paths(empty)
        assert (stats["exists"], stats["loaded"]) == (1, 0) and not any(
            stats[k] for k in ("parse_error", "non_object", "missing_id", "bad_key")
        ), "空文件：存在但没有任何行"
        _, stats = gate._load_enrichment_paths(all_bad)
        assert (stats["exists"], stats["loaded"], stats["non_object"]) == (1, 0, 5), "全废：必须与空文件不同形"

    def test_report_carries_the_stats_without_rewriting_existing_keys(self, tmp_path: Path) -> None:
        """报告 dict 的既有键是下游契约（experiments/run_full_stack_swe_bench_pro.py）。"""
        gate = _gate_module()
        data = tmp_path / "d"
        data.mkdir()
        _write(data / "swe_bench_pro_instances.jsonl", [_swe_row(1)])
        report = gate.check_pro_ready(str(data), enrichment=_write(tmp_path / "e.jsonl", list(NON_OBJECTS)))
        assert report["enrichment_stats"]["non_object"] == len(NON_OBJECTS)
        assert report["enrichment_loaded"] is False, "五条坏行都没落到映射"
        for key in ("data_dir", "data_files", "total_tasks", "ready_tasks", "task_issues", "ready"):
            assert key in report


@pytest.mark.unit
class TestGateMainLoopFailClosed:
    """门禁主数据侧：崩溃恰好也返回码 1，所以"阻塞生效"是假象——报告根本没生成。"""

    @pytest.mark.parametrize("bad", NON_OBJECTS)
    def test_non_object_data_lines_do_not_become_ready(self, tmp_path: Path, bad: str) -> None:
        gate = _gate_module()
        _write(tmp_path / "swe_bench_pro_instances.jsonl", [bad])
        report = gate.check_pro_ready(str(tmp_path))
        assert report["total_tasks"] == 1
        assert report["ready"] is False, "非对象行是数据缺陷，不得因为「能解析」就判就绪"
        assert list(report["task_issues"]) == ["non_object_swe_bench_pro_instances.jsonl_line1"]

    def test_a_good_row_next_to_a_bad_one_still_blocks_the_batch(self, tmp_path: Path) -> None:
        gate = _gate_module()
        good = {
            "instance_id": "repo__repo-1",
            "problem_statement": "fix",
            "instance_code": "def f():\n    return 1\n",
            "test_code": "def test_f():\n    assert f()\n",
            "FAIL_TO_PASS": ["test_f"],
            "base_commit": "abc123",
        }
        _write(tmp_path / "swe_bench_pro_instances.jsonl", [json.dumps(good), "[]"])
        report = gate.check_pro_ready(str(tmp_path))
        assert (report["total_tasks"], report["ready_tasks"], report["ready"]) == (2, 1, False)

    def test_cli_text_names_the_drop_reason_not_just_unloaded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """用户可见面：旧文本把"不存在 / 空 / 全废"压成"未加载 / 不存在"一句。"""
        gate = _gate_module()
        data = tmp_path / "d"
        data.mkdir()
        _write(data / "swe_bench_pro_instances.jsonl", [_swe_row(1)])
        inert = _write(tmp_path / "e.jsonl", list(NON_OBJECTS))
        monkeypatch.setattr(
            sys, "argv", ["check_swe_bench_pro_ready.py", "--data-dir", str(data), "--enrichment", inert]
        )
        assert gate.main() == 1
        out = capsys.readouterr().out
        assert "零行落到映射" in out and "非 JSON 对象 5" in out, out
        assert "文件不存在" not in out, "路径存在时不得报成「文件不存在」"
