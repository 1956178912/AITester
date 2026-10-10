"""experiments/trusted_verification.py 单元测试（弃权调整后通过率）。"""

from experiments.trusted_verification import arm_trusted_metrics


def _row(passed: bool, **signals) -> dict:
    r: dict = {"passed": passed}
    r.update(signals)
    return r


class TestArmTrustedMetrics:
    def test_abstain_strips_untrusted_pass(self):
        rows = [
            _row(True, test_regenerated_pass_unverified=True),  # 弃权（假通过）
            _row(True),  # 可信通过
            _row(False),  # 失败
        ]
        m = arm_trusted_metrics(rows)
        assert m["passed"] == 2
        assert m["abstained"] == 1
        assert m["trusted_pass"] == 1
        # 自洽：弃权 + 可信通过 = passed
        assert m["abstained"] + m["trusted_pass"] == m["passed"]

    def test_all_passed_abstained(self):
        rows = [_row(True, patch_evidence_level="none") for _ in range(3)]
        m = arm_trusted_metrics(rows)
        assert m["passed"] == 3
        assert m["abstained"] == 3
        assert m["trusted_pass"] == 0
        assert m["trusted_pass_rate_pct"] == 0.0

    def test_failed_rows_not_counted_as_abstain(self):
        # 失败行即使命中弃权信号（如 patch_evidence_level=none），也不算"不可信通过"
        rows = [_row(False, patch_evidence_level="none")]
        m = arm_trusted_metrics(rows)
        assert m["passed"] == 0
        assert m["abstained"] == 0
        assert m["trusted_pass"] == 0

    def test_empty_rows(self):
        m = arm_trusted_metrics([])
        assert m["total"] == 0
        assert m["trusted_pass_rate_pct"] is None

    def test_over_red_signal_triggers_abstain(self):
        rows = [_row(True, specificity_gate_verdict="over_red")]
        m = arm_trusted_metrics(rows)
        assert m["abstained"] == 1
        assert m["trusted_pass"] == 0
