"""测试 config_manager 模块"""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.config import config_manager
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


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    """将 config_manager.ENV_FILE 指向临时目录，避免测试触碰真实 .env.local。"""
    path = tmp_path / ".env.local"
    monkeypatch.setattr(config_manager, "ENV_FILE", path)
    return path


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
        configs = get_all_llm_configs()
        # 结构校验（环境无关）：模型名列表应与已配置 LLM 的 model_name 一一对应
        assert names == [cfg.model_name for cfg in configs]
        # 厂商名校验面向开发者真实配置（qwen/deepseek/agnes/glm 等）；
        # CI 使用 mock 配置（LLM_1_MODEL_NAME=test-model），不含任何真实厂商关键词，
        # 此时该校验不适用——跳过以保持测试在不同环境下行为一致
        vendor_keywords = ("qwen", "deepseek", "agnes", "glm")
        if not any(k in n for n in names for k in vendor_keywords):
            pytest.skip("未检测到真实厂商模型配置（CI/mock 环境），跳过厂商名校验")
        assert any(k in n for n in names for k in vendor_keywords)


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
    """测试 add_llm_config（真实临时文件 + 隔离 load_dotenv/refresh）"""

    @pytest.fixture(autouse=True)
    def _isolate_env_side_effects(self, monkeypatch):
        """隔离 load_dotenv 与 refresh_llm_configs，避免测试污染进程环境变量与全局 LLM_CONFIGS。"""
        monkeypatch.setattr(config_manager, "load_dotenv", lambda *a, **k: None)
        monkeypatch.setattr(config_manager, "refresh_llm_configs", lambda: None)

    def test_add_valid_config(self, env_file):
        result = add_llm_config(
            api_key="test-key",
            base_url="https://test.example.com",
            model_name="test-model",
            index=99,
        )
        assert result is True
        content = env_file.read_text(encoding="utf-8")
        assert "LLM_99_API_KEY=test-key" in content
        assert "LLM_99_BASE_URL=https://test.example.com" in content
        assert "LLM_99_MODEL_NAME=test-model" in content

    def test_add_duplicate_model_returns_false(self, env_file):
        env_file.write_text("LLM_1_MODEL_NAME=test-model\n", encoding="utf-8")
        result = add_llm_config(
            api_key="test-key",
            base_url="https://test.example.com",
            model_name="test-model",
            index=1,
        )
        assert result is False

    def test_add_duplicate_model_at_other_index_returns_false(self, env_file):
        """同一模型已存在于其他编号时也应判定为重复（避免跨编号重复配置）。"""
        env_file.write_text("LLM_1_MODEL_NAME=test-model\n", encoding="utf-8")
        result = add_llm_config(
            api_key="other-key",
            base_url="https://other.example.com",
            model_name="test-model",
            index=7,
        )
        assert result is False

    def test_add_config_auto_index(self, env_file):
        """无已有配置时，自动编号为 1。"""
        result = add_llm_config(api_key="k", base_url="https://ex.com", model_name="m")
        assert result is True
        assert "LLM_1_MODEL_NAME=m" in env_file.read_text(encoding="utf-8")

    def test_add_config_auto_index_with_holes(self, env_file):
        """编号空洞（LLM_1、LLM_3）时自动编号取最大值 +1（=4），不与已占编号冲突。"""
        env_file.write_text(
            "LLM_1_API_KEY=k1\nLLM_1_MODEL_NAME=m1\nLLM_3_API_KEY=k3\nLLM_3_MODEL_NAME=m3\n",
            encoding="utf-8",
        )
        result = add_llm_config(api_key="k4", base_url="https://ex.com", model_name="m4")
        assert result is True
        assert "LLM_4_MODEL_NAME=m4" in env_file.read_text(encoding="utf-8")

    def test_env_file_points_to_project_root(self):
        """回归锁：ENV_FILE 必须指向项目根目录的 .env.local（而非 src/config/ 下）。"""
        assert config_manager.ENV_FILE == Path("config.py").resolve().parent / ".env.local"


class TestRemoveLLMConfig:
    """测试 remove_llm_config（真实临时文件 + 隔离 load_dotenv/refresh）"""

    @pytest.fixture(autouse=True)
    def _isolate_env_side_effects(self, monkeypatch):
        """隔离 load_dotenv 与 refresh_llm_configs，避免测试污染进程环境变量与全局 LLM_CONFIGS。"""
        monkeypatch.setattr(config_manager, "load_dotenv", lambda *a, **k: None)
        monkeypatch.setattr(config_manager, "refresh_llm_configs", lambda: None)

    def test_remove_existing_model(self, env_file):
        env_file.write_text(
            "# 模型 1: test-model\nLLM_1_API_KEY=key1\nLLM_1_BASE_URL=https://ex.com\nLLM_1_MODEL_NAME=test-model\n\n",
            encoding="utf-8",
        )
        result = remove_llm_config("test-model")
        assert result is True
        content = env_file.read_text(encoding="utf-8")
        assert "LLM_1_MODEL_NAME=test-model" not in content

    def test_remove_existing_model_entire_block(self, env_file):
        """回归：整块移除，注释行/API_KEY/BASE_URL 不得残留（旧实现只删 MODEL_NAME 行）。"""
        env_file.write_text(
            "# 模型 1: test-model\nLLM_1_API_KEY=key1\nLLM_1_BASE_URL=https://ex.com\nLLM_1_MODEL_NAME=test-model\n\n",
            encoding="utf-8",
        )
        result = remove_llm_config("test-model")
        assert result is True
        content = env_file.read_text(encoding="utf-8")
        assert "LLM_1_API_KEY" not in content, "API_KEY 行必须随块移除（密钥不得残留）"
        assert "LLM_1_BASE_URL" not in content, "BASE_URL 行必须随块移除"
        assert "模型 1" not in content, "块注释行必须随块移除"
        # 该编号应不再被占用：自动分配下一个编号应回到 1
        assert add_llm_config(api_key="k2", base_url="https://ex.com", model_name="m2") is True
        assert "LLM_1_MODEL_NAME=m2" in env_file.read_text(encoding="utf-8")

    def test_remove_keeps_other_models(self, env_file):
        """移除其中一个模型时，其他模型的配置块必须原样保留。"""
        env_file.write_text(
            "# 模型 1: keep-me\nLLM_1_API_KEY=k1\nLLM_1_BASE_URL=https://a.com\nLLM_1_MODEL_NAME=keep-me\n"
            "\n# 模型 2: drop-me\nLLM_2_API_KEY=k2\nLLM_2_BASE_URL=https://b.com\nLLM_2_MODEL_NAME=drop-me\n",
            encoding="utf-8",
        )
        result = remove_llm_config("drop-me")
        assert result is True
        content = env_file.read_text(encoding="utf-8")
        assert "LLM_1_API_KEY=k1" in content
        assert "LLM_1_MODEL_NAME=keep-me" in content
        assert "LLM_2_API_KEY" not in content
        assert "LLM_2_MODEL_NAME" not in content
        assert "模型 2" not in content

    def test_remove_model_at_multiple_indices(self, env_file):
        """同一模型名出现在多个编号下（手工编辑场景）时，所有编号的整块都被移除。"""
        env_file.write_text(
            "LLM_1_API_KEY=k1\nLLM_1_MODEL_NAME=twin\n"
            "LLM_3_API_KEY=k3\nLLM_3_BASE_URL=https://c.com\nLLM_3_MODEL_NAME=twin\n",
            encoding="utf-8",
        )
        result = remove_llm_config("twin")
        assert result is True
        content = env_file.read_text(encoding="utf-8")
        assert "LLM_1_API_KEY" not in content
        assert "LLM_3_API_KEY" not in content
        assert "LLM_3_MODEL_NAME" not in content

    def test_remove_does_not_match_partial_names(self, env_file):
        """移除 short-model 时不得误删 short-model-x 的配置块（行尾精确匹配）。"""
        env_file.write_text(
            "LLM_1_API_KEY=k1\nLLM_1_MODEL_NAME=short-model\n"
            "LLM_2_API_KEY=k2\nLLM_2_MODEL_NAME=short-model-x\n",
            encoding="utf-8",
        )
        result = remove_llm_config("short-model")
        assert result is True
        content = env_file.read_text(encoding="utf-8")
        assert "LLM_1_MODEL_NAME" not in content
        assert "LLM_2_MODEL_NAME=short-model-x" in content

    def test_remove_nonexistent_model(self, env_file):
        env_file.write_text("LLM_1_MODEL_NAME=other-model\n", encoding="utf-8")
        result = remove_llm_config("nonexistent")
        assert result is False

    def test_remove_file_not_exists(self, env_file):
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
