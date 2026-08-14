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

import logging

# 模块级日志记录器，用于替代 print 输出
logger = logging.getLogger(__name__)

import pymysql
from config import (
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DATABASE,
)


def init_database() -> None:
    """
    连接 MySQL 并创建 AITester 所需的数据表。
    若数据库不存在则先创建。
    
    Returns:
        None
    """
    # 先连接默认数据库（无需指定 database）
    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        charset="utf8mb4",
    )
    cursor = conn.cursor()

    # 创建数据库（若不存在），使用 utf8mb4 字符集支持 Unicode
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
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

    # 提交事务并关闭连接
    conn.commit()
    cursor.close()
    conn.close()
    # 初始化完成后记录日志（INFO 级别），替代原有 print 输出
    logger.info("数据库 `%s` 初始化完成，包含表：tasks, test_runs, repair_history", MYSQL_DATABASE)


if __name__ == "__main__":
    init_database()
