# AITester：逻辑驱动的多智能体测试生成与自修复系统

> AITester 是一个基于多智能体协作的 Python 自动化测试生成与自修复框架。
> 核心创新：**逻辑驱动思维链（Logic-driven CoT）** + **分层错误修复机制（Hierarchical Repair）**。
> 
> 本系统面向学术研究，已在[研究动机文档](research_motivation.md)和[算法形式化描述](algorithm_paper.md)中提供了论文写作所需的全部素材。

## 快速开始

```bash
# 1. 安装依赖（需要 Python 3.10+）
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 等信息

# 3. 初始化数据库（可选，如需持久化实验数据）
python init_db.py

# 4. 运行单个文件测试
python main.py run examples/calculator.py --func divide

# 5. 批量基准测试（对 examples/ 下所有文件运行）
python experiments/run_benchmark.py

# 6. 可视化实验结果
python experiments/visualize_results.py
```

## 项目结构

```
AITester/
├── src/                          # 核心源代码
│   ├── agents/                   # 多智能体模块
│   │   ├── base_agent.py         # 智能体基类（LLM 调用、JSON 解析）
│   │   ├── planner.py            # 测试规划师（含逻辑驱动思维链）
│   │   ├── generator.py          # 测试代码生成器（支持 RAG 增强）
│   │   ├── executor.py           # 测试执行器（带超时和重试）
│   │   ├── debugger.py           # 调试修复师（分层错误修复）
│   │   └── error_classifier.py   # 错误类型分类器（规则匹配）
│   ├── tools/                    # 工具函数模块
│   │   ├── code_analyzer.py      # AST 代码分析（精确替换，避免正则误匹配）
│   │   └── patch_applier.py      # 补丁应用（支持完整文件和单函数模式）
│   ├── graph/                    # 工作流编排模块
│   │   ├── workflow.py           # LangGraph 工作流图（Planner→Generator→Executor→Debugger）
│   │   └── state.py              # 全局状态定义（TypedDict）
│   ├── prompts/                  # Prompt 模板模块
│   │   └── templates.py          # 各智能体的 System Prompt 集中管理
│   ├── db/                       # 数据库模块
│   │   └── mysql_client.py       # MySQL 单例客户端（任务、测试、修复记录）
│   └── rag/                      # 检索增强生成模块
│       └── retriever.py          # ChromaDB 向量检索器（测试用例与修复案例）
├── examples/                     # 示例被测代码（含已知 bug）
│   ├── calculator.py             # 计算器示例（除零、负数阶乘 bug）
│   ├── buggy_library.py          # 算法库示例（二分查找、排序合并等）
│   └── string_utils.py           # 字符串工具示例（回文、Caesar 密码等）
├── experiments/                  # 实验脚本模块
│   ├── run_benchmark.py          # 批量基准测试（输出 JSON 结果）
│   └── visualize_results.py      # 结果可视化（柱状图 + 详细表格）
├── tests/                        # 单元测试
│   ├── test_code_analyzer.py     # code_analyzer 模块测试
│   ├── test_error_classifier.py  # error_classifier 模块测试
│   └── test_patch_applier.py     # patch_applier 模块测试
├── research_motivation.md        # 研究动机、问题定义和研究问题（RQ）
├── algorithm_paper.md            # 算法形式化描述（状态转移、伪代码、复杂度分析）
├── main.py                       # CLI 入口（click 框架）
├── config.py                     # 全局配置（从 .env 读取）
├── init_db.py                    # 数据库初始化脚本
├── setup.py                      # 包管理配置（pip install -e .）
├── requirements.txt              # Python 依赖列表
├── Dockerfile                    # Docker 镜像定义（一键复现实验环境）
└── .env.example                  # 环境变量模板（复制为 .env 后填写真实值）
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
- 在 [src/graph/workflow.py](src/graph/workflow.py) 中通过 `RAG_ENABLED` 标志控制启用/禁用

## 论文写作指导

### 推荐论文结构
```
1. 引言（Introduction）
   - 自动化测试的重要性
   - 现有方法的局限性
   - 本文贡献

2. 相关工作（Related Work）
   - 传统测试生成工具（Pynguin、EvoSuite）
   - LLM 驱动测试生成（TestLoter、CHATTESTER）
   - 多智能体协作系统

3. 方法设计（Methodology）
   - 系统架构（参考 algorithm_paper.md）
   - 逻辑驱动思维链
   - 分层错误修复机制
   - RAG 增强模块

4. 实验设置（Experimental Setup）
   - 数据集（examples/ 下的示例代码）
   - 基线方法（直接 LLM 生成、单智能体方案）
   - 评估指标（成功率、覆盖率、修复轮数）

5. 结果与分析（Results and Analysis）
   - 基准测试结果（参考 experiments/results/）
   - 消融实验（移除 Planner/Debugger/RAG）
   - 案例分析

6. 讨论（Discussion）
   - 方法优势
   - 局限性
   - 未来工作

7. 结论（Conclusion）
```

### 论文素材位置
| 内容 | 文件位置 |
|------|----------|
| 研究背景与动机 | [research_motivation.md](research_motivation.md) |
| 算法形式化描述 | [algorithm_paper.md](algorithm_paper.md) |
| System Prompt 设计 | [src/prompts/templates.py](src/prompts/templates.py) |
| 实验脚本 | [experiments/run_benchmark.py](experiments/run_benchmark.py) |
| 可视化脚本 | [experiments/visualize_results.py](experiments/visualize_results.py) |

## 实验复现

### 环境要求
- Python 3.10+
- MySQL 5.7/8.0（可选，用于持久化实验数据）
- OpenAI API Key 或兼容 API（如 DeepSeek）

### 复现步骤
```bash
# 1. 克隆仓库
git clone <repository-url>
cd AITester

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY

# 4. 初始化数据库（可选）
python init_db.py

# 5. 运行基准测试
python experiments/run_benchmark.py

# 6. 查看结果
ls experiments/results/
python experiments/visualize_results.py
```

### Docker 一键复现
```bash
# 构建镜像
docker build -t aitester:latest .

# 运行测试
docker run --rm \
  -v $(pwd):/workspace \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  aitester:latest \
  python experiments/run_benchmark.py
```

## 单元测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行测试并生成覆盖率报告
pytest tests/ -v --cov=src --cov-report=term-missing
```

## 配置说明

所有配置项统一在 [config.py](config.py) 中管理，通过 `.env` 文件注入：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `OPENAI_API_KEY` | OpenAI API 密钥 | 必填 |
| `MODEL_NAME` | LLM 模型名称 | gpt-4o-mini |
| `MAX_ITERATIONS` | 最大修复迭代次数 | 3 |
| `COVERAGE_THRESHOLD` | 覆盖率阈值 | 80.0 |
| `EXECUTION_TIMEOUT` | 单次执行超时（秒） | 30 |

## 技术栈

- **LLM 框架**: LangChain + LangGraph
- **数据库**: MySQL（pymysql 驱动）
- **向量数据库**: ChromaDB（RAG 模块）
- **测试框架**: pytest + pytest-cov
- **命令行**: Click
- **可视化**: matplotlib + pandas

## 作者与研究信息

- 项目名称: AITester
- 目标期刊: 《软件学报》《计算机学报》
- 提交时间: 2026年8月
