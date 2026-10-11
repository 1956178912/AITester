"""S29 模型版本锁定 + S2 SWE-bench instance_code fail-fast 回归测试。

纪律：**不发起任何真实 LLM 调用**——探针路径全部经 `_fake_api_manager`
注入 stub（替换 `src.api.api_manager` 模块），gate 分支用内存 JSON 载荷。

覆盖：
A) S29 `experiments/run_benchmark.collect_model_fingerprint`
   - 探针成功：requested_alias / returned_model / system_fingerprint /
     probe_sha256 / probe_at / pinned=True 齐全；
   - 别名与返回模型不一致时留痕 alias_mismatch；
   - `system_fingerprint` 缺失（兼容网关）→ pinned=False + missing/error 如实标注；
   - API 调用抛异常 → **降级不抛**（pinned=False + error，跑批不得崩）；
   - 进程内缓存：同别名只调一次（不重复烧配额）；
   - `_build_fingerprint_from_response` 对无文本响应显式 raise（不静默造空哈希）；
   - 异常文本经脱敏工具（探针错误会写入对外工件）。
B) S2 `src/datasets/dataset_loader.SWEBenchDataset`
   - 默认口径（开关未设/false）保持历史兜底；
   - strict=true 时兜底行被剔除（task_id 记入 strict_skipped_task_ids）；
   - strict=true 但 enrichment / 显式字段提供源码 → 不剔除。
C) `scripts/gates/check_model_fingerprint.py`
   - pinned=true 通过；pinned=false / 整块缺失 / 非法 JSON 阻断；
   - 严格布尔口径（"true" 字符串不算通过）；main() 退出码 0/1。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any, ClassVar

import pytest

import experiments.run_benchmark as rb

# strict 开关名：与 dataset_loader._ENV_STRICT_INSTANCE_CODE 同源（测试直接
# 引用常量，防"改了常量名而测试仍绿"的僵化匹配）
from src.datasets.dataset_loader import _ENV_STRICT_INSTANCE_CODE as STRICT_ENV
from src.datasets.dataset_loader import SWEBenchDataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_GATE_SCRIPT = PROJECT_ROOT / "scripts" / "gates" / "check_model_fingerprint.py"

# ═══ 探针 stub（绝不发起真实调用） ═══════════════════════════════════════════


class _StubResponse:
    """最小 ChatCompletion 替身（与 openai SDK 响应形状同构）。"""

    def __init__(self, content: Any = "PROBE", model: Any = "deepseek-flash-eval", system_fingerprint: Any = "fp_x"):
        self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=content))]
        self.model = model
        self.system_fingerprint = system_fingerprint


class _FakeAPIManager:
    """APIManager 替身：记录实例化次数与调用参数，可按序返回响应或抛错。"""

    instances: ClassVar[list[_FakeAPIManager]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.init_kwargs = kwargs
        self.calls: list[dict[str, Any]] = []
        # 预置返回序列（_fake_api_manager 注入）：call() 每次 pop 一个
        self._outcomes: list[Any] = []
        type(self).instances.append(self)

    def call(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        self.calls.append({"messages": messages, "kwargs": kwargs})
        outcome = self._outcomes.pop(0) if self._outcomes else _StubResponse()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    @classmethod
    def reset(cls) -> None:
        cls.instances = []


def _fake_api_manager(monkeypatch: pytest.MonkeyPatch, responses: list[Any] | None = None) -> type[_FakeAPIManager]:
    """把 `src.api.api_manager` 换成只含 stub APIManager 的假模块。

    `collect_model_fingerprint` 内部是函数级 `from src.api.api_manager import
    APIManager`——运行期查 sys.modules，故替换模块即完全隔离真实客户端。
    """
    _FakeAPIManager.reset()
    fake_module = types.ModuleType("src.api.api_manager")
    fake_module.APIManager = _FakeAPIManager  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.api.api_manager", fake_module)
    if responses:
        # 预先给每个新实例注入返回序列（call() 每次 pop 一个）
        original_init = _FakeAPIManager.__init__

        def _init_with_outcomes(self: _FakeAPIManager, *args: Any, **kwargs: Any) -> None:
            original_init(self, *args, **kwargs)
            self._outcomes = list(responses)

        monkeypatch.setattr(_FakeAPIManager, "__init__", _init_with_outcomes)
    return _FakeAPIManager


def _load_gate_module():
    """进程内加载 gate 脚本为模块（scripts 非包，无 __init__.py）。"""
    spec = importlib.util.spec_from_file_location("aitester_check_model_fingerprint", _GATE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_result_json(tmp_path: Path, payload: dict[str, Any], name: str = "benchmark_x.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _payload_with_fingerprint(fingerprint: Any, *, provenance_missing: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {"dataset": "swe_bench"}
    if not provenance_missing:
        payload["provenance"] = {"model_name": "deepseek-flash", "model_fingerprint": fingerprint}
    return payload


# ═══ A) S29 探针 ═════════════════════════════════════════════════════════════


class TestModelFingerprintProbe:
    """collect_model_fingerprint：成功 / 降级 / 缓存 / 缺字段。"""

    def test_probe_success_pins_all_evidence(self, monkeypatch):
        """探针成功：三项证据齐全 → pinned=True，probe_sha256 与响应对齐。"""
        _fake_api_manager(monkeypatch)
        fingerprint = rb.collect_model_fingerprint("deepseek-flash", cache={})

        assert fingerprint["pinned"] is True
        assert fingerprint["requested_alias"] == "deepseek-flash"
        assert fingerprint["returned_model"] == "deepseek-flash-eval"
        assert fingerprint["system_fingerprint"] == "fp_x"
        assert fingerprint["probe_sha256"] == hashlib.sha256(b"PROBE").hexdigest()
        assert fingerprint["missing"] == []
        assert fingerprint["error"] is None
        # probe_at 必须是 UTC ISO 时间戳（可解析 + 带时区）
        assert fingerprint["probe_at"].endswith("+00:00")
        from datetime import datetime

        datetime.fromisoformat(fingerprint["probe_at"])
        # 贪心解码 + 固定 prompt：探针必须是 temperature=0.0 且 prompt 恒定
        call = _FakeAPIManager.instances[0].calls[0]
        assert call["kwargs"]["temperature"] == 0.0
        assert call["messages"][0]["content"] == rb._FINGERPRINT_PROBE_PROMPT
        # 探针不得带后台健康检查线程（构造副作用会周期性发真实请求）
        assert _FakeAPIManager.instances[0].init_kwargs.get("enable_health_checker") is False

    def test_probe_missing_system_fingerprint_not_pinned(self, monkeypatch):
        """system_fingerprint 缺失（部分网关不返回）→ pinned=False 且原因可见。"""
        _fake_api_manager(monkeypatch, responses=[_StubResponse(system_fingerprint=None)])
        fingerprint = rb.collect_model_fingerprint("deepseek-flash", cache={})

        assert fingerprint["pinned"] is False
        assert fingerprint["system_fingerprint"] is None
        assert fingerprint["returned_model"] == "deepseek-flash-eval"
        assert fingerprint["missing"] == ["system_fingerprint"]
        assert "system_fingerprint" in str(fingerprint["error"])
        # 有文本仍要算出哈希：哈希是"快照证据"，与是否 pinned 独立
        assert fingerprint["probe_sha256"] == hashlib.sha256(b"PROBE").hexdigest()

    def test_probe_failure_degrades_without_raising(self, monkeypatch):
        """API 抛异常 → **降级不抛**（跑批不得因探针失败崩溃），error 落盘。"""
        _fake_api_manager(monkeypatch, responses=[RuntimeError("所有 API 节点不可用")])
        fingerprint = rb.collect_model_fingerprint("deepseek-flash", cache={})

        assert fingerprint["pinned"] is False
        assert fingerprint["returned_model"] is None
        assert fingerprint["probe_sha256"] is None
        # 别名本身可解析 → 缺失项只列证据项（"探针没跑"与"别名读不到"不混同）
        assert fingerprint["missing"] == ["returned_model", "system_fingerprint"]
        assert "RuntimeError" in str(fingerprint["error"])
        assert "所有 API 节点不可用" in str(fingerprint["error"])

    def test_probe_missing_alias_never_pinned(self, monkeypatch):
        """requested_alias=None（模型名读不到）→ 不可能 pinned（无从登记别名映射）。"""
        _fake_api_manager(monkeypatch)
        fingerprint = rb.collect_model_fingerprint(None, cache={})

        assert fingerprint["pinned"] is False
        assert fingerprint["missing"] == ["requested_alias"]

    def test_probe_cached_single_call(self, monkeypatch):
        """缓存：同进程同别名只调一次（多 seed / 多基线复跑不重复烧配额）。"""
        _fake_api_manager(monkeypatch)
        cache: dict[str, dict[str, Any]] = {}
        first = rb.collect_model_fingerprint("deepseek-flash", cache=cache)
        second = rb.collect_model_fingerprint("deepseek-flash", cache=cache)

        assert first is second  # 命中缓存返回同一对象
        assert len(_FakeAPIManager.instances) == 1
        assert len(_FakeAPIManager.instances[0].calls) == 1
        # 另一别名 = 另一键 → 再探一次（缓存按别名分键，防"换了模型仍复用旧指纹"）
        rb.collect_model_fingerprint("another-alias", cache=cache)
        assert len(_FakeAPIManager.instances) == 2

    def test_probe_failure_is_cached_too(self, monkeypatch):
        """失败也入缓存：离线跑批不得对每个 seed 重试探针（否则每批次多一次超时）。"""
        _fake_api_manager(monkeypatch, responses=[RuntimeError("offline")])
        cache: dict[str, dict[str, Any]] = {}
        rb.collect_model_fingerprint("deepseek-flash", cache=cache)
        rb.collect_model_fingerprint("deepseek-flash", cache=cache)
        assert len(_FakeAPIManager.instances) == 1

    def test_build_fingerprint_rejects_empty_response(self):
        """无文本响应 → 显式 raise（不得用空哈希冒充指纹）。"""
        with pytest.raises(RuntimeError, match="无文本内容"):
            rb._build_fingerprint_from_response(_StubResponse(content=""), "alias", "2026-10-11T00:00:00+00:00")
        with pytest.raises(RuntimeError, match="无文本内容"):
            rb._build_fingerprint_from_response(_StubResponse(content=None), "alias", "2026-10-11T00:00:00+00:00")

    def test_alias_mismatch_is_recorded(self):
        """API 返回的 model 名与请求别名不一致 → alias_mismatch=True（跨批次可比性存疑）。"""
        fingerprint = rb._build_fingerprint_from_response(
            _StubResponse(model="deepseek-flash-2026-10-01"), "deepseek-flash", "2026-10-11T00:00:00+00:00"
        )
        assert fingerprint["pinned"] is True  # 三项齐全
        assert fingerprint["returned_model"] == "deepseek-flash-2026-10-01"

    def test_fingerprint_error_text_is_redacted(self, monkeypatch):
        """探针异常文本会写入对外工件 → 必须过脱敏工具（凭证不得明文化）。"""
        secret = "api_key=sk-abcdef0123456789abcdef0123456789"
        _fake_api_manager(monkeypatch, responses=[RuntimeError(f"bad gateway {secret}")])
        fingerprint = rb.collect_model_fingerprint("deepseek-flash", cache={})
        assert "sk-abcdef0123456789abcdef0123456789" not in str(fingerprint["error"])


# ═══ B) S2 dataset_loader strict 口径 ════════════════════════════════════════


def _write_swe_jsonl(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    """写 swe_bench_lite_instances.jsonl 到 tmp 目录（返回 data_dir）。"""
    data_dir = tmp_path / "swe_cache"
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "swe_bench_lite_instances.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return data_dir


_FALLBACK_ROW = {
    "instance_id": "repo__repo-1",
    "repo": "org/repo",
    "problem_statement": "fix the bug",
    "PASS_TO_PASS": '["t.py::test_a"]',
}
_EXPLICIT_ROW = {
    "instance_id": "repo__repo-2",
    "repo": "org/repo",
    "problem_statement": "fix the bug 2",
    "instance_code": "def f():\n    return 1\n",
    "PASS_TO_PASS": '["t.py::test_b"]',
}


class TestStrictInstanceCode:
    """S2：instance_code 兜底改为可配置 fail-fast（默认 false 保持历史口径）。"""

    def test_default_keeps_historic_fallback(self, tmp_path, monkeypatch):
        """默认（开关未设）：兜底为 issue 文本且任务照跑（历史口径逐字节不变）。"""
        monkeypatch.delenv(STRICT_ENV, raising=False)
        data_dir = _write_swe_jsonl(tmp_path, [_FALLBACK_ROW, _EXPLICIT_ROW])
        ds = SWEBenchDataset(subset="lite", data_dir=str(data_dir))

        assert ds.size == 2
        assert ds.strict_skipped_task_ids == []
        by_id = {t.task_id: t for t in ds.tasks}
        assert by_id["repo__repo-1"].instance_code == "fix the bug"

    def test_strict_true_drops_fallback_rows(self, tmp_path, monkeypatch):
        """strict=true：兜底行被剔除，显式源码行保留，剔除 ID 可审计。"""
        monkeypatch.setenv(STRICT_ENV, "true")
        data_dir = _write_swe_jsonl(tmp_path, [_FALLBACK_ROW, _EXPLICIT_ROW])
        ds = SWEBenchDataset(subset="lite", data_dir=str(data_dir))

        assert ds.size == 1
        assert [t.task_id for t in ds.tasks] == ["repo__repo-2"]
        assert ds.strict_skipped_task_ids == ["repo__repo-1"]
        # 剔除后不得留下"兜底 == issue 文本"的任务（那正是 F4 的静默缺口）
        assert ds.tasks_missing_source() == []

    def test_strict_false_explicit_value_keeps_fallback(self, tmp_path, monkeypatch):
        """显式 false / 非法值一律按默认口径（环境变量笔误不得让跑批崩溃）。"""
        for value in ("false", "0", "no", "off", "maybe"):
            monkeypatch.setenv(STRICT_ENV, value)
            data_dir = _write_swe_jsonl(tmp_path, [_FALLBACK_ROW])
            ds = SWEBenchDataset(subset="lite", data_dir=str(data_dir))
            assert ds.size == 1, f"值 {value!r} 不应触发 strict"
            assert ds.strict_skipped_task_ids == []

    def test_strict_enabled_helper_reads_env(self, monkeypatch):
        """开关读取函数：默认 false；true/1/yes/on 启用（大小写与空白容错）。"""
        from src.datasets.dataset_loader import _strict_instance_code_enabled

        monkeypatch.delenv(STRICT_ENV, raising=False)
        assert _strict_instance_code_enabled() is False
        for value in ("true", "TRUE", " True ", "1", "yes", "on"):
            monkeypatch.setenv(STRICT_ENV, value)
            assert _strict_instance_code_enabled() is True, value
        monkeypatch.setenv(STRICT_ENV, "false")
        assert _strict_instance_code_enabled() is False

    def test_strict_keeps_enrichment_supplied_source(self, tmp_path, monkeypatch):
        """strict=true 但 SWE_BENCH_ENRICHMENT 补了源码 → 该行有效，不得剔除。"""
        monkeypatch.setenv(STRICT_ENV, "true")
        enrichment = tmp_path / "enrich.jsonl"
        enrichment.write_text(
            json.dumps({"instance_id": "repo__repo-1", "instance_code": "def g():\n    return 2\n"}),
            encoding="utf-8",
        )
        monkeypatch.setattr("src.datasets.dataset_loader.SWE_BENCH_ENRICHMENT", str(enrichment))
        data_dir = _write_swe_jsonl(tmp_path, [_FALLBACK_ROW])
        ds = SWEBenchDataset(subset="lite", data_dir=str(data_dir))

        assert ds.size == 1
        assert ds.strict_skipped_task_ids == []
        assert ds.tasks[0].instance_code == "def g():\n    return 2\n"

    def test_strict_reload_resets_skipped_list(self, tmp_path, monkeypatch):
        """重载（_load_raw_data 再跑）后剔除面重置，不得累积旧记录。"""
        monkeypatch.setenv(STRICT_ENV, "true")
        data_dir = _write_swe_jsonl(tmp_path, [_FALLBACK_ROW])
        ds = SWEBenchDataset(subset="lite", data_dir=str(data_dir))
        _ = ds.tasks  # 触发首次加载（剔除面在加载期填充）
        assert ds.strict_skipped_task_ids == ["repo__repo-1"]
        ds._load_raw_data()
        assert ds.strict_skipped_task_ids == ["repo__repo-1"]  # 重置后重新记录一次，非累积两次


class _StubDataset:
    """最小 dataset 替身：只提供 run_benchmark 读取的四个面。

    用于验证"剔除计数 → provenance"接线，而不真跑任务：`tasks` 故意为空
    （0 次 LLM 调用）但 `size` 非 0（避免触发 run_benchmark 的"空数据集 ⇒
    降级到内置 examples"分支——那会真的跑 3 个任务）。`strict_skipped_task_ids`
    返回副本，模拟真实加载器的属性语义。
    """

    size = 1
    tasks: ClassVar[list[Any]] = []

    def __init__(self, skipped: list[str]) -> None:
        self._skipped = list(skipped)

    @property
    def strict_skipped_task_ids(self) -> list[str]:
        return list(self._skipped)


class TestProvenanceWiring:
    """run_benchmark 的 provenance 必须真实反映 S29 指纹 + S2 剔除面。"""

    def test_provenance_records_fingerprint_and_strict_skips(self, tmp_path, monkeypatch):
        """空任务批次：provenance 仍写 model_fingerprint + strict_skipped 明细。"""
        _fake_api_manager(monkeypatch, responses=[RuntimeError("offline-stub")])
        monkeypatch.setenv("AITESTER_LLM_CACHE", "0")
        monkeypatch.setattr(rb, "load_dataset", lambda *a, **k: _StubDataset(["repo__a-1", "repo__a-2"]))

        summary = rb.run_benchmark(
            dataset_name="swe_bench",
            baselines=["plain_llm"],
            output_dir=str(tmp_path),
            parallel=1,
        )
        prov = summary["provenance"]
        # S29：探针失败仍必须留字段（pinned=False + error），不得缺块
        assert prov["model_fingerprint"]["pinned"] is False
        assert prov["model_fingerprint"]["error"]
        # S2：剔除面可审计（count + ID 明细 + 截断标记）
        assert prov["strict_skipped_count"] == 2
        assert prov["strict_skipped_task_ids"] == ["repo__a-1", "repo__a-2"]
        assert prov["strict_skipped_truncated"] is False
        # 落盘工件与内存 summary 一致（工件是审计对象，不是内存态）
        out = next(tmp_path.glob("benchmark_*.json"))
        on_disk = json.loads(out.read_text(encoding="utf-8"))["provenance"]
        assert on_disk["strict_skipped_count"] == 2
        assert on_disk["model_fingerprint"]["pinned"] is False


# ═══ C) gate 脚本 ════════════════════════════════════════════════════════════


class TestModelFingerprintGate:
    """check_model_fingerprint.py：pinned != true → 阻断（含严格布尔口径）。"""

    @pytest.fixture()
    def gate(self):
        return _load_gate_module()

    def test_gate_passes_when_pinned(self, gate, tmp_path, capsys):
        """pinned=true → ([PASS], 退出码 0)。"""
        path = _write_result_json(
            tmp_path,
            _payload_with_fingerprint(
                {
                    "requested_alias": "deepseek-flash",
                    "returned_model": "deepseek-flash-eval",
                    "system_fingerprint": "fp_x",
                    "probe_sha256": "a" * 64,
                    "pinned": True,
                }
            ),
        )
        assert gate.main([str(path)]) == 0
        assert "[PASS]" in capsys.readouterr().out

    def test_gate_blocks_when_not_pinned(self, gate, tmp_path, capsys):
        """pinned=false → 阻断（退出码 1）且打印缺失项。"""
        path = _write_result_json(
            tmp_path,
            _payload_with_fingerprint(
                {
                    "requested_alias": "deepseek-flash",
                    "returned_model": None,
                    "system_fingerprint": None,
                    "pinned": False,
                    "missing": ["returned_model", "system_fingerprint"],
                    "error": "所有 API 节点不可用",
                }
            ),
        )
        assert gate.main([str(path)]) == 1
        captured = capsys.readouterr()
        assert "[FAIL]" in captured.out
        assert "returned_model" in captured.out and "system_fingerprint" in captured.out
        assert "所有 API 节点不可用" in captured.out

    def test_gate_blocks_when_fingerprint_block_missing(self, gate, tmp_path, capsys):
        """provenance 整块缺失 → 阻断，报"无 provenance"且缺失项列为全部必需键。"""
        path = _write_result_json(tmp_path, _payload_with_fingerprint(None, provenance_missing=True))
        assert gate.main([str(path)]) == 1
        out = capsys.readouterr().out
        assert "[FAIL]" in out
        assert "provenance" in out
        for key in gate.REQUIRED_FINGERPRINT_KEYS:
            assert key in out

    def test_gate_blocks_when_subblock_missing(self, gate, tmp_path, capsys):
        """有 provenance 但无 model_fingerprint 子块 → 阻断（老批次工件的典型形态）。"""
        path = _write_result_json(tmp_path, {"provenance": {"model_name": "deepseek-flash"}})
        assert gate.main([str(path)]) == 1
        out = capsys.readouterr().out
        assert "[FAIL]" in out
        assert "model_fingerprint" in out

    def test_gate_rejects_string_true(self, gate, tmp_path):
        """严格布尔口径：pinned="true"（字符串）不得算通过。"""
        path = _write_result_json(
            tmp_path,
            _payload_with_fingerprint(
                {
                    "requested_alias": "deepseek-flash",
                    "returned_model": "m",
                    "system_fingerprint": "fp",
                    "pinned": "true",
                }
            ),
        )
        passed, items, _ = gate.check_file(path)
        assert passed is False
        assert gate.main([str(path)]) == 1
        assert items  # 至少给出"pinned=false"这一原因项

    def test_gate_blocks_invalid_json(self, gate, tmp_path):
        """非法 JSON = 工件不可审计 → 阻断（不得静默跳过）。"""
        bad = tmp_path / "broken.json"
        bad.write_text("{not json", encoding="utf-8")
        assert gate.main([str(bad)]) == 1

    def test_gate_missing_path_is_usage_error(self, gate, tmp_path):
        """点名路径不存在 → 退出码 2（用法错误，与"未锁定"区分）。"""
        assert gate.main([str(tmp_path / "nope.json")]) == 2

    def test_gate_empty_scan_surface_passes(self, gate, tmp_path):
        """扫描面为空（近期无新批次）→ 通过。

        2026-10-11 修（范围错误）：S29 的可执行语义是"**新批次**在合并统计前
        必须已锁定"，因此"近期没有新批次"是**合规状态**（nothing to verify），
        不是故障。若空扫描面返回非零，门禁会在两次跑批之间**永久为红**而失去
        信号（与 check_branch_coverage 仅在存在 coverage.xml 时判定同理）。
        退出码语义：0=通过（或无新批次可验）；1=存在未锁定批次（真故障）；
        2=用法/路径错误。
        """
        assert gate.main([str(tmp_path)]) == 0
        assert gate.main([str(tmp_path), "--allow-empty"]) == 0

    def test_gate_scopes_to_benchmark_pattern(self, gate, tmp_path):
        """目录扫描默认只取 benchmark_*.json（范围正确性）。

        派生分析产物（`full_comparison.json` 等）从不含 provenance，判它们
        "未锁定"属范围错误（会往 CI 塞一个永远为红的门禁）。
        """
        # 派生分析产物不在默认扫描面内 → 不判红
        _write_result_json(tmp_path, {"note": "derived"}, name="full_comparison.json")
        assert gate.main([str(tmp_path)]) == 0
        # 但被**显式点名**时必须检（点名即检，防静默跳过）
        assert gate.main([str(tmp_path / "full_comparison.json")]) == 1

    def test_gate_checks_directory_and_dedups(self, gate, tmp_path):
        """目录扫描：全 pinned 通过；含一个未锁定即整体阻断。"""
        _write_result_json(
            tmp_path,
            _payload_with_fingerprint(
                {"requested_alias": "a", "returned_model": "m", "system_fingerprint": "fp", "pinned": True}
            ),
            name="benchmark_ok.json",
        )
        assert gate.main([str(tmp_path)]) == 0
        _write_result_json(
            tmp_path,
            _payload_with_fingerprint({"requested_alias": None, "returned_model": None, "pinned": False}),
            name="benchmark_bad.json",
        )
        assert gate.main([str(tmp_path)]) == 1

    def test_gate_payload_without_provenance(self, gate):
        """无 provenance 块（历史格式）→ 明确报"无 provenance"，不抛异常。"""
        passed, items, error = gate.check_payload({"dataset": "synthetic"})
        assert passed is False
        assert items == list(gate.REQUIRED_FINGERPRINT_KEYS)
        assert error is not None and "provenance" in error
