# BM 轮：实验/报告读侧把"检测没发生 / 检测崩了"折成最有利判定——崩溃记进"干净组"、未测记进"零回归"（2026-10-22，零 LLM，$0）

> 系列位置：BH→BI→BJ→BK→BL→**BM**（"读不懂 ⇒ 静默"缺陷族的第 5 面）。
> BL 把"发布侧带 status、判定侧仍按空值判定"收口在 `src/`，登记边界写明
> `experiments/` 未做——本轮就是那块。一句话：**实验与报告这两张读侧的桌上，
> "这条腿没测成"仍然被写成"测过了，而且没问题"**，而且写法比 `src/` 更直接：
> 崩溃分支返回的是取值域里**最有利**的那一档。

## 1. 缺陷：三个读侧站点，都把"没测"折成"最好看的读数"

### 1.1 污染检测的崩溃腿返回 `low`（= 干净组）

`experiments/run_benchmark.py` 的 `_compute_contamination_risk_level` 在
`try` 外先做材料守卫（无 golden_patches / 任务无对应条目 / 补丁任一侧为空
→ `not_applicable`，N7 口径），`try` 内才做真检测。收尾是：

```python
    except Exception:
        logger.debug("污染风险等级计算失败（保守标记 low）: task=%s", task_id, exc_info=True)
        return "low"        # 改前
```

而 `low` 在下游**就是"干净组"**：`experiments/statistical_analysis.py`
的 `contamination_view_summary` 把 `high/medium` 记入含污染分母、把
`low` 记入 `clean_n`/`clean_passed_rate`；`experiments/analysis_parts/cross_analysis.py`
的 `high_vs_low_success_delta` 也用 `low` 桶做对照基线。也就是说：
**"这条腿崩了"被登记成"检测过且无重叠证据"**。

这不是新发现，而是**修漏**：同仓的内层 `_combined_risk_level`
（`experiments/contamination_check.py:299`）在 O22（2026-09-29 审查 P1）
就为这件事新增过 `unknown` 档，docstring 逐字写着

> 此前缺 patch / 缺 gold / **异常时一律 fail-open 归 "low"**，导致 852 行
> 100% "low"（其中 580 行补丁为空串）的"零判别力"结果。

内层修了，**包装器没跟着修**；两个消费侧也都早已把 `unknown` 诚实排除在
两组分母之外（`ADR-0023` 写明"not_applicable/unknown 不入分母"）。

### 1.2 `contract_status` 在实验侧写了没人读

BL 把双读口径接进 `src/` 后，链路是这样的：

| 位置 | 状态 |
|---|---|
| `src/graph/state.py:371` | 声明 `contract_status: str \| None` |
| `src/graph/nodes.py:2867` | 发布 per-leg 值（`status_for_check(...)`） |
| `experiments/run_benchmark.py:1872` | 结果行写 `"contract_status": final_state.get(...)` |
| `src/graph/debugger.py:918` | BL 接的 `src/` 侧读者 |
| `experiments/run_benchmark.py:_build_risk_summary_for_result` | **不读**——`build_risk_summary(...)` 实参里没有它 |

后果：BL 新增的 `contract_unmeasurable(...)` 披露在**实验产出的
`risk_summary` 里永远不出现**，`risk_summary["contract_status"]` 恒 `None`
（BL 起 `build_risk_summary` 两个分支都逐字写该键，入参才是决定值）。

### 1.3 R4/N1 用全行分母，未测行按"没问题"计分

`experiments/run_main_batch.py` 的 `_print_r4_summary`（改前）：

```python
        regr_rate = round(sum(1 for r in det if r.get("regression_rate") == 1.0) / n * 100, 1) if n else None
        te_rate = round(sum(1 for r in det if r.get("test_error_rate") == 1.0) / n * 100, 1) if n else None
        print(f"    R4 regression_rate={regr_rate}% / N1 test_error_rate={te_rate}%")
```

`n = len(det)` 是**全部行**，包括 `regression_rate` 为 `None`（不可测）或
连键都没有的行。分子只数 `== 1.0`，所以未测行等价于**按"没回归 / 没测试错误"计分**，
而 `0.0%` 恰好好读成"零回归"。同一个打印块里的 M1 三指标早已用
`m1_denom`（可测行数）并打印"可测 {m1_denom}/{n} 任务"——**同块两种口径**。

### 1.4 5.3 对照表把三档整行吞掉

`experiments/analyze_results.py` 渲染 high-vs-low 对照时只取
`by_risk_level["high"]` 与 `["low"]`，`medium/unknown/not_applicable`
既不进对照、也不在表里留下任何计数——读者不知道对照建立在几行之上。

## 2. 处置：不入最有利组，不改判定方向

四处全部落在"披露 / 归位"这一侧，**没有任何一处把"没测成"翻成"判负"**：

| # | 站点 | 改法 | 判定方向 |
|---|---|---|---|
| ① | `run_benchmark._compute_contamination_risk_level` | 崩溃腿 `return "low"` → `return "unknown"`（沿用 O22 已引入、两个消费侧已排除的档位）；docstring 三处取值域同步 | 不入干净组，也不入污染组 |
| ② | `run_benchmark._build_risk_summary_for_result` | 成功分支补 `contract_status=final_state.get("contract_status")`；失败分支保持 `None` | 只多一条披露，分数/级别/因子逐位不变 |
| ③ | `run_main_batch._print_r4_summary` | R4/N1 分母改为可测行数 `regr_k`/`te_k`，并打印"可测 k/n"；`k=0` 时打印"不可测（无可测行）"而非 `0.0%` | 分子不变，只换分母并披露 |
| ④ | `analyze_results.render_markdown` 5.3 | 表加"未入对照任务"列（medium/unknown/not_applicable 合计）+ 一条口径注 | 纯披露 |

①的"不改判"具体指：`unknown` **不**触发任何拒绝、**不**改变 `passed`，
只让它离开 clean 组；②不改 `risk_score`；③分子仍是 `== 1.0` 的行数。

## 3. 测量（全部实测；Python 3.14.6，零 LLM）

### 3.1 崩溃腿可达性栅格（15 条输入，进程内复算 try 体以捕获真实异常）

| 输入形状 | 改前包装器 | 内联复算 | 腿 |
|---|---|---|---|
| str 与黄金逐字相同 | `high` | no-raise | 正常 |
| str 单落单 surrogate `\ud800` | `medium` | no-raise | 正常 |
| str NUL 字节 | `medium` | no-raise | 正常 |
| str fenced 代码块 | `low` | no-raise | 正常 |
| str 真 git diff（含 `@@`/`index` 头） | `low` | no-raise | 正常 |
| str 深嵌套括号 200000×2 | `low` | no-raise | 正常 |
| str 超长单 token 200000 | `low` | no-raise | 正常 |
| str 巨量修改行 20000 | `low` | no-raise | 正常 |
| str 全非修改行（只有上下文） | `low` | no-raise | 正常 |
| str 前导零数字 `0755` | `low` | no-raise | 正常 |
| **bytes** `b"+def f(x):..."` | `low` | `TypeError: a bytes-like object is required, not 'str'` @ `contamination_check.py:73` | **崩溃** |
| **list** `["+def f(): pass"]` | `low` | `AttributeError: 'list' object has no attribute 'splitlines'` @ `:72` | **崩溃** |
| **dict** `{"patch": "+x"}` | `low` | 同型 `AttributeError` | **崩溃** |
| **int** `123` | `low` | 同型 `AttributeError` | **崩溃** |
| 黄金侧非 str（反向） | `low` | `AttributeError` | **崩溃** |
| 导入腿（`sys.modules` 投毒，人工构造） | `low` | — | **崩溃** |

改前分布：`{'high': 1, 'medium': 2, 'low': 12, 'unknown': 0}`；
**崩溃腿 5/15 命中，5/5 折成 `low`**（含导入腿共 6/16）。
改后同一栅格：`{'high': 1, 'medium': 2, 'low': 7, 'unknown': 5}`，
"判优(low) 且来自崩溃腿 = **[]**"。

**语义腿口径必须写明（复测时才发现的第二个口径分叉）**：上面两行分布测于
`EMBEDDING_BACKEND=none`（词袋余弦代理）。默认嵌入口径下同一栅格为
`{'high': 1, 'low': 9, 'unknown': 5}`——两行 `medium` 改落 `low`。但**崩溃腿 5/15 命中**与
**「判优(low) 且来自崩溃腿 = []」**这两个判读在两种口径下逐条不变 ⇒ 本轮结论（崩溃不判优）
不依赖语义腿，但**登记档位分布时必须同时登记 `EMBEDDING_BACKEND` 取值**。

**str 侧为何不可达（构造性判据，不只是"跑了没红"）**：`_TOKEN_RE`
（`contamination_check.py:56`）只保留标识符与数字，标点全被丢弃，故
`_extract_statement_skeleton` 拼出的伪代码是非引号 token 序列，`ast.parse`
至多抛 `SyntaxError`（被内层 `(SyntaxError, ValueError)` 捕获），
`tokenize` 退路也自带 `(TokenError, IndentationError, SyntaxError)` 守卫；
`_embed_code` 吞掉全部异常；`_lcs_ratio`/`_token_bag_cosine` 只吃已归一的
token 列表。所以字符串输入不会穿透到包装器的 `except`。

### 3.2 归档零影响（两个口径要分开）

- **行级普查口径**（`experiments/results/**/*.json` 共 1700 个文件，递归展开
  所有 dict 计数 `contamination_risk_level`）：**8865 行**
  = `not_applicable` 7843 + `low` 1022；`unknown`/`high`/`medium` **各 0**。
  patch 字段形状：low 中 685 行 `patch` 为 **`null`**（2026-10-22 收口勘误：初稿记作
  「无 `patch` 键」，复测 8865 行里**缺键 0 行**——是键在、值为 `null`，BL §56 ④ 刚立的
  「`None` ≠ 缺席」在同一轮自己的探针里第二次被踩）+ 337 行 str（其中 42 行空串）；
  not_applicable 中 5563 `null`（同样不是缺键）+ 2280 str。**非 str 补丁 0 行** ⇒
  崩溃腿在归档里 **0 实例**，①的取值变更不触及任何已发布数字。
- **批次摘要口径**（只算 `results.<bl>.details` 列表）：259 个文件含
  `"details"` 原始字节，展开成 **335 个 (批次, 基线)** 组合、**11197 行**。
- 108 个 `JSONDecodeError` 文件全是
  `_superseded_20261010/.../quixbugs_filtered/json_testcases/*.json`
  （测试用例数据，不是结果行），原始字节扫描 **0 个含该键** ⇒ 分母完整。

### 3.3 R4/N1 分母缺口（11197 行，改前口径 vs 可测口径）

| 指标 | 缺键 | `None` | 可测 k | 其中 1.0 | 现口径(/n) | 可测口径(/k) |
|---|---|---|---|---|---|---|
| `regression_rate` | 3185 | 8012 | **0** | 0 | **0.0%** | 不可测 |
| `test_error_rate` | 3185 | 806 | 7206 | 814 | 7.3% | **11.3%** |

按基线（`te` 现口径 → 可测口径，括号内 k/n）：

| 基线 | n | regr k | te 现口径 | te 可测口径 | k/n |
|---|---|---|---|---|---|
| `aitester` | 5819 | 0 | 6.6% | 10.9% | 3513 |
| `plain_llm` | 2081 | 0 | 6.5% | 10.4% | 1304 |
| `plain_llm_df` | 2300 | 0 | 10.7% | 11.6% | 2129 |
| `plain_llm_df_doc` | 50 | 0 | 0.0% | 0.0% | 35 |
| `plain_llm_df_doc_augment` | 50 | 0 | 0.0% | 0.0% | 35 |
| `plain_llm_df_doc_union` | 50 | 0 | 2.0% | 2.9% | 34 |
| `plain_llm_df_spec` | 150 | 0 | 0.0% | 0.0% | 106 |
| `single_agent` | 697 | 0 | **6.7%** | **94.0%** | 50 |

`single_agent` 是最刺眼的一行：50 行可测里 47 行 `test_error_rate=1.0`，
现口径因为把 647 行未测算进分母而只报 6.7%。

### 3.4 `regression_rate` 为何恒 0.0%（对角线证据）

11197 行全部带 `task_metadata`。按 P2P 材料与键写入情况交叉：

| `pass_to_pass` | 行数 | 其中 `regression_rate` |
|---|---|---|
| 缺键 | 10965 | 8012 行写 `None` + 2953 行不写键 |
| 空列表 | 48 | **48 行全部不写键** |
| **非空** | 184 | **184 行全部不写键** |

有 P2P 材料（唯一可测前提，`_m1_metrics.py:990` 的 `p2p_tests` 守卫）的行
恰好都落在"键都没写"的那批，写了键的行恰好都没有材料 ⇒ **交集为空**
⇒ 归档中不存在"可测且有值"的 `regression_rate` ⇒ `R4 regression_rate=0.0%`
是结构性的，不是"测出来零回归"。

## 4. 回归锁（`tests/test_bm_experiments_readside.py`，32 例）

| 组 | 例数 | 锁什么 |
|---|---|---|
| `TestCrashLegIsNotTheFavorableGrade` | 17 | 5 条非 str 参数 + 黄金侧非 str + 导入腿 ⇒ `unknown`；8 条 str 形状**不得**落 `unknown`（防空腿被改成"崩了就逃"）；无重叠 str 仍是 `low`；材料缺失仍是 `not_applicable` |
| `TestUnknownLandsInAnHonestBucket` | 3 | `contamination_view_summary` 把 `unknown` 排除在两组分母外；`_contamination_cross_analysis` 分桶且不进 delta；5.3 表出现"未入对照任务"列且值为 3 |
| `TestContractStatusReachesExperimentSide` | 4 | 关态透传；开态出披露且分数/级别/因子与 `status=ok` 逐位相同；有缺失符号时 `contract_missing` 仍主导、不叠加披露；失败分支保持 `None` |
| `TestMeasurableDenominators` | 4 | 未测行不得计成 `0.0%`（打印"不可测（无可测行）（可测 0/3）"）；可测口径 `1.0/2 = 50.0%（可测 2/4）`；缺键与 `None` 同判；与 M1 行共用"可测 k/n"字样 |
| `TestWiringLocks` | 4 | 源码/`inspect.getsource` 接线存在性锁（措辞、透传实参、列与排除式、消费侧档位集合） |

邻近面回归（改后复跑，全部 `--no-cov`、单进程、`-q`）：
11 个文件 **268 passed / 1.82s**；另 14 个文件 **456 passed + 6 skipped / 10.41s**；
新锁文件本身 **32 passed / 1.73s**。既有断言无一处需要改写
（`test_2026_10_05_n_batch.py` 的 N7 栅格只锁 `not_applicable`/`high`，
`test_contamination_multidim.py` 只锁内层函数，均不与崩溃腿冲突）。

## 5. 变异验证（`scripts/tools/bm_mutation_verify.py`，9 锚点 + 1 中性对照）

基线：`collected=32`，rc=0。每个锚点：原串 count==1 → 写入变异 → `compile()`
→ collected 复核 → 跑受影响面 → `finally` 按原字节写回并校验 sha256。
**受影响面不是恒 32**：M1 与 M2 各把邻近文件拉进采集面，实测 collected
**83** / **91**，M3–M10 恒 **32**——红数必须和"该锚点实际采到多少条"一起登记，
否则"3 红 / 8 红"无从判读。复跑三次（墙钟 75s / 75s / 76s）红数逐次相同：
**8/3/1/2/2/1/2/1/1**，M10 中性对照 0 红，四份被改写文件 sha256 全部原字节还原。

| 锚点 | collected | 变异 | 结果 | 被谁打死 |
|---|---|---|---|---|
| M1 崩溃腿 | 83 | `return "unknown"` → `return "low"` | FAILED（**8** 红） | 5 条非 str + 黄金侧非 str + 诚实桶 + 接线锁 |
| M2 透传 | 91 | `contract_status=final_state.get(...)` → `=None` | FAILED（**3** 红） | 开/关两态透传锁 |
| M3 分母 | 32 | `/ regr_k` → `/ n` | FAILED（1 红） | 可测 50.0% 断言 |
| M4 未测计 0 | 32 | `regr_meas` 过滤器 → 全行按 0.0 | FAILED（2 红） | 不可测标注 + 可测口径 |
| M5 同上 te | 32 | `te_meas` 过滤器 → 全行按 0.0 | FAILED（2 红） | 100.0%(可测 1/3) 断言 |
| M6 标注丢失 | 32 | `regr_text` 去掉"不可测"分支 | FAILED（1 红） | 不可测串断言 |
| M7 排除计数 | 32 | `if lv not in ("high","low")` → `if False` | FAILED（2 红） | 列值 3 + 接线锁 |
| M8 表头列 | 32 | 删"未入对照任务"列 | FAILED（1 红） | 表头断言 |
| M9 注漏 unknown | 32 | 注里改成"两档合计" | FAILED（1 红） | 注断言 |
| **M10 中性对照** | 32 | 仅改 docstring 措辞 | **SURVIVED（rc=0）** | 必须不红——证明红来自判据而非噪声 |

残留扫描：`# mutation:` 在 `experiments/` 与 `src/` 均 **0**
（`experiments/run_benchmark.py:2782` 的 `# mutation_feedback 由…` 是散文，
不是标记；`scripts/tools/bm_mutation_verify.py` 里的命中是脚本自带的数据串）。

## 6. 踩坑与自纠（本轮实测发生的）

1. **`nonstr_low += 1` UnboundLocalError**——归档扫描探针里嵌套函数自增计数器，
   与 BK/BL 轮同型错误**第二次**发生。改为 `collections.Counter` 状态字典。
2. **`[{...}] * 3` 是同一个对象**——测试里想造 3 行再分别打补丁，实际互相污染。
   改为逐行独立 dict（否则 `test_unmeasurable_*` 会假通过）。
3. **glob 口径选错**——第一版只匹配 `*batch*.json`，命中 2 个文件、批次 0 个，
   差点登记成"归档里没有批次文件"。改为按 `"details"` 原始字节过滤再解析。
4. **断言里的输出串多写了一个 `%`**——实际输出是
   `不可测（无可测行）（可测 0/3）`（`%` 只在数值分支里）。复跑核对真实
   stdout 后改正，没有凭想象把断言掰回去。
5. **`d.get` 对 list 顶层文件崩**——归档里有 2 个 JSON 顶层是 list，加
   `isinstance(d, dict)` 守卫后计数才稳定。
6. 可达性结论必须同时登记**构造性判据**（`_TOKEN_RE` 丢标点）与**证据**
   （10 条 str 栅格 0 命中）；只写后者会把"没测到"当成"测不到"。
7. **复算入口落在会话临时目录 = 登记的是转引**：本节 §8 初稿指向 `/tmp/bm/probe*.py`，
   收口时把三个只读探针入库 `scripts/tools/bm_crash_leg_reachability.py` /
   `bm_archive_level_patch_census.py` / `bm_readside_denominator_census.py`，复算命令改指仓内路径。
   入库时顺手去掉探针自带的绝对路径 `sys.path.insert`（改按 `__file__` 上溯仓库根），
   并把"同一读数两处测量"合并（归档普查只由 `bm_archive_level_patch_census.py` 独占）。
8. **入库复跑当场发现两个口径分叉**：① 栅格分布从登记的 `{high:1, medium:2, low:7, unknown:5}`
   变成 `{high:1, low:9, unknown:5}`——不是代码变了，是原测跑在 `EMBEDDING_BACKEND=none` 下，
   脚本改为两种口径各跑一遍（见 §3.1）；② 归档 `patch` 字段的「无键」实为 `patch: null`
   （见 §3.2 勘误）。两条都是**只有把量具入库才暴露**的，转引 /tmp 脚本就留在原地了。
9. **README `**最新优化**` 行自 BC 起没轮换，本轮一次折进 9 轮叙事，把 BL/BH/BE 三句"当时计数"
   搬进了 `check_baseline_numbers.py` 的射程（`## 测试状态` → 下一个 `##`）——门禁报 4 处硬编码残留。
   行内改为 `11704 例通过 / 5 例跳过 / 零失败`（EN `11704 cases green / 5 skipped / no failures`），
   当前口径仍只指 BASELINE.yaml，头部引言不动。同一处还暴露出拼接锚点 `hits=2`（头部与表行含同一句
   BL 叙事），`expect=1` 断言把它变成信号而不是改错位置。见廉洁分册 §57 ⑧。
10. **`ruff format --check .` 的 977 是"探针入库前"的读数**——三个 `scripts/tools/bm_*.py` 注册进 §8 之后
    复算是 **980**（BL 974 + BM 6 个可格式化文件：1 锁 + 1 变异脚本 + 3 探针 + 本手册 `.md`）。
    登记句里的计数与"按名核对"的清单必须一起改，只改数字会留下一个自证的空位。
11. **路径列表里多写一个不存在的测试文件名 = 整跑 0 收集**——`pytest … tests/test_bilingual_docs.py`（仓内没有这个
    文件）直接以 `1 warning in 0.04s` 收场，一条用例都没执行，而 `tail -3` 只看得到那行摘要。**空摘要不是"跑得快"，
    是没跑**：先看 collected，再看 rc。（该双语门禁本体是 `scripts/gates/check_bilingual_docs.py`，无同名测试文件。）

## 7. 边界与未收口部分（按名登记，不写成"已排除"）

1. `cross_analysis._contamination_cross_analysis:42` 的 `if not level: continue`
   让**字段缺失**的行连 `observed` 都不计，而 `statistical_analysis` 把缺失折成
   `unknown`。两者口径不一致是**已知未收口**：统一它会改变
   `available=False` 的语义（全无该字段的批次将开始渲染一张空表），属判据方向
   变更，本轮只在 docstring 里把差异写明。
2. 崩溃腿的**真实生产实例仍为 0**（归档非 str 补丁 0 行）。本轮登记为
   "人工栅格 5 条 + 导入投毒 1 条 + 归档 0 实例"，与 BK 轮同一诚实口径：
   锁的是"以后崩了不判优"，不是"曾经崩过"。
3. `94.0%`（`single_agent` 可测口径）是**换分母读出来的新数**，不是"回归变严重了"；
   任何把它与历史 `6.7%` 相减的说法都是口径错配。
4. 本轮未动 `_combined_risk_level` 的 `unknown` 触发条件（`values` 为空），
   包装器路径下该档只能由崩溃腿与"值为空"产生，归档 0 实例。
5. `experiments/` 与 `scripts/` 仍在 mutation/ratchet 覆盖之外（BK 登记），
   本轮的 4 处收口靠 `tests/test_bm_experiments_readside.py` 的 32 例守。
6. `risk_summary["contract_status"]` 在归档 8865 行里 **0 次出现**（BL 才把键
   写进 `build_risk_summary`）⇒ ②对历史 JSON 零影响，只影响此后新跑的批次。

## 8. 复算命令（零 LLM、零写入、可逐条重跑）

```bash
# 1) 本轮 32 例新锁（先看 collected=32，再看 rc）
.venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_bm_experiments_readside.py

# 2) 邻近面（生产/消费两侧既有锁）
.venv/bin/python -m pytest -q --no-cov -p no:cacheprovider \
  tests/test_2026_10_05_n_batch.py tests/test_run_benchmark.py \
  tests/test_roadmap_13_22_21_mypy_5.py tests/test_experiments_analysis.py \
  tests/test_batch_ix.py tests/test_contamination_multidim.py \
  tests/test_contamination_check.py tests/test_embedding_utils.py \
  tests/test_run_main_batch_task_scope.py tests/test_risk_approval_matrix.py \
  tests/test_decontamination.py

# 3) 可达性栅格（15 条输入 + 导入投毒；会临时改 sys.modules，不落盘）
.venv/bin/python scripts/tools/bm_crash_leg_reachability.py
#    脚本自带两种语义腿口径（EMBEDDING_BACKEND=none 与默认嵌入）各跑一遍栅格并分别打印分布

# 4) 归档两口径（行级 8865 / 批次 11197；只读）
.venv/bin/python scripts/tools/bm_archive_level_patch_census.py &&
.venv/bin/python scripts/tools/bm_readside_denominator_census.py

# 5) 变异验证：9 锚点 + 1 中性对照（会临时改写 experiments/，finally 按 sha256 还原）
.venv/bin/python scripts/tools/bm_mutation_verify.py
#    中止过就必须扫残留，并复跑 §1 的 32 例：
grep -rn '# mutation:' experiments/ src/

# 6) 文档锁子集（回填前后各跑一次；本轮首跑后回填、终跑后再回填，两次都复跑过）
.venv/bin/python -m pytest -q --no-cov -p no:cacheprovider \
  tests/test_markdown_table_integrity.py tests/test_check_doc_links.py tests/test_ao_batch.py \
  tests/test_check_baseline_numbers.py tests/test_artifact_doc_consistency_gate.py \
  tests/test_bm_experiments_readside.py
.venv/bin/python scripts/gates/check_bilingual_docs.py --strict && .venv/bin/ruff format --check .

# 7) 门禁链（最后、单独跑，不要接管道）
make gates
```

**跑法提醒（本轮实测踩到）**：`pytest` 的路径列表里写一个不存在的文件，整跑直接 0 收集
（`1 warning in 0.04s`，无一条用例执行）——**空摘要不是"跑得快"，是没跑**；先看 collected 再看 rc。

## 9. 收口批注（2026-10-22）

**门禁链两跑 rc=0**（首跑在本节回填之前、终跑在回填之后，两次都单独执行，不与其他 pytest / 文档编辑重叠）：
墙钟 **211s / 213s**（`date +%s` 成对采集 1792638220→1792638431、1792638537→1792638750），
18 步命令 / 16 个 make 目标全绿。链内 pytest（`pytest tests/ -n 4 --dist loadfile`，**不带 `--cov`**）
两跑同判 `4 workers [11741 items]` → **11736 passed / 5 skipped / 0 failed**（用时 205.60s / 207.07s；
警告总数 **50 / 54**——差值落在 `test_spec_expr_property` 的 hypothesis `invalid decimal literal` 组 44→46
与摘要里逐条列出的 2 条同型条目，本轮未逐条归因 ⇒ 只登记两跑现值；确认跑口径为 37 条）——collected 面与本轮
确认跑（11741）相同。链尾分步读数两跑**逐字节相同**（原始 diff 仅 pytest 摘要 1 行）：`ruff check` All checks passed /
`ruff format --check .` **980** 文件已格式化 / `mypy` **Success: no issues found in 137 source files** /
双语同步 0 警告 0 失败 / 文档链接通过 / 严格 JSON **7274** 份工件（严格 7272 + 豁免 2 + 违规 0）/
零断言扫描 457 个测试文件 0 例 / `ast-guards` 136 文件 / 78 站点 / 未覆盖 20 / 违规 0 / 豁免命中 20 / EXEMPT 19
（BK 轮起逐位未动，本轮亦然）。覆盖率本轮未重跑 `--cov`（`src/` 零改动，行/弧读数 19393/19904 = 97.4327%、
7105/7532 = 94.3309% 为 BL 继承值）；`# mutation:` 残留扫描 0 处（变异脚本 finally 按 sha256 原字节还原，
9 锚点 + 1 中性对照见 §5）。回填分两段：**首跑与终跑之间**入的是首跑读数（本 §9、双语 CHANGELOG、`BASELINE.yaml` 门禁行），
**终跑之后**入的是两跑读数与本轮新踩的三条提醒（§6 第 9—11 条、§8 的文档锁子集命令、双语 README **头部引言**的门禁句、
登记册 §1「全量测试」行的两跑句；`**最新优化**` 表行本身在首跑之前已定稿）。两段全程未动 `src/` / `tests/` / `scripts/` / `experiments/` 任何一行 ⇒ 全量判读数不可能改变，链未第三次重跑：
本节主张"两跑跑过链、链内采集面与确认跑一致"，**不主张"最终树跑过链"**，只主张
"最终树与终跑的差异面 = 文档文本"。
