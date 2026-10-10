"""测试 config_generator 模块"""

import json
import os

from src.config.config_generator import (
    COMMON_MODELS,
    PROVIDER_TEMPLATES,
    generate_batch_config_script,
    generate_config_json,
    generate_env_template,
    print_model_catalog,
)


class TestProviderTemplates:
    """测试 PROVIDER_TEMPLATES 数据"""

    def test_aliyun_bailian_template(self):
        tmpl = PROVIDER_TEMPLATES["aliyun_bailian"]
        assert "base_url" in tmpl
        assert "description" in tmpl
        assert "dashscope" in tmpl["base_url"]

    def test_agnes_domestic_template(self):
        tmpl = PROVIDER_TEMPLATES["agnes_domestic"]
        assert "api.agnes-ai.cn" in tmpl["base_url"]

    def test_agnes_international_template(self):
        tmpl = PROVIDER_TEMPLATES["agnes_international"]
        assert "apihub.agnes-ai.com" in tmpl["base_url"]

    def test_bigmodel_template(self):
        tmpl = PROVIDER_TEMPLATES["bigmodel"]
        assert "bigmodel.cn" in tmpl["base_url"]

    def test_deepseek_template(self):
        tmpl = PROVIDER_TEMPLATES["deepseek"]
        assert "deepseek.com" in tmpl["base_url"]

    def test_get_unknown_provider_returns_empty(self):
        result = PROVIDER_TEMPLATES.get("nonexistent_provider", {})
        assert result == {}


class TestCommonModels:
    """测试 COMMON_MODELS 数据"""

    def test_common_models_not_empty(self):
        assert len(COMMON_MODELS) > 0

    def test_each_model_has_required_fields(self):
        for model in COMMON_MODELS:
            assert "name" in model
            assert "provider" in model

    def test_deepseek_v41_flash_is_the_only_model(self):
        """2026-10-09 配置要求：仅保留用户配置的 DeepSeek V4.1 Flash（官方 API
        现行 model 参数写法为 `deepseek-flash`），其余 qwen / glm / kimi /
        agnes / deepseek-chat 等条目已删除。"""
        names = [m["name"] for m in COMMON_MODELS]
        assert names == ["deepseek-flash"]
        for model in COMMON_MODELS:
            assert model["provider"] == "deepseek"


class TestGenerateEnvTemplate:
    """测试 generate_env_template 函数"""

    def test_generate_template_returns_string(self):
        result = generate_env_template()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_template_contains_api_key_placeholders(self):
        """模板变量名与 generate_batch_config 的 {PROVIDER}_API_KEY 推导同源（全名）。
        2026-10-09 起目录仅保留 DeepSeek provider（与 COMMON_MODELS 对齐），
        其余 provider 的占位符已删除。"""
        result = generate_env_template()
        assert "DEEPSEEK_API_KEY=your-deepseek-api-key-here" in result
        # 已删除 provider 的中间变量不再出现
        assert "ALIYUN_BAILIAN_API_KEY=your-aliyun-api-key-here" not in result
        assert "AGNES_DOMESTIC_API_KEY=your-agnes-api-key-here" not in result
        assert "AGNES_INTERNATIONAL_API_KEY=your-agnes-international-api-key-here" not in result
        assert "BIGMODEL_API_KEY=your-bigmodel-api-key-here" not in result
        # 旧短名变量已废弃，不再出现（与批处理脚本的推导名对齐）
        assert "ALIYUN_API_KEY=your-aliyun" not in result
        assert "AGNES_API_KEY=your" not in result

    def test_template_contains_model_examples(self):
        result = generate_env_template()
        assert "deepseek-flash" in result
        # 已删除 provider 的模型示例不再出现
        assert "qwen-max" not in result
        assert "agnes-3.0-flash" not in result
        assert "glm-4-flash" not in result

    def test_generate_template_writes_to_file(self, tmp_path):
        output = str(tmp_path / "test_template.env")
        result = generate_env_template(output)
        assert os.path.exists(output)
        with open(output, encoding="utf-8") as f:
            content = f.read()
        assert content == result
        assert "DEEPSEEK_API_KEY" in content


class TestGenerateConfigJson:
    """测试 generate_config_json 函数"""

    def test_generate_json_returns_string(self):
        result = generate_config_json()
        assert isinstance(result, str)

    def test_json_is_valid(self):
        result = generate_config_json()
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_json_structure(self):
        result = generate_config_json()
        data = json.loads(result)
        for item in data:
            assert "model_name" in item
            assert "provider" in item
            assert "base_url" in item

    def test_generate_json_writes_to_file(self, tmp_path):
        output = str(tmp_path / "configs.json")
        generate_config_json(output)
        assert os.path.exists(output)
        with open(output, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)


class TestPrintModelCatalog:
    """测试 print_model_catalog（不应抛出异常）"""

    def test_print_catalog_no_error(self, capsys):
        # U3（2026-10-05 系统性审查落地）：补断言——目录打印实际产出了模型清单
        print_model_catalog()
        captured = capsys.readouterr()
        assert "deepseek-flash" in captured.out

    def test_catalog_contains_models(self, capsys):
        print_model_catalog()
        captured = capsys.readouterr()
        assert "deepseek-flash" in captured.out


class TestGenerateBatchConfigScript:
    """测试 generate_batch_config_script 函数"""

    def test_returns_python_script(self):
        script = generate_batch_config_script()
        assert isinstance(script, str)
        assert "import argparse" in script
        assert "def main" in script

    def test_script_contains_cli_args(self):
        script = generate_batch_config_script()
        assert "--output" in script
        assert "--models" in script

    def test_script_writes_to_file(self, tmp_path):
        script = generate_batch_config_script()
        output = str(tmp_path / "gen_batch.py")
        with open(output, "w", encoding="utf-8") as f:
            f.write(script)
        assert os.path.exists(output)
        # 验证脚本可被 Python 解析
        with open(output, encoding="utf-8") as f:
            compile(f.read(), output, "exec")

    def test_script_empty_models_refuses_to_clobber(self, tmp_path):
        """数据丢失防护：模型列表为空时脚本应报错退出，不得用空文件覆盖现有 .env.local。"""
        import subprocess
        import sys

        script = generate_batch_config_script()
        script_path = tmp_path / "gen_batch.py"
        script_path.write_text(script, encoding="utf-8")

        env_file = tmp_path / ".env.local"
        env_file.write_text("LLM_1_API_KEY=keep-me\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(script_path), "--output", str(env_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        # 现有配置必须原样保留
        assert env_file.read_text(encoding="utf-8") == "LLM_1_API_KEY=keep-me\n"
        assert "模型列表为空" in result.stderr

    def test_script_env_var_name_matches_provider(self, tmp_path):
        """M20 回归：环境变量名按 provider 推导（{PROVIDER}_API_KEY），
        此前硬编码 ALIYUN_API_KEY 与 provider aliyun_bailian 的键名失配导致永远取不到。"""
        import subprocess
        import sys

        script = generate_batch_config_script()
        script_path = tmp_path / "gen_batch.py"
        script_path.write_text(script, encoding="utf-8")

        models_file = tmp_path / "models.json"
        models_file.write_text(
            json.dumps([{"name": "qwen-max", "provider": "aliyun_bailian", "base_url": "https://x/v1"}]),
            encoding="utf-8",
        )
        out_file = tmp_path / ".env.local"

        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
        env["ALIYUN_BAILIAN_API_KEY"] = "sk-real-key-123"
        env.pop("ALIYUN_API_KEY", None)

        result = subprocess.run(
            [sys.executable, str(script_path), "--output", str(out_file), "--models", str(models_file)],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, result.stderr
        assert "LLM_1_API_KEY=sk-real-key-123" in out_file.read_text(encoding="utf-8")
