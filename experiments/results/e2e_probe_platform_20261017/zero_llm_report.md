# AITester 全功能端到端探针报告（N 轮）

> 引擎：`scripts/tools/e2e_probe.py`；LLM 探针：未启用（零 LLM 子集）
> 汇总：**21 pass / 0 fail / 0 error / 4 skip**（共 25 探针）

## 功能矩阵

| 组 | 探针 | 状态 | LLM | 耗时(s) | 说明/证据 |
|---|---|---|---|---|---|
| budget | `budget-cost-cap` | **pass** | 否 | 0.07 | 累计 120 tokens 超过 100 上限 → check_budget=False；events=1 |
| budget | `budget-invalid-fail-closed` | **pass** | 否 | 0.07 | 坏值/负值均 fail-closed；misconfigured_events=2 |
| budget | `budget-batch-quota` | **pass** | 否 | 0.07 | estimate(150)=968；未配置→blocking 2 条；上限 2000→ok；上限 100→拦截 |
| budget | `budget-llm-stop` | **skip** | 是 | 0.0 | 未启用 --include-llm（LLM 探针默认不跑） |
| cache | `cache-disabled` | **pass** | 否 | 0.98 | 文件缓存 enabled=False；语义缓存默认 enabled=False（精确缓存口径） |
| cache | `cache-two-call-hit` | **skip** | 是 | 0.0 | 未启用 --include-llm（LLM 探针默认不跑） |
| cache | `cache-semantic-index` | **pass** | 否 | 0.83 | 语义索引 entries=1，同义命中 / 无关未命中（hits=1, misses=1） |
| dataset | `dataset-loaders` | **pass** | 否 | 1.11 | 三加载器真实加载 0.02s：quixbugs=50 / examples=3 / synthetic=3 |
| dataset | `dataset-ult` | **pass** | 否 | 1.11 | ULT 加载 200 任务；样例 task_id=['ult__is_degree_in_degree_range', 'ult__BinaryFromFraction', 'ult__fix_labels'] |
| dataset | `dataset-decontamination` | **pass** | 否 | 1.17 | 去污染口径正确：total=3 kept=1 dropped=1 unverifiable=1；decontamination_rate=0.5 |
| dataset | `dataset-check-cli` | **pass** | 否 | 2.64 | check-dataset CLI 2.5s rc=0，质量检查 50 个任务无加载问题 |
| executor | `executor-local` | **pass** | 否 | 1.43 | 本地执行器 1.36s 通过最小测试（coverage=100.0，failed_cases=0） |
| executor | `executor-venv` | **pass** | 否 | 1.0 | venv 执行器 0.93s 通过最小测试（coverage=100.0） |
| executor | `executor-docker-degrade` | **pass** | 否 | 0.11 | 无 docker CLI → passed=False + error_info.type=docker_unavailable（明确降级，未静默回退本地） |
| executor | `executor-repo-verify` | **pass** | 否 | 2.01 | 临时仓库 verify 全链路 1.8s：test_patch 基线红 → llm_patch 后 F2P 1/1 转绿 → passed=True |
| executor | `executor-kernel-sandbox` | **pass** | 否 | 2.75 | KERNEL_SANDBOX_ENABLE=true：local + venv 执行器真实跑通（passed/coverage/obs 齐备），总耗时 2.67s |
| observability | `observability-trace-redaction` | **pass** | 否 | 0.09 | trace JSONL 3 行（task_start/node/task_end 齐全）且假凭证已脱敏 |
| observability | `observability-event-bus` | **pass** | 否 | 0.08 | 事件发布/订阅/计数正常；EVENT_BUS_ENABLE=false 时 no-op（消融口径可用） |
| observability | `observability-model-fingerprint` | **skip** | 是 | 0.0 | 未启用 --include-llm（LLM 探针默认不跑） |
| rag | `rag-retriever` | **pass** | 否 | 0.79 | 检索器初始化 0.05s；写入 1 案例后检索到 1 条（top similarity=0.7143） |
| rag | `rag-workflow-stats` | **skip** | 是 | 0.0 | 未启用 --include-llm（LLM 探针默认不跑） |
| security | `security-injection-guard` | **pass** | 否 | 0.07 | 3 类注入全检出、干净文本零误报、警示文本含【安全警示】；危险补丁 os.system/eval 检出、安全补丁零误报 |
| security | `security-credential-scrub` | **pass** | 否 | 0.1 | 白名单最小环境剔除全部 6 个假凭证键；子进程 env 无 LLM_*/*_API_KEY；provider 名单 10 项 |
| security | `security-log-redaction` | **pass** | 否 | 0.07 | 3 条含假凭证日志经 handler 后均脱敏（输出 81 字符，占位符在场）；3 条长路径样本零误伤（D3 修复回归） |
| security | `security-kernel-sandbox` | **pass** | 否 | 0.09 | 内核沙箱可用（seatbelt，platform=darwin）：/bin/echo 在沙箱内真实执行 0.01s rc=0；profile 无双引号缺陷 |

## 失败/异常明细

（无）
