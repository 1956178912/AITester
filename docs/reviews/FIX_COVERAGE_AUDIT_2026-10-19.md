# 修复覆盖率缺口审计（2026-10-19，零 LLM）

> **性质**：对 V/W 两轮第三方评审修复的**测试锁定充分性**审计（不是功能审计）。
> **审计对象**：`ff15a2f`（V 轮修复起点）→ `HEAD` 之间 `src/` 的全部修复新增代码。
> **花费**：真实 LLM **$0**（纯静态 + 全量测试覆盖率数据）。
> **结论**：552 行修复新增可执行代码中，**37 行（6.70%）从未被任何测试执行**；
> 其中 6 行属于 P1 修复的**核心契约**，已补 5 个回归锁并逐项通过变异验证；
> 其余 31 行经分类为防御性/环境受限分支，记录在案。
> **测试基线**：审计前后均全量 **9139 passed / 19 skipped / 0 failed**（沙箱口径）。

## 1. 动机

`73481bb`（V 轮）之后，第二轮第三方复核查出 **A07/A09/A10 三项 P1 是"修复的未覆盖子场景"**
——代码已修、接口存在、主流程有测试，但某个分支路径零覆盖。这类缺陷的特征是：

> **把该分支回退掉，全套 9000+ 测试无一告警。**

这意味着"全量测试绿 + 覆盖率 96.49%"并不能证明修复被锁住：总量指标会掩盖局部空白。
本轮把这个检查显式化、可重跑化。

## 2. 方法与口径

1. **新增行**：`git diff --unified=0 ff15a2f HEAD -- src/` 的 `+` 侧行号（HEAD 行号）；
2. **可执行行**：**以 `coverage.xml` 的 `<line>` 条目为唯一权威**。这一点是本轮踩过的坑：
   最初自建判定（用字节码 `co_lines()`）把跨行函数签名的每个参数行都算成可执行行，
   得出「1400 行新增、63% 未覆盖」的假象；改用 coverage 行集合后为「552 行、6.70%」。
   coverage.py 用真实 trace 行事件判定，已排除 docstring、跨行签名参数、多行字面量；
3. **缺口**：新增行中 `hits == 0` 的行；
4. **数据新鲜度**：`coverage.xml` 必须由当前 HEAD 产出。仓内已有的 09:27 版本虽是
   在 W 轮代码上跑的（复算一致），但审计一律重跑 `make test-cov` 后再取数；
5. **变异验证**：每个补测都先证明"抹掉目标分支后用例必红"，再证明"HEAD 上必绿"。

工具：`scripts/tools/audit_fix_coverage.py`（可重跑，见附录）。

## 3. 结果总览

```
基线 ff15a2f → HEAD；src/ 修复新增且被 coverage 测量的行 552，其中未执行 37（6.70%）

!! src/agents/base_agent.py                     103      5  361, 370, 787, 788, 1023
   src/agents/executor.py                         6      0
   src/agents/executor_modes.py                   6      0
!! src/agents/executor_runtime.py               131     14  191, 267, 268, 290, 291, 294, 297, 298, 300, 410, 416-419
   src/agents/flaky_gate.py                       0      0
!! src/agents/llm_client.py                      49      3  592, 753, 771
   src/agents/semantic_cache.py                  12      0
!! src/api/api_manager.py                        91      6  178, 183, 184, 239, 240, 263
   src/graph/mutation_advisor.py                  12      0
   src/graph/nodes.py                             43      0
   src/graph/state.py                              0      0
   src/measurement/mdo.py                          3      0
   src/measurement/retrieval_quality.py           15      0
!! src/observability/trace.py                    31      9  147-149, 260-262, 469-471
   src/tools/multi_candidate.py                    1      0
   src/tools/patch_rollback.py                     1      0
   src/utils/logging_utils.py                      0      0
   src/utils/process_utils.py                     48      0
```

值得注意的**已充分覆盖**项：`process_utils.py`（A08 P0 凭证隔离 + A12 Windows 回收）
48 行新增全部被覆盖，包括 Windows 分支（用 Mock 覆盖）；`semantic_cache.py`（A09 补修）
12 行全绿；`nodes.py`（A14/A16）43 行全绿。

## 4. 已补的三组 P1 契约缺口

补测落在 `tests/test_fix_coverage_audit_2026_10_19.py`（5 个用例，零 LLM/零网络）。

### 4.1 A11 跨模型故障转移前的预算复查（`base_agent.py:1022-1023`）

**为什么漏**：A11 的预算复查有两层，既有测试只锁住第一层。

| 层 | 位置 | 触发时机 | 既有测试 |
|---|---|---|---|
| 第一层 | `pre_retry_check=_raise_if_budget_exceeded` 传入重试器 | **同模型重试前**（需 `max_retries>0`） | `test_budget_rechecked_before_retry` ✅ |
| 第二层 | `for model` 循环顶部 `if is_budget_exceeded()` | **跨模型故障转移前** | 无 ❌ |

**后果**：第一个模型失败后预算已耗尽，代码仍会继续尝试第二个、第三个模型，把预算闸绕过。

**变异证据**：把第二层条件改为恒假后，`test_budget_rechecked_before_retry` **仍然通过**
（它走第一层），仅新增用例变红，日志显示 `model-2` 被调用。这直接证明第一层的测试
无法保护第二层。

### 4.2 A11 zai 路径的预算异常透传（`llm_client.py:589-592`）

`_call_zai` 曾用 `except Exception` 把所有失败统一包成 `RuntimeError("zai API 调用失败")`。
预算超限被裹进去后，上层只看到普通 API 故障，于是**继续故障转移到下一个模型**。
修复加了 `except BudgetExceededError: raise`，但该分支零覆盖。

**变异证据**：把该分支改成永不匹配（让它落入通用 `except`）后，新增用例变红
（抛出的是 `RuntimeError` 而非 `BudgetExceededError`）。

### 4.3 A15 同端点不同 key 的实例 ID 后缀（`api_manager.py:239-240`）

A15 的端点实例 ID 只由 `base_url` 派生（刻意不让凭证进节点键）。因此
**同 model、同 base_url、不同 api_key**——配额轮询的常见配置——会算出**相同**实例 ID，
第二个实例必须退化为 `<id>#2`。

现有 8 个 A15 测试全部使用不同 `base_url`（digest 天然不同），该后缀分支从未执行。

**后果**：两个实例塌缩为一个，"同 model 多 provider 全保留"的修复在该配置下失效。

**变异证据**：抹掉 `while key in self.health_nodes` 后，`len(keys)` 从 2 变 1，
仅新增用例变红。

### 4.4 A09 旧格式缓存键的键材料逐字节复刻（`base_agent.py:361, 370`）

A09 保留「旧格式只读回退」，前提是能用**旧公式**重算出旧文件名。键材料为
`prompt + \x00 + system + t<temperature> + jm1 + m<model> + ns<namespace>`。
其中 `jm1`（json_mode）与 `ns<namespace>` 两个分支零覆盖。

**后果**：键材料一旦漏项/多项/顺序变化，升级后**所有历史缓存都命中不到**——表现为
重复计费，而功能测试全绿（新键路径正常）。其中 `ns` 更隐蔽：命名空间漏进键材料会导致
**跨实验命名空间互相命中缓存**，造成静默污染。

**变异证据**：抹掉两个材料分支后，两个新增用例同时变红（md5 前 16 位不匹配）。

## 5. 剩余 31 行的分类与处置

| 位置 | 行数 | 语义 | 分类 | 处置 |
|---|---|---|---|---|
| `executor_runtime.py` | 14 | 模块探测子进程的失败分支（rc≠0 / 无输出 / JSON 不可解析 / 结构非法）、`token` 非 str 守卫、`shutil.which` 解析 | 错误处理分支 | 记录，暂不补——需 mock 子进程多层返回值，性价比低 |
| `trace.py` | 9 | A20「坏行不落盘」三处守卫（结构脱敏失败降级 / 脱敏后非 JSON 丢弃 / 诊断快照坏行丢弃） | 防御语义 | **建议下轮补**：这是 A20 的核心契约，可用"让 `json.dumps` 产出非法串"的注入测试锁定 |
| `api_manager.py` | 4 | `178` 早退（键已非裸模型名）、`183-184` promote 时基 ID 冲突、`263` `_node_key` 兜底 | 防御/极边界 | `183-184` 需手工构造内部字典状态；记录 |
| `base_agent.py` | 2 | `787-788` 旧格式读取的宽泛 `except` | 防御 | 记录 |
| `llm_client.py` | 2 | `753/771` 空身份返回空串 | 边界返回值 | 记录（`fingerprint("")` 语义已由类型注解表达） |

合计 14 + 9 + 4 + 2 + 2 = 31 行，与总计 37 行减去已补 6 行吻合。

## 6. 结论

1. **修复新增代码的测试密度低于整体**：6.70% 未执行 vs 全仓 3.51% 未覆盖（96.49% 行覆盖）。
   考虑到修复代码集中在错误路径与防御分支，这个差距可以解释，但不应继续扩大。
2. **三组 P1 契约缺口全部通过变异验证**：它们不是"覆盖率数字不好看"，而是
   **回退后无人发现**的真实风险点。
3. **方法论沉淀**：`scripts/tools/audit_fix_coverage.py` 可对任意"修复起点→HEAD"
   重跑，建议纳入每轮第三方评审修复后的例行检查（不必进 CI 门禁——它是审计，
   不是红线；缺口存在时返回 0）。
4. **未做的事**（诚实披露）：本轮**没有**重跑全量变异测试矩阵（`make self-mutation`
   覆盖的是 3 个核心模块的等距抽样），也没有对 `experiments/` 侧修复做同样的审计
   （本轮只审 `src/`）。

## 附录：复跑

```bash
# 1) 产出与 HEAD 对齐的覆盖率（约 3 分钟）
make test-cov

# 2) 审计
python scripts/tools/audit_fix_coverage.py                    # 默认基线 ff15a2f
python scripts/tools/audit_fix_coverage.py --json /tmp/audit.json

# 3) 本轮新增的回归锁
pytest tests/test_fix_coverage_audit_2026_10_19.py -q         # 5 passed
```
