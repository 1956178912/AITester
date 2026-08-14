"""
全局配置文件：集中管理所有环境变量和常量。

此模块从 .env 文件读取基础配置，并从 .env.local 覆盖 LLM 敏感配置。
修改配置项时，优先修改此文件，而非在各处硬编码。

LLM 配置（API Key / Base URL / Model）属于敏感信息，
统一在 .env.local 中管理（已通过 .gitignore 排除），
此处以 <PLACEHOLDER> 标记，实际值由 load_env_local() 注入。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# ─── 基础配置加载（.env，非敏感项）───────────────────────────────────────────
load_dotenv()


def load_env_local() -> None:
    """加载本地敏感配置文件 .env.local（若存在），覆盖 .env 中的 LLM 配置。
    
    .env.local 不得提交到版本库，开发者需自行创建：
        cp config.local.example .env.local
        # 然后填入真实值
    """
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.local")
    if os.path.exists(local_path):
        load_dotenv(local_path, override=True)


# ─── LLM 配置（敏感信息，从 .env.local 读取）────────────────────────────────
# 每个 LLM provider 一组配置，可自由增删，格式如下：
#
#   LLM_N_API_KEY=<PLACEHOLDER>      # 第 N 个 API Key（从 .env.local 注入）
#   LLM_N_BASE_URL=<PLACEHOLDER>     # 对应 Base URL
#   LLM_N_MODEL_NAME=<PLACEHOLDER>   # 模型名称
#
# 示例（见 config.local.example）：
#   LLM_1_API_KEY=sk-your-key-here
#   LLM_1_BASE_URL=https://api.agnes-ai.cn/v1
#   LLM_1_MODEL_NAME=agnes-2.5-flash
#   LLM_2_API_KEY=sk-another-key
#   LLM_2_BASE_URL=https://api.deepseek.com
#   LLM_2_MODEL_NAME=deepseek-chat

load_env_local()  # 加载 .env.local，覆盖敏感 LLM 配置


@dataclass(frozen=True)
class LLMConfig:
    """单个 LLM Provider 的配置，包含 api_key、base_url、model_name。"""
    api_key: str
    base_url: str
    model_name: str


def _load_llm_configs() -> list[LLMConfig]:
    """从环境变量中读取所有 LLM_N_* 配置，返回非空配置列表。
    
    环境变量命名规则：
        LLM_1_API_KEY, LLM_1_BASE_URL, LLM_1_MODEL_NAME   → 第 1 个配置
        LLM_2_API_KEY, LLM_2_BASE_URL, LLM_2_MODEL_NAME   → 第 2 个配置
        ...
    
    只有 api_key、base_url、model_name 三项均非空时，该配置才会被加入列表。
    """
    configs: list[LLMConfig] = []
    idx = 1
    while True:
        api_key = os.getenv(f"LLM_{idx}_API_KEY", "").strip()
        base_url = os.getenv(f"LLM_{idx}_BASE_URL", "").strip()
        model_name = os.getenv(f"LLM_{idx}_MODEL_NAME", "").strip()
        if not api_key or not base_url or not model_name:
            break
        configs.append(LLMConfig(api_key=api_key, base_url=base_url, model_name=model_name))
        idx += 1
    return configs


# 所有已配置的 LLM Provider 列表（按 LLM_1, LLM_2, ... 顺序）
LLM_CONFIGS: list[LLMConfig] = _load_llm_configs()

# 默认使用的 LLM 配置（取第一个，即 LLM_1）
DEFAULT_LLM_CONFIG: LLMConfig | None = LLM_CONFIGS[0] if LLM_CONFIGS else None

# 向后兼容：保留旧的扁平变量名，指向默认 LLM 配置（供旧代码引用）
OPENAI_API_KEY: str = DEFAULT_LLM_CONFIG.api_key if DEFAULT_LLM_CONFIG else ""
OPENAI_BASE_URL: str = DEFAULT_LLM_CONFIG.base_url if DEFAULT_LLM_CONFIG else ""
MODEL_NAME: str = DEFAULT_LLM_CONFIG.model_name if DEFAULT_LLM_CONFIG else ""
# TEMPERATURE 非敏感配置，可留在 .env 或 .env.local 中
TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.2"))


# ─── 数据库配置 ──────────────────────────────────────────────────────────────
MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "aitester")

# ─── 执行环境配置 ────────────────────────────────────────────────────────────
DOCKER_ENABLED: bool = os.getenv("DOCKER_ENABLED", "false").lower() == "true"
DOCKER_IMAGE: str = os.getenv("DOCKER_IMAGE", "python:3.11-slim")
EXECUTION_TIMEOUT: int = int(os.getenv("EXECUTION_TIMEOUT", "30"))

# ─── 工作流配置 ──────────────────────────────────────────────────────────────
MAX_ITERATIONS: int = int(os.getenv("MAX_ITERATIONS", "3"))
COVERAGE_THRESHOLD: float = float(os.getenv("COVERAGE_THRESHOLD", "80.0"))

# ─── 消融实验开关 ────────────────────────────────────────────────────────────
ENABLE_PLANNER: bool = os.getenv("ENABLE_PLANNER", "true").lower() == "true"
ENABLE_RAG: bool = os.getenv("ENABLE_RAG", "false").lower() == "true"
ENABLE_DEBUGGER: bool = os.getenv("ENABLE_DEBUGGER", "true").lower() == "true"

# ─── 实验配置 ────────────────────────────────────────────────────────────────
BENCHMARK_PARALLELISM: int = int(os.getenv("BENCHMARK_PARALLELISM", "0"))
LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))
LLM_RETRY_WAIT: int = int(os.getenv("LLM_RETRY_WAIT", "30"))
