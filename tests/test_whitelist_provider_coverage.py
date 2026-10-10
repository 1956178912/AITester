"""C-08 收尾守卫（2026-10-09）：内置 pip 白名单必须覆盖 LLM provider 相关包。

背景：2026-10-09 审查修订 C-08 把 `PIP_PACKAGE_WHITELIST_ENABLE` 默认翻转为
开（Slopsquatting 已确认为现实攻击 [待核验]）。默认开后，若
`requirements.lock` 中 LLM provider / 编排框架相关包（openai / zai-sdk /
langchain 族等）不在内置 `_PIP_PACKAGE_WHITELIST` 内，正常依赖会被误拒，
沙箱执行退化为"缺依赖"。本守卫测试读取 requirements.lock，把 LLM provider
相关包（显式清单，防清单漂移）逐一断言被内置白名单覆盖——新增 provider
依赖时同步扩充白名单与本测试清单。
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCK_FILE = PROJECT_ROOT / "requirements.lock"

# requirements.lock 中 LLM provider / 编排框架 / 测试生成工具链相关包（显式
# 清单，与 pyproject.toml [project] dependencies + [rag] extra 对齐；
# 新增 provider 依赖须同步扩充本清单与 _PIP_PACKAGE_WHITELIST）。
_LLM_PROVIDER_PACKAGES: tuple[str, ...] = (
    # 直接 import 依赖（pyproject.toml 核心依赖面）
    "openai",
    "zai-sdk",
    "langchain",
    "langchain-openai",
    "langgraph",
    "click",
    "python-dotenv",
    "requests",
    # [rag] extra（可选，沙箱内可能被 LLM 推断引入）
    "chromadb",
    # LLM 生成测试/执行链路合理引入的常见工具包
    "tiktoken",
    "tenacity",
)


def _lock_package_names() -> set[str]:
    """解析 requirements.lock，返回全部包名（小写，PEP 503 口径）。"""
    names: set[str] = set()
    pattern = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==")
    for line in LOCK_FILE.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line.strip())
        if m:
            names.add(m.group(1).lower())
    return names


def _whitelisted() -> set[str]:
    from src.tools.dependency import _PIP_PACKAGE_WHITELIST

    return set(_PIP_PACKAGE_WHITELIST)


def test_lock_file_exists() -> None:
    assert LOCK_FILE.exists(), f"requirements.lock 不存在：{LOCK_FILE}"


def test_provider_packages_present_in_lock() -> None:
    """清单中每个包确实出现在 requirements.lock（防清单自身漂移）。"""
    lock_names = _lock_package_names()
    missing = [pkg for pkg in _LLM_PROVIDER_PACKAGES if pkg.lower() not in lock_names]
    assert not missing, f"清单包 {missing} 不在 requirements.lock（包名漂移或 lock 未更新）"


def test_whitelist_covers_provider_packages() -> None:
    """内置白名单必须覆盖全部 LLM provider 相关包（C-08 默认开口径）。"""
    allowed = _whitelisted()
    uncovered = [pkg for pkg in _LLM_PROVIDER_PACKAGES if pkg.lower() not in allowed]
    assert not uncovered, (
        f"LLM provider 包未被内置白名单覆盖（默认开后会被误拒）：{uncovered}；"
        "请在 src/tools/dependency.py 的 _PIP_PACKAGE_WHITELIST 中补充"
    )


def test_default_suggest_filters_provider_package() -> None:
    """默认开（未设置环境变量）时，provider 包经 suggest_package_names 放行、
    幻觉包名仍被拒——端到端验证 C-08 默认口径。"""
    import os

    from src.tools.dependency import suggest_package_names

    saved = {k: os.environ.get(k) for k in ("PIP_PACKAGE_WHITELIST_ENABLE", "PIP_PACKAGE_WHITELIST")}
    os.environ.pop("PIP_PACKAGE_WHITELIST_ENABLE", None)
    os.environ.pop("PIP_PACKAGE_WHITELIST", None)
    try:
        out = suggest_package_names({"openai", "definitely_hallucinated_pkg"})
    finally:
        os.environ.clear()
        os.environ.update({k: v for k, v in saved.items() if v is not None})
    assert "openai" in out
    assert "definitely_hallucinated_pkg" not in out
