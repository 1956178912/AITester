# AB-8：JSONL 非对象行与主键域崩溃类收口（2026-10-20）

> 立项依据有两条，都是上一轮自己登记的：
> ① `docs/reviews/DATASET_ADAPTER_TOLERANCE_AB5_2026-10-19.md` 结尾把
> `scripts/gates/check_swe_bench_pro_ready.py::_load_enrichment_paths` 的整段静默吞异常
> **登记为下一轮**（与 Z 轮 F06 同形）；
> ② AB-5 立的判据"坏行只作废那一行、留下痕迹、不得中止整批"。本轮把同一族输入再推一步，
> 发现这句判据当时**只对已测的两类形状成立**。零 LLM、$0、未提交。

## 1. 输入域：`json.loads` 能返回六种值，AB-5 只测了两种

AB-5 的 24 例锁覆盖的是"解析失败"（`JSONDecodeError`）与"对象里缺主键"。但
`except json.JSONDecodeError` 只覆盖**语法**损坏，不覆盖**形状**：下面六种都是合法 JSON，
其中五种不是记录。

| `json.loads` 返回 | 文本 | 修复前会发生什么 |
| --- | --- | --- |
| dict | `{"instance_id": "a"}` | 正常路径 |
| list | `[]` | `AttributeError: 'list' object has no attribute 'get'` |
| None | `null` | `AttributeError: 'NoneType' object has no attribute 'get'` |
| str | `"abc"` | `AttributeError: 'str' object has no attribute 'get'` |
| int | `3` | `AttributeError: 'int' object has no attribute 'get'` |
| bool | `true` | `AttributeError: 'bool' object has no attribute 'get'` |

复现分两步。第一步用一次性探测脚本（`tempfile.mkdtemp()` 现写文件、直接调生产函数与门禁函数，
仓内不留任何工件）把五种形状逐一喂进各处读取器；本表与 §2 第 1—5 行的异常消息都来自这一步。
第二步把同一族输入落成 `tmp_path` 回归锁，§2 的第 6 处（主键域）正是这一步跑红才定位到的。

## 2. 六个崩溃点，而不是一个

| # | 入口 | 崩溃表达式 |
| --- | --- | --- |
| 1 | `dataset_loader.py::_load_enrichment` | `row.get("instance_id")` |
| 2 | `dataset_loader.py::_load_raw_data` | 解析结果直接交给 `_build_task_from_swe_row` |
| 3 | `dataset_realbugs.py::_load_raw_data` | `row.get("buggy_code")` |
| 4 | `check_swe_bench_pro_ready.py::_load_enrichment_paths` | `row.get("instance_id")` |
| 5 | `check_swe_bench_pro_ready.py::check_pro_ready` 主循环 | `data.get("instance_id")` 与 `{**data}` |
| 6 | `dataset_loader.py::_build_task_from_swe_row` | `"__" in task_id`（`instance_id` 为 null / 列表 / 字典时） |

第 6 处不是先想出来再写的：**是锁定测试跑红之后才定位到的**。我按"解析结果不是对象"
设计了案例集，`{"instance_id": null}` 这类**对象内主键非标量**的行是另一个缺陷位置，
崩溃点在 `repo_name` 推导那行。原计划把这六个点当六个特例修，实测后才看清是
**同一处假设被复制了六份**——"解析成功就意味着那是个对象、主键就意味着那是字符串"。

**症状分级**（这一层决定处置力度）：第 1—4 处是"整条数据通道不可用"，一行坏数据让
整个数据集加载抛出 `AttributeError`；第 5 处最荒诞——门禁文档声明"退出码 1 表示数据
未就绪"，实际是崩溃，而 Python 崩溃码恰好也是 1，所以**阻塞看起来是生效的**，但调用方
`experiments/run_full_stack_swe_bench_pro.py` 拿不到任何报告，只有一段 traceback。

## 3. 处置：对齐仓库里已有的写法，不新设计

三处读取器统一对齐 `dataset_ult.py::_load_raw_data` **早已存在**的
`if not isinstance(raw_row, dict): skipped += 1; continue`（本轮核对时它已是正确形状，
所以 `dataset_ult` 不需要修改）；门禁主循环按它自己 `unparsed_` 分支的先例，把畸形行
计入 `total_tasks` 与问题清单，**保持 fail-closed**——非对象行是数据缺陷，不得因为
"能解析"就判就绪。

留痕口径按"这份文本谁写的"分两类，不是随意选择：

- **补充文件（人手写的）→ 汇总一条**：坏补充文件通常整份作废，一条 warning 指到文件
  就够定位；逐行刷屏会淹没信号。三类各一条，互不串味。
- **主数据文件（官方工件）→ 逐行含行号**：几百行里要指认具体是哪一行，与本循环既有的
  解析失败分支同口径。

G8 门禁的报表新增 `enrichment_stats`（`exists` / `loaded` / `parse_error` /
`non_object` / `missing_id` / `bad_key`）。加 `exists` 是因为只给四个坏行计数仍有一个
歧义没解决：文件不存在、文件为空、文件全废三种情况的四个计数**都是零**。文本输出原来
只说"（已加载）/（未加载 · 不存在）"，现在把原因逐项打出来。既有报告键一个没动
（`experiments/run_full_stack_swe_bench_pro.py` 消费它们）。

## 4. 主键域：本轮改判过一次，理由是"丢弃等于静默零生效"

初稿的处置是"主键必须是非空字符串，否则按坏行跳过并留痕"。写端到端案例时发现
`{"instance_id": 7}` 在主数据文件里会**撞上第 6 处崩溃**，而查表侧的 `task_id` 来自
主文件——也就是说主文件与补充文件都写 int 主键时，用户表达的是同一个实例，丢弃两侧
等于让补充文件"配了但零生效"，只是丢得有声有色而已。

最终处置因此改为**按形状分**：

- 标量（str / int / float / bool）→ `str()` 归一后使用，映射键域仍是 `str`，两侧同源，
  合并得以真的生效（新增正向锁 `test_int_key_reaches_the_enrichment_lookup`）；
- 列表 / 字典 → 不是标识符，按坏行跳过并留痕（也是写映射处的 `TypeError` 崩溃源）；
- falsy（缺键 / null / 空串 / `0`）→ 沿用 AB-5 的"缺少 instance_id"计数，
  **AB-5 的锁一条没改口径**（其消息串与断言字面量保持原样）。

主数据侧的 `instance_id` 为 null / 列表 / 字典时落带行号的兜底 id（`swe_1`），与既有
"缺键走 `fallback_task_id`"同一出口。**注意这修复的是"崩溃"而不是"少几条任务"**：
兜底 id 本来就存在，只是没机会被用上。

## 5. 一处前提被实测否证（我按代码形状推断，推断错了）

我读 `dataset_ult._iter_records` 的 JSONL 分支，看到 `yield json.loads(line)` 未过滤，
于是断定"`[]` 会被原样 yield 出来"。同一个一次性探测脚本给出相反结果：`[]` 那一份文件返回
**空**。原因是该函数**开头**就把首行以 `[` 起始的整个文件识别为 JSON 数组，而数组分支早有
`isinstance(row, dict)` 过滤——`[]` 那一行根本走不到 JSONL 分支。同一探测还给出另一半事实：
`null` / `"abc"` / `3` / `true` **确实**被原样 yield（`[None]` / `['abc']` / `[3]` / `[True]`），
ULT 通道不崩只是因为消费者 `dataset_ult.py:222` 把它们过滤掉。

教训两层：其一，按代码形状推断执行路径不等于路径真的被走到，推断必须实测；其二，同一份坏输入
在不同格式假设上性质不同，`[]` 在 JSONL 分支是"非对象记录"，在数组分支是"整份文件是个空数组"。

**否证它的不是锁**：本文件里没有 ULT 用例，`dataset_ult` 这条形状域只由一次性探测确认，
不得引用成"ULT 分支已被回归锁覆盖"。

## 6. 一次假绿的自我捕获：变异验证脚本自己空转了一轮

第一轮变异验证报"7 处守卫全部必红"。它没测到任何东西：脚本用
`-k "<mutation name>"` 过滤用例，而 mutation 名字是中文标签，**匹配零条**——pytest
返回"47 deselected"并以非零退出，我的脚本把"退出码非零"当成"变红"，于是七个全"红"。
这正是 AB-5 收紧判据时点名的"绿着但空转的锁"，只不过这次空转的是**验证脚本本身**。

第二轮改法：不带过滤跑整个文件，要求基线 0 failed、每处变异 `failed >= 1`，并打印
**具体变红的用例名**逐项核对是否是对应守卫的那几条；文件还原用 sha256 断言字节一致
（工作树有大量未提交变更，绝不能用 `git checkout` 还原）。

## 7. 复现与验证命令

```bash
.venv/bin/python -m pytest tests/test_jsonl_non_object_row_tolerance.py -q
.venv/bin/python -m pytest tests/test_dataset_manifest_tolerance.py \
  tests/test_dataset_loader.py tests/test_dataset_loader_extended.py \
  tests/test_g8_g2_g4_g5_g6_g7_g1.py -q
```

## 8. 未修面与引用纪律

- **只测了 JSONL 形状域，没测字段值域**。例如 `FAIL_TO_PASS` 里放 `null` 元素、
  `test_patch` 是非字符串——本轮未覆盖，不得引用"数据集适配层坏输入容错已完备"。
- **三个真实数据集仍在 `not_evaluated` 面**（登记册 §4 AB 轮行 ①：`swe_bench_{full,lite,mini}`
  三个子集文件在盘上仍是 **0 字节**）：本轮所有案例都是 `tmp_path` 现写的坏输入，不需要数据集，
  但也不能替代数据集跑通的证据。
- **JSON 数组形态的补充文件**（首行以 `[` 起始）在 `_load_enrichment` 里按逐行解析
  处理，第一条就会解析失败——与 `_iter_records` 的双形态兼容不同口径。本轮**没有**
  把它改成兼容，因为没有任何工件需要它；引用时须说明"补充文件只接受 JSONL"。
- 引用 AB-5 那句判据时应指明"**含非对象行与非标量主键**"；本轮之后它才对整个
  `json.loads` 返回域成立。
