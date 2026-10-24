"""CH 轮：门禁开关有效性对账 `scripts/gates/check_flag_effect.py` 的回归锁。

纪律：**零 LLM、$0**；除标记「真实树」的例外，全部判定跑在合成源码字符串上，不写真实文件。

为什么这些锁必须存在（2026-10-24 只读复算）：

- 在盘 31 道门禁、24 道有 argparse、声明 **71** 个 (门禁, 开关) 实例，其中 `dest` 在整个模块里
  从不被读的有 **2** 个：`check_docs_history_drift --warn-only`（调度只读 `args.strict`）与
  `checksum_results --verify`（调度只读 `args.write`）；
- 这两个**都是判据档**，且**都被 ci.yml 真实传入**——CG 判定四把「调用面出现该 token」算作读者，
  于是「判据档无读者 0」是真绿但误导：token 有读者，开关没有效果路径；
- 按子串搜「整包读走 Namespace」的写法会把**只在 docstring 里提到**这些写法的门禁误判成不可判
  （本门第一版就是这样，给 state-contract 那道门凭空造了一条红、也给自己造了一条）——
  这正是 CG 判定一「按结构不按子串」的同一条病灶，C 组锁专门咬住它；
- `checksum_results` 的两个模式开关同在 `required=True` 的互斥组里，今天按 `--write` 调度与按
  `--verify` 调度**等价**，所以这不是「CI 现在跑错了」；等价性由那个组担保，一旦有人摘掉
  `required=` 或往组里加第三个模式，`--verify` 就和新模式一起静默落进 `else` 分支。

本文件自身也是一个读者：它点名 `check_flag_effect` 并传 `--list` / `--quiet`（本门自己的两条声明），
还点名 `check_docs_history_drift` 与 `checksum_results`——后者使登记表里
`manual-only check_docs_history_drift --strict` 那一条**失效**（它现在有代码锁了），本轮按 CG 门的
「条目已失效计红」规则把它从 `docs/invocation_caliber_allowlist.txt` 删除。真实树的锁因此只断言
**本文件移动不了**的数（四态恒等式与死/代理为 0），把随文本变化的 `live_flags` 留给分母而不是硬编码。

分组（`--collect-only` 实测 99 例）：A dest 复算规则 11 例 / B 四态判定 24 例 / C 反子串与结构口径
7 例 / D 分母与权威清单 11 例 / E 登记面对账 13 例 / F 接线与 CLI 21 例 / R 真实树与两处写侧修复
12 例。上面 31/24/71 是**改前**读数；本门自己也在盘上（`add_argument` 两条），写侧修复后又多接一条
dest——改后读数以 BASELINE 的 `flag_effect.*` 为准，本文件不硬编码它。

D 组那两例（缺席 / 不可解析）不是本轮开头就写好的：首轮变异跑里 M38 存活，才暴露「进了在盘分母
却读不到源码的门贡献 0 且不留痕」是本门自己没折叠的那一面；M68 存活则暴露一条断言把 `[OK]` 行与
通过行共有的片段当成了通过行的证据。两条规矩：**判据的受检面必须等于它宣称的受检面**、
**断言必须钉在自己的那一行上**。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CH_SCRIPT = PROJECT_ROOT / "scripts" / "gates" / "check_flag_effect.py"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ch = _load("check_flag_effect_under_test", _CH_SCRIPT)


# ══ 合成门禁源码 ═══════════════════════════════════════════════════════
def _src(*lines: str) -> str:
    return "\n".join(lines)


HEADER = _src(
    "import argparse",
    "",
    "",
    "def main(argv=None):",
    "    parser = argparse.ArgumentParser()",
)
TAIL = _src("    args = parser.parse_args(argv)", "    return 0 if args.live else 1")

LIVE = _src(HEADER, '    parser.add_argument("--live", action="store_true")', TAIL)
DEAD = _src(
    HEADER,
    '    parser.add_argument("--live", action="store_true")',
    '    parser.add_argument("--ghost", action="store_true")',
    TAIL,
)
PROXY = _src(
    "import argparse",
    "",
    "",
    "def main(argv=None):",
    "    parser = argparse.ArgumentParser()",
    "    mode = parser.add_mutually_exclusive_group(required=True)",
    '    mode.add_argument("--write", action="store_true")',
    '    mode.add_argument("--check", action="store_true")',
    "    args = parser.parse_args(argv)",
    "    return 1 if args.write else 0",
)
# 同一个组但 `required` 缺省为 False：没人保证恰有一个为真，未读的那个就不是「等价代理」而是死开关。
PROXY_NOT_REQUIRED = PROXY.replace("required=True", "")
ANON_GROUP = _src(
    "import argparse",
    "",
    "",
    "def main(argv=None):",
    "    parser = argparse.ArgumentParser()",
    '    parser.add_mutually_exclusive_group(required=True).add_argument("--write", action="store_true")',
    '    parser.add_argument("--check", action="store_true")',
    "    args = parser.parse_args(argv)",
    "    return 1 if args.write else 0",
)
# 内联匿名组没有具名变量：`--write` 拿不到组名，`me_groups` 也不认它——「认不出代理关系」这件事
# 必须是显式的，不能悄悄算成已判。
PROXY_NO_SIBLING = _src(
    "import argparse",
    "",
    "",
    "def main(argv=None):",
    "    parser = argparse.ArgumentParser()",
    "    mode = parser.add_mutually_exclusive_group(required=True)",
    '    mode.add_argument("--write", action="store_true")',
    '    mode.add_argument("--check", action="store_true")',
    "    args = parser.parse_args(argv)",
    "    return 0",
)
# `parse_known_args()` 把命令行拆成「已知 + 未知」两包，未知串还能被再消费——dest 级活性不足以
# 回答「这个开关改变了什么」，按 fail-closed 归入不可判。
PARSE_KNOWN = _src(
    HEADER,
    '    parser.add_argument("--live", action="store_true")',
    "    ns2 = parser.parse_known_args(argv)[0]",
    "    return 0 if ns2.live else 1",
)
# 全是「整包读走」的字面形状，但宾语都不是本门 Namespace：按子串搜会一律命中（本门第一版的翻车点）。
NOT_ESCAPE = _src(
    HEADER,
    '    parser.add_argument("--live", action="store_true")',
    "    args = parser.parse_args(argv)",
    "    config = dict(live=True)",
    "    cfg = _Cfg()",
    "    return len(vars(config)) + len(getattr(cfg, 'live', '')) + len(cfg.__dict__) + _merge(**config) + int(args.live)",
    "",
    "",
    "def _merge(**kw):",
    "    return len(kw)",
)
OPAQUE_VARS = _src(
    HEADER,
    '    parser.add_argument("--live", action="store_true")',
    "    args = parser.parse_args(argv)",
    "    return len(vars(args))",
)
OPAQUE_GETATTR = _src(
    HEADER,
    '    parser.add_argument("--live", action="store_true")',
    "    args = parser.parse_args(argv)",
    '    return getattr(args, "live")',
)
OPAQUE_SPLAT = _src(
    HEADER,
    '    parser.add_argument("--live", action="store_true")',
    "    args = parser.parse_args(argv)",
    "    return _inner(**args.__dict__)",
    "",
    "",
    "def _inner(**kw):",
    "    return len(kw)",
)
OPAQUE_DICT = _src(
    HEADER,
    '    parser.add_argument("--live", action="store_true")',
    "    args = parser.parse_args(argv)",
    "    return 'live' in args.__dict__",
)
OPAQUE_PASSED = _src(
    HEADER,
    '    parser.add_argument("--live", action="store_true")',
    "    args = parser.parse_args(argv)",
    "    return _pick(args)",
    "",
    "",
    "def _pick(ns):",
    "    return ns.live",
)
# 只在 docstring 里提到这些写法——按子串搜会误判成不可判（本门第一版的真实翻车点）。
MENTIONS_ONLY = _src(
    '"""本模块不用 vars(args) 也不 getattr(args, ...)，全部逐属性读取。"""',
    "",
    "import argparse",
    "",
    "",
    "def main(argv=None):",
    "    parser = argparse.ArgumentParser()",
    '    parser.add_argument("--live", action="store_true")',
    "    args = parser.parse_args(argv)",
    "    return 0 if args.live else 1",
)


def _state(src: str, flag: str, stem: str = "check_synth") -> str:
    return ch.flag_effect_map(stem, src)[flag]["state"]


# ══ A 组：dest 复算按 argparse 自己的规则 ══════════════════════════════
class TestDestCaliber:
    def test_dashes_become_underscores(self):
        per = ch.flag_effect_map(
            "check_synth",
            _src(
                HEADER,
                '    parser.add_argument("--foo-bar", action="store_true")',
                TAIL.replace("args.live", "args.foo_bar"),
            ),
        )
        assert per["--foo-bar"]["dest"] == "foo_bar"
        assert per["--foo-bar"]["state"] == "活"

    def test_explicit_dest_overrides(self):
        src = _src(
            HEADER,
            '    parser.add_argument("--run-id", dest="run", action="store_true")',
            "    args = parser.parse_args(argv)",
            "    return 0 if args.run else 1",
        )
        per = ch.flag_effect_map("check_synth", src)
        assert per["--run-id"]["dest"] == "run"
        assert per["--run-id"]["state"] == "活"

    def test_unread_explicit_dest_is_dead(self):
        src = _src(
            HEADER,
            '    parser.add_argument("--run-id", dest="run", action="store_true")',
            "    args = parser.parse_args(argv)",
            "    return 0 if args.other else 1",
        )
        assert _state(src, "--run-id") == "死"

    def test_short_option_not_in_denominator(self):
        src = _src(
            HEADER,
            '    parser.add_argument("-v", "--verbose", action="store_true")',
            "    args = parser.parse_args(argv)",
            "    return 0 if args.verbose else 1",
        )
        assert set(ch.flag_effect_map("check_synth", src)) == {"--verbose"}

    def test_positional_not_in_denominator(self):
        src = _src(
            HEADER,
            '    parser.add_argument("paths", nargs="*")',
            '    parser.add_argument("--live", action="store_true")',
            TAIL,
        )
        assert set(ch.flag_effect_map("check_synth", src)) == {"--live"}

    def test_non_argparse_module_returns_empty(self):
        assert ch.flag_effect_map("check_synth", "def main():\n    return 0\n") == {}

    def test_syntax_error_degrades_empty_not_crash(self):
        assert ch.flag_effect_map("check_synth", "def main(:\n    ???") == {}

    def test_store_false_default_is_read(self):
        src = _src(
            HEADER,
            '    parser.add_argument("--no-color", dest="color", action="store_false")',
            "    args = parser.parse_args(argv)",
            "    return 0 if args.color else 1",
        )
        assert _state(src, "--no-color") == "活"

    def test_namespace_bound_to_attribute_falls_back_to_args(self):
        # `self.args = self.parser.parse_args(argv)` 的赋值目标不是 Name，复算不出命名空间名；
        # 此时退回默认名 args，否则「真读到了但没认出来」会造假红。
        src = _src(
            "import argparse",
            "",
            "",
            "class _Holder:",
            "    def run(self, argv):",
            '        parser.add_argument("--live", action="store_true")',
            "        self.args = self.parser.parse_args(argv)",
            "        return 0 if self.args.live else 1",
        )
        per = ch.flag_effect_map("check_synth", src)
        assert per["--live"]["reads"] == 1
        assert per["--live"]["state"] == "活"

    def test_attribute_target_under_another_name_is_not_a_read(self):
        # 退回的只有默认名 args：绑定成别的属性名时不该被兜住——读不到就是读不到。
        src = _src(
            "import argparse",
            "",
            "",
            "class _Holder:",
            "    def run(self, argv):",
            '        parser.add_argument("--live", action="store_true")',
            "        self.opts = self.parser.parse_args(argv)",
            "        return 0 if self.opts.live else 1",
        )
        per = ch.flag_effect_map("check_synth", src)
        assert per["--live"]["reads"] == 0
        assert per["--live"]["state"] == "死"

    def test_positional_only_gate_returns_empty(self):
        src = _src(
            HEADER,
            '    parser.add_argument("paths", nargs="*")',
            "    args = parser.parse_args(argv)",
            "    return len(args.paths)",
        )
        assert ch.flag_effect_map("check_synth", src) == {}


# ══ B 组：四态判定 ═════════════════════════════════════════════════════
class TestFourStates:
    def test_read_dest_is_live(self):
        assert _state(LIVE, "--live") == "活"

    def test_unread_dest_is_dead(self):
        assert _state(DEAD, "--ghost") == "死"

    def test_dead_still_counts_declared(self):
        per = ch.flag_effect_map("check_synth", DEAD)
        assert len(per) == 2
        assert {v["state"] for v in per.values()} == {"活", "死"}

    def test_dead_message_names_dest(self):
        problems, *_ = ch.judge_effect(sources={"check_synth": DEAD})
        assert any("死开关" in p and "--ghost" in p and "ghost" in p for p in problems)

    def test_required_group_sibling_read_is_proxy(self):
        assert _state(PROXY, "--check") == "代理"

    def test_proxy_message_says_the_group_guarantees_it(self):
        problems, *_ = ch.judge_effect(sources={"check_synth": PROXY})
        assert any("代理开关" in p and "互斥组" in p for p in problems)

    def test_group_member_that_is_read_is_live(self):
        assert _state(PROXY, "--write") == "活"

    def test_group_without_required_is_dead_not_proxy(self):
        assert _state(PROXY_NOT_REQUIRED, "--check") == "死"

    def test_anonymous_group_is_not_a_proxy(self):
        # 内联 `parser.add_mutually_exclusive_group(...).add_argument(...)` 没有具名变量，
        # 退回更严的判定：不可证明代理关系时按死开关算，宁可多红不可假绿。
        per = ch.flag_effect_map("check_synth", ANON_GROUP)
        assert per["--check"]["state"] == "死"
        # 这条退回必须是**显式**的：`--write` 拿不到组名、匿名组也不进 me_groups，
        # 否则「认不出代理关系」和「认出了但没有代理」在数字上长得一样。
        assert per["--write"]["group"] is None
        assert per["--write"]["state"] == "活"
        assert ch.judge_effect(sources={"check_a": ANON_GROUP})[3]["me_groups"] == 0

    def test_group_needs_a_read_sibling(self):
        # 代理的成立条件有两个：组是必填的 + 组里另有兄弟真被读。两个都没读时谁也不代理谁。
        per = ch.flag_effect_map("check_synth", PROXY_NO_SIBLING)
        assert {v["state"] for v in per.values()} == {"死"}

    def test_proxy_counts_into_proxy_flags_not_dead(self):
        _, _, _, counts = ch.judge_effect(sources={"check_synth": PROXY})
        assert counts["proxy_flags"] == 1
        assert counts["dead_flags"] == 0

    def test_opaque_gate_counts_its_declared_flags(self):
        # 不可判门禁的开关全部进「不可判」而不是「活」，否则分母自校验会被假绿糊过去。
        _, _, _, counts = ch.judge_effect(sources={"check_synth": OPAQUE_VARS})
        assert counts["declared_flags"] == 1
        assert counts["opaque_gates"] == 1

    def test_parse_known_args_is_opaque(self):
        problems, _, _, counts = ch.judge_effect(sources={"check_synth": PARSE_KNOWN})
        assert counts["opaque_gates"] == 1
        assert counts["opaque_flags"] == 1
        assert any("parse_known_args()" in p for p in problems)

    def test_non_namespace_bulk_reads_are_not_escapes(self):
        # vars/getattr/__dict__/** 的宾语不是本门 Namespace 时一律不算逃逸——按子串搜正是
        # 在这里给凭空一道门造了红（本门第一版的真实翻车点）。
        problems, _, _, counts = ch.judge_effect(sources={"check_synth": NOT_ESCAPE})
        assert counts["opaque_gates"] == 0
        assert counts["live_flags"] == 1
        assert problems == []

    @pytest.mark.parametrize(
        ("src", "form"),
        [
            (OPAQUE_VARS, "vars(args)"),
            (OPAQUE_GETATTR, "getattr(args, …)"),
            (OPAQUE_SPLAT, "**args 展开"),
            (OPAQUE_DICT, "args.__dict__"),
            (OPAQUE_PASSED, "整个 args 传进别的函数"),
        ],
    )
    def test_namespace_escape_makes_gate_opaque(self, src, form):
        problems, _, _, counts = ch.judge_effect(sources={"check_synth": src})
        assert counts["opaque_gates"] == 1
        assert any("不可判门禁" in p and form in p for p in problems)

    @pytest.mark.parametrize("src", [OPAQUE_VARS, OPAQUE_GETATTR, OPAQUE_SPLAT, OPAQUE_DICT, OPAQUE_PASSED])
    def test_opaque_flags_do_not_count_as_live(self, src):
        # 假绿方向必须堵死：整包读走 Namespace 时，不能把「读不到」说成「活着」。
        _, _, _, counts = ch.judge_effect(sources={"check_synth": src})
        assert counts["live_flags"] == 0
        assert counts["opaque_flags"] == 1


# ══ C 组：按结构不按子串 ═══════════════════════════════════════════════
class TestStructuralNotSubstring:
    def test_docstring_mention_is_not_an_escape(self):
        _, _, _, counts = ch.judge_effect(sources={"check_synth": MENTIONS_ONLY})
        assert counts["opaque_gates"] == 0
        assert counts["live_flags"] == 1

    def test_help_text_args_x_is_not_a_read(self):
        src = _src(
            "import argparse",
            "",
            "",
            "def main(argv=None):",
            "    parser = argparse.ArgumentParser()",
            '    parser.add_argument("--ghost", action="store_true", help="等价于写 args.ghost")',
            "    args = parser.parse_args(argv)",
            "    return 0 if args.live else 1",
            "",
            "",
            "def _unused(args):  # 这里 args.live 不是本门命名空间",
            "    return 0",
        )
        per = ch.flag_effect_map("check_synth", src)
        assert per["--ghost"]["reads"] == 0

    def test_other_namespace_name_is_read(self):
        src = _src(
            "import argparse",
            "",
            "",
            "def main(argv=None):",
            "    parser = argparse.ArgumentParser()",
            '    parser.add_argument("--opts", action="store_true")',
            "    ns = parser.parse_args(argv)",
            "    return 0 if ns.opts else 1",
        )
        assert _state(src, "--opts") == "活"

    def test_attribute_of_other_object_is_not_a_read(self):
        src = _src(
            HEADER,
            '    parser.add_argument("--live", action="store_true")',
            "    args = parser.parse_args(argv)",
            "    cfg = _Cfg()",
            "    return 0 if cfg.live else 1",
        )
        assert ch.flag_effect_map("check_synth", src)["--live"]["reads"] == 0

    def test_same_flag_name_different_gate_wiring(self):
        # 改前实测 ③：同一个开关名在一道门里接线、在另一道门里不接——判 (门禁, 开关) 组合，
        # 不能按名字给结论。这里用中性旗名，免得本文件的文本意外成为 CG 登记条目的"读者"。
        pair = _src(
            "import argparse",
            "",
            "",
            "def main(argv=None):",
            "    parser = argparse.ArgumentParser()",
            "    mode = parser.add_mutually_exclusive_group(required=True)",
            '    mode.add_argument("--alpha", action="store_true")',
            '    mode.add_argument("--beta", action="store_true")',
            "    args = parser.parse_args(argv)",
            "    return 1 if args.alpha else 0",
        )
        assert _state(pair, "--beta", stem="check_gate_one") == "代理"
        assert _state(pair, "--alpha", stem="check_gate_two") == "活"

    def test_prefix_flag_not_matched_as_other(self):
        src = _src(
            HEADER,
            '    parser.add_argument("--strict", action="store_true")',
            '    parser.add_argument("--strict-bytes", action="store_true")',
            "    args = parser.parse_args(argv)",
            "    return 0 if args.strict_bytes else 1",
        )
        per = ch.flag_effect_map("check_synth", src)
        assert per["--strict"]["state"] == "死"
        assert per["--strict-bytes"]["state"] == "活"

    def test_no_flags_no_problems(self):
        problems, _, _, counts = ch.judge_effect(sources={"check_plain": "def main():\n    return 0\n"})
        assert problems == []
        assert counts["declared_flags"] == 0


# ══ D 组：分母自校验 ═══════════════════════════════════════════════════
class TestDenominator:
    def _counts(self, sources):
        return ch.judge_effect(sources=sources)[3]

    def test_four_states_are_exhaustive(self):
        counts = self._counts({"check_a": DEAD, "check_b": PROXY, "check_c": OPAQUE_VARS, "check_d": LIVE})
        assert counts["declared_flags"] == 6
        assert (
            counts["live_flags"] + counts["proxy_flags"] + counts["dead_flags"] + counts["opaque_flags"]
            == counts["declared_flags"]
        )

    def test_self_check_holds_on_clean_source(self):
        problems, *_ = ch.judge_effect(sources={"check_a": LIVE})
        assert not any("分母自校验" in p for p in problems)

    def test_self_check_red_on_uncounted_state(self):
        # 枚举漏判不会被这条恒等式抓到（少一个开关，声明也跟着少）；它抓的是「加了一个新态却
        # 没进任何计数」——那正是下一轮最容易犯的形状，所以直接按漏计的 counts 造红。
        problems = ch.denominator_problems(
            {"declared_flags": 3, "live_flags": 1, "proxy_flags": 1, "dead_flags": 0, "opaque_flags": 0}
        )
        assert problems and "分母自校验失败" in problems[0]

    def test_self_check_green_when_balanced(self):
        assert (
            ch.denominator_problems(
                {"declared_flags": 3, "live_flags": 1, "proxy_flags": 1, "dead_flags": 0, "opaque_flags": 1}
            )
            == []
        )

    def test_judge_effect_still_calls_the_self_check(self):
        _, _, _, counts = ch.judge_effect(sources={"check_a": DEAD})
        assert ch.denominator_problems(counts) == []

    def test_me_group_count_only_counts_required(self):
        counts = self._counts({"check_a": PROXY, "check_b": PROXY_NOT_REQUIRED})
        assert counts["me_groups"] == 1

    def test_counts_surface_all_declared_gates(self):
        counts = self._counts({"check_a": DEAD, "check_b": DEAD})
        assert counts["disk_scripts"] == 2
        assert counts["argparse_gates"] == 2
        assert counts["dead_flags"] == 2

    def test_gate_without_argparse_is_not_an_argparse_gate(self):
        # 无 argparse 的门进在盘分母、不进判据分母；把两者混为一谈会让「有 argparse 门禁」
        # 这个数变成「在盘门禁」的同义反复。
        counts = self._counts({"check_plain": "def main():\n    return 0\n"})
        assert counts["disk_scripts"] == 1
        assert counts["argparse_gates"] == 0
        assert counts["declared_flags"] == 0

    def test_declared_items_are_the_nine_judged_numbers(self):
        # ITEMS 是本门自己的权威清单：漏一条 = 少判一个数，多一条 = 凭空要求登记面写一个不存在的数。
        assert list(ch.ITEMS) == [
            "在盘门禁",
            "有argparse门禁",
            "开关实例",
            "有效开关",
            "代理开关",
            "死开关",
            "不可判开关",
            "不可判门禁",
            "互斥必填组",
        ]
        assert list(ch.ITEMS.values()) == [
            "disk_scripts",
            "argparse_gates",
            "declared_flags",
            "live_flags",
            "proxy_flags",
            "dead_flags",
            "opaque_flags",
            "opaque_gates",
            "me_groups",
        ]
        assert all(key.startswith("flag_effect.") for key in ch.BASELINE_KEYS.values())
        _, _, _, counts = ch.judge_effect(sources={"check_a": LIVE})
        assert set(ch.ITEMS.values()) <= set(counts)

    def test_absent_source_is_red_not_skipped(self):
        # 在盘分母按 glob 数，判定面按源码复算：一个进了分子却读不到的门，披露里是「32 道都复算了」，
        # 实际一道也没看——这正是 BH→BT 一族「读不懂就静默」在本门自己身上的形状。
        problems, ok, _, counts = ch.judge_effect(["check_ghost_not_on_disk"])
        assert counts["disk_scripts"] == 1 and counts["declared_flags"] == 0
        assert any("源码缺席" in p and "check_ghost_not_on_disk" in p for p in problems)
        assert ok == []

    def test_unparsable_source_is_red_not_folded(self):
        # `flag_effect_map` 对直接调用者仍退回 {}（不崩），但判定面不许把「读不懂」折叠成「没有 argparse」。
        problems, _, _, counts = ch.judge_effect(sources={"check_broken": "def main(:\n    ???"})
        assert counts["argparse_gates"] == 0 and counts["declared_flags"] == 0
        assert any("源码不可解析" in p and "check_broken" in p for p in problems)
        clean_problems, _, _, clean = ch.judge_effect(sources={"check_a": LIVE})
        assert not any("源码不可解析" in p for p in clean_problems)
        assert clean["declared_flags"] == 1


# ══ E 组：登记面对账 ═══════════════════════════════════════════════════
def _baseline_stub(counts: dict[str, int]) -> dict:
    return {"flag_effect": {key: counts[key] for key in ch.ITEMS.values()}}


def _register_stub(counts: dict[str, int]) -> str:
    body = " / ".join(f"{label} {counts[key]}" for label, key in ch.ITEMS.items())
    return f"| 开关有效性（CH 轮） | 〔当前口径：{body}〕说明 | `make flag-effect` |\n"


class TestRegistration:
    def test_all_keys_agree(self):
        _, _, _, counts = ch.judge_effect(sources={"check_a": LIVE})
        problems, _ = ch.judge_registration(
            counts=counts, baseline=_baseline_stub(counts), register_text=_register_stub(counts)
        )
        assert problems == []

    def test_missing_baseline_key_is_red(self):
        _, _, _, counts = ch.judge_effect(sources={"check_a": LIVE})
        baseline = _baseline_stub(counts)
        del baseline["flag_effect"]["dead_flags"]
        problems, _ = ch.judge_registration(counts=counts, baseline=baseline, register_text=_register_stub(counts))
        assert any("BASELINE 键缺位" in p and "dead_flags" in p for p in problems)

    def test_baseline_drift_is_red(self):
        _, _, _, counts = ch.judge_effect(sources={"check_a": LIVE})
        baseline = _baseline_stub(counts)
        baseline["flag_effect"]["live_flags"] += 1
        problems, _ = ch.judge_registration(counts=counts, baseline=baseline, register_text=_register_stub(counts))
        assert any("BASELINE 漂移" in p for p in problems)

    def test_register_without_the_row_is_red(self):
        _, _, _, counts = ch.judge_effect(sources={"check_a": LIVE})
        problems, _ = ch.judge_registration(
            counts=counts, baseline=_baseline_stub(counts), register_text="没有那一行\n"
        )
        assert any("登记册 §1 未对账" in p for p in problems)

    def test_register_number_drift_is_red(self):
        _, _, _, counts = ch.judge_effect(sources={"check_a": LIVE})
        label = next(k for k, v in ch.ITEMS.items() if v == "dead_flags")
        stub = _register_stub(counts).replace(f"{label} {counts['dead_flags']}", f"{label} 9")
        problems, _ = ch.judge_registration(counts=counts, baseline=_baseline_stub(counts), register_text=stub)
        assert any("登记册 §1 未对账" in p for p in problems)

    def test_zero_values_must_still_be_declared(self):
        # 死开关 0 / 代理 0 也要真登记：键缺位和红相等是两件事，不能靠「0 就不写」蒙过去。
        _, _, _, counts = ch.judge_effect(sources={"check_a": LIVE})
        baseline = _baseline_stub(counts)
        del baseline["flag_effect"]["proxy_flags"]
        problems, _ = ch.judge_registration(counts=counts, baseline=baseline, register_text=_register_stub(counts))
        assert any("proxy_flags" in p for p in problems)

    def test_ok_line_carries_the_number(self):
        _, _, _, counts = ch.judge_effect(sources={"check_a": LIVE})
        _, ok = ch.judge_registration(
            counts=counts, baseline=_baseline_stub(counts), register_text=_register_stub(counts)
        )
        assert len(ok) == len(ch.ITEMS)
        assert all("[OK]" in line for line in ok)

    def test_counts_value_missing_is_red(self):
        # 「本门复算值」缺位不能退化成 0：0 是个合法的读数（死开关 0），拿它当缺省值会让
        # 「没判」和「判出来是 0」长得一样。
        _, _, _, counts = ch.judge_effect(sources={"check_a": LIVE})
        counts.pop("dead_flags")
        baseline = _baseline_stub({**counts, "dead_flags": 0})
        problems, _ = ch.judge_registration(
            counts=counts, baseline=baseline, register_text=_register_stub({**counts, "dead_flags": 0})
        )
        assert any("死开关" in p or "dead_flags" in p for p in problems)

    def test_bracket_must_be_the_current_caliber(self):
        # 〔〕里写着别的类别（如「示例口径」）时不算对账——CG 轮的病灶就是「注释/别的括号造数」。
        _, _, _, counts = ch.judge_effect(sources={"check_a": LIVE})
        label = next(k for k, v in ch.ITEMS.items() if v == "disk_scripts")
        stub = f"| 开关有效性（CH 轮） | 〔示例口径：{label} {counts['disk_scripts']}〕 | x |\n"
        assert ch._row_has(stub, label, counts["disk_scripts"]) is False
        assert ch._row_has(_register_stub(counts), label, counts["disk_scripts"]) is True

    def test_pairs_outside_table_rows_do_not_count(self):
        # 表行以外的文字（正文、注释）里出现「在盘门禁 1」不算登记——登记面是表，不是全文搜索。
        _, _, _, counts = ch.judge_effect(sources={"check_a": LIVE})
        label = next(k for k, v in ch.ITEMS.items() if v == "disk_scripts")
        prose = f"〔当前口径：{label} {counts['disk_scripts']}〕\n"
        assert ch._row_has(prose, label, counts["disk_scripts"]) is False

    def test_baseline_bool_is_not_a_number(self):
        # `dead_flags: true` 不是读数；当成 1 会既漏掉漂移又造出一个假对账。
        _, _, _, counts = ch.judge_effect(sources={"check_a": LIVE})
        baseline = _baseline_stub(counts)
        baseline["flag_effect"]["dead_flags"] = True
        problems, _ = ch.judge_registration(counts=counts, baseline=baseline, register_text=_register_stub(counts))
        assert any("BASELINE 键缺位" in p and "dead_flags" in p for p in problems)

    def test_load_baseline_nested_section(self, tmp_path):
        f = tmp_path / "BASELINE.yaml"
        f.write_text("top: 1\nflag_effect:\n  live_flags: 73\n  dead_flags: 0\n", encoding="utf-8")
        data, reason = ch.load_baseline(f)
        assert reason is None
        assert data["flag_effect"]["live_flags"] == 73
        assert data["flag_effect"]["dead_flags"] == 0

    def test_load_baseline_missing_file(self, tmp_path):
        data, reason = ch.load_baseline(tmp_path / "nope.yaml")
        assert data is None
        assert reason


# ══ F 组：接线与 CLI ══════════════════════════════════════════════════
class TestWiringAndCli:
    def test_wired_gate_passes(self):
        assert (
            ch.self_wiring(
                make_text="scripts/gates/check_flag_effect.py", ci_text="run: python scripts/gates/check_flag_effect.py"
            )
            == []
        )

    def test_missing_make_is_red(self):
        problems = ch.self_wiring(make_text="nothing", ci_text="check_flag_effect.py")
        assert problems and "Makefile" in problems[0]

    def test_missing_ci_is_red(self):
        problems = ch.self_wiring(make_text="check_flag_effect.py", ci_text="nothing")
        assert problems and "ci.yml" in problems[0]

    def test_both_missing_names_both(self):
        problems = ch.self_wiring(make_text="x", ci_text="y")
        assert "Makefile" in problems[0] and "ci.yml" in problems[0]

    def test_real_tree_is_wired(self):
        make_text = Path(PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
        ci_text = Path(PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert ch.self_wiring(make_text=make_text, ci_text=ci_text) == []

    def test_bare_filename_is_not_wiring(self):
        # 接线要求的是**整条调用路径**：Makefile 注释里写一句 `check_flag_effect.py` 不算有人调用。
        problems = ch.self_wiring(make_text="check_flag_effect.py", ci_text="scripts/gates/check_flag_effect.py")
        assert problems and "Makefile" in problems[0]

    def test_other_gate_path_is_not_this_gate(self):
        assert ch.self_wiring(make_text="scripts/gates/check_other.py", ci_text="scripts/gates/check_other.py") != []

    def test_cli_list_prints_rows_not_verdicts(self, capsys):
        assert ch.main(["--list"]) == 0
        out = capsys.readouterr().out
        assert "check_flag_effect\t--list\tlist\t活" in out
        assert "阻断" not in out

    def test_cli_green_repo_passes_and_prints_ok(self, monkeypatch, tmp_path, capsys):
        counts = _green_repo(monkeypatch, tmp_path)
        assert ch.main([]) == 0
        out = capsys.readouterr().out
        assert "[OK] 开关有效性" in out
        # 通过行与 [OK] 行都得带数：不带数的「通过」和上一轮的「真绿但误导」是同一件事。
        # 两条断言各自钉一行——只写「死开关 0、代理开关 0」这种两行共有的片段，
        # 把通过行的数抹掉时它会落回 [OK] 行上照样绿（M68 首轮正是这样活下来的）。
        assert f"{counts['declared_flags']} 个 (门禁, 开关) 实例" in out
        assert f"声明 {counts['declared_flags']} 个开关实例" in out
        assert f"死开关 {counts['dead_flags']}、代理开关 {counts['proxy_flags']}" in out
        assert f"通过：{counts['argparse_gates']} 道门禁声明 {counts['declared_flags']} 个开关实例" in out
        assert (
            f"死开关 {counts['dead_flags']}、代理开关 {counts['proxy_flags']}、"
            f"不可判 {counts['opaque_gates']} 全为 0，" in out
        )
        assert "四态分母自校验成立" in out
        assert "阻断" not in capsys.readouterr().err

    def test_cli_quiet_keeps_verdict_but_hides_items(self, monkeypatch, tmp_path, capsys):
        _green_repo(monkeypatch, tmp_path)
        assert ch.main(["--quiet"]) == 0
        out = capsys.readouterr().out
        assert "[OK]" not in out
        # --quiet 只收逐项 [OK]：受检面披露和通过行是判据的一部分，吞掉它们等于「少判一项」。
        assert "[SURFACE]" in out
        assert "通过：" in out

    def test_cli_discloses_judged_and_unjudged_faces(self, monkeypatch, tmp_path, capsys):
        counts = _green_repo(monkeypatch, tmp_path)
        ch.main([])
        out = capsys.readouterr().out
        assert out.count("[SURFACE]") == 3
        assert "判定面" in out and "不判定面" in out and "判据归属" in out
        assert "BASELINE 声明键 9 个" in out
        assert f"在盘门禁 {counts['disk_scripts']} 道" in out

    def test_cli_reports_self_wiring(self, monkeypatch, tmp_path, capsys):
        _green_repo(monkeypatch, tmp_path)
        # 登记表/BASELINE 都对得上，但 Makefile/ci.yml 里没这条路径 ⇒ 接线必须进退出码，
        # 否则「新增门禁忘记接线」只会留在 stdout 里没人看。
        (tmp_path / "Makefile").write_text("", encoding="utf-8")
        assert ch.main([]) == 1
        assert "未接入" in capsys.readouterr().err

    def test_baseline_unparsable_is_red(self, monkeypatch, tmp_path, capsys):
        _green_repo(monkeypatch, tmp_path)
        monkeypatch.setattr(ch, "load_baseline", lambda path: (None, "模拟：缩进错乱"))
        assert ch.main([]) == 1
        assert "BASELINE 不可解析" in capsys.readouterr().err

    def test_red_path_still_discloses_surface(self, monkeypatch, tmp_path, capsys):
        _green_repo(monkeypatch, tmp_path)
        (tmp_path / "BASELINE.yaml").write_text("flag_effect:\n  live_flags: 99\n", encoding="utf-8")
        assert ch.main([]) == 1
        assert "[SURFACE]" in capsys.readouterr().out

    def test_cli_quiet_suppresses_ok_lines(self, capsys, tmp_path, monkeypatch):
        _fake_repo(monkeypatch, tmp_path)
        ch.main(["--quiet"])
        assert "[OK]" not in capsys.readouterr().out

    def test_cli_missing_makefile_is_red(self, monkeypatch, tmp_path, capsys):
        _fake_repo(monkeypatch, tmp_path, missing="MAKEFILE")
        assert ch.main([]) == 1
        assert "仓库级前提缺席" in capsys.readouterr().err

    @pytest.mark.parametrize("attr", ["GATES_DIR", "CI_YML", "BASELINE", "REGISTER"])
    def test_cli_missing_required_premise_is_red(self, monkeypatch, tmp_path, attr):
        _fake_repo(monkeypatch, tmp_path, missing=attr)
        assert ch.main([]) == 1

    def test_usage_error_is_two(self):
        with pytest.raises(SystemExit) as exc:
            ch.main(["--no-such-flag"])
        assert exc.value.code == 2


def _fake_repo(monkeypatch, tmp_path, missing: str | None = None) -> None:
    """把仓库级前提指到 tmp：只用于 CLI 前提锁，判定本身仍读 tmp 里那一道合成门禁。"""
    gates = tmp_path / "scripts" / "gates"
    gates.mkdir(parents=True, exist_ok=True)
    (gates / "check_synth.py").write_text(LIVE, encoding="utf-8")
    paths = {
        "MAKEFILE": tmp_path / "Makefile",
        "GATES_DIR": gates,
        "CI_YML": tmp_path / ".github" / "workflows" / "ci.yml",
        "BASELINE": tmp_path / "BASELINE.yaml",
        "REGISTER": tmp_path / "docs" / "PROJECT_STATUS_REGISTER.md",
    }
    for attr, path in paths.items():
        if attr == missing:
            monkeypatch.setattr(ch, attr, tmp_path / "absent" / attr.lower())
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if attr != "GATES_DIR":
            path.write_text("", encoding="utf-8")
        monkeypatch.setattr(ch, attr, path)


def _green_repo(monkeypatch, tmp_path) -> dict[str, int]:
    """tmp 里造一棵**四面对得上**的树：判定、BASELINE、§1、接线全齐，用来锁 main() 的绿路径。"""
    _fake_repo(monkeypatch, tmp_path)
    counts = ch.judge_effect(["check_synth"])[3]
    (tmp_path / "BASELINE.yaml").write_text(
        "flag_effect:\n" + "".join(f"  {key}: {counts[key]}\n" for key in ch.ITEMS.values()), encoding="utf-8"
    )
    body = " / ".join(f"{label} {counts[key]}" for label, key in ch.ITEMS.items())
    (tmp_path / "docs" / "PROJECT_STATUS_REGISTER.md").write_text(
        f"| 开关有效性（CH 轮） | 〔当前口径：{body}〕说明 | `make flag-effect` |\n", encoding="utf-8"
    )
    script = "scripts/gates/check_flag_effect.py"
    (tmp_path / "Makefile").write_text(f"flag-effect:\n\t$(PY) {script}\n", encoding="utf-8")
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(f"run: python {script}\n", encoding="utf-8")
    return counts


# ══ R 组：真实树 + 两处写侧修复 ═══════════════════════════════════════
class TestRealTree:
    def test_no_dead_switch_left(self):
        problems, _, _, counts = ch.judge_effect()
        assert counts["dead_flags"] == 0
        assert not any("死开关" in p for p in problems)

    def test_no_proxy_switch_left(self):
        _, _, _, counts = ch.judge_effect()
        assert counts["proxy_flags"] == 0

    def test_denominator_closes_on_real_tree(self):
        _, _, _, counts = ch.judge_effect()
        assert counts["declared_flags"] == counts["live_flags"]
        assert counts["opaque_flags"] == 0

    def test_every_gate_and_switch_judged(self):
        _, _, _, counts = ch.judge_effect()
        assert counts["disk_scripts"] == len(list((PROJECT_ROOT / "scripts" / "gates").glob("*.py")))
        assert counts["argparse_gates"] >= 20

    def test_one_required_mutually_exclusive_group(self):
        _, _, _, counts = ch.judge_effect()
        assert counts["me_groups"] == 1

    def test_verify_now_selects_the_verify_branch(self, tmp_path, monkeypatch):
        cs = _load("checksum_results_under_test", PROJECT_ROOT / "scripts" / "gates" / "checksum_results.py")
        calls: list[str] = []
        monkeypatch.setattr(cs, "write_manifest", lambda *a, **k: calls.append("write") or 0)
        monkeypatch.setattr(cs, "verify_manifest", lambda *a, **k: calls.append("verify") or 0)
        assert cs.main(["--results-dir", str(tmp_path), "--verify"]) == 0
        assert calls == ["verify"]

    def test_write_still_selects_the_write_branch(self, tmp_path, monkeypatch):
        cs = _load("checksum_results_under_test2", PROJECT_ROOT / "scripts" / "gates" / "checksum_results.py")
        calls: list[str] = []
        monkeypatch.setattr(cs, "write_manifest", lambda *a, **k: calls.append("write") or 0)
        monkeypatch.setattr(cs, "verify_manifest", lambda *a, **k: calls.append("verify") or 0)
        assert cs.main(["--results-dir", str(tmp_path), "--write"]) == 0
        assert calls == ["write"]

    def test_missing_dir_fails_before_dispatch(self, tmp_path):
        cs = _load("checksum_results_under_test3", PROJECT_ROOT / "scripts" / "gates" / "checksum_results.py")
        assert cs.main(["--results-dir", str(tmp_path / "absent"), "--verify"]) == 1

    @pytest.mark.parametrize(
        ("argv", "strict_seen"), [(["x"], False), (["x", "--warn-only"], False), (["x", "--strict"], True)]
    )
    def test_drift_gate_routes_warn_only_into_dispatch(self, argv, strict_seen, monkeypatch):
        dh = _load("drift_under_test", PROJECT_ROOT / "scripts" / "gates" / "check_docs_history_drift.py")
        seen: list[bool] = []
        monkeypatch.setattr(sys, "argv", argv)
        monkeypatch.setattr(dh, "_check_history_drift", lambda threshold, strict: seen.append(strict) or 0)
        assert dh.main() == 0
        assert seen == [strict_seen]

    def test_drift_gate_rejects_contradictory_pair(self, monkeypatch):
        dh = _load("drift_under_test2", PROJECT_ROOT / "scripts" / "gates" / "check_docs_history_drift.py")
        called: list[bool] = []
        monkeypatch.setattr(sys, "argv", ["x", "--strict", "--warn-only"])
        monkeypatch.setattr(dh, "_check_history_drift", lambda threshold, strict: called.append(strict) or 0)
        assert dh.main() == 2
        assert called == []
