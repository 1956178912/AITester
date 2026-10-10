# Z7（2026-10-06 审查落地）：常用命令单入口。
# 此前构建/测试/门禁入口分散在 scripts/ 与 CI yml 中，新贡献者需要翻
# CONTRIBUTING 才能拼出完整命令链（审查 R20）。目标全部为既有命令的
# 薄封装，不引入新的执行口径——以 CI 为准的命令以 CI 实际参数为准。
#
# 用法：make help 查看全部目标。

.PHONY: help install lint format typecheck test test-cov docs-check env-budget baseline-check state-contract tool-versions gates repro power self-check clean-traces build-check cpr-idr repair-replay cf-upper-bound corrected-metrics

PY := .venv/bin/python

help:  ## 显示本说明
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install:  ## 安装依赖（requirements.txt，锁定口径）
	$(PY) -m pip install -r requirements.txt

lint:  ## ruff 检查（CI 固定 0.16.3）
	ruff check .

format:  ## ruff 格式化检查（CI 同口径，不落盘）
	ruff format --check .

typecheck:  ## mypy 类型检查（CI 同口径：src/ + config.py）
	$(PY) -m mypy src/ config.py

test:  ## 全量测试（CI 同口径：xdist -n 4 loadfile）
	$(PY) -m pytest tests/ -n 4 --dist loadfile

test-cov:  ## 全量测试 + 覆盖率（CI 同口径）
	$(PY) -m pytest tests/ -n 4 --dist loadfile --cov=src --cov-branch --cov-report=term-missing

docs-check:  ## 双语文档同步门禁（strict，CI 阻断项）
	$(PY) scripts/gates/check_bilingual_docs.py --strict

env-budget:  ## 环境变量开关预算棘轮（CI 阻断项）
	$(PY) scripts/gates/check_env_budget.py --check

baseline-check:  ## BASELINE.yaml 结构 + 文档数字漂移守卫
	$(PY) scripts/gates/check_baseline.py
	$(PY) scripts/gates/check_baseline_numbers.py

state-contract:  ## LangGraph 状态通道静态契约守卫（AK4 接入 CI）
	$(PY) scripts/gates/check_state_contract.py

tool-versions:  ## CI/pre-commit/lock 三方工具版本一致守卫（AK4 接入 CI）
	$(PY) scripts/gates/check_tool_versions.py

gates: lint typecheck test docs-check env-budget baseline-check state-contract tool-versions  ## 本地全部门禁（合并前自检）

repro:  ## 复现主批次（详见 reproduce.sh；消耗 LLM 配额，勿自动触发）
	bash reproduce.sh

power:  ## 统计功效分析速览（Z8：先算样本量，再跑实验）
	$(PY) scripts/tools/power_analysis.py

self-check:  ## 功效分析往返一致性自检
	$(PY) scripts/tools/power_analysis.py --self-check

clean-traces:  ## 清理失败追踪残留（tmp_trace/，--dump-trace-on-failure 运行时产物，可再生）
	rm -rf tmp_trace
	@echo "tmp_trace/ 已清理"

cpr-idr:  ## 补丁检测有效性 + 弃权视角报告（批次 II/V：IDR/CPR + would-be abstention，零 LLM 读存量工件）
	$(PY) experiments/cpr_idr_report.py --results-dir experiments/results/main_batch --arm aitester

repair-replay:  ## repair=0 围栏伪影存量重放（批次 VII/ADR-0021：修正口径 correct vs 原口径伪影，零 LLM）
	$(PY) -m experiments.repair_replay experiments/results/main_batch --arm aitester

cf-upper-bound:  ## 反事实 FL 上界归因分解（批次 X/ADR-0024：FL×correct 2×2 分解 + P(correct|FL命中)，零 LLM）
	$(PY) -m experiments.cf_upper_bound experiments/results/main_batch --arm aitester

corrected-metrics:  ## 修正口径重估总报告（批次 XIII/ADR-0027：repair/false_fix/CPR/弃权精确率 + bug_type 分层解混杂，零 LLM）
	$(PY) -m experiments.corrected_metrics experiments/results/main_batch --arm aitester

target-quality:  ## 目标质量存量重放（R5 审查批次：被测代码覆盖率 / 变异得分 / 规约可编译率，零 LLM 只读工件）
	$(PY) -m experiments.target_quality_replay experiments/results/main_batch

build-check:  ## 发行构建链路冒烟（AS 批 2026-10-07：build wheel → 全新 venv 安装 → CLI/import 冒烟；本地验证用，未接 CI——发布批次 AL9 再定）
	$(PY) -m build --wheel
	rm -rf /tmp/aitester_build_check
	python3 -m venv /tmp/aitester_build_check
	/tmp/aitester_build_check/bin/pip install --quiet dist/*.whl
	/tmp/aitester_build_check/bin/aitester --version
	/tmp/aitester_build_check/bin/python -c "import config, src; from src.cli.app import cli; print('build-check OK: wheel 安装/入口/导入全部正常')"
