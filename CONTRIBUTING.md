> **语言 / Language**：[English](CONTRIBUTING.en.md) | 简体中文（本文）

# 贡献指南

感谢你对 AITester 的关注！本文档说明如何参与项目开发。

## 开发环境搭建

```bash
# 克隆仓库
git clone <repository-url> && cd AITester

# 创建虚拟环境（Python 3.12+；锁定依赖 scipy 要求 ≥3.12）
python3 -m venv .venv && source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env           # 非敏感项
cp config.local.example .env.local   # LLM 密钥（LLM_N_*，已 gitignore，勿提交）
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

覆盖率要求：核心模块 ≥ 92%，整体 ≥ 90%。

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

## 文档组织约定

- **核心维护文档**（随功能更新）：`README.md` / `QUICKSTART.md` / `docs/api_reference.md` / `docs/algorithm_design.md` / `CHANGELOG.md` 及各自的 `.en.md` 英文版——功能批次落地后需同步更新，由 CI 的 `scripts/check_bilingual_docs.py` 守卫中英文配对完整性。
- **历史归档文档**（`docs/history/`，含 `optimization_plan.md` / `optimization_report.md` 等）：记录历史轮次的工作决策与实验记录，**非当前维护文档**，仅作开发内部参考，无需随版本迭代更新；每篇文档头部有归档说明，当前决策以 CHANGELOG 为准。
- **审查 / 审计报告**（`docs/review_*.md` / `docs/*_audit_findings.md`）：对应轮次的审查快照，完成后归入历史快照，不要求长期同步。

## 适合新贡献者的入门任务

首次参与推荐从以下类型的问题入手（无需理解全量架构即可上手）：

- **文档补齐**：核心文档的 docstring / 注释勘误、缺失章节（参见 CI 提示的 `check_bilingual_docs.py` 配对缺失项）。
- **回归测试**：在 `tests/` 中补充边界条件用例（先读对应模块 docstring 理解契约）。
- **依赖卫生**：`pip-audit` / `requirements.lock` 同步校验脚本的使用（`scripts/check_lock_sync.py`）。
- **CI 调试**：阅读 `.github/workflows/ci.yml` 各步骤注释，理解门禁意图。

较大的算法 / 架构改动（如错误分类器扩展、跨文件修复策略）建议在 Issue 中先讨论方案，阅读 `docs/algorithm_design.md` 与最近的 `docs/review_*.md` 了解既有设计权衡。
