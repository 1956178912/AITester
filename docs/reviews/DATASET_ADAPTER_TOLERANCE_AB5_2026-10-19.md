# AB-5：数据集适配层"分支不可达"前提核查与容错补锁（2026-10-19）

> 立项依据：`docs/reviews/FIX_COVERAGE_AUDIT_ROUND3_2026-10-19.md` §3.2 表格第三行
> 与 §4.3 ③——"**多数据集适配层**：本地只有部分数据集，其余分支不可达"，并把
> 补测前置条件写成"需先确认本地数据集可用性"。
> 本轮先核查这句前提，再据结论决定补锁还是登记。零 LLM、$0、未提交。

## 1. 前提核查：两句都要纠正

**(a) 本地数据其实基本齐备。** 实测 `~/.cache/aitester/`：

| 目录 | 内容 | 规模 |
| --- | --- | --- |
| `ult/ult_manifest.jsonl` | ULT manifest | 200 行 |
| `ult_repo/` | 官方仓库克隆（`datasets/`、`src/`、`Ray/`） | 存在 |
| `swe_bench/` | `swe_bench_instances.jsonl` | 225 行 |
| `swe_bench/swe_bench_{full,lite,mini,unknown}_instances.jsonl` | 子集文件 | **0 字节** |
| `quixbugs/` | `python_programs` / `correct_python_programs` / `python_testcases` | 存在 |
| `repo_envs/sqlfluff` | 仓库级执行环境 | 存在 |

所以"本地只有部分数据集"只对了一半：**主 manifest 在，缺的是子集文件**。

**(b) 但这条前提对本轮根本不重要——那 47 行没有一行真的需要数据集。**
逐行读源码后分类：47 行的主体是 `except SyntaxError` / `except json.JSONDecodeError` /
`if not line: continue` / 目录项过滤，它们缺的是**一份真的坏输入或畸形目录**，
不是网络、不是配额。在 `tmp_path` 里写出真实坏 JSONL、真实空 `.py`、真实非标识符文件名，
走的就是生产代码原路径——**这不是 mock**。

## 2. 47 行的最终归属（36 锁 / 9 登记）

覆盖口径：`make test-cov` 全量运行前后对账（`coverage.xml`，`hits="0"`）。

| 文件 | 轮前未覆盖 | 本轮被锁覆盖 | 仍登记 |
| --- | --- | --- | --- |
| `src/datasets/dataset_loader.py` | 19 | 10 | 9 |
| `src/datasets/dataset_realbugs.py` | 13 | 13 | 0 |
| `src/datasets/dataset_ult.py` | 15 | 15 | 0 |
| **合计** | **47** | **36** | **9** |

锁的落点（`tests/test_dataset_manifest_tolerance.py`，24 例）：

- **ULT**：数组形态 manifest 整体损坏→空数据集+warning；JSONL 坏行→跳过且 warning **带行号**；
  合法但非对象的记录（裸 `123`）→计入 skipped 而非 `AttributeError`；
  `tests` 双重编码为 JSON 字符串字面量→不得被逐字符展开成 gold 测试。
- **QuixBugs**：`.txt` / `_前缀` / 末段非标识符 / 空 `.py` 四类过滤，只留 1 个任务。
- **BugsInPy**：`data_dir` 直接指向 `.jsonl` 的显式文件口径；空行与坏行只作废自身。
- **SWE-bench**：`FAIL_TO_PASS` 三类畸形（list 含空串 / 非 JSON 串 / 类型不符）；
  截断 hunk 头；数据目录环境变量优先级（见 §3.3）。
- **补充文件**：坏 JSON 行跳过但其余照收、缺主键三类、路径缺失返回空映射。

## 3. 顺带产出的三项结论

### 3.1 一处真实行为缺口（已修）

`SWEBenchDataset._load_enrichment` 对 JSON 解析失败留了 warning，
对**缺 `instance_id` 的行完全静默**。后果可复现：补充文件用错键名（如 `id`）时
整份补充零生效，报表与日志都不区分"没配补充文件"和"配了但全废"——
这恰是本文件 docstring 主张要防的那类不可见代价。

处置：按行计数，结束时汇总**一条** warning（逐行刷屏会把真问题埋掉）：

```
补充文件有 3 行缺少 instance_id（已跳过）: /path/to/enrich.jsonl
```

返回值语义未变（`{instance_id: 字段}` 仍剔空值字段、保留主键），只补痕迹。
锁：`TestEnrichmentBadLineIsSkippedNotFatal::test_unusable_primary_key_rows_leave_one_bounded_trace`
同时断言"计数正确"和"只有 1 条"。

### 3.2 数据目录口径首次有锁

`SWEBenchDataset.__init__` 注释写着"Pro 数据集变量先于 rebench 泛化变量"，此前无锁。
`AITESTER_SWE_BENCH_PRO_DIR` 与 `SWE_BENCH_DATA_DIR` 同时设置时若顺序颠倒，
复测会读到一个任务都没有的子集目录——选错目录不报错，只是静默空跑。
现由 `TestSweBenchDataDirResolution` 双向钉住。

### 3.3 9 行登记为 not_evaluated（附机制，非"懒得补"）

| 位置 | 性质 | 为什么不补 |
| --- | --- | --- |
| `dataset_loader.py:69-70` | `except ImportError: _datasets = None` | 依赖环境分支：本机装了 `datasets` 包，该行在本机**永不触发**；补测需卸载依赖或子进程隔离，成本>价值。CI 侧由依赖矩阵自然覆盖。 |
| `dataset_loader.py:223` | ABC `_load_raw_data` 的 `raise NotImplementedError` | 构造上不可达：`ABCMeta` + `@abstractmethod` 已禁止实例化，子类全部覆写；直接调未绑定方法测的是 Python 语义而非本项目契约。 |
| `dataset_loader.py:377` | `paths.append(legacy)`（旧版通用文件名兼容） | 构造上不可达：`swe_bench_instances.jsonl` 本身满足 `startswith("swe_bench_") and endswith("_instances.jsonl")`，已在上方 glob 结果里，`legacy not in paths` 恒 False。**这是真冗余**，但删除属行为变更，留待单独轮次。 |
| `dataset_loader.py:563` | `if not os.path.exists(jsonl_path): continue` | 构造上不可达：`_resolve_jsonl_paths` 的返回值要么全部存在（listdir 派生 + legacy 存在性判定），要么全部不存在并由调用方在 546 行的 `not any(exists)` 早退，"混合存在"状态无法由公开 API 产生。 |
| `dataset_loader.py:974-977` | `if __name__ == "__main__":` 演示块 | 进程入口，pytest 内不可达。（同仓 `dataset_realbugs.py:283` 用 `# pragma: no cover` 消掉同类行；本轮**不加 pragma**，保持"登记而非掩盖"口径一致，是否统一两种写法留给下一轮决定。） |

另有一处**同类但不在本次范围**的缺口，登记为待办：
`scripts/gates/check_swe_bench_pro_ready.py:_load_enrichment_paths`（自称"与
`dataset_loader._load_enrichment` 同口径"）对坏行与无主键行**完全无痕迹**，
`enrichment_loaded` 只是布尔——部分行被丢时操作员仍看到"（已加载）"。
返回口径与生产代码一致，差异只在痕迹；本轮未动该文件（它是 G8 实验的数据前置门，
改动面超出"适配层"），留作下一项。

## 4. 三个"绿着但空转"的锁——本轮最实在的收获

写这 24 例的过程中，**变异检查抓出 3 条我自己写的空锁**：

1. **少一个换行**：坏行写成 `"这不是 JSON{{{\\n"`（字面反斜杠 + `n`），该行永不结束，
   下一条 `{"no_instance_id": 1}` 被拼进同一物理行、当成同一个坏 JSON 一起跳过——
   主键守卫**从未被执行**。表现为 `M4_enrichment_drops_primary_key_guard` 删掉守卫后 13 例全绿。
   修正：坏行显式以 `\n` 结尾，并补 null / 空串 / `0` 三类主键。
2. **用了合法的畸形输入**：截断 hunk 守卫用 `"@@ -1,2 +1,3 @@"` 触发不了——完整 hunk 头
   按 `@@` 切分本就是 **3 段**（尾段为空串），`len(parts) < 3` 恒 False。
   修正：改用真正截断的 `"@@ -1,2"`，`N12` 随即转红。
3. **守卫被兄弟分支吸收**：删掉空行守卫后，空行落进 `JSONDecodeError` 分支，
   任务数不变、warning 文案不变——只断言任务列表的锁看不见差异。
   修正：断言 **warning 条数**（ULT）与 **skipped 计数**（BugsInPy，空行不计入"无效记录"）。

判据就此收紧一次：**一条锁只有"删掉对应守卫必然转红"才算锁**。
本轮 2 批共 27 例变异（`M1–M13` 剔除被 `M12` 取代的 `M4`、`N1–N14`），
终态 **26 杀 / 1 由后继取代 / 0 存活**，源文件逐例做 sha256 还原校验。

## 5. 工件与验证入口

- `tests/test_dataset_manifest_tolerance.py`——24 例，全部 `tmp_path` 真实文件，
  不读 `~/.cache`、不联网、零 LLM。
- `src/datasets/dataset_loader.py`——`_load_enrichment` 无主键行汇总 warning（+7 行，返回值语义不变）。
- 变异驱动为一次性脚本（`/tmp`，不落仓）。

```bash
# 24 例 + 数据集回归面（254 例）
.venv/bin/python -m pytest -q tests/test_dataset_manifest_tolerance.py
.venv/bin/python -m pytest -q tests/test_dataset_manifest_tolerance.py \
  tests/test_dataset_validation.py tests/test_dataset_loader.py \
  tests/test_dataset_loader_extended.py tests/test_dataset_ult.py \
  tests/test_dataset_defects4j_edges.py tests/test_dataset_inmemory.py \
  tests/test_model_fingerprint.py tests/test_swe_bench_source_export.py \
  tests/test_g8_g2_g4_g5_g6_g7_g1.py

# 47 行归属复核（全量口径，hits="0" 计数）
make test-cov
```

## 6. 对外引用纪律

本轮可引用：**"多数据集适配层的坏输入容错分支已有 36 条变异验证锁，
9 条按机制登记为不可达"**。
本轮**不可**引用：任何"数据集质量已验证""SWE-bench Pro 就绪"类主张——
本轮只碰适配层容错面，未跑任何一批真实数据评测；
`swe_bench_lite` 仍为 0 字节，B3 的前置条件没有变化。
