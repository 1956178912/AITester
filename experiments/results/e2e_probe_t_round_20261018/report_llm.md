# AITester 全功能端到端探针报告（N 轮）

> 引擎：`scripts/tools/e2e_probe.py`；LLM 探针：已启用（真实调用，缓存关闭）
> 汇总：**68 pass / 0 fail / 0 error / 0 skip**（共 68 探针）

## 功能矩阵

| 组 | 探针 | 状态 | LLM | 耗时(s) | 说明/证据 |
|---|---|---|---|---|---|
| agents | `agents-planner-structured-plan` | **pass** | 是 | 4.39 | planner 结构化计划正常（9 用例，logic_degraded=False） |
| agents | `agents-generator-parseable-tests` | **pass** | 是 | 2.51 | generator 生成可解析 pytest（690 字符，4 个测试函数） |
| agents | `agents-executor-run` | **pass** | 否 | 1.58 | executor 沙箱正常（通过用例 passed=True/coverage=100.0，失败用例失败可归因） |
| budget | `budget-cost-cap` | **pass** | 否 | 0.05 | 累计 120 tokens 超过 100 上限 → check_budget=False；events=1 |
| budget | `budget-invalid-fail-closed` | **pass** | 否 | 0.05 | 坏值/负值均 fail-closed；misconfigured_events=2 |
| budget | `budget-batch-quota` | **pass** | 否 | 0.05 | estimate(150)=968；未配置→blocking 2 条；上限 2000→ok；上限 100→拦截 |
| budget | `budget-llm-stop` | **pass** | 是 | 1.57 | 首次调用成功（'7'）；耗尽后第二次抛 BudgetExceededError（consumed=29） |
| cache | `cache-disabled` | **pass** | 否 | 0.89 | 文件缓存 enabled=False；语义缓存默认 enabled=False（精确缓存口径） |
| cache | `cache-two-call-hit` | **pass** | 是 | 2.13 | 两次同 prompt：第二次缓存命中（0.000s vs 首次 0.91s）；llm_calls=1, cache_hits=1, avoided_tokens=29 |
| cache | `cache-semantic-index` | **pass** | 否 | 0.76 | 语义索引 entries=1，同义命中 / 无关未命中（hits=1, misses=1） |
| cli | `cli-help` | **pass** | 否 | 1.07 | CLI --help 正常，4 个子命令均在帮助面 |
| cli | `cli-list-examples` | **pass** | 否 | 1.08 | list-examples 正常，列出 5 个示例文件且建议 calculator.py |
| cli | `cli-check-dataset-quixbugs` | **pass** | 否 | 1.48 | check-dataset quixbugs 正常（50 任务 / 质量通过） |
| cli | `cli-run-json-single` | **pass** | 是 | 6.66 | CLI --json 输出合法 JSON（passed=True, rc=0） |
| cli | `cli-run-multi-parallel` | **pass** | 是 | 5.94 | 多文件 --parallel --json 正常（2 份结果，passed=2/2，rc=0） |
| cli | `cli-doctor-json` | **pass** | 否 | 1.63 | doctor 零 LLM 自检正常（checks=6，matrix pass=3，stdout 纯 JSON） |
| dataset | `dataset-loaders` | **pass** | 否 | 0.7 | 三加载器真实加载 0.01s：quixbugs=50 / examples=3 / synthetic=3 |
| dataset | `dataset-ult` | **pass** | 否 | 0.68 | ULT 加载 200 任务；样例 task_id=['ult__is_degree_in_degree_range', 'ult__BinaryFromFraction', 'ult__fix_labels'] |
| dataset | `dataset-decontamination` | **pass** | 否 | 0.69 | 去污染口径正确：total=3 kept=1 dropped=1 unverifiable=1；decontamination_rate=0.5 |
| dataset | `dataset-check-cli` | **pass** | 否 | 1.92 | check-dataset CLI 1.9s rc=0，质量检查 50 个任务无加载问题 |
| executor | `executor-local` | **pass** | 否 | 1.07 | 本地执行器 1.02s 通过最小测试（coverage=100.0，failed_cases=0） |
| executor | `executor-venv` | **pass** | 否 | 0.83 | venv 执行器 0.78s 通过最小测试（coverage=100.0） |
| executor | `executor-docker-degrade` | **pass** | 否 | 0.07 | 无 docker CLI → passed=False + error_info.type=docker_unavailable（明确降级，未静默回退本地） |
| executor | `executor-repo-verify` | **pass** | 否 | 1.87 | 临时仓库 verify 全链路 1.7s：test_patch 基线红 → llm_patch 后 F2P 1/1 转绿 → passed=True |
| executor | `executor-kernel-sandbox` | **pass** | 否 | 1.98 | KERNEL_SANDBOX_ENABLE=true：local + venv 执行器真实跑通（passed/coverage/obs 齐备），总耗时 1.93s |
| localization | `analysis-fl-spectral-topk` | **pass** | 否 | 0.04 | FL_spectral 正常：Top-1 命中缺陷分支行 5（Top-k=[5, 2, 3]） |
| localization | `analysis-fault-localizer-gold` | **pass** | 否 | 0.59 | fault localizer 正常：gold 变更函数 find_max 命中（MRR=1.0） |
| localization | `analysis-multi-candidate` | **pass** | 否 | 0.04 | multi-candidate 正常：静态筛选通过/拒绝正确，最小改动候选 index=1 |
| logic | `logic-spec-ir-parse` | **pass** | 否 | 0.05 | SpecIR 双通道解析正常，空材料保守降级 |
| logic | `logic-spec-expr-whitelist` | **pass** | 否 | 0.06 | 白名单正常：危险子句拒绝 3/3，可编译子句接受，readiness=1.00 |
| logic | `logic-spec-oracle-compile` | **pass** | 否 | 0.05 | 确定性 oracle 编译正常（489 字符，2 条断言，ast 合法） |
| logic | `logic-smt-witness` | **pass** | 否 | 0.08 | SMT 见证层正常：2 个见证（kinds=['boundary_max', 'sat']），不可翻译保守降级 |
| logic | `logic-spec-anchor-oracle-wiring` | **pass** | 否 | 1.13 | spec_anchor 接线正常：verdict=compiled_empty，injected=False；无材料负控 not_attempted |
| logic | `logic-oracle-independent-judging` | **pass** | 否 | 0.1 | oracle 独立判读字段/函数/replay 入口齐备，None 输入 fail-closed，设计文档已登记 |
| logic | `logic-stagnation-switch` | **pass** | 否 | 1.74 | 停滞开关正常（default=False，env true→True/false→False，消融臂互斥） |
| logic | `logic-mutation-advisor-assembly` | **pass** | 否 | 1.34 | mutation advisor 环装配正确（开=7 节点 / 关=6 节点） |
| logic | `logic-branch-coverage-inject` | **pass** | 否 | 0.86 | branch 覆盖测量真实可用（coverage=25.0%，missing=3，开关默认=False） |
| logic | `logic-oracle-instrument-safety` | **pass** | 否 | 0.62 | oracle 仪器加固生效：崩溃→skip（rc=0），静态 harness 齐备 |
| logic | `logic-oracle-replay-instrument-breakdown` | **pass** | 否 | 0.06 | replay 分类细化正常：fp=2（断言型）、instrument_error=0、skipped=27，旧四分类键保留 |
| logic | `logic-oracle-precondition-input-filter` | **pass** | 否 | 0.06 | 前件校验输入选择生效：跳过违反 side>0 的候选，绑定合法候选 side=3 |
| logic | `logic-oracle-examples-compile` | **pass** | 否 | 0.06 | 示例通道编译正常（1078 字符、examples=1、崩溃安全、无 eval/exec） |
| logic | `logic-oracle-examples-detection` | **pass** | 否 | 1.7 | 示例 oracle 检出能力正确：buggy rc=1（检出）/ fixed rc=0 / 无示例对照 rc=0（不检出） |
| logic | `logic-oracle-examples-production` | **pass** | 否 | 1.76 | Q-1 生产接线契约齐备（双门默认关/prompt 段/行字段/env 登记） |
| logic | `logic-examples-self-validation` | **pass** | 否 | 0.05 | 示例自校验正常（矛盾示例丢弃/safe-AST 危险子句保留/env 开关） |
| logic | `logic-examples-multisample` | **pass** | 否 | 0.05 | 多采样自一致性正常（归一化键/求交/审计/单采样 API 保持） |
| logic | `logic-profile-spec-fields` | **pass** | 是 | 7.65 | logic 档 spec 链路正常（6.4s，compile_rate=1.0，generated_test=有） |
| logic | `logic-stagnation-precedence` | **pass** | 否 | 1.04 | A-19 抢占优先级正常：默认关 repair-invalid 平局历史口径不变；ON 时停滞优先（done/coverage_stall） |
| logic | `logic-rollback-schema-fields` | **pass** | 否 | 1.7 | 回滚 verdict schema 正常：两分支键集合同构、含 patch_rollback_verdict/patch_rolled_back、投影与占位语义正确、可落盘 |
| observability | `observability-trace-redaction` | **pass** | 否 | 0.05 | trace JSONL 3 行（task_start/node/task_end 齐全）且假凭证已脱敏 |
| observability | `observability-event-bus` | **pass** | 否 | 0.05 | 事件发布/订阅/计数正常；EVENT_BUS_ENABLE=false 时 no-op（消融口径可用） |
| observability | `observability-model-fingerprint` | **pass** | 是 | 2.73 | 模型指纹 0.98s：alias=deepseek-flash returned=deepseek-flash pinned=True probe=fc3d915941b8… |
| observability | `observability-postprocess-wall` | **pass** | 否 | 1.74 | 后处理墙钟模块正常（稳定 JSON/线性分位/env 回退）+ run_benchmark hook 已接入 |
| rag | `rag-retriever` | **pass** | 否 | 0.76 | 检索器初始化 0.05s；写入 1 案例后检索到 1 条（top similarity=0.7143） |
| rag | `rag-workflow-stats` | **pass** | 是 | 4.83 | ENABLE_RAG 下最小任务 3.4s 完成；rag_stats 1 条（kinds=['test_cases']）；generated_test 1427 字符 |
| repair | `repair-debugger-patch-chain` | **pass** | 是 | 3.8 | 修复链正常：Debugger 产出补丁 → 安全应用 → 修复后测试通过 |
| repair | `repair-graph-loop` | **pass** | 是 | 9.15 | 修复环正常：debugger 进入 1 轮 → patch_applier 应用 → 复跑通过（stop_reason=test_passed） |
| safety | `safety-dangerous-api-guard` | **pass** | 否 | 0.05 | 危险 API 守卫正常：os.system / from-import 别名 / eval 均拒绝，正常补丁放行 |
| safety | `safety-naming-contract-guard` | **pass** | 否 | 0.05 | 命名契约守卫正常：删除模块级符号被拒（契约检查 missing=['g'] + apply 保守拒绝） |
| safety | `safety-test-hacking-detection` | **pass** | 否 | 0.04 | 测试黑客检测正常：三类信号全部命中且正常补丁无误报 |
| safety | `safety-deterministic-repair` | **pass** | 否 | 0.04 | 确定性修复正常：NameError→import 零 LLM 产出补丁，无匹配场景显式 abstain |
| safety | `safety-patch-rollback` | **pass** | 否 | 0.96 | 快照回滚协议正常：P2P 失败自动回滚、通过则保留，开关默认关/开启生效 |
| security | `security-injection-guard` | **pass** | 否 | 0.05 | 3 类注入全检出、干净文本零误报、警示文本含【安全警示】；危险补丁 os.system/eval 检出、安全补丁零误报 |
| security | `security-credential-scrub` | **pass** | 否 | 0.1 | 白名单最小环境剔除全部 6 个假凭证键；子进程 env 无 LLM_*/*_API_KEY；provider 名单 10 项 |
| security | `security-log-redaction` | **pass** | 否 | 0.05 | 3 条含假凭证日志经 handler 后均脱敏（输出 81 字符，占位符在场）；3 条长路径样本零误伤（D3 修复回归） |
| security | `security-kernel-sandbox` | **pass** | 否 | 0.07 | 内核沙箱可用（seatbelt，platform=darwin）：/bin/echo 在沙箱内真实执行 0.01s rc=0；profile 无双引号缺陷 |
| workflow | `workflow-fast-assembly` | **pass** | 否 | 1.09 | fast 档装配正确（5 节点 / 8 边） |
| workflow | `workflow-logic-assembly` | **pass** | 否 | 1.06 | logic 档装配正确（6 节点，mutation_advisor 环在场，预设开关已注入） |
| workflow | `workflow-logic-invoke` | **pass** | 是 | 8.31 | logic 档 invoke 正常（stop_reason=unknown，trace=1 条） |

## 失败/异常明细

（无）
