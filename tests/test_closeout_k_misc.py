"""KB 覆盖率收口：确定性修复 / 失败知识库 / 故障定位 / 语义缓存 / 配置写入的降级分支。

动机：这批模块的低覆盖行全部是**"外部输入不干净时"的保守降级**——AST 解析
失败、LLM 输出非法 JSON、知识库条目的时间戳损坏、语义索引条目的嵌入为零向量 /
跨用户条目、写配置时的空值/换行注入拒绝。它们共同的特征是：默认路径不经过，
但一旦触发就决定"是安全降级还是崩溃/数据损坏"。

纪律：零 LLM、零网络、零真实配置写盘（`config_manager.ENV_FILE` 指向 tmp_path）、
零真实嵌入（monkeypatch `embed_text`）；语义索引用真实单例但测试内清空条目。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.agents import failure_kb
from src.agents import fault_localizer as fl
from src.agents import semantic_cache as sc
from src.agents.failure_kb import kb_applied_state_key, kb_debugger_snippet, rank_knowledge_entries
from src.agents.semantic_cache import (
    SemanticCacheIndex,
    _SemanticEntry,
    build_semantic_index_from_cache_dir,
    get_semantic_index,
    maybe_rebuild_semantic_index,
)
from src.config import config_manager
from src.tools import deterministic_repair as dr


@pytest.mark.unit
class TestDeterministicRepairHelpers:
    """确定性修复的 AST 预检与 import 插入口径。"""

    def test_syntax_error_code_has_no_top_level_names(self):
        assert dr._top_level_names("def broken(:\n") == set()

    def test_top_level_names_covers_defs_classes_and_assignments(self):
        code = "import os\n\nX = 1\n\n\ndef f():\n    return X\n\n\nclass C:\n    pass\n"
        assert dr._top_level_names(code) == {"X", "f", "C"}

    def test_insert_import_after_module_docstring(self):
        code = "'''模块文档。'''\nX = 1\n"
        new_code = dr._insert_import(code, "os")
        lines = new_code.splitlines()
        assert lines[0].startswith("'''")
        assert lines[1] == "import os"
        assert "X = 1" in lines

    def test_attempt_repair_no_change_is_rejected(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(dr, "_TRANSFORMERS", (lambda code, output: ("noop", code),))
        outcome = dr.attempt_deterministic_repair(
            target_code="def f():\n    return 1\n",
            test_output="NameError: name 'os' is not defined",
        )
        assert outcome["attempted"] is True
        assert outcome["patch_code"] is None
        assert outcome["reason"] == "validation_failed:no_change"


@pytest.mark.unit
class TestFailureKbDegradation:
    """失败知识库闭环的排序/时间戳/观测键降级。"""

    def test_zero_weight_entries_break_ranking(self, monkeypatch: pytest.MonkeyPatch):
        entries = [{"error_category": "assertion", "root_cause": "x"}]
        monkeypatch.setattr(failure_kb, "_entry_decay_weight", lambda entry, now, half_life: 0.0)
        assert rank_knowledge_entries(entries, "assertion") == []

    def test_corrupted_last_seen_falls_back_to_empty(self, monkeypatch: pytest.MonkeyPatch):
        entry = {
            "error_category": "assertion",
            "root_cause": "边界处理缺失",
            "last_seen": "不是时间戳",
        }
        monkeypatch.setattr(failure_kb, "_kb_enabled", lambda: True)
        monkeypatch.setattr(failure_kb, "load_knowledge_base", lambda: [entry])
        monkeypatch.setattr(failure_kb, "rank_knowledge_entries", lambda entries, category, now=None: [entry])
        snippet = kb_debugger_snippet("assertion")
        assert snippet is not None
        assert "案例1" in snippet
        assert "最近修复于" not in snippet, "时间戳损坏时不得渲染半截日期文本"

    def test_applied_state_key_when_enabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(failure_kb, "_kb_enabled", lambda: True)
        assert kb_applied_state_key() == {"kb_prompt_snippet_applied": False}


@pytest.mark.unit
class TestFaultLocalizerDegradation:
    """LLM 推理定位的输入校验 / 调用失败 / JSON 解析失败降级。"""

    def test_empty_inputs_return_none(self):
        localizer = fl.FaultLocalizerAgent()
        assert localizer.localize(target_code="", test_code="", test_output="", failed_cases=[{"test": "t"}]) is None
        assert localizer.localize(target_code="def f(): pass", test_code="", test_output="", failed_cases=[]) is None

    def test_llm_call_failure_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        localizer = fl.FaultLocalizerAgent()
        monkeypatch.setattr(
            localizer,
            "_call_llm_with_cache",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("LLM 不可用（模拟）")),
        )
        assert (
            localizer.localize(
                target_code="def f():\n    return 1\n",
                test_code="def test(): pass",
                test_output="err",
                failed_cases=[{"test": "t"}],
            )
            is None
        )

    def test_unparseable_response_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        localizer = fl.FaultLocalizerAgent()
        monkeypatch.setattr(localizer, "_call_llm_with_cache", lambda *a, **k: "不是 JSON")
        assert (
            localizer.localize(
                target_code="def f():\n    return 1\n",
                test_code="def test(): pass",
                test_output="err",
                failed_cases=[{"test": "t"}],
            )
            is None
        )

    def test_prompt_contains_spectral_section(self):
        localizer = fl.FaultLocalizerAgent()
        prompt = localizer._build_prompt(
            target_code="def f():\n    return 1\n",
            test_code="def test(): pass",
            test_output="AssertionError",
            failed_cases=[{"test": "test_f"}],
            spectral_top_k=[{"line": 3, "score": 0.9}, {"line": 5, "score": 0.4}],
        )
        assert "【谱系定位佐证（Ochiai Top-k）】" in prompt
        assert "L3(0.9)" in prompt

    def test_parse_localization_non_dict_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        localizer = fl.FaultLocalizerAgent()
        monkeypatch.setattr(localizer, "_extract_json", lambda raw: [1, 2, 3])
        assert localizer._parse_localization("[]") is None

    def test_normalize_candidate_bad_numeric_field_returns_none(self):
        assert fl.FaultLocalizerAgent._normalize_candidate({"function_name": "f", "line_start": "坏值"}) is None

    def test_constraint_verdict_skips_non_dict_candidates(self):
        loc = {"candidates": [None, {"function_name": "f"}]}
        verdict = fl.fl_constraint_verdict(loc, {"f"})
        assert verdict is not None
        assert verdict["verdict"] == "hit"
        assert verdict["hit_rank"] == 1

    def test_rank_metrics_skips_non_dict_candidates(self):
        metrics = fl.localization_rank_metrics({"candidates": [None, {"function_name": "f"}]}, {"f"})
        assert metrics == {"localization_hit_function_at_3": True, "localization_mrr": 1.0}


@pytest.mark.unit
class TestSemanticCacheDegradation:
    """语义缓存的阈值坏值 / 嵌入缺失 / 零向量 / 跨用户条目 / 节流。"""

    def test_threshold_invalid_env_falls_back(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SEMANTIC_CACHE_THRESHOLD", "高")
        assert sc._semantic_threshold() == pytest.approx(0.92)

    def test_max_entries_invalid_env_falls_back(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SEMANTIC_CACHE_MAX_ENTRIES", "很多")
        assert sc._max_index_entries() == 256

    def test_disabled_upsert_returns_false(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sc, "_semantic_cache_enabled", lambda: False)
        assert SemanticCacheIndex().upsert("/tmp/x.json", "prompt", "response") is False

    def test_find_skips_zero_norm_embedding(self, monkeypatch: pytest.MonkeyPatch):
        index = get_semantic_index()
        index._entries.clear()
        index._entries["/tmp/zero.json"] = _SemanticEntry(
            cache_file="/tmp/zero.json", prompt="p", response="r", embedding=[0.0, 0.0]
        )
        monkeypatch.setattr(sc, "_semantic_cache_enabled", lambda: True)
        monkeypatch.setattr("src.utils.embedding_utils.embed_text", lambda prompt: [1.0, 0.0])
        assert index.find("query") is None, "零向量条目不参与余弦比较（防除零）"

    def test_index_build_glob_oserror_returns_zero(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setattr(sc, "_semantic_cache_enabled", lambda: True)
        monkeypatch.setattr(
            "glob.glob",
            lambda pattern: (_ for _ in ()).throw(OSError("目录不可读（模拟）")),
        )
        assert build_semantic_index_from_cache_dir(str(tmp_path)) == 0

    def test_index_build_skips_other_creator_entries(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog):
        import json
        import logging

        (tmp_path / "entry.json").write_text(
            json.dumps({"prompt": "p", "response": "r", "creator_uid": "other-user"}),
            encoding="utf-8",
        )
        monkeypatch.setattr(sc, "_semantic_cache_enabled", lambda: True)
        monkeypatch.setattr("src.agents.llm_client.cache_creator_ok", lambda stored: False)
        with caplog.at_level(logging.WARNING, logger="src.agents.semantic_cache"):
            added = build_semantic_index_from_cache_dir(str(tmp_path))
        assert added == 0
        assert "跳过 1 条非本用户创建者条目" in caplog.text

    def test_maybe_rebuild_throttled_returns_zero(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sc, "_last_rebuild_ts", time.time())
        assert maybe_rebuild_semantic_index("/tmp/任何目录") == 0

    def test_false_positive_sampling_invalid_env_falls_back(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SEMANTIC_FALSE_POSITIVE_SAMPLING", "十分之一")
        assert sc._false_positive_sampling_rate() == pytest.approx(0.1)


@pytest.mark.unit
class TestConfigManagerWriteGuards:
    """写 .env.local 前的输入校验（拒绝空值 / 换行 / 注释符注入）。"""

    @staticmethod
    def _temp_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, content: str = "") -> Path:
        env_file = tmp_path / ".env.local"
        env_file.write_text(content, encoding="utf-8")
        monkeypatch.setattr(config_manager, "ENV_FILE", env_file)
        return env_file

    def test_duplicate_model_rejected(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        self._temp_env_file(monkeypatch, tmp_path, "LLM_1_MODEL_NAME=dup-model\n")
        assert config_manager.add_llm_config("k", "https://a/v1", "dup-model") is False

    def test_empty_api_key_rejected(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        env_file = self._temp_env_file(monkeypatch, tmp_path)
        assert config_manager.add_llm_config("", "https://a/v1", "new-model") is False
        assert env_file.read_text(encoding="utf-8") == ""

    def test_newline_injection_rejected(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        env_file = self._temp_env_file(monkeypatch, tmp_path)
        assert config_manager.add_llm_config("key", "https://a/v1\nEVIL=1", "new-model") is False
        assert env_file.read_text(encoding="utf-8") == ""

    def test_hash_comment_injection_rejected(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        env_file = self._temp_env_file(monkeypatch, tmp_path)
        assert config_manager.add_llm_config("key#comment", "https://a/v1", "new-model") is False
        assert env_file.read_text(encoding="utf-8") == ""
