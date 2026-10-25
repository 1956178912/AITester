"""CF 轮：登记面读侧对账门禁 `scripts/gates/check_registration_consistency.py` 的回归锁。

纪律：**零 LLM、$0**；不写任何真实文档，所有判定用 tmp 目录里的合成登记面/门禁面跑；
只有标记「真实树」的 4 例读真仓库（不写）。

为什么这些锁必须存在（改前实测，2026-10-24）：
- 登记册 §1「静态检查」行声明 **999** 文件已格式化（BQ 轮复算），HEAD（`00e8c24d`）树复算
  `ruff format --check .` = **1037** ⇒ 漂移 **+38**（未提交工作树 1048），跨约 14 轮无人复算；
  本门初版还把 ruff 的 diff 正文当摘要读（全串 search），把 1047 读成 5 ⇒ 摘要必须锚定末行；
- 登记册 §1「门禁总数」行写「权威口径 = BASELINE.yaml `gates` 节」，而 BASELINE `gates`
  三键在全仓 Python 里读者 **0**；
- `docs/reviews/` 在盘 78 份分册，zh §3.5 登记 77（漏 X）、en §3.5 登记 74（漏 BR/BS/BT/X）
  ——死链方向有读者，反方向没有；
- zh §2.2 分册条目编号序列 `…20, 22, 21, 23`：编号是手写装饰，无读者。

分组：A 数字对账 12 例 / B 权威复算面 16 例 / C 清单与编号 8 例 / D 活性与接线 4 例 /
F 受检面披露 2 例 / E 真实树 4 例（共 46 例）。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_GATE_SCRIPT = PROJECT_ROOT / "scripts" / "gates" / "check_registration_consistency.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("aitester_check_registration_consistency", _GATE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


# ══ 合成登记面 / 门禁面 ═════════════════════════════════════════════════
# 一套自洽的假树：门禁 2 / ci 唯一 2 / 调用点 2 / 步骤 2（1 非阻断）/ make 2 目标 2 命令
FAKE_REGISTER = """# 登记册

## 1. 现状快照

| 维度 | 数值 | 验证入口 |
|---|---|---|
| 门禁总数 | 〔当前口径（示例）：门禁脚本 2 / 门禁索引 2 / ci唯一门禁 2 / ci调用点 2 / 门禁步骤 2 / 非阻断步骤 1 / 阻断步骤 1 / make目标 2 / make命令 2〕 | `make gates` |
| 静态检查 | 〔当前口径（示例）：已格式化 3 / mypy源文件 3〕**999** 文件已格式化（BQ 轮复算） | `make format` |
| 全量测试 | 〔当前口径（示例）：passed 10 / failed 0 / skipped 1 / collected 11〕 | `make test` |
| 总行覆盖 | **97.00%**（本门不判） | `coverage.xml` |

## 2. 阻断项

| 维度 | 数值 |
|---|---|
| 门禁总数 | 〔当前口径（历史小节里的同名行）：门禁脚本 999〕 |
"""

FAKE_MAKE = """PY := python3

lint:
\t$(PY) scripts/gates/check_alpha.py

format:
\t$(PY) scripts/gates/check_beta.py

gates: lint format  ## 全部门禁
"""

FAKE_CI = """jobs:
  test:
    steps:
      - name: Lint gate
        run: python scripts/gates/check_alpha.py
      - name: Weekly warn-only gate
        run: python scripts/gates/check_beta.py --warn-only
      - name: Not a gate step
        run: echo hello
"""

FAKE_BASELINE = """tests:
  total_passed: 10
  total_failed: 0
  total_skipped: 1
  total_xfailed: 0
  collected: 11
static_checks:
  ruff_version: "0.16.3"
  ruff_warnings: 0
  mypy_errors: 0
  mypy_source_files: 3
  formatted_files: 3
gates:
  scripts_total: 2
  index_scripts: 2
  ci_unique_scripts: 2
  ci_call_sites: 2
  gate_steps: 2
  non_blocking_steps: 1
  blocking_steps: 1
  make_targets: 2
  make_commands: 2
"""


def _fake_tree(tmp_path: Path, *, register: str = FAKE_REGISTER) -> Path:
    (tmp_path / "scripts" / "gates").mkdir(parents=True, exist_ok=True)
    for stem in ("check_alpha", "check_beta"):
        (tmp_path / "scripts" / "gates" / f"{stem}.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "PROJECT_STATUS_REGISTER.md").write_text(register, encoding="utf-8")
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "src" / "sub").mkdir(exist_ok=True)
    (tmp_path / "src" / "sub" / "b.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "config.py").write_text("z = 3\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text(FAKE_MAKE, encoding="utf-8")
    (tmp_path / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(FAKE_CI, encoding="utf-8")
    (tmp_path / "BASELINE.yaml").write_text(FAKE_BASELINE, encoding="utf-8")
    reviews = tmp_path / "docs" / "reviews"
    reviews.mkdir(exist_ok=True)
    (reviews / "A_BOOKLET.md").write_text("# A\n", encoding="utf-8")
    (reviews / "B_BOOKLET.md").write_text("# B\n", encoding="utf-8")
    index = (
        "# 索引\n\n## 2. 阅读路径\n\n### 2.2 审稿人\n\n"
        "1. [docs/reviews/A_BOOKLET.md](reviews/A_BOOKLET.md)\n"
        "2. [docs/reviews/B_BOOKLET.md](reviews/B_BOOKLET.md)\n\n"
        "### 2.3 复现者\n\n## 3. 清单\n\n### 3.5 治理与评审\n\n"
        "| 文档 | 说明 |\n|---|---|\n"
        "| [docs/reviews/A_BOOKLET.md](reviews/A_BOOKLET.md) | A |\n"
        "| [docs/reviews/B_BOOKLET.md](reviews/B_BOOKLET.md) | B |\n\n"
        "## 4. 维护\n"
    )
    (tmp_path / "docs" / "INDEX.md").write_text(index, encoding="utf-8")
    (tmp_path / "docs" / "INDEX.en.md").write_text(index, encoding="utf-8")
    return tmp_path


@pytest.fixture
def fake(gate, tmp_path, monkeypatch):
    """假树 + 稳定的权威值（不让真仓库的 git/ruff 进入判定）。"""
    root = _fake_tree(tmp_path)
    monkeypatch.setattr(gate, "index_gate_scripts", lambda _root=None: (["check_alpha", "check_beta"], None))
    monkeypatch.setattr(gate, "tracked_reviews", lambda _root=None: (["A_BOOKLET.md", "B_BOOKLET.md"], None))
    monkeypatch.setattr(
        gate,
        "ruff_surface",
        lambda _root=None: ({"待格式化": 0, "已格式化": 3}, None),
    )
    monkeypatch.setattr(
        gate,
        "ruff_version",
        lambda _root=None: ("0.16.3", None),
    )
    auth, notes, problems = gate.compute_authorities(verify_mypy=False, root=root)
    return SimpleNamespace(
        root=root, auth=auth, notes=notes, problems=problems, register=(root / "docs" / "PROJECT_STATUS_REGISTER.md")
    )


# ══ A 组：数字对账 ══════════════════════════════════════════════════════
class TestDeclaredNumbers:
    def test_all_matched_yields_no_problem(self, gate, fake):
        problems, ok, skips, per_row = gate.check_declared_numbers(fake.auth, fake.register.read_text(encoding="utf-8"))
        assert problems == [], problems
        assert skips == []
        assert len(per_row) == 3  # 门禁总数 / 静态检查 / 全量测试
        assert len(ok) == len(gate.ITEMS)

    def test_drift_is_red_with_both_readings(self, gate, fake):
        text = fake.register.read_text(encoding="utf-8").replace("已格式化 3", "已格式化 999")
        problems, _, _, _ = gate.check_declared_numbers(fake.auth, text)
        assert len(problems) == 1, problems
        assert "999" in problems[0] and "1046" not in problems[0]
        assert "权威复算 3" in problems[0], problems[0]

    def test_missing_key_is_red_not_silent(self, gate, fake):
        text = fake.register.read_text(encoding="utf-8").replace(" / mypy源文件 3", "")
        problems, _, _, _ = gate.check_declared_numbers(fake.auth, text)
        assert any("未登记当前口径键 mypy源文件" in p for p in problems), problems

    def test_unowned_bracket_key_is_red(self, gate, fake):
        text = fake.register.read_text(encoding="utf-8").replace("make命令 2〕", "make命令 2 / 神秘数字 7〕")
        problems, _, _, _ = gate.check_declared_numbers(fake.auth, text)
        assert any("无判定项" in p and "神秘数字" in p for p in problems), problems

    def test_row_absent_is_red(self, gate, fake):
        text = "\n".join(
            line for line in fake.register.read_text(encoding="utf-8").splitlines() if not line.startswith("| 静态检查")
        )
        problems, _, _, _ = gate.check_declared_numbers(fake.auth, text)
        assert any("未找到「静态检查」行" in p and "缺席 ≠ 通过" in p for p in problems), problems
        assert len(problems) == 2  # 该行的两个判定键都无归属

    def test_section_heading_absent_is_red(self, gate, fake):
        text = fake.register.read_text(encoding="utf-8").replace("## 1. 现状快照", "## 附录")
        problems, _, _, _ = gate.check_declared_numbers(fake.auth, text)
        assert problems == ["docs/PROJECT_STATUS_REGISTER.md：未找到 §1「现状快照」小节标题——登记面无从解析"], problems

    def test_history_section_rows_are_not_read(self, gate, fake):
        """§1 之外的同名行（带 999）必须不进判定——否则「历史快照」与「当前口径」同形。"""
        assert "门禁脚本 999" in FAKE_REGISTER  # §2 小节里的干扰行
        problems, _, _, per_row = gate.check_declared_numbers(fake.auth, fake.register.read_text(encoding="utf-8"))
        assert problems == [], problems
        assert per_row["门禁总数"]["门禁脚本"] == 2

    def test_bracket_without_key_space_number_does_not_parse(self, gate, fake):
        """语法严格：`键=数` 不认（漏登记会以「未登记当前口径键」转红，而不是静默通过）。"""
        text = fake.register.read_text(encoding="utf-8").replace("已格式化 3", "已格式化=3")
        problems, _, _, _ = gate.check_declared_numbers(fake.auth, text)
        assert any("未登记当前口径键 已格式化" in p for p in problems), problems

    def test_authority_absent_is_skip_not_red(self, gate, fake):
        """权威值取不到 ⇒ [SKIP] 带成因：既不凭空转红，也不静默通过（BZ §70）。"""
        auth = dict(fake.auth)
        del auth["已格式化"]
        problems, ok, skips, _ = gate.check_declared_numbers(auth, fake.register.read_text(encoding="utf-8"))
        assert any("[SKIP] 「静态检查」项 已格式化" in s for s in skips), skips
        assert not any("已格式化" in p for p in problems), problems
        assert not any("已格式化" in o for o in ok), ok

    def test_non_current_caliber_bracket_is_not_judged(self, gate, fake):
        """判定只认〔当前口径…〕：〔历史：已格式化 900〕不算声明，否则历史快照会被当成当前值。"""
        text = fake.register.read_text(encoding="utf-8").replace(
            "〔当前口径（示例）：已格式化 3 / mypy源文件 3〕", "〔历史：已格式化 900 / mypy源文件 3〕"
        )
        problems, _, _, _ = gate.check_declared_numbers(fake.auth, text)
        assert any("未登记当前口径键 已格式化" in p for p in problems), problems
        assert not any("900" in p for p in problems), problems

    def test_section_one_stops_at_next_h2(self, gate):
        """§1 切片必须在下一个 H2 处收口：越界就把「历史小节里的同名行」当当前口径读。"""
        section = gate.section_one(FAKE_REGISTER)
        assert section is not None
        assert "门禁脚本 2" in section and "门禁脚本 999" not in section

    def test_register_rows_keeps_first_hit(self, gate):
        """同名行重复时取首个为当前口径（当前表在前，历史表在后）——后写覆盖会把历史值当声明。"""
        rows = gate.register_rows(FAKE_REGISTER)  # 全文，不切小节
        assert "门禁脚本 2" in rows["门禁总数"], rows["门禁总数"]
        assert "999" not in rows["门禁总数"], rows["门禁总数"]


# ══ B 组：权威复算面 ════════════════════════════════════════════════════
class TestAuthorityRecompute:
    def test_authorities_match_fake_baseline(self, fake):
        assert fake.problems == [], fake.problems
        assert fake.auth["ci唯一门禁"] == 2 and fake.auth["ci调用点"] == 2
        assert fake.auth["make目标"] == 2 and fake.auth["make命令"] == 2
        assert fake.auth["已格式化"] == 3 and fake.auth["mypy源文件"] == 3
        assert fake.auth["collected"] == 11

    def test_non_blocking_criterion_includes_warn_only(self, gate):
        surface = gate.ci_gate_surface(FAKE_CI)
        assert surface == {
            "ci唯一门禁": 2,
            "ci调用点": 2,
            "门禁步骤": 2,
            "非阻断步骤": 1,
            "阻断步骤": 1,
        }, surface
        # 只按 continue-on-error 复算会得 0 非阻断 / 2 阻断 ⇒ 假红；判据必须两条都算
        strict_only = gate.ci_gate_surface(FAKE_CI.replace(" --warn-only", ""))
        assert strict_only["非阻断步骤"] == 0

    def test_ci_unique_scripts_and_call_sites_are_two_calibers(self, gate):
        """同一脚本被两个步骤调用：唯一数 2、调用点 3——两键同值就说明有一键没在算。"""
        ci = FAKE_CI + "      - name: Lint gate again\n        run: python scripts/gates/check_alpha.py --quiet\n"
        surface = gate.ci_gate_surface(ci)
        assert surface["ci唯一门禁"] == 2 and surface["ci调用点"] == 3, surface
        assert surface["门禁步骤"] == 3 and surface["阻断步骤"] == 2, surface

    def test_make_targets_and_commands_are_two_calibers(self, gate):
        make = FAKE_MAKE.replace(
            "\t$(PY) scripts/gates/check_beta.py",
            "\t$(PY) scripts/gates/check_beta.py\n\t$(PY) scripts/gates/check_beta.py --quiet",
        )
        assert gate.make_gate_surface(make) == {"make目标": 2, "make命令": 3}

    def test_ruff_surface_sums_both_halves(self, gate, monkeypatch):
        res = SimpleNamespace(
            returncode=1, stdout="", stderr="2 files would be reformatted, 3 files already formatted\n"
        )
        monkeypatch.setattr(gate, "_run", lambda cmd, root: res)
        assert gate.ruff_surface(Path(".")) == ({"待格式化": 2, "已格式化": 5}, None)
        clean = SimpleNamespace(returncode=0, stdout="1046 files already formatted\n", stderr="")
        monkeypatch.setattr(gate, "_run", lambda cmd, root: clean)
        assert gate.ruff_surface(Path(".")) == ({"待格式化": 0, "已格式化": 1046}, None)

    def test_ruff_diff_body_is_not_read_as_summary(self, gate, monkeypatch):
        """diff 正文里出现汇总句式也不能当汇总（改前实测踩过：1047 被读成 5）。"""
        res = SimpleNamespace(
            returncode=1,
            stdout=(
                "unformatted: File would be reformatted\n   --> t.py\n    |\n"
                "243 - 2 files would be reformatted, 3 files already formatted\n    |\n\n"
                "1 file would be reformatted, 1047 files already formatted\n"
            ),
            stderr="",
        )
        monkeypatch.setattr(gate, "_run", lambda cmd, root: res)
        assert gate.ruff_surface(Path(".")) == ({"待格式化": 1, "已格式化": 1048}, None)

    def test_ruff_unparseable_output_skips_with_cause(self, gate, monkeypatch):
        monkeypatch.setattr(gate, "_run", lambda cmd, root: SimpleNamespace(returncode=2, stdout="boom", stderr=""))
        surface, reason = gate.ruff_surface(Path("."))
        assert surface is None and "无法解析" in reason

    def test_ruff_module_absent_is_skip_not_red(self, gate, monkeypatch):
        monkeypatch.setattr(gate, "_run", lambda cmd, root: None)
        surface, reason = gate.ruff_surface(Path("."))
        assert surface is None and "子进程未能启动" in reason

    def test_ruff_unavailable_leaves_no_authority_value(self, gate, fake, monkeypatch):
        """取不到面 ⇒ 不写权威值 + [SKIP]。写成 0 会让「登记 0」蒙对一次。"""
        monkeypatch.setattr(gate, "ruff_surface", lambda _root=None: (None, "ruff 模块不可用（子进程未能启动）"))
        auth, notes, problems = gate.compute_authorities(verify_mypy=False, root=fake.root)
        assert "已格式化" not in auth, auth
        assert any("[SKIP] 已格式化面复算未执行" in n for n in notes), notes
        assert problems == [], problems

    def test_git_caliber_failure_is_not_empty_index(self, gate, monkeypatch):
        """git 取不到 ⇒ (None, 成因)：当成空索引会把「本轮未提交」读成「一个都没入库」。"""
        monkeypatch.setattr(
            gate, "_run", lambda cmd, root: SimpleNamespace(returncode=1, stdout="", stderr="not a repo")
        )
        assert gate.index_gate_scripts(Path(".")) == (None, "git ls-files 退出码 1")
        assert gate.tracked_reviews(Path(".")) == (None, "git ls-files 退出码 1")
        monkeypatch.setattr(gate, "_run", lambda cmd, root: None)
        assert gate.index_gate_scripts(Path("."))[1] == "git 可执行文件不可用（子进程未能启动）"
        assert gate.tracked_reviews(Path("."))[1] == "git 可执行文件不可用（子进程未能启动）"

    def test_mypy_derivation_follows_makefile_targets(self, gate, fake):
        """口径 = Makefile 真传给 mypy 的目标（`src/` 递归 + `config.py`），不是「src 下所有文件」。"""
        assert gate.mypy_target_count(fake.root) == 3  # src/a.py + src/sub/b.py + config.py
        (fake.root / "src" / "sub" / "c.py").write_text("w = 4\n", encoding="utf-8")
        assert gate.mypy_target_count(fake.root) == 4

    def test_verify_mypy_mismatch_is_red(self, gate, fake, monkeypatch):
        monkeypatch.setattr(gate, "mypy_self_report", lambda _root=None: (99, None))
        _, _, problems = gate.compute_authorities(verify_mypy=True, root=fake.root)
        assert any("--verify-mypy" in p and "口径分叉" in p for p in problems), problems

    def test_collected_identity_is_judged(self, gate, fake):
        bad = FAKE_BASELINE.replace("collected: 11", "collected: 12")
        (fake.root / "BASELINE.yaml").write_text(bad, encoding="utf-8")
        _, _, problems = gate.compute_authorities(verify_mypy=False, root=fake.root)
        assert any("收集口径与分项计数不等" in p for p in problems), problems

    def test_missing_baseline_key_is_red(self, gate, fake):
        bad = "\n".join(line for line in FAKE_BASELINE.splitlines() if line != "  collected: 11")
        (fake.root / "BASELINE.yaml").write_text(bad + "\n", encoding="utf-8")
        _, _, problems = gate.compute_authorities(verify_mypy=False, root=fake.root)
        assert any("tests.collected 缺席" in p for p in problems), problems

    def test_baseline_self_authority_drift_is_red(self, gate, fake):
        """缺陷②的正解：BASELINE `gates` 节被指认为权威源，就必须被本门逐项复算，不能只挂名。"""
        bad = FAKE_BASELINE.replace("  make_commands: 2", "  make_commands: 9")
        (fake.root / "BASELINE.yaml").write_text(bad, encoding="utf-8")
        _, _, problems = gate.compute_authorities(verify_mypy=False, root=fake.root)
        assert any("gates.make_commands = 9" in p and "差 +7" in p for p in problems), problems

    def test_baseline_self_authority_absent_is_red(self, gate, fake):
        bad = "\n".join(line for line in FAKE_BASELINE.splitlines() if line != "  index_scripts: 2")
        (fake.root / "BASELINE.yaml").write_text(bad + "\n", encoding="utf-8")
        _, _, problems = gate.compute_authorities(verify_mypy=False, root=fake.root)
        assert any("gates.index_scripts 缺席" in p and "没人读" in p for p in problems), problems


# ══ C 组：清单在场性与编号 ══════════════════════════════════════════════
class TestIndexPresence:
    def test_clean_tree_passes(self, gate, fake):
        problems, ok, _notes = gate.check_index_presence(fake.root)
        assert problems == [], problems
        assert len(ok) == 4  # zh/en §3.5 覆盖 + zh/en §2.2 编号

    def test_orphan_booklet_is_named(self, gate, fake):
        (fake.root / "docs" / "reviews" / "C_BOOKLET.md").write_text("# C\n", encoding="utf-8")
        problems, _, _ = gate.check_index_presence(fake.root)
        assert len(problems) == 2, problems  # zh 与 en 各一条
        assert all("C_BOOKLET.md" in p for p in problems)

    def test_allowlist_clears_only_the_named_side(self, gate, fake):
        (fake.root / "docs" / "reviews" / "C_BOOKLET.md").write_text("# C\n", encoding="utf-8")
        (fake.root / "docs" / "registration_consistency_allowlist.txt").write_text(
            "C_BOOKLET.md:docs/INDEX.md  # 只读普查，不给审稿人路径\n", encoding="utf-8"
        )
        problems, _, _ = gate.check_index_presence(fake.root)
        assert len(problems) == 1 and "INDEX.en.md" in problems[0], problems

    def test_allowlist_without_reason_is_red(self, gate, fake):
        (fake.root / "docs" / "reviews" / "C_BOOKLET.md").write_text("# C\n", encoding="utf-8")
        (fake.root / "docs" / "registration_consistency_allowlist.txt").write_text(
            "C_BOOKLET.md:docs/INDEX.md\n", encoding="utf-8"
        )
        problems, _, _ = gate.check_index_presence(fake.root)
        assert any("无理由" in p for p in problems), problems

    def test_stale_allowlist_entry_is_red(self, gate, fake):
        (fake.root / "docs" / "registration_consistency_allowlist.txt").write_text(
            "GONE_BOOKLET.md:docs/INDEX.md  # 已归档\n", encoding="utf-8"
        )
        problems, _, _ = gate.check_index_presence(fake.root)
        assert any("不存在的分册" in p for p in problems), problems

    def test_duplicate_index_row_is_red(self, gate, fake):
        text = (fake.root / "docs" / "INDEX.md").read_text(encoding="utf-8")
        row = "| [docs/reviews/A_BOOKLET.md](reviews/A_BOOKLET.md) | A |\n"
        # 重复行必须落在 §3.5 小节内：§4 之后追加会被小节切面丢掉，那不是本门要锁的口径
        (fake.root / "docs" / "INDEX.md").write_text(text.replace(row, row + row, 1), encoding="utf-8")
        problems, _, _ = gate.check_index_presence(fake.root)
        assert any("重复登记行" in p for p in problems), problems

    def test_numbering_gap_is_red(self, gate, fake):
        text = (
            (fake.root / "docs" / "INDEX.md")
            .read_text(encoding="utf-8")
            .replace("2. [docs/reviews/B_BOOKLET.md]", "4. [docs/reviews/B_BOOKLET.md]")
        )
        (fake.root / "docs" / "INDEX.md").write_text(text, encoding="utf-8")
        problems, _, _ = gate.check_index_presence(fake.root)
        assert any("编号非连续 [(1, 4)]" in p for p in problems), problems

    def test_missing_index_file_is_red(self, gate, fake):
        (fake.root / "docs" / "INDEX.en.md").unlink()
        problems, _, _ = gate.check_index_presence(fake.root)
        assert any("docs/INDEX.en.md 缺席" in p for p in problems), problems


# ══ D 组：拥有者活性与接线 ══════════════════════════════════════════════
class TestReaderLiveness:
    def test_owner_without_anchor_is_red(self, gate, fake, monkeypatch):
        owner = fake.root / "scripts" / "gates" / "check_alpha.py"
        owner.write_text("# 锚点被删掉了\n", encoding="utf-8")
        monkeypatch.setattr(gate, "OWNERS", [("覆盖率两行", "scripts/gates/check_alpha.py", ("_REGISTER_DECL",))])
        monkeypatch.setattr(gate, "CHAIN_OWNED", {"scripts/gates/check_alpha.py"})
        problems, ok = gate.check_owner_liveness(make_text=FAKE_MAKE, ci_text=FAKE_CI, root=fake.root)
        assert any("锚点缺失" in p for p in problems), problems
        assert ok == []

    def test_owner_not_invoked_is_red(self, gate, fake, monkeypatch):
        owner = fake.root / "scripts" / "gates" / "check_alpha.py"
        owner.write_text("_REGISTER_DECL = {}\n", encoding="utf-8")
        monkeypatch.setattr(gate, "OWNERS", [("覆盖率两行", "scripts/gates/check_alpha.py", ("_REGISTER_DECL",))])
        monkeypatch.setattr(gate, "CHAIN_OWNED", {"scripts/gates/check_alpha.py"})
        problems, ok = gate.check_owner_liveness(make_text=FAKE_MAKE, ci_text=FAKE_CI, root=fake.root)
        assert problems == [] and len(ok) == 1  # alpha 在 lint 配方里被调用
        # 「被跑」是 or 口径：make 链或 ci 任一即可（本地跑 / CI clone 跑都算活），所以要红必须两头都断
        make_cut = FAKE_MAKE.replace("$(PY) scripts/gates/check_alpha.py", "echo 1")
        ci_cut = FAKE_CI.replace("check_alpha.py", "check_gamma.py")
        problems, _ = gate.check_owner_liveness(make_text=FAKE_MAKE, ci_text=ci_cut, root=fake.root)
        assert problems == []  # 只剩 make 链，仍算活
        problems, _ = gate.check_owner_liveness(make_text=make_cut, ci_text=FAKE_CI, root=fake.root)
        assert problems == []  # 只剩 ci 调用点，也算活（CI clone 里跑）
        problems, _ = gate.check_owner_liveness(make_text=make_cut, ci_text=ci_cut, root=fake.root)
        assert any("写了没人跑" in p for p in problems), problems

    def test_self_wiring_red_when_not_in_chain(self, gate):
        problems = gate.self_check_wiring(make_text=FAKE_MAKE, ci_text=FAKE_CI, stem="check_registration_consistency")
        assert len(problems) == 1 and "本门自身未接入链" in problems[0], problems
        wired_make = FAKE_MAKE.replace(
            "format:\n\t$(PY) scripts/gates/check_beta.py",
            "format:\n\t$(PY) scripts/gates/check_beta.py\n\nregistration:\n\t$(PY) scripts/gates/check_registration_consistency.py",
        ).replace("gates: lint format", "gates: lint format registration")
        assert (
            gate.self_check_wiring(make_text=wired_make, ci_text=FAKE_CI, stem="check_registration_consistency") == []
        )

    def test_items_table_has_authority_for_every_key(self, gate):
        """判定表不许出现「有键无权威源」的项——那正是本门要收的口。"""
        assert set(gate.BASELINE_KEYS) == set(gate.ITEMS)
        for key, spec in gate.ITEMS.items():
            assert spec["authority"] in {"self", "baseline"}, key
            assert spec["row"] in {"门禁总数", "静态检查", "全量测试"}, key


# ══ F 组：受检面披露 ════════════════════════════════════════════════════
class TestDisclosure:
    def test_narrative_numbers_are_disclosed_not_judged(self, gate, fake):
        """括号外的历史叙述（999）只披露计数，不参与对账——否则「历史快照」与「当前口径」同形。"""
        register_text = fake.register.read_text(encoding="utf-8")
        problems, _, _, per_row = gate.check_declared_numbers(fake.auth, register_text)
        assert problems == [], problems
        lines = gate.surface_disclosure(per_row, fake.auth, register_text=register_text, root=fake.root)
        assert len(lines) == 3, lines
        assert "裸数字 1 个" in lines[1], lines[1]
        assert "本门检其中 3 行" in lines[1], lines[1]

    def test_disclosure_reads_the_given_root_not_the_real_repo(self, gate, fake):
        """披露也必须跟着 `root` 走（CE §76 的同类）：漏传 root 会读到真仓库的 18/5。"""
        lines = gate.surface_disclosure({}, {}, register_text=fake.register.read_text(encoding="utf-8"), root=fake.root)
        assert "在盘分册 2 份" in lines[0], lines[0]
        assert "§2.2 编号 zh 2 条目、en 2 条目" in lines[0], lines[0]


# ══ E 组：真实树（只读）════════════════════════════════════════════════
class TestRealTree:
    def test_gate_passes_on_real_tree(self, gate):
        assert gate.main([]) == 0

    def test_main_reports_every_surface_line_on_red(self, gate, monkeypatch, capsys):
        """报红路径也必须打印 `[SURFACE]`——CE §76：披露要落在每一条输出路径。"""
        monkeypatch.setattr(gate, "compute_authorities", lambda **kw: ({}, [], ["人造红"]))
        assert gate.main([]) == 1
        err = capsys.readouterr().err
        assert err.count("[SURFACE]") == 3

    def test_real_authorities_equal_baseline(self, gate):
        auth, _, problems = gate.compute_authorities(verify_mypy=False, root=PROJECT_ROOT)
        assert problems == [], problems
        for key, spec in gate.ITEMS.items():
            if spec["authority"] == "baseline":
                continue
            assert key in auth, key

    def test_owners_and_self_wiring_pass_on_real_tree(self, gate):
        make_text = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
        ci_text = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        problems, ok = gate.check_owner_liveness(make_text=make_text, ci_text=ci_text, root=PROJECT_ROOT)
        assert problems == [], problems
        assert len(ok) == len(gate.OWNERS)
        assert gate.self_check_wiring(make_text=make_text, ci_text=ci_text) == []

    def test_ci_snapshot_step_runs_after_pytest(self):
        """CL 轮：CI 树变异步骤必须排在 pytest 之后（顺序锁）。

        改前实测（2026-10-25）：`Generate static-check snapshot` 在 pytest **之前**
        把 `docs/history/static_report_<日期>.md` 写进树，该文件计入 ruff 格式化面
        （+1）⇒ 本门「已格式化」复算漂移（BASELINE 975 vs 复算 976）⇒
        `test_gate_passes_on_real_tree` 与本例邻居两条真树锁在 CI 三档全红，
        而本地 fresh clone 全绿——**差异不是代码，是步骤顺序造成的树状态差**。
        锁语义：快照生成步骤的序号必须大于 pytest 步骤的序号。
        """
        ci_text = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        names = [
            line.strip()[len("- name:") :].strip()
            for line in ci_text.splitlines()
            if line.strip().startswith("- name:")
        ]
        pytest_idx = next(i for i, n in enumerate(names) if n.startswith("Run tests with coverage"))
        snapshot_idx = next(i for i, n in enumerate(names) if n.startswith("Generate static-check snapshot"))
        assert snapshot_idx > pytest_idx, (
            f"CI 步骤顺序回退：Generate static-check snapshot（#{snapshot_idx}）又排到了 "
            f"Run tests with coverage（#{pytest_idx}）之前——它写入的 static_report_*.md "
            "会改变 ruff 格式化计数，使登记门禁在 pytest 内漂移红（CL 轮实测）"
        )
