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
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from config import LLM_CONFIGS, LLMConfig, refresh_llm_configs

logger = logging.getLogger(__name__)

# .env.local 位于项目根目录（与根目录 config.py 的 load_env_local() 读取路径一致）。
# 注意：此前误用 __file__ 所在目录（src/config/），导致写入的文件永不被应用读取。
ENV_FILE: Path = Path(__file__).resolve().parents[2] / ".env.local"

# 匹配 .env.local 中已占用的 LLM_N 编号（仅未注释行），用于自动分配下一个编号
_LLM_INDEX_PATTERN = re.compile(r"^LLM_(\d+)_", re.MULTILINE)


def _find_model_indices(lines: list[str], model_name: str) -> set[int]:
    """扫描配置行，返回目标模型占用的 LLM_N 编号集合。

    仅匹配 LLM_N_MODEL_NAME=<model> 行（行尾精确匹配，防止 partial 名误命中，
    与 add_llm_config 的重复检查规则一致），注释行与 API_KEY/BASE_URL 行不参与
    编号识别——编号只能由 MODEL_NAME 行确定，避免把同名 API Key 片段误判为配置行。

    Args:
        lines: 配置文件行列表（含行尾换行符）。
        model_name: 模型名称。

    Returns:
        该模型占用的编号集合（可能为空）。
    """
    pattern = re.compile(r"^LLM_(\d+)_MODEL_NAME=" + re.escape(model_name) + r"\s*$")
    indices: set[int] = set()
    for line in lines:
        m = pattern.match(line.rstrip("\n"))
        if m:
            indices.add(int(m.group(1)))
    return indices


def _scan_llm_indices(content: str) -> set[int]:
    """扫描 .env.local 内容中已占用的 LLM_N 编号集合（仅统计未注释行）。"""
    return {int(m) for m in _LLM_INDEX_PATTERN.findall(content)}


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
    添加新的 LLM 配置到项目根目录的 .env.local
    Args:
        api_key: API 密钥
        base_url: API 基础 URL
        model_name: 模型名称
        index: 配置索引（None 则自动分配：扫描文件中已占用的 LLM_N 编号，
               取最大编号 +1，避免与编号空洞场景（如删除 LLM_2）冲突）
    Returns:
        是否成功添加
    """
    existing_content = ""
    if ENV_FILE.exists():
        existing_content = ENV_FILE.read_text(encoding="utf-8")

    # 检查是否已存在相同模型（任意编号下命中即视为重复，避免跨编号重复配置）
    if re.search(rf"^LLM_\d+_MODEL_NAME={re.escape(model_name)}\s*$", existing_content, re.MULTILINE):
        logger.warning("模型 %s 已存在于配置中", model_name)
        return False

    if index is None:
        # 自动分配：已占用编号的最大值 + 1（空文件则为 1）
        used = _scan_llm_indices(existing_content)
        index = max(used) + 1 if used else 1

    # 追加新配置
    comment = f"# 模型 {index}: {model_name}\n"
    new_lines = [
        comment,
        f"LLM_{index}_API_KEY={api_key}\n",
        f"LLM_{index}_BASE_URL={base_url}\n",
        f"LLM_{index}_MODEL_NAME={model_name}\n",
        "\n",
    ]
    try:
        with ENV_FILE.open("a", encoding="utf-8") as f:
            f.writelines(new_lines)
        # 重新加载环境变量并原地刷新 config.LLM_CONFIGS（导入时的快照不会自动更新）
        load_dotenv(str(ENV_FILE), override=True)
        refresh_llm_configs()
        logger.info("成功添加模型配置: %s (%s)", model_name, base_url)
        return True
    except Exception as e:
        logger.error("添加模型配置失败: %s", e)
        return False


def _find_and_remove_model_block(lines: list[str], model_name: str) -> tuple[list[str], bool]:
    """
    从行列表中查找并移除指定模型的完整配置块。

    按编号识别块边界（编号由 LLM_N_MODEL_NAME=<model> 行确定）：
    移除该编号下的全部 LLM_N_API_KEY / LLM_N_BASE_URL / LLM_N_MODEL_NAME 行，
    以及形如 "# 模型 N:" 的块注释行（与 add_llm_config 的写盘格式对齐）。

    旧实现用逐行 skip 模式匹配，只能命中 MODEL_NAME 行本身，遗留同块的
    注释行/API_KEY/BASE_URL 行（密钥残留在文件中，且编号仍被占用影响
    自动分配）。新实现整块移除，保证 remove 后文件内不再出现该编号的任何行。

    Args:
        lines: 配置文件行列表
        model_name: 要移除的模型名称
    Returns:
        (新行列表，是否成功移除)
    """
    indices = _find_model_indices(lines, model_name)
    if not indices:
        return lines, False

    config_line = re.compile(r"^LLM_(\d+)_(API_KEY|BASE_URL|MODEL_NAME)=")
    comment_line = re.compile(r"^#\s*模型\s*(\d+)\s*[:：]")

    def _belongs_to_block(line: str) -> bool:
        stripped = line.rstrip("\n")
        m = config_line.match(stripped)
        if m and int(m.group(1)) in indices:
            return True
        m = comment_line.match(stripped)
        if m and int(m.group(1)) in indices:
            return True
        return False

    new_lines = [line for line in lines if not _belongs_to_block(line)]
    return new_lines, True


def remove_llm_config(model_name: str) -> bool:
    """
    从项目根目录的 .env.local 中移除指定模型
    Args:
        model_name: 要移除的模型名称
    Returns:
        是否成功移除
    """
    try:
        if not ENV_FILE.exists():
            logger.warning("配置文件不存在: %s", ENV_FILE)
            return False

        # 读取现有内容
        old_content = ENV_FILE.read_text(encoding="utf-8")
        lines = old_content.splitlines(keepends=True)

        # 找到并移除该模型的配置块
        new_lines, removed = _find_and_remove_model_block(lines, model_name)

        if not removed:
            logger.warning("未找到模型: %s", model_name)
            return False

        new_content = "".join(new_lines)
        # 写回文件
        ENV_FILE.write_text(new_content, encoding="utf-8")

        # 清理 os.environ 中已删除编号的 LLM_N_* 变量：
        # load_dotenv 只会新增/覆盖，不会删除残留变量，不清理则 refresh 后旧配置仍在
        gone_indices = _scan_llm_indices(old_content) - _scan_llm_indices(new_content)
        for idx in gone_indices:
            for suffix in ("API_KEY", "BASE_URL", "MODEL_NAME"):
                os.environ.pop(f"LLM_{idx}_{suffix}", None)

        # 重新加载环境变量并原地刷新 config.LLM_CONFIGS（导入时的快照不会自动更新）
        load_dotenv(str(ENV_FILE), override=True)
        refresh_llm_configs()
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
