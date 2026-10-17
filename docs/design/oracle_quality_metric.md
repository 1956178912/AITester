# 确定性规约 oracle 质量度量（A-05）：设计、口径与已知限制

> 状态：M 轮 T7-A（2026-10-17）零 LLM 重放工具的设计文档（本地件）。
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
