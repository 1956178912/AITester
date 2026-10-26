# AITester API 参考

最后更新：2026-10-26 · English: [api_reference.en.md](api_reference.en.md)

面向开发者的模块、CLI、配置、异常与 LLM 调用契约速查。架构背景见
[algorithm_design.md](algorithm_design.md)；安全边界见 [threat_model.md](threat_model.md)。

## 1. 模块地图

| 路径 | 职责 | 主要入口 |
|------|------|----------|
| `src/agents/` | 智能体与错误分类 | `PlannerAgent`、`GeneratorAgent`、`ExecutorAgent`、`DebuggerAgent`、`FaultLocalizerAgent`、`ErrorClassifier` |
| `src/graph/` | 工作流编排、状态机、事件与预算 | `WorkflowGraph`、节点函数、`EventBus`、`CostBudget` |
| `src/tools/` | 静态分析、补丁与回滚、上下文构建 | `CodeAnalyzer`、`PatchApplier`、`CodeContext`、快照回滚 |
| `src/specs/` | SpecIR 规约中间表示与 SMT 见证 | 规约编译、oracle 生成 |
| `src/api/` | Provider 池、熔断、健康检查 | `APIManager`、`APIManagerConfig` |
| `src/datasets/` | 数据集加载与合成任务生成 | `DatasetLoader`、`SyntheticDataset` |
| `src/observability/` | 结构化追踪与遥测 | `TraceSession`、`AgentTelemetry` |
| `src/measurement/` | 政策无关度量（MDO）、恢复延迟与检索质量 | `compute_mdo`、`compute_recovery_latency`、`retrieval_relevance` |
| `src/budget/` | token 与费用记账 | `CostBudget`、`BudgetExceededError` |
| `src/reports/` | 缺陷报告生成 | `ErrorReport` |
| `src/cli/` | 命令行实现 | `src/cli/app.py`（`main.py` 为薄封装） |
| `src/utils/` | 异常、日志脱敏、通用工具 | `AITesterError` 体系、`mask_sensitive_info` |
| `config.py` | 环境变量与集中配置 | `LLM_CONFIGS`、`MODEL_NAME` |

工作流：Planner → Generator → Executor → Debugger → PatchApplier，编排层是可消融容器
（ADR-0016），不是主断言。M1 指标（detection / repair / false_fix）不在
`src/measurement/`：实现在 `experiments/_m1_metrics.py`，由 `experiments/run_benchmark.py`
消费（需要 gold 材料）。

## 2. CLI 与入口

```bash
python3 main.py --help
python3 main.py run examples/calculator.py --func divide
python3 main.py run examples/calculator.py --json
python3 main.py doctor
```

| 命令 | 用途 | 关键选项 |
|------|------|----------|
| `run` | 运行测试生成与修复任务 | `--func` / `-f`、`--max-iterations`、`--coverage-threshold`、`--parallel` / `-p`、`--timeout` / `-t`、`--json`、`--verbose` / `-v`、`--dump-trace-on-failure` |
| `list-examples` | 列出 `examples/` 下的示例文件 | — |
| `check-dataset` | 校验数据集加载质量 | `--subset` / `-s`、`--limit` / `-n` |
| `clean-venv-cache` | 清理 Executor 的 venv 依赖缓存 | `--max-age-days`、`--max-size-mb`、`--list-only` / `-l` |
| `doctor` | 零 LLM 自检（环境 + 功能探针矩阵） | `--json`、`--groups`、`--timeout`、`--strict` |

`doctor` 退出码：0 通过；1 失败（或 `--strict` 下 warn/skip/矩阵不可用）；2 参数用法错误
（`--groups` 为空或未知分组）。功能矩阵依赖源码检出的 `scripts/tools/e2e_probe.py`；
wheel 安装面标记 `unavailable`（不计失败），环境检查仍有效。

`doctor --json` 的三条出口（成功 / 用法错误 / doctor 自身异常）输出**同一键集合**：
`schema`、`generated_at`、`cwd`、`command`、`python`、`checks`、`check_summary`、
`matrix`、`conclusion`、`ok`、`strict`、`exit_code`、`error`。`error` 在非异常路径为
`null`；异常路径 `matrix.status` 记 `internal`，未采集的 `checks` / `check_summary` /
矩阵聚合记 `null`（未知 ≠ 全 0），消费方无需按「键是否存在」分支。

CLI 退出码统一口径：0 通过；1 运行期失败（`run` 存在失败任务——覆盖率未达标只作
逐任务判定与摘要披露、不计入失败；`check-dataset` 加载异常、
0 个任务、请求的子集未生效或全量质量报告发现加载问题、`clean-venv-cache` 有条目删除失败）；
2 用法错误（未知数据集名、
`--limit` 为负、`--subset` 用于不支持子集的数据集或未知子集名、`run` 的 `--func` 或
`check-dataset` 的 `--subset` 为显式空值（空串 / 纯空白）、`--max-age-days` /
`--max-size-mb` 为负、`run` 无有效目标或数值选项非法，含 `--coverage-threshold=nan`）。
显式空值不等于「未提供」：脚本里 `--func "$FUNC"` / `--subset "$SUBSET"` 变量未展开时
传入的是 `""`，按未提供处理会静默放宽到全部函数（按函数数消耗 LLM）或全量数据；
省略选项才是「全部」口径。
`check-dataset` 只接受 `get_available_datasets()` 列出的名称（大小写与连字符不敏感）；
库函数 `load_dataset` 对未知名称仍按契约降级为内置示例——诊断命令不适用该宽容口径，
否则「没校验到目标数据集」会被报成通过。`clean-venv-cache` 的 `0` 过滤器是「全部过期」
的显式语义（与两个过滤条件缺省等价），只有负数被拒。

`run` 的 TARGET_FILES 只接受普通文件：显式目录 / 特殊文件与「通配符只匹配到目录」按
用法错误 rc=2 拒绝且不启动任务（不再伪装成任务失败）；同一文件经 glob 与显式路径重复
命中时按绝对路径去重、只跑一次，避免重复消耗 LLM。

`run --dump-trace-on-failure` 在任务失败（含崩溃）时尝试导出内存追踪快照：成功时结果
带 `trace_dump_path`，无快照可写 / 写盘失败时带 `trace_dump_error` 并在 stderr 披露
原因；导出失败不改变任务结果，`--json` 模式的 stdout 仍只承载 JSON。同一秒内的多次 /
并发导出各自落盘：同名文件已存在时追加序号（`<ts>_2_failed_trace.jsonl`），不覆盖旧快照。

`check-dataset --subset` 只在加载器真正支持子集时生效：`swe_bench` 系列把子集名映射为
`swe_bench_<subset>_instances.jsonl`，`ult` 支持 `lite` / `full`（官方子集文件）；其他
数据集（内置示例、QuixBugs、BugsInPy、Defects4J、synthetic）没有子集概念，传入
`--subset` 会按用法错误（退出码 2）拒绝并列出支持子集的数据集。`ult` 的子集文件缺失、
子集名未知或数据源为显式文件时，请求的子集不会被静默替换——命令以退出码 1 披露
「未生效」原因；去掉 `--subset` 才会校验回退后的数据。

`clean-venv-cache --list-only` 与过滤条件组合时按实际删除口径预演（`[将删除]` / `[保留]`），
预览与真实清理复用同一判定，名单不会各算一套；删除失败（目录仍存在，如权限不足）会逐项
报告并以退出码 1 结束，不会把失败计为已删除，也不会谎报释放空间。

`check-dataset` 的「全量质量检查通过」只在加载器实现 `quality_report` 时出现；内置示例、
QuixBugs、ULT 等数据集没有该能力，命令会显式打印「未提供 quality_report，跳过全量校验」；
`tasks_missing_source` 缺失时同样披露跳过。能力缺失（跳过校验）不是失败，退出码仍为 0；
但质量报告非空——即真的查出了加载问题——会逐项披露并以退出码 1 结束，与「加载异常」同码、
文案可区分（`加载质量校验未通过：N 个任务存在加载问题`）；`tasks_missing_source` 非空属
信息性披露（源码待导出），单独不改变退出码。

`run` 逐任务输出测试是否通过、覆盖率判定（结果键 `coverage_ok`）、覆盖率数值与迭代
次数；非 `--json` 模式的批次摘要汇总覆盖率达标情况（达标 / 未达标 / 不可测三态），
`--json` 输出逐任务结构化结果（含 `coverage_ok`）。任务崩溃（如源文件不是合法 UTF-8、
工作流抛异常）同样产出一行结果：`--json` 下与成功结果**键集合逐键相同**（`coverage` /
`coverage_ok` / `iterations` / `diagnosis` / `error_category` / 观测统计等未知判定显式
为 `null`，另含 `error` 描述）；非 `--json` 模式下原因写 stderr、stdout 仍只承载结果
表格（迭代列显示 `N/A`，不用 0 冒充未测）。`--coverage-threshold` 只影响覆盖率
判定与摘要，**不改变退出码**（退出码只反映测试通过/失败）。detection / repair /
false_fix 属于基准评估面，由 `experiments/_m1_metrics.py` 计算、
`experiments/run_benchmark.py` 消费（需要 gold 材料），CLI 不计算也不输出。

安装为包后也可用 `aitester` 控制台入口（见 `pyproject.toml`）。

## 3. 配置

配置来源：`.env.local`（LLM 凭证，gitignore）、`.env.example`（模板，入库）、
`config.local.example`（LLM 模板，入库）。`LLM_N_*` 支持多个 provider（N 从 1 起）。

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `LLM_N_API_KEY` / `LLM_N_BASE_URL` / `LLM_N_MODEL_NAME` | str | — | 第 N 个 OpenAI 兼容端点 |
| `LLM_N_COST_WEIGHT` | float | 0.0 | 成本感知路由的权重（0.0 = 无信息） |
| `MAX_ITERATIONS` | int | 3 | 最大修复迭代次数 |
| `COVERAGE_THRESHOLD` | float | 80.0 | 覆盖率阈值（%） |
| `EXECUTION_TIMEOUT` | int | 30 | pytest 执行超时（秒） |
| `LLM_TIMEOUT` / `LLM_RETRY_WAIT` | int | 60 / 30 | LLM 调用超时与重试等待（秒） |
| `TEMPERATURE` | float | 0.2 | 采样温度；确定性实验由 `run_benchmark(deterministic=True)` 强制 0.0 |
| `EXECUTOR_USE_VENV` | bool | true | venv 沙箱隔离执行（R10 起默认 true；false 仅调试用） |
| `EXECUTOR_AUTO_INSTALL_DEPS` | bool | false | venv 内自动安装缺失依赖 |
| `EXECUTOR_USE_DOCKER` | bool | false | Docker 隔离执行；不可用时返回 `docker_unavailable`，不静默降级 |
| `ENABLE_RAG` | bool | false | 启用 RAG 案例检索 |
| `ENABLE_MUTATION_SCORING` | bool | false | 启用变异评分 |
| `LLM_JSON_MODE` | str | "on" | JSON Output 契约（`json_object`）；`off` 为历史逐字节口径 |
| `LLM_THINKING_MODE` | str | "disabled" | DeepSeek 思考链默认关闭（成本保护） |
| `FAULT_LOCALIZER_ENABLE` | bool | true | RGFL 式 LLM 推理定位通道；false 退回纯谱系口径 |
| `AITESTER_PROFILE` | str | 未设 | 预设档：`safe` / `scientific` / `logic` / `fast` |
| `AITESTER_TRACE_DIR` | str | 未设 | 结构化 JSONL 追踪输出；未设时 no-op |
| `COST_BUDGET_ENABLE` | bool | false | 任务级 token / USD 预算硬闸 |

完整清单与逐项语义以 `config.py` 与 `docs/env_budget.yaml` 为准；批次 provenance 记录
`env_snapshot`，供复现审计。

## 4. 异常与错误分类

```python
from src.utils.exceptions import AITesterError, APIError, ParsingError

try:
    ...
except APIError as exc:
    ...
```

| 异常 | 父类 | 触发场景 |
|------|------|----------|
| `ConfigurationError` | `AITesterError` | 配置缺失或非法 |
| `ExecutionError` | `AITesterError` | 测试执行失败 |
| `TimeoutError` | `ExecutionError` | 测试执行超时（与内置同名，属既有 API） |
| `ParsingError` | `AITesterError` | LLM 输出解析失败 |
| `JSONParseError` | `ParsingError` | JSON 契约响应不可解析 |
| `SyntaxParseError` | `ParsingError` | 生成代码语法错误 |
| `APIError` | `AITesterError` | Provider 调用失败 |
| `RateLimitError` | `APIError` | 429 限流 |
| `AuthenticationError` | `APIError` | 401/403 鉴权失败 |
| `BudgetExceededError` | `RuntimeError` | 任务预算超限 |
| `SandboxUnavailable` | `RuntimeError` | 内核沙箱不可用（fail-closed） |

`ErrorClassifier` 产出 18 类 `ErrorCategory`：`llm_format_error`、`llm_empty_response`、
`llm_json_parse_failed`、`import_error`、`syntax`、`type_error`、`index_error`、`assertion`、
`logic_error`、`runtime`、`timeout`、`unknown`、`patch_validation_failed`、
`rag_retrieval_empty`、`execution_trace_missing`、`multi_candidate_all_rejected`、
`patch_syntax_invalid`、`test_regenerated_pass_unverified`。分类是纯规则（无 LLM），
未知形态归 `unknown` 并保守处理。

执行侧结构化诊断：`error_info.type` 可能为 `execution_dependency_missing`（缺 pytest 等
执行依赖，提示安装 `aitester[execution]`）、`docker_unavailable`、`docker_timeout`。

## 5. LLM 调用契约

- **Provider**：OpenAI 兼容端点，凭证只经 `.env.local`；内置 provider 仅 DeepSeek 官方。
- **JSON 契约**：七处调用点（Planner 计划、Debugger 补丁 / 严格重试 / 批评者 / 击穿用例 /
  缺陷分类、FaultLocalizer 定位）在 `LLM_JSON_MODE=on` 时绑定
  `response_format={"type": "json_object"}`；`off` 用于历史批次逐字节复现。
- **思考模式**：`LLM_THINKING_MODE=disabled` 默认关闭（V4 系思考链计入输出计费）；
  `LLM_REASONING_EFFORT` 与 `LLM_MAX_OUTPUT_TOKENS` 可选覆盖。
- **可恢复失败**：`finish_reason ∈ {length, insufficient_system_resource}` 按可恢复失败
  重试；JSON 值位的 Python 数值表达式由限制求值解析层修复（无 `eval`）。
- **缓存**：LLM 文件缓存默认在用户缓存目录（`~/.cache/aitester/llm`）；缓存键包含
  provider / 模型 / 温度 / JSON 模式等身份字段；种子只用于任务采样，不发送给 API。
- **路由与熔断**：`APIManager` 提供健康检查、熔断与成本感知路由；失败时保守降级，
  不伪造成功。凭证在三条执行链路进入子进程前由 `credential_scrub.scrub_os_environ` 清除。
