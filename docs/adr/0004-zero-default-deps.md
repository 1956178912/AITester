# ADR-0004: 零默认外部依赖（可选依赖透明降级）

- 日期：2026-09（贯穿所有改进批次）
- 状态：已采纳（Accepted）
- 关联：`requirements.txt`、`src/utils/embedding_utils.py`、
  `src/tools/type_repair.py`、`src/tools/patch_applier.py`

## 背景（Context）

AITester 核心能力（生成 → 执行 → 修复循环）只依赖
`langgraph` + `openai` + `pytest` 三个基础库。但改进批次陆续引入
了大量**可选增强能力**：

- 嵌入向量（CodeBERT / sentence-transformers / chromadb）——语义缓存、
  污染检测、RAG 混合检索；
- mypy / pyright / ruff——静态类型检查层（2.1）；
- CodeBERT（transformers + torch）——嵌入后端首选；
- rich——CLI 输出增强（6.1）。

## 决策（Decision）

**零默认外部依赖原则**：

- `requirements.txt` 只列核心三个库（langgraph / openai / pytest）；
- 所有可选增强能力**按需 import + try/except 降级**：
  - `embedding_utils.embed_text()` 级联：CodeBERT → sentence-transformers
    → chromadb → None（全部缺失时返回 None，调用方按"嵌入不可用"
    保守降级，不阻断主流程）；
  - `type_repair` 的 mypy/pyright 后端：`TYPE_CHECK_BACKEND` 选择，
    CLI 不可用时降级 ast 静态层；
  - `semantic_cache` 嵌入缺失时自动降级精确缓存口径（零行为变化）；
- 降级路径均有**单元测试守卫**（`tests/test_embedding_utils.py`、
  `tests/test_roadmap_gaps_g1_g2_g3.py` 等）确保"缺依赖时不崩"。

## 后果（Consequences）

**正面**：

- 新用户 `pip install -r requirements.txt` 即可跑通全流程
  （无需装 torch 2GB+ / chromadb 100MB+）；
- 可选能力"装了才生效，不装零影响"——与 ADR-0003 的
  "默认行为不变"原则协同。

**负面 / 已知代价**：

- 用户想启用语义缓存/嵌入必须手动装对应库（`pip install
  sentence-transformers` 等）——`.env.example` 注释 + QUICKSTART
  第 6 节已标注；
- 降级路径多 = 测试矩阵大（每个可选库 × 每个消费方），
  维护成本高——通过"级联函数集中一处
  （`embedding_utils.embed_text`）"降低测试面。
