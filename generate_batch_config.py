"""
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
    with open(models_file, encoding='utf-8') as f:
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

    return "\n".join(lines)


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
