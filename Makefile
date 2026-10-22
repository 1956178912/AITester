# Z7（2026-10-06 审查落地）：常用命令单入口。
# 此前构建/测试/门禁入口分散在 scripts/ 与 CI yml 中，新贡献者需要翻
# CONTRIBUTING 才能拼出完整命令链（审查 R20）。目标全部为既有命令的
# 薄封装，不引入新的执行口径——以 CI 为准的命令以 CI 实际参数为准。
#
# 用法：make help 查看全部目标。

.PHONY: help install lint format typecheck test test-cov docs-check env-budget baseline-check state-contract env-snapshot model-fingerprint tool-versions json-contract-sites json-strict prompt-artifacts-check preflight artifact-doc-consistency proc-hygiene perf-bench perf-check zero-assert ast-guards status-persistence self-mutation self-mutation-ci gates repro power self-check clean-traces build-check cpr-idr repair-replay cf-upper-bound corrected-metrics target-quality mutation-det-correlation swebench-disclosure pass-matched emse-stats

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

test-cov:  ## 全量测试 + 覆盖率（CI 同口径；额外落 coverage.xml 供棘轮/登记册对账消费）
	# N 轮（2026-10-17）：COVERAGE_FILE 指向独立数据文件——探针/执行器测试会启动真实
	# pytest 子进程，宿主 pytest-cov 的默认 .coverage 数据文件可能被子进程写入的
	# 非分支数据污染（实测报 "Can't combine branch coverage data with statement data"
	# 的 coverage INTERNALERROR）。隔离后 coverage.xml 仍落在仓库根供对账消费。
	rm -f .coverage.ci .coverage.ci.*
	COVERAGE_FILE=$(CURDIR)/.coverage.ci $(PY) -m pytest tests/ -n 4 --dist loadfile --cov=src --cov-branch --cov-report=term-missing --cov-report=xml

docs-check:  ## 双语文档同步 + 文档链接完整性门禁（strict，CI 阻断项）
	$(PY) scripts/gates/check_bilingual_docs.py --strict
	$(PY) scripts/gates/check_doc_links.py --strict

env-budget:  ## 环境变量开关预算棘轮（CI 阻断项）
	$(PY) scripts/gates/check_env_budget.py --check

baseline-check:  ## BASELINE.yaml 结构 + 文档数字漂移守卫
	$(PY) scripts/gates/check_baseline.py
	$(PY) scripts/gates/check_baseline_numbers.py

state-contract:  ## LangGraph 状态通道静态契约守卫（AK4 接入 CI）
	$(PY) scripts/gates/check_state_contract.py

env-snapshot:  ## 环境开关 provenance 完备性守卫（E-B，接入 CI）
	$(PY) scripts/gates/check_env_snapshot_keys.py

model-fingerprint:  ## 模型版本指纹锁定守卫（S29，接入 CI；默认仅扫近期批次）
	$(PY) scripts/gates/check_model_fingerprint.py

json-contract-sites:  ## JSON 契约调用点计数一致性（EMSE 批次 2026-10-15：口径 A=7，防文档 6/7 分裂）
	$(PY) scripts/gates/check_json_contract_sites.py

json-strict:  ## 全仓严格 JSON（AF 轮：工件拒绝裸 NaN/Infinity + 源码写入点 allow_nan=False）
	$(PY) scripts/gates/check_json_strict.py

prompt-artifacts:  ## Instruction artifact 清单生成（逐字抽取 + sha256；新增 prompt 后必须重跑）
	$(PY) -m experiments.prompt_artifacts

prompt-artifacts-check:  ## Instruction artifact 哈希锁（清单与源码逐位一致；strict 要求清单存在）
	$(PY) scripts/gates/check_prompt_artifacts.py --strict

artifact-doc-consistency:  ## 报告→工件数值对账（两个数字族：mutation×detection 表逐格 + T-10 匹配子集严格口径声明；源批次在场时现场再生成）
	# G6（2026-10-16）：本地不加 --require-coverage——coverage.xml 缺席时登记册
	# 对账打 [SKIP]（明示"未对账"，不谎报 [OK]）。CI 在覆盖率集群里以
	# --require-coverage 强制该支路（缺席即红）。
	$(PY) scripts/gates/check_artifact_doc_consistency.py

zero-assert:  ## 零断言测试守卫（U3，CI 阻断项；K 轮补入本地 gates，此前 HEAD 曾因此红而不自知）
	$(PY) scripts/gates/check_zero_assert_tests.py

ast-guards:  ## ast.parse 守卫捕获面棘轮（BK 轮，CI 阻断项：新增单腿守卫=抛穿 ValueError 族；豁免只允许变短）
	$(PY) scripts/gates/check_ast_parse_guards.py

status-persistence:  ## 状态通道落盘可达性棘轮（BN 轮，CI 阻断项：声明了却不落盘=归档里 0 出现、事后不可复核；豁免清单为空）
	$(PY) scripts/gates/check_status_persistence.py

self-mutation:  ## 自身测试套件变异测试（零 LLM；临时副本内变异；默认 3 个核心模块等距抽样 120/文件）
	$(PY) scripts/tools/self_mutation.py

self-mutation-ci:  ## 自身变异测试 CI 门禁口径（env_utils+atomic_io，阈值 0.85，约 2-4 分钟）
	# --test-map 必须显式接入击杀批次测试 tests/test_self_mutation_targets.py：
	# 自动发现只按模块名匹配（test_<stem>.py），击杀测试不在该命名族里；
	# 漏接的后果是门禁回退到"击杀前"分数（实测 env 0.8889 / atomic 0.3810，
	# 合计 0.7467 会被阈值 0.85 判红——这不是测试变弱，是测试集合选错）。
	$(PY) scripts/tools/self_mutation.py --files src/utils/env_utils.py,src/utils/atomic_io.py \
		--workers 2 --max-mutants 60 --fail-under 0.85 \
		--test-map src/utils/env_utils.py=tests/test_env_utils.py,tests/test_self_mutation_targets.py \
		--test-map src/utils/atomic_io.py=tests/test_atomic_io.py,tests/test_self_mutation_targets.py \
		--json-out experiments/results/self_mutation_ci/gate.json \
		--md-out experiments/results/self_mutation_ci/gate.md

preflight:  ## 批次跑批前置闸（配额预算 + 模型指纹 + 工作树 + 孤儿进程；零 LLM；strict 语义见脚本）
	$(PY) scripts/tools/run_preflight.py --strict

proc-hygiene:  ## 孤儿嵌套测试子进程巡检（只读；--kill 清理需手动，防 CPU 空转污染批次）
	$(PY) scripts/tools/detect_orphan_procs.py

perf-bench:  ## 性能基准跑分（写 experiments/results/performance_benchmark.json；perf.yml 同口径）
	$(PY) scripts/tools/performance_benchmark.py

perf-check:  ## 性能回归比对（默认 non-blocking 告警；本地同机排查可加 --strict）
	$(PY) scripts/gates/check_perf_regression.py --current experiments/results/performance_benchmark.json

tool-versions:  ## CI/pre-commit/lock 三方工具版本一致守卫（AK4 接入 CI）
	$(PY) scripts/gates/check_tool_versions.py

gates: lint format typecheck test docs-check env-budget baseline-check state-contract env-snapshot model-fingerprint tool-versions json-contract-sites json-strict artifact-doc-consistency zero-assert ast-guards status-persistence  ## 本地全部门禁（合并前自检；format = ruff format --check，2026-10-12 质量债清偿批次补入；zero-assert = K 轮补入，此前 CI 阻断但本地 gates 缺席；json-strict = AF 轮补入；ast-guards = BK 轮补入，捕获面棘轮；status-persistence = BN 轮补入，落盘可达性棘轮）

repro:  ## 复现主批次（详见 reproduce.sh；消耗 LLM 配额，勿自动触发）
	bash reproduce.sh

reproduce-zero-llm:  ## 零 LLM 复算链（EMSE Open Science 复制包 L0：统计扩展/口径矩阵/引用核验 + SHA256SUMS 校验，产出 REPRODUCTION_REPORT）
	$(PY) scripts/reproduce_zero_llm.py

reproduce-zero-llm-l1:  ## 零 LLM 复算链 L1（含小时级 cosmic-ray Mut@k 全量重算）
	$(PY) scripts/reproduce_zero_llm.py --level l1

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

mutation-det-correlation:  ## mutation × detection 交叉验证（EMSE 批次 2026-10-15：构念效度辅助证据 + 饱和纪律，零 LLM 只读工件）
	$(PY) -m experiments.emse_optimization --mutation-correlation experiments/results/main_batch --out experiments/results/main_batch/mutation_detection_correlation.md

swebench-disclosure:  ## SWE-bench Lite 基础设施失败披露（EMSE 批次 2026-10-15：四分账 + 无有效能力结论，零 LLM）
	$(PY) -m experiments.emse_optimization --swebench-disclosure --out experiments/results/emse_swebench_disclosure.md

pass-matched:  ## 通过率混淆敏感性分析（EMSE 审稿人 A3 复核点：成功声明率 + 条件口径 + 模板匹配子集，零 LLM）
	$(PY) -m experiments.pass_matched_sensitivity

emse-stats:  ## 统计报告补口（EMSE 批次 2026-10-15：三主要对比 MDE/功效 + 比例型端点 bootstrap 95% CI，零 LLM 只读工件）
	$(PY) -m experiments.emse_stats_report

# O-4（2026-10-18）：CI 零 LLM 作业 `.github/workflows/ci.yml::e2e-probe` 与本目标
# 同口径（同命令、只跑零 LLM 子集；CI 额外准备 pinned QuixBugs 数据 + chromadb
# 嵌入预热，产出报告走 artifact）。合并前建议本地先跑 `make e2e-probe`。
e2e-probe:  ## 全功能端到端探针（零 LLM 子集；功能矩阵报告）
	@# O-4（2026-10-18）：与 CI 零 LLM 作业同口径的嵌套 pytest 确定性钩子。
	@# 根因：executor-repo-verify 的 baseline/补丁两阶段在 1s 内写同尺寸源码时，
	@# pyc 头 (源 mtime 整秒, size) 不变 → 第二轮复用 baseline 字节码 → 随机假红
	@# （本地实测 6/15）。RepoExecutor 的嵌套 pytest 走 scrub_os_environ 白名单，
	@# 不透传 PYTHONDONTWRITEBYTECODE；故用 PYTHONPATH 注入 sitecustomize 置
	@# sys.dont_write_bytecode=True（CI 同机制，见 ci.yml e2e-probe job 注释）。
	@_ci_site=$$(mktemp -d) && \
	printf 'import sys\nsys.dont_write_bytecode = True\n' > "$$_ci_site/sitecustomize.py" && \
	PYTHONPATH="$$_ci_site" PYTHONDONTWRITEBYTECODE=1 \
	$(PY) scripts/tools/e2e_probe.py --all --json-out experiments/results/e2e_probe_latest.json --md-out experiments/results/e2e_probe_latest.md; \
	_rc=$$?; rm -rf "$$_ci_site"; exit $$_rc

e2e-probe-llm:  ## 全功能端到端探针（含真实 LLM 探针；消耗配额，默认不接 CI）
	AITESTER_E2E_LLM=true $(PY) scripts/tools/e2e_probe.py --all --include-llm --json-out experiments/results/e2e_probe_llm_latest.json --md-out experiments/results/e2e_probe_llm_latest.md

paper-audit:  ## 论文草稿数字-SRC 一致性审计（Q11 独立评审；本地工具，paper/ 不入库，缺失时跳过）
	$(PY) scripts/tools/audit_paper_numbers.py --md docs/emse/PAPER_CONSISTENCY_AUDIT_2026-10-17.md --strict

build-check:  ## 发行构建链路冒烟（AS 批 2026-10-07：build wheel → 全新 venv 安装 → CLI/import 冒烟；本地验证用，未接 CI——发布批次 AL9 再定）
	$(PY) -m build --wheel
	rm -rf /tmp/aitester_build_check
	python3 -m venv /tmp/aitester_build_check
	/tmp/aitester_build_check/bin/pip install --quiet dist/*.whl
	/tmp/aitester_build_check/bin/aitester --version
	/tmp/aitester_build_check/bin/python -c "import config, src; from src.cli.app import cli; print('build-check OK: wheel 安装/入口/导入全部正常')"
