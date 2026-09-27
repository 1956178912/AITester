# Pull Request

## 变更摘要 / Summary

<!-- 简述本 PR 做了什么、为什么做（对齐 Conventional Commits 的 feat/fix/docs/refactor/test/chore） -->

- [ ] 默认行为不变（新能力有独立环境变量开关，关闭时与历史口径一致）

## 自检 / Self-check

### 通用（所有 PR）

- [ ] 新增功能附带单元测试，且全量 `pytest tests/` 零回归
- [ ] `ruff check .` / `ruff format --check .` 全绿（CI 固定 ruff 0.16.3）
- [ ] `mypy` 0 错误（如 CI 矩阵已含 mypy 步骤）
- [ ] 核心维护文档（README / QUICKSTART / api_reference / algorithm_design / CHANGELOG
      及 .en 英文版）已同步；双语文档配对通过 `scripts/check_bilingual_docs.py`
- [ ] 批次落地后已刷新仓库根 `BASELINE.yaml`（实测 pytest / ruff / mypy 输出后更新
      `last_verified` 与对应数字）

### 依赖变更清单（仅当改动 requirements.txt / requirements.lock 时勾选）

- [ ] `requirements.txt` 顶层依赖以 `==` 显式锁版本
- [ ] `requirements.lock` 在目标 Python 版本（CI 矩阵 3.12 / 3.13 / 3.14）下重新生成
- [ ] 本地 `python scripts/check_lock_sync.py` 退出码 0（失败恢复：按提示重新生成 lock）
- [ ] Docker 镜像已重建（`docker build -t aitester:latest .`，构建期预安装同一锁定版本）
- [ ] CI 三版本矩阵（3.12 / 3.13 / 3.14）全绿

详细步骤见 `CONTRIBUTING.md` "依赖变更清单" 一节。

## 链接 / Links

- Issue / 讨论：
- 相关实验数据（可选）：
