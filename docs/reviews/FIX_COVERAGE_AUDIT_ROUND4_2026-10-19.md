# 覆盖率审计 ROUND4（AA 轮，2026-10-19）

最后更新：2026-10-19
范围：AA 轮对 ROUND3 §3「全仓未覆盖行地图」中**剩余防御线**的可达性判定 +
本轮新增的确定性回归锁。零 LLM 调用、$0 配额。
前置阅读：`FIX_COVERAGE_AUDIT_2026-10-19.md`（Y 轮）、
`FIX_COVERAGE_AUDIT_ROUND2_2026-10-19.md`（Y2 轮）、
`FIX_COVERAGE_AUDIT_ROUND3_2026-10-19.md`（Y3 轮，其 §4 优先级即本轮任务单）。

本轮立场先说清楚：**不再以降未覆盖行数为目标**。ROUND3 §4 已判定剩余 637 行以
容错 / 防御 / 平台分支为主，边际价值低于前三轮。AA 轮因此只做两件事——
① 把**可达但未锁**的路径补成确定性回归锁；② 把**不可达**的路径从"口头判断"
升级为**可复现证据 + 源码登记**，并拒绝用伪造 mock 或 `# pragma: no cover`
把它们从口径里抹掉。

---

## 1. 本轮新增的确定性回归锁（9 例）

| 文件 | 用例 | 锁住的行为 | 源站点 |
| --- | --- | --- | --- |
| `tests/test_trace_jsonl_integrity.py` | `test_unserializable_record_dropped_without_raising` | A20 契约"坏行丢弃不抛"（结构守卫后序列化失败） | `src/observability/trace.py:251-254` |
| 同上 | `test_unwritable_trace_path_ignored` | 落盘路径不可写（目录名冲突）时静默忽略、不影响主流程 | `trace.py:267-269` |
| 同上 | `test_dump_recent_to_limit_slices_newest_snapshots` | Recent-buffer 导出按**最新**截断（顺序错＝取证样本倒置） | `trace.py:445-446` |
| 同上 | `test_dump_recent_to_write_failure_returns_none` | 导出写失败返回 None 而非抛穿（观测层失败不改判定） | `trace.py:481-483` |
| `tests/test_cluster_robust_stats.py` | `test_row_without_task_id_is_skipped_not_resolved` | 结果行缺 `task_id` → 跳过而不是被解析成伪样本 | `experiments/statistical_analysis.py:2735-2736` |
| 同上 | `test_duplicate_task_id_keeps_first_archived_metadata` | 重复 `task_id` 保留**首个**归档元数据（口径唯一化） | 同文件同函数 |
| `tests/test_helpers_20261019_branches.py` | `test_array_falls_through_tier2_when_leaf_invalid` | 数组档 1/档 2 均非法时逐档降级后显式抛错（该落空弧此前无测试经过） | `src/utils/helpers.py:679-685` |
| 同上 | `test_object_tier2_cannot_rescue_bare_backslash_fragment` | 裸反斜杠致扫描器分歧时，首对象档**不救援**、落到叶子档取最后一个 | `helpers.py:775-789`（本轮判定见 §2.6） |
| 同上 | `test_value_position_gate_grammar_is_what_makes_safe_eval_rejects_dead` | 值位置正则门文法逐字节钉住 + 门内输入恒被改写为字符串 | `helpers.py:402`、`helpers.py:448-479` |

变异验证（每条都实跑，不是推理）：

- **门放宽**变异（`_JSON_VALUE_EXPR_PATTERN` 增放行 `"a"+3`）→
  `test_value_position_gate_...` **失败**，其余 11 例通过 ✓
- **修复器救援**变异（`_repair_json_text` 顺手删裸反斜杠）→
  `test_object_tier2_cannot_rescue_...` **失败** ✓
- 上一批次（同轮）：`analyze_results.load_latest_benchmark` 的静默回退复原 →
  2 例失败；还原修复 → 4 例通过。棘轮 `--allow-bump` 三例默认不写回锁见
  `tests/test_w_batch.py::TestW2CoverageRatchet`。

## 2. 判定为"构造上不可达"的 9 处（登记，不覆盖）

证据分两档：**可证**（值域/文法闭合，无需实验）与**实证**（大规模枚举未观测到，
且给出结构解释）。二者都**不**构成"可以删掉"的充分条件，处置见 §3。

| # | 站点 | 判据 | 证据 | 档 |
| --- | --- | --- | --- | --- |
| 1 | `helpers.py:454-457` Mult 反向操作数（`int × str`）与 `unsupported mult operands` | `_safe_eval` 唯一入口是 `:402` 的值位置正则门，门只放行 `引号串 * \d+` / `引号串 + "引号串"` | 门内文法枚举 3,990 条：节点种类仅 `{Constant, BinOp, Add, Mult}`，Mult 右恒为 int 常量 | 可证 |
| 2 | `helpers.py:458-459` `unsupported operator` | 同上，门内只可能出现 `Add` / `Mult` | 同上枚举：`ops = {Add, Mult}` | 可证 |
| 3 | `helpers.py:467` `unsupported node` | 门内文法不产出 `Call/Attribute/Name/Subscript/UnaryOp` | 同上枚举 | 可证 |
| 4 | `helpers.py:478-479` "求值结果非字符串则保持原样" | 首个 atom 恒为引号串，Add/Mult 结果恒 str | 枚举输入 100% 被改写、`json.loads(...)>k` 恒为 str | 可证 |
| 5 | `helpers.py:681-682` 假分支（叶子解析成功但非 list） | `_JSON_ARRAY_LEAF_PATTERN = \[[^\[\]]*\]` 保证片段以 `[` 开 `]` 闭 → `json.loads` 只会返回 list 或抛错 | 片段取值域枚举（含 `[[]]`、`[ ]`、`[null]`）无一返回非 list | 可证 |
| 6 | `helpers.py:786-787` 首对象修复档的返回分支 | 档 1 与本档在同一首 `{` 上取片段：`_find_balanced_json`（委托 `_find_balanced_delimited`）与 `_first_balanced_object` 仅在**字符串外的裸反斜杠**处分歧；分歧时本档片段自身含非法转义 | 54,006 输入扫描：分歧 832 例，被五个候选（raw + 四条修复）**任一救回 0 例**；28,017 残片 fuzz 未命中该行 | 实证 |
| 7 | `mdo.py:446-447` `not_serializable` | `payload` 出自同函数 `json.loads`，其值域天然可再序列化 | 结构推导（无循环引用、无自定义对象可进入） | 可证 |
| 8 | `mdo.py:893-898` rc 分派的 `else` | `rc<0` 与 `rc>=2` 归 `_is_execution_error`（`:764-777`），`rc==0/1` 各有分支 → 值域无剩余 | `rc ∈ [-14, 14]` 全枚举：落到 `else` 的 rc 为**空集** | 可证 |
| 9 | `mdo.py:902-903` `n == 0` 除零护栏 | `:815-816` 已对空变异体池提前返回，循环每轮必 `append` | `compute_mdo(mutants=[]) → not_available_reason="empty_mutant_pool"`，`n==0` 永不被求值 | 可证 |

站点 8 的**旧注释是错的**：它把这个 `else` 写成"其他非 0 退出（rc==3 internal
error / rc==4 usage error 等）"的处理分支，而 rc==3/4 早被 `rc >= 2` 收走。
本轮已就地改写注释——这类"注释声称在处理、实际恒不触发"的站点，比未覆盖行本身
更容易误导后续维护者。

## 3. 处置纪律：为什么不删、也不加 `# pragma: no cover`

- **不加 pragma**：`# pragma: no cover` 会把这 9 处从分母里抹掉，直接抬高
  总覆盖率读数。本项目的覆盖率是**论文口径的一部分**（`docs/coverage_ratchet.yaml`
  水位 + `check_artifact_doc_consistency.py` 对账状态登记册），用注释改分母属
  典型的"改口径不改事实"，与 H 轮以来"不得伪造 mock 凑覆盖"同族，拒绝。
- **暂不删除**：站点 6 的判定建立在经验枚举（54k/28k 输入、0 例反例）而非证明上，
  且其 docstring 声称的 `57/188` 多对象拼接是**真实历史样本**（D1 修复的立据）。
  删除它属于行为变更，需要单独的轮次带着更长的真实响应语料来判断，而不是在
  覆盖率补口轮里顺手做掉。§1 的 `test_object_tier2_cannot_rescue_bare_backslash_fragment`
  先把**当前可观察口径**钉住：若日后有人放宽修复器使首对象被救回，测试先红。
- **保留作双保险**：站点 1-5、7-9 的防御分支都在"上游一旦放宽即生效"的位置
  （正则门、执行器替身、探针 schema）。已在源码就地标注"恒不可达 + 为什么 +
  为何保留"，与本仓既有约定（`spec_ir_v2.py` 的"理论不可达…双保险"、
  `graph/workflow.py` 的开关不可达标注）同风格。
- **口径不刷新**：水位 `line_total: 96.40 / branch_total: 92.50` 维持不动。
  AA-4 已把上调改成 `--allow-bump` 显式确认——本轮新增 9 例测试带来的覆盖率
  增量要等 **CI ubuntu 3.14 阻断档**实测同口径后再决定，本地 macOS 读数不作数。

## 4. 结论与下一轮

1. 本轮**没有**发现新的 P1 契约缺口；净新增的是 9 例确定性锁 + 9 处不可达登记 +
   1 处误导性注释修正。
2. `helpers.py` 首对象修复档（§2.6）是本轮唯一**疑似冗余**的功能块：它可能在
   K 轮快路径 + 档 1 修复链补齐后已被完全吞并。这是下一轮值得单独处理的项——
   判据要用真实 LLM 响应语料（缓存样本 4,041 条已在 D1 记录里），不是随机残片。
   **【AB-1 已回答，2026-10-19 同日】**工件
   `docs/reviews/TIER2_REAL_CORPUS_REPLAY_2026-10-19.md` +
   `experiments/helpers_tier_replay.py`。实际可用语料已长到 **7,565** 条（不是 4,041）。
   结论**分两半，且一半推翻本项的假设**：
   ① "返回分支触发 **0** 次（0/667 取到片段）"——本项怀疑的冗余**在观测上成立**；
   ② 但"它可能被**完全吞并**"**不成立**：7,565 条里有 **1** 条 `_find_balanced_json`
   直接返回 `None`（串外裸反斜杠吃掉后继 `}`、深度不归零），此时整个档 1 修复块被
   跳过，**档 2 是首个也是唯一**产出片段并做语法修复的档。它这次没返回是因为
   5 个候选救不活那个片段（`Expecting ',' delimiter`，值位置 Python 表达式类），
   不是因为档 1 已经先试过。机制已钉成确定性锁（`'{"a":\\}{"b":1}'`）。
   ⇒ 处置：档 2 **保留**，但本项怀疑的"冗余"在**返回值层面被证实**（三口径一致
   0 次触发：真实语料 0/667、分歧类定向枚举 0/716、覆盖率该两行未命中），
   被推翻的只是 AA-5 的**论证**。`helpers.py` 注释里"恒不可达"这个全称措辞与
   "档 1 已全失败"这个错前提都已删除；删除本档属行为变更，仍按纪律留给单独轮次，
   且现在带着等价性锁（`TestDeletionEquivalenceProbe`）与"候选一旦能救活分歧片段
   即转红"的守卫（`TestDivergentClassUnrescuable`）去做。
3. 剩余未覆盖行按 ROUND3 §3 地图，仍以 `orchestration_search`（冻结功能，74 行，
   **不该**覆盖）、数据集适配层（需先确认本地数据集可用性）、
   `spec_ir_v2` SMT 见证保守边界为主。补测优先级已让位于**科学主张接线**
   （AA-6 D3b Step B）与**人工裁决执行面**（AA-7 E7）。

## 附录：复跑

```bash
# 本轮新增锁（279 例含同批 JSON/MDO/trace/w 批次回归）
.venv/bin/python -m pytest -q tests/test_helpers_20261019_branches.py \
    tests/test_trace_jsonl_integrity.py tests/test_cluster_robust_stats.py \
    tests/test_w_batch.py

# 变异验证（改 src/utils/helpers.py 前先 cp 备份）
#   变异 A：_JSON_VALUE_EXPR_PATTERN 末尾加 |\s*\+\s*\d+   → 门文法锁应失败
#   变异 B：_repair_json_text 内 s = s.replace(chr(92), "") → 首对象档锁应失败

# 不可达判定复现（三段脚本，逐条对应 §2）
#   1) 值位置门文法枚举：itertools.product(atoms+ops, repeat=1..4) 过
#      _JSON_VALUE_EXPR_PATTERN，统计 ast.walk 的节点/运算种类
#   2) 扫描器分歧枚举：随机残片 '{}",:1 \\' × 长度 2..10，比较
#      _find_balanced_delimited(t, t.find("{"), "{", "}") 与 _first_balanced_object(t)，
#      对每个分歧片段跑档 2 五候选，统计"被救回"例数
#   3) mdo：枚举 rc ∈ [-14,14] 打印 877/879/882/893 分派归属；
#      compute_mdo(mutants=[]) 应返回 empty_mutant_pool
```
