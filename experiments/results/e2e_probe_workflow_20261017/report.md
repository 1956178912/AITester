# AITester 全功能端到端探针报告（N 轮）

> 引擎：`scripts/tools/e2e_probe.py`；LLM 探针：已启用（真实调用，缓存关闭）
> 汇总：**23 pass / 0 fail / 0 error / 0 skip**（共 23 探针）

## 功能矩阵

| 组 | 探针 | 状态 | LLM | 耗时(s) | 说明/证据 |
|---|---|---|---|---|---|
| agents | `agents-planner-structured-plan` | **pass** | 是 | 5.17 | planner 结构化计划正常（10 用例，logic_degraded=False） |
| agents | `agents-generator-parseable-tests` | **pass** | 是 | 2.51 | generator 生成可解析 pytest（530 字符，3 个测试函数） |
| agents | `agents-executor-run` | **pass** | 否 | 2.87 | executor 沙箱正常（通过用例 passed=True/coverage=100.0，失败用例失败可归因） |
| cli | `cli-help` | **pass** | 否 | 1.69 | CLI --help 正常，4 个子命令均在帮助面 |
| cli | `cli-list-examples` | **pass** | 否 | 1.71 | list-examples 正常，列出 5 个示例文件且建议 calculator.py |
| cli | `cli-check-dataset-quixbugs` | **pass** | 否 | 2.42 | check-dataset quixbugs 正常（50 任务 / 质量通过） |
| cli | `cli-run-json-single` | **pass** | 是 | 7.84 | CLI --json 输出合法 JSON（passed=True, rc=0） |
| cli | `cli-run-multi-parallel` | **pass** | 是 | 5.31 | 多文件 --parallel --json 正常（2 份结果，passed=2/2，rc=0） |
| localization | `analysis-fl-spectral-topk` | **pass** | 否 | 0.08 | FL_spectral 正常：Top-1 命中缺陷分支行 5（Top-k=[5, 2, 3]） |
| localization | `analysis-fault-localizer-gold` | **pass** | 否 | 1.18 | fault localizer 正常：gold 变更函数 find_max 命中（MRR=1.0） |
| localization | `analysis-multi-candidate` | **pass** | 否 | 0.09 | multi-candidate 正常：静态筛选通过/拒绝正确，最小改动候选 index=1 |
| observability | `observability-trace-redaction` | **pass** | 否 | 0.09 | trace 正常：JSONL 三事件落盘且敏感串已脱敏 |
| observability | `observability-event-bus` | **pass** | 否 | 0.08 | 事件总线正常：发布→订阅回调/计数一致，关闭开关后 no-op |
| repair | `repair-debugger-patch-chain` | **pass** | 是 | 5.25 | 修复链正常：Debugger 产出补丁 → 安全应用 → 修复后测试通过 |
| repair | `repair-graph-loop` | **pass** | 是 | 11.82 | 修复环正常：debugger 进入 1 轮 → patch_applier 应用 → 复跑通过（stop_reason=test_passed） |
| safety | `safety-dangerous-api-guard` | **pass** | 否 | 0.08 | 危险 API 守卫正常：os.system / from-import 别名 / eval 均拒绝，正常补丁放行 |
| safety | `safety-naming-contract-guard` | **pass** | 否 | 0.08 | 命名契约守卫正常：删除模块级符号被拒（契约检查 missing=['g'] + apply 保守拒绝） |
| safety | `safety-test-hacking-detection` | **pass** | 否 | 0.08 | 测试黑客检测正常：三类信号全部命中且正常补丁无误报 |
| safety | `safety-deterministic-repair` | **pass** | 否 | 0.09 | 确定性修复正常：NameError→import 零 LLM 产出补丁，无匹配场景显式 abstain |
| safety | `safety-patch-rollback` | **pass** | 否 | 1.93 | 快照回滚协议正常：P2P 失败自动回滚、通过则保留，开关默认关/开启生效 |
| workflow | `workflow-fast-assembly` | **pass** | 否 | 1.68 | fast 档装配正确（5 节点 / 8 边） |
| workflow | `workflow-logic-assembly` | **pass** | 否 | 1.64 | logic 档装配正确（6 节点，mutation_advisor 环在场，预设开关已注入） |
| workflow | `workflow-logic-invoke` | **pass** | 是 | 8.8 | logic 档 invoke 正常（stop_reason=test_passed，trace=1 条） |

## 失败/异常明细

（无）
