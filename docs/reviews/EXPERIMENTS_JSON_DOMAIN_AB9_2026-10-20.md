# AB-9：`experiments/` 层 68 处 `json.loads` 的返回域普查（2026-10-20）

> 零 LLM、$0、全部改动堆在既有未提交树上。本轮**只普查与登记，不批量改造**：
> 68 处调用点逐处读数，结论分三类——响亮崩溃 / 已 fail-closed / **静默丢数据**，
> 本轮只处置第三类里"数字当前被引用且属复现入口"的一处，其余 11 处按机制登记。
> 本册撤销 `docs/PROJECT_STATUS_REGISTER.md` §4 AB-8 行 ⑥ 的"未普查"登记。

## 1. 判据来自上一轮，普查面来自上一轮的"未做"

AB-8 的结论是：`json.loads` 有**六种合法返回**（对象、数组、字符串、数字、布尔、null），
而 `except json.JSONDecodeError` 只挡语法、不挡形状；"一行坏数据让整条数据通道不可用"
与"配了但整份零生效"都是同一处假设被复制出来的缺陷。当时把 `experiments/` 层
（42 个文件、68 处调用）明确登记为**未普查**，理由是"本轮结论只适用于 `src/datasets/`
三个适配器与 G8 门禁"。本轮补的就是这块。

普查方法与 AB-8 相同：**先按返回域把每种形状喂进代码路径读数**，再决定处置。
两个只读子代理各取一半（37 处 / 31 处），逐站点填表（来源、per-line 还是 whole-file、
消费者表达式、五种形状各自的结果、来源工件与 SHA256SUMS 保护、既有守卫）。
普查面本身可现算复算：`experiments/*.py` 共 **95** 个文件，其中 **42** 个含 `json.loads` 调用点，
按行计数与按出现次数计数两种口径都是 **68** 处（不存在一行两次调用的情况）——命令见 §6。
分析层与产品层的判据不同，本轮明确采用**分析层判据**：

- **响亮崩溃是可接受的**：分析脚本宁可非零退出，也不要产出一个看起来正常的错数字；
  给 68 处都加 `isinstance` 会把崩溃换成静默，方向相反。
- **静默丢弃才是缺陷**：批次/行被 `continue` 掉、而报告与池化区间照出，
  读者无法从工件本身看出分母少了几份。

## 2. 汇总：68 处里 12 处会静默丢数据

| 分类 | 处数 | 判读 |
| --- | --- | --- |
| 任一非对象返回下响亮崩溃（`AttributeError` 或 `TypeError`，一路上抛到 `main`） | 42 | 不改。崩溃码非零、无报告产出，不会被误引用 |
| 已 fail-closed（显式判形状并给出可读错误或 `exit 1`） | 9 | 不改。形状假设已被显式化 |
| 崩溃被上层 `except` 吞掉、但在报告里留痕（如"读取失败"行） | 5 | 不改。已有披露口径 |
| **静默：至少一种形状下不抛、只让数据消失** | **12** | 逐处列名见下表，本轮处置 1 处 |

合计 42 + 9 + 5 + 12 = 68（A 组 37 处 + B 组 31 处）。12 处静默点按
"数字是否正在被引用 / 是否属复现入口"排序，处置一栏即本轮的取舍：

| 站点 | 静默形态 | 本轮处置 |
| --- | --- | --- |
| `target_quality_replay.py:116` | 五种非对象与语法错误都只 `continue`，坏批次从逐批次表、`totals`、`all_values` 里一起消失，没有任何"跳过几份"计数；只有目录 100% 不可解析才 `[FAIL]`。而产物正是 `BASELINE.yaml` `target_quality` 节在引用的区间，入口是 `make target-quality` | **已改为计数披露**（§3） |
| `analyze_t1_b2_main_batch.py:48` | `(x or {})` 把 `null` / `[]` / `0` 一律降成空对象：种子批次贡献零行而 `pooled` 与 `per_seed` 照常渲染；`GATES.json` 为 `null` 时渲染成 `gates_all_pass: FAIL`（**缺失被当成不通过**）；原批次循环的宽 `except Exception: continue` 还会把一对种子从配对比较里静默摘掉 | **本行原文列的三件 0 件处置、全部继续登记**：`(x or {})` 降空对象、`GATES.json` 缺席 → `gates_all_pass: FAIL`、宽 `except Exception: continue` 静默摘掉一对种子。**归因错位已由 AB-11 轮撤销**：AB-11 处置的是同一文件里的另一站点（profile 预设读取：四机制各给原因码、原因由机制拼不再写死 git、新增"档名缺席不等于无漂移"分支、两处不可核验文案打印登记原因，见 `docs/reviews/ABSENT_VS_ZERO_AB11_2026-10-20.md` §3），本行原文从未列过该站点，故不能记作本行的部分处置。三件在 AB-11 收口后逐个实测均 0 实例：该目录 11 份 JSON 0 份读不动；3 份种子批次顶层均为对象、`results` 为非空对象且三臂全在场（`or {}` 不改变任何一个）；`GATES.json` 实为对象且 `all_pass=true`；原批次目录 glob 命中 10 份、解析成功 10 份、被 except 摘掉 0 份、三 seed 配对无缺席 |
| `emse_docstring_augment_analysis.py:105` | `except (OSError, KeyError, TypeError, JSONDecodeError): return rows`，全部 `spec_augment_applied` 留在 `None`，`domain_stats` 把 `None` 归入 `none` 桶，报告读作"增广从未触发"而实际是"工件读不动"——普查里最像"结论翻转"的一处 | **已由 AB-11 处置**（值域三态 `None` / `key_absent` / `audit_unreadable` + 命名 WARN + 三数披露，删掉 `# pragma: no cover`；真路径 50/50 行仍落 `none`，入库读数逐字节不变，见 `docs/reviews/ABSENT_VS_ZERO_AB11_2026-10-20.md` §2.2） |
| `emse_ult_gold_diagnosis.py:556` | 顶层为字符串时 `[r for r in data if isinstance(r, dict)]` 得空列表，`official_source` 退化成本地 gold，`upstream_bodies_equal` 于是**拿本地 gold 和自己比**并报一致性 | **已由 AB-10 处置**（非列表顶层抛 `TypeError`、丢行报数、缺席工件 fail-closed、无上游可比时一致性返回 `None`；恒真那条已实测，见 `docs/reviews/ABSENT_VS_ZERO_AB10_2026-10-20.md` §2.2） |
| `emse_ult_gold_diagnosis.py:697` | `if supplement:` 只判真假，`null` / `false` / `0` / `""` / `[]` 都让 README 第 4d 节整段消失且无消息（`:1143` 的"缺文件即省略 4c 节"同形） | **已由 AB-10 处置**（给了路径而文件缺失即抛错、无 `records` 打 `[WARN]`、4c/4d 未渲染时在 README 原地点名原因） |
| `mast_trace_analysis.py:73` | 非对象行被 `isinstance` 滤掉（有留痕的意思），但整文件全是坏行时仍计入 `files`——**分母口径**与 AB-5 缺主键行同形 | **部分由 AB-11 处置**（同一站点的另一半更严重：`parse_trace_file` 损坏即返回 `None`，调用方把 `meta.baseline` 明写臂名的文件整体归入 `unknown`，坏行前已解析的记录**无痕**作废；AB-11 改为损坏也返回结构、归臂口径与完好文件一致、作废量汇总并披露，5 个损坏目录复刻证明判定分母不变，见 `docs/reviews/ABSENT_VS_ZERO_AB11_2026-10-20.md` §2.3）。**本行原文所指的"非对象行仍计入分母"已由 AB-12c 处置**（`parse_trace_file` 计数并按类型留痕、
"整份形状不合"不再进 `files` 分母、披露行只在出现时写入；0 实例时入库报告逐字节不变，
见 `docs/reviews/SITE_C_MAST_NONOBJECT_AB12C_2026-10-20.md`）。AB-11 当时的普查读数是"9086 个 trace 文件里非对象行 0 个、
"能打开但零事件"的文件 0 个"，AB-12c 复查发现该探针把 trace 目录的父目录当扫描根、漏扫 `main_batch/traces`，
修正覆盖面后为 138 目录 / 8539 文件 / 125270 行，非对象行仍为 0——**0 实例这条结论不变，但覆盖面数字以 AB-12c 为准** |
| `build_spec_anchor_table.py:73` 与 `:111`、`emse_dsl_diag3.py:149`、`helpers_tier_replay.py:88` 与 `:123`、`spec_examples_generator.py:191` | **刻意的**静默且已留痕：分别计入 `stats` 的 `rejected_json`、显式 `isinstance … continue`、`n_files` 对 `n_entries_used` 的差额、带原因码的 `schema_invalid_or_no_valid_example` | 不改（登记理由） |

**"有显式 `isinstance` 且已有计数或原因码"的静默与"消失得无影无踪"的静默是两类**，
本轮只补后者——因此上表最后 6 处判为"不改"，不是漏项。

## 3. 处置 1：`target_quality_replay.py` 的跳过计数

按 AB-8 门禁 `enrichment_stats` 的先例：**只新增键，既有键与既有数值一个不动**。

- `_collect` 返回值新增 `skipped`：`unreadable`（读失败或语法错误，按文件名）与
  `non_object`（顶层类型名）两个清单分开计。
- `_render` **只在有跳过时**追加"## 读取完整性"一节，并写明"引用本报告任何数字时
  必须同时引用本节"。零跳过时不出现该节，因此当前入库报告逐字节不变——
  这一点由锁执行（见下），不是由措辞承诺。
- `main` 在有跳过时向 stderr 打 `[WARN] 若干份批次被跳过（不可解析 x / 顶层非对象 y）`，
  **退出码不变**：仍有可用批次时返回 0（数字有效，报告自我披露），全部不可用时
  仍走原有 `[FAIL]` 返回 1（fail-closed 未放宽）。

验证入口与实测：

| 项 | 实测 |
| --- | --- |
| 回归锁 | `tests/test_experiments_json_domain_ab9.py` **14 例**（非对象计数与分开归因 5 例、只增不改 1 例、披露节存在性与引用纪律 3 例、CLI 契约 3 例、入库工件复现 2 例） |
| 变异验证 | 6 处锚点逐处删除**全部转红**：非对象计数改回静默 8 红、整条 `isinstance` 分支删除 9 红、不可解析计数删除 3 红、披露节永不渲染 3 红、CLI 告警删除 2 红、引用纪律句改写 1 红；脚本要求基线全绿、逐处打印变红用例名、sha256 断言字节还原 |
| 入库工件等价 | 对 `experiments/results/main_batch`（10 份批次、实测跳过 0 份）重放 `_render`，与 `target_quality_report.md` **逐字节相同** |
| 覆盖率影响 | 本轮 `src/` 零改动，`coverage.xml` 读数与 AB-8 逐位相同（18371/18896 行、6606/7044 弧）——`experiments/` 不在 `--cov=src` 口径内 |
| 全量实测 | 登记前一跑 9614 passed / 1 failed / 5 skipped（collected 9620，169.40s 带 `--cov`，唯一失败 = 基线一致性守卫自身）；刷新后收口确认跑 **9615 passed / 5 skipped / 0 failed，169.97s**，rc=0 |

## 4. 普查里两条与"形状"无关但同族的读数

这两条不是本轮加的判据，是普查顺带照出来的既有口径问题，如实登记：

1. **`experiments/price_table.json` 是普查里唯一"人写、无 `SHA256SUMS` 保护、多消费者"的 JSON 输入**：
   `experiments/` 顶层只有**两份**人写 JSON，另一份 `injection_benchmark_samples.json` 同样不在任何
   `SHA256SUMS` 之下，但只被 `tests/test_p2_injection_benchmark.py:31` 一处消费，所以"多消费者"这一条
   只对价目表成立。价目表被 5 处读取（`analyze_t1_b2_main_batch.py:765`、`emse_stats_report.py:452`、
   `emse_stats_extensions.py:171`、`run_b8_injection.py:672`、`spec_examples_generator.py:277`），
   这 5 处读取点**全部只给键缺省、不判顶层形状**，且该文件不在任何 `SHA256SUMS` 之下。
   五种非对象返回在全部 5 处都是**响亮崩溃**（`AttributeError` / `TypeError`），因此按本轮判据
   **不改**；两处带 `except` 的读取点降级的是**语法**而不是形状——实测五种形状读数如下，
   它把我先前写的"`[]` 在这两处降级为空表"直接否证了：

   | 读取点 | `[]` / `"abc"` / `3` / `true` / `null` 实测 | 语法错误实测 |
   | --- | --- | --- |
   | `emse_stats_report.py:452`（`except (OSError, ValueError)`） | `AttributeError: 'list'/'str'/'int'/'NoneType' object has no attribute 'get'`（`.get("models")` 在 try 内，但 `except` 不接 `AttributeError`） | `{}`（调用方按"价目未登记"口径输出） |
   | `spec_examples_generator.py:277`（`except (OSError, JSONDecodeError)`） | **原样返回**五种非对象值，读取点自身不抛；崩溃在调用方 `:285` 的 `table.get(...)` → `AttributeError` | `{}` |
   | `analyze_t1_b2_main_batch.py:765`、`run_b8_injection.py:672` | 无 try，`.get` → `AttributeError`（表达式级 10 组合实测全抛） | `JSONDecodeError` 上抛（不降级） |
   | `emse_stats_extensions.py:171` | `_load` 无 try 且原样返回，崩溃在消费点 `:216` 的 `data["models"]` → `TypeError`（5 组合实测全抛） | `JSONDecodeError` 上抛 |

   代价不对称的一处：`spec_examples_generator.py:277` 的崩溃发生在**整轮付费 LLM 重放之后**
   （`oracle_examples_replay.py:1030` 调用点在任何 try 之外），代价口径与 AB-8 的产品侧缺口同类，
   登记为下一轮候选。另有一处同族但更隐蔽的口径撞车：`estimate_cost_usd` 用
   `price_table=None` 兼作"未提供价目表"的哨兵，而 `None` 恰是 `json.loads` 的合法返回——
   实测显式传 `price_table=None` 时函数**回头重读盘上的真表**并给出 `0.0015`，坏输入被哨兵吞掉；
   真实路径（价目文件本身是 `null`）则由 `:285` 的 `None.get` 崩出，两条路径的读数不同形，
   登记为下一轮候选，本册不改。
   **该项已由 AB-12e 轮处置**（`docs/reviews/PRICE_TABLE_SENTINEL_AB12E_2026-10-20.md`）：
   非对象顶层改为空表 + 留痕，`None` 哨兵拆成"省略 / 显式 null / 非对象"三态。本册那句
   `0.0015` 是当时探针用的 usage，AB-12e 同探针在同函数上量到的是固定 usage（5000/1000）下
   的 `0.0027`，两者不是同一笔，勿混引。本册表内 `emse_stats_report.py:452`、
   `analyze_t1_b2_main_batch.py:765`、`run_b8_injection.py:672`、`emse_stats_extensions.py:171`
   四处**仍未处置**，其中前两处（同一文件的读取点与 `cost_effectiveness_block:473` 的
   同形哨兵）已由 AB-12e 一并量到并转登记为 AB-13 候选。
   **另一份人写 JSON 同形状、但后果只在测试收集期**：`injection_benchmark_samples.json` 按同一方法
   实测（`:31` 读取、`:32-35` 以 `data.get(k, [])` 消费）——五种非对象返回一律
   `AttributeError: 'list'/'str'/'int'/'bool'/'NoneType' object has no attribute 'get'`；值域同样未判，
   `{"positive_input": null}` 实测 `TypeError: 'NoneType' object is not iterable`，属 §5 登记的
   "值域仍未测"边界实例。崩溃发生在测试收集期，是响亮失败，按本轮判据**不改**。
2. **`.jsonl` 后缀不等于逐行 JSON**：`~/.cache/aitester/ult_repo/datasets/` 下的
   `ULT.jsonl` 与 `ULT_Lite.jsonl` 实测首字符都是 `[`（是 JSON 数组），
   与 AB-8 §10 里 `dataset_ult._iter_records` 的"首行以 `[` 起始走整文件数组分支"
   互相印证。任何按后缀名假设"逐行 dict"的代码都在这份数据上走另一条路径。

## 5. 验证层级与不得引用项

- **我亲自复核过的**：`target_quality_replay.py`（本轮改动 + 14 例锁 + 6 处变异 + 入库工件
  逐字节复现）、`experiments/results/main_batch` 的 10 份批次跳过计数、
  `pass_matched_sensitivity` 确为复现入口（`Makefile:149`、`scripts/reproduce_zero_llm.py:80`、
  并被 CI 门 `scripts/gates/check_artifact_doc_consistency.py:260` 直接 import）、
  ULT 两个 `.jsonl` 文件的首字符、§4 表里价目表 5 处读取/消费形状（`emse_stats_report.py:452`
  与 `spec_examples_generator.py:277` 直接调函数实测；其余三处按消费者表达式逐形状实测；
  `estimate_cost_usd` 另用桩替换 `load_price_table` 复现真实路径）、
  `injection_benchmark_samples.json` 的 5 组形状 + 1 组值域实测、
  `emse_docstring_augment_analysis.py:104-108` 的吞异常写法（读码）。
- **§4 探测自身被否证两次**（同 AB-8 §10 的"验证工具也要能失败"）：其一，改
  `gen._PRICE_TABLE_PATH` **不生效**——`load_price_table(path=_PRICE_TABLE_PATH)` 的默认值在
  定义时绑定，七种输入全部读到真表并给出 `0.0015`，那一轮探测什么都没测到；桩替换
  `load_price_table` 后才拿到真实读数。其二，初稿"`[]` 在两处带 `except` 的读取点都降级为空表"
  被直接调函数的探测否证（见下条）。
- **本册内一处被实测否证的自我捕获**：§4 初稿写的是"`[]` 在 `emse_stats_report.py:452` 与
  `spec_examples_generator.py:277` 两处都降级为空表"，探测给出相反读数——前者的 `.get("models")`
  虽在 try 内、但 `except (OSError, ValueError)` 不接 `AttributeError`，五种形状一律崩；
  后者把五种形状**原样返回**，崩在调用方。两处 `except` 降级的只有语法错误。
  这与 AB-8 §10 的教训同形：按代码形状推断执行路径不等于路径真的被走到，推断必须在写完后实测一次。
- **未逐处复核的**：§2 表里除上述之外的站点判定由两个只读子代理的逐站点读数得出，
  我抽查了其中 5 处。**因此不得据本册引用"experiments/ 层的坏输入容错已完备"**，
  可引用的口径只有："68 处已逐处读数分类，12 处静默点已列名，其中 1 处已改为计数披露
  并带 14 例变异验证锁，其余 11 处按机制登记"。
  **（AB-10 后续：登记里又处置了 2 处，剩 3 处；引用本册该句时应带此后缀。）**
  **（AB-11 后续：剩下的 3 处已全部处置，但两行的原文各列了多件机制，收口复核后计数须再改一次——
  `analyze_t1_b2_main_batch.py` 那行原文列三件机制，AB-11 **0 件处置**（`(x or {})` 降空对象、
  `GATES.json` 缺席报 `FAIL`、宽 `except Exception: continue` 静默摘掉一对种子）；AB-11 改的
  profile 预设是同一文件里的另一站点、该行原文从未列过，原记作"本行部分处置"系归因错位，已就地撤销。
  `mast_trace_analysis.py` 那行原文所指的"非对象行仍计入分母"同样仍登记。四处 AB-11 收口后实测均 0 实例。
  引用"AB-9 那三行已收口"必须带上这句。）**
- **值域仍未测**：与 AB-8 边界 ① 同形——本册只谈"顶层是不是对象"，
  没有谈字段值域（例如 `details` 里某个键放 `null`）。
  **（AB-11 后续：本册 §2 的 `emse_docstring_augment_analysis.py` 一行已被 AB-11 按**值域**重做——
  同一字段的"值为 `null`"与"键缺席"与"读不动"分成三桶；其余 67 处调用点的字段值域仍未普查。）**
- **本轮不改 42 处响亮崩溃点**（另有 9 处已 fail-closed、5 处崩溃被吞但留痕，同样不改），
  这是判据选择而不是遗漏清单；若下一轮要把"崩溃"换成
  "披露后继续"，必须先论证**继续产出的数字是否仍然可信**，否则等于把 AB-8 的
  "静默零生效"从产品侧搬到分析侧。

## 6. 复算命令

```
make target-quality
.venv/bin/python -m pytest tests/test_experiments_json_domain_ab9.py -q --no-cov
.venv/bin/python - <<'PY'   # 普查面复算（应为 95 文件 / 42 含调用 / 68 处）
from pathlib import Path
fs = sorted(Path("experiments").glob("*.py"))
c = sum(ln.count("json.loads(") for f in fs for ln in f.read_text(encoding="utf-8", errors="replace").splitlines())
print(len(fs), sum(1 for f in fs if "json.loads(" in f.read_text(encoding="utf-8", errors="replace")), c)
PY
.venv/bin/python /tmp/ab9_mutate.py        # 变异验证脚本（临时件，不入库）
```

关联登记：`docs/PROJECT_STATUS_REGISTER.md` §3.2 AB-9 行与 §4 AB-9 行（边界与不得引用项）、
`CHANGELOG.md` / `CHANGELOG.en.md` 同名节、`BASELINE.yaml` `tests` 节。
判据出处：`docs/MEASUREMENT_INTEGRITY.md` §10（按返回域枚举）与 §9（校验器口径不等于消费者口径）。
