"""
Defects4J-Python 加载器边界场景补充测试（在 test_defects4j_smoke.py 之外）。

覆盖 src/datasets/dataset_defects4j.py 中现有测试未触达的分支：
- _load_project_version: 缺 info.json 返回 None
- buggy/tests 目录缺失时 instance_code/test_code 为空串
- expected_pass 缺失时回退到 total_test_count
- fixed 目录存在但不被读取（仅文档结构，加载器只读 buggy+tests+info.json）
"""

from __future__ import annotations

import json

import pytest


def _make_project(
    root: pytest.TempPathFactory,
    project: str,
    version: str,
    *,
    buggy: list[str] | None = None,
    tests: list[str] | None = None,
    fixed: bool = False,
    info: dict | None = None,
    no_info: bool = False,
) -> str:
    """在 root/projects/<project>/<version>/ 下构造版本目录，返回 data_dir 字符串。"""
    from pathlib import Path

    vdir = Path(str(root)) / "projects" / project / version
    if buggy is not None:
        (vdir / "buggy").mkdir(parents=True)
        for i, code in enumerate(buggy):
            (vdir / "buggy" / f"m{i}.py").write_text(code, encoding="utf-8")
    if tests is not None:
        (vdir / "tests").mkdir(parents=True)
        for i, code in enumerate(tests):
            (vdir / "tests" / f"test_{i}.py").write_text(code, encoding="utf-8")
    if fixed:
        (vdir / "fixed").mkdir(parents=True)
        (vdir / "fixed" / "fixed.py").write_text("# fixed\n", encoding="utf-8")
    if not no_info:
        if info is None:
            info = {"description": f"{project} {version} bug"}
        (vdir / "info.json").write_text(json.dumps(info), encoding="utf-8")
    return str(Path(str(root)))


class TestDefects4JPYEdges:
    def test_missing_info_json_returns_no_task(self, tmp_path: pytest.TempPathFactory) -> None:
        """缺 info.json：_load_project_version 返回 None，任务列表为空。"""
        from src.datasets.dataset_loader import load_dataset

        _make_project(
            tmp_path,
            "noinfo",
            "1.0",
            buggy=["def f():\n    return 1\n"],
            tests=["def test_f():\n    assert f() == 1\n"],
            no_info=True,
        )
        loader = load_dataset("defects4j_python", data_dir=str(tmp_path))
        assert list(loader) == []

    def test_missing_buggy_and_tests_dirs_yield_empty_codes(self, tmp_path: pytest.TempPathFactory) -> None:
        """buggy/tests 目录缺失：instance_code/test_code 为空串，total_test_count=0，
        且 expected_pass 缺失时回退到 total_test_count（=0）。"""
        from src.datasets.dataset_loader import load_dataset

        _make_project(tmp_path, "empty", "1.0", buggy=[], tests=[])
        loader = load_dataset("defects4j_python", data_dir=str(tmp_path))
        tasks = list(loader)
        assert len(tasks) == 1
        task = tasks[0]
        assert task.instance_code == ""
        assert task.test_code == ""
        assert task.total_test_count == 0
        assert task.expected_pass_count == 0

    def test_expected_pass_falls_back_to_total_test_count(self, tmp_path: pytest.TempPathFactory) -> None:
        """info.json 无 expected_pass 字段：回退到统计到的 test 函数数。"""
        from src.datasets.dataset_loader import load_dataset

        _make_project(
            tmp_path,
            "fallback",
            "2.0",
            buggy=["def g():\n    return 2\n"],
            tests=[
                "def test_a():\n    assert True\n",
                "def test_b():\n    assert True\n",
            ],
            info={"description": "no expected_pass here"},
        )
        loader = load_dataset("defects4j_python", data_dir=str(tmp_path))
        task = next(iter(loader))
        assert task.total_test_count == 2
        assert task.expected_pass_count == 2  # 回退值

    def test_fixed_dir_ignored_by_loader(self, tmp_path: pytest.TempPathFactory) -> None:
        """fixed/ 目录仅文档结构，加载器不读取：任务不含 fixed 代码。"""
        from src.datasets.dataset_loader import load_dataset

        _make_project(
            tmp_path,
            "withfixed",
            "3.0",
            buggy=["def h():\n    return 3\n"],
            tests=["def test_h():\n    assert h() == 3\n"],
            fixed=True,
        )
        loader = load_dataset("defects4j_python", data_dir=str(tmp_path))
        task = next(iter(loader))
        assert "def h()" in task.instance_code
        assert "fixed" not in task.instance_code.lower()

    def test_non_py_files_in_buggy_ignored(self, tmp_path: pytest.TempPathFactory) -> None:
        """buggy/ 下非 .py 文件（如 .md 说明）不被拼入 instance_code。"""
        from src.datasets.dataset_loader import load_dataset

        data_dir = _make_project(
            tmp_path,
            "mixed",
            "1.0",
            buggy=["def k():\n    return 4\n", "README.md"],
            tests=["def test_k():\n    assert k() == 4\n"],
        )
        # 把 README.md 真正写成非 py 文件（_make_project 按文件名写 m0.py/m1.py，
        # 这里手动补一个 README.md 验证过滤逻辑）
        from pathlib import Path

        (Path(data_dir) / "projects" / "mixed" / "1.0" / "buggy" / "README.md").write_text("# doc\n", encoding="utf-8")
        loader = load_dataset("defects4j_python", data_dir=data_dir)
        task = next(iter(loader))
        assert "def k()" in task.instance_code
        assert "doc" not in task.instance_code

    def test_test_literal_in_string_not_miscounted(self, tmp_path: pytest.TempPathFactory) -> None:
        """2026-09-29 P2-5 修复：字符串字面量里的 def test_xxx 不被误计入 total_tests。

        历史实现用 re.findall(r"def test_\\w+")，测试代码中出现的字符串常量
        "def test_fake()" 会被 regex 命中 → total_test_count 虚增 → 任务通过率被低估。
        修复后优先 AST 逐文件计数（FunctionDef 节点），regex 仅作 AST 失败时的回退。
        """
        from src.datasets.dataset_loader import load_dataset

        # 测试代码含 1 个真实 test_ 函数 + 1 个字符串字面量里的 "def test_fake"
        test_code = 'def test_real():\n    assert True\n\nMSG = "see def test_fake() for details"\n'
        _make_project(
            tmp_path,
            "lit",
            "1.0",
            buggy=["def m():\n    return 1\n"],
            tests=[test_code],
            info={"description": "literal test_"},
        )
        loader = load_dataset("defects4j_python", data_dir=str(tmp_path))
        task = next(iter(loader))
        # AST 精确计数：仅 1 个真实 FunctionDef 命中 test_ 前缀
        assert task.total_test_count == 1, f"字符串字面量 def test_fake 不应被计入，实际 {task.total_test_count}"
        # expected_pass 缺失时回退 total_test_count（与 AST 口径一致）
        assert task.expected_pass_count == 1

    def test_ast_fallback_to_regex_on_syntax_error(self, tmp_path: pytest.TempPathFactory) -> None:
        """AST 解析失败（语法损坏的测试文件）时回退历史 regex 口径，加载行为不变。

        修复前 total_test_count 对语法损坏文件也走 regex（全量拼接后 findall），
        修复后优先 AST，AST 失败才回退 regex（口径一致）。
        """
        from src.datasets.dataset_loader import load_dataset

        # 语法损坏（冒号缺失的 def）→ ast.parse 失败 → 回退 regex
        broken_test = "def test_broken(:\n    x = 1\n"
        _make_project(
            tmp_path,
            "broke",
            "1.0",
            buggy=["def n():\n    return 1\n"],
            tests=[broken_test],
            info={"description": "broken"},
        )
        loader = load_dataset("defects4j_python", data_dir=str(tmp_path))
        task = next(iter(loader))
        # 回退 regex：def test_broken 命中 1 个（与修复前口径一致）
        assert task.total_test_count == 1
