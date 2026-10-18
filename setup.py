"""
AITester 包管理配置文件。

使用 python setup.py install 或 pip install -e . 进行安装。
包含基础依赖与可选 extras：[rag], [viz], [experiments], [ux], [dev],
[execution], [db], [formal], [ult]。

2026-10-18 第三方评审 A13（P1）：[execution] 是**执行功能运行依赖**
（pytest / pytest-cov / pytest-timeout）——Executor 子进程固定
`python -m pytest ... --cov`，干净基础 wheel 缺这些模块时执行路径会失败。
默认 install_requires 刻意不扩大（不跑执行功能的基础用户不背测试工具
依赖）；需要运行 Executor / 基准评测时 pip install "aitester[execution]"。

O9（2026-09-29 审查 P0）：PEP 621 [project] 元数据已迁移到
pyproject.toml（唯一事实来源）。本 setup.py 退化为兼容 shim：
pip 构建时优先读 pyproject.toml；setup.py 仅在 setuptools
回退路径（非 PEP 517 构建）下生效。
"""

from setuptools import find_packages, setup


def _load_version() -> str:
    """从 src/__init__.py 读取版本号（单一事实来源，避免多处硬编码漂移）。"""
    import re
    from pathlib import Path

    init_file = Path(__file__).parent / "src" / "__init__.py"
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_file.read_text(encoding="utf-8"))
    return match.group(1) if match else "0.0.0"


setup(
    name="aitester",
    version=_load_version(),
    # O9：仅收录 src/ 包（排除 experiments/ / scripts/ / tests/ 等
    # 非发布目录），使 wheel 只含 src/ + config.py
    packages=find_packages(include=["src", "src.*"]),
    # 根级 config.py 是全局配置模块（src/ 内 6 个模块 from config import ...），
    # 它不是含 __init__.py 的包，find_packages() 不会收录；不声明 py_modules
    # 则正式安装（pip install . 非 editable）后 entry point 触发 ModuleNotFoundError: config
    py_modules=["config"],
    # 锁定依赖集（requirements.lock）实际要求 Python >= 3.12（scipy 下限）
    python_requires=">=3.12",
    install_requires=[
        "langchain>=1.0.0",
        "langchain-openai>=1.0.0",
        "langgraph>=1.0.0",
        "click>=8.0.0",
        "python-dotenv>=1.0.0",
        # 注：radon 于 2026-09-09 依赖审计中移除（全项目无 import 引用）
        "requests>=2.31.0",
        # N-漂移修复（2026-10-05 复审）：与非 PEP 517 回退路径对齐
        # pyproject [project].dependencies——此前此处仍列 pymysql/DBUtils
        # （→ [db] extra）与 pytest/pytest-cov（→ [dev] extra），回退安装
        # 会把测试工具与可选 DB 驱动装进运行时依赖面（见下方 extras_require
        # 与 tests/test_packaging.py 的 install_requires 漂移守卫）。
        "openai>=1.0.0",
        "zai-sdk>=0.2.0",
    ],
    extras_require={
        "rag": ["chromadb>=0.5.0"],
        "viz": ["matplotlib>=3.7.0", "pandas>=2.0.0"],
        # 实验统计与 SWE-bench 数据集下载依赖
        "experiments": ["scipy>=1.10.0", "datasets>=5.0.0"],
        # CLI 富文本与进度条
        "ux": ["rich>=13.0.0", "tqdm>=4.65.0"],
        "dev": ["pytest>=8.0.0", "pytest-cov>=4.0.0", "pytest-timeout>=2.0.0"],
        # A13（2026-10-18 第三方评审 P1）：与 pyproject [execution] 对齐。
        # Executor 子进程固定 `python -m pytest ... --cov`（本地 / venv 沙箱
        # 链路；PYTEST_TIMEOUT_ENABLE=true 时附 --timeout），故执行功能需要
        # pytest + pytest-cov + pytest-timeout；不进默认 install_requires
        # （安装面最小化，见模块 docstring）。
        "execution": ["pytest>=8.0.0", "pytest-cov>=4.0.0", "pytest-timeout>=2.0.0"],
        # O6（2026-10-05 系统审查 P2）：补 db 组——pyproject [db] 有而此处缺，
        # 非 PEP 517 回退路径 pip install ".[db]" 装不到 MySQL 驱动
        # （tests/test_packaging.py 此前只守卫 install_requires，不守卫 extras）
        "db": ["pymysql>=1.0.0", "DBUtils>=3.0.0"],
        # G4（2026-10-05 优化批次·T2）：与 pyproject [formal] 对齐
        # （SMT 见证层可选求解器；tests/test_packaging.py extras 守卫锁双源一致）
        # AR 批（2026-10-07）：补 hypothesis（G18/T5 属性测试底座 + AN4
        # 属性模板路线），与 pyproject [formal] 保持双源一致
        "formal": ["z3-solver>=4.12.0", "hypothesis>=6.100.0"],
        # D3-W1（2026-10-13）：与 pyproject [ult] 对齐（ULT cosmic-ray 口径
        # mutation-score 适配器可选依赖，钉 8.7.0；tests/test_packaging.py
        # extras 守卫锁双源一致）
        "ult": ["cosmic-ray==8.7.0"],
    },
    entry_points={
        "console_scripts": [
            # 指向 src.cli.app（CLI 实现所在）；根级 main.py 仅本地入口，不被 find_packages 打包
            "aitester=src.cli.app:cli",
        ],
    },
    # O9：LICENSE 字段（与 pyproject.toml [project] license = {file = "LICENSE"} 对齐）
    license_files=["LICENSE"],
)
