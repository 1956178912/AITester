# 性能与成本指南

最后更新：2026-10-26 · English: [performance_guide.en.md](performance_guide.en.md)

本指南给出成本与时延的**计算口径**、测量方法，以及与 `BASELINE.yaml` 读数的关系。仓库
不承诺固定性能数字：可复算读数以 `BASELINE.yaml` 为唯一事实源，本文只写公式与单位。

## 1. 成本模型

单任务 LLM 成本：

```text
cost_task = Σ_calls ( input_tokens × price_in + output_tokens × price_out ) / 1_000_000
```

- 价格单位：USD / 百万 token；`price_in` / `price_out` 取自登记价目表（当前只登记
  DeepSeek 官方 deepseek-flash 峰时价，见 [COST_MODEL.md](COST_MODEL.md)）。
- 多智能体路径的调用数 = Planner + Generator + 每轮 Debugger（可多次）+ 可选
  FaultLocalizer / ExpertPool；基线路径通常只有单次生成调用。
- `plain_llm_df` 等基线的已记账花费是**下界**（`cost_caliber="recorded_lower_bound"`）：
  token 三元组全 0 但存在生成结果的行按 0 计入金额分子，真实花费只会更高。
- 缓存命中不产生 API 计费；冷启动与热缓存的成本不可直接比较。
- 可选成本闸：`COST_BUDGET_ENABLE`（默认关）按任务 token / USD 硬上限截断。

## 2. 时延模型

```text
wall_task ≈ llm_calls × (latency_llm + retry_wait)
          + iterations × (pytest_wall + patch_apply_wall + snapshot_wall)
```

- `latency_llm`：单次 LLM 调用的墙钟时延；受端点和模型影响，**未测**统一口径。
- `retry_wait`：`LLM_RETRY_WAIT`（默认 30s）× 可恢复失败次数（限流 / 超时 /
  `finish_reason` 截断）。
- `pytest_wall`：受 `EXECUTION_TIMEOUT`（默认 30s）约束；超时按失败处理。
- `iterations`：`MAX_ITERATIONS`（默认 3）内的实际修复轮数。
- 并发：CLI `--parallel`（默认 1）与基准 `BENCHMARK_PARALLELISM`（0 = 串行）降低总墙钟，
  但不改变单任务成本。
- venv 沙箱首次创建与依赖安装是冷启动开销；缓存命中后显著下降（缓存目录
  `AITESTER_VENV_CACHE_DIR`，可用 `clean-venv-cache` 清理）。

## 3. 如何测量

```bash
make perf-bench
make perf-check
```

- `make perf-bench` 写 `experiments/results/performance_benchmark.json`（与 `perf.yml` 同口径）。
- `make perf-check` 对比当前读数与基线，默认非阻断告警；本机排查可加 `--strict`。
- 单任务细粒度：`python3 main.py run <file> --json` 的结果含耗时字段；结构化 trace 由
  `AITESTER_TRACE_DIR` 指定目录输出（未设时不写盘，仅保留进程内快照缓冲；目录不可创建时
  告警降级为仅内存，不阻断任务）。
- 成本读数：批次 provenance 的 `usage` / token 三元组与价目表相乘；不要从日志文本估算。

测量纪律：同一机器、同一依赖锁、同一端点；明确标注**冷缓存还是热缓存**、并发度与
样本量；单次运行不构成性能结论。

## 4. 与 BASELINE 的读数关系

- `BASELINE.yaml` 是成本、时延与测试计数的唯一登记点；本文与 README 不复制具体数字。
- 基准成本按**单批**登记，不与已撤回的 n=261/臂池混算；不同世代（模型、代码树、
  数据清除前后）不可直接比较。
- 未测项显式写「未测」，不做外推估计；若某项在 `BASELINE.yaml` 中缺席，视为未测而不是 0。
- 发布前若刷新读数，先跑实测，再同步 `BASELINE.yaml` 与
  [PROJECT_STATUS_REGISTER.md](PROJECT_STATUS_REGISTER.md) §1，最后跑 `make gates` 对账。
