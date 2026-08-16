# 贡献指南

感谢你对 AITester 的关注！本文档说明如何参与项目开发。

## 开发环境搭建

```bash
# 克隆仓库
git clone <repository-url> && cd AITester

# 创建虚拟环境（Python 3.10+）
python3 -m venv .venv && source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
```

## 提交规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

- `feat:` 新功能
- `fix:` 修复 bug
- `docs:` 文档变更
- `refactor:` 重构代码
- `test:` 测试相关
- `chore:` 构建/工具相关

示例：
```bash
git commit -m "feat: 添加合成数据集生成器"
git commit -m "fix: 修复 parametrize 校验逻辑错误"
```

## 代码风格

- Python 遵循 [PEP 8](https://peps.python.org/pep-0008/)
- 所有函数必须包含中文 docstring
- 行长度 ≤ 120 字符
- 使用类型注解（typing 模块）

## 测试要求

新增功能必须附带单元测试：

```bash
# 运行全部测试
.venv/bin/python -m pytest tests/ -v

# 查看覆盖率
.venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

覆盖率要求：核心模块 ≥ 90%，整体 ≥ 80%。

## Pull Request 流程

1. Fork 本仓库
2. 创建特性分支（`git checkout -b feat/xxx`）
3. 提交变更（`git commit -m "feat: xxx"`）
4. 推送到 Fork 仓库（`git push origin feat/xxx`）
5. 创建 Pull Request

## 问题反馈

请使用 GitHub Issues 报告 bug 或提出功能建议，格式如下：

- **Bug 报告**：复现步骤、预期行为、实际行为、环境信息
- **功能建议**：问题描述、解决方案、使用场景
