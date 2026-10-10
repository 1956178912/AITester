# scripts/ —— 门禁与工具脚本

本目录收纳仓库级独立脚本。按**是否作为阻断项**分为两层，新脚本请按下表归位。

| 目录 | 判定标准 | 退出码语义 |
| --- | --- | --- |
| `gates/` | 被 CI（`.github/workflows/`）、pre-commit（`.pre-commit-config.yaml`）、git hook（`.git-hooks/`）或 `make gates` 调用，**违规即阻断** | 非 0 = 仓库状态不合规，必须修 |
| `tools/` | 生成 / 运维 / 探测 / 实验辅助，**不承担阻断职责** | 非 0 = 本次操作失败，不代表仓库不合规 |

> 命名不是判定依据：`tools/check_quota.py` 虽以 `check_` 开头，但它是对 LLM 端点发探测请求的运维工具，不参与门禁；`tools/generate_static_report.py` 虽被 CI 调用，但产物是报告而非判定，故归 `tools/`。

## gates/（20 个）

CI / pre-commit 阻断项，`make gates` 跑其中大部分：

| 脚本 | 守卫内容 |
| --- | --- |
| `check_artifacts_tracked.py` | 报告引用的证据工件必须已 git 入库 |
| `check_baseline.py` | `BASELINE.yaml` 健全性 |
| `check_baseline_numbers.py` | 核心文档不得内嵌过期基线数字 |
| `check_bilingual_docs.py` | 中英文档配对 / 日期 / 章节对齐 |
| `check_branch_coverage.py` | 核心路由模块分支覆盖门槛 |
| `check_citations.py` | 文档引用真实性 |
| `check_credential_scrub.py` | 静态枚举与动态接口漂移 |
| `check_dependency_exemptions.py` | pip-audit 漏洞豁免登记 |
| `check_docs_history_drift.py` | 核心文档与 `docs/history/` 归档口径漂移 |
| `check_env_budget.py` | 环境变量开关预算棘轮 |
| `check_llm_configs_schema.py` | `llm_configs.json` schema |
| `check_lock_sync.py` | `requirements.txt` ↔ `requirements.lock` 双轨同步 |
| `check_perf_regression.py` | 性能基线回归 |
| `check_state_contract.py` | 未声明 state 键读写 |
| `check_swe_bench_pro_ready.py` | SWE-bench Pro 数据前置校验 |
| `check_tool_versions.py` | 工具版本三方一致（CI / pre-commit / lock） |
| `check_zero_assert_tests.py` | 零断言测试 / 裸异常捕获 |
| `checksum_results.py` | 主批次工件 SHA256SUMS 校验 |
| `coverage_ratchet.py` | 覆盖率渐进 ratchet 水位 |
| `audit_log_redaction.py` | 日志脱敏调用点扫描 |

## tools/（17 个）

| 脚本 | 用途 |
| --- | --- |
| `bootstrap_dev.sh` | 开发者环境一键搭建 / 校验 |
| `smoke_test.sh` | 发布前冒烟（含一次最小 LLM 调用） |
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
