"""测试 config_manager 模块"""

from unittest.mock import mock_open, patch

from src.config.config_manager import (
    add_llm_config,
    batch_add_models,
    count_llm_configs,
    get_all_llm_configs,
    get_config_by_model,
    get_model_names,
    print_config_report,
    remove_llm_config,
    validate_configs,
)


class TestGetAllLLMConfigs:
    """测试 get_all_llm_configs"""

    def test_returns_list(self):
        configs = get_all_llm_configs()
        assert isinstance(configs, list)

    def test_returns_non_empty(self):
        configs = get_all_llm_configs()
        assert len(configs) > 0

    def test_each_config_has_required_fields(self):
        configs = get_all_llm_configs()
        for cfg in configs:
            assert hasattr(cfg, "api_key")
            assert hasattr(cfg, "base_url")
            assert hasattr(cfg, "model_name")


class TestCountLLMConfigs:
    """测试 count_llm_configs"""

    def test_count_positive(self):
        count = count_llm_configs()
        assert count > 0
        assert isinstance(count, int)


class TestGetModelNames:
    """测试 get_model_names"""

    def test_returns_list_of_strings(self):
        names = get_model_names()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)

    def test_names_not_empty(self):
        names = get_model_names()
        assert len(names) > 0

    def test_contains_expected_models(self):
        names = get_model_names()
        # 至少包含配置中的一些模型
        assert any("qwen" in n or "deepseek" in n or "agnes" in n or "glm" in n for n in names)


class TestGetConfigByModel:
    """测试 get_config_by_model"""

    def test_find_existing_model(self):
        names = get_model_names()
        if names:
            cfg = get_config_by_model(names[0])
            assert cfg is not None
            assert cfg.model_name == names[0]

    def test_find_nonexistent_model(self):
        cfg = get_config_by_model("nonexistent_model_xyz")
        assert cfg is None

    def test_find_model_by_partial_name_returns_none(self):
        # 精确匹配，模糊搜索不应返回
        cfg = get_config_by_model("partial")
        assert cfg is None


class TestAddLLMConfig:
    """测试 add_llm_config（使用 mock 文件系统）"""

    def test_add_valid_config(self, tmp_path):
        with patch("src.config.config_manager.os.path.exists", return_value=False):
            with patch("src.config.config_manager.open", mock_open()):
                with patch("src.config.config_manager.load_dotenv"):
                    result = add_llm_config(
                        api_key="test-key",
                        base_url="https://test.example.com",
                        model_name="test-model",
                        index=99,
                    )
        assert result is True

    def test_add_duplicate_model_returns_false(self, tmp_path):
        env_content = "LLM_1_MODEL_NAME=test-model\n"
        with patch("src.config.config_manager.os.path.exists", return_value=True):
            with patch("src.config.config_manager.open", mock_open(read_data=env_content)):
                with patch("src.config.config_manager.load_dotenv"):
                    result = add_llm_config(
                        api_key="test-key",
                        base_url="https://test.example.com",
                        model_name="test-model",
                        index=1,
                    )
        assert result is False

    def test_add_config_auto_index(self, tmp_path):
        with patch("src.config.config_manager.os.path.exists", return_value=False):
            with patch("src.config.config_manager.open", mock_open()):
                with patch("src.config.config_manager.load_dotenv"):
                    result = add_llm_config(
                        api_key="k",
                        base_url="https://ex.com",
                        model_name="m",
                    )
        assert result is True


class TestRemoveLLMConfig:
    """测试 remove_llm_config（使用 mock 文件系统）"""

    def test_remove_existing_model(self, tmp_path):
        env_content = (
            "# 模型 1: test-model\nLLM_1_API_KEY=key1\nLLM_1_BASE_URL=https://ex.com\nLLM_1_MODEL_NAME=test-model\n\n"
        )
        with patch("src.config.config_manager.os.path.exists", return_value=True):
            with patch("src.config.config_manager.open", mock_open(read_data=env_content)):
                with patch("src.config.config_manager.load_dotenv"):
                    result = remove_llm_config("test-model")
        assert result is True

    def test_remove_nonexistent_model(self, tmp_path):
        env_content = "LLM_1_MODEL_NAME=other-model\n"
        with patch("src.config.config_manager.os.path.exists", return_value=True):
            with patch("src.config.config_manager.open", mock_open(read_data=env_content)):
                with patch("src.config.config_manager.load_dotenv"):
                    result = remove_llm_config("nonexistent")
        assert result is False

    def test_remove_file_not_exists(self):
        with patch("src.config.config_manager.os.path.exists", return_value=False):
            result = remove_llm_config("any-model")
        assert result is False


class TestPrintConfigReport:
    """测试 print_config_report（不应抛出异常）"""

    def test_print_report_no_error(self, capsys):
        print_config_report()
        captured = capsys.readouterr()
        assert "总模型数" in captured.out


class TestValidateConfigs:
    """测试 validate_configs"""

    def test_validate_returns_dict(self):
        result = validate_configs()
        assert isinstance(result, dict)
        assert "total_configs" in result
        assert "valid_configs" in result
        assert "invalid_configs" in result
        assert "issues" in result

    def test_validate_counts_match(self):
        result = validate_configs()
        assert result["valid_configs"] + result["invalid_configs"] == result["total_configs"]

    def test_validate_no_issues_with_valid_config(self):
        result = validate_configs()
        # 当前配置应是有效的
        assert result["invalid_configs"] == 0
        assert len(result["issues"]) == 0


class TestBatchAddModels:
    """测试 batch_add_models（使用 mock）"""

    def test_batch_add_multiple(self):
        models = [
            {"api_key": "k1", "base_url": "https://a.com", "model_name": "m1"},
            {"api_key": "k2", "base_url": "https://b.com", "model_name": "m2"},
        ]
        with patch("src.config.config_manager.add_llm_config", return_value=True) as mock_add:
            results = batch_add_models(models)
        assert len(results) == 2
        assert all(r is True for r in results)
        assert mock_add.call_count == 2

    def test_batch_add_partial_failure(self):
        models = [
            {"api_key": "k1", "base_url": "https://a.com", "model_name": "m1"},
            {"api_key": "k2", "base_url": "https://b.com", "model_name": "m2"},
        ]
        with patch("src.config.config_manager.add_llm_config", side_effect=[True, False]) as mock_add:
            results = batch_add_models(models)
        assert results == [True, False]
        assert mock_add.call_count == 2
