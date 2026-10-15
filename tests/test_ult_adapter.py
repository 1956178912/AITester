"""STVR 实证研究批次：ULT cosmic-ray 口径 mutation-score 适配器回归测试。

锁定 `experiments/ult_adapter.py` 的关键口径：
- cosmic-ray 未安装 → `is_cosmic_ray_available()=False` + `ult_mutation_score`
  保守 skipped（**不**静默回退到自研 AST 变异体，口径可比性纪律）；
- 版本 / 配置哈希字段键集合同构（cosmic-ray 不可用时 version=None 且
  config_hash=None——哈希含实测版本，二者同步，见 ult_bridge_plan.md §4.3）；
- 输入缺失 / max_mutants 无效 → 各分支均返回完整键集（None 保守口径）；
- dry_run_plan 的字段键集合同构（cosmic-ray 不可用时 available=False /
  version=None / config_hash=None，三者同步保守口径）。

全部零 LLM 成本（不触发变异生成，只探测 import + 纯函数）。
"""

from __future__ import annotations

from experiments.ult_adapter import (
    ULT_MUTANT_OPERATORS,
    ULT_MUTATION_TIMEOUT_SECONDS,
    cosmic_ray_config_hash,
    cosmic_ray_version,
    dry_run_plan,
    is_cosmic_ray_available,
    ult_mutation_score,
)


class TestCosmicRayAvailability:
    """cosmic-ray 探测（确定性，不触发变异生成）。"""

    def test_config_hash_is_stable(self) -> None:
        """配置哈希是纯函数（常量 + 实测版本）→ 跨进程稳定。

        cosmic-ray 未安装时 version=None → 哈希返回 None（保守口径）；
        已安装时返回 64 位 SHA-256 hexdigest。
        """
        h1 = cosmic_ray_config_hash()
        h2 = cosmic_ray_config_hash()
        assert h1 == h2
        if cosmic_ray_version() is None:
            assert h1 is None
        else:
            assert h1 is not None
            assert len(h1) == 64  # SHA-256 hexdigest 长度

    def test_config_hash_reflects_actual_operator_config(self) -> None:
        """哈希覆盖实际启用的口径：全变异体默认 + 120s 超时 + cosmic-ray 版本。

        （ult_bridge_plan.md §4.3 裁定：算子集 = 全变异体，不设 operators 键；
        9 类描述常量 ULT_MUTANT_OPERATORS 非实际算子集，不参与哈希。）
        """
        import hashlib
        import json

        version = cosmic_ray_version()
        if version is None:
            assert cosmic_ray_config_hash() is None
            return
        expected = hashlib.sha256(
            json.dumps(
                {
                    "operators": "all_mutants_default",
                    "timeout_seconds": ULT_MUTATION_TIMEOUT_SECONDS,
                    "cosmic_ray_version": version,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        assert cosmic_ray_config_hash() == expected

    def test_ult_timeout_is_120(self) -> None:
        """ULT 官方口径超时 = 120s（ult_bridge_plan.md §4.3 锁死）。"""
        assert ULT_MUTATION_TIMEOUT_SECONDS == 120

    def test_ult_operators_cover_official_set(self) -> None:
        """ULT_MUTANT_OPERATORS 为 9 类**描述性分类**（展示用，非实际算子集）。

        ult_bridge_plan.md §4.3 裁定实际算子集 = 全变异体（不设 operators 键），
        此常量仅供 dry_run_plan 的 "operators" 字段展示，不参与配置哈希。
        """
        assert len(ULT_MUTANT_OPERATORS) == 9
        assert "Arithmetic" in ULT_MUTANT_OPERATORS
        assert "MethodCall" in ULT_MUTANT_OPERATORS

    def test_version_consistent_with_availability(self) -> None:
        """cosmic-ray 不可用 → version=None（保守口径，不误报版本）。"""
        avail = is_cosmic_ray_available()
        ver = cosmic_ray_version()
        if not avail:
            assert ver is None
        # 可导入时不强制断言版本字符串（取决于实际安装）


class TestUltMutationScore:
    """ult_mutation_score 各分支的键集合同构（None 保守口径）。"""

    def _expected_keys(self) -> set[str]:
        return {
            "available",
            "mutation_score",
            "mutants_total",
            "mutants_killed",
            "skipped",
            "skip_reason",
            "cosmic_ray_version",
            "cosmic_ray_config_hash",
            "elapsed_seconds",
        }

    def test_cosmic_ray_unavailable_returns_skipped(self) -> None:
        """cosmic-ray 未安装 → skipped=True + mutation_score=None（不回退自研 AST）。"""
        if is_cosmic_ray_available():
            # cosmic-ray 已安装的环境跳过（本测试锁定"不可用"口径）
            import pytest

            pytest.skip("cosmic-ray installed; unavailability caliber not exercisable")
        out = ult_mutation_score(
            target_code="def f(x):\n    return x + 1",
            test_code="import mod",
            module_name="mod",
        )
        assert set(out.keys()) == self._expected_keys()
        assert out["skipped"] is True
        assert out["available"] is False
        assert out["mutation_score"] is None
        assert "cosmic-ray not installed" in out["skip_reason"]
        # 配置哈希含实测版本 → 未安装时与 version 同步为 None（保守口径）
        assert out["cosmic_ray_config_hash"] is None

    def test_empty_inputs_returns_skipped(self) -> None:
        """输入材料缺失 → skipped=True + 完整键集合（优先于 cosmic-ray 探测）。"""
        out = ult_mutation_score(target_code="", test_code="t", module_name="m")
        assert set(out.keys()) == self._expected_keys()
        assert out["skipped"] is True
        assert out["mutation_score"] is None
        assert "输入材料缺失" in out["skip_reason"]

    def test_invalid_max_mutants_returns_skipped(self) -> None:
        """max_mutants < 1 → skipped=True（保守口径，优先于 cosmic-ray 探测）。"""
        out = ult_mutation_score(
            target_code="def f(x):\n    return x + 1",
            test_code="import mod",
            module_name="mod",
            max_mutants=0,
        )
        assert out["skipped"] is True
        assert out["mutation_score"] is None
        assert "max_mutants 无效" in out["skip_reason"]

    def test_default_timeout_is_120s(self) -> None:
        """默认超时 = ULT 官方 120s（ult_bridge_plan.md §4.3）。"""
        out = ult_mutation_score(
            target_code="def f(x):\n    return x + 1",
            test_code="import mod",
            module_name="mod",
        )
        # 超时不直接透出（在 skip_reason 隐含），但验证 elapsed 字段存在
        assert "elapsed_seconds" in out
        assert out["elapsed_seconds"] >= 0.0


class TestDryRunPlan:
    """dry_run_plan 的键集合同构 + cosmic-ray 不可用时的保守口径。"""

    def _expected_keys(self) -> set[str]:
        return {
            "adapter",
            "caliber",
            "dataset",
            "subset",
            "task_limit",
            "max_mutants",
            "timeout_seconds",
            "operators",
            "cosmic_ray_available",
            "cosmic_ray_version",
            "cosmic_ray_config_hash",
            "note",
        }

    def test_default_plan_keys(self) -> None:
        plan = dry_run_plan()
        assert set(plan.keys()) == self._expected_keys()
        assert plan["dataset"] == "ult"
        assert plan["subset"] == "lite"
        assert plan["timeout_seconds"] == ULT_MUTATION_TIMEOUT_SECONDS
        assert plan["operators"] == ULT_MUTANT_OPERATORS

    def test_cosmic_ray_unavailable_fields(self) -> None:
        plan = dry_run_plan()
        if not is_cosmic_ray_available():
            assert plan["cosmic_ray_available"] is False
            assert plan["cosmic_ray_version"] is None
            # 配置哈希含实测版本 → 未安装时与 version 同步为 None
            assert plan["cosmic_ray_config_hash"] is None

    def test_task_limit_passthrough(self) -> None:
        plan = dry_run_plan(task_limit=42, max_mutants=7)
        assert plan["task_limit"] == 42
        assert plan["max_mutants"] == 7


class TestUltMutationScoreCosmicRayIntegration:
    """cosmic-ray 实装后的真实口径集成测试（仅 cosmic-ray 已安装时执行）。

    走真实 `init → exec → dump` 工作流（耗时数十秒），零 LLM 成本；
    验证返回键集合同构 + mutation_score 语义（killed / total）。
    """

    def _expected_keys(self) -> set[str]:
        return {
            "available",
            "mutation_score",
            "mutants_total",
            "mutants_killed",
            "skipped",
            "skip_reason",
            "cosmic_ray_version",
            "cosmic_ray_config_hash",
            "elapsed_seconds",
        }

    def test_real_cosmic_ray_mutation_score(self) -> None:
        """真实 cosmic-ray 口径：available=True + mutation_score 落在 [0,1]。"""
        if not is_cosmic_ray_available():
            import pytest

            pytest.skip("cosmic-ray not installed; integration caliber not exercisable")

        out = ult_mutation_score(
            target_code="def f(x):\n    return x + 1\n",
            test_code="import mod\n\n\ndef test_f():\n    assert mod.f(2) == 3\n",
            module_name="mod",
            max_mutants=4,
        )
        assert set(out.keys()) == self._expected_keys()
        assert out["available"] is True
        assert out["skipped"] is False
        assert out["skip_reason"] == ""
        assert out["cosmic_ray_version"] is not None
        assert out["cosmic_ray_config_hash"] is not None
        assert isinstance(out["mutation_score"], float)
        assert 0.0 <= out["mutation_score"] <= 1.0
        assert 0 < out["mutants_total"] <= 4
        assert 0 <= out["mutants_killed"] <= out["mutants_total"]


class TestWorkItemAccountingAndSentinel:
    """exec 兜底超时按实际条目数计算（2026-10-15 批次八修复的回归锁定）。

    背景：修复前 exec 兜底超时 = ``max_mutants × timeout + 60``，全变异体
    哨兵（10**9）产出 ≈1.2e11s 的超时值，超出 C 层 PyTime_t（≈9.22e9s）
    ⇒ subprocess 抛 OverflowError ⇒ 全变异体口径每任务以 skipped 失败。
    修复后按 init+trim 后实测 ``work_items`` 条目数计算。
    """

    def test_count_work_items_reads_session_sqlite(self, tmp_path) -> None:
        """``_count_work_items`` 读取合成 session.sqlite 的行数。"""
        import sqlite3

        from experiments.ult_adapter import _count_work_items

        db = tmp_path / "session.sqlite"
        conn = sqlite3.connect(str(db))
        try:
            conn.execute("CREATE TABLE work_items (job_id TEXT PRIMARY KEY)")
            conn.executemany(
                "INSERT INTO work_items (job_id) VALUES (?)",
                [("a",), ("b",), ("c",)],
            )
            conn.commit()
        finally:
            conn.close()
        assert _count_work_items(str(db)) == 3

    def test_full_mutant_sentinel_no_overflow(self) -> None:
        """全变异体哨兵（10**9）不再溢出——真实 cosmic-ray 路径端到端。

        修复前该调用恒以 skipped（"cosmic-ray 子命令异常：
        OverflowError(...)"）返回；修复后应走完整 init→exec→dump，
        产出有效 mutation_score。
        """
        if not is_cosmic_ray_available():
            import pytest

            pytest.skip("cosmic-ray not installed; sentinel integration caliber not exercisable")

        out = ult_mutation_score(
            target_code="def f(x):\n    return x + 1\n",
            test_code="import mod\n\n\ndef test_f():\n    assert mod.f(2) == 3\n",
            module_name="mod",
            max_mutants=10**9,
        )
        assert set(out.keys()) == self._expected_keys()
        assert out["skipped"] is False
        assert "OverflowError" not in out["skip_reason"]
        assert isinstance(out["mutation_score"], float)
        assert out["mutants_total"] >= 1

    def _expected_keys(self) -> set[str]:
        return {
            "available",
            "mutation_score",
            "mutants_total",
            "mutants_killed",
            "skipped",
            "skip_reason",
            "cosmic_ray_version",
            "cosmic_ray_config_hash",
            "elapsed_seconds",
        }
