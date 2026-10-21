# AZ 轮：统计定义口径修正与工件重发（2026-10-21，零 LLM）

**范围**：`experiments/emse_stats_extensions.py` 的两处统计定义——

- `cohens_g`：配对 McNemar 不一致对的效应量；
- `binom_exact_two_sided`：二项精确双尾 p（McNemar 精确检验的唯一实现路径）。

**结论**：两处实现都与函数名/文档声称的口径不一致。`cohens_g` 返回的是
**2g**（范围 0–1），不是 Cohen's g（范围 0–0.5）；`binom_exact_two_sided`
对 `p=0.5` 走浮点 `pmf <= prob_k + 1e-12`，epsilon 把小到 1e-34 的尾部
整条收进分子，把 **1.926e-34 抬成 ~1.93e-12**。处置后真批次读数：
R-P0-2 aitester vs df **g 0.370 / p 1.716e-13**（原 0.739 / 1.073e-12）、
df vs plain LLM **g 0.500 / p 1.926e-34**（原 1.000 / 1.931e-12）、
E6 **g 0.423**（原 0.846）、E4 **g 0.500**（原 1.000，p 不变）。
受保护归档 `emse_stats_extensions_20261016/` 零改写（sha256 复验 OK），
修正值重发到 `emse_stats_extensions_20261021/`。
**21 例新锁 + 变异 M1 11 红 / M2 4 红 + 0 逃逸**；确认跑
**11222 passed / 5 skipped / 0 failed、187.56s、rc=0**。**未提交。**

---

## 1. 缺陷定义

### 1.1 `cohens_g` 返回 2g

改前：

```python
return abs(n10 - n01) / (n10 + n01)
```

effectsize 的标准口径是先把不一致对归一为 `P = max(b,c)/(b+c)`，再取
`g = P − 0.5`，展开即 `|b−c| / (2*(b+c))`，范围 0–0.5。改前实现缺了
分母的 2，返回的是 **2g**，范围 0–1。后果不是数值噪声，而是**量纲
错位**：论文与报告把 0.739 当 Cohen's g 引用，读者按标准 g 的 0–0.5
刻度理解，会把效应量高估一倍；同一批数据在 `g=1.0` 处还会被误读为
"完全一边倒"（标准 g 的上界只能到 0.5）。

### 1.2 `binom_exact_two_sided` 的 epsilon 抬升

改前对 `p=0.5`：

```python
probs = [math.comb(n, i) / 2**n for i in range(n + 1)]
return min(1.0, sum(x for x in probs if x <= probs[k] + 1e-12))
```

`1e-12` 容差的初衷是吸收浮点比较误差，但对极端尾它会把**整条低于
容差的尾部**一起收进分子：

| 读数 | 改前 | 改后 |
|---|---|---|
| 12/80 | 1.073374741074801e-12 | **1.715599535972955e-13** |
| 113/0 | 1.93144963207924e-12 | **1.925929944387236e-34** |
| 2/24 | 1.049041748046875e-05 | 同左（不在 epsilon 域） |
| 0/14 | 0.0001220703125 | 同左（不在 epsilon 域） |

113/0 是决定性反例：真实双尾概率是 `2 × 0.5^113 = 2^-112 ≈ 1.926e-34`，
改前报 ~1.93e-12——**抬高了 22 个数量级**。这不是"保守"或"更严"，
而是把一个几乎不可能的观测报成了"在 1e-12 量级上仍可能"。

### 1.3 同一缺陷族

两处都属于**统计量的定义与声称不一致**：一个量纲错位，一个尾部被
数值容差改写。它们进入论文/报告的路径相同（`build_report` → JSON →
README → 论文引用），因此作为同一轮收口。

## 2. 真批次测量（只读）

输入为已归档原始工件（零 LLM、零网络、纯 stdlib）：

| 对比 | n10 | n01 | 旧 g | 新 g | 旧 p | 新 p |
|---|---|---|---|---|---|---|
| R-P0-2 aitester vs df | 12 | 80 | 0.7391304347826086 | **0.3695652173913043** | 1.073374741074801e-12 | **1.715599535972955e-13** |
| R-P0-2 df vs plain LLM | 113 | 0 | 1.0 | **0.5** | 1.93144963207924e-12 | **1.925929944387236e-34** |
| E6 aitester vs df | 2 | 24 | 0.8461538461538461 | **0.4230769230769231** | 1.049041748046875e-05 | 同左 |
| E4 aitester vs df | 0 | 14 | 1.0 | **0.5** | 0.0001220703125 | 同左 |

方向与显著性判读不变（四组都仍显著，g 仍为正），但**幅度与极端性
必须按新值引用**。新 g 精确满足 effectsize 恒等式
`max(b,c)/(b+c) − 0.5`，且严格 ≤ 0.5。

## 3. 处置

### 3.1 公式与精确尾

```python
def cohens_g(n10: int, n01: int) -> float:
    total = n10 + n01
    if total == 0:
        return 0.0
    return abs(n10 - n01) / (2 * total)
```

`p=0.5` 分支不再走浮点比较，改用整数权重 `math.comb(n, i)` 做精确
`<=` 比较，最后除以 `2**n`：

```python
weights = [math.comb(n, i) for i in range(n + 1)]
cutoff = weights[k]
return min(1.0, sum(w for w in weights if w <= cutoff) / 2**n)
```

整数比较没有 epsilon，因此极端尾不会被"抹平"；`p != 0.5` 分支保留
概率序双侧（累加所有 `pmf(i) <= pmf(k)` 的结局），并与对称情形使用
同一套定义。

### 3.2 受保护归档不重写，修正值重发

`emse_stats_extensions_20261016/` 受 `SHA256SUMS` 保护，按纪律**原地
零改动**：`STATS_EXTENSIONS.json` sha256 `785edd76…56f021`、
`README.md` sha256 `9762d9ae…cd85599` 均与归档一致（测试逐字节锁定）。
修正值写入新目录 `emse_stats_extensions_20261021/`（README + JSON +
SHA256SUMS），并在其中显式标注旧值为 2g / epsilon 抬升值。默认输出
目录改为新目录；`scripts/reproduce_zero_llm.py` 的 `_CHECKSUM_DIRS`
同时校验两代目录，历史归档仍可复验。

### 3.3 引用传播

| 位置 | 处置 |
|---|---|
| `paper/draft.typ` | `g = 0.739` → **0.370** |
| `docs/study/SUBMISSION_SKELETON_2026-10-16.md` | 区间 `0.74–1.00` → **0.37–0.50**；`0.739` → **0.370**；工件路径改指 20261021，并注明旧值为 2g |
| `experiments/results/REPLICATION_PACKAGE.md` | 统计工件行改指 20261021（旧值保留在 20261016） |
| `docs/reviews/X_ROUND_ZERO_LLM_VERIFICATION_2026-10-19.md` | **只追加** AZ 勘误：该行 0.7391 是 2g，不是 Cliff's δ；标准 g = 0.369565 |
| `scripts/gates/check_artifacts_tracked.py` | MANIFEST 增补 20261021 三件；20261016 条目保留为历史 |
| `tests/test_aq_batch.py` | MANIFEST 长度锁 185 → 188（数量随清单增长） |
| `tests/test_experiments_cache_caliber_aj.py` | 归档对照改为"除已登记轮次增量外逐字段相等"，并把旧/新 g 与 p 作为差值断言 |

## 4. 回归锁

`tests/test_emse_stats_definition_az.py`：6 个测试类，**17 例**。
`tests/test_emse_stats_extensions.py` 净增 **4 例**（g 恒等式 / g 上界 /
epsilon 尾部 / 非 0.5 概率序）。

| 类 | 例数 | 覆盖 |
|---|---|---|
| `TestRealBatchReadings` | 5 | 四组真批次 (g, p) 精确读数 + `g <= 0.5` 全域上界 |
| `TestProtectedArchive` | 2 | 20261016 两文件 sha256 与归档逐字节一致 |
| `TestReissuedArtifact` | 4 | 默认输出目录 / JSON 与 `build_report` 一致 / SHA256SUMS 自校验 / README 表格单元格 |
| `TestReproduceWiring` | 1 | `reproduce_zero_llm` 同时登记两代目录 |
| `TestRendererCaliber` | 2 | 渲染口径行声明标准 g 与无 epsilon 精确尾 |
| `TestCitationPropagation` | 3 | 论文 g=0.370、EMSE 骨架区间、X 轮勘误只追加 |

## 5. 变异验证

两个真实锚点；逐锚点：写入变异 → `compile()` → 跑目标集 →
sha256 原字节还原（绝不用 `git checkout` / `git stash`）。基线
**107 passed**，collected 恒 **107**，还原后中性对照 **107 passed**。

| 锚点 | 变异 | 红数 |
|---|---|---|
| M1-cohens-g-2g | `cohens_g` 分母回退 `/ total`（2g） | **11** |
| M2-binom-epsilon-floor | 对半概率回退浮点比较 + `1e-12` 容差 | **4** |

M1 的 11 红覆盖：扩展文件 4 例（已知值 / 单侧 / 恒等式 / 上界）、AZ 锁
5 例（四组真读数 + 上界）、AJ 归档对照 1 例、重发件 JSON 一致性 1 例。
M2 的 4 红覆盖：扩展文件 epsilon 尾部 1 例、AZ 真读数 113/0 1 例、
重发件 JSON 1 例、AJ 归档对照 1 例。**0 逃逸**；还原后源文件
sha256 `79c4e1e4…8dc7fd` 逐字节一致。

## 6. 收口读数

- 登记前一跑（带 `--cov`）：**11221 passed / 1 failed / 5 skipped、
  196.47s**；collected **11227**；唯一失败 = BASELINE 数字守卫（仍写
  11201，实收 − 声明 = 21 > 6 容差）。
- 覆盖率（`coverage.xml` root 口径）：**19002 / 19528 行 = 97.3064%**、
  **6960 / 7396 弧 = 94.1049%**；未覆盖 **526** 行、缺弧 **436**。
  较 AY **−1 行 / −1 弧**，落在既有 ±2 行抖动域；本轮 `src/` 零改动，
  改动面在 `experiments/` + 测试 + 文档，覆盖率分母不测 experiments。
- 十项核心模块：**0 项变动**（base_agent 98.53、api_manager 99.24、
  dataset_loader 97.28、graph_nodes 99.88、code_analyzer 99.38、planner
  99.09、dependency 96.26、multi_candidate 98.67、cross_file 92.98、
  rag_retriever 98.10）；核心路由三项分支逐位不变（graph_workflow 99.17、
  error_classifier 96.49、graph_state 100.00）。
- 确认跑（刷新 BASELINE 后）：**11222 passed / 5 skipped / 0 failed、
  187.56s、rc=0**（collected 11227）。
- 门禁（单独跑 `make gates`，不与其他命令重叠）：**rc=0**；墙钟
  **193s**；链内 pytest **11222 passed / 5 skipped / 0 failed、
  187.84s**（13 warnings；collected 11227）；`ruff check` All checks
  passed、`ruff format --check .` **932 files**、mypy **135** 源文件、
  双语文档 0 警告 / 0 失败、文档链接 strict **168 份 / 711 条 / 0 错误
  0 警告**、env-budget 253/253、状态通道 134 文件、env-snapshot 84/84、
  tool-versions OK、JSON 契约 7/7、JSON strict **7274 工件 0 违规 /
  300 源文件 0 写入点违规**、报告↔工件对账 [OK]、零断言 **444 文件 /
  0 违规**。

## 7. 边界（不得引用为「全部统计口径已修正」）

1. **只改两处实现**：`experiments/emse_stats_extensions.py` 的
   `cohens_g` 与 `binom_exact_two_sided`。`experiments/emse_optimization.py`
   的 `mcnemar_exact_p` 是独立实现且本就使用整数权重，未改动。
2. **历史工件保留旧值**：20261016 归档按 `SHA256SUMS` 原样保留；
   引用旧目录的读者仍会看到 0.739 / 1.93e-12，必须按 20261021 或
   本文件勘误理解。
3. **只修正已登记的四个对比**：其它批次若曾调用旧函数，其历史读数
   仍是 2g / 抬升 p；本轮不做全仓历史回填，后续引用应重新复算。
4. **非 0.5 分支未被 McNemar 使用**：该分支的概率序定义有独立测试，
   但生产路径当前只以 `p=0.5` 调用；不得据此声称"任意 p 的检验已
   在论文场景验证"。
5. **未调用 `--write` 重写归档**：受保护工件零改动，本轮只新增
   20261021 目录并暂存（未提交）。

## 8. 复算命令

```bash
# 目标锁（17 + 22 collected）
.venv/bin/python -m pytest tests/test_emse_stats_definition_az.py \
  tests/test_emse_stats_extensions.py -q

# 受影响面（AJ 归档对照 + AQ 清单 + 工件守卫）
.venv/bin/python -m pytest tests/test_experiments_cache_caliber_aj.py \
  tests/test_aq_batch.py tests/test_artifacts_tracked_gate.py -q

# 工件自校验（两代目录）
(cd experiments/results/emse_stats_extensions_20261016 && shasum -a 256 -c SHA256SUMS)
(cd experiments/results/emse_stats_extensions_20261021 && shasum -a 256 -c SHA256SUMS)

# 全量 + 覆盖率（CI 同口径；不与 make gates 重叠）
make test-cov

# 确认跑（BASELINE 刷新后）
make test

# 门禁（最后单独跑，绝不与其他命令重叠）
make gates
```
