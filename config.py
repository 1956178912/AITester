"""
全局配置文件：集中管理所有环境变量和常量。

此模块从 .env 文件读取基础配置，并从 .env.local 覆盖 LLM 敏感配置。
修改配置项时，优先修改此文件，而非在各处硬编码。

LLM 配置（API Key / Base URL / Model）属于敏感信息，
统一在 .env.local 中管理（已通过 .gitignore 排除），
此处以 <PLACEHOLDER> 标记，实际值由 load_env_local() 注入。
"""

from __future__ import annotations

import logging
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


# ─── 数值环境变量容错解析 ─────────────────────────────────────────────────────
# 所有数值型配置统一经此解析：坏值（如 MAX_ITERATIONS=abc）不再让 import 崩溃，
# 而是记 WARNING 并回退默认值。默认值与范围约束的来源见各配置项注释。
logger = logging.getLogger(__name__)


def _parse_int_env(name: str, default: int, min_val: int | None = None, max_val: int | None = None) -> int:
    """容错读取整型环境变量。

    未设置/空值 → 返回 default；非数字 → 警告并返回 default；
    超出 [min_val, max_val]（None 侧不限制）→ 警告并返回 default。

    Args:
        name: 环境变量名。
        default: 缺省值。
        min_val: 允许的最小值（None 表示不限制）。
        max_val: 允许的最大值（None 表示不限制）。

    Returns:
        合法的环境变量值；非法或未设置时返回 default。
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        logger.warning("环境变量 %s=%r 不是合法整数，回退默认值 %d", name, raw, default)
        return default
    if (min_val is not None and value < min_val) or (max_val is not None and value > max_val):
        logger.warning("环境变量 %s=%d 超出范围 [%s, %s]，回退默认值 %d", name, value, min_val, max_val, default)
        return default
    return value


def _parse_float_env(name: str, default: float, min_val: float | None = None, max_val: float | None = None) -> float:
    """容错读取浮点环境变量（语义同 _parse_int_env，针对 float）。"""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError:
        logger.warning("环境变量 %s=%r 不是合法浮点数，回退默认值 %g", name, raw, default)
        return default
    if (min_val is not None and value < min_val) or (max_val is not None and value > max_val):
        logger.warning("环境变量 %s=%g 超出范围 [%s, %s]，回退默认值 %g", name, value, min_val, max_val, default)
        return default
    return value


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
#   LLM_1_MODEL_NAME=agnes-3.0-flash
#   LLM_2_API_KEY=sk-another-key
#   LLM_2_BASE_URL=https://api.deepseek.com
#   LLM_2_MODEL_NAME=deepseek-chat
#
# 注意：编号无需连续（删除中间某个 provider 后剩余编号自动保留），
# _load_llm_configs 会扫描到固定上限并跳过不完整的编号。

load_env_local()  # 加载 .env.local，覆盖敏感 LLM 配置

# LLM 编号扫描上限：容忍 .env.local 中删除中间 provider 产生的编号空洞
_LLM_MAX_SCAN_INDEX = 32


@dataclass(frozen=True)
class LLMConfig:
    """单个 LLM Provider 的配置，包含 api_key、base_url、model_name。

    字段:
        api_key: API 密钥（敏感，来自 .env.local）。
        base_url: 服务 Base URL。
        model_name: 模型名称。
        cost_weight: 相对成本倍数（3.4 成本感知路由，来源 llm_configs.json 的
            cost_weight 字段，未配置时 0.0 表示"无成本信息"，APIManager 回退 1.0）。
    """

    api_key: str
    base_url: str
    model_name: str
    cost_weight: float = 0.0


def _load_llm_configs() -> list[LLMConfig]:
    """从环境变量中读取所有 LLM_N_* 配置，返回完整配置列表。

    环境变量命名规则：
        LLM_1_API_KEY, LLM_1_BASE_URL, LLM_1_MODEL_NAME   → 第 1 个配置
        LLM_2_API_KEY, LLM_2_BASE_URL, LLM_2_MODEL_NAME   → 第 2 个配置
        ...

    只有 api_key、base_url、model_name 三项均非空时，该配置才会被加入列表。
    扫描至 _LLM_MAX_SCAN_INDEX 上限，容忍编号空洞（如删除 LLM_2 后 LLM_3 仍会被加载），
    不再在第一个不完整编号处中断。
    """
    configs: list[LLMConfig] = []
    for idx in range(1, _LLM_MAX_SCAN_INDEX + 1):
        api_key = os.getenv(f"LLM_{idx}_API_KEY", "").strip()
        base_url = os.getenv(f"LLM_{idx}_BASE_URL", "").strip()
        model_name = os.getenv(f"LLM_{idx}_MODEL_NAME", "").strip()
        if not api_key or not base_url or not model_name:
            continue  # 不完整编号跳过，继续扫描后续编号
        # 3.4 成本感知路由：可选读取 LLM_{idx}_COST_WEIGHT（相对成本倍数），
        # 未设置时 0.0 表示"无成本信息"（APIManager 回退 1.0 基准）
        cost_weight = _parse_float_env(f"LLM_{idx}_COST_WEIGHT", 0.0, 0.1, 1000.0)
        configs.append(LLMConfig(api_key=api_key, base_url=base_url, model_name=model_name, cost_weight=cost_weight))
    return configs


# 所有已配置的 LLM Provider 列表（按 LLM_1, LLM_2, ... 顺序）
# 注意：其他模块通过 `from config import LLM_CONFIGS` 持有的是同一个列表对象，
# 因此 refresh_llm_configs() 采用"原地更新"（LLM_CONFIGS[:] = ...），
# 使所有持有方都能看到刷新后的值，而不是得到一个隔离的快照。
LLM_CONFIGS: list[LLMConfig] = _load_llm_configs()

# 默认使用的 LLM 配置（取第一个，即 LLM_1）
DEFAULT_LLM_CONFIG: LLMConfig | None = LLM_CONFIGS[0] if LLM_CONFIGS else None


def refresh_llm_configs() -> list[LLMConfig]:
    """重新扫描 LLM_N_* 环境变量并原地刷新 LLM_CONFIGS 列表。

    供 config_manager 的 add/remove 操作在写入 .env.local 之后调用，
    使内存中的配置与文件内容保持一致（否则导入时的快照不会自动更新）。

    Returns:
        刷新后的 LLM_CONFIGS 列表（与模块级常量是同一个对象）。
    """
    LLM_CONFIGS[:] = _load_llm_configs()
    return LLM_CONFIGS


# 向后兼容：保留旧的扁平变量名，指向默认 LLM 配置（供旧代码引用）
OPENAI_API_KEY: str = DEFAULT_LLM_CONFIG.api_key if DEFAULT_LLM_CONFIG else ""
OPENAI_BASE_URL: str = DEFAULT_LLM_CONFIG.base_url if DEFAULT_LLM_CONFIG else ""
MODEL_NAME: str = DEFAULT_LLM_CONFIG.model_name if DEFAULT_LLM_CONFIG else ""
# TEMPERATURE 非敏感配置，可留在 .env 或 .env.local 中
# 范围 [0, 2]：OpenAI 兼容接口的合法采样温度上限（来源：OpenAI API 文档）
TEMPERATURE: float = _parse_float_env("TEMPERATURE", 0.2, 0.0, 2.0)


# ─── 数据库配置 ──────────────────────────────────────────────────────────────
MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT: int = _parse_int_env("MYSQL_PORT", 3306, 1, 65535)
MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "aitester")

# MySQL 连接池参数（PooledDB）：此前硬编码在 mysql_client.py，
# 现统一由环境变量配置，便于按实验规模（如 --parallel 并发）调整。
# 默认值与历史硬编码值保持一致，保证未配置时行为不变。
# min_cached 必须 ≤ max_cached ≤ max_connections，越界值由 PooledDB 侧兜底告警。
MYSQL_POOL_MIN_CACHED: int = _parse_int_env("MYSQL_POOL_MIN_CACHED", 5, 0, None)
MYSQL_POOL_MAX_CACHED: int = _parse_int_env("MYSQL_POOL_MAX_CACHED", 10, 0, None)
MYSQL_POOL_MAX_CONNECTIONS: int = _parse_int_env("MYSQL_POOL_MAX_CONNECTIONS", 20, 1, None)
# 获取连接的等待超时（秒），范围 [1, 600]：0 意味着拿不到连接就失败，无意义
MYSQL_POOL_TIMEOUT: int = _parse_int_env("MYSQL_POOL_TIMEOUT", 30, 1, 600)


# ─── 超时配置验证函数 ────────────────────────────────────────────────────────
def _validate_timeout(value: int, name: str, min_val: int, max_val: int, default: int) -> int:
    """验证超时配置值是否在合理范围内。

    若配置值超出范围，记录警告并使用默认值，防止因错误配置导致服务卡死或超时过短。

    Args:
        value: 用户配置的值。
        name: 配置项名称（用于日志）。
        min_val: 允许的最小值。
        max_val: 允许的最大值。
        default: 超出范围时的默认值。

    Returns:
        验证后的有效值（在 [min_val, max_val] 范围内）。
    """
    if value < min_val or value > max_val:
        logging.getLogger(__name__).warning(
            "%s 配置值 %d 超出范围 [%d, %d]，使用默认值 %d",
            name,
            value,
            min_val,
            max_val,
            default,
        )
        return default
    return value


# ─── 执行环境配置 ────────────────────────────────────────────────────────────
DOCKER_ENABLED: bool = os.getenv("DOCKER_ENABLED", "false").lower() == "true"
# 锁定依赖集（scipy==1.18.0 等）要求 Python >= 3.12，镜像须匹配
DOCKER_IMAGE: str = os.getenv("DOCKER_IMAGE", "python:3.12-slim")
# 先容错解析（坏值回退默认 30），再走 _validate_timeout 范围校验（[10, 300]）
_EXECUTION_TIMEOUT_RAW = _parse_int_env("EXECUTION_TIMEOUT", 30)
EXECUTION_TIMEOUT: int = _validate_timeout(_EXECUTION_TIMEOUT_RAW, "EXECUTION_TIMEOUT", 10, 300, 30)

# ─── 工作流配置 ──────────────────────────────────────────────────────────────
# 最小 1：迭代 0 次的工作流无意义（至少执行一次生成/执行循环）
MAX_ITERATIONS: int = _parse_int_env("MAX_ITERATIONS", 3, 1, None)
# 范围 [0, 100]：百分比阈值超出区间无意义（来源：覆盖率定义域）
COVERAGE_THRESHOLD: float = _parse_float_env("COVERAGE_THRESHOLD", 80.0, 0.0, 100.0)

# ─── 消融实验开关 ────────────────────────────────────────────────────────────
ENABLE_PLANNER: bool = os.getenv("ENABLE_PLANNER", "true").lower() == "true"
ENABLE_RAG: bool = os.getenv("ENABLE_RAG", "false").lower() == "true"
ENABLE_DEBUGGER: bool = os.getenv("ENABLE_DEBUGGER", "true").lower() == "true"

# ─── RAG 检索增强配置 ────────────────────────────────────────────────────────
# 持久化路径：默认项目根下 rag_data/（此前总是内存模式，进程重启数据全丢，
# 跨实验运行的历史用例无法复用）。设为空字符串则回退内存模式。
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RAG_PERSIST_PATH: str = os.getenv("RAG_PERSIST_PATH", os.path.join(_PROJECT_ROOT, "rag_data"))
# 集合名：同一持久化目录下按集合名区分不同数据集/实验
RAG_COLLECTION_NAME: str = os.getenv("RAG_COLLECTION_NAME", "aitester_cases")
# TTL：持久化场景下需要跨实验复用，默认放宽到 7 天（内存模式仍可用默认 1 小时）
RAG_TTL_SECONDS: int = _parse_int_env("RAG_TTL_SECONDS", 7 * 24 * 3600, 60, None)

# ─── 数据集配置 ────────────────────────────────────────────────────────────────
# SWE-bench 源码补充文件路径（P0）：官方 SWE-bench JSONL 不含被测源码字段，
# 通过该 JSONL 按 instance_id 补全 instance_code/test_code。默认空串 = 不补全。
# 环境变量名保持不变（scripts/export_swe_bench_source.py 输出的正是此格式，
# README 复现步骤也以 `SWE_BENCH_ENRICHMENT=<路径>` 引用），仅在此集中声明默认值。
SWE_BENCH_ENRICHMENT: str = os.getenv("SWE_BENCH_ENRICHMENT", "")

# ─── 执行隔离配置（依赖检测 / venv 沙箱）─────────────────────────────────────
# 本地执行默认直接跑在系统 Python 环境：被测代码 import 的第三方库缺失时
# 测试直接失败，且无法区分"代码 bug"与"环境缺依赖"。
# 沙箱模式（EXECUTOR_USE_VENV=true）：为任务创建隔离 venv 并用其解释器执行 pytest，
# 通过 PYTHONPATH 控制模块搜索路径，避免污染系统环境。
EXECUTOR_USE_VENV: bool = os.getenv("EXECUTOR_USE_VENV", "false").lower() == "true"
# 是否自动 pip install 缺失的第三方依赖（需配合 venv 沙箱使用）
EXECUTOR_AUTO_INSTALL_DEPS: bool = os.getenv("EXECUTOR_AUTO_INSTALL_DEPS", "false").lower() == "true"
# 依赖安装等待超时（秒）：防止 pip 网络卡顿拖垮整个实验
EXECUTOR_DEP_INSTALL_TIMEOUT: int = _parse_int_env("EXECUTOR_DEP_INSTALL_TIMEOUT", 120, 10, None)

# ─── 实验配置 ────────────────────────────────────────────────────────────────
# 0 = 串行（合法值），最小 0 防止负并行度
BENCHMARK_PARALLELISM: int = _parse_int_env("BENCHMARK_PARALLELISM", 0, 0, None)
# 先容错解析（坏值回退默认 60），再走 _validate_timeout 范围校验（[30, 300]）
_LLM_TIMEOUT_RAW = _parse_int_env("LLM_TIMEOUT", 60)
LLM_TIMEOUT: int = _validate_timeout(_LLM_TIMEOUT_RAW, "LLM_TIMEOUT", 30, 300, 60)
# 最小 1：等待 0 秒等于不等待，重试退避失去意义
LLM_RETRY_WAIT: int = _parse_int_env("LLM_RETRY_WAIT", 30, 1, None)

# ─── 功能模块自有开关（默认关，不在本文件集中声明）──────────────────────────
# 说明：CROSS_FILE_ENABLE / CROSS_FILE_MAX_MODULES（3.5 跨文件修复）与
# ASSERTION_AUGMENT_ENABLE（3.4 断言增强）等"默认关"的实验性功能开关，由各自
# 功能模块在调用期读取环境变量（cross_file.py / generator.py，与 multi_candidate.py
# 模式一致），以保留测试的运行期切换能力（patch.dict(os.environ)）。此处在 config.py
# 再定义一份会造成"双源漂移"，故 2026-09-15 收敛轮次移除重复常量，配置说明见
# .env.example 对应小节与各功能模块 docstring。
