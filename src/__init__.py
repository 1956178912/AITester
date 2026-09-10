"""
AITester 核心模块包。

包含以下子模块：
    - agents: 多智能体实现（Planner, Generator, Executor, Debugger）
    - api: API 管理与多模型轮换
    - config: 配置生成与管理
    - datasets: 数据集加载（SWE-bench, Defects4J）与合成数据集生成
    - db: MySQL 数据库客户端
    - experiments: 实验分析与报告
    - graph: LangGraph 工作流编排
    - prompts: 提示词模板
    - rag: 检索增强生成模块
    - reports: 实验报告生成
    - tools: 工具函数（代码分析、补丁应用等）
    - utils: 通用工具（辅助函数、异常处理、日志）
"""

# 版本号单一事实来源：setup.py 与 CLI（--version）均从此处读取，
# 避免多处硬编码导致版本漂移。
__version__ = "0.9.3"

__all__ = ["__version__"]
