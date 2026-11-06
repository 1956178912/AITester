"""B1（2026-11-05）：源码补丁证据门的 **图内 gold 裁决**——官方测试跑在打补丁的源码上。

背景（最小批暴露的 B1）：`assess_patch_evidence` 的 gold 支只读
`state["repo_verification"]`，而该键此前**只有**工作流结束后、且只在
SWE-bench 仓库级分支里被写（`experiments/run_benchmark.py:3036`）。于是
图内每一轮的等级只能落在 sbfl（被 B5 覆盖率链卡死）/ keyword（非确定）/
none，证据门把**本来正确**的源码补丁按"无证据"回滚——gold 是一条声明了
却永不命中的死支。

本文件锁四件事：
1. `run_official_tests` 的三值裁决（gold / red / unavailable）与计数披露——
   真起 pytest 子进程，不用 mock 造一个"看起来绿"的裁决；
2. 证据门只在**等级不足**时才执行官方测试（默认关时零子进程、行为逐位不变）；
3. gold 只从"官方测试全绿"来：红 / 不可判定 / 无官方测试一律仍拒，
   **不许降级成 keyword 放行**；
4. 材料管道与 M1 事后 repair **同一提取器**，且 gold 答案材料
   （`fixed` / `fixed_module_code`）不得进入 state（prompt 泄漏面）。
"""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

import pytest

import src.tools.detection_gates as dg_mod
import src.tools.patch_evidence as pe_mod
from src.graph import nodes as nodes_mod

_ORIG = "def f():\n    return 1\n"
_PATCH = "def f():\n    return 2\n"
# 委托原语把 target_code 落成 `{module_name}.py`、test_code 落成 `test_{module_name}.py`，
# 官方测试必须显式 import 目标模块——否则 NameError 让"绿/红"两条腿都变成假信号
_MOD = "modb1"
# 官方测试：断言 f() == 2 ⇒ 在 _ORIG 上红、在 _PATCH 上绿
_GREEN_TEST = f"from {_MOD} import f\n\n\ndef test_f():\n    assert f() == 2\n"
_RED_TEST = f"from {_MOD} import f\n\n\ndef test_f():\n    assert f() == 3\n"
_NO_TESTS_TEST = "def helper():\n    return 1\n"
_SKIPPED_TEST = (
    f"import pytest\nfrom {_MOD} import f\n\n\n@pytest.mark.skip(reason='n/a')\ndef test_f():\n    assert f() == 2\n"
)
_BAD_IMPORT_TEST = "from definitely_missing_module_xyz import thing\n\n\ndef test_f():\n    assert thing\n"


def _state(tmp_path: Any, **extra: Any) -> dict[str, Any]:
    """patch_applier 入参 state：target_file 落在 tmp_path（白名单内，真实可写）。"""
    target = tmp_path / "mod.py"
    target.write_text(_ORIG, encoding="utf-8")
    state: dict[str, Any] = {
        "target_code": _ORIG,
        "patch": _PATCH,
        "target_file": str(target),
        "module_name": "mod",
        "iteration": 0,
        "error_category": "RUNTIME",
        "diagnosis": "off-by-one",
    }
    state.update(extra)
    return state


def _run(monkeypatch: pytest.MonkeyPatch, state: dict[str, Any], **env: str) -> dict[str, Any]:
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with (
        patch.object(nodes_mod, "_trace_node"),
        patch.object(nodes_mod, "publish_patch_applied"),
    ):
        return nodes_mod._patch_applier_node(state)  # type: ignore[arg-type]


def _disk(tmp_path: Any) -> str:
    return (tmp_path / "mod.py").read_text(encoding="utf-8")


def _stub_verdict(monkeypatch: pytest.MonkeyPatch, verdict: str, **extra: Any) -> MagicMock:
    """桩掉执行面（run_official_tests），只测门对裁决的反应；真执行另有专测。"""
    spy = MagicMock(return_value={"verdict": verdict, "reason": verdict, "rc": 0, "passed": 1, **extra})
    monkeypatch.setattr(dg_mod, "run_official_tests", spy)
    return spy


@pytest.mark.unit
class TestOfficialTestsGoldEnabledFlag:
    """开关默认关：ADR-0003 口径，坏值不放行（与证据门本体同用 env_flag 真值集）。"""

    def test_default_is_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PATCH_EVIDENCE_OFFICIAL_TESTS_ENABLE", raising=False)
        assert pe_mod.official_tests_gold_enabled() is False

    def test_true_values_and_garbage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PATCH_EVIDENCE_OFFICIAL_TESTS_ENABLE", "true")
        assert pe_mod.official_tests_gold_enabled() is True
        monkeypatch.setenv("PATCH_EVIDENCE_OFFICIAL_TESTS_ENABLE", "")
        assert pe_mod.official_tests_gold_enabled() is False


@pytest.mark.unit
class TestRunOfficialTestsVerdict:
    """真起 pytest 的三值裁决：rc / 摘要计数 / 有效通过三件都得对上。"""

    def _verdict(self, test_code: str, patched_code: str = _PATCH, module_name: str | None = _MOD) -> dict:
        return dg_mod.run_official_tests(test_code, patched_code, module_name)

    def test_all_green_is_gold_with_counts(self) -> None:
        res = self._verdict(_GREEN_TEST)
        assert res["verdict"] == "gold"
        assert res["reason"] == "gold"
        assert res["rc"] == 0
        assert res["passed"] == 1, "计数必须来自权威摘要行，不能只报一个布尔"

    def test_failing_assertion_is_red_not_unavailable(self) -> None:
        res = self._verdict(_RED_TEST)
        assert res["verdict"] == "red"
        assert res["reason"] == "failed"
        assert res["rc"] == 1
        assert res["failed"] == 1

    def test_buggy_source_is_red_proving_the_test_is_discriminating(self) -> None:
        """反例腿：同一份官方测试跑在**未修**源码上必须是 red（否则"全绿"无信息量）。"""
        assert self._verdict(_GREEN_TEST, patched_code=_ORIG)["verdict"] == "red"

    def test_collection_error_is_unavailable(self) -> None:
        res = self._verdict(_BAD_IMPORT_TEST)
        assert res["verdict"] == "unavailable"
        assert res["reason"] == "exec_error"

    def test_no_tests_collected_is_unavailable(self) -> None:
        """rc==5（没有收到任何用例）= 根本没跑起来，不得读作"官方测试通过"。"""
        res = self._verdict(_NO_TESTS_TEST)
        assert res["verdict"] == "unavailable"
        assert res["reason"] in ("exec_error", "no_effective_pass")

    def test_all_skipped_suite_is_unavailable(self) -> None:
        """F03 口径：全 skip 的套件 rc==0，但没有任何断言执行 ⇒ 不可判定。"""
        res = self._verdict(_SKIPPED_TEST)
        assert res["verdict"] == "unavailable"
        assert res["reason"] == "no_effective_pass"

    def test_empty_test_code_makes_no_subprocess(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = MagicMock(side_effect=AssertionError("不该执行"))
        monkeypatch.setattr(dg_mod, "_pytest_in_tmp_raw", spy)
        res = dg_mod.run_official_tests("   ", _PATCH, "modb1")
        assert spy.call_count == 0
        assert res["verdict"] == "unavailable"
        assert res["reason"] == "no_official_tests"

    def test_illegal_module_name_stays_before_delegation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """module_name 同时是临时目录文件名 ⇒ 非法名必须在委托层之前挡掉（AC2 同口径）。"""
        spy = MagicMock(side_effect=AssertionError("不该执行"))
        monkeypatch.setattr(dg_mod, "_pytest_in_tmp_raw", spy)
        for bad in ("", None, "a/b", "1mod"):
            res = dg_mod.run_official_tests(_GREEN_TEST, _PATCH, bad)
            assert res["verdict"] == "unavailable", res
            assert res["reason"] == "invalid_module"
        assert spy.call_count == 0

    def test_runner_unavailable_is_unavailable_not_red(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = MagicMock(return_value=None)
        monkeypatch.setattr(dg_mod, "_pytest_in_tmp_raw", spy)
        res = dg_mod.run_official_tests(_GREEN_TEST, _PATCH, "modb1")
        assert spy.call_count == 1
        assert res["verdict"] == "unavailable"
        assert res["reason"] == "runner_unavailable"


@pytest.mark.unit
class TestOfficialTestsEvidenceReadsStateMaterial:
    """state["official_tests"] → 执行入参的映射（材料缺省一律 unavailable）。"""

    def test_missing_channel_is_unavailable(self) -> None:
        res = pe_mod.official_tests_evidence({"module_name": "mod"}, _PATCH)
        assert res["verdict"] == "unavailable"
        assert res["reason"] == "no_official_tests"

    def test_channel_without_code_is_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = MagicMock(side_effect=AssertionError("不该执行"))
        monkeypatch.setattr(dg_mod, "run_official_tests", spy)
        res = pe_mod.official_tests_evidence({"official_tests": {"module_name": "mod"}}, _PATCH)
        assert spy.call_count == 0
        assert res["reason"] == "no_official_tests"

    def test_material_module_name_and_payload_are_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = MagicMock(return_value={"verdict": "gold"})
        monkeypatch.setattr(dg_mod, "run_official_tests", spy)
        official = {
            "code": _GREEN_TEST,
            "module_name": "quix_bitcount",
            "material": {"source": "quixbugs", "is_cross_file": False},
        }
        res = pe_mod.official_tests_evidence({"official_tests": official, "module_name": "mod"}, _PATCH)
        assert res["verdict"] == "gold"
        # 模块名取材料侧（gold 测试 import 的目标名），不是 state 侧的截取名
        assert spy.call_args.args[:3] == (_GREEN_TEST, _PATCH, "quix_bitcount")
        assert spy.call_args.kwargs["task_metadata"] == official["material"]


@pytest.mark.unit
class TestEvidenceGateUsesOfficialTestsOnlyWhenInsufficient:
    """门的三条腿：gold 放行、red 仍拒、不可判定仍拒——且等级不足才付执行成本。"""

    def test_default_off_makes_no_subprocess_and_still_refuses(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """对照腿（零行为变化）：开关不设 ⇒ 不执行官方测试，等级 none、照旧回滚。"""
        spy = _stub_verdict(monkeypatch, "gold")
        state = _state(tmp_path, official_tests={"code": _GREEN_TEST, "module_name": "mod"})
        update = _run(monkeypatch, state)
        assert spy.call_count == 0, "默认关不得新增子进程执行面"
        assert update["patch_evidence_level"] == "none"
        assert update["source_patched_unverified"] is True
        assert _disk(tmp_path) == _ORIG, "默认关必须保持历史拒绝口径"

    def test_gold_from_official_tests_allows_the_write(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = _stub_verdict(monkeypatch, "gold", passed=3)
        state = _state(tmp_path, official_tests={"code": _GREEN_TEST, "module_name": "mod"})
        update = _run(monkeypatch, state, PATCH_EVIDENCE_OFFICIAL_TESTS_ENABLE="true")
        assert spy.call_count == 1
        assert update["patch_evidence_level"] == "gold", "官方测试全绿⇒等级升到 gold（不是 keyword）"
        assert update["source_patched_unverified"] is False
        assert _disk(tmp_path) == _PATCH, "gold 放行后磁盘必须是补丁态"
        assert update["official_test_evidence"]["passed"] == 3, "放行理由要留在工件里，不能只给结论"

    def test_red_official_tests_still_refuse(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_verdict(monkeypatch, "red", failed=1)
        state = _state(tmp_path, official_tests={"code": _RED_TEST, "module_name": "mod"})
        update = _run(monkeypatch, state, PATCH_EVIDENCE_OFFICIAL_TESTS_ENABLE="true")
        assert update["patch_evidence_level"] == "none"
        assert update["source_patched_unverified"] is True
        assert _disk(tmp_path) == _ORIG

    def test_unavailable_official_tests_still_refuse(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_verdict(monkeypatch, "unavailable", reason="exec_error")
        state = _state(tmp_path, official_tests={"code": _BAD_IMPORT_TEST, "module_name": "mod"})
        update = _run(monkeypatch, state, PATCH_EVIDENCE_OFFICIAL_TESTS_ENABLE="true")
        assert update["patch_evidence_level"] == "none"
        assert _disk(tmp_path) == _ORIG

    def test_no_official_tests_material_still_refuses(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """无官方测试（如 SWE-bench 面）⇒ 仍拒——不许因为"开了开关"就放行。"""
        spy = _stub_verdict(monkeypatch, "unavailable", reason="no_official_tests")
        state = _state(tmp_path)  # 无 official_tests 键
        update = _run(monkeypatch, state, PATCH_EVIDENCE_OFFICIAL_TESTS_ENABLE="true")
        assert spy.call_count == 0, "state 无材料时连委托都不该发出"
        assert update["patch_evidence_level"] == "none"
        assert _disk(tmp_path) == _ORIG

    def test_keyword_diagnosis_does_not_become_gold(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """不许降级放行：keyword 级证据在默认门限下仍被拒，官方测试 red 也不改变这点。"""
        _stub_verdict(monkeypatch, "red", failed=2)
        state = _state(
            tmp_path,
            diagnosis="测试生成错误：断言写反",
            official_tests={"code": _RED_TEST, "module_name": "mod"},
        )
        update = _run(monkeypatch, state, PATCH_EVIDENCE_OFFICIAL_TESTS_ENABLE="true")
        assert update["patch_evidence_level"] == "keyword"
        assert _disk(tmp_path) == _ORIG

    def test_enough_evidence_skips_the_official_test_run(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """sbfl 已放行时不再付执行成本（官方测试只补"本该存在但拿不到"的那条证据）。"""
        spy = _stub_verdict(monkeypatch, "gold")
        state = _state(
            tmp_path,
            official_tests={"code": _GREEN_TEST, "module_name": "mod"},
            fl_spectral_focus={"top_k": [{"line": 2, "score": 0.9}]},
        )
        update = _run(monkeypatch, state, PATCH_EVIDENCE_OFFICIAL_TESTS_ENABLE="true")
        assert spy.call_count == 0
        assert update["patch_evidence_level"] == "sbfl"
        assert "official_test_evidence" not in update

    def test_gate_off_ablation_does_not_pay_for_official_tests(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """消融腿：证据门本体关掉时不跑官方测试（不阻断就没有必要付执行成本）。"""
        spy = _stub_verdict(monkeypatch, "gold")
        state = _state(tmp_path, official_tests={"code": _GREEN_TEST, "module_name": "mod"})
        update = _run(
            monkeypatch, state, PATCH_EVIDENCE_OFFICIAL_TESTS_ENABLE="true", PATCH_EVIDENCE_GATE_ENABLE="false"
        )
        assert spy.call_count == 0
        assert update["patch_evidence_level"] == "none"
        assert _disk(tmp_path) == _PATCH


@pytest.mark.unit
class TestOfficialTestsStateChannel:
    """两条新通道必须声明 + 工厂初始化，否则 LangGraph 静默丢弃（M14/O35 同类）。"""

    def test_declared_and_initialized(self) -> None:
        from src.graph.state import AITesterState, create_initial_state

        annotations = AITesterState.__annotations__
        assert "official_tests" in annotations
        assert "official_test_evidence" in annotations
        state = create_initial_state(task_uuid="t1", target_file="/tmp/t.py", target_code=_ORIG, max_iterations=1)
        assert state["official_tests"] is None
        assert state["official_test_evidence"] is None


@pytest.mark.unit
class TestOfficialTestsMaterialPipeline:
    """run_benchmark 侧的材料提取：与 M1 事后 repair 同源，且不带走 gold 答案。"""

    class _Task:
        def __init__(self, task_id: str, metadata: dict[str, Any], instance_code: str = _ORIG) -> None:
            self.task_id = task_id
            self.metadata = metadata
            self.instance_code = instance_code
            self.expected_pass_count = 1
            self.total_test_count = 1
            self.test_code = metadata.get("test_cases", "")

    def test_synthetic_material_is_extracted(self) -> None:
        from experiments.run_benchmark import _official_tests_material

        task = self._Task(
            "synthetic__mod", {"source": "synthetic", "test_cases": _GREEN_TEST, "fixed": "def f():\n    return 2\n"}
        )
        material = _official_tests_material(task)
        assert material is not None
        assert material["code"] == _GREEN_TEST
        assert material["module_name"] == "mod"
        assert material["expected_pass_count"] == 1
        assert material["total_test_count"] == 1

    def test_gold_answer_material_never_enters_state(self) -> None:
        """泄漏锁：`fixed` / `fixed_module_code` 是 gold 答案，不得随材料入 state（prompt 面）。"""
        from experiments.run_benchmark import _official_tests_material

        task = self._Task(
            "synthetic__mod",
            {
                "source": "synthetic",
                "test_cases": _GREEN_TEST,
                "fixed": "def f():\n    return 2\n",
                "fixed_module_code": "def f():\n    return 2\n",
                "module_a_code": "def g():\n    return 1\n",
                "module_a_name": "module_a",
                "is_cross_file": True,
            },
        )
        material = _official_tests_material(task)["material"]
        assert "fixed" not in material
        assert "fixed_module_code" not in material
        # 物化所需的伴生模块**缺陷原版**必须留下，否则跨文件官方测试收不到用例
        assert material["module_a_code"] == "def g():\n    return 1\n"
        assert material["is_cross_file"] is True

    def test_no_gold_material_yields_none(self) -> None:
        from experiments.run_benchmark import _official_tests_material

        assert (
            _official_tests_material(self._Task("swe__x-1", {"source": "swe_bench", "test_cases": _GREEN_TEST})) is None
        )
        assert (
            _official_tests_material(self._Task("synthetic__mod", {"source": "synthetic", "test_cases": "  "})) is None
        )
        assert _official_tests_material(self._Task("synthetic__mod", {"source": "synthetic"})) is None


def _make_support_tree(base: Any, *, json_dir_name: str = "json_testcases") -> Any:
    """造一棵"预备目录"：python_testcases/{node,load_testdata}.py + json 测试数据。

    `base` 即缓存根（与 `QuixBugsDataset.DEFAULT_CACHE_DIR` 同位），返回其下的
    quixbugs 目录。
    """
    root = base / "quixbugs"
    tc = root / "python_testcases"
    tc.mkdir(parents=True)
    (tc / "node.py").write_text("class Node:\n    pass\n", encoding="utf-8")
    (tc / "load_testdata.py").write_text("def load_json_testcases(name):\n    return []\n", encoding="utf-8")
    (root / json_dir_name).mkdir()
    (root / json_dir_name / "bitcount.json").write_text("[]", encoding="utf-8")
    return root


@pytest.mark.unit
class TestQuixBugsSupportRootSharesLoaderCaliber:
    """材料在盘上却判"未配置"= 判分层与加载层各说一套（B1 实测 gold 可达 0/41）。"""

    def _m1(self, monkeypatch: pytest.MonkeyPatch, cache_dir: Any) -> Any:
        import experiments._m1_metrics as m1_mod
        import src.datasets.dataset_realbugs as realbugs

        monkeypatch.delenv("AITESTER_QUIXBUGS_DATA", raising=False)
        monkeypatch.setattr(realbugs.QuixBugsDataset, "DEFAULT_CACHE_DIR", str(cache_dir))
        return m1_mod

    def test_default_cache_dir_resolves_without_the_env_var(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        m1_mod = self._m1(monkeypatch, tmp_path / "aitester_cache")
        root = _make_support_tree(tmp_path / "aitester_cache")
        assert m1_mod._quixbugs_support_root() == str(root)
        ready, reason = m1_mod._packaged_support_ready()
        assert ready is True, reason

    def test_nested_clone_is_a_candidate(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """辅助件只在上游克隆 `<root>/repo/` 里时也要认（加载器读的是同一棵树）。"""
        cache = tmp_path / "aitester_cache"
        m1_mod = self._m1(monkeypatch, cache)
        repo = cache / "quixbugs" / "repo"
        tc = repo / "python_testcases"
        tc.mkdir(parents=True)
        (tc / "node.py").write_text("class Node:\n    pass\n", encoding="utf-8")
        (tc / "load_testdata.py").write_text("def load_json_testcases(name):\n    return []\n", encoding="utf-8")
        assert m1_mod._quixbugs_support_root() == str(repo)
        assert not (cache / "quixbugs" / "python_testcases").exists(), "对照面：预备目录本身没有辅助件"

    def test_explicit_env_still_wins(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        m1_mod = self._m1(monkeypatch, tmp_path / "aitester_cache")
        root = _make_support_tree(tmp_path / "aitester_cache")
        other = tmp_path / "elsewhere"
        (other / "python_testcases").mkdir(parents=True)
        (other / "python_testcases" / "node.py").write_text("", encoding="utf-8")
        (other / "python_testcases" / "load_testdata.py").write_text("", encoding="utf-8")
        monkeypatch.setenv("AITESTER_QUIXBUGS_DATA", str(other))
        assert m1_mod._quixbugs_support_root() == str(other)
        assert root.is_dir(), "对照物：默认目录也在盘，但显式 env 优先"

    def test_nothing_on_disk_stays_fail_closed(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """R16 口径不变：材料真不在盘上时仍 None + 具名理由，不静默判 0。"""
        m1_mod = self._m1(monkeypatch, tmp_path / "empty_cache")
        assert m1_mod._quixbugs_support_root() is None
        ready, reason = m1_mod._packaged_support_ready()
        assert ready is False and reason

    def test_packaged_tree_copies_json_from_the_repo_subdir(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """json 测试数据只在 `<root>/repo/` 时也必须拷进 tmp 树——缺 json 会让
        官方测试在**收集期**报错，把"材料没拷全"伪装成"补丁没修好"。"""
        import experiments._m1_metrics as m1_mod

        cache = tmp_path / "aitester_cache"
        root = _make_support_tree(cache)
        # 把 json 数据挪进 repo/，辅助件留在预备目录根（真实机器上的形态）
        (root / "repo").mkdir()
        (root / "json_testcases").rename(root / "repo" / "json_testcases")
        monkeypatch.setenv("AITESTER_QUIXBUGS_DATA", str(root))
        work = tmp_path / "work"
        work.mkdir()
        _test_path, _pp = m1_mod._prepare_packaged_test_tree(str(work), _PATCH, _GREEN_TEST, _MOD)
        assert (work / "json_testcases" / "bitcount.json").is_file()


class _FakeTask:
    def __init__(self, instance_code: str, fixed: str, source: str = "synthetic") -> None:
        self.task_id = "synthetic__mod"
        self.instance_code = instance_code
        self.metadata = {"source": source, "fixed": fixed, "test_cases": _GREEN_TEST}


@pytest.mark.unit
class TestDegenerateGoldMaterialIsNotMaterial:
    """B7：ULT 的 `fixed` 是同码占位 ⇒ 对门①而言等于**没有** gold 材料。

    `src/datasets/dataset_ult.py:284,354-357` 注明 `fixed = 被测函数全文`（ULT 语料
    只有 `source_code` + `test_cases` 两样，manifest 实测无修复文本）。把它当
    "gold fixed" 注入 state 后，`logic` 档（`DETECTION_SPECIFICITY_GATE_ENABLE=true`）
    下的特异性门会在**缺陷原码**上跑新生成测试：一条真正缺陷特异的测试必然红
    ⇒ 判 over_red ⇒ 路由换成"再生成"而不是修复 ⇒ ult 面（200 任务、最大单文件面）
    的付费迭代永远修不到源码。同码占位不得冒充独立裁决。
    """

    def test_real_fix_is_still_injected(self) -> None:
        """对照腿：真有修复文本时必须照旧注入（否则本守卫会把 gold 侧一起抹掉）。"""
        from experiments.run_benchmark import _gold_fixed_material

        got = _gold_fixed_material(_FakeTask(_ORIG, _PATCH))
        assert got.strip() == _PATCH.strip(), f"应用后的修复文本须原样可用，实为 {got!r}"
        assert got.strip() != _ORIG.strip()

    def test_same_code_placeholder_yields_no_material(self) -> None:
        from experiments.run_benchmark import _gold_fixed_material

        assert _gold_fixed_material(_FakeTask(_ORIG, _ORIG)) == ""
        # 只差首尾空白同样算同码（占位文本可能带换行）
        assert _gold_fixed_material(_FakeTask(_ORIG, "\n" + _ORIG + "\n")) == ""

    def test_repo_tasks_keep_their_empty_material(self) -> None:
        from experiments.run_benchmark import _gold_fixed_material

        assert _gold_fixed_material(_FakeTask(_ORIG, "", source="swe_bench")) == ""

    def test_injection_site_uses_the_degeneracy_guard(self) -> None:
        """源码锁：注入点必须走带同码守卫的助手，而不是直取未加守卫的原始提取器。"""
        import inspect

        import experiments.run_benchmark as rb_mod

        src = inspect.getsource(rb_mod)
        at = src.index('initial_state["gold_fixed_code"]')
        window = src[max(0, at - 800) : at]
        assert "_gold_fixed_material(task)" in window, "注入点绕开了同码守卫"
        assert "_extract_gold_fixed(" not in window, "注入点不得再直取未加守卫的原始提取器"


@pytest.mark.unit
class TestMaterialBlockersAreNotPaidTwice:
    """B10（2026-11-05）：与补丁无关的"跑不起来"，重复跑只会再付一次超时。

    冒烟 `test_run_20261105T115002Z`（B11 之前，60s 档超时统一落在 `m1_metrics` 标签下）共 8 条
    `m1_metrics：执行超时（>60s）`，分布在 7 个 quixbugs 格，其中 `deepseek-flash__aitester__quixbugs`
    单格 2 条——冒烟每格只有 1 个任务，所以"同一任务重复执行"确凿；标签不分辨是 AC2 对照门
    还是 B1 官方测试门（那正是 B11 收口的归因缺口）。同一任务每一轮被拒都会重跑官方测试，而
    `exec_error`/`runner_unavailable`/`no_effective_pass`/`invalid_module` 这类结论**只取决于测试材料与
    本机环境**，与这一版补丁写了什么无关；重复执行既不改结论也不改放行决定，纯烧墙钟（B12
    把并发放开后这份浪费会被放大）。反之 `red`（断言失败）与补丁有关，**不得**记忆——否则会把
    "这版没修好"错扣到下一版头上。
    """

    def _spy(self, monkeypatch: pytest.MonkeyPatch, ret: dict[str, Any]) -> MagicMock:
        spy = MagicMock(return_value=dict(ret))
        monkeypatch.setattr(dg_mod, "run_official_tests", spy)
        return spy

    _STATE: ClassVar[dict[str, Any]] = {
        "official_tests": {"code": _GREEN_TEST, "module_name": _MOD},
        "module_name": _MOD,
    }

    @pytest.mark.parametrize("reason", ["exec_error", "runner_unavailable", "no_effective_pass", "invalid_module"])
    def test_material_blocker_is_memoized(self, monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
        spy = self._spy(monkeypatch, {"verdict": "unavailable", "reason": reason, "rc": 2})
        state = dict(self._STATE)
        first = pe_mod.official_tests_evidence(state, _PATCH)
        assert first["reason"] == reason and spy.call_count == 1
        state["official_test_evidence"] = first
        second = pe_mod.official_tests_evidence(state, _PATCH + "# 下一轮的补丁不同\n")
        assert spy.call_count == 1, f"{reason} 属材料级不可判定，第二轮不得再付一次执行"
        assert second["memoized"] is True and second["verdict"] == "unavailable"

    @pytest.mark.parametrize("reason", ["failed", "gold", "no_official_tests"])
    def test_patch_dependent_and_zero_cost_reasons_are_not_memoized(
        self, monkeypatch: pytest.MonkeyPatch, reason: str
    ) -> None:
        """red 与补丁有关必须重跑；gold 不记忆（门已放行，不会再问）；无材料本就零成本。"""
        verdict = "unavailable" if reason == "no_official_tests" else ("red" if reason == "failed" else "gold")
        spy = self._spy(monkeypatch, {"verdict": verdict, "reason": reason, "rc": 1})
        state = dict(self._STATE)
        state["official_test_evidence"] = pe_mod.official_tests_evidence(state, _PATCH)
        assert spy.call_count == 1
        pe_mod.official_tests_evidence(state, _PATCH + "# 新补丁\n")
        assert spy.call_count == 2, f"{reason} 的结论与补丁有关（或本就免费），必须重新执行"

    def test_gate_reuses_the_memo_and_still_refuses(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """端到端：带 memo(unavailable) 的第二轮——零子进程、判定不变（仍拒并回滚）。"""
        spy = self._spy(monkeypatch, {"verdict": "unavailable", "reason": "exec_error", "rc": 2})
        memo = {"verdict": "unavailable", "reason": "exec_error", "rc": 2, "passed": 0, "failed": 0}
        state = _state(tmp_path, official_tests={"code": _GREEN_TEST, "module_name": _MOD}, official_test_evidence=memo)
        update = _run(monkeypatch, state, PATCH_EVIDENCE_OFFICIAL_TESTS_ENABLE="true")
        assert spy.call_count == 0
        assert update["patch_evidence_level"] == "none"
        assert _disk(tmp_path) == _ORIG, "memo 不得把拒绝变成放行"
        assert update["official_test_evidence"]["reason"] == "exec_error"
