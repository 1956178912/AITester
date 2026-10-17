"""H2 收口回归锁：所有「子进程里再跑 pytest」的站点都必须走 ``nested_pytest_env``。

背景（`docs/PROJECT_STATUS_REGISTER.md` §3.2 H2 / §4）
----------------------------------------------------
历史写法 ``env={**os.environ, "PYTHONPATH": tmpdir, ...}`` 把宿主环境整体继承、
同时把 ``PYTHONPATH`` 覆盖成 tmpdir。宿主若设了 ``PYTEST_PLUGINS``（插件在宿主
sys.path 上、不在 tmpdir 上），嵌套 pytest 会在**收集之前** ImportError 退出
rc=1；判分链路把这次 rc=1 读成「测试红」，于是 specificity 裁决得出与被测代码
无关的结论（H2 实测复现，详见 ``src/utils/process_utils.py::nested_pytest_env``
文档串）。

修复路径：``nested_pytest_env(**overrides)`` 先剔除宿主 pytest 配置键
（``PYTEST_PLUGINS`` / ``PYTEST_ADDOPTS``），再叠加显式 overrides。H 轮修了
2/7 处，K 轮 8d4f35c「运行期卫生」把剩余 5 处 / 4 个冻结实验文件收敛完毕
（逐文件 ``git log -S nested_pytest_env`` 可复核），本文件是 L 轮补的**独立
回归锁**——防止未来把该模式改回裸 ``os.environ``。

三层锁（全部零 LLM / 零网络 / 确定性）：

1. **逐站点静态锁**：5 处历史站点 + 2 处 H 轮参考接线逐函数解析 AST，断言 env
   构造引用 ``nested_pytest_env``、无 ``os.environ`` 直传/局部变量数据流回退，
   且 override 键集合与 ``PYTHONPATH`` 覆盖语义被钉死（含 emse 两处「自写插件
   物化进 tmpdir 靠 ``PYTHONPATH`` 加载」的语义）；
2. **仓库面扫描**：``experiments/`` 与 ``src/`` 内任何 pytest 子进程调用都不得
   就地展开 ``os.environ``（含「先赋局部变量再传入」的隐蔽写法）；
3. **行为合约**：干净环境下新 env 与历史 ``{**os.environ, **overrides}`` 逐位
   等价（差分只允许剔除宿主 pytest 配置键）；宿主注入不可导入的
   ``PYTEST_PLUGINS`` 时旧写法 rc≠0 / 新写法 rc=0，并对**真实站点函数**
   （gold 剪枝 ``_run_suite``、testlevel ``run_side``）做最小化端到端调用。
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

from src.utils.process_utils import nested_pytest_env, run_with_timeout

_REPO_ROOT = Path(__file__).resolve().parents[1]

# 任务口径的 5 处历史站点（H2 遗留；K 轮 8d4f35c 已收敛）：(文件, 函数名)。
_H2_SITES: tuple[tuple[str, str], ...] = (
    ("experiments/gold_consistency_pruning.py", "_run_suite"),
    ("experiments/mutation_testing.py", "_run_mutant_tests"),
    ("experiments/suite_repair_pipeline.py", "_runs_green_on"),
    ("experiments/emse_testlevel_detection.py", "run_side"),
    ("experiments/emse_testlevel_detection.py", "independent_check"),
)

# H 轮已修的 2/7 处参考接线：一并锁进本文件，使「7/7 面」都由同一回归锁覆盖。
_REFERENCE_SITES: tuple[tuple[str, str], ...] = (
    ("experiments/_m1_metrics.py", "_run_pytest_in_tmp"),
    ("src/measurement/mdo.py", "_run_tests_on_code"),
)

# 逐站点 override 键集合（语义钉死：改键 = 改测量口径，必须显式评审）。
_EXPECTED_OVERRIDE_KEYS: dict[tuple[str, str], set[str]] = {
    ("experiments/gold_consistency_pruning.py", "_run_suite"): {"PYTHONDONTWRITEBYTECODE", "PYTHONPATH"},
    ("experiments/mutation_testing.py", "_run_mutant_tests"): {"PYTHONPATH"},
    ("experiments/suite_repair_pipeline.py", "_runs_green_on"): {"PYTHONDONTWRITEBYTECODE", "PYTHONPATH"},
    ("experiments/emse_testlevel_detection.py", "run_side"): {
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONHASHSEED",
        "PYTHONPATH",
        "DSH_OUTCOME_JSONL",
        "COLUMNS",
    },
    ("experiments/emse_testlevel_detection.py", "independent_check"): {
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONPATH",
        "COLUMNS",
    },
    ("experiments/_m1_metrics.py", "_run_pytest_in_tmp"): {"PYTHONDONTWRITEBYTECODE", "PYTHONPATH"},
    ("src/measurement/mdo.py", "_run_tests_on_code"): {"PYTHONDONTWRITEBYTECODE", "PYTHONPATH"},
}

_HOST_PYTEST_KEYS = frozenset(("PYTEST_PLUGINS", "PYTEST_ADDOPTS"))

_TRIVIAL_TARGET = "def f():\n    return 1\n"
_TRIVIAL_TEST = "from m import f\n\n\ndef test_ok() -> None:\n    assert f() == 1\n"


# ────────────────────────────── AST 静态分析工具 ──────────────────────────────


def _parse(rel_path: str) -> ast.Module:
    """解析仓库根相对路径的 Python 文件为 AST。"""
    return ast.parse((_REPO_ROOT / rel_path).read_text(encoding="utf-8"))


def _function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    """取模块内指定名字的函数定义（测试文件里同名工具函数不算）。"""
    matches = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    assert matches, f"函数 {name!r} 不在模块中（站点行号漂移时请同步本文件）"
    assert len(matches) == 1, f"函数 {name!r} 出现 {len(matches)} 次，无法唯一定位"
    return matches[0]


def _nested_pytest_env_calls(func: ast.FunctionDef) -> list[ast.Call]:
    """函数体内对 ``nested_pytest_env(...)`` 的调用节点。"""
    return [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "nested_pytest_env"
    ]


def _env_override_keys(func: ast.FunctionDef) -> set[str]:
    """函数内所有 ``nested_pytest_env`` 调用的关键字 override 名集合。"""
    keys: set[str] = set()
    for call in _nested_pytest_env_calls(func):
        keys.update(kw.arg for kw in call.keywords if kw.arg is not None)
    return keys


def _materialized_overrides(func: ast.FunctionDef) -> dict[str, str]:
    """把站点里的 override 键物化成确定性的测试值（值本身不影响等价性断言）。"""
    out: dict[str, str] = {}
    for call in _nested_pytest_env_calls(func):
        for kw in call.keywords:
            if kw.arg is None:
                continue
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                out[kw.arg] = kw.value.value
            else:
                out[kw.arg] = f"/tmp/l_round_{kw.arg.lower()}"
    return out


def _resolve_local_env_source(call: ast.Call, enclosing: ast.FunctionDef) -> str | None:
    """解析 ``env=`` 实参的表达式源码；``env=env`` 形式回溯同函数内最近赋值。

    历史缺陷可能被写成「先 ``env = {**os.environ, ...}`` 再 ``env=env`` 传入」，
    只看调用点字面量会漏报——这里做一层函数内数据流回溯（不为完整数据流分析，
    只覆盖 H2 缺陷形态所需的「同函数内局部变量别名」）。
    """
    env_kw = next((kw for kw in call.keywords if kw.arg == "env"), None)
    if env_kw is None:
        return None
    if isinstance(env_kw.value, ast.Name):
        best: ast.Assign | None = None
        for node in ast.walk(enclosing):
            if not isinstance(node, ast.Assign) or node.lineno >= call.lineno:
                continue
            if not any(isinstance(t, ast.Name) and t.id == env_kw.value.id for t in node.targets):
                continue
            if best is None or node.lineno > best.lineno:
                best = node
        if best is not None:
            return ast.unparse(best.value)
    return ast.unparse(env_kw.value)


def _is_pytest_spawn_command(expr: ast.expr) -> bool:
    """命令表达式是否为 ``[..., '-m', 'pytest', ...]`` 形态的 pytest 子进程。"""
    if not isinstance(expr, (ast.List, ast.Tuple)):
        return False
    consts = {e.value for e in expr.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return {"-m", "pytest"} <= consts


def _enclosing_function(node: ast.AST, parent: dict[ast.AST, ast.AST]) -> ast.FunctionDef | None:
    """向上找最近一层函数定义。"""
    cur: ast.AST = node
    while cur in parent:
        cur = parent[cur]
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur
    return None


def _raw_environ_pytest_sites() -> list[str]:
    """扫描 experiments/ + src/：pytest 子进程的 env 不得就地展开 ``os.environ``。

    返回违规点列表（空 = 干净）。纯 python 探针（命令无 ``-m pytest``）与
    ``env=None``（不覆盖 PYTHONPATH，宿主插件仍可导入，非 H2 缺陷形态）不在面内。
    """
    offenders: list[str] = []
    for root in ("experiments", "src"):
        for path in (_REPO_ROOT / root).rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover - 非 Python 临时脚本
                continue
            parent: dict[ast.AST, ast.AST] = {}
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    parent[child] = node
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                enclosing = _enclosing_function(node, parent)
                first = node.args[0]
                resolved = first
                if isinstance(first, ast.Name) and enclosing is not None:
                    resolved = _resolve_local_name(first.id, node.lineno, enclosing) or first
                if not _is_pytest_spawn_command(resolved):
                    continue
                env_src = _resolve_local_env_source(node, enclosing) if enclosing is not None else None
                if env_src and "os.environ" in env_src and "nested_pytest_env" not in env_src:
                    offenders.append(f"{path.relative_to(_REPO_ROOT)}:{node.lineno}")
    return offenders


def _resolve_local_name(name: str, before_lineno: int, enclosing: ast.FunctionDef) -> ast.expr | None:
    """同函数内取 ``name`` 在调用前最近一次赋值的右值（命令变量别名解析）。"""
    best: ast.Assign | None = None
    for node in ast.walk(enclosing):
        if not isinstance(node, ast.Assign) or node.lineno >= before_lineno:
            continue
        if not any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            continue
        if best is None or node.lineno > best.lineno:
            best = node
    return best.value if best is not None else None


# ───────────────────────── 1) 逐站点静态回归锁（7/7） ─────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(("rel_path", "func_name"), _H2_SITES, ids=[f"{p.split('/')[-1]}::{f}" for p, f in _H2_SITES])
def test_h2_site_uses_nested_pytest_env(rel_path: str, func_name: str) -> None:
    """H2 5 处历史站点：env 构造必须引用 nested_pytest_env，且无 os.environ 直传。"""
    func = _function_node(_parse(rel_path), func_name)
    source = ast.unparse(func)
    assert _nested_pytest_env_calls(func), f"{rel_path}::{func_name} 未引用 nested_pytest_env（H2 回退）"
    assert "os.environ" not in source, f"{rel_path}::{func_name} 仍直接展开 os.environ（宿主 pytest 配置会污染测量）"
    assert "PYTHONPATH=" in source, f"{rel_path}::{func_name} 必须显式覆盖 PYTHONPATH（tmpdir 导入语义）"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rel_path", "func_name"), _REFERENCE_SITES, ids=[f"{p.split('/')[-1]}::{f}" for p, f in _REFERENCE_SITES]
)
def test_reference_site_uses_nested_pytest_env(rel_path: str, func_name: str) -> None:
    """H 轮已修的 2 处参考接线：同样由本回归锁覆盖（合计 7/7 面）。"""
    func = _function_node(_parse(rel_path), func_name)
    source = ast.unparse(func)
    assert _nested_pytest_env_calls(func), f"{rel_path}::{func_name} 未引用 nested_pytest_env（H2 回退）"
    assert "os.environ" not in source, f"{rel_path}::{func_name} 仍直接展开 os.environ"
    assert "PYTHONPATH=" in source


@pytest.mark.unit
@pytest.mark.parametrize(("rel_path", "func_name"), _H2_SITES, ids=[f"{p.split('/')[-1]}::{f}" for p, f in _H2_SITES])
def test_h2_site_override_keys_are_semantically_pinned(rel_path: str, func_name: str) -> None:
    """override 键集合被钉死：任何增删都改变测量口径，必须显式评审后同步本测试。"""
    func = _function_node(_parse(rel_path), func_name)
    expected = _EXPECTED_OVERRIDE_KEYS[(rel_path, func_name)]
    assert _env_override_keys(func) == expected, (
        f"{rel_path}::{func_name} 的 nested_pytest_env override 键漂移："
        f"期望 {sorted(expected)}，实际 {sorted(_env_override_keys(func))}"
    )


@pytest.mark.unit
def test_emse_plugin_sites_keep_pythonpath_plugin_semantics() -> None:
    """emse 两处把自写插件物化进 tmpdir 靠 PYTHONPATH 加载：收敛后语义必须保留。"""
    module = _parse("experiments/emse_testlevel_detection.py")
    run_side = _function_node(module, "run_side")
    run_side_src = ast.unparse(run_side)
    # 插件文件物化在 tmpdir + `-p _dsh_outcomes` + 记录落盘键
    assert "_dsh_outcomes" in run_side_src
    assert "DSH_OUTCOME_JSONL" in run_side_src
    # PYTHONPATH 必须仍来自 packaged test tree（pythonpath 变量），不能被丢弃
    assert "PYTHONPATH=pythonpath" in run_side_src
    independent = ast.unparse(_function_node(module, "independent_check"))
    assert "PYTHONPATH=pythonpath" in independent
    assert "nested_pytest_env(" in independent


@pytest.mark.unit
@pytest.mark.parametrize(
    "rel_path",
    [
        "experiments/gold_consistency_pruning.py",
        "experiments/mutation_testing.py",
        "experiments/suite_repair_pipeline.py",
        "experiments/emse_testlevel_detection.py",
    ],
)
def test_frozen_experiment_files_have_no_raw_environ_expansion(rel_path: str) -> None:
    """4 个冻结实验文件整体不得再出现 ``**os.environ`` 直传模式（不只 5 个函数）。"""
    text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
    assert "**os.environ" not in text, f"{rel_path} 重新引入了裸 os.environ 展开（H2 回退）"


# ───────────────────────── 2) 仓库面扫描（防隐蔽回退） ─────────────────────────


@pytest.mark.unit
def test_no_pytest_spawn_inherits_host_config_via_raw_environ() -> None:
    """experiments/ + src/ 内 pytest 子进程不得用裸 os.environ 构造 env。

    比 ``tests/test_process_utils.py::TestNoRawEnvAroundNestedPytest`` 多一层
    「同函数内局部变量别名」回溯，防止把 ``env = {**os.environ, ...}`` 先赋变量
    再传入的隐蔽回退绕过守卫。
    """
    offenders = _raw_environ_pytest_sites()
    assert not offenders, f"以下 pytest 子进程仍继承宿主环境（H2 缺陷形态）：{offenders}"


# ─────────────────────── 3) 行为合约：等价性 + 端到端负控 ───────────────────────


@pytest.mark.unit
def test_nested_pytest_env_strips_only_host_pytest_config_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """键集合差分：只剔除 PYTEST_PLUGINS / PYTEST_ADDOPTS，其余键值逐位相同。"""
    monkeypatch.setenv("PYTEST_PLUGINS", "no_such_host_plugin_xyz")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--no-header")
    env = nested_pytest_env()
    removed = set(os.environ) - set(env)
    assert removed == _HOST_PYTEST_KEYS, f"仅允许剔除宿主 pytest 配置键，实际剔除 {sorted(removed)}"
    for key, value in env.items():
        assert os.environ[key] == value


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rel_path", "func_name"),
    _H2_SITES + _REFERENCE_SITES,
    ids=[f"{p.split('/')[-1]}::{f}" for p, f in _H2_SITES + _REFERENCE_SITES],
)
def test_clean_env_is_bitwise_identical_to_legacy_env(
    rel_path: str, func_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """干净环境下，5 站点 + 2 参考站点的新旧 env 逐位等价（零行为变化）。"""
    monkeypatch.delenv("PYTEST_PLUGINS", raising=False)
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    overrides = _materialized_overrides(_function_node(_parse(rel_path), func_name))
    assert overrides, f"{rel_path}::{func_name} 未提取到 override"
    assert nested_pytest_env(**overrides) == {**os.environ, **overrides}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rel_path", "func_name"),
    _H2_SITES + _REFERENCE_SITES,
    ids=[f"{p.split('/')[-1]}::{f}" for p, f in _H2_SITES + _REFERENCE_SITES],
)
def test_poisoned_host_env_diff_is_exactly_pytest_config_keys(
    rel_path: str, func_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """宿主 pytest 配置被污染时，新旧 env 的差分只是两个宿主配置键（其余逐位相同）。"""
    monkeypatch.setenv("PYTEST_PLUGINS", "no_such_host_plugin_xyz")
    monkeypatch.setenv("PYTEST_ADDOPTS", "-p no:cacheprovider")
    monkeypatch.setenv("PATH", os.environ.get("PATH", "/usr/bin:/bin"))
    overrides = _materialized_overrides(_function_node(_parse(rel_path), func_name))
    legacy = {**os.environ, **overrides}
    fixed = nested_pytest_env(**overrides)
    assert set(legacy) - set(fixed) == _HOST_PYTEST_KEYS
    assert set(fixed) - set(legacy) == set()
    for key in fixed:
        assert fixed[key] == legacy[key], f"{key} 值被意外改写"
    for key, value in overrides.items():
        assert fixed[key] == value, f"override {key} 未生效"


def _run_trivial_nested_pytest(tmp_path: Path, env: dict[str, str]) -> int:
    """在 tmp 目录里跑一次最小 pytest，返回 rc（复刻生产嵌套调用形态）。"""
    test_file = tmp_path / "test_min.py"
    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    proc = run_with_timeout(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", str(test_file)],
        timeout=120,
        cwd=str(tmp_path),
        text=True,
        env=env,
    )
    assert proc.timed_out is False
    return int(proc.returncode)


@pytest.mark.unit
def test_legacy_env_breaks_under_unimportable_host_plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """端到端负控（旧写法）：宿主 PYTEST_PLUGINS 不可导入 → 嵌套 pytest 根本没跑起来。"""
    monkeypatch.setenv("PYTEST_PLUGINS", "no_such_host_plugin_xyz")
    legacy_rc = _run_trivial_nested_pytest(tmp_path, {**os.environ, "PYTHONPATH": str(tmp_path)})
    assert legacy_rc != 0, "前提不成立：宿主 PYTEST_PLUGINS 未让旧口径嵌套 pytest 失败"


@pytest.mark.unit
def test_helper_env_survives_unimportable_host_plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """端到端正控（新写法）：同样污染下，nested_pytest_env 让嵌套 pytest 正常通过。"""
    monkeypatch.setenv("PYTEST_PLUGINS", "no_such_host_plugin_xyz")
    fixed_rc = _run_trivial_nested_pytest(tmp_path, nested_pytest_env(PYTHONPATH=str(tmp_path)))
    assert fixed_rc == 0, "剔除宿主 pytest 配置后嵌套运行应正常通过"


@pytest.mark.unit
def test_real_gold_pruning_site_survives_poisoned_host_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """真实站点最小化调用：gold 剪枝 ``_run_suite`` 在宿主污染下仍返回 rc=0。"""
    from experiments.gold_consistency_pruning import _run_suite

    monkeypatch.setenv("PYTEST_PLUGINS", "no_such_host_plugin_xyz")
    rc = _run_suite(_TRIVIAL_TARGET, _TRIVIAL_TEST, "m", timeout=120)
    assert rc == 0, f"真实站点在宿主 PYTEST_PLUGINS 污染下未跑通（rc={rc}）"


@pytest.mark.unit
def test_real_testlevel_run_side_site_survives_poisoned_host_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """真实站点最小化调用：testlevel ``run_side`` 在宿主污染下仍能靠 PYTHONPATH 加载插件。

    这条同时证明 5 处站点里最复杂的一处（自写 ``_dsh_outcomes`` 插件物化进 tmpdir、
    靠 ``PYTHONPATH`` 与 ``-p`` 加载）在收敛后语义未变：rc=0 且插件记录被解析到。
    """
    from experiments.emse_testlevel_detection import run_side

    monkeypatch.setenv("PYTEST_PLUGINS", "no_such_host_plugin_xyz")
    rec = run_side("m", _TRIVIAL_TARGET, _TRIVIAL_TEST, cap_seconds=120)
    assert rec["timed_out"] is False
    assert rec["rc"] == 0, f"run_side 在宿主污染下 rc={rec['rc']}，stderr={rec['stderr_tail']}"
    assert rec["parser"] in ("plugin", "plugin+verbose"), f"插件解析链路异常：parser={rec['parser']}"
    assert rec["n_nodeids"] >= 1
