# BD 轮：MDO 的两个 rc==0 判绿点收口（2026-10-21，零 LLM）

**范围**：`src/measurement/mdo.py`（MDO：政策无关变异判别力度量）。这是
F03 缺陷族（pytest 对全 skip / xfail / xpass / deselect 的套件同样返回
`rc==0` 且摘要 `passed==0`）在**测量指标实现**中的最后两个裸判绿点；
BA / BB / BC 已收口 M1 与 experiments 侧消费点，MDO 的基线/变异体判定
从未接过共享谓词。

**结论**：两个判绿点全部接入有效通过证据；谓词上移到
`src/utils/pytest_output.py` 作为单一事实源，`experiments/_m1_metrics.py`
保留同名别名（同一对象），消除"两套实现漂移"的结构性风险。
**15 例新锁 + 变异 6 锚点全红（8 / 2 / 24 / 21 / 2 / 1）+ 中性对照 0 红**；
确认跑 **11367 passed / 5 skipped / 0 failed、222.87s、rc=0**
（collected **11372**）；`make gates` 全链 **rc=0**（墙钟 230s；链内
pytest 11367 passed / 5 skipped / 0 failed、222.38s、49 warnings）。
**未提交**（随收口提交一并入库）。

---

## 1. 两个判绿点

MDO 的判据链里 `rc==0` 出现两次，语义不同，缺陷相同：

1. **基线**（`compute_mdo` 前置）：测试套件必须在基准实现上全绿，否则
   MDR 不成立。改前只检查 `_is_execution_error` 与 `rc == 0`；全 skip
   基线既不是执行错误（pytest rc=0），也不是"红"，于是直接进入探针与
   变异体循环。每个变异体上套件同样全 skip → 全部 `rc==0` →
   `outcome.ran=True`、无 `assertion_failed` → **`measured` 且 MDR=0**。
   这是把"没跑断言"记成"测了 0 个判别"。
2. **变异体**（循环内）：改前 `rc==0 ⇒ ran=True`，该变异体留在 MTR/MDR
   分母。若测试对某个变异体条件化 skip，skip 会被当成"未判别"，以
   **无证据**压低 MDR；skip 既不是判别也不是崩溃，不应进入分母。

两处的判据与 BA / BB / BC 完全一致：**至少 1 个真实 `passed` 且 0 个
`failed`**；部分 skip 与真实 passed 并存仍算有效通过；摘要不可解析
（空输出 / 自定义运行器）不算有效通过（fail-closed）。

## 2. 逐点处置

| # | 位置 | 改前 | 改后 |
|---|---|---|---|
| 1 | `compute_mdo` 基线 | `rc==0` 且非执行错误 ⇒ 继续度量 | 再要求 `suite_has_effective_pass(base_out)`；否则 `not_measurable`，reason=`test_not_green_on_base(no_effective_pass)`，**在探针/变异体执行前短路** |
| 2 | 变异体 rc==0 | `ran=True`，留在分母 | 有效通过 ⇒ `ran=True`；否则 `no_effective_pass=True`、`ran=False`、不记 `crashed` |
| 3 | MTR/MDR 分母 | 排除 non_terminating / probe_invalid | 再排除 `no_effective_pass` |
| 4 | 全部变异体无有效通过 | — | `not_measurable`，reason=`mutant_runs_no_effective_pass`（不输出伪零值 MDR） |
| 5 | `MDOResult.as_dict` | `mdo_evaluable` 只排除两类 | 新增 `mdo_no_effective_pass` 计数；`mdo_evaluable` 同步排除第三类 |
| 6 | 谓词单一事实源 | `_m1_metrics` 内私有实现 | 上移 `src/utils/pytest_output.py`；`_m1_metrics` 保留 `_suite_has_effective_pass = suite_has_effective_pass`（同一对象，既有消费点与回归锁零改动） |

行为不变面（逐位保持）：

- 干净基线（真实 passed）⇒ 照常度量；
- **部分 skip + 真实 passed** ⇒ 仍算有效通过（基线、变异体两侧）；
- `rc==1` 断言失败仍记判别；纯运行异常仍记 `crashed`（F12 不变）；
- 收集/语法错误、无测试、信号终止仍先判 `_is_execution_error`
  （`rc=5` 的 module-level skip 走 `baseline_execution_error`，本轮不动）；
- 池规模、池下限、`provisional_pool` 出口拦截、`mdo_raw` 审计字段不变；
  `pool_size` 仍按全池 n 计，排除只作用于 MTR/MDR 分母。

## 3. 真语料测量（只读静态扫描）

对 `experiments/results/**/*.json` 逐行扫描含 `mdo_available` 键的任务行：

| 口径 | 实测 |
|---|---|
| 含 MDO 的任务行 | **4044** |
| `mdo_available is True` | **624** |
| available 行中 flat `mdr > 0` | **94** |
| available 行中 `mdo_raw.mdr > 0`（provisional 出口置 None 的行） | **530** |
| available 行中 MDR = 0 | **0** |
| `generated_test` 含 skip 标记的行 | **228** |
| 其中 available 且 MDR > 0 | **130** |
| 模块级 `allow_module_level=True` 全 skip 行 | **0** |
| available 行保存了基线 stdout / 摘要 | **0**（档案不存基线原文，无法重算） |

**静态适用面为零**：任何全 skip 基线的可用行都会得到 MDR=0（基线 skip
⇒ 变异体同样 skip ⇒ 无判别）；档案中 **624 条 available 行的 MDR 全部
为正**，不存在该形态。130 条含 skip 标记的 available 行 MDR 也全为正
⇒ **部分 skip 与真实通过并存**的口径边界得到语料支持。历史归档读数
**零影响**（不重跑、不回填、不改写任何工件）。

## 4. 回归锁

`tests/test_mdo_effective_green_bd.py`：**15 例**（零 LLM）。

| 类 | 例数 | 覆盖 |
|---|---|---|
| `TestSingleSource` | 2 | `_m1_metrics` 别名与 `mdo` 导入都指向共享谓词同一对象；源码锁 |
| `TestBaselineEffectivePass` | 10 | 7 个 rc==0 无有效通过参数（skip / xfail / xpass / deselect / no tests ran / pass+failed / 空）；执行错误优先级；部分 skip+pass 仍度量；**真实 pytest 运行期 skip** 端到端 |
| `TestMutantEffectivePass` | 3 | 全 skip 变异体 ⇒ 不可测且不记 crash；部分 skip+pass 仍入分母；混合池排除 1 个并在 `as_dict` 披露 |

既有 `tests/test_mdo_20261019_branches.py` 的 `_GREEN` 替身同步补上
`"1 passed in 0.01s"` 摘要行（用例数不变）；`tests/test_review_20261019_measurement.py`
的替身原本就返回 `"1 passed"`，无需改写。

## 5. 变异验证

6 个真实锚点 + 1 个中性对照；逐锚点：读取原字节 → 写入变异 →
`compile()` → 收集数核对 → 跑受影响面 → sha256 校验后按原字节还原
（绝不用 `git checkout` / `git stash`；脚本
`scripts/tools/bd_mutation_verify.py`，带名字过滤参数）。基线干净副本
**15 passed**；每个变异体运行后源文件 sha256 与原字节一致（脚本内 assert）。

| 锚点 | 变异 | 红数 |
|---|---|---|
| M1-baseline-effective-pass-guard-off | 基线守卫改 `if False:` | **8** |
| M2-shared-predicate-ignores-failed | 共享谓词去掉 `failed==0` | **2** |
| M3-shared-predicate-always-true | 共享谓词恒真 | **24** |
| M4-shared-predicate-ignores-passed | 共享谓词去掉 `passed>0` | **21** |
| M5-mutant-effective-pass-guard-off | 变异体守卫改回 `ran=True` | **2** |
| M6-denominator-keeps-no-effective-pass | 分母保留 `no_effective_pass` | **1** |
| M7-control-comment-wording | 仅改注释用词（行为不变） | **0（SURVIVED）** |

## 6. 踩坑与自纠

1. **真实 pytest 的 module-level skip 是 rc=5，不是 rc=0**：最初端到端锁
   用 `pytest.skip(..., allow_module_level=True)`，实测
   `TestRunResult(rc=5, output="1 skipped")`——没有测试被收集，已被既有
   `_is_execution_error` 收口，无法证明新守卫。改为**运行期 skip**
   （测试函数内 `pytest.skip`，rc=0）后锁才真正覆盖缺陷路径。
2. **`_GREEN` 替身是空输出**：新守卫上线后，既有分支测试的基线替身
   `TestRunResult(0, "")` 会被判"无有效通过"。它不是生产代码缺陷，而是
   替身不保真；补上真实摘要行后 21 例分支测试逐位保持。
3. **守卫顺序**：有效通过检查放在"非 0 rc"之后、探针之前。若放在
   `_is_execution_error` 之前，`rc=5` 的 module-level skip 会被改判为
   `no_effective_pass`，与既有执行错误口径冲突；若放在探针之后，会先
   浪费一次子进程。二者都由测试锁定。

## 7. 边界（不得引用为「MDO 所有执行判定均已收口」）

1. **只改 `src/measurement/mdo.py` 的两个 rc==0 点**：`_is_execution_error`
   的收集/语法/信号判据、F12 的 rc==1 分类、F13 的探针有效性均沿用原口径；
   本轮不重估它们的覆盖与语义。
2. **生产路径的裸 rc==0 仍未收口**：`detection_gates._run_test_against_code`
   的 `green`、`executor_runtime` / `executor_modes` / `executor` 的 `passed`、
   `testless_validation` 两处（BC §7 已登记，BD 未选取）。本轮只回答 MDO，
   不得引用为全仓已闭合。
3. **skip 不是 crash**：变异体全 skip 记 `no_effective_pass`，不记
   `crashed`；CRASH 率分母仍是全池 n，不因排除而改变。
4. **分母排除会提高 MDR 的点估计**：被排除的是"无断言执行证据"的
   变异体；池下限仍按全池 n 判定，不把排除后的样本量当作有效池规模。
5. **历史归档零回填**：§3 实测静态适用面为零；不重跑 LLM 批次、不改写
   任何归档 JSON / SHA256SUMS。
6. **摘要解析的既有边界**：`suite_has_effective_pass` 只认标准 pytest
   摘要片段；自定义运行器 / 非标准输出一律判 False（fail-closed）。这是
   BA 已登记的口径，本轮不改。

## 8. 复算命令

```bash
# 目标锁（15 collected）
.venv/bin/python -m pytest tests/test_mdo_effective_green_bd.py -q

# 受影响面（MDO 分支/契约 + BA/BB/BC 消费点）
.venv/bin/python -m pytest tests/test_mdo_effective_green_bd.py \
  tests/test_mdo_20261019_branches.py tests/test_mdo_metrics.py \
  tests/test_review_20261019_measurement.py tests/test_misguided_metrics.py \
  tests/test_misguided_replay_effective_green_bc.py \
  tests/test_effective_green_ba.py tests/test_effective_green_consumers_bb.py \
  tests/test_r5_mutation_detection.py tests/test_oracle_instrument_safety.py -q

# 变异验证（7 锚点；可传名字前缀过滤，如 M1 M6）
.venv/bin/python scripts/tools/bd_mutation_verify.py

# 全量 + 门禁（CI 同口径；不与 make gates 重叠）
make test
make gates
```
