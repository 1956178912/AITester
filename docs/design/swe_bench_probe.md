# R-01 SWE-bench 补跑探路立项（5 任务小范围验证）

> 立项日期：2026-09-21（0.7 轮次 C 方向）
> 状态：**立项完成，待用户确认配额后执行**
> 关联清单：历史缺口清单 R-01（2.1 SWE-bench 子集补跑）
> 前置依赖：SWE-bench lite 子集已下载至 `~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl`（225 可用）

## 1. 背景与目标

### 1.1 现状

历史 SWE-bench 20 任务验证（`experiments/results/swebench_20_summary.json`，2026-08-17）：
- 20 任务中 7 完成 / 3 失败 / 10 超时，总耗时 1173.5s；
- **pass_rate 0/7（0%）**——全部 7 个完成任务均因 API 限流（429）失败；
- 根因：当时各端点（International Agnes / Domestic Agnes / BigModel）全部限流，
  非代码缺陷，属于外部配额瓶颈。

### 1.2 问题

- 历史 0/7 的 pass_rate 是"配额瓶颈"而非"能力评估"，无法作为
  AITester 在 SWE-bench 真实任务上的有效基准；
- 当前 `.env` 已配置 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `MODEL_NAME`
  （见 `.env` 前 40 行键名），具备实际调用条件；
- 需要一次小范围探路验证"当前配额能否稳定跑通"，再决定是否扩大。

### 1.3 目标

- **成功标准（可测）**：5 任务探路中，至少 1 个任务在 600s 内完成
  且 API 调用零 429（即配额可承载），结果归档至 `experiments/results/`；
- 探路通过 → 扩大至 20 任务对齐历史口径（与 `swebench_20_summary.json` 对比）；
- 探路失败（仍全 429）→ 记录配额瓶颈，R-01 维持"待配额"状态。

## 2. 方案对比

### 方案 A：直接 20 任务对齐历史口径
- 优点：与历史 `swebench_20_summary.json` 可直接对比；
- 缺点：配额不足时 20 任务全失败，耗时 ~1200s 浪费；
  若中途发现限流已停（key 失效），整个批次作废。

### 方案 B：5 任务探路 + 通过则扩大（本轮采用）
- 优点：小成本验证配额可用性，通过后再投入 20 任务；
- 缺点：多一轮实验周期；
- 选 B。理由：历史 0/7 全因 429，当前配额状态未知，先小范围探路更稳。

## 3. 执行命令

### 3.1 探路（5 任务）

```bash
cd /Users/wangchenyu/Workspace/AITester
.venv/bin/python experiments/run_benchmark.py \
  --dataset swe_bench --subset lite \
  --task-limit 5 \
  --baselines aitester \
  --output-dir experiments/results \
  --no-rag \
  -v
```

参数说明：
- `--subset lite`：用 lite 子集（225 可用，历史口径）；
- `--task-limit 5`：限制 5 任务（run_benchmark.py:758 `dataset.tasks[:task_limit]` 生效）；
- `--baselines aitester`：仅跑 AITester（多智能体协作，探路最小面）；
- `--no-rag`：显式关 RAG（历史基准口径，避免 RAG 首次下载嵌入模型干扰探路计时）；
- `-v`：详细日志，便于定位 429。

### 3.2 探路通过后的扩大（20 任务，待执行）

```bash
.venv/bin/python experiments/run_benchmark.py \
  --dataset swe_bench --subset lite \
  --task-limit 20 \
  --baselines aitester,plain_llm,single_agent \
  --output-dir experiments/results \
  --no-rag \
  -v
```

## 4. 结果归档与对比

- 探路结果输出至 `experiments/results/benchmark_swe_bench_<timestamp>.json`；
- 与历史 `experiments/results/swebench_20_summary.json` 对比：
  - 若探路 5 任务 pass_rate > 0：记录"配额已恢复"，执行 §3.2 扩大批次；
  - 若仍全 429：记录"配额瓶颈持续"，R-01 维持待配额状态，不扩大。

## 5. 风险与回滚

- **配额风险**：5 任务探路消耗 ~5×3 轮次×2 LLM 调用 ≈ 30 次调用，
  配额成本可控；
- **超时风险**：单任务 600s 上限（`EXECUTION_TIMEOUT` 默认 30，
  任务级超时由 run_benchmark 控制），5 任务总耗时预计 300-600s；
- **回滚**：探路为只读实验（不修改 src/ 代码），结果仅归档至
  `experiments/results/`，无回滚必要。

## 5.1 探路首跑发现（2026-09-21，0.7 轮次实测）

首跑 `--dataset swe_bench --subset lite --task-limit 5` 暴露两个前置阻塞：

1. **lite 子集 JSONL 为空**：`~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl`
   0 行（全仓 SWE-bench 缓存中仅 `swe_bench_instances.jsonl` 有 225 条，
   lite/mini/full/unknown 子集文件均为 0 行）；
2. **加载器静默降级**：lite 子集 0 任务 → 加载器回退到 examples 合成数据集，
   实际跑了 3 个合成任务（`task_id` 前缀 `examples__`），结果归档
   `experiments/results/benchmark_swe_bench_20260921_175906.json`
   （`total_tasks: 3`，但 dataset 字段标 `swe_bench`/`lite`，具误导性）；
3. **缺源码字段**：通用文件 225 条无 `instance_code`（SWE-bench 官方 JSONL
   不含被测源码），未配 `SWE_BENCH_ENRICHMENT` → 即使子集文件有任务，
   源码仍缺失，基准仅验证流程、不产生有效修复对比（见 2.1 节历史结论）。

**结论：R-01 的真实阻塞项不是"配额不够"，而是"数据集无可用源码"。**
需先解决以下任一项才能有效探路：
- (a) 用 `scripts/download_swe_bench.py` 补下载 lite 子集 JSONL（若源站有）；
- (b) 用 `scripts/export_swe_bench_source.py` 生成 `SWE_BENCH_ENRICHMENT` 补充
  文件（需先 `git clone` 各仓库到 `--repos-dir`，成本较高）；
- (c) 接受现状，把 R-01 标记为"数据集准备未完成，待源码补齐后再探路"。

0.7 轮次选择 **(c)**：记录在案，不强行跑（避免"3 个合成任务冒充 SWE-bench
基准"的误导归档）。R-01 维持"待数据集准备"状态，源码补齐后再执行 §3.1 探路。

## 6. 与 R-03（对抗性推理）的关系

R-03（AdverIntent-Agent）已实装于 `src/agents/debugger.py`
（`ADVERSARIAL_DEBUGGING_ENABLE` 默认关 + 批评者评估闭环，0.5 批次落地），
与 R-01 独立。R-01 探路默认**不启用** R-03（保持历史实验口径）。

注：`experiments/run_benchmark.py` 当前无 `--adversarial` CLI flag，
R-03 仅经环境变量 `ADVERSARIAL_DEBUGGING_ENABLE=true` 启用。
扩大批次若要对照 R-03，需 `export ADVERSARIAL_DEBUGGING_ENABLE=true`
后再执行 §3.2 命令（或后续给 run_benchmark 补一个 `--adversarial` flag，
属小改，不阻塞本轮探路）。
