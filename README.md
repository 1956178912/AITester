# AITester：逻辑驱动的多智能体测试生成与自修复系统

> AITester 是一个基于多智能体协作的 Python 自动化测试生成与自修复框架。
> 核心创新：**逻辑驱动思维链（Logic-driven CoT）** + **分层错误修复机制（Hierarchical Repair）**。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 等信息

# 运行单个文件
python main.py run examples/calculator.py --func divide

# 批量基准测试
python experiments/run_benchmark.py
```

## 项目结构

```
AITester/
├── src/
│   ├── agents/
│   │   ├── planner.py          # 逻辑驱动规划器（含思维链）
│   │   ├── generator.py         # 测试代码生成器
│   │   ├── executor.py          # 测试执行器（带重试）
│   │   ├── debugger.py          # 分层修复调试器
│   │   └── error_classifier.py  # 错误类型分类器
│   ├── tools/
│   │   ├── code_analyzer.py     # AST 代码分析（含精确替换）
│   │   └── patch_applier.py     # 补丁应用
│   ├── graph/
│   │   ├── workflow.py          # LangGraph 工作流
│   │   └── state.py             # 状态定义
│   ├── prompts/
│   │   └── templates.py         # System Prompt 模板
│   └── db/
│       └── mysql_client.py      # MySQL 持久化
├── examples/
│   ├── calculator.py            # 计算器示例（含 bug）
│   ├── buggy_library.py         # 算法库示例（二分查找等）
│   └── string_utils.py          # 字符串工具示例
├── experiments/
│   └── run_benchmark.py         # 批量基准测试脚本
├── tests/                       # 单元测试
├── research_motivation.md       # 研究动机与 RQ
├── algorithm_paper.md           # 算法形式化描述（论文素材）
└── main.py                      # CLI 入口
```

## 核心方法

### 1. 逻辑驱动思维链（Logic-driven CoT）
Planner 在输出测试计划前，先对函数进行输入域、输出域、前置条件、后置条件、边界情况的显式分析，引导 Generator 按逻辑覆盖生成测试用例。

### 2. 分层错误修复（Hierarchical Repair）
将测试失败分为五类（syntax/assertion/runtime/timeout/unknown），每类采用差异化修复策略，避免"一刀切"式的随机重试。

### 3. AST 精确替换
使用 `ast` 模块进行代码分析和替换，避免正则表达式在嵌套函数场景下的误匹配问题。

## 论文写作

- [研究动机文档](research_motivation.md)：包含研究背景、问题定义和三个研究问题（RQ）
- [算法形式化描述](algorithm_paper.md)：包含状态转移函数、终止条件、伪代码和复杂度分析

## 实验复现

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 .env

# 3. 运行基准测试（自动对 examples/ 下所有示例文件进行测试）
python experiments/run_benchmark.py

# 4. 查看结果（JSON 格式输出到 experiments/results/）
ls experiments/results/
```

## 单元测试

```bash
pytest tests/ -v --cov=src --cov-report=term-missing
```
