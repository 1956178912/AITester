# 击杀后剩余存活变异体归因（2026-10-17，WP-A）

> 事实源：`self_mutation_report.json`（击杀前基线）与 `self_mutation_after.json`（追加 `tests/test_self_mutation_targets.py` 后复跑）。
> **两次运行使用同一生成器快照、同一工作树、同一抽样口径，变异体 ID 集合逐项相同（224/224 对账一致）**，改动面只有测试集合（多了击杀测试文件）。
> 本文件对第 2 轮后仍存活的变异体逐条归因；**不把「等价变异体」计入测试缺陷**，也不把「未构造出可观测差异」冒充「已证明等价」——两类分开披露。

## 1. 口径

- **可证明等价**：变异只改 type annotation，而模块启用 `from __future__ import annotations`（注解除引用，运行期从未求值）→ 行为逐字节恒等；
- **强证据实践等价**：变异改变死代码/冗余防御/被超集分支覆盖的路径，机制可解释，且 100 组公开 API 差分输入 corpus 零差异；
- **公开契约外**：变异改内部异常类型/消息/诊断字段，公开契约只承诺 `json.JSONDecodeError`或调用方捕获后不可观测——按「不把实现细节固化为测试契约」原则**不纳入击杀口径**，也不算等价；
- **待补（未构造出可杀输入）**：防御性字符串感知/叶子回退/表达式求值分支，公开 API 差分探测未命中差异；本批未击杀，**不声称等价**，后续可用更强输入生成补齐。

## 2. 第 2 轮已击杀（27 个，全部 survived→killed）

| 变异体（基线 ID） | 变异语义 | 击杀测试 |
| --- | --- | --- |
| `atomic_io:16db84aa5293` | line 47: -X → X（一元负号移除） | `test_atomic_write_mkstemp_failure_does_not_close_arbitrary_fd` |
| `atomic_io:49d3118af77d` | line 84: 字符串常量 'atomic_write_text' → 'xxxxxxxxxxxxxxxxx' | `test_atomic_io_public_api_surface_is_exact` |
| `atomic_io:6234f51035a5` | line 69: 字符串常量 'U4 atomic_write 临时文件清理失败（忽略）: %s' → 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' | `test_atomic_write_cleanup_failure_leaves_identifiable_temp` |
| `atomic_io:7c7574163adb` | line 84: 字符串常量 'atomic_write_json' → 'xxxxxxxxxxxxxxxxx' | `test_atomic_io_public_api_surface_is_exact` |
| `atomic_io:7e5948d1dd26` | line 50: 字符串常量 '.aitester_tmp_' → 'xxxxxxxxxxxxxx' | `test_atomic_write_cleanup_failure_leaves_identifiable_temp` |
| `atomic_io:bd21a0d242d4` | line 46: or → and（布尔互换） | `test_atomic_write_cleanup_failure_leaves_identifiable_temp` |
| `atomic_io:ce5570ddbcb3` | line 47: 删除语句（语句删除变异） | `test_atomic_write_mkstemp_failure_does_not_close_arbitrary_fd` |
| `atomic_io:e5a5b2e08868` | line 48: 删除语句（语句删除变异） | `test_atomic_write_mkstemp_failure_does_not_close_arbitrary_fd` |
| `atomic_io:fcd9305bde69` | line 50: 字符串常量 '.tmp' → 'xxxx' | `test_atomic_write_cleanup_failure_leaves_identifiable_temp` |
| `env_utils:817f4edcb8c2` | line 178: Lt → LtE（边界变异） | `test_env_int_lo_boundary_is_inclusive` |
| `env_utils:ca9e2bbd415b` | line 215: Gt → GtE（边界变异） | `test_env_float_hi_boundary_is_inclusive` |
| `env_utils:d8ac3d59d51d` | line 215: Lt → LtE（边界变异） | `test_env_float_lo_boundary_is_inclusive` |
| `env_utils:f3afbc06be0a` | line 178: Gt → GtE（边界变异） | `test_env_int_hi_boundary_is_inclusive` |
| `helpers:0c832ebf6a0b` | line 225: 字符串常量 '(' → 'x' | `test_extract_json_object_quotes_python_tuple_keys` |
| `helpers:25585de66de3` | line 461: 字符串常量 'eval' → 'xxxx' | `test_extract_json_object_evaluates_python_string_expressions` |
| `helpers:28f3e7623b5a` | line 458: 字符串常量 '\n' → 'x' | `test_extract_json_object_evaluates_python_string_expressions` |
| `helpers:2a79bf382145` | line 162: 字符串常量 'False' → 'xxxxx' | `test_extract_json_object_repairs_python_false_literal` |
| `helpers:2b2a44279380` | line 91: 删除语句（语句删除变异） | `test_extract_code_block_honors_requested_language_fence` |
| `helpers:523affeeda57` | line 237: X → not X（比较前插 not） | `test_extract_json_object_quotes_python_tuple_keys` |
| `helpers:6c54ca18b2f5` | line 431: 删除语句（语句删除变异） | `test_extract_json_object_evaluates_python_string_expressions` |
| `helpers:814062761ac7` | line 235: 条件取反（not） | `test_extract_json_object_quotes_python_tuple_keys` |
| `helpers:85f51aab993f` | line 419: X → not X（比较前插 not） | `test_extract_json_object_evaluates_python_string_expressions` |
| `helpers:983effa31ffa` | line 453: return out → return None | `test_extract_json_object_evaluates_python_string_expressions` |
| `helpers:a115c7e267c4` | line 256: 删除语句（语句删除变异） | `test_extract_json_object_quotes_python_tuple_keys` |
| `helpers:c1b8b5ba8a7a` | line 436: and → or（布尔互换） | `test_extract_json_object_evaluates_python_string_expressions` |
| `helpers:d0872864317d` | line 221: 字符串常量 '([{,]\\s*)\\((\\s*-?\\d+(?:\\s*,\\s*-?\\d+)+)\\)(\\s*:)' → 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' | `test_extract_json_object_quotes_python_tuple_keys` |
| `helpers:f6ee52d99960` | line 258: continue → break（循环控制变异） | `test_extract_json_object_quotes_python_tuple_keys` |

> 每个击杀均先在「单变异体 × 目标测试集合」沙箱里预验证 `rc==1`，再用于正式 after 复跑；对应测试在未变异代码上全绿（green baseline 前置校验通过）。

## 3. 剩余存活归因（50 个）

### 3.1 可证明等价（5 个）：annotation-only

`from __future__ import annotations` 使注解仅在编译期保留为字符串，运行期从不求值；变异只改写注解表达式，对公开 API 行为零影响。

| 变异体 ID | 变异的注解 |
| --- | --- |
| `env_utils:64503fd89fd3` | `_DEFAULT_TRUE: tuple[str, ...]` 注解被取反 |
| `env_utils:d878f6d742fa` | `_DEFAULT_OFF: tuple[str, ...]` 注解被取反 |
| `env_utils:e45234decf0a` | `env_flag_opt_out(..., off_values: tuple[str, ...] | None)` 注解被取反 |
| `env_utils:f4f329f903f1` | `env_flag(..., extra_true: tuple[str, ...])` 注解被取反 |
| `helpers:1f497e6d172a` | `prev_match: re.Match[str] | None` 局部变量注解被取反 |

### 3.2 强证据实践等价（17 个）

| 变异体 ID | 变异语义 | 等价机制 |
| --- | --- | --- |
| `atomic_io:1cd56015792b` | line 46: 字符串常量 '.' → 'x' | `dirname(abspath(path)) or "."` 的 `"."` 被改写：abspath 后 dirname 恒非空 → 右侧死代码 |
| `atomic_io:1e70830a0a5a` | line 62: const 0 → +1 | `if fd >= 0` → `fd >= 1`：mkstemp 返回 fd 恒 ≥3（stdio 占 0/1/2），fd==0 分支正常进程不可达 |
| `atomic_io:3d86e2a8cfa5` | line 51: 字符串常量 'w' → 'x' | `os.fdopen(fd, "w")` → `"x"`：fdopen 对已打开 fd 忽略创建语义（Python 3.14 实测相同） |
| `atomic_io:d1ee323e21c3` | line 62: GtE → Gt（边界变异） | `if fd >= 0` → `fd > 0`：同上 |
| `helpers:076b4fb6bd68` | line 24: 字符串常量 '```python\\s*\\n(.*?)\\n\\s*```' → 'xxxxxxxxxxxxxxxxxxxxxxxxxxx' | `_CODE_BLOCK_PYTHON_PATTERN` 被改写：下一档 `_CODE_BLOCK_PATTERN` 是其超集，同输入同结果 |
| `helpers:181ced4c9a27` | line 585: return value if isinstance(value, expected_type) else None → return None | `_try_parse_raw_json` 返回值 → None：快路径失败后修复链对同输入仍产出相同结果 |
| `helpers:1fbc17a82a71` | line 498: 删除语句（语句删除变异） | 删除同一越界守卫：越界输入在后续切分路径同样得 None（差分探测零差异） |
| `helpers:2676fb402fc5` | line 625: 移除 raise json.JSONDecodeError('No JSON array found in response', text or '', 0)（异常路径变异） | 删除 `if start == -1` 分支的早期 JSONDecodeError：后续兜底 raise 同类型异常，公开契约不变 |
| `helpers:380f944f4d05` | line 469: False → True（常量置换） | `json.dumps(..., ensure_ascii=False)` → `True`：仅 JSON 文本转义表示差异，解析后的字符串值相同 |
| `helpers:48aefe5bc7c2` | line 630: 删除语句（语句删除变异） | 删除 `if _fast is not None: return _fast`：同上（数组快路径被绕过，修复链兜底同结果） |
| `helpers:6e7072a0ce66` | line 634: 删除语句（语句删除变异） | 删除 `_JSON_BACKTICK_STRIP_PATTERN.sub`：与 `_JSON_FENCE_STRIP_PATTERN` 冗余，围栏行已被前一条剥离 |
| `helpers:8f110b11781a` | line 164: 字符串常量 'NaN' → 'xxx' | 修复表 `'NaN'` 被改写：`json.loads` 原生接受 NaN 字面量（raw 快路径先行），修复档映射未被公开输入触发差异 |
| `helpers:d4e24d830a4e` | line 533: 删除语句（语句删除变异） | 删除函数尾部 `return None`：Python 尾部隐式返回 None，逐字节恒等 |
| `helpers:df6a1908286d` | line 742: continue → break（循环控制变异） | 搜索循环 `continue` → `break`：该循环最多命中一个候选，提前终止与继续扫描结果一致 |
| `helpers:dfceeed070e0` | line 714: 字符串常量 '{' → 'x' | 对象快路径首字符 `'{'` 被改写：慢速修复链兜底同结果 |
| `helpers:f024186d57c1` | line 498: GtE → Gt（边界变异） | balanced 搜索越界守卫 `>=` → `>`：`start == len(text)` 时后续循环无字符可匹配，同样返回 None |
| `helpers:fc7613504be5` | line 47: 字符串常量 '(?m)^[ \\t]*```[ \\t]*\\r?\\n?' → 'xxxxxxxxxxxxxxxxxxxxxxxxxx' | `_JSON_BACKTICK_STRIP_PATTERN` 被改写：前一条 `_JSON_FENCE_STRIP_PATTERN` 已覆盖同一围栏行集合（幂等叠加） |

### 3.3 公开契约外（5 个）：内部异常细节 / 诊断字段

| 变异体 ID | 变异语义 |
| --- | --- |
| `helpers:114f04d5d4a0` | `TypeError('unsupported pow operands (int-only)')` 消息被改写（调用方捕获后不可观测） |
| `helpers:8011133ca57c` | `TypeError(f'unsupported node ...')` 消息前缀被改写（同上） |
| `helpers:9716aa32b00c` | 私有 `_quote_python_expressions` 内 `TypeError` → `ValueError`（公开契约只承诺 JSONDecodeError） |
| `helpers:99254d5ff306` | `TypeError('non-numeric operand')` 消息被改写（同上） |
| `helpers:9da8ba489b67` | 删除 `raise TypeError('unsupported mult operands')` → `pass`：后续路径同样降级/抛错，公开结果一致 |

### 3.4 待补：未构造出可杀输入的防御分支（23 个）

这些分支防御的是 LLM 畸形输出（字符串状态感知 / 叶子回退 / Python 表达式求值守卫）；本次 100 组差分输入 corpus 未观测到公开行为差异。**不声称等价**，要观测它们需构造更极端的畸形输入（成本高于本批收益），属后续可补项。

| 变异体 ID | 所属防御面 | 变异语义 |
| --- | --- | --- |
| `helpers:1567052b264f` | `_repair_json_bounded` 循环控制 continue→break | line 768: continue → break（循环控制变异） |
| `helpers:29836f6132a3` | `_repair_json_bounded` 循环控制 continue→break | line 654: continue → break（循环控制变异） |
| `helpers:383bf2851ceb` | 叶子回退 WARNING 文本被整体改写 | line 813: 字符串常量 'JSON 提取叶子回退（次新候选）：返回倒数第二内层片段（len=%d）' → 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' |
| `helpers:396a28db8ca8` | `_quote_python_expressions` 快路径守卫 `or` → `and` | line 458: or → and（布尔互换） |
| `helpers:499e052e17f3` | `_first_balanced_object` 字符串段判定取反 | line 185: X → not X（比较前插 not） |
| `helpers:4b692477a69f` | 字符串拼接守卫 `and` → `or` | line 439: and → or（布尔互换） |
| `helpers:5e361b2a0469` | 平衡对象入口守卫 `start == -1` 取反 | line 576: X → not X（比较前插 not） |
| `helpers:5f59874830d1` | `_find_balanced_object` 闭合符 `"}"` → `"x"` | line 857: 字符串常量 '}' → 'x' |
| `helpers:5f886043809a` | 叶子回退哨兵置位 `_LEAF_FALLBACK_ACTIVE = True` → False | line 827: True → False（常量置换） |
| `helpers:608205e3bd2f` | `_first_balanced_object` 字符串段判定常量被改写 | line 244: 字符串常量 '"' → 'x' |
| `helpers:708a96fb4c79` | 平衡对象 opener 分派 `opener == '{'` 取反 | line 578: X → not X（比较前插 not） |
| `helpers:90f214353202` | 私有 `_repl` 删除 `return m.group(0)`/类型守卫语句 | line 465: 删除语句（语句删除变异） |
| `helpers:925bf0576cf6` | 数值位数上限边界 `len(str(val)) > _MAX_NUMERIC_DIGITS` → `>=` | line 366: Gt → GtE（边界变异） |
| `helpers:969a4fdc693d` | `_first_balanced_object` 字符串段判定常量被改写 | line 188: 字符串常量 '"' → 'x' |
| `helpers:9d7b56bee4bd` | 反向拼接守卫 `and` → `or` | line 441: and → or（布尔互换） |
| `helpers:a3ee749e3485` | 叶子回退候选选择边界 `len(tail_matches) > 2` → `> 3` | line 824: const 2 → +1 |
| `helpers:a93688ca6eb0` | `_first_balanced_object` 转义状态初始值 False → True | line 231: False → True（常量置换） |
| `helpers:b7e3f4dfe70b` | 私有 `_repl` 的 bool 判定 `or` → `and` | line 364: or → and（布尔互换） |
| `helpers:b96d0e079983` | `extract_json_object` 叶子回退候选修复分支被删除 | line 755: 删除语句（语句删除变异） |
| `helpers:cc058e223acc` | 叶子回退哨兵复位 `_LEAF_FALLBACK_ACTIVE = False` → True | line 808: False → True（常量置换） |
| `helpers:e6b7f907a2b1` | `_repair_json_bounded` 循环返回 `cur` → None | line 395: return cur → return None |
| `helpers:f95a3a18c5c3` | `_first_balanced_object` 字符串段判定取反 | line 239: X → not X（比较前插 not） |
| `helpers:fdaf4935266c` | JSON 值 bool 判定 `not isinstance(jv, bool)` 取反 | line 353: not X → X |

## 4. 统计

| 类别 | 数量 |
| --- | ---: |
| 基线 survived（击杀前） | 77 |
| 第 2 轮击杀（survived→killed） | 27 |
| 剩余存活 | 50 |
| — 可证明等价（annotation-only） | 5 |
| — 强证据实践等价 | 17 |
| — 公开契约外（内部异常/诊断） | 5 |
| — 待补（未构造出可观测差异，不声称等价） | 23 |

**结论**：第 2 轮后剩余 50 个存活变异体中，22 个有等价性证据、5 个属公开契约外内部细节、23 个是防御性残缺输入分支（本批未补）。所有未击杀项均不改变 `killed/(killed+survived)` 分子，也不应据此推断对应代码「测试薄弱」——它们多数是为 LLM 畸形输出准备的冗余防御层。
