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
"""

from __future__ import annotations

import os
import re

# 凭证类环境变量剔除模式（按前缀匹配，N 为数字）
# LLM_N_API_KEY / LLM_N_BASE_URL：LLM 配置（config.py _load_llm_configs 扫描口径 1-32）
# LLM_N_MODEL_NAME 非凭证（模型名非敏感），不剔除。
_CREDENTIAL_PATTERNS = (
    re.compile(r"^LLM_\d+_API_KEY$"),
    re.compile(r"^LLM_\d+_BASE_URL$"),
    # 通用 SDK 凭证（固定名单，与历史本地执行路径口径一致）
    re.compile(r"^(OPENAI_API_KEY|OPENAI_BASE_URL|ANTHROPIC_API_KEY|API_KEY|LLM_API_KEY|LLM_CONFIG_API_KEY)$"),
)


def scrub_credentials(env: dict[str, str]) -> dict[str, str]:
    """剔除环境字典中的凭证类变量，返回副本（不修改入参）。

    匹配规则见模块 docstring：动态 `LLM_N_API_KEY` / `LLM_N_BASE_URL`
    + 通用 SDK 凭证固定名单。

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
    """os.environ.copy() 后再剔除凭证，一步到位。

    供执行链路直接使用（替代此前的 `env = os.environ.copy()` + 手工 pop 列表）。

    Returns:
        已剔除凭证的环境字典副本。
    """
    return scrub_credentials(os.environ.copy())
