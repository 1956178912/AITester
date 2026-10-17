"""击杀 self-mutation 基线存活变异体的**行为契约**补测（WP-A，2026-10-17）。

## 这个文件为什么存在

`scripts/tools/self_mutation.py` 对 3 个核心叶子工具模块跑了自身测试套件的
变异测试基线（报告见 `experiments/results/self_mutation_20261017/`）。**存活
变异体** = 现有测试没有断言到的行为面；本文件只补"真实行为契约"类缺口
（docstring 明示的语义 / 跨模块约定 / 公开 API 面），**不为凑分数去硬杀
等价变异体或实现细节**。

## 口径纪律

- 每个用例注释里写明它击杀的 `mutant_id`（来自基线 JSON；`mutant_id` =
  模块 stem + 变异代码 sha256 前缀，源码不变时跨 run 稳定，可逐条对账）；
- 只断言**变异体会改变的可观测行为**：断言必须在不带变异时通过、在变异体下
  失败（before/after 复跑由 `--test-map` 把本文件追加进对应模块测试集合验证）；
- 零 LLM / 零网络 / 确定性；不依赖时间、随机、外部资源；
- 等价变异体（annotation-only、不可达分支、fd 编号约定）**不在本文件硬杀**，
  逐个归因见报告 `generator_filtered` 之外的存活清单与
  `docs/design/self_mutation_harness.md`。

## 复跑口径（before/after 同一 target 集合，只多本文件）

    python scripts/tools/self_mutation.py \
      --test-map src/utils/env_utils.py=tests/test_env_utils.py,tests/test_self_mutation_targets.py \
      --test-map src/utils/helpers.py=tests/test_helpers_json_property.py,tests/test_helpers_json_robustness.py,tests/test_helpers_json_fence_content.py,tests/test_self_mutation_targets.py \
      --test-map src/utils/atomic_io.py=tests/test_atomic_io.py,tests/test_self_mutation_targets.py \
      --workers 2
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

import src.utils.atomic_io as atomic_io
from src.utils.env_utils import env_float, env_int
from src.utils.helpers import extract_code_block, extract_json_object

# ─── env_utils：lo/hi 边界是**闭区间**（docstring "超出 [lo, hi]"） ──────────
#
# 基线 4 个 boundary_shift 存活变异体全部落在 `(lo is not None and value < lo)
# or (hi is not None and value > hi)` 的 strict/non-strict 互换上：
#   env_utils:817f4edcb8c2  `<`  → `<=`（lo 边界值被误判越界）
#   env_utils:f3afbc06be0a  `>`  → `>=`（hi 边界值被误判越界）
#   env_utils:d8ac3d59d51d  env_float 的 `<` → `<=`
#   env_utils:ca9e2bbd415b  env_float 的 `>` → `>=`
# 既有测试只测了"0 < lo / 99 > hi"，恰好没测**恰好等于边界**的值。


def test_env_int_lo_boundary_is_inclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    """恰好等于 lo 的值是合法值（击杀 env_utils:817f4edcb8c2）。"""
    monkeypatch.setenv("AITESTER_SELF_MUT_LO", "5")
    assert env_int("AITESTER_SELF_MUT_LO", 7, lo=5) == 5, "lo 边界值被误判越界（应为闭区间）"


def test_env_int_hi_boundary_is_inclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    """恰好等于 hi 的值是合法值（击杀 env_utils:f3afbc06be0a）。"""
    monkeypatch.setenv("AITESTER_SELF_MUT_HI", "50")
    assert env_int("AITESTER_SELF_MUT_HI", 7, hi=50) == 50, "hi 边界值被误判越界（应为闭区间）"


def test_env_float_lo_boundary_is_inclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    """env_float 的 lo 边界同样闭区间（击杀 env_utils:d8ac3d59d51d）。"""
    monkeypatch.setenv("AITESTER_SELF_MUT_FLO", "0.0")
    assert env_float("AITESTER_SELF_MUT_FLO", 0.95, lo=0.0) == 0.0


def test_env_float_hi_boundary_is_inclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    """env_float 的 hi 边界同样闭区间（击杀 env_utils:ca9e2bbd415b）。"""
    monkeypatch.setenv("AITESTER_SELF_MUT_FHI", "1.0")
    assert env_float("AITESTER_SELF_MUT_FHI", 0.95, hi=1.0) == 1.0


# ─── helpers：JSON 修复链 / 代码块提取 的既有行为缺口 ──────────────────────
#
# 这些变异体全部落在 helpers 的"LLM 输出鲁棒性修复链"上：现有测试覆盖了
# 主路径与常见降级，但没有逐条锁定下面四类**修复档**语义；变异体存活说明
# 修复链的行为在该输入上无人断言。每个用例对应一条基线存活变异体（注释
# 写明 mutant_id 与变异的语义），before/after 由 --test-map 复跑对账。


def test_extract_code_block_honors_requested_language_fence() -> None:
    """`language=` 必须精确匹配对应语言标记的围栏块（而非落入通用兜底）。

    击杀 helpers:2b2a44279380：删除 `if language:` 精确匹配分支后，非 python
    语言的围栏（javascript/ruby/cpp）不再被识别，函数退化为返回原文——这正是
    docstring 承诺的"按调用方期望语言精确匹配"行为。
    """
    text = "说明\n```javascript\nconst a = 1;\n```\n结束"
    assert extract_code_block(text, language="javascript") == "const a = 1;"
    assert extract_code_block("```ruby\nputs 1\n```", language="ruby") == "puts 1"


def test_extract_json_object_repairs_python_false_literal() -> None:
    """值位置 `False` 应被修复为 JSON 的 `false`（LLM 常见 Python 字面量泄漏）。

    击杀 helpers:2a79bf382145：把 `_repair_json_text` 字面量映射表中的
    'False' 换成垃圾串后，`{"a": False}` 无法解析（修复档失效 → JSONDecodeError）。
    """
    assert extract_json_object('{"a": False}') == {"a": False}


def test_extract_json_object_quotes_python_tuple_keys() -> None:
    """键位置的 Python 元组字面量应被加引号保留意图（而非解析失败/键被改写）。

    击杀 5 个存活变异体（_quote_tuple_keys_once 的字符串感知与元组键正则）：
    - helpers:d0872864317d 元组键正则被整体改写（匹配失败 → JSONDecodeError）；
    - helpers:0c832ebf6a0b `'({inner})'` 的 '(' 被改写（键变成 'x0,1)'）；
    - helpers:0b57662662a5 字符串段判定 `ch == '"'` 被改写（切分错乱 → 解析失败）；
    - helpers:873b3ed69dfc `in_str = True` 被改成 False（字符串感知失效）；
    - helpers:f6ee52d99960 循环控制 continue→break（字符串段扫描提前终止）。
    """
    text = '{"length_by_edge":{(0,1):5,(1,0):5}}'
    assert extract_json_object(text) == {"length_by_edge": {"(0,1)": 5, "(1,0)": 5}}


def test_extract_json_object_evaluates_python_string_expressions() -> None:
    """值位置的 Python 字符串表达式（拼接/重复）应被求值为真实字符串。

    击杀 9 个存活变异体（`_quote_python_expressions` / `_safe_eval_numeric_expr`
    的字符串表达式修复档）：
    - helpers:85f51aab993f（`'"' not in s` 快路径判定取反）
    - helpers:6c54ca18b2f5（删除 AST Constant 求值分支）
    - helpers:c1b8b5ba8a7a（Add 判定的 and→or）
    - helpers:983effa31ffa（`return out` → None）
    - helpers:28f3e7623b5a（换行守卫 `'\n'` 常量被改写）
    - helpers:25585de66de3（ast.parse mode='eval' 被改写）
    - helpers:382d9b6c2ac2（前缀长度计算 Sub→Add）
    - helpers:b86cc996a7f1（返回 prefix+json.dumps 改为 None）
    - helpers:61d14eae6dcb（字符串表达式正则被整体改写）
    这些分支此前只在"恰好需要修复"的输入上才会触发，普通 JSON 走快路径无感。
    """
    assert extract_json_object('{"a": "x" + "y"}') == {"a": "xy"}
    assert extract_json_object('{"a": "abc" * 2}') == {"a": "abcabc"}


# ─── atomic_io：fd 卫生 / 临时文件命名约定 / 公开 API 面 ────────────────────


def test_atomic_write_mkstemp_failure_does_not_close_arbitrary_fd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """mkstemp 失败时不得关闭 fd>=0 的任意描述符（否则可能关掉 stdio）。

    击杀 3 个存活变异体（都在 fd/tmp_path 的**初始值**上）：
    - atomic_io:16db84aa5293 `fd = -1` → `fd = 1`（mkstemp 失败后误 close(1)）；
    - atomic_io:ce5570ddbcb3 删除 `fd = -1` 语句（finally 引用未定义 fd → NameError）；
    - atomic_io:e5a5b2e08868 删除 `tmp_path: str | None = None`（finally NameError）。
    这些初始值的意义就是"mkstemp 前/fdopen 接管前的安全默认"，此前无测试覆盖。
    """
    closed: list[int] = []

    def _fake_close(fd: int) -> None:
        closed.append(fd)

    def _raise_mkstemp(*_args: object, **_kwargs: object) -> None:
        raise OSError("模拟 mkstemp 失败")

    monkeypatch.setattr(atomic_io.tempfile, "mkstemp", _raise_mkstemp)
    monkeypatch.setattr(atomic_io.os, "close", _fake_close)
    with pytest.raises(OSError):
        atomic_io.atomic_write_text(str(tmp_path / "never.txt"), "内容")
    assert closed == [], f"mkstemp 失败后错误关闭了 fd: {closed}"


def test_atomic_write_cleanup_failure_leaves_identifiable_temp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """清理失败时：临时文件命名保持 `.aitester_tmp_*.tmp` 约定 + 留 DEBUG 痕迹。

    为什么这是行为契约而不是实现细节：
    - 跨模块约定——`tests/test_venv_cache_monitoring.py` 以
      `glob(".aitester_tmp_*.tmp")` 断言"缓存目录无残留"；命名漂移会让清理失败的
      垃圾逃过该监控（监控恒绿但磁盘在泄漏）；
    - 可观测性——清理失败必须留 DEBUG 日志（含临时路径），否则"文件残留"无从定位。

    击杀 3 个存活变异体：
    - atomic_io:7e5948d1dd26 `prefix=".aitester_tmp_"` → 'x' 重写；
    - atomic_io:fcd9305bde69 `suffix=".tmp"` → 'x' 重写；
    - atomic_io:6234f51035a5 清理失败日志文本被整体重写（"清理失败"字样丢失）。
    """
    target = tmp_path / "keep.txt"
    atomic_io.atomic_write_text(str(target), "old-content")

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise OSError("模拟 replace/unlink 失败")

    monkeypatch.setattr(atomic_io.os, "replace", _raise)
    monkeypatch.setattr(atomic_io.os, "unlink", _raise)
    with caplog.at_level(logging.DEBUG, logger="src.utils.atomic_io"), pytest.raises(OSError):
        atomic_io.atomic_write_text(str(target), "new-content")
    leftovers = list(tmp_path.glob(".aitester_tmp_*.tmp"))
    assert len(leftovers) == 1, f"清理失败后的临时文件应保持 .aitester_tmp_*.tmp 命名约定，实得 {leftovers}"
    assert "清理失败" in caplog.text, "清理失败必须有可定位的 DEBUG 日志"
    assert target.read_text(encoding="utf-8") == "old-content", "替换失败后目标文件必须保持旧完整内容"


def test_atomic_io_public_api_surface_is_exact() -> None:
    """`__all__` 是模块公开 API 声明，必须精确（star-import 契约）。

    击杀 atomic_io:7c7574163adb / atomic_io:49d3118af77d：变异体把 `__all__`
    里两个函数名字符串之一重写成 'x'——显式 import 的测试不受影响，但
    `from src.utils.atomic_io import *` 的消费方会拿不到真实实现。
    """
    assert set(atomic_io.__all__) == {"atomic_write_json", "atomic_write_text"}
    exported: dict[str, object] = {}
    exec("from src.utils.atomic_io import *", {}, exported)  # 锁定 star-import 契约（S102 全局豁免）
    assert {"atomic_write_json", "atomic_write_text"} <= set(exported)
