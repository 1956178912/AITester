#!/usr/bin/env python3
"""
批量扩展模型配置

基于现有 API Key，自动添加更多可用模型到配置中
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import LLM_CONFIGS
from src.config_manager import add_llm_config, count_llm_configs, get_model_names

# 基于现有配置的模型扩展列表
# 使用相同的 API Key 和 Base URL，只添加新的模型名称
MODEL_EXTENSIONS = {
    # 阿里云百炼 - 通义千问系列（使用 LLM_1/4 的 key 和 URL）
    "qwen-plus": {"provider": "aliyun", "description": "通义千问-plus"},
    "qwen-turbo": {"provider": "aliyun", "description": "通义千问-turbo（快速）"},
    "qwen-long": {"provider": "aliyun", "description": "通义千问-long（长上下文）"},

    # DeepSeek 系列
    "deepseek-chat": {"provider": "deepseek", "description": "DeepSeek Chat"},
    "deepseek-coder": {"provider": "deepseek", "description": "DeepSeek Coder"},

    # GLM 系列
    "glm-4": {"provider": "bigmodel", "description": "GLM-4"},
    "glm-4-plus": {"provider": "bigmodel", "description": "GLM-4-Plus"},
    "glm-4-air": {"provider": "bigmodel", "description": "GLM-4-Air（快速）"},
    "glm-4-flash": {"provider": "bigmodel", "description": "GLM-4-Flash（最快）"},

    # Agnes AI 系列
    "agnes-2.5-pro": {"provider": "agnes", "description": "Agnes 2.5 Pro"},
    "agnes-2.0": {"provider": "agnes", "description": "Agnes 2.0"},

    # Kimi 系列
    "kimi-k2.5": {"provider": "kimi", "description": "Kimi K2.5"},
    "kimi-k2.5-lite": {"provider": "kimi", "description": "Kimi K2.5 Lite"},
}

# API 端点映射
API_ENDPOINTS = {
    "aliyun": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "bigmodel": "https://open.bigmodel.cn/api/paas/v4/",
    "agnes": "https://api.agnes-ai.cn/v1",
    "kimi": "https://dashscope.aliyuncs.com/compatible-mode/v1",  # Kimi 通过百炼访问
}

# API Key 映射（从现有配置中提取）
API_KEYS = {}
for config in LLM_CONFIGS:
    # 根据 base_url 推断 provider
    if "dashscope" in config.base_url or "aliyuncs" in config.base_url:
        API_KEYS["aliyun"] = config.api_key
    elif "agnes-ai" in config.base_url:
        API_KEYS["agnes"] = config.api_key
    elif "bigmodel" in config.base_url:
        API_KEYS["bigmodel"] = config.api_key
    elif "deepseek" in config.base_url:
        API_KEYS["deepseek"] = config.api_key


def expand_models():
    """扩展模型配置"""
    print("\n" + "=" * 80)
    print("批量扩展模型配置")
    print("=" * 80)
    print(f"\n当前已配置模型数: {count_llm_configs()}")
    print(f"已有模型: {get_model_names()}")

    # 检查是否有可用的 API Key
    if not API_KEYS:
        print("\n错误：未找到任何有效的 API Key")
        print("请确保 .env.local 中已配置至少一个 LLM_*_API_KEY")
        return

    print("\n已识别的 API Key:")
    for provider, key in API_KEYS.items():
        masked_key = key[:10] + "..." + key[-4:] if len(key) > 14 else "***"
        print(f"  {provider}: {masked_key}")

    # 准备要添加的模型
    models_to_add = []
    for model_name, info in MODEL_EXTENSIONS.items():
        if model_name not in get_model_names():
            provider = info["provider"]
            if provider in API_KEYS:
                models_to_add.append({
                    "model_name": model_name,
                    "base_url": API_ENDPOINTS[provider],
                    "api_key": API_KEYS[provider],
                    "description": info["description"]
                })

    print(f"\n待添加模型数: {len(models_to_add)}")
    print("-" * 80)

    if not models_to_add:
        print("\n所有模型已存在，无需添加")
        return

    # 显示将要添加的模型
    print("\n将要添加的模型:")
    for i, model in enumerate(models_to_add, start=1):
        print(f"  {i}. {model['model_name']:<20} ({model['description']})")

    # 批量添加
    print("\n开始批量添加...")
    success_count = 0
    fail_count = 0

    for model in models_to_add:
        success = add_llm_config(
            api_key=model["api_key"],
            base_url=model["base_url"],
            model_name=model["model_name"]
        )

        if success:
            print(f"  ✓ {model['model_name']}")
            success_count += 1
        else:
            print(f"  ✗ {model['model_name']}")
            fail_count += 1

    print("\n" + "=" * 80)
    print("扩展完成!")
    print(f"  成功添加: {success_count}")
    print(f"  失败: {fail_count}")
    print(f"  当前总模型数: {count_llm_configs()}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    expand_models()
