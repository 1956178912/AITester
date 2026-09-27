"""
P2 凭证剔除动态推导守卫（2026-09-29 批次）。

背景：`src/utils/credential_scrub.py` 的 provider 中间变量剔除模式改为从
`config_generator.PROVIDER_TEMPLATES` 动态推导（消除 LiteLLM CVE-2026-89032
式"静态枚举与动态接口漂移"根因）。本脚本做 CI 一致性守卫：

1. PROVIDER_TEMPLATES 的每个键（全名大写 + `_API_KEY` / `_BASE_URL`）
   必须被 `credential_scrub._CREDENTIAL_PATTERNS` 覆盖，否则 fail；
2. 反向（scrub 覆盖但模板无键）不 fail——通用 SDK 名单（OPENAI/ANTHROPIC）
   与 LLM_N_* 动态口径本就宽于 provider 模板，属预期超集；
3. COMMON_MODELS 引用的 provider 必须全部存在于 PROVIDER_TEMPLATES
   （新增 provider 的模型配置漂移检查）。

用法：
    python scripts/check_credential_scrub.py
退出码：0 = 全过；1 = 漂移（provider 新增未同步）或结构错误。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config.config_generator import COMMON_MODELS, PROVIDER_TEMPLATES  # noqa: E402
from src.utils import credential_scrub  # noqa: E402


def main() -> int:
    failures: list[str] = []

    # 1. PROVIDER_TEMPLATES 键必须被 scrub 模式覆盖
    for provider in PROVIDER_TEMPLATES:
        upper = provider.upper()
        for suffix in ("API_KEY", "BASE_URL"):
            env_name = f"{upper}_{suffix}"
            covered = any(p.match(env_name) for p in credential_scrub._CREDENTIAL_PATTERNS)
            if not covered:
                failures.append(
                    f"PROVIDER_TEMPLATES 键 '{provider}' 的 {env_name} 未被 credential_scrub 剔除模式覆盖"
                    "（新增 provider 未同步脱敏口径——凭证将进入被测代码子进程）"
                )

    # 2. COMMON_MODELS 引用的 provider 必须存在于模板
    for model in COMMON_MODELS:
        provider = model.get("provider", "")
        if provider not in PROVIDER_TEMPLATES:
            failures.append(
                f"COMMON_MODELS 的 '{model.get('name')}' 引用了未定义的 provider '{provider}'"
                "（应为 PROVIDER_TEMPLATES 的键——脱敏口径无推导来源）"
            )

    if failures:
        for f in failures:
            print(f"  [FAIL] {f}")
        print(f"凭证剔除动态推导守卫未通过（{len(failures)} 处漂移）")
        return 1
    print(
        f"凭证剔除动态推导守卫通过（{len(PROVIDER_TEMPLATES)} 个 provider 键"
        f" × API_KEY/BASE_URL 全部被 {len(credential_scrub._CREDENTIAL_PATTERNS)} 条剔除模式覆盖）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
