# ULT Mut@k 真实基准变异指标（2026-10-14，零 LLM）

> 复算：`experiments/emse_ult_mutk.py`（5 例测试 `tests/test_emse_ult_mutk.py`）；
> 口径：cosmic-ray 8.7.0（ULT 官方），target=`task_metadata.fixed`（正确实现），
> max_mutants=10（确定性截断面），timeout=120s（timeout 计 killed，2026-10-13 裁定）。
> 配置哈希 `1e1230a7e298d1e2d7856ca437332e27702cfa1612dfc80ab71f9ca105b6ea22`。

## 结果

| 组 | 任务 | killed/total | pooled |
|---|---|---|---|
| 生成测试·完整规格优先（specir 探针 25） | 25 | 232/250 | **0.928** |
| 生成测试·纯 NL 规格优先（ult_lite46 replace 46） | 46 | 439/460 | 0.9543 |
| gold 官方测试（上界参照，探针 25） | 25 | 250/250 | 1.0 |

配对子集（任务重叠仅 7，描述性）：specir 6/7 满分、replace 6/7 满分
（deg2HMS：specir 0.7/replace 1.0；BinaryFromFraction：specir 1.0/replace 0.4）。

## 结论（论文价值）

1. **填补 EMSE 报告 §0 表第 5 项**（mutation score 主指标未跑）：真实基准
   （ULT，cosmic-ray 官方口径）上生成测试 Mut@k=**0.928**，距 gold 上界
   1.0 仅 7.2pp——回应「合成集 mutation_score 0.955 饱和/变异体太弱」
   的审稿人质疑：在真实基准与官方变异协议下，测试质量仍然高；
2. **「变异强但缺陷盲」机制洞察**：同批 specir 生成测试 detection=0/24
   （不在缺陷码上变红）却杀死 92.8% 的 fixed 变异体——测试断言的多是
   buggy/fixed 上都成立的不变量（规格后置性质），对随机变异敏感、
   对种子缺陷不敏感。与「全绿假成功」叙事互补：**测试强度（变异维度）
   与缺陷检出（F2P 维度）是可分离的两种质量**；
3. specir（0.928）vs replace（0.9543）无 SpecExpr 增益证据（任务集不同，
   配对子集 7 对 5:2 平）——规格通道不改善变异维度，与 synthetic detection
   阴性（§6.8）一致：SpecExpr 的效应（若有）局限于 F2P 检出维度。

## 边界

- max_mutants=10 为确定性截断面（与自研 AST 口径/D3 冒烟一致），非全变异体；
- 臂级任务集不同（25 vs 46，重叠 7），配对子集仅描述性；
- 与合成集自研 mutation score 不可直接比（双口径分述）。

## 运行记录

- 墙钟 2h23m（ULT 含挂起测试：单任务 10 变异体 × 120s 超时 ≈ 20 分钟）；
- 零 LLM 调用；产物 JSON + MD 同目录；`chain.log` 为同链尾的全量 pytest
  阻断记录（沙箱 bulk-delete 守卫，非代码回归）。
