"""R-1 跑后：计算冻结复现判定 + 将诊断/复现摘要写入 README 与 ANALYSIS_REPORT（零 LLM）。"""
import json
import re
from pathlib import Path

out = Path('experiments/results/r_round_examples_repro_20261018')
rep = json.loads((out / 'ANALYSIS_REPORT.json').read_text(encoding='utf-8'))
a = rep['primary']['llm_suite_detection']['A']
b = rep['primary']['llm_suite_detection']['B']
a_rate, b_rate = a.get('rate'), b.get('rate')
loss_pp = round((a_rate - b_rate) * 100, 2) if (a_rate is not None and b_rate is not None) else None
direction_consistent = bool(loss_pp is not None and b_rate < a_rate and loss_pp >= 10)
repro = {
    'seed': 43,
    'rule': 'direction_consistent = (B_det < A_det) AND loss_pp >= 10',
    'A_detected': a.get('detected'), 'A_measurable': a.get('measurable'), 'A_rate': a_rate,
    'B_detected': b.get('detected'), 'B_measurable': b.get('measurable'), 'B_rate': b_rate,
    'loss_pp': loss_pp,
    'direction_consistent': direction_consistent,
    'verdict': 'reproducible_tradeoff' if direction_consistent else 'not_reproduced',
    'oracle_correct': {
        'A_correct': rep['primary']['A_correct'], 'B_correct': rep['primary']['B_correct'],
        'delta_B_minus_A': rep['primary']['delta_B_minus_A'],
        'b_B_only': rep['primary']['b'], 'c_A_only': rep['primary']['c'],
        'mcnemar_one_sided_p': rep['primary']['mcnemar_one_sided_p'],
    },
    'q2_frozen_rule_verdict_reference': rep['primary']['verdict'],
    'note': 'R-1 判定只按 PREREG_REPRO.md 冻结规则；Q-2 规则（non-inferiority/McNemar）仅作参考报告。',
}
rep['repro_judgment'] = repro
(out / 'ANALYSIS_REPORT.json').write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding='utf-8')

rp = out / 'README.md'
s = rp.read_text(encoding='utf-8')
diag = (out / 'DIAGNOSIS.md').read_text(encoding='utf-8')[:0]  # 仅确认存在
diag_exists = (out / 'DIAGNOSIS.md').exists()

summary = f"""## 0. R-1 摘要：诊断 + seed-43 复现判定

> 本批回答 Q-2 判定 `not_confirmed` 的直接原因——LLM-suite detection A 15/15=100% vs B 12/15=80%（3 任务）——是**真实 trade-off** 还是**单次运行噪声**。
> 判定规则跑前冻结于 `PREREG_REPRO.md`（seed=43、20 任务、A/B env 同 Q-2、预算 ≤$0.35/墙钟 ≤70min/watchdog 3600s）。

### A. 零 LLM 诊断（完整见 `DIAGNOSIS.md`）
- 两臂 **20/20** 任务 generated_test 均不同（test-name Jaccard 均值 0.197）；3 个损失任务的生成差异与普通任务同级（Jaccard 0.189，gt_len 相对差 0.445）——单次运行无法与一般随机性分离。
- `hanoi` 轨迹差异最强：A=1 轮 test_passed（detection=1）vs B=3 轮 max_iterations（detection=0，B oracle 也变 correct）→ 契约段可能改变 Planner→生成/修复行为；`detect_cycle`（B 测试 15 vs A 9）与 `knapsack`（A 24 vs B 10）均属生成内容差异。
- 候选机制排序：(a) 契约段改变下游生成/修复行为（正证据：oracle-correct 0→6、examples 17/20 来自 planner；但无法与随机性分离） > (b) 随机性（全量生成差异同级） > (c) oracle-suite 直接影响（N-3 口径上排除）。

### B. seed-43 复现判定（冻结规则）

| 项 | 值 |
|---|---|
| A_detection | {a.get('detected')}/{a.get('measurable')} = {a_rate} |
| B_detection | {b.get('detected')}/{b.get('measurable')} = {b_rate} |
| 损失 (pp) = (A−B)×100 | **{loss_pp}**（阈值 ≥10pp） |
| direction_consistent | **{direction_consistent}** |
| **复现判定** | **`{repro['verdict']}`** |
| oracle-correct（参考） | A={rep['primary']['A_correct']} / B={rep['primary']['B_correct']}（Δ={rep['primary']['delta_B_minus_A']}；b={rep['primary']['b']}, c={rep['primary']['c']}, McNemar p={rep['primary']['mcnemar_one_sided_p']:.6f}） |

- **解释**：若 `reproducible_tradeoff` → 检出损失在独立 seed 下方向一致（≥10pp），登记为真实风险、生产开关保持关；
  若 `not_reproduced` → 本轮未复现，视为单次运行噪声，**仍不自动生产化**，登记下一轮 3 臂复核。
- Q-2 冻结规则（non-inferiority/McNemar）的参考判定：`{rep['primary']['verdict']}`（仅参考，不用于 R-1 判定）。
"""
# 插入 §0 摘要（在 > 引言块之后、## 1 之前）
anchor = '## 1. 协议与切点'
assert anchor in s
s = s.replace(anchor, summary + '\n' + anchor, 1)

# 替换 §4（Q-2 冻结规则段落）为 R-1 复现判定（保留 MDE 披露）
start = s.find('## 4. 主指标配对与判定')
end = s.find('## 5. 逐任务配对')
assert start != -1 and end != -1
new4 = f"""## 4. 主指标配对与判定（R-1：复现规则 + 参考指标）

**R-1 冻结复现判定**（`PREREG_REPRO.md`）：
- A_detection = **{a.get('detected')}/{a.get('measurable')} = {a_rate}**；B_detection = **{b.get('detected')}/{b.get('measurable')} = {b_rate}**；损失 = **{loss_pp}pp**（阈值 ≥10pp）；
- `direction_consistent` = **{direction_consistent}** → **`{repro['verdict']}`**。

**参考（Q-2 冻结规则口径，不用于 R-1 判定）**：共同任务 **{rep['primary']['common_tasks']}**；A_correct=**{rep['primary']['A_correct']}**，
B_correct=**{rep['primary']['B_correct']}**（Δ=**{rep['primary']['delta_B_minus_A']}**；b=**{rep['primary']['b']}**，c=**{rep['primary']['c']}**，
McNemar 单向 p=**{rep['primary']['mcnemar_one_sided_p']:.6f}**）；Q-2 规则 verdict=`{rep['primary']['verdict']}`。

- **MDE 披露（oracle-correct）**：n={rep['primary']['common_tasks']}、单次运行；c=0 时需 b≥5 才 p<0.05（b=4 时 p=0.0625，b=5 时 p=0.03125）。
- **复现批的 seed 差异**：seed=43 的 quixbugs 任务子集/顺序可能与 seed=42 不同 → 本批评测"臂级方向复现"，非逐任务复现；任务集合以本批批次 JSON 为准。

"""
s = s[:start] + new4 + s[end:]

# §8 局限补充 R-1 特有
s = s.replace('- `TEMPERATURE=0` 仍有服务端非确定性；两臂并发共享 CPU（后处理指标受争抢影响）。',
              '- `TEMPERATURE=0` 仍有服务端非确定性；两臂并发共享 CPU（后处理指标受争抢影响）。\n- R-1 为单次 seed-43 复现批：只判定方向一致性（≥10pp），不做事后改规则/不做 confirmatory 主张。')

# §9 文件清单补充
s = s.replace('| `PREREG_REPRO.md` | 跑前冻结的预注册（判定规则/MDE/局限） |',
              '| `PREREG_REPRO.md` | 跑前冻结的复现预注册（seed=43/判定规则/局限） |')
s = s.replace('| `SHA256SUMS` | checksum_results.py --write 生成（verify 通过） |',
              '| `DIAGNOSIS.md` / `DIAGNOSIS_EVIDENCE.json` | 零 LLM 诊断报告 + 机读证据（逐任务表/mismatch 时间线/机制判断） |\n| `_helpers/` | 诊断/复现判定脚本（零 LLM，可复算） |\n| `SHA256SUMS` | checksum_results.py --write 生成（verify 通过） |')
rp.write_text(s, encoding='utf-8')
print('finalize done: verdict=', repro['verdict'], '| loss_pp=', loss_pp, '| direction_consistent=', direction_consistent)
