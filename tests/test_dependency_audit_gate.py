"""DF（2026-10-26）：依赖漏洞豁免过期守卫的测试锁。

## 为什么这道锁存在

本仓对 chromadb 1.5.9 的 5 条漏洞（PYSEC-2026-311 重复两条 + 3813 / 3814 / 3815）
的处置是 `pip-audit --ignore-vuln`。这个写法有三个让它「适合被一道锁钉住」的性质：

1. **豁免没有到期日**：`--ignore-vuln` 按 ID 匹配，与「是否有修复版本」无关；
   上游发布修复版后 CI 照常绿，「复审触发条件」只是一句人话。
2. **豁免会把新事实一起吞掉**：同一 ID 的 `fix_versions` 变化不再出现在阻断面上。
3. **豁免理由会随代码漂移**：登记表写「仅嵌入式、无服务器面、无 trust_remote_code」，
   但此前没有任何判据在读这句话。

## 判据

- 审计命中但登记表没有的 ID ⇒ 红；
- 登记表有、审计命中且 `fix_versions` 非空 ⇒ 红（**豁免已过期**）；
- 登记表锁定版本与 `requirements.lock` 不一致 ⇒ 红（依赖变了必须复审）；
- 登记了但本次未命中 ⇒ warning（去关闭登记），不是红；
- 同一 advisory 被 pip-audit 报告两次（实测 PYSEC-2026-311）⇒ 按 ID 合并，不重复计数；
- `src/` 中**提到 chromadb 的文件**出现 `trust_remote_code` / `HttpClient` /
  `SimpleRBACAuthorizationProvider` / `chromadb.app` ⇒ 红（豁免前提被推翻）；
  非 chromadb 文件里的同名 token 不误报；
- pip-audit 缺席 / 网络失败 ⇒ 结构化 `[SKIP]`，默认 rc=0；`--require-audit` rc=1；
- 退出码为 1 但 JSON 可解析（pip-audit 发现漏洞的正常表现）必须按 ok 处理；
- `--list` 只多打印明细，不改变判定方向。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GATE = PROJECT_ROOT / "scripts" / "gates" / "check_dependency_audit.py"

_REGISTRY_TEXT = """\
# 依赖豁免登记表

## 当前豁免

| 依赖 | 锁定版本 | 漏洞 ID | 豁免原因 | 复审触发条件 | 复审期限 | 备注 |
|---|---|---|---|---|---|---|
| chromadb | 1.5.9 | PYSEC-2026-311（重复两条）+ PYSEC-2026-3813 / 3814 / 3815 | 理由 | 触发 | 每季度 | 备注 |

## 已复审关闭的历史豁免

| 依赖 | 锁定版本 | 漏洞 ID | 豁免原因 | 复审触发条件 | 复审期限 | 备注 |
|---|---|---|---|---|---|---|
| chromadb | 0.4.16 | PYSEC-2025-9999 | 已关闭 | 已关闭 | 已关闭 | 已关闭 |
"""


def _load_gate():
    spec = importlib.util.spec_from_file_location("check_dependency_audit", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass + `from __future__ import annotations` 在动态加载时要求模块
    # 已在 sys.modules 里，否则 dataclasses 解析类型注解会拿到 None。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


def _dep(name: str, version: str, vulns: dict[str, list[str]]) -> dict:
    return {
        "name": name,
        "version": version,
        "vulns": [{"id": vuln_id, "fix_versions": fixes} for vuln_id, fixes in vulns.items()],
    }


def _registered_dep(*, fixes: list[str] | None = None, include: tuple[str, ...] | None = None) -> dict:
    ids = include or ("PYSEC-2026-311", "PYSEC-2026-3813", "PYSEC-2026-3814", "PYSEC-2026-3815")
    return _dep("chromadb", "1.5.9", {vuln_id: list(fixes or []) for vuln_id in ids})


def _write_tree(
    tmp_path: Path, *, registry: str = _REGISTRY_TEXT, lock: str = "chromadb==1.5.9\n"
) -> tuple[Path, Path, Path]:
    registry_path = tmp_path / "dependency_exemptions.md"
    lock_path = tmp_path / "requirements.lock"
    src_path = tmp_path / "src"
    registry_path.write_text(registry, encoding="utf-8")
    lock_path.write_text(lock, encoding="utf-8")
    src_path.mkdir()
    return registry_path, lock_path, src_path


def _patch_paths(gate, monkeypatch, tmp_path: Path, **kwargs) -> None:
    registry_path, lock_path, src_path = _write_tree(tmp_path, **kwargs)
    monkeypatch.setattr(gate, "REGISTRY", registry_path)
    monkeypatch.setattr(gate, "LOCK", lock_path)
    monkeypatch.setattr(gate, "SRC", src_path)


class TestRegistryParsing:
    def test_current_section_ids_and_version(self, gate):
        entries = gate._registry_exemptions(_REGISTRY_TEXT)
        assert len(entries) == 1, entries
        assert entries[0].package == "chromadb"
        assert entries[0].version == "1.5.9"
        assert entries[0].ids == (
            "PYSEC-2026-311",
            "PYSEC-2026-3813",
            "PYSEC-2026-3814",
            "PYSEC-2026-3815",
        )

    def test_closed_section_is_not_current(self, gate):
        """「已复审关闭」节的 ID 不得被当成现行豁免。"""
        ids = {vuln_id for entry in gate._registry_exemptions(_REGISTRY_TEXT) for vuln_id in entry.ids}
        assert "PYSEC-2025-9999" not in ids

    def test_header_and_separator_are_skipped(self, gate):
        """表头 / 分隔行没有漏洞 ID，不得被解析成空条目。"""
        assert len(gate._registry_exemptions(_REGISTRY_TEXT)) == 1

    def test_missing_section_yields_no_exemptions(self, gate):
        assert gate._registry_exemptions("# 空表\n\n没有当前豁免节\n") == []

    def test_bare_ids_continue_the_previous_prefix(self, gate):
        assert gate._vuln_ids("PYSEC-2026-3813 / 3814 / 3815") == (
            "PYSEC-2026-3813",
            "PYSEC-2026-3814",
            "PYSEC-2026-3815",
        )

    def test_duplicate_id_in_cell_is_deduped(self, gate):
        assert gate._vuln_ids("PYSEC-2026-311 与 PYSEC-2026-311") == ("PYSEC-2026-311",)


class TestLockParsing:
    def test_versions_are_read(self, gate):
        versions = gate._lock_versions("chromadb==1.5.9\nclick==8.4.2  # comment\n")
        assert versions == {"chromadb": "1.5.9", "click": "8.4.2"}

    def test_non_pinned_lines_are_ignored(self, gate):
        assert gate._lock_versions("-r other.txt\n# c\nchromadb>=1.0\n") == {}


class TestJudge:
    def _judge(self, gate, dependencies, *, lock: str = "chromadb==1.5.9\n"):
        exemptions = gate._registry_exemptions(_REGISTRY_TEXT)
        return gate._judge(exemptions, gate._lock_versions(lock), dependencies)

    def test_registered_without_fix_is_green(self, gate):
        verdict = self._judge(gate, [_registered_dep()])
        assert verdict.reds == [], verdict.reds

    def test_no_findings_is_green(self, gate):
        verdict = self._judge(gate, [_dep("click", "8.4.2", {})])
        assert verdict.reds == []

    def test_fix_version_expires_the_exemption(self, gate):
        """修复版发布 ⇒ 红（这是本门存在的根本理由）。"""
        verdict = self._judge(gate, [_registered_dep(fixes=["1.6.0"], include=("PYSEC-2026-3813",))])
        assert len(verdict.reds) == 1, verdict.reds
        assert "过期" in verdict.reds[0]
        assert "1.6.0" in verdict.reds[0]

    def test_one_expired_among_many_is_still_red(self, gate):
        verdict = self._judge(gate, [_registered_dep(fixes=["1.6.0"], include=("PYSEC-2026-3815",))])
        assert any("PYSEC-2026-3815" in red for red in verdict.reds)

    def test_unregistered_finding_is_red(self, gate):
        verdict = self._judge(gate, [_dep("newpkg", "0.1.0", {"PYSEC-2026-9999": []})])
        assert any("未登记" in red and "PYSEC-2026-9999" in red for red in verdict.reds)

    def test_duplicate_advisory_entries_do_not_double_count(self, gate):
        """实测 PYSEC-2026-311 会被报告两次；去重后不得产生红。"""
        duplicated = _dep("chromadb", "1.5.9", {"PYSEC-2026-311": []})
        verdict = self._judge(gate, [_registered_dep(), duplicated])
        assert verdict.reds == [], verdict.reds

    def test_lock_version_drift_is_red(self, gate):
        """登记表还写着 1.5.9，lock 已到 2.0.0 ⇒ 理由必须复审。"""
        verdict = self._judge(gate, [_registered_dep()], lock="chromadb==2.0.0\n")
        assert any("不一致" in red and "2.0.0" in red for red in verdict.reds)

    def test_registered_package_absent_from_lock_is_red(self, gate):
        verdict = self._judge(gate, [], lock="click==8.4.2\n")
        assert any("不在 requirements.lock" in red for red in verdict.reds)

    def test_package_mismatch_is_red(self, gate):
        verdict = self._judge(gate, [_dep("otherpkg", "1.0", {"PYSEC-2026-3813": []})])
        assert any("依赖与登记不一致" in red for red in verdict.reds)

    def test_stale_registry_is_warning_not_red(self, gate):
        """登记了但本次没命中：可能 advisory 已撤回 ⇒ 提示关闭，不阻断。"""
        verdict = self._judge(gate, [_dep("click", "8.4.2", {})])
        assert verdict.reds == []
        assert len(verdict.warnings) == 4


class TestReachability:
    def test_trust_remote_code_in_chromadb_file_is_flagged(self, gate, tmp_path):
        (tmp_path / "rag.py").write_text(
            "import chromadb\nclient = chromadb.PersistentClient(trust_remote_code=True)\n"
        )
        hits = gate._reachability_hits(tmp_path)
        assert [token for _, token, _ in hits] == ["trust_remote_code"]

    def test_http_client_is_flagged(self, gate, tmp_path):
        (tmp_path / "rag.py").write_text("import chromadb\nclient = chromadb.HttpClient(host='x')\n")
        assert [token for _, token, _ in gate._reachability_hits(tmp_path)] == ["HttpClient"]

    def test_rbac_provider_is_flagged(self, gate, tmp_path):
        (tmp_path / "server.py").write_text("import chromadb\nauth = SimpleRBACAuthorizationProvider()\n")
        assert [token for _, token, _ in gate._reachability_hits(tmp_path)] == ["SimpleRBACAuthorizationProvider"]

    def test_non_chromadb_file_is_not_flagged(self, gate, tmp_path):
        """HF 的 trust_remote_code 是另一件事：没有 chromadb 上下文不归本门管。"""
        (tmp_path / "hf.py").write_text("model = load(trust_remote_code=True)\n")
        assert gate._reachability_hits(tmp_path) == []

    def test_clean_embedded_client_passes(self, gate, tmp_path):
        (tmp_path / "rag.py").write_text("import chromadb\nclient = chromadb.PersistentClient(path='x')\n")
        assert gate._reachability_hits(tmp_path) == []

    def test_missing_src_is_empty(self, gate, tmp_path):
        assert gate._reachability_hits(tmp_path / "absent") == []


class TestAuditFailureMapping:
    def test_timeout_is_structured(self, gate, monkeypatch, tmp_path):
        lock = tmp_path / "requirements.lock"
        lock.write_text("chromadb==1.5.9\n", encoding="utf-8")
        monkeypatch.setattr(
            gate.subprocess,
            "run",
            lambda *a, **k: (_ for _ in ()).throw(gate.subprocess.TimeoutExpired(cmd="pip-audit", timeout=300)),
        )
        result = gate._run_audit(lock)
        assert result.status == "unavailable"
        assert "超时" in result.reason

    def test_oserror_is_structured(self, gate, monkeypatch, tmp_path):
        lock = tmp_path / "requirements.lock"
        lock.write_text("chromadb==1.5.9\n", encoding="utf-8")

        def _boom(*_a, **_k):
            raise OSError("no such binary")

        monkeypatch.setattr(gate.subprocess, "run", _boom)
        result = gate._run_audit(lock)
        assert result.status == "unavailable"
        assert "启动失败" in result.reason

    def test_invalid_json_is_unavailable(self, gate, monkeypatch, tmp_path):
        lock = tmp_path / "requirements.lock"
        lock.write_text("chromadb==1.5.9\n", encoding="utf-8")
        monkeypatch.setattr(
            gate.subprocess,
            "run",
            lambda *a, **k: type("P", (), {"returncode": 2, "stdout": "boom", "stderr": "network down\n"})(),
        )
        result = gate._run_audit(lock)
        assert result.status == "unavailable"
        assert "未产出 JSON" in result.reason

    def test_returncode_one_with_valid_json_is_ok(self, gate, monkeypatch, tmp_path):
        """pip-audit 发现漏洞时退出码 1，但 JSON 有效 ⇒ 必须按 ok 处理。"""
        lock = tmp_path / "requirements.lock"
        lock.write_text("chromadb==1.5.9\n", encoding="utf-8")
        payload = {"dependencies": [_registered_dep()]}
        monkeypatch.setattr(
            gate.subprocess,
            "run",
            lambda *a, **k: type("P", (), {"returncode": 1, "stdout": json.dumps(payload), "stderr": ""})(),
        )
        result = gate._run_audit(lock)
        assert result.status == "ok"
        assert result.dependencies == payload["dependencies"]


class TestCliContract:
    def test_green_report_returns_zero(self, gate, monkeypatch, tmp_path, capsys):
        _patch_paths(gate, monkeypatch, tmp_path)
        monkeypatch.setattr(gate, "_run_audit", lambda *a, **k: gate.AuditResult("ok", [_registered_dep()]))
        assert gate.main([]) == 0
        assert "✅" in capsys.readouterr().out

    def test_offline_skips_with_zero(self, gate, monkeypatch, tmp_path, capsys):
        _patch_paths(gate, monkeypatch, tmp_path)
        monkeypatch.setattr(
            gate, "_run_audit", lambda *a, **k: gate.AuditResult("unavailable", reason="pip-audit 不在当前解释器")
        )
        assert gate.main([]) == 0
        out = capsys.readouterr().out
        assert "[SKIP]" in out and "pip-audit 不在当前解释器" in out

    def test_offline_require_audit_is_red(self, gate, monkeypatch, tmp_path, capsys):
        _patch_paths(gate, monkeypatch, tmp_path)
        monkeypatch.setattr(gate, "_run_audit", lambda *a, **k: gate.AuditResult("unavailable", reason="离线"))
        assert gate.main(["--require-audit"]) == 1
        assert "无法验证" in capsys.readouterr().out

    def test_expired_exemption_is_red(self, gate, monkeypatch, tmp_path, capsys):
        _patch_paths(gate, monkeypatch, tmp_path)
        monkeypatch.setattr(
            gate,
            "_run_audit",
            lambda *a, **k: gate.AuditResult("ok", [_registered_dep(fixes=["1.6.0"], include=("PYSEC-2026-3813",))]),
        )
        assert gate.main([]) == 1
        assert "豁免已过期" in capsys.readouterr().out

    def test_reachability_red_even_when_audit_is_skipped(self, gate, monkeypatch, tmp_path, capsys):
        """静态通道不依赖网络：离线也必须能戳穿「仅嵌入式」前提。"""
        _patch_paths(gate, monkeypatch, tmp_path)
        (tmp_path / "src" / "rag.py").write_text("import chromadb\nchromadb.HttpClient(host='x')\n")
        monkeypatch.setattr(gate, "_run_audit", lambda *a, **k: gate.AuditResult("unavailable", reason="离线"))
        assert gate.main([]) == 1
        assert "可达性前提被推翻" in capsys.readouterr().out

    def test_missing_registry_is_red(self, gate, monkeypatch, tmp_path, capsys):
        _patch_paths(gate, monkeypatch, tmp_path)
        (tmp_path / "dependency_exemptions.md").unlink()
        assert gate.main([]) == 1
        assert "登记表缺席" in capsys.readouterr().out

    def test_list_flag_does_not_change_verdict(self, gate, monkeypatch, tmp_path, capsys):
        _patch_paths(gate, monkeypatch, tmp_path)
        monkeypatch.setattr(gate, "_run_audit", lambda *a, **k: gate.AuditResult("ok", [_registered_dep()]))
        assert gate.main([]) == 0
        first = capsys.readouterr().out
        assert gate.main(["--list"]) == 0
        second = capsys.readouterr().out
        assert "PYSEC-2026-3813: chromadb 1.5.9" in second
        assert "✅" in first

    def test_real_registry_and_lock_are_self_consistent(self, gate):
        """真实登记表 × 真实 lock × 合成审计报告（只取登记 ID、无修复版）⇒ 绿。"""
        exemptions = gate._registry_exemptions(Path(gate.REGISTRY).read_text(encoding="utf-8"))
        assert exemptions, "真实登记表未解析出任何豁免"
        dependencies = [
            _dep(entry.package, entry.version, {vuln_id: [] for vuln_id in entry.ids}) for entry in exemptions
        ]
        verdict = gate._judge(
            exemptions, gate._lock_versions(Path(gate.LOCK).read_text(encoding="utf-8")), dependencies
        )
        assert verdict.reds == [], verdict.reds

    def test_gate_file_exists(self):
        assert GATE.exists(), f"门禁缺失：{GATE}"
