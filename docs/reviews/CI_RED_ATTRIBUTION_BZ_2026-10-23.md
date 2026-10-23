# BZ 轮：CI 历史三族红的归因与修复——测试契约工件入库、三类前提缺失显式 skip、依赖升级清零 45 漏洞（零 LLM，$0）

登记日 2026-10-23；实测自 2026-10-23（本机 macOS，Python 3.14.6，pytest 9.1.1）。
归因对象 = GitHub Actions run `39905189493`（head `5eb51607`，BV 轮推送）及其历史
（`39437924646` @ AE 轮 `388dbf9f`、`39268356717` @ 10-19 定时自变异，均 failure；
最后一个绿色 push run 是 10-19 06:24 的 X 轮 `39209706724`）。

## 1. 发现：三族红，三种完全不同的根因

run `39905189493` 的 8 个作业里 3 红 1 取消（Docker build / E2E probes /
Smoke LLM / SBOM 全绿）：

| 红 | 位置 | 根因（归因后） |
|---|---|---|
| test (3.12) / test (3.13) | 步骤 "Run tests with coverage (parallel)" | **29 例测试引用的归档工件被 `.gitignore` 排除** ⇒ fresh clone 里 FileNotFoundError；另有语料面下界 / 历史切点 / 双盲文件 / 跨平台 libm 四类前提缺失（合计 32 例，见 §2） |
| test (3.14) | 作业 30min 超时（cancelled） | 失败后的"测试失败诊断"步骤重跑整轮套件，与测试步骤串联后慢 runner 上超帽；非独立缺陷 |
| Security (blocking) | 步骤 "Check transitive dependencies for vulnerabilities (P1-7 lock 全量审计)" | **45 个未豁免漏洞**（pillow 35 / aiohttp 8 / certifi 1 / opentelemetry-api 1），全部有上游修复版 |

三条归因路径（都不需要 admin 权限）：

1. **失败清单逐字取自 check-run 注解 API**：ci.yml 的诊断步骤把失败用例写成
   `::error` 注解，公开可读（`/check-runs/{id}/annotations`）——3.12 与 3.13 的
   名单**逐字一致**，直接排除 Python 版本因素。注意该名单被 `head -30` 截断，
   真实数是 32（见 §2）。
2. **fresh clone 模拟**：本地 `git clone --depth 1`（复刻 actions/checkout 的
   shallow 语义）+ CI 同套环境变量（`LLM_1_*` mock + `COVERAGE_FILE` 隔离），
   首轮复现 **31 例**，与远端名单逐条对应；本地全量绿只因工件在盘（4129 个
   被忽略文件）——"逻辑有测试、工件没入库"的镜像面。
3. **pip-audit 本地复现**：沙箱网络恢复后同版本（2.10.1）同豁免清单复跑
   `-r requirements.lock`，`Found 45 known vulnerabilities, ignored 5 in 4 packages`，
   退出码 1——与 CI 步骤失败逐字同形。

## 2. 处置：五类分开修，一类一种形态

### 2.1 契约工件入库（17 例；408 个文件 / 5.9 MB）

这 17 例把具体归档文件/目录写进契约（pinned 批次、损坏 trace 目录、逐位复现的
报告），此前全部被 `experiments/results/**` 排除。按 main_batch / r4_batches /
e6_a1_batches 同口径**逐层放行**（`!dir/` 放行目录 → `dir/**` 压回内容 → 按名
放行目标；gitignore 规范：父目录被排除时内层 negation 永久失效——`.gitignore`
U1 注释的同一教训，本轮在 `cross_file_ab_level3` 等深层路径上又踩一次），并把
`experiments/results/emse_*/`（目录排除）窄化为 `emse_*/**`（内容排除）让
negation 可达。重产物主体（246 份批次 JSON 共 92.6 MB）仍走 Zenodo，不入库。

入库清单（按测试契约）：2 个顶层 `benchmark_examples_*.json`、
`cross_file_ab_level3/cross_file_off/traces`（100）、
`emse_stats_2026-10-15` 报告两份、`emse_t08_gates_20261013` 与
`emse_ult_dfsmoke_20261017` 各 1 个 pinned 批次、
`llm_logic_ab_20261010_202129/c1`+`c3` 两个 pinned 批次、
`pilot_mdo_full50` 1 个、`rag_ab_synthetic` 全子树（43）、
`rag_lvl25h_n40` 全子树（83）、`rag_lvl25h_n40_g8batch/traces`（80）、
`spec_ab_quixbugs_20261012/replace` 1 个、
`spec_ab_scale87_20261012/ult_lite46_off/traces`（92）。

**AST 普查漏采的教训**：首轮按"字符串字面量含 `experiments/results/`"采集，
漏掉 `DET1_ROWS` 式不带前缀的相对路径 ⇒ 二轮验证剩 9 红时才补入 2 个文件
（emse_t08_gates / llm_logic_ab c1）。**普查脚本必须同时覆盖两种路径写法，
且必须以失败清单（实况）闭环，不能以普查集合（期望）闭环。**

### 2.2 语料面普查改显式 skip（8 例）

这 8 例的扫描面下界以**全归档**校准（246 份 `benchmark_*.json` / 138 个
`traces*` 目录 / 8539 个 trace 文件 / 129058 个 span），fresh clone 只有入库
子集（107/246、84/138、6759/8539）⇒ 新增 `tests/_corpus_guard.py`（单一事实源）
的 `require_full_corpus()`：低于实测下界时 `pytest.skip` 且理由带三个实测读数。
覆盖 effective_green 1、arm_row_collapse 2、mast_nonobject 1、otel_aq 2、
otel_ar 1、token_ax 1。**首轮误分类**：这些例首轮失败形态是 FileNotFoundError，
被当成文件缺失族；文件到场后计数下界才暴露——**同一测试可以先后属于两类，
归因必须以最终失败形态为准**。

### 2.3 历史切点对账改显式 skip（4 例）

`_profile_drift(old_rev, new_rev)` 对两个历史 rev 跑 `git show <rev>:config.py`；
shallow clone（fetch-depth=1）里必败 ⇒ ab11 两例、ab12 两例（报告/README 复现锁
内嵌该对账）改 `require_history(rev)`：rev 不在对象库时 skip 并点名缺哪个 rev。
顺带把两个 rev 提为生产模块常量 `PROFILE_DRIFT_OLD/NEW_REV`（原为报告生成与
ab11 测试两处手抄），三处消费者共用单一事实源。

### 2.4 双盲纪律不入库的文件改具名 skip（2 例）

`paper/draft.typ`（.gitignore:119-120）与
`docs/study/SUBMISSION_SKELETON_2026-10-16.md`（:124）按学术文件纪律
**有意**不入库——这两例不可能靠入库修复，改为缺席时 skip 并点名 .gitignore 行号
与纪律名。与 2.2/2.3 同口径：不折叠成通过，也不折叠成失败。

### 2.5 跨平台 libm 末位容差（1 例，仅 CI 红）

`test_non_tied_case_matches_exact_enumeration` 对非 0.5 精确二项断言
`abs=0.0`（逐位相等）。非 0.5 分支走 `lgamma`/`log`/`exp` 的 logsumexp，
macOS Accelerate 与 Linux glibc 末位可差 1–2 ULP ⇒ CI 3.12/3.13 红、macOS 绿
（fresh clone 在 macOS 上复现不出这一例）。改 `rel=1e-12`，与同族
`test_emse_stats_extensions.py:109`（p=0.1）同口径；p=0.5 整数权重分支与全并列
早退（1.0）**保持 abs=0.0**——那些值精确可表示，不承担 libm 敏感性。

### 2.6 依赖升级（Security 族）

pip-audit 的 45 个漏洞全部有上游修复 ⇒ 按 ci.yml 既定治理（"一旦发布修复版本，
应升级并移除对应 --ignore-vuln"）升级而非登记豁免：

| 包 | 锁内旧版 | 新版 | 漏洞数 |
|---|---|---|---|
| pillow | 12.3.0 | 13.0.0 | 35 |
| aiohttp | 3.14.3 | 3.14.4 | 8 |
| certifi | 2026.7.22 | 2026.10.19 | 1 |
| opentelemetry-api | 1.44.0 | 1.45.1 | 1 |
| opentelemetry-sdk / -proto / -exporter-otlp-proto-{common,grpc} | 1.44.0 | 1.45.1 | （家族同版，pip 联动） |
| opentelemetry-semantic-conventions | 0.65b0 | 0.66b1 | （1.45.1 的依赖） |
| opentelemetry-exporter-otlp-common | —（新增） | 0.66b1 | （1.45.1 exporter 的新传递依赖） |
| yarl | 1.24.5 | 1.25.1 | （aiohttp 3.14.4 的依赖） |

`requirements.lock` 132 → 133 条（外科式增量，不用 `pip freeze` 全量重生成——
venv 含 185 个包、与锁的 132 条本就有既有漂移，全量重生成会把漂移一起写进锁）。
chromadb 的 5 条 PYSEC 豁免**不动**（上游仍无修复版，登记表治理不变）。
兼容性核查：新钉版 `requires_python`（pillow ≥3.11 / otel ≥3.10）不排除 CI 矩阵
的 3.12/3.13/3.14；cp312 wheel 实测可下载（`pip download --python-version 3.12`）。

### 2.7 CI 超时上限

test 作业 `timeout-minutes` 30 → 60：3.14 档撞帽被 cancel 的直接原因是失败后
诊断重跑（整轮套件 `--tb=no -rf`）与测试步骤串联；本轮修复后失败路径不再触发，
但上限必须覆盖"失败 + 重跑"的最长路径。

## 3. 验证

### 3.1 fresh clone 三轮闭环（CI 模拟）

| 轮次 | HEAD | 结果 |
|---|---|---|
| 1（修复前） | 1022c63b | **31 failed** / 12436 passed / 32 skipped |
| 2（BZ 一） | e02824dd | **9 failed** / 12450 passed / 40 skipped |
| 3（BZ 二） | ee258bff | **0 failed** / 12453 passed / 46 skipped |

口径：`git clone --depth 1` + `LLM_1_*` mock + `COVERAGE_FILE` 隔离 +
`-n 4 --dist loadfile`。第三轮 skip 理由逐条核过（`-rs`）：8 条语料面
（`benchmark_*.json 107/246、traces* 目录 84/138、trace 文件 6759/8539`）、
4 条历史切点（`b533cff1c316 不在场（shallow clone…）`）、2 条双盲文件
（点名 .gitignore:119 / :124）——**全部具名带读数，零静默 skip**。
3.12/3.13 失败名单逐字一致已证非版本因素；3.14 的超时随失败路径消失。

### 3.2 pip-audit

升级后同命令复跑：`No known vulnerabilities found, 5 ignored`，退出码 0
（5 = chromadb 登记豁免，治理不变）。

### 3.3 本地全量与门禁

- 全量套件（升级后 venv）：**12480 passed / 19 skipped / 0 failed、204.16s**
  （沙箱口径；正常口径 12494 / 5 / 0，与升级前逐位相同——pillow 13 / otel 1.45 /
  aiohttp 3.14.4 零回归）。
- `make gates` 全链在最终提交的干净树复跑（读数见收口提交）。
- 受影响测试文件本地 158 passed（守卫在全量环境为无操作，行为与本轮之前逐位相同）。

## 4. 复现

```bash
# A. 失败清单（公开 API，无需 admin）
curl -s "https://api.github.com/repos/1956178912/AITester/actions/runs/39905189493/jobs?per_page=50"
curl -s "https://api.github.com/repos/1956178912/AITester/check-runs/120255420398/annotations?per_page=50"

# B. fresh clone 模拟（CI 同口径）
git clone --depth 1 file:///Users/wangchenyu/Workspace/AITester /tmp/ci_sim
cd /tmp/ci_sim && LLM_1_API_KEY=test-key LLM_1_BASE_URL=https://test.example.com \
  LLM_1_MODEL_NAME=test-model COVERAGE_FILE=/tmp/cov/.coverage.ci \
  /path/to/.venv/bin/python -m pytest tests/ -n 4 --dist loadfile -q --tb=line -rf

# C. pip-audit（lock 全量审计，CI Security 作业同命令）
pip-audit -r requirements.lock \
  --ignore-vuln PYSEC-2026-311 --ignore-vuln PYSEC-2026-3813 \
  --ignore-vuln PYSEC-2026-3814 --ignore-vuln PYSEC-2026-3815
```

## 5. 未做 / 边界

- **重产物主体仍不入库**：246 份批次 JSON（92.6 MB）按 Zenodo 纪律留在库外；
  依赖它们的 8 例语料面普查在 fresh clone 上显式 skip（理由带读数），只在完整
  语料环境（作者机 / 复现包解包后）执行。CI 绿 ≠ 这些锁在 CI 执行过。
- **shallow clone 的历史对账不上 CI**：4 例历史切点锁同理；没有改
  actions/checkout 的 fetch-depth（全历史克隆成本与收益不成比例）。
- **论文与投稿骨架仍不入库**（双盲纪律）：2 例引用锁只在作者环境执行。
- **`pytest.approx` 的跨平台语义只修了暴露的一例**：非 0.5 分支还有
  `test_emse_stats_extensions.py:109`（p=0.1）用 rel=1e-12（CI 绿），本轮把
  br_round 那例对齐到同一口径；没有全仓审计所有浮点断言的 abs=0.0。
- **venv 与 lock 的既有漂移未处理**：venv 实装 185 包 vs lock 132 条（typer
  0.25.1 vs 0.27.1 等，dist-info 时间戳证明早于本轮）；本轮只做外科式增量。
  "本地全量绿"与"CI 装锁后绿"之间仍隔着一层未登记的漂移，留后续轮次对账。
- **README「已知失败」行的 CI 声明曾有近一周失实**：该行写 "CI 3.12/3.13/3.14
  全绿"，而 10-19 以来 push run 全红——本轮修复 + 推送 + 远端转绿后该声明
  才恢复为真；失实窗口（10-19 ~ 10-23）登记于此，不悄悄抹平。

## 6. 本轮自纠

| # | 自纠项 | 说明 |
|---|---|---|
| ① | **AST 普查漏采不带前缀的路径写法** | `DET1_ROWS` 用 `"emse_t08_gates_20261013/benchmark_….json"`（无 `experiments/results/` 前缀），首轮采集条件漏掉 ⇒ 二轮验证剩 9 红才补 2 个文件。修法：二轮按失败清单逐条提取路径；**普查必须两种写法都覆盖，闭环必须以实况（失败清单）为准**。 |
| ② | **浅层 negation 永久失效又踩一次** | `results/**` 连中间目录一起排除，`!deep/path/file` 不生效；必须 `!dir/` + `dir/**` + 按名放行逐层做（main_batch 惯例）。首版 negation 写了 12 条全部落空，`git check-ignore` 逐条验过才提交。 |
| ③ | **误分类：FileNotFoundError 掩盖了计数下界** | otel/token 四例首轮因文件缺失红，入库后改为计数下界红（129058 / 27000 / 9086 / 34）——它们是语料面族不是文件族。**归因必须看最终失败形态，同一测试可先后属两类。** |
| ④ | **json-strict 门禁被自己入库的工件打破** | 406 个入库工件里 3 个是 AB-11/AB-12「损坏通道」语料（测试契约锁定的坏行文件）⇒ 门禁红。修法：按档内登记口径加 3 条豁免（归档工件不重写），豁免漂移检查随之覆盖。**入库动作本身会激活此前不可达的门禁面。** |
| ⑤ | **pip 全量安装被沙箱杀死（exit 137）** | 一次装 9 个包（含 pillow 大 wheel）被 OOM/kill；改 broker 变量 unset + 分批安装成功。残留 `~dist-info` 目录已清。 |
| ⑥ | **pip freeze 不能用来重生成锁** | venv 185 包 vs lock 132 条（既有漂移），全量 freeze 会把 Authlib/GitPython/cosmic_ray 等 53 个开发工具写进锁。修法：只应用 10 条升级 + 1 条新增的外科式增量，并逐条核对。 |
| ⑦ | **CI 失败名单被 head -30 截断** | 诊断步骤的注解只带前 30 条，真实数 32（br_round 那例在第 31 位之外？不——首条即是；截断丢掉的是 1 条 macOS 复现不出的 libm 例）。**读注解名单要当作下界，不能当作全集**；缺口由 fresh clone 模拟补齐。 |
