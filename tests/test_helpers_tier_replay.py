"""AB-1（2026-10-19）：`experiments/helpers_tier_replay.py` 的回归锁。

这组测试**不碰真实缓存**（真实缓存含 prompt 与响应正文，可能夹带被测代码，
且随用户机器变化）——全部用 `tmp_path` 里的合成假缓存。它们锁的是三件事：

1. **隐私纪律可机器验**：正文哨兵绝不出现在脚本输出里，且抑制计数非零
   （否则"没泄漏"只是因为压根没触发告警，锁是空的）；
2. **仪表不是虚设**：`_first_parse` 必须**能**检出一个会返回的片段，
   否则"真实语料上 0 次触发"这条结论毫无意义（阳性对照）；
3. **口径与源码同步**：档 2 的候选序与本仓 `helpers.py` 里的实际字面量
   逐 AST 对齐，源码一改、镜像测试先红。
"""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from experiments import helpers_tier_replay as rep
from src.utils import helpers

# 合成语料里植入的正文哨兵：出现在 prompt/system/response 三处，
# 任何一处被打印即失败。
BODY_SENTINEL = "SENTINEL-MUST-NOT-LEAK-7f3a9c"

# 串外裸反斜杠致两个扫描器分歧的**最小复现**（AB-1 实测：真实语料 7,565 条
# 中有 1 条属此类）：`_find_balanced_delimited` 把串外的 `\` 也当转义符（吃掉
# 下一个 `}`），`_first_balanced_object` 在串外忽略 `\`，故档 1 取不到片段、
# 档 2 取到 `{"a":\}`。
DIVERGENT_INPUT = '{"a":\\}{"b":1}'


def _write_cache(cache_dir: Path, responses: list[tuple[str, str]]) -> None:
    """按产品缓存 schema 写合成条目（只写测试自造内容，绝不读真实缓存）。"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    for i, (system, response) in enumerate(responses):
        payload = {
            "prompt": f"{BODY_SENTINEL}-prompt-{i}",
            "system": system,
            "response": response,
            "tokens": {"prompt": 1, "completion": 1},
            "timestamp": "2026-10-19T00:00:00",
            "creator_uid": "tester",
        }
        (cache_dir / f"{i:04d}.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.unit
class TestPrivacyDiscipline:
    """正文一个字都不出：脚本自身输出只含聚合计数。"""

    def test_response_bodies_never_appear_in_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        cache = tmp_path / "llm"
        # 叶子回退档会对这类输入打 warning 且**把片段前缀写进日志**——正是要锁的那条路
        _write_cache(
            cache,
            [
                (f"{BODY_SENTINEL}-sys", '{"outer": stuff, {"k": 42}'),
                ("", f'{{"{BODY_SENTINEL}": broken,}}'),
                ("logic_analysis", "no json at all here"),
            ],
        )
        assert rep.main(["--cache-dir", str(cache), "--json"]) == 0
        captured = capsys.readouterr()
        out = captured.out + captured.err
        assert BODY_SENTINEL not in out, "响应正文泄漏进脚本输出"
        report = json.loads(out)
        assert report["n_suppressed_warnings"] > 0, "抑制计数为 0 ⇒ 本锁未真正覆盖告警路径"

    def test_missing_cache_dir_fails_closed(self, tmp_path: Path) -> None:
        """目录不存在必须报错退出，不能返回"全零但看起来像跑过"的报告。"""
        assert rep.main(["--cache-dir", str(tmp_path / "nope"), "--json"]) == 2


@pytest.mark.unit
class TestInstrumentIsNotVacuous:
    """阳性对照：仪器检得出"会返回"，否则 0 次触发不构成证据。"""

    def test_first_parse_detects_a_returnable_fragment(self) -> None:
        # 尾随逗号片段：档 2 的 `_repair_json_text` 能救活 ⇒ 计数必须增加
        assert rep._first_parse('{"a": 1,}') == {"a": 1}
        # 多对象背靠背拼接（D1 档 2 立项时的实测主因）：取到的**首个**片段
        # 可经修复解析 ⇒ 本档返回分支会命中。`_first_parse` 的入参是片段
        # 而非整串，直接喂整串必然 None（那是入参口径错，不是仪器失灵）。
        joined = '{"a": 1,}{"b": 2}'
        fragment = helpers._first_balanced_object(joined)
        assert fragment == '{"a": 1,}'
        assert rep._first_parse(fragment) == {"a": 1}

    def test_first_parse_rejects_empty_dict_via_gate_semantics(self) -> None:
        # `_first_parse` 有意保留空字典（`{}`），因为源码的门是
        # `isinstance(_obj, dict) and _obj`——空字典不算返回。
        assert rep._first_parse("{}") == {}

    def test_counts_reproduced_on_synthetic_corpus(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cache = tmp_path / "llm"
        _write_cache(
            cache,
            [
                ("", '{"ok": 1}'),  # 快路径直接解析
                ("", "plain text"),  # 必然 raise
                ("", DIVERGENT_INPUT),  # 串外裸反斜杠：档 1 失败、档 2 取到片段
            ],
        )
        # 只压日志等级、不改全局状态（monkeypatch 负责还原）——AA-8 那类
        # "测试偷偷改了进程级状态"的通道不能再开一次。
        monkeypatch.setattr(helpers.logger, "level", logging.CRITICAL)
        report = rep.replay(cache)
        assert report["n_response_str"] == 3
        assert report["n_ok_dict"] == 2  # 含分歧样本经叶子档返回的那条
        assert report["n_raise"] == 1
        assert report["tier2_entered"] == 1
        assert report["tier2_fragment"] == 1
        assert report["tier2_scanner_divergent"] == 1
        # 关键：分歧确实发生了，但档 2 的五个候选**都救不活**含裸反斜杠的片段
        assert report["tier2_would_return_any"] == 0
        assert report["divergent_would_return_any"] == 0
        assert report["tier2_multi_call"] == 0, "一个响应多次进入档 2 ⇒ `_calls[-1]` 口径失效"


@pytest.mark.unit
class TestMirrorStaysInSyncWithSource:
    """镜像与源码逐 AST 对齐：`helpers.py` 的档 2 一改，本锁先红。"""

    @staticmethod
    def _source_candidate_names() -> tuple[str, ...]:
        tree = ast.parse(Path("src/utils/helpers.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.For) or not isinstance(node.iter, ast.Tuple):
                continue
            # 目标是 `Name` 而非解包元组：仓内另有 `for a, b in (5 元组)` 的
            # 循环（如枚举候选），不排除就会误命中并 AttributeError。
            if not (isinstance(node.target, ast.Name) and node.target.id == "cand"):
                continue
            if len(node.iter.elts) != 5:
                continue
            body_src = "\n".join(ast.unparse(s) for s in node.body)
            if "isinstance(_obj, dict) and _obj" in body_src:
                return tuple(ast.unparse(e) for e in node.iter.elts)
        raise AssertionError("未在 helpers.py 找到档 2 的 5 候选循环，镜像锁失去依据")

    @staticmethod
    def _mirror_candidate_names() -> tuple[str, ...]:
        fn = getattr(rep._tier2_candidates, "__code__", None)
        assert fn is not None
        tree = ast.parse(Path(rep.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_tier2_candidates":
                ret = next(s for s in node.body if isinstance(s, ast.Return))
                assert isinstance(ret.value, ast.Tuple)
                return tuple(ast.unparse(e) for e in ret.value.elts)
        raise AssertionError("找不到 _tier2_candidates 的候选元组")

    def test_candidate_grammar_matches_source(self) -> None:
        def norm(seq: tuple[str, ...]) -> tuple[str, ...]:
            # 源码片段变量叫 `_first`、镜像形参叫 `fragment`，且镜像必须带
            # `helpers.` 模块前缀才能调用私有函数——归一化这两处差异后逐字比对。
            return tuple(
                item.replace("_first", "FRAG").replace("fragment", "FRAG").replace("helpers.", "") for item in seq
            )

        source = norm(self._source_candidate_names())
        mirror = norm(self._mirror_candidate_names())
        assert source == mirror, f"档 2 候选序漂移：{source} vs {mirror}"
        assert source == (
            "FRAG",
            "_repair_json_text(FRAG)",
            "_quote_python_expressions(FRAG)",
            "_quote_python_expressions(_repair_json_text(FRAG))",
            "_repair_json_bounded(FRAG)",
        ), "候选序本身也被钉住：任一候选增删换序即红"


@pytest.mark.unit
class TestDeletionEquivalenceProbe:
    """AB-2 前置：在锁定的分歧类上，"删掉档 2"与"保留档 2"输出是否逐字相同。

    这**不是**在实施删除，只是把"删除属行为变更"这句话换成可跑的证据。
    """

    @pytest.mark.parametrize(
        "text",
        [
            DIVERGENT_INPUT,  # 档 1 取不到片段（真实语料 1/667 的那类）
            '{"a":1}\\{"b":2}',  # 多对象拼接、两扫描器一致
            '{"k": 1,}',  # 纯语法损坏，档 1 修复命中
            '{"outer": stuff, {"k": 42}',  # 叶子档兜底
        ],
    )
    def test_output_identical_with_and_without_tier2(self, text: str) -> None:
        def _run(kill_tier2: bool) -> Any:
            original = helpers._first_balanced_object
            prev_leaf = helpers._LEAF_FALLBACK_ACTIVE  # 入口态记下、出口还原（AA-8 纪律）
            helpers._first_balanced_object = (lambda _t: None) if kill_tier2 else original
            helpers._LEAF_FALLBACK_ACTIVE = False
            try:
                return helpers.extract_json_object(text)
            except json.JSONDecodeError:
                return "JSONDecodeError"
            finally:
                helpers._first_balanced_object = original
                helpers._LEAF_FALLBACK_ACTIVE = prev_leaf

        with_tier2 = _run(False)
        without_tier2 = _run(True)
        assert with_tier2 == without_tier2, f"分歧类上删档 2 会改变输出：{with_tier2!r} vs {without_tier2!r}"


@pytest.mark.unit
class TestDivergentClassUnrescuable:
    """分歧类（档 1 失败 / 档 2 取到片段）里，档 2 的 5 个候选能否救活？实测 0。

    AA-5 的 54,006 条枚举只覆盖"两扫描器取到**同一**片段"的情形，恰恰没覆盖
    本类——而本类才是档 2 可能与档 1 结论不同的唯一入口。故这里**定向枚举分歧类**：
    分歧样本数必须 > 0（否则本锁是空的），且可被返回的样本数必须 == 0。
    任何往候选里加"删反斜杠"类修复的改动都会先在这里转红。
    """

    CORES = (
        '{"a": 1}',
        '{"a": 1,}',
        '{"k": {"x": 1}}',
        '{"a": "s"}',
        '{"a": [1,2]}',
        '{"a": None}',
        '{"a": True}',
        '{"a": inf}',
        '{"(0,1)": 5}',
        '{"a": "b" "c"}',
        '{"a": 1}{"b": 2}',
        'text {"a": 1} more',
        '{"a": 1, "b": "two"}',
    )
    INJECT = ("\\", "\\}", "\\{", "\\ ", "\\\\", "\\x")
    SUFFIX = ("", '{"z": 9}', "}", " tail", '{"y": {"w": 1}}')

    def test_no_divergent_fragment_is_rescuable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(helpers.logger, "level", logging.CRITICAL)
        original = helpers._find_balanced_json
        divergent = rescuable = 0
        for core in self.CORES:
            for inj in self.INJECT:
                for pos in range(len(core) + 1):
                    for sfx in self.SUFFIX:
                        text = core[:pos] + inj + core[pos:] + sfx
                        start = text.find("{")
                        if start == -1:
                            continue
                        base = original(text, start)
                        first = helpers._first_balanced_object(text)
                        if first is None:
                            continue
                        if (base.strip() if base else None) == first:
                            continue  # 只统计分歧类
                        divergent += 1
                        if rep._first_parse(first):
                            rescuable += 1
        assert divergent > 0, "分歧类样本数为 0 ⇒ 本锁没有覆盖到任何东西"
        assert rescuable == 0, f"分歧类里档 2 能返回 {rescuable} 例：保留理由需重新评估"
        assert divergent >= 500, f"分歧样本仅 {divergent} 条，枚举强度低于登记值"
