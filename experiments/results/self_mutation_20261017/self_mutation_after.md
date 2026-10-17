# 自身测试套件变异测试报告（self-mutation）

> 机器可读事实源为同名 JSON；本文件是其可读镜像。所有数字由
> `scripts/tools/self_mutation.py` 实测产出，复现命令见文末。

## 测量口径

- mutation score = killed / (killed + survived)；invalid/timeout **不进分母**。
- rc 分类：rc==1 killed、rc==0 survived、rc==2/3/4/5 或超时 invalid。
- 变异在 tempfile 临时副本中进行，工作树零改动；子进程 pytest 经
  `nested_pytest_env` 隔离宿主配置、经 `run_with_timeout` 整树超时终止。
- 基线（未变异副本）执行结果单列于各模块 `baseline`，红基线默认阻断。
- 抽样前先剔除**生成器无效**变异体：语义恒等（identity，与源码 AST 逐节点相同）与语法非法（syntax_error）——前者计入分母会把生成器缺陷误判成测试弱，后者不可执行。剔除数量逐模块披露于 `generator_filtered`；抽样率按可执行池披露。

## 运行环境

- 生成时间：2026-10-17T17:24:44+0800；总耗时：322.154s；模式：`execute`
- 主机：WangChenyudeMacBook-Air.local / macOS-27.0.1-arm64-arm-64bit-Mach-O / CPU 10 核
- Python：3.14.6（/Users/wangchenyu/Workspace/AITester/.venv/bin/python）；pytest：9.1.1
- git：sha=`362bf0221fa89c298f52e4faf3713ab84b20b37f`，dirty=True（82 个未提交变更）
- worker：2；每变异体超时：60.0s；每文件变异体上限：120（0=全量）
- 测试命令模板：`{python} -m pytest {test_files} -q --tb=no -x -p no:cacheprovider -o addopts=`；样本量口径：等距抽样（按源码行号+变异类型排序；0=全量）

## 总览

| 模块 | 生成 | 过滤(恒等/语法) | 可执行池 | 抽样执行 | killed | survived | invalid | timeout | mutation score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `src/utils/env_utils.py` | 83 | 0/0 | 83 | 83 | 71 | 4 | 8 | 0 | 0.9467 |
| `src/utils/helpers.py` | 468 | 0/0 | 468 | 120 | 77 | 42 | 0 | 1 | 0.6471 |
| `src/utils/atomic_io.py` | 21 | 0/0 | 21 | 21 | 17 | 4 | 0 | 0 | 0.8095 |
| **合计** | 572 | 0/0 | 572 | 224 | 165 | 50 | 8 | 1 | **0.7674** |

- 测量有效性：baseline_green=True，measurement_valid=True；有效分母（killed+survived）=215

## 分模块明细

### `src/utils/env_utils.py`

- 源码 sha256：`58acf13b308e3851…`（64 位）
- 测试集合：`tests/test_env_utils.py`, `tests/test_self_mutation_targets.py`
- 基线（未变异）：green=True，rc=0，2.293s
- 生成 83，其中生成器无效被剔除 0 个恒等 + 0 个语法非法；可执行池 83，抽样执行 83，mutation score = **0.9467**

| 变异类型 | killed | survived | invalid | timeout | score |
| --- | ---: | ---: | ---: | ---: | ---: |
| arith_op_swap | 1 | 0 | 0 | 0 | 1.0000 |
| bool_op_swap | 7 | 0 | 1 | 0 | 1.0000 |
| boolean_negation | 3 | 0 | 0 | 0 | 1.0000 |
| boundary_shift | 4 | 0 | 0 | 0 | 1.0000 |
| cond_negate | 4 | 0 | 1 | 0 | 1.0000 |
| const_swap | 2 | 0 | 0 | 0 | 1.0000 |
| return_empty | 1 | 0 | 0 | 0 | 1.0000 |
| return_void | 10 | 0 | 0 | 0 | 1.0000 |
| stmt_delete | 15 | 0 | 4 | 0 | 1.0000 |
| string_const_swap | 11 | 0 | 0 | 0 | 1.0000 |
| subscript_negate | 0 | 4 | 0 | 0 | 0.0000 |
| unary_not_insert | 13 | 0 | 2 | 0 | 1.0000 |

**存活变异体（4 个，待击杀/归因）**：

| mutant_id | 行号 | 类型 | 描述 |
| --- | ---: | --- | --- |
| `env_utils:64503fd89fd3` | 70 | subscript_negate | line 70: 下标取反（序列边界） |
| `env_utils:d878f6d742fa` | 74 | subscript_negate | line 74: 下标取反（序列边界） |
| `env_utils:f4f329f903f1` | 77 | subscript_negate | line 77: 下标取反（序列边界） |
| `env_utils:e45234decf0a` | 101 | subscript_negate | line 101: 下标取反（序列边界） |

**invalid / timeout（8 个，不进分母）**：

| mutant_id | 行号 | 结果 | 原因 |
| --- | ---: | --- | --- |
| `env_utils:c166e1c2f988` | 95 | invalid | usage_error(rc=4) |
| `env_utils:6c84a485afe8` | 171 | invalid | usage_error(rc=4) |
| `env_utils:a8fb1a40dd3f` | 94 | invalid | usage_error(rc=4) |
| `env_utils:38accdbf7a89` | 95 | invalid | usage_error(rc=4) |
| `env_utils:4d5ecd796b9f` | 170 | invalid | usage_error(rc=4) |
| `env_utils:e9232891b337` | 171 | invalid | usage_error(rc=4) |
| `env_utils:5ba0487ddae3` | 171 | invalid | usage_error(rc=4) |
| `env_utils:12c2a8a687bc` | 171 | invalid | usage_error(rc=4) |

### `src/utils/helpers.py`

- 源码 sha256：`0a1f6e1af167db9d…`（64 位）
- 测试集合：`tests/test_helpers_json_fence_content.py`, `tests/test_helpers_json_property.py`, `tests/test_helpers_json_robustness.py`, `tests/test_self_mutation_targets.py`
- 基线（未变异）：green=True，rc=0，4.247s
- 生成 468，其中生成器无效被剔除 0 个恒等 + 0 个语法非法；可执行池 468，抽样执行 120，mutation score = **0.6471**

| 变异类型 | killed | survived | invalid | timeout | score |
| --- | ---: | ---: | ---: | ---: | ---: |
| arith_op_swap | 3 | 0 | 0 | 0 | 1.0000 |
| aug_assign_swap | 0 | 0 | 0 | 1 | n/a |
| bool_op_swap | 2 | 4 | 0 | 0 | 0.3333 |
| boolean_negation | 2 | 1 | 0 | 0 | 0.6667 |
| boundary_shift | 1 | 2 | 0 | 0 | 0.3333 |
| break_continue_swap | 1 | 3 | 0 | 0 | 0.2500 |
| cond_negate | 9 | 0 | 0 | 0 | 1.0000 |
| const_swap | 0 | 4 | 0 | 0 | 0.0000 |
| exception_remove | 1 | 2 | 0 | 0 | 0.3333 |
| exception_type_swap | 0 | 1 | 0 | 0 | 0.0000 |
| numeric_offset | 1 | 1 | 0 | 0 | 0.5000 |
| operator_flip | 7 | 0 | 0 | 0 | 1.0000 |
| return_void | 8 | 2 | 0 | 0 | 0.8000 |
| stmt_delete | 22 | 6 | 0 | 0 | 0.7857 |
| string_const_swap | 9 | 11 | 0 | 0 | 0.4500 |
| subscript_negate | 1 | 1 | 0 | 0 | 0.5000 |
| unary_not_insert | 10 | 4 | 0 | 0 | 0.7143 |

**存活变异体（42 个，待击杀/归因）**：

| mutant_id | 行号 | 类型 | 描述 |
| --- | ---: | --- | --- |
| `helpers:076b4fb6bd68` | 24 | string_const_swap | line 24: 字符串常量 '```python\\s*\\n(.*?)\\n\\s*```' → 'xxxxxxxxxxxxxxxxxxxxxxxxxxx' |
| `helpers:fc7613504be5` | 47 | string_const_swap | line 47: 字符串常量 '(?m)^[ \\t]*```[ \\t]*\\r?\\n?' → 'xxxxxxxxxxxxxxxxxxxxxxxxxx' |
| `helpers:8f110b11781a` | 164 | string_const_swap | line 164: 字符串常量 'NaN' → 'xxx' |
| `helpers:499e052e17f3` | 185 | unary_not_insert | line 185: X → not X（比较前插 not） |
| `helpers:969a4fdc693d` | 188 | string_const_swap | line 188: 字符串常量 '"' → 'x' |
| `helpers:a93688ca6eb0` | 231 | const_swap | line 231: False → True（常量置换） |
| `helpers:f95a3a18c5c3` | 239 | unary_not_insert | line 239: X → not X（比较前插 not） |
| `helpers:608205e3bd2f` | 244 | string_const_swap | line 244: 字符串常量 '"' → 'x' |
| `helpers:99254d5ff306` | 323 | string_const_swap | line 323: 字符串常量 'non-numeric operand' → 'xxxxxxxxxxxxxxxxxxx' |
| `helpers:114f04d5d4a0` | 326 | string_const_swap | line 326: 字符串常量 'unsupported pow operands (int-only)' → 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' |
| `helpers:fdaf4935266c` | 353 | boolean_negation | line 353: not X → X |
| `helpers:b7e3f4dfe70b` | 364 | bool_op_swap | line 364: or → and（布尔互换） |
| `helpers:925bf0576cf6` | 366 | boundary_shift | line 366: Gt → GtE（边界变异） |
| `helpers:e6b7f907a2b1` | 395 | return_void | line 395: return cur → return None |
| `helpers:4b692477a69f` | 439 | bool_op_swap | line 439: and → or（布尔互换） |
| `helpers:9d7b56bee4bd` | 441 | bool_op_swap | line 441: and → or（布尔互换） |
| `helpers:9da8ba489b67` | 444 | exception_remove | line 444: 移除 raise TypeError('unsupported mult operands')（异常路径变异） |
| `helpers:9716aa32b00c` | 446 | exception_type_swap | line 446: raise TypeError → raise ValueError（异常类型变异） |
| `helpers:8011133ca57c` | 454 | string_const_swap | line 454: 字符串常量 'unsupported node ' → 'xxxxxxxxxxxxxxxxx' |
| `helpers:396a28db8ca8` | 458 | bool_op_swap | line 458: or → and（布尔互换） |
| `helpers:90f214353202` | 465 | stmt_delete | line 465: 删除语句（语句删除变异） |
| `helpers:380f944f4d05` | 469 | const_swap | line 469: False → True（常量置换） |
| `helpers:f024186d57c1` | 498 | boundary_shift | line 498: GtE → Gt（边界变异） |
| `helpers:1fbc17a82a71` | 498 | stmt_delete | line 498: 删除语句（语句删除变异） |
| `helpers:d4e24d830a4e` | 533 | stmt_delete | line 533: 删除语句（语句删除变异） |
| `helpers:5e361b2a0469` | 576 | unary_not_insert | line 576: X → not X（比较前插 not） |
| `helpers:708a96fb4c79` | 578 | unary_not_insert | line 578: X → not X（比较前插 not） |
| `helpers:181ced4c9a27` | 585 | return_void | line 585: return value if isinstance(value, expected_type) else None → return None |
| `helpers:2676fb402fc5` | 625 | exception_remove | line 625: 移除 raise json.JSONDecodeError('No JSON array found in response', text or '', 0)（异常路径变异） |
| `helpers:48aefe5bc7c2` | 630 | stmt_delete | line 630: 删除语句（语句删除变异） |
| `helpers:6e7072a0ce66` | 634 | stmt_delete | line 634: 删除语句（语句删除变异） |
| `helpers:29836f6132a3` | 654 | break_continue_swap | line 654: continue → break（循环控制变异） |
| `helpers:dfceeed070e0` | 714 | string_const_swap | line 714: 字符串常量 '{' → 'x' |
| `helpers:df6a1908286d` | 742 | break_continue_swap | line 742: continue → break（循环控制变异） |
| `helpers:b96d0e079983` | 755 | stmt_delete | line 755: 删除语句（语句删除变异） |
| `helpers:1567052b264f` | 768 | break_continue_swap | line 768: continue → break（循环控制变异） |
| `helpers:1f497e6d172a` | 785 | subscript_negate | line 785: 下标取反（序列边界） |
| `helpers:cc058e223acc` | 808 | const_swap | line 808: False → True（常量置换） |
| `helpers:383bf2851ceb` | 813 | string_const_swap | line 813: 字符串常量 'JSON 提取叶子回退（次新候选）：返回倒数第二内层片段（len=%d）' → 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' |
| `helpers:a3ee749e3485` | 824 | numeric_offset | line 824: const 2 → +1 |
| `helpers:5f886043809a` | 827 | const_swap | line 827: True → False（常量置换） |
| `helpers:5f59874830d1` | 857 | string_const_swap | line 857: 字符串常量 '}' → 'x' |

**invalid / timeout（1 个，不进分母）**：

| mutant_id | 行号 | 结果 | 原因 |
| --- | ---: | --- | --- |
| `helpers:c0e4a16c2e8a` | 512 | timeout | 超时：已 killpg 整树终止（单独记 invalid，不进分母） |

### `src/utils/atomic_io.py`

- 源码 sha256：`10e4367b63764415…`（64 位）
- 测试集合：`tests/test_atomic_io.py`, `tests/test_self_mutation_targets.py`
- 基线（未变异）：green=True，rc=0，1.626s
- 生成 21，其中生成器无效被剔除 0 个恒等 + 0 个语法非法；可执行池 21，抽样执行 21，mutation score = **0.8095**

| 变异类型 | killed | survived | invalid | timeout | score |
| --- | ---: | ---: | ---: | ---: | ---: |
| bool_op_swap | 1 | 0 | 0 | 0 | 1.0000 |
| boundary_shift | 0 | 1 | 0 | 0 | 0.0000 |
| const_swap | 1 | 0 | 0 | 0 | 1.0000 |
| numeric_offset | 0 | 1 | 0 | 0 | 0.0000 |
| stmt_delete | 4 | 0 | 0 | 0 | 1.0000 |
| string_const_swap | 6 | 2 | 0 | 0 | 0.7500 |
| unary_minus_remove | 2 | 0 | 0 | 0 | 1.0000 |
| unary_not_insert | 3 | 0 | 0 | 0 | 1.0000 |

**存活变异体（4 个，待击杀/归因）**：

| mutant_id | 行号 | 类型 | 描述 |
| --- | ---: | --- | --- |
| `atomic_io:1e70830a0a5a` | 62 | numeric_offset | line 62: const 0 → +1 |
| `atomic_io:d1ee323e21c3` | 62 | boundary_shift | line 62: GtE → Gt（边界变异） |
| `atomic_io:1cd56015792b` | 46 | string_const_swap | line 46: 字符串常量 '.' → 'x' |
| `atomic_io:3d86e2a8cfa5` | 51 | string_const_swap | line 51: 字符串常量 'w' → 'x' |

## 复现命令

```bash
/Users/wangchenyu/Workspace/AITester/.venv/bin/python scripts/tools/self_mutation.py --files src/utils/env_utils.py,src/utils/helpers.py,src/utils/atomic_io.py --workers 2 --max-mutants 120 --test-map src/utils/env_utils.py=tests/test_env_utils.py,tests/test_self_mutation_targets.py --test-map src/utils/helpers.py=tests/test_helpers_json_fence_content.py,tests/test_helpers_json_property.py,tests/test_helpers_json_robustness.py,tests/test_self_mutation_targets.py --test-map src/utils/atomic_io.py=tests/test_atomic_io.py,tests/test_self_mutation_targets.py --json-out experiments/results/self_mutation_20261017/self_mutation_after.json --md-out experiments/results/self_mutation_20261017/self_mutation_after.md
```

报告落点与测试文件/源码的 sha256 已记录在 JSON 中；同一工作树下重跑应得到相同的变异体集合与（在确定性测试前提下）相同的计数。
