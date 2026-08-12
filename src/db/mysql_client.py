"""
MySQL 数据库操作封装（单例模式）。
提供任务记录、测试运行记录、修复历史等 CRUD 操作。
"""

from __future__ import annotations

import pymysql
from contextlib import contextmanager
from typing import Any, Dict, Optional

from config import (
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DATABASE,
)


class MySQLClient:
    """
    MySQL 数据库单例客户端。

    属性:
        connection: pymysql 连接对象。
    """

    _instance: Optional["MySQLClient"] = None

    def __new__(cls) -> "MySQLClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # 使用 _initialized 标志确保单例仅在首次实例化时建立连接
        if not getattr(self, "_initialized", False):
            self.connection = pymysql.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
            )
            self._initialized = True

    @contextmanager
    def cursor(self):
        """
        提供事务安全的游标上下文管理器。
        自动提交成功事务，回滚失败事务。
        """
        cur = self.connection.cursor()
        try:
            yield cur
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        finally:
            cur.close()

    # ─── 任务记录 CRUD ───────────────────────────────────────────────────────

    def create_task(
        self,
        target_file: str,
        target_function: Optional[str] = None,
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
            cur.execute(
                "INSERT INTO tasks (target_file, target_function) VALUES (%s, %s)",
                (target_file, target_function),
            )
            return str(cur.lastrowid)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        查询任务记录。

        Args:
            task_id: 任务主键 ID。

        Returns:
            任务字典，未找到时返回 None。
        """
        with self.cursor() as cur:
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
        创建测试运行记录。

        Args:
            task_id: 关联任务 ID。
            test_code: 执行的测试代码。
            passed: 是否通过。
            output: 测试输出。
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
        创建修复历史记录。

        Args:
            task_id: 关联任务 ID。
            diagnosis: 根因诊断。
            patch: 修复代码。
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
