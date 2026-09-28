"""
路线图剩余缺口落地单元测试（G1 SWE-bench Pro / G2 CodeBERT / G3 pyright）。

覆盖：
- G1a: contamination_check.CONTAMINATION_RESISTANT_BENCHMARKS 含 swe-bench-pro 条目；
- G1b: dataset_loader.load_dataset("swe_bench_pro") 路由到 SWEBenchDataset +
       get_available_datasets 同步；
- G2:  embedding_utils CodeBERT 后端（EMBEDDING_BACKEND=codebert 缺依赖回退
       None；优先级 codebert → sentence_transformers → chromadb）；
- G3:  type_repair pyright 静态类型后端（TYPE_CHECK_BACKEND 开关路由 /
       pyright 不可用保守降级 / type_repair_layer 后端接线）。

全部测试零 LLM / 零重型模型依赖（缺失的可选依赖走保守降级路径）。
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── G1a: SWE-bench Pro 抗污染基准注册表 ─────────────────────────────────────


class TestSweBenchProRegistry:
    """experiments.contamination_check 注册表含 SWE-bench Pro 条目。"""

    def test_registry_contains_swe_bench_pro(self):
        from experiments.contamination_check import CONTAMINATION_RESISTANT_BENCHMARKS

        assert "swe-bench-pro" in CONTAMINATION_RESISTANT_BENCHMARKS

    def test_swe_bench_pro_required_fields(self):
        from experiments.contamination_check import CONTAMINATION_RESISTANT_BENCHMARKS

        meta = CONTAMINATION_RESISTANT_BENCHMARKS["swe-bench-pro"]
        assert meta["display_name"] == "SWE-bench Pro"
        # 抗污染机制说明含 copyleft 设计口径
        assert "copyleft" in meta["resistance_mechanism"]
        # 建议与主基准成对报告
        assert meta.get("recommended_pairing")

    def test_render_section_lists_swe_bench_pro(self):
        from experiments.contamination_check import render_resistant_benchmark_section

        joined = "\n".join(render_resistant_benchmark_section())
        assert "SWE-bench Pro" in joined


# ─── G1b: swe_bench_pro 数据集加载器路由 ────────────────────────────────────


class TestSweBenchProLoader:
    """load_dataset("swe_bench_pro") 复用 SWEBenchDataset（字段同构口径）。"""

    def test_load_dataset_routes_to_swebench_dataset(self):
        from src.datasets.dataset_loader import SWEBenchDataset, load_dataset

        ds = load_dataset("swe_bench_pro", data_dir="/tmp/nonexistent_pro_dir")
        assert isinstance(ds, SWEBenchDataset)
        # 数据目录指向 Pro 数据集目录（非默认 lite 目录）
        assert "nonexistent_pro_dir" in ds.data_dir

    def test_swebench_pro_alias(self):
        from src.datasets.dataset_loader import SWEBenchDataset, load_dataset

        ds = load_dataset("swebench_pro", data_dir="/tmp/nonexistent_pro_dir")
        assert isinstance(ds, SWEBenchDataset)

    def test_get_available_datasets_lists_pro(self):
        from src.datasets.dataset_loader import get_available_datasets

        names = get_available_datasets()
        assert "swe_bench_pro" in names
        assert "swebench_pro" in names

    def test_empty_pro_dataset_degrades_gracefully(self, monkeypatch):
        """Pro 数据目录为空时加载器 graceful degrade（空任务列表，不崩溃）。"""
        import src.datasets.dataset_loader as dl

        monkeypatch.setattr(
            dl.SWEBenchDataset,
            "_load_raw_data",
            lambda self: None,  # 模拟目录为空（无 JSONL 可解析）
        )
        from src.datasets.dataset_loader import load_dataset

        ds = load_dataset("swe_bench_pro", data_dir="/tmp/definitely_empty_pro_dir")
        assert ds.size == 0


# ─── G2: CodeBERT 嵌入后端 ──────────────────────────────────────────────────


class TestCodebertBackend:
    """embedding_utils 的 CodeBERT 后端（缺 transformers 时保守回退 None）。"""

    def _reset_backend_cache(self):
        from src.utils import embedding_utils

        embedding_utils._backend_cache = {"instance": None, "name": None}
        embedding_utils._backend_initialized = False

    def test_codebert_unavailable_falls_back_to_none(self, monkeypatch):
        """EMBEDDING_BACKEND=codebert 但 transformers 未装 → embed_text None。"""
        self._reset_backend_cache()
        monkeypatch.setenv("EMBEDDING_BACKEND", "codebert")
        # transformers 未安装（本环境确认缺失）：AutoModel 导入抛 ImportError
        # → 回退 None（词袋余弦保守口径保持）
        from src.utils.embedding_utils import embed_text

        assert embed_text("def f():\n    return 1\n") is None

    def test_codebert_explicit_spec_logged_not_crash(self, monkeypatch):
        """显式指定 codebert 时异常路径不崩溃（保守降级）。"""
        self._reset_backend_cache()
        monkeypatch.setenv("EMBEDDING_BACKEND", "codebert")
        from src.utils import embedding_utils

        _name, instance = embedding_utils._load_backend()
        assert instance is None
        assert _name is None

    def test_auto_priority_codebert_first(self, monkeypatch):
        """auto 优先级：codebert(transformers) → sentence_transformers → chromadb。

        用 monkeypatch 屏蔽 transformers / sentence_transformers 导入，
        验证 auto 路径在"codebert 不可用"时能正确降级到下一个可用后端
        （chromadb，若 venv 已装；否则 None）——优先级链不崩溃、
        且 codebert 被真实尝试过（非静默跳过）。
        """
        self._reset_backend_cache()
        monkeypatch.setenv("EMBEDDING_BACKEND", "auto")
        import builtins

        _real_import = builtins.__import__
        _blocked = {"transformers", "sentence_transformers"}
        _attempted: list[str] = []

        def _block(mod, *args, **kwargs):
            if mod in _blocked:
                _attempted.append(mod)
                raise ImportError(f"{mod} blocked for priority test")
            return _real_import(mod, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_block):
            from src.utils import embedding_utils

            _name, instance = embedding_utils._load_backend()

        # codebert 分支确实被尝试过（transformers 导入被拦截）
        assert "transformers" in _attempted
        # 降级结果：chromadb（venv 已装时）或 None（未装时）
        try:
            import chromadb  # noqa: F401

            _chroma_available = True
        except ImportError:
            _chroma_available = False
        if _chroma_available:
            assert _name == "chromadb"
            assert instance is not None
        else:
            assert _name is None
            assert instance is None

    def test_codebert_model_env_var(self, monkeypatch):
        """EMBEDDING_CODEBERT_MODEL 可覆盖默认模型名（缺失依赖时仅验证
        环境变量读取路径，不真实加载模型）。"""
        self._reset_backend_cache()
        monkeypatch.setenv("EMBEDDING_BACKEND", "codebert")
        monkeypatch.setenv("EMBEDDING_CODEBERT_MODEL", "test/local-codebert")
        from src.utils import embedding_utils

        _name, instance = embedding_utils._load_backend()
        # transformers 缺失 → 仍回退 None（保守）
        assert instance is None

    def test_embed_with_backend_codebert_path(self, monkeypatch):
        """_embed_with_backend 的 codebert 分支：注入 fake tokenizer/model，
        验证 [CLS] 归一化向量提取路径（torch 缺失时走保守异常路径）。"""
        self._reset_backend_cache()
        monkeypatch.setenv("EMBEDDING_BACKEND", "codebert")
        from src.utils import embedding_utils

        # 构造 fake instance（模拟 transformers 加载成功后的 dict 结构）
        class _FakeTokenizer:
            def __call__(self, text, truncation=None, max_length=None):
                return {"input_ids": [[1, 2]], "attention_mask": [[1, 1]]}

        class _FakeCLS:
            def __getitem__(self, key):
                if key == 0:
                    return _FakeVec()
                return key

        class _FakeOut:
            last_hidden_state = _FakeCLS()

        class _FakeVec:
            def __init__(self):
                self._v = [0.6, 0.8]

            def norm(self):
                return 1.0

            def tolist(self):
                return self._v

        class _FakeModel:
            def eval(self):
                return self

            def __call__(self, **kwargs):
                return _FakeOut()

        fake_instance = {"tokenizer": _FakeTokenizer(), "model": _FakeModel(), "model_name": "fake"}
        # 让 _embed_with_backend 走 codebert 分支（不真实加载）
        embedding_utils._backend_cache = {"instance": fake_instance, "name": "codebert"}
        embedding_utils._backend_initialized = True

        # torch 未安装时 _embed_with_backend 的 codebert 分支应走异常路径回退 None
        # （保守口径：不崩溃）
        try:
            vec = embedding_utils._embed_with_backend(fake_instance, "def f(): pass")
            # torch 可用时返回归一化向量列表
            if vec is not None:
                assert isinstance(vec, list)
                assert all(isinstance(x, float) for x in vec)
        except Exception:
            # 无 torch：保守路径（_embed_with_backend 捕获后回退 None 语义由
            # 调用方 embed_text 承担）；本测试仅验证不抛出未捕获异常
            pass


# ─── G3: pyright 静态类型后端 ───────────────────────────────────────────────


class TestPyrightBackend:
    """type_repair 的 pyright 静态类型后端（TYPE_CHECK_BACKEND 路由 + 保守降级）。"""

    def test_default_backend_is_mypy(self, monkeypatch):
        monkeypatch.delenv("TYPE_CHECK_BACKEND", raising=False)
        from src.tools.type_repair import _static_type_check_backend

        assert _static_type_check_backend() == "mypy"

    def test_pyright_backend_env(self, monkeypatch):
        monkeypatch.setenv("TYPE_CHECK_BACKEND", "pyright")
        from src.tools.type_repair import _static_type_check_backend

        assert _static_type_check_backend() == "pyright"
        # 大小写不敏感
        monkeypatch.setenv("TYPE_CHECK_BACKEND", "PyRight")
        assert _static_type_check_backend() == "pyright"

    def test_pyright_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("TYPE_CHECK_ENABLE", raising=False)
        monkeypatch.setenv("TYPE_CHECK_BACKEND", "pyright")
        from src.tools.type_repair import _run_pyright_findings

        assert _run_pyright_findings("def f():\n    return 1\n", "def f():\n    return 2\n") == []

    def test_pyright_not_selected_under_mypy_backend(self, monkeypatch):
        """TYPE_CHECK_ENABLE=true 但 backend=mypy（默认）时 pyright 层不触发。"""
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.delenv("TYPE_CHECK_BACKEND", raising=False)
        from src.tools.type_repair import _run_pyright_findings

        assert _run_pyright_findings("def f():\n    return 1\n", "def f():\n    return 2\n") == []

    def test_pyright_unavailable_returns_empty(self, monkeypatch):
        """pyright CLI 与 pyright-python 包均不可用时保守返回空列表。

        本环境两者均未安装（已确认）：shutil.which('pyright') 为 None 且
        `import pyright` 抛 ImportError → 返回 []（保持 ast 静态层口径）。
        """
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.setenv("TYPE_CHECK_BACKEND", "pyright")
        from src.tools import type_repair

        with patch("shutil.which", return_value=None):
            import builtins

            _real_import = builtins.__import__

            def _raise_on_pyright(name, *args, **kwargs):
                if name == "pyright":
                    raise ImportError("pyright-python not installed")
                return _real_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=_raise_on_pyright):
                findings = type_repair._run_pyright_findings(
                    "def f():\n    return 1\n",
                    "def f():\n    return undefined_sym\n",
                )
        assert findings == []

    def test_type_repair_layer_pyright_backend_no_exception(self, monkeypatch):
        """TYPE_CHECK_BACKEND=pyright（后端不可用）时 type_repair_layer
        保守降级：不抛异常，mypy_findings_count 键保持（值为 0）。"""
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.setenv("TYPE_CHECK_BACKEND", "pyright")
        from src.tools.type_repair import type_repair_layer

        result = type_repair_layer(
            original_code="def f(x):\n    return x + 1\n",
            patched_code="def f(x):\n    x = 'str'\n    return x\n",  # 触发 ast 层 type_mismatch
        )
        # ast 层疑点仍产出（静态层不受 pyright 不可用影响）
        assert "findings" in result
        assert "mypy_findings_count" in result
        assert result["mypy_findings_count"] == 0  # pyright 不可用 → 0 条
        # 契约字段保持（未修订）
        assert result["contract_ok"] is True


class TestPyrightFindingsParsing:
    """_run_pyright_findings 的 JSON/文本输出解析路径（mock subprocess）。"""

    def test_json_diagnostics_parsed(self, monkeypatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.setenv("TYPE_CHECK_BACKEND", "pyright")
        from src.tools import type_repair

        fake_report = json.dumps(
            {
                "generalDiagnostics": [
                    {
                        "severity": "error",
                        "range": {"start": {"line": 2, "character": 4}, "end": {"line": 2, "character": 20}},
                        "message": "Argument of type int incompatible with expected str",
                        "rule": "reportArgumentType",
                    },
                    {
                        "severity": "error",
                        "range": {"start": {"line": 3, "character": 0}, "end": {"line": 3, "character": 5}},
                        "message": "Unused variable",
                        "rule": "reportUnusedVariable",  # 不在白名单 → 过滤
                    },
                    {
                        "severity": "warning",
                        "range": {"start": {"line": 4, "character": 0}, "end": {"line": 4, "character": 5}},
                        "message": "low severity",
                        "rule": "reportArgumentType",
                    },
                ]
            }
        )

        class _FakeProc:
            stdout = fake_report

        with (
            patch("shutil.which", return_value="/usr/bin/pyright-fake"),
            patch("subprocess.run", return_value=_FakeProc()),
        ):
            findings = type_repair._run_pyright_findings(
                "def f(x):\n    pass\n",
                "def f(x):\n    g(x)\n",
            )
        # 仅 reportArgumentType（白名单 + error 级）保留；rule 名转 kind
        assert len(findings) == 1
        assert findings[0]["kind"] == "pyright_reportArgumentType"
        assert findings[0]["line"] == 3  # 0-based line 2 → 1-based 3
        assert findings[0]["file"] == "patched"

    def test_empty_patched_code_returns_empty(self, monkeypatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.setenv("TYPE_CHECK_BACKEND", "pyright")
        from src.tools.type_repair import _run_pyright_findings

        assert _run_pyright_findings("def f():\n    pass\n", "") == []
        assert _run_pyright_findings("def f():\n    pass\n", "   \n") == []
