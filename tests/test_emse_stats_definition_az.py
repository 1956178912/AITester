"""AZ 轮（2026-10-21）统计定义修正回归锁（第三方审查 F01/F02）。

锁定五件事：
1. 真批次四组对比按标准定义复算——Cohen's g 用 effectsize 口径
   （|n10-n01|/(2(n10+n01))，范围 0–0.5），精确二项尾不再被 1e-12
   epsilon 抬高（113/0 参考值 1.925929944387236e-34）；
2. 受保护归档 emse_stats_extensions_20261016 一字未动（sha256 常量）；
3. 新工件 emse_stats_extensions_20261021 与当前 build_report 逐位一致，
   且 SHA256SUMS 自校验；
4. reproduce 零 LLM 链同时校验历史归档与重发工件；
5. 引用面（paper / EMSE skeleton / X 轮复核）不再引用 2g 旧值。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from experiments import emse_stats_extensions as ext

REPO = Path(__file__).resolve().parent.parent
OLD_DIR = REPO / "experiments" / "results" / "emse_stats_extensions_20261016"
NEW_DIR = REPO / "experiments" / "results" / "emse_stats_extensions_20261021"

OLD_JSON_SHA = "785edd76b81f4c4ba87319eea5f7c319b911b27bcdc47685442b06737756f021"
OLD_README_SHA = "9762d9ae3a0d427ed1e49250308ff7324c775819027e9b72fee6ecd26cd85599"

# label -> (n10, n01, 标准 g, 精确 p)
EXPECTED: dict[str, tuple[int, int, float, float]] = {
    "rp02_aitester_vs_df": (12, 80, 0.3695652173913043, 1.715599535972955e-13),
    "rp02_df_vs_plain_llm": (113, 0, 0.5, 1.925929944387236e-34),
    "e6_aitester_vs_df": (2, 24, 0.4230769230769231, 1.049041748046875e-05),
    "e4_aitester_vs_df": (0, 14, 0.5, 0.0001220703125),
}


def _sha256(path: Path) -> str:
    """返回文件 SHA256 十六进制摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sums(directory: Path) -> dict[str, str]:
    """解析 `<sha>  <name>` 形式的 SHA256SUMS。"""
    out: dict[str, str] = {}
    for line in (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split("  ", 1)
            out[name] = digest
    return out


def _load_reproduce_module():
    """按路径加载 scripts/reproduce_zero_llm.py（scripts 不是包）。"""
    path = REPO / "scripts" / "reproduce_zero_llm.py"
    spec = importlib.util.spec_from_file_location("reproduce_zero_llm_az", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def report() -> dict:
    return ext.build_report()


@pytest.mark.unit
class TestRealBatchReadings:
    """真批次四组对比按修正定义读数（0.54s 级，零 LLM）。"""

    @pytest.mark.parametrize("label", sorted(EXPECTED))
    def test_corrected_definitions(self, report: dict, label: str) -> None:
        n10, n01, g, p = EXPECTED[label]
        cmp = report["comparisons"][label]
        assert (cmp["n10_a_only"], cmp["n01_b_only"]) == (n10, n01)
        assert cmp["cohens_g"] == pytest.approx(g, abs=1e-15)
        assert cmp["mcnemar_exact_p"] == pytest.approx(p, rel=1e-9)

    def test_g_never_exceeds_half(self, report: dict) -> None:
        for cmp in report["comparisons"].values():
            assert 0.0 <= cmp["cohens_g"] <= 0.5


@pytest.mark.unit
class TestProtectedArchive:
    """历史归档只读：本轮不得重写 20261016 的 JSON / README。"""

    def test_known_hashes_unchanged(self) -> None:
        assert _sha256(OLD_DIR / "STATS_EXTENSIONS.json") == OLD_JSON_SHA
        assert _sha256(OLD_DIR / "README.md") == OLD_README_SHA

    def test_sums_file_still_verifies(self) -> None:
        for name, digest in _sums(OLD_DIR).items():
            assert _sha256(OLD_DIR / name) == digest


@pytest.mark.unit
class TestReissuedArtifact:
    """重发工件：与当前代码逐位一致、可自校验。"""

    def test_default_out_dir_points_to_reissue(self) -> None:
        assert getattr(ext, "DEFAULT_OUT_DIR", None) == "experiments/results/emse_stats_extensions_20261021"

    def test_json_matches_build_report(self, report: dict) -> None:
        art = json.loads((NEW_DIR / "STATS_EXTENSIONS.json").read_text(encoding="utf-8"))
        assert art["comparisons"] == report["comparisons"]
        assert art["arms"] == report["arms"]

    def test_sums_cover_exactly_two_files_and_verify(self) -> None:
        sums = _sums(NEW_DIR)
        assert set(sums) == {"STATS_EXTENSIONS.json", "README.md"}
        for name, digest in sums.items():
            assert _sha256(NEW_DIR / name) == digest

    def test_readme_prints_standard_g_and_corrected_tails(self) -> None:
        md = (NEW_DIR / "README.md").read_text(encoding="utf-8")
        for cell in ("| 0.370 |", "| 0.423 |", "| 0.500 |"):
            assert cell in md
        for p_cell in ("1.716e-13", "1.926e-34", "1.049e-05", "0.0001221"):
            assert p_cell in md
        assert "0.739" not in md
        assert "1.073e-12" not in md
        assert "1.931e-12" not in md


@pytest.mark.unit
class TestReproduceWiring:
    """零 LLM 复算链：历史归档校验 + 重发工件校验，两条都在。"""

    def test_checksum_dirs_include_both_generations(self) -> None:
        mod = _load_reproduce_module()
        assert "experiments/results/emse_stats_extensions_20261016" in mod._CHECKSUM_DIRS
        assert "experiments/results/emse_stats_extensions_20261021" in mod._CHECKSUM_DIRS


@pytest.mark.unit
class TestRendererCaliber:
    """渲染口径须写明标准 g 尺度与无 epsilon 的精确尾。"""

    def test_caliber_lines(self, report: dict) -> None:
        md = ext.render_markdown(report)
        assert "2*(n10+n01)" in md
        assert "0–0.5" in md
        assert "无 1e-12 epsilon 容差" in md

    def test_artifact_history_note(self, report: dict) -> None:
        md = ext.render_markdown(report)
        assert "20261016" in md
        assert "历史值" in md


@pytest.mark.unit
class TestCitationPropagation:
    """2g 旧值不得继续出现在论文 / 投稿骨架；历史复核要有日期化勘误。"""

    def test_paper_uses_standard_g(self) -> None:
        # BZ 轮：paper/ 与 *.typ 按 .gitignore:119-120 双盲纪律不入库
        # （公开 clone 无论文稿）——本锁只能在论文在场的环境执行；缺席时
        # 显式 skip 并点名原因，不折叠成通过，也不折叠成失败。
        paper = REPO / "paper" / "draft.typ"
        if not paper.exists():
            pytest.skip("paper/draft.typ 不入库（.gitignore:119 双盲纪律）——本锁仅在论文在场环境执行")
        text = paper.read_text(encoding="utf-8")
        assert "g = 0.370" in text
        assert "g = 0.739" not in text

    def test_submission_skeleton_uses_standard_g(self) -> None:
        # BZ 轮：投稿骨架按 .gitignore:124（学术文件，local use only）不入库；
        # 同 paper 的口径——缺席显式 skip 并点名原因。
        skeleton = REPO / "docs" / "emse" / "EMSE_SUBMISSION_SKELETON_2026-10-16.md"
        if not skeleton.exists():
            pytest.skip(
                "EMSE_SUBMISSION_SKELETON_2026-10-16.md 不入库（.gitignore:124 学术文件纪律）——本锁仅在骨架在场环境执行"
            )
        text = skeleton.read_text(encoding="utf-8")
        assert "g=0.370" in text
        assert "g=0.37–0.50" in text
        assert "g=0.739" not in text
        assert "g=0.74-1.00" not in text

    def test_x_round_review_has_dated_errata(self) -> None:
        text = (REPO / "docs" / "reviews" / "X_ROUND_ZERO_LLM_VERIFICATION_2026-10-19.md").read_text(encoding="utf-8")
        assert "AZ 轮日期化勘误（2026-10-21" in text
        assert "0.3696" in text
