# 日志脱敏覆盖审计报告

> 审计日期：2026-09-14 | 审计范围：所有可能输出敏感信息（API Key / Token / 凭证 / 带密钥 URL）的路径
> 审计方法：逐出口路径静态走查（logging 出口 / 直接 print / 直接文件落盘 / JSON 结果字段），确认每个出口的脱敏接线状态。

## 脱敏机制总览（三层防线）

| 层 | 机制 | 位置 | 覆盖出口 |
|----|------|------|----------|
| Handler 层 | `SensitiveFilter`（消息体）+ `SensitiveFormatter`（完整行含 exc_info 堆栈） | `src/utils/logging_utils.py`，挂 root logger 与全部 handler | 所有经 logging 框架传播到 root 的消息与异常堆栈 |
| 入口接线层 | `setup_logger_safety()`（挂 root + 已有 handler） | `src/cli/app.py:80`、`experiments/run_benchmark.py:74`、`logging_utils.py:154`（模块导入自挂） | CLI 入口、benchmark 入口 |
| 旁路落盘层 | `mask_sensitive_info` 直接对 JSONL 行脱敏 | `src/observability/trace.py:169`（`_append`） | trace JSONL（AITESTER_TRACE_DIR 已设时） |

**已确认无泄漏的出口**（本轮走查通过）：
- `trace.py` 的 `_append`：每行写盘前过 `mask_sensitive_info`，且 `task_meta` / `output` / `extra` 均先经 `_summarize` 截断再脱敏；
- CLI / run_benchmark 入口的异常堆栈：handler 挂 `SensitiveFormatter`，`format()` 产物（含 traceback）整体再过一次脱敏（`test_sensitive_formatter` 用例锁定）；
- `base_agent._call_llm` 的 LLM 异常文本：`_redact_log_text` 就地脱敏（P2-8），不依赖入口接线。

## 本轮发现的盲点与处置

### A. APIManager 故障转移/健康检查日志的 `str(e)`（已修复）

**路径**：`src/api/api_manager.py` 的 `check_health` / `_handle_api_error` / `_handle_generic_error` / `HealthCheckerThread` 共 5 处 `logger.warning/error("… %s", e)`，以及 `_init_clients` / `add_node` 的 2 处 `base_url` 直打日志。

**风险**：APIManager 可被嵌入式使用（`examples/api_manager_example.py`、第三方集成、单测），调用方未必调用 `setup_logger_safety()`。openai SDK 的 `APIError` 文本在部分网关会回显请求头或 base_url（其中可能含 API Key）。此前这些日志仅在入口挂了脱敏 handler 时才安全，嵌入式场景裸奔。

**处置**：新增模块级 `_redact()`（懒加载 `mask_sensitive_info`，与 `base_agent._redact_log_text` 同口径），在全部 7 处日志点就地脱敏——**不依赖任何入口接线**，嵌入式使用同样安全。

**验证**：`tests/test_api_manager.py::TestCircuitCooldownBoundaries` 与既有 APIManager 用例全绿；`str(e)` 脱敏由 `mask_sensitive_info` 单测（`tests/test_logging_utils.py`）覆盖。

### B. `get_status()` 返回的 `base_url` 明文（已修复）

**路径**：`APIManager.get_status()` 的 `nodes_summary[name]["base_url"]` 原样返回配置值。该字典流经 `print_status_table`（直接 `print` 到 stdout，**不经 logging handler 脱敏**）与任何监控/导出消费方。部分网关的 base_url 内嵌 token（`https://gw.example/v1/<token>`）。

**处置**：`get_status()` 出口处对 `base_url` 过 `mask_sensitive_info`（与日志口径一致）。调用方拿到的状态字典已脱敏；`_init_clients` / `add_node` 的注册日志同步脱敏。

**验证**：`tests/test_api_manager.py` 全绿（`get_status` 既有断言未涉及 base_url 明文，回归通过）。

### C. LLM 文件缓存（`src/cache/*.json`）——记录为"已知可接受风险"

**路径**：`base_agent._call_llm_with_cache` 写缓存文件时落盘原始 `prompt` / `system` / `response` 全文，默认目录 `src/cache/`（仓库内相对路径，`AITESTER_LLM_CACHE_DIR` 可覆盖；代码 `_LLM_CACHE_DIR_DEFAULT` 相对 `src/agents/` 解析为仓库根下 `src/cache/`）。若被测项目源码或 LLM 响应中含密钥，会随之持久化到该目录。

**为何不改**：缓存读取靠 `cached_data["prompt"] == user_message` 精确匹配命中；对落盘值脱敏会使读侧（未脱敏原值）永远不命中，缓存功能直接失效。脱敏与缓存正确性互斥，须二选一。

**处置**：维持原样，明确为**本地可信域内的已知风险**——`src/cache/` 已被 `.gitignore` 排除（不进 git、不上传），且目录名 `src/cache` 易被误认为源码模块（实际是运行时产物），开发者勿将其当源码阅读。

**后续可选**（不在本轮做，避免破坏缓存正确性）：为缓存文件加可选的"脱敏+双字段"方案（明文值存内存、脱敏值落盘），需要缓存读侧改造，单独立项。

### D. 实验结果 JSON / raw 产物（`experiments/results/**`）——记录为"归档面，非泄漏面"

**路径**：`run_benchmark._dump_state_artifacts` 与结果 JSON 落盘 `diagnosis` / `patch` / `generated_test` / `rag_stats` / `token_usage`。

**判定**：这是实验数据归档面，不是日志/控制台泄漏面。内容是被测代码与 LLM 诊断文本（实验本身的数据），且 `experiments/results/` 已入 `.gitignore`（4.3 约定，不入库、不上 git）。清单 4.3 的归档自动化（Zenodo 上传）若启用，**上传前应对结果 JSON 过一遍 `mask_sensitive_info`**（作为归档脚本的一部分，本轮未做——归档脚本未立项）。

## 未覆盖/建议后续

1. **归档脱敏**：4.3 归档脚本（未立项）落 Zenodo 前应统一过 `mask_sensitive_info`（含结果 JSON 与 trace JSONL）；
2. **LLM 缓存脱敏双字段**（C 的后续可选项），单独立项；
3. **新入口接线检查**：未来新增入口（如 notebook / Jupyter 内嵌）若使用 APIManager，应调用 `setup_logger_safety()`——本轮 A 修复后 APIManager 自身日志已自脱敏，此条从"必须"降为"建议"。

## 测试覆盖

- `tests/test_logging_utils.py`：`mask_sensitive_info` 全模式（API Key / 长十六进制 / 长 base64 / key= 形式 / JWT）+ `SensitiveFilter` + `SensitiveFormatter`（exc_info 堆栈脱敏）；
- `tests/test_trace_observability.py`（12 用例）：trace JSONL 脱敏与 no-op 双路径；
- `tests/test_cli_app.py`：CLI 入口 SensitiveFilter 接线 + handler formatter 回归；
- `tests/test_api_manager.py`：APIManager 全量回归（含本轮 4.1 新增冷却期边界用例）。
