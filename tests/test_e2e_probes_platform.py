"""N-2 探针模块单元测试（零网络 / 零 LLM / 确定性）。

锁定三件事：
1. **探针注册契约**：`PROBES` 数量/命名/分组/LLM 标记/超时（≥12 个探针，
   4 个真 LLM 探针，其余零 LLM）；
2. **零 LLM 探针的真实语义**：预算 fail-closed / 注入检测 / 脱敏 / 事件总线 /
   配置坏值等纯本地探针直接执行断言（这些也是生产判定口径的 e2e 锁）；
3. **LLM/重依赖探针的断言逻辑**：用 mock 注入"真实调用会返回什么"，验证探针
   在**功能静默失效**（未命中/无 rag_stats/未 pinned/错误降级）时给出 fail/skip
   而不是静默 pass。

约束：全部用例不打真实网络、不调用真实 LLM；临时目录由探针自行清理。
"""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import pytest

from scripts.tools import e2e_probes_platform as probes
from scripts.tools.e2e_probe import Probe, ProbeOutcome

#: 4 个真 LLM 探针（每探针 ≤2 次真实调用；其余必须零 LLM）。
_EXPECTED_LLM_PROBES = {
    "budget-llm-stop",
    "cache-two-call-hit",
    "rag-workflow-stats",
    "observability-model-fingerprint",
}


class TestRegistryContract:
    """探针注册契约：数量/唯一性/分组/LLM 标记/超时。"""

    def test_at_least_12_probes(self) -> None:
        assert len(probes.PROBES) >= 12, f"探针数不足：{len(probes.PROBES)}"

    def test_all_entries_are_probe_instances(self) -> None:
        for probe in probes.PROBES:
            assert isinstance(probe, Probe), f"非 Probe 元素：{probe!r}"
            assert callable(probe.func)

    def test_unique_kebab_case_names(self) -> None:
        names = [probe.name for probe in probes.PROBES]
        assert len(names) == len(set(names)), f"探针名重复：{names}"
        for name in names:
            assert name == name.lower() and " " not in name and "_" not in name, f"命名非 kebab-case：{name}"

    def test_groups_are_platform_domains(self) -> None:
        expected_groups = {"budget", "cache", "rag", "security", "executor", "dataset", "observability"}
        actual = {probe.group for probe in probes.PROBES}
        assert actual <= expected_groups, f"出现未登记分组：{actual - expected_groups}"
        assert actual == expected_groups, f"功能分组缺项：{expected_groups - actual}"

    def test_llm_probe_set_exact(self) -> None:
        llm = {probe.name for probe in probes.PROBES if probe.requires_llm}
        assert llm == _EXPECTED_LLM_PROBES, f"LLM 探针集合漂移：{llm}"
        assert len(probes.PROBES) - len(llm) >= 16, "零 LLM 探针应 ≥16（保证 --all 零 LLM 子集覆盖）"

    def test_timeouts_positive_and_bounded(self) -> None:
        for probe in probes.PROBES:
            assert 0 < probe.timeout_s <= 600, f"{probe.name} timeout 越界：{probe.timeout_s}"
            assert probe.description, f"{probe.name} 缺 description"

    def test_every_probe_name_mentioned_in_module_docstring(self) -> None:
        doc = probes.__doc__ or ""
        for probe in probes.PROBES:
            assert probe.name in doc, f"模块 docstring 覆盖矩阵缺 {probe.name}"


class TestEnvHelper:
    def test_env_sets_and_restores(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("N2_E2E_TEST_KEY", raising=False)
        with probes._env(N2_E2E_TEST_KEY="on", N2_E2E_ABSENT=None):
            import os

            assert os.environ["N2_E2E_TEST_KEY"] == "on"
            assert "N2_E2E_ABSENT" not in os.environ
        import os

        assert "N2_E2E_TEST_KEY" not in os.environ
        assert "N2_E2E_ABSENT" not in os.environ

    def test_env_restores_previous_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("N2_E2E_TEST_KEY", "before")
        with probes._env(N2_E2E_TEST_KEY="during"):
            import os

            assert os.environ["N2_E2E_TEST_KEY"] == "during"
        import os

        assert os.environ["N2_E2E_TEST_KEY"] == "before"


class TestBudgetProbes:
    """预算类零 LLM 探针直接执行（生产判定口径 e2e 锁）。"""

    def test_cost_cap_probe_passes(self) -> None:
        outcome = probes.probe_budget_cost_cap()
        assert isinstance(outcome, ProbeOutcome)
        assert outcome.status == "pass", outcome.detail

    def test_invalid_fail_closed_probe_passes(self) -> None:
        outcome = probes.probe_budget_invalid_fail_closed()
        assert outcome.status == "pass", outcome.detail

    def test_batch_quota_probe_passes(self) -> None:
        outcome = probes.probe_budget_batch_quota()
        assert outcome.status == "pass", outcome.detail
        assert outcome.evidence["estimate"] == 968

    def test_cost_cap_probe_fails_when_limit_not_enforced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """负控：check_budget 恒 True（上限失效）时探针必须 fail 而非静默 pass。"""
        from src.budget import cost_budget

        monkeypatch.setattr(cost_budget, "check_budget", lambda *a, **k: True)
        outcome = probes.probe_budget_cost_cap()
        assert outcome.status == "fail", f"预算未生效却判 pass：{outcome.detail}"

    def test_invalid_probe_fails_when_bad_value_treated_as_unlimited(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.budget import cost_budget

        monkeypatch.setattr(cost_budget, "check_budget", lambda *a, **k: True)
        outcome = probes.probe_budget_invalid_fail_closed()
        assert outcome.status == "fail", outcome.detail


class TestCacheProbes:
    def test_disabled_probe_passes(self) -> None:
        outcome = probes.probe_cache_disabled()
        assert outcome.status == "pass", outcome.detail

    def test_semantic_index_probe_passes_with_deterministic_embedding(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """mock 嵌入后端（确定性向量），验证同义命中/无关未命中判定逻辑。"""

        def _fake_embed(text: str) -> list[float]:
            vec = [0.0] * 16
            for token in text.replace("，", " ").replace("？", " ").split():
                vec[hash(token) % 16] += 1.0
            return vec

        monkeypatch.setattr("src.utils.embedding_utils.embed_text", _fake_embed)
        outcome = probes.probe_cache_semantic_index()
        assert outcome.status == "pass", outcome.detail

    def test_semantic_index_probe_skips_when_embedding_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("src.utils.embedding_utils.embed_text", lambda text: None)
        outcome = probes.probe_cache_semantic_index()
        assert outcome.status == "skip", outcome.detail
        assert "降级" in outcome.detail

    def test_two_call_hit_probe_passes_with_mocked_agent(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """mock agent：第二次命中缓存 + usage 记账 → 探针 pass。"""
        from src.budget import token_usage

        class _FakeAgent:
            calls = 0

            def _call_llm_with_cache(self, user_message: str, max_retries: int = 1) -> str:
                self.calls += 1
                if self.calls == 1:  # 首次真实调用落盘缓存文件
                    cache_dir = token_usage_dir()
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    (cache_dir / "fake_cache.json").write_text("{}", encoding="utf-8")
                return "3"

        def token_usage_dir() -> Path:
            import os

            return Path(os.environ["AITESTER_LLM_CACHE_DIR"])

        fake_usage = types.SimpleNamespace(
            as_dict=lambda: {
                "llm_calls": 1,
                "cache_hits": 1,
                "cache_avoided_tokens": 24,
                "total_tokens": 24,
            }
        )
        monkeypatch.setattr(probes, "_make_tiny_agent", lambda: _FakeAgent())
        monkeypatch.setattr(token_usage, "get_usage", lambda: fake_usage)
        monkeypatch.setattr(probes, "_clear_llm_cache_state", lambda: None)
        outcome = probes.probe_cache_two_call_hit()
        assert outcome.status == "pass", outcome.detail

    def test_two_call_hit_probe_fails_when_second_call_misses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.budget import token_usage

        class _FakeAgent:
            def _call_llm_with_cache(self, user_message: str, max_retries: int = 1) -> str:
                return "3"

        fake_usage = types.SimpleNamespace(
            as_dict=lambda: {"llm_calls": 2, "cache_hits": 0, "cache_avoided_tokens": 0, "total_tokens": 48}
        )
        monkeypatch.setattr(probes, "_make_tiny_agent", lambda: _FakeAgent())
        monkeypatch.setattr(token_usage, "get_usage", lambda: fake_usage)
        monkeypatch.setattr(probes, "_clear_llm_cache_state", lambda: None)
        outcome = probes.probe_cache_two_call_hit()
        assert outcome.status == "fail", outcome.detail


class TestRagProbes:
    def test_retriever_probe_passes_with_fake_retriever(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _FakeRetriever:
            def add_case(self, **kwargs: Any) -> None:
                return None

            def retrieve_test_cases(self, code: str, top_k: int = 2) -> list[dict[str, Any]]:
                return [{"test_code": "def test_add(): ...", "similarity": 0.91}]

        fake_module = types.ModuleType("src.graph.rag")
        fake_module.get_rag_retriever = lambda: _FakeRetriever()  # type: ignore[attr-defined]
        monkeypatch.setitem(__import__("sys").modules, "src.graph.rag", fake_module)
        outcome = probes.probe_rag_retriever()
        assert outcome.status == "pass", outcome.detail

    def test_retriever_probe_skips_when_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_module = types.ModuleType("src.graph.rag")
        fake_module.get_rag_retriever = lambda: None  # type: ignore[attr-defined]
        monkeypatch.setitem(__import__("sys").modules, "src.graph.rag", fake_module)
        outcome = probes.probe_rag_retriever()
        assert outcome.status == "skip", outcome.detail

    def test_workflow_stats_probe_passes_with_rag_stats(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fake_invoke(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], float]:
            return (
                {
                    "rag_stats": [{"kind": "test_cases", "results": 0, "max_similarity": None}],
                    "generated_test": "def test_add():\n    assert True\n",
                },
                1.2,
            )

        monkeypatch.setattr(probes, "invoke_workflow", _fake_invoke)
        outcome = probes.probe_rag_workflow_stats()
        assert outcome.status == "pass", outcome.detail

    def test_workflow_stats_probe_fails_when_rag_stats_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(probes, "invoke_workflow", lambda *a, **k: ({"generated_test": "x"}, 1.0))
        outcome = probes.probe_rag_workflow_stats()
        assert outcome.status == "fail", outcome.detail


class TestSecurityProbes:
    def test_injection_guard_probe_passes(self) -> None:
        outcome = probes.probe_security_injection_guard()
        assert outcome.status == "pass", outcome.detail

    def test_credential_scrub_probe_passes(self) -> None:
        outcome = probes.probe_security_credential_scrub()
        assert outcome.status == "pass", outcome.detail
        assert outcome.evidence["removed"], "探针应记录被剔除的假凭证键"

    def test_log_redaction_probe_passes(self) -> None:
        outcome = probes.probe_security_log_redaction()
        assert outcome.status == "pass", outcome.detail

    def test_kernel_sandbox_probe_passes_with_fake_exec(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        fake_cmd = ["sandbox-exec", "-p", "(version 1)(allow default)", "/bin/echo", "sandbox-e2e-ok"]
        from src.agents import kernel_sandbox

        monkeypatch.setattr(kernel_sandbox, "sandbox_supported", lambda: True)
        monkeypatch.setattr(
            kernel_sandbox,
            "describe_capabilities",
            lambda: {"platform": "darwin", "supported": True, "backends": ["seatbelt"], "notes": ""},
        )
        monkeypatch.setattr(
            kernel_sandbox,
            "build_sandbox_command",
            lambda *a, **k: (list(fake_cmd), {"platform": "darwin", "backend": "seatbelt", "supported": True}),
        )
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="sandbox-e2e-ok\n", stderr=""),
        )
        outcome = probes.probe_security_kernel_sandbox()
        assert outcome.status == "pass", outcome.detail

    def test_kernel_sandbox_probe_skips_when_unsupported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.agents import kernel_sandbox

        monkeypatch.setattr(kernel_sandbox, "sandbox_supported", lambda: False)
        monkeypatch.setattr(
            kernel_sandbox,
            "describe_capabilities",
            lambda: {"platform": "windows", "supported": False, "backends": [], "notes": ""},
        )
        outcome = probes.probe_security_kernel_sandbox()
        assert outcome.status == "skip", outcome.detail
        assert "unsupported" in outcome.detail or "无可用" in outcome.detail

    def test_kernel_sandbox_probe_detects_single_quote_regression(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """负控：profile 重新出现单引号 subpath（rc=65 缺陷）时探针必须 fail。"""
        from src.agents import kernel_sandbox

        monkeypatch.setattr(kernel_sandbox, "sandbox_supported", lambda: True)
        monkeypatch.setattr(
            kernel_sandbox,
            "describe_capabilities",
            lambda: {"platform": "darwin", "supported": True, "backends": ["seatbelt"], "notes": ""},
        )
        bad_profile = "(version 1)\n(deny default)\n(allow file-read* (subpath '/tmp'))\n"
        monkeypatch.setattr(
            kernel_sandbox,
            "build_sandbox_command",
            lambda *a, **k: (["sandbox-exec", "-p", bad_profile, "/bin/echo"], {"supported": True}),
        )
        outcome = probes.probe_security_kernel_sandbox()
        assert outcome.status == "fail", outcome.detail
        assert "单引号" in outcome.detail


class TestExecutorProbes:
    def test_local_probe_passes_with_fake_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            probes,
            "_run_trivial_executor",
            lambda **k: {"passed": True, "coverage": 100.0, "failed_cases": [], "output": "1 passed"},
        )
        outcome = probes.probe_executor_local()
        assert outcome.status == "pass", outcome.detail

    def test_local_probe_fails_when_executor_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            probes,
            "_run_trivial_executor",
            lambda **k: {
                "passed": False,
                "coverage": 0.0,
                "failed_cases": [],
                "output": "boom",
                "error_info": {"type": "x"},
            },
        )
        outcome = probes.probe_executor_local()
        assert outcome.status == "fail", outcome.detail

    def test_venv_probe_passes_with_fake_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            probes, "_run_trivial_executor", lambda **k: {"passed": True, "coverage": 100.0, "output": "ok"}
        )
        outcome = probes.probe_executor_venv()
        assert outcome.status == "pass", outcome.detail

    def test_docker_probe_asserts_explicit_degrade(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(probes.shutil, "which", lambda name: None)
        monkeypatch.setattr(
            probes,
            "_run_trivial_executor",
            lambda **k: {
                "passed": False,
                "output": "docker CLI 未安装",
                "error_info": {"type": "docker_unavailable", "message": "请安装 docker"},
            },
        )
        outcome = probes.probe_executor_docker_degrade()
        assert outcome.status == "pass", outcome.detail

    def test_docker_probe_skips_when_cli_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(probes.shutil, "which", lambda name: "/usr/bin/docker")
        outcome = probes.probe_executor_docker_degrade()
        assert outcome.status == "skip", outcome.detail

    def test_repo_verify_probe_passes_with_fake_executor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _FakeRepoExecutor:
            def __init__(self, **kwargs: Any) -> None:
                self.env_root = ""

            def verify(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
                return {
                    "passed": True,
                    "fail_to_pass": {"expected": 1, "passed": 1, "baseline_passed": 0},
                    "pass_to_pass": {"expected": 0, "passed": 0},
                    "output": "[FAIL_TO_PASS baseline] 0/1 passed\n[FAIL_TO_PASS after-llm-patch] 1/1 passed",
                }

        import src.agents.executor_repo as executor_repo

        monkeypatch.setattr(executor_repo, "RepoExecutor", _FakeRepoExecutor)
        outcome = probes.probe_executor_repo_verify()
        assert outcome.status == "pass", outcome.detail


class TestExecutorSandboxProbe:
    """N-2 追加：执行器内核沙箱探针（修复后真实 local+venv 执行）。"""

    def _fake_result(self, passed: bool) -> dict[str, Any]:
        return {
            "passed": passed,
            "coverage": 100.0 if passed else 0.0,
            "error_info": None if passed else {"type": "test_failure"},
            "output": "1 passed",
            "kernel_sandbox_obs": {"supported": True, "backend": "seatbelt"},
        }

    def test_probe_passes_with_fake_executor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.agents import kernel_sandbox

        monkeypatch.setattr(kernel_sandbox, "sandbox_supported", lambda: True)
        monkeypatch.setattr(probes, "_run_trivial_executor", lambda **k: self._fake_result(True))
        outcome = probes.probe_executor_kernel_sandbox()
        assert outcome.status == "pass", outcome.detail
        assert outcome.evidence["local"]["passed"] and outcome.evidence["venv"]["passed"]

    def test_probe_fails_when_executor_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.agents import kernel_sandbox

        monkeypatch.setattr(kernel_sandbox, "sandbox_supported", lambda: True)
        monkeypatch.setattr(probes, "_run_trivial_executor", lambda **k: self._fake_result(False))
        outcome = probes.probe_executor_kernel_sandbox()
        assert outcome.status == "fail", outcome.detail

    def test_probe_fails_when_sandbox_not_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """负控：obs.supported=False（静默裸跑）必须 fail 而非 pass。"""
        from src.agents import kernel_sandbox

        monkeypatch.setattr(kernel_sandbox, "sandbox_supported", lambda: True)
        result = self._fake_result(True)
        result["kernel_sandbox_obs"] = {"supported": False}
        monkeypatch.setattr(probes, "_run_trivial_executor", lambda **k: result)
        outcome = probes.probe_executor_kernel_sandbox()
        assert outcome.status == "fail", outcome.detail

    def test_probe_skips_when_platform_unsupported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.agents import kernel_sandbox

        monkeypatch.setattr(kernel_sandbox, "sandbox_supported", lambda: False)
        outcome = probes.probe_executor_kernel_sandbox()
        assert outcome.status == "skip", outcome.detail


class TestDatasetProbes:
    def _fake_dataset(self, size: int, task_ids: list[str] | None = None) -> Any:
        ids = task_ids if task_ids is not None else [f"quixbugs__t{index}" for index in range(size)]
        tasks = [
            types.SimpleNamespace(
                task_id=task_id,
                metadata={"fixed": "def f():\n    return 1\n", "test_cases": "def test_f(): ..."},
            )
            for task_id in ids
        ]
        return types.SimpleNamespace(size=size, tasks=tasks)

    def test_loaders_probe_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.datasets.dataset_loader as loader

        fake = {
            "quixbugs": self._fake_dataset(50, ["quixbugs__bitcount"]),
            "examples": self._fake_dataset(3, ["examples__a", "examples__b", "examples__c"]),
        }

        def _fake_load(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "synthetic":
                return self._fake_dataset(3, ["synthetic__a", "synthetic__b", "synthetic__c"])
            return fake[name]

        monkeypatch.setattr(loader, "load_dataset", _fake_load)
        outcome = probes.probe_dataset_loaders()
        assert outcome.status == "pass", outcome.detail
        assert outcome.evidence["sizes"]["quixbugs"] == 50

    def test_loaders_probe_skips_when_quixbugs_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.datasets.dataset_loader as loader

        monkeypatch.setattr(
            loader, "load_dataset", lambda name, *a, **k: self._fake_dataset(0 if name == "quixbugs" else 3)
        )
        outcome = probes.probe_dataset_loaders()
        assert outcome.status == "skip", outcome.detail

    def test_ult_probe_skips_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.datasets.dataset_loader as loader

        monkeypatch.setattr(loader, "load_dataset", lambda name, *a, **k: self._fake_dataset(0))
        outcome = probes.probe_dataset_ult()
        assert outcome.status == "skip", outcome.detail

    def test_ult_probe_passes_when_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.datasets.dataset_loader as loader

        monkeypatch.setattr(loader, "load_dataset", lambda name, *a, **k: self._fake_dataset(2, ["ult__a", "ult__b"]))
        outcome = probes.probe_dataset_ult()
        assert outcome.status == "pass", outcome.detail

    def test_decontamination_probe_passes(self) -> None:
        outcome = probes.probe_dataset_decontamination()
        assert outcome.status == "pass", outcome.detail

    def test_check_cli_probe_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(probes, "run_cmd", lambda *a, **k: (0, "ℹ ✓ 全量质量检查通过（50 个任务无加载问题）\n", ""))
        outcome = probes.probe_dataset_check_cli()
        assert outcome.status == "pass", outcome.detail
        assert outcome.evidence["checked_tasks"] == 50

    def test_check_cli_probe_fails_on_nonzero_rc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(probes, "run_cmd", lambda *a, **k: (2, "", "boom"))
        outcome = probes.probe_dataset_check_cli()
        assert outcome.status == "fail", outcome.detail


class TestObservabilityProbes:
    def test_trace_redaction_probe_passes(self) -> None:
        outcome = probes.probe_observability_trace_redaction()
        assert outcome.status == "pass", outcome.detail

    def test_event_bus_probe_passes(self) -> None:
        outcome = probes.probe_observability_event_bus()
        assert outcome.status == "pass", outcome.detail

    def test_model_fingerprint_probe_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_module = types.ModuleType("experiments.run_benchmark")
        fake_module.collect_model_fingerprint = lambda alias, cache=None: (  # type: ignore[attr-defined]
            {
                "requested_alias": alias,
                "returned_model": "deepseek-flash",
                "system_fingerprint": "abc",
                "probe_sha256": "deadbeef" * 8,
                "missing": [],
                "pinned": True,
                "alias_mismatch": False,
            }
        )
        monkeypatch.setitem(__import__("sys").modules, "experiments.run_benchmark", fake_module)
        from src.agents import llm_client

        monkeypatch.setattr(llm_client, "get_first_valid_model_name", lambda: "deepseek-flash")
        outcome = probes.probe_observability_model_fingerprint()
        assert outcome.status == "pass", outcome.detail

    def test_model_fingerprint_probe_fails_when_unpinned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_module = types.ModuleType("experiments.run_benchmark")
        fake_module.collect_model_fingerprint = lambda alias, cache=None: (  # type: ignore[attr-defined]
            {
                "requested_alias": alias,
                "returned_model": None,
                "system_fingerprint": None,
                "probe_sha256": None,
                "missing": ["returned_model"],
                "pinned": False,
                "error": "probe failed",
            }
        )
        monkeypatch.setitem(__import__("sys").modules, "experiments.run_benchmark", fake_module)
        from src.agents import llm_client

        monkeypatch.setattr(llm_client, "get_first_valid_model_name", lambda: "deepseek-flash")
        outcome = probes.probe_observability_model_fingerprint()
        assert outcome.status == "fail", outcome.detail


class TestLlmGating:
    """LLM 探针的离线语义：无配额时运行器应 skip（本模块只锁定标记与函数存在）。"""

    @pytest.mark.parametrize("name", sorted(_EXPECTED_LLM_PROBES))
    def test_llm_probe_declared_and_present(self, name: str) -> None:
        probe = next((item for item in probes.PROBES if item.name == name), None)
        assert probe is not None and probe.requires_llm is True
