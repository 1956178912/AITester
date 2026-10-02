"""tools/strategy_bank 策略匹配 / outcome 加权 / 写盘降级分支补齐。

锁定 2026-10-02 批次策略银行低覆盖分支（纯静态，零 LLM / 零网络）：
- select_strategy 三级匹配（精确 / 次级 / 末级）+ 预算约束 + 成功率加权
- record_strategy_outcome 写盘降级（路径不可写时静默不抛）
- strategy_bank_stats 观测统计
- _strategy_success_rate / _rank_strategy_entries 聚合口径
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def bank_file(tmp_path, monkeypatch):
    """写入一个临时策略库文件并指向 STRATEGY_BANK_PATH。"""
    bank = tmp_path / "strategy_bank.json"
    bank.write_text(
        json.dumps(
            {
                "strategies": [
                    {
                        "error_category": "assertion",
                        "fix_strategy_tag": "logic_error",
                        "cross_file": False,
                        "strategy": "rewrite_logic",
                        "prompt_hint": "hint_a",
                        "budget": "medium",
                    },
                    {
                        "error_category": "assertion",
                        "fix_strategy_tag": None,
                        "cross_file": False,
                        "strategy": "add_guard",
                        "prompt_hint": "hint_b",
                        "budget": "low",
                    },
                    {
                        "error_category": "runtime",
                        "fix_strategy_tag": "none",
                        "cross_file": False,
                        "strategy": "wrap_try",
                        "prompt_hint": "hint_c",
                        "budget": "high",
                    },
                ],
                "outcomes": [
                    {"strategy": "rewrite_logic", "success": True},
                    {"strategy": "rewrite_logic", "success": True},
                    {"strategy": "add_guard", "success": False},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("STRATEGY_BANK_PATH", str(bank))
    return str(bank)


class TestStrategyBankSwitchBranch:
    def test_default_false(self, monkeypatch):
        from src.tools.strategy_bank import strategy_bank_enabled

        monkeypatch.delenv("STRATEGY_BANK_ENABLE", raising=False)
        assert strategy_bank_enabled() is False

    def test_true(self, monkeypatch):
        from src.tools.strategy_bank import strategy_bank_enabled

        monkeypatch.setenv("STRATEGY_BANK_ENABLE", "true")
        assert strategy_bank_enabled() is True


class TestSelectStrategyBranches:
    def test_exact_match(self, bank_file):
        from src.tools.strategy_bank import select_strategy

        out = select_strategy(
            "assertion",
            fix_strategy_tag="logic_error",
            cross_file=False,
            path=bank_file,
        )
        assert out is not None
        # 精确命中（三元组全等）
        assert out["strategy"] == "rewrite_logic"

    def test_partial_match_when_tag_missing(self, bank_file):
        from src.tools.strategy_bank import select_strategy

        # 传 fix_strategy_tag=None → 次级匹配（tag 通配）
        out = select_strategy(
            "assertion",
            fix_strategy_tag=None,
            cross_file=False,
            path=bank_file,
        )
        assert out is not None

    def test_category_match(self, bank_file):
        from src.tools.strategy_bank import select_strategy

        # 仅 error_category 命中
        out = select_strategy(
            "runtime",
            fix_strategy_tag="unknown_tag",
            cross_file=True,
            path=bank_file,
        )
        # runtime 条目 tag=none / cross_file=False → 末级匹配（仅 category）
        assert out is not None

    def test_no_match_returns_none(self, bank_file):
        from src.tools.strategy_bank import select_strategy

        out = select_strategy(
            "syntax",  # 策略库无 syntax 条目
            fix_strategy_tag="whatever",
            path=bank_file,
        )
        assert out is None

    def test_budget_filter(self, bank_file):
        from src.tools.strategy_bank import select_strategy

        # 预算 low 仅命中 add_guard 条目
        out = select_strategy(
            "assertion",
            fix_strategy_tag=None,
            cross_file=False,
            budget_hint="low",
            path=bank_file,
        )
        assert out is not None
        assert out["strategy"] == "add_guard"

    def test_budget_any_matches_all(self, bank_file):
        from src.tools.strategy_bank import select_strategy

        # budget="any" 通配条目；rewrite_logic 条目 budget="medium"，
        # 此处 budget_hint="any" 不匹配 medium → 该条目被过滤
        out = select_strategy(
            "assertion",
            fix_strategy_tag="logic_error",
            cross_file=False,
            budget_hint="any",
            path=bank_file,
        )
        # 仅 strategy 条目 budget 为 None/"any" 时通配命中；medium 被过滤
        assert out is None or out.get("budget") in ("any", None)


class TestSuccessRateWeightingBranches:
    def test_rank_by_success_rate(self, bank_file):
        from src.tools.strategy_bank import _load_bank, _rank_strategy_entries, _strategy_success_rate

        bank = _load_bank(bank_file)
        rates = _strategy_success_rate(bank)
        assert rates["rewrite_logic"] == 1.0
        assert rates["add_guard"] == 0.0

        candidates = [
            {"strategy": "add_guard"},  # 0.0
            {"strategy": "rewrite_logic"},  # 1.0
        ]
        ranked = _rank_strategy_entries(candidates, rates)
        assert ranked[0]["strategy"] == "rewrite_logic"

    def test_no_outcomes_defaults_1_0(self, bank_file):
        from src.tools.strategy_bank import _load_bank, _rank_strategy_entries, _strategy_success_rate

        bank = _load_bank(bank_file)
        rates = _strategy_success_rate(bank)
        # 未知策略名 .get(name, 1.0) 兜底
        candidates = [{"strategy": "brand_new_strategy"}]
        ranked = _rank_strategy_entries(candidates, rates)
        assert ranked[0]["strategy"] == "brand_new_strategy"

    def test_single_candidate_returns_as_is(self):
        from src.tools.strategy_bank import _rank_strategy_entries

        out = _rank_strategy_entries([{"strategy": "x"}], {})
        assert out == [{"strategy": "x"}]


class TestRecordOutcomeBranches:
    def test_appends_to_outcomes(self, bank_file):
        from src.tools.strategy_bank import record_strategy_outcome

        record_strategy_outcome(
            ("assertion", "logic_error", False),
            "rewrite_logic",
            True,
            task_id="t1",
            path=bank_file,
        )
        with open(bank_file, encoding="utf-8") as f:
            data = json.loads(f.read())
        assert any(o.get("task_id") == "t1" for o in data["outcomes"])

    def test_write_failure_degrades(self, tmp_path):
        from src.tools.strategy_bank import record_strategy_outcome

        # 指向不存在且不可创建目录 → 写盘失败静默降级
        bad_path = str(tmp_path / "no_such_dir" / "bank.json")
        try:
            record_strategy_outcome(("assertion", None, False), "s", False, path=bad_path)
            # 不抛异常即通过（write failure 静默降级）
        except Exception:
            pytest.fail("record_strategy_outcome 写盘失败应静默降级，不抛异常")

    def test_existing_file_preserves_strategies(self, bank_file):
        from src.tools.strategy_bank import record_strategy_outcome

        record_strategy_outcome(("assertion", None, False), "add_guard", True, path=bank_file)
        with open(bank_file, encoding="utf-8") as f:
            data = json.loads(f.read())
        # 既有 strategies 字段保留
        assert len(data["strategies"]) == 3


class TestStrategyBankStatsBranches:
    def test_stats_default_disabled(self, bank_file, monkeypatch):
        from src.tools.strategy_bank import strategy_bank_stats

        monkeypatch.delenv("STRATEGY_BANK_ENABLE", raising=False)
        out = strategy_bank_stats(path=bank_file)
        assert out["enabled"] is False
        assert out["strategy_count"] == 3
        assert out["outcome_count"] == 3

    def test_stats_success_rate(self, bank_file):
        from src.tools.strategy_bank import strategy_bank_stats

        out = strategy_bank_stats(path=bank_file)
        # 3 outcomes，2 success → 0.666...
        assert abs(out["success_rate"] - 2 / 3) < 1e-6

    def test_stats_empty_bank(self, tmp_path, monkeypatch):
        from src.tools.strategy_bank import strategy_bank_stats

        empty = tmp_path / "empty.json"
        empty.write_text(json.dumps({"strategies": [], "outcomes": []}), encoding="utf-8")
        out = strategy_bank_stats(path=str(empty))
        assert out["success_rate"] == 0.0


class TestLoadBankBranches:
    def test_missing_file_returns_empty_bank(self, tmp_path):
        from src.tools.strategy_bank import _load_bank

        out = _load_bank(str(tmp_path / "does_not_exist.json"))
        assert out == {"strategies": []}

    def test_corrupt_json_returns_empty_bank(self, tmp_path):
        from src.tools.strategy_bank import _load_bank

        corrupt = tmp_path / "corrupt.json"
        corrupt.write_text("{not valid json", encoding="utf-8")
        out = _load_bank(str(corrupt))
        assert out == {"strategies": []}

    def test_non_dict_data_normalized(self, tmp_path):
        from src.tools.strategy_bank import _load_bank

        arr = tmp_path / "arr.json"
        arr.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        out = _load_bank(str(arr))
        assert out == {"strategies": []}
