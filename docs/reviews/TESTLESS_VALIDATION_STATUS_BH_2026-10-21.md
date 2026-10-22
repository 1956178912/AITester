# BH 轮：testless 验证四层的「不可测量 → 验证通过」收口（2026-10-21，零 LLM）

**范围**：`src/tools/testless_validation.py` 的四层（AST 符号守卫 /
mypy 静态检查 / 命名契约回归 / 导入冒烟）与 `src/graph/nodes.py` 的
`_maybe_run_testless_validation` 消费点。这是 F03 缺陷族的又一形态：
BG 收口的是**外部检查器的空 findings**，BH 收口的是**校验层的
`passed=True`**——四层把"这层根本没测成"与"这层测完且零缺陷"折成同一个
布尔值，顶层 `passed` 只在 `not passed` 时才记 `failed_layers`，docstring
与图节点消费点都按"验证通过"读它。

**结论**：每层返回 `{passed, status, reason, detail}`，status 四值
`ok / disabled / unavailable / error`（词表与 BG 逐字一致）；顶层新增
`validation_status`（**最差层胜出**：error > unavailable > disabled > ok）
与 `degraded_layers`，`status != ok` 时发 warning 点名
`层=status:reason`。**只把未披露的假干净翻成 fail-closed**，已披露的降级
路径 `passed` 一律不动。**根因是实测出来的**：mypy 层长期传
`--silent-imports`（mypy 1.15.0 已无此旗标），该层对**任何**输入都返回
逐字节相同的结果、从未完成过一次真实类型检查。**52 例新锁 + 1 条旧断言
按新口径改写 + 变异 11 锚点全红（7/4/1/5/2/1/8/2/1/1/1）+ 中性对照 0
红**；真语料 `TESTLESS_VALIDATION_ENABLE` 在 **100** 份归档 JSON 的
**107** 处取值全为 `null` ⇒ 历史读数零影响、零回填。**未提交**（随收口
提交一并入库）。

---

## 1. 缺陷：四条层各自的假干净路径（改前实测）

改前读数取自 `git show HEAD:src/tools/testless_validation.py` 的直接调用
（Python 3.14.6 / mypy 1.15.0，非推断）：

| 层 / 输入 | 改前返回 | 问题 |
|---|---|---|
| mypy / 干净补丁 | `passed=False`，detail `mypy 发现 1 处问题：mypy: error: unrecognized arguments: --silent-imports` | 把**工具链用法错误**记成**代码疑点** |
| mypy / 类型错误代码 | 与上一行**逐字节相同** | 三种输入一个结论，层无判别力 |
| mypy / 语法错误代码 | 与上两行**逐字节相同** | 同上 |
| AST 守卫 / 原文不可解析（`def f(:`） | `passed=True`，"AST 符号守卫通过（新增 1 个模块级定义，不影响守卫）" | 原符号集为空 ⇒ 差集恒空，**从未做过比较**却报"守卫通过" |
| AST 守卫 / 补丁不可解析 | `passed=False`，"补丁删除了原代码的模块级定义 `['f']`" | 把**解析失败**归因成**删符号** |
| 命名契约 / 原文不可解析 | `passed=True`，"命名契约回归通过（无被删模块级符号）" | `check_naming_contract` 的 `(True, [])` 是三件事共用返回值（比较过且无删除 / 无法解析所以没得比 / `PATCH_CONTRACT_CHECK=false` 恒放行），文本是**假陈述** |
| 导入冒烟 / 危险 API 预检命中拒跑 | `passed=False`（无状态区分） | 拒跑是策略不是测量，下游无法区分"跑过且失败" |
| 导入冒烟 / 解释器起不来（`OSError`） | `passed=True` + `infra_degraded` | 已披露，但布尔值仍是"通过" |

mypy 返回码语义另有一条独立的假干净：旧代码
`passed = len(error_lines) == 0`，于是 `rc=2`（mypy 致命错误 / 读不到目标
文件）且输出不含 `error:` / `note:` 行时返回 `passed=True`、detail
"mypy 发现 0 处问题"。

## 2. 处置：分层状态 + 最差者优先 + 消费点披露

### 2.1 状态语义（词表同 BG，聚合方向相反）

| status | 含义 | `passed=True` 可否作"验证通过"的证据 |
|---|---|---|
| `ok` | 本层确实执行完成且报告可信 | **可以** |
| `disabled` | 按设计未检查（层开关关 / `PATCH_CONTRACT_CHECK=false` / 危险 API 拒跑） | 不可以（未检查） |
| `unavailable` | 依赖或解释器缺席，预期降级 | 不可以 |
| `error` | 跑了但没产出可信报告（超时 / 崩溃 / rc 异常 / 输入不可解析） | **不可以**（不可测量） |

聚合取**最差层胜出**（error > unavailable > disabled > ok），未知或缺失
status 也按 `error` 处理。这与 BG 的"任一 ok ⇒ ok"**方向相反**，因为
`type_repair` 的两个后端是同一检查的可替换实现，而本模块四层是彼此独立
的校验层——任一层不可测量，整体验证就不完整。判据：**先问"这几层分别
执行了吗"，再问"它们报缺陷了吗"**；聚合方向由"层之间是什么关系"决定，
不能照抄上一轮的写法。

### 2.2 逐点判定

| 层 / 路径 | status | reason | `passed` |
|---|---|---|---|
| AST 守卫 / 原文或补丁不可解析 | `error` | `unparseable_original` / `unparseable_patched` | False（fail-closed） |
| AST 守卫 / 正常比较 | `ok` | — | 按差集 |
| mypy / 层开关关 | `disabled` | `mypy_layer_disabled` | True（口径不变） |
| mypy / 未安装 | `unavailable` | `mypy_not_installed` | True（口径不变） |
| mypy / rc=0 | `ok` | — | True |
| mypy / rc=1 且有疑点行 | `ok` | — | False |
| mypy / rc=1 但解析不出疑点行 | `error` | `mypy_rc1_no_findings` | False |
| mypy / rc∉{0,1}（2 致命、3 内部错误、负数信号、`None`） | `error` | `mypy_rc_<n>` | False |
| mypy / 超时或 `OSError` | `error` | `mypy_timeout` / `mypy_exception` | **True（保持已披露降级）** |
| 命名契约 / 输入不可解析 | `error` | `unparseable_*` | False |
| 命名契约 / `PATCH_CONTRACT_CHECK=false` | `disabled` | `patch_contract_check_disabled` | True |
| 命名契约 / 层开关关 | `disabled` | `naming_contract_layer_disabled` | True |
| 导入冒烟 / 危险 API 预检命中 | `disabled` | `refused_dangerous_api` | False |
| 导入冒烟 / 超时 | `error` | `import_smoke_timeout` | False |
| 导入冒烟 / 解释器起不来 | `unavailable` | `import_smoke_exception` | **True（口径不变）** |
| 导入冒烟 / 正常跑完 | `ok` | — | 按 rc |

### 2.3 行为差异

- **argv 根因修复**：`--silent-imports` → `--follow-imports=silent`，并以
  两条 argv 断言锁住"不得再出现旧拼写"、"目标解释器与临时文件正确"，另加
  真 mypy 端到端 3 例（干净 / 类型错误 / 语法错误三者结果互不相同）。
- **只翻未披露的假干净**：mypy `rc ∉ {0,1}`、`rc==1` 空报告、AST 与命名
  契约输入不可解析 ⇒ `error` + fail-closed；开关关 / 未安装 / 超时 /
  `OSError` 仍 `passed=True`（其中超时与 `OSError` 的 `status` 记 `error`
  但 `passed` 不动，保持 ADR-0003 的默认关不阻断口径）。
- **消费点显式披露**：`nodes.py` 在 `passed=True` 而
  `validation_status != "ok"` 时记一条
  "不构成'验证通过'的证据（不阻断主流程）"，此前该分支不存在——只有
  `failed_layers` 非空才有日志。
- **本轮无状态键连带改动**：`testless_validation` 键早已在
  `src/graph/state.py` 声明，故不触发 TypedDict / `debug()` 键集合契约 /
  prompt card 三条既有门（BG 轮踩过）。

## 3. 真语料测量（本轮重测，非沿用笔记）

- `TESTLESS_VALIDATION_ENABLE`：`*.json` 归档 **100** 份命中、共 **107** 处
  取值**全为 `null`**；另有 17 份 `.log` 也提到该键（全口径 128 处，同样
  全 `null`）⇒ 登记口径按 JSON 计。
- `testless_validation` 载荷键：只在 **2** 份归档出现，且**均为 `null`**。
- `failed_layers` / `infra_degraded` / `validation_status` /
  `degraded_layers` 在 **1702** 份归档 JSON 中出现 **0** 次。
- `.mypy_cache/` 的 5 份匹配是工具缓存不是工件，已排除。

⇒ 该层默认关、历史读数零影响、零回填。本轮新增的是**未启用时的可区分
状态**，不是重算历史数字。

## 4. 回归锁

`tests/test_bh_testless_validation_status.py`（**52 例**，含参数化展开）：

- `TestMypyRcClassification`（10）：rc0/rc1/rc1 空报告/rc2/rc3/负 rc/`None`
  的 status 与 passed 双向上锁；
- `TestMypyInvocationFlags`（2）：**argv 根因锁**——现代拼写在、旧拼写不
  在、解释器与临时文件正确；
- `TestMypyRealRun`（3）：真 mypy 端到端，干净 ⇒ `ok`+passed、类型错误 ⇒
  `ok`+failed、语法错误 ⇒ `error`，且三者互不相同；
- `TestMypyDegradedPaths`（5）：层开关 / 未安装 / 超时 / `OSError` /
  `timed_out` 标志归因（已披露路径 `passed` 不变）；
- `TestAstSymbolGuardStatus`（5）、`TestNamingContractStatus`（5）、
  `TestImportSmokeStatus`（6）：逐层不可测量 / 拒跑 / 起不来的 status；
- `TestWorstLayerStatus`（8）：优先级、顺序无关、缺 status 与空层集 ⇒
  `error`；
- `TestRollUpStatus`（6）：**核心假干净锁**——四层全 `passed=True` 但含
  `error` 层时整体 `validation_status="error"` + `degraded_layers` +
  warning 点名；四层全关 ⇒ `disabled` 而非 `ok`；每层都带 status；
  `failed_layers` / `infra_degraded` 等历史键不变；
- `TestConsumerDisclosure`（2）：`nodes.py` 消费点在降级时记录"不构成
  验证通过的证据"、全可测量时不记录。

按新口径改写既有一处：
`tests/test_testless_validation.py::TestAstSymbolGuard::test_syntax_error_degrades`
原断言 `passed is True`，锁的正是本轮收口的假干净；改为断言 `status ==
"error"` 且 `passed is False`（用例数不变，该文件仍 21 例）。

## 5. 变异验证

`scripts/tools/bh_mutation_verify.py`：11 锚点 + 1 中性对照。纪律同 BG：
干净副本先全绿（collected **73**）、逐锚点 `compile()` + collected 数
核对、跑完按 sha256 原字节还原（不用 git checkout / stash，工作区有数百
未提交文件）。

| 锚点 | 红数 | 被谁抓住（节选） |
|---|---:|---|
| M1 不可信 rc 恢复"疑点行为空即通过"且自称 ok | 7 | `test_unreadable_target_file_is_error`、`test_usage_error_is_not_attributed_to_code` 等 |
| M2 argv 换回 `--silent-imports` | 4 | `TestMypyRealRun` 端到端 + argv 锁 |
| M3 rc=1 空报告被接受 | 1 | `test_rc1_without_findings_is_error` |
| M4 AST 不可解析当作可比较 | 5 | `test_unparseable_patch_makes_overall_error`、改写后的 `test_syntax_error_degrades` |
| M5 命名契约不可解析当作通过 | 2 | `test_unparseable_original_is_error_not_passed`、整体聚合 |
| M6 `PATCH_CONTRACT_CHECK` 恒放行不披露 | 1 | `test_contract_check_switch_off_is_disabled` |
| M7 聚合改成"ok 优先"（BG 方向） | 8 | 聚合器 6 例 + 顶层披露 |
| M8 未知 / 缺失 status 默认 ok | 2 | `test_missing_status_is_error`、`test_empty_layers_is_error` |
| M9 降级不发 warning | 1 | `test_passed_true_with_unmeasurable_layers_is_disclosed` |
| M10 危险 API 拒跑记成 ok | 1 | `test_dangerous_api_refusal_is_disabled_not_ok` |
| M11 解释器起不来记成 ok | 1 | `test_os_error_is_unavailable` |
| M12 中性对照（仅删注释一个"早"字） | 0 | 必须存活 |

复跑结果与登记逐字一致（11 锚点 7/4/1/5/2/1/8/2/1/1/1、控制 0 红、
collected 全程 73、sha256 还原断言通过）。

## 6. 踩坑与自纠

- **根因不在判据里，在 argv 里**：本轮最容易漏掉的是"四层里有一层从未
  真正工作过"。如果只给 `passed` 补 `status`，mypy 层会继续以 `error`
  状态**永远不可测量**，锁仍然是绿的。判据：**给"不可测量"上锁之前，先
  确认它不是自己的调用姿势错了**——把模块按 HEAD 版本直接调一遍，三种
  输入逐字节相同就是信号。
- **同一词表不等于同一聚合**：BG 与 BH 共用 `ok / disabled / unavailable
  / error`，但聚合方向相反（可替换后端 vs 独立校验层）。照抄上一轮的
  聚合器会造出新的假干净。判据：**先写清"这些结果之间是什么关系"，再决
  定谁胜出**。
- **`passed` 与 `status` 分轴，已披露路径不动**：mypy 超时 / `OSError`
  的 `passed=True` 是 ADR-0003 的既有口径，本轮只把 `status` 记为
  `error`，不改布尔值；改了就等于把"崩溃翻成失败"再犯一次"崩溃翻成
  干净"的反向错误。判据：**处置只把沉默翻成披露或 fail-closed，不把一
  个已披露的降级翻成另一个方向的读数**。
- **勘误（当场纠正）**：`branch_total_pct` 落笔前曾按工作笔记写 **94.89**
  〔7081/7462〕，复算 `coverage.xml` root 属性得
  `branches-covered=7027` ⇒ 真值 **94.1705%**；笔记里的 7081 在工件中不存
  在。错误发生在转录环节而非测量环节，已按工件改写并在 BASELINE 该行注
  登记。判据：**转录的每个数字都要回到工件复算，不能从笔记继承**。
- **改写既有断言要留痕**：`test_syntax_error_degrades` 原来是本轮要收口
  的假干净的"守卫"，若只是删除或静默改绿，读者会以为口径从未变过；改后
  在用例数与登记里都写明"原断言锁的是假干净"。

## 7. 边界（不得引用为"testless 验证已整体可信"）

- 本轮只动 `testless_validation.py` 四层与 `nodes.py` 消费点；
  `src/tools/patch_applier.check_naming_contract` 的
  `(True, [])` 三义返回**未改**（对外契约），区分发生在 testless 侧前置
  判别。
- `validation_status` / `degraded_layers` 是**观测与披露，不是阻断策略**：
  图节点仍不阻断主流程（ADR-0003 默认关）。下游若要据此决策，必须显式
  读两键，不能继续只看 `passed`。
- 导入冒烟的"危险 API 拒跑"记 `disabled`：拒跑保护了执行环境，但也意味着
  该补丁的运行时行为**没有任何证据**，不得读成"import 安全"。
- mypy 层用 `--follow-imports=silent` + `--ignore-missing-imports`，只对被
  写进临时文件的补丁片段负责，不外推为"整个模块类型正确"。
- 四层都是**无测试场景**的静态/冒烟探针：它们既不能证明补丁修好了缺陷，
  也不能替代 pytest 判据；`validation_status="ok"` 只说明"四层各自跑成了
  且没报缺陷"。

## 8. 复算命令

```bash
.venv/bin/python -m pytest tests/test_bh_testless_validation_status.py \
  tests/test_testless_validation.py -q
.venv/bin/python scripts/tools/bh_mutation_verify.py
.venv/bin/python -m pytest tests/test_detection_gates_matrix.py \
  tests/test_untrusted_exec_env.py -q
grep -rho --include='*.json' '"TESTLESS_VALIDATION_ENABLE": [^,}]*' experiments/results | sort | uniq -c
git show HEAD:src/tools/testless_validation.py > /tmp/bh_old_tv.py
```

最后一条把改前版本取出，供逐层直接调用复现 §1 的三行同结果。

## 9. 收口批注（2026-10-21）

- 登记前（含 `--cov`）一跑：**11503 passed / 1 failed / 5 skipped、
  218.93s**（collected **11509**；唯一失败 = 基线守卫，登记前仍写
  11452，实收 − 声明 = 57 > 6 容差）。覆盖率
  **19151/19678 行 = 97.3219%**、**7027/7462 弧 = 94.1705%**；未覆盖
  **527**（+1）、缺弧 **435**（−1）均落在既有 ±2 行抖动域，不作回收或
  退化主张。十项核心模块登记值 0 变动，唯一分母变动是 graph_nodes
  824/825 → **826/827**（branch 99.04% → **99.05%**，两位小数仍
  99.88）；`src/tools/testless_validation.py` 本轮 **160/162 行 =
  98.77%、弧 44/44 = 100%**（三项核心路由逐位不变）。
- 确认跑（无 `--cov`，单独执行、不与其他命令重叠）：**11504 passed /
  5 skipped / 0 failed、212.17s、rc=0**（collected **11509** = 11504 +
  5 + 0，与登记前同一采集面；21 warnings）。该跑跨过零点完成，读数仍按
  BH 登记日 2026-10-21 记录。
- 门禁实测（单独跑 `make gates`，不与其他 pytest / 文档编辑重叠）：
  **rc=0**、墙钟 **263s**；链内 pytest（`-n 4 --dist loadfile`，**不带
  `--cov`**，与带覆盖率读数不可互换）**11504 passed / 5 skipped /
  0 failed、213.22s**（34 warnings；collected 11509 = 11504 + 5 + 0，
  与确认跑同一采集面）；`ruff check .` 全过、`ruff format --check .`
  **956 份已格式化**（BG 轮 953 → +3 = BH 手册 / 新锁 / 变异脚本）、
  mypy **136 源文件零问题**；双语文档 0 警告 / 0 失败；文档链接 strict
  **176 份文件 / 814 条链接 / 0 错误 / 0 警告**；env-budget **253/253**
  全部登记；`check_baseline` 结构校验与数字漂移检查均通过；状态通道
  **135 文件**无未声明键；env-snapshot **84 开关 / 115 键 / 缺失 0**；
  model-fingerprint（近期无新批次）通过；工具版本一致；JSON 契约 **7/7**
  调用点一致；严格 JSON **7274 份工件**（7272 严格 + 2 历史豁免 + 0
  违规）、**304 份**源码写入点 0 违规；报告→工件对账 [OK]（不一致 0；
  T-10 严格 29 行 / 25 可测、宽松 62 / 55；登记册 §1 覆盖率对账相符）；
  零断言 **452 份测试文件 / 0 违规**。
- 回填门禁读数后验证跑（再次单独 `make gates`，不与其他 pytest / 文档编辑重叠）：
  **rc=0**、墙钟 **219s**、链内 **11504 passed / 5 skipped / 0 failed、213.47s**
  （28 warnings；collected 11509）；其余门禁读数与首跑逐项一致（956 份已格式化、mypy
  136 源文件、176 份文件 / 814 条链接 / 0 错误、253/253、135 文件、84/84、7/7、7274
  工件 0 违规、对账 [OK]、452 测试文件 0 违规）。两次墙钟与 warnings 数差仅作抖动，
  不作性能主张；回填的读数本身在两跑中均被同一门禁复验。
- 双语头行与 CHANGELOG 门禁句回填后再单独跑一次 `make gates`（全部登记文本落定，
  工作区不再含未复验改动）：**rc=0**、墙钟 **218s**、链内 **11504 passed /
  5 skipped / 0 failed、213.01s**（123 warnings；collected 11509）；其余门禁读数
  与前两跑逐项一致（956 份已格式化、mypy 136 源文件、双语文档 0 警告 / 0 失败、
  文档链接 176 份 / 814 条 / 0 错误、env-budget 253/253、状态通道 135、
  env-snapshot 84 缺失 0、JSON 契约 7/7、7274 工件 0 违规、对账 [OK]、452 测试
  文件 0 违规）。三跑的墙钟与 warnings 计数差仅作抖动，不作性能主张。
- 本轮改动全部未提交，未推送（工作区随收口提交一并入库）。
