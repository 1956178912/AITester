# N-2 全功能 e2e 探针证据：平台/基础设施组（2026-10-17）

> **性质**：N 轮 N-2 交付工件（全功能 e2e 探针，平台/基础设施组）。
> **探针模块**：`scripts/tools/e2e_probes_platform.py`（导出 `PROBES`，**25 个探针**）。
> **运行器**：`scripts/tools/e2e_probe.py`（每探针独立子进程、崩溃/挂死隔离、
> LLM 探针默认 skip、运行器强制 `AITESTER_LLM_CACHE=0` 与独立 cache namespace）。
> **实测结论**：零 LLM 子集 **21 pass / 0 fail / 0 error / 4 skip（LLM 未启用）**；
> `AITESTER_E2E_LLM=true --include-llm` 全量 **25 pass / 0 fail / 0 skip**。
> 真实 LLM 调用：报告跑 **4 次** + safe 档追加验证 **1 次**（1026 tokens，≈$0.0009），
> 合计上界 **< $0.01**（预算 $0.2 内）。
> 跑出 **4 处静默失效缺陷**，全部在写域内修复：
> ① Seatbelt SBPL 单引号语法；② deny-default 缺根目录 read/metadata；
> ③ **执行器沙箱接线**（解释器路径/TMPDIR/`.venv` 误伤 DENY 正则；Lead 批准追加，
> 含错误分类修正与 safe 档端到端复验）；④ **D3 过度脱敏**（长路径段被 base64
> 模式误判为密钥；N-1 上报，Lead 批准追加）。

## 0. 结论速览

| 项 | 结果 |
|---|---|
| 探针数量 | **25**（预算 4 / 缓存 3 / RAG 2 / 安全 4 / 执行器 **5** / 数据集 4 / 可观测 3；真 LLM 4 个） |
| 零 LLM 子集 | **21 pass / 0 fail / 0 error / 4 skip**（skip = LLM 探针未启用，报告可见原因） |
| 全量 LLM 子集 | **25 pass / 0 fail / 0 error / 0 skip** |
| 真实 LLM 调用/成本 | 报告 4 次（预算 29 tokens、缓存首调 29 tokens、RAG/指纹最小调用）+ safe 档 1 次（1026 tokens）；上界估算 **< $0.01**（$0.2 预算内） |
| 缺陷 | **4 修复**：kernel_sandbox SBPL 语法 / 根目录放行 / 执行器沙箱接线（含 `.venv` 误伤 DENY 正则、错误分类、safe 档复验）/ **D3 过度脱敏**（长路径段误判，N-1 上报） |
| 新增回归测试 | **134 例**（`test_e2e_probes_platform.py` 54 + `test_n_round_platform_kernel_sandbox.py` 14 + `test_n_round_platform_executor_sandbox.py` 29 + `test_n_round_platform_over_redaction.py` 37）；另既有 redaction/kernel sandbox/执行器测试零回归 |
| 验证 | `--list` 25 行；零 LLM 全跑 exit 0（含 D3 路径零误伤断言）；LLM 全跑 exit 0；ruff/format 全绿；`mypy src/utils/logging_utils.py src/agents/kernel_sandbox.py src/agents/executor.py src/agents/executor_modes.py` 0 错 |

## 1. 复现命令（可直接重跑；报告为落盘 JSON/MD）

```bash
# 1) 探针清单
.venv/bin/python scripts/tools/e2e_probe.py --module scripts.tools.e2e_probes_platform --list

# 2) 零 LLM 子集（默认；LLM 探针 skip）
.venv/bin/python scripts/tools/e2e_probe.py --module scripts.tools.e2e_probes_platform --all \
  --json-out experiments/results/e2e_probe_platform_20261017/zero_llm_report.json \
  --md-out   experiments/results/e2e_probe_platform_20261017/zero_llm_report.md

# 3) 全量（含真实 LLM；4 次真实调用，成本 < $0.005）
AITESTER_E2E_LLM=true .venv/bin/python scripts/tools/e2e_probe.py \
  --module scripts.tools.e2e_probes_platform --all --include-llm \
  --json-out experiments/results/e2e_probe_platform_20261017/llm_report.json \
  --md-out   experiments/results/e2e_probe_platform_20261017/llm_report.md

# 4) safe 档最小任务端到端（1 次真实 LLM；验证 KERNEL_SANDBOX_ENABLE 执行链路）
AITESTER_LLM_CACHE=0 .venv/bin/python \
  experiments/results/e2e_probe_platform_20261017/repro_safe_profile_e2e.py \
  | tee experiments/results/e2e_probe_platform_20261017/safe_profile_e2e.log

# 5) 回归测试（N-2 全部新增 + 既有内核沙箱/执行器）
.venv/bin/python -m pytest -q tests/test_e2e_probes_platform.py \
  tests/test_n_round_platform_kernel_sandbox.py tests/test_n_round_platform_executor_sandbox.py \
  tests/test_kernel_sandbox.py tests/test_p0_4_kernel_sandbox_enabled_path.py \
  tests/test_p2_5_venv_kernel_sandbox.py
```

## 2. 探针清单与实测状态

| group | 探针 | LLM | 零 LLM 集 | 全量集 | 说明/实测证据 |
|---|---|---|---|---|---|
| budget | `budget-cost-cap` | 否 | pass | pass | 累计 120 tokens > 上限 100 → check_budget=False，events=1 |
| budget | `budget-invalid-fail-closed` | 否 | pass | pass | 坏浮点/负值均 fail-closed，misconfigured_events=2 与真实超限分列 |
| budget | `budget-batch-quota` | 否 | pass | pass | `estimate_calls(150)=968`；未配置→2 条 blocking；上限 2000→ok；100→拦截 |
| budget | `budget-llm-stop` | **是** | skip | pass | 真调 1 次成功（'7'）后预算耗尽；第 2 次在联网前抛 `BudgetExceededError`（consumed=29 tokens） |
| cache | `cache-disabled` | 否 | pass | pass | `AITESTER_LLM_CACHE=0` → 文件缓存 enabled=False；语义缓存默认 enabled=False |
| cache | `cache-two-call-hit` | **是** | skip | pass | 真调 1 次：同 prompt 第 2 次命中（0.000s vs 首次 0.93s），`llm_calls=1, cache_hits=1, avoided_tokens=29` |
| cache | `cache-semantic-index` | 否 | pass | pass | 真实嵌入：同义命中 / 无关未命中（hits=1, misses=1，阈值 0.75） |
| rag | `rag-retriever` | 否 | pass | pass | chromadb 检索器初始化 0.05s；写 1 案例 → 检索 1 条（相似度 0.7143） |
| rag | `rag-workflow-stats` | **是** | skip | pass | `ENABLE_RAG=true` 最小任务完成；终态 `rag_stats=[{kind:test_cases,...}]`，generated_test 1437 字符 |
| security | `security-injection-guard` | 否 | pass | pass | 3 类注入全检出、干净文本零误报、警示含【安全警示】；危险补丁 os.system/eval 检出、安全补丁零误报 |
| security | `security-credential-scrub` | 否 | pass | pass | 白名单剔除 6 个假凭证键；真实子进程 env 无 `LLM_*`/`*_API_KEY`；provider 名单 10 项 |
| security | `security-log-redaction` | 否 | pass | pass | 3 条含假 sk- key 日志经 handler 后均脱敏（含 args 拆分形态） |
| security | `security-kernel-sandbox` | 否 | pass | pass | macOS Seatbelt：`/bin/echo` 在沙箱内**真实执行** rc=0；profile 无双引号缺陷（修复后） |
| executor | `executor-local` | 否 | pass | pass | 本地执行器真实跑最小测试 passed/coverage=100.0 |
| executor | `executor-venv` | 否 | pass | pass | venv 沙箱执行器真实跑最小测试 passed/coverage=100.0 |
| executor | `executor-docker-degrade` | 否 | pass | pass | 本机无 docker CLI → passed=False + `error_info.type=docker_unavailable`（明确降级，未回退本地） |
| executor | `executor-repo-verify` | 否 | pass | pass | 本地临时 git 仓库：test_patch 基线红 → llm_patch 后 F2P 1/1 转绿 → passed=True（零网络） |
| executor | `executor-kernel-sandbox` | 否 | pass | pass | **N-2 追加**：`KERNEL_SANDBOX_ENABLE=true` 下 local+venv 真实沙箱执行均 passed（2.6s），obs.supported=True |
| dataset | `dataset-loaders` | 否 | pass | pass | quixbugs=50 / examples=3 / synthetic=3 + gold 材料键（fixed/test_cases） |
| dataset | `dataset-ult` | 否 | pass | pass | ULT 加载 200 任务（`ult__*`） |
| dataset | `dataset-decontamination` | 否 | pass | pass | total=3 kept=1 dropped=1 unverifiable=1；rate=0.5（unverifiable 显式披露） |
| dataset | `dataset-check-cli` | 否 | pass | pass | `main.py check-dataset quixbugs` rc=0，检查 50 任务无加载问题 |
| observability | `observability-trace-redaction` | 否 | pass | pass | TraceSession JSONL 3 行（task_start/node/task_end）且假凭证已脱敏 |
| observability | `observability-event-bus` | 否 | pass | pass | 发布/订阅/计数正常；`EVENT_BUS_ENABLE=false` 时 no-op（消融口径） |
| observability | `observability-model-fingerprint` | **是** | skip | pass | 真调 1 次：alias=deepseek-flash / returned=deepseek-flash / **pinned=True**，probe_sha256 在场 |

## 3. 发现的缺陷与修复

### 3.1 已修复：内核沙箱 Seatbelt profile 静默失效（2 处同源缺陷）

**缺陷 A（根因）**：`src/agents/kernel_sandbox.py::_seatbelt_profile` 用 Python
`repr()`（`f"(subpath {path!r})"`）生成 SBPL 路径字面量 = **单引号字符串**，
而 Seatbelt profile 语言只接受双引号字符串：

```
$ sandbox-exec -p "(version 1)(deny default)(allow file-read* (subpath '/tmp'))..." /bin/echo hi
sandbox-exec: unexpected symbol argument
Backtrace:
<input string>:3:20:
    (subpath '/tmp')
rc=65
```

即 `KERNEL_SANDBOX_ENABLE=true` 时**所有**内核沙箱执行链路 100% 失效，且失败
只出现在 pytest 输出里（被归类为 `test_failure` 而不是"沙箱不可用"）。
既有单测只断言 `cmd[0] == "sandbox-exec"`，未真实执行 → 缺陷长期静默。

**缺陷 B（同源，修复 A 后暴露）**：`(deny default)` 下缺根目录 read/metadata
放行 → 沙箱进程在 dyld/路径解析阶段 **SIGABRT（rc=-6，无任何错误输出）**。
最小必要放行（实测 bisect）：`(allow file-read* (literal "/"))` +
`(allow file-read-metadata (subpath "/"))`（仅 stat/根目录，不放开全盘内容读取）。

**修复**（`src/agents/kernel_sandbox.py`）：新增 `_sbpl_quote()`（JSON 双引号
转义，反斜杠/引号/非 ASCII 安全）；全部路径字面量改用之；profile 增加根目录
read + 祖先 metadata 放行；保留 S2 凭证 DENY。回归锁：
`tests/test_n_round_platform_kernel_sandbox.py`（14 例，含沙箱命令真实执行 rc=0）。

### 3.2 已修复（N-2 追加，Lead 批准）：执行器沙箱接线

**修复前**（证据 `defect_executor_kernel_sandbox_wiring.log`）：

```
KERNEL_SANDBOX_ENABLE=true + ExecutorAgent().execute(trivial_test, target)
→ passed=False
→ error_info={'type': 'test_failure', 'returncode': 71, ...}
→ output: sandbox-exec: execvp() of '/Users/.../.venv/bin/python' failed: Operation not permitted
→ kernel_sandbox_obs.allowed_paths = [<target_dir>, <project_root>]
```

两种执行模式（local `executor.py:239` / venv `executor_modes.py:148`）均失败，
且被误分类为 `test_failure`（Debugger 会去"修代码"而不是发现沙箱不可用）。

**修复过程中又暴露 3 个被上层缺陷掩盖的静默问题**（全部在写域内一起修）：

1. **解释器不在放行面**：接线只放行任务目录。解释器 `venv/bin/python` 的
   **字面路径**、realpath（framework `Python.app`）、venv 根（`pyvenv.cfg`/
   site-packages）、framework 安装根、pytest 临时目录都不可见 →
   exec/读均被拒。修复：新增 `interpreter_sandbox_allowances()` 计算最小
   exec/read 放行面（只读+仅执行，不扩大可写面），并给 `build_sandbox_command`
   增加细粒度参数 `cwd_rw / exec_paths / read_paths / write_paths`
   （文件 literal、目录 subpath；文件/目录语义分开）。
2. **`.venv` 被凭证 DENY 正则误伤**：历史 DENY 正则 `.env.*` 把 `.venv/` 整棵
   虚拟环境树也 DENY（".venv" 含子串 ".env"）→ Python 读 `pyvenv.cfg`
   `PermissionError`。修复：正则改为**路径分量匹配**
   `(^|/)\.env($|[./])|(^|/)\.ssh($|/)|(^|/)\.aws($|/)|llm_configs\.json|credentials`
   ——`.env/.env.local/.ssh/.aws/llm_configs.json` 仍拒，`.venv` 放行（真实执行
   验证见回归测试）。
3. **系统路径符号链接与设备节点**：macOS `/tmp → /private/tmp`、`/var →
   /private/var`，SBPL 按真实路径匹配 → TMPDIR 扫描被拒（pytest rootdir 失败）；
   `deny default` 下缺 `/dev/null` 等设备节点（pytest 捕获层/`tempfile` 失败）。
   修复：放行规则同时生成**字面 + realpath 两种形式**；极小放行
   `/dev/null`（读写）、`/dev/zero`、`/dev/urandom`、`/dev/random`（只读）。

**接线修正**（`src/agents/executor.py` / `executor_modes.py`）：

- 两模式统一：`interpreter_sandbox_allowances(cmd[0])` → exec/read 放行面；
  `cwd_rw=False`（项目根**只读**，防写仓库根）+ TMPDIR 读写；
- 沙箱模式专有：`-p no:cacheprovider`、`PYTHONDONTWRITEBYTECODE=1`、`TMPDIR`
  显式传入、`COVERAGE_FILE` 落 TMPDIR（不写仓库根）；
- **错误分类**：`sandbox_launch_failure(output)` 识别 `sandbox-exec:`/`bwrap:`/
  `execvp() of`/`Operation not permitted` 等启动失败特征 → 覆盖
  `error_info.type="kernel_sandbox_unavailable"`（附 `returncode/message` +
  `kernel_sandbox_launch_failed=True`）；**不新增 `ErrorCategory` 枚举值**，
  不改 BASELINE `error_categories=18` 口径（回归测试锁定 `len(ErrorCategory)==18`）；
  真实测试失败仍记 `test_failure`（分类只覆盖沙箱场景）。

**修复后**（证据 `after_executor_kernel_sandbox_wiring.log`）：

```
KERNEL_SANDBOX_ENABLE=true + ExecutorAgent().execute(trivial_test, target)
→ passed=True, coverage=100.0, error_info=None
→ kernel_sandbox_obs = {supported: true, backend: seatbelt,
     exec_paths: [...venv/bin/python 字面, framework realpath/bin, framework 安装根],
     read_paths: [项目根, TMPDIR, venv 根, framework 根, ...],
     write_paths: [TMPDIR], cwd_rw: false,
     profile_summary: "1 路径写放行 + 6 只读 + 5 仅执行 + 全文件系统只读 + 断网"}
```

**safe 档端到端**（证据 `repro_safe_profile_e2e.py` + `safe_profile_e2e.log`，
真实 LLM **1 次**、1026 tokens、≈$0.0009）：

```
ACTIVE_PROFILE=safe / KERNEL_SANDBOX_ENABLE=true / INJECTION_GUARD_ENABLE=true
执行器（safe 档沙箱）: passed=True coverage=100.0 obs.supported=True
最小 workflow 任务: elapsed=3.2s, test_passed=true, error_category=null,
  generated_test_len=1569, injection_findings=[],
  token_usage={in:391, out:635, total:1026, llm_calls:1}
VERDICT = PASS
```

**回归锁**：`tests/test_n_round_platform_executor_sandbox.py`（29 例）：
解释器放行面（exec/read 分离、venv 根仅 pyvenv 存在时只读）、profile 细粒度
规则（literal/subpath、realpath 变体、`.venv` 不误伤 vs `.env/.ssh/.aws` 仍拒）、
`cwd_rw=False` 不写仓库根、启动失败分类正/负控、**local+venv 沙箱真实执行
passed**、平台不支持 fail-closed、**默认关零行为变化**（不调用沙箱构建）、
错误枚举不变、**safe 档端到端**（子进程 `AITESTER_PROFILE=safe` 真实执行）；
另探针模块新增 `executor-kernel-sandbox`（真实 local+venv 沙箱执行，防回归）。


### 3.3 已修复（D3，N-1 上报，2026-10-17）：日志脱敏过度脱敏（长路径误判密钥）

**症状**（Lead 转述 N-1 上报 + 本次复现）：

```
mask_sensitive_info('/tmp/.cache/aitester/quixbugs/correct_python_programs')
→ '/tmp/.<REDACTED_KEY>'                       # 点号后长路径段被当成 base64 密钥
$ python main.py check-dataset quixbugs
# gold 修复版目录：/Users/<user>/.<REDACTED_KEY>  ← 诊断路径不可读（非泄露）
```

**根因**：`src/utils/logging_utils.py` 的"长 base64（≥40 位）"模式字符类
`[A-Za-z0-9+/=_-]` **含 `/`**，`.` 后连续路径段（≥40 字符）整体命中 → 只保留
前导 `/tmp/.` 其余替换为 `<REDACTED_KEY>`。

**修复**（`src/utils/logging_utils.py`，零 LLM）：
1. **边界锚定**：base64 模式起始前不得是字母数字或路径上下文
   `/ . _ ~ + -`，首字符不得为 `/`（避免从绝对路径中间开始匹配整段路径）；
2. **内容判定** `_redact_base64_like(match)`：候选含 `/` 且无 `+/=` → 路径形态
   原样返回；含 ≥2 个 `/` 或"全小写字母/数字/下划线"单级路径段 → 原样返回；
   含 `+`/`=` 结尾或混合大小写的真实 base64 密钥 → 仍脱敏；
3. 主路径与 fallback 路径共用同一模式（`_FALLBACK_PATTERNS` 派生关系不变）。

**修复前后对照**（证据 `before/after_check_dataset_over_redaction.log`）：

| 样本 | 修复前 | 修复后 |
|---|---|---|
| `/tmp/.cache/aitester/quixbugs/correct_python_programs` | `/tmp/.<REDACTED_KEY>` | 原样 |
| `/Users/u/.venv/bin/python` | `/Users/u/.venv/bin/<REDACTED_KEY>` | 原样 |
| `/var/folders/.../aitester_m1_bitcount_07q05sj_` | `/var/folders/.../<REDACTED_KEY>` | 原样 |
| `check-dataset quixbugs` gold 目录行 | `/Users/<user>/.<REDACTED_KEY>` | `/Users/<user>/.cache/aitester/quixbugs/correct_python_programs`（可读） |
| sk-/ghp_/AKIA/长 hex/长 base64/JWT 真密钥 | 已脱敏 | **仍全部脱敏**（正控） |

`repro_over_redaction.py` 可复跑：修复前 `VERDICT=FAIL(过度脱敏)`；修复后
`VERDICT=OK`（`OVER_REDACTED_LINES=0`，真实密钥族 5/5 仍脱敏）。

**回归锁**：`tests/test_n_round_platform_over_redaction.py`（**37 例**）：
5 条路径样本 × mask/fallback/redact_text/Filter+Formatter 五条路径零误伤、
`.env/.ssh/.venv` 路径段不整体误伤、混合行"路径保留 + 密钥脱敏"、39/40 位边界、
真实密钥族正控（sk/ghp_/AKIA/hex/base64/JWT/Bearer/大写凭证赋值）、跨路径一致性
守卫（`verify_redaction_consistency`）不回归、check-dataset CLI 端到端 gold 路径
可读（数据缺失时 skip）；`security-log-redaction` 探针新增"长路径零误伤"断言。

**附注（极小化既有测试更新）**：无——既有 `tests/test_logging_utils.py` /
`test_audit_log_redaction.py` / `test_credential_scrub.py` 全部零回归（实跑 221
passed）；仅探针模块内部 logger 调用点改为 `handler.handle(LogRecord)`（避免
审计门禁把"故意喂假密钥给脱敏层"的探针误报为未脱敏日志点，链路等价）。

## 4. 证据文件


| 文件 | 内容 |
|---|---|
| `zero_llm_report.json` / `.md` | 零 LLM 子集报告（21 pass / 4 skip，逐探针 evidence） |
| `llm_report.json` / `.md` | 全量含真 LLM 报告（25 pass；逐探针证据）。**注**：该报告为 D3 修复前一次运行（D3 为零 LLM 修复，LLM 探针结论不受影响）；零 LLM 报告已含 D3 后断言刷新 |
| `zero_llm_run.log` / `llm_run.log` | 零 LLM / 全量运行完整 stdout 日志（逐探针状态/耗时/明细） |
| `defect_executor_kernel_sandbox_wiring.log` | §3.2 **修复前**最小复现（passed=False / test_failure / execvp 拒绝 / allowed_paths） |
| `after_executor_kernel_sandbox_wiring.log` | §3.2 **修复后**同一复现（passed=True / coverage=100 / obs 放行面齐备） |
| `repro_safe_profile_e2e.py` / `safe_profile_e2e.log` | safe 档最小任务端到端（真实 LLM 1 次；执行器沙箱 + workflow 均 PASS） |
| `defect... / before_check_dataset_over_redaction.log` | §3.3 **修复前**复现（路径 `.<REDACTED_KEY>`、CLI gold 路径不可读、VERDICT=FAIL） |
| `after_check_dataset_over_redaction.log` | §3.3 **修复后**同一复现（路径原样、CLI gold 路径可读、VERDICT=OK、真实密钥 5/5 仍脱敏） |
| `repro_over_redaction.py` | D3 最小复现脚本（零 LLM；路径/密钥/CLI 三组断言，可复跑 before/after） |
| `SHA256SUMS` | 本目录完整性清单 |

## 5. 限制与风险（如实披露）

1. **并发**：本次 LLM 探针与 N-4 真 LLM 重探针在相邻时间窗运行；本模块调用均为
   最小 prompt/max_tokens，未观察到限流；运行器强制独立 cache namespace。
2. **LLM 成本口径**：报告 4 次调用（预算 29 tokens、缓存首调 29 tokens/avoided 29；
   RAG 生成 1437 字符、指纹 probe max_tokens=64）+ safe e2e 1 次（1026 tokens，
   in 391/out 635）。按 deepseek-flash 标准价上界估算合计 **< $0.01**（$0.2 预算内），
   非精确账单。
3. **沙箱内 hypothesis 告警**：`deny default` 下仓库根只读，hypothesis 插件默认
   数据库路径不可写 → 输出 `HypothesisWarning ... falling back to in-memory
   database`（设计内降级，不影响测试结果；未再放宽写面）。
4. **docker 探针**：本机无 docker CLI，断言明确降级；CI 有 docker CLI 时按零网络
   skip（不拉镜像）。
5. **Linux bwrap 路径**：本机 macOS 只实测 Seatbelt；bwrap 分支有单元测试覆盖
   argv 装配（`--ro-bind` exec/read、`--bind` write），未在本机真跑。
6. **D3 脱敏边界（残留）**：路径形态判定基于"含 `/` 且无 `+/=`、多级或全小写段"
   启发式；混合大小写的单级长目录名（无路径分隔符粘连）仍会被当 base64 脱敏
   （保守方向：宁可过杀也不漏真实密钥）；真实密钥族正控全部保持脱敏。
7. **沙箱策略边界**：exec/read 放行面以"解释器可运行最小集"为限（venv 根/
   framework 安装根只读、TMPDIR 读写、项目根只读）；未放行写仓库根、未放行
   `.env/.ssh/.aws/llm_configs.json` 读取（真实执行验证）。残余扩张面：
   framework 安装根整棵可执行（系统 Python 发行版，只读）。
