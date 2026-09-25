> **语言 / Language**：[English](README.en.md) | 简体中文（本文）

# AITester：逻辑驱动的多智能体测试生成与自修复系统

> AITester 是一个基于多智能体协作的 Python 自动化测试生成与自修复框架。
> 核心创新：**逻辑驱动思维链（Logic-driven CoT）** + **分层错误修复机制（Hierarchical Repair）**。

## 测试状态

| 指标 | 状态 |
|------|------|
| **总测试数** | ✅ 1667 collected（全量依赖）/ 精简环境（缺 chromadb/matplotlib 时 RAG/可视化用例自动跳过，约 1607 collected） |
| **单元测试** | ✅ 全量 1667 passed, 0 failed；精简环境约 1607 passed（`skipif`/`importorskip` 优雅降级，非误报 ERROR） |
| **代码覆盖率** | 94% 总覆盖（src/；0.10 深度审查修复 4 处 + 新增 2 条回归用例后 1667 全绿；核心模块：base_agent 100% / api_manager 94% / dataset_loader 94% / graph/nodes.py 95% / code_analyzer 100% / planner 100% / dependency 96% / multi_candidate 94% / cross_file 95% / rag/retriever 95%） |
| **已知失败** | ✅ 0（RAG / 数据集下载测试已修复；CI 3.12/3.14 全绿；缺可选依赖时相关用例 `skipif` 跳过而非报错） |
| **安全审查** | ✅ 无硬编码密钥（`.env*` / `.env.local.bak` / `.private` 已 gitignore / 删除）；日志脱敏三层防线（Handler 层 SensitiveFilter/Formatter + 入口接线 + trace JSONL 旁路脱敏）；APIManager 日志点就地 `_redact()`（不依赖入口接线，嵌入式安全）；`get_status()` 出口 base_url 脱敏；**三条执行链路（本地/venv/Docker）统一剔除 LLM 凭证（`credential_scrub.scrub_os_environ` 动态模式，覆盖 `LLM_N_API_KEY` 全部编号，封堵生成代码继承宿主凭证的泄露面）**；LLM 文件缓存记录为已知可接受风险（本地可信域，不进 git） |
| **最新优化** | ✅ 2026-09-25 0.10 深度审查修复（LLM 缓存负缓存 TTL 正确性回归 + 路径白名单根归一口径修正 + 追踪层冗余摘要消除 + 统计接口免重扫；全量 1667 passed / 零回归 / mypy 0 错误 / ruff 全绿）；此前 0.9 轮次 LRU 快路径 + 双套缓存漂移消除 + 0.8 全面审查修复，详见 [CHANGELOG](CHANGELOG.md) |
| **核心模块覆盖** | ✅ code_analyzer.py (100%), helpers.py (100%), planner.py (100%), base_agent.py (100%), mysql_client.py (98%), token_usage.py (98%), reports/generator.py (99%), api_manager.py (94%), rag/retriever.py (95%), dataset_loader.py (94%), graph/nodes.py (95%), config/config_manager.py (95%), multi_candidate.py (94%), observability/trace.py (98%), error_classifier.py (95%), cli/app.py (93%), cli/output.py (94%), logging_utils.py (95%), tools/dependency.py (96%), executor_modes.py (96%), cross_file.py (95%), credential_scrub.py (100%) |
| **代码规范** | ✅ Ruff 检查全部通过（`ruff check` + `ruff format --check`，CI 固定 0.16.3；0.6 轮次 15 告警清零 + 33 文件 format 归一 + 全面审查轮次 5 处 tests/ 瑕疵清零） |
| **最近改动** | ✅ 2026-09-24 全面审查修复：凭证脱敏动态模式化（新增 `src/utils/credential_scrub.py`，本地/venv/Docker 三条链路统一，覆盖 `LLM_N_API_KEY` 全部编号）+ CLI `finally` 块脆弱代码消除（`final_state` 显式初始化）+ 多候选节点无副作用化（统计改经 update dict 传递）+ 补丁函数定位正则→AST（装饰函数/含注释函数体不再被过早截断）+ `requirements.txt` 显式声明 `openai==2.54.0`；详见 [CHANGELOG](CHANGELOG.md) |

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
# 运行所有单元测试（全量 1667 个用例；缺 chromadb/matplotlib 时 RAG/可视化用例自动 skip，约 1607 个收集）
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

**技术实现**：`src/graph/rag.py` 中的 `get_rag_retriever()` 函数（经 `workflow.py` re-export 保持旧导入路径）。

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
│   │   ├── base_agent.py             # 智能体基类（LLM 调用 + 文件缓存 + JSON 解析；客户端工厂已拆至 llm_client.py）
│   │   ├── llm_client.py             # LLM 客户端工具函数（ChatOpenAI 工厂 + 模块级连接池缓存，0.1 拆分）
│   │   ├── planner.py                # 测试规划师（含逻辑驱动思维链）
│   │   ├── generator.py              # 测试代码生成器（支持 RAG 增强）
│   │   ├── executor.py               # 测试执行器（类主体 + 本地执行编排；导入修复/结果解析/沙箱与 Docker 模式/子进程基础设施已拆至 executor_* 子模块）
│   │   ├── executor_imports.py       # 导入路径自动修复（模块名提取 / sys.path 注入 / 相似名替换，0.1 拆分）
│   │   ├── executor_modes.py         # venv 沙箱 + Docker 隔离执行模式（0.1 拆分）
│   │   ├── executor_output.py        # 执行结果解析（覆盖率 / 失败用例 / 错误信息，0.1 拆分）
│   │   ├── executor_runtime.py       # 子进程运行、重试与临时资源清理（0.1 拆分）
│   │   ├── debugger.py               # 调试修复师（分层错误修复）
│   │   └── error_classifier.py       # 错误类型分类器（规则匹配）
│   ├── api/                          # API 配置管理
│   │   ├── api_manager.py            # 多 LLM 配置 CRUD（.env.local / llm_configs.json）+ 熔断/路由
│   │   └── api_health.py             # API 健康状态与路由策略数据模型（APIHealth/APIManagerConfig/RotationStrategy）
│   ├── config/                       # 配置管理
│   │   ├── config_manager.py         # LLM 配置增删查
│   │   └── config_generator.py       # .env / llm_configs 模板生成
│   ├── datasets/                     # 数据集加载层
│   │   ├── dataset_loader.py         # SWE-bench 加载器 + 数据模型 / 抽象基类 / 工厂函数（Defects4J 与 InMemory 子类已拆出）
│   │   ├── dataset_defects4j.py      # Defects4J-Python 加载器（0.1 拆分）
│   │   ├── dataset_inmemory.py       # 内置示例数据集（0.1 拆分）
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
│   │   ├── patch_applier.py          # 补丁应用（支持完整文件和单函数模式）
│   │   ├── code_context.py           # AST 智能截取（P0 大文件上下文优化）
│   │   ├── dependency.py             # 依赖检测与 venv 缓存管理（P1 执行隔离）+ 4.4 命中率统计/清理
│   │   ├── multi_candidate.py        # 多候选补丁生成与验证筛选（3.1，默认关）
│   │   └── cross_file.py             # 3.5 跨文件修复（协调器-提议者架构，默认关）
│   ├── graph/                        # 工作流编排模块
│   │   ├── workflow.py               # LangGraph 工作流图（支持消融开关；节点注册与 RAG 接线）
│   │   ├── nodes.py                  # 节点函数实现（_planner/_generator/_executor/_debugger/_patch_applier/_cross_file_analyzer）
│   │   ├── rag.py                    # RAG 检索器单例管理（get_rag_retriever，经 workflow.py re-export）
│   │   ├── tracing.py                # 追踪层接线（任务级 JSONL 会话，经 workflow.py re-export）
│   │   ├── state.py                  # 全局状态定义（TypedDict）+ create_initial_state 工厂（单一构造点）
│   │   └── token_usage.py            # 线程局部 LLM token 用量统计（P0 效率指标）
│   ├── observability/                # 结构化可观测性（4.1）
│   │   └── trace.py                  # JSONL 节点级追踪（默认关，AITESTER_TRACE_DIR 启用）
│   ├── prompts/                      # 提示词模板
│   │   └── templates.py              # Planner/Generator/Debugger 系统提示词（PLANNER_SYSTEM_PROMPT 等）
│   ├── db/                           # 数据库模块
│   │   └── mysql_client.py           # MySQL 单例客户端（任务、测试、修复记录）
│   ├── rag/                          # 检索增强生成模块
│   │   └── retriever.py              # ChromaDB 向量检索器（测试用例与修复案例）
│   ├── reports/                      # 报告生成
│   │   └── generator.py             # 实验结果报告
│   └── experiments/                  # 实验分析
│       └── analysis.py               # 统计检验与结果分析
├── experiments/                      # 实验脚本模块
│   ├── run_benchmark.py              # 批量基准测试（多基线对比 + 消融实验 + 公平性 token 输出）
│   ├── visualize_results.py          # 结果可视化（柱状图 + 详细表格 + 统计检验）
│   ├── analyze_results.py            # 结果分析脚本（4.3 + 1.1/1.2/1.3/3.2/4.4：Markdown 汇总 + RAG 自动汇总 + 修复收敛/质量代理指标 + 异味检测 + 变异得分 + 边界覆盖 + 执行轨迹 + 缓存命中率，旧 JSON 兜底）
│   ├── compare_failures.py           # 失败翻转任务对比（Planner/Debugger/环境归因 + 5.3 跨批次失败模式对比）
│   ├── analyze_failures.py           # 失败案例聚类报告（供技术评审使用）
│   ├── mutation_testing.py           # 1.2 内置变异测试生成器（AST 级三类变异体 + mutation_score_from_details 汇总）
│   ├── contamination_check.py        # 2.1 SWE-bench 数据污染检测（token 级 Jaccard 重叠度）
│   ├── difficulty_stratification.py  # 2.2 任务难度分层分析
│   ├── run_large_scale.py            # 大规模实验入口
│   ├── run_statistical_test.py       # 统计检验入口
│   └── statistical_analysis.py       # 统计分析工具
├── reproduce.sh                    # 一键实验复现脚本（quick/full 模式）
├── tests/                            # 单元测试
│   ├── test_code_analyzer.py
│   ├── test_error_classifier.py
│   ├── test_patch_applier.py
│   └── test_dataset_loader.py        # 数据集加载器测试（新增）
├── docs/                             # 文档
│   ├── algorithm_design.md           # 算法设计与理论描述
│   ├── api_reference.md              # API 参考
│   ├── usage_examples.md             # 使用示例
│   ├── performance_guide.md          # 性能调优指南（含性能剖析基准）
│   ├── failure_analysis.md           # 失败案例分析（历史快照）
│   └── history/                      # 归档的历史轮次工作记录
│       ├── optimization_plan.md
│       └── optimization_report.md
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
将测试失败分为十二类：**LLM 响应格式异常（llm_format_error）、导入失败（import_error）、语法错误（syntax）、类型不匹配（type_error）、索引越界（index_error）、断言失败（assertion）、测试逻辑错误（logic_error）、运行时异常（runtime）、超时（timeout）、未知（unknown）、补丁被安全守卫拒绝（patch_validation_failed）、RAG 检索全空（rag_retrieval_empty）**，每类采用差异化修复策略（P2 细化：import/type/logic 三类从旧的五类中拆出；1.2 残余：LLM_FORMAT_ERROR 与 INDEX_ERROR 从 UNKNOWN 拆出；1.1 状态细化：PATCH_VALIDATION_FAILED 与 RAG_RETRIEVAL_EMPTY 为流程状态类，由 `refine_failure_category()` 在任务收尾按 repair_history/rag_stats 信号判定——前 10 类走 `classify()` 文本正则，后 2 类不走正则，成功任务原样返回）。

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

### 5.1 多候选补丁与验证（3.1，默认关闭）
单补丁"一步走错步步错"的风险：LLM 偶发输出语法残缺/误删函数/改错行时，坏补丁会污染 target_code 并带着错误诊断进入下一轮迭代，白白消耗修复预算。多候选补丁策略在同一轮内生成 N 个候选（视角扰动提示让各候选走不同修复路径：最小改动/根因修复/防御式修复），静态筛选（`ast.parse` 语法 + 函数完整性 + 10% 长度安全）淘汰坏候选，可选执行验证逐候选跑测试选通过率/覆盖率最高者，仅当选中的候选严格优于原代码才提交。

**技术实现**：
- [src/tools/multi_candidate.py](src/tools/multi_candidate.py) 中的 `generate_candidates()` / `select_best_candidate()` / `static_validate_patch()`
- 经 [src/graph/workflow.py](src/graph/workflow.py) 的 `_patch_applier_node` 接入，`ENABLE_MULTI_CANDIDATE_PATCH` 默认 false 保持历史实验口径，无有效候选自动回退单补丁

### 5.2 结构化可观测性（4.1，默认关闭）
JSONL 追加式记录每个任务各智能体节点的输入输出、决策路径（debug/done/regenerate）、token 消耗与墙钟耗时，供实验分析逐智能体重放（日志是给人看的、会被脱敏采样，无法支撑结构化回放）。`AITESTER_TRACE_DIR` 未设时全 no-op 零性能税，已设时按 `<task_uuid>.trace.jsonl` 落盘并过脱敏。

**技术实现**：
- [src/observability/trace.py](src/observability/trace.py) 中的 `TraceSession` 类
- workflow 各节点（planner/generator/executor/debugger/patch_applier/_should_debug）逐节点记录，benchmark 入口与 CLI 在 finally 收尾 task_end

### 5.3 成本感知路由（3.4 + 3.2 阈值可配）
`APIManager` 的 `COST_AWARE` 策略按"成功率 50% + 1/成本 50%"综合评分排序，故障转移时避免把全量流量切到昂贵 provider；转移到 `cost_weight >= 阈值`（`APIManagerConfig.cost_alert_threshold`，默认 2.0，3.2 可配——阈值过低导致误报多时上调如 3.0/5.0，成本敏感度高时下调，无需改代码）的昂贵节点时记 WARNING 成本告警（`cost_alert_enabled` 可关，告警文案打印配置阈值避免误导调参）。`LLMConfig.cost_weight` 经 `LLM_N_COST_WEIGHT` 读取（0.1~1000，未配置默认 0.0=无信息、APIManager 回退 1.0 基准；`APIManagerConfig.node_cost_weights` 支持显式映射覆盖）。

**技术实现**：
- [src/api/api_manager.py](src/api/api_manager.py) 中的 `RotationStrategy.COST_AWARE` / `_select_node_cost_aware()` / 成本告警分支

### 5.4 RAG 纳入主实验（2.3）
`reproduce.sh` 对合成/内置数据集默认显式 `--enable-rag`（`rag_data/` 持久化跨实验复用），`--no-rag` 可回退 config 默认；`run_benchmark.py` 新增 `--no-rag` 参数与 `--enable-rag` 共同覆盖 `config.ENABLE_RAG`。

### 5.5 结果分析脚本（4.3 + 1.1/1.2 首批指标增强）
`experiments/analyze_results.py` 从 benchmark JSON 提取成功率 / 覆盖率 / 迭代次数分布 / Token 效率 / 按基线失败原因分布（1.2 细化类别可单独计数）/ RAG 检索质量 / 修复收敛效率（首次尝试成功率、成功与失败任务的迭代及耗时统计）/ 多维质量代理（覆盖率与耗时代理、可选 `generated_test` 的断言行数代理、失败类别 Top N），终端打印 Markdown 汇总并写 `analysis_summary.md`；旧 JSON 无 `token_metrics`/`rag_metrics`/`generated_test` 键时自动兜底或降级，不崩。

```bash
# 分析最新一次 benchmark 结果
python experiments/analyze_results.py --results-dir experiments/results

# 分析指定文件
python experiments/analyze_results.py --input experiments/results/benchmark_xxx.json
```

### 5.6 熔断冷却期 + 半开探测（4.1 + 4.2）
`APIManager` 的熔断器在节点连续失败达 `max_consecutive_failures` 后进入冷却期（`APIManagerConfig.circuit_cooldown_seconds`，默认 60s）。冷却期内即使健康检查线程把 `is_healthy` 翻回 True，路由层（`get_healthy_nodes()` 与 `_build_node_list` 备用候选）仍跳过该节点，避免流量重新打回死 provider（浪费时间与 token）；`mark_success` 复位熔断器，`get_status()` 暴露 `circuit_open_remaining_s` 与 `circuit_state`（closed / open / half_open）字段供监控。

4.2 半开探测（默认开，`APIManagerConfig.enable_half_open_probe=True`）：冷却到期后节点不直接恢复全量路由，而是进入"半开"窗口——该节点被纳入路由候选（`in_circuit_half_open`），承载一次探测请求；探测成功闭合熔断器恢复全量路由，失败则重新打开半程冷却期（`min(cooldown/2, half_open_probe_penalty_cap_seconds)`，默认 cap 30s），防止死 provider 被反复打流量。`call()` 与 `check_health()` 的成功 / 各异常分支统一消费探测结果；置 `enable_half_open_probe=False` 退回 4.1 直接放行行为，便于对比实验。

### 5.7 SWE-bench 源码导出自动化（2.1）
官方 SWE-bench JSONL 无 `instance_code` 字段（任务只有 patch 文本）。新增 `scripts/export_swe_bench_source.py` 自动补全：读取已下载的 JSONL，按 patch 的 `+++ b/<path>` 提取首个非测试目标文件，经 `git show <base_commit>:<path>` 只读导出（不污染工作树），输出 `SWE_BENCH_ENRICHMENT` 格式的 enrichment JSONL；支持 `--instance-ids`（逗号或 @文件，配合 check-dataset 输出的缺失列表批量补）、`--dry-run`、`--limit`。`SWEBenchDataset` 新增 `tasks_missing_source()`（识别 instance_code 兜底为 issue 文本的任务）；`check-dataset` 质量报告输出缺失源码的 instance_id 列表与补全指引。

```bash
# 补全全部缺失源码（需 SWE-bench 仓库缓存 + git）
python scripts/export_swe_bench_source.py --dry-run          # 先看导出计划
python scripts/export_swe_bench_source.py --instance-ids @missing_ids.txt
# 加载 enrichment（自动合并到任务的 instance_code）
python main.py check-dataset swe_bench
```

### 5.8 跨文件修复（3.5，默认关闭）
真实数据集（SWE-bench / Defects4J）中约 40% 的任务需要多文件修改。协调器-提议者架构：`cross_file_analyzer` 节点（`CROSS_FILE_ENABLE=true` 时启用）在 `executor → debugger` 之间插入，做 AST 跨文件 import 依赖分析，把依赖边写入 `state["cross_file_deps"]`；`_patch_applier_node` 在跨文件分支按拓扑序对多个模块应用补丁（被调用方先改，调用方后改），任一文件应用失败整体回滚（与单文件 `safe_apply_patch` 同口径）。单文件项目自动降级（依赖边为空时 `cross_file_plan=None`，走单文件路径）。

**0.7 二期增强**（`src/tools/cross_file.py`，默认行为不变，以下为新增能力）：
- **多入口依赖分析** `analyze_multi_entry_deps(entry_modules, source_files, max_depth=1)`：对多个入口模块做一级 import 展开（保守口径，不递归——防依赖图爆炸），去重合并各入口的依赖边（同 `(source, target, symbol)` 保留 `call_line` 最小者）。一期单入口 `analyze_cross_file_deps` 保持原签名不变（多入口是叠加能力）。
- **拓扑序补丁应用** `apply_multi_file_patch(..., deps=...)`：传入依赖边时按依赖图拓扑序应用（被调用方先改、调用方后改，Kahn 算法 + 环按字典序打破）；不传 `deps`（None）时退回模块名字典序（一期口径），保持历史实验可比性。
- **修复计划缓存** `build_cross_file_repair_plan_cached(...)`：相同依赖图指纹（入口 + 依赖边 + max_modules 的 SHA1）落盘 LLM 缓存目录（复用 `AITESTER_LLM_CACHE` / `AITESTER_LLM_CACHE_DIR` 口径），命中时零 LLM 调用；`use_cache=False` 或缓存开关关闭时退化为不缓存。

```bash
# 启用跨文件修复（显式设置环境变量）
CROSS_FILE_ENABLE=true CROSS_FILE_MAX_MODULES=5 python main.py run examples/calculator.py
# 默认关闭（历史单文件口径不变）
```

设计文档：[docs/design/cross_file_repair.md](docs/design/cross_file_repair.md)

### 5.9 断言增强策略（3.4，默认关闭）
`GeneratorAgent` 在生成前先 AST 提取被测代码中已有 `assert` 语句（去重，最多 10 条），作为"锚点断言"注入 prompt，引导 LLM 避免断言弱化 / 恒真断言 / 魔数未命名等异味。默认 `false` 保持历史生成口径；启用需显式 `ASSERTION_AUGMENT_ENABLE=true`。

### 5.10 依赖缓存监控（4.4）
`venv` 缓存从"有复用无监控"升级为"命中率可观测 + 可清理"：
- `get_venv_cache_stats()`：进程内累计 hit/create 事件 + 落盘 JSON 跨进程聚合，返回 `hit_rate = hits/(hits+creates)`
- `list_venv_cache()`：列出缓存目录所有 venv（name/path/size_mb/created_at）
- `clear_venv_cache(max_age_days, max_size_mb)`：按年龄/大小过滤清理，均 None 时清空

### 5.11 测试异味检测 / 修复收敛曲线 / 收敛失败模式归因 / 边界用例覆盖 / 变异得分 / 断言强度 AST 增强（1.2/1.3）
`experiments/analyze_results.py` 新增六个保守可复算章节（全部"字段缺失即跳过"，旧 JSON 不崩）：
- **测试异味检测（1.2）**：AST 扫 `details[].generated_test`，识别 Assertion Roulette / Magic Number / 断言弱化 / 平凡测试 4 类异味
- **修复收敛曲线（1.3）**：按迭代轮次 0/1/2/3+ 统计累计通过率与平均耗时，观察"随迭代增加通过率如何变化"
- **收敛失败模式归因（1.2）**：对达到 MAX_ITERATIONS 仍未修复的任务，区分"无法定位根因"（诊断反复同义且从未写盘成功）与"无法生成有效补丁"（补丁写盘成功但测试仍失败 / 被安全守卫反复拒绝）
- **边界用例覆盖（1.3）**：AST 保守判定 `generated_test` 是否覆盖 None / 空字符串 / 空集合 / 0 / -1 / >= / <= 等边界条件，输出各边界类型命中数与覆盖率
- **变异得分（1.3）**：收集 `details[].mutation_score`（外部变异测试器如 mutmut 产出），汇总平均 / 高（>=0.7）/ 低（<0.4）分布；无该字段时跳过章节
- **断言强度 AST 增强（1.3）**：在原有 `assert` 行数统计基础上新增 AST 口径（`ast.parse` + `ast.Assert` 节点计数），输出 `ast_avg_assertions` 与 `ast_parse_failed_tasks`（解析失败任务清单，可交叉异味检测）

旧 JSON 无 `generated_test` / `mutation_score` 字段时自动降级，不崩溃。

### 5.12 失败根因分类与案例知识库（5.3）
`experiments/analyze_failures.py` 新增：
- **失败根因分类**：三大根因（`llm_capability` / `dependency` / `framework`）按 `error_category` + `diagnosis` 关键词保守启发式归类
- **案例知识库**：按 `error_category` 多样性优先选取典型失败案例，结构化为 `experiments/results/failure_knowledge_base.json`（含 task_id / root_cause / reproducible_steps / suggested_fix）

CLI 新增 `--knowledge-base/-k` 选项控制输出路径。

### 5.13 执行反馈轨迹收集（3.2）
`state.py` 新增 `execution_trace` 字段（list，默认 `[]`，`create_initial_state` 同步初始化），`nodes.py` 的 `_executor_node` 每次执行追加一条记录到 `state["execution_trace"]`：

```
{
  "iteration": int,
  "passed": bool,
  "coverage": float,
  "coverage_delta": float | None,   # 首轮为 None
  "elapsed_seconds": float,
  "reward_signals": {               # 保守线性归一，仅记录观测，不参与路由
    "correctness": 0.0 | 1.0,
    "efficiency": 0.0~1.0,          # 1 - elapsed / EXECUTION_TIMEOUT
    "simplicity": 0.0~1.0           # 1 - elapsed / (EXECUTION_TIMEOUT * 2)
  }
}
```

纯观测层默认常开（不影响修复路由），`run_benchmark.py` 结果行带 `execution_trace`（失败分支 `None` 兜底保持键集合同构）；`analyze_results.py` 新增"执行反馈轨迹汇总（3.2）"章节：统计观测任务数 / 总执行次数 / 平均轮数 / 首轮即通过率 / 末轮 correctness & efficiency 均值 / 首末轮覆盖率趋势（delta）。旧 JSON 无该字段时章节跳过。

> 用途：为未来执行反馈驱动的微调（如 BoostAPR 类方法）备料——每次 benchmark 自动把"通过/失败、覆盖率变化、耗时、多维奖励信号"落进结果 JSON，无需额外执行轨迹采集脚本。

### 5.14 内置变异测试生成器（1.2）
`experiments/mutation_testing.py` 提供 AST 级轻量变异生成器，无需 mutmut 依赖即可产出 mutation_score：

- **三类变异体**：运算符翻转（`_OPERATOR_FLIP_MAP`，比较运算符 `Eq`→`NotEq`、`Lt`→`LtE` 等 AST 类名映射）/ 布尔取反（`_RemoveNotTransformer` 改写 `If/While/Return/Assign/BoolOp/Compare/Expr` 槽位的 `not X → X`，仅当真正替换成功才计入变异体，避免死代码）/ 数字常量偏移（比较中常量 `value → value+1`）
- **保守口径**：每任务 ≤ 20 个变异体（`_MAX_MUTANTS_PER_TASK`），仅处理纯 Python 函数体；语法错误返回空列表不阻断
- **`mutation_score_from_details`**：收集 `details[].mutation_score`（0.0-1.0），汇总平均 / 高（>=0.7）/ 低（<0.4）分布；无该字段时 `available=False` 跳过
- **可选 mutmut 兜底**：系统已安装 mutmut 时优先使用其完整结果，否则回退内置生成器
- **`run_benchmark` 流水线接线**（`ENABLE_MUTATION_SCORING`，默认关闭）：开关启用时
  `experiments/run_benchmark.py` 在基线结果构建后逐任务调用
  `compute_mutation_score`，把 `mutation_score` 写回 `details[]`，
  `analyze_results._mutation_score_metrics` 即可汇总；`generated_test`
  字段经 `_build_task_result` 写进标准结果 JSON（此前仅经 `--save-state`
  落盘 raw/）。CLI `--enable-mutation` / `--no-mutation` 显式覆盖配置默认。

```python
from experiments.mutation_testing import MutationGenerator, mutation_score_from_details

gen = MutationGenerator()
mutants = gen.generate(target_code)  # 每个 Mutant 可单独跑测试套件
# 统计被杀死比例 → details[].mutation_score
score = mutation_score_from_details(details)  # → {"available": True, "avg_mutation_score": 0.65, ...}
```

```bash
# 启用变异得分的 benchmark（每任务 ≤ MUTATION_MAX_MUTANTS 变异体，耗时显著增加）
ENABLE_MUTATION_SCORING=true MUTATION_MAX_MUTANTS=10 \
    python experiments/run_benchmark.py --dataset examples --baselines aitester
# 或显式 CLI 开关
python experiments/run_benchmark.py --dataset examples --baselines aitester --enable-mutation
```

### 5.15 跨批次失败模式对比（5.3）
`experiments/compare_failures.py` 新增 `cross_batch_comparison` / `render_cross_batch_section`：追踪多个 benchmark JSON 批次间失败模式变化，输出 `new_categories`（新出现）/ `resolved_categories`（已消失）/ `regressed_categories`（数量增长）三类趋势，渲染为"跨实验批次失败模式对比（5.3）"章节。

```bash
# 对比 3 个批次（按时间顺序，旧批次在前）
python experiments/compare_failures.py \
    --results experiments/results/benchmark_synthetic_20260918.json \
    --cross-batch \
        experiments/results/benchmark_synthetic_20260901.json \
        experiments/results/benchmark_synthetic_20260907.json \
    --cross-batch-baseline aitester
```

### 5.16 对抗性推理 + 双向依赖图 + 多维污染检测（3.1 / 2.2 / 2.1，默认关闭）
本轮新增的三项能力，均以环境变量开关默认关闭保持历史实验口径，启用为显式行为：

- **对抗性推理（3.1，`ADVERSARIAL_DEBUGGING_ENABLE`）**：Debugger 在生成补丁前注入 2-3 个"击穿当前实现"的对抗性意图假设（AdverIntent-Agent 式），生成针对性测试；生成后独立"批评者"LLM 调用尝试构造击穿用例；被击穿则把负面反馈注入 prompt 重新生成一次补丁（仍失败保留当前并记录风险）。纯观测层，启用会增加 2-4 次 LLM 调用/修复轮。

```bash
# 启用对抗性推理（显式设置环境变量）
ADVERSARIAL_DEBUGGING_ENABLE=true python main.py run examples/calculator.py
```

- **双向依赖图（2.2，`CROSS_FILE_BIDIRECTIONAL`）**：在 3.5 跨文件修复（§5.8）基础上额外收集"其他模块→entry"反向依赖边（被调用方视角），使修复计划能同步更新调用方模块。需配合 `CROSS_FILE_ENABLE=true` 生效，独立开关保证"跨文件启用 ≠ 双向启用"两级保守。

```bash
# 启用跨文件 + 双向依赖图（两级开关）
CROSS_FILE_ENABLE=true CROSS_FILE_BIDIRECTIONAL=true python main.py run examples/calculator.py
```

- **多维污染检测（2.1）**：在 token Jaccard 之外新增结构级（AST 语句骨架 LCS 比率）与语义级（token 词袋余弦，`_embed_code` 钩子可接 CodeBERT）两个维度，`patch_semantic_similarity` 输出三维相似度；`detect_contamination` 每任务输出 `risk_level`（取最严重维度）+ `contamination_summary`（污染 vs 无污染的各自成功率与 delta）；`render_resistant_benchmark_section` 注册 SWE-rebench 抗污染基准（交叉验证建议）。

```bash
# 多维污染检测（experiments/contamination_check.py）
python experiments/contamination_check.py \
    --gold-patches experiments/results/benchmark_xxx.json \
    --output experiments/results/contamination_report.json
```

### 5.17 熔断器指数退避 + Prometheus 导出（4.4，默认开）
`APIHealth` 的熔断器冷却期改按 `base * 2^open_count` 指数退避（封顶 `half_open_probe_penalty_cap_seconds`）：彻底死掉的 provider 冷却期单调增长（第 1 次 60s → 第 2 次 120s → 第 3 次 240s → …），避免反复短冷却打同一死点；`mark_success` 重置 `circuit_open_count`。`APIManager` 新增 `to_prometheus_text()` 导出 7 类 Prometheus 指标（health / circuit_state / open_remaining_s / open_count / probe_success_rate / success_rate / avg_response_ms）供监控抓取，纯旁路不影响既有路由行为。

```bash
# 启用 Prometheus 导出（显式设置环境变量）
API_PROMETHEUS_EXPORT=true python main.py run examples/calculator.py
# 回退 4.2 固定冷却期口径（便于对比实验）
API_CIRCUIT_BACKOFF=false python main.py run examples/calculator.py
```

### 5.18 多维评估指标深化 + 变异反馈闭环（1.1 / 1.2）
- **多维评估指标**（1.1，`experiments/analyze_results.py`）：测试异味检测扩展 Eager Test + Lack of Cohesion 两类 AST 口径，异味统计按策略分组，新增 `smell_density`（有异味任务占比）；新增收敛 token 效率（逐轮 token/边际收益）、难度分层迭代分布、变异-断言强度交叉一致性校验、RAG vs 无 RAG token/迭代对比 + 相似度直方图、三类失败根因占比与时间趋势、高/低污染风险成功率 delta。
- **变异反馈闭环**（1.2，`experiments/mutation_testing.py` + `src/agents/generator.py`）：新增 `boundary_shift`（Gt↔GtE 边界语义变异）与 `return_void`（return X → return None）两类变异体；`build_mutation_feedback()` 把"存活变异体"打包成可注入 Generator prompt 的反馈字典（MutGen 式"变异引导测试增强"闭环）；`run_benchmark` 的 `--enable-mutation` 开关启用时把反馈写回结果行。

```bash
# 启用变异反馈闭环的 benchmark
ENABLE_MUTATION_SCORING=true MUTATION_MAX_MUTANTS=10 \
    python experiments/run_benchmark.py --dataset examples --baselines aitester --enable-mutation
```

### 5.19 错误分类体系扩展（5.2，14 类）
`ErrorCategory` 由 12 类扩至 14 类，新增 `EXECUTION_TRACE_MISSING`（任务失败但 `execution_trace` 为空 = 执行器异常路径）与 `MULTI_CANDIDATE_ALL_REJECTED`（多候选全被静态筛选拒绝）；`refine_failure_category` 新增 `execution_trace` / `multi_candidate_stats` 参数，判定优先级 `patch_rejected > rag_empty > trace_missing > multi_rejected`；`refine_final_error_category` 接线新字段；`get_fix_strategy` 补两类修复策略描述。

```python
from src.agents.error_classifier import refine_final_error_category

category = refine_final_error_category(final_state)  # → 14 类之一
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
# 运行所有测试（全量 1667 个用例；缺可选依赖时自动 skip 降级）
.venv/bin/python -m pytest tests/ -v

# 运行测试并生成覆盖率报告
.venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing

# 运行指定模块测试
.venv/bin/python -m pytest tests/test_dataset_loader.py -v
```

**测试覆盖模块**（68 个测试文件，全量 1667 个 pytest 收集用例；精简环境约 1607 收集，src 总覆盖率 94%）：

| 测试文件 | 测试函数数 | 覆盖范围 |
|---------|-------|---------|
| `test_api_manager.py` | 77 | API 管理器（轮询/加权随机/健康感知策略、健康线程开关、失败阈值配置接线、4.1 熔断冷却期状态机与路由过滤、1.5 冷却期边界 3 用例、4.1 脱敏接线 2 用例） |
| `test_api_circuit_breaker.py` | 16 | 4.4/0.6 熔断器指数退避（`API_CIRCUIT_BACKOFF` 开/关双路径）+ Prometheus 导出（`API_PROMETHEUS_EXPORT` 默认空串） |
| `test_api_manager_extended.py` | 74 | API 管理器扩展路径（健康恢复、限流标记、4.2 半开探测 TestHalfOpenProbe 12 用例） |
| `test_base_agent.py` | 39 | JSON 提取、代码块提取、客户端复用、AST 智能截取 |
| `test_base_agent_extended.py` | 46 | 指数退避重试、LLM 缓存、zai 客户端复用 |
| `test_cli_app.py` | 40 | CLI 命令（list-examples/--version/参数校验/parallel/json 边界 + 1.4 超时贯通/并发容错/check-dataset 边界/glob 并发 + 4.4 clean-venv-cache 4 用例 + 5.1 并发中断/信号处理 3 用例） |
| `test_cli_output.py` | 10 | CLI 输出层回归（colorize TTY 双分支、success/error/warning/info 图标与 stdout/stderr 路由、print_rich_table 空列表/缺键兜底/coverage=0.0 不被误判 N/A，O-01 批次） |
| `test_cli_parallel.py` | 10 | 并发派发器 `_dispatch_parallel_tasks` 与 `run` 并发分支回归（rich/无 rich 双路径、逐任务容错、CI 门控 exit 1）（0.1） |
| `test_cli_run.py` | 6 | run 命令编排（超时/覆盖率阈值透传） |
| `test_cli_console_output.py` | 8 | run 非 JSON 控制台摘要（成功/失败/诊断/建议）+ _dispatch_concurrent rich/降级/JSON 静默分支（0.1） |
| `test_code_analyzer.py` | 17 | AST 解析、圈复杂度、代码替换 |
| `test_code_context.py` | 18 | 11 | AST 智能截取（P0 大文件上下文） |
| `test_complex_logic.py` | 12 | 复杂业务逻辑（邮箱验证等） |
| `test_config_generator.py` | 26 | LLM 配置生成器模板 |
| `test_config_manager.py` | 35 | 32 | 配置管理器（LLM 配置增删） |
| `test_config.py` | 15 | 14 | config.py 默认值与容错解析 |
| `test_core_modules.py` | 29 | 核心模块冒烟（BenchmarkTask / InMemoryDataset / Planner / Executor / DatasetLoader 多类） |
| `test_cost_aware_routing.py` | 13 | 成本感知路由与昂贵 provider 成本告警（3.4 + 3.2 阈值可配 4 用例） |
| `test_dataset_loader.py` | 83 | 数据集加载器（InMemory/SWEBench） |
| `test_dataset_loader_extended.py` | 73 | 数据集加载扩展路径（raw 加载/字段校验） |
| `test_dataset_validation.py` | 22 | SWE-bench 加载质量校验与源码补充（P0）+ tasks_missing_source（2.1） |
| `test_debugger.py` | 29 | 错误诊断、RAG 注入、分类透传 |
| `test_contamination_check.py` | 15 | 2.1 数据污染检测（token 提取/Jaccard 重叠度/分级/detect 扫描/渲染章节） |
| `test_contamination_multidim.py` | 25 | 2.1 多维污染检测（结构级 AST 骨架 LCS + 语义级词袋余弦三维相似度 / 综合风险等级 / detect 全流程 / 抗污染基准注册表） |
| `test_dependency.py` | 43 | 依赖检测与 venv 管理（P1）+ 4.4 缓存监控（命中率统计/列表/清理，8 用例） |
| `test_dependency_edge_cases.py` | 14 | 依赖检测边界分支（标准库回退/find_spec 异常/venv 创建超时/OSError 静默降级，0.1 新增） |
| `test_error_classifier.py` | 89 | 85 | 十二类错误分类与修复策略映射（P2 细化 + 1.2 残余 + 1.1 状态细化：refine_failure_category） |
| `test_error_classifier_new_categories.py` | 16 | 5.2 新增两错误类别判定（`EXECUTION_TRACE_MISSING` / `MULTI_CANDIDATE_ALL_REJECTED`，判定优先级 / 修复策略描述 / 从 final_state 接线） |
| `test_exceptions.py` | 33 | 自定义异常类与装饰器 |
| `test_executor.py` | 50 | 48 | 覆盖率解析、失败用例解析 |
| `test_executor_docker.py` | 11 | 4.3 Docker 执行模式（不可用诊断/模式开关/docker 优先于 venv/子进程环境凭证剔除 + TestDockerExecutionFlow 容器内执行链路 6 用例 + 沙箱清理兜底） |
| `test_executor_sandbox.py` | 14 | 沙箱执行路径与依赖安装（P1，含 install 失败短路 / 目标文件缺失边界） |
| `test_experiments_analysis.py` | 20 | 实验结果分析（排名/统计）+ 5.1 统计检验边界 5 用例（样本量 <3 / 部分配对缺失 / 单基线 / 脏数据） |
| `test_experiments_scripts.py` | 54 | visualize 结果选择 / 标准化实验返回键 / benchmark 并行度回归（0.1）+ 4.3 analyze_results 纯函数 + 2.3 RAG 自动汇总 + 1.1/1.2 修复收敛与质量代理指标 + 1.2 测试异味检测 + 1.3 修复收敛曲线 + 4.4 依赖缓存命中统计 + 1.2 收敛失败模式归因 / 1.3 边界用例覆盖 / 1.3 变异得分 / 3.2 执行轨迹汇总（14 用例） |
| `test_generator.py` | 43 | parametrize 校验、import 修正、LLM 调用 + 3.4 断言增强（TestAssertionAugmentation：AST 提取现有 assert，默认关，9 用例） |
| `test_llm_file_cache.py` | 7 | LLM 文件缓存命中/失效 + 温度键不互命中 + system_prompt 参与缓存键（0.9 深度审查回归） |
| `test_logging_utils.py` | 19 | 日志脱敏正则（sk- 前缀/带点号分段/无前缀长 hex·base64 三类形态，0.1 脱敏扩展回归）+ 5.1 脱敏边界 5 用例（格式化失败/exc_info 堆栈脱敏/嵌套 dict 口径锁定/幂等/mask 异常回退） |
| `test_mysql_client.py` | 15 | MySQL 客户端单例/事务/连接池参数 |
| `test_multi_candidate.py` | 23 | 多候选补丁生成与静态/执行验证筛选（3.1） |
| `test_packaging.py` | 3 | 打包完整性（子包 __init__ 齐全） |
| `test_patch_applier.py` | 39 | 补丁应用（完整文件/单函数模式）+ 多函数补丁排序顺序（0.9 回归） |
| `test_planner.py` | 5 | PlannerAgent 规划逻辑序列化 |
| `test_prompts_templates.py` | 14 | 三个 system prompt 常量结构契约（关键指令段/错误类别/JSON 输出格式，0.1） |
| `test_rag_metrics.py` | 13 | RAG 检索质量指标 Hit Rate/MRR（P1） |
| `test_rag_retriever.py` | 42 | RAG 检索器增删查清与持久化 |
| `test_report_generator.py` | 48 | 错误报告生成器（含十二类分类分支） |
| `test_run_benchmark.py` | 5 | benchmark 结果构造与异常路径回归（0.1 去重重构 + 2.1 patch 字段键集合同构护栏） |
| `test_swe_bench_source_export.py` | 13 | SWE-bench 源码导出脚本（patch 目标文件提取 / enrichment 落盘 / dry-run，2.1） |
| `test_state.py` | 8 | AITesterState 单一构造点工厂（create_initial_state 键集守护 / module_name 推导 / 可变容器隔离，深度重构批次） |
| `test_viz_significance.py` | 6 | 统计显著性收敛（visualize_results 复用 statistical_analysis 配对原语 / NaN 占位 / 原语引用锁定，深度重构批次） |
| `test_string_utils.py` | 10 | 字符串工具 |
| `test_synthetic_dataset.py` | 5 | 合成数据集生成与确定性验证 |
| `test_token_usage.py` | 9 | token 消耗统计（P0 效率指标） |
| `test_trace_observability.py` | 12 | 结构化 JSONL 追踪层（4.1） |
| `test_venv_cache_monitoring.py` | 11 | 4.4 venv 缓存容量监控（`get_venv_cache_size_mb` / `check_venv_cache_size` 5GB 阈值告警 / 统计文件路径动态化 / 命中率 / 清理） |
| `test_workflow.py` | 41 | 工作流图构建与路由 + 3.5 跨文件修复（CROSS_FILE_ENABLE 启用/禁用路径，2 用例）+ 3.2 执行反馈轨迹（TestExecutionTrace 3 用例：首轮 / 二轮 delta / 缺键容错） |
| `test_workflow_extended.py` | 47 | 38 | 工作流扩展路径（RAG 初始化单例、planner 默认计划去重等） |
| `test_cross_file.py` | 39 | 3.5 跨文件修复（AST 依赖分析 / 协调器-提议者 / 多文件补丁应用 / 降级单文件 / 序列化 / 二期多入口依赖 / 拓扑序应用 / 修复计划缓存） |
| `test_cross_file_bidirectional.py` | 16 | 2.2 跨文件双向依赖图（单向/双向口径 / `CROSS_FILE_BIDIRECTIONAL` 环境变量开关 / 符号定义行定位） |
| `test_analyze_failures.py` | 13 | 5.3 失败根因分类（LLM/依赖/框架三大根因）+ 案例知识库 + CLI --knowledge-base |
| `test_weak_coverage_modules.py` | 16 | 5.1 弱覆盖模块补强（cli_output print_rich_table 边界 / error_classifier 新分类路径 / executor_runtime 清理与重试异常分支） |
| `test_weak_coverage_modules2.py` | 10 | 5.1 弱覆盖模块补强第二轮（config_generator main 入口 / prompts_templates 常量结构 / synthetic_dataset 边界生成） |
| `test_weak_coverage_modules3.py` | 13 | 5.1 弱覆盖模块补强第三轮（trace 写盘失败降级 / analysis 统计检验边界 / error_classifier 分支 / cli_output 非 rich 降级 / prompts __main__） |
| `test_smell_detection_v2.py` | 6 | 1.1 异味检测补强（Eager Test / Lack of Cohesion 触发与不触发 + 语法错误兜底） |
| `test_failure_kb.py` | 181 | 5.3 失败案例知识库 + 跨批次失败模式对比（failure_knowledge_base 结构化 JSON / cross_batch_comparison 批次趋势 / 三大失败根因） |
| `test_defects4j_smoke.py` | 155 | 3.4 Defects4J-Python 加载器冒烟验证（无数据目录优雅降级 / 完整目录解析 / 字段完整性） |

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
| `CROSS_FILE_ENABLE` | 3.5 跨文件修复开关（协调器-提议者架构，默认关） | false |
| `CROSS_FILE_MAX_MODULES` | 3.5 跨文件依赖分析最大模块数 | 5 |
| `CROSS_FILE_BIDIRECTIONAL` | 2.2 跨文件双向依赖图开关（默认 false 保持单入口视角；启用时额外收集"其他模块→entry"反向依赖边，使修复计划能同步更新调用方模块；需配合 CROSS_FILE_ENABLE=true 生效） | false |
| `ADVERSARIAL_DEBUGGING_ENABLE` | 3.1 对抗性推理开关（默认关；启用后 Debugger 生成补丁前注入 2-3 个"击穿当前实现"的对抗性意图假设 + 生成针对性测试，生成后独立批评者评估，被击穿则重生成一次补丁；观测层，不影响主修复路径） | false |
| `ASSERTION_AUGMENT_ENABLE` | 3.4 断言增强策略（AST 提取现有 assert 注入 prompt，默认关） | false |

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
| `AITESTER_VENV_CACHE_DIR` | 4.4 venv 缓存目录覆盖（默认 `~/.cache/aitester/venvs`；配合 `clean-venv-cache` 清理） | 未设 |
| `MYSQL_POOL_MIN_CACHED` | 连接池最小预留连接 | 5 |
| `MYSQL_POOL_MAX_CACHED` | 连接池最大空闲连接 | 10 |
| `MYSQL_POOL_MAX_CONNECTIONS` | 连接池最大连接总数 | 20 |
| `MYSQL_POOL_TIMEOUT` | 获取连接等待超时（秒） | 30 |
| `LLM_N_COST_WEIGHT` | 第 N 个 LLM 的相对成本倍数（3.4 成本感知路由；0.0=未配置，APIManager 回退 1.0 基准） | 1.0 |
| `SWE_BENCH_ENRICHMENT` | SWE-bench 源码补充 JSONL 路径（P0，可选） | 无 |
| `BENCHMARK_PARALLELISM` | 批量测试并行度（0=串行） | 0 |
| `TEMPERATURE` | LLM 采样温度 | 0.2 |

## 高级开关（默认全关，按需启用）

以下开关均以环境变量形式提供，默认值保持历史实验口径不变；启用是显式行为。

| 开关 | 默认 | 启用效果 | 关联章节 |
|------|------|---------|----------|
| `ENABLE_MULTI_CANDIDATE_PATCH` | false | 多候选补丁生成与验证筛选（3.1；`reproduce.sh` 复现流程默认显式启用，`--no-multi-candidate` 可回退历史口径） | 5.1 |
| `AITESTER_TRACE_DIR` | 未设（no-op） | 结构化 JSONL 追踪层（4.1；`reproduce.sh` 默认启用至 `experiments/results/traces`） | 5.2 |
| `ENABLE_MUTATION_SCORING` | false | 1.2 变异得分评估：benchmark 运行后对每任务"生成测试 vs 被测源码"计算 mutation_score（内置轻量变异生成器，每任务 ≤ `MUTATION_MAX_MUTANTS` 个变异体）；耗时显著增加，默认关闭保持历史口径 | 5.14 |
| `MUTATION_MAX_MUTANTS` | 10 | 1.2 每任务最多评估的变异体数量（需配合 `ENABLE_MUTATION_SCORING=true` 生效） | 5.14 |
| `EXECUTOR_USE_DOCKER` | false | 4.3 Docker 隔离执行（经 docker CLI 在容器内跑 pytest，镜像内置依赖；不可用时返回 `docker_unavailable` 诊断不降级本地） | 5.13 |
| `EXECUTOR_DOCKER_IMAGE` | aitester:latest | 4.3 Docker 执行使用的镜像名（对应仓库根 Dockerfile） | 5.13 |
| `CROSS_FILE_ENABLE` | false | 跨文件修复（协调器-提议者架构，3.5；`reproduce.sh --cross-file` 显式启用） | 5.8 |
| `CROSS_FILE_BIDIRECTIONAL` | false | 2.2 跨文件双向依赖图（额外收集"其他模块→entry"反向依赖边，修复计划同步更新调用方；需配合 `CROSS_FILE_ENABLE=true` 生效，独立开关保证"跨文件启用 ≠ 双向启用"两级保守） | 5.8 |
| `ADVERSARIAL_DEBUGGING_ENABLE` | false | 3.1 对抗性推理（AdverIntent 式：生成补丁前注入 2-3 个对抗性意图假设 + 生成针对性测试，生成后独立批评者评估，被击穿则重生成一次；纯观测层，默认关保持历史口径） | 5.16 |
| `API_CIRCUIT_BACKOFF` | true | 4.4 API 熔断器指数退避开关（冷却期改按 `base * 2^open_count` 指数增长，彻底死掉的 provider 冷却期单调增长；`reproduce.sh` 显式透传，设 false 回退 4.2 固定冷却期口径便于对比实验） | 5.17 |
| `API_PROMETHEUS_EXPORT` | false | 4.4 Prometheus 指标导出开关（启用后 `APIManager.to_prometheus_text()` 输出 7 类指标供 Prometheus 抓取；纯旁路，不影响既有路由行为；`reproduce.sh` 显式透传） | 5.17 |
| `ASSERTION_AUGMENT_ENABLE` | false | 断言增强策略（AST 提取现有 assert，3.4） | 5.9 |

详见 [QUICKSTART.md](QUICKSTART.md) 与 [.env.example](.env.example)。

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
  --dataset, -d       数据集名称（examples/synthetic/swe_bench/swe_rebench/defects4j_py）
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

> **2.1 数据污染检测**：SWE-bench 场景下，结果 JSON 的 `details[].patch`（系统生成补丁）与
> `details[].task_metadata.golden_patch`（官方黄金补丁）会自动送入污染检测。运行分析时可用
> `python experiments/analyze_results.py --golden-patches <json>` 显式传入黄金补丁映射（JSON
> 对象 `{task_id: patch_text}`）；分析报告自动渲染"数据污染检测（2.1）"章节（high/medium 任务
> 列表 + 重叠度分数 + 抗污染基准建议）。

**示例：**
```bash
# 快速验证（2 个任务，单基线）
python experiments/run_benchmark.py --dataset examples --task-limit 2 --baselines aitester

# 并行执行（4 线程，100 个合成任务）
python experiments/run_benchmark.py --dataset synthetic --task-count 100 \
    --baselines aitester,plain_llm,single_agent --parallel 4

# 仅运行 aitester 完整系统（JSON 为默认输出，无需 --json 开关）
python experiments/run_benchmark.py --dataset examples --baselines aitester

# 2.1 抗污染基准（SWE-rebench，需经 AITESTER_SWE_REBENCH_DATA 指向数据目录）
python experiments/run_benchmark.py --dataset swe_rebench --baselines aitester

# 4.3 Docker 隔离执行（需本机 docker + 镜像已构建；容器内零安装开销）
EXECUTOR_USE_DOCKER=true python experiments/run_benchmark.py --dataset examples --baselines aitester
```

### `python main.py list-examples` — 列出示例文件

```
python main.py list-examples
```

### `python main.py clean-venv-cache` — 清理依赖缓存（4.4）

```
python main.py clean-venv-cache [OPTIONS]

选项：
  --max-age-days N    删除 N 天前的 venv（None 表示不按年龄过滤）
  --max-size-mb N     删除超过 N MB 的 venv（None 表示不按大小过滤）
  --list-only, -l     仅列出缓存目录内容（含命中率统计），不删除
```

**示例：**
```bash
# 查看现有缓存与命中率
python main.py clean-venv-cache --list-only

# 删除 30 天前的 venv
python main.py clean-venv-cache --max-age-days 30

# 删除超过 512MB 的 venv
python main.py clean-venv-cache --max-size-mb 512
```

> 缓存目录默认 `~/.cache/aitester/venvs/`，可经 `AITESTER_VENV_CACHE_DIR` 环境变量覆盖（容器/CI 隔离场景指向挂载卷）。

## 数据集说明

| 数据集名称 | 数据来源 | 任务数 | 下载要求 |
|-----------|---------|-------|---------|
| `examples` | 内置示例（calculator/buggy_library/string_utils） | 3 | 无需下载 |
| `synthetic` / `synth` | 本地生成，支持自定义规模 | 可配置 | 无需下载 |
| `swe_bench` | HuggingFace SWE-bench | 500 (lite) | 需调用 download_from_huggingface() |
| `defects4j_python` | Defects4J-Python 数据集 | 可变 | 需手动下载 |
| `swe_rebench` | SWE-rebench 抗污染基准（2.1 数据污染风险应对，字段与 SWE-bench 同构） | 可变 | 需经 `load_dataset("swe_rebench", data_dir=...)` 指向 rebench 数据目录 |

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

### 合成数据集实验（50个任务，3种基线对比，最新数据快照）

> 某次 50 任务运行（3 种基线对比）的最新数据快照，用于演示多基线方法论，非当前版本性能承诺。

| 基线方法 | 成功率 (%) | 平均覆盖率 (%) | 平均迭代次数 | 平均耗时 (s) |
|---------|-----------|---------------|-------------|-------------|
| **AITester** | **88.0** | **97.8** | 0.64 | 45.33 |
| Plain LLM | 68.0 | 98.0 | 0.0 | 16.6 |
| Single Agent | 4.0 | 0.0 | 0.24 | 26.85 |

**关键发现**：
- AITester 成功率显著高于 Plain LLM（88.0% vs 68.0%），覆盖率持平（97.8% vs 98.0%）
- AITester 平均耗时 45.33s，Plain LLM 为 16.6s，多智能体修复循环带来约 2.7 倍耗时增加
- Single Agent 基线成功率仅 4.0%（50 任务仅 2 个通过），验证多智能体架构的必要性
- 统计检验：AITester vs Single Agent 差异极显著（p < 0.001，Cohen's d 远大于 0.8）

详细结果参见 [experiments/results/synthetic_50_final/charts/](experiments/results/synthetic_50_final/charts/)（本地保留，不入库；仓库内 `experiments/results/` 仅跟踪占位说明，历史产物经 .gitignore 排除）

### SWE-bench Lite 实验（20个任务）

该批次实验受 API 限流影响，结果未归档到仓库；后续重跑数据以本地私有目录保存（不入库）。

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

## 技术文档

- [算法设计文档](docs/algorithm_design.md)：核心算法形式化描述
- [失败案例分析](docs/failure_analysis.md)：失败率的根因分析与改进路线图（历史数据快照）
- [性能调优指南](docs/performance_guide.md)：并发执行、RAG 单例化、超时配置、性能剖析基准
- [API 参考文档](docs/api_reference.md)：模块接口说明
- [使用示例](docs/usage_examples.md)：编程接口与 CLI 用法
- [高级开关说明](QUICKSTART.md)：结构化追踪 / 多候选补丁 / 成本感知路由（默认全关，按需启用）
- [历史优化记录](docs/history/optimization_plan.md)：归档的历史轮次优化计划与报告（`docs/history/`，非当前维护文档）

---

## 贡献指南

欢迎贡献代码！请阅读 [贡献指南](CONTRIBUTING.md) 了解如何参与项目开发。

---

## 迭代优化记录

### v0.1 (2026-09-18) — 首个正式版本

**核心成果**:
- 四智能体协作架构（Planner / Generator / Executor / Debugger）+ 分层错误修复机制（12 类错误分类）
- 逻辑驱动思维链（Logic-driven CoT）：Planner 显式分析输入域/输出域/前置条件/后置条件/边界
- RAG 检索增强（ChromaDB，默认关闭；`ENABLE_RAG=true` 启用）
- 多基线对比与消融实验（aitester / plain_llm / single_agent）
- 多候选补丁生成与验证筛选（3.1，默认关）
- 结构化可观测性：JSONL 节点级追踪（4.1，默认关；`AITESTER_TRACE_DIR` 启用）
- 成本感知路由 + 熔断冷却期 + 半开探测（3.4 + 4.1 + 4.2）
- SWE-bench 源码导出自动化（2.1）+ 数据污染检测（token 级 Jaccard）
- 跨文件修复（协调器-提议者架构，3.5，默认关）
- 断言增强策略（AST 提取现有 assert，3.4，默认关）
- 依赖缓存监控（venv 命中率可观测 + clean-venv-cache CLI）
- 测试异味检测 / 修复收敛曲线 / 边界用例覆盖 / 变异得分 / 执行反馈轨迹（1.2/1.3/3.2）
- 内置变异测试生成器（`experiments/mutation_testing.py`，AST 级三类变异体）
- Docker 隔离执行（`EXECUTOR_USE_DOCKER`，4.3）
- 全量 1667 个测试用例 / 覆盖率 94% / Ruff 全绿

**基准测试**（合成数据集 50 任务，3 基线对比）：
- AITester：成功率 88.0%，覆盖率 97.8%，平均耗时 45.33s
- Plain LLM：成功率 68.0%，覆盖率 98.0%，平均耗时 16.6s
- Single Agent：成功率 4.0%，覆盖率 0.0%，平均耗时 26.85s

**验证**: 全量 1667 passed / 0 failed / ruff 全绿 / 覆盖率 94%

---

## 许可证

MIT License
