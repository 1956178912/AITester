"""
AITester 包管理配置文件。

使用 python setup.py install 或 pip install -e . 进行安装。
包含基础依赖与可选 extras：[rag], [viz], [dev]。
"""

from setuptools import setup, find_packages

setup(
    name="aitester",
    version="0.1.0",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "langchain>=1.0.0",
        "langchain-openai>=1.0.0",
        "langgraph>=1.0.0",
        "pymysql>=1.0.0",
        "click>=8.0.0",
        "pytest>=8.0.0",
        "pytest-cov>=4.0.0",
        "python-dotenv>=1.0.0",
        "radon>=6.0.0",
        "requests>=2.31.0",
    ],
    extras_require={
        "rag": ["chromadb>=0.5.0"],
        "viz": ["matplotlib>=3.7.0", "pandas>=2.0.0"],
        "dev": ["pytest>=8.0.0", "pytest-cov>=4.0.0"],
    },
    entry_points={
        "console_scripts": [
            "aitester=main:cli",
        ],
    },
)
