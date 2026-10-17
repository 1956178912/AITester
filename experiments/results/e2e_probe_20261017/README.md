# N 轮全功能端到端探针矩阵报告（2026-10-17）

> **性质**：N 轮"全功能全面优化"的**功能矩阵实跑工件**（不是研究证据）。
> 引擎：`scripts/tools/e2e_probe.py`；设计：`docs/design/e2e_probe_matrix.md`。
> 三组探针模块：`e2e_probes_workflow.py`（CLI/workflow/agents/repair/safety/localization/
> observability）、`e2e_probes_platform.py`（budget/cache/RAG/security/executor/dataset/
> observability）、`e2e_probes_logic.py`（规约/DSL/SMT/oracle/停滞/变异顾问/branch 覆盖）。
>
> **结果**：**56/56 pass**（pass=56, fail=0, error=0, skip=0；含 **12 个真实 LLM 探针**），
> 总墙钟 **119.8s**。运行环境：HEAD `f194d67` + N 轮收口工作树（内容即本批提交内容；
> 运行时刻 2026-10-17 23:07 Asia/Shanghai），Python 3.14.6，模型 `deepseek-flash`
> （`LLM_THINKING_MODE=disabled`、`AITESTER_LLM_CACHE=0` 由框架强制 → 全部真实调用）。
>
> **纪律**：LLM 探针在无 `AITESTER_E2E_LLM=true` 时一律 skip（不静默通过）；失败必须带
> 实测值；`requires_llm` 探针按结构/字段断言（不断言模型具体输出）。

## 1. 命令（可复现）

```bash
# 零 LLM 子集（44 探针）
.venv/bin/python scripts/tools/e2e_probe.py --all \
  --json-out experiments/results/e2e_probe_20261017/report_zero_llm.json

# 全量（56 探针，含 12 个真实 LLM 探针；本报告来源）
AITESTER_E2E_LLM=true .venv/bin/python scripts/tools/e2e_probe.py --all --include-llm \
  --json-out experiments/results/e2e_probe_20261017/report.json \
  --md-out experiments/results/e2e_probe_20261017/report.md
```

Makefile：`make e2e-probe`（零 LLM）/ `make e2e-probe-llm`（真 LLM）。

## 2. 功能组覆盖矩阵

| 组 | 探针数 | 其中真实 LLM | 结果 |
|---|---|---|---|
| `agents` | 3 | 2 | pass |
| `budget` | 4 | 1 | pass |
| `cache` | 3 | 1 | pass |
| `cli` | 5 | 2 | pass |
| `dataset` | 4 | 0 | pass |
| `executor` | 5 | 0 | pass |
| `localization` | 3 | 0 | pass |
| `logic` | 10 | 1 | pass |
| `observability` | 3 | 1 | pass |
| `rag` | 2 | 1 | pass |
| `repair` | 2 | 2 | pass |
| `safety` | 5 | 0 | pass |
| `security` | 4 | 0 | pass |
| `workflow` | 3 | 1 | pass |

## 3. 本矩阵驱动的真实缺陷修复（N 轮）

| 缺陷 | 影响 | 修复 |
|---|---|---|
| **kernel sandbox SBPL 单引号注入**（`src/agents/kernel_sandbox.py`） | `KERNEL_SANDBOX_ENABLE=true` 时 profile 被 sandbox-exec 整体拒绝 → **safe 档执行链路 100% 静默失效**且被误分类为 test_failure | `_sbpl_quote()` 双引号转义 + 根目录 read/metadata 放行；safe 档端到端复验 PASS |
| **kernel sandbox 执行器接线**（`executor.py`/`executor_modes.py`） | 解释器路径未放行 → `execvp() failed`，日志误报 test_failure | 解释器最小放行面（exec-only）+ TMPDIR 读写 + `kernel_sandbox_unavailable` 显式错误类型；local/venv 真实执行 PASS |
| **`.env.*` DENY 正则误伤 `.venv`**（`kernel_sandbox.py`） | venv 内 Python 读 `pyvenv.cfg` 被拒；`.venv` 整树被当凭证目录 | 路径分量匹配（`.env/.env.local/.ssh/.aws/llm_configs.json` 仍拒） |
| **`run --json --verbose` stdout 污染**（`src/cli/app.py`） | `| jq` 解析失败（JSON 契约破坏） | 提示改走 stderr |
| **`list-examples` 列出 `__init__.py`**（`src/cli/app.py`） | 建议执行空模块（无效示例） | 过滤下划线文件、优先 recommend calculator.py |
| **日志过度脱敏误伤长路径段**（`src/utils/logging_utils.py`） | `check-dataset` 的 gold 路径不可读（诊断可读性下降） | base64 模式边界锚定 + 内容判定；真实密钥族正控全保留 |

## 4. 与其它工件的关系

- 探针发现的**研究链路结论**（如 oracle 通道净负、repair 环可达性）由 N-3/N-4 的
  `emse_oracle_independent_judging_20261017/`、`e2e_llm_probes_20261017/` 与
  `BASELINE.yaml` 承载；本目录只负责"功能可达 + 状态字段正确"。
- 每个探针失败的证据字段已写入 `report.json`（功能矩阵的机器可读形态）。

## 5. 已知边界

- 探针验证"可达 + 关键状态正确"，不验证语义正确性（单元测试）与研究口径（工件对账）。
- 真实 LLM 探针受模型非确定性影响：断言仅落在结构/字段；单次运行通过不等于长期稳定
  （建议发布前重跑 `make e2e-probe-llm`）。
- 本机能力（无 docker CLI、macOS Seatbelt）差异一律显式 skip/明确降级，已在探针内断言。
