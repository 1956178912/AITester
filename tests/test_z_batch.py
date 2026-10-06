"""Z 批次（2026-10-06 系统性审查落地）回归测试。

覆盖：
- Z1 策略银行 prompt_hint 不再拼入 patch（静态守卫 + state 键契约）
- Z2 再生成上限单一事实源（config.MAX_REGENERATIONS）
- Z3 仓库环境缓存校验全等比较（静态守卫）
- Z4 telemetry 拼写占位符清理
- Z5 双语文档门禁扩围到根目录配对（进程内直调 check_bilingual）
- Z6 数据卡双语成对存在
- Z7 Makefile / Issue 模板存在
- Z8 功效分析：往返一致性 / 单调性 / 合法性校验（importlib 进程内加载）
- Z9 贝叶斯配对分析：精确矩手算 / 配对口径与 _pair_by_task 等价 /
  可复现性 / 样本不足口径 / 结论标签

全部用例零 LLM / 零网络 / 零子进程。
"""

from __future__ import annotations

import importlib.util
import math
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_POWER_SCRIPT = PROJECT_ROOT / "scripts" / "power_analysis.py"


def _load_power_module():
    """进程内加载 power_analysis 脚本为模块（免子进程，与 W2 ratchet 同口径）。"""
    spec = importlib.util.spec_from_file_location("aitester_power_analysis", _POWER_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(rel: str) -> str:
    return (PROJECT_ROOT / rel).read_text(encoding="utf-8")


# ═══ Z1：策略银行 prompt_hint 与 patch 隔离 ═════════════════════════════════


class TestZ1StrategyBankHintIsolation(unittest.TestCase):
    def test_prompt_hint_no_longer_concatenated_into_patch(self):
        """静态守卫：nodes.py 不得再把 prompt_hint 字符串拼进 patch。

        历史 bug：策略提示文本（自然语言）直接 `+ "\\n\\n" +` 追加到候选
        patch 代码尾部（专家池路径 / 独立路径各一处），只能靠下游 AST
        守卫兜底拒绝——浪费候选且污染补丁内容。
        """
        src = _read("src/graph/nodes.py")
        self.assertNotIn('+ "\\n\\n" + strategy["prompt_hint"]', src)
        self.assertNotIn('+ "\\n\\n" + _sb_strategy["prompt_hint"]', src)
        # 修复后：提示文本经 update["strategy_bank_hint"] 持久化
        self.assertIn('"strategy_bank_hint": _sb_hint', src)

    def test_state_key_declared_and_initialized(self):
        """state 契约：strategy_bank_hint 已声明 + 工厂初始化 None（键集合同构）。"""
        from src.graph.state import AITesterState, create_initial_state

        self.assertIn("strategy_bank_hint", AITesterState.__annotations__)
        state = create_initial_state(
            task_uuid="z-batch-test",
            target_file="fake_module.py",
            target_code="def f():\n    pass\n",
            max_iterations=3,
        )
        self.assertIsNone(state.get("strategy_bank_hint"))


# ═══ Z2：再生成上限单一事实源 ═══════════════════════════════════════════════


class TestZ2MaxRegenerationsSingleSource(unittest.TestCase):
    def test_nodes_local_literal_removed_and_config_is_source(self):
        """nodes.py 的同值局部字面量已删除；workflow 别名与 config 同源。"""
        import re

        nodes_src = _read("src/graph/nodes.py")
        # 真赋值语句不得存在（注释中的历史叙述允许；按行首缩进+赋值形态匹配）
        self.assertIsNone(re.search(r"^\s*_MAX_REGENERATIONS\s*=\s*1\s*$", nodes_src, re.M))
        self.assertIn('int(state.get("regeneration_count", 0)) < MAX_REGENERATIONS', nodes_src)

        import config
        from src.graph import workflow

        self.assertEqual(config.MAX_REGENERATIONS, 1)
        self.assertEqual(workflow._MAX_REGENERATIONS, config.MAX_REGENERATIONS)


# ═══ Z3：仓库环境缓存校验全等 ═══════════════════════════════════════════════


class TestZ3RepoCacheCommitExactMatch(unittest.TestCase):
    def test_no_prefix_comparison_remains(self):
        """静态守卫：executor_repo 不得再用 12 位前缀比较 commit。"""
        src = _read("src/agents/executor_repo.py")
        self.assertNotIn("startswith(base_commit[:12])", src)
        # 两处缓存校验（首检 + 锁内复检）均为全等
        self.assertEqual(src.count("head.stdout.strip() == base_commit"), 2)


# ═══ Z4：telemetry 占位符清理 ═══════════════════════════════════════════════


class TestZ4TelemetryPlaceholderRemoved(unittest.TestCase):
    def test_typo_placeholder_gone_and_detectors_intact(self):
        src = _read("src/observability/agent_telemetry.py")
        self.assertNotIn("_PATTERns", src)

        from src.observability.agent_telemetry import _PATTERN_DETECTORS

        # 清理不伤功能：11 个本地失败模式检测器完整（Y2 MAST 对齐口径）
        self.assertGreaterEqual(len(_PATTERN_DETECTORS), 11)


# ═══ Z5：双语文档门禁扩围 ═══════════════════════════════════════════════════


class TestZ5BilingualGateRootPairs(unittest.TestCase):
    def test_root_pairs_in_gate_and_on_disk(self):
        import scripts.check_bilingual_docs as cbd

        for rel in ("README.md", "QUICKSTART.md", "CONTRIBUTING.md", "MODEL_CARD.md", "SECURITY.md"):
            self.assertIn(rel, cbd._CHECK_FILES)
            self.assertTrue((PROJECT_ROOT / rel).exists(), rel)
            en = PROJECT_ROOT / (rel[:-3] + ".en.md")
            self.assertTrue(en.exists(), str(en))

    def test_gate_strict_passes_in_process(self):
        """扩围后 strict 门禁整体通过（进程内直调，与 CI CLI 同一函数）。"""
        import scripts.check_bilingual_docs as cbd

        failures, warnings = cbd.check_bilingual(strict=True)
        self.assertEqual(failures, [], "\n".join(failures))
        self.assertEqual(warnings, [], "\n".join(warnings))


# ═══ Z6/Z7：数据卡与工程入口 ════════════════════════════════════════════════


class TestZ6Z7DocsAndTooling(unittest.TestCase):
    def test_data_card_bilingual_pair_exists(self):
        zh = PROJECT_ROOT / "docs" / "DATA_CARD.md"
        en = PROJECT_ROOT / "docs" / "DATA_CARD.en.md"
        self.assertTrue(zh.exists())
        self.assertTrue(en.exists())
        zh_text = zh.read_text(encoding="utf-8")
        en_text = en.read_text(encoding="utf-8")
        # 泄漏控制与许可核实结论是数据卡的核心承诺字段。
        # AH1（2026-10-06）许可经 GitHub API 权威核实：QuixBugs=MIT（L1 前置
        # 解除）、BugsInPy 无 SPDX 许可证（L2 决策门槛）——断言由"待核实"
        # 状态升级为"核实结论已登记"状态。
        self.assertIn("spdx_id=MIT", zh_text)
        self.assertIn("spdx_id=MIT", en_text)
        # BugsInPy 无许可门槛必须保持登记（L2 立项前置）
        self.assertIn("null", zh_text)
        self.assertIn("null", en_text)

    def test_makefile_and_issue_templates_exist(self):
        makefile = PROJECT_ROOT / "Makefile"
        self.assertTrue(makefile.exists())
        mk = makefile.read_text(encoding="utf-8")
        for target in ("lint:", "typecheck:", "test:", "docs-check:", "gates:"):
            self.assertIn(target, mk)
        for tpl in ("bug_report.md", "feature_request.md"):
            self.assertTrue((PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE" / tpl).exists(), tpl)


# ═══ Z8：功效分析 ═══════════════════════════════════════════════════════════


class TestZ8PowerAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pa = _load_power_module()

    def test_round_trip_required_n_vs_detectable_delta(self):
        """往返一致性：required_n 反解的 detectable_delta 不超过原 δ。"""
        for p_a, p_b, p11 in ((0.12, 0.02, 0.01), (0.32, 0.02, 0.015), (0.75, 0.52, 0.45)):
            n = self.pa.required_n_paired(p_a, p_b, p11)
            delta_back = self.pa.detectable_delta_paired(n, p_b, p11)
            self.assertLessEqual(delta_back, p_a - p_b + 1e-9)
            # 反解出的样本量恰好达标：功效不低于目标（留 1e-6 数值容差）
            self.assertGreaterEqual(self.pa.power_paired(n, p_b + delta_back, p_b, p11), 0.8 - 1e-6)

    def test_required_n_monotone_in_delta(self):
        """效应量越大所需样本量越小（单调性）。"""
        n_small = self.pa.required_n_paired(0.12, 0.02, 0.01)
        n_large = self.pa.required_n_paired(0.32, 0.02, 0.015)
        self.assertLess(n_large, n_small)

    def test_illegal_p11_raises(self):
        with self.assertRaises(ValueError):
            self.pa.required_n_paired(0.12, 0.02, 0.12)  # p11 > min(p_a, p_b) 非法

    def test_self_check_exits_zero(self):
        self.assertEqual(self.pa._self_check(), 0)


# ═══ Z9：贝叶斯配对分析 ════════════════════════════════════════════════════


def _rows(pairs: list[tuple[str, object, object]]) -> tuple[list[dict], list[dict]]:
    """构造两基线结果行：pairs = [(task_id, a 值, b 值)]。"""
    a = [{"task_id": t, "passed": va, "detection_rate": va} for t, va, _ in pairs]
    b = [{"task_id": t, "passed": vb, "detection_rate": vb} for t, _, vb in pairs]
    return a, b


class TestZ9BayesianPaired(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from experiments.bayesian_paired import bayesian_paired_analysis, interpret_bayes

        cls.analyze = staticmethod(bayesian_paired_analysis)
        cls.interpret = staticmethod(interpret_bayes)

    def test_exact_posterior_moments_hand_computed(self):
        """闭式矩手算锁定：n01=6, n10=0, n11=30, n00=12（n=48）。

        α = (31, 7, 1, 13)，α0 = 52：
        E[δ] = (7−1)/52 = 0.1153846…
        Var[δ] = (52×8 − 36)/(52²×53) = 380/143312 = 0.0026515…
        """
        rows_a, rows_b = _rows(
            [(f"t{i:02d}", 1, 0) for i in range(6)]  # n01 = 6
            + [(f"u{i:02d}", 1, 1) for i in range(30)]  # n11 = 30
            + [(f"v{i:02d}", 0, 0) for i in range(12)]  # n00 = 12
        )
        res = self.analyze(rows_a, rows_b, n_draws=0)  # 仅闭式矩
        self.assertEqual(res["n_common"], 48)
        self.assertEqual(res["n01"], 6)
        self.assertEqual(res["n10"], 0)
        self.assertAlmostEqual(res["post_mean"], 6.0 / 52.0, places=9)
        self.assertAlmostEqual(res["post_sd"], math.sqrt(380.0 / 143312.0), places=9)

    def test_mc_reproducible_and_directionally_sane(self):
        """同 seed 两次调用逐位一致；CI 包含均值；P(δ>0) 与正态近似吻合。"""
        rows_a, rows_b = _rows(
            [(f"t{i:02d}", 1, 0) for i in range(6)]
            + [(f"u{i:02d}", 1, 1) for i in range(30)]
            + [(f"v{i:02d}", 0, 0) for i in range(12)]
        )
        r1 = self.analyze(rows_a, rows_b, n_draws=5000)
        r2 = self.analyze(rows_a, rows_b, n_draws=5000)
        self.assertEqual(r1, r2)  # 固定 seed：dict 级逐位一致
        self.assertLess(r1["ci_low"], r1["post_mean"])
        self.assertLess(r1["post_mean"], r1["ci_high"])
        # 正态近似：P(δ>0) ≈ Φ(mean/sd) = Φ(0.11538/0.05149) ≈ 0.9874
        from statistics import NormalDist

        approx = NormalDist().cdf(r1["post_mean"] / r1["post_sd"])
        self.assertAlmostEqual(r1["p_greater"], approx, delta=0.02)

    def test_pairing_semantics_matches_pair_by_task(self):
        """配对口径与 statistical_analysis._pair_by_task 等价（锁不变量）。

        覆盖三类边界：重复 task_id（首见胜出）、None 值（gold 缺失，分母外）、
        单侧独有 task_id（交集外）。
        """
        from experiments.statistical_analysis import _pair_by_task

        rows_a = [
            {"task_id": "dup", "detection_rate": 1},
            {"task_id": "dup", "detection_rate": 0},  # 重复：首见（=1）胜出
            {"task_id": "none_a", "detection_rate": None},  # None：跳过
            {"task_id": "only_a", "detection_rate": 1},  # 交集外
            {"task_id": "both0", "detection_rate": 0},
            {"task_id": "both1", "detection_rate": 1},
        ]
        rows_b = [
            {"task_id": "dup", "detection_rate": 0},
            {"task_id": "none_b", "detection_rate": None},
            {"task_id": "only_b", "detection_rate": 1},
            {"task_id": "both0", "detection_rate": 0},
            {"task_id": "both1", "detection_rate": 1},
        ]
        paired_a, paired_b, common = _pair_by_task(rows_a, rows_b, field="detection_rate")
        from experiments.bayesian_paired import paired_contingency

        counts = paired_contingency(rows_a, rows_b, field="detection_rate")
        self.assertEqual(counts["n_common"], len(common))
        n01 = sum(1 for x, y in zip(paired_a, paired_b, strict=True) if x == 1 and y == 0)
        n10 = sum(1 for x, y in zip(paired_a, paired_b, strict=True) if x == 0 and y == 1)
        self.assertEqual(counts["n01"], n01)
        self.assertEqual(counts["n10"], n10)
        self.assertEqual(counts["n11"] + counts["n01"] + counts["n10"] + counts["n00"], counts["n_common"])

    def test_insufficient_sample_returns_none_with_note(self):
        rows_a, rows_b = _rows([("only_one", 1, 0)])
        res = self.analyze(rows_a, rows_b)
        self.assertEqual(res["n_common"], 1)
        self.assertIsNone(res["post_mean"])
        self.assertIn("样本不足", res["note"])

    def test_interpret_bayes_labels(self):
        self.assertEqual(
            self.interpret({"p_greater": 0.99, "p_less": 0.01, "p_rope": 0.96, "rope": 0.05}),
            "bayes_equiv",
        )
        self.assertEqual(
            self.interpret({"p_greater": 0.99, "p_less": 0.01, "p_rope": 0.01, "rope": 0.05}),
            "bayes_pos",
        )
        self.assertEqual(
            self.interpret({"p_greater": 0.01, "p_less": 0.99, "p_rope": 0.01, "rope": 0.05}),
            "bayes_neg",
        )
        self.assertEqual(
            self.interpret({"p_greater": 0.6, "p_less": 0.4, "p_rope": 0.2, "rope": 0.05}),
            "bayes_inconclusive",
        )
        self.assertEqual(self.interpret({"p_greater": None}), "n/a")


if __name__ == "__main__":
    unittest.main()
