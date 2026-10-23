"""AO 批次（2026-10-07 第十五轮审查落地）锁定测试。

覆盖五项自主执行项（第十五轮审查报告 R15-4/R15-7/R15-9 + E7 前置）：
- AO1 E6 预注册修订：matched cap 改取 E2 实测均值（shell 占位变量注入），
  R-P0-2 旧常数（26,115/4,223）不得再以字面 cap 出现；修订效力声明在场；
- AO2 CI 安装切换 requirements.lock：test/smoke 作业安装与缓存键走 lock
  （132 项全量钉版），lock 含关键测试工具链；
- AO3 en README 头部 Last updated 与 AN/AO 批次同步（修内部日期漂移）；
- AO4 U10 弃用别名移除时间线定档（v0.8.0）；
- AO5 E7 候选清单工件：存在、口径齐全、SHA256SUMS 登记、真实工件上
  确定性复算逐位一致。
"""

from __future__ import annotations

import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PREREG_ZH = (PROJECT_ROOT / "docs" / "preregistration.md").read_text(encoding="utf-8")
PREREG_EN = (PROJECT_ROOT / "docs" / "preregistration.en.md").read_text(encoding="utf-8")
CI_YML = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
README_EN_HEAD = "\n".join((PROJECT_ROOT / "README.en.md").read_text(encoding="utf-8").splitlines()[:10])
E7_ARTIFACT = PROJECT_ROOT / "experiments" / "results" / "main_batch" / "e7_repair_sample_candidates.md"


class TestPreregE6CapAmendment:
    """AO1：E6 matched cap 来源修订（R-P0-2 常数 → E2 实测均值）锁定。"""

    def test_amendment_marker_and_effect_statement(self) -> None:
        """修订标记与效力声明双语在场（修订时点早于任何 E6 数据）。"""
        assert "AO 修订，2026-10-07，早于任何 E6 数据" in PREREG_ZH
        assert "修订效力声明" in PREREG_ZH
        assert "E2 实测均值" in PREREG_ZH
        assert "amended by batch AO, 2026-10-07" in PREREG_EN
        assert "Amendment effect statement" in PREREG_EN
        assert "E2 measured means" in PREREG_EN

    def test_extraction_command_present(self) -> None:
        """就绪命令含"E2 实测均值提取"步骤（行级 token_usage 聚合口径）。"""
        for text in (PREREG_ZH, PREREG_EN):
            assert "mean_total_tokens_per_task" in text
            assert "token_usage']['total_tokens']" in text

    def test_placeholder_caps_in_both_languages(self) -> None:
        """双语命令块均以占位变量注入两个 matched 臂的 cap。"""
        for text in (PREREG_ZH, PREREG_EN):
            assert '--per-task-token-caps "aitester=${DF_MEAN}"' in text
            assert '--per-task-token-caps "plain_llm_df=${AITESTER_MEAN}"' in text


class TestCILockInstall:
    """AO2：CI 执行环境切换 requirements.lock（R15-7）锁定。"""

    def test_ci_yaml_parses(self) -> None:
        """ci.yml 可被 YAML 解析器加载（防块标量语法回归）。"""
        import yaml

        cfg = yaml.safe_load(CI_YML)
        assert isinstance(cfg, dict) and "jobs" in cfg

    def test_install_and_cache_use_lock(self) -> None:
        """所有 Python 作业安装走 lock 且无 requirements.txt 安装残留；
        缓存键随 lock（O 轮起 3 处：test + smoke-llm + e2e-probe）。"""
        assert CI_YML.count("pip install -r requirements.lock") == 3
        assert "pip install -r requirements.txt" not in CI_YML
        assert CI_YML.count("cache-dependency-path: requirements.lock") == 3

    def test_lock_contains_test_toolchain(self) -> None:
        """lock 全量钉版覆盖测试工具链（pytest 系/ruff/hypothesis/coverage）。"""
        lock = (PROJECT_ROOT / "requirements.lock").read_text(encoding="utf-8")
        for pin in (
            "pytest==",
            "pytest-cov==",
            "pytest-xdist==",
            "pytest-timeout==",
            "ruff==",
            "hypothesis==",
            "coverage==",
        ):
            assert pin in lock, f"requirements.lock 缺少 {pin} 钉版"


class TestReadmeEnHeader:
    """AO3：en README 头部 Last updated 与最新批次同步。"""

    def test_head_updated_line_current(self) -> None:
        """头部日期行为 2026-10-20 且提及最新批次（行锁随最新批次推进——
        AC 轮 2026-10-20 合法更新本锁。历史：W 轮补到 2026-10-19 时发现
        U/V 两轮未随该约定推进日期行（旧锁停留在批次 XIV/2026-10-07）；
        X 轮漏维护本锁，Y 轮文档同步时一并收口 X/Y 两轮；Z→AB 批
        （2026-10-19~20）漏维护后由 AB 收口轮补推至 2026-10-20；AC 轮 / AD 轮 / AE 轮
        （均 2026-10-20）相继推进短语（日期同为 2026-10-20）；AF 轮（2026-10-20）推进
        至 "AF round"——本锁在 AF 的 `make gates` 里当场转红，README 头部同步后转绿；
        AG 轮（2026-10-20）按同一约定推进至 "AG round"；AH 轮（2026-10-20）推进至
        "AH round"；AI 轮（2026-10-21）推进至 "AI round" 并随日期行改为 2026-10-21；
        AJ 轮（2026-10-21）推进至 "AJ round"；AK 轮（2026-10-21）推进至 "AK round"；
        AL 轮（2026-10-21）推进至 "AL round"；AM 轮（2026-10-21）推进至 "AM round"；
        AN 轮（2026-10-21）推进至 "AN round"；AO 轮（2026-10-21）推进至 "AO round"；
        AP 轮（2026-10-21）推进至 "AP round"；AQ 轮（2026-10-21）推进至 "AQ round"；
        AR 轮（2026-10-21）推进至 "AR round"；AS 轮（2026-10-21）推进至 "AS round"；
        AT 轮（2026-10-21）推进至 "AT round"；AU 轮（2026-10-21）推进至 "AU round"；
        AV 轮（2026-10-21）推进至 "AV round"；AW 轮（2026-10-21）推进至 "AW round"；
        AX 轮（2026-10-21）推进至 "AX round"；AY 轮（2026-10-21）推进至 "AY round"；
        AZ 轮（2026-10-21）推进至 "AZ round"；BA 轮（2026-10-21）推进至 "BA round"；
        BB 轮（2026-10-21）与 BC 轮（2026-10-21）**未推进本锁**——BC 头部历史链
        含 "After the BA round…" / "Previously **BA round**:" 两处 "BA round"
        字面，旧断言因此恒真（**误绿**）；BC 文档收口把断言推进至 "BC round"，
        并把 README.en 头部统一为 "**BC round:" 写法（行锁必须指向唯一最新批次
        标记，不能指向会在历史链里反复出现的旧轮次名）；BD 轮（2026-10-21）
        推进至 "**BD round:"；BE 轮（2026-10-21）推进至 "**BE round:"；
        BF 轮（2026-10-21）推进至 "**BF round:"（带冒号的完整标记，历史链
        中的 "Previously **BE round:" 不命中该字面）；BG 轮（2026-10-21）
        推进至 "**BG round:"（同样带冒号；历史链中的 "Previously **BF
        round:" 不命中该字面）；BH 轮（2026-10-21）推进至 "**BH round:"
        （同一写法；历史链中的 "Previously **BG round:" 不命中该字面）；BI 轮
        （2026-10-22，登记日随零点跨班后移）推进至 "**BI round:"，日期行同步
        改为 2026-10-22（改写后前 10 行已不再出现 "Last updated: 2026-10-21"，
        旧日期断言不会因残留文本误绿）；BJ 轮（2026-10-22）推进至 "**BJ round:"
        （同一写法：历史链里 BI 的标记已改为 "Previously **BI round:"，不命中
        带冒号的最新字面），日期行仍为 2026-10-22；BK 轮（2026-10-22）推进至
        "**BK round:"（BJ 的标记随之改为 "Previously **BJ round:"，故带冒号的最新
        字面在头部唯一命中），日期行仍为 2026-10-22；
        BL 轮（2026-10-22）推进至 "**BL round:"（BK 的标记随之改为 "Previously **BK round:"，故带冒号的最新
        字面在头部唯一命中），日期行仍为 2026-10-22；BM 轮（2026-10-22）推进至
        "**BM round:"（同一写法：BL 的标记随之改为 "Previously **BL round:"，带冒号的
        最新字面在头部唯一命中），日期行仍为 2026-10-22；BN 轮（2026-10-22）推进至
        "**BN round:"（同一写法：BM 的标记随之改为 "Previously **BM round:"，带冒号的最新字面
        在头部唯一命中），日期行仍为 2026-10-22；BO 轮（2026-10-22）推进至 "**BO round:"（同一写法：BN 的标记随之改为 "Previously **BN round:"，带冒号的最新字面在头部唯一命中），日期行仍为 2026-10-22；BP 轮（2026-10-22）推进至 "**BP round:"（同一写法：BO 的标记随之改为 "Previously **BO round:"，带冒号的最新字面在头部唯一命中；本轮头部叙述按 EN 惯例把轮次名加粗闭合，避免插入奇数个 `**` 打乱整行的粗体配对），日期行仍为 2026-10-22；BQ 轮（2026-10-22）推进至 "**BQ round:"（同一写法：BP 的标记随之改为 "Previously **BP round:"，带冒号的最新字面在头部唯一命中；本轮头部叙述按 EN 惯例把轮次名加粗闭合，避免插入奇数个 `**` 打乱整行的粗体配对——BP 轮 §6⑤ 的口径：单逻辑行 + 剔除行内代码后奇偶必须为偶，本轮轮换后实测为偶），日期行仍为 2026-10-22；BR 轮（2026-10-22）与 BS 轮（2026-10-22）
        **未推进本锁**——两轮已把 README.en 头部分别推进至 "**BR round:" 与 "**BS round:"，
        但断言仍钉 "**BQ round:"，而此时该字面只命中历史链里的 "Previously **BQ round:"，
        即 BC 轮 docstring 记过的同一**误绿**形态（头部再往后退到 BR/BS 也不会转红）；
        BT 轮（2026-10-22）收口：断言推进至 "**BT round:"（单逻辑行剔除行内代码后 `**` = 476
        为偶，最新字面在头部唯一命中、历史链首项为 "Previously **BS round:"），同时登记
        BR/BS 两轮行锁未推进的存量漂移，日期行仍为 2026-10-22；BU 轮（2026-10-23，登记日随零点跨班后移）
        推进至 "**BU round:"（同一写法：BT 的标记随之改为 "Previously **BT round:"，带冒号的最新字面
        在头部唯一命中；中文侧同步推进至 "**BU 轮："，历史链首项为 "此前 **BT 轮："；
        单逻辑行剔除行内代码后 `**` 中文 472 / 英文 498，均为偶），日期行同步改为 2026-10-23
        （改写后头部前 10 行已不再出现 "Last updated: 2026-10-22"，旧日期断言不会因残留文本误绿）。
        BV 轮（2026-10-23）推进至 "**BV round:"（同一写法：BU 的标记随之改为
        "Previously **BU round:"，带冒号的最新字面在头部唯一命中；中文侧同步推进至
        "**BV 轮："，历史链首项为 "此前 **BU 轮："；单逻辑行剔除行内代码后 `**` 中文 498 /
        英文 524，均为偶）。
        BW 轮（2026-10-23）推进至 "**BW round:"（同一写法：BV 的标记随之改为
        "Previously **BV round:"，带冒号的最新字面在头部唯一命中；中文侧同步推进至
        "**BW 轮："，历史链首项为 "此前 **BV 轮："；单逻辑行剔除行内代码后 `**` 中文 502 /
        英文 528，均为偶）。
        BX 轮（2026-10-23）推进至 "**BX round:"（同一写法：BW 的标记随之改为
        "Previously **BW round:"，带冒号的最新字面在头部唯一命中；中文侧同步推进至
        "**BX 轮："，历史链首项为 "此前 **BW 轮："；单逻辑行剔除行内代码后 `**` 中文 506 /
        英文 532，均为偶）。
        BY 轮（2026-10-23）推进至 "**BY round:"（同一写法：BX 的标记随之改为
        "Previously **BX round:"，带冒号的最新字面在头部唯一命中；中文侧同步推进至
        "**BY 轮："，历史链首项为 "此前 **BX 轮："；单逻辑行剔除行内代码后 `**` 中文 510 /
        英文 536，均为偶）。
        BZ 轮（2026-10-23）推进至 "**BZ round:"（同一写法：BY 的标记随之改为
        "Previously **BY round:"，带冒号的最新字面在头部唯一命中；中文侧同步推进至
        "**BZ 轮："，历史链首项为 "此前 **BY 轮："；本轮轮换后在
        tests/test_ao_batch.py 同款方法（全文件剔除行内代码后 `**` 出现次数）下实测
        中文 986 / 英文 920，均为偶）。"""
        assert "Last updated: 2026-10-23" in README_EN_HEAD
        assert "**BZ round:" in README_EN_HEAD


class TestDeprecationTimeline:
    """AO4：U10 弃用别名移除时间线定档。"""

    def test_old_alias_warns_with_removal_version(self) -> None:
        """entry_ocurrence_stat 旧名触发 DeprecationWarning 且含 v0.8.0 移除档。"""
        from src.agents.failure_kb import entry_ocurrence_stat

        entries = [{"error_category": "assertion", "target_module": "foo"}]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            entry_ocurrence_stat(entries, "assertion", {"error_category": "assertion"})
        messages = [str(item.message) for item in caught if item.category is DeprecationWarning]
        assert messages, "旧名未触发 DeprecationWarning"
        assert any("v0.8.0" in message for message in messages)


class TestE7CandidateArtifact:
    """AO5：E7 修复上限抽样候选清单（预注册 E7 的人工复核入口）。"""

    def test_artifact_registered_with_checksums(self) -> None:
        """候选清单存在、口径齐全且已登记 SHA256SUMS。"""
        content = E7_ARTIFACT.read_text(encoding="utf-8")
        assert content.startswith("# E7")
        assert "seed=42" in content
        assert "（待复核）" in content
        sums = (PROJECT_ROOT / "experiments" / "results" / "main_batch" / "SHA256SUMS").read_text(encoding="utf-8")
        assert "e7_repair_sample_candidates.md" in sums

    def test_sampling_deterministic_on_real_artifacts(self) -> None:
        """真实批次工件上同参复算：两次抽样 task_id 序列逐位一致，且行数
        与候选清单登记行数一致（预注册确定性口径）。"""
        from experiments.repair_sample_selection import (
            _DEFAULT_BATCHES,
            build_sampling_frame,
            select_stratified_sample,
            stratify,
        )
        from experiments.statistical_analysis import load_experiment_results_with_sources

        results, _ = load_experiment_results_with_sources(
            "experiments/results/main_batch",
            list(_DEFAULT_BATCHES),
            allow_schema_mixed=False,
            pool_seeds=True,
        )
        frame = build_sampling_frame(results.get("aitester") or [])
        strata = stratify(frame)
        first = [r["task_id"] for r in select_stratified_sample(strata, 0.10, 42)]
        second = [r["task_id"] for r in select_stratified_sample(strata, 0.10, 42)]
        assert first == second
        content = E7_ARTIFACT.read_text(encoding="utf-8")
        assert len(first) == content.count("（待复核）")

    def test_frame_single_stratum_disclosed(self) -> None:
        """抽样框分层信息在清单中如实披露（当前 72 行全部 sbfl 单层）。"""
        content = E7_ARTIFACT.read_text(encoding="utf-8")
        assert "sbfl" in content
        assert "72 行" in content
