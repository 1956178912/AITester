# AITester

**检出优先**的 Python 测试生成与修复评估（归因）研究系统：给定函数级修复任务，自动生成 pytest 测试、执行、诊断并打补丁。"多智能体编排"是可消融容器，不是主断言。

当前版本 1.0.0 · [变更日志](CHANGELOG.md) · [文档索引](docs/INDEX.md) · [MIT 许可证](LICENSE)

> **结论复现**：报告中的每个关键读数都走零 LLM 复算路径（`make reproduce-zero-llm`，L1 是 `make reproduce-zero-llm-l1`）。本仓库中需要消耗 API 配额的 `reproduce.sh` 与 `experiments/run_main_batch.py` 只是按预注册配置**重新跑批**，不在「工件 → 结论数值」的链路上。六个开放科学维度的逐条回答、以及包内哪些支路当前是 `skipped` 而非 `passed`，写在 [INVENTORY.md](INVENTORY.md)。

> 最后更新：2026-10-27

## 它是什么

AITester 是一个研究用系统，用 LangGraph 编排 Planner → Generator → Executor → Debugger → PatchApplier 闭环：

- **输入**：函数级修复任务（合成数据集，或 SWE-bench Lite 拆分任务）。
- **过程**：生成 pytest 测试 → 沙箱执行 → 失败诊断 → 生成补丁 → 复跑验证。
- **输出**：测试、补丁、结构化 trace，以及可复算的指标工件。

研究问题不是"多智能体是否更好"，而是"检出优先的测试生成能否作为修复的可靠前置"。
多智能体编排只作为可消融容器参与对照（ADR-0016）。

## 它不是什么（诚实披露）

- **不是"自修复已达成"**。自修复是**可测量口径**，不是已证实主张。
- repair 指标经两轮测量口径修正（ADR-0021/0027/0029）后为 **39.31%**（v2，57/145
  可重放行；gold 独立裁决）。修正前口径的 **repair=0** 是 patch 字段围栏残留与
  跨文件任务未物化造成的**伪影**，不是能力读数；口径分叉与复算方式见
  [修复口径矩阵](docs/design/repair_caliber_matrix.md)。
- **E7 人工复核未执行**：协议与预注册已冻结（[预注册](docs/preregistration.md)），
  结果不在任何发布读数中。
- **SWE-bench Lite 只有链路能力，没有可引用通过率**；引用其 pass_rate 属误用。
- 主批次使用**单一模型家族**（用户配置的 OpenAI 兼容端点；内置仅 DeepSeek 官方端点），
  跨模型外推不在已测范围内。

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
| 测试生成 + 修复闭环 | `make repro` | 消耗 LLM 配额；主批次复现 |
| 零 LLM 复算链 | `make reproduce-zero-llm` | 统计扩展 / 口径矩阵 / 引用核验 |
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
make reproduce-zero-llm   # 零 LLM：统计复算 + 工件校验
make test                 # 测试套件（CI 同口径）
make repro                # 主批次（消耗 LLM 配额，勿自动触发）
```

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
