"""STVR 实证研究批次：ULT cosmic-ray 口径 mutation-score 适配器回归测试。

锁定 `experiments/ult_adapter.py` 的关键口径：
- cosmic-ray 未安装 → `is_cosmic_ray_available()=False` + `ult_mutation_score`
  保守 skipped（**不**静默回退到自研 AST 变异体，口径可比性纪律）；
- 版本 / 配置哈希字段键集合同构（cosmic-ray 不可用时 version=None，
  但 config_hash 仍可算——配置常量与 cosmic-ray 安装无关）；
- 输入缺失 / max_mutants 无效 → 各分支均返回完整键集（None 保守口径）；
- dry_run_plan 的字段键集合同构（cosmic-ray 不可用时 available=False /
  version=None，但 config_hash 仍非 None）。

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
        """配置哈希是纯函数（常量 + 常量）→ 跨进程稳定。"""
        h1 = cosmic_ray_config_hash()
        h2 = cosmic_ray_config_hash()
        assert h1 == h2
        assert h1 is not None
        assert len(h1) == 64  # SHA-256 hexdigest 长度

    def test_config_hash_includes_ult_constants(self) -> None:
        """哈希覆盖 ULT_MUTATION_TIMEOUT_SECONDS + ULT_MUTANT_OPERATORS。"""
        import hashlib
        import json

        expected = hashlib.sha256(
            json.dumps(
                {"timeout": ULT_MUTATION_TIMEOUT_SECONDS, "operators": ULT_MUTANT_OPERATORS},
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        assert cosmic_ray_config_hash() == expected

    def test_ult_timeout_is_120(self) -> None:
        """ULT 官方口径超时 = 120s（ult_bridge_plan.md §4.3 锁死）。"""
        assert ULT_MUTATION_TIMEOUT_SECONDS == 120

    def test_ult_operators_cover_official_set(self) -> None:
        """ULT 官方 cosmic-ray 算子集（9 类，与 cosmic-ray 默认一致）。"""
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
        # 配置哈希仍可算（与 cosmic-ray 安装无关）
        assert out["cosmic_ray_config_hash"] is not None

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
            # 配置哈希仍可算
            assert plan["cosmic_ray_config_hash"] is not None

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
