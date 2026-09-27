# 能力演示：语义级 LLM 缓存（SEMANTIC_CACHE_ENABLE）

最小可运行脚本，验证"相似 prompt（表述不同但语义等价）命中缓存"的观测口径。

## 运行

```bash
python examples/semantic_cache_demo/run.py
```

无需真实 LLM key 即可离线运行：嵌入不可用时自动降级为精确缓存口径
（零行为变化），统计输出在离线模式下同样可读。

## 预期输出

- 离线（无嵌入后端 / 未启用）：`enabled=False`，语义级命中不生效（保守降级口径）；
- 启用（`SEMANTIC_CACHE_ENABLE=true` + 有缓存条目 + 嵌入后端可用）：
  语义命中使相同语义、不同措辞的 prompt 复用缓存响应，`hits` 计数上升，
  省 LLM 调用 token。

## 涉及的环境变量开关

| 开关 | 默认 | 说明 |
|------|------|------|
| `SEMANTIC_CACHE_ENABLE` | false | 语义级匹配总开关 |
| `SEMANTIC_CACHE_THRESHOLD` | 0.92 | 余弦相似度阈值（保守：宁可漏命中） |
| `SEMANTIC_CACHE_MAX_ENTRIES` | 256 | 索引扫描的缓存文件数上限 |

## 真实工作流中的效果验证

启用后跑一次带修复循环的任务（多轮迭代间 prompt 模板小改、温度微调），
相同语义的 LLM 调用将命中语义缓存，`get_semantic_cache_stats()` 的
`hits` 上升、总 token 下降：

```bash
SEMANTIC_CACHE_ENABLE=true python main.py run examples/calculator.py --func divide
```
