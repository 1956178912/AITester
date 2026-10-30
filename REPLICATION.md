# AITester 复现说明

最后更新：2026-10-27

本文件说明如何复现 AITester 的实验：零 LLM 可复算路径、含 LLM 的重新跑批路径，以及
挂载与测试门的行为。**原始 LLM 响应不随仓库分发**，因此含 LLM 路径必须重新消耗 API
配额；可离线复算的只有基于已入库工件的指标。

## 1. 前置条件

- Python 3.12+（`pyproject.toml` 的 `requires-python = ">=3.12"`；CI 矩阵
  3.12/3.13/3.14）。建议使用仓库内 `.venv`。
- 依赖：`pip install -r requirements.txt`（或 `make install`）；wheel 安装的运行侧还需
  `pip install "aitester[execution]"`。
- 含 LLM 路径需要 `.env.local`（从 `config.local.example` 复制）里的 `LLM_1_API_KEY` /
  `LLM_1_BASE_URL` / `LLM_1_MODEL`；**密钥不入库**，缺失时脚本告警而非静默继续。
- 可选：Docker（`Dockerfile.repro`）；内核级沙箱与 venv 沙箱由 `EXECUTOR_USE_VENV`
  等开关控制，默认 venv 沙箱开启。

```bash
python3 -m venv .venv && source .venv/bin/activate
make install
cp config.local.example .env.local   # 仅含 LLM 的路径需要填写
```

## 2. 三条复现路径

**A. 零 LLM 可复算（不需要 API Key）**：

```bash
make reproduce-zero-llm
make reproduce-zero-llm-l1
```

L0 执行统计扩展、mutation × detection 交叉验证、SWE-bench 披露、引用核验与逐目录
SHA256SUMS 校验；L1 追加 QuixBugs 全量 Mut@k 重算（小时级）。结果三态：`ok` /
`FAILED` / `skipped`——源工件已撤回的支路显式 `[SKIP]` 并附理由，**跳过不等于通过**；
退出码只由 FAILED 命令数与 SHA256SUMS 失败数决定。

**B. 含 LLM 的单批重新跑（需要 API Key）**：

```bash
bash reproduce.sh --dataset synthetic --full
```

`--full` = 87 任务 / `--max-pattern-repeat 2` / seed 42 / 三臂
（`aitester`、`plain_llm`、`plain_llm_df`）。本脚本单 seed；完整三种子协议入口是
`experiments/run_main_batch.py`，**不同 seed 批次不可直接合并统计**。产物写入
`experiments/results/`（运行为产、不入库）。

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

`.dockerignore` 排除 `experiments/results`，镜像**不自含**该目录。挂载的目录同时是
**历史输入**（全量测试以其中归档工件为夹具）与输出（本次结果）：复现时须挂载含归档
结果的完整目录；用空目录启动时，Step 3 的全量测试会失败，须显式跳过测试门。

## 4. 测试门逃生

`reproduce.sh` 的 Step 3 默认执行 `python3 -m pytest tests/ -v --tb=short`，测试失败
**默认硬失败**（退出非零）。两个显式逃生开关：

| 变量 | 行为 |
|------|------|
| `REPRODUCE_ALLOW_TEST_FAILURES=1` | 测试失败仅告警并继续 |
| `REPRODUCE_SKIP_TESTS=1` | 整个测试门跳过，打印醒目 WARN |

跳过时结论**不含测试验证**——这是披露，不是通过。默认不设任何变量即保持 fail-closed。

## 5. 证据索引

| 内容 | 位置 |
|------|------|
| 数字单一事实源（测试计数、静态检查、基准读数） | `BASELINE.yaml` |
| 数据来源与许可（合成模板 / SWE-bench / QuixBugs） | `docs/DATA_CARD.md` |
| 预注册协议（E1–E7） | `docs/preregistration.md` |
| 测量口径矩阵与修复读数 | `docs/design/repair_caliber_matrix.md` |
| 2026-10-24 撤回工件映射 | `docs/study/WITHDRAWN_ARTIFACTS_2026-10-24.md` |
| 工件校验和 | `experiments/results/**/SHA256SUMS` |
| 许可证与引用 | `LICENSE`、`CITATION.cff` |

历史主批次（n=261/臂）已随 2026-10-24 清除撤回；当前读数以 `BASELINE.yaml` 与重建批
为准，单批不混池。缺口：原始 LLM 响应未归档，重跑受服务端漂移影响；历史批无模型指纹。

## 6. 环境四元组（N08，2026-10-30 冻结）

新批次必须钉死 **seed / 模型别名+fingerprint / 温度 / 数据集版本内容指纹** 四元组
（缺一 fail-closed、跨四元组不可混池）——细则见 `docs/design/replication_quadruple_n08.md`。
