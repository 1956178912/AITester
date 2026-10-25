#!/usr/bin/env python3
"""工件 git 入库守卫（`scripts/gates/check_artifacts_tracked.py`）的回归锁定。

锁定五件事（2026-10-17 独立评审 A-04；T 轮 2026-10-18 扩面）：

1. **证据目录覆盖扫描**：`experiments/results/` 下 `emse_*` 与 `*_round_*`
   每个目录必须 git 入库或显式登记豁免——防"新结果目录静默缺席"复发
   （四批旗舰工件曾 0 跟踪而无门禁察觉；T 轮发现 q/r/s/t 轮次前缀亦在
   `emse_*` 扫描盲区）；
2. **豁免必须带理由**：`EVIDENCE_DIR_EXEMPTIONS` 的值一律为非空字符串；
3. **真扫描真的会失败**：构造未跟踪目录必须被 `_scan_evidence_dirs` 报出
   （emse_* 与 *_round_* 两种前缀都验）；
4. **扫描面固定**：`EVIDENCE_DIR_GLOBS` 必须同时含 `emse_*` 与 `*_round_*`
   （缩小扫描面 = 门禁静默失效）；
5. **MANIFEST 无重复条目**（重复登记会掩盖清单增长审计）；
6. **豁免登记自身受审计**（CA 轮 2026-10-23）：目录消失 / 已全部入库 /
   目录为空 / 不可读 / 登记名不在扫描面内 → `exemption_drift_failures()`
   非空（此前豁免只在抑制报错时被读取，过期条目永不被发现）；
7. **遮蔽量可见**：`exemption_coverage()` 逐条给出未入库工件数，门禁通过时
   打印的披露数字必须等于其重算值（披露不得与数据分叉）；
8. **登记删除不减弱扫描**：为两条已失效登记（目录已删 / 53 个文件已全部
   入库）移除条目后，原本未登记的未跟踪目录仍必须被报出。

注意：本测试在真实仓库上运行（门禁语义依赖 git），不 mock git。
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

_GATE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "gates" / "check_artifacts_tracked.py"
_spec = importlib.util.spec_from_file_location("_artifacts_tracked_gate", _GATE_PATH)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
sys.modules["_artifacts_tracked_gate"] = gate
_spec.loader.exec_module(gate)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _fake_repo(root: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def _fake_batch(root: Path, name: str, files: int) -> Path:
    directory = root / "experiments" / "results" / name
    directory.mkdir(parents=True)
    for index in range(files):
        (directory / f"f{index}.json").write_text("{}", encoding="utf-8")
    return directory


class TestManifestHygiene:
    def test_manifest_has_no_duplicates(self):
        assert len(gate.MANIFEST) == len(set(gate.MANIFEST)), "MANIFEST 存在重复条目"

    def test_manifest_entries_exist_in_worktree(self):
        """清单内每个路径必须存在于工作区（缺失=引用链断裂，门禁应红）。"""
        missing = [rel for rel in gate.MANIFEST if not (PROJECT_ROOT / rel).exists()]
        assert not missing, f"MANIFEST 条目不存在于工作区: {missing}"

    def test_manifest_is_empty_after_purge_and_self_consistent(self):
        """CI 轮第三批（2026-10-24）：用户指令清除 experiments/results/ 全部历史数据
        （DeepSeek 重跑前），MANIFEST 条目随文件一并删除——13 个「清单必须含 X」
        内容锁整体退役为本空表语义锁：空表 + 去重 + 门禁通过是该机制在数据清除期的
        正常终态；重跑生成新工件后由新登记重建清单、锁面随之重建。"""
        assert gate.MANIFEST == ()
        assert len(set(gate.MANIFEST)) == len(gate.MANIFEST)


class TestEmseDirScan:
    def test_exemptions_have_reasons(self):
        for name, reason in gate.EVIDENCE_DIR_EXEMPTIONS.items():
            assert reason and reason.strip(), f"豁免 {name} 未登记理由"
            assert not name.endswith("/"), "豁免名应为目录名（不带斜杠）"

    def test_evidence_globs_cover_emse_and_round_prefixes(self):
        """扫描面必须同时覆盖 emse_* 与 *_round_*（T 轮扩面，防再次出现命名盲区）。"""
        assert "emse_*" in gate.EVIDENCE_DIR_GLOBS
        assert "*_round_*" in gate.EVIDENCE_DIR_GLOBS

    def test_scan_passes_on_current_repo(self):
        """当前仓库（四批旗舰已 force-add 后）覆盖扫描必须零违例。"""
        offenders = gate._scan_evidence_dirs()
        assert offenders == [], f"证据目录存在未入库且未豁免者: {offenders}"

    def test_scan_flags_untracked_dir(self, tmp_path, monkeypatch):
        """构造一个未跟踪的 emse_* 目录，扫描必须报错（防扫描退化为永真）。"""
        fake_results = tmp_path / "experiments" / "results"
        fake_dir = fake_results / "emse_fake_untracked_20261017"
        fake_dir.mkdir(parents=True)
        (fake_dir / "data.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(gate, "PROJECT_ROOT", tmp_path)
        # 在 fake 仓库里 git ls-files 对不存在仓库返回空 → 视为未跟踪
        offenders = gate._scan_evidence_dirs()
        rels = [rel for rel, _ in offenders]
        assert any("emse_fake_untracked_20261017" in rel for rel in rels), f"未检出未跟踪目录: {offenders}"

    def test_scan_flags_untracked_round_dir(self, tmp_path, monkeypatch):
        """T 轮扩面：未跟踪的 t_round_*/q_round_* 目录也必须被报出（旧扫描面盲区）。"""
        fake_results = tmp_path / "experiments" / "results"
        for name in ("t_round_fake_untracked_20261018", "q_round_fake_untracked_20261018"):
            fake_dir = fake_results / name
            fake_dir.mkdir(parents=True)
            (fake_dir / "REPORT.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(gate, "PROJECT_ROOT", tmp_path)
        offenders = gate._scan_evidence_dirs()
        rels = " ".join(rel for rel, _ in offenders)
        assert "t_round_fake_untracked_20261018" in rels, f"未检出未跟踪 t_round 目录: {offenders}"
        assert "q_round_fake_untracked_20261018" in rels, f"未检出未跟踪 q_round 目录: {offenders}"

    def test_exempt_dir_is_skipped(self, tmp_path, monkeypatch):
        """登记豁免的目录即使未跟踪也不报。"""
        fake_results = tmp_path / "experiments" / "results"
        fake_dir = fake_results / "emse_d2_profile_smoke_20261013"
        fake_dir.mkdir(parents=True)
        monkeypatch.setattr(gate, "PROJECT_ROOT", tmp_path)
        # CI 轮第三批：真实豁免表已随数据清除清空，本测试测的是「豁免机制」本身，
        # 故注入临时条目而不是依赖那张具体表。
        monkeypatch.setattr(
            gate, "EVIDENCE_DIR_EXEMPTIONS", {"emse_d2_profile_smoke_20261013": "测试豁免（tmp 合成目录） @tmp"}
        )
        offenders = gate._scan_evidence_dirs()
        assert offenders == [], f"豁免目录被误报: {offenders}"


class TestExemptionDrift:
    """CA 轮：豁免登记的失效判定与遮蔽量披露（读侧不得与数据分叉）。"""

    def test_registry_size_is_locked(self):
        # CI 轮补跑（2026-10-24）：豁免表自「清空态」重建为 5 条（DeepSeek 重跑期
        # 新批目录、按用户口径暂不提交）；提交入库后「已全部入库」漂移会提醒删登记，
        # 届时同步把本锁改回更小值。
        assert gate.EVIDENCE_DIR_EXEMPTIONS == {}  # 2026-10-25：四目录入库后清空

    def test_registry_names_stay_in_scan_surface(self):
        """登记名必须落在 EVIDENCE_DIR_GLOBS 内，否则豁免永不被扫描读取。"""
        off = [name for name in gate.EVIDENCE_DIR_EXEMPTIONS if not gate._in_scan_surface(name)]
        assert off == [], f"登记名不在扫描面内: {off}"

    def test_coverage_reconciles_with_registry(self):
        """覆盖表与登记表一一对应，且 hidden = total - tracked（同一计数口径）。"""
        rows = gate.exemption_coverage()
        assert sorted(row.name for row in rows) == sorted(gate.EVIDENCE_DIR_EXEMPTIONS)
        for row in rows:
            assert row.hidden_files == row.total_files - row.tracked_files
            assert row.status == "ok", (row.name, row.status, row.detail)
            assert 0 <= row.tracked_files < row.total_files, (row.name, row.tracked_files, row.total_files)

    def test_drift_clean_on_current_repo(self):
        """当前仓库：14 条登记全部仍然需要（目录存在、未全入库、可审计）。"""
        assert gate.exemption_drift_failures() == []

    def test_drift_flags_missing_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gate, "EVIDENCE_DIR_EXEMPTIONS", {"emse_gone_20260101": "已删批次"})
        monkeypatch.setattr(gate, "PROJECT_ROOT", tmp_path)
        failures = gate.exemption_drift_failures()
        assert [name for name, _ in failures] == ["emse_gone_20260101"]
        assert "目录已不存在" in failures[0][1]

    def test_drift_flags_empty_dir(self, tmp_path, monkeypatch):
        (tmp_path / "experiments/results/emse_empty_20260101").mkdir(parents=True)
        monkeypatch.setattr(gate, "EVIDENCE_DIR_EXEMPTIONS", {"emse_empty_20260101": "空目录"})
        monkeypatch.setattr(gate, "PROJECT_ROOT", tmp_path)
        failures = gate.exemption_drift_failures()
        assert [name for name, _ in failures] == ["emse_empty_20260101"]
        assert "不遮蔽任何工件" in failures[0][1]

    def test_drift_flags_fully_tracked_dir(self, tmp_path, monkeypatch):
        """全部入库后豁免不再抑制任何东西——登记应移除。"""
        repo = _fake_repo(tmp_path)
        directory = _fake_batch(repo, "emse_all_tracked_20260101", 2)
        subprocess.run(["git", "-C", str(repo), "add", str(directory)], check=True)
        monkeypatch.setattr(gate, "EVIDENCE_DIR_EXEMPTIONS", {"emse_all_tracked_20260101": "旧豁免"})
        monkeypatch.setattr(gate, "PROJECT_ROOT", repo)
        rows = gate.exemption_coverage()
        assert [(row.status, row.tracked_files, row.total_files) for row in rows] == [("fully_tracked", 2, 2)]
        failures = gate.exemption_drift_failures()
        assert [name for name, _ in failures] == ["emse_all_tracked_20260101"]
        assert "2/2" in failures[0][1]

    def test_drift_flags_unreadable_dir(self, tmp_path, monkeypatch):
        """git ls-files 失败时豁免无法复核，必须判漂移而不是静默继续。"""
        _fake_batch(tmp_path, "emse_unreadable_20260101", 1)
        real_run = subprocess.run
        boom = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")

        def fake_run(cmd, *args, **kwargs):
            if isinstance(cmd, list) and "ls-files" in cmd:
                return boom
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr(gate.subprocess, "run", fake_run)
        monkeypatch.setattr(gate, "EVIDENCE_DIR_EXEMPTIONS", {"emse_unreadable_20260101": "不可读"})
        monkeypatch.setattr(gate, "PROJECT_ROOT", tmp_path)
        failures = gate.exemption_drift_failures()
        assert [name for name, _ in failures] == ["emse_unreadable_20260101"]
        assert "无法审计" in failures[0][1]

    def test_drift_flags_name_outside_scan_surface(self, tmp_path, monkeypatch):
        repo = _fake_repo(tmp_path)
        _fake_batch(repo, "review_batch_20260101", 1)
        monkeypatch.setattr(gate, "EVIDENCE_DIR_EXEMPTIONS", {"review_batch_20260101": "命名不在扫描面"})
        monkeypatch.setattr(gate, "PROJECT_ROOT", repo)
        failures = gate.exemption_drift_failures()
        assert [name for name, _ in failures] == ["review_batch_20260101"]
        assert "扫描面内" in failures[0][1]

    def test_partial_exemption_is_not_drift(self, tmp_path, monkeypatch):
        """部分入库（1/2）仍是有效豁免，遮蔽量如实给出 1。"""
        repo = _fake_repo(tmp_path)
        directory = _fake_batch(repo, "emse_partial_20260101", 2)
        subprocess.run(["git", "-C", str(repo), "add", str(directory / "f0.json")], check=True)
        monkeypatch.setattr(gate, "EVIDENCE_DIR_EXEMPTIONS", {"emse_partial_20260101": "部分入库"})
        monkeypatch.setattr(gate, "PROJECT_ROOT", repo)
        rows = gate.exemption_coverage()
        assert [(row.status, row.hidden_files, row.total_files) for row in rows] == [("ok", 1, 2)]
        assert gate.exemption_drift_failures() == []

    def test_gate_imports_without_sys_modules_registration(self):
        """历史测试以 spec_from_file_location 动态加载且不登记 sys.modules——
        门禁模块在该载入路径下也必须可导入（`@dataclass` 在 3.14 会因
        `sys.modules[cls.__module__]` 为 None 而 AttributeError）。"""
        name = "_ca_unregistered_gate"
        sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location(name, _GATE_PATH)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # 故意不写入 sys.modules
        assert module.EVIDENCE_DIR_GLOBS
        rows = module.exemption_coverage()
        assert rows == [] or all(r.hidden_files >= 0 for r in rows)

    def test_drift_blocks_gate_even_when_scan_clean(self, tmp_path, monkeypatch, capsys):
        """main() 必须把漂移接成阻断（扫描面无违例 ≠ 登记健康）。"""
        monkeypatch.setattr(gate, "EVIDENCE_DIR_EXEMPTIONS", {"emse_gone_20260101": "已删批次"})
        monkeypatch.setattr(gate, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(gate, "MANIFEST", ())
        assert gate.main([]) == 1
        out = capsys.readouterr().out
        assert "豁免登记漂移" in out, out
        assert "emse_gone_20260101" in out, out

    def test_exemption_does_not_mask_other_dirs(self, tmp_path, monkeypatch):
        """删条目后扫描面不得退化：未登记的未跟踪目录仍被报出。"""
        _fake_repo(tmp_path)
        _fake_batch(tmp_path, "emse_waived_20260101", 1)
        _fake_batch(tmp_path, "emse_unwaived_20260101", 1)
        monkeypatch.setattr(gate, "EVIDENCE_DIR_EXEMPTIONS", {"emse_waived_20260101": "冒烟"})
        monkeypatch.setattr(gate, "PROJECT_ROOT", tmp_path)
        offenders = gate._scan_evidence_dirs()
        rels = " ".join(rel for rel, _ in offenders)
        assert "emse_unwaived_20260101" in rels, offenders
        assert "emse_waived_20260101" not in rels, offenders


class TestGateEndToEnd:
    def test_gate_exit_zero_on_current_repo(self):
        """端到端：当前暂存/提交态下门禁 exit 0。"""
        result = subprocess.run(
            [sys.executable, str(_GATE_PATH)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"门禁失败:\n{result.stdout}\n{result.stderr}"

    def test_gate_discloses_hidden_artifacts(self):
        """披露不得与数据分叉：打印的项数/遮蔽总数必须等于重算值。"""
        result = subprocess.run(
            [sys.executable, str(_GATE_PATH)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"门禁失败:\n{result.stdout}\n{result.stderr}"
        match = re.search(r"豁免披露：(\d+) 项有效登记共遮蔽未入库工件 (\d+) 个", result.stdout)
        assert match, result.stdout
        rows = gate.exemption_coverage()
        assert int(match.group(1)) == len(rows)
        assert int(match.group(2)) == sum(row.hidden_files for row in rows)
        for row in rows:
            line = f"[EXEMPT] {row.name}: 遮蔽未入库工件 {row.hidden_files}/{row.total_files}"
            assert line in result.stdout, f"缺少逐条披露: {line}"
