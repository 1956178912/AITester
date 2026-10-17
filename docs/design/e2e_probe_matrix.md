# 全功能端到端探针矩阵（e2e probe matrix）

> 最后更新：2026-10-18（O 轮：接入 CI 零 LLM 作业 + Docker 构建校验）
>
> **一句话**：`scripts/tools/e2e_probe.py` + 三个探针模块，把"项目所有用户可见
> 功能"变成一张可执行、可重复、可审计的**功能矩阵**——每个功能一行探针，状态
> （pass/fail/skip/error）+ 证据字段；零 LLM 默认，真实 LLM 探针按需显式开启。

## 1. 为什么需要它（三层验证的分工）

| 层 | 载体 | 回答的问题 | 盲区 |
|---|---|---|---|
| 单元/契约测试 | `tests/`（约 8000 条） | 模块接口是否符合契约 | 装配后是否真的可达 |
| 研究链路 e2e | `experiments/`（单链路脚本） | 某一条研究结论能否复现 | 其它功能是否静默失效 |
| **功能矩阵 e2e（本框架）** | `scripts/tools/e2e_probe.py` | **每个功能在真实装配（CLI/workflow/真 LLM/真子进程）下能不能用** | 语义正确性仍靠前两层 |

形成原因：M 轮之前的多次"文档与工件静默分裂"教训说明，**"有单元测试"不等于
"功能可达"**（例：开关打开了、代码路径却从不进入；字段存在、值恒 None）。
探针矩阵把这类"静默失效"显式化——fail/skip 都必须带证据与原因。

## 2. 架构

```
scripts/tools/e2e_probe.py          # 运行引擎（发现/隔离执行/报告/CLI）
scripts/tools/e2e_probes_workflow.py    # 组 1：CLI / workflow / agents / repair / safety
scripts/tools/e2e_probes_platform.py    # 组 2：budget / cache / RAG / security / executor / dataset / observability
scripts/tools/e2e_probes_logic.py       # 组 3：spec / DSL / SMT / oracle / stagnation
```

- **探针**：`Probe(name, group, func, requires_llm, timeout_s, description)`；
  `func` 返回 `ok()/fail()/skip()/error()` 或同构 dict。
- **隔离**：每个探针在**子进程**中执行（`--run-probe <name>`），崩溃/挂死/全局
  状态污染不波及主进程；超时由父进程统一处理（rc=124 → error）。
- **零 LLM 默认**：`requires_llm=True` 的探针只有在 `--include-llm` 且
  `AITESTER_E2E_LLM=true` 时才执行，否则 skip（并写原因）。运行器强制
  `AITESTER_LLM_CACHE=0`（避免把缓存重放误当真实功能验证）与独立 cache
  namespace。
- **纪律**：探针只写 tmp 目录；失败必须带实测值；skip 必须带原因；不得把
  "模型未产出"（如 LLM 没写补丁）当功能缺陷——功能正确性看状态字段（如
  `stop_reason`/`abstain`）是否按设计产生。

## 3. 功能矩阵（组与覆盖范围）

| 组 | 覆盖功能 |
|---|---|
| `cli` | `--help` / `list-examples` / `check-dataset` / `run`（单文件、多文件、`--json`）/ 参数校验 |
| `workflow` | `build_workflow` 节点装配（fast/safe/scientific/logic 档）/ 图连通 / 状态通道 / trace |
| `agents` | Planner 结构化计划 / Generator 生成可解析测试 / Executor 沙箱执行与判分 / Debugger 诊断 |
| `repair` | 修复环全链路 / 补丁应用 / 回滚 / 弃权 / 确定性修复 / 测试黑客守卫 / 契约守卫 |
| `localization` | 谱系 FL（Ochiai）/ fl_spectral / 多候选 / 故障知识库 |
| `safety` | 补丁安全守卫族（危险 API / 命名契约 / 测试黑客 / 确定性修复 / 快照回滚）——与 `security`（沙箱/凭证/注入）分列，避免"安全"一词混淆两类不同防线 |
| `budget` | 任务级 USD cap / 非法值 fail-closed / 批次级配额估算与停止通道 |
| `cache` | 语义缓存命中与 avoided-token 记账 / 缓存关闭口径 |
| `rag` | retriever 初始化/检索 / `ENABLE_RAG` 全链路 / 依赖缺失优雅降级 |
| `security` | 注入守卫检出与警示 / 凭据清洗 / 日志脱敏 / 内核沙箱能力探测 |
| `executor` | local / venv / docker（缺失时明确降级）/ repo 模式 |
| `dataset` | quixbugs / synthetic / ult / examples 加载 / 去污染检查 |
| `observability` | trace/event bus 落盘与脱敏 / model fingerprint（pinned） |
| `logic` | SpecIR / DSL 编译 / SMT 见证 / 确定性 oracle / 停滞检测开关 |
| `oracle` | oracle 独立判读（N-3）后的 LLM-suite vs oracle-suite 分离口径 |

> 功能新增/修改时**必须同步新增或更新探针**（矩阵即功能清单；门禁可对探针
> 清单长度与必需组做锁定测试，见 `tests/test_e2e_probe.py`）。

## 4. 用法

```bash
# 列出全部探针（功能清单）
python scripts/tools/e2e_probe.py --list

# 零 LLM 子集（CI 安全；默认不含 requires_llm 探针）
python scripts/tools/e2e_probe.py --all --md-out experiments/results/e2e_probe_latest.md

# 真实 LLM 探针（消耗配额；单探针 ≤2 次调用，运行器强制缓存关闭）
AITESTER_E2E_LLM=true python scripts/tools/e2e_probe.py --all --include-llm \
  --json-out experiments/results/e2e_probe_llm_latest.json \
  --md-out experiments/results/e2e_probe_llm_latest.md

# 按组/名过滤；--strict 让 fail/error/必需 skip 返回非零
python scripts/tools/e2e_probe.py --group repair --strict
```

Makefile：`make e2e-probe`（零 LLM）、`make e2e-probe-llm`（真 LLM）。

## 5. 与门禁/CI 的关系

- **CI 已有零 LLM `e2e-probe` job**（`.github/workflows/ci.yml`，O 轮 2026-10-18
  接入，ubuntu-latest）：跑 `python scripts/tools/e2e_probe.py --all`（47 个零 LLM
  探针；12 个真实 LLM 探针默认 skip，不设 secrets、零 API 配额）。job 判据是
  **0 fail / 0 error**；预期 skip 由探针内既有逻辑显式产生并在摘要逐条打印：
  `executor-docker-degrade`（CI 有 docker CLI）、`security-kernel-sandbox` /
  `executor-kernel-sandbox`（CI 明确不装 bwrap → 无 Linux 沙箱后端）、
  `dataset-ult`（CI 无 ULT 数据）。报告（`e2e_probe.json` / `e2e_probe.md`）
  以 artifact 归档。
- **CI 环境的非 secrets 前置准备**（失败即 job 红，不静默豁免）：`requirements.lock`
  全量安装；pinned QuixBugs 数据（dataset 探针需要 ≥41 程序，公开仓库钉 SHA）；
  chromadb 默认嵌入模型预热（RAG/语义缓存探针，首次 ~79MB，之后走 runner HOME 缓存）；
  git 身份（`RepoExecutor` 临时仓库 commit 需要）；嵌套 pytest 确定性钩子
  （`PYTHONPATH` 注入 `sitecustomize` 置 `sys.dont_write_bytecode`，消除
  "baseline/补丁两阶段同秒同尺寸源码 → pyc 复用"造成的 `executor-repo-verify`
  随机假红，本地 6/15 → 修复后 15/15；`make e2e-probe` 目标内嵌同一钩子，
  本地 "合并前建议跑" 与 CI 同口径）。
- **用户入口 `python main.py doctor`（P-3 产品化包装，2026-10-18）**：一条命令输出
  环境/配置检查（Python/可选依赖/LLM 端点存在性/数据集缓存/内核沙箱/git 状态）
  + 零 LLM 探针矩阵聚合（内部隔离子进程调本框架 `--all --json-out`，强制剥除
  `AITESTER_E2E_LLM`）；支持 `--json`（stdout 纯 JSON）/`--groups`/
  `--timeout`/`--strict`；退出码 fail/error→1、仅 warn/skip→0（`--strict` 时
  warn/skip→1）。本机实测全量零 LLM 自检约 20s 量级；pass/skip 数量随探针
  矩阵演进而变，以命令实际输出（或 `--json` 报告）为准，本文不复制具体计数。
- **真实 LLM 探针不进 CI**：成本与模型非确定性不适合每次 push 阻断；仍按
  `make e2e-probe-llm`（或 `AITESTER_E2E_LLM=true ... --include-llm`）在发布前/
  季度巡检按需跑。
- 另有随 CI 新增的 `docker-build` job（同文件，纯 shell）：构建 `Dockerfile`
  运行时镜像 + 镜像内 import/CLI 冒烟 + `.env*` 不入镜像检查；`Dockerfile.repro`
  只做存在性 + 可选 `docker build --check` 静态检查（不真构建）。
- 功能矩阵的**长期价值**在于"每次新功能落地都补一行探针"——它比一次性 e2e
  脚本更难腐化（每行都有断言与原因），也比门禁更灵活（skip 允许披露能力缺口）。

## 6. 已知边界

- 探针验证"可达 + 关键状态正确"，**不**验证语义正确性/研究口径（前者归单元测试，
  后者归 BASELINE/工件对账）。
- 真实 LLM 探针受模型非确定性影响：断言必须落在**结构/字段**上（例如"生成了可解析
  的 pytest 文件、字段非空"），不得断言具体内容/具体检出结果。
- 本机能力差异（无 docker CLI、macOS seatbelt 不可用等）一律显式 skip/限定
  "unsupported"，不得静默 pass。
- CI（ubuntu-latest）与本地 macOS 的探针覆盖差异（均为**显式 skip**、不是静默
  放过）：内核沙箱探针在 CI 因无 bwrap 而 skip（macOS 本地走 Seatbelt 真实
  执行）；`executor-docker-degrade` 在 CI 因 docker CLI 存在而 skip（本地无
  docker CLI 时走降级断言）。需要覆盖这些路径时用对应平台/专门 job 跑。
- 探针模块间存在**同名探针**（`observability-trace-redaction` /
  `observability-event-bus` 同时定义在 workflow 与 platform 模块）；`--all`
  加载时运行器保留首个并打印"探针名重复"告警。不影响 pass/fail 判据，但同名
  探针的 platform 版本在当前 `--all` 口径下不会被执行（已知边界，见 O 轮报告）。
