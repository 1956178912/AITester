# T-E 对抗式验证记录（独立 subagent 对 `FINAL_REVIEW_2026-10-11.md` 的证伪性复核）

- **验证执行者**：T-E 对抗式验证员（独立 subagent；与报告作者、与既有 `T_A`–`T_D` 审计员均非同一执行体）
- **验证时间**：2026-10-11 10:42–11:0x（Asia/Shanghai）
- **验证方式**：**零 LLM、只读**。全部数值由本次直接解析 `experiments/results/**` 原始工件重算；引用真伪由 `curl` 访问 Crossref / arXiv 机读端点独立核验。**未运行任何产生新数据的命令**（未跑 pytest、未跑 replay、未跑 LLM）。
- **写入范围**：本文件是本次验证**唯一**写入的项目内文件；未修改 `FINAL_REVIEW_2026-10-11.md`，未新增/修改任何脚本或工件。（一次性复算脚本落在 `/tmp/t_e_repro.py`，全文见附录 A。）
- **纪律**：下表每一行的"我复算值"都来自附录 A 脚本或表内标注的 heredoc 命令的实际输出；**未复算的项一律列入 §5"我无法验证"**，不以推断填充。

---

## 0. 审计对象指纹（重要：报告在本次审计过程中被就地修改过）

| 版本 | 观察到的时间/大小 | 本次能否给出哈希 | 关键差异 |
|---|---|---|---|
| **R-old**（我开始审计时读到的版本） | mtime `2026-10-11 10:42`，size **133,651 B** | **不能**：文件随后被就地覆盖，且该文件未被 git 跟踪（`git status` 显示 `?? FINAL_REVIEW_2026-10-11.md`），全盘检索无副本 | §0.2 K1 写"反事实分解：对齐'产红率'可补 **88%** 缺口，对齐'红→检出转化率'仅补 12%"；§3.4.2 写"只把产红率对齐 → 检出升至 ~244（+166）；只把转化率对齐 → ~179（+101）。**产红率缺口贡献约 88% 的差距**" |
| **R-new**（本次逐条核对的版本，即交付时点版本） | mtime `2026-10-11 10:44:59`，size **139,491 B** | **能**：`sha256 = f19b196c11cf9f2ffb5b86eec2b40a2d40063062b1c96a3438a38bf3f42aaaa1` | 同一处已改为"对齐'产红率'贡献 **44.2%**、对齐'红→检出转化率'贡献 **26.1%**、两因子交互 **29.7%**"，并附"口径更正（本报告自查）"注记 |

**处置**：§1 逐条核对以 **R-new** 为对象；凡 R-old 与 R-new 有差异处，两版分别判定。**"88%"这一表述在当前版已不存在**——若下游材料（如正文引述、汇报稿）仍在引用 R-old 的 88%/+244/+179，须以 R-new 为准。

> 结论先说：**R-new 的 44.2%/26.1%/29.7% 我独立复算一致**（算法与序贯约定见 §1.3）；**R-old 的 88% / "+166 → 244" / "+101 → 179" 均不可复算**（§3-S5 给出重建尝试）。

---

## 1. 逐条核对表

> 复算命令统一说明：**A.x** = 附录 A 脚本 `/tmp/t_e_repro.py` 的第 x 节（本次已实跑，输出见 A.11）；表内另附最小表达式。全部为 `.venv/bin/python`（Python 3，只读 `json.load`）。

### 1.1 §3.3 三臂核心数字（7 批 `benchmark_synthetic_2026100[67]_*.json`，各臂 609 行）

| # | 报告值（R-new） | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 1 | aitester detection **78/556 = 14.0%** | **78/556 = 14.029%** | ✅ 一致 | A.1：`sum(detection_rate==1.0) / sum(detection_rate is not None)` |
| 2 | df detection **279/571 = 48.9%** | **279/571 = 48.862%** | ✅ 一致 | A.1 同上 |
| 3 | plain_llm detection **10/609 = 1.6%** | **10/609 = 1.642%**（None=0，故可测=全集） | ✅ 一致 | A.1 同上 |
| 4 | 可测行 **556 / 571 / 609** | **aitester 556（None 53）、df 571（None 38）、plain_llm 609（None 0）** | ✅ 一致 | A.1 `detNone` |
| 5 | 三臂 repair_rate 全 0（"非 None 且为 1"=0） | **repair_rate==1.0：0 / 0 / 0**；`==0.0`：**556 / 609 / 571**；`None`：53 / 0 / 38 | ✅ 一致（但表述需精确：plain_llm 是 609 个 0，aitester/df 另有 53/38 个 `None` 而非 0） | A.1 |
| 6 | `patch_correct=0` | **三臂 `patch_correct==1` 行数 = 0 / 0 / 0**（全 1827 行 `patch_correct==0`） | ✅ 一致 | A.1 末列 |
| 7 | 产物补丁行 aitester **251**（基线两臂 0） | **251 / 0 / 0**（aitester 另有 `patch=None` 349、`patch=""` 9） | ✅ 一致 | A.1 `patch_nonempty` |
| 8 | `passed=True` **389 / 535 / 15** | **389 / 535 / 15** | ✅ 一致 | A.1 `passed=True` |
| 9 | "7 批 × 3 臂 = 12,789 行" | **1827 行/批 × 7 = 12,789** | ✅ 一致 | A.1 行数求和 |
| 10 | 检出（全集口径）df **279/609 = 45.8%**、aitester 12.8% | **45.81% / 12.81%** | ✅ 一致 | A.1 中列 |

### 1.2 §3.4.1 `detection_first_status` 分解（aitester 609 行）

| # | 报告值 | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 11 | `all_green_unverified` **296（48.6%）**，全部 `iterations=0`、patch 为空 | **296（296/609 = 48.60%）**；`iterations` 全 0；`patch` 全为 `None`（无一是空串）；`detection_rate` 全 0.0 | ✅ 一致 | A.2 |
| 12 | `red_not_repaired` **167**，`iterations 2–3`，**158 有**补丁，检出 19 | **167**（iters `{2:132, 3:35}`）；patch 非空 **158**（另 9 空）；`detection_rate==1.0` **19**（`==0.0` 148） | ✅ 一致 | A.2 |
| 13 | `red_then_green` **93**，`iterations 1–3`，全部有补丁，检出 59 | **93**（iters `{1:76, 2:15, 3:2}`）；patch 非空 **93/93**；`det=1` **59**、`det=0` **34** | ✅ 一致 | A.2 |
| 14 | `None`（不可测）**53**，`iterations 0`，无补丁 | **53**；iters 全 0；patch 全空；`detection_rate` 全 `None` | ✅ 一致 | A.2 |
| 15 | "这 296 行从未进入修复循环" | 全部 `regeneration_count==1`、`test_regenerated_pass_unverified==True`、`stop_reason=='test_passed'`、`iterations==0` → 确未进入 repair 循环 | ✅ 一致（补充证据） | A.2 |
| 16 | K1："**两版生成测试都在缺陷原码上全绿，从未产生任何 assert 失败**" | 296 行的生成测试**均含 ≥3 处 `assert`**（均值 15.3，212/296 用 `pytest.raises`）；`test_error_rate` 全 0.0；`execution_trace` 全非空且末次 `passed=True`；`detection_first_red_seen` 全 False | ✅ **不算过强（属偏窄）**：字段保证严格强于"无 assert 失败"（详见 §3-S10） | A.2 + heredoc `re.findall(r"\bassert\b", r["generated_test"])` |
| 17 | K1："df 该比例仅 **2.5%（15/609）**" | **15/609 = 2.46%** | ✅ 一致 | A.2 末行 |

### 1.3 §3.4.2 通道对比与反事实分解

| # | 报告值 | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 18 | red_seen：aitester **260/609 = 42.7%**、df **556/609 = 91.3%** | **260/609 = 42.69%**；**556/609 = 91.30%** | ✅ 一致 | A.3 |
| 19 | 条件转化率 **78/260 = 30.0%** vs **279/556 = 50.2%** | **30.00%** vs **50.18%** | ✅ 一致 | A.3 |
| 20 | 缺口 = 279 − 78 = **201 行** | **201** | ✅ 一致 | A.3 |
| 21 | R-new 反事实：产红率 **44.2%**、转化率 **26.1%**、交互 **29.7%** | 序贯分解（以 aitester 为基准、含交互项）：**88.8 行（44.2%）+ 52.5 行（26.1%）+ 59.7 行（29.7%）= 201.0** | ✅ 一致 | A.3（见下方算法） |
| 22 | 单对齐后的检出水平（R-new §3.4.2 表：~167 / ~130） | 只对齐产红率 → **166.8 行**；只对齐转化率 → **130.5 行** | ✅ 一致 | A.3 |
| 23 | **R-old**："检出升至 ~244（+166）"/"~179（+101）"/"产红率缺口贡献约 **88%**" | **均不可复算**：244 ≈ 78 + 556×0.300 = 244.8（把"对齐后的新值 166.8"当增量又叠加了基数 78，双计）；+101 与 179 无法由任何标准分解或简单两/三项组合重建；88% 与"88.8 **行**"数值巧合，疑为单位混淆（行 vs %）。正确值：新值 166.8 / 130.5，增量 +88.8 / +52.5，占比 44.2% / 26.1% | ❌ **不一致（R-old 已作废；R-new 已修正）** | A.3；重建搜索见 §3-S5 |

**我采用的反事实算法（供复算）**：设 `p_a=260/609`、`c_a=78/260`、`p_d=556/609`、`c_d=279/556`，`N=609`；
总缺口 `G=(p_d·c_d−p_a·c_a)·N=201.0`；以 aitester 为基准的序贯（含交互）分解：
`产红率主效应=(p_d−p_a)·c_a·N=88.8`，`转化率主效应=p_a·(c_d−c_a)·N=52.5`，`交互=(p_d−p_a)·(c_d−c_a)·N=59.7`。
**该分解与次序有关**：改用以 df 为基准则为 `73.9% / 55.8% / −29.7%`（见 A.3 第二行）。报告当前只给一个次序的结果，未声明约定（见 §3-S5 建议措辞）。

### 1.4 §3.4.3 门 verdict × `detection_rate` 交叉表（对抗性重点）

| # | 报告值 | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 24 | `specific_red → detection_rate=1.0` **206/206** | **206/206**（全 7 批 3 臂） | ✅ 一致 | A.4 |
| 25 | `over_red → detection_rate=0.0` **244/244** | **244/244** | ✅ 一致 | A.4 |
| 26 | "例外仅 **2 行**" | 交叉表 **off-diagonal = 0**；`verdict=None ∧ detection=1.0` = **2 行**（即报告所称"例外"）——但**这 2 行不是门与指标的分歧行，而是"门根本没运行"的行** | ⚠️ **数值一致、定性不准确**（详见 §3-S2） | A.4 |
| 27 | "**全量**交叉表" | 交叉表只在 **4/7 批**存在（`20261007` 四批；`20261006` 三批**连 `specificity_gate_verdict` 键都没有**）；键存在行 **1044/1827**，其中 verdict 非 None 的只有 **450 行** | ⚠️ **"全量"用词不准确**（覆盖面为 450 行，非 1827 行） | A.4 |
| 28 | （报告未提）2 行例外是什么 | 2 行 = `plain_llm` 臂 / `synthetic__task_0002` / seed42 缓存重放对（`..161053` 与 `..181638`），**同一观测被计 2 次**；同行 `passed=True`、`detection_first_red_seen=False`、`detection_first_status=all_green_unverified`、`iterations=0`、`test_error_rate=0.0`、`execution_trace` 仅 1 条且 `passed=True`，却 `detection_rate=1.0`——**行内自相矛盾**。7 批全集中同类行共 **3 行**（另含 `20261006_140906` 同一任务） | ❌ 未披露，建议单列 | A.4 |

### 1.5 §3.5 修复（repair）口径与 QuixBugs

| # | 报告值 | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 29 | "原始工件 `repair_rate` 全为 0.0（7 批**可测 556/571 行**）" | aitester **556** 个 0（+53 None）、df **571** 个 0（+38 None）、**plain_llm 609 个 0**；三臂合计 **1736 个 0** | ⚠️ 数值一致但**分母表述不全**（漏掉 plain_llm 的 609 行；556/571 是两臂口径） | A.1 |
| 30 | QuixBugs aitester detection **17/37** | **17/37** | ✅ 一致 | A.7 |
| 31 | QuixBugs aitester repair **37/40** | **37/40**（`==0.0` 3 行、`None` 10 行，共 50 行） | ✅ 一致 | A.7 |
| 32 | QuixBugs **13 行** `plausible=0 ∧ correct=1`，全落 `skip_debugger_repair_invalid` / `iterations=2` | **13 行**，13/13 `stop_reason=skip_debugger_repair_invalid`、`iterations=2` | ✅ 一致 | A.7 |
| 33 | df 臂 detection **31/37**、repair **0/41**、`iterations` 全 0、patch 全空 | **31/37**、**0/41**（`None` 9）、iters **全 0（50/50）**、`patch` 非空 **0/50**、`stop_reason` 全 `unknown` | ✅ 一致 | A.7 |
| 34 | 全库 `repair_history` 键出现 **0/7,153** | **0/7153** | ✅ 一致 | A.9 |
| 35 | `patch_correct=1 ∧ patch_plausible=0` **129 行** | **129 行**；文件分布亦相符（`aitester.json` 13、`over_red_section_verified.json` 13、`a1_strip_fixedharness.json` 12…） | ✅ 一致 | A.9 |
| 36 | §3.5.1 独立重放 87→54→20→**0.3704** | **未复算**（需运行 `experiments.repair_replay`，非只读） | ❓ 见 §5 | — |

### 1.6 §3.7 真实仓库基准普查（`experiments/results/**/*.json`，按工件顶层 `dataset` 字段）

| # | 报告值 | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 37 | `swe_bench` **293 行** + `swe_bench_pro` **72 行** = **365 行** | **293 + 72 = 365** | ✅ 一致 | A.5 |
| 38 | 100% `instance_code` 为空 | **293/293、72/72 = 365/365 为空** | ✅ 一致 | A.5 |
| 39 | 100% 行内不存在 `detection_rate` 键 | **365/365 无该键** | ✅ 一致 | A.5 |
| 40 | `passed=True`：swe_bench **4**、pro **0** | **4 / 0**（合计 4/365） | ✅ 一致 | A.5 |
| 41 | "全部 **23 个**唯一真实仓库基准工件" | **23 个含 ≥1 行的工件**（swe_bench 11 + swe_bench_pro 12）；另有 `swebench_20_summary.json` 带 `dataset` 字段但 0 行（不计入，与"23"自洽） | ✅ 一致 | A.5 `artifacts` |
| 42 | `error_category` 为 `syntax`(**19**)/`patch_validation_failed`(**18**)/`execution_trace_missing`(**20**) 等 | 365 行普查实为：**swe_bench** `patch_validation_failed 76`、`""125`、`execution_trace_missing 59`、`syntax 28`、`import_error 2`、`index_error 1`、`timeout 1`、`unknown 1`；**swe_bench_pro** `patch_validation_failed 72`。报告的 19/18/20 实为**单个 60 行工件**的分布（`benchmark_swe_bench_20260925_162822.json` = 20/20/20 或 `..184622.json` = 18/19/23），**不是普查值** | ❌ **不一致** | A.5 `err_*`；单批定位：heredoc 遍历 `dataset=="swe_bench"` 且 `rows==60` 的工件 |
| 43 | （附注）`swe_bench` 293 行的构成 | 其中 **3 行** `task_metadata.source == 'examples'`（`benchmark_swe_bench_20260921_175906.json`，`total_tasks=3`，任务名 `examples__calculator_divide` 等），并非 SWE-bench 任务；不影响 100% 不可测结论 | ⚠️ 细节未披露（低） | A.5 + heredoc 打印该文件行 |

### 1.7 §3.8 伪重复（对抗性重点）

| # | 报告值 | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 44 | seed42 对（`..161053` ↔ `..181638`）逐值相同 **143/261**（aitester 45/87、plain_llm 49/87、df 49/87） | **按行序（positional）比较**：45/87、49/87、49/87 = **143/261**（与报告逐位相同）；**按 `task_id` 对齐比较**：**78/87、87/87、87/87 = 252/261** | ❌ **报告值只对"行序对齐"成立；该对齐无效**（两文件仅 49/87 个位置是同名任务）→ 报告**低估**重复度 | A.6 |
| 45 | seed44 对（`..170147` ↔ `..185941`）逐值相同 **140/261**（42/49/49） | 行序对齐：42/87、49/87、49/87 = **140/261**（与报告一致）；`task_id` 对齐：**75/87、87/87、87/87 = 249/261** | ❌ 同上 | A.6 |
| 46 | 比较字段 = `detection_rate`/`repair_rate`/`passed`/`generated_test`/`detection_first_status`/`specificity_gate_verdict`/`stop_reason`/`patch` | 本次用**同一字段集**、同一 `==` 语义复算；两对批次 `seed` 字段均为 42/42、44/44 | ✅ 字段集本身无误 | A.6 |
| 47 | "该 seed 真实独立值 `specificity_gate` 为 9/18" | `..161053` aitester：`specific_red=9`、`over_red=18`（另 60 行 None）；四批 aitester 合计 40/66 | ✅ 一致 | A.4 |
| 48 | §2.2 A6 / §7 G6 / P0-5 引用"140–143/261" | 同上，应为 **249–252/261**（`task_id` 对齐） | ❌ 连带需改 | A.6 |
| 49 | §3.8 机制："`AITESTER_LLM_CACHE_NAMESPACE` 按 seed 命名" | 代码中**不存在** `AITESTER_LLM_CACHE_NAMESPACE`；实际变量为 **`AITESTER_CACHE_NAMESPACE`**（`src/agents/base_agent.py:388`；`experiments/run_benchmark.py:2431-2432` 自动设 `seed<N>`），命名空间注释见 `:384-393`、`run_benchmark.py:2426-2432` | ❌ 变量名错误（机制结论不受影响） | `grep -rn AITESTER_LLM_CACHE_NAMESPACE .`（0 命中）；`grep -n AITESTER_CACHE_NAMESPACE src/agents/base_agent.py experiments/run_benchmark.py` |

### 1.8 §3.6 / K8 全库 `oracle_type` 普查

| # | 报告值 | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 50 | "**全库/全量** `oracle_type` 普查：`generated_test` **1,803**（aitester）/ `None` **1,672**" | 1,803/1,672 是**文件名以 `benchmark_` 开头的工件子集**的 aitester 计数（精确命中）；**全库** aitester 为 `generated_test 2,015` / 键缺失 `1,788`；**全部臂**合计 `generated_test 3,968` / 键缺失 `3,185`（总行 7,153） | ❌ **数字口径标注错误**（"全库/全量"名不副实；真值高 212 行/AITESTER、2,165 行/全臂） | A.8 |
| 51 | "`None` 1,672" | **键不存在**才是 1,672/1,788；**不存在"键存在且值为 None"的行**（全库 0 行） | ⚠️ 应为"键不存在"而非"None" | A.8 |
| 52 | "无一行 `enhanced_generated_test`（任何 enhanced/spec oracle）" | **确认**：全库**键存在且取值非 `generated_test` 的行数 = 0**；`oracle_type` 仅两种状态（`generated_test` 或键缺失） | ✅ 一致（结论成立且更强） | A.8 末行 |
| 53 | 7 批中 `spec_oracle_verdict` / `spec_oracle_injected` 键不存在 | **0/1827、0/1827** | ✅ 一致 | A.9 |

### 1.9 §3.3/§3.4.3/§3.8 的代码依据（"是否同一函数"等）

| # | 报告表述 | 代码核查结果 | 判定 | 复算命令 |
|---|---|---|---|---|
| 54 | "三臂的 detection 由同一个函数计算（`run_benchmark.py:1094` → `_m1_metrics.py` 的 `_compute_detection_rate`）" | **成立**：`run_benchmark.py:952 def _build_task_result(...)` 是**唯一**行构造器，被 5 处调用（`:1584, :1875, :1904, :1917, :1929`）覆盖全部臂；`:1094` 在同一构造器内调用 `_compute_detection_rate`；该名字在 `run_benchmark.py:536-542` 是**薄封装**，直接 `from experiments._m1_metrics import _compute_detection_rate`（实现 `_m1_metrics.py:473`）。**三臂共享同一 fail-to-pass 三段判据** | ✅ 有代码依据 | `grep -n "_build_task_result(\|_compute_detection_rate" experiments/run_benchmark.py`；`sed -n '536,542p;1088,1096p'` |
| 55 | "因此 −34.9pp 不是'口径不对称'造成的" | **该推论强于代码证据**：指标函数与判据同一，但**传入的 `final_state` 由各臂各自管线产出**（`aitester` 走完整图；`plain_llm_df` 为 `build_workflow(planner=False, debugger=False, allow_regeneration=True)` + 线程级 `set_detection_first_thread_override(True)`，见 `:381-421`）。故"指标定义对称"成立，"输入分布/管线行为对称"不成立 | ⚠️ 建议限定措辞 | `sed -n '381,421p;425,430p' experiments/run_benchmark.py` |
| 56 | 门"只取 `rc==0` 当绿（`detection_gates.py:96-121`），未复用 `_looks_like_test_execution_error`；且不传 `task_metadata`（`:85-87`）" | **成立**：`detection_gates.py:87` 为 `res = _runner(test_code, target_code, module_name, timeout=timeout)`（无 `task_metadata` 参数）；`grep` 显示 `_looks_like_test_execution_error` 与 `task_metadata` 在该文件**0 命中**；`green = res[0] == 0` | ✅ 一致（citation 行号落在函数体内，可接受） | `grep -n "_runner(test_code\|_looks_like_test_execution_error\|task_metadata" src/tools/detection_gates.py` |
| 57 | `MAX_REGENERATIONS=1`（`config.py:375`）、`workflow.py:682-699` 首轮全绿→regenerate、`:734-743` `_recent_repairs_invalid` 提前 done | **逐条成立**：`config.py:375 MAX_REGENERATIONS: int = 1`；`workflow.py:682-699` 即"首轮全绿且未 red_seen 且预算未用尽 → regenerate"；`:734-743` 即"`iteration < max_iterations` 且 `_recent_repairs_invalid` → done" | ✅ 一致 | `sed -n '682,699p;734,743p' src/graph/workflow.py`；`grep -n MAX_REGENERATIONS config.py` |

---

## 2. 引用抽查表（独立 `curl` 机读端点，HTTP 状态 + 标题/作者比对）

> 端点：`https://api.crossref.org/works/<DOI>`、`https://export.arxiv.org/api/query?id_list=<id>`。命令形如
> `curl -s -o out.json -w "HTTP %{http_code}\n" --max-time 25 "<URL>"`，再用 Python 解析 `message.title/author/container-title/published`。

| # | 引用（报告 §16） | URL | HTTP | 端点返回标题 / 作者 | 与报告一致？ | 判定 |
|---|---|---|---|---|---|---|
| C1 | CANDOR，TOSEM 2026，DOI 10.1145/3803418 | `https://api.crossref.org/works/10.1145/3803418` | **200** | *Hallucination to Consensus: Multi-Agent LLMs for End-to-End JUnit Test Generation* / Xu Qinghua, Wang Guancheng, Briand Lionel, Liu Kui / ACM TOSEM / 2026-03-25 | **完全一致** | ✅ A |
| C2 | TestAgent，DOI 10.1145/3803437.3806428 | `.../10.1145/3803437.3806428` | **200** | *TestAgent: A Multi-Agent LLM Framework for Repository-Level Unit Test Generation* / Shang Ye, Zhang Quanjun, Zhan Zhengyu, Huang Ke, Fang Chunrong, Chen Zhenyu / *Proceedings of the 34th ACM International Conference on the Foundations of Software Engineering* / 2026-07-05 | 标题、作者、年份一致；**容器名未含 "Companion"**（报告写 "FSE Companion 2026"） | ✅（venue 后缀待核，低） |
| C3 | Konstantinou 等，ICST 2026，DOI 10.1109/icst69053.2026.00040 | `.../10.1109/icst69053.2026.00040` | **200** | *How well LLM-based test generation techniques perform with newer LLM versions?* / Konstantinou Michael, Degiovanni Renzo, Papadakis Mike / *2026 IEEE International Conference on Software Testing, Verification and Validation (ICST)* / 2026-05-18 | **完全一致** | ✅ A |
| C4 | AdverTest，DOI 10.1145/3832122（ISSTA 2026） | `.../10.1145/3832122` | **200** | *Test vs Mutant: Adversarial LLM Agents for Robust Unit Test Generation* / Chang Pengyu, Fang Yixiong, Chen Silin, Shi Yuling, Shen Beijun, Gu Xiaodong / *Proceedings of the ACM on Software Engineering* / 2026-10-01 | 标题、作者一致；PACMSE 卷 = ISSTA 会议录，与"IsSTA 2026"自洽 | ✅ A |
| C5 | Zhao/Zhou/Cohen，DOI 10.1145/3832093（ISSTA 2026） | `.../10.1145/3832093` | **200** | *Do Coverage and Mutation Scores of LLM-Generated Test Suites Correlate with Their Effectiveness? (Replicability Study)* / Zhao Junda, Zhou Shurui, Cohen Eldan / PACMSE / 2026-10-01 | **一致**（报告写 "Zhao, J., Zhou, S., Cohen, E."，端点给出 Junda/Shurui/Eldan） | ✅ A |
| C6 | arXiv:2609.09315 | `https://export.arxiv.org/api/query?id_list=2609.09315` | **200**（entries=1） | *How effective are traditional test criteria at detecting bugs in large language models generated code?* / Asma Hamidi, Michael Konstantinou, Renzo Degiovanni, Mike Papadakis / published **2026-09-08** | **完全一致**（报告 §16[1] 作者、日期、标题逐项相符） | ✅ A |
| C7 | arXiv:2609.17394 | `...?id_list=2609.17394` | **200**（entries=1） | *Coding Agents Have Converged: Why the SWE-bench Leaderboard Can No Longer Order Its Top Entries, and What to Measure Instead* / Fengshuo Liu, Ying Liu, Ruize Sun, Lie Luo, Siyuan Guo / **2026-09-15** | 标题、作者一致；**报告标注的 "ADMA 2026" 未在 arXiv 元数据中出现，本次未核** | ✅（数值级一致）/ venue 见 §5 |
| C8 | arXiv:2602.08146 | `...?id_list=2602.08146` | **200**（entries=1） | *Test vs Mutant: Adversarial LLM Agents for Robust Unit Test Generation* / Pengyu Chang, Yixiong Fang, Silin Chen, Yuling Shi, Beijun Shen, Xiaodong Gu / **2026-02-08** | **完全一致**（与 C4 同一工作） | ✅ A |
| C9 | （附加，用于核 K9）arXiv:2601.09695 | `...?id_list=2601.09695` | **200** | *How well LLM-based test generation techniques perform with newer LLM versions?* / Konstantinou, Degiovanni, Papadakis；摘要内出现 **17.72% / 19.80% / 20.92%** | 与 K9 的"该文原文报告相对提升 17.72/19.80/20.92%"一致；项目 `README.md:27` 确将其写成 "Plain-LLM 49.95/35.33/33.82" | ✅ A（**支持 K9**） |

**结论**：8 个指定引用 **8/8 端点 HTTP 200，标题/作者与报告一致**；无虚构引用。仅 C2 的 venue 后缀（Companion）与 C7 的 venue（ADMA）未获端点直接背书。

---

## 3. 主动找茬：应修正清单（按严重度排序，附建议措辞）

> 严重度定义：**高** = 数字或定性结论不成立/不可复算；**中** = 数字口径标注错误或关键限定缺失，可能被审稿人直接质疑；**低** = 事实性小错/表述可更严谨。

### S1（高）§3.8（第 353–354 行）+ §2.2 A6（第 171 行）+ §7 G6/G7 + P0-5（第 744 行）：伪重复行数用"行序对齐"比较，**低估**重复度

- 报告值：`143/261`、`140/261`（附 aitester 45/42、plain_llm 49/49、df 49/49）。
- 我复算：这两个数**只能用"按列表下标逐位比较"复现**；但两文件**任务顺序不同**（仅 **49/87** 个位置是同一 `task_id`）。按 `task_id` 对齐、用报告自己声明的 8 个字段比较 → **252/261**（78/87、87/87、87/87）与 **249/261**（75/87、87/87、87/87）。
- 影响：结论方向不变（同 seed 重跑确为缓存确定性重放），但报告数字**低报约 10pp**；plain_llm/df 两臂实为**逐行完全相同**（87/87），报告写 49/87 会被轻易证伪。
- 建议措辞：*"同 seed 两批按 `task_id` 对齐后，8 个核心字段逐值相同的行数为 **252/261**（seed42：aitester 78/87、plain_llm 87/87、df 87/87）与 **249/261**（seed44：75/87、87/87、87/87）——即 96% 的行是缓存的确定性重放。注意两批任务顺序不同（仅 49/87 位置同名），任何按下标对齐的比较都会低估重复度。"*

### S2（高）§3.4.3（第 283 行）+ §0.2 K2（第 42 行）+"例外仅 2 行"与"全量交叉表"两处不准确

- 事实 A：门判据只在 **`20261007` 四批**落盘（`20261006` 三批**无 `specificity_gate_verdict` 键**）。"全量"实际覆盖 = 键存在 1044 行 / verdict 非 None **450 行**（不是 1827 行）。
- 事实 B：有 verdict 的行 **off-diagonal = 0**（`specific_red→1.0` 206/206；`over_red→0.0` 244/244）——报告的核心等价性**成立**。
- 事实 C：所谓"2 行例外"是 `verdict=None ∧ detection_rate=1.0`：`plain_llm` 臂 `synthetic__task_0002`，seed42 缓存重放对的两个副本（同一观测计两次；7 批中共 3 行）。**它们不是门与指标的分歧，而是"门未运行"的行**；更严重的是**这 3 行自身矛盾**：`detection_rate=1.0` 与同行 `passed=True`、`detection_first_red_seen=False`、`detection_first_status=all_green_unverified`、`iterations=0`、`execution_trace=[{passed:True}]` 直接冲突。
- 建议措辞：*"在门实际运行的 450 行（E1/E2 四批）上，`specific_red→det=1` 206/206、`over_red→det=0` 244/244，off-diagonal 为 0；另有 2 行（同一任务 `synthetic__task_0002` 的缓存重放副本，7 批共 3 行）门未运行却 `detection_rate=1.0`，且与同行 `passed=True / red_seen=False / iterations=0` 自相矛盾——该异常应单列，不应作为'门的例外'，也不应计入门-指标等价性的分母。"*

### S3（中）K8（第 48 行）/§2.1（第 155 行）/§3.6（第 329 行）/§11 C-10（第 789 行）：`oracle_type` 计数被标为"全库/全量"，实为 `benchmark_*.json` 文件名子集

- 报告值：**全库** `generated_test` 1,803（aitester）/ `None` 1,672。
- 我复算：1,803 / 1,672 精确等于"文件名以 `benchmark_` 开头的工件"子集；**全库**为 aitester `generated_test` **2,015**、键缺失 **1,788**；全臂合计 `generated_test` **3,968**、键缺失 **3,185**（总行 7,153，与 §2.2 A7/§3.11 使用的 7,153 一致）。
- 另有口径错：1,672 是"**键不存在**"，不是"值为 `None`"——全库**没有**任何"键存在且值为 None"的行。
- 结论（0 行 enhanced/spec oracle）**不受影响且已独立确认**。
- 建议措辞：*"全库 7,153 行中 aitester 2,015 行 `oracle_type='generated_test'`、1,788 行不含该键；全部臂合计 3,968 / 3,185。**没有任何一行取 `generated_test` 以外的值**（即 0 行增强/规约 oracle）。若仅统计 `benchmark_*.json` 工件，aitester 为 1,803 / 1,672。"*

### S4（中）§3.7（第 346 行）：`error_category` 的 "(19)/(18)/(20)" 不是 365 行普查结果

- 我复算普查值：`patch_validation_failed` **148**（swe_bench 76 + pro 72）、`execution_trace_missing` **59**、`syntax` **28**、空串 125、`import_error` 2、`index_error` 1、`timeout` 1、`unknown` 1。
- 19/18/20 精确对应**单个 60 行工件**的分布（如 `benchmark_swe_bench_20260925_184622.json` = syntax? 实测为 `{'' 23, patch_validation_failed 18, execution_trace_missing 19}`；`..162822.json` = 20/20/20）——按上下文它被当成普查分布引用。
- 建议措辞：*"365 行的 `error_category` 普查：`patch_validation_failed` 148、`execution_trace_missing` 59、`syntax` 28、空串 125 等（以 lite20 单批 60 行为例，则三类分别为 18/19/20）。"*

### S5（中）§3.4.2 反事实分解：当前版算术成立，但缺"分解次序约定"声明；旧版 88% 系口径错误（已被就地更正）

- 当前版 44.2% / 26.1% / 29.7% 我独立复算**逐位一致**（算法见 §1.3）。
- 但序贯分解**依赖次序**：以 df 为基准则为 73.9% / 55.8% / −29.7%。报告未声明"以 aitester 为基准"。
- 旧版（R-old）的"88% / ~244（+166）/ ~179（+101）"不可复算：244 = 78 + 556×0.300 属**基数双计**（正确新值 166.8）；+101/179 无法从工件重建；"88%"疑为把"88.8 行"写成百分比。
- 建议措辞：*"反事实分解采用**以 aitester 为基准的序贯（含交互项）分解**：产红率主效应 (0.913−0.427)×0.300×609 = +88.8 行（44.2%）、转化率主效应 0.427×(0.502−0.300)×609 = +52.5 行（26.1%）、交互 +59.7 行（29.7%）；若改用 df 基准，三者为 148.5/112.2/−59.7 行（73.9%/55.8%/−29.7%），故结论'产红率是最大单一因子'应限定在该次序约定下。"*

### S6（低）§3.8（第 357 行）：缓存命名空间变量名写错

- 报告写 `AITESTER_LLM_CACHE_NAMESPACE`；代码实为 **`AITESTER_CACHE_NAMESPACE`**（`src/agents/base_agent.py:388`；`experiments/run_benchmark.py:2431-2432` 自动设 `seed{seed}`）。全仓对错误变量名 **0 命中**。
- 建议：直接替换变量名。

### S7（低）§3.5.1（第 288 行附近）："7 批可测 556/571 行"易误读

- 实际：aitester 556 个 0（+53 `None`）、df 571 个 0（+38 `None`）、**plain_llm 609 个 0**；三臂合计 1736 个 0，且 `patch_correct==1` 全库为 0。
- 建议措辞：*"7 批三臂 `repair_rate` 无一为 1.0：`0.0` 共 1736 行（aitester 556、plain_llm 609、df 571），另 91 行为 `None`（不可测）；`patch_correct=1` 行数为 0。"*

### S8（低）§3.7：`swe_bench` 293 行中含 3 行非 SWE-bench 行

- `benchmark_swe_bench_20260921_175906.json`（`dataset=swe_bench`, `total_tasks=3`）的 3 行 `task_metadata.source='examples'`（`examples__calculator_divide` 等）。
- 建议：加一句括注，或按 `task_metadata.source` 复核该文件归类；不影响"100% 不可测"。

### S9（低）§5.1 / §5.2 / §0.4（第 72 行）："不可比"维度上仍给出比较性判定（内部张力）

- 事实：§5.1 的"绝对差距/相对差距"两列**全部为 "—"**，纪律的字面要求（不给差距数字）**成立**。
- 但"程序修复：端到端成功率"行 `可否对比=否（任务分布差异过大，仅可作方向性判断）`，同一行"竞争位置"却写 **"落后（合成集）"**；§5.2 进一步写"**程序修复 | 落后**（合成集 all-task 21.84%；真实基准仅玩具程序 74.0%）"；§0.4 写"**低于** SWE-bench Verified 一线方法数量级"。把"自生成合成集 all-task 21.84%"与"SWE-bench Verified 榜首 396/500=79.2%"并置，构成事实上的数量级对比，与"否（不可比）"冲突。
- 建议措辞：*"程序修复：合成集 all-task 21.84%（57/261）、可重放口径 39.31%；与 SWE-bench Verified 79.2% **任务分布不同，不构成数量级对比**，仅可判定'未在公开基准上建立可比的端到端修复证据'。"*

### S10（低）K1/§5.1："从未产生 assert 失败"——**不是过强，而是偏窄**（建议改得更准）

- 字段定义（`src/graph/nodes.py:649-672` + `src/graph/state.py:184`）：`all_green_unverified` = 终态 `passed=True ∧ detection_first_red_seen` 为假；其中 `red_seen` 只在 `iteration==0` 写、且为**粘性**（任一次首轮执行 `not passed` 即 True）。
- 因此该字段的保证是"**首轮与再生成版在缺陷原码上都没有出现任何非零退出**（含断言失败、收集/导入错误）"——**严格强于**"没有 assert 失败"。故 K1 的措辞并不过强。
- 佐证（我复算）：296 行 `iterations=0`、`regeneration_count=1`、`test_regenerated_pass_unverified=True`（第二版也通过）、`test_error_rate=0.0`、`execution_trace` 全非空、生成测试**每行 ≥3 处 `assert`**（均值 15.3）。故"两版都在缺陷原码上全绿"成立。
- 建议措辞：*"48.6%（296/609）的 aitester 行终态为 `all_green_unverified`：首版与再生成版在缺陷原码上均 rc==0 全绿（`red_seen=False`、`iterations=0`、无补丁），从未出现任何红灯——既未覆盖到缺陷，也未产出可归因的断言失败。该字段本身不区分'测试没覆盖缺陷'与'断言写错/写反'（见 K7）。"*

### 附带观察（低，跨文档）

`audit_2026/T_B_code_domain_audit.md` 的反事实口径（"只对齐 red 产生率 → 28.1%；只对齐转化率 → 20.9%"）与报告 §3.4.2 的基数不同：其隐含 aitester red_seen = **254**，恰等于 **`20261006` 三批**的 df red_seen 计数（我复算：10-06 三批 df red_seen=254、aitester red_seen=154；10-07 四批 df=302、aitester=106；7 批 df=556、aitester=260）。两文件若被同一审稿人交叉阅读，会看到不一致的反事实百分比；建议统一到 §1.3 的算法与基数（aitester 260/609、df 556/609）。

---

## 4. 对四项指定深查的直接回答

1. **"48.6% 的行从未产生 assert 失败"是否与工件字段一致？** → **一致，但措辞偏窄**。字段语义是"从未变红（首轮与再生成版均 rc==0）"，比"无 assert 失败"更强；296 行确有断言（≥3 处/行）且执行痕迹完整。建议按 §3-S10 改词。
2. **"产红率缺口贡献约 88%" 是否可复算？** → **R-old 不可复算**（正确：主效应 88.8 **行** = 44.2%，另转化率 52.5 行 = 26.1%、交互 59.7 行 = 29.7%）；**R-new 已改为 44.2/26.1/29.7，我复算一致**。算法与次序依赖见 §1.3、§3-S5。
3. **"三臂同一函数计算 detection" 是否有代码依据？** → **有**（`_build_task_result` 唯一构造器 + `:1094` + 薄封装 `:536-542` → `_m1_metrics.py:473`）；但"因此 −34.9pp 与口径不对称无关"是**推论**，需限定为"指标定义与判据对称；输入状态由各臂各自管线产出"（§3-S54/55）。
4. **§5 的"不能对比"判定是否内部矛盾？** → **无差距数字**（两列全 "—"，字面纪律成立）；**但存在判定级矛盾**：标"否"的程序修复行仍给"落后"，§0.4 用"低于……数量级"把合成集 21.84% 与 SWE-bench Verified 79.2% 并置（§3-S9）。

---

## 5. 我无法验证的项（明确声明，不以推断填充）

| # | 项 | 原因（具体） |
|---|---|---|
| U1 | **R-old 报告的 sha256** | 文件在审计中途（10:42→10:44:59）被就地覆盖；该文件未被 git 跟踪，全盘检索无副本。只能提供我阅读时的大小（133,651 B）与原文引述 |
| U2 | §3.5.1 的独立重放链（带补丁 **87** → 可重放 **54** → correct **20** → **0.3704**）与 §3.1 P2/P3 的 39.31% / 54.72% | 需要运行 `experiments.repair_replay`（会执行 gold 测试，非只读）；本次只读范围外。本次仅确认**原始工件** `repair_rate` 无一为 1.0、`patch_correct==1` 为 0（与报告一致） |
| U3 | `~/.cache` 内 **225 个** SWE-bench 实例缓存"0 行含 `instance_code`" | 未访问 `~/.cache`（本次只读范围限定在仓库内工件） |
| U4 | §3.9 成本口径（E1/E2 **348/348** 行 0-token、df 35/261、E6 phase1 0/87、$/task 比值） | 未复算（非本次指定范围）；仅确认 7 批行内 `token_usage` 字段存在 |
| U5 | §3.10 三个孤儿进程（pid 36935/37116/37498）、§3.2 测试全量跑批（5,311 passed / 2 failed）、§1.2 文件规模（7,502 文件 / 103.5 MB / 行数统计） | 未复算（需运行进程/测试套件或全目录遍历统计，超出本次只读抽样范围） |
| U6 | §4/§5 中前沿数值的**正文级**核对（如 F-1 的"检出率 1–2%"、TestAgent 97.46/92.34、ULT 45.10、SWE-bench Verified 396/500、TraceCoder +34.43%、LANTERN +22.09%） | 本次只核**元数据端点**（标题/作者/venue/日期），未逐篇读全文核对每个指标；该部分属 `T_C`/`T_D` 的职责范围 |
| U7 | venue 标注：arXiv:2609.17394 的 "ADMA 2026"、TestAgent 的 "FSE **Companion** 2026" | Crossref/arXiv 元数据未直接给出该后缀；未进一步查会议录目录 |
| U8 | §3.7 的"代码归因"（`_extract_gold_material` 对 `source=="swe_bench"` 直接 `return None`、`_gold_fixed_code` 返回 `""`、detection 要求 `instance_code` 非空） | 本次**部分**核到：`_m1_metrics.py:506-508` 的 `instance_code` 判空我读到了；`430-431`/`462-463` 两处仅按报告行号抽查上下文，未逐行核验 return 语句（属 `T_B` 范围） |
| U9 | QuixBugs 数值的**口径**判定（17/37 是否等价于"缺陷检出能力"、df 臂"不可比"的强度） | 我只能复算数值；口径合理性属判断问题，本次不代替领域结论 |
| U10 | §3.4.1 "第二版仍全绿 → 直接 done"的**完整轨迹** | 工件只落最终 `detection_first_status`/`regeneration_count`/`test_regenerated_pass_unverified`，无逐轮 trace 落盘；我用字段组合（296/296 均为 `iterations=0 ∧ red_seen=False ∧ 第二版 passed=True`）**推断**成立，未取得逐轮证据 |

---

## 6. 验证结论

1. **§3.3 三臂核心数字（detection、可测行、repair、patch、passed）逐位复算一致**；§3.4.1 的 296/167/93/53 及其不变式（iterations/patch/det）**逐位一致**；§3.4.2 的 red_seen 与转化率**逐位一致**；§3.4.3 的 206/206、244/244 **逐位一致**；§3.5 的 QuixBugs 与全库不变量（repair_history 0/7153、129 行违反）**一致**；§3.7 的 293+72=365、100%/100%、passed=4 **一致**；§1.8 的"0 行 enhanced/spec oracle" **确认成立**。
2. **发现 3 处不应放过的实质问题**：**S1**（§3.8 伪重复用行序对齐 → 252/249 被写成 143/140，低报 10pp）、**S2**（§3.4.3"全量交叉表/例外 2 行"口径不实，且那 2 行是 metric 与信号自相矛盾的异常行）、**S3**（K8 的 1,803/1,672 被标为"全库"，实为 `benchmark_*` 子集；全库 aitester 为 2,015）。
3. **R-old 的"88%"反事实错误已在 R-new 中更正**，更正后的 44.2/26.1/29.7 我独立复算一致；但需补"分解次序约定"（S5）。
4. **8/8 指定引用真实**（HTTP 200，标题/作者一致），无虚构；K9 关于 arXiv:2601.09695 的更正**得到端点支持**。
5. **未复算项已逐条列于 §5**（含 R-old 哈希不可得、repair 重放链、成本/覆盖率/测试套件/前沿正文数值）。

---

## 附录 A：一次性复算脚本（本次实际执行，未写入仓库）

执行方式（本次实跑）：

```bash
cd /Users/wangchenyu/Workspace/AITester
cat > /tmp/t_e_repro.py <<'PY'   # ← 下方 A.1–A.10 全文
...
PY
.venv/bin/python /tmp/t_e_repro.py 2>&1 | tee /tmp/t_e_repro.out
```

### A.1–A.10 脚本全文

```python
"""T-E 对抗式验证：一次性只读复算脚本（零 LLM）。运行：.venv/bin/python /tmp/t_e_repro.py"""
import json, glob, os, collections, itertools, hashlib
R = "experiments/results"
def rows_of(f, arm):   return json.load(open(f))["results"][arm]["details"]
MAIN = sorted(glob.glob(f"{R}/main_batch/benchmark_synthetic_2026100[67]_*.json"))
ARMS = ("aitester", "plain_llm", "plain_llm_df")

print("### 1. 7 批 × 3 臂（文件数=%d）" % len(MAIN))
for arm in ARMS:
    rs = [r for f in MAIN for r in rows_of(f, arm)]
    det = [r.get("detection_rate") for r in rs]
    meas = [x for x in det if x is not None]
    rep = [r.get("repair_rate") for r in rs]
    print(f"[{arm}] rows={len(rs)} det=1:{sum(1 for x in meas if x==1.0)}/{len(meas)} "
          f"({sum(1 for x in meas if x==1.0)/len(meas)*100:.1f}%) detNone={len(det)-len(meas)} "
          f"| all-rows {sum(1 for x in det if x==1.0)}/{len(det)}={sum(1 for x in det if x==1.0)/len(det)*100:.1f}% "
          f"| repair=1:{sum(1 for x in rep if x==1.0)} repair=0:{sum(1 for x in rep if x==0.0)} repNone:{sum(1 for x in rep if x is None)} "
          f"| patch_nonempty:{sum(1 for r in rs if (r.get('patch') or '').strip())} "
          f"| passed=True:{sum(1 for r in rs if r.get('passed') is True)} | patch_correct=1:{sum(1 for r in rs if r.get('patch_correct')==1)}")

A = [r for f in MAIN for r in rows_of(f, "aitester")]
D = [r for f in MAIN for r in rows_of(f, "plain_llm_df")]
print("\n### 2. aitester(detection_first_status / iterations / patch / det)")
st = collections.Counter(r.get("detection_first_status") for r in A)
for k, v in st.most_common():
    sub = [r for r in A if r.get("detection_first_status") == k]
    print(f"  {str(k):22} n={v:3} ({v/len(A)*100:.1f}%) iters={dict(collections.Counter(r.get('iterations') for r in sub))} "
          f"patch_nonempty={sum(1 for r in sub if (r.get('patch') or '').strip())} "
          f"det1={sum(1 for r in sub if r.get('detection_rate')==1.0)} det0={sum(1 for r in sub if r.get('detection_rate')==0.0)}")
ag = [r for r in A if r.get("detection_first_status")=="all_green_unverified"]
print(f"  all_green 不变式: iterations全0={all(r.get('iterations')==0 for r in ag)} "
      f"patch全None/空={all(not (r.get('patch') or '').strip() for r in ag)} det全0={all(r.get('detection_rate')==0.0 for r in ag)} "
      f"passed全True={all(r.get('passed') is True for r in ag)} red_seen全False={all(r.get('detection_first_red_seen') is False for r in ag)} "
      f"regeneration_count={dict(collections.Counter(r.get('regeneration_count') for r in ag))} "
      f"test_regenerated_pass_unverified全True={all(r.get('test_regenerated_pass_unverified') is True for r in ag)} "
      f"execution_trace非空={sum(1 for r in ag if r.get('execution_trace'))}/{len(ag)} "
      f"test_error_rate全0={all(r.get('test_error_rate')==0.0 for r in ag)}")
print(f"  df all_green_unverified={sum(1 for r in D if r.get('detection_first_status')=='all_green_unverified')}/{len(D)}")

print("\n### 3. red_seen / 转化率 / 反事实分解")
pa, ca = sum(1 for r in A if r.get('detection_first_red_seen') is True)/len(A), 78/260
pd, cd = sum(1 for r in D if r.get('detection_first_red_seen') is True)/len(D), 279/556
print(f"  aitester red_seen={pa*len(A):.0f}/{len(A)}={pa*100:.1f}%  df red_seen={pd*len(D):.0f}/{len(D)}={pd*100:.1f}%")
print(f"  转化率 aitester=78/260={ca*100:.1f}%  df=279/556={cd*100:.1f}%")
N, ga = len(A), 279-78
e1 = (pd-pa)*ca*N; e2 = pa*(cd-ca)*N; inter = ga-e1-e2
print(f"  aitester-base 3 项分解: 产红率={e1:+.1f} ({e1/ga*100:.1f}%) 转化率={e2:+.1f} ({e2/ga*100:.1f}%) 交互={inter:+.1f} ({inter/ga*100:.1f}%) 合计={e1+e2+inter:.1f}/{ga}")
f1 = (pd-pa)*cd*N; f2 = pd*(cd-ca)*N
print(f"  df-base 3 项分解      : 产红率={f1:+.1f} ({f1/ga*100:.1f}%) 转化率={f2:+.1f} ({f2/ga*100:.1f}%) 交互={ga-f1-f2:+.1f} ({(ga-f1-f2)/ga*100:.1f}%)")
print(f"  单对齐新值: 产红率对齐 -> {pd*ca*N:.1f} 行; 转化率对齐 -> {pa*cd*N:.1f} 行")

print("\n### 4. 门 verdict × detection_rate（3 臂）")
allrows = [r for f in MAIN for arm in ARMS for r in rows_of(f, arm)]
ct = collections.Counter((str(r["specificity_gate_verdict"]), r.get("detection_rate")) for r in allrows if "specificity_gate_verdict" in r)
print("  键存在行数=%d / 总行数=%d" % (sum(ct.values()), len(allrows)), dict(ct))
print("  verdict=非 None 的行数:", sum(1 for r in allrows if r.get("specificity_gate_verdict")))
gate_files = sorted({os.path.basename(f) for f in MAIN if any(r.get("specificity_gate_verdict") for arm in ARMS for r in rows_of(f, arm))})
print("  含非 None verdict 的批次:", len(gate_files), [x[-15:-5] for x in gate_files])
anom = [(f.split('/')[-1], arm, r.get("task_id")) for f in MAIN for arm in ARMS for r in rows_of(f, arm)
        if r.get("detection_rate")==1.0 and r.get("detection_first_red_seen") is not True]
print("  detection=1 但 red_seen≠True 的行:", anom)

print("\n### 5. SWE 普查（按工件顶层 dataset 字段）")
c = collections.defaultdict(lambda: collections.Counter()); fileset = collections.defaultdict(set)
for f in sorted(glob.glob(f"{R}/**/*.json", recursive=True)):
    try: d = json.load(open(f))
    except Exception: continue
    if not isinstance(d, dict) or d.get("dataset") not in ("swe_bench", "swe_bench_pro"): continue
    for arm, v in (d.get("results") or {}).items():
        for r in (v.get("details") or []):
            e = c[d["dataset"]]; e["rows"] += 1
            md = r.get("task_metadata") if isinstance(r.get("task_metadata"), dict) else {}
            if not str(md.get("instance_code") or "").strip(): e["no_instance_code"] += 1
            if "detection_rate" not in r: e["no_detkey"] += 1
            if r.get("passed") is True: e["passed"] += 1
            e["err_" + str(r.get("error_category"))] += 1
            fileset[d["dataset"]].add(f)
for ds in ("swe_bench", "swe_bench_pro"):
    e = c[ds]
    print(f"  [{ds}] rows={e['rows']} no_instance_code={e['no_instance_code']} no_detection_key={e['no_detkey']} passed=True={e['passed']} files={len(fileset[ds])}")
print("  合计 rows=%d  artifacts=%d" % (sum(e['rows'] for e in c.values()), len(fileset['swe_bench'] | fileset['swe_bench_pro'])))

print("\n### 6. 伪重复：按 task_id 对齐 vs 按行序（positional）")
F8 = ["detection_rate","repair_rate","passed","generated_test","detection_first_status","specificity_gate_verdict","stop_reason","patch"]
for a, b, tag in (("benchmark_synthetic_20261007_161053.json","benchmark_synthetic_20261007_181638.json","seed42"),
                  ("benchmark_synthetic_20261007_170147.json","benchmark_synthetic_20261007_185941.json","seed44")):
    da = json.load(open(f"{R}/main_batch/{a}")); db = json.load(open(f"{R}/main_batch/{b}"))
    print(f"  [{tag}] seeds {da.get('seed')}/{db.get('seed')}")
    tot_al = tot_pos = 0
    for arm in ARMS:
        la, lb = da["results"][arm]["details"], db["results"][arm]["details"]
        mb = {x["task_id"]: x for x in lb}
        al = sum(1 for x in la if all(x.get(k) == mb[x["task_id"]].get(k) for k in F8))
        pos = sum(1 for x, y in zip(la, lb) if all(x.get(k) == y.get(k) for k in F8))
        order = sum(1 for x, y in zip(la, lb) if x["task_id"] == y["task_id"])
        tot_al += al; tot_pos += pos
        print(f"     {arm:12} task_id对齐={al}/87  行序对齐={pos}/87  同位置同task={order}/87")
    print(f"     合计: task_id 对齐 {tot_al}/261 ; 行序对齐 {tot_pos}/261")

print("\n### 7. QuixBugs")
for name, arm in (("aitester.json","aitester"), ("plain_llm_df.json","plain_llm_df")):
    rs = json.load(open(f"{R}/e6_a1_batches/e4_quixbugs_FIXED_harness/{name}"))["results"][arm]["details"]
    det = [r.get("detection_rate") for r in rs]; rep = [r.get("repair_rate") for r in rs]
    dm = [x for x in det if x is not None]; rm = [x for x in rep if x is not None]
    print(f"  [{arm}] rows={len(rs)} det=1:{sum(1 for x in dm if x==1.0)}/{len(dm)} repair=1:{sum(1 for x in rm if x==1.0)}/{len(rm)} "
          f"iters={dict(collections.Counter(r.get('iterations') for r in rs))} patch_nonempty={sum(1 for r in rs if (r.get('patch') or '').strip())} "
          f"plausible0&correct1={sum(1 for r in rs if r.get('patch_plausible')==0 and r.get('patch_correct')==1)} "
          f"stop={dict(collections.Counter(str(r.get('stop_reason')) for r in rs))}")

print("\n### 8. oracle_type 全库普查")
tot = collections.Counter(); byarm = collections.Counter(); bench = collections.Counter()
for f in sorted(glob.glob(f"{R}/**/*.json", recursive=True)):
    try: d = json.load(open(f))
    except Exception: continue
    if not isinstance(d, dict): continue
    for arm, v in (d.get("results") or {}).items():
        if not isinstance(v, dict): continue
        for r in (v.get("details") or []):
            if not isinstance(r, dict): continue
            k = "absent" if "oracle_type" not in r else str(r.get("oracle_type"))
            tot[k] += 1; byarm[(arm, k)] += 1
            if os.path.basename(f).startswith("benchmark_"): bench[(arm, k)] += 1
print("  全库按值:", dict(tot))
print("  全库 aitester:", {k: v for k, v in byarm.items() if k[0] == "aitester"})
print("  benchmark_*.json 子集 aitester:", {k: v for k, v in bench.items() if k[0] == "aitester"})
print("  非 generated_test 且键存在的行:", sum(v for k, v in tot.items() if k not in ("generated_test", "absent")))

print("\n### 9. 其他不变量")
rh = viol = n = 0
for f in sorted(glob.glob(f"{R}/**/*.json", recursive=True)):
    try: d = json.load(open(f))
    except Exception: continue
    if not isinstance(d, dict): continue
    for arm, v in (d.get("results") or {}).items():
        for r in (v.get("details") or []):
            if not isinstance(r, dict): continue
            n += 1
            if "repair_history" in r: rh += 1
            if r.get("patch_correct") == 1 and r.get("patch_plausible") == 0: viol += 1
print(f"  全库行数={n} repair_history 键={rh} patch_correct=1&plausible=0={viol}")
for k in ("spec_oracle_injected", "spec_oracle_verdict"):
    p = sum(1 for f in MAIN for arm in ARMS for r in rows_of(f, arm) if k in r)
    print(f"  7 批中 {k} 键存在行数={p}/1827")
print("\n### 10. 报告文件指纹")
h = hashlib.sha256(open("FINAL_REVIEW_2026-10-11.md","rb").read()).hexdigest()
print("  sha256(FINAL_REVIEW_2026-10-11.md) =", h, "size=", os.path.getsize("FINAL_REVIEW_2026-10-11.md"))
```

> 注：脚本内 `# ### 2` 段对 `all_green` 的"两版全绿"结论只依赖 `iterations/regeneration_count/test_regenerated_pass_unverified/red_seen` 四个字段；生成测试的 `assert` 计数与 `execution_trace` 详情由另一次 heredoc 命令取得（见 §1.2 第 16 行"复算命令"）。

### A.11 关键输出（本次实跑，逐字摘录）

```
### 1. 7 批 × 3 臂（文件数=7）
[aitester] rows=609 det=1:78/556 (14.0%) detNone=53 | all-rows 78/609=12.8% | repair=1:0 repair=0:556 repNone:53 | patch_nonempty:251 | passed=True:389 | patch_correct=1:0
[plain_llm] rows=609 det=1:10/609 (1.6%) detNone=0 | all-rows 10/609=1.6% | repair=1:0 repair=0:609 repNone:0 | patch_nonempty:0 | passed=True:535 | patch_correct=1:0
[plain_llm_df] rows=609 det=1:279/571 (48.9%) detNone=38 | all-rows 279/609=45.8% | repair=1:0 repair=0:571 repNone:38 | patch_nonempty:0 | passed=True:15 | patch_correct=1:0

### 2. aitester(detection_first_status / iterations / patch / det)
  all_green_unverified   n=296 (48.6%) iters={0: 296} patch_nonempty=0 det1=0 det0=296
  red_not_repaired       n=167 (27.4%) iters={2: 132, 3: 35} patch_nonempty=158 det1=19 det0=148
  red_then_green         n= 93 (15.3%) iters={1: 76, 3: 2, 2: 15} patch_nonempty=93 det1=59 det0=34
  None                   n= 53 (8.7%) iters={0: 53} patch_nonempty=0 det1=0 det0=0
  all_green 不变式: iterations全0=True patch全None/空=True det全0=True passed全True=True red_seen全False=True regeneration_count={1: 296} test_regenerated_pass_unverified全True=True execution_trace非空=296/296 test_error_rate全0=True
  df all_green_unverified=15/609

### 3. red_seen / 转化率 / 反事实分解
  aitester red_seen=260/609=42.7%  df red_seen=556/609=91.3%
  转化率 aitester=78/260=30.0%  df=279/556=50.2%
  aitester-base 3 项分解: 产红率=+88.8 (44.2%) 转化率=+52.5 (26.1%) 交互=+59.7 (29.7%) 合计=201.0/201
  df-base 3 项分解      : 产红率=+148.5 (73.9%) 转化率=+112.2 (55.8%) 交互=-59.7 (-29.7%)
  单对齐新值: 产红率对齐 -> 166.8 行; 转化率对齐 -> 130.5 行

### 4. 门 verdict × detection_rate（3 臂）
  键存在行数=1044 / 总行数=1827 {('None', 0.0): 522, ('specific_red', 1.0): 206, ('None', None): 70, ('over_red', 0.0): 244, ('None', 1.0): 2}
  verdict=非 None 的行数: 450
  含非 None verdict 的批次: 4 ['007_161053', '007_170147', '007_181638', '007_185941']
  detection=1 但 red_seen≠True 的行: [('benchmark_synthetic_20261006_140906.json', 'plain_llm', 'synthetic__task_0002'), ('benchmark_synthetic_20261007_161053.json', 'plain_llm', 'synthetic__task_0002'), ('benchmark_synthetic_20261007_181638.json', 'plain_llm', 'synthetic__task_0002')]

### 5. SWE 普查（按工件顶层 dataset 字段）
  [swe_bench] rows=293 no_instance_code=293 no_detection_key=293 passed=True=4 files=11
  [swe_bench_pro] rows=72 no_instance_code=72 no_detection_key=72 passed=True=0 files=12
  合计 rows=365  artifacts=23

### 6. 伪重复：按 task_id 对齐 vs 按行序（positional）
  [seed42] seeds 42/42
     aitester     task_id对齐=78/87  行序对齐=45/87  同位置同task=49/87
     plain_llm    task_id对齐=87/87  行序对齐=49/87  同位置同task=49/87
     plain_llm_df task_id对齐=87/87  行序对齐=49/87  同位置同task=49/87
     合计: task_id 对齐 252/261 ; 行序对齐 143/261
  [seed44] seeds 44/44
     aitester     task_id对齐=75/87  行序对齐=42/87  同位置同task=49/87
     plain_llm    task_id对齐=87/87  行序对齐=49/87  同位置同task=49/87
     plain_llm_df task_id对齐=87/87  行序对齐=49/87  同位置同task=49/87
     合计: task_id 对齐 249/261 ; 行序对齐 140/261

### 7. QuixBugs
  [aitester] rows=50 det=1:17/37 repair=1:37/40 iters={2: 26, 1: 10, 3: 14} patch_nonempty=50 plausible0&correct1=13 stop={'skip_debugger_repair_invalid': 24, 'test_passed': 13, 'max_iterations': 13}
  [plain_llm_df] rows=50 det=1:31/37 repair=1:0/41 iters={0: 50} patch_nonempty=0 plausible0&correct1=0 stop={'unknown': 50}

### 8. oracle_type 全库普查
  全库按值: {'generated_test': 3968, 'absent': 3185}
  全库 aitester: {('aitester', 'generated_test'): 2015, ('aitester', 'absent'): 1788}
  benchmark_*.json 子集 aitester: {('aitester', 'generated_test'): 1803, ('aitester', 'absent'): 1672}
  非 generated_test 且键存在的行: 0

### 9. 其他不变量
  全库行数=7153 repair_history 键=0 patch_correct=1&plausible=0=129
  7 批中 spec_oracle_injected 键存在行数=0/1827
  7 批中 spec_oracle_verdict 键存在行数=0/1827

### 10. 报告文件指纹
  sha256(FINAL_REVIEW_2026-10-11.md) = f19b196c11cf9f2ffb5b86eec2b40a2d40063062b1c96a3438a38bf3f42aaaa1 size= 139491
```

---

## 附录 B：本文件此前内容的保留（Lead 于 10:44:47 写入的自查稿，原文照录）

> **保留原因**：本次验证开始时该路径已存在一份 Lead 自查稿（68 行），其声明"报告中被抽查的核心数字 15/15 逐条复算一致"。本 T-E 记录在 §1/§3 中对其中 **#10、#12、#15** 三条给出了不同结论（见 S1/S2/S3）。为不丢失前稿信息，原文照录如下（**其结论以本记录 §3 的修正为准**）。

```markdown
# T-E 对抗式验证记录（对 FINAL_REVIEW_2026-10-11.md 的独立复核）

- 验证执行者：Lead（final 阶段自查；原委派的独立验证 subagent 未产出文件，故由 Lead 完成并如实标注来源）
- 验证时间：2026-10-11（Asia/Shanghai）
- 验证方式：**零 LLM**、只读解析 `experiments/results/**` + `curl` 机读元数据端点
- 纪律：本节只记录**实际执行的命令与观察到的输出**；发现报告有错时如实记录并已就地更正

---

## 1. 逐条复算（报告 §3.3 / §3.4 / §3.5 / §3.7 / §3.8）

| # | 报告值 | 本次复算值 | 判定 | 复算方式 |
|---|---|---|---|---|
| 1 | aitester detection **78/556 = 14.0%** | **78 / 556 = 14.029%** | ✅ 一致 | 解析 7 批 `benchmark_synthetic_2026100[67]_*.json`，`detection_rate==1.0` 计数 ÷ `detection_rate is not None` 计数 |
| 2 | df detection **279/571 = 48.9%** | **279 / 571 = 48.862%** | ✅ 一致 | 同上 |
| 3 | plain_llm detection **10/609 = 1.6%** | **10 / 609 = 1.642%** | ✅ 一致 | 同上 |
| 4 | 三臂 `repair_rate==1.0` 全为 0 | **aitester 0 / plain_llm 0 / df 0** | ✅ 一致 | 同上 |
| 5 | 可测行 556 / 609 / 571 | **556 / 609 / 571** | ✅ 一致 | 同上 |
| 6 | `all_green_unverified` = **296**，全部 `iterations==0` 且 patch 为空 | **296（it0=296 / nopatch=296）** | ✅ 一致 | `detection_first_status` 分组 + `iterations` + `patch.strip()` |
| 7 | `red_not_repaired` 167 / `red_then_green` 93（det=1 为 59）/ `None` 53 | **167 / 93（59） / 53** | ✅ 一致 | 同上 |
| 8 | red_seen：aitester **260/609 = 42.7%**、df **556/609 = 91.3%** | **260（42.7%） / 556（91.3%）** | ✅ 一致 | `detection_first_red_seen is True` |
| 9 | 条件转化率 78/260=**30.0%** vs 279/556=**50.2%** | **30.0% / 50.2%** | ✅ 一致 | 同上 |
| 10 | 门 × 检出交叉表：`specific_red→1.0` **206**、`over_red→0.0` **244**、例外 **2** | `{('specific_red',1.0):206, ('over_red',0.0):244, (None,0.0):522, (None,None):70, (None,1.0):2}` | ✅ 一致 | 仅对**键存在**的行统计（区分 `k in r` 与 `r.get(k)`） |
| 11 | 真实仓库基准 **365 行**（swe_bench 293 + pro 72），100% 无 `instance_code`、100% 无 `detection_rate` | **293 + 72 = 365；instance_code 空 365/365；无 detection 键 365/365** | ✅ 一致 | 遍历全部 `experiments/results/**/*.json`，按 `dataset` 过滤 |
| 12 | 伪重复：seed42 对 **143/261**、seed44 对 **140/261** 行核心字段逐值相同 | **143 / 261、140 / 261** | ✅ 一致 | 比较字段 `detection_rate/repair_rate/passed/generated_test/detection_first_status/specificity_gate_verdict/stop_reason/patch` |
| 13 | QuixBugs：detection **17/37**、repair **37/40**、df detection **31/37**、df `iterations` 全 0 且 patch 全空 | **17/37、37/40、31/37、iterations 全 0、patch 非空 0/50** | ✅ 一致 | 解析 `e4_quixbugs_FIXED_harness/{aitester,plain_llm_df}.json` |
| 14 | QuixBugs 13 行 `plausible=0 ∧ correct=1` | **13 行**（`stop_reason=skip_debugger_repair_invalid`、`iterations=2`） | ✅ 一致 | 分组计数 |
| 15 | 全库 `oracle_type` 无任何 enhanced/spec oracle | **`generated_test` 1,803（aitester）/ `None` 1,672；无 `enhanced_generated_test`** | ✅ 一致 | 全库扫描 |

## 2. 发现并已更正的报告错误

| # | 位置 | 初稿表述 | 实际问题 | 更正后 |
|---|---|---|---|---|
| **E-1** | §0.2 K1 与 §3.4.2 | "反事实分解：对齐产红率可补 **88%** 缺口，对齐转化率仅补 12%" | **算错**：把"主效应占比"误算为"缺口占比"。实测缺口 = 201 行；产红率主效应 = (0.913−0.427)×0.300×609 = **+88.8（44.2%）**；转化率主效应 = 0.427×(0.502−0.300)×609 = **+52.5（26.1%）**；交互 = **59.7（29.7%）** | 已改为 44.2% / 26.1% / 29.7%，并加"口径更正"注记 |
| **E-2** | §3.4.2 结论 | 隐含"转化率不重要" | 由 E-1 连带修正：**产红率是最大单一因子，但转化率 + 交互合计 55.8%**，两类问题都必须修 | 已改为"两因子均必要"，并回写 §6 路径优先级说明 |

## 3. 引用抽查（直接访问机读端点）

| 引用 | 端点 | HTTP | 观察到的标题/容器 | 与报告一致？ |
|---|---|---|---|---|
| 10.1145/3803418（CANDOR） | `api.crossref.org` | **200** | *Hallucination to Consensus: Multi-Agent LLMs for End-to-End…* / **ACM Transactions on Software Engineering and Methodology** | ✅ |
| 10.1145/3803437.3806428（TestAgent） | 同上 | **200** | *TestAgent: A Multi-Agent LLM Framework for Repository-Level…* / *Proceedings of the 34th ACM…*（FSE Companion '26） | ✅ |
| 10.1109/icst69053.2026.00040（Konstantinou/ICST） | 同上 | **200** | *How well LLM-based test generation techniques perform with newer…* / **2026 IEEE International Conference on…** | ✅ |
| 10.1145/3832122（AdverTest） | 同上 | **200** | *Test vs Mutant: Adversarial LLM Agents for Robust Unit Tes…* / *Proceedings of the ACM on So…* | ✅ |
| 10.1145/3832093（Zhao/Zhou/Cohen） | 同上 | **200** | *Do Coverage and Mutation Scores of LLM-Generated Test Suit…* / *Proceedings of the ACM on So…* | ✅ |
| arXiv:2609.09315 | `export.arxiv.org/api` | **200** | *How effective are traditional test criteria at detecting b…*（entries=1） | ✅ |
| arXiv:2609.17394 | `arxiv.org/abs`（评审早期直接抓取） | **200** | *Coding Agents Have Converged…* | ✅ |
| arXiv:2602.08146 | `arxiv.org/html`（评审早期直接抓取） | **200** | *Test vs Mutant: Adversarial LLM Agents…* | ✅ |
| arXiv:2601.09695 | `arxiv.org/abs`（评审早期直接抓取） | **200** | *How well LLM-based test generation techniques perform with newer LLM versions?* | ✅ |

> **注**：`10.1109/icst69053.2026.00040` 的 Crossref 容器标题为 IEEE 会议论文集；项目文档未标该 DOI，本报告 §16 [4] 已补。

## 4. 未能验证 / 保留不确定

| 项 | 原因 |
|---|---|
| 覆盖率 89% / 83% 与逐模块覆盖 | 仓库根 `.coverage` 仅含 1 个被测文件，需全量 `--cov=src` 重跑（本次未跑） |
| `slim_environment: 1863` | 需卸载可选依赖的独立环境 |
| v1 口径 35.86% / 48.11% | 已被 v2 取代的历史值，未独立重放 |
| "无缓存理论成本" | 需关闭缓存重跑（成本高） |
| 项目 `patch_plausible` 的历史真实值 | `repair_history` 全库 0 次落盘，**不可复核**（这本身是报告结论之一） |
| `instance_code` 物化失败的上游原因 | 需 SWE-bench 数据集 + HF 访问（本环境缺） |

## 5. 验证结论

**报告中被抽查的核心数字 15/15 逐条复算一致；引用抽查 9/9 端点可用且标题与报告一致；发现并已更正的实质错误 1 处（E-1 反事实分解口径），连带修正 1 处（E-2）。**

**残余风险**：本验证由 Lead 自查完成（原独立验证 subagent 未产出），因此**不构成完全的第三方独立复核**；建议在正式投稿前，由未参与本项目的人员按本文件 §1 的命令做一次外部复算。
```

---

### 附录 B 备注（本记录对前稿三条"✅"的修正）

| 前稿行 | 前稿判定 | 本记录结论 | 依据 |
|---|---|---|---|
| #10 | ✅ 一致（把"2 行"当作门的例外） | ⚠️ 数值一致、**定性错误**：那 2 行是"门未运行"的行，且 `detection_rate=1.0` 与同行 `passed=True/red_seen=False/iterations=0` 自相矛盾；"全量"只覆盖 450 行/4 批 | A.4 |
| #12 | ✅ 一致（143/261、140/261） | ❌ **比较对齐方式无效**：按 `task_id` 对齐为 **252/261、249/261** | A.6 |
| #15 | ✅ 一致（1,803/1,672 记作"全库"） | ❌ **口径标注错误**：1,803/1,672 是 `benchmark_*.json` 子集；全库 aitester 为 2,015/1,788，全臂 3,968/3,185；且 1,672 是"键缺失"而非"值为 None" | A.8 |

> 以上三条**不改变**前稿的核心结论（三臂数字一致、引用真实、E-1 已更正），但"15/15 逐条一致"的表述应修正为"**12/15 逐条一致，3 条口径/对齐方式需修正**"。
