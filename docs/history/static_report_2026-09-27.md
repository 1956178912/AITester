# 静态检查快照（2026-09-27 12:10 UTC）

> 本文件由 `scripts/generate_static_report.py` 自动生成（Python 3.14.6）。
> 各批次落地后运行脚本刷新；与 BASELINE.yaml `static_checks` 节同口径。
> 前序快照保留在同目录（按日期命名），历史结论以对应快照为准。

## 工具

### ruff check .（退出码 0，输出 1 行）

```
All checks passed!
```

### ruff format --check .（退出码 1，输出 315 行）

```
unformatted: File would be reformatted
   --> experiments/model_gradient.py:114:31
    |
113 |         for d in details
    -         if isinstance(d, dict)
    -         and isinstance(d.get("repo_verification"), dict)  # type: ignore[union-attr]
114 +         if isinstance(d, dict) and isinstance(d.get("repo_verification"), dict)  # type: ignore[union-attr]
115 |     ]
--------------------------------------------------------------------------------
206 |     parser.add_argument("--baseline", default="aitester", help="统计基线（默认 aitester）")
    -     parser.add_argument("--no-run", action="store_true", help="仅汇总已有结果 JSON，不跑新 benchmark（--analyze-only 口径）")
207 +     parser.add_argument(
208 +         "--no-run", action="store_true", help="仅汇总已有结果 JSON，不跑新 benchmark（--analyze-only 口径）"
209 +     )
210 |     args = parser.parse_args()
    |

unformatted: File would be reformatted
   --> src/agents/debugger.py:594:32
    |
593 |             "downgrade_triggered": bool(contract_reject_feedback),
    -             "downgrade_tier": (
    -                 str(contract_reject_feedback.get("tier")) if contract_reject_feedback else None
    -             ),
594 +             "downgrade_tier": (str(contract_reject_feedback.get("tier")) if contract_reject_feedback else None),
595 |             # 2.1 P1 改进：结构化修复策略标签（错误分类 → 修复路径显式映射）
    |

unformatted: File would be reformatted
   --> src/graph/event_bus.py:63:18
    |
62  |
    -     def __init__(self, task_uuid: str = "", function_name: str = "", test_case_count: int = 0,
    -                  cfg_cyclomatic: int | None = None, iteration: int = 0) -> None:
63  +     def __init__(
64  +         self,
65  +         task_uuid: str = "",
66  +         function_name: str = "",
67  +         test_case_count: int = 0,
68  +         cfg_cyclomatic: int | None = None,
69  +         iteration: int = 0,
70  +     ) -> None:
71  |         super().__init__(
--------------------------------------------------------------------------------
87  |
    -     def __init__(self, task_uuid: str = "", passed: bool = False, coverage: float | None = None,
    -                  error_category: str = "", iteration: int = 0) -> None:
88  +     def __init__(
89  +         self,
90  +         task_uuid: str = "",
91  +         passed: bool = False,
92  +         coverage: float | None = None,
93  +         error_category: str = "",
94  +         iteration: int = 0,
95  +     ) -> None:
96  |         super().__init__(
--------------------------------------------------------------------------------
111 |
    -     def __init__(self, task_uuid: str = "", applied: bool = False, new_code_chars: int = 0,
    -                  postprocess_labels: list[str] | None = None, iteration: int = 0) -> None:
112 +     def __init__(
113 +         self,
114 +         task_uuid: str = "",
115 +         applied: bool = False,
116 +         new_code_chars: int = 0,
117 +         postprocess_labels: list[str] | None = None,
118 +         iteration: int = 0,
119 +     ) -> None:
120 |         payload: dict[str, Any] = {
--------------------------------------------------------------------------------
134 |
    -     def __init__(self, task_uuid: str = "", error_category: str = "", fix_strategy_tag: str = "",
    -                  fix_strategy_action: str = "", iteration: int = 0) -> None:
135 +     def __init__(
136 +         self,
137 +         task_uuid: str = "",
138 +         error_category: str = "",
139 +         fix_strategy_tag: str = "",
140 +         fix_strategy_action: str = "",
141 +         iteration: int = 0,
142 +     ) -> None:
143 |         super().__init__(
--------------------------------------------------------------------------------
158 |
    -     def __init__(self, task_uuid: str = "", test_passed: bool = False, iteration: int = 0,
    -                  final_error_category: str = "") -> None:
159 +     def __init__(
160 +         self, task_uuid: str = "", test_passed: bool = False, iteration: int = 0, final_error_category: str = ""
161 +     ) -> None:
162 |         super().__init__(
    |

unformatted: File would be reformatted
    --> src/graph/nodes.py:135:1
     |
134  |
135  +
136  | # 安全检查 2 用：函数定义探测正则（re 编译缓存命中，热路径零编译开销）。
--------------------------------------------------------------------------------
216  |         _planner_budget_hit = isinstance(e, BudgetExceededError)
     -         logger.warning("Planner LLM 失败（%s），使用默认计划: %s", "5.4 预算封顶" if _planner_budget_hit else "JSON 解析失败", e)
217  +         logger.warning(
218  +             "Planner LLM 失败（%s），使用默认计划: %s", "5.4 预算封顶" if _planner_budget_hit else "JSON 解析失败", e
219  +         )
220  |         test_plan = _get_default_test_plan(state.get("target_function"))
--------------------------------------------------------------------------------
1277 |             postprocess_labels = list(_pp_labels)
     -             if (
     -                 (_pp_flags["import_repair"] or _pp_flags["contract_alias"])
     -                 and ("imports_repaired" in _pp_labels or "contract_aliases_restored" in _pp_labels)
1278 +             if (_pp_flags["import_repair"] or _pp_flags["contract_alias"]) and (
1279 +                 "imports_repaired" in _pp_labels or "contract_aliases_restored" in _pp_labels
1280 |             ):
--------------------------------------------------------------------------------
1394 |                 from src.tools.patch_applier import check_naming_contract as _ck
1395 +
1396 |                 _ok2, _missing2 = _ck(original_code, new_code)
     |

unformatted: File would be reformatted
   --> src/tools/control_flow.py:59:75
    |
58  |     for node in tree.body:
    -         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
    -             func_name is None or node.name == func_name
    -         ):
59  +         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (func_name is None or node.name == func_name):
60  |             return node
--------------------------------------------------------------------------------
130 |                 if isinstance(node.type, ast.Tuple):
    -                     types = [
    -                         _exc_type_name(elt) for elt in node.type.elts
    -                     ]
131 +                     types = [_exc_type_name(elt) for elt in node.type.elts]
132 |                 else:
--------------------------------------------------------------------------------
160 |     if branches_dedup:
    -         hint_parts.append(f"分支 {len(branches_dedup)} 处（第 " + ", ".join(str(b["line"]) for b in branches_dedup[:8]) + " 行）")
161 +         hint_parts.append(
162 +             f"分支 {len(branches_dedup)} 处（第 " + ", ".join(str(b["line"]) for b in branches_dedup[:8]) + " 行）"
163 +         )
164 |     if loops:
--------------------------------------------------------------------------------
168 |             "异常路径 "
    -             + ", ".join(
    -                 (f"{e['kind']}[{','.join(e['types'])}]" if e["types"] else e["kind"])
    -                 for e in exceptions[:5]
    -             )
169 +             + ", ".join((f"{e['kind']}[{','.join(e['types'])}]" if e["types"] else e["kind"]) for e in exceptions[:5])
170 |         )
    |

unformatted: File would be reformatted
   --> src/tools/patch_postprocess.py:41:1
    |
40  |
41  +
42  | # ─── 开关（环境变量，功能模块在调用期读取，与 multi_candidate/cross_file
--------------------------------------------------------------------------------
49  |
50  +
51  | # P2 导入断裂修复（默认 false，保持历史行为）：补丁应用前自动把原代码的
--------------------------------------------------------------------------------
55  |
56  +
57  | # P3 契约符号别名回填（默认 false，保持历史行为）：检测 LLM 对模块级
--------------------------------------------------------------------------------
228 |                         sink.add(target.id)
    -             elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and not node.target.id.startswith(
    -                 "__"
229 +             elif (
230 +                 isinstance(node, ast.AnnAssign)
231 +                 and isinstance(node.target, ast.Name)
232 +                 and not node.target.id.startswith("__")
233 |             ):
--------------------------------------------------------------------------------
246 |     new_symbols = patch_symbols - orig_symbols
247 +
248 |     def _common_prefix_len(a: str, b: str) -> int:
    |

unformatted: File would be reformatted
   --> src/tools/type_repair.py:139:42
    |
138 |
    -         with tempfile.NamedTemporaryFile(
    -             "w", suffix=".py", delete=False, encoding="utf-8"
    -         ) as _f:
139 +         with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as _f:
140 |             _f.write(patched_code or "")
--------------------------------------------------------------------------------
146 |             # 解析 mypy 输出（格式：path:line:col: error: message [category]）
    -             _MYPY_LINE_RE = re.compile(
    -                 r"^.+?:?(\d+):\d+: (warning|error): (.+?) \[([a-z-]+)\]$"
    -             )
147 +             _MYPY_LINE_RE = re.compile(r"^.+?:?(\d+):\d+: (warning|error): (.+?) \[([a-z-]+)\]$")
148 |             findings: list[dict[str, Any]] = []
--------------------------------------------------------------------------------
265 |
    -         with tempfile.NamedTemporaryFile(
……（截断，完整输出共 315 行）
```

### mypy src/ config.py（退出码 0，输出 1 行）

```
Success: no issues found in 69 source files
```

