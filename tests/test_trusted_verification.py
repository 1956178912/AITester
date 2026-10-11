"""experiments/trusted_verification.py 单元测试（弃权调整后通过率 + 分层报告）。"""

from experiments.trusted_verification import arm_trusted_metrics, build_report_by_repo


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

    def test_validated_and_filtered_pass(self):
        """验证层：有 gold 独立裁决的行计 validated，且 filtered_pass 要求弃权+验证双满足。"""
        rows = [
            _row(True, repo_verification={"passed": True}),  # 通过 + 验证（gold）
            _row(True),  # 通过但无验证证据
            _row(False),  # 失败
        ]
        m = arm_trusted_metrics(rows)
        assert m["passed"] == 2
        assert m["validated"] == 1
        # filtered_pass = passed ∧ ¬abstain ∧ validated → 仅第 1 行
        assert m["filtered_pass"] == 1

    def test_filtered_excludes_abstained(self):
        """弃权行即使有验证证据也不计 filtered_pass（双策略都要满足）。"""
        rows = [
            _row(True, test_regenerated_pass_unverified=True, repo_verification={"passed": True}),
            _row(True, repo_verification={"passed": True}),
        ]
        m = arm_trusted_metrics(rows)
        assert m["abstained"] == 1
        assert m["filtered_pass"] == 1
        # filtered 分母 = total - abstained = 1，分子 = 1 → 100%
        assert m["filtered_pass_rate_pct"] == 100.0

    def test_deterministic_repair_counts_as_validated(self):
        rows = [_row(True, deterministic_repair_status={"patch_produced": True})]
        m = arm_trusted_metrics(rows)
        assert m["validated"] == 1
        assert m["filtered_pass"] == 1

    def test_all_abstained_filtered_denominator_zero(self):
        """全部弃权时 filtered 分母为 0 → 保守 None。"""
        rows = [_row(True, patch_evidence_level="none") for _ in range(2)]
        m = arm_trusted_metrics(rows)
        assert m["abstained"] == 2
        assert m["filtered_pass_rate_pct"] is None


class TestBuildReportByRepo:
    def test_groups_by_repo(self, tmp_path):
        """按 repo 分层，逐组计算 trusted metrics。"""
        import json

        batch = {
            "results": {
                "aitester": {
                    "details": [
                        {"passed": True, "repo": "pandas", "repo_verification": {"passed": True}},
                        {"passed": False, "repo": "pandas"},
                        {"passed": True, "repo": "scrapy", "patch_evidence_level": "none"},
                    ]
                }
            }
        }
        p = tmp_path / "batch.json"
        p.write_text(json.dumps(batch), encoding="utf-8")
        report = build_report_by_repo(str(p))
        assert "aitester" in report
        by_repo = report["aitester"]
        assert set(by_repo) == {"pandas", "scrapy"}
        assert by_repo["pandas"]["total"] == 2
        assert by_repo["pandas"]["filtered_pass"] == 1
        assert by_repo["scrapy"]["total"] == 1
        assert by_repo["scrapy"]["abstained"] == 1

    def test_missing_repo_defaults_unknown(self, tmp_path):
        import json

        batch = {"results": {"arm": {"details": [{"passed": True}]}}}
        p = tmp_path / "b.json"
        p.write_text(json.dumps(batch), encoding="utf-8")
        report = build_report_by_repo(str(p))
        assert "unknown" in report["arm"]
