"""AB-12d 回归锁：共享 loader 的 `task_id` 折叠不得静默缩分母（2026-10-20）。

AB-11 §6⑤ 登记的缺口是："重复 `task_id` 缩分母已修"不可引用——折叠发生在**共享 loader**
`emse_df_spec_analysis.load_arm_rows`（`emse_docstring_anchor_analysis` 与
`emse_docstring_augment_analysis` 都复用它），AB-11 只在 augment 侧加了命名 WARN 与三数披露。
本轮处置 loader 本身：

- `out[tid] = ...` 让后出现的同 id 行覆盖前一行 ⇒ 返回字典可以比 `details` 行数少，
  而 41 缺陷程序口径、可判定子集、McNemar 配对全按这个字典算 ⇒ 分母静默缩水；
- `row.get("task_id", "")` 把"键缺席"与"空串"折成同一个 `""` 键，显式 `null` 落在 `None` 键，
  非字符串键各自成键，不可哈希键（list / dict）在旧写法下 `TypeError` 崩掉整条分析；
- `details` 里的非对象行在旧写法下同样 `AttributeError` 崩。

处置口径：**返回域与既有语义一个字不改**（后写仍覆盖先写、键仍按原样成键），只把折叠
变成命名 WARN——**只在真的发生时**打印，点名文件、臂、`details 行数 / 行摘要数`、被覆盖 id
与五种无主键形态的分开计数（五桶互斥，一行只进一个桶）。真批次实测 0 实例，覆盖面按桶记账：
glob 命中 246 份 `benchmark_*.json` → 242 份提供证据（320 个臂、10659 个 dict 行、被覆盖 0、
无主键 0、非对象行 0）+ 2 份空 `details` 例 + 2 份 `.mdo.json` 非臂形状 + 0 份读不动，故入库
读数一字不变——这条由 `TestRealPathInvariants` 连**分桶等式**（四桶之和 == glob 命中数）与覆盖面
下界一起执行，不靠措辞承诺。

判据 = **删掉对应守卫必然转红**（变异验证逐处打印变红用例名，sha256 断言字节还原）。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from experiments.emse_df_spec_analysis import MissingArtifactError, defect_program_ids, load_arm_rows
from tests._corpus_guard import require_full_corpus

_ROOT = Path(__file__).resolve().parents[1]
_BENCH_GLOB = "experiments/results/**/benchmark_*.json"
# AB-12d 前置普查（/tmp/ab12d_dup_probe.py + 本文件 _census）实测覆盖面；任何一项回落都要先撤销"0 实例"登记
_CENSUS_MIN_FILES = 246  # glob 命中总数
_CENSUS_MIN_JUDGED_FILES = 242  # 其中真正有 ≥1 行可核的文件数
_CENSUS_MIN_ARMS = 300
_CENSUS_MIN_ROWS = 10659
_OMIT = object()


def _row(tid: Any = _OMIT, detection: float = 1.0) -> dict[str, Any]:
    """`_OMIT` = 这行根本没有 task_id 键；显式传 "" / None / 7 / ["a"] 各是一种形态。"""
    out: dict[str, Any] = {"detection_rate": detection}
    if tid is not _OMIT:
        out["task_id"] = tid
    return out


def _batch(arm: str, rows: list[Any]) -> dict[str, Any]:
    return {"results": {arm: {"details": rows}}}


def _write(tmp_path: Path, payload: dict[str, Any], name: str = "b.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# ─── 1. 折叠：语义不变，但必须留痕 ─────────────────────────────────────────────
class TestDuplicateCollapseIsDisclosed:
    def test_last_write_wins_is_unchanged(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """本轮只加披露，不改哪一行存活——改存活会动既有读数，超出登记范围。"""
        p = _write(tmp_path, _batch("df", [_row("t1", 1.0), _row("t1", 0.0)]))
        rows = load_arm_rows(p)
        assert rows["t1"]["detection_rate"] == 0.0 and len(rows) == 1
        assert capsys.readouterr().err  # 存活语义与披露互不干扰

    def test_duplicate_names_file_arm_and_both_counts(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path, _batch("df", [_row("t1"), _row("t1"), _row("t2")]))
        rows = load_arm_rows(p, "df")
        err = capsys.readouterr().err
        assert len(rows) == 2
        assert "[WARN] b.json" in err
        assert "臂 'df' 行集折叠 details 行 3 → 行摘要 2" in err
        assert "被覆盖 task_id 1 个：'t1'" in err
        assert "不得读成'该臂只有 N 个任务'" in err

    def test_the_warned_number_is_the_denominator_consumer_sees(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = _write(tmp_path, _batch("df", [_row(f"t{i}") for i in range(5)] + [_row("t0")]))
        rows = load_arm_rows(p, "df")
        assert len(defect_program_ids(rows)) == 5, "41 口径按字典大小算，折叠就是缩分母"
        assert "details 行 6 → 行摘要 5" in capsys.readouterr().err

    def test_more_than_ten_collisions_are_capped_but_total_is_stated(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ids = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l"]
        p = _write(tmp_path, _batch("df", [x for tid in ids for x in (_row(tid), _row(tid))]))
        load_arm_rows(p, "df")
        err = capsys.readouterr().err
        assert "被覆盖 task_id 12 个" in err
        assert "'a'" in err and "'l'" not in err, "点名只列前 10 个，总数仍要说全"
        assert "只点名前 10 个" in err

    def test_no_duplicate_no_warning(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path, _batch("df", [_row("t1"), _row("t2"), _row("t3_test")]))
        rows = load_arm_rows(p, "df")
        assert len(rows) == 3
        assert capsys.readouterr().err == "", "无折叠时不得凭空出 WARN（入库读数一字不变）"

    def test_counts_are_machine_extractable(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """WARN 里"details 行 N → 行摘要 M"必须摘得出来，披露要可复核不是可读即可。"""
        p = _write(tmp_path, _batch("df", [_row("t1"), _row("t1"), _row("t2"), _row()]))
        rows = load_arm_rows(p, "df")
        m = re.search(r"details 行 (\d+) → 行摘要 (\d+)", capsys.readouterr().err)
        assert m and m.group(1) == "4" and m.group(2) == str(len(rows))


# ─── 2. 无主键行的形态各自留痕 ─────────────────────────────────────────────────
class TestKeylessRowShapes:
    @pytest.mark.parametrize(
        ("row", "bucket"),
        [
            (_row(), "key_absent"),
            (_row(""), "empty_string"),
            (_row(None), "value_null"),
            (_row(7), "not_string"),
            (_row(["a"]), "unhashable"),
        ],
    )
    def test_each_shape_gets_its_own_mechanism_name(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], row: dict[str, Any], bucket: str
    ) -> None:
        p = _write(tmp_path, _batch("df", [_row("t1"), row]))
        load_arm_rows(p, "df")
        err = capsys.readouterr().err
        assert f"无主键行 {bucket} 1" in err, err

    def test_the_five_buckets_partition_the_rows_so_counts_are_not_inflated(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """五种形态是**一次划分**：一行只进一个桶，`无主键行` 各桶之和 == 无主键行数。

        本轮前置写法把不可哈希键先记成 `not_string` 再记成 `unhashable`，5 行会报成 6 行——
        披露自身的计数虚增同样是"读错数"，与它想纠正的错读同属一类。
        """
        one_unhashable = _write(tmp_path, _batch("df", [_row("t1"), _row(["a"])]), name="one.json")
        load_arm_rows(one_unhashable, "df")
        err = capsys.readouterr().err
        assert "unhashable 1" in err and "not_string" not in err, f"不可哈希行被重复记账：{err}"

        all_shapes = _write(
            tmp_path, _batch("df", [_row(), _row(None), _row(""), _row(7), _row(["a"]), _row("t1")]), name="all.json"
        )
        load_arm_rows(all_shapes, "df")
        err = capsys.readouterr().err
        seg = re.search(r"无主键行 ([^）]+)", err)
        assert seg, err
        counts = {k: int(n) for k, n in re.findall(r"([a-z_]+) (\d+)", seg.group(1))}
        assert counts == {
            "key_absent": 1,
            "value_null": 1,
            "empty_string": 1,
            "not_string": 1,
            "unhashable": 1,
        }, counts
        assert sum(counts.values()) == 5, "一行不得进两个桶"

    def test_absent_key_and_empty_string_share_a_key_but_not_a_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ "键缺席"与"空串"在旧写法里折成同一个 `""` 键——键可以同形，机制不得混写。"""
        p = _write(tmp_path, _batch("df", [_row(), _row("", 0.0)]))
        rows = load_arm_rows(p, "df")
        err = capsys.readouterr().err
        assert list(rows) == [""] and rows[""]["detection_rate"] == 0.0, "键语义未改，仍是同一个空键"
        assert "key_absent 1、empty_string 1" in err, err
        assert "details 行 2 → 行摘要 1" in err

    def test_unhashable_id_is_counted_instead_of_crashing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = _write(tmp_path, _batch("df", [_row(["x"]), _row("t1")]))
        rows = load_arm_rows(p, "df")
        assert list(rows) == ["t1"], "不可哈希键进不了字典，但也不能崩掉整条分析"
        assert "unhashable 1" in capsys.readouterr().err

    def test_non_object_detail_row_is_counted_not_crash(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = _write(tmp_path, _batch("df", ["not-a-row", _row("t1")]))
        rows = load_arm_rows(p, "df")
        assert list(rows) == ["t1"]
        err = capsys.readouterr().err
        assert "非对象详情行 1" in err
        assert "无主键行" not in err, "行形状问题不是键形态问题，两条不得并写"

    def test_only_the_shapes_that_occurred_are_named(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path, _batch("df", [_row(None)]))
        load_arm_rows(p, "df")
        err = capsys.readouterr().err
        assert err.count("无主键行") == 1 and "value_null 1" in err
        for absent in ("key_absent", "empty_string", "not_string", "unhashable", "非对象详情行", "被覆盖"):
            assert absent not in err, f"未发生的机制不得出现在 WARN 里：{absent}"

    def test_collision_and_keyless_are_reported_in_one_line_but_counted_apart(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = _write(tmp_path, _batch("df", [_row("t1"), _row("t1"), _row(), _row(["z"])]))
        rows = load_arm_rows(p, "df")
        err = capsys.readouterr().err
        assert "被覆盖 task_id 1 个：'t1'" in err and "key_absent 1、unhashable 1" in err
        assert "details 行 4 → 行摘要 2" in err and len(rows) == 2


# ─── 3. 既有 fail-closed 语义不得被本轮改造放宽 ────────────────────────────────
class TestExistingFailClosedKept:
    def test_missing_artifact_still_raises(self, tmp_path: Path) -> None:
        with pytest.raises(MissingArtifactError):
            load_arm_rows(tmp_path / "nope.json")

    def test_ambiguous_arm_still_raises(self, tmp_path: Path) -> None:
        p = _write(tmp_path, {"results": {"a": {"details": [_row("t1")]}, "b": {"details": [_row("t1")]}}})
        with pytest.raises(MissingArtifactError):
            load_arm_rows(p)

    def test_details_not_list_still_raises(self, tmp_path: Path) -> None:
        p = _write(tmp_path, {"results": {"a": {"details": None}}})
        with pytest.raises(MissingArtifactError):
            load_arm_rows(p, "a")

    def test_auto_arm_selection_and_row_summary_unchanged(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = _write(tmp_path, _batch("only", [_row("t1"), _row("t2")]))
        assert load_arm_rows(p) == {
            "t1": {
                "detection_rate": 1.0,
                "spec_replace_applied": None,
                "specificity_gate_verdict": None,
                "red_regression_violation": None,
            },
            "t2": {
                "detection_rate": 1.0,
                "spec_replace_applied": None,
                "specificity_gate_verdict": None,
                "red_regression_violation": None,
            },
        }
        assert capsys.readouterr().err == ""


# ─── 4. 真路径：全仓 0 实例 + 覆盖面下界 ───────────────────────────────────────
def _bucket_batches(paths: list[Path]) -> dict[str, Any]:
    """按共享 loader 的真实走法核每一批次，并把命中**全部分桶**留痕。

    四个桶必须加起来等于命中总数：`judged`（有 ≥1 个含 dict 行的臂，真正提供了
    "0 折叠"证据）、`empty_details`（能打开但没有一行可核）、`other_schema`（根本不是
    臂批次）、`unreadable`。后三桶**不**为 0 实例提供证据，只能点名承认——"没打开的文件"
    当成"打开了且干净"，就是 AB-12c 那条探针漏扫的同一类缺陷。真语料与合成语料走同一个
    函数：真语料里 `unreadable` 实测 0 例，等式只有在合成语料上才会被四个非空桶同时压过。
    """
    judged: set[Path] = set()
    empty_details: list[Path] = []
    other_schema: list[Path] = []
    unreadable: list[Path] = []
    arms = 0
    dict_rows = 0
    collapsed_arms = 0
    mismatched_arms = 0
    paths = sorted(paths)
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            unreadable.append(p)
            continue
        if not isinstance(data, dict):
            other_schema.append(p)
            continue
        results = data.get("results")
        if not isinstance(results, dict):
            other_schema.append(p)
            continue
        usable = [
            arm for arm, body in results.items() if isinstance(body, dict) and isinstance(body.get("details"), list)
        ]
        if not usable:
            other_schema.append(p)
            continue
        armed = False
        for arm in usable:
            details = results[arm]["details"]
            n_rows = sum(1 for r in details if isinstance(r, dict))
            if n_rows == 0:
                continue
            armed = True
            judged.add(p)
            arms += 1
            dict_rows += n_rows
            rows = load_arm_rows(p, arm)
            if len(rows) != n_rows:
                mismatched_arms += 1
                collapsed_arms += 1
        if not armed:
            empty_details.append(p)
    return {
        "glob": len(paths),
        "judged_files": len(judged),
        "arms": arms,
        "dict_rows": dict_rows,
        "collapsed": collapsed_arms,
        "mismatched": mismatched_arms,
        "empty_details": empty_details,
        "other_schema": other_schema,
        "unreadable": unreadable,
    }


class TestRealPathInvariants:
    def _census(self) -> dict[str, Any]:
        return _bucket_batches(sorted(_ROOT.glob(_BENCH_GLOB)))

    def test_bucket_equation_is_stressed_by_a_corpus_with_all_four_kinds(self, tmp_path: Path) -> None:
        """四桶同时非空的语料才能压等式——真批次里 `unreadable` 实测 0 例，等式从没被那条撑过。"""
        good = _write(tmp_path, _batch("df", [_row("t1"), _row("t2")]), name="benchmark_good.json")
        no_rows = _write(tmp_path, _batch("df", []), name="benchmark_empty.json")
        no_arm = _write(tmp_path, {"results": {"df": {"summary": {}}}}, name="benchmark_noarm.json")
        mdo = _write(tmp_path, {"batch": "pilot", "rows": [], "summary": {}}, name="benchmark_mdo.mdo.json")
        listing = _write(tmp_path, ["not", "an", "object"], name="benchmark_list.json")
        broken = tmp_path / "benchmark_broken.json"
        broken.write_text("{truncated", encoding="utf-8")
        c = _bucket_batches([good, no_rows, no_arm, mdo, listing, broken])
        assert c["glob"] == 6
        assert c["judged_files"] == 1 and c["arms"] == 1 and c["dict_rows"] == 2
        assert c["collapsed"] == 0 and c["mismatched"] == 0
        assert [p.name for p in c["empty_details"]] == ["benchmark_empty.json"]
        assert [p.name for p in c["other_schema"]] == [
            "benchmark_list.json",
            "benchmark_mdo.mdo.json",
            "benchmark_noarm.json",
        ]
        assert [p.name for p in c["unreadable"]] == ["benchmark_broken.json"]
        assert (
            c["judged_files"] + len(c["empty_details"]) + len(c["other_schema"]) + len(c["unreadable"]) == c["glob"]
        ), "分桶等式在四桶全非空时也必须平"

    def test_no_real_batch_collapses_any_row(self, capsys: pytest.CaptureFixture[str]) -> None:
        # BZ 轮：扫描面下界以全归档（246 份 / 300 臂 / 10,659 行）校准——
        # fresh clone 只有入库子集，前提不成立时显式 skip 并带实测读数
        # （tests/_corpus_guard.py），不把"没扫到"折成"扫过且干净"。
        require_full_corpus()
        c = self._census()
        assert c["glob"] >= _CENSUS_MIN_FILES, f"扫描面回落：glob 只命中 {c['glob']} 份批次"
        assert c["judged_files"] >= _CENSUS_MIN_JUDGED_FILES, f"真正核到行的文件回落：{c['judged_files']} 份"
        assert c["arms"] >= _CENSUS_MIN_ARMS, f"扫描面回落：只核了 {c['arms']} 个臂"
        assert c["dict_rows"] >= _CENSUS_MIN_ROWS, f"扫描面回落：只数到 {c['dict_rows']} 个 dict 行"
        assert c["collapsed"] == 0 and c["mismatched"] == 0, "真批次出现行集折叠——0 实例登记须撤销"
        assert capsys.readouterr().err == "", "真批次上不得新产生任何 WARN"

    def test_every_glob_match_is_bucketed_so_nothing_is_silently_skipped(self) -> None:
        """分桶总数 == glob 命中数：少一个桶就意味着有一份文件没被承认它为什么不算证据。"""
        c = self._census()
        accounted = c["judged_files"] + len(c["empty_details"]) + len(c["other_schema"]) + len(c["unreadable"])
        assert accounted == c["glob"], f"分桶不平：{accounted} != glob {c['glob']}（有文件既没核也没点名）"
        assert c["unreadable"] == [], f"读不动的批次要按 AB-9 撤销 0 实例登记：{c['unreadable']}"

    def test_non_arm_batches_are_admitted_by_name_not_dropped(self) -> None:
        """核不到行的批次只能以"看得出的形状"承认出局，且形状本身要能被复核。"""
        # BZ 轮：两类出局文件（.mdo.json / 空 details）的存在性以全归档为
        # 前提——同 test_no_real_batch_collapses_any_row 的显式 skip 口径。
        require_full_corpus()
        c = self._census()
        for p in c["other_schema"]:
            assert p.name.endswith(".mdo.json"), f"意外的非臂批次形状：{p}——需先撤销覆盖面登记"
        assert len(c["other_schema"]) >= 2 and len(c["empty_details"]) >= 2, (
            f"本轮实测的两类出局文件（2 份 .mdo.json + 2 份空 details 例）不得凭空消失："
            f"other_schema={c['other_schema']} empty_details={c['empty_details']}"
        )

    def test_committed_batch_jsons_are_not_rewritten(self) -> None:
        """批次与报告受 SHA256SUMS 保护：本轮不重写它们——逐位比对才叫锁。"""
        checked = 0
        for sums in sorted(_ROOT.glob("experiments/results/**/SHA256SUMS")):
            entries = {
                line.split()[1]: line.split()[0]
                for line in sums.read_text(encoding="utf-8").splitlines()
                if len(line.split()) == 2
            }
            for name, digest in entries.items():
                target = sums.parent / name
                if not target.exists():
                    continue
                assert hashlib.sha256(target.read_bytes()).hexdigest() == digest, f"{target} 已被改动"
                checked += 1
        assert checked >= 100, f"SHA256SUMS 核对面回落：只核了 {checked} 个工件"
