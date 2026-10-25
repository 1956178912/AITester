# AITester 复现包说明（Replication Package）

本文档描述 AITester（面向 EMSE 的 LLM 测试生成实证研究）复现包的构成与
使用口径：运行环境、模型与执行设置、数据来源与许可、零 LLM 可复算路径、
含 LLM 的实验路径、预期产物与已知偏差、引用与许可、已知限制。

写作纪律：文中每一项数字/事实均标注仓库内来源（`文件:行号`），且该文件已
被实际读取核对；凡无法从仓库内文件核实的条目，一律写作
`[待补充：<所需信息>]`，不作推测。历史批次的原始 LLM 执行不可离线重放，
可离线复算的只有基于已入库工件的指标（见第 4、8 节）。

**路径口径（CM 轮补，2026-10-25）**：本文反引号里的路径分三类，读者可按类复核：

1. **在盘文件**（默认）：可直接 `ls`/读取；
2. **已撤回的历史工件**：同句标「已撤回」并指向
   `docs/study/WITHDRAWN_ARTIFACTS_2026-10-24.md`（表 W-1 为冻结读数落点）；
3. **运行时产物**：同句标「运行为产、不入库」，干净检出中本就不存在。

`path:line` 的行号指当前工作树版本；文件改动后行号会漂移，以路径 + 内容为准。

## 1. 环境（Environment）

**Python 版本要求**（各处声明的精确字符串）：

- `pyproject.toml:24`：`requires-python = ">=3.12"`；
- `Dockerfile:6`：`FROM python:3.12-slim`（运行时镜像，`EXECUTOR_USE_DOCKER=true`
  时的被执行侧）；
- `Dockerfile.repro:32`：`FROM python:3.12-slim`（宿主侧实验复现镜像）；
- `Dockerfile.repro:18-20` 的口径说明：`python:3.12-slim` 为发行基准，与
  `Dockerfile` 一致；`pyproject requires-python >=3.12` 为下限，CI 矩阵
  3.12/3.13/3.14 全绿。

注意（如实披露）：主批次工件记录的**实际**解释器为 Python 3.14.6（macOS），
并非 3.12 —— 见第 2 节与第 6 节。

**依赖锁定**：

- `requirements.lock` 共 132 行（`wc -l`），全部为纯 `==` 版本固定
  （`Dockerfile.repro:21` 明确记载"requirements.lock 为纯 `==` 版本固定，
  与解释器小版本无关"）；
- 实际读取到的示例 pin（行号取自 `requirements.lock`）：
  `numpy==2.5.2`（第 64 行）、`pandas==3.0.5`（第 78 行）、
  `scipy==1.18.0`（第 110 行）、`openai==2.54.0`（第 67 行）、
  `pytest==9.1.1`（第 94 行）；
- 依赖安装口径：`Dockerfile:23-24` 与 `Dockerfile.repro:46-48` 均为
  `COPY requirements.txt ...` + `pip install --no-cache-dir -r requirements.txt`
  （实际安装 `requirements.txt`；`requirements.lock` 作为锁定记录随镜像复制）；
  `Dockerfile:17-22` 记载顶层依赖以 `==` 锁定并"与 requirements.lock 同步，
  由 `scripts/gates/check_lock_sync.py` 在 CI 守卫一致性"；
- `Dockerfile.repro:22-25` 说明复现镜像采用**全量依赖**口径（含
  chromadb / matplotlib / scipy），而非 `slim_environment` 精简口径。
- **wheel 安装口径（A13，2026-10-18）**：仅 wheel / 非仓库开发安装时，
  运行 Executor 与基准评测须安装执行 extra：
  `pip install "aitester[execution]"`（pytest + pytest-cov + pytest-timeout）；
  `requirements.txt` 全量安装已含 pytest，仓库开发 / 复现环境无需额外。
  默认 `pip install aitester` 不含执行工具；缺模块时 Executor 返回
  `error_info.type=execution_dependency_missing` 并提示该命令（执行前能力
  检查，不再以晦涩的 rc=1 失败）。

**复现容器（Dockerfile.repro）**：

- 构建（`Dockerfile.repro:8-9`）：
  `docker build --build-arg GIT_SHA=$(git rev-parse HEAD) -f Dockerfile.repro -t aitester-repro:$(git rev-parse --short HEAD) .`
- 运行（`Dockerfile.repro:10-15`）：
  `docker run --rm -v $(pwd)/experiments/results:/workspace/experiments/results -v $(pwd)/.env.local:/workspace/.env.local:ro aitester-repro:<sha> bash reproduce.sh --dataset synthetic --full`
  （`--dataset synthetic --full` = 主批任务规模参数 87 任务 / `--max-pattern-repeat 2`
  / seed 42 / 主批三臂；本脚本单 seed，三种子协议见
  `experiments/run_main_batch.py`，见 §5、§6 偏差说明）
- 系统依赖：`gcc` 与 `git`（`Dockerfile.repro:35-38`，注释说明 `git` 为
  SWE-bench 源码导出脚本所需）；
- **GIT_SHA provenance 机制**（逐行读取 + A03 修复后口径）：
  - `Dockerfile.repro:8-14`：构建命令显式传 `--build-arg GIT_SHA=$(git rev-parse HEAD)`；
  - `Dockerfile.repro:40`：`ARG GIT_SHA=unknown`（未传时的缺省值）；
  - `Dockerfile.repro:52`：
    `RUN echo "GIT_SHA=${GIT_SHA}" > /workspace/.repro_provenance`
    （容器内落盘标记文件）；
  - 运行侧消费点（A03 修复，2026-10-18）：`.dockerignore` 排除 `.git`，容器内
    `git rev-parse HEAD` 必然失败——`experiments/run_benchmark.py` 的
    `_read_repro_provenance_marker` / `_resolve_git_provenance` /
    `_build_environment_provenance` 读取 marker 的 `GIT_SHA`：
    - 无 git（复现容器 / 源码包）：`environment.git_sha` 与
      `provenance.git_sha` = marker SHA，`git_sha_source="repro_provenance"`；
    - 有 git：以 `git rev-parse HEAD` 为 `git_sha`，同时记录 marker 值并校验
      一致性（`provenance.repro_provenance.git_sha_matches_git` /
      `git_sha_conflict`；不一致时 logger.warning）；
    - `environment.in_docker_repro` 仍表示"marker 是否存在"；
    - marker 值为 `unknown`（构建未传 build-arg）时**不**当作提交 SHA：
      `git_sha_source=null` 并如实标注不可追溯。
  - 仓库内调用点核查：全仓检索 `Dockerfile.repro` 仅命中其自身注释、
    `experiments/run_benchmark.py`（provenance 实现）、
    `docs/design/real_benchmark_upgrade.md:47`、
    `docs/study/SUBMISSION_CHECKLIST_2026-10-15.md:50`（人工命令）、
    `reproduce.sh` 头注释与本文件；在 `*.yml` / `*.yaml` / `Makefile` 中检索
    `build-arg GIT_SHA` / `GIT_SHA=` **0 命中**，即仓库内**没有**自动构建该镜像
    的 CI 调用点（镜像构建为人工/外部步骤）。

## 2. 模型与执行设置（Model and Execution Settings）

> **历史口径横幅（2026-10-25 CK 轮补）**：本节原文逐字段描述的主批次工件
> `experiments/results/main_batch/benchmark_synthetic_20261006_140906.json`
> 已随 2026-10-24 数据清除**撤回**（文件不在盘；撤回映射见
> `docs/study/WITHDRAWN_ARTIFACTS_2026-10-24.md`）。以下字段值作为**历史记录**
> 保留（论文中引用该批数字处均已标 historical）；**当前语料**的模型与执行口径
> 以 v0.8.0 重建批为准：DeepSeek 官方单端点（`https://api.deepseek.com` /
> `deepseek-flash`）、`temperature=0`、 provenance 带模型指纹与 SHA256SUMS
> 冻结（`git_dirty=False`），逐批读数见 `BASELINE.yaml` 与各批
> `experiments/results/<批次>/` 工件。

主批次工件（已撤回）：`experiments/results/main_batch/benchmark_synthetic_20261006_140906.json`
（原 2,339,376 字节，原已入库）。以下字段均直接读取自该文件（撤回前）的
`provenance` 块：

| 字段 | 值 | 来源 |
|------|----|------|
| `model_name` | `deepseek-flash` | provenance.model_name |
| `valid_apis[0].url` / `.model` | `https://api.deepseek.com` / `deepseek-flash` | provenance.valid_apis |
| `temperature` | `0.0` | provenance.temperature |
| `max_iterations` | `3` | provenance.max_iterations |
| `seed` | `42` | provenance.seed（顶层 `seed` 同为 42） |
| `cache_namespace` | `seed42` | provenance.cache_namespace |
| `cache_enabled` / `cache_isolate_model` | `true` / `true` | provenance |
| `env_snapshot` | 32 个键（dict 长度 32） | provenance.env_snapshot |
| `harness.snapshot_date` / `harness.model_version` | `2026-10-06` / `deepseek-flash` | provenance.harness |
| `git_sha` | `b533cff1c316e8e80db635a1b2946610b211a5b6` | provenance.git_sha |
| `git_dirty` | `true` | provenance.git_dirty |

同文件的顶层执行口径：`dataset = "synthetic"`、`total_tasks = 87`、
`baselines = ["aitester", "plain_llm", "plain_llm_df"]`、`parallelism = 4`、
`enable_rag = false`、`p2p_gate_enabled = true`、`p2p_gate_threshold = 0.95`；
`environment` 块记录 `python_version = "3.14.6"`、
`platform = "macOS-27.0.1-arm64-arm-64bit-Mach-O"`、`in_docker_repro = false`。

**seed 的作用域（读源码核实）**：`experiments/run_benchmark.py:2945-2946`
的注释原文为"LLM 文件缓存键不含 seed（seed 只作用于任务采样，不传 API）"。
即：seed 用于合成任务采样（`experiments/run_benchmark.py:2972-2973`：
`SyntheticDataset(task_count=tc, seed=seed, ...)`）与缓存命名空间隔离
（`experiments/run_benchmark.py:2952-2953`：缓存开启且未显式设 `AITESTER_CACHE_NAMESPACE`
时自动设为 `f"seed{seed}"`，故主批次命名空间为 `seed42`），**不会**作为
采样参数发送给 LLM API。佐证（读该 JSON 的 `env_snapshot`）：命名空间
`AITESTER_CACHE_NAMESPACE = seed42` 已记录在快照中，而快照里与 API 采样
相关的键只有 `TEMPERATURE = 0.0`（共 32 个键，其余为功能开关与超时；
未见 `seed` / `top_p` 等 API 采样参数键）。

**已知可复现性限制（如实声明）**：该主批次 provenance 中
`git_dirty = true`，且**没有** `model_fingerprint` 块——对文件原文做字符串
计数，`model_fingerprint` 出现 0 次；`provenance` 的键集合为
`{git_sha, git_dirty, model_name, temperature, max_iterations, seed,
env_snapshot, cache_enabled, cache_isolate_model, cache_namespace,
valid_apis, harness}`。因此：

1. 仅凭 `git_sha` 无法重建当时的代码树（存在未提交改动）；
2. 无法事后核验 API 实际返回的模型版本（`experiments/run_benchmark.py:2627-2734` 存在
   模型指纹探针实现，但本批次工件未落盘该块）。

即本批次的模型版本锁定不完整，属**已知复现性缺口**，不作"完全可复现"
表述。

## 3. 数据（Data）

**合成基准来源**（`docs/DATA_CARD.md`）：

- `docs/DATA_CARD.md:29-31`："**来源**：全部由项目作者手写（8 个 pattern 池
  按 name 去重共 50 个唯一缺陷 pattern，`BASELINE.yaml synthetic_templates`
  为单一事实来源，`scripts/tools/verify_synthetic_templates.py` 三重不变量
  自验证）"；
- `docs/DATA_CARD.md:32-35`："**构造**：每 pattern 含 buggy `template` /
  `fixed` / gold `test_cases` 三件套；实例化仅追加噪声注释
  （`# noise_seed=<0-9999>`）并做 task_id 中性化（`task_0000..`，P1-4 泄漏
  修复……），gold 测试 import 同步重写（`_neutralize_gold_imports`）"；
- `docs/DATA_CARD.md:21` 状态列：合成缺陷模板库为"多批次在用（模板库 **50 个唯一
  pattern**；当前确认性主批 = **87 任务 × 3 seeds** × 3 臂；n=50/seed42 为**历史
  主批**）"（原文以勾选符号标注状态，此处按纯文本转述）。**F17 更正（2026-10-22）**：
  "n=50"与"87 任务"不是矛盾口径——前者是 pattern 数/历史主批规模，后者是当前主批
  实例化规模；同一说明已在数据卡给出。

**原始任务定义位置**（读取源码核实）：`src/datasets/synthetic_dataset.py`
内定义 8 个 pattern 池 —— `BUG_PATTERNS`（第 32 行）、`BUG_PATTERNS_LEVEL2`
（第 499 行）、`CROSS_FILE_PATTERNS`（第 773 行）、`BUG_PATTERNS_LEVEL25`
（第 860 行）、`BUG_PATTERNS_LEVEL25HARD`（第 1253 行）、
`CROSS_FILE_DEEP_PATTERNS`（第 1824 行）、`BUG_PATTERNS_LEVEL4`（第 1922 行）、
`BUG_PATTERNS_LEVEL45`（第 2138 行），并由 `_DIFFICULTY_PATTERNS`（第 2237 行）
按难度索引；pattern 总数以 `BASELINE.yaml` 为准（`BASELINE.yaml:120`：
`synthetic_templates: 50`）。

**gold 材料位置**（`docs/DATA_CARD.md:42-45`）：`metadata["test_cases"]`
（gold 测试）、`metadata["fixed"]`（单文件 gold 补丁）、`fixed_module_code`
（跨文件）、`pass_to_pass`（P2P 回归集）；gold 材料只进结果行
`task_metadata`，"**不进任何 LLM prompt**"。

**数据许可事实**（引自 `docs/DATA_CARD.md` 已核实结论，原文照录）：

- `docs/DATA_CARD.md:87-89`："**QuixBugs：MIT License（已核实，L1/E4 前置
  条件解除）**——`api.github.com/repos/jkoppel/QuixBugs` license 字段
  `spdx_id=MIT`（核实日期 2026-10-06）"；
- `docs/DATA_CARD.md:108-110`："**BugsInPy：无 SPDX 可识别许可证（新发现
  合规门槛，L2 实跑前须用户决策）**——`api.github.com/repos/google/bugsinpy`
  license 字段为 null（2026-10-06 核实），即上游未随仓库声明许可、默认
  版权保留"；
- `docs/DATA_CARD.md:81-84`（TestGenEval，L2 候补、未加载零实跑）：
  "**许可：CC BY-NC 4.0**（GitHub API license 字段 `spdx_id=NOASSERTION`，
  LICENSE 原文核实 2026-10-07 = Attribution-NonCommercial 4.0 International）"；
- 第三方数据本体**不随仓库分发**：QuixBugs 目录经 `AITESTER_QUIXBUGS_DATA`
  注入、"不随仓库分发，需自行获取上游数据"（`docs/DATA_CARD.md:71-72`），
  本地目录 `data/quixbugs` 为 gitignore 区不入库
  （`docs/DATA_CARD.md:90-91`）；
- 本仓库软件许可为 MIT（`LICENSE:1`："MIT License"；`LICENSE:3`：
  "Copyright (c) 2026 AITester Contributors"）。
- `[待补充：合成缺陷模板库（合成基准本体）的再分发许可声明]`——`docs/DATA_CARD.md`
  未就合成模板单独声明许可，仅有"由项目作者手写"的来源说明。

## 4. 零 LLM 可复算路径（Offline Path, no API key）

**当前官方零 LLM 复算链**（2026-10-25 CJ 轮起口径）：`scripts/reproduce_zero_llm.py`，
两个 Makefile 入口（`Makefile:130,133`）：

- `make reproduce-zero-llm`（层级 `l0`）：统计扩展（Wilson CI / Cohen's g / OR /
  bootstrap Δ CI）、统计报告补口（MDE / 功效 / 比例型 bootstrap CI）、mutation ×
  detection 交叉验证、SWE-bench Lite 基础设施失败披露、通过率混淆敏感性分析、
  引用可追溯性核验，外加逐目录 SHA256SUMS 校验；
- `make reproduce-zero-llm-l1`（层级 `l1`）：在 L0 之上增加 QuixBugs 全量
  Mut@k 重算（cosmic-ray，小时级）。

**三态结果与退出码口径**（v0.8.0 后数据重置的直接后果）：每条命令的结果为
`ok` / `FAILED` / `skipped` 三态之一；源工件已随 2026-10-24 数据清除撤回的支路
输出显式 `[SKIP]` 并附理由（如「源批次 main_batch 已随 2026-10-24 数据清除撤回，
本支路待主批重建后恢复」）——**可复算性受损是事实，不谎报 ok、也不计红**；报告
顶部明示「N/M 条命令通过（K 条源工件缺席 [SKIP]）」。脚本退出码只由
「FAILED 命令数 + SHA256SUMS 失败数」决定（`scripts/reproduce_zero_llm.py`
的 `main()` 收尾段）。2026-10-25 实测（L0，CM 轮）：**3 ok / 3 [SKIP] / rc=0**
（回撤支路 = 统计报告补口、mutation × detection 交叉验证、通过率混淆敏感性分析，
三者共用已撤回的 `main_batch`）。

**工件完整性四态（CM 轮收口）**：`SHA256SUMS` 校验此前只有「有清单就校验 /
没清单就跳过」两态，于是「6 条清单里 5 条目录已撤回、唯一在盘目录没有清单」
被读成「0 通过 / 0 失败 / 6 跳过」——完整的 0 份受检文件也是绿的。现分四态：

| 状态 | 含义 | 是否计红 |
|---|---|---|
| `ok` | 清单存在且逐文件校验通过 | 否 |
| `FAILED` | 校验不符，**或目录在盘却没有清单** | **是** |
| `absent` | 目录缺席（已撤回 / 未生成） | 否（披露） |

受检面 = 除 `traces/` 外的全部文件（论文数字来自 benchmark / stats / raw 工件；
原始 trace 是旁路记录，纳入会把完整性稀释成日志归档）。发布轮用
`python scripts/reproduce_zero_llm.py --write-checksums` 生成/刷新清单。
2026-10-25 实测：**8 个目录通过 / 401 个受检文件 / 0 失败 / 5 目录缺席**
（缺席 = `main_batch` 与四个 20261014–20261016 历史批）。
本链的结构契约（命令集完整性 / 四元组形态 / 数据集分支 / 完整性四态）由
`tests/test_reproduce_zero_llm.py` 锁定。

**遗留存量重放目标（历史口径，当前无输入）**：以下 Makefile 目标在
2026-10-24 数据重置前基于已入库主批次工件做零 LLM 重算；其输入目录
`experiments/results/main_batch/` 随该次清除撤回（撤回清单与替代映射见
`docs/study/WITHDRAWN_ARTIFACTS_2026-10-24.md`），**在当前树上没有可读取的
输入**，作为历史能力保留（脚本与回归测试仍在盘，主批重建后即可恢复）：

| Makefile 目标 | 重算什么 | 当前状态 |
|---------------|----------|----------|
| `repair-replay` | `repair=0` 围栏伪影的存量重放（`Makefile:76-77`，批次 VII/ADR-0021） | 输入已撤回；命令形态 `python -m experiments.repair_replay <results_dir> --arm aitester`，`--out` 默认 `None` 打印到 stdout |
| `corrected-metrics` | 修正口径重估总报告（`Makefile:82-83`，批次 XIII/ADR-0027） | 输入已撤回；同上 stdout 口径 |
| `target-quality` | 目标质量存量重放（`Makefile:85-86`，R5 审查批次） | 输入已撤回；写出 `<results_dir>/target_quality_report.md` |
| `mutation-det-correlation` | mutation × detection 交叉验证（`Makefile:88-89`，EMSE 批次 2026-10-15） | 输入已撤回；产物为 `--out` 指定路径 |
| `swebench-disclosure` | SWE-bench Lite 基础设施失败披露（`Makefile:91-92`，EMSE 批次 2026-10-15） | **仍可执行**（不依赖主批；产物 `experiments/results/emse_swebench_disclosure.md` 在盘且已随 L0 复算） |
| `cpr-idr` | 补丁检测有效性 + 弃权视角报告（`Makefile:73-74`，批次 II/V） | 输入已撤回；stdout 口径 |

上述目标的离线性由脚本 import 面保证（仅标准库，不导入 `config` / `dotenv` /
LLM 客户端）；均可用 `make <target>` 调用（`Makefile:10`：`PY := .venv/bin/python`），
前提是本地已安装仓库锁定依赖（`.venv`）且指定目录含相应批次工件。

## 5. 含 LLM 的实验路径（Requires API Key）

`reproduce.sh` 的 6 个步骤（逐段读取该文件）：

1. **Step 1/6 检查运行环境**（`reproduce.sh:170-227`）：检查 `python3`
   （"请安装 Python 3.12+"，第 191-193 行）、按需创建并激活 `.venv`
   （第 199-206 行）、检查 `.env`（缺失则从 `.env.example` 复制，第 209-214 行）、
   检查 LLM 敏感配置 `.env.local`（缺失则从 `config.local.example` 复制并提示
   "请填入 LLM_1_API_KEY 后再运行"，第 218-222 行）；若 `LLM_1_API_KEY` 未设置
   或仍为占位值则告警（第 225-227 行）。
2. **Step 2/6 安装 Python 依赖**（`reproduce.sh:229-234`）：
   `pip install -q -r requirements.txt`，并额外
   `pip install -q scipy matplotlib pandas`。
3. **Step 3/6 运行单元测试**（`reproduce.sh:236-253`）：
   `python -m pytest tests/ -v --tb=short`，输出经 `tee` 写入
   `experiments/results/test_output.log`（第 247 行）；测试失败默认**硬失败**
   退出（第 248-253 行），仅当显式设置
   `REPRODUCE_ALLOW_TEST_FAILURES=1` 才告警继续。F05 逃生：显式设置
   `REPRODUCE_SKIP_TESTS=1` 时整个测试门跳过并打印醒目 WARN
   （"本次复现缺少测试门，复现结论不含测试验证"）；默认不设仍跑测试且保持
   fail-closed。
4. **Step 4/6 准备数据集**（`reproduce.sh:255-278`，A02 修复后口径）：
   `--dataset swe_bench` 时从 HuggingFace 下载（quick=mini 50 任务 /
   full=lite 500 任务，第 257-270 行）；`--dataset examples` 使用内置示例数据集
   （3 个预定义 bug 任务，第 271-272 行）；**`--dataset synthetic` 使用内置合成
   数据集**（本地生成，无需下载，第 273-274 行）；未知数据集**不再回退**
   examples——参数解析段（`reproduce.sh:96-135`）已 fail-closed 报错退出，
   此处仅双保险（第 275-278 行）。此步不调用 LLM。
5. **Step 5/6 运行基准测试**（`reproduce.sh:280-332`）：
   `python experiments/run_benchmark.py --dataset "$DATASET" --baselines "$BASELINES"
   $TASK_LIMIT_ARG $TASK_COUNT_ARG $MAX_PATTERN_REPEAT_ARG $SEED_ARG $ENABLE_RAG
   --output-dir experiments/results $VERBOSE`
   （第 318-327 行）；synthetic 参数透传（`--task-count` / `--max-pattern-repeat`
   / `--seed`）构建于第 288-293 行；同时显式设置 `AITESTER_TRACE_DIR`
   （默认 `experiments/results/traces`，第 297-298 行）；变异得分默认关闭
   （`ENABLE_MUTATION_SCORING` 未设为 true 时不启用，第 305-310 行）。
   **本步是真正需要真实 API Key 的步骤**——基准测试由 LLM 生成/修复驱动，
   密钥来自 `.env.local` 的 `LLM_1_API_KEY`（Step 1 只做存在性检查与告警，
   不会因为缺 Key 而终止）。
6. **Step 6/6 生成可视化**（`reproduce.sh:334-337`）：
   `python experiments/visualize_results.py --dataset "$DATASET"`（F06：显式
   数据集来源——只取 `benchmark_<dataset>_*` 前缀产物，不按文件名倒序猜测），
   生成柱状图、统计检验图、CSV 表格与 Markdown 汇总报告。

**A02 修复（2026-10-18）：数据集分支与主批入口对齐**。`reproduce.sh` 现显式
支持 `--dataset synthetic`：参数解析段归一 `synth` 别名并 fail-closed 未知值
（`reproduce.sh:96-135`）。`--dataset synthetic --full` 的默认参数 = 主批入口
参数 `--task-count 87 --max-pattern-repeat 2 --seed 42` + 主批三臂
`aitester,plain_llm,plain_llm_df`（用户显式 `--baselines` 可覆盖；
quick 模式为 3 任务）。与主批**完整协议**（3 seed 42/43/44 × 3 臂、逻辑档
`AITESTER_PROFILE=logic`、`TEMPERATURE=0.0`、冷缓存）的差异：本脚本单次运行
单 seed，且不代设 profile/温度环境变量；三种子协议入口是
`experiments/run_main_batch.py` / `experiments/run_t1_b2_main_batch.sh`，
不同 seed 批次不可直接合并统计。回归锁定：
`tests/test_reproduce_zero_llm.py::TestReproduceShDatasetBranch`。

结果文件位置（`reproduce.sh:345-351`，**运行为产、不入库**——干净检出中不存在，
由 Step 5/6 现场生成）：`experiments/results/benchmark_*.json`、
`experiments/results/charts/baseline_comparison.png`、
`experiments/results/charts/statistical_significance.png`、
`experiments/results/charts/results_table.csv`、
`experiments/results/charts/summary_stats.md`。

Docker 化路径同样落在 Step 5（`Dockerfile.repro:10-15` 的 `docker run ... bash
reproduce.sh --dataset synthetic --full`），故需将 `.env.local` 只读挂载进容器。

**F05 修复（2026-10-19 第三方审查，P2）**：`Dockerfile.repro` 通过
`.dockerignore` 排除 `experiments/results`（`.dockerignore:49-53` 的 F05 注释），
即镜像**不自含**该目录（镜像保持轻量、历史归档不随镜像分发）；但 Step 3 全量
测试中多组用例以该目录下的历史归档工件为夹具。因此
`-v $(pwd)/experiments/results:/workspace/experiments/results` 挂载的目录
（`Dockerfile.repro:10-16`、`Dockerfile.repro:59-70` 的 F05 注释）
**同时是历史输入（测试夹具）和输出（本次结果）**：复现时须挂载含归档结果的
完整目录；空目录启动须显式 `REPRODUCE_SKIP_TESTS=1` 跳过 Step 3
（`reproduce.sh:236-253`；该次结论不含测试验证，脚本打印醒目 WARN）。默认不设
该变量时仍跑测试并保持 fail-closed。

## 6. 预期产物与已知偏差（Expected Artifacts and Known Deviations）

**逐目录校验和（SHA256SUMS）**（`find` / `git ls-files` / 逐条计数实测，
2026-10-25 CJ 轮，数据重置后口径）：

- 全仓共 **4** 个校验和文件，全部位于 `experiments/results/` 下、**全部已被
  git 跟踪**（`git ls-files` 逐条实证），无未跟踪清单（2026-10-18 旧口径的
  69 个文件 / 7,048 条记录随 2026-10-24 数据清除整体退出，撤回映射见
  `docs/study/WITHDRAWN_ARTIFACTS_2026-10-24.md`）；
- 在盘清单逐条计数（`grep -c '^[0-9a-f]\{64\}'`，2026-10-25 实测）：
  `emse_docstring_anchor_20261017/run_artifacts_20261024T121431Z/SHA256SUMS`
  **17** 条、`emse_docstring_augment_20261017/SHA256SUMS` **127** 条、
  `emse_misguided_augment_20261017/SHA256SUMS` **3** 条、
  `p_round_b8_ablation_20261018/SHA256SUMS` **34** 条，合计 **181** 条；
- 这些清单覆盖的是**重建语料的正式批工件**（docstring 锚/增广三臂 + b8 消融），
  即 v0.8.0 数据换代后按历轮惯例 `git add -f` 入库的部分；
- **跨平台字节口径（A17 修复，仍然有效）**：仓库根 `.gitattributes` 对
  `experiments/results/**` 与 `docs/reviews/review_recompute/**` 设 `-text`
  （证据工件按二进制保真，检出字节 = 入库字节 = LF；不使用 `text eol=lf`，
  以免改写历史 CRLF 字节）。Windows `core.autocrlf=true` 的干净检出因此同样
  按原始字节匹配；受影响的历史 Windows 检出需重新检出才恢复字节。
  `scripts/gates/checksum_results.py --verify` 现区分
  **原始字节 / 仅 EOL 差异 / 内容不符** 三类：EOL 差异单独报告且默认不判
  （不再把换行约定误报为篡改），内容不符仍失败；`--strict-bytes` 可把 EOL
  差异升级为失败（发布/归档字节闸）；
- **清单只覆盖分发文件（A18 修复，仍然有效）**：`--write`/`--verify` 统一排除
  `__pycache__` / `*.pyc` 等解释器缓存；校验入口：
  `python scripts/gates/checksum_results.py --write`（生成/刷新，只写规范名
  `SHA256SUMS`）/ `--verify`（按清单校验；对外部工具生成的 `SHA256SUMS.txt`
  变体同样支持）/ `--verify --strict-bytes`（严格字节闸），默认
  `--results-dir experiments/results`；回归：
  `tests/test_checksum_results_gate.py`。

**已知偏差（如实声明）**：

1. **历史主批次已撤回（2026-10-24），其偏差记录降为历史口径**：原第 1/3/4 条
   所述的 `benchmark_synthetic_20261006_140906.json`（`git_dirty: true`、无
   `model_fingerprint`、实际运行环境 Python 3.14.6/macOS 而复现镜像为
   `python:3.12-slim`）随数据清除撤回，**不在当前复现包内**；撤回规模、逐目录
   映射与保留判定见 `docs/study/WITHDRAWN_ARTIFACTS_2026-10-24.md`。引用该批
   历史数字时（论文中以 historical 标注处）应同时声明这三条偏差。
2. **未归档原始 LLM 响应**：LLM 响应只落盘到本地文件缓存，且缓存路径被
   `.gitignore` 排除——`.gitignore:66-67` 原文为
   `# LLM 文件缓存（本地优化产物，避免重复提交）` 与 `src/cache/`
   （`git check-ignore -v src/cache/example.json` 实证命中 `.gitignore:67`）；
   另据 `src/agents/llm_client.py:561-566`，运行时缓存默认目录已从
   `src/cache/` 迁出源码树，改为用户缓存目录
   （`XDG_CACHE_HOME` 或 `~/.cache/aitester/llm`，第 567-571 行），即**默认
   路径本就在仓库之外**。两种情形下仓库内均不含原始 LLM 响应。
3. **重建语料的 provenance 口径**：v0.8.0 重建批（27 批 / 14 traces 目录 /
   1,106 traces，`git_dirty=False`）带模型指纹与 SHA256SUMS 冻结；论文表 1
   主数字与 RQ1 配对对比均出自该重建语料（`spec_ab_scale87_20261024` 等），
   与撤回前的历史读数**不混池**。
4. **校验和文件的生成/校验入口（A17/A18 修复后口径）**：仓库提供
   `python scripts/gates/checksum_results.py --write`（生成/刷新，排除
   `__pycache__` 等非分发文件，只写规范名 `SHA256SUMS`）与 `--verify`
   （按清单校验：缺失/清单外新增/内容不符判失败；**仅换行差异**单独报告、
   默认不判，`--strict-bytes` 可升级为失败），默认
   `--results-dir experiments/results`；清单名常量为 `SHA256SUMS`，
   `--verify` 兼容外部工具生成的 `SHA256SUMS.txt` 变体
   （`scripts/gates/checksum_results.py`；回归：
   `tests/test_checksum_results_gate.py`）。证据工件换行策略见仓库根
   `.gitattributes`（上方 A17 条目）。
5. **零 LLM 复算链的三态口径**：`scripts/reproduce_zero_llm.py` 对源工件缺席
   的支路输出显式 `[SKIP]`（第 4 节），退出码只由 FAILED 与 SHA256SUMS 失败
   决定——`[SKIP]` 是披露，不是通过；主批重建后这些支路自动恢复判定。

## 7. 引用与许可（Citation and License）

- **软件许可**：MIT License（`LICENSE:1` "MIT License"；`LICENSE:3`
  "Copyright (c) 2026 AITester Contributors"）。
- **引用元数据**：`CITATION.cff`（CFF 1.2.0；`cff-version: 1.2.0`，第 1 行）；
  当前 `version: 0.8.0`（第 19 行）、`date-released: "2026-10-25"`（第 20 行）、
  `license: MIT`（第 21 行）、`repository-code:
  https://github.com/1956178912/AITester`（第 22 行）——行号为本文件所引用的
  当前工作树版本（`CITATION.cff` 25+ 行）。
- **归档**：`[待补充：Zenodo DOI / 归档计划]`（`CITATION.cff` 内已同步以
  YAML 注释登记 DOI 待归档，见该文件第 2-5 行；CFF 1.2.0 的 `doi` 字段需
  真实 DOI，占位值不可用）。归档元数据**尚未生成**（2026-10-25 CK 轮更正：
  该处原写「已备：`experiments/results/zenodo_metadata.json`」，实测该文件
  不在盘、git 历史亦无——属登记面失实，已改为待补充项；Zenodo 上传元数据
  将在投稿/归档时随 DOI 一并生成）。
- 数据集许可按来源分别登记，见第 3 节与 `docs/DATA_CARD.md` §4。

## 8. 已知限制与后续（Known Limitations and Follow-up Work）

- **原始 LLM 执行不可离线重放**：仓库内不含原始 LLM 响应（第 6 节第 2 条），
  故第 5 节的含 LLM 路径必须重新消耗 API 配额才能重跑；重跑结果受模型服务端
  版本变化影响。v0.8.0 重建批带模型指纹（`git_dirty=False`），撤回前的历史
  主批无 `model_fingerprint` 可作对照（第 6 节第 1 条）。
- **可离线复算的只有指标，且以三态披露**：第 4 节的零 LLM 复算链基于已入库
  工件重算（统计扩展 / 引用核验 / SWE-bench 披露 / 重建批 Mut@k 等），不需要
  API Key、不产生新的 LLM 调用；源工件缺席的支路显式 `[SKIP]`——**跳过不等于
  通过**，缺席清单见第 4 节实测读数与 `docs/study/WITHDRAWN_ARTIFACTS_2026-10-24.md`。
- **历史主批次代码树状态不可重建**（`git_dirty = true`，已撤回）：引用其历史
  数字时应同时声明该偏差与"无模型指纹"两条限制（论文中相关数字已标
  historical）。
- 后续补充项：`[待补充：Zenodo DOI / 归档计划]`、
  `[待补充：原始 LLM 响应归档方案（当前不入库）]`。
