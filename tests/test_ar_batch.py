"""AR 批次（2026-10-07 第十五轮审查续三）锁定测试。

覆盖三项自主执行项：
- AR1 hypothesis extras 缺口：G18/T5 的 SpecIR→Hypothesis 策略编译与
  AN4 属性模板路线同以 hypothesis 为执行底座，此前仅 requirements.txt
  声明、pyproject/setup.py 的 extras 无入口——现补入 [formal] 并锁双源
  一致（test_packaging 奇偶守卫之上再加内容断言）；
- AR2 README 双语"已知失败"行的 CI 矩阵声称勘误：矩阵自 2026-09-28 起
  为 3.12/3.13/3.14，"3.12/3.14" 陈旧写法不得残留，且与 BASELINE
  python_ci_matrix 交叉一致；
- AR3 prereg 双语结构奇偶锁：zh/en 的二级/三级标题数与 bash 命令块数
  相等（check_bilingual_docs 只查配对存在与日期，不查结构奇偶——本锁
  防单侧增删节造成内容级漂移；2026-10-07 实测 13/3/9 三项相等）。
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PYPROJECT = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
SETUP_PY = (PROJECT_ROOT / "setup.py").read_text(encoding="utf-8")
REQUIREMENTS_TXT = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
README_ZH = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
README_EN = (PROJECT_ROOT / "README.en.md").read_text(encoding="utf-8")
PREREG_ZH = (PROJECT_ROOT / "docs" / "preregistration.md").read_text(encoding="utf-8")
PREREG_EN = (PROJECT_ROOT / "docs" / "preregistration.en.md").read_text(encoding="utf-8")


class TestHypothesisFormalExtra:
    """AR1：hypothesis 属性测试底座进入 [formal] extras（双源一致）。"""

    def test_pyproject_formal_contains_hypothesis(self) -> None:
        """pyproject [formal] 同时含 z3-solver 与 hypothesis。"""
        formal = PYPROJECT["project"]["optional-dependencies"]["formal"]
        joined = " ".join(formal)
        assert "z3-solver" in joined
        assert "hypothesis" in joined

    def test_setup_py_formal_matches_pyproject(self) -> None:
        """setup.py shim 的 formal extra 与 pyproject 同内容（非 PEP 517
        回退路径一致；test_packaging 奇偶守卫之外的显式内容锁）。"""
        assert '"formal": ["z3-solver>=4.12.0", "hypothesis>=6.100.0"]' in SETUP_PY

    def test_requirements_txt_source_unchanged(self) -> None:
        """开发/CI 环境来源 requirements.txt 仍声明 hypothesis==（不被
        extras 补齐动作移除或改版）。"""
        assert re.search(r"^hypothesis==[0-9.]+$", REQUIREMENTS_TXT, re.M)


class TestReadmeCiMatrixClaim:
    """AR2：README 双语 CI 矩阵声称与 BASELINE python_ci_matrix 一致。"""

    def test_matrix_claim_matches_baseline(self) -> None:
        """双语均写全三档矩阵，且与 BASELINE.yaml 的 python_ci_matrix 逐项
        一致；陈旧两档声称（原句"CI 3.12/3.14 全绿"）不得残留——注意断言
        锚定原句语境而非裸子串：最近改动行的勘误文本"3.12/3.14→…"含
        该子串属合法历史引用（AQ 批同类教训的复现与修正）。"""
        baseline = (PROJECT_ROOT / "BASELINE.yaml").read_text(encoding="utf-8")
        match = re.search(r"python_ci_matrix:\s*\[(.+?)\]", baseline)
        assert match, "BASELINE.yaml 缺 python_ci_matrix 节"
        versions = sorted(v.strip().strip('"') for v in match.group(1).split(","))
        assert versions == ["3.12", "3.13", "3.14"]
        expected = "3.12/3.13/3.14"
        assert expected in README_ZH
        assert expected in README_EN
        for text in (README_ZH, README_EN):
            assert "CI 3.12/3.14 全绿" not in text
            assert "CI 3.12/3.14 all green" not in text


class TestPreregBilingualStructureParity:
    """AR3：prereg zh/en 结构奇偶（标题层级与命令块数量一致）。"""

    @staticmethod
    def _structure(text: str) -> tuple[int, int, int]:
        """提取 (二级标题数, 三级标题数, bash 命令块数)。"""
        return (
            len(re.findall(r"^## ", text, re.M)),
            len(re.findall(r"^### ", text, re.M)),
            len(re.findall(r"^```bash", text, re.M)),
        )

    def test_zh_en_structure_equal(self) -> None:
        """zh/en 结构计数逐项相等（当前实测 13/3/9；单侧增删节即红）。"""
        zh = self._structure(PREREG_ZH)
        en = self._structure(PREREG_EN)
        assert zh == en
        # 非退化守卫：三项计数均非零（防止两边同时删空仍相等）
        assert zh[0] >= 10 and zh[1] >= 3 and zh[2] >= 5
