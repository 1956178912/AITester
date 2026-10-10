# 外部数据集 QuixBugs：本地集成与还原（嵌套仓库注意事项）

> **本文只记"运维/集成"事项**：这个目录是什么、为什么不在仓库里、怎么还原、
> 哪些操作会造成损坏。
>
> 数据集的**用途、许可核实结论与定位降格声明**见
> [../DATA_CARD.md](../DATA_CARD.md) §4（此处不重复，避免两处口径漂移）。

## 一、现状（2026-10-10 实测）

| 项 | 值 |
|---|---|
| 路径 | `data/quixbugs/` |
| 上游 | <https://github.com/jkoppel/QuixBugs> |
| 本地 HEAD | `4257f44b0ff1181dedaedee6a447e133219fcebf`（2022-08-29，`Merge pull request #52 from h4iku/add-manual-run`） |
| 许可 | MIT（Copyright 2017-2019 James Koppel，见 `data/quixbugs/LICENSE`） |
| 文件数 | 410（不含内层 `.git/`） |
| 目录内容 | `python_programs/`（缺陷版）、`correct_python_programs/`（正确版）、`python_testcases/`、`java_*`、`json_testcases/`、`tester.py`、`build.gradle` 等 |
| 内层仓库 | **是** —— `data/quixbugs/.git/` 是一个**独立 git 仓库**，`origin` 指向上游 |
| 本仓库跟踪数 | **0**（被 [.gitignore](../../.gitignore) 的 `data/` 规则整体忽略） |
| `.gitmodules` | **不存在** —— 它不是 submodule，而是"归属未声明的嵌套克隆" |

## 二、三个必须知道的坑

### 1. 内层 `.git/` 不是 submodule，也不受本仓库管理

本仓库没有 `.gitmodules`，`git ls-files data/` 恒为 0，`git status` 不会递归进入
内层仓库——**内层仓库里的任何改动对本仓库完全不可见**。这既是安全网（误改不会污染
本仓库），也是陷阱（改了被测程序却不自知，会让实验失去可复现性）。

### 2. 数据集不在仓库里 —— 新克隆后该目录不存在

`.gitignore` 的 `data/` 规则意味着 `git clone` 之后 `data/quixbugs/` **不会存在**。
依赖它的实验请先按 §三 还原；`src/datasets/dataset_realbugs.py` 在数据缺失时会抛出
带指引的错误（`QuixBugs 数据未找到…请克隆 https://github.com/jkoppel/QuixBugs`）。

### 3. 路径不会被自动发现 —— 必须显式指向

`QuixBugsDataset` 的默认数据目录是 `~/.cache/aitester/quixbugs/`，**不是**仓库内的
`data/quixbugs/`。要用仓库内这份克隆，须显式设置环境变量（与
[docs/preregistration.md](../preregistration.md) 中 E4 就绪命令同口径，
`tests/test_aj_batch.py` 锁定该字符串）：

```bash
export AITESTER_QUIXBUGS_DATA=data/quixbugs
```

### 危险操作清单

| 操作 | 后果 |
|---|---|
| `git add -f data/quixbugs` | 410 个上游文件涌入索引；若一并加入内层 `.git/`，会形成 gitlink 混乱，且引入与本研究无关的第三方历史 |
| `rm -rf data/quixbugs/.git` | 丢失来源标识与 HEAD 可达性，此后无法核对"用的是哪个上游版本" |
| `git clean -xfd` | 数据集被删（**可再生产**，按 §三 还原即可，不影响仓库内容） |
| 直接编辑 `python_programs/*.py` | 内层仓库改动对本仓库不可见，实验可复现性静默失效 |

## 三、还原 / 重建

```bash
# 场景 A：目录整体丢失
git clone https://github.com/jkoppel/QuixBugs data/quixbugs
git -C data/quixbugs checkout 4257f44b0ff1181dedaedee6a447e133219fcebf

# 场景 B：目录在、内层 .git 被误删（只需恢复来源标识）
cd data/quixbugs
git init
git remote add origin https://github.com/jkoppel/QuixBugs
git fetch origin
git checkout 4257f44b0ff1181dedaedee6a447e133219fcebf
```

**为什么固定到 `4257f44` 而不是跟随 `main`**：E4 / R4 批次的 QuixBugs 工件已入库并受
`SHA256SUMS` 保护，实验结果的可复现性依赖**被测程序字节不变**。跟随上游 `main`
会让"同一 task_id"在不同时间指向不同代码。

## 四、核对（全部只读）

```bash
git -C data/quixbugs rev-parse HEAD                        # 期望 4257f44b0ff1181dedaedee6a447e133219fcebf
find data/quixbugs -type f -not -path '*/.git/*' | wc -l   # 期望 410
git ls-files data | wc -l                                  # 期望 0（本仓库不跟踪）
git check-ignore -v data/quixbugs                          # 期望命中 .gitignore 的 data/ 规则
```

---
*最后更新：2026-10-10（目录治理批次新增）。*
