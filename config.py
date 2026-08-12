"""
全局配置文件：所有环境变量和常量在此集中管理。
"""

from __future__ import annotations

import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# ─── LLM 配置 ───────────────────────────────────────────────────────────────
# OpenAI 兼容 API 基地址，支持 DeepSeek / Qwen 等替换
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME: str = os.getenv("MODEL_NAME", "gpt-4o-mini")
# 温度，控制输出随机性
TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.2"))

# ─── 数据库配置 ──────────────────────────────────────────────────────────────
MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "aitester")

# ─── 执行环境配置 ────────────────────────────────────────────────────────────
# 是否启用 Docker 隔离执行，false 时回退到本地执行
DOCKER_ENABLED: bool = os.getenv("DOCKER_ENABLED", "false").lower() == "true"
# Docker 镜像
DOCKER_IMAGE: str = os.getenv("DOCKER_IMAGE", "python:3.11-slim")
# 单次测试最大运行时间（秒）
EXECUTION_TIMEOUT: int = int(os.getenv("EXECUTION_TIMEOUT", "30"))

# ─── 工作流配置 ──────────────────────────────────────────────────────────────
# 最大修复迭代次数
MAX_ITERATIONS: int = int(os.getenv("MAX_ITERATIONS", "3"))
# 覆盖率阈值（达到此阈值视为合格）
COVERAGE_THRESHOLD: float = float(os.getenv("COVERAGE_THRESHOLD", "80.0"))
