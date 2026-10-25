"""scripts/reproduce_zero_llm.py 结构契约（EMSE Open Science 复制包编排器）。

锁定零 LLM 复算链的命令集完整性与基本执行语义：
- L0 命令集覆盖论文主数字复算入口（统计扩展 / 口径矩阵 / 引用核验）；
- 每条命令为 (非空名, 非空 argv, 正 tail 行数) 结构；
- `_run` 以本解释器执行并捕获输出尾；
- `_CHECKSUM_DIRS` 为相对 experiments/results/ 的目录。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module():
    path = REPO_ROOT / "scripts" / "reproduce_zero_llm.py"
    spec = importlib.util.spec_from_file_location("reproduce_zero_llm", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mod():
    return _load_module()


def test_command_lists_well_formed(mod):
    """每条命令为 (非空名, 非空 argv 列表, 正 tail 行数, 前提探针 | None)。"""
    for name, argv, tail, probe in mod._L0_COMMANDS + mod._L1_COMMANDS:
        assert isinstance(name, str) and name.strip()
        assert isinstance(argv, list) and argv
        assert all(isinstance(a, str) and a for a in argv)
        assert isinstance(tail, int) and tail > 0
        assert probe is None or callable(probe)  # v0.8.0：源工件缺席探针


def test_l0_commands_cover_key_numbers(mod):
    """L0 命令集覆盖论文主数字复算入口（统计扩展 / 口径矩阵 / 引用核验）。"""
    joined = " ".join(a for _, argv, _, _ in mod._L0_COMMANDS for a in argv)
    assert "emse_stats_extensions" in joined
    assert "emse_stats_report" in joined
    assert "check_citations.py" in joined
    assert "mutation-correlation" in joined


def test_checksum_dirs_are_relative(mod):
    """SHA256SUMS 校验目录为相对 experiments/results/ 的相对路径。"""
    assert mod._CHECKSUM_DIRS
    for d in mod._CHECKSUM_DIRS:
        assert d.startswith("experiments/results/")


def test_run_trivial_captures_tail(mod):
    """_run 以本解释器执行并捕获输出尾。"""
    rc, tail = mod._run(["-c", "print('repro-ok')"])
    assert rc == 0
    assert "repro-ok" in tail


def test_report_paths_inside_results(mod):
    """报告落盘路径位于 experiments/results/ 下。"""
    assert str(mod.REPORT_MD).startswith(str(REPO_ROOT / "experiments" / "results"))
    assert str(mod.REPORT_JSON).startswith(str(REPO_ROOT / "experiments" / "results"))


# ─── reproduce.sh 数据集分支（A02，2026-10-18 第三方审查 P1）─────────────────────
# 评审证据：REPLICATION.md:49 / docs/INDEX.md 推荐
# `reproduce.sh --dataset synthetic --full` 作为主批复现入口，但脚本无 synthetic
# 分支，未知 --dataset 静默回退 examples——实际跑 3 任务示例集，"主批复现"
# 承诺落空。本节锁定：synthetic 分支真实参数透传 + 未知数据集 fail-closed。


class TestReproduceShDatasetBranch:
    """`reproduce.sh` 的数据集分支静态契约（不执行含 LLM 的基准步骤）。"""

    SCRIPT = REPO_ROOT / "reproduce.sh"
    BENCH_ENTRY = "experiments/run_benchmark.py"

    @pytest.fixture()
    def script(self) -> str:
        return self.SCRIPT.read_text(encoding="utf-8")

    def test_script_syntax_is_valid(self):
        """bash -n 语法检查（静态可验证性的第一道）。"""
        import shutil
        import subprocess

        bash = shutil.which("bash")
        if bash is None:  # pragma: no cover - 无 bash 的 Windows 环境
            pytest.skip("无 bash，跳过 reproduce.sh 语法检查")
        proc = subprocess.run([bash, "-n", str(self.SCRIPT)], capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr

    def test_synthetic_branch_exists_and_normalizes_alias(self, script: str):
        """synthetic 分支存在且 synth 别名归一（不再落入未知数据集分支）。"""
        assert 'synthetic|synth) DATASET="synthetic"' in script
        assert "examples|swe_bench)" in script

    def test_unknown_dataset_fails_closed(self, script: str):
        """未知数据集必须报错退出，不得再回退 examples。"""
        assert 'error "未知数据集: ${DATASET}（支持: examples | swe_bench | synthetic' in script
        # 历史回退语句不得回归（不静默替换数据集）
        assert "回退到 examples" not in script
        assert 'warn "未知数据集' not in script
        # 只在合法分支内使用 examples 默认值，不存在"未知→examples"的重赋值
        assert script.count('DATASET="examples"') == 1

    def test_unknown_dataset_actually_exits_nonzero(self):
        """行为验证：未知 --dataset 在任何环境/LLM 步骤前立即退出。"""
        import shutil
        import subprocess

        bash = shutil.which("bash")
        if bash is None:  # pragma: no cover
            pytest.skip("无 bash")
        proc = subprocess.run(
            [bash, str(self.SCRIPT), "--dataset", "definitely-not-a-dataset"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(REPO_ROOT),
        )
        assert proc.returncode != 0
        assert "未知数据集" in (proc.stdout + proc.stderr)

    def test_full_synthetic_matches_main_batch_entry(self, script: str):
        """--full synthetic 默认 = 主批入口参数：87 任务 / max-pattern-repeat 2 /
        seed 42 / 三臂（aitester, plain_llm, plain_llm_df）。"""
        assert "TASK_COUNT=87" in script
        assert "MAX_PATTERN_REPEAT=2" in script
        assert 'SEED="42"' in script
        assert 'BASELINES="aitester,plain_llm,plain_llm_df"' in script

    def test_real_arguments_are_passed_through_to_run_benchmark(self, script: str):
        """synthetic 参数（--task-count / --max-pattern-repeat / --seed）必须拼进
        run_benchmark 调用（不是只算不传）。"""
        assert "TASK_COUNT_ARG=" in script
        assert "MAX_PATTERN_REPEAT_ARG=" in script
        assert "SEED_ARG=" in script
        bench_call = script[script.index(self.BENCH_ENTRY) :]
        assert "$TASK_COUNT_ARG" in bench_call
        assert "$MAX_PATTERN_REPEAT_ARG" in bench_call
        assert "$SEED_ARG" in bench_call
        # 真实参数名必须出现在 run_benchmark 的 CLI 选项中（脚本→入口口径一致）
        entry = (REPO_ROOT / "experiments" / "run_benchmark.py").read_text(encoding="utf-8")
        for flag in ("--task-count", "--max-pattern-repeat", "--seed"):
            assert flag in entry
