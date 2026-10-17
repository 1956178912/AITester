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

## 5. Hook 集成（run_benchmark 批后处理，3 行核心 + 1 行落盘）

集成 hook 由 Lead 在 Q-1 完成后插入 `experiments/run_benchmark.py`；本模块不改
run_benchmark.py（避免与 Q-1 同文件并发写入）。插入点：批次后处理中逐任务执行
mutation / M1 / MDO 的循环处（每阶段一个 `StageTimer`）。

```python
from experiments.postprocess_wall import StageTimer, build_postprocess_wall, postprocess_warn_s

# 1) 每个后处理阶段各建一个计时器；逐任务耗时用 measure_task / record_task 记录
mdo_timer = StageTimer("mdo")
for task in tasks:
    with mdo_timer.measure_task(timed_out=task.timed_out):
        run_mdo_postprocess(task)  # 原后处理逻辑（计时零行为变化）

# 2) 聚合为稳定 JSON（warn_s 从 env AITESTER_POSTPROCESS_WARN_S 读，默认 600s）
wall = build_postprocess_wall(
    {timer.stage: timer.durations for timer in (mutation_timer, m1_timer, mdo_timer, other_timer)},
    timed_out={timer.stage: timer.timed_out_tasks for timer in (mutation_timer, m1_timer, mdo_timer, other_timer)},
    warn_s=postprocess_warn_s(),
)
for message in wall.warnings:  # 3) 阈值超限由调用方 logger.warning
    logger.warning("%s", message)
batch_report["postprocess_wall"] = wall  # 4) 写入批次 JSON 的 postprocess_wall 键
```

- `StageTimer` 同时支持 `with timer:`（阶段总 wall）、`with timer.measure_task():`
  （逐任务耗时）、`timer.record_task(duration, timed_out=...)`（调用方已测好时长）
  与 `@timer.measure` 装饰器（单函数调用记为一个任务）；
- 异常**不吞**：计时范围内异常只计数（`timer.exceptions`）并原样上抛；
- `timed_out_tasks` 由调用方传入已判定集合（watchdog 截断值本身即为该任务耗时，
  模块不做二次截断，按传入值如实统计）。

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
- smoke 工件：`experiments/results/q_round_postprocess_wall_20261018/`（构造数据
  的确定性 JSON 样例 + SHA256 清单，仅演示形状，不代表真实批次数字）。
- 验收命令：`python -m pytest -q tests/test_postprocess_wall_metrics.py`；
  `ruff check` / `mypy` 目标文件干净。
