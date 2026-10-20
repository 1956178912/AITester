# AB-12e：价目表读取点 —— 非对象顶层改为披露，`None` 哨兵与显式 null 分离（2026-10-20）

零 LLM、$0、全程未提交。站点是 `experiments/spec_examples_generator.py` 的
`load_price_table`（:274）与 `estimate_cost_usd`（:309），AB-9 登记在册
（`EXPERIMENTS_JSON_DOMAIN_AB9_2026-10-20.md` §4 行 97 与行 104）。

---

## 1. 前置读数（`/tmp/ab12e_price_probe.py`，只读、只打 tmp 合成文件）

| 顶层形状 | 改前 `load_price_table` | 改前下游 `estimate_cost_usd` | 改后 |
| --- | --- | --- | --- |
| dict（真表） | 原样返回 | `0.0027` | `0.0027`（一字不变） |
| list / str / int / float / bool | **原样返回** | `AttributeError`（崩在 `table.get`） | 空表 + 留痕 ⇒ `None` |
| `null` | 返回 `None` | 哨兵吞掉 ⇒ **回头读盘**给出 `0.0027` | 空表 + 留痕 ⇒ `None` |
| 文件缺失 / 语法损坏 | 静默 `{}` | `None`（无痕） | `{}` + 点名机制 |

两条要单独强调：

- `null` 那一行是**两件事叠在一起**：读取点把 `None` 交出去，`None` 又恰是形参的"未提供"哨兵，
  于是"这份价目表写着没有价目表"被读成"按另一份文件的价目计费"，报告里出现一个来自
  `experiments/price_table.json` 的金额。AB-11 的"键缺失 ≠ 值为 null"是同一族，方向相反。
- 崩溃位置决定性质：`oracle_examples_replay.py:1030` 在**整轮付费 LLM 重放之后**才读价目表，
  所以这条 `AttributeError` 不是"响亮失败省了钱"，而是"钱花完、报告一行没有"。
  AB-9 的分析层判据（响亮崩溃可接受）在这里**不适用**，原因就是这个先后顺序。

## 2. 处置口径（对齐仓内先例，不改计费口径）

| 改点 | 改法 | 依据的先例 |
| --- | --- | --- |
| 非对象顶层 | 落空表 + `logger.warning` 点名形状 | `statistical_analysis.py:859`、`src/budget/pricing.py:71` |
| 读不动（缺文件 / 坏语法） | 保留降级，但**说得出是哪条机制** | 同上的 `logger.warning` 口径 |
| `price_table=None` | 拆成三态：省略 ⇒ 读盘；显式 `None` ⇒ 声明无表，**不读盘**；非对象 ⇒ `None` + 留痕 | AB-11 值域三态先例 |
| 成本为 `None` | 留痕明写"成本估算为 None（不是 0）" | AB-10"缺席不得读成零" |

文档串原先写"缺失/非法 → 空 dict"而返回域并非如此——本轮把**代码改成与声明一致**，
不是把声明改成与代码一致。

## 3. 入库读数与既有测试

- 盘上真表顶层是 dict、`models` 有 3 个键（`deepseek-flash` / `agnes-3.0-flash` / `qwen-long`），
  本轮改动只影响"顶层非对象 / 显式 None"两支，真表路径逐字段不变；
- 同族既有套件一并跑：`tests/test_oracle_examples.py`、`test_examples_multisample.py`、
  `test_oracle_examples_production.py`、`test_ae_batch.py`、`test_ak_batch.py` 与新锁
  合计 **192 passed / 0 failed**（变异验证基线）；
- 未改写任何 `experiments/results/**` 工件。

## 4. 验证

- 锁：`tests/test_experiments_price_table_ab12e.py` **26 条**（非对象顶层 14 / 哨兵三态 5 /
  真表不变 7），全绿；
- 变异验证 `/tmp/ab12e_mutate.py`：**rc=0，8 锚点 + 1 行为中性对照，0 MISS**；基线
  `collected=192 passed=192`，收集数在 9 轮变异中恒为 192，每轮先 `compile()`，
  结束后按 sha256 断言两个文件字节还原。

| 锚点 | 删掉的是什么 | 变红数 |
| --- | --- | --- |
| e1 | 顶层非对象守卫整体 | 7 |
| e2 | 顶层非对象的留痕 | 7 |
| e3 | 两条降级机制并写 | 6 |
| e4 | 读不动留痕 | 2 |
| e5 | 显式 `None` 分支 | 1 |
| e6 | 整体退回旧哨兵写法 | 5 |
| e7 | 非对象价目表直传的守卫 | 1 |
| e8 | 省略分支反读 | 4 |
| ctrl_e | 只改文档串 | 0（对照通过） |

另有一条**默认参数绑定的反面锁**（不是锚点而是断言）：AB-9 曾自捕获"改 `gen._PRICE_TABLE_PATH`
的探测不生效"，本轮把这件事写成 `test_default_argument_binding_is_still_the_repo_table`
——用 `inspect.signature` 直接锁默认值在定义期绑定，桩替换模块变量不影响读取。
"读盘是否发生"因此一律用 `monkeypatch` 替换 `gen.load_price_table` 本身来证明。

## 5. 本轮新查、未处置（转 AB-13 登记）

同一轮普查顺手量到**同族两处**，本轮**只登记不修**（避免一册内同时改两个站点导致锁的归属说不清）：

| 站点 | 实测 | 未修的原因 |
| --- | --- | --- |
| `emse_stats_report.py:453` `_load_price_table` | list / `null` / str 顶层均 `AttributeError`（只拦 `OSError, ValueError`） | 与本轮站点同形但崩在读取点自身；修它需要另一组锁 |
| `emse_stats_report.py:473` `cost_effectiveness_block` | `if price_table is None: price_table = _load_price_table()` 是**同一个哨兵双身份** | 同上；且该函数被成本-效果节直接消费，读数锁要另立 |

对照：`statistical_analysis.load_price_table`（:859）与 `src/budget/pricing.load_price_table`
（:71）**已经是**本轮采用的形状（`isinstance` 判定 + 警告留痕），无需改。

## 6. 不得据本册引用

1. "价目表读取已全仓收口"——本册只处置 `spec_examples_generator` 一处，§5 两处仍是崩溃。
2. "成本估算现在永不为假数"——诚实条款未变：模型未登记 / 币种非 USD / 价格为 null 一律 `None`，
   本轮只是**新增**了"顶层非对象 / 显式 None"两支的 `None`，未新增任何计价能力。
3. "`0.0027` 是某次真实重放的成本"——它是本轮**探针用的固定 usage**（5000 / 1000 token）
   对真表的算术读数，不是任何批次的实际消耗。
4. AB-9 原登记的 `0.0015` 与本册 `0.0027` 不是同一笔：usage 不同，勿混引。

## 7. 复算命令

```bash
.venv/bin/python /tmp/ab12e_price_probe.py          # 前置读数（改后复跑即得本册 §1 右列）
.venv/bin/python -m pytest tests/test_experiments_price_table_ab12e.py \
  tests/test_oracle_examples.py tests/test_examples_multisample.py \
  tests/test_oracle_examples_production.py tests/test_ae_batch.py tests/test_ak_batch.py \
  -q --no-cov                                        # 192 passed
.venv/bin/python /tmp/ab12e_mutate.py               # rc=0，8 锚点 + 对照
```
