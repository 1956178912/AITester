# Q-2 零 LLM 预检设计 + dry-run 证据（准备阶段）

> 跑批前零 LLM 准备产物；真实切点/成本以拿到 Q-1 cut 后的 `PREFLIGHT.json` 为准。
> 事故与加固见 `_incident_unintended_llm_launch_20261018/README_INCIDENT.md`。

## 预检实现（`experiments/run_q_examples_ab.sh` [1/8]，零 LLM）

- 切点/干净度/预注册冻结：`--expect-sha` 校验；**真实模式强制 dirty=0**；`PREREG.md` 不得含 `DRAFT`/占位符且须含切点 sha；`.env.local` 在场；
- Q-1 接线静态检查：`run_benchmark.py` 的 `SPEC_ORACLE_EXAMPLES_ENABLE`（env snapshot）与行字段 `spec_oracle_examples_source`/`count`；`planner.py` 契约标记；
- Q-1 契约测试 `tests/test_oracle_examples_production.py`（零 LLM；存在时运行，失败即阻断）；
- 两臂 env 有效值实测（A: exec=true/examples=false；B: true/true；`AITESTER_PROFILE=logic` 显式值不被 setdefault 覆盖）；
- 成本/墙钟估算：tokens/task=16000、in_share=0.72（历史 aitester/logic QuixBugs 批次）、deepseek-flash 价目表；>$0.5 或 >110min → 降 15 任务/臂并写 `PREREG_DOWNGRADE.md`；
- TOCTOU 守卫：记录 `run_benchmark.py`/`planner.py` sha256，launch 前复核（并发编辑即中止）；
- 零 LLM 自测模式：`--dry-run`（允许 dirty/feature 缺失）与 `--preflight-only`（真实门禁语义、绝不 launch）。

## dry-run 证据（机制自检，非真实批）

- 执行：`bash experiments/run_q_examples_ab.sh --root /Users/wangchenyu/Workspace/AITester --expect-sha 6e6c3392c1a884e3061efde527511d9dec87d8bd --dry-run`
- 结果：**通过**（exit 0；未执行任何 LLM 调用、未产出批次工件）
- feature_present=True（主树已含 Q-1 在途接线；真实跑批仍要求干净切点 worktree + 冻结 PREREG）
- blocking=[]；warnings=[]
- 两臂 env probe：A='true false'，B='true true'（true false / true true，distinct）
- 成本估算：$0.35328（tokens≈640000；20 任务/臂，无需降级）；墙钟估算 48.3min（≤110min）

## 安全门禁实测（事故后加固验证；均零 LLM、无 launch）

| 场景 | 期望 | 实测 |
|---|---|---|
| 真实门禁 on dirty 主树（preflight-only） | exit 2 阻断 | exit 2；staging/log 工件 0 |
| 干净临时仓库 + DRAFT PREREG（preflight-only） | exit 2 阻断 | exit 2；无 launch |
| 干净临时仓库 + 冻结 PREREG + feature 缺失（preflight-only） | exit 3 阻断 | exit 3；无 launch |

## 真实跑批（待 Q-1 切点后）

1. Lead 提供 `q-examples` sha + worktree → checkout 该 sha、更新并冻结 PREREG §0（写入切点/命令，移除 DRAFT）、记录 PREREG sha256；
2. `bash experiments/run_q_examples_ab.sh --root <worktree> --expect-sha <sha> --require-clean-root`；
3. 预检（含 Q-1 契约测试 + TOCTOU）通过后两臂同秒并发；跑后聚合 → README/ANALYSIS_REPORT.json/SHA256SUMS → 报告。
