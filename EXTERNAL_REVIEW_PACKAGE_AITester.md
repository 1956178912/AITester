# AITester 独立外部评审报告

**评审对象**：`/Users/wangchenyu/Workspace/AITester`（逻辑驱动的多智能体测试生成与自修复系统）
**评审时点**：2026-10-11（Asia/Shanghai）
**代码快照**：HEAD `d9e51df` + 工作树（35 个已修改文件未提交）
**评审性质**：**独立评审**——不采信项目内既有评审、自评数据、基线数字与前沿引用数值
**报告版本**：外部评审版（自包含，无需其他文件即可评估）

---

## 给外部评审者的导读

### 这份报告的立场

我**没有**采信仓库里任何既有材料。仓库内存在至少 4.2 MB 的既有审查产物（6 份根目录审查报告、`audit_2026/` 5 份、`review_2026/` 21 份、`.private/review/` 15 份）。它们在本报告中**只是复核对象**，不是事实来源。本报告每一条结论都来自：

1. **我亲自重算的原始工件**（`experiments/results/**/*.json` 等）；
2. **我亲自访问的一手文献载体**（arXiv 摘要/全文、Crossref DOI 记录、会议官方 program、官方 GitHub、机构官方页）；
3. **我亲自发起的真实 LLM 调用**（DeepSeek 官方 API，约 146 万 token）；
4. **我亲自读的源码**（逐条给 `file:line`）。

### 证据分级（全文统一）

| 等级 | 定义 |
|---|---|
| **A** | 一手可验证：原始工件/论文正文/官方榜单/可复现实验，且可追溯到版本、提交或日期 |
| **B** | 一手但不可完全验证：仅有摘要级文本，或纸张/元数据层一手而正文缺失 |
| **C** | 二手转述：综述、博客、项目内引用、第三方索引 |
| **D** | 不可验证：无法定位承载该数值的一手来源 |
| **E** | 推测：基于理论或类比推断，无直接实证 |

**规则**：A 级可独立支撑关键结论；B 级需两个独立来源交叉验证；C 级不得单独支撑关键结论；D 级不得支撑任何结论；E 级必须显式标注为推测。

### 三条阅读规则（避免误读本报告）

1. **本报告的批评不是"项目造假"。** 我重算的 14 项头条指标中 **9 项与项目声称逐位一致**。问题不在数字，**在数字能支撑什么**。
2. **"不可验证"不等于"不成立"。** 本次会话中 IEEE Xplore（HTTP 202 空体）、ACM DL（403 + Cloudflare）、OpenAI 官方页（403）被拦截，Semantic Scholar 持续 429。凡以这些域为唯一载体的数值，我只能标注"未能独立核实"。
3. **本报告不给"项目落后前沿 X%"的结论**，因为在当前实验条件下，这样的结论**无法被任何证据支撑**（理由见 §3）。

### 如何独立验证（关键证据的一键复现）

```bash
cd /Users/wangchenyu/Workspace/AITester

# 1) 重算头条三臂指标（零 LLM，读原始工件）
python - <<'EOF'
import json
for f in ["benchmark_synthetic_20261006_140906.json",
          "benchmark_synthetic_20261006_151907.json",
          "benchmark_synthetic_20261006_164357.json"]:
    d = json.load(open("experiments/results/main_batch/"+f))
    for arm, blk in d["results"].items():
        v = [r.get("detection_rate") for r in blk["details"]]
        v = [x for x in v if x is not None]
        print(f, arm, f"{sum(1 for x in v if x>0.5)}/{len(v)}")
EOF
# 期望：aitester 38/240、plain_llm 4/261、plain_llm_df 117/261

# 2) 证明基准只有 26 个唯一程序体（零 LLM）
python - <<'EOF'
import sys, re, hashlib, collections
sys.path.insert(0, ".")
from src.datasets.synthetic_dataset import SyntheticDataset, BUG_PATTERNS
print("BUG_PATTERNS =", len(BUG_PATTERNS))               # 16
ts = list(SyntheticDataset(task_count=87, seed=42))
h = collections.Counter(hashlib.sha256(
    re.sub(r"#.*", "", t.instance_code).strip().encode()).hexdigest() for t in ts)
print("tasks =", len(ts), "| unique bodies =", len(h))   # 87 | 26
EOF

# 3) 证明真实仓库补丁从未成功应用（零 LLM，读原始日志）
python - <<'EOF'
import json, glob
for f in sorted(glob.glob("experiments/results/raw/sqlfluff__*/aitester.json")):
    d = json.load(open(f))
    rv = (d.get("repo_verification") or {}).get("output", "")
    print(d["task_id"], "| llm_patch_apply_failed:", "llm_patch_apply_failed" in rv)
EOF
# 期望：全部 20 个 task 均为 True

# 4) 证明 JSON 数组解析缺陷（零 LLM，纯函数）
python -c "
from src.utils.helpers import extract_json_object
try: extract_json_object('[\"a\",\"b\"]')
except Exception as e: print('RAISES:', e)"
# 期望：RAISES: No JSON found in response
```

**会产生真实计费的复现命令**（真实 LLM 调用）见 §7.2 的 T1/T2/T3 与 §11.1。

---

## 0. 执行摘要

### 0.1 一句话定位（独立判断）

> **AITester 不是"逻辑驱动的多智能体测试生成与自修复系统"。它是一个测量纪律异常严格、工程化程度远超同类科研代码的"检出优先（detection-first）测试生成研究平台"——其自称的两个核心机制（多智能体编排、逻辑驱动闭环）或为负贡献、或未接线；而其全套基准与唯一一次真实仓库基准都不能支撑任何对外有效性主张。**

### 0.2 关键发现（每条附本次独立实测证据与证据等级）

| # | 发现 | 独立证据 | 等级 |
|---|---|---|---|
| **F1** | **核心主张被自身数据否定：完整系统显著劣于单提示协议，成本高 5.5 倍。** `plain_llm_df`（单次 LLM 调用 + 检出优先提示）检出率 **44.8%**，完整多智能体系统 `aitester` **15.8%**；aitester 每任务输出 token **20,056** vs df **3,640** | 我重算三批次工件：38/240、4/261、117/261；token 逐臂求和 | **A** |
| **F2** | **该负结论经聚类稳健检验后依然成立，但真实效应比头条小。** 任务级配对 n=240 得 δ=−28.3pp（exact McNemar p=1.7e-13）；**按"唯一程序体"聚类后 n=26**，δ=**−24.6pp**，95% CI **[−33.7,−15.6]**，配对 t=−5.36，符号检验 p=0.0001 | 我自建聚类分析（项目未做聚类校正，p 值与 CI 过窄） | **A** |
| **F3** | **基准外部有效性为零：全部头条数字来自项目自建合成集，87 个"任务"实为 26 个不同程序体。** 模板库 `BUG_PATTERNS` 仅 **16** 个；噪声只是行尾注释 `# noise_seed=` | 我实跑 `SyntheticDataset(task_count=87, seed=42)` 逐任务哈希 | **A** |
| **F4** | **唯一一次真实仓库基准（SWE-bench Lite）全链条失效，失败在基础设施而非算法。** aitester 臂 20/20 失败，**每个 task 都记录 `llm_patch_apply_failed`**，且 `FAIL_TO_PASS baseline` 与 `after-llm-patch` **逐任务完全相同**（证明补丁从未生效） | 我逐个解析 `experiments/results/raw/sqlfluff__*/*.json` 的 `repo_verification.output` | **A** |
| **F5** | **"逻辑驱动"对约半数任务空转。** 全量 1,607 个 aitester 结果行 `spec_compile_rate`：**中位数 0.200、47.6% 为 0**、仅 12.2% 达 1.0 | 我遍历全仓工件统计分布 | **A** |
| **F6** | **头条"闭环"未接线。** `README.md:59` 称"逻辑驱动反例精化**闭环**（CEGIR）"，但 `src/specs/spec_refine.py:22-24` 自述"**不接入主链路**"，全仓对 `spec_refine`/`CEGIR` **零引用**；`README.md:1376` 自己也写明"未接入主链路"——**同一文档两处互相矛盾** | 全仓 grep + 源码自述 | **A** |
| **F7** | **覆盖率与变异得分在合成集上饱和，无鉴别力。** 任务级 line coverage 中位数：aitester **98**、plain_llm **100**、df **98**（**88.1%/98.9%/98.1% 的任务达 100%**）；而检出率仅 15.8%/1.5%/44.8%。项目自己也在 `BASELINE.yaml:56` 承认"鉴别力有限" | 我逐任务统计 `details[].coverage` | **A** |
| **F8** | **验证 oracle 与生成 oracle 同源，修复正确性从未被独立判定。** 所谓"P2P 全量回归"实为**重跑系统自己生成的单个测试文件**（`src/graph/nodes.py:2044-2049` → `patch_rollback.py:189` 的 `pytest test_path -q`）；logic 档 `PATCH_ROLLBACK_FAIL_CLOSED=true` 使 rc≥2/超时一律回滚 → **测试自身有瑕疵即误杀正确修复** | 源码证据链 | **A** |
| **F9** | **记账与独立性两条支柱在同一批工件内失效。** 4 份 logic 档批次中 `plain_llm`/`plain_llm_df` 的 `token_usage` **全字段为 0**（含 `llm_calls`），而 `generated_test` 非空；另有同 seed 两份批次（git_sha 不同）3 臂 × 87 任务 `generated_test` **逐字节相同** | 我逐批次逐臂统计 | **A** |
| **F10** | **引用完整性是真实强项：8 个 DOI/arXiv 标识符零伪造、零张冠李戴。** CANDOR（TOSEM 2026, `10.1145/3803418`）的 0.991/0.970/0.980 与原文表 1 **精确一致**；BOAD 经 IBM Research 官方页确认为 ICLR 2026；Zhao 等为 ISSTA 2026 **Distinguished Paper**。**但 1 处数值误述**：Konstantinou 论文请求数项目写 11,718/12,264，原文为 **11,815/12,741** | 独立联网核实 13 条标识符 | **A** |
| **F11** | **工程化质量远超同类科研代码。** 我独立实跑全量测试：**5390 passed / 3 skipped / 1 xfailed，耗时 200.6s，0 failed**（收集 5394）。但门禁有真实缺口（见 F12） | 我实跑 `pytest tests/` | **A** |
| **F12** | **文档数字漂移且守卫放行。** `BASELINE.yaml:17` 字段值 `total_passed: 5389`，同字段注释写"实测 **5323** passed"；我实测 **5390**。三者互不相等。守卫只校验 `declared ≤ collected` 且差额 ≤9，故陈旧值仍判绿 | 实跑 + 逐行核对 | **A** |
| **F13** | **【最高优先】项目存档主批次在当前 API 上不可复现（模型漂移）。** 同一 87 任务 × 3 seed、同命令、同代码路径、同模型名 `deepseek-flash`，仅隔离 LLM 缓存：`plain_llm` 检出率 **1.5%（4/261）→ 19.2%（50/261）**，三 seed 全部同向。**指标本身稳定**（存档测试重放 87–100% 精确复现）。详见 §2.6（模型漂移专项） | 我发起真实调用的对照实验 | **A** |
| **F14** | **"逻辑驱动"失效根因被定位到提示-文法契约，而非求解器。** 真实调用下 planner 对 3 个函数中的 2 个返回 `logic_degraded=True`（空规约）；唯一成功者产出**自然语言**规约（`"text 为 str 类型"`、`"成功时返回 int 类型结果"`），而编译器白名单只接受形式表达式 → **编译产物恒 0 字节**。z3 求解本身实测完全正确（`r>0 ∧ r<0` → `unsat`） | 我发起真实 LLM 调用的链路测试 | **A** |
| **F15** | **`ADVERSARIAL_DEBUGGING_ENABLE` 是死代码——从设计上永远不可能生效。** `_extract_json` 委托的 `extract_json_object` **只解析 JSON 对象、从不解析顶层 JSON 数组**（实测 `'["a","b"]'` → `JSONDecodeError`），而该能力要求 LLM 输出数组。LLM 实际输出的假设质量很高，但被解析器全部丢弃 | 我显式开启该开关后真实调用 + 纯函数证明 | **A** |

### 0.3 数据可信度总览

| 类别 | 条目数 | 本次可独立验证 | 无法验证 / D 级 | 备注 |
|---|---|---|---|---|
| 项目性能声明 | 14 项核心 | **11** | 3 | 2 项因记账缺陷不可算，1 项为口径歧义 |
| 项目引用外部文献 | 13 条标识符 | **8 属实** | **5** | 含 1 处数值误述；最重"负面证据"四值不可复核 |
| 前沿 SOTA 数值 | 30+ 数据点 | 见 §3 各表等级列 | **27 项（D1–D27）** | 自修复与形式化两方向一手数值最稀薄 |
| **模型快照可复现性** | 1 项（主批次三臂基线） | — | **1（不可复现）** | F13；`provenance` 无可校验版本指纹 |
| 既有评审结论 | 抽样 12 条 | **支持 5 / 部分支持 3** | **推翻 2 / 口径有误 1**（另 1 条计数未复核） | 见 §8 |

### 0.4 竞争位置判定（独立结论）

**项目在 2025–2026 前沿格局中不具备任何可验证的竞争优势。** 三条独立理由：

1. **同口径不可比。** 项目主指标是"fail-to-pass 检出率"。我核实了 TestGenEval（line coverage 35.2% / mutation 18.8%）与 ULT（statement 45.10% / mutation 40.21%）的分子分母后确认：**2025–2026 一手前沿基准中没有一份报告 fail-to-pass 检出率**。因此 44.8% **在文献中找不到同口径对手**——既不能被证明超越前沿，也不能被证明落后。
2. **可比的维度上项目无真实数据，且先前实测失败。** 若以覆盖率/变异得分对比，项目仅在合成集上有数（且饱和到 98%/0.98，鉴别力为零）；在真实 Python 代码上**唯一一次尝试是 SWE-bench Lite 0/20，失败于补丁无法应用**（F4）。
3. **项目的"编排"这一差异点被自身数据否定。** 受控对照（同模型、同温度 0.0、同 `max_iterations=3`、以 seed 配对）下，增加编排带来 **−24.6pp**（95% CI [−33.7,−15.6]）与 **5.5× 输出 token**。这与 ICST 2026 独立复现的结论同向（Plain-LLM 49.95% line 全面优于 HITS/SymPrompt/CoverUp/TestSpark）。

**可以主张的窄结论（有证据支撑）**：

- 项目的**测量纪律**（预注册、口径矩阵、25 份 ADR、三次测量伪影事后更正）达到可发表的工程标准；
- 项目的**引用完整性**优于多数同类项目（8/13 标识符完全属实、0 伪造）；
- 项目**较早地把"高覆盖 ≠ 高检出"落到可测量协议上**（`src/measurement/mdo.py` 的 MTR/MDR/CRASH 三分解），与 MUTGEN（TSE 2026："100% 覆盖但仅 4% 变异得分"）、LM2Alloy（"68% 分支覆盖但三次运行全漏同一真实缺陷"）的一手发现同向。**这是项目唯一具备前沿对话资格的资产**（见 §6）。

---

## 1. 项目理解与边界

### 1.1 实际执行路径（读源码所得，非文档）

`src/graph/workflow.py:40` 的 LangGraph StateGraph：

```
Planner → Generator → Executor → [Debugger → PatchApplier] × N(≤3) → END
```

三臂对照的实际定义（`experiments/run_benchmark.py:201/217/381`）：

| 臂 | 实际实现 | 声称 | 本次核实 |
|---|---|---|---|
| `aitester` | `build_workflow()` 完整图（planner+debugger，逻辑档 12+ 开关全开） | 完整系统 | ✅ 一致 |
| `plain_llm` | `build_workflow(planner=False, debugger=False)` | "仅一次调用" | ⚠️ **仍是完整 LangGraph 图**，仅关闭两个节点；同文件 `:226-230` 注释自认"此前 plain_llm 跑的是完整管线" |
| `plain_llm_df` | 同上 + `set_detection_first_thread_override(True)` | 检出优先提示基线 | ✅ 一致，**这是最强的臂** |

**关键公平性事实**：三臂**同模型**（`deepseek-flash`）、**同温度**（0.0）、**同 `max_iterations`**（3）、**同 seed 配对**（`provenance` 实测确认）。**因此 F1 的对比是公平的**——不存在"给 AITester 更多预算/更多轮"的不公平。相反，aitester 是**唯一开满 12+ 逻辑档开关**的臂，仍显著落后。

### 1.2 "逻辑驱动"的真实边界（源码自述，我逐条核对属实）

`src/specs/spec_smt.py:17-31` 自述能力边界：

- **支持**：布尔 / 比较 / `+-*/%` / 常量 / 名称；前件 SAT 见证、数值目标 optimize、前件 UNSAT（空洞化）检测、后件自一致性 UNSAT 检测；
- **不支持**：函数调用（`len()` 等）、幂、下标、属性访问 → 整体保守跳过返回 `[]`；
- **z3 真实存在**（实测 **z3 5.1.0** 已安装），SMT 层是真调用求解器，不是轻量仿制。**这是"逻辑驱动"主张中最扎实的一块。**

但**规约本身由 LLM 从自然语言生成**，再经白名单 AST 编译。实测结果见 F5/F14：**47.6% 的任务产不出任何可编译子句，中位数 0.2**。

### 1.3 关键假设的红队审查

| 假设 | 红队反证 | 判定 |
|---|---|---|
| "系统是逻辑驱动的" | 规约由 LLM 生成（非形式化推导）；47.6% 任务零可编译子句；CEGIR 未接线 | **不成立（当前形态）** |
| "多智能体编排带来增益" | 受控配对 δ=**−24.6pp**，CI [−33.7,−15.6]；成本 5.5× | **被自身数据推翻** |
| "自修复能力存在" | 主批次三臂 repair 全为 **0.0**；39.31% 来自**存量重放**而非当次运行；真实仓库上补丁从未成功应用 | **无当次证据** |
| "合成基准可代表真实能力" | 16 模板 / 87 标签 / **26 唯一程序体**；coverage 与 mutation 双饱和；bug、gold、oracle 同源编写 | **不成立** |
| "闭环收敛" | 停止条件是 `MAX_ITERATIONS=3` 固定上限，非收敛判据；`avg_iterations`：aitester 1.10 / df 0.00 | **无收敛证据** |
| "测试质量可独立于修复策略度量" | **该假设被项目自己识别并纠正**（`src/measurement/mdo.py` 明确指出 `detection_rate` 与修复策略数学耦合） | **项目已自纠，本次确认** |

---

## 2. 核心发现详述

### 2.1 核心主张被自身数据否定（F1/F2）

**数据源**：`experiments/results/main_batch/benchmark_synthetic_20261006_{140906,151907,164357}.json`（seed 42/43/44，各 87 任务 × 3 臂）。

| 臂 | detection | 占比 | repair | false_fix | avg coverage | tokens/task |
|---|---|---|---|---|---|---|
| `aitester` | 38/240 | **15.8%** | 0.0% | 59.6% | 97.2 | 26,115 |
| `plain_llm` | 4/261 | **1.5%** | 0.0% | 87.7% | 99.5 | 3,209 |
| `plain_llm_df` | 117/261 | **44.8%** | 0.0% | 2.7% | 98.3 | 4,223 |

**统计检验（我独立重算）**：

| 口径 | 统计量 | 值 |
|---|---|---|
| 任务级（项目口径） | n / δ / exact McNemar p | 240 / **−28.3pp** / **1.7×10⁻¹³** |
| **聚类稳健（唯一程序体，方法学上正确）** | n / δ / 95% CI / t(df=25) / 符号检验 | **26** / **−24.6pp** / **[−33.7, −15.6]** / **−5.36** / **p=0.0001** |
| 分 seed 波动 | aitester / df | 13.8–19.0% / 41.4–49.4% |

**共同支撑校正（我补充）**：项目对 aitester 用分母 240（剔除 21 行 `None`），对另两臂用 261。只保留三臂均可测的 240 个任务后：aitester 15.8%、plain_llm **1.7%**、df **44.2%**，δ=−28.3pp。**结论方向不变。**

**判定**：负向结论在三种方法下一致显著，**不是伪影**；但项目把 87 个标签当独立样本，**把精确度高估约 3.35 倍**（240 行 → 26 簇）。

### 2.2 基准外部有效性为零（F3/F7）

我实跑项目自己的生成器：

| 事实 | 实测值 | 证据 |
|---|---|---|
| `BUG_PATTERNS` 模板数 | **16** | `src/datasets/synthetic_dataset.py:36-56`；实跑 `len(BUG_PATTERNS)=16` |
| 生成任务数 | 87 | `len(list(SyntheticDataset(task_count=87, seed=42)))` |
| **去注释后唯一程序体数** | **26** | 逐任务 `sha256(re.sub(r'#.*','',instance_code).strip())` |
| 重复度 | 最大 **9 次**，另有 7、6、5 次 | `Counter` |
| 噪声形式 | **行尾注释** `# noise_seed=4386` | `synthetic_dataset.py:2401,2482` |

**覆盖率饱和（同一批任务）**：

| 臂 | p25 | median | 100% 任务占比 |
|---|---|---|---|
| aitester | 93 | **98** | **88.1%** |
| plain_llm | 100 | **100** | **98.9%** |
| plain_llm_df | 91 | **98** | **98.1%** |

**判定**：`plain_llm`（无编排、无修复、近乎一次调用）即达 **98.9% 任务满覆盖**——**该指标在此基准上完全无鉴别力**。且 bug、gold、gold 测试三者同源编写，构成**自出题 + 自备标准答案的自评测循环**。

### 2.3 唯一一次真实仓库基准全链条失效（F4）——**最重要的单一发现**

项目在 `README.md:56` 诚实披露"SWE-bench Lite（sqlfluff-20）**0/20**"。我独立追查到**两代工件**，结论比"0/20"更严重：

**工件 A**：`experiments/results/swe_bench_lite_20/benchmark_swe_bench_20260818_113525.json`（2026-08-18，n=20）
- `passed=0/20`、`avg_coverage=0.0`、`error_category ∈ {syntax:19, timeout:1}`；
- `provenance=null`、`environment=null`、`repo="unknown"`（**无环境快照、无 git_sha**）；
- 根因：`~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl` **为 0 字节**，且**全仓无 enrichment JSONL** → `dataset_loader.py:626` 的 `instance_code = data.get("instance_code") or ... or problem_statement` **兜底为 issue 文本** → 19/20 任务拿到自然语言文本而非 Python 源码 → 必然 `SyntaxError`。

**工件 B（更关键）**：`experiments/results/raw/sqlfluff__*/{aitester,plain_llm,single_agent}.json`（2026-09-25，17 任务 × 3 臂）——**这是真实执行**（`generated_test` 非空、coverage 非零、token 非零）。但 aitester 臂：

| Task | FAIL_TO_PASS baseline | FAIL_TO_PASS after-patch | 判定 |
|---|---|---|---|
| sqlfluff-1625 | 0/1 | **0/1（完全相同）** | `llm_patch_apply_failed` |
| sqlfluff-2326 | 0/51 | **0/51（完全相同）** | `llm_patch_apply_failed` |
| sqlfluff-2336 | 14/14 | **14/14（完全相同）** | `llm_patch_apply_failed` |
| sqlfluff-2849 | 0/18 | **0/18（完全相同）** | `llm_patch_apply_failed` |
| sqlfluff-3904 | 82/117 | **82/117（完全相同）** | `llm_patch_apply_failed` |
| …（其余 5 个同样） | — | **完全相同** | `llm_patch_apply_failed` |

**判定（A 级）**：
1. **"before" 与 "after" 逐任务完全相同**，是"补丁从未生效"的直接证据；
2. 每条都显式带 `[llm_patch_apply_failed] 补丁未成功应用` 标记；
3. 补充观察：部分任务的 `FAIL_TO_PASS baseline` 本身非零（2336 为 14/14、3904 为 82/117），说明这些用例在缺陷代码上**本就通过**，其 F2P 标注与实测环境不一致（环境/依赖不完整）。

> **结论**：**AITester 从未在任何真实仓库任务上成功应用过一个补丁。** 因此项目对外**没有任何真实代码上的功效证据**。这不是"结果不好"，而是"该实验尚未具备产出有效结果的条件"。

### 2.4 逻辑驱动失效的真实机制（F5/F14）

**(a) 全量统计（1,607 个 aitester 结果行）**

| 统计量 | 实测值 |
|---|---|
| 均值 | 0.320 |
| **中位数** | **0.200** |
| **恰好 0.0（零可编译子句）** | **765 行 = 47.6%** |
| 恰好 1.0 | 196 行 = 12.2% |

**(b) 真实 LLM 调用下的链路测试（我发起）**

| 函数 | `logic_degraded` | pre/post/inv/edge | `readiness` | 编译产物长度 |
|---|---|---|---|---|
| `divide` | **True** | 0/0/0/0 | 0.0 | **0** |
| `find_max` | **True** | 0/0/0/0 | 0.0 | **0** |
| `parse_age` | False | 2/3/0/11 | 1.0 | **0** |

`parse_age` 的规约内容是**自然语言**：

- `preconditions[0] = "text 为 str 类型"`
- `postconditions[0] = "成功时返回 int 类型结果"`

这些**不是可编译的 SpecExpr**（白名单只接受布尔/比较/算术表达式），故 `compile_spec_oracle` 产出 0 字节，log 记录 `SpecIR v2 oracle 产物自检失败，保守丢弃`。

**同时观察到强校验拒绝链**（logic 档 `LOGIC_SPEC_STRICT_ENABLE=true`）：
```
M10：LLM 未输出 logic_analysis，已填充空值并标记 logic_degraded=True
M10 强校验拒绝已降级：logic_analysis 缺失，拒绝静默兜底
M10 schema 校验：5 条 findings
M10 强校验后续拒绝：logic_analysis schema 校验失败，拒绝静默兜底
```

**(c) 判定**：**"逻辑驱动"的失效点在于 planner 要求 LLM 在"自然语言 vs 形式表达式"之间选择时，LLM 系统性选择自然语言，而编译器只接受形式表达式。这是提示-文法契约缺陷，不是求解器缺陷**（z3 实测 `r>0 ∧ r<0` → `unsat`，完全正确）。这条根因比统计描述更精确，可直接指导修复（成本远低于扩展文法）。

**(d) 项目 benchmark 内独立复现**：25 任务批次中 aitester 的 `spec_compile_rate` **19/25 为 0（中位数 0.0）**，8 任务批次中 **7/8 为 0**。

### 2.5 验证闭环的结构性缺陷（F8）

| 环节 | 项目声称 | 源码实际 | 后果 |
|---|---|---|---|
| 补丁验证 | "**P2P 全量回归**" | `src/graph/nodes.py:2044-2049` 只把 `state["generated_test"]` 传给协议；`patch_rollback.py:189` 子进程仅 `pytest test_path -q` | **重跑系统自己生成的单个测试文件**，不是既有测试套件回归 |
| 判据独立性 | "验证正确性" | 验证 oracle 与生成 oracle **同源**（同一个 `generated_test`） | 测试自身有瑕疵即**误杀正确修复** |
| fail-closed | "回归失败自动回滚" | `patch_rollback.py:198-213` + logic 档 `PATCH_ROLLBACK_FAIL_CLOSED=true` → rc≥2/超时/无测试**一律回滚** | 坏测试把正确修复判为回归失败并回滚 |
| test-hacking 守卫 | `README.md:62` 称"守卫" | `patch_test_hacking.py:20-27` 自述判定核是**观测层**（"命中即拒绝补丁"属"阻断档（待 A/B 后转正）"）；唯一调用点只写结果行 | **是检测信号而非守卫** |

**本次真实调用中该机制的现场证据**（25 任务批次日志，12 行）：

```
A-03 P2P 回归失败（rc=1），自动回滚补丁（snapshot=5a335a1921b3）
A-03 P2P 回归失败，补丁已自动回滚（verdict=regression_failed, snapshot=5a335a1921b3, disk_restored=True）
```

**回滚确实在运行并成功落盘恢复。** 但：

| 字段 | 声明位置 | 实测（75 行结果） |
|---|---|---|
| `patch_rollback_verdict` | `BASELINE.yaml` `metrics_schema`；`src/graph/state.py:321` | **100% 缺失** |
| `patch_rolled_back` | 同上 | **100% 缺失** |

`experiments/run_benchmark.py` 中 grep 这两个字段**命中 0 次**——观测字段写入 state 后**从未被 result-row builder 消费**。**该能力在工件层不可审计。**

**test-hacking 守卫的实测攻击面**（我构造 5 类绕过）：

| 作弊构造 | `suspected` |
|---|---|
| 硬编码 `if x == 5: return 6` | 依输入而定（常量返回可被捕获） |
| 硬编码经变量 `y = 6; return y` | **False（绕过）** |
| 映射表后门 `table = {5: 6}` | **False（绕过）** |
| 吞异常 `except Exception: return x` | **False（绕过）** |
| **删除断言 / `assert True` / `pytest.skip`** | **不可见**——函数签名**不接收 `generated_test`** |

且我实测头条批次 `test_hacking_*` 字段**一个都不存在**（从未产数）。

### 2.6 【最高优先】项目存档主批次在当前 API 上无法复现（F13）

这是本次评审**最重要的发现**，其严重性高于其他任何一条。

**对照设计**（两组唯一差异 = 缓存状态）：

| 组 | 数据 |
|---|---|
| **A（存档）** | `experiments/results/main_batch/benchmark_synthetic_20261006_*.json`（seed 42/43/44，项目头条数字来源） |
| **B（本次新跑）** | 同命令、同 `--dataset synthetic --task-count 87`、同 seed、同 `AITESTER_PROFILE=logic`、同模型名 `deepseek-flash`；**唯一差异**：`AITESTER_LLM_CACHE_DIR` 指向**全新空目录** |

**首先排除"我的执行/指标口径有误"**：我把**存档里的 `generated_test` 原文**重新执行到 buggy / gold 两侧，用与项目相同的 F2P 三段判定复算 `detection_rate`：

| 臂 | 可重放条数 | 与存档 `detection_rate` **一致** |
|---|---|---|
| `aitester` | 22 | **21/22 = 95%** |
| `plain_llm` | 23 | **23/23 = 100%** |
| `plain_llm_df` | 23 | **20/23 = 87%** |

→ **指标定义与执行语义是稳定的**（少数不一致为跨文件任务的 `rc=2` 收集错误，属我的重放脚手架未物化伴生模块）。

**结果**：

| seed | 存档 `plain_llm` | 本次新跑 | 绝对偏移 |
|---|---|---|---|
| 42 | 1/87 = **1.1%** | **12/87 = 13.8%** | +12.6 pp |
| 43 | 1/87 = **1.1%** | **18/87 = 20.7%** | +19.5 pp |
| 44 | 2/87 = **2.3%** | **20/87 = 23.0%** | +20.7 pp |
| **合并（n=261）** | **4/261 = 1.5%** | **50/261 = 19.2%** | **+17.7 pp（12.5×）** |

**决定性配对对照（同 seed 42、同 87 任务）**：

| 臂 | 存档 | 新跑 | 变化 |
|---|---|---|---|
| `aitester`（完整系统） | 12/81 = **14.8%** | 7/87 = **8.0%** | −6.8 pp |
| `plain_llm`（裸 LLM） | 1/87 = **1.1%** | 12/87 = **13.8%** | +12.7 pp |
| **配对差（aitester − plain_llm）** | **+13.7 pp**（系统领先） | **−5.7 pp**（**裸 LLM 反超**） | **符号反转** |

新跑配对检验（n=87）：aitester 独占胜出 5 个任务，plain_llm 独占胜出 10 个，exact McNemar **p = 0.30（不显著）**。

**判定（A 级事实 / 谨慎归因）**：
1. **可确认**：存档批次中 `aitester` 显著优于 `plain_llm`（14.8% vs 1.1%）；在当前 API 上该**相对位次反转**（13.8% vs 8.0%），尽管差值本身不显著。
2. **不得过度归因**：p=0.30 意味着**尚不能断言"模型漂移导致 aitester 变差"**；能断言的是**"存档中 aitester 领先 plain_llm 这一结论在当前模型上不再成立"**。
3. **最可能原因是 API 侧模型已更新**（`deepseek-flash` 是**浮动别名**），而 **`provenance` 只记录别名、不记录任何可校验的模型版本指纹**。项目文档亦可见别名漂移痕迹（`.env.local` 注释："历史别名 `deepseek-v4.1-flash` 已弃用"）。此归因为**推测（E 级）**；可确认的**事实（A 级）**是"同别名下产出显著不同"。
4. **对项目的直接影响**：项目在 `README.md:56` 与全部历史报告中把"aitester 15.8% > plain_llm 1.5%"作为**"编排至少优于裸 LLM"**的证据。**该证据在当前模型上已失效。** 且**当前模型下一次裸 LLM 调用（19.2%）已超过存档中完整系统的 15.8%。**

### 2.7 记账与独立性缺陷（F9）

**(a) token 记账在某批次内整臂为零**

| 批次 | aitester | plain_llm | plain_llm_df |
|---|---|---|---|
| 20261006_140906 (s42) | 87 非零 | 87 非零 | 74 非零 / **8 缺失** |
| 20261006_151907 (s43) | 87 非零 | 87 非零 | 74 / **13 缺失** |
| 20261006_164357 (s44) | 87 非零 | 87 非零 | 73 / **14 缺失** |
| 20261007_161053 (s42) | 87 非零 | **87 全零** | **87 全零** |
| 20261007_170147 (s44) | 87 非零 | **87 全零** | **87 全零** |
| 20261007_181638 (s42) | 27 非零 / **60 全零** | **87 全零** | **87 全零** |
| 20261007_185941 (s44) | 26 非零 / **61 全零** | **87 全零** | **87 全零** |

**影响**：4 份批次的**成本结论不可计算**（分母为零）；2026-10-07 之后 aitester 臂也开始大面积零记账 → **该时间点之后的成本对比全部失效**。引用成本必须绑定批次。

**(b) 同 seed 重放产出逐字节相同的结果**

我逐任务比对 `generated_test` 的 SHA256：

| 配对 | 逐字节相同 |
|---|---|
| `20261007_161053`(s42) vs `20261007_181638`(s42) | **87/87 = 100%**（3 臂全部） |
| `20261007_170147`(s44) vs `20261007_185941`(s44) | **87/87 = 100%**（3 臂全部） |

两批 `git_sha` 不同（`d3c3cc4e` vs `1a5a5a79`），却产出**完全相同**的测试 → **LLM 响应缓存命中，代码变更未生效**。

**(c) 但头条三批次是真正独立的**（我推翻了"n=261 是伪造重复"的怀疑）

跨 seed 的 `generated_test` **逐字节相同数 = 0/87（0.0%）**，任务 ID 集合交集 = 87/87。**但**簇内一致性检验暴露新问题：

| 臂 | 同一任务跨 seed 判定一致 | 占比 |
|---|---|---|
| aitester | 38/67 | **56.7%** |
| plain_llm | 83/87 | 95.4% |
| plain_llm_df | 29/87 | **33.3%** |

即**两臂的检出判定在换 seed 后仅 33–57% 一致**——点估计稳定性远低于 n=261 所暗示的水平。

**(d) LLM 缓存使"多次运行"退化为单次**（我实测确认）

| 条件 | 单次耗时 | 多次试验结果 |
|---|---|---|
| 缓存存在（默认 `~/.cache/aitester/llm/`，实测 **5,275** 个文件） | **≈0.8s** | **逐位相同** |
| 缓存清空 | **7.7s** | **发生变化** |

### 2.8 致命安全缺陷：对抗性调试是死代码（F15）

**现象**：显式开启 `ADVERSARIAL_DEBUGGING_ENABLE=true` 后，对抗性意图生成**恒定返回空列表**：
```
对抗性意图假设生成失败（跳过，3.1）: No JSON found in response: line 1 column 1 (char 0)
```

**根因（我以纯函数证明）**：`debugger.py:1016` 调用 `self._extract_json(raw)` 并期望返回 **list**，但该函数委托给：

```python
# src/utils/helpers.py:336
def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = _JSON_FENCE_STRIP_PATTERN.sub("", text)
    ...
    start = cleaned.find("{")          # ← 只找 '{'
    if start == -1:
        raise json.JSONDecodeError("No JSON found in response", text, 0)
```

**该函数只解析 JSON 对象，从不解析顶层 JSON 数组。** 实测：

| 输入 | 结果 |
|---|---|
| `'["a", "b", "c"]'`（合法 JSON 数组） | **RAISES** `JSONDecodeError: No JSON found` |
| `'Here are 3 hypotheses:\n["a", "b"]'` | **RAISES** |
| `'{"hypotheses": ["a"]}'` | OK dict |

**而 LLM 实际返回的是完全正确的 JSON 数组**（我抓取的原始响应，236 字符）：
```
[
  "当 b 为 0 时函数返回整数 0 而非 float，导致返回类型不一致（0 而非 0.0），下游若按 float 处理可能出错。",
  "当 a 或 b 传入非数值类型（如字符串、None、列表）时，`b != 0` 判断通过但 `a / b` 抛出 TypeError，函数崩溃。",
  "当 b 为浮点 0.0 或 False 等与 0 相等但类型不同的值时，返回整数 0 造成类型不一致；当 b 为极小非零浮点数时结果…"
]
```
**假设质量很高，但永远无法进入系统。**

**影响范围**：
1. `debugger.py:1016` 的 `isinstance(arr, list)` **永远为假**，唯一可用分支是 `{"hypotheses": [...]}`，但提示词明确要求"输出 JSON 数组"；
2. **连带失效**：Critic 评估（`debugger.py:1060`）依赖 `hypotheses`，而 `hypotheses` 恒为空 → `_build_adversarial_prompt_section` 恒返回空串 → **整个"对抗性推理（3.1）"能力从未生效**；
3. `oracle_enhancer.py:121-125` 同样期望 list（注释写"`_extract_json` 可能返回…或列表"——**该注释与实际能力不符**）→ 实测恒走"LLM 输出非列表，保守降级"。

**建议（P0）**：新增 `extract_json_array(text)`（对称实现，找 `[` 并做括号平衡），或让 `extract_json_object` 支持顶层数组并在返回类型上显式区分；同时修正 `oracle_enhancer.py:123` 的失实注释。

### 2.9 其余"声称 vs 实现"差异（我在真实调用下复核）

| # | 声称 | 实现反证（file:line） | 严重度 |
|---|---|---|---|
| C1 | `README:59` "逻辑驱动反例精化**闭环**" | `spec_refine.py:22-24` 自述"**不接入主链路**"；全仓零引用 | **P0** |
| C2 | 称 `FL_SPECTRAL_ENABLE` 是"**纯测量开关，不改变生成/修复行为**"（`config.py:106-112`） | `src/agents/debugger.py:440-441` **拼进补丁生成 prompt**（`query += "\n\n" + fl_spectral_section`）→ 直接改变 LLM 输入 | **P0** |
| C3 | `experiments/run_benchmark.py:3334,3396` 的 `max_pattern_repeat` 入 CLI | **不入 `provenance`**（实测 4 份工件 JSON 无该字符串）→ 违反项目自订"干预必须可从工件证明"最高纪律（项目自述已发生 3 次同类事故） | **P0** |
| C4 | "mypy 硬门禁 / 119 源文件 0 错误" | `pyproject.toml:232-256` **无任何严格开关**；AST 实测 src **1,111** 函数中仅 **842（75.8%）** 完全标注（`api_manager.py` 仅 6/43） | P1 |
| C5 | 覆盖率来自 pytest-cov | 实为 `re` 解析 stdout（`executor_output.py:20` `r"TOTAL\s+.+?(\d+)%"`）；无 TOTAL 行返回 **0.0** → "无数据"与"真 0%"不可区分 | P1 |
| C6 | "沙箱执行" | 默认 `use_docker=False`、`kernel_sandbox=False`；venv 路径为**裸子进程**（`executor_modes.py:113-160` 自述）→ 是依赖隔离+环境脱敏，**不是安全隔离** | P1 |
| C7 | `expert_pool` "**多 Agent 辩论收敛**" | `expert_pool.py:505-513` `debate_round` 只做 **1 次** `DebuggerAgent.debug` 综合调用；`:522-532` 修订候选不参与投票即置首位；`:269-293` "专家"是同构调用的维度后缀变体 | P1 |
| C8 | "变异得分"作为测试强度证据 | 杀死判据 `rc==1`（崩溃亦算杀死，`mutation_testing.py:1246-1249`）；默认 `max_mutants=10`（`:1259`），低于池下限 29 → 饱和 | P1 |
| C9 | "污染检测"可判定训练集污染 | 三通道均为"生成补丁 vs gold patch"相似度（`contamination_check.py:84-102`），**无成员推断/时间切分/无上下文探针** → 会把"独立得出同一最小修复"误判为污染；且对同源编写的合成集无意义 | P1 |
| C10 | `mutation_score` 默认落盘 | 未加 `--enable-mutation` 时该字段**全部缺失**（实测 8 任务批次） | P2 |

---

## 3. 2025–2026 前沿基线（独立重建）与可比性判定

### 3.1 同口径可比性判定（**先于表格，这是本报告的核心方法论结论**）

| 项目指标 | 前沿是否有同口径对手 | 判定依据 | 可否对比 |
|---|---|---|---|
| `detection_rate`（fail-to-pass 检出率） | **无** | 我核实 TestGenEval（line coverage）、ULT（Pass@k 通过率 + mutation）、CANDOR（line/branch/mutation）、TestAgent（line + bug precision）的分子分母后确认：**2025–2026 一手基准无一报告 fail-to-pass 检出率** | ❌ **不可直接对比** |
| target line coverage | 有（ULT 45.10% stmt；TestGenEval 35.2% line） | 口径相近 | ⚠️ 形式可比，但项目侧仅在合成集有数且饱和（88.1% 达 100%）→ **对比无意义** |
| mutation score | 有（ULT 40.21%；TestGenEval 18.8%） | 口径相近 | ⚠️ 项目侧 0.818–0.976 系合成集饱和值 → **对比会误导** |
| repair rate / Pass@1 | 有（FTDI HumanEval Pass@1 63.41%） | 任务与语言不同 | ❌ 不可直接对比；且项目侧无当次运行证据 |
| 成本 | 有（ICST 2026 以 LLM 请求数度量） | 量纲不同 | ⚠️ 方向可比 |

> **因此本报告拒绝给出"项目 X% vs 前沿 Y%，故超越/落后 Zpp"的表格。** 任何这类表述在方法论上无效。

### 3.2 前沿一手基线（我亲自访问载体，A/B 级）

**测试生成**

| 系统 | 论文（venue / ID） | 关键指标 | 等级 |
|---|---|---|---|
| **CoverUp** | FSE 2025, DOI `10.1145/3729398`；arXiv:2403.16218 | **overall line+branch 90%** vs MuTAP 77%；per-module median **80%** vs CodaMosa 47% | **A** |
| **MUTGEN** | **IEEE TSE 52(5):1657–1671, 2026**, DOI `10.1109/tse.2026.3682975` | 核心论断："**部分测试套件达 100% 覆盖率但变异得分仅 4%**" | **A** |
| **CANDOR** | **TOSEM 2026**, DOI `10.1145/3803418`；arXiv:2506.02943 | HumanEvalJava **0.991 / 0.970 / 0.980**（line/branch/mutation）；领先 LLM-Empirical **15.8–25.1pp** | **A** |
| **TestAgent** | **FSE Companion '26** pp.242–246, DOI `10.1145/3803437.3806428` | line **92.34%**；检出 **154 个真实缺陷**，precision **92.22%**；**摘要不含 mutation 值** | **A/B** |
| **ICST 2026 复现**（Konstantinou 等） | **ICST 2026**，arXiv:2601.09695v2 | **Plain-LLM 49.95 / 35.33 / 33.82 全面优于 HITS/SymPrompt/CoverUp/TestSpark**；请求数 **11,815 vs CoverUp 12,741**；~20% 生成测试不编译、~43% 不通过 | **A** |
| **TestGenEval** | **ICLR 2025**, arXiv:2410.00752 | **GPT-4o line coverage 35.2% / mutation 18.8%**（All-Pass@1 7.5%） | **A** |
| **ULT (UnLeakedTestbench)** | **TOSEM 2026**, DOI `10.1145/3805043` | **statement 45.10% / branch 30.22% / mutation 40.21%**；3,909 真实 Python 函数、抗污染筛选 | **A** |
| **SWT-Bench** | **NeurIPS 2024**, DOI `52202/079017-2601` | **Code Agent 在测试生成上超过专用测试系统**；生成测试使 **SWE-Agent precision 翻倍** | **A** |

**多智能体 / 自修复 / 逻辑驱动**

| 系统 | venue / ID | 我核实的内容 | 等级 |
|---|---|---|---|
| **BOAD** | **ICLR 2026**, arXiv:2512.23631（IBM Research 官方页确认） | 多臂老虎机**自动搜索**层级 orchestrator；SWE-bench-Verified 优于单智能体与**手工**多智能体 | **A** |
| **FTDI** | **Expert Systems with Applications**, DOI `10.1016/j.eswa.2026.134164` | 预算感知自修复：HumanEval Pass@1 **63.41%**（Resilience 99.05%） | **A** |
| **VIGIL** | arXiv:2512.07094 | 机制完整（EmoBank→RBT 诊断→guarded prompt 更新）。**摘要中无任何定量延迟/MTTR 数值** | 机制 **A** / 数值 **D** |
| **MTTR-A** | arXiv:2511.20663 | 提出 MTTR-A / MTBF / NRR **指标定义**；**是度量论文，不报 SRE 实测数字** | **A**（定义） |
| **TOGLL** | **ICSE 2025** pp.1475–1487, DOI `10.1109/ICSE55347.2025.00098` | **3.8× 正确断言、4.9× 异常预言；1,023 个 EvoSuite 检测不到的唯一缺陷** | **A** |
| **LM2Alloy** | arXiv:2607.18555 | **直接 LLM 基线拿到 68% 分支覆盖，却三次运行全部漏掉真实缺陷**。⚠️ 9 KB 探索性预印本、无 venue、仅 2 个库 | **A**（弱载体） |
| **KLEE** | USENIX OSDI 2008 | 符号执行测试生成奠基引用 | **A** |

### 3.3 前沿表的三条结论

1. **"覆盖率饱和"是真实趋势，但仅限方法级/小型程序。** CANDOR 0.991 line（HumanEvalJava）、TestAgent 92.34%（Java 仓库）↔ 而**真实世界 Python 函数**上 ULT 仅 45.10% statement、TestGenEval 上 GPT-4o 仅 35.2%。**同一"覆盖率"名词下相差 2.8 倍。**
2. **同一系统在不同评测下可差 3 倍**（CoverUp：自报 90% ↔ 独立复现 38.85% line）。这是项目"不轻信单一来源"纪律的最强外部支持。
3. **"工具特定编排 vs 强 LLM 单提示"的负面结论有两份独立一手来源**（ICST 2026 复现可直接复核；IEEE 11655121 存在但四值本次不可复核，见 §3.4）。

> **对项目"逻辑驱动"定位的结构性发现**：项目实际采用的**属性推断 / Hypothesis 路线在 2025–2026 一手学术文献中无实质载体**（唯一定向命中的 Zenodo 记录全部沉积文件仅 794 字节）；而该方向**最活跃、最可对话的前沿是 Alloy / 形式化规约路线（LM2Alloy、TOGLL）**。项目当前的技术选型与前沿活跃区**不重合**。

### 3.4 项目引用的独立核实（13 条标识符全查）

| 结论 | 数量 | 明细 |
|---|---|---|
| **属实**（标识符+作者+venue+数值均与一手源一致） | **8** | CANDOR（数值精确匹配原文表 1）、ULT（45.10/40.21 映射正确）、MUTGEN（DOI 卷期页码正确）、Zhao/Zhou/Cohen（**ISSTA 2026 Distinguished Paper**）、BOAD（IBM 官方页确认 ICLR 2026）、CoverUp（FSE 2025）、TestGenEval（ICLR 2025）、SWT-Bench（NeurIPS 2024） |
| **数值或出处被误述** | **1（纯数值）+ 4（口径问题）** | 见下 |
| **无法定位一手来源** | **5** | IEEE 11655121 四值、TestAgent 两 mutation 值、Zhao 的 r=0.780、SWE-bench Verified 弃用日期、`agent-sandbox-runtime` |

**唯一硬伤（数值误述）**：`README.md:28` 写"请求数不高于 CoverUp（**11,718 vs 12,264**）"，arXiv:2601.09695v2 原文为 **11,815 vs 12,741**。定性结论成立。疑似引用 v1 稿（我未取得 v1，标注为**推测 E 级**）。

**4 处口径问题**：
1. **IEEE 11655121（项目最重的"不利证据"）四个数值本次无法从任何公开可及一手源确认**（D 级，IEEE HTTP 202 空体 / ACM 403 / S2 429）。建议改以**可复核的 ICST 2026 复现**作主负面证据——论点强度不降反升。
2. **TestAgent 的 mutation 值项目内自相冲突**：`README.md:24` 写 **83.69%**，`BASELINE.yaml:50-51` 写 **55.4%**；**两者我都无法核实**。建议删除 mutation 断言。
3. **CANDOR 的 branch 优势统计不显著**：原文明确"none of the differences between CANDOR and EvoSuite are statistically significant"，且 LeetCode-Medium 上 EvoSuite 反超。项目未披露该限定。
4. **TestAgent 是 5 页 Companion 短文**，与 CANDOR（TOSEM 全文）证据权重不对等。

> **正向结论（必须写明）**：项目所列 **8 个 DOI/arXiv 标识符零伪造、零张冠李戴**。这在高产出科研项目中**显著优于平均水平**。

### 3.5 无法定位一手来源的 D 级清单（27 项，摘要）

| # | 条目 | 拦截/失败原因 |
|---|---|---|
| D1 | IEEE 11655121 的 88.35 / 35.92 / 69.90 / 45.63 | IEEE HTTP 202 空体、ACM 403、S2 连续 429 |
| D2/D3 | TestAgent mutation 83.69%（README）与 55.4%（BASELINE） | ACM PDF 403；摘要无该值 |
| D4 | Zhao et al. 的 r=0.780 @k=10 | Crossref/ISSTA program 摘要无数值；PDF 403 |
| D5 | SWE-bench Verified 2026-02-23 弃用日期 | openai.com 403 |
| D6 | `agent-sandbox-runtime` | 未定位任何一手来源 |
| D7 | VIGIL 的任何定量指标 | 原文摘要即无数值 |
| D8–D11 | LANTERN / TraceCoder / AgentRepair / UTgen | 均未定位 |
| D13/D14/D22 | SpecIR、ESBMC-AI、SMT 驱动测试生成 | 未定位对应论文 |
| D20/D25 | LLM 属性不变量推断、Hypothesis×LLM 实证 | 命中误归属 / 唯一载体为 794 字节空壳 |
| D26 | SWE-bench Verified 榜首 79.2%（396/500）及两个榜单条目 ID | `swebench.com` 30s 超时；`github.com` 被拒；条目 ID 精确检索零命中 |
| D27 | arXiv:2609.24341 的任何具体数值 | 仅取到 abs 摘要，未抓全文 |

**两条与项目最可比锚点的精确口径**：
- **TestGenEval 35.2%** = **被测代码行覆盖率**：分子 = 生成套件执行到的被测文件行数；分母 = 该文件可执行行数；**仅统计通过的测试**；文件级。检出代理是同一行的 **Mutation 18.8%**。
- **ULT 41.32%** = **测试通过率**（Eq.1 `Pass@k = ΣCᵢ/(N×K)`），**不是缺陷检出率**。⚠️ 论文 RQ1.1 表实测 ULT Pass@1 = 9.39–17.83%，**平均不出 41.32%** → **建议在 TOSEM 正式版定位前只引定义、不引此数**。

---

## 4. 量化对比矩阵

| 维度 | 2025–2026 前沿 SOTA（一手） | 等级 | 项目现状（本次实测） | 项目等级 | 差距 | 竞争位置 | 可否对比 |
|---|---|---|---|---|---|---|---|
| 测试生成 · line coverage（真实 Python） | TestGenEval GPT-4o **35.2%**；ULT **45.10%** stmt | A | **无真实代码数据**；合成集 med 98%（88.1% 任务=100%） | A（合成）/ **无**（真实） | **无法计算** | **不可判定** | ❌ |
| 测试生成 · mutation | ULT **40.21%**；TestGenEval **18.8%** | A | 合成集 **0.818–0.976**（项目自认饱和） | A（合成） | 不可比 | **不可判定** | ⚠️ |
| **检出能力 · fail-to-pass** | **前沿无同口径指标** | — | aitester **15.8%**；plain_llm_df **44.8%**；plain_llm 1.5%（存档）/ **19.2%**（当前 API） | A | — | **无对手可比** | ❌ |
| 多智能体协作 · 编排增益 | ICST 2026：Plain-LLM 49.95/35.33/33.82 **全面优于** 4 个 SOTA 工具 | A | **受控配对 δ = −24.6pp，95% CI [−33.7,−15.6]** | A | **项目自身数据同向且更强地否定编排** | **与前沿同向** | ✅ 方向可比 |
| 自修复 · repair success | FTDI HumanEval Pass@1 **63.41%** | A | 主批次三臂 **0.0%**；离线重放 **39.31%**（无当次证据） | A / D | −24pp 或 −63pp | **显著落后** | ⚠️ 仅量级参照 |
| **真实仓库任务（唯一外部有效性）** | SWE-bench 系（BOAD 在 Verified 上优于单智能体） | A | **0/20 通过，补丁在全部 20 个任务上应用失败** | A | **无有效数据** | **尚未进入可比区间** | ❌ 实验未跑通 |
| 逻辑驱动 · 规约可编译率 | TOGLL：1,023 唯一缺陷；LM2Alloy：68% 覆盖仍漏真实缺陷 | A | **全量中位 0.200；47.6% 为零** | A | 项目侧"逻辑"对半数任务空转 | **未形成可对话能力** | ❌ |
| 自修复 · detection latency / MTTR | **一手文献普遍不报数值** | D（数值） | 项目无该指标 | — | — | **该维度前沿尚无基线** | ❌ |
| 工程化 · 可复现性 | — | — | 5390 passed/0 failed；SHA256SUMS 20/20 抽样通过；24 个门禁（1 个红） | A | — | **显著优于同类科研代码** | ✅（质量事实） |
| 引用完整性 | — | — | 8/13 标识符完全属实，0 伪造 | A | — | **优于平均** | ✅ |

---

## 5. 差距诊断（按维度）

| 维度 | 项目现状 | 前沿 | 差距性质 | 优先级 |
|---|---|---|---|---|
| **科学性** | 测量伪影三次事后更正；预注册双语；口径矩阵。**高于平均** | 未检索到"如何发现自己的测量错误"的同类报告 | **反向领先**（方法论） | — |
| **创新性（核心机制）** | 编排受控对照 δ=−24.6pp | ICST 2026 同向 | **项目自证负贡献** | **P0** |
| **创新性（逻辑驱动）** | 中位 0.200、47.6% 为零；CEGIR 未接线 | TOGLL / LM2Alloy | **能力未形成** | **P0** |
| **问题定义** | 自称"逻辑驱动多智能体测试生成与自修复"；实际主体是"检出优先提示协议"（df 44.8% vs aitester 15.8%） | SWT-Bench | **命名与实体错配** | **P0** |
| **数据** | 16 模板 / 87 标签 / **26 唯一程序体**；bug+gold+oracle 同源 | ULT 3,909 真实函数、抗污染 | **外部有效性为零** | **P0** |
| **方法** | LangGraph 图 + 12 开关；SMT 见证（真 z3）；MDO 已实现未接线 | BOAD 自动搜索；FTDI 预算感知 | 手工 vs 自动搜索 | P1 |
| **实验设计** | 三臂同模型/温度/迭代/seed（公平）；但 `git_dirty=true`、token 记账整臂为零、同 seed 重放逐字节相同 | ICST 2026 方法论（完整仓库、seen/unseen 切分、Mann-Whitney U、显式排除网络失败请求） | **取证纪律有缺口** | **P0** |
| **评估指标** | `detection_rate` 与修复策略数学耦合（项目已自识）；coverage/mutation 饱和 | MUTGEN 4% 论断；Zhao ISSTA'26 限定性结论 | 指标设计方向正确 | P1 |
| **可复现性** | 见 F12/F13 | 前沿普遍不提供复现包 | 有缺口 | **P0** |
| **规模与成本** | 1.2 GB；4 个文件 >2,000 行（`run_benchmark.py` 3,401 行）；$0.0259 vs df $0.0045（**5.8×**） | — | 可维护性 + 成本 | P1 |
| **安全与合规** | 无硬编码密钥；`.env` 从未入库；**默认无真隔离** | — | 优于平均但有缺口 | P1 |
| **落地场景** | 无真实仓库成功案例 | SWE-bench 系已有可运行系统 | **尚未进入可比区间** | **P0** |

**差距性质分布**：P0 共 **9** 项，其中 **7 项属于"实验条件未就绪"而非"能力不足"**。**项目的当务之急不是提升性能，而是让实验能产出有效数据。**

---

## 6. 超越前沿方法设计

> **设计前提**：项目的核心问题是**"实验条件未就绪"**而非"性能不够"。因此全部路径的前置条件是**让实验能产出有效数据**；且因项目主指标在前沿**无同口径对手**，唯一可行的"超越"形态是**制造一个新的可比维度**。

### 6.1 路径 A1｜把"政策无关的 oracle 判别力"做成前沿第一个可分维度（**最高优先**）

**技术路径**：把项目已实现的 `src/measurement/mdo.py`（MTR 触发率 / MDR 判别率 / CRASH 崩溃率三分解，含池规模下限 `pool_floor(p,α)` 与 `available=False` 保守语义）从"独立测量层"升级为**在真实世界 Python 基准上的主终点**，并在 ULT（TOSEM 2026，3,909 真实函数，抗污染）上跑出第一批 MTR/MDR 数值。

**差异化点（本路径成立的核心理由）**：

| 前沿现状（一手核实） | 项目可提供的增量 |
|---|---|
| MUTGEN（TSE 2026）证明"100% 覆盖但仅 4% 变异得分"，但**把落差作为一个标量报告** | 把落差**分解为"触发（MTR）"与"判别（MDR）"**，定位落差发生在哪一环 |
| ULT 报告 mutation **40.21%**（单一标量） | 同一批函数上给出 **MTR / MDR / CRASH 三分解** |
| 项目自身 `mutation_score` 用 **`rc==1` 判"杀死"**，把"变异体让程序崩溃"也算作杀死 | MDO **不以退出码为判据**，把"崩溃但无断言失败"单列为 CRASH，**不并入 MDR** |

> **这不是"再做一个变异测试器"，而是把一个已知的度量缺陷（退出码判杀死）修正为行为判据，并在真实基准上给出前沿从未报告过的分解。**

**预期提升**：产出 ULT 标定集（≥200 任务）MTR/MDR/CRASH —— 首次产出（**置信度高**，工程可得，A 级工具链）；池下限 ≥29（`pool_floor(0.10, 0.05)=29`，**A**）；MDR 显著低于 MTR（**方向性预期，置信度中，B/E**）。

**实验验证方案**：
- 基准：ULT 官方 200 任务标定集（先定标，后全量 3,909），**不得使用合成集**；
- 对照组：① ULT 论文 mutation 40.21%（A）；② 项目自身退出码口径 `mutation_score`——同一批任务并列，量化"退出码 vs 行为判据"差值；
- 指标：MTR、MDR、CRASH、`pool_floor_ok` 比例、与官方 Cosmic-Ray mutation 的 Spearman ρ；
- 统计：报告**效应量（Cliff's δ / A12）而非仅 p 值**（CANDOR 的呈现标准）；
- 可复现性：temp=0.0、`git_sha` + **非脏树**、ULT 数据版本 + Cosmic-Ray 版本。

**反事实推演**：该分解逻辑公开（`pool_floor` 是教科书公式），**复制门槛约 2–4 周**；项目护城河**不在方法，而在"已经跑通 + 已在抗污染基准上落数"**——先发优势约 1–2 个季度。**最大失败风险**：MDR 与 mutation_score 高度相关（ρ>0.95）→ 增量仅为"可归因"，不构成新维度。

**判定标准**：
- ✅ **成功**：ULT ≥200 任务上 `pool_floor_ok` ≥80%，MTR/MDR 可计算；发布数据表可被第三方用官方 Cosmic-Ray 复算。
- ❌ **失败**：（a）`pool_floor_ok` <50%；（b）MDR 与官方 mutation 的 ρ>0.95；（c）无法在非脏树上复现。

### 6.2 路径 A2｜修通外部有效性闸门（**P0 阻断项**）

**技术路径**：修复"真实仓库任务上补丁从未成功应用"（§2.3）。三个已知断点：
1. **数据**：`~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl` 为 0 字节、全仓无 enrichment JSONL → `dataset_loader.py:626` 兜底为 issue 文本；
2. **补丁落地**：`llm_patch_apply_failed` 在 20/20 任务上出现；
3. **provenance**：工件 A 的 `provenance=null`、`environment=null`、`repo="unknown"` → 该实验**不满足项目自订的取证纪律**。

**预期**：**不以提升 repair rate 为目标**。唯一目标是 `llm_patch_apply_failed` 不再出现于 100% 的任务，且 F2P baseline 与 after-patch 计数**出现差异**。

**判定标准**：
- ✅ **成功**：≥60% 任务补丁成功应用；**且** 至少一个任务的 `FAIL_TO_PASS after-patch > baseline`；provenance 100% 完整。
- ❌ **失败**：补丁应用成功率 <20%，或 after-patch 与 baseline 计数仍逐任务相同。

### 6.3 路径 B｜把"逻辑驱动"从空转变为约束产出

**技术路径**（针对 §2.4 定位的根因）：
- **在 planner 提示中给出 SpecExpr 的 BNF 与 5 个正/反例**，要求 LLM 输出前自检"该子句是否只含比较/布尔/算术算子"——这是 `spec_compile_rate` 从 0.2 → 0.55 的**最直接杠杆**（成本远低于扩文法）；
- 放开 `src/specs/spec_ir_v2.py:63-69` 白名单：加入集合/序列谓词、有界量化退化形式、关系比较；
- 把 `spec_smt.py` 翻译层从"整体跳过"改为"**部分可译则部分求解**"；
- 与 TOGLL（ICSE 2025）的断言挖掘策略对齐。

**预期提升**：`spec_compile_rate` 中位数 **0.200 → ≥0.55**（项目自订目标，**E 级纯工程推导**）；零可编译子句任务占比 **47.6% → <15%**（E）；MDR 提升（**方向性，置信度低，E**，类比 TOGLL 的 3.8× 断言质量）。

**反事实推演**：TOGLL/LM2Alloy 已在做更强的形式化，**项目没有理论领先**。**唯一可能的技术原创点**：项目的 SMT 通道产出**可执行的见证（witness）输入**而非仅断言——这是"用求解器生成测试输入"而非"用 LLM 猜输入"。**在前沿一手文献中我未找到同构系统**（SpecIR、SMT 驱动测试生成均未定位一手来源）。**若成立，这是项目唯一可能的技术原创点**，但需严格的形式化陈述与对照实验证明它优于"LLM 直接生成边界输入"。

**判定标准**：
- ✅ **成功**：`spec_compile_rate` 中位 ≥0.55 **且** MDR 相对无规约臂提升 ≥5pp（证明规约转化为判别力）。
- ❌ **失败**：编译率提升但 MDR 无变化（说明"逻辑驱动"对检出无因果贡献，应降级为工程选项）。

### 6.4 路径 C｜把编排从手工设计改为自动搜索（对齐 BOAD）

**技术路径**：项目当前是**手工编排**。BOAD（ICLR 2026）用**多臂老虎机自动搜索**层级式 orchestrator，在 SWE-bench-Verified 上优于单智能体与**手工**多智能体。项目应把编排拓扑作为搜索空间。

**差异化点**：项目拥有 BOAD 没有的**12+ 个可独立开关的机制**（`config.py:43-115` 的 `_PROFILE_PRESETS`）与完整消融基础设施，是天然的搜索空间。

**预期提升**：在受控预算下把 δ 从 **−24.6pp** 收窄到 **≥−5pp** —— **置信度低，E 级**（项目自订转正判据 + BOAD 的跨任务类比）。

**反事实推演（本路径最重要的一段）**：BOAD 已在做且更彻底，**项目无先发优势**。若 δ 无法转正，**正确的研究决策是放弃编排作为主张**，把资源集中到 A1 与 A2。**护城河不在编排。**

**判定标准**：
- ✅ **成功**：搜索得到的编排在**预算匹配**（token cap + 迭代数对齐）下 δ ≥ 0。
- ❌ **失败**：δ 仍 < −5pp → **应据预注册停止规则终止编排路线**。

### 6.5 路径 D｜把"测量纪律"本身产品化（**真正的护城河**）

**技术路径**：项目最强的资产不是算法，是**可复现的测量制度**：预注册（双语）、口径矩阵、24 个 CI 门禁、25 份 ADR、SHA256SUMS 工件清单、以及**三次测量伪影的事后更正记录**（ADR-0021/0027/0029）。

**差异化点**：我核实的 8 个前沿一手来源中，**没有一篇报告了"我们如何发现自己此前的测量是错的"**。ULT 的正式文献形态就是把"污染"作为基准设计的一等约束——**项目在"自曝测量缺陷"这件事上有真实案例积累**。

**反事实推演**：这一路径**不可被"同样的算法优化"抹平**——因为它不是算法。**它是唯一在竞争路线采用相同技术后仍然成立的优势。**

**判定标准**：
- ✅ **成功**：以"LLM 测试生成评估中的测量伪影：案例与协议"为题的完整方法论产出，且被第三方复用。
- ❌ **失败**：无法给出可迁移的一般化协议（只讲了自己的故事）。

### 6.6 超越路径汇总

| 编号 | 子方向 | 技术路径 | 前沿参考 | 差异化点 | 目标 | 预期提升 | 置信度 | 等级 | 验证基准 | 成功判定 | 失败判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **A1** | 评估/度量 | MDO 在 ULT 上落数 | MUTGEN TSE'26；ULT TOSEM'26 | 前沿只报单一标量；MDO 分解触发/判别，不用退出码 | MTR/MDR/CRASH | 首次产出 | 高（可得）/中（结论） | A/E | ULT 200→3,909 | 池下限 ≥80% 且可第三方复算 | ρ>0.95 或池下限 <50% |
| **A2** | 外部有效性 | 修通 SWE-bench 管道 | BOAD ICLR'26 | 无技术差异；前提工程 | 补丁应用成功率 | 0% → ≥60% | 中 | A | SWE-bench Lite 300 | ≥60% + ≥1 任务 F2P 变化 | <20% |
| **B** | 逻辑驱动 | 提示-文法契约 + 文法扩展 + 部分可译求解 | TOGLL ICSE'25；LM2Alloy | SMT 产**见证输入**而非仅断言 | spec_compile_rate 中位 | 0.200 → ≥0.55 | 中 | **E** | ULT + QuixBugs | 编译率 ≥0.55 且 MDR +5pp | 编译率升但 MDR 无变化 |
| **C** | 多智能体 | 编排拓扑自动搜索 | BOAD ICLR'26 | 12+ 独立开关作搜索空间 | δ（预算匹配） | −24.6pp → ≥−5pp | 低 | **E** | 合成集→真实基准 | 预算匹配下 δ ≥ 0 | δ 仍 < −5pp → 停止 |
| **D** | 方法论 | 测量伪影协议产品化 | ULT；ICST'26 方法论 | 前沿无人报告"如何发现自己的测量错误" | 可迁移协议 | 非性能 | 中 | **B** | — | 被第三方复用 | 无法一般化 |

---

## 7. 改进建议（按优先级）

### 7.1 P0（15 项：不修则结论不可信）

| # | 位置 | 问题 | 具体做法 | 验证指标 |
|---|---|---|---|---|
| **S1** | `src/datasets/synthetic_dataset.py:36-56`；`run_main_batch.py:60` | 基准自建自评，87 标签仅 **26 唯一程序体** | 停止把合成集作为对外口径；改三层：ULT 标定集 200（主口径）/ QuixBugs / 合成集降级为冒烟 | ULT 上产出首份可复算报告 |
| **S2** | `run_benchmark.py` 全链路；`~/.cache/aitester/swe_bench/`（0 字节） | 真实仓库补丁**从未成功应用** | ① 生成 enrichment JSONL（`scripts/tools/export_swe_bench_source.py` 已存在）；② `instance_code` 必须 `compile()` 通过且 ≠ `problem_statement`（`dataset_loader.py:392-398` 已有校验，改为**拒跑**）；③ 前置断言 `provenance` 完整 | 补丁应用成功率 ≥60%；F2P 计数出现差异 |
| **S3** | `src/graph/nodes.py:2044-2049`；`patch_rollback.py:189` | "P2P 全量回归"实为**重跑自己生成的单个测试**；验证 oracle 与生成 oracle **同源** | ① 回归改用**仓库既有测试套件**；② 测试侧错误（rc≥2/收集错误）改为 **`inconclusive`**，仅断言失败判 `regression_failed`；③ 新增结果行 `validation_oracle_type` | 该字段 100% 非 none；误杀率下降 |
| **S4** | `patch_test_hacking.py:106`；`run_benchmark.py:758-761,1284-1285` | **守卫只审"代码补丁"，完全不审 `generated_test`**；头条批次 `test_hacking_*` 键**一个都不存在**；命中也不阻断 | ① 检测目标**扩展到测试侧**（断言删除/放宽、`assert True`、`pytest.skip`、`xfail`、吞异常、mock 被测函数）；② 升级为**阻断档**；③ 修复字段未落盘 | ≥1 批次 `test_hacking_suspected` 非全 False；新增 6 类构造单测 |
| **S5** | `config.py:106-112` | 称 `FL_SPECTRAL_ENABLE` "纯测量开关"，实际拼进补丁 prompt（`debugger.py:440-441`） | 修正注释；消融归因中视为**行为开关** | 注释与代码一致 |
| **S6** | `README.md:59` vs `README.md:1376` | 同一文档：头条称 CEGIR"闭环"，开关表自述"未接入主链路"；全仓零引用 | 二选一：接线，或把"闭环"改为"可调用能力（未接线）"。**接线前不得用"闭环"表述** | 文档两处一致 |
| **S7** | `BASELINE.yaml:17`；`tests/test_2026_10_10_optimization_batch.py:169-175` | 字段 `5389` / 注释 `5323` / 实测 `5390` 三值互斥；守卫只校验 `declared ≤ collected` 且差 ≤9 | 字段改实测值；守卫改**精确相等**（`declared == collected − skipped − xfailed`）；`suite_seconds: 35` 一并更正 | 精确守卫绿 |
| **S8** | `scripts/gates/check_zero_assert_tests.py` | 实测 **exit 1**，2 个零断言用例；`pytest` 全绿掩盖之 | 修 2 个用例或按 `EXEMPT` 登记理由；把"门禁全绿"与"pytest 全绿"分开报告 | 该门禁 exit 0 |
| **S9** | `run_benchmark.py:3334,3396` | `max_pattern_repeat` 入 CLI **不入 provenance**；违反项目自订最高纪律 | 全部 CLI 干预参数写入 `provenance`；加静态守卫（CLI 参数集合 ⊆ provenance 键集合） | 新守卫 exit 0 |
| **S10** | 主批次 `provenance.git_dirty=true` | 记录的 `git_sha` **不对应实际运行代码** | 跑批**强制干净树**（默认拒跑）；或记录 `git diff` 的 SHA256 作为脏树指纹 | 新批次 `git_dirty=false` 或含指纹 |
| **S11** | `src/budget/token_usage.py:107-135`；`base_agent.py:404-415` | 7 份批次中两臂 token **整臂为零**；2026-10-07 后 aitester 亦大面积零 → 成本对比失效 | ① 断言结果行 `llm_calls>0` 或显式标记 `cache_hit=true`；② 零值行写 `token_accounting_status`；③ 报告工具在零记账时**拒绝输出成本结论** | 字段 100% 覆盖 |
| **S12** | LLM 缓存键 | 同 seed 不同 `git_sha` 产出**逐字节相同** `generated_test`；重复试验退化为单次 | 缓存键加入**代码版本指纹**；重复试验模式默认禁用缓存；provenance 记录 `cache_enabled` + 命中率 | 同 seed 不同 commit 不再产出相同测试 |
| **S13** | `experiments/statistical_analysis.py` | 未做**聚类校正**（87 标签实为 26 程序体）；p 值与 CI 过窄约 3.35 倍 | 所有显著性检验改为**以唯一程序体为聚类单元**；报告效应量（A12/Cliff's δ）；预注册固化该口径 | 报告含聚类 CI 与效应量 |
| **S15** | `src/agents/executor_output.py:20,54-66` | 覆盖率**正则解析 stdout**；无 TOTAL 行返回 **0.0** → "无数据"与"真 0%"不可区分 | 改用 `coverage.json`/API；无法解析返回 `None`；结果行标注 `coverage_source` | `None` 语义正确 |
| **S23** | `CITATION.cff` / `README.md` 标题 / 任务书 | 对外称"逻辑驱动的多智能体测试生成与自修复系统"，与内部证据不同步 | 对外定位改为 detection-first 口径（ADR-0016 已做，需同步到标题/CITATION）；**并显式声明"前沿无同口径 fail-to-pass 指标，故不作跨基准比较"** | 全部对外材料口径一致 |
| **S29** | `run_benchmark.py` 的 `provenance` 块 | **模型版本未锁定**：只记浮动别名 `deepseek-flash`，不记 API 返回的 `model`/`system_fingerprint`/探针哈希。实测同别名下 `plain_llm` 由 1.5% 漂移至 19.2%（F13） | ① `provenance` 增记 API 返回 `model` + 固定探针补全的**贪心输出哈希**；② 缺指纹批次标记 `model_version_unpinned`；③ 预注册增加**"模型快照失效即实验作废"停止规则** | 新批次 100% 带模型指纹 |

### 7.2 P0 补充（本次实测新发现）

| # | 位置 | 问题 | 做法 |
|---|---|---|---|
| **T1** | `src/utils/helpers.py:336` | `extract_json_object` **只解析 JSON 对象、从不解析顶层数组** → `ADVERSARIAL_DEBUGGING_ENABLE` 与 `oracle_enhancer` 的数组格式**永远不可能生效**（F15） | 新增 `extract_json_array`，或让该函数支持顶层数组并在返回类型上显式区分；修正 `oracle_enhancer.py:123` 失实注释 |
| **T2** | `src/agents/generator.py` 提示模板 | 真实调用下 18/18 检出为 0：测试**断言缺陷行为**（buggy 绿 / gold 红） | 生成后**强制自检**"该测试在给定源码上是否失败？"；把"检出优先"从**首轮全绿才触发**改为**默认注入** |
| **T3** | `src/graph/nodes.py:471` `_detection_first_regenerate_entry` | 检出优先仅在 `test_passed is True and iteration==0` 触发；短链路与首轮红场景**不触发** | 检出优先提示改为**无条件注入**（或至少在 `SPEC_IR_DSL_ENABLE` 档位下），并做 A/B |
| **T4** | `result-row builder`（`run_benchmark.py`） | `patch_rollback_verdict` / `patch_rolled_back` 在 `BASELINE.yaml metrics_schema` 中声明，但**75/75 行实测缺失**；回滚协议实测触发 12 次却**不可审计** | 接入 `_build_task_result`；扩展 `check_state_contract.py` 为"state 观测键 ⊆ 结果行键" |
| **T5** | `src/measurement/mdo.py` 输出 | `pool_floor_ok=False`（池仅 2，下限 29）时仍输出 `mtr/mdr`（实测 **1.0/1.0**）→ 下游误读"判别力满分" | `pool_floor_ok=False` 时把 `mtr/mdr` 置 `None` 或加 `provisional=True` |
| **T6** | `src/tools/type_repair.py:643` | 注入回调路径对带 ```python 围栏的代码直接 `ast.parse` 而拒绝（生产路径正常） | 把 `extract_code_block` 从 `_auto_llm_repair` **下沉到 `_repair_with_llm`**，两条路径口径一致 |
| **T7** | `experiments/run_benchmark.py` 结果行 | `mutation_score` 仅开关开启时落盘；实测 `test_passed` **恒为 None** | 增加 `mutation_scoring_enabled` 字段；修复 `test_passed` |

### 7.3 P1 / P2（摘要）

- **P1**：mypy 严格化棘轮（`pyproject.toml:232-256` 无严格开关，实测覆盖面 75.8%）；`run_benchmark.py` 3,401 行继续拆分；`expert_pool` 要么实现真辩论要么删除"辩论/共识"表述；污染检测引入 ULT 式 **PLT 对照**与 seen/unseen 时间切分；变异杀死判据改用行为判据 + 池 ≥29；契约修正 `README.md:28`（11,718/12,264 → 11,815/12,741）、删除 TestAgent mutation 断言（`README.md:24` vs `BASELINE.yaml:50-51` 自相冲突且均不可核实）、IEEE 11655121 降级标注。
- **P2**：`pyproject.toml:116` `extend-exclude` 加入未跟踪审查目录（`ruff check .` 当前 417 errors 全来自 `audit_2026/` 与我新增的目录）；统一 `experiments/mutation_testing.py:1239` 的凭证剔除。

---

## 8. 既有评审结论独立复核

我抽样复核了项目内既有评审的 12 条最具后果的结论。

| # | 原结论 | 我的复核方法 | 判定 |
|---|---|---|---|
| R1 | "多智能体有增益"被自身数据证伪（15.8% vs 44.8%） | 独立重算 + **补做聚类稳健检验**（26 程序体，δ=−24.6pp，CI [−33.7,−15.6]，t=−5.36，符号 p=0.0001） | ✅ **支持（并加强）** |
| R2 | QuixBugs `17/37=45.9%`、`37/40=92.5%`，对照不可比 | 读 `e6_a1_batches/e4_quixbugs_FIXED_harness/`：aitester 45.9%（repair 37/40）；**df 31/37=83.8%**（repair 0/41） | ⚠️ **部分支持 + 摘要层表述问题**（见下） |
| R3 | 合成集 aitester detection **14.0%**、df **48.9%** | 官方三批次重算为 **15.8% / 44.8%**；14.0%/48.9% 的分母 556/571 非 261 整数倍，属跨批次或含 superseded 工件 | ❌ **口径有误** |
| R4 | "逻辑驱动"主口径**零实证**（`oracle_type` 只有 `generated_test`，`spec_oracle_*` 键不存在） | 我统计 **7 份主批次共 1,827 行**：`oracle_type` 全为 `generated_test`（1827/1827）；三个 spec_oracle 键**均 0 行**。且 logic 档 `SPEC_ORACLE_EXEC_ENABLE=true` **显式开启**却从未落盘 | ✅ **支持（并加强）** |
| R5 | "'plain LLM 优于复杂编排'已被**两篇**独立一手研究复现" | ① arXiv:2601.09695 我核实成立，但支撑的是"优于**工具特定流水线**"；② **arXiv:2609.24341 我逐字核实：设计中没有 orchestration 这个自变量**（因子空间仅 prompt × model），核心是方差分解（"Model choice explains more variation than prompt choice"），且**主动放弃排序**（"unequal executable subsets, so their relative mutation scores do not establish superiority"） | ❌ **推翻（命题替换）** |
| R6 | "自修复"在代码层不构成运行时自修复系统 | 读 `main.py`（465 B）、`src/cli/app.py`：确为批量 CLI；无守护/热加载/watchdog | ✅ **支持** |
| R7 | "覆盖率是生成有效性的代理"被证否 | 我实测任务级 coverage med 98–100% 而 plain_llm detection 1.5% → **满覆盖与近零检出共存** | ✅ **支持（并加强）** |
| R10 | 项目自评 repair 39.31%（57/145） | 独立重放（自写 normalizer + 自写 pytest runner，**零复用项目函数**）：**57/145 逐位一致**；行级分布 `{skipped 8, no_patch 395, wrong_patch 151, correct 115}` 亦一致；反事实证实 v1→v2 的 +5 行确由跨文件物化贡献 | ✅ **支持（附两项保留）** |
| R11 | 项目自评 tests `5389` | 我实测 **5390**；同字段注释写 5323 | ❌ **推翻** |
| R12 | "触发率 32–39% 而检出率仅 1–2%"（arXiv:2609.09315） | 未取得一手正文；**但定性结论与项目自身实测高度同向**（98.9% 满覆盖 / 1.5% 检出） | ⚠️ 定性支持 / **数值未核实（D，不得引用）** |

**复核结果分布**：**支持 5**（R1/R4/R6/R7/R10）· **部分支持或附保留 3**（R2/R8/R12）· **推翻 2**（R5、R11）· **口径有误 1**（R3）。

**对既有评审的总体判定**：
1. **核心发现（编排负贡献、逻辑驱动零实证、非运行时自愈）我逐条独立验证支持。** 这批报告在事实层面**整体可靠**，且**主动披露了自身局限**（如 P4 标注"对照不可比"）——诚信加分项。
2. **两处应予更正**：（a）"两篇独立一手研究复现"是**命题替换**（R5）；（b）合成集 detection 的 14.0%/48.9% 与官方 15.8%/44.8% 不一致（R3）。
3. **一处框架性问题**：执行摘要把 QuixBugs 45.9% 称为"最优可验证数字"，**而不在同一句给出 83.8% 的对照臂**（83.8% 在正文有，摘要层缺失）。数值无误、可比性也已标注，但**摘要层的呈现会引导读者高估完整系统的水平**——鉴于本项目的问题恰恰是"完整系统更差"，这与项目自身的诚实口径**张力明显**。**建议摘要层与正文口径统一。**

---

## 9. 风险、伦理与合规

### 9.1 技术风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| **模型漂移**（已实测发生，F13） | **已发生** | 所有历史结论不可复现 | 落实 S29：模型版本指纹 + "快照失效即作废"停止规则 |
| ULT 数据许可不明（上游 The Stack v2 gated + `license: other`） | 高 | 无法打包/发布数据 | 用户本地拉取 + 显式接受条款 + 逐文件许可元数据（项目 `docs/design/ult_bridge_plan.md` §4.1 已设计） |
| MDR 与 mutation_score 高相关（ρ>0.95）→ 无增量 | 中 | 路径 A1 失效 | **先做 200 任务标定验证** |
| 编排搜索后 δ 仍为负 | 中高 | 路径 C 失效 | 预注册停止规则，及时转向 A1/A2 |
| 真实仓库 harness 修复成本超预期 | 中 | M2 延期 | 从 Lite 20 例小步验证，再放量 |
| LLM 缓存导致批次非独立（**已发生**） | 高 | 复现性失效 | 缓存键加代码版本指纹（S12） |
| 合成集结论被误用为对外主张 | 中 | 学术声誉 | 全部材料标注"仅内部" |

### 9.2 数据与伦理

| 项 | 现状 | 判定 |
|---|---|---|
| 人类受试者 | 无 | 不适用 |
| 隐私 / PII | 无个人数据；`rag_data/` 与 `data/` 为公开数据集 | 合规 |
| 数据许可 | QuixBugs MIT（已核实）；TestGenEval **CC BY-NC 4.0**；BugsInPy **无 SPDX**；**ULT 许可未澄清** | ⚠️ 项目已登记为"非清洁许可三选一门槛"（加分）；ULT 待澄清 |
| 代码执行安全 | 默认 `use_docker=False`、`kernel_sandbox=False`、venv 子进程 | ⚠️ **默认非安全隔离**；对外不得表述为"沙箱执行" |
| Secrets | `git log --all -- .env` **为空 = 从未入库**；三层脱敏；第四条链路未脱敏 | 基本合规 |
| 滥用风险 | 系统生成代码补丁并自动应用 | ⚠️ 建议默认开启 `kernel_sandbox` + 补丁白名单，或声明"研究用途" |
| 学术诚信 | 引用 8/13 完全属实、**0 伪造**；负面结果入库；三次测量伪影自曝 | ✅ **显著优于平均** |

### 9.3 Plan B

| 失败情形 | Plan B |
|---|---|
| ULT 无法获取/许可不可接受 | 退到 QuixBugs + BugsInPy，如实声明基准局限；MDO 仍可落数 |
| MDR 无增量（ρ>0.95） | 转向"测量伪影协议"（路径 D）作为主贡献 |
| 真实仓库 harness 修不通 | 彻底放弃"修复"主张，收窄为"测试生成 + 检出测量" |
| 编排搜索无果 | 停止编排投入，把最强臂（plain_llm_df 形态）作为唯一生成通道 |
| 规约通道无因果贡献 | 承认属性测试是工程选择，删除"逻辑驱动"标签 |

---

## 10. 待澄清问题（提交项目方）

| # | 问题 | 为何重要 |
|---|---|---|
| **Q1** | 对外主张的最终版本是什么？（"逻辑驱动多智能体测试生成与自修复" vs `ADR-0016` 的 detection-first 口径） | 决定全部建议的取舍 |
| **Q2** | 是否有**当次运行**（而非离线重放）的 repair 非零证据？近半年是否有新实验批次计划？ | repair 39.31% 虽经独立重放证实，但无当次证据 |
| **Q3** | SWE-bench enrichment 数据是否还能获取？`~/swe_repos` 克隆是否仍在？ | 决定 S2 的成本与可行性 |
| **Q4** | ULT 数据许可如何澄清？是否接受"用户本地拉取"模式？ | 决定路径 A1 是否可行 |
| **Q5** | `spec_oracle_exec` 通道为何在 7 份主批次全部零落盘？（未执行 vs 未记录） | 决定"逻辑驱动"是**能力问题**还是**接线问题**——修复成本差一个数量级 |
| **Q6** | `test_hacking_*` 字段为何在头条批次完全不存在？ | 决定该守卫是"未产数"还是"从未运行" |
| **Q7** | 是否会核实 arXiv:2609.09315（"触发率 32–39% 而检出率仅 1–2%"）的一手结论？ | 影响 R12 的最终判定 |
| **Q8** | 目标产出形态是什么？（论文 / 开源工具 / 内部平台） | 决定路径 D 与路径 A 的优先级 |
| **Q9** | 是否接受"放弃多智能体主张、转向度量贡献"的方案？ | §6 路径选择的前提 |
| **Q10** | 合成数据集是否曾用于论文/对外材料？若已用于某处，需评估更正范围 | 影响学术诚信风险等级 |
| **Q11** | **模型漂移（F13）项目方是否知情？** `provenance` 为何不记录可校验的模型版本指纹？ | 这是本报告最高优先级的可复现性威胁 |

---

## 11. 本次评审的方法与局限

### 11.1 我实际做了什么

| 项目 | 数量 |
|---|---|
| 重算的原始工件 | `main_batch` 7 份（各 261 行）+ `raw/sqlfluff__*` 51 份 + QuixBugs 3 份 + `swe_bench_lite_20` 1 份 |
| 独立核实的文献标识符 | **13 条**（8 属实 / 1 数值误述 / 4 口径问题 / 5 无法定位） |
| 亲自访问的一手载体 | arXiv abs/全文、Crossref REST API、会议官方 program、机构官方页、官方 GitHub |
| 独立核实测试套件 | 实测 `pytest tests/` = **5390 passed / 3 skipped / 1 xfailed / 0 failed，200.6s** |
| 实跑项目门禁 | 9 个（`check_zero_assert_tests` **exit 1** 其余通过） |
| **真实 LLM 调用** | **18 个组件逐一验证 + 5 次 benchmark 跑批（8/25/87/87/87 任务）+ 链路测试**，累计 **798,400 input + 664,086 output tokens ≈ $1.1** |
| 代码证据 | 逐条 `file:line` |

### 11.2 已知局限（请一并评估）

| 局限 | 影响 |
|---|---|
| **联网拦截** | IEEE Xplore（HTTP 202 空体）、ACM DL（403）、OpenAI（403）、Semantic Scholar（429）→ 5 条引用无法独立核实（D 级，**不等于"不成立"**） |
| **模型单一** | 真实调用全程仅 `deepseek-flash`；无法回答"换更强模型是否改善" |
| **样本量** | 真实 LLM 端到端试验 18 次（3 模板 × 6）+ 5 次 benchmark 跑批。**足以证伪"组件不可用"，不足以给出稳定的检出率点估计** |
| **缺陷模板** | 真实端到端测试使用我按项目 `synthetic_dataset` 风格手写的 3 个模板，**非项目模板库的机器生成版本** |
| **真实仓库未测** | 项目 SWE-bench 管道在补丁应用处结构性失败，修通前无法测试 |
| **RAG 路径** | 索引为空，`retrieve` 返回 0 条；**RAG 未获有效测试** |
| **未测付费路径** | 双向诊断（需特定触发）、补丁重采样（需补丁应用失败）、2 个演示脚本。**均不构成独立未覆盖代码路径** |
| **知识时效** | 我的参数化知识对 2025 年中之后不可靠；所有 2025–2026 数值均来自本次联网检索，凡未取得一手载体的标注 D 或不填 |

### 11.3 评审资产清单（随报告提供）

| 资产 | 说明 |
|---|---|
| 本报告 | 自包含外部评审版 |
| `_independent_audit/WS1_frontier_primary_sources.md`（567 行 / 82 KB） | 前沿一手来源重建：13 条引用核实、各子方向 SOTA 表、冲突与交叉验证、D1–D27 清单、全部 URL |
| `_independent_audit/WS2_recompute_results.md`（28 KB）+ `ws2_recompute.py`（895 行） | 头条指标独立重算，脚本一键复现、只读原始工件、脚本内不读任何 `.md` |
| `_independent_audit/WS3_code_domain_audit.md`（185 行） | 代码与领域审计：工程化 24 行 / 领域 21 行 / **声称 vs 实现 20 条**（附 file:line） |
| `_independent_audit/LLM_LIVE_TEST_2026-10-11.md`（396 行） | 真实 LLM 调用测试：组件表、L1–L8、§11 模型漂移证据链 |
| `_independent_audit/PAID_FEATURE_COVERAGE_2026-10-11.md`（14 KB） | 付费功能覆盖审计 |

---

## 12. 结论

**这份项目值得被认真对待，但它当前的对外主张必须撤回或重写。**

**值得肯定的三件事（有 A 级证据）**：
1. **测量纪律**：预注册双语、口径矩阵、25 份 ADR、SHA256SUMS、三次测量伪影的事后自曝与更正。在我核实过的 8 个前沿一手来源中，**没有一篇报告过"我们如何发现自己的测量是错的"**。这是真本事。
2. **引用完整性**：8/13 标识符完全属实、**零伪造、零张冠李戴**——在一个 4.2 MB 文档、130 KB README 的项目里，这个成绩优于平均。
3. **工程化**：5390 个测试全绿、24 个 CI 门禁、`SHA256SUMS` 抽样 20/20 通过、可安装打包链路。这是科研代码里罕见的水平。

**必须撤回或重写的三件事**：
1. **"多智能体"主张**：受控对照下完整系统比单提示协议低 **24.6pp**（CI [−33.7,−15.6]）、贵 **5.5 倍**。且在当前模型上，"系统优于裸 LLM"这一存档结论**已反转**（F13）。
2. **"逻辑驱动"主张**：**47.6% 的任务产不出任何可编译规约**，中位数 0.200；头条所称的"闭环"**未接线**。真实调用下失效根因是**提示-文法契约**（LLM 输出自然语言，编译器只收形式表达式）。
3. **"自修复"主张**：主批次当次 repair **全为 0**；39.31% 来自离线存量重放（虽经独立重放证实）；**真实仓库上补丁从未成功应用过一个**；验证 oracle 与生成 oracle **同源**。

**唯一有前沿对话资格的资产**：`src/measurement/mdo.py` 的**政策无关 oracle 判别力分解**（MTR/MDR/CRASH）——因为前沿只报单一 mutation 标量，而 MUTGEN（TSE 2026）恰好证明了这个标量会掩盖"100% 覆盖 / 4% 变异"的巨大落差。把它搬到 ULT 上落数，是这个项目**最有希望产出真实贡献**的方向（§6.1）。

**最后一点，也是最要紧的一点**：本报告最高优先级的发现不是任何一条性能缺陷，而是 **F13 —— 项目的存档结果在当前 API 上无法复现**（同一 87 任务 × 3 seed，`plain_llm` 检出率 1.5% → 19.2%，12.5 倍）。`provenance` 只记录了浮动模型别名，没有任何可校验的版本指纹。**这意味着项目现有的绝大多数数字，在今天的模型上都失去了可复现性。** 无论项目最终选择哪条路线，**先解决模型版本锁定（S29）**是前提。

---

> **报告结束**。所有结论标注证据等级（A/B/C/D/E）；所有不可验证项已显式列为"无法验证"或"待澄清"。
> 本报告**不提供"超越前沿"的确定性结论**——因为在当前实验条件下，**这样的结论无法被任何证据支撑**。
