"""
智能体基类模块：封装智能体通用行为，为所有子类提供统一的接口。

所有智能体（Planner、Generator、Debugger）均继承此类，
共享 LLM 调用、JSON 解析、代码提取等通用能力。

LLM 客户端管理（客户端缓存 / 指数退避重试 / 日志脱敏 / token 统计 / 配置获取 /
文件缓存开关）已拆分到 `src/agents/llm_client.py`（代码可维护性
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
    _ABNORMAL_FINISH_REASONS,
    _DEFAULT_LLM_MAX_RETRIES,
    _cache_creator_label,
    _get_all_api_configs,
    _get_llm_config,
    _get_or_create_chat_client,
    _llm_cache_dir,
    _llm_cache_enabled,
    _openai_extra_body,
    _raise_if_budget_exceeded,
    _record_actual_request_config,
    _record_response_usage,
    _redact_log_text,
    _retry_with_exponential_backoff,
    _thread_local_api_override,
    cache_creator_ok,
    clear_last_request_config,
    get_last_request_config,
    json_output_mode_enabled,
    request_identity_fingerprint,
    request_identity_material,
)
from src.agents.rogue_monitor import rogue_monitor_enabled
from src.utils.env_utils import env_flag_opt_out
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
# P0 止血（缓存记账缺口）：LRU 正缓存并行存"该 key 对应的上次实际调用 token
# 数"，供 LRU 快路径命中时还原 cache_avoided_tokens（此前快路径拿不到 token、
# 只能记 0，导致进程内重复命中的"避免 token"被系统性低估）。
# AT（2026-10-21）：值可能是文件里的原始 tokens（坏记账值原样保留，命中时由
# record_cache_hit_usage 统一判定并披露），也可能是 None（本次调用发生写拒绝，
# 消耗量未知）。
_lru_tokens: dict[tuple[str, str, float | None], Any] = {}
_lru_lock = threading.Lock()


def _lru_lookup(key: tuple[str, str, float | None]) -> str | None:
    """进程内 LRU 命中时直接返回值（O(1)，含 move_to_end）。"""
    with _lru_lock:
        if key in _lru_cache:
            _lru_cache.move_to_end(key)
            return _lru_cache[key]
        return None


def _lru_lookup_tokens(key: tuple[str, str, float | None]) -> Any:
    """读取 LRU 中该 key 对应的上次实际调用 token 数（0 = 无记录；原值交由写入口判定）。"""
    with _lru_lock:
        return _lru_tokens.get(key, 0)


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


def _lru_store(key: tuple[str, str, float | None], value: str | None, tokens: Any = 0) -> None:
    """进程内 LRU 写入（None 记为负缓存，容量超限时淘汰最久未用条目）。

    非 None 值写入 LRU 正缓存的同时清除该键的负缓存条目（文件写入成功
    = "该键文件不存在"判定失效，TTL 窗口内同键调用不得再跳过文件重读）。

    A23（2026-10-18 第三方审查 P2）：`_lru_tokens` 是 `_lru_cache` 的并行
    记账字典（缓存命中时还原"避免的 token"），历史上只在写入时赋值——
    正缓存按 `_LRU_MAXSIZE` 淘汰 / `_lru_clear()` 清空时 tokens 字典既不
    淘汰也不清空，长程 benchmark 下成为永久增长的泄漏。现与 `_lru_cache`
    严格同步：淘汰条目时同步弹出其 token 记录；写负缓存（条目转为负缓存，
    正缓存失效）时同样弹出残留 token；容量由正缓存淘汰唯一驱动，故
    `_lru_tokens` 天然受 `_LRU_MAXSIZE` 约束（键集 ⊆ `_lru_cache` 键集）。
    """
    with _lru_lock:
        if value is None:
            _lru_negatives[key] = time.time()
            # 条目转入负缓存：正缓存值已不存在，token 记录失去宿主 → 同步移除
            # （防"先正后负"序列残留孤儿 token 键）
            _lru_tokens.pop(key, None)
            # 2026-09-26 round10 P2：负缓存与正缓存同容量上限（_LRU_MAXSIZE，
            # FIFO 淘汰）——旧实现无 cap，长程 benchmark（数千任务 × 温度
            # 变体）下从未被查的负缓存条目永久驻留，内存无界增长。超限
            # 淘汰最久未插入项（dict 插入序 = FIFO），口径与 LRU 一致
            while len(_lru_negatives) > _LRU_MAXSIZE:
                oldest_key = next(iter(_lru_negatives))
                del _lru_negatives[oldest_key]
            return
        _lru_cache[key] = value
        _lru_tokens[key] = tokens
        _lru_cache.move_to_end(key)
        _lru_negatives.pop(key, None)
        while len(_lru_cache) > _LRU_MAXSIZE:
            evicted_key, _evicted_value = _lru_cache.popitem(last=False)
            # A23：token 字典与正缓存同步淘汰（键集保持 ⊆ 正缓存键集）
            _lru_tokens.pop(evicted_key, None)


def _lru_clear() -> None:
    """清空进程内 LRU 与全部辅助结构（缓存目录/开关切换或外部清理时调用）。

    A23：清空范围必须覆盖 `_lru_tokens`（并行 token 记账）——M7 验收：
    `_LRU_MAXSIZE=2` 连续写 3 条后 `len(_lru_cache), len(_lru_tokens)` 为
    `2 2`（此前 `2 3`），clear 后为 `0 0`（此前 `0 3`）。
    """
    with _lru_lock:
        _lru_cache.clear()
        _lru_tokens.clear()
        _lru_negatives.clear()


def _budget_exceeded_error() -> Exception:
    """5.4 预算超限异常工厂（延迟构造，避免模块加载期对 cost_budget 的依赖）。

    D1（N-5）：按快照的实际生效单位取数——USD 口径取 consumed_usd/usd_limit
    （历史上无 USD 生产记账，该分支不可达；USD 接线后必须同口径，否则 USD
    触发时异常消息会把 token 数当美元展示，可诊断性失效）。

    A11（2026-10-18 第三方审查 P1）：单一实现在 `llm_client._budget_exceeded_error`
    ——重试前预算复查抛同一异常，不得各持一份单位口径。
    """
    from src.agents.llm_client import _budget_exceeded_error as _factory

    return _factory()


# ─── A09：有效请求身份（精确缓存键 / 语义索引分区）─────────────────────────
def _system_prompt_digest(system_prompt: str | None) -> str | None:
    """系统提示词的稳定摘要（A09 语义分区材料）。

    2026-10-19 第三方复核残留补修：历史身份材料只覆盖模型/参数/端点，
    精确缓存文件名虽另含完整 system 文本，但传给语义索引的分区键是
    `request_identity_fingerprint(identity)`——同一 user prompt、不同
    system（Planner vs Generator 等角色）指纹相同，语义路径可直接复用
    另一角色的响应。把 system 的 sha256 前 16 位纳入身份材料后，精确键与
    语义分区共享同一来源，跨 system 必然分区隔离。

    取摘要而非全文：身份 dict 会写入每个缓存 payload 并参与指纹计算，
    全文会让同目录条目体积与哈希成本随提示词线性增长；sha256 截断 16 位
    （64 bit）对缓存分区足够，碰撞概率可忽略。
    """
    if not system_prompt:
        return None
    return hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:16]


def _effective_request_identity(
    temperature: float | None,
    json_mode: bool,
    complexity_class: str | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """构造规范化的"有效请求身份"（A09，2026-10-18 第三方审查 P1）。

    历史缺陷（base_agent.py:386 一带）：精确缓存键 = prompt + system +
    （仅显式 temperature）+ json_mode 布尔 + （隔离开启时）模型名 + namespace，
    **遗漏实际操作参数量**：调用方未显式传 temperature 时实际生效的默认
    温度（config.TEMPERATURE）、`_openai_extra_body()` 注入的
    thinking / reasoning_effort / max_tokens、`json_output_mode_enabled()`
    与 json_mode 共同决定的 JSON 绑定实际值、以及真实请求端点（同 model_name
    多 provider 场景）。重启进程/切换环境变量后，同一 prompt 仍可能命中
    旧配置下写入的响应（缓存串味）。

    本函数把"真实请求将携带/生效的全部身份材料"规范化为 dict（供
    `request_identity_material()` 稳定哈希与缓存 payload 记录；语义缓存用
    `request_identity_fingerprint()` 同一材料做分区）。字段：

    - ``v``：身份版本号（材料语义升级时递增，旧键自然失效）。当前 **3**
      （2026-10-19：加入 ``system`` 摘要；v2 → v3 使旧精确缓存文件自然失效，
      旧格式只读回退仍按 `_legacy_cache_identity_compatible` 的包络规则处理）；
    - ``model`` / ``endpoint``：**真实请求链首个配置**的模型与端点
      （`_get_all_api_configs()` 已按 A10 改为线程局部配置优先；端点经
      脱敏，凭证不进入键材料）。`AITESTER_CACHE_ISOLATE_MODEL=0` 显式
      退回"跨模型复用"历史口径时两者记 ``None``（用户显式选择不隔离）；
    - ``system``：system_prompt 的 sha256 前 16 位（A09 2026-10-19 补修：
      不同角色/指令的系统提示词必须分区隔离；None = 无 system 材料）。
      取摘要而非全文，避免身份 dict 写入每个缓存 payload 时体积随提示词增长；
    - ``temperature``：实际生效采样温度 = 显式覆盖值，否则 config.TEMPERATURE；
      该字段描述**实际发出的请求**，身份材料与实际请求保持同一口径；
    - ``json_object``：JSON 输出**实际生效值** = json_mode 且
      LLM_JSON_MODE≠off；
    - ``thinking`` / ``reasoning_effort`` / ``max_tokens``：请求体实际注入值
      （来自 `_openai_extra_body()`，未配置为 None）；
    - ``namespace``：AITESTER_CACHE_NAMESPACE（多 seed 实验隔离材料）；
    - ``routing``：复杂度路由档位（复杂/简单档会改变"优先请求哪个端点实例"，
      属于有效请求身份的一部分；None = 历史默认路由）。

    Args:
        temperature: 调用方显式温度覆盖（None = 使用默认温度）。
        json_mode: 调用点是否请求结构化 JSON 输出。
        complexity_class: 复杂度路由档位（"simple"/"medium"/"complex"/None）。
        system_prompt: 本次请求的系统提示词（None = 无 system 材料）。
            生产调用点必须传 `self.system_prompt`——语义索引分区依赖该维度。

    Returns:
        可 JSON 序列化的身份 dict（同一请求设置必产出逐字节相同材料）。
    """
    from src.utils.logging_utils import mask_sensitive_info

    configs = _get_all_api_configs()
    primary: tuple[str, str, str] | None = configs[0] if configs else None
    isolate = env_flag_opt_out("AITESTER_CACHE_ISOLATE_MODEL")
    extra = _openai_extra_body()
    return {
        "v": 3,
        "model": (primary[2] if primary else None) if isolate else None,
        "endpoint": (mask_sensitive_info(primary[1]) if primary else None) if isolate else None,
        "system": _system_prompt_digest(system_prompt),
        "temperature": round(float(temperature if temperature is not None else TEMPERATURE), 6),
        "json_object": bool(json_mode and json_output_mode_enabled()),
        "thinking": extra.get("thinking"),
        "reasoning_effort": extra.get("reasoning_effort"),
        "max_tokens": extra.get("max_tokens"),
        "namespace": os.environ.get("AITESTER_CACHE_NAMESPACE", "").strip(),
        "routing": complexity_class,
    }


def _exact_cache_file(identity: dict[str, Any], user_message: str, system_prompt: str) -> str:
    """按规范化的有效请求身份计算精确缓存文件路径（A09）。

    键材料 = `user_message \\x00 system_prompt \\x00 id:<身份稳定材料>`；文件名
    取 md5 前 16 位（与历史一致）。身份材料参与后，不同模型/端点/温度/
    thinking/JSON/输出上限/namespace 的组合必然映射到不同文件。

    Args:
        identity: `_effective_request_identity()` 的返回值。
        user_message: 用户消息文本。
        system_prompt: System Prompt 文本。

    Returns:
        规范化的缓存文件绝对路径（目录来自 `_llm_cache_dir()`）。
    """
    material = request_identity_material(identity)
    cache_key = f"{user_message}\x00{system_prompt}\x00id:{material}"
    digest = hashlib.md5(cache_key.encode("utf-8")).hexdigest()[:16]
    return os.path.normpath(os.path.join(_llm_cache_dir(), f"{digest}.json"))


def _legacy_cache_file(
    user_message: str,
    system_prompt: str,
    temperature: float | None,
    json_mode: bool,
) -> str:
    """按 A09 修复前的历史公式重算旧缓存文件路径（仅用于只读兼容回退）。

    历史键材料（逐字节复刻，顺序与旧实现一致）：prompt + \\x00 + system +
    （显式 temperature）+（json_mode=True 时 jm1）+（隔离开启且模型名有效时
    m<model>）+（namespace 非空时 ns<namespace>），最后 md5 前 16 位为文件名。
    """
    legacy_key = f"{user_message}\x00{system_prompt}"
    if temperature is not None:
        legacy_key += f"\x00t{temperature}"
    if json_mode:
        legacy_key += "\x00jm1"
    if env_flag_opt_out("AITESTER_CACHE_ISOLATE_MODEL"):
        from src.agents.llm_client import get_first_valid_model_name

        _iso_model = get_first_valid_model_name()
        if _iso_model:
            legacy_key += f"\x00m{_iso_model}"
    _cache_ns = os.environ.get("AITESTER_CACHE_NAMESPACE", "").strip()
    if _cache_ns:
        legacy_key += f"\x00ns{_cache_ns}"
    digest = hashlib.md5(legacy_key.encode("utf-8")).hexdigest()[:16]
    return os.path.normpath(os.path.join(_llm_cache_dir(), f"{digest}.json"))


def _legacy_cache_identity_compatible(identity: dict[str, Any]) -> bool:
    """旧格式缓存文件（A09 修复前写入）是否仍可作为只读命中候选。

    **旧缓存兼容策略（显式声明与边界）**：旧文件只记录了 prompt/system/
    response/tokens/creator_uid，没有记录写入时的有效请求身份，因此**无法
    自证**它是在当前配置下产生的。为兼顾"历史缓存不整体失效"与"不得串味"，
    仅在当前身份处于**历史默认包络**时接受旧文件：

    - `json_object` 为 False（无 JSON 绑定；旧 jm1 键无法证明有效开关一致）；
    - thinking 恰为默认 disabled、未设 reasoning_effort / max_tokens
      （任何输出控制生效都属"身份充足"，此时只用新键、旧文件不命中）；
    - namespace 为空（多 seed 实验身份显式隔离，不回退旧文件）；
    - routing 为 None（复杂度路由会改变优先端点实例，旧键未覆盖）。

    满足条件时仍存在**有界残余风险**（已在 docstring 说明）：旧文件写入后
    若仅改变了不参与旧键的默认 TEMPERATURE / 端点（同 model 换 provider）
    再改回默认包络，旧条目理论上仍可能被命中。该风险是"旧缓存可复用"的
    代价；正式实验应显式 `AITESTER_LLM_CACHE=0`（仓库既有约定）或清理
    缓存目录。反之，任何"身份充足"的配置（thinking/reasoning/max_tokens/
    JSON/namespace 改变）都不会回退旧文件——旧缓存不误命中。

    system 维度不受旧键公式遗漏影响：`_legacy_cache_file` 的键材料显式含
    system 文本，读侧还要求 `cached_data["system"] == self.system_prompt`，
    因此回退路径不会跨 system 命中（A09 2026-10-19 补修说明）。
    """
    if identity.get("json_object"):
        return False
    if identity.get("thinking") != {"type": "disabled"}:
        return False
    if identity.get("reasoning_effort") is not None:
        return False
    if identity.get("max_tokens") is not None:
        return False
    if identity.get("routing") is not None:
        return False
    return not identity.get("namespace")


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


def _pin_thread_api_group(
    api_groups: dict[str, list[tuple[str, str]]],
    override: tuple[str, str, str] | None,
) -> dict[str, list[tuple[str, str]]]:
    """把线程局部显式分配的端点组钉到请求链首位（A10 优先级契约）。

    优先级契约（2026-10-19 复核残留补修后明确）：

        **显式任务分配 > 复杂度路由 > 全局配置顺序**

    背景：`_reorder_api_groups_by_complexity` 按 cost_weight 重排 base_url 组，
    可能把另一端点排到显式分配之前——`_get_all_api_configs()` 里"override
    居首"的保证会被随后的重排覆盖。本函数在重排之后重新钉住 override 所在
    组，并在组内把 override 的三元组提到首位（同 base_url 多模型的形状）。

    Args:
        api_groups: `{base_url: [(api_key, model_name), ...]}`（可能已被
            复杂度路由重排）。
        override: 线程局部三元组（api_key, base_url, model_name）；None 或
            半截配置时不改动顺序（与 `_get_all_api_configs` 同口径）。

    Returns:
        新的有序字典；override 存在且其 base_url 组在场时该组居首，
        组内 override 条目居首。原字典不被修改。
    """
    if not override or not all(override):
        return api_groups
    api_key, base_url, model_name = override
    group = api_groups.get(base_url)
    if group is None:
        # 防御：override 完整但其 base_url 组不在链中（理论不可达——
        # _get_all_api_configs 已把它放在 all_configs 首位）→ 保持原序。
        return api_groups
    pinned_models = [(k, m) for k, m in group if (k, m) == (api_key, model_name)]
    pinned_models.extend((k, m) for k, m in group if (k, m) != (api_key, model_name))
    pinned: dict[str, list[tuple[str, str]]] = {base_url: pinned_models}
    pinned.update({k: v for k, v in api_groups.items() if k != base_url})
    return pinned


class BaseAgent:
    """
    所有智能体的公共基类。

    封装了与 LLM 交互的底层逻辑，包括：
    - 初始化 LangChain ChatOpenAI 客户端（复用连接池缓存）
    - 带重试的 LLM 调用（指数退避 + API 自动切换）
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
        json_mode: bool = False,
    ) -> str:
        """
        带缓存的 LLM 调用方法。

        首次调用时执行完整的 LLM 请求并缓存结果，
        后续相同输入直接返回缓存响应，节省 token 和延迟。

        缓存分层（性能优化）：
        1. 进程内 LRU 快路径：命中时零磁盘 IO 直接返回；
        2. 文件缓存（默认 ~/.cache/aitester/llm/*.json，可经
           AITESTER_LLM_CACHE_DIR 覆盖）：LRU 未命中时完整读文件回填，
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
            json_mode: 结构化 JSON 调用标记（2026-10-14 LLM_JSON_MODE，
                DeepSeek JSON Output）。仅期待 JSON 对象的调用点传 True
                （Planner 测试计划 / Debugger 补丁/批评/分类）；True 时
                （且 LLM_JSON_MODE≠off）对请求绑定
                response_format={"type":"json_object"} 并计入缓存键——
                与历史非 JSON 口径的响应严格隔离（同 prompt 不同模式
                不共享缓存条目）。False 时全路径与历史逐字节一致。

        缓存身份（A09，2026-10-18 第三方审查 P1；2026-10-19 复核残留补修）：
        精确缓存键由**规范化的有效请求身份**派生（`_effective_request_identity`：
        实际生效温度、thinking/reasoning_effort/max_tokens、JSON 输出实际绑定值、
        真实请求链首选的模型与端点、实验 namespace、复杂度路由档位、**system
        提示词摘要**），语义缓存按同一身份的指纹分区。不同请求设置（含隐式
        默认值）与不同 system（角色/指令）不再共用缓存条目。

        旧缓存兼容策略（显式声明，勿删）：A09 之前的旧缓存文件没有身份字段、
        无法自证写入配置；本方法仅在当前身份处于**历史默认包络**（未绑定 JSON、
        thinking=disabled、无 reasoning_effort/max_tokens、namespace 为空、
        无复杂度路由）时，
        按旧公式重算文件路径做**只读回退**，且要求 prompt/system/creator 全量
        校验一致。任何"身份充足"的配置（上述任一项非默认 / 显式 JSON 模式）
        只用新键，**旧文件不命中**（不误命中优先于旧缓存复用率）。见
        `_legacy_cache_identity_compatible` 的残余风险说明。

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
        # json_mode 仅在 True 时透传（False 时调用签名与历史逐字节一致）
        _jm_kwargs: dict[str, Any] = {"json_mode": True} if json_mode else {}
        if not _llm_cache_enabled():
            if complexity_class is not None:
                if temperature is not None:
                    return self._call_llm(
                        user_message,
                        max_retries,
                        temperature=temperature,
                        complexity_class=complexity_class,
                        **_jm_kwargs,
                    )
                return self._call_llm(user_message, max_retries, complexity_class=complexity_class, **_jm_kwargs)
            if temperature is not None:
                return self._call_llm(user_message, max_retries, temperature=temperature, **_jm_kwargs)
            return self._call_llm(user_message, max_retries, **_jm_kwargs)

        # ─── A09（2026-10-18 第三方审查 P1）：缓存键材料 = 规范化有效请求身份 ───
        # 历史键 = prompt + system +（仅显式 temperature）+ json_mode 布尔 +
        # （隔离开启时）首个 model_name + namespace——**遗漏实际生效参数**：
        # 默认温度、thinking/reasoning_effort/max_tokens（_openai_extra_body 注
        # 入）、JSON 绑定实际生效值、真实请求端点。切配置重启后同一 prompt 仍
        # 可能命中旧响应（跨模型/参数/seed 串味）。现改为：
        #   identity = _effective_request_identity(temperature, json_mode)
        #   键材料   = user_message \x00 system_prompt \x00 id:<身份规范材料>
        # 同一身份必产出逐字节相同材料（排序 JSON），不同身份必不同文件。
        #
        # 旧缓存兼容策略（显式，见 _legacy_cache_identity_compatible）：
        # 旧文件无身份字段、无法自证，故仅在"当前身份处于历史默认包络"
        # 时做只读回退；身份充足（thinking/reasoning/max_output/JSON/namespace
        # 任一非默认、或显式 JSON 模式）时只用新键，旧文件不误命中。
        identity = _effective_request_identity(temperature, json_mode, complexity_class, self.system_prompt)
        identity_fp = request_identity_fingerprint(identity)
        cache_file = _exact_cache_file(identity, user_message, self.system_prompt)
        cache_key = f"{user_message}\x00{self.system_prompt}\x00id{identity_fp}"
        lru_key = (cache_file, user_message, temperature)

        # A09 旧格式缓存只读回退路径：默认包络下才计算（默认测试/生产环境
        # 通常命中此分支，历史缓存条目继续可用）；默认包络之外为 None。
        legacy_file: str | None = None
        if _legacy_cache_identity_compatible(identity):
            _legacy_file = _legacy_cache_file(user_message, self.system_prompt, temperature, json_mode)
            if _legacy_file != cache_file:
                legacy_file = _legacy_file

        # 快路径 1：进程内 LRU 命中（零磁盘 IO）
        hit = _lru_lookup(lru_key)
        if hit is not None:
            from src.agents.llm_client import record_cache_hit

            record_cache_hit(True)  # 15. 多进程缓存协调观测：LRU 命中
            # P0 止血（缓存记账缺口）：LRU 并行存 token（_lru_tokens），快路径
            # 命中同样能还原"避免的 token"；历史条目无 token 记录时记 0。
            from src.budget.token_usage import record_cache_hit_usage

            record_cache_hit_usage(_lru_lookup_tokens(lru_key))
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
            # A09：语义索引按**同一有效请求身份分区**检索（identity_fp）——
            # 历史实现 index.find(prompt) 在全索引上找余弦相似项，同 prompt
            # 的向量相似度可为 1，切模型/system/seed 后仍复用旧身份响应
            # （跨模型/seed 串味）。分区后只有身份完全一致的条目参与命中。
            _sem_hit = find_semantic_cache(cache_file, user_message, identity_key=identity_fp)
            if _sem_hit is not None:
                _sem_resp = _sem_hit[1]
                # D2 收口（2026-10-16 第十九轮评审）：语义缓存命中同样还原
                # "避免的 token"。LRU 快路径与文件路径已有记账（_lru_tokens
                # 并行存储 / 文件 tokens 字段），但语义路径此前直接 return，
                # cache_avoided_tokens 系统性低估。被命中条目是磁盘缓存文件
                # （索引只存响应文本），读其 tokens 字段计入独立口径
                # （不污染真实消耗语义）；文件缺失/损坏/无 tokens 字段时
                # 保守记 0（fail-closed，与 LRU 快路径"历史条目无 token
                # 记录时记 0"同口径）。同时把 token 数并入 LRU 回填，
                # 使同一 key 的后续 LRU 命中也能还原正确值。
                # AT（2026-10-21）：tokens 原值交给 record_cache_hit_usage 判定；
                # 不再 int() 归一（坏记账值曾让整次语义命中退化成真实调用）。
                # 键缺席 = 历史 0；在场 null = 本次调用写拒绝、消耗量未知。
                _sem_tokens: Any = 0
                try:
                    with open(_sem_hit[0], encoding="utf-8") as _sem_f:
                        _sem_tokens = json.load(_sem_f).get("tokens", 0)
                except (OSError, ValueError):
                    _sem_tokens = 0
                from src.budget.token_usage import record_cache_hit_usage

                record_cache_hit_usage(_sem_tokens)
                _lru_store(lru_key, _sem_resp, _sem_tokens)
                logger.info("5.1 语义缓存命中（复用响应，相似度 >= 阈值）: %s", cache_key[:50])
                return _sem_resp

        # 快路径 2：LRU 未命中——完整读**新格式**文件（含身份校验）才命中
        # （防 md5 前16位碰撞误命中 / 跨身份串味），命中后回填 LRU。
        # 命中要求：prompt/system 全量一致 + 写入时的 request_identity 与本次
        # 身份严格相等（A09）+ 创建者归属校验（Clinejection 教训）。
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
                    # A09：身份材料严格相等（旧格式文件无该字段 → 不命中）
                    and cached_data.get("request_identity") == identity
                    # 19. 创建者归属校验（Clinejection 教训）：uid 可得且条目
                    # 携带非空 creator_uid 时，非本用户条目不命中并告警（防
                    # 共享 CI / 多用户机器的跨用户缓存投毒）。历史无该字段的
                    # 条目视为兼容（不破坏既有缓存）；条目 creator_uid 为空
                    # 串（uid 不可得的平台）同样跳过校验。
                    and cache_creator_ok(cached_data.get("creator_uid"))
                ):
                    # AT（2026-10-21）：tokens 原值落 LRU 并交写入口判定——坏记账值
                    # 不得让一次身份校验通过的缓存命中退化成真实 LLM 调用；缺席 = 0，
                    # 在场 null = 消耗量未知（披露而非折零）。
                    _cached_tokens: Any = cached_data.get("tokens", 0)
                    _lru_store(lru_key, cached_data["response"], _cached_tokens)
                    # P0 止血（缓存记账缺口）：读缓存文件记录的上次实际调用 token，
                    # 计入 cache_avoided_tokens（独立口径，不污染真实消耗语义）。
                    from src.budget.token_usage import record_cache_hit_usage

                    record_cache_hit_usage(_cached_tokens)
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

        # A09 旧格式缓存（修复前写入、无 request_identity 字段）只读回退：
        # 仅在历史默认包络（_legacy_cache_identity_compatible）下尝试，并以
        # 旧公式重算文件路径 + prompt/system/creator 全量校验。命中不回写
        # 文件（只读兼容），但回填**新键** LRU 与 avoided-token 记账，后续
        # 同调用零磁盘 IO。身份充足（thinking/reasoning/max_output/JSON/
        # namespace 生效）时本分支为 None —— 旧文件不误命中。
        # 说明：本回退**不写负缓存**（`_lru_negatives` 只服务新格式键）——
        # 旧文件是过渡期产物，一次失败的 open 相对一次 LLM 调用可忽略；且
        # 避免旧键负缓存条目与"写成功后负缓存已清除"的既有口径混淆。
        if legacy_file is not None:
            try:
                with open(legacy_file, encoding="utf-8") as f:
                    legacy_data = json.load(f)
                if (
                    len(legacy_data.get("prompt", "")) == len(user_message)
                    and legacy_data.get("prompt") == user_message
                    and legacy_data.get("system") == self.system_prompt
                    # 新格式文件不得走旧回退（防身份材料被绕过校验）
                    and "request_identity" not in legacy_data
                    and cache_creator_ok(legacy_data.get("creator_uid"))
                ):
                    _legacy_tokens: Any = legacy_data.get("tokens", 0)
                    _lru_store(lru_key, legacy_data["response"], _legacy_tokens)
                    from src.budget.token_usage import record_cache_hit_usage

                    record_cache_hit_usage(_legacy_tokens)
                    logger.info("LLM 缓存命中 (旧格式只读回退): %s", cache_key[:50])
                    return legacy_data["response"]
            except FileNotFoundError:
                pass  # 无旧格式文件：正常未命中（不写负缓存，见上）
            except Exception as e:
                logger.debug("旧格式缓存读取失败: %s", e)

        # 未命中，执行实际调用（仅在成功时写缓存；失败如 403 额度用尽则不缓存）
        from src.agents.llm_client import record_cache_hit

        record_cache_hit(False)  # 15. 多进程缓存协调观测：文件缓存未命中
        # N11（2026-10-22 第三方复审 P2）：本次调用消耗改用**调用作用域**计量。
        # 历史实现取任务级 total_tokens 前后差值——专家池并发时共享同一累计器，
        # 差值会把其他线程的消耗算进本次（real=30，两条命中合计 avoided=40）。
        # 加锁只能防丢更新，不能给整次调用差分以隔离性；记录侧按线程维护
        # 作用域（token_usage.begin_call_scope），任务总账仍照常累加。
        from src.budget.token_usage import begin_call_scope, call_scope_had_rejection, call_scope_tokens

        begin_call_scope()
        # A10：清空"最近成功请求"记录后再调用——故障转移场景下真正返回响应的
        # 端点可能不是请求链首选；_call_llm 成功时会记录真实配置供下方 payload
        # 写入 response_identity（provenance/cache 标签取真实请求身份）。
        clear_last_request_config()
        if complexity_class is not None:
            if temperature is not None:
                response = self._call_llm(
                    user_message, max_retries, temperature=temperature, complexity_class=complexity_class, **_jm_kwargs
                )
            else:
                response = self._call_llm(user_message, max_retries, complexity_class=complexity_class, **_jm_kwargs)
        elif temperature is not None:
            response = self._call_llm(user_message, max_retries, temperature=temperature, **_jm_kwargs)
        else:
            response = self._call_llm(user_message, max_retries, **_jm_kwargs)
        # AT（2026-10-21）：本次调用若发生 token 写拒绝，作用域只是部分和 → 缓存
        # tokens 记 null（未知），不得把部分和当"避免的 token"全额复用。
        _call_tokens: Any = None if call_scope_had_rejection() else call_scope_tokens()
        # A10：真实响应来源（故障转移后可能 ≠ 请求链首选）。仅内存配置，写入
        # payload 时只保留脱敏端点 + 模型名（api_key 绝不落盘）。
        _actual_config = get_last_request_config()
        _response_identity: dict[str, Any] | None = None
        if _actual_config is not None:
            from src.utils.logging_utils import mask_sensitive_info

            _response_identity = {
                "model": _actual_config[2],
                "endpoint": mask_sensitive_info(_actual_config[1]),
            }

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
                # A09：写入时的规范化有效请求身份——读侧命中要求严格相等
                # （旧格式条目无该字段 → 只可能走默认包络的只读回退）。
                # 身份含实际生效温度/thinking/reasoning/max_tokens/JSON 绑定/
                # 模型/端点/namespace，重启进程或切配置后不再误命中。
                "request_identity": identity,
                # A10：真实响应来源（模型 + 脱敏端点）。请求首选端点失败而
                # 故障转移到备用端点时与 request_identity 不同；纯 provenance
                # 字段，不参与命中判定（api_key 不落盘）。
                "response_identity": _response_identity,
                # P0 止血（缓存记账缺口）：记录本次实际调用的 token 总数，
                # 供下次缓存命中时还原"若未命中会消耗"的量（见命中路径的
                # record_cache_hit_usage 读取）。
                "tokens": _call_tokens,
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
                    json.dump(payload, f, ensure_ascii=False, allow_nan=False)
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
            _lru_store(lru_key, response, _call_tokens)  # 回填 L1（含 token 供快路径记账）+ 清除负缓存
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
                    # A09：新条目按本次有效请求身份分区入索引（与 find 分区
                    # 同源 identity_fp），下轮近似 prompt 只在同身份内命中。
                    get_semantic_index().upsert(cache_file, user_message, response, identity_key=identity_fp)
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
        json_mode: bool = False,
    ) -> str:
        """
        调用 LLM 并返回文本响应。
        失败时进行最多 max_retries 次重试，采用指数退避策略（1s, 2s, 4s）。
        OpenAI 兼容路径套 _retry_with_exponential_backoff
        （0.6 轮次 P0-1 修复：此前 OpenAI 路径单次调用零重试，网络抖动即触发
        跨模型/跨 API 故障转移）；重试耗尽后自动切换到备用 API 继续尝试。

        Args:
            user_message: 用户消息内容。
            max_retries: 单次 API 的最大重试次数，默认 3 次。
            temperature: 采样温度覆盖（3.3 动态策略接线用）；None 时使用
                config.TEMPERATURE，实际发送的有效温度与
                `_effective_request_identity` 记录保持一致——缓存身份不与
                实际请求分叉。
            complexity_class: P0 1.2 复杂度档位（"simple"/"medium"/"complex"）。
                提供时传递给 APIManager 按档位选择 LLM 实例（同模型多 provider
                端点场景下路由到对应复杂度档位）；None 走历史策略。
            json_mode: 结构化 JSON 调用标记（默认 False）。True 且
                LLM_JSON_MODE≠off 时对 OpenAI 兼容请求绑定
                response_format={"type":"json_object"}（DeepSeek JSON
                Output，保证合法 JSON；提示侧"必须指示输出 JSON"的前置
                条件由调用点保证——Planner/Debugger 提示均含 JSON 字样
                与格式示例，2026-10-14 逐一核查）。False 时请求体与历史逐字节
                一致。响应 finish_reason ∈ {length, insufficient_system_
                resource}（截断/资源中断）视为可恢复失败重试，不把残缺
                内容交给下游解析。

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
        from src.budget.cost_budget import BudgetExceededError, is_budget_exceeded

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

        # A10 优先级契约（2026-10-19 复核残留补修）：显式任务分配 > 复杂度路由 >
        # 全局顺序。复杂度重排按 cost_weight 排序可能把另一 base_url 组提到
        # 显式分配之前，因此在重排之后重新钉住分配组；无 override 时零行为变化。
        api_groups = _pin_thread_api_group(api_groups, _thread_local_api_override())

        # 依次尝试每个 API 组（自动故障转移：主 API 失败 → 备用 API）
        # 同一 API 内也尝试不同模型（额度用完时自动切换）
        # P0 1.2 修复：eff_temperature = 调用方覆盖值 or config 默认值
        eff_temperature = temperature if temperature is not None else TEMPERATURE
        # 2026-10-14 LLM_JSON_MODE（DeepSeek JSON Output）：调用点显式
        # json_mode=True 且环境开关非 off 时，对请求绑定
        # response_format={"type":"json_object"}（默认 on；off=历史口径，
        # 请求体逐字节一致，供旧批次复现）。
        eff_json = bool(json_mode and json_output_mode_enabled())

        for base_url, models in api_groups.items():
            for api_key, model_name in models:
                # 每次尝试新模型前先查预算，超出即快速失败（不再空耗剩余组合）
                if time.time() > deadline:
                    raise RuntimeError(f"LLM 调用超过全局预算 {LLM_CALL_BUDGET_SECONDS}s，快速失败")
                # A11：重试/故障转移前复查任务级预算——上一响应即使被判不可用，
                # 其 usage 已记账（见 _invoke_openai），预算可能已耗尽；
                # 超限立即抛 BudgetExceededError，不再尝试后续模型（默认关零变化）。
                if is_budget_exceeded():
                    raise _budget_exceeded_error()
                try:
                    # OpenAI 兼容接口：复用缓存的 ChatOpenAI 客户端（连接池跨调用复用）
                    # P0-1 修复（0.6 轮次性能审计）：此前 llm.invoke 单次调用零重试——
                    # 一次网络抖动/429 即跨模型切换或任务级失败。现套通用指数退避
                    # （_retry_with_exponential_backoff，base_wait=1s：1s/2s/4s）；
                    # 重试耗尽才进入故障转移。
                    llm = _get_or_create_chat_client(model_name, eff_temperature, api_key, base_url)

                    def _invoke_openai(
                        client: Any = llm,
                        model: str = model_name,
                        # B023：显式绑定循环变量，避免闭包晚绑定歧义
                        # （本函数在迭代内即被重试器同步消费，绑定后语义不变）
                        _api_key: str = api_key,
                        _base_url: str = base_url,
                    ) -> str:
                        _invoke_kwargs: dict[str, Any] = {"timeout": LLM_TIMEOUT}
                        if eff_json:
                            # DeepSeek JSON Output（官方文档 guides/json_mode）：
                            # 保证响应为合法 JSON 字符串。提示侧先决条件
                            # （须指示输出 JSON）由调用点保证。
                            _invoke_kwargs["response_format"] = {"type": "json_object"}
                        response = client.invoke(
                            [
                                SystemMessage(content=self.system_prompt),
                                HumanMessage(content=user_message),
                            ],
                            **_invoke_kwargs,
                        )
                        # A11（2026-10-18 第三方审查 P1）：收到响应**立即**
                        # 记账，再判 finish_reason / 空响应。历史实现先对
                        # 截断（finish_reason=length）与空响应 raise，最后才
                        # `_record_response_usage`——带 usage 的失败响应其
                        # token 已真实消耗却漏记，重试/故障转移继续烧 token
                        # 时统计系统性偏低（成本报表失真）。记账早于任何
                        # raise 后，每一次已发生的响应消耗都入账；重试前由
                        # _raise_if_budget_exceeded 复查预算。
                        _record_response_usage(getattr(response, "usage_metadata", None), model)
                        # 2026-10-14：异常 finish_reason 守卫（DeepSeek 官方
                        # 文档）——length=被 max_tokens 截断 / insufficient_
                        # system_resource=推理系统资源不足中断；残缺响应
                        # 按可恢复失败重试，不交给下游解析。
                        _finish = str((getattr(response, "response_metadata", None) or {}).get("finish_reason") or "")
                        if _finish in _ABNORMAL_FINISH_REASONS:
                            logger.warning(
                                "LLM 响应不完整（finish_reason=%s, model=%s），按可恢复失败重试",
                                _finish,
                                model,
                            )
                            raise RuntimeError(f"LLM 响应不完整（finish_reason={_finish}）")
                        text_ = response.content.strip()
                        # 空响应视为失败，触发重试（而非直接跨模型切换）
                        if not text_:
                            raise RuntimeError("LLM 返回空响应")
                        # A10：记录真实请求配置（首选端点成功时即首选；
                        # 故障转移后记录实际成功端点，供缓存 provenance 使用）
                        _record_actual_request_config(_api_key, _base_url, model)
                        return text_

                    text = _retry_with_exponential_backoff(
                        _invoke_openai,
                        max_retries,
                        base_wait=1,
                        # N02（2026-10-22 第三方复审 P1）：预算类异常是控制流
                        # 信号（真超限 / 记账不可判定锁存），不得被退避重试
                        # 吞掉——每次重试都是一次无法计量或已越预算的付费请求。
                        non_retryable_exceptions=(BudgetExceededError,),
                        pre_retry_check=_raise_if_budget_exceeded,
                    )

                    # 打印成功日志
                    api_id = base_url.split("/")[2] if "/" in base_url else base_url
                    logger.info("API 调用成功 (api=%s, model=%s)", api_id, model_name)
                    return text

                except Exception as e:
                    # A11：预算超限是控制流信号（非 API 故障），不得进入
                    # 限流等待/跨模型故障转移——否则记账后的预算闸被绕过。
                    if isinstance(e, BudgetExceededError):
                        raise
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
# AITESTER_LLM_CACHE_DIR 变更或外部清理 LLM 缓存目录后，进程内 LRU 可能持有
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
