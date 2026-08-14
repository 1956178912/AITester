# 附录

## A. 实验复现指南

### A.1 环境搭建
```bash
git clone <repo> && cd AITester
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
```

### A.2 运行基准测试
```bash
# 快速验证（内置示例，3 任务，三种基线）
python experiments/run_benchmark.py --dataset examples --baselines aitester,plain_llm,single_agent

# 合成数据集（100 任务）
python experiments/run_large_scale.py --task-count 100 --baselines aitester,plain_llm,single_agent

# SWE-bench-lite（500 任务，需先下载数据）
python scripts/download_swe_bench.py --subset lite
python experiments/run_benchmark.py --dataset swe_bench --subset lite --baselines aitester,plain_llm,single_agent
```

### A.3 生成失败案例分析
```bash
python experiments/analyze_failures.py --results-dir experiments/results --output docs/paper/failure_analysis.md
```

### A.4 可视化结果
```bash
python experiments/visualize_results.py
# 输出：charts/baseline_comparison.png, charts/statistical_significance.png
```

## B. 源码索引

| 功能模块 | 文件路径 |
|---------|---------|
| 多智能体工作流 | [src/graph/workflow.py](../src/graph/workflow.py) |
| 全局状态定义 | [src/graph/state.py](../src/graph/state.py) |
| 测试规划师 | [src/agents/planner.py](../src/agents/planner.py) |
| 测试生成器 | [src/agents/generator.py](../src/agents/generator.py) |
| 测试执行器 | [src/agents/executor.py](../src/agents/executor.py) |
| 调试修复师 | [src/agents/debugger.py](../src/agents/debugger.py) |
| 错误分类器 | [src/agents/error_classifier.py](../src/agents/error_classifier.py) |
| Prompt 模板 | [src/prompts/templates.py](../src/prompts/templates.py) |
| 补丁应用 | [src/tools/patch_applier.py](../src/tools/patch_applier.py) |
| 代码分析（AST） | [src/tools/code_analyzer.py](../src/tools/code_analyzer.py) |
| RAG 检索 | [src/rag/retriever.py](../src/rag/retriever.py) |
| 数据集加载 | [src/dataset_loader.py](../src/dataset_loader.py) |
| 合成数据集 | [src/synthetic_dataset.py](../src/synthetic_dataset.py) |
| 基准测试脚本 | [experiments/run_benchmark.py](../experiments/run_benchmark.py) |
| 大规模实验 | [experiments/run_large_scale.py](../experiments/run_large_scale.py) |
| 失败分析 | [experiments/analyze_failures.py](../experiments/analyze_failures.py) |
| 可视化 | [experiments/visualize_results.py](../experiments/visualize_results.py) |

## C. 论文文件清单

| 文件 | 内容 |
|-----|------|
| [01_introduction.md](01_introduction.md) | 引言（研究背景、问题、贡献） |
| [02_related_work.md](02_related_work.md) | 相关工作 |
| [03_methodology.md](03_methodology.md) | 方法论 |
| [04_experimental_setup.md](04_experimental_setup.md) | 实验设置 |
| [05_results.md](05_results.md) | 实验结果 |
| [06_discussion.md](06_discussion.md) | 讨论（局限性、未来工作） |
| [07_conclusion.md](07_conclusion.md) | 结论 |
| [08_appendix.md](08_appendix.md) | 附录（复现指南、源码索引） |
| [failure_analysis.md](failure_analysis.md) | 失败案例深度分析 |
