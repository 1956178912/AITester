#!/bin/sh
# Pre-commit 钩子：本地提交前跑 CI 同源守卫（与 .github/workflows/ci.yml 共用同一批脚本）。
# 安装：把本文件（或 pre-commit 配置）接入 git hooks：
#   pip install pre-commit && pre-commit install
#   或手动：ln -sf <repo>/.git-hooks/pre-commit.sh .git/hooks/pre-commit
# 手动运行：sh .git-hooks/pre-commit.sh
#
# 守卫口径与 CI 一致（单一实现，防"本地跑通但 CI 挂"漂移）：
#   1. check_baseline_numbers.py —— 当前基线 H2 段不得硬编码测试数字（11. 漂移守卫）
#   2. check_baseline.py         —— BASELINE.yaml 结构校验（5b. 结构校验）
#   3. check_bilingual_docs.py   —— 双语文档同步（默认非 strict 警告；CI 可用 --strict）
# 仅提交时运行（pre-commit），不阻塞本地开发。

set -e

# 定位仓库根目录（钩子从任意 workdir 触发都能跑）
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

PY="${PYTHON:-python3}"

echo "[pre-commit] 运行 CI 同源守卫（check_baseline_numbers / check_baseline / check_bilingual_docs）…"

"$PY" scripts/check_baseline_numbers.py
"$PY" scripts/check_baseline.py
# 双语文档检查：提交时仅警告不阻塞（避免历史警告误拦提交）；CI 用 --strict 门禁用。
"$PY" scripts/check_bilingual_docs.py || true

echo "[pre-commit] 守卫通过。"
