"""tests for scripts/tools/self_mutation.py（WP-A 自身变异测试驱动器）。

覆盖口径（与 scripts/tools/self_mutation.py 的模块 docstring 一一对应）：
- 变异生成/等距抽样：数量上限、确定性、ID 跨 run 稳定；
- rc 分类：rc==1 kill / rc==0 survive / rc==2/3/4/5/超时 invalid（不进分母）；
- 报告 schema：逐模块计数、有效分母、invalid 单列、baseline_green/measurement_valid；
- 临时副本隔离：变异只写副本、还原逐字节、工作树零改动；
- 沙箱端到端：假仓库上绿基线 → 变异体被杀死 → 还原后再回绿（唯一子进程用例）；
- CLI：默认值、参数校验、互斥组（--dry-run/--fail-under、-q/-v）。

纪律：不在单测里跑真实 3 模块变异批次（那是 experiments/results 的实测工件）；
唯一的子进程是"假仓库沙箱内 3 次极小 pytest 运行"，秒级、确定性、零 LLM/零网络。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "tools" / "self_mutation.py"


def _load_tool() -> ModuleType:
    """按文件路径加载脚本模块（scripts/ 不是包，与仓内既有测试口径一致）。"""
    spec = importlib.util.spec_from_file_location("self_mutation_tool", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass 装饰器需要模块在 sys.modules 中可见（否则 repr/转发解析报错）
    sys.modules["self_mutation_tool"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool() -> ModuleType:
    """模块级 fixture：全文件只 exec 一次脚本。"""
    return _load_tool()


def _sample_mutants(tool: ModuleType, count: int) -> list[object]:
    """构造 count 个合成变异体（行号/类型交错，供抽样测试用）。"""
    return [
        tool.Mutant(
            code=f"value = {index}\n",
            mutant_type=("nearby" if index % 2 else "arith"),
            description=f"合成变异体 {index}",
            line_no=index // 2,
        )
        for index in range(count)
    ]


def _make_record(tool: ModuleType, outcome: str, *, index: int = 0, mutant_type: str = "stmt_delete") -> object:
    """构造一条合成执行记录（报告汇总测试用）。"""
    return tool.MutantOutcome(
        mutant_id=f"module:{index:04d}",
        module="src/utils/example.py",
        mutant_type=mutant_type,
        line_no=index,
        description=f"合成记录 {index}",
        code_sha256=f"sha{index}",
        outcome=outcome,
        returncode=0 if outcome == "survived" else 1,
        duration_s=0.1,
    )


def _make_report(tool: ModuleType) -> dict:
    """构造一份包含 killed/survived/invalid/timeout 的最小报告。"""
    mutants = _sample_mutants(tool, 3)
    plan = tool.ModulePlan(
        module="src/utils/example.py",
        source_sha256="a" * 64,
        total_generated=4,
        test_files=("tests/test_example.py",),
        mutants=tuple(mutants),
    )
    records = [
        _make_record(tool, "killed", index=0),
        _make_record(tool, "survived", index=1),
        _make_record(tool, "invalid", index=2),
        _make_record(tool, "timeout", index=3),
    ]
    module_report = tool.summarize_module(plan, records, {"green": True, "returncode": 0, "duration_s": 0.5})
    return tool.build_report(
        module_reports=[module_report],
        plans=[plan],
        config={"allow_red_baseline": False, "command": "python scripts/tools/self_mutation.py"},
        environment={"hostname": "host", "platform": "test-platform", "cpu_count": 8, "python_version": "3.14.6"},
        git={"sha": "0" * 40, "dirty": False, "dirty_files": 0},
        mode="execute",
        duration_s=1.5,
        generated_at="2026-10-17T00:00:00+0800",
    )


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """最小可运行仓库：src/foo.py + tests/test_foo.py + 最小 pytest 配置。"""
    repo = tmp_path / "fake_repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "foo.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (repo / "config.py").write_text("# 假仓库占位配置\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "conftest.py").write_text("# 假仓库占位 conftest\n", encoding="utf-8")
    (repo / "tests" / "test_foo.py").write_text(
        "from src.foo import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    return repo


# ─── CLI：默认值 / 参数校验 / 互斥组 ────────────────────────────────────────


def test_help_exits_zero(tool: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    """--help 必须可跑且退出码 0（验收项：脚本可跑）。"""
    with pytest.raises(SystemExit) as excinfo:
        tool._parse_args(["--help"])
    assert excinfo.value.code == 0
    assert "--files" in capsys.readouterr().out


def test_cli_defaults(tool: ModuleType) -> None:
    """默认值锁定：2 worker / 每文件 120 变异体 / 无阈值。"""
    args = tool._parse_args([])
    assert args.workers == 2
    assert args.max_mutants == 120
    assert args.timeout_per_mutant == 60.0
    assert args.fail_under is None
    assert args.files == ",".join(tool.DEFAULT_MODULES)


@pytest.mark.parametrize(
    "argv",
    [
        ["--dry-run", "--fail-under", "0.5"],
        ["-q", "-v"],
    ],
)
def test_cli_mutually_exclusive_pairs(tool: ModuleType, argv: list[str]) -> None:
    """互斥组：--dry-run/--fail-under（无分数可判）与 -q/-v（输出口径唯一）。"""
    with pytest.raises(SystemExit) as excinfo:
        tool._parse_args(argv)
    assert excinfo.value.code == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["--workers", "0"],
        ["--workers", "9"],
        ["--max-mutants", "-1"],
        ["--timeout-per-mutant", "0"],
        ["--test-command", "{python} -m pytest"],
        ["--files", " "],
    ],
)
def test_cli_rejects_invalid_args(tool: ModuleType, argv: list[str]) -> None:
    """非法参数必须 argparse error（退出码 2），不允许静默接受。"""
    with pytest.raises(SystemExit) as excinfo:
        tool._parse_args(argv)
    assert excinfo.value.code == 2


# ─── 变异生成 / 抽样 / ID ───────────────────────────────────────────────────


def test_sample_mutants_caps_and_determinism(tool: ModuleType) -> None:
    """抽样数量受 cap 约束，且同一输入两次抽样结果逐项一致（无随机种子）。"""
    mutants = _sample_mutants(tool, 50)
    sampled = list(tool.sample_mutants(mutants, 10))
    assert len(sampled) == 10
    assert sampled == list(tool.sample_mutants(mutants, 10))
    assert len({id(mutant) for mutant in sampled}) == 10


def test_sample_mutants_zero_means_full(tool: ModuleType) -> None:
    """cap=0 表示全量；不足上限时也全量返回（不补齐、不截断）。"""
    mutants = _sample_mutants(tool, 17)
    assert list(tool.sample_mutants(mutants, 0)) == list(mutants)
    assert list(tool.sample_mutants(mutants, 100)) == list(mutants)
    assert len(tool.sample_mutants(mutants, 1)) == 1


def test_filter_generator_invalid_mutants(tool: ModuleType) -> None:
    """生成器假变异体必须在抽样前剔除：语义恒等（重排版）与语法非法两类。

    背景（2026-10-17 实测）：`_generate_numeric_offset` 对 Compare 中的非数值
    常量（None/字符串）登记"const None → +1"但实际未改任何节点；`_gen_subscript_negate`
    对 helpers 产出语法非法代码。两者都是生成器缺陷，不是"测试弱"的证据。
    """
    source = "def f(x):\n    if x is None:\n        return 1\n    return 2\n"
    identity = tool.Mutant(
        code=source,  # ast.unparse 重排版后与源码 AST 逐节点相同
        mutant_type="numeric_offset",
        description="line 2: const None → +1（实际未变异）",
        line_no=2,
    )
    syntax_error = tool.Mutant(
        code="def f(x):\n    return [-:x]\n",
        mutant_type="subscript_negate",
        description="语法非法变异体",
        line_no=2,
    )
    real = tool.Mutant(
        code="def f(x):\n    if x is None:\n        return 1\n    return 3\n",
        mutant_type="numeric_offset",
        description="真实变异",
        line_no=4,
    )
    kept, filtered = tool.filter_generator_invalid_mutants(source, [identity, syntax_error, real])
    assert kept == [real]
    assert filtered == {"identity": 1, "syntax_error": 1}


def test_filter_generator_invalid_keeps_real_mutants(tool: ModuleType) -> None:
    """无假变异体时一个不少（过滤不能误伤真实变异）。"""
    source = "x = 1\n"
    real = tool.Mutant(code="x = 2\n", mutant_type="numeric_offset", description="真实变异", line_no=1)
    kept, filtered = tool.filter_generator_invalid_mutants(source, [real])
    assert kept == [real]
    assert filtered == {"identity": 0, "syntax_error": 0}


def test_mutant_id_is_content_stable(tool: ModuleType) -> None:
    """变异体 ID 由内容哈希决定：同内容同 ID、异内容异 ID（before/after 可对账）。"""
    first = tool.Mutant(code="x = 1\n", mutant_type="t", description="d", line_no=1)
    same = tool.Mutant(code="x = 1\n", mutant_type="t", description="d2", line_no=9)
    other = tool.Mutant(code="x = 2\n", mutant_type="t", description="d", line_no=1)
    assert tool._mutant_id("mod", first) == tool._mutant_id("mod", same)
    assert tool._mutant_id("mod", first) != tool._mutant_id("mod", other)


def test_dry_run_records_are_not_run(tool: ModuleType) -> None:
    """dry-run 只登记清单：outcome=not_run，绝无 killed/survived。"""
    mutants = _sample_mutants(tool, 3)
    plan = tool.ModulePlan(
        module="src/utils/example.py",
        source_sha256="b" * 64,
        total_generated=3,
        test_files=("tests/test_example.py",),
        mutants=tuple(mutants),
    )
    records = tool._dry_run_records([plan])
    assert len(records) == 3
    assert {record.outcome for record in records} == {"not_run"}


# ─── 结果分类 ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("returncode", "timed_out", "expected"),
    [
        (0, False, "survived"),
        (1, False, "killed"),
        (2, False, "invalid"),
        (3, False, "invalid"),
        (4, False, "invalid"),
        (5, False, "invalid"),
        (None, False, "invalid"),
        (-9, False, "invalid"),
        (1, True, "timeout"),
        (0, True, "timeout"),
        (2, True, "timeout"),
    ],
)
def test_classify_result_matrix(tool: ModuleType, returncode: int | None, timed_out: bool, expected: str) -> None:
    """rc 分类矩阵：只有 0/1 进分母，收集错误/超时一律 invalid（防虚增/虚减）。"""
    outcome, reason = tool.classify_result(returncode, timed_out)
    assert outcome == expected
    if expected == "invalid":
        assert reason, "invalid 必须带归因原因"
    if expected in {"killed", "survived"}:
        assert reason == ""


def test_classify_invalid_reason_mentions_collection_failure(tool: ModuleType) -> None:
    """rc==2 的归因必须点名收集错误（否则 invalid 无法与"测试弱"区分）。"""
    _, reason = tool.classify_result(2, False)
    assert "collection" in reason


# ─── 测试命令构造 ───────────────────────────────────────────────────────────


def test_build_test_command_expands_placeholders(tool: ModuleType) -> None:
    """含空格的解释器路径必须是单个 argv 元素（不经过 shell 分词）。"""
    argv = tool.build_test_command(
        "{python} -m pytest {test_files} -q",
        "/tmp/py with space/python",
        ["tests/a.py", "tests/b.py"],
    )
    assert argv == ["/tmp/py with space/python", "-m", "pytest", "tests/a.py", "tests/b.py", "-q"]


def test_build_test_command_requires_test_files_placeholder(tool: ModuleType) -> None:
    """模板缺 {test_files} 属于可预期用法错误（否则被测集合会被静默忽略）。"""
    with pytest.raises(tool.SelfMutationError):
        tool.build_test_command("{python} -m pytest -q", "python", [])


def test_build_test_command_rejects_unknown_placeholder(tool: ModuleType) -> None:
    """未知占位符不得静默留字面量进命令行。"""
    with pytest.raises(tool.SelfMutationError):
        tool.build_test_command("{python} {unknown} {test_files}", "python", ["tests/a.py"])


# ─── 测试集合发现 / --test-map ──────────────────────────────────────────────


def test_discover_test_files_exact_convention(tool: ModuleType) -> None:
    """精确命名 tests/test_<stem>.py 优先命中。"""
    assert tool.discover_test_files("src/utils/atomic_io.py") == ["tests/test_atomic_io.py"]


def test_discover_test_files_family_convention(tool: ModuleType) -> None:
    """无精确文件时按前缀族发现（helpers 的 json property/robustness 等）。"""
    found = tool.discover_test_files("src/utils/helpers.py")
    assert "tests/test_helpers_json_property.py" in found
    assert "tests/test_helpers_json_robustness.py" in found
    assert all(path.startswith("tests/test_helpers_") for path in found)


def test_discover_test_files_returns_empty_for_unknown(tool: ModuleType, tmp_path: Path) -> None:
    """无专属测试时返回空（调用方要求显式 --test-map，不瞎猜全会话套件）。"""
    (tmp_path / "tests").mkdir()
    assert tool.discover_test_files("src/whatever.py", repo_root=tmp_path) == []


def test_parse_test_map_freezes_test_set(tool: ModuleType) -> None:
    """--test-map 可把模块绑定到显式测试集合（before/after 可比性前提）。"""
    mapping = tool.parse_test_map(
        ["src/utils/atomic_io.py=tests/test_atomic_io.py,tests/test_process_utils.py"],
        ["src/utils/atomic_io.py"],
    )
    assert mapping == {
        "src/utils/atomic_io.py": ("tests/test_atomic_io.py", "tests/test_process_utils.py"),
    }


def test_parse_test_map_rejects_unknown_module(tool: ModuleType) -> None:
    """--test-map 指向未在 --files 中的模块必须报错。"""
    with pytest.raises(tool.SelfMutationError):
        tool.parse_test_map(["src/utils/env_utils.py=tests/test_env_utils.py"], ["src/utils/atomic_io.py"])


def test_parse_test_map_rejects_bad_format(tool: ModuleType) -> None:
    """缺 '=' 的映射项必须报错（不做模糊猜测）。"""
    with pytest.raises(tool.SelfMutationError):
        tool.parse_test_map(["no-equals-sign"], ["src/utils/atomic_io.py"])


def test_repo_relative_rejects_paths_outside_repo(tool: ModuleType, tmp_path: Path) -> None:
    """仓外路径无法映射进沙箱副本，必须显式报错而不是静默降级。"""
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(tool.SelfMutationError):
        tool._repo_relative(str(outside))
    with pytest.raises(tool.SelfMutationError):
        tool._repo_relative("src/utils/not_exists_self_mutation.py")


# ─── 汇总 / 报告 schema ─────────────────────────────────────────────────────


def test_summarize_excludes_invalid_from_denominator(tool: ModuleType) -> None:
    """mutation score 分母只含 killed+survived；invalid/timeout 单列。"""
    records = [
        _make_record(tool, "killed", index=0),
        _make_record(tool, "survived", index=1),
        _make_record(tool, "invalid", index=2),
        _make_record(tool, "timeout", index=3),
    ]
    summary = tool._summarize_records(records)
    assert (summary["killed"], summary["survived"], summary["invalid"], summary["timeout"]) == (1, 1, 1, 1)
    assert summary["valid_denominator"] == 2
    assert summary["mutation_score"] == 0.5


def test_summarize_all_invalid_has_no_score(tool: ModuleType) -> None:
    """无有效样本时 score=None（绝不用 0 冒充"分数为 0"）。"""
    summary = tool._summarize_records([_make_record(tool, "invalid", index=0)])
    assert summary["valid_denominator"] == 0
    assert summary["mutation_score"] is None


def test_summarize_by_type_keeps_type_dimension(tool: ModuleType) -> None:
    """按算子类型汇总保留类型维度（定位"哪类算子总能/从不能被杀死"）。"""
    records = [
        _make_record(tool, "killed", index=0, mutant_type="stmt_delete"),
        _make_record(tool, "survived", index=1, mutant_type="stmt_delete"),
        _make_record(tool, "killed", index=2, mutant_type="const_swap"),
    ]
    by_type = tool._summarize_by_type(records)
    assert by_type["stmt_delete"]["mutation_score"] == 0.5
    assert by_type["const_swap"]["mutation_score"] == 1.0


def test_build_report_schema_and_totals(tool: ModuleType) -> None:
    """报告 schema：必备键齐全、总量由逐模块记录复算、JSON 可序列化。"""
    report = _make_report(tool)
    assert report["schema_version"] == tool._SCHEMA_VERSION
    for key in ("tool", "mode", "generated_at", "environment", "git", "config", "summary", "modules"):
        assert key in report
    summary = report["summary"]
    assert summary["sampled_mutants"] == 4
    assert (summary["killed"], summary["survived"], summary["invalid"], summary["timeout"]) == (1, 1, 1, 1)
    assert summary["valid_denominator"] == 2
    assert summary["mutation_score"] == 0.5
    assert summary["baseline_green"] is True
    assert summary["measurement_valid"] is True
    assert summary["generator_filtered_identity"] == 0
    assert summary["generator_filtered_syntax_error"] == 0
    assert summary["executable_pool"] == 4
    module_report = report["modules"][0]
    assert module_report["generator_filtered"] == {"identity": 0, "syntax_error": 0}
    assert module_report["executable_pool"] == 4
    assert isinstance(json.dumps(report, ensure_ascii=False), str)


def test_build_report_marks_red_baseline_invalid_measurement(tool: ModuleType) -> None:
    """红基线 + 未放行 → measurement_valid=False（分数不可作结论）。"""
    report = _make_report(tool)
    report["modules"][0]["baseline"]["green"] = False
    report = tool.build_report(
        module_reports=report["modules"],
        plans=[
            tool.ModulePlan(
                module="src/utils/example.py",
                source_sha256="a" * 64,
                total_generated=4,
                test_files=("tests/test_example.py",),
                mutants=(),
            )
        ],
        config={"allow_red_baseline": False},
        environment={},
        git={},
        mode="execute",
        duration_s=1.0,
        generated_at="2026-10-17T00:00:00+0800",
    )
    assert report["summary"]["baseline_green"] is False
    assert report["summary"]["measurement_valid"] is False


def test_render_markdown_contains_core_sections(tool: ModuleType) -> None:
    """Markdown 必须含总览表/分数/存活清单/复现命令（人读版可独立使用）。"""
    markdown = tool.render_markdown(_make_report(tool))
    assert "# 自身测试套件变异测试报告" in markdown
    assert "mutation score = killed / (killed + survived)" in markdown
    assert "`src/utils/example.py`" in markdown
    assert "0.5000" in markdown
    assert "## 复现命令" in markdown
    assert "python scripts/tools/self_mutation.py" in markdown


# ─── 临时副本隔离 ───────────────────────────────────────────────────────────


def test_sandbox_isolation_never_touches_repo(tool: ModuleType, fake_repo: Path, tmp_path: Path) -> None:
    """变异只写副本；还原逐字节；工作树原文件全程不变（核心安全契约）。"""
    original = (fake_repo / "src" / "foo.py").read_text(encoding="utf-8")
    sandbox = tool.Sandbox.create(
        tmp_path / "sandbox" / "worker-0",
        fake_repo,
        module_paths=["src/foo.py"],
        test_files=["tests/test_foo.py"],
    )
    try:
        sandbox.apply_mutant("src/foo.py", "def add(a, b):\n    return a - b\n")
        assert "a - b" in (sandbox.root / "src" / "foo.py").read_text(encoding="utf-8")
        assert (fake_repo / "src" / "foo.py").read_text(encoding="utf-8") == original
        sandbox.restore_module("src/foo.py")
        assert (sandbox.root / "src" / "foo.py").read_text(encoding="utf-8") == original
        assert sandbox.env["PYTHONPATH"] == str(sandbox.root)
        assert "PYTEST_CURRENT_TEST" not in sandbox.env
        assert "PYTHONDONTWRITEBYTECODE" in sandbox.env
        assert (sandbox.root / "tests" / "conftest.py").is_file()
        assert (sandbox.root / "pyproject.toml").is_file()
    finally:
        sandbox.close()
    assert not sandbox.root.exists()


def test_sandbox_end_to_end_kill_restore_survive(tool: ModuleType, fake_repo: Path, tmp_path: Path) -> None:
    """端到端：未变异绿 → 变异体 rc=1(killed) → 还原后回绿（锁 run/restore 闭环）。"""
    sandbox = tool.Sandbox.create(
        tmp_path / "e2e" / "worker-0",
        fake_repo,
        module_paths=["src/foo.py"],
        test_files=["tests/test_foo.py"],
    )
    try:
        pristine = sandbox.run_tests(["tests/test_foo.py"], tool.DEFAULT_TEST_COMMAND, timeout=120)
        assert pristine.returncode == 0, f"假仓库绿基线失败: {pristine.stderr[-500:]}"
        sandbox.apply_mutant("src/foo.py", "def add(a, b):\n    return a - b\n")
        try:
            killed = sandbox.run_tests(["tests/test_foo.py"], tool.DEFAULT_TEST_COMMAND, timeout=120)
        finally:
            sandbox.restore_module("src/foo.py")
        assert tool.classify_result(killed.returncode, killed.timed_out)[0] == "killed"
        restored = sandbox.run_tests(["tests/test_foo.py"], tool.DEFAULT_TEST_COMMAND, timeout=120)
        assert restored.returncode == 0
    finally:
        sandbox.close()


# ─── main() dry-run 集成 ────────────────────────────────────────────────────


def test_main_dry_run_writes_reports(tool: ModuleType, tmp_path: Path) -> None:
    """dry-run 走完 main 全链路：退出码 0、JSON/Markdown 落盘、inventory 自洽。"""
    json_out = tmp_path / "report.json"
    md_out = tmp_path / "report.md"
    rc = tool.main(
        [
            "--dry-run",
            "--files",
            "src/utils/atomic_io.py",
            "--json-out",
            str(json_out),
            "--md-out",
            str(md_out),
            "-q",
        ]
    )
    assert rc == 0
    report = json.loads(json_out.read_text(encoding="utf-8"))
    assert report["mode"] == "dry_run"
    module_report = report["modules"][0]
    assert module_report["sampled_mutants"] == len(module_report["mutants"]) > 0
    assert module_report["executable_pool"] == module_report["total_generated_mutants"] - sum(
        module_report["generator_filtered"].values()
    )
    assert report["summary"]["not_run"] == module_report["sampled_mutants"]
    assert report["summary"]["mutation_score"] is None
    assert md_out.is_file()
