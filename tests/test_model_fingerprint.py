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
import subprocess
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


def _gate_rel_key(gate: Any, path: Path) -> str:
    """豁免登记键与门禁同源（相对路径口径只由门禁定义，测试不手抄）。"""
    return gate._rel_key(Path(path))


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
                {"requested_alias": "deepseek-flash", "returned_model": "m", "system_fingerprint": "fp", "pinned": True}
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

    # ── BZ 轮（2026-10-23）：预指纹时代历史批次的按名豁免 + 漂移检查 ──────
    # 背景：2 天 mtime 窗口在 fresh clone（CI）上失效（checkout 刷新全部
    # mtime），为测试契约入库的预指纹历史工件会被当作"新批次"要求
    # pinned=true；豁免走 json-strict 同纪律（登记理由 + 漂移检查）。

    def test_gate_exempts_registered_pre_fingerprint_batch(self, gate, tmp_path, monkeypatch, capsys):
        """登记在豁免表里的未锁定工件：不阻断，且 [EXEMPT] 带理由。"""
        path = _write_result_json(tmp_path, {"dataset": "examples", "results": {}}, name="benchmark_old.json")
        monkeypatch.setattr(gate, "_PRE_FINGERPRINT_EXEMPT", {_gate_rel_key(gate, path): "测试豁免理由"})
        assert gate.main([str(tmp_path)]) == 0
        out = capsys.readouterr().out
        assert "[EXEMPT]" in out and "测试豁免理由" in out
        assert "另有 1 个预指纹时代历史批次按名豁免" in out
        assert "[FAIL]" not in out

    def test_gate_exemption_does_not_mask_other_batches(self, gate, tmp_path, monkeypatch):
        """豁免只作用于登记的那一份：同目录另一份未锁定批次仍阻断。"""
        exempt = _write_result_json(tmp_path, {"dataset": "examples", "results": {}}, name="benchmark_old.json")
        _write_result_json(tmp_path, {"dataset": "synthetic", "results": {}}, name="benchmark_new.json")
        monkeypatch.setattr(gate, "_PRE_FINGERPRINT_EXEMPT", {_gate_rel_key(gate, exempt): "测试豁免理由"})
        assert gate.main([str(tmp_path)]) == 1

    def test_gate_exemption_drift_when_unreadable(self, gate, tmp_path, monkeypatch, capsys):
        """豁免登记项不可解析 ⇒ 漂移失败（豁免不能把坏工件变成干净）。"""
        path = tmp_path / "benchmark_broken.json"
        path.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(gate, "_PRE_FINGERPRINT_EXEMPT", {_gate_rel_key(gate, path): "测试豁免理由"})
        assert gate.main([str(tmp_path)]) == 1
        assert "工件不可审计" in capsys.readouterr().err

    def test_gate_exemption_drift_when_pinned(self, gate, tmp_path, monkeypatch, capsys):
        """豁免登记项已 pinned=true ⇒ 漂移失败（豁免不再需要，应移除登记）。"""
        path = _write_result_json(
            tmp_path,
            _payload_with_fingerprint(
                {"requested_alias": "deepseek-flash", "returned_model": "m", "system_fingerprint": "fp", "pinned": True}
            ),
            name="benchmark_now_pinned.json",
        )
        monkeypatch.setattr(gate, "_PRE_FINGERPRINT_EXEMPT", {_gate_rel_key(gate, path): "测试豁免理由"})
        assert gate.main([str(tmp_path)]) == 1
        assert "豁免漂移" in capsys.readouterr().err

    def test_gate_exemption_drift_when_missing(self, gate, tmp_path, monkeypatch, capsys):
        """豁免登记项的文件消失 ⇒ 漂移失败（豁免失去对象）。"""
        monkeypatch.setattr(
            gate,
            "_PRE_FINGERPRINT_EXEMPT",
            {str(tmp_path / "benchmark_gone.json"): "测试豁免理由"},
        )
        assert gate.main([str(tmp_path)]) == 1
        assert "豁免漂移" in capsys.readouterr().err

    def test_gate_exempt_registry_entries_are_reasoned(self, gate):
        """豁免登记表每条带理由；表为空是合法态——CI 轮（2026-10-24）非 DeepSeek
        历史数据清除后，唯一的预指纹条目随文件一并删除（「文件消失 ⇒ 删登记」），
        空表 + 门禁 rc=0 是该机制的正常终态，不再是「机制没接线」。"""
        assert all(reason.strip() for reason in gate._PRE_FINGERPRINT_EXEMPT.values())

    def test_gate_rel_key_matches_registry_keys(self, gate):
        """相对键口径与登记表同源：绝对路径、仓库相对路径都收敛到登记键。

        少了这条锁，`_rel_key` 的根目录写错也能全绿——登记表遍历不经过它。
        """
        for key in gate._PRE_FINGERPRINT_EXEMPT:
            assert gate._rel_key(PROJECT_ROOT / key) == key
            assert gate._rel_key(Path(key)) == key

    def test_gate_exempt_registry_is_healthy_on_disk(self, gate):
        """真实登记表零漂移；每条都是盘上存在、确无指纹块的历史工件。

        CI 轮（2026-10-24）起条目数为 0（唯一条目随非 DeepSeek 历史数据清除
        一并删除）；锁改为双向：条目为 0 时登记机制仍须输出空漂移清单，
        条目非 0 时逐条做盘上存在与无指纹块核验——新增豁免必须同步改本锁。
        """
        assert gate._PRE_FINGERPRINT_EXEMPT == {} or len(gate._PRE_FINGERPRINT_EXEMPT) >= 1
        assert gate.exemption_drift_failures() == []
        for key in gate._PRE_FINGERPRINT_EXEMPT:
            payload = json.loads((PROJECT_ROOT / key).read_text(encoding="utf-8"))
            provenance = payload.get("provenance")
            assert not (isinstance(provenance, dict) and provenance.get("model_fingerprint")), (
                f"{key}: 登记为预指纹时代工件，但含 model_fingerprint 块"
            )


# ═══ CE 轮（2026-10-23）：pinned=true 不等于「可比」，也不等于「语料已审」 ══════


class TestComparabilityAndScannedSurface:
    """可比性围栏（alias_mismatch / 运行时模型集对账）+ 受检面披露。

    改前实测（同一棵树，围栏未落地时）：
    ① `pinned=true` + `alias_mismatch=true` 的工件 ⇒ 门禁 rc=0（写侧记了三处
       `alias_mismatch`，全仓**零读者**）；
    ② `pinned=true` + `requested_alias="gpt-4o-mini"`（CD 轮后运行面只剩
       `deepseek-flash`）⇒ 门禁 rc=0；
    ③ 成功语句「通过：1/1 个受检工件均 pinned=true」的分母 = 近 2 天窗口内
       的文件数（实测窗口内 2、豁免 1、实检 1），而入库 `benchmark_*.json`
       有 107 份、在盘递归 239 份——「1/1」可被读成语料级断言。
    """

    @pytest.fixture()
    def gate(self):
        return _load_gate_module()

    @staticmethod
    def _compliant(**over: Any) -> dict[str, Any]:
        fp: dict[str, Any] = {
            "requested_alias": "deepseek-flash",
            "returned_model": "deepseek-flash",
            "system_fingerprint": "fp_x",
            "probe_sha256": "a" * 64,
            "probe_at": "2026-10-23T00:00:00+00:00",
            "missing": [],
            "pinned": True,
            "error": None,
            "alias_mismatch": False,
        }
        fp.update(over)
        return _payload_with_fingerprint(fp)

    # ── 围栏一：写侧信号 alias_mismatch 必须有读者 ─────────────────────────

    def test_gate_blocks_pinned_batch_with_alias_mismatch(self, gate, tmp_path, capsys):
        """pinned=true 但 alias_mismatch=true → 阻断并点名可比性（改前 rc=0）。"""
        path = _write_result_json(tmp_path, self._compliant(alias_mismatch=True, returned_model="deepseek-v4-pro"))
        assert gate.main([str(path)]) == 1
        out = capsys.readouterr().out
        assert "可比性" in out
        assert "alias_mismatch" in out

    # ── 围栏二：工件记录的 alias 必须仍在运行时模型集内 ────────────────────

    def test_gate_blocks_pinned_batch_with_unsupported_alias(self, gate, tmp_path, capsys):
        """pinned=true 但 requested_alias 不在运行时模型集 → 阻断（改前 rc=0）。"""
        path = _write_result_json(
            tmp_path,
            self._compliant(requested_alias="gpt-4o-mini", returned_model="gpt-4o-mini-2024-07-18"),
        )
        assert gate.main([str(path)]) == 1
        out = capsys.readouterr().out
        assert "运行时" in out and "COMMON_MODELS" in out

    def test_gate_passes_fully_compliant_batch(self, gate, tmp_path, capsys):
        """两项围栏都满足 → 仍 rc=0，且逐件说明"围栏跑过"（不是"没跑所以干净"）。"""
        path = _write_result_json(tmp_path, self._compliant())
        assert gate.main([str(path)]) == 0
        assert "可比性围栏通过" in capsys.readouterr().out

    def test_pinned_judgment_values_are_untouched(self, gate):
        """既有判定面逐字节不动：check_payload 仍只判 pinned（围栏在 main 侧）。"""
        for over in ({"alias_mismatch": True}, {"requested_alias": "gpt-4o-mini"}):
            passed, items, _ = gate.check_payload(self._compliant(**over))
            assert passed is True and items == [], over

    # ── 前提缺失必须显式 skip 带读数，不得静默放行 ─────────────────────────

    def test_registry_unavailable_skips_alias_judgment_explicitly(self, gate, tmp_path, monkeypatch, capsys):
        """运行时注册表取不到 → 不判 alias，但必须打印显式 [SKIP] 带成因（不静默）。"""
        monkeypatch.setattr(
            gate, "runtime_model_aliases", lambda: (frozenset(), "注册表不可用：`COMMON_MODELS` 导入失败（测试注入）")
        )
        path = _write_result_json(
            tmp_path, self._compliant(requested_alias="gpt-4o-mini", returned_model="gpt-4o-mini-x")
        )
        assert gate.main([str(path)]) == 0
        out = capsys.readouterr().out
        assert "[SKIP]" in out and "alias" in out and "COMMON_MODELS" in out

    def test_alias_mismatch_fence_survives_registry_unavailable(self, gate, tmp_path, monkeypatch):
        """注册表不可用只关闭 alias 对账，不关闭 mismatch 判定。"""
        monkeypatch.setattr(gate, "runtime_model_aliases", lambda: (frozenset(), "测试注入：注册表不可用"))
        path = _write_result_json(tmp_path, self._compliant(alias_mismatch=True))
        assert gate.main([str(path)]) == 1

    # ── 受检面披露：成功语句的分母必须与语料面同时给出 ────────────────────

    def test_success_path_discloses_scanned_share(self, gate, tmp_path, capsys):
        """通过路径也必须打印受检面 / 语料面读数（改前只有 N/N 一个分母）。"""
        path = _write_result_json(tmp_path, self._compliant())
        assert gate.main([str(path)]) == 0
        out = capsys.readouterr().out
        assert "受检面" in out and "语料面" in out
        assert "在盘递归" in out and "入库" in out

    def test_corpus_surface_keys_are_fully_reported(self, gate):
        """corpus_surface() 的读数键集合锁（少一个键就是少一路披露）。"""
        assert set(gate.corpus_surface()) == {
            "tracked",
            "on_disk",
            "top_level",
            "with_provenance",
            "with_fingerprint",
            "pinned_true",
            "unsupported_alias",
            "alias_mismatch_true",
        }

    def test_real_corpus_is_reconciled_and_clean(self, gate):
        """真实语料对账：CD 轮收敛后，入库指纹的 alias 全部仍受运行时支持。"""
        from tests._corpus_guard import require_full_corpus

        require_full_corpus()
        surface = gate.corpus_surface()
        # 收口回钉（2026-10-25，v0.8.0 二次回钉：b1_lite 七格入库）：34/4/16/34/34/34
        # （CI 重建期下界 25/4/5/25/25/25；原历史 239/64/107/122/87/85）
        # B1 批上调（2026-10-30，只升不降）：2026-10-25 锁定后新增批次自然落盘
        # （TestGenEval / SWE 诊断 / E8 三格 / B2 指纹 / ULT 定标等 benchmark_*.json）
        # + specir probe 归档入库 ⇒ 46/4/17/46/46/46；结构层数以测试报数迭代回填。
        assert surface["on_disk"] == 46, surface
        assert surface["top_level"] == 4, surface
        assert surface["tracked"] == 17, surface
        assert surface["with_provenance"] == 46, surface
        # 45 = specir probe 旧工件（2026-10-14，pinned=False / 无 fingerprint）
        assert surface["with_fingerprint"] == 45, surface
        assert surface["pinned_true"] == 45, surface
        assert surface["unsupported_alias"] == 0, surface
        assert surface["alias_mismatch_true"] == 0, surface

    def test_gate_run_as_script_keeps_registry_available(self):
        """脚本方式执行（CI / `make model-fingerprint` 口径）时 alias 对账必须可用。

        进程内 import 与脚本执行的 `sys.path[0]` 不同（脚本口径下是
        `scripts/gates`，仓库根不在路径上）；测试内加载模块会**掩盖**这条
        死路，使门禁在真实执行时静默退化成"只判 pinned"（CC 轮同源教训：
        mock 的输出形态必须是真实形态）。这里用子进程跑真实入口。
        """
        out = subprocess.run(
            [sys.executable, str(_GATE_SCRIPT)], capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=300
        )
        assert out.returncode == 0, out.stdout + out.stderr
        assert "[SKIP]" not in out.stdout, out.stdout
        assert "运行时模型集 ['deepseek-flash']" in out.stdout, out.stdout

    def test_runtime_registry_authority_is_named(self, gate):
        """对账权威源必须是运行面本身（CD 轮后 = COMMON_MODELS 单别名）。"""
        aliases, reason = gate.runtime_model_aliases()
        assert reason is None, reason
        assert aliases == frozenset({"deepseek-flash"}), aliases

    # ── 分母 / 披露面：每一路读数都要在四条输出路径上都存在 ────────────────

    def test_success_denominator_is_checked_not_window(self, gate, tmp_path, monkeypatch, capsys):
        """成功语句的分母 = 实检数，不是窗口内文件数（改前两者混读）。"""
        exempt = _write_result_json(tmp_path, {"dataset": "examples", "results": {}}, name="benchmark_old.json")
        _write_result_json(tmp_path, self._compliant(), name="benchmark_ok.json")
        monkeypatch.setattr(gate, "_PRE_FINGERPRINT_EXEMPT", {_gate_rel_key(gate, exempt): "测试豁免理由"})
        assert gate.main([str(tmp_path)]) == 0
        out = capsys.readouterr().out
        assert "通过：1/1 个受检工件" in out
        assert "豁免 1 ⇒ 实检 1" in out
        assert "1/2" not in out

    def test_failure_path_also_discloses_scanned_surface(self, gate, tmp_path, capsys):
        """报红路径同样打印受检面/语料面——红字更要说清算了哪些文件。"""
        _write_result_json(tmp_path, {"dataset": "examples"}, name="benchmark_unlocked.json")
        assert gate.main([str(tmp_path)]) == 1
        err = capsys.readouterr().err
        assert "受检面" in err and "语料面" in err

    def test_empty_window_still_discloses_corpus_surface(self, gate, tmp_path, capsys):
        """空扫描面（近期无新批次）也要打印语料面："没有新批次"不得读成"语料已审"。"""
        empty = tmp_path / "empty"
        empty.mkdir()
        assert gate.main([str(empty)]) == 0
        assert "语料面" in capsys.readouterr().out
        assert gate.main([str(empty), "--allow-empty"]) == 0
        assert "受检面" in capsys.readouterr().out

    def test_block_summary_names_both_failure_kinds(self, gate, tmp_path, capsys):
        """阻断汇总必须点名"未锁定 + 可比性不成立"两类，否则读不出判据口径。"""
        path = _write_result_json(tmp_path, self._compliant(alias_mismatch=True))
        assert gate.main([str(path)]) == 1
        err = capsys.readouterr().err
        assert "可比性不成立" in err
        assert "不得与历史批次合并统计" in err

    # ── 语料面读数必须是"读出来的"，不是写死的 0 ────────────────────────────

    def test_corpus_surface_counts_alias_reconciliation_on_planted_corpus(self, gate, tmp_path):
        """递归在盘 / 单层顶层 / 结构层 / alias 双读数各自由增量构成，且严格 `is True`。"""
        (tmp_path / "benchmark_a.json").write_text(json.dumps(self._compliant(alias_mismatch=True)), encoding="utf-8")
        (tmp_path / "benchmark_b.json").write_text(
            json.dumps(self._compliant(requested_alias="gpt-4o-mini", returned_model="gpt-4o-mini-2")),
            encoding="utf-8",
        )
        (tmp_path / "benchmark_c.json").write_text(json.dumps(self._compliant()), encoding="utf-8")
        (tmp_path / "notes.json").write_text(json.dumps({"provenance": {}}), encoding="utf-8")
        nested = tmp_path / "nested"
        nested.mkdir()
        (nested / "benchmark_d.json").write_text(json.dumps(self._compliant(alias_mismatch="true")), encoding="utf-8")
        gate.DEFAULT_RESULTS_DIR = tmp_path
        gate._CORPUS_SURFACE_CACHE = None
        surface = gate.corpus_surface()
        assert surface["on_disk"] == 4, surface  # 递归口径；notes.json 不入面
        assert surface["top_level"] == 3, surface  # 目录单层
        assert surface["with_provenance"] == 4, surface
        assert surface["with_fingerprint"] == 4, surface
        assert surface["pinned_true"] == 4, surface
        assert surface["alias_mismatch_true"] == 1, surface  # 字符串 "true" 不算（与 pinned 同口径）
        assert surface["unsupported_alias"] == 1, surface

    def test_tracked_count_failure_is_disclosed_not_zero(self, gate, monkeypatch):
        """git 失败 ⇒ -1 并在披露里写"不可用"；计数只收 benchmark_*.json。"""
        keys = (
            "tracked",
            "on_disk",
            "top_level",
            "with_provenance",
            "with_fingerprint",
            "pinned_true",
            "unsupported_alias",
            "alias_mismatch_true",
        )

        def _raise(*_a: Any, **_k: Any) -> None:
            raise RuntimeError("git 不可用（测试注入）")

        monkeypatch.setattr(gate, "subprocess", types.SimpleNamespace(run=_raise))
        assert gate._tracked_benchmark_count() == -1
        mixed = "experiments/results/benchmark_a.json\nexperiments/results/full_comparison.json\n"
        monkeypatch.setattr(
            gate, "subprocess", types.SimpleNamespace(run=lambda *_a, **_k: types.SimpleNamespace(stdout=mixed))
        )
        assert gate._tracked_benchmark_count() == 1
        gate._CORPUS_SURFACE_CACHE = dict.fromkeys(keys, 0) | {"tracked": -1}
        assert any("入库 不可用" in line for line in gate.surface_disclosure([], 0))

    # ── 前提缺失的成因必须分类，且绝不冒充"可用" ────────────────────────────

    def test_degenerate_registry_reports_its_own_cause(self, gate, monkeypatch):
        """空集 / 类型漂移 / 条目无 name 三类成因不得混同，合法集仍照读。"""
        cases = (
            ([], "为空或类型漂移"),
            ("not-a-list", "为空或类型漂移"),
            ([{"model": "deepseek-flash"}], "无带 name 的条目"),
        )
        for value, expected in cases:
            fake = types.ModuleType("src.config.config_generator")
            fake.COMMON_MODELS = value
            monkeypatch.setitem(sys.modules, "src.config.config_generator", fake)
            aliases, reason = gate.runtime_model_aliases()
            assert aliases == frozenset(), value
            assert expected in str(reason), (value, reason)
        ok = types.ModuleType("src.config.config_generator")
        ok.COMMON_MODELS = [{"name": "deepseek-flash"}]
        monkeypatch.setitem(sys.modules, "src.config.config_generator", ok)
        assert gate.runtime_model_aliases() == (frozenset({"deepseek-flash"}), None)

    def test_registry_import_failure_reports_cause_not_availability(self, gate, tmp_path, monkeypatch, capsys):
        """import 失败 ⇒ 报成因 + 显式 [SKIP]；返回 (空集, None) 就是把前提缺失静默放行。"""
        monkeypatch.setitem(sys.modules, "src.config.config_generator", None)
        aliases, reason = gate.runtime_model_aliases()
        assert aliases == frozenset()
        assert "运行时模型集不可用" in str(reason)
        path = _write_result_json(
            tmp_path, self._compliant(requested_alias="gpt-4o-mini", returned_model="gpt-4o-mini-2")
        )
        assert gate.main([str(path)]) == 0
        out = capsys.readouterr().out
        assert "[SKIP]" in out and "import" in out
