# 自身测试套件变异测试 L 轮报告（2026-10-17）

> 本文件由同名 JSON（机器可读事实源）镜像生成；所有数字来自
> `scripts/tools/self_mutation.py` 的 before/after 实测报告，不手写。

## 1. 口径与复现命令

- 测量口径与 K 轮完全一致：3 个叶子模块、workers=2、**每文件 120 变异体等距抽样**、
  `--test-map` 冻结测试集（after 仅追加 L 轮击杀测试文件）；env_utils/atomic_io 全量执行；
- before 与 after 使用**同一生成器快照、同一工作树源码、同一抽样口径**，变异体 ID 逐项相同；
- score = killed/(killed+survived)；invalid/timeout 不进分母；helpers 为 120/468 抽样点估计。

```bash
# before（K 轮 after 测试集，复现 0.7674）
.venv/bin/python scripts/tools/self_mutation.py --files src/utils/env_utils.py,src/utils/helpers.py,src/utils/atomic_io.py --workers 2 --test-map src/utils/env_utils.py=tests/test_env_utils.py,tests/test_self_mutation_targets.py --test-map src/utils/helpers.py=tests/test_helpers_json_property.py,tests/test_helpers_json_robustness.py,tests/test_helpers_json_fence_content.py,tests/test_self_mutation_targets.py --test-map src/utils/atomic_io.py=tests/test_atomic_io.py,tests/test_self_mutation_targets.py --json-out experiments/results/self_mutation_l_round/self_mutation_before.json --md-out experiments/results/self_mutation_l_round/self_mutation_before.md

# after（同一测试集 + L 轮击杀测试）
.venv/bin/python scripts/tools/self_mutation.py --files src/utils/env_utils.py,src/utils/helpers.py,src/utils/atomic_io.py --workers 2 --test-map src/utils/env_utils.py=tests/test_env_utils.py,tests/test_self_mutation_targets.py --test-map src/utils/helpers.py=tests/test_helpers_json_property.py,tests/test_helpers_json_robustness.py,tests/test_helpers_json_fence_content.py,tests/test_self_mutation_targets.py,tests/test_self_mutation_survivors_l.py --test-map src/utils/atomic_io.py=tests/test_atomic_io.py,tests/test_self_mutation_targets.py --json-out experiments/results/self_mutation_l_round/self_mutation_after.json --md-out experiments/results/self_mutation_l_round/self_mutation_after.md
```

## 2. before / after 总览

| 模块 | before K/S | before score | after K/S | after score | Δ score |
| --- | ---: | ---: | ---: | ---: | ---: |
| `src/utils/env_utils.py` | 71/4 | 0.9467 | 71/4 | 0.9467 | +0.0000 |
| `src/utils/helpers.py` | 77/42 | 0.6471 | 89/30 | 0.7479 | +0.1008 |
| `src/utils/atomic_io.py` | 17/4 | 0.8095 | 17/4 | 0.8095 | +0.0000 |
| **合计** | 165/50 | **0.7674** | 177/38 | **0.8233** | **+0.0558** |

- 有效分母：before 215 → after 215；
- invalid/timeout：before 8/1 → after 8/1；
- baseline_green：before True / after True；measurement_valid：before True / after True。

## 3. L 轮新击杀（12 个，全部 survived→killed，无反向翻转；其中 1 个为诊断文本间接击杀）

| 变异体 | 变异语义 | 击杀测试（tests/test_self_mutation_survivors_l.py） | 行为契约 |
| --- | --- | --- | --- |
| `helpers:29836f6132a3` | extract_json_array 修复候选循环 continue→break | `test_numeric_expression_repaired_in_array` | 数组路径数值表达式修复：首个候选失败后必须继续尝试后续修复档，不得提前终止 |
| `helpers:396a28db8ca8` | _quote_python_expressions 超长/多行守卫 or→and | `test_overlong_single_line_expression_is_not_evaluated` | 超长单行表达式保守不评估（文档 max_len 口径）→ 诚实失败而非静默截断改写 |
| `helpers:5f59874830d1` | _find_balanced_json 闭合符 '}'→'x' | `test_empty_object_via_direct_path_is_not_leaf_fallback; test_fenced_empty_object_is_not_leaf_fallback` | 合法空对象直解析不得被误记为叶子回退（OMS 哨兵公开可观测契约） |
| `helpers:5f886043809a` | 叶子回退尾扫档哨兵置位 True→False | `test_tail_scan_fallback_returns_later_fragment_and_sets_flag` | 尾扫档命中时必须置位 OMS 哨兵（返回值 + 可观测标记成对承诺） |
| `helpers:608205e3bd2f` | _quote_tuple_keys_once 字符串开引号判定改写 | `test_tuple_key_repair_preserves_string_literal_content` | 元组键修复必须字符串感知：字符串内部 ',(0,1):' 文本不得被当键替换 |
| `helpers:925bf0576cf6` | 数值结果位数上限 >→>= | `test_numeric_expression_digit_boundary_is_conservative` | 恰好 4096 位的结果仍须修复（严格大于才拒绝，边界语义） |
| `helpers:a3ee749e3485` | 叶子回退尾扫阈值 2→3 | `test_tail_scan_fallback_returns_later_fragment_and_sets_flag` | ≥3 个叶子且末两个不可解析时尾扫必须触发（返回更早可解析片段） |
| `helpers:a93688ca6eb0` | _quote_tuple_keys_once esc 初值 False→True | `test_tuple_key_repair_with_empty_first_string` | 字符串感知状态机对「空串/首字符转义」边界正确，元组键才能修复 |
| `helpers:cc058e223acc` | 叶子回退失败分支哨兵复位 False→True | `test_leaf_flag_resets_when_extraction_ultimately_fails` | 解析最终失败时哨兵必须复位 False（不得残留「发生过回退」的假标记） |
| `helpers:e6b7f907a2b1` | _repair_json_bounded 尾部 return cur→None | `test_bounded_repair_failure_raises_json_decode_error_not_type_error` | 修复轮次耗尽必须抛 json.JSONDecodeError（调用方降级契约），不得泄漏 TypeError |
| `helpers:f95a3a18c5c3` | _quote_tuple_keys_once 字符串闭合判定取反 | `test_tuple_key_repair_preserves_string_literal_content` | 元组键修复必须字符串感知（同 608205 契约的另一处状态机分支） |
| `helpers:383bf2851ceb` | 叶子回退「次新候选」logger.warning 文本整体改写（诊断文本变异） | `test_second_newest_leaf_fallback_sets_flag; test_tail_scan_fallback_returns_later_fragment_and_sets_flag` | 【间接击杀，机制如实披露】改写后的格式串不含占位符但调用仍传参 → 在会格式化日志记录的运行环境（pytest logging 捕获）触发 TypeError，调用方观测到异常而非返回字典；未断言日志消息文本，属诊断文本变异在测试运行环境下的可观测崩溃（非「公开契约外」硬杀） |

> 每个击杀均在「临时沙箱副本 × 单变异体 × L 轮测试文件」预验证 rc==1，
> 且 L 轮测试文件在未变异工作树全绿；工作树 `src/` 零改动。

## 4. 仍存活变异体归因（38 个）

| 类别 | 数量 | 说明 |
| --- | ---: | --- |
| 可证明等价（annotation-only） | 5 | K 轮既有：注解在 `from __future__ import annotations` 下运行期从不求值 |
| 强证据实践等价 | 28 | K 轮 17 + L 轮 11（机制见下表） |
| 公开契约外（内部诊断文本） | 5 | K 轮 5（L 轮 383b 因日志格式化 TypeError 转为间接击杀） |
| 待补（未构造出可杀输入） | 0 | L 轮已清空：23 个「待补」中 12 击杀（11 直接 + 1 间接）、11 归因等价 |

### 4.1 L 轮新增「强证据实践等价」（11 个）

判定证据 = 机制论证 + 确定性公开 API 差分探测零差异（20,200 输入 × 2 API，
见 `verify_equivalent_mutants.py`，固定种子 20261017）。

| 变异体 | 等价机制 |
| --- | --- |
| `helpers:1567052b264f` | extract_json_object 首对象修复环 continue→break：该环在可修复片段上不可达（可修复/可解析片段必然先被主链同候选集返回；差分语料零差异） |
| `helpers:499e052e17f3` | _first_balanced_object 字符串闭合判定取反：唯一调用点即上述不可达修复环，公开面不可观测 |
| `helpers:969a4fdc693d` | _first_balanced_object 开引号判定改写：唯一调用点即上述不可达修复环，公开面不可观测 |
| `helpers:b96d0e079983` | 删除 extract_json_object 首对象修复环整段：环不可达，等价于死代码删除 |
| `helpers:4b692477a69f` | _safe_eval Mult 首分支 and→or：正则文法保证 Mult 左操作数恒为 str、右操作数恒为 int（非 bool），首分支恒真，elif/else 不可达 |
| `helpers:9d7b56bee4bd` | _safe_eval Mult 次分支 and→or：同上，次分支与 else 在匹配文法下不可达 |
| `helpers:90f214353202` | _quote_python_expressions 非 str 守卫删除：匹配文法下 _safe_eval 恒返回 str，守卫空转 |
| `helpers:b7e3f4dfe70b` | _normalize 结果类型守卫 or→and：求值成功值恒为 int/float 且非 bool，守卫空转 |
| `helpers:fdaf4935266c` | 合法 JSON 数字早退守卫取反：回退路径对整数重序列化文本等价（解析值相同；'-0'→'0' 同值） |
| `helpers:5e361b2a0469` | raw 快路径 start 守卫取反（等价于禁用快路径）：合法片段直解析与主链同片段同结果，纯性能路径 |
| `helpers:708a96fb4c79` | raw 快路径 opener 分派取反（等价于禁用快路径）：同上，公开输出零差异 |

### 4.2 L 轮新增「公开契约外」（0 个；383b 转为间接击杀）


### 4.3 K 轮既有存活归因（延续）

- annotation-only 5 个、强证据实践等价 17 个、公开契约外 5 个：逐条见
  `experiments/results/self_mutation_20261017/survivor_attribution.md`；本 L 轮 JSON
  已把全部存活逐条机器化归因（`survivor_attribution`）。

## 5. 验证命令（本机实测）

```bash
# L 轮新增测试 + K 轮击杀测试 + 工具测试 全绿
.venv/bin/python -m pytest tests/test_self_mutation_survivors_l.py tests/test_self_mutation_targets.py tests/test_self_mutation_tool.py -q

# 12 个击杀变异体的沙箱逐条预验证（临时副本，不动工作树）
.venv/bin/python experiments/results/self_mutation_l_round/verify_kills_sandbox.py

# 11 个实践等价变异体的公开 API 差分探测（零差异）
.venv/bin/python experiments/results/self_mutation_l_round/verify_equivalent_mutants.py

# 孤儿进程巡检（只读）
.venv/bin/python scripts/tools/detect_orphan_procs.py --json
```

## 6. 限制与披露

1. **抽样分数**：helpers 120/468（25.6%）等距抽样，合计分数是抽样点估计，不写成全量 mutation score；
   采样确定性（无随机种子，按源码行+类型排序等距）保证 before/after 变异体 ID 逐项可对账。
2. **不硬杀**：11 个实践等价变异体如实保留存活并归因；未使用「断言私有属性/具体错误消息/随机值」的脆弱测试。
   383b（诊断文本）为**间接击杀**：变异后的 logger 格式串与参数不匹配，在 pytest 日志捕获下
   触发 TypeError——归因表如实注明该机制，未断言任何日志文本。
3. **行为导向**：所有新测试只调用公开 API（`extract_json_object` / `extract_json_array` /
   `was_leaf_fallback_used`），不 monkeypatch 被测实现、不读取私有函数。
4. **CPU 竞争**：after 复跑在 L 轮跑批窗口结束后执行；timeout 单列不进分母
   （K 轮既有的 aug_assign_swap timeout 未复活）。

