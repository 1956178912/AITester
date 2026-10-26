#!/usr/bin/env python3
"""CI 作业超时预算锁（DH 轮，2026-10-26）。

## 为什么需要它

GitHub Actions 的作业默认上限是 360 分钟。2026-10-26 普查时，`ci.yml` 的
`smoke-llm` 是**唯一**没有声明 `timeout-minutes` 的作业——其余 9 个作业都有显式
预算（10–60 分钟）。真实 LLM 冒烟一旦挂起（网络黑洞、客户端不设读超时），runner
会被占满 6 小时才被平台回收；超时是**作业级**声明，漏一个不会有任何门禁变红。

本锁对 `.github/workflows/*.yml` 做结构判据：

1. 每个作业都必须声明 `timeout-minutes`；
2. 预算必须是正整数且落在 (0, 60]——60 是本仓现有最大档（test / self-mutation），
   声明超过 GitHub 默认上限的值等于没声明；
3. 解析面自校验：作业总数下限 + 已知作业在场，防「文件改名 / 解析塌陷」后
   前两条判据在空集上零用例通过。
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _jobs() -> dict[str, dict]:
    """全部 workflow 的作业，键为 `文件名::作业名`。"""
    workflows = sorted(WORKFLOW_DIR.glob("*.yml"))
    assert workflows, f"未发现 workflow 文件：{WORKFLOW_DIR}"
    jobs: dict[str, dict] = {}
    for path in workflows:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, job in (data.get("jobs") or {}).items():
            jobs[f"{path.name}::{name}"] = job
    return jobs


def test_every_job_declares_a_timeout():
    """缺预算的作业会吃满平台默认 360 分钟——挂起即烧 runner。"""
    missing = sorted(key for key, job in _jobs().items() if job.get("timeout-minutes") is None)
    assert not missing, f"这些 CI 作业没有 timeout-minutes（挂起会占满默认 360 分钟）：{missing}"


def test_timeout_budgets_are_positive_and_within_project_cap():
    """预算必须是正整数且在 (0, 60]——0 / 非整数 / 超过本仓最大档都不是有效预算。"""
    for key, job in _jobs().items():
        value = job.get("timeout-minutes")
        assert value is not None, f"{key} 缺 timeout-minutes"
        assert isinstance(value, int) and not isinstance(value, bool), f"{key} 的 timeout-minutes 不是整数：{value!r}"
        assert 1 <= value <= 60, f"{key} 的 timeout-minutes={value} 超出 (0, 60]"


def test_job_census_is_not_empty():
    """解析面塌了要当场红——否则上面两条会在空集上「零用例通过」。"""
    jobs = _jobs()
    assert len(jobs) >= 10, f"只解析到 {len(jobs)} 个作业——workflow 解析面可能塌了"
    for expected in ("ci.yml::smoke-llm", "ci.yml::test", "mutation.yml::self-mutation", "release.yml::release"):
        assert expected in jobs, f"缺少作业 {expected}——文件改名或结构变动后判据需重新校准"
