"""
单元测试：测试 MySQLClient（单例、cursor 事务）和 config.py（默认值、LLM 配置）。

覆盖范围：
    - MySQLClient 单例模式
    - cursor 上下文管理器的事务提交/回滚（mock pymysql）
    - config.py：默认值验证、LLM_CONFIGS 为空列表、load_env_local
"""

import os
from unittest.mock import MagicMock, patch

import pytest


# ─── TestMySQLClient：数据库客户端 ─────────────────────────────────────────────
class TestMySQLClient:
    """测试 MySQLClient 单例模式和事务行为。"""

    @patch("src.db.mysql_client.pymysql.connect")
    def test_singleton_pattern(self, mock_connect):
        """多次初始化应返回同一实例。"""
        mock_connect.return_value = MagicMock()
        from src.db.mysql_client import MySQLClient

        # 清除已有实例以确保测试独立
        MySQLClient._instance = None
        client1 = MySQLClient()
        client2 = MySQLClient()
        assert client1 is client2

    @patch("src.db.mysql_client.pymysql.connect")
    def test_cursor_commits_on_success(self, mock_connect):
        """cursor 上下文管理器在正常执行时应提交事务。"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        from src.db.mysql_client import MySQLClient

        MySQLClient._instance = None
        client = MySQLClient()
        with client.cursor() as cur:
            cur.execute("SELECT 1")
        mock_conn.commit.assert_called_once()

    @patch("src.db.mysql_client.pymysql.connect")
    def test_cursor_rolls_back_on_error(self, mock_connect):
        """cursor 上下文管理器在异常时应回滚事务。"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        from src.db.mysql_client import MySQLClient

        MySQLClient._instance = None
        client = MySQLClient()
        with pytest.raises(ValueError):
            with client.cursor() as cur:
                cur.execute("SELECT 1")
                raise ValueError("模拟错误")
        mock_conn.rollback.assert_called_once()

    @patch("src.db.mysql_client.pymysql.connect")
    def test_create_task_returns_string_id(self, mock_connect):
        """create_task 应返回任务 ID 字符串。"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 42
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        from src.db.mysql_client import MySQLClient

        MySQLClient._instance = None
        client = MySQLClient()
        task_id = client.create_task("examples/calculator.py", "divide")
        assert task_id == "42"
        mock_cursor.execute.assert_called_once()

    @patch("src.db.mysql_client.pymysql.connect")
    def test_get_task_returns_none_when_not_found(self, mock_connect):
        """查询不存在任务时应返回 None。"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        from src.db.mysql_client import MySQLClient

        MySQLClient._instance = None
        client = MySQLClient()
        result = client.get_task("999")
        assert result is None


# ─── TestConfig：配置验证 ──────────────────────────────────────────────────────
class TestConfig:
    """测试 config.py 的默认值和加载逻辑。"""

    def test_temperature_default(self):
        """TEMPERATURE 默认值应为 0.2。"""
        from config import TEMPERATURE

        assert TEMPERATURE == 0.2

    def test_max_iterations_default(self):
        """MAX_ITERATIONS 默认值应为 3。"""
        from config import MAX_ITERATIONS

        assert MAX_ITERATIONS == 3

    def test_coverage_threshold_default(self):
        """COVERAGE_THRESHOLD 默认值应为 80.0。"""
        from config import COVERAGE_THRESHOLD

        assert COVERAGE_THRESHOLD == 80.0

    def test_execution_timeout_default(self):
        """EXECUTION_TIMEOUT 默认值应为 30。"""
        from config import EXECUTION_TIMEOUT

        assert EXECUTION_TIMEOUT == 30

    def test_enable_planner_default(self):
        """ENABLE_PLANNER 默认值应为 True。"""
        from config import ENABLE_PLANNER

        assert ENABLE_PLANNER is True

    def test_enable_debugger_default(self):
        """ENABLE_DEBUGGER 默认值应为 True。"""
        from config import ENABLE_DEBUGGER

        assert ENABLE_DEBUGGER is True

    def test_enable_rag_default(self):
        """ENABLE_RAG 默认值应为 False。"""
        from config import ENABLE_RAG

        assert ENABLE_RAG is False

    def test_llm_configs_empty_without_env(self):
        """直接测试 _load_llm_configs：无 LLM_* 环境变量时返回空列表。"""
        import config as config_module

        # 移除所有 LLM_* 环境变量（保留非 LLM 变量）
        keys_to_remove = [k for k in os.environ if k.startswith("LLM_")]
        original_values = {}
        for k in keys_to_remove:
            original_values[k] = os.environ.pop(k)
        try:
            configs = config_module._load_llm_configs()
            assert configs == []
        finally:
            # 恢复环境变量
            for k, v in original_values.items():
                os.environ[k] = v

    def test_mysql_defaults(self):
        """MySQL 默认连接参数正确。"""
        from config import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PORT

        assert MYSQL_HOST == "localhost"
        assert MYSQL_PORT == 3306
        assert MYSQL_DATABASE == "aitester"

    def test_docker_defaults(self):
        """Docker 相关配置默认值正确。"""
        from config import DOCKER_ENABLED, DOCKER_IMAGE

        assert DOCKER_ENABLED is False
        assert DOCKER_IMAGE == "python:3.11-slim"
