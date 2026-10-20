"""E7 客观证据预筛工具的回归锁（零 LLM）。

对应 `experiments/e7_evidence_prepass.py`。该工具只提取事实、不做判定，
但它的**正确性**直接决定人工裁决的起点，故此处锁定五件事：

1. 围栏语言标签剥离——`python` 首行是**合法表达式**而非语法错误，
   按"解析失败才剥离"的顺序处理会让 AST 等价判定恒为 False（实测踩过）；
   且剥离只摘首行，正文含尾换行逐字节原样；
2. docstring 归一化——去 docstring 后结构相同的代码应判等价；
3. 差异分类——仅注释/空行的差异应判 trivial；
4. **跨文件 gold 口径**——`is_cross_file=True` 的 gold 在 `fixed_module_code`，
   只读 `fixed` 会拿到空串，把"工具取错字段"印成"上游素材缺失"，审阅者据此
   无法裁决（2026-10-19 在 n41/n72 工作表候选 32/44 实测踩过）；
5. 归档数据上的**事实快照**——当前 72 条候选中 15 条 AST 结构等价、其中
   14 条差异仅注释/空行。数字会随批次/抽样变化，锁定它是为了让工具回归或
   数据漂移立刻可见，而不是断言"永远如此"。
"""

from __future__ import annotations

from experiments.e7_evidence_prepass import (
    ast_signature,
    collect_evidence,
    diff_facts,
    strip_fence_language,
)
from experiments.repair_sample_selection import (
    _DEFAULT_BATCHES,
    build_sampling_frame,
    gold_reference_code,
    select_stratified_sample,
    stratify,
)
from experiments.statistical_analysis import load_experiment_results_with_sources


class TestFenceArtifact:
    """围栏语言标签剥离（踩坑回归锁）。"""

    def test_strips_language_tag(self) -> None:
        assert strip_fence_language("python\nx = 1\n") == "x = 1\n"
        assert strip_fence_language("PY\nx = 1\n") == "x = 1\n"

    def test_strips_only_first_line_keeping_body_verbatim(self) -> None:
        """多行正文与尾换行必须逐字节保留（`splitlines()` 再 join 会吃尾换行）。"""
        assert strip_fence_language("python\na = 1\n\nb = 2\n") == "a = 1\n\nb = 2\n"
        assert strip_fence_language("python\n") == ""

    def test_leaves_real_code_untouched(self) -> None:
        code = "x = 1\npython = 2\n"
        assert strip_fence_language(code) == code, "只应剥离首行标签，不碰正文"

    def test_python_first_line_is_not_a_syntax_error(self) -> None:
        """锁定根因：`python` 是合法表达式，必须先剥离再解析。

        若实现改成"解析失败才剥离"，本用例会失败——因为 ``python\\nx = 1``
        能被 ast.parse 接受，只是多出 ``Name(id='python')`` 节点。
        """
        with_fence = "python\nx = 1\n"
        without_fence = "x = 1\n"
        assert ast_signature(with_fence) == ast_signature(without_fence)


class TestGoldReferenceResolution:
    """跨文件任务的 gold 口径（B4 人工裁决可执行性的前提）。"""

    def test_cross_file_uses_fixed_module_code(self) -> None:
        md = {"is_cross_file": True, "fixed_module_code": "def leaf(x):\n    return x\n", "fixed": ""}
        assert gold_reference_code(md) == "def leaf(x):\n    return x\n"

    def test_single_file_uses_fixed(self) -> None:
        assert gold_reference_code({"fixed": "x = 1\n"}) == "x = 1\n"

    def test_missing_metadata_is_empty_not_crash(self) -> None:
        assert gold_reference_code(None) == ""
        assert gold_reference_code({}) == ""

    def test_cross_file_candidate_not_reported_as_missing(self) -> None:
        """变异锁：若 collect_evidence 退回只读 `fixed`，本用例立刻红。

        跨文件候选的 `fixed` 为空串，而空串能被 ast.parse 接受（空模块），
        因此退回旧实现时既不会报"无法解析"、也不会抛错——只会静默把该行
        标成 gold 缺失 + `ast_state="素材缺失"`，正是本用例要拦住的形态。
        """
        row = {
            "task_id": "s42__synthetic__task_cross",
            "patch": "python\ndef leaf(x):\n    return x\n",
            "task_metadata": {
                "is_cross_file": True,
                "fixed_module_code": "def leaf(x):\n    return x\n",
                "fixed": "",
            },
        }
        evidence = collect_evidence(row)
        assert evidence["gold_missing"] is False
        assert evidence["ast_state"] != "素材缺失"
        assert evidence["ast_equal"] is True


class TestMissingMaterialState:
    """素材缺失必须自成一态，不得伪装成"有差异"。"""

    def test_empty_gold_is_reported_as_missing_not_as_diff(self) -> None:
        """空 gold 能被 ast.parse 接受（空模块），必须先短路再比对。

        退回旧实现时本行会报 `ast_state="有差异"` + `n_diff=21`，与同行的
        "素材缺失=gold" 自相矛盾，并把"无可比对"渲染成"有 21 行真实差异"。
        """
        row = {
            "task_id": "t_missing_gold",
            "patch": "python\n" + "".join(f"line_{i} = {i}\n" for i in range(10)),
            "task_metadata": {"fixed": ""},
        }
        evidence = collect_evidence(row)
        assert evidence["gold_missing"] is True
        assert evidence["ast_state"] == "素材缺失"
        assert evidence["ast_equal"] is False
        assert evidence["n_diff"] is None, "无可比对素材时差异行数不得给整数"
        assert evidence["trivial_only"] is None

    def test_empty_patch_is_reported_as_missing(self) -> None:
        row = {"task_id": "t_missing_patch", "patch": "  \n", "task_metadata": {"fixed": "x = 1\n"}}
        evidence = collect_evidence(row)
        assert evidence["patch_missing"] is True
        assert evidence["ast_state"] == "素材缺失"
        assert evidence["n_diff"] is None


class TestAstSignature:
    def test_docstring_ignored(self) -> None:
        a = 'def f():\n    """doc A."""\n    return 1\n'
        b = 'def f():\n    """doc B, different text."""\n    return 2 * 0 + 1\n'
        assert ast_signature(a) != ast_signature(b), "实质代码不同不得判等价"

        c = 'def f():\n    """doc A."""\n    return 1\n'
        d = "def f():\n    return 1\n"
        assert ast_signature(c) == ast_signature(d), "仅 docstring 差异应判结构等价"

    def test_real_change_detected(self) -> None:
        assert ast_signature("x = 1\n") != ast_signature("x = 2\n")

    def test_unparseable_returns_none(self) -> None:
        assert ast_signature("def broken(:\n") is None


class TestDiffFacts:
    def test_comment_only_diff_is_trivial(self) -> None:
        patch = "x = 1\n# noise_seed=42\n"
        gold = "x = 1\n"
        n_diff, trivial = diff_facts(patch, gold)
        assert n_diff == 1
        assert trivial is True

    def test_code_change_is_not_trivial(self) -> None:
        n_diff, trivial = diff_facts("x = 1\n", "x = 2\n")
        assert n_diff == 2
        assert trivial is False

    def test_identical_is_zero(self) -> None:
        assert diff_facts("x = 1\n", "x = 1\n") == (0, True)


class TestArchivedSnapshot:
    """归档 n=72 候选上的事实快照（数据漂移可见，不作为永久断言）。"""

    @staticmethod
    def _selected() -> list[dict]:
        results, _ = load_experiment_results_with_sources(
            "experiments/results/main_batch",
            list(_DEFAULT_BATCHES),
            allow_schema_mixed=False,
            pool_seeds=True,
        )
        frame = build_sampling_frame(results.get("aitester") or [])
        return select_stratified_sample(stratify(frame), 1.0, 42)

    def test_ast_equal_count_snapshot(self) -> None:
        """当前快照：72 条中 15 条 AST 结构等价，其中 14 条差异仅注释/空行。

        若本用例失败，先确认是"批次数据变化"还是"工具回归"：
        - 数据变化 → 更新本数字并重跑 `e7_evidence_prepass.py`；
        - 工具回归 → 修工具（这是本类存在的意义）。
        """
        rows = [collect_evidence(r) for r in self._selected()]
        equal = [r for r in rows if r["ast_equal"]]
        assert len(rows) == 72
        assert len(equal) == 15, f"AST 等价条数漂移：{len(equal)}（期望 15）"
        trivial_equal = sum(1 for r in equal if r["trivial_only"])
        assert trivial_equal == 14, f"等价中纯注释差异条数漂移：{trivial_equal}（期望 14）"

    def test_cross_file_candidates_present_and_resolved(self) -> None:
        """快照含 2 条跨文件候选，且其 gold 已由 `fixed_module_code` 正确取到。

        锁定本批次的形状：若跨文件候选数变化，说明抽样框或批次数据漂移，
        需重新核对 gold 口径而非直接改数字。
        """
        selected = self._selected()
        cross = [r for r in selected if (r.get("task_metadata") or {}).get("is_cross_file")]
        assert [r.get("task_id") for r in cross] == [
            "s42__synthetic__task_0068",
            "s42__synthetic__task_0058",
        ], "跨文件候选集合漂移，须重新核对 gold 取值口径"
        for row in cross:
            md = row.get("task_metadata") or {}
            assert not str(md.get("fixed") or "").strip(), "跨文件任务的 fixed 应为空（口径前提）"
            assert str(md.get("fixed_module_code") or "").strip(), "跨文件任务的 gold 应在 fixed_module_code"
            assert gold_reference_code(md) == str(md["fixed_module_code"])

    def test_no_candidate_has_missing_material(self) -> None:
        """预筛的前提：全部候选的 patch 与 gold 都可解析、非空。"""
        rows = [collect_evidence(r) for r in self._selected()]
        assert not [r["task_id"] for r in rows if r["patch_missing"] or r["gold_missing"]]
        assert not [r["task_id"] for r in rows if r["ast_state"] in ("无法解析", "素材缺失")]
        assert all(isinstance(r["n_diff"], int) for r in rows), "无素材缺失时差异行数应全为整数"
