"""
结构化可观测性模块包。

包含 JSONL 追踪记录（trace.py）：
    - 记录每个智能体节点的输入输出、决策路径
    - 记录逐任务 token 消耗与墙钟耗时
    - 供实验分析与调试回放（4.1）

包标记文件（__init__.py）必须存在：setuptools find_packages() 仅收集
含 __init__.py 的目录，缺失时 src.observability 不会打入安装包。
"""
