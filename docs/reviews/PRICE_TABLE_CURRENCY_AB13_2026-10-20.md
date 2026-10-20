# AB-13：`total_usd` 声明美元而实现不看币种，加同族哨兵与返回域收口（2026-10-20）

> 零 LLM、$0。站点全部在 `experiments/emse_stats_report.py`。本轮处置 AB-12 收口时转来的两处
> （`:453` 读取点、`:473` 同形哨兵），**并在前置复测中新坐实第三处**——字段名声称美元、
> 实现里币种不参与判定。判据链：AB-9（静默缩分母才是缺陷）→ AB-10（缺席不得报成零命中）→
> AB-11（键缺席 ≠ 值为 null ≠ 读不动；同值不是证据）→ AB-12c（0 实例要连覆盖面一起锁）→
> AB-12d（披露自身的计数也要划分）→ **AB-13（字段名里的单位不是实现约束，直到实现参与判定）**。

## 1. 前置读数（`/tmp/ab13_probe.py`、`/tmp/ab13_probe2.py`，只读 + 只打 tmp 合成文件）

| 编号 | 测的事 | 改前实测 |
|---|---|---|
| R1 | `_load_price_table` 对六种合法非对象顶层（list/str/int/float/bool/null） | **全部抛 `AttributeError`**，而 docstring 写着"缺失/损坏 → 空表" |
| R2 | 同函数对"文件不存在 / 空文件语法错 / `models` 键缺席 / `models` 值为 list / 值为 null" | 一律无痕返回 `{}`，与"表里真的一个模型都没登记"同形 |
| R3 | `cost_effectiveness_block` 三态（deepseek-flash USD 0.3/1.2，1M+1M token） | 省略 `1.5` / 显式 `None` **也是 `1.5`**（回头读盘）/ 显式 `{}` 是 `0.0` |
| R4 | **本轮新发现**：币种是否参与 `total_usd` | `qwen-long` 真表登记 CNY 0.5/2.0，实测 `total_usd=2.5`、`n_priced=1`——人民币被累加成美元 |
| R5 | `if not price` 之后的条目形状 | `{"m": 5}` 时 `price.get` 直接 `AttributeError`；空条目与未登记共用一个桶 |
| R6 | 真批次实际用到的模型（受保护读数的前提） | 三臂 783 行只用 `deepseek-flash`（USD 已登记），`n_priced` 261/261/226、`n_unpriceable` 全 0 |

R6 是本轮能"修而不重写工件"的全部依据：币种闸门对真批次一行也不改变，它只关掉一条尚未发生的通道。

## 2. 处置口径

1. `_load_price_table`：非对象顶层 → 空表 + **点名机制**（`价目表顶层非对象（list）` 等）；
   `models` 键缺席与 `models` 值为非对象分两条读数；文件不存在与一般 `OSError` 分两条。
   **返回域一字不动**（仍是 models 层映射或空表）。
2. `cost_effectiveness_block` 的 `price_table` 按 AB-12e 先例拆三态：新增 `_UnsetPriceTable` 哨兵，
   **只有省略形参才读盘**；显式 `None` 与非对象价目按空表计并留痕。
3. **币种闸门**：只有 `currency` 大写等于 `USD` 的条目进入 `total_usd`；非 USD 记
   `currency_not_usd:XXX`，币种键缺席记 `currency_absent`（缺席不默认成任何单位）。
   仓内 `statistical_analysis.py:991` 是另一条口径（随行输出 `currency`、缺省视为 USD），
   本处字段名是 `usd` 且报告表不带币种列，取剔除一侧；**该分歧本轮不统一，登记在第 5 节**。
4. 不可计价机制分桶：`model_unregistered` / `entry_empty` / `entry_not_object:T` /
   `currency_absent` / `currency_not_usd:X` / `price_null` / `multi_model_row`，
   一行只进一桶，`sum(reasons.values()) == n_unpriceable_rows` 写进断言。
5. 披露键 `n_unpriceable_reasons` **只在真发生剔除时写入**；`_render_cost_section` 的机制点名行
   同样只在有机制时落字（0 机制时报告长度逐行不变）。

## 3. 既有断言与新口径冲突时的裁决

`tests/test_emse_stats_report.py::TestCostEffectivenessA07` 两例用不写 `currency` 的合成条目，
新口径下它们会从"计价成功"退化为"根本没计价"。逐条裁决后**改其输入而非放宽其断言**：

- `test_single_model_priced_exactly`：条目补 `"currency": "USD"`，算术断言原样保留；
- `test_zero_detection_no_division`：条目补 `"currency": "USD"`，**另加**
  `n_priced_rows == 1 and total_usd > 0`——否则这条除零守卫的锁会退化成假绿
  （分子为 0 时 `usd_per_detection` 为 `None` 与守卫无关）。

这条是本轮的方法学产出：**改口径撞上旧断言时，先判旧期望对不对，再改它，并且改后必须让该例
仍测它声称的东西**。登记入 `docs/MEASUREMENT_INTEGRITY.md` §16。

## 4. 验证

- 新增 `tests/test_experiments_price_table_ab13.py` **51 例**：返回域 6 参数化 + 语法/缺席/键缺席
  分桶 + 六机制互不相同 + 真表无留痕 + 禁 pragma + 哨兵三态 6 + 币种与机制分桶 14 + 渲染 5 +
  真路径不变量 7（三臂 $/task 逐位、无披露键、783 行/3 文件覆盖面下界、两模型证明闸门不空转、
  入库报告确实早于 cost_eff 块）。
- 变异验证 `/tmp/ab13_mutate.py` **15 处锚点逐处转红**（p1 7 / p2 2 / p3 10 / p4 2 / s1 1 / s2 9 /
  s3 7 / c1 4 / c2 2 / e1 1 / e2 1 / e3 2 / r1 4 / r2 9 / m1 5），行为中性对照 **0 红**，
  收集数 78 全程不变，sha256 断言字节还原（本树大量未提交，绝不用 `git checkout`）。
  c1（币种闸门撤销）与 c2（缺席默认成 USD）各红 4 / 2 例，是 R4 那条新发现的真锁。
- 两处自纠：p1 第一版锚点把 `if` 连赋值删空留下 `else:` 直接跟 `elif` ⇒ `SyntaxError`，
  被 `compile()` 前置检查拦下；r2 预期红数从 10 下调到 9，依据是打印出的用例名**全部**是消费
  `n_unpriceable_reasons` 的锁（AB-12c §15 的"预期红数订高不等于缺锁"同型）。
- 全量口径（本机 macOS Python 3.14.6、xdist `-n 4 --dist loadfile` 带 `--cov`）：**登记前一跑 9875 passed / 1 failed / 5 skipped、177.56s**（collected **9881** = 9875 + 1 + 5；唯一失败 = 基线一致性守卫本身，BASELINE 当时仍写 9825 / collected 9830，实收 9881 超 ±6 容差）；**刷新 BASELINE 后的收口确认跑 9876 passed / 5 skipped / 0 failed、179.05s、rc=0**，其 `coverage.xml` 复算 **18371/18896 行（97.2216%）、6606/7044 弧（93.7819%）**，与 AB-8/AB-9/AB-10/AB-11/AB-12 登记同值——按 §14，同值只作观测，不作佐证。`src/` + `config.py` 零改动，佐证是改动面文件清单
  （1 个 `experiments/` 脚本 + 1 个新测试文件 + 1 个既有测试文件 + 文档），不是覆盖率同值。
- 另立一条**不可互换**的口径：`make gates` 全链跑测试**不带 `--cov`**，本机共三跑均 **rc=0** ——
  前两跑 **174.92s / 176.10s**（均 9876 passed / 5 skipped / 0 failed），收口后为验证末次文档改写
  再跑一次 **193.34s**（同样 9876/5/0），该跑与两个独立小批 pytest 并发，耗时不作代表值，登记只为
  说明 174.92/176.10 不是下界。三个读数与上面 179.05s 分属两个口径，引用时必须带口径标签。

## 5. 未处置（登记）

1. `statistical_analysis.py:991` 的"币种缺省视为 USD"与本处"缺席剔除"并存，两套口径未统一；
   统一会动到受保护的成本报告，转 AB-14。
2. `_render_cost_section` 的 §4.1 表不带币种列，读者无从看出某臂被剔了多少非 USD 行——
   本轮只在有机制时追加一行点名，**没有新增计价能力**。
3. 价目表补齐 `agnes-3.0-flash` 价格是数据事项，不是代码事项；本轮未碰 `price_table.json`。

## 6. 不得据本册引用

- 不得引用"成本口径已全仓统一"——第 5 节第 1 条明写两套口径并存。
- 不得引用"真批次成本被改过"——R6 与本轮实测逐位一致（`0.025885 / 0.003359 / 0.004543` $/task）。
- 不得引用"币种闸门提高了任何读数"——它只收窄 `total_usd` 的准入，真批次 0 行受影响。

## 7. 复算命令

```bash
.venv/bin/python /tmp/ab13_probe.py            # 改前读数需 git stash 才可复现，本树未提交，
.venv/bin/python /tmp/ab13_verify.py           # 故改前读数以本册 §1 与 §4 的红数为准
.venv/bin/python -m pytest tests/test_experiments_price_table_ab13.py tests/test_emse_stats_report.py -q --no-cov
.venv/bin/python /tmp/ab13_mutate.py           # 15 锚点 + 对照，rc=0 才算锁齐
```
