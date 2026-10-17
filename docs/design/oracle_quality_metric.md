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
