# 评测诚信 Checklist v1（P3，2026-10-18 第三轮独立评审落地）

> **定位**：把 AITester 自身"测量伪影系列 + 口径纪律"固化为**可执行 checklist**，
> 使任何 LLM 测试生成/修复实验（本项目批次或外部公开工件）都能被同一把尺子
> 检验。配套校验器：`experiments/eval_integrity_check.py`（零 LLM，静态检查）。
>
> **理论依据（一手）**：Zhao/Zhou/Cohen（ISSTA 2026, DOI 10.1145/3832093）——
> coverage/mutation 等代理指标的效度**依赖语境**，未修正即高估；ULT（TOSEM 2026,
> DOI 10.1145/3805043）——污染基准系统性高估；MAST（arXiv:2503.13657）——47% 多
> agent 失败可归因验证环节。本 checklist 是上述结论在"工件级"的操作化。
>
> **执行方式**：`python experiments/eval_integrity_check.py --artifact-dir <目录>
> [--artifact-dir ...] [--strict]`；退出码 0 = 硬检查全过，1 = 存在 FAIL
> （`--strict` 时 WARN 亦计失败）。

## 检查项总表

| ID | 检查 | 等级 | 失败含义 | 项目内依据 |
|---|---|---|---|---|
| IC-1 | provenance 完备性（git_sha / git_dirty / model_name / temperature） | FAIL | 批次不可溯源，不得作确认性证据 | BASELINE provenance 字段；`check_model_fingerprint` |
| IC-2 | 模型指纹 pinned | WARN | 降级为 B 级证据，仅可并列报告 | B2 锁指纹批（`model_fingerprint.pinned=true`） |
| IC-3 | fail-closed None 纪律（detection/repair/false_fix 的 None 行不进分母，校验器独立重算对账） | PASS+披露 | 以 0 记 None = 系统性低估（U1 教训） | A-06 判分口径；`tests/test_m1_*` |
| IC-4 | 补丁应用验证（补丁存在必须 `patch_validate_verdict ∈ {evidence, applied}`；弃权门 `patch_abstained` 例外） | FAIL | 补丁存在却从未验证 = ADR-0021 类伪影（假成功通道） | ADR-0021/0020；`tests/test_apply_patch_*` |
| IC-5 | 缓存 namespace 隔离（同目录多批次 namespace 互异） | FAIL | 跨臂/跨批命中污染，temp=0 下把重跑伪装成新实验 | 缓存纪律（`AITESTER_CACHE_NAMESPACE`） |
| IC-6 | SHA256SUMS 校验 | FAIL（有清单时）/ WARN（无清单） | 工件被事后修改而数字未同步 | `scripts/gates/checksum_results.py` |
| IC-7 | 变异得分报告纪律（有分母时分数∈[0,1] 且 killed≤total；无分母 = 占位值，禁用于跨系统对比） | FAIL（矛盾）/ WARN（占位） | Mut@k 三偏差（随机截断/恒红平凡击杀/gold 未验证）未修正即高估 | EMSE Mut@k 修正链；`emse_*_mutk_full_*` |
| IC-8 | 不可测披露（detection_rate=None 行数显式计数） | PASS+披露 | 把不可测当失败/当成功都是口径污染 | fail-closed 纪律；None-记-0 勘误史 |

## 使用规程

1. **跑批后必跑**：任何对外引用数字的批次，产出时跑一次本校验器，报告随工件
   入库（`--md`/`--json` 输出到工件目录）。
2. **跨批对比前必跑**：两批次 IC-1/IC-2/IC-5/IC-6 状态不一致时，禁止合并或
   并列对比（先披露差异）。
3. **外部工件重放**（P3 中期目标）：对 ULT 官方 12 模型结果、TestGenEval 公开
   产物等应用同一 checklist；凡 IC-3/IC-7 类口径信息缺失的公开结果，标注
   "口径不完整，不可直接对比"。
4. **WARN 不阻塞、但必须披露**：IC-7 占位值（协议内未测变异得分）出现在引用
   位置时必须带"未测"标签——本项目 B2/df_spec 批次的 608/51 行即此类。

## 已知边界（v1）

- 只覆盖**工件级静态诚信**；不检查统计功效、样本量充分性、基准选择偏差
  （后者属预注册与评审流程，见 `docs/preregistration.md`）。
- IC-4 的"已验证"语义以 `patch_validate_verdict` 字段为准；外部工件无该字段
  时整项降级为 WARN（口径不完整）。
- IC-3 的重算对账目前只在校验器内部报告（`recomputed` 节），未与批次自报
  汇总做自动断言——v2 可加 `--assert-summary` 模式。

## 与项目门禁的关系

本 checklist **不替代** `scripts/gates/` 的提交期门禁（那些检查代码/文档/
配置的一致性）；它检查的是**实验数据工件**的诚信，运行时机是"跑批后/引用前"。
两者共同构成"代码可信 → 工件可信 → 数字可信"的第三层。
