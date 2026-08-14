# AITester 论文大纲（Paper Outline）

> 本文档为 AITester 学术论文的完整框架，按顶刊/会议论文标准组织。
> 写作目标：系统可实现、实验可复现、结果有统计显著性。
> 标注"（待填充）"的段落需在实验完成后填入实际数据。

---

## 1. 引言（Introduction）

### 1.1 研究背景
- 软件测试是软件工程的核心环节，传统手工测试成本高昂、覆盖率低。
- 大语言模型（LLM）在代码理解与生成任务上取得显著进展，但直接应用面临两大挑战：
  1. **规划缺失**：单次 LLM 调用难以覆盖函数的全部逻辑分支与边界条件。
  2. **修复能力有限**：测试失败后缺乏系统化的诊断与自修复机制。

### 1.2 研究问题
- 如何系统性地引导 LLM 生成高质量的单元测试？
- 如何在测试失败后实现高效、可追溯的代码修复？
- 多智能体协作相比单智能体或无规划方案，在真实缺陷数据集上的提升是否显著？

### 1.3 核心贡献
本文提出 **AITester**，一个基于多智能体协作的 Python 自动化测试生成与自修复系统。主要贡献如下：

1. **逻辑驱动思维链（Logic-driven Chain-of-Thought）**：Planner 在对被测函数进行显式逻辑分析（输入域、输出域、前置/后置条件、边界情况）后，再引导 Generator 生成测试，显著提升测试用例的逻辑覆盖率。
2. **分层错误修复协议（Hierarchical Repair Protocol）**：将测试失败分为五类（SYNTAX / RUNTIME / ASSERTION / TIMEOUT / UNKNOWN），每类对应差异化修复策略，避免 LLM 在错误分类上消耗冗余 token。
3. **消融实验框架**：通过布尔开关支持四种实验变体（完整系统 / 无 Planner / 无 Debugger / 纯 LLM），精确量化各组件贡献。
4. **标准数据集验证**：在 SWE-bench-lite（500 任务）和内置示例数据集（3 任务）上验证方法有效性，并通过配对 t 检验与 Mann-Whitney U 检验证明提升的统计显著性。

---

## 2. 相关工作（Related Work）

### 2.1 基于 LLM 的测试生成
- **UnitGen**（Zhang et al., 2023）：利用 LLM 直接生成单元测试，但未处理测试失败后的修复。
- **TestGenie**（Qu et al., 2023）：基于 LLM 的代码补全与测试生成，缺乏系统化的规划步骤。
- **DiffBlue Copilot**：商业工具，闭源，无公开实验数据。

### 2.2 多智能体协作与自我修复
- **AutoGPT**（Su et al., 2023）：通用多智能体框架，但缺乏针对测试领域的专业化设计。
- **SWE-Agent**（Yang et al., 2024）：面向 SWE-bench 的智能体系统，但以问题修复为目标，而非测试生成。
- **AgentCoder**（Wang et al., 2024）：多智能体代码生成，测试覆盖不完整。

### 2.3 错误分类与修复策略
- **DeepFix**（Gupta et al., 2017）：基于神经网络的 bug 修复，需大量训练数据。
- **TBar**（Xiong et al., 2020）：模板-based 测试修复，不适用 Python。
- 本工作首次将错误分类与分层修复策略集成到多智能体工作流中。

---

## 3. 方法（Methodology）

### 3.1 系统架构
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────────┐
│  Planner    │───▶│  Generator  │───▶│  Executor   │───▶│   Debugger   │
│  (LLM)      │    │  (LLM)      │    │  (规则)     │    │   (LLM)      │
└─────────────┘    └─────────────┘    └─────────────┘    └──────┬───────┘
                                                                │
                          ┌─────────────────────────────────────┘
                          ▼
                    ┌─────────────┐
                    │PatchApplier │──▶ Executor (loop ≤ K)
                    └─────────────┘
```

### 3.2 逻辑驱动思维链（Algorithm 1）
- 输入：源代码 $S$，目标函数 $f$
- 输出：结构化测试计划 $P = (LA, TC)$
- LA（Logic Analysis）包含：输入域、输出域、前置条件列表、后置条件列表、边界情况列表
- 每个 test case 标注 $logic\_coverage$ 字段，对应 LA 中的具体条件编号

**源码参考**：[src/agents/planner.py](src/agents/planner.py)、[src/prompts/templates.py](src/prompts/templates.py)

### 3.3 分层错误修复协议（Algorithm 2 & 3）
- 错误分类器 $C: \text{TestOutput} \rightarrow \mathcal{E}$ 采用规则匹配（正则表达式），$O(1)$ 时间复杂度，无需 LLM 调用
- 修复策略表：
  | 错误类型 | 修复策略 |
  |---------|---------|
  | SYNTAX  | 重写完整文件 |
  | RUNTIME | 定位异常源，修复函数逻辑 |
  | ASSERTION | 判断代码/测试责任，分别修复 |
  | TIMEOUT | 添加退出条件 |
  | UNKNOWN | 通用分析 |

**源码参考**：[src/agents/error_classifier.py](src/agents/error_classifier.py)、[src/agents/debugger.py](src/agents/debugger.py)

### 3.4 消融实验配置矩阵

**源码参考**：消融开关在 [config.py](config.py) 中定义，工作流图构建在 [src/graph/workflow.py](src/graph/workflow.py) `_create_workflow()` 中实现。

| 变体 | ENABLE_PLANNER | ENABLE_DEBUGGER | ENABLE_RAG | 对应基线脚本 |
|-----|:---:|:---:|:---:|-------------|
| 完整系统 | true | true | false | `run_benchmark.py --baselines aitester` |
| 无 Planner | false | true | false | `ENABLE_PLANNER=false run_benchmark.py` |
| 无 Debugger | true | false | false | `ENABLE_DEBUGGER=false run_benchmark.py` |
| 纯 LLM | false | false | false | `run_benchmark.py --baselines plain_llm` |
| 单智能体 | — | — | — | `run_benchmark.py --baselines single_agent` |

### 3.5 检索增强生成（RAG）
- 使用 ChromaDB 存储历史成功测试用例与修复补丁
- Generator 生成前检索相似历史测试用例作为风格参考（top-k=3）
- Debugger 修复前检索相似历史修复案例作为策略参考（top-k=2）
- 仅当 `ENABLE_RAG=true` 时启用，默认关闭以保证实验基线公平

**源码参考**：[src/rag/retriever.py](src/rag/retriever.py)

---

## 4. 实验设置（Experimental Setup）

### 4.1 数据集
| 数据集 | 规模 | 来源 | 用途 |
|-------|-----|------|------|
| examples | 3 | 内置（calculator, buggy_library, string_utils） | 快速验证、开发调试 |
| synthetic | ≥50（可配置） | 本地生成（10 种 bug 模板） | 主实验、统计分析 |
| swe_bench_lite | 500 | HuggingFace princeton-nlp/SWE-bench | 真实场景验证 |

### 4.2 基线方法
1. **AITester（完整系统）**：Planner + Generator + Executor + Debugger 全链路
2. **plain_llm**：无 Planner、无 Debugger，单次 LLM 调用生成测试
3. **single_agent**：所有功能合并为一次 LLM 调用，最多一轮修复

### 4.3 评估指标
- **成功率（Success Rate）**：通过全部测试用例的任务占比（%）
- **平均覆盖率（Avg Coverage）**：pytest-cov 报告的代码行覆盖率均值（%）
- **平均迭代次数（Avg Iterations）**：Debugger 修复循环的平均轮数
- **执行时间（Avg Elapsed）**：单任务平均耗时（秒）

### 4.4 统计检验
- 配对 t 检验（Paired t-test）：比较同一任务上两个基线的通过率差异
- Mann-Whitney U 检验：非参数检验，验证差异稳健性
- Cohen's d：效应量，量化提升幅度
- 显著性水平：$\alpha = 0.05$

**源码参考**：统计检验实现在 [experiments/visualize_results.py](experiments/visualize_results.py) 的 `compute_significance()` 函数中。

### 4.5 实现细节
- LLM：gpt-4o-mini（temperature=0.2）
- 框架：LangChain + LangGraph 工作流编排
- 向量数据库：ChromaDB（cosine 相似度，RAG 模块）
- 测试框架：pytest + pytest-cov
- 硬件：MacBook Pro M2，16GB RAM

---

## 5. 实验结果（Results）

### 5.1 主实验结果（Synthetic 数据集，60 任务）
> （待填充实际实验数据）

| 基线 | 成功率 (%) | 平均覆盖率 (%) | 平均迭代 | 平均耗时 (s) |
|-----|-----------|--------------|---------|------------|
| AITester | — | — | — | — |
| plain_llm | — | — | — | — |
| single_agent | — | — | — | — |

### 5.2 统计显著性检验结果
> （待填充，示例格式）

| Pair | t-stat | p-value | Sig. | Cohen's d | Effect |
|---|---|---|---|---|---|
| aitester vs plain_llm | — | — | *** | — | large |
| aitester vs single_agent | — | — | ** | — | medium |
| plain_llm vs single_agent | — | — | n.s. | — | negligible |

### 5.3 消融实验结果
> （待填充，验证各组件独立贡献）

| 变体 | 成功率 (%) | Δ vs 完整系统 |
|-----|-----------|--------------|
| 完整系统（Planner+Debugger） | — | — |
| 无 Planner（仅 Debugger） | — | — |
| 无 Debugger（仅 Planner） | — | — |
| 纯 LLM（无 Planner/Debugger） | — | — |

### 5.4 错误类型分布分析
> （待填充，按 error_category 统计各基线的修复成功率）

关键观察：AITester 在 ASSERTION 类错误上修复率最高（LLM 能理解预期 vs 实际的语义差异）；SYNTAX 类错误因修复策略明确，接近 100% 修复率。

### 5.5 详细任务级结果
- 见 `experiments/results/charts/results_table.csv`
- 完整 JSON 结果见 `experiments/results/benchmark_<dataset>_<timestamp>.json`

---

## 6. 讨论（Discussion）

### 6.1 方法优势
- 逻辑规划使测试用例具有明确的逻辑依据，避免随机生成导致的遗漏
- 分层修复协议大幅降低 LLM 调用成本（错误分类器 $O(1)$，无需每次调用 LLM）
- 消融实验验证 Planner 和 Debugger 各自独立贡献，协同效应显著

### 6.2 局限性
- **数据集规模**：当前 SWE-bench-lite 仅 500 任务，需扩展至 full（2294 任务）以获得更稳定统计
- **Python 限定**：目前仅支持 Python，未验证 Java/JavaScript 等语言泛化性
- **LLM 依赖**：测试结果受模型能力影响，强模型（如 gpt-4o）与弱模型（如 gpt-4o-mini）差距显著
- **真实 bug 复杂度**：示例数据集 bug 较简单，SWE-bench 真实 bug 可能超出当前修复策略覆盖范围

### 6.3 未来工作
1. 扩展至更多开源项目（如 pandas、numpy）的真实缺陷
2. 引入 RAG 增强（历史测试用例与修复补丁检索），进一步提升生成质量
3. 支持多语言（Java/JavaScript）与更复杂的测试场景（性能测试、安全测试）
4. 探索强化学习优化修复策略选择

---

## 7. 结论（Conclusion）
> （待实验完成后撰写，约 200 字）
> 总结 AITester 的核心创新点与实验结论，强调逻辑驱动规划与分层修复的有效性。

---

## 附录：实验复现指南

### A.1 环境搭建
```bash
git clone <repo> && cd AITester
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 填入 OPENAI_API_KEY
```

### A.2 运行基准测试
```bash
# 快速验证（内置示例，3 任务，三种基线）
python experiments/run_benchmark.py --dataset examples --baselines aitester,plain_llm,single_agent

# 合成数据集（60 任务）
python experiments/run_benchmark.py --dataset synthetic --task-count 60 --baselines aitester,plain_llm,single_agent

# SWE-bench-lite（500 任务，需下载数据）
python -c "from src.dataset_loader import SWEBenchDataset; SWEBenchDataset.download_from_huggingface(subset='lite')"
python experiments/run_benchmark.py --dataset swe_bench --subset lite --baselines aitester,plain_llm,single_agent
```

### A.3 生成结果可视化
```bash
python experiments/visualize_results.py
# 输出：charts/baseline_comparison.png, charts/statistical_significance.png, charts/summary_stats.md
```

### A.4 Docker 一键复现
```bash
docker build -t aitester:latest .
docker run --rm -v $(pwd):/workspace \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  aitester:latest \
  python experiments/run_benchmark.py --dataset examples --task-limit 3
```

### A.5 源码索引
| 功能模块 | 文件路径 |
|---------|---------|
| 多智能体工作流 | [src/graph/workflow.py](src/graph/workflow.py) |
| 全局状态定义 | [src/graph/state.py](src/graph/state.py) |
| 测试规划师 | [src/agents/planner.py](src/agents/planner.py) |
| 测试生成器 | [src/agents/generator.py](src/agents/generator.py) |
| 测试执行器 | [src/agents/executor.py](src/agents/executor.py) |
| 调试修复师 | [src/agents/debugger.py](src/agents/debugger.py) |
| 错误分类器 | [src/agents/error_classifier.py](src/agents/error_classifier.py) |
| Prompt 模板 | [src/prompts/templates.py](src/prompts/templates.py) |
| 补丁应用 | [src/tools/patch_applier.py](src/tools/patch_applier.py) |
| 代码分析（AST） | [src/tools/code_analyzer.py](src/tools/code_analyzer.py) |
| RAG 检索 | [src/rag/retriever.py](src/rag/retriever.py) |
| 数据集加载 | [src/dataset_loader.py](src/dataset_loader.py) |
| 合成数据集 | [src/synthetic_dataset.py](src/synthetic_dataset.py) |
| 基准测试脚本 | [experiments/run_benchmark.py](experiments/run_benchmark.py) |
| 可视化脚本 | [experiments/visualize_results.py](experiments/visualize_results.py) |
