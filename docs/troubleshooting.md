# 故障排查

最后更新：2026-10-26 · English: [troubleshooting.en.md](troubleshooting.en.md)

按「症状 / 原因 / 处置」组织。先跑零 LLM 自检：`python3 main.py doctor`。

## 1. 安装与环境

**症状**：`ModuleNotFoundError: No module named 'pytest'`，任务报 `execution_dependency_missing`。
**原因**：执行侧依赖未安装（wheel 安装默认不含执行工具）。
**处置**：`pip install "aitester[execution]"`，或改为 `pip install -r requirements.txt`。

**症状**：`401` / `403`，或 `LLM 调用失败，已重试`。
**原因**：`LLM_1_API_KEY` 无效、额度用尽，或 `.env.local` 未创建。
**处置**：从 `config.local.example` 复制 `.env.local` 并填入端点；用
`python3 experiments/run_smoke_llm.py` 做最小连通性检查。

**症状**：`429` 限流或长时间无响应。
**原因**：端点限流，或 `LLM_TIMEOUT` 对深度思考模型过短。
**处置**：降低并发；设置 `LLM_THINKING_MODE=disabled`；必要时调大 `LLM_TIMEOUT`。

**症状**：`doctor` 报配置项非法或缺失。
**原因**：环境变量拼写错误或取值越界。
**处置**：对照 [api_reference.md](api_reference.md) 的配置表修正；`doctor --json` 可定位到具体项。

**症状**：`doctor` 退出码 2，提示「用法错误」或「未知分组」。
**原因**：`--groups` 为空或只有逗号，或分组名拼写错误（区分大小写）。
**处置**：`python3 scripts/tools/e2e_probe.py --list` 查看可用分组；省略 `--groups` 跑全量。

**症状**：`doctor` 提示「功能矩阵不可用」。
**原因**：pip 安装的 wheel 不含 `scripts/`，功能矩阵只在源码检出中可用。
**处置**：环境/配置检查仍然有效；需要矩阵时在源码检出内运行 `python3 main.py doctor`。

**症状**：`check-dataset` 退出码 2 / 1，或 `clean-venv-cache` 拒绝了过滤条件。
**原因**：数据集名不在注册表名单、数据未就位（加载到 0 个任务），或过滤值为负。
**处置**：按错误行列出的合法名称改正（大小写与连字符不敏感）；`--limit 0` 只看汇总；
`clean-venv-cache` 的 `0` 表示「全部过期」，只有负数被拒（负数在删除逻辑里恒真）。

## 2. 运行与沙箱

**症状**：`docker_unavailable` / `docker_timeout`。
**原因**：未安装 Docker、守护进程未启动，或镜像未构建。
**处置**：设置 `EXECUTOR_USE_DOCKER=false` 改用 venv 沙箱；或先构建镜像再重试。

**症状**：沙箱内缺依赖，或复跑结果与上次不一致。
**原因**：venv 缓存与当前依赖指纹不一致。
**处置**：`python3 main.py clean-venv-cache --max-age-days 7`；必要时
`--list-only` 先确认再清理。

**症状**：RAG 初始化失败，日志出现 `rag_retrieval_empty`。
**原因**：chromadb 未安装、嵌入模型下载失败，或 `rag_data/` 损坏。
**处置**：安装可选依赖 `pip install chromadb`；或将 `rag_data` 重命名后重建；不装时链路
按无 RAG 口径降级，属预期行为。

**症状**：`llm_localization` 恒为 `None`，或 `localization_hit_function` 全空。
**原因**：推理定位通道被关闭（`FAULT_LOCALIZER_ENABLE=false`），或 LLM 定位失败后保守降级。
**处置**：确认 `FAULT_LOCALIZER_ENABLE=true`；纯谱系消融实验则属预期口径，读数时注明。

**症状**：补丁应用后测试仍失败，或回滚未发生。
**原因**：证据门拒绝补丁，或 P2P 回归判定为 `regression_error` 且未启用 fail-closed。
**处置**：查看 `error_info.type` 与补丁证据；需要严格回滚时设置
`PATCH_ROLLBACK_FAIL_CLOSED=true`。

## 3. 测试与门禁

**症状**：会话输出出现 `实测 12,xxx passed` 之类数字，与 `BASELINE.yaml` 不一致。
**原因**：把历史叙述或单次运行读数当成了登记值。
**处置**：以 `BASELINE.yaml` 为唯一事实源；刷新读数走「实测 → BASELINE → 登记册 §1 → gates」。

**症状**：`make docs-check` 报缺英文配对、日期不一致或章节数偏差。
**原因**：新增/修改中文文档后未同步 `.en.md`，或两侧「最后更新」日期不同。
**处置**：补齐英文孪生并对齐日期；确属单语文档时在
`scripts/gates/check_bilingual_docs.py` 的豁免清单登记理由。

**症状**：`make doc-commands` 报某 `make` 目标或 `scripts/*.py` 不存在。
**原因**：文档引用了已改名/删除的命令或脚本。
**处置**：按报错行修正文档；不存在的能力不要写进文档。

**症状**：`make registration-consistency` 报 §1 数字漂移或在盘分册未登记。
**原因**：BASELINE / 登记册 / INDEX 未同步，或 `docs/reviews/` 新增文件没进 §3.5。
**处置**：按报错项刷新登记册与 [INDEX.md](INDEX.md) §3.5；不要手工复制计数。

**症状**：`ruff format --check .` 报 Markdown 文件需格式化。
**原因**：代码围栏内的 Python 片段也参与格式化。
**处置**：直接运行 `ruff format .` 后重跑；不要只格式化 `.py`。

**症状**：pytest 退出码 0 但套件全 skip。
**原因**：`rc==0` 不等于有断言执行的通过。
**处置**：派生读数按「至少 1 passed 且 0 failed」判定；否则记 `unverifiable`，见
[preregistration.md](preregistration.md)。

**仍未解决**：带最小复现（命令、完整报错、`python3 main.py doctor --json` 输出、commit sha）
开 Issue；安全漏洞不要走私开 Issue，见 [SECURITY.md](../SECURITY.md)。
