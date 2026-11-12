# AITester 复现说明

最后更新：2026-11-12

本文件说明如何复现 AITester 的实验：零 LLM 复算路径、含 LLM 的重新跑批路径，以及挂载与
测试门的行为。**原始 LLM 响应不随仓库分发**，含 LLM 路径必须重新消耗 API 配额。

> **归档快照**：版本锁定的派生判定行（含 50 格聚合、SHA-256 清单与一键复算脚本）
> 在 `10.5281/zenodo.24136905`（<https://doi.org/10.5281/zenodo.24136905>）公开，
> CC0-1.0、不含原始执行 trace 与模型转录。结果目录被 `.gitignore` 排除，
> 因此 fresh clone 必须把该快照与本仓代码配合使用，单独克隆仓库不足以复算稿件表格。

## 1. 前置条件

- Python 3.12+（`requires-python = ">=3.12"`；CI 矩阵 3.12/3.13/3.14），建议用仓库内 `.venv`。
- 依赖：`pip install -r requirements.txt`（或 `make install`）；wheel 运行侧还需 `pip install "aitester[execution]"`。
- 含 LLM 路径需要 `.env.local`（从 `config.local.example` 复制）的 `LLM_1_API_KEY` / `LLM_1_BASE_URL` / `LLM_1_MODEL`；**密钥不入库**，缺失时告警而非静默继续。
- 可选：Docker（`Dockerfile.repro`）；沙箱由 `EXECUTOR_USE_VENV` 等开关控制，默认 venv 沙箱开启。

```bash
python3 -m venv .venv && source .venv/bin/activate
make install
cp config.local.example .env.local   # 仅含 LLM 的路径需要填写
```

## 2. 三条复现路径

**A. 零 LLM 复算（不需要 API Key）**：

```bash
python scripts/tools/results_data_pack_20261111.py   # 现稿表格（需 DOI 快照的判定行）
make reproduce-zero-llm                              # 旧代语料复算链 L0
make reproduce-zero-llm-l1                           # L0 + 小时级 Mut@k 重算
```

pack 脚本只扫描三个登记批次目录（主批 50 格 + swebench / testgeneval 补充重跑），血统去重后逐指标带
`n_obs` 聚合，写出 `RESULTS_DATA_PACK_20261111.json`，冒烟目录不入白名单。L0/L1 面向**已退役协议代**
语料：统计扩展、mutation × detection 交叉验证、SWE-bench 披露、引用核验与 SHA256SUMS 校验（L1 追加
QuixBugs 全量 Mut@k）。结果三态 `ok` / `FAILED` / `skipped`——撤回支路显式 `[SKIP]` 并附理由，
**跳过不等于通过**；退出码只由 FAILED 命令数与校验和失败数决定。

**B. 含 LLM 的重新跑批（需要 API Key）**：

```bash
bash reproduce.sh --dataset synthetic --full
```

`--full` = 87 任务 / `--max-pattern-repeat 2` / seed 42 / 三臂（`aitester`、`plain_llm`、`plain_llm_df`）
——**旧代 synthetic 协议，不是现稿批次**；三种子入口 `experiments/run_main_batch.py`，**不同 seed 批次
不可直接合并统计**。现稿批次的重跑入口是 `scripts/run_all_tests.py` 的 full 档（两模型 × 5 臂 × 5 面）。
产物写入 `experiments/results/`（运行为产、不入库）。

**C. Docker 化复现**：

```bash
docker build --build-arg GIT_SHA=$(git rev-parse HEAD) -f Dockerfile.repro -t aitester-repro:$(git rev-parse --short HEAD) .
docker run --rm \
  -v $(pwd)/experiments/results:/workspace/experiments/results \
  -v $(pwd)/.env.local:/workspace/.env.local:ro \
  aitester-repro:<sha> bash reproduce.sh --dataset synthetic --full
```

镜像内无 `.git`，provenance 从构建期写入的 `.repro_provenance` 读取 `GIT_SHA`；未传
build-arg 时该值记为 `unknown`，不作提交 SHA 使用。

## 3. 历史输入与挂载

`.dockerignore` 排除 `experiments/results`，镜像**不自含**该目录。挂载目录同时是**历史输入**（全量测试
以其中归档工件为夹具）与输出：须挂载含归档结果的完整目录；空目录启动时 Step 3 的全量测试会失败，须显式跳过测试门。

## 4. 测试门逃生

`reproduce.sh` 的 Step 3 默认执行 `python3 -m pytest tests/ -v --tb=short`，测试失败**默认硬失败**（退出非零）。两个显式逃生开关：

| 变量 | 行为 |
|------|------|
| `REPRODUCE_ALLOW_TEST_FAILURES=1` | 测试失败仅告警并继续 |
| `REPRODUCE_SKIP_TESTS=1` | 整个测试门跳过，打印醒目 WARN |

跳过时结论**不含测试验证**——这是披露，不是通过。默认不设任何变量即保持 fail-closed。 一次跑完全部测试面的入口是 `python scripts/run_all_tests.py`（两档：`smoke` 每个面跑一项验装配、`full` 每个面跑满出读数；默认 `both` 顺序执行且冒烟未全通即不开全量——旧证据还必须与本轮**同配置指纹**（矩阵形状、协议取值、`HEAD`、工作树摘要、逐模型并发决议），详见 `INVENTORY.md` 的入口点表）；两条路径的深度思考默认关闭（`LLM_THINKING_MODE`，实测单调用输出 −92%/−94%），跨模型对比因此建立在同一设置上。付费段的三件事在同一处决定：每格 LLM 并发 = 厂商额度 80% ∩ 机器闸 ∩ 显式 `--llm-parallel`（额度登记在 `MODEL_RATE_LIMITS`，两种量纲不互换：在途档封顶并发，RPM 档只封发起速率）；数据集闸的结论参与选面（判不可判定的面点名剔除，不再照旧付费）；严格口径开关（`AITESTER_DATASET_STRICT_INSTANCE_CODE` / `AITESTER_DATASET_STRICT_TEST_CODE`）把"没有源码"与"官方测试给不出判定"的任务留在分母之外，同时 `PATCH_EVIDENCE_OFFICIAL_TESTS_ENABLE` 打开图内 gold 裁决——证据门等级不足时把该任务的官方测试跑在打补丁源码上，全绿才放行。

## 5. 证据索引

| 内容 | 位置 |
|------|------|
| 现稿读数事实源（50 格聚合 + 稿件） | `experiments/results/RESULTS_DATA_PACK_20261111.json`、`paper/tex/manuscript.tex` |
| 派生判定行快照（版本锁定、CC0-1.0） | DOI `10.5281/zenodo.24136905` |
| 测试计数 / 静态检查 / 旧代基准读数 | `BASELINE.yaml` |
| 数据来源与许可（五个基准面） | `docs/DATA_CARD.md` |
| 预注册协议（E1–E7） | `docs/preregistration.md` |
| 测量口径矩阵与修复读数（旧代） | `docs/design/repair_caliber_matrix.md` |
| 工件校验和 | `experiments/results/**/SHA256SUMS` |
| 许可证与引用 | `LICENSE`、`CITATION.cff` |

现稿读数以数据 pack 与稿件为准；`BASELINE.yaml` 的 benchmark 节与已撤回的 n=261/臂旧主批（2026-10-24）属已退役协议代，不与现稿混池。缺口：原始 LLM 响应未归档，重跑受服务端漂移影响。

## 6. 环境四元组（N08，2026-10-30 冻结）

新批次必须钉死 **seed / 模型别名+fingerprint / 温度 / 数据集版本内容指纹** 四元组（缺一 fail-closed、跨四元组不可混池）——细则见 `docs/design/replication_quadruple_n08.md`。
