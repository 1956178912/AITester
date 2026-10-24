"""R4（2026-10-09 审查落地·S9）：llm_configs.json schema 校验测试。

覆盖口径：
- 合法模型目录 → 零违例；
- provider 未登记 / required_api_key 漂移 / base_url 非 http(s) /
  model_name 重复 / 缺字段 / 顶层非数组 / 条目非对象 → 各自违例。
"""

from __future__ import annotations

from src.config.config_generator import validate_llm_configs


def _entry(**overrides: str) -> dict[str, str]:
    base = {
        "model_name": "deepseek-flash",
        "provider": "deepseek",
        "provider_description": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "required_api_key": "DEEPSEEK_API_KEY",
    }
    base.update(overrides)
    return base


def test_valid_catalog_no_violations() -> None:
    assert validate_llm_configs([_entry()]) == []


def test_valid_catalog_two_entries_no_violations() -> None:
    """同 provider 两个不同 model_name 的条目也合法（schema 只锁唯一性与推导）。"""
    assert validate_llm_configs([_entry(), _entry(model_name="deepseek-flash-2")]) == []


def test_top_level_not_list() -> None:
    assert validate_llm_configs({"model_name": "x"}) == ["顶层结构必须为 JSON 数组（list）"]  # type: ignore[arg-type]


def test_entry_not_dict() -> None:
    assert any("必须是对象" in v for v in validate_llm_configs(["not-a-dict"]))  # type: ignore[list-item]


def test_unknown_provider_flagged() -> None:
    violations = validate_llm_configs([_entry(provider="mystery_provider")])
    assert any("provider 'mystery_provider' 未在 PROVIDER_TEMPLATES 登记" in v for v in violations)


def test_required_api_key_drift_flagged() -> None:
    violations = validate_llm_configs([_entry(required_api_key="WRONG_KEY")])
    assert any("required_api_key 'WRONG_KEY' 应为 'DEEPSEEK_API_KEY'" in v for v in violations)


def test_base_url_not_http_flagged() -> None:
    violations = validate_llm_configs([_entry(base_url="not-a-url")])
    assert any("必须以 http(s):// 开头" in v for v in violations)


def test_duplicate_model_name_flagged() -> None:
    violations = validate_llm_configs([_entry(), _entry()])
    assert any("重复" in v for v in violations)


def test_missing_field_flagged() -> None:
    entry = _entry()
    del entry["model_name"]
    violations = validate_llm_configs([entry])
    assert any("缺 model_name" in v for v in violations)


def test_empty_list_ok() -> None:
    assert validate_llm_configs([]) == []
