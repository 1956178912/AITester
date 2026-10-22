# AITester 复现包（Replication Package）顶层 README

> **用途**：EMSE Open Science Initiative 复制包的顶层索引。本目录
> （`experiments/results/`）收录论文全部数字对应的原始工件、重算脚本
> 入口与校验和。**论文中每一个数字都可以在本目录找到对应工件，并由
> 零 LLM（或限定 LLM 配额）脚本逐位复算。**
>
> 版本：2026-10-16（第十九轮评审 + EMSE 投稿前整理批次）
> 关联：`docs/emse/EMSE_SUBMISSION_SKELETON_2026-10-16.md`（论文骨架）、
> `../../reproduce.sh`（端到端复现入口）、`../../Dockerfile.repro`（容器复现）

---

## 1. 目录结构与文件格式

| 路径 | 内容 | 格式 |
|---|---|---|
| `main_batch/` | **R-P0-2 主批次**（当前口径）：三种子三臂原始结果 JSON + 统计报告 + SHA256SUMS | JSON（每任务一行 details）+ Markdown 报告 + 校验和 |
| `e6_a1_batches/` | E1-E7 系列：E4 QuixBugs 修正结算双臂、E6 等预算对照、各消融臂 | JSON + log + SHA256SUMS |
| `emse_*_2026101[3-6]/` | EMSE 优化批次工件：DSL 诊断、Mut@k 全量、校准、规格扩展复算、统计扩展 | JSON + README + SHA256SUMS |
| `emse_stats_extensions_20261021/` | **当前重发（AZ 轮，2026-10-21）**：Wilson CI / Cohen's g / OR / 成本 bootstrap（零 LLM 逐位复算）；修正标准 g 尺度与精确二项尾 epsilon；`20261016/` 为修正前历史归档，只读保留 | JSON + Markdown + SHA256SUMS |
| `benchmark_*.json`（根散点） | 历史批次原始结果（2026-08 至 2026-10），保留供审计追溯 | JSON |
| `SHA256SUMS`（各子目录内） | 工件完整性校验 | 文本（sha256 + 文件名） |

**命名规范**：`benchmark_<dataset>_<YYYYMMDD>_<HHMMSS>.json`（原始批次）、
`<分析主题>_<YYYYMMDD>/`（批次工件目录）。每个分析目录自带 README.md
说明口径、输入与复算命令。

## 2. 论文数字 → 工件对照（核心指标）

| 论文数字 | 工件 | 复算命令（零 LLM） |
|---|---|---|
| detection 三臂 15.8% / 1.5% / 44.8%（n=261） | `main_batch/benchmark_synthetic_20261006_*.json` | `make mutation-det-correlation` 或独立聚合脚本 |
| McNemar χ²=48.79 / p≈2.8e-12 | 同上 | `python -m experiments.bayesian_paired`（频率派部分） |
| Wilson CI / Cohen's g / OR / 成本 bootstrap | `emse_stats_extensions_20261021/`（历史值见 `20261016/`） | `python -m experiments.emse_stats_extensions`（种子 42，逐位确定） |
| E4 QuixBugs 45.9% vs 83.8%；repair 92.5% | `e6_a1_batches/e4_quixbugs_FIXED_harness/` | `python -m experiments.emse_optimization --mutation-correlation ...` |
| false_fix 口径矩阵（100% / 59.58% / 87.16%） | `main_batch/` + `emse_optimization.py::false_fix_caliber` | `python -m experiments.emse_optimization`（零 LLM） |
| Mut@k 全量 0.9396（QuixBugs，健全 29/50） | `emse_quixbugs_mutk_full_20261015/` | `python -m experiments.emse_quixbugs_mutk_full`（cosmic-ray 本地执行，无 LLM，耗时数小时） |
| spec_compile_rate 0.7161/0.5937/0.6397 | `emse_calib_*_20261014/` | `python -m experiments.emse_dsl_diag3` / `emse_dsl_extend_recheck`（零 LLM） |
| ULT 检出优先 accuracy 21.0%（42/200，Wilson [15.9%, 27.2%]） | `emse_ult_df200_20261017/` | `python experiments/emse_ult_dfsmoke_accuracy.py --benchmark <benchmark_ult_*.json> --arm plain_llm_df`（零 LLM 判定；跑批工件需 LLM 配额或 Zenodo） |

## 3. 一键复现（分层，按审稿人资源分级）

```bash
# L0 零 LLM 五分钟级：统计扩展 + 口径矩阵 + 引用核验
python -m experiments.emse_stats_extensions
python -m experiments.emse_optimization --mutation-correlation experiments/results/main_batch
python scripts/gates/check_citations.py --traceability

# L1 零 LLM 小时级：Mut@k 全量重算（cosmic-ray，本地确定性执行）
python -m experiments.emse_quixbugs_mutk_full

# L2 需 LLM 配额（~$0.3/臂）：主批次三臂复现（预注册口径）
bash reproduce.sh            # 快速模式（3 任务，冒烟）
bash reproduce.sh --full     # 完整模式（全部任务）

# L3 容器化（环境完全隔离，结果含 provenance；需挂载 .env.local 提供 LLM 凭证）
docker build -f Dockerfile.repro -t aitester-repro:$(git rev-parse --short HEAD) .
docker run --rm \
  -v $(pwd)/experiments/results:/workspace/experiments/results \
  -v $(pwd)/.env.local:/workspace/.env.local:ro \
  aitester-repro:$(git rev-parse --short HEAD)
```

## 4. 环境锁定

- Python 3.12 / 3.13 / 3.14（CI 三版本矩阵）；依赖全锁
  （`requirements.lock`，`pip freeze` 口径）；
- LLM 后端：deepseek-flash（temp=0.0 常驻，R11）；价目表
  `experiments/price_table.json`（官方价目 URL 登记，峰时全价保守口径）；
- 批次 JSON 内嵌 `environment` 块（git sha / python / platform /
  容器标记 / ~118 个环境开关快照），跨版本串味可检测。

## 5. 许可证

- **代码**：MIT（根目录 `LICENSE`）；
- **本目录数据与工件**：CC0-1.0（见 `REPLICATION_LICENSE.md`）——
  数据/结果工件放弃著作权，便利第三方复现与再分析；
- 第三方基准数据（QuixBugs / ULT 子集 / Defects4J）遵循其上游许可证，
  本包**不整体收录**上游原始语料；
- **例外（F14 更正，2026-10-22）**：benchmark JSON 的 `task_metadata` 内嵌上游
  `fixed` 源码与 gold `test_cases` 原文（可逐字节对照上游固定提交），这些字段
  按上游许可证处理，不属于 CC0 派生产出；包内其余工件（生成测试、判分结果、
  统计量）为派生数据。

## 6. Zenodo 归档元数据（待上传）

上传参数已备好（`zenodo_metadata.json`）：上传本目录 + 根目录核心文件，
获取 DOI 后回填至 `CITATION.cff` 的 `doi` 字段与论文 Data Availability
Statement。**归档完成前不得猜测填入 DOI**（CITATION.cff 注释口径）。
