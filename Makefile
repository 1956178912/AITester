# Z7（2026-10-06 审查落地）：常用命令单入口。
# 此前构建/测试/门禁入口分散在 scripts/ 与 CI yml 中，新贡献者需要翻
# CONTRIBUTING 才能拼出完整命令链（审查 R20）。目标全部为既有命令的
# 薄封装，不引入新的执行口径——以 CI 为准的命令以 CI 实际参数为准。
#
# 用法：make help 查看全部目标。

.PHONY: help install lint format typecheck test test-cov docs-check env-budget baseline-check state-contract tool-versions gates repro power self-check clean-traces

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
	$(PY) scripts/check_bilingual_docs.py --strict

env-budget:  ## 环境变量开关预算棘轮（CI 阻断项）
	$(PY) scripts/check_env_budget.py --check

baseline-check:  ## BASELINE.yaml 结构 + 文档数字漂移守卫
	$(PY) scripts/check_baseline.py
	$(PY) scripts/check_baseline_numbers.py

state-contract:  ## LangGraph 状态通道静态契约守卫（AK4 接入 CI）
	$(PY) scripts/check_state_contract.py

tool-versions:  ## CI/pre-commit/lock 三方工具版本一致守卫（AK4 接入 CI）
	$(PY) scripts/check_tool_versions.py

gates: lint typecheck test docs-check env-budget baseline-check state-contract tool-versions  ## 本地全部门禁（合并前自检）

repro:  ## 复现主批次（详见 reproduce.sh；消耗 LLM 配额，勿自动触发）
	bash reproduce.sh

power:  ## 统计功效分析速览（Z8：先算样本量，再跑实验）
	$(PY) scripts/power_analysis.py

self-check:  ## 功效分析往返一致性自检
	$(PY) scripts/power_analysis.py --self-check

clean-traces:  ## 清理失败追踪残留（tmp_trace/，--dump-trace-on-failure 运行时产物，可再生）
	rm -rf tmp_trace
	@echo "tmp_trace/ 已清理"
