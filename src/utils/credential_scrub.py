"""
执行环境脱敏工具：从环境变量副本中剔除 LLM API 凭证类变量。

背景（4.1 脱敏审计扩展）：LLM 生成的测试代码在子进程中执行，
子进程环境若继承调用方完整环境变量，则 LLM 凭证（API Key 等）
泄露进被测沙箱——既是凭证暴露面，也是生成代码意外外传的执行向量。

实现为"动态模式剔除"而非固定名单：
- 按前缀模式匹配 `LLM_N_API_KEY` / `LLM_N_BASE_URL`（N 为 1-32 数字）；
- 覆盖 config.py 的 `_LLM_MAX_SCAN_INDEX` 扫描口径（1-32）；
- 避免固定名单遗漏 LLM_3 及以后的凭证。

三条执行链路（本地 / venv 沙箱 / Docker）共用本函数，
保持脱敏口径单一实现（避免名单漂移）。

P2（2026-09-29 批次）：provider 中间变量不再静态枚举——
`_provider_key_patterns()` 从 `config_generator.PROVIDER_TEMPLATES` 的键
自动推导 `{PROVIDER}_API_KEY` / `{PROVIDER}_BASE_URL` 模式（键全名大写），
新增 provider 时脱敏口径自动跟随（消除 LiteLLM CVE-2026-89032 式
"静态枚举与动态接口漂移"根因）；CI 守卫 scripts/check_credential_scrub.py
在新增 provider 未同步时阻断合并。

S4（M11，2026-09-29 审查 P0）：白名单最小化环境构建
`build_minimal_env()`。历史口径的"动态模式剔除"是黑名单——新增凭证
变量（如 `MYSQL_PASSWORD` / `AWS_ACCESS_KEY_ID` / `DATABASE_URL`）
不在剔除名单内即原样进入子进程（实测 `MYSQL_PASSWORD` 泄漏）。
现补白名单：`build_minimal_env()` 仅保留路径/语言/Python/SSL/TMPDIR
等**非敏感**基础变量（13 个，见 `_WHITELIST_ENV_KEYS`），其余一律剔除。
D.4-3（2026-09-30）起 `CREDENTIAL_SCRUB_WHITELIST_ENABLE` **默认 true**
（安全默认"拒绝"口径）；显式设为 `false` 时 `scrub_credentials` 保持
历史黑名单口径（需要全量继承环境的场景）。
"""

from __future__ import annotations

import os
import re
from typing import Any

# 凭证类环境变量剔除模式（按前缀匹配，N 为数字）
# LLM_N_API_KEY / LLM_N_BASE_URL：LLM 配置（config.py _load_llm_configs 扫描口径 1-32）
# LLM_N_MODEL_NAME 非凭证（模型名非敏感），不剔除。
# 通用 SDK 凭证：历史固定名单 + 编号变体通配（.env 实测存在 OPENAI_API_KEY_2/3、
# OPENAI_BASE_URL_2/3 等多端点命名；此前锚定全名 `^OPENAI_API_KEY$` 匹配不到
# 编号变体，凭证原样进被测代码子进程——正是本模块要封堵的"执行向量"）。
_STATIC_CREDENTIAL_PATTERNS = (
    re.compile(r"^LLM_\d+_API_KEY$"),
    re.compile(r"^LLM_\d+_BASE_URL$"),
    # 通用 SDK 凭证（固定名单，与历史本地执行路径口径一致）
    re.compile(r"^(OPENAI_API_KEY|ANTHROPIC_API_KEY|API_KEY|LLM_API_KEY|LLM_CONFIG_API_KEY)$"),
    # 编号变体通配（OPENAI_API_KEY_2、OPENAI_BASE_URL_3 等多端点命名）
    re.compile(r"^OPENAI_API_KEY(_\d+)?$"),
    re.compile(r"^OPENAI_BASE_URL(_\d+)?$"),
)

# provider 中间变量模式（P2 动态推导）：从 PROVIDER_TEMPLATES 键自动派生
# （模块加载期计算一次；config_generator 纯标准库模块，顶层导入安全）
_PROVIDER_BASE_URLS: dict[str, Any] = {}
try:
    from src.config.config_generator import PROVIDER_TEMPLATES

    _PROVIDER_BASE_URLS = dict(PROVIDER_TEMPLATES)
except ImportError:  # config_generator 缺失时回退空（守卫脚本会报出）
    pass

# provider 中间变量的 API Key / Base URL 模式（{PROVIDER}_API_KEY /
# {PROVIDER}_BASE_URL，键全名大写 + 编号变体通配；_d 转义全名内的
# 非单词字符，如 AGNES_DOMESTIC → AGNES_DOMESTIC 无特殊字符恒等）
_PROVIDER_KEY_PATTERNS: tuple[re.Pattern, ...] = tuple(
    re.compile(rf"^{re.escape(provider.upper())}_(API_KEY|BASE_URL)(_{{0,1}}\d+)?$") for provider in _PROVIDER_BASE_URLS
)
# 兼容口径：历史固定名单（ALIYUN_BAILIAN/AGNES_*/BIGMODEL/DEEPSEEK）已被
# 动态推导覆盖；保留显式回退清单仅在 PROVIDER_TEMPLATES 不可用时生效
_PROVIDER_KEY_PATTERNS_FALLBACK = (
    re.compile(
        r"^(ALIYUN_BAILIAN_API_KEY|AGNES_(DOMESTIC|INTERNATIONAL)_API_KEY|BIGMODEL_API_KEY|DEEPSEEK_API_KEY)"
        r"(_\d+)?$"
    ),
)
if not _PROVIDER_KEY_PATTERNS:
    _PROVIDER_KEY_PATTERNS = _PROVIDER_KEY_PATTERNS_FALLBACK

# 合并后的完整剔除模式（动态 provider + 静态通用名单）
_CREDENTIAL_PATTERNS: tuple[re.Pattern, ...] = tuple(list(_STATIC_CREDENTIAL_PATTERNS) + list(_PROVIDER_KEY_PATTERNS))

# S4（M11，2026-09-29 审查 P0；D.4-3 修复 2026-09-30）：白名单最小化环境构建。
# 仅保留路径/语言/Python/SSL/TMPDIR 等非敏感基础变量，
# 其余（含 MYSQL_PASSWORD / AWS_* / DATABASE_URL 等一切未列入白名单
# 的变量）一律剔除——"默认拒绝"口径，新增凭证变量无需更新名单。
# 开关 CREDENTIAL_SCRUB_WHITELIST_ENABLE（D.4-3 起默认 true，安全默认"拒绝"口径）。
_WHITELIST_ENV_KEYS: frozenset[str] = frozenset(
    {
        # 路径 / 语言 / locale（非敏感）
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        # Python 运行时
        "PYTHONPATH",
        "PYTHONIOENCODING",
        "PYTHONUNBUFFERED",
        # 临时目录 / 系统
        "TMPDIR",
        "TEMP",
        "TMP",
        # SSL 证书（系统信任链，非凭证）
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
)


def whitelist_enabled() -> bool:
    """S4 白名单最小化环境开关（M11 D.4-3 修复：默认 true）。

    2026-09-30 审查 D.4-3 确认 S4 凭证白名单已实现但默认关（false），
    实测 MYSQL_PASSWORD / AWS_* / SSH_AUTH_SOCK 仍进子进程。
    现改为默认 true（安全默认"拒绝"口径），如需回退到历史黑名单行为
    可显式设 CREDENTIAL_SCRUB_WHITELIST_ENABLE=false。
    """
    return os.getenv("CREDENTIAL_SCRUB_WHITELIST_ENABLE", "true").lower() in ("true", "1", "on")


def build_minimal_env() -> dict[str, str]:
    """S4（M11，2026-09-29 审查 P0）：白名单最小化环境构建。

    仅保留 `_WHITELIST_ENV_KEYS` 中当前 os.environ 实际存在的键
    （缺失的键不注入空值，保持"有则保留、无则不造"口径）。
    其余全部剔除——包括所有未列入白名单的凭证变量
    （`MYSQL_PASSWORD` / `AWS_*` / `DATABASE_URL` 等），
    实现"默认拒绝"口径。

    与 `scrub_credentials`（黑名单）的对比：
    - 黑名单：新增凭证变量需手动加剔除模式（易遗漏）；
    - 白名单：仅保留已知安全变量，新增凭证自动被拒（安全默认）。

    调用方：三条执行链路（本地 / venv 沙箱 / Docker）在
    `whitelist_enabled()=True` 时用本函数替代 `scrub_credentials`。

    Returns:
        仅含白名单变量的环境字典（非空键值对）。
    """
    minimal: dict[str, str] = {}
    for key in _WHITELIST_ENV_KEYS:
        val = os.environ.get(key)
        if val is not None:
            minimal[key] = val
    return minimal


def provider_scrub_names() -> list[str]:
    """当前动态推导覆盖的 provider 中间变量全名清单（守卫/测试消费）。

    返回 PROVIDER_TEMPLATES 键对应的 `{PROVIDER}_API_KEY` /
    `{PROVIDER}_BASE_URL` 环境变量名列表；PROVIDER_TEMPLATES 不可用时
    返回历史固定名单（ALIYUN_BAILIAN / AGNES_DOMESTIC / AGNES_INTERNATIONAL
    / BIGMODEL / DEEPSEEK）。
    """
    if _PROVIDER_BASE_URLS:
        names: list[str] = []
        for provider in sorted(_PROVIDER_BASE_URLS):
            upper = provider.upper()
            names.append(f"{upper}_API_KEY")
            names.append(f"{upper}_BASE_URL")
        return names
    return [
        "ALIYUN_BAILIAN_API_KEY",
        "AGNES_DOMESTIC_API_KEY",
        "AGNES_INTERNATIONAL_API_KEY",
        "BIGMODEL_API_KEY",
        "DEEPSEEK_API_KEY",
    ]


def scrub_credentials(env: dict[str, str]) -> dict[str, str]:
    """剔除环境字典中的凭证类变量，返回副本（不修改入参）。

    匹配规则见模块 docstring：动态 `LLM_N_API_KEY` / `LLM_N_BASE_URL`
    + 通用 SDK 凭证固定名单 + PROVIDER_TEMPLATES 动态推导的
    provider 中间变量。

    Args:
        env: 源环境字典（通常为 os.environ.copy()）。

    Returns:
        剔除凭证后的新字典（原 env 不被修改，避免污染调用方环境）。
    """
    scrubbed: dict[str, str] = {}
    for key, value in env.items():
        if any(p.match(key) for p in _CREDENTIAL_PATTERNS):
            continue
        scrubbed[key] = value
    return scrubbed


def scrub_os_environ() -> dict[str, str]:
    """os.environ 脱敏，一步到位。

    S4（M11，2026-09-29 审查 P0）：白名单最小化环境开关
    （CREDENTIAL_SCRUB_WHITELIST_ENABLE，D.4-3 起**默认 true**——
    安全默认"拒绝"口径）。启用时直接走 `build_minimal_env()`（白名单
    "默认拒绝"），显式设为 false 时保持历史 `scrub_credentials` 黑名单
    口径（需要全量继承环境的场景）。

    供执行链路直接使用（替代此前的 `env = os.environ.copy()` + 手工 pop 列表）。

    Returns:
        已剔除凭证的环境字典副本。
    """
    if whitelist_enabled():
        return build_minimal_env()
    return scrub_credentials(os.environ.copy())
