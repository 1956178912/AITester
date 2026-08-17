# LaTeX 本地安装指南

> 生成时间：2026-08-16
> 目标：在本地编译 AITester 论文

---

## 📦 方案对比

| 方案 | 大小 | 安装时间 | 难度 | 推荐度 |
|-----|------|---------|------|--------|
| **MacTeX** | 5.5 GB | 10-15 分钟 | 简单 | ⭐⭐⭐⭐⭐ |
| **TinyTeX** | 500 MB | 3-5 分钟 | 简单 | ⭐⭐⭐⭐ |
| **Homebrew** | 5.5 GB | 10-15 分钟 | 中等 | ⭐⭐⭐ |
| **Docker** | 4 GB | 5-10 分钟 | 中等 | ⭐⭐⭐ |

**推荐方案**：TinyTeX（轻量、快速）或 MacTeX（完整、稳定）

---

## 方案 1: TinyTeX（推荐）

### 1.1 通过 R 安装
```bash
# 启动 R
R

# 在 R 中执行
install.packages('tinytex')
tinytex::install_tinytex()

# 验证
tinytex::tlmgr("--version")
pdflatex --version
```

### 1.2 通过 npm 安装
```bash
# 安装 tinytex npm 包
npm install -g tinytex

# 安装 TinyTeX
tinytex::install_tinytex()

# 验证
pdflatex --version
```

### 1.3 直接安装脚本
```bash
# 下载并运行安装脚本
curl -fsSL https://yihui.org/tinytex/install.sh | sh

# 添加到 PATH（重启终端或执行）
export PATH="$HOME/.TinyTeX/bin/universal-darwin:$PATH"

# 验证
pdflatex --version
```

---

## 方案 2: MacTeX（完整方案）

### 2.1 下载安装
```bash
# 访问官方网站
open https://tug.org/mactex/

# 下载 MacTeX-2024.dmg (约 5.5 GB)
# 双击挂载并运行安装程序
# 选择自定义安装（可选）
# 等待安装完成（约 10-15 分钟）
```

### 2.2 验证安装
```bash
pdflatex --version
mpost --version
bibtex --version
```

---

## 方案 3: Homebrew

### 3.1 安装 Homebrew（如果未安装）
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 3.2 安装 MacTeX
```bash
brew install --cask mactex
```

### 3.3 验证安装
```bash
pdflatex --version
```

---

## 方案 4: Docker

### 4.1 拉取镜像
```bash
docker pull texlive/texlive:latest
```

### 4.2 编译论文
```bash
cd /Users/wangchenyu/Workspace/AITester/docs/paper
docker run --rm -v "$(pwd)":/tmp:ro texlive/texlive:latest pdflatex -interaction=nonstopmode /tmp/paper.tex
```

---

## 📝 编译论文步骤

### 步骤 1: 进入论文目录
```bash
cd /Users/wangchenyu/Workspace/AITester/docs/paper
```

### 步骤 2: 首次编译
```bash
pdflatex -interaction=nonstopmode paper.tex
```

### 步骤 3: 生成参考文献
```bash
bibtex paper
```

### 步骤 4: 再次编译（解决引用）
```bash
pdflatex -interaction=nonstopmode paper.tex
pdflatex -interaction=nonstopmode paper.tex
```

### 步骤 5: 验证 PDF
```bash
open paper.pdf
```

---

## ⚠️ 常见问题

### 问题 1: pdflatex 命令找不到
**解决方案**：
```bash
# 检查 PATH
echo $PATH

# 添加 TeX Live 到 PATH
export PATH="/usr/local/texlive/2024basic/bin/universal-darwin:$PATH"

# 或 TinyTeX
export PATH="$HOME/.TinyTeX/bin/universal-darwin:$PATH"
```

### 问题 2: 缺少某个 LaTeX 包
**解决方案**：
```bash
# 使用 tlmgr 安装
tlmgr install <package-name>

# 例如
tlmgr install collection-fontsrecommended
```

### 问题 3: 编译速度慢
**解决方案**：
- 使用 `-interaction=nonstopmode` 避免交互提示
- 使用 `-halt-on-error` 快速定位错误
- 考虑使用 LuaLaTeX 或 XeLaTeX 加速

---

## 📊 推荐配置

### 开发环境
- **编辑器**：VS Code + LaTeX Workshop 插件
- **预览器**：Skim (macOS) 或 Adobe Acrobat
- **版本控制**：Git（排除 .aux, .log, .pdf 文件）

### .gitignore 配置
```gitignore
# LaTeX 输出文件
*.aux
*.bbl
*.blg
*.log
*.out
*.toc
*.pdf
!paper.pdf  # 保留最终 PDF

# 编译中间文件
*.synctex.gz
*.fls
*.fdb_latexmk
```

---

## 🎯 快速开始

### 最快方案（TinyTeX）
```bash
# 1. 安装 TinyTeX（5 分钟）
curl -fsSL https://yihui.org/tinytex/install.sh | sh

# 2. 编译论文（2 分钟）
cd /Users/wangchenyu/Workspace/AITester/docs/paper
pdflatex -interaction=nonstopmode paper.tex
bibtex paper
pdflatex -interaction=nonstopmode paper.tex
pdflatex -interaction=nonstopmode paper.tex

# 3. 查看结果
open paper.pdf
```

**总耗时：约 7 分钟**

---

## 📞 技术支持

- **TeX Live 文档**：https://www.tug.org/texlive/
- **TinyTeX 文档**：https://yihui.org/tinytex/
- **LaTeX 入门教程**：https://www.latex-project.org/help/
- **常见问题**：https://tex.stackexchange.com/

---

**最后更新**：2026-08-16
**推荐方案**：TinyTeX（轻量快速）或 MacTeX（完整稳定）
