# CI/CD 集成指南（P2 #23）

> 本文档给出把 AITester 的 CI 守卫、本地 pre-commit 钩子接入你自己仓库的示例。
> 配套文件：
> - [.github/workflows/ci.yml](../../.github/workflows/ci.yml) — GitHub Actions 矩阵
> - [../../.pre-commit-config.yaml](../../.pre-commit-config.yaml) — 本地 pre-commit 钩子
> - [../../.git-hooks/pre-commit.sh](../../.git-hooks/pre-commit.sh) — 独立 sh 钩子脚本
> - [../../.env.example](../../.env.example) — 环境变量模板（含 `AITESTER_SMOKE_LLM`）
> - [vendored_quixbugs.md](vendored_quixbugs.md) — 外部数据集（嵌套 git 仓库）的集成与还原

## 一、本地 pre-commit 钩子

```bash
pip install pre-commit
pre-commit install        # 安装 .git/hooks/pre-commit（自动读 .pre-commit-config.yaml）
# 或手动跑：sh .git-hooks/pre-commit.sh
```

钩子运行与 CI 同源的守卫脚本（`check_baseline_numbers.py` / `check_baseline.py` /
`check_bilingual_docs.py`），保证"本地跑通但 CI 挂"漂移最小化。

## 二、GitHub Actions 最小配置（非 Python 仓库消费 AITester 时）

```yaml
# .github/workflows/aitester-guard.yml
name: AITester guards
on:
  pull_request:
  push:
    branches: [main]
jobs:
  guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.14' }
      - run: python scripts/gates/check_baseline_numbers.py
      - run: python scripts/gates/check_baseline.py
      - run: python scripts/gates/check_bilingual_docs.py --strict
```

## 三、可选 LLM 冒烟（成本敏感）

`smoke-llm` 作业缺省 `AITESTER_SMOKE_LLM=false`（零 LLM 成本）。需要真实端点
连通性 + JSON 输出校验时，设 `AITESTER_SMOKE_LLM=true` 并配置
`LLM_1_API_KEY` / `LLM_1_BASE_URL` / `LLM_1_MODEL`（`.env` 或 GitHub Secrets）：

```yaml
- name: LLM smoke
  env:
    AITESTER_SMOKE_LLM: 'true'
    LLM_1_API_KEY: ${{ secrets.LLM_1_API_KEY }}
    LLM_1_BASE_URL: ${{ secrets.LLM_1_BASE_URL }}
    LLM_1_MODEL: ${{ vars.LLM_1_MODEL }}
  working-directory: experiments
  run: python run_smoke_llm.py
```

## 四、分支覆盖率门槛

核心路由模块（`graph/workflow.py` / `state.py` / `tracing.py` /
`error_classifier.py`）分支覆盖率门槛经 `scripts/gates/check_branch_coverage.py`
校验（总门槛 79%、核心 85%），CI 在 `coverage.xml` 生成后运行：

```bash
python scripts/gates/check_branch_coverage.py coverage.xml
```

## 五、静态报告归档

`scripts/tools/generate_static_report.py` 把 ruff / mypy 快照归档到
`docs/history/static_report_<date>.md`（CI 主分支上传 artifact）：

```bash
python scripts/tools/generate_static_report.py            # 写快照
python scripts/tools/generate_static_report.py --check    # 仅打印不写盘
```

---
*最后更新：2026-09-28（P2 #23 改进批次新增）。*
