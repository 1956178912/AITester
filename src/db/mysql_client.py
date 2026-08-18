"""
MySQL 数据库操作封装（单例 + 连接池）。
提供任务记录、测试运行记录、修复历史等 CRUD 操作。
output 字段使用 MEDIUMTEXT 类型，不再截断。
连接池使用 DBUtils.PooledDB 提升并发能力（~10 QPS → 100+ QPS）。
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

import pymysql
from dbutils.pooled_db import PooledDB

from config import (
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
)

logger = logging.getLogger(__name__)

# ─── 连接池配置常量 ───────────────────────────────────────────────────────────
# 初始化时创建的预留空闲连接数
_POOL_MIN_CACHED = 5
# 连接池中允许的最大空闲连接数
_POOL_MAX_CACHED = 10
# 连接池允许的最大连接总数（含正在使用的）
_POOL_MAX_CONNECTIONS = 20
# 从池获取连接的等待超时秒数（连接池满时阻塞等待）
_POOL_CONNECTION_TIMEOUT = 30
# 连接空闲超过此秒数后被回收（0 表示不回收）
_POOL_IDLE_TIMEOUT = 600


class MySQLClient:
    """
    MySQL 数据库单例客户端（带连接池）。

    使用 DBUtils.PooledDB 管理连接池，支持高并发读写。
    所有连接通过 pool.connection() 按需获取，使用完毕归还至池中。

    类属性:
        _pool: PooledDB 连接池单例。
    """

    _instance: MySQLClient | None = None
    _pool: PooledDB | None = None

    def __new__(cls) -> MySQLClient:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # 避免重复初始化连接池
        if MySQLClient._pool is not None:
            return
        MySQLClient._pool = PooledDB(
            creator=pymysql,
            maxconnections=_POOL_MAX_CONNECTIONS,
            mincached=_POOL_MIN_CACHED,
            maxcached=_POOL_MAX_CACHED,
            blocking=True,
            timeout=_POOL_CONNECTION_TIMEOUT,
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        logger.info(
            "MySQL 连接池已创建: max=%d, min_cached=%d, max_cached=%d",
            _POOL_MAX_CONNECTIONS,
            _POOL_MIN_CACHED,
            _POOL_MAX_CACHED,
        )

    @classmethod
    def get_pool(cls) -> PooledDB:
        """获取全局连接池单例。"""
        return cls._pool

    @contextmanager
    def cursor(self):
        """
        提供事务安全的游标上下文管理器。
        从连接池获取连接，自动提交成功事务，回滚失败事务，
        并在 finally 中归还连接到池。
        """
        conn = self._pool.connection()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()  # 归还连接到池

    # ─── 任务记录 CRUD ───────────────────────────────────────────────────────

    def create_task(
        self,
        target_file: str,
        target_function: str | None = None,
    ) -> str:
        """
        创建新任务记录。

        Args:
            target_file: 被测代码文件路径。
            target_function: 被测函数名。

        Returns:
            新创建的任务 UUID。
        """
        with self.cursor() as cur:
            # 使用参数化查询（%s 占位符）防止 SQL 注入
            # lastrowid 返回最后一次 INSERT 的自增主键
            cur.execute(
                "INSERT INTO tasks (target_file, target_function) VALUES (%s, %s)",
                (target_file, target_function),
            )
            return str(cur.lastrowid)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """
        查询任务记录。

        Args:
            task_id: 任务主键 ID。

        Returns:
            任务字典，未找到时返回 None。
        """
        with self.cursor() as cur:
            # fetchone() 返回第一行结果（字典格式），未找到时返回 None
            cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
            return cur.fetchone()

    # ─── 测试运行记录 CRUD ──────────────────────────────────────────────────

    def create_test_run(
        self,
        task_id: str,
        test_code: str,
        passed: bool,
        output: str,
        coverage: float,
        iteration: int = 1,
    ) -> str:
        """
        创建测试运行记录。output 字段使用 MEDIUMTEXT，不截断。

        Args:
            task_id: 关联任务 ID。
            test_code: 执行的测试代码。
            passed: 是否通过。
            output: 测试输出（完整文本，不截断）。
            coverage: 覆盖率。
            iteration: 迭代次数。

        Returns:
            新记录的主键 ID。
        """
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO test_runs
                    (task_id, test_code, passed, output, coverage, iteration)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (task_id, test_code, passed, output, coverage, iteration),
            )
            return str(cur.lastrowid)

    # ─── 修复历史 CRUD ───────────────────────────────────────────────────────

    def create_repair_history(
        self,
        task_id: str,
        diagnosis: str,
        patch: str,
        iteration: int,
    ) -> str:
        """
        创建修复历史记录。patch 字段使用 MEDIUMTEXT，不截断。

        Args:
            task_id: 关联任务 ID。
            diagnosis: 根因诊断。
            patch: 修复代码（完整文本，不截断）。
            iteration: 迭代次数。

        Returns:
            新记录的主键 ID。
        """
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO repair_history
                    (task_id, diagnosis, patch, iteration)
                VALUES (%s, %s, %s, %s)
                """,
                (task_id, diagnosis, patch, iteration),
            )
            return str(cur.lastrowid)
