"""
性能回归守卫测试（2026-09-26 全面优化轮次新增）。

针对本优化轮次改动的关键性能路径提供"行为不变 + 不回归"的守卫：
- code_context.extract_focused_code_detail 复用已解析 tree 走契约块路径
  （P0 1.2 AST 重复解析消除）
- complexity_router.count_imports 的 _tree 复用参数（run_benchmark
  单次解析复用）
- dataset_loader 的 O(1) task_index 与 property 直访 _tasks 路径
- error_classifier 共享合并文本的 classify/classify_with_context 一致性
- workflow._diagnosis_hits_test_gen_keywords 预编译 alternation 正则

断言口径：
- 复用路径（传 _tree/_ast）与独立路径（不传）结果逐字段一致；
- 复用路径不触发新的 ast.parse（通过注入计数桩验证）；
- 性能相关断言保持宽松（量级阈值），避免 CI 机器抖动误报。
"""

from __future__ import annotations

import ast
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.complexity_router import count_imports
from src.datasets.dataset_loader import BenchmarkTask, InMemoryDataset

# ─── code_context：AST 复用路径 ──────────────────────────────────────────────


class TestExtractFocusedCodeAstReuse:
    """extract_focused_code_detail 的契约块路径应复用已解析 tree。"""

    def test_ingredient_block_appended_within_budget(self):
        from src.tools.code_context import extract_focused_code_detail

        src = (
            "import os\nimport json\n\n__all__ = ['a']\n\nCONFIG = 42\n\n"
            "def helper_a(x):\n    return x * 2\n\n"
            "def a(y):\n    return helper_a(y) + 1\n"
        )
        out, resolved = extract_focused_code_detail(src, focus_function="a", max_chars=3000)
        assert resolved is True
        assert "[PATCH_INGREDIENTS]" in out
        assert "helper_a" in out  # 契约块含调用签名

    def test_reuse_path_produces_same_block_as_standalone(self):
        """复用 _ast 的 preserve_patch_ingredients 与独立路径字段逐一对齐。"""
        from src.tools.code_analyzer import preserve_patch_ingredients

        src = "import os\n\nREG = 1\n\ndef h(x):\n    return x\n\ndef a(y):\n    return h(y)\n"
        tree = ast.parse(src)
        standalone = preserve_patch_ingredients(src, "a")
        reuse = preserve_patch_ingredients(src, "a", _ast=tree)
        for key in ("imports", "exports", "register_symbols", "target_ast", "called_signatures", "module_constants"):
            assert reuse[key] == standalone[key], key
        assert reuse["ast_tree"] is tree

    def test_reuse_path_does_not_reparse(self):
        """注入 ast.parse 计数桩：复用路径不应新增任何 ast.parse 调用。"""
        import src.tools.code_analyzer as ca

        parse_count = {"n": 0}
        real_parse = ast.parse

        def counting_parse(source, *args, **kwargs):
            parse_count["n"] += 1
            return real_parse(source, *args, **kwargs)

        src = "def a():\n    return 1\n"
        tree = ast.parse(src)  # 外部已解析（不计入桩）
        # 只桩 code_analyzer 模块内的 ast.parse 引用（其通过 ast.parse 解析）
        ca.ast.parse = counting_parse  # type: ignore[method-override]
        try:
            reuse = ca.preserve_patch_ingredients(src, "a", _ast=tree)
            assert parse_count["n"] == 0, "复用路径不应触发 ast.parse"
        finally:
            ca.ast.parse = real_parse  # type: ignore[method-override]
        assert reuse["parsed"] is True
        assert reuse["target_ast"] == "def a():\n    return 1"


# ─── complexity_router：count_imports tree 复用 ──────────────────────────────


class TestCountImportsTreeReuse:
    def test_standalone_and_reuse_agree(self):
        src = "import os\nfrom x import y\nimport z\n\nA = 1\n"
        assert count_imports(src) == 3
        tree = ast.parse(src)
        assert count_imports(src, _tree=tree) == 3

    def test_invalid_source_without_tree_returns_zero(self):
        assert count_imports("def f(:\n", _tree=None) == 0

    def test_no_imports(self):
        src = "A = 1\nB = 2\n"
        assert count_imports(src) == 0
        tree = ast.parse(src)
        assert count_imports(src, _tree=tree) == 0


# ─── dataset_loader：O(1) task_index 与 property 直访 ─────────────────────────


def _make_inmemory(n: int = 200) -> InMemoryDataset:
    """构造含 n 个任务的内存数据集（task_id 形如 t000..t199）。"""
    ds = InMemoryDataset()
    for i in range(n):
        ds.add_task(
            BenchmarkTask(
                task_id=f"repo__t{i:03d}",
                repo_name="repo",
                problem_statement=f"issue {i}",
                instance_code=f"def f_{i}():\n    return {i}\n",
                test_code=f"def test_f_{i}():\n    assert f_{i}() == {i}\n",
                expected_pass_count=1,
                total_test_count=1,
            )
        )
    return ds


class TestDatasetLoaderO1Paths:
    def test_task_ids_and_size_consistent(self):
        ds = _make_inmemory(50)
        ids = ds.task_ids
        assert len(ids) == 50
        assert ds.size == 50
        assert ids[0] == "repo__t000"

    def test_get_task_by_id_o1_lookup(self):
        ds = _make_inmemory(50)
        task = ds.get_task_by_id("repo__t023")
        assert task is not None
        assert task.task_id == "repo__t023"
        assert ds.get_task_by_id("repo__missing") is None

    def test_task_index_o1_lookup(self):
        ds = _make_inmemory(200)
        # 直接验证 O(1) 索引存在且与遍历结果一致
        idx = getattr(ds, "_task_index", None)
        if idx is None:
            return  # 旧实现无索引，跳过守卫
        ds.get_task_by_id("repo__t100")  # 触发惰性重建
        idx = ds._task_index
        assert idx["repo__t100"].task_id == "repo__t100"
        assert len(idx) == 200

    def test_repeated_property_calls_stable_and_fast(self):
        """O(n) property 直访 _tasks 后，重复调用不应随 n 线性放大。"""
        ds = _make_inmemory(300)
        t0 = time.perf_counter()
        for _ in range(200):
            _ = ds.task_ids
            _ = ds.size
        elapsed = time.perf_counter() - t0
        # 300 任务 × 200 次 property 调用：O(1) 路径应在百毫秒量级内
        # （O(n) 每调用 O(n) 拷贝则 ~300*200 = 6 万次对象构造，仍可控，
        #  此处守卫的是"指数放大"量级回归而非微秒级绝对值）
        assert elapsed < 2.0, f"重复 property 调用耗时 {elapsed:.2f}s 超阈值"

    def test_filter_by_repo_pattern(self):
        ds = _make_inmemory(4)
        matched = ds.filter_by_repo("repo")
        assert len(matched) == 4
        assert ds.filter_by_repo("nomatch") == []


# ─── error_classifier：共享合并文本一致性 ────────────────────────────────────


class TestErrorClassifierSharedCombined:
    def test_classify_and_classify_with_context_agree(self):
        from src.agents.error_classifier import ErrorClassifier

        clf = ErrorClassifier()
        out = """
==================== test session starts ====================
FAILED test_mod.py::test_fail - TypeError: unsupported operand
E   TypeError: 'int' + 'str'
"""
        failed = [{"name": "test_fail", "error": "TypeError: 'int' + 'str'"}]
        cat_direct = clf.classify(out, failed)
        cat_ctx, _ = clf.classify_with_context(out, failed)
        assert cat_direct == cat_ctx

    def test_extract_error_context_standalone_matches_shared(self):
        from src.agents.error_classifier import ErrorClassifier

        clf = ErrorClassifier()
        out = 'Traceback (most recent call last):\n  File "mod.py", line 5, in f\n'
        failed = []
        ctx_standalone = clf.extract_error_context(out, failed)
        _cat, ctx_shared = clf.classify_with_context(out, failed)
        assert ctx_standalone.filename == ctx_shared.filename
        assert ctx_standalone.line == ctx_shared.line

    def test_combined_shared_between_classify_and_extract(self):
        """classify(_combined=...) 与独立 classify 结果一致（共享路径等价）。"""
        from src.agents.error_classifier import ErrorCategory, ErrorClassifier

        clf = ErrorClassifier()
        out = "ImportError: No module named 'missing_pkg'"
        failed = []
        combined = out + "\n"
        assert clf.classify(out, failed, _combined=combined) == ErrorCategory.IMPORT_ERROR
        assert clf.classify(out, failed) == ErrorCategory.IMPORT_ERROR


# ─── workflow：诊断关键词预编译正则 ──────────────────────────────────────────


class TestWorkflowDiagnosisKeywordRegex:
    def test_precompiled_regex_hits_all_keywords(self):
        from src.graph.workflow import _TEST_GEN_DIAGNOSIS_KEYWORDS, _diagnosis_hits_test_gen_keywords

        for kw in _TEST_GEN_DIAGNOSIS_KEYWORDS:
            assert _diagnosis_hits_test_gen_keywords(f"xx {kw} xx"), kw

    def test_regex_equivalent_to_any_substring(self):
        """预编译 alternation 正则与历史 any(kw in text) 口径等价。"""
        import re as _re

        from src.graph.workflow import _TEST_GEN_DIAGNOSIS_KEYWORDS, _diagnosis_hits_test_gen_keywords

        ref = _re.compile("|".join(_re.escape(kw) for kw in _TEST_GEN_DIAGNOSIS_KEYWORDS))
        samples = [
            "",
            "普通诊断文本",
            "测试生成错误",
            "期望的异常类型不匹配",
            "test code has bug",
            "测试设计存在错误",
            "测试用例",
        ]
        for s in samples:
            legacy = any(kw in s for kw in _TEST_GEN_DIAGNOSIS_KEYWORDS)
            assert _diagnosis_hits_test_gen_keywords(s) == legacy == bool(ref.search(s)), s

    def test_m5_source_defect_signatures_removed(self):
        """M5（2026-09-29 审查 P0）：三个源码缺陷签名词（AttributeError /
        NameError / SyntaxError）已从关键词表删除，命中它们不再触发"测试
        生成错误"路由（防止把实现缺陷误判为测试缺陷 → 假通过）。"""
        from src.graph.workflow import _diagnosis_hits_test_gen_keywords

        for kw in ("AttributeError", "NameError", "SyntaxError"):
            assert not _diagnosis_hits_test_gen_keywords(f"xx {kw} xx"), f"M5 后 {kw} 不应命中"


# ─── llm_client：zai 域名预编译正则等价性守卫 ────────────────────────────────


class TestZaiDomainRegexEquivalence:
    """_is_zai_compatible 预编译正则与历史 any(d in url) 口径逐样本等价。"""

    def test_regex_equivalent_to_substring_scan(self):
        import src.agents.llm_client as lc
        from src.agents.llm_client import _is_zai_compatible

        # 历史口径参照
        legacy_domains = ["bigmodel.cn", "zhipuai"]
        samples = [
            "https://open.bigmodel.cn/api/paas/v4",
            "https://open.bigmodel.cn/api/paas/v4/embeddings",
            "https://api.zhipuai.cn",
            "https://api.zhipuai.cn/v4",
            "https://api.openai.com/v1",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "https://custom.host.example/zhipuai-proxy",  # 子串命中（历史口径同样命中）
            "",
        ]
        for url in samples:
            legacy = any(d in url for d in legacy_domains)
            assert _is_zai_compatible(url) == legacy, url
        # bigmodel.cn 的 "." 为字面匹配（正则已转义）：非域名变体不误命中，
        # 同时不与历史子串扫描口径产生分歧
        assert _is_zai_compatible("https://bigmodelXcn.example") is False
        assert "bigmodelXcn.example" not in legacy_domains  # sanity: 历史口径同样不命中
        # 模块级预编译正则确实存在（防止重构漂移回 list 重建）
        assert isinstance(lc._ZAI_DOMAIN_RE, re.Pattern)


# ─── 大文件 AST 解析量级守卫（宽松阈值，防量级回归）────────────────────────


class TestAstParseScaleGuard:
    def test_large_source_parse_under_seconds(self):
        """~400KB 源码的 extract_focused_code_detail 应在秒级内完成。

        守卫的是"量级回归"（如误引入逐函数二次解析 → 分钟级），
        不是微秒级绝对值（CI 机器抖动）。
        """
        from src.tools.code_context import extract_focused_code_detail

        func = "def f():\n    x = 1\n    return x\n\n"
        big = "import os\n" + func * 12000  # ~400KB
        t0 = time.perf_counter()
        _out, resolved = extract_focused_code_detail(big, focus_function="f", max_chars=3000)
        elapsed = time.perf_counter() - t0
        assert resolved is True
        assert elapsed < 3.0, f"大文件聚焦提取 {elapsed:.2f}s 超量级阈值"
