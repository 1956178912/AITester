# 日志脱敏完整审计（4.2）

> 审计时间：2026-09-19 ｜ 审计范围：四层脱敏防线的完整性核查
> 审计方法：静态代码路径追踪（无运行时日志采样）

---

## 审计结论

三层防线（SensitiveFilter 消息体 / SensitiveFormatter 异常堆栈 / 出口脱敏
`mask_sensitive_info`）在**主要路径**上完整有效，本次审计发现 **1 个需
修复的真实风险点**与 **2 个设计取舍记录项**。

---

## 逐层核查结果

### 1. api_manager 故障转移日志中 Provider 的 base_url

**状态：✓ 已脱敏（覆盖完整）**

- `get_status()` 的 `base_url` 字段经 `mask_sensitive_info` 出口脱敏
  （`src/api/api_manager.py:565`），防"部分网关把 token 放 URL 查询串"
  场景。
- 故障转移 / 健康检查 / API 错误日志只打印 `model_name`（不打印
  base_url），API 错误体经 `_redact` 委托 `mask_sensitive_info`
  （`src/api/api_manager.py:40-53`）。
- 动态添加节点日志也经 `_redact(config.base_url)` 脱敏
  （`src/api/api_manager.py:649`）。

**⚠️ 发现 R-1（需修复）：`_redact` 的降级路径存在泄漏风险。**
`_redact` 在 `mask_sensitive_info` 导入失败时 `except Exception: return
text`——原始未脱敏文本被直接打日志。若脱敏模块因任何原因不可用
（如循环导入 / 模块损坏），API 错误体中的凭证会原样落入日志。
**修复建议**：降级路径至少做"长随机串"兜底脱敏（正则替换 32+ 位
hex / base64 / sk- 前缀串），而非原样返回。见本次提交的
`src/api/api_manager.py` 变更。

### 2. trace.py 的 JSONL 落盘内容

**状态：✓ 已脱敏（覆盖完整）**

- `TraceSession._append` 在写盘前对整行 JSON 字符串跑
  `mask_sensitive_info`（`src/observability/trace.py:165-171`），
  与日志脱敏同源。
- 输入摘要经 `_summarize` 截断（2000 字符头尾各半），单行体积
  有界。
- 写盘失败仅 warning，不阻断主流程。
- 本地无实际 trace 产物文件（09-18 批次未设 AITESTER_TRACE_DIR），
  审计按代码路径静态核查，未做运行时采样。

### 3. Docker 容器环境变量注入路径

**状态：✓ 覆盖完整（设计正确）**

- `execute_docker`（`src/agents/executor_modes.py:199+`）**不注入
  任何环境变量**——容器只挂载卷（sandbox_dir → /workspace）+
  使用镜像内预装依赖。无 `docker run -e` / `--env-file` 调用。
- Dockerfile（根目录）的 `COPY . .` 会带入构建上下文，但
  `.dockerignore` 已排除 `.env` / `.env.*` / `.local` / `rag_data`
  / `experiments/results`（真实密钥文件不进镜像）。
- 运行时密钥路径：用户挂载宿主机的 `.env.local`，镜像内 `COPY . .`
  不含密钥（被 .dockerignore 挡住），符合"密钥随挂载生效"的设计
  意图（Dockerfile 第 4 行注释）。

**记录项 O-1（设计取舍，非缺陷）：`config.local.example` 被
.dockerignore 排除。** 该文件是模板（不含真实密钥），排除后镜像内
无"配置说明"文件，新手首次构建需手动创建 .env.local。这是保守
选择（宁可少带入），不需修复，仅作记录。

### 4. 异常堆栈的完整打印路径

**状态：✓ 已脱敏（双保险）**

- 全项目唯一 `exc_info=True` 打印点：`src/utils/exceptions.py:321`
  （`safe_execute` 的安全执行失败）。该点经 CLI/服务入口挂载的
  `SensitiveFormatter` 覆盖——Formatter 在 `super().format()`
  得到的完整行（含 `formatException` 生成的 traceback）上再跑
  `mask_sensitive_info`（`src/utils/logging_utils.py:85-102`）。
- `SensitiveFormatter` 挂在 `src/cli/app.py` 的 console + file
  handler（第 57/62/66 行）；`setup_logger_safety` 在 import 期挂
  SensitiveFilter（第 80 行）。
- 双层防护（Filter 脱消息体 + Formatter 脱整行含堆栈），脱敏幂等。

**记录项 O-2（设计取舍，非缺陷）：`_redact` 的降级兜底。** 与 R-1
同源——`mask_sensitive_info` 不可用时降级为原样返回。本次提交将
降级路径改为"长随机串正则兜底"，R-1 即闭环。

---

## 修复清单（本次提交）

| 编号 | 位置 | 问题 | 修复 |
|------|------|------|------|
| R-1a | `src/api/api_manager.py:_redact` | `mask_sensitive_info` 不可用时原样返回敏感文本 | 降级路径委托 `logging_utils.fallback_mask_sensitive_info`（纯正则兜底，拦截 32+ hex / 40+ base64 / sk- 前缀串） |
| R-1b | `src/agents/llm_client.py:_redact_log_text` | 同上（同源同款降级风险） | 同 R-1a 修复，两处委托收敛到 logging_utils 单一实现 |
| R-1c | `src/utils/logging_utils.py` | 新增兜底能力 | 新增 `fallback_mask_sensitive_info`（取 `_SENSITIVE_PATTERNS` 前 3 条"长随机串"类模式，与 `mask_sensitive_info` 同源避免逻辑漂移） |

O-1 / O-2 为设计取舍记录项，不需修复。

---

## 验证建议（运行时采样）

本次审计为静态路径核查。若需运行时验证，可：
1. 设 `AITESTER_TRACE_DIR=/tmp/audit_traces` 跑 3 任务 benchmark，
   grep trace JSONL 中 `<REDACTED` 占位符计数 > 0（确认脱敏生效）；
2. 构造含 `sk-<32hex>` 的异常消息经 `safe_execute` 触发，确认
   `aitester.log` 中该 key 已被 `SensitiveFormatter` 替换。
