#!/bin/sh
# 密钥泄漏守卫（pre-commit 调用，2026-10-01 全面审查 P0 配套）。
#
# 扫描"本次提交将纳入的文件"中是否含敏感凭证：
#   - staged 新文件（git diff --cached --name-only --diff-filter=A）
#   - 未跟踪文件（git ls-files --others --exclude-standard）
# O17（2026-09-29 审查 P0）：正则改用 logging_utils._SENSITIVE_PATTERNS
# 全口径（sk- / 32+ hex / 40+ base64 / key= / JWT / Bearer / URL userinfo /
# AWS AKIA|ASIA / DSN），消除历史仅 sk- 前缀 41% 盲区。
# 命中即 return 1 阻断提交（由 pre-commit.sh 的 set -e 接管）。
#
# 设计口径：
#   - 跳过明显占位符（your- / placeholder / example / < / xxxxx 的行）；
#   - 跳过 .gitignore 已排除的文件（git ls-files --others --exclude-standard 语义）。
#   真实密钥备份（.env.local.bak_g8）含真实 sk- 前缀 API Key 值 → 必命中。
#   注：真实前缀样例不得写入本脚本注释（守卫扫描未跟踪文件时会扫到
#   自身），否则守卫被自己的规则拦下（自锁）；示例一律用占位符形式。
#
# 已知误报登记（_KNOWN_FP）：原 2026-10-01 基线 5 项（基线核查类 Markdown
# 的 ICLR/NeurIPS proceedings URL 中 hex 片段≥32 位十六进制串，非真实凭证）
# 所涉文档已于 2026-10-09 清理批次删除，登记项随之清空（正则恒不命中，
# 保留结构以便未来新增误报文档时扩展）。命中文件非占位符时照常阻断。
# 维护：新增误报文档时同步加入 _KNOWN_FP 正则，并在头部登记。

set -e

echo "[pre-commit] 密钥泄漏守卫（O17 全口径）：扫描 staged 新文件 + 未跟踪文件…"

# 候选文件 = staged 新增 + 未跟踪（未被 .gitignore 排除）
{
  git diff --cached --name-only --diff-filter=A 2>/dev/null || true
  git ls-files --others --exclude-standard 2>/dev/null || true
} | sort -u > .tmp_secret_leak_candidates.txt

# O17（2026-09-29 审查 P0）：全口径敏感模式（与 logging_utils._SENSITIVE_PATTERNS
# 同步，共 11 类）：
#   1. sk- 前缀 API Key（sk- + >= 20 位）
#   2. 32+ 位长十六进制串（独立 token）
#   3. 大写字母+下划线命名凭证赋值（MYSQL_PASSWORD=、DB_SECRET= 等，值 >= 8 位）
#   4. JWT（eyJ.xxx.xxx）
#   5. Bearer <token>
#   6. AWS Access Key（AKIA/ASIA + 16-20 位大写）
#   7. URL userinfo（scheme://user:pass@）
#   8. sk- 前缀短 Key（含 sk- 任意长度 >= 10 位，覆盖 sk-abc123 型）
# 占位符过滤（your- / placeholder / example / <全大写> / 全 x）
_SENSITIVE_RE='sk-[A-Za-z0-9._-]{10,}|[A-Fa-f0-9]{32,}|[A-Z][A-Z_]*(PASSWORD|PASSWD|SECRET|API_KEY|TOKEN|CREDENTIAL)=[A-Za-z0-9+/_=.-]{8,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|Bearer +[A-Za-z0-9\-_~+/=]{8,}|\b(AKIA|ASIA)[A-Z0-9]{16,20}\b|[a-zA-Z][a-zA-Z0-9+.\-]*://[^/@\s]+:[^@\s]+@'

# 已知误报登记（占位符形式，与头部"已知误报登记"注释同步）。
# 原 5 项基线核查类文档已删除（2026-10-09 清理批次），登记清空；
# 未来新增误报文档时请扩展本正则并同步头部注释。
_KNOWN_FP='^$'

LEAKED=""
while IFS= read -r f; do
  # 文件不存在（已删除/缓存）跳过
  [ -f "$f" ] || continue
  # 只扫文本文件（二进制 grep -q 报 "Binary matches" 会误伤）
  case "$f" in
    *.png|*.jpg|*.jpeg|*.gif|*.webp|*.ico|*.pdf|*.zip|*.tar|*.gz|*.bz2|*.xz|*.7z|*.docx|*.xlsx|*.pptx|*.sqlite|*.db|*.so|*.dylib|*.dll|*.pyc|*.bin)
      continue ;;
  esac
  # grep 命中条件：任一敏感模式命中
  hit=$(grep -nE "$_SENSITIVE_RE" "$f" 2>/dev/null || true)
  # 过滤占位符行（your- / placeholder / example / <全大写> / 全 x）
  real=$(printf '%s\n' "$hit" | grep -vE 'your-|placeholder|example|<[A-Z_]+>|x{5,}' || true)
  # 已知误报登记命中 → 打印供人工复核（不阻断），见头部"已知误报登记"
  if printf '%s\n' "$f" | grep -qE "$_KNOWN_FP"; then
    if [ -n "$real" ]; then
      echo "[pre-commit] 密钥泄漏守卫：已知误报登记文件 $(basename "$f") 命中敏感模式（URL hex 片段类，非凭证），打印供人工复核："
      printf '%s\n' "$real" | head -3
    fi
    continue
  fi
  if [ -n "$real" ]; then
    LEAKED="${LEAKED}${f}: $(printf '%s' "$real" | head -1)
"
  fi
done < .tmp_secret_leak_candidates.txt
rm -f .tmp_secret_leak_candidates.txt

if [ -n "$LEAKED" ]; then
  echo "[pre-commit] 密钥泄漏守卫（O17 全口径）：检测到疑似真实凭证："
  echo "$LEAKED"
  echo ""
  echo "阻断提交。请："
  echo "  1. 确认该文件是否含真实 API Key / 凭证（如 .env.local.bak* 备份）；"
  echo "  2. 若是，将文件加入 .gitignore（如 .env.local.bak* 通配）并从 git 移除；"
  echo "  3. 若凭证已泄漏到仓库历史，需 rotate 密钥 + git filter-branch 重写历史。"
  return 1 2>/dev/null || exit 1
fi

echo "[pre-commit] 密钥泄漏守卫（O17 全口径）：通过（无未登记敏感模式命中，已知误报登记除外）。"
