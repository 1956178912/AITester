"""Z 轮（2026-10-19 第三方全量静态审查）配置/复现/可视化/JSON 回归锁（零 LLM）。

背景：审查报告 F03（venv 模板默认值覆盖代码默认）、F05（复现镜像挂载目录
前置条件不完整）、F06（可视化按文件名倒序静默选错数据集）、F19（复算输出写
裸 Infinity 非标准 JSON）。本文件以**静态工件断言 + tmp_path 行为测试**锁定：

1. F03：`.env.example` 活动值、README 中英文、API 参考中英文表的
   `EXECUTOR_USE_VENV` 默认值统一为 true（与 `config.py` 现行默认一致，R10
   起开启），`EXECUTOR_AUTO_INSTALL_DEPS` 仍为 false；
2. F05：`reproduce.sh` 提供 `REPRODUCE_SKIP_TESTS=1` 显式逃生（默认仍跑测试、
   保持 fail-closed），`Dockerfile.repro` / `.dockerignore` / `REPLICATION.md`
   明确挂载目录**同时是历史输入（Step 3 测试夹具）和输出**；
3. F06：`load_latest_result` 支持显式 `result_path` / `dataset` 前缀过滤，
   无匹配显式报错（不再回退全量倒序）；`main()` 支持 `--result` / `--dataset`；
   `reproduce.sh` Step 6 传 `--dataset "$DATASET"`；
4. F19：`recompute_outputs.json` 可被严格 JSON 解析（`parse_constant` 拒绝），
   不含 `Infinity` / `NaN` token；c=0 的 McNemar 块 `odds_ratio=None` + 状态
   说明；写盘 `allow_nan=False`；`SHA256SUMS` 与实际工件逐字节一致。

纪律：零 LLM、零网络；不写仓库工件（行为测试全部落 tmp_path）。
"""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]
_REVIEW_RECOMPUTE = REPO_ROOT / "docs" / "reviews" / "review_recompute"


def _text(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _table_row(text: str, key: str) -> list[str]:
    """取 Markdown 表格中首列为 `key` 的行（返回去首尾空段的单元格列表）。"""
    needle = f"| `{key}` |"
    for line in text.splitlines():
        if line.strip().startswith(needle):
            return [c.strip() for c in line.strip().strip("|").split("|")]
    raise AssertionError(f"未找到 `{key}` 的表格行")


def _env_active_value(text: str, key: str) -> str | None:
    """`.env` 模板中该键的**活动值**（首个非注释赋值行）；无则 None。"""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            return stripped.split("=", 1)[1].strip()
    return None


def _summary() -> dict[str, Any]:
    """最小合法 benchmark 汇总（visualize_results.main 可消费；与 B6 测试同构）。"""
    a_rows = [
        {
            "task_id": "t1",
            "detection_rate": 1.0,
            "false_fix_rate": 0.0,
            "repair_rate": 0.0,
            "passed": True,
            "coverage": 90.0,
        },
        {
            "task_id": "t2",
            "detection_rate": 0.0,
            "false_fix_rate": 0.0,
            "repair_rate": 0.0,
            "passed": False,
            "coverage": 80.0,
        },
        {
            "task_id": "t3",
            "detection_rate": 0.0,
            "false_fix_rate": 0.0,
            "repair_rate": 0.0,
            "passed": True,
            "coverage": 90.0,
        },
        {
            "task_id": "t4",
            "detection_rate": None,
            "false_fix_rate": 0.0,
            "repair_rate": 0.0,
            "passed": False,
            "coverage": 70.0,
        },
    ]
    b_rows = [
        {
            "task_id": "t1",
            "detection_rate": 1.0,
            "false_fix_rate": 0.0,
            "repair_rate": 0.0,
            "passed": True,
            "coverage": 90.0,
        },
        {
            "task_id": "t2",
            "detection_rate": 1.0,
            "false_fix_rate": 1.0,
            "repair_rate": 0.0,
            "passed": False,
            "coverage": 85.0,
        },
        {
            "task_id": "t3",
            "detection_rate": 0.0,
            "false_fix_rate": 0.0,
            "repair_rate": 0.0,
            "passed": False,
            "coverage": 75.0,
        },
        {
            "task_id": "t4",
            "detection_rate": 1.0,
            "false_fix_rate": 0.0,
            "repair_rate": 0.0,
            "passed": True,
            "coverage": 95.0,
        },
    ]
    meta = {
        "success_rate": 50.0,
        "passed_count": 2,
        "failure_count": 2,
        "avg_coverage": 90.0,
        "avg_iterations": 1.0,
        "avg_elapsed_seconds": 1.0,
        "total_time": 4.0,
        "total_functions": 4,
    }
    return {
        "dataset": "synthetic",
        "results": {
            "aitester": {**meta, "details": a_rows},
            "plain_llm_df": {**meta, "success_rate": 25.0, "passed_count": 1, "failure_count": 3, "details": b_rows},
        },
    }


# ─── F03：venv 模板默认值与代码/文档政策一致 ──────────────────────────────────


class TestF03VenvDefaultConsistency:
    """`.env.example` 的活动值不得覆盖 `config.py` 的 True 默认（F03/P1）。"""

    def test_env_example_active_value_matches_code_default(self) -> None:
        text = _text(".env.example")
        assert _env_active_value(text, "EXECUTOR_USE_VENV") == "true"
        assert _env_active_value(text, "EXECUTOR_AUTO_INSTALL_DEPS") == "false"
        # 旧注释口径（"两者默认 false"）不得回归——快速开始会 cp 模板覆盖代码默认
        assert "两者默认 false" not in text

    def test_config_py_default_is_true(self) -> None:
        # EG 轮（2026-10-27）：默认开启守卫迁到 opt-out 读取（坏值不再静默关沙箱）
        assert 'env_flag_opt_out("EXECUTOR_USE_VENV")' in _text("config.py")

    def test_quickstart_warning_still_states_default_on(self) -> None:
        # DD 轮（2026-10-26）文档重写：venv 默认开启的读者提示随「安装步骤」
        # 迁至 QUICKSTART.md，README 只保留快速开始链接；事实判据不变。
        text = _text("QUICKSTART.md")
        assert "EXECUTOR_USE_VENV" in text
        assert "默认开启" in text
        assert "R10" in text or "2026-09-30" in text

    @pytest.mark.parametrize(
        ("rel", "column"),
        [
            ("docs/api_reference.md", 2),
            ("docs/api_reference.en.md", 2),
        ],
    )
    def test_doc_tables_show_true_default(self, rel: str, column: int) -> None:
        cells = _table_row(_text(rel), "EXECUTOR_USE_VENV")
        assert cells[column] == "true", (rel, cells)


# ─── F05：复现镜像挂载目录 = 历史输入 + 输出；测试门显式逃生 ──────────────────


class TestF05ReproMountPrerequisites:
    """镜像不自含 experiments/results；空目录启动须显式跳过测试门（F05/P2）。"""

    def test_reproduce_has_explicit_skip_tests_escape(self) -> None:
        text = _text("reproduce.sh")
        # 只有显式 == "1" 才跳过（默认不设即照常跑测试）
        assert '[[ "${REPRODUCE_SKIP_TESTS:-0}" == "1" ]]' in text
        # 默认路径仍执行全量 pytest（跳过分支不得成为默认）
        assert "python -m pytest tests/ -v --tb=short" in text
        # 跳过时必须有醒目警告：缺测试门 + 结论不含测试验证
        assert "缺少测试门" in text
        assert "不含测试验证" in text

    def test_reproduce_keeps_fail_closed_semantics(self) -> None:
        text = _text("reproduce.sh")
        # U2 语义保持：测试失败默认 error 退出；宽容口径只能显式开启
        assert "单元测试失败" in text
        assert "REPRODUCE_ALLOW_TEST_FAILURES=1" in text

    @pytest.mark.parametrize("rel", ["Dockerfile.repro", ".dockerignore", "REPLICATION.md"])
    def test_mount_dual_role_documented(self, rel: str) -> None:
        text = _text(rel)
        assert "历史输入" in text, f"{rel} 未说明挂载目录是历史输入"
        assert "REPRODUCE_SKIP_TESTS" in text, f"{rel} 未说明空目录逃生开关"

    def test_dockerignore_keeps_results_excluded(self) -> None:
        lines = [ln.strip() for ln in _text(".dockerignore").splitlines()]
        # 镜像保持轻量：experiments/results 仍为活动排除项（不自包含历史归档）
        assert "experiments/results" in lines

    def test_reproduce_syntax_valid(self) -> None:
        bash = shutil.which("bash")
        if bash is None:  # pragma: no cover - 无 bash 的 Windows 环境
            pytest.skip("无 bash，跳过 reproduce.sh 语法检查")
        proc = subprocess.run([bash, "-n", str(REPO_ROOT / "reproduce.sh")], capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr


# ─── F06：可视化结果来源显式化（禁止文件名倒序静默猜测）───────────────────────


class TestF06VisualizeResultSource:
    """多数据集产物混存时，出图来源必须显式可判定（F06/P1）。"""

    @pytest.fixture()
    def vr(self):
        pytest.importorskip("matplotlib", reason="matplotlib 未安装（experiments.visualize_results 依赖）")
        return importlib.import_module("experiments.visualize_results")

    @staticmethod
    def _touch(dirpath: Path, name: str) -> Path:
        path = dirpath / name
        path.write_text(json.dumps({"name": name}), encoding="utf-8")
        return path

    def test_dataset_filter_beats_filename_order(self, vr, tmp_path: Path) -> None:
        """旧行为反例：'ult' 字典序压过 'synthetic'；--dataset 取本次数据集。"""
        self._touch(tmp_path, "benchmark_ult_20261017_110803.json")
        self._touch(tmp_path, "benchmark_synthetic_20261006_140906.json")
        # 无过滤（旧口径）会选中字典序更大的旧 ult 文件——问题复现
        assert vr.load_latest_result(str(tmp_path)).endswith("benchmark_ult_20261017_110803.json")
        # 显式 dataset 后选中 synthetic（即使其时间戳更早）
        picked = vr.load_latest_result(str(tmp_path), dataset="synthetic")
        assert picked.endswith("benchmark_synthetic_20261006_140906.json")

    def test_explicit_result_path_wins(self, vr, tmp_path: Path) -> None:
        self._touch(tmp_path, "benchmark_synthetic_20261006_140906.json")
        explicit = tmp_path / "custom_result.json"
        explicit.write_text(json.dumps({}), encoding="utf-8")
        picked = vr.load_latest_result(str(tmp_path), dataset="synthetic", result_path=str(explicit))
        assert picked == str(explicit)

    def test_explicit_path_missing_fails_closed(self, vr, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            vr.load_latest_result(str(tmp_path), result_path=str(tmp_path / "missing.json"))

    def test_dataset_prefix_mismatch_raises(self, vr, tmp_path: Path) -> None:
        self._touch(tmp_path, "benchmark_synthetic_20261006_140906.json")
        with pytest.raises(FileNotFoundError):
            vr.load_latest_result(str(tmp_path), dataset="swe_bench")

    def test_no_benchmark_files_never_falls_back(self, vr, tmp_path: Path) -> None:
        """无 benchmark_* 时不得回退全量 JSON 猜测（F06：禁止静默猜测）。"""
        (tmp_path / "swebench_20_summary.json").write_text("{}", encoding="utf-8")
        with pytest.raises(FileNotFoundError):
            vr.load_latest_result(str(tmp_path))

    def test_main_dataset_arg_uses_matching_result(
        self, vr, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "benchmark_ult_20261017_110803.json").write_text(json.dumps(_summary()), encoding="utf-8")
        (tmp_path / "benchmark_synthetic_20261006_140906.json").write_text(json.dumps(_summary()), encoding="utf-8")
        monkeypatch.setattr(
            sys,
            "argv",
            ["visualize_results.py", "--results-dir", str(tmp_path), "--dataset", "synthetic"],
        )
        vr.main()
        out = capsys.readouterr().out
        assert "benchmark_synthetic_20261006_140906.json" in out
        assert "benchmark_ult_20261017_110803.json" not in out
        assert (tmp_path / "charts" / "summary_stats.md").is_file()

    def test_main_result_arg_overrides_dataset(
        self, vr, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "benchmark_synthetic_20261006_140906.json").write_text(json.dumps(_summary()), encoding="utf-8")
        explicit = tmp_path / "benchmark_synthetic_20250101_000000.json"
        explicit.write_text(json.dumps(_summary()), encoding="utf-8")
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "visualize_results.py",
                "--results-dir",
                str(tmp_path),
                "--dataset",
                "synthetic",
                "--result",
                str(explicit),
            ],
        )
        vr.main()
        assert str(explicit) in capsys.readouterr().out

    def test_main_exposes_result_and_dataset_flags(self) -> None:
        source = _text("experiments/visualize_results.py")
        assert '"--result"' in source
        assert '"--dataset"' in source

    def test_reproduce_step6_passes_dataset(self) -> None:
        text = _text("reproduce.sh")
        assert 'python experiments/visualize_results.py --dataset "$DATASET"' in text
        # 旧的裸调用（无来源参数）不得回归
        assert "python experiments/visualize_results.py\n" not in text

    def test_script_runs_directly_without_pythonpath(self) -> None:
        """F06 执行前提：`python experiments/visualize_results.py` 直接运行必须能
        import `experiments.*`（reproduce.sh Step 6 的真实调用口径，此前
        sys.path[0]=experiments/ 导致 ModuleNotFoundError）。"""
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "experiments" / "visualize_results.py"), "--help"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        assert "--dataset" in proc.stdout


# ─── F19：非标准 JSON 输出修复（Infinity → null + 状态说明）───────────────────


class TestF19StrictJsonOutputs:
    """复算输出必须是标准 JSON，且 c=0 的 OR 语义显式化（F19/P2）。"""

    def test_outputs_are_strict_json(self) -> None:
        text = (_REVIEW_RECOMPUTE / "recompute_outputs.json").read_text(encoding="utf-8")

        def _reject(token: str) -> Any:
            raise AssertionError(f"非标准 JSON token: {token}")

        data = json.loads(text, parse_constant=_reject)
        assert "Infinity" not in text
        assert "NaN" not in text
        # c=0 的 C3：OR 无定义 → null + 状态说明；原始 b/c 计数保留
        c3 = data["claims"]["C3_df_vs_plain_llm_mcnemar"]
        assert c3["c_only_b"] == 0
        assert c3["odds_ratio"] is None
        assert "无定义" in c3["odds_ratio_note"]
        # 分母非零的块保持有限数值（不得一刀切成 null）
        assert data["claims"]["C2_aitester_vs_df_mcnemar"]["odds_ratio"] == 0.15
        assert data["claims"]["C4_e4_quixbugs"]["odds_ratio"] == 0.0
        # 有定义的块 note 为 null（schema 稳定，消费者可按固定键读取）
        assert data["claims"]["C2_aitester_vs_df_mcnemar"]["odds_ratio_note"] is None

    def test_script_serializes_strictly(self) -> None:
        source = _text("docs/reviews/review_recompute/recompute_core_claims.py")
        # 写盘 + stdout 双端点均 allow_nan=False
        assert source.count("allow_nan=False") >= 2
        assert '"odds_ratio": round(b / c, 3) if c else None' in source
        assert "odds_ratio_note" in source

    def test_sha256sums_cover_changed_artifacts(self) -> None:
        """脚本与输出都改了 → 清单必须同步（防工件漂移）。"""
        manifest = (_REVIEW_RECOMPUTE / "SHA256SUMS").read_text(encoding="utf-8")
        entries: dict[str, str] = {}
        for line in manifest.splitlines():
            if not line.strip():
                continue
            digest, name = line.split()
            entries[name] = digest
        assert {"recompute_core_claims.py", "recompute_outputs.json"} <= set(entries)
        for name, digest in entries.items():
            actual = hashlib.sha256((_REVIEW_RECOMPUTE / name).read_bytes()).hexdigest()
            assert actual == digest, f"{name} 的 SHA256 与清单不一致（工件已变但清单未同步）"
