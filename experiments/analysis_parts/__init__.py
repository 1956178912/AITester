"""analyze_results.py 的统计函数子模块包（0.7 债务项 1.6 拆分）。

按主题分文件：
- rag_analysis：RAG 检索质量与 Token 效率
- convergence_analysis：修复收敛 / 质量代理 / 测试异味 / 跨基线对比
- cross_analysis：跨主题交叉分析（污染 / venv 缓存）

experiments.analyze_results 通过 re-export 保持公开入口不变（build_analysis /
render_markdown / main / load_latest_benchmark），历史 import 路径不受影响。
"""
