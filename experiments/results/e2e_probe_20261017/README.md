# S 轮全功能端到端探针矩阵报告（2026-10-18）

> **性质**：全功能功能矩阵实跑工件（不是研究证据）。
> 引擎：`scripts/tools/e2e_probe.py`；设计：`docs/design/e2e_probe_matrix.md`。
> 三组探针模块：`e2e_probes_workflow.py`（24）、`e2e_probes_platform.py`（25）、
> `e2e_probes_logic.py`（19；O/P/Q/R/S 轮新增 3 个 oracle 仪器探针 + 2 个示例通道探针 + 示例生产契约 + 后处理墙钟/hook + 示例自校验 + 多采样自一致性）。
>
> **结果**：**66/66 pass**（pass=66, fail=0, error=0, skip=0；含 **12 个真实 LLM 探针**），
> 总墙钟 **74.3s**。运行环境：HEAD `566f973` + P 轮收口工作树（内容即本批提交内容；
> 运行时刻 2026-10-18 06:5x Asia/Shanghai），Python 3.14.6，模型 `deepseek-flash`
> （`AITESTER_LLM_CACHE=0` 由框架强制 → 全部真实调用）。
>
> **纪律**：LLM 探针在无 `AITESTER_E2E_LLM=true` 时一律 skip（不静默通过）；失败必须带
> 实测值；`requires_llm` 探针按结构/字段断言（不断言模型具体输出）。

## 1. 命令（可复现）

```bash
# 零 LLM 子集（54 探针）
.venv/bin/python scripts/tools/e2e_probe.py --all \
  --json-out experiments/results/e2e_probe_20261017/report_zero_llm.json

# 全量（66 探针，含 12 个真实 LLM 探针；本报告来源）
AITESTER_E2E_LLM=true .venv/bin/python scripts/tools/e2e_probe.py --all --include-llm \
  --json-out experiments/results/e2e_probe_20261017/report.json \
  --md-out experiments/results/e2e_probe_20261017/report.md
```

Makefile：`make e2e-probe`（零 LLM，CI 同口径）/ `make e2e-probe-llm`（真 LLM）；
用户侧入口：`python main.py doctor`（P-3，零 LLM 自检 + 矩阵子集）；CI 已有零 LLM
`e2e-probe` job（.github/workflows/ci.yml，判据 0 fail/0 error）。

## 2. 功能组覆盖矩阵

| 组 | 探针数 | 其中真实 LLM | 结果 |
|---|---|---|---|
| `agents` | 3 | 2 | pass |
| `budget` | 4 | 1 | pass |
| `cache` | 3 | 1 | pass |
| `cli` | 6 | 2 | pass |
| `dataset` | 4 | 0 | pass |
| `executor` | 5 | 0 | pass |
| `localization` | 3 | 0 | pass |
| `logic` | 18 | 1 | pass |
| `observability` | 4 | 1 | pass |
| `rag` | 2 | 1 | pass |
| `repair` | 2 | 2 | pass |
| `safety` | 5 | 0 | pass |
| `security` | 4 | 0 | pass |
| `workflow` | 3 | 1 | pass |

## 3. 本矩阵驱动的真实缺陷修复（N/O/P 轮）

| 缺陷 | 影响 | 修复 |
|---|---|---|
| kernel sandbox SBPL 单引号注入（N） | safe 档执行链路 100% 静默失效 | `_sbpl_quote()` + 根目录规则；safe 档真实 PASS |
| kernel sandbox 执行器接线（N） | `execvp() failed` 且误报 test_failure | exec-only 放行面 + 显式错误类型 |
| `.env` DENY 误伤 `.venv`（N） | venv 内 Python 读 pyvenv.cfg 被拒 | 路径分量匹配 |
| `run --json --verbose` stdout 污染（N） | `jq` 解析失败 | 提示改走 stderr |
| `list-examples` 引 `__init__.py`（N） | 无效示例 | 过滤下划线文件 |
| 日志过度脱敏误伤长路径（N） | gold 路径不可读 | 边界锚定 + 内容判定 |
| `COST_BUDGET_USD` 记账未接线（N） | 费用上限永不生效 | pricing + 记账接线（修后 1 调用即触发） |
| 跨文件结果行审计字段缺失（N） | 无法逐行审计 | 三键进结果行 |
| oracle 崩溃冒充假阳（O-1） | fp 76.3% 中 27/29 是仪器崩溃 | 崩溃安全 harness + 前件校验输入（fp 29→2） |
| branch 测量孤儿 pytest（O-5） | ppid=1、99% CPU、82min | 单测 10s 超时 + orphan_guard |
| RepoExecutor stale pyc 假红（O-5） | 补丁已应用却随机失败 6/15 | `-B` + `PYTHONDONTWRITEBYTECODE` 根修 |
| A-19 停滞检测纸面功能（P-2） | 开关存在但无路由消费、标签被遮蔽 | 短路提前停止 + 优先级前移（26 测试） |
| 示例通道未接生产（Q-1） | 重放有检出但生产默认无通路 | Planner 契约 + 双门开关 + 行字段（默认关零差异） |
| 后处理墙钟不可观测（Q-3/R-3） | 批后处理超时/波动无法诊断 | postprocess_wall 模块 + run_benchmark hook（per_baseline 粒度） |

## 4. 与其它工件的关系

- 研究链路结论由 `emse_oracle_instrument_hardening_20261017/`、
  `emse_oracle_enabled_validation_20261017/`、`o_round_cross_file_20261017/`、
  `p_round_oracle_examples_20261018/`、`p_round_b8_ablation_20261018/` 与
  `BASELINE.yaml` 承载；本目录只负责"功能可达 + 状态字段正确"。

## 5. 已知边界

- 探针验证"可达 + 关键状态正确"，不验证语义正确性（单元测试）与研究口径（工件对账）。
- 真实 LLM 探针受模型非确定性影响：断言仅落在结构/字段；发布前重跑 `make e2e-probe-llm`。
- 本机能力（无 docker CLI、macOS Seatbelt）差异显式 skip/明确降级，已在探针内断言。
- 同名探针 `observability-trace-redaction`/`observability-event-bus` 同时定义在
  workflow 与 platform 模块（`--all` 保留首个并告警），已知边界见设计文档 §6。
