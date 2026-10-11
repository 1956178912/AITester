# WS3 代码实现与领域专项独立审计（声称 vs 实现）

- 审计对象：`/Users/wangchenyu/Workspace/AITester` **工作树**（HEAD `d9e51dfccb82e2ffcd9518c0fe78a0e81f035b84`，`git status` 77 项未提交：35 M + 42 ??；本报告结论只对这一刻的工作树成立）
- 审计时间：2026-10-11
- 本机环境（实测）：Python 3.14.6（`.venv`）、mypy 1.15.0、ruff 0.16.3、z3 可用、macOS(darwin)
- 方法：只读代码 + grep + 小探针（AST 统计、import 阻断、正则探针、mypy `-c` 探针、`ruff check`、单测试文件）。**未跑真实 LLM / 未跑长时间批次**。
- 纪律声明：项目内既有审查报告（`review_2026/`、`audit_2026/`、`EXTERNAL_REVIEW_*`、`FINAL_REVIEW_*`、`README`/`CHANGELOG`/`BASELINE.yaml` 的方法描述、`docs/design/`、ADR）在本报告中**只作为"声称出处"引用，不作为事实**。下列每条结论的证据均为我自己读代码/跑命令所得；无法确证的写入 §E。
- 已独立执行的命令（真实输出见正文）：`ruff check .` / `ruff check src|experiments|scripts|tests|config.py`、`pytest tests/test_executor.py`（41 passed）、`mypy --config-file pyproject.toml -c ...`、src 全模块导入扫描（124/124 成功）、可选依赖阻断导入探针、`kernel_sandbox` 实机探针、`git log --all -- .env`、工件 JSON 逐字段比对。

---

## §A Python 工程化诊断表

| # | 维度 | 证据（file:line） | 现状（我自己核实的事实） | 严重度 | 与声称是否不符 |
|---|---|---|---|---|---|
| A1 | 打包双源 | `setup.py:26-53`（`setup()` + `install_requires`）、`pyproject.toml:32-61`（`[project].dependencies`）、`setup.py:54-71`（`extras_require`）、`pyproject.toml:74-91`（`[project.optional-dependencies]`）、`tests/test_packaging.py:137-145,175-184` | `setup.py` 已声明为兼容 shim，但**仍完整重复** 8 个 `install_requires` 与 7 组 `extras`（rag/viz/experiments/ux/dev/db/formal）。双源由测试用 AST 守卫**名字集合**（非版本）。实测两侧集合一致 | P2 | 一致（"唯一事实来源"指 PEP 621 元数据；重复声明仍在，属维护风险而非漂移） |
| A2 | 版本与 requires-python | `pyproject.toml:21,24`、`pyproject.toml:63-66`、`setup.py:26-37`（`version=_load_version()` / `python_requires=">=3.12"`）、`src/__init__.py`（dynamic version）、`.github/workflows/ci.yml:107-118` | 版本走 `dynamic={attr="src.__version__"}` + `_load_version()` 同源；`requires-python=">=3.12"` 与 `python_requires=">=3.12"`、CI 矩阵 `['3.12','3.13','3.14']` 三方一致 | P2 | 一致 |
| A3 | 依赖三源一致性 | `requirements.txt:1-80`、`requirements.lock:1-132`、`scripts/gates/check_lock_sync.py:1-20` | 我逐项解析：requirements.txt 23 项**全部**在 lock 中，`==` 版本**零漂移**；lock 132 项含 109 项传递依赖。pyproject 8 个核心依赖与 requirements.txt 名字集合一致，仅"下限 `>=` vs 钉版 `==`"差异（设计如此）。`check_lock_sync` 只比对 txt↔lock，**不含 pyproject**（自述于 `pyproject.toml:50-51`） | P2 | 一致；pyproject 侧版本漂移无门禁（已知设计，非隐藏） |
| A4 | 可选依赖降级真实性 | `pyproject.toml:74-91`、`src/cli/app.py:318-329`（`_rich_available` 守卫）、`src/specs/spec_smt.py:63-71`、`src/utils/embedding_utils.py:225-234`（numpy `try/except ImportError`） | **实测量化**：用 meta_path 阻断 `rich/chromadb/hypothesis/z3/matplotlib/datasets/scipy` 后，`src.cli.app`、`src.specs.spec_smt`、`src.graph.rag`、`src.specs.spec_ir`、`src.datasets.dataset_loader`、`src.experiments.analysis` **全部导入成功**；`_rich_available()→False`、`smt_available()→False`。降级路径真实存在，非纸面 | P2 | 一致（这一条是"声称=实现"的正面证据） |
| A5 | 入口点 / 可安装性 | `pyproject.toml:93-94`、`setup.py:72-78` | 双源 `console_scripts: aitester=src.cli.app:cli`；实测 `import src.cli.app` 成功且 `cli` 存在；`build_workflow()` 可构造（返回 `_RecursionLimitedGraph`）。**未**实测 `python -m build` / 全新 venv 安装（无网络+耗时，见 §D/§E） | P2 | 未完全核实（静态一致） |
| A6 | 循环导入 | 实测脚本：遍历 `src/**/*.py` 共 124 个模块逐一 `import_module` | **ok=124，failed=0** | P2 | 一致（无循环导入崩溃面） |
| A7 | mypy 严格度（**核心**） | `pyproject.toml:232-256`（只有 `[[tool.mypy.overrides]]`，**无 `[tool.mypy]` 严格开关**）、`.github/workflows/ci.yml:175-178`、`.pre-commit-config.yaml:22-30` | 配置里没有任何 `strict`/`disallow_untyped_defs`/`check_untyped_defs`/`warn_unused_ignores`；只有按模块 `ignore_missing_imports=true`。**实测探针**（`mypy --config-file pyproject.toml -c`，两处同样错误、一处未标注、一处已标注）：只报 1 个错（标注函数），**未标注函数体内的类型错误不被检出**。AST 统计：src 共 1111 个函数，**完全标注 842（75.8%）**→ 约 269 个函数体在门禁之外 | **P1** | **部分不符**：CI 称"mypy 硬门禁"字面成立，但真实覆盖面 ≈76%；`BASELINE.yaml:14`"mypy 119 源文件 0 错误"在此配置下语义弱于读者预期 |
| A8 | mypy 热点文件 | AST 统计（同 A7 脚本，按文件） | 标注率最低：`src/api/api_manager.py` **14.0%（6/43）**、`src/datasets/dataset_loader.py` 23.3%、`src/agents/executor_repo.py` 24.0%、`src/graph/event_bus.py` 36.8%、`src/agents/debugger.py` 37.5%。即**多模型路由核心 1112 行里 86% 的函数不在类型门禁内** | P1 | 不符（"类型检查覆盖"的直觉预期） |
| A9 | pre-commit 与 CI 口径差 | `.pre-commit-config.yaml:29-30`（`--ignore-missing-imports --no-strict-optional`，`exclude: ^tests/`）vs `ci.yml:178`（`python -m mypy src/ config.py`，默认 `strict_optional=True`） | 本地 hook 显式关掉 Optional 严格性且只跑改动文件 → **本地绿 ≠ CI 绿**（两层不同口径） | P2 | 与"三方版本/口径一致守卫"（`check_tool_versions.py`）的意图不完全一致（版本一致，参数不一致） |
| A10 | type:ignore / noqa 存量 | `grep` 全 src | `# type: ignore` 43 处（`attr-defined` 24、`arg-type` 8、`import-not-found` 3…）；`noqa` 42 处（`F401` 21、`T201` 5）。`PGH003`（blanket ignore）已从全局 ignore 移除（`pyproject.toml:188-191`） | P2 | 一致（存量有据、非 blanket 泛滥） |
| A11 | ruff 规则集与豁免 | `pyproject.toml:118-210` | `select` 33 条规则族（含 `S`/`A`/`PL`/`TRY`/`T20`）；`ignore` 21 条，逐条给理由；`per-file-ignores` 对 `tests/**`(24 条)、`experiments/**`、`scripts/**` 大范围豁免，`src/` **不豁免**（仅 CLI 报表文件 `# ruff: noqa: T201`） | P2 | 一致（豁免面在非产品目录） |
| A12 | "ruff 全绿"的成立条件 | 实测 `.venv/bin/ruff check .` | `src/`+`experiments/`+`scripts/`+`tests/`+`config.py` **全部 clean**；但 `ruff check .`（= `Makefile:19` 的 `make lint`）在**当前工作树报 417 errors**，全部来自未跟踪目录 `audit_2026/`(259) 与 `_independent_audit/`(158)——这两个目录**不在** `extend-exclude`（`pyproject.toml:116` 只排除 `tmp_apr_baseline`/`experiments/results`/`review_2026`） | P2 | 条件成立：clean checkout 下为真；但"跑 `make lint` 全绿"的本地体验与 `BASELINE.yaml:14` 的"ruff 全绿"陈述在脏树上会冲突（口径未写清） |
| A13 | 大文件可维护性 | `wc -l`/字节实测 | `experiments/run_benchmark.py` **3401 行 / 176,620 B**；`src/datasets/synthetic_dataset.py` 2532 行；`src/graph/nodes.py` **2210 行 / 128,405 B**；`experiments/statistical_analysis.py` 2026 行 / 97,026 B；`experiments/mutation_testing.py` 1458 行。全仓 Python 166,807 行 | **P1** | 部分不符：`nodes.py` 号称多轮拆分（新增 `flags.py`/`trace_reward.py`/`patch_io.py` 等）后仍 2210 行；单文件万行级实验脚本使改动面不可控（无复杂度门禁，`pyproject.toml:149-153` 明确说明 C901 已被删除） |
| A14 | 测试规模与跳过面 | `ls tests/*.py \| wc -l`、`grep` 统计 | 266 个测试文件；`assert` 语句 9312 条；`skipif/importorskip/pytest.skip` 共 20 处（`hypothesis` 2 处、`matplotlib` 3 处、无 LLM 配置 3 处、docker 环境 1 处…）。`pytest` addopts 含 `--timeout=1200 --strict-markers`（`pyproject.toml:264-276`），无 `-m` 分层过滤 | P2 | 一致 |
| A15 | 测试与实现的耦合（抽样 9 文件） | `tests/conftest.py:39-70`；`tests/test_workflow_extended.py:29-36`；`tests/test_executor.py:195-216`；`tests/test_spec_oracle_metrics.py:70,128-131`；`tests/test_branch_coverage_gates.py:70-75`；`tests/test_cost_aware_routing.py:45`；`tests/test_smoke_llm.py:1-35`；`tests/test_property_invariants.py:24`；`tests/test_rag_metrics.py:25` | 见下方"A15 抽样明细"。总体：**未发现**"用实现自身计算期望值导致回归不可见"的普遍现象（`EXPECTED_COMPILABLE` 为硬编码字面量表）；主要问题是**LLM 边界全 mock**（`patch("src.*")` 386 处 / 115 文件；`_call_llm` 相关 patch 169 处；`build_workflow/graph.invoke` 仅 35 处）→ 端到端行为只由真实批次验证 | P2 | 一致（无夸大），但"多智能体"行为在测试层几乎只能验 mock 交互 |
| A16 | 安全：危险原语实际点位 | grep 实测 | `shell=True`：**0 处**；`pickle.`：**0 处**；裸 `eval(`：**0 处**；`exec(compile(...))`：`src/agents/runtime_probe.py:251`（**子进程内**执行 LLM 生成代码，探针语义，已从"主进程子线程"改为 subprocess）；`ast.literal_eval`：3 处（`spec_ir_v2.py:547`、`spec_smt.py:507`、脚本） | P2 | 一致（`pyproject.toml:164` 的 S102 ignore 说明与实现相符） |
| A17 | 安全：LLM 生成代码的隔离强度 | `src/agents/executor_modes.py:113-160`（默认 venv 路径）、`src/agents/executor.py:168-186`（env 白名单 PATH/HOME/LANG/LC_ALL/PYTHONPATH，第 182 行）、`src/agents/kernel_sandbox.py:68-70`（开关默认 false）、`src/agents/executor.py:222-266`（fail-closed 分支）；实机探针输出 | 默认执行 = **venv + 临时目录 + 环境变量白名单**，`use_docker=False`、`KERNEL_SANDBOX_ENABLE=false`（工件 `provenance.harness.execution_isolation` 三键亦可证）。**实机探针（macOS）**：`build_sandbox_command` 生成 Seatbelt profile（`(deny default)` + 路径白名单 + 断网 + `deny file-read* .env/.ssh/.aws`），`obs.supported=True` —— 即"内核级隔离能力真实存在但默认关闭"。因此默认链路**不是**安全沙箱：LLM 生成测试以当前用户身份裸跑，文件系统/网络无约束 | **P1** | **部分不符**：把 venv 链路称作"sandbox"在文档/日志层易被读作安全隔离；真正的隔离（Seatbelt/bwrap/Docker）均需显式开关 |
| A18 | 安全：凭证与 `.env` | `git log --all -- .env`（空）、`git ls-files \| grep -c '^\.env$'`=0、`src/utils/credential_scrub.py:23-31`（白名单默认 true）、src 内 `sk-...` 硬编码扫描（0 命中） | `.env` **从未被 git 跟踪**（历史与索引均无）；无硬编码密钥；执行链路经 `scrub_os_environ()` 动态剔除 + 可选最小白名单 | P2 | 一致 |
| A19 | 安全：变体执行路径未脱敏（新发现） | `experiments/mutation_testing.py:1239`：`env={**os.environ, "PYTHONPATH": tmpdir}` | 变异体 pytest 子进程继承**完整** `os.environ`（含 `LLM_*_API_KEY`/`OPENAI_API_KEY`），与 executor 三条链路的脱敏/白名单口径不一致；被测变异体由 AST 自动生成（非 LLM），但同一进程环境里有真实凭证 | P2 | 与 `credential_scrub` 自述"三条执行链路共用本函数，保持脱敏口径单一实现"（`credential_scrub.py:13-14`）**不符**：变异测试链路是第四条执行链路，未接入 |
| A20 | 可复现性：种子与采样 | `experiments/run_main_batch.py:50-56`（默认 seed=42/task-count=50）、`src/datasets/synthetic_dataset.py:2392`（`random.Random(self._seed)`）、`experiments/run_benchmark.py`（`TEMPERATURE=0.0` 三处级联，见 `run_main_batch.py:82-88`）、`src/api/api_manager.py:241`（`random.choices` 无种子） | 数据集/批次种子固定；温度强制 0.0；仅负载均衡的加权随机无种子（非实验语义） | P2 | 一致 |
| A21 | 可复现性：配置快照缺口 | `experiments/run_benchmark.py:2983-3120`（~150 键 env_snapshot）、`experiments/run_benchmark.py:3334,3396`（`max_pattern_repeat` 透传）；**实测**：`provenance` 键集合 = `['cache_enabled','cache_isolate_model','cache_namespace','env_snapshot','git_dirty','git_sha','harness','max_iterations','model_name','per_task_token_caps','profile','seed','temperature','valid_apis']`，全 JSON 中 `max_pattern_repeat` 字符串**不存在** | 影响"合成数据集同池模板重复上限"的干预**无法从工件证明是否生效**——而这正是项目自述的最高优先审计缺口类型（同文件注释把"干预不入 provenance ⇒ 生效性不可审计"列为"已发生 3 次的事故类"） | **P1** | **不符**（自订纪律 vs 实现） |
| A22 | 可复现性：Docker / reproduce.sh | `Dockerfile:6,23-24`（`python:3.12-slim` + `pip install -r requirements.txt`）、`reproduce.sh:23`（`set -euo pipefail`）、`reproduce.sh:116-131`（venv 构建）、`reproduce.sh:171-176`（先跑全量 pytest，失败即 abort）、`reproduce.sh:232`（run_benchmark） | 静态可执行性成立：严格模式 + 前置全量测试 + 依赖钉版；Docker 用 `requirements.txt`（全 `==`，与 lock 等价）而非 lock。**未实际执行**（会触发真实 LLM） | P2 | 一致（未端到端实测，见 §E） |
| A23 | 可复现性/独立性：同 seed 批次工件逐字节相同 | 工件 `experiments/results/main_batch/benchmark_synthetic_20261007_161053.json` 与 `..._20261007_181638.json`（`git_sha` 分别为 `d3c3cc4…` 与 `1a5a5a7…`，同 `seed=42`、同 `cache_namespace="seed42"`、同 profile=logic）；自查脚本比对 | 3 臂 × 87 任务的 `generated_test` **87/87 逐字节相同**，`patch` 78–87/87 相同，`detection_rate`/`coverage` 87/87 相同；但 `token_usage.total_tokens` 差异巨大（aitester 588,100 vs 91,570） | **P0**（统计独立性/记账可信度） | 不符：同 seed 复跑被设计为"可复现性特性"（`src/agents/base_agent.py:381-397`），但若把两份工件当独立重复入池（`--pool-seeds` 语义）即伪重复；且 token 记账在同一响应下不可复现 |
| A24 | 可复现性/记账：基线臂 token 全 0 | 工件 `benchmark_synthetic_20261007_161053.json` / `170147` / `181638` / `185941`（4 份 logic 档批次）：`plain_llm`、`plain_llm_df` 两臂 87/87 行 `token_usage` 的 `input/output/total/llm_calls/cache_hits/cache_avoided_tokens` **全为 0**；对比 `benchmark_synthetic_20261006_140906.json`（无 profile）同臂有 `llm_calls=96/87`。记账入口 `src/budget/token_usage.py:107-135`（`record_usage` 累加 `llm_calls`）、缓存命中记账 `src/agents/base_agent.py:404-415,453-460`（两条命中路径均调 `record_cache_hit_usage` → `cache_hits>0`） | 这些行既无真实调用计数、也无缓存命中计数，但 `generated_test` 非空且与另一批次逐字节相同 → **该批次基线臂的 token/成本不可用**，$/task 类结论在这些工件上不可计算。机制未在静态阅读中唯一确定（见 §E） | **P0** | 不符（E6/成本口径声称可测） |

### A15 抽样明细（≥8 个测试文件）

| 文件 | 我读到的写法 | 判断 |
|---|---|---|
| `tests/conftest.py:39-70` | autouse fixture 关缓存 + `patch(get_first_valid_model_name→None)` | 合理隔离；副作用是"缓存命中路径"默认永不被测（需显式 opt-in）→ 覆盖率口径外的盲区 P2 |
| `tests/test_workflow_extended.py:29-36` | `assert hasattr(mod,"RAG_MODULE_AVAILABLE")`，随后 `if not AVAILABLE:` 才断言 → chromadb 已安装时**零有效断言** | **断言过弱**（P2，真实样本） |
| `tests/test_executor.py:195-216` | `parse_coverage` 仅 3 例（正常/无匹配/多行），`test_parse_coverage_no_match` 把"未测量→0.0"钉死 | 覆盖 happy path；**指标二义性（0% vs 未测）被测试固化**而非暴露（P2，与 §B9 交叉） |
| `tests/test_spec_oracle_metrics.py:70,128-131` | 硬编码 `EXPECTED_COMPILABLE=[F,F,F,F,T,T,T,T]` 与实现判定逐条对比；另有"两通道判定一致"双向断言 | **正面例**：能发现回归，非同源自证 |
| `tests/test_branch_coverage_gates.py:70-75` | 与 `scripts/gates/check_branch_coverage.py` 的常量对齐守卫 | 防漂移有效，但两边同时改错不会发现（P2） |
| `tests/test_cost_aware_routing.py:45` | `cfg.cost_alert_threshold == _COST_ALERT_THRESHOLD`（常量从实现导入） | 同源自证（P2）；`test_config_defaults` 其余断言尚可 |
| `tests/test_smoke_llm.py:1-35` | 只测开关语义与 `_check_response` 纯函数；默认不发真实调用 | 与"零成本"口径一致（P2） |
| `tests/test_property_invariants.py:24`、`tests/test_ak_batch.py:160` | `pytest.importorskip("hypothesis")` → 整个文件跳过 | CI 已装 hypothesis（`requirements.txt`），可接受；本地缺装即静默整文件跳过（P2） |
| `tests/test_patch_test_hacking.py:1-166`、`tests/test_batch_viii.py:29-42` | 三信号正向/负向用例 | 覆盖检测核本身；**不测绕过构造**（见 §B10） |

---

## §B 领域专项诊断表

| # | 专项 | 证据（file:line） | 现状（我核实的事实） | 严重度 | 与声称是否不符 |
|---|---|---|---|---|---|
| B1 | 逻辑驱动：支持哪些逻辑片段 | `src/specs/spec_smt.py:322-388`（`_translate`：Constant/Name/BoolOp/UnaryOp/Compare/BinOp，**无 Call/Subscript/Attribute/量词/蕴涵**）、`spec_smt.py:459-557`（`Solver`+`Optimize` 产输入见证）、`spec_smt.py:559-583`（前件空洞 UNSAT）、`spec_smt.py:654-690`（后件自洽 UNSAT）、`spec_smt.py:600-601`（自述"**不**判定实现是否满足后件"） | 实际逻辑片段 = **无量化的整数/实数/布尔约束系统**（比较 + 布尔 + 算术：`+ - * / // % **`），**没有**：蕴涵（`implies` 不在白名单）、函数调用、数组/序列/字符串、量词、时序、不变量归纳证明。能力范围 = 前件可满足性/空洞检测、后件自洽性检测、边界见证生成。**不含**"代码是否满足规约"的验证 | P1 | 部分不符：若对外表述为"形式化验证/逻辑驱动保证正确性"则过强；模块自身 docstring 是诚实的（明确不做实现级验证） |
| B2 | 逻辑驱动：是否真接 z3 | `src/specs/spec_smt.py:63-71`（`smt_available`）、`spec_smt.py:473,525-547`（`import z3`、`z3.Solver()`、`z3.Optimize()`、`solver.check()==z3.sat`）、`spec_smt.py:571-581`；实测 | **真接 z3**（不是自研轻量求值）：实机 `smt_available()` 为真，代码路径确有 `Solver.check()` / `Optimize.check()` / 模型抽取 + Python 语义复核（`spec_smt.py:495-497`）。CI 另有 fail-closed 断言（`ci.yml:196-206`） | P2 | 一致（这条推翻了"假 SMT"的怀疑） |
| B3 | 逻辑驱动：spec_compile_rate 低至 0.21 的代码层根因 | `src/specs/spec_ir_v2.py:686-719`（`compile_readiness`）、`spec_ir_v2.py:267-304`（`_clause_is_compilable` 四门）、`spec_ir_v2.py:92-124`（形态门：字符白名单 + ≤200 字符（`is_expression_clause` 第 106 行）+ `ast.parse(mode="eval")`）、`spec_ir_v2.py:63-69`（调用/属性白名单）、`spec_ir_v2.py:295-299`（标识符绑定门）、`spec_ir_v2.py:644-665`（通道选择：expr 通道优先，否则 NL 通道）、`src/agents/planner.py:196-199`、`src/prompts/templates.py:31-35` | 分子分母定义即"通过白名单的子句数 / 非空子句数"，且判定函数与注入通道**同一函数**（`spec_ir_v2.py:333`）。语言侧根因是三件事叠加：(1) 中文 NL 子句必然被字符门拒绝（恒 0）；(2) 200 字符上限与未知标识符门（签名未对齐时 `{r,x,a,b,y}` 之外的参数名全部拒绝）；(3) 通过编译门的调用类/下标类子句（`len(xs)>0`、`isinstance(x,int)`、`xs[0]>0`）在 SMT 层全部 `_Untranslatable`（`_translate` 无 Call/Subscript 分支）→ 形式化通道实际可用面比 compile_rate 更窄 | **P1** | 部分不符：`compile_readiness` 是"**编译器自身的接受率**"，不是"逻辑推理能力"的可证伪内核；指标升降无法区分"LLM 不会写形式规约"与"编译器太严"，因此以它为 H1 判据时不可归因 |
| B4 | 逻辑驱动：去裸 eval 后的受限求值器安全性 | `src/specs/spec_smt.py:125-198`（`_safe_eval`）、`spec_smt.py:99-118`（`_BINOP_FUNCS` 含 `Pow`/`FloorDiv`）、`spec_smt.py:52-55`（`_EVAL_SAFE_FUNCS`）；**实测探针** | 结构上安全：不注入 `__builtins__`，Name 仅查 `env`，拒绝 Attribute/Subscript/Lambda/推导式/f-string，Call 仅限 11 个纯函数白名单。两处瑕疵：(a) 注释 `spec_smt.py:50-51` 声称与 `spec_ir_v2._ALLOWED_CALL_NAMES` "同一集合"，**实测缺 `isinstance`**（`ALLOWED` 12 个 vs `EVAL_SAFE` 11 个）——当前因 `_translate` 不支持 Call 而未产生行为偏差，属注释失真；(b) 支持 `**` 且无规模/时间上限，≤200 字符足以构造巨整数运算（`9**9**9`）→ 复核阶段可被退化子句拖死 | P2 | 部分不符（注释失真 + DoS 面）；"去裸 eval"本身成立 |
| B5 | 逻辑驱动：CEGIR 反例精化闭环是否接入 | `src/specs/spec_refine.py:1-28`（自述"**不接入主链路**，调用点接入属后续批次"）；全仓 grep `spec_refine/refine_spec/CEGIR` 于 `src/`+`experiments/` **零引用**（仅 `tests/test_spec_refine.py:20-21` 引用）；对照 `README.md:59`（头条称"逻辑驱动反例精化闭环"）与 `README.md:1376`（自述"未接入主链路"） | CEGIR 是**孤立能力**：没有任何生产调用点；主链路的规约矛盾检测（`check_spec_consistency`）也无消费方（`spec_smt.py:693-709` 仅被 `spec_refine` 调用） | **P1** | **不符**（头条级"闭环"vs 零接线；README 另一处已自述，属表述不一致而非隐瞒） |
| B6 | 多智能体：角色与通信机制 | `src/graph/workflow.py:429`（`StateGraph(AITesterState)`）、`workflow.py:434-561`（节点/边：planner→generator→executor→diagnosis?→debugger→patch_applier→executor）、`src/graph/state.py:1-100+`（单一 TypedDict 共享状态） | 角色是 8 个**普通 Python 函数节点**；节点间**无消息传递**，全部经共享 state 通道；并发只出现在两处：专家池线程池（`expert_pool.py:335-372`）与批处理 worker 线程 | P2 | 部分不符：若表述为"多 Agent 协商/通信"，实现层是"单状态机 + 多角色提示 + 共享状态" |
| B7 | 多智能体：专家池是否真"辩论收敛" | `src/graph/expert_pool.py:58-62`（只有 **3** 个维度）、`expert_pool.py:106-114`（`_take_n` 维度不足时**循环复用**）、`expert_pool.py:269-293`（每个"专家"= 同一 `DebuggerAgent.debug` + 在 `target_code` 尾部追加维度提示）、`expert_pool.py:306`（置信度=常量 `_EXPERT_BASE_CONFIDENCE=0.5`）、`expert_pool.py:423-430`（投票后置信度=0.5+0.1×验证数+0.05×(补丁≥200 字符)-0.1(含 TODO)）、`expert_pool.py:535-543`（"同意"= 归一化文本完全相等或被包含）、`expert_pool.py:436-532`（debate=**一次** LLM 综合调用，修订候选直接置首位、绕过投票）、`expert_pool.py:122-125`（温度/置信度常量）；接线于 `src/graph/debugger.py:508-630`（`EXPERT_POOL_ENABLE` 默认 false，`expert_pool.py:128-130`） | "N 个专家" = N 次同构 LLM 调用（同模型、同基础 prompt、同温度 0.3、仅尾部提示不同；N>3 时维度重复）；"共识"= 文本包含关系的多数票；"置信度"部分由**补丁长度**驱动（长度启发式而非质量信号）；"辩论收敛"= 单轮综合调用，无收敛判据、无轮次迭代 | **P1** | **不符**（"辩论收敛"在实现上是 1 次 prompt 综合 + 启发式打分） |
| B8 | 多智能体：预算与停止条件 | `config.py:369`（`MAX_ITERATIONS=3`）、`src/graph/workflow.py:224`（`_MAX_REGENERATIONS`）、`workflow.py:126-186`（`determine_stop_reason` 七类原因）、`workflow.py:600-651`（覆盖率停滞检测）、`workflow.py:883-889`（显式 `recursion_limit=4*MAX_ITERATIONS+8`）、`src/budget/cost_budget.py:46-47`（`COST_BUDGET_ENABLE` 默认 **false**）；工件 `provenance.harness.retry_stop_rules.cost_budget_enabled=False` | 生效的停止条件：`test_passed` / 迭代 3 轮 / 再生成上限 / 停滞 / 回归 / 预算（默认关）。任务级 token cap 仅当显式传 `--per-task-token-caps`（`run_main_batch.py:96-114`）时注入 | P2 | 一致（预算能力存在但默认不在实验口径内） |
| B9 | 测试生成/变异测试：自研可信度 | `experiments/mutation_testing.py:1-30`（自述内置轻量变异器，`mutmut` 仅可选兜底；全仓无 `mutmut` 依赖）、`mutation_testing.py:214-302`（生成器）、`mutation_testing.py:891`（`max_per_task=120`）、`mutation_testing.py:1259`（`max_mutants=10`）、`mutation_testing.py:1315-1322`（`seed=None` → 取**前 10 个** AST 顺序变异体） | 变异测试完全自研（无第三方变异器），仅 3 类轻量变异 + 5 类扩展；默认只跑 10/120 个且缺省按生成顺序截断（同质偏差，注释自认） | P1 | 部分不符（若称"变异测试"为完整口径） |
| B10 | 测试生成/变异测试：杀死判定 | `mutation_testing.py:1157-1252`（`_run_mutant_tests`）、`:1246-1249`（**仅 rc==1 判杀**；rc=0 判存活；rc≥2/超时判存活）、`:1324-1335`（原始缺陷代码作基线，`pre_existing_failures` 只记不裁决）、`:1343`（`score=killed/len(selected)`）、`:1429-1458`（聚合只看 `mutation_score`，忽略 `pre_existing_failures`） | 杀死的语义是"**测试在变异体上失败**"；而被测原码**本身带缺陷、测试本就应当失败**（检出任务的定义），因此大量变异体"被杀"与"仍能检出原缺陷"不可区分 → 得分偏向饱和/混淆；`pre_existing_failures=1`（测试在原始缺陷上全过）时得分仍照算并入均值 | **P1** | 部分不符（变异得分被当作测试强度的独立证据时不可靠） |
| B11 | 覆盖率：pytest-cov 还是正则 | `src/agents/executor.py:190-200`（`--cov={target_dir} --cov-report=term`，**无** `--cov-branch`）、`executor.py:284`（`self._parse_coverage(output)`）、`src/agents/executor_output.py:20`（`_RE_COVERAGE_TOTAL = re.compile(r"TOTAL\s+.+?(\d+)%")`）、`executor_output.py:38-66`（`startswith("TOTAL")` 优先、无则退化为**全文扫描**、再失败返回 `0.0`）；**实测探针** | 覆盖率数字由 pytest-cov 产生，但**取数靠正则解析 stdout 文本**。实测脆弱点：`"TOTAL 50 5 1% 99%"` → 返回 **1.0**（非贪婪取第一个百分数）；`"TOTAL 12 3 -"`（无语句）→ 0.0；无 TOTAL 行 → 0.0，与"真实 0% 覆盖"**不可区分**（`tests/test_executor.py:201-205` 把该二义性固化为期望行为）。另：实验口径为**行覆盖**，CI 自测为 `--cov-branch`（`ci.yml:316`），两处"覆盖率"含义不同 | **P1** | 部分不符（"覆盖率来自 pytest-cov"表面成立，但指标是文本解析产物；fail-silent 的 0.0 会直接污染 avg_coverage 类头条数字） |
| B12 | 自修复：闭环是否真实 | 触发：`src/graph/workflow.py:653-820`（`_should_debug` 路由）；应用：`src/tools/patch_applier.py`（安全守卫）；验证/回滚：`src/tools/patch_rollback.py:147-226,240-331` + `src/graph/nodes.py:2041-2060`；观测：`src/tools/oracle_validator.py`（`nodes.py:980`）、`src/tools/patch_validate.py:36-96`（自述观测层）、`src/tools/self_repair_trap.py:11-19`（自述"刻意不做阻断"）、`src/agents/fl_spectral.py` | "触发→应用→验证→回滚"链路**存在**（`PATCH_SNAPSHOT_ROLLBACK_ENABLE` 在 logic 档开启，`config.py:73`），回滚同时恢复 state 与磁盘。但"验证"依据是**本流程自己生成的测试**；`patch_validate`（`patch_validate.py:36-49`）与 `self_repair_trap`（`self_repair_trap.py:11-19`）自述观测层不改行为，而 `fl_spectral` **不属观测层**：它渲染定位先验段落注入 Debugger 的补丁生成 prompt（`src/graph/debugger.py:438-441` `query += "\n\n" + fl_spectral_section`） | P1 | 部分不符（"自修复闭环"含验证环节，但验证 oracle 与生成 oracle 同源，不能作为独立正确性证据；另见 C20） |
| B13 | 自修复："P2P 全量回归"的真实范围 | `src/tools/patch_rollback.py:1-20`（自称"P2P 全量回归裁决"）、`:154-176`（`test_code` 空 → `no_oracle`）、`:187-217`（子进程只跑传入的**单个测试文件**）；调用点 `src/graph/nodes.py:2044-2049`（`test_code=state.get("generated_test")`） | 实际执行 = **把 LLM 生成的测试文件在临时目录里对补丁后代码重跑一遍**；不是项目既有测试套件的全量回归，也不含 P2P 用例集合 | **P1** | **不符**（"全量回归"措辞与实现范围不一致） |
| B14 | 自修复：fail-closed 下正确补丁被误杀 | `src/tools/patch_rollback.py:165-168`（fail_closed 语义）、`:198-213`（超时/rc≥2/"no tests were run" 一律改判 `regression_failed`）、`:216-217`（rc==1 即回滚）；`config.py:74-76`（logic 档 `PATCH_ROLLBACK_FAIL_CLOSED=true`） | logic 档下"回归无法裁决 = 回滚"：只要生成测试自身有瑕疵（收集错误/超时/断言过严），补丁就被回滚。而生成测试有瑕疵是本项目自认的常态（`test_error_rate` 为受监控指标）→ 正确补丁可被系统性回滚，`repair` 类指标被该机制压低 | **P1** | 部分不符（该策略被表述为"保守安全"，实际把生成 oracle 的错误转嫁为修复失败） |
| B15 | test-hacking 守卫：能否绕过 | `src/tools/patch_test_hacking.py:106-145`（判定核）、`:81-85`（硬编码分支要求 `body` 恰为 1 条 `return 常量`）、`:96-103`（吞异常体恰为 `pass`/`return 常量`）、`:140-141`（`assert` **计数**减少才报警）、`:20-27`（自述"观测层…主终点/passed 零变化"）；接线 `experiments/run_benchmark.py:739-763`（仅写结果行）、`run_benchmark.py:1284` | 该核**不阻断任何补丁**（ADR 观测层），且判定是可轻易绕过的形态匹配。可构造的绕过（均基于上述代码分支）：① `if x == 5:` 体内多写一条语句（`_: None`）→ `len(body)==1` 不成立；② 用 `d.get(x, default)`/`x if x in MAP` 之类映射后门替代 `If`；③ 删除 1 条真实 `assert` 后补一条 `assert True` → 计数相等，不报 `assert_weakened`；④ `except Exception: logger.debug(...)` 或 `return DEFAULT_NAME`（非常量）→ 不报 `exception_swallow_added`；⑤ 在**测试侧**弱化（该核只比较被测代码原/新，不审生成测试） | **P1** | **不符**（"守卫"字面义 vs 观测层 + 形态匹配；`README.md:62` 称"test-hacking 守卫"） |
| B16 | 评估公平性：三臂定义 | `experiments/run_benchmark.py:5-8`（docstring 称 plain_llm "仅一次调用"）、`:217-239`（实测实现：`build_workflow(planner=False, debugger=False)` → **仍是完整 LangGraph 管线**，只移除 planner/debugger）、`:381-419`（`plain_llm_df` = 同裁剪 + 线程级 `detection_first` 覆盖）、`:423-429`（注册表）、`:242-378`（`single_agent` 才是一次调用 + 一轮修复） | `plain_llm` **并非**"单次 LLM 调用"，而是与 aitester 共用同一图与节点实现的裁剪版（对基线有利，设计上公平）；但模块 docstring 与实现的描述不一致（代码内注释 `:226-230` 已澄清） | P2 | 部分不符（文档层措辞） |
| B17 | 评估公平性：预算/轮次是否可比 | `experiments/run_main_batch.py:96-114`（`--per-task-token-caps` 默认 None）、`run_benchmark.py:1621-1648`（cap 解析）、工件 `provenance.per_task_token_caps=None`（4 份 logic 档批次实测）；`config.py:369`（aitester 侧迭代 3 轮 + 再生成）；`workflow.py:224` | **头条批次（2026-10-07 logic 档）三臂预算未匹配**：aitester 有 planner + 最多 3 轮修复 + 最多 2 次再生成；`plain_llm` 无修复；`plain_llm_df` 无修复但可再生成。cap 机制存在（E6 专用），standard 臂不启用 | **P1** | 部分不符：若头条结论取自 standard 臂，则"预算可比"不成立（项目另有 E6 matched-cap 臂，但不在 main_batch 这批工件里） |
| B18 | 评估公平性：三臂 token 不可比 | 同 A24（工件实测）；`token_usage` 读取点 `run_benchmark.py:1097,1331` | logic 档四批中 plain_llm/plain_llm_df 两臂 token 与调用数**全 0** → 三臂成本/效率对比在这些工件上不可计算 | **P0** | 不符（E6/$per-task 声称可测） |
| B19 | 评估公平性：数据集与实现同源（自我评测） | `src/datasets/synthetic_dataset.py:36-56` 等模板（每个模板同时含 `template`(buggy) / `fixed`(gold) / `test_cases`(gold 测试)）、`:2401`（`noise=rng.randint(0,9999)`）、`:2482`（`instance_code = template + "\n# noise_seed={noise}"`）、`:2500-2509`（gold 材料入 `metadata`，供 M1 独立裁决）；**实测**：`BUG_PATTERNS=16`；`SyntheticDataset(task_count=87, seed=42)` → 去掉 `# noise_seed=` 注释后**只有 26 个不同代码体**，最大重复 9 次 | 合成数据集由本仓 16 个模板生成，缺陷/gold/裁决测试**同一处编写**；"噪声"只是行尾注释，seed 不改变缺陷语义。因此 87 任务的**有效独立样本 ≈26**；以 87 为 n 的显著性检验会把簇内重复当独立观测（伪重复） | **P0**（评估效力） | 不符（若以"87 任务 n≥50 主批次"表述独立性）；项目另有 cluster-robust 敏感性分析（`config.py` AC4 批次描述），但数据集的簇结构需显式披露 |
| B20 | 评估公平性：提示/模型/温度可比性 | 工件 `provenance.model_name="deepseek-flash"`、`temperature=0.0`、`seed`、`cache_namespace="seed42"`；`run_benchmark.py:1860-1863`（三基线同 slot 走同一 API 槽，注释自述"消除模型混淆"） | 模型/温度/seed/API 槽位在三臂间一致（这三条**可比**成立）；差异集中在预算与协议 | P2 | 一致（正面证据） |
| B21 | 污染检测方法学 | `experiments/contamination_check.py:84-102`（token Jaccard）、`:196-210`（AST 语句骨架 LCS）、`:213-260`（词袋余弦）、`:299-377`（组合规则：`structural` 需佐证才升级）、`:105-118`（阈值 0.85/0.6） | 三个通道度量的都是"**生成补丁 vs 官方 gold patch 的输出相似度**"。它无法区分"模型记忆训练数据"与"模型独立得出同一最小修复"——对 1–3 行的最小修复（QuixBugs/合成模板的主要形态），正确答案与 gold 天然高度一致，会把**正确性**判成污染；对"背出后改写为等价形式"又无判别力。模块内**没有**任何训练集成员推断、时间切分或"无上下文复现"探针（grep 未见） | **P1** | 部分不符（作为"训练集污染判定"证据时效力被高估；模块自身对 `structural` 假阳性有自述，但识别性问题未被处理） |

---

## §C "声称 vs 实现"差异清单（核心）

按严重度排序。每条给出**声称出处**与**代码反证**；声称文本只作引用，不代表我认可。

| # | 严重度 | 声称（出处） | 代码反证（file:line） | 我的判定 |
|---|---|---|---|---|
| C1 | **P0** | "逻辑驱动反例精化**闭环**（`spec_refine.py` CEGIR——规约矛盾反例回灌 LLM 只改契约 + SMT 复验预算化迭代）" —— `README.md:59` | 全仓 `src/`+`experiments/` 对 `spec_refine`/`refine_spec_with_counterexample`/`CEGIR` **零引用**；模块自述"本模块是**独立可调用能力**…**不接入主链路**（Planner/Generator 调用点的接入属后续批次）" `src/specs/spec_refine.py:22-24`；唯一入口 `check_spec_consistency` 也只被该模块调用（`spec_smt.py:693-709`） | 头条"闭环"与实现不符：能力存在但无消费方。`README.md:1376` 已自述"未接入主链路"，两处表述互相矛盾 |
| C2 | **P0** | "**87 任务**主批次 / n≥50 独立样本"（`experiments/run_main_batch.py:1-20`、`:50-56`） | `BUG_PATTERNS` 实测 **16** 个；同一 seed=42 生成 87 任务，去掉 `# noise_seed=` 注释后仅 **26** 个不同代码体，最大重复 9 次；噪声仅行尾注释（`synthetic_dataset.py:2401,2482`） | 任务的独立性远低于 n=87 的表观值；簇内伪重复会夸大显著性 |
| C3 | **P0** | 三臂成本/效率可对比（结果行 `token_usage`、E6 $/task 口径） | 4 份 logic 档批次工件中 `plain_llm`/`plain_llm_df` 的 `token_usage` 全部字段为 0（含 `llm_calls` 与 `cache_hits`），而 `generated_test` 非空；记账入口确在 `src/budget/token_usage.py:107-135` 与 `base_agent.py:404-415,453-460` | 这些批次的成本结论不可计算；记账链路存在未覆盖分支（机制见 §E） |
| C4 | **P0** | 同 seed 复跑 = "可复现性特性"（`src/agents/base_agent.py:381-397` 注释：同 seed 复跑共享缓存） | 两份同 seed=42、同 namespace 的批次（`git_sha` 不同）中 3 臂 × 87 任务 `generated_test` **逐字节相同**、`detection_rate`/`coverage` 全同，但 `total_tokens` 588,100 vs 91,570 | 若两批入池统计，"独立重复"不成立；同时暴露记账不可复现 |
| C5 | **P1** | "**P2P 全量回归**…应用后 P2P 全量回归 → 失败自动回滚"（`src/tools/patch_rollback.py:1-20,154`） | 实际只跑调用方传入的**单个**测试文件即 `state["generated_test"]`（`src/graph/nodes.py:2044-2049`）；子进程命令为 `pytest test_path -q`（`patch_rollback.py:189`） | "全量回归"名不副实：它是"重跑自己生成的测试"，不是既有测试套件回归 |
| C6 | **P1** | 验证/回滚构成独立正确性门（`PATCH_SNAPSHOT_ROLLBACK_ENABLE` + `PATCH_ROLLBACK_FAIL_CLOSED=true`，`config.py:73-76`） | 验证 oracle 与生成 oracle 同源（同一个 `generated_test`）；fail-closed 下 rc≥2/超时/无测试一律回滚（`patch_rollback.py:198-213`） | 验证不能独立于 LLM 生成物；坏测试会把正确修复判为回归失败并回滚 |
| C7 | **P1** | "**test-hacking 守卫**"（`README.md:62`） | 判定核自述为**观测层**（"命中即拒绝补丁"属"阻断档（待 A/B 后转正）"，`src/tools/patch_test_hacking.py:20-27`）；唯一调用点只写结果行（`experiments/run_benchmark.py:739-763,1284`）；判定已被形态约束（`patch_test_hacking.py:81-85,96-103,140-141`） | 是"检测信号"而非守卫；且 4 类平凡绕过（加一条语句 / 换映射后门 / 补 `assert True` / 吞异常体写非 Const）可规避，测试侧作弊完全不在其视野 |
| C8 | **P1** | "**多 Agent 辩论收敛**轮次…进一步收敛候选补丁"（`src/graph/expert_pool.py:436,444`） | `debate_round` 只做 **1 次** `DebuggerAgent.debug` 综合调用（`:505-513`），无迭代/无收敛判据；修订候选不参与投票即置首位（`:522-532`）；"专家"是同构调用的维度后缀变体（`:269-293`），`N>3` 时维度循环复用（`:106-114`） | 无真正的辩论/共识机制：一次 prompt 综合 + 文本包含式投票 + 长度启发式置信度 |
| C9 | **P1** | "mypy 硬门禁 / mypy **119 源文件 0 错误**"（`ci.yml:175-178`、`BASELINE.yaml:14`） | `pyproject.toml:232-256` 无 `[tool.mypy]` 严格开关；实测探针证明未标注函数体不被检查；AST 统计 src **1111** 函数中仅 **842（75.8%）** 完全标注，`api_manager.py` 仅 14% | 门禁真实但覆盖 ≈76%；"0 错误"是在该配置下的结论，不等于"类型安全"（含 1112 行路由核心基本未检查） |
| C10 | **P1** | "覆盖率来自 pytest-cov"（指标口径） | 取数实为 `re` 解析 stdout：`executor_output.py:20,38-66`；实测 `TOTAL 50 5 1% 99% → 1.0`；无 TOTAL 行 → `0.0` 与真实 0% 不可区分（并被 `tests/test_executor.py:201-205` 固化） | 指标为文本解析产物，存在静默污染通道（0.0 二义 + 首百分数陷阱） |
| C11 | **P1** | "变异得分"作为测试有效性指标 | 杀判据 `rc==1` 且被测原码本就带缺陷（`mutation_testing.py:1246-1249,1324-1335`）；`pre_existing_failures` 只记不裁决；聚合只看 score（`:1429-1458`）；默认 `max_mutants=10` 截断（`:1259,1322`） | 得分与"测试能否区分正确/缺陷实现"耦合不清，且采样同质；不宜作为独立强度证据 |
| C12 | **P1** | "干预开关必须入 provenance，否则生效性不可审计"（`experiments/run_benchmark.py:3050-3120` 注释，自述已发生 3 次同类事故） | `max_pattern_repeat` 由 CLI 传至数据集（`run_benchmark.py:3334,3396`），但**不在** `provenance`/`env_snapshot`；实测 4 份工件 JSON 中该字符串不存在 | 自己的最高优先纪律被自己违反 |
| C13 | **P1** | "合成数据集…主批次"（`run_main_batch.py:1-20`、`--dataset synthetic` 默认） | 模板内含 gold 与 gold 测试（`synthetic_dataset.py:36-56,2500-2509`）：bug/gold/oracle 同源编写 | 构成"自出题 + 自备标准答案"的自评测循环；跨数据集外推性未被约束 |
| C14 | **P1** | "污染检测（token Jaccard / AST LCS / 余弦）"用于判定训练集污染 | 三通道均为"生成补丁 vs gold patch"相似度（`contamination_check.py:84-102,196-210,213-260`），无成员推断/时间切分/无上下文探针 | 度量的是输出相似度，会把"独立得出同一最小修复"误判为污染 |
| C15 | **P1** | "沙箱执行"（executor 链路措辞） | 默认 `use_venv=True, use_docker=False, kernel_sandbox=False`（工件 `harness.execution_isolation`；开关 `kernel_sandbox.py:68-70`）；venv 路径为裸子进程（`executor_modes.py:113-160` 自述"却走裸子进程"） | 默认链路是依赖隔离 + 环境脱敏，不是安全隔离；真隔离需显式开关 |
| C16 | **P2** | "**纯 LLM 基线**：无 Planner、无修复循环，**仅一次调用**"（`run_benchmark.py:5-8,221`） | 实现为 `build_workflow(planner=False, debugger=False)`（`:238`）——仍是完整图；代码内注释 `:226-230` 已澄清"此前 plain_llm 跑的是完整管线" | 同文件 docstring 与实现/注释自相矛盾（描述性失真，非实验口径失真） |
| C17 | **P2** | `spec_smt` 注释："`_EVAL_SAFE_FUNCS` 与 `spec_ir_v2._ALLOWED_CALL_NAMES` **同一集合**"（`spec_smt.py:50-51`） | 实测 `ALLOWED` 含 `isinstance`（12 项），`EVAL_SAFE` 缺（11 项）；而 `isinstance(x,int)` 确实可通过编译门（实测 `_clause_is_compilable=True`） | 注释失真；当前被 `_translate` 不支持 Call 掩盖，一旦翻译层放宽即成为静默丢弃点 |
| C18 | **P2** | "ruff 全绿"（`BASELINE.yaml:14`） | 实测产品目录 clean，但 `ruff check .`（= `make lint`）在当前工作树 417 errors（`audit_2026/` 259 + `_independent_audit/` 158），两目录不在 `extend-exclude`（`pyproject.toml:116`） | 条件成立但口径未写明（未跟踪审查目录会污染本地"全绿"） |
| C19 | **P2** | "凭证脱敏…三条执行链路共用…避免名单漂移"（`credential_scrub.py:13-14`） | 第四条执行链路 `experiments/mutation_testing.py:1239` 传 `env={**os.environ, ...}`，未脱敏/未白名单 | 自述的"单一实现"被实验链路绕过 |
| C20 | **P1** | "FL 谱定位（Ochiai）…**纯测量开关，不改变生成/修复行为**；默认档零变化"（`config.py:106-112`，logic 档 `FL_SPECTRAL_ENABLE=true`） | `src/graph/debugger.py:268-281` 在 `agent.debug` 调用前测量 FL 焦点并渲染段落，`:438-441` 把该段落**拼进补丁生成 query**（`query += "\n\n" + fl_spectral_section`）→ 直接改变 LLM 修复输入与输出分布 | 与"纯测量、零行为影响"的注释直接矛盾；这同时是 logic 档与 default 档的**行为差异来源**，消融归因时必须计入 |

---

## §D 可立即验证的命令建议（不附输出，避免编造）

> 全部为**只读/短时**命令；涉及真实 LLM 的一律不建议自动执行。仓库自带的门禁脚本优先用 `.venv/bin/python` 以对齐 CI 依赖面。

**D1 静态质量（秒级）**
```bash
cd /Users/wangchenyu/Workspace/AITester
.venv/bin/ruff check src/ experiments/ scripts/ tests/ config.py   # 产品目录口径（预期 clean）
.venv/bin/ruff check .                                             # 与 Makefile:19 同口径；含未跟踪审查目录
.venv/bin/python -m mypy src/ config.py                            # CI 同口径（pyproject 为准）
.venv/bin/python -m mypy --strict src/specs/ 2>&1 | tail -20       # 对照：严格模式下的真实差距
.venv/bin/python -m mypy --config-file pyproject.toml -c $'def f(x):\n    return x + "a"\ndef g(x: int) -> int:\n    return x + "a"'  # 验证"未标注函数体不检查"
```

**D2 依赖与打包（秒级~分钟级，build 需网络）**
```bash
.venv/bin/python scripts/gates/check_lock_sync.py
.venv/bin/pip-audit -r requirements.txt            # 需 pip-audit 与 advisory DB 网络
.venv/bin/python -m build --wheel && ls -l dist/   # 需网络拉 build/setuptools
.venv/bin/python -c "import tomllib,pathlib;d=tomllib.loads(pathlib.Path('pyproject.toml').read_text());print(d['project']['optional-dependencies'].keys())"
```

**D3 门禁脚本（仓库自带，秒级）**
```bash
for g in check_env_snapshot_keys check_state_contract check_tool_versions check_bilingual_docs check_baseline check_baseline_numbers check_artifacts_tracked; do
  echo "== $g"; .venv/bin/python scripts/gates/$g.py 2>&1 | tail -3; done
```

**D4 测试（分层，避免全量长跑）**
```bash
.venv/bin/python -m pytest tests/test_executor.py -q                       # 我已实跑：41 passed / 0.20s
.venv/bin/python -m pytest tests/test_spec_oracle_metrics.py tests/test_spec_smt.py -q
.venv/bin/python -m pytest tests/ -q -x --timeout=300 -k "coverage or spec_ir or patch_rollback"
.venv/bin/python -m pytest tests/ -q -n 4 --dist loadfile --cov=src --cov-branch --cov-report=term-missing  # 全量+分支（CI:316 口径，耗时）
```

**D5 针对性复现我的指标类发现（零 LLM）**
```bash
# 覆盖率解析脆弱性（预期 1.0，非 99.0）
.venv/bin/python -c "from src.agents.executor_output import parse_coverage as p; print(p('TOTAL      50      5    1%    99%'), p('TOTAL 12 3 -'))"
# 受限求值器与白名单集合差
.venv/bin/python -c "from src.specs.spec_smt import _EVAL_SAFE_FUNCS;from src.specs.spec_ir_v2 import _ALLOWED_CALL_NAMES as A;print(sorted(set(A)-set(_EVAL_SAFE_FUNCS)))"
# 数据集有效独立样本量（预期 26 / 87）
.venv/bin/python -c "import re;from src.datasets.synthetic_dataset import SyntheticDataset;ts=list(SyntheticDataset(task_count=87,seed=42));b=[re.sub(r'# noise_seed\w*=\d+','',t.instance_code).strip() for t in ts];print(len(ts),len(set(b)))"
# 同 seed 两份批次是否逐字节重放
.venv/bin/python -c "import json;a=json.load(open('experiments/results/main_batch/benchmark_synthetic_20261007_161053.json'));b=json.load(open('experiments/results/main_batch/benchmark_synthetic_20261007_181638.json'));print({k:sum(1 for x,y in zip(v['details'],b['results'][k]['details']) if x.get('generated_test')==y.get('generated_test')) for k,v in a['results'].items()})"
```
（以上 4 条我在审计中均已实跑，结论见 §A/§B。）

**D6 不建议自动执行（需真实 LLM / 长时 / 花钱）**
```bash
# 复现主批次（会真实调用 LLM）——仅在明确预算与密钥时人工执行
AITESTER_PROFILE=logic .venv/bin/python experiments/run_main_batch.py --dataset synthetic --task-count 20 --seed 42 --baselines aitester,plain_llm,plain_llm_df --output-dir /tmp/ws3_replay --skip-stats
# 复现脚本 / Docker 全链（含全量测试 + 批次）
bash reproduce.sh            # 会跑全量 pytest 后再跑 benchmark
docker build -t aitester:latest . && docker run --rm aitester:latest --help
```

---

## §E 不确定项清单（未核实 / 机制未定，禁止当结论使用）

1. **plain_llm / plain_llm_df 的 `token_usage` 全 0 的机制未定**。已排除：不是"缓存命中导致"（`cache_hits` 同为 0，两条命中路径都会 `record_cache_hit_usage`：`base_agent.py:404-415,453-460`）；也不是"该臂没发 LLM 调用"（`generated_test` 非空且与另一批次逐字节相同）。可能是未走 `_call_llm_with_cache` 的某条生成路径、或记账写入的线程与结果行读取的线程不同（`token_usage` 为线程局部，`run_benchmark.py:1878` 每任务 `reset()`）。**需受控复跑 1 个任务并打印 `get_usage().as_dict()` 才能定论。**
2. **`spec_compile_rate`=0.21 的分母构成未逐行重算**（expr 通道 vs NL 通道占比、各门拒绝计数）。本报告只给代码层三道门的结构性根因；数值层面的复核属 WS2（指标重算）范围，我未采信任何既有报告数字。
3. **`_safe_eval` 支持 `**` 的 DoS 未实测触发**（构造巨整数会挂死进程，为避免影响同仓其他作业主动不跑）。这是基于代码路径的推断（`spec_smt.py:99-118,125-198` + 200 字符上限 `spec_ir_v2.py:106`），未做实证。
4. **未跑全量 pytest**，因此 `BASELINE.yaml:14` 的"5014 passed / 0 failed"与"全量用例零代码回归"未独立复核（我只实跑了 `tests/test_executor.py`：41 passed）。全量套件耗时与资源占用不明（addopts `--timeout=1200`）。
5. **未验证 PyPI 上钉版真实存在**（`z3-solver==5.1.0.0`、`pytest==9.1.1`、`pandas==3.0.5` 等 132 项 lock）。本机 `z3` 可用，仅证明本地环境有该包。跨源真伪核验属 WS1。
6. **未实测 `python -m build` / 全新 venv 安装 / CLI 冒烟**，A5 的"可安装性"仅静态一致。
7. **未执行 `reproduce.sh` / Dockerfile 构建**（会触发真实 LLM 或长时间构建）。
8. **`patch_applier.py` 的补丁安全守卫细节未逐条读完**（1375 行），§B12 的"应用侧守卫"只基于调用点与函数名/注释，未逐行核验其绕过面；与之相关的 `multi_candidate.static_validate_patch` 亦未逐行读。
9. **CI 的其余门禁脚本**（`check_env_budget`、`check_citations`、`check_artifacts_tracked` 等）我只读了配置与调用点，未逐个运行核验其断言强度。
10. **`docs/design/`、ADR 与 `docs/preregistration/` 的阈值/停止规则文本未核对**（本报告只做代码层判定；预注册与实现是否一致属另一工作流）。
