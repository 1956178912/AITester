# AITester - 多智能体自动化测试与自修复系统

基于 LangGraph 多智能体协作的自动化测试系统，可自动为 Python 代码生成 pytest 单元测试，并在测试失败时利用大语言模型（LLM）分析根因并尝试修复代码，直至测试通过或达到最大迭代次数。

## 功能特性

- **自动化测试生成**：Planner + Generator 双智能体协作生成 pytest 测试用例
- **智能调试修复**：Debugger 分析测试失败，自动生成代码补丁
- **多轮迭代修复**：最多 3 轮修复尝试，自动验证修复效果
- **多 LLM 支持**：兼容 OpenAI、DeepSeek、Qwen 等 API
- **实验数据记录**：MySQL 数据库记录任务、测试结果和修复历史

## 系统架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Planner   │────▶│  Generator  │────▶│   Executor  │
│  (测试规划)  │     │  (测试生成)  │     │  (测试执行)  │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                              │
                    ┌─────────────────────────┘
                    │  测试失败?
                    ▼
              ┌─────────────┐     ┌─────────────┐
              │  Debugger   │────▶│PatchApplier │
              │  (智能调试)  │     │  (补丁应用)  │
              └─────────────┘     └──────┬──────┘
                                         │
                                         ▼
                                    ┌─────────────┐
                                    │   Re-test   │
                                    │  (重新测试)  │
                                    └─────────────┘
```

## 环境要求

- Python 3.11+
- MySQL 8.0+
- Docker（可选，默认本地执行）

## 安装步骤

### 1. 克隆项目

```bash
git clone <repository-url>
cd AITester
```

### 2. 创建虚拟环境

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置以下变量：

```bash
# LLM API 配置（示例：OpenAI）
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-4o-mini
TEMPERATURE=0.2

# LLM API 配置（示例：Agnes AI）
# OPENAI_API_KEY=sk-xxxx
# OPENAI_BASE_URL=https://apihub.agnes-ai.com/v1
# MODEL_NAME=agnes-2.5-flash

# 数据库配置
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=aitester

# 工作流配置
MAX_ITERATIONS=3
COVERAGE_THRESHOLD=80.0
```

### 5. 初始化数据库

```bash
python init_db.py
```

## 使用方法

### 基本使用

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行单个测试任务
python main.py run examples/calculator.py --func divide

# 指定最大迭代次数
python main.py run examples/calculator.py --func divide --max-iterations 5

# 列出可用示例
python main.py list-examples
```

### 输出示例

```
补丁已应用到文件: examples/calculator.py

==================================================
任务完成：examples/calculator.py
被测函数：divide
测试通过：True
修复迭代：1/3
==================================================

✓ 测试全部通过！
```

### 命令行参数

**run 命令参数：**
- `target_file`：被测 Python 文件路径（必填）
- `--func, -f`：指定被测函数名
- `--max-iterations`：最大修复迭代次数（默认 3）
- `--coverage-threshold`：覆盖率阈值（默认 80%）

## 示例说明

### 示例代码 (examples/calculator.py)

```python
def add(a: float, b: float) -> float:
    return a + b

def divide(a: float, b: float) -> float:
    # BUG: 除零时未做检查
    return a / b

def factorial(n: int) -> int:
    # BUG: 负数输入未做处理
    if n == 0:
        return 1
    return n * factorial(n - 1)
```

### 工作流程

1. **Planner** 分析代码，生成测试计划
2. **Generator** 根据计划生成 pytest 测试代码
3. **Executor** 执行测试，捕获结果
4. 如果测试失败：
   - **Debugger** 分析失败原因，生成修复补丁
   - **PatchApplier** 将补丁应用到源代码
   - 重新执行测试，直到通过或达到最大迭代次数

## 数据库表结构

### tasks 表

记录每个测试任务的基本信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| target_file | VARCHAR(500) | 被测文件路径 |
| target_function | VARCHAR(200) | 被测函数名 |
| created_at | TIMESTAMP | 创建时间 |
| status | ENUM | 任务状态 |
| result | TEXT | 执行结果 |

### test_runs 表

记录每次测试执行的结果。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| task_id | INT | 关联任务 |
| test_code | MEDIUMTEXT | 测试代码 |
| passed | BOOLEAN | 是否通过 |
| output | MEDIUMTEXT | 测试输出 |
| coverage | FLOAT | 覆盖率 |
| iteration | INT | 迭代次数 |
| created_at | TIMESTAMP | 创建时间 |

### repair_history 表

记录每次修复尝试的详情。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| task_id | INT | 关联任务 |
| diagnosis | TEXT | 根因诊断 |
| patch | MEDIUMTEXT | 修复补丁 |
| iteration | INT | 迭代次数 |
| created_at | TIMESTAMP | 创建时间 |

## 扩展开发

### 添加新智能体

1. 在 `src/agents/` 下新建智能体类，继承 `BaseAgent`
2. 在 `src/prompts/templates.py` 中添加 System Prompt
3. 在 `src/graph/workflow.py` 中注册节点并调整路由逻辑

### 更换 LLM 提供商

修改 `.env` 配置文件：
- `OPENAI_API_KEY`：API 密钥
- `OPENAI_BASE_URL`：API 地址
- `MODEL_NAME`：模型名称

### 启用 Docker 执行

设置 `.env`：
```bash
DOCKER_ENABLED=true
DOCKER_IMAGE=python:3.11-slim
```

## 技术栈

- **核心语言**：Python 3.11+
- **AI 框架**：LangChain, LangGraph
- **LLM 接口**：OpenAI 兼容 API
- **测试框架**：pytest, pytest-cov
- **数据库**：MySQL, pymysql
- **CLI**：click

## 注意事项

1. 确保 `.env` 中配置了有效的 API Key
2. MySQL 服务需提前启动
3. Docker 模式需要本地 Docker 守护进程
4. 本系统为研究原型，未做大规模并发优化

## 学术引用

本项目可用于软件工程领域的实验验证，适用于 ICSE、FSE、ASE 及中文期刊《软件学报》等学术会议和期刊。

## License

MIT License
