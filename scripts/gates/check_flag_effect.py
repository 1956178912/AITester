r"""门禁开关有效性对账：命令行上出现的开关，是否真的在源码里接了线。

CG 轮判「这个开关有没有人传」（读者活性），并把 CG 边界①显式交给下一族：

> **只判静态调用面**，不执行任何门禁。「传了这个开关」不等于「那个开关真改变了行为」。

本轮闭合它的**可静态判定核**：一个开关是否改变了行为，不必跑那道门也能判——看它的 `dest`
在门禁源码里有没有被读。`add_argument("--verify")` 之后整个模块再没出现过 `args.verify`，
那么这个开关在命令行上出现多少次、被多少个面传过，都不产生任何效果。

改前实测（2026-10-24，只读复算，权威 = 本门就地复算）：

| # | 形态 | 改前读数 | 后果 |
|---|---|---|---|
| ① | 开关声明后 `dest` 从不被读 | 31 道门禁里 24 道有 argparse、声明 **71** 个开关实例，`dest` 从不被读的 **2** 个：`check_docs_history_drift --warn-only`（dest `warn_only`，调度只读 `args.strict`）与 `checksum_results --verify`（dest `verify`，调度只读 `args.write`） | 两个**都是判据档**，且**都被 ci.yml 真实传入**（ci.yml:744、ci.yml:298）。CG 判定四把「调用面出现该 token」算作读者，于是「判据档无读者 0」这条绿是**真绿但误导**：token 有读者，开关没有效果路径 |
| ② | 有效性由「兄弟开关缺席」间接保证 | `checksum_results` 的 `--write`/`--verify` 在同一个 `add_mutually_exclusive_group(required=True)` 里，组内 `--write` 被读 2 次、`--verify` 被读 **0** 次；全仓 31 道门禁里这样的互斥必填组**只有这 1 个** | 今天的行为与按 `--verify` 调度**等价**（`required=True` 保证恰有一个为真），所以这不是「CI 现在跑错了」，而是**潜在**：等价性由那个组担保，不由开关自己担保。一旦有人去掉 `required=True`，或往组里加第三个模式（如 `--list-only`），`--verify` 立刻和新模式一起落进 `else` 分支——命令行写着「校验」，跑的是别的 |
| ③ | 同名开关在不同门禁里一边活一边死 | `--verify` 这个名字出现在 **2** 道门：`check_baseline`（dest 被读）与 `checksum_results`（不被读）。71 个实例去重后只有 **51** 个唯一名，重名 11 组（`--list` ×6、`--strict` ×4、`--json` ×4…） | 「这个开关在这道门里生效」不能从名字推断，只能逐 (门禁, 开关) 判——本轮分母因此是 **(门禁, 开关) 组合数 71**，不是唯一名 51 |
| ④ | 无逃逸写法（判据得以成立的前提） | 扫 `vars(args)` / `getattr(args, …)` / `**args.` / `args.__dict__` / `parse_known_args`：31 道门禁命中 **0** | 命中即「整包读走」，dest 级判定就会造假；本门把这类门禁单列为**不可判**并计红（fail-closed：不可判必须是显式的，不能静默算通过） |
| ⑤ | 「装饰性开关」在本仓不是正当终态 | `--warn-only` 的 help 自述「与默认行为一致，便于 CI 可读性」——它是**被文档承认**的 no-op | 处置只有两种：接线，或删掉。因此本门**不设豁免表**：加一张表等于把「没人接线的开关」变成可以申请的常态，与 CG 判定五里「33 条豁免会把登记表变成橡皮章」同一条顾虑 |

处置纪律：**纯读侧、只读、fail-closed，不改任何被判定文件**。四条口径约定：

1. **判 (门禁, 开关) 组合，不判开关名**。71 个实例逐个回答「它的 dest 在这道门里被没被读」；
   同名不同门各算一条（对应③）。
2. **`dest` 由 argparse 自己的规则复算**：`--foo-bar` → `foo_bar`，显式 `dest=` 覆盖；
   只在 `add_argument(...)` 调用体之外的行上计读，避免把声明本身读成使用。
3. **四态互斥且完备**：`活`（dest 被读）/ `代理`（dest 不被读，但属于 `required=True` 的互斥组
   且组内有兄弟被读——当下等价、保证来自组）/ `死`（dest 不被读且无结构代理）/ `不可判`
   （整包读走 Namespace）。分母自校验 `声明 = 活 + 代理 + 死 + 不可判`，不成立即红。
4. **`代理` 与 `死` 都记红**，不给豁免。理由见⑤：一个不改变任何行为的开关留在命令行上，
   下一个人就会按它的名字推断口径。修法要么让 dest 真去选分支，要么把开关删掉。

退出码：`0` = 全部开关有效或已接线；`1` = 存在死开关 / 代理开关 / 不可判门禁 / 分母自校验失败 /
在盘门的源码缺席或不可解析 / 本门复算键缺位 / 本门未接线；`2` = 用法错误（argparse 默认）。仓库级前提缺席（`Makefile` /
`scripts/gates` / `BASELINE.yaml` / 登记册）⇒ 计红——自产权威源缺位一律计红，否则「少判一项」
会永久静默。

用法：
    python3 scripts/gates/check_flag_effect.py [--list] [--quiet]

`--list`：只打印逐 (门禁, 开关) 的 dest 与活性状态表，不判定；`--quiet`：不打印逐项 `[OK]`。
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
GATES_DIR = REPO_ROOT / "scripts" / "gates"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
BASELINE = REPO_ROOT / "BASELINE.yaml"
REGISTER = REPO_ROOT / "docs" / "PROJECT_STATUS_REGISTER.md"

_PAIR_RE = re.compile(r"([^\s/；;、]+)\s+([0-9]+(?:\.[0-9]+)?)")
_BRACKET_RE = re.compile(r"〔当前口径[^：:]*[：:](?P<body>[^〕]*)〕")

# §1「开关有效性（CH 轮）」行的声明键 → 本门复算值键（同名，全部 authority=self）
ITEMS: dict[str, str] = {
    "在盘门禁": "disk_scripts",
    "有argparse门禁": "argparse_gates",
    "开关实例": "declared_flags",
    "有效开关": "live_flags",
    "代理开关": "proxy_flags",
    "死开关": "dead_flags",
    "不可判开关": "opaque_flags",
    "不可判门禁": "opaque_gates",
    "互斥必填组": "me_groups",
}
BASELINE_KEYS: dict[str, str] = {k: f"flag_effect.{v}" for k, v in ITEMS.items()}


def _escape_reads(tree: ast.AST, ns: set[str]) -> list[str]:
    """整包读走 Namespace 的写法（AST 判定，不按子串——按子串搜会把「文档里提到这些写法」
    的门禁误判成不可判，包括本门自己）。命中则 dest 级活性无法静态判定。"""
    hits: list[str] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id == "vars" and _uses_ns(n.args, ns):
                hits.append("vars(args)")
            elif isinstance(f, ast.Name) and f.id == "getattr" and _uses_ns(n.args[:1], ns):
                hits.append("getattr(args, …)")
            elif isinstance(f, ast.Attribute) and f.attr == "parse_known_args":
                hits.append("parse_known_args()")
            hits.extend("**args 展开" for kw in n.keywords if kw.arg is None and _uses_ns([kw.value], ns))
        elif isinstance(n, ast.Attribute) and n.attr == "__dict__" and _uses_ns([n.value], ns):
            hits.append("args.__dict__")
        elif isinstance(n, ast.Name) and n.id in ns and _is_call_arg(n, tree):
            hits.append("整个 args 传进别的函数")
    return sorted(set(hits))


def _uses_ns(nodes: list[ast.expr], ns: set[str]) -> bool:
    for node in nodes:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id in ns:
                return True
    return False


def _is_call_arg(target: ast.Name, tree: ast.AST) -> bool:
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            for a in list(n.args) + [kw.value for kw in n.keywords]:
                if a is target:
                    return True
    return False


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def gate_scripts() -> list[str]:
    return sorted(p.stem for p in GATES_DIR.glob("*.py"))


def _dest_of(call: ast.Call) -> str | None:
    """argparse 的 dest 推导：第一个长选项名去掉 `--`、`-` 换 `_`；显式 `dest=` 覆盖。"""
    flag = None
    for a in call.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.startswith("--"):
            flag = a.value
            break
    if flag is None:
        return None
    dest = flag[2:].replace("-", "_")
    for kw in call.keywords:
        if kw.arg == "dest" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            dest = kw.value.value
    return dest


def _flag_of(call: ast.Call) -> str | None:
    for a in call.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.startswith("--"):
            return a.value
    return None


def _decl_ranges(tree: ast.AST) -> list[tuple[int, int]]:
    """`add_argument(...)` 调用占据的行区间——这些行里出现的 `args.x` 是文档字符串或 help 文本，不算使用。"""
    return [
        (n.lineno, n.end_lineno or n.lineno)
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "add_argument"
    ]


def _namespace_names(tree: ast.AST) -> set[str]:
    """被赋成 `parse_args()` 结果的局部名——只有 `args.x` / `a.x` 这类前缀才算真读。"""
    out = set()
    for n in ast.walk(tree):
        if (
            isinstance(n, ast.Assign)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Attribute)
            and n.value.func.attr in ("parse_args", "parse_known_args")
        ):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
    return out


def _mutually_exclusive(tree: ast.AST) -> tuple[dict[str, bool], dict[str, str]]:
    """返回 (组变量名 → required, 组内 dest → 组变量名)。

    `mode = parser.add_mutually_exclusive_group(required=True)` 之后 `mode.add_argument(...)`
    才是组内开关；只认赋值给具名变量的组，匿名内联组退化成「不在组里」（判定更严，不会造假绿）。
    """
    groups: dict[str, bool] = {}
    for n in ast.walk(tree):
        if (
            isinstance(n, ast.Assign)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Attribute)
            and n.value.func.attr == "add_mutually_exclusive_group"
        ):
            required = any(
                kw.arg == "required" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                for kw in n.value.keywords
            )
            for t in n.targets:
                if isinstance(t, ast.Name):
                    groups[t.id] = required
    members: dict[str, str] = {}
    for n in ast.walk(tree):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "add_argument"
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id in groups
        ):
            dest = _dest_of(n)
            if dest:
                members[dest] = n.func.value.id
    return groups, members


def flag_effect_map(stem: str, src: str | None = None) -> dict[str, dict]:
    """逐开关复算：dest、被读次数、所在互斥组、四态（活 / 代理 / 死 / 不可判）。"""
    if src is None:
        path = GATES_DIR / f"{stem}.py"
        if not path.is_file():
            return {}
        src = _read(path)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {}
    flags: list[tuple[str, str]] = []
    for n in ast.walk(tree):
        if not (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "add_argument"
            and any(
                isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.startswith("--") for a in n.args
            )
        ):
            continue
        flag, dest = _flag_of(n), _dest_of(n)
        if flag and dest:
            flags.append((flag, dest))
    if not flags:
        return {}
    ns = _namespace_names(tree)
    groups, members = _mutually_exclusive(tree)
    lines = src.splitlines()
    blocked = _decl_ranges(tree)
    body = "\n".join(ln for i, ln in enumerate(lines, 1) if not any(lo <= i <= hi for lo, hi in blocked))
    opaque_hits = _escape_reads(tree, ns)
    opaque = bool(opaque_hits)
    reads = {d: _read_count(body, ns, d) for _, d in flags}
    out: dict[str, dict] = {}
    for flag, dest in flags:
        group = members.get(dest)
        required = bool(group and groups.get(group))
        sibling_read = any(
            reads.get(other_dest, 0) > 0
            for other_dest, other_group in members.items()
            if other_group == group and other_dest != dest
        )
        if opaque:
            state = "不可判"
        elif reads[dest] > 0:
            state = "活"
        elif required and sibling_read:
            state = "代理"
        else:
            state = "死"
        out[flag] = {
            "dest": dest,
            "reads": reads[dest],
            "group": group,
            "required": required,
            "state": state,
            "opaque": opaque,
            "escapes": opaque_hits,
        }
    return out


def _read_count(body: str, ns: set[str], dest: str) -> int:
    total = 0
    for name in ns or {"args"}:
        total += len(re.findall(rf"\b{re.escape(name)}\.{re.escape(dest)}\b", body))
    return total


def me_group_count(disk: list[str], *, sources: Mapping[str, str] | None = None) -> int:
    n = 0
    for stem in disk:
        src = sources[stem] if sources is not None else _src_of(stem)
        if not src:
            continue
        try:
            groups, _ = _mutually_exclusive(ast.parse(src))
        except SyntaxError:
            continue
        n += sum(1 for required in groups.values() if required)
    return n


def _src_of(stem: str) -> str | None:
    path = GATES_DIR / f"{stem}.py"
    return _read(path) if path.is_file() else None


def denominator_problems(counts: Mapping[str, int]) -> list[str]:
    """四态必须互斥且完备。今天这个恒等式由循环结构保证，留着它防的是**下一轮**给分类加一个
    新态却忘了计数——那时「死开关 0」会变成漏计之后的数，而不是判出来的数。"""
    accounted = counts["live_flags"] + counts["proxy_flags"] + counts["dead_flags"] + counts["opaque_flags"]
    if accounted == counts["declared_flags"]:
        return []
    return [
        f"分母自校验失败：声明 {counts['declared_flags']} ≠ 活 {counts['live_flags']} + "
        f"代理 {counts['proxy_flags']} + 死 {counts['dead_flags']} + 不可判 {counts['opaque_flags']}（差 "
        f"{counts['declared_flags'] - accounted:+}）——四态分类必须互斥且完备，否则「死开关 0」不可信"
    ]


def judge_effect(
    disk: list[str] | None = None, *, sources: Mapping[str, str] | None = None
) -> tuple[list[str], list[str], list[str], dict[str, int]]:
    """判定主体。`sources` 给定时只读这些合成源码（回归锁用），否则读在盘门禁。"""
    disk = list(sources) if sources is not None else (disk if disk is not None else gate_scripts())
    problems: list[str] = []
    ok: list[str] = []
    notes: list[str] = []
    counts = {
        "disk_scripts": len(disk),
        "argparse_gates": 0,
        "declared_flags": 0,
        "live_flags": 0,
        "proxy_flags": 0,
        "dead_flags": 0,
        "opaque_gates": 0,
        "opaque_flags": 0,
        "me_groups": me_group_count(disk, sources=sources),
    }
    for stem in disk:
        src = sources[stem] if sources is not None else _src_of(stem)
        if src is None:
            problems.append(
                f"源码缺席：{stem} 进了在盘分母（disk_scripts）却读不到 `scripts/gates/{stem}.py`——"
                "受检面比判定面多一道门，而它对全部判据的贡献是 0 且不留痕；"
                "fail-closed 计红：要么把文件补回来，要么让它离开 glob 口径"
            )
            continue
        try:
            ast.parse(src)
        except SyntaxError as exc:
            problems.append(
                f"源码不可解析：{stem} 的 `ast.parse` 失败（第 {exc.lineno} 行：{exc.msg}）——"
                "本门把它和「没有 argparse」的门折叠成同一个读数（声明 0），"
                "于是「在盘门禁逐 (门禁, 开关) 复算」这句披露对它是假的；计红而不是静默跳过"
            )
            continue
        per = flag_effect_map(stem, src)
        if not per:
            continue
        counts["argparse_gates"] += 1
        counts["declared_flags"] += len(per)
        if any(v["opaque"] for v in per.values()):
            forms = sorted({e for v in per.values() for e in v["escapes"]})
            counts["opaque_gates"] += 1
            problems.append(
                f"不可判门禁：{stem} 整包读走 Namespace（{'、'.join(forms)}）——"
                "dest 级活性无法静态判定，须改成逐属性显式读取；"
                f"本轮该门的 {len(per)} 个开关全部计入「不可判」而不是「活」，不进判据面"
            )
        for flag, info in sorted(per.items()):
            state = info["state"]
            if state == "活":
                counts["live_flags"] += 1
                continue
            if state == "不可判":
                counts["opaque_flags"] += 1
                continue
            counts["proxy_flags" if state == "代理" else "dead_flags"] += 1
            if state == "代理":
                problems.append(
                    f"代理开关：{stem} {flag}（dest `{info['dest']}`）从不被读，它与兄弟开关同处 "
                    f"`required=True` 的互斥组，当下行为等价——但等价性由那个组担保、不由它自己担保。"
                    "去掉 `required=` 或往组里加第三个模式，这个开关立刻静默失效。"
                    f"要么让 {flag} 真去选分支，要么删掉它"
                )
            else:
                problems.append(
                    f"死开关：{stem} 声明 {flag}（dest `{info['dest']}`）但整个模块从不读它——"
                    f"命令行上传或不传都改变不了任何行为。要么让 `{info['dest']}` 参与调度，要么删掉这条 "
                    "`add_argument`（本门不设豁免表：装饰性开关不是正当终态）"
                )
    problems += denominator_problems(counts)
    if not problems:
        ok.append(
            f"[OK] 开关有效性：{counts['argparse_gates']} 道有 argparse 的门禁声明 "
            f"{counts['declared_flags']} 个 (门禁, 开关) 实例，死开关 {counts['dead_flags']}、"
            f"代理开关 {counts['proxy_flags']}（都须为 0），互斥必填组 {counts['me_groups']} 个"
        )
    notes.append(
        f"[SURFACE] 判定面：在盘门禁 {counts['disk_scripts']} 道逐 (门禁, 开关) 复算 dest 活性，"
        f"四态计数 活 {counts['live_flags']} / 代理 {counts['proxy_flags']} / 死 {counts['dead_flags']} / "
        f"不可判 {counts['opaque_flags']}，分母自校验 声明 {counts['declared_flags']} = 四态之和；"
        f"不可判门禁 {counts['opaque_gates']} 道（整包读走 Namespace ⇒ 显式计红，不静默放行）；"
        f"BASELINE 声明键 {len(BASELINE_KEYS)} 个（缺键即红）"
    )
    notes.append(
        "[SURFACE] 不判定面：本门**不执行任何门禁**，也不判「传了这个开关是否改变了退出码的方向」——"
        "dest 被读只是必要非充分（读了但两个分支同行为，本门看不到）；短选项 `-x`、位置参数、"
        "`add_parser` 子命令均不在分母里；`--flag=val` 的取值对不对由 CG 门的有效值对账判"
    )
    notes.append(
        "[SURFACE] 判据归属：CG 门判「有没有人传这个开关」（读者活性），本门判「这个开关在源码里接没接线」"
        "（dest 活性）——同一个 (门禁, 开关) 分母、两个不同的判定量，两条独立实现"
        "（本门不复用 CG 的 `flag_specs`，两边各自复算再对账）"
    )
    return problems, ok, notes, counts


def judge_registration(*, counts: dict[str, int], baseline: dict, register_text: str) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    ok: list[str] = []
    for label, self_key in ITEMS.items():
        measured = counts.get(self_key)
        path = BASELINE_KEYS[label]
        declared = _baseline_get(baseline, path)
        if declared is None:
            problems.append(f"BASELINE 键缺位：{path}（本门复算值 {measured}）——自产权威源缺位一律计红")
            continue
        if declared != measured:
            problems.append(f"BASELINE 漂移：{path} 登记 {declared}，本门复算 {measured}")
            continue
        if not _row_has(register_text, label, measured):
            problems.append(
                f"登记册 §1 未对账：〔当前口径〕里没有「{label} {measured}」这条——"
                f"BASELINE 与本门都算 {measured}，但登记面写着别的数（或根本没写），读者只会读到后者"
            )
            continue
        ok.append(f"[OK] {label} = {measured}（本门复算 == BASELINE `{path}` == §1 当前口径）")
    return problems, ok


def _baseline_get(baseline: dict, dotted: str) -> int | None:
    node = baseline
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, int) and not isinstance(node, bool) else None


def _row_has(register_text: str, label: str, value: int) -> bool:
    """只在 〔当前口径…〕 括号内文里配对：整行扫的话第一个键被「〔当前口径：」粘住，永远匹配不上。"""
    for line in register_text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        for bracket in _BRACKET_RE.finditer(line):
            for key, num in _PAIR_RE.findall(bracket.group("body")):
                if key == label and float(num) == float(value):
                    return True
    return False


def load_baseline(path: Path) -> tuple[dict | None, str | None]:
    if not path.is_file():
        return None, f"{_rel(path)} 不在盘"
    text = _read(path)
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or ":" not in raw:
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, _, value = raw.strip().partition(":")
        key = key.strip()
        value = value.split("#")[0].strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if not stack:
            continue
        parent = stack[-1][1]
        if value == "":
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            if re.fullmatch(r"-?\d+", value):
                parent[key] = int(value)
    return root, None


def self_wiring(*, make_text: str, ci_text: str, stem: str | None = None) -> list[str]:
    stem = stem or Path(__file__).stem
    script = f"scripts/gates/{stem}.py"
    in_make = script in make_text
    in_ci = script in ci_text
    if in_make and in_ci:
        return []
    missing = [name for name, present in (("Makefile", in_make), ("ci.yml", in_ci)) if not present]
    return [
        f"本门自身未接入：{'、'.join(missing)} 里没有 {script}——"
        "「新增门禁忘记接线」是 CA 轮那一族；接线是「开关有效性」这条判据能进 CI 的前提"
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="门禁开关有效性对账：声明的 dest 有没有被读（零 LLM）")
    parser.add_argument("--list", action="store_true", help="只打印逐 (门禁, 开关) 的 dest 与活性表，不判定")
    parser.add_argument("--quiet", action="store_true", help="不打印逐项 [OK]")
    args = parser.parse_args(argv)

    for required in (MAKEFILE, GATES_DIR, CI_YML, BASELINE, REGISTER):
        if not required.exists():
            print(f"[FAIL] 仓库级前提缺席：{_rel(required)}", file=sys.stderr)
            return 1

    disk = gate_scripts()
    make_text = _read(MAKEFILE)
    ci_text = _read(CI_YML)

    if args.list:
        for stem in disk:
            for flag, info in sorted(flag_effect_map(stem).items()):
                print(f"{stem}\t{flag}\t{info['dest']}\t{info['state']}\treads={info['reads']}")
        return 0

    problems, ok, notes, counts = judge_effect(disk)
    baseline, reason = load_baseline(BASELINE)
    if baseline is None:
        problems.append(f"BASELINE 不可解析：{reason}")
    else:
        reg_problems, reg_ok = judge_registration(counts=counts, baseline=baseline, register_text=_read(REGISTER))
        problems += reg_problems
        ok += reg_ok
    problems += self_wiring(make_text=make_text, ci_text=ci_text)

    for line in notes:
        print(line)
    if not args.quiet:
        for line in ok:
            print(line)
    if problems:
        print(f"\n[flag-effect] 阻断：{len(problems)} 项", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(
        f"\n[flag-effect] 通过：{counts['argparse_gates']} 道门禁声明 {counts['declared_flags']} 个开关实例，"
        f"死开关 {counts['dead_flags']}、代理开关 {counts['proxy_flags']}、不可判 {counts['opaque_gates']} 全为 0，"
        f"四态分母自校验成立"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
