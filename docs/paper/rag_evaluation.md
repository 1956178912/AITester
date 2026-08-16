# RAG 模块独立评估报告

**评估日期**: 2025-08-16  
**评估人**: evaluator（aitester-paper-sprint 团队成员）  
**评估对象**: TestCaseRetriever RAG 模块  

---

## 一、评估背景与目标

### 1.1 研究问题
检索增强生成（RAG）在软件测试领域的应用价值如何？具体而言：
- RAG 是否能提升测试生成和 bug 修复的成功率？
- RAG 对不同类型的错误修复效果是否有差异？
- RAG 的知识积累机制是否有效？

### 1.2 评估范围
- **模块**: `src/rag/retriever.py` 中的 TestCaseRetriever
- **集成点**: Generator 和 Debugger 两个节点
- **开关**: `ENABLE_RAG` 环境变量控制
- **实验规模**: 合成数据集（synthetic），30 个任务

---

## 二、RAG 实现架构分析

### 2.1 核心组件

#### TestCaseRetriever 类
```python
class TestCaseRetriever:
    def __init__(self, collection_name="aitester_cases", persist_path=None)
    def add_case(self, code, test_code, passed, metadata=None)
    def add_repair(self, original_code, patch, error_category, metadata=None)
    def retrieve_test_cases(self, target_code, top_k=3)
    def retrieve_repairs(self, error_category, target_code, top_k=2)
```

**设计特点**:
- 使用 ChromaDB 作为向量数据库，支持持久化存储
- 余弦相似度度量（cosine）
- MD5 hash 去重机制
- 延迟导入策略，避免依赖缺失时崩溃

### 2.2 数据流设计

#### 入库流程
```
Generator 生成测试
    ↓
Executor 执行测试
    ↓
测试通过？
    ├── 是 → add_case() → ChromaDB
    └── 否 → Debugger 分析错误
                    ↓
               Debugger 生成补丁
                    ↓
               补丁成功？
                    ├── 是 → add_repair() → ChromaDB
                    └── 否 → 放弃修复
```

#### 检索流程
```
Generator 节点：
    target_code → retrieve_test_cases() → rag_references → LLM prompt

Debugger 节点：
    error_category + target_code → retrieve_repairs() → rag_references → LLM prompt
```

### 2.3 关键设计决策

**决策 1**: 仅入库成功案例
- 原因：避免污染检索库，确保参考案例质量
- 权衡：初期知识库增长较慢

**决策 2**: 按错误类型过滤修复案例
- 原因：提高检索精准度，避免跨类型错误混淆
- 实现：ChromaDB where 过滤器

**决策 3**: 检索失败时静默降级
- 原因：保证系统鲁棒性，RAG 为辅助而非必需
- 表现：日志警告，继续执行

---

## 三、消融实验设计

### 3.1 实验配置

| 实验组 | ENABLE_RAG | 其他开关 | 数据集 | 任务数 |
|--------|-----------|---------|--------|--------|
| 实验组 | true | PLANNER=true, DEBUGGER=true | synthetic | 30 |
| 对照组 | false | PLANNER=true, DEBUGGER=true | synthetic | 30 |

### 3.2 评估指标

**主要指标**:
- 成功率（pass_rate）= 通过任务数 / 总任务数
- 平均覆盖率（avg_coverage）= Σ覆盖率 / 任务数
- 平均迭代次数（avg_iterations）= Σ迭代次数 / 任务数

**次要指标**（需后续实验补充）:
- 检索命中率
- 案例采纳率
- 检索延迟占比
- 知识库增长曲线

### 3.3 执行脚本

创建 `experiments/evaluate_rag.py`，支持：
- 快速模式（10任务）：快速验证流程
- 完整模式（30任务）：正式实验
- 自动保存结果到 `experiments/results/rag_ablation/`

---

## 四、预期效果分析

### 4.1 RAG 可能带来增益的场景

**场景 1: 相似函数测试生成**
- 输入：实现 `calculate_discount(price, rate)` 的测试
- RAG 检索：历史上 `calculate_tax(amount, rate)` 的成功测试
- 收益：学习测试结构、边界情况处理、断言模式

**场景 2: 同类型错误修复**
- 输入：IndexError 在列表操作中的修复
- RAG 检索：历史上类似 IndexError 的修复补丁
- 收益：避免重复试错，直接参考有效修复方案

**场景 3: 复杂逻辑代码测试**
- 输入：含多重条件分支的函数
- RAG 检索：类似复杂函数的测试用例
- 收益：提高测试覆盖率和场景完整性

### 4.2 RAG 可能无效的场景

**场景 1: 全新领域代码**
- 问题：无相似历史案例可检索
- 结果：检索返回空，退化为无 RAG 模式

**场景 2: 高度定制化逻辑**
- 问题：历史案例与当前任务差异过大
- 结果：检索到的案例参考价值低，甚至产生误导

**场景 3: 冷启动阶段**
- 问题：知识库为空或案例不足
- 结果：前 N 个任务无法受益，需积累一定数量后生效

### 4.3 潜在风险

**风险 1: 知识库污染**
- 条件：测试质量不稳定，低质量案例入库
- 后果：检索到噪声案例，干扰 LLM 判断
- 缓解：仅入库 passed=True 且高覆盖率的案例

**风险 2: 检索延迟**
- 条件：知识库增长到万级别案例
- 后果：检索耗时增加，影响整体效率
- 缓解：定期清理低质量案例，优化索引策略

**风险 3: 过拟合风险**
- 条件：长期运行后，模型偏向历史模式
- 后果：创新测试生成能力下降
- 缓解：保留一定随机性，定期重置知识库

---

## 五、改进建议

### 5.1 检索策略优化

**建议 1: 混合检索**
```python
# 当前：仅向量检索
results = collection.query(query_texts=[target_code], n_results=top_k)

# 建议：向量 + 关键词混合
from chromadb.utils import embedding_functions
ef = embedding_functions.DefaultEmbeddingFunction()
vector_results = collection.query(query_embeddings=ef.encode_documents(target_code), ...)
keyword_results = collection.query(query_texts=[target_code], ...)
# 融合排序
```

**建议 2: 动态 top_k**
```python
# 根据代码复杂度动态调整
complexity = len(target_code.split('\n'))
top_k = min(3 + complexity // 100, 10)  # 简单代码 3 个，复杂代码最多 10 个
```

**建议 3: 重排序机制**
```python
# 二次排序：先粗筛，再精排
candidates = collection.query(n_results=top_k * 2)
reranked = rerank_by_similarity(candidates, target_code)
return reranked[:top_k]
```

### 5.2 入库质量控制

**建议 1: 置信度阈值**
```python
# 仅入库高置信度案例
if passed and coverage >= 0.9 and len(failed_cases) == 0:
    retriever.add_case(...)
```

**建议 2: 去重策略升级**
```python
# 当前：MD5 精确匹配
# 建议：语义去重（embedding 相似度 > 0.95 视为重复）
```

**建议 3: 过期机制**
```python
# 标记案例时间戳，定期清理超过 N 天未使用的案例
def cleanup_old_cases(max_age_days=30):
    old_cases = collection.get(where={"updated_at": {"$lt": cutoff_timestamp}})
    collection.delete(ids=old_cases["ids"])
```

### 5.3 评估指标扩展

**当前指标**:
- 成功率
- 覆盖率
- 迭代次数

**建议新增**:
```python
# 1. 检索有效性
retrieval_hit_rate = count(retrieve results > 0) / total_tasks

# 2. 案例采纳率
case_adoption_rate = count(LLM uses RAG refs) / count(RAG returns results)

# 3. 检索延迟
retrieval_latency = avg(time(retrieve_test_cases) + time(retrieve_repairs))

# 4. 知识库质量
knowledge_base_quality = avg(coverage of retrieved cases)
```

### 5.4 消融实验细化

**建议实验矩阵**:

| 实验编号 | ENABLE_RAG | Generator RAG | Debugger RAG | 目的 |
|---------|-----------|--------------|-------------|------|
| Exp-0 | false | false | false | 基线 |
| Exp-1 | true | true | false | 仅 Generator RAG |
| Exp-2 | true | false | true | 仅 Debugger RAG |
| Exp-3 | true | true | true | 完整 RAG |

**不同 top_k 对比**:
- top_k=1: 仅参考最相似案例
- top_k=3: 默认配置
- top_k=5: 更多参考，更长 prompt

---

## 六、实验执行计划

### 6.1 快速验证阶段（当前）
- 运行 10 个任务的消融实验
- 验证流程正确性
- 检查日志和结果格式

### 6.2 正式实验阶段（后续）
- 运行 30 个任务的完整实验
- 收集定量数据（成功率、覆盖率、迭代次数）
- 分析定性数据（检索命中、案例采纳）

### 6.3 深入分析阶段（可选）
- 按错误类型分组分析（syntax/runtime/assertion）
- 分析知识库增长对效果的影响
- 对比不同 top_k 和检索策略

---

## 七、结论与下一步

### 7.1 初步结论

**优势**:
1. 设计合理，实现了完整的检索增强闭环
2. 错误类型过滤提高了修复检索的精准度
3. 静默降级保证了系统鲁棒性

**待验证**:
1. RAG 对成功率的实际提升幅度
2. 知识库积累效果（随任务数量变化）
3. 不同错误类型的修复增益差异

### 7.2 下一步行动

1. **执行实验**: 运行 `experiments/evaluate_rag.py` 获取定量数据
2. **分析结果**: 比较 RAG enabled vs disabled 的性能差异
3. **深入诊断**: 若效果不明显，分析检索失败原因
4. **迭代优化**: 根据实验结果调整检索策略和入库规则

### 7.3 预期成果

- 明确的 RAG 贡献量化数据
- 针对失败案例的深度分析报告
- 可落地的 RAG 优化方案

---

**报告完成时间**: 2025-08-16  
**评估状态**: 代码分析完成，实验待执行  
**建议优先级**: P1（需尽快执行实验验证）
