#!/usr/bin/env python3
"""CG 轮变异验证：门禁调用口径对账的判定锚点 70 个 + 1 个中性对照。

纪律（与 BH→CF 轮同）：
- 先全绿且收集数一致，再逐锚点变异；
- 每个变异：读原字节 → 写变异 → `compile()` → 跑受影响面 → 收集数核对 →
  记录红数与首批红名 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（只在 docstring 加星号）必须 0 红；
- 「不报」类变异一律改成 `pass` / 静默跳过，而不是让判定崩掉——崩溃不是红，是另一种沉默。

锚点方向：每一处都是把本轮补上的判据退回改前口径——子串式 `continue-on-error`、键不看值、
缩进不设界、注释当正文、`--warn-only` 与 `set +e` 不算兜底层、多层/动态/矛盾不判、
归属不判（孤儿、只被代码调用）、`make` 目标当链、链不展开、行尾注释当依赖、
门禁互点名当调用者、argparse 默认值不复算、`store_true` 在场不记、只比开关名不比有效值、
幽灵开关不报、不对称不要求登记、`--f=v` 不拆值、下一 token 被吞、续行不合并、
判据档并入呈现档不记红、读者判据放松、分母自校验不判、手动档登记不算/失效不查、
登记表九种审计各退回沉默、登记表缺席当无豁免、交叉核对不等不报、自产复算键缺位当正常、
声明键缺席不红、§1 不收口、同名行后者赢、同名行只判第一行、重复行不点名、任何〔〕都算当前口径、
行缺席不报、无主键不查、仓库级前提不查、不可解析连 [SKIP] 都不打、`--list` 也判定、
`--quiet` 吞披露、报红路径不披露受检面、通过行不报数。

首轮 67 锚点跑出 12 个未杀活项，处置如下（无一遗漏）：
- 两处是**判据缺口**，本轮补了代码并加了锚点：`set +e` 只认同行写法（M67/M68/M34 覆盖区块级作用域
  与 `set -e` 回补），§1 同名行折叠成一行（M59/M69/M70 覆盖收成列表·重复点名·逐行判三件事）；
- 九处是**有判据、无锁**，各补一例：注释行当命令（a06）、登记无 `@现场`（e08 第九例）、
  `no-face` 陈旧不查（b06）、门禁互点名当调用者（b05）、`--f=v` 不拆值（c06）、
  `manual-only` 细节开关不在现场（e15）、任何〔〕都算当前口径（e17）、通过行不报数（f06）、
  未登记不对称放行（M28 锚点本身写坏了语法，红路径早已存在）；
- 一处**等价变异**，不列锚点：`_locked_flags` 里 `if flag in specs` 这层过滤——返回的集合两处消费
  都以 `specs` 为迭代轴（`[f for f in specs if f in locked]` 与 `for flag in specs`），
  多收的 token 进不了任何数、任何输出、任何红，删掉它行为逐字不变。留着是防御性的，
  但它不构成「判据已被锁住」的证据，故不入锚点。

第二轮 70 锚点跑出 1 个未杀活项：M59（`setdefault(...).append(...)` → `rows[label] = [...]`，即后者赢）。
它存活的原因是 e16 的两行标签**不同**，字典里本来就有两个键，折叠与否都判得到——补 e18 把两行标签做成
逐字相同、漂移放在前一行，M59 当场转红（单点复核红 1 例）。这正是「红数扇出 ≠ 判据数」的反面教材：
一条锁看起来覆盖了同名行折叠，其实一个字节也没碰到。

第三轮（收口跑）：**70 锚点全红 + 对照 0 红**、`未杀活的变异 = []`、`锚点自身失效 = []`、
`残留标记 = False`、collected 逐锚点恒 **66**、墙钟 **424s**（单进程逐锚点串行的口径，不与 xdist 全量跑互换）。
红数分布：36 锚点红 **1**（一锚点一判据）/ 11 红 **2** / 最高扇出 **33**（M04 把「步骤键必须缩进 8 格」
这条界放松后，合成树里本该算正文的 `continue-on-error` 字样成了键，凡是断言「这棵树是绿的」或断言计数的锁一起红）
——**红数是扇出，不是判据数**。

受影响面 = `tests/test_invocation_caliber_cg.py`（真实树锁在本轮登记前就是绿的，无需 deselect）。
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

GATE = "scripts/gates/check_invocation_caliber.py"
LOCK = "tests/test_invocation_caliber_cg.py"

COLLECTED_RE = re.compile(r"(\d+)(?:/\d+)? tests collected")
FAILED_RE = re.compile(r"^FAILED (\S+)", re.MULTILINE)

CONTROL = "N01-control-docstring"

# (锚点名, 文件, 原串, 变异串)
MUTANTS: list[tuple[str, str, str, str]] = [
    # ── 结构判据：阻断性三层（判定三 + 解析面二）
    (
        "M01-coe-counted-from-command-body",
        GATE,
        '        if self.continue_on_error:\n            layers.append("coe")',
        '        if self.continue_on_error or "continue-on-error: true" in " ".join(self.commands):'
        '  # mutation: 退回子串口径\n            layers.append("coe")',
    ),
    (
        "M02-coe-key-value-not-parsed",
        GATE,
        '                    step.continue_on_error = match.group(1).strip().lower() == "true"',
        "                    step.continue_on_error = True  # mutation: 键在场即算，不看值",
    ),
    (
        "M03-run-comments-count-as-commands",
        GATE,
        '        if stripped.startswith("#"):\n            continue',
        '        if stripped.startswith("#@"):\n            continue  # mutation: 注释行不再跳过',
    ),
    (
        "M04-step-key-indent-bound-loosened",
        GATE,
        '        if indent <= 8 and not stripped.startswith("- "):',
        '        if indent <= 10 and not stripped.startswith("- "):  # mutation: 缩进 10 也算步骤级键',
    ),
    (
        "M05-swallow-drops-set-plus-e",
        GATE,
        "                if _SWALLOW_RE.search(command) or err_off:",
        "                if _SWALLOW_RE.search(command):  # mutation: 不再认 set +e 生效区",
    ),
    (
        "M06-swallow-regex-narrowed-to-true",
        GATE,
        r'_SWALLOW_RE = re.compile(r"\|\|\s*(?:echo|true|exit[ \t]+0)(?![a-z0-9_-])|\|\|\\?\s*$")',
        r'_SWALLOW_RE = re.compile(r"\|\|\s*true(?![a-z0-9_-])")  # mutation: 只认 || true',
    ),
    (
        "M07-warn-only-not-a-layer",
        GATE,
        '        if self.warn_only():\n            layers.append("warn-only")',
        '        if False:  # mutation: --warn-only 不算一层\n            layers.append("warn-only")',
    ),
    (
        "M08-multi-layer-not-judged",
        GATE,
        "    for step in multi:",
        "    for step in []:  # mutation: 多层兜底不判",
    ),
    (
        "M09-dynamic-injection-not-judged",
        GATE,
        "    for step in dynamic:",
        "    for step in []:  # mutation: 动态注入不判",
    ),
    (
        "M10-injected-var-not-tracked",
        GATE,
        '                    if _FLAG_RE.search(step.assignments.get(var, "")):\n                        step.dynamic.append(var)',
        "                    if False:  # mutation: 变量里带开关也不算注入\n                        step.dynamic.append(var)",
    ),
    (
        "M11-strict-contradiction-not-judged",
        GATE,
        '        for step in gate_steps\n        if "--strict" in " ".join(step.commands) and step.non_blocking_layers()',
        '        for step in []\n        if "--strict" in " ".join(step.commands) and step.non_blocking_layers()  # mutation: 口径矛盾不报',
    ),
    (
        "M12-soft-and-dynamic-staleness-off",
        GATE,
        '        if key[0] in ("soft-layer", "dynamic-flag") and key not in used:',
        "        if False:  # mutation: 这两类登记失效不查",
    ),
    # ── 调用面归属（判定一 + 解析面一）
    (
        "M13-ownership-not-judged",
        GATE,
        "    for stem in disk:\n        faces = sorted(table.get(stem, {}))\n        hit = callers.get(stem, [])",
        "    for stem in []:  # mutation: 调用面归属不判\n        faces = sorted(table.get(stem, {}))\n        hit = callers.get(stem, [])",
    ),
    (
        "M14-programmatic-only-counted-as-wired",
        GATE,
        "        if not faces and hit:",
        "        if False:  # mutation: 有代码读者就算在链上",
    ),
    (
        "M15-no-face-staleness-off",
        GATE,
        '        if key[0] == "no-face" and key not in used:',
        "        if False:  # mutation: 无面类登记失效不查",
    ),
    (
        "M16-self-wiring-always-wired",
        GATE,
        "    if in_make and in_ci:\n        return []",
        "    if True:  # mutation: 本门永远算已接线\n        return []",
    ),
    (
        "M17-chain-not-expanded",
        GATE,
        "        chain.extend(recipes.get(dep, []))",
        "        chain.extend([])  # mutation: 链不展开依赖目标",
    ),
    (
        "M18-all-make-targets-counted-as-chain",
        GATE,
        '        if target in deps or target == "gates":\n            continue',
        "        if False:  # mutation: 所有 make 目标都算链上\n            continue",
    ),
    (
        "M19-gate-deps-include-trailing-comment",
        GATE,
        '    return line.split("#", 1)[0].split()[1:]',
        "    return line.split()[1:]  # mutation: 行尾注释被当成依赖",
    ),
    (
        "M20-callers-skip-experiments",
        GATE,
        '    for directory in CALLER_DIRS:\n        for path in sorted((root / directory).rglob("*.py")):',
        '    for directory in ("scripts",):  # mutation: experiments 不算调用者\n        for path in sorted((root / directory).rglob("*.py")):',
    ),
    (
        "M21-callers-include-gates-dir",
        GATE,
        '            if path.parent == root / "scripts" / "gates":\n                continue\n            text = _read(path)\n            if stem in text:',
        "            if False:  # mutation: 门禁互相点名也算调用者\n                continue\n            text = _read(path)\n            if stem in text:",
    ),
    # ── 有效值口径（判定二 + 解析面三）
    (
        "M22-argparse-default-not-recomputed",
        GATE,
        '        default = _flatten(kwargs.get("default"), consts)',
        "        default = None  # mutation: 不读 argparse 的 default",
    ),
    (
        "M23-store-true-presence-not-marked",
        GATE,
        '            if spec["kind"] == "flag":\n                out[flag] = "set"',
        '            if False:  # mutation: 在场不记 set\n                out[flag] = "set"',
    ),
    (
        "M24-effective-flags-skip-defaults",
        GATE,
        '        if spec["default"] is not None:\n            out[flag] = spec["default"]',
        '        if False:  # mutation: 缺省值不并入有效口径\n            out[flag] = spec["default"]',
    ),
    (
        "M25-face-diff-compares-names-only",
        GATE,
        "        va, vb = a.get(flag), b.get(flag)\n        if va == vb:\n            continue",
        '        va = vb = ""  # mutation: 只比开关名、不比有效值\n        if va == vb:\n            continue',
    ),
    (
        "M26-ghost-flags-not-reported",
        GATE,
        "    for face, stem, flag in ghost:",
        "    for face, stem, flag in []:  # mutation: 幽灵开关不报",
    ),
    (
        "M27-ghost-judged-without-argparse",
        GATE,
        "        specs = specs_cache.setdefault(stem, flag_specs(stem))\n        if not specs:\n            continue",
        "        specs = specs_cache.setdefault(stem, flag_specs(stem))\n        if False:  # mutation: 无 argparse 也判幽灵\n            continue",
    ),
    (
        "M28-unregistered-asymmetry-passed",
        GATE,
        "                else:\n                    problems.append(\n"
        '                        f"跨面开关：{stem} 在 {a} 与 {b} 的有效开关不等 {diff}——同一道门跑两种命题；"\n'
        '                        f"要么对齐，要么登记 {key} 并写理由（注释里的理由不会被复算）"\n'
        "                    )",
        "                else:\n                    pass  # mutation: 未登记的不对称也放行",
    ),
    (
        "M29-flag-diff-staleness-off",
        GATE,
        '        if key[0] == "flag-diff" and key not in used:',
        "        if False:  # mutation: 两侧已一致的登记不查",
    ),
    (
        "M30-equals-form-not-split",
        GATE,
        '            if "=" in tok:\n                name, _, value = tok.partition("=")',
        '            if False:  # mutation: --f=v 不拆值\n                name, _, value = tok.partition("=")',
    ),
    (
        "M31-next-flag-consumed-as-value",
        GATE,
        '                if nxt and not nxt.startswith("-") and nxt not in {"|", "||", "&&", ";", "\\\\", "|&"}:',
        "                if nxt:  # mutation: 下一个开关被当成本开关的值",
    ),
    (
        "M32-line-continuations-not-joined",
        GATE,
        '        if stripped.endswith("\\\\"):\n            buf += stripped[:-1].rstrip() + " "\n            continue',
        '        if False:  # mutation: 续行不合并\n            buf += stripped[:-1].rstrip() + " "\n            continue',
    ),
    # ── 开关活性 + 判据档（判定四）
    (
        "M33-caliber-family-merged-into-presentation",
        GATE,
        "            if family is None:\n                presentation_unread += 1\n                continue",
        "            if True:  # mutation: 判据档并进呈现档，不记红\n                presentation_unread += 1\n                continue",
    ),
    (
        "M34-set-e-sign-ignored",
        GATE,
        '                    err_off = flip.group(1) == "+"',
        "                    err_off = True  # mutation: 只认 set +e，`set -e` 不回补",
    ),
    (
        "M35-reader-need-not-name-gate",
        GATE,
        "        if stem not in text and not (core and core in name):\n            continue",
        "        if False:  # mutation: 文件里出现过 token 就算读者\n            continue",
    ),
    (
        "M36-denominator-self-check-off",
        GATE,
        "    if accounted != declared_total:",
        "    if False:  # mutation: 读者分类分母自校验不判",
    ),
    (
        "M37-manual-registration-not-a-reader",
        GATE,
        '            key = ("manual-only", stem, flag)\n            if key in allow:',
        '            key = ("manual-only", stem, flag)\n            if False:  # mutation: 手动档登记不算读者',
    ),
    (
        "M38-manual-only-staleness-off",
        GATE,
        '        if key[0] == "manual-only" and key not in used:',
        "        if False:  # mutation: 手动档登记失效不查",
    ),
    (
        "M39-reader-index-only-tests",
        GATE,
        '    files = sorted((root / "tests").rglob("*.py")) + [\n        p for d in CALLER_DIRS for p in sorted((root / d).rglob("*.py")) if p.parent != root / "scripts" / "gates"\n    ]',
        '    files = sorted((root / "tests").rglob("*.py"))  # mutation: 只有 tests 算读者',
    ),
    (
        "M40-caliber-families-narrowed",
        GATE,
        '        re.compile(r"^(?:--list|--allow-empty|--warn-only|--no-strict|--skip-[a-z0-9-]+)$"),',
        '        re.compile(r"^(?:--allow-empty|--no-strict)$"),  # mutation: 放松档不含 --list/--warn-only/--skip-*',
    ),
    # ── 登记表审计（八种红 + fail-closed）
    (
        "M41-reason-not-required",
        GATE,
        "        if not sep or not reason.strip():",
        "        if False:  # mutation: 无理由的豁免也接受",
    ),
    (
        "M42-entry-shape-not-checked",
        GATE,
        "        if len(fields) != 3:",
        "        if False:  # mutation: 三段式形状不查",
    ),
    (
        "M43-unknown-kind-accepted",
        GATE,
        "        if kind not in KINDS:",
        "        if False:  # mutation: 未知类别也放行",
    ),
    (
        "M44-duplicate-entry-allowed",
        GATE,
        "        if key in entries:",
        "        if False:  # mutation: 重复登记不查",
    ),
    (
        "M45-evidence-anchor-not-required",
        GATE,
        "        if not cited and kind in _EVIDENCE_REQUIRED_KINDS:",
        "        if False:  # mutation: 不要求 `@现场`",
    ),
    (
        "M46-deleted-subject-allowed",
        GATE,
        '        if core.replace("_", "").isalnum() and not (GATES_DIR / f"{core}.py").is_file():',
        "        if False:  # mutation: 主体已删的登记不查",
    ),
    (
        "M47-missing-scene-silently-dropped",
        GATE,
        '            if not cited_path.is_file():\n                problems.append(f"{_rel(path)}:{lineno}：理由指向 {_rel(cited_path)}——文件不存在，理由不可核对")\n                continue',
        "            if not cited_path.is_file():  # mutation: 现场不存在就悄悄不算\n                continue",
    ),
    (
        "M48-subject-containment-off",
        GATE,
        '            if kind != "manual-only" and core.replace("_", "").isalnum() and core not in sites[-1][1]:',
        "            if False:  # mutation: 现场不含主体不查",
    ),
    (
        "M49-flag-token-in-scene-off",
        GATE,
        "        if must and sites and not any(token in text for token in must for _, text in sites):",
        "        if False:  # mutation: 理由里的开关不在现场也不查",
    ),
    (
        "M50-allowlist-absent-fail-open",
        GATE,
        '        return entries, [f"{_rel(path)}：登记表缺席——不对称无处登记 ⇒ fail-closed 全计红"]',
        "        return entries, []  # mutation: 登记表缺席当作没有豁免",
    ),
    (
        "M51-manual-only-detail-not-compared",
        GATE,
        '        must = [detail] if kind == "manual-only" else sorted(set(_FLAG_RE.findall(reason)))',
        "        must = sorted(set(_FLAG_RE.findall(reason)))  # mutation: manual-only 不比细节开关",
    ),
    # ── 登记面（判定五）
    (
        "M52-cross-check-inequality-off",
        GATE,
        "        if got != mine:",
        "        if False:  # mutation: 交叉核对不等也不报",
    ),
    (
        "M53-self-assembled-absence-silent",
        GATE,
        "        if mine is None:",
        "        if False:  # mutation: 自产复算键缺位不红",
    ),
    (
        "M54-item-authority-absence-counted-zero",
        GATE,
        "        authority = counts.get(count_key)",
        "        authority = counts.get(count_key, 0)  # mutation: 缺键当 0，不点名",
    ),
    (
        "M55-baseline-declared-key-absent-not-red",
        GATE,
        "        mine = counts.get(ITEMS[label])\n        if got is None:",
        "        mine = counts.get(ITEMS[label])\n        if False:  # mutation: 本门声明键缺席不红",
    ),
    (
        "M56-register-row-absent-not-reported",
        GATE,
        '        problems.append(f"{_rel(REGISTER)} §1：未找到「调用口径」行——本门的复算值没有登记面，写了没人查")\n        return problems, ok, skips',
        "        return problems, ok, skips  # mutation: 行缺席不报",
    ),
    (
        "M57-unowned-bracket-key-off",
        GATE,
        "    unowned = sorted({k for k in declared if k not in ITEMS})",
        "    unowned = []  # mutation: 括号里的无主键不查",
    ),
    (
        "M58-section-one-not-cut",
        GATE,
        '    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))\n    return "\\n".join(lines[start:end])',
        '    return "\\n".join(lines[start:])  # mutation: §1 不在下一个 H2 收口',
    ),
    (
        "M59-register-rows-last-wins",
        GATE,
        '        rows.setdefault(label, []).append(match.group("body"))',
        '        rows[label] = [match.group("body")]  # mutation: 同名行后来者覆盖前者的清单',
    ),
    (
        "M60-bracket-needs-current-caliber",
        GATE,
        r'_BRACKET_RE = re.compile(r"〔当前口径[^：:]*[：:](?P<body>[^〕]*)〕")',
        r'_BRACKET_RE = re.compile(r"〔[^：:]*[：:](?P<body>[^〕]*)〕")  # mutation: 任何〔〕都算当前口径',
    ),
    # ── CLI 与披露
    (
        "M61-repo-premise-not-checked",
        GATE,
        "    for required in (MAKEFILE, WF_DIR, GATES_DIR, BASELINE, REGISTER):",
        "    for required in ():  # mutation: 仓库级前提不查",
    ),
    (
        "M62-unparsable-baseline-silent",
        GATE,
        '        else ([], [], [f"[SKIP] BASELINE 未解析：{baseline_reason}"])',
        "        else ([], [], [])  # mutation: 不可解析连 [SKIP] 都不打",
    ),
    (
        "M63-list-still-judges",
        GATE,
        "    if args.list:",
        "    if False:  # mutation: --list 也走判定",
    ),
    (
        "M64-quiet-hides-notes",
        GATE,
        "    for line in reg_skips + flag_notes + block_notes + live_notes:\n        print(line)",
        "    for line in [] if args.quiet else reg_skips + flag_notes + block_notes + live_notes:  # mutation: --quiet 吞掉受检面注记\n        print(line)",
    ),
    (
        "M65-red-path-drops-disclosure",
        GATE,
        "        for line in disclosure:\n            print(line, file=sys.stderr)",
        "        pass  # mutation: 报红路径不披露受检面",
    ),
    (
        "M66-pass-line-drops-numbers",
        GATE,
        "        f\"幽灵开关 {counts['ghost_flags']}、本门已接线\"",
        '        f"通过（数字不复算）"  # mutation: 通过行不报数',
    ),
    (
        "M67-set-e-state-not-advanced",
        GATE,
        '                flip = _SET_E_RE.search(command)\n                if flip is not None:\n                    err_off = flip.group(1) == "+"',
        "                pass  # mutation: 不推进区块内的 set 状态",
    ),
    (
        "M68-set-e-regex-never-matches",
        GATE,
        r'_SET_E_RE = re.compile(r"\bset\s+([+-])e\b")',
        r'_SET_E_RE = re.compile(r"\bset\s+([+-])ex\b")  # mutation: 正则放松到要求后缀，实际永不匹配',
    ),
    (
        "M69-duplicate-row-not-reported",
        GATE,
        "    if len(bodies) > 1:",
        "    if False:  # mutation: §1 同名行重复不点名",
    ),
    (
        "M70-only-first-row-compared",
        GATE,
        "    for body in dict.fromkeys(bodies):",
        "    for body in dict.fromkeys(bodies[:1]):  # mutation: 同名行只判第一行",
    ),
    (
        CONTROL,
        GATE,
        "退出码：`0` = 全部对账通过；`1` = 口径漂移 / 未登记差异 / 判据档无读者 / 幽灵开关 / 仓库级前提缺席 /",
        "退出码：**`0` = 全部对账通过；`1` = 口径漂移 / 未登记差异 / 判据档无读者 / 幽灵开关 / 仓库级前提缺席 /",
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
    cmd = [str(PY), "-m", "pytest", LOCK, "-q", "--basetemp=/tmp/pt_cg_mut", "-p", "no:cacheprovider"]
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
