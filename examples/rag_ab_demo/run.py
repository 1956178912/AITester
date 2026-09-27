"""
能力演示：RAG A/B 对比实验（ENABLE_RAG，3.1 RAG 检索增强）。

最小可运行说明脚本：指向 `experiments/rag_ab_experiment.py` 的两个使用
路径（实跑 ON/OFF 两批 + `--analyze-only` 仅分析已有结果），并演示
RAG 检索器单例的懒加载口径。无需真实 LLM key 即可离线演示检索器
降级口径（chromadb 不可用时 RAG 透明关闭，零行为变化）。

运行（离线演示，不消耗 LLM token）：
    python examples/rag_ab_demo/run.py

实跑 RAG A/B（需真实 LLM key + chromadb，消耗 token）：
    python experiments/rag_ab_experiment.py \
        --dataset synthetic --task-count 20 --seed 42 \
        --output-dir experiments/results/rag_ab_demo

涉及的环境变量开关（详见 .env.example 注释）：
    ENABLE_RAG       默认 false（开启 RAG 检索增强）
    RAG_TOP_K        检索返回的相似用例数（默认 5）
    EMBEDDING_BACKEND 嵌入后端（auto / chromadb / sentence-transformers /
                      codebert / none，缺依赖时保守降级）
"""

from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main() -> int:
    """演示 RAG A/B 实验入口与检索器懒加载降级口径（不发起 LLM 调用）。"""
    print("── RAG A/B 对比实验入口（experiments/rag_ab_experiment.py）")
    print("  实跑 ON/OFF 两批 + 统计检验（Welch t-test / Mann-Whitney U / Cohen's d）：")
    print("    python experiments/rag_ab_experiment.py \\")
    print("        --dataset synthetic --task-count 20 --seed 42 \\")
    print("        --output-dir experiments/results/rag_ab_demo")
    print("  仅分析已有结果（--analyze-only，离线）：")
    print("    python experiments/rag_ab_experiment.py \\")
    print("        --analyze-only \\")
    print("        --results-rag-on <rag_on.json> --results-rag-off <rag_off.json>")

    print("\n── RAG 检索器单例懒加载口径（chromadb 不可用时透明降级）")
    # 经 graph.rag 的受控守卫演示降级口径：chromadb 缺失时返回 None，
    # 工作流节点自动跳过 RAG 检索（零行为变化，不阻断主流程）。
    from src.graph.rag import get_rag_retriever

    retriever = get_rag_retriever()
    if retriever is None:
        print("  get_rag_retriever() = None（chromadb 未安装或初始化失败 → 透明降级，")
        print("  RAG 检索被跳过；这是保守设计口径，非缺陷）")
    else:
        print(f"  get_rag_retriever() = {type(retriever).__name__}（检索器已就绪）")
    print("  开关：ENABLE_RAG=true 时工作流节点调用上述检索器；默认 false 不启用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
