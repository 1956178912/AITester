# 更新日志归档（2026-10-27，FC 轮）：[Unreleased] 的 DI–DL 四轮逐条记录

> 这四轮的条目自 2026-10-27 起从 `CHANGELOG.md` 的 `[Unreleased]` 节移出（**原文逐字保留，未删改**），
> 目的是给简洁度棘轮（`tests/test_doc_concision.py`：CHANGELOG.md ≤ 160 行）留出余量，
> 同时让门面只保留近期轮次。英文版见 [CHANGELOG_2026-10-27_batches.en.md](CHANGELOG_2026-10-27_batches.en.md)。

## 归档条目（DI–DL 轮）

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
- 门禁链子进程全部带超时预算（DI 轮）：10 处 `subprocess` 调用缺 `timeout`——git 锁、ruff、mypy 与 pytest 收集任一挂起都会让 `make gates` / CI 无限挂起（没有读数、没有失败行，只有被平台上限回收的作业）。
  补齐预算并钉死超时语义：登记面对账超时抛 `RuntimeError` 判红（返回 `None` 会被读成 `[SKIP]` 静默放行）、基线收集降级为 `None`、仓库卫生抛 `RuntimeError`、工件门合成 rc=124、静态快照记 `(124, 超时)`；
  删除 `check_invocation_caliber` 的死 helper；AST 结构锁覆盖 `scripts/gates/*.py` 与两个工具脚本（7 例，先红后绿）。
