"""
MySQL 客户端单元测试（src/db/mysql_client.py）。

PooledDB 连接池全程 mock，不依赖真实 MySQL 实例，覆盖：
- 连接池单例语义（_instance / _pool 复用）
- cursor 上下文管理器的 commit / rollback 行为
- tasks / test_runs / repair_history 三张表的 CRUD 方法（SQL 与参数化查询）

背景：本模块此前无任何测试，且其依赖 DBUtils 曾在 requirements 中漏声明
（2026-09-09 已补齐 DBUtils==3.1.2，本套件同时验证补齐后的可导入性）。
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import mysql_client as mysql_client_module
from src.db.mysql_client import MySQLClient


@pytest.fixture(autouse=True)
def _isolated_mysql_client():
    """每个测试前后隔离单例状态，避免类级 _pool/_instance 跨测试残留。"""
    MySQLClient._instance = None
    MySQLClient._pool = None
    yield
    MySQLClient._instance = None
    MySQLClient._pool = None


def _make_client(pool: MagicMock | None = None) -> MySQLClient:
    """以 mock 连接池构造 MySQLClient（跳过 PooledDB 真实构建）。"""
    MySQLClient._pool = pool or MagicMock(name="PooledDB")
    return MySQLClient()


def _make_client_and_conn():
    """构造带 mock 连接池/连接/游标的客户端，返回 (client, pool, conn, cur)。"""
    pool = MagicMock(name="PooledDB")
    conn = pool.connection.return_value
    cur = conn.cursor.return_value
    client = _make_client(pool)
    return client, pool, conn, cur


class TestPoolSingleton:
    """连接池单例语义"""

    def test_instance_is_singleton(self):
        """同一进程内 MySQLClient() 返回同一实例"""
        client_a = _make_client()
        client_b = MySQLClient()
        assert client_a is client_b

    def test_existing_pool_reused_without_rebuild(self):
        """已存在 _pool 时，再次构造不重建连接池（__init__ 提前返回）"""
        pool = MagicMock(name="PooledDB")
        client = _make_client(pool)
        assert MySQLClient.get_pool() is pool
        # 再次构造：复用既有 _pool，返回同一实例
        client2 = MySQLClient()
        assert client2 is client
        assert MySQLClient.get_pool() is pool

    def test_pool_construction_uses_mysql_config(self):
        """_pool 为空时按 config 中的 MySQL 参数构建 PooledDB（参数化传递）"""
        with (
            patch.object(mysql_client_module, "PooledDB") as mock_pooled_class,
            patch.object(mysql_client_module, "MYSQL_HOST", "db.example.com"),
            patch.object(mysql_client_module, "MYSQL_PORT", 3307),
            patch.object(mysql_client_module, "MYSQL_USER", "app_user"),
            patch.object(mysql_client_module, "MYSQL_PASSWORD", "secret"),
            patch.object(mysql_client_module, "MYSQL_DATABASE", "aitester_db"),
        ):
            client = MySQLClient()
        # 池实例是 PooledDB(...) 的返回值，构造参数来自 config 全局
        assert MySQLClient.get_pool() is mock_pooled_class.return_value
        assert client is not None
        kwargs = mock_pooled_class.call_args.kwargs
        assert kwargs["host"] == "db.example.com"
        assert kwargs["port"] == 3307
        assert kwargs["user"] == "app_user"
        assert kwargs["password"] == "secret"
        assert kwargs["database"] == "aitester_db"


class TestCursorContextManager:
    """cursor() 上下文管理器的提交/回滚语义"""

    def test_cursor_commits_on_success(self):
        """正常退出时提交事务并归还连接"""
        client, pool, conn, cur = _make_client_and_conn()
        with client.cursor() as c:
            assert c is cur
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()
        cur.close.assert_called_once()
        conn.close.assert_called_once()  # 归还到连接池

    def test_cursor_rolls_back_on_error(self):
        """块内异常时回滚事务，异常继续向外传播"""
        client, pool, conn, cur = _make_client_and_conn()
        cur.execute.side_effect = RuntimeError("db down")
        with pytest.raises(RuntimeError, match="db down"):
            with client.cursor():
                cur.execute("SELECT 1")
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
        # 即使回滚失败路径，连接与游标仍被关闭（资源不泄漏）
        cur.close.assert_called_once()
        conn.close.assert_called_once()


class TestTaskCrud:
    """tasks 表 CRUD（参数化查询防注入）"""

    def test_create_task_returns_lastrowid_as_str(self):
        client, pool, conn, cur = _make_client_and_conn()
        cur.lastrowid = 42
        task_id = client.create_task("examples/calculator.py", "divide")
        assert task_id == "42"
        # SQL 使用 %s 占位符，参数独立传递（防 SQL 注入）
        sql, params = cur.execute.call_args.args
        assert "INSERT INTO tasks" in sql
        assert params == ("examples/calculator.py", "divide")

    def test_create_task_without_function(self):
        client, pool, conn, cur = _make_client_and_conn()
        cur.lastrowid = 7
        task_id = client.create_task("examples/calculator.py")
        assert task_id == "7"
        sql, params = cur.execute.call_args.args
        assert params == ("examples/calculator.py", None)

    def test_get_task_returns_row(self):
        client, pool, conn, cur = _make_client_and_conn()
        cur.fetchone.return_value = {"id": 1, "target_file": "a.py"}
        row = client.get_task("1")
        assert row == {"id": 1, "target_file": "a.py"}
        sql, params = cur.execute.call_args.args
        assert "SELECT * FROM tasks WHERE id = %s" in sql
        assert params == ("1",)

    def test_get_task_not_found_returns_none(self):
        client, pool, conn, cur = _make_client_and_conn()
        cur.fetchone.return_value = None
        assert client.get_task("999") is None


class TestTestRunCrud:
    """test_runs 表 CRUD"""

    def test_create_test_run_inserts_all_fields(self):
        client, pool, conn, cur = _make_client_and_conn()
        cur.lastrowid = 5
        run_id = client.create_test_run(
            task_id="1",
            test_code="def test_x(): pass",
            passed=False,
            output="FAILED ...",
            coverage=73.5,
            iteration=2,
        )
        assert run_id == "5"
        sql, params = cur.execute.call_args.args
        assert "INSERT INTO test_runs" in sql
        assert params == ("1", "def test_x(): pass", False, "FAILED ...", 73.5, 2)


class TestRepairHistoryCrud:
    """repair_history 表 CRUD"""

    def test_create_repair_history_inserts_all_fields(self):
        client, pool, conn, cur = _make_client_and_conn()
        cur.lastrowid = 9
        record_id = client.create_repair_history(
            task_id="1",
            diagnosis="除零未处理",
            patch="def safe_div(a, b): ...",
            iteration=1,
        )
        assert record_id == "9"
        sql, params = cur.execute.call_args.args
        assert "INSERT INTO repair_history" in sql
        assert params == ("1", "除零未处理", "def safe_div(a, b): ...", 1)
