# AITester 全功能端到端探针报告（N 轮）

> 引擎：`scripts/tools/e2e_probe.py`；LLM 探针：已启用（真实调用，缓存关闭）
> 汇总：**25 pass / 0 fail / 0 error / 0 skip**（共 25 探针）

## 功能矩阵

| 组 | 探针 | 状态 | LLM | 耗时(s) | 说明/证据 |
|---|---|---|---|---|---|
| budget | `budget-cost-cap` | **pass** | 否 | 0.08 | 累计 120 tokens 超过 100 上限 → check_budget=False；events=1 |
| budget | `budget-invalid-fail-closed` | **pass** | 否 | 0.07 | 坏值/负值均 fail-closed；misconfigured_events=2 |
| budget | `budget-batch-quota` | **pass** | 否 | 0.07 | estimate(150)=968；未配置→blocking 2 条；上限 2000→ok；上限 100→拦截 |
| budget | `budget-llm-stop` | **pass** | 是 | 2.24 | 首次调用成功（'7'）；耗尽后第二次抛 BudgetExceededError（consumed=29） |
| cache | `cache-disabled` | **pass** | 否 | 1.21 | 文件缓存 enabled=False；语义缓存默认 enabled=False（精确缓存口径） |
| cache | `cache-two-call-hit` | **pass** | 是 | 2.23 | 两次同 prompt：第二次缓存命中（0.000s vs 首次 0.69s）；llm_calls=1, cache_hits=1, avoided_tokens=29 |
| cache | `cache-semantic-index` | **pass** | 否 | 0.91 | 语义索引 entries=1，同义命中 / 无关未命中（hits=1, misses=1） |
| dataset | `dataset-loaders` | **pass** | 否 | 1.06 | 三加载器真实加载 0.02s：quixbugs=50 / examples=3 / synthetic=3 |
| dataset | `dataset-ult` | **pass** | 否 | 1.05 | ULT 加载 200 任务；样例 task_id=['ult__is_degree_in_degree_range', 'ult__BinaryFromFraction', 'ult__fix_labels'] |
| dataset | `dataset-decontamination` | **pass** | 否 | 1.05 | 去污染口径正确：total=3 kept=1 dropped=1 unverifiable=1；decontamination_rate=0.5 |
| dataset | `dataset-check-cli` | **pass** | 否 | 2.48 | check-dataset CLI 2.4s rc=0，质量检查 50 个任务无加载问题 |
| executor | `executor-local` | **pass** | 否 | 1.46 | 本地执行器 1.38s 通过最小测试（coverage=100.0，failed_cases=0） |
| executor | `executor-venv` | **pass** | 否 | 1.02 | venv 执行器 0.95s 通过最小测试（coverage=100.0） |
| executor | `executor-docker-degrade` | **pass** | 否 | 0.09 | 无 docker CLI → passed=False + error_info.type=docker_unavailable（明确降级，未静默回退本地） |
| executor | `executor-repo-verify` | **pass** | 否 | 2.14 | 临时仓库 verify 全链路 1.9s：test_patch 基线红 → llm_patch 后 F2P 1/1 转绿 → passed=True |
| executor | `executor-kernel-sandbox` | **pass** | 否 | 2.67 | KERNEL_SANDBOX_ENABLE=true：local + venv 执行器真实跑通（passed/coverage/obs 齐备），总耗时 2.58s |
| observability | `observability-trace-redaction` | **pass** | 否 | 0.08 | trace JSONL 3 行（task_start/node/task_end 齐全）且假凭证已脱敏 |
| observability | `observability-event-bus` | **pass** | 否 | 0.07 | 事件发布/订阅/计数正常；EVENT_BUS_ENABLE=false 时 no-op（消融口径可用） |
| observability | `observability-model-fingerprint` | **pass** | 是 | 3.74 | 模型指纹 1.21s：alias=deepseek-flash returned=deepseek-flash pinned=True probe=fc3d915941b8… |
| rag | `rag-retriever` | **pass** | 否 | 0.91 | 检索器初始化 0.06s；写入 1 案例后检索到 1 条（top similarity=0.7143） |
| rag | `rag-workflow-stats` | **pass** | 是 | 5.55 | ENABLE_RAG 下最小任务 3.8s 完成；rag_stats 1 条（kinds=['test_cases']）；generated_test 1437 字符 |
| security | `security-injection-guard` | **pass** | 否 | 0.07 | 3 类注入全检出、干净文本零误报、警示文本含【安全警示】；危险补丁 os.system/eval 检出、安全补丁零误报 |
| security | `security-credential-scrub` | **pass** | 否 | 0.11 | 白名单最小环境剔除全部 6 个假凭证键；子进程 env 无 LLM_*/*_API_KEY；provider 名单 10 项 |
| security | `security-log-redaction` | **pass** | 否 | 0.08 | 3 条含假凭证日志经 handler 后均脱敏（输出 82 字符，占位符在场） |
| security | `security-kernel-sandbox` | **pass** | 否 | 0.12 | 内核沙箱可用（seatbelt，platform=darwin）：/bin/echo 在沙箱内真实执行 0.01s rc=0；profile 无双引号缺陷 |

## 失败/异常明细

（无）
