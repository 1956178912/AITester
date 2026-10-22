# BS 轮：覆盖率口径写进配置（`branch = true`）+ 基线复算（零 LLM，$0）

## 1. 发现

文档与 CI 都要求覆盖率按 `pytest --cov=src --cov-branch ...` 跑，但仓库**没有
`[tool.coverage]` 配置**——分支口径只由 CLI 开关携带。实测（2026-10-22，收口
HEAD `645046eb`，macOS 3.14.6）：

```
pytest tests/ -q --cov=src --cov-branch --cov-report=xml -n 4 --dist loadfile
...
coverage.exceptions.DataError: Can't combine branch coverage data with statement data
```

数据文件实证：

| 文件 | line_bits | arc |
|---|---:|---:|
| `.coverage`（控制进程） | 1 | 0 |
| `.coverage.*`（4 个 xdist worker） | 0 | 2438 / 13157 / 23076 / 22076 / 23136 |

即：**同一个 `--cov-branch` 命令行，控制进程写了语句口径数据，worker 写了分支
口径数据**，combine 阶段两者不能合并，整轮覆盖率不可得（`coverage.xml` 停在
上一轮）。这不只是本地问题：任何"非 CLI 入口"（xdist 控制器、子进程、`coverage
run` 直接调用）都拿不到该开关，口径取决于谁先写盘。

## 2. 处置

`pyproject.toml` 新增：

```toml
[tool.coverage.run]
branch = true
```

再加 1 例锁（`tests/test_packaging.py::test_coverage_branch_mode_is_pinned_in_config`）：
解析 TOML，断言 `tool.coverage.run.branch is True`，失败信息写明"非 CLI 入口会写
语句口径数据，覆盖率无法合并"。选 `test_packaging.py` 是因为该文件已是
"pyproject 契约"的落点（依赖分组 / setup.py 对齐），不新开主题文件。

边界：CI 本来就传 `--cov-branch`，读数不变；本项只让**所有入口**（含本地
`-n 4`、子进程）落到同一口径，并让"配置被删"从"跑挂才知道"变成"测试即红"。

## 3. 复算（CI 口径，同一命令；沙箱 19 skip）

| 指标 | 本轮 | BQ 轮 | 差 |
|---|---:|---:|---|
| 行覆盖 | **19526/20040 = 97.4351%**（97.44） | 19393/19904 = 97.4327% | +133 / +136 行，未覆盖 511 → **514** |
| 分支覆盖 | **7148/7582 = 94.2759%**（94.28） | 7103/7532 = 94.3043% | +45 / +50 弧，缺弧 429 → **434** |

棘轮（`coverage_ratchet.py --check`）：行 97.44 ≥ 96.40（余量 1.04pp）、分支
94.28 ≥ 92.50（余量 1.78pp），**rc=0**；`check_branch_coverage.py` 门槛达标。
**水位不上调**：AA-4（2026-10-19）规定水位必须取 CI ubuntu 3.14 口径，本地
macOS 余量（1.04/1.78pp > 0.5pp 步长）只算"满足上调条件"，不得据此写回。

逐模块（按同一份 `coverage.xml` 复算，只列变动项）：

| 模块 | 本轮 | 上一登记 | 说明 |
|---|---|---|---|
| `agents/base_agent.py` | **399/405 = 98.52%**（branch 133/136 = 97.79%） | 401/407 = 98.53% | BR 轮预算记账 + 缓存作用域改动面；缺行 6 |
| `graph/nodes.py` | **864/865 = 99.88%**（branch 331/334 = 99.10%） | 852/853 = 99.88% | 探针 backend 接线 +12 行；仍 1 行未覆盖 |
| `graph/state.py` | **126/126 = 100.00%**（branch 2/2） | 125/125 = 100% | 源文件本轮未改；按当前 `coverage.xml` 登记，不追认上一读数（分母差 1 的成因未查明，不强行归因） |
| 其余 10 项 | 与 BK/BJ 登记逐位相同 | — | 本轮未触碰其代码面 |

## 4. 复现

```bash
find . -maxdepth 1 -name '.coverage*' -delete   # 清并行数据（zsh 下勿用裸 glob）
.venv/bin/python3 -m pytest tests/ -q --cov=src --cov-branch --cov-report=xml \
  --cov-report=term -n 4 --dist loadfile --basetemp=/tmp/pt_bs_cov
.venv/bin/python3 scripts/gates/coverage_ratchet.py --check
```

## 5. 未做

- 未在 CI ubuntu 上实跑；水位沿用 96.40/92.50，不上调（AA-4）。
- 未回填历史轮次的覆盖率读数——本轮只对当前 `coverage.xml` 负责。
- 全量计数：collected **12070** = passed **12065** + skipped 5 + failed 0
  （规范口径）；沙箱确认跑 **12051 passed / 19 skipped / 0 failed、202.70s、rc=0**。
