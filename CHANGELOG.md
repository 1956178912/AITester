# 更新日志

> 最后更新：2026-10-26

本文件只记录对外可见的变化；逐轮历史见下方归档。

## [Unreleased]

### Added
- 依赖漏洞豁免过期守卫（DF 轮）：`make dependency-audit` 与 CI 阻断步骤真实跑一次
  **不带** `--ignore-vuln` 的 pip-audit——登记条目出现修复版本、新 advisory 未登记、
  登记版本与 `requirements.lock` 漂移即红；豁免理由「仅嵌入式、无服务器面、
  无 `trust_remote_code`」由 `src/` 静态扫描锁定；离线按 `[SKIP]` 披露，
  CI 的 `--require-audit` 把「无法验证」判红（37 例测试锁）。

### Changed
- 重算论文引用键快照（DG 轮）：稿件在快照生成后被外部改动，按
  `scripts/tools/export_paper_citation_keys.py` 重算 `docs/study/PAPER_CITATION_KEYS.md`
  （64 行，其中 6 行的形态计数随生成器修复而变化），快照与读者链测试全绿。
- 重建投稿 PDF（DE 轮）：70 页、`refs.bib` 79 条 ↔ 79 个 `\bibitem`、0 未定义引用；
  `docs/study/PAPER_BUILD.md` 与 `paper/tex/README.md` 的旧页数/条数读数按实测刷新。
- 文档门面重写（DD 轮）：README / QUICKSTART / CONTRIBUTING / MODEL_CARD /
  REPLICATION / docs 核心改为简洁结构，中英同步；旧叙事归档到 `docs/history/`。
- 文档测试锁改为结构判据（定位区 / 披露小节 / 行数上限 / 索引完备性），
  退役逐轮标记与行窗口锁。

### Fixed
- 失败追踪导出的参数与并发落点不再失真（DX 轮）：`limit=0` 曾静默导出全部快照、负数反向切片；
  同一秒内的多次 / 并发导出又共用文件名、后写覆盖先写。现在 0 / 负数抛 `ValueError`，`O_EXCL` + 序号重试、绝不覆盖旧快照。11 例新锁。
- `--dump-trace-on-failure` 的失败态不再静默或反噬任务（DW 轮）：目录创建失败曾把已完成任务改写成崩溃，
  无快照 / 写盘失败又静默。现在三态可区分（`trace_dump_path` / `trace_dump_error` + stderr 原因），崩溃任务同样尝试导出。9 例新锁。
- `doctor` 的 `dataset-check-cli` 探针不再要求已移除的文本（DV 轮）：QuixBugs 现在输出「共加载 N 个任务」+
  「未提供 quality_report，跳过全量校验」，旧探针把能力缺失报成故障；现接受「通过 / 显式跳过」（缺失即红）。净增 4 例（探针共 6 条）。
- `check-dataset` 查出加载问题不再报成功（DU 轮）：报告非空时只打 warning、退出码仍为 0，与「0 = 无问题」相反；
  现在报告非空逐项列出并以 1 退出，能力缺失与源码待导出仍为披露；QuixBugs 探针接受「经校验通过 / 显式跳过」。11 例新锁。
- `doctor --json` 的三条出口现在共用 13 键 schema（DT 轮）：内部异常只输出 4 个键、正常 12 个，
  `jq -e '.conclusion == "pass"'` 在崩溃时取不到键。现在崩溃时 `matrix.status` 记 `internal`、
  未采集的聚合记 `null`（未知 ≠ 全 0）、脱敏原因进 `error` 并以 1 退出。13 例新锁。
- 任务崩溃的结果面不再与成功路径不同构（DS 轮）：崩溃结果只有 5 个键、成功有 14 个，`jq '.coverage_ok'` 在崩溃任务上取不到键，
  人读模式把缺键兜底画成「迭代 0」、原因只进日志。现在两条路径共用全部键（未知判定显式 `null`、成功结果带 `error: null`），
  原因写 stderr、迭代列显示 `N/A`；崩溃结果 dict 让状态通道 update dict 重登记为 47 键 / 99 站点。9 例新锁。
- `run --func` / `check-dataset --subset` 不再把显式空值当作「未提供」（DR 轮）：脚本里
  `--func "$FUNC"` / `--subset "$SUBSET"` 变量未展开时 click 收到 `""`，按 falsy 判定
  等于悄悄放宽口径——`check-dataset examples --subset ""` 实测输出「（子集: 全部）」并
  rc=0，`run … --func ""` 把空串原样交给任务（按函数数消耗 LLM）。现在两者都按用法错误
  rc=2 在加载数据 / 启动任务之前拒绝；省略选项才是「全部」口径。8 例新锁。
- `check-dataset` 的状态图标只有一个来源（DQ 轮）：`info_msg` / `warning_msg` 等助手已自带
  `ℹ ` / `⚠ ` 前缀，六个调用点又手写图标，实测输出 `ℹ   ✓ 加载质量健康`，警告路径会是
  `⚠ ⚠ …`；三处成功事实（单个任务健康 / 全量质量通过 / 源码完整）还用蓝 `ℹ` 冒充成功。
  现在图标由助手唯一提供，成功事实改用 `success_msg`（绿 `✓`），并以 AST 结构锁约束
  `src/` 全部助手调用不得自带图标。15 例新锁。
- `run` 不再把目录当任务、也不再重复执行同一文件（DP 轮）：显式目录 / 特殊文件被
  `glob.glob` 原样收下，任务在 `open()` 处抛 `IsADirectoryError` 后被记成「任务失败」
  （rc=1），用法问题伪装成测试没过；同一文件经显式与通配符重复命中时会重复进入工作流、
  重复消耗 LLM。现在目录 / 特殊文件与「通配符只匹配到目录」按用法错误 rc=2 在启动前
  拒绝，重复目标按绝对路径去重、只跑一次。11 例新锁。
- `run` 的帮助与文档不再宣称不存在的报告面（DO 轮）：help 不再泄漏 rich/Markdown 标记
  （`[bold]…`、`**…**`）；detection / repair / false_fix 改述为基准评估面
  （`experiments/_m1_metrics.py`，需要 gold 材料）并以「不在 CLI 输出中」披露；模块地图
  不再把 M1 记在 `src/measurement/`；批次摘要新增覆盖率三态（达标/未达标/不可测），
  `run --help` 与 api_reference 写明阈值不改变退出码。16 例新锁。
- `check-dataset --subset` 不再静默忽略或静默替换（DN 轮）：内置示例、QuixBugs、BugsInPy、
  Defects4J、synthetic 等数据集没有子集概念，此前传 `--subset lite` 仍 rc=0 并输出
  「（子集: lite）」，实际加载的是全量数据（`check-dataset quixbugs --subset lite` 实测照载
  50 个任务）；ULT 请求 `lite` 而 `ULT_Lite.jsonl` 缺失、或 `AITESTER_ULT_DATA` 指向显式
  文件时，也同样静默回退却照称已校验子集。现在：不支持子集的数据集与未知子集名按用法错误
  rc=2 拒绝（提示由 `dataset_subset_support` 能力表派生，新增数据集只改能力表）；请求的子集
  未生效时 rc=1 并披露回退原因；子集真正生效时仍 rc=0 且只加载子集文件。
  `load_dataset` 的程序化契约不变（`subset` 仍被接受，ULT 回退行为保留并新增
  `subset_fallback_reason` 记录）。14 例真实 CLI/加载器测试锁，先红后绿。
- `clean-venv-cache` 的报告不再与磁盘现实脱节（DM 轮）：`shutil.rmtree(..., ignore_errors=True)`
  会吞掉一切删除失败，紧随其后的 `except OSError` 是死分支——实测把缓存目录设为只读后，
  命令仍打印「✓ 已删除 1 个 venv（释放 0.0 MB）」且 rc=0，目录原封不动（旧测试用
  `MagicMock` 让 rmtree 主动抛异常，锁住的是 mock 形态而非真实行为）。现在按目录是否真的
  消失区分 `removed` / `failed`，失败逐项报告并以 rc=1 结束，释放空间只累计真正删掉的目录，
  释放空间不再虚报。同时 `--list-only` 此前静默忽略 `--max-age-days` / `--max-size-mb`，
  预览列出全部条目；现在与清理复用同一判定，输出 `[将删除]` / `[保留]`，预览名单与实删
  名单同源（8 例真实文件系统测试锁，先红后绿；旧 mock 锁按新契约改写）。
- `check-dataset` 不再把「没有校验器」报成通过（DL 轮）：`quality_report` 只有 SWE-bench
  系列实现，其他数据集（内置示例、QuixBugs、ULT 等）此前走 `report = {}` 的空分支，输出
  「✓ 全量质量检查通过（N 个任务无加载问题）」——N 可能远大于 `--limit` 实际展示的任务数，
  全量校验从未发生；`tasks_missing_source` 缺失时则完全静默，读者会误以为「无缺失源码」。
  现在两种能力缺失都显式披露「未提供 …，跳过」（退出码仍为 0，与 `doctor` 的 unavailable
  不计失败同口径）；实现了 `quality_report` 且返回空报告时仍输出经过校验的通过结论
  （5 例测试锁，先红后绿）。
- CLI 用法错误与运行失败的退出码不再混淆（DK 轮）：诊断命令 `check-dataset` 此前对未知
  数据集名静默降级为内置示例并报「全量质量检查通过」（rc=0），`--limit -5` 走 Python 负切片
  取尾部，加载异常只打印错误仍 rc=0，数据未就位（加载到 0 个任务）同样报通过；`run` 无有效
  目标或数值选项非法返回 1，与「任务失败」无法区分；`clean-venv-cache --max-age-days -5`
  的负数过滤在删除逻辑里恒真（`age_days > -5`），实测 rc=0 且删光全部缓存。现在用法错误
  统一 rc=2（未知数据集名并列出合法名单、负 `--limit`、负缓存过滤、空目标、
  `--coverage-threshold=nan`），运行失败 rc=1（加载异常 / 0 个任务），`0` 过滤保持
  「全部过期」的显式语义。数据集名单改由模块级注册表派生（新增
  `normalize_dataset_name` 与 `_DATASET_REGISTRY`，消除手工平行名单的漂移面）；工厂
  `load_dataset` 对未知名称仍按契约降级为内置示例（21 例测试锁，先红后绿）。
- `doctor` 用法错误与安装面不可用不再伪装成系统故障（DJ 轮）：拼错分组名或
  `--groups` 解析为空原本都报 `matrix.status="error"`（或静默跑满全量矩阵）；
  pip 安装的 wheel 因不含 `scripts/tools/e2e_probe.py` 使 `aitester doctor`
  恒红且不可行动。现在探针框架对未知 `--group`/`--name` 在过滤前报错并列出
  合法值（rc=2）；`doctor` 把子进程 rc=2 映射为 `usage`（退出码 2，不伪造
  error 行）、脚本缺件映射为 `unavailable`（不计失败，`--strict` 下退 1），
  空 `--groups` 直接走用法错误路径且不采集检查/不跑矩阵（10 例测试锁，先红后绿）。
- 门禁链子进程全部带超时预算（DI 轮）：10 处 `subprocess` 调用缺 `timeout`——git 锁、
  ruff、mypy 与 pytest 收集任一挂起都会让 `make gates` / CI 无限挂起（没有读数、
  没有失败行，只有被平台上限回收的作业）。补齐预算并钉死超时语义：登记面对账超时
  抛 `RuntimeError` 判红（返回 `None` 会被读成 `[SKIP]` 静默放行）、基线收集降级为
  `None`、仓库卫生抛 `RuntimeError`、工件门合成 rc=124、静态快照记
  `(124, 超时)`；删除 `check_invocation_caliber` 的死 helper；AST 结构锁覆盖
  `scripts/gates/*.py` 与两个工具脚本（7 例，先红后绿）。
- CI 作业预算补齐（DH 轮）：`ci.yml` 的 `smoke-llm` 是唯一没有 `timeout-minutes`
  的作业——LLM 端点挂起时会被平台默认的 360 分钟兜底回收；补 15 分钟预算，并新增
  `tests/test_ci_job_timeouts.py` 锁全部 workflow 作业的预算声明与 (0,60] 值域
  （3 例，先红后绿）。
- 引用键快照生成器漏计多键引用（DG 轮）：`render_snapshot` 按单键正则统计
  `\citep` / `\citet` 形态，正文 `\citep{a,b}` 组内的键被漏计——读者链判据实测
  `konstantinou2026icst` 快照合计 3 / 正文 4。真实稿件 4 个多键组、9 个键位，旧逻辑
  低估 6 个受管键（konstantinou2026icst / arna2026icstw / radaideh2026bdai /
  zuppardo2026beyondaccuracy / curmi2026harnessmatter / sghaier2026harnesshierarchy）；
  改为按组拆分计数，1 例测试锁先红后绿。
- 可选嵌入后端加载失败必须降级（DG 轮）：`src/utils/embedding_utils.py` 的
  sentence-transformers 分支此前只捕获 `ImportError`，模型下载失败 / 缓存损坏等
  非 ImportError 会击穿「不可用即 None」契约，`embed_text()` 直接向调用方抛异常
  （codebert / chromadb 两分支均捕获 `Exception` 降级）；现补同形降级并在显式
  选择该后端时告警，3 例测试锁先红后绿。
- 注释语义按文件类型分治（DE 轮）：TeX `%` 按反斜杠奇偶、Typst `//` 与可嵌套块注释、
  BibTeX 按括号深度且 `\"` 不切换字符串态；修复 `refs.bib` 注释被误算进上一条目字段值造成的假 CJK 红。
- 论文构建脚本前置判据改为 `--pre-build`：只跳过产物页数对账，源侧判据照常阻断，
  避免「编辑源文件后无法重建」的自锁。
- 外部读数登记册更正 `wang2026harnessreeval` 为 arXiv v4 并补齐 v1–v4 版本史；
  两处强否定改为「所核摘要与正文未见」。

## [1.0.0] - 2026-10-25

### Added
- 复现包 `REPLICATION.md`、`REPRODUCE_SKIP_TESTS` 显式逃生口与零 LLM 复算链。
- 发布判据 ADR-0036；发布新鲜度守卫。

### Changed
- repair 读数采用修正口径 v2（39.31%，57/145 可重放行，gold 独立裁决）；
  历史口径见 `docs/design/repair_caliber_matrix.md`。
- 模型调用默认关闭 thinking、默认开启 JSON 模式（ADR-0031）。

### Fixed
- 修复 `repair=0` 两起测量伪影：patch 字段围栏残留、跨文件任务未物化。
- 文档命令可执行性、引用库可编译性等门禁补链。

### Security
- 敏感/私有路径纳入仓库卫生门禁；`.env*` 与私有目录不得被跟踪。
- git 历史存量泄漏处置见 `docs/security/history_leak_remediation_runbook.md`。

## 更早版本

0.8 / 0.9 系列与更早的逐轮记录见归档（原样保留，链接不保证可达）：

| 归档 | 内容 |
|---|---|
| [README_2026-10-26_full.md](docs/history/README_2026-10-26_full.md) | 重写前 README（中文） |
| [README_2026-10-26_full.en.md](docs/history/README_2026-10-26_full.en.md) | 重写前 README（英文） |
| [CHANGELOG_2026-10-26_full.md](docs/history/CHANGELOG_2026-10-26_full.md) | 重写前 CHANGELOG（中文） |
| [CHANGELOG_2026-10-26_full.en.md](docs/history/CHANGELOG_2026-10-26_full.en.md) | 重写前 CHANGELOG（英文） |
