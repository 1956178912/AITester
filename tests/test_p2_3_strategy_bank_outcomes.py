"""P2-3 ESDA Phase 2 回归测试（2026-10 批次）：
strategy_bank.record_strategy_outcome + select_strategy 成功率加权的
"在线积累 → 离线挖掘"闭环锁定。

锁定口径（与 strategy_bank.py 实现一致）：
1. record_strategy_outcome 纯追加（不改写已有 strategies / outcomes 字段）；
2. 写盘失败静默降级（不阻断调用方）；
3. 追加 outcome 后 select_strategy 的成功率排序生效（同签名多策略条目
   按历史成功率排前，无 outcome 条目权重 1.0 排前）。
"""

from __future__ import annotations

import json

from src.tools.strategy_bank import (
    _rank_strategy_entries,
    _strategy_success_rate,
    record_strategy_outcome,
    select_strategy,
)


def test_record_outcome_appends(tmp_path, monkeypatch):
    p = tmp_path / "bank.json"
    p.write_text(
        json.dumps({"strategies": [{"error_category": "assertion", "strategy": "add_assertion_probe"}]}, indent=2)
    )
    record_strategy_outcome(
        signature=("assertion", "logic_error", False),
        strategy="add_assertion_probe",
        success=True,
        task_id="t1",
        path=str(p),
    )
    record_strategy_outcome(
        signature=("assertion", "logic_error", False),
        strategy="add_assertion_probe",
        success=False,
        task_id="t2",
        path=str(p),
    )
    data = json.loads(p.read_text())
    assert len(data["outcomes"]) == 2
    assert data["outcomes"][0]["success"] is True
    assert data["outcomes"][0]["task_id"] == "t1"
    # strategies 字段未被改写（纯追加 outcomes）
    assert len(data["strategies"]) == 1


def test_record_outcome_missing_dir_creates(tmp_path, monkeypatch):
    p = tmp_path / "sub" / "bank.json"
    record_strategy_outcome(
        signature=("syntax", None, False),
        strategy="resample",
        success=True,
        task_id="t9",
        path=str(p),
    )
    data = json.loads(p.read_text())
    assert len(data["outcomes"]) == 1
    assert data["outcomes"][0]["strategy"] == "resample"


def test_success_rate_aggregation():
    bank = {
        "outcomes": [
            {"strategy": "A", "success": True},
            {"strategy": "A", "success": True},
            {"strategy": "A", "success": False},
            {"strategy": "B", "success": True},
            {"strategy": "C", "success": False},
        ]
    }
    rates = _strategy_success_rate(bank)
    assert rates["A"] == 2 / 3
    assert rates["B"] == 1.0
    assert rates["C"] == 0.0


def test_rank_by_success_rate():
    candidates = [
        {"strategy": "low_hit"},
        {"strategy": "high_hit"},
        {"strategy": "no_outcome"},
    ]
    rates = {"low_hit": 0.1, "high_hit": 0.9}
    ranked = _rank_strategy_entries(candidates, rates)
    # no_outcome 权重 1.0（.get 兜底）> high_hit 0.9 > low_hit 0.1
    assert [e["strategy"] for e in ranked] == ["no_outcome", "high_hit", "low_hit"]


def test_select_strategy_prefers_higher_success(tmp_path, monkeypatch):
    """同签名两条策略条目，outcomes 显示 B 成功率更高 → select 返回 B。"""
    p = tmp_path / "bank.json"
    p.write_text(
        json.dumps(
            {
                "strategies": [
                    {
                        "error_category": "assertion",
                        "fix_strategy_tag": "logic",
                        "cross_file": False,
                        "strategy": "A",
                        "prompt_hint": "hint-a",
                    },
                    {
                        "error_category": "assertion",
                        "fix_strategy_tag": "logic",
                        "cross_file": False,
                        "strategy": "B",
                        "prompt_hint": "hint-b",
                    },
                ],
                "outcomes": [
                    {"strategy": "A", "success": False},
                    {"strategy": "B", "success": True},
                    {"strategy": "B", "success": True},
                    {"strategy": "B", "success": True},
                ],
            },
            indent=2,
        )
    )
    # 清空缓存（同进程内多次 _load_bank 命中 mtime 缓存时取首值）
    import src.tools.strategy_bank as sb

    sb._bank_cache = None
    sb._bank_mtime = 0.0
    result = select_strategy(
        error_category="assertion",
        fix_strategy_tag="logic",
        cross_file=False,
        path=str(p),
    )
    assert result is not None
    assert result["strategy"] == "B"  # 3/3 成功率 > A 0/1


def test_select_strategy_no_outcomes_keeps_original_order(tmp_path):
    """无 outcomes 字段时（冷启动）候选条目权重全 1.0 → 保持原始匹配序。"""
    p = tmp_path / "bank.json"
    p.write_text(
        json.dumps(
            {
                "strategies": [
                    {"error_category": "runtime", "strategy": "first", "prompt_hint": "h1"},
                    {"error_category": "runtime", "strategy": "second", "prompt_hint": "h2"},
                ]
            }
        )
    )
    import src.tools.strategy_bank as sb

    sb._bank_cache = None
    sb._bank_mtime = 0.0
    result = select_strategy(error_category="runtime", path=str(p))
    assert result is not None
    assert result["strategy"] == "first"  # 无 outcome → 原始顺序，无重排
