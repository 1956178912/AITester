# AITester 使用示例

最后更新：2026-10-26 · English: [usage_examples.en.md](usage_examples.en.md)

六个常用场景，命令均可直接运行。数字口径以 [BASELINE.yaml](../BASELINE.yaml) 为准，本文不
内嵌会漂移的计数。

## 1. 跑通测试套件

```bash
python3 -m venv .venv && source .venv/bin/activate
make install
make test
```

`make test` 与 CI 同口径（xdist `-n 4 --dist loadfile`）。自检环境与功能探针（零 LLM）：

```bash
python3 main.py doctor
python3 main.py doctor --json
```

`doctor` 不消耗 API 配额；`--strict` 在出现警告或跳过时返回非零；参数用法错误（`--groups`
为空或未知分组）返回 2。功能矩阵依赖源码检出的 `scripts/tools/e2e_probe.py`，wheel 安装面
仅报告 `unavailable`，环境检查不受影响。

## 2. 零 LLM 复算

基于已入库工件重算指标，不需要 API Key：

```bash
make reproduce-zero-llm
make reproduce-zero-llm-l1
```

L0 覆盖统计扩展、mutation × detection 交叉验证、SWE-bench 披露、引用核验与 SHA256SUMS
校验；L1 追加 QuixBugs 全量 Mut@k（小时级）。结果为 `ok` / `FAILED` / `skipped` 三态：
源工件已撤回的支路打印 `[SKIP]`，**跳过不等于通过**。报告写入
`experiments/results/REPRODUCTION_REPORT.md`（运行为产、不入库）。

## 3. 单任务修复前检查

先跑一个内置示例，确认链路可用：

```bash
python3 main.py run examples/calculator.py --func divide
python3 main.py run examples/buggy_library.py --func binary_search
python3 main.py run examples/calculator.py --json
```

批量跑批前执行前置闸（配额、模型指纹、工作树、孤儿进程；零 LLM）：

```bash
make preflight
```

需要真实 LLM 的单批复现见 [REPLICATION.md](../REPLICATION.md) 的 `reproduce.sh` 路径。

## 4. 变异评估

自身测试套件的变异测试（零 LLM，默认抽样 3 个核心模块）：

```bash
make self-mutation
make self-mutation-ci
```

`self-mutation-ci` 是 CI 门禁口径（`env_utils` + `atomic_io`，阈值 0.85）。基准跑批中如需
变异评分，显式设置 `ENABLE_MUTATION_SCORING=true`（默认关闭）。mutation × detection 的
交叉验证报告由零 LLM 链的 L0 生成。

## 5. 修复覆盖率审计

```bash
make test-cov
make fix-coverage
```

`make test-cov` 运行全量测试并写 `coverage.xml`；`make fix-coverage` 审计「修复逻辑新增但
从未被测试执行」的代码行，基线默认取最近一次改动 `src/` 的提交。覆盖率读数与门槛登记在
[BASELINE.yaml](../BASELINE.yaml) 与
[PROJECT_STATUS_REGISTER.md](PROJECT_STATUS_REGISTER.md) §1。

## 6. 文档与门禁自检

```bash
make docs-check
make doc-commands
make gates
```

- `docs-check`：双语文档配对、更新日期同步、内部链接完整性（strict，CI 阻断）。
- `doc-commands`：文档中引用的 `scripts/*.py` 与 `make <target>` 必须真实存在。
- `gates`：本地全部门禁单链执行；合并前自检用它，不要并行叠加。

只改文档时至少跑前三者中的 `docs-check` 与 `doc-commands`；改代码后跑 `gates`。门禁读数
统一回填 `BASELINE.yaml`，不要写在文档正文里。
