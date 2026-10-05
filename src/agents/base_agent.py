"""
智能体基类模块：封装智能体通用行为，为所有子类提供统一的接口。

所有智能体（Planner、Generator、Debugger）均继承此类，
共享 LLM 调用、JSON 解析、代码提取等通用能力。

LLM 客户端管理（客户端缓存 / 指数退避重试 / 日志脱敏 / token 统计 / 配置获取 /
zai 兼容检测 / 文件缓存开关）已拆分到 `src/agents/llm_client.py`（代码可维护性
优化）。本模块通过 re-import 复用其工具函数，保持「从 base_agent 命名空间访问」
的历史语义不变。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from contextlib import suppress
from typing import Any

from config import LLM_CALL_BUDGET_SECONDS, LLM_TIMEOUT, TEMPERATURE
from src.agents.llm_client import (
    _DEFAULT_LLM_MAX_RETRIES,
    _cache_creator_label,
    _call_zai,
    _get_all_api_configs,
    _get_llm_config,
    _get_or_create_chat_client,
    _is_zai_compatible,
    _llm_cache_dir,
    _llm_cache_enabled,
    _record_response_usage,
    _redact_log_text,
    _retry_with_exponential_backoff,
    cache_creator_ok,
)
from src.agents.rogue_monitor import rogue_monitor_enabled
from src.utils.helpers import extract_code_block, extract_json_object


def _is_rate_limit_error(e: BaseException) -> bool:
    """O15（2026-09-29 审查 P2）：判断异常是否为限流（429）错误。

    覆盖 openai.RateLimitError / httpx.HTTPStatusError(429) / 通用
    "429" / "rate limit" / "too many requests" 关键词匹配（SDK 版本差异
    下异常类名不同，关键词兜底确保跨 SDK 可识别）。
    """
    _msg = str(e).lower()
    if "429" in _msg or "rate limit" in _msg or "too many requests" in _msg:
        return True
    _type_name = type(e).__name__
    if "RateLimit" in _type_name or "rate_limit" in _msg:
        return True
    # httpx.HTTPStatusError with status_code == 429
    return getattr(e, "status_code", None) == 429


def _extract_retry_after_seconds(e: BaseException) -> float | None:
    """O15：从限流异常中提取 Retry-After 头（秒），无则返回 None。"""
    _resp = getattr(e, "http_response", None) or getattr(e, "response", None)
    if _resp is not None:
        _h = getattr(_resp, "headers", {})
        _ra = _h.get("retry-after") if isinstance(_h, dict) else None
        if _ra:
            try:
                return float(_ra)
            except (ValueError, TypeError):
                pass
    return None


logger = logging.getLogger(__name__)

# ─── Token 优化常量 ─────────────────────────────────────────────────────────
# 单条代码输入最大字符数：超长代码截断，避免 token 浪费
# P0 1.1 分层代码压缩：预算可经 CODE_MAX_CHARS 环境变量上调（大文件仓库级
# 任务 3000 字符装不下"目标函数 + 2 层调用链"），默认保持历史 3000。
# （os 已在文件头导入，2026-09-26 全面审查移除此处冗余的 `import os as _os`）

_code_max_chars_env = os.getenv("CODE_MAX_CHARS", "").strip()
try:
    _CODE_MAX_CHARS = int(_code_max_chars_env) if _code_max_chars_env else 3000
except ValueError:
    _CODE_MAX_CHARS = 3000
# P0 1.1：调用链展开层数（depth=1 历史行为；2 = 目标函数 → 被调函数 → 其被调，
# 跨文件任务经 CODE_FOCUS_DEPTH=2 构建"目标函数 → 被调用函数（1-2层）"上下文）
_code_focus_depth_env = os.getenv("CODE_FOCUS_DEPTH", "").strip()
try:
    CODE_FOCUS_DEPTH = int(_code_focus_depth_env) if _code_focus_depth_env else 1
except ValueError:
    CODE_FOCUS_DEPTH = 1
# 代码截断提示信息
_CODE_TRUNCATED_MSG = "\n\n[代码已截断，仅显示前 {max} 字符]"

# ─── LLM 文件缓存的进程内快路径（性能优化）────────────────────────────────────
# _call_llm_with_cache 每次调用都对缓存文件做 open + json.load（~20μs，--parallel
# 下每次 LLM 调用都走该路径），命中判定还要全量比较 prompt + system 文本。
# 文件缓存条目不可变（写入后内容固定），进程内再挂一层 LRU：
# - 命中：O(1) 直接返回（零磁盘 IO）；
# - 未命中但文件存在：完整读文件后回填 LRU（语义与"每次读文件"一致，
#   文件条目仍为事实来源，多进程场景下跨进程修改/删除文件不影响行为）；
# - 未命中：文件读取路径的"键材料不匹配 / 文件不存在"记录负缓存时间戳，
#   TTL 窗口内同键调用省的是"读文件失败"的 IO（命中判定仍需读文件——
#   文件是事实来源，外部写入/目录恢复后下一读文件即可命中）。
# 淘汰策略：固定容量 LRU（与 LLM 客户端缓存同口径，超限 FIFO/LRU 淘汰）。
# 负缓存 TTL（秒）：该间隔内同键跳过文件读取（"该键文件不存在"的快判），
# 过期后重新读文件（恢复"外部写入/目录变更可读"正确性——文件仍是事实
# 来源，负缓存只省 IO、不改变命中语义）。
_LRU_MAXSIZE = 1024
_LRU_NEGATIVE_TTL_SECONDS = 30.0
_lru_cache: OrderedDict[tuple[str, str, float | None], str] = OrderedDict()
# 负缓存：键 → 最近一次"文件不存在"确认的时间戳（TTL 窗口内跳过文件读取）
_lru_negatives: dict[tuple[str, str, float | None], float] = {}
_lru_lock = threading.Lock()


def _lru_lookup(key: tuple[str, str, float | None]) -> str | None:
    """进程内 LRU 命中时直接返回值（O(1)，含 move_to_end）。"""
    with _lru_lock:
        if key in _lru_cache:
            _lru_cache.move_to_end(key)
            return _lru_cache[key]
        return None


def _lru_check_negative(key: tuple[str, str, float | None]) -> bool:
    """负缓存是否命中（该键在 TTL 窗口内最近已确认文件不存在，可跳过文件读取）。

    命中即过期清理：超 TTL 的负缓存条目就地删除（惰性回收，无后台线程），
    过期后调用方重新走文件读取路径。
    """
    with _lru_lock:
        ts = _lru_negatives.get(key)
        if ts is None:
            return False
        if time.time() - ts < _LRU_NEGATIVE_TTL_SECONDS:
            return True
        del _lru_negatives[key]
        return False


def _lru_store(key: tuple[str, str, float | None], value: str | None) -> None:
    """进程内 LRU 写入（None 记为负缓存，容量超限时淘汰最久未用条目）。

    非 None 值写入 LRU 正缓存的同时清除该键的负缓存条目（文件写入成功
    = "该键文件不存在"判定失效，TTL 窗口内同键调用不得再跳过文件重读）。
    """
    with _lru_lock:
        if value is None:
            _lru_negatives[key] = time.time()
            # 2026-09-26 round10 P2：负缓存与正缓存同容量上限（_LRU_MAXSIZE，
            # FIFO 淘汰）——旧实现无 cap，长程 benchmark（数千任务 × 温度
            # 变体）下从未被查的负缓存条目永久驻留，内存无界增长。超限
            # 淘汰最久未插入项（dict 插入序 = FIFO），口径与 LRU 一致
            while len(_lru_negatives) > _LRU_MAXSIZE:
                oldest_key = next(iter(_lru_negatives))
                del _lru_negatives[oldest_key]
            return
        _lru_cache[key] = value
        _lru_cache.move_to_end(key)
        _lru_negatives.pop(key, None)
        while len(_lru_cache) > _LRU_MAXSIZE:
            _lru_cache.popitem(last=False)


def _lru_clear() -> None:
    """清空进程内 LRU（缓存目录/开关切换或缓存文件被外部清理时调用）。"""
    with _lru_lock:
        _lru_cache.clear()
        _lru_negatives.clear()


def _budget_exceeded_error() -> Exception:
    """5.4 预算超限异常工厂（延迟构造，避免模块加载期对 cost_budget 的依赖）。"""
    from src.graph.cost_budget import BudgetExceededError, get_budget_stats

    stats = get_budget_stats()
    return BudgetExceededError(
        consumed=int(stats.get("consumed_tokens", 0)),
        limit=int(stats.get("token_limit", 0)),
        unit=str(stats.get("unit", "none")),
    )


def _reorder_api_groups_by_complexity(
    api_groups: dict[str, list[tuple[str, str]]],
    all_configs: list[tuple[str, str, str]],
    complexity_class: str,
) -> dict[str, list[tuple[str, str]]]:
    """P0 1.2 复杂度感知路由：按档位重排 api_groups。

    对同一模型（agnel-3.0-flash）的多个 LLM 实例（不同 provider 端点 /
    cost_weight），按复杂度档位重新排列尝试顺序：
    - "complex" → 高 cost_weight 端点在前（更强 / 更贵）
    - "simple"  → 低 cost_weight 端点在前（省钱）
    - "medium"  → 按 cost_weight 接近 1.0 排序

    cost_weight 从 LLM_CONFIGS（config 模块）读取（LLMConfig.cost_weight 字段，
    未配置为 0.0 = 1.0 基准），与 APIManager._cost_weight_for 同口径。
    单实例或无多实例差异时排序无效果（历史行为不变）。

    Args:
        api_groups: 原 api_groups 字典（{base_url: [(api_key, model_name), ...]}）。
        all_configs: 全部 LLM 配置（_get_all_api_configs 返回的三元组列表）。
        complexity_class: 复杂度档位（"simple"/"medium"/"complex"）。

    Returns:
        重排后的 api_groups（新字典，原字典不变）。
    """
    # 构建 cost_weight 查找表（model_name → cost_weight，0.0 视为 1.0）
    cost_weights: dict[str, float] = {}
    try:
        from config import LLM_CONFIGS

        for cfg in LLM_CONFIGS:
            cost_weights[cfg.model_name] = float(cfg.cost_weight) if cfg.cost_weight else 1.0
    except Exception:
        cost_weights = {}

    # 按 cost_weight 排序 base_url 键
    def _bw(key: str) -> float:
        """取该 base_url 下所有模型的 max cost_weight（最贵端点代表该组）。"""
        group = api_groups.get(key, [])
        if not group:
            return 1.0
        return max(cost_weights.get(m, 1.0) for _, m in group)

    if complexity_class == "complex":
        ordered_keys = sorted(api_groups.keys(), key=_bw, reverse=True)
    elif complexity_class == "simple":
        ordered_keys = sorted(api_groups.keys(), key=_bw)
    else:  # medium 或未知
        ordered_keys = sorted(api_groups.keys(), key=lambda k: abs(_bw(k) - 1.0))

    # 重新构建有序字典（Python 3.7+ dict 保序）
    reordered: dict[str, list[tuple[str, str]]] = {}
    for key in ordered_keys:
        if key in api_groups:
            reordered[key] = api_groups[key]
    return reordered


class BaseAgent:
    """
    所有智能体的公共基类。

    封装了与 LLM 交互的底层逻辑，包括：
    - 初始化 LangChain ChatOpenAI 客户端（复用连接池缓存）
    - 带重试的 LLM 调用（指数退避 + API 自动切换，支持 zai SDK）
    - JSON 输出提取（处理 LLM 可能输出的 markdown 包裹）
    - Python 代码块提取

    属性:
        llm: LangChain ChatOpenAI 实例（来自模块级缓存，连接池跨实例/跨调用复用）。
        system_prompt: 该智能体的 System Prompt 字符串。
    """

    def __init__(self, system_prompt: str) -> None:
        # 从配置获取默认 LLM 参数（api_key / base_url / model_name）
        api_key, base_url, model_name = _get_llm_config()
        # 复用缓存的 LangChain 客户端（连接池跨实例复用）：
        # 此前每个 BaseAgent 实例都新建一个 ChatOpenAI，而生产调用全部走
        # _call_llm 的缓存客户端，self.llm 实际只是"占位"属性——每个智能体
        # 实例化都白白多建一个 httpx 连接池；现改为与 _call_llm 共享同一缓存
        self.llm = _get_or_create_chat_client(model_name, TEMPERATURE, api_key, base_url)
        # 每个智能体携带自己的 System Prompt，定义其角色和行为约束
        self.system_prompt = system_prompt

    def _call_llm_with_cache(
        self,
        user_message: str,
        max_retries: int = _DEFAULT_LLM_MAX_RETRIES,
        temperature: float | None = None,
        complexity_class: str | None = None,
    ) -> str:
        """
        带缓存的 LLM 调用方法。

        首次调用时执行完整的 LLM 请求并缓存结果，
        后续相同输入直接返回缓存响应，节省 token 和延迟。

        缓存分层（性能优化）：
        1. 进程内 LRU 快路径：命中时零磁盘 IO 直接返回；
        2. 文件缓存（src/cache/*.json）：LRU 未命中时完整读文件回填，
           保证跨进程/跨会话命中（文件是事实来源）；
        3. LLM 调用成功且缓存开启时写文件并回填 LRU。

        O12（2026-09-29 审查 P1）：complexity_class 参数透传至 _call_llm，
        使 MODEL_ROUTING_STRATEGY=complexity_aware（默认值）的复杂度感知
        路由在缓存命中/未命中路径下均生效（此前该参数恒为 None，
        复杂度路由为死代码）。

        Args:
            user_message: 用户消息内容。
            max_retries: 单次 API 的最大重试次数。
            temperature: 采样温度覆盖（3.3 动态策略接线用）；None 时使用
                config.TEMPERATURE。非 None 时温度参与缓存键，避免不同温度
                命中同一缓存导致结果串味。
            complexity_class: P0 1.2 复杂度档位（"simple"/"medium"/"complex"）。
                非 None 时经 _call_llm → _reorder_api_groups_by_complexity
                按档位重排 API 组（complex → 高成本端点在前）。

        Returns:
            LLM 返回的文本字符串（来自缓存或实时调用）。
        """
        # R16（2026-10-05 审查 P1）：流氓行为监控上报（ROGUE_MONITOR_ENABLE=true
        # 时启用，默认关零开销）。每次 LLM 调用（含缓存命中——命中也是 agent 的
        # 一次"动作"）上报到进程内监控单例；失控循环（同一 agent 短窗口内调用
        # 频率 z-score 越限）由 _executor_node 的 check 消费写 state。上报异常
        # 不影响主链路（监控层自身故障不崩 LLM 调用）。
        if rogue_monitor_enabled():
            try:
                from src.agents.rogue_monitor import AgentEvent, get_rogue_monitor

                get_rogue_monitor().report_tool_call(AgentEvent(agent_id=type(self).__name__, tool="llm_call"))
            except Exception:  # 监控旁路失败静默（观测层不阻断主链路）
                pass
        # 缓存开关关闭时直接透传（测试环境默认关闭，避免缓存文件污染与 flaky）
        if not _llm_cache_enabled():
            if complexity_class is not None:
                if temperature is not None:
                    return self._call_llm(
                        user_message, max_retries, temperature=temperature, complexity_class=complexity_class
                    )
                return self._call_llm(user_message, max_retries, complexity_class=complexity_class)
            if temperature is not None:
                return self._call_llm(user_message, max_retries, temperature=temperature)
            return self._call_llm(user_message, max_retries)

        # 生成缓存键（基于 user_message + system_prompt + temperature）
        # 使用 hashlib.md5 替代 hash()，确保跨会话稳定命中（hash() 在 Python 3.3+ 默认随机化）
        # 说明：键不含 model（M8：基线/实验场景下跨模型调用时，缓存的是
        # "成功的 LLM 输出文本"；同一 prompt 在不同模型下的输出可能不同，
        # 但配额故障转移/模型切换后命中旧结果仍是该 prompt 的合理回答，
        # 且不再消耗 token——历史口径保持。正式实验须显式 AITESTER_LLM_CACHE=0
        # 以消除跨模型串味；此注释仅说明设计意图，不改变默认行为）。
        # 键材料用 \x00 分隔（user_message 与 system_prompt 均可能含冒号）；
        # 读缓存时先比长度再比全量文本，命中路径零额外成本
        # 写入缓存记录 temperature（None 归一为默认 TEMPERATURE）：读取校验时
        # 同键同材料重算，命中要求三要素全一致，语义收敛
        cache_key = f"{user_message}\x00{self.system_prompt}"
        if temperature is not None:
            cache_key += f"\x00t{temperature}"
        cache_hash = hashlib.md5(cache_key.encode("utf-8")).hexdigest()[:16]  # 取前16位十六进制，固定长度
        cache_file = os.path.normpath(os.path.join(_llm_cache_dir(), f"{cache_hash}.json"))
        lru_key = (cache_file, user_message, temperature)

        # M8（2026-09-29 审查 P0）：跨模型缓存隔离开关。
        # R13（2026-09-30 独立审查 P0）起**默认开启**（"1"）：缓存键加入
        # "当前配置链中首个有效 model_name"作为隔离材料——同一 prompt 在
        # 不同 model 命名空间下不再共享缓存条目（消除跨模型串味，保证
        # A/B 对照与可复现性）。设 AITESTER_CACHE_ISOLATE_MODEL=0 可显式
        # 退回"不隔离"历史口径（配额故障转移/模型切换复用旧结果的场景）。
        if os.environ.get("AITESTER_CACHE_ISOLATE_MODEL", "1").strip() != "0":
            from src.agents.llm_client import get_first_valid_model_name

            _iso_model = get_first_valid_model_name()
            if _iso_model:
                cache_key = f"{cache_key}\x00m{_iso_model}"
                cache_hash = hashlib.md5(cache_key.encode("utf-8")).hexdigest()[:16]
                cache_file = os.path.normpath(os.path.join(_llm_cache_dir(), f"{cache_hash}.json"))
                lru_key = (cache_file, user_message, temperature)

        # 快路径 1：进程内 LRU 命中（零磁盘 IO）
        hit = _lru_lookup(lru_key)
        if hit is not None:
            from src.agents.llm_client import record_cache_hit

            record_cache_hit(True)  # 15. 多进程缓存协调观测：LRU 命中
            logger.info("LLM 缓存命中 (LRU 快路径): %s", cache_key[:50])
            return hit

        # 5.1 语义级缓存快路径（SEMANTIC_CACHE_ENABLE=true 时启用，默认关）：
        # LRU/文件精确未命中后，按嵌入向量余弦相似度（复用 embedding_utils
        # 的 CodeBERT/sentence-transformers/chromadb 后端，后端缺失时自动
        # 降级为精确口径零行为变化）匹配"语义相同但措辞不同"的缓存条目，
        # 命中则直接复用响应（省一次 LLM 调用）。
        from src.agents.semantic_cache import (
            find_semantic_cache,
            get_semantic_cache_stats,
            maybe_rebuild_semantic_index,
        )

        if get_semantic_cache_stats()["enabled"]:
            # 节流 60s 的目录补建（嵌入后端缺失时全路径静默降级，零行为变化）
            maybe_rebuild_semantic_index(_llm_cache_dir())
            _sem_hit = find_semantic_cache(cache_file, user_message)
            if _sem_hit is not None:
                _sem_resp = _sem_hit[1]
                _lru_store(lru_key, _sem_resp)
                logger.info("5.1 语义缓存命中（复用响应，相似度 >= 阈值）: %s", cache_key[:50])
                return _sem_resp

        # 快路径 2：LRU 未命中——完整读文件校验 prompt/system 一致才命中
        # （防 md5 前16位碰撞误命中），命中后回填 LRU。
        # 负缓存语义（0.10）：负缓存命中（TTL 窗口内）时跳过文件重读
        # （省"读不存在的文件"IO），过期后重新读文件（恢复外部写入/
        # 目录变更可读的正确性）。文件仍是事实来源，负缓存仅省 IO。
        if _lru_check_negative(lru_key):
            logger.debug("LLM 缓存负缓存命中（跳过文件重读）: %s", cache_key[:50])
        else:
            try:
                with open(cache_file, encoding="utf-8") as f:
                    cached_data = json.load(f)
                if (
                    len(cached_data.get("prompt", "")) == len(user_message)
                    and cached_data.get("prompt") == user_message
                    and cached_data.get("system") == self.system_prompt
                    # 19. 创建者归属校验（Clinejection 教训）：uid 可得且条目
                    # 携带非空 creator_uid 时，非本用户条目不命中并告警（防
                    # 共享 CI / 多用户机器的跨用户缓存投毒）。历史无该字段的
                    # 条目视为兼容（不破坏既有缓存）；条目 creator_uid 为空
                    # 串（uid 不可得的平台）同样跳过校验。
                    and cache_creator_ok(cached_data.get("creator_uid"))
                ):
                    _lru_store(lru_key, cached_data["response"])
                    logger.info("LLM 缓存命中 (文件→LRU): %s", cache_key[:50])
                    return cached_data["response"]
                # 文件存在但键材料/归属不匹配（md5 前 16 位碰撞或跨用户
                # 投毒条目）：按未命中处理，记负缓存（延长 TTL 窗口，
                # 避免热循环反复读同一错配文件）
                _lru_store(lru_key, None)
            except FileNotFoundError:
                _lru_store(lru_key, None)  # 负缓存：该键当前无文件
            except Exception as e:
                logger.debug("缓存读取失败: %s", e)

        # 未命中，执行实际调用（仅在成功时写缓存；失败如 403 额度用尽则不缓存）
        from src.agents.llm_client import record_cache_hit

        record_cache_hit(False)  # 15. 多进程缓存协调观测：文件缓存未命中
        if complexity_class is not None:
            if temperature is not None:
                response = self._call_llm(
                    user_message, max_retries, temperature=temperature, complexity_class=complexity_class
                )
            else:
                response = self._call_llm(user_message, max_retries, complexity_class=complexity_class)
        elif temperature is not None:
            response = self._call_llm(user_message, max_retries, temperature=temperature)
        else:
            response = self._call_llm(user_message, max_retries)

        # 写入缓存（文件是事实来源；写成功则同步回填 LRU 供后续快路径）
        # 0.10 正确性：写成功 = "该键文件现已存在"，回填 LRU 时同步清除
        # 该键的负缓存条目（此前 _lru_store 用 `del _lru_negatives[key]`
        # 会 KeyError（写成功路径从不先记负缓存）；现改为 .pop(key, None)
        # 幂等清除，防"外部清理缓存目录 → 负缓存残留 → TTL 窗口内误跳过
        # 文件重读"的正确性回归）
        try:
            from src.agents.llm_client import ensure_llm_cache_dir, secure_cache_file

            # 目录已存在时跳过 makedirs（热路径：每次命中后二次调用免系统调用；
            # 首写仍保留建目录语义，缓存目录不存在时行为不变）；18. 安全改进：
            # 新目录以 0o700 创建（仅当前用户可读写，收敛敏感缓存暴露面）
            cache_dir = os.path.dirname(cache_file)
            if not os.path.isdir(cache_dir):
                ensure_llm_cache_dir(cache_dir)
            # 2026-09-26 全面审查（原子写，与 cross_file CF-8 / nodes._write_file_atomic
            # 同模式）：此前直接 open("w") + json.dump 非原子——--parallel 下两
            # worker 同键（同 prompt 材料 → 同 md5 → 同 cache_file）并发写时，
            # 另一方读侧可能观察到半截 JSON → json.load 抛错 → 静默降级重调
            # LLM（浪费 token + 延迟）。缓存文件键即内容 md5，并发写入的是
            # 逐字节相同的 JSON，原子替换可彻底消除半截读。
            payload = {
                "prompt": user_message,
                "system": self.system_prompt,
                "response": response,
                "timestamp": time.time(),
                # 19. 缓存创建者归属（Clinejection 教训）：写 uid 到文件头部，
                # 读侧 _lru_check_negative 之外的命中校验按归属校验，非本用户
                # 条目不命中（防跨用户/共享 CI 缓存投毒）。空串 = uid 不可得
                # （读侧跳过校验，历史口径）。
                "creator_uid": _cache_creator_label(),
            }
            tmp_file = f"{cache_file}.tmp.{threading.get_ident()}"
            try:
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False)
                # 18. 安全改进：缓存文件收敛 0o600（仅当前用户可读），
                # 防完整 prompt + 响应（可能夹带代码片段）被同机其他用户读取
                secure_cache_file(tmp_file)
                os.replace(tmp_file, cache_file)
                tmp_file = ""  # 替换成功，无需清理
            finally:
                if tmp_file:
                    # 替换失败（OSError）时清理临时文件，避免残留堆积
                    with suppress(OSError):
                        os.unlink(tmp_file)
            _lru_store(lru_key, response)  # 回填 L1 + 清除该键负缓存条目（文件已存在）
            logger.info("LLM 缓存已写入: %s", cache_key[:50])
            # 5.1 P2 修复（2026-10-01 全面审查）：语义命中后未 upsert 新响应，
            # docstring 宣称"下轮可命中"与实现不符——此前 LLM 调用成功写文件后
            # 不同步入语义索引，"省 token"完全依赖 60s 节流目录重扫（同任务内
            # 连续相似 prompt 若 L1/L1.5 未命中、新响应又未经 60s 重扫入索引，
            # 后续轮次仍走真实 LLM 调用）。现写文件成功后即时 upsert（嵌入失败
            # 静默跳过，零默认外部依赖、不阻断主流程）。
            try:
                from src.agents.semantic_cache import _semantic_cache_enabled, get_semantic_index

                if _semantic_cache_enabled():
                    get_semantic_index().upsert(cache_file, user_message, response)
            except Exception:
                logger.debug("语义缓存 upsert 失败（保守跳过，不影响文件缓存）", exc_info=True)
        except Exception as e:
            logger.debug("缓存写入失败: %s", e)

        return response

    def _call_llm(
        self,
        user_message: str,
        max_retries: int = _DEFAULT_LLM_MAX_RETRIES,
        temperature: float | None = None,
        complexity_class: str | None = None,
    ) -> str:
        """
        调用 LLM 并返回文本响应。
        失败时进行最多 max_retries 次重试，采用指数退避策略（1s, 2s, 4s）。
        OpenAI 兼容路径与 zai SDK 路径均套 _retry_with_exponential_backoff
        （0.6 轮次 P0-1 修复：此前 OpenAI 路径单次调用零重试，网络抖动即触发
        跨模型/跨 API 故障转移）；重试耗尽后自动切换到备用 API 继续尝试。
        支持 OpenAI 兼容接口和 zai SDK（BigModel）两种调用路径。

        Args:
            user_message: 用户消息内容。
            max_retries: 单次 API 的最大重试次数，默认 3 次。
            temperature: 采样温度覆盖（3.3 动态策略接线用）；None 时使用
                config.TEMPERATURE。注意 zai SDK 路径当前不支持温度参数，
                该覆盖仅对 OpenAI 兼容路径生效（保守口径）。
            complexity_class: P0 1.2 复杂度档位（"simple"/"medium"/"complex"）。
                提供时传递给 APIManager 按档位选择 LLM 实例（同模型多 provider
                端点场景下路由到对应复杂度档位）；None 走历史策略。

        Returns:
            LLM 返回的文本字符串。

        Raises:
            RuntimeError: 所有 API 和重试均失败时抛出。
        """
        # P0 1.2：复杂度感知路由——complexity_class 非 None 时经下方
        # _reorder_api_groups_by_complexity 按档位重排 api_groups（simple → 低成本
        # 端点在前，complex → 高成本端点在前）；路由不依赖 APIManager kwargs
        # 注入，故无需额外构造调用参数字典（2026-09-26 死代码清理：此前构建的
        # 死变量从未被任何调用点引用，已删）。
        # 延迟导入：避免循环导入（base_agent 被 planner/generator/debugger 导入）
        from langchain_core.messages import HumanMessage, SystemMessage

        # 获取所有已配置的 API，未配置时直接报错不进入重试循环
        all_configs = _get_all_api_configs()
        if not all_configs:
            raise RuntimeError("未配置任何 LLM API")

        # 5.4 任务级预算硬上限：上一 LLM 调用记账后超限（cost_budget 线程
        # 局部标志）时拒绝本次调用（快速失败，不再空转烧 token）。
        # 开关 COST_BUDGET_ENABLE 默认 false：is_budget_exceeded() 恒 False，
        # 历史口径零变化。
        from src.graph.cost_budget import is_budget_exceeded

        if is_budget_exceeded():
            raise _budget_exceeded_error()

        # 记录最后一次异常，用于最终报错信息
        last_error: Exception | None = None

        # 0.7 债务项 2.2：单次调用的全局墙钟总预算。故障转移 × 模型 × 重试的
        # 最坏组合可达数十分钟，超出预算即快速失败，避免单任务卡死整个基准跑批。
        deadline = time.time() + LLM_CALL_BUDGET_SECONDS

        # 按 base_url 分组配置，支持同一 API 内切换模型
        # 结构：{base_url: [(api_key, model_name), ...]}
        api_groups: dict[str, list[tuple[str, str]]] = {}
        for api_key, base_url, model_name in all_configs:
            if base_url not in api_groups:
                api_groups[base_url] = []
            api_groups[base_url].append((api_key, model_name))

        # P0 1.2 复杂度感知路由：complexity_class 非 None 且配置了多 LLM 实例时，
        # 按档位重排 api_groups（complex → 高 cost_weight 端点在前，simple → 低
        # cost_weight 端点在前），使同一模型的多 provider 端点按复杂度分级路由。
        # 单实例时排序无效果（历史行为不变）。
        if complexity_class is not None and len(all_configs) > 1:
            api_groups = _reorder_api_groups_by_complexity(api_groups, all_configs, complexity_class)

        # 依次尝试每个 API 组（自动故障转移：主 API 失败 → 备用 API）
        # 同一 API 内也尝试不同模型（额度用完时自动切换）
        # P0 1.2 修复：eff_temperature = 调用方覆盖值 or config 默认值
        eff_temperature = temperature if temperature is not None else TEMPERATURE

        for base_url, models in api_groups.items():
            # 判断当前 API 是否为 zai SDK 兼容接口，分流至不同调用路径
            is_zai = _is_zai_compatible(base_url)

            for api_key, model_name in models:
                # 每次尝试新模型前先查预算，超出即快速失败（不再空耗剩余组合）
                if time.time() > deadline:
                    raise RuntimeError(f"LLM 调用超过全局预算 {LLM_CALL_BUDGET_SECONDS}s，快速失败")
                try:
                    if is_zai:
                        # BigModel 等非 OpenAI 兼容接口：使用 zai SDK 专属调用
                        text = _call_zai(api_key, base_url, model_name, self.system_prompt, user_message, max_retries)
                    else:
                        # OpenAI 兼容接口：复用缓存的 ChatOpenAI 客户端（连接池跨调用复用）
                        # P0-1 修复（0.6 轮次性能审计）：此前 llm.invoke 单次调用零重试——
                        # 一次网络抖动/429 即跨模型切换或任务级失败。现套通用指数退避
                        # （_retry_with_exponential_backoff，base_wait=1s：1s/2s/4s），
                        # 语义与 zai 路径对齐；重试耗尽才进入故障转移。
                        llm = _get_or_create_chat_client(model_name, eff_temperature, api_key, base_url)

                        def _invoke_openai(
                            client: Any = llm,
                            model: str = model_name,
                        ) -> str:
                            response = client.invoke(
                                [
                                    SystemMessage(content=self.system_prompt),
                                    HumanMessage(content=user_message),
                                ],
                                timeout=LLM_TIMEOUT,
                            )
                            text_ = response.content.strip()
                            # 空响应视为失败，触发重试（而非直接跨模型切换）
                            if not text_:
                                raise RuntimeError("LLM 返回空响应")
                            # token 消耗统计（LangChain 响应的 usage_metadata，可能缺失）
                            _record_response_usage(getattr(response, "usage_metadata", None), model)
                            return text_

                        text = _retry_with_exponential_backoff(
                            _invoke_openai,
                            max_retries,
                            base_wait=1,
                        )

                    # 打印成功日志
                    api_id = base_url.split("/")[2] if "/" in base_url else base_url
                    logger.info("API 调用成功 (api=%s, model=%s)", api_id, model_name)
                    return text

                except Exception as e:
                    # O15（2026-09-29 审查 P2）：限流（429 RateLimitError）
                    # 可重试分支——此前 except Exception 吞掉所有异常统一
                    # continue（跨模型切换），外层 except RateLimitError 分支
                    # 永远不可达。现补限流识别：命中 openai.RateLimitError /
                    # httpx.HTTPStatusError 429 时，在**当前模型内**等待
                    # Retry-After（或指数退避）后重试（不立即跨模型切换），
                    # 避免"一个 429 就把所有模型端点轮一遍"的浪费。
                    _is_rate_limit = _is_rate_limit_error(e)
                    if _is_rate_limit:
                        _retry_after = _extract_retry_after_seconds(e)
                        # 限流退避：Retry-After 优先，未设则用基础等待 2s，统一封顶 30s
                        _wait = min(max(_retry_after or 0.0, 2.0), 30.0)
                        logger.warning(
                            "O15 限流（429）模型 %s：等待 %.1fs 后重试（Retry-After=%s）",
                            model_name,
                            _wait,
                            f"{_retry_after}s" if _retry_after else "未设",
                        )
                        time.sleep(_wait)
                        # 限流重试一次后再走常规故障转移（continue 到下一模型）
                        continue
                    # 记录当前模型失败原因，继续尝试同 API 的下一个模型
                    # 异常文本可能携带请求头/URL 中的 API Key（部分 SDK 会把
                    # Authorization 头打进报错信息），统一走脱敏后再落日志（P2-8）
                    last_error = e
                    logger.warning("模型 %s 调用失败: %s，尝试同 API 的其他模型", model_name, _redact_log_text(str(e)))
                    continue

            # 当前 API 的所有模型都失败，记录并尝试下一个 API
            api_id = base_url.split("/")[2] if "/" in base_url else base_url
            logger.warning("API %s 所有模型均失败，尝试备用 API", api_id)
            continue

        # 所有 API 均失败，抛出包含最后一次异常信息的 RuntimeError
        raise RuntimeError(f"LLM 调用失败，已尝试所有 API: {_redact_log_text(str(last_error))}") from last_error

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """
        从 LLM 输出中提取 JSON 对象（委托给公共工具函数）。

        Args:
            text: LLM 返回的原始文本。

        Returns:
            解析后的字典对象。

        Raises:
            json.JSONDecodeError: 无法找到有效 JSON 时抛出。
        """
        return extract_json_object(text)

    @staticmethod
    def _extract_python_code(text: str) -> str:
        """
        从 LLM 输出中提取 Python 代码块（委托给公共工具函数）。

        Args:
            text: LLM 返回的包含代码的文本。

        Returns:
            提取出的 Python 代码字符串（无 markdown 包裹）。
        """
        return extract_code_block(text, language="python")

    @staticmethod
    def truncate_code(
        code: str,
        max_chars: int = _CODE_MAX_CHARS,
        focus_function: str | None = None,
        focus_depth: int | None = None,
    ) -> str:
        """截断超长代码，避免 LLM token 浪费。

        截取策略（P0 优化，解决 SWE-bench 大文件上下文丢失问题）：
        1. 代码在预算内 → 原样返回；
        2. 否则先做基于 AST 的智能截取（保留 import + 目标函数及其
           调用链 focus_depth 层依赖的辅助函数，超长函数体首尾截断；
           P0 1.2 焦点存在时追加 [PATCH_INGREDIENTS] 契约块），
           优先于"头尾各半"硬截断——硬截断对数百行源文件会让 LLM 看不到
           目标函数；
        3. AST 截取仍超预算时：焦点函数解析成功（focus_resolved=True，
           已含契约块）→ 保留聚焦结果不硬截断（契约块位于尾部，头尾截断
           会破坏 P0 1.2 语义）；解析失败/无焦点（focus_resolved=False）
           → 回退字符级头尾截断兜底（历史口径）。

        Args:
            code: 原始代码字符串。
            max_chars: 最大允许字符数，默认 3000（CODE_MAX_CHARS 可上调）。
            focus_function: 焦点函数名（如 "divide"）。提供时按函数维度
                截取上下文；None 时保留全部顶层函数再按预算裁剪。
            focus_depth: 调用链展开层数（P0 1.1 分层代码压缩）。None 时
                读 CODE_FOCUS_DEPTH 环境变量（默认 1 = 历史行为）；
                仅当 focus_function 提供且存在于源码时生效。

        Returns:
            截断后的代码字符串。
        """
        if len(code) <= max_chars:
            return code

        depth = CODE_FOCUS_DEPTH if focus_depth is None else max(1, focus_depth)
        # 第一层：AST 智能截取（code_context 模块无对外部依赖，顶层导入安全）
        # P0 1.2：焦点函数存在时截取结果已追加 [PATCH_INGREDIENTS] 契约块，
        # 用 extract_focused_code_detail 拿 (code, focus_resolved) 二元组，
        # focus_resolved=False（源码无法解析/无函数体/焦点不在源码中）时
        # 契约块未追加，需回退字符级头尾截断兜底（历史口径）。
        from src.tools.code_context import extract_focused_code_detail

        focused, focus_resolved = extract_focused_code_detail(
            code, focus_function=focus_function, max_chars=max_chars, depth=depth
        )
        if len(focused) <= max_chars:
            logger.info(
                "代码已按 AST 智能截取：%d → %d 字符（focus=%s）", len(code), len(focused), focus_function or "*"
            )
            return focused

        # AST 截取超预算：焦点已解析成功（契约块已追加，focus_resolved=True）
        # 时保留聚焦结果不再硬截断——头尾截断会破坏尾部 [PATCH_INGREDIENTS]
        # 契约块的语义（P0 1.2）；解析失败/无焦点时走字符级兜底。
        if focus_resolved:
            logger.info(
                "P0 1.2 AST 聚焦结果超预算（%d → %d 字符，focus=%s），保留聚焦+契约块不硬截断",
                len(code),
                len(focused),
                focus_function or "*",
            )
            return focused

        # 第二层：字符级头尾截断兜底（保留 import 头 + 尾部，中间省略）
        head_len = max_chars // 2
        tail_len = max_chars - head_len - len(_CODE_TRUNCATED_MSG.format(max=max_chars))
        head = code[:head_len]
        tail = code[-tail_len:] if tail_len > 0 else ""
        truncated = head + _CODE_TRUNCATED_MSG.format(max=max_chars) + tail
        logger.info("代码已字符级截断：%d → %d 字符", len(code), len(truncated))
        return truncated


# ─── 进程内 LRU 维护接口（测试 / 缓存清理钩子）───────────────────────────────
# AITESTER_LLM_CACHE_DIR 变更或外部清理 src/cache 后，进程内 LRU 可能持有
# 已被删除条目的响应值。由于 LRU 命中值与文件内容一致时行为等价（响应不可变），
# 该风险可接受；需要强一致口径（如测试）时调用 clear_llm_lru_cache() 清空。
def clear_llm_lru_cache() -> None:
    """清空 LLM 文件缓存的进程内 LRU（含负缓存），恢复纯文件读取语义。

    同步清除 llm_client 的缓存开关/目录环境变量记忆（AITESTER_LLM_CACHE /
    AITESTER_LLM_CACHE_DIR 经 monkeypatch.setenv 被测试修改后，必须显式清记忆
    才能恢复"每次调用读环境变量"的历史口径，否则进程内记忆值继续生效）。
    """
    _lru_clear()
    from src.agents.llm_client import clear_llm_cache_option_memory

    clear_llm_cache_option_memory()


__all__ = [
    "BaseAgent",
    "clear_llm_lru_cache",
]
