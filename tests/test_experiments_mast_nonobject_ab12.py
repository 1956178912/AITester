"""AB-12c 回归锁：站点 c 的"可解析但不是对象"行不得充进有效分母（2026-10-20）。

AB-9 普查表（`docs/reviews/EXPERIMENTS_JSON_DOMAIN_AB9_2026-10-20.md` §2，行 44）对
`experiments/mast_trace_analysis.py:73` 的登记原文是"非对象行被 `isinstance` 滤掉，
但整文件全是坏行时仍计入 `files`——分母口径与 AB-5 缺主键行同形"；AB-11 处置了同一站点
更严重的另一半（损坏整份作废无痕 + 归臂 unknown），并在 §6③ 明确本机制**未处置、继续登记**。
本轮处置它：

- `parse_trace_file` 原先对可解析非对象行**既不计数也不标损坏**——一个逐行都是数组或字符串
  的 trace 文件，读起来与"真的没有任何事件"逐字同形；
- `analyze_traces` 于是把这种文件计入 `stats["files"]`（命中率分母），把该臂命中率摊薄；
- 报告只会说"有效文件数 N"，读者无从知道 N 里有几份其实一行对象记录都没有。

处置口径（同 AB-9/AB-10/AB-11/AB-12b）：**披露只在真的发生时写入**——非对象行 0 实例时
报告逐字节不变（真路径由 `TestRealPathInvariants` 执行，不靠措辞承诺）；同时把两类通道
分开：坏行走 `damage`，形状不合走 `non_object_records`，**整份形状不合**不得冒充"零事件有效文件"。

全仓实测（`docs/reviews/SITE_C_MAST_NONOBJECT_AB12C_2026-10-20.md` §1）：138 个 `traces*` 目录、
8539 个 `*.trace.jsonl`、125270 行非空行里非对象行 **0 个**——`TestRepoWideCensus` 把这条
读数和"扫描器确实扫到了东西"一起锁住（漏扫的探针曾经报 783 个文件，见 §1 的口径修正）。

判据 = **删掉对应守卫必然转红**（变异验证逐处打印变红用例名，sha256 断言字节还原）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from experiments.mast_trace_analysis import analyze_traces, parse_trace_file
from experiments.mast_trace_analysis import render_markdown as render_mast_md
from tests._corpus_guard import require_full_corpus

_ROOT = Path(__file__).resolve().parents[1]
_MAIN_TRACES = _ROOT / "experiments/results/main_batch/traces"
_MAST_REPORT = _ROOT / "experiments/results/main_batch/mast_distribution_report.md"
_MAST_SUMS = _ROOT / "experiments/results/main_batch/SHA256SUMS"
# AB-11 普查里含坏行的 5 个入库目录（本轮用来证明"形状通道"没把损坏通道挤掉）
_DAMAGED_DIRS = (
    "experiments/results/cross_file_ab_level3/cross_file_off/traces",
    "experiments/results/emse_ult_specir_probe_20261014/traces",
    "experiments/results/rag_lvl25h_n40_g8batch/traces",
    "experiments/results/spec_ab_scale87_20261012/ult_lite46_off/traces",
    "experiments/results/spec_ab_scale87_20261012/ult_lite46_replace/traces",
)
_NON_OBJECT_SCALARS = ('["a", "b"]', '"just a string"', "42", "3.5", "true", "null")


def _require(path: Path) -> Path:
    """入库工件必须在场——缺席是环境事实，用 fail 说明"本锁未执行"，不用 skip 蒙数。"""
    if not path.exists():
        pytest.fail(f"入库工件缺失，本锁未执行：{path}")
    return path


def _start(arm: str) -> str:
    return json.dumps({"event": "task_start", "meta": {"baseline": arm, "dataset_task_id": "t1"}})


def _node(cat: str = "logic_error") -> str:
    return json.dumps({"event": "node", "node": "debugger", "task": "t1", "output": {"error_category": cat}})


def _trace(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


# ─── 1. parse_trace_file：非对象行有自己的读数，不再无痕消失 ─────────────────────
class TestParseNonObjectLines:
    @pytest.mark.parametrize("line", _NON_OBJECT_SCALARS)
    def test_each_non_object_shape_is_counted_not_dropped(self, tmp_path: Path, line: str) -> None:
        p = _trace(tmp_path / "a_aitester_1.trace.jsonl", [line])
        parsed = parse_trace_file(p)
        assert parsed["records"] == []
        assert parsed["non_object_records"] == 1
        assert parsed["non_object_shapes"] == {type(json.loads(line)).__name__: 1}

    def test_mixed_file_keeps_objects_and_counts_the_rest(self, tmp_path: Path) -> None:
        p = _trace(
            tmp_path / "a_aitester_1.trace.jsonl",
            [_start("aitester"), '["x"]', _node(), '"tail"', "7"],
        )
        parsed = parse_trace_file(p)
        assert len(parsed["records"]) == 2, "对象记录一个都不能少"
        assert parsed["non_object_records"] == 3
        assert parsed["non_object_only"] is False, "有对象记录就不是形状不合独占"

    def test_all_non_object_file_is_flagged_as_shape_only(self, tmp_path: Path) -> None:
        p = _trace(tmp_path / "a_aitester_1.trace.jsonl", list(_NON_OBJECT_SCALARS))
        parsed = parse_trace_file(p)
        assert parsed["non_object_only"] is True
        assert parsed["damaged"] is False, "形状不合不是坏行，两个通道不得合并"
        assert parsed["damage"] is None

    def test_genuinely_empty_file_is_not_shape_only(self, tmp_path: Path) -> None:
        """ "能读、无事件"仍是零事件有效读数——本轮只把形状不合挪出分母，不许顺手缩它。"""
        for name, lines in (("e1_aitester_1.trace.jsonl", []), ("e2_aitester_2.trace.jsonl", ["", "  "])):
            parsed = parse_trace_file(_trace(tmp_path / name, lines))
            assert parsed["records"] == [] and parsed["non_object_records"] == 0
            assert parsed["non_object_only"] is False

    def test_damage_channel_still_wins_when_both_are_present(self, tmp_path: Path) -> None:
        """整份都是非对象行、又撞到坏行：只算损坏，不重复算形状不合——两条通道各记各的数。"""
        _trace(tmp_path / "a_aitester_1.trace.jsonl", ['["x"]', "{broken"])
        parsed = parse_trace_file(tmp_path / "a_aitester_1.trace.jsonl")
        assert parsed["damaged"] is True and parsed["damage"] == "JSONDecodeError"
        assert parsed["non_object_records"] == 1, "坏行前的非对象行也要计数，不能随整份作废蒸发"
        assert parsed["non_object_only"] is False, "损坏文件走损坏通道，不重复算形状不合"
        assert parsed["records_before_damage"] == 0 and parsed["records"] == []
        result = analyze_traces(tmp_path)
        assert result["damaged_files"] == 1 and result["non_object_only_files"] == 0
        assert result["non_object_lines"] == 1, "同一份文件的两条通道读数都要留下"

    def test_clean_file_reports_zero_non_object(self, tmp_path: Path) -> None:
        parsed = parse_trace_file(_trace(tmp_path / "a_aitester_1.trace.jsonl", [_start("aitester"), _node()]))
        assert parsed["non_object_records"] == 0 and parsed["non_object_shapes"] == {}
        assert parsed["non_object_only"] is False and parsed["damaged"] is False


# ─── 2. analyze_traces：分母、归臂与点名 ────────────────────────────────────────
class TestDenominatorAndAttribution:
    def test_shape_only_file_is_not_counted_as_valid_file(self, tmp_path: Path) -> None:
        _trace(tmp_path / "a1_aitester_1.trace.jsonl", [_start("aitester"), _node()])
        _trace(tmp_path / "a2_aitester_2.trace.jsonl", ['["x"]', '"y"'])
        result = analyze_traces(tmp_path)
        arm = result["arms"]["aitester"]
        assert arm["files"] == 1, "形状不合的文件不得充进命中率分母"
        assert arm["non_object_only"] == 1
        assert result["non_object_only_files"] == 1
        assert result["non_object_lines"] == 2

    def test_hit_rate_denominator_is_the_shrunk_one(self, tmp_path: Path) -> None:
        _trace(tmp_path / "a1_aitester_1.trace.jsonl", [_start("aitester"), _node()])
        _trace(tmp_path / "a2_aitester_2.trace.jsonl", ["null"])
        _trace(tmp_path / "a3_aitester_3.trace.jsonl", [_start("aitester")])
        result = analyze_traces(tmp_path)
        arm = result["arms"]["aitester"]
        assert arm["files"] == 2 and arm["non_object_only"] == 1
        assert sum(arm["category_files"].values()) == 1, "命中面只来自两份有效文件"

    def test_denominator_accounting_balances(self, tmp_path: Path) -> None:
        _trace(tmp_path / "a1_aitester_1.trace.jsonl", [_start("aitester"), _node()])
        _trace(tmp_path / "a2_aitester_2.trace.jsonl", ["42"])
        _trace(tmp_path / "a3_aitester_3.trace.jsonl", [])
        _trace(tmp_path / "a4_aitester_4.trace.jsonl", [_start("aitester"), "{broken"])
        _trace(tmp_path / "b1_plain_llm_5.trace.jsonl", ['["z"]', "9"])
        result = analyze_traces(tmp_path)
        files = sum(v["files"] for v in result["arms"].values())
        damaged = sum(v["damaged"] for v in result["arms"].values())
        shape = sum(v["non_object_only"] for v in result["arms"].values())
        assert files + damaged + shape == result["total_files"] == 5, "三份账必须相加等于扫描到的文件数"
        assert (files, damaged, shape) == (2, 1, 2)

    def test_shape_only_file_is_attributed_to_its_arm_not_unknown(self, tmp_path: Path) -> None:
        _trace(tmp_path / "q1_plain_llm_df_1.trace.jsonl", ['["x"]'])
        result = analyze_traces(tmp_path)
        assert "unknown" not in result["arms"], "文件名可归臂时形状不合文件也不得整份落 unknown"
        assert result["arms"]["plain_llm_df"]["non_object_only"] == 1

    def test_unattributable_shape_only_file_goes_to_unknown(self, tmp_path: Path) -> None:
        _trace(tmp_path / "orphan_task.trace.jsonl", ['["x"]'])
        result = analyze_traces(tmp_path)
        assert result["arms"]["unknown"]["non_object_only"] == 1
        assert result["arms"]["unknown"]["files"] == 0

    def test_mixed_valid_file_stays_in_denominator_and_is_named(self, tmp_path: Path) -> None:
        _trace(tmp_path / "a1_aitester_1.trace.jsonl", [_start("aitester"), _node(), '"dropped"'])
        result = analyze_traces(tmp_path)
        assert result["arms"]["aitester"]["files"] == 1
        assert result["files_with_non_object_lines"] == 1
        assert result["non_object_only_files"] == 0
        assert result["non_object_files"] == ["a1_aitester_1.trace.jsonl"]

    def test_no_absence_no_names(self, tmp_path: Path) -> None:
        _trace(tmp_path / "a1_aitester_1.trace.jsonl", [_start("aitester"), _node()])
        result = analyze_traces(tmp_path)
        assert result["non_object_files"] == [] and result["non_object_shapes"] == {}
        assert result["non_object_lines"] == 0 and result["non_object_only_files"] == 0

    def test_shapes_aggregate_across_files(self, tmp_path: Path) -> None:
        _trace(tmp_path / "a1_aitester_1.trace.jsonl", ['["x"]', '["y"]'])
        _trace(tmp_path / "a2_aitester_2.trace.jsonl", ['"s"', "3"])
        result = analyze_traces(tmp_path)
        assert result["non_object_shapes"] == {"list": 2, "str": 1, "int": 1}
        assert result["non_object_lines"] == 4


# ─── 3. render_markdown：披露只在发生时出现，措辞说清分母 ─────────────────────────
class TestRendering:
    def _render(self, tmp_path: Path, lines_by_arm: dict[str, list[str]]) -> str:
        for i, (arm, lines) in enumerate(lines_by_arm.items()):
            _trace(tmp_path / f"a{i}_{arm}_{i}.trace.jsonl", lines)
        return "\n".join(render_mast_md(analyze_traces(tmp_path), tmp_path))

    def test_no_disclosure_when_no_non_object_lines(self, tmp_path: Path) -> None:
        text = self._render(tmp_path, {"aitester": [_start("aitester"), _node()]})
        assert "非对象行留痕" not in text, "0 实例时不得凭空加披露行（入库报告零变化）"
        assert "有效文件数：1（损坏 0）" in text, "臂头行措辞在无新读数时必须与改前逐字相同"

    def test_disclosure_names_counts_and_denominator_rule(self, tmp_path: Path) -> None:
        text = self._render(tmp_path, {"aitester": ['["x"]', '"y"'], "plain_llm": [_start("plain_llm"), _node()]})
        assert "非对象行留痕：2 行可解析但不是对象" in text
        assert "list 1 行、str 1 行" in text
        assert "不计入下面的有效文件数" in text
        assert "非对象行独占 1 份不计入分母" in text
        assert "有效文件数：1（损坏 0）" in text, "干净臂的臂头行不得被改写成两样"

    def test_disclosure_says_shape_is_not_damage(self, tmp_path: Path) -> None:
        text = self._render(tmp_path, {"aitester": ["null"]})
        assert "非对象行不是坏行" in text, "两条通道混同会让读者把形状问题读成语法问题"


# ─── 4. 真路径与全仓读数 ────────────────────────────────────────────────────────
class TestRealPathInvariants:
    def test_main_batch_traces_have_zero_non_object_instances(self) -> None:
        _require(_MAIN_TRACES)
        result = analyze_traces(_MAIN_TRACES)
        assert result["total_files"] == len(list(_MAIN_TRACES.glob("*.trace.jsonl")))
        assert result["non_object_lines"] == 0
        assert result["non_object_only_files"] == 0 and result["files_with_non_object_lines"] == 0
        assert sum(v["non_object_only"] for v in result["arms"].values()) == 0
        assert "非对象行留痕" not in "\n".join(render_mast_md(result, _MAIN_TRACES))

    def test_main_batch_denominator_accounting_balances(self) -> None:
        """入库目录上三份账也要平——非对象桶若被误接进 files，这条会先红。"""
        _require(_MAIN_TRACES)
        result = analyze_traces(_MAIN_TRACES)
        files = sum(v["files"] for v in result["arms"].values())
        damaged = sum(v["damaged"] for v in result["arms"].values())
        shape = sum(v["non_object_only"] for v in result["arms"].values())
        assert files + damaged + shape == result["total_files"]
        assert damaged == 0

    def test_committed_report_hash_still_matches_its_sums_entry(self) -> None:
        """入库报告受 SHA256SUMS 保护：本轮不重写它——逐位比对才叫锁。"""
        text = _require(_MAST_REPORT).read_text(encoding="utf-8")
        entry = {
            line.split()[1]: line.split()[0]
            for line in _require(_MAST_SUMS).read_text(encoding="utf-8").splitlines()
            if len(line.split()) == 2
        }
        assert "mast_distribution_report.md" in entry, "报告不在清单里 ⇒ 本锁失效"
        assert hashlib.sha256(_MAST_REPORT.read_bytes()).hexdigest() == entry["mast_distribution_report.md"]
        assert "非对象行留痕" not in text, "0 实例的披露行不得出现在入库快照里"
        assert "损坏留痕" not in text, "main_batch 实跑损坏 0 个，入库快照也不该有该行"

    @pytest.mark.parametrize("rel", sorted(_DAMAGED_DIRS))
    def test_damaged_dirs_keep_damage_channel_after_shape_channel(self, rel: str) -> None:
        d = _require(_ROOT / rel)
        result = analyze_traces(d)
        assert result["damaged_files"] == 1
        assert result["non_object_lines"] == 0 and result["non_object_only_files"] == 0
        files = sum(v["files"] for v in result["arms"].values())
        shape = sum(v["non_object_only"] for v in result["arms"].values())
        assert files + result["damaged_files"] + shape == result["total_files"]

    def test_committed_mast_report_is_untouched_and_carries_no_new_section(self) -> None:
        """入库报告受 SHA256SUMS 保护：本轮没有重写它，也不得含本轮才有的披露行。"""
        text = _require(_MAST_REPORT).read_text(encoding="utf-8")
        assert "非对象行留痕" not in text
        assert "损坏留痕" not in text, "main_batch 实跑损坏 0 个，入库快照也不该有该行"

    def test_repo_wide_non_object_census_is_zero_and_instrument_covered(self) -> None:
        """全仓普查读数 0 实例 + 覆盖面自证（漏扫的探针只报 783 个文件，见册 §1）。"""
        # BZ 轮：扫描面下界（138 个 traces* 目录 / 8539 个 trace 文件）以全归档
        # 校准——fresh clone 只有入库子集，前提不成立时显式 skip 并带实测读数
        # （tests/_corpus_guard.py），不把"没扫到"折成"扫过且干净"。
        require_full_corpus()
        trace_dirs = sorted({p for p in _ROOT.glob("experiments/results/**/traces*") if p.is_dir()})
        assert len(trace_dirs) >= 138, f"扫描面回落：{len(trace_dirs)} 个 traces* 目录"
        files = 0
        non_object_lines = 0
        unreadable = 0
        for d in trace_dirs:
            for f in sorted(d.glob("*.trace.jsonl")):
                files += 1
                try:
                    text = f.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    unreadable += 1
                    continue
                for line in text.splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        rec = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue  # 坏行走损坏通道，另有登记
                    if not isinstance(rec, dict):
                        non_object_lines += 1
        assert files >= 8539, f"扫描面回落：只扫到 {files} 个 trace 文件"
        assert unreadable == 0
        assert non_object_lines == 0, "非对象行从 0 实例变成非 0——本轮披露块会开始出字，须复核登记"
