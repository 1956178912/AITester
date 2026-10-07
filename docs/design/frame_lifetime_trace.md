# Frame Lifetime Trace 设计草案（Debugger 拆分批设计输入）

> **状态**：设计草案——**未实现、未排期**。激活门槛与验收标准见 §7。
> **来源**：外部"前沿对齐审查报告"P1-2（2026-10-07 对照评估净新增④，
> ADR-0028 登记）；对标 ADI（Agent-centric Debugging Interface，FSE 2026）。
> **关联**：Debugger 拆分批（TDFlow 四组件锚点，待立项）、ADR-0017/0018、
> `experiments/cf_upper_bound.py`（ADR-0024）。

## 1. 引用纪律（先于一切设计细节）

- ADI 在 SWE-bench Verified 上基础 agent 解决 **63.8%**——该锚点经
  2026-10-06 第十一轮联网核验（"SoRFT/ADI 2026，开源 SOTA Verified
  ~63.8%+"）；
- 外部报告给出的 **$1.28/task** 与 **"即插即用增益 6.2%–18.5%"** 系二手
  数字 **[未核验]**——按 AX 批次纪律（二手数字进稿前必须一手定位或显式
  红线），引用前须定位 arXiv/ACM DL 原文核对；本文其余表述不依赖该
  两个数字。

## 2. 动机

当前 Debugger 的输入是**事后粗粒度执行反馈**：failed_cases（测试名 +
错误输出尾段）+ 谱系/LLM 定位段落。缺口在两点：

1. 错误输出只覆盖"测试失败那一刻"，不覆盖**函数执行轨迹**——同一条
   failed case 可以由不同深度的状态错误导致，现有反馈无法区分；
2. 修复循环（debug → patch → re-execute）每轮重新失败时，Debugger 无法
   对比"上一轮与这一轮的执行差异"，只能靠 diff 补丁文本间接推断。

ADI 的主张（function-level 交互范式）与本项目两个已实证结论直接咬合：

- ADR-0024："生成侧主导"——补丁合成不消费定位信号；帧证据是
  "为什么改这里"的运行时凭据；
- E2 定性："82% 生成测试在 gold fixed 上不全绿"——oracle 质量弱，
  帧级状态有助于区分"断言写错"与"代码真的错了"。

## 3. Frame Lifetime Trace 数据结构草案（Python）

以**函数**为封装单元的有状态执行轨迹（ADI 核心数据结构的本仓映射）：

```text
FrameRecord:
    frame_id: int                      # 全局递增
    function: str                      # 限定名（module.qualname）
    caller: str | None                 # 调用方限定名
    depth: int                         # 调用深度
    entry: {args: {name: summary}}     # 实参摘要（截断序列化）
    exit: {kind: "return"|"exception"|"unwind",
           value: summary | None,      # 返回值 / 异常 repr
           exception_chain: [str]}     # 异常类型限定名链
    locals_snapshot: {name: summary}   # 仅 exit 时（预算内），非逐步采样
    timestamp_us: int
```

要点：

- **函数生命周期四事件**：call / return / raise / unwind（异常穿越帧）；
  unwind 链是"失败测试 → 真实出错帧"的最短路径，现有 error_category
  （17 类分类器）只给类型不给路径；
- **摘要序列化**：repr 截断（默认 120 字符）+ 容器长度上限（默认 8 项）
  + 总帧数预算（默认 2,000 帧）——防 SWE-Effi 式 token 雪球
  （2509.09853，已核验锚点）；
- **不采逐步行级状态**：ADI 与本项目一致地放弃 line-by-line 交互
  （每步一次 LLM 往返的成本结构在本仓预算模型下不可行）。

## 4. 采集策略（Python 3.12+ / 3.13 / 3.14 三档）

| 策略 | 机制 | 取舍 |
|---|---|---|
| 默认 | `sys.setprofile`（C 级 call/return/unwind 事件） | 零 AST 侵入；无行内事件——本设计不需要 |
| 3.12+ | `sys.monitoring`（TOOL_ID 预留注册） | 开销更低；事件集覆盖同需求 |
| 排除 | AST 插桩重写被测代码 | 污染补丁 diff 与 AST 守卫口径，明确排除 |

执行边界：被测代码在 venv / KERNEL_SANDBOX 隔离下运行，profile 钩子
随执行进程同生命周期（子进程口径与 `_run_pytest_in_tmp` 一致）；追踪
产物落 tmp 目录、按轮次滚动覆盖（只保留最近 N 轮），不进 result JSON
正文（摘要经导航命令渲染后进 prompt / trace）。

## 5. 高层导航命令（function-level 范式）

Debugger 不读原始 trace，经四个导航命令取**摘要**（渲染为 debug()
prompt 段落，与定位段落 / 谱系段落并列）：

- `summarize_frame(function)`：该函数本轮的 entry/exit/异常摘要；
- `diff_frames(function, prev_round, this_round)`：两轮执行差异（同一
  输入不同行为的最短解释）；
- `trace_exceptions()`：本轮异常 unwind 链去重列表（top 按频次）；
- `budget_report()`：剩余帧预算（供 Debugger 自行节制取用）。

段落注入遵守 ORACLE_CONTEXT_TIER：minimal 档只注入 `trace_exceptions()`，
full 档全量——与 ADR-0025 的上下文消融档正交复用。

## 6. 与既有资产的整合点

- **17 类错误分类器**（`src/observability/failure_taxonomy.py`）：失败
  分类 → 定向取帧（runtime 类才取深帧，assertion 类只取断言帧）；
- **execution_trace**（3.2 执行反馈轨迹）：Frame Lifetime Trace 是其
  函数级下钻层，不替代；
- **FL Top-k 约束门**（ADR-0028 观测层）：帧证据为"补丁为何改这里"
  提供运行时凭据，与 hit/miss 观测互补；
- **FL_GOLD_INJECTION 反事实臂**（ADR-0024）：完美定位 + 帧证据 =
  "生成侧上限"反事实的完整形态。

## 7. 激活门槛与验收标准（未实现声明）

- **触发条件**：Debugger 拆分批（TDFlow 四组件锚点）立项时，作为
  debug 组件的设计输入评审本文；在此之前不实现、不预埋开关
  （ADR-0003 纪律：无实验设计不开关位）；
- **验收标准（草案，届时随批预注册）**：
  1. 合成集上 debug 轮均 token 增幅 ≤10%（帧预算约束生效证据）；
  2. detection / repair 修正口径不降（门禁双指标）；
  3. 帧证据段落消融 A/B：有/无帧证据段的 debug 成功率差 ≥5pp 才转正；
- **风险登记**：`sys.setprofile` / `sys.monitoring` 可能触发 Mimosa
  污点扫描误报（AF 批 N12 先例：结构性阻塞时按"不绕过安全工具"原则
  登记阻塞与解除路径，不混淆绕行）。
