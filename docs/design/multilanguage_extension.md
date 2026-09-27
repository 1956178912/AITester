# 多语言扩展架构预留设计文档（P3 #24）

> 立项日期：2026-09-28
> 状态：**设计文档（Design-only，未落地代码）**——本文档定义"非 Python 被测语言"
> 的扩展点与分层边界，尚未改动任何运行时代码（默认行为不变；实装时另立
> 批次 + ADR）。与 [ADR-0004 零默认外部依赖](../adr/0004-zero-default-deps.md)
> 口径一致：多语言支持走"可选扩展后端 + 透明降级"，不引入新的默认依赖。

## 1. 背景与目标

AITester 当前的生成器 / 执行器 / 分类器面向 **Python**（pytest 用例、
Python 源码补丁、`ast` 静态解析、Python traceback 正则）。当被测代码是
其他语言（TypeScript / Go / Java / Rust 等）时，现有链路在以下环节失效：

| 环节 | 现状（Python 耦合点） | 多语言需要 |
|------|----------------------|-----------|
| 生成器 prompt | 固定 Python / pytest 语料 | 语言感知的测试框架语料（vitest / go test / junit / cargo test） |
| 执行器 | `subprocess` 跑 `pytest` | 语言对应的测试运行器 + 结果解析 |
| 错误分类 | Python traceback 正则（`IndexError` / `SyntaxError` 等） | 各语言异常文本 / 编译器错误的特征映射 |
| 补丁应用 | unified diff + Python 字符串替换 | 语言无关的 diff（可保留），但**符号守卫 / 契约检查**依赖 `ast`，需语言对应 AST |
| 类型修复层 | mypy / pyright / `ast` 静态 | 语言对应静态检查器（tsc / gopls / javac / clippy） |
| RAG / 嵌入 | 词袋 / 句向量对 Python 标识符调优 | 跨语言嵌入（多语言 CodeBERT / 通用句向量） |

**目标**：在不破坏 Python 默认路径（历史实验口径不变）的前提下，预留
"语言后端（Language Backend）"抽象层，使新增一种被测语言 = 实现一个
后端注册 + 数据（不改动核心图编排）。

## 2. 分层边界

```
            ┌─────────────────────────────────────────────┐
  编排层    │ LangGraph StateGraph（语言无关，纯控制流）    │  不变
            ├─────────────────────────────────────────────┤
  后端层    │ LanguageBackend 抽象（按语言注册，可插拔）     │  新增扩展点
            │  - Planner 语料（测试框架 prompt 模板）        │
            │  - Executor 运行器（命令 + 结果解析）          │
            │  - Classifier 特征映射（异常文本 → 17 类）     │
            │  - Patch 守卫（语言 AST 符号契约）            │
            │  - TypeChecker 静态层（语言静态分析器）        │
            ├─────────────────────────────────────────────┤
  数据层    │ 语言后端注册表 + 测试语料 + 数据集（per-language）│  可配置
            └─────────────────────────────────────────────┘
```

核心原则（对齐 [ADR-0001](../adr/0001-langgraph-state-graph.md) 与
[ADR-0003](../adr/0003-default-off-experiment-hygiene.md)）：

1. **编排层语言无关**：LangGraph 节点图不感知语言——语言差异全部收敛到
   后端层，避免在 `workflow.py` / `nodes.py` 里散落 if-else；
2. **默认 Python 后端零变化**：`AITESTER_LANGUAGE`（或数据集元数据
   `language` 字段）缺省 `"python"`，行为与历史逐字节一致；
3. **可选后端透明降级**（对齐 ADR-0004）：非 Python 后端依赖（tsc /
   gopls / javac / clippy）缺失或工具链未装时，该语言后端的"类型修复层"
   降级为"仅静态识别不修订"，不阻断生成 → 执行 → 修复主循环；
4. **默认关 + 独立开关**：每种语言后端以 `AITESTER_ENABLE_<LANG>_BACKEND`
   形式落地（默认 false），保证 A/B 对比口径不变。

## 3. 扩展点接口（设计，未实装）

```python
# src/backends/base.py（示意，未落地）
class LanguageBackend(Protocol):
    language: str
    def planner_corpus(self) -> str: ...            # 测试框架语料 prompt
    def executor_command(self, test_path: str) -> list[str]: ...
    def parse_result(self, raw: str) -> ExecResult: ...
    def classify_error(self, text: str) -> str: ... # → 17 类口径
    def patch_guard(self, code: str, patch: str) -> tuple[bool, list[str]]: ...
    def type_checker(self, code: str) -> list[Finding]: ...
```

注册机制（数据驱动，无代码改动）：`src/backends/registry.py` 按
`AITESTER_LANGUAGE` 查表返回后端实例；未知语言 / 未启用 → 回退 Python
后端（保守降级，不抛异常）。

## 4. 落地里程碑（后续批次，独立 ADR）

| 里程碑 | 内容 | 前置 |
|--------|------|------|
| M1 | 后端抽象 + Python 默认后端（重封装现有逻辑，行为零变化回归） | 本文档评审通过 |
| M2 | 首个非 Python 后端（建议 TypeScript / vitest 或 Go / go test，按团队需求） | M1 回归全绿 |
| M3 | 跨语言嵌入（RAG 后端）+ 数据集 per-language 分片 | M2 至少一个后端转正 |

> 任一里程碑实装前：`pytest tests/` 全绿 + 双语文档同步 +
> BASELINE.yaml 刷新；默认行为不变（新开关全默认关）。

## 5. 与现有文档的关联

- [ADR-0004](../adr/0004-zero-default-deps.md)：可选后端工具链缺失时降级口径；
- [../algorithm_design.md](../algorithm_design.md) 附录映射表：新增"语言后端"
  行时须同步"相关 ADR"列；
- [../adr/README.md](../adr/README.md)：M1 落地时新增 ADR-0006（语言后端
  抽象）并追加到索引表。

---
*最后更新：2026-09-28（P3 #24 改进批次立项，设计文档，未实装代码）。*
