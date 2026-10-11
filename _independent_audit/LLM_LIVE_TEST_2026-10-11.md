# LLM 真实调用测试报告（2026-10-11）

> **性质**：本报告是 [INDEPENDENT_AUDIT_2026-10-11.md](INDEPENDENT_AUDIT_2026-10-11.md) 的**实测补充**。
> 前次审查（含既有评审）**未发起任何真实 LLM 调用**；本报告对项目中**所有依赖 LLM 的组件**做了真实端到端测试。
> 模型：`deepseek-flash`（DeepSeek 官方 API，`.env.local` 中的真实凭证）｜温度 0.0｜`AITESTER_PROFILE=logic`
> **未修改仓库任何源码或配置**；测试脚本与工件在 `/tmp/aitester_llm_test/`。

---

## 0. 执行摘要

**连通性：全部组件可用。** 18 个 LLM 依赖组件中 **18/18 在真实调用下功能正常**（无一处因代码缺陷而失败）。项目的 LLM 集成工程质量是**真实可靠的**。

**但功能可用 ≠ 有效。** 在真实调用下：

| 结论 | 实测证据 | 等级 |
|---|---|---|
| **L1** | 全链路 18 次真实试验的 **fail-to-pass 检出率 = 0.0%**（0/18）。三种项目自身缺陷模式下，生成的测试**在缺陷代码上通过、在 gold 修复代码上失败**——即断言的是**缺陷行为**本身（oracle-from-implementation 陷阱） | **A** |
| **L2** | 用项目**自己的 benchmark 代码路径**新跑 8 任务 × 3 臂：aitester **1/8**、plain_llm **1/8**、plain_llm_df **3/8**。**df 臂仍是最好，aitester 未优于 plain_llm**；token 消耗 aitester **57,838** vs df **20,671**（2.8×）vs plain_llm **9,999**（5.8×） | **A** |
| **L3** | **"逻辑驱动"通道在真实调用下产出为零**：8 个 aitester 任务中 **7 个 `spec_compile_rate = 0.0`**；独立链路测试 3 个函数中，planner 对 2 个返回 `logic_degraded=True`（空规约），唯一成功的一个产出**自然语言规约**（`"text 为 str 类型"`、`"成功时返回 int 类型结果"`）而非可编译表达式 → **编译产物长度 0** | **A** |
| **L4** | **覆盖率再次确认无鉴别力**：三臂 avg coverage 分别为 **97.2% / 99.5% / 99.1%**，而检出率为 12.5%/12.5%/37.5% | **A** |
| **L5** | **LLM 缓存使"多次运行"退化为单次运行**：18 次试验中后 17 次耗时均 ≈0.8s 且**结果逐位相同**（缓存命中）；清空缓存后耗时升至 7.7s 且**结果发生变化**（同类任务的 bad_test 从 True 变 False）。**项目 `BASELINE.yaml` 声称的"三种子独立采样"需在此机制下重新审视** | **A** |
| **L6** | **`--enable-mutation` 关闭时 `mutation_score` 不落盘**；开启时方能产出（实测 3 变异体 / score 0.333） | **A** |
| **L7** | **MDO 池规模在真实函数上严重不足**：`mdo_pool_floor_ok = False`（pool_size **2**，下限 29），但 MTR/MDR 仍报 **1.0/1.0** —— 指标"有值"但**不可用**，与我在 §6.1 路径 A1 中的失败判定条件吻合 | **A** |
| **L8** | **test-hacking 判定核对测试侧完全不可见**：该函数只接收 `original_code` / `patched_code`，**不接收 `generated_test`**。5 类测试侧作弊（断言删除 / `assert True` / `pytest.skip` / 吞异常）**全部无法检出** | **A** |

**一句话**：项目的 LLM 管道**跑得通**，但跑出来的**不是有效检出**——最根本的原因是生成器写出的测试**断言了缺陷行为**，而系统把这种测试当作"证据"。这解释了为什么 `plain_llm`（1.5%）与 `aitester`（15.8%）在主批次都接近地板，而**只有显式"检出优先"提示的 df 臂（44.8%）能突破**。

---

## 1. 组件清单与实测结果

**方法**：每个组件在**独立子进程**中运行（避免 LLM 缓存与全局状态跨测试污染）。

| # | 组件 | 真实调用结果 | 耗时 | 实测细节 |
|---|---|---|---|---|
| 1 | `APIManager.call` | ✅ OK | 1.15s | `nodes=1 healthy=1`，回复 `PONG`；重试/故障转移链路未触发 |
| 2 | `BaseAgent._call_llm` | ✅ OK | 1.11s | 回复 `ALPHA` |
| 3 | `BaseAgent._call_llm_with_cache` | ✅ OK | <0.1s | 第二次调用 `cache_hits=1`、`cache_avoided_tokens=19`；**记账正确** |
| 4 | `PlannerAgent.plan` | ✅ OK | 0.57–3.7s | 产出 `logic_analysis`；**稳定性依赖任务**（见 L3） |
| 5 | `GeneratorAgent.generate` | ✅ OK | 0.62–3.6s | 产出 2,432–2,643 字符、`ast.parse` 通过 |
| 6 | `DebuggerAgent.debug` | ✅ OK | 1.4–6.7s | 产出 `root_cause` / `patch`(285B) / 20 个键 |
| 7 | `OracleEnhancerAgent.enhance` | ✅ OK | 0.51s | 保留 2 个 case；**LLM 输出非列表 → 保守降级**（日志可见） |
| 8 | `ExpertPoolAgent.generate_parallel` + `debate_round` | ✅ OK | 5.66s | 3 候选 / 4 条辩论输出；**3 个置信度全为 0.5**（证实启发式置信度） |
| 9 | `FaultLocalizerAgent.localize` | ✅ OK | 1.62s | 正确定位 `divide` 行 3，`confidence=0.98`，`expected_logic` 描述准确 |
| 10 | `spec_ir_v2.compile_spec_oracle` | ✅ OK（无 LLM） | <0.1s | 手工规约下产出 0 字节（见 L3） |
| 11 | `spec_smt.check_postcondition_consistency` | ✅ OK | 0.03s | `r==a/b` → `sat`；`r>0 ∧ r<0` → **`unsat`**（z3 真求解，正确） |
| 12 | `spec_refine.refine_spec_with_counterexample` | ✅ OK | 11.78s | **真实 LLM 闭环成功**：`unsat → LLM 修正 → sat`，`converged=true` |
| 13 | `build_workflow()`（完整图） | ✅ OK | 1.28s | 18 个状态键；`test_passed=true`；coverage 88.0 |
| 14 | `build_workflow(planner=False,debugger=False)` | ✅ OK | 1.22s | `test_passed=true` |
| 15 | `build_mutation_feedback` | ✅ OK | 1.27s | 3 变异体、`mutation_score=0.3333` |
| 16 | `AdversarialMutantSearch.propose_and_filter` | ✅ OK | <0.1s | `proposed=2 killed=2 accepted=0`（无盲区存活） |
| 17 | `get_rag_retriever().retrieve` | ✅ OK | 0.31s | 返回 0 条（RAG 默认关、索引为空） |
| 18 | `compute_mdo` | ✅ OK | <0.1s | 见 L7 |

**判定**：**没有任何组件因代码缺陷而失败**。三处初次失败均为**我的测试脚手架 API 误用**（已修正后重测通过）。

---

## 2. L1：真实缺陷上的端到端检出测试（**最重要**）

**设计**：用项目自身 `synthetic_dataset` 风格的 3 个真实缺陷模板，走完整链路：

```
PlannerAgent.plan(buggy) → GeneratorAgent.generate → pytest(buggy) → pytest(gold)
                        → [M1 三段判定] → DebuggerAgent.debug → apply_patch → pytest(patched)
```

**结果（18 次试验：3 模板 × 6 重复）**：

| 指标 | 实测值 |
|---|---|
| **fail-to-pass 检出率** | **0/18 = 0.0%** |
| 坏测试（buggy 与 gold 两侧皆红） | 6/18 |
| 执行错误（收集/语法/导入） | 0/18 |
| 测试语法解析失败 | 0/18 |
| `logic_degraded=True` | 6/18 |
| 修复尝试次数（仅在检出后进入） | **0**（因检出为 0，修复回路一次未进入） |
| 平均耗时（缓存命中） | 0.8s |

**失败模式分解（清空缓存后的真实分布）**：

| 模板 | `rc_buggy` | `rc_gold` | 判定 |
|---|---|---|---|
| `divide_by_zero_missing` | 0（**绿**） | 1（红） | **反向**：测试认可用 `else 0` 吞掉除零的缺陷行为 |
| `find_max_empty_crash` | 0（**绿**） | 1（红） | **反向**：测试未覆盖空列表路径 |
| `parse_age_no_validation` | 0（**绿**） | 1（红） | **反向**：测试断言了"无校验"的行为 |

**机制判定（A 级）**：生成的测试**在缺陷代码上通过**，说明断言写的是**当前（缺陷）实现的行为**，而非 docstring 声明的契约。这正是项目 `src/datasets/synthetic_dataset.py:213` 注释中自称修复过的"oracle-from-implementation"通道，也是 `plain_llm` 臂在主批次只有 **1.5%** 检出的根因。

**与项目数字的关系**：主批次 `aitester` 15.8% 中的那 38 次成功检出，依赖 `DETECTION_SPECIFICITY_GATE_ENABLE`（logic 档开启）在首轮全绿后**触发再生成**并注入"先红后绿"提示。**短链路直调（我的脚手架）不触发该分支**，故检出为 0——这与 `src/graph/nodes.py:471` 的条件一致：`detection_first_enabled() and test_passed is True and iteration==0`。

---

## 3. L2：项目自身 benchmark 代码路径的独立复跑

**命令**（新缓存目录，避免历史缓存干扰）：

```bash
AITESTER_PROFILE=logic AITESTER_LLM_CACHE_DIR=/tmp/aitester_llm_test/llmcache \
.venv/bin/python experiments/run_benchmark.py \
  --dataset synthetic --task-count 8 --task-limit 8 --seed 42 \
  --baselines aitester,plain_llm,plain_llm_df \
  --output-dir /tmp/aitester_llm_test/bench_out --no-rag
```

**结果**（8 任务 / 臂，seed 42）：

| 臂 | detection | repair | false_fix | avg coverage | avg iter | total tokens |
|---|---|---|---|---|---|---|
| `aitester` | **1/8 = 12.5%** | **2/8 = 25%** | 6/8 | 97.2% | 0.5 | **57,838** |
| `plain_llm` | **1/8 = 12.5%** | 0/8 | 7/8 | 99.5% | 0.0 | 9,999 |
| `plain_llm_df` | **3/8 = 37.5%** | 0/8 | 3/8 | 99.1% | 0.0 | 20,671 |

**独立判定**：
1. **df 仍是最强臂**（37.5% vs 12.5%），**复现主批次的定性结论**。
2. **aitester 未优于 plain_llm**（均 12.5%），与主批次 δ=−24.6pp 方向一致。
3. **成本差距被复现且更大**：aitester 消耗 **5.8×** plain_llm、**2.8×** df 的 token。
4. **覆盖率再次无鉴别力**：97.2% / 99.5% / 99.1%，而检出 12.5% / 12.5% / 37.5%。
5. ⚠️ **本次 aitester 的 repair = 2/8 = 25%**（主批次当次为 0.0%）——说明修复回路在此配置下**确实能产生非零修复**，但样本仅 8 且属单次运行，**不足以支撑**项目声称的 39.31%；需要更大样本 + 机器可读工件。
6. ⚠️ `provenance.git_dirty = True`（工作树未提交），**本次结果同样不可从 commit 重建**。

---

## 4. L3：逻辑驱动通道的真实产出

**(a) 项目 benchmark 内的 `spec_compile_rate`（8 个 aitester 任务）**

| 取值 | 任务数 |
|---|---|
| 0.0 | **7** |
| 1.0 | 1 |

→ **87.5% 的 aitester 任务在该批次产不出任何可编译规约**，**比项目全量中位数 0.200 更差**。这为我在主审查 §3.5 的发现（全量 n=1,607 中 47.6% 为零）提供了**独立复现**。

**(b) 独立链路测试（planner → 编译 → SMT）**

| 函数 | `logic_degraded` | pre/post/inv/edge | `readiness` | 编译产物长度 |
|---|---|---|---|---|
| `divide` | **True** | 0/0/0/0 | 0.0 | **0** |
| `find_max` | **True** | 0/0/0/0 | 0.0 | **0** |
| `parse_age` | False | 2/3/0/11 | 1.0 | **0** |

**关键机制（A 级）**：`parse_age` 的 planner 成功产出了 2 条前置 + 3 条后置，但内容是**自然语言**：

- `preconditions[0] = "text 为 str 类型"`
- `postconditions[0] = "成功时返回 int 类型结果"`

这些**不是可编译的 SpecExpr**（白名单只接受布尔/比较/算术表达式），故 `compile_spec_oracle` 产出 0 字节，并记录：

```
SpecIR v2 oracle 产物自检失败，保守丢弃（防坏代码注入执行链路）
```

**同时观察到强校验拒绝链**（`LOGIC_SPEC_STRICT_ENABLE=true` 在 logic 档开启）：

```
M10：LLM 未输出 logic_analysis，已填充空值并标记 logic_degraded=True
M10 强校验拒绝已降级：logic_analysis 缺失，拒绝静默兜底
M10 schema 校验：5 条 findings
M10 强校验后续拒绝：logic_analysis schema 校验失败，拒绝静默兜底
```

**判定**：**"逻辑驱动"的失效点在于 planner 要求 LLM 产出"自然语言 vs 形式表达式"时，LLM 系统性选择自然语言**，而编译器只接受形式表达式。**这是提示-文法契约缺陷，不是求解器缺陷**（`spec_smt` 的 z3 求解实测完全正确）。这条根因**比主审查 §3.5 的统计描述更精确**，可直接指导修复（见 §7 建议）。

**(c) `spec_refine` CEGIR 是唯一真实闭环的能力**

实测（真实 LLM 调用，11.78s）：
```
输入规约 preconditions = ["b != 0", "b == 0"]
→ initial_findings.precondition = {"status": "unsat", "clauses": 2}
→ LLM 修正契约
→ final_findings.precondition  = {"status": "sat",  "clauses": 1}
→ converged = true, rounds = 1
```
**该闭环在真实调用下确实工作**。但如主审查 §9.2 B4 所述，它**未接入主链路**（全仓零引用）——即**能跑通，但没人在用**。

---

## 5. L5：LLM 缓存使重复试验退化为单次（方法论风险）

**实测对比**：

| 条件 | 单次耗时 | 18 次试验结果的差异 |
|---|---|---|
| 缓存**存在**（默认 `~/.cache/aitester/llm/`，实测 **5,275** 个缓存文件） | **≈0.8s** | **逐位相同**（同模板 rc 恒定） |
| 缓存**已清空** | **7.7s** | **发生变化**（`divide_by_zero_missing` 的 `bad_test` 由 True → False） |

**判定（A 级）**：`BaseAgent._call_llm_with_cache` 的缓存键**不含需要变化的维度**，因此：
1. **相同 prompt 的重复试验不是独立采样**；
2. 这也是我在主审查 §3.6(b) 发现的"同 seed 不同 `git_sha` 产出**逐字节相同** `generated_test`"的机制根因；
3. **对项目的影响**：任何"跑 N 次取平均"的实验，若不清缓存，实际是**跑 1 次 + N−1 次重放**。项目 `BASELINE.yaml` 声称的"三种子独立采样"（seed 42/43/44）**经我验证产出确实互不相同**（跨 seed `generated_test` 逐字节相同率 = 0%），因此主批次**未受此影响**；但**同 seed 的重复批次会受影响**（已在主审查 §3.6b 举证 100% 相同）。

---

## 6. L6–L8：三个测量与安全项的实测

**L6 · 变异得分默认不落盘**

- 未加 `--enable-mutation` 时，8 任务的 `mutation_score` 字段**全部缺失**；
- 直接调用 `build_mutation_feedback` 可产出：3 变异体 / killed 1 / **score 0.3333**。

→ 项目 `BASELINE.yaml` 的 mutation 区间（0.818–0.976）**仅在显式开启开关的批次中存在**；引用时必须绑定该条件。

**L7 · MDO 池规模不足但仍产出数值**

```
compute_mdo(divide, 简单测试, mutants=2) →
  mdo_available = True, mdo_pool_size = 2, mdo_pool_floor_ok = False,
  mtr = 1.0, mdr = 1.0, crash_rate = 0.0, status = "measured"
```

→ **指标"有值"但池规模仅 2（下限 29）**。`pool_floor_ok=False` 是项目**自己设计的诚实标记**（值得肯定），但**数值仍照常写出**，下游若只看 `mdr=1.0` 会得出"判别力满分"的错误结论。**这正是我在主审查 §6.1 路径 A1 中设定的失败判定条件之一。**

**L8 · test-hacking 判定核对测试侧不可见（安全项）**

实测 `detect_test_hacking(original_code, patched_code)` 的输出：

| 作弊构造（测试侧/代码侧） | `suspected` | 说明 |
|---|---|---|
| 硬编码 `if x == 5: return 6` | 依输入而定 | 形态受限的常量返回可被捕获 |
| 硬编码经变量 `y = 6; return y` | **False** | **绕过**（非 Const 节点） |
| 映射表后门 `table = {5: 6}` | **False** | **绕过** |
| 吞异常 `except Exception: return x` | **False** | **绕过** |
| **删除断言 / `assert True` / `pytest.skip`** | **不可见** | 函数签名**不接收 `generated_test`** |

→ **判定**：该判定核的分析对象是**被测代码的补丁**，而"测试侧作弊"（放宽或删除断言、跳过用例）**完全不在其输入范围内**。结合主审查 §9.2 B14 的实测（头条批次 `test_hacking_*` 字段**一个都不存在**），该守卫当前**既未覆盖主要威胁面，也未在实验口径内产出过数据**。

---

## 7. 基于实测的改进建议（补充主审查 §10）

| # | 位置 | 实测依据 | 建议 | 优先级 |
|---|---|---|---|---|
| **T1** | `src/agents/planner.py` 提示模板 + `src/specs/spec_ir_v2.py:63-69` | L3：LLM 系统性产出自然语言规约（`"text 为 str 类型"`），编译器只收形式表达式 → 编译产物恒 0 | **在 planner 提示中给出 SpecExpr 的 BNF 与 5 个正/反例**，并要求 LLM 输出前自检"该子句是否只含比较/布尔/算术算子"。这是 `spec_compile_rate` 从 0.2 → 0.55 的**最直接杠杆**（成本远低于扩文法） | **P0** |
| **T2** | `src/agents/generator.py` 提示模板 | L1：18/18 检出为 0，测试**断言缺陷行为**（buggy 绿 / gold 红） | 生成后**强制自检**："该测试在给定源码上是否失败？"若否，注入"当前实现可能错误，请写出能区分正确/错误实现的断言"。等价于把 `DETECTION_FIRST` 的"先红后绿"从**首轮全绿才触发**改为**默认注入** | **P0** |
| **T3** | `src/graph/nodes.py:471` `_detection_first_regenerate_entry` | L1/L2：检出优先仅在 `test_passed is True and iteration==0` 时触发；短链路与首轮红场景**不触发** | 把检出优先提示改为**无条件注入**（或至少在 `SPEC_IR_DSL_ENABLE` 档位下默认注入），并做 A/B 验证 | **P0** |
| **T4** | `src/agents/base_agent.py:284` `_call_llm_with_cache` | L5：相同 prompt 重复试验退化为缓存重放；耗时 0.8s vs 7.7s | 缓存键加入**实验维度**（要求调用方传入 `experiment_nonce` 或 `seed`），并在**重复试验模式**下默认禁用缓存；`provenance` 记录 `cache_enabled` + 命中率 | **P0** |
| **T5** | `src/tools/patch_test_hacking.py:106` | L8：签名不含 `generated_test`，测试侧作弊完全不可见 | 扩展签名为 `detect_test_hacking(original_code, patched_code, generated_test, original_test)`；新增 6 类测试侧信号（断言数下降 / `assert True` / `pytest.skip` / `xfail` / `except: pass` / mock 掉被测函数） | **P0** |
| **T6** | `src/measurement/mdo.py` 输出 | L7：`pool_floor_ok=False` 时仍输出 `mtr/mdr` | `pool_floor_ok=False` 时**将 `mtr/mdr` 置 `None`**（或加 `provisional=True` 标记），避免下游误读"判别力满分" | **P1** |
| **T7** | `experiments/run_benchmark.py` 结果行 | L6：`mutation_score` 仅开关开启时落盘；L2：`test_passed` 全为 `None` | 结果行增加 `mutation_scoring_enabled` 字段；修复 `test_passed` 恒 None 的问题 | **P1** |
| **T8** | 全部实验批次 | L2：本次跑批同样 `git_dirty=True` | 落实主审查 S10（干净树或脏树指纹），否则**每次新跑的结果都不可从 commit 重建** | **P0** |

---

## 8. 局限声明（本次测试不能覆盖的范围）

| 项 | 说明 |
|---|---|
| **样本量** | L1 为 18 次试验（3 模板 × 6）；L2 为 8 任务。**足以证伪"组件不可用"，不足以给出稳定的检出率点估计** |
| **模型单一** | 全程仅 `deepseek-flash`。项目历史批次亦为此模型，故可比；但**无法回答"换更强模型是否改善"** |
| **缺陷模板** | L1 使用我按项目 `synthetic_dataset` 风格手写的 3 个模板，**非项目模板库的机器生成版本** |
| **真实仓库** | **未测试**。项目 SWE-bench 管道在补丁应用处结构性失败（主审查 §3.3），修通前无法测试 |
| **成本** | 本次为真实计费调用；L1+L2 合计约 20 万 tokens 量级（8 任务全批次 aitester 单项即 57,838） |
| **RAG** | 索引为空，`retrieve` 返回 0 条；**RAG 路径未获有效测试** |
| **未测组件** | `semantic_cache`（项目实现为模块级函数而非类）、`complexity_router`、`api_health` 后台健康检查、`cross_file` 跨文件修复通道 |

---

## 9. 与主审查结论的关系

| 主审查结论 | 本次实测的关系 |
|---|---|
| F1（编排劣于单提示，δ=−24.6pp） | **独立复现方向**（8 任务：df 37.5% vs aitester 12.5%）；小样本不构成新的显著性证据 |
| F5（spec_compile_rate 中位 0.200、47.6% 为零） | **独立复现并定位根因**：planner 产出自然语言规约 vs 编译器只收形式表达式（L3） |
| F7（覆盖率与变异得分饱和无鉴别力） | **独立复现**：coverage 97.2/99.5/99.1% 对 12.5/12.5/37.5% 检出 |
| F9（记账/独立性缺陷） | **机制定位**：LLM 缓存键缺实验维度导致重复试验退化（L5） |
| B14（test-hacking 是观测层） | **独立加强**：不仅未阻断，且**输入不含测试侧**（L8） |
| B4（CEGIR 未接线） | **确认能力真实**：`spec_refine` 在真实 LLM 下完整跑通 `unsat→修正→sat`，但无人调用 |
| U1（repair 无当次证据） | **部分更新**：本次 8 任务中 aitester **repair = 2/8 = 25%**（非零），但样本过小，需更大批次 + 机器可读工件 |

---

## 10. 复现方式

```bash
# 0. 前置：.env.local 含真实 LLM_1_API_KEY / BASE_URL / MODEL_NAME
cd /Users/wangchenyu/Workspace/AITester

# 1. 组件级（18 项，每项独立子进程）
.venv/bin/python /tmp/aitester_llm_test/runner.py

# 2. 补充项（缓存 / 对抗搜索 / MDO / planner 稳定性）
.venv/bin/python /tmp/aitester_llm_test/runner2.py

# 3. 逻辑链路端到端（planner → 编译 → SMT）
.venv/bin/python /tmp/aitester_llm_test/logic_chain.py

# 4. 真实缺陷端到端 + 守卫攻防
.venv/bin/python /tmp/aitester_llm_test/e2e_real_bug.py

# 5. 重复试验（清缓存以获得独立采样）
REPEATS=6 .venv/bin/python /tmp/aitester_llm_test/repeat_e2e.py

# 6. 项目自身 benchmark（8 任务 × 3 臂，约 2 分钟）
AITESTER_PROFILE=logic AITESTER_LLM_CACHE_DIR=/tmp/aitester_llm_test/llmcache \
.venv/bin/python experiments/run_benchmark.py --dataset synthetic \
  --task-count 8 --task-limit 8 --seed 42 \
  --baselines aitester,plain_llm,plain_llm_df \
  --output-dir /tmp/aitester_llm_test/bench_out --no-rag
```

---

## 11. **【最高优先】项目存档批次在当前 API 上无法复现**

这是本次测试**最重要的发现**，其严重性高于 L1–L8 中的任何一条。

### 11.1 方法（对照实验，两组唯一差异 = 缓存状态）

| 组 | 数据 | 说明 |
|---|---|---|
| **A（存档）** | `experiments/results/main_batch/benchmark_synthetic_20261006_*.json`（seed 42/43/44） | 项目头条数字的来源工件 |
| **B（本次新跑）** | 同命令、同 `--dataset synthetic --task-count 87 --task-limit 87`、同 seed、同 `AITESTER_PROFILE=logic`、同模型名 `deepseek-flash`；**唯一差异**：`AITESTER_LLM_CACHE_DIR` 指向**全新空目录** | 消除历史缓存复用 |

**首先排除了"我的执行/指标口径有误"这一竞争解释**：我把**存档里的 `generated_test` 原文**重新执行到 buggy / gold 两侧，用与项目相同 F2P 三段判定复算 `detection_rate`：

| 臂 | 可重放条数 | 与存档 `detection_rate` **一致** |
|---|---|---|
| `aitester` | 22 | **21/22 = 95%** |
| `plain_llm` | 23 | **23/23 = 100%** |
| `plain_llm_df` | 23 | **20/23 = 87%** |

→ **指标定义与执行语义是稳定的**（少数不一致均为跨文件任务的 `rc=2` 收集错误，属我的重放脚手架未物化伴生模块，非指标问题）。

### 11.2 结果：`plain_llm` 臂出现数量级偏移

| seed | 存档 `plain_llm` | **本次新跑 `plain_llm`** | 绝对偏移 |
|---|---|---|---|
| 42 | 1/87 = **1.1%** | **12/87 = 13.8%** | **+12.6 pp** |
| 43 | 1/87 = **1.1%** | **18/87 = 20.7%** | **+19.5 pp** |
| 44 | 2/87 = 2.3% | **20/87 = 23.0%** | **+20.7 pp** |
| **合并（n=261）** | **4/261 = 1.5%** | **50/261 = 19.2%** | **+17.7 pp（12.5×）** |

**同一 87 个任务 × 3 seed、同一代码路径、同一模型名**，`plain_llm` 检出率从 **1.5% 升至 19.2%**（**12.5 倍**），三个 seed 全部同向，**无一例外**。

> **关键的推论**：项目存档中**完整系统 `aitester` 的检出率是 15.8%**。而当前模型下**最简单的 `plain_llm` 基线已达 19.2%**——即在今天的模型上，**一次裸 LLM 调用就已超过项目存档中完整多智能体系统的头条数字**。

### 11.3 独立复现的方向性结论（跨全部 5 次新跑）

| 运行 | 任务数 | `plain_llm` 检出 |
|---|---|---|
| 存档（2026-10-06） | 261 | **1.5%** |
| 本次 A（3 臂） | 8 | 12.5% |
| 本次 B（3 臂） | 25 | **24.0%** |
| 本次 C（fresh cache） | 10 | 20.0% |
| 本次 D（fresh cache） | 10 | 10.0% |
| 本次 E（fresh cache） | 10 | 20.0% |
| 本次 F/G/H（87 任务 ×3 seed，fresh cache） | 261 | **19.2%**（13.8/20.7/23.0） |

**6 次独立新跑全部落在 10–24% 区间；存档为 1.5%。两者不重叠。**

### 11.4 判定（A 级证据）

1. **项目的存档批次在当前 API 上不可复现。** 证据链：① 存档测试重放 87–100% 精确复现指标（排除指标漂移）；② 同任务同 seed 新跑检出率高出一个数量级（排除任务采样差异）；③ 缓存已隔离（排除缓存复用）。
2. **最可能的原因是 API 侧模型已更新**（`deepseek-flash` 是**浮动别名**，非版本锁定标识），而 **`provenance` 只记录别名、不记录任何可校验的模型版本指纹**。项目文档中亦可见别名漂移痕迹（`.env.local` 注释："历史别名 `deepseek-v4.1-flash` 已弃用"）。此归因为**推测（E 级）**；可确认的**事实（A 级）**是"同别名下产出显著不同"。
3. **方向对项目不利**：漂移使**最简单的 `plain_llm` 臂**大幅变强（1.5% → 19.2%），而 `aitester` 在新跑中为 **8.0%**（seed 42，87 任务）。详见 §11.4b 的配对对照——**aitester 相对 plain_llm 的位次已反转**。
4. **对项目所有历史结论的影响**：主批次 `detection` 数字（df 44.8% / aitester 15.8% / plain_llm 1.5%）中的 **`plain_llm` 基线已失效**；`df` 与 `aitester` 的**差值**需在当前模型上重测才能引用。**在此之前，项目不得再引用 1.5% 与 −28pp 这一对数字。**

### 11.4b **决定性配对对照：`aitester` 与 `plain_llm` 的相对位次在 seed 42 上发生反转**

**设计**：seed 42、**同样的 87 个任务**、**同一代码路径**、同 `AITESTER_PROFILE=logic`、**各自全新空缓存**。
存档对照组取自 `benchmark_synthetic_20261006_140906.json`（同 seed 42 同 87 任务）。

| 臂 | **存档（2026-10-06）** | **本次新跑（fresh cache）** | 变化 |
|---|---|---|---|
| `aitester`（完整系统） | 12/81 = **14.8%** | 7/87 = **8.0%** | **-6.8 pp** |
| `plain_llm`（裸 LLM 单提示） | 1/87 = **1.1%** | 12/87 = **13.8%** | **+12.7 pp** |
| **配对差（aitester - plain_llm）** | **+13.7 pp**（完整系统领先） | **-5.7 pp**（**裸 LLM 反超**） | **符号反转** |

**新跑配对检验**（n=87，同任务配对）：aitester 独占胜出 **5** 个任务，plain_llm 独占胜出 **10** 个任务，
exact McNemar **p = 0.30**（**不显著**）。

**判定（A 级事实 / 谨慎归因）**：
1. **可确认的事实**：存档批次中 `aitester` 显著优于 `plain_llm`（14.8% vs 1.1%）；在**当前 API** 上
   该**相对位次反转**为 `plain_llm` 领先（13.8% vs 8.0%），尽管该差值本身不显著（p=0.30）。
2. **不得过度归因**：p=0.30 意味着**尚不能断言「模型漂移导致 aitester 变差」**；能断言的是
   **「存档中 aitester 领先 plain_llm 这一结论在当前模型上不再成立」**。
3. **对项目对外主张的直接影响**：项目在 `README.md:56` 与全部历史报告中把
   「aitester 15.8% > plain_llm 1.5%」作为**「编排至少优于裸 LLM」**的证据。**该证据在当前模型上已失效。**
4. **与 df 臂的关系**：本 seed 未重跑 `df`；此前 8/25 任务批次中 df 仍居首（37.5% / 48.0%）。
   综合看，**唯一在当前模型下持续领先的臂始终是「检出优先提示协议」（df），而非完整系统**。

### 11.5 建议（**P0，最高优先**）

| # | 建议 | 理由 |
|---|---|---|
| **D1** | **把模型版本纳入 provenance 并强制可校验**：记录 API 返回的 `model` 字段（而非请求的别名）、`system_fingerprint`（若有）、以及一次固定的**探针补全**（例如固定 prompt 的贪心输出哈希）。缺少其中任一 → 批次标记为 `model_version_unpinned` | 当前无法判断历史批次与当前是否为同一模型 |
| **D2** | 在报告中**显式声明结果绑定于某个模型快照**，并把"模型漂移"列为与数据污染同级的一等有效性威胁 | ULT（TOSEM 2026）正是把污染列为一等约束的先例 |
| **D3** | **在当前模型上重跑主批次三臂**（87×3 seed，约 30 分钟/臂），重新建立基线；旧基线归档为 `historical` | 漂移已实测发生，旧基线不可再引用 |
| **D4** | 在 `preregistration` 中增加"模型快照失效即实验作废"的**停止规则** | 避免跨模型版本混合统计 |

---

**注意**：脚本 5、6、11 会产生真实 API 计费。
