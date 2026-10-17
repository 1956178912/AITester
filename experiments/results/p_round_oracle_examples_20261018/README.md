# P-1 规格可执行示例通道：质量重放（A=无示例 vs B=LLM spec-only 示例）

> **性质（先读）**：这是**探索性机制验证（非 confirmatory）**，不是能力声明。
> B 臂示例由 LLM（deepseek-flash）**只看规约材料**生成（**不发送缺陷代码**），
> 每任务仅 1 次调用、n=20、单次运行；不得外推。逐测试分类复用 O-1 口径
> （崩溃→skipped/unavailable 单列，断言失败保留为 fp/correct 等）。
>
> **一句话结论**：示例通道**确实有检出能力**（A 臂 0 检出 → B 臂 **6 个真检
> 出**，逐例人工核验 fixed 全过、buggy 至少一例败），但同时引入 **5 个错误
> 分类**（3 例表示形态 fp：generator/tuple vs list；2 例 LLM 示例期望值错误
> → misguided）。在 14 个可分类 oracle 测试中 correct 6 / fp 3 / misguided 2 /
> silent 3（精确率 42.9%，错误率 35.7%）——"大幅提升检出"与"接近可用"都**不**
> 成立；这是 v1 通道的机制证据与下一步清单。

## 1. 协议（探索性）

| 项 | 设置 |
|---|---|
| 数据 | `experiments/results/emse_df_spec_20261016/` 的 **两个 df_spec 归档臂**（`plain_llm_df_spec` / `plain_llm_df`） |
| 任务子集 | 缺陷程序（排除 `*_test` 驱动任务），按 task_id 排序取前 **20** 个（`--limit 20`，预算控制；子集偏置见 §8） |
| A 臂 | O-1 当前编译产物：同一锚表 `logic_analysis` → pre/post/boundary 通道，**无 examples** |
| B 臂 | 同一锚材料 + **LLM spec-only 生成**的 examples（`parse_logic_analysis` 透传 → `compile_spec_oracle` 逐示例断言） |
| 分类 | oracle 测试在 buggy/fixed 两侧本地 pytest 执行；correct=buggy 败∧fixed 过；misguided=buggy 过∧fixed 败；silent=两侧过；fp=fixed 败（断言型）；unavailable=skipped/timeout/collect/材料不可判（O-1 harness：崩溃→skip） |
| 分母 | **可分类 oracle 测试数**（correct/fp/silent/misguided）；unavailable 单列、不进分母 |
| 生成预算 | 每任务 **1 次** LLM 调用；`LLM_MAX_OUTPUT_TOKENS=512`；`--no-llm-cache`（真实调用，成本可测）；目标 ≤$0.1（实际 **$0.006195**） |

复算命令：

```bash
nice -n 15 .venv/bin/python -m experiments.oracle_examples_replay \
    --out experiments/results/p_round_oracle_examples_20261018 \
    --limit 20 --jobs 4 --per-test-timeout 1 --file-timeout 180 --no-llm-cache
```

墙钟 271.4s；body digest `f5d5d241…`；run_meta 记录 python/platform/argv。
JSON 收尾时以 append-only 方式补记两条口径披露（§8 末两条），`run_meta.postprocess`
记录该操作；分类/生成/成本数值未变，工具源已同步，未来运行直接包含。
LLM 服务端非严格确定（temperature=0 也无法保证逐位复现），工件记录每任务
prompt sha256 与实际生成 examples（`report.arms[].tasks[].examples_generation`）。

## 2. 输入与实现

| 输入 | sha256 |
|---|---|
| `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json` | `813c437f…` |
| `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json` | `536da803…` |
| `experiments/results/emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json` | `3e90b2ad…` |

实现（本轮新增/修改）：

1. **数据通道** `src/specs/spec_ir.py::parse_logic_analysis`：透传 `examples`
   （`[{"input": <JSON literal>, "expected": <JSON literal>}]`，≤5、非法形状
   丢弃不抛、NaN/非 JSON 字面量拒绝、完全重复去重）；无有效示例**不写键**
   （向后兼容）。
2. **编译器** `spec_ir_v2.compile_spec_oracle`：有效示例逐条编译为
   `assert f(实参…) == 期望值`（repr 字面量、零 eval/exec），与 O-1 同一崩溃
   安全 harness（AssertionError re-raise、其余 Exception→
   `pytest.skip("oracle-unavailable: …")`）；示例断言位于执行体最前；**有示例
   时丢弃"0 字面量臆造输入"的退化体**（避免 fixed 侧自伤 crash 使整个 oracle
   不可用）；示例 input 契约 = **位置实参列表**（单参函数 `[x]`→`f(x)`；单参
   值为容器时 `[[1,2]]`→`f([1,2])`；长度≠1 的 list 按旧"单参值"兼容）。
3. **生成器** `experiments/spec_examples_generator.py`：**spec-only**（仅
   `logic_analysis` 字段 + 人类 docstring + 参数名元数据；**不发送缺陷代码**），
   strict JSON（兼容围栏/裸 list/前后说明）、失败透传空+原因、每任务 1 次、
   小 max_tokens、cache namespace、usage/成本快照。
4. **质量重放** `experiments/oracle_examples_replay.py`：A/B 逐任务物化两侧、
   本地 pytest 分类（O-1 口径）、任务级类别转移、生成审计、确定性 JSON 报告。

## 3. 示例生成审计（spec-only）

- 任务 20 / 20 成功（status=ok，无 empty/error）；**生成成功率 100%**；
  平均 4.5 条/任务、共 **90** 条 examples（上限 5/任务）；
- LLM 调用 **20 次**（无缓存命中）；tokens in/out = **13,835 / 1,704**；
  估算成本 **$0.006195**（deepseek-flash 峰时价，`experiments/price_table.json`；
  实际 < 预算 $0.1 的 7%）；
- 生成失败降级：B 回退 A（逐任务可审计；本轮未触发）。

## 4. A/B 前后对照（两个 df_spec 源臂结果相同；下表任取一臂）

| 指标（oracle 测试级） | A 无示例（O-1 现状） | B 加 LLM spec-only 示例 |
|---|---|---|
| 注入成功任务 | 18/20（2 个 `compiled_empty`） | **20/20**（示例恢复了 2 个无法注入任务） |
| 可测量任务 | 18 | 20 |
| 可分类 oracle 测试数（分母） | **5** | **14** |
| `correct` | 0 | **6** |
| `fp`（全部 `fp_assertion_fail`） | 0 | **3** |
| `silent` | 5 | 3 |
| `misguided` | 0 | **2** |
| `unavailable`（单列、不进分母） | **13** | **6** |
| skip 原因 | TypeError 11 / AttributeError 1 / ZeroDivisionError 1 | TypeError 2 / AttributeError 1 / IndexError 1 / RecursionError 1 |

**任务级 A→B 转移**（20 任务）：

| 转移 | 数量 | 任务 |
|---|---|---|
| unavailable→correct | **5** | bucketsort, lcs_length, levenshtein, lis, max_sublist_sum |
| silent→correct | **1** | get_factors |
| unavailable→misguided | 2 | is_valid_parenthesization, knapsack |
| unavailable→fp | 2 | flatten, kheapsort |
| silent→fp | 1 | hanoi |
| unavailable→silent | 3 | find_in_sorted, kth, longest_common_subsequence |
| silent→unavailable | 3 | bitcount, breadth_first_search, depth_first_search |
| unavailable→unavailable | 3 | detect_cycle, find_first_in_sorted, gcd |

解读：A 臂 13 个 unavailable 是 O-1 harness 的"崩溃→skip"（单列），其中
5 个在 B 臂被示例断言变成**真检出**；但 B 臂也让 5 个任务从"未分类/静默"变成
**错误分类**（3 fp + 2 misguided），且 3 个 A 的 silent 因示例超时/崩溃变为
unavailable——通道收益与代价并存。

## 5. 检出证据（自含 demo + 真实数据）

**单元自含 demo**（`tests/test_oracle_examples.py::TestSelfContainedDetectionDemo`，
buggy=`a-b` vs fixed=`a+b` fixture）：无示例 oracle 只有前件断言 → buggy 静默
通过（**不检出**）；加正确示例 `f(2,3)==5` → buggy **AssertionError 检出**、
fixed 通过。另有反证：错误期望值会在 fixed 上误报（示例质量决定语义质量）。

**真实数据逐例核验**（`ATTRIBUTION.json`，用 buggy/fixed 真实实现回放示例）：

- **6 个 correct 全部为真检出**：fixed 对全部示例结果等于 expected、buggy
  至少一例不等（bucketsort / get_factors / lcs_length / levenshtein / lis /
  max_sublist_sum）。示例（节选）：`bucketsort([2,1,2,0],3) == [0,1,2,2]`、
  `lcs_length('abc','abc') == 3`、`levenshtein('cat','cut') == 1`、
  `get_factors(12) == [2,2,3]`、`lis([1,2,3,4,5]) == 5`。
- **3 个 fp 均为返回容器表示形态差异**（非语义错误）：`flatten`/`kheapsort`
  fixed 返回 **generator**、`hanoi` fixed 返回 **list[tuple]**，与示例期望的
  list 字面量直接 `==` 不等。做 JSON 归一（generator/tuple→list）后 3 个任务
  fixed 全过、buggy 仍有失败 → **若加归一会变成 3 个额外真检出**。
- **2 个 misguided 均为 LLM 示例期望值错误**且 buggy 恰好匹配错误值：
  `is_valid_parenthesization('(((')` 示例期望 `True`（应为 `False`，buggy 也
  返回 True→被判 misguided）；`knapsack(5, [[5,10]])` 示例期望 `0`（fixed 返回
  10→buggy 的 0 匹配错误期望→misguided）。属 spec-only 示例幻觉，非通道缺陷。

## 6. 口径纪律与诚实结论

- **不是能力主张**：correct 0→6 与错误 0→5 同时发生；n=20、单次生成、
  单次重放。精确率 6/14、错误率 5/14，不能表述为"oracle 质量提升"。
- **unavailable 单列**：A 的 13 个 unavailable 不等于"漏检"（仪器不可判定），
  B 的 6 个亦单列；分母只含可分类测试。
- **示例来源**：LLM **spec-only** 生成（无缺陷代码输入），示例正确性完全
  取决于规约可执行程度与 LLM 对规约的理解；2 例幻觉已逐条披露。
- **A/B 差异同时包含**：示例断言通道 + "有示例时丢弃 0 字面量退化绑定"
  （后者是必要的仪器安全措施，避免 fixed 侧自伤 crash；无示例路径保持
  O-1 行为）。比较的是"示例替代臆造输入"的整包治疗，不是单变量消融。
- **与 O-1 的关系**：O-1 让崩溃可记账（fp→unavailable）；P-1 在可记账的
  仪器上测"断言是否触达缺陷行为"。两者口径不同，数字不可混池。

## 7. 下一步（按优先级）

1. **返回值表示归一（v2 编译器，最高性价比）**：示例断言比较前对
   generator/tuple/迭代器做 JSON 归一（递归 tuple→list、iterator→list）——
   本轮 3 个表示型 fp 将变成真检出（correct 6→9、错误 5→2，均为纯 LLM 示例
   错误），需在文档中明确"比较规格语义而非容器实现表示"的口径与风险。
2. **示例自校验/二次过滤（spec-only）**：生成后用**规约自身**（post 表达式/
   类型域）做一致性过滤（例如 `'((('` 期望 True 与括号平衡规格矛盾、返回类型
   与 output_domain 不符的示例丢弃），降低 2 例幻觉型错误。
3. **prompt 增补表示契约**：明确"返回迭代器/元组请按 JSON 可比较形态给出期望"
   或要求示例自带规范化说明。
4. **扩大 n 与重复采样**：20→50 任务、每任务 2 次采样（成本仍 <$0.1），给出
   通道增益/错误率的描述性区间与配对一致性（仍非 confirmatory）。
5. **生产接线决策**：`run_benchmark` 接 examples（Planner/锚 → 生成器 → SpecIR）
   涉及 nodes/run_benchmark 写域与配额，**需 Lead 裁决**；本任务仅重放验证。

## 8. 限制

- 任务子集为按 task_id 排序前 20 个缺陷程序（带宽限制的确定性截断），
  非随机抽样；20 个任务中两个 df_spec 源臂的 oracle 材料相同，故两臂结果
  逐位相同（B 示例跨臂复用，预算纪律）。
- 每任务仅 1 次生成、无重试/自一致性投票；temperature=0 但服务端非严格确定。
- per-test timeout=1s：bitcount 等任务示例若选大输入会 timeout→unavailable
  （已通过 prompt 要求小输入，但仍出现 3 个 A silent→B unavailable）。
- 示例断言为**字面量相等**（v1 契约），不处理容器表示/浮点误差/无序集合。
- 归因核验脚本为离线人工验证（`ATTRIBUTION.json`），非重放工具内建；分类
  主口径仍是 oracle 测试在 buggy/fixed 两侧的执行结果。
- **实现偏差披露**：为让 A/B 公平，本轮同时修复了 O-1 的一个仪器 bug——
  multi-param boundary 的 pre 断言在 `args = X; f(*args)` 绑定下 NameError
  （合法输入被误判不可用）。因此"无示例时与 O-1 逐字节不变"在
  **multi-param boundary** 子集上不再成立（多了一行参数名绑定、调用保持
  `f(*args)`）；其余路径字节不变。该修复计入 P-1 工件，O-2 前需知悉。

## 9. 工件清单

| 文件 | 说明 |
|---|---|
| `ORACLE_EXAMPLES_REPORT.json` | P-1 主报告（raw 字面量比较；协议/生成审计/逐任务 A/B 分类/转移/limitations；含每任务 prompt sha256 与实际 examples） |
| `ORACLE_EXAMPLES_REPORT_norm.json` | P-1.1 追加报告（表示归一；`--reuse-examples` 零 LLM 复算；A 臂产物逐字节一致） |
| `ATTRIBUTION.json` | 逐例归因证据（buggy/fixed 真实实现回放；genuine/representation/llm-error） |
| `README.md` | 本文件 |
| `SHA256SUMS` | 本目录文件 + 输入引用（df_spec 两臂/锚表）的 sha256 |

## 13. P-1.1 追加：返回值表示归一（零 LLM 复算）

> 目的：P-1 §5 定位的 3 个表示型 fp（`flatten`/`kheapsort` 返回 generator、
> `hanoi` 返回 list[tuple]）是"容器表示形态"与 JSON list 直接 `==` 不等，
> 不是语义错误。P-1.1 在示例断言比较处引入 stdlib-only 归一
> （tuple/list 递归→list、Iterator→list 一次性消费、str/bytes/dict 不误归），
> **复用 P-1 已生成的 examples**（`--reuse-examples`，**零 LLM 调用/零成本**），
> 仅重跑分类；A 臂（无示例）产物与 P-1 逐字节一致（20/20 任务 oracle code
> sha256 相同）。

复算命令：

```bash
nice -n 15 .venv/bin/python -m experiments.oracle_examples_replay \
    --out experiments/results/p_round_oracle_examples_20261018 \
    --reuse-examples experiments/results/p_round_oracle_examples_20261018/ORACLE_EXAMPLES_REPORT.json \
    --report-name ORACLE_EXAMPLES_REPORT_norm \
    --skip-markdown --limit 20 --jobs 4 --per-test-timeout 1 --file-timeout 180
```

墙钟 255.3s；`ORACLE_EXAMPLES_REPORT_norm.json` body digest `9c101a60…`；
`report.reuse_examples` 记录来源报告 path/sha256/body_digest（
`87ee536b…` / `f5d5d241…`），生成审计 status=reused、llm_calls=0。

### 13.1 B 臂 归一前/后（oracle 测试级；A 臂不变：correct 0 / silent 5 / unavailable 13）

| 指标（分母=可分类） | P-1 raw（字面量 `==`） | P-1.1 norm（表示归一） |
|---|---|---|
| 可分类 oracle 测试数（分母） | 14 | **13** |
| `correct` | 6 | **8** |
| `fp`（全部断言型） | 3 | **0** |
| `silent` | 3 | 3 |
| `misguided` | 2 | **2** |
| `unavailable`（单列） | 6 | 7 |
| 精确率（correct/分母） | 42.9% | **61.5%** |
| 错误率（(fp+misguided)/分母） | 35.7% | **15.4%** |

### 13.2 3 个表示型 fp 的去向（逐任务）

| 任务 | P-1 raw | P-1.1 norm | 原因 |
|---|---|---|---|
| `quixbugs__hanoi` | fp | **correct** | fixed 返回 list[tuple]，归一后与 list 期望相等；buggy 换序 → 检出 |
| `quixbugs__kheapsort` | fp | **correct** | fixed 返回 generator，归一后相等；buggy 输出错序 → 检出 |
| `quixbugs__flatten` | fp | **unavailable** | fixed 归一后通过，但 **buggy 侧在一个混合类型示例上 TypeError→skip**（O-1 harness），全 oracle 不可判定；**不再是 fp**，但也不计入检出 |

### 13.3 2 个 misguided 仍存在（预期）

`is_valid_parenthesization`（`'((('` 期望 True 应为 False）与 `knapsack`
（`5, [[5,10]]` 期望 0 应为 10）都是**示例期望值本身错误**且 buggy 恰好匹配
错误值——表示归一不改变错误期望，故 **misguided 2 例原样保留**。这是
"示例正确性"问题，需下一轮示例自校验/二次过滤解决（本任务按裁决不做）。

### 13.4 结论

- 3 个表示型 fp **全部消除**（2 转 correct、1 转 unavailable）；fp 从 3→0；
- 剩余错误 **仅 2 例 LLM 示例幻觉**（misguided），错误率 5/14→2/13；
- correct 6→8（n=20、单次重放，仍为**探索性**，不作 confirmatory/能力主张）；
- 表示归一是幂等比较口径（不改被测函数），A 臂产物逐字节未变；下一步按
  Lead 裁决推进**示例自校验**与**生产接线（下一轮）**。

工件更新：`ORACLE_EXAMPLES_REPORT_norm.json` 已加入本目录（§9 清单同步）；
`SHA256SUMS` 已重算并覆盖新旧报告。
