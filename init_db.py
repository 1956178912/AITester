"""
数据库初始化脚本：创建所需表结构。
手动运行此脚本以初始化 MySQL 数据库。
"""

from __future__ import annotations

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

    # 创建数据库（若不存在）
    cursor.execute("CREATE DATABASE IF NOT EXISTS %s CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci", (MYSQL_DATABASE,))
    cursor.execute("USE %s", (MYSQL_DATABASE,))

    # tasks 表：记录每个测试任务
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

    # test_runs 表：记录每次测试执行结果
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

    # repair_history 表：记录每次修复尝试
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

    conn.commit()
    cursor.close()
    conn.close()
    print(f"数据库 `{MYSQL_DATABASE}` 初始化完成，包含表：tasks, test_runs, repair_history")


if __name__ == "__main__":
    init_database()
