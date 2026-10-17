# N-1 全功能端到端探针报告（workflow / CLI / agents / repair / safety）

> **性质**：N 轮 N-1 功能清单级 e2e 探针的实跑工件（不是正式实验证据）。
> 引擎：`scripts/tools/e2e_probe.py`（框架）；本组探针：
> `scripts/tools/e2e_probes_workflow.py`（23 个探针，7 个真实 LLM）。
> 报告由框架直出：`report_zero_llm.json`（零 LLM 子集）、`report.json` /
> `report.md`（全量 + 真实 LLM）。
>
> **运行环境（如实披露）**：2026-10-17 22:43–23:00（Asia/Shanghai）；HEAD
> `f194d679aaaba1c2fa97ef80fd53dbf47de203a9`（M 轮收口提交）+ **N 轮并发
> 未提交工作树**（同批 N-2/N-3 队友在改 src/agents/executor*、
> src/agents/kernel_sandbox、src/graph/nodes|state、experiments/run_benchmark 等；
> 探针工件对应 23:00:39 时刻的工作树状态，不是某个干净 commit 的冻结快照）；
> Python 3.14.6；模型 `deepseek-flash`（`LLM_THINKING_MODE=disabled` 由探针
> 强制，`AITESTER_LLM_CACHE=0` 由框架强制 → 全部真实调用、无缓存重放）。

## 1. 命令（可复现）

```bash
# 探针清单
.venv/bin/python scripts/tools/e2e_probe.py --module scripts.tools.e2e_probes_workflow --list

# 零 LLM 子集（16 探针全跑）
.venv/bin/python scripts/tools/e2e_probe.py --module scripts.tools.e2e_probes_workflow --all \
  --json-out experiments/results/e2e_probe_workflow_20261017/report_zero_llm.json

# 全量（含 7 个真实 LLM 探针；需 AITESTER_E2E_LLM=true）
AITESTER_E2E_LLM=true .venv/bin/python scripts/tools/e2e_probe.py \
  --module scripts.tools.e2e_probes_workflow --all --include-llm \
  --json-out experiments/results/e2e_probe_workflow_20261017/report.json \
  --md-out experiments/results/e2e_probe_workflow_20261017/report.md
```

## 2. 结果矩阵（23/23 pass，0 fail / 0 error / 0 skip）

| 组 | 探针 | LLM | 状态 | 关键断言 |
|---|---|---|---|---|
| cli | cli-help | 否 | pass | `--help` rc=0；run/list-examples/check-dataset/clean-venv-cache 在帮助面 |
| cli | cli-list-examples | 否 | pass | 列出 5 个可运行示例（**不含 `__init__.py`**）；建议 `examples/calculator.py` |
| cli | cli-check-dataset-quixbugs | 否 | pass | 加载 50 任务 + 全量质量检查通过（见 §4 缺陷 D3 观测） |
| cli | cli-run-json-single | 是 | pass | `run examples/calculator.py --json --verbose`：stdout **单一合法 JSON**、rc=0/1（实测 passed=True rc=0） |
| cli | cli-run-multi-parallel | 是 | pass | 两文件 `--parallel 2 --json`：2 份 JSON 均可逐份解析、rc=0 |
| workflow | workflow-fast-assembly | 否 | pass | fast 档 5 节点/8 边；无 mutation_advisor/diagnosis/cross_file |
| workflow | workflow-logic-assembly | 否 | pass | logic 档 6 节点；`executor→mutation_advisor→generator` 环在场；profile 预设（DETECTION_FIRST/FL_SPECTRAL）已注入 |
| workflow | workflow-logic-invoke | 是 | pass | logic 档真 invoke：test_plan/generated_test/execution_trace/stop_reason=`test_passed` 齐全 |
| agents | agents-planner-structured-plan | 是 | pass | 真实 LLM 输出结构化 test_cases + logic_analysis（logic_degraded=False） |
| agents | agents-generator-parseable-tests | 是 | pass | 真实 LLM 生成可解析 pytest（3 个 test 函数、import/assert 齐全） |
| agents | agents-executor-run | 否 | pass | 本地沙箱：通过用例 passed=True/coverage=100%，失败用例可归因（failed_cases） |
| repair | repair-debugger-patch-chain | 是 | pass | Debugger 真实产出补丁→安全应用→修复后测试通过 |
| repair | repair-graph-loop | 是 | pass | **真实 graph 修复环**：executor 失败→debugger(1 轮)→patch_applier 写盘→复跑通过（stop_reason=test_passed） |
| safety | safety-dangerous-api-guard | 否 | pass | `os.system` / `from os import system` 别名 / `eval` 三种危险补丁全部拒绝应用；正常补丁放行 |
| safety | safety-naming-contract-guard | 否 | pass | 删除模块级符号：apply 层保守拒绝 + 契约检查 missing=['g'] 双拦截 |
| safety | safety-test-hacking-detection | 否 | pass | 删断言/硬编码输入分支/新增吞异常三信号命中；正常补丁零误报 |
| safety | safety-deterministic-repair | 否 | pass | NameError→缺 import 零 LLM 产出合法补丁；无匹配场景显式 abstain |
| safety | safety-patch-rollback | 否 | pass | P2P 回归失败自动回滚到原文；通过则保留；开关默认关/开启生效 |
| observability | observability-trace-redaction | 否 | pass | trace JSONL task_start/node/task_end 三事件落盘；`sk-...` 假凭据脱敏为 `REDACTED` |
| observability | observability-event-bus | 否 | pass | 发布→订阅回调/计数一致；`EVENT_BUS_ENABLE=false` 时 no-op |
| localization | analysis-fl-spectral-topk | 否 | pass | Ochiai 打分 Top-1 命中注入缺陷分支行（Top-k=[5,2,3]） |
| localization | analysis-fault-localizer-gold | 否 | pass | gold 反事实定位 find_max 命中，Hit@1/@3=true、MRR=1.0 |
| localization | analysis-multi-candidate | 否 | pass | 静态筛选通过/拒绝正确；大改动 vs 最小改动候选择优 index=1 |

## 3. 真实 LLM 调用与成本（≤$0.3 预算内）

- **调用总数 ≈ 11 次**：5 个 LLM 探针进程内记账 8 次（workflow-logic-invoke 2、
  planner 1、generator 1、repair-debugger-chain 1、repair-graph-loop 3）+
  CLI 子进程内 3 次（单文件 1 + 多文件 2；CLI 孙进程 token 记账不可见，按
  典型 generator prompt 保守估）。
- 进程内实测 token：**12,897**（input 9,797 / output 3,100）。
- 成本上界估算（deepseek-flash 标准价：$0.3/M in、$1.2/M out，
  `experiments/price_table.json`）：**≈ $0.0093**（含 CLI 推定 token 后
  in≈13,697 / out≈4,300）。远低于 N-1 预算 $0.3 与框架建议 <$0.05。
- 说明：`repair-graph-loop` 实测 3 次调用（generator 偶发 parametrize 校验
  重试 +1），略超"每探针 ≤2 次"建议值但成本可忽略；其余 LLM 探针均 ≤2 次。

## 4. 发现的缺陷（3 项：2 项本写域已修复 + 1 项跨写域上报）

### D1（已修复，本写域 src/cli/）`run --json --verbose` 污染 stdout

- **复现**（修复前）：`.venv/bin/python main.py run examples/calculator.py --json --verbose`
  → stdout 首行为 `ℹ 提示：--json 模式下控制台日志被静音...`，其后才是 JSON；
  `... | jq` 首行解析失败。
- **观察 vs 期望**：观察 = 提示经 `info_msg`（stdout）；期望 = `--json` 模式
  stdout 只承载 JSON（`_quiet_console_logs` docstring 明确承诺、rich 进度条
  也特意走 stderr）。
- **定位**：`src/cli/app.py:597-607`（`run` 的 verbose+json 分支）。
- **修复**：提示改走 stderr（`click.echo(..., err=True)`）；非 JSON 模式的
  verbose 提示路径不变。
- **回归**：`tests/test_n_round_workflow_cli.py::TestJsonVerboseStdoutPurity`
  （3 例：单文件纯 JSON、无 verbose 纯 JSON、多文件逐份可解析）；
  探针 `cli-run-json-single` 已把 `--json --verbose` 组合纳入常规回归面。

### D2（已修复，本写域 src/cli/）`list-examples` 推荐不可运行文件

- **复现**（修复前）：`.venv/bin/python main.py list-examples`
  → 列出 `__init__.py` 且"使用示例"建议 `python main.py run examples/__init__.py`
  （空模块，用户按提示执行得到无意义任务）。
- **观察 vs 期望**：期望只列可运行示例文件、建议主推示例（calculator.py）。
- **定位**：`src/cli/app.py:762-775`（`list_examples`）。
- **修复**：过滤下划线开头文件；使用示例优先 `calculator.py`。
- **回归**：`tests/test_n_round_workflow_cli.py::TestListExamplesCleanliness`
  （3 例）；探针 `cli-list-examples` 断言清单无下划线文件、建议非 dunder。

### D3（未修复：跨写域，上报 Lead / N-2 平台组）日志脱敏误伤长路径段

- **复现**：`.venv/bin/python main.py check-dataset quixbugs --limit 2`
  → 输出 `gold 修复版目录：/Users/<user>/.<REDACTED_KEY>`；实际路径
  `/Users/<user>/.cache/aitester/quixbugs/correct_python_programs`。
- **最小复现（模块级）**：
  `.venv/bin/python -c "from src.utils.logging_utils import mask_sensitive_info; print(mask_sensitive_info('/tmp/.cache/aitester/quixbugs/correct_python_programs'))"`
  → `/tmp/.<REDACTED_KEY>`。
- **根因定位**：`src/utils/logging_utils.py:22-24` 的"长 base64 串（≥40 位）"
  脱敏模式 `([A-Za-z0-9+/=_-]{40,}={0,2})` 把点号后的长路径段（可含 `/`、`_`、
  字母数字，如 `cache/aitester/quixbugs/correct_python_programs` = 48 字符）
  误判为密钥。影响：控制台日志 / trace JSONL 中的长路径被替换为
  `<REDACTED_KEY>`，诊断可读性下降；不构成凭证泄露（属过度脱敏）。
- **建议修复**（N-2 写域 src/utils/）：base64 候选要求不含 `/` 或以 `=` 结尾
  等更严锚定；或对"路径上下文（前有 `/` 或 `.`）"豁免。修复后应补
  正/负控测试（路径不脱敏、真 base64 仍脱敏）。
- 本组探针 `cli-check-dataset-quixbugs` 已把它作为**观测项**（evidence
  `redacted_path_segments`）如实记录，不阻断功能判定。

## 5. 修复的回归测试与验证

| 项 | 结果 |
|---|---|
| `pytest tests/test_n_round_workflow_cli.py` | **6 passed**（D1 3 例 + D2 3 例） |
| `pytest tests/test_e2e_probes_workflow.py` | **56 passed**（清单契约 / 零 LLM 真实探针 / LLM 探针 mock / 负控分类 / 辅助函数） |
| CLI + 探针相关既有套件 | 168 passed（test_cli_app / test_cli_run / test_cli_parallel / test_cli_console_output / test_closeout_k_cli_app …） |
| `ruff check` + `ruff format --check`（目标文件） | All checks passed / already formatted |
| `mypy`（目标文件 src/cli/app.py + 两个测试 + 探针模块） | 目标文件无错误；仅剩既有依赖告警（src/agents/kernel_sandbox.py 1 处、框架 scripts/tools/e2e_probe.py 2 处，均非本轮改动） |

## 6. 限制（如实披露）

1. **单机单日/单模型**：结果对应当前 macOS 环境与 deepseek-flash；模型非确定性
   意味着 LLM 探针存在跨次波动（本次全绿，不代表任意重跑必全绿）。
2. **探针不是全功能矩阵**：N-1 覆盖用户主链（CLI/workflow/agents/repair/安全
   守卫/可观测/分析工具）；预算/缓存/RAG/安全套件/执行器模式/数据集等由 N-2
   `e2e_probes_platform.py` 覆盖，规约/oracle 链由 N-3 覆盖。
3. **repair 图链路预算**：`repair-graph-loop` 为控成本用 `planner=False +
   max_iterations=1`（真实 generator+debugger+patch_applier+executor，2–3 次
   调用）；planner→debugger 的 3 智能体全链路冒烟在 N-4 重型探针覆盖。
4. **工作树非冻结快照**：N 轮并发队友改动与本组工件同期存在（见文首
   环境披露）；本目录工件只对应报告 `generated_at` 时刻的工作树状态。
5. **D3 未修复**：跨写域（src/utils/ 属 N-2），按纪律只上报不擅自修改。

## 7. 文件与指纹

- `report.json` / `report.md`：全量 23 探针（真实 LLM，23:00:39 生成）。
- `report_zero_llm.json`：零 LLM 子集 16 pass / 7 skip（LLM 探针按纪律 skip）。
- `SHA256SUMS`：上述报告与 README 的内容哈希。
