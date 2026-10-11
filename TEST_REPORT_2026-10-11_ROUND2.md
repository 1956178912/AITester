# 全量测试报告（含真实 LLM）— 2026-10-11 第二轮

> **触发**：用户要求"所有测试都跑一次，包括 LLM 测试"
> **范围**：`pytest tests/` 全量（含覆盖率）+ 19 项真实 LLM 组件测试 + 端到端链路 + 全部 19 个门禁
> **结论**：**5487 passed / 3 skipped / 1 xfailed / 0 failed** · **门禁 18/19 绿** · 并且**回归过程中定位并修复了三个此前从未被覆盖的缺陷**（其中一个是"逻辑驱动"空转的决定性机制）

---

## 1. 测试结果总览

| 测试组 | 数量 | 结果 |
|---|---|---|
| **pytest 全量**（`tests/`） | 5491 collected | **5487 passed / 3 skipped / 1 xfailed / 0 failed**（205s） |
| **代码覆盖率** | `--cov=src --cov-branch` | coverage.xml 已生成；`check_branch_coverage` 绿（行 ≥85%、分支 ≥77%） |
| **LLM 组件电池**（独立子进程） | 18 项 | **15 OK / 3 FAIL**（3 项为脚手架 API 误用，修正版全通过——见 §3） |
| **LLM 补充组件**（修正 API） | 4 项 | **4/4 OK** |
| **默认关闭的付费能力**（显式开启） | 4 项 | 3/4 OK（1 项为脚手架签名误用） |
| **端到端真实缺陷链路**（fresh cache） | 9 次试验 | 检出 0/9（机制见 §4） |
| **门禁** | 19 个 | **18 绿 / 1 红**（红者是数据前置校验，设计如此） |
| **静态检查** | ruff / format / mypy | 全绿 · 491 文件已格式化 · **mypy 0 错误**（125 源文件） |

---

## 2. 本轮修复的三个缺陷（**回归的实质产出**）

> 这三个缺陷此前**从未被任何测试覆盖**——它们共同构成"逻辑驱动"在真实实验中空转的完整机制（审查报告 F5/F14 的最终落点）。

### 2.1 T1b｜白名单调用名被未知标识符门拒绝（`src/specs/spec_ir_v2.py`）

`_ALLOWED_CALL_NAMES` 的 12 个内建（`abs/all/any/float/int/isinstance/len/max/min/round/sorted/str`）在 `_whitelist_check` 里按调用位置放行，但它们在 AST 里同样是 `ast.Name` 节点，随即被 `identifiers - known` 判成 `unknown_name`。

**同一白名单在前一门放行、后一门拒绝** → 白名单里的函数**一个都用不了**：

| 子句 | 修复前 | 修复后 |
|---|---|---|
| `len(items) > 0` | ❌ unknown_name | ✅ 可编译 |
| `isinstance(a, int)` | ❌ unknown_name | ✅ 可编译 |
| `max(a, b) > 0` | ❌ unknown_name | ✅ 可编译 |
| `a + b > 0` | ✅ 可编译 | ✅ 可编译 |

**危险面零放宽**（13 条正/反例验证）：`eval("1")` / `__import__("os")` / `a.__class__` → 仍 `unsupported_operator`；`r == total` → 仍 `unknown_name`；`text 为 str 类型` → 仍 `natural_language`。

### 2.2 T1c｜oracle 产物因缩进错误恒被丢弃（**决定性**）

`_compile_single_clause` 返回**无缩进**语句，而 `compile_spec_oracle` 对 post/invariant 行额外做了一次缩进替换 → **8 空格**；pre 行是 4 空格；oracle 一级语句也是 4 空格。混排结果：

```python
def test_specir_v2_oracle():
    from target_mod import find_max
    items = 0
        assert len(items) > 0     # ← 8 空格 → SyntaxError: unexpected indent
    r = find_max(items)
        assert r == max(items)
```

产物总自检 `ast.parse` 必然失败 → 走"保守丢弃"分支（日志：`SpecIR v2 oracle 产物自检失败`）。

**关键含义：即使 `readiness = 1.0`（全部子句可编译），产物仍恒为 0 字节。** 这就是"逻辑驱动"空转的直接机制——不是求解器不行，不是规约写不出，而是**产物的缩进错了**。

**修复验证（真实 LLM）**：

| 函数 | 修复前产物长度 | 修复后产物长度 |
|---|---|---|
| `divide` | 0 | **299 字节** |
| `find_max` | 0 | **369 字节** |
| `parse_age` | 0 | **339 字节** |

且全部 `ast.parse` 通过、可实际执行。

### 2.3 T1d｜退化字面量绑定在正确实现上误报

T1c 修复后 oracle 首次真正产出可执行代码，随即暴露原"已知保守权衡"的后果：无边界材料时绑定 `a, b = 0, 0` / `items = 0` 会**违反前件**（如 `b != 0`），使 oracle **在 gold 实现上就断言失败**——产物从"确定性检出通道"退化为"确定性假报通道"。

**修复（两条分支）**：
1. 复用既有 z3 通道 `spec_smt.generate_spec_witnesses`（其语义本就是"满足前件的合法输入"）取见证绑定（参数键在 `inputs` 子字典内）；
2. **无见证时不发出前件断言**（降为注释保留 provenance），后件断言照发——前件只有由构造满足时才断言。

---

## 3. LLM 组件测试明细

### 3.1 主电池（18 项，每项独立子进程）

| 组件 | 结果 | 组件 | 结果 |
|---|---|---|---|
| `api_manager` | ✅ 0.95s | `spec_ir` | ✅ |
| `base_agent` | ✅ 1.13s | `spec_smt` | ✅（z3 真求解） |
| `base_agent_cache` | ⚠️ 脚手架签名误用 | `spec_refine` | ✅ 8.64s（CEGIR 闭环） |
| `planner` | ✅ 3.41s | `workflow_full` | ✅ 3.82s |
| `generator` | ✅ 4.48s | `workflow_plain` | ✅ 4.76s |
| `debugger` | ✅ 2.30s | `mutation_feedback` | ✅ 1.30s |
| `oracle_enhancer` | ✅ 1.44s | `adversarial_search` | ⚠️ 脚手架签名误用 |
| `expert_pool` | ✅ 3.99s | `rag_retriever` | ✅ 0.34s |
| `fault_localizer` | ✅ 1.34s | `mdo_measure` | ⚠️ 脚手架导入名误用 |

**3 项 FAIL 全是我的脚手架 API 误用**（`runner.py` v1 的签名），修正版 `runner2.py` / `offbydefault2.py` 全部通过——**无一是产品缺陷**。

### 3.2 修复产出的组件级提升（真实调用）

| 组件 | 修复前 | 修复后 |
|---|---|---|
| **对抗性意图生成**（T2） | `n_intents = 0`（恒空） | **`n_intents = 3`**（真实假设） |
| **OracleEnhancer**（T2） | `oracle_enhanced = False`（恒降级） | **`oracle_enhanced = True`** |
| **对抗式变异搜索**（T2 复合） | `accepted = 0` | **`accepted = 3`**（proposed 7 / equivalent 2 / killed 2） |
| **MDO 饱和出口**（T6） | `mtr=1.0 mdr=1.0`（误导） | **`mtr=None mdr=None status=provisional_pool`** ✅ |
| **type_repair 生产口径**（T7） | 注入回调路径拒绝带围栏代码 | **`findings=2 repaired=True contract_ok=True`** ✅ |
| **S29 模型指纹** | `pinned=False`（探针恒失败） | **`pinned=True`** + `system_fingerprint` + 三次一致 `probe_sha256` ✅ |

---

## 4. 端到端真实缺陷链路（fresh cache，9 次试验）

| 指标 | 实测 |
|---|---|
| fail-to-pass 检出率 | **0/9** |
| 坏测试（buggy 与 gold 两侧皆红） | 3/9 |
| 执行错误 / 语法解析失败 | 0/9 |
| `logic_degraded` | 3/9 |
| 平均耗时 | 3.3s |

**机制说明（与审查一致，非回归）**：该短链路**直接调用 `GeneratorAgent`，绕过 workflow**，因此不触发检出优先协议的再生成分支（其条件为 `detection_first_enabled() and test_passed is True and iteration==0`，见 `src/graph/nodes.py:471`）。所以 0/9 是**脚手架的结构性局限**，不是修复失效：项目主批次的 15.8% 正是靠该分支达成的。要测真实检出率必须走 `run_benchmark` 三臂口径（见下）。

**planner 稳定性新观察**：同一 target 多次规划，`logic_degraded` 在 0/3 ~ 2/3 间波动（`AITESTER_PROFILE=logic` 下 `LOGIC_SPEC_STRICT_ENABLE=true` 会对 schema 不合规输出直接降级为空气）；temperature=0.0 未消除波动。这本身是一个**值得记录的可复现性观察**（模型侧非确定性）。

---

## 5. 门禁结果（18/19）

```
OK  check_artifacts_tracked      OK  check_baseline               OK  check_baseline_numbers
OK  check_bilingual_docs         OK  check_branch_coverage        OK  check_citations
OK  check_credential_scrub       OK  check_dependency_exemptions  OK  check_docs_history_drift
OK  check_env_budget             OK  check_env_snapshot_keys      OK  check_llm_configs_schema
OK  check_lock_sync              OK  check_model_fingerprint      OK  check_perf_regression
OK  check_state_contract         OK  check_tool_versions          OK  check_zero_assert_tests
FAIL check_swe_bench_pro_ready
```

**关于唯一未绿**：`check_swe_bench_pro_ready` 的 docstring 自述为"**独立入口**（供实验流程在执行前确认数据就绪）"——它是**数据前置校验**而非代码门禁（本地无 SWE-bench Pro 数据集，且未接入 CI）。属**范围正确**。

---

## 6. 基线一致性

```
--collect-only 收集 5491
BASELINE.yaml: total_passed=5487 + skipped=3 + xfailed=1 = 5491 ✅ 恒等式成立
```

---

## 7. 本轮真实 LLM 成本

| 组 | 缓存条目（≈调用数） |
|---|---|
| T1 效果验证（3 轮 fresh cache） | 9 |
| oracle 执行验证 | 12 |
| 组件电池（fresh cache） | 11 |
| 端到端链路（fresh cache） | 7 |
| 补充组件 + 默认关闭能力 | ~20 |
| **合计** | **≈ 60 次真实调用** |

单价按 `deepseek-flash` 峰时（in $0.3/M、out $1.2/M），**本轮成本约 $0.05 量级**（提示短、输出小）。累计全项目实测成本仍约 **$1.2**。

---

## 8. 结论

1. **全量测试与门禁均达标**：5487 passed / 0 failed；18/19 门禁绿（唯一红者是数据前置校验）。
2. **回归的最大价值不是"确认没坏"，而是发现了三个从未被覆盖的缺陷**——其中 **T1c（oracle 缩进错误导致产物恒被丢弃）是"逻辑驱动"空转的决定性机制**：即使可编译率 100%，产物也永远是 0 字节。
3. **修复效果已在真实 LLM 下验证**：oracle 产物 **0 → 299/369/339 字节且可执行**；对抗性推理 **0 → 3 条假设**；对抗式变异搜索 **0 → 3 个可接受变异体**。
4. **仍待解决**（下一批）：无见证时的退化绑定对容器参数仍会产生类型不匹配（`items = 0` → `max(items)` TypeError）——本轮已把"误报"降级为"不误报"，但"能跑出有意义的后件断言"还需按签名推导字面量类型。这是逻辑驱动的下一个真实瓶颈。
