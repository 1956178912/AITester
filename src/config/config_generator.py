"""
批量配置生成器
用于生成大量模型配置的模板和脚本。

用法：
    # 生成全部产物（模型目录 + .env.local.template + llm_configs.json
    # + scripts/tools/generate_batch_config.py，写入项目根目录）
    python -m src.config.config_generator
"""
# ruff: noqa: T201  — 本文件为 CLI 用户可见的报表/自检输出（print 属有意行为，非库代码副作用）

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# 常见 LLM API 提供商配置模板
# PROVIDER_TEMPLATES 是 provider 登记的全量注册表（schema 校验与
# credential_scrub 动态凭证剔除名单都依赖它，见 validate_llm_configs /
# src/utils/credential_scrub.py），保留全量 provider 键；
# 当前项目实际启用的端点见 COMMON_MODELS（仅 DeepSeek 官方 deepseek-flash，
# 2026-10-09 配置要求：删除其余 API，仅保留用户配置的 DeepSeek）。
PROVIDER_TEMPLATES = {
    "aliyun_bailian": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        # S6（2026-10-09 修正）：百炼 compatible-mode 端点可路由多模型
        # （通义千问 + 第三方 deepseek/glm/kimi 经 OpenAI 兼容端点），
        # 原"（通义千问）"会让 deepseek-v3/glm-4.7/kimi 等条目误读为
        # 通义千问系列；改为中性"阿里云百炼"，模型身份由 model_name 表达。
        "description": "阿里云百炼",
    },
    "agnes_domestic": {"base_url": "https://api.agnes-ai.cn/v1", "description": "Agnes AI 国内站"},
    "agnes_international": {"base_url": "https://apihub.agnes-ai.com/v1", "description": "Agnes AI 国际站"},
    "bigmodel": {"base_url": "https://open.bigmodel.cn/api/paas/v4/", "description": "BigModel 智谱"},
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "description": "DeepSeek"},
}
# 当前项目启用的模型目录（2026-10-09：仅保留用户配置的 DeepSeek V4.1 Flash；
# 其余 qwen / glm / kimi / agnes / deepseek-chat 等条目已按要求移除。
# generate_config_json / print_model_catalog 以本列表为唯一来源。
# 注：model_name 使用 DeepSeek 官方 API 当前接受的写法 `deepseek-flash`
# （历史别名 `deepseek-v4.1-flash` 已弃用，与 .env.local / llm_configs.json 对齐）。
COMMON_MODELS = [
    {"name": "deepseek-flash", "provider": "deepseek"},
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
        "# ─── LLM 中间变量模板（供批量生成脚本使用）────────────────────────────────",
        "# 重要：本文件由 generate_env_template() 生成，{PROVIDER}_API_KEY 是批量配置",
        "# 脚本的中间变量；config.py 运行时直接读取 LLM_N_* 编号格式，不会读取这些",
        "# {PROVIDER}_API_KEY 变量。请勿直接复制本文件为 .env.local 使用！",
        "# 手动配置请改用：cp config.local.example .env.local（填入 LLM_N_* 格式）",
        "# 批量生成用法：python scripts/tools/generate_batch_config.py --models llm_configs.json",
        "",
        "# ─── API Key 配置（必填）────────────────────────────────────────────────────",
        "# 每个 LLM Provider 需要独立的 API Key",
        "# 变量名约定：{PROVIDER}_API_KEY（provider 全名大写 + _API_KEY），",
        "# 与 generate_config_json / scripts/tools/generate_batch_config.py 的推导规则同源",
        "# （当前目录仅保留 DeepSeek 官方 provider，与 COMMON_MODELS 对齐）",
        "",
        "# DeepSeek API Key",
        "DEEPSEEK_API_KEY=your-deepseek-api-key-here",
        "",
        "# ─── 模型配置示例 ──────────────────────────────────────────────────────────",
        "",
        "# 示例：添加 DeepSeek 官方模型（当前项目唯一配置的 LLM 端点）",
        "# LLM_1_API_KEY=${DEEPSEEK_API_KEY}",
        "# LLM_1_BASE_URL=https://api.deepseek.com/v1",
        "# LLM_1_MODEL_NAME=deepseek-flash",
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


def validate_llm_configs(configs: list[dict[str, Any]]) -> list[str]:
    """校验 llm_configs.json 模型目录 schema，返回违例清单（空 = 合法）。

    校验规则（与 PROVIDER_TEMPLATES 权威来源对齐，防数据质量漂移）：
    1. 每条目必填字段：model_name（非空 str）/ provider / base_url /
       required_api_key；缺字段或类型不符 → 违例；
    2. provider 必须 ∈ PROVIDER_TEMPLATES 键（未登记 provider 拒绝，
       与 credential_scrub 的 provider 键联动防漂移）；
    3. required_api_key 必须 == f"{provider.upper()}_API_KEY"
       （与 generate_config_json 的推导规则同源，防手改漂移）；
    4. base_url 必须以 http(s):// 开头（防残缺/内网占位混入）；
    5. model_name 全局唯一（重复条目会使 expand_models/check_quota
       路由歧义）。

    Args:
        configs: json.load 读入的模型目录列表（顶层为 list[dict]）。

    Returns:
        违例描述列表（每条含 1-based 条目序数）；空列表 = 全通过。
    """
    violations: list[str] = []
    if not isinstance(configs, list):
        return ["顶层结构必须为 JSON 数组（list）"]
    seen_models: set[str] = set()
    for idx, entry in enumerate(configs, start=1):
        if not isinstance(entry, dict):
            violations.append(f"#{idx}: 条目必须是对象（dict）")
            continue
        model_name = entry.get("model_name")
        provider = entry.get("provider")
        base_url = entry.get("base_url")
        required_key = entry.get("required_api_key")
        if not isinstance(model_name, str) or not model_name.strip():
            violations.append(f"#{idx}: 缺 model_name（非空字符串）")
        elif model_name in seen_models:
            violations.append(f"#{idx}: model_name {model_name!r} 重复（路由歧义）")
        else:
            seen_models.add(model_name)
        if not isinstance(provider, str) or provider not in PROVIDER_TEMPLATES:
            violations.append(
                f"#{idx}: provider {provider!r} 未在 PROVIDER_TEMPLATES 登记（合法值：{sorted(PROVIDER_TEMPLATES)}）"
            )
        else:
            expected_key = f"{provider.upper()}_API_KEY"
            if required_key != expected_key:
                violations.append(f"#{idx}: required_api_key {required_key!r} 应为 {expected_key!r}")
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            violations.append(f"#{idx}: base_url {base_url!r} 必须以 http(s):// 开头")
    return violations


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
    return '''"""
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
import sys
from typing import Any


def parse_args():
    parser = argparse.ArgumentParser(description="批量生成 LLM 配置")
    parser.add_argument("--output", default=".env.local", help="输出文件路径")
    parser.add_argument("--models", help="模型列表文件（JSON）")
    parser.add_argument("--template", help="配置模板文件")
    return parser.parse_args()


def load_models(models_file: str) -> list[dict[str, Any]]:
    with open(models_file, encoding="utf-8") as f:
        return json.load(f)


def generate_config(models: list[dict[str, Any]], api_keys: dict[str, str]) -> str:
    lines = []
    for idx, model in enumerate(models, start=1):
        provider = model.get("provider", "")
        api_key_var = f"{provider.upper()}_API_KEY"
        api_key = api_keys.get(api_key_var, f"your-{provider}-api-key-here")

        # llm_configs.json 的字段是 model_name（兼容旧 schema 的 name）
        model_name = model.get("model_name") or model.get("name") or "unknown"
        lines.append(f"# {model_name}")
        lines.append(f"LLM_{idx}_API_KEY={api_key}")
        lines.append(f"LLM_{idx}_BASE_URL={model.get('base_url', '')}")
        lines.append(f"LLM_{idx}_MODEL_NAME={model_name}")
        lines.append("")

    return "\\n".join(lines)


def main():
    args = parse_args()

    # 加载模型列表（未指定时使用空默认列表）
    models = load_models(args.models) if args.models else []

    # 数据丢失防护：模型列表为空时，"w" 模式写入会用空文件覆盖现有
    # .env.local，抹掉已配置的 LLM_N_*。此时应报错退出而非生成空配置。
    if not models:
        print(
            "错误：模型列表为空。为避免用空文件覆盖现有 .env.local，请通过 --models 指定模型列表 JSON 文件。",
            file=sys.stderr,
        )
        sys.exit(1)

    # 加载 API Keys：按 models 中实际出现的 provider 推导环境变量名
    # （与 generate_config 的命名约定 {PROVIDER}_API_KEY 同源，避免此前
    # 硬编码 ALIYUN_API_KEY 等与 aliyun_bailian/agnes_domestic 等 provider
    # 键名失配、导致环境变量永远取不到的问题）
    api_keys: dict[str, str] = {}
    for model in models:
        provider = model.get("provider", "")
        if not provider:
            continue
        key_var = f"{provider.upper()}_API_KEY"
        env_val = os.getenv(key_var, "")
        if env_val:
            api_keys[key_var] = env_val

    # 生成配置
    config_content = generate_config(models, api_keys)

    # 写入文件
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(config_content)

    print(f"配置已生成: {args.output}")
    print(f"共生成 {len(models)} 个模型配置")


if __name__ == "__main__":
    main()
'''


# 项目根目录（本文件位于 src/config/ 下，向上三级即仓库根）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if __name__ == "__main__":
    # 打印模型目录
    print_model_catalog()
    # 生成模板
    template = generate_env_template()
    print("模板已生成: .env.local.template")
    # 生成 JSON 配置
    json_content = generate_config_json()
    print("JSON 配置已生成: llm_configs.json")
    # 生成批量配置脚本（移入 scripts/ 子目录，与独立运维脚本集中管理）
    script = generate_batch_config_script()
    scripts_dir = _PROJECT_ROOT / "scripts" / "tools"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    with open(scripts_dir / "generate_batch_config.py", "w", encoding="utf-8") as f:
        f.write(script)
    print("批量配置脚本已生成: scripts/tools/generate_batch_config.py")
