r"""门禁调用口径对账：`make gates` 链与各 workflow 是否**以同一口径**跑同一道门。

CF 轮判定「有没有人调用」（在场性）；本轮判定「以什么口径调用」——调用面归属、命令行开关、
阻不阻断。改前实测（2026-10-24，只读复算；①~⑥ 与 ⑦ 的括号数取自「改前树」，⑦ 主句取自「中间态树」，
两棵树的定义见表格下方注）：

| # | 形态 | 改前读数 | 后果 |
|---|---|---|---|
| ① | 非阻断判据按子串搜步骤正文 | CF 复算 **非阻断 3 / 阻断 26**；按 YAML 结构（步骤键缩进 8、排除注释）复算 **2 / 27** | ci.yml:366 注释里那句「改 continue-on-error: true」被当成当前键 ⇒ 已进 BASELINE 与 §1 的数字里有一条是注释造出来的 |
| ② | 同一脚本跨调用面开关不等，无人对账 | 只比「`make gates` ↔ ci.yml」这一对面得 **1** 处不等（`check_artifact_doc_consistency`：链上不带 `--require-coverage`、CI 覆盖率作业带）；比**所有面两两**得 **3** 处（另两处 = `check_perf_regression` 的 `--strict`、`check_prompt_artifacts` 的 `--strict`） | 两处理由只写在 Makefile:71-73 与 perf.yml:62-67 的**注释**里；注释不会被复算，下一轮改了命令行，注释不会变红 |
| ③ | 本地链缺席被 OR 语义掩盖 | `check_prompt_artifacts` 不在 `make gates` 链上（只有 `make prompt-artifacts-check` 带 `--strict`），而 ci.yml:275 **裸跑不带 `--strict`** | 清单缺席时 CI 打 `[SKIP]` rc=0 ⇒ 两侧都不是强制档，「已接线」为真但「强制」为假 |
| ④ | 不阻断还有第三层：shell 兜底 | ci.yml:713-714 `check_citations.py --online --no-strict \|\| echo "::warning …"`，同一步骤同时有 `continue-on-error` 键与 `\|\|` 兜底 | 删掉键也永远绿；两层各自消失都无人知 |
| ⑤ | 开关由 shell 变量注入 | perf.yml:72 `… $STRICT_FLAG`（值由 `workflow_dispatch` 输入决定） | 静态普查看不到 `--strict`；阻断性取决于运行时输入 |
| ⑥ | 在盘门禁的调用面归属 | 在盘 30：链上 16 / ci.yml 28 / perf.yml 1 / 仅由 `experiments/run_full_stack_swe_bench_pro.py` 以 import 调用 1（`check_swe_bench_pro_ready`）/ 三侧皆无 0 | 「写了没人跑」第一次有判据 |
| ⑦ | 声明开关的读者 | 声明 **71**（24 道门有 argparse）：调用面传过 **14**、代码锁 **24**、无读者 **33**。初测用「文件里出现过该开关 token 就算读者」的宽松规则得 52 有锁 / 0 无读者——收紧成「同一文件既出现该开关、又点名这道门」后，33 条从未有读者的开关第一次露面。反向的幽灵开关（传了但脚本没声明）实测 **0**，判定二按源码 `add_argument` 复算它。**这一行的分母是「本门已在盘、本轮回归锁与登记表尚未写」的中间态**；把本门自身从分母里剔掉（真正的改前树，见下注）回落到 69 / 23 道 / 无读者 31。差的 2 个开关是本门自己的 `--list` 与 `--quiet`，差的 1 条判据档就是 `--list` | 无读者 33 条里 **10 条是判据档**（改变退出码语义：`--list`「不判退出码」、`--skip-t10`、`--allow-empty`、`--strict`、`--verify`、`--update-baseline`），**23 条是范围与呈现档**（`--json`/`--threshold`/`--file`…，默认值即两侧共同的有效口径）；改前树口径下是 9 + 22 = 31，那 9 条全部落登记表，第 10 条由本轮回归锁补成代码锁 |

改前两行（⑥ 与 ⑦）**不同树**，这里把两棵都说清楚，避免「同一棵树」这种读起来自洽、复算对不上的说法：

- **改前树**（① 的 3/26 与 2/27、⑥ 的 在盘 30 / 链上 16 / ci 唯一 28 / perf 1 / import 1、⑦ 括号里的
  69 个声明 / 23 道有 argparse / 无读者 31）= `00e8c24d` + 工作树里历轮未提交改动，
  再移除本轮新增的四个文件（本门、回归锁、变异工装、登记表）并回退 `Makefile` 的目标与 `gates` 链条目、
  `ci.yml` 的本轮步骤。复现命令见分册 §4 C 段。
- **中间态树**（⑦ 主句的 71 / 24 道 / 33 条、⑨ 的 32 与 30）= 改前树 + 本门脚本本身 + 本轮 `Makefile`
  与 `ci.yml` 接线。本门一落地就给自己贡献了 `--list`（判据档）与 `--quiet`（呈现档）两条声明，
  所以分母从 69 变 71、无读者从 31 变 33，门禁步骤从 29 变 30、阻断从 27 变 28；
  这两条开关随后由本轮回归锁 `tests/test_invocation_caliber_cg.py`（传它们并点名本门）收为代码锁。
| ⑧ | 严格档从未在任何面被传 | `check_registration_consistency --verify-mypy` 声明后无**执行面**——但它有代码锁（`tests/test_registration_readers_cf.py` 传它），按判定四不算无读者 | CF §4 交来的边界仍在：登记面永远读不到它本可以读到的东西（`--verify-mypy` 的默认分支才是 CI 实际口径）；本门只披露不记红 |
| ⑨ | 调用点也按全文正则数 | CF 原式 `findall(ci_text)` = **32**；只数非注释行 = **30**（两数均在中间态树；改前树同一对是 **31 / 29**，本轮接线 +1 处。多出的 2 处在 ci.yml:556 `coverage_ratchet.py --allow-bump` 的手动流程说明、ci.yml:720 `check_citations.py --online` 的步骤说明，被原式算成调用点） | 与①同一条病灶的第二处：注释在场≠调用在场。CF 已改为 `ci_effective_refs`，两门复算同一个数 |
| ⑩ | 软档开关与脚本默认同形 | ci.yml:730 `check_docs_history_drift.py --warn-only`，而该脚本 help 自述「显式标记为 warning-only（与默认行为一致，便于 CI 可读性）」、`--strict` 无读者 | 「有人显式选了软档」是文本给人错觉；这一步的不阻断由默认值给出。本门**不判**「开关是否真改变了行为」（那需要执行），只把它列为边界 |

处置纪律：**纯读侧、只读、fail-closed，不改任何被判定文件**。五条口径约定：

1. **判据按结构，不按子串**（对应①⑨）。步骤级键 = 缩进恰为 8 且非注释；`run` 区块内容
   （缩进 ≥10）与注释都不算键；调用点只数非注释行。shell 兜底这一层含 `||` 与 `set +e` 两种
   写法，后者按区块内 `set ±e` 的先后推进状态——门禁命令落在 `+e` 区间里就算不阻断，
   被 `set -e` 回补之后跑的仍算阻断。
2. **开关相等按有效值，不按文本**。一侧显式传 `--baseline docs/performance_baseline.json`、
   另一侧靠 argparse 默认值，是**同一口径**（默认值从脚本源码的 `default=` 复算）；只有
   `store_true` 类或缺省不可解析的开关才按文本比。只按文本比会凭空造出一条假不对称——
   与①同族、方向相反。
3. **差异必须落在机器可读的登记表** `docs/invocation_caliber_allowlist.txt`，语法
   `<类别> <主体> <细节>  # 理由`（三段均不含空格；步骤主体用 `<文件>::<名称去空格>`）。
   注释 / 分册 / CHANGELOG 里的理由都不算登记，因为它们不会被复算。无理由 / 畸形 / 重复 /
   已失效各计红；每条登记必须有 `@路径` 现场，现场必须存在且**能在其中找到登记的开关**
   （`manual-only` 查 `细节` 那个开关本身）——理由里的开关在现场找不到，就还是 prose。
4. **判据档记红，范围与呈现档记数**。判据档 = 改变这道门退出码语义的开关（更松 / 更严 /
   改写判据文件），无读者即红；其余 23 条不逐条登记（33 条豁免会把登记表变成橡皮章），
   而是以数字锁进 BASELINE `invocation.presentation_unread` 并在 `[SURFACE]` 披露。
5. **不复制常量，四重锚定**：本门复算值 == BASELINE `invocation.*` / `gates.non_blocking_steps`
   等键 == 登记册 §1「调用口径」行的〔当前口径〕括号 == CF 门的独立复算。CF 判 §1↔BASELINE，
   本门判 BASELINE↔实测——两条独立实现在同一个登记数上相遇，不是双判据。§1 里同一个标签出现
   两次 ⇒ 逐行都判并把重复本身点名（只取一行的话，人改的那一行可以永远不被读）。判定四另加一条
   分母自校验：`声明 = 调用面 + 代码锁 + 登记 + 判据档 + 呈现档`，不成立即红（读者分类
   必须互斥且完备）。

退出码：`0` = 全部对账通过；`1` = 口径漂移 / 未登记差异 / 判据档无读者 / 幽灵开关 / 仓库级前提缺席 /
本门复算键缺位；`2` = 用法错误（argparse 默认）。仓库内文件缺席（Makefile / workflows / BASELINE / 登记册）
⇒ 计红；环境性前提（`git` 不可用、BASELINE 不可解析、BASELINE 的既有交叉核对键缺席）⇒ 打 `[SKIP]` 带成因；
但 `counts` 是本门自己装配的——自产权威源缺位一律计红，否则「少判一项」会永久静默。

用法：
    python3 scripts/gates/check_invocation_caliber.py [--list] [--quiet]

`--list`：只打印调用面归属表（stem → 面 → 开关 / 兜底层），不判定；`--quiet`：不打印逐项 `[OK]`。
"""

from __future__ import annotations

import argparse
import ast
import re
import shlex
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
WF_DIR = REPO_ROOT / ".github" / "workflows"
GATES_DIR = REPO_ROOT / "scripts" / "gates"
BASELINE = REPO_ROOT / "BASELINE.yaml"
REGISTER = REPO_ROOT / "docs" / "PROJECT_STATUS_REGISTER.md"
ALLOWLIST = REPO_ROOT / "docs" / "invocation_caliber_allowlist.txt"

_GATES_REF_RE = re.compile(r"scripts/gates/([A-Za-z0-9_]+)\.py")
_FLAG_RE = re.compile(r"--[a-z0-9][a-z0-9_-]*")
_STEP_RE = re.compile(r"^ {6}- name: (.*)$")
_TARGET_RE = re.compile(r"^([A-Za-z0-9_.\-]+):")
_COE_RE = re.compile(r"^continue-on-error:\s*(\S+)\s*(?:#.*)?$")
_WARN_ONLY_RE = re.compile(r"--warn-only(?![a-z0-9_-])")
_SWALLOW_RE = re.compile(r"\|\|\s*(?:echo|true|exit[ \t]+0)(?![a-z0-9_-])|\|\|\\?\s*$")
# `set +e` 关掉的是整块 shell 的失败即退，作用域从它那一行起、到配对的回补 `set -e` 止；
# 所以按区块内的先后顺序推进状态，而不是「这一行含 set +e」——门禁行单独一行时兜底照样成立。
_SET_E_RE = re.compile(r"\bset\s+([+-])e\b")
_VAR_RE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
_ASSIGN_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(\"([^\"]*)\"|'([^']*)'|([^\s;)]+))")
_BRACKET_RE = re.compile(r"〔当前口径[^：:]*[：:](?P<body>[^〕]*)〕")
_PAIR_RE = re.compile(r"([^\s/；;、]+)\s+([0-9]+(?:\.[0-9]+)?)")
_ROW_RE = re.compile(r"^\|\s*([^|]*?[^|\s])\s*\|(?P<body>[^\n]*)\|", re.M)

# 「判据档」= 改变这道门**退出码语义**的开关：让它更松 / 让它真的更严 / 让它改写自己的判据文件。
# 与之相对的是「范围档与呈现档」（`--all-keys` `--threshold` `--file` `--json` `--report` …）：
# 它们改的是扫描面与参数取值，而默认值本身就是两侧共同的有效口径（判定二按有效值比较时已经算进去）。
# 因此本门只对判据档记红；其余无读者开关以**数字**锁进 BASELINE `invocation.presentation_unread`
# 并在 `[SURFACE]` 里披露——记红 33 条会把登记表变成橡皮章，静默 33 条才是本门要收的口。
_CALIBER_FAMILIES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "放松档",
        re.compile(r"^(?:--list|--allow-empty|--warn-only|--no-strict|--skip-[a-z0-9-]+)$"),
        "传它这道门就不给红",
    ),
    ("严格档", re.compile(r"^(?:--strict|--verify|--require-[a-z0-9-]+|--verify-[a-z0-9-]+)$"), "它才让这道门真的更严"),
    ("改写判据档", re.compile(r"^--update-[a-z0-9-]+$"), "跑它这道门会改写自己的判据文件"),
)

FACE_CHAIN = "make:gates"
CALLER_DIRS = ("scripts", "experiments")

# §1「调用口径」行的声明键 → 本门复算的权威值键（同名，全部 authority=self）
ITEMS: dict[str, str] = {
    "在盘门禁": "disk_scripts",
    "链上面脚本": "chain_scripts",
    "调用面数": "faces",
    "声明开关": "declared_flags",
    "传过开关": "passed_flags",
    "代码锁开关": "locked_flags",
    "登记无读者": "registered_unread",
    "判据档无读者": "caliber_unread",
    "范围呈现档无读者": "presentation_unread",
    "跨面不对称": "flag_diffs",
    "兜底步骤": "swallow_steps",
    "动态注入步骤": "dynamic_steps",
    "幽灵开关": "ghost_flags",
}
BASELINE_KEYS: dict[str, str] = {
    "在盘门禁": "invocation.disk_scripts",
    "链上面脚本": "invocation.chain_scripts",
    "调用面数": "invocation.faces",
    "声明开关": "invocation.declared_flags",
    "传过开关": "invocation.passed_flags",
    "代码锁开关": "invocation.locked_flags",
    "登记无读者": "invocation.registered_unread",
    "判据档无读者": "invocation.caliber_unread",
    "范围呈现档无读者": "invocation.presentation_unread",
    "跨面不对称": "invocation.flag_diffs",
    "兜底步骤": "invocation.swallow_steps",
    "动态注入步骤": "invocation.dynamic_steps",
    "幽灵开关": "invocation.ghost_flags",
}
# BASELINE 里由 CF 与本机共用、本门只做交叉核对的既有键 → 本门复算值键
XCHECK_KEYS: dict[str, str] = {
    "非阻断步骤": "gates.non_blocking_steps",
    "阻断步骤": "gates.blocking_steps",
    "ci唯一门禁": "gates.ci_unique_scripts",
    "ci调用点": "gates.ci_call_sites",
    "门禁步骤": "gates.gate_steps",
    "make目标": "gates.make_targets",
    "make命令": "gates.make_commands",
}
XCHECK_COUNT_KEYS: dict[str, str] = {
    "非阻断步骤": "non_blocking_ci",
    "阻断步骤": "blocking_ci",
    "ci唯一门禁": "ci_unique_scripts",
    "ci调用点": "ci_call_sites",
    "门禁步骤": "gate_steps_ci",
    "make目标": "make_targets",
    "make命令": "make_commands",
}
KINDS = ("flag-diff", "no-face", "manual-only", "soft-layer", "dynamic-flag")
# 每一类都必须指向在盘现场：登记的价值在于「理由可复算」，纯 prose 理由与 Makefile:71-73
# 那句注释没有区别——而注释正是本轮的①号病灶。
_EVIDENCE_REQUIRED_KINDS = KINDS


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _slugify(text: str) -> str:
    """步骤名 → 无空格主体（登记表里的 subject 不能含空格，否则三段式会被撑成四段）。"""
    return re.sub(r"\s+", "-", text.strip())


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _run(cmd: list[str], root: Path) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    except (OSError, ValueError):
        return None


def _join_continuations(lines: list[str]) -> list[str]:
    """把以 `\\` 续行的配方/脚本行合成一条命令（开关与兜底常在续行上）。"""
    out: list[str] = []
    buf = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.endswith("\\"):
            buf += stripped[:-1].rstrip() + " "
            continue
        out.append((buf + stripped).strip())
        buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _explicit_flags(command: str) -> dict[str, str | None]:
    """按 `--flag [值]` 取显式开关；值取下一个既不以 `-` 开头也不像 shell 运算符的 token。"""
    out: dict[str, str | None] = {}
    toks = _tokens(command)
    i = 0
    while i < len(toks):
        tok = toks[i]
        if tok.startswith("--"):
            if "=" in tok:
                name, _, value = tok.partition("=")
                out[name] = value
            else:
                nxt = toks[i + 1] if i + 1 < len(toks) else ""
                if nxt and not nxt.startswith("-") and nxt not in {"|", "||", "&&", ";", "\\", "|&"}:
                    out[tok] = nxt
                    i += 1
                else:
                    out[tok] = None
        i += 1
    return out


# ══ 解析面一：Makefile 调用面 ═══════════════════════════════════════════
def make_gate_deps(make_text: str) -> list[str]:
    line = next((raw for raw in make_text.splitlines() if raw.startswith("gates:")), None)
    if line is None:
        return []
    return line.split("#", 1)[0].split()[1:]


def make_recipes(make_text: str) -> dict[str, list[str]]:
    """目标 → 配方命令行（去注释、合续行）。"""
    recipes: dict[str, list[str]] = {}
    current: str | None = None
    for line in make_text.splitlines():
        if line.startswith("\t"):
            if current is None:
                continue
            code = line[1:].strip()
            if code and not code.startswith("#"):
                recipes[current].append(code)
            continue
        match = _TARGET_RE.match(line)
        if match:
            current = match.group(1)
            recipes.setdefault(current, [])
    return {target: _join_continuations(cmds) for target, cmds in recipes.items()}


def make_faces(make_text: str) -> dict[str, list[str]]:
    """`make:gates`（链展开）＋每个引用门禁脚本的其它目标。"""
    recipes = make_recipes(make_text)
    deps = make_gate_deps(make_text)
    chain: list[str] = []
    for dep in deps:
        chain.extend(recipes.get(dep, []))
    faces = {FACE_CHAIN: chain}
    for target, cmds in recipes.items():
        if target in deps or target == "gates":
            continue
        gate_cmds = [c for c in cmds if "scripts/gates/" in c]
        if gate_cmds:
            faces[f"make:{target}"] = gate_cmds
    return {name: lines for name, lines in faces.items() if lines}


# ══ 解析面二：workflow 步骤（按结构，不按子串）═══════════════════════════
class Step:
    def __init__(self, file: str, name: str) -> None:
        self.file = file
        self.name = name
        self.commands: list[str] = []  # run 区块里的命令行（不含注释、不含步骤级键）
        self.continue_on_error = False  # 步骤级键（缩进 8、非注释）
        self.if_key: str | None = None
        self.assignments: dict[str, str] = {}  # shell 变量 → 值
        self.swallow = False  # 门禁命令被 `|| echo/true/exit 0` 兜底，或执行它时 `set +e` 仍生效
        self.dynamic: list[str] = []  # 注入开关的变量名

    @property
    def slug(self) -> str:
        return f"{self.file}::{_slugify(self.name)}"

    def gate_stems(self) -> list[str]:
        return [s for command in self.commands for s in _GATES_REF_RE.findall(command)]

    def flags(self, stem: str) -> dict[str, str | None]:
        out: dict[str, str | None] = {}
        for command in self.commands:
            if f"scripts/gates/{stem}.py" in command:
                out.update(_explicit_flags(command))
        for var in self.dynamic:
            value = self.assignments.get(var, "")
            for flag in _FLAG_RE.findall(value):
                out.setdefault(flag, None)
        return out

    def warn_only(self) -> bool:
        return any(_WARN_ONLY_RE.search(command) for command in self.commands)

    def non_blocking_layers(self) -> list[str]:
        layers = []
        if self.continue_on_error:
            layers.append("coe")
        if self.warn_only():
            layers.append("warn-only")
        if self.swallow:
            layers.append("shell-or")
        return layers


def _parse_run_regions(lines: list[str], start: int, end: int) -> tuple[list[str], list[str]]:
    """返回（步骤级键行，run 区块内容行）。run 键行缩进 8，其块内容缩进 ≥10。"""
    keys: list[str] = []
    run: list[str] = []
    in_run = False
    for raw in lines[start:end]:
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip())
        stripped = raw.strip()
        if stripped.startswith("#"):
            continue
        if indent <= 8 and not stripped.startswith("- "):
            if in_run and indent < 10:
                in_run = False
            if stripped.startswith("run:"):
                value = stripped[4:].strip()
                if value in {"|", ">", "|-", ">-", "|+", ">+"}:
                    in_run = True
                elif value:
                    run.append(value)
                continue
            keys.append(stripped)
            continue
        if in_run:
            run.append(stripped)
    return keys, run


def workflow_steps(wf_dir: Path | None = None) -> list[Step]:
    """解析所有 workflow 的步骤；`None` ⇒ 调用时取当前 `WF_DIR`（默认值在 `def` 时就固化，会静默读真仓库）。"""
    wf_dir = WF_DIR if wf_dir is None else wf_dir
    steps: list[Step] = []
    if not wf_dir.is_dir():
        return steps
    for path in sorted(wf_dir.glob("*.yml")):
        lines = _read(path).splitlines()
        starts = [i for i, line in enumerate(lines) if _STEP_RE.match(line)]
        if not starts:
            continue
        bounds = [*starts[1:], len(lines)]
        for a, b in zip(starts, bounds, strict=True):
            header = _STEP_RE.match(lines[a])
            assert header is not None
            step = Step(path.name, header.group(1).strip())
            keys, run_lines = _parse_run_regions(lines, a + 1, b)
            step.commands = _join_continuations(run_lines)
            for key_line in keys:
                match = _COE_RE.match(key_line)
                if match is not None:
                    step.continue_on_error = match.group(1).strip().lower() == "true"
                elif key_line.startswith("if:"):
                    step.if_key = key_line[3:].strip()
            for command in step.commands:
                for assign in _ASSIGN_RE.finditer(command):
                    step.assignments[assign.group(1)] = assign.group(2).strip("\"'")
            err_off = False
            for command in step.commands:
                flip = _SET_E_RE.search(command)
                if flip is not None:
                    err_off = flip.group(1) == "+"
                if not _GATES_REF_RE.search(command):
                    continue
                if _SWALLOW_RE.search(command) or err_off:
                    step.swallow = True
                for var in _VAR_RE.findall(command):
                    if _FLAG_RE.search(step.assignments.get(var, "")):
                        step.dynamic.append(var)
            steps.append(step)
    return steps


def wf_faces(steps: list[Step]) -> dict[str, list[Step]]:
    """workflow 调用面：`wf:<文件>` → 调用门禁的步骤列表。"""
    faces: dict[str, list[Step]] = {}
    for step in steps:
        if step.gate_stems():
            faces.setdefault(f"wf:{step.file}", []).append(step)
    return faces


# ══ 解析面三：脚本源码里的开关声明与默认值 ══════════════════════════════
def _flatten(expr: ast.expr | None, consts: dict[str, str]) -> str | None:
    """把 `PROJECT_ROOT / "docs" / "x.json"`、`str(DEFAULT_X)`、字面量归一成一个值。"""
    if expr is None:
        return None
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return expr.value
    if isinstance(expr, ast.Name):
        return consts.get(expr.id)
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, (ast.Div, ast.Add)):
        left = _flatten(expr.left, consts)
        right = _flatten(expr.right, consts)
        if left is None:
            return right
        if right is None:
            return left
        return f"{left}/{right}".strip("/") if isinstance(expr.op, ast.Div) else f"{left}{right}"
    if isinstance(expr, ast.Call):
        flat = _flatten(expr.args[0] if expr.args else None, consts)
        for extra in expr.args[1:]:
            tail = _flatten(extra, consts)
            if flat is not None and tail is not None:
                flat = f"{flat}/{tail}".strip("/")
        return flat
    return None


def flag_specs(stem: str) -> dict[str, dict[str, str | None]]:
    """`add_argument` 复算：`{--flag: {"kind": store_true|value, "default": 值|None}}`。"""
    path = GATES_DIR / f"{stem}.py"
    if not path.is_file():
        return {}
    try:
        tree = ast.parse(_read(path))
    except SyntaxError:
        return {}
    consts: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    value = _flatten(node.value, consts)
                    if value is not None:
                        consts[target.id] = value
    specs: dict[str, dict[str, str | None]] = {}
    for item in ast.walk(tree):
        if not (
            isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr == "add_argument"
        ):
            continue
        names = [
            a.value
            for a in item.args
            if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.startswith("-")
        ]
        if not names:
            continue
        long = next((n for n in names if n.startswith("--")), names[0])
        kwargs = {k.arg: k.value for k in item.keywords if k.arg}
        action = kwargs.get("action")
        is_flag = isinstance(action, ast.Constant) and action.value == "store_true"
        default = _flatten(kwargs.get("default"), consts)
        specs[long] = {"kind": "flag" if is_flag else "value", "default": default}
    return specs


def effective_flags(stem: str, face_flags: dict[str, str | None]) -> dict[str, str | None]:
    """显式值 ∪ 缺省值：一侧靠默认、一侧显式传同一个值 ⇒ 同一口径（约定 2）。

    `store_true` 类按「在场」记 `set`——否则「一侧传、另一侧不传」在值维度上都是 `None`，
    开关集合的对账会静默漏判最典型的一类不对称（`--strict` / `--require-coverage`）。
    """
    specs = flag_specs(stem)
    out = dict(face_flags)
    for flag, spec in specs.items():
        if flag in out:
            if spec["kind"] == "flag":
                out[flag] = "set"
            continue
        if spec["default"] is not None:
            out[flag] = spec["default"]
    return out


# ══ 调用面归属表 ═════════════════════════════════════════════════════
def invocations(
    make_text: str, steps: list[Step]
) -> tuple[dict[str, dict[str, dict[str, str | None]]], dict[str, list[Step]]]:
    """stem → face → 有效开关；以及 face → 步骤（workflow 面）。"""
    table: dict[str, dict[str, dict[str, str | None]]] = {}
    for face, lines in make_faces(make_text).items():
        for line in lines:
            for stem in _GATES_REF_RE.findall(line):
                merged = table.setdefault(stem, {}).setdefault(face, {})
                merged.update(_explicit_flags(line))
    for step in steps:
        for stem in step.gate_stems():
            merged = table.setdefault(stem, {}).setdefault(f"wf:{step.file}", {})
            merged.update(step.flags(stem))
    return table, wf_faces(steps)


def programmatic_callers(stem: str, root: Path | None = None) -> list[str]:
    """`scripts/` 与 `experiments/` 里以 import 或路径方式调用该门的文件（门禁链之外）。"""
    root = REPO_ROOT if root is None else root
    hits: list[str] = []
    for directory in CALLER_DIRS:
        for path in sorted((root / directory).rglob("*.py")):
            if path.parent == root / "scripts" / "gates":
                continue
            text = _read(path)
            if stem in text:
                hits.append(_rel(path))
    return hits


# ══ 登记表 ══════════════════════════════════════════════════════════
def parse_allowlist(path: Path) -> tuple[dict[tuple[str, str, str], str], list[str]]:
    """`<类别> <主体> <细节>  # 理由`；返回 {(kind, subject, detail): 理由} 与畸形/无理由/重复问题。"""
    entries: dict[tuple[str, str, str], str] = {}
    problems: list[str] = []
    if not path.is_file():
        return entries, [f"{_rel(path)}：登记表缺席——不对称无处登记 ⇒ fail-closed 全计红"]
    for lineno, raw in enumerate(_read(path).splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        body, sep, reason = line.partition("#")
        fields = body.split()
        if not sep or not reason.strip():
            problems.append(f"{_rel(path)}:{lineno}：无理由——`# 理由` 不是装饰，无理由的豁免等于没有豁免：{line}")
            continue
        if len(fields) != 3:
            problems.append(f"{_rel(path)}:{lineno}：畸形（应为 `类别 主体 细节 # 理由` 三段）：{line}")
            continue
        kind, subject, detail = fields
        if kind not in KINDS:
            problems.append(f"{_rel(path)}:{lineno}：未知类别 {kind}（可用 {list(KINDS)}）")
            continue
        key = (kind, subject, detail)
        if key in entries:
            problems.append(f"{_rel(path)}:{lineno}：重复登记 {key}")
            continue
        core = subject.split("::")[0]
        cited = re.findall(r"@([\w./-]+)", reason)
        if not cited and kind in _EVIDENCE_REQUIRED_KINDS:
            problems.append(
                f"{_rel(path)}:{lineno}：{kind} 类登记没有理由现场 `@路径`——"
                f"注释 / 分册 / CHANGELOG 里的理由不会被复算，登记必须指向一个在盘现场：{line}"
            )
        if core.replace("_", "").isalnum() and not (GATES_DIR / f"{core}.py").is_file():
            problems.append(
                f"{_rel(path)}:{lineno}：登记的主体 {core} 已不在 scripts/gates/ 下——"
                "门禁删了而登记还在，这条豁免正在遮蔽一个不存在的差异"
            )
        sites: list[tuple[str, str]] = []
        for name in cited:
            cited_path = REPO_ROOT / name
            if not cited_path.is_file():
                problems.append(f"{_rel(path)}:{lineno}：理由指向 {_rel(cited_path)}——文件不存在，理由不可核对")
                continue
            sites.append((name, _read(cited_path)))
            if kind != "manual-only" and core.replace("_", "").isalnum() and core not in sites[-1][1]:
                problems.append(f"{_rel(path)}:{lineno}：理由指向 {_rel(cited_path)}——正文不含主体 {core}")
        # 现场复算：`manual-only` 登记的细节就是开关本身，`flag-diff` 的理由要点名不对称的那个开关。
        must = [detail] if kind == "manual-only" else sorted(set(_FLAG_RE.findall(reason)))
        if must and sites and not any(token in text for token in must for _, text in sites):
            problems.append(
                f"{_rel(path)}:{lineno}：登记的 {must} 在引用现场 {[n for n, _ in sites]} "
                "一个都找不到——理由里写的开关必须在现场出现，否则这条登记只是 prose（复算不了的理由 = 没有理由）"
            )
        entries[key] = reason.strip()
    return entries, problems


# ══ 判定一：调用面归属 ════════════════════════════════════════════════
def judge_wiring(
    *, disk: list[str], table: dict[str, dict[str, dict[str, str | None]]], callers: dict[str, list[str]], allow: dict
) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    ok: list[str] = []
    used: set[tuple[str, str, str]] = set()
    for stem in disk:
        faces = sorted(table.get(stem, {}))
        hit = callers.get(stem, [])
        if not faces and not hit:
            key = ("no-face", stem, "zero-faces")
            if key in allow:
                used.add(key)
                ok.append(f"[OK] 归属：{stem} 无调用面，已登记（{allow[key]}）")
            else:
                problems.append(
                    f"调用面归属：{stem} 在盘却不被任何面调用（Makefile 目标 / workflow / 代码内调用皆无）"
                    f"——写了没人跑，登记表里没有这一条：{key}"
                )
            continue
        if not faces and hit:
            key = ("no-face", stem, "programmatic-only")
            if key in allow:
                used.add(key)
                ok.append(f"[OK] 归属：{stem} 仅由 {'、'.join(hit)} 调用，已登记")
            else:
                problems.append(
                    f"调用面归属：{stem} 不在任何门禁调用面上，只被 {hit[0]} 以代码方式调用"
                    f"——「有读者」不等于「在链上」，须登记 {key}"
                )
    for key, reason in allow.items():
        if key[0] == "no-face" and key not in used:
            problems.append(
                f"登记表失效：{_rel(ALLOWLIST)} 里 {key} 已不再触发（理由：{reason}）——要么删，要么它保护的东西变了"
            )
    return problems, ok


# ══ 判定二：跨面开关集合 ══════════════════════════════════════════════
def judge_flags(
    *, table: dict[str, dict[str, dict[str, str | None]]], allow: dict, specs_cache: dict[str, dict]
) -> tuple[list[str], list[str], list[str], int]:
    problems: list[str] = []
    ok: list[str] = []
    notes: list[str] = []
    used: set[tuple[str, str, str]] = set()
    diff_count = 0
    for stem in sorted(table):
        faces = table[stem]
        if len(faces) < 2:
            continue
        names = sorted(faces)
        eff = {face: effective_flags(stem, faces[face]) for face in names}
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                diff = _face_diff(eff[a], eff[b])
                if not diff:
                    continue
                diff_count += 1
                key = ("flag-diff", stem, f"{a}>{b}")
                if key in allow:
                    used.add(key)
                    ok.append(f"[OK] 跨面开关：{stem} {a}≠{b}（{diff}）已登记（{allow[key]}）")
                else:
                    problems.append(
                        f"跨面开关：{stem} 在 {a} 与 {b} 的有效开关不等 {diff}——同一道门跑两种命题；"
                        f"要么对齐，要么登记 {key} 并写理由（注释里的理由不会被复算）"
                    )
    for key, reason in allow.items():
        if key[0] == "flag-diff" and key not in used:
            problems.append(f"登记表失效：{key} 两侧现已一致（理由：{reason}）")
    ghost = _ghost_flags(table, specs_cache)
    for face, stem, flag in ghost:
        problems.append(
            f"幽灵开关：{face} 给 {stem} 传 {flag}，但脚本里没有这个 `add_argument`"
            "——真跑起来是 argparse 退出码 2；文本对账看不见，只有声明面能证伪"
        )
    notes.append(
        f"[SURFACE] 开关判定面：有 ≥2 个调用面的脚本 {sum(1 for s in table if len(table[s]) > 1)} 个、"
        f"面组合比对 {diff_count} 处不等；幽灵开关 {len(ghost)} 条（判据 = 脚本源码 `add_argument` 复算）"
    )
    return problems, ok, notes, diff_count


def _face_diff(a: dict[str, str | None], b: dict[str, str | None]) -> list[str]:
    out: list[str] = []
    for flag in sorted(set(a) | set(b)):
        va, vb = a.get(flag), b.get(flag)
        if va == vb:
            continue
        out.append(f"{flag}={va if va is not None else '—'}/{vb if vb is not None else '—'}")
    return out


def _ghost_flags(table: dict, specs_cache: dict[str, dict]) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for stem, faces in table.items():
        specs = specs_cache.setdefault(stem, flag_specs(stem))
        if not specs:
            continue
        for face, flags in sorted(faces.items()):
            out.extend((face, stem, flag) for flag in sorted(flags) if flag not in specs)
    return out


# ══ 判定三：阻断性三层 ════════════════════════════════════════════════
def judge_blocking(steps: list[Step], allow: dict) -> tuple[list[str], list[str], list[str], dict[str, int]]:
    problems: list[str] = []
    ok: list[str] = []
    notes: list[str] = []
    used: set[tuple[str, str, str]] = set()
    gate_steps = [s for s in steps if s.gate_stems()]
    non_blocking = [s for s in gate_steps if s.non_blocking_layers()]
    swallow = [s for s in gate_steps if s.swallow]
    dynamic = [s for s in gate_steps if s.dynamic]
    multi = [s for s in gate_steps if len(s.non_blocking_layers()) > 1]
    ci = [s for s in gate_steps if s.file == "ci.yml"]
    ci_non_blocking = [s for s in ci if s.non_blocking_layers()]

    for step in multi:
        layers = "+".join(step.non_blocking_layers())
        key = ("soft-layer", step.slug, layers)
        if key in allow:
            used.add(key)
            ok.append(f"[OK] 多层兜底：{step.slug}（{layers}）已登记（{allow[key]}）")
        else:
            problems.append(
                f"多层兜底：{step.slug} 同时用 {layers} 两层写法不阻断——两层各自消失都无人知，"
                f"且删掉任一层都不改变「这一步永远不会红」；须登记 {key}"
            )
    for step in dynamic:
        key = ("dynamic-flag", step.slug, "+".join(sorted(set(step.dynamic))))
        if key in allow:
            used.add(key)
            ok.append(f"[OK] 动态注入：{step.slug} 开关由 ${key[2]} 注入（{allow[key]}）")
        else:
            problems.append(
                f"动态注入：{step.slug} 的命令行进参来自 shell 变量 {step.dynamic}，"
                f"静态对账看不到实际口径；须登记 {key} 并写明由什么决定"
            )
    problems.extend(
        f"口径自相矛盾：{step.slug} 传 `--strict`（最严档）却仍不阻断（{step.non_blocking_layers()}）"
        "——严格档跑在最软的容器里，红被写成了绿"
        for step in gate_steps
        if "--strict" in " ".join(step.commands) and step.non_blocking_layers()
    )
    for key, reason in allow.items():
        if key[0] in ("soft-layer", "dynamic-flag") and key not in used:
            problems.append(f"登记表失效：{key} 已不再触发（理由：{reason}）")
    notes.append(
        f"[SURFACE] 阻断性判定面：workflow 门禁步骤 {len(gate_steps)}（ci.yml {len(ci)}）/ "
        f"三层判据下非阻断 {len(non_blocking)}（ci.yml {len(ci_non_blocking)}）/ shell 兜底 {len(swallow)} / "
        f"动态注入 {len(dynamic)} / 多层兜底 {len(multi)}；步骤级键按缩进 8 且非注释识别"
    )
    counts = {
        "gate_steps_all": len(gate_steps),
        "gate_steps_ci": len(ci),
        "non_blocking_all": len(non_blocking),
        "non_blocking_ci": len(ci_non_blocking),
        "blocking_ci": len(ci) - len(ci_non_blocking),
        "swallow_steps": len(swallow),
        "dynamic_steps": len(dynamic),
    }
    return problems, ok, notes, counts


# ══ 判定四：声明开关活性 + 判据档可达性 ════════════════════════════════
def caliber_family(flag: str) -> tuple[str, str] | None:
    """开关属于哪个判据档族：`(族名, 这一族的后果)`；非判据档返回 None。"""
    for name, pattern, consequence in _CALIBER_FAMILIES:
        if pattern.match(flag):
            return name, consequence
    return None


def judge_liveness(
    *, disk: list[str], table: dict[str, dict[str, dict[str, str | None]]], allow: dict, root: Path | None = None
) -> tuple[list[str], list[str], list[str], dict[str, int]]:
    root = REPO_ROOT if root is None else root
    problems: list[str] = []
    ok: list[str] = []
    notes: list[str] = []
    used: set[tuple[str, str, str]] = set()
    index = _reader_index(root)
    declared_total = 0
    passed_total = 0
    locked_total = 0
    caliber_unread = 0
    presentation_unread = 0
    registered_unread = 0
    argparse_gates = 0
    for stem in disk:
        specs = flag_specs(stem)
        if not specs:
            continue
        argparse_gates += 1
        passed: set[str] = set()
        for flags in table.get(stem, {}).values():
            passed.update(flags)
        declared_total += len(specs)
        passed_total += len([f for f in specs if f in passed])
        locked = _locked_flags(stem, specs, index)
        locked_total += len([f for f in specs if f not in passed and f in locked])
        for flag in specs:
            if flag in passed or flag in locked:
                continue
            family = caliber_family(flag)
            key = ("manual-only", stem, flag)
            if key in allow:
                used.add(key)
                registered_unread += 1
                continue
            if family is None:
                presentation_unread += 1
                continue
            caliber_unread += 1
            problems.append(
                f"判据档无读者（{family[0]}）：{stem} 声明 {flag}——{family[1]}，"
                "但没有任何调用面传它、也没有任何代码引用它；"
                f"须登记 {key} 并写明「谁手动跑、跑的是什么口径」（`@路径` 指向现场），或让它真有个读者"
            )
    for key, reason in allow.items():
        if key[0] == "manual-only" and key not in used:
            problems.append(f"登记表失效：{key} 现在已被某个面或代码引用（理由：{reason}）")
    accounted = passed_total + locked_total + registered_unread + caliber_unread + presentation_unread
    if accounted != declared_total:
        problems.append(
            f"本门分母自校验失败：声明 {declared_total} ≠ 调用面 {passed_total} + 代码锁 {locked_total} "
            f"+ 登记 {registered_unread} + 判据档 {caliber_unread} + 范围呈现档 {presentation_unread}"
            f"（差 {declared_total - accounted:+}）——一个开关被两类同时计数或漏计，"
            "「无读者」这个数就不可信；判定四的读者分类必须互斥且完备"
        )
    notes.append(
        f"[SURFACE] 开关活性判定面：有 argparse 的门禁 {argparse_gates} 道、"
        f"声明 {declared_total} 个；读者四类 = 调用面 {passed_total} / 代码锁 {locked_total} / "
        f"登记表 {registered_unread} / 无读者 {caliber_unread + presentation_unread} = "
        f"判据档 {caliber_unread}（记红）+ 范围与呈现档 {presentation_unread}（本门不判，数字锁在 BASELINE）"
    )
    counts = {
        "declared_flags": declared_total,
        "passed_flags": passed_total,
        "locked_flags": locked_total,
        "caliber_unread": caliber_unread,
        "presentation_unread": presentation_unread,
        "registered_unread": registered_unread,
    }
    return problems, ok, notes, counts


def _reader_index(root: Path | None = None) -> list[tuple[str, str, set[str]]]:
    """一次读遍候选读者文件：(文件名, 正文, 该文件里出现的开关 token 集合)。"""
    root = REPO_ROOT if root is None else root
    files = sorted((root / "tests").rglob("*.py")) + [
        p for d in CALLER_DIRS for p in sorted((root / d).rglob("*.py")) if p.parent != root / "scripts" / "gates"
    ]
    out: list[tuple[str, str, set[str]]] = []
    for path in files:
        text = _read(path)
        out.append((path.name, text, set(_FLAG_RE.findall(text))))
    return out


def _locked_flags(stem: str, specs: Mapping[str, object], index: list[tuple[str, str, set[str]]]) -> set[str]:
    """代码锁：`tests/` 或其它脚本/实验里出现该开关，且同一文件点名这道门（正文或文件名）。"""
    core = stem.removeprefix("check_")
    locked: set[str] = set()
    for name, text, tokens in index:
        if stem not in text and not (core and core in name):
            continue
        locked.update(flag for flag in tokens if flag in specs)
    return locked


# ══ 判定五：BASELINE / 登记册 与实测对齐 ═══════════════════════════════
def judge_registration(
    *,
    counts: dict[str, int],
    baseline: dict,
    register_text: str,
) -> tuple[list[str], list[str], list[str]]:
    problems: list[str] = []
    ok: list[str] = []
    skips: list[str] = []

    def lookup(dotted: str):
        node = baseline
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node if isinstance(node, int) and not isinstance(node, bool) else None

    for label, dotted in XCHECK_KEYS.items():
        got = lookup(dotted)
        mine = counts.get(XCHECK_COUNT_KEYS[label])
        if mine is None:
            problems.append(
                f"交叉核对 {dotted}：本门复算键 `{XCHECK_COUNT_KEYS[label]}` 未装配"
                "——自产权威源缺位不判等于默认通过（BASELINE 侧键缺席才是登记债，走 [SKIP]）"
            )
            continue
        if got is None:
            skips.append(f"[SKIP] 交叉核对 {dotted}：BASELINE 键未取到（本门复算值 = {mine}）")
            continue
        if got != mine:
            problems.append(
                f"交叉核对：BASELINE `{dotted}` = {got}，本门结构复算 = {mine}（差 {got - mine:+}）"
                f"——登记数与实测不符；CF 门也复算这件事，两侧必须同时等于这一个数"
            )
        else:
            ok.append(f"[OK] 交叉核对：{dotted} = {got}")

    section = _section_one(register_text)
    if section is None:
        problems.append(f"{_rel(REGISTER)}：未找到 §1「现状快照」小节——本门的「调用口径」行无从对账")
        return problems, ok, skips
    rows = _register_rows(section)
    bodies = [text for label, texts in rows.items() if "调用口径" in label for text in texts]
    if not bodies:
        problems.append(f"{_rel(REGISTER)} §1：未找到「调用口径」行——本门的复算值没有登记面，写了没人查")
        return problems, ok, skips
    if len(bodies) > 1:
        problems.append(
            f"{_rel(REGISTER)} §1：「调用口径」行出现 {len(bodies)} 次——同一个标签两个口径，"
            "读者不知道信哪一行；这里逐行都照复算值判，只留一行等于把另一行的漂移放进暗处"
        )
    for body in dict.fromkeys(bodies):  # 逐字重复的同名行只判一次，红不因复制而刷屏
        declared = _declared_values(body)
        for label, count_key in ITEMS.items():
            authority = counts.get(count_key)
            if authority is None:
                problems.append(
                    f"「调用口径」项 {label}：本门复算键 `{count_key}` 未装配，该项无从对账"
                    "——`counts` 由本门自己装配，缺键是代码坏了，不能打 [SKIP] 蒙过去"
                )
                continue
            if label not in declared:
                problems.append(
                    f"{_rel(REGISTER)} §1「调用口径」行：未登记当前口径键 {label}（复算 {authority}）"
                    "——数字散在叙述里而无可解析的当前口径，等价于没有读者"
                )
                continue
            if declared[label] != authority:
                problems.append(
                    f"{_rel(REGISTER)} §1「调用口径」行：当前口径 {label} 声明 {declared[label]:.0f}，"
                    f"本门复算 {authority}（差 {declared[label] - authority:+.0f}）"
                    f"——BASELINE 键 = {BASELINE_KEYS.get(label, '—')}"
                )
                continue
            ok.append(f"[OK] 调用口径 · {label} = {authority:g}")
        unowned = sorted({k for k in declared if k not in ITEMS})
        if unowned:
            problems.append(f"{_rel(REGISTER)} §1「调用口径」行：括号里的键 {unowned} 无判定项——补权威源或删掉")
    for label, dotted in BASELINE_KEYS.items():
        got = lookup(dotted)
        mine = counts.get(ITEMS[label])
        if got is None:
            problems.append(f"BASELINE `{dotted}`：缺键或非整数（本门声明键，缺位即红）；复算值 = {mine}")
        elif mine is not None and got != mine:
            problems.append(
                f"BASELINE `{dotted}` = {got}，本门复算 {mine}（差 {got - mine:+}）——BASELINE 是唯一数字刷新点"
            )
        else:
            ok.append(f"[OK] BASELINE {dotted} = {got}")
    return problems, ok, skips


def _section_one(register_text: str) -> str | None:
    lines = register_text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("## 1.")), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start:end])


def _register_rows(section: str) -> dict[str, list[str]]:
    """§1 表格：标签 → 该标签下的**所有**行体（同名行不折叠——一个标签出现两次就是两个口径）。"""
    rows: dict[str, list[str]] = {}
    for match in _ROW_RE.finditer(section):
        label = match.group(1).strip()
        if label in ("维度", "") or set(label) <= {"-"}:
            continue
        rows.setdefault(label, []).append(match.group("body"))
    return rows


def _declared_values(row_body: str) -> dict[str, float]:
    bracket = _BRACKET_RE.search(row_body)
    if bracket is None:
        return {}
    out: dict[str, float] = {}
    for match in _PAIR_RE.finditer(bracket.group("body")):
        out[match.group(1)] = float(match.group(2))
    return out


# ══ 本门自身接线 ═════════════════════════════════════════════════════
def self_wiring(*, make_text: str, steps: list[Step], stem: str | None = None) -> list[str]:
    stem = stem or Path(__file__).stem
    script = f"scripts/gates/{stem}.py"
    in_make = any(script in line for line in make_faces(make_text).get(FACE_CHAIN, []))
    in_ci = any(script in " ".join(s.commands) for s in steps if s.file == "ci.yml")
    if in_make and in_ci:
        return []
    missing = [name for name, present in (("`make gates` 链", in_make), ("ci.yml", in_ci)) if not present]
    return [
        f"本门自身未接入：{'、'.join(missing)} 里没有 {script}——"
        "「新增门禁忘记接线」是 CA 轮那一族；本门判的是口径，接线是它生效的前提"
    ]


def surface_disclosure(counts: dict[str, int], disk: list[str], table: dict, allow_size: int) -> list[str]:
    faces = sorted({face for per in table.values() for face in per})
    return [
        f"[SURFACE] 判定面：在盘门禁 {len(disk)} 个逐项判定调用面归属；调用面 {len(faces)} 个 = {faces}"
        f"；声明开关 {counts.get('declared_flags')} 个逐个回答「谁传它」；BASELINE 交叉核对键 {len(XCHECK_KEYS)} 个"
        f" + 本门声明键 {len(BASELINE_KEYS)} 个（缺键即红）；登记表 {allow_size} 条（{len(KINDS)} 类），"
        "无理由/畸形/重复/失效各计红",
        f"[SURFACE] 不判定面：单面脚本 {sum(1 for s in table.values() if len(s) == 1)} 个不做跨面对账"
        f"（只有一个口径可比较 = 无可比较）；无 argparse 的门禁 {counts.get('no_argparse_gates')} 道不参与开关判定；"
        "workflow 步骤的 `if:` 条件（何时跑）与 `needs`/作业矩阵本门不判",
        "[SURFACE] 判据归属：非阻断/阻断两数由本门按结构复算（三层：步骤键 / `--warn-only` / shell 兜底「`||` 或 `set +e` 生效区」），"
        "CF 门独立复算同一数，两侧都须等于 BASELINE `gates.non_blocking_steps`——同一个数，两条独立实现",
    ]


def load_baseline_yaml(path: Path) -> tuple[dict | None, str | None]:
    """轻量取整数：只解析 `a.b.c: <int>` 形式的键（环境性前提缺失 ⇒ [SKIP]，不是红）。"""
    if not path.is_file():
        return None, f"{_rel(path)} 缺席（仓库级前提）"
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return None, "PyYAML 不可用（环境性前提缺失；本仓它是传递依赖，不是直接依赖）"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"BASELINE 解析失败：{type(exc).__name__}: {exc}"
    return (data if isinstance(data, dict) else None, None if isinstance(data, dict) else "BASELINE 顶层不是映射")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="门禁调用口径对账：调用面 / 开关 / 阻断性（零 LLM）")
    parser.add_argument("--list", action="store_true", help="只打印调用面归属表，不判定")
    parser.add_argument("--quiet", action="store_true", help="不打印逐项 [OK]")
    args = parser.parse_args(argv)

    for required in (MAKEFILE, WF_DIR, GATES_DIR, BASELINE, REGISTER):
        if not required.exists():
            print(f"[FAIL] 仓库级前提缺席：{_rel(required)}", file=sys.stderr)
            return 1

    make_text = _read(MAKEFILE)
    disk = sorted(p.stem for p in GATES_DIR.glob("*.py"))
    steps = workflow_steps()
    table = invocations(make_text, steps)[0]
    callers = {stem: programmatic_callers(stem) for stem in disk if not table.get(stem)}
    allow, allow_problems = parse_allowlist(ALLOWLIST)
    baseline, baseline_reason = load_baseline_yaml(BASELINE)
    register_text = _read(REGISTER)

    specs_cache: dict[str, dict[str, dict[str, str | None]]] = {stem: flag_specs(stem) for stem in disk}
    wiring_problems, wiring_ok = judge_wiring(disk=disk, table=table, callers=callers, allow=allow)
    flag_problems, flag_ok, flag_notes, diff_count = judge_flags(table=table, allow=allow, specs_cache=specs_cache)
    block_problems, block_ok, block_notes, block_counts = judge_blocking(steps, allow)
    live_problems, live_ok, live_notes, live_counts = judge_liveness(disk=disk, table=table, allow=allow)
    wiring_self = self_wiring(make_text=make_text, steps=steps)

    ci_steps = [s for s in steps if s.gate_stems() and s.file == "ci.yml"]
    chain_lines = make_faces(make_text).get(FACE_CHAIN, [])
    counts = {
        **block_counts,
        **live_counts,
        "disk_scripts": len(disk),
        "chain_scripts": len({s for line in chain_lines for s in _GATES_REF_RE.findall(line)}),
        "faces": len({face for per in table.values() for face in per}),
        "flag_diffs": diff_count,
        "ghost_flags": len(_ghost_flags(table, specs_cache)),
        "ci_unique_scripts": len({s for st in ci_steps for s in st.gate_stems()}),
        "ci_call_sites": sum(len(st.gate_stems()) for st in ci_steps),
        "make_targets": len(make_gate_deps(make_text)),
        "make_commands": len(chain_lines),
        "no_argparse_gates": len([s for s in disk if not flag_specs(s)]),
    }

    if args.list:
        for stem in sorted(table):
            for face, flags in sorted(table[stem].items()):
                print(f"{stem}\t{face}\t{sorted(flags)}")
        for stem, hit in sorted(callers.items()):
            print(f"{stem}\t callers\t{hit}")
        return 0

    reg_problems, reg_ok, reg_skips = (
        judge_registration(counts=counts, baseline=baseline or {}, register_text=register_text)
        if baseline is not None
        else ([], [], [f"[SKIP] BASELINE 未解析：{baseline_reason}"])
    )

    problems = (
        allow_problems + wiring_problems + flag_problems + block_problems + live_problems + reg_problems + wiring_self
    )
    oks = wiring_ok + flag_ok + block_ok + live_ok + reg_ok
    for line in reg_skips + flag_notes + block_notes + live_notes:
        print(line)
    if not args.quiet:
        for line in oks:
            print(line)

    disclosure = surface_disclosure(counts, disk, table, len(allow))
    if problems:
        print(f"\n[invocation-caliber] 阻断：{len(problems)} 项", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        for line in disclosure:
            print(line, file=sys.stderr)
        return 1
    print(
        f"\n[invocation-caliber] 通过：在盘 {counts['disk_scripts']} 道门各有归属、"
        f"{counts['declared_flags']} 个声明开关中判据档无读者 {counts['caliber_unread']}（须为 0）、"
        f"已登记 {counts['registered_unread']}、范围与呈现档无读者 {counts['presentation_unread']}（以数字锁定）、"
        f"跨面不对称 {counts['flag_diffs']} 处全部登记、"
        f"幽灵开关 {counts['ghost_flags']}、本门已接线"
    )
    for line in disclosure:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
