# 检查点：数据清空 + 论文骨架 + 提示词英化（2026-11-04 11:20）

## 目标（用户指令汇总）

方向重置为**从 0 重跑**：删除全部历史数据与缓存、提示词英化、模型默认开思考、价格改人民币、
论文只留框架、测试取最高覆盖面但资源占用不超 75%、测试严格单一变量。

## 已完成

### 数据与缓存
| 对象 | 处置 |
|---|---|
| `experiments/results/` | 清空（8,185 文件 / 340 MB；已 tar 至 `~/Workspace/_aitester_backup/results_20261104.tar.gz`，50 MB） |
| `~/.cache/aitester/llm` + `llm.bak.1791699261` | 删除（77 MB） |
| `rag_data/` | 清空（2.2 MB，Chroma 索引） |
| `~/.cache/aitester/{quixbugs,swe_bench,bugsinpy,repo_envs,pro_repos}` | **保留**（重跑基础设施，约 47 GB；删了要重新下载/建环境） |

### 模型与计费
- 登记 `xiaomi` provider + `mimo-v2.6-pro`（`https://api.xiaomimimo.com/v1`，OpenAI 兼容）。
  `LLM_2_*` 不占首请求位（`_get_llm_config` 恒取 `LLM_CONFIGS[0]`），既有跑批默认模型不变。
- `LLM_THINKING_MODE` 默认 `disabled` → **`enabled`**；`LLM_MAX_RETRIES` 默认 3 → **6**（延迟解析）；
  `LLM_HTTP_TIMEOUT` 180 → **600 s**；pytest 单测超时 1200 → **3600 s**（thread 法）。
- 价目表切 **CNY、高峰时段价**：deepseek-flash ¥2/¥8、mimo-v2.6-pro ¥3/¥6 per Mtok。
  新增 `pricing.estimate_in_table_currency()`（返回 `(amount, currency, source)`）；
  `estimate_usd` 保持"只认 USD"的历史契约；`entry_block_reason` 对基准币种 CNY 隐式放行（共享谓词一处收口）。
  `BudgetExceededError` 增加 `cny` 单位与 `¥` 符号分支；`_budget_exceeded_error` 的金额分支从 `== "usd"` 改为 `in ("usd","cny")`
  （否则 CNY 会落 token 分支，把 3000 tokens 当金额）。

### 提示词英化
- `src/prompts/templates.py`：4 个 agent 的 system prompt + 规约表达式契约段，全英文。
- `src/graph/nodes.py`：`_detection_first_section`（原 196 字符中文干预段）、`_over_red_section`、补丁语法校验反馈，全英文。
- 连带更新回归锁：`test_prompt_artifacts_gate`（中文关键词断言）、`test_ad_batch`（思考默认）、
  `test_config_generator`（provider/模型集合）、`test_credential_scrub`、`test_closeout_k_base_agent`（逻辑缓存信封）。
- **未完成**：`src/agents/`（error_classifier 18 条、expert_pool 4 条、generator/debugger/planner 若干）与
  `src/tools/`（failure_frequency 5 条、multi_candidate、operation_map、logic_spec、spec_first、patch_intent、spec_refine）
  约 30 处增强段仍为中文。这些是按需注入的修复/增强提示，不是每次调用都发。

### 论文
- 骨架化至 **40 页**：保留标题/作者/摘要骨架（5 段 + `[Pending rerun]`）、引言、相关工作、研究设计、
  5 个 RQ 陈述与表模板（`tab:protocol`/`main`/`falsefix`/`anchor`/`crossbench` 空表）、讨论骨架、威胁、复现、结论占位、声明、附录 A–C。
- 删除：全部结果数字与结果叙述、讨论结论、Appendix D–I（分母/成本/门禁/预注册/统计机制/spec 仪器）。
- 新增"单一变量原则"段（Study Design）：模型对比固定协议/prompt/任务集/seed/温度/思考档；
  协议对比固定模型与采样；预算对比固定模型与协议。两因素同动只作描述、不作因果。
- 署名：取消共同第三作者（`§`），Xing Yu、Yue Xu 按原顺序列为普通作者；题名页与主稿三处同步。
- 验证：`pdflatex` exit 0、0 undefined reference、0 undefined control sequence；compliance FAIL 0 / WARN 2 / PASS 13；摘要 188 词。

### 测试基础设施
- `scripts/run_all_tests.py`：门禁 → pytest 全量（0 LLM）→ LLM 冒烟 三段串联；
  并行度 = 物理核 × **75%**（10 核 → 7）；失败 `--lf` 重跑（默认 3 轮）；
  心跳采样 load/内存；`REPORT.json` 落 `experiments/results/test_run_<ts>/`。
- `--selftest` 通过；实跑验证：4 次尝试、1m52s、按设计退避重跑。

## 验证记录
- `python scripts/run_all_tests.py --selftest` → 并行度 7、超时 3600 s、通过。
- `python scripts/gates/check_llm_configs_schema.py` → 2 条模型目录、exit 0。
- `price_table.json` 实测：deepseek 100 万入+出 = ¥10.0、mimo = ¥9.0、未登记 = unpriced、旧 USD 通道 = unpriced。
- `paper/check_emse_compliance.py` → FAIL 0。
- `pdflatex manuscript.tex` → 40 pages、0 error、0 undefined ref。

## 风险与注意
1. **提示词只英化了核心链路**：剩余约 30 处增强段仍是中文。若要求"全部提示词英文"，需再来一轮。
2. **`consumed_usd` / `COST_BUDGET_USD` 字段名保留美元名，语义已是人民币**，文档已标注为历史遗留；
   彻底改名会波及 40+ 引用点与全部报表，作为独立技术债。
3. **删除不可逆性**：`experiments/results` 的 6,068 个未跟踪文件只能从 50 MB 备份包恢复。
4. **论文 40 页仍高于"正文 30 + 附录 12"**：附录 A–C 与 Threats 未进一步压缩。

## 下一步
1. 等全量测试收敛（当前在跑）；若有残留红，按币种/思考档两类归因。
2. 剩余提示词英化（`src/agents/` + `src/tools/` 约 30 处）。
3. 论文压到 42 页以内（当前 40 页，已达标；若需正文 30 页需再切附录）。
