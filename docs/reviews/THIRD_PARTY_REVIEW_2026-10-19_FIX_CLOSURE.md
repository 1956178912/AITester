# 第四轮第三方全量静态审查（2026-10-19）20 项修复收口报告

> **性质**：Z 轮（2026-10-19）第三方全量静态审查 20 项（**P0=0 / P1=14 / P2=6**）的修复交付说明与验收记录。
> **评审基线**：第三方报告 `AITester_审查报告(1).md`（Windows 环境，对提交 `55bb711833134f1492cd85c31102f5758dead27e` 的 8,491 文件 / 141,221,102 字节全量静态审查，审查日期 2026-10-19）。本仓修复起点为该提交的后续 HEAD（报告 20 项均按**当前代码**逐项复核；报告中的行号在 Y 轮后已有漂移，一律按内容定位）。
> **复核判定**：报告的 **20 项新增问题全部静态确认**（无 P0；14 项 P1 / 6 项 P2），**0 项误报、0 项降级**；其中 F10/F12/F13/F14 属**条件性触发**缺陷（代码路径确定，历史触发频率未由本轮重放证实），F11 的"官方包端到端"与 F05 的"镜像自包含"保留如实边界（见 §6）。
> **修复花费**：真实 LLM **$0**（全部为代码/文档/工件层修复与零 LLM 验证；未安装新依赖、未联网调用模型）。
> **回归结论**：全量测试 **9338 passed / 5 skipped / 0 failed**（collected 9343；xdist `-n 4 --dist loadfile`）；`make gates` **exit 0**；报告 §M 验收脚本 M1–M9 / M11 复跑通过，M10（官方 CLI 真实包）与 M12（v2 修复率逐行重放）**未执行**并如实登记（§2、§6）。
> **新增回归锁**：`tests/test_review_20261019_{stats,executor,measurement,repro,docs}.py` 共 **138 例**；5 个既有测试文件按新口径更新断言（`test_r14_statistical_protocol.py`、`test_ak_batch.py`、`test_executor_repo_j4_coverage.py`、`test_mdo_metrics.py`、`test_closeout_k_llm_client.py`、`test_base_agent_extended.py`、`test_untrusted_exec_env.py`、`test_an_batch.py`、`test_experiments_scripts.py`）。

## 0. 一句话结论

报告 20 项全部确认并逐项修复：**评估口径错误（BH q / 配对分母）已改为标准算法并全量重算引用值；测量构念缺陷（MDO 断言判别 / Windows 探针 / 负 rc）已实现 fail-closed；执行器错源与官方接口不匹配已修复并加锁；配置/复现/绘图/JSON 与协议文档已同步**。修复后主批三项显著性结论、E2 δ 与修复上限定性结论均不翻转；所有历史原始数据未改写，仅对派生报告与文档加**日期化勘误**。

## 1. 逐项收口矩阵

编号与级别沿用第三方报告；"验证入口"为可复跑命令/测试。所有修复均未触碰原始实验数据（三批/四批 JSON 原字节不变）。

### P1（14 项）

| 编号 | 报告问题 | 确认证据（本轮复核） | 修复内容 | 关键文件 | 验证入口 |
|---|---|---|---|---|---|
| F01 | BH q 值计算错误 | 手算反例三组全部复现（`[0.03,0.20,0.30]` 旧 q 与 rejected 矛盾）；主批 q 应在 `1.77e-25 / 4.27e-12 / 1.81e-7` 量级而非 `6.0e-8 / 1.2e-7` | `bh_fdr_correct` 重写为**标准 BH**：`q_(i)=min(1, min_{j≥i} m·p_(j)/j)`（逆序累积最小、与 α 拒绝位置无关）；step-up 拒绝集合与 nan 语义保留。**全量重算引用**：主批 pooled 表、BASELINE（主批/E6/A1/E6-matched 族）、EVALUATION_SCOPE、preregistration 中英、statistical_report / e2 / e2_iter 日期化勘误、本地论文 `paper/draft.typ`（3 处，PDF 同步重编） | `experiments/statistical_analysis.py`、`BASELINE.yaml`、`docs/EVALUATION_SCOPE.md`、`docs/preregistration*.md`、`experiments/results/main_batch/*.md` | `pytest tests/test_review_20261019_stats.py tests/test_r14_statistical_protocol.py -q`；§2 M1 |
| F02 | 整臂阳性数与配对分母混用 | `sensitivity_bounds` base 行用整臂求和除共同 n；独立复算 aitester–df 共同 n=240、A/B 阳性 38/106、正确经验差 **−0.283333**（旧 −0.329167，偏差 4.5833pp） | 三情形统一经 `_pair_by_task` 同源配对列表取分子/分母（worst/best 先填充再配对）；重生成 `repair_ceiling_report.md`（含 2026-10-19 勘误节），pooled 报告 AK 双界表 base 行同步 −0.329→−0.283 | `experiments/repair_ceiling_analysis.py`、`experiments/results/main_batch/{repair_ceiling_report,statistical_report_3seed_pooled}.md` | `pytest tests/test_review_20261019_stats.py tests/test_ak_batch.py -q`；§2 M2 |
| F03 | 默认配置冲突（模板 false vs README/代码 true） | `.env.example` 活动值 `EXECUTOR_USE_VENV=false` 注释"两者默认 false"；`config.py` 默认 True、README 称 R10 起默认开 | 模板活动值改 **true** 并重写政策注释（`EXECUTOR_AUTO_INSTALL_DEPS` 仍 false）；README.en/api_reference 中英默认值表 false→true；其余同口径表 grep 同步 | `.env.example`、`README.en.md`、`docs/api_reference*.md` | `pytest tests/test_review_20261019_repro.py tests/test_executor_sandbox.py -q` |
| F04 | 资源限额"0=禁用"实为 0 额度 | mock 复现 AS 对应 `setrlimit(...,(0,0))` 实际调用 | 五项逐项 `limit > 0` 才设置；0 = 跳过该项；Darwin 跳过 AS、`env_int(lo=0)`、坏值回退保持 | `src/agents/executor_runtime.py` | `pytest tests/test_review_20261019_executor.py tests/test_s5_darwin_rlimit.py -q`；§2 M7 |
| F05 | 复现镜像前置条件不完整 | `.dockerignore` 排除 `experiments/results`，但 `reproduce.sh` Step3 全量 pytest 依赖该目录 45 个测试文件 | 诚实化（P2 口径）：`REPRODUCE_SKIP_TESTS=1` 显式逃生（默认仍跑测试、fail-closed、跳过时醒目 warn）；Dockerfile.repro / REPLICATION.md / .dockerignore 明确挂载目录**同时是历史输入（测试夹具）与输出**，空目录启动必须显式跳过测试；镜像保持轻量不自包含 | `reproduce.sh`、`Dockerfile.repro`、`.dockerignore`、`REPLICATION.md` | `bash -n reproduce.sh`；`pytest tests/test_review_20261019_repro.py -q` |
| F06 | 绘图静默选旧批结果 | tmp 目录同时放 `benchmark_ult_*`（旧）与 `benchmark_synthetic_*`（新），旧实现选 ult | `load_latest_result(results_dir, dataset, result_path)`：显式路径优先 → `benchmark_{dataset}_` 前缀过滤 → 无匹配 `FileNotFoundError`（不再静默回退）；`main()` 新增 `--result/--dataset`；`reproduce.sh` Step6 传 `--dataset "$DATASET"`；另修复该脚本直接运行时的 `ModuleNotFoundError`（原 Step6 命令实际从未跑通） | `experiments/visualize_results.py`、`reproduce.sh` | `pytest tests/test_review_20261019_repro.py tests/test_visualize_results_b6.py -q` |
| F07 | 数据库异常时 cursor/conn 泄漏 | mock 复现 SQL 异常后 `cursor_closed=False / conn_closed=False` | `init_database` 资源创建后即进入 try/finally，覆盖库名校验+全部 SQL+commit；finally 分项 suppress 关闭；连接失败不二次关闭 | `init_db.py` | `pytest tests/test_review_20261019_executor.py -q`；§2 M9 |
| F08 | 低基线被解释为天花板、定因越界 | narrative 写"~3%（无 flip 空间）""主机制=基线天花板"；CONFIRM_REPORT 实为 replace 6/174、specir 5/174、BF10=0.5/2 → not_confirmed；敏感性数字应为 +8pp→≈24.5（非 +12pp→≈25） | 撤回"基线天花板/信息性真阴性/无 flip 空间"定因，改为如实计数 + **机制未由设计识别** + 替代解释未排除；保留预注册敏感性事实（+8pp≈24.5 / +12pp≈31 / 实测 3）；§0 表格、§1 标题/事实/推论同步；BASELINE note 同口径收缩 | `docs/design/emse_layered_narrative.md`（+ `BASELINE.yaml` note） | `pytest tests/test_review_20261019_docs.py -q` |
| F09 | zai 路径静默忽略 temperature、身份仍记温度 | 签名无 temperature、SDK create 无该键；而缓存身份记录"实际生效温度" | `_call_zai(..., temperature)` 透传 `create(temperature=...)`；调用点传 `eff_temperature`；docstring 固化"身份记录=实际请求"契约 | `src/agents/llm_client.py`、`src/agents/base_agent.py` | `pytest tests/test_review_20261019_measurement.py tests/test_closeout_k_llm_client.py -q`；§2 M11 |
| F10 | 共享 venv 命中旧 commit 跳过重指向 | mock 复现缓存命中 `cached=True / repoint_calls=0`（venv 仍指上一 commit）；同仓库 A→B→A 会导入 B 源码 | 新增 `<venv>/.venv_editable_commit` marker；setup 缓存命中在**仓库级 venv 锁**内校验并按需重指向；verify 持同一锁至验证结束、锁内复核绑定，失败 fail-closed；同时补齐文档承诺但全仓无消费点的 `SWE_REPO_VENV_REUSE_BY_REPO` 接线（`run_benchmark.py`），文档同步为 marker 口径 | `src/agents/executor_repo.py`、`experiments/run_benchmark.py`、`README.md`、`.env.example` | `pytest tests/test_review_20261019_executor.py -q`；§2 M8 |
| F11 | 官方 swebench harness 接口全链不匹配 | 位置参数、预测字段 `patch`、伪造 instance_id、读旁置 `_report.json` 四事实全部确认 | CLI 改官方命名参数（`--dataset_name/--split/--predictions_path/--max_workers/--run_id/--report_dir`）；预测 JSON 用 `instance_id/model_name_or_path/model_patch`；`verify(..., instance_id=...)` 由 `task.metadata["instance_id"]` 透传；递归解析官方 per-instance report（`resolved` + `tests_status.*.success`）；缺 ID/坏 schema/rc≠0 一律日志+降级不假过；docstring 明示官方版本未锁定 | `src/agents/executor_repo.py`、`experiments/run_benchmark.py` | `pytest tests/test_executor_repo_j4_coverage.py tests/test_review_20261019_executor.py -q`；M10 未执行边界见 §6 |
| F12 | `rc==1` 无差别当断言失败 → 无断言异常也产 MDR | 报告最小反例 mock 复现（29 个运行异常变异体 `mtr=1/mdr=1/crash=0`） | 主路径：tmp 目录零依赖 `conftest.py` 用 `pytest_exception_interact` 记录 call 阶段失败异常类型；仅"全部失败均为断言型（AssertionError / Failed / DID NOT RAISE）"计断言判别；纯运行异常记 CRASH（MDR 不增）；无 JSON 时回退 `-rf/--tb=short` 解析，仍不能证明断言则保守不计判别 | `src/measurement/mdo.py` | `pytest tests/test_review_20261019_measurement.py tests/test_mdo_metrics.py -q`；§2 M5 |
| F13 | Windows 探针失效被当相同行为 → measured 伪零值 | 探针硬依赖 `SIGALRM/setitimer/ITIMER_REAL`；父进程只比较 stdout | (a) 探针源码能力守卫，缺 API 即输出 `probe_unsupported` 退出；(b) `_run_probe` 校验 schema（必须含 `calls: list`），拒绝 `probe_error/import_error/probe_unsupported`/非 JSON；(c) base 探针无效→not_measurable，单变异体无效→排除分母，全无效→不可测；新增 `mdo_probe_invalid` 披露 | `src/measurement/mdo.py` | `pytest tests/test_review_20261019_measurement.py tests/test_mdo_metrics.py -q`；§2 M6（fake-signal 模拟） |
| F14 | 负 rc 穿守卫 → 异常终止可计阳性检出 | `_looks_like_test_execution_error(-15,'')` 返回 False；`buggy=-15 ∧ fixed=0` 落 `return 1.0` | 负 rc（POSIX 信号终止）一律判异常终止/执行错误，docstring 固化语义；detection 记 0.0（非阳性）、test_error_rate=1.0、oracle/gates=unavailable；全部消费方同源 | `experiments/_m1_metrics.py` | `pytest tests/test_review_20261019_measurement.py tests/test_m1_metric_semantics.py -q`；§2 M4 |

### P2（6 项）

| 编号 | 报告问题 | 确认证据 | 修复内容 | 关键文件 | 验证入口 |
|---|---|---|---|---|---|
| F15 | 终态被当作有效检出充分条件 | `algorithm_design` 中英 + ADR-0015 写"`red_not_repaired` 计检出"；同文 F2P 三段判据与 88 行过红反例矛盾 | 明确 `red_not_repaired` 只是**协议层机制状态**（算法伪码 `detection=red_seen` 同为协议层信号），**不构成有效检出充分条件**；有效检出始终由评估层独立 F2P 裁决；88 行过红 `detection=0` 列为反例，不得改判分迎合文字 | `docs/algorithm_design*.md`、`docs/adr/0015-detection-first-protocol.md` | `pytest tests/test_review_20261019_docs.py -q` |
| F16 | 主设计仍以多智能体协作为主定位（ADR-0016 违规） | 中英标题/首句仍为"多智能体协作…" | 标题改《检出优先的测试生成与修复归因评估协议》；首句重定位为"检出优先协议 + 多智能体编排=可消融容器"（架构事实保留）；§4 标题同步 | `docs/algorithm_design.md`、`docs/algorithm_design.en.md` | `pytest tests/test_review_20261019_docs.py -q`；`make docs-check` |
| F17 | 引用核验状态更正未传播 | VALIDITY 中英 3 处仍称 ADR-0025"未一手核验"；范围文档仍称 allowlist"4 处待核验" | 改为"2026-10-16 已一手核验（DOI/13,866 预言/135 Java 项目/43% vs 45% 与摘要吻合）；allowlist 已清空零豁免"，保留 Java→Python 外推限制与仍属未核验的 claude-code 聚合数字（拆条表述） | `docs/VALIDITY.md`、`docs/VALIDITY.en.md`、`docs/EVALUATION_SCOPE.md` | `pytest tests/test_review_20261019_docs.py -q` |
| F18 | 数据卡把旧实验标为"当前主批次" | DATA_CARD 仍写 n=50 / seed42 为当前主批；当前确认性主批实为 87×3 seeds×3 臂 | 拆"历史主批（n=50/seed42）"与"当前确认性主批（87 任务 × 3 seeds {42,43,44} × 3 臂 = 261 行/臂，`--max-pattern-repeat 2`）"；明写 50 是模板库唯一 pattern 数/历史主批任务数；中英同步 | `docs/DATA_CARD.md`、`docs/DATA_CARD.en.md` | `pytest tests/test_review_20261019_docs.py tests/test_an_batch.py -q` |
| F19 | 裸 `Infinity` 非标准 JSON | `recompute_outputs.json:93` `"odds_ratio": Infinity` | c=0 时 `odds_ratio=None` + `odds_ratio_note`；写盘 `allow_nan=False`；脚本重跑重生成工件（diff 仅时间戳 + 该 4 块）；SHA256SUMS 同步 | `docs/reviews/review_recompute/{recompute_core_claims.py,recompute_outputs.json,SHA256SUMS}` | `pytest tests/test_review_20261019_repro.py tests/test_emse_recompute_entrypoints.py -q`；§2 M3 |
| F20 | 严格匹配条件与比较总体交代不全 | 代码实际严格键为 `(pattern,difficulty,seed)`；文档只写 pattern×seed；strict 0/25 后接 loose 互补 38/185 未说明非互补 | 写全三字段键并分别给出两组互补总体：strict 29 行/25 可测（互补 232 行/215 可测，38/215=17.67%）与 loose 62/55（互补 199/185，38/185=20.54%）；明确 strict/loose 是不同总体、非互补对照，保留描述性限定 | `docs/EVALUATION_SCOPE.md`、`docs/VALIDITY.md`、`docs/VALIDITY.en.md` | `pytest tests/test_review_20261019_docs.py tests/test_review_20261019_stats.py -q` |

## 2. 报告 §M 验收脚本复跑（修复前 → 修复后）

除说明外均为本机 macOS 3.14 / `.venv` 实跑；所有脚本未触发 LLM、未改生产数据。

| 验收 | 修复前实测 | 修复后实测 | 结论 |
|---|---|---|---|
| M1 BH q | `bh_fdr_correct([0.01,0.02,0.20])` → q=`[0.01,0.02,1]`；`[0.03,0.2,0.3]` → q 与 rejected 矛盾 | q=`[0.03,0.03,0.20]`；`[0.09,0.30,0.30]`；`[0.003,0.0075,0.02]`，与报告手算表逐位一致 | ✅ 闭合 |
| M2 主批配对 | 报告值可复算：n=240、`26/12/80/122`、经验差 −0.283333、后验 −0.278689（E2 `16/4/58/65`、−0.3673469） | 同左，独立脚本复算逐位一致 | ✅ 报告值确认 |
| M3 严格 JSON | `ValueError: nonstandard JSON token: Infinity` | `parse_constant=raise` 通过；无 `Infinity/NaN` token | ✅ 闭合 |
| M4 负 rc 守卫 | `_looks_like_test_execution_error(-15,'') = False` | `True`；`buggy=(-15) ∧ fixed=0` 端到端 detection=0.0、test_error_rate=1.0、gate=unavailable | ✅ 闭合 |
| M5 MDO 运行异常 | mock 29 个运行异常变异体 → `measured / mtr=1 / mdr=1 / crash=0` | 同 mock（探针 schema 合法）→ `mtr=1 / mdr=0 / crash=1`；若探针输出非 JSON 则直接 not_measurable（更严格 fail-closed） | ✅ 闭合 |
| M6 Windows 探针 | —（macOS 有 SIGALRM，静态确认 Windows 无三 API；报告预期两次相同 `probe_error`） | fake-signal 子进程模拟（无 SIGALRM/setitimer）→ `probe_unsupported` → `_run_probe` 返回 None → not_measurable；真实 Windows 未实跑（§6） | ✅ 代码面闭合，平台边界如实 |
| M7 0 资源限额 | mock 捕获到 AS `(0,0)` 调用 | 0 项不再产生 setrlimit 调用；正值项仍设置（4 项，Darwin 跳过 AS） | ✅ 闭合 |
| M8 共享 venv 缓存命中 | `cached=True / repoint_calls=0` | `cached=True / repoint_calls=1`（marker 不一致时重指向；同 commit 命中为 0） | ✅ 闭合 |
| M9 建库异常清理 | `cursor_closed=False / conn_closed=False` | `True / True` | ✅ 闭合 |
| M10 官方 CLI 契约 | 本机无 `swebench` 包（`ModuleNotFoundError`），无法调用真实 CLI | 代码改为官方命名参数 + 官方 predictions/report schema（契约测试 mock 覆盖）；**真实包/Docker 未验收** | ⚠️ 代码面修复，真实包边界见 §6 |
| M11 zai 参数 | `_call_zai` 签名无 temperature，SDK 请求无该键 | 签名含 `temperature`；mock 调用级断言 SDK 收到该键，且 base_agent 传 `eff_temperature` | ✅ 闭合 |
| M12 v2 修复率重放 | 未执行（需真实 pytest 逐行重放 261 行，报告亦未执行） | **未执行**（与本轮修复无耦合；边界见 §6） | ⏸ 保留人工项 |

## 3. 独立复算与真值（Lead 复核）

| 项 | 独立复算结果 | 与报告/修复后文档 |
|---|---|---|
| 主批三比较 p / 标准 BH q | p=`5.890715e-26 / 2.843839e-12 / 1.811017e-7` → q=`1.767215e-25 / 4.265758e-12 / 1.811017e-7` | 逐位一致 |
| E6/A1 家族（m=3） | p=`[0.4795001, 3.814478e-5, 0.0133283]` → q=`[0.479500, 1.144343e-4, 1.999249e-2]` | 与 BASELINE/preregistration 修正值一致 |
| E6 matched 主端点（m=2） | `df(matched) vs aitester(std)`：n=86、b/c=18/1、χ²=13.473684、p=2.4193279e-4；同族 p=0.4795001 → q=`[0.00048387, 0.4795001]` → 4dp `[0.0005, 0.4795]` | BASELINE + prereg 一致 |
| F02 主批配对 | 共同 n=240、A 阳性 38、B 阳性 **106**（整臂为 117）→ 经验差 **−0.283333**；aitester–plain +0.141667；df–plain +0.432950（n=261） | 与重生成报告/勘误一致 |
| F20 strict/loose | aitester 261 行/240 可测/38 检出；strict 29 行/25 可测/0；loose 62/55/0；strict 互补 232/215、38/215=17.6744%；loose 互补 199/185、38/185=20.5405% | 与修复后文档一致 |
| F19 严格 JSON | `json.loads(..., parse_constant=raise)` 通过；工件 SHA256SUMS 8 行全部校验通过 | 闭合 |

## 4. 回归锁与既有测试更新

| 新回归锁 | 用例数 | 覆盖 |
|---|---:|---|
| `tests/test_review_20261019_stats.py` | 16 | BH 三反例 + α 无关性 + nan 不变量；主批 p/q 从原始 JSON 独立重建；F02 最小反例 + 真实主批配对；E6/A1 族 q + BASELINE 一致性；F20 strict/loose 复算 + 文档一致 |
| `tests/test_review_20261019_executor.py` | 41 | F04 0=跳过（含 Darwin AS 兜底）；F07 三条异常清理路径；F10 marker/锁/同 commit 零重指向/verify fail-closed/SWE_REPO_VENV_REUSE_BY_REPO 接线；F11 官方参数契约 + 官方 report schema 解析 + 缺 ID/坏 schema/rc≠0 降级 |
| `tests/test_review_20261019_measurement.py` | 38 | F09 调用级 SDK 温度 + 身份契约；F12 §M5 反例 + 真实 pytest 端到端（无断言 ValueError vs 真断言）+ 分类回退；F13 §M6 fake-signal/全无效/单无效排除；F14 §M4 + 端到端 detection/gate 一致 |
| `tests/test_review_20261019_repro.py` | 27 | F03 模板/文档默认值；F05 `REPRODUCE_SKIP_TESTS` 与镜像挂载语义静态锁；F06 dataset 过滤/显式路径/无匹配报错；F19 严格 JSON 与 `odds_ratio=None` 契约 |
| `tests/test_review_20261019_docs.py` | 16 | F08/F15/F16/F17/F18/F20 的"错误句不存在 + 修正句存在 + 中英日期同步" |
| **合计** | **138** | |

既有测试按新口径更新断言（不加宽松豁免、不削弱覆盖）：`test_r14_statistical_protocol.py`（标准 BH q 真值）、`test_ak_batch.py`（配对分子不变式）、`test_executor_repo_j4_coverage.py`（官方 report 真实 schema，替代原自 mock 假 schema）、`test_mdo_metrics.py`（运行异常=CRASH、坏变异体=not_measurable）、`test_closeout_k_llm_client.py` / `test_base_agent_extended.py`（zai temperature 调用级）、`test_untrusted_exec_env.py`（探针 schema 收紧后返回 None，凭证断言不变）、`test_an_batch.py`（DATA_CARD 日期哨兵）、`test_experiments_scripts.py`（F06 无回退行为）。

**连带修复（验证中发现，非评审编号）**：① `tests/test_e2e_probes_platform.py` 的 fake embedding 用内置 `hash()`，受 `PYTHONHASHSEED` 随机化影响在全量 xdist 下偶发"无关 prompt 误命中"（实测复现 1/10 文件级运行）；改为 sha256 派生维度后 25 次复跑 0 失败。② `make gates` 的 `ruff format --check` 在全仓发现 7 个未格式化文件，其中 4 个在 HEAD 即未格式化（`scripts/tools/audit_fix_coverage.py`、`tests/test_fix_coverage_audit_2026_10_19.py`、`tests/test_run_benchmark.py`、`tests/test_trace_jsonl_integrity.py`，系此前轮次未跑全门禁遗留），连同本轮 3 个文件（`experiments/visualize_results.py`、`tests/test_review_20261019_docs.py`、`tests/test_review_20261019_repro.py`）一并用 ruff 0.16.3 格式化，**零逻辑变更**，使格式门禁全绿。

## 5. 门禁与历史更正纪律

| 项目 | 结果 |
|---|---|
| 全量测试 | **9338 passed / 5 skipped / 0 failed**（collected 9343；xdist `-n 4 --dist loadfile`；最终 test-cov 全量 185.1s，`make gates` 内 test 181.0s） |
| `make gates` | **exit 0**（lint / format / mypy / test / docs-check / env-budget / baseline-check / state-contract / env-snapshot / model-fingerprint / tool-versions / json-contract-sites / artifact-doc-consistency / zero-assert） |
| `make docs-check` | 双语文档 strict + 链接 strict 通过 |
| 基线/工件门禁 | `check_baseline.py` / `check_baseline_numbers.py` / `check_artifact_doc_consistency.py` / `check_artifacts_tracked.py` 通过 |
| 证据链 | 全仓 `SHA256SUMS` 校验通过（本轮修改的 5 个 main_batch 报告 + `review_recompute` 脚本/输出行已同步；E7 本地待提交条目保留原位） |
| 覆盖率（本地 macOS 3.14） | 行 **96.58%**（18173/18817）/ 分支 **92.84%**（6525/7028）；ratchet 水位 96.4 / 92.5，余量 +0.18pp / +0.34pp |

**历史更正纪律**：原始批次 JSON 与其他实验原始数据**未改写**。对派生报告（pooled / repair_ceiling / statistical_report / e2 / e2_iter）与现行文档一律采用**日期化勘误**（保留旧值 + 注明 2026-10-19 修正值与原因）；`paper/` 为本地未入库投稿件，`draft.typ` 三处 q 同步修正并用 venv 内 typst-py 重编 PDF（PDF 未入库）。

## 6. 残余风险与未闭环边界

1. **条件性缺陷的历史触发频率未重放**：F10（共享 venv + `venv_reuse_by_repo` + A→B→A）、F12/F13（运行异常 rc=1 与 Windows 探针）、F14（负 rc）的代码路径已确定并修复，但归档历史批次是否实际命中需按 §M12 类重放才能量化；本轮**不据此改写任何历史数字**。
2. **F11 官方 harness 的真实包验收未执行**：本机无网络、无 Docker，未安装 `swebench`；CLI/预测 schema/报告 schema 均按官方 main 分支接口静态核对并用 mock 契约测试锁定。官方接口若再变更，该路径会因 rc≠0/报告缺失而降级自建口径（**不会假过**），但"真实包端到端可跑"仍待有网/Docker 环境验收；数据集名默认假设 `SWE-bench/SWE-bench_Lite`（可经函数参数/模块常量覆写）。
3. **F05 镜像仍不自包含**：设计上不把 125MB 历史归档打进镜像；空目录启动必须显式 `REPRODUCE_SKIP_TESTS=1`。本轮未真实构建镜像。
4. **F13 的 Windows 端到端未实跑**（macOS 无真实 Windows；用 fake-signal 子进程模拟 + 静态能力守卫验证）；F12 的 `conftest` 钩子依赖 pytest 稳定 API（9.1.1 实测），若测试进程被 `os._exit`/硬崩溃则回退 `-rf` 摘要解析（已测），极端文本误判方向为"少记不误记"。
5. **M10 / M12 未执行**：官方 CLI 真实包与 v2 修复率（57/145、58/106）逐行 pytest 重放均登记为人工后续项（报告 §M 同口径）。
6. **平台/内核边界**：Linux `setrlimit` 真实内核效果未在 Linux 实测（仅 mock 调用面 + Darwin 既有兜底回归）；真实 zai 端点未调用（mock + 已安装 SDK 0.2.3 签名静态核对；`TEMPERATURE` 取值域 >1 时 zai 侧接受行为未验证，修复前该参数被静默忽略）。
7. **报告 §L 的 18 组已披露未闭环事项不受本轮影响**（历史 flaky 不重判、原始 LLM 响应未归档、E7 未执行等），继续按原披露边界引用。
8. **本地未入库材料未全量同步**：`.private/`、`.workbuddy/` 记忆、`docs/emse/` 未入库投稿/预注册件中的旧 q 值与旧 BH 描述未改（不属仓库审查面）；`check_citations --traceability` 的 4 处既有数字型外链缺口（`docs/PROJECT_STATUS_REGISTER.md`）非本报告 20 项、未在本轮处理。
9. **`experiments/analyze_results.py::load_latest_benchmark` 仍保留旧的"无 benchmark 回退全量"行为**：报告 F06 只指 `visualize_results`，本轮未扩大改动面；主复现入口已走显式 `--dataset` 口径。

## 7. 与报告 §P 优先修复 Top 5 的对应

| 报告优先级 | 编号 | 状态 | 验证 |
|---|---|---|---|
| 1 | F14 负 rc / 异常进程终止 | ✅ 修复 | §M4；measurement 回归锁 |
| 2 | F12、F13 MDO 构念与不可测状态 | ✅ 修复（fail-closed） | §M5/M6；measurement 回归锁 |
| 3 | F10 共享 venv 错源 | ✅ 修复（marker+锁+fail-closed） | §M8；executor 回归锁 |
| 4 | F02 配对分母 | ✅ 修复（−0.283333 + 勘误） | §M2；stats 回归锁 |
| 5 | F01 BH q | ✅ 修复（标准 BH + 全量重算） | §M1；stats 回归锁 |

F03 配置默认、F06 绘图来源、F08 机制解释亦已按报告建议在本次收口（§1）。

## 附录 A：报告问题 → 修复文件 / 回归锁

| 编号 | 修复文件 | 回归锁 |
|---|---|---|
| F01 | `experiments/statistical_analysis.py`、`BASELINE.yaml`、`docs/EVALUATION_SCOPE.md`、`docs/preregistration*.md`、`experiments/results/main_batch/*.md`、`paper/draft.typ` | `test_review_20261019_stats.py`、`test_r14_statistical_protocol.py` |
| F02 | `experiments/repair_ceiling_analysis.py`、`main_batch/repair_ceiling_report.md`、`main_batch/statistical_report_3seed_pooled.md` | `test_review_20261019_stats.py`、`test_ak_batch.py` |
| F03 | `.env.example`、`README.en.md`、`docs/api_reference*.md` | `test_review_20261019_repro.py` |
| F04 | `src/agents/executor_runtime.py` | `test_review_20261019_executor.py`、`test_s5_darwin_rlimit.py` |
| F05 | `reproduce.sh`、`Dockerfile.repro`、`.dockerignore`、`REPLICATION.md` | `test_review_20261019_repro.py` |
| F06 | `experiments/visualize_results.py`、`reproduce.sh` | `test_review_20261019_repro.py`、`test_visualize_results_b6.py`、`test_experiments_scripts.py` |
| F07 | `init_db.py` | `test_review_20261019_executor.py` |
| F08 | `docs/design/emse_layered_narrative.md`、`BASELINE.yaml`（note） | `test_review_20261019_docs.py` |
| F09 | `src/agents/llm_client.py`、`src/agents/base_agent.py` | `test_review_20261019_measurement.py`、`test_closeout_k_llm_client.py`、`test_base_agent_extended.py` |
| F10 | `src/agents/executor_repo.py`、`experiments/run_benchmark.py`、`README.md`、`.env.example` | `test_review_20261019_executor.py` |
| F11 | `src/agents/executor_repo.py`、`experiments/run_benchmark.py` | `test_review_20261019_executor.py`、`test_executor_repo_j4_coverage.py` |
| F12/F13 | `src/measurement/mdo.py` | `test_review_20261019_measurement.py`、`test_mdo_metrics.py` |
| F14 | `experiments/_m1_metrics.py` | `test_review_20261019_measurement.py`、`test_m1_metric_semantics.py` |
| F15/F16 | `docs/algorithm_design*.md`、`docs/adr/0015-detection-first-protocol.md` | `test_review_20261019_docs.py` |
| F17 | `docs/VALIDITY*.md`、`docs/EVALUATION_SCOPE.md` | `test_review_20261019_docs.py` |
| F18 | `docs/DATA_CARD*.md` | `test_review_20261019_docs.py`、`test_an_batch.py` |
| F19 | `docs/reviews/review_recompute/{recompute_core_claims.py,recompute_outputs.json,SHA256SUMS}` | `test_review_20261019_repro.py`、`test_emse_recompute_entrypoints.py` |
| F20 | `docs/EVALUATION_SCOPE.md`、`docs/VALIDITY*.md` | `test_review_20261019_docs.py`、`test_review_20261019_stats.py` |

## 附录 B：本轮校验命令清单

```bash
# 专项回归锁（5 个新文件，零 LLM）
.venv/bin/python -m pytest tests/test_review_20261019_stats.py tests/test_review_20261019_executor.py \
  tests/test_review_20261019_measurement.py tests/test_review_20261019_repro.py \
  tests/test_review_20261019_docs.py -q

# 全量门禁（CI 同口径）
make gates

# 报告 §M 验收脚本（修复后）
python -B -c "from experiments.statistical_analysis import bh_fdr_correct; print(bh_fdr_correct([0.03,0.2,0.3]))"
python -B -c "import json,pathlib; json.loads(pathlib.Path('docs/reviews/review_recompute/recompute_outputs.json').read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))"
python -B -c "import experiments._m1_metrics as m; print(m._looks_like_test_execution_error(-15,''))"
```
