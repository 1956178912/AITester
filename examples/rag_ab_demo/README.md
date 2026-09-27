# 能力演示：RAG A/B 对比实验（ENABLE_RAG）

最小可运行说明脚本，指向 `experiments/rag_ab_experiment.py` 的两个使用路径
（实跑 ON/OFF 两批 + `--analyze-only` 仅分析已有结果），并演示 RAG 检索器
单例的懒加载降级口径。

## 运行

```bash
python examples/rag_ab_demo/run.py        # 离线演示（不消耗 LLM token）
```

实跑 RAG A/B（需真实 LLM key + chromadb，消耗 token）：

```bash
python experiments/rag_ab_experiment.py \
    --dataset synthetic --task-count 20 --seed 42 \
    --output-dir experiments/results/rag_ab_demo
```

## 预期输出

- **离线演示**：打印实跑 / `--analyze-only` 两条命令入口 + 检索器懒加载状态
  （chromadb 未安装时 `get_rag_retriever()` 返回 `None` → 透明降级，
  RAG 检索被跳过；这是保守设计口径，非缺陷）；
- **实跑 A/B**：产出结构化数据——成功率 / 平均 token / 平均迭代 /
  平均耗时（RAG ON vs OFF），按错误类型分组（哪类错误在 RAG ON 下
  显著减少），配对 Welch t-test + Mann-Whitney U + Cohen's d。

## 涉及的环境变量开关

| 开关 | 默认 | 说明 |
|------|------|------|
| `ENABLE_RAG` | false | RAG 检索增强总开关 |
| `RAG_TOP_K` | 5 | 检索返回的相似用例数 |
| `EMBEDDING_BACKEND` | auto | 嵌入后端（auto / chromadb / sentence-transformers / codebert / none，缺依赖时保守降级） |
