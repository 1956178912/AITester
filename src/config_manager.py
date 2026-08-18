"""
API 配置管理工具
功能：
- 自动发现所有配置的 LLM 模型
- 批量添加/移除模型配置
- 生成配置报告
- 验证配置完整性
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

from config import LLM_CONFIGS, LLMConfig

logger = logging.getLogger(__name__)


def get_all_llm_configs() -> list[LLMConfig]:
    """
    获取所有已配置的 LLM 配置
    Returns:
        LLMConfig 列表
    """
    return LLM_CONFIGS


def count_llm_configs() -> int:
    """获取已配置的模型数量"""
    return len(LLM_CONFIGS)


def get_model_names() -> list[str]:
    """获取所有模型名称列表"""
    return [config.model_name for config in LLM_CONFIGS]


def get_config_by_model(model_name: str) -> LLMConfig | None:
    """
    根据模型名称获取配置
    Args:
        model_name: 模型名称
    Returns:
        LLMConfig 对象，如果未找到返回 None
    """
    for config in LLM_CONFIGS:
        if config.model_name == model_name:
            return config
    return None


def add_llm_config(api_key: str, base_url: str, model_name: str, index: int | None = None) -> bool:
    """
    添加新的 LLM 配置到环境变量
    Args:
        api_key: API 密钥
        base_url: API 基础 URL
        model_name: 模型名称
        index: 配置索引（None 则自动分配）
    Returns:
        是否成功添加
    """
    if index is None:
        # 自动分配下一个索引
        idx = len(LLM_CONFIGS) + 1
    else:
        idx = index
    # 写入 .env.local 文件
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.local")
    try:
        # 读取现有内容
        existing_content = ""
        if os.path.exists(env_file):
            with open(env_file, encoding="utf-8") as f:
                existing_content = f.read()
        # 检查是否已存在相同模型
        if f"LLM_{idx}_MODEL_NAME={model_name}" in existing_content:
            logger.warning("模型 %s 已存在于配置中", model_name)
            return False
        # 追加新配置
        comment = f"# 模型 {idx}: {model_name}\n"
        new_lines = [
            comment,
            f"LLM_{idx}_API_KEY={api_key}\n",
            f"LLM_{idx}_BASE_URL={base_url}\n",
            f"LLM_{idx}_MODEL_NAME={model_name}\n",
            "\n",
        ]
        with open(env_file, "a", encoding="utf-8") as f:
            f.writelines(new_lines)
        # 重新加载配置
        load_dotenv(env_file, override=True)
        logger.info("成功添加模型配置: %s (%s)", model_name, base_url)
        return True
    except Exception as e:
        logger.error("添加模型配置失败: %s", e)
        return False


def remove_llm_config(model_name: str) -> bool:
    """
    从配置中移除指定模型
    Args:
        model_name: 要移除的模型名称
    Returns:
        是否成功移除
    """
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.local")
    try:
        if not os.path.exists(env_file):
            logger.warning("配置文件不存在: %s", env_file)
            return False
        # 读取现有内容
        with open(env_file, encoding="utf-8") as f:
            lines = f.readlines()
        # 找到并移除该模型的配置块
        new_lines = []
        skip_until_next_model = False
        removed = False
        for line in lines:
            # 检查是否是目标模型的配置
            if f"LLM_{model_name}" in line or (not removed and "MODEL_NAME=" in line and model_name in line):
                skip_until_next_model = True
                removed = True
                continue
            # 跳过属于该模型的其他配置行
            if skip_until_next_model:
                if line.startswith("LLM_") and "_MODEL_NAME=" not in line:
                    continue
                elif line.startswith("#") and "模型" in line:
                    continue
                elif line.strip() == "":
                    # 遇到空行，结束跳过
                    skip_until_next_model = False
                    if not removed:
                        new_lines.append(line)
                    continue
                else:
                    skip_until_next_model = False
                    new_lines.append(line)
            else:
                new_lines.append(line)
        if not removed:
            logger.warning("未找到模型: %s", model_name)
            return False
        # 写回文件
        with open(env_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        # 重新加载配置
        load_dotenv(env_file, override=True)
        logger.info("成功移除模型配置: %s", model_name)
        return True
    except Exception as e:
        logger.error("移除模型配置失败: %s", e)
        return False


def print_config_report() -> None:
    """打印配置报告"""
    print("\n" + "=" * 80)
    print("LLM 配置报告")
    print("=" * 80)
    print(f"总模型数: {len(LLM_CONFIGS)}")
    print("-" * 80)
    print(f"{'编号':<6} {'模型名称':<25} {'API 端点':<45}")
    print("-" * 80)
    for idx, config in enumerate(LLM_CONFIGS, start=1):
        # 截取 URL 显示
        url_display = config.base_url[:42] + "..." if len(config.base_url) > 45 else config.base_url
        print(f"{idx:<6} {config.model_name:<25} {url_display:<45}")
    print("=" * 80 + "\n")


def validate_configs() -> dict[str, Any]:
    """
    验证所有配置的有效性
    Returns:
        验证结果字典
    """
    results = {"total_configs": len(LLM_CONFIGS), "valid_configs": 0, "invalid_configs": 0, "issues": []}
    for idx, config in enumerate(LLM_CONFIGS, start=1):
        # 检查必填字段
        if not config.api_key:
            results["issues"].append(f"配置 {idx}: API Key 为空")
            results["invalid_configs"] += 1
        elif not config.base_url:
            results["issues"].append(f"配置 {idx}: Base URL 为空")
            results["invalid_configs"] += 1
        elif not config.model_name:
            results["issues"].append(f"配置 {idx}: Model Name 为空")
            results["invalid_configs"] += 1
        else:
            results["valid_configs"] += 1
    return results


def batch_add_models(models: list[dict[str, str]]) -> list[bool]:
    """
    批量添加多个模型配置
    Args:
        models: 模型配置列表，每个元素包含 api_key, base_url, model_name
    Returns:
        每个模型的添加结果列表
    """
    results = []
    for model_info in models:
        success = add_llm_config(
            api_key=model_info["api_key"], base_url=model_info["base_url"], model_name=model_info["model_name"]
        )
        results.append(success)
    return results


if __name__ == "__main__":
    # 运行配置报告
    print_config_report()
    # 验证配置
    validation = validate_configs()
    print(f"验证结果: {validation['valid_configs']}/{validation['total_configs']} 个配置有效")
    if validation["issues"]:
        print("\n发现的问题:")
        for issue in validation["issues"]:
            print(f"  - {issue}")
