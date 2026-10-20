# AB-12d：共享 loader 的 `task_id` 行集折叠 —— 命名 WARN + 分桶普查（2026-10-20）

零 LLM、$0、全程未提交（用户口径"暂不提交，继续堆叠"）。本轮只处置一个站点：
`experiments/emse_df_spec_analysis.py` 的 `load_arm_rows`——它是三个分析的**共享 loader**
（`emse_docstring_anchor_analysis.py` 与 `emse_docstring_augment_analysis.py` 都复用它），
所以 AB-11 只在 augment 侧加的命名 WARN 从来没有护住另外两条通道。

对应 AB-11 §6⑤ 登记的缺口："`task_id` 重复缩分母已修"不可引用。本轮处置其本体。

---

## 1. 前置读数（先测再说，探针与判据同口径）

普查脚本 `/tmp/ab12d_dup_probe.py`（只读）与锁内 `_bucket_batches` 走同一判据；锁内读数按**桶**记账：

| 量 | 实测值 | 口径 |
| --- | --- | --- |
| glob 命中 `benchmark_*.json` | 246 份 | `experiments/results/**` |
| 真正核到行的文件 | 242 份 | 有 ≥1 个含 dict 行的臂 |
| 核到的臂 | 320 个 | 同上 |
| dict 行总数 | 10659 行 | `details` 里的对象行 |
| 被覆盖的 `task_id` | 0 | 同键后写覆盖前写 |
| 无主键行（五形态） | 0 | 键缺席 / null / 空串 / 非串 / 不可哈希 |
| 非对象详情行 | 0 | `details` 里的裸标量 |
| 空 `details` 例 | 2 份 | `benchmark_examples_20260814_123734.json`、`..._124015.json` |
| 非臂形状（`.mdo.json`） | 2 份 | `pilot_mdo_20261011`、`pilot_mdo_full50` 各 1 |
| 读不动 | 0 份 | OSError / JSONDecodeError |

**探针自纠一处**：AB-12d 前置版本按"glob 命中 246 份"报覆盖面，但 `_census` 只在有 dict 行的臂上
`add(p)`，实际核到 242 份——4 份被静默跳过。这跟 AB-12c 那条"用 `{p.parent ...}` 当扫描根、
把 `main_batch/traces` 整目录漏掉"的探针是同一类缺陷（"没打开"被当成"打开了且干净"）。
本轮把分桶等式写进锁：`judged + empty_details + other_schema + unreadable == glob`。

## 2. 处置口径（只增不改：返回域一个字不动）

| 折叠形态 | 旧行为 | 本轮处置 | 会不会改变既有读数 |
| --- | --- | --- | --- |
| 同 `task_id` 后写覆盖前写 | 静默缩字典，下游分母跟着缩 | 计数 + 命名 WARN，点名文件、臂、`details 行 N → 行摘要 M`、被覆盖 id | 不会（真批次 0 例） |
| 键缺席 / 空串 | 都折成同一个 `""` 键 | 两种机制分开计，消息不并写 | 不会 |
| 显式 `null` 键 | 落 `None` 键 | 单列 `value_null` 桶 | 不会 |
| 非字符串且可哈希（如 `7`） | 直接成键 | `not_string` 桶 | 不会 |
| 不可哈希（list / dict） | `TypeError` 崩整条分析 | `unhashable` 桶 + 跳过该行 + WARN | 由崩改为披露（AB-9 允许的一侧） |
| `details` 里的非对象行 | `AttributeError` 崩 | `非对象详情行 N` + WARN | 同上 |

两条判据值得单独记：

1. **五桶是一次划分**：一行只进一个桶。本轮前置写法把不可哈希键先记 `not_string` 再记
   `unhashable`，5 行会报成 6 行——披露自身的计数虚增，与它要纠正的错读同类。d5 锚点专打这条。
2. **WARN 只在真的发生时打印**：0 例时 stderr 一字不出，入库读数与报告逐字节不变。
   d10 锚点（把 WARN 改成恒发）转红 3 例，含真批次那条。

## 3. 入库工件未被重写（本轮只改 loader 与测试）

- `git status --porcelain "experiments/results/**/benchmark_*.json"` → **0 行**；
- 锁 `test_committed_batch_jsons_are_not_rewritten` 逐个核 `experiments/results/**/SHA256SUMS`
  条目（本轮实测对面 ≥100 个工件，断言为下界），sha256 逐位比对；
- 三个消费方套件（df_spec / anchor / augment）与本轮 26 条锁同批跑：`126 passed / 0 failed`，
  真批次 stderr 为空 ⇒ 任何已入库报告的输入未变。

## 4. 验证

- 锁：`tests/test_experiments_arm_row_collapse_ab12.py` **26 条**（折叠披露 6 / 无主键形态 11 /
  既有 fail-closed 保留 4 / 真路径与分桶 5），全绿；
- 变异验证 `/tmp/ab12d_mutate.py`：**rc=0，14 锚点 + 1 行为中性对照全部到位，0 MISS**；
  基线 `collected=126 passed=126`，收集数在 16 轮变异中恒为 126，每轮改后先 `compile()`，
  结束后两个文件按 sha256 **字节还原**（本树大量未提交，绝不用 `git checkout` 回滚）。

| 锚点 | 删掉的是什么 | 变红数 |
| --- | --- | --- |
| d1 | 非对象详情行的计数化滤除 | 1 |
| d2 | 键缺席桶（并入空串） | 4 |
| d3 | `null` 值桶（落到 not_string） | 3 |
| d4 | 空串桶（无痕作废） | 3 |
| d5 | 五桶划分撤销，一行记两次 | 3 |
| d6 | 不可哈希行的跳过 | 4 |
| d7 | 覆盖计数 | 5 |
| d8 | 点名上限（10 → 1000） | 1 |
| d9 | 无主键段永不落字 | 10 |
| d10 | WARN 恒发 | 3 |
| d11 | 普查读不动桶静默跳过 | 1 |
| d12 | 普查无可用臂桶静默跳过 | 1 |
| d13 | 普查非臂形状桶静默跳过 | 3 |
| d14 | 普查空 details 桶静默跳过 | 3 |
| ctrl_d | 只改文档串 | 0（对照通过） |

d11/d12 首轮按 ≥2 记、实测 1 红后下调，理由可复核：真批次里这两桶**各 0 例**（246 份全部可读，
2 份出局文件都在更早的"results 非对象"处被拦），等式只能由合成语料那条 `test_bucket_equation_
is_stressed_by_a_corpus_with_all_four_kinds` 压。变红的正是本轮为这两个 0 例桶专补的锁。

**本轮新增判据（接 MEASUREMENT_INTEGRITY §15）**：0 实例的**桶**也要有实例来源——真语料给不出
实例时，等式必须由合成语料压，否则那条守卫是痕都不留的。

## 5. 不得据本册引用

1. 不得引用"`task_id` 折叠已消除"——本轮只把静默折叠改成**命名披露**，同键后写覆盖前写的语义
   一字未改（这是刻意保留的：改语义会让已入库报告的口径不可比）。
2. 不得引用"三个 EMSE 分析的 loader 已全锁"——本轮锁的是共享 loader 的折叠与形态计数；
   各分析脚本**下游**对 `out` 的其他用法（配对、子集筛选）不在本轮判据内。
3. 不得引用"批次工件不可能有重复 task_id"——实测是**当前 246 份里 0 例**，不是结构约束。
4. 不得把 d11/d12 的 1 红读成"覆盖面锁弱"——真语料 0 例，锁的作用面由合成语料提供。

## 6. 复算命令

```bash
# 分桶普查读数（246 / 242 / 320 / 10659 / 0 / 0）
.venv/bin/python /tmp/ab12d_dup_probe.py

# 26 条锁 + 三个消费方套件
.venv/bin/python -m pytest tests/test_experiments_arm_row_collapse_ab12.py \
  tests/test_emse_df_spec_analysis.py tests/test_emse_docstring_anchor_analysis.py \
  tests/test_emse_docstring_augment_analysis.py -q --no-cov

# 变异验证（rc=0；结束时按 sha256 断言字节还原）
.venv/bin/python /tmp/ab12d_mutate.py

# 批次工件未被改写（应为 0 行）
git status --porcelain "experiments/results/**/benchmark_*.json"
```
