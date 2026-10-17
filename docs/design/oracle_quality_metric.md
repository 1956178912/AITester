# 确定性规约 oracle 质量度量（A-05）：设计、口径与已知限制

> 状态：M 轮 T7-A（2026-10-17）零 LLM 重放工具的设计文档（本地件）；
> N-3（2026-10-17）更新：接线修复 + 独立判读已落地，质量控制口径见 §10。
> 对应独立评审 §10 A-05 / G6 / D-4："spec_oracle 注入率 40%，正确率未度量"。
> 工具：`experiments/oracle_quality_replay.py`；工件：
> `experiments/results/emse_oracle_quality_20261017/`；单测：
> `tests/test_oracle_quality_replay.py`。
> **描述性度量**：不是预注册确认性证据、不做显著性推断；
> **oracle 质量反映确定性规约通道，不是 LLM 生成能力指标**，也不与
> Tratto/TOGLL 等外部工作数字横向对比（数据集/口径/语言不同）。

## 1. 动机：为什么需要它

逻辑驱动通道（`SPEC_ORACLE_EXEC_ENABLE` / PROFILE=logic）会把
`src/specs/spec_ir_v2.compile_spec_oracle` 编译出的**确定性 oracle** 追加到
LLM 生成测试尾部并列执行（生产注入口
`src/graph/nodes.py::_append_spec_oracle_to_test_with_verdict`；注入测试名固定
`test_specir_v2_oracle` / `test_specir_v2_smt_witness`）。

此前项目只对注入做**存在性**记账：

- `spec_oracle_injected`（True/False/None 三态）与 `spec_oracle_verdict`
  （`not_attempted` / `compiled_empty` / `injected` / 执行后升级两态）；

但从未度量 oracle **本身**的行为质量。缺口有两个方向：

1. **假阳**：oracle 在正确实现（gold fixed）上失败 → 它会把"逻辑驱动"的
   确定性通道变成检出损伤源（过红 / 误杀正确修复）；
2. **无信号**：oracle 在缺陷版与修复版上都通过 → 它对该缺陷没有贡献。

A-05 的验收要求是"oracle_correct / oracle_fp / oracle_silent 三指标 +
注入任务检出贡献"；本工具落地为**四分类**（增加 misguided：把缺陷行为
断言为期望），以与 T2 的 misguided/effective 逐测试度量口径对齐。

## 2. 定义与公式

### 2.1 逐 oracle 测试四分类（互斥、覆盖全部可分类 oracle 测试）

对每个任务的**增强重放**（归档 LLM 测试 + 生产注入函数追加的 oracle）在
buggy / fixed 两侧各跑一次 pytest（`--junitxml` 逐测试结果），只取 oracle
测试节点（测试名含生产注入名），按两侧 pass/fail 分类：

| 类别 | 条件 | 语义 |
|---|---|---|
| `oracle_correct` | buggy=FAIL ∧ fixed=PASS | 真检出：oracle 区分了缺陷版与修复版 |
| `oracle_misguided` | buggy=PASS ∧ fixed=FAIL | 把缺陷行为断言成期望行为（编译器产物自身误导） |
| `oracle_silent` | buggy=PASS ∧ fixed=PASS | 两侧都过 → 对该缺陷零信号 |
| `oracle_fp` | 其余可分类（含 buggy=FAIL ∧ fixed=FAIL） | fixed 失败 = 对正确实现的假阳（恒红型 oracle） |

形式化（n 可分类 oracle 测试）：

    oracle_correct_share  = |correct|  / n
    oracle_fp_share       = |fp|       / n
    oracle_silent_share   = |silent|   / n
    oracle_misguided_share= |misguided|/ n

**分母 = 可分类 oracle 测试数**（两侧均有 pass/fail 结果）。以下原因
**单列、绝不并入四分类分母**（与 T2 `misguided_metrics` 的不可分类原因
同源，直接复用其分类器）：

- `timeout`（per-test/整文件）、`collect_error`、`import_error`、
  `syntax_error`、`skipped`、`test_error`（setup/teardown）、
  `missing_side`（某侧无该 node）、`unknown`。

### 2.2 注入率 / 编译产物非空率

- `n_attempted`：生产注入函数 verdict ≠ `not_attempted` 的任务数
  （有规约材料 + 函数名 + 模块名）；
- `n_injected`：verdict == `injected`（编译产物非空、注入成功）；
- `injection_rate_of_rows = n_injected / 任务行数`；
- `compiled_nonempty_rate_of_attempted = n_injected / n_attempted`
  （"编译产物非空率"：尝试编译中产物非空的占比）；
- `oracle_tests_per_measurable_task`：可测任务上收集到的 oracle 测试数分布。

### 2.3 注入任务检出贡献（任务级，M1 detection 口径）

任务级 detection 二值（与 `experiments/_m1_metrics.py` 的 M1 口径同源，
沿用 T2 工具实现）：buggy 侧 pytest 非零退出 ∧ fixed 侧为 0 ∧ 两侧无执行错误；
超时/材料不可用 → None（不可判）。

三口径对比（同任务配对）：

    archived_detection          = 归档行 detection_rate（LLM-only；批次未注入）
    llm_only_detection          = LLM-only 重放 detection（与归档交叉校验）
    oracle_augmented_detection  = 增强重放 detection（LLM 测试 + oracle 同文件）

    Δ_contribution = oracle_augmented_detection − llm_only_detection
    转移类别：added (0→1) / lost (1→0) / preserved (1→1) / none (0→0) /
              undecidable（任一 None）

- **added** 归因为 oracle 在 buggy 侧失败且 fixed 通过（correct），或
  全局状态扰动（逐任务披露 oracle 四分类）；
- **lost** 归因为 oracle 在 fixed 侧失败（fp/misguided）把正确实现判红；
  报告逐条给出 fixed 侧失败类型（`failure_stats.fixed_side_exception_types`）。

## 3. 注入 fidelity：state 如何重建（关键口径）

归档批次（`emse_df_spec_20261016/` 两臂）的臂为 `plain_llm_df*`
（**Planner 关闭**），故该批生产注入口一律 `not_attempted`
（归档 `spec_oracle_verdict=not_attempted` 50/50，已交叉校验）。

本工具做**反事实重放**：对每个任务用锚表材料重建生产注入口的 state，
**原样调用生产函数**注入 oracle（不重写注入/编译逻辑）：

| state 键 | 重建来源 |
|---|---|
| `target_code` | QuixBugs 缺陷版源码（`~/.cache/aitester/quixbugs/python_programs/` 优先，data/env 回退） |
| `module_name` | `task_id` 末段（`-`→`_`，截 50 字符；与 `run_benchmark` 同口径） |
| `target_function` | 归档 `task_metadata.suggested_function`（生产缺席语义：空则不写键） |
| `test_plan` | `{function_name, logic_analysis}` ← 锚表条目（内容寻址命中） |
| `spec_ir` | **不写**（复现生产注入函数的"现场解析 `test_plan.logic_analysis`"降级路径） |

**锚表强制 sha256 校验**：`SPEC_ANCHOR_TABLE.json` 加载时与同目录
`SHA256SUMS` 条目逐位比对（不一致 / 无条目 / 文件缺失均 fail-closed；
不允许无校验加载）。内容寻址键 = `sha256(target_code.strip())`（与
`run_benchmark._lookup_spec_anchor` 同口径）——命中即证明重建的缺陷版
源码与该锚材料同源。QuixBugs 50/50 命中（锚覆盖 100%）。

## 4. 交叉校验（0 mismatch 要求）

报告必须给出、且默认要求 0 mismatch：

1. **LLM-only 重放 detection vs 归档 `detection_rate`**：
   - `match`（两侧均可判且相等）/ `both_none`（都不可判）为正常；
   - `mismatch`（两侧均可判但不同）= 不允许；`artifact_none` /
     `replay_none`（单侧不可判）单列并逐条归因（超时口径/环境差异/
     跨批次随机性）。
2. **归档 `spec_oracle_verdict` 的语义复现**：用"归档 state"（无 test_plan，
   Planner 关闭）重建 state 调生产注入口，重放 verdict 必须与归档逐行一致
   （归档批次应全部 `not_attempted`）。
3. **归档字段自洽性**：`spec_oracle_injected` 三态与 `spec_oracle_verdict`
   取值域是否一致（如 verdict=injected 但 injected=None 即字段矛盾）。

任一 mismatch > 0：`cross_check.all_ok=false`，差异逐条归因写入报告；
`--fail-on-mismatch` 时退出码 3（gate 用）。

## 5. 确定性

- 报告 body 不含时间戳/墙钟（只进 `run_meta`），body digest =
  规范化 JSON 的 sha256；`--repeat ≥2` 比较各次 digest 并如实披露差异路径。
- 注入口/编译器/四分类均为确定性路径；pytest 子进程环境经
  `nested_pytest_env` 剔除宿主 `PYTEST_PLUGINS`/`PYTEST_ADDOPTS`，
  固定 `PYTHONHASHSEED=0`。

## 6. 本轮实测摘要（M 轮 T7-A，2026-10-17，**描述性**）

> 工件：`experiments/results/emse_oracle_quality_20261017/`
> （`ORACLE_QUALITY_REPORT.json/.md` + `README.md`）；body digest
> `ce10e33bc54b56c00c26cd5fd5f7f741649a52554e579d0f154f4a46fd372376`；
> 重放墙钟 **390.3s**（`--jobs 4 --per-test-timeout 1 --file-timeout 240
> --repeat 1`，nice 15，与 M-4 真 LLM 跑批窗口并行）。
> 输入 sha256：df_spec 臂 `813c437f…` / df 对照 `536da803…`；锚表
> `3e90b2ad…`（SHA256SUMS 校验通过）；锚 416 条、QuixBugs 命中 50/50。

**注入统计（两臂相同，oracle 材料与臂无关）**：任务行 50；锚命中 50；
尝试注入 49（`node` 无规约材料 → not_attempted）；注入成功（编译产物非空）
**38（76%）**；`compiled_empty` 11（9 个 `*_test` 驱动任务 + 2 个缺陷程序）。

**oracle 四分类（分母 = 38 个可分类 oracle 测试；每注入任务 1 条）**：

| 类别 | 计数 | 占比 |
|---|---|---|
| `correct` | 0 | 0.00% |
| `fp` | **29** | **76.32%** |
| `silent` | 9 | 23.68% |
| `misguided` | 0 | 0.00% |

fixed 侧失败类型：异常 27（TypeError 24 / AttributeError 2 /
ZeroDivisionError 1）、断言失败 2 ——即假阳绝大多数是 oracle 自身在正确
实现上**崩溃**（绑定字面量 `a, b = 0, 0` 与 list/dict 参数不匹配的典型
`TypeError`），而非"断言了错误行为"。

**注入任务检出贡献（40 缺陷程序口径，任务级二值）**：

| 指标 | df_spec（处理） | df（对照） |
|---|---|---|
| 归档 detection（LLM-only，批次未注入） | 19/35 = 54.29% | 28/36 = 77.78% |
| LLM-only 重放 detection | 20/40 = 50.00% | 31/40 = 77.50% |
| oracle-augmented 重放 detection | **4/38 = 10.53%** | **7/38 = 18.42%** |
| Δ augmented − llm_only（配对） | **−36.84pp** | **−57.89pp** |
| 转移（lost / none / preserved / added） | 14 / 20 / 4 / 0 | 22 / 9 / 7 / 0 |

即：在该"仅锚表材料"反事实口径下，附加的确定性 oracle 没有带来任何
新增检出，反而因 fixed 侧假阳破坏了 14（df_spec）/22（df）个原本由 LLM
测试检出的任务——**oracle 质量是该通道自身的主要风险**，不是 LLM 测试的
问题。两臂 oracle 四分类数字完全相同（oracle 文本仅由锚材料/state 决定、
与 LLM 测试无关）；差异只出现在被损伤的 LLM 检出集合上。

**交叉校验（0 mismatch 要求）**：两臂 `all_ok=True`。detection 对账
df_spec：match 35 / artifact_none 6 / both_none 9（mismatch 0）；df：
match 36 / artifact_none 5 / both_none 9（mismatch 0）；归档 verdict
复现 match 50/50；归档字段自洽性违规 0。artifact_none 的 5–6 条
（bitcount / find_first_in_sorted / node / sqrt / to_base / wrap 等）
逐条归因见报告 §6（缺陷实现不终止/辅助模块的历史 None 口径）。

**解释纪律**：① 该数字是"锚表材料直接重建 test_plan（无现场
`spec_ir`/`boundary_triplets`）"的受控反事实，**不应外推为完整 logic
链路生产注入质量**；② 它给出的是该材料条件下的**质量下界**信号——
"把规约锚表材料直接编译成 oracle"目前不可用于提升检出，反而需要先修
编译器的绑定退化（0 字面量）与假阳问题；③ 描述性度量，不做显著性推断。

## 7. 已知限制（必须随数字一起引用）

1. **反事实口径 ≠ 生产全链路**：state 不含 Planner 现场 `spec_ir` 与
   `boundary_triplets`（确定性边界输入），编译产物只能退化为保守字面量绑定
   （如 `a, b = 0, 0`）。当被测函数要求 list/dict/非平凡输入时，oracle 会
   在两侧抛 TypeError 等多归为 `oracle_fp`——这是**该材料条件下的真实
   oracle 质量下界**，不应外推为"完整 logic 链路生产注入质量"。
2. **归档批次未实际注入**：df_spec 批生产注入口为 `not_attempted`
   （Planner 关闭），本报告数字全部来自零 LLM 重放（不会因重放而出现在
   原批次工件里）。
3. 生成测试与 oracle **同文件、同 pytest session** 执行（生产口径）：全局
   状态污染与收集顺序照旧；oracle 在 LLM 测试之后执行。
4. 官方金测试 `test_cases` 不参与 oracle 分类；仅用于任务级 detection 口径。
5. 9 个 QuixBugs `*_test` 驱动任务（相对 import、无金测试）与辅助模块
   `node` 在平铺执行口径下结构性不可 replay（或 oracle 编译为空/未尝试）
   → 结构跳过单列；主分析集取 40 缺陷程序口径（非 `*_test` 且 buggy≠fixed），
   41 口径兼容行另报。
6. per-test timeout（默认 1s，与 T2 工具重放口径一致）把挂死 oracle 测试
   记为不可分类 `timeout`，不并入四分类；与 M1 判分口径有意不同。
7. 描述性对比（df vs df_spec 两臂）不提供显著性推断；两臂差异仅作机制侧
   方向参考。
8. 报告含机器路径（quixbugs 根/工件路径）与 pytest 版本，属工件 provenance；
   body digest 同机可复算、跨机不保证相同。

## 8. 证据分级与引用

- **证据级别**：描述性机制指标（B 级：可复算、工件齐全、分母披露），
  **不是**预注册确认性证据。
- 外部参照（仅背景，不横向比较）：独立评审 §10 A-05 引用 Tratto 73% /
  TOGLL 63% 的 oracle/断言正确率作为"测试预言质量"缺口参照；ISSTA'26
  （Zhao, Zhou & Cohen, DOI 10.1145/3832204）的 misguided/effective 二分
  是本工具四分类的语义来源（经 T2 工具操作化）。本工具不复用其任何数字。

## 9. 复算入口

```bash
# 目标单测（微型 fixture，零 LLM/零网络；<60s）
.venv/bin/python -m pytest tests/test_oracle_quality_replay.py -q

# 真实重放（只读存量工件；生成 ORACLE_QUALITY_REPORT.json/.md + README）
nice -n 15 .venv/bin/python -m experiments.oracle_quality_replay \
    --out experiments/results/emse_oracle_quality_20261017 \
    --jobs 4 --per-test-timeout 1 --file-timeout 240 --repeat 1
```

工件 README 记录输入 sha256（两臂批次 JSON + 锚表 SHA256SUMS 校验）、
复算命令、覆盖/分母、墙钟与限制。

## 10. N-3 更新（2026-10-17）：接线修复 + 独立判读（落地 A-05 两个缺陷）

§6 登记了两条独立缺陷：**仪器未自校验**（76% 假阳）与**判分对象耦合**（oracle
与 LLM 测试同文件混判，oracle 失败抹掉既有检出）。N-3 处置其中的**结构性接线
缺口**与**判分耦合**；"仪器自校验/质量改进"（编译器绑定、假阳治理）**不在本轮
范围**，登记为下一轮任务。

### 10.1 接线修复：`spec_anchor` 成为第三材料源

- **缺陷**：生产 df_spec / doc / union / augment 类臂的 baseline **不跑
  Planner** → state 里没有 `test_plan`；而注入口只读 `spec_ir` /
  `test_plan.logic_analysis` → 这些臂的 `SPEC_ORACLE_EXEC_ENABLE=true` 永远
  返回 `not_attempted`（A-05 重放只能用 test_plan 反事实绕过接线）。
- **修复**：`src/graph/nodes.py::_append_spec_oracle_to_test_with_verdict`
  材料优先级扩展为：
  `spec_ir` → `test_plan.logic_analysis` → `spec_anchor.logic_analysis` →
  `spec_anchor.human_spec`。**人类 docstring 锚不强行编译**（human_spec 是自然
  语言、非 SpecExpr 通道），如实返回可审计 verdict。
- **可审计 verdict 扩展**（既有 5 值逐字不变，state.py 注释同步）：
  `not_attempted_missing_target`（有材料但缺函数名/模块名） /
  `not_attempted_human_spec_only`（仅人类规格锚，不强行编译） /
  `not_attempted_anchor_unparseable`（锚 logic_analysis 在场但解析为空）。
- **零差异**：`SPEC_ORACLE_EXEC_ENABLE=false`（默认）时
  `_spec_oracle_injection_verdict` 在开关守卫处即返回 → 生成测试逐字节不变、
  历史批次 JSON 数字不受影响。

### 10.2 独立判读：LLM-suite / oracle-suite 分开执行

- **`detection_rate` 语义（自本修复起）= LLM-suite**：pytest
  `-k "not test_specir_v2_oracle and not test_specir_v2_smt_witness"` 排除
  oracle 测试后执行 buggy/fixed 两段 F2P 判定；oracle 单独以
  `-k "test_specir_v2_oracle or test_specir_v2_smt_witness"` 运行，输出
  **`oracle_suite_verdict`** ∈ correct / fp / silent / misguided / unavailable
  （超时、收集错误、材料缺失 → unavailable，fail-closed 不臆测）。
- **结果行新增两键**：`llm_suite_detection_rate`（同 detection_rate 值的显式
  口径名）与 `oracle_suite_verdict`；失败分支同键位（None / unavailable）保持
  键集合同构。`M1_PER_TEST_TIMEOUT` 语义不变（超时仍单列）。
- **口径变更纪律（重要）**：变更**只影响未来批次**；默认开关关闭时生成测试
  不含 oracle 测试名 → `-k` 不启用、命令逐位不变、oracle 判定零额外子进程，
  历史工件 JSON 不被改写。对历史批次的引用须标注"detection = 混判旧口径"。
- **耦合修复的直接效果**：在旧混判口径下，df_spec / df 两臂分别有 14 / 22 个
  原本由 LLM 测试检出的任务被 oracle 假阳抹成未检出（§6）；新口径下
  detection_rate 只由 LLM-suite 决定，oracle 失败不再改写它。

### 10.3 零 LLM 重放验证与真 LLM 冒烟（工件在同名结果目录）

工具新增 `experiments/oracle_quality_replay.py --independent-judging`：state
**只带 spec_anchor**（复刻生产臂形态、同时验证接线修复），直接调用生产
`_m1_metrics` 判分链，`M1_PER_TEST_TIMEOUT=1s` 与 M-2 重放口径对齐。工件：
`experiments/results/emse_oracle_independent_judging_20261017/`
（README + JSON + SHA256SUMS + `smoke/` 真 LLM 冒烟）。核心结果：

| 指标 | df_spec（处理） | df（对照） |
|---|---|---|
| LLM-suite detection（40 口径） | **20/40 = 50.00%** | **31/40 = 77.50%** |
| M-2 基线（40 口径） | 20/40 = 50.00% | 31/40 = 77.50% |
| 逐任务对账（match / both_none / replay_none / **mismatch**） | 40 / 9 / 1 / **0** | 40 / 9 / 1 / **0** |
| oracle 独立四分类（38 注入任务） | correct **0** / fp **29** / silent **9** / misguided 0 / unavailable 2 | 同左 |
| oracle 类别 vs M-2 混判分类 | match 38 / both_unavailable 12 | 同左 |

- **接线验证**：anchor-only state 注入 38/50（compiled_empty 12 = 9 个
  `*_test` 驱动任务 + flatten + max_sublist_sum + node），未注入原因逐任务可审计。
- **关键结论**：判分耦合修复后，LLM-suite detection 与 M-2 **逐位一致**；oracle
  独立四分类与 M-2 混判逐任务分类一致（38/38）。即**"oracle 通道当前净负"
  的质量结论不变**（correct 0 / fp 76%）——耦合是"可测量性"缺陷而非质量缺陷，
  质量改进（编译器绑定自校验、假阳治理）仍需下一轮。
- **真 LLM 冒烟**（`smoke/`，find_in_sorted，df_spec 臂，1 次真实调用）：注入
  发生（`spec_oracle_injected=true`）、`oracle_suite_verdict=fp`；
  **同一生成测试 LLM-suite detection=1.0，而 legacy 混判 detection=0.0**
  ——直接演示独立判读防止既有检出被 oracle 失败抹掉（验证性，不作证据）。

## 11. O-1 仪器加固（2026-10-18）：崩溃安全 harness + 前件校验输入

> **性质**：**仪器治疗 ≠ 检出能力提升**。本节修复的是"仪器失效如何被记账"
> （崩溃被误判为 fp、前件违反输入被绑进 oracle），不改变 oracle 断言语义；
> `correct` 仍为 0（语义质量治理是独立任务）。生产开关
> `SPEC_ORACLE_EXEC_ENABLE` 默认关 → 历史批次数字不变。

### 11.1 两条仪器缺陷（承接 §10 的 M-2 证据）

§6/§10 的 M-2 重放显示 oracle 四分类 correct 0 / fp 29（76.32%），其中 fixed
侧失败 **27 例是异常崩溃**（TypeError 24 / AttributeError 2 /
ZeroDivisionError 1）、**仅 2 例是断言失败**——即"净负"的绝大多数是**仪器
把崩溃记成假阳判定**，而不是 oracle 判定"语义错误"。此外旧口径的输入绑定
（`boundaries[0]` 直绑 / 无边界时字面量 0）可能**违反前置条件**，前件断言
失败被混入 fp，无法区分"输入不合法"与"实现不满足规约"。

### 11.2 修复（`src/specs/spec_ir_v2.py` / `src/specs/spec_smt.py`）

1. **崩溃安全 harness**：`compile_spec_oracle` 生成的主 oracle
   `test_specir_v2_oracle`（以及 `test_specir_v2_smt_witness_*`）把
   绑定/前件断言/调用/后件断言全部包进 `try`：
   - `AssertionError` **原样 re-raise**（断言失败 = oracle 的语义判定信号，
     必须保留为 fail，不得 skip）；
   - 其余 `Exception`（TypeError / ZeroDivisionError 等仪器失效形态）→
     `pytest.skip("oracle-unavailable: <ExcType>: <msg>")`（不静默 pass、
     不伪装 fail；`pytest-timeout` 的 Failed 属 BaseException 不在此捕获，
     超时仍单列）；
   - BaseException（KeyboardInterrupt 等）不捕获（不掩盖进程级故障）。
2. **前件校验输入选择**：有 `boundaries` 且签名已知时，按顺序用**受限安全
   求值**（`spec_smt.safe_eval_clause`，白名单 AST + 内建调用白名单，零
   eval/exec）检查候选 input 是否满足全部**可机检前件**（= 能编译为
   `assert <expr>` 的表达式子句；NL 前件不可机检、保持 provenance 注释）：
   - 只绑定"元数兼容且满足前件"的第一个候选（违反前件的候选不绑定、
     继续试下一个）；
   - 全部候选被拒 → 不自造输入：改走 **SMT 见证**绑定（`spec_smt` 求解器
     通道，见证值满足前件）；
   - SMT 亦无见证（开关关/z3 缺失/UNSAT）→ 产出带
     `pytest.skip("oracle-unavailable: no-valid-input")` 的**保守骨架**。
     选骨架而非返回空串：空串会让注入率静默下降且丢失原因；骨架保留审计
     原因、可被判分/重放记为 unavailable，且**不产假断言**（skip 后不可达的
     assert 属自欺）。
3. **判分/重放细化**：
   - `experiments/_m1_metrics.py`：pytest 摘要解析——skipped>0 且无
     failed → `oracle_suite_verdict="unavailable"`（不再把 rc=0 的 skip-only
     套件误判为 pass/silent；断言失败仍计 fail/fp）；
   - `experiments/oracle_quality_replay.py`：旧四分类键保留，新增
     `fp_breakdown`（`fp_assertion_fail` / `instrument_error` /
     `fp_unattributed`）、`skipped_count`、`skip_reason_counts`；
     `--compare-report` 直出 before/after 对照表。

### 11.3 before/after（df_spec 双臂，零 LLM 重放，工件见 §11.5）

| 指标（分母=可分类 oracle 测试数） | before（M-2 工件） | after（加固后重放） |
|---|---|---|
| `correct` | 0 | **0**（语义质量未变） |
| `fp`（旧键） | **29** | **2**（仅断言型） |
| └ `fp_assertion_fail` | 2 | **2** |
| └ `instrument_error`（崩溃型） | **27** | **0** |
| `silent` | 9 | 9 |
| `misguided` | 0 | 0 |
| `skipped`（仪器不可用，单列不进分母） | 0 | **27** |
| 可分类 oracle 测试数（分母） | 38 | **11** |
| （混判口径）oracle-augmented 40 口径 detection | 10.53% / 18.42% | **44.74% / 71.05%** |
| （混判口径）LLM-only → augmented 转移 lost | 14 / 22 | **1 / 2** |

- 崩溃→skip 原因分布（27）：`oracle-unavailable: TypeError` 24 /
  `AttributeError` 2 / `ZeroDivisionError` 1（与 before 的异常类型分布
  逐类一致）；
- **断言型 fp 保留（2）**：`reverse_linked_list` / `pascal` 类 oracle 在
  fixed 上断言失败，属"oracle 断言与实现不一致"的语义问题，不被 harness
  吞掉——这是"判断错误"与"仪器失效"在测量上可区分的关键证据；
- correct 0 → 0：**加固没有、也不声称提升检出能力**；可分类分母 38→11
  （27 例转为 skipped 单列），任何占比引用必须同时给出分母与 skipped 数。
- **重要修正（诚实披露）**：M-2/N-3 记录的"oracle 混判抹掉 14/22 个 LLM 检出"
  同样被仪器缺陷**放大**——那 14/22 个 lost 任务绝大多数是**崩溃型 oracle 在
  fixed 侧恒红**（仪器失效），而非 oracle 断言真的判错。加固后混判 lost 降至
  **1/2**，augmented detection 由 10.53%/18.42% 升至 44.74%/71.05%。这**不是**
  检出能力提升：LLM-suite detection 不变（50.00%/77.50%）、correct 仍 0；
  只说明"混合判分净损伤"的原量级是仪器伪影主导。剩余 lost 1/2 对应断言型
  fp（语义质量问题），仍需质量治理。

### 11.4 生产判分路径验证（N-3 `--independent-judging` 重放）

加固后以生产 `_m1_metrics` 独立判读链重放 df_spec 双臂（工件
`emse_oracle_instrument_hardening_20261017/independent_judging/`）：
`oracle_suite_verdict` 分布（40 口径）= **unavailable 29 / fp 2 / silent 9 /
correct 0**（两臂相同；29 = 27 个崩溃 skip + 2 个未注入任务 flatten /
max_sublist_sum），即生产判分同样把崩溃 skip 记为 **unavailable**（不混入
fp/silent）；LLM-suite detection 与 M-2 基线逐位一致（df_spec 20/40=50.00%、
df 31/40=77.50%，逐任务 mismatch 0）——仪器加固不影响 LLM 检出测量。

### 11.5 工件与复算

```bash
# 目标单测（零 LLM/零网络；微型 fixture）
.venv/bin/python -m pytest tests/test_oracle_instrument_safety.py -q

# 加固后 before/after 重放（df_spec 两臂；--compare-report 指定 before 基线）
nice -n 15 .venv/bin/python -m experiments.oracle_quality_replay \
    --out experiments/results/emse_oracle_instrument_hardening_20261017 \
    --compare-report experiments/results/emse_oracle_quality_20261017/ORACLE_QUALITY_REPORT.json \
    --jobs 4 --per-test-timeout 1 --file-timeout 240 --repeat 1

# 生产独立判读验证（同一结果目录 subdir）
nice -n 15 .venv/bin/python -m experiments.oracle_quality_replay \
    --independent-judging \
    --out experiments/results/emse_oracle_instrument_hardening_20261017/independent_judging \
    --jobs 4 --repeat 1
```

工件：`experiments/results/emse_oracle_instrument_hardening_20261017/`
（README + JSON + MD + `independent_judging/` + SHA256SUMS；输入 sha256/命令/
分母/限制齐全）。

### 11.6 残余风险（不得省略）

- harness 只捕获 `Exception` 子类：段错误/SIGSEGV/BaseException 类故障仍
  会崩（由外层 subprocess 超时与执行错误单列兜底）；
- **skip 暴露而非修复编译器绑定缺陷**：本治疗只让"仪器失效"不再伪装成
  假阳；绑定/输入选择的语义质量（correct 仍 0）需独立质量治理；
- 前件校验只覆盖**可机检的表达式前件**；NL 前件仍不可机检（保持注释），
  边界候选筛选可能因此宽松；
- `src/graph/nodes.py::_spec_oracle_verdict_after_run` 仍可能把"oracle 全
  skip"的轮次记成 `injected_and_passed`（nodes 写域归 O-3 的 augment-dev，
  本轮未改）——**风险登记**：行级 verdict 与 oracle_suite_verdict 应以
  `oracle_suite_verdict` 为准；
- 仪器加固只影响开关开启后的**未来批次**；历史工件数字不得与加固后数字
  混池引用（须标 mixed/instrument-hardened 口径）。

## 12. P-1 规格可执行示例通道（2026-10-18，v1 探索性）

> **性质**：探索性机制验证（**非 confirmatory**）。本节的任何"提升"数字都
> 不是能力主张——n=20、单次 LLM 生成、单次重放，结论只用于定位下一步。

### 12.1 背景与目标

O-1 仪器治疗后 oracle 崩溃可记账（fp 29→2、unavailable 27），但 **correct
仍为 0**：语义质量瓶颈是"机器化断言不触达缺陷行为"（§11）。P-1 给 oracle
增加一条**规格可执行示例**通道：LLM **只看规约材料**（Planner 锚
`logic_analysis` / 人类 docstring / 参数名元数据，**不发送缺陷代码**，防
oracle-from-implementation 固化 misguided）生成
`[{"input": ..., "expected": ...}]`，编译为 `assert f(*args) == expected`。

### 12.2 实现（写域内 4 文件 + 测试 + 工件）

1. **数据通道**（`src/specs/spec_ir.py`）：`parse_logic_analysis` 透传
   `examples`（≤5；非法形状/NaN/非 JSON 字面量丢弃不抛；重复去重；无有效
   示例不写键）。
2. **编译器**（`src/specs/spec_ir_v2.py::compile_spec_oracle`）：逐示例断言
   （repr 字面量、零 eval/exec、与 O-1 同一崩溃安全 harness：AssertionError
   re-raise、其余 Exception→pytest.skip）；示例断言置于执行体最前；**有示例
   时丢弃 0 字面量退化绑定**（避免 fixed 侧自伤 crash 把整 oracle 变
   unavailable）；input 契约 = 位置实参列表（单参 `[x]`→`f(x)`，容器
   `[[1,2]]`→`f([1,2])`）。
3. **生成器**（`experiments/spec_examples_generator.py`）：spec-only prompt、
   strict JSON 校验、失败透传空+原因、每任务 1 次调用、`LLM_MAX_OUTPUT_TOKENS`
   默认 512、cache namespace、token/成本快照、价目表成本估算（缺失不编造）。
4. **质量重放**（`experiments/oracle_examples_replay.py`）：df_spec 归档双臂
   A（无示例）/ B（LLM spec-only 示例）逐任务本地 pytest 分类（O-1 口径），
   任务级转移 + 生成审计 + 确定性 JSON 报告。

另修复 O-1 遗留仪器 bug：multi-param boundary 的 pre 断言在
`args = X; f(*args)` 下 NameError（合法输入被误判不可用）。该修复使
"无示例与 O-1 逐字节不变"在 multi-param boundary 子集上出现一行参数名绑定
（调用保持 `f(*args)`），已在工件 §8 披露。

### 12.3 结果（df_spec 双臂，工件 `p_round_oracle_examples_20261018/`）

任务子集：缺陷程序按 task_id 排序前 20 个；两源臂 oracle 材料相同、结果逐位
相同。生成：**20/20 成功**、90 条 examples、20 次调用、13,835/1,704 tokens、
**$0.006195**（预算 $0.1 的 7%）。

| 指标（oracle 测试级；分母=可分类） | A 无示例 | B 加示例 |
|---|---|---|
| 注入成功任务 | 18/20 | **20/20** |
| 可分类 oracle 测试数（分母） | 5 | **14** |
| correct | 0 | **6** |
| fp（全部断言型） | 0 | **3** |
| silent | 5 | 3 |
| misguided | 0 | **2** |
| unavailable（单列） | 13 | **6** |

任务级 A→B：unavailable→correct 5、silent→correct 1、unavailable→misguided 2、
unavailable→fp 2、silent→fp 1、unavailable→silent 3、silent→unavailable 3、
unavailable→unavailable 3。

**逐例归因**（`ATTRIBUTION.json`，buggy/fixed 真实实现回放示例）：

- 6 个 correct **全部为真检出**（fixed 全过、buggy 至少一例败）；
- 3 个 fp 均为**返回容器表示形态差异**（generator/tuple vs list，直接 `==`
  不等；JSON 归一后 fixed 全过、buggy 仍败 → 归一化后可转为 3 个额外真检出）；
- 2 个 misguided 均为 **LLM 示例期望值错误**且 buggy 恰好匹配错误值：
  `is_valid_parenthesization('(((')` 期望 True（应 False）、
  `knapsack(5, [[5,10]])` 期望 0（fixed 返回 10）。

### 12.4 诚实结论

- 示例通道**有真实检出能力**（0→6 个真检出），但 **v1 不提升净质量**：
  同时引入 5 个错误分类（3 表示型 fp + 2 示例幻觉 misguided）；精确率
  6/14、错误率 5/14。任何"oracle 质量提升"的表述都不成立。
- 5 个错误分类里 **3 个是表示比较口径问题**（可通过 v2 归一化消除）、
  **2 个是 spec-only 示例正确性问题**（需示例自校验/二次过滤），说明下一步
  方向明确、通道本身不是死路。
- unavailable 单列（A 13 / B 6）：A 的 13 不等于漏检——O-1 harness 把崩溃
  记 skip；B 的 6 同样不进分母。
- 与 O-1 数字不可混池（口径不同：O-1 是仪器处置前后，P-1 是示例通道 A/B）。

### 12.5 下一步

1. **v2 表示归一**：示例断言比较前对 generator/tuple/迭代器做 JSON 归一
   （预期 3 个表示型 fp→correct，correct 6→9、错误 5→2）；需明确"比较规格
   语义而非容器实现表示"的口径与误报风险。
2. **示例自校验**：用 spec 自身 post 表达式/类型域过滤矛盾示例（消除 2 例
   幻觉型 misguided）。
3. **扩大 n 与重复采样**（50 任务 × 2 采样，成本仍 <$0.1），给描述性区间。
4. **生产接线**（run_benchmark/nodes 写域 + 配额）需 Lead 裁决，本轮仅重放。

### 12.6 工件与复算

```bash
# 真实质量重放（每任务 1 次 LLM 调用，预算 ≤$0.1；本轮 $0.006195，墙钟 271.4s）
nice -n 15 .venv/bin/python -m experiments.oracle_examples_replay \
    --out experiments/results/p_round_oracle_examples_20261018 \
    --limit 20 --jobs 4 --per-test-timeout 1 --file-timeout 180 --no-llm-cache

# 契约/自含 demo 测试（零 LLM/零网络）
.venv/bin/python -m pytest tests/test_oracle_examples.py -q
```

工件：`experiments/results/p_round_oracle_examples_20261018/`
（`ORACLE_EXAMPLES_REPORT.json` + `ATTRIBUTION.json` + `README.md` +
`SHA256SUMS`；输入 sha256/prompt sha256/生成 examples/成本/限制齐全）。


### 12.7 P-1.1 表示归一（2026-10-18，零 LLM 复算）

P-1 §12.3 的 3 个 fp（`flatten`/`kheapsort` 返回 generator、`hanoi` 返回
list[tuple]）是**容器表示形态**而非语义错误。P-1.1 在示例断言比较处引入
stdlib-only 归一（`spec_ir_v2.normalize_return_value`，产物内联
`_specir_norm_return`）：tuple/list 递归→list、dict 保持 dict 值递归、
str/bytes/bytearray 原样、**Iterator（generator/iter）→list 一次性消费**、
其余原样；两侧（返回值与 expected）比较归一后值。无示例路径不引入任何
归一代码（A 臂 20/20 任务 oracle code sha256 与 P-1 逐字节一致）。

复用 P-1 已生成 examples（重放工具 `--reuse-examples`，**零 LLM**），仅重跑
分类（墙钟 255.3s；工件 `ORACLE_EXAMPLES_REPORT_norm.json`，body digest
`9c101a60…`；来源报告 `87ee536b…` / `f5d5d241…`）：

| B 臂（oracle 测试级；分母=可分类） | P-1 raw | P-1.1 norm |
|---|---|---|
| 可分类分母 | 14 | **13** |
| correct | 6 | **8** |
| fp | 3 | **0** |
| silent | 3 | 3 |
| misguided | 2 | **2** |
| unavailable | 6 | 7 |
| 精确率 / 错误率 | 42.9% / 35.7% | **61.5% / 15.4%** |

逐任务：`hanoi` fp→**correct**、`kheapsort` fp→**correct**（归一后 fixed
全过、buggy 仍败）；`flatten` fp→**unavailable**（fixed 归一后通过，但 buggy
在一个混合类型示例上 TypeError→O-1 harness skip，全 oracle 不可判定；已不再是
fp）。**2 个 misguided 原样保留**（`'((('` 期望 True、`knapsack` 期望 0 均为
LLM 示例期望值错误，归一只改表示比较、不改错误期望）。

结论：表示型误差清零，剩余错误仅 2 例 spec-only 示例幻觉；correct 8/13、
错误 2/13（n=20、单次重放，**探索性**）。下一步按 Lead 裁决：示例自校验/
二次过滤（消除幻觉）→ 生产接线（下一轮，涉及 nodes/run_benchmark 写域与配额）。

## 13. Q-1 示例通道生产接线（2026-10-18）

P-1/P-1.1 只在重放工具中验证示例通道；Q-1 把它接入真实生产链路，为 Q-2 二臂
A/B 提供开关。**默认关 → 零行为变化**。

### 13.1 开关与 Planner 契约

新 env `SPEC_ORACLE_EXAMPLES_ENABLE`（默认 false），与既有
`SPEC_ORACLE_EXEC_ENABLE` 组成**双门**：两者都为 true 时
`PlannerAgent.plan` 在 prompt 末尾追加 `SPEC_EXPR_EXAMPLES_SECTION`
（`src/agents/planner.py`）——请求 `logic_analysis.examples`：≤3 条、
`[{"input": <JSON 字面量列表>, "expected": <JSON 字面量>}]`、input 为按参数
顺序展开的实参列表、expected **由规格推导而非实现猜测**、输入尽量小、无法
判定则不输出。关闭时该段不追加（prompt 与历史**逐字节一致**，单测以
`on_query == off_query + SECTION` 锁定；删契约负控亦覆盖）。

Planner 返回后 `_sanitize_logic_analysis_examples` 严格净化：≤3 条、非法
JSON 字面量/形状丢弃不抛；开关关时**删除** `logic_analysis.examples`（即使
模型/缓存自发输出），保证下游 SpecIR/oracle 产物与历史口径一致。

### 13.2 链路生效与材料源

`Planner → parse_logic_analysis（examples 透传）→ compile_spec_oracle
（逐示例断言，P-1.1 归一比较 + O-1 harness）→ N-3 独立判读` 全链路真实
生效：`nodes._resolve_spec_oracle_material` 四源优先级不变，`spec_ir` /
`test_plan.logic_analysis` 中的 examples 直接进入编译。开关关时
`_append_spec_oracle_to_test_with_verdict` 在编译前**剥离**材料中的 examples
（`material_source` 追加 `+examples_stripped` 日志），关闭口径与历史逐字节
一致（单测锁定）。

无 Planner 臂（`plain_llm_df_spec` / `_doc` / `_doc_union` / `_doc_augment`）：
`run_benchmark._attach_generated_spec_examples` 在双门开时调用
`experiments/spec_examples_generator.py`（**spec-only**、不发送缺陷代码、
每任务 **+1 次 LLM 调用**、示例 ≤3、max_tokens 默认 512、cache namespace
沿用 `AITESTER_CACHE_NAMESPACE`）；成功 → examples 并入
`spec_anchor.logic_analysis`（仅 human_spec 的锚构造
`{"function_name", "examples"}` 的 logic_analysis），失败/空/异常透传空且
不改锚材料。

### 13.3 审计字段与 env 门禁

结果行新增两键（成功/失败分支键位一致）：
`spec_oracle_examples_source ∈ {planner, spec_generator, none}`、
`spec_oracle_examples_count`（int，实际被 oracle 使用的条数；默认关恒
none/0）。`spec_ir`/`test_plan.logic_analysis` → `planner`；
`spec_anchor.logic_analysis` → `spec_generator`；无示例 → `none`。

env 门禁：`SPEC_ORACLE_EXAMPLES_ENABLE` 与 Q-3 的
`AITESTER_POSTPROCESS_WARN_S`（默认 600，仅登记）已登记入
`docs/env_budget.yaml` 与 `experiments/run_benchmark.py::_env_snapshot_keys`；
`check_env_budget.py --check` / `check_env_snapshot_keys.py` / `check_baseline.py`
全绿。Q-3 的键由 `check_env_budget.py::MANUALLY_REGISTERED` 保登记（该键由
experiments/postprocess_wall.py 消费，实验脚本不在产品开关扫描面）。

### 13.4 零差异证据 / 成本 / 测试

- **关闭零差异**：Planner prompt 逐字节不变（单测 on=off+SECTION）；节点层
  剥离 examples 后产物与无示例编译逐字节一致；行字段 none/0；`SPEC_ORACLE_*`
  历史批次工件不受影响。
- **成本估算**（Q-2 aitester 双臂）：契约段约 +250 input tokens/任务；20 任务
  ×2 臂 ≈ +10k tokens，按 deepseek-flash 峰时价 < **$0.01**；无 Planner 臂
  的 spec_generator 每任务 +1 次小调用（max_tokens 512），20 任务约
  +$0.006/臂（Q-2 不用该路径）。
- **测试**：`tests/test_oracle_examples_production.py` 33 例（双门开关、prompt
  逐字节/契约内容/删契约负控、净化≤3、planner→oracle 端到端断言、关闭剥离
  逐字节、生成器调用/降级/human_spec 锚、行字段三分支两键位、env 门禁子进程）；
  相关回归 395+202 例通过；ruff/mypy 目标文件干净。
- **端到端 demo（mock LLM，零真实调用）**：mock Planner 返回 examples
  `[{"input":[2,3],"expected":5}]` → `plan()` → `nodes` 注入产物出现
  `assert _specir_norm_return(add(2, 3)) == _specir_norm_return(5)` 且
  `examples=1`；开关关时同一路径产物与无示例编译逐字节一致（见
  `test_planner_examples_compile_to_assertions` /
  `test_disabled_strips_examples_and_matches_no_example_output`）。
