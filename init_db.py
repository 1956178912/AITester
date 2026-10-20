"""
数据库初始化脚本：创建所需表结构。
手动运行此脚本以初始化 MySQL 数据库。

创建三张表：
    - tasks:       记录每个测试任务的基本信息（目标文件、函数名、状态）
    - test_runs:   记录每次测试执行的详细结果（覆盖率、输出文本、通过状态）
    - repair_history: 记录每次修复尝试的诊断与补丁（迭代次数关联）
test_runs.output 和 repair_history.patch 使用 MEDIUMTEXT，可存储完整的测试输出和代码补丁。
"""

from __future__ import annotations

import contextlib
import logging
import re

import pymysql

from config import (
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
)

# 模块级日志记录器，用于替代 print 输出
logger = logging.getLogger(__name__)


def init_database() -> None:
    """
    连接 MySQL 并创建 AITester 所需的数据表。
    若数据库不存在则先创建。

    资源清理契约（F07／2026-10-19 Z 轮审查修复）：conn / cursor 创建后立即
    进入 ``try/finally``，finally 分别 suppress 关闭 cursor 与 conn——覆盖
    数据库名校验、全部 CREATE/USE/建表 SQL 与 commit 的**整个使用区间**。
    历史实现只在 commit 外包 try/finally：连接成功后任一建库／建表 SQL 或
    库名校验抛异常时 cursor/conn 泄漏（MySQL 连接数有限，批量实验泄漏会
    耗尽连接池）。连接失败时 conn 保持 None，不重复关闭。

    Returns:
        None
    """
    # F07：两个资源先置 None——连接失败时 finally 不得对未创建的资源 close
    # （也不得用 locals() 猜当前进度）。
    conn = None
    cursor = None
    try:
        # 先连接默认数据库（无需指定 database）
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            charset="utf8mb4",
        )
        cursor = conn.cursor()

        # 创建数据库（若不存在），使用 utf8mb4 字符集支持 Unicode。
        # 库名来自 .env（运维者控制），白名单校验后再拼入 SQL，防止环境变量被恶意注入
        # 多语句（CREATE DATABASE IF NOT EXISTS `x``; DROP TABLE ...`）。
        if not re.fullmatch(r"[A-Za-z0-9_]+", MYSQL_DATABASE):
            raise ValueError(f"非法数据库名（仅允许字母/数字/下划线）: {MYSQL_DATABASE!r}")
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cursor.execute(f"USE `{MYSQL_DATABASE}`")

        # tasks 表：记录每个测试任务的基本信息
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                target_file VARCHAR(500) NOT NULL,
                target_function VARCHAR(200) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status ENUM('pending', 'running', 'completed', 'failed') DEFAULT 'pending',
                result TEXT DEFAULT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # test_runs 表：记录每次测试执行结果，含覆盖率数据
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_runs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                task_id INT NOT NULL,
                test_code MEDIUMTEXT NOT NULL,
                passed BOOLEAN NOT NULL,
                output MEDIUMTEXT DEFAULT NULL,
                coverage FLOAT DEFAULT NULL,
                iteration INT DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # repair_history 表：记录每次修复尝试的诊断与补丁
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS repair_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                task_id INT NOT NULL,
                diagnosis TEXT DEFAULT NULL,
                patch MEDIUMTEXT DEFAULT NULL,
                iteration INT DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # 提交事务
        conn.commit()
    finally:
        # F07：资源生命周期覆盖整个使用区间——SQL/校验异常、cursor 获取失败、
        # commit 异常都走这里；连接失败时 conn 为 None，不重复关闭。
        if cursor is not None:
            with contextlib.suppress(Exception):
                cursor.close()
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()
    # 初始化完成后记录日志（INFO 级别），替代原有 print 输出
    logger.info("数据库 `%s` 初始化完成，包含表：tasks, test_runs, repair_history", MYSQL_DATABASE)


if __name__ == "__main__":
    init_database()
