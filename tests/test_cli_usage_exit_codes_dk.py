"""DK 轮：CLI 用法错误 / 运行失败的退出码口径（诊断命令假绿 + 负数过滤静默破坏）。

修复前实测（真实 CLI，非 mock）：
- ``check-dataset no_such_dataset_xyz`` → rc=0：工厂按契约降级为 examples，
  诊断命令于是把「没校验到用户要的数据集」报成「全量质量检查通过」；
- ``check-dataset examples --limit=-5`` → rc=0：``tasks[:-5]`` 是 Python 负切片，
  静默改变语义（展示尾部而非前 N 个）；
- ``check-dataset`` 加载抛异常 → 打印错误但 rc=0（把失败报成成功）；
- ``check-dataset swe_bench`` 在数据未就位时 0 个任务 → 仍报「质量检查通过」；
- ``run``（无有效目标）/ ``--parallel 0`` → rc=1，与「任务失败」混淆；
- ``clean-venv-cache --max-age-days -5`` → rc=0 且删光全部缓存：负数过滤
  在 ``clear_venv_cache`` 里恒为真（``age_days > -5``），是静默破坏性语义。

本轮口径（与 click 用法错误口径一致，亦与 doctor/e2e_probe 已统一的 0/1/2 对齐）：
0 = 通过；1 = 运行期失败（数据集加载异常 / 零任务 / 任务失败）；
2 = 用法错误（未知数据集、非法数值、无有效目标）。
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from src.cli import app as cli_app


def _invoke(args: list[str]):
    return CliRunner().invoke(cli_app.cli, args)


# ─── check-dataset：未知数据集 / 非法 limit / 零任务 / 加载失败 ───────────────


class TestCheckDatasetUsageAndFailureCodes:
    def test_unknown_dataset_exits_2_and_names_supported(self):
        """未知数据集名是用法错误：rc=2，且把合法名称列出来，绝不报「通过」。"""
        r = _invoke(["check-dataset", "no_such_dataset_xyz"])
        assert r.exit_code == 2, r.output
        assert "未知数据集" in r.stderr
        assert "swe_bench" in r.output, "用法错误必须列出受支持的名称，用户才能直接改正"
        assert "质量检查通过" not in r.output

    def test_dataset_name_is_normalized_before_validation(self):
        """名称归一口径与工厂一致（大小写/连字符不敏感），合法别名照常执行。"""
        r = _invoke(["check-dataset", "EXAMPLES", "--limit", "0"])
        assert r.exit_code == 0, r.output
        assert "共加载 3 个任务" in r.output

    def test_negative_limit_exits_2(self):
        """--limit 负数是用法错误（Python 负切片会静默取尾部，语义完全不同）。"""
        r = _invoke(["check-dataset", "examples", "--limit=-5"])
        assert r.exit_code == 2, r.output
        assert "--limit" in r.stderr
        assert "── " not in r.output, "用法错误时不得进入详情打印"

    def test_zero_limit_is_legal_and_skips_details(self):
        """--limit 0 是显式「只看汇总」的合法请求（区别于负数的未定义语义）。"""
        r = _invoke(["check-dataset", "examples", "--limit", "0"])
        assert r.exit_code == 0, r.output
        assert "共加载 3 个任务" in r.output
        assert "── examples__" not in r.output

    def test_zero_tasks_exit_1_not_green(self, monkeypatch: pytest.MonkeyPatch):
        """加载到 0 个任务 ⇒ 什么都没校验，必须 rc=1 而不是「质量检查通过」。"""

        class _EmptyLoader:
            def __init__(self) -> None:
                self.tasks: list = []

        monkeypatch.setattr("src.datasets.dataset_loader.load_dataset", lambda *a, **k: _EmptyLoader())
        r = _invoke(["check-dataset", "swe_bench"])
        assert r.exit_code == 1, r.output
        assert "未加载到任何任务" in r.output
        assert "质量检查通过" not in r.output

    def test_load_exception_exits_1(self, monkeypatch: pytest.MonkeyPatch):
        """数据集加载抛异常是运行期失败：rc=1（此前打印错误后仍 rc=0）。"""

        def _boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("src.datasets.dataset_loader.load_dataset", _boom)
        r = _invoke(["check-dataset", "swe_bench"])
        assert r.exit_code == 1, r.output
        assert "数据集加载失败" in r.stderr

    def test_factory_graceful_degradation_preserved(self):
        """工厂的「未知名称降级为 InMemoryDataset」契约不变（只在 CLI 层拦）。"""
        from src.datasets.dataset_loader import InMemoryDataset, load_dataset

        assert isinstance(load_dataset("no_such_dataset_xyz"), InMemoryDataset)


# ─── 数据集名称：注册表唯一事实源 ───────────────────────────────────────────


class TestDatasetRegistrySingleSource:
    def test_available_names_derived_from_single_registry(self):
        """可用名称必须由注册表派生（手工维护的平行名单正是「工厂能加载、名单漏列」的来源）。"""
        from src.datasets import dataset_loader as dl

        registry = getattr(dl, "_DATASET_REGISTRY", None)
        assert isinstance(registry, dict) and registry, "数据集注册表应上提为模块级唯一事实源"
        assert dl.get_available_datasets() == sorted(set(registry) | {"synthetic", "synth"})
        for name in registry:
            assert dl.normalize_dataset_name(name) == name

    def test_registry_names_all_loadable(self):
        """注册表里每个名称都能被工厂解析（反过来锁住名单不指向不存在的分支）。"""
        from src.datasets.dataset_loader import get_available_datasets, normalize_dataset_name

        for name in get_available_datasets():
            assert normalize_dataset_name(name) == name


# ─── run：用法错误统一 rc=2 ────────────────────────────────────────────────


class TestRunUsageExitCodes:
    @pytest.mark.parametrize(
        "args",
        [
            (0, 3, 80.0, None),
            (1, 0, 80.0, None),
            (1, 3, -1.0, None),
            (1, 3, 100.5, None),
            (1, 3, 80.0, 0),
            (1, 3, float("nan"), None),
        ],
    )
    def test_validate_run_args_usage_errors_exit_2(self, args: tuple):
        """非法数值是用法错误：SystemExit.code == 2（nan 绕过了范围比较，单独锁）。"""
        with pytest.raises(SystemExit) as exc:
            cli_app._validate_run_args(*args)
        assert exc.value.code == 2

    def test_run_without_targets_exits_2(self):
        """没有有效目标文件是用法错误（此前 rc=1，与任务失败无法区分）。"""
        r = _invoke(["run"])
        assert r.exit_code == 2, r.output
        assert "没有有效的目标文件" in r.output

    def test_run_parallel_zero_exits_2(self, tmp_path):
        """命令体到 ``_validate_run_args`` 的接线口径：--parallel 0 → rc=2。"""
        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        r = _invoke(["run", str(target), "--parallel=0"])
        assert r.exit_code == 2, r.output
        assert "--parallel 必须大于 0" in r.stderr


# ─── clean-venv-cache：负数过滤是用法错误，且不得触碰缓存 ────────────────────


class TestCleanVenvCacheFilterValidation:
    @pytest.mark.parametrize("flag", ["--max-age-days", "--max-size-mb"])
    def test_negative_filter_exits_2_without_touching_cache(self, monkeypatch: pytest.MonkeyPatch, flag: str):
        """负数过滤恒真（``age_days > -5``），必须先拦在删除之前。"""
        calls: list[dict] = []
        monkeypatch.setattr(
            "src.tools.dependency.clear_venv_cache",
            lambda **kwargs: calls.append(kwargs) or {"removed": [], "failed": [], "kept": [], "freed_mb": 0.0},
        )
        r = _invoke(["clean-venv-cache", f"{flag}=-5"])
        assert r.exit_code == 2, r.output
        assert flag in r.stderr
        assert calls == [], "用法错误不得触发任何删除"

    def test_zero_filter_still_clears_explicitly(self, monkeypatch: pytest.MonkeyPatch):
        """0 是「全部过期」的显式语义（与两个过滤条件缺省等价），保持合法。"""
        calls: dict = {}

        def fake_clear(max_age_days=None, max_size_mb=None):
            calls.update(max_age_days=max_age_days, max_size_mb=max_size_mb)
            return {"removed": [], "failed": [], "kept": [], "freed_mb": 0.0}

        monkeypatch.setattr("src.tools.dependency.clear_venv_cache", fake_clear)
        r = _invoke(["clean-venv-cache", "--max-age-days=0"])
        assert r.exit_code == 0, r.output
        assert calls == {"max_age_days": 0, "max_size_mb": None}

    def test_list_only_still_validates_filters(self, monkeypatch: pytest.MonkeyPatch):
        """用法错误先于 --list-only 早返回：非法选项不能被只读分支吞掉。"""
        listed: list[int] = []
        monkeypatch.setattr("src.tools.dependency.list_venv_cache", lambda: listed.append(1) or [])
        r = _invoke(["clean-venv-cache", "--list-only", "--max-size-mb=-1"])
        assert r.exit_code == 2, r.output
        assert listed == []
