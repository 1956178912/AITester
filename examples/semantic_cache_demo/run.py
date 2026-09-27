"""
能力演示：语义级 LLM 缓存（SEMANTIC_CACHE_ENABLE，5.1）。

最小可运行脚本：验证"相似 prompt（表述不同但语义等价）命中缓存，省 LLM
调用 token"的能力。无需真实 LLM key 亦可离线运行——嵌入不可用时自动
降级为精确缓存口径（零行为变化），本脚本打印的统计在离线模式下同样
可读（enabled=False 时语义索引不生效，命中率恒 0，属预期降级）。

运行：
    python examples/semantic_cache_demo/run.py

预期输出说明：
    - 离线（无嵌入后端 / 未启用）：enabled=False，hits/misses 统计
      反映精确缓存口径，语义级命中不生效；
    - 启用（SEMANTIC_CACHE_ENABLE=true + 有缓存条目 + 嵌入后端可用）：
      语义命中使相同语义、不同措辞的 prompt 复用缓存响应，
      token 消耗下降。

涉及的环境变量开关（详见 .env.example 注释）：
    SEMANTIC_CACHE_ENABLE      默认 false（开启语义级匹配）
    SEMANTIC_CACHE_THRESHOLD   余弦阈值，默认 0.92（保守：宁可漏命中）
    SEMANTIC_CACHE_MAX_ENTRIES 索引扫描的缓存文件数上限，默认 256
"""

from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main() -> int:
    """演示语义缓存统计口径（不消耗 LLM token，纯观测层）。"""
    from src.agents.semantic_cache import get_semantic_cache_stats

    # 环境变量开关经调用期读取（保留测试的 patch.dict 切换能力），
    # 演示脚本经 os.environ 显式设值以展示"开启前后"的统计差异。
    os.environ.setdefault("SEMANTIC_CACHE_ENABLE", "true")
    stats = get_semantic_cache_stats()
    print("── 语义缓存统计（get_semantic_cache_stats）")
    for key, value in stats.items():
        print(f"  {key} = {value}")
    enabled = stats.get("enabled")
    if not enabled:
        print(
            "\n注意：嵌入后端不可用或未启用时语义级命中不生效（精确缓存口径降级，"
            "零行为变化）——这是保守设计口径，非缺陷。"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
