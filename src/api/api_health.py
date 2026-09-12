"""
API 节点健康状态与轮换配置数据模型。

从 api_manager.py 拆分而来（代码可维护性优化）：本模块承载 API 健康节点的
状态机（熔断器三态 / 成功率统计 / 滑动窗口响应时间）与轮换策略、管理器配置
等纯数据模型；APIManager 路由与故障转移逻辑保留在原模块，通过
`from .api_health import ...` 复用本模块类型，两者职责分离。
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from config import LLMConfig

logger = logging.getLogger(__name__)


class RotationStrategy(Enum):
    """轮换策略枚举"""

    ROUND_ROBIN = "round_robin"  # 轮询
    WEIGHTED_RANDOM = "weighted_random"  # 加权随机
    HEALTH_BASED = "health_based"  # 健康感知（优先健康节点）
    FASTEST_FIRST = "fastest_first"  # 响应最快优先（针对大规模节点池优化）
    COST_AWARE = "cost_aware"  # 成本感知（3.4：故障转移时避免全量切到昂贵 provider）


# 成本告警阈值（3.4，默认 2.0）：故障转移后若实际流量落在 cost_weight >= 该值的
# 昂贵 provider 上，记 WARNING（让实验分析/监控能捕获"配额故障把流量全切
# 到贵模型"的成本风险）。取值来源：经验值 2.0，即比基准贵 2 倍以上即告警。
# 3.2 调优：可按实际实验中的 Provider 成本分布经 APIManagerConfig.cost_alert_threshold
# 覆盖（阈值过低导致过多误报时上调；成本敏感度高时下调），无需改代码。
_COST_ALERT_THRESHOLD = 2.0


@dataclass
class APIHealth:
    """单个 API 节点的健康状态"""

    config: LLMConfig
    is_healthy: bool = True
    consecutive_failures: int = 0
    # 连续失败达到该阈值即标记不健康（原 APIManagerConfig.max_consecutive_failures
    # 幽灵配置：定义了却从未被 mark_failure 消费，此处接线，默认 3 保持历史行为）
    max_consecutive_failures: int = 3
    total_requests: int = 0
    success_count: int = 0
    error_count: int = 0
    last_response_time_ms: float = 0.0
    last_check_time: float = 0.0
    rate_limit_remaining: int = 0
    # 成本权重（3.4 成本感知路由）：相对成本倍数（1.0=基准，越大越贵）。
    # 故障转移到备用节点时用于避免全量切到昂贵 provider；默认 1.0 表示
    # 未配置成本信息时保持历史行为（成本维度不参与排序）。
    cost_weight: float = 1.0
    # 熔断冷却期截止时间戳（4.1 熔断器）：连续失败达到 max_consecutive_failures
    # 后，节点被"熔断"，在冷却期内即使健康检查线程翻回 is_healthy=True 也
    # 继续被路由层跳过，避免把流量重新打回已知不可用的 provider（浪费
    # 时间与 token）。使用 monotonic 时钟，不受系统时间回拨影响；
    # 默认 0.0 表示当前无熔断。
    circuit_open_until: float = 0.0
    # 熔断冷却时长（秒）：mark_failure 触发熔断时写入 circuit_open_until，
    # 默认 60.0 保持经验值（死 provider 通常 1-2 分钟内恢复或彻底失效）。
    # 经 APIManagerConfig.circuit_cooldown_seconds 在注册节点时注入。
    circuit_cooldown_seconds: float = 60.0
    # 4.2 半开探测失败的惩罚时长上限（秒）：失败时重新打开的冷却 =
    # min(circuit_cooldown_seconds / 2.0, 本字段)，默认 30s（4.1 默认冷却
    # 60s 的一半），防止 provider 彻底宕机时冷却期越缩越短。
    # 经 APIManagerConfig.half_open_probe_penalty_cap_seconds 在注册节点时注入。
    half_open_probe_penalty_cap_seconds: float = 30.0
    # 滑动窗口记录最近 N 次响应时间（用于计算平均值）
    _response_times: deque[float] = field(default_factory=lambda: deque(maxlen=10))

    @property
    def in_circuit_open(self) -> bool:
        """当前是否处于熔断冷却期（monotonic 时钟判定）。

        4.2：冷却已到期但半开探测尚未完成时（circuit_open_until > 0 且
        monotonic 已越过该时间点）返回 False——路由放行该节点作为"半开"
        探测请求；探测结果由 _probe_circuit_half_open 消费（成功闭合 /
        失败重新开半程冷却）。
        """
        if self.circuit_open_until <= 0.0:
            return False
        return time.monotonic() < self.circuit_open_until

    @property
    def in_circuit_half_open(self) -> bool:
        """4.2：当前是否处于半开探测窗口（冷却已到期、探测尚未完成）。

        窗口内该节点仍可被路由选中（in_circuit_open 为 False），但仅
        承载探测请求；_probe_circuit_half_open 在发起真实请求前调用，
        根据探测成功与否将状态推回"熔断中"或"闭合"。
        """
        if self.circuit_open_until <= 0.0:
            return False
        return time.monotonic() >= self.circuit_open_until

    def _probe_circuit_half_open(self, probe_succeeded: bool) -> None:
        """4.2：消费半开探测结果（在发起/结束真实请求前后调用）。

        Args:
            probe_succeeded: 本次半开探测请求是否成功。

        行为：
        - 不在半开窗口（探测未启用 / 未熔断 / 冷却未到）：无操作；
        - 成功：熔断器闭合（circuit_open_until 清零），节点恢复全量路由；
        - 失败：重新打开半程冷却期（min(cooldown/2, penalty_cap)），
          冷却时长减半使"彻底死掉"的 provider 冷却期单调收缩但不越过
          惩罚上限，避免无限次探测打同一死点。
        """
        if not self.in_circuit_half_open:
            return
        if probe_succeeded:
            self.circuit_open_until = 0.0
            logger.info("API %s 半开探测成功，熔断器闭合，恢复全量路由", self.config.model_name)
        else:
            penalty = min(self.circuit_cooldown_seconds / 2.0, self.half_open_probe_penalty_cap_seconds)
            self.circuit_open_until = time.monotonic() + penalty
            logger.warning(
                "API %s 半开探测失败，重新进入熔断冷却 %.1fs",
                self.config.model_name,
                penalty,
            )

    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 1.0
        return self.success_count / self.total_requests

    @property
    def avg_response_time_ms(self) -> float:
        """平均响应时间（毫秒，基于滑动窗口）"""
        if not self._response_times:
            return self.last_response_time_ms
        return sum(self._response_times) / len(self._response_times)

    def mark_success(self, response_time_ms: float) -> None:
        """标记成功调用（成功即熔断器复位：清零连续失败计数与熔断冷却）"""
        self.is_healthy = True
        self.consecutive_failures = 0
        self.circuit_open_until = 0.0  # 4.1：成功 = 熔断器闭合
        self.total_requests += 1
        self.success_count += 1
        self._response_times.append(response_time_ms)
        self.rate_limit_remaining = max(0, self.rate_limit_remaining - 1)

    def mark_failure(self, error_type: str = "unknown") -> None:
        """标记失败调用（连续失败达到阈值进入熔断冷却期，4.1）"""
        self.total_requests += 1
        self.error_count += 1
        self.consecutive_failures += 1
        # 连续失败达到阈值（可配置）标记为不健康；原硬编码 3 改为读自身字段
        if self.consecutive_failures >= self.max_consecutive_failures:
            self.is_healthy = False
            # 4.1 熔断器：达到阈值即打开熔断，冷却期内路由层继续跳过该节点
            self.circuit_open_until = time.monotonic() + self.circuit_cooldown_seconds
            logger.warning(
                "API %s 连续失败 %d 次，触发熔断冷却 %.0fs",
                self.config.model_name,
                self.consecutive_failures,
                self.circuit_cooldown_seconds,
            )
        # 限流错误特殊处理
        if error_type == "rate_limit":
            self.rate_limit_remaining = 0


@dataclass
class APIManagerConfig:
    """API管理器配置"""

    rotation_strategy: RotationStrategy = RotationStrategy.HEALTH_BASED
    health_check_interval: float = 60.0  # 健康检查间隔（秒）
    fallback_on_failure: bool = True  # 失败时是否自动降级
    max_consecutive_failures: int = 3  # 连续失败次数阈值
    timeout: int = 60  # 单次请求超时（秒）
    retry_count: int = 2  # 重试次数
    batch_health_check_size: int = 10  # 批量健康检查的批次大小
    health_check_timeout: float = 5.0  # 单次健康检查超时（秒）
    # 4.2 半开探测开关（默认 True）：熔断冷却到期后，节点不直接恢复全量路由，
    # 而是先处于"半开"状态，仅允许一次探测请求；探测成功才闭合熔断器，
    # 失败则重新打开半程冷却期（cooldown/2，受 half_open_probe_penalty_cap_seconds
    # 上限约束），避免死 provider 被全量流量反复打。置 False 退回 4.1 旧行为
    # （冷却到期即直接放行）。取值来源：经典熔断器三态（closed/open/half-open）
    # 标准做法。
    enable_half_open_probe: bool = True
    # 半开探测失败的惩罚时长上限（秒）：失败时重新打开的冷却 =
    # min(circuit_cooldown_seconds / 2.0, 本字段)，默认 30s（4.1 默认冷却
    # 60s 的一半），防止 provider 彻底宕机时冷却期越缩越短。
    # 经注册节点时注入到 APIHealth.half_open_probe_penalty_cap_seconds。
    half_open_probe_penalty_cap_seconds: float = 30.0
    # 节点成本权重映射（3.4 成本感知路由）：{model_name: 相对成本倍数}。
    # 未列出的模型默认 1.0（基准）。COST_AWARE 策略按"成功率/成本"综合排序，
    # 故障转移时优先选择"够用且便宜"的节点，避免把全量流量切到昂贵 provider。
    # 来源：llm_configs.json 的 cost_weight 字段（由 config.py 注入），或手动指定。
    node_cost_weights: dict[str, float] = field(default_factory=dict)
    # 成本告警开关（3.4）：故障转移落到 cost_weight >= _COST_ALERT_THRESHOLD 的
    # 昂贵 provider 时记 WARNING。默认 True（告警是纯旁路，不影响路由行为）。
    cost_alert_enabled: bool = True
    # 成本告警阈值（3.2 调优）：可配覆盖模块默认 _COST_ALERT_THRESHOLD（2.0）。
    # 根据实验中的 Provider 成本分布调整：阈值过低（如 1.5）会把"贵 1.5 倍"
    # 的常规切换也告警造成误报，上调到 3.0/5.0 只告警真正昂贵的 provider；
    # 成本敏感度高（如配额紧张）时反而下调。
    cost_alert_threshold: float = _COST_ALERT_THRESHOLD
    # 熔断冷却时长（秒，4.1）：节点连续失败达到 max_consecutive_failures 后
    # 进入熔断，冷却期内即使健康检查翻回健康也继续被路由跳过，避免把流量
    # 重新打回已知不可用的 provider（浪费时间与 token）。经验值 60s：
    # 死 provider 通常 1-2 分钟内恢复或彻底失效。
    circuit_cooldown_seconds: float = 60.0
