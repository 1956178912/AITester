# AITester 全功能端到端探针报告（N 轮）

> 引擎：`scripts/tools/e2e_probe.py`；LLM 探针：已启用（真实调用，缓存关闭）
> 汇总：**56 pass / 0 fail / 0 error / 0 skip**（共 56 探针）

## 功能矩阵

| 组 | 探针 | 状态 | LLM | 耗时(s) | 说明/证据 |
|---|---|---|---|---|---|
| agents | `agents-planner-structured-plan` | **pass** | 是 | 4.57 | planner 结构化计划正常（8 用例，logic_degraded=False） |
| agents | `agents-generator-parseable-tests` | **pass** | 是 | 3.03 | generator 生成可解析 pytest（792 字符，5 个测试函数） |
| agents | `agents-executor-run` | **pass** | 否 | 2.74 | executor 沙箱正常（通过用例 passed=True/coverage=100.0，失败用例失败可归因） |
| budget | `budget-cost-cap` | **pass** | 否 | 0.08 | 累计 120 tokens 超过 100 上限 → check_budget=False；events=1 |
| budget | `budget-invalid-fail-closed` | **pass** | 否 | 0.08 | 坏值/负值均 fail-closed；misconfigured_events=2 |
| budget | `budget-batch-quota` | **pass** | 否 | 0.08 | estimate(150)=968；未配置→blocking 2 条；上限 2000→ok；上限 100→拦截 |
| budget | `budget-llm-stop` | **pass** | 是 | 2.21 | 首次调用成功（'7'）；耗尽后第二次抛 BudgetExceededError（consumed=29） |
| cache | `cache-disabled` | **pass** | 否 | 1.18 | 文件缓存 enabled=False；语义缓存默认 enabled=False（精确缓存口径） |
| cache | `cache-two-call-hit` | **pass** | 是 | 2.28 | 两次同 prompt：第二次缓存命中（0.000s vs 首次 0.79s）；llm_calls=1, cache_hits=1, avoided_tokens=29 |
| cache | `cache-semantic-index` | **pass** | 否 | 1.01 | 语义索引 entries=1，同义命中 / 无关未命中（hits=1, misses=1） |
| cli | `cli-help` | **pass** | 否 | 1.79 | CLI --help 正常，4 个子命令均在帮助面 |
| cli | `cli-list-examples` | **pass** | 否 | 1.68 | list-examples 正常，列出 5 个示例文件且建议 calculator.py |
| cli | `cli-check-dataset-quixbugs` | **pass** | 否 | 2.43 | check-dataset quixbugs 正常（50 任务 / 质量通过） |
| cli | `cli-run-json-single` | **pass** | 是 | 7.94 | CLI --json 输出合法 JSON（passed=True, rc=0） |
| cli | `cli-run-multi-parallel` | **pass** | 是 | 5.24 | 多文件 --parallel --json 正常（2 份结果，passed=2/2，rc=0） |
| dataset | `dataset-loaders` | **pass** | 否 | 1.15 | 三加载器真实加载 0.02s：quixbugs=50 / examples=3 / synthetic=3 |
| dataset | `dataset-ult` | **pass** | 否 | 1.15 | ULT 加载 200 任务；样例 task_id=['ult__is_degree_in_degree_range', 'ult__BinaryFromFraction', 'ult__fix_labels'] |
| dataset | `dataset-decontamination` | **pass** | 否 | 1.15 | 去污染口径正确：total=3 kept=1 dropped=1 unverifiable=1；decontamination_rate=0.5 |
| dataset | `dataset-check-cli` | **pass** | 否 | 2.78 | check-dataset CLI 2.7s rc=0，质量检查 50 个任务无加载问题 |
| executor | `executor-local` | **pass** | 否 | 1.69 | 本地执行器 1.61s 通过最小测试（coverage=100.0，failed_cases=0） |
| executor | `executor-venv` | **pass** | 否 | 1.15 | venv 执行器 1.07s 通过最小测试（coverage=100.0） |
| executor | `executor-docker-degrade` | **pass** | 否 | 0.1 | 无 docker CLI → passed=False + error_info.type=docker_unavailable（明确降级，未静默回退本地） |
| executor | `executor-repo-verify` | **pass** | 否 | 2.58 | 临时仓库 verify 全链路 2.4s：test_patch 基线红 → llm_patch 后 F2P 1/1 转绿 → passed=True |
| executor | `executor-kernel-sandbox` | **pass** | 否 | 2.91 | KERNEL_SANDBOX_ENABLE=true：local + venv 执行器真实跑通（passed/coverage/obs 齐备），总耗时 2.79s |
| localization | `analysis-fl-spectral-topk` | **pass** | 否 | 0.08 | FL_spectral 正常：Top-1 命中缺陷分支行 5（Top-k=[5, 2, 3]） |
| localization | `analysis-fault-localizer-gold` | **pass** | 否 | 1.28 | fault localizer 正常：gold 变更函数 find_max 命中（MRR=1.0） |
| localization | `analysis-multi-candidate` | **pass** | 否 | 0.08 | multi-candidate 正常：静态筛选通过/拒绝正确，最小改动候选 index=1 |
| logic | `logic-spec-ir-parse` | **pass** | 否 | 0.08 | SpecIR 双通道解析正常，空材料保守降级 |
| logic | `logic-spec-expr-whitelist` | **pass** | 否 | 0.08 | 白名单正常：危险子句拒绝 3/3，可编译子句接受，readiness=1.00 |
| logic | `logic-spec-oracle-compile` | **pass** | 否 | 0.08 | 确定性 oracle 编译正常（248 字符，2 条断言，ast 合法） |
| logic | `logic-smt-witness` | **pass** | 否 | 0.11 | SMT 见证层正常：2 个见证（kinds=['boundary_max', 'sat']），不可翻译保守降级 |
| logic | `logic-spec-anchor-oracle-wiring` | **pass** | 否 | 1.64 | spec_anchor 接线正常：verdict=compiled_empty，injected=False；无材料负控 not_attempted |
| logic | `logic-oracle-independent-judging` | **pass** | 否 | 0.16 | oracle 独立判读字段/函数/replay 入口齐备，None 输入 fail-closed，设计文档已登记 |
| logic | `logic-stagnation-switch` | **pass** | 否 | 2.62 | 停滞开关正常（default=False，env true→True/false→False，消融臂互斥） |
| logic | `logic-mutation-advisor-assembly` | **pass** | 否 | 1.87 | mutation advisor 环装配正确（开=7 节点 / 关=6 节点） |
| logic | `logic-branch-coverage-inject` | **pass** | 否 | 1.1 | branch 覆盖测量真实可用（coverage=25.0%，missing=3，开关默认=False） |
| logic | `logic-profile-spec-fields` | **pass** | 是 | 14.87 | logic 档 spec 链路正常（12.9s，compile_rate=1.0，generated_test=有） |
| observability | `observability-trace-redaction` | **pass** | 否 | 0.09 | trace 正常：JSONL 三事件落盘且敏感串已脱敏 |
| observability | `observability-event-bus` | **pass** | 否 | 0.08 | 事件总线正常：发布→订阅回调/计数一致，关闭开关后 no-op |
| observability | `observability-model-fingerprint` | **pass** | 是 | 3.72 | 模型指纹 1.06s：alias=deepseek-flash returned=deepseek-flash pinned=True probe=fc3d915941b8… |
| rag | `rag-retriever` | **pass** | 否 | 0.98 | 检索器初始化 0.07s；写入 1 案例后检索到 1 条（top similarity=0.7143） |
| rag | `rag-workflow-stats` | **pass** | 是 | 6.03 | ENABLE_RAG 下最小任务 4.1s 完成；rag_stats 1 条（kinds=['test_cases']）；generated_test 1361 字符 |
| repair | `repair-debugger-patch-chain` | **pass** | 是 | 6.13 | 修复链正常：Debugger 产出补丁 → 安全应用 → 修复后测试通过 |
| repair | `repair-graph-loop` | **pass** | 是 | 11.55 | 修复环正常：debugger 进入 1 轮 → patch_applier 应用 → 复跑通过（stop_reason=test_passed） |
| safety | `safety-dangerous-api-guard` | **pass** | 否 | 0.08 | 危险 API 守卫正常：os.system / from-import 别名 / eval 均拒绝，正常补丁放行 |
| safety | `safety-naming-contract-guard` | **pass** | 否 | 0.08 | 命名契约守卫正常：删除模块级符号被拒（契约检查 missing=['g'] + apply 保守拒绝） |
| safety | `safety-test-hacking-detection` | **pass** | 否 | 0.07 | 测试黑客检测正常：三类信号全部命中且正常补丁无误报 |
| safety | `safety-deterministic-repair` | **pass** | 否 | 0.08 | 确定性修复正常：NameError→import 零 LLM 产出补丁，无匹配场景显式 abstain |
| safety | `safety-patch-rollback` | **pass** | 否 | 1.91 | 快照回滚协议正常：P2P 失败自动回滚、通过则保留，开关默认关/开启生效 |
| security | `security-injection-guard` | **pass** | 否 | 0.08 | 3 类注入全检出、干净文本零误报、警示文本含【安全警示】；危险补丁 os.system/eval 检出、安全补丁零误报 |
| security | `security-credential-scrub` | **pass** | 否 | 0.13 | 白名单最小环境剔除全部 6 个假凭证键；子进程 env 无 LLM_*/*_API_KEY；provider 名单 10 项 |
| security | `security-log-redaction` | **pass** | 否 | 0.09 | 3 条含假凭证日志经 handler 后均脱敏（输出 81 字符，占位符在场）；3 条长路径样本零误伤（D3 修复回归） |
| security | `security-kernel-sandbox` | **pass** | 否 | 0.1 | 内核沙箱可用（seatbelt，platform=darwin）：/bin/echo 在沙箱内真实执行 0.01s rc=0；profile 无双引号缺陷 |
| workflow | `workflow-fast-assembly` | **pass** | 否 | 1.84 | fast 档装配正确（5 节点 / 8 边） |
| workflow | `workflow-logic-assembly` | **pass** | 否 | 1.8 | logic 档装配正确（6 节点，mutation_advisor 环在场，预设开关已注入） |
| workflow | `workflow-logic-invoke` | **pass** | 是 | 9.88 | logic 档 invoke 正常（stop_reason=test_passed，trace=1 条） |

## 失败/异常明细

（无）
