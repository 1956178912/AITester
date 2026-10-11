# E7 · SWE-bench 数据链体检（零 LLM）—— 0/20 的**第二层**根因

> 2026-10-10 独立审查落地批次 · 全部零 LLM 成本 · 未修改任何缓存与仓库数据

## 0. 结论速览

审查报告 §C5/F7 已定案：2026-08-18 的 SWE-bench Lite 工件是"**失败分支行**"
（9–19 键、无 `detection_rate`、`instance_code` 长度为 0），故 0/20 **不是负结果**。

本次零 LLM 体检把根因**精确定位为三层独立缺陷**，并**更正本文件初稿的一处误判**：

| 层 | 缺陷 | 证据 | 影响 |
|---|---|---|---|
| **第 1 层** | **JSONL 里没有源码字段** → `instance_code` **兜底为 issue 文本** | 项目**自带**的 `python main.py check-dataset swe_bench` 直接报：**"缺失被测源码任务 225 个（instance_code 兜底为 issue 文本）"**，并逐一列出含 sqlfluff-4764 等全部 20 个待测实例 | 喂给系统的是 issue 描述而非代码 → `error_category=syntax`（19/20）→ **detection 从未被计算** |
| **第 2 层** | **仓库级 venv 环境不兼容** | 缓存 venv 为 `click 8.5.0`（已移除 `CliRunner(mix_stderr=…)`），sqlfluff `src/sqlfluff/utils/testing/cli.py:18` 仍在传该参数 → **gold 补丁正确应用后 F2P 仍 TypeError**（实测 rc=1） | **即使修好第 1 层，gold 测试仍跑不起来 → F2P 不可判定，detection 结构性为 0** |
| **第 3 层** | 修复路径存在但**未执行** | 同上 check-dataset 给出指引：`scripts/tools/export_swe_bench_source.py` 按 base_commit 导出 + `SWE_BENCH_ENRICHMENT` 环境变量加载 | 源码**可得但未物化**（仓库检出与 venv 其实都已存在） |

**⚠️ 本文件初稿的误判（已更正）**：初稿见 `load_dataset("swe_bench")` 返回 225 任务、
`instance_code` 长度 771 字符，据此写"数据链现状比 8 月好 ✅"。
**该判断错误**——771 字符是 **issue 摘要**，与 `problem_statement` 前 100 字符逐字相同
（已实测 `instance_code[:100] == problem_statement[:100]` 为 `True`）。
8 月那批的 `instance_code` 长度为 0，本次为"issue 文本"，**两者都不是源码**，
差别只在兜底策略，**不是改善**。

**结论**：SWE-bench 在**当前环境下完全不可评测**——三层缺陷**都发生在"判定之前"**，
**从未产生过任何 SWE-bench 检出/修复结果**。§C5 的"管道缺陷"定性正确，
但需从"输入物化失败"细化为**上述三层**。

## 1. 数据链现状（**表面可用，实为兜底**）

```
load_dataset("swe_bench")            → SWEBenchDataset，225 个任务 ✅
  task_id            = sqlfluff__sqlfluff-4764
  instance_code 长度 = 771 字符        ⚠️ **是 issue 摘要，不是源码**（与 problem_statement 逐字相同）
  test_code 长度     = 2781 字符        ✅
  metadata           = golden_patch(12125) / test_patch(2781) / fail_to_pass(2) ✅
  仓库检出            = ~/.cache/aitester/repo_envs/sqlfluff/a820c139ccbe/repo ✅ 存在
  venv                = .../a820c139ccbe/venv/bin/python ✅ 存在
```

实例缓存：`~/.cache/aitester/swe_bench/swe_bench_instances.jsonl` = **225 行**；
`swe_bench_pro` / `swe_bench_lite` / `swe_bench_mini` 均为 **0 行**。
`scripts/gates/check_swe_bench_pro_ready.py` → **exit 0 但报"数据未就绪"**
（Pro 数据集为空；注意该脚本**报未就绪却返回 0**，属"存在但不阻断"的门禁形态）。

## 2. 决定性验证（F2P 三段）

在 `sqlfluff__sqlfluff-4764` 上实测（副本上操作，不动缓存）：

| 步骤 | 结果 |
|---|---|
| ① F2P 在 base_commit（buggy）上执行 | rc=1，2 failed ✅ 符合预期 |
| ② `git apply golden_patch` | rc=0，3 个文件全部 cleanly applied ✅ |
| ③ **F2P 在 gold 上执行** | **rc=1，仍 2 failed ❌** |

失败原因（`--tb=long`）：

```
src/sqlfluff/utils/testing/cli.py:18
    runner = CliRunner(mix_stderr=mix_stderr)
E   TypeError: CliRunner.__init__() got an unexpected keyword argument 'mix_stderr'
```

**即：gold 补丁正确应用后，F2P 仍因环境不兼容而失败 → 该实例的
"检测/修复是否成功"在这一环境下**不可判定**。**

版本取证：

| 位置 | click 版本 | `mix_stderr` |
|---|---|---|
| 缓存 venv（`a820c139ccbe`） | **8.5.0** | ❌ 已移除（`click/testing.py:247` 注释明写 "has been removed"） |
| 仓库 `.venv`（本项目自测口径） | 8.4.2（lock 钉版） | ❌ 也已移除 |
| sqlfluff 检出（6/20 个） | — | 代码仍在传 `mix_stderr=` |

> 注：我的诊断脚本首次报 `AttributeError: click.testing` 是**我自己的探针写法问题**
> （`click.__version__` 弃用路径），非环境缺陷；已用 `pip show` + 直读文件复核，
> 缓存 venv 的 click 8.5.0 是**真实 pip 安装**（有 `click-8.5.0.dist-info`）。

## 3. 附带发现的真实打包缺陷（建议 I-31）

| 项 | 值 |
|---|---|
| `pyproject.toml:41` 声明 | `click>=8.0.0` —— **无上界** |
| `requirements.lock` 实测口径 | `click==8.4.2` |
| 最新版 | 8.5.0（**已移除 `CliRunner(mix_stderr=)`**） |

**风险**：`pip install aitester`（不带 lock）会拉最新 click。
本项目自测只用 `CliRunner()` 无 `mix_stderr`，**暂不受影响**；
但**被测仓库**（sqlfluff 等）大量使用 `mix_stderr`——
这正是第 2 层根因，且是"测试生成工具"这一类工具的通病：
**它的依赖解析策略直接决定它能否评测老仓库。**

## 4. 结论与建议

1. **C5/F7 的因果表述更正**：SWE-bench 0/20 = **输入物化失败（第 1 层）**
   **叠加 环境不兼容（第 2 层）**；两次失败都发生在"判定之前"，
   **从未产生过任何 SWE-bench 检出/修复结果**。
2. **修复顺序**（缺一不可）：
   a. 修第 1 层：确认 loader 在跑批路径上确实注入 `instance_code`（8 月为 0，
      当前直接加载已非 0，需在 `run_benchmark` 路径上复验）；
   b. 修第 2 层：**仓库 venv 必须按各 repo 的锁定依赖重建**（或对
      `pyproject`/`setup.py` 约束做 `pip install -e ".[test]"`），
      而不是直接 `python -m venv` + 装最新依赖；
   c. 加**前置门禁**：跑批前先验证"gold 补丁能让 F2P 转绿"（零 LLM，本文件 §2 的
      三步即可自动化）。**gold 不过 → 拒绝把该实例计入任何指标**（fail-closed）。
3. **新增建议 I-31（P1）**：`pyproject.toml` 的 `click>=8.0.0` 补上界
   （`click>=8.0,<9`）并在 `docs/dependency_exemptions.md` 登记；
   同时把"被测仓库 venv 构建策略"写成 `docs/design/` 设计文档
   （当前 `repo_envs` 的构建方式不可复现且已知会产生不兼容环境）。
4. **不要**在任何对外材料中引用 SWE-bench 的 0/20：它既不是负结果，
   也不是有效评测——**是两次发生在判定之前的失败**。

---

## 5. 修复与复测（2026-10-10 追加，零 LLM）

### 5.1 🔴 新发现并已修复的真实缺陷：导出脚本字段名不匹配

`scripts/tools/export_swe_bench_source.py:193` 读的是 `data.get("repository")`，
而**官方 SWE-bench JSONL 的字段名是 `repo`**（实测 jsonl 键：
`FAIL_TO_PASS / PASS_TO_PASS / base_commit / created_at / environment_setup_commit /
hints_text / instance_id / patch / problem_statement / repo / test_patch / version`）。

**后果链**：`repository` 恒取到 `""` → `resolve_repo_dir("")` 回退到 **cwd** →
`git show` 在**当前工作目录**执行 → 全部实例报
`fatal: not a git repository` → **本脚本从未成功导出过任何源码**
（实测修复前 **225/225 失败、产物 0 行**）。

这与 `instance_code` 兜底为 issue 文本是**同一类字段不匹配缺陷**——
即 E7 §0 第 1 层与第 3 层**根因相同**（脚本与加载器各读各的字段名）。

**修复**：改为 `data.get("repo") or data.get("repository") or ""`（双键兼容）。

### 5.2 修复后复测结果

| 项 | 修复前 | 修复后 |
|---|---|---|
| 导出成功数 | **0 / 225** | **48 / 225** ✅ |
| 失败原因 | 全部 `not a git repository`（cwd 误用） | 177 条 = **5 个未克隆仓库**（pydicom 56 / pvlib 63 / astroid 31 / pyvista 16 / marshmallow 9） |
| `check-dataset`（带 `SWE_BENCH_ENRICHMENT`） | 225 条全部"兜底为 issue 文本" | **48 条 ✓ 加载质量健康**（`instance_code` 达 43973 字符，真源码） |

覆盖面对账：缓存数据集含 **6 个仓库**（sqlfluff 50 / pvlib 63 / pydicom 56 / astroid 31 /
pyvista 16 / marshmallow 9 = 225）；本地 `repo_envs/` **只检出 sqlfluff**，
其 20 个 commit 支撑了 48 条可导出实例。**其余 177 条要克隆对应仓库才能导出**
（`git clone` 需网络）。

### 5.3 第 2 层（venv）复测

把缓存 venv 的 click 从 8.5.0 **降到 8.4.2**（与本项目 `requirements.lock` 同口径）后，
**`TypeError: CliRunner(mix_stderr=…)` 消失** —— 第 2 层的修法确认有效且成本极低
（一条 `pip install "click==8.4.2"`）。

### 5.4 第 4 层（本次新暴露）：参数化测试 ID 的转义/截断

继续复测时 F2P 报 `rc=4 (no tests ran)`，而**检出 HEAD 与 base_commit 逐位一致**
（`447ecf862a4d` = `447ecf862a4d2b977d0add9f444655357b9c4f1f`）、目标测试文件存在。
根因指向 F2P 列表中的**参数化 ID 含特殊字符**：

```
test/core/templaters/jinja_test.py::test__templater_jinja_slice_file[{%   ← 明显被截断
```

真实 ID 应形如 `…[{%-if x-%}…]` 这类含 `{`/`%`/`-`/`}` 的参数化形式。
**该层的修法属于 SWE-bench harness 实现细节**（需按 JSON 原始值传递、
避免 shell/日志层做 `%` 插值或截断），本轮未继续追。

### 5.5 结论：SWE-bench 从"完全不可评测"变为"**部分可评测**"

| 层 | 状态 |
|---|---|
| 1 源码物化 | ✅ **已修复**（导出脚本字段名），48/225 可用 |
| 2 venv 兼容 | ✅ **已验证修法**（click 降级） |
| 3 导出未执行 | ✅ **已执行**（48 条 enrichment） |
| 4 参数化 F2P ID | ⚠️ **新暴露，未修**（rc=4） |
| 5 仓库覆盖 | ⚠️ 177/225 需克隆 5 个仓库（需网络） |

**故对外仍不得引用 SWE-bench 的任何数字**；但修复路径已从"不明"变为
"**4 步、其中 2 步已验证**"。

---

## 6. 第 4 层（参数化 F2P ID）—— 根因定量 + 已实施修法

### 6.1 根因：**上游数据集自身**含被截断的节点 ID（不是本项目引入）

实测（`swe_bench_instances.jsonl` 全部 225 条）：

| 项 | 值 |
|---|---|
| 测试节点 ID 总数 | **24,122** |
| 参数化但**未闭合 `]`**（截断） | **530（2.20%）** |
| 分布 | sqlfluff 279 / pydicom 173 / marshmallow 41 / astroid 37 |

样例（注意 `[` 后内容缺失）：
```
test/cli/commands_test.py::test__cli__command_fix_stdin[select      ← 应为 [select=…]
test/cli/commands_test.py::test__cli__fix_loop_limit_behavior[--    ← 应为 [--rules=…]
test/core/templaters/jinja_test.py::test__templater_jinja_slice_file[{%
```
两处取证：① 原始 JSONL 内该字符串**已被截断**（非本项目测试命令所致）；
② 本项目下载脚本 `scripts/tools/download_swe_bench.py:36` 仅做
`json.dumps(item)` 直通，无任何截断/格式化逻辑。
**故成因在上游 `princeton-nlp/SWE-bench`，本项目不可修。**

### 6.2 危害（已实测复现）：**一个坏 ID 毒化整个 pytest 调用**

在同一检出（`447ecf862a4d`，与实际 base_commit 逐位一致）上对照：

| 调用 | rc | 结果 |
|---|---|---|
| 只给**合法** ID | **1** | `1 failed` —— 正常断言失败（有效 F2P 信号） |
| 合法 ID + **1 个截断 ID** | **4** | `no tests ran` —— **连合法 ID 都没跑** |

pytest 对无法匹配的节点报 `ERROR: not found: <id>` 并**中止整个调用**。
另实测 `--continue-on-collection-errors` **不能**修复该行为（仍 rc=4），
故必须**从入参侧剔除**坏 ID。

### 6.3 好消息：fail-closed 防线本就成立（无假信号）

`experiments/_m1_metrics.py:66-84` 的 `_looks_like_test_execution_error`
以 **`rc >= 2`** 为"测试没跑起来"，rc=4 满足该判据 → 该任务记为
**detection=0.0（保守）而非假检出**。即**已发生的测量是安全的**，
问题在"该任务被静默当成可判定"。

### 6.4 已实施修法（`src/datasets/dataset_loader.py`）

新增 `_drop_malformed_test_ids()`：含 `[` 但**未以 `]` 收尾** → 判为截断并剔除；
**绝不猜测补全**（宁缺毋滥）。同时修掉一处**净化白做**的缺陷：
`metadata` 里原先是 `self._parse_swe_test_list(data.get("FAIL_TO_PASS",""))`
**重新解析原始值**，使新加的净化被绕过 —— 现改用净化后的列表。

并新增可观测字段 `fail_to_pass_malformed_ids` / `pass_to_pass_malformed_ids`，
非空即表示该任务 F2P/P2P 面**不完整**（下游可据此知晓覆盖率折损，而非静默按完整处理）。

**效果（实测）**：剔除 **530 个坏 ID**，影响 **82/225 个任务**；
`sqlfluff__sqlfluff-2862` 净化为 `['test/api/simple_test.py::test__api__lint_string']`
（保留合法 ID）+ 2 个坏 ID 留痕。**回归锁 4 例**（含"闭合 ID 不得误杀"与
"不得猜补全"）。

### 6.5 第 2 层（venv）复测：比初判更深

复测时又暴露两点（均为**环境层**，非本项目代码缺陷）：

| 问题 | 证据 |
|---|---|
| 缓存 venv **缺框架依赖** | 该 repo 的 `tests/conftest.py:17` 导入 `src.agents.llm_client` → `langchain_openai`，而 sqlfluff 缓存 venv **未装** → conftest ImportError |
| pytest 与仓库年代不匹配 | venv 内 pytest **9.1.1**，而 sqlfluff 检出为 **0.11.0**（2023 年） |

> 说明：把 click 从 8.5.0 降到 8.4.2 确实消除了 `CliRunner(mix_stderr=)`
> 的 TypeError（修法有效）；但随后暴露出上述更底层的问题。
> 复核确认**该降级只作用于 `a820c139ccbe` 那一个 venv**，其余 venv 仍为 8.5.0
> —— **未波及其它实例**。

**结论**：第 2 层的正确修法不是"降级 click"，而是**按各 repo 自己的
测试依赖重装环境**；这正对应 I-31 的 ②。

### 6.6 更新后的缺陷栈状态

| 层 | 状态 |
|---|---|
| 1 JSONL 无源码字段 → issue 文本兜底 | ✅ 已修（`repo` 字段名），48/225 可导出 |
| 2 仓库 venv 环境 | ⚠️ **比初判更深**：缺框架依赖 + pytest 版本不匹配；click 降级只是表层修法 |
| 3 导出未执行 | ✅ 已执行（48 条 enrichment） |
| 4 参数化 F2P ID 截断（上游） | ✅ **已修**（剔除 530 个坏 ID + 留痕 + 4 例回归锁） |
| 5 仓库覆盖 | ⚠️ 177/225 需克隆另外 5 个仓库（需网络） |

**对外口径不变**：在层 2 与层 5 解决前，SWE-bench 仍**不得引用任何数字**。
