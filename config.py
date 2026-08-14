"""
全局配置文件：集中管理所有环境变量和常量。

此模块从 .env 文件读取配置，为整个项目提供统一的配置接口。
修改配置项时，优先修改此文件，而非在各处硬编码。
"""

from __future__ import annotations

import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量，使配置与代码分离
load_dotenv()

# ─── LLM 配置 ───────────────────────────────────────────────────────────────
# OpenAI API 密钥，用于调用语言模型生成测试计划和代码
# 若使用 DeepSeek、Qwen 等兼容 API，需同时设置 OPENAI_BASE_URL
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
# OpenAI 兼容 API 的基地址，支持切换至 DeepSeek、Qwen 等模型提供商
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
# 使用的模型名称，默认为 gpt-4o-mini（轻量级，成本较低）
MODEL_NAME: str = os.getenv("MODEL_NAME", "gpt-4o-mini")
# 温度参数，控制模型输出的随机性；越低越确定性，越高越有创造性
TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.2"))

# ─── 数据库配置 ──────────────────────────────────────────────────────────────
# MySQL 数据库连接参数
MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
# MySQL 端口，默认 3306
MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
# 数据库密码，建议通过环境变量注入，避免硬编码
MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
# 数据库名称，AITester 的所有表将创建在此数据库中
MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "aitester")

# ─── 执行环境配置 ────────────────────────────────────────────────────────────
# 是否启用 Docker 隔离执行测试；false 时在本地执行（速度更快）
DOCKER_ENABLED: bool = os.getenv("DOCKER_ENABLED", "false").lower() == "true"
# Docker 镜像名称，用于容器化测试执行环境
DOCKER_IMAGE: str = os.getenv("DOCKER_IMAGE", "python:3.11-slim")
# 单次测试执行的最大超时时间（秒），防止被测函数死循环导致进程卡死
# 可通过环境变量 EXECUTION_TIMEOUT 覆盖，默认 30 秒
EXECUTION_TIMEOUT: int = int(os.getenv("EXECUTION_TIMEOUT", "30"))

# ─── 工作流配置 ──────────────────────────────────────────────────────────────
# 最大修复迭代次数：达到此次数后停止修复，无论测试是否通过
MAX_ITERATIONS: int = int(os.getenv("MAX_ITERATIONS", "3"))
# 覆盖率阈值：当代码覆盖率达到此百分比时视为测试合格
COVERAGE_THRESHOLD: float = float(os.getenv("COVERAGE_THRESHOLD", "80.0"))

# ─── 消融实验开关 ────────────────────────────────────────────────────────────
# 启用/禁用 Planner 节点（测试计划生成）
# False 时 Generator 直接基于目标代码生成测试，跳过逻辑分析阶段
ENABLE_PLANNER: bool = os.getenv("ENABLE_PLANNER", "true").lower() == "true"

# 启用/禁用 RAG 检索增强（Generator 和 Debugger 的相似案例检索）
# 需安装 chromadb（pip install "aitester[rag]"）
ENABLE_RAG: bool = os.getenv("ENABLE_RAG", "false").lower() == "true"

# 启用/禁用 Debugger 修复节点（调试自修复循环）
# False 时 Executor 失败后直接结束，不进行修复
ENABLE_DEBUGGER: bool = os.getenv("ENABLE_DEBUGGER", "true").lower() == "true"

# ─── 实验配置 ────────────────────────────────────────────────────────────────
# 批量基准测试的并行度（同时运行的任务数，0 表示串行，暂未实现多线程）
BENCHMARK_PARALLELISM: int = int(os.getenv("BENCHMARK_PARALLELISM", "0"))
# 单个任务的 LLM 调用超时（秒）
LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))
# LLM 限流等待时间（秒），用于 rate limit 后重试
LLM_RETRY_WAIT: int = int(os.getenv("LLM_RETRY_WAIT", "30"))
# 第二个 LLM API 配置（可选，用于并行基准测试分摊限流压力）
OPENAI_API_KEY_2: str = os.getenv("OPENAI_API_KEY_2", "")
OPENAI_BASE_URL_2: str = os.getenv("OPENAI_BASE_URL_2", "")

# ─── 第三个 LLM API 配置（BigModel 备用）────────────────────────────────────
# 当 Agnes 国际/国内 API 限流或失败时自动切换
OPENAI_API_KEY_3: str = os.getenv("OPENAI_API_KEY_3", "")
OPENAI_BASE_URL_3: str = os.getenv("OPENAI_BASE_URL_3", "")
LLM_MODEL_BIGMODEL: str = os.getenv("LLM_MODEL_BIGMODEL", "GLM-4-Flash")
