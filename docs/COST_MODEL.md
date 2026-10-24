# 成本与墙钟模型：批后处理墙钟可观测（Q-3）

> 最后更新：2026-10-18
>
> 本文定义**批后处理墙钟（postprocess wall）**的观测口径与集成契约。它补的是
> 现有成本/墙钟账本的盲区：批次 JSON 只有总墙钟与 token/美元成本，没有
> "后处理各阶段（mutation / M1 / MDO / other）逐任务耗时分布"，因此无法回答
> "这次跑到 2400s 是哪个阶段、哪一类任务、是不是长尾"。

## 1. 背景与问题

O-2 真实 LLM 验证批（同 cut / 同协议）暴露后处理墙钟的 run-to-run 波动：
control 臂 **2102s → >2400s（撞 2400s 后处理 watchdog）→ 2297s**，波动 ≥14%。
批次既有字段只能看到"总墙钟"，无法区分：

- 波动来自哪个后处理阶段（mutation 逐变异体执行 / M1 指标复算 / MDO 后处理）；
- 是"全体任务变慢"还是"少数任务长尾"（p50 稳定但 p95/max 爆炸）；
- 是"任务超时被 watchdog 截断"还是"真实计算变慢"（超时任务计数）。

因此需要把后处理墙钟做成**稳定、可序列化、可告警**的观测字段，随批次 JSON
一起归档（与 token/美元成本并列，构成"资源-时间"二维诊断）。

## 2. 指标与 JSON 形状

`experiments/postprocess_wall.py::build_postprocess_wall` 的输出形状（每个后处理
阶段一项；阶段按传入顺序）：

```json
{
  "mdo": {
    "wall_s": 123.4,
    "n_tasks": 15,
    "mean_s": 8.23,
    "p50_s": 3.1,
    "p95_s": 40.0,
    "max_s": 60.0,
    "timed_out_tasks": 1
  }
}
```

- `wall_s`：该阶段全部被计时任务耗时之和（任务级口径；**不等于**阶段墙钟中
  包含的排队/IO 等待，也不等于批次总墙钟）；
- `n_tasks`：该阶段计时任务数（**含**超时任务）；
- `mean_s` / `p50_s` / `p95_s` / `max_s`：逐任务耗时分布（秒，6 位小数）；
- `timed_out_tasks`：被调用方判定超时的任务数（由 hook 传入，见 §5）。
- **无任务**的阶段输出全 0 分布（`n_tasks=0` 且各统计量为 0），保证键集合稳定。
- 告警不进入 JSON：`build_postprocess_wall` 返回值是 `dict` 子类
  `PostprocessWallResult`，`json.dumps()` 只序列化阶段映射；阈值告警在
  `.warnings` 属性（供调用方 `logger.warning`），避免瞬时诊断与稳定指标混层。

## 3. 分位算法（纯 stdlib，numpy `linear` / R-7 同口径）

升序样本 `v[0..n-1]`、分位 `p∈[0,1]`：

```
rank = p * (n - 1)
lo   = floor(rank)
hi   = min(lo + 1, n - 1)
value = v[lo] + (rank - lo) * (v[hi] - v[lo])
```

- `n == 1`：直接返回唯一值；`n == 0`：返回 0.0（无任务分布口径）；
- 该口径与仓库既有 `experiments/bayesian_paired.py::_percentile_linear`（注释
  写明"与 numpy 默认 'linear' 方法同口径"）一致；本模块独立实现，避免跨模块
  import 依赖；
- 已知精确值示例：`[10,20,30,40]` → p50=25、p95=38.5；`[10,20,30]` →
  p50=20、p95=29；`[42]` → 42。

## 4. 阈值与告警

- 阈值 env：`AITESTER_POSTPROCESS_WARN_S`（**默认 600 秒**；由 Q-1 代登记 env
  门禁）。读取实现位于 `src/utils/env_utils.py::postprocess_warn_seconds`
  （Q-3 裁决方案 a：`check_env_budget.py` 扫描面为 `src/**/*.py` + `config.py`，
  `experiments/` 不计入；读取点放 src 使登记表不被判「未使用」而收缩）；
  `experiments/postprocess_wall.py::postprocess_warn_s` 委托调用。
- `postprocess_warn_s()`：读取并校验阈值；env 未设置/空串/非数值/NaN/inf/≤0
  时回退默认 600（坏 env 不得让观测层崩溃或静默关闭告警）。
- 判定：`wall_s > warn_s` 时产生一条 `warnings` 消息（等于阈值不告警），消息含
  阶段名、实测墙钟、阈值与 env 名；**模块不直接打日志**，由调用方
  `logger.warning`（保持库纯度，也便于测试/门禁接管）。

## 5. Hook 集成（已接入 run_benchmark，R-3，2026-10-18）

**状态：已接入。** `experiments/run_benchmark.py` 的逐基线批后处理块（mutation
scoring/detection + MDO 调用）已用 `StageTimer` 包住，并经三个小 helper 落盘
（`_run_postprocess_stage` / `_run_baseline_postprocess_with_wall` /
`_attach_postprocess_wall_to_summary`；默认调用路径逐字节等价，纯观测）。

**当前粒度 = `per_baseline`**：每个基线在每个阶段记一个 wall 样本（该基线该阶段
全部后处理调用总 wall），在批次 summary 中记录：

```json
{
  "postprocess_wall": {
    "mutation": {"wall_s": 1.1e-05, "n_tasks": 1, "mean_s": 1.1e-05,
                  "p50_s": 1.1e-05, "p95_s": 1.1e-05, "max_s": 1.1e-05,
                  "timed_out_tasks": 0},
    "mdo":      {"wall_s": 3e-06, "n_tasks": 1}
  },
  "postprocess_wall_granularity": "per_baseline"
}
```

- **字段总在**：`mutation_enabled=False`（默认）时 `postprocess_wall={}`（空映射，
  只包含实际执行的阶段；不产生空阶段键），`postprocess_wall_granularity` 仍为
  `"per_baseline"`；
- 阈值告警由 hook 逐条 `logger.warning`（阈值 `AITESTER_POSTPROCESS_WARN_S`，
  默认 600s，读取实现见 §4），JSON 内不含 warnings；
- 异常路径：阶段调用抛异常时仍先追加该阶段 wall 样本，随后原异常上抛——
  不吞异常、不改变重试/超时/判分逻辑；
- 更细粒度（逐任务/逐变异体）为后续可选扩展；当前不改 Q-3 模块 API。

集成代码形态（`run_benchmark.py` 现状）：

```python
# 批后处理收集器（R-3）：阶段名 → 每基线实测 wall 样本
postprocess_stage_durations: dict[str, list[float]] = {}

# 逐基线后处理（原三个调用的顺序/入参/日志不变，仅新增 wall 观测）
_run_baseline_postprocess_with_wall(
    bl_results,
    tasks,
    postprocess_stage_durations,
    mutation_enabled=mutation_enabled,
    mutation_max_mutants=MUTATION_MAX_MUTANTS,
    seed=seed,
)

# 批汇总：写入 summary 两键并对超阈值告警 logger.warning
_attach_postprocess_wall_to_summary(summary, postprocess_stage_durations)
```

## 6. 设计取舍与已知边界

- **零行为变化**：模块只做计时/聚合，不改任何后处理逻辑与判分字段；额外开销为
  每任务 2 次 `time.perf_counter()`（纳秒级）。
- **任务级口径**：`wall_s` 之和 ≠ 批次总墙钟（任务间串行/并行/IO 等待未计入）；
  需要总账时同时消费批次既有耗时字段。
- **超时语义**：超时任务的耗时应由调用方传 watchdog 截断值；模块不区分
  "计算超时"与"排队超时"，两者都计入 `timed_out_tasks` 与分布。
- **线程模型**：`StageTimer` 非线程安全（后处理 hook 单线程串行收集）；若未来
  并行收集，应按线程各建计时器再合并耗时列表。
- **阶段名登记**：`registered_stage_names()` 返回 `("mutation","m1","mdo","other")`；
  `build_postprocess_wall` 对未登记阶段名抛 `ValueError`（防 hook 拼写漂移让指标
  悄悄改名）；新增阶段需同步登记并更新本条文档。

## 7. 验证与测试

- 测试：`tests/test_postprocess_wall_metrics.py`（88 例，零网络/零 LLM/无 numpy）：
  计时器正常/异常/空任务/嵌套/装饰器、分位精确值（奇偶/单值/乱序/重复）、JSON
  形状与可序列化、阈值与 env 回退、全超时/无任务/数据不一致 fail-fast、hook
  集成样例。
- smoke 工件：`（工件已清除）`（构造数据
  的确定性 JSON 样例 + SHA256 清单，仅演示形状，不代表真实批次数字）。
- 接入测试（R-3）：`tests/test_run_benchmark_postprocess_hook.py`（23 例）：
  mutation 关闭零行为、三调用顺序/入参等价、每基线样本粒度、阈值告警、
  异常路径仍写样本且原异常上抛、summary 仅新增两键且 JSON 可序列化；
- 默认零行为变化证据（R-3）：以同一 fake 基线分别运行 **HEAD（接入前）** 与
  当前工作树的 `run_benchmark()`（examples 1 任务；provenance/耗时等易失字段
  归一化后比较）：mutation 关闭与开启两种模式的历史 summary 字段**完全相等**，
  差异仅为新增的 `postprocess_wall` / `postprocess_wall_granularity` 两键；
- 验收命令：`python -m pytest -q tests/test_postprocess_wall_metrics.py
  tests/test_run_benchmark_postprocess_hook.py`；`ruff check` / `mypy` 目标文件
  干净（run_benchmark 既有 mypy 错误数不新增）。
