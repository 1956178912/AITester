"""登记面读侧门禁：`docs/PROJECT_STATUS_REGISTER.md` §1 的派生数字与 `docs/INDEX*.md` 的分册清单必须有读者。

归因对象 = **文档登记面的「写了没人查」**（CA 轮那一族在文档层的镜像）。改前实测
（2026-10-24，只读普查 + 复算，同一棵未提交树）：

| # | 形态 | 改前读数 | 成因 |
|---|---|---|---|
| ① | §1「静态检查」行声明 `**999** 文件已格式化（**BQ 轮复算**）` | HEAD（`00e8c24d`）树复算 `ruff format --check .` = **1037** ⇒ 漂移 **+38**（本仓未提交工作树 1048），跨 BR…CE 约 14 轮无人复算 | `check_baseline_numbers.py` 的 `_TARGETS` 只含 README 的「当前基线」块，登记册不在其扫描面；登记册自身只有两行覆盖率被 `check_artifact_doc_consistency.py` 锚定 |
| ② | §1「门禁总数」行写「权威口径 = BASELINE.yaml `gates` 节」 | BASELINE `gates.scripts_total` / `ci_unique_scripts` / `ci_call_sites` 在全仓 Python 里读者 **0**——被指认为权威的那一节没人复算 | `check_baseline.py` 结构校验只看 `static_checks.ruff_warnings` / `mypy_errors` 是否为 0，不看 `gates` 节 |
| ③ | `docs/reviews/` 分册在盘 78 份 vs INDEX 清单 | zh §3.5 登记 77（`X_ROUND_ZERO_LLM_VERIFICATION_2026-10-19.md` 未登记）、en §3.5 登记 74（另缺 BR / BS / BT / X） | 死链方向有读者（`check_doc_links.py --strict`），**反向（在盘⇒须在清单）读者 0**——分册写了就永久不可达 |
| ④ | zh §2.2「审稿人 15 分钟路径」编号序列 | `…19, 20, 22, 21, 23`——3 处非连续（CE 追加时把 CB 记 21、CC 记 22）；en §2.2 停在 5 条目（BR 之后 13 轮未进路径） | 编号是手写装饰、无读者，读者会把它当计数用 |
| ⑤ | 本门 `ci_gate_surface` 的两项按子串复算（CG 轮 2026-10-24 实测，非本轮自查） | 非阻断/阻断 **3 / 26**（结构复算 2 / 27）；调用点 **32**（非注释行复算 30） | ci.yml:366 注释里「改 continue-on-error: true」是一句**历史说明**而非当前键；ci.yml:556/720 注释里的脚本路径不是调用点。被污染的这两个数已经写进 BASELINE `gates` 与 §1 括号——注释能造出登记数 |

处置纪律：**纯读侧、只读、fail-closed，不改任何被登记的文档**——本门只判定并点名，
修复动作是把登记面刷新到复算值。五条口径约定：

1. **判定量必须有可复算权威源，且权威源自身也要有读者**。门禁链数字用文件系统 /
   `ci.yml` / `Makefile` 复算；`已格式化` 直接调 `ruff format --check .`（实测 0.03s）；
   `mypy源文件` 按 Makefile 实际传给 mypy 的命令行目标（`src/` 递归 + `config.py`）复算；
   测试四计数以 BASELINE `tests` 节为权威（其与实测的一致性由
   `TestBaselineNumbersConsistency` 拥有，本门只做拥有者活性检查）。指认 BASELINE 作权威
   却不复算它，等于把「没人查」写进权威源——所以 `ITEMS` 全部 `BASELINE_KEYS` 都要被读到、
   与本门复算值逐项相等（`self` 项）或作为权威值注入（`baseline` 项），缺键即红。刻意
   **不复制常量**（CE §76）：能从运行面取的就从运行面取。
2. **登记面用可解析的「当前口径」括号**：`〔当前口径…：<键> <数> / …〕`。行内其它数字
   一律按**历史快照叙述**处理、不判定（BASELINE `gates.note` 的「历史不回溯刷新」口径）。
   括号里出现而判定表里没有的键 = 无主数字 ⇒ 报红，防止下一轮继续加裸数字。
3. **一个判定量只留一个判据**。覆盖率两行已由 `check_artifact_doc_consistency.py` 以
   ±0.20pp 对 `coverage.xml` 判定，本门**不重判**，只披露归属并检查拥有者活性
   （拥有者失效也要红——否则「有人查」这件事本身会烂掉而无人知晓）。
4. **解析子进程摘要只取末行**。`ruff format --check` 会把 diff 正文一起打到 stdout，正文里
   完全可能出现「2 files would be reformatted, 3 files already formatted」这样的句式——本门
   初版对自己的测试文件全串 `search`，把 1047 读成了 5。摘要行才是工具给的口径，正文不是
   （见 `_summary_line`）。
5. **判据按结构，不按子串**（CG 轮对本门自身的修正，对应下表 ⑤）。`ci_gate_surface` 初版
   用 `"continue-on-error: true" in body` 和 `findall(ci_text)`，两条都被 ci.yml 的**注释**
   污染：非阻断/阻断复算成 3/26（实际 2/27），调用点复算成 32（实际 30）。现在按缩进层级
   识别步骤级键、注释行不参与计数（`step_effective_lines` / `step_is_non_blocking` /
   `ci_effective_refs`），与 `check_invocation_caliber.py` 的独立实现复算同一个数。

退出码：`0` = 全部对账通过；`1` = 存在漂移 / 未登记分册 / 无主数字 / 拥有者失效 /
仓库级前提缺席；`2` = 用法错误（argparse 默认）。前提缺失分两类：仓库内文件缺席
（登记册 / INDEX / Makefile / ci.yml / `src/`）属仓库级问题 ⇒ 计红；环境性前提
（`git` 不可用、`ruff`/PyYAML 模块缺席、BASELINE 解析失败）⇒ 打 `[SKIP]` 带成因、
不阻断（BZ §70「前提不成立必须显式 skip 带实测读数」）。

用法：
    python3 scripts/gates/check_registration_consistency.py [--verify-mypy] [--quiet]

`--verify-mypy`：额外真跑 `mypy src/ config.py`（本仓暖缓存实测 0.62s）核对
「命令行目标数 == mypy 自报源文件数」；默认不跑，只在披露行里说明未跑。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTER = REPO_ROOT / "docs" / "PROJECT_STATUS_REGISTER.md"
INDEX_ZH = REPO_ROOT / "docs" / "INDEX.md"
INDEX_EN = REPO_ROOT / "docs" / "INDEX.en.md"
REVIEWS_DIR = REPO_ROOT / "docs" / "reviews"
BASELINE = REPO_ROOT / "BASELINE.yaml"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = REPO_ROOT / "Makefile"
ALLOWLIST = REPO_ROOT / "docs" / "registration_consistency_allowlist.txt"

# 登记册 §1 的可解析声明位：`〔当前口径…：键 数 / 键 数 …〕`
_BRACKET_RE = re.compile(r"〔当前口径[^：:]*[：:](?P<body>[^〕]*)〕")
_PAIR_RE = re.compile(r"([^\s/；;、]+)\s+([0-9]+(?:\.[0-9]+)?)")
# §1 表格行：`| 维度 | 数值 | 验证入口 |`
_ROW_RE = re.compile(r"^\|\s*([^|]*?[^|\s])\s*\|(?P<body>[^\n]*)\|", re.M)

_RUFF_SURFACE_RE = re.compile(r"(\d+)\s+files?\s+would be reformatted,\s*(\d+)\s+files?\s+already formatted")
_RUFF_CLEAN_RE = re.compile(r"(\d+)\s+files?\s+already formatted")
_RUFF_VERSION_RE = re.compile(r"ruff\s+(\d+\.\d+\.\d+)")
_MYPY_OK_RE = re.compile(r"no issues found in (\d+) source files")
_MYPY_CHECKED_RE = re.compile(r"[Cc]hecked (\d+) (?:files|source files)")
_GATES_REF_RE = re.compile(r"scripts/gates/([A-Za-z0-9_]+)\.py")
_CI_STEP_RE = re.compile(r"^ {6}- name: (.*)$", re.M)
# 不阻断的三层判据（CG 轮：本门与 check_invocation_caliber.py 各实现一遍，判同一个数）
_COE_KEY_RE = re.compile(r"^continue-on-error:\s*true\s*(?:#.*)?$")
_WARN_ONLY_RE = re.compile(r"--warn-only(?![a-z0-9_-])")
_SHELL_SWALLOW_RE = re.compile(r"\|\|\s*(?:echo|true|exit[ \t]+0)(?![a-z0-9_-])|\|\|\\?\s*$")
_REVIEW_ROW_RE = re.compile(r"\]\(reviews/([^)\s]+)\)")
_NUMBERED_ROW_RE = re.compile(r"^(\d+)\.\s+\[[^\]]*\]\(reviews/[^)\s]+\)", re.M)


def _rel(path: Path) -> str:
    """路径显示名：仓库内用相对路径，仓库外（测试用 tmp_path）退化为绝对路径。"""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _run(cmd: list[str], root: Path) -> subprocess.CompletedProcess[str] | None:
    """指定仓库根下的只读子进程；不可用时返回 None（环境性前提缺失，不是红）。"""
    try:
        return subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    except (OSError, ValueError):
        return None


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ══ 复算面一：门禁链（文件系统 / ci.yml / Makefile）══════════════════════
def disk_gate_scripts(root: Path = REPO_ROOT) -> list[str]:
    return sorted(p.stem for p in (root / "scripts" / "gates").glob("*.py"))


def index_gate_scripts(root: Path = REPO_ROOT) -> tuple[list[str] | None, str | None]:
    """`git ls-files` 口径：CI clone 会拿到的门禁脚本。返回 (名单 | None, 不可用成因)。"""
    res = _run(["git", "ls-files", "scripts/gates"], root)
    if res is None:
        return None, "git 可执行文件不可用（子进程未能启动）"
    if res.returncode != 0:
        return None, f"git ls-files 退出码 {res.returncode}"
    return sorted(Path(line).stem for line in res.stdout.split() if line.endswith(".py")), None


def tracked_reviews(root: Path = REPO_ROOT) -> tuple[list[str] | None, str | None]:
    res = _run(["git", "ls-files", "docs/reviews"], root)
    if res is None:
        return None, "git 可执行文件不可用（子进程未能启动）"
    if res.returncode != 0:
        return None, f"git ls-files 退出码 {res.returncode}"
    return [Path(line).name for line in res.stdout.split() if line.endswith(".md")], None


def ci_steps(ci_text: str) -> list[tuple[str, str]]:
    """按 `      - name:` 切分步骤，返回 (步骤名, 步骤体)。"""
    lines = ci_text.splitlines()
    starts = [i for i, line in enumerate(lines) if _CI_STEP_RE.match(line)]
    steps: list[tuple[str, str]] = []
    for a, b in zip(starts, [*starts[1:], len(lines)], strict=True):
        name = _CI_STEP_RE.match(lines[a])
        assert name is not None
        steps.append((name.group(1).strip(), "\n".join(lines[a + 1 : b])))
    return steps


def step_effective_lines(body: str) -> list[tuple[int, str]]:
    """步骤体里「有生效位置」的行：`(缩进, 去空白内容)`——空行与注释行不在场。

    CG 轮的①号病灶正是把注释行当键：ci.yml 里 bilingual 步骤的注释有「改
    `continue-on-error: true`」这句历史说明，按子串搜整段正文就会把这一步算成非阻断。
    """
    out: list[tuple[int, str]] = []
    for line in body.splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        out.append((len(line) - len(text), text))
    return out


def step_is_non_blocking(body: str) -> bool:
    """三层不阻断判据（与 CG 门各写一遍、判同一个数）：步骤级 `continue-on-error: true`
    键（缩进恰为 8，注释里同名不算）/ 命令行 `--warn-only` / shell 兜底 `|| echo|true|exit 0`。"""
    for indent, text in step_effective_lines(body):
        if indent == 8 and _COE_KEY_RE.match(text):
            return True
        if _WARN_ONLY_RE.search(text) or _SHELL_SWALLOW_RE.search(text):
            return True
    return False


def ci_effective_refs(ci_text: str) -> list[str]:
    """ci.yml 里**非注释行**上的门禁脚本引用（调用点）。

    ①号病灶的第二处：按全文正则数调用点得 32，其中 2 处在注释里
    （`coverage_ratchet.py --allow-bump` 的手动流程说明、`check_citations.py --online` 的
    步骤说明）⇒ 注释里的引用不是调用点，结构复算 30。
    """
    refs: list[str] = []
    for line in ci_text.splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        refs.extend(_GATES_REF_RE.findall(text))
    return refs


def ci_gate_surface(ci_text: str) -> dict[str, int]:
    """ci.yml 的门禁引用面：唯一脚本数 / 调用点数 / 调用门禁的步骤数 / 阻断与非阻断步骤数。

    非阻断按**结构**三层复算（见 `step_is_non_blocking`），不按子串搜正文。改前实测（CG 轮）：
    子串判据复算 3/26，结构判据复算 **2/27**——多出来的那条是 ci.yml 注释里的
    `continue-on-error: true` 字样被当成了当前键，而这个数已经进了 BASELINE 与 §1。
    同一层判据若只按 `continue-on-error` 复算又得 2（第三条 `check_docs_history_drift.py
    --warn-only` 靠脚本开关不阻断）⇒ 少算一条假红。本门与 CG 门是同一个数的两条独立实现。
    """
    refs = ci_effective_refs(ci_text)
    gate_steps = [(name, body) for name, body in ci_steps(ci_text) if "scripts/gates/" in body]
    non_blocking = sum(1 for _, body in gate_steps if step_is_non_blocking(body))
    return {
        "ci唯一门禁": len(set(refs)),
        "ci调用点": len(refs),
        "门禁步骤": len(gate_steps),
        "非阻断步骤": non_blocking,
        "阻断步骤": len(gate_steps) - non_blocking,
    }


def make_gate_deps(make_text: str) -> list[str]:
    gates_line = next((line for line in make_text.splitlines() if line.startswith("gates:")), None)
    if gates_line is None:
        return []
    return gates_line.split("#", 1)[0].split()[1:]


def make_target_body(make_text: str, dep: str) -> str:
    """某个 make 目标的配方正文（不含注释行）；用于计数命令与判定接线。"""
    lines = make_text.splitlines()
    head = next((i for i, line in enumerate(lines) if re.match(rf"^{re.escape(dep)}:", line)), None)
    if head is None:
        return ""
    body: list[str] = []
    for nxt in lines[head + 1 :]:
        if nxt.startswith("\t"):
            stripped = nxt.strip()
            if stripped and not stripped.startswith("#"):
                body.append(stripped)
        elif nxt and not nxt.startswith(" "):
            break
    return "\n".join(body)


def make_gate_surface(make_text: str) -> dict[str, int]:
    """`make gates` 的前置目标数与展开后的命令行数。"""
    deps = make_gate_deps(make_text)
    commands = sum(len(make_target_body(make_text, dep).splitlines()) for dep in deps)
    return {"make目标": len(deps), "make命令": commands}


def invoked_by_chain(stem: str, make_text: str, ci_text: str) -> bool:
    """某门禁脚本是否真被跑：`make gates` 前置的配方里，或 ci.yml 的调用点里。"""
    script = f"scripts/gates/{stem}.py"
    if any(script in make_target_body(make_text, dep) for dep in make_gate_deps(make_text)):
        return True
    return script in ci_text


# ══ 复算面二：静态工具（ruff / mypy）════════════════════════════════════
def _summary_line(out: str) -> str:
    """只取子进程输出的末行汇总。

    `ruff format --check .` 会把 diff 正文一并打到 stdout（实测 2100 字符），而 diff 里
    完全可能出现「2 files would be reformatted, 3 files already formatted」这样的句子
    ——对本门自己的测试文件全串 search 就把 1047 读成了 5。解析工具摘要必须锚定汇总行。
    """
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def ruff_surface(root: Path = REPO_ROOT) -> tuple[dict[str, int] | None, str | None]:
    """`ruff format --check .` 的受检面：(读数, 不可用成因)。

    口径含 `.md`（ruff 会把 Markdown 的代码栅栏一并计入），因此新增一份分册也会让
    计数 +1——**登记值必须在所有文件落盘后复算**，否则本门在终跑转红。
    """
    res = _run([sys.executable, "-m", "ruff", "format", "--check", "."], root)
    if res is None:
        return None, "ruff 模块不可用（子进程未能启动）"
    summary = _summary_line(res.stdout + res.stderr)
    m = _RUFF_SURFACE_RE.search(summary)
    if m:
        return {"待格式化": int(m.group(1)), "已格式化": int(m.group(1)) + int(m.group(2))}, None
    m = _RUFF_CLEAN_RE.search(summary)
    if m:
        return {"待格式化": 0, "已格式化": int(m.group(1))}, None
    return None, f"ruff 输出末行无法解析（退出码 {res.returncode}，末行 {summary or '空输出'}）"


def ruff_version(root: Path = REPO_ROOT) -> tuple[str | None, str | None]:
    res = _run([sys.executable, "-m", "ruff", "--version"], root)
    if res is None:
        return None, "ruff 模块不可用（子进程未能启动）"
    m = _RUFF_VERSION_RE.search(res.stdout + res.stderr)
    if not m:
        return None, "ruff --version 输出无法解析"
    return m.group(1), None


def mypy_target_count(root: Path = REPO_ROOT) -> int | None:
    """按 Makefile 实际传给 mypy 的命令行目标复算源文件数（`src/` 递归 + `config.py`）。

    与 `$(PY) -m mypy src/ config.py` 同口径；真跑核对在 `--verify-mypy`。
    """
    src = root / "src"
    if not src.is_dir():
        return None
    count = len(list(src.rglob("*.py")))
    if (root / "config.py").is_file():
        count += 1
    return count


def mypy_self_report(root: Path = REPO_ROOT) -> tuple[int | None, str | None]:
    res = _run([sys.executable, "-m", "mypy", "src/", "config.py"], root)
    if res is None:
        return None, "mypy 模块不可用（子进程未能启动）"
    summary = _summary_line(res.stdout + res.stderr)
    m = _MYPY_OK_RE.search(summary) or _MYPY_CHECKED_RE.search(summary)
    if not m:
        return None, f"mypy 末行无法解析（退出码 {res.returncode}，末行 {summary or '空输出'}）"
    return int(m.group(1)), None


# ══ 登记面解析 ═════════════════════════════════════════════════════════
def section_one(register_text: str) -> str | None:
    """§1「现状快照」小节正文；标题缺席返回 None（登记面解析前提不成立）。

    只在 §1 内取行——登记册 §2–§5 也有表格，全文取行会把历史小节里的同名行
    当成当前口径（`register_rows` 保留首个命中，§1 在前只是巧合而非规则）。
    """
    start = re.search(r"^##\s+1\.", register_text, re.M)
    if start is None:
        return None
    tail = register_text[start.end() :]
    nxt = re.search(r"^##\s+\d\.", tail, re.M)
    return tail[: nxt.start()] if nxt else tail


def register_rows(register_text: str) -> dict[str, str]:
    """§1 表格：`维度` 名 → 数值单元格原文。重复行名取**首个**（= 当前表，历史表在其后）。"""
    rows: dict[str, str] = {}
    for m in _ROW_RE.finditer(register_text):
        label, body = m.group(1).strip(), m.group("body")
        if label in {"维度", "分项"} or set(label) <= {"-", " "} or "---" in label:
            continue
        rows.setdefault(label, body)
    return rows


def declared_values(row_body: str) -> dict[str, float]:
    """行内所有 `〔当前口径…〕` 括号的 `键 数值` 对（同名键后出现的括号覆盖先出现的）。"""
    out: dict[str, float] = {}
    for m in _BRACKET_RE.finditer(row_body):
        for key, num in _PAIR_RE.findall(m.group("body")):
            out[key] = float(num)
    return out


def bare_number_count(row_body: str) -> int:
    """括号外的裸数字计数——只披露不判定（历史快照叙述，口径见 docstring 约定 2）。"""
    without = _BRACKET_RE.sub("", row_body)
    without = re.sub(r"`[^`]*`", "", without)  # 行内代码里的示例数字不是声明
    return len(re.findall(r"(?<![\d.])\d[\d,]*(?:\.\d+)?(?![\d.])", without))


def index_booklets(path: Path) -> tuple[list[str], str | None]:
    """§3.5 小节里登记的 `reviews/*.md` 文件名（含 §2.2 之后的分组行；按小节切面）。"""
    if not path.is_file():
        return [], f"{_rel(path)} 缺席"
    text = _read(path)
    marker = "### 3.5"
    if marker not in text:
        return [], f"{_rel(path)}：未找到 §3.5 小节——清单面无从解析"
    tail = text[text.index(marker) :]
    nxt = tail.find("\n## ", 1)
    section = tail if nxt == -1 else tail[:nxt]
    names = [Path(target).name for target in _REVIEW_ROW_RE.findall(section)]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        return names, f"{_rel(path)} §3.5：重复登记行 {dup}"
    return names, None


def reviewer_path_numbers(path: Path) -> tuple[list[int], str | None]:
    """§2.2「审稿人路径」里指向分册的编号序列。"""
    if not path.is_file():
        return [], f"{_rel(path)} 缺席"
    text = _read(path)
    marker = "### 2.2"
    if marker not in text:
        return [], f"{_rel(path)}：未找到 §2.2 小节"
    tail = text[text.index(marker) + len(marker) :]
    nxt = tail.find("\n### ")
    section = tail if nxt == -1 else tail[:nxt]
    return [int(n) for n in _NUMBERED_ROW_RE.findall(section)], None


def parse_allowlist(
    path: Path = ALLOWLIST, *, reviews_dir: Path = REVIEWS_DIR
) -> tuple[dict[tuple[str, str], str], list[str]]:
    """`<分册名>:<INDEX 文件>  # 理由`；无理由 / 指向不存在分册 / 重复登记都计红（CA 轮口径）。"""
    entries: dict[tuple[str, str], str] = {}
    problems: list[str] = []
    if not path.is_file():
        return entries, []
    for lineno, raw in enumerate(_read(path).splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        spec, _, reason = line.partition("#")
        reason = reason.strip()
        spec = spec.strip()
        if ":" not in spec:
            problems.append(f"{_rel(path)}:{lineno}：格式应为 `<分册名>:<INDEX 文件>  # 理由`")
            continue
        booklet, index_file = spec.split(":", 1)
        booklet = booklet.strip()
        if not reason:
            problems.append(f"{_rel(path)}:{lineno}：豁免 {spec} 无理由——豁免必须是判定，不是便利")
            continue
        if not (reviews_dir / booklet).is_file():
            problems.append(f"{_rel(path)}:{lineno}：豁免 {booklet} 指向不存在的分册（陈旧豁免）")
            continue
        key = (booklet, index_file.strip())
        if key in entries:
            problems.append(f"{_rel(path)}:{lineno}：重复豁免 {key[0]} / {key[1]}")
        entries[key] = reason
    return entries, problems


# ══ 判定项表 ═══════════════════════════════════════════════════════════
# authority：
#   "self"     —— 本门复算即权威
#   "baseline" —— BASELINE 键是登记权威（其与实测的一致性另有拥有者）
ITEMS: dict[str, dict[str, str]] = {
    "门禁脚本": {"row": "门禁总数", "authority": "self"},
    "门禁索引": {"row": "门禁总数", "authority": "self"},
    "ci唯一门禁": {"row": "门禁总数", "authority": "self"},
    "ci调用点": {"row": "门禁总数", "authority": "self"},
    "门禁步骤": {"row": "门禁总数", "authority": "self"},
    "非阻断步骤": {"row": "门禁总数", "authority": "self"},
    "阻断步骤": {"row": "门禁总数", "authority": "self"},
    "make目标": {"row": "门禁总数", "authority": "self"},
    "make命令": {"row": "门禁总数", "authority": "self"},
    "已格式化": {"row": "静态检查", "authority": "self"},
    "mypy源文件": {"row": "静态检查", "authority": "self"},
    "passed": {"row": "全量测试", "authority": "baseline"},
    "failed": {"row": "全量测试", "authority": "baseline"},
    "skipped": {"row": "全量测试", "authority": "baseline"},
    "collected": {"row": "全量测试", "authority": "baseline"},
}
BASELINE_KEYS: dict[str, str] = {
    "门禁脚本": "gates.scripts_total",
    "门禁索引": "gates.index_scripts",
    "ci唯一门禁": "gates.ci_unique_scripts",
    "ci调用点": "gates.ci_call_sites",
    "门禁步骤": "gates.gate_steps",
    "非阻断步骤": "gates.non_blocking_steps",
    "阻断步骤": "gates.blocking_steps",
    "make目标": "gates.make_targets",
    "make命令": "gates.make_commands",
    "已格式化": "static_checks.formatted_files",
    "mypy源文件": "static_checks.mypy_source_files",
    "passed": "tests.total_passed",
    "failed": "tests.total_failed",
    "skipped": "tests.total_skipped",
    "collected": "tests.collected",
}
# 拥有者活性表：(这件事, 拥有者文件, 必须仍在文件里的锚点)
OWNERS: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "登记册 §1 覆盖率两行对 coverage.xml",
        "scripts/gates/check_artifact_doc_consistency.py",
        ("_REGISTER_DECL", "总行覆盖", "总分支覆盖", "_REGISTER_TOLERANCE_PP"),
    ),
    ("README 当前基线块不得硬编码", "scripts/gates/check_baseline_numbers.py", ("_DRIFT_PATTERNS", "_TARGETS")),
    ("文档死链方向（清单→盘）", "scripts/gates/check_doc_links.py", ("_LINK_RE",)),
    (
        "BASELINE tests 与实测收集数",
        "tests/test_2026_10_10_optimization_batch.py",
        ("class TestBaselineNumbersConsistency",),
    ),
    ("中英日期行与 H2 骨架同步", "scripts/gates/check_bilingual_docs.py", ("_DATE_RE",)),
    (
        "门禁调用口径（跨面开关 / 判据档读者 / 阻断层）",
        "scripts/gates/check_invocation_caliber.py",
        ("_CALIBER_FAMILIES", "judge_liveness", "invocation_caliber_allowlist"),
    ),
]
# 锚在 `make gates` / ci.yml 上才算活的拥有者（测试文件由 `make test` 跑，不在此列）
CHAIN_OWNED = {
    "scripts/gates/check_artifact_doc_consistency.py",
    "scripts/gates/check_baseline_numbers.py",
    "scripts/gates/check_doc_links.py",
    "scripts/gates/check_bilingual_docs.py",
    "scripts/gates/check_invocation_caliber.py",
}


def load_baseline(root: Path = REPO_ROOT) -> tuple[dict | None, str | None]:
    if not (root / "BASELINE.yaml").is_file():
        return None, f"{_rel(root / 'BASELINE.yaml')} 缺席"
    try:
        # 仅此处需要；缺席按环境性前提处置
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return None, "PyYAML 不可用（环境性前提缺失）"
    try:
        data = yaml.safe_load(_read(root / "BASELINE.yaml"))
    except Exception as exc:  # pragma: no cover - 解析失败由 check_baseline 门点名
        return None, f"BASELINE.yaml 解析失败（{type(exc).__name__}）"
    if not isinstance(data, dict):
        return None, "BASELINE.yaml 顶层不是映射"
    return data, None


def baseline_lookup(data: dict, dotted: str) -> tuple[object, str | None]:
    node: object = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None, f"键 {dotted} 缺席"
        node = node[part]
    return node, None


def compute_authorities(
    *,
    verify_mypy: bool,
    root: Path = REPO_ROOT,
) -> tuple[dict[str, float], list[str], list[str]]:
    """返回 (每项权威值, 披露与 [SKIP] 行, 前提缺失产生的问题)。"""
    auth: dict[str, float] = {}
    notes: list[str] = []
    problems: list[str] = []

    disk = disk_gate_scripts(root)
    auth["门禁脚本"] = float(len(disk))
    tracked, reason = index_gate_scripts(root)
    if tracked is None:
        notes.append(f"[SKIP] 门禁索引口径未取到：{reason}")
    else:
        auth["门禁索引"] = float(len(tracked))
        only_disk = sorted(set(disk) - set(tracked))
        if only_disk:
            notes.append(
                f"[SURFACE] 门禁口径：盘 {len(disk)} / 索引 {len(tracked)}，未跟踪 {len(only_disk)} 个 "
                f"{only_disk}——读作「本轮未提交」，CI clone 拿不到这些"
            )

    ci_text = _read(root / ".github/workflows/ci.yml")
    make_text = _read(root / "Makefile")
    for key, value in {**ci_gate_surface(ci_text), **make_gate_surface(make_text)}.items():
        auth[key] = float(value)

    surface, reason = ruff_surface(root)
    if surface is None:
        notes.append(f"[SKIP] 已格式化面复算未执行：{reason}")
    else:
        auth["已格式化"] = float(surface["已格式化"])
        if surface["待格式化"]:
            notes.append(
                f"[SKIP] `ruff format --check .` 另有 {surface['待格式化']} 个文件待格式化——"
                "该面由 `make format` 判定，本门只取受检总数（含 .md）"
            )

    targets = mypy_target_count(root)
    if targets is None:
        problems.append(f"{_rel(root / 'src')} 缺席：mypy 命令行目标无从复算")
    else:
        auth["mypy源文件"] = float(targets)
        if verify_mypy:
            self_reported, mypy_reason = mypy_self_report(root)
            if self_reported is None:
                problems.append(f"--verify-mypy：mypy 真跑核对未完成（{mypy_reason}）")
            elif self_reported != targets:
                problems.append(
                    f"--verify-mypy：mypy 自报 {self_reported} 源文件，命令行目标复算 {targets}"
                    "——口径分叉，须核对 Makefile 的 mypy 调用与排除面"
                )
        else:
            notes.append(
                "[SURFACE] mypy 面按命令行目标（`src/` 递归 + `config.py`）派生，未真跑核对（--verify-mypy 可核对）"
            )

    data, baseline_reason = load_baseline(root)
    if data is None:
        if "缺席" in (baseline_reason or ""):
            problems.append(f"BASELINE 权威项无从对账：{baseline_reason}")
        else:
            notes.append(f"[SKIP] BASELINE 对账未执行：{baseline_reason}")
    else:
        for key, spec in ITEMS.items():
            if spec["authority"] != "baseline":
                continue
            raw, missing = baseline_lookup(data, BASELINE_KEYS[key])
            if missing is not None:
                problems.append(f"{spec['row']} 项 {key}：BASELINE.yaml {missing}——无权威值可对")
                continue
            if not isinstance(raw, int):
                problems.append(f"{spec['row']} 项 {key}：BASELINE.yaml {BASELINE_KEYS[key]} 非整数（{raw!r}）")
                continue
            auth[key] = float(raw)

        # self 权威项在 BASELINE 里的登记键必须有读者：值不等或键缺席都计红
        baseline_path = _rel(root / "BASELINE.yaml")
        for key, spec in ITEMS.items():
            if spec["authority"] != "self":
                continue
            authority = auth.get(key)
            if authority is None:
                continue  # 该面已按 [SKIP] 处理，不双重计红
            raw, missing = baseline_lookup(data, BASELINE_KEYS[key])
            if missing is not None:
                problems.append(
                    f"{baseline_path} {missing}——本门复算 {key} = {authority:.0f}，"
                    "被指认为登记的权威源却没有这一键，等于没人读"
                )
                continue
            if not isinstance(raw, int):
                problems.append(
                    f"{baseline_path} {BASELINE_KEYS[key]} 非整数（{raw!r}）——本门复算 {key} = {authority:.0f}"
                )
                continue
            if float(raw) != authority:
                problems.append(
                    f"{baseline_path} {BASELINE_KEYS[key]} = {raw}，本门复算 {key} = {authority:.0f}"
                    f"（差 {float(raw) - authority:+.0f}）——BASELINE 与运行面口径分叉"
                )

        version, version_reason = ruff_version(root)
        if version_reason is not None:
            notes.append(f"[SKIP] ruff 版本对账未执行：{version_reason}")
        else:
            declared_version, missing = baseline_lookup(data, "static_checks.ruff_version")
            if missing is None and str(declared_version) != version:
                problems.append(
                    f"BASELINE static_checks.ruff_version = {declared_version!r}，"
                    f"实跑 `ruff --version` = {version}——工具口径分叉"
                )

        # 派生恒等：collected = passed + failed + skipped + xfailed（S7 校正后的口径）
        collected = auth.get("collected")
        passed = auth.get("passed")
        failed = auth.get("failed")
        skipped = auth.get("skipped")
        xfailed, xfailed_missing = baseline_lookup(data, "tests.total_xfailed")
        if (
            collected is not None
            and passed is not None
            and failed is not None
            and skipped is not None
            and xfailed_missing is None
            and isinstance(xfailed, int)
        ):
            derived = passed + failed + skipped + float(xfailed)
            if derived != collected:
                problems.append(
                    f"BASELINE tests.collected = {collected:.0f}，按 passed+failed+skipped+xfailed "
                    f"派生 = {derived:.0f}（xfailed={xfailed}）——收集口径与分项计数不等"
                )
    return auth, notes, problems


# ══ 判定一：登记册 §1 数字 ↔ 权威值 ═════════════════════════════════════
def check_declared_numbers(
    auth: dict[str, float], register_text: str, *, register_path: Path = REGISTER
) -> tuple[list[str], list[str], list[str], dict[str, dict[str, float]]]:
    """返回 (问题, [OK], [SKIP], {行名: 该行已登记的当前口径键值})。"""
    section = section_one(register_text)
    if section is None:
        return ([f"{_rel(register_path)}：未找到 §1「现状快照」小节标题——登记面无从解析"], [], [], {})
    rows = register_rows(section)
    if not rows:
        return ([f"{_rel(register_path)} §1：未解析到表格行——登记面无从对账"], [], [], {})
    problems: list[str] = []
    ok: list[str] = []
    skips: list[str] = []
    per_row: dict[str, dict[str, float]] = {}
    for key, spec in ITEMS.items():
        label = spec["row"]
        body = next((text for name, text in rows.items() if label in name), None)
        if body is None:
            problems.append(f"{_rel(register_path)} §1：未找到「{label}」行——缺席 ≠ 通过")
            continue
        declared = per_row.setdefault(label, declared_values(body))
        authority = auth.get(key)
        if authority is None:
            skips.append(f"[SKIP] 「{label}」项 {key}：权威值未取到，本项不判（成因见上）")
            continue
        if key not in declared:
            problems.append(
                f"{_rel(register_path)} §1「{label}」行：未登记当前口径键 {key}（权威值 {authority:.0f}）"
                "——数字散在叙述里而无可解析的当前口径，等价于没有读者"
            )
            continue
        got = declared[key]
        if got != authority:
            problems.append(
                f"{_rel(register_path)} §1「{label}」行：当前口径 {key} 声明 {got:.0f}，权威复算 {authority:.0f}"
                f"（差 {got - authority:+.0f}）——权威源 = {spec['authority']}，"
                f"BASELINE 键 = {BASELINE_KEYS.get(key, '—')}"
            )
            continue
        ok.append(f"[OK] {label} · {key} = {got:.0f}（权威 {spec['authority']}）")

    unowned = sorted({f"{label}:{key}" for label, declared in per_row.items() for key in declared if key not in ITEMS})
    if unowned:
        problems.append(
            f"{_rel(register_path)} §1：当前口径括号里的键 {unowned} 无判定项——要么补权威源，要么删掉该数字"
            "（「登记在场、读者缺席」正是本门要收的口）"
        )
    return problems, ok, skips, per_row


# ══ 判定二：分册 ↔ INDEX 清单（在盘→清单方向）═══════════════════════════
def _index_label(side: str, root: Path = REPO_ROOT) -> Path:
    return root / ("docs/INDEX.md" if side == "zh" else "docs/INDEX.en.md")


def check_index_presence(root: Path = REPO_ROOT) -> tuple[list[str], list[str], list[str]]:
    problems: list[str] = []
    ok: list[str] = []
    notes: list[str] = []
    reviews = root / "docs" / "reviews"
    if not reviews.is_dir():
        return ([f"{_rel(reviews)}：目录缺席——清单对账无从进行"], [], [])
    on_disk = sorted(p.name for p in reviews.glob("*.md"))
    allow, allow_problems = parse_allowlist(
        root / "docs" / "registration_consistency_allowlist.txt", reviews_dir=reviews
    )
    problems += allow_problems

    for side in ("zh", "en"):
        path = _index_label(side, root)
        names, parse_problem = index_booklets(path)
        if parse_problem is not None:
            problems.append(parse_problem)
            continue
        suffix = "" if side == "zh" else ".en"
        orphans = [b for b in on_disk if b not in set(names) and (b, f"docs/INDEX{suffix}.md") not in allow]
        if orphans:
            problems.append(
                f"{_rel(path)} §3.5：在盘分册未登记 {len(orphans)} 份（{orphans}）"
                f"——死链方向有读者，反方向没有：分册写了就等于不存在"
            )
        else:
            ok.append(f"[OK] {side} 侧 §3.5 覆盖在盘 {len(on_disk)} 份（登记 {len(names)} 行）")
        nums, num_reason = reviewer_path_numbers(path)
        if num_reason is not None:
            notes.append(f"[SKIP] {side} 侧 §2.2 编号未解析：{num_reason}")
            continue
        gaps = [(nums[i], nums[i + 1]) for i in range(len(nums) - 1) if nums[i + 1] != nums[i] + 1]
        if gaps:
            problems.append(
                f"{_rel(path)} §2.2：分册条目编号非连续 {gaps}（全长 {len(nums)}：{nums}）"
                "——编号是手写装饰，而读者会把它当计数用"
            )
        else:
            ok.append(f"[OK] {side} 侧 §2.2 编号连续（{len(nums)} 条目）")

    tracked, reason = tracked_reviews(root)
    if tracked is None:
        notes.append(f"[SKIP] 分册索引口径未取到：{reason}")
    else:
        only_disk = sorted(set(on_disk) - set(tracked))
        if only_disk:
            notes.append(
                f"[SURFACE] 分册口径：在盘 {len(on_disk)} / 索引 {len(tracked)}，未跟踪 {len(only_disk)} 份"
                f"（{only_disk}）——读作「本轮未提交」，不是丢失"
            )
        else:
            notes.append(f"[SURFACE] 分册口径：在盘 {len(on_disk)} == 索引 {len(tracked)}")
    return problems, ok, notes


# ══ 判定三：拥有者活性 + 本门自身接线 ═══════════════════════════════════
def check_owner_liveness(*, make_text: str, ci_text: str, root: Path = REPO_ROOT) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    ok: list[str] = []
    for matter, owner, anchors in OWNERS:
        path = root / owner
        if not path.is_file():
            problems.append(f"拥有者 {matter}：{_rel(path)} 缺席——被指派的读者已不存在")
            continue
        text = _read(path)
        missing = [a for a in anchors if a not in text]
        if missing:
            problems.append(
                f"拥有者 {matter}：{_rel(path)} 内锚点缺失 {missing}——该门不再判定这件事，而登记面仍把它当作「有人查」"
            )
            continue
        if owner in CHAIN_OWNED:
            stem = path.stem
            if not invoked_by_chain(stem, make_text, ci_text):
                problems.append(f"拥有者 {matter}：{_rel(path)} 不在 `make gates` 链与 ci.yml 内——写了没人跑")
                continue
        ok.append(f"[OK] 拥有者活性：{matter}")
    return problems, ok


def self_check_wiring(*, make_text: str, ci_text: str, stem: str | None = None) -> list[str]:
    stem = stem or Path(__file__).stem
    if invoked_by_chain(stem, make_text, ci_text):
        return []
    return [
        f"本门自身未接入链：`scripts/gates/{stem}.py` 既不在 `make gates` 前置配方也不在 ci.yml——"
        "「新增门禁但忘记接线」是 CA 轮那一族"
    ]


# ══ 受检面披露（每条输出路径都打印：CE §76）════════════════════════════
def surface_disclosure(
    per_row: dict[str, dict[str, float]],
    auth: dict[str, float],
    *,
    register_text: str,
    root: Path = REPO_ROOT,
) -> list[str]:
    section = section_one(register_text) or ""
    rows = register_rows(section)
    bare = sum(bare_number_count(rows[label]) for label in per_row if label in rows)
    reviews = root / "docs" / "reviews"
    on_disk = len(list(reviews.glob("*.md"))) if reviews.is_dir() else 0
    zh_names, _ = index_booklets(_index_label("zh", root))
    en_names, _ = index_booklets(_index_label("en", root))
    return [
        f"[SURFACE] 判定面：ITEMS 数字项 {len(ITEMS)}（权威值已取到 {len(auth)}）"
        f" / BASELINE 登记键 {len(BASELINE_KEYS)} 个全部被读（缺键与非整数都计红）"
        f" / 拥有者活性 {len(OWNERS)} 项"
        f" / 在盘分册 {on_disk} 份双向对账（zh §3.5 登记 {len(zh_names)}、en §3.5 登记 {len(en_names)}）"
        f" / §2.2 编号 zh {len(reviewer_path_numbers(_index_label('zh', root))[0])} 条目、"
        f"en {len(reviewer_path_numbers(_index_label('en', root))[0])} 条目",
        f"[SURFACE] 不判定面：§1 解析到表格行 {len(rows)}，本门检其中 {len(per_row)} 行"
        f"（已声明当前口径键 {sum(len(v) for v in per_row.values())} 个 / 判定项 {len(ITEMS)} 个）；"
        f"这 {len(per_row)} 行内括号外裸数字 {bare} 个按历史快照叙述处理、不判定"
        "（判定只认〔当前口径…〕括号）",
        "[SURFACE] 覆盖率两行本门不重判：权威 = check_artifact_doc_consistency.py 对 coverage.xml ±0.20pp"
        "（一个判定量只留一个判据）",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="登记面读侧对账：§1 派生数字 + 分册清单在场性 + 读者活性")
    parser.add_argument("--verify-mypy", action="store_true", help="额外真跑 mypy 核对源文件数口径")
    parser.add_argument("--quiet", action="store_true", help="不打印逐项 [OK]")
    args = parser.parse_args(argv)

    for required in (REGISTER, INDEX_ZH, INDEX_EN, REVIEWS_DIR, MAKEFILE, CI_YML):
        if not required.exists():
            print(f"[FAIL] 仓库级前提缺席：{_rel(required)}", file=sys.stderr)
            return 1

    make_text = _read(MAKEFILE)
    ci_text = _read(CI_YML)
    register_text = _read(REGISTER)

    auth, auth_notes, problems = compute_authorities(verify_mypy=args.verify_mypy)
    number_problems, number_ok, number_skips, per_row = check_declared_numbers(auth, register_text)
    index_problems, index_ok, index_notes = check_index_presence()
    owner_problems, owner_ok = check_owner_liveness(make_text=make_text, ci_text=ci_text)
    wiring_problems = self_check_wiring(make_text=make_text, ci_text=ci_text)
    problems += number_problems + index_problems + owner_problems + wiring_problems

    for line in auth_notes + index_notes + number_skips:
        print(line)
    if not args.quiet:
        for line in number_ok + index_ok + owner_ok:
            print(line)

    surface = surface_disclosure(per_row, auth, register_text=register_text)
    if problems:
        print(f"\n[registration-consistency] 阻断：{len(problems)} 项", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        for line in surface:
            print(line, file=sys.stderr)
        return 1
    print(
        f"\n[registration-consistency] 通过：数字项 {len(ITEMS)} 全部对账、分册清单双向覆盖、"
        f"拥有者活性 {len(OWNERS)} 项在位、本门已接线"
    )
    for line in surface:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
