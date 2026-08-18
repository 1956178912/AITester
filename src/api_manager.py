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
    from src.api_manager import APIManger
    manager = APIManger()
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

from config import LLM_CONFIGS, LLMConfig

logger = logging.getLogger(__name__)


class RotationStrategy(Enum):
    """轮换策略枚举"""

    ROUND_ROBIN = "round_robin"  # 轮询
    WEIGHTED_RANDOM = "weighted_random"  # 加权随机
    HEALTH_BASED = "health_based"  # 健康感知（优先健康节点）
    FASTEST_FIRST = "fastest_first"  # 响应最快优先（针对大规模节点池优化）


@dataclass
class APIHealth:
    """单个 API 节点的健康状态"""

    config: LLMConfig
    is_healthy: bool = True
    consecutive_failures: int = 0
    total_requests: int = 0
    success_count: int = 0
    error_count: int = 0
    last_response_time_ms: float = 0.0
    last_check_time: float = 0.0
    rate_limit_remaining: int = 0
    # 滑动窗口记录最近 N 次响应时间（用于计算平均值）
    _response_times: deque[float] = field(default_factory=lambda: deque(maxlen=10))

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
        """标记成功调用"""
        self.is_healthy = True
        self.consecutive_failures = 0
        self.success_count += 1
        self._response_times.append(response_time_ms)
        self.rate_limit_remaining = max(0, self.rate_limit_remaining - 1)

    def mark_failure(self, error_type: str = "unknown") -> None:
        """标记失败调用"""
        self.error_count += 1
        self.consecutive_failures += 1
        # 连续失败3次标记为不健康
        if self.consecutive_failures >= 3:
            self.is_healthy = False
            logger.warning("API %s 连续失败 %d 次，标记为不健康", self.config.model_name, self.consecutive_failures)
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


class HealthCheckerThread(threading.Thread):
    """后台健康检查线程：按配置间隔定时执行批量健康检查。

    该线程作为守护线程运行，APIManger 初始化时自动启动，
    周期性调用 health_check_batch() 更新节点健康状态，
    实现不健康的 API 节点及时被剔除出路由池。
    """

    def __init__(self, manager: APIManger, interval: float = 60.0) -> None:
        super().__init__(daemon=True, name="APIManger-HealthChecker")
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
                logger.error("健康检查后台线程异常: %s", e)
        logger.info("健康检查后台线程已停止")

    def stop(self) -> None:
        """发送停止信号，等待线程自然退出。"""
        self._stop_event.set()


class APIManger:
    """
    智能 API 管理器
    支持多 LLM Provider 的智能路由、健康检查与故障转移。
    针对大规模节点池（100+ 模型）优化。
    """

    def __init__(self, config: APIManagerConfig | None = None):
        self.config = config or APIManagerConfig()
        self.health_nodes: dict[str, APIHealth] = {}
        self._rr_index: int = 0  # 轮询索引
        self._last_health_check: dict[str, float] = {}
        self._client_cache: dict[str, openai.OpenAI] = {}
        self._lock = threading.Lock()  # 线程安全锁
        self._health_checker: HealthCheckerThread | None = None
        # 初始化所有配置的 LLM
        self._init_clients()
        # 启动后台健康检查线程
        self._start_health_checker()

    def _init_clients(self) -> None:
        """初始化所有 LLM 客户端并注册到健康节点"""
        for _idx, llm_config in enumerate(LLM_CONFIGS, start=1):
            client = openai.OpenAI(
                api_key=llm_config.api_key, base_url=llm_config.base_url, timeout=self.config.timeout
            )
            self._client_cache[llm_config.model_name] = client
            health = APIHealth(config=llm_config)
            self.health_nodes[llm_config.model_name] = health
            logger.info("注册 LLM 节点: %s (%s)", llm_config.model_name, llm_config.base_url)
        logger.info("已完成 %d 个 LLM 节点初始化", len(self.health_nodes))

    def get_healthy_nodes(self) -> list[APIHealth]:
        """获取所有健康节点"""
        return [h for h in self.health_nodes.values() if h.is_healthy]

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

    def select_node(self) -> APIHealth | None:
        """根据当前策略选择节点"""
        with self._lock:
            if self.config.rotation_strategy == RotationStrategy.ROUND_ROBIN:
                return self._select_node_round_robin()
            elif self.config.rotation_strategy == RotationStrategy.WEIGHTED_RANDOM:
                return self._select_node_weighted_random()
            elif self.config.rotation_strategy == RotationStrategy.FASTEST_FIRST:
                return self._select_node_fastest_first()
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
            node.mark_failure(f"api_error:{e.status_code}")
            logger.warning("API 错误: %s - %s", node.config.model_name, e)
            return False
        except Exception as e:
            node.mark_failure(f"error:{type(e).__name__}")
            logger.error("健康检查异常: %s - %s", node.config.model_name, e)
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
        fallback_candidates = [n for n in all_nodes if n not in nodes_to_try and n.is_healthy]
        return nodes_to_try, fallback_candidates

    def _try_call_node(self, node, messages, kwargs, call_model: str, attempt: int) -> Any:
        """尝试调用单个节点的 API。"""
        client = self._client_cache.get(node.config.model_name)
        if not client:
            return None
        start = time.time()
        response = client.chat.completions.create(
            model=call_model, messages=messages, timeout=self.config.timeout, **kwargs
        )
        elapsed_ms = (time.time() - start) * 1000
        node.mark_success(elapsed_ms)
        node.total_requests += 1
        if attempt > 0:
            logger.info("故障转移成功: %s -> %s", node.config.model_name, node.config.model_name)
        return response

    def _handle_rate_limit(self, node, attempt: int, primary_count: int) -> None:
        """处理限流错误，根据配置决定是否等待重试。"""
        node.mark_failure("rate_limit")
        node.total_requests += 1
        logger.warning("限流: %s (attempt %d)", node.config.model_name, attempt + 1)
        if self.config.fallback_on_failure and attempt < primary_count - 1:
            time.sleep(2)
        elif self.config.fallback_on_failure:
            time.sleep(5)

    def _handle_api_error(self, e, node) -> None:
        """处理API错误，根据配置决定是否抛出。"""
        node.mark_failure(f"api_error:{e.status_code}")
        node.total_requests += 1
        logger.warning("API 错误: %s - %s", node.config.model_name, e)
        if not self.config.fallback_on_failure:
            raise

    def _handle_generic_error(self, e, node) -> None:
        """处理通用异常，根据配置决定是否抛出。"""
        node.mark_failure(f"error:{type(e).__name__}")
        node.total_requests += 1
        logger.error("调用失败: %s - %s", node.config.model_name, e)
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
            call_model = model or node.config.model_name
            try:
                response = self._try_call_node(node, messages, kwargs, call_model, attempt)
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
        """获取所有节点的当前状态"""
        nodes_summary = {}
        for name, h in self.health_nodes.items():
            nodes_summary[name] = {
                "model": h.config.model_name,
                "base_url": h.config.base_url,
                "is_healthy": h.is_healthy,
                "success_rate": round(h.success_rate, 3),
                "total_requests": h.total_requests,
                "consecutive_failures": h.consecutive_failures,
                "avg_response_time_ms": round(h.avg_response_time_ms, 2),
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
        """重置所有统计数据"""
        with self._lock:
            for node in self.health_nodes.values():
                node.total_requests = 0
                node.success_count = 0
                node.error_count = 0
                node.consecutive_failures = 0
                node.is_healthy = True
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
            health = APIHealth(config=config)
            self.health_nodes[config.model_name] = health
            logger.info("动态添加节点: %s (%s)", config.model_name, config.base_url)

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


# 全局单例
_manager: APIManger | None = None


def get_manager() -> APIManger:
    """获取全局 API 管理器单例"""
    global _manager
    if _manager is None:
        _manager = APIManger()
    return _manager


def reset_manager() -> None:
    """重置全局管理器（用于测试）"""
    global _manager
    _manager = None


def print_status_table(manager: APIManger | None = None) -> None:
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
