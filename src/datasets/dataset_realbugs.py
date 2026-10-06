"""W4（2026-10-05 审查落地）：真实缺陷基准加载器（QuixBugs / BugsInPy）。

背景（docs/design/real_benchmark_upgrade.md U13，原状态"设计稿（未实现）"）：
    主批次的正向证据 100% 来自项目自写合成模板（内部效度受限），真实基准
    仅 SWE-bench sqlfluff-20（单仓库、n=20）。本模块落地该设计稿的
    L1（QuixBugs）与 L2（BugsInPy）两级阶梯，验收标准（设计稿原文）：
    L1 "detection>0 且 resolved>0"。

设计约定：
    1. 两个加载器均为**本地目录解析**（与 Defects4J-Python 加载器同模式）：
       数据需用户自行获取（见各类 docstring 的获取方式），目录缺失时返回
       空数据集 + warning（优雅降级，不阻断 CI / 精简环境）。
    2. gold 材料对齐合成数据集口径：metadata["test_cases"]（gold 测试）与
       metadata["fixed"]（修复后代码全文）齐备时，experiments/_m1_metrics
       的 M1 诚实指标（detection/repair/false_fix）开箱可用（模块名按
       task_id 末段派生的既有单点规则自动工作）。
    3. task_id 末段 = 模块文件名（与合成集 P1-4 中性化口径一致：末段是
       可导入的普通标识符，不泄缺陷语义）。

引用（基准来源）：
    - QuixBugs: Lin et al., 2017, "QuixBugs: A Multi-Lingual Program Repair
      Benchmark Toy Dataset"（github.com/jkoppel/QuixBugs）。
    - BugsInPy: Widyasari et al., ICSE 2020, "BugsInPy: A Database of
      Existing Bugs in Python Programs to Enable Controlled Testing and
      Debugging Studies"（github.com/soarsmu/BugsInPy）。
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from typing import ClassVar

from src.datasets.dataset_loader import BaseDatasetLoader, BenchmarkTask

logger = logging.getLogger(__name__)


def _count_test_functions(code: str) -> int:
    """AST 精确计数 test_* 函数（语法损坏时回退 regex，与 D4J 加载器同口径）。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return len(re.findall(r"def test_\w+", code))
    return sum(isinstance(n, ast.FunctionDef) and n.name.startswith("test_") for n in ast.walk(tree))


def _first_top_level_function(code: str) -> str | None:
    """提取首个顶层函数名（作为 suggested_function 的保守默认值）。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    return None


class QuixBugsDataset(BaseDatasetLoader):
    """QuixBugs 真实缺陷基准加载器（real_benchmark_upgrade 阶梯 L1）。

    数据目录结构（相对 self.data_dir，默认 ~/.cache/aitester/quixbugs/）：
        python_programs/<prog>.py           # 缺陷版（必需）
        correct_python_programs/<prog>.py   # 修复版（gold 材料，可选但推荐）
        python_testcases/<prog>_test.py     # 官方测试（可选；也兼容 test_<prog>.py）

    获取方式：
        git clone https://github.com/jkoppel/QuixBugs <data_dir>
        （或环境变量 AITESTER_QUIXBUGS_DATA 指向已克隆目录）

    任务口径：
        - 每个程序一个任务，task_id = quixbugs__<prog>（末段=模块名）；
        - metadata["fixed"] = 修复版全文（M1 F2P 判据的 gold 侧）；
        - metadata["test_cases"] = 官方测试文件内容（M1 detection 的 gold
          测试）；官方测试是 unittest 风格，M1 子进程以 pytest 运行时可
          正常收集（pytest 兼容 unittest.TestCase）。
        - 缺修复版/测试的程序仍生成任务（降级为无 gold 材料任务，
          M1 指标记 None，不阻断主链路）。
    """

    DATASET_NAME = "quixbugs"

    _BUGGY_DIR: ClassVar[str] = "python_programs"
    _FIXED_DIRS: ClassVar[tuple[str, ...]] = ("correct_python_programs", "python_programs_correct")
    _TEST_DIRS: ClassVar[tuple[str, ...]] = ("python_testcases", "python_testcases_correct")

    def __init__(self, subset: str | None = None, data_dir: str | None = None) -> None:
        # data_dir 显式参数 > AITESTER_QUIXBUGS_DATA 环境变量 > 默认缓存目录
        # （与 SWE-rebench 经环境变量注入的口径一致）
        super().__init__(subset=subset, data_dir=data_dir or os.getenv("AITESTER_QUIXBUGS_DATA") or None)

    def _load_raw_data(self) -> None:
        self._tasks.clear()
        buggy_dir = os.path.join(self.data_dir, self._BUGGY_DIR)
        if not os.path.isdir(buggy_dir):
            logger.warning(
                "QuixBugs 数据未找到: %s\n请克隆 https://github.com/jkoppel/QuixBugs 或设 AITESTER_QUIXBUGS_DATA 指向已克隆目录",
                buggy_dir,
            )
            return

        fixed_dir = next(
            (os.path.join(self.data_dir, d) for d in self._FIXED_DIRS if os.path.isdir(os.path.join(self.data_dir, d))),
            None,
        )
        test_dir = next(
            (os.path.join(self.data_dir, d) for d in self._TEST_DIRS if os.path.isdir(os.path.join(self.data_dir, d))),
            None,
        )

        loaded = 0
        for fname in sorted(os.listdir(buggy_dir)):
            if not fname.endswith(".py") or fname.startswith(("_", "test")):
                continue
            prog = fname[:-3]
            if not prog.isidentifier():
                continue
            buggy_path = os.path.join(buggy_dir, fname)
            with open(buggy_path, encoding="utf-8") as f:
                buggy_code = f.read()
            if not buggy_code.strip():
                continue

            fixed_code = ""
            if fixed_dir:
                fixed_path = os.path.join(fixed_dir, fname)
                if os.path.exists(fixed_path):
                    with open(fixed_path, encoding="utf-8") as f:
                        fixed_code = f.read()

            test_code = ""
            if test_dir:
                for cand in (f"{prog}_test.py", f"test_{prog}.py", f"{prog}.py"):
                    test_path = os.path.join(test_dir, cand)
                    if os.path.exists(test_path):
                        with open(test_path, encoding="utf-8") as f:
                            test_code = f.read()
                        break

            total_tests = _count_test_functions(test_code)
            self._tasks.append(
                BenchmarkTask(
                    task_id=f"quixbugs__{prog}",
                    repo_name="quixbugs",
                    problem_statement=f"QuixBugs program {prog} contains a single-line seeded bug",
                    instance_code=buggy_code,
                    test_code=test_code,
                    expected_pass_count=total_tests,
                    total_test_count=total_tests,
                    metadata={
                        "source": "quixbugs",
                        "program": prog,
                        "test_cases": test_code,
                        "fixed": fixed_code,
                        "suggested_function": _first_top_level_function(buggy_code),
                        "is_cross_file": False,
                    },
                )
            )
            loaded += 1
        logger.info(
            "QuixBugs 加载完成：%d 个任务（gold 修复版目录：%s；官方测试目录：%s）",
            loaded,
            fixed_dir or "缺失",
            test_dir or "缺失",
        )


class BugsInPyDataset(BaseDatasetLoader):
    """BugsInPy 真实缺陷基准加载器（real_benchmark_upgrade 阶梯 L2）。

    数据格式（manifest JSONL，相对 self.data_dir，默认 ~/.cache/aitester/bugsinpy/）：
        文件名 bugs_in_py_manifest.jsonl（或 data_dir 直接指向 .jsonl 文件），
        每行一个缺陷任务：
        {
          "project": "pandas",            # 必需
          "bug_id": "2-00121",            # 必需（BugsInPy 编号）
          "file_path": "pandas/core/...",  # 缺陷文件相对路径（必需）
          "buggy_code": "def ...",         # 缺陷版文件全文（必需）
          "fixed_code": "def ...",         # 修复版文件全文（必需，gold 材料）
          "test_code": "def test_...",     # 官方测试（可选；BugsInPy 测试为
                                          # 项目级 pytest，此处为可导出的相关
                                          # 测试文件内容）
          "problem_statement": "..."       # 可选（issue 摘要）
        }

    获取方式：BugsInPy 官方仓库（github.com/soarsmu/BugsInPy）提供
    `bugsinpy-ckpt`/`bugsinpy-revert` 工作流检出缺陷/修复版本；建议用
    官方工作流导出上述 manifest（字段一一对应），经
    AITESTER_BUGSINPY_DATA 指向数据目录。W4 不内置抓取脚本（避免
    网络依赖与许可争议），manifest 生成口径见
    docs/design/real_benchmark_upgrade.md。

    任务口径：
        - task_id = bugsinpy__<project>_<bug_id>_<stem>（末段=模块名，中性、
          可导入标识符，≤50 字符与 _extract_gold_material 派生规则对齐）；
        - metadata["test_cases"] / metadata["fixed"] 齐备时 M1 诚实指标可用。
    """

    DATASET_NAME = "bugsinpy"
    _MANIFEST_NAMES: ClassVar[tuple[str, ...]] = ("bugs_in_py_manifest.jsonl", "manifest.jsonl")
    _MAX_STEM_LEN: ClassVar[int] = 30  # 末段长度预算（project/bug_id 前缀之外）

    def __init__(self, subset: str | None = None, data_dir: str | None = None) -> None:
        # data_dir 显式参数 > AITESTER_BUGSINPY_DATA 环境变量 > 默认缓存目录
        super().__init__(subset=subset, data_dir=data_dir or os.getenv("AITESTER_BUGSINPY_DATA") or None)

    def _manifest_path(self) -> str | None:
        if self.data_dir.endswith(".jsonl") and os.path.exists(self.data_dir):
            return self.data_dir
        for name in self._MANIFEST_NAMES:
            candidate = os.path.join(self.data_dir, name)
            if os.path.exists(candidate):
                return candidate
        return None

    def _load_raw_data(self) -> None:
        self._tasks.clear()
        manifest = self._manifest_path()
        if manifest is None:
            logger.warning(
                "BugsInPy manifest 未找到: %s（期待 %s 之一，或直接指向 .jsonl 文件；"
                "设 AITESTER_BUGSINPY_DATA 指向数据目录）",
                self.data_dir,
                " / ".join(self._MANIFEST_NAMES),
            )
            return

        loaded = skipped = 0
        with open(manifest, encoding="utf-8") as f:
            for line_no, raw in enumerate(f, 1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning("BugsInPy manifest 第 %d 行解析失败（跳过）: %s", line_no, e)
                    skipped += 1
                    continue
                buggy_code = str(row.get("buggy_code") or "")
                fixed_code = str(row.get("fixed_code") or "")
                if not buggy_code.strip():
                    skipped += 1
                    continue

                project = str(row.get("project") or "unknown")
                bug_id = str(row.get("bug_id") or line_no)
                stem = os.path.splitext(os.path.basename(str(row.get("file_path") or f"bug{line_no}")))[0]
                stem = re.sub(r"\W", "_", stem)[: self._MAX_STEM_LEN].strip("_") or f"bug{line_no}"

                test_code = str(row.get("test_code") or "")
                total_tests = _count_test_functions(test_code)
                self._tasks.append(
                    BenchmarkTask(
                        task_id=f"bugsinpy__{project}_{bug_id}_{stem}",
                        repo_name=f"bugsinpy/{project}",
                        problem_statement=str(row.get("problem_statement") or f"BugsInPy {project} bug {bug_id}"),
                        instance_code=buggy_code,
                        test_code=test_code,
                        expected_pass_count=total_tests,
                        total_test_count=total_tests,
                        metadata={
                            "source": "bugs_in_py",
                            "project": project,
                            "bug_id": bug_id,
                            "file_path": row.get("file_path"),
                            "test_cases": test_code,
                            "fixed": fixed_code,
                            "suggested_function": _first_top_level_function(buggy_code),
                            "is_cross_file": False,
                        },
                    )
                )
                loaded += 1
        logger.info("BugsInPy 加载完成：%d 个任务（跳过 %d 行无效记录）", loaded, skipped)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    for cls in (QuixBugsDataset, BugsInPyDataset):
        ds = cls()
        logger.info("%s: %d tasks", cls.DATASET_NAME, ds.size)
