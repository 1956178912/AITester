"""批后处理墙钟可观测模块（Q-3，2026-10-18）。

背景（O-2 实测教训）
--------------------
O-2 真实 LLM 验证批（同 cut / 同协议）两臂后处理墙钟出现异常波动：
control 臂 2102s → >2400s（撞 2400s watchdog）→ 2297s，**run-to-run 波动 ≥14%**；
但批次工件只有总墙钟，**没有逐阶段（mutation / M1 / MDO / other）耗时分布**，
无法判断波动来自哪个后处理阶段、是否单任务长尾、还是阶段级退化。本模块提供
零依赖、零行为变化的观测原语，供 `experiments/run_benchmark.py` 的批后处理
hook 消费（hook 由 Lead 在 Q-1 完成后按下方示例插入；本模块**不修改**
run_benchmark.py，避免同文件并发写入）。

模块 API（零第三方依赖；除纯标准库 `time` / `math` / `functools` / `contextlib` 外，仅 import 轻量叶子模块 `src.utils.env_utils`——用于让 env 读取点落在 ADR-0003 env 门禁扫描面内，见 :func:`postprocess_warn_s`）
--------------------------------------------------------------------------
1. :class:`StageTimer`：单阶段计时器（上下文管理器 / 装饰器 / 逐任务计时），
   记录本阶段总 wall、逐任务耗时列表、超时/异常任务计数；异常**不吞**（原样
   上抛，仅计数）。
2. :func:`build_postprocess_wall`：把 ``{stage: [逐任务耗时]}`` 聚合为稳定
   JSON 形状 ``{stage: {wall_s, n_tasks, mean_s, p50_s, p95_s, max_s,
   timed_out_tasks}}``；无任务 → 全 0 分布；返回 :class:`PostprocessWallResult`
   （dict 子类，JSON 序列化=阶段映射；``.warnings`` 列表供调用方
   ``logger.warning`` —— **本模块不直接打日志**）。
3. :func:`registered_stage_names`：登记阶段名常量（``mutation`` / ``m1`` /
   ``mdo`` / ``other``，供 hook 与测试引用；未登记阶段名会被拒绝）。
4. :func:`postprocess_warn_s`：读取 env ``AITESTER_POSTPROCESS_WARN_S``
   （默认 600s；Q-3 裁决后读取实现在 ``src/utils/env_utils.py::
   postprocess_warn_seconds``，本函数委托调用，使 env 门禁扫描面可见；
   本模块不改 ``check_env_budget.py`` / ``run_benchmark.py``）。

分位算法（纯 stdlib，与 numpy 默认 ``linear`` / R-7 同口径）
-----------------------------------------------------------
升序样本 ``v[0..n-1]``、分位 ``p∈[0,1]``：
``rank = p*(n-1)``，``lo=floor(rank)``、``hi=min(lo+1, n-1)``、
``v[lo] + (rank-lo)*(v[hi]-v[lo])``；``n==1`` 直接返回唯一值；``n==0`` 返回 0.0。
仓库内已有同口径实现：``experiments/bayesian_paired.py::_percentile_linear``
（本模块独立实现，避免跨模块 import 重依赖；两者算法一致）。

Hook 集成示例（run_benchmark 批后处理循环，3 行核心 + 1 行落盘）
----------------------------------------------------------------
```
from experiments.postprocess_wall import StageTimer, build_postprocess_wall, postprocess_warn_s

# 1) 每个后处理阶段各建一个计时器；逐任务耗时用 measure_task / record_task 记录
mdo_timer = StageTimer("mdo")
for task in tasks:
    with mdo_timer.measure_task(timed_out=task.timed_out):
        run_mdo_postprocess(task)          # 原后处理逻辑（计时零行为变化）

# 2) 聚合为稳定 JSON（warn_s 从 env AITESTER_POSTPROCESS_WARN_S 读，默认 600s）
wall = build_postprocess_wall(
    {timer.stage: timer.durations for timer in (mutation_timer, m1_timer, mdo_timer, other_timer)},
    timed_out={timer.stage: timer.timed_out_tasks for timer in (...同上...)},
    warn_s=postprocess_warn_s(),
)
for message in wall.warnings:               # 3) 阈值超限由调用方 logger.warning
    logger.warning("%s", message)
batch_report["postprocess_wall"] = wall     # 4) 写入批次 JSON 的 postprocess_wall 键
```
说明：``wall`` 是 dict 子类，``json.dump(batch_report)`` 直接得到
``"postprocess_wall": {stage: {...}}`` 稳定形状；``wall.warnings`` 只用于日志，
不进入 JSON（避免把瞬时诊断与稳定指标混在一起）。

设计取舍 / 已知边界
------------------
- **零行为变化**：模块只做计时与聚合（除 `src.utils.env_utils` 的纯标准库 env 读取外无内部
  依赖），不改变任何后处理逻辑/判分字段；
  每个阶段额外开销 = 每任务 2 次 ``perf_counter`` 调用（纳秒级）。
- **分位基于任务粒度**：``n_tasks`` 是"该阶段被计时的任务数"（含超时任务，
  超时任务的耗时应由调用方按 watchdog 截断值传入，避免把 watchdog 等待时间
  混入长尾——本模块如实统计传入值，不做截断）。
- **线程模型**：StageTimer 非线程安全（后处理 hook 在单线程串行收集）；
  若未来并行收集，应由调用方按线程各建计时器再合并列表。
- **跨阶段总 wall**：各阶段 ``wall_s`` 之和**不等于**批次总墙钟（任务间有
  串行/并行/IO 等待）；需要总账时同时消费批次既有耗时字段。
- 未登记阶段名一律 ``ValueError``（防止 hook 拼写漂移让指标悄悄改名）。
"""

from __future__ import annotations

import functools
import math
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from src.utils.env_utils import POSTPROCESS_WARN_ENV, postprocess_warn_seconds

#: 后处理阶段名（供 hook / 测试引用；新增阶段需同步登记并更新文档）。
_REGISTERED_STAGES: tuple[str, ...] = ("mutation", "m1", "mdo", "other")

#: 默认告警阈值（秒）：O-2 中 control 臂 >2400s 撞 watchdog；600s 为单阶段
#: 后处理"明显异常"的经验阈值（可按批次规模用 env 调大/调小）。
_DEFAULT_WARN_S: float = 600.0

#: 浮点输出保留位数（稳定 JSON：6 位小数 ≈ 微秒级，足够诊断且避免尾差抖动）。
_FLOAT_DIGITS = 6


def registered_stage_names() -> tuple[str, ...]:
    """返回登记的后处理阶段名（只读常量副本）。"""
    return _REGISTERED_STAGES


def _round(value: float) -> float:
    """稳定 JSON 用浮点舍入（6 位小数；负零归一为正零）。"""
    rounded = round(float(value), _FLOAT_DIGITS)
    return 0.0 if rounded == 0 else rounded


def _validate_duration(stage: str, value: Any) -> float:
    """校验单个任务耗时（有限、非负、非 bool），返回 float。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"阶段 {stage!r} 的任务耗时必须为数值，收到 {type(value).__name__}: {value!r}")
    duration = float(value)
    if not math.isfinite(duration) or duration < 0:
        raise ValueError(f"阶段 {stage!r} 的任务耗时必须为有限非负数，收到 {value!r}")
    return duration


def _validate_stage(stage: Any) -> str:
    """校验阶段名：非空字符串且在 :func:`registered_stage_names` 内。"""
    if not isinstance(stage, str):
        raise TypeError(f"阶段名必须为字符串，收到 {type(stage).__name__}: {stage!r}")
    if not stage.strip():
        raise ValueError(f"阶段名必须为非空字符串，收到 {stage!r}")
    name = stage.strip()
    if name not in _REGISTERED_STAGES:
        raise ValueError(f"未登记阶段名 {name!r}（已登记：{list(_REGISTERED_STAGES)}；新增阶段请同步登记）")
    return name


def _percentile_linear(sorted_values: list[float], p: float) -> float:
    """升序样本的线性插值分位（numpy 默认 ``linear`` / R-7 同口径）。

    Args:
        sorted_values: **已升序**的样本（调用方保证；空列表返回 0.0）。
        p: 分位（0.0–1.0）。

    Returns:
        分位值；空样本返回 0.0；单样本返回唯一值。
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = p * (len(sorted_values) - 1)
    lo = math.floor(rank)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = rank - lo
    return sorted_values[lo] + frac * (sorted_values[hi] - sorted_values[lo])


def _stats_from_durations(durations: list[float]) -> dict[str, float | int]:
    """把逐任务耗时列表聚合为分布字段（wall_s/mean/p50/p95/max/n_tasks）。"""
    n_tasks = len(durations)
    if n_tasks == 0:
        return {"wall_s": 0.0, "n_tasks": 0, "mean_s": 0.0, "p50_s": 0.0, "p95_s": 0.0, "max_s": 0.0}
    ordered = sorted(durations)
    return {
        "wall_s": _round(math.fsum(durations)),
        "n_tasks": n_tasks,
        "mean_s": _round(math.fsum(durations) / n_tasks),
        "p50_s": _round(_percentile_linear(ordered, 0.50)),
        "p95_s": _round(_percentile_linear(ordered, 0.95)),
        "max_s": _round(ordered[-1]),
    }


def postprocess_warn_s(default: float = _DEFAULT_WARN_S) -> float:
    """读取墙钟告警阈值 env ``AITESTER_POSTPROCESS_WARN_S``（默认 600s）。

    Q-3 裁决（2026-10-18，Lead 方案 a）：env **读取实现**放在
    ``src/utils/env_utils.py::postprocess_warn_seconds``（本函数委托调用）——
    ``scripts/gates/check_env_budget.py`` 的扫描面是 ``src/**/*.py`` +
    ``config.py``（``experiments/`` 刻意不计入产品开关面）；读取点留在实验模块
    会让登记表被判"未使用"而收缩移除。委托后门禁可见、登记表稳定。

    口径不变：未设置/空串/非数值/NaN/inf/≤0 → ``default``（坏 env 不得让
    观测层崩溃或静默关掉告警；解析失败不在此打日志，模块不直接打日志）。

    Args:
        default: env 未设置/不可用时的回退阈值（秒，正数）。

    Returns:
        生效的告警阈值（秒）。
    """
    return postprocess_warn_seconds(default)


class StageTimer:
    """单阶段计时器：总 wall + 逐任务耗时 + 超时/异常计数（异常不吞）。

    用法（上下文管理器 + 逐任务计时）::

        timer = StageTimer("mdo")
        with timer:                                  # 阶段总 wall
            for task in tasks:
                with timer.measure_task(timed_out=task.timed_out):
                    run_postprocess(task)            # 异常原样上抛，计时器只计数
        build_postprocess_wall({timer.stage: timer.durations},
                               timed_out={timer.stage: timer.timed_out_tasks})

    也可作装饰器（每次调用记为一个任务耗时）::

        @StageTimer("mutation").measure
        def postprocess_one(task): ...

    Attributes:
        stage: 阶段名。
        durations: 逐任务耗时列表（秒，按记录顺序）。
        timed_out_tasks: 被标记超时的任务数（``measure_task(timed_out=True)``
            或 ``record_task(..., timed_out=True)``）。
        exceptions: 计时范围内异常次数（含任务级与阶段级；异常仍会抛出）。
        wall_s: 所有 ``with`` 块累计 wall（秒；未进入过为 0.0）。

    线程模型：非线程安全（后处理 hook 单线程串行收集；并行收集请每线程一个实例）。
    """

    def __init__(self, stage: str, *, clock: Callable[[], float] | None = None) -> None:
        """初始化。

        Args:
            stage: 阶段名（非空；仅 :func:`build_postprocess_wall` 校验登记名，
                本类允许任意非空名以便局部子阶段计时）。
            clock: 可注入时钟（默认 ``time.perf_counter``；测试用假时钟）。
        """
        if not isinstance(stage, str):
            raise TypeError(f"阶段名必须为字符串，收到 {type(stage).__name__}: {stage!r}")
        if not stage.strip():
            raise ValueError(f"阶段名必须为非空字符串，收到 {stage!r}")
        self.stage = stage.strip()
        self._clock: Callable[[], float] = clock or time.perf_counter
        self._started_at: float | None = None
        self.durations: list[float] = []
        self.timed_out_tasks = 0
        self.exceptions = 0
        self.wall_s = 0.0

    # ── 上下文管理器：阶段总 wall ──────────────────────────────────────────

    def start(self) -> StageTimer:
        """开始计时（已开始则 RuntimeError，防止嵌套误用同一实例）。"""
        if self._started_at is not None:
            raise RuntimeError(f"StageTimer({self.stage!r}) 已在计时中：不支持同一实例重入")
        self._started_at = self._clock()
        return self

    def stop(self) -> float:
        """结束计时并累计 wall_s，返回本次 wall（未开始则 RuntimeError）。"""
        if self._started_at is None:
            raise RuntimeError(f"StageTimer({self.stage!r}) 未开始计时，无法 stop()")
        elapsed = max(0.0, float(self._clock() - self._started_at))
        self.wall_s += elapsed
        self._started_at = None
        return elapsed

    def __enter__(self) -> StageTimer:
        return self.start()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        """结束计时；异常只计数并原样上抛（返回 None ⇒ 绝不吞异常）。"""
        self.stop()
        if exc is not None:
            self.exceptions += 1

    # ── 逐任务计时 ────────────────────────────────────────────────────────

    def record_task(self, duration_s: float, *, timed_out: bool = False) -> None:
        """记录一个任务耗时（调用方已测好时长时用；校验有限非负）。

        Args:
            duration_s: 任务耗时（秒）。
            timed_out: 该任务是否被判定超时（计入 ``timed_out_tasks``）。
        """
        self.durations.append(_validate_duration(self.stage, duration_s))
        if timed_out:
            self.timed_out_tasks += 1

    @contextmanager
    def measure_task(self, *, timed_out: bool = False) -> Iterator[StageTimer]:
        """逐任务计时上下文（异常照常上抛并计数，耗时仍被记录）。"""
        started = self._clock()
        try:
            yield self
        except BaseException:
            self.exceptions += 1
            raise
        finally:
            self.record_task(max(0.0, float(self._clock() - started)), timed_out=timed_out)

    def measure(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """装饰器：把被装饰函数每次调用记为一个任务耗时（异常计数后上抛）。"""

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            started = self._clock()
            try:
                return func(*args, **kwargs)
            except BaseException:
                self.exceptions += 1
                raise
            finally:
                self.record_task(max(0.0, float(self._clock() - started)))

        return wrapper

    # ── 快照 ──────────────────────────────────────────────────────────────

    def stage_durations(self) -> list[float]:
        """逐任务耗时副本（防止调用方原地修改内部列表）。"""
        return list(self.durations)

    def timed_out_stage_map(self) -> dict[str, int]:
        """``{stage: timed_out_tasks}`` 便捷形式（直接传给 build_postprocess_wall）。"""
        return {self.stage: self.timed_out_tasks}

    def snapshot(self) -> dict[str, Any]:
        """计时器自检快照（供日志/测试；不参与批次 JSON 稳定形状）。"""
        return {
            "stage": self.stage,
            "wall_s": _round(self.wall_s),
            "n_tasks": len(self.durations),
            "timed_out_tasks": self.timed_out_tasks,
            "exceptions": self.exceptions,
        }


class PostprocessWallResult(dict):
    """``build_postprocess_wall`` 返回值：dict 子类（JSON 形状=阶段映射）。

    ``json.dumps(result)`` 只输出 ``{stage: {wall_s, ...}}`` 稳定形状；
    阈值告警放在 :attr:`warnings` 属性（供调用方 ``logger.warning``），
    不进入批次 JSON，避免瞬时诊断与稳定指标混层。
    """

    def __init__(
        self,
        stages: dict[str, dict[str, float | int]],
        warnings: list[str],
        warn_s: float,
    ) -> None:
        super().__init__(stages)
        self.warnings: list[str] = list(warnings)
        self.warn_s: float = float(warn_s)

    def to_json(self) -> dict[str, dict[str, float | int]]:
        """返回纯 dict 副本（等同上层 JSON 形状；便于显式落盘）。"""
        return dict(self)


def build_postprocess_wall(
    stages: Mapping[str, list[float]],
    timed_out: Mapping[str, int] | None = None,
    warn_s: float = _DEFAULT_WARN_S,
) -> PostprocessWallResult:
    """把逐阶段逐任务耗时聚合为稳定 JSON 形状 + 阈值告警。

    输出形状（每个输入阶段一项；阶段按输入顺序）::

        {"mdo": {"wall_s": 123.4, "n_tasks": 15, "mean_s": 8.2, "p50_s": 3.1,
                 "p95_s": 40.0, "max_s": 60.0, "timed_out_tasks": 1},
         "mutation": {...}}

    ``wall_s`` = 该阶段全部任务耗时之和（阶段总 wall 的**任务级**口径）；
    ``n_tasks`` 含超时任务；无任务阶段 → 全 0 分布；分位算法见模块 docstring
    （线性插值 R-7）。

    Args:
        stages: ``{stage_name: [逐任务耗时（秒）]}``；阶段名必须在
            :func:`registered_stage_names` 内（防 hook 拼写漂移）。
        timed_out: ``{stage: 已判定超时任务数}``（可选；缺省全 0）。
            负值/超过该阶段任务数 → ValueError（数据不一致不静默吞）。
        warn_s: 告警阈值（秒，有限正数；默认 600，通常传
            :func:`postprocess_warn_s` 读取 env）。

    Returns:
        :class:`PostprocessWallResult`：dict 子类，JSON 形状为上述稳定映射；
        ``.warnings`` 为超阈值阶段的消息列表（空列表表示无告警）。

    Raises:
        ValueError: 阶段名未登记/为空、耗时非法、timed_out 数据不一致、
            warn_s 非法。
    """
    if isinstance(warn_s, bool) or not isinstance(warn_s, (int, float)):
        raise TypeError(f"warn_s 必须为数值，收到 {type(warn_s).__name__}: {warn_s!r}")
    warn_value = float(warn_s)
    if not math.isfinite(warn_value) or warn_value <= 0:
        raise ValueError(f"warn_s 必须为有限正数，收到 {warn_s!r}")
    if not isinstance(stages, Mapping):
        raise TypeError(f"stages 必须为 {{stage: [逐任务耗时]}} 映射，收到 {type(stages).__name__}")

    timed_out_map: Mapping[str, int] = timed_out or {}
    unknown_timeout_stages = [str(key) for key in timed_out_map if str(key) not in {str(k) for k in stages}]
    if unknown_timeout_stages:
        raise ValueError(f"timed_out 含 stages 之外的阶段：{unknown_timeout_stages}")

    normalized: dict[str, list[float]] = {}
    for raw_stage, raw_durations in stages.items():
        stage = _validate_stage(raw_stage)
        if isinstance(raw_durations, (str, bytes, bytearray)) or not isinstance(raw_durations, (list, tuple)):
            raise TypeError(f"阶段 {stage!r} 的逐任务耗时必须为 list/tuple，收到 {type(raw_durations).__name__}")
        normalized[stage] = [_validate_duration(stage, value) for value in raw_durations]

    result_stages: dict[str, dict[str, float | int]] = {}
    warnings: list[str] = []
    for stage, durations in normalized.items():
        stats = _stats_from_durations(durations)
        raw_count = timed_out_map.get(stage, 0)
        if isinstance(raw_count, bool) or not isinstance(raw_count, int):
            raise TypeError(f"阶段 {stage!r} 的 timed_out_tasks 必须为整数，收到 {raw_count!r}")
        if raw_count < 0 or raw_count > stats["n_tasks"]:
            raise ValueError(f"阶段 {stage!r} 的 timed_out_tasks={raw_count} 与 n_tasks={stats['n_tasks']} 不一致")
        stats["timed_out_tasks"] = raw_count
        result_stages[stage] = stats
        wall_s = float(stats["wall_s"])
        if wall_s > warn_value:
            warnings.append(
                f"后处理阶段 {stage!r} 墙钟 {wall_s:.1f}s 超过阈值 {warn_value:.1f}s"
                f"（可能撞后处理 watchdog/后处理退化；建议拆分阶段或调大 watchdog 裕量；"
                f"阈值可用 {POSTPROCESS_WARN_ENV} 覆盖）"
            )
    return PostprocessWallResult(result_stages, warnings, warn_value)


__all__ = [
    "POSTPROCESS_WARN_ENV",
    "PostprocessWallResult",
    "StageTimer",
    "build_postprocess_wall",
    "postprocess_warn_s",
    "registered_stage_names",
]
