# AITester：逻辑驱动的多智能体测试生成与自修复系统

> AITester 是一个基于多智能体协作的 Python 自动化测试生成与自修复框架。
> 核心创新：**逻辑驱动思维链（Logic-driven CoT）** + **分层错误修复机制（Hierarchical Repair）**。

## 快速开始

```bash
# 0. 创建虚拟环境（推荐 Python 3.10+）
python3 -m venv .venv
source .venv/bin/activate

# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key 等信息

# 3. 初始化数据库（可选，如需持久化实验数据）
python init_db.py

# 4. 运行单个文件测试
python main.py run examples/calculator.py --func divide

# 5. 批量基准测试（内置示例数据集，三种基线对比）
python experiments/run_benchmark.py --dataset examples --baselines aitester,plain_llm,single_agent

# 6. 仅运行完整系统 + 限制任务数
python experiments/run_benchmark.py --dataset examples --task-limit 2

# 7. 消融实验：仅启用 Planner
ENABLE_PLANNER=true ENABLE_DEBUGGER=false python experiments/run_benchmark.py --dataset examples

# 8. 运行合成数据集基准测试（无需外部下载，可自定义规模）
python experiments/run_benchmark.py --dataset synthetic --task-count 50 --baselines aitester,plain_llm,single_agent

# 9. 可视化实验结果（含统计显著性检验）
python experiments/visualize_results.py
python experiments/visualize_results.py --results-dir experiments/results/synthetic_full

# 10. 并发执行基准测试（加速多任务处理）
BENCHMARK_PARALLELISM=4 python experiments/run_benchmark.py --dataset synthetic --task-count 20

# 11. 使用 --parallel 参数指定并行度
python experiments/run_benchmark.py --dataset examples --parallel 4

# 12. 使用 --timeout 参数设置全局超时
python main.py run examples/calculator.py --func divide --timeout 120

# 13. 使用 --json 参数输出 JSON 格式结果
python experiments/run_benchmark.py --dataset examples --json
```

## 性能优化说明

### RAG 检索器单例化

系统已实现 RAG 检索器的**懒加载单例模式**，在整个工作流执行期间只初始化一次 ChromaDB 客户端，避免重复加载嵌入模型（约 100MB）和打开向量索引的开销。

**性能收益**：每个任务节省 2-6 秒初始化时间。

**技术实现**：`src/graph/workflow.py` 中的 `get_rag_retriever()` 函数。

### LLM 调用超时配置

通过 `LLM_TIMEOUT` 配置项控制单次 LLM 调用的超时时间，防止 API 响应过慢导致任务卡死。

```bash
# .env 文件配置
LLM_TIMEOUT=60          # 单次 LLM 调用超时（秒），默认 60
LLM_RETRY_WAIT=30       # LLM 重试等待时间（秒），默认 30
EXECUTION_TIMEOUT=30    # pytest 执行超时（秒），默认 30
```

### 并发执行（BENCHMARK_PARALLELISM）

支持多线程并行执行多个 benchmark 任务，显著缩短大批量测试的总耗时。

```bash
# 使用 4 个线程并行执行（环境变量方式）
BENCHMARK_PARALLELISM=4 python experiments/run_benchmark.py --dataset synthetic --task-count 50

# 使用 --parallel 参数（命令行方式）
python experiments/run_benchmark.py --dataset synthetic --task-count 50 --parallel 4

# 串行执行（默认）
python experiments/run_benchmark.py --dataset synthetic --task-count 50
```

**注意**：并发执行需要为每个线程配置独立的 API Key，可通过 `LLM_1_*`, `LLM_2_*` 等多组配置实现 API Key 轮询。

更多细节请参考 [性能调优指南](docs/performance_guide.md)。

### 超时控制（--timeout）

通过 `--timeout` 参数或 `EXECUTION_TIMEOUT` 环境变量控制单次测试执行的超时时间，防止任务卡死。

```bash
# 命令行指定超时（秒）
python main.py run examples/calculator.py --func divide --timeout 120

# 或环境变量方式
EXECUTION_TIMEOUT=120 python main.py run examples/calculator.py --func divide
```

超时后测试被强制终止，状态标记为 `timeout`，Debugger 可针对超时场景进行专项修复。

### JSON 输出模式（--json）

通过 `--json` 参数将实验结果以结构化 JSON 格式输出到控制台，便于程序化处理或管道传输。

```bash
# 输出结构化 JSON 结果
python experiments/run_benchmark.py --dataset examples --json

# 结合 --output-dir 保存 JSON 文件
python experiments/run_benchmark.py --dataset examples --output-dir ./results --json
```

JSON 输出包含完整的结果统计、各基线详细数据和性能指标，可直接用于后续分析脚本。

更多细节请参考 [性能调优指南](docs/performance_guide.md)。

## 项目结构

```
AITester/
├── src/                              # 核心源代码
│   ├── agents/                       # 多智能体模块
│   │   ├── base_agent.py             # 智能体基类（LLM 调用、JSON 解析）
│   │   ├── planner.py                # 测试规划师（含逻辑驱动思维链）
│   │   ├── generator.py              # 测试代码生成器（支持 RAG 增强）
│   │   ├── executor.py               # 测试执行器（带超时和重试）
│   │   ├── debugger.py               # 调试修复师（分层错误修复）
│   │   └── error_classifier.py       # 错误类型分类器（规则匹配）
│   ├── tools/                        # 工具函数模块
│   │   ├── code_analyzer.py          # AST 代码分析（精确替换，避免正则误匹配）
│   │   └── patch_applier.py          # 补丁应用（支持完整文件和单函数模式）
│   ├── graph/                        # 工作流编排模块
│   │   ├── workflow.py               # LangGraph 工作流图（支持消融开关）
│   │   └── state.py                  # 全局状态定义（TypedDict）
│   ├── prompts/                      # Prompt 模板模块
│   │   └── templates.py              # 各智能体的 System Prompt 集中管理
│   ├── db/                           # 数据库模块
│   │   └── mysql_client.py           # MySQL 单例客户端（任务、测试、修复记录）
│   ├── rag/                          # 检索增强生成模块
│   │   └── retriever.py              # ChromaDB 向量检索器（测试用例与修复案例）
│   └── dataset_loader.py             # 数据集加载层（SWE-bench / Defects4J-Python）
│   └── synthetic_dataset.py          # 合成数据集生成器（本地生成，无需外部下载）
├── experiments/                      # 实验脚本模块
│   ├── run_benchmark.py              # 批量基准测试（多基线对比 + 消融实验）
│   └── visualize_results.py          # 结果可视化（柱状图 + 详细表格 + 统计检验）
├── reproduce.sh                    # 一键实验复现脚本（quick/full 模式）
├── tests/                            # 单元测试
│   ├── test_code_analyzer.py
│   ├── test_error_classifier.py
│   ├── test_patch_applier.py
│   └── test_dataset_loader.py        # 数据集加载器测试（新增）
├── docs/                             # 文档
│   └── algorithm_design.md           # 算法设计与理论描述（新增）
├── examples/                         # 示例被测代码（含已知 bug）
│   ├── calculator.py                 # 计算器示例（除零、负数阶乘 bug）
│   ├── buggy_library.py              # 算法库示例（二分查找、排序合并等）
│   └── string_utils.py               # 字符串工具示例（回文、Caesar 密码等）
├── main.py                           # CLI 入口
├── config.py                         # 全局配置（含消融实验开关）
├── init_db.py                        # 数据库初始化脚本
├── setup.py                          # 包管理配置
├── requirements.txt                  # Python 依赖列表
├── Dockerfile                        # Docker 镜像定义
└── .env.example                      # 环境变量模板
```

## 核心方法

### 1. 逻辑驱动思维链（Logic-driven Chain-of-Thought）
Planner 在输出测试计划前，先对函数进行**输入域、输出域、前置条件、后置条件、边界情况**的显式分析，引导 Generator 按逻辑覆盖生成测试用例。

**技术实现**：
- [src/agents/planner.py](src/agents/planner.py) 中的 `PlannerAgent.plan()` 方法
- [src/prompts/templates.py](src/prompts/templates.py) 中的 `PLANNER_SYSTEM_PROMPT`

### 2. 分层错误修复机制（Hierarchical Repair Strategy）
将测试失败分为五类：**语法错误（syntax）、断言失败（assertion）、运行时异常（runtime）、超时（timeout）、未知（unknown）**，每类采用差异化修复策略。

**技术实现**：
- [src/agents/error_classifier.py](src/agents/error_classifier.py) 中的 `ErrorClassifier` 类（规则匹配）
- [src/agents/debugger.py](src/agents/debugger.py) 中的 `DebuggerAgent.debug()` 方法
- [src/prompts/templates.py](src/prompts/templates.py) 中的 `DEBUGGER_SYSTEM_PROMPT`

### 3. AST 精确代码替换
使用 `ast` 模块进行函数解析和替换，避免正则表达式在嵌套函数或同名函数场景下的误匹配问题。

**技术实现**：
- [src/tools/code_analyzer.py](src/tools/code_analyzer.py) 中的 `replace_function_code()` 函数
- [src/tools/patch_applier.py](src/tools/patch_applier.py) 中的 `apply_patch_to_code()` 函数

### 4. 检索增强生成（RAG）
使用 ChromaDB 存储历史成功测试用例和修复补丁，在 Generator 和 Debugger 生成前检索相似案例作为参考。

**技术实现**：
- [src/rag/retriever.py](src/rag/retriever.py) 中的 `TestCaseRetriever` 类
- 在 [src/graph/workflow.py](src/graph/workflow.py) 中通过 `ENABLE_RAG` 标志控制启用/禁用

### 5. 多基线对比与消融实验（新增）
支持四种实验配置，一键对比不同组件的贡献：

| 基线名称 | 配置 | 说明 |
|---------|------|------|
| `aitester` | Planner+Debugger 均启用 | 完整多智能体系统 |
| `plain_llm` | Planner+Debugger 均禁用 | 纯 LLM 单次调用基线 |
| `single_agent` | Planner+Debugger 合并为一次调用 | 单智能体对比基线 |

**消融实验开关**（在 [.env](.env) 或 [config.py](config.py) 中配置）：
```bash
ENABLE_PLANNER=true      # 启用 Planner（默认 true）
ENABLE_DEBUGGER=true     # 启用 Debugger 修复循环（默认 true）
ENABLE_RAG=false         # 启用 RAG 检索增强（默认 false）
```

### 6. 标准数据集集成（新增）
通过 `src/dataset_loader.py` 和 `src/synthetic_dataset.py` 支持多种数据集：

```python
from src.dataset_loader import SWEBenchDataset, load_dataset
from src.synthetic_dataset import SyntheticDataset

# 加载内置示例数据集（无需下载，3 个预定义 bug 任务）
dataset = load_dataset("examples")

# 加载 SWE-bench（需先下载数据）
dataset = SWEBenchDataset(subset="lite")  # 500 个任务
SWEBenchDataset.download_from_huggingface(subset="mini")

# 生成合成数据集（本地生成，无需外部数据）
dataset = SyntheticDataset(task_count=50, seed=42)
```

## 实验复现

### 环境要求
- Python 3.10+
- MySQL 5.7/8.0（可选，用于持久化实验数据）
- LLM API Key（如 OpenAI、DeepSeek 等）

### 复现步骤
```bash
# 1. 克隆仓库
git clone <repository-url>
cd AITester

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key 等信息

# 4. 初始化数据库（可选）
python init_db.py

# 5. 运行基准测试（内置示例数据集，三种基线对比）
python experiments/run_benchmark.py --dataset examples --baselines aitester,plain_llm,single_agent

# 6. 限制任务数量（快速验证）
python experiments/run_benchmark.py --dataset examples --task-limit 2

# 7. 查看结果
ls experiments/results/
python experiments/visualize_results.py
```

### 运行 SWE-bench 基准（需下载数据）
```bash
# 方式一：从 HuggingFace 下载 lite 子集（约 500 任务）
python -c "from src.dataset_loader import SWEBenchDataset; SWEBenchDataset.download_from_huggingface(subset='lite')"

# 方式二：手动下载后放入 ~/.cache/aitester/swe_bench/swe_bench_instances.jsonl

# 运行 benchmark
python experiments/run_benchmark.py --dataset swe_bench --subset lite --task-limit 10
```

### 结果文件说明

基准测试结果保存在 `experiments/results/` 目录下，格式为 JSON：
```
experiments/results/benchmark_<dataset>_<timestamp>.json  # 例：benchmark_examples_20260814_120000.json、benchmark_synthetic_20260814_120000.json
```
该目录已加入 `.gitignore`，不会提交到版本库。

---

## 合成数据集与统计检验

### 合成数据集
AITester 内置了 `SyntheticDataset`，可在不依赖 SWE-bench/Defects4J 的情况下生成任意规模的缺陷任务：
- 10 种预定义 bug 模式（除零、边界条件、逻辑错误等）
- 通过 `--task-count` 控制任务数量（建议 ≥ 50 以满足发表要求）
- 固定 seed 保证结果可复现

### 统计显著性检验
`visualize_results.py` 自动输出：
- **配对 t 检验**：比较基线间通过率的统计显著性
- **Mann-Whitney U 检验**：非参数检验作为补充
- **Cohen's d**：量化效应量大小
- **p 值热力图**：直观展示显著性差异

输出文件：
- `experiments/results/charts/statistical_significance.png`
- `experiments/results/charts/summary_stats.md`

---

## Docker 一键复现

使用 Docker 可以完全隔离执行环境，避免本地依赖冲突。

```bash
# 构建镜像（首次约需 5 分钟，取决于网络速度）
docker build -t aitester:latest .

# 运行 benchmark
docker run --rm \
  -v $(pwd):/workspace \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  aitester:latest \
  python experiments/run_benchmark.py --dataset examples --task-limit 1

# 运行单个文件测试
docker run --rm \
  -v $(pwd):/workspace \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  aitester:latest \
  python main.py run examples/calculator.py
```

## 单元测试

```bash
# 运行所有测试（当前 185 个用例全部通过）
.venv/bin/python -m pytest tests/ -v

# 运行测试并生成覆盖率报告
.venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing

# 运行指定模块测试
.venv/bin/python -m pytest tests/test_dataset_loader.py -v
```

**测试覆盖模块**（17 个文件，185 个用例）：

| 测试文件 | 用例数 | 覆盖范围 |
|---------|-------|---------|
| `test_base_agent.py` | 20 | JSON 提取、Python 代码块提取 |
| `test_planner.py` | 6 | PlannerAgent 规划逻辑序列化 |
| `test_generator.py` | 13 | parametrize 校验、import 修正、LLM 调用 |
| `test_debugger.py` | 5 | 错误诊断、RAG 注入、failed_cases 截断 |
| `test_executor.py` | 11 | 覆盖率解析、失败用例解析 |
| `test_workflow.py` | 11 | _should_debug 路由、工作流图构建 |
| `test_state.py` | 5 | AITesterState TypedDict 结构完整性 |
| `test_prompts.py` | 14 | 各智能体 System Prompt 完整性校验 |
| `test_retriever.py` | 7 | RAG 检索器增删查清功能 |
| `test_config.py` | 15 | MySQLClient 单例/事务、config.py 默认值 |
| `test_patch_applier.py` | 9 | 补丁应用（完整文件/单函数模式） |
| `test_patch_applier_boundary.py` | 10 | 补丁应用边界情况 |
| `test_code_analyzer.py` | 14 | AST 解析、圈复杂度、代码替换 |
| `test_error_classifier.py` | 12 | 五类错误分类与修复策略映射 |
| `test_dataset_loader.py` | 15 | 数据集加载器（InMemory/SWEBench） |
| `test_synthetic_dataset.py` | 18 | 合成数据集生成与确定性验证 |

## 配置说明

所有配置项统一在 [config.py](config.py) 中管理，通过 `.env` 文件注入：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `LLM_N_API_KEY` | LLM API 密钥（配置见 `config.local.example`）| 必填 |
| `MODEL_NAME` | LLM 模型名称 | agnes-2.5-flash |
| `MAX_ITERATIONS` | 最大修复迭代次数 | 3 |
| `COVERAGE_THRESHOLD` | 覆盖率阈值 | 80.0 |
| `EXECUTION_TIMEOUT` | pytest 执行超时（秒） | 30 |
| `LLM_TIMEOUT` | 单次 LLM 调用超时（秒） | 60 |
| `LLM_RETRY_WAIT` | LLM 重试等待时间（秒） | 30 |
| `ENABLE_PLANNER` | 启用 Planner（消融开关） | true |
| `ENABLE_DEBUGGER` | 启用 Debugger 修复循环（消融开关） | true |
| `ENABLE_RAG` | 启用 RAG 检索增强 | false |
| `BENCHMARK_PARALLELISM` | 批量测试并行度（0=串行） | 0 |
| `TEMPERATURE` | LLM 采样温度 | 0.2 |

---

## CLI 命令参考

### `python main.py run` — 运行单个测试任务

```
python main.py run <target_file> [OPTIONS]

参数：
  target_file    被测 Python 文件路径（必须存在）

选项：
  --func, -f          指定被测函数名，不指定则测试全部函数
  --max-iterations    最大修复迭代次数，默认 3
  --coverage-threshold  覆盖率阈值百分比，默认 80.0
  --timeout           pytest 执行超时（秒），覆盖 EXECUTION_TIMEOUT 配置
  --json              以 JSON 格式输出结果
```

**示例：**
```bash
# 测试单个函数
python main.py run examples/calculator.py --func divide

# 指定最大迭代次数
python main.py run examples/buggy_library.py --func binary_search --max-iterations 5

# JSON 输出结果
python main.py run examples/string_utils.py --func is_palindrome --json
```

### `python experiments/run_benchmark.py` — 批量基准测试

```
python experiments/run_benchmark.py [OPTIONS]

选项：
  --dataset, -d       数据集名称（examples/synthetic/swe_bench/defects4j_py）
  --subset, -s        数据子集（swe_bench_lite 等）
  --baselines, -b     基线方法列表，逗号分隔（默认：aitester,plain_llm,single_agent）
  --output-dir, -o    结果输出目录（默认：experiments/results）
  --verbose, -v       详细日志输出
  --task-limit, -n    限制运行任务数量
  --task-count, -c    合成数据集任务数量
  --parallel, -p      并行任务数（替代 BENCHMARK_PARALLELISM 环境变量）
  --timeout           全局执行超时（秒）
  --json              JSON 格式输出结果
```

**示例：**
```bash
# 快速验证（2 个任务，单基线）
python experiments/run_benchmark.py --dataset examples --task-limit 2 --baselines aitester

# 并行执行（4 线程，100 个合成任务）
python experiments/run_benchmark.py --dataset synthetic --task-count 100 \
    --baselines aitester,plain_llm,single_agent --parallel 4

# 仅运行 aitester 完整系统，JSON 输出
python experiments/run_benchmark.py --dataset examples --baselines aitester --json
```

### `python main.py list-examples` — 列出示例文件

```
python main.py list-examples
```

## 数据集说明

| 数据集名称 | 数据来源 | 任务数 | 下载要求 |
|-----------|---------|-------|---------|
| `examples` | 内置示例（calculator/buggy_library/string_utils） | 3 | 无需下载 |
| `synthetic` / `synth` | 本地生成，支持自定义规模 | 可配置 | 无需下载 |
| `swe_bench` | HuggingFace SWE-bench | 500 (lite) | 需调用 download_from_huggingface() |
| `defects4j_python` | Defects4J-Python 数据集 | 可变 | 需手动下载 |

更多细节请参考 [性能调优指南](docs/performance_guide.md) 和 [API 参考](docs/api_reference.md)。

## 技术栈

- **LLM 框架**: LangChain + LangGraph
- **数据库**: MySQL（pymysql 驱动）
- **向量数据库**: ChromaDB（RAG 模块）
- **测试框架**: pytest + pytest-cov
- **命令行**: Click
- **数据集**: SWE-bench / Defects4J-Python（通过 HuggingFace datasets 库加载）
- **可视化**: matplotlib + pandas

## 基准测试结果

### 内置示例数据集（examples，3 个任务）

| 任务 | 状态 | 覆盖率 | 迭代次数 | LLM 调用次数 |
|------|------|--------|----------|-------------|
| `calculator.py::divide` | ✅ PASS | 100% | 0 | 1 |
| `buggy_library.py::binary_search` | ✅ PASS | 100% | 1 | 2（含重试） |
| `string_utils.py::is_palindrome` | ✅ PASS | 75% | 0 | 1 |

**汇总**：成功率 **100%**，平均覆盖率 **91.7%**，平均耗时 **30.1s/任务**。

### 关键修复记录

- `_validate_parametrize` 由 regex 改为 ast 解析，解决嵌套列表导致参数误判问题
- `_patch_applier_node` 增加安全守卫（非空、≥10% 长度、含函数定义）
- Generator 二次 parametrize 校验，避免 LLM 反复生成相同错误代码


## 常见问题

### Q: 运行时报 `ModuleNotFoundError`

**原因**：测试文件与模块不在同一目录，Python 无法找到被测模块。
**解决**：确保 `target_file` 路径正确，或检查 `module_name` 配置。

### Q: LLM 返回非 JSON 格式

**原因**：模型输出不符合预期格式。
**解决**：检查 `.env` 中的 `MODEL_NAME` 和 `OPENAI_BASE_URL`，确保 API Key 有效。

### Q: 覆盖率始终为 0%

**原因**：覆盖率统计文件未生成或路径错误。
**解决**：检查 `pytest-cov` 是否正确安装，确认 `--cov` 参数传递。

### Q: 合成数据集成功率低（< 10%）

**原因**：合成数据集 bug 模式较复杂，单轮修复可能不足以覆盖所有场景。
**解决**：
1. 增加 `MAX_ITERATIONS`（默认 3，可调至 5）
2. 启用 RAG 增强：`ENABLE_RAG=true`
3. 使用更强大的模型（如 `gpt-4o` 替代 `gpt-4o-mini`）

---

## 许可证

MIT License
