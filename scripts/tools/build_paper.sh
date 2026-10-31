#!/usr/bin/env bash
# 投稿 PDF 构建脚本：**先跑判据 → 再编译 → 再跑判据**。
#
# 为什么是这个顺序（CZ 轮 2026-10-26）：
#   CR 轮加了「可排版文本不得含 CJK」判据，但**判据不会自己执行**——CY 轮与 CZ 轮
#   **连续两轮**把中文写进 `refs.bib` 的 note 字段，都是**先编译、后（才发现）**跑判据：
#   LaTeX 报 `Unicode character … not set up for use with LaTeX`，参考文献处缺字形。
#   两次都是判据最终抓到了（8/8），但那时产物已经坏了。**判据是可执行的，不是自动的**：
#   要防复发，就得把「先跑判据」变成**流程的固定第一步**，而不是靠人记得。
#
# 三步各自的职责：
#   1. **前置判据**（audit --strict --pre-build）：源文件已经不合格 ⇒ **拒绝编译**（不产出坏产物）；
#   2. **编译**：标准 TeX Live（pdflatex ×2 → bibtex → pdflatex，排到 `.aux` 不再
#      变化为止，通常三遍、最多五遍）；不写死路径，先找 PATH 再找 TinyTeX；
#   3. **后置判据**：构建可能改变读数（页数、文献数）⇒ 重新对账；不一致时**退出码非 0**
#      并打印需要更新的读数 ⇒ 投稿包在数字对齐前**不算完成**。
#
# 用法：
#   scripts/tools/build_paper.sh              # 构建三份 PDF 并对账
#   AITESTER_PY=python3 scripts/tools/build_paper.sh
#
# 退出码：0 = 全部对齐；1 = 判据红（前置或后置）或编译失败；2 = 用法/环境错误。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="${AITESTER_PY:-$REPO_ROOT/.venv/bin/python3}"
AUDIT="$REPO_ROOT/paper/scripts/tools/audit_paper_numbers.py"
PAPER_DIR="$REPO_ROOT/paper"
TEX_DIR="$PAPER_DIR/tex"

die() { echo "[build-paper] ❌ $*" >&2; exit "${2:-2}"; }

# ── 环境：python 与 TeX ───────────────────────────────────────────────────
[ -x "$PY" ] || PY="$(command -v python3)" || die "找不到 python3（可设 AITESTER_PY）"
[ -f "$AUDIT" ] || die "找不到审计器 $AUDIT"
if ! command -v pdflatex >/dev/null 2>&1; then
  TINYTEX_BIN="$HOME/Library/TinyTeX/bin/universal-darwin"
  if [ -d "$TINYTEX_BIN" ]; then
    PATH="$PATH:$TINYTEX_BIN"
    export PATH
  fi
fi
command -v pdflatex >/dev/null 2>&1 || die "找不到 pdflatex（装 TeX Live 或 TinyTeX，见 docs/study/PAPER_BUILD.md）"
command -v bibtex   >/dev/null 2>&1 || die "找不到 bibtex"

echo "[build-paper] 工具链：pdflatex=$(command -v pdflatex)"

# ── 1. 前置判据：源文件不合格就不编译 ───────────────────────────────────
# `--pre-build`：源文件刚改过时产物必然过期，页数对账留给构建后（否则本脚本
# 在编辑源文件后的第一次运行就红在「产物已过期」，永远进不到编译步骤）。
echo "[build-paper] ① 前置判据（audit --strict --pre-build）……"
if ! "$PY" "$AUDIT" --strict --pre-build; then
  die "前置判据未通过——**不编译**（源文件已不合格，编译只会产出坏产物）" 1
fi

# ── 2. 编译 ──────────────────────────────────────────────────────────────
echo "[build-paper] ② 编译稿件（pdflatex ×2 → bibtex → pdflatex，按 Rerun 提示收敛）……"
cd "$TEX_DIR" || die "找不到 $TEX_DIR"
rm -f manuscript.aux manuscript.bbl manuscript.blg manuscript.log \
      manuscript.out manuscript.fdb_latexmk manuscript.fls manuscript.pdf
pdflatex -interaction=nonstopmode manuscript.tex >/dev/null 2>&1 \
  || die "稿件第一遍 pdflatex 失败（看 $TEX_DIR/manuscript.log）" 1
bibtex manuscript >/dev/null 2>&1 || die "bibtex 失败（看 $TEX_DIR/manuscript.blg）" 1
pdflatex -interaction=nonstopmode manuscript.tex >/dev/null 2>&1 \
  || die "稿件第二遍 pdflatex 失败（看 $TEX_DIR/manuscript.log）" 1
# 从零构建时：第 1 遍没有 .bbl，引文按 `?` 占位；第 2 遍引文入版后分节页码整体
# 后移（实测 68 → 70 页）。LaTeX **只在引用未定义时**报 `Rerun`，页码变化本身不报，
# 所以拿「上一遍的 .aux == 这一遍的 .aux」当收敛判据——它逐字记录 `\newlabel` 的页码。
prev_aux="$(mktemp)"
cp manuscript.aux "$prev_aux"
passes=2
while :; do
  pdflatex -interaction=nonstopmode manuscript.tex >/dev/null 2>&1 \
    || { rm -f "$prev_aux"; die "稿件第 $((passes + 1)) 遍 pdflatex 失败（看 $TEX_DIR/manuscript.log）" 1; }
  passes=$((passes + 1))
  if cmp -s "$prev_aux" manuscript.aux; then
    rm -f "$prev_aux"
    break
  fi
  cp manuscript.aux "$prev_aux"
  [ "$passes" -ge 5 ] \
    && { rm -f "$prev_aux"; die "pdflatex 第 $passes 遍后 .aux 仍未收敛（看 $TEX_DIR/manuscript.log）" 1; }
done
grep -q 'There were undefined references\|Citation .* undefined' manuscript.log \
  && die "仍有未定义的引用/文献（看 $TEX_DIR/manuscript.log）" 1

for stem in cover_letter title_page; do
  cd "$PAPER_DIR" || die "找不到 $PAPER_DIR"
  pdflatex -interaction=nonstopmode "$stem.tex" >/dev/null 2>&1 \
    || die "$stem.tex 编译失败（看 $PAPER_DIR/$stem.log）" 1
done

# 产物读数（**从构建产物的日志里取**，不手写）
man_pages="$(grep -o 'Output written on manuscript.pdf ([0-9]* pages' "$TEX_DIR/manuscript.log" \
  | grep -o '[0-9]*' | head -1)"
man_bib="$(grep -c '\\bibitem' "$TEX_DIR/manuscript.bbl")"
echo "[build-paper] 产物读数：manuscript = ${man_pages:-?} 页 / ${man_bib:-?} 条 bibitem"
echo "[build-paper]          cover_letter = $(grep -o 'Output written on cover_letter.pdf ([0-9]* pages' "$PAPER_DIR/cover_letter.log" | grep -o '[0-9]*' | head -1) 页"
echo "[build-paper]          title_page   = $(grep -o 'Output written on title_page.pdf ([0-9]* pages' "$PAPER_DIR/title_page.log" | grep -o '[0-9]*' | head -1) 页"

# ── 3. 后置判据：读数是否仍与投稿材料一致 ───────────────────────────────
echo "[build-paper] ③ 后置判据（audit --strict）……"
if ! "$PY" "$AUDIT" --strict; then
  echo "[build-paper] ⇒ 构建本身成功，但**投稿材料的数字已与产物脱节**。" >&2
  echo "[build-paper]    请把 paper/SUBMISSION.md 与 paper/title_page.tex 里的页数格与" >&2
  echo "[build-paper]    refs.bib 条数格更新为实测值（稿件 ${man_pages:-?} 页 / ${man_bib:-?} 条），" >&2
  echo "[build-paper]    然后重跑本脚本。" >&2
  exit 1
fi

echo "[build-paper] ✅ 三份 PDF 已构建，且与投稿材料的声明一致。"
