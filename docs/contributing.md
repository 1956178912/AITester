# 贡献指南

> 感谢你对 AITester 项目的关注！本文档说明如何参与项目开发。

---

## 目录

1. [快速开始](#快速开始)
2. [开发环境搭建](#开发环境搭建)
3. [代码规范](#代码规范)
4. [提交规范](#提交规范)
5. [测试要求](#测试要求)
6. [文档要求](#文档要求)
7. [PR 流程](#pr-流程)

---

## 快速开始

```bash
# 1. Fork 仓库
# 2. 克隆到本地
git clone <your-fork-url>
cd AITester

# 3. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 4. 安装依赖
pip install -r requirements.txt
pip install -r requirements-dev.txt  # 开发依赖

# 5. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key

# 6. 运行测试
pytest tests/ -v
```

---

## 开发环境搭建

### 必需工具

- Python 3.10+
- MySQL 5.7/8.0（可选，用于持久化实验数据）
- Git

### 可选工具

- Docker（用于隔离环境）
- pre-commit（代码格式化）

### 安装开发依赖

```bash
pip install -r requirements-dev.txt
```

包含：`pytest`, `pytest-cov`, `black`, `flake8`, `mypy`

---

## 代码规范

### Python 风格

- 遵循 **PEP 8** 规范
- 使用 **4 空格缩进**
- 行长度不超过 **120 字符**
- 使用 **类型注解**（Python 3.10+）

### 代码格式化工具

```bash
# 使用 black 格式化代码
black src/ tests/

# 使用 flake8 检查风格
flake8 src/ tests/

# 使用 mypy 检查类型
mypy src/
```

### 中文注释

所有思考、分析、解释和代码注释**必须使用中文**。

```python
def calculate_discount(price: float, ratio: float) -> float:
    """
    计算折扣价格。
    
    Args:
        price: 原价
        ratio: 折扣比例（0-1）
    
    Returns:
        折后价格
    """
    return price * (1 - ratio)
```

---

## 提交规范

遵循 **Conventional Commits** 规范：

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 类型

| Type | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat: 添加 RAG 检索增强` |
| `fix` | Bug 修复 | `fix: 修复 import 模块名错误` |
| `docs` | 文档更新 | `docs: 更新 API 参考文档` |
| `refactor` | 代码重构 | `refactor: 重构错误分类器` |
| `perf` | 性能优化 | `perf: 优化 RAG 单例初始化` |
| `test` | 测试相关 | `test: 添加 parametrize 校验测试` |
| `chore` | 构建/工具 | `chore: 更新依赖版本` |

### 示例

```bash
# 新功能
git commit -m "feat(generator): 添加 RAG 检索增强支持"

# Bug 修复
git commit -m "fix(debugger): 修复 syntax 错误分类不准确问题"

# 文档更新
git commit -m "docs: 完善 API 参考文档"
```

---

## 测试要求

### 必须覆盖的场景

1. **正常路径**：功能正常工作的场景
2. **边界条件**：输入边界值、空值、极大值等
3. **异常场景**：错误输入、网络异常、API 失败等

### 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行指定测试文件
pytest tests/test_generator.py -v

# 生成覆盖率报告
pytest tests/ -v --cov=src --cov-report=html
```

### 覆盖率要求

- 新功能/修复：**≥ 80%**
- 核心模块：**≥ 90%**

---

## 文档要求

### 必须更新的文档

| 改动类型 | 需要更新的文档 |
|---------|--------------|
| 新功能 | README、API 参考、使用示例 |
| API 变更 | API 参考、CHANGELOG |
| 配置变更 | README 配置说明、`.env.example` |
| 性能优化 | 性能调优指南 |

### 文档格式

- 使用 **Markdown** 格式
- 代码块标注语言类型（`python`, `bash`）
- 提供**可运行的示例**

---

## PR 流程

### 提交 PR 前检查清单

- [ ] 代码已通过所有测试（`pytest tests/ -v`）
- [ ] 新增了必要的测试用例
- [ ] 更新了相关文档
- [ ] 遵循了代码规范和提交规范
- [ ] 无敏感信息泄露（API Key、密码等）

### PR 描述模板

```markdown
## 改动说明
<!-- 简要描述本次改动的目的和内容 -->

## 测试情况
<!-- 列出通过的测试用例 -->

## 影响范围
<!-- 说明改动影响的模块和功能 -->

## 相关 Issue
<!-- 关联的 Issue 编号 -->
```

---

## 问题反馈

如有问题，请通过以下方式反馈：

- **Issue**: GitHub Issues
- **讨论**: GitHub Discussions

---

## 致谢

感谢所有贡献者的付出！
