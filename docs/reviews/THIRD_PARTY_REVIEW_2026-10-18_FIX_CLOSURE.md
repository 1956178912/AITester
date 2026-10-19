# 第三方审查（2026-10-18，Windows 环境）23 项修复收口报告

> **性质**：V 轮（2026-10-18）第三方独立审查修复的交付说明与验收记录。
> **评审基线**：审查报告 `AITester_审查报告.md`（第三方在 Windows 环境对提交
> `ff15a2f` 的静态审查；用户确认 23 项结论 **100% 准确**）；本仓修复起点
> `ff15a2f` 与评审提交逐位一致。
> **修复花费**：真实 LLM **$0**（全部为代码/文档/工件层修复与零 LLM 验证）。
> **回归结论**：全量测试 **9125 passed / 5 skipped / 0 failed**（collected
> 9130，xdist `-n 4 --dist loadfile`）；评审 M1–M9 验收脚本复跑通过（M5 的
> Windows 分支以 Mock 单测覆盖，本机 macOS 无法实跑 `taskkill`）。
>
> **2026-10-19 复核追加（重要）**：第二轮第三方复核（提交 `73481bb`）确认
> **P0=0、P1=3**——A07/A09/A10 三项为本轮修复的**未覆盖子场景**，故本报告
> 原先"23 项全量收口"应读作 **"20 项有针对性修订/历史披露 + 3 项部分修复"**。
> 三项已于 2026-10-19 补修并有反例回归锁，见 §5。

## 1. 逐项收口矩阵

编号与级别沿用第三方审查报告；"验证"列给出可复跑的验收入口。

### P0（1 项）

| 编号 | 修复内容 | 关键文件 | 验证入口 |
|---|---|---|---|
| A08 凭证隔离失效 | 新增统一 `untrusted_exec_env()`（最小白名单 + 嵌套 pytest 运行期键 + 显式 overrides），收敛 M1 判分 / MDO 探针与测试执行 / P2P 回归 / 两个候选代码探针；`nested_pytest_env` 保留兼容别名 | `src/utils/process_utils.py`、`experiments/_m1_metrics.py`、`src/measurement/mdo.py`、`src/tools/patch_rollback.py`、`experiments/solver_directed_trigger.py`、`experiments/spec_ambiguity.py` | 审查 M4 脚本 → `sentinel inherited: False`；`pytest tests/test_untrusted_exec_env.py -q`（34 passed） |

### P1（16 项）

| 编号 | 修复内容 | 关键文件 | 验证入口 |
|---|---|---|---|
| A01 非劣外推 | 登记册/既有评审的"非劣成立/损失来自移除实现代码"改为点估计阈值标记（`independent_marker`）+ 不确定性披露（n=35、4:3、CI [−11.43,+17.14]pp、单侧下界 −8.57pp）；因果主张降为候选假设；历史评审加日期化勘误 | `docs/PROJECT_STATUS_REGISTER.md`、`docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-18.md`、`docs/design/docstring_anchor.md` | `make docs-check`；全仓 grep 无裸旧表述 |
| A02 复现入口 | `reproduce.sh` fail-closed 数据集分派；synthetic 透传真实主批参数（full=87/2/42、三臂）；未知 dataset 立即报错 | `reproduce.sh`、`REPLICATION.md`、`docs/INDEX.md` | `bash -n reproduce.sh`；`bash reproduce.sh --dataset bogus` → rc=1；`pytest tests/test_reproduce_zero_llm.py -q` |
| A03 来源追踪 | 解析 `.repro_provenance` 的 `GIT_SHA`（无 git 时作为 provenance 来源、有 git 时记录并校验一致性） | `experiments/run_benchmark.py`、`Dockerfile.repro`、`REPLICATION.md` | `pytest tests/test_run_benchmark.py -q`（7 例 marker 测试） |
| A04 协议叙事失同步 | Algorithm 3 中英重写为 Detection-First Loop；修正"单侧 oracle 失败=确定性检出"；`mas_compilation` 改三方并列 | `docs/algorithm_design.md/.en.md`、`docs/design/mas_compilation.md` | `make docs-check`；人工核对 ADR-0015/0016 口径 |
| A05 API 示例失效 | API 参考中英示例/表格按当前签名重写（`compute_cyclomatic_complexity`、`apply_patch_to_code -> tuple`、`replace_function_code(..., new_function_code)`）；默认开关说明对齐 | `docs/api_reference.md/.en.md`、`README.en.md` | 文档示例抽取执行 + `inspect.signature` 核对；`make docs-check` |
| A06 簇映射错误 | 三层身份解析（归档元数据优先 → 分 seed 正确重建 cap=2 → 保守单例）；旧错误 26 簇保留为反面锁定 | `experiments/statistical_analysis.py`、`tests/test_cluster_robust_stats.py` | main_batch 复算：261→31 簇、5:17:9、p=0.01690054；`pytest tests/test_cluster_robust_stats.py -q` |
| A07 最新 None 回退 | 先去重（最新批次优先）再排除 None；**2026-10-19 补修**：主配对/贝叶斯/模板敏感性三处统一接入 `experiments/_row_pairing.py` 共享原语（此前模板分支仍"跳过 None + 后写覆盖"） | `experiments/statistical_analysis.py`、`experiments/bayesian_paired.py`、`experiments/_row_pairing.py` | 审查 M8 → `n_common=0`；**M3 复跑 → `discordant 2:1`（修复前 1:2）**；`pytest tests/test_review_73481bb_residuals.py -q`（A07 四例） |
| A09 缓存身份 | 精确键与语义索引统一按规范化有效请求身份隔离；旧缓存仅默认包络只读回退；**2026-10-19 补修**：身份材料加入 `system_prompt` sha256 摘要（`v` 2→3），跨角色语义命中消除 | `src/agents/base_agent.py`、`src/agents/semantic_cache.py` | 审查 M6 → B 身份返回 `None`；**M2 复跑 → 跨 system 语义未命中（修复前命中 A）**；`pytest tests/test_semantic_cache.py tests/test_closeout_k_base_agent.py tests/test_review_73481bb_residuals.py -q` |
| A10 请求链/标签 | 线程局部任务分配优先、全局链故障转移；成功请求记录真实配置（`request_identity`/`response_identity`）；**2026-10-19 补修**：全局列表已含 override 时同样提到链首（此前直接早退），并明确契约"显式分配 > 复杂度路由 > 全局顺序"（复杂度重排后二次钉住） | `src/agents/llm_client.py`、`src/agents/base_agent.py` | 审查 M9-A10：首请求=线程局部 B、链=[B, global-A]；**M1 复跑 → 全局 [A,B] + 分配 B 时为 [B,A]（修复前 [A,B]）**；`pytest tests/test_closeout_k_llm_client.py tests/test_review_73481bb_residuals.py -q` |
| A11 消耗漏记 | 收到响应先记账 usage、再判 finish_reason/空响应；重试前复查预算 | `src/agents/base_agent.py`、`src/agents/llm_client.py` | 审查 M9-A11：两次 usage 累计 22；相关 mock 测试 |
| A12 Windows 回收 | 可注入平台分派；Windows `taskkill /T /F` + `kill()` 兜底 + 有界等待；看门狗脚本同步分流 | `src/utils/process_utils.py` | 审查 M5 语义 → `pytest tests/test_windows_process_termination.py -q`（16 passed） |
| A13 执行运行依赖 | 新增 `execution` extra（pytest/pytest-cov/pytest-timeout）；执行前能力检查 `execution_dependency_missing` | `pyproject.toml`、`setup.py`、`src/agents/executor_runtime.py`、`executor_modes.py` | `pytest tests/test_packaging.py -q`；`tomllib` 解析 + extras 静态校验 |
| A14 发行缺包导入 | `mutation_advisor` 的 experiments 导入移入 try 降级；nodes N5 同护栏；12 处 src→experiments 导入点审计 | `src/graph/mutation_advisor.py`、`src/graph/nodes.py`、`setup.py` | 缺包模拟测试（`sys.modules`）；`pytest tests/test_packaging.py -q` |
| A15 节点身份 | 端点实例 ID 标识节点；同 model 多 provider 全保留、健康/选路独立；单实例对外键不变 | `src/api/api_manager.py` | 审查 M9-A15：同 model 两端点 2 节点、健康独立；`pytest tests/test_api_manager*.py -q` |
| A16 fail→pass 证据 | 保留每次尝试记录；节点/单智能体基线消费并保守判分；`_m1_metrics` 对 flaky 任务 M1 端点记 None | `src/agents/executor_runtime.py`、`src/agents/executor.py`、`src/agents/executor_modes.py`、`src/graph/nodes.py`、`experiments/run_benchmark.py`、`experiments/_m1_metrics.py` | `pytest tests/test_flaky_gate.py tests/test_m1_metric_semantics.py -q`；真实 pytest fail→pass 端到端 |
| A17 跨平台字节 | `.gitattributes` 对证据目录 `-text`；校验门禁区分 raw/EOL-only/内容不符，新增 `--strict-bytes` | `.gitattributes`、`scripts/gates/checksum_results.py` | 审查 M2：本机 69 清单/7,639 raw/0 缺失/0 不符；模拟 CRLF 检出 64/64 通过 |

### P2（6 项）

| 编号 | 修复内容 | 关键文件 | 验证入口 |
|---|---|---|---|
| A18 清单失效条目 | 清单只覆盖分发文件（排除 `__pycache__`/pyc，支持 `--exclude`）；清除 9 条失效、补 3 条漏记 | 各 `SHA256SUMS`、`scripts/gates/checksum_results.py` | 干净检出模拟：64 清单/7,048 条全部 raw 一致、64/64 verify 通过 |
| A19 CSV 转义 | 标准 csv writer 修复第 19 行引用；12 列复正、其余语义不变 | `docs/reviews/review_recompute/recommendations.csv` | 审查 M3 → header 12 / row19 12 / 21 行全 12 列 |
| A20 损坏 JSONL | 根因 = 先序列化后整行脱敏且凭证模式贪婪吞尾；修复脱敏模式 + 结构感知脱敏 + `json.loads` 落盘守卫；损坏工件原字节保留并加勘误 | `src/utils/logging_utils.py`、`src/observability/trace.py`、批次 README | `pytest tests/test_trace_jsonl_integrity.py -q`（15 passed）；损坏行 sha256 未变 |
| A21 引用题名 | README 中英 Carleton 题名更正 | `README.md`、`README.en.md` | `make docs-check`；check_citations 通过 |
| A22 检索计数 | 一次解析有效 k、top-k 内整数计数 | `src/measurement/retrieval_quality.py` | `pytest tests/test_retrieval_quality.py -q` |
| A23 LRU 边界 | `_lru_tokens` 同步淘汰/清空、受容量约束 | `src/agents/base_agent.py` | 审查 M7 → `before 2 2 / after 0 0`；`pytest tests/test_closeout_k_base_agent.py -q` |

## 2. 评审验收脚本复跑结果（M1–M9）

| 验收项 | 命令出处 | 修复后结果 |
|---|---|---|
| M1 主批分母/配对/非劣区间 | 审查报告 M1 | 与报告基线逐位一致：aitester 38/240/21、plain_llm 4/261/0、df 117/261/0；共同 n=240、b/c=12/80；31 归档模板 |
| M2 摘要与缺失目标 | 审查报告 M2 | 本机：69 份清单 / 7,639 条 raw 匹配 / LF-only 0 / **missing 0 / mismatch 0**（修复前 missing 9）；干净检出模拟 64 份 / 7,048 条全部一致 |
| M3 CSV 与损坏 JSONL | 审查报告 M3 | CSV header 12 / 第 19 行 12 / 全部 21 行 12 列；损坏 JSONL 仍为第 10 行第 201 列（**原字节保留**，已在批次 README 勘误；新写入受结构守卫保护） |
| M4 伪凭证继承 | 审查报告 M4 | `sentinel inherited: False` |
| M5 Windows 回收 | 审查报告 M5 | 本机 macOS 用 Mock 覆盖 Windows 分支：不抛 `AttributeError`、不触碰 POSIX API、直接子进程被等待/兜底 |
| M6 语义缓存身份 | 审查报告 M6 | B 身份（`MODEL_B_SEED44`）→ `None`；A 身份仍可命中自身 |
| M7 LRU token 字典 | 审查报告 M7 | `before clear: 2 2`；`after clear: 0 0`（修复前 `2 3` / `0 3`） |
| M8 最新 None 配对 | 审查报告 M8 | `{'n_common': 0, ...}` |
| M9 发行/路由/记账/节点身份 | 审查报告 M9 | A10 首请求=线程局部 B、链=[B, global-A]；A11 两次 usage 累计 22；A13/A14 干净 wheel 路径有测试与能力检查；A15 同 model 两端点 2 节点、健康独立；A16 fail→pass 端到端保留 |

## 3. 回归与门禁

| 项目 | 结果 |
|---|---|
| 全量测试 | **9125 passed / 5 skipped / 0 failed**（collected 9130；`make gates` 实测 180.26s；含覆盖率采集的全量 184.00s） |
| 覆盖率（本地 macOS 3.14） | 行 **96.48%**（17883/18535）/ 分支 **92.71%**（6406/6910）；ratchet 水位 96.4 / 92.5，余量 +0.08pp / +0.21pp（`BASELINE.yaml` coverage 节与 `docs/coverage_ratchet.yaml` 已刷新/核对） |
| 本地全门禁 | `make gates` **exit 0**（lint + format + mypy + test + docs-check + env-budget + baseline-check + state-contract + env-snapshot + model-fingerprint + tool-versions + json-contract-sites + artifact-doc-consistency + zero-assert） |
| 文档门禁 | `make docs-check`（双语 strict + 链接 strict）通过 |
| 基线门禁 | `check_baseline.py` / `check_baseline_numbers.py` / `check_artifact_doc_consistency.py` 通过 |
| 证据链门禁 | 全仓 `SHA256SUMS` 校验通过（0 缺失 / 0 内容不符） |
| 其他 | `check_zero_assert_tests.py`、`check_env_budget.py --check`、`check_branch_coverage.py`、`coverage_ratchet.py --check`、`check_citations.py`、`audit_log_redaction.py`、`check_credential_scrub.py`、`check_lock_sync.py`、`check_prompt_artifacts.py --strict`、`check_artifacts_tracked.py`（179/179）均通过 |

## 4. 残余风险与未纳入本轮的事项

1. **A17 的历史 Windows 检出**：`.gitattributes` 只对**新检出**生效；评审机已有 CRLF 工作树需重新检出才恢复字节一致。过渡期 `--verify` 只把 EOL 差异单列为 WARN（不判篡改），发布闸用 `--strict-bytes`。
2. **A08 的边界**：环境隔离 ≠ 文件系统隔离——`HOME` 下的 `~/.aws`、`~/.ssh` 等对不可信代码仍可读（威胁模型另一数据流，未在本轮环境修复面内）；`scripts/tools/{e2e_probe,run_logic_ab,compare_executor_modes}` 属开发工装，保留 `os.environ` 合并（非评分/生成代码执行面）。
3. **A16 的残余**：M1 只对 `flaky_unverified=True` 任务记不可测；fail→pass 判分改变的是**未来**行为，历史工件不重跑（新字段纯增量）。
4. **A10 的 provenance**：结果 JSON 工件层的请求来源字段仅到缓存 payload（`request_identity`/`response_identity`）；批次结果行如需直接展示实际端点，需另行接线（本轮未改实验工件 schema 消费面）。
5. **A20 的损坏工件**：损坏轨迹原字节保留（不静默修补）；成因与复核命令见该批次 README 勘误节。
6. **A15 的对外影响面**：同 model 出现第二个 provider 时 `health_nodes[model_name]` 原有键会升级为实例 ID；仓库内无此类生产消费者（测试已兼容），外部直接读取该内部结构的代码需改用 `get_status()` / `get_all_nodes()` / `remove_node_by_id()`。
7. **A06 的旧批次**：默认 cap=2 对 2026-10-06 前无 cap 的旧批次不再静默错映射（元数据不可复现 → 单例 + 披露）；正确复现旧批次请显式传 `--cluster-max-pattern-repeat 0`。
8. **A01 的历史快照**：`CHANGELOG` 历史条目与历史评审原文保留（按历史快照纪律）；现行文档已收缩口径并加勘误。
9. **A14 的冻结组件**：`src/graph/orchestration_search.py` 对 experiments 的导入按 ADR-0034 冻结范围未加固（非生产预设路径；触发条件 = 干净 wheel + 显式 oracle 化 search 真实评估）。
10. **未执行**：本轮未真实构建 Docker 镜像、未真实调用 LLM、未在 Windows 主机实跑（M5 以 Mock 覆盖；M2 以 CRLF 模拟覆盖）。

## 5. 第二轮复核残留补修（2026-10-19，P1×3，零 LLM）

**触发**：第二轮第三方复核（Windows 只读静态审查，提交 `73481bb`）确认
P0=0、P1=3、P2=0、P3=0；三项均为本轮修复的**未覆盖子场景**，不新增编号。

**修复原则**：不复述结论，逐项消除报告给出的最小反例，并把反例固化为
回归锁 `tests/test_review_73481bb_residuals.py`（12 例；同一文件在修复前
提交上实测 **10 failed / 2 passed**，修复后 **12 passed**）。

| 编号 | 报告根因 | 本次修复 | 反例锁定 |
|---|---|---|---|
| A07 | `template_cluster_sensitivity._binary` 先跳过 None 再字典赋值（后写覆盖），且 `row_by_id` 用后写覆盖字典取模板元数据 | 新增 `experiments/_row_pairing.py`：`latest_rows_by_task`（首见=最新，不看字段值）+ `latest_binary_by_task`（去重后排除 None，数值与元数据同源）。`_pair_by_task`、`template_cluster_sensitivity`、`bayesian_paired.paired_contingency` 三处共用 | 报告 §M3 反例 → `discordant 2:1`；最新 None 不回退；模板元数据取最新行（k=2 而非 3）；同 seed/同批重复行 |
| A09 | `_effective_request_identity` 不含 `system_prompt`，精确文件名分离但语义分区键相同 → 跨角色可命中 | 身份字典新增 `system`（sha256 前 16 位摘要），版本 `v` 2→3；生产调用点传入 `self.system_prompt`；语义索引重建从 payload 派生身份（自动同源）；`_legacy_cache_identity_compatible` 明确 system 维度的旧键隔离说明 | 报告 §M2 反例 → 跨 system 语义未命中；两个不同 system 的 BaseAgent 同 prompt 各调用一次（调用级回归）；同 system 仍可命中 |
| A10 | `_get_all_api_configs` 在 `override in global_configs` 时直接返回全局链，正常轮询分配被静默丢弃 | 统一为 `[override, *其余全局配置（去重、原序）]`；新增 `_pin_thread_api_group` 在复杂度重排后二次钉住分配组，明确契约 **显式分配 > 复杂度路由 > 全局顺序** | 报告 §M1 反例 → `[B, A]`；同 base_url 不同 model 组内重排；真实调用链首客户端 = B；`complex` 档不夺走显式分配 |

**边界（不夸大修复范围）**：

0. **连带修复（验证过程中发现，非评审编号项）**：全量回归中按 xdist 文件
   配对顺序随机转红的用例定位为**既有测试间全局状态污染**而非本次修复引入，
   共两处生产级泄漏 + 一处测试卫生：
   ① `experiments/spec_examples_generator.py::generate_spec_examples` 注入
   `LLM_MAX_OUTPUT_TOKENS=512` 后**从不恢复**（只恢复了 namespace），一次
   示例生成即永久改变同进程后续所有 LLM 调用的请求体与缓存身份（已改为
   快照-恢复，与 namespace 同款；显式配置优先、异常路径同样恢复）；
   ② `experiments/run_benchmark.py::run_single_task` 经 `_set_thread_api`
   把任务分配（真实 env 凭证）写入当前线程后**从不清理**——并行跑批行为
   不变，但进程内单线程调用方（CLI/库/测试）会把最后一次分配永久留在主
   线程，污染后续 `_get_llm_config`/`_get_all_api_configs` 与缓存身份（已在
   函数 finally 中快照-恢复线程局部三元组）；③
   `oracle_examples_replay.main` 对进程环境 `setdefault` 该键属 CLI 生命周期
   口径（不改），但 `test_oracle_examples.py` 把 CLI 当库调用后未恢复——
   已在测试内显式快照恢复。
   回归锁：`test_examples_multisample.py::test_generate_restores_max_output_tokens_env`
   （未配置→移除 / 显式→原样 / 异常→恢复）+ `test_run_benchmark.py::test_thread_local_api_assignment_restored_after_task`
   （无分配→不残留 / 已有分配→恢复原值）。
1. **历史工件不重算**：三项均为"条件性错误"——只在输入含跨批重复 task_id、
   启用语义缓存且跨 system、或线程分配形状命中时触发。归档主批（无重复
   task_id、语义缓存默认关、A10 相关批次以单端点为主）的既有数字不因本次
   修复而改写；是否需要重算受影响批次，按报告 §P 的口径在运行验收后再定。
2. **A09 旧缓存**：`v` 升版使旧精确缓存文件自然失效（miss 后重新生成）；
   旧格式只读回退仍受 `_legacy_cache_identity_compatible` 的默认包络约束，
   且旧键公式本身含 system 文本、读侧校验 `system` 等值，不跨 system 命中。
3. **A10 优先级**：本次把"显式分配优先于复杂度路由"定为产品契约；若未来
   需要"复杂度路由可覆盖任务分配"，必须显式改契约并同步本表与测试，不得
   静默调换顺序。
4. **运行验收**：A07/A09/A10 的验收均为进程内最小反例与调用级回归（零
   网络、零 LLM、零缓存文件写入生产目录）；真实多端点/真实语义后端的
   端到端验收仍需在具备凭据的环境单独执行（报告 §M 的其余项同）。
