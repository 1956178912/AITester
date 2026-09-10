"""打包完整性回归测试：确保 find_packages() 能发现的全部子包都有 __init__.py。

回归背景：src/utils 曾缺失 __init__.py（PEP 420 命名空间包），本地导入正常，
但 setuptools.find_packages() 只收集"含 __init__.py 的目录"，导致 pip 安装包
漏掉 src.utils，安装后 from src.utils.helpers import ... 抛 ImportError。
本测试不依赖 setuptools（venv 中可能未安装），改用文件系统断言锁定。
"""

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
