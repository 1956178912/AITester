"""
Defects4J-Python 风格数据集加载器。

拆分自 dataset_loader.py（结构优化轮次）：Defects4J-Python 专用解析逻辑独立成模块，
dataset_loader.py 保留数据模型 / 抽象基类 / SWE-bench 加载器 / 工厂函数，
并经 re-export 维持 `from src.datasets.dataset_loader import Defects4JPYDataset` 的旧导入路径。

Defects4J 是 Java 生态中最著名的缺陷基准，Defects4J-Python 是其 Python 移植版本，
提供真实项目中的历史缺陷修复配对数据。本加载器从本地目录解析，若无数据则返回
空列表并提示用户。
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import ClassVar

from src.datasets.dataset_loader import BaseDatasetLoader, BenchmarkTask

logger = logging.getLogger(__name__)


class Defects4JPYDataset(BaseDatasetLoader):
    """
    Defects4J-Python 风格数据集加载器。

    数据目录结构（相对 self.data_dir）:
        projects/<project_name>/<version>/
            buggy/      # 有缺陷的代码
            fixed/      # 修复后的代码
            tests/      # 测试套件
            info.json   # 元数据
    """

    DATASET_NAME = "defects4j_python"

    KNOWN_PROJECTS: ClassVar[list[str]] = [
        "requests",
        "pytest",
        "httpie",
        "matplotlib",
        "numpy",
        "pandas",
        "scikit-learn",
    ]

    def _load_project_version(self, version_path: str, project_name: str, version_dir: str) -> BenchmarkTask | None:
        """
        加载单个项目版本的缺陷数据。

        Args:
            version_path: 版本目录路径。
            project_name: 项目名称。
            version_dir: 版本目录名。

        Returns:
            BenchmarkTask 对象，失败时返回 None。
        """
        info_path = os.path.join(version_path, "info.json")
        if not os.path.exists(info_path):
            return None

        try:
            with open(info_path, encoding="utf-8") as f:
                info = json.load(f)
        except json.JSONDecodeError as e:
            # 2026-09-26 全面审查：损坏的 info.json 原静默跳过（无感知），
            # 现记 warning 便于定位数据问题
            logger.warning("Defects4J-Python info.json 解析失败（跳过该版本）: %s: %s", info_path, e)
            return None

        # 加载有缺陷的代码。目录列举一律 sorted：os.listdir 顺序依赖文件系统，
        # 未排序会让两次加载的拼接顺序不同 → instance_code 内容与下游 RAG md5
        # 指纹不可复现（此前 tests 目录已 sorted 而 buggy 目录漏了，属不对称遗漏）。
        # 用 list 累积 + join 替代字符串 +=，避免 CPython 3.12+ 下 += 的 O(n²) 拷贝。
        buggy_dir = os.path.join(version_path, "buggy")
        buggy_parts: list[str] = []
        if os.path.isdir(buggy_dir):
            for fname in sorted(os.listdir(buggy_dir)):
                if fname.endswith(".py"):
                    with open(os.path.join(buggy_dir, fname), encoding="utf-8") as ff:
                        buggy_parts.append(ff.read() + "\n")

        # 加载测试代码（同样 sorted + list 累积）
        tests_dir = os.path.join(version_path, "tests")
        test_parts: list[str] = []
        if os.path.isdir(tests_dir):
            for fname in sorted(os.listdir(tests_dir)):
                if fname.startswith("test_") and fname.endswith(".py"):
                    with open(os.path.join(tests_dir, fname), encoding="utf-8") as ff:
                        test_parts.append(ff.read() + "\n")

        buggy_code = "".join(buggy_parts)
        test_code = "".join(test_parts)

        # 统计测试函数
        test_funcs = re.findall(r"def test_\w+", test_code)
        total_tests = len(test_funcs)
        expected_pass = info.get("expected_pass", total_tests)

        task_id = f"{project_name}__{version_dir}"
        return BenchmarkTask(
            task_id=task_id,
            repo_name=project_name,
            problem_statement=info.get("description", f"Bug in {project_name}"),
            instance_code=buggy_code,
            test_code=test_code,
            expected_pass_count=expected_pass,
            total_test_count=total_tests,
            metadata={
                "project": project_name,
                "version": version_dir,
                "bug_type": info.get("bug_type", "unknown"),
                "source": "defects4j_python",
            },
        )

    def _load_raw_data(self) -> None:
        """
        从本地目录加载 Defects4J-Python 数据。

        目录结构:
            defects4j_python/projects/<project_name>/<version>/
                buggy/      # 有缺陷的代码
                fixed/      # 修复后的代码
                tests/      # 测试套件
                info.json   # 元数据
        """
        # 清空任务列表，避免重复加载时数据累积
        self._tasks.clear()

        projects_dir = os.path.join(self.data_dir, "projects")

        if not os.path.exists(projects_dir):
            logger.warning(
                "Defects4J-Python 数据未找到: %s\n请从 https://github.com/rustcodex/defects4jpython 下载数据",
                projects_dir,
            )
            return

        loaded = 0
        # sorted：项目/版本两级列举也需确定性，否则任务列表顺序跨文件系统漂移
        for project_name in sorted(os.listdir(projects_dir)):
            project_dir = os.path.join(projects_dir, project_name)
            if not os.path.isdir(project_dir):
                continue
            for version_dir in sorted(os.listdir(project_dir)):
                version_path = os.path.join(project_dir, version_dir)
                task = self._load_project_version(version_path, project_name, version_dir)
                if task is not None:
                    self._tasks.append(task)
                    loaded += 1

        logger.info("Defects4J-Python 加载完成：%d 个任务", loaded)
