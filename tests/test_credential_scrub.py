"""credential_scrub 单元测试（2026-09-26 全面审查：P0 凭证剔除模式补强回归）。

回归背景：.env 实测存在 OPENAI_API_KEY_2/3、OPENAI_BASE_URL_2/3 等多端点
编号命名，旧模式锚定全名 `^OPENAI_API_KEY$` 匹配不到编号变体——凭证原样
进被测代码子进程（执行向量 + 泄露面）。本测试锁定：
- LLM_N_API_KEY / LLM_N_BASE_URL 动态编号剔除（覆盖 1-32 扫描口径）；
- 编号变体（OPENAI_API_KEY_2、OPENAI_BASE_URL_3）剔除；
- provider 中间变量（ALIYUN_BAILIAN / AGNES_DOMESTIC 等，config_generator
  PROVIDER_TEMPLATES 联动命名）剔除；
- 非凭证变量（LLM_N_MODEL_NAME、PYTHONPATH）保留；
- 入参不可变（返回副本，不修改源 dict）。
"""

from src.utils.credential_scrub import scrub_credentials, scrub_os_environ

# 模拟 .env / .env.local 注入后的环境：含编号 LLM 配置 + 多端点 OPENAI 变体
# + provider 中间变量（值均为伪密钥，测试不落真实凭证）
_ENV_SAMPLE = {
    "LLM_1_API_KEY": "sk-llx1fakefakefakefakefake1",
    "LLM_1_BASE_URL": "https://example.invalid/v1",
    "LLM_1_MODEL_NAME": "m1",
    "LLM_2_API_KEY": "sk-llx2fakefakefakefakefake2",
    "LLM_2_BASE_URL": "https://example.invalid/v2",
    "LLM_2_MODEL_NAME": "m2",
    "OPENAI_API_KEY": "sk-openai",
    "OPENAI_BASE_URL": "https://api.openai.example/v1",
    "OPENAI_API_KEY_2": "sk-openai-2",
    "OPENAI_BASE_URL_2": "https://api2.openai.example/v1",
    "OPENAI_API_KEY_3": "sk-openai-3",
    "OPENAI_BASE_URL_3": "https://api3.openai.example/v1",
    "ALIYUN_BAILIAN_API_KEY": "sk-bailian",
    "AGNES_DOMESTIC_API_KEY": "sk-agnes",
    "BIGMODEL_API_KEY": "sk-bigmodel",
    "DEEPSEEK_API_KEY": "sk-deepseek",
    "ANTHROPIC_API_KEY": "sk-anthropic",
    "LLM_API_KEY": "sk-llm",
    "LLM_CONFIG_API_KEY": "sk-llmconf",
    "API_KEY": "sk-plain",
    # 非凭证：保留
    "LLM_3_MODEL_NAME": "m3",
    "PYTHONPATH": "/a:/b",
    "PATH": "/usr/bin",
    "LANG": "zh_CN.UTF-8",
    "HOME": "/home/u",
}

# 应被剔除的键（编号变体 + provider 变量全部命中）
_SCRUBBED_KEYS = {
    "LLM_1_API_KEY",
    "LLM_1_BASE_URL",
    "LLM_2_API_KEY",
    "LLM_2_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_API_KEY_2",
    "OPENAI_BASE_URL_2",
    "OPENAI_API_KEY_3",
    "OPENAI_BASE_URL_3",
    "ALIYUN_BAILIAN_API_KEY",
    "AGNES_DOMESTIC_API_KEY",
    "BIGMODEL_API_KEY",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
    "LLM_API_KEY",
    "LLM_CONFIG_API_KEY",
    "API_KEY",
}

# 应保留的键（非凭证）
_PRESERVED_KEYS = {"LLM_3_MODEL_NAME", "PYTHONPATH", "PATH", "LANG", "HOME"}


class TestScrubCredentials:
    def test_numbered_llm_credentials_scrubbed(self):
        out = scrub_credentials(_ENV_SAMPLE)
        for key in _SCRUBBED_KEYS:
            assert key not in out, f"凭证 {key} 未被剔除"

    def test_non_credential_vars_preserved(self):
        out = scrub_credentials(_ENV_SAMPLE)
        for key in _PRESERVED_KEYS:
            assert key in out, f"非凭证变量 {key} 被误剔除"
        assert out["PYTHONPATH"] == "/a:/b"

    def test_input_not_mutated(self):
        snapshot = dict(_ENV_SAMPLE)
        scrub_credentials(_ENV_SAMPLE)
        assert snapshot == _ENV_SAMPLE, "入参 dict 被修改"

    def test_high_index_llm_keys_covered(self):
        """LLM 编号上限 32（config.py _LLM_MAX_SCAN_INDEX 口径）：边界编号剔除。"""
        env = {"LLM_32_API_KEY": "sk-x32", "LLM_32_BASE_URL": "https://x", "LLM_33_API_KEY": "sk-x33"}
        out = scrub_credentials(env)
        assert "LLM_32_API_KEY" not in out
        assert "LLM_32_BASE_URL" not in out
        # 33 超出扫描口径（系统不读），模式按 LLM_\d+_ 前缀通配也剔除
        # （防御口径：剔除它无害，保留才可能泄漏）——此前断言写成
        # `in out or not in out` 恒真（2026-10-02 审查修复），
        # 锁定实际防御行为。
        assert "LLM_33_API_KEY" not in out

    def test_scrub_os_environ_returns_copy(self, monkeypatch):
        monkeypatch.setenv("LLM_9_API_KEY", "sk-env9")
        monkeypatch.setenv("OPENAI_API_KEY_2", "sk-env2")
        monkeypatch.setenv("LLM_9_MODEL_NAME", "m9")
        out = scrub_os_environ()
        assert "LLM_9_API_KEY" not in out
        assert "OPENAI_API_KEY_2" not in out
        # D.4-3（2026-09-30）：S4 白名单默认启用后，LLM_N_MODEL_NAME 不在
        # _WHITELIST_ENV_KEYS 中，故不再保留（安全默认"拒绝"口径）。
        # 如需验证黑名单行为，显式设 CREDENTIAL_SCRUB_WHITELIST_ENABLE=false。
        # 此前断言写成 `not in out or in out` 恒真（2026-10-02 审查修复），
        # 锁定白名单默认路径的实际行为。
        assert "LLM_9_MODEL_NAME" not in out
        # 白名单路径（默认）：非白名单变量一律剔除
        # os.environ 本身不被修改
        assert "LLM_9_API_KEY" in __import__("os").environ


if __name__ == "__main__":
    import sys

    sys.exit(__import__("pytest").main([__file__, "-v"]))


class TestWhitelistMinimalEnv:
    """S4 白名单最小化环境（build_minimal_env / whitelist_enabled）回归。

    2026-10-02 审查：白名单实现此前无独立单测——scrub_os_environ 仅在
    "默认白名单"下被顺带覆盖，build_minimal_env 的键白名单语义与
    whitelist_enabled 开关翻转路径零覆盖。本类补齐。
    """

    def test_whitelist_enabled_default_true(self):
        """D.4-3 起默认 true（安全默认"拒绝"口径）。"""
        import os as _os

        from src.utils.credential_scrub import whitelist_enabled

        saved = _os.environ.pop("CREDENTIAL_SCRUB_WHITELIST_ENABLE", None)
        try:
            assert whitelist_enabled() is True
        finally:
            if saved is not None:
                _os.environ["CREDENTIAL_SCRUB_WHITELIST_ENABLE"] = saved

    def test_minimal_env_keeps_whitelisted_only(self, monkeypatch):
        """白名单键保留，其余（含凭证）一律剔除。"""
        from src.utils.credential_scrub import _WHITELIST_ENV_KEYS, build_minimal_env

        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setenv("HOME", "/home/u")
        monkeypatch.setenv("LANG", "en_US.UTF-8")
        monkeypatch.setenv("MYSQL_PASSWORD", "SuperSecret123")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "abc")
        monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agent.sock")
        monkeypatch.setenv("SOME_RANDOM_VAR", "x")
        out = build_minimal_env()
        for key in ("PATH", "HOME", "LANG"):
            assert key in out, f"白名单键 {key} 被误剔除"
        for key in ("MYSQL_PASSWORD", "AWS_SECRET_ACCESS_KEY", "SSH_AUTH_SOCK", "SOME_RANDOM_VAR"):
            assert key not in out, f"非白名单键 {key} 泄漏进子进程 env"
        # 输出键集必须是白名单的子集（默认拒绝口径）
        assert set(out).issubset(set(_WHITELIST_ENV_KEYS))

    def test_scrub_os_environ_blacklist_path_when_disabled(self, monkeypatch):
        """显式关闭白名单 → 回退历史黑名单口径（PYTHONPATH 等保留）。"""
        monkeypatch.setenv("CREDENTIAL_SCRUB_WHITELIST_ENABLE", "false")
        monkeypatch.setenv("LLM_7_API_KEY", "sk-env7")
        monkeypatch.setenv("PYTHONPATH", "/a:/b")
        out = scrub_os_environ()
        assert "LLM_7_API_KEY" not in out, "黑名单口径下凭证仍应剔除"
        assert out.get("PYTHONPATH") == "/a:/b", "黑名单口径下非凭证变量应保留"


class TestProviderScrubNames:
    """provider_scrub_names 动态/回退双分支（P2 动态推导口径，2026-10-08 补齐）。"""

    def test_dynamic_names_from_templates(self):
        from src.utils.credential_scrub import provider_scrub_names

        names = provider_scrub_names()
        # 动态推导：PROVIDER_TEMPLATES 每个 provider 产生 {UPPER}_API_KEY / _BASE_URL
        assert "DEEPSEEK_API_KEY" in names
        assert "DEEPSEEK_BASE_URL" in names
        assert "ALIYUN_BAILIAN_API_KEY" in names
        # 每个 provider 恰好两条（API_KEY + BASE_URL）
        assert len(names) % 2 == 0

    def test_fallback_names_when_templates_unavailable(self):
        from unittest.mock import patch

        import src.utils.credential_scrub as cs

        with patch.object(cs, "_PROVIDER_BASE_URLS", {}):
            names = cs.provider_scrub_names()
        # 回退历史固定名单（ALIYUN_BAILIAN / AGNES_DOMESTIC / BIGMODEL / DEEPSEEK）
        assert "ALIYUN_BAILIAN_API_KEY" in names
        assert "BIGMODEL_API_KEY" in names
        assert "DEEPSEEK_API_KEY" in names
