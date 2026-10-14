# ULT Mut@k 真实基准变异指标报告（2026-10-14，零 LLM）

> 口径：cosmic-ray（ULT 官方，`ult_adapter.py`），target=fixed 正确实现，
> max_mutants=10（确定性截断面），
> timeout=120s（timeout 计 killed）。

## 1. 臂级结果

| 组 | 任务数 | 可测 | killed/total | pooled | 均值 |
|---|---|---|---|---|---|
| 生成测试·完整规格优先（探针 25） | 25 | 25 | 232/250 | 0.928 | 0.928 |
| 生成测试·纯 NL 规格优先（ult_lite46 46） | 46 | 46 | 439/460 | 0.9543 | 0.9543 |
| gold 官方测试（上界参照，探针 25） | 25 | 25 | 250/250 | 1.0 | 1.0 |

## 2. 配对子集（n=7/7，描述性）

探针（25）与 ult_lite46（46）任务重叠仅 7——配对子集为描述性，不作推断检验

| task | specir | replace |
|---|---|---|
| ult__BinaryFromFraction | 1.0 | 0.4 |
| ult__deg2HMS | 0.7 | 1.0 |
| ult__get_allen_relation | 1.0 | 1.0 |
| ult__max_rewards | 1.0 | 1.0 |
| ult__single_defcom_extract | 1.0 | 1.0 |
| ult__string_contrast | 1.0 | 1.0 |
| ult__windows_k_distinct | 1.0 | 1.0 |

cosmic-ray 版本 8.7.0，配置哈希 1e1230a7e298d1e2d7856ca437332e27702cfa1612dfc80ab71f9ca105b6ea22。

## 3. 解读边界

- max_mutants=10 为确定性截断面（与自研 AST 口径/D3 冒烟一致），非 cosmic-ray
  全变异体——跨报告引用须带此口径标签；
- 任务集不同（探针 25 vs ult_lite46 46，重叠 7）——臂级对比受任务混合混淆，
  配对子集仅 7 对，作描述性证据；
- 与合成集自研 mutation score（0.955 饱和）**不可直接比**（算子集/超时/
  变异体数量均不同，双口径分述纪律）。
