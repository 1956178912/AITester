"""打包完整性回归测试：确保 find_packages() 能发现的全部子包都有 __init__.py。

回归背景：src/utils 曾缺失 __init__.py（PEP 420 命名空间包），本地导入正常，
但 setuptools.find_packages() 只收集"含 __init__.py 的目录"，导致 pip 安装包
漏掉 src.utils，安装后 from src.utils.helpers import ... 抛 ImportError。
本测试不依赖 setuptools（venv 中可能未安装），改用文件系统断言锁定。
"""

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
