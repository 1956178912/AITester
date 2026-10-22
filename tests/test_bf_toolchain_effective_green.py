"""BF 轮（2026-10-21）锁：脚本工具链的 rc==0 判绿点接「有效通过」。

F03 同型普查后的最后一层：BE 收口生产路径后，`scripts/tools/` 仍有两处
把 pytest 的 `rc==0` 直接当绿色证据：

1. `self_mutation.py`——基线 `green = rc==0 and not timed_out`；变异体
   `rc==0 → survived`。全 skip / xfail / deselect 的套件同样 rc==0，
   会被读成"基线绿、变异体存活"，压低 mutation score 且无证据；
2. `verify_synthetic_templates.py`——buggy 侧 rc==0 记"全绿"、fixed 侧
   rc==0 记"自洽"。没有断言执行时两侧都没有被证明，fixed 侧的假绿尤其
   危险（模板会进入检测率分母）。

口径与 `src/utils/pytest_output.py` 单一事实源一致：rc==0 且摘要至少
1 个真实 passed、0 failed；部分 skip 与真实 passed 并存仍有效；摘要
不可解析 fail-closed。分类结果沿用既有 `invalid`（不进变异分数分母）+
`baseline_no_effective_pass`（基线阻断原因），不新增报告顶层键。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SELF_MUTATION = _REPO_ROOT / "scripts" / "tools" / "self_mutation.py"
_TEMPLATES = _REPO_ROOT / "scripts" / "tools" / "verify_synthetic_templates.py"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool() -> ModuleType:
    return _load("bf_self_mutation_tool", _SELF_MUTATION)


@pytest.fixture(scope="module")
def templates() -> ModuleType:
    return _load("bf_template_verifier", _TEMPLATES)


def _proc(returncode: int | None, output: str, *, timed_out: bool = False) -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=output, stderr="", timed_out=timed_out)


class TestClassifyResultEffectivePass:
    """变异体分类：rc==0 只有含真实通过才是 survived。"""

    def test_rc0_with_real_pass_is_survived(self, tool: ModuleType) -> None:
        outcome, reason = tool.classify_result(0, False, "1 passed in 0.01s")
        assert outcome == "survived"
        assert reason == ""

    def test_rc0_with_partial_skip_still_survived(self, tool: ModuleType) -> None:
        outcome, _ = tool.classify_result(0, False, "3 passed, 2 skipped in 0.02s")
        assert outcome == "survived"

    def test_rc0_all_skip_is_invalid_not_survived(self, tool: ModuleType) -> None:
        outcome, reason = tool.classify_result(0, False, "2 skipped in 0.01s")
        assert outcome == "invalid"
        assert "no_effective_pass" in reason
        assert "skipped" in reason

    def test_rc0_xfail_only_is_invalid(self, tool: ModuleType) -> None:
        outcome, reason = tool.classify_result(0, False, "1 xfailed in 0.01s")
        assert outcome == "invalid"
        assert "no_effective_pass" in reason

    def test_rc0_empty_output_is_invalid(self, tool: ModuleType) -> None:
        outcome, reason = tool.classify_result(0, False, "")
        assert outcome == "invalid"
        assert "no_effective_pass" in reason

    def test_rc0_deselected_only_is_invalid(self, tool: ModuleType) -> None:
        outcome, reason = tool.classify_result(0, False, "4 deselected in 0.01s")
        assert outcome == "invalid"
        assert "no_effective_pass" in reason

    def test_rc1_remains_killed(self, tool: ModuleType) -> None:
        outcome, _ = tool.classify_result(1, False, "1 failed in 0.01s")
        assert outcome == "killed"

    def test_timeout_wins_over_effective_pass(self, tool: ModuleType) -> None:
        outcome, _ = tool.classify_result(0, True, "1 passed in 0.01s")
        assert outcome == "timeout"


class TestPreflightEffectivePass:
    """基线门：全 skip 的 rc==0 不是绿基线。"""

    def _plan(self, tool: ModuleType) -> object:
        return tool.ModulePlan(
            module="src/utils/example.py",
            source_sha256="a" * 64,
            total_generated=1,
            test_files=("tests/test_example.py",),
            mutants=(),
        )

    def _run(
        self, tool: ModuleType, monkeypatch: pytest.MonkeyPatch, proc: SimpleNamespace, *, allow_red: bool
    ) -> dict:
        class FakeSandbox:
            def run_tests(self, test_files: object, command_template: object, timeout: float) -> SimpleNamespace:
                return proc

            def close(self) -> None:
                return None

        monkeypatch.setattr(tool.Sandbox, "create", classmethod(lambda cls, *a, **k: FakeSandbox()))
        return tool._run_preflight(
            [self._plan(tool)],
            sandbox_base=Path("/tmp/bf-preflight"),
            repo_root=_REPO_ROOT,
            command_template=tool.DEFAULT_TEST_COMMAND,
            timeout=5.0,
            allow_red_baseline=allow_red,
            quiet=True,
        )

    def test_all_skip_baseline_is_not_green(self, tool: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        reports = self._run(tool, monkeypatch, _proc(0, "2 skipped in 0.01s"), allow_red=True)
        report = reports["src/utils/example.py"]
        assert report["green"] is False
        assert report["reason"] == "baseline_no_effective_pass"
        assert "skipped" in report["output_tail"]

    def test_all_skip_baseline_blocks_by_default(self, tool: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        with pytest.raises(tool.SelfMutationError) as excinfo:
            self._run(tool, monkeypatch, _proc(0, "2 skipped in 0.01s"), allow_red=False)
        assert "有效通过" in str(excinfo.value)

    def test_real_pass_baseline_is_green(self, tool: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        reports = self._run(tool, monkeypatch, _proc(0, "5 passed in 0.01s"), allow_red=False)
        assert reports["src/utils/example.py"]["green"] is True
        assert reports["src/utils/example.py"]["reason"] == ""

    def test_rc1_baseline_reason_unchanged(self, tool: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        reports = self._run(tool, monkeypatch, _proc(1, "1 failed in 0.01s"), allow_red=True)
        assert reports["src/utils/example.py"]["green"] is False
        assert reports["src/utils/example.py"]["reason"] == "baseline_not_green"


class TestSingleMutantEffectivePass:
    """单变异体执行：全 skip 的 rc==0 不能记 survived。"""

    def _run(self, tool: ModuleType, monkeypatch: pytest.MonkeyPatch, proc: SimpleNamespace) -> object:
        class FakeSandbox:
            def apply_mutant(self, module_rel: str, code: str) -> None:
                return None

            def restore_module(self, module_rel: str) -> None:
                return None

            def run_tests(self, test_files: object, command_template: object, timeout: float) -> SimpleNamespace:
                return proc

        mutant = tool.Mutant(code="x = 1\n", mutant_type="arith", description="d", line_no=1)
        return tool._run_single_mutant(
            FakeSandbox(),
            "src/utils/example.py",
            mutant,
            test_files=("tests/test_example.py",),
            command_template=tool.DEFAULT_TEST_COMMAND,
            timeout=5.0,
        )

    def test_all_skip_mutant_is_invalid_with_tail(self, tool: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        outcome = self._run(tool, monkeypatch, _proc(0, "2 skipped in 0.01s"))
        assert outcome.outcome == "invalid"
        assert "no_effective_pass" in outcome.reason
        assert "skipped" in outcome.output_tail

    def test_real_pass_mutant_is_survived(self, tool: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        outcome = self._run(tool, monkeypatch, _proc(0, "4 passed in 0.01s"))
        assert outcome.outcome == "survived"

    def test_kill_is_unchanged(self, tool: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        outcome = self._run(tool, monkeypatch, _proc(1, "1 failed in 0.01s"))
        assert outcome.outcome == "killed"


class TestTemplateEffectivePass:
    """模板自验证：fixed 侧 rc==0 必须含真实通过。"""

    def _template(self) -> dict:
        return {
            "name": "t",
            "test_cases": "def test_one():\n    assert True\n",
            "total_tests": 1,
            "template": "def f():\n    return 1\n",
            "fixed": "def f():\n    return 2\n",
        }

    def _run(self, templates: ModuleType, monkeypatch: pytest.MonkeyPatch, results: list[tuple[int, str]]) -> list[str]:
        calls = iter(results)
        monkeypatch.setattr(templates, "_run_pytest", lambda cwd: next(calls))
        return templates.verify_template(self._template())

    def test_buggy_red_fixed_green_is_clean(self, templates: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._run(templates, monkeypatch, [(1, "1 failed in 0.01s"), (0, "1 passed in 0.01s")]) == []

    def test_fixed_all_skip_is_reported(self, templates: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        problems = self._run(templates, monkeypatch, [(1, "1 failed in 0.01s"), (0, "1 skipped in 0.01s")])
        assert len(problems) == 1
        assert "无有效通过" in problems[0]

    def test_buggy_all_skip_is_not_green(self, templates: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        problems = self._run(templates, monkeypatch, [(0, "1 skipped in 0.01s"), (0, "1 passed in 0.01s")])
        assert len(problems) == 1
        assert "无有效通过" in problems[0]

    def test_buggy_real_green_is_still_reported(self, templates: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        problems = self._run(templates, monkeypatch, [(0, "1 passed in 0.01s"), (0, "1 passed in 0.01s")])
        assert len(problems) == 1
        assert "全绿" in problems[0]

    def test_fixed_red_message_unchanged(self, templates: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        problems = self._run(templates, monkeypatch, [(1, "1 failed in 0.01s"), (1, "1 failed in 0.01s")])
        assert len(problems) == 1
        assert "gold 材料不自洽" in problems[0]
