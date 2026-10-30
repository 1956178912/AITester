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
# 所涉文档已于 2026-10-09 清理批次删除。2026-10-26（DU 收口提交批次）新增
# 两项：`docs/history/CHANGELOG_2026-10-26_full*.md` 是冻结的历史归档，正文
# 含 sha256 摘要（64 位 hex）与「曾误报的占位值」说明文字（如 AKIA+PLACEHOLDER），
# 均为记录而非凭证；命中仅打印供人工复核，不阻断。命中文件非占位符时照常阻断。
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
# 2026-10-26（DU 收口提交批次）新增：`docs/history/CHANGELOG_2026-10-26_full*.md`
# 是冻结的历史归档，正文含 sha256 摘要（64 位 hex）与「曾误报的占位值」说明
# 文字（如 AKIA+PLACEHOLDER），均为记录而非凭证。
# 2026-10-30（B1 批收口提交）新增两项证据目录：
#   - experiments/results/emse_ult_mutk_full_20261029/：D3 全量 Mut@k 终版
#     分片工件，每份的 `cosmic_ray_config_hash` 是 cosmic-ray 配置文件内容
#     指纹（40 位 hex），非凭证；
#   - experiments/results/emse_ult_specir_probe_20261014/：specir/gold probe
#     归档（带 SHA256SUMS 完整性清单，64 位 hex 摘要）与批次 provenance 的
#     `git_sha`（40 位 hex）。
#   - experiments/results/q05_interaction_attribution_20261030/：Q05 聚合工件
#     目录（2026-10-30 收口）自带 SHA256SUMS 完整性清单（64 位 hex 摘要）。
#   - experiments/results/swe_pro_judge_20261030/：SWE-bench Pro 判定工件
#     目录（2026-10-30 收口）自带 SHA256SUMS 完整性清单（64 位 hex 摘要）。
#   - experiments/results/q04q07_ab_20261030/ 与 g8_fullstack_20261030/：
#     六臂 LLM 批 + G8 工件（2026-10-30 晚收口），SHA256SUMS/批次 provenance
#     的 git_sha 与 trace 内 system_fingerprint 均为记录而非凭证。
# 七处均为记录而非凭证；命中仅打印供人工复核，不阻断。命中文件非占位符时照常阻断。
# 维护：新增误报文档时同步加入 _KNOWN_FP 正则，并在头部登记。
_KNOWN_FP='^docs/history/CHANGELOG_2026-10-26_full(\.en)?\.md$|^experiments/results/emse_ult_mutk_full_20261029/|^experiments/results/emse_ult_specir_probe_20261014/|^experiments/results/q05_interaction_attribution_20261030/|^experiments/results/swe_pro_judge_20261030/|^experiments/results/q04q07_ab_20261030/|^experiments/results/g8_fullstack_20261030/'

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
  real=$(printf '%s\n' "$hit" | grep -viE 'your-|placeholder|example|<[A-Z_]+>|x{5,}' || true)
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
