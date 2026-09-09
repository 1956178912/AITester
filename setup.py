"""
AITester 包管理配置文件。

使用 python setup.py install 或 pip install -e . 进行安装。
包含基础依赖与可选 extras：[rag], [viz], [dev]。
"""

from setuptools import find_packages, setup

setup(
    name="aitester",
    version="0.9.0",
    packages=find_packages(),
    # 锁定依赖集（requirements.lock）实际要求 Python >= 3.12（scipy 下限）
    python_requires=">=3.12",
    install_requires=[
        "langchain>=1.0.0",
        "langchain-openai>=1.0.0",
        "langgraph>=1.0.0",
        "pymysql>=1.0.0",
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
        "dev": ["pytest>=8.0.0", "pytest-cov>=4.0.0"],
    },
    entry_points={
        "console_scripts": [
            # 指向 src.cli.app（CLI 实现所在）；根级 main.py 仅本地入口，不被 find_packages 打包
            "aitester=src.cli.app:cli",
        ],
    },
)
