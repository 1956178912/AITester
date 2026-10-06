"""AJ 批次测试（2026-10-06 E4 数据前置 + 三实验就绪命令预置）。

覆盖：
- AJ1 QuixBugs 数据溯源登记：DATA_CARD 双语含已获取 commit
  （4257f44b…）与加载器冒烟口径（50 加载 / 41 gold 齐全）；
- AJ2 预注册三实验就绪命令齐全：E1（AH2）/ E2 / E4（AJ 批补）——
  E2 命令块必须含"--batches 白名单只选 E2 新批次"的去重陷阱警示
  （同种子重复跑"最新优先"折叠会把 gate 前/后口径错配）；
- AJ3 data/ 隔离守卫：data/quixbugs 不入 git（gitignore 生效——
  本地存在的克隆不得污染版本库）。

全部纯 stdlib / 零 LLM / 零网络 / 零子进程（数据存在性不做测试断言：
干净 checkout 无 data/，AJ1/AJ2 只锁文档登记）。
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

_COMMIT = "4257f44b0ff1181dedaedee6a447e133219fcebf"


class TestDataProvenanceRegistered:
    """AJ1：数据溯源已入卡（许可 + commit + 冒烟口径）。"""

    def test_zh_card_has_commit_and_smoke(self) -> None:
        text = (_ROOT / "docs" / "DATA_CARD.md").read_text(encoding="utf-8")
        assert _COMMIT in text
        assert "50 程序加载" in text
        assert "41 个 gold 三件套齐全" in text

    def test_en_card_has_commit_and_smoke(self) -> None:
        text = (_ROOT / "docs" / "DATA_CARD.en.md").read_text(encoding="utf-8")
        assert _COMMIT in text
        assert "50 programs" in text
        assert "41" in text


class TestPreregReadyCommands:
    """AJ2：三实验就绪命令齐全（批准 + 干净树 → 逐条可执行）。"""

    @staticmethod
    def _prereg(lang: str) -> str:
        name = "preregistration.md" if lang == "zh" else "preregistration.en.md"
        return (_ROOT / "docs" / name).read_text(encoding="utf-8")

    def test_e4_ready_command_present(self) -> None:
        for lang in ("zh", "en"):
            text = self._prereg(lang)
            assert "AITESTER_QUIXBUGS_DATA=data/quixbugs" in text
            assert "--dataset quixbugs" in text

    def test_e2_ready_command_present(self) -> None:
        for lang in ("zh", "en"):
            text = self._prereg(lang)
            assert "--max-pattern-repeat 2" in text
            assert "--pool-seeds" in text
            # 主终点通道计数一行命令
            assert "red_not_repaired" in text and "red_then_green" in text

    def test_e2_dedup_footgun_warning(self) -> None:
        """E2 统计命令必须警示"--batches 只选 E2 新批次"（去重折叠陷阱）。"""
        zh = self._prereg("zh")
        assert "--batches" in zh
        assert "只选 E2 新批次" in zh
        en = self._prereg("en")
        assert "must select only the new E2" in en

    def test_no_allow_dirty_anywhere(self) -> None:
        """三实验命令块均不得出现裸 --allow-dirty（预注册红线）。

        行级判定：每个 --allow-dirty 出现行必须是禁止性语境
        （中文含"不得"，英文含 never / do not）——逐行检查而非
        全文排除（replace 链对多语境变体脆弱）。
        """
        forbidden_markers = ("不得", "never", "do not", "Do not", "violate", "red line")
        for lang in ("zh", "en"):
            for lineno, line in enumerate(self._prereg(lang).splitlines(), 1):
                if "--allow-dirty" in line:
                    assert any(m in line for m in forbidden_markers), (
                        f"preregistration({lang}):{lineno} 出现非禁止语境的 --allow-dirty"
                    )


class TestDataIsolation:
    """AJ3：data/ 隔离（本地克隆不入版本库）。"""

    def test_gitignore_covers_data_dir(self) -> None:
        gi = (_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert any(line.strip() == "data/" for line in gi.splitlines())

    def test_quixbugs_not_tracked(self) -> None:
        """本地 data/quixbugs 存在时必须被 git 忽略（不存在则跳过——
        干净 checkout 场景）。"""
        d = _ROOT / "data" / "quixbugs"
        if not d.exists():
            return
        git_check = Path(".git") / "QuixBugs"  # 占位防误用
        assert not git_check.exists()
        # 直接验证 ignore 规则命中（不跑子进程：按 .gitignore 规则文本判断）
        gi_lines = [line.strip() for line in (_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()]
        assert "data/" in gi_lines
