# 4. 实验设置

## 4.1 数据集

| 数据集 | 规模 | 来源 | 用途 |
|-------|-----|------|------|
| examples | 3 | 内置（calculator, buggy_library, string_utils） | 快速验证、开发调试 |
| synthetic | 187 | 本地生成（10 种 bug 模板） | 主实验、统计分析 |
| swe_bench_lite | 500 | HuggingFace princeton-nlp/SWE-bench | 真实场景验证（待执行） |

合成数据集通过 [src/synthetic_dataset.py](../src/synthetic_dataset.py) 的 `SyntheticDataset` 类本地生成，支持 10 种预定义 bug 模式（除零缺失、边界偏移、大小写敏感等），每个任务包含明确的 bug 描述、缺陷代码与参考测试。

SWE-bench 数据集通过 [src/dataset_loader.py](../src/dataset_loader.py) 的 `SWEBenchDataset` 加载，支持从 HuggingFace 自动下载（`download_from_huggingface()` 方法），数据缓存于 `~/.cache/aitester/swe_bench/`。

## 4.2 基线方法

1. **AITester（完整系统）**：Planner + Generator + Executor + Debugger 全链路，启用逻辑规划与分层修复。
2. **plain_llm**：无 Planner、无 Debugger，单次 LLM 调用直接生成测试代码，不进行修复迭代。
3. **single_agent**：所有功能合并为一次 LLM 调用，最多一轮修复尝试。

所有基线使用相同 LLM 模型（`MODEL_NAME`）、相同温度参数（`TEMPERATURE=0.2`）与相同最大迭代次数（`MAX_ITERATIONS=3`），确保对比公平性。

## 4.3 评估指标

- **成功率（Success Rate）**：通过全部测试用例的任务占比（%）。
- **平均覆盖率（Avg Coverage）**：pytest-cov 报告的代码行覆盖率均值（%）。
- **平均迭代次数（Avg Iterations）**：Debugger 修复循环的平均轮数。
- **执行时间（Avg Elapsed）**：单任务平均耗时（秒）。

## 4.4 统计检验

- **配对 t 检验（Paired t-test）**：比较同一任务上两个基线的通过率差异。
- **Mann-Whitney U 检验**：非参数检验，验证差异稳健性。
- **Cohen's d**：效应量，量化提升幅度。
- 显著性水平：$\alpha = 0.05$。

统计检验实现在 [experiments/visualize_results.py](../experiments/visualize_results.py) 的 `compute_significance()` 函数中。

## 4.5 实现细节

- **LLM**：agnes-2.5-flash（temperature=0.2），通过 OpenAI 兼容 API 调用
- **框架**：LangChain + LangGraph 工作流编排
- **向量数据库**：ChromaDB（cosine 相似度，RAG 模块）
- **测试框架**：pytest + pytest-cov
- **硬件**：MacBook Pro M2，16GB RAM
- **环境隔离**：测试执行使用临时目录 +  subprocess 超时控制（30 秒）
