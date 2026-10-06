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
import math
import os
import threading
from dataclasses import dataclass

from dotenv import load_dotenv

# ─── 基础配置加载（.env，非敏感项）───────────────────────────────────────────
load_dotenv()


# ─── R15（2026-10-05 审查 P2）：AITESTER_PROFILE 开关预设 ─────────────────────
# 背景：全仓 60+ 环境变量开关导航成本高（审查指出"开关矩阵不可导航"）。
# Profile 用 os.environ.setdefault 注入一组推荐开关值——**不覆盖用户显式
# 设置**（显式 env 优先级最高），且发生在各开关定义求值之前（本块位于
# 全部开关常量定义之前），保证 setdefault 的值被后续 os.getenv 读到。
# 预设口径（均可被单开关显式覆盖；未识别的 profile 值记 WARNING 并忽略）：
#   safe       —— 安全敏感档：执行隔离 + 补丁回滚 + 注入守卫全开
#                 （KERNEL_SANDBOX / PATCH_SNAPSHOT_ROLLBACK / INJECTION_GUARD /
#                  ROGUE_MONITOR / CREDENTIAL 白名单环境已默认启用）；
#   scientific —— 科研评测档：R1c/R5 审查落地的评测链路全开
#                 （SPEC_IR / SPEC_IR_DSL / SPEC_ORACLE_EXEC / MUTATION_SCORING /
#                  ORACLE_VALIDATE），配合 run_benchmark(deterministic=True)；
#   logic      —— 逻辑链全开档（2026-10-05 系统审查 O1）：scientific 超集，
#                 另开规约强校验 / 确定性守卫 / 分支覆盖注入 / 结构化路由——
#                 使"逻辑驱动"主张的完整链路（规约解析→DSL 编译→确定性
#                 oracle→守卫→覆盖测量→结构化路由）一键可测可观测；
#   fast       —— 历史默认档（全部维持默认关，与不设 PROFILE 等价）。
_PROFILE_PRESETS: dict[str, dict[str, str]] = {
    "safe": {
        "KERNEL_SANDBOX_ENABLE": "true",
        "PATCH_SNAPSHOT_ROLLBACK_ENABLE": "true",
        "PATCH_ROLLBACK_FAIL_CLOSED": "true",
        "INJECTION_GUARD_ENABLE": "true",
        "ROGUE_MONITOR_ENABLE": "true",
        "FLAKY_CHECK_ENABLE": "true",
    },
    "scientific": {
        # U12（2026-10-05 系统性审查落地）：补 SPEC_SMT_ENABLE——SMT 见证层
        # （T2 批次新增）属规约确定性 oracle 链路的一部分，scientific 档
        # 应一键覆盖（z3 未安装时保守降级，无行为风险）。
        "SPEC_IR_ENABLE": "true",
        "SPEC_IR_DSL_ENABLE": "true",
        "SPEC_SMT_ENABLE": "true",
        "SPEC_ORACLE_EXEC_ENABLE": "true",
        "ENABLE_MUTATION_SCORING": "true",
        "ORACLE_VALIDATE_ENABLE": "true",
        "PATCH_SNAPSHOT_ROLLBACK_ENABLE": "true",
    },
    "logic": {
        # scientific 全量（评测链路）
        "SPEC_IR_ENABLE": "true",
        "SPEC_IR_DSL_ENABLE": "true",
        # U12：SMT 见证层（与前件约束求解见证，逻辑链路组成部分）
        "SPEC_SMT_ENABLE": "true",
        "SPEC_ORACLE_EXEC_ENABLE": "true",
        "ENABLE_MUTATION_SCORING": "true",
        "ORACLE_VALIDATE_ENABLE": "true",
        "PATCH_SNAPSHOT_ROLLBACK_ENABLE": "true",
        # U12：回滚 fail-closed——逻辑档主批次口径"回归无法裁决 = 回滚"
        # （R4b 开关；bad-test 误杀由 M1 None 口径在下游兜底）
        "PATCH_ROLLBACK_FAIL_CLOSED": "true",
        # 逻辑链强化（O1）：规约 schema 强校验（拒绝空规约静默兜底）+
        # 确定性守卫 + AST 边界锚点注入 + 分支覆盖测量 + 结构化路由
        # （替代中文诊断关键词路由，ROUTE_STRUCTURED 默认关的历史口径在此档打开）
        "LOGIC_SPEC_STRICT_ENABLE": "true",
        "DETERMINISTIC_GUARD_ENABLE": "true",
        "BRANCH_COVERAGE_INJECT_ENABLE": "true",
        "ROUTE_STRUCTURED_ENABLE": "true",
        # AA（2026-10-06 代码优化批次）：检出优先协议（ADR-0015 / W3）——logic 档
        # 定义于 O1，早于 W3 落地，漏配行为层核心开关。ADR-0015"可经
        # AITESTER_PROFILE=logic 组合"的口径由此补齐：开启后首轮全绿不再计成功，
        # 路由 regenerate 逼 generator 先检出（红）再修复（绿），直指主批次
        # false_fix=89.8% 的奖励自指根因（代价：+1 LLM call/任务，
        # regeneration_count 上限保护）。默认档（fast / 不设 PROFILE）零变化。
        "DETECTION_FIRST_ENABLE": "true",
        # AB1（2026-10-06 生死实验根因修复）：M10 强校验拒绝降级出口——
        # 实验实测 21/261 任务因 strict raise 整任务死亡（detection=None，
        # M1 分母外），同任务 plain_llm_df 臂正常检出。开启后强校验拒绝
        # 改为显式标记（logic_spec_rejected）+ 降级继续，吞吐恢复且
        # 非"静默"兜底（M10 科学主张口径不回退）。默认档零变化
        # （LOGIC_SPEC_STRICT_ENABLE 默认 false，本开关无从触发）。
        "LOGIC_SPEC_STRICT_FALLBACK_ENABLE": "true",
        # AC2（2026-10-06 第十轮审查 T-P0-4）：检出优先协议双门——
        # ①特异性门：首轮红在 gold fixed 上对照执行，过红（非缺陷特异）
        # 路由 regenerate 而非修复循环（机制依据：生死实验 88 行过红通道）；
        # ②红回归门：再生成测试在未修补源码上变绿 = 抹红假成功，恢复
        # 红证人交回修复循环（机制依据：28 行抹红通道）。两门均默认关，
        # logic 档（检出优先协议主口径）注入开启。
        "DETECTION_SPECIFICITY_GATE_ENABLE": "true",
        "RED_REGRESSION_GATE_ENABLE": "true",
        # AI1（2026-10-06 第十一轮审查漏配审计）：FL 谱定位（Ochiai）——
        # fl_spectral 经 C3（第四轮）修复后从未接入 logic 档：生死实验
        # 实测 fl_at_k 0/87 全空（ab1 env 快照 FL_SPECTRAL_ENABLE=None
        # 实证），定位质量指标在全部 logic 档批次缺数。E2 复跑前补齐
        # （AA1 同类"漏配补齐"先例：档位定义早于该能力落地）。纯测量
        # 开关，不改变生成/修复行为；默认档零变化。
        "FL_SPECTRAL_ENABLE": "true",
    },
    "fast": {},
}


def _apply_profile_presets() -> str | None:
    """按 AITESTER_PROFILE 注入预设开关（setdefault，显式 env 不被覆盖）。

    Returns:
        生效的 profile 名（未设置时 None）；未识别值记 WARNING 返回 None。
    """
    profile = (os.getenv("AITESTER_PROFILE") or "").strip().lower()
    if not profile:
        return None
    presets = _PROFILE_PRESETS.get(profile)
    if presets is None:
        logging.getLogger(__name__).warning(
            "AITESTER_PROFILE=%r 未识别（可选：safe/scientific/logic/fast），忽略", profile
        )
        return None
    for key, value in presets.items():
        os.environ.setdefault(key, value)
    logging.getLogger(__name__).info(
        "AITESTER_PROFILE=%s 生效：%d 个开关预设注入（显式设置不受影响）", profile, len(presets)
    )
    return profile


ACTIVE_PROFILE: str | None = _apply_profile_presets()


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
    """容错读取浮点环境变量（语义同 _parse_int_env，针对 float）。

    非有限值（NaN / ±inf）与越界值同口径回退默认值：`nan` 参与任何 `<` / `>`
    比较都返回 False，只做范围检查会让 `COVERAGE_THRESHOLD=nan` 这类值静默
    穿透（覆盖率门槛恒不满足、阈值判定恒 False），故先做 isfinite 判定。
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError:
        logger.warning("环境变量 %s=%r 不是合法浮点数，回退默认值 %g", name, raw, default)
        return default
    if not math.isfinite(value):
        logger.warning("环境变量 %s=%r 非有限值（NaN/inf），回退默认值 %g", name, raw.strip(), default)
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
# Z2（2026-10-06 审查修复）：测试再生成次数上限的单一事实源。此前该值以
# 字面量 1 同时硬编码在 workflow._MAX_REGENERATIONS 与 nodes 内局部变量
# （两处靠注释"同口径"维系），漂移风险已在审查中登记。取 1：一次再生成
# 已足够验证"换一版测试"是否解决问题，再多只会浪费 token（背景见
# workflow.py 同名注释）。非环境变量（不进 env_budget 登记口径）。
MAX_REGENERATIONS: int = 1
# 范围 [0, 100]：百分比阈值超出区间无意义（来源：覆盖率定义域）
COVERAGE_THRESHOLD: float = _parse_float_env("COVERAGE_THRESHOLD", 80.0, 0.0, 100.0)

# ─── 消融实验开关 ────────────────────────────────────────────────────────────
ENABLE_PLANNER: bool = os.getenv("ENABLE_PLANNER", "true").lower() == "true"
ENABLE_RAG: bool = os.getenv("ENABLE_RAG", "false").lower() == "true"
ENABLE_DEBUGGER: bool = os.getenv("ENABLE_DEBUGGER", "true").lower() == "true"


def detection_first_enabled() -> bool:
    """W3（2026-10-05 审查落地）：检出优先协议开关（DETECTION_FIRST_ENABLE）。

    背景：主批次（benchmark_synthetic_20261001_121523）实证 false_fix_rate=89.8%——
    修复循环以"自产测试通过"为成功信号，系统被奖励生成"能在缺陷代码上通过"
    的弱测试而非"能让缺陷代码变红"的强测试。检出优先协议（"先红后绿"）：

    1. 首轮执行（iteration==0，被测代码未修复）全绿 = 测试未检出任何缺陷
       → 不视为成功，路由 regenerate 逼 generator 生成能让缺陷代码变红的
       测试（受 _MAX_REGENERATIONS 上限保护，防乒乓）；
    2. 首轮曾红（detection_first_red_seen=True）且修复后变绿 → 成功标记
       red_then_green；再生成预算耗尽仍全绿 → all_green_unverified
       （评估层应归入"未验证"，不计修复成功）。

    读取口径：函数调用时读 env（非 import 期常量），与 nodes 层
    TEST_SUITE_DEDUP_ENABLE 等开关同口径，便于测试 monkeypatch 与
    运行时切换。默认 false 保持历史行为零变化（ADR-0003）。

    X1（2026-10-05 审查 P0-3）：线程级覆盖。基准实验在同一进程内逐基线
    顺序执行（run_benchmark 任务循环内 BASELINE_REGISTRY 逐个调用），
    但 --parallel 下多个任务线程并发——进程级 os.environ 开关无法
    区分"本线程正在跑 plain_llm_df 基线"与"邻线程正在跑 plain_llm"。
    线程局部覆盖（set_detection_first_thread_override）供
    run_plain_llm_df_baseline 在自身执行窗口内强制开启检出优先，
    不污染同进程其他基线；None（默认）时回落 env 口径。
    """
    _override = getattr(_DETECTION_FIRST_THREAD_LOCAL, "override", None)
    if _override is not None:
        return bool(_override)
    return os.getenv("DETECTION_FIRST_ENABLE", "false").lower() in ("true", "1", "on")


# X1：检出优先协议的线程局部覆盖载体（与 llm_client._thread_local 同模式）
_DETECTION_FIRST_THREAD_LOCAL = threading.local()


def set_detection_first_thread_override(value: bool | None) -> None:
    """设置/清除当前线程的检出优先覆盖（None = 回落 env 开关）。

    供 run_benchmark 的 plain_llm_df 基线在 invoke 窗口内启用检出优先
    路由与 prompt 段落；finally 中置 None 恢复，防跨任务残留
    （线程池线程复用时尤其重要）。
    """
    _DETECTION_FIRST_THREAD_LOCAL.override = value


# 1.2 变异得分评估：benchmark 运行后对每个任务的"生成测试 vs 被测源码"
# 计算 mutation_score（内置轻量变异生成器，experiments/mutation_testing.py）。
# 默认关闭——变异测试需对每任务跑 N 个变异体 × pytest 子进程（约 1-3s/变异体，
# 20 变异体 ≈ 30-60s/任务），对全量实验是显著的时间税；显式开启（True）
# 才在 run_benchmark 流水线末尾逐任务计算并写入 details[].mutation_score。
# 与 ENABLE_RAG 同口径：消融实验开关，不影响核心修复管线，仅影响评估产出。
ENABLE_MUTATION_SCORING: bool = os.getenv("ENABLE_MUTATION_SCORING", "false").lower() == "true"
# 每任务最多评估的变异体数量（来源：mutation_testing.MutationGenerator._MAX_MUTANTS_PER_TASK
# 的上限口径；T3（2026-10-05 优化批次）默认 10→20——审查 G10：10 个变异体下
# mutation_detection_rate 的二值噪声区间过宽（±30pct），20 个起才有区分度；
# 变异评估为 opt-in（ENABLE_MUTATION_SCORING 默认关），调默认不影响历史批次）
MUTATION_MAX_MUTANTS: int = _parse_int_env("MUTATION_MAX_MUTANTS", 20, 1, None)

# ─── 4.4 API 观测层开关（0.6 轮次幽灵开关实装）──────────────────────────────
# 0.6 轮次性能/文档审计发现：.env.example / QUICKSTART / api_reference /
# reproduce.sh / CHANGELOG / README 六处文档描述以下两个开关为"对比实验"
# 能力（false 时回退 4.2 固定冷却期 / Prometheus 导出关闭），但全仓无任何
# 代码读取点——用户设 false 不会发生任何事（幽灵开关）。现经 config 集中
# 声明后由 api_health / api_manager 读取，文档承诺落地。
# API_CIRCUIT_BACKOFF：熔断器指数退避开关（4.4）。默认 true（保持 4.4 行为，
# 开启指数退避）；设 false 时熔断器使用固定冷却期（_CIRCUIT_COOLDOWN_S）
# 作为 4.2 历史对照口径。
API_CIRCUIT_BACKOFF: bool = os.getenv("API_CIRCUIT_BACKOFF", "true").lower() == "true"
# API_PROMETHEUS_EXPORT：Prometheus 指标导出开关（4.4）。默认 false（保持
# 历史行为：to_prometheus_text() 默认不输出指标，纯旁路不影响路由）；
# 设 true 时 APIManager.to_prometheus_text() 导出 7 类指标供监控抓取。
API_PROMETHEUS_EXPORT: bool = os.getenv("API_PROMETHEUS_EXPORT", "false").lower() == "true"

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
# 本地执行：被测代码 import 的第三方库缺失时测试直接失败，且无法区分
# "代码 bug"与"环境缺依赖"。
# 沙箱模式（EXECUTOR_USE_VENV=true）：为任务创建隔离 venv 并用其解释器执行
# pytest，通过 PYTHONPATH 控制模块搜索路径，避免污染系统环境。
# R10（2026-09-30 独立审查 N8，P1）起**默认开启 venv 沙箱**：LLM 生成的
# 测试代码在隔离 venv 内执行（venv 缓存在 ~/.cache/aitester/venvs/，
# 相同依赖组合任务复用），不再直接落在宿主系统 Python 环境——
# 默认配置从 fail-open（无沙箱）转为 fail-closed（有沙箱），
# 消除"默认在宿主机执行任意 LLM 生成代码"的攻击面。
# 设 EXECUTOR_USE_VENV=false 可显式退回"本地系统 Python"历史口径
# （仅调试 / 无 venv 权限的环境使用）。
EXECUTOR_USE_VENV: bool = os.getenv("EXECUTOR_USE_VENV", "true").lower() == "true"
# 是否自动 pip install 缺失的第三方依赖（需配合 venv 沙箱使用）
EXECUTOR_AUTO_INSTALL_DEPS: bool = os.getenv("EXECUTOR_AUTO_INSTALL_DEPS", "false").lower() == "true"
# 依赖安装等待超时（秒）：防止 pip 网络卡顿拖垮整个实验
EXECUTOR_DEP_INSTALL_TIMEOUT: int = _parse_int_env("EXECUTOR_DEP_INSTALL_TIMEOUT", 120, 10, None)
# 4.3 Docker 隔离执行（预留接口转正，默认关）：
# EXECUTOR_USE_DOCKER=true 时 ExecutorAgent 经 docker CLI 在容器内跑 pytest，
# 需本机安装 docker 且镜像已构建（镜像名可经 EXECUTOR_DOCKER_IMAGE 覆盖，
# 默认 aitester:latest，对应仓库根 Dockerfile）。
EXECUTOR_USE_DOCKER: bool = os.getenv("EXECUTOR_USE_DOCKER", "false").lower() == "true"
EXECUTOR_DOCKER_IMAGE: str = os.getenv("EXECUTOR_DOCKER_IMAGE", "aitester:latest")

# ─── P0 仓库级验证（SWE-bench 官方口径，默认关）─────────────────────────────
# REPO_LEVEL_EXECUTION=true 时，experiments/run_benchmark.py 对携带
# source/repo_url/base_commit/fail_to_pass 元数据的任务（仅 SWE-bench 数据集
# 经加载器产出）启用 RepoExecutor 仓库级验证：clone + checkout + pip install -e
# 的环境缓存内，把 LLM 补丁与 gold test_patch 应用进真实仓库工作区，跑
# FAIL_TO_PASS（修复前失败、修复后须全过）与 PASS_TO_PASS（不得回归）实测。
# 合成数据集 / examples 任务无这些元数据字段，永不命中，历史口径零变化。
# 环境缓存根目录 SWE_REPO_ENVS_DIR 默认 ~/.cache/aitester/repo_envs/
# （(repo, commit) 分目录复用，同仓库多任务只 clone/pip 一次）。
REPO_LEVEL_EXECUTION: bool = os.getenv("REPO_LEVEL_EXECUTION", "false").lower() == "true"
# 仓库级环境 setup 子进程超时（秒）：clone + checkout + pip install -e 远慢于
# 单任务测试执行，默认 600s；缓存命中后不再触发。
SWE_REPO_SETUP_TIMEOUT: int = _parse_int_env("SWE_REPO_SETUP_TIMEOUT", 600, 60, None)
# P1 仓库级 venv 隔离（默认关，opt-in）：SWE_REPO_VENV_ISOLATION=true 时
# RepoExecutor 在每个 (repo, commit) 环境旁建独立 venv，pip install -e 装入
# venv（而非全局 sys.executable），pytest 用 venv 的 python 运行。
# 各 repo_env 共享全局 python 时，全局 site-packages 的 editable 安装指向
# "最近一次 pip install -e"的 commit 源码 → 跨 commit 任务 `import <repo_pkg>`
# M3（2026-09-29 审查 P0 + D.4-7）：SWE-bench 实例可解性前置门禁。
# R46（2026-09-30 独立审查 P0）起 SWE-bench 批次**默认开启门禁**
# （SWE_BENCH_P2P_GATE_ENABLE 缺省视为 "true"）：SWE-bench ProMax 实测
# ~60% 未解出实例的测试本身有缺陷（P2P 基线通过率不达标），把"0 解出"
# 从"能力边界"误读为"系统无效"——开门禁后不可解实例记 harness_invalid
# 并剔除（不计入失败统计），0% 还原为"harness 无效"。
# 设 SWE_BENCH_P2P_GATE_ENABLE=false 可显式退回"关闭"历史口径
# （消融对照 / 无 verify 脚本环境使用）。
# 仅对 source=swe_bench 且含 repo_url/base_commit 的任务生效（合成 /
# examples 任务永不命中，零行为变化）；验证基线 PASS_TO_PASS ≥
# SWE_BENCH_P2P_GATE_THRESHOLD，不可解实例标记 harness_invalid 剔除。
SWE_BENCH_P2P_GATE_ENABLE: bool = os.getenv("SWE_BENCH_P2P_GATE_ENABLE", "true").lower() == "true"
# 阈值经容错解析（坏值回退 0.95）+ [0, 1] 范围校验（通过率阈值超出区间无意义）：
# 此前此处是裸 float(os.getenv(...))，与本文件"坏值不让 import 崩溃"的口径
# 相悖——SWE_BENCH_P2P_GATE_THRESHOLD=abc 会让所有入口（import config）直接
# ValueError 崩溃。
SWE_BENCH_P2P_GATE_THRESHOLD: float = _parse_float_env("SWE_BENCH_P2P_GATE_THRESHOLD", 0.95, 0.0, 1.0)
# 解析到错误版本（实测 sqlfluff BaseSegment._log_apply_fixes_check_issue
# 在 8e724ef 存在、38cff664 不存在 → AttributeError，与 LLM 补丁无关）。
# 默认关保持与已缓存 repo_envs（全局 .pip_installed 标记）的兼容；
# 开启时 RepoExecutor 按 .venv_pip_installed 标记判缓存命中（新建 venv）。
# venv 模式下不注入宿主 PYTHONPATH（实测带注入反而 ImportError），
# PATH 前置 venv/bin（子进程内再调 python/pip 时指向 venv）。
SWE_REPO_VENV_ISOLATION: bool = os.getenv("SWE_REPO_VENV_ISOLATION", "false").lower() == "true"

# ─── 实验配置 ────────────────────────────────────────────────────────────────
# 0 = 串行（合法值），最小 0 防止负并行度
BENCHMARK_PARALLELISM: int = _parse_int_env("BENCHMARK_PARALLELISM", 0, 0, None)
# 先容错解析（坏值回退默认 60），再走 _validate_timeout 范围校验（[30, 300]）
_LLM_TIMEOUT_RAW = _parse_int_env("LLM_TIMEOUT", 60)
LLM_TIMEOUT: int = _validate_timeout(_LLM_TIMEOUT_RAW, "LLM_TIMEOUT", 30, 300, 60)
# 最小 1：等待 0 秒等于不等待，重试退避失去意义
LLM_RETRY_WAIT: int = _parse_int_env("LLM_RETRY_WAIT", 30, 1, None)
# 单次 LLM 调用的全局墙钟总预算（秒）：覆盖"故障转移 × 模型 × 重试"整段，
# 超出即快速失败（防极端组合下基准跑批被单任务卡死数十分钟；0.7 债务项 2.2）
LLM_CALL_BUDGET_SECONDS: int = _parse_int_env("LLM_CALL_BUDGET_SECONDS", 600, 1, None)

# ─── 功能模块自有开关（默认关，不在本文件集中声明）──────────────────────────
# 说明：CROSS_FILE_ENABLE / CROSS_FILE_MAX_MODULES（3.5 跨文件修复）与
# ASSERTION_AUGMENT_ENABLE（3.4 断言增强）等"默认关"的实验性功能开关，由各自
# 功能模块在调用期读取环境变量（cross_file.py / generator.py，与 multi_candidate.py
# 模式一致），以保留测试的运行期切换能力（patch.dict(os.environ)）。此处在 config.py
# 再定义一份会造成"双源漂移"，故 2026-09-15 收敛轮次移除重复常量，配置说明见
# .env.example 对应小节与各功能模块 docstring。
