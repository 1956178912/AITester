# scripts/ —— 门禁与工具脚本

本目录收纳仓库级独立脚本。按**是否作为阻断项**分为两层，新脚本请按下表归位。

| 目录 | 判定标准 | 退出码语义 |
| --- | --- | --- |
| `gates/` | 被 CI（`.github/workflows/`）、pre-commit（`.pre-commit-config.yaml`）、git hook（`.git-hooks/`）或 `make gates` 调用，**违规即阻断** | 非 0 = 仓库状态不合规，必须修 |
| `tools/` | 生成 / 运维 / 探测 / 实验辅助，**不承担阻断职责** | 非 0 = 本次操作失败，不代表仓库不合规 |

> 命名不是判定依据：`tools/check_quota.py` 虽以 `check_` 开头，但它是对 LLM 端点发探测请求的运维工具，不参与门禁；`tools/generate_static_report.py` 虽被 CI 调用，但产物是报告而非判定，故归 `tools/`。

## gates/（36 个）

CI / pre-commit 阻断项，`make gates` 跑其中大部分：

| 脚本 | 守卫内容 |
| --- | --- |
| `check_artifact_doc_consistency.py` | 报告→工件数值对账（mutation×detection 表 / T-10 匹配子集声明 / 登记册覆盖率） |
| `check_artifacts_tracked.py` | 报告引用的证据工件必须已 git 入库 |
| `check_ast_parse_guards.py` | ast.parse 守卫捕获面棘轮（新增单腿守卫 = 抛穿 ValueError 族） |
| `check_baseline.py` | `BASELINE.yaml` 健全性 |
| `check_baseline_numbers.py` | 核心文档不得内嵌过期基线数字 |
| `check_bilingual_docs.py` | 中英文档配对 / 日期 / 章节对齐 |
| `check_branch_coverage.py` | 核心路由模块分支覆盖门槛 |
| `check_citations.py` | 文档引用真实性 |
| `check_credential_scrub.py` | 静态枚举与动态接口漂移 |
| `check_dependency_exemptions.py` | pip-audit 漏洞豁免登记 |
| `check_doc_commands.py` | 文档引用的 `scripts/….py` 路径与 `make <target>` 目标必须真实存在 |
| `check_doc_links.py` | 文档相对链接 / 行锚 / 标题锚点静态完整性 |
| `check_docs_history_drift.py` | 核心文档与 `docs/history/` 归档口径漂移 |
| `check_env_budget.py` | 环境变量开关预算棘轮 |
| `check_env_snapshot_keys.py` | 环境开关 provenance 快照完备性 |
| `check_flag_effect.py` | 门禁开关有效性对账（dest 活性：传了却不改变行为的死开关判红） |
| `check_invocation_caliber.py` | 门禁调用口径对账（同一道门在 `make` 链与各 workflow 是否以同一口径在跑） |
| `check_json_contract_sites.py` | JSON 契约调用点计数一致性 |
| `check_json_strict.py` | 工件严格 JSON（RFC 8259，拒绝裸 `NaN`/`Infinity`）+ 源码写入点 `allow_nan=False` |
| `check_llm_configs_schema.py` | `llm_configs.json` schema |
| `check_lock_sync.py` | `requirements.txt` ↔ `requirements.lock` 双轨同步 |
| `check_model_fingerprint.py` | 模型版本指纹锁定 |
| `check_perf_regression.py` | 性能基线回归 |
| `check_prompt_artifacts.py` | Instruction artifact 清单哈希锁 |
| `check_registration_consistency.py` | 登记册 §1「当前口径」数字 ↔ `BASELINE.yaml` 双向对账 |
| `check_repo_hygiene.py` | 仓库卫生：临时/缓存产物不得被 git 跟踪 + 本清单与盘面一致 |
| `check_release_freshness.py` | 发布新鲜度：最新 release tag 不得落在 main 后面（落后须登记例外） |
| `check_scheduled_workflows.py` | 远端定时作业巡检：每周跑一次的作业最近一次必须非红（定时红 + 更新的成功手动运行 ⇒ 绿） |
| `check_state_contract.py` | 未声明 state 键读写 |
| `check_status_persistence.py` | 状态通道落盘可达性棘轮（声明了却不落盘 = 归档里 0 出现） |
| `check_swe_bench_pro_ready.py` | SWE-bench Pro 数据前置校验 |
| `check_tool_versions.py` | 工具版本三方一致（CI / pre-commit / lock） |
| `check_zero_assert_tests.py` | 零断言测试 / 裸异常捕获 |
| `checksum_results.py` | 主批次工件 SHA256SUMS 校验 |
| `coverage_ratchet.py` | 覆盖率渐进 ratchet 水位 |
| `audit_log_redaction.py` | 日志脱敏调用点扫描 |

## tools/（30 个：27 个 `.py` + 3 个 `.sh`）

| 脚本 | 用途 |
| --- | --- |
| `bootstrap_dev.sh` | 开发者环境一键搭建 / 校验 |
| `smoke_test.sh` | 发布前冒烟（含一次最小 LLM 调用） |
| `build_paper.sh` | 投稿 PDF 构建（**先跑判据 → 再编译 → 再跑判据**；CZ 轮起） |
| `check_quota.py` | LLM 端点额度 / 存活探测 |
| `compare_executor_modes.py` | 执行模式对比 |
| `download_swe_bench.py` | SWE-bench 数据下载 |
| `expand_models.py` | 模型目录扩展 |
| `export_swe_bench_source.py` | 按 base_commit 导出基准源码 |
| `generate_batch_config.py` | 批量 LLM 配置脚本生成（由 `src/config/config_generator.py` 写入本目录） |
| `generate_static_report.py` | 静态报告生成（CI 调用，产物非判定） |
| `list_env_flags.py` | 环境变量开关清单 |
| `performance_benchmark.py` | 性能基准（perf.yml 调用） |
| `performance_profile.py` | cProfile / tracemalloc 剖析 |
| `power_analysis.py` | 统计功效分析（`make self-check`） |
| `run_standardized_experiments.py` | 标准化实验入口 |
| `verify_instance_solvable.py` | SWE-bench 实例可解性校验 |
| `verify_swe_bench_export.py` | 源码导出结果校验 |
| `verify_synthetic_templates.py` | 合成模板三重不变量自验证 |
| `audit_paper_numbers.py` | 论文数字 `// SRC:` 与工件对账（`make paper-audit`；paper/ 为本地件） |
| `audit_fix_coverage.py` | 修复覆盖率缺口审计：找出「修复新增但从未被测试执行」的代码行（`make fix-coverage`；基线默认 auto） |
| `check_doc_commands.py` | 文档命令可执行性门禁：文档引用的脚本与 `make` 目标必须存在（`make doc-commands`） |
| `export_paper_citation_keys.py` | 论文外部读数引用键快照生成 / 校验（`make paper-citation-keys`；paper/ 为本地件，缺失时明确失败） |
| `convert_ult_manifest.py` | ULT 官方 manifest 转换 / 适配 |
| `detect_orphan_procs.py` | 孤儿嵌套测试进程巡检（`make proc-hygiene`；preflight 阻断项） |
| `e2e_probe.py` | 全功能端到端探针运行器（`make e2e-probe` / `make e2e-probe-llm`） |
| `e2e_probes_logic.py` | logic 通道与 DSL 相关探针组 |
| `e2e_probes_platform.py` | 平台 / 沙箱 / 执行器探针组 |
| `e2e_probes_workflow.py` | 工作流 / 可观测性探针组 |
| `refresh_patch_field.py` | 存量批次 `patch` 字段重放刷新 |
| `run_arm_with_cap.py` | 单臂跑批 + 预算 / 调用上限包装 |
| `run_logic_ab.py` | logic 档 A/B 快捷入口 |
| `run_logic_channel_ab.sh` | logic 通道 A/B shell 入口 |
| `run_preflight.py` | 批次跑批前置闸（配额 / 指纹 / 工作树 / 孤儿；`make preflight`） |
| `self_mutation.py` | 项目自身测试套件变异测试（`make self-mutation` / `make self-mutation-ci`） |

## 维护约定

**1. 仓库根解析**：本目录脚本位于仓库根下**两级**（`scripts/<层>/<脚本>`），因此：

```python
# Python：仓库根 = parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 等价写法：Path(__file__).resolve().parent.parent.parent
# os.path 风格：os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Shell：仓库根 = 脚本目录的 ../..
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
```

`scripts/` 与两个子目录均**不含 `__init__.py`**（隐式命名空间包）。测试通过
`importlib.util.spec_from_file_location` 或 `from scripts.gates.<mod> import ...`
加载；新增脚本请沿用该约定，不要添加 `__init__.py`。

**2. 改动脚本路径时**：调用点分布在 CI workflow、`Makefile`、`.pre-commit-config.yaml`、
`.git-hooks/`、文档与 `tests/`（多处用 `PROJECT_ROOT / "scripts" / ...` 拼接或
`sys.path.insert` 注入目录）。移动脚本必须同步这些调用点，否则门禁静默失效。
