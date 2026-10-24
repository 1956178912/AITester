#!/usr/bin/env python3
"""CH 轮变异验证：门禁开关有效性对账的判定锚点 75 个 + 1 个中性对照。

纪律（与 BH→CG 轮同）：
- 先全绿且收集数一致，再逐锚点变异；
- 每个变异：读原字节 → 写变异 → `compile()` → 跑受影响面 → 收集数核对 →
  记录红数与首批红名 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（只在 docstring 加星号）必须 0 红；
- 「不报」类变异一律改成 `pass` / 静默跳过，而不是让判定崩掉——崩溃不是红，是另一种沉默。

锚点方向：每一处都是把本轮补上的判据退回「开关在场即开关有效」的改前口径——dest 推导不按 argparse
自己的规则（连字符、显式 `dest=`、第一个 token）、声明行里的 help 当使用、命名空间名硬编码或放宽到
任何赋值目标、词尾不设界、互斥组不看 `required=`、匿名内联组当具名组、代理不要求兄弟真被读、
整包逃逸按子串命中或干脆不判、不可判并入活、代理并入死、四态计数漏一条、分母恒等式漏态、
BASELINE 缺键当 0、不等也放行、§1 整行扫 / 任何〔〕都算当前口径 / 表行以外也算 / 只比键不比值、
权威清单少一条、接线只点脚本名 / 只查一面 / 不进阻断面、仓库级前提不查、`--list` 也判定、
`--quiet` 吞掉受检面、报红不阻断、通过行与披露行不报数、在盘分母退回 `check_*` 前缀或文件名。

**已知不列锚点的等价区**（逐一核对过，删掉/放松都不改变任何数、任何输出、任何红）：
1. `_namespace_names` 里 `parse_known_args` 与 `parse_args` 并列——两者一旦命中，`_escape_reads`
   必定先把这道门判成不可判（`parse_known_args` 本身是逃逸形态），活性分支永远走不到；
2. `_mutually_exclusive` 成员循环里 `n.func.value.id in groups` 这层过滤——`required` 仍要求
   `groups.get(group)` 为真，组外名进 `members` 也只写进 `out[flag]["group"]` 这个无人消费的字段；
3. `_mutually_exclusive` 兄弟判据里的 `other_dest != dest`——被读的那个开关在更早的分支就判成活，
   永远轮不到把自己当兄弟；
4. `_read_count` 正则里 `re.escape(...)`——本仓 dest 全是标识符，转义与否逐字节同结果；
5. `judge_effect` 里 `problems += denominator_problems(counts)` 这个**调用点**——四态由 if/elif/else
   三分支恰好命中一次，恒等式在结构上不会失败，所以任何放松调用点的变异都造不出红；函数本体
   的四条求和与「恒过」各有锚点，这里缺的是**触发场景**而不是判据（D 组 docstring 同义）；
6. `flag_effect_map` 声明准入里的 `any(... startswith("--"))` 那层过滤（原 M06，首轮 0 红后删除）——
   放松成「任意字符串 token」后，`add_argument("-v")` / `add_argument("paths")` 能过准入，但下一步
   `_flag_of` 同样要求 `--` 前缀、`if flag and dest` 把它们全部丢弃 ⇒ `flags` 集合逐字不变，
   声明数、四态、红、披露一个都不动。这层过滤只是省一次函数调用，不是判据。
这条清单本身就是产出：它说明「哪些代码删了也没人发现」，而这类地方恰恰是下一轮最容易长出新 bug 的
地方——留着是防御性的，但它不构成「判据已被锁住」的证据。

首轮 76 项（75 锚点 + 对照）跑出 3 个存活项，处置如下（无一遗漏）：
- **M06**：等价变异，见上面第 6 条，删锚点不删代码；
- **M38**（`if src is None: continue`）：原锚点把「缺席就跳过」改成「缺席也继续」，而
  `flag_effect_map` 内部对 `src=None` 又读一次盘并返回 `{}`，于是**那个 `continue` 本身就是冗余防御**，
  怎么变异都不动数。真正的问题是判据缺口：进了在盘分母（`disk_scripts`）却读不到源码的门，
  对本门全部判据贡献 0 且不留痕，而披露句写的是「在盘 N 道逐 (门禁, 开关) 复算」——
  BH→BT 一族「读不懂就静默」在本门自己身上的形状。补 fail-closed（缺席计红 + 不可解析计红）、
  补两例锁（`test_absent_source_is_red_not_skipped` / `test_unparsable_source_is_red_not_folded`）、
  锚点改写成「删掉红行、保留跳过」，另为不可解析那一面新增 **M76**；
- **M68**（通过行抹掉数字）：判据在、锁没咬住。原因是当时的断言写成 `死开关 0、代理开关 0`，
  这个片段 `[OK]` 行与通过行**都有**，抹掉通过行的数以后断言落回 `[OK]` 行照样绿——
  CG 轮 ⑦「断言里出现关键词 ≠ 断言执行了那条分支」的同一条病灶，换个方向重演。
  改成逐行钉死：通过行按 `通过：{argparse_gates} 道门禁声明 {declared_flags} 个开关实例` 与
  `{dead}、{proxy}、{opaque_gates} 全为 0，` 两条整段断言，当场转红（红 1 例）。
顺带把三处「三态」措辞对齐成「四态」（`活/代理/死/不可判` 与恒等式的四项），pass 行文案随之改为
「四态分母自校验成立」——M68 的整段断言把这句也钉住了。

受影响面 = `tests/test_flag_effect_ch.py`（真实树锁在本轮登记前就是绿的，无需 deselect；
collected 逐锚点恒 **99**）。
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "bin" / "python"

GATE = "scripts/gates/check_flag_effect.py"
LOCK = "tests/test_flag_effect_ch.py"

COLLECTED_RE = re.compile(r"(\d+)(?:/\d+)? tests collected")
FAILED_RE = re.compile(r"^FAILED (\S+)", re.MULTILINE)

CONTROL = "N01-control-docstring"

# (锚点名, 文件, 原串, 变异串)
MUTANTS: list[tuple[str, str, str, str]] = [
    # ── dest 复算口径（口径约定 2）
    (
        "M01-dest-keeps-hyphen",
        GATE,
        '    dest = flag[2:].replace("-", "_")',
        "    dest = flag[2:]  # mutation: 连字符不换下划线",
    ),
    (
        "M02-explicit-dest-ignored",
        GATE,
        '        if kw.arg == "dest" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):\n            dest = kw.value.value',
        "        if False:  # mutation: 显式 dest= 不认\n            dest = kw.value.value",
    ),
    (
        "M03-dest-scans-first-token-only",
        GATE,
        "    flag = None\n    for a in call.args:",
        "    flag = None\n    for a in call.args[:1]:  # mutation: 只看第一个 token，短选项在前就整个漏掉",
    ),
    (
        "M04-flag-of-first-token-only",
        GATE,
        "def _flag_of(call: ast.Call) -> str | None:\n    for a in call.args:",
        "def _flag_of(call: ast.Call) -> str | None:\n    for a in call.args[:1]:  # mutation: 同上，第一个 token 当开关名",
    ),
    (
        "M05-denominator-scans-first-token-only",
        GATE,
        '            and any(\n                isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.startswith("--") for a in n.args\n            )',
        '            and any(\n                isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.startswith("--")\n                for a in n.args[:1]\n            )  # mutation: 改前口径——只看第一个位置 token',
    ),
    # （M06 曾在此：把 `any(...)` 过滤放松成「任意字符串 token」——首轮跑出 0 红，复核为**等价变异**，
    #  已删。放松后 `add_argument("-v")` / `add_argument("paths")` 能过这层准入，但下一步
    #  `flag, dest = _flag_of(n), _dest_of(n)` 里 `_flag_of` 同样要求 `--` 前缀，`if flag and dest`
    #  把它们全部丢弃 ⇒ flags 集合逐字不变 ⇒ 声明数、四态、红、披露一个都不动。
    #  这层 `any()` 是防御性的（省一次 `_flag_of` 调用），不构成判据，故不入锚点——
    #  与 CG 轮 `_locked_flags` 的 `if flag in specs` 同一处置：记进等价清单，不用它凑锚点数。）
    # ── 声明行不算使用
    (
        "M07-decl-ranges-never-match",
        GATE,
        '        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "add_argument"\n    ]',
        '        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "add_argument_x"  # mutation: 声明行区间恒空\n    ]',
    ),
    (
        "M08-body-keeps-declaration-lines",
        GATE,
        '    body = "\\n".join(ln for i, ln in enumerate(lines, 1) if not any(lo <= i <= hi for lo, hi in blocked))',
        '    body = "\\n".join(lines)  # mutation: 声明行也算正文——help 里的 args.x 被当成使用',
    ),
    # ── 命名空间名（只有 parse_args 的结果才算）
    (
        "M09-namespace-names-hardcoded",
        GATE,
        "                    out.add(t.id)\n    return out",
        '                    out.add(t.id)\n    return {"args"}  # mutation: 命名空间名硬编码成 args',
    ),
    (
        "M10-namespace-names-any-assign-target",
        GATE,
        '        if (\n            isinstance(n, ast.Assign)\n            and isinstance(n.value, ast.Call)\n            and isinstance(n.value.func, ast.Attribute)\n            and n.value.func.attr in ("parse_args", "parse_known_args")\n        ):\n            for t in n.targets:',
        "        if isinstance(n, ast.Assign):  # mutation: 任何赋值目标都算命名空间\n            for t in n.targets:",
    ),
    (
        "M11-no-fallback-to-args",
        GATE,
        '    for name in ns or {"args"}:',
        "    for name in ns:  # mutation: 复算不出命名空间名时不退回默认 args",
    ),
    # ── 读的计数
    (
        "M12-read-count-drops-trailing-boundary",
        GATE,
        '        total += len(re.findall(rf"\\b{re.escape(name)}\\.{re.escape(dest)}\\b", body))',
        '        total += len(re.findall(rf"\\b{re.escape(name)}\\.{re.escape(dest)}", body))  # mutation: 词尾不设界',
    ),
    # ── 互斥组与 required
    (
        "M13-me-count-credits-any-group",
        GATE,
        "        n += sum(1 for required in groups.values() if required)",
        "        n += len(groups)  # mutation: 组在场即必填",
    ),
    (
        "M14-group-required-always-true",
        GATE,
        "                    groups[t.id] = required",
        "                    groups[t.id] = True  # mutation: 组存在即视为必填",
    ),
    (
        "M15-inline-anonymous-group-credited",
        GATE,
        "    for n in ast.walk(tree):\n"
        "        if (\n"
        "            isinstance(n, ast.Assign)\n"
        "            and isinstance(n.value, ast.Call)\n"
        "            and isinstance(n.value.func, ast.Attribute)\n"
        '            and n.value.func.attr == "add_mutually_exclusive_group"\n'
        "        ):\n"
        "            required = any(\n"
        '                kw.arg == "required" and isinstance(kw.value, ast.Constant) and kw.value.value is True\n'
        "                for kw in n.value.keywords\n"
        "            )\n"
        "            for t in n.targets:\n"
        "                if isinstance(t, ast.Name):\n"
        "                    groups[t.id] = required",
        "    for n in ast.walk(tree):  # mutation: 内联匿名组也认成具名组（放松「只认赋值给具名变量」）\n"
        "        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'add_mutually_exclusive_group':\n"
        "            groups['mode'] = any(kw.arg == 'required' and getattr(kw.value, 'value', None) is True for kw in n.keywords)",
    ),
    # ── 四态判定
    (
        "M16-opaque-not-prioritized",
        GATE,
        '        if opaque:\n            state = "不可判"',
        '        if False:  # mutation: 整包读走不再优先归不可判\n            state = "不可判"',
    ),
    (
        "M17-any-declaration-is-live",
        GATE,
        "        elif reads[dest] > 0:",
        "        elif reads.get(dest, -1) >= 0:  # mutation: 声明过就算活",
    ),
    (
        "M18-proxy-without-read-sibling",
        GATE,
        '        elif required and sibling_read:\n            state = "代理"',
        '        elif required:  # mutation: 组里没人读也当代理\n            state = "代理"',
    ),
    (
        "M19-proxy-state-removed",
        GATE,
        '        elif required and sibling_read:\n            state = "代理"',
        '        elif False:  # mutation: 代理态取消，退回死开关\n            state = "代理"',
    ),
    # ── 整包逃逸：AST 判定，不按子串
    (
        "M20-escape-walk-disabled",
        GATE,
        "    hits: list[str] = []\n    for n in ast.walk(tree):",
        "    hits: list[str] = []\n    for n in []:  # mutation: 整包逃逸一律不判",
    ),
    (
        "M21-vars-hit-ignores-object",
        GATE,
        '            if isinstance(f, ast.Name) and f.id == "vars" and _uses_ns(n.args, ns):',
        '            if isinstance(f, ast.Name) and f.id == "vars":  # mutation: vars 的宾语是不是 Namespace 不看',
    ),
    (
        "M22-getattr-hit-ignores-object",
        GATE,
        '            elif isinstance(f, ast.Name) and f.id == "getattr" and _uses_ns(n.args[:1], ns):',
        '            elif isinstance(f, ast.Name) and f.id == "getattr":  # mutation: getattr 的宾语不看',
    ),
    (
        "M23-parse-known-args-not-escape",
        GATE,
        '            elif isinstance(f, ast.Attribute) and f.attr == "parse_known_args":',
        "            elif False:  # mutation: parse_known_args 不算逃逸",
    ),
    (
        "M24-splat-hit-ignores-object",
        GATE,
        '            hits.extend("**args 展开" for kw in n.keywords if kw.arg is None and _uses_ns([kw.value], ns))',
        '            hits.extend("**args 展开" for kw in n.keywords if kw.arg is None)  # mutation: 任何 ** 展开都算逃逸',
    ),
    (
        "M25-dict-hit-ignores-object",
        GATE,
        '        elif isinstance(n, ast.Attribute) and n.attr == "__dict__" and _uses_ns([n.value], ns):',
        '        elif isinstance(n, ast.Attribute) and n.attr == "__dict__":  # mutation: 任何 __dict__ 都算逃逸',
    ),
    (
        "M26-whole-args-passed-not-judged",
        GATE,
        "        elif isinstance(n, ast.Name) and n.id in ns and _is_call_arg(n, tree):",
        "        elif False:  # mutation: 整个 args 传进别的函数不判",
    ),
    (
        "M27-call-arg-check-always-true",
        GATE,
        "                if a is target:\n                    return True",
        "                if True:  # mutation: args 出现过就算传给了别人\n                    return True",
    ),
    (
        "M28-uses-ns-matches-any-name",
        GATE,
        "            if isinstance(sub, ast.Name) and sub.id in ns:",
        "            if isinstance(sub, ast.Name):  # mutation: 宾语里出现任何名字都算碰到 Namespace",
    ),
    # ── judge_effect 的计数与红面
    (
        "M29-opaque-gate-not-flagged",
        GATE,
        '        if any(v["opaque"] for v in per.values()):',
        "        if False:  # mutation: 不可判门禁不数也不报",
    ),
    (
        "M30-opaque-problem-not-emitted",
        GATE,
        """            problems.append(
                f"不可判门禁：{stem} 整包读走 Namespace（{'、'.join(forms)}）——"
                "dest 级活性无法静态判定，须改成逐属性显式读取；"
                f"本轮该门的 {len(per)} 个开关全部计入「不可判」而不是「活」，不进判据面"
            )""",
        "            pass  # mutation: 不可判门禁不报红，只留在计数里",
    ),
    (
        "M31-opaque-flags-counted-as-live",
        GATE,
        '            if state == "不可判":\n                counts["opaque_flags"] += 1\n                continue',
        '            if state == "不可判":\n                counts["live_flags"] += 1  # mutation: 不可判并入活\n                continue',
    ),
    (
        "M32-proxy-counted-as-dead",
        GATE,
        '            counts["proxy_flags" if state == "代理" else "dead_flags"] += 1',
        '            counts["dead_flags"] += 1  # mutation: 代理并入死开关',
    ),
    (
        "M33-proxy-problem-not-emitted",
        GATE,
        """            if state == "代理":
                problems.append(
                    f"代理开关：{stem} {flag}（dest `{info['dest']}`）从不被读，它与兄弟开关同处 "
                    f"`required=True` 的互斥组，当下行为等价——但等价性由那个组担保、不由它自己担保。"
                    "去掉 `required=` 或往组里加第三个模式，这个开关立刻静默失效。"
                    f"要么让 {flag} 真去选分支，要么删掉它"
                )
            else:""",
        "            if False:  # mutation: 代理开关不报红\n                pass\n            else:",
    ),
    (
        "M34-dead-problem-not-emitted",
        GATE,
        """            else:
                problems.append(
                    f"死开关：{stem} 声明 {flag}（dest `{info['dest']}`）但整个模块从不读它——"
                    f"命令行上传或不传都改变不了任何行为。要么让 `{info['dest']}` 参与调度，要么删掉这条 "
                    "`add_argument`（本门不设豁免表：装饰性开关不是正当终态）"
                )""",
        "            else:\n                pass  # mutation: 死开关不报红，只进计数",
    ),
    (
        "M35-argparse-gates-not-counted",
        GATE,
        '        counts["argparse_gates"] += 1\n        counts["declared_flags"] += len(per)',
        '        counts["declared_flags"] += len(per)  # mutation: 有 argparse 的门数不记',
    ),
    (
        "M36-declared-flags-not-counted",
        GATE,
        '        counts["argparse_gates"] += 1\n        counts["declared_flags"] += len(per)',
        '        counts["argparse_gates"] += 1  # mutation: 开关实例不进分母',
    ),
    (
        "M37-gate-without-argparse-entered",
        GATE,
        "        per = flag_effect_map(stem, src)\n        if not per:\n            continue",
        "        per = flag_effect_map(stem, src)\n        if False:  # mutation: 无 argparse 的门也进判据面\n            continue",
    ),
    (
        "M38-absent-source-not-red",
        GATE,
        "        if src is None:\n            problems.append(\n"
        '                f"源码缺席：{stem} 进了在盘分母（disk_scripts）却读不到 `scripts/gates/{stem}.py`——"\n'
        '                "受检面比判定面多一道门，而它对全部判据的贡献是 0 且不留痕；"\n'
        '                "fail-closed 计红：要么把文件补回来，要么让它离开 glob 口径"\n'
        "            )\n            continue",
        "        if src is None:\n            pass  # mutation: 缺席不报红，退回静默跳过\n            continue",
    ),
    # ── 分母自校验
    (
        "M39-self-check-always-pass",
        GATE,
        '    if accounted == counts["declared_flags"]:\n        return []',
        "    if True:  # mutation: 分母自校验恒过\n        return []",
    ),
    (
        "M40-self-check-sum-drops-opaque",
        GATE,
        '    accounted = counts["live_flags"] + counts["proxy_flags"] + counts["dead_flags"] + counts["opaque_flags"]',
        '    accounted = counts["live_flags"] + counts["proxy_flags"] + counts["dead_flags"]  # mutation: 不可判漏出恒等式',
    ),
    (
        "M41-self-check-sum-drops-proxy",
        GATE,
        '    accounted = counts["live_flags"] + counts["proxy_flags"] + counts["dead_flags"] + counts["opaque_flags"]',
        '    accounted = counts["live_flags"] + counts["dead_flags"] + counts["opaque_flags"]  # mutation: 代理漏出恒等式',
    ),
    # ── 登记面：BASELINE 与 §1 三面同权
    (
        "M42-baseline-key-absent-passed",
        GATE,
        "        if declared is None:",
        "        if False:  # mutation: BASELINE 缺键不红",
    ),
    (
        "M43-baseline-drift-passed",
        GATE,
        "        if declared != measured:",
        "        if False:  # mutation: 登记值与复算值不等也放行",
    ),
    (
        "M44-register-row-not-checked",
        GATE,
        "        if not _row_has(register_text, label, measured):",
        "        if False:  # mutation: §1 当前口径不对账",
    ),
    (
        "M45-measured-missing-defaults-zero",
        GATE,
        "        measured = counts.get(self_key)",
        "        measured = counts.get(self_key, 0)  # mutation: 本门复算值缺位当 0",
    ),
    (
        "M46-baseline-bool-counts-as-number",
        GATE,
        "    return node if isinstance(node, int) and not isinstance(node, bool) else None",
        "    return node if isinstance(node, int) else None  # mutation: true/false 也算数",
    ),
    (
        "M47-row-has-scans-whole-line",
        GATE,
        '        for bracket in _BRACKET_RE.finditer(line):\n            for key, num in _PAIR_RE.findall(bracket.group("body")):',
        "        for key, num in _PAIR_RE.findall(line):  # mutation: 整行扫，不单独取括号内文",
    ),
    (
        "M48-any-bracket-is-current-caliber",
        GATE,
        r'_BRACKET_RE = re.compile(r"〔当前口径[^：:]*[：:](?P<body>[^〕]*)〕")',
        r'_BRACKET_RE = re.compile(r"〔[^：:]*[：:](?P<body>[^〕]*)〕")  # mutation: 任何〔〕都算当前口径',
    ),
    (
        "M49-prose-outside-table-counts",
        GATE,
        '        if not line.lstrip().startswith("|"):\n            continue',
        "        if False:  # mutation: 表行以外的文字也算登记面\n            continue",
    ),
    (
        "M50-row-compares-key-not-value",
        GATE,
        "                if key == label and float(num) == float(value):",
        "                if key == label:  # mutation: 键对上就算，不比数",
    ),
    (
        "M51-baseline-keys-built-from-labels",
        GATE,
        'BASELINE_KEYS: dict[str, str] = {k: f"flag_effect.{v}" for k, v in ITEMS.items()}',
        'BASELINE_KEYS: dict[str, str] = {k: f"flag_effect.{k}" for k in ITEMS}  # mutation: 键名取中文标签',
    ),
    (
        "M52-items-drops-last-key",
        GATE,
        '    "不可判门禁": "opaque_gates",\n    "互斥必填组": "me_groups",\n}',
        '    "不可判门禁": "opaque_gates",\n}',
    ),
    (
        "M53-counts-drops-me-groups",
        GATE,
        '        "me_groups": me_group_count(disk, sources=sources),\n    }',
        "    }",
    ),
    # ── 自产接线
    (
        "M54-self-wiring-always-wired",
        GATE,
        "    if in_make and in_ci:\n        return []",
        "    if True:  # mutation: 本门永远算已接线\n        return []",
    ),
    (
        "M55-self-wiring-bare-filename",
        GATE,
        '    script = f"scripts/gates/{stem}.py"',
        '    script = f"{stem}.py"  # mutation: 只点名脚本文件也算接线',
    ),
    (
        "M56-self-wiring-ci-face-not-checked",
        GATE,
        "    in_ci = script in ci_text",
        "    in_ci = True  # mutation: CI 面不查",
    ),
    (
        "M57-self-wiring-names-one-face-only",
        GATE,
        '    missing = [name for name, present in (("Makefile", in_make), ("ci.yml", in_ci)) if not present]',
        '    missing = [name for name, present in (("Makefile", in_make),) if not present]  # mutation: 只查 Makefile 面',
    ),
    (
        "M58-self-wiring-not-in-blockers",
        GATE,
        "    problems += self_wiring(make_text=make_text, ci_text=ci_text)",
        "    pass  # mutation: 本门未接线不进阻断面",
    ),
    # ── CLI 与披露
    (
        "M59-repo-premises-not-checked",
        GATE,
        "    for required in (MAKEFILE, GATES_DIR, CI_YML, BASELINE, REGISTER):",
        "    for required in ():  # mutation: 仓库级前提不查",
    ),
    (
        "M60-baseline-unparsable-silent",
        GATE,
        '        problems.append(f"BASELINE 不可解析：{reason}")',
        "        pass  # mutation: BASELINE 不可解析不红",
    ),
    (
        "M61-list-still-judges",
        GATE,
        "    if args.list:",
        "    if False:  # mutation: --list 也走判定",
    ),
    (
        "M62-list-rows-drop-dest-and-state",
        GATE,
        """                print(f"{stem}\\t{flag}\\t{info['dest']}\\t{info['state']}\\treads={info['reads']}")""",
        '                print(f"{stem}\\t{flag}")  # mutation: --list 不报 dest 与活性',
    ),
    (
        "M63-quiet-hides-surface-notes",
        GATE,
        "    for line in notes:\n        print(line)",
        "    for line in [] if args.quiet else notes:  # mutation: --quiet 连受检面披露一起吞\n        print(line)",
    ),
    (
        "M64-quiet-cannot-hide-items",
        GATE,
        "    if not args.quiet:\n        for line in ok:\n            print(line)",
        "    if True:  # mutation: --quiet 吞不掉逐项 [OK]\n        for line in ok:\n            print(line)",
    ),
    (
        "M65-problems-do-not-block",
        GATE,
        '    if problems:\n        print(f"\\n[flag-effect] 阻断：{len(problems)} 项", file=sys.stderr)',
        '    if False:  # mutation: 报了红也不阻断\n        print(f"\\n[flag-effect] 阻断：{len(problems)} 项", file=sys.stderr)',
    ),
    (
        "M66-red-path-drops-disclosure",
        GATE,
        "    for line in notes:\n        print(line)",
        "    if not problems:  # mutation: 报红路径不披露受检面\n        for line in notes:\n            print(line)",
    ),
    (
        "M67-no-problems-drops-close-out-line",
        GATE,
        "    if not problems:\n        ok.append(",
        "    if False:  # mutation: 全绿时不打收口行\n        ok.append(",
    ),
    (
        "M68-pass-line-drops-numbers",
        GATE,
        """        f"死开关 {counts['dead_flags']}、代理开关 {counts['proxy_flags']}、不可判 {counts['opaque_gates']} 全为 0，\"""",
        '        "死开关、代理开关、不可判全为 0，"  # mutation: 通过行不复算数',
    ),
    (
        "M69-surface-note-drops-disk-count",
        GATE,
        """        f"[SURFACE] 判定面：在盘门禁 {counts['disk_scripts']} 道逐 (门禁, 开关) 复算 dest 活性，\"""",
        '        "[SURFACE] 判定面：在盘门禁逐 (门禁, 开关) 复算 dest 活性，"  # mutation: 披露行不报在盘数',
    ),
    (
        "M70-surface-note-drops-key-count",
        GATE,
        '        f"BASELINE 声明键 {len(BASELINE_KEYS)} 个（缺键即红）"',
        '        "BASELINE 声明键若干（缺键即红）"  # mutation: 不报声明键数',
    ),
    (
        "M71-unjudged-face-label-swapped",
        GATE,
        '        "[SURFACE] 不判定面：本门**不执行任何门禁**，也不判「传了这个开关是否改变了退出码的方向」——"',
        '        "[SURFACE] 判定面补注：本门**不执行任何门禁**，也不判「传了这个开关是否改变了退出码的方向」——"  # mutation: 不判定面标签换掉',
    ),
    (
        "M72-only-first-note-disclosed",
        GATE,
        "    return problems, ok, notes, counts",
        "    return problems, ok, notes[:1], counts  # mutation: 只披露判定面",
    ),
    # ── 在盘分母
    (
        "M73-disk-glob-restricted-to-check-prefix",
        GATE,
        '    return sorted(p.stem for p in GATES_DIR.glob("*.py"))',
        '    return sorted(p.stem for p in GATES_DIR.glob("check_*.py"))  # mutation: 在盘分母退回 check_* 前缀',
    ),
    (
        "M74-disk-keys-are-filenames",
        GATE,
        '    return sorted(p.stem for p in GATES_DIR.glob("*.py"))',
        '    return sorted(p.name for p in GATES_DIR.glob("*.py"))  # mutation: 键名用文件名而非 stem',
    ),
    (
        "M75-src-of-returns-empty",
        GATE,
        '    path = GATES_DIR / f"{stem}.py"\n    return _read(path) if path.is_file() else None',
        '    path = GATES_DIR / f"{stem}.py"\n    return ""  # mutation: 读盘退化成空串——所有门都判不出 argparse',
    ),
    (
        "M76-unparsable-source-not-red",
        GATE,
        "        except SyntaxError as exc:\n            problems.append(\n"
        '                f"源码不可解析：{stem} 的 `ast.parse` 失败（第 {exc.lineno} 行：{exc.msg}）——"\n'
        '                "本门把它和「没有 argparse」的门折叠成同一个读数（声明 0），"\n'
        '                "于是「在盘门禁逐 (门禁, 开关) 复算」这句披露对它是假的；计红而不是静默跳过"\n'
        "            )\n            continue",
        "        except SyntaxError:  # mutation: 不可解析折叠成「没有 argparse」，不报红\n            continue",
    ),
    (
        CONTROL,
        GATE,
        "退出码：`0` = 全部开关有效或已接线；`1` = 存在死开关 / 代理开关 / 不可判门禁 / 分母自校验失败 /",
        "退出码：**`0` = 全部开关有效或已接线；`1` = 存在死开关 / 代理开关 / 不可判门禁 / 分母自校验失败 /",
    ),
]


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def collect_count() -> int:
    cmd = [str(PY), "-m", "pytest", LOCK, "--collect-only", "-q", "-p", "no:cacheprovider"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300, env=_clean_env())
    match = COLLECTED_RE.search(proc.stdout + proc.stderr)
    if proc.returncode != 0 or not match:
        raise RuntimeError(f"collect failed rc={proc.returncode}: {(proc.stdout + proc.stderr)[-500:]}")
    return int(match.group(1))


def run_tests() -> tuple[int, int, str, list[str]]:
    cmd = [str(PY), "-m", "pytest", LOCK, "-q", "--basetemp=/tmp/pt_ch_mut", "-p", "no:cacheprovider"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900, env=_clean_env())
    output = proc.stdout + proc.stderr
    failed = FAILED_RE.findall(output)
    tail = "\n".join(output.splitlines()[-3:])
    return proc.returncode, len(failed), tail, failed


def precheck() -> bool:
    ok = True
    seen: set[str] = set()
    text = (ROOT / GATE).read_text(encoding="utf-8")
    for name, relpath, old, _new in MUTANTS:
        if name in seen:
            print(f"[{name}] DUPLICATE ANCHOR NAME")
            ok = False
        seen.add(name)
        assert relpath == GATE, f"{name}: 锚点只允许打在门禁源码上"
        counts = text.count(old)
        if counts != 1:
            print(f"[{name}] PRECHECK anchor count={counts} in {relpath}")
            ok = False
    print(f"[precheck] 锚点唯一性 {'全部通过' if ok else '有失败'}（{len(MUTANTS)} 个，含对照）")
    return ok


def main() -> int:
    print(f"[caliber] 受影响面 = {LOCK}（真实树锁登记前即绿，无需 deselect）")
    if not precheck():
        return 1
    baseline_collected = collect_count()
    rc, red, tail, _ = run_tests()
    print(f"[baseline] rc={rc} red={red} selected={baseline_collected}\n{tail}")
    if rc != 0 or red != 0:
        print("BASELINE NOT GREEN — abort")
        return 1

    selected = MUTANTS
    if len(sys.argv) > 1:
        wanted = set(sys.argv[1:])
        selected = [m for m in MUTANTS if any(m[0].startswith(w) for w in wanted)]
        print(f"[filter] running {len(selected)} of {len(MUTANTS)}")

    results = []
    for name, relpath, old, new in selected:
        path = ROOT / relpath
        original = path.read_bytes()
        sha_before = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")
        if text.count(old) != 1:
            print(f"[{name}] ANCHOR NOT UNIQUE ({text.count(old)}) — skip")
            results.append((name, "ANCHOR-ERROR", -1, []))
            continue
        mutated = text.replace(old, new, 1)
        try:
            compile(mutated, str(path), "exec")
        except SyntaxError as exc:
            print(f"[{name}] MUTATION SYNTAX ERROR: {exc}")
            results.append((name, "SYNTAX-ERROR", -1, []))
            continue
        path.write_text(mutated, encoding="utf-8")
        try:
            rc, red, tail, failed = run_tests()
            mutated_collected = collect_count()
        finally:
            path.write_bytes(original)
            restored = path.read_bytes()
            assert hashlib.sha256(restored).hexdigest() == sha_before, f"{name}: restore mismatch"
        if mutated_collected != baseline_collected:
            print(f"[{name}] COLLECTED DRIFT {baseline_collected} -> {mutated_collected}")
            results.append((name, "COLLECTED-DRIFT", red, failed))
            continue
        verdict = "FAILED" if rc != 0 else "SURVIVED"
        killers = [f.rsplit("::", 1)[-1] for f in failed[:3]]
        print(f"[{name}] rc={rc} red={red} selected={mutated_collected} {verdict} 红名={killers}")
        results.append((name, verdict, red, failed))

    print("\n=== SUMMARY ===")
    for name, verdict, red, _failed in results:
        print(f"{verdict:14s} red={red:<3d} {name}")
    survivors = [n for n, v, _r, _f in results if v != "FAILED" and n != CONTROL]
    broken = [n for n, v, _r, _f in results if v in ("SYNTAX-ERROR", "ANCHOR-ERROR", "COLLECTED-DRIFT")]
    wrong_control = [n for n, v, _r, _f in results if n == CONTROL and v != "SURVIVED"]
    residue = "# mutation:" in (ROOT / GATE).read_text(encoding="utf-8")
    print(f"\n未杀活的变异 = {survivors}")
    print(f"锚点自身失效 = {broken}；对照误杀 = {wrong_control}；残留标记 = {residue}")
    return 0 if not survivors and not broken and not wrong_control and not residue else 2


if __name__ == "__main__":
    sys.exit(main())
