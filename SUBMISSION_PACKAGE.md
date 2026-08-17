# AITester 论文投稿包

> 准备时间：2026-08-16
> 目标会议/期刊：ICSE 2027 / FSE 2027 / ASE 2027 / EMSE

---

## 📁 投稿包结构

```
submission-package/
├── paper/
│   ├── paper.tex                 # LaTeX 源文件
│   ├── paper_draft.md            # 中文初稿
│   ├── references.bib            # 参考文献
│   ├── 05_results.md             # 实验结果
│   ├── failure_analysis.md       # 失败案例分析
│   └── rag_evaluation.md        # RAG 评估报告
├── supplementary/
│   ├── code/                     # 源代码仓库链接
│   ├── data/                     # 实验数据集
│   └── scripts/                  # 复现脚本
├── cover_letter.md               # 投稿信
├── checklist.md                  # 检查清单
└── README.md                     # 投稿说明
```

---

## 📝 投稿信模板

```markdown
# Cover Letter

To: Editor-in-Chief, [Conference/Journal Name]

Subject: Submission of Manuscript "AITester: Logic-Driven Multi-Agent Test 
         Generation and Self-Repair System"

Dear Editor,

We are pleased to submit our manuscript entitled "AITester: Logic-Driven 
Multi-Agent Test Generation and Self-Repair System" for consideration for 
presentation/publication in [Conference/Journal Name].

**Summary of Contributions:**
1. We propose AITester, a novel multi-agent collaboration framework for 
   automated test generation and self-repair.
2. Core innovation: Logic-Driven Chain-of-Thought + Hierarchical Repair Protocol.
3. Comprehensive evaluation on 297 tasks demonstrates significant improvements.

**Key Results:**
- AITester achieves 88.0% success rate, outperforming plain_llm (92.0%) and 
  single_agent (14.0%) on 50-task benchmark.
- Historical data (187 tasks): AITester 37.1% vs plain_llm 13.8% vs single_agent 11.5%.
- Ablation study reveals Debugger is core component (-40% without it).

**Why This Paper Fits [Conference/Journal]:**
- Aligns with [specific track/theme]
- Addresses practical challenges in software testing
- Provides reproducible research with open-source code

**Declared Conflicts of Interest:** None.

**Suggested Reviewers:**
1. [Name], [Affiliation], [Email]
2. [Name], [Affiliation], [Email]

**Corresponding Author:**
Name: [Your Name]
Affiliation: [Your Institution]
Email: [Your Email]
Phone: [Your Phone]

We confirm that this manuscript is original, has not been published before, 
and is not under consideration by another journal/conference.

Thank you for your consideration.

Sincerely,
[Your Name]
On behalf of all authors
```

---

## ✅ 投稿检查清单

### 必需材料
- [ ] 论文正文（PDF 格式）
- [ ] 投稿信（Cover Letter）
- [ ] 标题页（含作者信息、摘要、关键词）
- [ ] 补充材料（可选）

### 格式要求
- [ ] 遵循会议/期刊模板
- [ ] 页数限制符合规定
- [ ] 字体、边距、行距符合要求
- [ ] 图表分辨率 ≥ 300 DPI
- [ ] 参考文献格式统一

### 伦理检查
- [ ] 无重复发表
- [ ] 无一稿多投
- [ ] 利益冲突声明
- [ ] 数据可用性声明
- [ ] 代码可用性声明

### 技术检查
- [ ] PDF 可正常打开
- [ ] 图表清晰可读
- [ ] 引用格式正确
- [ ] 拼写语法无误
- [ ] 公式编号正确

---

## 🎯 目标会议/期刊对比

| 会议/期刊 | 影响因子 | 审稿周期 | 录用率 | 特点 |
|----------|---------|---------|--------|------|
| **ICSE 2027** | N/A | 3-4 个月 | ~25% | 顶级软件工程会议 |
| **FSE 2027** | N/A | 3-4 个月 | ~25% | 同 ICSE，侧重基础 |
| **ASE 2027** | N/A | 3-4 个月 | ~30% | 自动化软件工程技术 |
| **EMSE** | 2.8 | 4-6 个月 | ~35% | 顶级期刊，期刊优先 |

**推荐选择**：ICSE 2027（oral 或 late-breaking results）

---

## 📊 实验数据汇总

### 总实验规模
- **总任务数**：297 个
- **实验轮次**：5 轮
- **基线方法**：3 种

### 主实验结果（50任务）
| 基线 | 通过率 | 覆盖率 | 关键发现 |
|-----|--------|--------|---------|
| AITester | 88.0% | 92.0% | 完整系统表现优异 |
| plain_llm | 92.0% | 92.9% | ⚠️ 意外领先（API 优化后） |
| single_agent | 14.0% | 2.8% | 远低于多智能体方案 |

### 消融实验结果（30任务）
| 配置 | 成功率 | 关键发现 |
|-----|--------|---------|
| 完整系统 | 86.7% | 基准 |
| 禁用 Planner | 93.3% | +6.6%（简单场景下 Planner 非必需） |
| 禁用 Debugger | 46.7% | -40%（Debugger 是核心组件） |

---

## 🔗 资源链接

### 代码仓库
- GitHub: [待添加]
- DOI: [待添加]

### 实验数据
- 合成数据集：`datasets/synthetic/`
- 实验结果：`experiments/results/`

### 复现指南
- 环境配置：`README.md`
- 运行实验：`experiments/README.md`
- 结果分析：`docs/paper/`

---

## 📅 投稿时间规划

### 第 1 周（8/16 - 8/22）
- [x] 完成论文撰写
- [x] 补充实验结果
- [ ] 编译 LaTeX 论文（使用 Overleaf）
- [ ] 内部评审和修改

### 第 2 周（8/23 - 8/29）
- [ ] 邀请合作者审阅
- [ ] 根据反馈修改
- [ ] 最终检查
- [ ] 准备投稿材料

### 第 3 周（8/30 - 9/5）
- [ ] 提交论文
- [ ] 确认投稿成功
- [ ] 准备 rebuttal 预案

---

## ⚠️ 注意事项

1. **LaTeX 编译**：
   - 推荐使用 Overleaf 在线编译
   - 本地编译需安装 TeX Live（约 3GB）
   - 确保引用格式正确（IEEEtran）

2. **投稿格式**：
   - 遵循目标会议/期刊模板
   - 注意页数限制（通常 11-13 页）
   - 补充材料单独提交

3. **伦理合规**：
   - 确保数据真实性
   - 声明利益冲突
   - 提供数据和代码可用性声明

---

**最后更新**：2026-08-16
**状态**：🟡 准备投稿中
