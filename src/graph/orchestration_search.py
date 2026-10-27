"""编排自动搜索（bandit）——P1-A 落地（ADR-0016 后续方向，BOAD 式自动配置发现）。

背景（ADR-0016）：完整多智能体编排臂 detection 净负贡献 −28pp，编排降级为
"可消融容器"；后续方向是用 BOAD（ICLR 2026，IBM Research）式 bandit 在容器内
**自动发现**编排配置——BOAD 在 SWE-bench Verified 上证明自动发现的层级智能体
（53.2%）优于手工设计（47.4%），关键机制是 hindsight credit assignment
（orchestrator 最终失败时，只要某 sub-agent 的贡献推进了问题解决仍给予奖励）。

本模块是该方向的 M1 实现骨架（规格见 spec-p1a-bandit 交付文档）：

1. **臂空间**：`ArmSpec` + `ARM_REGISTRY`——16 臂精选空间（ incumbent 复刻 +
   incumbent 逐组件消融 + 全拓扑协议叠加 + 下界锚点）；全因子上界 3072 臂
   （拓扑 4 × 协议门 8 × 增强器 32 × max_iterations 3），M1 精选约 1%。
2. **奖励信号**：bandit 唯一优化对象是 M1 detection_rate（gold 独立裁决的
   F2P 三段判定，口径逐位复用 `experiments/_m1_metrics.build_m1_task_metrics`）；
   成本（token/耗时）以预算硬顶 + champion 选拔约束进入，**不做 λ 标量化**。
3. **Hindsight credit**：`hindsight_credits` / `attribute_mechanisms`——基于
   真实 trace JSONL 字段的步骤级回顾信用与机制归因。**只进归因报告，绝不进
   UCB 臂选择**（防 reward hacking——ADR-0016 教训；`OrchestrationSearch`
   不引用信用函数，测试以源码检查锁定该不变量）。
4. **搜索算法**：`UCB1Bandit`——UCB1（bonus = c·sqrt(2·ln t / n_a)），纯
   stdlib；给定奖励历史完全确定（同 seed 同结果）。
5. **预算控制**：`SearchBudget`——eval / token 双硬顶，先到即停。
6. **主循环**：`OrchestrationSearch`——确定性 cell 分配（全局种子洗牌游标）、
   每 (arm, cell) 至多评估一次（零重复 LLM 成本）、串行执行前提。

设计纪律：
- 主开关 `ORCHESTRATION_SEARCH_ENABLE` 默认 false：关时本模块全部公共入口
  立即抛 `SearchDisabledError`，不触碰 os.environ、零 I/O（ADR-0003 默认关
  口径；测试锁定零行为变化）。
- 纯 stdlib（json/math/random/os/time/...）；统计阶段由驱动复用既有
  `experiments/statistical_analysis.py`（numpy/scipy 已在依赖清单）。
- 臂经 env 覆盖默认关开关（调用期读取，项目惯例）+ 拓扑经 `build_workflow()`
  显式传参（import 期常量不可经 env 改——run_plain_llm_baseline 已实证
  reload 无效，勿重蹈）。
"""

from __future__ import annotations

import copy
import inspect
import json
import logging
import math
import os
import random
import shutil
import tempfile
import threading
import time
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from src.utils.env_utils import env_flag

logger = logging.getLogger(__name__)


def _as_count_int(value: Any) -> int:
    """把 token_usage.as_dict() 的值保守转为 int 计数（非数值 / 布尔 → 0）。

    as_dict 的值域为混合类型（int | float | dict[str, int] 等），直接 int()
    在 mypy 下类型不合法（union-arg）、运行期对 dict 会抛错——本助手统一
    收窄："数值（非布尔）→ int；其余 → 0"（观测层保守口径，不臆测）。
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    return 0


# ─── 主开关与禁用错误 ────────────────────────────────────────────────────────


class SearchDisabledError(RuntimeError):
    """编排搜索主开关关闭时公共入口的拒绝执行错误（ADR-0003 默认关口径）。"""


def search_enabled() -> bool:
    """编排搜索主开关是否开启（调用期读 env，便于测试 monkeypatch 动态切换）。

    Returns:
        `ORCHESTRATION_SEARCH_ENABLE` ∈ {true, 1, on} 时为 True；默认 false。
    """
    return env_flag("ORCHESTRATION_SEARCH_ENABLE")


def _require_enabled() -> None:
    """主开关关闭时抛 `SearchDisabledError`（零副作用：不碰 env、不 I/O）。"""
    if not search_enabled():
        raise SearchDisabledError(
            "ORCHESTRATION_SEARCH_ENABLE 未开启（默认 false）——编排自动搜索为实验 harness 能力，"
            "显式设 true 后才允许执行；关闭时对库行为零变化（ADR-0003）"
        )


# ─── 已知臂 env 键（干净基线纪律 + 键名防拼写错误） ─────────────────────────
# 规格 §1.1 的 B/C 两层共 10 个 env 键（协议门 3 + 增强器 7，其中 SPEC 链
# 3 键一体）。max_iterations 不是 env 键（经 create_initial_state 注入），
# 拓扑（planner/debugger）不是 env 键（经 build_workflow 显式传参）。
ENV_DETECTION_FIRST = "DETECTION_FIRST_ENABLE"
ENV_SPECIFICITY_GATE = "DETECTION_SPECIFICITY_GATE_ENABLE"
ENV_RED_REGRESSION_GATE = "RED_REGRESSION_GATE_ENABLE"
ENV_ROUTE_STRUCTURED = "ROUTE_STRUCTURED_ENABLE"
ENV_BRANCH_COVERAGE = "BRANCH_COVERAGE_INJECT_ENABLE"
ENV_MUTATION_ADVISOR = "MUTATION_ADVISOR_ENABLE"
ENV_FL_SPECTRAL = "FL_SPECTRAL_ENABLE"
ENV_SPEC_IR = "SPEC_IR_ENABLE"
ENV_SPEC_IR_DSL = "SPEC_IR_DSL_ENABLE"
ENV_SPEC_ORACLE_EXEC = "SPEC_ORACLE_EXEC_ENABLE"

KNOWN_ARM_ENV_KEYS: tuple[str, ...] = (
    ENV_DETECTION_FIRST,
    ENV_SPECIFICITY_GATE,
    ENV_RED_REGRESSION_GATE,
    ENV_ROUTE_STRUCTURED,
    ENV_BRANCH_COVERAGE,
    ENV_MUTATION_ADVISOR,
    ENV_FL_SPECTRAL,
    ENV_SPEC_IR,
    ENV_SPEC_IR_DSL,
    ENV_SPEC_ORACLE_EXEC,
)

# SPEC 规约链：三开关一体——臂空间把它作为单一旋钮处理。三层在运行时各有
# 独立降级（nodes.py 的 DSL 重解析与 oracle 四源材料回退），但拆开后的臂
# 无法按「SPEC 链」归因，故登记表只接受同进同退
_SPEC_CHAIN_KEYS: tuple[str, ...] = (ENV_SPEC_IR, ENV_SPEC_IR_DSL, ENV_SPEC_ORACLE_EXEC)

# 臂 env 合法取值（项目开关读取口径：.lower() in ("true","1","on")；臂登记
# 统一用 "true"/"false" 字面量，与 _PROFILE_PRESETS 风格一致）
_TRUTHY = "true"
_FALSY = "false"


class ArmSpecError(ValueError):
    """臂定义非法（键名未知 / 依赖违反 / 拓扑与再生路由矛盾）。"""


@dataclass
class ArmSpec:
    """一条臂 = 一个编排配置（拓扑显式参 + env 覆盖 + 可选预算覆盖）。

    属性:
        arm_id: 臂标识（结果行 / 报告键）。
        planner: 是否启用 Planner 节点（`build_workflow(planner=)` 显式传参）。
        debugger: 是否启用 Debugger + PatchApplier 修复循环。
        env: 臂级开关覆盖（键 ⊆ `KNOWN_ARM_ENV_KEYS`，值 ∈ {"true"/"false"}）；
            未列出的键在干净基线下为 "false"（驱动职责，见
            `establish_clean_baseline`）。
        max_iterations: 修复迭代上限覆盖（None = 沿用 config.MAX_ITERATIONS；
            仅 debugger=True 时有意义——无修复循环时迭代恒 0）。
        allow_regeneration: 无 Debugger 拓扑下是否保留 executor → generator
            再生成路由（None = 派生：debugger 关闭时等于 DETECTION_FIRST 开启态；
            显式 True 要求 debugger=False——plain_llm_df 式拓扑）。

    Raises:
        ArmSpecError: 键名未知 / 取值非法 / SPEC 链拆开 / mutation_advisor 或
            fl_spectral 依赖 debugger / allow_regeneration 与 debugger 矛盾。
    """

    arm_id: str
    planner: bool
    debugger: bool
    env: dict[str, str] = field(default_factory=dict)
    max_iterations: int | None = None
    allow_regeneration: bool | None = None

    def __post_init__(self) -> None:
        if not self.arm_id or not self.arm_id.replace("_", "").isalnum():
            raise ArmSpecError(f"arm_id 非法（须为非空字母数字下划线）：{self.arm_id!r}")
        for key, value in self.env.items():
            if key not in KNOWN_ARM_ENV_KEYS:
                raise ArmSpecError(f"臂 {self.arm_id} 含未知 env 键 {key!r}（已知集合：{KNOWN_ARM_ENV_KEYS}）")
            if value not in (_TRUTHY, _FALSY):
                raise ArmSpecError(f"臂 {self.arm_id} 的 {key} 取值须为 'true'/'false'，得到 {value!r}")
        # SPEC 链一体性：三键同进同退；缺省键在干净基线下按 false 生效，
        # 故按生效值比较（只查显式键会放行「oracle 单开」这类效应拆链）
        effective_chain = {k: self.env.get(k, _FALSY) for k in _SPEC_CHAIN_KEYS}
        if len(set(effective_chain.values())) > 1:
            raise ArmSpecError(f"臂 {self.arm_id} 拆开了 SPEC 链（三开关须一体，缺省按 false）：{effective_chain}")
        # 依赖：mutation_advisor / fl_spectral 由 debugger 路径消费，无修复循环时惰性
        for dep_key in (ENV_MUTATION_ADVISOR, ENV_FL_SPECTRAL):
            if self.env.get(dep_key) == _TRUTHY and not self.debugger:
                raise ArmSpecError(
                    f"臂 {self.arm_id} 开启 {dep_key} 但 debugger=False（该开关由 debugger 路径消费，无修复循环时惰性）"
                )
        # 再生路由只存在于无 Debugger 拓扑（有 Debugger 时默认路由已含 regenerate）
        if self.allow_regeneration is True and self.debugger:
            raise ArmSpecError(
                f"臂 {self.arm_id} allow_regeneration=True 与 debugger=True 矛盾（再生路由仅无 Debugger 拓扑需要显式保留）"
            )

    @property
    def resolved_allow_regeneration(self) -> bool:
        """再生路由最终取值（显式值优先；None 时派生：无 Debugger ⇒ DETECTION_FIRST 开启态）。

        Returns:
            True = 无修复循环但保留 executor → generator 再生成路由
            （plain_llm_df 式拓扑）；False = executor 直通 END（plain_llm 式）。
        """
        if self.allow_regeneration is not None:
            return self.allow_regeneration
        return (not self.debugger) and self.env.get(ENV_DETECTION_FIRST) == _TRUTHY

    def to_dict(self) -> dict[str, Any]:
        """臂配置的可 JSON 序列化快照（入结果工件 provenance）。"""
        return {
            "arm_id": self.arm_id,
            "planner": self.planner,
            "debugger": self.debugger,
            "allow_regeneration": self.resolved_allow_regeneration,
            "max_iterations": self.max_iterations,
            "env": dict(self.env),
        }


# ─── 16 臂精选登记表（规格 §1.2） ────────────────────────────────────────────
# 选取原则：incumbent 复刻 + incumbent 逐组件消融 + 全拓扑协议叠加 + 下界锚点。
# 关键依据（spec-p1a-bandit 勘察）：R-P0-2 的 plain_llm_df 是在
# AITESTER_PROFILE=logic 下跑的——df 拓扑（planner=off, debugger=off）下 logic
# 档**实际生效**的开关只有 DETECTION_FIRST / DETECTION_SPECIFICITY_GATE /
# RED_REGRESSION_GATE / ROUTE_STRUCTURED / BRANCH_COVERAGE_INJECT（spec 链 /
# FL / mutation_advisor 在该拓扑惰性）。df_incumbent 按此逐位复刻，否则
# "超过 df" 的判据不可迁移到 Stage-2 确认。

ARM_REGISTRY: tuple[ArmSpec, ...] = (
    # ── 参照臂 ────────────────────────────────────────────────────────────
    ArmSpec(
        arm_id="df_incumbent",
        planner=False,
        debugger=False,
        env={
            ENV_DETECTION_FIRST: _TRUTHY,
            ENV_SPECIFICITY_GATE: _TRUTHY,
            ENV_RED_REGRESSION_GATE: _TRUTHY,
            ENV_ROUTE_STRUCTURED: _TRUTHY,
            ENV_BRANCH_COVERAGE: _TRUTHY,
        },
    ),
    ArmSpec(arm_id="full_default", planner=True, debugger=True),
    # ── incumbent 逐组件消融（df 拓扑） ────────────────────────────────────
    ArmSpec(
        arm_id="df_no_gates",
        planner=False,
        debugger=False,
        env={
            ENV_DETECTION_FIRST: _TRUTHY,
            ENV_ROUTE_STRUCTURED: _TRUTHY,
            ENV_BRANCH_COVERAGE: _TRUTHY,
        },
    ),
    ArmSpec(
        arm_id="df_no_structured",
        planner=False,
        debugger=False,
        env={
            ENV_DETECTION_FIRST: _TRUTHY,
            ENV_SPECIFICITY_GATE: _TRUTHY,
            ENV_RED_REGRESSION_GATE: _TRUTHY,
            ENV_BRANCH_COVERAGE: _TRUTHY,
        },
    ),
    ArmSpec(
        arm_id="df_no_branch",
        planner=False,
        debugger=False,
        env={
            ENV_DETECTION_FIRST: _TRUTHY,
            ENV_SPECIFICITY_GATE: _TRUTHY,
            ENV_RED_REGRESSION_GATE: _TRUTHY,
            ENV_ROUTE_STRUCTURED: _TRUTHY,
        },
    ),
    # ── 协议叠加到全拓扑（planner + debugger） ────────────────────────────
    ArmSpec(arm_id="full_df", planner=True, debugger=True, env={ENV_DETECTION_FIRST: _TRUTHY}),
    ArmSpec(
        arm_id="full_logic_equiv",
        planner=True,
        debugger=True,
        env={
            ENV_DETECTION_FIRST: _TRUTHY,
            ENV_SPECIFICITY_GATE: _TRUTHY,
            ENV_RED_REGRESSION_GATE: _TRUTHY,
            ENV_ROUTE_STRUCTURED: _TRUTHY,
            ENV_BRANCH_COVERAGE: _TRUTHY,
            ENV_FL_SPECTRAL: _TRUTHY,
            ENV_MUTATION_ADVISOR: _TRUTHY,
            ENV_SPEC_IR: _TRUTHY,
            ENV_SPEC_IR_DSL: _TRUTHY,
            ENV_SPEC_ORACLE_EXEC: _TRUTHY,
        },
    ),
    ArmSpec(
        arm_id="full_df_gates",
        planner=True,
        debugger=True,
        env={
            ENV_DETECTION_FIRST: _TRUTHY,
            ENV_SPECIFICITY_GATE: _TRUTHY,
            ENV_RED_REGRESSION_GATE: _TRUTHY,
            ENV_ROUTE_STRUCTURED: _TRUTHY,
            ENV_BRANCH_COVERAGE: _TRUTHY,
        },
    ),
    ArmSpec(
        arm_id="full_df_gates_mut",
        planner=True,
        debugger=True,
        env={
            ENV_DETECTION_FIRST: _TRUTHY,
            ENV_SPECIFICITY_GATE: _TRUTHY,
            ENV_RED_REGRESSION_GATE: _TRUTHY,
            ENV_ROUTE_STRUCTURED: _TRUTHY,
            ENV_BRANCH_COVERAGE: _TRUTHY,
            ENV_MUTATION_ADVISOR: _TRUTHY,
        },
    ),
    ArmSpec(
        arm_id="full_df_gates_fl",
        planner=True,
        debugger=True,
        env={
            ENV_DETECTION_FIRST: _TRUTHY,
            ENV_SPECIFICITY_GATE: _TRUTHY,
            ENV_RED_REGRESSION_GATE: _TRUTHY,
            ENV_ROUTE_STRUCTURED: _TRUTHY,
            ENV_BRANCH_COVERAGE: _TRUTHY,
            ENV_FL_SPECTRAL: _TRUTHY,
        },
    ),
    ArmSpec(
        arm_id="full_df_gates_spec",
        planner=True,
        debugger=True,
        env={
            ENV_DETECTION_FIRST: _TRUTHY,
            ENV_SPECIFICITY_GATE: _TRUTHY,
            ENV_RED_REGRESSION_GATE: _TRUTHY,
            ENV_ROUTE_STRUCTURED: _TRUTHY,
            ENV_BRANCH_COVERAGE: _TRUTHY,
            ENV_SPEC_IR: _TRUTHY,
            ENV_SPEC_IR_DSL: _TRUTHY,
            ENV_SPEC_ORACLE_EXEC: _TRUTHY,
        },
    ),
    # ── 预算旋钮（精简修复循环，省 token） ────────────────────────────────
    ArmSpec(
        arm_id="full_lean1",
        planner=True,
        debugger=True,
        env={
            ENV_DETECTION_FIRST: _TRUTHY,
            ENV_SPECIFICITY_GATE: _TRUTHY,
            ENV_RED_REGRESSION_GATE: _TRUTHY,
            ENV_ROUTE_STRUCTURED: _TRUTHY,
            ENV_BRANCH_COVERAGE: _TRUTHY,
        },
        max_iterations=1,
    ),
    ArmSpec(
        arm_id="full_lean2",
        planner=True,
        debugger=True,
        env={
            ENV_DETECTION_FIRST: _TRUTHY,
            ENV_SPECIFICITY_GATE: _TRUTHY,
            ENV_RED_REGRESSION_GATE: _TRUTHY,
            ENV_ROUTE_STRUCTURED: _TRUTHY,
            ENV_BRANCH_COVERAGE: _TRUTHY,
        },
        max_iterations=2,
    ),
    # ── 门无再生协议 / 全拓扑门无协议（分离门与协议效应） ─────────────────
    # gates_only_noregen 显式保留再生路由（allow_regeneration=True）但关闭
    # 检出优先协议——特异性门的 over_red → regenerate 路由仍可触发，用以
    # 分离"门效应"与"协议效应"；若随 DF 派生则退化為 plain_llm + 门观测。
    ArmSpec(
        arm_id="gates_only_noregen",
        planner=False,
        debugger=False,
        allow_regeneration=True,
        env={
            ENV_SPECIFICITY_GATE: _TRUTHY,
            ENV_RED_REGRESSION_GATE: _TRUTHY,
            ENV_ROUTE_STRUCTURED: _TRUTHY,
            ENV_BRANCH_COVERAGE: _TRUTHY,
        },
    ),
    ArmSpec(
        arm_id="full_only_gates",
        planner=True,
        debugger=True,
        env={
            ENV_SPECIFICITY_GATE: _TRUTHY,
            ENV_RED_REGRESSION_GATE: _TRUTHY,
            ENV_ROUTE_STRUCTURED: _TRUTHY,
            ENV_BRANCH_COVERAGE: _TRUTHY,
        },
    ),
    # ── 下界锚点（历史 plain_llm detection ≈ 1.5%） ───────────────────────
    ArmSpec(arm_id="plain_llm_floor", planner=False, debugger=False),
)

_INCUMBENT_ARM_ID = "df_incumbent"


def get_arm(arm_id: str) -> ArmSpec:
    """按 id 取臂（未找到抛 `ArmSpecError`）。

    Args:
        arm_id: 臂标识。

    Returns:
        ARM_REGISTRY 中对应臂。

    Raises:
        ArmSpecError: id 不在登记表。
    """
    for arm in ARM_REGISTRY:
        if arm.arm_id == arm_id:
            return arm
    raise ArmSpecError(f"未知臂 id {arm_id!r}（登记表：{[a.arm_id for a in ARM_REGISTRY]}）")


# ─── 臂级 env 上下文（串行前提；嵌套即 Bug） ─────────────────────────────────
# env 是进程全局：--parallel 多线程并发跑不同臂会互相污染（X1 线程级覆盖的
# 存在正是该问题的历史证据）。M1 驱动强制串行；本上下文管理器提供键级
# 保存/恢复 + 嵌套检测（嵌套臂 = 调用方 Bug，直接抛错而非静默串扰）。
_ARM_ENV_LOCAL = threading.local()


@contextmanager
def _apply_arm_env_cm(arm: ArmSpec) -> Iterator[None]:
    """臂 env 上下文管理器实体（进入时应用、退出时逐键恢复）。

    干净基线纪律：调用方须先经 `establish_clean_baseline()` 把全部已知臂键
    置 "false"——否则恢复会把 ambient 值（如 AITESTER_PROFILE=logic 注入的
    开关）带回后续臂的评估，造成 confounding。

    Raises:
        ArmSpecError: 嵌套应用（另一臂的 env 上下文尚未退出）。
    """
    if getattr(_ARM_ENV_LOCAL, "active", False):
        raise ArmSpecError("检测到嵌套 apply_arm_env——臂 env 为进程全局，串行评估前提下嵌套即调用方 Bug")
    saved: dict[str, str | None] = {key: os.environ.get(key) for key in arm.env}
    _ARM_ENV_LOCAL.active = True
    try:
        for key, value in arm.env.items():
            os.environ[key] = value
        yield
    finally:
        # 恢复逐键（含"原未设置"的清除）；变量名与上方应用循环区分，
        # 避免 mypy 对同名变量的 str / str|None 联合收窄冲突
        for saved_key, saved_value in saved.items():
            if saved_value is None:
                os.environ.pop(saved_key, None)
            else:
                os.environ[saved_key] = saved_value
        _ARM_ENV_LOCAL.active = False


def apply_arm_env(arm: ArmSpec) -> Any:
    """在上下文内应用臂的 env 覆盖，退出时逐键恢复（含"原未设置"的清除）。

    主开关校验在**调用期**完成（fail-fast：关时本函数直接抛
    `SearchDisabledError`，不返回上下文对象）。

    Args:
        arm: 臂配置（只读其 env 覆盖集）。

    Returns:
        可进入的上下文管理器（进入后 env 生效）。

    Raises:
        SearchDisabledError: 主开关关闭（本函数属搜索能力公共入口）。
    """
    _require_enabled()
    return _apply_arm_env_cm(arm)


def establish_clean_baseline() -> dict[str, str | None]:
    """把全部已知臂 env 键显式置 "false"（干净基线），返回原值快照。

    动机：操作者 shell 可能带 AITESTER_PROFILE=logic/scientific/safe——import
    期 setdefault 会注入臂未提及的开关（ confounding 有前科：ab1 批次
    FL_SPECTRAL_ENABLE=None 静默失效）。搜索启动时统一压到 false 后再按臂
    覆盖，使臂空间自洽（与 ambient profile 解耦）。

    Returns:
        原值快照 {key: value | None}——调用方须在 finally 中经
        `restore_env_snapshot(snapshot)` 恢复。
    """
    _require_enabled()
    snapshot: dict[str, str | None] = {}
    for key in KNOWN_ARM_ENV_KEYS:
        snapshot[key] = os.environ.get(key)
        os.environ[key] = _FALSY
    ambient_profile = os.getenv("AITESTER_PROFILE")
    if ambient_profile:
        logger.warning(
            "编排搜索干净基线：ambient AITESTER_PROFILE=%r 已把 %d 个已知臂开关压为 false（搜索与 ambient profile 解耦）",
            ambient_profile,
            len(KNOWN_ARM_ENV_KEYS),
        )
    return snapshot


def restore_env_snapshot(snapshot: Mapping[str, str | None]) -> None:
    """恢复 `establish_clean_baseline` 返回的原值快照（None = 清除该键）。"""
    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


# ─── Cell / CellResult（搜索的最小评估单元） ────────────────────────────────


@dataclass(frozen=True)
class Cell:
    """一个评估单元 = (任务, 种子)。

    属性:
        task_id: 数据集任务 id（中性化命名，跨种子同名是设计使然——种子分层
            拼接统计时加 s<seed>__ 前缀，口径同 R-P0-2 pooled 报告）。
        seed: 数据集生成种子（决定该任务的任务实例）。
        task: BenchmarkTask 对象（携带 instance_code / metadata 等；类型标注
            为 Any 以避免本模块对 dataset_loader 的 import 依赖）。
    """

    task_id: str
    seed: int
    task: Any = None


@dataclass
class CellResult:
    """单 (臂, cell) 评估结果（bandit 统计与报告行的数据载体）。

    属性:
        arm_id / task_id / seed: 评估坐标。
        detection: M1 detection_rate（0.0/1.0；None = 不可测——无 gold 材料 /
            无生成物 / 执行超时；None 不进臂统计但预算计数照记）。
        repair_rate / false_fix_rate: M1 另两项诚实指标（诊断 + champion 守卫）。
        total_tokens: 本 cell LLM token 总消耗（task_end 快照）。
        llm_calls: 本 cell LLM 调用次数。
        duration_s: 本 cell 墙钟耗时（秒）。
        trace_records: 本 cell 的 trace JSONL 记录列表（归因报告消费；文件
            追踪未启用时为空列表）。
    """

    arm_id: str
    task_id: str
    seed: int
    detection: float | None
    repair_rate: float | None = None
    false_fix_rate: float | None = None
    total_tokens: int = 0
    llm_calls: int = 0
    duration_s: float = 0.0
    trace_records: list[dict[str, Any]] = field(default_factory=list)

    def to_row(self) -> dict[str, Any]:
        """结果 JSON 的逐行记录（键集合同构， None 显式落盘不省略）。"""
        return {
            "arm_id": self.arm_id,
            "task_id": self.task_id,
            "seed": self.seed,
            "detection_rate": self.detection,
            "repair_rate": self.repair_rate,
            "false_fix_rate": self.false_fix_rate,
            "total_tokens": self.total_tokens,
            "llm_calls": self.llm_calls,
            "duration_s": self.duration_s,
        }


# ─── UCB1 bandit（纯 stdlib；给定奖励历史完全确定） ──────────────────────────
# 选型理由（规格 §4）：epsilon-greedy 在 240 evals 小预算下 ε 比例纯随机浪费
# 且无不确定性自适应；successive elimination 的早轮淘汰在二值奖励
# （p≈0.45、n≈15 → SE≈0.13）下误杀真最优的风险高；UCB1 乐观不确定性、无 ε
# 浪费、O(log T) 遗憾界，且给定奖励历史完全确定（满足同 seed 同结果）。


@dataclass
class ArmStats:
    """单臂统计（可测评估的二值奖励矩 + 不可测计数）。

    属性:
        n: 可测评估次数（detection 非 None）。
        total: 可测评估的 detection 之和。
        unmeasurable: 不可测评估次数（detection 为 None）。
    """

    n: int = 0
    total: float = 0.0
    unmeasurable: int = 0

    @property
    def mean(self) -> float:
        """可测评估的 detection 均值（无观测时 0.0）。"""
        return self.total / self.n if self.n else 0.0

    @property
    def se(self) -> float:
        """均值的标准误（二项近似 sqrt(p(1-p)/n)；无观测时 0.0）。"""
        if not self.n:
            return 0.0
        p = self.mean
        return math.sqrt(max(p * (1.0 - p), 0.0) / self.n)


class UCB1Bandit:
    """UCB1 bandit（bonus = c·sqrt(2·ln t / n_a)）。

    实现纪律：
    - 前 |A| 次 select 按臂序 round-robin（保证每臂 ≥1 观测）；
    - 之后每步选 mean + bonus 最大者；tie-break 取活跃序最小（确定性）；
    - `update(reward=None)` 记不可测：不进 n/mean（M1 口径 None 不进分母），
      但 `unmeasurable` 计数供上层排除结构性不可测臂；
    - `select()` 只返回活跃臂；全部排除时返回 None。
    """

    def __init__(self, arm_ids: Sequence[str], c: float = 1.0) -> None:
        """初始化 bandit。

        Args:
            arm_ids: 臂 id 序列（顺序即 round-robin 与 tie-break 顺序）。
            c: 探索常数（bonus = c·sqrt(2·ln t / n_a)）。
        """
        if not arm_ids:
            raise ArmSpecError("UCB1Bandit 需要非空臂集合")
        self._order: tuple[str, ...] = tuple(arm_ids)
        self._c = c
        self._stats: dict[str, ArmStats] = {arm_id: ArmStats() for arm_id in self._order}
        self._active: list[str] = list(self._order)
        self._pulls = 0

    @property
    def c(self) -> float:
        """探索常数 c。"""
        return self._c

    def select(self) -> str | None:
        """选择下一臂（UCB1 + round-robin 初始化 + 确定性 tie-break）。

        Returns:
            选中臂 id；无活跃臂时 None。
        """
        if not self._active:
            return None
        self._pulls += 1
        if self._pulls <= len(self._order):
            # 初始化轮：按臂序 round-robin（该臂此间不可能被排除——排除只发生
            # 在 update 之后，故活跃序与登记序一致）
            return self._order[self._pulls - 1]
        t = self._pulls
        best_id: str | None = None
        best_score = 0.0
        for arm_id in self._active:
            stats = self._stats[arm_id]
            if stats.n == 0:
                # 无可测观测的臂优先（理论上前 |A| 轮已覆盖；此为防御路径）
                return arm_id
            bonus = self._c * math.sqrt(2.0 * math.log(t) / stats.n)
            score = stats.mean + bonus
            if best_id is None or score > best_score:
                best_id, best_score = arm_id, score
        return best_id

    def update(self, arm_id: str, reward: float | None) -> None:
        """记录一次评估结果。

        Args:
            arm_id: 臂 id。
            reward: detection（0.0/1.0）；None = 不可测（只计 unmeasurable）。
        """
        stats = self._stats[arm_id]
        if reward is None:
            stats.unmeasurable += 1
            return
        stats.n += 1
        stats.total += float(reward)

    def exclude(self, arm_id: str) -> None:
        """把臂移出活跃池（统计保留供报告；如 cells 耗尽 / 结构性不可测）。"""
        if arm_id in self._active:
            self._active.remove(arm_id)

    def stats(self, arm_id: str) -> ArmStats:
        """单臂统计（只读视图）。"""
        return self._stats[arm_id]

    @property
    def active(self) -> tuple[str, ...]:
        """当前活跃臂（顺序 = 登记序）。"""
        return tuple(self._active)


# ─── 预算控制（eval / token 双硬顶，先到即停） ──────────────────────────────


@dataclass
class SearchBudget:
    """搜索预算（双顶）。

    属性:
        max_evals: 总评估次数硬顶（含不可测评估）。
        max_total_tokens: 总 token 消耗硬顶。
        evals_used / tokens_used: 已用量。
        stop_reason: 触顶原因（"max_evals" / "max_tokens"；None = 未触顶）。
    """

    max_evals: int
    max_total_tokens: int
    evals_used: int = 0
    tokens_used: int = 0
    stop_reason: str | None = None

    def can_continue(self) -> bool:
        """预算是否仍允许继续评估。"""
        return self.stop_reason is None

    def record(self, *, tokens: int) -> None:
        """记录一次评估的消耗（evals +1；tokens 累加；触顶即置 stop_reason）。

        Args:
            tokens: 本次评估的 token 消耗（memo/零成本路径传 0）。
        """
        self.evals_used += 1
        self.tokens_used += max(0, int(tokens))
        if self.stop_reason is None and self.evals_used >= self.max_evals:
            self.stop_reason = "max_evals"
        if self.stop_reason is None and self.tokens_used >= self.max_total_tokens:
            self.stop_reason = "max_tokens"

    def to_dict(self) -> dict[str, Any]:
        """预算状态快照（入结果工件）。"""
        return {
            "max_evals": self.max_evals,
            "max_total_tokens": self.max_total_tokens,
            "evals_used": self.evals_used,
            "tokens_used": self.tokens_used,
            "stop_reason": self.stop_reason,
        }


# ─── Hindsight credit assignment（BOAD 式；**仅归因，绝不进臂选择**） ────────
# 规格 §3。输入：单 (arm, task, seed) cell 的 trace JSONL 记录列表（按 ts 排序，
# 实测 schema：node/output/decision/duration_ms/iteration + task_end/token_usage）
# + M1 detection。BOAD 核心机制：orchestrator 终局失败（detection=0）时，凡
# 推进问题解决的步骤仍按 γ 折扣保留正信用；负向信号（补丁被拒）仅在成功分支
# 计罚（失败不二次惩罚）；detection=None → 全 0（不可测不误报）。

W_RED_WITNESS = 0.4  # S1: iteration==0 的 executor FAIL（红证人——缺陷代码变红）
W_COVERAGE_GAIN = 0.2  # S2: executor coverage 相对上一轮递增
W_PATCH_LANDED = 0.2  # S3: patch_applier written
W_REGEN_RESPOND = 0.1  # S5: generator regenerated（响应协议/门/顾问）
W_MUTATION_PROGRESS = 0.1  # S6: mutation_advisor injected
W_GATE_HIT = 0.1  # S7: _should_debug reason=specificity_gate_over_red（门①修正过红）
W_PATCH_REJECTED = 0.1  # S4: patch_applier rejected（负向；仅成功分支计罚）

# _should_debug.output.reason → 机制名（路由决策的机制归因表）
_REASON_TO_MECHANISM: dict[str, str] = {
    "detection_first_all_green": "detection_first",
    "specificity_gate_over_red": "specificity_gate",
    "test_gen_diagnosis": "route_structured",
    "test_gen_diagnosis_early": "route_structured",
    "review_test_defect": "debugger",
}


def _hindsight_gamma_default() -> float:
    """回顾信用折扣 γ 的默认值（调用期读 config 常量，便于测试 setattr 覆盖）。"""
    import config as _config

    return float(getattr(_config, "ORCHESTRATION_SEARCH_HINDSIGHT_GAMMA", 0.5))


def hindsight_credits(
    records: Sequence[Mapping[str, Any]], detection: float | None, gamma: float | None = None
) -> list[float]:
    """BOAD 式回顾信用：为每条 trace 记录计算步骤级信用 ∈ [-1, 1]。

    信号（全部来自实测 trace 字段，规格 §3.2）：
    - S1 red_witness：`node=="executor" and iteration==0 and decision=="FAIL"`
      （生成物让缺陷代码变红——检出潜势的直接证据）；
    - S2 coverage_gain：executor 的 `output.coverage` 高于上一 executor 事件
      （trace JSONL 无 coverage_delta 键，与 execution_trace 同口径自算）；
    - S3 patch_landed：`node=="patch_applier" and decision=="written"`；
    - S4 patch_rejected：`node=="patch_applier" and decision=="rejected"`；
    - S5 regen_responded：`node=="generator" and decision=="regenerated"`；
    - S6 mutation_progress：`node=="mutation_advisor" and decision=="injected"`；
    - S7 gate_hit：`node=="_should_debug" and output.reason=="specificity_gate_over_red"`。

    公式（规格 §3.3）：
        detection == 1.0 → credit = pos − neg（成功：按贡献计奖罚）
        detection == 0.0 → credit = γ · pos（hindsight：失败仍奖励推进步骤，
                              负向信号不二次惩罚）
        detection is None → credit = 0.0（不可测不误报）

    已知局限（写入归因报告）：抹红通道（red_then_green ∧ detection=0）中
    debugger/patch 步骤仍获 hindsight 正信用——步骤级公式看不到"终局抹红"，
    该判据由 final_state 级旗标在报告层单独陈述。

    Args:
        records: trace 记录列表（task_start / node / task_end 事件的 dict）。
        detection: M1 detection_rate（0.0/1.0/None）。
        gamma: 回顾折扣（None = 读 config.ORCHESTRATION_SEARCH_HINDSIGHT_GAMMA）。

    Returns:
        与 records 等长的信用列表（按下标对齐）。
    """
    if detection is None:
        return [0.0] * len(records)
    if gamma is None:
        gamma = _hindsight_gamma_default()
    prev_coverage: float | None = None
    step_credits: list[float] = []
    for record in records:
        pos = 0.0
        neg = 0.0
        node = record.get("node")
        decision = record.get("decision")
        output = record.get("output") or {}
        if node == "executor":
            if record.get("iteration") == 0 and decision == "FAIL":
                pos += W_RED_WITNESS  # S1
            coverage = output.get("coverage")
            if isinstance(coverage, (int, float)) and not isinstance(coverage, bool):
                if prev_coverage is not None and coverage > prev_coverage:
                    pos += W_COVERAGE_GAIN  # S2
                prev_coverage = float(coverage)
        elif node == "patch_applier":
            if decision == "written":
                pos += W_PATCH_LANDED  # S3
            elif decision == "rejected":
                neg += W_PATCH_REJECTED  # S4
        elif node == "generator" and decision == "regenerated":
            pos += W_REGEN_RESPOND  # S5
        elif node == "mutation_advisor" and decision == "injected":
            pos += W_MUTATION_PROGRESS  # S6
        elif node == "_should_debug" and output.get("reason") == "specificity_gate_over_red":
            pos += W_GATE_HIT  # S7
        step_credits.append((pos - neg) if detection == 1.0 else gamma * pos)
    return step_credits


def attribute_mechanisms(
    records: Sequence[Mapping[str, Any]], arm: ArmSpec, step_credits: Sequence[float]
) -> dict[str, float]:
    """机制归因：把步骤级信用聚合到臂旋钮（规格 §3.4）。

    映射规则：
    - `_should_debug` 的 `output.reason` 经 `_REASON_TO_MECHANISM` 映射
      （detection_first_all_green→detection_first；specificity_gate_over_red
      →specificity_gate；test_gen_diagnosis*→route_structured；
      review_test_defect→debugger）；
    - planner 事件→"planner"；patch_applier→"debugger"；mutation_advisor
      →"mutation_advisor"；executor 红证人（S1）→"detection_first"（臂开时）
      否则 "generator_base"；generator 首轮生成→"planner"（拓扑开时）否则
      "generator_base"；
    - **只聚合有非零信用的事件**：零信用事件（如未命中 S1-S7 信号的路由决策）
      不产生归因——其效果由被路由触发的动作事件（S5 再生成等）承载信用；
    - 只统计该机制在臂内实际激活的任务（调用方按臂过滤）。

    Args:
        records: trace 记录列表（与 step_credits 等长对齐）。
        arm: 臂配置（判定机制是否激活）。
        step_credits: `hindsight_credits` 产出的信用列表。

    Returns:
        {机制名: 信用合计}（无信用的机制不出现）。
    """
    totals: dict[str, float] = {}
    for record, credit in zip(records, step_credits, strict=False):
        if not credit:
            continue
        node = record.get("node")
        decision = record.get("decision")
        output = record.get("output") or {}
        mechanism: str | None = None
        if node == "_should_debug":
            mechanism = _REASON_TO_MECHANISM.get(str(output.get("reason") or ""))
        elif node == "planner":
            mechanism = "planner"
        elif node == "patch_applier":
            mechanism = "debugger"
        elif node == "mutation_advisor":
            mechanism = "mutation_advisor"
        elif node == "executor":
            if record.get("iteration") == 0 and decision == "FAIL":
                mechanism = "detection_first" if arm.env.get(ENV_DETECTION_FIRST) == _TRUTHY else "generator_base"
        elif node == "generator":
            mechanism = "planner" if arm.planner else "generator_base"
        if mechanism:
            totals[mechanism] = totals.get(mechanism, 0.0) + credit
    return totals


# ─── 真实 LLM 评估路径（代码级正确性保证；本任务不实跑） ────────────────────
# 与 experiments/run_benchmark.py run_single_task 同模式：tmpdir 物化实例 →
# create_initial_state（唯一构造点）→ gold 材料注入 → token reset → 任务级
# trace 会话 → build_workflow（拓扑显式传参）→ invoke → M1 指标 + token 快照
# → trace 收尾。差异仅在于：臂的 env 覆盖经 apply_arm_env 包裹 build+invoke，
# 且 max_iterations 可经臂覆盖。


def _derive_module_name(task_id: str) -> str:
    """从 task_id 末段派生模块名（与 run_single_task 同口径：连字符→下划线，截断 50）。

    `split("__")[-1]` 与 `rsplit("__", 1)[-1]` 等价（取最后一段），后者免去
    全量切分（PLC0207）。
    """
    raw_name = task_id.rsplit("__", 1)[-1]
    return raw_name.replace("-", "_")[:50]


def _trace_file_path(trace_dir: str, task_uuid: str) -> str:
    """复算 TraceSession 的文件名卫生化规则（`src/observability/trace.py` L156）。"""
    safe_task = "".join(c if c.isalnum() or c in "-_." else "_" for c in task_uuid) or "task"
    return os.path.join(trace_dir, f"{safe_task}.trace.jsonl")


def _read_trace_records(trace_dir: str | None, task_uuid: str) -> list[dict[str, Any]]:
    """读取单任务 trace JSONL（文件不存在/解析失败 → 空列表；观测层不阻断）。

    坏字节行（非 UTF-8）与坏 JSON 行同口径按行跳过并留痕行号：文本模式
    迭代器会在行内 try 之外解码，一行坏字节此前会拖垮整份 trace 读取。
    """
    if not trace_dir:
        return []
    path = _trace_file_path(trace_dir, task_uuid)
    records: list[dict[str, Any]] = []
    try:
        with open(path, "rb") as f:
            for line_no, raw_bytes in enumerate(f, start=1):
                try:
                    line = raw_bytes.decode("utf-8").strip()
                except UnicodeDecodeError as e:
                    logger.warning("trace 第 %d 行不是合法 UTF-8（跳过）: %s", line_no, e)
                    continue
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError:
        return []
    return records


def run_arm_cell(arm: ArmSpec, cell: Cell, *, trace_dir: str | None = None) -> CellResult:
    """真实评估路径：在 (臂, cell) 上跑一次完整工作流并计算 M1 指标。

    Args:
        arm: 臂配置（env 覆盖经 `apply_arm_env` 包裹 build + invoke）。
        cell: 评估单元（任务 + 种子）。
        trace_dir: 结构化追踪目录（None = 不读 trace 文件，records 为空列表）。

    Returns:
        CellResult（detection 三指标 + token/耗时 + trace 记录）。

    Raises:
        SearchDisabledError: 主开关关闭。
    """
    _require_enabled()
    # 延迟 import：重依赖（run_benchmark 链）仅在真实评估路径加载，保持本模块
    # 被测试/桩评估器引入时的轻量与零循环导入风险
    import config as _config
    from experiments._m1_metrics import build_m1_task_metrics
    from src.graph import token_usage
    from src.graph.state import create_initial_state
    from src.graph.tracing import end_task_trace, start_task_trace
    from src.graph.workflow import build_workflow

    task = cell.task
    task_id = str(getattr(task, "task_id", cell.task_id))
    tmp_dir = tempfile.mkdtemp(prefix=f"aitester_search_{arm.arm_id}_")
    try:
        # 物化实例文件（与 run_single_task 同口径：tmpdir 隔离，避免改原始文件）
        module_name = _derive_module_name(task_id)
        instance_file = os.path.join(tmp_dir, f"{module_name}.py")
        with open(instance_file, "w", encoding="utf-8") as f:
            f.write(str(task.instance_code))

        state = create_initial_state(
            task_uuid=task_id,
            target_file=instance_file,
            target_function=(task.metadata or {}).get("suggested_function"),
            module_name=module_name,
            target_code=str(task.instance_code),
            # 臂级 max_iterations 覆盖（None 沿用 config 单一事实源）
            max_iterations=arm.max_iterations if arm.max_iterations is not None else _config.MAX_ITERATIONS,
            problem_statement=getattr(task, "problem_statement", None),
            # 复杂度评分由工厂统一计算；metadata 提供数据集统计兜底
            task_metadata=task.metadata,
        )
        # AC2 门①材料管道：gold 修复代码注入（评估/门禁专用，禁入 agent prompt；
        # 无 gold 材料保持 None，门①自动降级 unavailable）
        try:
            from experiments._m1_metrics import _gold_fixed_code

            gold_fixed = _gold_fixed_code(task)
            if gold_fixed and gold_fixed.strip():
                state["gold_fixed_code"] = gold_fixed
        except Exception:
            logger.debug("gold 材料注入失败（保守跳过，门①降级）", exc_info=True)

        # 逐任务成本/token 统计复位（与 run_single_task 并置同口径）
        token_usage.reset()
        task_uuid = f"{task_id}_{arm.arm_id}_s{cell.seed}_{int(time.time())}"
        start_task_trace(
            task_uuid,
            task_meta={
                "dataset_task_id": task_id,
                "arm_id": arm.arm_id,
                "seed": cell.seed,
                "target_function": (task.metadata or {}).get("suggested_function"),
            },
        )
        start = time.time()
        try:
            with apply_arm_env(arm):
                graph = build_workflow(
                    planner=arm.planner,
                    debugger=arm.debugger,
                    allow_regeneration=arm.resolved_allow_regeneration,
                )
                final_state = graph.invoke(copy.deepcopy(state))
        except Exception:
            # 观测层收尾不因任务崩溃而丢失（与 run_single_task 失败分支同口径）
            end_task_trace(False, token_snapshot=token_usage.get_usage().as_dict())
            raise
        elapsed = time.time() - start
        usage = token_usage.get_usage().as_dict()
        end_task_trace(final_state.get("test_passed"), token_snapshot=usage)

        m1 = build_m1_task_metrics(task, final_state)
        return CellResult(
            arm_id=arm.arm_id,
            task_id=task_id,
            seed=cell.seed,
            detection=m1.get("detection_rate"),
            repair_rate=m1.get("repair_rate"),
            false_fix_rate=m1.get("false_fix_rate"),
            total_tokens=_as_count_int(usage.get("total_tokens")),
            llm_calls=_as_count_int(usage.get("llm_calls")),
            duration_s=round(elapsed, 3),
            trace_records=_read_trace_records(trace_dir, task_uuid),
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ─── 主循环（不引用 hindsight 信用函数——测试以源码检查锁定） ────────────────


class OrchestrationSearch:
    """编排自动搜索主循环（UCB1 + 双顶预算 + 确定性 cell 分配 + 零重复评估）。

    确定性纪律：
    - 串行评估（调用方职责；env 补丁为进程全局，并行即串扰）；
    - cell 顺序 = `random.Random(seed)` 对 cells 的洗牌（全局游标，不为每臂
      单独洗牌——避免 cell 混淆；UCB 自主分配拉取次数，覆盖期望均衡）；
    - 每 (arm, cell) 至多评估一次（played-set 扫描 + memo 安全网）；
    - tie-break 全部取登记序最小。

    Args:
        arms: 臂集合（顺序即 round-robin / tie-break 顺序）。
        cells: 评估单元集合（(task, seed) 对）。
        budget: 预算（双顶）。
        ucb_c: UCB1 探索常数。
        seed: 搜索种子（cell 洗牌）。
        evaluator: 评估器 `(arm, cell) -> CellResult`；None = 真实 LLM 路径
            `run_arm_cell`（测试传桩评估器，不触真实 LLM）。
        min_evals_per_arm: champion 选拔资格的最小可测评估数。
        max_unmeasurable: 单臂不可测累计上限（超过即 excluded_structurally）。
        trace_dir: 真实评估路径的 trace 目录（透传 `run_arm_cell`）。

    Raises:
        SearchDisabledError: 主开关关闭。
        ArmSpecError: 臂集合为空 / cell 集合为空 / 臂 id 重复。
    """

    def __init__(
        self,
        *,
        arms: Sequence[ArmSpec],
        cells: Sequence[Cell],
        budget: SearchBudget,
        ucb_c: float = 1.0,
        seed: int = 0,
        evaluator: Any = None,
        min_evals_per_arm: int = 5,
        max_unmeasurable: int = 5,
        trace_dir: str | None = None,
    ) -> None:
        _require_enabled()
        if not arms:
            raise ArmSpecError("OrchestrationSearch 需要非空臂集合")
        if not cells:
            raise ArmSpecError("OrchestrationSearch 需要非空 cell 集合")
        arm_ids = [arm.arm_id for arm in arms]
        if len(set(arm_ids)) != len(arm_ids):
            raise ArmSpecError(f"臂 id 重复：{arm_ids}")
        self._arms: dict[str, ArmSpec] = {arm.arm_id: arm for arm in arms}
        self._arm_order: tuple[str, ...] = tuple(arm_ids)
        self._cells: tuple[Cell, ...] = tuple(cells)
        self._budget = budget
        self._bandit = UCB1Bandit(arm_ids, c=ucb_c)
        self._seed = seed
        self._evaluator = evaluator if evaluator is not None else self._default_evaluator
        self._min_evals_per_arm = min_evals_per_arm
        self._max_unmeasurable = max_unmeasurable
        self._trace_dir = trace_dir
        # 确定性 cell 顺序：种子洗牌 + 全局游标
        self._cell_order: list[Cell] = list(self._cells)
        random.Random(seed).shuffle(self._cell_order)
        self._cell_cursor = 0
        # 每臂已评估 cell 集合（零重复评估的权威记录）与 memo 安全网
        self._played: dict[str, set[tuple[str, str, int]]] = {arm_id: set() for arm_id in arm_ids}
        self._memo: dict[tuple[str, str, int], CellResult] = {}
        # 过程记录
        self._pull_sequence: list[str] = []
        self._rows: list[dict[str, Any]] = []
        self._excluded_reason: dict[str, str] = {}
        # defaultdict：避免 dict.fromkeys 的共享可变默认值陷阱（C420 的正确修法）
        self._arm_tokens: defaultdict[str, list[int]] = defaultdict(list)
        self._arm_durations: defaultdict[str, list[float]] = defaultdict(list)
        self._arm_false_fix: defaultdict[str, list[float]] = defaultdict(list)
        # False 为不可变默认值，dict.fromkeys 安全（C420）
        self._arm_repair_any: dict[str, bool] = dict.fromkeys(arm_ids, False)

    # ── 内部辅助 ──────────────────────────────────────────────────────────

    def _default_evaluator(self, arm: ArmSpec, cell: Cell) -> CellResult:
        """真实 LLM 评估路径（未注入 evaluator 时）。"""
        return run_arm_cell(arm, cell, trace_dir=self._trace_dir)

    @staticmethod
    def _cell_key(arm_id: str, cell: Cell) -> tuple[str, str, int]:
        """(臂, cell) 复合键。"""
        return (arm_id, cell.task_id, cell.seed)

    def _next_fresh_cell(self, arm_id: str) -> Cell | None:
        """从全局游标取下一个该臂未评估的 cell（至多扫描一轮；None = 臂已耗尽）。

        设计意图（规格 §4）：全局游标循环取用，不为每臂单独洗牌——UCB 自主
        分配拉取次数，cell 覆盖在期望上均衡；扫描跳过已评估 cell 保证每次
        新鲜拉取都是新信息（memo 命中仅作安全网）。
        """
        played = self._played[arm_id]
        for _ in range(len(self._cell_order)):
            cell = self._cell_order[self._cell_cursor % len(self._cell_order)]
            self._cell_cursor += 1
            if self._cell_key(arm_id, cell) not in played:
                played.add(self._cell_key(arm_id, cell))
                return cell
        return None

    def _exclude(self, arm_id: str, reason: str) -> None:
        """排除臂（活跃池移除 + 原因记录）。"""
        if arm_id not in self._excluded_reason:
            self._excluded_reason[arm_id] = reason
            self._bandit.exclude(arm_id)
            logger.info("编排搜索：臂 %s 退出活跃池（%s）", arm_id, reason)

    # ── 主循环 ───────────────────────────────────────────────────────────

    def run(self) -> dict[str, Any]:
        """执行搜索（预算耗尽 / 全部臂退出时停止）。

        Returns:
            搜索报告 dict（`build_search_report` 产物；含逐臂统计、拉取序列、
            逐行结果、champion 选拔与预算状态）。
        """
        while self._budget.can_continue():
            arm_id = self._bandit.select()
            if arm_id is None:
                # 全部臂退出活跃池（cells 耗尽 / 结构性不可测）——非预算触顶的
                # 自然停止，显式记录原因供报告区分
                self._budget.stop_reason = "all_arms_excluded"
                logger.info("编排搜索：全部臂已退出活跃池，停止")
                break
            arm = self._arms[arm_id]
            cell = self._next_fresh_cell(arm_id)
            if cell is None:
                self._exclude(arm_id, "cells_exhausted")
                continue
            key = self._cell_key(arm_id, cell)
            result = self._memo.get(key)
            # 直接以 `result is None` 分支（而非中间 fresh 布尔量）——mypy 可据此
            # 收窄下方对 result 的访问（union-attr 消除），语义与 fresh 判据逐字一致
            if result is None:
                result = self._evaluator(arm, cell)
                self._memo[key] = result
                self._budget.record(tokens=result.total_tokens)
                self._arm_tokens[arm_id].append(result.total_tokens)
                self._arm_durations[arm_id].append(result.duration_s)
                if result.false_fix_rate is not None:
                    self._arm_false_fix[arm_id].append(float(result.false_fix_rate))
                if result.repair_rate is not None and result.repair_rate > 0.0:
                    self._arm_repair_any[arm_id] = True
            else:
                # 安全网路径：played-set 扫描下不应发生；若发生（如外部直接调
                # evaluator）计一次拉取、零 token 成本，保证循环必然终止
                logger.warning("编排搜索：memo 命中 (arm=%s, cell=%s)——重复拉取记零成本", arm_id, cell.task_id)
                self._budget.record(tokens=0)
            self._pull_sequence.append(arm_id)
            self._rows.append(result.to_row())
            self._bandit.update(arm_id, result.detection)
            if result.detection is None and self._bandit.stats(arm_id).unmeasurable > self._max_unmeasurable:
                self._exclude(arm_id, "unmeasurable_exceeded")
            if len(self._played[arm_id]) >= len(self._cells):
                self._exclude(arm_id, "cells_exhausted")
        return build_search_report(
            arm_order=self._arm_order,
            arms=self._arms,
            bandit=self._bandit,
            budget=self._budget,
            excluded_reason=self._excluded_reason,
            arm_tokens=self._arm_tokens,
            arm_durations=self._arm_durations,
            arm_false_fix=self._arm_false_fix,
            arm_repair_any=self._arm_repair_any,
            rows=self._rows,
            pull_sequence=self._pull_sequence,
            seed=self._seed,
            min_evals_per_arm=self._min_evals_per_arm,
            max_unmeasurable=self._max_unmeasurable,
            n_cells=len({(cell.task_id, cell.seed) for cell in self._cells}),
        )


# ─── 报告与 champion 选拔 ───────────────────────────────────────────────────


def _mean(values: Sequence[float]) -> float:
    """均值（空序列 0.0）。"""
    return sum(values) / len(values) if values else 0.0


def select_champion(
    arm_stats: Mapping[str, Mapping[str, Any]],
    *,
    incumbent_arm_id: str = _INCUMBENT_ARM_ID,
    min_evals: int = 5,
    max_token_ratio: float = 2.0,
    max_false_fix: float = 0.5,
) -> tuple[str | None, str]:
    """champion 选拔（规格 §8.1）。

    规则：
    1. incumbent（df_incumbent）须可测评估 ≥ min_evals，否则无从比较；
    2. 候选臂须可测评估 ≥ min_evals **且 mean detection 严格优于 incumbent**
       ——搜索的命题是"自动发现优于手工设计"，打平/更差均为阴性结果；
    3. 约束：mean tokens/任务 ≤ incumbent × max_token_ratio（默认 2×）且
       mean false_fix ≤ max_false_fix（默认 0.5，防"刷 passed"配置）；
    4. 过约束的臂中 mean detection 最大者（tie-break = 登记序，dict 插入序）。

    Args:
        arm_stats: {arm_id: 统计 dict}（`build_search_report` 的 arm_stats）。
        incumbent_arm_id: incumbent 臂 id。
        min_evals: 最小可测评估数。
        max_token_ratio: token 成本约束（相对 incumbent 均值的倍数）。
        max_false_fix: 假修复率守卫上限。

    Returns:
        (champion arm_id 或 None, 原因说明)——None 即阴性结果（按 ADR-0016
        口径仍可发表）。
    """
    incumbent = arm_stats.get(incumbent_arm_id)
    if incumbent is None or int(incumbent.get("n_measurable", 0)) < min_evals:
        return None, f"incumbent 臂 {incumbent_arm_id} 不可用（可测评估 < {min_evals}）——无从比较"
    eligible = [aid for aid, s in arm_stats.items() if int(s.get("n_measurable", 0)) >= min_evals]
    if not eligible:
        return None, f"无臂达到最小可测评估数 {min_evals}——阴性结果（证据不足，不可主张）"
    inc_detection = float(incumbent.get("mean_detection", 0.0))
    inc_tokens = float(incumbent.get("mean_tokens", 0.0))
    # 严格优于 incumbent：打平/更差 = 阴性（搜索命题是"自动发现优于手工设计"）
    better = [aid for aid in eligible if float(arm_stats[aid].get("mean_detection", 0.0)) > inc_detection]
    if not better:
        return None, "无臂 detection 严格优于 incumbent——阴性结果（按 ADR-0016 可发表）"

    def _passes_constraints(stats: Mapping[str, Any]) -> bool:
        token_ok = inc_tokens <= 0.0 or float(stats.get("mean_tokens", 0.0)) <= inc_tokens * max_token_ratio
        false_fix_ok = float(stats.get("mean_false_fix", 0.0)) <= max_false_fix
        return token_ok and false_fix_ok

    constrained = [aid for aid in better if _passes_constraints(arm_stats[aid])]
    if not constrained:
        return (
            None,
            "有臂 detection 更优但未过成本/假修复约束（token > 2× incumbent 或 false_fix > 0.5）——阴性结果（按 ADR-0016 可发表）",
        )
    champion = max(constrained, key=lambda aid: float(arm_stats[aid].get("mean_detection", 0.0)))
    return champion, f"champion={champion}（mean_detection={arm_stats[champion].get('mean_detection'):.4f}）"


def build_search_report(
    *,
    arm_order: Sequence[str],
    arms: Mapping[str, ArmSpec],
    bandit: UCB1Bandit,
    budget: SearchBudget,
    excluded_reason: Mapping[str, str],
    arm_tokens: Mapping[str, Sequence[int]],
    arm_durations: Mapping[str, Sequence[float]],
    arm_false_fix: Mapping[str, Sequence[float]],
    arm_repair_any: Mapping[str, bool],
    rows: Sequence[Mapping[str, Any]],
    pull_sequence: Sequence[str],
    seed: int,
    min_evals_per_arm: int,
    max_unmeasurable: int,
    n_cells: int,
) -> dict[str, Any]:
    """汇总搜索报告（结果 JSON 的直接载体）。

    Args:
        arm_order: 臂登记序（报告键顺序 = 登记序，保证确定性）。
        arms: {arm_id: ArmSpec}。
        bandit: UCB1Bandit（读统计）。
        budget: 预算状态。
        excluded_reason: {arm_id: 退出原因}。
        arm_tokens / arm_durations / arm_false_fix / arm_repair_any: 逐臂成本
            与诊断指标累计（仅新鲜评估）。
        rows: 逐 (臂, cell) 结果行。
        pull_sequence: 拉取序列（复现/审计用）。
        seed: 搜索种子。
        min_evals_per_arm: champion 资格门槛。
        max_unmeasurable: 单臂不可测累计上限（超过即退出 UCB 池）。
        n_cells: 设计集唯一 cell 数（(task, seed) 去重；与预算/提前停止无关）。

    Returns:
        报告 dict（schema = "orchestration_search_v1"；`config.n_cells` 是设计集
        分母，`coverage.cells_observed` 是本次实际触达的 distinct cell 数）。
    """
    arm_stats: dict[str, dict[str, Any]] = {}
    for arm_id in arm_order:
        stats = bandit.stats(arm_id)
        tokens = list(arm_tokens.get(arm_id, ()))
        arm_stats[arm_id] = {
            "n_measurable": stats.n,
            "unmeasurable": stats.unmeasurable,
            "excluded_reason": excluded_reason.get(arm_id),
            "mean_detection": round(stats.mean, 6),
            "se_detection": round(stats.se, 6),
            "mean_tokens": round(_mean(tokens), 3),
            "mean_duration_s": round(_mean(list(arm_durations.get(arm_id, ()))), 3),
            "mean_false_fix": round(_mean(list(arm_false_fix.get(arm_id, ()))), 6),
            "repair_any": bool(arm_repair_any.get(arm_id, False)),
        }
    champion, champion_reason = select_champion(arm_stats, min_evals=min_evals_per_arm)
    cells_observed = len({(str(r.get("task_id")), int(r.get("seed", 0))) for r in rows})
    return {
        "schema": "orchestration_search_v1",
        "config": {
            "ucb_c": bandit.c,
            "seed": seed,
            "min_evals_per_arm": min_evals_per_arm,
            "max_unmeasurable": max_unmeasurable,
            "n_arms": len(arm_order),
            "n_cells": n_cells,
        },
        "arms": {arm_id: arms[arm_id].to_dict() for arm_id in arm_order},
        "arm_stats": arm_stats,
        "budget": budget.to_dict(),
        "coverage": {"cells_observed": cells_observed},
        "champion": champion,
        "champion_reason": champion_reason,
        "pull_sequence": list(pull_sequence),
        "rows": list(rows),
    }


def assert_no_credit_coupling() -> None:
    """不变量自检：`OrchestrationSearch` 源码不得引用 hindsight 信用函数。

    BOAD 的 credit 是归因诊断信号；一旦进入臂选择即构成 reward hacking
    （ADR-0016 教训：自指指标刷高分）。本函数以源码文本检查锁定该边界，
    供测试与 Code Review 调用。
    """
    source = inspect.getsource(OrchestrationSearch)
    for banned in ("hindsight", "credit", "attribute_mechanisms"):
        assert banned not in source, f"OrchestrationSearch 引用禁用的信用符号 {banned!r}（reward hacking 风险）"


__all__ = [
    "ARM_REGISTRY",
    "KNOWN_ARM_ENV_KEYS",
    "ArmSpec",
    "ArmSpecError",
    "ArmStats",
    "Cell",
    "CellResult",
    "OrchestrationSearch",
    "SearchBudget",
    "SearchDisabledError",
    "UCB1Bandit",
    "apply_arm_env",
    "assert_no_credit_coupling",
    "attribute_mechanisms",
    "establish_clean_baseline",
    "get_arm",
    "hindsight_credits",
    "restore_env_snapshot",
    "run_arm_cell",
    "search_enabled",
    "select_champion",
]
