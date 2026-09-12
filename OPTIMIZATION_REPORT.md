# AITester 项目优化报告

> 本报告为 2026-09-11 优化轮次的完整交付记录。阶段 0 基线与阶段 1 优化点清单
> 详见 `OPTIMIZATION_PLAN.md`；阶段 3-5 已在同一轮内完成，阶段 6 推送与 PR 待用户最终确认。
>
> **后续轮次**：2026-09-12 轮次（文档数据对齐批次，N-01~N-04）的完整记录见文末
> 「附录：2026-09-12 轮次」；2026-09-13 轮次（文档数据对齐批次，M-01~M-03）的完整记录见
> 「附录：2026-09-13 轮次」；2026-09-13 系统功能增强轮次（3.1/3.4/4.1/2.3/1.5）的完整记录见
> 「附录：2026-09-13 系统功能增强轮次」。优化点清单与实施批次详见 `OPTIMIZATION_PLAN.md` 同名章节。

## 阶段 0：基线检查

### Git 状态（本次执行时的实测快照）

- **分支**：`main`，工作区 clean
- **本地领先**：`origin/main` 15 个提交（本次会话开始时的 `ahead` 计数；阶段 6 推送后归零）
- **远程**：`https://github.com/1956178912/AITester.git`

### 项目结构

```
AITester/
├── src/                    # 核心包（find_packages 会收录）
│   ├── agents/             # 多智能体（Planner/Generator/Executor/Debugger/ErrorClassifier）
│   ├── api/                # API 管理与多模型轮换
│   ├── cli/                # 命令行入口（app.py + output.py）
│   ├── config/             # 配置生成与管理（config_manager.py + config_generator.py）
│   ├── datasets/           # SWE-bench/Defects4J 加载与合成数据集
│   ├── db/                 # MySQL 客户端
│   ├── experiments/        # 实验分析与报告
│   ├── graph/              # LangGraph 工作流编排
│   ├── prompts/            # 提示词模板
│   ├── rag/                # 检索增强生成
│   ├── reports/            # 实验报告生成
│   ├── tools/              # 工具（代码分析、补丁应用、依赖管理）
│   └── utils/              # 通用工具（辅助函数、异常、日志）
├── tests/                  # ~38 个测试文件
├── examples/               # 示例代码
├── experiments/            # 实验输出与中间数据（部分被 .gitignore 排除）
├── scripts/                # 辅助脚本
├── docs/                   # 文档
├── config.py               # 全局配置（集中管理环境变量）
├── llm_configs.json        # LLM 配置（按 provider 分组的元数据，不含真实 key）
├── setup.py                # 包管理
├── main.py                 # CLI 薄封装（委托给 src/cli/app.py）
├── requirements.txt        # 依赖锁定（== 版本）
├── requirements.lock       # 全量锁文件（pip freeze 产物）
├── .env.example            # 环境变量示例（模板）
├── .env.local.template     # LLM 敏感配置模板
├── .github/workflows/ci.yml  # CI 配置（测试 + 安全扫描）
└── ...
```

### 技术栈与包管理器

- **语言**：Python 3.14.6（venv）
- **框架**：langchain 1.3.15、langchain-openai 1.4.3、langgraph 1.2.11
- **数据库**：pymysql 1.2.0、DBUtils 3.1.2
- **测试**：pytest 9.1.1、pytest-cov 7.1.0、pytest-timeout 2.4.0
- **Lint**：ruff 0.16.3
- **依赖管理**：pip（requirements.txt == 锁定 + requirements.lock 全量锁）
- **入口**：`aitester=src.cli.app:cli`（setup.py console_scripts）

### 命令清单

| 操作 | 命令 |
|------|------|
| 安装依赖 | `pip install -r requirements.txt` |
| 构建/打包 | `pip install .` 或 `python -m build` |
| 运行测试 | `python -m pytest tests/` |
| 覆盖率 | `python -m pytest tests/ --cov=src --cov-report=term` |
| Lint | `ruff check .` |
| 格式化 | `ruff format --check .` |
| 类型检查 | 无显式 mypy/pyright 配置（项目未启用静态类型检查器） |
| 安全扫描 | `pip-audit -r requirements.txt`（CI 中执行） |

### 基线结果

| 检查项 | 命令 | 结果 | 备注 |
|--------|------|------|------|
| Ruff Lint | `ruff check .` | ✅ 通过 | All checks passed |
| Ruff 格式 | `ruff format --check .` | ✅ 通过 | 121 files already formatted |
| 单元测试 | `python -m pytest tests/` | ✅ 通过 | 1020 passed, 2 warnings, 28.4s |
| 覆盖率 | `--cov=src` | ✅ 91% | TOTAL 3536/326 miss = 91% |
| 类型检查 | 无 mypy 配置 | ⚠️ 不适用 | 项目未引入静态类型检查器 |
| 构建 | `pip install .` | ⚠️ 未验证 | 基线未执行，需阶段 4 补充 |

### 敏感信息说明

- `.env`、`.env.local`、`.env.local.bak` 均被 `.gitignore` 排除，未被 Git 跟踪
- `config.py` 从 `.env.local` 读取 LLM 敏感配置（LLM_N_* 变量），不硬编码密钥
- `llm_configs.json` 仅记录 provider 元数据，不含真实 API Key
- ⚠️ 本地 `.env` 文件含真实密钥（OPENAI_API_KEY、OPENAI_API_KEY_2、OPENAI_API_KEY_3），但**未被 Git 跟踪**

---

## 阶段 1：项目检索与优化点识别

优化点全表（16 项，含去重后证据、影响、优先级、验证方式）见 `OPTIMIZATION_PLAN.md`「阶段 1 优化点清单」。
要点摘要：

- **文档陈旧（P2/P3，4 项）**：README 幽灵测试文件 4 行（D-01）、用例数/覆盖率数据陈旧（D-02/D-08）、消融开关措辞与 .env.example 不一致（D-09）
- **日志脱敏盲区（P2，D-07）**：`logging_utils.py` 旧正则仅覆盖 `sk-` 前缀 + 字母数字 20+ 位，本地真实密钥中「带点号分段的长 sk- 型」「无 sk- 前缀长 hex/base64」两类可绕过脱敏 → 已扩展正则并补 14 个合成占位符用例
- **沙箱审计（P1 待确认，T-04）**：executor subprocess 边界需专项审计，本轮不做（高风险、需设计文档，列入后续建议）
- **密钥泄露（P1 提示项，D-05）**：本地 `.env` / `src/.env.local` 含真实 API Key 明文（sk- 前缀 2 条 + 无 sk- 前缀长 key 1 条），均未被 Git 跟踪（`git ls-files` 核实）；**不在本次代码改动范围**，建议用户尽快轮换这些 key
- **测试可维护性（P3，T-01）**：各测试文件重复构造 LLMConfig/APIManager mock，可下沉公共 fixture —— 重构面大，列为后续建议
- **CLI 分支覆盖（P2，T-03）**：parallel/json 边界缺用例 → 已补 4 个参数校验用例
- **本地配置漂移（P3，D-04）**：本地 `.env` 的 `DOCKER_IMAGE=python:3.11-slim` 与模板/默认 3.12-slim 不一致 → 已在本地修正（`.env` 不入库，无 commit）

## 阶段 2：优化计划

计划表（批次 A/B/C + 后续建议 + 需确认项）见 `OPTIMIZATION_PLAN.md`「本次实施范围」。
用户已确认：① 批次 B1 脱敏正则扩展纳入本轮；② 本地 .env 顺手改为 3.12-slim；③ 阶段 4 全量验证；④ 推送 main 并创建 PR。

## 阶段 3：实施优化

全部改动已提交（提交历史见 `git log`），对应关系：

| 提交 | 内容 |
|------|------|
| `40ef2e7` docs(readme) | 移除测试状态表中 4 个不存在的测试文件（A1） |
| `cd058b4` docs(readme) | 用例数/覆盖率对齐 0.9.11 基线（A2 第一阶段） |
| `4c7e17d` docs(readme) | 消融实验开关配置位置措辞对齐（A3） |
| `0558090` fix(utils) | 日志脱敏正则覆盖点号/无 sk- 前缀密钥 + 新增 test_logging_utils.py（B1） |
| `e5252a6` fix(packaging) | setup.py 声明 py_modules 收录根级 config；CLI 参数校验补测（B2 + 打包修复） |
| `94433a2` style(tests) | ruff format 归一新增测试文件 |
| `68fb35f` docs(changelog) | 补充 Unreleased 优化轮次条目 + README 用例数对齐 1038（A2 收敛） |
| `80e2f05` fix(utils) | 测试与注释中的真实密钥形态改为合成占位符（敏感信息零容忍） |
| `ab9edb7` chore(changelog) | CHANGELOG 同步脱敏占位符口径 |

本地 .env 的 DOCKER_IMAGE 修正（C1）为工作区外文件，无 commit。

## 阶段 4：全面测试

本次执行实测结果（venv Python 3.14.6，命令与 CI 对齐）：

| 检查项 | 命令 | 结果 | 备注 |
|--------|------|------|------|
| 单元测试 | `python -m pytest tests/ -q` | ✅ 1038 passed, 2 warnings, 27.7s | 2 个 warning 为 scipy 数值精度提示，非代码问题 |
| Lint | `ruff check .` | ✅ All checks passed | ruff 0.16.3（与 lock 一致） |
| 格式化 | `ruff format --check .` | ✅ 124 files already formatted | |
| lock 同步 | `python scripts/check_lock_sync.py` | ✅ requirements.txt（19 项）与 requirements.lock（130 项）一致 | CI 同款检查 |
| 构建 | `python -m build --wheel` | ✅ 构建 aitester-0.9.11-py3-none-any.whl（107 文件） | 已验证 config.py 进 wheel（修复点回归） |
| 安全扫描 | `pip-audit -r requirements.txt --no-deps --ignore-vuln ...` | ✅ No known vulnerabilities found, 5 ignored | 豁免清单与 CI 一致（chromadb 暂无修复版，见 ci.yml 注释） |
| 类型检查 | 无 mypy/pyright 配置 | ⚠️ 不适用 | 项目未引入静态类型检查器，保持现状 |
| 覆盖率 | `pytest --cov=src` | ✅ 91% | 与 CHANGELOG/README 口径一致 |

## 阶段 5：更新文档

- `CHANGELOG.md`：Unreleased 轮次条目已补齐（安全/打包/测试/文档四节，见 `git log` 中 `68fb35f`、`80e2f05`、`ab9edb7`）
- `README.md`：用例数 1038 / 覆盖率 91% 已对齐；幽灵测试文件行已删；消融开关措辞已对齐
- `OPTIMIZATION_PLAN.md` / `OPTIMIZATION_REPORT.md`：阶段 0-5 的完整记录（本文件 + 计划文件），随本轮一并提交
- 本地 `.env`：DOCKER_IMAGE → 3.12-slim（不入库，无文档影响）

## 阶段 6：上传 GitHub

用户已确认「推送 main 并创建 PR」。实际执行结果：**推送仍受阻于网络**——
2026-09-11 19:07 复测：`curl https://github.com` 短连接可达（HTTP 200），但 `git push`
两次（默认 60s / 180s 超时窗口内）均失败：
`Failed to connect to github.com port 443 after 75003 ms: Couldn't connect to server`。
特征：HTTP GET 能通、git 的长连接 443 握手挂起（疑似出站链路对 git 协议大包/长连接有限制）。
工作区 clean，commit 状态完好。

将推送内容：`origin/main`（d42bbdd）落后的全部 **17 个 commit**（`bd4de49`…`eaf7931`，
完整清单见 `git log refs/remotes/origin/main..main --oneline`；较上一版记录多出 1 个
`eaf7931` docs 收尾提交）。

手动执行命令（恢复网络/代理后）：

```bash
cd /Users/wangchenyu/Workspace/AITester
# 1. 推送 main（若 443 握手再次挂起，可先试降档再推：
#    git config http.version HTTP/1.1
#    或设置代理：git config http.proxy http://127.0.0.1:<port>）
git push origin main

# 2. 创建 PR（gh 未安装，可用 GitHub Web 或先安装 gh 执行）
gh pr create --base main \
  --title "chore(optimize): 0.9.11 优化轮次——文档对齐、日志脱敏扩展、打包修复与 CI 安全门禁同步" \
  --body-file /dev/stdin <<'EOF'
## 背景
0.9.11 基线（1020 用例 / 91% 覆盖 / ruff 全绿）上的优化轮次：修复 README 陈旧数据与幽灵条目、日志脱敏正则盲区、setup.py 打包缺根级 config、pip-audit 豁免清单漂移。

## 变更内容
- **fix(utils)**：日志脱敏正则扩展（带点号分段 sk- 型 / 无 sk- 前缀长 hex·base64）+ 测试注释真实密钥形态改合成占位符（敏感信息零容忍）
- **fix(packaging)**：setup.py `py_modules=["config"]`（正式安装后入口不再 ModuleNotFoundError）+ extras 补全
- **chore(ci)**：pip-audit 豁免清单同步实测漏洞 ID（CVE-4583x → PYSEC-2026-3813/3814/3815）
- **fix(datasets / experiments / utils)**：Defects4J O(n²) 消除、显著性 skipped 条目 KeyError、extract_code_block 误吞标识符行
- **docs(readme / changelog / optimize)**：用例数 1038 对齐、幽灵测试文件行删除、消融开关措辞、OPTIMIZATION_PLAN/REPORT 入库

## 测试结果
| 检查项 | 命令 | 结果 |
|--------|------|------|
| 单元测试 | `pytest tests/ -q` | 1038 passed / 0 failed（27.7s） |
| Lint | `ruff check .` | All checks passed |
| 格式化 | `ruff format --check .` | 124 files already formatted |
| lock 同步 | `python scripts/check_lock_sync.py` | 通过（19 vs 130 项一致） |
| 构建 | `python -m build --wheel` | aitester-0.9.11-py3-none-any.whl（config.py 已验证入包） |
| 安全扫描 | `pip-audit`（同 CI 豁免清单） | No known vulnerabilities found, 5 ignored |
| 覆盖率 | `pytest --cov=src` | 91%（与 README/CHANGELOG 口径一致） |

## 风险与回滚
- 脱敏正则扩展为纯新增匹配分支，旧用例全部通过（1038 无失败），无误伤回归；回滚单条 `git revert 0558090` 即可
- setup.py 修复为纯声明补齐，对 editable 安装无行为变化；回滚 `git revert e5252a6`
- pip-audit 豁免漂移为 CI 配置同步，无运行时影响；回滚 `git revert 3bf75bb`
- 本 PR 不含敏感信息（真实密钥仅存在于 gitignored 的本地 .env，提交历史已用合成占位符归一，见 80e2f05）

## 检查清单
- [x] 构建 / 测试 / lint / 格式化 / lock 同步全绿
- [x] 全量 1038 用例通过，覆盖率 91% 与文档对齐
- [x] 无敏感信息入库（git ls-files 核实 .env 系未跟踪）
- [x] 无未说明的破坏性变更（setup.py extras 新增为增量）
- [x] 文档（README/CHANGELOG/OPTIMIZATION_*）与代码一致

## 本轮追加验证（2026-09-11 19:06-19:07）

| 检查项 | 命令 | 结果 | 备注 |
|--------|------|------|------|
| 单元测试 | `python -m pytest tests/ -q` | ✅ 1038 passed, 2 warnings, 28.07s | 2 warning 为 scipy 精度提示 |
| Lint | `ruff check .` | ✅ All checks passed | ruff 0.16.3 |
| 格式化 | `ruff format --check .` | ✅ 124 files already formatted | |
| lock 同步 | `python scripts/check_lock_sync.py` | ✅ 19 vs 130 项一致 | |
| 构建 | `python -m build --wheel` | ✅ aitester-0.9.11-py3-none-any.whl | config.py 入包已验证 |
| 安全扫描 | `pip-audit`（CI 同款豁免） | ✅ No known vulnerabilities found, 5 ignored | 豁免 PYSEC-2026-311/3813/3814/3815 |
| 覆盖率 | `pytest --cov=src` | ✅ TOTAL 91%（3536 行） | 与文档口径一致 |
| 推送 | `git push origin main` | ❌ 443 握手挂起（75s 超时 ×2） | 17 commit 已就绪，见上节手动命令 |
EOF
```

> 若 `gh` 不可用：浏览器打开 `https://github.com/1956178912/AITester/compare/main...main`（推送后自动出现 compare 链接）→ Create new pull request，正文用上面 `## 背景` 到 `## 检查清单` 的内容。

## 阶段 7：最终报告

### 完成状态
- 阶段 0-5：**全部完成**，工作区 clean，本地 main 领先 origin/main 17 个 commit
- 阶段 6：**受阻于网络**（2026-09-11 19:07 复测：HTTP 短连接可达但 git 443 长连接握手挂起，
  两次 push 失败；gh 未安装），17 个 commit 已就绪、未推送；手动命令与 PR 正文见上节，
  恢复网络后 `git push origin main` 即完成

### 优化项清单及结果
| 项 | 结果 |
|----|------|
| D-01 README 幽灵测试文件 4 行 | ✅ 已删（40ef2e7） |
| D-02/D-08 用例数/覆盖率陈旧 | ✅ 对齐 1038/91%（cd058b4 + 68fb35f） |
| D-09 消融开关措辞 | ✅ 对齐（4c7e17d） |
| D-04 本地 .env DOCKER_IMAGE 漂移 | ✅ 本地修正 3.11→3.12-slim（不入库） |
| D-07 日志脱敏正则盲区 | ✅ 扩展 + 14 个合成占位符用例（0558090） |
| D-05 本地真实密钥 | ⚠️ 仅提醒，未动代码；`80e2f05` 已将测试/注释中的真实密钥形态归一为占位符；**建议尽快轮换 .env 中的 LLM key** |
| B2 CLI 参数校验缺口 | ✅ 补 4 用例（e5252a6） |
| T-01 公共 fixture 下沉 / T-04 executor 沙箱审计 | 📋 列为后续建议（重构面大 / 需设计文档） |
| 打包缺陷（发现于本轮验证） | ✅ setup.py py_modules 修复（e5252a6） |
| CI pip-audit 豁免漂移 | ✅ 同步（3bf75bb） |

### 测试结果汇总
全量 pytest 1038 passed / ruff check·format 全绿 / lock 同步通过 / wheel 构建成功且 config.py 入包 / pip-audit 无未豁免漏洞 / 覆盖率 91%。明细表见「阶段 4」。

### 文档更新汇总
CHANGELOG（Unreleased 条目）、README、OPTIMIZATION_PLAN/REPORT 全部入库；代码注释无冗余新增。

### 风险与回滚
- 所有改动均可按 commit 粒度 `git revert <hash>` 回滚（单文件为主，无跨文件耦合）
- 脱敏正则为纯新增匹配分支，1038 用例零失败即回归证据
- setup.py 为声明补齐，editable 开发流程行为不变
- 无敏感信息入库；本地 .env 真实密钥建议轮换（与本次代码改动无关）

### 后续建议
1. 恢复网络后执行阶段 6 手动命令推送 17 个 commit 并开 PR（正文已备好）
2. 轮换本地 .env 中的 LLM API Key（已在会话中暴露过一次，零容忍原则下建议更换）
3. T-01 公共 fixture 下沉（测试可维护性）与 T-04 executor 沙箱深度审计（需设计文档）排入下一迭代
4. chromadb 修复版发布后升级并移除 ci.yml 对应 `--ignore-vuln`（PYSEC-2026-3813/3814/3815）

---

## 附录：2026-09-12 轮次（文档数据对齐批次）

> 该轮次在 0.9.11 轮次 18 个待推送 commit 之上执行，新增 4 个 commit
> （`d1afffc` / `5c7fc80` / `d683741` / `a563d60`）。优化点清单（N-01~N-04）与
> 检索结论见 `OPTIMIZATION_PLAN.md`「0.9.11 后续优化轮次（2026-09-12）」章节。

### 阶段 0：基线检查

- **Git 状态**：`main`，工作区 clean，本地领先 `origin/main` 18 个 commit
- **新基线**（venv Python 3.14.6）：

| 检查项 | 命令 | 结果 |
|--------|------|------|
| 单元测试 | `python -m pytest tests/ -q` | ✅ 1038 passed, 2 warnings, 27.9s |
| 覆盖率 | `--cov=src` | ✅ TOTAL 91%（3536/318 miss） |
| Lint | `ruff check .` | ✅ All checks passed |
| 格式化 | `ruff format --check .` | ✅ 124 files already formatted |
| lock 同步 | `python scripts/check_lock_sync.py` | ✅ 19 vs 130 项一致 |
| 构建 | `python -m build --sdist --wheel` | ✅ aitester-0.9.11.tar.gz + .whl |
| 安全扫描 | `pip-audit`（同 CI 豁免清单） | ✅ No known vulnerabilities found, 5 ignored |
| 类型检查 | 无 mypy/pyright 配置 | ⚠️ 不适用（与上轮一致） |

### 阶段 1：优化点识别（要点）

- **N-01（P2）**：README 测试状态表核心模块覆盖率数据陈旧（logging_utils 83%→88%、cli/app.py 61%→64%），上轮新增 18 用例后未同步
- **N-02（P2）**：README 安全扫描说明仍写"4 条已知 CVE"，ci.yml 已漂移为 PYSEC 豁免口径
- **N-03（P3）**：QUICKSTART 第 4 步"验证配置"措辞与实际行为不符（`from config import LLM_CONFIGS` 仅加载校验，无网络调用）
- **N-04（P2）**：README 引用的测试文件逐一 `ls` 核对，**全部存在**，无需修改（无 commit）
- 检索结论（无优化点维度）：源码无 eval/exec/os.system 危险调用；源码与测试无真实密钥残留（80e2f05 归一后复核通过）；依赖全量与 lock 同步、pip-audit 无未豁免漏洞；CI 结构完整无漂移；src 无 TODO/FIXME 残留

### 阶段 3：实施记录

| 提交 | 内容 |
|------|------|
| `d1afffc` docs(readme) | N-01 覆盖率数据对齐 88%/64% |
| `5c7fc80` docs(readme) | N-02 安全扫描说明对齐 PYSEC 豁免口径 |
| `d683741` docs(quickstart) | N-03 配置验证步骤措辞修正 |
| `a563d60` docs(changelog) | CHANGELOG 补本轮 Unreleased 条目 |

（N-04 核对无漂移，无 commit；纯文档改动，未触碰源码，最小验证为 `ruff check` + 相关测试子集全绿。）

### 阶段 4：全面测试（全部命令与 CI 对齐，venv Python 3.14.6）

| 检查项 | 命令 | 结果 | 备注 |
|--------|------|------|------|
| 单元测试 | `python -m pytest tests/ -q` | ✅ 1038 passed, 2 warnings, 28.6s | 2 warning 为 scipy 数值精度提示，非代码问题 |
| Lint | `ruff check .` | ✅ All checks passed | ruff 0.16.3 |
| 格式化 | `ruff format --check .` | ✅ 124 files already formatted | |
| lock 同步 | `python scripts/check_lock_sync.py` | ✅ 19 vs 130 项一致 | |
| 构建 | `python -m build --sdist --wheel` | ✅ tar.gz + whl 均成功 | |
| 安全扫描 | `pip-audit -r requirements.txt --no-deps --ignore-vuln ...` | ✅ No known vulnerabilities found, 5 ignored | 豁免清单与 CI 一致 |
| 覆盖率 | `pytest --cov=src` | ✅ TOTAL 91% | 与 README/CHANGELOG 口径一致 |
| 类型检查 | 无 mypy/pyright 配置 | ⚠️ 不适用 | 项目未引入静态类型检查器，保持现状 |

### 阶段 5：文档更新

- `CHANGELOG.md`：新增 2026-09-12 Unreleased 轮次条目（文档批次 + 全量测试结果）
- `OPTIMIZATION_PLAN.md` / `OPTIMIZATION_REPORT.md`（本附录）：本轮完整记录入库
- README/QUICKSTART：N-01~N-03 对齐改动随代码 commit 提交

---

## 附录：2026-09-13 轮次（文档数据对齐批次 M-01~M-03）

> 该轮次在 2026-09-12 轮次 4 个 commit（`d1afffc`/`5c7fc80`/`d683741`/`a563d60`）之上执行。
> 09-12 轮次 18 个待推 commit 已推送完成（工作区 clean、本地与 origin/main 同步），
> 本轮新增 2 个 commit（`5553c35` + 计划/报告入库提交）。
> 优化点清单（M-01~M-03）与检索结论见 `OPTIMIZATION_PLAN.md`「0.9.11 后续优化轮次（2026-09-13）」章节。

### 阶段 0：基线检查

- **Git 状态**：`main`，工作区 clean，本地与 `origin/main` 同步（09-12 轮次存量已推完）
- **新基线**（venv Python 3.14.6）：

| 检查项 | 命令 | 结果 |
|--------|------|------|
| 单元测试 | `python -m pytest tests/ -q` | ✅ 1038 passed, 2 warnings, 28.1s |
| 覆盖率 | `--cov=src` | ✅ TOTAL 91%（3536/318 miss） |
| Lint | `ruff check .` | ✅ All checks passed |
| 格式化 | `ruff format --check .` | ✅ 124 files already formatted |
| lock 同步 | `python scripts/check_lock_sync.py` | ✅ 19 vs 130 项一致 |
| 构建 | `python -m build --sdist --wheel` | ✅ tar.gz + whl 均成功 |
| 安全扫描 | `pip-audit`（同 CI 豁免清单） | ✅ No known vulnerabilities found, 5 ignored |
| 类型检查 | 无 mypy/pyright 配置 | ⚠️ 不适用（与上轮一致） |

### 阶段 1：优化点识别（要点）

- **M-01（P2）**：README「测试覆盖模块」主表 13 个文件的用例数与实测 `def test_` 计数漂移（0.9.11 批次新增 27 回归用例后未同步）：test_api_manager 62→63、test_cli_app 11→15、test_config_manager 29→32、test_dataset_loader_extended 57→62、test_dependency 27→35、test_error_classifier 56→60、test_executor 35→39、test_experiments_analysis 11→15、test_experiments_scripts 8→10、test_generator 21→30、test_mysql_client 12→13、test_patch_applier 36→38、test_workflow 28→30
- **M-02（P2）**：README "41 个测试文件" 与 tests/ 实际 44 个 .py 不符；主表缺 `test_logging_utils.py`（0.9.11 轮次新增的 14 用例脱敏测试）——更正为 44 并补行
- **M-03（P3）**：CHANGELOG 补 2026-09-13 Unreleased 轮次条目（本轮纯文档改动需可追溯）
- 检索结论（无优化点维度）：src 无 eval/exec/os.system 危险调用（复核通过）；executor `_run_pytest_with_retry` 的 subprocess.run 为受控 pytest 命令（timeout/cwd/env 限定，非用户输入拼接），沙箱边界无逃逸调用；真实密钥仅存于 gitignored 的本地 .env（sk- 2 条）与 src/.env.local（sk- 5 条），`git ls-files` 仅跟踪占位符模板，建议轮换；依赖 130 项与 lock 同步，pip-audit 无未豁免漏洞；CI 结构无漂移；docs/ 与 QUICKSTART 无旧数据残留

### 阶段 3：实施记录

| 提交 | 内容 |
|------|------|
| `5553c35` docs(readme) | M-01 主表 13 行用例数同步 + M-02 文件数 41→44 与补 test_logging_utils 行 |
| （计划/报告入库提交） docs(optimize) | M-03 CHANGELOG 条目 + OPTIMIZATION_PLAN/REPORT 09-13 章节 |

（v0.9/v0.10 历史版本叙事表保留原值，按设计不随基线同步；纯文档改动，未触碰源码。）

### 阶段 4：全面测试（全部命令与 CI 对齐，venv Python 3.14.6）

| 检查项 | 命令 | 结果 | 备注 |
|--------|------|------|------|
| 单元测试 | `python -m pytest tests/ -q` | ✅ 1038 passed, 2 warnings | 纯文档改动，测试集无变化 |
| Lint | `ruff check .` | ✅ All checks passed | ruff 0.16.3 |
| 格式化 | `ruff format --check .` | ✅ 124 files already formatted | |
| lock 同步 | `python scripts/check_lock_sync.py` | ✅ 19 vs 130 项一致 | |
| 构建 | `python -m build --sdist --wheel` | ✅ tar.gz + whl 均成功 | |
| 安全扫描 | `pip-audit`（CI 同款 4 条 PYSEC 豁免） | ✅ No known vulnerabilities found, 5 ignored | |
| 覆盖率 | `pytest --cov=src` | ✅ TOTAL 91% | 与 README/CHANGELOG 口径一致 |
| 类型检查 | 无 mypy/pyright 配置 | ⚠️ 不适用 | 保持现状 |

### 阶段 5：文档更新

- `CHANGELOG.md`：新增 2026-09-13 Unreleased 轮次条目（M-01/M-02 说明 + 全量测试结论）
- `OPTIMIZATION_PLAN.md` / `OPTIMIZATION_REPORT.md`（本附录）：本轮完整记录入库
- `README.md`：主表 13 行 + 文件数 + 补 test_logging_utils 行（随 `5553c35` 提交）

### 阶段 6：上传 GitHub

用户确认"文档批次 + 推送，推送不成功就重试"。执行 `git push origin main`（本轮 2 个 commit；
09-11/09-12 轮次的 18 个存量已在此前推送完成）。若 443 握手挂起（历史轮次经验），按降档
`git config http.version HTTP/1.1` 或代理方案重试；仍失败则输出手动命令 + 说明。

### 阶段 7：后续建议

1. 轮换本地 .env / src/.env.local 中的 LLM API Key（零容忍原则，跨轮次保留建议）
2. T-01 公共 fixture 下沉（测试可维护性）与 T-04 executor 沙箱深度审计（需设计文档）排入下一迭代
3. chromadb 修复版发布后升级并移除 ci.yml 对应 `--ignore-vuln`（PYSEC-2026-3813/3814/3815；311 重复两条为其别名条目）

---

## 附录：2026-09-13 系统功能增强轮次（3.1 / 3.4 / 4.1 / 2.3 / 1.5）

### 用户清单核对（先甄别已实现项，避免重复造轮子）

用户提出 20 条优化建议，逐条核对代码现状后确认 **8 条系统已实现**（建议写于代码更新前）：

| 用户条目 | 现状 | 证据位置 |
|---------|------|---------|
| 1.2 错误分类细化（import/type/logic） | ✅ 已实现 | `src/agents/error_classifier.py`（P2 细化：IMPORT_ERROR/TYPE_ERROR/LOGIC_ERROR 已从旧五类拆出） |
| 1.3 依赖隔离 | ✅ 已实现 | `EXECUTOR_USE_VENV` + 沙箱 venv + `PYTHONPATH` 控制 + 依赖自动安装（`src/tools/dependency.py`） |
| 1.4 连接池配置化 | ✅ 已实现 | `MYSQL_POOL_*` 从 `config.py` 环境变量读取（`src/db/mysql_client.py`） |
| 2.1 SWE-bench 校验 | ✅ 已实现 | `validate_task` / `quality_report` / `_extract_suggested_function` + 源码补充通道（`dataset_loader.py`） |
| 2.2 Token 效率对比 | ✅ 已实现 | `src/graph/token_usage.py` + benchmark `token_metrics` 聚合 |
| 2.3 RAG 检索质量 | ✅ 已实现 | `evaluate_retrieval`（Hit Rate/MRR）+ `--enable-rag` + `RAG_PERSIST_PATH`（默认 `rag_data/`） |
| 1.1 日志脱敏全链路 | ✅ 已实现 | `SensitiveFormatter` 覆盖异常堆栈 + base_agent 全 LLM 路径接入脱敏 |
| 4.3 熔断器 | ✅ 已实现 | `APIHealth.max_consecutive_failures` 阈值接线（连续失败 N 次标记不健康、剔出路由） |

### 本批实现（真正缺失的 4 项 + 2 项补强，6 个原子 commit）

| 序号 | 目标 | 文件 | 状态 |
|------|------|------|------|
| F1 | 4.1 结构化 JSONL 追踪层（默认关） | `src/observability/{__init__,trace}.py` + workflow 节点 + CLI + benchmark 接线 + `tests/test_trace_observability.py`（12 用例） | ✅ |
| F2 | 3.4 成本感知路由 + 成本告警 | `src/api/api_manager.py`（COST_AWARE 策略 + 昂贵 provider WARNING）+ `config.py`（LLMConfig.cost_weight）+ `tests/test_cost_aware_routing.py`（10 用例） | ✅ |
| F3 | 3.1 多候选补丁与验证（默认关，无候选回退单补丁） | `src/tools/multi_candidate.py` + workflow `_patch_applier_node` 接入 + `tests/test_multi_candidate.py`（19 用例） | ✅ |
| F4 | 2.3 合成数据集默认开 RAG + `--no-rag` | `reproduce.sh`（synthetic/examples 默认 `--enable-rag`）+ `run_benchmark.py`（`--no-rag` 参数） | ✅ |
| F5 | 1.5 CLI parallel/json 边界补测 + 文档对齐 | `tests/test_cli_app.py`（`TestRunParallelJsonBoundaries` 6 用例）+ `.env.example` / CHANGELOG / README / `QUICKSTART` 同步 | ✅ |

### 全量验证结果

| 检查项 | 命令 | 结果 |
|--------|------|------|
| Ruff Lint | `ruff check .` | ✅ All checks passed |
| Ruff 格式 | `ruff format --check .` | ✅ 130 files already formatted |
| 全量测试 | `python -m pytest tests/` | ✅ **1085 passed** / 0 failed |
| 覆盖率 | `--cov=src` | ✅ TOTAL 3813 / 348 miss = 91% |
| 端到端 smoke | 多候选 generate→select + 追踪落盘 | ✅ 坏候选被静态筛除、好候选选中、JSONL 事件序列正确 |
| 打包 | `find_packages()` | ✅ `src.observability` / `src.tools` 均收录 |

### 设计决策（默认关闭的开关）

- **3.1 / 4.1 均默认关闭**（`ENABLE_MULTI_CANDIDATE_PATCH=false` / `AITESTER_TRACE_DIR` 未设），保持历史实验口径不变；开启为显式行为，无隐式行为变化。
- **3.1 无有效候选自动回退单补丁**：多候选策略"只多不少"，保证不会比原路径更差。
- **3.4 成本字段走 `.env.local`**（`LLM_N_COST_WEIGHT`，gitignore 不入库），未配置默认 1.0 基准；如需持久化可在 `llm_configs.json` 加 cost_weight 字段（本批先用环境变量口径，避免改 JSON 结构）。

### 阶段 6：上传 GitHub

本批 7 个原子 commit（6 个功能/测试 + 1 个文档批次），经代理 `http://127.0.0.1:7891`
推送到 `origin/main`（443 直连不可达时按历史经验配置 http.proxy）。推送后执行
`git filter-repo` 重写历史，移除全部论文/隐私相关路径（paper.md、docs/paper/、
TASK_SUMMARY.md、.agent-teams/、SUBMISSION_* 等），`--force` 推送干净历史到 GitHub。

### 阶段 7：后续建议

1. **3.2 跨文件修复**与 **3.3 测试用例质量挖掘**：本批未实施（改动面大，涉及 patch_applier 跨文件依赖分析 + 测试自验证过滤），建议单独立项并配设计文档。
2. **4.2 Docker 实际启用**：仍维持 `use_docker=False` 预留（历史 D-06 决策），接通需确认实验环境有 Docker daemon。
3. 推送前确认 `main` 领先提交数，一并推送全部（含 09-13 文档批次与系统功能增强批次）。

---

## 附录：2026-09-13 文档同步 + 隐私清理 + GitHub 推送轮次

### 执行范围

1. **全项目文档同步**（`docs: 全项目文档同步...`）：
   - README / QUICKSTART / OPTIMIZATION_REPORT 补 3.1/3.4/4.1/2.3/1.5 批次
     新模块说明（多候选补丁、成本感知路由、结构化追踪、RAG 默认开、CLI 边界），
     测试基线 1038→1085；QUICKSTART 增「7. 可选高级开关」节。
   - 去除论文/手稿措辞：README「论文与文档」章节删除 `paper.md` 链接与摘要、
     `docs/algorithm_design.md`「供论文撰写」改为「供技术评审」、
     `docs/failure_analysis.md` 与 README 实验数据区加「历史数据快照」标注。
   - 本地删除 `paper.md` 与 `.private/`（论文源码 LaTeX/大纲/实验报告，均已 .gitignore 排除，未进 git 树）。
2. **隐私与论文内容全量排查**（敏感信息扫描脚本）：
   - 全部被跟踪的 md/py/json/sh 文件无真实密钥落盘（命中均为测试 fixture 合成占位符）；
   - 本地真实密钥仅存于 gitignored 的 `.env` / `src/.env.local`（建议轮换，跨轮次保留建议）。
3. **git 历史清理**（`git filter-repo`）：
   - 移除 `paper.md` / `docs/paper/`（8 章 LaTeX + 摘要）/ `TASK_SUMMARY.md` /
     `FINAL_PAPER_STATUS.md` / `PAPER_IMPROVEMENT_PLAN.md` /
     `algorithm_paper.md` / `docs/paper_outline.md` / `.agent-teams/` /
     `SUBMISSION_CHECKLIST.md` / `SUBMISSION_PACKAGE.md` /
     `quality_review_report_20260817.md` 全部历史版本；
   - 重写 263 个提交，SHA 全部变化（原 `5ca09a7` → 新 `f6ac74d`），
     `--force` 推送到 `origin/main`。

### 验证

| 检查项 | 结果 |
|--------|------|
| 全量测试 | ✅ 1085 passed / 0 failed（推送前最后回归） |
| 远端与本地一致 | ✅ `git ls-remote origin main` = `f6ac74d` |
| 远端历史无 paper/隐私残留 | ✅ `git log --all -- paper.md docs/paper TASK_SUMMARY.md` 空 |
| 工作区 | ✅ clean |

---

## 附录：2026-09-14 状态细化 + 可配阈值 + 边界补测 + 源码导出 + 脱敏审计轮次

### 执行范围

本批次消化 2026-09-14 改进清单中的 7 项纯代码项（1.1 / 1.4 / 1.5 / 2.1 / 2.3 / 3.2 / 4.1）：

| 项 | 内容 | 改动文件 | 状态 |
|----|------|----------|------|
| 1.1 | 错误分类补 2 个状态细化类（PATCH_VALIDATION_FAILED / RAG_RETRIEVAL_EMPTY），`refine_failure_category()` 任务收尾判定（补丁被拒优先于 RAG 空） | `src/agents/error_classifier.py` + `src/reports/generator.py` + `experiments/run_benchmark.py` + `src/cli/app.py` + 测试 | ✅ |
| 3.2 | 成本告警阈值可配（`APIManagerConfig.cost_alert_threshold`，默认 2.0），告警文案打印配置值 | `src/api/api_manager.py` + 测试 | ✅ |
| 1.5 | 熔断冷却期 3 条边界测试（到期回归 / 多节点同时冷却降级 / 冷却期内快速失败） | `tests/test_api_manager.py`（`TestCircuitCooldownBoundaries` 3 用例） | ✅ |
| 1.4 | CLI 参数异常路径与并发行为补测（--timeout 贯通 / 无效 dataset 降级 / 并发单任务超时不阻塞整批 / glob 边界语义） | `tests/test_cli_app.py`（3 组 8 用例） | ✅ |
| 2.1 | SWE-bench 源码导出自动化（`scripts/export_swe_bench_source.py`：patch 提取首个非测试目标文件 + `git show` 只读导出 + enrichment JSONL 输出 + `--instance-ids`/`--dry-run`）；`SWEBenchDataset.tasks_missing_source()` + check-dataset 输出缺失 instance_id 列表 | `scripts/export_swe_bench_source.py`（新）+ `src/datasets/dataset_loader.py` + `src/cli/app.py` + 测试 | ✅ |
| 2.3 | RAG 指标自动汇总（analyze_results.py 新增按检索类型分解 + RAG 命中 × 失败类别交叉表） | `experiments/analyze_results.py` + 测试 | ✅ |
| 4.1 | 脱敏完整审计（`docs/redaction_audit.md`）：修复 2 个真实盲点（APIManager 7 处日志点就地 `_redact()` + `get_status()` base_url 出口脱敏），LLM 文件缓存记录为已知可接受风险（脱敏与缓存精确命中互斥） | `src/api/api_manager.py` + `docs/redaction_audit.md`（新）+ 测试 | ✅ |

### 全量验证结果

| 检查项 | 结果 |
|--------|------|
| 全量测试 | ✅ **1158 passed** / 0 failed（2 warning 为 scipy 退化数据精度告警，非代码问题） |
| 新增用例 | +41（错误分类 9 + 成本路由 4 + APIManager 5 + CLI 8 + 源码导出 11 + 数据集 2 + 实验脚本 4 + 脱敏回归 2，其中 1.5/1.4 与既有套件叠加后净增量以全量数为准） |

### 设计决策

- **1.1 状态细化类不走文本正则**：`classify()` 保持 10 类纯文本分类不变；`PATCH_VALIDATION_FAILED` / `RAG_RETRIEVAL_EMPTY` 是流程状态类，由 `refine_failure_category()` 在任务收尾按 `repair_history` / `rag_stats` 信号判定，仅在失败任务上生效（成功任务原样返回），benchmark 与 CLI 两个出口口径一致。
- **优先级：补丁被拒 > RAG 检索空**：前者是"修复未生效"的更具体根因；RAG 空是"检索未提供帮助"。两者同时成立时归 patch_validation_failed。
- **3.2 默认值不变**：`cost_alert_threshold` 默认沿用模块常量 2.0，不改变既有告警行为；调优为显式配置行为。
- **4.1 LLM 缓存不脱敏**：`base_agent` 文件缓存靠 `prompt == user_message` 精确匹配命中，脱敏落盘值会破坏读侧匹配（缓存永不命中）。缓存目录（代码实际为 `src/cache/`，`AITESTER_LLM_CACHE_DIR` 可覆盖；已入 `.gitignore`，不进 git、不上传）记录为本地可信域已知可接受风险，后续可选"脱敏+双字段"方案单独立项。（注：此前本附录与 redaction_audit 误记为 `~/.cache/aitester/llm_cache/`，2026-09-14 F 批次已按代码更正）

---

## 附录：2026-09-14 批次②收尾轮次（文档数据对齐）

### 执行范围

批次②（7 项纯代码项）的文档收尾，用户确认「全部执行 + 推送 main」：

| 项 | 内容 | 改动文件 | 状态 |
|----|------|----------|------|
| O-01 | README 测试覆盖模块主表 9 行用例数与实测 `def test_` 计数漂移同步（test_api_manager 80→77、test_cli_app 30→27、test_cost_aware_routing 14→13、test_dataset_validation 20→22、test_experiments_scripts 23→19、test_swe_bench_source_export 11→13、test_core_modules 29→19、test_executor_sandbox 14→7、test_dataset_loader_extended 73→59） | `README.md` | ✅ |
| O-02 | README「当前 1111 个用例」→ 1158（与状态表/全量实测一致） | `README.md` | ✅ |
| O-03 | docs/api_reference.md 错误分类「十类」→「十二类」：枚举表补 patch_validation_failed / rag_retrieval_empty 两行（1.1 状态细化）+ 优先级说明补 refine_failure_category 判定口径 | `docs/api_reference.md` | ✅ |
| O-04 | docs/failure_analysis.md 状态说明「扩展为 10 类」→ 12 类（注明批次②补 2 状态细化类） | `docs/failure_analysis.md` | ✅ |
| O-05 | QUICKSTART.md「高级开关」节补 3.2 成本告警阈值可配（APIManagerConfig.cost_alert_threshold，默认 2.0） | `QUICKSTART.md` | ✅ |
| O-06 | CHANGELOG 顶部 Unreleased 批次②条目补「文档对齐（批次②收尾）」小节 | `CHANGELOG.md` | ✅ |

### 检索结论（无优化点的维度）

- 源码无 eval/exec/os.system 危险调用（复核，与历史轮次一致）；
- 被跟踪文件无真实密钥残留（`git ls-files` 仅 .env.example / .env.local.template 占位符模板，.env.local / .env 已 gitignore；本地 .env 真实密钥建议轮换——跨轮次保留建议）；
- CI 结构完整（矩阵 3.12/3.14、lock 校验、ruff 固定 0.16.3、pip-audit 5 条 PYSEC 豁免、测试失败诊断注解），无漂移；
- 全量 1158 passed / 0 failed、ruff check 全绿、覆盖率 TOTAL 91%（3911/354 miss，src 行增长系批次②新增模块所致）。

### 实施记录

| 提交 | 内容 |
|------|------|
| `6a423fe` docs | O-01~O-05 文档数据对齐（主表 9 行 + 用例数 + 枚举表 + 优先级说明 + 状态说明 + QUICKSTART） |
| （本提交） docs(optimize) | O-06 CHANGELOG 条目 + OPTIMIZATION_PLAN/REPORT 批次②收尾章节 |

（纯文档改动，未触碰源码；最小验证为 ruff check + 受影响模块测试子集（test_error_classifier 85 收集 / test_cost_aware_routing 13）全绿。）

---

## 附录：2026-09-14 全项目文档同步轮次（F 批次）

### 执行范围

用户指令"更新所有文档到最新并上传 GitHub"，在 O 批次（数据对齐）之上再做一轮**全项目**文档与代码现状核对，共 10 项（F-01~F-10）：

| 项 | 内容 | 改动文件 | 状态 |
|----|------|----------|------|
| F-01 | README 项目结构树补齐 4 处缺失（src/observability/、src/graph/token_usage.py、src/tools/ 3 个、experiments/ 4 个脚本） | `README.md` | ✅ |
| F-02 | redaction_audit C 项 LLM 缓存路径更正：`~/.cache/aitester/llm_cache/`（HOME）→ `src/cache/`（仓库内 + gitignore），信任级论述对齐代码实际 | `docs/redaction_audit.md` + `OPTIMIZATION_REPORT.md`（4.1 决策条目同处误记一并更正） | ✅ |
| F-03 | performance_guide 的 `rm -rf .chroma_cache/` 指向不存在目录（chromadb 1.x 持久化在 rag_data/） | `docs/performance_guide.md` | ✅ |
| F-04 | "供论文讨论章节"措辞残留 2 处（09-13 隐私清理轮次漏改）：README 结构树 + analyze_failures.py docstring；后者 `--output` 默认值 `docs/paper/` → `experiments/results/`（目录已不存在，无测试引用该脚本） | `README.md` + `experiments/analyze_failures.py` | ✅ |
| F-05 | README 5.3 成本感知路由补 3.2 阈值可配口径（默认 2.0 + 调优方向 + 0.0=无信息回退 1.0） | `README.md` | ✅ |
| F-06 | README 新增 5.7 SWE-bench 源码导出自动化小节（脚本用法 + check-dataset 联动） | `README.md` | ✅ |
| F-07 | api_reference 版本历史补 Unreleased（批次②）行（0.9.13 行保留为历史记录） | `docs/api_reference.md` | ✅ |
| F-08 | .env.example 3.4 节注释补 3.2 阈值可配 + LLM_N_COST_WEIGHT 数值口径对齐 config.py（0.1~1000，未配置默认 0.0 非 1.0） | `.env.example` | ✅ |
| F-09 | performance_guide（2026-08-16）/ usage_examples（2026-09-11）时间戳同步 2026-09-14 | 两文件 | ✅ |
| F-10 | usage_examples 引用小写 `contributing.md`（docs/ 下不存在）→ `../CONTRIBUTING.md` | `docs/usage_examples.md` | ✅ |

### 检索结论（无优化点的维度）

- `.env.example` / `config.local.example` 占位符无真实密钥（模板口径与 config.py 实际解析核对一致）；
- QUICKSTART 各步骤与 CLI 实际参数核对无漂移；docs/algorithm_design.md 为算法叙事（"供技术评审"口径），与代码无数据漂移；
- failure_analysis.md 为历史快照且 09-14 状态说明已注明"以 analyze_results.py 输出为准"，按设计保留原文；
- 全项目 `grep` 漂移复查（缓存路径 / chroma_cache / 十类 / 论文措辞 / 1111 用例 / 小写引用）全部清零。

### 全量验证结果

| 检查项 | 结果 |
|--------|------|
| 全量测试 | ✅ **1158 passed / 0 failed**（2 warning 为 scipy 退化数据精度告警，非代码问题） |
| Lint / 格式化 | ✅ `ruff check` All checks passed + `ruff format --check` 134 files already formatted |
| 敏感信息 | ✅ 被跟踪文件无真实密钥；.env / .env.local / src/cache/ / dist / build 均 gitignore |

### 设计决策

- **F-02 缓存路径**：redaction_audit C 项"已知可接受风险"结论不变（本地可信域、脱敏与缓存命中互斥），仅路径与信任级论述对齐代码实际（`src/cache/` 在仓库内且已 gitignore）；
- **F-04 默认输出路径**：`analyze_failures.py --output` 默认值改为 `experiments/results/failure_analysis.md`（无测试引用该脚本，零回归面）；
- **阶段 6 推送**：用户指令"上传 GitHub"，沿用历史轮次 main 直推（无 feature 分支、无 PR）。
