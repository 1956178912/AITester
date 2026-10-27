# 更新日志

> 最后更新：2026-10-27

本文件只记录对外可见的变化；逐轮历史见下方归档。

## [Unreleased]

### Added
- 依赖漏洞豁免过期守卫（DF 轮）：`make dependency-audit` 与 CI 阻断步骤真实跑一次**不带**
  `--ignore-vuln` 的 pip-audit——修复版出现、新 advisory 未登记、版本漂移即红；豁免理由由
  `src/` 静态扫描锁定；离线 `[SKIP]` 披露，CI `--require-audit` 把「无法验证」判红（37 例锁）。

### Changed
- 重算论文引用键快照（DG 轮）：稿件在快照后被外部改动，按导出脚本重算 `docs/study/PAPER_CITATION_KEYS.md`（64 行，6 行形态计数随生成器修复变化），读者链全绿。
- 重建投稿 PDF（DE 轮）：70 页、`refs.bib` 79 条 ↔ 79 个 `\bibitem`、0 未定义引用；`PAPER_BUILD.md` 与 `paper/tex/README.md` 的旧读数按实测刷新。
- 文档门面重写（DD 轮）：README / QUICKSTART / CONTRIBUTING / MODEL_CARD / REPLICATION / docs 核心改为简洁结构，中英同步；旧叙事归档到 `docs/history/`。
- 文档测试锁改为结构判据（定位区 / 披露小节 / 行数上限 / 索引完备性），退役逐轮标记与行窗口锁。

### Fixed
- 复杂度感知路由不再在多 provider 端点构型下空转（ET 轮）：`src/agents/base_agent.py::_reorder_api_groups_by_complexity` 以 `model_name` 为唯一键建成本表——同一模型挂在多个 provider 端点、各端点 `cost_weight` 不同时后写覆盖先写，所有分组权重恒等，`sorted` 的稳定排序退化为原序，simple / medium / complex 三档全部空转；而 `complexity_router.py` 承诺的正是「同模型不同 provider 端点，或同 provider 不同 cost_weight」，A15 的 `APIManager._cost_weight_for` 也已按实例取成本，两条路由口径分裂。现按实例键 `(base_url, model_name)` 建表，无 `base_url` 的注入配置回退模型级键，未知端点保持 1.0 基准（不继承同模型另一端点成本）。5 例新锁（4 红→绿 + 1 口径护栏）；本机 `.env.local` 只有 1 个 LLM 实例（`len(all_configs) > 1` 不成立、重排函数不会被调用），缺陷仅在文档承诺的多端点构型下激活。
- 双语文档门禁的「H2 骨架按序对齐」不再对翻译文档空转（ES 轮）：`check_bilingual_docs.py` 的 P2 结构化对照把中英 H2 标题归一化后做**字面**比对，翻译标题天然不同——实测 20 对配对中仅 CHANGELOG 有 2 个跨语言相同标题，其余 19 对永不触发；合成「编号章节互换」与「少一章（总数差 1，在 ±2 容差内）」两个样本旧实现均判无漂移。现改用语言无关的骨架指纹：H2 编号序列（"一、"/"1." 折算整数）逐位相等，H2 数相等时逐节比对 H3 小节数；真语料 13 对带编号、20/20 骨架一致（strict 零警告），6 例新锁（含「可比分母 ≥10」反空转锁），`src/` 零改动 ⇒ 覆盖读数不变。
- 布尔开关不再声明不可达的关态（ER 轮）：`e7_evidence_prepass` / `repair_ceiling_analysis` / `repair_review_worksheet` / `repair_sample_selection` 的 `--pool-seeds` 与 `emse_ult_gold_diagnosis` 的 `--with-generated` 都是 `store_true, default=True`——传与不传等价、`--no-*` 不存在，帮助文本却写「默认开」；前者是预注册固定的多种子拼接口径，后者的关态会在 README §2c 渲染成误导性零值（`n_tasks_with_generated=0`）。现按 EQ 先例移除 5 个旗标、把默认语义钉死在调用点（`pool_seeds=True` / 生成门常开），4 个脚本的 `main()` 增加 `argv` 形参使解析面可测；20 例新锁（16 红→绿 + 4 口径护栏，含 `statistical_analysis` 真开关的邻接护栏），`src/` 零改动 ⇒ 覆盖读数不变。
- 模型目录工具的 `add` 子命令与重放脚本的 `--repeat` 不再与实现脱钩（EQ 轮）：`scripts/tools/expand_models.py add --name/--url/--key` 声明了三个必填旗标，`cmd_add` 却读 `args.model_name/base_url/api_key`——文档里的主命令一给旗标就 `AttributeError`（rc=1），从未成功执行过；`experiments/oracle_examples_replay.py --repeat N` 被接受且全程无 `args.repeat` 读取，用户以为做了 N 次确定性验证（同目录三个重放脚本都实现了整批重复 + body digest 比对，本脚本只抄了旗标）。
  现把三个旗标的 `dest` 对齐 `cmd_add`（CLI 表面不变），删除从未实现的 `--repeat`（同型 `emse_batch5_orchestrator.py --skip-rerun` 因文件被 `.gitignore` 排除、不在跟踪面而不入库）。5 例新锁（2 红→绿 + 3 口径护栏）。
- 批量配置脚本不再用占位符覆盖真实凭证（EP 轮）：生成物 `scripts/tools/generate_batch_config.py` 只为「模型列表为空」设了防覆盖守卫，缺 `*_API_KEY` 或 provider 时仍以 `w` 模式写出 `your-<provider>-api-key-here`、rc=0——现有可用 `.env.local` 会被伪配置替换；usage / argparse 里声明的 `--template` 从不读取（传了静默忽略）。现写入前逐条检查 provider 与对应 API Key，任一缺失即列出原因、rc=1、输出文件原样保留（部分缺 Key 整批拒绝）；删除幽灵开关；在盘脚本与生成模板由测试逐字节对账。7 例新锁（5 红→绿 + 2 口径护栏）。
- 缓存开关的显式关闭拼写不再只在运行时生效（EO 轮）：`AITESTER_LLM_CACHE` / `AITESTER_CACHE_ISOLATE_MODEL` 是 opt-out 开关，运行时走 `env_flag_opt_out`（`false` / `0` / `off` 关），但 `experiments/run_benchmark.py` 三处仍手抄 `!= "0"`——X1 命名空间自设、`cache_enabled`、`cache_isolate_model` 在 `false` / `off` / 大小写空白变体下全部按「开」处理；同一份工件可同时出现 `env_snapshot="false"`、`cache_enabled=true`、`cache_namespace="seed42"`。三处改用 `env_flag_opt_out`，缓存关闭时不再自设命名空间；19 例新锁（12 红→绿 + 7 口径护栏），历史工件一字节不动，`src/` 零改动 ⇒ 覆盖读数不变。
- 批次工件自述的 harness 开关不再与运行时解析脱钩（EN 轮）：`provenance.harness` 用裸 `os.environ.get(...).lower() == "true"` 解析 8 个运行时开关 + 1 个零消费者幻影键，而运行时走 `env_flag` / `env_flag_opt_out`——`EXECUTOR_USE_VENV=yes`、`KERNEL_SANDBOX_ENABLE=on`、`COST_BUDGET_ENABLE=1` 等 8 个实测场景工件自述与生效值相反，`--enable-rag` 时同一工件顶层 `enable_rag=true`、harness 块却 `rag_enabled=false`。现与运行时同一解析器、RAG 披露 `_apply_rag_setting` 生效值；删除运行时零消费者的 `truncation_first` 幻影键。21 例新锁（16 红→绿 + 5 口径护栏）；`src/` 零改动 ⇒ 覆盖读数不变。
- 批次 provenance 的停止原因词表不再与 `StopReason` 枚举脱钩（EM 轮）：harness 披露块承诺「停止规则可复核」，但 `retry_stop_rules.stop_reasons` 是手写 7 值字面量、枚举已 13 值——`recursion_limit`（EJ 起可落盘）、`coverage_stall`（P2-4）等 6 个真实终止原因从未出现在工件自述里，读者会以为 harness 只会以旧 7 值停止。
  现由枚举派生（单一事实源），新增值自动进入新批次工件；历史工件一字节不动。6 例新锁（3 红→绿 + 3 口径护栏）；`src/` 零改动 ⇒ 覆盖读数不变。
- P2P 门禁判无效的行不再在失效分布里冒充「运行异常/限流」（EL 轮）：批次汇总承诺 harness_invalid（基线 P2P 不达标）实例「从统计中剔除」，但 `_aggregate_failure_buckets` 只看 `failure_bucket` 是否为空——门禁早退行（从未进入工作流）与真崩溃同形计入 `unclassified_rows`，报告层还把它们写成「无工作流终局状态〔运行异常/限流〕」。
  现单列 `harness_invalid_rows` 并从桶分母剔除（恒等式 total + unclassified_rows + harness_invalid_rows == total_rows），`render_markdown` 分因披露两种排除；逐行四键仍 `None`（不臆造桶）。10 例新锁（8 红→绿 + 2 口径护栏），分母口径变化已在 `MEASUREMENT_INTEGRITY` §105 披露。
- 已知崩溃原因不再与归因列自相矛盾（EK 轮）：EJ 轮把 `GraphRecursionError` 落成结果行 `stop_reason="recursion_limit"` 后，失败分支仍把归因四键硬编码为 `None`——同一行「原因已知、归因未知」，批次聚合继续把这类确定性 harness 崩溃计入 `unclassified_rows`，ADR-0026 的 harness 归因在生产工件里仍不可读。 现让 `_failure_attribution_for_result` 接受已知 `stop_reason`（仅 `final_state=None` 时生效），失败分支四键取归因结果；无原因崩溃仍四键 `None` 并单列。7 例新锁（4 红→绿 + 3 口径护栏），分母口径变化已在 `MEASUREMENT_INTEGRITY` §104 披露。
- 编排硬上界的崩溃不再被折叠成「无终局状态」（EJ 轮）：`StopReason.RECURSION_LIMIT` 与失效分类法的 `recursion_limit → harness/harness_side` 映射（ADR-0026）都在，但全链路无写入点——基准跑批的异常分支把结果行 `stop_reason` 硬编码为 `None`，图递归上限触顶这一**确定性**原因在工件里退化成「状态信息不足」，分类法承诺的 harness 归因永不命中。
  现新增 `stop_reason_for_exception`（仅 `GraphRecursionError` → `recursion_limit`；普通 `RecursionError` 是节点代码缺陷不得冒充），两条异常分支落盘该标签；桶分布分母口径不变（无终局状态仍单列 unclassified_rows）。10 例新锁（8 红→绿 + 2 口径护栏）。
- 单次 LLM 调用的全局预算不再被时钟回拨绕过（EH 轮）：`LLM_CALL_BUDGET_SECONDS`（默认 600s）此前用 `time.time()` 算截止点，NTP 阶跃校正 / VM 快照恢复导致墙钟回拨时截止点随之后移、预算永不触发；且检查只在换模型时进行，同一模型内的重试阶梯（1/2/4s）与 429 退避（最长 30s）越预算后仍会继续发请求（与 `COST_MODEL` 的「不继续发请求」相反）。 现改 monotonic 计时、每次真实请求前复查、429 等待按剩余预算截断，预算耗尽以 `LlmCallBudgetExceeded` 收口。6 例新锁。
- 时间预算异常不再被「预算封顶」读者漏认（EI 轮）：`LlmCallBudgetExceeded` 原为 `RuntimeError` 兄弟类，而 planner / generator / debugger 与 `determine_stop_reason` 只认 `BudgetExceededError`——超时照常降级，但 `budget_exceeded` 永不落盘、`BUDGET_EXCEEDED` 终止原因不可达，`.env.example` 的「触发 5.4 预算封顶」承诺落空。现改为 `BudgetExceededError` 子类（`unit="seconds"`、`consumed=None` 表示未知），三节点与停止原因零改动自动同待遇。7 例新锁。
- 默认开启的安全/质量守卫不再被坏值静默关闭（EG 轮）：venv 沙箱、凭证与 pip 白名单、危险 API、命名契约、注入输出扫描、证据门、P2P 门禁、容器只读/断网共 10 个开关（11 处读取）走正集 `env_flag(name, True)`，`yes` / `enabled` / 拼错 / 空串都会把守卫判关——实测危险补丁被放行、`MYSQL_PASSWORD` 重新进入子进程环境、容器丢掉 `--read-only` 与 `--network=none`。
  现统一改走 `env_flag_opt_out`：仅 `false`/`0`/`off` 关闭，坏值保持开启；默认关的特征/成本开关仍为正集（坏值不得隐式开启）。31 例新锁（24 红→绿 + 7 边界），先红后绿。
- 可选依赖「装上但坏了」不再击穿降级契约（ED 轮）：12 处 `try: import … except ImportError` 只拦缺包，扩展 ABI / 传递依赖冲突抛出的 RuntimeError/OSError 会穿过去（chromadb 损坏时整个 CLI 无法启动）；现在导入期任意异常都降级告警。12 例新锁 + 1 例负控制。
- 读侧「损坏」判定不再停在 JSON 语法层（EE 轮）：15 处 JSON/JSONL 读侧只捕 `json.JSONDecodeError`（只覆盖解码后文本），坏字节（截断多字节 / GBK 保存）在解码期抛 `UnicodeDecodeError`——行级「坏行跳过」变成一行拖垮整份文件，整文件「损坏 → 空值」直接抛出。
  行级读侧改二进制逐行严格解码（不吞坏字节），整文件补同口径降级，策略库写侧仍 fail-closed 不覆写。15 例新锁。
- 非有限浮点环境值不再静默改写控制流（EF 轮）：6 处本地解析只捕 `ValueError`，而 `float("nan")` 不抛——
  NaN 夹到上界、`-inf` 夹到下界：语义缓存把无关条目当命中返回、覆盖率停滞恒判、风险中阈值变 1.0 绕过审批、
  失败知识库排序退回插入序、`long_sleep` 守卫失效。解析统一委托 `env_float`（告警 + 默认值），有限值钳制不变。49 例新锁。
- trace 可视化 / 回放的读侧词汇与写侧对齐（EC 轮）：写侧只写 `node` 事件、`passed` 三态与 `token_usage`，读侧却按 `node_end` / `test_passed` / `token_delta` 读——100 份真实轨迹 100% 渲染成「无节点记录 + FAIL」（写侧 100/100 通过）；节点时间轴、三态判定与回放演化现按写侧字段读。12 例新锁；状态通道重登记 2/11 → 3/12。
- 发布新鲜度门禁的例外登记不再「登记即通行」（EB 轮）：登记表头的两条语法承诺——条目必须写理由、条目
  必须对应当前最新 tag——此前只在「最新 tag 未登记」一个分支检查一次；当前 tag 已登记 / tag == HEAD /
  仓库没有 `v*` tag 三种状态下，失效或空理由条目静默通过。现在两类缺陷在任何绿色分支之前统一判红并逐条
  点名（无理由条目先于网络判定，API 不可达时同样生效）。9 例新锁。
- OTel 导出的 span 区间不再落在未来（EA 轮）：node / task_end 的记录时刻是操作**结束**，导出器却把它当起点，每段时长向未来延伸（真实会话实测 task_end 晚于导出时刻一个任务时长）。现在起点 = 记录时刻 − 时长，区间闭合在结束时刻；duration > ts 时裁到 `[0, ts]` 并披露 `span_interval_clamped`。14 例新锁。
- OTel 导出的整任务时长不再恒为 0（DZ 轮）：`record_task_end` 写 `duration_s`（秒）、导出器只读 `duration_ms`，task_end 时长被静默丢成 0。现在按字段名选单位（`duration_s` 优先），坏值给 `duration_s_*`。7 例新锁。
- 追踪会话不再因目录不可建而反噬任务（DY 轮）：`AITESTER_TRACE_DIR` 指向普通文件之下曾抛 `NotADirectoryError`、`run` 把任务改写成崩溃；现在告警后降级为仅内存快照，`duration_s` 也不再只在文件模式下存在。4 例新锁。
- 失败追踪导出的参数与并发落点不再失真（DX 轮）：`limit=0` 曾静默导出全部快照、负数反向切片；
  同一秒内的多次 / 并发导出又共用文件名、后写覆盖先写。现在 0 / 负数抛 `ValueError`，`O_EXCL` + 序号重试、绝不覆盖旧快照。11 例新锁。
- `--dump-trace-on-failure` 的失败态不再静默或反噬任务（DW 轮）：目录创建失败曾把已完成任务改写成崩溃，
  无快照 / 写盘失败又静默。现在三态可区分（`trace_dump_path` / `trace_dump_error` + stderr 原因），崩溃任务同样尝试导出。9 例新锁。
- `doctor` 的 `dataset-check-cli` 探针不再要求已移除的文本（DV 轮）：QuixBugs 现在输出「共加载 N 个任务」+「未提供 quality_report，跳过全量校验」，旧探针把能力缺失报成故障；现接受「通过 / 显式跳过」（缺失即红）。净增 4 例（探针共 6 条）。
- `check-dataset` 查出加载问题不再报成功（DU 轮）：报告非空时只打 warning、退出码仍为 0，与「0 = 无问题」相反；现在报告非空逐项列出并以 1 退出，能力缺失与源码待导出仍为披露；QuixBugs 探针接受「经校验通过 / 显式跳过」。11 例新锁。
- `doctor --json` 的三条出口现在共用 13 键 schema（DT 轮）：内部异常只输出 4 个键、正常 12 个，
  `jq -e '.conclusion == "pass"'` 在崩溃时取不到键。现在崩溃时 `matrix.status` 记 `internal`、
  未采集的聚合记 `null`（未知 ≠ 全 0）、脱敏原因进 `error` 并以 1 退出。13 例新锁。
- 任务崩溃的结果面不再与成功路径不同构（DS 轮）：崩溃结果只有 5 个键、成功有 14 个，`jq '.coverage_ok'` 在崩溃任务上取不到键，
  人读模式把缺键兜底画成「迭代 0」；现在两条路径共用全部键（未知判定显式 `null`），原因写 stderr、迭代列显示 `N/A`；状态通道重登记 47 键 / 99 站点。9 例新锁。
- `run --func` / `check-dataset --subset` 不再把显式空值当作「未提供」（DR 轮）：脚本里
  `--func "$FUNC"` / `--subset "$SUBSET"` 变量未展开时 click 收到 `""`，按 falsy 判定
  等于悄悄放宽口径——`check-dataset examples --subset ""` 实测输出「（子集: 全部）」并
  rc=0，`run … --func ""` 把空串原样交给任务（按函数数消耗 LLM）。现在两者都按用法错误
  rc=2 在加载数据 / 启动任务之前拒绝；省略选项才是「全部」口径。8 例新锁。
- `check-dataset` 的状态图标只有一个来源（DQ 轮）：`info_msg` / `warning_msg` 等助手已自带
  `ℹ ` / `⚠ ` 前缀，六个调用点又手写图标，实测输出 `ℹ   ✓ 加载质量健康`，警告路径会是
  `⚠ ⚠ …`；三处成功事实（单个任务健康 / 全量质量通过 / 源码完整）还用蓝 `ℹ` 冒充成功。
  现在图标由助手唯一提供，成功事实改用 `success_msg`（绿 `✓`），并以 AST 结构锁约束
  `src/` 全部助手调用不得自带图标。15 例新锁。
- `run` 不再把目录当任务、也不再重复执行同一文件（DP 轮）：显式目录 / 特殊文件被
  `glob.glob` 原样收下，任务在 `open()` 处抛 `IsADirectoryError` 后被记成「任务失败」
  （rc=1），用法问题伪装成测试没过；同一文件经显式与通配符重复命中时会重复进入工作流、
  重复消耗 LLM。现在目录 / 特殊文件与「通配符只匹配到目录」按用法错误 rc=2 在启动前
  拒绝，重复目标按绝对路径去重、只跑一次。11 例新锁。
- `run` 的帮助与文档不再宣称不存在的报告面（DO 轮）：help 不再泄漏 rich/Markdown 标记
  （`[bold]…`、`**…**`）；detection / repair / false_fix 改述为基准评估面
  （`experiments/_m1_metrics.py`，需要 gold 材料）并以「不在 CLI 输出中」披露；模块地图
  不再把 M1 记在 `src/measurement/`；批次摘要新增覆盖率三态（达标/未达标/不可测），
  `run --help` 与 api_reference 写明阈值不改变退出码。16 例新锁。
- `check-dataset --subset` 不再静默忽略或静默替换（DN 轮）：不支持子集的数据集（内置示例、QuixBugs、
  BugsInPy、Defects4J、synthetic 等）此前传 `--subset lite` 仍 rc=0 并输出「（子集: lite）」，
  实际加载全量数据；ULT 请求 `lite` 而 `ULT_Lite.jsonl` 缺失时同样静默回退。现在不支持 / 未知子集按
  用法错误 rc=2 拒绝（提示由 `dataset_subset_support` 能力表派生），请求子集未生效时 rc=1 并披露原因；
  `load_dataset` 契约不变（`subset` 仍被接受，ULT 回退新增 `subset_fallback_reason`）。14 例新锁。
- `clean-venv-cache` 的报告不再与磁盘现实脱节（DM 轮）：`shutil.rmtree(..., ignore_errors=True)`
  会吞掉一切删除失败，紧随其后的 `except OSError` 是死分支——实测把缓存目录设为只读后，
  命令仍打印「✓ 已删除 1 个 venv（释放 0.0 MB）」且 rc=0，目录原封不动（旧测试用
  `MagicMock` 让 rmtree 主动抛异常，锁住的是 mock 形态而非真实行为）。现在按目录是否真的
  消失区分 `removed` / `failed`，失败逐项报告并以 rc=1 结束，释放空间只累计真正删掉的目录，
  释放空间不再虚报。同时 `--list-only` 此前静默忽略 `--max-age-days` / `--max-size-mb`，
  预览列出全部条目；现在与清理复用同一判定，输出 `[将删除]` / `[保留]`，预览名单与实删
  名单同源（8 例真实文件系统测试锁，先红后绿；旧 mock 锁按新契约改写）。
- `check-dataset` 不再把「没有校验器」报成通过（DL 轮）：`quality_report` 只有 SWE-bench
  系列实现，其他数据集（内置示例、QuixBugs、ULT 等）此前走 `report = {}` 的空分支，输出
  「✓ 全量质量检查通过（N 个任务无加载问题）」——N 可能远大于 `--limit` 实际展示的任务数，
  全量校验从未发生；`tasks_missing_source` 缺失时则完全静默，读者会误以为「无缺失源码」。
  现在两种能力缺失都显式披露「未提供 …，跳过」（退出码仍为 0，与 `doctor` 的 unavailable
  不计失败同口径）；实现了 `quality_report` 且返回空报告时仍输出经过校验的通过结论
  （5 例测试锁，先红后绿）。
- CLI 用法错误与运行失败的退出码不再混淆（DK 轮）：诊断命令 `check-dataset` 此前对未知
  数据集名静默降级为内置示例并报「全量质量检查通过」（rc=0），`--limit -5` 走 Python 负切片
  取尾部，加载异常只打印错误仍 rc=0，数据未就位（加载到 0 个任务）同样报通过；`run` 无有效
  目标或数值选项非法返回 1，与「任务失败」无法区分；`clean-venv-cache --max-age-days -5`
  的负数过滤在删除逻辑里恒真（`age_days > -5`），实测 rc=0 且删光全部缓存。现在用法错误
  统一 rc=2（未知数据集名并列出合法名单、负 `--limit`、负缓存过滤、空目标、
  `--coverage-threshold=nan`），运行失败 rc=1（加载异常 / 0 个任务），`0` 过滤保持
  「全部过期」的显式语义。数据集名单改由模块级注册表派生（新增
  `normalize_dataset_name` 与 `_DATASET_REGISTRY`，消除手工平行名单的漂移面）；工厂
  `load_dataset` 对未知名称仍按契约降级为内置示例（21 例测试锁，先红后绿）。
- `doctor` 用法错误与安装面不可用不再伪装成系统故障（DJ 轮）：拼错分组名或
  `--groups` 解析为空原本都报 `matrix.status="error"`（或静默跑满全量矩阵）；
  pip 安装的 wheel 因不含 `scripts/tools/e2e_probe.py` 使 `aitester doctor`
  恒红且不可行动。现在探针框架对未知 `--group`/`--name` 在过滤前报错并列出
  合法值（rc=2）；`doctor` 把子进程 rc=2 映射为 `usage`（退出码 2，不伪造
  error 行）、脚本缺件映射为 `unavailable`（不计失败，`--strict` 下退 1），
  空 `--groups` 直接走用法错误路径且不采集检查/不跑矩阵（10 例测试锁，先红后绿）。
- 门禁链子进程全部带超时预算（DI 轮）：10 处 `subprocess` 调用缺 `timeout`——git 锁、ruff、mypy 与 pytest 收集任一挂起都会让 `make gates` / CI 无限挂起（没有读数、没有失败行，只有被平台上限回收的作业）。
  补齐预算并钉死超时语义：登记面对账超时抛 `RuntimeError` 判红（返回 `None` 会被读成 `[SKIP]` 静默放行）、基线收集降级为 `None`、仓库卫生抛 `RuntimeError`、工件门合成 rc=124、静态快照记 `(124, 超时)`；
  删除 `check_invocation_caliber` 的死 helper；AST 结构锁覆盖 `scripts/gates/*.py` 与两个工具脚本（7 例，先红后绿）。
- CI 作业预算补齐（DH 轮）：`ci.yml` 的 `smoke-llm` 是唯一没有 `timeout-minutes`
  的作业——LLM 端点挂起时会被平台默认的 360 分钟兜底回收；补 15 分钟预算，并新增
  `tests/test_ci_job_timeouts.py` 锁全部 workflow 作业的预算声明与 (0,60] 值域
  （3 例，先红后绿）。
- 引用键快照生成器漏计多键引用（DG 轮）：`render_snapshot` 按单键正则统计
  `\citep` / `\citet` 形态，正文 `\citep{a,b}` 组内的键被漏计（真实稿件 4 个多键组、9 个键位，
  低估 `konstantinou2026icst` 等 6 个受管键）；改为按组拆分计数，1 例测试锁先红后绿。
- 可选嵌入后端加载失败必须降级（DG 轮）：`sentence-transformers` 分支只捕 `ImportError`，模型下载失败 / 缓存损坏会击穿「不可用即 None」契约；现补同形降级并在显式选择该后端时告警，3 例测试锁先红后绿。
- 注释语义按文件类型分治（DE 轮）：TeX `%` 按反斜杠奇偶、Typst `//` 与可嵌套块注释、BibTeX 按括号深度且 `\"` 不切换字符串态；修复 `refs.bib` 注释被误算进上一条目字段值造成的假 CJK 红。
- 论文构建脚本前置判据改为 `--pre-build`：只跳过产物页数对账，源侧判据照常阻断，避免「编辑源文件后无法重建」的自锁。
- 外部读数登记册更正 `wang2026harnessreeval` 为 arXiv v4 并补齐 v1–v4 版本史；两处强否定改为「所核摘要与正文未见」。

## [1.0.0] - 2026-10-25

### Added
- 复现包 `REPLICATION.md`、`REPRODUCE_SKIP_TESTS` 显式逃生口与零 LLM 复算链。
- 发布判据 ADR-0036；发布新鲜度守卫。

### Changed
- repair 读数采用修正口径 v2（39.31%，57/145 可重放行，gold 独立裁决）；
  历史口径见 `docs/design/repair_caliber_matrix.md`。
- 模型调用默认关闭 thinking、默认开启 JSON 模式（ADR-0031）。

### Fixed
- 修复 `repair=0` 两起测量伪影：patch 字段围栏残留、跨文件任务未物化。
- 文档命令可执行性、引用库可编译性等门禁补链。

### Security
- 敏感/私有路径纳入仓库卫生门禁；`.env*` 与私有目录不得被跟踪。
- git 历史存量泄漏处置见 `docs/security/history_leak_remediation_runbook.md`。

## 更早版本

0.8 / 0.9 系列与更早的逐轮记录见归档（原样保留，链接不保证可达）：
[README（中文）](docs/history/README_2026-10-26_full.md) · [README（英文）](docs/history/README_2026-10-26_full.en.md) ·
[CHANGELOG（中文）](docs/history/CHANGELOG_2026-10-26_full.md) · [CHANGELOG（英文）](docs/history/CHANGELOG_2026-10-26_full.en.md)。
