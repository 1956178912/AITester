"""打包完整性回归测试：确保 find_packages() 能发现的全部子包都有 __init__.py。

回归背景：src/utils 曾缺失 __init__.py（PEP 420 命名空间包），本地导入正常，
但 setuptools.find_packages() 只收集"含 __init__.py 的目录"，导致 pip 安装包
漏掉 src.utils，安装后 from src.utils.helpers import ... 抛 ImportError。
本测试不依赖 setuptools（venv 中可能未安装），改用文件系统断言锁定。
"""

import ast as _ast
import tomllib as _tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 包目录清单：与 setup.py find_packages() 语义对齐
# （src 及其子包、examples、experiments；tests 不参与分发但同样需要包标记）
REQUIRED_PACKAGE_DIRS = [
    "src",
    "src/agents",
    "src/api",
    "src/cli",
    "src/config",
    "src/datasets",
    "src/db",
    "src/experiments",
    "src/graph",
    "src/prompts",
    "src/rag",
    "src/reports",
    "src/tools",
    "src/utils",
]


def test_all_package_dirs_have_init():
    """每个包目录都必须存在 __init__.py（find_packages 的收集前提）。"""
    missing = [d for d in REQUIRED_PACKAGE_DIRS if not (PROJECT_ROOT / d / "__init__.py").is_file()]
    assert not missing, f"以下包目录缺少 __init__.py，pip 安装后会导入失败: {missing}"


def test_src_utils_submodules_importable():
    """src.utils 三个工具模块均可导入（锁定包标记存在且模块无导入错误）。"""
    import src.utils.exceptions
    import src.utils.helpers
    import src.utils.logging_utils

    assert src.utils.helpers.extract_code_block is not None
    assert src.utils.exceptions.AITesterError is not None
    assert src.utils.logging_utils.SensitiveFilter is not None


def test_no_namespace_package_drift():
    """扫描 src 下所有含 .py 文件但缺 __init__.py 的目录（漂移检测）。

    命名空间包在本地"能跑"，但永远进不了 pip 包——新加子包目录时
    必须同步补 __init__.py，此测试防止再次漂移。
    """
    src_root = PROJECT_ROOT / "src"
    offenders = []
    for py_file in src_root.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        pkg_dir = py_file.parent
        if not (pkg_dir / "__init__.py").is_file():
            offenders.append(str(pkg_dir.relative_to(PROJECT_ROOT)))
    assert not sorted(set(offenders)), f"以下目录含模块但缺少 __init__.py: {sorted(set(offenders))}"


# P2-5（2026-10 依赖分组）：运行时依赖面锁定。
# 背景：此前 pytest / pytest-cov / pymysql / DBUtils 在 [project] 核心
# dependencies 中——测试工具与可选 DB 驱动进了发行安装面。现分组为
# dev / db extra（requirements.txt 全量清单不变，CI/dev 装全量；
# 发行安装面收敛）。本测试解析 pyproject.toml 锁定分组不漂移。


def _pyproject_project() -> dict:
    """解析 pyproject.toml 的 [project] 节（tomllib，Python 3.11+ stdlib）。"""
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as f:
        return _tomllib.load(f)["project"]


def test_dev_tools_not_in_runtime_dependencies():
    """P2-5：pytest / pytest-cov 不得回到 [project] 核心依赖（应在 dev extra）。"""
    project = _pyproject_project()
    deps = {d.split(">=")[0].split("==")[0].strip().lower() for d in project.get("dependencies", [])}
    dev_deps = {
        d.split(">=")[0].split("==")[0].strip().lower() for d in project.get("optional-dependencies", {}).get("dev", [])
    }
    assert "pytest" in dev_deps and "pytest-cov" in dev_deps, "pytest/pytest-cov 应在 dev extra"
    assert not ({"pytest", "pytest-cov"} & deps), "pytest/pytest-cov 不得在核心运行时依赖中"


def test_db_optional_extra_exists():
    """P2-5：pymysql / DBUtils 在 db extra（MySQL 持久化可选功能）。"""
    project = _pyproject_project()
    deps = {d.split(">=")[0].split("==")[0].strip().lower() for d in project.get("dependencies", [])}
    db_deps = {
        d.split(">=")[0].split("==")[0].strip().lower() for d in project.get("optional-dependencies", {}).get("db", [])
    }
    assert {"pymysql", "dbutils"} <= db_deps, "pymysql/DBUtils 应在 db extra"
    assert not ({"pymysql", "dbutils"} & deps), "pymysql/DBUtils 不得在核心运行时依赖中"


# N-漂移守卫（2026-10-05 复审）：setup.py 是非 PEP 517 回退路径，其
# install_requires 曾与 pyproject [project].dependencies 漂移（多出
# pymysql/DBUtils/pytest/pytest-cov——P2-5 分组后未同步回退路径），导致
# 走 setup.py 安装的用户多装测试工具与 DB 驱动。下方测试用 ast 静态解析
# setup.py（不执行），锁定两条路径核心依赖集合一致。


def _normalize_dep_name(dep: str) -> str:
    """PyPI 名称归一：取约束前的包名，小写，-/_ 视为等价（PEP 503）。"""
    name = dep.strip()
    for sep in (">=", "<=", "==", "!=", "~=", ">", "<", ";", "["):
        name = name.split(sep)[0]
    return name.strip().lower().replace("_", "-")


def _setup_py_install_requires() -> list[str]:
    """ast 解析 setup.py 的 setup(install_requires=[...]) 字面量（不执行文件）。"""
    tree = _ast.parse((PROJECT_ROOT / "setup.py").read_text(encoding="utf-8"))
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call):
            func = node.func
            func_name = getattr(func, "id", None) or getattr(func, "attr", None)
            if func_name == "setup":
                for kw in node.keywords:
                    if kw.arg == "install_requires" and isinstance(kw.value, _ast.List):
                        return [
                            elt.value
                            for elt in kw.value.elts
                            if isinstance(elt, _ast.Constant) and isinstance(elt.value, str)
                        ]
    raise AssertionError("setup.py 中未找到 setup(install_requires=[...]) 字面量列表")


def test_setup_py_install_requires_matches_pyproject():
    """N-漂移守卫：setup.py 回退路径核心依赖集合 == pyproject [project].dependencies。"""
    project = _pyproject_project()
    pyproject_names = {_normalize_dep_name(d) for d in project.get("dependencies", [])}
    setup_names = {_normalize_dep_name(d) for d in _setup_py_install_requires()}
    assert setup_names == pyproject_names, (
        f"setup.py install_requires 与 pyproject [project].dependencies 漂移："
        f"仅 setup.py 有 {sorted(setup_names - pyproject_names)}，"
        f"仅 pyproject 有 {sorted(pyproject_names - setup_names)}"
    )


def _setup_py_extras_require() -> dict[str, list[str]]:
    """ast 解析 setup.py 的 setup(extras_require={...}) 字面量（不执行文件）。"""
    tree = _ast.parse((PROJECT_ROOT / "setup.py").read_text(encoding="utf-8"))
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call):
            func = node.func
            func_name = getattr(func, "id", None) or getattr(func, "attr", None)
            if func_name == "setup":
                for kw in node.keywords:
                    if kw.arg == "extras_require" and isinstance(kw.value, _ast.Dict):
                        out: dict[str, list[str]] = {}
                        for key_node, val_node in zip(kw.value.keys, kw.value.values, strict=False):
                            if (
                                isinstance(key_node, _ast.Constant)
                                and isinstance(key_node.value, str)
                                and isinstance(val_node, _ast.List)
                            ):
                                out[key_node.value] = [
                                    elt.value
                                    for elt in val_node.elts
                                    if isinstance(elt, _ast.Constant) and isinstance(elt.value, str)
                                ]
                        return out
    raise AssertionError("setup.py 中未找到 setup(extras_require={...}) 字面量字典")


def test_setup_py_extras_groups_match_pyproject():
    """O6（2026-10-05 系统审查 P2）：setup.py extras 分组集合 == pyproject extras。

    此前 setup.py 缺 db 组（pyproject 有）——非 PEP 517 回退路径
    pip install ".[db]" 装不到 MySQL 驱动；本守卫锁定两条路径 extras
    分组名与各组依赖包名集合一致（防未来再次漂移）。
    """
    project = _pyproject_project()
    pyproject_extras = project.get("optional-dependencies", {})
    setup_extras = _setup_py_extras_require()
    assert set(setup_extras) == set(pyproject_extras), (
        f"extras 分组漂移：仅 setup.py 有 {sorted(set(setup_extras) - set(pyproject_extras))}，"
        f"仅 pyproject 有 {sorted(set(pyproject_extras) - set(setup_extras))}"
    )
    for group in pyproject_extras:
        py_names = {_normalize_dep_name(d) for d in pyproject_extras[group]}
        setup_names = {_normalize_dep_name(d) for d in setup_extras.get(group, [])}
        assert py_names == setup_names, (
            f"extras[{group}] 依赖漂移：仅 setup.py 有 {sorted(setup_names - py_names)}，"
            f"仅 pyproject 有 {sorted(py_names - setup_names)}"
        )


# ─── A13 / A14（2026-10-18 第三方评审 P1）：执行运行依赖 + 发行缺包导入 ────────
# A13：Executor 子进程固定 `python -m pytest ... --cov`，pytest / pytest-cov
# 此前只在 dev extra——干净基础 wheel 安装后执行路径缺模块。修复为显式
# [execution] extra + 执行前能力检查（缺模块时结构化 execution_dependency_missing）。
# A14：setup.py 只收 src*，src→experiments 的函数内导入在干净 wheel 下必须
# 保守降级（mutation_advisor / nodes 的 N5 去重层），不得打断节点/路由。

import sys  # noqa: E402


def test_execution_extra_declares_executor_runtime_dependencies():
    """A13：execution extra 必须含 Executor 子进程运行所需模块（双源一致）。"""
    project = _pyproject_project()
    execution = {_normalize_dep_name(dep) for dep in project.get("optional-dependencies", {}).get("execution", [])}
    assert {"pytest", "pytest-cov", "pytest-timeout"} <= execution, (
        f"execution extra 缺少执行运行依赖: {sorted({'pytest', 'pytest-cov', 'pytest-timeout'} - execution)}"
    )
    # 默认安装面刻意不扩大：pytest/pytest-cov 仍不得回核心 dependencies
    core = {_normalize_dep_name(dep) for dep in project.get("dependencies", [])}
    assert not ({"pytest", "pytest-cov"} & core)
    # setup.py 回退路径同组存在（依赖集合一致性由上面的 extras 双源守卫锁定）
    assert "execution" in _setup_py_extras_require()


def test_execution_capability_available_in_project_env():
    """A13：开发/CI 环境（requirements.lock 含 pytest/pytest-cov）能力检查可用。"""
    from src.agents import executor_runtime as er

    capability = er.check_execution_capability(require_coverage=True, require_timeout_plugin=True)
    assert capability["available"] is True
    assert capability["missing_modules"] == []
    assert set(capability["required_modules"]) == {"pytest", "pytest_cov", "pytest_timeout"}
    assert capability["install_hint"] == 'pip install "aitester[execution]"'


def test_execution_capability_reports_missing_modules(monkeypatch):
    """A13：缺模块时返回清晰诊断（缺失清单 + 安装指引），而非晦涩 rc=1。"""
    from src.agents import executor_runtime as er

    monkeypatch.setattr(
        er,
        "_probe_interpreter_modules",
        lambda interpreter, modules, env=None: (
            {"pytest": True, "pytest_cov": False, "pytest_timeout": True},
            None,
        ),
    )
    er.clear_execution_capability_cache()
    try:
        capability = er.check_execution_capability(require_coverage=True, require_timeout_plugin=False)
        assert capability["available"] is False
        assert capability["missing_modules"] == ["pytest_cov"]
        assert capability["missing_packages"] == ["pytest-cov"]
        assert capability["probe"] == "in_process"
        error_info = er.build_execution_dependency_error(capability)
        assert error_info["type"] == "execution_dependency_missing"
        assert "aitester[execution]" in error_info["message"]
        assert "pytest-cov" in error_info["detail"]
        assert error_info["missing_modules"] == ["pytest_cov"]
    finally:
        er.clear_execution_capability_cache()


def test_execution_capability_probe_failure_does_not_block():
    """A13：探测基础设施自身失败 → available=True（交回执行层真实错误）。"""
    from src.agents import executor_runtime as er

    capability = er.check_execution_capability("/nonexistent/python-for-probe")
    # 解释器不存在 → 子进程探测失败 → 保守放行（不误报缺模块）
    assert capability["available"] is True
    assert capability["probe"] == "failed"
    assert capability["probe_error"]


def test_command_python_interpreter_handles_kernel_sandbox_argv():
    """A13：能力检查能从内核沙箱包装后的 argv 中定位解释器。"""
    from src.agents import executor_runtime as er

    assert er._command_python_interpreter(["pytest", "-q"]) is None  # 无解释器 → 跳过检查
    assert er._command_python_interpreter([sys.executable, "-m", "pytest"]) == sys.executable
    wrapped = ["sandbox-exec", "-p", "(version 1)(allow default)", sys.executable, "-m", "pytest"]
    assert er._command_python_interpreter(wrapped) == sys.executable


def test_executor_returns_clear_error_when_execution_deps_missing(monkeypatch, tmp_path):
    """A13：干净基础 wheel（缺 pytest/pytest-cov）→ 结构化早退，不跑子进程。"""
    from src.agents import executor_runtime as er
    from src.agents.executor import ExecutorAgent

    target = tmp_path / "cap_target_mod.py"
    target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    monkeypatch.setattr(
        er,
        "check_execution_capability",
        lambda *a, **k: {
            "available": False,
            "interpreter": sys.executable,
            "required_modules": ["pytest", "pytest_cov"],
            "missing_modules": ["pytest", "pytest_cov"],
            "missing_packages": ["pytest", "pytest-cov"],
            "install_hint": 'pip install "aitester[execution]"',
            "probe": "in_process",
            "probe_error": None,
        },
    )

    def _must_not_run(*_a, **_k):
        raise AssertionError("能力检查未通过时不得启动 pytest 子进程")

    monkeypatch.setattr(er, "run_with_timeout", _must_not_run)
    agent = ExecutorAgent(timeout=10, use_venv=False)
    result = agent.execute("def test_add():\n    assert add(1, 2) == 3\n", str(target))

    assert result["passed"] is False
    assert result["error_info"]["type"] == "execution_dependency_missing"
    assert 'pip install "aitester[execution]"' in result["output"]
    assert result["error_info"]["missing_modules"] == ["pytest", "pytest_cov"]


def test_mutation_advisor_degrades_when_experiments_missing(monkeypatch, caplog):
    """A14：干净 wheel（无 experiments 包）下 mutation_advisor 节点不崩、feedback=None。"""
    import logging as _logging
    from unittest.mock import patch as _patch

    from src.graph.mutation_advisor import _mutation_advisor_node

    monkeypatch.setattr("src.graph.tracing._trace_node", lambda *a, **k: None)
    with (
        caplog.at_level(_logging.WARNING, logger="src.graph.mutation_advisor"),
        _patch.dict(sys.modules, {"experiments": None, "experiments.mutation_testing": None}),
    ):
        update = _mutation_advisor_node(
            {
                "target_code": "def f():\n    return 1\n",
                "generated_test": "def test_f():\n    assert f() == 1\n",
                "iteration": 1,
            }
        )
    assert update == {}  # 保守降级：不写 mutation_feedback、不抛异常
    # 判别性：确实走了 ImportError 降级分支（而不是碰巧测量层返回空）
    assert any("experiments 测量层不可用" in record.message for record in caplog.records)


def test_src_has_no_module_level_experiments_imports():
    """A14 全仓守卫：src/ 模块顶层不得 import experiments（wheel 不含该包）。"""
    offenders: list[str] = []
    for path in (PROJECT_ROOT / "src").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = _ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:  # 仅模块顶层语句（函数内延迟导入不受影响）
            names: list[str] = []
            if isinstance(node, _ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, _ast.ImportFrom):
                names = [node.module or ""]
            if any(name == "experiments" or name.startswith("experiments.") for name in names):
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}")
    assert not offenders, f"src/ 顶层 import experiments 会打断干净 wheel 导入: {offenders}"


def test_test_suite_dedup_degrades_when_experiments_missing(monkeypatch, caplog):
    """A14：nodes N5 去重层在缺 experiments 时保守跳过（不打断 generator）。"""
    import logging as _logging
    from unittest.mock import patch as _patch

    from src.graph.nodes import _apply_test_suite_dedup

    monkeypatch.setenv("TEST_SUITE_DEDUP_ENABLE", "true")
    code = "def test_x():\n    assert 1 == 1\n"
    with (
        caplog.at_level(_logging.WARNING, logger="src.graph.nodes"),
        _patch.dict(sys.modules, {"experiments": None, "experiments.test_suite_minimize": None}),
    ):
        deduped, removed = _apply_test_suite_dedup(code)
    assert deduped == code
    assert removed == 0
    assert any("去重层不可用" in record.message for record in caplog.records)


def test_test_suite_dedup_switch_off_is_noop(monkeypatch):
    """A14：默认关时 N5 去重层零行为变化（连 experiments 都不尝试导入）。"""
    from unittest.mock import patch as _patch

    from src.graph.nodes import _apply_test_suite_dedup

    monkeypatch.delenv("TEST_SUITE_DEDUP_ENABLE", raising=False)
    code = "def test_x():\n    assert 1 == 1\n"
    with _patch.dict(sys.modules, {"experiments": None, "experiments.test_suite_minimize": None}):
        assert _apply_test_suite_dedup(code) == (code, 0)


def test_execution_capability_subprocess_probe_parses_result():
    """A13：非当前进程解释器的子进程探测路径可解析（真实解释器 + 缺失模块）。"""
    from src.agents import executor_runtime as er

    modules, error = er._probe_modules_subprocess(
        sys.executable,
        ("pytest", "definitely_missing_module_a16"),
    )
    assert error is None
    assert modules == {"pytest": True, "definitely_missing_module_a16": False}
