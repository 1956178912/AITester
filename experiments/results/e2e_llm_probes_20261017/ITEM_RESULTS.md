# N-4 真实 LLM 重型功能探针：逐项观测汇总（脚本直出）

> 运行 20261017T150106Z；总墙钟 28.82min；总成本（标准价上界）≈ $0.046292
> 数字均来自各 item 的批次 JSON / 日志 / trace，不手写；结论与缺陷清单见 README.md。

| item | exit | 墙钟(s) | tokens | 成本($) | 行数 | stop_reason | trace 节点命中 |
|---|---|---|---|---|---|---|---|
| `01_logic_fullchain` | 0 | 356 | 29507 | 0.01563 | 3 | max_iterations | _should_debug, debugger, executor, generator, patch_applier, planner |
| `02_rag_enabled` | 0 | 395 | 20635 | 0.010637 | 2 | max_iterations, test_passed | _should_debug, debugger, executor, generator, patch_applier, planner |
| `03_cross_file` | 0 | 27 | 15280 | 0.008253 | 2 | test_passed | _should_debug, executor, generator, planner |
| `04_venv_executor` | 0 | 312 | 6802 | 0.003671 | 1 | max_iterations | _should_debug, debugger, executor, generator, patch_applier, planner |
| `05a_budget_usd` | 0 | 371 | 6757 | 0.003651 | 1 | max_iterations | _should_debug, debugger, executor, generator, patch_applier, planner |
| `05b_budget_tokens` | 0 | 12 | 3197 | 0.00159 | 1 | budget_exceeded | _should_debug, debugger, executor, generator, patch_applier, planner |
| `06_safe_profile` | 0 | 252 | 4520 | 0.00286 | 1 | max_iterations | _should_debug, debugger, executor, generator, patch_applier, planner |
| `07_oracle_smoke` | None | None | 0 | None | 0 | — | — |

## 逐项关键观测（字段恒 None / 路径进入证据）

### `01_logic_fullchain`

- exit=0，墙钟 356s，batches=1，rows=3
- tokens={'total_input_tokens': 21976, 'total_output_tokens': 7531, 'total_tokens': 29507, 'total_llm_calls': 11, 'total_cache_hits': 0, 'total_cache_avoided_tokens': 0}，成本≈$0.01563
- 字段 None/空计数：`detection_rate`=2，`repair_rate`=1，`false_fix_rate`=1，`stop_reason`=0，`diagnosis_present`=0，`patch_present`=0，`spec_compile_rate`=0，`spec_oracle_injected`=0，`spec_oracle_verdict`=0，`spec_expr_coverage`=0，`rag_stats`=3，`cross_file_deps`=3，`task_metadata_difficulty`=3
- trace：3 文件；节点事件计数={'planner': 3, 'generator': 4, 'executor': 7, '_should_debug': 7, 'debugger': 3, 'patch_applier': 3}
- 日志关键词命中：`venv`×3，`aitester_sandbox`×2，`RAG`×1，`trace`×1，`补丁`×3，`repair`×1
  - row `quixbugs__bitcount`：passed=False iterations=1 stop_reason=max_iterations diagnosis=✓ patch=✓ repair_history_len=1 spec_compile_rate=1.0 spec_oracle_injected=True spec_oracle_verdict=injected rag_stats=✗ cross_file_deps=None difficulty=None token_budget_capped=False
  - row `quixbugs__breadth_first_search`：passed=False iterations=1 stop_reason=max_iterations diagnosis=✓ patch=✓ repair_history_len=1 spec_compile_rate=1.0 spec_oracle_injected=True spec_oracle_verdict=injected rag_stats=✗ cross_file_deps=None difficulty=None token_budget_capped=False
  - row `quixbugs__breadth_first_search_test`：passed=False iterations=1 stop_reason=max_iterations diagnosis=✓ patch=✓ repair_history_len=1 spec_compile_rate=0.0 spec_oracle_injected=False spec_oracle_verdict=compiled_empty rag_stats=✗ cross_file_deps=None difficulty=None token_budget_capped=False
- 日志告警/错误样本：
  - `基准测试 [aitester]:   0%|          | 0/3 [00:00<?, ?task/s]executor_runtime：执行超时（>30s），已终止整个进程组并返回（文件后端，不会挂死）`
  - `测试执行超时（>30s）: Command '['/Users/wangchenyu/Workspace/AITester/.venv/bin/python', '-m', 'pytest', '/var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/aitester_sandbox_gu_c66y5/test_generated.py', '-v', '--tb=short', '--cov=/var/folders/pj/frxc6s715_x9x19hkk6pj2nh`
  - `executor_runtime：执行超时（>30s），已终止整个进程组并返回（文件后端，不会挂死）`
  - `测试执行超时（>30s）: Command '['/Users/wangchenyu/Workspace/AITester/.venv/bin/python', '-m', 'pytest', '/var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/aitester_sandbox_4xnm_z0t/test_generated.py', '-v', '--tb=short', '--cov=/var/folders/pj/frxc6s715_x9x19hkk6pj2nh`
  - `m1_metrics：执行超时（>120s），已终止整个进程组并返回（文件后端，不会挂死）`

### `02_rag_enabled`

- exit=0，墙钟 395s，batches=1，rows=2
- tokens={'total_input_tokens': 15694, 'total_output_tokens': 4941, 'total_tokens': 20635, 'total_llm_calls': 8, 'total_cache_hits': 0, 'total_cache_avoided_tokens': 0}，成本≈$0.010637
- 字段 None/空计数：`detection_rate`=1，`repair_rate`=1，`false_fix_rate`=1，`stop_reason`=0，`diagnosis_present`=0，`patch_present`=0，`spec_compile_rate`=0，`spec_oracle_injected`=0，`spec_oracle_verdict`=0，`spec_expr_coverage`=0，`rag_stats`=0，`cross_file_deps`=2，`task_metadata_difficulty`=2
- trace：2 文件；节点事件计数={'planner': 2, 'generator': 3, 'executor': 5, '_should_debug': 5, 'debugger': 2, 'patch_applier': 2}
- 日志关键词命中：`venv`×3，`aitester_sandbox`×2，`rag`×7，`RAG`×2，`不可用`×5，`trace`×1，`补丁`×1，`repair`×1
  - row `quixbugs__bitcount`：passed=False iterations=1 stop_reason=max_iterations diagnosis=✓ patch=✓ repair_history_len=1 spec_compile_rate=1.0 spec_oracle_injected=True spec_oracle_verdict=injected rag_stats=✓ cross_file_deps=None difficulty=None token_budget_capped=False
  - row `quixbugs__breadth_first_search`：passed=True iterations=1 stop_reason=test_passed diagnosis=✓ patch=✓ repair_history_len=1 spec_compile_rate=0.0 spec_oracle_injected=False spec_oracle_verdict=compiled_empty rag_stats=✓ cross_file_deps=None difficulty=None token_budget_capped=False
- 日志告警/错误样本：
  - `基准测试 [aitester]:   0%|          | 0/2 [00:00<?, ?task/s]executor_runtime：执行超时（>30s），已终止整个进程组并返回（文件后端，不会挂死）`
  - `测试执行超时（>30s）: Command '['/Users/wangchenyu/Workspace/AITester/.venv/bin/python', '-m', 'pytest', '/var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/aitester_sandbox_7lw4swsf/test_generated.py', '-v', '--tb=short', '--cov=/var/folders/pj/frxc6s715_x9x19hkk6pj2nh`
  - `m1_metrics：执行超时（>60s），已终止整个进程组并返回（文件后端，不会挂死）`
  - `executor_runtime：执行超时（>30s），已终止整个进程组并返回（文件后端，不会挂死）`
  - `测试执行超时（>30s）: Command '['/Users/wangchenyu/Workspace/AITester/.venv/bin/python', '-m', 'pytest', '/var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/aitester_sandbox_yifjqhtl/test_generated.py', '-v', '--tb=short', '--cov=/var/folders/pj/frxc6s715_x9x19hkk6pj2nh`

### `03_cross_file`

- exit=0，墙钟 27s，batches=1，rows=2
- tokens={'total_input_tokens': 11203, 'total_output_tokens': 4077, 'total_tokens': 15280, 'total_llm_calls': 6, 'total_cache_hits': 0, 'total_cache_avoided_tokens': 0}，成本≈$0.008253
- 字段 None/空计数：`detection_rate`=0，`repair_rate`=0，`false_fix_rate`=0，`stop_reason`=0，`diagnosis_present`=0，`patch_present`=0，`spec_compile_rate`=0，`spec_oracle_injected`=1，`spec_oracle_verdict`=0，`spec_expr_coverage`=0，`rag_stats`=2，`cross_file_deps`=2，`task_metadata_difficulty`=0
- trace：2 文件；节点事件计数={'planner': 2, 'generator': 4, 'executor': 4, '_should_debug': 4}
- 日志关键词命中：`venv`×1，`RAG`×1，`cross_file`×5，`跨文件`×1，`trace`×1
  - row `synthetic__task_0000`：passed=True iterations=0 stop_reason=test_passed diagnosis=✗ patch=✗ repair_history_len=0 spec_compile_rate=0.0 spec_oracle_injected=False spec_oracle_verdict=compiled_empty rag_stats=✗ cross_file_deps=None difficulty=3 token_budget_capped=False
  - row `synthetic__task_0001`：passed=True iterations=0 stop_reason=test_passed diagnosis=✗ patch=✗ repair_history_len=0 spec_compile_rate=1.0 spec_oracle_injected=None spec_oracle_verdict=not_attempted rag_stats=✗ cross_file_deps=None difficulty=3 token_budget_capped=False

### `04_venv_executor`

- exit=0，墙钟 312s，batches=1，rows=1
- tokens={'total_input_tokens': 4990, 'total_output_tokens': 1812, 'total_tokens': 6802, 'total_llm_calls': 3, 'total_cache_hits': 0, 'total_cache_avoided_tokens': 0}，成本≈$0.003671
- 字段 None/空计数：`detection_rate`=1，`repair_rate`=0，`false_fix_rate`=0，`stop_reason`=0，`diagnosis_present`=0，`patch_present`=0，`spec_compile_rate`=0，`spec_oracle_injected`=0，`spec_oracle_verdict`=0，`spec_expr_coverage`=0，`rag_stats`=1，`cross_file_deps`=1，`task_metadata_difficulty`=1
- trace：1 文件；节点事件计数={'planner': 1, 'generator': 1, 'executor': 2, '_should_debug': 2, 'debugger': 1, 'patch_applier': 1}
- 日志关键词命中：`venv`×9，`aitester_sandbox`×2，`RAG`×1，`trace`×1，`补丁`×1，`repair`×1
  - row `quixbugs__bitcount`：passed=False iterations=1 stop_reason=max_iterations diagnosis=✓ patch=✓ repair_history_len=1 spec_compile_rate=1.0 spec_oracle_injected=True spec_oracle_verdict=injected rag_stats=✗ cross_file_deps=None difficulty=None token_budget_capped=False
- 日志告警/错误样本：
  - `基准测试 [aitester]:   0%|          | 0/1 [00:00<?, ?task/s]executor_runtime：执行超时（>30s），已终止整个进程组并返回（文件后端，不会挂死）`
  - `测试执行超时（>30s）: Command '['/Users/wangchenyu/Workspace/AITester/.venv/bin/python', '-m', 'pytest', '/var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/aitester_sandbox_8i6yvfiq/test_generated.py', '-v', '--tb=short', '--cov=/var/folders/pj/frxc6s715_x9x19hkk6pj2nh`
  - `executor_runtime：执行超时（>30s），已终止整个进程组并返回（文件后端，不会挂死）`
  - `测试执行超时（>30s）: Command '['/Users/wangchenyu/Workspace/AITester/.venv/bin/python', '-m', 'pytest', '/var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/aitester_sandbox_vtj2jf5s/test_generated.py', '-v', '--tb=short', '--cov=/var/folders/pj/frxc6s715_x9x19hkk6pj2nh`
  - `m1_metrics：执行超时（>120s），已终止整个进程组并返回（文件后端，不会挂死）`

### `05a_budget_usd`

- exit=0，墙钟 371s，batches=1，rows=1
- tokens={'total_input_tokens': 4953, 'total_output_tokens': 1804, 'total_tokens': 6757, 'total_llm_calls': 3, 'total_cache_hits': 0, 'total_cache_avoided_tokens': 0}，成本≈$0.003651
- 字段 None/空计数：`detection_rate`=1，`repair_rate`=0，`false_fix_rate`=0，`stop_reason`=0，`diagnosis_present`=0，`patch_present`=0，`spec_compile_rate`=0，`spec_oracle_injected`=0，`spec_oracle_verdict`=0，`spec_expr_coverage`=0，`rag_stats`=1，`cross_file_deps`=1，`task_metadata_difficulty`=1
- trace：1 文件；节点事件计数={'planner': 1, 'generator': 1, 'executor': 2, '_should_debug': 2, 'debugger': 1, 'patch_applier': 1}
- 日志关键词命中：`venv`×3，`aitester_sandbox`×2，`RAG`×1，`预算`×1，`budget`×7，`trace`×1，`补丁`×1，`repair`×1
  - row `quixbugs__bitcount`：passed=False iterations=1 stop_reason=max_iterations diagnosis=✓ patch=✓ repair_history_len=1 spec_compile_rate=1.0 spec_oracle_injected=True spec_oracle_verdict=injected rag_stats=✗ cross_file_deps=None difficulty=None token_budget_capped=False
- 日志告警/错误样本：
  - `基准测试 [aitester]:   0%|          | 0/1 [00:00<?, ?task/s]executor_runtime：执行超时（>30s），已终止整个进程组并返回（文件后端，不会挂死）`
  - `测试执行超时（>30s）: Command '['/Users/wangchenyu/Workspace/AITester/.venv/bin/python', '-m', 'pytest', '/var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/aitester_sandbox_fv_3ql4d/test_generated.py', '-v', '--tb=short', '--cov=/var/folders/pj/frxc6s715_x9x19hkk6pj2nh`
  - `m1_metrics：执行超时（>60s），已终止整个进程组并返回（文件后端，不会挂死）`
  - `executor_runtime：执行超时（>30s），已终止整个进程组并返回（文件后端，不会挂死）`
  - `测试执行超时（>30s）: Command '['/Users/wangchenyu/Workspace/AITester/.venv/bin/python', '-m', 'pytest', '/var/folders/pj/frxc6s715_x9x19hkk6pj2nh0000gn/T/aitester_sandbox_x8qm27va/test_generated.py', '-v', '--tb=short', '--cov=/var/folders/pj/frxc6s715_x9x19hkk6pj2nh`

### `05b_budget_tokens`

- exit=0，墙钟 12s，batches=1，rows=1
- tokens={'total_input_tokens': 2496, 'total_output_tokens': 701, 'total_tokens': 3197, 'total_llm_calls': 1, 'total_cache_hits': 0, 'total_cache_avoided_tokens': 0}，成本≈$0.00159
- 字段 None/空计数：`detection_rate`=0，`repair_rate`=0，`false_fix_rate`=0，`stop_reason`=0，`diagnosis_present`=0，`patch_present`=0，`spec_compile_rate`=0，`spec_oracle_injected`=0，`spec_oracle_verdict`=0，`spec_expr_coverage`=0，`rag_stats`=1，`cross_file_deps`=1，`task_metadata_difficulty`=1
- trace：1 文件；节点事件计数={'planner': 1, 'generator': 1, 'executor': 2, '_should_debug': 2, 'debugger': 1, 'patch_applier': 1}
- 日志关键词命中：`venv`×1，`RAG`×1，`预算`×4，`超限`×1，`budget`×7，`降级`×1，`trace`×1，`repair`×1
  - row `quixbugs__bitcount`：passed=False iterations=1 stop_reason=budget_exceeded diagnosis=✓ patch=✗ repair_history_len=1 spec_compile_rate=1.0 spec_oracle_injected=True spec_oracle_verdict=injected rag_stats=✗ cross_file_deps=None difficulty=None token_budget_capped=True
- 日志告警/错误样本：
  - `Generator LLM 调用失败（5.4 预算封顶），降级为空测试: LLM 预算耗尽：已消耗 3197 tokens >= 上限 100 tokens`
  - `第 1 次执行失败，尝试重试...`
  - `第 2 次执行失败，尝试重试...`
  - `第 1 次执行失败，尝试重试...`
  - `第 2 次执行失败，尝试重试...`

### `06_safe_profile`

- exit=0，墙钟 252s，batches=1，rows=1
- tokens={'total_input_tokens': 2849, 'total_output_tokens': 1671, 'total_tokens': 4520, 'total_llm_calls': 3, 'total_cache_hits': 0, 'total_cache_avoided_tokens': 0}，成本≈$0.00286
- 字段 None/空计数：`detection_rate`=1，`repair_rate`=0，`false_fix_rate`=0，`stop_reason`=0，`diagnosis_present`=0，`patch_present`=0，`spec_compile_rate`=1，`spec_oracle_injected`=1，`spec_oracle_verdict`=0，`spec_expr_coverage`=1，`rag_stats`=1，`cross_file_deps`=1，`task_metadata_difficulty`=1
- trace：1 文件；节点事件计数={'planner': 1, 'generator': 1, 'executor': 2, '_should_debug': 2, 'debugger': 1, 'patch_applier': 1}
- 日志关键词命中：`venv`×1，`RAG`×1，`trace`×1，`补丁`×1，`repair`×1
  - row `quixbugs__bitcount`：passed=False iterations=1 stop_reason=max_iterations diagnosis=✓ patch=✓ repair_history_len=1 spec_compile_rate=None spec_oracle_injected=None spec_oracle_verdict=not_attempted rag_stats=✗ cross_file_deps=None difficulty=None token_budget_capped=False
- 日志告警/错误样本：
  - `基准测试 [aitester]:   0%|          | 0/1 [00:00<?, ?task/s]第 1 次执行失败，尝试重试...`
  - `第 2 次执行失败，尝试重试...`
  - `第 1 次执行失败，尝试重试...`
  - `第 2 次执行失败，尝试重试...`
  - `第 1 次执行失败，尝试重试...`

### `07_oracle_smoke`

- **blocked**：N-3 未提交（tests/test_oracle_independent_judging.py 缺失 / oracle_suite_verdict·llm_suite_detection_rate 接线未落地）——按 N-4 任务书记录 blocked 并跳过；未消耗 LLM 调用。

