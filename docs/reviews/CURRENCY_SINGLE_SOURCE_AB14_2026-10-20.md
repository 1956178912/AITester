# AB-14：币种判定收口为单一谓词，五站点全部接过去（2026-10-20）

> 零 LLM、$0。本轮处置 AB-13 处置第 3 条自己留下的那句话——"仓内另有口径、本轮不统一"。
> 前置复测把那句话展开成一张表：**同一个"这笔钱是不是美元"的判断，仓内写了四遍且四遍互不相同，
> 第五遍干脆没写**。判据链：AB-9（静默缩分母才是缺陷）→ AB-10（缺席不得报成零命中）→
> AB-11（键缺席 ≠ 值为 null ≠ 读不动；同值不是证据）→ AB-12c（0 实例要连覆盖面一起锁）→
> AB-12d（披露计数也要划分）→ AB-13（字段名里的单位要参与判定）→
> **AB-14（判定只写一遍；缺席不得默认成任何单位；"看起来多余"的 term 也要有观测面）**。

## 1. 前置读数（`/tmp/ab14_probe.py`、`/tmp/ab14_probe2.py`、`/tmp/ab14_addcost_check.py`，只读 + 只写 tmp）

| 编号 | 测的事 | 改前实测 |
|---|---|---|
| R1 | `src/budget/pricing.py` 的币种取值 `entry.get("currency", "USD")` | 键缺席**默认成美元**并计价；同站点值为 `null` 时**不计价** ⇒ 两种缺席给出相反结论 |
| R2 | `statistical_analysis.cost_analysis` 的 `models[m].get("currency") or "USD"` | 键缺席 / `null` / `""` **三种事实一律印成 "USD"**——报告币种列里的单位是代码编的，不是登记的 |
| R3 | 同处 `currencies` 集合（大小写敏感） | `USD` 与 `usd` 并存 ⇒ 集合大小 2 ⇒ 整臂成本降为 `None`，而 `missing_models` 为空 ⇒ 报告落一行"未计价——（缺: ）"（无归因） |
| R4 | 同处币种为非字符串 | `123` 原样流进声明返回 `str` 的单元格；`["USD"]` 让 `set` 推导抛 `TypeError` ⇒ 实测 CLI **退出码 1、整份统计报告不产出** |
| R5 | `spec_examples_generator`（`or ""` + `.upper()`，不 strip）与 `emse_stats_report` 同族写法 | 缺席一律剔除（与 R1/R2 相反）；`" USD "` 被剔；条目不是对象时 `.get` 直接崩在计费路径上 |
| R6 | **第五处** `analyze_t1_b2_main_batch.add_cost` | 读 `input_per_mtok` / `output_per_mtok` 却**从不读 `currency`** ⇒ 非 USD（或没登记单位）被原样累加进名为 `cost_usd` 的字段；与 AB-13c 同型，但这里连"判错"都算不上，是**没判** |
| R7 | 形状：`cost_analysis` 要 `{"models": …}` 包装体 | 三条形状通道（顶层非对象 / 缺 `models` 键 / `models` 值非对象）一律**静默**塌成空表 ⇒ 把其实已登记的模型列进 `missing_models`，报告据"价目未登记"让人去补一份本来就补好了的价目表 |
| R8 | 真批次实际用到的模型（本轮"改而不重写"的前提） | e2 与 e2_iter 两份报告只用到 `deepseek-flash`（币种精确登记 `USD`）；归档 T1/B2 载荷 21 条 `cost_usd` 同样只用该模型 |

R8 是本轮能不动受 `SHA256SUMS` 保护工件的全部依据；`src/` 侧的行为变化（R1）只影响"没写币种的条目"，
而真表每个条目都写了。

## 2. 处置口径

1. **单一事实源**：`src/budget.pricing.currency_status(entry)` 一次判定，值域七族
   `absent` / `null` / `blank` / `usd` / `other:<NORM>` / `not_string:<T>` / `entry_not_object:<T>`；
   13 个输入落 **9 个互不相同的读数**（锁用显式集合相等断言，不是"数量等于 9"）。
   `usd` 的判定是 strip + 大写归一，故 `" usd "` 与 `USD` 同族。
2. **计价准入与可呈现标签分开**：`currency_label(status)` 只在 `usd` 与 `other:<NORM>` 时给出标签，
   其余为 `None`；`is_usd_entry(entry)` 供只有一列美元的站点使用。**缺席不得被渲染成任何单位名**，
   尤其不得渲染成 `USD`。
3. **五处全部接过去**：`pricing._usd_prices`、`statistical_analysis.cost_analysis`、
   `spec_examples_generator.estimate_cost_usd`、`emse_stats_report.cost_effectiveness_block`、
   `analyze_t1_b2_main_batch.add_cost`。第五处纳入的理由是"否则『判定只写一遍』本身就是过度承诺"。
4. **站点差异只允许出现在有没有地方写单位**：带币种列的 `cost_analysis` **可以**对 `other:CNY`
   计价，但标签必须是归一化后的 `CNY`，且表后追加单位提醒（仅当真存在非 USD 计价行）；
   单一美元列的 `total_usd` / `cost_usd` 对非 USD 一律剔除。判定同一份，处置分两种，这是设计而非漂移。
5. **只增不改**：`cost_analysis` 的行字典新增键 `unpriced_currency_models`（模型名 → 状态读数），
   **只在真发生不可判定时写入** ⇒ 币种可判定的行（含真批次）返回域逐键不变。
   `_price_models_layer` 只增加点名，**返回值口径一字不动**（坏形状仍是空表 ⇒ 诚实降级为未计价）；
   `{}` 与 `{"models": {}}` 保持静默——空对象没有形状可说。
6. **报告侧措辞**：未计价行的成因串在同一段里分别点名两种机制（`（缺: …）` 与
   `币种不可判定: m（状态）`）；早退分支（没有任何计价行时）新增机制清单，并明写
   "只补 `input_per_mtok` 不改变本结论"。

## 3. 与既有断言相撞时的裁决

`tests/test_experiments_absent_vs_zero_ab12.py` 的合成价目条目不写 `currency`，新口径下该组会从
"计价成功"退化为"根本没计价"。按 AB-13 先例**改输入而非放宽断言**：`_PRICE` 补 `"currency": "USD"`，
原算术断言一字未动。另有一处**登记不修**：`tests/test_ae_batch.py:125` 在测试侧写
`entry.get("currency", "USD")` 兜底——那是测试自己造的第二套口径，本轮把它登记在 §5 而不是顺手改，
因为改它要连带核对该文件全部成本例的期望值。

## 4. 验证

- 新增 `tests/test_experiments_currency_caliber_ab14.py` **124 例**：谓词值域（13 参数化 + 集合相等 +
  缺席不印成任何单位）+ 四站点与第五处一致性（同输入同读数）+ 币种不可判定不得编出 USD +
  机制分桶 + 形状点名三通道 + 渲染（单位提醒 / 早退清单 / 成因串）+ 真批次读数不变 + 接线锁
  （禁 `or "USD"` 与各站点必须引用共享谓词）。
- 变异验证 `/tmp/ab14_mutate.py`：**19 处锚点逐处转红**（红数 21 / 25 / 26 / 21 / 22 / 1 / 1 / 1 /
  29 / 1 / 9 / 1 / 1 / 1 / 21 / 5 / 3 / 12 / 5），基线 collected **709** 全程不变（16 个价目相关
  测试文件），行为中性对照 **0 红**，五文件还原后 sha256 逐字节一致（脚本持有原始字节整份写回，
  绝不用 `git checkout`——本树大量未提交）。
- **一处自纠（本轮方法学产出）**：`cost_analysis` 闸门上的 `not currency_blocked` 第一版**0 红**——
  币种不可判定同时让 `labels` 变空，`len(labels) == 1` 先挡住了。逐条推演后找到唯一能单独触发它的
  输入（一个模型登记 `USD`、另一个没写单位、两者价目数字一字相同），补
  `test_usd_plus_undecidable_arm_refuses_to_price_even_at_equal_prices` 后该锚转红 1 例，
  基线 collected 由 708 变 709。
  "这条 term 看起来多余"既不构成删除理由，也不构成缺锁的理由——**答不出哪条输入只有它能挡，就是没锁**。
- 该中性对照同样如实登记：`_currency_cell` 去掉 `str()` **0 红且没有观测面**（f-string 已强制字符串化），
  故它不是锁，只是"变异脚本本身没坏"的对照。
- **受保护工件三项对账**：改前快照 `/tmp/ab14_re`、改后 `/tmp/ab14_post`、本轮终态 `/tmp/ab14_post3`
  三份 `statistical_report_e2.md` / `_e2_iter.md` **逐字节相同**（只归一生成时间行）⇒ AB-14 对报告输出
  改变 0 行；`experiments/results/main_batch/SHA256SUMS` **2040 条全 OK、0 条不符**；
  归档 T1/B2 载荷 21 条 `cost_usd` 与 `cost` 节**逐位相等**（全载荷仅 `out_dir` / `orig_dir` /
  `prereg_amendment` 三节不同，成因是核查脚本用绝对路径调用，非代码所致）。
- 与入库版本身的差值是**既存陈旧**：`_e2.md` 差 86 行、`_e2_iter.md` 差 88 行，改前改后同一读数
  （成因：S11 记账节与 BH-FDR 节晚于报告生成），本轮不修，登记在 §5。
- 全量口径（本机 macOS Python 3.14.6、xdist `-n 4 --dist loadfile` 带 `--cov`）：**登记前一跑
  9999 passed / 1 failed / 5 skipped、176.76s**（collected **10005** = 9999 + 1 + 5；唯一失败 =
  基线一致性守卫本身，BASELINE 当时仍写 9876 / collected 9881，实收 10005 超 ±6 容差）；
  **刷新 BASELINE 后的收口确认跑 10000 passed / 5 skipped / 0 failed、176.33s、rc=0**。
- 覆盖率本轮**换了性质**：`src/budget/pricing.py` 被改 ⇒ 两跑 `coverage.xml` 复算
  **18391/18916 行（97.2246%）**、**6618/7056 弧（93.7925%）**，较 AB-13 登记 +20 行 / +12 弧，
  新增部分 100% 被锁执行；未覆盖行数 525 与偏弧 438 **逐位不变**；十项逐模块行覆盖逐项复算**全部不变**。
  §14 的口径反过来同样成立：读数**变化**也不是缺陷的证据，佐证是改动面文件清单。
- **`make gates` 全链实测 rc=0，共两跑**（该链跑测试**不带 `--cov`**，与上面两个全量读数分属两个
  口径、不可互换引用）：**更正文档前 169.69s（链墙钟 175.91s）**、**末次文档更正后复跑 168.96s
  （链墙钟 172.74s）**，两跑均 **10000 passed / 5 skipped / 0 failed**，1.2s 差属墙钟抖动；
  链内文档↔工件门三项对账两跑全部 `[OK]`（含"状态登记册 §1 行/分支声明与 `coverage.xml` 实测相符，
  容差 ±0.20pp"）。第二个读数登记的正是本轮那条**文档自纠**（§5 第 3 条）改完之后的状态。

## 5. 未处置（登记）

1. **`oracle_examples_replay.py` 的"无法估算"被印成 `$None`**（本条原文写的是
   `oracle_examples_replay.compute_cost_usd`，**该函数名不存在**——收口前复算 `/tmp/ab15_probe.py` P1
   全仓 `.py` 扫描命中 0 个文件，P2 进一步确认本文件没有任何自己的计价函数，它在 `:508` 直接委托
   `gen.estimate_cost_usd`，而 `:508` 正是本轮五站点之一 ⇒ **"它同样把非美元当美元算"这句被证伪**。
   真实存在的缺陷在渲染侧：`render_readme`（`:581`）打印
   `估算成本 **${generation.get('estimated_cost_usd')}**`，P5 实测三种输入落三种字——
   未登记模型与 `qwen-long`（CNY，本轮改造后）都落 **`$None`**，`0.0` 落 **`$0.0`**。
   也就是说"无法估算"与"确实没花钱"在报告里差一个词、但都挂着同一个美元前缀，且 P6 确认
   **没有任何一行说清是哪条机制**。AB-13/AB-14 的判据在这里同样成立：**字段名（这里是 `$` 前缀）
   里的单位不是实现约束**，而"成本为 `None`"这件事本轮在计价侧写对了、在打印侧仍然被抹平成看起来
   像金额的形状。**本轮实测坐实但不纳入**：改 `:581` 要连带核对 P-1 通道的归档 README 与
   文档↔工件门（该函数正是归档报告的渲染器），改动面与验证面都要另立一组锁。转 AB-15。
2. **`spec_examples_generator` 的 `{"models": <非对象>}` 崩溃通道——形状域比原登记更窄，也更糟**：
   本册原文（及状态登记册 §4 的同一行）写的是"`models` 值为非对象时抛 `AttributeError`"。P3 实测
   六形：**`[]` 与 `None` / 键缺席一律静默返回 `None`**（`(table.get("models") or {})` 把假值折成空表），
   **只有 `'abc'` 与 `5` 这两种"真值非对象"抛 `AttributeError`，落点 `spec_examples_generator.py:337`**。
   同一条形状域里同时有静默塌缩与响亮崩溃两种结局，是 AB-9/AB-12e 的判据在**同一个表达式**上复发。
   P4 另确认盘上真表顶层与 `models` 都是对象、3 条目分别落 `usd` / `usd`（价目 null）/ `other:CNY`，
   故该通道对真批次 0 实例。按 AB-12e / AB-13 的先例（哨兵与顶层非对象已在当时处置），本轮
   **只登记不修**。
3. **更正记录（本轮方法学自纠第二条）**：上述两处原文有两处错——一处函数名（`compute_cost_usd`
   不存在，且其"不看币种"的判断随委托关系一并失效）、一处形状域（"非对象即崩"实为"真值非对象才崩"）。
   两条都在收口前被 `/tmp/ab15_probe.py` 复算推翻并就地更正，未流入对外主张。**教训**：
   登记"未处置站点"也必须带可复算的函数名与形状清单；把"我在 §1 里读过这段代码"当成"我对它的
   记忆可靠"，就是 §14"同值不是证据"在**文档侧**的同型。
4. **入库报告自述"数值逐位可复现"已失效**（`_e2.md` 差 86 行、`_e2_iter.md` 差 88 行）。修它要么重写
   受保护工件（禁止），要么改掉那句自述（属文档↔工件对账，转 AB-15）。
5. **`（缺: ）` 空归因写法与 `$/task` 节标题**：现码仍会对"币种不可判定但价目齐全"之外的情形落一行
   空清单成因；改它会动到受 `SHA256SUMS` 保护的报告文本，转 AB-15。
6. **`tests/test_ae_batch.py:125` 测试侧 `entry.get("currency", "USD")` 兜底**：测试自己造了第二套口径，
   与本轮"判定只写一遍"相反；改它需连带核对该文件全部成本例期望值，转 AB-15。
7. **`pricing.load_price_table()` 的形状降级仍静默**（MEASUREMENT_INTEGRITY §13.2 已登记为
   "取空表不阻断"）：本轮只统一"是不是美元"，没有改"表读不出来怎么办"。
8. **产品侧行为变化须随 CHANGELOG 记为 Changed**：`src/` 的 USD 记账里，**币种键缺席的条目不再当成
   美元**，改走 `COST_USD_PER_1K` 回退或记"未计价"。真表每条目都登记了币种，故存量部署读数不变。

## 6. 不得据本册引用

- 不得引用"全仓币种口径已统一"——§5 第 1、2 条明写两处未纳入。
- 不得引用"入库统计报告可逐位复现"——§5 第 4 条，差 86 / 88 行且改前即如此。
- 不得引用"本轮提高了任何成本读数"——真批次只用 `USD` 已登记模型，三份快照逐字节相同。
- 不得引用"覆盖率下降说明质量变差"或"覆盖率上升说明质量变好"——本轮 `src/` 有改动，
  按 §14 口径，佐证只能是改动面清单与新增行/弧 100% 被锁执行这两件事。
- **不得引用 `oracle_examples_replay.compute_cost_usd` 这个函数名**（全仓 `.py` 扫描 0 命中，见 §5 第 3 条），
  也不得引用"`oracle_examples_replay` 不看币种把非美元当美元算"（它在 `:508` 委托给本轮已统一的站点）；
  同样不得引用"`models` 值非对象一律崩"——P3 实测只有 `'abc'` / `5` 这类**真值非对象**才崩，
  `[]` / `null` / 键缺席是静默 `None`。

## 7. 复算命令

```bash
.venv/bin/python /tmp/ab14_probe.py            # 改前读数需 git stash 才可复现，本树未提交，
.venv/bin/python /tmp/ab14_probe2.py           # 故改前读数以本册 §1 与 §4 的红数为准
.venv/bin/python -m pytest tests/test_experiments_currency_caliber_ab14.py -q --no-cov
.venv/bin/python /tmp/ab14_mutate.py           # 19 锚点 + 对照，rc=0 才算锁齐
.venv/bin/python /tmp/ab14_addcost_check.py    # 第五处接线：归档 21 条 cost_usd 逐位相等
.venv/bin/python /tmp/ab15_probe.py            # §5 第 1/2/3 条的复算：函数名普查 + models 形状域六形
                                               # + 真表 3 条目读数 + $None / $0.0 实际落字
```
