# T2 Python 工程化专项诊断（独立审计）

- **审计对象**：`/Users/wangchenyu/Workspace/AITester`（HEAD `d9e51df`，工作树干净——除本轮审查产物 `review_2026/` 外 `git status --porcelain` 为空）
- **环境**：`.venv` / Python 3.14.6（`v3.14.6 (c63aec69bd8, Jun 10 2026)`）/ mypy 1.15.0 / ruff 0.16.3 / bandit 1.9.4 / pytest 9.1.1 + xdist
- **方法**：只读命令 + AST 静态扫描 + 仓库内已入库工件的独立复算；**未修改任何仓库源文件**，未运行任何 formatter/自动修复；临时产物只落 `/tmp`（`/tmp/t2pytest` 已在跑批后清理），报告只写本文件
- **可复现命令**：本文所有结论均附 `文件:行` 或命令原文，`§附录` 汇总关键命令

**结论速览**

| # | 结论 | 严重度 | 一句话证据 |
|---|------|--------|-----------|
| P0-1 | RT1 控制臂（"+43pp 归因提示协议"的唯一证据）的**定义开关未入工件**，与它自己判为"不作结论依据"的 `over_red_section_firstrun_NOTVERIFIABLE` 属同一审计缺陷 | **P0** | `rt1_no_reinforcement_seed42/benchmark_synthetic_20261009_193509.json` 的 `provenance.env_snapshot` 只有 38 键、无 `DETECTION_FIRST_SECTION_ENABLE`；`rt1.log` 中该串出现 **0** 次；该开关由 `src/graph/nodes.py:490-495` 定义，且当前 `_env_snapshot_keys` 仍未收录（`experiments/run_benchmark.py:2712-2770`） |
| P0-2 | D2（缓存命中不计 token）只做了"侧信道记账"，**`total_tokens` 与预算口径仍不覆盖缓存命中**；已入库的 10 个 main_batch 工件**全部 `cache_enabled=true`**，其 token/成本/预算结论不可与冷缓存结论互换，且工件层无任何校验门禁 | **P0** | `src/budget/token_usage.py:129-148`（明确"不写入 record_usage"）；`src/budget/cost_budget.py:141/154` + `src/agents/llm_client.py:331`（预算只累加真实调用）；10/10 main_batch `provenance.cache_enabled=true`；e6_control 两臂 `tok_rows=0/87` |
| P0-3 | 自述挂死/孤儿进程根因**只修了 1 个文件**：其余 **9 文件 12 处 `subprocess.run`** 仍是"只 kill 直接子进程"的旧语义（无 `start_new_session`/`killpg`），而该缺陷已实际造成 30+ 分钟挂死与 2 个 ppid=1、~100% CPU 空转 56–63 分钟的孤儿进程 | **P0** | `grep -rn run_with_timeout` 只有 `src/tools/branch_coverage_inject.py:42,168`；`src/utils/process_utils.py:57`；12 处清单见 §6.2；`BASELINE.yaml:270-281,479-485` |
| P1-1 | 单一事实来源 `BASELINE.yaml` 的头号数字已过期：**声明 5015 / 35s，实测 5178 收集 / 5175 passed+3 skipped / 54.08s**（同一条命令、同一 venv） | P1 | `BASELINE.yaml:16-25`；`.venv/bin/python -m pytest --collect-only -q` → `5178 tests collected`；全量跑批 → `5175 passed, 3 skipped, 8 warnings in 54.08s` |
| P1-2 | "开关必须入 provenance"这一 D3 修复**未系统化**：`*_ENABLE` 共 55 个，`_env_snapshot_keys` 只收 39 键、**37 个缺席**（含 `SEMANTIC_CACHE_ENABLE`/`SPEC_IR_DSL_ENABLE`/`SPEC_ORACLE_EXEC_ENABLE`/`RUNTIME_PROBE_ENABLE` 等实验杠杆） | P1 | AST/正则复算：`os.getenv("*_ENABLE")`=55 vs `_env_snapshot_keys`=39；`BASELINE.yaml:456-460` 自己也承认门禁"未实施" |
| P1-3 | 覆盖率/门禁口径漂移：`check_branch_coverage.py` 文档字符串写"总门槛 85%"，代码是 **0.77**；`BASELINE` 的 mypy 源文件数 119 与实际 120 不符 | P1 | `scripts/gates/check_branch_coverage.py:8-9` vs `:57` `_TOTAL_THRESHOLD = 0.77`；`.venv/bin/python -m mypy src/ config.py` → `Success: no issues found in 120 source files` |
| P1-4 | `make gates`（自述"本地全部门禁"）是 CI 的真子集，缺 format/branch/ratchet/zero-assert/artifacts/credential-scrub/audit-log/依赖豁免/llm_configs 共 9 类门禁 → 本地全绿仍可能 CI 红 | P1 | `Makefile:49` vs `.github/workflows/ci.yml:305,364,379,246,236,331,323,554,209` |
| P1-5 | 权威工件 MANIFEST 未覆盖当前主结论证据：`check_artifacts_tracked.py` 只登记 21 条（全是 main_batch/R4/文档），**E6 phase1/phase2、RT1、A1 strip、D1 批次 JSON 均不在册**（虽已入库，但被删除时门禁不响） | P1 | `scripts/gates/check_artifacts_tracked.py:39-68`；`git ls-files experiments/results/e6_a1_batches \| wc -l` = 1089 |
| P1-6 | 对外数字与内部日志口径冲突：同一臂 BASELINE 记 `2/87 (2.3%)`，跑批日志记 `可测 11/87 → 18.2%`；且 `interpretation` 下的结论（"低预算下 aitester 更差…源于编排结构"）被其自己的 primary endpoint 判为"检验力不足**不作判定**" | P1 | `BASELINE.yaml:590-602` vs `e6_phase2_matched_coldcache/phase2.log:1150` |
| P1-7 | `Dockerfile.repro` 装 `requirements.txt`（23 顶层钉，传递依赖浮动），CI 装 `requirements.lock`（132 钉）→ "复现容器"与"CI 环境"不是同一环境，与其注释"锁定版本"不符 | P1 | `Dockerfile.repro:36` vs `ci.yml:141` |
| P1-8 | `test_visible_to_system`（APR 严谨性检查点 #2）是**硬编码常量 True**，不是测量值；读者会误当逐行观测 | P1 | `experiments/run_benchmark.py:1097`、`:1244` 两处字面量 `True` |
| P2 | mypy 配置为零严格选项（`[tool.mypy]` 空表）；`--warn-unused-ignores` 多出 8 错、`--warn-return-any` 多出 24 错 | P2 | `pyproject.toml:227-229`；§3.3 四条命令输出 |
| P2 | 无任何复杂度门禁（C901 被删、PLR09xx 全 ignore）；实测 30 个函数 >120 行（最大 675 行）、15 个文件 >800 行（最大 2532 行） | P2 | `pyproject.toml:140,149,173-177`；§3.2 |
| P2 | 软门禁清单：SBOM 作业 info-only、perf 回归默认非阻断、gitleaks 全历史非阻断、引用核验 `continue-on-error: true`、docs-history 漂移**永不失败**（131 条告警 exit 0）、smoke-llm 默认短路 | P2 | `.github/workflows/ci.yml:529,542,560,592`；`perf.yml`；`scripts/gates/check_docs_history_drift.py:123-125` |
| P2 | `pip-audit` 证据不在仓内（`pip_audit_lock.json` 仅 CI artifact），本地无法离线复核漏洞结论；豁免仅 4 条有登记 | P2 | `check_dependency_exemptions.py` rc=0（4 条）；`git ls-files \| grep pip_audit` 空 |
| P3 | 顶层 `config` 模块随 wheel 装进 site-packages（通用名冲突面）；`single_agent` 臂在存量工件里覆盖率 4.8%（n=50）未见登记 | P3 | wheel top-level = `{src, config.py, dist-info}`；`benchmark_synthetic_20261001_121523.json` |

> 说明：本项目自述里明确承认的 4 起测量伪影（D1/D2/D3 + 挂死）本文**不重复计入发现**，但会核对其修复是否真正闭环（结果：D2 仅止血未闭环、D3 仅个案未系统化、挂死仅修 1/10 文件）。

---

## 1. 项目结构与包管理

### 1.1 现状（已核验为健康）

```text
$ find src -name "*.py" | wc -l          → 119
$ find src -name "*.py" -exec cat {} + | wc -l → 45371
$ ls src/__init__.py                      → 存在（__version__ = 0.7）
$ cat main.py                             → 465 字节薄入口 → src/cli/app.py:cli
$ pyproject [project.scripts] aitester = "src.cli.app:cli"
```

**可安装性实测**（未污染仓库：把 `src/ config.py pyproject.toml setup.py README.md LICENSE` 复制到 `/tmp/t2pkg` 后构建）：

```text
$ python -m pip wheel . -w dist --no-deps --no-build-isolation
aitester-0.7-py3-none-any.whl   items=127
top-level entries: ['aitester-0.7.dist-info', 'config.py', 'src']
config.py present: True   py.typed present: True
LICENSE entries: ['aitester-0.7.dist-info/licenses/LICENSE']
Metadata-Version: 2.4 / License-Expression: MIT / Requires-Python: >=3.12
entry_points.txt: [console_scripts] aitester = src.cli.app:cli
Requires-Dist × 22（含 [rag]/[viz]/[experiments]/[ux]/[dev]/[formal]/[db] extras）
```

结论：PEP 621 + `dynamic version {attr="src.__version__"}` + PEP 639 SPDX 全链有效；`AS` 批声称的"wheel 114 项"现为 127 项（工件数随文件增长，非缺陷，但**该数字无任何门禁锁定**）。

### 1.2 问题

1. **P3｜顶层 `config` 模块注入 site-packages**：`setup.py:36` `py_modules=["config"]` 使一个通用名模块进入全局命名空间；同环境其它包含 `config.py` 的发行包会发生遮蔽。这是"src/ 内 6 个模块 `from config import ...`"的历史包袱，短期可接受，但应在 `MODEL_CARD`/`README` 安装章节显式声明该副作用。
2. **P2｜延迟导入是常态而非例外**：函数体内 `from src. …` 共 **204** 处，`PLC0415` 全局 ignore（`pyproject.toml:149` ignore 列表）。这说明循环依赖压力被"用延迟 import 绕开"而非结构解决；同时 `src/graph/token_usage.py`、`src/graph/cost_budget.py` 两个 36 行兼容 shim 仍在（`experiments/run_benchmark.py:82` 走的是 shim 路径）。
   - 我核对了 shim 的安全性：`src/graph/token_usage.py` 是 `from src.budget.token_usage import ...` 的对象转发（同一 `_thread_local`），**不存在"两个累加器"的隐患**——此项为阴性结论。
3. **P3｜`Makefile build-check` 未接 CI**（`Makefile:79` 自述"未接 CI"）；且本地 `python -m build --wheel` 在无 `wheel` 包时直接 `ERROR Missing dependencies: wheel`（本轮实测），说明该目标只在联网隔离构建下可用。

### 1.3 修复

```bash
# 1) 在 CI 增加一条"wheel 内容物断言"（防 config.py/py.typed 丢失）
python -m build --wheel && python -m zipfile -l dist/*.whl | grep -E 'config.py|py.typed'
# 2) Makefile lint 目标改为与 CI 同解释器/同版本
lint: ; $(PY) -m ruff check . && $(PY) -m ruff format --check .
```

---

## 2. 环境与依赖

### 2.1 现状

| 项 | 实测 |
|---|---|
| 元数据 | PEP 621；`dynamic=["version"]`；`[build-system] requires=["setuptools>=77.0","wheel"]` |
| 三源一致性 | `check_lock_sync.py` → `rc=0`（23 项 vs 132 项，109 条"lock 独有"仅警告） |
| pyproject ↔ lock | 独立复算：**0 个缺失、0 个 specifier 被违反**（`packaging.Requirement` × lock 版本） |
| pyproject ↔ setup.py | `tests/test_packaging.py:137-192` 锁定 `install_requires` 与 extras 分组一致 |
| CI/工具版本 | `check_tool_versions.py` rc=0（ci.yml ↔ .pre-commit-config ↔ lock 三方比对） |
| bandit | 本地以 CI 同命令跑：`bandit -r src/ -c pyproject.toml -q` → exit 0，零输出 |

`requirements.txt` 23 项**全部**为 `==` 钉版（无 `>=` 漂移），lock 132 项。

### 2.2 问题

1. **P1｜两套"锁定"环境并存**：`ci.yml:141` 装 `requirements.lock`（132 钉），`Dockerfile.repro:36` 装 `requirements.txt`（23 钉 → 传递依赖随 PyPI 当日解析浮动）。`Dockerfile.repro:8` 的注释声称"把全量依赖 + 锁定版本固定进容器"，与实现不符。**复现容器 ≠ CI 环境 ≠ 用户环境**，任何"在 repro 容器里复现"的结论都无法与 CI/主批次对齐。
2. **P2｜开发工具链不在任何锁定源**：`pre-commit` 既不在 `requirements.txt` 也不在 `requirements.lock`（`grep -c '^pre-commit==' requirements.lock` → 0），而 `README.md:84` 要求 `pre-commit install`；`mypy` 不在 lock，由 `ci.yml:159` 显式 `pip install "mypy==1.15.0"` 兜住；`ruff` 在 lock 且 CI 再钉一次（冗余但安全）。→ 新贡献者按文档装不出一致的 hook 环境。
3. **P2｜`Makefile:18` 用 PATH 上的 `ruff`**（`lint: ruff check .`），而 `check_tool_versions.py:84-86` 只读 `ci.yml`/`.pre-commit-config.yaml`/`requirements.lock` **三个文件**，不校验 Makefile → 本地 ruff 版本漂移不会被任何门禁发现。
4. **P2｜漏洞审计证据不在仓内**：`pip_audit_lock.json` 未入库（`git ls-files | grep pip_audit` 为空），CI 仅作为 artifact 上传（`ci.yml:513`）；本地/离线无法复核"5 ignored"的漏洞结论。豁免登记只有 4 条且 `check_dependency_exemptions.py` rc=0。
5. **P2｜许可合规依赖人工**：`DATA_CARD.md §4` 登记 BugsInPy 无 SPDX、TestGenEval CC BY-NC-4.0 为非清洁许可——正确做法，但无自动化门禁（无法在 CI 校验数据集许可变更）。

### 2.3 修复

```bash
# 1) 统一 repro 环境到 lock（一行改动 + 一个断言测试）
#    Dockerfile.repro:36 → RUN pip install --no-cache-dir -r requirements.lock
# 2) 把 pre-commit 纳入锁定源
echo 'pre-commit==<pin>' >> requirements.txt && uv pip compile ... > requirements.lock
# 3) check_tool_versions.py 增加 Makefile 解析源（RUFF_BIN / PY 行）
# 4) pip-audit 结论入库（仓内 audit 摘要 JSON + SHA256），或至少在 CI 里把摘要写进 job summary
```

---

## 3. 代码质量

### 3.1 ruff（正向结论）

```text
$ python -m ruff check . --no-cache                    → All checks passed!   (exit 0)
$ python -m ruff format --check src tests experiments scripts config.py main.py init_db.py
  → 460 files already formatted                        (exit 0)
$ python -m ruff format --check $(git ls-files '*.md' | head -60)  → 60 files already formatted (exit 0)
```

选择集很宽（E/W/F/I/B/UP/SIM/PERF/RET/RUF/T20/A/S/C4/DTZ/G/ISC/PIE/PL/PLE/TRY/FURB/PGH，`pyproject.toml:113-148`），且 `PGH003`（blanket `type: ignore`）自 R3 起**不再**全局 ignore。

> 附带发现（对审查团队自身有效）：`ruff format --check .` 会格式化 **Markdown 里的 ```python 代码块**——本轮 `review_2026/T4_claims_audit.md` 即被判定"would be reformatted"。该文件未跟踪、CI 洁净检出不受影响，但**本团队任何入库的 .md 若含 ```python 片段都会把 CI format 门禁变红**。（本报告因此统一用 ```text/```bash 围栏。）

### 3.2 问题

1. **P2｜复杂度零门禁**：`pyproject.toml:140` 注释自述"移除 C90/C901 死配置"，`ignore` 列表同时忽略 `PLR0911/0912/0913/0915/0917`（`:173-177`）。AST 实测：
   - **函数 >120 行：30 个**，最长 `src/graph/debugger.py:206 _debugger_node` **675 行**、`src/agents/debugger.py:226 debug` 592 行、`src/graph/nodes.py:1440 _patch_applier_node` 516 行、`src/graph/nodes.py:524 _generator_node` 445 行；
   - **文件 >800 行：15 个**，最长 `src/datasets/synthetic_dataset.py` 2532、`src/graph/nodes.py` 2005、`src/tools/patch_applier.py` 1375、`src/agents/error_classifier.py` 1348、`src/agents/debugger.py` 1147、`src/agents/executor_repo.py` 1135。
   → 拆分批次做过（nodes.py 3593→1909），但**没有门禁防止回涨**：下一次新增 500 行函数不会有任何提示。
2. **P2｜mypy 配置是空表**：`pyproject.toml:227 [tool.mypy]` 之后直接是 `:229 [[tool.mypy.overrides]]`——没有任何 `strict`/`disallow_untyped_defs`/`warn_unused_ignores`/`warn_return_any`/`disallow_any_generics`。实测四档对比（`--cache-dir=/tmp/t2_mypy_cache --no-incremental`）：

   | 命令 | 结果 |
   |---|---|
   | `mypy src/ config.py`（CI 口径） | `Success: no issues found in 120 source files` |
   | `+ --check-untyped-defs` | `Success`（注解覆盖率高，见下） |
   | `+ --warn-unused-ignores` | **8 errors in 3 files**（`src/rag/retriever.py:237,261,558` 等死抑制） |
   | `+ --warn-return-any` | **24 errors in 13 files**（`src/graph/debugger.py:134` 等隐式 Any 泄漏） |

   **公允说明**：注解覆盖率高——AST 统计 1082 个函数中 **1076（99.4%）** 参数与返回值注解齐全，未注解的仅 6 个（`src/graph/workflow.py:902/913/922/929` 的 LangGraph 鸭子类型 shim、`src/graph/nodes.py:550`、`src/graph/debugger.py:229` 的回调）。所以"mypy 0 错误"不是空转，但**默认模式仍放过了 32 处可检出的问题**（8 死抑制 + 24 Any 返回）。
   - `# type: ignore` 共 43 处，**0 处 blanket**（全部带错误码）——S8b 收窄有效。
3. **P3｜自述计数漂移**：`pyproject.toml:166` 注释称 try-except-pass "3 处"/"14 处"，实测 `except: pass` **16 处**；`BASELINE.yaml:82` 称 mypy 119 源文件，实测 120。
4. **P3｜TODO/FIXME 密度极低**：`grep -rn "TODO\|FIXME\|XXX\|HACK" src/` = 9，其中 8 处是 `src/graph/expert_pool.py:428` 的**降权特征字符串**（`("TODO","FIXME","HACK")`），真实待办 ≈ 0。此项为阳性结论。
5. **P3｜异常处理**：`S110`（try-except-pass）全局 ignore，16 处均有注释说明"卫生性操作不阻断主流程"；`G201` 在 tests/experiments/scripts 放宽（日志格式）——口径自洽。

### 3.3 修复

```bash
# 1) 打开三个"零成本、零改造"的 mypy 开关（先修 32 处存量）
#    [tool.mypy] 下加：warn_unused_ignores = true / warn_return_any = true
# 2) 复杂度门禁：ruff select 增加 "C901" + [tool.ruff.lint.mccabe] max-complexity = 25
#    （只拦新增：对原 30 个超标函数用 per-file-ignores 白名单冻结，逐批偿还）
# 3) 文件长度门禁（自定义 gate，5 行脚本）：src/**.py > 2000 行即 fail
python - <<'EOF'
import pathlib,sys
bad=[(len(p.read_text().splitlines()),str(p)) for p in pathlib.Path('src').rglob('*.py') if len(p.read_text().splitlines())>2000]
print(bad); sys.exit(1 if bad else 0)
EOF
```

---

## 4. 测试与验证

### 4.1 现状（实跑取证）

```text
$ .venv/bin/python -m pytest --collect-only -q -p no:cacheprovider --basetemp=/tmp/t2pytest
  → 5178 tests collected in 1.31s

$ .venv/bin/python -m pytest tests/ -q -p no:cacheprovider --basetemp=/tmp/t2pytest -n 4 --dist loadfile
  → 5175 passed, 3 skipped, 8 warnings in 54.08s        (real 0m55.176s)

$ git status --porcelain -uall   # 跑批前后 diff
  → 无新增文件（除队友正在写的 review_2026/T4_claims_audit.md）
```

- tests/：**253** 个 `test_*.py`（共 255 个 .py），**66880** 行 —— 与任务书给的 257/66880 在行数上一致（文件数口径差异来自 `conftest.py`/`__init__.py` 是否计入）。
- 断言密度（独立 AST 复算）：**8906 条 assert / 4996 个 test 函数 = 1.78**；`assert True` 仅 1 条；`x is not None` 类弱断言 168 条（1.9%）；mock 交互型断言 96 条（1.1%）。**"零断言/空心化"在本仓不是系统性问题**（与预设假设相反，属阴性结论）。
- 零断言门禁真实存在且生效：`scripts/gates/check_zero_assert_tests.py` → `扫描 253 个测试文件：零断言用例 0 个（豁免 0，违规 0）`；其豁免表 `EXEMPT`（`:41-44`）已清空。
- 测试隔离：`tests/conftest.py`（70 行）两个 autouse fixture——`:22 _isolate_agent_instance_caches`、`:40 _isolate_llm_cache`（强制 `AITESTER_LLM_CACHE=0` + `tmp_path` 目录），实测跑批**不污染工作树**（见上）。
- marker：`slow/integration/unit` 三个已声明 + `--strict-markers`（`pyproject.toml:253-262`），使用 184 处；skip/skipif 9 处。
- 属性测试：**10** 个测试文件 import hypothesis（`tests/test_property_invariants.py`、`test_patch_applier_properties.py`、`test_spec_smt.py` 等）。

### 4.2 问题

1. **P1｜单一事实来源的数字已过期**：`BASELINE.yaml:16-20` `total_passed: 5015` / `suite_seconds: 35`（"实测 34.5s"）。本轮同命令实测 **5178 收集 / 5175 passed + 3 skipped / 54.08s**——用例数 +163（+3.2%）、耗时 +54%。`README.md:29-48` 已改为"不硬编码、指向 BASELINE"，方向正确，但**BASELINE 本身没人校准**：`check_baseline_numbers.py` 只输出"当前基线块零硬编码，统一指向 BASELINE.yaml"（exit 0），并不校验 BASELINE 的数字与实跑一致。
2. **P2｜覆盖率门禁的"口径文档—代码漂移"**：`scripts/gates/check_branch_coverage.py:8-9` 写"总门槛（hard gate）：全仓分支覆盖率 ≥ 总门槛（默认 85%）"，代码 `:57 _TOTAL_THRESHOLD = 0.77`（`:62 _TOTAL_LINE_THRESHOLD = 0.85` 是行覆盖）。同一文件内两套口径互串，读者极易把 77% 当成 85%。
   - 另一处细节：本地无 `coverage.xml` 时该脚本 exit 1（fail-closed，正确），但输出是"分支覆盖门槛未达标（1 处）"，而非"产物缺失"——诊断信息误导。
3. **P2｜6 个工件类门禁只在 3.14 矩阵腿跑**：`ci.yml:233/242/250/258/296/356` 的 `if: matrix.python-version == '3.14'` 覆盖 checksum/artifacts-tracked/zero-assert/env-budget/codecov/static-snapshot。矩阵一旦缩到单版本或 3.14 被临时禁用，这些门禁会静默消失（无 fail-closed 断言"必须有一个腿跑过"）。
4. **P3｜零断言门禁的判定下限偏低**：`_has_assertion_signal`（`:54-88`）只要命中任一 assert 即通过，无法识别"断言与行为无关"；且模块级扫描只看 `tree.body`（`：113-117`），`if TYPE_CHECKING:`/嵌套非 `Test*` 类内的 test 函数会漏扫。当前 253 文件全绿，风险是未来。
5. **P3｜覆盖率只有"总量"门禁**：行 85 / 分支 77 / ratchet 89.5+82.5 都是全仓聚合口径，无 diff-cover 类"新增代码覆盖率"门禁（脚本 `:60-61` 自述"增量门禁属后续 diff-cover 批次"）；低覆盖模块（type_repair/debugger）由高覆盖模块稀释。

### 4.3 修复

```bash
# 1) 让 BASELINE 数字可被机器校准（新增 gate，跑得快）
.venv/bin/python -m pytest --collect-only -q | tail -1   # 与 baseline tests.total_passed 比对
#    写进 scripts/gates/check_baseline_numbers.py：±0 容忍（收集数不受机器影响）
# 2) 修 docstring：check_branch_coverage.py:8-9 的 85% → 77%，并区分 line/branch
# 3) 增加"至少一个矩阵腿执行过工件门禁"的断言（用一个 sentinel 步骤写入 GITHUB_OUTPUT 后校验）
# 4) 引入 diff-cover（--fail-under=80）作为增量行覆盖门禁
```

---

## 5. 可复现性

### 5.1 现状

| 资产 | 状态 |
|---|---|
| `reproduce.sh` | 存在（15KB，`set -euo pipefail`，quick/full/dataset/profile 参数化） |
| `Dockerfile.repro` | 存在（python:3.14-slim，git sha 注入 `.repro_provenance`） |
| 种子 | `AITESTER_CACHE_NAMESPACE=seed<N>` 自动注入（`run_benchmark.py:2399-2402`，X1 修复） |
| 工件哈希 | `experiments/results/e6_a1_batches/SHA256SUMS`：**1088/1088 校验通过**（`checksum_results.py --verify`） |
| 工件入库 | 3426 个文件 / 88MB 已跟踪；`.gitignore:129-152` 用 negation 白名单放行 main_batch / r4_batches / e6_a1_batches |
| provenance | 29 个批次 JSON 带 provenance，`git_sha` 29/29 存在 |

### 5.2 问题

1. **P1｜83% 的工件跑自脏工作树**：`git_dirty: True` **24/29**（False 仅 5）。`experiments/results/main_batch` 的 **10/10** 全部 `git_dirty=true`——即 README/target_quality/repair 结论所依赖的主批次**无法绑定到任何 commit**。`statistical_report_3seed_pooled.md:139-140` 自己也做过勘误（"provenance git_dirty=False 表述与工件不符"），但**只修了文字，没改协议**（无"跑批前后 git status 必须干净"的硬门禁；`--allow-dirty` 仍是常规路径）。
2. **P1｜cache 状态与脏树一样普遍**：`cache_enabled: True` **23/29**；main_batch 10/10 缓存开启。配合 D2（§6.1），这些工件的 token 数只是"真实 API 调用量"，不是"任务计算量"，跨臂/跨批次成本对比需要一个显式口径声明——目前只散落在个别报告行（`statistical_report_3seed_pooled.md:9`），**没有工件级字段或门禁**。
3. **P1｜MANIFEST 覆盖不全**：见总表 P1-5。当前主结论证据（E6 phase1 `…190234.json`、phase2 `…191716.json`、RT1 `…193509.json`、A1 strip `…180655.json`、D1 `…200343.json`）都不在 `MANIFEST`，删除/移动它们不会让 CI 变红。
4. **P2｜环境快照缺口 37/55 开关**：见总表 P1-2；这直接决定"这条结论是在哪个配置下跑出来的"能否被审计。样本：`provenance.env_snapshot` 实际只有 **38** 键（`rt1` 批次），而 `src/` 内 `os.getenv("*_ENABLE")` 有 **55** 个。
5. **P2｜`git_dirty` 之外的"代码版本"信息缺失**：无 `git stash`/diff 摘要入库；脏树跑批时无法知道差异内容（`provenance` 只有 bool + sha）。
6. **P3｜`python -m build` 不可离线执行**：本轮 `python -m build --no-isolation --outdir …` → `ERROR Missing dependencies: wheel`；`make build-check`（`Makefile:79`）依赖联网隔离构建。

### 5.3 修复

```bash
# 1) 跑批前置门禁（run_main_batch 入口，fail-closed）：git status 非空且未显式 --allow-dirty → 拒绝
#    并在 provenance 增加 git_diff_sha256（git diff | sha256sum）+ dirty 文件清单
# 2) provenance 增 "cost_caliber": {"cache_enabled":…, "token_semantics":"api_spend|work_equivalent"}
# 3) MANIFEST 扩充到"BASELINE 引用的全部证据工件"（当前 +5 条）
# 4) env_snapshot 的键集合改为**自动枚举**：扫描 config.py + src/**/flags.py 的 os.getenv("X_ENABLE")
#    并断言 ⊆ 快照键（这就是 BASELINE:456-460 承认"未实施"的那条门禁）
```

---

## 6. 性能与资源

### 6.1 D2 缓存记账：核查结论（对线索的独立复核）

**代码事实**（`src/agents/base_agent.py:284 _call_llm_with_cache`）：

| 路径 | 行 | 记账行为 | 结论 |
|---|---|---|---|
| LRU 快路径命中 | `:398-406` | `record_cache_hit(True)` + `record_cache_hit_usage(_lru_lookup_tokens(key))` | 已止血（侧信道） |
| 语义缓存命中 | `:420-431` | `return _sem_resp`——**既无 `record_cache_hit` 也无 `record_cache_hit_usage`** | **残留缺口**（默认关，`SEMANTIC_CACHE_ENABLE`） |
| 文件→LRU 命中 | `:450-458` | `record_cache_hit_usage(int(cached_data.get("tokens",0) or 0))` | 已止血（侧信道） |
| 真未命中 | `:470-543` | `_before_total = get_usage().total_tokens` → 差值 `_call_tokens` 写回缓存 | 主路径正确 |

**关键点：止血是"分离口径"，不是"补齐口径"**——`src/budget/token_usage.py:129-148` 的 docstring 明确：`cache_avoided_tokens` **不写入** `input/output/total/llm_calls`，"保持真实 API 消耗口径不变，避免破坏既有 $/task 结论"。因此：

1. `total_tokens` 依旧**不含**缓存命中省下的工作量（这是设计选择，不是 bug）；
2. 但**预算闸门也只认真实调用**：`src/agents/llm_client.py:331 → record_usage_and_check → src/budget/cost_budget.py:141/154`，缓存命中不经过任何 `check_budget`。→ **缓存开启时，cap 会晚于"等能量"时点触发**，`token_budget_capped` 语义随缓存命中率漂移。
3. 因此 E6 预算配对实验**必须冷缓存**——项目确实这样做了（`e6_phase1/phase2` 均 `cache_enabled=false`，`token_coverage 87/87`）。**这个分支是对的**。
4. **但被引用的旧工件没有重跑**：`e6_control_seed42`（`BASELINE.yaml` 头部结论"−28pp 第三次复现"的证据）`cache_enabled=true`，两臂 `tok_rows=0/87`（ainester 37/87），且 `cache_hits` 字段在旧 schema 中不存在（补算为 0）→ **读这个 JSON 无法知道缓存命中多少次、省了多少 token**。
5. **工件层无任何校验**：仓内 `grep cache_hits scripts/gates/*.py` 为空；只有 `tests/test_token_usage.py:149-174` 的单元测试。→ 冷缓存批次出现 `cache_hits>0`、或 token 行覆盖 <100% 时，**没有门禁会失败**。

**影响面清单**（针对"成本/预算配对实验是否都受影响"）：

| 实验/工件 | cache | token 覆盖 | 是否受影响 |
|---|---|---|---|
| `e6_control_seed42`（cited） | true | aitester 37/87；plain_llm 0/87；df 0/87 | **受影响（结论仍可用，但 token/成本不可引用）** |
| `a1_strip_seed42` | true | 71/87 | **受影响（同上）** |
| `e6_phase1/phase2_matched_coldcache` | false | 87/87 三臂 | 不受影响（正确做法） |
| `rt1_no_reinforcement_seed42` | false | 87/87 | 不受影响 |
| `d1_json_repair_seed42` | false | 87/87 | 不受影响 |
| `main_batch` ×10（target_quality/$ 口径来源） | **true ×10** | 4 个批次两臂 0/87 | **受影响（$ /token 效率结论不可跨臂比）** |
| `e4_quixbugs_*` | false | 50/50 | 不受影响 |

### 6.2 subprocess 挂死/孤儿进程：AST 全量清单（对线索的独立复核）

`src/utils/process_utils.py::run_with_timeout`（129 行，`start_new_session` + `killpg` + 有界收口）**只有 1 个消费点**：

```text
$ grep -rn "run_with_timeout" src/ | grep -v process_utils
src/tools/branch_coverage_inject.py:42:from src.utils.process_utils import run_with_timeout
src/tools/branch_coverage_inject.py:168:        proc = run_with_timeout(
```

**其余 9 文件 12 处 `subprocess.run`（AST 口径，全部带 `timeout=`，但无进程组终止）**：

| # | 位置 | 上下文 |
|---|---|---|
| 1 | `src/agents/executor_modes.py:467` | venv/sandbox 链路跑 pytest |
| 2 | `src/agents/executor_repo.py:90` | repo 级执行（`_run` 原语） |
| 3 | `src/agents/executor_repo.py:869` | repo 级验证 |
| 4 | `src/agents/executor_runtime.py:133` | 子进程执行生成代码 |
| 5 | `src/agents/fl_spectral.py:238` | 失败定位（**BASELINE 自评风险最高**） |
| 6 | `src/agents/runtime_probe.py:345` | 探针执行（20s 超时） |
| 7 | `src/tools/dependency.py:533` | 依赖解析 |
| 8 | `src/tools/dependency.py:895` | 依赖验证 |
| 9 | `src/tools/patch_rollback.py:188` | git 快照/回滚 |
| 10 | `src/tools/testless_validation.py:120` | 无测试校验 |
| 11 | `src/tools/testless_validation.py:228` | 无测试校验 |
| 12 | `src/tools/type_repair.py:270` | 子进程类型检查 |

**与自述的对账**：`BASELINE.yaml:281` 写"另 9 文件 20 处 subprocess.run"——**文件数吻合（9），处数不吻合（AST 实测 12）**。`grep -c "subprocess.run(" src/` = 16 行，其中 4 行是注释/docstring（`branch_coverage_inject.py:164`、`executor_repo.py:712`、`executor.py:219`、`process_utils.py:5`）；把 `subprocess.` 的各种属性（Popen/TimeoutExpired/CompletedProcess）都算上才是 60 处。自述的"20"无来源可复算 → 建议改为 AST 计数并入库脚本。

**为什么仍是 P0**：`subprocess.run(timeout=)` 超时只 `kill()` 直接子进程；孙进程继承管道写端时 `communicate()` 等 EOF **永久阻塞**——这正是 `BASELINE.yaml:270-278` 记录的 30+ 分钟挂死（`branch_coverage_inject.py:161`）。`BASELINE.yaml:479-485` 记录第 1 环（病态任务不终止）未修，且实测 2 个孤儿进程（ppid=1、~100% CPU、56–63 分钟）。**执行 LLM 生成代码/测试的那几条链路（#1/#2/#3/#4/#5/#6/#12）风险最高**，任何一条再把批次挂死，损失是一个批次的算力预算。

### 6.3 其它性能项

- **并行默认关闭**：`config.py:545 BENCHMARK_PARALLELISM = _parse_int_env("BENCHMARK_PARALLELISM", 0, 0, None)` → 默认 0（串行）；E6 批次用 4。`--parallel` 与 env 并存。
- **测试耗时回升**：34.5s（自述）→ **54.08s**（实测，-n 4 loadfile）。
- 缓存目录卫生：`.mypy_cache` / `.ruff_cache` / `.pytest_cache` / `.hypothesis` 均在仓库根（均已 gitignore，`AH` 批把 `.hypothesis` 入 ignore）。
- `scripts/tools/performance_profile.py` + `perf.yml` 周跑微基准存在，但回归判定默认非阻断（见 §8）。

### 6.4 修复

```bash
# 1) 12 处统一换 primitive（机械替换，逐个补敌意测试）
sed -n '57,129p' src/utils/process_utils.py      # 先读实现
# 对每个调用点：subprocess.run(...) → run_with_timeout(...)；保留 timeout= 语义
# 2) 新增 AST 门禁（防新增裸 subprocess.run）：
python - <<'EOF'
import ast,pathlib,sys
bad=[f"{p}:{n.lineno}" for p in pathlib.Path('src').rglob('*.py')
     for n in ast.walk(ast.parse(p.read_text()))
     if isinstance(n,ast.Call) and getattr(n.func,'attr','')=='run'
     and getattr(getattr(n.func,'value',None),'id','')=='subprocess']
print(bad); sys.exit(1 if bad else 0)
EOF
# 3) 预算与缓存口径解耦：check_budget 增加 work_equivalent 维度（或至少在 cap 命中时把 cache_avoided 计入）
```

---

## 7. 安全与合规

### 7.1 现状（阳性为主）

```text
AST 扫描 src/（119 文件）：
  exec=0  eval=0  pickle=0  os.system=0  shell=True=0  __import__=0
  compile=1 → src/datasets/dataset_loader.py:396（对 instance_code 做语法校验，正当用途）

$ bandit -r src/ -c pyproject.toml -q     → exit 0（零 findings，bandit 1.9.4）
$ python scripts/gates/check_credential_scrub.py   → 通过（5 provider 键 × API_KEY/BASE_URL 全被 10 条剔除模式覆盖）
$ python scripts/gates/audit_log_redaction.py      → ✓ 未发现未脱敏可疑点
$ python scripts/gates/check_dependency_exemptions.py → 全部 4 条 --ignore-vuln 已登记
```

- 沙箱三档：`EXECUTOR_USE_VENV` 默认 **true**（`config.py:488`）；`EXECUTOR_USE_DOCKER` 默认 false（`:497`）；`KERNEL_SANDBOX_ENABLE` 默认 **false**（`src/agents/kernel_sandbox.py:69-70`，`config.py:45` 里的 "true" 只属于 `AITESTER_PROFILE=safe` 预设，我已核对无默认漂移）。缺平台工具时 fail-closed（`kernel_sandbox.py:16-38`），CI 预装 bwrap 但**安装失败不阻断**（`ci.yml:162-173`）。
- bandit skip 清单（10 条）每条都有书面理由（`pyproject.toml:223-226`），且 ruff `S` 规则集作为第二口径共存。
- 静态危险调用守卫：`src/tools/patch_applier.py:515-534 _DANGEROUS_CALL_TARGETS` + `:560 _build_import_alias_map`（C4 修复了 `from os import system` 别名绕过）；`src/agents/injection_guard.py:135-160` 正则拦 shell/eval/网络外连。

### 7.2 问题

1. **P2｜本地密钥守卫未生效（环境事实）**：`git config core.hooksPath` 未设置、`.git/hooks/` 无任何活动 hook → `.git-hooks/check_secret_leak.sh` 与 `.pre-commit-config.yaml` 的 `secret-leak-guard` 在实际检出中**都没装**；真正的阻断只发生在 CI（gitleaks，`ci.yml:448`）。`README.md:84` 要求 `pre-commit install`，但 `pre-commit` 不在任何锁定源（§2.2-2）。
2. **P2｜漏洞审计不可离线核验**：`pip-audit` 需联网；`pip_audit_lock.json` 仅 CI artifact。4 条 `--ignore-vuln` 的豁免理由在 `docs/dependency_exemptions*.md` 有登记（脚本 rc=0），但**漏洞状态本身无法在本地复核**。
3. **P3｜静态守卫的残余绕过面**：`_DANGEROUS_CALL_TARGETS` 是 AST 限定名匹配；`getattr(os,"system")`、`importlib.import_module` + `getattr`、`eval` 经字符串拼接（`RE_EVAL_EXEC` 只匹配字面 `eval(`/`exec(`）等动态派发仍可绕过。方向是"保守拦截"（宁可误拒），但应写入 `docs/threat_model.md` 的已知局限。
4. **P3｜`compile()` 单点**：`dataset_loader.py:396` 对**外部 JSONL 的 instance_code** 做 `compile(..., "exec")`——只编译不执行，安全；但同函数对 `test_code` 只做字符串包含判断（`dataset_loader.py:402-403`），真正的执行发生在 Executor 沙箱链路。无问题，仅提示"编译校验 ≠ 执行安全"。
5. **P3｜`pip` 安装类操作在依赖解析链路**（`dependency.py`）需要网络，无离线降级断言（属产品行为，非缺陷）。

### 7.3 修复

```bash
# 1) 把本地守卫变成"装得上"的默认路径
git config core.hooksPath .git-hooks     # 或把 pre-commit 纳入 requirements.txt/.lock
bash .git-hooks/check_secret_leak.sh     # 冒烟：应在含 sk- 的未跟踪文件上 exit 1
# 2) CI 增加"漏洞豁免复查"工件的入库校验（pip_audit_lock.json 的摘要 + 日期）
# 3) threat_model.md 增补"静态守卫不可覆盖的动态派发"清单
```

---

## 8. 工程化与运维（CI 门禁全表）

### 8.1 触发与作业

| 工作流 | 触发 | 作业 | 阻断性 |
|---|---|---|---|
| `ci.yml` | push/PR(main,master)、周日 cron、手动 | `smoke-llm`（`:45`）、`test`（`:102`，3.12/3.13/3.14）、`security`（`:395`，"blocking"）、`supply-chain`（`:573`，"info-only"） | 见下表 |
| `perf.yml` | 周日 cron `30 7 * * 0` + 手动 | `perf-benchmark` | **默认非阻断**（`--strict` 仅手动输入开启） |
| `release.yml` | tag `v*` | `ci-green` → `release`（build/twine/SBOM/PyPI 条件发布/GH Release） | `ci-green` 轮询 GitHub API 20 次；发布条件见下 |

### 8.2 `test` 作业逐门禁（行号 + 是否软）

| 步骤（`ci.yml` 行） | 作用 | 条件 | 判定 |
|---|---|---|---|
| `:175` mypy | 类型检查 | 全部腿 | **硬**（配置宽松，见 §3.2） |
| `:180` lock sync | txt↔lock | 全部腿 | **硬** |
| `:183` Solver gate | z3 可用性 fail-closed | 全部腿 | **硬** |
| `:209` llm_configs schema | 模型目录 schema | 全部腿 | **硬** |
| `:215` tool versions | CI↔hook↔lock 版本一致 | 全部腿 | **硬** |
| `:221` state contract | LangGraph 状态键静态契约 | 全部腿 | **硬** |
| `:227` checksum | 工件 SHA256 | **仅 3.14** | 硬（条件性） |
| `:236` artifacts tracked | MANIFEST 入库 | **仅 3.14** | 硬（条件性，覆盖 21 条） |
| `:246` zero-assert | 零断言测试 | **仅 3.14** | 硬（条件性） |
| `:253` env budget | 开关预算棘轮 | **仅 3.14** | 硬（条件性） |
| `:261` baseline numbers | 文档数字漂移 | 全部腿 | **硬但空转**（只查"是否硬编码"，不查数字正确性） |
| `:266` baseline 结构 | BASELINE 结构 | 全部腿 | **硬** |
| `:270` bilingual docs | 双语配对 `--strict` | 全部腿 | **硬** |
| `:290` static snapshot | 归档 docs/history | 全部腿 | 硬（生成物） |
| `:305` ruff check + format | lint/format | 全部腿 | **硬** |
| `:310` pytest + cov | 全量测试 | 全部腿（3 腿 × 全量套件） | **硬** |
| `:323` audit log redaction | 日志脱敏 | 全部腿 | **硬** |
| `:331` credential scrub | 凭证剔除动态推导 | 全部腿 | **硬** |
| `:364` branch coverage | 行 85/branch 77/核心模块 85–90 | 全部腿 | **硬** |
| `:379` ratchet | 89.5/82.5 只升不降 | 全部腿 | **硬** |

### 8.3 `security` / `supply-chain` / `perf` 的软门禁

| 步骤 | 行为 | 软/硬 |
|---|---|---|
| bandit `:422` | `bandit -r src/ -c pyproject.toml -q` | 硬（本地实测 exit 0） |
| gitleaks 工作树 `:448` | 当前树扫描 | 硬 |
| pip-audit txt `:460` / lock `:490` | 依赖漏洞（含 4 条 ignore） | 硬（需联网） |
| 豁免登记 `:554` | 4 条豁免留痕 | 硬 |
| **gitleaks 全历史 `:529`** | `gitleaks detect --redact \|\| echo ::warning` | **软（非阻断周检）** |
| **引用核验 `:542`** | `continue-on-error: true` + `--online --no-strict \|\| echo ::warning` | **软** |
| **docs 漂移 `:560`** | `--warn-only`，且 `check_docs_history_drift.py:123-125` **只有 `--strict` 才 return 1** | **软（永远绿）**——实测 **131 条**漂移告警仍然 exit 0 |
| **SBOM `:592`** | `cyclonedx-py … \|\| pip install … && cyclonedx-py …` | **软（info-only 作业）** |
| perf 回归 | 默认 `STRICT_FLAG=""` | **软（除非手动 strict）** |
| release PyPI 发布 | 非官方仓/无 secret 时静默跳过（仅 notice） | 软（有意） |

其它：`check_swe_bench_pro_ready.py` 本地 **exit 1**（数据未就绪，预期），**未接 CI**；18 个本地 gate 实跑 = 16 绿 + 2 红（上述 1 个 + branch coverage 因无 coverage.xml）。

### 8.4 问题

1. **P1｜`make gates` 与 CI 不对齐**（总表 P1-4）：贡献者按 `Makefile:49` 自检全绿仍可能 CI 红（缺 format、branch、ratchet、zero-assert、artifacts、credential、audit-log、豁免、llm_configs）。
2. **P2｜"永不失败"的门禁**：docs-history 漂移门禁 131 条告警恒 exit 0（除非 `--strict`，而 CI 传的是 `--warn-only`）→ 该步骤只有提示价值，应改名或在 job summary 里显式标注。
3. **P2｜条件门禁无"至少跑一次"断言**：6 个步骤绑死 3.14 腿（见 §4.2-3）。
4. **P2｜pre-commit 与 CI 的 mypy 口径不同**：hook 用 `--ignore-missing-imports --no-strict-optional` 且 `exclude: ^tests/`；CI 用仓库配置。hook 绿 ≠ CI 绿（历史上出现过 B-05 的 rev 缩进 bug 使校验"形同虚设"，已修）。
5. **P3｜第三方 action 与 hook 版本混代**：actions 用 SHA 固定（好），但 `pre-commit-hooks v4.5.0` 是 2023 年版本，与 ruff/mypy 的 2025-2026 版本混用。
6. **P3｜无监控/告警**：观测只有 `tmp_trace`/`traces/*.trace.jsonl` + `rogue_monitor`/telemetry 模块；无指标后端、无失败告警（对本项目"跑批 37 分钟"的运营形态，批次失败只能靠人看日志）。

### 8.5 修复

```bash
# 1) Makefile gates 改为 CI 真子集对齐（把 9 类缺失门禁补进 gates 目标）
# 2) 条件门禁增 sentinel：Write gate-ran marker → 最后一步断言 marker 存在
# 3) docs-history 门禁：CI 改 --strict --threshold 20（只拦"历史文档声明当前基线"这类硬漂移）
# 4) pre-commit mypy hook 与 CI 参数对齐；升级 pre-commit-hooks 到 v5/v6
```

---

## 9. 数据 / 实验 / ML 管线

### 9.1 缓存污染与对照（重点）

- **命名空间只按 seed，不按臂**：`experiments/run_benchmark.py:2399-2402` → `AITESTER_CACHE_NAMESPACE = f"seed{seed}"`；键材料 = `prompt + system + temperature + model + ns`（`base_agent.py:355-395`）。因此**同 seed 下不同臂只要有一段提示词相同就会共享缓存条目**。
- **已发生的对照事故**（`BASELINE.yaml:448-455`）：`over_red_section_firstrun_NOTVERIFIABLE.json` —— 开关未入快照 + 复用标准臂 namespace，再生成响应被缓存短路，"强化段未送到模型" → 判为**不作结论依据**。这是**缓存掩盖"开关未生效"**的典型案例。
- **同一缺陷在 RT1 上重演**（本轮新发现，P0-1）：
  - RT1 臂的定义开关 = `DETECTION_FIRST_SECTION_ENABLE=false`（`BASELINE.yaml:531-534`；开关实现 `src/graph/nodes.py:490-495`）；
  - `rt1_no_reinforcement_seed42/benchmark_synthetic_20261009_193509.json` 的 `provenance.env_snapshot` **38 键**，含 `DETECTION_FIRST_ENABLE: "true"`，**不含 `DETECTION_FIRST_SECTION_ENABLE`**；
  - `rt1.log` 中 `DETECTION_FIRST_SECTION_ENABLE` 出现 **0** 次（`grep -c` = 0），日志头只写"基线：plain_llm_df"；
  - 当前 `_env_snapshot_keys`（`run_benchmark.py:2712-2770`）仍**未**收录该键（2026-10-10 只补了 `OVER_RED_SECTION_ENABLE`）。
  → **"RT1 与 plain_llm 采样效应可忽略、+43pp 归因提示协议本身"这一结论，与它自己废掉的 NOTVERIFIABLE 臂一样，无法从工件证明干预是否生效**。修复：补键 → 重跑该臂（或至少把该结论降级为"log 之外无工件证据"）。

### 9.2 detection 的 None/分母口径

- `e6_phase2_matched_coldcache`：`aitester` 臂 **76/87 行 `detection_rate=None`**，`plain_llm_df` 仅 1/87。
  - `BASELINE.yaml:591` 记 `2/87 (2.3%)`（全量分母）；
  - 同一批次的日志自己算的是 **"可测 11/87 → 18.2%"**（`phase2.log:1150`）；
  - 配对主终点表自己也写"仅 11 共同任务，**检验力不足不作判定**"（`BASELINE.yaml:596`）。
  → 三处口径不一致，且 `:602` 的 `interpretation`（"低预算下 aitester 更差…源于编排结构"）**超出了其注册主终点允许的结论强度**。修复：统一"可测口径 + ITT 口径"双列呈现，并把 `interpretation` 降级为待验证假设。
- 一般规律：各臂 `None` 比例不同（main_batch 各批 6–11/87；E6 control aitester 6、plain_llm 0、df 0），**配对分析丢行 → 实际是 as-treated 而非 ITT**；报告只给一个百分比，未声明分母。

### 9.3 统计模块（抽检为正确）

- 方法齐备：McNemar（连续性校正）、两比例精确检验、BH-FDR、Cliffs δ、bootstrap 配对 CI（固定 `seed=42`，纯 Python，`statistical_analysis.py:682-733`）、贝叶斯配对 + ROPE（`bayesian_paired.py`）、模板簇 ICC/DEFF/符号检验、`pass@k`、`$/detection`。
- 抽检算术：`statistical_analysis.py:525-526` `chi2=(|n01-n10|-1)^2/(n01+n10)`，与 `BASELINE.yaml` 的 `χ²=0.500, p=0.4795`（不一致对 2）**一致**。
- 缺口：聚类校正后的 `χ²_adj=6.60` 等数字只出现在 BASELINE 文本里，**仓内无对应脚本入口**（`grep -rn "chi2_adj\|DEFF\|n_eff" experiments/*.py` 无实现），属"文本级统计"→ 不可复算。建议把簇校正写进 `statistical_analysis.py` 并让报告直接产出。

### 9.4 泄漏与质量控制

- **金标测试未进生成提示**：`oracle_type=generated_test`（全部行）；`repair_rate/false_fix_rate` 走独立 gold 通道（`run_benchmark.py:1087-1097` 注释与实现一致）。生成侧只从 `problem_statement` 出发；RAG 参考会注入历史 `test_code`（`src/agents/generator.py:430-433`），而 RAG 默认关且有 A/B 阴性证据 → **当前口径无 gold 泄漏**。
- **`test_visible_to_system` 是常量**（P1-8）：`run_benchmark.py:1097` 与 `:1244` 均硬编码 `True`，把"APR 严谨性检查点 #2"变成不变量；若未来 Executor 不再"看见"测试，该字段仍为 True → 建议改为真实推导或改名 `test_visibility_policy`。
- 合成集模板簇：cluster k=29（`BASELINE.yaml:246`），模板 50 个自验证通过（`synthetic_templates: 50`）。
- **存疑数据点**：`benchmark_synthetic_20261001_121523.json` 的 `single_agent` 臂 50 行覆盖率均值 **4.8%**、detection 全 0——与同批 aitester 93.6% / plain_llm 86.0% 差一个量级，`target_quality_report.md` 也只列 aitester/plain_llm/plain_llm_df（该臂被静默略过）。建议在历史批次注记中登记为"已知损坏臂"或补勘误。
- 模型卡/数据卡/预注册齐备（`MODEL_CARD.md`、`DATA_CARD.md`、`docs/preregistration.md` 双语），非清洁许可数据集已登记（BugsInPy / TestGenEval）。

### 9.5 修复

```bash
# 1) 缓存命名空间升级到 per-arm：AITESTER_CACHE_NAMESPACE=f"seed{seed}__{arm}"
#    （跨臂共享从此不可能；再跑一次 E6 control 即可消除历史污染面）
# 2) 工件校验器（新 gate，失败即阻断报告引用）：
#    - provenance.cache_enabled==false ⇒ 所有行 total_tokens>0 且 cache_hits==0
#    - 冷缓存批次的 token 覆盖必须 == n
# 3) 报告层强制双口径：detection_full / detection_measurable 两列 + n_measurable
# 4) 把簇校正/符号检验落进 statistical_analysis.py，禁止"文本级统计"
```

---

## 10. 文档与协作

### 10.1 现状

- 双语门禁：`check_bilingual_docs.py --strict` → `双语文档同步检查通过（0 警告 / 0 失败）`；配对文档齐备（README/QUICKSTART/CONTRIBUTING/SECURITY/MODEL_CARD/DATA_CARD/threat_model/api_reference/algorithm_design/failure_analysis/performance_guide/preregistration/dependency_exemptions 均为 .md + .en.md）。
- CHANGELOG：`CHANGELOG.md` 88 个 `##` 段落、`CHANGELOG.en.md` 88 个，日期覆盖均到 **2026-10-10**（结构未见分叉）；体量 397KB / 411KB。
- 模板与责任人：`.github/ISSUE_TEMPLATE/`、`.github/PULL_REQUEST_TEMPLATE.md`、`.github/CODEOWNERS` 均存在（任务书假设的"模板缺失"**不成立**）。
- **数字去硬编码**做得好：`README.md:29-48` 明确"当前数字不在 README 硬编码，见 BASELINE.yaml"，`check_baseline_numbers.py` rc=0。
- 覆盖率口径澄清：`BASELINE.yaml:26-30` 显式声明 `coverage` 是 **meta_coverage（项目自身源码）**，与 `target_quality`（被测代码）分离——这是本仓最值得肯定的一处口径纪律。

### 10.2 问题

1. **P1｜BASELINE 数字未校准**（总表 P1-1：5015→5178、35s→54s、mypy 119→120）。**"唯一事实来源"没有自动校验环**，门禁只查"别处有没有硬编码"。
2. **P2｜遗留歧义数字仍在正文**：`README.md:48` 的"全量 4669/0"（2026-10-07 批次口径）、`:1584` 的"成功率 100%，平均覆盖率 91.7%"（旧口径示例）——都属历史叙述，但与当前 5178/5015 混排时极易被引用为现状；`check_baseline_numbers.py` 不覆盖这两个位置。
3. **P2｜文档-代码漂移实例（可复核）**：
   - `scripts/gates/check_branch_coverage.py:8-9`（85%）vs `:57`（0.77）；
   - `BASELINE.yaml:82`（119 文件）vs mypy 实测 120；
   - `pyproject.toml:166`（14 处 try-except-pass）vs 实测 16；
   - `BASELINE.yaml:281`（20 处 subprocess.run）vs AST 12；
   - `Dockerfile.repro:8`（"锁定版本"）vs `:36`（requirements.txt）；
   - `README.md:84`（`pre-commit install`）vs 工具链不在锁定源。
   → 共同模式：**注释/文档里的"计数与承诺"没有机器校验**，而代码里的行为（阈值、开关）会被 gate 拦。建议把这类"自述数字"统一改用"(命令) → 数字"格式，并由一个 `docs-numbers-check` 任务在 CI 里重算。
4. **P2｜历史文档漂移门禁永不失败**：`docs/history/*.md` 131 条基线数字漂移告警，CI `--warn-only`；即便不加 `--warn-only` 也 return 0（脚本逻辑决定）。→ 建议 `--strict --threshold 20`，或明确标注"信息性"。
5. **P3｜CHANGELOG 体量与结构**：两份合计 ~800KB；最新条目依赖超长段落叙述（BASELINE 的 `last_verified` 单行即数千字），可读性/可 diff 性差。建议 CHANGELOG 只保留条目摘要，长叙事移到 `docs/history/`（本批已删 2 份历史快照 + 8 份孤儿报告，方向一致）。

### 10.3 修复

```bash
# 1) 新增 scripts/gates/check_baseline_measured.py：
#    pytest --collect-only 计数 + mypy 文件数 + suite_seconds(可选) 与 BASELINE 比对，不一致 exit 1
# 2) README 历史数字加显式年份/批次前缀（"（2026-10-07 批次，历史口径）"）
# 3) docs-history 门禁转 --strict --threshold 20
# 4) 把"自述数字"（85%/20 处/119 文件…）纳入同一校验器或改为生成式引用
```

---

## 11. 无法核验项（明确声明）

| # | 项 | 原因 |
|---|---|---|
| 1 | `pip-audit` 漏洞结论与 4 条 `--ignore-vuln` 的时效性 | 需联网；仓内无审计工件（仅 CI artifact），离线不可复算 |
| 2 | gitleaks 全树/全历史扫描结论 | 工具未安装，需联网下载；本地无 `gitleaks` 二进制 |
| 3 | GitHub Actions 上 3.12/3.13 腿与 security 作业的真实运行结果 | 无 CI 日志/API 凭据；本轮只核验了配置与本地等价命令 |
| 4 | `python -m build` 隔离构建（PEP 517 默认路径） | 需联网拉 setuptools/wheel；本轮改用 `pip wheel --no-build-isolation`（`ERROR Missing dependencies: wheel` 已如实记录） |
| 5 | 任何真实 LLM 调用/象限实验（含 E6/E7 待跑部分） | 本轮零 LLM 成本，未消耗配额 |
| 6 | `perf.yml` 微基准的绝对性能结论 | 依赖 GitHub runner 环境；本地未复跑基准脚本 |
| 7 | 30+ 分钟挂死与孤儿进程的历史现象 | 只读取 `BASELINE.yaml` 记录，不做复现（避免制造真实孤儿进程占用机器） |
| 8 | `main_batch` 中 `single_agent` 臂（覆盖率 4.8%）的成因 | 该臂已从当前 baselines 列表移除，无代码路径可对照 |
| 9 | 队友 T3/T4 的领域与断言审查结论 | 跨任务边界，不重复核验 |

---

## 附录：本轮关键命令与原始输出（可复跑）

```bash
# ── 结构/包 ──────────────────────────────────────────────
find src -name "*.py" | wc -l                     # 119
find src -name "*.py" -exec cat {} + | wc -l      # 45371
.venv/bin/python -m pip wheel . -w /tmp/t2pkg/dist --no-deps --no-build-isolation

# ── 依赖 ────────────────────────────────────────────────
.venv/bin/python scripts/gates/check_lock_sync.py                    # rc=0（23↔132）
.venv/bin/python scripts/gates/check_dependency_exemptions.py        # rc=0（4 条）
grep -c '^pre-commit==' requirements.lock                            # 0

# ── 质量 ────────────────────────────────────────────────
.venv/bin/python -m ruff check . --no-cache                          # All checks passed!
.venv/bin/python -m ruff format --check src tests experiments scripts config.py main.py init_db.py --no-cache  # 460 files OK
.venv/bin/python -m mypy --cache-dir=/tmp/t2_mypy_cache --no-incremental src/ config.py            # 0 错 / 120 文件
.venv/bin/python -m mypy --cache-dir=/tmp/t2_mypy_cache --no-incremental --warn-unused-ignores src/ config.py  # 8 错
.venv/bin/python -m mypy --cache-dir=/tmp/t2_mypy_cache --no-incremental --warn-return-any src/ config.py      # 24 错
.venv/bin/bandit -r src/ -c pyproject.toml -q                        # rc=0 零 findings

# ── 测试 ────────────────────────────────────────────────
.venv/bin/python -m pytest --collect-only -q -p no:cacheprovider --basetemp=/tmp/t2pytest | tail -1   # 5178 collected
.venv/bin/python -m pytest tests/ -q -p no:cacheprovider --basetemp=/tmp/t2pytest -n 4 --dist loadfile  # 5175 passed, 3 skipped in 54.08s
.venv/bin/python scripts/gates/check_zero_assert_tests.py --list      # 253 文件 / 0 违规

# ── 门禁矩阵（18 个本地脚本）────────────────────────────
for g in check_baseline check_baseline_numbers check_bilingual_docs check_branch_coverage \
         check_citations check_credential_scrub check_dependency_exemptions check_docs_history_drift \
         check_env_budget check_llm_configs_schema check_lock_sync check_perf_regression \
         check_state_contract check_swe_bench_pro_ready check_tool_versions check_zero_assert_tests \
         audit_log_redaction check_artifacts_tracked; do
  .venv/bin/python scripts/gates/$g.py >/dev/null 2>&1; echo "$g rc=$?"; done
# → 16×rc=0；check_branch_coverage rc=1（无 coverage.xml）；check_swe_bench_pro_ready rc=1（数据未就绪）

# ── 工件复算 ────────────────────────────────────────────
.venv/bin/python scripts/gates/checksum_results.py --results-dir experiments/results/e6_a1_batches --verify  # 1088/1088
# provenance 统计：29 个批次有 provenance，git_dirty=True 24 / cache_enabled=True 23
# rt1 批次 env_snapshot 键数 38；`grep -c DETECTION_FIRST_SECTION_ENABLE rt1.log` → 0
# e6_phase2 日志："可测 11/87 任务: detection=18.2%"（phase2.log:1150）

# ── subprocess AST 清单 ─────────────────────────────────
# 13 个启动调用 / 10 文件（含 process_utils 的 Popen）；
# 裸 subprocess.run = 12 处 / 9 文件（见 §6.2 表）
grep -rn "run_with_timeout" src/ | grep -v process_utils   # 只有 branch_coverage_inject.py:42,168
```

---

### 附：与自述缺陷的闭环核对表

| 自述缺陷 | 自述状态 | 本轮独立核验 |
|---|---|---|
| D1 Planner 空计划（JSON 解析） | 已修（`helpers.py` 5 函数） | 未复核解析器本身（超范围）；BASELINE 的消融数字与 artifacts 一致 |
| D2 缓存命中不计 token | "P0 止血" | **部分闭环**：LRU/文件路径已记侧信道；`total_tokens`/预算仍不含；**语义缓存命中零记账**（`base_agent.py:420-431`）；无工件级门禁 |
| D3 消融开关未入 env_snapshot | 个案已补（PLAN_STRIP/OVER_RED） | **未系统化**：`DETECTION_FIRST_SECTION_ENABLE`（RT1 定义开关）仍缺席，37/55 开关无快照 |
| batch_hang_fix（killpg） | 已接线 1 文件 | **确认只 1 处**；其余 9 文件 12 处同风险；自述"20 处"无法复算 |
| orphan_processes 第 1 环 | 未修 | 与代码一致（无病态任务资源上限/快速失败标记）；`_PROBE_SUBPROCESS_TIMEOUT` 等仅覆盖单次执行 |
