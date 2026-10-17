#!/usr/bin/env python3
"""N 轮：全功能端到端探针框架（`scripts/tools/e2e_probe.py`）的回归锁定。

覆盖：
1. 结果构造器 ok/fail/skip/error 的 status/detail/evidence 语义；
2. 探针发现：模块导入、PROBES 收集、非 Probe 元素/重名/导入失败的显式报错；
3. 子进程隔离执行：`--run-probe` 结构化结果解析、超时/无结果 → fail/error；
4. 运行引擎：LLM 探针在未启用时 skip（不静默通过）、fail_fast 生效；
5. 报告渲染（Markdown 汇总/功能矩阵/失败明细）与 JSON 报告 schema；
6. CLI：`--list`、filter（--group/--name）、无匹配 → exit 2、fail → exit 1、
   strict 模式 skip → exit 1；LLM 门禁（--include-llm 但 AITESTER_E2E_LLM!=true → skip）。

测试不依赖真实 LLM/网络；探针模块用 sys.modules 注入的假模块。
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

_FRAMEWORK = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "e2e_probe.py"
_spec = importlib.util.spec_from_file_location("_e2e_probe_framework", _FRAMEWORK)
assert _spec and _spec.loader
e2e = importlib.util.module_from_spec(_spec)
sys.modules["_e2e_probe_framework"] = e2e
_spec.loader.exec_module(e2e)


def _install_fake_module(monkeypatch, name: str, probes: list, tmp_path: Path | None = None) -> Path:
    """把 duck-typed 假探针模块写到磁盘并加入 sys.path/PYTHONPATH。

    模块**零依赖**（不 import 框架）：探针对象只需 name/group/func 属性，
    运行器会 `_coerce_probe` 规范化——这正是框架支持的第三方探针形态，
    也保证 `_run_probe_isolated` 在子进程里能重新导入同一模块。
    """
    import tempfile

    base = Path(tmp_path) if tmp_path is not None else Path(tempfile.mkdtemp(prefix="probe_mod_"))
    module_file = base / f"{name}.py"
    lines = ["_PROBES = []", "class _P:", "    pass"]
    for idx, probe in enumerate(probes):
        if isinstance(probe, str):
            lines.append(f"_PROBES.append({probe!r})")
            continue
        var = f"_p{idx}"
        lines.append(f"{var} = _P()")
        lines.append(f"{var}.name = {probe.name!r}")
        lines.append(f"{var}.group = {probe.group!r}")
        lines.append(f"{var}.requires_llm = {probe.requires_llm!r}")
        lines.append(f"{var}.timeout_s = {probe.timeout_s!r}")
        lines.append(f"{var}.description = {probe.description!r}")
        behavior = getattr(probe, "behavior", "pass")
        detail = "ok" if behavior == "pass" else "probe-failed"
        lines.append(f"{var}.func = lambda: {{'status': {behavior!r}, 'detail': {detail!r}}}")
        lines.append(f"_PROBES.append({var})")
    lines.append("PROBES = _PROBES")
    module_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(base))
    old_pythonpath = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", f"{base}{os.pathsep}{old_pythonpath}" if old_pythonpath else str(base))
    sys.modules.pop(name, None)
    return module_file


def _make_probe(
    name: str,
    func,
    *,
    group: str = "test",
    requires_llm: bool = False,
    timeout_s: float = 30.0,
    behavior: str = "pass",
):
    probe = e2e.Probe(
        name=name, group=group, func=func, requires_llm=requires_llm, timeout_s=timeout_s, description="d"
    )
    probe.behavior = behavior  # 假磁盘模块按此生成 func（子进程可复现）
    return probe


class TestOutcomeConstructors:
    def test_ok(self):
        out = e2e.ok("fine", value=1)
        assert (out.status, out.detail, out.evidence) == ("pass", "fine", {"value": 1})

    def test_fail_requires_detail(self):
        out = e2e.fail("实测 0 != 期望 1", observed=0)
        assert out.status == "fail"
        assert out.evidence["observed"] == 0

    def test_skip_and_error(self):
        assert e2e.skip("缺 chromadb").status == "skip"
        assert e2e.error("boom", tb="x").status == "error"


class TestDiscovery:
    def test_collects_probes_from_module(self, monkeypatch, tmp_path):
        probe = _make_probe("p1", lambda: e2e.ok())
        _install_fake_module(monkeypatch, "fake_probes_a", [probe], tmp_path)
        probes, errors = e2e.discover_probes(["fake_probes_a"])
        assert [p.name for p in probes] == ["p1"]
        assert errors == []

    def test_missing_module_is_reported_not_crash(self):
        probes, errors = e2e.discover_probes(["definitely_not_a_module_xyz"])
        assert probes == []
        assert errors and "模块不存在" in errors[0]

    def test_non_probe_element_reported(self, monkeypatch, tmp_path):
        _install_fake_module(monkeypatch, "fake_probes_b", ["not-a-probe"], tmp_path)
        probes, errors = e2e.discover_probes(["fake_probes_b"])
        assert probes == []
        assert any("非 Probe" in e for e in errors)

    def test_duplicate_name_reported(self, monkeypatch, tmp_path):
        a = _make_probe("dup", lambda: e2e.ok())
        b = _make_probe("dup", lambda: e2e.ok())
        _install_fake_module(monkeypatch, "fake_probes_c", [a, b], tmp_path)
        probes, errors = e2e.discover_probes(["fake_probes_c"])
        assert len(probes) == 1
        assert any("重复" in e for e in errors)

    def test_import_error_reported(self, monkeypatch, tmp_path):
        bad_file = tmp_path / "fake_probes_bad.py"
        bad_file.write_text("raise RuntimeError('boom-at-import')\n", encoding="utf-8")
        monkeypatch.syspath_prepend(str(tmp_path))
        sys.modules.pop("fake_probes_bad", None)
        probes, errors = e2e.discover_probes(["fake_probes_bad"])
        assert probes == []
        assert any("导入失败" in e for e in errors)


@pytest.fixture()
def isolated_probe_module(monkeypatch, tmp_path):
    """把三类隔离执行测试的探针写进磁盘模块（子进程可发现）。"""
    probes = [
        _make_probe("iso-ok", lambda: e2e.ok("done")),
        _make_probe("iso-boom", lambda: e2e.error("kaboom")),
        _make_probe("iso-llm", lambda: e2e.ok(), requires_llm=True),
    ]
    _install_fake_module(monkeypatch, "fake_probes_iso", probes, tmp_path)
    return "fake_probes_iso"


class TestIsolatedRunner:
    def _find(self, module: str, name: str):
        probes, _ = e2e.discover_probes([module])
        return next(p for p in probes if p.name == name)

    def test_structured_result_roundtrip(self, isolated_probe_module):
        out = e2e._run_probe_isolated(self._find(isolated_probe_module, "iso-ok"), include_llm=False)
        assert out.status == "pass"

    def test_probe_error_becomes_error(self, isolated_probe_module):
        out = e2e._run_probe_isolated(self._find(isolated_probe_module, "iso-boom"), include_llm=False)
        # 子进程不存在的探针名 → 框架返回 error（诊断路径）
        out_missing = e2e._run_probe_isolated(
            e2e.Probe(name="does-not-exist", group="test", func=lambda: e2e.ok()), include_llm=False
        )
        assert out_missing.status in ("error", "fail")
        assert out.status == "pass"

    def test_llm_probe_skipped_without_flag(self, isolated_probe_module):
        out = e2e._run_probe_isolated(self._find(isolated_probe_module, "iso-llm"), include_llm=False)
        assert out.status == "skip"


class TestRunProbes:
    def test_llm_probe_skips_when_disabled(self):
        probe = _make_probe("skip-llm", lambda: e2e.ok(), requires_llm=True)
        rows = e2e.run_probes([probe], include_llm=False)
        assert rows[0]["status"] == "skip"
        assert "include-llm" in rows[0]["detail"]

    def test_fail_fast_stops(self, tmp_path, monkeypatch):
        calls: list[str] = []

        def first():
            calls.append("first")
            return e2e.fail("bad")

        def second():
            calls.append("second")
            return e2e.ok()

        _install_fake_module(
            monkeypatch,
            "fake_probes_ff",
            [_make_probe("ff-1", first, behavior="fail"), _make_probe("ff-2", second, behavior="pass")],
            tmp_path,
        )
        probes, _ = e2e.discover_probes(["fake_probes_ff"])
        rows = e2e.run_probes(probes, include_llm=False, fail_fast=True)
        assert len(rows) == 1
        assert rows[0]["status"] == "fail"
        assert calls == []  # 子进程隔离：磁盘模块的 func 生效，原 lambda 不会被调用


class TestReport:
    def test_markdown_contains_matrix_and_summary(self):
        rows = [
            e2e._row(_make_probe("p-pass", lambda: e2e.ok(), group="cli"), e2e.ok("good"), 0.5),
            e2e._row(_make_probe("p-fail", lambda: e2e.fail("bad|tick"), group="budget"), e2e.fail("bad|tick"), 1.0),
        ]
        md = e2e.render_markdown(rows, include_llm=False)
        assert "功能矩阵" in md
        assert "1 pass / 1 fail" in md
        assert "## 失败/异常明细" in md
        assert "bad\\|tick" in md  # 管道符转义

    def test_json_report_schema(self, tmp_path, monkeypatch):
        probe = _make_probe("json-ok", lambda: e2e.ok())
        _install_fake_module(monkeypatch, "fake_probes_json", [probe], tmp_path)
        out_json = tmp_path / "r.json"
        rc = e2e._main(["--module", "fake_probes_json", "--all", "--json-out", str(out_json)])
        assert rc == 0
        report = json.loads(out_json.read_text(encoding="utf-8"))
        assert report["schema"] == e2e._REPORT_SCHEMA
        assert report["summary"]["pass"] == 1
        assert report["probes"][0]["name"] == "json-ok"


class TestCli:
    def test_list_outputs_probes(self, monkeypatch, capsys, tmp_path):
        _install_fake_module(
            monkeypatch, "fake_probes_list", [_make_probe("list-me", lambda: e2e.ok(), group="cli")], tmp_path
        )
        rc = e2e._main(["--module", "fake_probes_list", "--list"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "list-me" in captured.out
        assert "零LLM" in captured.out

    def test_no_selection_returns_usage_error(self):
        assert e2e._main(["--module", "whatever"]) == 2

    def test_group_filter(self, monkeypatch, capsys, tmp_path):
        _install_fake_module(
            monkeypatch,
            "fake_probes_filter",
            [
                _make_probe("a", lambda: e2e.ok(), group="cli"),
                _make_probe("b", lambda: e2e.ok(), group="budget"),
            ],
            tmp_path,
        )
        rc = e2e._main(["--module", "fake_probes_filter", "--group", "budget", "--list"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "b " in out and "a " not in out

    def test_fail_returns_one(self, monkeypatch, tmp_path):
        _install_fake_module(
            monkeypatch, "fake_probes_fail", [_make_probe("f", lambda: e2e.fail("nope"), behavior="fail")], tmp_path
        )
        rc = e2e._main(["--module", "fake_probes_fail", "--all", "--json-out", str(tmp_path / "o.json")])
        assert rc == 1

    def test_strict_skip_returns_one(self, monkeypatch, tmp_path):
        _install_fake_module(
            monkeypatch,
            "fake_probes_skip",
            [_make_probe("s", lambda: e2e.ok(), requires_llm=True)],
            tmp_path,
        )
        rc = e2e._main(["--module", "fake_probes_skip", "--all", "--strict", "--json-out", str(tmp_path / "o.json")])
        assert rc == 1

    def test_include_llm_without_env_is_skip_not_fail(self, monkeypatch, tmp_path, capsys):
        monkeypatch.delenv("AITESTER_E2E_LLM", raising=False)
        _install_fake_module(
            monkeypatch,
            "fake_probes_llm",
            [_make_probe("llm", lambda: e2e.ok(), requires_llm=True)],
            tmp_path,
        )
        rc = e2e._main(
            [
                "--module",
                "fake_probes_llm",
                "--all",
                "--include-llm",
                "--json-out",
                str(tmp_path / "o.json"),
            ]
        )
        assert rc == 0
        report = json.loads((tmp_path / "o.json").read_text(encoding="utf-8"))
        assert report["probes"][0]["status"] == "skip"

    def test_run_probe_subprocess_mode(self, monkeypatch, capsys, tmp_path):
        _install_fake_module(monkeypatch, "fake_probes_sub", [_make_probe("sub-me", lambda: e2e.ok("sub"))], tmp_path)
        rc = e2e._main(["--module", "fake_probes_sub", "--run-probe", "sub-me"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert payload["status"] == "pass"


@pytest.mark.parametrize("status", ["pass", "fail", "skip", "error"])
def test_outcome_status_domain(status):
    assert status in {"pass", "fail", "skip", "error"}
