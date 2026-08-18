"""
批量配置生成器
用于生成大量模型配置的模板和脚本
"""

from __future__ import annotations

import json

# 常见的 LLM API 提供商配置模板
PROVIDER_TEMPLATES = {
    "aliyun_bailian": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "description": "阿里云百炼（通义千问）",
    },
    "agnes_domestic": {"base_url": "https://api.agnes-ai.cn/v1", "description": "Agnes AI 国内站"},
    "agnes_international": {"base_url": "https://apihub.agnes-ai.com/v1", "description": "Agnes AI 国际站"},
    "bigmodel": {"base_url": "https://open.bigmodel.cn/api/paas/v4/", "description": "BigModel 智谱"},
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "description": "DeepSeek"},
}
# 常见模型列表
COMMON_MODELS = [
    # 通义千问系列
    {"name": "qwen-max", "provider": "aliyun_bailian"},
    {"name": "qwen-plus", "provider": "aliyun_bailian"},
    {"name": "qwen-turbo", "provider": "aliyun_bailian"},
    {"name": "qwen-long", "provider": "aliyun_bailian"},
    # DeepSeek 系列
    {"name": "deepseek-chat", "provider": "deepseek"},
    {"name": "deepseek-coder", "provider": "deepseek"},
    {"name": "deepseek-v3", "provider": "aliyun_bailian"},
    {"name": "deepseek-v4-pro", "provider": "aliyun_bailian"},
    {"name": "deepseek-v4-flash", "provider": "aliyun_bailian"},
    # GLM 系列
    {"name": "glm-4", "provider": "bigmodel"},
    {"name": "glm-4-plus", "provider": "bigmodel"},
    {"name": "glm-4-air", "provider": "bigmodel"},
    {"name": "glm-4-flash", "provider": "bigmodel"},
    {"name": "glm-4.7", "provider": "aliyun_bailian"},
    {"name": "glm-4.7-flash", "provider": "bigmodel"},
    # Kimi 系列
    {"name": "kimi-k2.7-code", "provider": "aliyun_bailian"},
    # Agnes 系列
    {"name": "agnes-2.5-flash", "provider": "agnes_domestic"},
]


def generate_env_template(output_file: str = ".env.local.template") -> str:
    """
    生成环境变量配置模板
    Args:
        output_file: 输出文件路径
    Returns:
        生成的模板内容
    """
    template_lines = [
        "# ─── LLM 配置模板 ──────────────────────────────────────────────────────────",
        "# 使用说明：",
        "# 1. 复制此文件为 .env.local",
        "# 2. 填入真实的 API Key",
        "# 3. 根据需要增删模型配置",
        "",
        "# ─── API Key 配置（必填）────────────────────────────────────────────────────",
        "# 每个 LLM Provider 需要独立的 API Key",
        "",
        "# 阿里云百炼 API Key",
        "ALIYUN_API_KEY=your-aliyun-api-key-here",
        "",
        "# Agnes AI API Key",
        "AGNES_API_KEY=your-agnes-api-key-here",
        "",
        "# BigModel API Key",
        "BIGMODEL_API_KEY=your-bigmodel-api-key-here",
        "",
        "# DeepSeek API Key",
        "DEEPSEEK_API_KEY=your-deepseek-api-key-here",
        "",
        "# ─── 模型配置示例 ──────────────────────────────────────────────────────────",
        "",
        "# 示例：添加通义千问模型",
        "# LLM_1_API_KEY=${ALIYUN_API_KEY}",
        "# LLM_1_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1",
        "# LLM_1_MODEL_NAME=qwen-max",
        "",
        "# 示例：添加 Agnes AI 模型",
        "# LLM_2_API_KEY=${AGNES_API_KEY}",
        "# LLM_2_BASE_URL=https://api.agnes-ai.cn/v1",
        "# LLM_2_MODEL_NAME=agnes-2.5-flash",
        "",
        "# 示例：添加智谱模型",
        "# LLM_3_API_KEY=${BIGMODEL_API_KEY}",
        "# LLM_3_BASE_URL=https://open.bigmodel.cn/api/paas/v4/",
        "# LLM_3_MODEL_NAME=glm-4-flash",
        "",
    ]
    content = "\n".join(template_lines)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def generate_config_json(output_file: str = "llm_configs.json") -> str:
    """
    生成 JSON 格式的模型配置
    Args:
        output_file: 输出文件路径
    Returns:
        生成的 JSON 内容
    """
    configs = []
    for model in COMMON_MODELS:
        provider = PROVIDER_TEMPLATES.get(model["provider"], {})
        configs.append(
            {
                "model_name": model["name"],
                "provider": model["provider"],
                "provider_description": provider.get("description", ""),
                "base_url": provider.get("base_url", ""),
                "required_api_key": f"{model['provider'].upper()}_API_KEY",
            }
        )
    content = json.dumps(configs, indent=2, ensure_ascii=False)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def print_model_catalog() -> None:
    """打印可用模型目录"""
    print("\n" + "=" * 80)
    print("可用模型目录")
    print("=" * 80)
    print(f"{'模型名称':<25} {'提供商':<20} {'API 端点':<45}")
    print("-" * 80)
    for model in COMMON_MODELS:
        provider = PROVIDER_TEMPLATES.get(model["provider"], {})
        base_url_raw = provider.get("base_url", "N/A")
        base_url = base_url_raw[:42] + "..." if len(base_url_raw) > 45 else base_url_raw
        print(f"{model['name']:<25} {provider.get('description', 'N/A'):<20} {base_url:<45}")
    print("=" * 80 + "\n")


def generate_batch_config_script() -> str:
    """
    生成批量配置脚本
    Returns:
        Python 脚本内容
    """
    script = '''"""
批量配置生成脚本
用法：
    python generate_batch_config.py --output .env.local
选项：
    --output FILE     输出文件路径（默认：.env.local）
    --models FILE     模型列表文件（JSON 格式）
    --template FILE   配置模板文件
"""
import argparse
import json
import os
from typing import Any
def parse_args():
    parser = argparse.ArgumentParser(description="批量生成 LLM 配置")
    parser.add_argument("--output", default=".env.local", help="输出文件路径")
    parser.add_argument("--models", help="模型列表文件（JSON）")
    parser.add_argument("--template", help="配置模板文件")
    return parser.parse_args()
def load_models(models_file: str) -> list[dict[str, Any]]:
    with open(models_file, 'r', encoding='utf-8') as f:
        return json.load(f)
def generate_config(models: list[dict[str, Any]], api_keys: dict[str, str]) -> str:
    lines = []
    for idx, model in enumerate(models, start=1):
        provider = model.get("provider", "")
        api_key_var = f"{provider.upper()}_API_KEY"
        api_key = api_keys.get(api_key_var, f"your-{provider}-api-key-here")
        lines.append(f"# {model.get('name', 'unknown')}")
        lines.append(f"LLM_{idx}_API_KEY={api_key}")
        lines.append(f"LLM_{idx}_BASE_URL={model.get('base_url', '')}")
        lines.append(f"LLM_{idx}_MODEL_NAME={model.get('name', 'unknown')}")
        lines.append("")
    return "\\n".join(lines)
def main():
    args = parse_args()
    # 加载模型列表
    if args.models:
        models = load_models(args.models)
    else:
        # 使用默认模型列表
        models = []
    # 加载 API Keys（从环境变量或配置文件）
    api_keys = {
        "ALIYUN_API_KEY": os.getenv("ALIYUN_API_KEY", ""),
        "AGNES_API_KEY": os.getenv("AGNES_API_KEY", ""),
        "BIGMODEL_API_KEY": os.getenv("BIGMODEL_API_KEY", ""),
        "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY", ""),
    }
    # 生成配置
    config_content = generate_config(models, api_keys)
    # 写入文件
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(config_content)
    print(f"配置已生成: {args.output}")
    print(f"共生成 {len(models)} 个模型配置")
if __name__ == "__main__":
    main()
'''
    return script


if __name__ == "__main__":
    # 打印模型目录
    print_model_catalog()
    # 生成模板
    template = generate_env_template()
    print("模板已生成: .env.local.template")
    # 生成 JSON 配置
    json_content = generate_config_json()
    print("JSON 配置已生成: llm_configs.json")
    # 生成批量配置脚本
    script = generate_batch_config_script()
    with open("generate_batch_config.py", "w", encoding="utf-8") as f:
        f.write(script)
    print("批量配置脚本已生成: generate_batch_config.py")
