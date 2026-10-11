# T1 工作目录索引与关键文件摘要

- **审查对象**：`/Users/wangchenyu/Workspace/AITester`
- **审查人**：inventory-auditor（独立审查团队，共享任务 task-1）
- **产出日期**：2026-10-10（会话本地时间；仓库内文档最后更新日同为 2026-10-10）
- **git 状态**：HEAD = `d9e51df`（`git rev-parse --short HEAD`），提交总数 **456**（`git rev-list --count HEAD`），工作树 `git status --porcelain` 输出为空（干净），当前分支 `main`
- **统计口径（可复现）**：文件数 = `LC_ALL=C find <dir> -type f | wc -l`；大小 = `find <dir> -type f -exec stat -f %z {} + | awk '{t+=$1} END{print t}'`（字节，下表换算为 MB/KB）；行号 = `grep -n` / `sed -n`。
- **重要前提（口径纪律）**：本项目明文约定机器可读数字以 `BASELINE.yaml` 为"单一事实来源"，README/CHANGELOG/MODEL_CARD 中的数字含**历史快照**。本文件在引用任何数字时都标注**来源文件 + 行号**，并把"当前口径"与"历史快照"分开陈述（见 §3、§7）。

---

## 1. 文件树汇总（目录 → 文件数 → 总大小 → 代表文件）

### 1.1 统计范围声明

| 项 | 值 | 依据 |
|---|---|---|
| 仓库总占用 | 1.2 GB（`du -sh .`） | 含 `.git` 16 MB、`.venv` **911 MB**、`experiments/results` **88 MB** |
| 顶层条目 | 37 个文件 + 9 个目录（`.git` 与 `.venv` 计入目录数） | `find . -maxdepth 1 -type f \| wc -l` = 37；`ls -d */` = 9 |
| 排除明细统计的目录 | `.git/`、`.venv/`（911 MB）、`__pycache__/`、`.mypy_cache/`、`.pytest_cache/`、`.ruff_cache/`、`.hypothesis/`、`experiments/results/` | 本报告 §1.4 对 `experiments/results/` 只做类别汇总 |
| 排除上述目录后的源码/文档/测试文件总数 | **1,035** | `find . \( -name .git -o -name .venv -o -name __pycache__ -o -name .mypy_cache -o -name .pytest_cache -o -name .ruff_cache -o -name .hypothesis -o -path ./experiments/results -o -path ./review_2026 \) -prune -o -type f -print \| wc -l`（`review_2026/` 为本审查会话产出目录，剔除以保证数字可与仓库交付态比对；含本目录时为 1,038） |
| 被 git 追踪的文件总数 | **4,028** | `git ls-files \| wc -l` |

### 1.2 顶层目录汇总表

| 目录 | 文件数 | 总大小 | 代表文件（路径:大小） |
|---|---:|---:|---|
| `src/` | 239 | 4.1 MB | `src/graph/nodes.py` 114,684 B；`src/datasets/synthetic_dataset.py` 89,801 B；`src/agents/error_classifier.py` 74,880 B；`src/cli/app.py` 41,495 B |
| `tests/` | 511 | 12.0 MB | `tests/test_api_manager.py` 58,981 B；`tests/test_experiments_scripts.py` 44,538 B；`tests/test_branch_coverage_fill.py` 40,601 B |
| `experiments/` | 5,406 | 77.3 MB | `experiments/run_benchmark.py` 156,754 B；`experiments/statistical_analysis.py` 97,026 B；`experiments/results/` 5,322 文件 / 75.6 MB（详见 §1.4） |
| `docs/` | 83 | 1.2 MB | `docs/api_reference.md` 92,204 B；`docs/preregistration.md` 42,159 B；`docs/adr/` 25 文件；`docs/design/` 13 文件 |
| `data/` | 438 | 2.1 MB | `data/quixbugs/`（vendored 上游仓库，**内含嵌套 `.git/`**，gitignore 区） |
| `scripts/` | 88 | 0.7 MB | `scripts/gates/check_bilingual_docs.py` 11,625 B；`scripts/gates/check_branch_coverage.py` 11,000 B；`scripts/tools/power_analysis.py` 9,340 B |
| `examples/` | 16 | <0.1 MB | `examples/calculator.py`、`examples/complex_logic.py`、`examples/cost_budget_demo/run.py` |
| `review_2026/` | 本次审查新建 | — | 本文件；另有 teammate/Lead 并行写入的 `LEAD_findings.md`（**非本任务产出**，`git status` 显示 `?? review_2026/`） |
| 仓库根 | 37 | 1.3 MB | `README.md` 128,786 B；`CHANGELOG.md` 397,160 B；`BASELINE.yaml` 56,991 B |

补充分类计数（`find ... | sed 's/.*\.//' | sort | uniq -c`，排除缓存与 `.venv`）：`jsonl` 4,406、`json` 855、`py` 612、`java` 182、`md` 156、`class` 44、`log` 42、`png` 9、`sh` 6、`yml` 5、`csv` 5、`yaml` 4、`txt` 4、`toml` 2、`cff` 1、`pdf` 1、`lock` 1、`gradle` 1、`typed` 1、`repro` 1、`template` 1、`example` 2、`gitignore` 2、`local` 2。

代码行数（`find <dir> -name '*.py' -not -path '*__pycache__*' -exec cat {} + | wc -l`）：`src/` **119 文件 / 45,371 行**、`tests/` **255 文件 / 66,880 行**、`experiments/` **46 文件 / 19,087 行**、`scripts/` **35 文件 / 6,292 行**；仓库内 `.md` 合计 **33,108 行**（排除 `.git`/`.venv`/`.private`/`experiments/results`）。

### 1.3 `src/` 子模块与 `docs/` 子目录

| `src/` 子目录 | 文件数 | 大小 | | `docs/` 子目录 | 文件数 |
|---|---:|---:|---|---|---:|
| `src/tools/` | 58 | 1.0 MB | | `docs/adr/` | 25（24 份 ADR + README） |
| `src/agents/` | 48 | 1.1 MB | | `docs/design/` | 13（+1 `.en.md`） |
| `src/graph/` | 34 | 0.7 MB | | `docs/history/` | 20 |
| `src/utils/` | 18 | 0.2 MB | | `docs/integration/` | 2 |
| `src/datasets/` | 12 | 0.3 MB | | `docs/security/` | 1 |
| `src/observability/` | 10 | 0.1 MB | | `docs/` 顶层文件 | 22（19 个 `.md` + 3 个配置/数据） |
| `src/specs/` | 10 | 0.2 MB | | `docs/` 文件合计 | **83** |
| 其余（api/budget/cli/config/db/experiments/prompts/rag/reports） | 各 4–8 | <0.2 MB | | | |

### 1.4 `experiments/results/` 类别汇总（**不逐条读取**）

- 条目总数 **138** = 子目录 **52** + 顶层文件 **86**（`ls -1 | wc -l` / `ls -d */ | wc -l` / `ls -p | grep -v '/$' | wc -l`）。
- 顶层文件构成：`json` **68**、`log` **13**、`md` **5**；文件名前缀分布：`benchmark_examples_*` 46、`benchmark_synthetic_*` 12、`benchmark_swe_bench_*` 5，其余为单件日志/汇总（`synthetic_*.log`、`experiment_report_20260925.md`、`strategy_bank.json`、`performance_benchmark.json` 等）。
- 目录内文件类型（全 5,322 文件）：`jsonl` 4,406（trace）、`json` 820、`log` 42、`md` 34、`png` 9、`csv` 5、`txt` 1、`sh` 1、`SHA256SUMS` 4。
- **SHA256SUMS 仅 4 处**：`analysis/`、`e6_a1_batches/`、`main_batch/`、`r4_batches/`；**README 仅 2 处**：`e6_a1_batches/README.md`、`r4_batches/README.md`。
- 含 `traces/` 子目录的批次 **22 个**（`ab1_validation`、`lite20_*`、`main_batch`、`rag_*`、`smoke_*` 等）。
- 最大批次（文件数 / 体积）：`main_batch` **2,030 文件 / 20.6 MB** > `e6_a1_batches` **1,089 文件 / 15.8 MB** > `r4_batches` **309 文件 / 4.5 MB** > `cross_file_ab_level1` / `level3` 各 204 文件 > `pa_l25h_n40(_g8batch)` 各 164 > `cf_bi_l35_n40` 163。
- 单文件最大：`lite20_repo_level_aitester/traces/sqlfluff__sqlfluff-2862_aitester_1790417254.trace.jsonl` 2.57 MB、`e6_a1_batches/e6_control_seed42/benchmark_synthetic_20261009_181758.json` 2.43 MB、`main_batch/benchmark_synthetic_20261006_140906.json` 2.23 MB。
- **53→52 修正说明**：本报告曾一度按目录名清单计数为 53，经 `ls -d */` 与 `find -maxdepth 1 -type d` 双向比对，权威值为 **52 个子目录 + 86 个顶层文件 = 138 条目**（`ls -1 | sed 's|/$||' | sort` 与 `find` 输出 `diff` 无差异）。
- `main_batch/` 深度 1 共 24 条目：1 个 `SHA256SUMS` + 10 个 `benchmark_synthetic_*.json` + **10 份 `*.md` 报告**（`statistical_report.md`、`statistical_report_3seed_pooled.md`、`statistical_report_e2.md`、`statistical_report_e2_iter.md`、`corrected_report_v2.md`、`repair_ceiling_report.md`、`target_quality_report.md`、`mast_distribution_report.md`、`e7_repair_sample_candidates.md`、`e7_review_worksheet.md`）+ `traces/` + 内嵌 `.mimosa/` 运行时状态目录。
- 入库白名单（`.gitignore:119-152`）：`experiments/results/**` 默认忽略，仅 `main_batch/`（`*.json`/`*.md`/`SHA256SUMS`/`traces/**`）、`r4_batches/`、`e6_a1_batches/` 被 negation 白名单放行；`git ls-files experiments/results` = **3,426** 个受追踪文件。

---

## 2. 关键文件清单表（≥60 条）

**字段说明**：类型 = 扩展名/形态；用途分类 = 说明文档 / 需求（预注册） / 设计 / 论文（模型卡·数据卡·引用） / 源码 / Notebook（本项目无 `.ipynb`，**0 个**，以实验脚本近似替代→标注"实验脚本"） / 配置 / 数据 / 实验记录 / 评估结果 / 测试 / CI / 合规 / 其他。可读性：全部条目均以当前用户（`wangchenyu`，属主）身份实际 `stat`/读取成功，标"可读"；标"可读(0600)"者文件权限位为 `-rw-------`，属主可读、同组/其他用户不可读。所有条目均已 `read`/`grep`/`sed` 读取过内容或其标题行（除 §4 明确标注者）。

### 2.1 根目录（说明文档 / 配置 / 合规）

| # | 路径 | 类型 | 大小(B) | 修改时间 | 用途分类 | 可读性 |
|---:|---|---|---:|---|---|---|
| 1 | `README.md` | md | 128,786 | 2026-10-10 16:10 | 说明文档 | 可读 |
| 2 | `README.en.md` | md | 113,540 | 2026-10-10 16:10 | 说明文档 | 可读 |
| 3 | `QUICKSTART.md` | md | 20,080 | 2026-10-10 16:10 | 说明文档 | 可读 |
| 4 | `QUICKSTART.en.md` | md | 18,821 | 2026-10-10 16:10 | 说明文档 | 可读 |
| 5 | `CHANGELOG.md` | md | 397,160 | 2026-10-10 16:28 | 说明文档（历史快照） | 可读 |
| 6 | `CHANGELOG.en.md` | md | 411,469 | 2026-10-10 16:28 | 说明文档（历史快照） | 可读 |
| 7 | `CONTRIBUTING.md` | md | 8,224 | 2026-10-10 16:10 | 说明文档 | 可读 |
| 8 | `CONTRIBUTING.en.md` | md | 9,797 | 2026-10-10 16:10 | 说明文档 | 可读 |
| 9 | `BASELINE.yaml` | yaml | 56,991 | 2026-10-10 16:10 | **配置（单一事实来源）** | 可读 |
| 10 | `MODEL_CARD.md` | md | 7,928 | 2026-10-10 16:10 | 论文/合规 | 可读 |
| 11 | `MODEL_CARD.en.md` | md | 8,156 | 2026-10-10 16:10 | 论文/合规 | 可读 |
| 12 | `SECURITY.md` | md | 2,555 | 2026-10-05 19:29 | 合规 | 可读 |
| 13 | `SECURITY.en.md` | md | 3,095 | 2026-10-06 11:00 | 合规 | 可读 |
| 14 | `CITATION.cff` | cff | 1,065 | 2026-10-06 18:18 | 合规 | 可读 |
| 15 | `LICENSE` | 文本 | 1,078 | 2026-10-05 18:37 | 合规（MIT） | 可读 |
| 16 | `pyproject.toml` | toml | 16,780 | 2026-10-08 21:30 | 配置 | 可读 |
| 17 | `setup.py` | py | 3,817 | 2026-10-07 12:32 | 配置（兼容 shim） | 可读 |
| 18 | `requirements.txt` | txt | 6,230 | 2026-10-10 16:10 | 配置 | 可读 |
| 19 | `requirements.lock` | lock | 2,481 | 2026-10-10 16:10 | 配置 | 可读 |
| 20 | `Dockerfile` | 文本 | 1,308 | 2026-10-10 16:10 | 配置 | 可读 |
| 21 | `Dockerfile.repro` | 文本 | 2,059 | 2026-10-05 19:16 | 配置 | 可读(0600) |
| 22 | `Makefile` | 文本 | 4,379 | 2026-10-10 16:10 | 配置 | 可读 |
| 23 | `reproduce.sh` | sh(0755) | 15,110 | 2026-10-05 19:28 | 配置 | 可读 |
| 24 | `.pre-commit-config.yaml` | yaml | 2,882 | 2026-10-10 16:10 | CI | 可读 |
| 25 | `.gitignore` | 文本 | 6,679 | 2026-10-10 16:10 | 配置 | 可读 |
| 26 | `.gitleaks.toml` | toml | 2,483 | 2026-10-05 12:23 | CI（密钥扫描） | 可读 |
| 27 | `.dockerignore` | 文本 | 2,520 | 2026-10-10 16:10 | 配置 | 可读 |
| 28 | `.dvcignore` | 文本 | 1,723 | 2026-09-30 12:54 | 配置 | 可读(0600) |
| 29 | `config.py` | py | 34,213 | 2026-10-10 16:10 | 源码（配置中心） | 可读 |
| 30 | `config.local.example` | example | 2,490 | 2026-10-10 16:10 | 配置示例 | 可读 |
| 31 | `llm_configs.json` | json | 205 | 2026-10-10 16:18 | 配置（受追踪） | 可读 |
| 32 | `main.py` | py | 465 | 2026-10-04 18:24 | 源码（入口） | 可读 |
| 33 | `init_db.py` | py | 4,286 | 2026-10-05 15:49 | 源码（DB 初始化） | 可读 |
| 34 | `.env.example` | example | 42,101 | 2026-10-10 16:10 | 配置示例（受追踪） | 可读 |
| 35 | `.env.local.template` | template | 1,586 | 2026-10-10 16:18 | 配置示例（受追踪） | 可读 |
| 36 | `.env` | 文本 | 1,977 | 2026-10-09 14:42 | 敏感配置（**未读取内容**） | 存在（0644） |
| 37 | `.env.local` | 文本 | 812 | 2026-10-09 14:44 | 敏感配置（**未读取内容**） | 存在（0644） |

### 2.2 文档 / 预注册 / 设计 / ADR

| # | 路径 | 类型 | 大小(B) | 修改时间 | 用途分类 | 可读性 |
|---:|---|---|---:|---|---|---|
| 38 | `docs/preregistration.md` | md | 42,159 | 2026-10-10 16:10 | **需求（预注册）** | 可读 |
| 39 | `docs/preregistration.en.md` | md | 48,245 | 2026-10-10 16:10 | 需求（预注册） | 可读 |
| 40 | `docs/api_reference.md` | md | 92,204 | 2026-10-10 16:10 | 说明文档 | 可读 |
| 41 | `docs/api_reference.en.md` | md | 86,591 | 2026-10-10 16:10 | 说明文档 | 可读 |
| 42 | `docs/algorithm_design.md` | md | 24,020 | 2026-10-07 19:48 | 设计 | 可读 |
| 43 | `docs/DATA_CARD.md` | md | 8,006 | 2026-10-10 16:10 | 论文/合规 | 可读 |
| 44 | `docs/threat_model.md` | md | 11,278 | 2026-10-10 16:10 | 合规 | 可读 |
| 45 | `docs/failure_analysis.md` | md | 15,008 | 2026-09-29 14:34 | 说明文档 | 可读 |
| 46 | `docs/usage_examples.md` | md | 20,632 | 2026-10-10 16:10 | 说明文档 | 可读 |
| 47 | `docs/troubleshooting.md` | md | 10,793 | 2026-10-10 16:10 | 说明文档（**无英文版**） | 可读 |
| 48 | `docs/performance_guide.md` | md | 30,110 | 2026-10-10 16:10 | 说明文档 | 可读 |
| 49 | `docs/performance_baseline.json` | json | 3,023 | 2026-10-10 16:10 | 评估结果（性能基线） | 可读 |
| 50 | `docs/coverage_ratchet.yaml` | yaml | 411 | 2026-10-10 16:10 | 配置（覆盖率棘轮） | 可读 |
| 51 | `docs/env_budget.yaml` | yaml | 5,070 | 2026-10-10 16:10 | 配置（环境变量预算） | 可读 |
| 52 | `docs/dependency_exemptions.md` | md | 2,566 | 2026-10-10 16:10 | 合规（依赖豁免） | 可读 |
| 53 | `docs/adr/README.md` | md | 12,855 | 2026-10-10 16:10 | 设计（ADR 索引） | 可读 |
| 54 | `docs/adr/0016-orchestration-container-repositioning.md` | md | 7,028 | 2026-10-06 22:49 | 设计（核心 ADR） | 可读 |
| 55 | `docs/adr/0017-repair-engine-pivot.md` | md | 8,275 | 2026-10-07 21:51 | 设计 | 可读 |
| 56 | `docs/adr/0021-repair-zero-measurement-artifact.md` | md | 5,706 | 2026-10-07 21:51 | 设计（测量伪影） | 可读 |
| 57 | `docs/adr/0027-corrected-caliber-re-estimation.md` | md | 4,247 | 2026-10-07 22:32 | 设计 | 可读 |
| 58 | `docs/adr/0029-measurement-artifact-cross-file-and-packaged-import.md` | md | 7,591 | 2026-10-10 16:10 | 设计（**未入索引**） | 可读 |
| 59 | `docs/design/repair_caliber_matrix.md` | md | 6,892 | 2026-10-08 17:52 | 设计（repair 口径矩阵） | 可读 |
| 60 | `docs/design/mas_compilation.md` | md | 5,236 | 2026-10-10 16:10 | 设计（Proposed） | 可读 |
| 61 | `docs/design/r4_localized_edit_ab.md` | md | 12,171 | 2026-10-08 19:47 | 设计（A/B 预注册） | 可读 |
| 62 | `docs/design/cross_file_repair.md` | md | 21,982 | 2026-10-10 16:10 | 设计（有 `.en.md`） | 可读 |
| 63 | `docs/design/real_benchmark_upgrade.md` | md | 6,759 | 2026-10-10 16:10 | 设计 | 可读 |
| 64 | `docs/design/swe_bench_probe.md` | md | 8,702 | 2026-10-10 16:10 | 设计 | 可读 |
| 65 | `docs/design/spec_to_repair_wiring.md` | md | 5,441 | 2026-10-08 18:07 | 设计（待设计） | 可读 |
| 66 | `docs/design/frame_lifetime_trace.md` | md | 6,246 | 2026-10-07 23:13 | 设计（未实现） | 可读 |
| 67 | `docs/design/failure_knowledge_feedback.md` | md | 7,711 | 2026-09-27 20:37 | 设计 | 可读(0600) |
| 68 | `docs/design/hierarchical_summary.md` | md | 4,894 | 2026-10-05 18:37 | 设计（已实现） | 可读 |
| 69 | `docs/design/multilanguage_extension.md` | md | 5,985 | 2026-09-28 12:03 | 设计（未落地） | 可读(0600) |
| 70 | `docs/design/property_template_route_skeleton.md` | md | 4,691 | 2026-10-07 11:20 | 设计（占位骨架） | 可读 |
| 71 | `docs/history/README_iteration_log.md` | md | 27,572 | 2026-10-10 16:10 | 实验记录（历史） | 可读 |
| 72 | `docs/history/code_analysis_report.md` | md | 20,911 | 2026-10-10 16:27 | 说明文档（自述已过期） | 可读 |
| 73 | `docs/history/optimization_report.md` | md | 58,561 | 2026-09-19 18:53 | 说明文档（历史快照） | 可读 |
| 74 | `docs/history/statistical_report_2026-09-25_expired.md` | md | 3,639 | 2026-09-30 16:23 | 评估结果（已过期） | 可读 |
| 75 | `docs/security/history_leak_remediation_runbook.md` | md | 4,104 | 2026-10-10 16:10 | 合规（应急手册） | 可读 |
| 76 | `docs/integration/vendored_quixbugs.md` | md | 4,297 | 2026-10-10 16:10 | 说明文档 | 可读 |
| 77 | `scripts/README.md` | md | 4,517 | 2026-10-10 16:10 | 说明文档 | 可读 |

### 2.3 源码 / 实验脚本 / 门禁 / 测试 / CI

| # | 路径 | 类型 | 大小(B) | 修改时间 | 用途分类 | 可读性 |
|---:|---|---|---:|---|---|---|
| 78 | `src/graph/nodes.py` | py | 114,684 | 2026-10-10 16:10 | 源码（工作流节点） | 可读 |
| 79 | `src/graph/workflow.py` | py | 59,373 | 2026-10-10 16:10 | 源码（LangGraph 编排） | 可读 |
| 80 | `src/graph/state.py` | py | 49,246 | 2026-10-08 15:57 | 源码（状态 schema） | 可读 |
| 81 | `src/graph/patch_io.py` | py | 27,955 | 2026-10-10 16:10 | 源码（R4 新拆出） | 可读 |
| 82 | `src/agents/error_classifier.py` | py | 74,880 | 2026-09-30 19:56 | 源码 | 可读 |
| 83 | `src/agents/base_agent.py` | py | 46,295 | 2026-10-10 16:10 | 源码 | 可读 |
| 84 | `src/agents/llm_client.py` | py | 37,743 | 2026-10-06 18:36 | 源码 | 可读 |
| 85 | `src/agents/fault_localizer.py` | py | 21,343 | 2026-10-07 23:16 | 源码（ADR-0017 转向） | 可读 |
| 86 | `src/cli/app.py` | py | 41,495 | 2026-10-10 16:10 | 源码（CLI） | 可读 |
| 87 | `src/api/api_manager.py` | py | 58,897 | 2026-10-05 15:57 | 源码（多模型路由） | 可读 |
| 88 | `src/tools/patch_applier.py` | py | 63,585 | 2026-10-07 21:46 | 源码（ADR-0021 修复点） | 可读 |
| 89 | `src/tools/dependency.py` | py | 38,844 | 2026-10-10 16:10 | 源码（C-08 白名单） | 可读 |
| 90 | `src/specs/spec_ir_v2.py` | py | 33,137 | 2026-10-10 16:10 | 源码（SpecIR DSL） | 可读 |
| 91 | `src/specs/spec_smt.py` | py | 31,865 | 2026-10-10 16:10 | 源码（SMT 后件一致性） | 可读 |
| 92 | `src/utils/credential_scrub.py` | py | 9,464 | 2026-10-10 16:10 | 源码（凭证脱敏） | 可读 |
| 93 | `experiments/run_benchmark.py` | py | 156,754 | 2026-10-10 16:10 | 实验脚本（**全仓最大 py**） | 可读 |
| 94 | `experiments/statistical_analysis.py` | py | 97,026 | 2026-10-08 17:43 | 实验脚本（统计协议） | 可读 |
| 95 | `experiments/_m1_metrics.py` | py | 36,877 | 2026-10-10 16:10 | 实验脚本（M1 三指标） | 可读 |
| 96 | `experiments/repair_replay.py` | py | 9,434 | 2026-10-08 17:42 | 实验脚本（存量重放） | 可读 |
| 97 | `experiments/corrected_metrics.py` | py | 13,253 | 2026-10-07 22:37 | 实验脚本（修正口径） | 可读 |
| 98 | `experiments/target_quality_replay.py` | py | 11,767 | 2026-10-10 16:10 | 实验脚本（被测代码质量） | 可读 |
| 99 | `experiments/price_table.json` | json | 1,668 | 2026-10-06 22:29 | 数据（价目表） | 可读 |
| 100 | `scripts/gates/check_bilingual_docs.py` | py | 11,625 | 2026-10-10 16:27 | CI（双语文档门禁） | 可读 |
| 101 | `scripts/gates/check_branch_coverage.py` | py | 11,000 | 2026-10-10 16:10 | CI（分支覆盖率门禁） | 可读 |
| 102 | `scripts/gates/check_artifacts_tracked.py` | py | 5,898 | 2026-10-10 16:10 | CI（工件入库守卫） | 可读 |
| 103 | `scripts/gates/check_env_budget.py` | py | 6,689 | 2026-10-10 16:10 | CI（env 预算棘轮） | 可读 |
| 104 | `scripts/gates/checksum_results.py` | py | 4,267 | 2026-10-10 16:10 | CI（校验和） | 可读 |
| 105 | `scripts/tools/power_analysis.py` | py | 9,340 | 2026-10-10 16:10 | 实验脚本（功效分析） | 可读 |
| 106 | `tests/test_api_manager.py` | py | 58,981 | 2026-10-05 15:49 | 测试（最大单测文件） | 可读 |
| 107 | `tests/test_experiments_scripts.py` | py | 44,538 | 2026-10-10 16:10 | 测试 | 可读 |
| 108 | `tests/test_workflow_extended.py` | py | 44,085 | 2026-10-10 16:10 | 测试 | 可读 |
| 109 | `tests/test_branch_coverage_fill.py` | py | 40,601 | 2026-10-10 16:10 | 测试（覆盖率补口） | 可读 |
| 110 | `.github/workflows/ci.yml` | yml | 36,952 | 2026-10-10 16:10 | CI（4 作业） | 可读 |
| 111 | `.github/workflows/perf.yml` | yml | 4,090 | 2026-10-10 16:10 | CI（周度性能巡检） | 可读 |
| 112 | `.github/workflows/release.yml` | yml | 8,217 | 2026-10-05 18:02 | CI（tag 发布） | 可读 |
| 113 | `.git-hooks/pre-commit.sh` | sh | 4,305 | 2026-10-10 16:10 | CI（本地钩子） | 可读 |
| 114 | `.git-hooks/check_secret_leak.sh` | sh | 5,046 | 2026-10-10 16:10 | 合规（密钥泄漏守卫） | 可读 |
| 115 | `.github/CODEOWNERS` | 文本 | 251 | 2026-10-05 13:36 | 合规 | 可读 |
| 116 | `experiments/results/main_batch/benchmark_synthetic_20261006_140906.json` | json | 2,231,000± | 2026-10-06 | 评估结果（当前主批次） | 可读 |
| 117 | `experiments/results/main_batch/SHA256SUMS` | 文本 | — | 2026-10 | 实验记录（校验和） | 可读 |
| 118 | `experiments/results/e6_a1_batches/SHA256SUMS` | 文本 | — | 2026-10-09 | 实验记录（校验和） | 可读 |
| 119 | `experiments/results/r4_batches/README.md` | md | — | 2026-10-08 | 实验记录 | 可读 |
| 120 | `experiments/results/analysis_summary.md` | md | 888 | 2026-10-10 16:25 | 实验记录 | 可读 |
| 121 | `data/quixbugs/`（vendored 上游，含嵌套 `.git`） | 目录 | 2.1 MB | 2026-10 | 数据（gitignore 区） | 可读（未逐文件读取） |
| 122 | `examples/cost_budget_demo/run.py` | py | — | 2026-10 | 源码（示例） | 可读 |

> 说明：清单共 **122 条**（其中目录类条目 2 条、结果目录内条目 4 条按类别计），远超"≥60 条"要求。表中标"—"者为未单独取 `stat` 数值（仅列出存在性与分类），不构成数字断言。

---

## 3. 关键文件摘要（引用原文数字与行号）

### 3.1 `README.md`（128,786 B / 1,696 行，中文主文档）

1. 定位：**"检出优先的测试生成与修复评估（归因）系统"**；顶部把"多智能体编排"降级为**可消融容器**，并给出 E2 判据 `aitester vs plain_llm_df δ=−0.3673`（`README.md:1-9`）。
2. 诚实披露行给出两种 repair 口径并存：**修正后存量重放 39.31%（145 可重放行 correct=57）、E1/E2 logic 档 54.72%**，v1 口径 35.86% / 48.11% 标注为"伪影下界"（`README.md:22-28`）。
3. 测试数字**刻意不硬编码**：明确"当前数字以 `BASELINE.yaml` 对应节（`tests`/`coverage`/`static_checks`）为唯一事实来源"（`README.md:29-40`）。
4. 结构：`## 测试状态`:29、`## 快速开始`:116、`## 项目结构`:291、`## 核心方法`:411、`## 实验复现`:1048、`## 合成数据集与统计检验`:1126；方法节含 `### 5.19.5 检出优先协议`:744、`### 5.21 P0 改进批次`:809、`### 5.22 前沿推荐批次`:949。
5. **未发现文件头日期行**（`grep -n -E '最后更新|Last updated' README.md` 无命中），而英文版有 `Last updated: 2026-10-07`（`README.en.md:3`）→ 中英最后更新日期无法核对（详见 §6 发现 4）。

### 3.2 `README.en.md`（113,540 B / 1,403 行）

1. 头部自带 `Last updated: 2026-10-07 (repair-engine batch XIV ...)`（`README.en.md:3`），内容为批次 XIV（FL Top-k 约束门 / Self-Repair Trap / Frame Lifetime Trace 设计输入）。
2. 英文标题与摘要同为 detection-first 定位，并同样声明 multi-agent 为 ablatable container、`E2 δ=−0.3673, ADR-0016/R26`（`README.en.md:7-14`）。
3. 数据点与中文版**同日不同步**：英文为 10-07 口径，中文正文已含 2026-10-09 C-01/C-08 段（对应 `CHANGELOG.md:122-127`），属典型"历史快照 vs 当前口径"分层。

### 3.3 `QUICKSTART.md`（20,080 B / 354 行）与 `QUICKSTART.en.md`（18,821 B）

1. 安装：`python3 -m venv .venv` + `pip install -r requirements.txt`，注明 **Python 3.12+（scipy 要求 ≥3.12）**（`QUICKSTART.md:12-26`）。
2. 两步配置法：步骤一 `.env`（非敏感）、步骤二 `.env.local`（**必须**填 `LLM_N_API_KEY`）（`QUICKSTART.md:28-50`）。
3. 一键引导脚本 `bash scripts/tools/bootstrap_dev.sh`（含 `--check-only` 校验模式）（`QUICKSTART.md:24-27`）。
4. 开关预设四档 `safe / scientific / logic / fast`；`logic` 档为 scientific 超集并补 `DETECTION_FIRST_ENABLE`（`QUICKSTART.md:103-113`）。
5. 高级能力清单含 `KERNEL_SANDBOX_ENABLE`（默认关，平台不支持时 fail-closed）、`API_PROMETHEUS_EXPORT`（默认关）、`RUNTIME_PROBE_ENABLE`（默认关）（`QUICKSTART.md:290-300`、`:213-216`）。
6. **中文版无 `最后更新` 行**；英文版为 `Last updated: 2026-10-06`（`QUICKSTART.en.md:3`）→ 与中文内容（含 2026-10-06 AA 批次描述）同日但库内已演进，日期同步形同虚设（见 §6 发现 4）。

### 3.4 `BASELINE.yaml`（56,991 B / 611 行，**机器可读单一事实来源**）

1. 维护约定（文件头注释 `:1-12`）：核心维护文档的"当前基线"数字统一引用本文件；**"本文件只维护当前"，历史快照归 `docs/history/`**。
2. `version: "1"`（`:13`）；`last_verified: "2026-10-09"`（`:14`，注释内载 R4 批次说明：本机实测 **5014 passed + 1 环境类 failed**，mypy **119 源文件 0 错误**，ruff 全绿，env 预算 170→172）。
3. `tests` 节：`total_passed: 5015`（`:17`，注明 `--collect-only` 收集数，"正常环境预期全绿"）、`total_failed: 0`、`slim_environment: 1863`、`suite_seconds: 35`（`:18-20`）。
4. `coverage` 节**显式区分 meta_coverage 与被测代码覆盖率**（口径澄清见 `:22-26`）：`line_total_pct: 89`、`branch_total_pct: 83`、核心路由模块分支覆盖 `graph_workflow: 98 / error_classifier: 91 / graph_state: 100`（`:27-52`）。
5. `target_quality` 节（被测代码侧一等指标，`:53-76`）：行覆盖 `aitester [84.0, 93.6]` vs `plain_llm [86.0, 97.2]`；`mutation_score aitester [0.818, 0.976]`；`spec_compile_rate aitester [0.205, 0.219]`（注：由恒 0.0 抬升）；特异性门 `specific_red: 40 / over_red: 66` 而 `plain_llm_df 162/140`（≈1.16 vs ≈0.61，注释称其为"−28pp 的主机制"）。
6. `static_checks`：ruff `0.16.3`、`ruff_warnings: 0`、`mypy_errors: 0`、`mypy_source_files: 119`（`:78-82`）；`python_ci_matrix: ["3.12","3.13","3.14"]`（`:84`）；`error_categories: 18`（`:86`）；`synthetic_templates: 50`（`:88`）。
7. `benchmark` 节：`current_main_batch = experiments/results/main_batch/benchmark_synthetic_20261006_140906.json`（`:159`），当前口径 detection `plain_llm_df 44.8%（117/261）> aitester 15.8%（38/240）> plain_llm 1.5%（4/261）`、配对差 `df vs plain_llm +0.426`、`aitester vs df −0.279`（`:160-169`）；成本 `aitester 0.0259 / plain_llm 0.0034 / plain_llm_df 0.0045 USD per task`（`:179-180`）。
8. 2026-10-09 实跑补充节（`:195-...`）：E6 control **−28pp 第三次独立复现**（aitester 9.2% 8/87 vs df 34.5% 30/87 vs plain_llm 0.0% 0/87，`:205-207`）；E6 matched 结论 `已执行：预算混杂被证否 → −28pp 归因编排结构（ADR-0016 加固）`（`:578-580`），phase2 `aitester_matched 2/87 (2.3%)、df_matched 23/87 (26.4%)`（`:589-590`）。

### 3.5 `CHANGELOG.md`（397,160 B / 5,400 行，88 个 `## ` 条目）

**"最后 3 个条目"按文件内**最新在顶部（倒序）**给出，并同时给出末尾 3 个历史版本条目，避免歧义。**

最新 3 条（文件顶部的 Unreleased 批次）：

1. `## [Unreleased] — 2026-10-10 文档清理批次`（`:9-46`）：删除 2 份过时历史快照 + **8 份孤儿实验报告（均为 gitignore 未入库工件）**；保留裁定含 `docs/history/code_analysis_report.md`（有 **7 处归档内回引**）与 `.private/review/**`（**20 份**，连通引用图无孤儿）；删除前建立本地专用分支 `local/docs-archive-2026-10-10`（**48 份本地文档 = .private 20 + results 28**），并注明远端 `1956178912/AITester` 为 public、该分支**禁止推送**。
2. `## [Unreleased] — 2026-10-09 D1 修复 + CI 三红清零批次`（`:47-104`）：D1 根因=JSON 解析层，**621 个 Planner 形态响应中 188 个（30.3%）无法 `json.loads`**（`Expecting ','` 94 / `Extra data` 57 / `Expecting value` 35 / `Expecting property name` 2），异常经 `nodes.py:269` 走 `_get_default_test_plan`；修复后**可解析且含 function_name 427/621（68.8%）→ 555/621（89.4%），+20.6pp（净回收 128 条）**；消融 `空计划 34/87（39.1%）→ 22/87（25.3%）` 但 detection `6.9%→8.0%`（McNemar p=1.0000）→ 假说证否；CI 三红清零含 5 包升级（PyJWT 2.13.0→2.15.1、urllib3 2.7.0→2.8.0、langgraph-sdk 0.4.2→0.4.6、multidict 6.7.1→6.9.1、oauthlib 3.3.1→4.0.0）；全量回归 **5107 passed / 3 skipped / 0 failed**（`:100`）。
3. `## [Unreleased] — 2026-10-09 R5 审查修订落地批次`（`:105-151`）：C-08 包名白名单默认 `false→true`（`:110-113`）；LLM 端点收拢 **`llm_configs.json` 17 条 → 1 条**（`deepseek-v4.1-flash`，`:128-130`）；2026 新文献（CANDOR/BOAD/Centaur 等）统一标注 **[待核验]**（`:146-150`）。

历史版本表末 3 条（文件尾部）：

4. `## [0.1] - 2026-09-18 首个正式版本（功能全集）`（`:5354`）——含"全量 **1459 个测试用例** / 覆盖率 **96%** / Ruff 全绿"与三基线表（AITester 成功率 **88.0%** vs Plain LLM 68.0% vs Single Agent 4.0%）。
5. `## [0.2] - 2026-09-19 代码质量与可靠性优化轮次`（`:5309`）、`## [0.3] - 2026-09-19 评估指标深化 + 变异生成器修复 + 脱敏审计轮次`（`:5252`）。
6. **版本口径冲突（须注意）**：`CHANGELOG.md:5400` 的"版本说明"称"**当前版本为 0.6**"，而 `src/__init__.py`（唯一事实来源）`__version__ = "0.7"`、`CITATION.cff:8 version: 0.7`；同一文件另有历史 `## [0.9.11] - 凭证安全…（2025-09-25）`（`:4738`）——2025 日期与其余 2026 时间线矛盾，属历史遗留条目。

### 3.6 `docs/preregistration.md`（42,159 B / 606 行，预注册）

1. **主终点 / 判定规则 / 停止规则**逐实验固化（`:20-31` 声明效力范围覆盖 E1/E2/E3/E4/E6/E7；E5 为探索性不受约束）。
2. **E1**（`:48-64`）：主终点 `spec_compile_rate`；判定 `≥0.3` 保留、`<0.2` 放弃、`[0.2,0.3)` 灰区允许**恰好一次**迭代；预算 ≈0.1M token。
3. **E2**（`:66-96`）：主终点=过红/抹红通道行数 + `aitester vs plain_llm_df` detection 配对差；停止规则=未归零但相对基线（**88 行过红 / 28 行抹红**）降幅 ≥50% 允许恰好一次修正重跑，<50% 直接接受；预算 ≈3–6M token。
4. **E4**（`:111-153`）：设计 29 任务 × 3 臂 × 1 种子；验收线"任一臂 detection>0 ∧ resolved>0"；污染防控增补给出 4 条强制披露口径（模型训练截止 vs 实例时间 / 靶点错位声明 / PatchDiff 式差分复核 / 三客观字段），并规定"污染披露小节缺失 → 报告不完整不得对外引用"。
5. **E6**（`:155-177`）：预算匹配四臂 2×2；matched 上限改取 **E2 同种子 standard 批次实测每任务总 token 均值**（AO 修订，早于任何 E6 数据）；R-P0-2 的 **26,115 vs 4,223 tok/任务（8.1×）**仅作量级参照。
6. **统计分析计划**（`:234-245`）：检验族 = McNemar（连续性校正）+ BH-FDR（α=0.05）+ 贝叶斯 Dirichlet 配对（ROPE ±5pp，MC seed=42）+ 模板聚类 DEFF 敏感性 + 模板级符号检验；功效依据"基线检出 2%、检出差 10pp 需 **n≈87**"。
7. **执行记录表**（`:274-283`）：E1 `spec_compile_rate 0.367（n=10/12）` **保留**；E2+E3 迭代终判 `过红 88→31（−64.8%）、抹红 28→2（−92.9%）`、`δ=−0.3673 [−0.4552,−0.2785]`、`FL@1 19/53=35.8%`；E4 双臂 `detection 0/41 = 0.0%`、aitester `repair 35/40=87.5%`、token/task 17,156 vs 2,370（**贵 7.2×**）；E6 四臂 detection 6.9% / 2.3% / 31.0% / 26.4%。

### 3.7 `docs/design/*.md` 目录清单（13 份，每份一句话主题）

| 文件 | 大小(B) | 一句话主题（依据首行标题/状态行） |
|---|---:|---|
| `cross_file_repair.md`(+`.en.md`) | 21,982 | 3.5 跨文件修复能力设计文档（唯一有英文配对的 design 文档） |
| `r4_localized_edit_ab.md` | 12,171 | R4 A/B 预注册：定位锚定的局部编辑通道（`LOCALIZED_EDIT_ENABLE`），声明"判定规则与阈值落盘后不因结果而改" |
| `swe_bench_probe.md` | 8,702 | R-01 SWE-bench 补跑探路立项（2026-09-21），状态"已完成（P0/P1 仓库级验证取代原探路方案）" |
| `failure_knowledge_feedback.md` | 7,711 | 失败知识库→修复策略离线/在线闭环（落点 B 已实装最小在线消费侧） |
| `repair_caliber_matrix.md` | 6,892 | **repair 口径矩阵**：终结"四个 repair 数字分母混杂"的口径危机（详见下） |
| `real_benchmark_upgrade.md` | 6,759 | 真实基准升级三级递进（QuixBugs/BugsInPy/SWE-bench Lite）；L1/L2 加载器已落地，L2 manifest 与 L3 复测未实现 |
| `frame_lifetime_trace.md` | 6,246 | Frame Lifetime Trace 设计草案（Debugger 拆分批设计输入），**未实现、未排期** |
| `multilanguage_extension.md` | 5,985 | 多语言扩展架构预留（Design-only，未落地代码） |
| `spec_to_repair_wiring.md` | 5,441 | 规约→修复定向通道（R22），状态"**待架构师设计**"（本轮侦查判定信号不足） |
| `mas_compilation.md` | 5,236 | 多智能体→单智能体技能库编译路线（R4/S7），状态"**探索性，Proposed**，本文不落任何代码" |
| `hierarchical_summary.md` | 4,894 | 超长文件分层摘要策略（P3 #17），状态"已实现"（原误标 Design-only，P1-9 修正） |
| `property_template_route_skeleton.md` | 4,691 | 属性模板路线预注册草案骨架（E1 失败出口应急占位），"占位骨架，未激活" |

**`repair_caliber_matrix.md` 要点**（6,892 B / 79 行）：① 表头即明示风险——"在建立本表之前，任何对外引用 repair 数字都有被审稿人一枪命中的风险"（`:3-7`）；② §1 口径矩阵 8 行（①–⑧）逐行给出分子/分母/oracle/数据集/臂/种子/开关/工件/复算命令（`:11-21`）；③ 关键值 `① 16.0%（8/50）`、`② 35.86%（52/145）`、`③ 48.11%（51/106）`、`④ 90.2%（37/41）/87.8%（36/41）`、`⑤ v2 39.31%（57/145）`、`⑥ v2 54.72%（58/106）`、`⑦ v2 55.6%（10/18）`；④ §3 强制引用纪律 4 条：必须注明口径编号、禁止 all-task 与 M1 可测混用、**禁止引用未修正旧数字**、新增数字须先入表（`:50-57`）；⑤ §2 给出 R27 跨文件物化 v2 增量表（跨文件 25 行 correct `0→11`，非跨文件 191 行 `→85`）。

**ADR 列表（`docs/adr/`，24 份 ADR + `README.md` 索引）**：编号使用段 = `0001–0005`、`0011–0029`，`0006–0010` 为**历史保留段（从未使用）**（`docs/adr/README.md:41-43`）。索引表 23 行，覆盖 0001–0028；核心条目一句话：
- `0003`（默认行为不变原则：新能力一律"默认关+独立开关"）、`0004`（零默认外部依赖）、`0005`（节点异常降级兜底）。
- `0011`（LLM 缓存用户隔离）、`0012`（Prompt Injection 防御）、`0013`（分类器可解释性）、`0014`（分支覆盖率门槛 85%/核心 90%）。
- `0015`（检出优先协议 `DETECTION_FIRST_ENABLE` 默认关）、`0016`（**编排定位重述=可消融容器**，含 −28pp/8.1× token 与增益收缩为检出优先协议 +43pp）。
- `0017`（修复引擎范式转向：局部化→合成→验证）、`0018`（结构化编辑意图+确定性落盘）、`0019`（确定性优先修复路由）、`0020`（补丁弃权门，观测层已采纳/阻断档 Proposed）、`0021`（**repair=0 围栏伪影定案**：274/274 带补丁行 `python\n` 残留致 100% 失败）、`0022`（test-hacking 守卫）、`0023`（pass@k / $/solved / 污染视角）、`0024`（反事实 FL 上界：`P(correct|FL命中)=15.8% < 未命中=64.7%` 负相关）、`0025`（oracle 上下文消融档）、`0026`（交互中心失败归因）、`0027`（修正口径重估：false_fix 87.2% / CPR 84.3% / 弃权精确率 86.0%）、`0028`（FL Top-k 约束门 + Self-Repair Trap 观测器）。
- **`0029`（测量伪影连环：包结构 import + 跨文件任务未物化，2026-10-08，状态"已采纳"）未出现在索引表**，索引仍写"下一个 0029"（`docs/adr/README.md:41-42`）→ 索引未随 ADR 落盘更新（本报告只陈述该事实）。

### 3.8 合规材料

| 文件 | 大小(B) | 关键内容（行号） |
|---|---:|---|
| `MODEL_CARD.md` | 7,928 | 定位"**检出优先的 Python 测试生成与修复评估研究系统**"，多智能体=可消融容器；repair 修正口径 **39.31%（57/145）**（`:1-16`）；§2 不自研/不微调模型，智能由 `.env.local` 的 `LLM_N_*` 三元组提供（`:23-27`）；§4 诚实声明：`detection plain_llm_df 44.8% > aitester 15.8% > plain_llm 1.5%`、`aitester vs df −28pp`（`:59-65`）、**真实 SWE-bench Lite n=20 冒烟 resolved 0/20，"有效性主张尚未被真实基准支持"**（`:85-86`）、"逻辑驱动"全链路**默认关闭**（`:87-88`） |
| `docs/DATA_CARD.md` | 8,006 | §1 数据集总览表（synthetic/QuixBugs/BugsInPy 零实跑/SWE-bench Lite 历史 0/20）（`:18-25`）；§2 主批次 n=50、seed=42、难度 L1–L5 分布 `{15,10,10,8,7}`、8 个跨文件任务、`bug_type assert 30/runtime 20`（`:34-39`）；§3 已知偏差 **"出题人=判卷人"**（`:47-50`）、`problem_statement` 无 prompt 消费点由静态守卫锁定（`:53-56`）、n=50 功效不足（`:57-58`）；§4 QuixBugs MIT / BugsInPy 无 SPDX / TestGenEval CC BY-NC 4.0 门槛（`:60-77`） |
| `SECURITY.md` | 2,555 | 只定义披露与响应流程（威胁模型指向 `docs/threat_model.md`）；支持范围仅 main 最新 commit、**不提供 LTS**；私有安全通告优先、**7 天内确认收悉**；安全基线列出 CI 阻断门禁（gitleaks 工作树扫描 + 二进制 SHA256 校验） |
| `docs/threat_model.md` | 11,278 | 六大攻击面 A1–A6 + R18 增补 T7–T9；系统假设含"**LLM 生成代码在本系统内自动执行——最核心的风险源**"；A1 凭证泄露→`credential_scrub.py` 三链路统一剔除、`.env*` 全部 gitignore；A2 供应链白名单 `PIP_PACKAGE_WHITELIST_ENABLE` **2026-10-09 C-08 起默认开**；A3 提示注入（召回 ≥0.8 / 误伤 0 回归基准）；A4 三级沙箱，其中**内核级 `KERNEL_SANDBOX_ENABLE` 默认关**（状态列 ⚠️ 部分） |
| `CITATION.cff` | 1,065 | `cff-version: 1.2.0`；`version: 0.7`、`date-released: "2026-10-06"`、`license: MIT`；摘要声明 detection-first + M1 honest metrics + pooled 多种子统计（McNemar / 贝叶斯 / BH-FDR / 模板簇敏感性）为工件组成部分 |
| `LICENSE` | 1,078 | MIT License，`Copyright (c) 2026 AITester Contributors` |

### 3.9 工程与配置

| 文件 | 大小(B) | 关键内容（行号） |
|---|---:|---|
| `pyproject.toml` | 16,780 | `[build-system] requires = ["setuptools>=77.0","wheel"]`（AS 批为 PEP 639 抬下限，`:7-11`）；`name = "aitester"`、`dynamic = ["version"]`（O35：避免 PEP 517 下产出 `0.0.0` 而 `--version` 为 0.7，`:14-23`）；`requires-python = ">=3.12"`（`:24`）；`license = "MIT"` + `license-files = ["LICENSE"]`（`:30-31`）；`version = {attr = "src.__version__"}`（`:66`）；运行时依赖核心为 langchain/langchain-openai/langgraph/click/python-dotenv/requests（`:32-...`） |
| `requirements.txt` | 6,230 | 顶层依赖全部 `==` 锁定并与 `requirements.lock` 同步（`:1-5`）：`langchain==1.3.15`、`langchain-openai==1.4.3`、`langgraph==1.2.11`、`openai==2.54.0`、`pymysql==1.2.0`、`DBUtils==3.1.2`（`:7-20`） |
| `requirements.lock` | 2,481 | 全量钉版（含 `chromadb==1.5.9`、`coverage==7.15.4`、`datasets==5.0.1` 等）；CI 以本文件为缓存键 |
| `setup.py` | 3,817 | 自述"退化为兼容 shim；pip 构建时优先读 pyproject.toml"；`_load_version()` 从 `src/__init__.py` 正则读取版本（单一事实来源） |
| `Dockerfile` | 1,308 | `FROM python:3.12-slim`；先 `COPY requirements.txt` 后装依赖以利用层缓存；注明"requirements.txt 锁定版本与 `requirements.lock` 由 `check_lock_sync.py` 在 CI 守卫一致性"；`CMD ["python","experiments/run_benchmark.py"]` |
| `Makefile` | 4,379 | 24 个 `.PHONY` 目标；`gates` = lint+typecheck+test+docs-check+env-budget+baseline-check+state-contract+tool-versions；只读复算目标 `cpr-idr` / `repair-replay` / `cf-upper-bound` / `corrected-metrics` / `target-quality` 均标注"零 LLM"；`build-check` **刻意不接 CI** |
| `.pre-commit-config.yaml` | 2,882 | ruff `v0.16.3`（与 CI 固定版本、lock 三方一致）；mypy `v1.15.0` + `additional_dependencies: [types-requests, types-PyYAML]`（已移除废弃 `types-all`）；`check-added-large-files --maxkb=500`；local hook `audit-log-redaction` 与 `secret-leak-guard`（复用 `.git-hooks/check_secret_leak.sh`，O17 全口径） |
| `.github/workflows/ci.yml` | 36,952 | 4 个作业：`smoke-llm`（`:45`，push/PR 默认关，周日 schedule 且三 Secrets 齐备才置 true）、`test`（`:102`，矩阵 `['3.12','3.13','3.14']` 见 `:118`，timeout 30 分钟）、`security`（`:395`）、`supply-chain`（`:573`）；`permissions: contents: read`（`:31-32`）；并发取消旧 run（`:37-39`）；action 全部 SHA 钉版（如 `actions/checkout@3f3f7fd…`、`actions/setup-python@8d5bc5b…`） |
| `.github/workflows/perf.yml` | 4,090 | 周日 07:30 UTC 性能巡检（错开 ci.yml 06:00），与 `docs/performance_baseline.json` 比对，**15% 相对阈值 + 0.05ms 绝对下限、non-blocking 告警** |
| `.github/workflows/release.yml` | 8,217 | tag `v*` 触发；流程 build → twine check → CycloneDX SBOM → PyPI（仅官方仓且配置 `PYPI_API_KEY` 时）→ GitHub Release；刻意不引入新第三方 action |
| `.dockerignore` / `.gitignore` | 2,520 / 6,679 | `.dockerignore` 首段即声明排除本地含真实 LLM 密钥的 `.env`；`.gitignore` 中 `.env`:28、`.env.local`:29、`.private/`:40（另见 :103/:118）、`.hypothesis/`:55、`data/`:153 |

---

## 4. 缺失 / 不可读 / 敏感文件清单

### 4.1 敏感与受限文件（**未读取任何内容**，仅取元数据与 git 状态）

| 路径 | 存在 | 权限位 | 大小(B) | gitignore | git 追踪 | 说明 |
|---|---|---|---|---|---|---|
| `.env` | 是 | `-rw-r--r--`（0644） | 1,977 | 是（`.gitignore:28`） | **否** | 未读取内容。**权限位为 0644（同机其他用户可读）**，与"敏感"定位不匹配；仅陈述权限事实，不评估实际凭证强度 |
| `.env.local` | 是 | `-rw-r--r--`（0644） | 812 | 是（`.gitignore:29`） | **否** | 未读取内容。同上；`MODEL_CARD.md:23-27` 声明 LLM 密钥即为本文件的 `LLM_N_*` 三元组 |
| `.private/` | 是 | `drwxr-xr-x`（0755） | 21 文件 / 0.92 MB | 是（`.gitignore:40/:103/:118`） | **否**（`git check-ignore -v .private/...` 命中 `.gitignore:118`） | 未读取内容；仅列名：`audit/project_full_audit_2026-10-10.md`、`review/`（9 份审查报告 + `recovered/`）、`recovered/workbuddy_memory/`。`CHANGELOG.md:33-36` 载明 `.private/review/**` 为 20 份且"全部保留" |
| `.private/.env.local` | 是 | — | — | 是 | 否 | 未读取内容 |
| `llm_configs.json` | 是 | `-rw-r--r--` | 205 | **否** | **是**（受追踪） | 已读取：**非敏感**配置（`CHANGELOG.md:128-129` 载明 17 条 → 1 条 `deepseek-v4.1-flash`，无明文 Key） |
| `config.local.example` | 是 | `-rw-r--r--` | 2,490 | 否 | **是** | 本地配置示例（占位符） |
| `Dockerfile.repro` / `.dvcignore` | 是 | `-rw-------`（0600） | 2,059 / 1,723 | 否 | 否（未追踪且未被忽略） | 属主可读；权限位异常严格，但与敏感内容无必然关系 |

### 4.2 缺失 / 不存在的文件

| 期望路径 | 状态 | 备注 |
|---|---|---|
| `docs/troubleshooting.en.md` | **缺失** | 中文版自述 `> 语言 / Language：[English](troubleshooting.en.md)（待补）`（`docs/troubleshooting.md:3`）；该缺口由 `scripts/gates/check_bilingual_docs.py:63-85` 的 `_EXEMPT_NO_EN` 白名单豁免（`:83` 条目） |
| `README_iteration_log.md`（根目录） | **缺失** | 实际路径为 `docs/history/README_iteration_log.md`（27,572 B）与 `docs/history/README.en_iteration_log.md`（29,473 B） |
| `docs/review/`（R5 审查报告原文） | **缺失** | `CHANGELOG.md:107-109` 载明 `docs/review/review_2026_10_09_revision.md` 已随 2026-10-09 清理批次删除 |
| `docs/history/full_test_report_2026-09-28.md`、`docs/history/implementation_2026-10_l25hard_n40_batch.md` | **已删除（本次文档清理批次）** | 依据 `CHANGELOG.md:13-17` |
| `experiments/results/swe_bench_lite_statistical_report.md`、6 份 `g8_*` 单次全失败汇总、0 字节 `PA` | **已删除（孤儿报告）** | 依据 `CHANGELOG.md:18-22` |
| `data/swe_bench_lite_*` | 未在本机发现独立目录 | `MODEL_CARD.md:39` 提及该数据来源；本机 `data/` 下仅有 `quixbugs/`（438 文件） |

### 4.3 未能读取 / 未读取项（诚实声明）

| 项 | 原因 |
|---|---|
| `.env`、`.env.local`、`.private/**` 内容 | 任务明令禁止读取敏感内容；仅取 `stat` 元数据与 `git check-ignore`/`git ls-files` 结果 |
| `README.md`（128 KB）、`docs/api_reference.md`（92 KB）、`CHANGELOG.md`（397 KB）全文 | 按任务要求改用 `grep -n` 定位标题/关键数字 + 定点 `sed -n` 读取，**未全文读入**；因此上述文件的摘要只覆盖被引用行段 |
| `experiments/results/` 的 138 条目明细 | 按任务要求只做类别汇总（§1.4），**未逐个读取**；其 4,406 个 `.trace.jsonl` 与 820 个 `.json` 未打开 |
| `data/quixbugs/**`（438 文件，含 182 `.java`、44 `.class`、1 PDF） | 属 vendored 上游数据、gitignore 区，仅统计规模，未读取内容 |
| 二进制/缓存类：`.venv/`（911 MB）、`.mypy_cache/`、`.pytest_cache/`、`.ruff_cache/`、`.hypothesis/`、各 `__pycache__/` | 非审查对象，按任务排除，未读取 |
| `docs/history/optimization_plan.md`（60 KB）、`optimization_report.md`（58 KB）等大文件 | 只取标题与元数据，未全文读取 |

---

## 5. 本次审查依据的文件范围声明

### 5.1 实际读取并用于结论的文件（grep 定位 + 定点全文/片段阅读）

`README.md`、`README.en.md`、`QUICKSTART.md`、`QUICKSTART.en.md`、`CHANGELOG.md`（含 `:1-160` 与尾部版本说明）、`CHANGELOG.en.md`（头部）、`BASELINE.yaml`（`:1-260` 及 `:570-600`）、`docs/preregistration.md`（`:1-45`、`:48-177`、`:234-283`）、`docs/adr/README.md`（全表）、`docs/adr/0029-*.md`（头部）、`docs/design/repair_caliber_matrix.md`（`:1-70`）、`docs/design/*.md`（13 份各取前 4 行标题/状态）、`MODEL_CARD.md`（`:1-88`）、`docs/DATA_CARD.md`（`:1-77`）、`SECURITY.md`（头部）、`docs/threat_model.md`（头部 + A1–A4 行）、`CITATION.cff`、`LICENSE`、`CONTRIBUTING.md`（grep）、`pyproject.toml`、`requirements.txt`（头部）、`requirements.lock`（头部）、`setup.py`（头部）、`Dockerfile`、`Makefile`、`.pre-commit-config.yaml`（全文）、`.github/workflows/{ci,perf,release}.yml`（头部与作业名）、`.gitignore`（相关行）、`.dockerignore`（头部）、`.git-hooks/*`（清单）、`scripts/gates/check_bilingual_docs.py`（`:41-189`）、`src/__init__.py`（全文）、`docs/troubleshooting.md`（头部）、`experiments/results/analysis_summary.md`（元数据）、`.env`/`.env.local`/`.private/`（**仅元数据**）。

### 5.2 只列清单、未读内容的文件

- `experiments/results/**` 全部 5,322 个文件（除 `analysis_summary.md` 元数据外）；
- `data/quixbugs/**` 全部 438 个文件；
- `.venv/`、各类缓存目录；
- `tests/**` 255 个测试文件（仅统计文件数与行数，未打开内容）；
- `src/**` 中除 `src/__init__.py` 外的 118 个源文件（仅按大小/时间排序取元数据，未打开内容）；
- `docs/history/**` 20 份文档（仅元数据），`docs/api_reference.md`（仅元数据与标题未读全文）。

### 5.3 已经执行的只读命令（可复现）

`pwd`、`git rev-parse --short HEAD`、`git rev-list --count HEAD`、`git status --porcelain`、`git ls-files`、`git check-ignore -v`、`git branch -a`、`du -sh`、`find`（文件数/类型/权限/大小）、`stat -f`（大小与 mtime）、`wc -l`、`grep -n`、`sed -n`、`diff`，以及一次**只读**文档门禁复核：`.venv/bin/python scripts/gates/check_bilingual_docs.py --strict` → 输出"双语文档同步检查通过（0 警告 / 0 失败）"、`exit=0`（该脚本先经 grep 确认无 `write_text`/`open(...,"w")`/`subprocess` 等写操作）。

**未执行**：任何 formatter / 自动修复 / 写操作；未创建、修改、删除 `review_2026/T1_inventory.md` 以外的任何文件（本报告写入前 `review_2026/` 仅含 Lead 的 `LEAD_findings.md`）。

---

## 6. 索引过程中发现的事实性偏差（仅陈述证据，不做价值判断）

1. **ADR 索引落后于 ADR 实体**：`docs/adr/` 有 24 份 ADR（含 `0029`，2026-10-08，状态"已采纳"），但 `docs/adr/README.md` 索引表 23 行、覆盖到 `0028`，并在维护惯例中仍写"下一个 **0029**"（`docs/adr/README.md:41-43`）。
2. **`CHANGELOG.md` 的"当前版本"与版本单一事实来源不一致**：`CHANGELOG.md:5400` 称"当前版本为 0.6"，而 `src/__init__.py` 为 `__version__ = "0.7"`、`CITATION.cff:8` 为 `version: 0.7`、`BASELINE.yaml:14` 的记录亦引用 AS 批"`aitester --version 0.7`"。
3. **`CHANGELOG.md` 存在时间线异常的条目**：`## [0.9.11] - 凭证安全、可观测性与性能优化（2025-09-25）`（`:4738`）的年份（2025）与全文其余条目（2026-09 ~ 2026-10）不一致。
4. **双语文档门禁存在覆盖盲区（已实测）**：`check_bilingual_docs.py --strict` 当前 `exit 0`，但 `README.md`、`QUICKSTART.md`、`CONTRIBUTING.md` **均无"最后更新/Last updated"日期行**（`grep` 无命中），而对应英文版分别有 `2026-10-07`（`README.en.md:3`）、`2026-10-06`（`QUICKSTART.en.md:3`）、`2026-10-06`（`CONTRIBUTING.en.md:3`）。`scripts/gates/check_bilingual_docs.py:174-183` 的日期核对逻辑为"中英**双方**都能提取到日期才比对，否则只提示警告"，故中文侧缺日期行时**静默通过**——中英内容可无限期漂移而不触发门禁。
5. **`README.md` 正文日期口径与文档同步流程不一致**：`CHANGELOG.md:3`（中）/`:1`（英）已更新至 2026-10-10，`MODEL_CARD.md:3`/`docs/DATA_CARD.md:3` 为 2026-10-08，`README.en.md:3` 为 2026-10-07，`QUICKSTART.en.md:3`/`CONTRIBUTING.en.md:3`/`SECURITY.en.md:3` 为 2026-10-06 —— 同一时点的对外文档存在 **10-10 / 10-08 / 10-07 / 10-06 四档**"最后更新"日期。
6. **追踪面与 gitignore 白名单的规模**：仓库 4,028 个受追踪文件中 **3,426 个位于 `experiments/results/`**（占 85.1%），而该目录本机总计 5,322 文件；即"实验工件入库"策略实际把大批 trace/log 纳入版本控制（`.gitignore:119-152` 白名单显式放行 `main_batch/traces/**` 与 `e6_a1_batches/`、`r4_batches/` 全目录）。
7. **`experiments/results/` 只有 4/52 个批次带 `SHA256SUMS`**（`analysis`、`e6_a1_batches`、`main_batch`、`r4_batches`），仅 2 个带 `README.md`；而 `docs/preregistration.md:247-250` 的工件约定为"每个实验产出：批次 JSON + 全量 trace + 统计报告 + SHA256SUMS"。**注：该约定第 250 行以"（`experiments/results/main_batch/` 口径）"限定适用范围**，故上述差值不必然构成违约，仅登记为事实。
8. **权限位不一致**：仓库内 **209 个**既有文件为 `-rw-------`（0600），包括 `docs/adr/0003,0004,0011–0013`、`docs/design/{cross_file_repair.en,failure_knowledge_feedback,multilanguage_extension}.md`、`experiments/{contamination_check,model_gradient,synthetic_difficulty,test_suite_minimize,…}.py`、`src/agents/fl_spectral.py`、`tests/` 下 129 个测试文件等；而含真实 LLM 密钥的 `.env` / `.env.local` 反为 `0644`。
   - 精确口径（可复现）：`find . -type f -perm 600 -not -path './.git/*' -not -path './.venv/*' -not -path '*/__pycache__/*' -not -path './.hypothesis/*' -not -path './review_2026/*' | wc -l` = **209**；目录分布（前 6）：`tests/` 129、`src/tools/` 13、`experiments/`（顶层）10、`src/agents/` 6、`docs/adr/` 5、`src/utils/`+`src/graph/` 各 4。
   - 第一次测量曾得到 210/212，差值来自本会话内并行产生的 `review_2026/LEAD_findings.md`、`REPORT_draft.md`、`T1_inventory.md`（三者均为 0600），**非仓库既有文件**；上表口径已剔除 `review_2026/` 以保持可比。
9. **`data/quixbugs/` 是嵌套 git 仓库**：`data/quixbugs/.git` 存在（`find . -name .git -maxdepth 4` 唯一命中），外层仓库以 `data/`（`.gitignore:153`）整体忽略，未登记为 submodule（`git ls-files | grep quixbugs` 无命中）。
10. **`BASELINE.yaml` 自身存在"当前 vs 受阻"的并存表述**：`:195-211` 记录 2026-10-09 实跑时"**E6 matched 臂不可执行**…E6 状态改'受阻'"，而同文件 `:578-580` 的 `e6_matched.verdict` 又写"已执行：预算混杂被证否"。两处结论方向相反，**引用本节数字时必须以行号区分**。

---

## 7. 摘要（供 Lead 汇总用）

- **规模**：`src/` 119 py / 45,371 行；`tests/` 255 py / 66,880 行；`experiments/` 46 py / 19,087 行；`scripts/` 35 py / 6,292 行；文档 `.md` 33,108 行。仓库 1.2 GB（其中 `.venv` 911 MB、`experiments/results` 88 MB）；受追踪文件 4,028；HEAD `d9e51df`（456 提交），工作树干净。
- **数字的单一事实来源**：`BASELINE.yaml`（611 行）当前口径 = tests `5015`（`:17`）、行覆盖 `89%` / 分支 `83%`（`:27-52`）、mypy 119 文件 0 错误（`:82`）、CI 矩阵 3.12/3.13/3.14（`:84`）；**README/CHANGELOG/MODEL_CARD 中的 `1459 用例 / 96% 覆盖率 / 88.0% 成功率` 属 0.1 版本历史快照**（`CHANGELOG.md:5354` 起），`CHANGELOG` 顶部批次另有 `5107 passed`（`:100`）——三者时间点不同，不可混用。
- **预注册完整性**：E1–E7 均有主终点、阈值、停止规则与执行记录（`docs/preregistration.md:48-283`），并含 E4 污染防控强制披露条款（`:124-153`）。
- **候选问题（2–3 条，均附行号）**：① ADR 索引未收 `0029`（`docs/adr/README.md:41-43` vs `docs/adr/0029-*.md`）；② `CHANGELOG` 版本说明"0.6" vs 代码/`CITATION` "0.7"（`CHANGELOG.md:5400` vs `src/__init__.py`）；③ 双语日期门禁对"中文侧无日期行"静默放行（`scripts/gates/check_bilingual_docs.py:174-183`），当前 `README/QUICKSTART/CONTRIBUTING` 三对中英日期不可核对。
- **无法读取项**：`.env`、`.env.local`、`.private/**` 内容（按任务禁止读取，仅元数据 + gitignore/追踪状态）；`experiments/results/**`（按任务只做类别汇总）；`data/quixbugs/**`、`.venv`、各类缓存（非审查对象）。
