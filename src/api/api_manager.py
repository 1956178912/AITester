"""
智能 API 管理器：支持多模型轮换、健康检查、自动故障转移。
功能：
- 多策略轮换：轮询 / 加权随机 / 健康感知（优先健康节点）
- 实时健康检查：通过轻量请求验证 API 可用性
- 自动故障转移：失败时自动切换至备用节点
- 使用统计：记录调用次数、延迟、错误率
- 限流控制：防止单节点过载
- 大规模节点池支持（100+ 模型）
使用示例：
    from src.api.api_manager import APIManager
    manager = APIManager()
    result = manager.call(messages=[...], model="qwen-max")
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import openai

# 项目根目录的 config.py 仅依赖标准库与 python-dotenv，无循环导入风险，直接导入即可
# （此前用 importlib + sys.modules 别名加载同一文件，导致两份独立模块实例，已简化）
from config import LLM_CONFIGS, LLMConfig

logger = logging.getLogger(__name__)


def _redact(text: str) -> str:
    """对单段日志文本脱敏（4.1 审计：APIManager 被嵌入式使用时调用方未必挂脱敏 handler）。

    APIManager 的故障转移/健康检查日志会把 openai 异常的 str(e) 打进日志——
    部分 SDK/网关的错误体回显请求头或 base_url（其中可能含 API Key）。
    与 base_agent._redact_log_text 同口径：在日志点就地脱敏，不依赖入口接线。
    """
    try:
        from src.utils.logging_utils import mask_sensitive_info

        return mask_sensitive_info(text)
    except Exception:
        return text


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
    # 滑动窗口记录最近 N 次响应时间（用于计算平均值）
    _response_times: deque[float] = field(default_factory=lambda: deque(maxlen=10))

    @property
    def in_circuit_open(self) -> bool:
        """当前是否处于熔断冷却期（monotonic 时钟判定）。"""
        if self.circuit_open_until <= 0.0:
            return False
        return time.monotonic() < self.circuit_open_until

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


class HealthCheckerThread(threading.Thread):
    """后台健康检查线程：按配置间隔定时执行批量健康检查。

    该线程作为守护线程运行，APIManager 初始化时自动启动，
    周期性调用 health_check_batch() 更新节点健康状态，
    实现不健康的 API 节点及时被剔除出路由池。
    """

    def __init__(self, manager: APIManager, interval: float = 60.0) -> None:
        super().__init__(daemon=True, name="APIManager-HealthChecker")
        self._manager = manager
        self._interval = interval
        self._stop_event = threading.Event()

    def run(self) -> None:
        """线程主循环：等待间隔后执行一次健康检查，循环直到被停止信号唤醒。"""
        logger.info("健康检查后台线程已启动，间隔 %.1fs", self._interval)
        while not self._stop_event.wait(self._interval):
            try:
                self._manager.health_check_batch()
            except Exception as e:
                logger.error("健康检查后台线程异常: %s", _redact(str(e)))
        logger.info("健康检查后台线程已停止")

    def stop(self) -> None:
        """发送停止信号，等待线程自然退出。"""
        self._stop_event.set()


# 健康检查线程关闭的等待上限（秒）：join 超时后记录告警并放弃等待
# （守护线程随进程退出，不阻塞主流程）
_HEALTH_CHECKER_SHUTDOWN_TIMEOUT = 5.0


class APIManager:
    """
    智能 API 管理器
    支持多 LLM Provider 的智能路由、健康检查与故障转移。
    针对大规模节点池（100+ 模型）优化。
    """

    def __init__(self, config: APIManagerConfig | None = None, enable_health_checker: bool = True) -> None:
        # enable_health_checker：是否自动启动后台健康检查守护线程（默认 True，保持历史行为）。
        # 该线程每 60s 会对所有节点发起真实 LLM 请求（消耗 API 配额）；
        # 嵌入式使用、单元测试等不想引入后台线程的场景传 False 显式关闭。
        self.config = config or APIManagerConfig()
        self.health_nodes: dict[str, APIHealth] = {}
        self._rr_index: int = 0  # 轮询索引
        self._last_health_check: dict[str, float] = {}
        self._client_cache: dict[str, openai.OpenAI] = {}
        self._lock = threading.Lock()  # 线程安全锁
        self._health_checker: HealthCheckerThread | None = None
        # 初始化所有配置的 LLM
        self._init_clients()
        # 启动后台健康检查线程（可关闭，避免构造副作用：线程会周期性发起真实 API 请求）
        if enable_health_checker:
            self._start_health_checker()

    def _init_clients(self) -> None:
        """初始化所有 LLM 客户端并注册到健康节点"""
        for _idx, llm_config in enumerate(LLM_CONFIGS, start=1):
            client = openai.OpenAI(
                api_key=llm_config.api_key, base_url=llm_config.base_url, timeout=self.config.timeout
            )
            self._client_cache[llm_config.model_name] = client
            # 3.4 成本感知：从配置读取该模型的成本权重（未配置默认 1.0=基准）
            cost_weight = self._cost_weight_for(llm_config.model_name)
            health = APIHealth(
                config=llm_config,
                max_consecutive_failures=self.config.max_consecutive_failures,
                cost_weight=cost_weight,
                # 4.1：把配置里的熔断冷却时长注入节点（mark_failure 触发熔断时写入）
                circuit_cooldown_seconds=self.config.circuit_cooldown_seconds,
            )
            self.health_nodes[llm_config.model_name] = health
            logger.info(
                "注册 LLM 节点: %s (%s, cost_weight=%.2f)",
                llm_config.model_name,
                _redact(llm_config.base_url),
                cost_weight,
            )
        logger.info("已完成 %d 个 LLM 节点初始化", len(self.health_nodes))

    def _cost_weight_for(self, model_name: str) -> float:
        """取模型的成本权重（3.4）：优先读 APIManagerConfig.node_cost_weights，
        缺省回退到 LLMConfig.cost_weight 字段（config.py 从 llm_configs.json 注入），
        再缺省 1.0（基准）。

        Args:
            model_name: 模型名称。

        Returns:
            相对成本倍数（>= 0.1，防除零由调用方兜底）。
        """
        if model_name in self.config.node_cost_weights:
            return float(self.config.node_cost_weights[model_name])
        # 从已注册节点反查 LLMConfig.cost_weight（_init_clients 时已建立映射）
        node = self.health_nodes.get(model_name)
        if node is not None and getattr(node.config, "cost_weight", 0.0):
            return float(node.config.cost_weight)
        return 1.0

    def get_healthy_nodes(self) -> list[APIHealth]:
        """获取所有健康节点（4.1：熔断冷却期内的节点即使 is_healthy 为
        True 也继续被跳过，直到冷却到期或 mark_success 复位）"""
        return [h for h in self.health_nodes.values() if h.is_healthy and not h.in_circuit_open]

    def get_all_nodes(self) -> list[APIHealth]:
        """获取所有节点（包括不健康的）"""
        return list(self.health_nodes.values())

    def _select_node_round_robin(self) -> APIHealth | None:
        """轮询策略：按顺序选择下一个健康节点"""
        healthy = self.get_healthy_nodes()
        if not healthy:
            return None
        node = healthy[self._rr_index % len(healthy)]
        self._rr_index = (self._rr_index + 1) % len(healthy)
        return node

    def _select_node_weighted_random(self) -> APIHealth | None:
        """加权随机策略：根据成功率和响应时间加权"""
        healthy = self.get_healthy_nodes()
        if not healthy:
            return None
        # 计算权重：成功率高且响应时间快的权重更高
        weights = []
        for node in healthy:
            # 基础权重 = 成功率 * 1000 / (响应时间 + 1)
            weight = node.success_rate * 1000 / (node.avg_response_time_ms + 1)
            weights.append(max(weight, 0.1))  # 最小权重 0.1
        return random.choices(healthy, weights=weights, k=1)[0]

    def _select_node_health_based(self) -> APIHealth | None:
        """健康感知策略：优先选择响应最快且成功率最高的节点"""
        healthy = self.get_healthy_nodes()
        if not healthy:
            return None

        # 按综合评分排序：成功率 * 0.6 + (1/响应时间) * 0.4
        def score(node: APIHealth) -> float:
            resp_score = 1.0 / (node.avg_response_time_ms + 1)
            return node.success_rate * 0.6 + resp_score * 0.4

        healthy.sort(key=score, reverse=True)
        return healthy[0]

    def _select_node_fastest_first(self) -> APIHealth | None:
        """最快优先策略：选择响应时间最短的健康节点（适合大规模节点池）"""
        healthy = self.get_healthy_nodes()
        if not healthy:
            return None
        # 按平均响应时间排序，选择最快的
        healthy.sort(key=lambda n: n.avg_response_time_ms)
        return healthy[0]

    def _select_node_cost_aware(self) -> APIHealth | None:
        """成本感知策略（3.4）：按"成功率 / 成本权重"综合评分选节点。

        评分 = 成功率 * 0.5 + (1 / cost_weight) * 0.5。
        - 成本权重越高（越贵），其"性价比项" 1/cost 越低，排序越靠后；
        - 故障转移到备用节点时，昂贵的 provider 不会被无差别推上主位，
          避免把全量流量切到成本更高的服务；
        - 成功率仍占 50% 权重，健康表现差的便宜节点不会被误选。

        未配置成本信息（cost_weight 全为 1.0）时退化为按成功率 + 响应倒数，
        行为与健康感知接近但更偏"便宜优先"。
        """
        healthy = self.get_healthy_nodes()
        if not healthy:
            return None

        def score(node: APIHealth) -> float:
            cost = max(node.cost_weight, 0.1)  # 防除零
            return node.success_rate * 0.5 + (1.0 / cost) * 0.5

        healthy.sort(key=score, reverse=True)
        return healthy[0]

    def select_node(self) -> APIHealth | None:
        """根据当前策略选择节点"""
        with self._lock:
            if self.config.rotation_strategy == RotationStrategy.ROUND_ROBIN:
                return self._select_node_round_robin()
            elif self.config.rotation_strategy == RotationStrategy.WEIGHTED_RANDOM:
                return self._select_node_weighted_random()
            elif self.config.rotation_strategy == RotationStrategy.FASTEST_FIRST:
                return self._select_node_fastest_first()
            elif self.config.rotation_strategy == RotationStrategy.COST_AWARE:
                return self._select_node_cost_aware()
            else:  # HEALTH_BASED
                return self._select_node_health_based()

    def check_health(self, node: APIHealth) -> bool:
        """
        对单个节点进行健康检查
        发送一个轻量请求测试 API 可用性
        """
        try:
            client = self._client_cache.get(node.config.model_name)
            if not client:
                node.is_healthy = False
                return False
            start = time.time()
            # 使用最小请求测试
            response = client.chat.completions.create(
                model=node.config.model_name,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
                temperature=0,
                timeout=self.config.health_check_timeout,
            )
            elapsed_ms = (time.time() - start) * 1000
            # 检查响应
            if response and response.choices:
                node.mark_success(elapsed_ms)
                logger.debug("健康检查通过: %s (%.2fms)", node.config.model_name, elapsed_ms)
                return True
            else:
                node.mark_failure("empty_response")
                return False
        except openai.RateLimitError:
            node.mark_failure("rate_limit")
            logger.warning("API 限流: %s", node.config.model_name)
            return False
        except openai.APIError as e:
            status = getattr(e, "status_code", "unknown")
            node.mark_failure(f"api_error:{status}")
            logger.warning("API 错误: %s - %s", node.config.model_name, _redact(str(e)))
            return False
        except Exception as e:
            node.mark_failure(f"error:{type(e).__name__}")
            logger.error("健康检查异常: %s - %s", node.config.model_name, _redact(str(e)))
            return False

    def health_check_all(self) -> dict[str, bool]:
        """
        对所有节点进行健康检查
        Returns:
            字典 {model_name: is_healthy}
        """
        results = {}
        for name, node in self.health_nodes.items():
            results[name] = self.check_health(node)
        return results

    def health_check_batch(self, batch_size: int | None = None) -> dict[str, bool]:
        """
        批量健康检查（分批执行，避免一次性请求过多）
        Args:
            batch_size: 每批检查的节点数，默认使用配置值
        Returns:
            字典 {model_name: is_healthy}
        """
        if batch_size is None:
            batch_size = self.config.batch_health_check_size
        all_results = {}
        nodes = list(self.health_nodes.items())
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i : i + batch_size]
            logger.info("正在检查第 %d-%d 个节点...", i + 1, min(i + batch_size, len(nodes)))
            for name, node in batch:
                all_results[name] = self.check_health(node)
                time.sleep(0.1)  # 短暂间隔，避免瞬时流量过大
        healthy_count = sum(1 for v in all_results.values() if v)
        logger.info("批量健康检查完成: %d/%d 个节点健康", healthy_count, len(all_results))
        return all_results

    def _build_node_list(self, model: str | None) -> tuple[list, list]:
        """构建待尝试节点列表和备用节点列表。"""
        if model and model in self.health_nodes:
            nodes_to_try = [self.health_nodes[model]]
        else:
            primary = self.select_node()
            if primary:
                nodes_to_try = [primary]
            else:
                raise RuntimeError("无可用 API 节点，请检查配置")
        all_nodes = self.get_all_nodes()
        # 4.1：备用节点候选同样排除熔断冷却期内的节点（is_healthy 为 True
        # 但冷却未到期的节点不可用，否则故障转移会把流量重新打回死 provider）
        fallback_candidates = [n for n in all_nodes if n not in nodes_to_try and n.is_healthy and not n.in_circuit_open]
        return nodes_to_try, fallback_candidates

    def _try_call_node(
        self, node, messages, kwargs, call_model: str, attempt: int, prev_model: str | None = None
    ) -> Any:
        """尝试调用单个节点的 API。

        Args:
            node: 目标节点（APIHealth）。
            messages: 对话消息列表。
            kwargs: 传给 chat.completions.create 的额外参数。
            call_model: 实际请求携带的模型名。
            attempt: 当前尝试序号（0 起）。
            prev_model: 上一次尝试的模型名（故障转移成功时用于日志，attem > 0 才有意义）。
        """
        client = self._client_cache.get(node.config.model_name)
        if not client:
            return None
        start = time.time()
        response = client.chat.completions.create(
            model=call_model, messages=messages, timeout=self.config.timeout, **kwargs
        )
        elapsed_ms = (time.time() - start) * 1000
        node.mark_success(elapsed_ms)
        if attempt > 0:
            # 故障转移成功：记录"上一个节点 -> 当前节点"（此前误把当前节点名打印了两遍）
            logger.info("故障转移成功: %s -> %s", prev_model or "unknown", node.config.model_name)
            # 3.4 成本告警：故障转移落到昂贵 provider（cost_weight >= 阈值）时记 WARNING，
            # 让监控/实验分析能捕获"配额故障把全量流量切到贵模型"的成本风险。
            # 告警是纯旁路（不影响路由），cost_alert_enabled=False 可关闭；
            # 阈值经 3.2 可配覆盖（cost_alert_threshold），默认 2.0。
            if self.config.cost_alert_enabled and node.cost_weight >= self.config.cost_alert_threshold:
                logger.warning(
                    "成本告警：故障转移到昂贵 provider %s（cost_weight=%.2f >= %.2f），"
                    "请确认配额故障是否导致全量流量切到高成本模型",
                    node.config.model_name,
                    node.cost_weight,
                    self.config.cost_alert_threshold,
                )
        return response

    def _handle_rate_limit(self, node, attempt: int, primary_count: int) -> None:
        """处理限流错误，根据配置决定是否等待重试。"""
        node.mark_failure("rate_limit")
        logger.warning("限流: %s (attempt %d)", node.config.model_name, attempt + 1)
        if self.config.fallback_on_failure and attempt < primary_count - 1:
            time.sleep(2)
        elif self.config.fallback_on_failure:
            time.sleep(5)

    def _handle_api_error(self, e, node) -> None:
        """处理API错误，根据配置决定是否抛出。"""
        node.mark_failure(f"api_error:{getattr(e, 'status_code', 'unknown')}")
        logger.warning("API 错误: %s - %s", node.config.model_name, _redact(str(e)))
        if not self.config.fallback_on_failure:
            # fallback 禁用时，记录错误后直接抛出原始异常
            raise

    def _handle_generic_error(self, e, node) -> None:
        """处理通用异常，根据配置决定是否抛出。"""
        node.mark_failure(f"error:{type(e).__name__}")
        logger.error("调用失败: %s - %s", node.config.model_name, _redact(str(e)))
        if not self.config.fallback_on_failure:
            raise

    def call(self, messages: list[dict[str, str]], model: str | None = None, **kwargs: Any) -> Any:
        """
        调用 LLM API（带自动故障转移）
        Args:
            messages: 对话消息列表
            model: 指定模型（None 则按策略自动选择）
            **kwargs: 其他参数（temperature, max_tokens 等）
        Returns:
            OpenAI 的 ChatCompletion 对象
        Raises:
            RuntimeError: 所有节点均不可用时抛出
        """
        nodes_to_try, fallback_candidates = self._build_node_list(model)
        last_error: Exception | None = None
        all_nodes = nodes_to_try + fallback_candidates

        for attempt, node in enumerate(all_nodes):
            # 显式指定 model 时：主节点（attempt < len(nodes_to_try)）用指定模型；
            # 故障转移到备用节点后改用该节点自身模型名——备用 provider 通常没有
            # 指定模型，沿用会逐个 APIError 陪葬，故障转移形同虚设
            call_model = model if model and attempt < len(nodes_to_try) else node.config.model_name
            prev_model = all_nodes[attempt - 1].config.model_name if attempt > 0 else model
            try:
                response = self._try_call_node(node, messages, kwargs, call_model, attempt, prev_model)
                if response is not None:
                    return response
            except openai.RateLimitError as e:
                self._handle_rate_limit(node, attempt, len(nodes_to_try))
                last_error = e
            except openai.APIError as e:
                self._handle_api_error(e, node)
                last_error = e
            except Exception as e:
                self._handle_generic_error(e, node)
                last_error = e

        if last_error:
            raise RuntimeError(f"所有 API 节点调用失败: {last_error}")
        raise RuntimeError("所有 API 节点不可用")

    def get_status(self) -> dict[str, Any]:
        """获取所有节点的当前状态（4.1：含熔断冷却信息；4.1 审计：base_url 脱敏）。

        base_url 可能内嵌凭证（部分网关把 token 放在 URL 路径/查询串中），
        本字典会流经 print_status_table（直接 print 到 stdout，不经 logging
        handler 脱敏）与监控导出等出口，统一在出口脱敏——与日志脱敏口径一致。
        """
        from src.utils.logging_utils import mask_sensitive_info

        now = time.monotonic()
        nodes_summary = {}
        for name, h in self.health_nodes.items():
            # 熔断剩余冷却秒数（0 = 未熔断或已到期），便于监控/实验分析
            circuit_remaining = max(0.0, h.circuit_open_until - now) if h.circuit_open_until > 0 else 0.0
            nodes_summary[name] = {
                "model": h.config.model_name,
                "base_url": mask_sensitive_info(h.config.base_url),
                "is_healthy": h.is_healthy,
                "success_rate": round(h.success_rate, 3),
                "total_requests": h.total_requests,
                "consecutive_failures": h.consecutive_failures,
                "avg_response_time_ms": round(h.avg_response_time_ms, 2),
                # 4.1 熔断器状态：冷却剩余秒数（>0 表示该节点当前处于熔断冷却期）
                "circuit_open_remaining_s": round(circuit_remaining, 1),
            }
        return {
            "total_nodes": len(self.health_nodes),
            "healthy_nodes": len(self.get_healthy_nodes()),
            "unhealthy_nodes": len(self.get_all_nodes()) - len(self.get_healthy_nodes()),
            "rotation_strategy": self.config.rotation_strategy.value,
            "nodes": nodes_summary,
        }

    def get_top_nodes(self, n: int = 10, sort_by: str = "success_rate") -> list[dict[str, Any]]:
        """
        获取表现最好的 N 个节点
        Args:
            n: 返回节点数量
            sort_by: 排序字段（"success_rate" / "response_time" / "requests"）
        Returns:
            节点信息列表
        """
        healthy = self.get_healthy_nodes()
        # 过滤至少有 1 次请求的节点
        experienced = [n for n in healthy if n.total_requests > 0]
        if sort_by == "success_rate":
            experienced.sort(key=lambda x: x.success_rate, reverse=True)
        elif sort_by == "response_time":
            experienced.sort(key=lambda x: x.avg_response_time_ms)
        elif sort_by == "requests":
            experienced.sort(key=lambda x: x.total_requests, reverse=True)
        result = []
        for node in experienced[:n]:
            result.append(
                {
                    "model": node.config.model_name,
                    "success_rate": round(node.success_rate, 3),
                    "avg_response_time_ms": round(node.avg_response_time_ms, 2),
                    "total_requests": node.total_requests,
                }
            )
        return result

    def reset_stats(self) -> None:
        """重置所有统计数据（含 4.1 熔断器状态：清零冷却截止时间）"""
        with self._lock:
            for node in self.health_nodes.values():
                node.total_requests = 0
                node.success_count = 0
                node.error_count = 0
                node.consecutive_failures = 0
                node.is_healthy = True
                node.circuit_open_until = 0.0
                node._response_times.clear()
        logger.info("已重置所有 API 节点统计")

    def add_node(self, config: LLMConfig) -> None:
        """
        动态添加新节点
        Args:
            config: LLM 配置对象
        """
        with self._lock:
            client = openai.OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=self.config.timeout)
            self._client_cache[config.model_name] = client
            health = APIHealth(
                config=config,
                max_consecutive_failures=self.config.max_consecutive_failures,
                cost_weight=self._cost_weight_for(config.model_name),
                circuit_cooldown_seconds=self.config.circuit_cooldown_seconds,
            )
            self.health_nodes[config.model_name] = health
            logger.info("动态添加节点: %s (%s)", config.model_name, _redact(config.base_url))

    def remove_node(self, model_name: str) -> bool:
        """
        动态移除节点
        Args:
            model_name: 模型名称
        Returns:
            是否成功移除
        """
        with self._lock:
            if model_name in self.health_nodes:
                del self.health_nodes[model_name]
                if model_name in self._client_cache:
                    del self._client_cache[model_name]
                logger.info("移除节点: %s", model_name)
                return True
            return False

    def _start_health_checker(self) -> None:
        """启动后台健康检查守护线程。

        在初始化完成后立即启动，线程以 daemon=True 运行，
        主程序退出时线程自动终止，无需手动清理。
        """
        if self._health_checker is not None and self._health_checker.is_alive():
            logger.debug("健康检查线程已在运行，跳过启动")
            return
        self._health_checker = HealthCheckerThread(self, interval=self.config.health_check_interval)
        self._health_checker.start()
        logger.info("已启动后台健康检查线程，间隔 %.1fs", self.config.health_check_interval)

    def _stop_health_checker(self) -> None:
        """停止并等待后台健康检查线程退出（释放管理器实例前调用）。

        线程是 daemon=True，进程退出时会被杀掉；但若只是释放实例（如
        reset_manager）而不停线程，残留线程会继续按间隔对旧实例发起
        真实 LLM 健康检查请求（消耗 API 配额）。因此此处显式停止并等待。
        """
        checker = self._health_checker
        if checker is None:
            return
        checker.stop()
        checker.join(timeout=_HEALTH_CHECKER_SHUTDOWN_TIMEOUT)
        if checker.is_alive():
            # 批量健康检查可能耗时较长（真实 API 探测），等待超时后不阻塞，
            # 依赖 daemon 特性在进程退出时清理
            logger.warning("健康检查线程未在 %.1fs 内退出，交由进程退出清理", _HEALTH_CHECKER_SHUTDOWN_TIMEOUT)
        self._health_checker = None


# 全局单例
_manager: APIManager | None = None
# 单例锁：保护 get_manager/reset_manager，避免并发时创建多个管理器实例
_manager_lock = threading.Lock()


def get_manager() -> APIManager:
    """获取全局 API 管理器单例（双重检查锁，线程安全）。"""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = APIManager()
    return _manager


def reset_manager() -> None:
    """重置全局管理器（用于测试）。

    清空前停止旧实例的后台健康检查线程，避免残留线程继续发起
    真实 LLM 健康检查请求（详见 _stop_health_checker 的说明）。
    """
    global _manager
    with _manager_lock:
        if _manager is not None:
            _manager._stop_health_checker()
        _manager = None


def print_status_table(manager: APIManager | None = None) -> None:
    """
    打印友好的状态表格
    Args:
        manager: API 管理器实例（None 则使用全局单例）
    """
    if manager is None:
        manager = get_manager()
    status = manager.get_status()
    print("\n" + "=" * 80)
    print(f"API 管理器状态 (共 {status['total_nodes']} 个节点, {status['healthy_nodes']} 个健康)")
    print("=" * 80)
    print(f"轮换策略: {status['rotation_strategy']}")
    print("-" * 80)
    print(f"{'模型名称':<25} {'健康状态':<8} {'成功率':<8} {'请求数':<8} {'平均延迟(ms)':<12}")
    print("-" * 80)
    for _name, node in status["nodes"].items():
        health_str = "✓ 健康" if node["is_healthy"] else "✗ 不健康"
        print(
            f"{node['model']:<25} {health_str:<8} {node['success_rate']:<8.2%} "
            f"{node['total_requests']:<8} {node['avg_response_time_ms']:<12.2f}"
        )
    print("=" * 80 + "\n")
