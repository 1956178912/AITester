# AITester：逻辑驱动的多智能体测试生成与自修复系统

> AITester 是一个基于多智能体协作的 Python 自动化测试生成与自修复框架。
> 核心创新：**逻辑驱动思维链（Logic-driven CoT）** + **分层错误修复机制（Hierarchical Repair）**。

## 测试状态

| 指标 | 状态 |
|------|------|
| **总测试数** | ✅ 1038 collected |
| **单元测试** | ✅ 1038 passed, 0 skipped |
| **代码覆盖率** | 91% 总覆盖（核心模块：reports/generator 97% / mysql_client 100% / base_agent 98% / api_manager 96% / dataset_loader 95% / workflow 94% / code_analyzer 100% / planner 100% / analysis 90% / helpers 100% / logging_utils 88% / cli-app 64%） |
| **已知失败** | ✅ 0（RAG / 数据集下载测试已修复；CI 3.12/3.14 全绿） |
| **安全审查** | ✅ 无硬编码密钥（`.env*` / `.private` 已 gitignore）；日志脱敏过滤器已接入 CLI 入口（API Key / JWT 自动替换占位符） |
| **最新优化** | ✅ 0.9.11 批次：import 提取单一实现（逗号多模块完整捕获，executor 复用去双份正则）+ 故障转移模型路由语义修正 + MySQL 单例 DCL 线程安全 + RAG 初始化失败粘性标志 + 显著性检验 NaN/Inf 序列化修复（详见 [CHANGELOG 0.9.11](CHANGELOG.md)） |
| **核心模块覆盖** | ✅ mysql_client.py (100%), helpers.py (100%), llm_cache.py (100%), code_analyzer.py (100%), planner.py (100%), base_agent.py (98%), api_manager.py (96%), dataset_loader.py (95%), workflow.py (94%), cli/app.py (64%), logging_utils.py (88%) |
| **代码规范** | ✅ Ruff 检查全部通过（`ruff check` + `ruff format --check`，CI 固定 0.16.3） |
| **最近改动** | ✅ 0.9.11 批次：import 提取单一实现、故障转移模型路由、MySQL 单例 DCL、RAG 粘性标志、NaN/Inf 序列化修复等 14 项 + 27 个回归用例（详见 [CHANGELOG 0.9.11](CHANGELOG.md)） |

更多详情参见 [CHANGELOG.md](CHANGELOG.md)、[QUICKSTART.md](QUICKSTART.md)、[docs/api_reference.md](docs/api_reference.md)、[docs/usage_examples.md](docs/usage_examples.md)。

## 开发工具

### Lint 与格式化

项目使用 [Ruff](https://docs.astral.sh/ruff/) 进行代码检查和格式化（CI 固定 `0.16.3`，与 `requirements.lock` 一致，避免上游发版导致格式化门禁漂移）：

```bash
# 安装 ruff（固定与 CI 相同的版本）
pip install "ruff==0.16.3"

# 检查代码
ruff check .

# 自动修复可修复的问题
ruff check --fix .

# 格式化代码
ruff format .

# 检查格式化（不修改）
ruff format --check .
```

### Pre-commit Hooks

推荐使用 pre-commit hooks 在提交前自动执行检查：

```bash
# 安装 pre-commit
pip install pre-commit

# 安装 hooks
pre-commit install

# 手动运行所有 hooks
pre-commit run --all-files
```

### CI/CD

项目配置了 GitHub Actions 持续集成，支持：
- 多 Python 版本测试（3.12, 3.14；下限由锁定依赖决定：scipy 需 ≥3.12）
- Ruff lint 检查
- pytest 测试 + 覆盖率报告
- 依赖安全扫描（pip-audit；chromadb 1.5.9 命中 5 条已知漏洞（PYSEC-2026-311 重复两条 + PYSEC-2026-3813/3814/3815），因 PyPI 暂无修复版本而显式豁免，详见 ci.yml 注释与 CHANGELOG）
- requirements 与 requirements.lock 一致性校验（scripts/check_lock_sync.py）
- 测试失败诊断注解：测试步骤挂掉时自动把 FAILED/ERROR 用例清单写成 GitHub 注解（check-runs annotations API 可读，无需 admin 下载日志）

### 测试命令

```bash
# 运行所有单元测试
.venv/bin/python -m pytest tests/ -v

# 运行测试并显示覆盖率
.venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing

# 仅运行工作流集成测试（端到端编排）
.venv/bin/python -m pytest tests/test_workflow.py tests/test_workflow_extended.py -v

# 仅运行数据集加载测试
.venv/bin/python -m pytest tests/test_dataset_loader.py tests/test_dataset_loader_extended.py -v
```

## 快速开始

```bash
# 0. 创建虚拟环境（推荐 Python 3.12+；锁定依赖 scipy 要求 ≥3.12）
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

# 13. 基准结果以 JSON 输出（stdout 直接输出结构化 JSON，无需额外参数）
python experiments/run_benchmark.py --dataset examples
```

## 性能优化说明

### RAG 检索器单例化

系统已实现 RAG 检索器的**懒加载单例模式**，在整个工作流执行期间只初始化一次 ChromaDB 客户端，避免重复加载嵌入模型（约 100MB）和打开向量索引的开销。

**性能收益**：每个任务节省 2-6 秒初始化时间。

**技术实现**：`src/graph/workflow.py` 中的 `get_rag_retriever()` 函数。

### LLM 文件缓存（省 token）

`base_agent` 的 LLM 调用已接入**持久化文件缓存**（`src/cache/*.json`，按 `md5(prompt + system_prompt)` 命名）。相同输入第二次起直接命中缓存，不再消耗 token——在「免费额度用完即停」的模型供应商下可显著延长可用时长。

- **默认启用**；设环境变量 `AITESTER_LLM_CACHE=0` 可关闭；缓存目录可用 `AITESTER_LLM_CACHE_DIR` 覆盖。
- **仅缓存成功响应**：调用失败（如 403 额度用尽）不写缓存。
- 缓存是本地优化产物，`src/cache/` 已加入 `.gitignore`，不会提交。

```bash
export AITESTER_LLM_CACHE=0      # 临时关闭缓存（需要"换种思路重生成"时）
rm -rf src/cache                # 清空缓存，让所有 prompt 重新调用 LLM
```

### LLM 客户端复用（连接池共享）

`base_agent` 中的 LLM 客户端现在按配置**复用**，避免每次调用都新建客户端（含底层 HTTP 连接池）：

- **OpenAI 兼容路径**（`ChatOpenAI`）：按 `(model_name, temperature, api_key, base_url)` 缓存，上限 16 个（FIFO 驱逐）。
- **zai SDK 路径**（`ZhipuAiClient`）：按 `(api_key, base_url)` 缓存，上限 16 个。

**性能收益**：同一配置的多次 LLM 调用共享连接池，省去重复建连开销；多任务并发时连接池状态一致、行为更可预测。

**技术实现**：`src/agents/base_agent.py` 的 `_get_or_create_chat_client()` 与 `_get_or_create_zai_client()`。

### 模型额度探测（scripts/check_quota.py）

探测各已配置模型当前是「存活 / 免费额度用尽(403) / 限流 / key 失效 / 模型不存在」，每个模型仅发 1-token 请求，**不打印任何密钥**：

```bash
.venv/bin/python scripts/check_quota.py                      # 探测 .env.local 已配置的全部 LLM
.venv/bin/python scripts/check_quota.py --provider aliyun_bailian   # 扫某 provider 目录全模型
.venv/bin/python scripts/check_quota.py --models qwen-max,qwen-plus --provider aliyun_bailian
.venv/bin/python scripts/check_quota.py --dry-run           # 只列出将探测的目标，不发请求
```

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

### JSON 输出（基准结果默认行为）

`run_benchmark.py` 结束时始终将汇总结果以结构化 JSON 打印到 stdout（`--output-dir` 下同时落盘 `benchmark_<数据集>_<时间戳>.json`；加 `--save-state` 时各环节状态另存 `raw/<task_id>/`），可直接管道给 `jq` 等工具做程序化处理。注意：该脚本没有 `--json` 开关——JSON 输出是默认且唯一的结果输出形式。

```bash
# 结构化 JSON 结果直接输出到 stdout
python experiments/run_benchmark.py --dataset examples

# 结合 --output-dir 在目录下保存结果 JSON
python experiments/run_benchmark.py --dataset examples --output-dir ./results
```

JSON 输出包含完整的结果统计、各基线详细数据和性能指标，可直接用于后续分析脚本。

更多细节请参考 [性能调优指南](docs/performance_guide.md)。

## 项目结构

```
AITester/
├── src/                              # 核心源代码
│   ├── agents/                       # 多智能体模块
│   │   ├── base_agent.py             # 智能体基类（LLM 调用 + 文件缓存 + 客户端复用、JSON 解析）
│   │   ├── planner.py                # 测试规划师（含逻辑驱动思维链）
│   │   ├── generator.py              # 测试代码生成器（支持 RAG 增强）
│   │   ├── executor.py               # 测试执行器（带超时和重试）
│   │   ├── debugger.py               # 调试修复师（分层错误修复）
│   │   └── error_classifier.py       # 错误类型分类器（规则匹配）
│   ├── api/                          # API 配置管理
│   │   └── api_manager.py            # 多 LLM 配置 CRUD（.env.local / llm_configs.json）
│   ├── config/                       # 配置管理
│   │   ├── config_manager.py         # LLM 配置增删查
│   │   └── config_generator.py       # .env / llm_configs 模板生成
│   ├── datasets/                     # 数据集加载层
│   │   ├── dataset_loader.py         # SWE-bench / Defects4J-Python 加载
│   │   └── synthetic_dataset.py      # 合成数据集生成器（本地生成）
│   ├── cli/                          # 命令行界面（click 命令组 + rich 输出）
│   │   ├── app.py                    # CLI 命令定义与任务执行
│   │   └── output.py                 # ANSI/Rich 终端输出工具
│   ├── utils/                        # 公共工具
│   │   ├── exceptions.py             # 统一异常层级
│   │   ├── helpers.py                # 正则 / JSON / 代码块提取等工具
│   │   └── logging_utils.py          # 日志工具
│   ├── tools/                        # 工具函数模块
│   │   ├── code_analyzer.py          # AST 代码分析（精确替换，避免正则误匹配）
│   │   └── patch_applier.py          # 补丁应用（支持完整文件和单函数模式）
│   ├── graph/                        # 工作流编排模块
│   │   ├── workflow.py               # LangGraph 工作流图（支持消融开关）
│   │   ├── state.py                  # 全局状态定义（TypedDict）
│   │   └── llm_cache.py             # LLM 内存 LRU 缓存（可选，带命中统计）
│   ├── db/                           # 数据库模块
│   │   └── mysql_client.py           # MySQL 单例客户端（任务、测试、修复记录）
│   ├── rag/                          # 检索增强生成模块
│   │   └── retriever.py              # ChromaDB 向量检索器（测试用例与修复案例）
│   ├── reports/                      # 报告生成
│   │   └── generator.py             # 实验结果报告
│   └── experiments/                  # 实验分析
│       └── analysis.py               # 统计检验与结果分析
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
├── main.py                           # CLI 入口（薄封装，实现位于 src/cli/）
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
将测试失败分为八类：**导入失败（import_error）、语法错误（syntax）、类型不匹配（type_error）、断言失败（assertion）、测试逻辑错误（logic_error）、运行时异常（runtime）、超时（timeout）、未知（unknown）**，每类采用差异化修复策略（P2 细化：import/type/logic 三类从旧的五类中拆出，修复路径更精准）。

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

**消融实验开关**（在 [config.py](config.py) 中读取默认值，可通过 `.env` 注入环境变量覆盖；`.env` 已加入 `.gitignore`，不入库）：
```bash
ENABLE_PLANNER=true      # 启用 Planner（默认 true）
ENABLE_DEBUGGER=true     # 启用 Debugger 修复循环（默认 true）
ENABLE_RAG=false         # 启用 RAG 检索增强（默认 false）
```

### 6. 标准数据集集成（新增）
通过 `src/datasets/` 子包（`dataset_loader.py` + `synthetic_dataset.py`）支持多种数据集：

```python
from src.datasets import SWEBenchDataset, load_dataset
from src.datasets import SyntheticDataset

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
- Python 3.12+（锁定依赖 scipy 要求 ≥3.12）
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
python -c "from src.datasets import SWEBenchDataset; SWEBenchDataset.download_from_huggingface(subset='lite')"

# 方式二：手动下载后放入 ~/.cache/aitester/swe_bench/swe_bench_instances.jsonl

# 运行 benchmark
python experiments/run_benchmark.py --dataset swe_bench --subset lite --task-limit 10
```

### SWE-bench 加载质量校验与源码补充（P0）

官方 SWE-bench JSONL **不含被测源码字段**（只有 issue 文本 + 修复补丁），
直接跑基准时 LLM 看不到真实代码，结果只能验证流程、不能产生有效修复对比。
用以下两步排查/补全：

```bash
# 1. 校验加载质量（逐任务打印 instance_code/test_code 完整性 + 全量质量报告）
python main.py check-dataset swe_bench --subset lite

# 2. 提供源码补充文件（JSONL，按 instance_id 关联）：
#    {"instance_id": "r/r-1", "instance_code": "def f(): ...", "test_code": "def test_f(): ..."}
#    可通过 git checkout <base_commit> 导出目标文件内容生成
SWE_BENCH_ENRICHMENT=./swe_bench_enrichment.jsonl \
  python experiments/run_benchmark.py --dataset swe_bench --task-limit 10
```

目标函数定位：加载器会从官方 `patch` 的 hunk 头自动提取目标函数名
（`metadata["suggested_function"]`，本地缓存 225 任务实测提取率 96%），
benchmark 用它初始化 `target_function`，驱动 Planner/Generator/Debugger
的 **AST 聚焦截取**——大源文件不再"头尾各半"硬截断，而是保留
import + 目标函数 + 其直接调用的辅助函数（见 `src/tools/code_context.py`）。

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

## 执行隔离与依赖管理（P1）

本地执行默认跑在系统 Python：被测代码 import 的第三方库缺失时测试直接失败，
且无法区分"代码 bug"与"环境缺依赖"，不同任务的依赖还会互相冲突。
开启 venv 沙箱后，每个任务在临时目录 + 按依赖组合缓存的隔离 venv 中执行，
`PYTHONPATH` 仅指向沙箱目录：

```bash
# 隔离 venv 执行（缺失依赖只会被检测记录，测试结果仍正常产出）
EXECUTOR_USE_VENV=true python experiments/run_benchmark.py --dataset swe_bench --task-limit 10

# 执行前自动 pip install 缺失依赖（只装入 venv，不污染系统环境）
EXECUTOR_USE_VENV=true EXECUTOR_AUTO_INSTALL_DEPS=true \
  python experiments/run_benchmark.py --dataset swe_bench --task-limit 10
```

- venv 按"缺失包组合"做磁盘缓存（`~/.cache/aitester/venvs/`），相同依赖的任务复用；
- 缺失依赖会写入结果的 `error_info.missing_dependencies`，由错误分类器归为
  独立的 `import_error` 类别（区别于代码写错语法的 `syntax`）；
- 依赖安装失败时直接提前返回 `dependency_install_failed`，避免测试结果误导分析。

## RAG 检索增强与质量指标（P1）

RAG 默认关闭（`ENABLE_RAG=false`）。开启后 Generator/Debugger 会检索
相似历史案例；检索库持久化到 `rag_data/`（`RAG_PERSIST_PATH` 可配），
**跨实验运行可复用**，TTL 默认 7 天（`RAG_TTL_SECONDS`）：

```bash
# 显式开启 RAG 跑消融实验（检索库跨次运行累积）
python experiments/run_benchmark.py --dataset synthetic --enable-rag

# 查看 RAG 检索质量指标（结果 JSON 的 results.<baseline>.rag_metrics：
# retrievals / hits / hit_rate / avg_max_similarity；JSON 为默认输出，无需开关）
python experiments/run_benchmark.py --dataset synthetic --enable-rag
```

单独评估检索库质量（Hit Rate@k / MRR，针对已知标注查询）：

```python
from src.rag.retriever import TestCaseRetriever

retriever = TestCaseRetriever(persist_path="rag_data")
metrics = retriever.evaluate_retrieval(
    [{"query": "def add(a, b): ...", "expected_id": "<入库时的 doc_id>"}],
    top_k=5,
)
# → {"num_queries": 1, "hits": 1, "hit_rate": 1.0, "mrr": 1.0}
```

## 效率指标与基线对比排查（P0）

每次基准运行自动记录 token 消耗（结果 JSON 的 `results.<baseline>.token_metrics`
与逐任务 `token_usage`），用于"完整系统 vs Plain LLM 性价比"对比。
若发现基线反超，用对比工具定位差异环节：

```bash
# 1. 双基线跑一遍并落盘环节级产物（测试计划/生成代码/诊断/补丁）
python experiments/run_benchmark.py --dataset synthetic \
    --baselines aitester,plain_llm --save-state

# 2. 找出"plain_llm 成功但 aitester 失败"的任务，逐环节对比 + 输出 Markdown 报告
python experiments/compare_failures.py \
    --results experiments/results/benchmark_synthetic_<ts>.json \
    --raw-dir experiments/results/raw --max-tasks 5 \
    --report experiments/results/failure_analysis.md
```

报告会对每个翻转任务给出"疑似环节"提示（Planner 噪声 / Debugger 未收敛 /
环境依赖失败），并汇总 token 对比。

---

## Docker 一键复现

使用 Docker 可以完全隔离执行环境，避免本地依赖冲突。

```bash
# 构建镜像（首次约需 5 分钟，取决于网络速度）
docker build -t aitester:latest .

# 运行 benchmark
# LLM 密钥随 $(pwd) 的 .env.local 一并挂载进容器，无需 -e 传递（旧 OPENAI_API_KEY 变量已废弃）
docker run --rm \
  -v $(pwd):/workspace \
  aitester:latest \
  python experiments/run_benchmark.py --dataset examples --task-limit 1

# 运行单个文件测试
docker run --rm \
  -v $(pwd):/workspace \
  aitester:latest \
  python main.py run examples/calculator.py
```

## 单元测试

```bash
# 运行所有测试（当前 1038 个用例，全量通过）
.venv/bin/python -m pytest tests/ -v

# 运行测试并生成覆盖率报告
.venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing

# 运行指定模块测试
.venv/bin/python -m pytest tests/test_dataset_loader.py -v
```

**测试覆盖模块**（41 个测试文件，1038 个 pytest 收集用例，src 总覆盖率 91%）：

| 测试文件 | 测试函数数 | 覆盖范围 |
|---------|-------|---------|
| `test_api_manager.py` | 62 | API 管理器（轮询/加权随机/健康感知策略、健康线程开关、失败阈值配置接线） |
| `test_api_manager_extended.py` | 62 | API 管理器扩展路径（健康恢复、限流标记） |
| `test_base_agent.py` | 39 | JSON 提取、代码块提取、客户端复用、AST 智能截取 |
| `test_base_agent_extended.py` | 46 | 指数退避重试、LLM 缓存、zai 客户端复用 |
| `test_cli_app.py` | 11 | CLI 命令（list-examples/--version/参数校验） |
| `test_cli_parallel.py` | 10 | 并发派发器 `_dispatch_parallel_tasks` 与 `run` 并发分支回归（rich/无 rich 双路径、逐任务容错、CI 门控 exit 1）（0.9.10） |
| `test_cli_run.py` | 6 | run 命令编排（超时/覆盖率阈值透传） |
| `test_code_analyzer.py` | 17 | AST 解析、圈复杂度、代码替换 |
| `test_code_context.py` | 11 | AST 智能截取（P0 大文件上下文） |
| `test_complex_logic.py` | 12 | 复杂业务逻辑（邮箱验证等） |
| `test_config_generator.py` | 26 | LLM 配置生成器模板 |
| `test_config_manager.py` | 29 | 配置管理器（LLM 配置增删） |
| `test_config.py` | 14 | config.py 默认值与容错解析 |
| `test_core_modules.py` | 19 | 核心模块冒烟 |
| `test_dataset_loader.py` | 76 | 数据集加载器（InMemory/SWEBench） |
| `test_dataset_loader_extended.py` | 57 | 数据集加载扩展路径（raw 加载/字段校验） |
| `test_dataset_validation.py` | 14 | SWE-bench 加载质量校验与源码补充（P0） |
| `test_debugger.py` | 29 | 错误诊断、RAG 注入、分类透传 |
| `test_dependency.py` | 27 | 依赖检测与 venv 管理（P1） |
| `test_error_classifier.py` | 56 | 八类错误分类与修复策略映射（P2 细化） |
| `test_exceptions.py` | 33 | 自定义异常类与装饰器 |
| `test_executor.py` | 35 | 覆盖率解析、失败用例解析 |
| `test_executor_sandbox.py` | 7 | 沙箱执行路径与依赖安装（P1） |
| `test_experiments_analysis.py` | 11 | 实验结果分析（排名/统计） |
| `test_experiments_scripts.py` | 8 | visualize 结果选择 / 标准化实验返回键 / benchmark 并行度回归（0.9.9） |
| `test_generator.py` | 21 | parametrize 校验、import 修正、LLM 调用 |
| `test_llm_cache.py` | 16 | LLM 内存缓存 |
| `test_llm_file_cache.py` | 4 | LLM 文件缓存命中/失效 |
| `test_mysql_client.py` | 12 | MySQL 客户端单例/事务/连接池参数 |
| `test_packaging.py` | 3 | 打包完整性（子包 __init__ 齐全） |
| `test_patch_applier.py` | 36 | 补丁应用（完整文件/单函数模式） |
| `test_planner.py` | 5 | PlannerAgent 规划逻辑序列化 |
| `test_rag_metrics.py` | 5 | RAG 检索质量指标 Hit Rate/MRR（P1） |
| `test_rag_retriever.py` | 29 | RAG 检索器增删查清与持久化 |
| `test_report_generator.py` | 48 | 错误报告生成器（含八类分类分支） |
| `test_run_benchmark.py` | 4 | benchmark 结果构造与异常路径回归（0.9.8 去重重构） |
| `test_string_utils.py` | 10 | 字符串工具 |
| `test_synthetic_dataset.py` | 5 | 合成数据集生成与确定性验证 |
| `test_token_usage.py` | 9 | token 消耗统计（P0 效率指标） |
| `test_workflow.py` | 28 | 工作流图构建与路由 |
| `test_workflow_extended.py` | 35 | 工作流扩展路径（RAG 初始化单例、planner 默认计划去重等） |

## 配置说明

所有配置项统一在 [config.py](config.py) 中管理，通过 `.env` 和 `.env.local` 文件注入：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `LLM_N_API_KEY` | LLM API 密钥（支持多配置，见 `config.local.example`）| 必填 |
| `LLM_N_BASE_URL` | LLM Base URL | - |
| `LLM_N_MODEL_NAME` | LLM 模型名称 | agnes-3.0-flash |
| `MODEL_NAME` | 向后兼容：默认 LLM 模型名称 | agnes-3.0-flash |
| `MAX_ITERATIONS` | 最大修复迭代次数 | 3 |
| `COVERAGE_THRESHOLD` | 覆盖率阈值 | 80.0 |
| `EXECUTION_TIMEOUT` | pytest 执行超时（秒） | 30 |
| `LLM_TIMEOUT` | 单次 LLM 调用超时（秒） | 60 |
| `LLM_RETRY_WAIT` | LLM 重试等待时间（秒） | 30 |
| `ENABLE_PLANNER` | 启用 Planner（消融开关） | true |
| `ENABLE_DEBUGGER` | 启用 Debugger 修复循环（消融开关） | true |
| `ENABLE_RAG` | 启用 RAG 检索增强 | false |
| `RAG_PERSIST_PATH` | RAG 持久化路径（空=内存模式，默认项目根 rag_data/） | rag_data |
| `RAG_COLLECTION_NAME` | RAG ChromaDB 集合名 | aitester_cases |
| `RAG_TTL_SECONDS` | RAG 缓存 TTL（秒，持久化场景默认 7 天） | 604800 |
| `EXECUTOR_USE_VENV` | venv 沙箱隔离执行（依赖隔离，P1） | false |
| `EXECUTOR_AUTO_INSTALL_DEPS` | 执行前自动 pip install 缺失依赖（P1） | false |
| `EXECUTOR_DEP_INSTALL_TIMEOUT` | 依赖安装超时（秒） | 120 |
| `MYSQL_POOL_MIN_CACHED` | 连接池最小预留连接 | 5 |
| `MYSQL_POOL_MAX_CACHED` | 连接池最大空闲连接 | 10 |
| `MYSQL_POOL_MAX_CONNECTIONS` | 连接池最大连接总数 | 20 |
| `MYSQL_POOL_TIMEOUT` | 获取连接等待超时（秒） | 30 |
| `SWE_BENCH_ENRICHMENT` | SWE-bench 源码补充 JSONL 路径（P0，可选） | 无 |
| `BENCHMARK_PARALLELISM` | 批量测试并行度（0=串行） | 0 |
| `TEMPERATURE` | LLM 采样温度 | 0.2 |

### 多 LLM 配置支持

系统支持配置多个 LLM Provider，实现 API Key 轮询和高可用：

```bash
# .env.local 配置示例
LLM_1_API_KEY=sk-key-1
LLM_1_BASE_URL=https://api.provider1.com/v1
LLM_1_MODEL_NAME=model-1

LLM_2_API_KEY=sk-key-2
LLM_2_BASE_URL=https://api.provider2.com/v1
LLM_2_MODEL_NAME=model-2
```

代码中使用：
```python
from config import LLM_CONFIGS, DEFAULT_LLM_CONFIG

# 获取所有配置
all_configs: list[LLMConfig] = LLM_CONFIGS
# 获取默认配置（第一个）
default_config: LLMConfig | None = DEFAULT_LLM_CONFIG
```

更多配置详情参见 [docs/api_reference.md](docs/api_reference.md) 和 [config.local.example](config.local.example)。

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
  --json              以 JSON 格式输出结果（stdout 仅承载纯 JSON，日志/进度条走 stderr，便于管道给 jq）
```

> **退出码**：任一测试任务失败（含任务崩溃）时进程以 `1` 退出，全部通过以 `0` 退出，可在 CI/脚本中当作门控工具使用。

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
  --enable-rag        显式开启 RAG 检索增强（P1 消融实验；默认沿用 config.ENABLE_RAG）
  --save-state        环节级状态落盘到 <output-dir>/raw/（P0 基线对比排查用）
```

**示例：**
```bash
# 快速验证（2 个任务，单基线）
python experiments/run_benchmark.py --dataset examples --task-limit 2 --baselines aitester

# 并行执行（4 线程，100 个合成任务）
python experiments/run_benchmark.py --dataset synthetic --task-count 100 \
    --baselines aitester,plain_llm,single_agent --parallel 4

# 仅运行 aitester 完整系统（JSON 为默认输出，无需 --json 开关）
python experiments/run_benchmark.py --dataset examples --baselines aitester
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

更多细节请参考 [性能调优指南](docs/performance_guide.md)、[API 参考](docs/api_reference.md) 和 [使用示例](docs/usage_examples.md)。

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

### 合成数据集实验（50个任务，3种基线对比）

| 基线方法 | 成功率 (%) | 平均覆盖率 (%) | 平均迭代次数 | 平均耗时 (s) |
|---------|-----------|---------------|-------------|-------------|
| **AITester** | **68.0** | **98.0** | 1.26 | 47.2 |
| Plain LLM | 68.0 | 95.2 | 1.10 | 348.3 |
| Single Agent | 22.0 | 71.1 | 0.62 | 17.3 |

**关键发现**：
- AITester 与 Plain LLM 成功率相当，但覆盖率更高（98.0% vs 95.2%）
- AITester 执行速度提升 **7.4倍**（47.2s vs 348.3s），体现多智能体协作效率
- Single Agent 基线表现显著较差（22.0%），验证多智能体架构的必要性
- 统计检验显示 AITester vs Single Agent 差异显著（p < 0.001, Cohen's d = 0.848）

详细结果参见 [experiments/results/synthetic_50_final/charts/](experiments/results/synthetic_50_final/charts/)

### SWE-bench Lite 实验（20个任务）

当前处于实验阶段，受API限流影响，已完成7个任务。详细结果将在API配额恢复后补充。

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
**解决**：检查 `.env.local` 中的 `LLM_N_*` 配置（模型名、Base URL），确保 API Key 有效。

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

## 论文与文档

### 学术论文

完整论文草稿：[paper.md](paper.md)

**摘要**：
> AITester 是一个基于多智能体协作的 Python 自动化测试生成与自修复框架。核心创新包括逻辑驱动思维链（Logic-driven CoT）和分层错误修复协议（Hierarchical Repair）。在合成数据集（50任务）上的实验表明，AITester 达到 68% 成功率，98% 平均覆盖率，相比单智能体基线（22%）具有统计显著性优势（p < 0.001）。

### 技术文档

- [算法设计文档](docs/algorithm_design.md)：核心算法形式化描述
- [失败案例分析](docs/failure_analysis.md)：32% 失败率的根因分析与改进路线图
- [性能调优指南](docs/performance_guide.md)：并发执行、RAG单例化、超时配置
- [API参考文档](docs/api_reference.md)：模块接口说明

---

## 贡献指南

欢迎贡献代码！请阅读 [贡献指南](CONTRIBUTING.md) 了解如何参与项目开发。

---

## 迭代优化记录

### v0.10 (2026-08-18) — 第二轮迭代：性能优化与依赖锁定

**核心成果**:
- **测试扩展**: 653+ → 696+ 个用例（新增 40+ 个）
- **性能优化报告**: 识别 3 个高优先级瓶颈（缓存、健康检查、连接池）
- **API 管理器增强**: 支持多 Provider 轮询和高可用故障转移
- **依赖锁定**: 生成 requirements.lock 确保可复现构建

**性能优化实施**:
- ✅ RAG 检索器单例化（节省 2-6 秒/任务初始化时间）
- ✅ LLM 调用超时配置（防止 API 响应卡死）
- ✅ 并发执行支持（BENCHMARK_PARALLELISM 环境变量）
- 🔲 LLM 缓存键修复（使用 MD5 替代 hash()）
- 🔲 数据库连接池（待实施）

**新增测试模块**:
| 测试文件 | 用例数 | 覆盖范围 |
|---------|-------|---------|
| `test_api_manager.py` | 17 | API 管理器策略测试 |
| `test_base_agent_extended.py` | 46 | 指数退避重试、LLM 缓存、zai 客户端复用 |
| `test_report_generator.py` | 13 | 错误报告生成器 |

### v0.9 (2026-08-18) — 代码质量优化 + 错误报告生成器

**核心成果**:
- **Ruff 问题修复**: 791 → 61 (92% 修复率)
- **测试扩展**: 147 → 653+ 个用例
- **新增模块**: `src/reports/` 错误报告生成器
- **多 LLM 配置**: `LLM_CONFIGS` 支持 API Key 轮询

**变更详情**:
- 新增错误报告生成器，支持文本/JSON/Markdown 三种格式
- 修复未使用变量和过时类型注解
- 优化 LLM token 消耗（压缩 Prompt 和代码截断）
- 完善指数退避重试逻辑和路径安全检查

### v0.2.0 (2026-08-17) — 工程化改进

- Ruff Lint 配置、Pre-commit Hooks、GitHub Actions CI
- 并发执行支持 (`BENCHMARK_PARALLELISM`)
- RAG 检索器单例化优化

### v0.1.0 (2026-08-14) — 初始版本

- 四智能体协作架构
- 支持 examples/synthetic/swe_bench 数据集
- Docker 一键复现

---

## 许可证

MIT License
