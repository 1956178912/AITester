# AITester

**检出优先**的 Python 测试生成与修复评估（归因）研究系统：给定函数级修复任务，自动生成 pytest 测试、执行、诊断并打补丁。"多智能体编排"是可消融容器，不是主断言。

当前版本 1.0.0 · [变更日志](CHANGELOG.md) · [文档索引](docs/INDEX.md) · [MIT 许可证](LICENSE)

> **结论复现**：现稿表格的读数由 `scripts/tools/results_data_pack_20261111.py` 在三个登记批次目录上零 LLM 聚合（配合下面的 DOI 快照即可复算）；`make reproduce-zero-llm`（L1 是 `make reproduce-zero-llm-l1`）是**旧代语料**的复算链，部分支路因旧主批撤回而 `skipped`——跳过不等于通过。消耗 API 配额的 `reproduce.sh` 与 `experiments/run_main_batch.py` 只是按旧代预注册配置**重新跑批**，不在「工件 → 现稿数值」的链路上。六个开放科学维度的逐条回答写在 [INVENTORY.md](INVENTORY.md)。

> **数据归档 DOI**：[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24136905.svg)](https://doi.org/10.5281/zenodo.24136905) — 2026-11-11 版本锁定的派生判定行快照已公开发布（`10.5281/zenodo.24136905`），CC0-1.0、不含原始执行 trace 与模型转录；与本仓代码配合使用可零 LLM 逐字节复算 50 格聚合。

> 最后更新：2026-11-12

## 它是什么

AITester 是一个研究用系统，用 LangGraph 编排 Planner → Generator → Executor → Debugger → PatchApplier 闭环：

- **输入**：五个基准的任务（QuixBugs、BugsInPy、SWE-bench、TestGenEval、ULT；函数级单文件与仓库级两类）。
- **过程**：生成 pytest 测试 → 沙箱执行 → 失败诊断 → 生成补丁 → 复跑验证。
- **输出**：测试、补丁、结构化 trace，以及可复算的指标工件。

现稿的中心主张不是"多智能体是否更好"，而是"声明通过 ≠ 裁决真实通过"的 false-fix 配对报告（RQ2）
与 harness 排除披露（RQ3）。多智能体编排只作为可消融容器参与对照，不承载独立的能力主张。

## 它不是什么（诚实披露）

- **不是"自修复已达成"**。自修复是**可测量口径**，不是已证实主张。
- **历史读数（已退役协议代，不与现稿混池）**：repair 经两轮测量口径修正（ADR-0021/0027/0029）后为
  **39.31%**（v2，57/145 可重放行；gold 独立裁决）。修正前口径的 **repair=0** 是 patch 字段围栏残留与
  跨文件任务未物化造成的**伪影**，不是能力读数；口径分叉与复算方式见
  [修复口径矩阵](docs/design/repair_caliber_matrix.md)。
- **E7-r2 人工校标未执行**：抽样框已换成现稿 tab:falsefix 的 **89 条 declared-pass 判定行普查**
  （补丁轨 42 行 + 套件轨 47 行），备料包已生成、裁决仍待人工；协议见
  [预注册](docs/preregistration.md)，结果不在任何发布读数中（全仓无 Kappa 工件）。
- **SWE-bench 面是结构性排除，不是通过率**：2,197 行中 1,919 行 `harness_invalid`、278 行可判，
  排除行不进判定分母（RQ3 如实披露）；引用其 pass_rate 属误用。
- **读数限于本批次**：现行权威批次逐格对比两个端点（`deepseek-flash` × `mimo-v2.6-pro`，5 臂 × 5 面），
  跨模型读数按「模型 × 臂 × 面」分格、不混池，不外推到未测端点或任务集，跨批次不混池。
  `scripts/run_all_tests.py` 的冒烟档每格 1 任务只验装配，每格并发由厂商额度 80% ∩ 机器闸 ∩
  `--llm-parallel` 逐模型决议并写进冒烟指纹——冒烟不是能力读数。

## 快速开始

```bash
python3 -m venv .venv && source .venv/bin/activate
make install
cp config.local.example .env.local   # 只填变量值；变量名见 QUICKSTART
make test
```

完整步骤（含 venv 沙箱默认开启、第一个任务、故障排查）见 [QUICKSTART.md](QUICKSTART.md)。
LLM 端点通过 `.env.local` 的 `LLM_1_API_KEY` / `LLM_1_BASE_URL` / `LLM_1_MODEL_NAME`
配置（`1` 可换成其它编号）。

## 能做什么

| 能力 | 入口 | 说明 |
|---|---|---|
| 现稿表格复算 | `python scripts/tools/results_data_pack_20261111.py` | 零 LLM；需 DOI 快照的判定行 |
| 测试生成 + 修复闭环 | `make repro` | 消耗 LLM 配额；重新跑批（旧代 synthetic 协议） |
| 零 LLM 复算链（旧代语料） | `make reproduce-zero-llm` | 统计扩展 / 口径矩阵 / 引用核验 |
| 全量门禁 | `make gates` | lint / format / typecheck / 测试 / 文档与登记面门禁 |
| 代码质量 | `make lint` / `make format` / `make typecheck` | [Ruff](https://docs.astral.sh/ruff/) + mypy |
| 变异评估 | `make self-mutation` | 自身测试套件变异测试（零 LLM） |
| 修复覆盖率审计 | `make fix-coverage` | 找出新增但从未被执行的修复代码 |

确定性通道：SpecIR v2 编译断言、SMT 见证、Ochiai 谱系、变异评估、P2P 回归门禁。
故障定位是双通道：Ochiai 谱系（非 LLM）+ RGFL 式推理定位（`FaultLocalizerAgent`，
消耗 LLM，失败时保守降级）。

## 文档地图

| 想了解 | 读这份 |
|---|---|
| 全景与阅读路径 | [docs/INDEX.md](docs/INDEX.md) |
| 系统设计与算法 | [docs/algorithm_design.md](docs/algorithm_design.md) |
| 模块 / CLI / 配置 | [docs/api_reference.md](docs/api_reference.md) |
| 可运行示例 | [docs/usage_examples.md](docs/usage_examples.md) |
| 测量口径与成本 | [docs/performance_guide.md](docs/performance_guide.md) |
| 数据来源与许可 | [docs/DATA_CARD.md](docs/DATA_CARD.md) |
| 效度与局限 | [docs/VALIDITY.md](docs/VALIDITY.md) |
| 已知限制与风险 | [MODEL_CARD.md](MODEL_CARD.md) |
| 安全与威胁模型 | [SECURITY.md](SECURITY.md) · [docs/threat_model.md](docs/threat_model.md) |
| 常见故障 | [docs/troubleshooting.md](docs/troubleshooting.md) |
| 复现包 | [REPLICATION.md](REPLICATION.md) |
| 决策记录 | [docs/adr/](docs/adr/) |

## 复现

三条路径，按成本从低到高：

```bash
make reproduce-zero-llm   # 零 LLM：旧代语料统计复算 + 工件校验
make test                 # 测试套件（CI 同口径）
make repro                # 重新跑批（旧代 synthetic 协议；消耗 LLM 配额，勿自动触发）
```

现稿表格走另一条零 LLM 路径：`python scripts/tools/results_data_pack_20261111.py`（需 DOI 快照的判定行）。
前置条件、镜像挂载与证据索引见 [REPLICATION.md](REPLICATION.md)。

## 测试状态

数值只在一处维护：[BASELINE.yaml](BASELINE.yaml) 的 `tests` / `coverage` / `static_checks` 节；
本地与 CI 用 `make test` / `make test-cov` 复跑。

支持 Python 3.12 / 3.13 / 3.14（CI 矩阵 `3.12/3.13/3.14`，见 BASELINE.yaml `python_ci_matrix`）。

## 安全与贡献

- 漏洞披露流程见 [SECURITY.md](SECURITY.md)；请勿公开 Issue。
- 开发环境、提交前检查与文档约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。
- 合并前必须 `make gates`（单链，勿与其它测试并发）。

## 许可证与引用

MIT，见 [LICENSE](LICENSE)。学术引用格式见 [CITATION.cff](CITATION.cff)。
