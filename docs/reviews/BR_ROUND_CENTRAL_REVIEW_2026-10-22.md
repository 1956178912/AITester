# BR 轮：第三方集中复审 27 项收口（零 LLM，$0）

> 对象：`AITester_集中复审报告_2026-10-21.md`（第三方，Windows，报告 HEAD
> `53bbbbd4`，比较基线 `388dbf9f`）。收口时仓库 HEAD 为 `f49959b2`（中间已有
> BD→BP、BQ 两批修复），本轮**逐项在收口 HEAD 上复核**，不沿用报告的静态快照。
> 结论：**27/27 全部确认为真（P1=14 / P2=13，P0=0），零误报、零撤回**；报告 M 节的构造反例与复算项在收口 HEAD 上逐位复现（N03/N04/N05/N06/N07/N10/N02-B/N11/F04/F07/F15/F16）。

## 1. 结论与口径

| 维度 | 结果 |
|---|---|
| 确定问题 | 27（N01–N11 新增/遗漏消费点 11；F04–F10、F14–F20 上轮遗留 16） |
| 本轮修复 | 27（代码/流程 18、文档/引用/契约 9） |
| 报告误报 | 0 |
| 新增回归锁 | 77 例（5 个 BR 文件 + 2 处既有契约改写，逐文件见 §3） |
| 全量回归 | collected **12069** = passed **12064** + skipped 5 + failed 0（规范口径）；本会话沙箱确认跑 **12050 passed / 19 skipped / 0 failed、537.77s、rc=0** |
| 门禁 | `check_baseline_numbers` / `check_doc_links` / `check_bilingual_docs` / `check_citations` / `check_artifact_doc_consistency` / `check_zero_assert_tests` / `check_env_budget` / `check_baseline` / `check_ast_parse_guards` 全绿 |

沙箱 19 skip = 规范 5 + 14 环境能力缺失（与 BP/BQ 同口径，不混用）。

## 2. 逐项处置矩阵

级别按报告；"处置"列给出改动后的行为，不写"已修复"式声明。

### 2.1 N 系列（本轮新增/遗漏消费点）

| 编号 | 级别 | 根因（报告） | 处置 | 锁定 | 边界 |
|---|---|---|---|---|---|
| N01 | P1 | 探针在隔离拒绝/更强隔离之后回宿主 `sys.executable` 重执行 | `capture_failure_snapshot(backend=...)`：仅 `local`/`venv` 放行，`docker`/`kernel`/`refused`/`unknown` 一律不启动子进程；`nodes._runtime_probe_backend` 从 `error_info.type` 与执行器实态推导档位，trace 记 `probe_blocked` | `test_br_round_runtime_contracts.py::TestProbeIsolationGuard`（5 后端 × 不启动子进程 + local 对照） | 未跑真实 Docker/Seatbelt；按调用链静态定档，动态隔离未验证 |
| N02 | P1 | 坏 token 记账的拒绝只查 env 开关：重试继续、实例 cap 被跳过 | 新增 `budget_effective()`（env **或** cap>0）与 `mark_budget_exceeded()`；拒绝时锁存 `budget.exceeded` 并抛 `BudgetAccountingError(BudgetExceededError)`；OpenAI/zai 两条重试链把预算异常列入 `non_retryable_exceptions`；`_record_response_usage` 的宽 `except` 显式放行预算异常 | `test_br_round_budget_accounting.py` 11 例（两分支、重试链 invoke 只 1 次、锁存后 0 次） | 未证明历史调用已触发；未跑真实 provider |
| N03 | P1 | E7 按候选号合并，不校验同号 task_id，完全相反的两表可算 κ=1.0 | 新增 `identity_conflicts()`；`merge_sheets` 在 `align_pairs` 前拒绝身份冲突（缺 task_id 也算冲突）；`candidates` 抽样清单可选传入 `validate_entry_rows`；C 表改为**先校验再算 κ** | `test_br_round_stats_contracts.py::TestE7Identity` 4 例（互换拒绝、一致 κ=-1、缺 id 拒绝、清单绑定） | E7 人工裁决仍未执行；本轮不产生任何人工信度结论 |
| N04 | P1 | 缺归因行进入总量后被其他行单价补齐；扩展路径整臂相抵过关 | 路径 A：正 token 缺归因 ⇒ 全额 `cost=None` + `attribution_missing_rows:N`，可归因小计落 `attributed_cost`/`attributed_cost_scope`；路径 B：`_read_tokens` 逐行校验 `by_model` 闭合（空 `{}` 仍归"无归因"臂级披露） | 同文件 `TestCostAttribution` 3 例（缺归因阻断、完整归因计价不变、逐行相抵不过关） | 归档 131 个 results 臂未发现相抵组合；历史金额未重算、未改写 |
| N05 | P1 | `paired_contrast` 先排 None 再 setdefault，旧可测值顶替最新 None | 改用共享 `latest_rows_by_task`：先选最新行，再单独排除 None | 同文件 `TestPairedLatestRows` 2 例（n=2/δ=+50pp） | 主三 seed 每题唯一，未声称 AZ 工件受影响 |
| N06 | P2 | 非 0.5 精确二项用裸浮点比较，并列概率被排除 | 对数域 + **相对**容差（log 1e-12）+ logsumexp；全结局入选直接返回 1.0；p∈{0,1} 边界显式 | 同文件 `TestBinomialTies` 4 例（含 p=.5 尾部逐位不变） | McNemar 生产实参 p=.5 走整数权重分支，不受影响 |
| N07 | P2 | 零基线 MDE 在退化端点判"检不出"，返回 nan | `power_paired` 区分 δ=0（返回 α）与 σ²≤0（返回 0）；`detectable_delta_paired` 在端点失败时先复核有效内部点再二分 | 同文件 `TestZeroBaselineMDE` 4 例（MDE=.0727765、功效=.8、真不足仍 nan） | 报告主口径为闭式 MDE，本项仅二分交叉核对字段 |
| N08 | P2 | 标准 `---/+++` diff 与 difflib fallback 被当完整源码拒绝 | `_looks_like_unified_diff` 识别相邻成对文件头；`_normalize_unified_headers` 给裸路径补 a//b/（只改文件头，hunk 内容行不动）；`_diff_codes` fallback 产出带前缀路径 | `test_br_round_patch_contracts.py::TestUnifiedDiffRecognition` 11 例 | 未在真实 SWE-bench 仓库重放；只保证识别与路径形状 |
| N09 | P2 | 探针只留最内层一帧且父进程只许探针文件帧，目标模块异常帧被清空 | runner 保留完整异常链（≤3 帧）；父进程按 **probe 文件 + 真实 target_file/模块名** 选帧 | 同文件 `TestProbeFrameSelection` 2 例（foo.py 帧保留、无关帧仍过滤） | pytest fixture/parametrize 未重放（报告同族语义偏差），仍按直接调用 `test_*` 采集 |
| N10 | P2 | 合法非对象 JSONL 行（`null`/`[]`/`0`/`false`/字符串）让整文件导出崩溃 | 解析后校验 dict 形状；非对象行跳过并带行号 + 类型 warning，其余记录照常导出 | 同文件 `TestOtelNonObjectRecords` 5 例 | 归档 6892 份 trace 未发现非对象行；未重放全部 trace |
| N11 | P2 | 并发专家共享任务账本，缓存用总量差分把别人的消耗算进本次 | 新增调用作用域 `begin_call_scope`/`call_scope_tokens`/`call_scope_had_rejection`（线程局部）；`record_usage` 同点累加；`_call_llm_with_cache` 改用作用域，任务总账不变 | 同文件 `TestCallScopeIsolation` 3 例（两线程 barrier 交错 → 10/20，总账 30） | 未跑真实专家池线程调度；数学交错不等于历史污染计数 |

### 2.2 F 系列（上轮遗留）

| 编号 | 级别 | 处置 | 锁定/证据 |
|---|---|---|---|
| F04 | P1 | `auto_fix_imports` 的 sys.path 前缀插到 docstring 与 `__future__` 之后（`_insert_sys_path_prefix`，AST 定界 + 共享 `AST_UNREADABLE_ERRORS`） | `test_br_round_patch_contracts.py::TestSysPathInsertion` 3 例（future 仍第一、docstring 不被顶掉、可编译） |
| F05 | P1 | P2P 基线改为**补丁前**测量；补丁后 P2P 只判回归（`passed=False`），M3 门禁只看基线；输出/结果行同时给 baseline 与 after | 同文件 `TestP2PBaselineSplit` 2 例（2/2→1/2 不判 harness_invalid；基线 1/2 仍判） |
| F06 | P1 | pass@k 分组键改为稳定程序身份（`task_metadata.fixed` SHA256）；无内容身份时退回"同批 task_id"（`_batch_tag` 由加载层写入）；披露 `identity_basis` | `test_br_round_loading_cli.py::TestPassAtKIdentity` 3 例（同号不同程序 → 2 题；同程序跨批 → 轮次 2；无身份 → 跨批不合并） |
| F07 | P1 | 批次加载先完整装配再一次性提交；非列表/非对象行直接报错，**零提交**且不登记来源 | 同文件 `TestAtomicBatchLoad` 3 例（后臂坏 → 前臂 0 行；健康批照常） |
| F08 | P1 | 发布绿门改查 `actions/workflows/ci.yml/runs?head_sha=`，要求 completed+success 且作业全成功；排除自身 in_progress；补 `actions: read` | 同文件 `TestReleaseGreenGate`（静态契约：无 `/commits/` 查询、有 SHA 与 workflow 限定）；未打 tag 实跑 |
| F09 | P1 | ICST'26 数字改**相对 HITS 的 17.72%/19.80%/20.92%**（绝对 +7.52/+5.84/+5.85pp）；ADR0030、设计文档、citation_allowlist 三处同步 | 一手核验 arXiv:2601.09695v2 表 II + 摘要 |
| F10 | P1 | ADR0030 删去"手工编排已不被前沿视为价值来源"的领域判断，改为逐研究限定 + 指回 `EVALUATION_SCOPE` C10 | 同段改写（无新增引用） |
| F11 | P2 | JSON 模式异常任务也输出一行错误 JSON（`_append_task_error` 单一入口，并行/串行共用） | `test_br_round_loading_cli.py::TestCliJsonErrorLine` 3 例 |
| F12 | P2 | 删除 `ALLOW_UNSANDBOXED` 的"恢复指引"：`.env.example` 明写设了也不会让任务跑起来，执行器/内核沙箱提示改为补后端或走 Docker | 同文件 `TestUnsandboxedGuidance` 2 例 |
| F14 | P2 | 分发范围改为**按字段**说明：`task_metadata.fixed` / `test_cases` 内嵌上游原文（附 QuixBugs 哈希实例），其余为派生；两份许可文档同步 | 本地复验 `benchmark_quixbugs_20261009_215514.json` 的 `test_cases` 为上游 gold（1868 字符） |
| F15 | P2 | df 成本比 **6.2×**（26,115/4,223）；8.1× 只保留给 plain 对照；中英预注册 + ADR0030 + ADR 索引四处同步 | 直接算术复算 6.183992 |
| F16 | P2 | n=41 界限改 **7.3 / 8.6 / 12.6%**；41/72 改 **56.9%**；协议与澄清文档同步 | Wilson/rule-of-three 复算（7.3171 / 8.5670 / 12.5953） |
| F17 | P2 | 复现说明删掉"87 vs n=50 待对账"占位，改为已澄清事实（50 pattern / 87 任务 / n=50 为历史主批） | `DATA_CARD.md:21` 现行文本 |
| F18 | P2 | CANDOR 改 **v7 ≥21.1pp vs TOGLL**；15.8–25.1 标注为 v3 vs LLM-Empirical；两处表格 + 日期化勘误 | 一手核验 arXiv:2506.02943v7 摘要原文 |
| F19 | P1 | 口径矩阵定义改 `false_fix_rate is not None`（240 行），并登记 261 vs 240 的 4.79pp 差异来源（21 行整任务死亡） | 代码 `false_fix_caliber()` + 定案表对齐 |
| F20 | P1 | 双语文档按真实签名：`execute(test_code, target_file)`、`result["passed"]`、`find_missing_modules(set[str])`、`install_packages → (bool, str)`、`token_usage.reset()` 模块级、`BenchmarkTask` 属性访问 | `inspect.signature` 实测 + `hasattr` 核验 |

## 3. 提交划分

| 批次 | 内容 |
|---|---|
| ① 代码 + 测试 | N01–N11、F04–F07、F11、F12、F19 的代码/测试面；新增 `tests/test_br_round_{runtime,stats,patch,budget,loading}_*.py` 5 个文件 77 例；两处既有契约按新口径改写（AM 两条"unattributed 不阻断"→"阻断并给小计"、BK 站点读数 78→79 附理由） |
| ② 发布流程 | `.github/workflows/release.yml` 的 ci-green 作业（F08） |
| ③ 文档/引用 | F09、F10、F14–F18、F19 文档定义、F20 双语 API/示例；并同步 BASELINE/README/CHANGELOG/INDEX |

## 4. 验证

- **构造反例（报告 M 节）**：N03 κ=1.0、N04 $0.0002、N05 n=3/δ=0、N06 .5904、N07 nan、N10 AttributeError、N02-B allowed=True 全部在修复前复现、修复后按预期改变；N11 real=30/avoided=40 → 10/20。
- **变异抽查（3/3 红）**：关闭 E7 身份闸（`if False and conflicts`）→ `TestE7Identity` 红；取消缺归因阻断（`money_readable` 不复位）→ `TestCostAttribution` 红；关闭有效预算判定（`if False`）→ `TestRecordResponseUsageRefusal` 红。三处改回后 sha256 与改前一致（`e7_adjudication` / `statistical_analysis` / `llm_client`），无残留。
- **全量**：见 §1；失败 0。
- **门禁**：见 §1；`check_ast_parse_guards` 站点 78→79（新增站点直接吃 `AST_UNREADABLE_ERRORS`，EXEMPT 与命中数不变）。
- **未做**：真实 Docker/Seatbelt/bwrap 动态隔离、真实 provider 重试链、E7 人工裁决、tag 发布实跑、全部 trace/生成测试重放、法律侵权判定。以上均按报告 §N 的盲区声明保留，不用静态结论冒充动态验证。

## 5. 残余与后续

1. **N09 的 pytest 语义**：仍以直接调用 `test_*` 采集，不重放 fixture/parametrize；报告已列为同族偏差，登记为已知限制。
2. **F05 的批量影响**：主 runner 另有前置 P2P gate，未重放历史批次；本项只保证新跑批的基线与回归分离。
3. **F14 的许可**：只把分发事实说清，不作侵权判断；上游条款需另行核验。
4. **E7 样本量路径**（8/41/72）仍需研究负责人与两名裁决者在看判定前登记——本报告不替裁决者选择。
