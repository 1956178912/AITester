"""S-1 跑后：三 seed 合并表 + 冻结决策规则 + README/ANALYSIS_REPORT（零 LLM）。"""
import json
from pathlib import Path

out = Path('experiments/results/s_round_examples_decision_20261018')
seed_reports = [
    ('42', 'Q-2 q_round_examples_ab_20261018', Path('experiments/results/q_round_examples_ab_20261018/ANALYSIS_REPORT.json')),
    ('43', 'R-1 r_round_examples_repro_20261018', Path('experiments/results/r_round_examples_repro_20261018/ANALYSIS_REPORT.json')),
    ('44', 'S-1 本批', out / 'ANALYSIS_REPORT.json'),
]
rows = []
for seed, source, path in seed_reports:
    r = json.loads(path.read_text(encoding='utf-8'))
    p = r['primary']
    det = p['llm_suite_detection']
    a, b = det['A'], det['B']
    loss = round((a['rate'] - b['rate']) * 100, 2) if (a['rate'] is not None and b['rate'] is not None) else None
    rows.append({
        'seed': seed, 'source': source,
        'A_correct': p['A_correct'], 'B_correct': p['B_correct'], 'delta': p['delta_B_minus_A'],
        'A_det': f"{a['detected']}/{a['measurable']}", 'A_rate': a['rate'],
        'B_det': f"{b['detected']}/{b['measurable']}", 'B_rate': b['rate'],
        'loss_pp': loss, 'b': p['b'], 'c': p['c'], 'p': p['mcnemar_one_sided_p'],
        'q2_rule_verdict': p['verdict'],
        'cost_usd': r.get('cost_total_usd'), 'wall_max': r.get('wall_max_seconds'),
    })

c1 = [row for row in rows if row['delta'] is not None and row['delta'] >= 5]
c2 = [row for row in rows if row['loss_pp'] is not None and row['loss_pp'] <= 5]
crit1 = len(c1) >= 2
crit2 = len(c2) >= 2
decision = 'enable_candidate' if (crit1 and crit2) else 'keep_off'

# 本批（seed44）补充：写入 ANALYSIS_REPORT
r44 = json.loads((out / 'ANALYSIS_REPORT.json').read_text(encoding='utf-8'))
r44['three_seed_decision'] = {
    'rule': {
        'c1_oracle_correct_delta_ge5_in_ge2of3': 'Δ=B_correct−A_correct ≥5 in ≥2/3 seeds',
        'c2_llm_suite_loss_le5pp_in_ge2of3': 'loss_pp=(A_det−B_det)×100 ≤5pp in ≥2/3 seeds',
        'enable_candidate_iff_both': True,
    },
    'seeds': rows,
    'criteria': {
        'c1_pass': crit1, 'c1_seeds_pass': [x['seed'] for x in c1],
        'c2_pass': crit2, 'c2_seeds_pass': [x['seed'] for x in c2],
    },
    'decision': decision,
    'note': 'decision support only, not a capability claim; production switch remains off by default.',
}
(out / 'ANALYSIS_REPORT.json').write_text(json.dumps(r44, ensure_ascii=False, indent=2), encoding='utf-8')

# README 补丁
rp = out / 'README.md'
s = rp.read_text(encoding='utf-8')
s = s.replace('# Q-2：oracle 示例通道生产化验证——预注册二臂 A/B（真 LLM，QuixBugs 20 任务）',
              '# S-1：seed-44 复现批 + 3-seed 生产化决策（预注册二臂 A/B，真 LLM，QuixBugs 20 任务）')
s = s.replace('> **性质：预注册判定测量（单次运行、小样本）**。判定规则在 `PREREG_DECISION.md` 跑前冻结；结果只按该规则报告 `confirmed` / `not_confirmed`，并披露 MDE/功效/局限；不做超出规则的 confirmatory 因果主张。',
              '> **性质：预注册决策支持（decision support，非能力主张）**。决策规则在 `PREREG_DECISION.md` 跑前冻结；本批只按该规则报告 `enable_candidate` / `keep_off`；生产开关默认关不变，enabling 需另行变更+回归。')


def f(v, nd=2):
    if v is None:
        return '—'
    if isinstance(v, float):
        return f'{v:.{nd}f}'
    return str(v)


table = '| seed | 来源 | A_correct | B_correct | Δ=B−A | A_det | B_det | loss_pp | b/c | McNemar p | Q-2 规则判定（参考） |\n|---|---|---|---|---|---|---|---|---|---|---|\n'
for row in rows:
    table += f"| {row['seed']} | {row['source']} | {row['A_correct']} | {row['B_correct']} | **{row['delta']:+d}** | {row['A_det']} | {row['B_det']} | **{f(row['loss_pp'])}** | {row['b']}/{row['c']} | {row['p']:.6f} | {row['q2_rule_verdict']} |\n"

summary = f"""## 0. S-1 决策摘要（三 seed 合并）

> 决策规则跑前冻结于 `PREREG_DECISION.md`：`enable_candidate` = ① oracle-correct Δ≥5 任务 in ≥2/3 seeds ∧ ② LLM-suite 损失 loss_pp≤5pp in ≥2/3 seeds；否则 `keep_off`。
> **决策支持、非能力主张；生产开关 `SPEC_ORACLE_EXAMPLES_ENABLE` 默认关不变。**

### 三 seed 合并表（主指标）

{table}
### 两条判据逐项

| 判据 | 结果 | 达成 seeds |
|---|---|---|
| ① oracle-correct Δ≥5 in ≥2/3 seeds | **{'PASS' if crit1 else 'FAIL'}** | {', '.join(x['seed'] for x in c1) or '—'} |
| ② LLM-suite loss_pp≤5pp in ≥2/3 seeds | **{'PASS' if crit2 else 'FAIL'}** | {', '.join(x['seed'] for x in c2) or '—'} |

### **决策：`{decision}`**

- {'两条判据均满足 → 进入 candidate 阶段（enabling 仍需另行变更+回归；生产默认关不变）。' if decision == 'enable_candidate' else '至少一条判据未满足 → 保持关闭（keep_off）；不自动生产化。'}
- 逐 seed Q-2 冻结规则口径判定（仅参考，不参与本决策规则）：{'; '.join(f"seed{x['seed']}={x['q2_rule_verdict']}" for x in rows)}。
"""
anchor = '## 1. 协议与切点'
assert anchor in s
s = s.replace(anchor, summary + '\n' + anchor, 1)

# 替换 §2（模板仍为 Q-2 规则）为 S-1 决策规则
st = s.find('## 2. 预注册判定（冻结规则）')
en = s.find('## 3. 两臂表（实测）')
assert st != -1 and en != -1
new2 = """## 2. 预注册决策规则（冻结，S-1）

**本批（seed44）只提供第三个 seed 的测量；决策 = 三 seed 合并规则（只读合并，不重跑 seed42/43）：**
- **`enable_candidate`** = ① Δ=B_correct−A_correct ≥ **5 任务** in **≥2/3 seeds** ∧ ② LLM-suite 损失 loss_pp=(A_det−B_det)×100 ≤ **5pp** in **≥2/3 seeds**；
- 否则 → **`keep_off`**。
- 声明：决策支持、非能力主张；生产开关默认关不变；enabling 需另行变更+回归。
- 同时报告逐 seed 的 Q-2 冻结规则口径判定/McNemar/verdict 分布/examples 来源/成本墙钟（见 §0/§4）。

"""
s = s[:st] + new2 + s[en:]

# 替换 §4（Q-2 规则段落）为 S-1 决策摘要（保留参考指标）
st = s.find('## 4. 主指标配对与判定')
en = s.find('## 5. 逐任务配对')
assert st != -1 and en != -1
new4 = f"""## 4. 主指标配对与判定（S-1：决策 + 本批参考指标）

**三 seed 决策**：① Δ≥5 in ≥2/3 seeds = **{'PASS' if crit1 else 'FAIL'}**（seeds {', '.join(x['seed'] for x in c1) or '—'}）；
② loss_pp≤5pp in ≥2/3 seeds = **{'PASS' if crit2 else 'FAIL'}**（seeds {', '.join(x['seed'] for x in c2) or '—'}）→ **决策 `{decision}`**。

**本批（seed44）参考指标（Q-2 冻结规则口径，不参与 S-1 决策）**：
- 共同任务 **{r44['primary']['common_tasks']}**；A_correct=**{r44['primary']['A_correct']}**，B_correct=**{r44['primary']['B_correct']}**（Δ=**{r44['primary']['delta_B_minus_A']}**；b=**{r44['primary']['b']}**，c=**{r44['primary']['c']}**，McNemar p=**{r44['primary']['mcnemar_one_sided_p']:.6f}**）；
- LLM-suite detection：A={r44['primary']['llm_suite_detection']['A']['detected']}/{r44['primary']['llm_suite_detection']['A']['measurable']}，B={r44['primary']['llm_suite_detection']['B']['detected']}/{r44['primary']['llm_suite_detection']['B']['measurable']}，loss_pp=**{f(rows[-1]['loss_pp'])}**；
- 本批 Q-2 规则 verdict（参考）：`{r44['primary']['verdict']}`。

"""
s = s[:st] + new4 + s[en:]

# §9 文件清单补充
s = s.replace('| `PREREG_DECISION.md` | 跑前冻结的预注册（判定规则/MDE/局限） |',
              '| `PREREG_DECISION.md` | 跑前冻结的决策预注册（三 seed 规则/局限） |')
s = s.replace('| `SHA256SUMS` | checksum_results.py --write 生成（verify 通过） |',
              '| `_helpers/` | 本批 runner 辅助 + finalize_s1.py（零 LLM 可复算三 seed 决策） |\n| `SHA256SUMS` | checksum_results.py --write 生成（verify 通过） |')
rp.write_text(s, encoding='utf-8')
print('finalize_s1 done: decision=', decision, '| c1=', crit1, c1, '| c2=', crit2, c2)
