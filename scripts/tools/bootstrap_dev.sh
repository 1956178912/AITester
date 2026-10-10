#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# 最小可运行配置脚本（bootstrap）：自动完成 venv 创建、依赖安装、两个 env
# 文件复制，并引导用户仅需编辑 .env.local 填入 LLM key。
#
# 对应 QUICKSTART 第 2-4 步的"两步都要做"强调——本脚本把步骤固化下来，
# 失败时给出具体哪一项缺失的提示。
#
# 用法：
#   bash scripts/tools/bootstrap_dev.sh              # 交互式：创建 venv + 安装依赖 + 复制 env 模板
#   bash scripts/tools/bootstrap_dev.sh --check-only # 仅校验当前环境（不创建/不安装）
#   bash scripts/tools/bootstrap_dev.sh --no-install # 跳过 pip install（离线 / 已装好场景）
#
# 退出码：0 = 校验通过；1 = 校验失败（提示缺失项）；2 = 环境错误
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

CHECK_ONLY=0
NO_INSTALL=0
PY="${PYTHON:-python3}"
for arg in "$@"; do
  case "$arg" in
    --check-only) CHECK_ONLY=1 ;;
    --no-install) NO_INSTALL=1 ;;
    -h|--help) grep '^#' "$0" | head -30; exit 0 ;;
    *) echo "未知参数: $arg（支持 --check-only / --no-install）" >&2; exit 2 ;;
  esac
done

info() { echo "── $*"; }
ok()   { echo "   ✓ $*"; }
warn() { echo "   ⚠ $*" >&2; }
fail() { echo "   ✗ $*" >&2; exit 1; }

# ── 1. Python 版本（≥3.12；锁定依赖 scipy 要求）────────────────────────────
info "检查 Python 版本（要求 ≥3.12）"
MIN_PY_MINOR=12
CUR_MINOR=$($PY -c "import sys; print(sys.version_info[1])" 2>/dev/null || echo 0)
if [[ "$CUR_MINOR" -lt "$MIN_PY_MINOR" ]]; then
  fail "当前 Python 主版本 $PY 为 3.$CUR_MINOR（或无法探测），要求 ≥3.12（锁定依赖 scipy 下限）。
       可用 --python3.12 或 PATH 中指向 3.12+ 解释器：PYTHON=python3.12 bash scripts/tools/bootstrap_dev.sh"
fi
ok "Python 3.$CUR_MINOR（≥3.12）"

# ── 2. venv ───────────────────────────────────────────────────────────────────
if [[ "$CHECK_ONLY" -eq 1 ]]; then
  if [[ -x ".venv/bin/python" ]]; then
    PY=".venv/bin/python"
    ok ".venv 已存在（复用）"
  else
    warn "--check-only 模式下 .venv 不存在；跳过安装校验"
  fi
else
  if [[ ! -x ".venv/bin/python" ]]; then
    info "创建 .venv"
    $PY -m venv .venv || fail "venv 创建失败（python3 缺失或权限不足）"
    PY=".venv/bin/python"
    ok ".venv 已创建"
  else
    PY=".venv/bin/python"
    ok ".venv 已存在（复用）"
  fi

  # ── 3. 依赖安装 ────────────────────────────────────────────────────────────
  if [[ "$NO_INSTALL" -eq 1 ]]; then
    warn "--no-install：跳过 pip install -r requirements.txt"
  else
    info "安装依赖（pip install -r requirements.txt）"
    $PY -m pip install --upgrade pip >/dev/null
    $PY -m pip install -r requirements.txt \
      || fail "依赖安装失败：请检查网络 / 锁定版本可用性（CI 矩阵 3.12-3.14）"
    ok "依赖安装完成"
  fi

  # ── 4. 两个 env 文件（两步都要做：非敏感 .env + 敏感 .env.local）─────────
  if [[ ! -f ".env" ]]; then
    info "复制 .env.example → .env（非敏感配置）"
    cp .env.example .env
    ok ".env 已创建"
  else
    ok ".env 已存在（复用，未覆盖）"
  fi

  if [[ ! -f ".env.local" ]]; then
    info "复制 config.local.example → .env.local（LLM 密钥，已 gitignore，勿提交）"
    cp config.local.example .env.local
    ok ".env.local 已创建——请编辑填入 LLM_N_API_KEY 等真实值"
  else
    warn ".env.local 已存在（未覆盖）；若密钥仍为占位符，请手动编辑"
  fi
fi

# ── 5. 配置加载校验（无网络调用）：定位具体缺失项 ─────────────────────────
info "校验 LLM 配置加载（python3 -c \"from config import LLM_CONFIGS\"）"
if $PY - <<'EOF'
import os
from config import LLM_CONFIGS

if not LLM_CONFIGS:
    missing = []
    if not os.path.exists(".env.local"):
        missing.append(".env.local 文件缺失（cp config.local.example .env.local）")
    else:
        text = open(".env.local", encoding="utf-8").read()
        keys = [l for l in text.splitlines() if l.strip().startswith("LLM_") and "=" in l and not l.strip().startswith("#")]
        if not any("_API_KEY=" in l for l in keys):
            missing.append(".env.local 中未找到 LLM_N_API_KEY= 真实值（当前均为占位符）")
        else:
            missing.append("LLM_N_API_KEY 已配置但 config.LLM_CONFIGS 为空——检查 LLM_N_BASE_URL / LLM_N_MODEL_NAME 是否齐全")
    print("   ✗ LLM_CONFIGS 为空。缺失项：")
    for m in missing:
        print(f"       - {m}")
    raise SystemExit(1)
print(f"   ✓ 已加载 {len(LLM_CONFIGS)} 个 LLM 配置")
EOF
then
  ok "LLM 配置校验通过"
else
  fail "配置校验失败（见上方缺失项提示；修复后重跑 bash scripts/tools/bootstrap_dev.sh --check-only）"
fi

# ── O17（2026-09-29 审查 P0）：git hooks 安装 + gitleaks 全历史扫描 ─────
# 历史缺陷：.git-hooks/check_secret_leak.sh 从未被 git 激活（无
# core.hooksPath 设置 + 未安装 pre-commit），41% 敏感模式盲区（仅 sk- 前缀）
# 从未真正拦截过提交。现补两步：
# 1. git config core.hooksPath .git-hooks（激活 O17 全口径守卫）；
# 2. gitleaks 全历史扫描（若已安装）；未安装时提示 + 跳过（不阻断）。
if [[ "$CHECK_ONLY" -eq 0 ]]; then
  info "安装 git pre-commit hooks（O17 密钥守卫）"
  if git rev-parse --git-dir >/dev/null 2>&1; then
    git config core.hooksPath .git-hooks \
      && ok "core.hooksPath → .git-hooks（O17 守卫已激活）" \
      || warn "git config 失败（非 git 仓库或权限不足）"
    # 确保 hooks 可执行
    chmod +x .git-hooks/*.sh 2>/dev/null || true
  else
    warn "非 git 仓库，跳过 hooks 安装"
  fi

  info "gitleaks 全历史扫描（若已安装）"
  if command -v gitleaks >/dev/null 2>&1; then
    gitleaks detect --repo-root . --no-git -v 2>&1 | tail -5 \
      && ok "gitleaks 扫描通过" \
      || warn "gitleaks 检测到疑似凭证（详见上方输出；请 rotate + filter-branch 清理历史）"
  else
    warn "gitleaks 未安装——建议 brew install gitleaks 或 apt install gitleaks"
  fi
fi

info "bootstrap 校验全部通过"
echo
echo "下一步："
echo "  1. 编辑 .env.local 填入真实 LLM_N_API_KEY（若第 4 步提示缺失）"
echo "  2. 可选额度探测：$PY scripts/tools/check_quota.py"
echo "  3. 一键冒烟：bash scripts/tools/smoke_test.sh（含一次最小 LLM 调用）"
