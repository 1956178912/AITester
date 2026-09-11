"""
AITester 包管理配置文件。

使用 python setup.py install 或 pip install -e . 进行安装。
包含基础依赖与可选 extras：[rag], [viz], [dev]。
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
    packages=find_packages(),
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
        "pymysql>=1.0.0",
        # DBUtils: PooledDB 连接池，src/db/mysql_client.py 使用
        "DBUtils>=3.0.0",
        "click>=8.0.0",
        "pytest>=8.0.0",
        "pytest-cov>=4.0.0",
        "python-dotenv>=1.0.0",
        # 注：radon 于 2026-09-09 依赖审计中移除（全项目无 import 引用）
        "requests>=2.31.0",
    ],
    extras_require={
        "rag": ["chromadb>=0.5.0"],
        "viz": ["matplotlib>=3.7.0", "pandas>=2.0.0"],
        # 实验统计与 SWE-bench 数据集下载依赖
        "experiments": ["scipy>=1.10.0", "datasets>=5.0.0"],
        # CLI 富文本与进度条
        "ux": ["rich>=13.0.0", "tqdm>=4.65.0"],
        "dev": ["pytest>=8.0.0", "pytest-cov>=4.0.0", "pytest-timeout>=2.0.0"],
    },
    entry_points={
        "console_scripts": [
            # 指向 src.cli.app（CLI 实现所在）；根级 main.py 仅本地入口，不被 find_packages 打包
            "aitester=src.cli.app:cli",
        ],
    },
)
