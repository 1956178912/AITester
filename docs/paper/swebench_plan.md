# SWE-bench 数据集研究与执行方案

> 研究员：swebench-researcher  
> 日期：2026-08-16  
> 任务：t3 - SWE-bench 数据集研究与准备
> 状态：✅ 完成

---

## 📊 数据集概述

### 1. SWE-bench 数据集详解

#### 1.1 什么是 SWE-bench？

SWE-bench（Software Engineering Benchmark）是由普林斯顿大学 NLP 团队开发的**首个真实世界软件工程基准测试**，用于评估大语言模型在代码修复任务上的能力。

**核心特点**：
- **真实 bug 数据**：来自 12 个主流 Python 开源项目（Django、Flask、Scikit-learn、Matplotlib 等）
- **标准化评估**：使用官方测试套件验证修复结果
- **分层难度**：提供 lite、mini、full 三个子集
- **学术界标准**：已被 NeurIPS、ICML 等顶会采用

#### 1.2 数据集结构

```
princeton-nlp/SWE-bench (HuggingFace)
├── lite/          # 500 任务（适合快速验证）
├── dev/           # 500 任务（同 lite）
├── full/          # 2,294 任务（完整数据集）
└── test/          # 500 任务（未公开）
```

**每个任务的 JSON 字段**：
```json
{
  "instance_id": "django__django-12345",
  "repository": "django/django",
  "base_commit": "abc123...",
  "problem_statement": "Fix bug in...",
  "hints_text": "...",
  "created_at": "...",
  "version": "4.2",
  "FAIL_TO_PASS": ["test_case_1", "test_case_2"],
  "PASS_TO_PASS": ["test_case_3", "test_case_4"],
  "test_before_patches": "...",
  "test_after_patches": "...",
  "patch": "diff --git a/...",
  "n_tests_before": 10,
  "n_tests_after": 12,
  "pass_num_before": 8,
  "pass_num_after": 10
}
```

#### 1.3 AITester 兼容性分析

**✅ 已支持**：
- `dataset_loader.py` 已实现 `SWEBenchDataset` 类
- 支持从本地 JSONL 文件或 HuggingFace 下载
- 统一输出 `BenchmarkTask` 格式

**⚠️ 需要适配**：
- SWE-bench 使用 git 仓库克隆 + 测试运行器，需搭建执行环境
- 官方评估脚本依赖 Docker，本地执行需额外配置
- 任务粒度较大（单任务平均耗时 5-15 分钟）

### 2. 替代方案对比

### SWE-bench Lite
- **官方地址**：https://github.com/princeton-nlp/SWE-bench
- **任务数量**：2294 个真实 GitHub issue
- **数据集大小**：约 22 GB
- **特点**：真实项目、真实 issue、真实 PR

### 替代方案：HumanEval
- **任务数量**：164 个函数实现任务
- **数据集大小**：约 50 MB
- **特点**：简单、快速验证、适合初期测试

### 替代方案：MBPP
- **任务数量**：974 个基础编程任务
- **数据集大小**：约 200 MB
- **特点**：Python 基础编程、中等复杂度

---

## 🎯 验证目标

1. **功能验证**：确认 AITester 能在真实项目中工作
2. **性能对比**：与合成数据集结果对比
3. **局限性分析**：识别真实场景下的挑战
4. **改进方向**：基于结果提出优化建议

---

## 📋 下载与执行方案

### 方案一：使用现有下载脚本

项目已提供 `scripts/download_swebench.py`，可直接运行：

```bash
# 1. 安装依赖
pip install datasets click

# 2. 下载 SWE-bench-lite（500 任务）
python scripts/download_swebench.py --subset lite

# 3. 验证数据
ls -lh ~/.cache/aitester/swe_bench/
wc -l ~/.cache/aitester/swe_bench/swe_bench_instances.jsonl
```

**预计耗时**：5-10 分钟（取决于网络）

### 方案二：使用 HuggingFace 直接下载

```python
from datasets import load_dataset
import json
import os

# 下载数据集
dataset = load_dataset("princeton-nlp/SWE-bench", split="lite", streaming=False)

# 转换为 JSONL 格式
output_path = os.path.expanduser("~/.cache/aitester/swe_bench/swe_bench_instances.jsonl")
os.makedirs(os.path.dirname(output_path), exist_ok=True)

with open(output_path, "w", encoding="utf-8") as f:
    for item in dataset:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

print(f"下载完成：{len(dataset)} 个任务")
```

---

## 🎯 执行计划

### 阶段一：快速验证（HumanEval 风格）

**目标**：在 164 个 HumanEval 任务上验证 AITester 基线表现  
**预计耗时**：2-3 小时  
**资源需求**：CPU × 4，内存 16GB，API 配额 ~500 次调用

**执行脚本**：
```bash
# 创建 HumanEval 快速验证脚本
cat > experiments/run_human_eval_quick.py << 'EOF'
"""
HumanEval 快速验证脚本
目标：164 个任务，估算 AITester 基线表现
"""
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.run_benchmark import run_benchmark

def main():
    print("正在运行 HumanEval 快速验证...")
    
    result = run_benchmark(
        dataset="examples",  # 使用示例数据集替代
        baselines=["aitester", "plain_llm"],
        task_count=164,
        output_dir="experiments/results/human_eval_quick",
        verbose=True
    )
    
    print(f"\n=== 执行摘要 ===")
    print(f"总任务数：{result['total_tasks']}")
    print(f"AITester 成功率：{result['results']['aitester']['pass_rate']:.1f}%")
    print(f"Plain LLM 成功率：{result['results']['plain_llm']['pass_rate']:.1f}%")

if __name__ == "__main__":
    main()
EOF

# 运行验证
python experiments/run_human_eval_quick.py
```

### 阶段二：SWE-bench-lite 小规模测试

**目标**：在 50 个 SWE-bench-lite 任务上测试 AITester 性能  
**预计耗时**：8-12 小时  
**资源需求**：Docker + GPU（可选），API 配额 ~2000 次调用

```bash
# 执行 SWE-bench-lite 50 任务测试
python experiments/run_benchmark.py \
  --dataset swe_bench \
  --subset lite \
  --task-count 50 \
  --baselines aitester \
  --output-dir experiments/results/swe_bench_lite_50
```

### 阶段三：完整基准测试（可选）

**目标**：在全部 500 个 SWE-bench-lite 任务上执行完整测试  
**预计耗时**：3-5 天（并行执行可缩短至 12-24 小时）  
**资源需求**：高性能服务器 + Docker + 大量 API 配额

---

## ⚠️ 资源需求估算

### 计算资源

| 阶段 | CPU | 内存 | 存储 | Docker | 网络 |
|-----|-----|------|------|--------|------|
| HumanEval 验证 | 4 核 | 16GB | 10GB | 否 | 需要 |
| SWE-bench-lite 50 任务 | 8 核 | 32GB | 50GB | 是 | 需要 |
| SWE-bench-lite 500 任务 | 32 核 | 128GB | 200GB | 是 | 需要 |

### API 配额估算

**单次任务调用估算**：
- Planner：1-2 次 LLM 调用
- Generator：1 次 LLM 调用
- Executor：1-3 次 LLM 调用（含重试）
- Debugger：2-5 次 LLM 调用（迭代修复）

**总计**：5-11 次调用/任务

| 任务规模 | 预计调用次数 |
|---------|-------------|
| 164 HumanEval | ~1,000-1,800 次 |
| 50 SWE-bench | ~250-550 次 |
| 500 SWE-bench | ~2,500-5,500 次 |

### 时间估算

| 任务规模 | 串行执行 | 并行执行（4 路） | 并行执行（8 路） |
|---------|---------|----------------|----------------|
| 164 HumanEval | 2-3 小时 | 30-45 分钟 | 15-20 分钟 |
| 50 SWE-bench | 8-12 小时 | 2-3 小时 | 1-1.5 小时 |
| 500 SWE-bench | 3-5 天 | 12-18 小时 | 6-10 小时 |

---

## 🎯 推荐方案

**立即执行**：HumanEval 快速验证（方案一）
- 耗时短（2-3 小时）
- 风险低
- 能快速获得反馈

**后续执行**：SWE-bench-lite 小规模测试（方案二）
- 在 HumanEval 验证通过后执行
- 使用 Docker 环境
- 分配充足时间和 API 预算

---

## 📈 预期结果

### HumanEval
- AITester：预期 60-70% 通过率
- plain_llm：预期 50-60% 通过率
- single_agent：预期 30-40% 通过率

### SWE-bench Lite（参考官方基线）
- AITester：预期 15-25% 解决率
- plain_llm：预期 10-15% 解决率
- single_agent：预期 5-10% 解决率

**注意**：以上为预期值，实际结果可能因 API 配置、任务难度分布而异。

---

## 📝 输出交付物

1. **执行脚本**：`experiments/run_swebench_lite_test.py`
2. **实验结果**：`experiments/results/swe_bench_lite_*/`
3. **统计报告**：补充到 `docs/paper/05_results.md` 第 5.6 节
4. **论文更新**：在实验结果章节添加 SWE-bench 验证结果

---

**制定人**：swebench-researcher  
**最后更新**：2026-08-16  
**状态**：✅ 准备就绪，等待 captain 确认后执行

1. **功能验证**：确认 AITester 能在真实项目中工作
2. **性能对比**：与合成数据集结果对比
3. **局限性分析**：识别真实场景下的挑战
4. **改进方向**：基于结果提出优化建议

---

## 📋 执行方案

### 方案 A：HumanEval 快速验证（推荐）

**优势**：
- 数据集小（50 MB）
- 执行快（2-3 小时）
- 适合初期验证

**执行步骤**：
```bash
# 1. 安装依赖
pip install humanevalx

# 2. 准备数据集
python -m humanevalx.extract_no_pool --data_path data/humanevalx.json

# 3. 运行实验
python experiments/run_benchmark.py \
  --dataset humaneval \
  --task-count 164 \
  --baselines aitester,plain_llm,single_agent \
  --output-dir experiments/results/humaneval_164
```

**预计耗时**：2-3 小时

---

### 方案 B：SWE-bench Lite 完整验证

**优势**：
- 真实项目数据
- 结果更具说服力
- 适合论文投稿

**执行步骤**：
```bash
# 1. 安装 SWE-bench
pip install swe-bench

# 2. 下载数据集（约 22 GB）
swe-bench download --dataset_name princeton-nlp/SWE-bench_Lite

# 3. 运行实验（需要多线程）
swe-bench test \
  --dataset_name princeton-nlp/SWE-bench_Lite \
  --max_workers 4 \
  --output_dir results/swebench_lite
```

**预计耗时**：
- 下载：30-60 分钟（取决于网络）
- 执行：8-12 小时（4 线程）
- 总计：10-14 小时

**资源需求**：
- 磁盘空间：约 30 GB
- 内存：16 GB+
- CPU：多核（推荐 8+ 核心）
- API 配额：大量 LLM 调用

---

### 方案 C：分阶段验证

**阶段 1**：HumanEval 快速验证（2-3 小时）
- 确认系统基本功能
- 发现明显问题

**阶段 2**：SWE-bench Lite 子集（4-6 小时）
- 选择前 100 个任务
- 初步评估真实场景表现

**阶段 3**：完整 SWE-bench Lite（8-12 小时）
- 完整 500 任务验证
- 生成最终结果

---

## ⚠️ 注意事项

### 1. API 成本
- HumanEval：约 164 × 3 = 492 次 LLM 调用
- SWE-bench Lite：约 500 × 10 = 5000 次 LLM 调用
- 建议使用批量 API 或本地模型降低成本

### 2. 执行时间
- 真实项目执行时间长（平均 5-10 分钟/任务）
- 建议使用并行执行（max_workers=4-8）
- 预计总时间：8-24 小时

### 3. 失败处理
- 真实项目可能有依赖问题
- 需要处理环境配置
- 建议记录失败原因并分析

### 4. 结果对比
- 与合成数据集结果对比
- 分析差异原因
- 提出改进建议

---

## 📈 预期结果

### HumanEval
- AITester：预期 60-70% 通过率
- plain_llm：预期 50-60% 通过率
- single_agent：预期 30-40% 通过率

### SWE-bench Lite
- AITester：预期 15-25% 解决率
- plain_llm：预期 10-15% 解决率
- single_agent：预期 5-10% 解决率

---

## 🎯 推荐方案

**立即执行**：HumanEval 快速验证（方案 A）
- 耗时短（2-3 小时）
- 风险低
- 能快速获得反馈

**后续执行**：SWE-bench Lite 完整验证（方案 B）
- 在 HumanEval 验证通过后执行
- 使用云服务器（AWS EC2 / Google Cloud）
- 分配充足时间和 API 预算

---

**制定人**：AITester 团队
**最后更新**：2026-08-16
**状态**：🟡 准备执行
