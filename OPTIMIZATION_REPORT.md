# AITester 项目优化报告

> 本报告为 2026-09-11 优化轮次的完整交付记录。阶段 0 基线与阶段 1 优化点清单
> 详见 `OPTIMIZATION_PLAN.md`；阶段 3-5 已在同一轮内完成，阶段 6 推送与 PR 待用户最终确认。

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

用户已确认「推送 main 并创建 PR」。实际执行结果：**推送受阻于网络**——本机到 `github.com:443` 不可达（curl 8s 超时、git push 两次失败 `Couldn't connect to server`），且本机未运行任何代理（clash/proxyman 均不在进程列表）。工作区与 commit 状态完好，可随时重推。

将推送内容：`origin/main` 落后的全部 **16 个 commit**（`bd4de49`…`1c4897a`，完整清单见 `git log origin/main..main --oneline`）。

手动执行命令（恢复网络/代理后）：

```bash
cd /Users/wangchenyu/workspace/AITester
# 1. 推送 main
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
EOF
```

> 若 `gh` 不可用：浏览器打开 `https://github.com/1956178912/AITester/compare/main...main`（推送后自动出现 compare 链接）→ Create new pull request，正文用上面 `## 背景` 到 `## 检查清单` 的内容。

## 阶段 7：最终报告

### 完成状态
- 阶段 0-5：**全部完成**，工作区 clean，本地 main 领先 origin/main 16 个 commit
- 阶段 6：**受阻于网络**（github.com:443 不可达、本机无代理），16 个 commit 已就绪、未推送；手动命令与 PR 正文见上节，恢复网络后 `git push origin main` 即完成

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
1. 恢复网络后执行阶段 6 手动命令推送 16 个 commit 并开 PR（正文已备好）
2. 轮换本地 .env 中的 LLM API Key（已在会话中暴露过一次，零容忍原则下建议更换）
3. T-01 公共 fixture 下沉（测试可维护性）与 T-04 executor 沙箱深度审计（需设计文档）排入下一迭代
4. chromadb 修复版发布后升级并移除 ci.yml 对应 `--ignore-vuln`（PYSEC-2026-3813/3814/3815）
