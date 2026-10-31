"""H1 统计分析脚本的纯函数锁（预注册 §3.1/§3.2/§4）。

锁三件事：
1. ``detection_rate=None`` 的行必须从配对分母剔除，**不得记 0**
   （预注册 §3.1 明文禁止；把挂起行算作未检出会系统性压低检出率）；
2. McNemar 单侧精确检验与 BH-FDR 的数值口径（判定表直接消费这两个值）；
3. 判定表三分支的阈值边界（+20pp / +5pp / ROPE 0.90）不得漂移。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.h1_payload_analysis import (  # noqa: E402
    bh_fdr,
    detection_map,
    one_sided_mcnemar,
    verdict,
)


def _batch(rows: list[dict]) -> dict:
    return {"results": {"aitester": {"details": rows}}}


class TestDetectionMap:
    def test_none_rows_excluded_not_zero(self) -> None:
        batch = _batch(
            [
                {"task_id": "a", "detection_rate": 1.0},
                {"task_id": "b", "detection_rate": 0.0},
                {"task_id": "c", "detection_rate": None},
            ]
        )
        mapping, none_rows = detection_map(batch)
        assert mapping == {"a": True, "b": False}
        assert none_rows == 1
        assert "c" not in mapping, "None 行必须从分母剔除，不能记成 False"

    def test_missing_baseline_raises(self) -> None:
        """基线名缺失必须报错，而不是静默返回空表（空表会把操纵检查算成 0% 检出）。"""
        # 注意：U3 守卫按 `pytest.raises` 字面形态扫描——不得使用
        # `import pytest as _pytest` 别名（守卫 AST 扫描不识别别名，
        # 会被判为零断言用例，CI U3 门禁红）。
        with pytest.raises(KeyError):
            detection_map({"results": {}}, baseline="plain_llm_df")


class TestMcNemarOneSided:
    def test_ties_return_one(self) -> None:
        assert one_sided_mcnemar(0, 0) == 1.0
        assert one_sided_mcnemar(4, 4) == 1.0

    def test_all_discordant_in_one_direction(self) -> None:
        # 6 个不一致对全部偏向 ①：单侧 p = (1/2)^6
        assert one_sided_mcnemar(6, 0) == 1 / 64

    def test_direction_symmetric(self) -> None:
        assert one_sided_mcnemar(1, 5) == one_sided_mcnemar(5, 1)


class TestBhFdr:
    def test_single_contrast_is_identity(self) -> None:
        assert bh_fdr([0.03]) == [0.03]

    def test_monotone_and_bounded(self) -> None:
        adjusted = bh_fdr([0.01, 0.04, 0.03])
        assert all(0.0 <= p <= 1.0 for p in adjusted)
        assert adjusted[0] <= adjusted[1] and adjusted[0] <= adjusted[2]


class TestVerdictThresholds:
    def test_positive_claim_requires_both(self) -> None:
        assert verdict(20.0, 0.049, 0.0) == "H1 成立"
        assert verdict(19.9, 0.001, 0.0) == "indeterminate"
        assert verdict(25.0, 0.051, 0.0) == "indeterminate"

    def test_refutation_requires_rope(self) -> None:
        assert verdict(5.0, 0.9, 0.90) == "H1 否证"
        assert verdict(5.0, 0.9, 0.89) == "indeterminate"
        assert verdict(5.1, 0.9, 0.99) == "indeterminate"
