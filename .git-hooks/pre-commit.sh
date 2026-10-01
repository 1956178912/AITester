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
#   4. check_secret_leak.sh      —— 未跟踪/新增文件含 sk-/sk-ws-/sk-or- 密钥前缀即阻断
#   5. ruff check + format --check —— O34 新增：与 CI Lint 步骤同口径（防 D.3 复发）
# 仅提交时运行（pre-commit），不阻塞本地开发。

set -e

# 定位仓库根目录（钩子从任意 workdir 触发都能跑）
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

PY="${PYTHON:-python3}"

echo "[pre-commit] 运行 CI 同源守卫（check_lock_sync / check_credential_scrub / check_baseline_numbers / check_baseline / check_bilingual_docs / check_secret_leak）…"

# lock 同步守卫（requirements.lock 与 pyproject 一致性，CI 同名步骤）
if [ -f scripts/check_lock_sync.py ]; then
  "$PY" scripts/check_lock_sync.py
fi
# 凭证脱敏审计（4.2 日志脱敏门禁，CI 同名步骤；缺失时跳过不阻断）
if [ -f scripts/check_credential_scrub.py ]; then
  "$PY" scripts/check_credential_scrub.py
fi
# 依赖豁免守卫（check_dependency_exemptions.py，缺失时跳过）
if [ -f scripts/check_dependency_exemptions.py ]; then
  "$PY" scripts/check_dependency_exemptions.py
fi
"$PY" scripts/check_baseline_numbers.py
"$PY" scripts/check_baseline.py
# 双语文档检查：提交时仅警告不阻塞（避免历史警告误拦提交）；CI 用 --strict 门禁用。
"$PY" scripts/check_bilingual_docs.py || true

# O34（2026-09-30 全面审查优化 P1）：与 CI "Lint with ruff" 同口径的本地门禁。
# 根因（此前审查 D.3"推送后 CI 必挂"复发面）：.pre-commit-config.yaml 的
# ruff / ruff-format 钩子依赖 pre-commit 框架（本机未安装 → 从未执行），
# 本地提交前没有任何格式化检查 → 只跑 ruff check --fix 不跑 ruff format
# 就会把"21 files would be reformatted"推上 CI。
# 现直接调用本机 ruff（.venv 优先，回退 PATH），与 CI 固定版本 0.16.3 同源。
RUFF=""
if [ -x ".venv/bin/ruff" ]; then
  RUFF=".venv/bin/ruff"
elif command -v ruff >/dev/null 2>&1; then
  RUFF="ruff"
fi
if [ -n "$RUFF" ]; then
  echo "[pre-commit] ruff check . + ruff format --check .（与 CI Lint 步骤同口径）"
  "$RUFF" check .
  "$RUFF" format --check .
else
  echo "[pre-commit] 未找到 ruff（.venv/bin/ruff / PATH），跳过 lint 门禁——注意 CI 仍会执行，可能红" >&2
fi

# 密钥泄漏守卫（2026-10-01 全面审查 P0）：扫描"本次提交将纳入的文件"（staged
# 新文件 + 未跟踪文件）中是否含 sk-/sk-ws-/sk-or- 前缀的 API Key 行。命中即
# 阻断提交（set -e 下 return 1）。防 .env.local.bak* 类密钥备份被 git add -A 误提交。
# 口径：仅查 .env* / *.local / *bak* / llm_configs.json 等高敏文件名，避免误伤
# 测试夹具中的合成占位符（如 your-*-api-key-here）。
# O35（2026-09-30 全面审查 P2）：check_secret_leak.sh 此前未纳入版本库，而本钩子
# 在 `set -e` 下无条件调用它 → 全新 clone 安装钩子后每次提交都 exit 127（脚本
# 不存在），钩子反而挡住一切提交。现补存在性守卫（与其他守卫同口径），
# 并保留"脚本缺失时显式告警"（该守卫只在本地生效，CI 侧由 gitleaks 覆盖）。
if [ -f .git-hooks/check_secret_leak.sh ]; then
  sh .git-hooks/check_secret_leak.sh
else
  echo "[pre-commit] 警告：.git-hooks/check_secret_leak.sh 缺失，跳过密钥泄漏守卫（建议 git add 纳入版本库）" >&2
fi

echo "[pre-commit] 守卫通过。"
