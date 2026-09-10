# Changelog

所有重要变更将记录在此文件中。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [0.9.4] - 2026-09-13

### 缺陷修复
- **批量配置生成器环境变量名失配（M20）**：`generate_batch_config.py` 与内嵌模板的 `main()` 硬编码读 `ALIYUN_API_KEY`/`AGNES_API_KEY` 等 4 个环境变量名，但 `generate_config` 按 `{PROVIDER}_API_KEY`（如 `aliyun_bailian → ALIYUN_BAILIAN_API_KEY`）查键，两者永远对不上、只能落占位符。现改为按 models 实际出现的 provider 推导键名（与 `generate_config` 同源），任意 provider 都能取到；根脚本与内嵌模板同步，新增子进程回归测试
- **`analysis.py` 假 t 检验（M15）**：`significance` 字段此前写死 `"t-test (requires scipy)"` 占位文本（从未执行）。现按 per-task `details` 真实计算：`task_id` 配对走 `ttest_rel`，否则 Welch 双样本；样本不足 / 缺 scipy / 无 details 时如实返回 `insufficient_data` / `unavailable`，不再假装检验过；`generate_comparison_report` 增加 Significance Test 节
- **`code_analyzer` 三处失真**：`replace_function_code` 只匹配 `ast.FunctionDef`，`async def` 被静默漏配（`AsyncFunctionDef` 非其子类）；圈复杂度漏算三目表达式 `ast.IfExp`；`BoolOp` 注释与 CPython 实际行为矛盾（链式 `and` 折叠为单节点而非二叉树）；`parse_function_nodes` 文档声称 args 不含 self/cls 但代码从不剔除——三处均已修正

### 重构
- **统计检验双实现收敛**：`experiments/statistical_analysis.py` 与 `run_statistical_test.py` 各有一份近似重复实现，且旧版按位置（min_len 截断）配对——两基线结果顺序不一致时不同任务被错配成一对、t/p 值失真。现统一为按 `task_id` 配对（同一任务在两个基线下各跑一次），规范实现收敛到 `statistical_analysis.py`（论文提交包引用的文件名），`run_statistical_test.py` 退化为薄壳入口；配对逻辑提取为 `_pair_by_task`、效应量改配对差值标准差口径、NaN 分支安全、Markdown 报告 nan 值显示 n/a
- **chromadb 1.x 现代客户端 API 迁移**：`chromadb.Client(Settings(persist_directory=...))` 已弃用，且 `Settings()` 默认 `persist_directory='./chroma'`——"内存模式"（`persist_path=None`）实际会在 CWD 落出持久目录（与 aiterator.log 同类污染）。现 `persist_path` 给定时用 `PersistentClient`、否则 `EphemeralClient` 纯内存，并关闭 `anonymized_telemetry` 避免后台遥测上报

### 性能
- **RAG 清理全表扫描加 60s 节流**：旧行为每次 `add_case`/`add_repair` 都做一次 `collection.get(include=[metadatas])` 全表扫描（O(N)），大缓存长跑累积为 O(N²)。现"容量未满 且 已清理过 且 距上次 <60s"时跳过扫描；容量满（需驱逐）与首次清理仍每次执行，驱逐语义不变；TTL 默认 3600s，最坏 60s 清理延迟对实际过期语义可忽略

### 测试与文档
- 补齐低覆盖模块测试：`planner.py`（42%→，mock `_call_llm_with_cache` 覆盖 `plan()` 四路径 + `LogicAnalysisResult`）、`synthetic_dataset.py`（48%→，触发惰性加载验证结构/seed 可复现/异 seed 差异/取模覆盖）、`code_analyzer.py`（0%→，17 用例）、`analysis.py`（0%→，11 用例）、`cli/app.py`（`list-examples` 正常/缺目录 + `--version`）；`run` 命令为 140 行编排胶水、需重度 mock，本轮未覆盖
- 修正 `plan()` 文档：非 JSON 实际抛 `JSONDecodeError`（`_extract_json` 委托 `extract_json_object`），此前误标为 `RuntimeError`
- **回归**：全量 **842 passed**（+44 新增用例），0 skipped，1 warning（chromadb 内部 DeprecationWarning，第三方库）；总覆盖率 88%；`ruff check` / `ruff format --check` / lock 同步校验全部通过

## [0.9.3] - 2026-09-13

### 配置与实验正确性修复
- **`.env.local` 写入路径与刷新失效**：`config_manager` 此前把 LLM 配置写进 `src/config/.env.local`（模块所在目录），而应用只读根目录 `.env.local`，`add_llm_config`/`remove_llm_config` 重启后全部不生效。现统一写根目录；新增 `config.refresh_llm_configs()` 原地刷新 `LLM_CONFIGS`（导入时快照不会自动更新），删除时同步清理 `os.environ` 中残留的 `LLM_N_*` 变量；自动编号改为扫描文件已占编号取 max+1（编号空洞不再冲突）；重复模型检查覆盖任意编号
- **基线对比有效性**：`build_workflow` 新增 `planner`/`debugger` 参数（None 回落 config 值），`plain_llm` 基线改为直接构建降级图——此前 `importlib.reload` 改的是 `run_benchmark` 命名空间的全局开关，`workflow.py` 重新 `from config import` 后拿到的仍是原值，开关实际未生效（plain_llm 跑的其实是完整管线）；`run_single_task` 每基线 deepcopy 初始 state 并重置磁盘实例文件（single_agent 基线会把修复代码写回 target_file，共享 state 时后续基线从已修复状态起步）；`run_benchmark` 新增 `seed` 参数并透传 `SyntheticDataset`（此前硬编码 42，`--seed` 被静默忽略），结果 JSON 记录 seed
- **SWE-bench 下载/加载路径对齐**：`download_from_huggingface` 此前写 `~/.cache/aitester/swe_bench_instances.jsonl`，加载器却读 `~/.cache/aitester/swe_bench/`，下载完永远找不到。现默认目录对齐加载器 data_dir，文件名带子集标识（mini/lite/full 不再互相覆盖）；加载器按 subset 读专属文件，未指定时合并全部子集文件并按 instance_id 去重；`instance_code` 优先级 `instance_code > base_code > problem_statement` 兜底
- **批量配置生成器数据丢失防护**：`generate_batch_config.py` 及内嵌模板在模型列表为空时以 "w" 模式写 `.env.local` 会抹掉现有全部 LLM 配置，现改为报错退出（新增子进程回归测试）

### 缺陷修复
- **错误报告上下文失效**：`ReportGenerator.generate()` 此前 `classify() + context=None`，ImportError 根因/修复建议分支（依赖 `context.module_name`）是死代码、`error_subtype` 恒为 None。现接 `classify_with_context`，并修复 `context.subtype` 为 None 时的 `.value` 崩溃；`save_report` 对参与文件名拼接的 task_id 做白名单 + 截断消毒（防路径穿越）；分类器 traceback 分支不再给纯运行时错误误标 `SYNTAX_ERROR` 子类型
- **RAG 相似度恒 0.0**：ChromaDB 余弦空间下 distance 不在 metadatas 中，旧 `meta.get("distance", 0.0)` 永远取默认值。现从查询结果 `distances` 字段换算 `similarity = round(1 - distance, 4)`
- **CLI 健壮性**：模块导入期的 `FileHandler("aitester.log")` 在只读 CWD 下 PermissionError 崩溃整个 CLI，现捕获 OSError 降级为仅控制台；覆盖率 0.0 是合法数据，三处 falsy 判断误显示 N/A 改为 `is not None`
- **BaseAgent 客户端复用**：`__init__` 此前每实例新建一个 `ChatOpenAI`（生产调用全走 `_call_llm` 的缓存客户端，`self.llm` 实为占位属性），现改为复用模块级缓存；修正 `_call_zai` docstring（实际所有可重试异常统一 5s 基准退避，旧注释与实现不符）

### 重构
- **`APIManger` → `APIManager`**：类名拼写错误统一重命名（src/api、`__init__` 导出、测试与示例共 6 文件），后台线程名同步更正；1.0 前无外部用户，不做别名兼容；CHANGELOG 历史记录中的旧拼写保留
- **加载 hack 简化**：`api_manager`/`config_manager` 中重复的 `importlib + sys.modules` 别名加载 `config.py` 改为常规 `from config import`（无循环导入风险，且消除两份独立模块实例）
- **CLI 死代码清理**：移除无引用的 `tqdm`/`TQDM_AVAILABLE` 探测块与转导的 `rich.progress` 组件

### 文档与一致性
- **reproduce.sh**：单测 tee 目录前置创建 + pipefail 容错；SWE-bench import 路径修正（`src.datasets.dataset_loader`）；环境校验从废弃的 `OPENAI_API_KEY` 改为 `LLM_1_API_KEY`；Python 3.10+ → 3.12+（锁定依赖 scipy==1.18.0 要求）
- **`.env.example`**：`DOCKER_IMAGE` 3.11-slim → 3.12-slim（与锁定依赖/config.py 默认/Dockerfile 对齐）；`DOCKER_ENABLED` 注释如实说明容器隔离尚未实现（`use_docker` 为保留接口）
- **回归**：全量 **798 passed**（+11 新增用例），0 skipped，1 warning（chromadb 内部 DeprecationWarning，第三方库）；总覆盖率 83%；`ruff check` / `ruff format --check` / lock 同步校验全部通过

## [0.9.2] - 2026-09-09

### CI 门禁修复（主分支恢复全绿）
- **ruff format 门禁转红修复**：主分支 CI 在 "Lint with ruff" 步骤失败（`ruff format --check` 对 `src/agents/base_agent.py`、`src/cli/app.py`、`tests/test_cli_run.py` 三个文件要求重排），全仓库重新执行 `ruff format` 修复
- **CI 固定 ruff 版本**：此前 CI `pip install ruff` 安装最新版，上游发版改变格式化规则时门禁随机转红（2026-09-09 相邻两次 CI 运行结果不一致即此原因）。现固定 `ruff==0.16.3`（与 `requirements.lock` 一致），升级时同步更新 lock
- **补齐 DBUtils 依赖声明**：`src/db/mysql_client.py` 使用 `dbutils.pooled_db.PooledDB`，但 `requirements.txt`/`requirements.lock`/`setup.py` 均未声明——全新环境安装后 `src.db` 模块 ImportError。现补齐 `DBUtils==3.1.2` 并新增 `tests/test_mysql_client.py`（11 个用例，mock 连接池覆盖单例、commit/rollback 与三张表 CRUD）

### 测试质量提升
- **重新启用 LLM 文件缓存 6 个测试**：`test_base_agent_extended.py` 中 6 个以"局部 import os/json 无法 patch"为由 skip 的测试，其 skip 理由在源码重构为模块级 import 后已失效。现通过 `AITESTER_LLM_CACHE`/`AITESTER_LLM_CACHE_DIR` 环境变量实现：缓存未命中、命中、prompt 不匹配、读取损坏 JSON、写入成功、写入异常 6 条路径全覆盖（skip 清零）
- **API 管理器线程卫生测试**：新增 5 个用例（单例一致性、reset 停止健康检查线程、并发 get_manager 单实例、故障转移迁移日志）
- **报告生成器测试补全**：新增 `tests/test_report_generator.py`（44 个用例），`src/reports/generator.py` 覆盖率由 **0% 提升至 100%**。覆盖 ErrorReport 四种序列化（dict/text/markdown/json）全部分支、generate() 五大错误分类路径、根本原因/修复建议的 context 分支（`generate()` 内 context 恒为 None，需直接调用私有方法构造 `ErrorContext` 覆盖）、`_parse_failed_cases` 解析（含 name 兜底为 unknown 的边界）、`save_report` 三格式落盘与单例语义

### 缺陷修复
- **API 管理器后台线程泄漏**：`reset_manager()` 此前只清全局引用，`APIManger` 初始化的后台健康检查守护线程（每 60s 发起真实 LLM 探测）残留，继续对旧实例消耗 API 配额。现 reset 前调用新增的 `_stop_health_checker()` 显式停止并等待线程退出
- **故障转移日志错误**：`_try_call_node` 的 "故障转移成功" 日志此前把**当前**节点名打印两遍（`%s -> %s` 同值），无法看出迁移路径。现经 `prev_model` 参数记录"上一节点 -> 当前节点"
- **单例线程安全**：`get_manager()` 增加双重检查锁，多线程并发只创建一个管理器实例

### 代码质量
- **版本号收敛为单一事实来源**：`src/__init__.py` 新增 `__version__`（0.9.2），`setup.py` 与 CLI `--version` 均从此读取，消除两处硬编码漂移
- **RAG 类 pytest 收集告警**：`TestCaseRetriever` 类名以 Test 开头触发 `PytestCollectionWarning`，加 `__test__ = False` 消除
- **魔数提升**：`workflow._patch_applier_node` 内 `_MAX_REPAIR_HISTORY` 提升为模块级常量（附注释）
- **冗余 import 清理**：`generator._validate_parametrize` 移除方法内重复的 `import ast`（模块顶部已导入）

### 文档与一致性
- **README 测试状态刷新**：测试数 708→787 passed、0 skipped；"最新优化/最近改动" 行同步本轮内容
- **requirements.txt 过时注释修正**：CI Python 矩阵说明 3.10-3.12 → 3.12-3.14；ruff 安装说明改为固定版本
- **回归**：全量 787 passed, 0 skipped, 1 warning（chromadb 内部 DeprecationWarning，第三方库问题）；`ruff check` / `ruff format --check` / lock 同步校验全部通过

## [0.9.1] - 2026-09-09

### CLI 选项失效修复（state 贯通）
- **--timeout 生效**：此前 `run --timeout` 值传入 `_run_single_task` 后从未被使用，Executor 直接读 `os.getenv("EXECUTION_TIMEOUT", "30")`，绕过了 config 的范围校验。现经 state 新增 `execution_timeout` 字段贯通到 `_executor_node`（优先级：state 注入 > config.EXECUTION_TIMEOUT）
- **--coverage-threshold 生效**：此前该选项仅做 0-100 校验后从未参与任何判定。现经 state 新增 `coverage_threshold` 字段贯通，结果字典新增 `coverage_ok`（无覆盖率数据时为 None 不误判）与 `coverage_threshold` 字段，文本摘要展示达标状态

### 缺陷修复
- **LLM 配置加载遇编号空洞中断**：`config._load_llm_configs` 原实现在首个不完整编号处 `break`，删除中间某个 provider（如 LLM_2）会导致后续编号（LLM_3+）静默失效。改为扫描至上限 32 并跳过不完整编号，结果按原编号顺序保持
- **指数退避公式错误**：`base_agent._retry_with_exponential_backoff` 等待时间误写为 `base_wait**attempt`——默认 base_wait=1 时退化为固定 1s（非文档宣称的 1s/2s/4s），zai 路径 base=5 时膨胀为 5s/25s/125s。修正为 `base_wait * 2**attempt`（1s/2s/4s；zai 5s/10s/20s）
- **Executor 导入替换误伤第三方库**：`_apply_import_replacements` 原用未锚定正则对**全部** import 语句做全局替换，测试代码中的 `import numpy` 等第三方库会被错误改写为被测模块名。现按模块名锚定正则，并经相似度门控（SequenceMatcher ≥ 0.6，如 calculater→calculator）仅替换目标模块名的笔误变体；顺带消除未使用的 `_RE_FROM_REPLACE`/`_RE_IMPORT_REPLACE` 模块级正则

### 代码质量
- **CLI 统计去重**：`run` 命令的 total/passed/failed 此前在 JSON/非 JSON 两个分支各算一次，合并为单一计算点
- **异常处理去重**：`_handle_task_exception` 的 `future.exception()` 从两次调用降为一次并记入日志
- **Executor 小优化**：`_build_sys_path_code` 多目录注入不再产生重复 `import sys` 行；`_parse_coverage` 优先只扫描 TOTAL 汇总行（保留全文扫描兜底）
- **回归**：新增 13 个回归测试（CLI state 贯通 6 + Executor 导入保护 3 + 退避公式 1 + 配置空洞容忍 3），全量 721 passed, 6 skipped；ruff 全绿

## [0.9.0] - 2026-09-09

> 说明：0.4.0–0.8.0 时期的迭代工作记录在 README「迭代优化记录」章节，CHANGELOG 未逐版记录；本版本为最近一次版本发布。

### CI 兼容性与安全扫描修复 (2026-09-09)
- **矩阵与锁定版本对齐**：lock 生成自 Python 3.14 开发环境，`scipy==1.18.0` 要求 `>=3.12`、`pandas/matplotlib` 要求 `>=3.11`，原矩阵 3.10/3.11 装不上锁定版本集。矩阵收窄为 `['3.12', '3.14']`（下限 + 开发环境），Codecov 上传条件同步改为 3.14
- **安全扫描迁移**：废弃的 `safety` 工具（`check` 子命令 2024-06 起不再支持，CI 上退出码 64）替换为 PyPA 维护的 `pip-audit`
- **chromadb 漏洞例外（记录在案）**：`chromadb==1.5.9` 命中 PYSEC-2026-311（=CVE-2026-45829）、CVE-2026-45830/45831/45833 共 4 条已知漏洞，PyPI 上无修复版本（1.5.9 即最新），CI 以 `--ignore-vuln` 显式忽略并注释说明；**后续动作：chromadb 发布修复版后立即升级并移除忽略**
- **pytest-timeout 降级 2.5.0→2.4.0**：2.5.0 已被上游 yank（原因 "accidental breaking change (probably)"），此前 lock 误锁了该 yanked 版本。降级为最新未 yank 的 2.4.0（已验证与 pytest 9.1.1 的 `--timeout` 行为正常）；requirements/lock/本地 .venv 三处同步
- **action 版本升级**：`checkout@v4→v5`、`setup-python@v5→v6`（消除 Node.js 20 弃用告警）
- **CI 测试步骤失败根因修复**：本地无 `.env.local` 的干净仿真（仅 mock `LLM_1_*`）复现出唯一失败用例 `test_contains_expected_models`——它硬编码断言模型名含 `qwen/deepseek/agnes/glm`，CI 的 mock 名 `test-model` 不匹配（环境依赖型测试缺陷）。重构为结构校验（模型名与已配置 LLM 一一对应）+ 无真实厂商配置时 `pytest.skip`；dev 环境（真实 `.env.local`）行为不变
- **CI 测试失败诊断注解**：新增 `if: failure()` 诊断步骤，失败时重跑 `pytest -q --tb=no -rf` 提取 FAILED/ERROR 清单并写 `::error` 注解（check-runs annotations API 公开可读，无需 admin 下载日志）；诊断步骤与测试步骤携带同一套 mock env，避免重跑产生假失败

### CI lock 一致性校验 (2026-09-09)
- **新增 lock 同步校验**：`scripts/check_lock_sync.py`（纯 stdlib），校验 `requirements.txt` 中每项依赖都存在于 `requirements.lock` 且 `==` 锁定版本与 lock 一致；CI 新增 "Check lock sync" 步骤，版本脱节即阻断合并
- **验证方式**：故意把 langgraph 版本改成 9.9.9，脚本正确报"版本脱节"并退出码 1；恢复后通过

### 性能优化 (2026-09-09)
- **ChatOpenAI 客户端复用**：`base_agent._call_llm` 此前每次调用都新建 `ChatOpenAI` 实例（底层 httpx 连接池随之重建，无法复用 TCP/TLS 连接）。新增 `_get_or_create_chat_client`，按 `(model, temperature, api_key, base_url)` 缓存实例（上限 16，FIFO 淘汰），进程内复用连接；客户端线程安全，兼容 `--parallel` 并发
- **zai 路径客户端复用**：`_call_zai` 此前每次调用都新建 `ZhipuAiClient`。经核实 `ZhipuAiClient` 继承自 OpenAI SDK 基类、底层共享线程安全的 `httpx.Client`，故新增 `_get_or_create_zai_client`，按 `(api_key, base_url)` 缓存（model 是请求参数不进键）
- **测试隔离**：`tests/test_base_agent_extended.py` 增加 autouse fixture 清理两套客户端缓存，避免 mock 实例跨测试残留；新增 8 个客户端复用单测（ChatOpenAI 4 个 + zai 4 个，后者通过向 `sys.modules` 注入假 `zai` 模块追踪构造次数）
- **回归**：708 passed, 6 skipped

### CLI 拆包与 CI 修复 (2026-09-09)
- **main.py 拆包为 src/cli/**：507 行的 main.py 拆为 `src/cli/app.py`（命令定义与任务执行）+ `src/cli/output.py`（ANSI/Rich 输出工具），main.py 保留为薄入口，`python main.py ...` 与 setup.py 控制台脚本行为不变；`list-examples` 路径定位改为按项目根计算（拆分前用 `__file__` 指向根目录）
- **修复 CI 格式化门禁**：全仓库 `ruff format` 统一（33 个文件，纯格式变更），此前 `ruff format --check` 步骤必然失败
- **CI 安装步骤去重**：`pytest-cov` 已在 requirements.txt 中锁定，移除 CI 中的重复安装行
- **回归**：700 passed, 6 skipped；`python main.py --help` / `list-examples` 冒烟通过

### 依赖治理 (2026-09-09)
- **顶层依赖锁定**：`requirements.txt` 的 18 个顶层依赖由 `>=` 改为 `==`，版本与 `requirements.lock` 同步，保证 CI（Python 3.10-3.12 矩阵）安装可复现
- **补装 CI 缺失插件**：新增 `pytest-timeout==2.5.0`（`pyproject.toml` addopts 的 `--timeout=1200` 依赖它，此前 CI 安装步骤未包含，pytest 会因无法识别 `--timeout` 参数而失败）
- **移除未使用依赖**：`radon` 全项目无 import 引用，从 `requirements.txt` 与 `setup.py` 移除（注释记录备查）
- **修正过期注释**：`requests` 实际被 `scripts/check_quota.py` 使用，原"未直接使用"注释已更正

### 架构重构与性能优化 (2026-09-09 续)
- **模块归类到子包**：`dataset_loader`/`synthetic_dataset` → `src/datasets/`，`api_manager` → `src/api/`，`config_manager`/`config_generator` → `src/config/`，`exceptions` → `src/utils/`，更新全部导入引用
- **LLM 文件缓存接入**：`base_agent._call_llm_with_cache` 正式接入 planner/generator/debugger，相同 prompt 命中缓存省 token；新增开关 `AITESTER_LLM_CACHE` 与目录 `AITESTER_LLM_CACHE_DIR`（默认启用，测试自动隔离）
- **重写 llm_cache**：`src/graph/llm_cache.py` 由空壳改为可用线程安全 LRU，命中率统计准确（可选内存缓存工具）
- **新增额度探测脚本**：`scripts/check_quota.py`，逐个模型 1-token 探测存活/403 额度/限流/key 失效，不打印密钥
- **模型目录更新**：Agnes 国内站 `agnes-2.5-flash` → `agnes-3.0-flash`；默认模型 `LLM_1` 切至 `agnes-3.0-flash`
- **测试修复**：dataset_loader 接口/环境依赖/下载 mock 修复；全量 700 passed, 6 skipped, 0 failed
- **文档**：README/QUICKSTART/docs 同步架构、缓存、脚本与模型；`.gitignore` 增加 `src/cache/`、`.env.local.bak`

### 代码优化 (2026-09-09)
- **提取公共工具模块**：新增 `src/utils/helpers.py`，统一代码块和 JSON 提取逻辑
  - `extract_code_block()`: 从 LLM 输出中提取代码块（支持多种格式）
  - `extract_json_object()`: 从文本中提取 JSON 对象（含括号平衡法）
- **重构 base_agent.py**：移除重复代码，委托调用公共工具函数（-85 行）
- **重构 patch_applier.py**：使用公共工具函数替代 `_extract_patch_code()`（-34 行）
- **优化 workflow.py**：
  - 移除冗余常量 `_DEFAULT_MAX_ITERATIONS`
  - 简化路径安全检查逻辑（使用 tuple 替代 list）
  - 改进类型注解
- **测试修复**：更新测试文件以适配新的导入路径
- **测试结果**：524 passed, 6 skipped（核心模块 100% 通过）

---

### 代码质量优化
- **修复代码规范问题**：全部 E501 (行长度) 和 C901 (复杂度) 问题已修复
- **重构 config_manager.py**：
  - 提取 `_is_model_config_line()` 辅助函数
  - 提取 `_is_model_comment()` 辅助函数
  - 提取 `_find_and_remove_model_block()` 辅助函数
  - 降低 `remove_llm_config()` 复杂度 (11→9)
- **重构 dataset_loader.py**：
  - 提取 `_load_project_version()` 方法
  - 降低 `Defects4JPYDataset._load_raw_data()` 复杂度 (13→9)
- **修复测试文件**：
  - 简化 test_debugger.py 的 sys.path 导入
  - 修复 test_error_classifier.py 的行长度
  - 修复 test_rag_retriever.py 的长列表定义
  - 修复 test_dataset_loader.py 的测试逻辑

### 测试状态
- 总测试数：686
- 通过：551 (核心测试)
- 跳过：6
- 失败：5 (网络超时，数据集下载测试)
- 覆盖率：70% (核心模块 85%+)

### 代码规范
- ✅ Ruff check 全部通过
- ✅ 行长度 ≤ 120 字符
- ✅ 代码复杂度符合要求

---

## [0.3.0] - 2026-08-18

> 说明：本节工作于 2026-08-18 完成，此前一直挂在 [Unreleased] 未随版本发布，2026-09-09 整理时补记为 0.3.0 并随 0.9.0 一并归档。

### 全量功能验证（2026-08-18）
- **测试结果**：873 个测试用例收集，860 通过（98.6%），12 失败（已知边界问题），1 跳过
- **验证范围**：单元测试 + 集成测试 + CLI端到端 + 模块导入 + 实验脚本
- **已通过模块**：
  - CLI：`run`、`list-examples` 命令正常
  - Agent 层：BaseAgent(46)、ExecutorAgent(30)、PlannerAgent(5)、ErrorClassifier(44)、GeneratorAgent(7)、DebuggerAgent(5)
  - 工具层：CodeAnalyzer(12)、PatchApplier(33)
  - 工作流层：workflow(63)、state(5)、llm_cache(24)
  - 集成测试：integration(52)、e2e(34)、examples(90)
  - API 管理器：APIManager(50，含 22 节点大规模测试)
  - RAG 检索器：retriever(16)、report_generator(43)
  - 数据集：dataset_loader_extended(33)、synthetic_dataset(40)
  - 实验脚本：run_benchmark/run_large_scale/visualize_results/statistical_analysis/analyze_failures 全部可用
- **已知失败**：
  - `test_retriever_extended.py` 6 个（Python 3.14 MagicMock 行为变化）
  - `test_base_agent_zai.py` 2 个（API 配额耗尽）
  - `test_dataset_loader.py` 3 个（HuggingFace mock 配置）
  - `test_concurrent_execution_safety` 1 个（随机性，重跑通过）
- **详细报告**：`FUNCTIONAL_VALIDATION_REPORT_20260818.md`（文件已不在仓库中，仅作记录）

### 新增功能
- **API 管理器增强**：新增 `src/api_manager.py` 模块，支持多 Provider 轮询和高可用故障转移
  - 实现轮询、加权随机、健康感知、最快优先四种策略
  - 支持动态节点添加/移除
  - 自动健康检查与故障转移
  - 新增 31 个单元测试覆盖完整功能
- **LLM 缓存机制**：实现 `src/graph/llm_cache.py`，支持 LLM 调用结果缓存
  - 减少重复 API 调用，节省 token 消耗
  - 提供缓存统计接口
- **错误报告生成器**：新增 `src/reports/` 模块，支持将测试失败信息转化为结构化诊断报告
  - 支持文本、JSON、Markdown 三种输出格式
  - 自动分类错误类型（语法/运行时/断言/超时/未知）
  - 生成根本原因分析和修复建议
  - 集成 `ErrorClassifier` 进行错误分类
  - 新增 13 个单元测试覆盖完整功能
- **多 LLM 配置支持**：`LLM_CONFIGS` 列表支持 API Key 轮询和高可用
  - 配置格式：`LLM_N_API_KEY`, `LLM_N_BASE_URL`, `LLM_N_MODEL_NAME`
  - 向后兼容：保留 `MODEL_NAME`, `OPENAI_API_KEY` 等旧变量名

### 代码质量
- **Ruff 代码格式化**：修复 791 个代码风格问题（导入排序、空白行、过时类型注解等）
- **类型注解现代化**：将 `Optional[X]` 替换为 `X | None`，符合 Python 3.10+ 风格

### 工程化改进
- **Ruff Lint 配置**：新增 `pyproject.toml`，配置 ruff 进行代码检查和格式化（替代 flake8 + isort）
- **Pre-commit Hooks**：新增 `.pre-commit-config.yaml`，集成 ruff、mypy、trailing-whitespace 等检查
- **GitHub Actions CI**：新增 `.github/workflows/ci.yml`，支持多 Python 版本测试、lint 检查和安全扫描
- **pytest 配置**：在 `pyproject.toml` 中配置 pytest 参数（测试路径、标记、输出格式）

### 性能优化
- **RAG 检索器单例化**：将 ChromaDB 客户端改为懒加载单例模式（`src/graph/workflow.py`），节省每个任务 2-6 秒初始化时间
- **LLM_TIMEOUT 配置接入**：在 `src/agents/base_agent.py` 中接入 `LLM_TIMEOUT` 配置，防止 LLM 调用卡死
- **并发执行支持**：实现 `BENCHMARK_PARALLELISM` 环境变量驱动的多线程并行基准测试（`experiments/run_benchmark.py`）
- **Parametrize 重试逻辑优化**：修复 `src/agents/generator.py` 中 parametrize 校验失败时使用相同 query 重试的问题，改为追加负面反馈提示
- **Executor 导入路径搜索优化**：限制 `_auto_fix_imports` 的全量 rglob 遍历，优先检查常见路径（`src/`, `lib/`, 当前目录），提升 98.6%

### Bug 修复
- **指数退避重试逻辑**：修复 `src/agents/base_agent.py` 中的重试退避策略
- **路径安全检查**：增强 `src/tools/patch_applier.py` 的路径验证，防止路径遍历攻击
- **模块导入路径搜索优化**：限制 `_auto_fix_imports` 的全量 rglob 遍历，优先检查常见路径（`src/`, `lib/`, 当前目录）

### 文档更新
- **README.md**：添加性能优化说明章节，包括 RAG 单例化、LLM_TIMEOUT 配置、并发执行使用指南
- **README.md**：更新快速开始部分，新增并发执行命令示例
- **README.md**：更新配置说明表格，补充 LLM_TIMEOUT 和 LLM_RETRY_WAIT 配置项
- **README.md**：更新迭代优化记录，添加 v0.10 和 v0.9 变更记录
- **README.md**：更新测试状态表格，反映最新测试结果（696+ passed）
- **CHANGELOG.md**：添加多 LLM 配置支持说明
- **新增文档**：`docs/performance_optimization_report.md`、`docs/report_generator_guide.md`、`API_MANAGER_EXTENSION_GUIDE.md`（该批文件后续已清理出仓库，此处仅作历史记录）
- **迭代报告**：`ITERATION_REPORT_20260818.md`、`FINAL_ITERATION_SUMMARY.md`、`ITERATION_REPORT_ROUND2.md`（该批文件后续已清理出仓库，此处仅作历史记录）
- **架构文档**：更新 `docs/algorithm_design.md`，反映 RAG 单例化改动

## [0.2.0] - 2026-08-17

### 工程化改进
- **Ruff Lint 配置**：新增 `pyproject.toml`，配置 ruff 进行代码检查和格式化
- **Pre-commit Hooks**：新增 `.pre-commit-config.yaml`，集成 ruff、mypy、trailing-whitespace 等检查
- **GitHub Actions CI**：新增 `.github/workflows/ci.yml`，支持多 Python 版本测试、lint 检查和安全扫描
- **pytest 配置**：在 `pyproject.toml` 中配置 pytest 参数（测试路径、标记、输出格式）

### 文档更新
- **README.md**：更新测试状态表格，集成测试已标记为通过（52 passed）
- **README.md**：新增「开发工具」章节，包含 Ruff lint、Pre-commit hooks、CI/CD、测试命令说明
- **CHANGELOG.md**：按 Keep a Changelog 格式规范更新

### 测试状态
- 单元测试：215 passed（含集成测试）
- 无硬编码密钥
- 代码覆盖率 75%（目标 80%+）

---

## [0.1.0] - 2026-08-14

### 新增
- 初始版本发布
- 四智能体协作架构（Planner → Generator → Executor → Debugger）
- 支持 examples、synthetic、swe_bench 三种数据集
- Docker 一键复现支持
- 完整单元测试（185 个用例，17 个测试文件）

---

## 版本说明

- `Unreleased`: 当前开发中功能，尚未正式发布
- 版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)
