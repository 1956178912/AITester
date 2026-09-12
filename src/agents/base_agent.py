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
import time
from typing import Any

from config import LLM_TIMEOUT, TEMPERATURE
from src.agents.llm_client import (
    _DEFAULT_LLM_MAX_RETRIES,
    _call_zai,
    _get_all_api_configs,
    _get_llm_config,
    _get_or_create_chat_client,
    _is_zai_compatible,
    _llm_cache_dir,
    _llm_cache_enabled,
    _record_response_usage,
    _redact_log_text,
)
from src.utils.helpers import extract_code_block, extract_json_object

logger = logging.getLogger(__name__)

# ─── Token 优化常量 ─────────────────────────────────────────────────────────
# 单条代码输入最大字符数：超长代码截断，避免 token 浪费
_CODE_MAX_CHARS = 3000
# 代码截断提示信息
_CODE_TRUNCATED_MSG = "\n\n[代码已截断，仅显示前 {max} 字符]"


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

    def _call_llm_with_cache(self, user_message: str, max_retries: int = _DEFAULT_LLM_MAX_RETRIES) -> str:
        """
        带缓存的 LLM 调用方法。

        首次调用时执行完整的 LLM 请求并缓存结果，
        后续相同输入直接返回缓存响应，节省 token 和延迟。

        Args:
            user_message: 用户消息内容。
            max_retries: 单次 API 的最大重试次数。

        Returns:
            LLM 返回的文本字符串（来自缓存或实时调用）。
        """
        # 缓存开关关闭时直接透传（测试环境默认关闭，避免缓存文件污染与 flaky）
        if not _llm_cache_enabled():
            return self._call_llm(user_message, max_retries)

        # 生成缓存键（基于 user_message + system_prompt）
        # 使用 hashlib.md5 替代 hash()，确保跨会话稳定命中（hash() 在 Python 3.3+ 默认随机化）
        # 说明：键不含 model，缓存的是"成功的 LLM 输出文本"；配额故障转移/模型切换后，
        # 命中旧结果仍有效（都是该 prompt 的合理回答），且不再消耗 token。
        cache_key = f"{user_message}:{self.system_prompt}"
        cache_hash = hashlib.md5(cache_key.encode("utf-8")).hexdigest()[:16]  # 取前16位十六进制，固定长度
        cache_file = os.path.join(_llm_cache_dir(), f"{cache_hash}.json")
        cache_file = os.path.normpath(cache_file)

        # 读缓存：校验 prompt 与 system 完全一致才命中（防 md5 前16位碰撞误命中）
        try:
            if os.path.exists(cache_file):
                with open(cache_file, encoding="utf-8") as f:
                    cached_data = json.load(f)
                    if cached_data.get("prompt") == user_message and cached_data.get("system") == self.system_prompt:
                        logger.info("LLM 缓存命中 (省 1 次调用): %s", cache_key[:50])
                        return cached_data["response"]
        except Exception as e:
            logger.debug("缓存读取失败: %s", e)

        # 未命中，执行实际调用（仅在成功时写缓存；失败如 403 额度用尽则不缓存）
        response = self._call_llm(user_message, max_retries)

        # 写入缓存
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "prompt": user_message,
                        "system": self.system_prompt,
                        "response": response,
                        "timestamp": time.time(),
                    },
                    f,
                    ensure_ascii=False,
                )
            logger.info("LLM 缓存已写入: %s", cache_key[:50])
        except Exception as e:
            logger.debug("缓存写入失败: %s", e)

        return response

    def _call_llm(self, user_message: str, max_retries: int = _DEFAULT_LLM_MAX_RETRIES) -> str:
        """
        调用 LLM 并返回文本响应。
        失败时进行最多 max_retries 次重试，采用指数退避策略（1s, 2s, 4s）。
        若所有重试均失败，自动切换到备用 API 继续尝试。
        支持 OpenAI 兼容接口和 zai SDK（BigModel）两种调用路径。

        Args:
            user_message: 用户消息内容。
            max_retries: 单次 API 的最大重试次数，默认 3 次。

        Returns:
            LLM 返回的文本字符串。

        Raises:
            RuntimeError: 所有 API 和重试均失败时抛出。
        """
        # 延迟导入：避免循环导入（base_agent 被 planner/generator/debugger 导入）
        from langchain_core.messages import HumanMessage, SystemMessage

        # 获取所有已配置的 API，未配置时直接报错不进入重试循环
        all_configs = _get_all_api_configs()
        if not all_configs:
            raise RuntimeError("未配置任何 LLM API")

        # 记录最后一次异常，用于最终报错信息
        last_error: Exception | None = None

        # 按 base_url 分组配置，支持同一 API 内切换模型
        # 结构：{base_url: [(api_key, model_name), ...]}
        api_groups: dict[str, list[tuple[str, str]]] = {}
        for api_key, base_url, model_name in all_configs:
            if base_url not in api_groups:
                api_groups[base_url] = []
            api_groups[base_url].append((api_key, model_name))

        # 依次尝试每个 API 组（自动故障转移：主 API 失败 → 备用 API）
        # 同一 API 内也尝试不同模型（额度用完时自动切换）
        for base_url, models in api_groups.items():
            # 判断当前 API 是否为 zai SDK 兼容接口，分流至不同调用路径
            is_zai = _is_zai_compatible(base_url)

            for api_key, model_name in models:
                try:
                    if is_zai:
                        # BigModel 等非 OpenAI 兼容接口：使用 zai SDK 专属调用
                        text = _call_zai(api_key, base_url, model_name, self.system_prompt, user_message, max_retries)
                    else:
                        # OpenAI 兼容接口：复用缓存的 ChatOpenAI 客户端（连接池跨调用复用）
                        llm = _get_or_create_chat_client(model_name, TEMPERATURE, api_key, base_url)
                        response = llm.invoke(
                            [
                                SystemMessage(content=self.system_prompt),
                                HumanMessage(content=user_message),
                            ],
                            timeout=LLM_TIMEOUT,
                        )
                        text = response.content.strip()
                        # 空响应视为失败，触发当前 API 的异常捕获并尝试下一个 API
                        if not text:
                            raise RuntimeError("LLM 返回空响应")
                        # token 消耗统计（LangChain 响应的 usage_metadata，可能缺失）
                        _record_response_usage(getattr(response, "usage_metadata", None), model_name)

                    # 打印成功日志
                    api_id = base_url.split("/")[2] if "/" in base_url else base_url
                    logger.info("API 调用成功 (api=%s, model=%s)", api_id, model_name)
                    return text

                except Exception as e:
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
    def _find_balanced_json(text: str, start: int) -> str | None:
        """
        使用括号平衡法找到从 start 位置开始的第一个完整 JSON 对象（委托给公共工具函数）。

        Args:
            text: 待搜索的文本。
            start: 起始搜索位置（应为 '{' 的位置）。

        Returns:
            完整的 JSON 字符串，未找到匹配时返回 None。
        """
        from src.utils.helpers import _find_balanced_json as _helpers_find_balanced_json

        return _helpers_find_balanced_json(text, start)

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
    ) -> str:
        """截断超长代码，避免 LLM token 浪费。

        截取策略（P0 优化，解决 SWE-bench 大文件上下文丢失问题）：
        1. 代码在预算内 → 原样返回；
        2. 否则先做基于 AST 的智能截取（保留 import + 目标函数及其
           直接依赖的辅助函数，超长函数体首尾截断），优先于"头尾各半"
           硬截断——硬截断对数百行源文件会让 LLM 看不到目标函数；
        3. AST 截取仍超预算（或源码无法解析、无函数体）→ 回退字符级
           头尾截断兜底。

        Args:
            code: 原始代码字符串。
            max_chars: 最大允许字符数，默认 3000。
            focus_function: 焦点函数名（如 "divide"）。提供时按函数维度
                截取上下文；None 时保留全部顶层函数再按预算裁剪。

        Returns:
            截断后的代码字符串。
        """
        if len(code) <= max_chars:
            return code

        # 第一层：AST 智能截取（惰性导入，避免 tools 模块的循环依赖）
        from src.tools.code_context import extract_focused_code

        focused = extract_focused_code(code, focus_function=focus_function, max_chars=max_chars)
        if len(focused) <= max_chars:
            logger.info(
                "代码已按 AST 智能截取：%d → %d 字符（focus=%s）", len(code), len(focused), focus_function or "*"
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
