"""CG 轮：门禁调用口径对账 `scripts/gates/check_invocation_caliber.py` 的回归锁。

纪律：**零 LLM、$0**；除标记「真实树」的 6 例外，全部判定跑在 tmp 目录里的合成调用面上
（合成 Makefile / workflow / 门禁脚本 / BASELINE / 登记册 / 登记表），不写真实文件。

为什么这些锁必须存在（2026-10-24 只读复算，两棵树：**改前树** = 未提交 `00e8c24d` + 历轮未提交改动，
再移除本轮四个新文件（本门、本文件、变异工装、登记表）并回退本轮 `Makefile` 目标与链条目、本轮 ci 步骤；
**中间态树** = 改前树 + 本门脚本 + 本轮接线。标「中间态」的读数取自后者，其余取自前者；构造命令见门禁
docstring 的树注与分册 §4 C 段）：
- 非阻断判据按子串搜步骤正文时 CF 复算 **3/26**，按 YAML 结构复算 **2/27**（改前树）——多出来的那条是
  ci.yml 注释里的 `continue-on-error: true` 字样被当成当前键，而这个数已进 BASELINE 与 §1；中间态树同一
  对判据是 **2/28**（本轮 CI 步骤 +1 个阻断项）；
- 只比「`make gates` ↔ ci.yml」一对面得 **1** 处开关不等，比所有面两两得 **3** 处；两处理由只写在
  Makefile 与 perf.yml 的**注释**里，注释不会被复算；
- `check_prompt_artifacts` 不在 `make gates` 链上、CI 又裸跑不带 `--strict` ⇒「已接线」为真而「强制」为假；
- 同一门禁的命令行开关由 shell 变量注入（perf.yml `$STRICT_FLAG`）⇒ 静态普查看不到实际口径；
- 声明 71 个开关里（中间态；改前树为 69 个 / 23 道有 argparse），初测用「文件里出现过该开关 token 就算读者」
  得 52 有锁 / 0 无读者；收紧成「同一文件既出现该开关、又点名这道门」后 **33** 条从未有读者的开关第一次露面
  （其中判据档 **10** 条）。改前树同一分类是 **31** 条 / 判据档 **9** 条——差的正是本门自己声明的那一对，
  判据档里少的那一条是它的 `--list`。

本文件自身也是一个读者：它点名 `check_invocation_caliber` 并传 `--list` / `--quiet`，正是这两个开关的
代码锁（改前 `--list` 是全仓最后一条「判据档无读者」红）。CG 轮把真实树的锁写成第二份硬编码字面量
（在盘 31 / 链上 17 / 声明 71 / 登记 9 / 结构 2-28-30-29-30 / 登记表 15 条）；CH 轮新增一道门把这些分母
全部移动（32 / 18 / 73 / 8 / 2-29-31-30-31 / 14 条）后只刷了 BASELINE 与 §1，四条锁 r01/r03/r04/r05
红了一整轮无人见，收口声明还误记「随登记文本落盘转绿」——硬编码锁不读登记文本，这句话对它们不可能
成立（**CI 轮（2026-10-24）勘误并收口**，证据链见分册 `docs/reviews/CLOSING_TREE_SPLIT_CI_2026-10-24.md`）。
**CI 轮起真树锁的期望值一律从 BASELINE 读取**（`gates` / `invocation` 两节，与 CG 门同一权威源），
本文件不再复制第二份；保留的字面量只有「性质锁」（调用面 5 / 幽灵 0 / 兜底与动态 1-1 /
判据档无读者 0）与分母恒等式——性质不会因增删一道门而移动，分母会。

变异验证（70 个锚点 + 1 个中性对照，两轮）查出两处判据缺口，本轮一并补上并各配锁：
- `set +e` 只在与门禁同一行时才被认成兜底，单独一行的区块级 `set +e` 静默放过（d04/d05/d06）；
- 登记册 §1 同名行折叠成一行，第二行人工的口径从不被读（e16 管标签不同、e18 管标签逐字相同——
  后者才是「按标签收成列表」这条实现真正被锁住的地方，只写 e16 时 M59 是永久存活变异）；
  另补注释行不成为面/兜底层（a06）、`--f=v` 写法（c06）、门禁互相点名不算调用面（b05）、
  `no-face` 陈旧判定（b06）、`manual-only` 细节开关要能在现场找到（e15）、`〔当前口径〕`前缀（e17）、
  通过行带数（f06）、缺 `@现场`（e08 第九例）。

分组（`--collect-only` 实测 66 例）：A 结构判据 7 例 / B 调用面归属 6 例 / C 有效值口径 6 例 /
D 兜底层与动态注入 6 例 / E 活性与登记表 26 例（含 9 种坏登记参数化）/ F CLI 与前提 9 例（含 4 种仓库级前提）/
R 真实树 6 例。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import re
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_GATE_SCRIPT = PROJECT_ROOT / "scripts" / "gates" / "check_invocation_caliber.py"
_CF_SCRIPT = PROJECT_ROOT / "scripts" / "gates" / "check_registration_consistency.py"


def _load_gate(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ══ 合成树：6 道门 / 4 个调用面 / 13 个声明开关（每个数字都在断言里手算）═══════════
_ALPHA = '''"""合成的门 A：6 个声明开关，链与 CI 靠默认值对齐。"""

import argparse

DEFAULT_BASELINE = "docs/alpha_baseline.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE)
    parser.add_argument("--threshold", default="0.9")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--warn-only", action="store_true")
    parser.parse_args()
    return 0
'''

_BETA = '''"""合成的门 B：`--require-coverage` 只在 CI 传，`--skip-smoke` 只在手册里。"""

import argparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-coverage", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    parser.parse_args()
    return 0
'''

_PERF = '''"""合成的门 P：开关由 shell 变量注入；单面所以不参与跨面对账。"""

import argparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--baseline", default="docs/perf_baseline.json")
    parser.parse_args()
    return 0
'''

_CALIBER = '''"""合成树里的 CG 门自己：两个开关都没有面传（`--quiet` 呈现档、`--report` 范围档）。"""

import argparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--report", default="docs/out.md")
    parser.parse_args()
    return 0
'''

_PLAIN = '"""合成的无 argparse 门禁（不参与开关判定，但调用面归属照判）。\n\nprint("ok")\n'

_BLUEPRINT: dict[str, str] = {
    "Makefile": (
        "PY ?= python3\n"
        ".PHONY: gates alpha-check beta-check caliber-check weekly\n"
        "\n"
        "gates: alpha-check beta-check caliber-check  ## 全部阻断门禁\n"
        "\t@echo gates\n"
        "\n"
        "alpha-check:\n"
        "\t$(PY) scripts/gates/check_alpha.py --strict \\\n"
        "\t\t--baseline docs/alpha_baseline.json\n"
        "\n"
        "beta-check:\n"
        "\t$(PY) scripts/gates/check_beta.py\n"
        "\n"
        "caliber-check:\n"
        "\t$(PY) scripts/gates/check_invocation_caliber.py\n"
        "\n"
        "weekly:\n"
        "\t$(PY) scripts/gates/check_gamma.py --all\n"
    ),
    ".github/workflows/ci.yml": """name: Synth CI
on: push
jobs:
  gates:
    runs-on: ubuntu-latest
    steps:
      - name: Alpha gate
        if: github.event_name == 'push'
        run: |
          # 这一步曾经写成 continue-on-error: true，现在必须阻断
          python3 scripts/gates/check_alpha.py --strict
          echo "continue-on-error: true"
      - name: Beta gate (non-blocking)
        continue-on-error: true
        run: |
          python3 scripts/gates/check_beta.py --require-coverage || echo "::warning::beta 红不阻断"
      - name: Alpha soft weekly
        run: |
          python3 scripts/gates/check_alpha.py --warn-only
      - name: Caliber gate
        run: |
          python3 scripts/gates/check_invocation_caliber.py
""",
    ".github/workflows/perf.yml": """name: Synth perf
on: workflow_dispatch
jobs:
  perf:
    runs-on: ubuntu-latest
    steps:
      - name: Perf check
        run: |
          VERIFY_FLAG=""
          if [ "${{ inputs.verify }}" = "1" ]; then VERIFY_FLAG="--verify"; fi
          python3 scripts/gates/check_perf.py --baseline docs/perf_baseline.json $VERIFY_FLAG || true
""",
    "scripts/gates/check_alpha.py": _ALPHA,
    "scripts/gates/check_beta.py": _BETA,
    "scripts/gates/check_perf.py": _PERF,
    "scripts/gates/check_invocation_caliber.py": _CALIBER,
    "scripts/gates/check_gamma.py": _PLAIN,
    "scripts/gates/check_delta.py": _PLAIN,
    "experiments/run_synth.py": (
        '"""合成实验入口：`check_delta` 只被代码调用，不在任何门禁面上。"""\n\n'
        "import sys\n\nsys.path.insert(0, 'scripts/gates')\n"
        "import check_delta  # noqa: E402\n\ncheck_delta\n"
    ),
    "tests/test_alpha_lock.py": (
        '"""合成代码锁：既出现开关、又点名 check_alpha，才算读者。"""\n\n'
        "from pathlib import Path\n\nGATE = Path('scripts/gates/check_alpha.py')\n\n\n"
        'def test_json():\n    assert "--json" in GATE.read_text(encoding="utf-8")\n\n\n'
        'def test_list():\n    assert "--list" in GATE.read_text(encoding="utf-8")\n'
    ),
    "docs/BETA_MANUAL.md": "# beta 手动口径\n\n排障时手动跑：`python3 scripts/gates/check_beta.py --skip-smoke`\n",
    "docs/README_NO_NAME.md": "这里只出现开关 token，不出现门禁脚本名：`--require-coverage` / `--never` / `--verify`\n",
    "BASELINE.yaml": """gates:
  non_blocking_steps: 2
  blocking_steps: 2
  ci_unique_scripts: 3
  ci_call_sites: 4
  gate_steps: 4
  make_targets: 3
  make_commands: 3
invocation:
  disk_scripts: 6
  chain_scripts: 3
  faces: 4
  declared_flags: 13
  passed_flags: 6
  locked_flags: 2
  registered_unread: 1
  caliber_unread: 0
  presentation_unread: 4
  flag_diffs: 2
  swallow_steps: 2
  dynamic_steps: 1
  ghost_flags: 0
""",
    "docs/PROJECT_STATUS_REGISTER.md": """# Synth 登记册

## 1. 现状快照

| 维度 | 数值 | 验证入口 |
|---|---|---|
| 门禁总数 | 〔当前口径（示例）：门禁脚本 6 / 非阻断步骤 2 / 阻断步骤 2〕 | `make gates` |
| 调用口径（CG 轮） | 合成树：6 道门 / 4 个面 / 13 个开关 | 〔当前口径：在盘门禁 6 / 链上面脚本 3 / 调用面数 4 / 声明开关 13 / 传过开关 6 / 代码锁开关 2 / 登记无读者 1 / 判据档无读者 0 / 范围呈现档无读者 4 / 跨面不对称 2 / 兜底步骤 2 / 动态注入步骤 1 / 幽灵开关 0〕 | `make invocation-caliber` |

## 2. 阻断项

| 维度 | 数值 |
|---|---|
| 调用口径 | 〔当前口径（历史小节里的同名行）：在盘门禁 999〕 |
""",
    "docs/invocation_caliber_allowlist.txt": """# 合成登记表
flag-diff check_alpha make:gates>wf:ci.yml # 链上带 --strict，CI 多一个 --warn-only 周检档 @.github/workflows/ci.yml
flag-diff check_beta make:gates>wf:ci.yml # CI 覆盖率作业要 --require-coverage，链上不必 @.github/workflows/ci.yml
no-face check_delta programmatic-only # 只由合成实验入口以代码方式调用 @experiments/run_synth.py
soft-layer ci.yml::Beta-gate-(non-blocking) coe+shell-or # 步骤键与 shell 兜底两层同用，删任一层都无人知 @.github/workflows/ci.yml
dynamic-flag perf.yml::Perf-check VERIFY_FLAG # --verify 由 workflow_dispatch 输入决定，静态普查看不到 @.github/workflows/perf.yml
manual-only check_beta --skip-smoke # 排障时手动跑，口径见手册 @docs/BETA_MANUAL.md
""",
}


def _assert_authority_complete(mod: Any, counts: dict[str, int]) -> None:
    """两条 `counts` 装配（合成树 / 真实树）都必须覆盖判定五要读的键。

    漏一个键的后果不对称：真实树锁直接 KeyError，而门禁自己把「少装配一项」打成不判——
    所以完备性要在装配处断言，而不是等某次断言恰好读到那个键才发现。
    """
    required = set(mod.ITEMS.values()) | set(mod.XCHECK_COUNT_KEYS.values())
    missing = sorted(required - set(counts))
    assert missing == [], f"counts 装配缺键：{missing}"


class Synth:
    """合成树 + 被改指到合成路径的 CG 门。"""

    ALLOW = "docs/invocation_caliber_allowlist.txt"
    CI = ".github/workflows/ci.yml"
    PERF = ".github/workflows/perf.yml"
    REGISTER = "docs/PROJECT_STATUS_REGISTER.md"

    def __init__(self, mod: Any, root: Path) -> None:
        self.mod = mod
        self.root = root

    # ── 变异 = 重写某个合成文件
    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8")

    def mutate(self, rel: str, old: str, new: str) -> None:
        text = self.read(rel)
        assert old in text, f"合成树里找不到 {old!r}"
        self.write(rel, text.replace(old, new))

    def append_allow(self, line: str) -> None:
        self.write(self.ALLOW, self.read(self.ALLOW) + line + "\n")

    def drop_allow(self, needle: str) -> None:
        kept = [line for line in self.read(self.ALLOW).splitlines() if needle not in line]
        self.write(self.ALLOW, "\n".join(kept) + "\n")

    # ── 直接调判定面（不经 CLI）
    def steps(self) -> list[Any]:
        return self.mod.workflow_steps()

    def table(self) -> dict[str, dict[str, dict[str, str | None]]]:
        return self.mod.invocations(self.read("Makefile"), self.steps())[0]

    def disk(self) -> list[str]:
        return sorted(p.stem for p in self.mod.GATES_DIR.glob("*.py"))

    def allow(self) -> tuple[dict, list[str]]:
        return self.mod.parse_allowlist(self.mod.ALLOWLIST)

    def specs(self) -> dict[str, dict]:
        return {stem: self.mod.flag_specs(stem) for stem in self.disk()}

    def blocking(self) -> tuple[list[str], list[str], list[str], dict[str, int]]:
        return self.mod.judge_blocking(self.steps(), self.allow()[0])

    def liveness(self) -> tuple[list[str], list[str], list[str], dict[str, int]]:
        return self.mod.judge_liveness(disk=self.disk(), table=self.table(), allow=self.allow()[0])

    def flags(self) -> tuple[list[str], list[str], list[str], int]:
        return self.mod.judge_flags(table=self.table(), allow=self.allow()[0], specs_cache=self.specs())

    def counts(self) -> dict[str, int]:
        """与 `main()` 同一套装配，供结构断言（不经 CLI 的红/绿）。"""
        steps = self.steps()
        table = self.table()
        chain = self.mod.make_faces(self.read("Makefile")).get(self.mod.FACE_CHAIN, [])
        ci = [s for s in steps if s.gate_stems() and s.file == "ci.yml"]
        counts = {
            **self.blocking()[3],
            **self.liveness()[3],
            "disk_scripts": len(self.disk()),
            "chain_scripts": len({s for line in chain for s in self.mod._GATES_REF_RE.findall(line)}),
            "faces": len({face for per in table.values() for face in per}),
            "flag_diffs": self.flags()[3],
            "ghost_flags": len(self.mod._ghost_flags(table, self.specs())),
            "ci_unique_scripts": len({s for st in ci for s in st.gate_stems()}),
            "ci_call_sites": sum(len(st.gate_stems()) for st in ci),
            "make_targets": len(self.mod.make_gate_deps(self.read("Makefile"))),
            "make_commands": len(chain),
        }
        _assert_authority_complete(self.mod, counts)
        return counts

    # ── CLI
    def run(self, argv: list[str] | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = self.mod.main(list(argv or []))
        return rc, out.getvalue(), err.getvalue()

    def problems(self, argv: list[str] | None = None) -> list[str]:
        _, _, err = self.run(argv)
        return [line[4:] for line in err.splitlines() if line.startswith("  - ")]


@pytest.fixture
def synth(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Synth:
    mod = _load_gate("aitester_cg_synth", _GATE_SCRIPT)
    tree = Synth(mod, tmp_path)
    for rel, text in _BLUEPRINT.items():
        tree.write(rel, text)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "MAKEFILE", tmp_path / "Makefile")
    monkeypatch.setattr(mod, "WF_DIR", tmp_path / ".github/workflows")
    monkeypatch.setattr(mod, "GATES_DIR", tmp_path / "scripts/gates")
    monkeypatch.setattr(mod, "BASELINE", tmp_path / "BASELINE.yaml")
    monkeypatch.setattr(mod, "REGISTER", tmp_path / tree.REGISTER)
    monkeypatch.setattr(mod, "ALLOWLIST", tmp_path / tree.ALLOW)
    return tree


# ══ A 组：阻断性按结构，不按子串 ═══════════════════════════════════════
def test_a00_read_side_follows_the_repointed_tree(synth: Synth) -> None:
    """锁（本轮实现期发现）：读侧参数不能把路径固化在 `def` 时刻，否则「合成树」是假的。

    改前 `workflow_steps(wf_dir=WF_DIR)` / `_reader_index(root=REPO_ROOT)` 这类默认值在导入时就绑定，
    monkeypatch 无效 ⇒ 合成锁实际读的是真仓库，绿色与被测代码无关。
    """
    assert {s.file for s in synth.steps()} == {"ci.yml", "perf.yml"}
    assert "Check prompt artifacts" not in {s.name for s in synth.steps()}  # 真仓库的步骤名一个都不许出现
    assert {name for name, _, _ in synth.mod._reader_index()} == {"test_alpha_lock.py", "run_synth.py"}
    assert synth.mod.programmatic_callers("check_delta") == ["experiments/run_synth.py"]
    assert synth.root / "scripts/gates" == synth.mod.GATES_DIR


def test_a01_comment_and_echo_coe_are_not_step_keys(synth: Synth) -> None:
    """①：Alpha 步骤正文里 `continue-on-error: true` 出现两次（注释 + echo），结构判据仍算阻断。"""
    alpha = next(s for s in synth.steps() if s.file == "ci.yml" and s.name == "Alpha gate")
    assert "continue-on-error: true" in " ".join(alpha.commands)
    assert alpha.continue_on_error is False and alpha.non_blocking_layers() == []
    beta = next(s for s in synth.steps() if "Beta" in s.name)
    assert beta.non_blocking_layers() == ["coe", "shell-or"]  # 真键（缩进 8）+ `|| echo`
    counts = synth.blocking()[3]
    assert (counts["gate_steps_ci"], counts["non_blocking_ci"], counts["blocking_ci"]) == (4, 2, 2)


def test_a02_indent_ten_coe_text_is_still_blocking(synth: Synth) -> None:
    """①续：同一句话放进 run 区块（缩进 ≥10）也不算键——缩进决定它是键还是正文。"""
    synth.write(
        synth.CI,
        synth.read(synth.CI)
        + """      - name: Perf echo
        run: |
          echo "continue-on-error: true"
          python3 scripts/gates/check_perf.py --verify --baseline docs/perf_baseline.json
""",
    )
    step = next(s for s in synth.steps() if s.name == "Perf echo")
    assert step.continue_on_error is False and step.non_blocking_layers() == []
    counts = synth.blocking()[3]
    assert counts["non_blocking_ci"] == 2 and counts["gate_steps_ci"] == 5  # 多一步，但没多一条非阻断


def test_a03_real_coe_key_on_strict_step_is_contradiction(synth: Synth) -> None:
    """①反向 + 口径自相矛盾：真把键加上，这一步就转非阻断；而它传的是 `--strict`（最严档）。"""
    synth.mutate(synth.CI, "      - name: Alpha gate\n", "      - name: Alpha gate\n        continue-on-error: true\n")
    counts = synth.blocking()[3]
    assert (counts["non_blocking_ci"], counts["blocking_ci"]) == (3, 1)
    problems = synth.problems()
    assert any(p.startswith("口径自相矛盾：ci.yml::Alpha-gate") for p in problems)


def test_a04_green_tree_passes_and_discloses_surface(synth: Synth) -> None:
    """合成控制树必须真的全绿：否则下面每条锚定的「红」都可能只是既有红。"""
    rc, out, err = synth.run()
    assert rc == 0, err
    assert "在盘 6 道门各有归属" in out
    assert "[SURFACE] 阻断性判定面" in out and "范围与呈现档 4" in out
    assert "读者四类 = 调用面 6 / 代码锁 2 / 登记表 1" in out


def test_a05_explicit_false_coe_key_stays_blocking(synth: Synth) -> None:
    """键的**值**也是判据：`continue-on-error: false` 是合法写法，意思是阻断。

    只看「这一行是不是 `continue-on-error:`」的门会把阻断步骤数成非阻断——本轮要收的正是这种
    「在场即算」的子串口径，所以值必须解析。
    """
    synth.mutate(synth.CI, "      - name: Alpha gate\n", "      - name: Alpha gate\n        continue-on-error: false\n")
    alpha = next(s for s in synth.steps() if s.file == "ci.yml" and s.name == "Alpha gate")
    assert alpha.continue_on_error is False and alpha.non_blocking_layers() == []
    counts = synth.blocking()[3]
    assert (counts["non_blocking_ci"], counts["blocking_ci"]) == (2, 2)
    assert synth.problems() == []


def test_a06_commented_gate_command_is_neither_a_face_nor_a_layer(synth: Synth) -> None:
    """①的第二副面孔：`run` 区块里被注释掉的一条门禁命令行，读成命令就同时造出面与兜底层。

    真实树的 ci.yml 正是这种形状——两处「手动流程说明」写在注释里，含脚本名也含开关。
    注释行既不进 `commands`（不产生调用面、不产生开关、不产生 `||` 兜底），也不进任何计数。
    """
    synth.mutate(
        synth.CI,
        "          python3 scripts/gates/check_invocation_caliber.py\n",
        '          # python3 scripts/gates/check_alpha.py --warn-only || echo "曾经的兜底"\n'
        "          python3 scripts/gates/check_invocation_caliber.py\n",
    )
    caliber = next(s for s in synth.steps() if s.name == "Caliber gate")
    assert caliber.gate_stems() == ["check_invocation_caliber"]
    assert caliber.non_blocking_layers() == []
    counts = synth.counts()
    assert (counts["non_blocking_ci"], counts["swallow_steps"]) == (2, 2)
    assert synth.problems() == []


# ══ B 组：调用面归属（make 目标 ≠ `make gates` 链）═══════════════════════
def test_b01_make_target_is_not_the_gates_chain(synth: Synth) -> None:
    """⑥：`check_gamma` 在 `make weekly` 面上，但不在 `make gates` 链上——归属与「链上」是两个数。"""
    faces = synth.mod.make_faces(synth.read("Makefile"))
    assert sorted(faces) == ["make:gates", "make:weekly"]
    chain = faces["make:gates"]
    assert len(chain) == 3  # 续行合成一条命令，而不是拆成两条
    assert "--baseline docs/alpha_baseline.json" in chain[0] and chain[0].startswith(
        "$(PY) scripts/gates/check_alpha.py"
    )
    assert all("check_gamma" not in line for line in chain)
    counts = synth.counts()
    assert (counts["disk_scripts"], counts["chain_scripts"], counts["faces"]) == (6, 3, 4)


def test_b02_orphan_script_is_red_until_registered(synth: Synth) -> None:
    """⑥：在盘而三个面都不调用 ⇒ 红；登记 `no-face ... zero-faces` 后该红消失（数字债另计）。"""
    synth.write("scripts/gates/check_orphan.py", _PLAIN)
    assert any(p.startswith("调用面归属：check_orphan") and "写了没人跑" in p for p in synth.problems())
    synth.append_allow("no-face check_orphan zero-faces # 历史遗留，等下一轮决定去留 @docs/BETA_MANUAL.md")
    assert not any("调用面归属：check_orphan" in p for p in synth.problems())


def test_b03_programmatic_only_needs_registration(synth: Synth) -> None:
    """⑥：`check_delta` 只被 experiments 以 import 调用——「有读者」不等于「在链上」。"""
    synth.drop_allow("no-face check_delta")
    problems = synth.problems()
    assert any(p.startswith("调用面归属：check_delta") and "experiments/run_synth.py" in p for p in problems)
    assert any(p.startswith("登记表失效：('no-face', 'check_delta'") is False for p in problems)


def test_b04_self_gate_unwired_is_red(synth: Synth) -> None:
    """③续：本门从 `gates:` 依赖里摘掉 ⇒ 自己判自己没接线；链上脚本数同时被 BASELINE 钉住。"""
    synth.mutate("Makefile", "gates: alpha-check beta-check caliber-check", "gates: alpha-check beta-check")
    problems = synth.problems()
    assert any(p.startswith("本门自身未接入") and "check_invocation_caliber" in p for p in problems)
    assert any("invocation.chain_scripts" in p for p in problems)


def test_b05_gate_prose_naming_a_gate_is_not_a_caller(synth: Synth) -> None:
    """门禁源码里点名另一道门不算调用面——归属问的是「谁执行它」，不是「谁提到它」。

    真实树就是这个形状：`check_registration_consistency.py` 把几道门列成拥有者清单。若把
    「同目录文件正文含该 stem」当代码调用，零面的门会被改判成「只被别的门调用」，那条
    `no-face … zero-faces` 登记还会顺带变成陈旧——口径就从执行滑到文本，正是本轮的病灶。
    """
    synth.write("scripts/gates/check_lone.py", _PLAIN)
    synth.mutate("scripts/gates/check_alpha.py", "import argparse", "import argparse  # 与 check_lone 同一口径")
    lone = [p for p in synth.problems() if p.startswith("调用面归属：check_lone")]
    assert any("写了没人跑" in p for p in lone), lone
    assert not any("以代码方式调用" in p for p in lone), lone


def test_b06_no_face_entry_goes_stale_the_day_a_face_appears(synth: Synth) -> None:
    """`no-face` 类登记的失效判据：脚本一旦真被某个面调用，豁免必须当场失效变红。

    判定一里的 staleness 分支与判定三/四各自独立——不查它，「曾经没人跑」这条豁免会
    永久替一个现在天天跑的门挡住归属红。
    """
    synth.mutate(
        synth.CI,
        "          python3 scripts/gates/check_invocation_caliber.py\n",
        "          python3 scripts/gates/check_invocation_caliber.py\n          python3 scripts/gates/check_delta.py\n",
    )
    assert any("登记表失效" in p and "no-face" in p and "check_delta" in p for p in synth.problems()), synth.problems()


# ══ C 组：开关相等按有效值，不按文本 ═══════════════════════════════════
def test_c01_explicit_value_equal_to_default_is_not_a_diff(synth: Synth) -> None:
    """约定 2：链上显式传 `--baseline docs/alpha_baseline.json`、CI 靠默认值 ⇒ 同一口径，不红。"""
    table = synth.table()
    chain = synth.mod.effective_flags("check_alpha", table["check_alpha"]["make:gates"])
    ci = synth.mod.effective_flags("check_alpha", table["check_alpha"]["wf:ci.yml"])
    assert chain["--baseline"] == ci["--baseline"] == "docs/alpha_baseline.json"
    assert synth.mod._face_diff(chain, ci) == ["--warn-only=—/set"]
    assert synth.flags()[0] == []


def test_c02_default_change_creates_cross_face_asymmetry(synth: Synth) -> None:
    """约定 2 的反面：默认值一改，「命令行文本没变」的两面立刻不再同口径 ⇒ 必须红。"""
    synth.mutate(
        "scripts/gates/check_alpha.py",
        'DEFAULT_BASELINE = "docs/alpha_baseline.json"',
        'DEFAULT_BASELINE = "docs/moved.json"',
    )
    chain = synth.mod.effective_flags("check_alpha", synth.table()["check_alpha"]["make:gates"])
    ci = synth.mod.effective_flags("check_alpha", synth.table()["check_alpha"]["wf:ci.yml"])
    assert chain["--baseline"] == "docs/alpha_baseline.json" and ci["--baseline"] == "docs/moved.json"
    # 这条不对称已被登记（合成表里那条 flag-diff），所以先删登记才看得到红——登记遮住了它，正是它的作用
    assert not any(p.startswith("跨面开关：check_alpha") for p in synth.problems())
    synth.drop_allow("flag-diff check_alpha")
    problems = synth.problems()
    assert any(p.startswith("跨面开关：check_alpha") and "--baseline=" in p for p in problems)


def test_c03_store_true_presence_is_a_diff(synth: Synth) -> None:
    """②：`store_true` 两侧值都是 None ⇒ 按「在场」记 `set`，否则最典型的一类不对称会被静默漏判。"""
    eff = synth.mod.effective_flags("check_beta", synth.table()["check_beta"]["wf:ci.yml"])
    assert eff["--require-coverage"] == "set"
    synth.drop_allow("flag-diff check_beta")
    assert any("--require-coverage=—/set" in p for p in synth.problems())


def test_c04_registered_diff_ok_and_stale_when_faces_align(synth: Synth) -> None:
    """②：登记过的不对称不红；两侧真对齐后那条登记必须红（豁免保护的东西变了）。"""
    assert synth.problems() == []
    synth.mutate(
        "Makefile",
        "\t$(PY) scripts/gates/check_beta.py\n",
        "\t$(PY) scripts/gates/check_beta.py --require-coverage\n",
    )
    problems = synth.problems()
    assert any(p.startswith("登记表失效：('flag-diff', 'check_beta'") and "两侧现已一致" in p for p in problems)
    assert not any(p.startswith("跨面开关：check_beta") for p in problems)


def test_c05_ghost_flag_is_red_and_number_locked(synth: Synth) -> None:
    """判定二反：面上传了脚本没声明的开关 ⇒ 真跑是 argparse 退出码 2；幽灵数同时被 BASELINE 钉住。"""
    synth.mutate(synth.PERF, " $VERIFY_FLAG || true", " $VERIFY_FLAG --nope || true")
    problems = synth.problems()
    assert any(p.startswith("幽灵开关：wf:perf.yml 给 check_perf 传 --nope") for p in problems)
    assert any("invocation.ghost_flags` = 0，本门复算 1" in p for p in problems)


def test_c06_equals_form_is_split_before_comparing(synth: Synth) -> None:
    """约定 2 的写法维度：`--threshold=0.9` 与 `--threshold 0.9` 是同一个入参，也同一个有效值。

    不拆 `=` 的话，这个 token 既不在声明面（argparse 里是 `--threshold`）也不在两侧的比较里相等
    ⇒ 凭空造出一条跨面不对称 + 一个幽灵开关——「同一口径的两种写法」变成「两种口径」。
    """
    synth.mutate(
        "Makefile",
        "\t\t--baseline docs/alpha_baseline.json\n",
        "\t\t--baseline docs/alpha_baseline.json --threshold=0.9\n",
    )
    counts = synth.counts()
    assert (counts["flag_diffs"], counts["ghost_flags"]) == (2, 0)
    assert counts["passed_flags"] == 7  # --threshold 真被链上传了：分母动一格，口径没多一格
    problems = synth.problems()
    assert not any(p.startswith(("跨面开关", "幽灵开关")) for p in problems), problems
    assert any("传过开关" in p for p in problems), problems  # 唯一后果是登记数要刷新


# ══ D 组：多层兜底与动态注入 ═══════════════════════════════════════════
def test_d01_two_soft_layers_must_be_registered(synth: Synth) -> None:
    """④：单层不阻断不红；两层同用（步骤键 + shell 兜底）必须登记，删任一层都无人知。"""
    assert next(s for s in synth.steps() if s.file == "perf.yml").non_blocking_layers() == ["shell-or"]
    synth.mutate(
        synth.PERF, "      - name: Perf check\n", "      - name: Perf check\n        continue-on-error: true\n"
    )
    problems = synth.problems()
    assert any(p.startswith("多层兜底：perf.yml::Perf-check") and "coe+shell-or" in p for p in problems)
    synth.append_allow(
        "soft-layer perf.yml::Perf-check coe+shell-or # 两层同用，删任一层都不改变「永不红」 @.github/workflows/perf.yml"
    )
    assert not any(p.startswith("多层兜底") for p in synth.problems())


def test_d02_dynamic_injection_is_keyed_by_variable_name(synth: Synth) -> None:
    """⑤：登记的细节就是变量名；换变量名等于换一个口径，旧登记立刻失效、新注入立刻红。"""
    assert synth.blocking()[3]["dynamic_steps"] == 1
    synth.mutate(synth.PERF, "VERIFY_FLAG", "CHECK_FLAG")
    problems = synth.problems()
    assert any(p.startswith("动态注入：perf.yml::Perf-check") and "CHECK_FLAG" in p for p in problems)
    assert any(p.startswith("登记表失效：('dynamic-flag'") for p in problems)


def test_d03_warn_only_is_a_layer_of_its_own(synth: Synth) -> None:
    """⑩相关：`--warn-only` 与步骤键、shell 兜底并列为三层之一；与 shell 兜底同用即多层。"""
    soft = next(s for s in synth.steps() if s.name == "Alpha soft weekly")
    assert soft.non_blocking_layers() == ["warn-only"]
    synth.mutate(
        synth.CI,
        "          python3 scripts/gates/check_alpha.py --warn-only\n",
        "          python3 scripts/gates/check_alpha.py --warn-only || true\n",
    )
    problems = synth.problems()
    assert any(p.startswith("多层兜底：ci.yml::Alpha-soft-weekly") and "warn-only+shell-or" in p for p in problems)


def test_d04_set_plus_e_on_the_gate_line_is_a_soft_layer(synth: Synth) -> None:
    """第三层的第二种写法：`set +e` 与门禁同行时，那一行的退出码已经不被 shell 负责。"""
    synth.mutate(
        synth.CI,
        "          python3 scripts/gates/check_invocation_caliber.py\n",
        "          set +e; python3 scripts/gates/check_invocation_caliber.py\n",
    )
    caliber = next(s for s in synth.steps() if s.name == "Caliber gate")
    assert caliber.non_blocking_layers() == ["shell-or"]
    assert synth.blocking()[3]["non_blocking_ci"] == 3


def test_d05_set_plus_e_scopes_the_block_not_the_line(synth: Synth) -> None:
    """`set +e` 单独一行时作用域覆盖其后整块——只看门禁那一行会把它读成阻断。"""
    synth.mutate(
        synth.CI,
        "          python3 scripts/gates/check_invocation_caliber.py\n",
        "          set +e\n          python3 scripts/gates/check_invocation_caliber.py\n",
    )
    caliber = next(s for s in synth.steps() if s.name == "Caliber gate")
    assert caliber.swallow is True
    counts = synth.blocking()[3]
    assert (counts["swallow_steps"], counts["non_blocking_ci"]) == (3, 3)


def test_d06_set_e_before_the_gate_restores_blocking(synth: Synth) -> None:
    """回补 `set -e` 之后跑的门禁仍算阻断：只认「区块里出现过 set +e」会把严格档误判成软档。"""
    synth.mutate(
        synth.CI,
        "          python3 scripts/gates/check_invocation_caliber.py\n",
        "          set +e\n          echo warmup\n          set -e\n"
        "          python3 scripts/gates/check_invocation_caliber.py\n",
    )
    caliber = next(s for s in synth.steps() if s.name == "Caliber gate")
    assert caliber.non_blocking_layers() == []
    assert synth.blocking()[3]["non_blocking_ci"] == 2
    assert synth.problems() == []


# ══ E 组：判定四（开关活性）与登记表审计 ═══════════════════════════════
def test_e01_loose_reader_rule_is_not_a_lock(synth: Synth) -> None:
    """⑦：token 出现在文件里不等于读者——同一文件必须既出现该开关、又点名这道门（正文或文件名）。"""
    assert (synth.liveness()[3]["locked_flags"], synth.liveness()[3]["caliber_unread"]) == (2, 0)
    synth.write(
        "tests/check_orphan_tokens.py",
        '"""只有 token，既不点名门禁、文件名也不含门名核心。"""\n\nFLAGS = ["--json", "--list"]\n',
    )
    synth.write("tests/test_alpha_lock.py", '"""空壳：文件还在，但既无开关 token 也无门禁名。"""\n\nassert True\n')
    problems, _, _, counts = synth.liveness()
    assert counts["locked_flags"] == 0 and counts["caliber_unread"] == 1
    assert any(p.startswith("判据档无读者（放松档）：check_alpha 声明 --list") for p in problems)
    assert not any("check_alpha 声明 --json" in p for p in problems)  # `--json` 是呈现档，只记数不记红
    assert counts["presentation_unread"] == 5


def test_e02_registered_caliber_flag_and_its_staleness(synth: Synth) -> None:
    """约定 4：判据档可登记（写清谁手动跑）；一旦某面真传了它，这条登记立刻红。"""
    assert synth.liveness()[0] == []
    synth.mutate(
        synth.CI,
        "python3 scripts/gates/check_beta.py --require-coverage",
        "python3 scripts/gates/check_beta.py --require-coverage --skip-smoke",
    )
    problems, _, _, counts = synth.liveness()
    assert counts["registered_unread"] == 0
    assert any(p.startswith("登记表失效：('manual-only', 'check_beta', '--skip-smoke')") for p in problems)


def test_e03_unregistered_caliber_flag_is_red(synth: Synth) -> None:
    """约定 4：删掉那条 manual-only 登记 ⇒ 同一个开关立刻是红，而不是静默通过。"""
    synth.drop_allow("manual-only check_beta")
    problems = synth.liveness()[0]
    assert any(
        p.startswith("判据档无读者（放松档）：check_beta 声明 --skip-smoke") and "manual-only" in p for p in problems
    )


def test_e04_denominator_self_check_fires(synth: Synth) -> None:
    """约定 5：声明数 ≠ 四类读者之和 ⇒ 读者分类不互斥/不完备，本门自己的分母也进红。"""

    class _Lie(dict):
        def __len__(self) -> int:
            return super().__len__() + 1

    real = synth.mod.flag_specs
    synth.mod.flag_specs = lambda stem: _Lie(real(stem)) if stem == "check_beta" else real(stem)
    try:
        problems = synth.liveness()[0]
    finally:
        synth.mod.flag_specs = real
    assert any("本门分母自校验失败" in p and "读者分类必须互斥且完备" in p for p in problems)


def test_e05_cross_check_number_must_equal_baseline(synth: Synth) -> None:
    """约定 5：本门复算值还要等于 BASELINE——把 BASELINE 改 1 就红（登记数与实测的两条腿）。"""
    synth.mutate("BASELINE.yaml", "  non_blocking_steps: 2", "  non_blocking_steps: 3")
    problems = synth.problems()
    assert any(p.startswith("交叉核对：BASELINE `gates.non_blocking_steps` = 3，本门结构复算 = 2") for p in problems)


def test_e06_missing_register_row_is_red(synth: Synth) -> None:
    """§1 没有「调用口径」行 ⇒ 本门的复算值没有登记面：写了没人查（CF 轮那一族的反向）。"""
    synth.mutate(synth.REGISTER, "| 调用口径（CG 轮）", "| 别的维度（CG 轮）")
    assert any("未找到「调用口径」行" in p for p in synth.problems())


def test_e07_register_row_without_authority_is_red(synth: Synth) -> None:
    """括号里出现没有权威判定项的键 ⇒ 装饰性数字不算登记，要么补权威源要么删。"""
    synth.mutate(synth.REGISTER, " / 幽灵开关 0〕", " / 幽灵开关 0 / 顺手写一个 7〕")
    problems = synth.problems()
    assert any("无判定项" in p and "顺手写一个" in p for p in problems)


@pytest.mark.parametrize(
    ("line", "fragment"),
    [
        ("flag-diff check_alpha make:weekly>wf:ci.yml", "无理由"),
        ("no-face check_delta # 只有两段 @docs/README_NO_NAME.md", "畸形"),
        ("ghost-kind check_alpha zero-faces # 现场 @Makefile", "未知类别"),
        ("flag-diff check_beta make:gates>wf:ci.yml # 又登记一次 @Makefile", "重复登记"),
        (
            "flag-diff check_gone make:gates>wf:ci.yml # --require-coverage @.github/workflows/ci.yml",
            "已不在 scripts/gates/ 下",
        ),
        ("no-face check_delta zero-faces # 见 @docs/NOWHERE.md", "文件不存在"),
        ("flag-diff check_beta make:weekly>wf:ci.yml # --require-coverage @docs/README_NO_NAME.md", "正文不含主体"),
        (
            "flag-diff check_alpha make:weekly>wf:ci.yml # 现场没有 --ghost-flag @.github/workflows/ci.yml",
            "一个都找不到",
        ),
        ("flag-diff check_alpha make:weekly>wf:ci.yml # 两侧口径本就不同（理由没指现场）", "没有理由现场"),
    ],
    ids=["无理由", "畸形", "未知类别", "重复", "主体已删", "现场不存在", "现场不含主体", "开关不在现场", "缺现场锚点"],
)
def test_e08_allowlist_audit(synth: Synth, line: str, fragment: str) -> None:
    """登记表自身可审计：九种坏登记各计一条红——复算不了的理由等于没有理由。"""
    synth.append_allow(line)
    problems = synth.allow()[1]
    assert fragment in "\n".join(problems), problems


def test_e09_stale_entry_is_red_without_audit_trouble(synth: Synth) -> None:
    """第十条红是「条目失效」：登记审计全过，但豁免不再触发也必须红（判据归判定面）。"""
    synth.append_allow("manual-only check_gamma --never # 历史上手动跑过，现已删 @docs/README_NO_NAME.md")
    assert synth.allow()[1] == []
    assert any(p.startswith("登记表失效：('manual-only', 'check_gamma', '--never')") for p in synth.problems())


def test_e10_manual_only_skips_subject_containment(synth: Synth) -> None:
    """`manual-only` 的证据义务由开关 token 承担：现场不必点名门禁自己（源码里没有自己的名字）。"""
    synth.append_allow("manual-only check_perf --verify # 排障时手动跑，口径见 @docs/README_NO_NAME.md")
    assert not any("正文不含主体" in p for p in synth.allow()[1])


def test_e11_allowlist_absent_fails_closed(synth: Synth) -> None:
    """登记表缺席 ⇒ 不对称无处登记，全计红（fail-closed，而不是静默通过）。"""
    (synth.root / synth.ALLOW).unlink()
    problems = synth.problems()
    assert any("登记表缺席" in p for p in problems) and any(p.startswith("跨面开关：check_beta") for p in problems)


def test_e12_self_assembled_authority_absent_is_red(synth: Synth) -> None:
    """自产权威源缺位 ⇒ 红：`counts` 由本门自己装配，少一个键是代码坏了，不能打成不判。

    实现期真实踩到：`_real_counts` 漏 `flag_diffs` / `ghost_flags` 时真实树锁直接 KeyError，
    而门禁自己只会在登记面缺项时沉默——BASELINE 侧键缺席（登记债）才配 [SKIP]。
    """
    pytest.importorskip("yaml")
    mod = synth.mod
    baseline, reason = mod.load_baseline_yaml(mod.BASELINE)
    assert reason is None and baseline is not None
    register = synth.read(synth.REGISTER)

    counts = dict(synth.counts())
    del counts["flag_diffs"]
    problems, _, skips = mod.judge_registration(counts=counts, baseline=baseline, register_text=register)
    assert any("`flag_diffs` 未装配" in p for p in problems), problems
    assert not any("跨面不对称" in s for s in skips), skips

    counts = dict(synth.counts())
    del counts["non_blocking_ci"]
    problems, _, skips = mod.judge_registration(counts=counts, baseline=baseline, register_text=register)
    assert any("gates.non_blocking_steps" in p and "未装配" in p for p in problems), problems
    assert not any("non_blocking_steps" in s for s in skips), skips

    synth.mutate("BASELINE.yaml", "  non_blocking_steps: 2\n", "")
    debt, reason = mod.load_baseline_yaml(mod.BASELINE)
    assert reason is None and debt is not None
    _, _, skips = mod.judge_registration(counts=synth.counts(), baseline=debt, register_text=register)
    assert any("non_blocking_steps" in s and "BASELINE 键未取到" in s for s in skips), skips


def test_e13_section_one_closes_at_next_heading(synth: Synth) -> None:
    """§1 必须在下一个 H2 收口：不切就会读到 §2 那行诱饵「在盘门禁 999」，红变成漂移而不是缺席。"""
    synth.mutate(synth.REGISTER, "| 调用口径（CG 轮）", "| 别的维度（CG 轮）")
    problems = synth.problems()
    assert any("未找到「调用口径」行" in p for p in problems), problems
    assert not any("999" in p for p in problems), problems


def test_e14_baseline_declared_key_absent_is_red(synth: Synth) -> None:
    """本门自己声明的 13 个 BASELINE 键缺位即红——不像 `gates.*` 那样是别人的键、可以打 [SKIP]。"""
    pytest.importorskip("yaml")
    synth.mutate("BASELINE.yaml", "  flag_diffs: 2\n", "")
    problems = synth.problems()
    assert any("invocation.flag_diffs" in p and "缺键" in p for p in problems), problems


def test_e15_manual_only_detail_must_appear_in_the_scene(synth: Synth) -> None:
    """`manual-only` 的细节就是那个开关本身：现场里找不到它，这条登记只是在说「曾经有人跑过」。

    只从理由正文抓开关的话，理由里写别的开关就能替一个查无此证的细节过关——细节必须自己受审。
    """
    synth.append_allow(
        "manual-only check_alpha --json # 排障时手动跑一次，README 里提到过 --verify @docs/README_NO_NAME.md"
    )
    problems = synth.allow()[1]
    assert any("一个都找不到" in p and "--json" in p for p in problems), problems


def test_e16_duplicate_current_caliber_row_is_red_and_still_compared(synth: Synth) -> None:
    """§1 出现第二行「调用口径」⇒ 重复本身红，且两行都照复算值判。

    只取一行（首行或末行都行得通）就等于把人改的那一行留在暗处：漂移不报，重复也不报。
    """
    synth.mutate(
        synth.REGISTER,
        "`make invocation-caliber` |\n",
        "`make invocation-caliber` |\n| 调用口径（复制） | 〔当前口径：在盘门禁 999〕 | `make invocation-caliber` |\n",
    )
    problems = synth.problems()
    assert any("「调用口径」行出现 2 次" in p for p in problems), problems
    assert any("在盘门禁 声明 999" in p for p in problems), problems
    assert not any("在盘门禁 声明 6" in p for p in problems), problems


def test_e17_history_bracket_before_current_one_is_not_read(synth: Synth) -> None:
    """括号必须有「当前口径」这个前缀：同一行里先写的 〔历史口径：…〕 不能成为登记值。"""
    synth.mutate(
        synth.REGISTER,
        "〔当前口径：在盘门禁 6",
        "〔历史口径（BF 轮）：在盘门禁 42〕 〔当前口径：在盘门禁 6",
    )
    problems = synth.problems()
    assert not any("42" in p for p in problems), problems
    assert synth.run()[0] == 0


def test_e18_two_rows_with_the_same_label_are_both_compared(synth: Synth) -> None:
    """同一个标签写两行 ⇒ 前一行也照复算值判——按标签折叠成一行是「后者赢」的静默放行。

    e16 的两行标签不同（`调用口径` 与 `调用口径（复制）`），字典里本来就是两个键，折叠不折叠都判得到；
    这一例把两行的标签做得**逐字相同**，只有真的把同名行收成列表才能看见前一行的漂移。
    """
    text = synth.read(synth.REGISTER)
    row = next(line for line in text.splitlines() if line.startswith("| 调用口径（CG 轮）"))
    drifted = row.replace("在盘门禁 6", "在盘门禁 999")
    assert drifted != row
    synth.write(synth.REGISTER, text.replace(row, f"{drifted}\n{row}", 1))
    problems = synth.problems()
    assert any("「调用口径」行出现 2 次" in p for p in problems), problems
    assert sum("在盘门禁 声明 999" in p for p in problems) == 1, problems


# ══ F 组：CLI 与仓库级前提 ═════════════════════════════════════════════
def test_f01_list_prints_face_table_without_judging(synth: Synth) -> None:
    rc, out, _ = synth.run(["--list"])
    assert rc == 0
    rows = [line for line in out.splitlines() if line]
    assert any(line.startswith("check_alpha\tmake:gates\t") and "--strict" in line for line in rows)
    assert any(line.startswith("check_delta\t callers\t['experiments/run_synth.py']") for line in rows)
    assert {line.split("\t")[1].strip() for line in rows} == {
        "make:gates",
        "make:weekly",
        "wf:ci.yml",
        "wf:perf.yml",
        "callers",
    }
    assert "[SURFACE]" not in out and "[OK]" not in out


def test_f02_quiet_hides_ok_but_keeps_surface(synth: Synth) -> None:
    _, verbose, _ = synth.run()
    rc, quiet, err = synth.run(["--quiet"])
    assert rc == 0 and "[OK]" not in quiet and "[SURFACE]" in quiet and err == ""
    assert verbose.count("[OK]") > 0


@pytest.mark.parametrize(
    "rel",
    ["Makefile", ".github/workflows", "BASELINE.yaml", "docs/PROJECT_STATUS_REGISTER.md"],
    ids=["Makefile", "workflows", "BASELINE", "登记册"],
)
def test_f03_missing_repo_premise_is_red(synth: Synth, rel: str) -> None:
    """仓库级前提缺席 = 红（与环境性前提缺席打 [SKIP] 分开）：判据不能靠缺席蒙过去。"""
    target = synth.root / rel
    if rel == ".github/workflows":
        for yml in sorted(target.glob("*.yml")):
            yml.unlink()
        target.rmdir()
    else:
        target.unlink()
    rc, _, err = synth.run()
    assert rc == 1 and "仓库级前提缺席" in err


def test_f04_baseline_unparsable_skips_registration(synth: Synth) -> None:
    """环境性/解析性前提：BASELINE 不可解析 ⇒ 判定五打 `[SKIP]` 带成因，不冒充成「口径漂移」。

    处置只把沉默换成披露：跳过在 `--quiet` 下照打（与 `[SURFACE]` 同规），其余四面照常判；
    只有仓库级前提缺席才计红（F03）。跳过也必须是有条件的，否则门可以永远打折而不被发现。
    """
    pytest.importorskip("yaml")
    _, clean, _ = synth.run()
    assert "[SKIP]" not in clean
    synth.mutate("BASELINE.yaml", "gates:\n", "gates: [oops\n")
    rc, out, err = synth.run()
    skips = [line for line in out.splitlines() if line.startswith("[SKIP]")]
    assert rc == 0 and len(skips) == 1 and "BASELINE 解析失败" in skips[0]
    assert re.search(r"[A-Za-z]+Error", skips[0]), skips[0]  # 成因是异常类型，不是空话
    assert synth.problems() == [] and err == ""
    _, quiet, _ = synth.run(["--quiet"])
    assert skips[0] in quiet


def test_f05_red_path_still_discloses_surface(synth: Synth) -> None:
    """报红也要带出「判了什么 / 不判什么」：三行 `[SURFACE]` 在红路径上一条都不能少。

    否则读红的人只看到一条断言失败，不知道这一跑覆盖了几道门、几个面、哪些档本门不管——
    受检面披露是红的可解释性的一部分，不是绿色的装饰。
    """
    synth.drop_allow("flag-diff check_beta")
    rc, out, err = synth.run()
    assert rc == 1 and err.count("[SURFACE]") == 3 and "[SURFACE] 判定面" in err
    assert "[SURFACE] 阻断性判定面" in out and "[SURFACE] 开关活性判定面" in out


def test_f06_pass_line_restates_the_recomputed_numbers(synth: Synth) -> None:
    """通过行不复述数字，绿就只是一句绿：六个分母必须在绿路径上也能被读到。"""
    rc, out, _ = synth.run()
    assert rc == 0
    line = next(text for text in out.splitlines() if "[invocation-caliber] 通过" in text)
    for fragment in (
        "在盘 6 道门",
        "13 个声明开关中判据档无读者 0",
        "已登记 1",
        "范围与呈现档无读者 4",
        "跨面不对称 2 处全部登记",
        "幽灵开关 0",
    ):
        assert fragment in line, line


# ══ R 组：真实树（只读，不写）═══════════════════════════════════════════
@pytest.fixture(scope="module")
def real():
    return _load_gate("aitester_cg_real", _GATE_SCRIPT)


@pytest.fixture(scope="module")
def real_cf():
    return _load_gate("aitester_cf_real", _CF_SCRIPT)


def _real_counts(mod) -> dict:
    """真实树上按 `main()` 的同一套键装配——判定五读不到的键在这里也必须存在。"""
    make_text = mod._read(mod.MAKEFILE)
    steps = mod.workflow_steps()
    table = mod.invocations(make_text, steps)[0]
    disk = sorted(p.stem for p in mod.GATES_DIR.glob("*.py"))
    allow = mod.parse_allowlist(mod.ALLOWLIST)[0]
    specs = {stem: mod.flag_specs(stem) for stem in disk}
    ci = [s for s in steps if s.gate_stems() and s.file == "ci.yml"]
    chain = mod.make_faces(make_text).get(mod.FACE_CHAIN, [])
    flags = mod.judge_flags(table=table, allow=allow, specs_cache=specs)
    counts = {
        "steps": steps,
        "table": table,
        "disk": disk,
        "allow": allow,
        "wiring": mod.judge_wiring(
            disk=disk,
            table=table,
            callers={s: mod.programmatic_callers(s) for s in disk if not table.get(s)},
            allow=allow,
        ),
        "flags": flags,
        "blocking": mod.judge_blocking(steps, allow),
        "liveness": mod.judge_liveness(disk=disk, table=table, allow=allow),
        "disk_scripts": len(disk),
        "chain_scripts": len({s for line in chain for s in mod._GATES_REF_RE.findall(line)}),
        "faces": len({face for per in table.values() for face in per}),
        "ci_unique_scripts": len({s for st in ci for s in st.gate_stems()}),
        "ci_call_sites": sum(len(st.gate_stems()) for st in ci),
        "gate_steps_ci": len(ci),
        "make_targets": len(mod.make_gate_deps(make_text)),
        "make_commands": len(chain),
        "flag_diffs": flags[3],  # 判定二返回 int 而非 dict，`**` 带不进来
        "ghost_flags": len(mod._ghost_flags(table, specs)),
        **mod.judge_blocking(steps, allow)[3],
        **mod.judge_liveness(disk=disk, table=table, allow=allow)[3],
    }
    _assert_authority_complete(mod, counts)
    return counts


def _baseline(real) -> dict:
    """真树锁期望值的单一事实源 = BASELINE（CG 门逐键对账它、CF 门交叉复算它）。

    CI 轮收口：这些数曾在 CG 轮被硬编码成第二份字面量，CH 轮移动分母后只刷了 BASELINE 与 §1，
    四条锁红了一轮才被发现——「同一个数留两份」正是 AB14 单一事实源判据反对的形态。"""
    data, reason = real.load_baseline_yaml(real.BASELINE)
    assert data is not None and reason is None, reason
    return data


def test_r01_cf_and_cg_agree_on_structural_numbers(real, real_cf) -> None:
    """约定 5 的实证：同一个数由两条独立实现在真实树上相遇（结构，不是子串）。
    绝对值以 BASELINE `gates` 节为单一事实源——CI 轮起不再复制第二份字面量。"""
    c = _real_counts(real)
    cf = real_cf.ci_gate_surface(real_cf._read(real_cf.REPO_ROOT / ".github/workflows/ci.yml"))
    g = _baseline(real)["gates"]
    assert c["non_blocking_ci"] == cf["非阻断步骤"] == g["non_blocking_steps"]
    assert c["blocking_ci"] == cf["阻断步骤"] == g["gate_steps"] - g["non_blocking_steps"]
    assert c["gate_steps_ci"] == cf["门禁步骤"] == g["gate_steps"]
    assert c["ci_unique_scripts"] == cf["ci唯一门禁"] == g["ci_unique_scripts"]
    # 子串式正则会把注释里的说明数成调用点；CI 轮把这里的绝对值锚也交给 BASELINE（ci.yml 每接一道门 +1）
    assert c["ci_call_sites"] == cf["ci调用点"] == g["ci_call_sites"]


def test_r02_real_judgments_empty_and_cli_holds_only_debt(real) -> None:
    """本轮判定面在真实树上只剩「数字刷新债」：BASELINE / §1 尚未回填，其余五面必须全空。"""
    c = _real_counts(real)
    assert c["wiring"][0] == [] and c["flags"][0] == []
    assert c["blocking"][0] == [] and c["liveness"][0] == []
    assert real.self_wiring(make_text=real._read(real.MAKEFILE), steps=c["steps"]) == []
    problems = Synth(real, real.REPO_ROOT).problems()
    unexpected = [
        p
        for p in problems
        if not p.startswith(("交叉核对：BASELINE `", "BASELINE `", "docs/PROJECT_STATUS_REGISTER.md"))
    ]
    assert unexpected == [], unexpected


def test_r03_real_reader_split_is_a_closed_denominator(real) -> None:
    """⑦：真实树四类读者之和 = 声明数，且判据档无读者为 0（本文件就是 `--list` 的那个读者）。
    三个移动分母以 BASELINE `invocation` 节为单一事实源；`caliber_unread == 0` 是性质锁，保留字面量。"""
    c = _real_counts(real)
    inv = _baseline(real)["invocation"]
    assert c["declared_flags"] == inv["declared_flags"]
    assert c["passed_flags"] == inv["passed_flags"]
    assert c["registered_unread"] == inv["registered_unread"]
    assert c["caliber_unread"] == inv["caliber_unread"] == 0
    assert (
        c["passed_flags"] + c["locked_flags"] + c["registered_unread"] + c["caliber_unread"] + c["presentation_unread"]
        == c["declared_flags"]
    )


def test_r04_real_surface_numbers(real) -> None:
    """⑥②④⑤：在盘 / 链上 / 调用面 / make 面 / 幽灵 / 兜底——期望值全部取 BASELINE（gates + invocation 两节）；
    性质锁保留字面量（faces 5 / 幽灵 0 / 兜底与动态 1-1）。跨面差异数与登记表 flag-diff 条数同源互证。"""
    c = _real_counts(real)
    b = _baseline(real)
    g, inv = b["gates"], b["invocation"]
    assert c["disk_scripts"] == inv["disk_scripts"] == g["scripts_total"]
    assert c["chain_scripts"] == inv["chain_scripts"]
    assert c["faces"] == inv["faces"] == 5
    assert len({face for per in c["table"].values() for face in per}) == c["faces"]
    assert c["make_targets"] == g["make_targets"]
    assert c["make_commands"] == g["make_commands"]
    assert c["flag_diffs"] == inv["flag_diffs"]
    assert sum(1 for key in c["allow"] if key[0] == "flag-diff") == inv["flag_diffs"]
    assert c["ghost_flags"] == inv["ghost_flags"] == 0
    assert (c["swallow_steps"], c["dynamic_steps"]) == (inv["swallow_steps"], inv["dynamic_steps"]) == (1, 1)


def test_r05_real_allowlist_clean_and_five_kinds(real) -> None:
    """登记表五类齐全、每条理由指向在盘现场、flag-diff 条数 == BASELINE `flag_diffs`。
    CI 轮删掉了「总条数 15」这第二份字面量：它只随登记表增删移动、不是判据——CH 轮删一条后
    它过期一整轮；登记表内容的真实性由 CG 门（无理由 / 畸形 / 失效条目各计红）判定，不由本锁复判。"""
    entries, problems = real.parse_allowlist(real.ALLOWLIST)
    assert problems == []
    assert {key[0] for key in entries} == set(real.KINDS)
    assert all("@" in reason for reason in entries.values())  # 每条登记都指向在盘现场
    assert sum(1 for key in entries if key[0] == "flag-diff") == _baseline(real)["invocation"]["flag_diffs"]


def test_r06_cg_is_wired_into_chain_and_ci_blocking(real) -> None:
    """本门自己：链上有目标、`gates:` 依赖里有它、ci.yml 有这一步且不阻断（否则判据永不生效）。"""
    make_text = real._read(real.MAKEFILE)
    assert "invocation-caliber" in real.make_gate_deps(make_text)
    assert "scripts/gates/check_invocation_caliber.py" in "\n".join(real.make_recipes(make_text)["invocation-caliber"])
    steps = [s for s in real.workflow_steps() if s.file == "ci.yml" and "invocation" in s.name.lower()]
    assert len(steps) == 1 and steps[0].non_blocking_layers() == []
