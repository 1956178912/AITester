# T 轮全功能 e2e 探针矩阵（2026-10-18）

> `scripts/tools/e2e_probe.py --all`（零 LLM 子集）与 `AITESTER_E2E_LLM=true --include-llm`（含 12 个真实 LLM 探针）
> 在 T 轮代码切点（commit `962c77e`，含 A-19 抢占优先级/回滚 schema/探针去重）上的实测。
> 运行器强制 `AITESTER_LLM_CACHE=0`；除 LLM 探针外零网络/零配额。

## 0. 结果

| 运行 | 命令 | 汇总 |
|---|---|---|
| 零 LLM | `python scripts/tools/e2e_probe.py --all` | **pass=56 / fail=0 / error=0 / skip=12（共 68）** |
| 含真实 LLM | `AITESTER_E2E_LLM=true python scripts/tools/e2e_probe.py --all --include-llm` | **pass=68 / fail=0 / error=0 / skip=0（共 68）**，探针耗时合计 97.5s |

- **注册数 = 可执行数 = 68**（56 零 LLM + 12 真实 LLM）。T 轮前实际注册 68 但运行器按 name 去重时
  把 2 个重名探针（`observability-trace-redaction` / `observability-event-bus`，workflow+platform 双重注册）
  静默丢弃到 `load_errors`，报告仍显示 66/66 pass——本轮已去重（详见 `docs/MEASUREMENT_INTEGRITY.md` §7 T-5a）。
- 分组计数：logic 20 / cli 6 / safety 5 / executor 5 / budget 4 / security 4 / dataset 4 /
  observability 4 / workflow 3 / agents 3 / localization 3 / cache 3 / repair 2 / rag 2。
- T 轮新增 2 探针（均 pass）：`logic-stagnation-precedence`（A-19 抢占优先级默认关零变化 + ON 停滞优先）、
  `logic-rollback-schema-fields`（回滚两键双分支键集合同构 + 三态投影 + 落盘）。

## 1. 产物

- `report.json` / `report.md`：零 LLM 子集报告（12 个 LLM 探针 skip，原因显式）。
- `report_llm.json` / `report_llm.md`：含真实 LLM 探针的完整报告（68/68 pass）。
- `README.md`（本文）+ `SHA256SUMS`（`checksum_results.py --write`，verify 通过）。

## 2. 口径与限制

- 零 LLM 报告里的 12 个 skip 是**预期**（未开 `--include-llm`），不是失败；含 LLM 报告为全量矩阵。
- 矩阵不接 CI 阻断（启动子进程/本机能力差异）；CI 只跑零 LLM 子集。发布前手动 `make e2e-probe(-llm)`。
- 探针矩阵是"功能清单级可达性"验证，不替代单元测试（模块契约）与实验批次（研究结论）。
