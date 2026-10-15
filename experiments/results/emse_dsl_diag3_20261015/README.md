# SpecExpr DSL 拒绝分布诊断（emse_dsl_diag3，2026-10-15，零 LLM）

> 用途：EMSE 批次六（SpecExpr DSL 覆盖率提升）的**实测依据基**——在真实 LLM
> 产物语料上量化当前门的拒绝分布，决定"扩什么、不收什么"。零新 LLM 调用
> （语料=本地 Planner 缓存；对账=纯本地）。

## 语料与口径

- 语料：`~/.cache/aitester/llm` 的 **Planner** 缓存条目（system 含"测试规划师"），
  prompt 首个 ``` 块=被测源码（签名提取材料源），response=计划 JSON（含
  `*_expr` 形式化子句=compile_readiness 的靶）；
- 719 个含 `*_expr` 契约产物的计划 → **607 去重子句实例**（dedup：
  (dataset, function_name, kind, clause) 唯一，防 A/B 臂双计），
  涉及 91 个（dataset×函数）任务；数据集按 def 行匹配本地索引
  （quixbugs 246 / ult / other=合成集等）；
- 函数名解析 719/719 走 plan_name 路径（无 "unknown"/空名——M10 降级计划
  不产 *_expr，天然不在语料内）；
- 判定：当前门（2026-10-14 修复后：sole 函数名回退 + 内建类型名值位置放行），
  四门（形态/白名单/未知标识符/产物自检）与在线管线逐字一致。

## 核心结果（当前门，去重子句）

| 拒绝原因 | 计数 | 占比 |
|---|---|---|
| 可编译 | 537 | 88.5% |
| unknown_name | 40 | 6.6% |
| unsupported_operator | 25 | 4.1% |
| unsupported_syntax | 5 | 0.8% |

旧门（10-14 修复前）可编译率 0.8056 → 当前门 0.8847。分数据集：
quixbugs 0.8906（n=256）/ other 0.8782（n=238）/ ult 0.885（n=113）。

## 缺口图谱（扩文法决策依据）

**unsupported_syntax 5 条全部是冒号形态**：4 条切片（`result == s[::-1]`、
`result == s[:len(result)]`、`n <= 0 or result == s[:n - 1]`、`result == result[::-1]`）
+ 1 条双引号字符串内冒号（`result.startswith("result: ")`——被字符门**整体**误拒）。
LLM 无视提示"无冒号"禁令高频自然写切片 ⇒ 冒号入字符类是明确缺口。

**unsupported_operator 25 条 = 可收长尾 + 合法拒绝**：
- 可收（纯函数/纯只读方法，diag3 频次）：sum×3、set×3、hasattr×2、
  values×3、isupper×1、bit_length×1、bool×1、get×1；
- 合法拒绝（刻意不收）：域名属性 successor×5 / outgoing_nodes×1（任意属性链=
  注入面）、模块链 collections.abc.Sequence / heapq.heappushpop、
  被测函数自递归 fibonacci×4 / gcd×1 / factorial×1（语义扩展留待后续）。

**unknown_name 40 条全部是函数内部变量/模块级名**（left/right/scores/best/
i/j/n/memo/_STOCK/day/month/year…）：oracle 只绑定参数+result，这些名字
运行期 NameError ⇒ **正确拒绝**，非 DSL 缺口（属 Planner 提示遵从度问题，
自检③已点名）。

## 结论

1. 编译器对"LLM 已形式化子句"的接受率已达 88.5%——剩余拒绝多数合法；
2. 可行动缺口 = 切片/字符串内冒号（字符门）+ 约 20 条纯函数长尾（白名单门）；
3. 已据此实施 v4 扩展，前后对账见 `emse_dsl_extend_recheck_20261015/`
   （0.8847 → 0.9127，收复 17 条、零回退）。

## 复算

```bash
python3 experiments/emse_dsl_diag3.py --prior-gate   # 本报告的快照口径（v4 前门，常量摘除法）
python3 experiments/emse_dsl_diag3.py                # 当前门（v4 后）——会覆盖快照，勿用于归档
python3 experiments/emse_dsl_extend_recheck.py       # v4 前后对账（自含旧门复刻）
```

归档纪律：`DIAG3_REPORT.json` 是 **v4 实施前**的诊断快照（`meta.prior_gate_snapshot=true`）；
v4 后重跑默认口径会用新门覆盖它，故快照必须用 `--prior-gate` 重建。旧门复刻
（pre-10-14）需摘除三处常量（字符类冒号 + v4 白名单 + 类型名放行）才逐字忠实
——2026-10-15 归档重建时先后发现并修正了漏摘字符类/白名单两处高估。

注意：语料只含"有 *_expr 产出的计划"，衡量**编译器接受率**，不衡量 LLM
形式化意愿（后者=spec_expr_coverage，正交指标）。
