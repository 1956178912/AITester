# 超长文件分层摘要策略设计文档（P3 #17）

> 立项日期：2026-09-28
> 状态：**已实现（P1-9 修正：原状态头误标 Design-only——`src/tools/hierarchical_summary.py`
> 已落地 `HIERARCHICAL_SUMMARY_ENABLE` 开关与降级链，配套 29 用例；本状态头
> 2026-10-05 与实现对齐）**
> （默认行为不变；实装时另立批次 + ADR）。与 [ADR-0004 零默认外部依赖](
> ../adr/0004-zero-default-deps.md) 口径一致：摘要层优先纯静态（AST + 滑窗 +
> 重要性打分），LLM 摘要仅作可选增强且默认关。

## 1. 背景与问题

当被测文件 / 注入上下文超过 LLM 单次调用预算（默认
`CODE_MAX_CHARS ≈ 2000`、跨文件 `CROSS_FILE_CONTEXT_MAX_CHARS ≈ 4000`、
Debugger prompt 总长无硬上限但越长越贵）时，现状是**截断**
（`truncate_code` 截尾部 / 跨文件按 2000 字符每模块截断）——尾部逻辑、
被截断模块的关键符号会丢失，导致 LLM 修复"看不到全貌"。
改进项 #17 要求改为**分层摘要（Hierarchical Summarization）**：把超长内容
按"函数 / 模块 / 文件"层级逐步压缩，保留高信息密度部分（异常相关栈帧、
命名契约符号、公共 API、测试关注函数），而非机械截尾。

## 2. 分层边界与策略

```
Level 0  原始文件 / 模块全文（≤ 预算 → 直接用，零摘要开销）
Level 1  函数级摘要：按 AST 抽取目标函数 + 1-2 层调用链 + 命名契约符号
         （复用 3.3 位置感知定位的"包围异常行的最短区间函数"思路，
          src/agents/debugger.py::_locate_repair_focus 已实现静态定位，
          本层把同一 AST 能力推广为"无异常时按 target_function 定位"）
Level 2  模块级摘要：每模块保留"公共 API + 异常相关符号 + 测试关注点"
         的签名级摘要（函数 / 方法签名 + docstring 首行，不保留函数体）
Level 3  文件级摘要：多模块文件仅保留"模块导出 + 顶层常量 + 关键类签名"
（可选）  LLM 摘要层：对 Level 1-3 仍超预算的长上下文，用 LLM 生成
         结构化摘要（默认关，AITESTER_LLM_SUMMARY_ENABLE=true 启用，
         独立开关 + 缓存复用 LLM 文件缓存省 token）
```

降级链（与 1.3 上下文档位降级 `patch_applier._CONTEXT_TIER_TEMPERATURES`
同口径）：Level 0 超限 → Level 1 → Level 2 → Level 3 → （可选）LLM 摘要 →
仍超限才退化为现行截尾（保证最坏情况不劣于现状）。

## 3. 设计要点

1. **纯静态优先**（ADR-0004）：Level 1-3 全部基于 `ast` + 符号表 +
   滑窗打分（异常栈帧权重 > 公共 API > 命名契约符号 > 其余），零 LLM
   成本、确定性可复现（实验口径不变）；
2. **预算参数化**：每层预算走环境变量（`SUMMARY_BUDGET_L1/L2/L3`，
   默认分别 1200 / 800 / 400 字符），`AITESTER_LLM_CACHE` 复用 LLM 摘要
   缓存；
3. **默认关 + 独立开关**（ADR-0003）：`HIERARCHICAL_SUMMARY_ENABLE=true`
   启用分层摘要；缺省 false 时行为与历史截断完全一致（逐字节回归守卫）；
4. **可观测层**：每任务记录 `summary_level`（实际停在哪层）+ 丢弃符号
   列表（`summary_dropped_symbols`），供 `analyze_results.py` 统计
   "摘要层触发率 / 各层丢弃率"；
5. **不改动 17 类分类器**：摘要只喂生成器 / 调试器，不喂
   `error_classifier`（分类器保持纯规则零 LLM，ADR-0002 口径不变）。

## 4. 落地里程碑（后续批次，独立 ADR）

| 里程碑 | 内容 | 前置 |
|--------|------|------|
| M1 | Level 1-3 纯静态分层摘要 + 降级链 + 默认关开关 | 本文档评审通过 |
| M2 | 可观测层（summary_level / 丢弃符号）进 analyze_results | M1 回归全绿 |
| M3 | 可选 LLM 摘要层（默认关，复用 LLM 文件缓存） | M2 + 独立 ADR |

> 任一里程碑实装前：`pytest tests/` 全绿 + 双语文档同步 +
> BASELINE.yaml 刷新；默认行为不变（新开关全默认关）。

## 5. 与现有文档的关联

- [ADR-0002](../adr/0002-error-classifier-rules.md)：摘要不喂分类器
  （分类器保持零 LLM）；
- [../algorithm_design.md](../algorithm_design.md) 附录映射表：M1 落地时
  新增"分层摘要"行 + 相关 ADR 列；
- [3.3 位置感知修复](../algorithm_design.md)：Level 1 复用
  `_locate_repair_focus` 的 AST 定位能力；
- [../adr/README.md](../adr/README.md)：M1 落地时新增 ADR-0007（分层（2026-10-05 勘误：ADR-0007 编号同时被 ADR-0001 中的事件总线引用占用，两者均已实现却均未交付 ADR 文本——编号冲突待下一个 ADR 批次统一裁决后补写）
  摘要策略）并追加到索引表。

---
*最后更新：2026-09-28（P3 #17 改进批次立项，设计文档，未实装代码）。*
