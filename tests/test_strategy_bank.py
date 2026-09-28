"""批次4 策略银行（Strategy Bank）单元测试。

覆盖：
- 开关默认关（STRATEGY_BANK_ENABLE 未设 → strategy_bank_enabled() False）
- 开关开启（monkeypatch 环境变量）
- select_strategy 精确匹配（三元组全命中）
- select_strategy 次级匹配（tag 通配）
- select_strategy 末级匹配（仅 category 通配）
- select_strategy 预算约束过滤
- select_strategy 空库 → None
- select_strategy outcome 成功率加权（ESDA Phase 1）
- record_strategy_outcome 追加到 JSON 文件
- strategy_bank_stats 统计口径
- 文件缺失 → 保守降级（空库，select_strategy 返回 None）
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import patch


def _write_bank(bank: dict, tmp: str) -> str:
    path = os.path.join(tmp, "strategy_bank.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False)
    return path


def test_strategy_bank_default_off() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("STRATEGY_BANK_ENABLE", None)
        from src.tools.strategy_bank import strategy_bank_enabled

        assert strategy_bank_enabled() is False


def test_strategy_bank_switch_on() -> None:
    with patch.dict(os.environ, {"STRATEGY_BANK_ENABLE": "true"}):
        from src.tools.strategy_bank import strategy_bank_enabled

        assert strategy_bank_enabled() is True


def test_select_strategy_exact_match() -> None:
    from src.tools.strategy_bank import select_strategy

    with tempfile.TemporaryDirectory() as tmp:
        bank = {
            "strategies": [
                {
                    "error_category": "assertion",
                    "fix_strategy_tag": "logic_error",
                    "cross_file": False,
                    "strategy": "single_patch",
                    "prompt_hint": "inject assertion-specific context",
                    "budget": "low",
                },
                {
                    "error_category": "assertion",
                    "fix_strategy_tag": "logic_error",
                    "cross_file": True,
                    "strategy": "cross_file_coordination",
                    "prompt_hint": "coordinate across modules",
                    "budget": "high",
                },
            ]
        }
        path = _write_bank(bank, tmp)
        result = select_strategy("assertion", "logic_error", cross_file=False, path=path)
        assert result is not None
        assert result["strategy"] == "single_patch"
        # cross_file=True → 命中第二条
        result2 = select_strategy("assertion", "logic_error", cross_file=True, path=path)
        assert result2 is not None
        assert result2["strategy"] == "cross_file_coordination"


def test_select_strategy_partial_match_tag_wildcard() -> None:
    """次级匹配：fix_strategy_tag 通配（entry_tag=None 匹配任意 tag）。"""
    from src.tools.strategy_bank import select_strategy

    with tempfile.TemporaryDirectory() as tmp:
        bank = {
            "strategies": [
                {
                    "error_category": "runtime",
                    "fix_strategy_tag": None,
                    "cross_file": False,
                    "strategy": "rewrite_runtime",
                    "prompt_hint": "runtime rewrite",
                }
            ]
        }
        path = _write_bank(bank, tmp)
        # 传任意 tag → 次级匹配命中（entry_tag=None 是通配）
        result = select_strategy("runtime", "any_tag", cross_file=False, path=path)
        assert result is not None
        assert result["strategy"] == "rewrite_runtime"


def test_select_strategy_category_only_match() -> None:
    """末级匹配：仅 error_category 命中（cross_file / tag 通配）。"""
    from src.tools.strategy_bank import select_strategy

    with tempfile.TemporaryDirectory() as tmp:
        bank = {
            "strategies": [
                {
                    "error_category": "timeout",
                    "fix_strategy_tag": None,
                    "cross_file": True,
                    "strategy": "loop_break",
                    "prompt_hint": "add exit conditions",
                }
            ]
        }
        path = _write_bank(bank, tmp)
        # cross_file=False（与 entry 的 True 不匹配）→ 次级不命中，
        # 末级 category 通配命中
        result = select_strategy("timeout", None, cross_file=False, path=path)
        assert result is not None
        assert result["strategy"] == "loop_break"


def test_select_strategy_budget_filter() -> None:
    """预算约束：budget_hint 过滤不匹配的条目。"""
    from src.tools.strategy_bank import select_strategy

    with tempfile.TemporaryDirectory() as tmp:
        bank = {
            "strategies": [
                {
                    "error_category": "assertion",
                    "fix_strategy_tag": "logic_error",
                    "cross_file": False,
                    "strategy": "expensive_multi_candidate",
                    "budget": "high",
                },
                {
                    "error_category": "assertion",
                    "fix_strategy_tag": "logic_error",
                    "cross_file": False,
                    "strategy": "cheap_single",
                    "budget": "low",
                },
            ]
        }
        path = _write_bank(bank, tmp)
        # budget_hint="low" → 只命中 cheap_single
        result = select_strategy("assertion", "logic_error", cross_file=False, budget_hint="low", path=path)
        assert result is not None
        assert result["strategy"] == "cheap_single"
        # budget_hint="high" → 只命中 expensive_multi_candidate
        result_high = select_strategy("assertion", "logic_error", cross_file=False, budget_hint="high", path=path)
        assert result_high is not None
        assert result_high["strategy"] == "expensive_multi_candidate"


def test_select_strategy_empty_bank_returns_none() -> None:
    """空策略库 → select_strategy 返回 None（保守降级，不阻断修复）。"""
    from src.tools.strategy_bank import select_strategy

    with tempfile.TemporaryDirectory() as tmp:
        bank: dict = {"strategies": []}
        path = _write_bank(bank, tmp)
        assert select_strategy("assertion", "logic_error", path=path) is None


def test_select_strategy_missing_file_degrades() -> None:
    """策略库文件缺失 → 保守降级（空库，返回 None）。"""
    import tempfile as _tf

    from src.tools.strategy_bank import select_strategy

    with _tf.TemporaryDirectory() as tmp:
        missing_path = os.path.join(tmp, "nonexistent.json")
        assert select_strategy("assertion", None, path=missing_path) is None


def test_record_strategy_outcome_appends_to_json() -> None:
    from src.tools.strategy_bank import record_strategy_outcome, strategy_bank_stats

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "bank.json")
        # 初始空文件
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"strategies": [], "outcomes": []}')
        record_strategy_outcome(("assertion", "logic_error", False), "single_patch", success=True, path=path)
        record_strategy_outcome(("runtime", None, False), "rewrite", success=False, path=path)
        stats = strategy_bank_stats(path=path)
        assert stats["outcome_count"] == 2
        assert stats["success_rate"] == 0.5


def test_strategy_bank_stats_empty() -> None:
    """空策略库统计：strategy_count=0, outcome_count=0, success_rate=0.0。"""
    from src.tools.strategy_bank import strategy_bank_stats

    with tempfile.TemporaryDirectory() as tmp:
        path = _write_bank({"strategies": [], "outcomes": []}, tmp)
        stats = strategy_bank_stats(path=path)
        assert stats["strategy_count"] == 0
        assert stats["outcome_count"] == 0
        assert stats["success_rate"] == 0.0


# ─── ESDA Phase 1：outcome 成功率加权检索 ─────────────────────────────────────


def test_select_strategy_success_rate_weighting() -> None:
    """同签名下两个策略变体，outcome 记录显示 A 成功率高 → 选 A。

    保守口径验证：
    - 有 outcome 数据时：成功率高的策略优先；
    - 无 outcome 数据时（冷启动）：匹配优先级不变（历史口径等价）。
    """
    from src.tools.strategy_bank import select_strategy

    with tempfile.TemporaryDirectory() as tmp:
        bank = {
            "strategies": [
                {
                    "error_category": "assertion",
                    "fix_strategy_tag": "judge_code_vs_test",
                    "cross_file": False,
                    "strategy": "oracle_enhance_first",
                    "prompt_hint": "run oracle enhancer before fixing",
                },
                {
                    "error_category": "assertion",
                    "fix_strategy_tag": "judge_code_vs_test",
                    "cross_file": False,
                    "strategy": "raw_llm_fix",
                    "prompt_hint": "let LLM decide raw",
                },
            ],
            "outcomes": [
                {
                    "error_category": "assertion",
                    "fix_strategy_tag": "judge_code_vs_test",
                    "cross_file": False,
                    "strategy": "raw_llm_fix",
                    "success": False,
                    "task_id": "t1",
                },
                {
                    "error_category": "assertion",
                    "fix_strategy_tag": "judge_code_vs_test",
                    "cross_file": False,
                    "strategy": "raw_llm_fix",
                    "success": False,
                    "task_id": "t2",
                },
                {
                    "error_category": "assertion",
                    "fix_strategy_tag": "judge_code_vs_test",
                    "cross_file": False,
                    "strategy": "oracle_enhance_first",
                    "success": True,
                    "task_id": "t3",
                },
                {
                    "error_category": "assertion",
                    "fix_strategy_tag": "judge_code_vs_test",
                    "cross_file": False,
                    "strategy": "oracle_enhance_first",
                    "success": True,
                    "task_id": "t4",
                },
            ],
        }
        path = _write_bank(bank, tmp)
        # 同签名两条精确匹配，oracle_enhance_first 成功率 100% vs raw_llm_fix 0%
        result = select_strategy("assertion", "judge_code_vs_test", cross_file=False, path=path)
        assert result is not None
        assert result["strategy"] == "oracle_enhance_first"


def test_select_strategy_no_outcomes_preserves_order() -> None:
    """无 outcome 数据（冷启动）时，匹配优先级不变（按 strategies 列表顺序取首个命中）。"""
    from src.tools.strategy_bank import select_strategy

    with tempfile.TemporaryDirectory() as tmp:
        bank = {
            "strategies": [
                {
                    "error_category": "runtime",
                    "fix_strategy_tag": None,
                    "cross_file": False,
                    "strategy": "alpha",
                    "prompt_hint": "hint A",
                },
                {
                    "error_category": "runtime",
                    "fix_strategy_tag": None,
                    "cross_file": False,
                    "strategy": "beta",
                    "prompt_hint": "hint B",
                },
            ],
            "outcomes": [],
        }
        path = _write_bank(bank, tmp)
        # 无 outcome → 全权重 1.0 → 按列表顺序取第一个命中（alpha）
        result = select_strategy("runtime", None, cross_file=False, path=path)
        assert result is not None
        assert result["strategy"] == "alpha"


def test_select_strategy_mixed_outcomes_weighting() -> None:
    """outcome 成功率 50% vs 100% → 100% 优先；无 outcome 的策略不惩罚（权重 1.0）。"""
    from src.tools.strategy_bank import select_strategy

    with tempfile.TemporaryDirectory() as tmp:
        bank = {
            "strategies": [
                {
                    "error_category": "runtime",
                    "fix_strategy_tag": None,
                    "cross_file": False,
                    "strategy": "half_reliably",
                    "prompt_hint": "h1",
                },
                {
                    "error_category": "runtime",
                    "fix_strategy_tag": None,
                    "cross_file": False,
                    "strategy": "never_tested",
                    "prompt_hint": "h2",
                },
                {
                    "error_category": "runtime",
                    "fix_strategy_tag": None,
                    "cross_file": False,
                    "strategy": "fully_relied",
                    "prompt_hint": "h3",
                },
            ],
            "outcomes": [
                # half_reliably: 1 success / 1 fail = 50%
                {
                    "error_category": "runtime",
                    "fix_strategy_tag": None,
                    "cross_file": False,
                    "strategy": "half_reliably",
                    "success": True,
                    "task_id": "a",
                },
                {
                    "error_category": "runtime",
                    "fix_strategy_tag": None,
                    "cross_file": False,
                    "strategy": "half_reliably",
                    "success": False,
                    "task_id": "b",
                },
                # fully_relied: 1 success / 0 fail = 100%
                {
                    "error_category": "runtime",
                    "fix_strategy_tag": None,
                    "cross_file": False,
                    "strategy": "fully_relied",
                    "success": True,
                    "task_id": "c",
                },
                # never_tested: 无 outcome → 权重 1.0
            ],
        }
        path = _write_bank(bank, tmp)
        # 权重：fully_relied=1.0, never_tested=1.0（无 outcome 不惩罚）, half_reliably=0.5
        # 排序：fully_relied 或 never_tested（均 1.0）优先；half_reliably 垫底
        result = select_strategy("runtime", None, cross_file=False, path=path)
        assert result is not None
        # 1.0 权重的两条里，sorted 稳定排序保持原始顺序 → fully_relied（列表中靠后但 1.0 打平）
        # 保守：不断言具体哪条 1.0 胜出（稳定排序按原序），只断言 half_reliably 不胜出
        assert result["strategy"] != "half_reliably"
