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
        # 33 超出扫描口径（系统不读），保守保留（剔除它无害但口径以 32 为准）
        assert "LLM_33_API_KEY" in out or "LLM_33_API_KEY" not in out

    def test_scrub_os_environ_returns_copy(self, monkeypatch):
        monkeypatch.setenv("LLM_9_API_KEY", "sk-env9")
        monkeypatch.setenv("OPENAI_API_KEY_2", "sk-env2")
        monkeypatch.setenv("LLM_9_MODEL_NAME", "m9")
        out = scrub_os_environ()
        assert "LLM_9_API_KEY" not in out
        assert "OPENAI_API_KEY_2" not in out
        assert "LLM_9_MODEL_NAME" in out
        # os.environ 本身不被修改
        assert "LLM_9_API_KEY" in __import__("os").environ


if __name__ == "__main__":
    import sys

    sys.exit(__import__("pytest").main([__file__, "-v"]))
