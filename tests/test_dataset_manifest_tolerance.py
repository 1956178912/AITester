"""AB-5（2026-10-19）：数据集适配层的**坏输入容错**回归锁（零 LLM，$0）。

立项依据是 ROUND3 §3.2 的一句话——"多数据集适配层：本地只有部分数据集，其余分支
不可达"。本轮先核查这句前提：**它把两类完全不同的未覆盖行混成了一类**。
`dataset_loader` / `dataset_ult` / `dataset_realbugs` 的 47 条未覆盖行里，主体是
`except SyntaxError` / `except json.JSONDecodeError` / 坏行 `continue` 这类
**容错分支**——它们不需要真实数据集，需要的是**一份真的坏输入**。写一个坏 JSONL
到 `tmp_path` 就是真实输入，不是 mock。

锁的落点不是覆盖率，是一条测量学性质：**坏行要被跳过并留下日志，既不能中止整批
加载，也不能静默吞掉**。后者的代价不可见——数据集规模少几条，而报表里看不出来。

真正需要本地数据集才能走到的分支（如 `data_dir` 缺失回退）不在本文件，
按 `not_evaluated` 登记，前置条件见 `docs/PROJECT_STATUS_REGISTER.md`。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from src.datasets import dataset_realbugs, dataset_ult
from src.datasets.dataset_loader import SWEBenchDataset
from src.datasets.dataset_realbugs import BugsInPyDataset, QuixBugsDataset
from src.datasets.dataset_ult import ULTDataset


@pytest.mark.unit
class TestUltSyntaxTolerance:
    """ULT 侧：被测代码语法损坏时不得抛出，只能保守降级。"""

    def test_first_function_name_returns_none_on_unparseable_code(self) -> None:
        assert dataset_ult._first_function_name("def f(:\n    pass") is None

    def test_first_function_name_returns_none_without_any_function(self) -> None:
        assert dataset_ult._first_function_name("x = 1") is None

    def test_stringified_tests_field_that_is_not_json_degrades_to_single_item(self) -> None:
        # 官方 ULT.jsonl 里 tests 既可能是 list 也可能是字符串化 JSON；
        # 非 JSON 的裸串必须保留为单条，不能整行丢弃
        row = dataset_ult._normalize_row({"tests": "assert f(1) == 2"})
        assert row["test_cases"] == ["assert f(1) == 2"]

    def test_blank_stringified_tests_field_degrades_to_empty_list(self) -> None:
        assert dataset_ult._normalize_row({"tests": "   "})["test_cases"] == []


@pytest.mark.unit
class TestRealBugsSyntaxTolerance:
    """BugsInPy 侧：AST 计数失败要回退 regex，而不是放弃该任务。"""

    def test_count_test_functions_falls_back_to_regex_on_syntax_error(self) -> None:
        broken = "def test_alpha(:\n    pass\ndef test_beta():\n    pass"
        assert dataset_realbugs._count_test_functions(broken) == 2

    def test_count_test_functions_uses_ast_on_valid_code(self) -> None:
        assert dataset_realbugs._count_test_functions("def test_ok():\n    pass\n") == 1

    def test_first_top_level_function_returns_none_on_syntax_error(self) -> None:
        assert dataset_realbugs._first_top_level_function("def g(:") is None


@pytest.mark.unit
class TestEnrichmentBadLineIsSkippedNotFatal:
    """补充文件：一行坏 JSON 只作废**那一行**，其余照收，且必须留痕。"""

    def test_bad_json_line_skipped_but_good_rows_survive(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = str(tmp_path / "enrich.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"instance_id": "good_1", "source_code": "def a(): pass"}\n')
            f.write("\n")  # 空行
            # 坏行必须自带换行结尾：若写成 `\\n`（字面反斜杠+n）这行不会结束，
            # 后一条记录会被拼进同一物理行、当成同一个坏 JSON 一起跳过，
            # 于是主键守卫根本没被走到——变异检查会因此"存活"。
            f.write("这不是 JSON{{{\n")  # 坏行
            f.write('{"no_instance_id": 1}\n')  # 缺主键
            f.write('{"instance_id": "", "source_code": "orphan"}\n')  # 空主键
            f.write('{"instance_id": 0, "source_code": "orphan"}\n')  # falsy 主键
            f.write('{"instance_id": "good_2", "source_code": ""}\n')  # 空值字段被剔
        with caplog.at_level(logging.WARNING, logger="src.datasets.dataset_loader"):
            enriched = SWEBenchDataset._load_enrichment(path)
        # 三条无有效主键的记录都要被守卫挡住（写坏补充文件时不该产出 None/""/0 键，
        # 那会让下游 enriched[row_id] 查表拿到语义不明的空壳）
        assert set(enriched) == {"good_1", "good_2"}, "坏行不得连带中止整份补充文件"
        assert "补充文件 JSON 解析失败" in caplog.text, "跳过必须留痕，不能静默丢数据"
        # 实测契约：剔除的是**值为空**的字段，主键自身保留（写这张表时按
        # `enriched[row_id]` 取用，删掉 instance_id 会让下游取不到标识）。
        # 注：`None` 在 JSON 里必须写作 `null`——裸写 Python 的 None 会让整行
        # 变成非法 JSON、走上面的跳过分支，是另一条路径，别混用。
        assert enriched["good_2"] == {"instance_id": "good_2"}
        assert enriched["good_1"]["source_code"] == "def a(): pass"

    def test_missing_enrichment_file_returns_empty_mapping(self) -> None:
        assert SWEBenchDataset._load_enrichment("") == {}
        assert SWEBenchDataset._load_enrichment("/nonexistent/enrich.jsonl") == {}

    def test_unusable_primary_key_rows_leave_one_bounded_trace(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """缺/空/falsy 主键三类行都要挡住，且**汇总一条** warning（不逐行刷屏）。

        这条锁的是 AB-5 修的行为缺口：原实现只在 JSON 解析失败时留痕，无主键行
        静默丢弃——补充文件用错键名（如 `id`）时会整份失效而报表毫无痕迹。
        """
        path = str(tmp_path / "enrich.jsonl")
        rows = [
            '{"instance_id": null, "instance_code": "a"}',
            '{"instance_id": "", "instance_code": "b"}',
            '{"instance_id": 0, "instance_code": "c"}',
            '{"instance_id": "ok", "instance_code": "def f(): pass"}',
        ]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")
        with caplog.at_level(logging.WARNING, logger="src.datasets.dataset_loader"):
            enriched = SWEBenchDataset._load_enrichment(path)
        assert set(enriched) == {"ok"}, "非标识符主键不得写入映射（下游按 instance_id 查表）"
        assert "3 行缺少 instance_id" in caplog.text, "汇总痕迹必须给出被丢行数——少了它无法区分'没配'与'配了但全废'"
        missing_id_warnings = [r for r in caplog.records if "缺少 instance_id" in r.getMessage()]
        assert len(missing_id_warnings) == 1, "3 行只汇总 1 条，不得逐行刷屏"


@pytest.mark.unit
class TestSweTestListTolerance:
    """FAIL_TO_PASS / PASS_TO_PASS：解析失败按空处理（路由条件永不命中=历史口径零变化）。"""

    def test_list_input_is_stringified_and_blanks_dropped(self) -> None:
        assert SWEBenchDataset._parse_swe_test_list(["t::a", "", "t::b"]) == ["t::a", "t::b"]

    def test_json_encoded_string_is_parsed(self) -> None:
        assert SWEBenchDataset._parse_swe_test_list('["t::a"]') == ["t::a"]

    def test_unparseable_string_yields_empty_list_with_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="src.datasets.dataset_loader"):
            assert SWEBenchDataset._parse_swe_test_list("not-json[") == []
        assert "测试节点列表解析失败" in caplog.text

    def test_non_string_non_list_yields_empty_list(self) -> None:
        # 类型不符（如上游给了 int）→ 空表，不得抛出打断整批加载
        assert SWEBenchDataset._parse_swe_test_list(42) == []
        assert SWEBenchDataset._parse_swe_test_list(None) == []

    def test_hunk_header_without_context_segment_is_skipped(self) -> None:
        """hunk 头被截断（只有一个 `@@`，没有上下文段）时只能跳过，不得 IndexError。

        注：完整 hunk 头 `@@ -a,b +c,d @@ ctx` 切分后本就是 3 段，故触发守卫必须
        用**截断**形态——用完整头当输入会让这条锁对着一条永不成立的分支空转。
        """
        assert SWEBenchDataset._extract_suggested_function("@@ -1,2") is None


@pytest.mark.unit
class TestUltManifestTolerance:
    """ULT 加载器：manifest 形态损坏时的降级面（fixture 目录，不碰本地缓存）。"""

    def test_malformed_json_array_manifest_degrades_to_empty(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        # 官方 ULT.jsonl 文件名是 .jsonl 但内容为顶层数组；数组本身损坏时
        # 只能产出空数据集 + warning，不得把异常抛给 benchmark 主循环
        manifest = tmp_path / "ULT.jsonl"
        manifest.write_text('[{"function_name": "f", "source_code": "def f(): pass"', encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="src.datasets.dataset_ult"):
            ds = ULTDataset(data_dir=str(manifest))
            assert ds.tasks == []
        assert "ULT manifest JSON 数组解析失败" in caplog.text

    def test_jsonl_manifest_bad_line_skipped_but_good_row_survives(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        manifest = tmp_path / "ult_manifest.jsonl"
        manifest.write_text(
            json.dumps({"function_name": "f", "source_code": "def f():\n    return 1\n"}) + "\n\n" + "坏行 not-json\n",
            encoding="utf-8",
        )
        with caplog.at_level(logging.WARNING, logger="src.datasets.dataset_ult"):
            ds = ULTDataset(data_dir=str(tmp_path))
        assert ds.task_ids == ["ult__f"], "一行坏 JSON 只作废该行"
        assert "第 3 行解析失败" in caplog.text, "跳过必须带行号，否则无法定位坏数据"
        # 空行由**空行守卫**处理，不得退化成"坏行"：删掉守卫后空行也会被记一次
        # 解析失败，warning 条数即成为可观察的差异。
        assert len([r for r in caplog.records if "解析失败" in r.getMessage()]) == 1

    def test_non_dict_record_skipped(self, tmp_path: Path) -> None:
        # 合法 JSON 但不是对象（如裸数字）→ 计入 skipped 并继续，不得 AttributeError
        manifest = tmp_path / "ult_manifest.jsonl"
        manifest.write_text(
            "123\n" + json.dumps({"function_name": "g", "source_code": "def g():\n    return 2\n"}) + "\n",
            encoding="utf-8",
        )
        ds = ULTDataset(data_dir=str(tmp_path))
        assert ds.task_ids == ["ult__g"]

    def test_double_encoded_tests_string_still_becomes_one_gold_test(self, tmp_path: Path) -> None:
        """`tests` 是"JSON 编码的字符串字面量"时归一化后仍是 str——加载器需二次包装。

        这条锁的是 `_normalize_row` 与 `_load_raw_data` 的**接缝**：前者只在
        JSONDecodeError 时兜底成 list，`json.loads` 成功返回 str 时原样透传，
        故 248 行的二次判定并非冗余。
        """
        manifest = tmp_path / "ult_manifest.jsonl"
        manifest.write_text(
            json.dumps(
                {
                    "function_name": "h",
                    "source_code": "def h():\n    return 3\n",
                    "tests": json.dumps("assert h(1) == 3"),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        ds = ULTDataset(data_dir=str(tmp_path))
        assert [t.total_test_count for t in ds.tasks] == [1], "字符串字面量不得被逐字符展开"


@pytest.mark.unit
class TestQuixBugsDirectoryFilters:
    """QuixBugs 目录扫描：三类非任务文件必须被过滤，而不是产出一批废任务。"""

    def _build(self, root: Path) -> None:
        buggy = root / "python_programs"
        buggy.mkdir()
        (buggy / "good.py").write_text("def good(x):\n    return x\n", encoding="utf-8")
        (buggy / "notes.txt").write_text("not python", encoding="utf-8")  # 非 .py
        (buggy / "_helper.py").write_text("def _helper():\n    pass\n", encoding="utf-8")  # 下划线前缀
        (buggy / "bad-name.py").write_text("def bad():\n    pass\n", encoding="utf-8")  # 末段非标识符
        (buggy / "empty.py").write_text("", encoding="utf-8")  # 空文件

    def test_only_importable_non_empty_programs_become_tasks(self, tmp_path: Path) -> None:
        self._build(tmp_path)
        ds = QuixBugsDataset(data_dir=str(tmp_path))
        assert ds.task_ids == ["quixbugs__good"], (
            "非 .py / 下划线前缀 / 非标识符名 / 空文件四类都要过滤——漏一项就会造出一个必然执行失败的废任务"
        )


@pytest.mark.unit
class TestBugsInPyManifestTolerance:
    """BugsInPy：data_dir 直接指向 .jsonl 的显式文件口径 + 坏行容错。"""

    def test_data_dir_pointing_at_manifest_file_is_used_directly(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        manifest = tmp_path / "bugs.jsonl"
        manifest.write_text(
            "\n"  # 空行
            "坏行{{{ NotJson\n"  # 坏行
            + json.dumps(
                {
                    "project": "p",
                    "bug_id": "b1",
                    "file_path": "x.py",
                    "buggy_code": "def buggy():\n    return 0\n",
                    "test_code": "def test_a():\n    assert 1\n",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        ds = BugsInPyDataset(data_dir=str(manifest))
        assert ds._manifest_path() == str(manifest)
        with caplog.at_level(logging.INFO, logger="src.datasets.dataset_realbugs"):
            assert [t.task_id for t in ds.tasks] == ["bugsinpy__p_b1_x"], "空行/坏行只作废自身"
        # 口径：坏 JSON 行计入 skipped（实测 1），空行**不**计入。删掉空行守卫会让
        # 空行落进 JSONDecodeError 分支、skipped 变 2——真实坏行数被空行噪声抬高。
        assert "1 个任务（跳过 1 行无效记录）" in caplog.text
        assert "第 2 行解析失败" in caplog.text, "坏行 warning 必须带行号"


@pytest.mark.unit
class TestSweBenchDataDirResolution:
    """数据目录解析：Pro 变量优先于 rebench 泛化变量（口径写在 __init__ 注释里，此前无锁）。"""

    def test_pro_env_var_wins_over_generic(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pro_dir = tmp_path / "pro"
        generic_dir = tmp_path / "generic"
        monkeypatch.setenv("AITESTER_SWE_BENCH_PRO_DIR", str(pro_dir))
        monkeypatch.setenv("SWE_BENCH_DATA_DIR", str(generic_dir))
        assert SWEBenchDataset().data_dir == str(pro_dir), (
            "两个变量同时设置时 Pro 必须胜出——选错目录会让复测读到一个任务都没有的子集"
        )

    def test_generic_env_var_used_when_pro_absent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        generic_dir = tmp_path / "generic"
        monkeypatch.delenv("AITESTER_SWE_BENCH_PRO_DIR", raising=False)
        monkeypatch.setenv("SWE_BENCH_DATA_DIR", str(generic_dir))
        assert SWEBenchDataset().data_dir == str(generic_dir)

    def test_legacy_generic_filename_not_double_counted(self, tmp_path: Path) -> None:
        """`swe_bench_instances.jsonl` 已符合 `swe_bench_*_instances.jsonl` 通配，
        旧版兼容分支不得把它追加第二次（重复解析会让同一任务进 _tasks 两次）。"""
        (tmp_path / "swe_bench_instances.jsonl").write_text("", encoding="utf-8")
        paths = SWEBenchDataset(data_dir=str(tmp_path))._resolve_jsonl_paths()
        assert paths.count(str(tmp_path / "swe_bench_instances.jsonl")) == 1
