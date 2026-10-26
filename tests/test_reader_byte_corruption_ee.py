"""EE（2026-10-27）：读侧「损坏」判定停在 JSON 语法层——字节层损坏不得击穿降级契约。

缺陷族（自查实证）：所有 JSON/JSONL 读侧只捕获 ``json.JSONDecodeError``
（部分另捕 ``OSError``）。``json.JSONDecodeError`` 只在**已解码文本**上触发；
字节层损坏（部分写入截断多字节字符、编辑器以 GBK 保存、坏扇区）在
**解码时**抛 ``UnicodeDecodeError``，穿透文档承诺：

- 行级读侧：「坏行跳过、其余照常」对坏 JSON 成立，对坏字节失效——
  ``for raw_line in f`` 的迭代器在进入行内 try 之前解码，一行坏字节
  拖垮整份文件（SWE-bench 主数据 / 补充文件 / ULT / BugsInPy /
  trace 可视化 / OTel 导出 / 编排搜索 trace）；
- 整文件读侧：「缺失 / 损坏 → 空列表 / 空库 / 跳过，不阻断」同样失效
  （failure_kb、strategy_bank 读侧与写侧、rag 兜底材料源、
  executor_repo 官方报告、Defects4J info.json）。

每例先写健康行/健康文件作对照，证明失败不是「文件根本读不到」；行级
用例断言**坏行前后**的健康记录都在——只断言「不抛异常」会放过
「整份文件被当空」的静默降级。``errors="replace"`` 不是修法：替换字符
可能把坏字节洗成一份可被 ``json.loads`` 接受的错数据（静默串味），
故行级读侧必须逐行严格解码。

策略库写侧（``record_strategy_outcome``）单列：它已有「读不懂 ⇒ 不覆写」
的 fail-closed 契约，坏字节必须走同一条路——原文件原样保留。
"""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

from src.agents.executor_repo import RepoExecutor
from src.agents.failure_kb import load_knowledge_base
from src.datasets.dataset_defects4j import Defects4JPYDataset
from src.datasets.dataset_loader import SWEBenchDataset, load_dataset
from src.datasets.dataset_realbugs import BugsInPyDataset
from src.graph.orchestration_search import _read_trace_records
from src.graph.rag import _iter_candidate_docs
from src.observability.otel_export import export_trace_jsonl
from src.tools.strategy_bank import _load_bank, record_strategy_outcome
from src.utils.trace_viz import _parse_jsonl

_BAD = b"\xff\xfe"  # 非 UTF-8 起始字节：解码期即失败，不进入 json.loads


def _jsonl(*rows: dict) -> bytes:
    return b"".join(json.dumps(r, ensure_ascii=False).encode("utf-8") + b"\n" for r in rows)


class TestLineReadersKeepLineIsolation:
    """行级读侧：一行坏字节只损失该行，前后健康行照常加载。"""

    def test_swe_bench_main_jsonl_keeps_healthy_lines(self, tmp_path, caplog):
        """主数据 JSONL：坏字节行被跳过（含行号告警），t1/t3 仍加载。"""
        (tmp_path / "swe_bench_instances.jsonl").write_bytes(
            _jsonl({"instance_id": "t1", "repository": "r1"})
            + _BAD
            + b"\n"
            + _jsonl({"instance_id": "t3", "repository": "r3"})
        )
        ds = SWEBenchDataset()
        with patch.object(ds, "data_dir", str(tmp_path)), caplog.at_level(logging.WARNING):
            ds._load_raw_data()
            ds._loaded = True
        assert ds.size == 2
        assert {t.task_id for t in ds.tasks} == {"t1", "t3"}
        assert "第 2 行" in caplog.text
        assert "UTF-8" in caplog.text

    def test_swe_bench_enrichment_keeps_healthy_lines(self, tmp_path, caplog):
        """源码补充文件：坏字节行跳过，其余 instance_id 仍进入映射。"""
        path = tmp_path / "enrichment.jsonl"
        path.write_bytes(
            _jsonl({"instance_id": "t1", "instance_code": "def f(): pass"})
            + _BAD
            + b"\n"
            + _jsonl({"instance_id": "t2", "instance_code": "def g(): pass"})
        )
        with caplog.at_level(logging.WARNING):
            enriched = SWEBenchDataset._load_enrichment(str(path))
        assert set(enriched) == {"t1", "t2"}
        assert enriched["t2"]["instance_code"] == "def g(): pass"
        assert "第 2 行" in caplog.text

    def test_ult_jsonl_keeps_healthy_lines(self, tmp_path):
        """ULT 逐行 manifest：坏字节行跳过，其余函数仍成为任务。"""
        path = tmp_path / "ult_manifest.jsonl"
        path.write_bytes(
            _jsonl({"function_name": "f1", "source_code": "def f1():\n    return 1\n"})
            + _BAD
            + b"\n"
            + _jsonl({"function_name": "f2", "source_code": "def f2():\n    return 2\n"})
        )
        ds = load_dataset("ult", data_dir=str(path))
        assert ds.size == 2
        assert {t.task_id for t in ds.tasks} == {"ult__f1", "ult__f2"}

    def test_ult_array_with_bad_bytes_degrades_to_empty(self, tmp_path, caplog):
        """ULT 顶层数组（官方格式）：单个坏字节 → 整份降级为空 + 告警，不抛异常。"""
        path = tmp_path / "ULT.jsonl"
        path.write_bytes(
            b"["
            + json.dumps({"function_name": "f1", "source_code": "def f1():\n    return 1\n"}).encode()
            + b", "
            + _BAD
            + b"]"
        )
        with caplog.at_level(logging.WARNING):
            ds = load_dataset("ult", data_dir=str(path))
        assert ds.size == 0
        assert "解析失败" in caplog.text
        assert "UTF-8" in caplog.text

    def test_realbugs_manifest_keeps_healthy_lines(self, tmp_path, caplog):
        """BugsInPy manifest：坏字节行计入跳过，健康 bug 记录仍加载。"""
        row = {"project": "p", "bug_id": "1", "buggy_code": "def f(): pass", "fixed_code": "def f(): return 1"}
        (tmp_path / "bugs_in_py_manifest.jsonl").write_bytes(
            _jsonl(row) + _BAD + b"\n" + _jsonl({**row, "bug_id": "3"})
        )
        with caplog.at_level(logging.WARNING):
            ds = BugsInPyDataset(data_dir=str(tmp_path))
            assert len(ds.tasks) == 2
        assert "第 2 行" in caplog.text

    def test_trace_viz_jsonl_keeps_healthy_records(self, tmp_path, caplog):
        """trace 可视化：坏字节行跳过，其余节点记录仍可渲染。"""
        path = tmp_path / "t.trace.jsonl"
        path.write_bytes(b'{"event": "node", "ts": 1.0}\n' + _BAD + b"\n")
        with caplog.at_level(logging.WARNING):
            records = _parse_jsonl(str(path))
        assert [r["event"] for r in records] == ["node"]
        assert "第 2 行" in caplog.text

    def test_otel_export_skips_bad_bytes_line(self, tmp_path, caplog):
        """OTel 导出：坏字节行跳过，task_start 仍导出为根 span。"""
        path = tmp_path / "t.trace.jsonl"
        start = {"event": "task_start", "task": "t", "ts": 1.0, "run_id": "a" * 32, "span_id": "b" * 16}
        path.write_bytes(_jsonl(start) + _BAD + b"\n")
        with caplog.at_level(logging.WARNING):
            spans = export_trace_jsonl(str(path))
        assert [s["name"] for s in spans] == ["task_task_start"]
        assert "第 2 行" in caplog.text

    def test_orchestration_trace_reader_keeps_healthy_records(self, tmp_path, caplog):
        """编排搜索的 trace 读侧：观测层「不阻断」对坏字节同样成立。"""
        path = tmp_path / "task1.trace.jsonl"
        path.write_bytes(b'{"event": "node", "ts": 1.0}\n' + _BAD + b'\n{"event": "task_end", "ts": 2.0}\n')
        with caplog.at_level(logging.WARNING):
            records = _read_trace_records(str(tmp_path), "task1")
        assert [r["event"] for r in records] == ["node", "task_end"]
        assert "第 2 行" in caplog.text


class TestWholeFileReadersUseDocumentedFallback:
    """整文件读侧：坏字节 ⇒ 文档承诺的降级值 / fail-closed，不抛异常。"""

    def test_failure_kb_corrupt_bytes_degrades_to_empty(self, tmp_path, caplog):
        path = tmp_path / "kb.json"
        path.write_bytes(_BAD)
        with caplog.at_level(logging.WARNING):
            assert load_knowledge_base(str(path)) == []
        assert "降级为空" in caplog.text

    def test_strategy_bank_read_corrupt_bytes_degrades_to_empty(self, tmp_path, caplog):
        path = tmp_path / "bank.json"
        path.write_bytes(_BAD)
        with caplog.at_level(logging.WARNING):
            assert _load_bank(str(path)) == {"strategies": []}
        assert "降级为空库" in caplog.text

    def test_strategy_bank_write_corrupt_bytes_does_not_overwrite(self, tmp_path, caplog):
        """写侧 fail-closed：读不懂的库文件原样保留，本次追加跳过。"""
        path = tmp_path / "bank.json"
        path.write_bytes(_BAD)
        with caplog.at_level(logging.WARNING):
            record_strategy_outcome(("syntax", None, False), "s1", True, path=str(path))
        assert path.read_bytes() == _BAD
        assert "跳过本次 outcome 追加" in caplog.text

    def test_rag_docs_skip_corrupt_bytes_file(self, tmp_path, monkeypatch):
        """RAG 兜底材料源：坏字节缓存文件跳过，健康文件仍入候选。"""
        import src.graph.rag as rag

        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path))
        monkeypatch.setattr(rag, "RAG_PERSIST_PATH", "")
        (tmp_path / "bad.json").write_bytes(_BAD)
        (tmp_path / "good.json").write_text(json.dumps({"prompt": "hello", "response": "world"}), encoding="utf-8")
        docs = _iter_candidate_docs()
        assert [doc_id for _src, doc_id, _text in docs] == ["good.json"]
        assert "hello" in docs[0][2]

    def test_rag_data_source_skips_corrupt_bytes_file(self, tmp_path, monkeypatch):
        """RAG 持久化案例源（rag_data 分支）：坏字节文件跳过，健康案例仍入候选。"""
        import src.graph.rag as rag

        cache_dir = tmp_path / "cache"
        rag_dir = tmp_path / "rag"
        cache_dir.mkdir()
        rag_dir.mkdir()
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(cache_dir))
        monkeypatch.setattr(rag, "RAG_PERSIST_PATH", str(rag_dir))
        (rag_dir / "bad.json").write_bytes(_BAD)
        (rag_dir / "good.json").write_text(json.dumps({"case": "x"}), encoding="utf-8")
        docs = _iter_candidate_docs()
        assert [(src, doc_id) for src, doc_id, _text in docs] == [("rag_data", "good.json")]

    def test_executor_repo_skips_corrupt_bytes_report(self, tmp_path):
        """M3 官方报告扫描：坏字节文件跳过，健康报告仍命中 instance。"""
        (tmp_path / "bad.json").write_bytes(_BAD)
        report = {"instance_id": "i1", "resolved": True, "tests_status": {}}
        (tmp_path / "good.json").write_text(json.dumps(report), encoding="utf-8")
        assert RepoExecutor._find_official_instance_report(str(tmp_path), "i1") == report

    def test_defects4j_corrupt_info_json_skips_version(self, tmp_path, caplog):
        """Defects4J 版本元数据坏字节 ⇒ 跳过该版本（返回空数据集），不中断列举。"""
        version_dir = tmp_path / "projects" / "requests" / "v1"
        (version_dir / "buggy").mkdir(parents=True)
        (version_dir / "buggy" / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        (version_dir / "info.json").write_bytes(_BAD)
        with caplog.at_level(logging.WARNING):
            ds = Defects4JPYDataset(data_dir=str(tmp_path))
            assert ds.tasks == []
        assert "info.json 解析失败" in caplog.text
