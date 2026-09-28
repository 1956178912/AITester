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

### 硬性规则：当前基线数字单一来源（BASELINE.yaml）

- **任何核心维护文档不得内嵌已被后续轮次覆盖的数字**（如"1937 passed / 94% 覆盖率 / ruff 0 告警"这类会随批次推进过期的快照）——当前基线数字（测试数 / 覆盖率 / ruff / mypy / CI 矩阵）统一以仓库根 [`BASELINE.yaml`](BASELINE.yaml) 为**机器可读单一事实来源**，核心文档仅保留"指向 BASELINE.yaml 的链接 + 一句话摘要"，不各自硬编码。
- **过期内容必须整节归档而非就地标注**：已被后续轮次覆盖的历史分析 / 基线轨迹，整节移入 `docs/history/`（或 CHANGELOG 对应条目），不得在核心文档内以 ⚠️ / "历史快照"标注方式堆叠在原文中；历史文档头部的归档说明是唯一允许的历史标注位置。
- **维护约定**：任何功能批次落地后，必须先跑全量 `pytest tests/` / `ruff check .` / `mypy` 实测，再同步刷新 `BASELINE.yaml` 的 `last_verified` 与对应数字；未刷新前不得在核心文档引用该批次数字。
- **版本演进历史**（CHANGELOG / api_reference 的版本表）记录的是当时快照，属历史叙事，不随 BASELINE.yaml 刷新——二者边界为"当前基线" vs "历史版本记录"。

## 依赖变更清单（修改 requirements / lock 必做步骤）

`requirements.txt`（顶层依赖 + `==` 锁定）与 `requirements.lock`（含传递依赖的完整锁定）
是**双轨制**：CI 由 `scripts/check_lock_sync.py` 守卫二者同步（顶层依赖必须出现在 lock
中且版本一致）。修改任何依赖时**必须**按以下清单执行，否则容易出现"requirements 加了包
但 lock 没更新 → CI 通过但生产 / Docker 环境行为不一致"的漂移：

1. **改 `requirements.txt`**：顶层依赖用 `==` 显式锁版本（与 CI 固定工具版本同原则，
   避免上游发版导致门禁漂移）；
2. **更新 `requirements.lock`**：在目标 Python 版本（CI 矩阵 3.12 / 3.13 / 3.14）下
   重新生成 lock（pip-compile 或 `pip freeze` 口径，与 lock 现有格式对齐——含传递依赖）；
3. **本地校验**：`python scripts/check_lock_sync.py` 退出码 0（规则 1/2 阻断；规则 4
   的"lock 多余项"仅 WARNING 不阻断，但提示重新生成 lock）；
4. **Docker 镜像**：依赖变更需重建镜像（`docker build -t aitester:latest .`，构建期
   预安装使用同一锁定版本，见 `Dockerfile` 注释）；
5. **CI 矩阵验证**：推 PR 后确认 3.12 / 3.13 / 3.14 三版本矩阵全绿
   （3.13 处于 scipy/pandas 锁定版本支持区间，2026-09-28 批次补入矩阵）。

> PR 提交前请在 PR 模板勾选"依赖变更清单"（见 `.github/PULL_REQUEST_TEMPLATE.md`）。
> 失败恢复：`check_lock_sync.py` 退出码 1 时，按"规则 1 缺失项 / 规则 2 版本脱节"
> 提示定位是 requirements 漏声明还是 lock 版本漂移，重新生成 lock 后再校验。

## 适合新贡献者的入门任务

首次参与推荐从以下类型的问题入手（无需理解全量架构即可上手）：

- **文档补齐**：核心文档的 docstring / 注释勘误、缺失章节（参见 CI 提示的 `check_bilingual_docs.py` 配对缺失项）。
- **回归测试**：在 `tests/` 中补充边界条件用例（先读对应模块 docstring 理解契约）。
- **依赖卫生**：`pip-audit` / `requirements.lock` 同步校验脚本的使用（`scripts/check_lock_sync.py`）。
- **CI 调试**：阅读 `.github/workflows/ci.yml` 各步骤注释，理解门禁意图。

较大的算法 / 架构改动（如错误分类器扩展、跨文件修复策略）建议在 Issue 中先讨论方案，阅读 `docs/algorithm_design.md` 与最近的 `docs/review_*.md` 了解既有设计权衡。

## 依赖豁免登记（pip-audit 漏洞豁免必做步骤）

`pip-audit` 安全扫描命中的已知漏洞，因"上游暂无修复版"而需显式豁免
（CI `--ignore-vuln`）时，**必须**在 [docs/dependency_exemptions.md](docs/dependency_exemptions.md)
登记豁免条目（依赖 / 锁定版本 / 漏洞 ID / 豁免原因 / 复审触发条件 / 复审期限），
不允许"只在 ci.yml 加一行 `--ignore-vuln` 而不在登记表留痕"。

- 新增豁免：先登记、再改 ci.yml（二者同一 PR 落地，保持可审计）；
- 上游发布修复版：按登记表"复审触发条件"列尽快升级、移除 ci.yml 对应
  `--ignore-vuln` 行，并把该条目从登记表"当前豁免"移入"已复审关闭"；
- 每季度复审一次登记表（过期未复审的条目在 CHANGELOG 标注"豁免过期"），
  与"依赖变更清单"的双轨制（requirements / lock）口径一致。
