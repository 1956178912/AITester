# AF 轮：JSON 落盘收口到 RFC 8259（2026-10-20，零 LLM）

**范围**：AE 评审 §5.6（全仓非严格 JSON 工件且无门禁）与 §5.7（`run_b8._write_json` 的
`allow_nan=True`）合并处置，并同时修正 AE §5.6 对本仓工件的一处计量误读。

**结论**：仓内所有受控 JSON/JSONL 落盘路径改为 fail-closed 严格序列化；新增全仓门禁
`scripts/gates/check_json_strict.py` 并接入 `make gates` 与 CI。**本轮没有重写任何入库工件**
（2 份 A20 历史截断轨迹按原字节保留、逐路径豁免）。28 例回归锁 + **9/9 变异锚点转红**。

---

## 1. 缺陷定义

Python `json.dumps` 默认 `allow_nan=True`，把 `float("nan")` / `±inf` 写成裸
`NaN` / `Infinity` / `-Infinity`。这不是 RFC 8259 合法 JSON：

- Python 自己的 `json.loads` 默认能读回（`parse_constant` 未设置时）；
- jq / Go `encoding/json` / Rust serde_json / JavaScript `JSON.parse` 会拒绝；
- 后果是**生产端静默写出、消费端读不动**，且中间没有任何失败信号。

本轮前置复现（改前）：

| 写入口 | 输入 | 改前落盘 |
|---|---|---|
| `src/utils/atomic_io.atomic_write_json` | `{"v": nan}` | `{"v": NaN}` |
| `experiments/run_b8_injection._write_json` | `{"cost": inf}` | `{"cost": Infinity}` |
| `TraceSession.record_node` | `output={"duration_ms": nan}` | 单行 JSONL 含裸 `NaN` |

## 2. 修复

### 2.1 严格序列化原语

新增 `src/utils/json_strict.py`：

- `nonfinite_pointers(obj)`：递归定位 NaN/±Infinity（含 dict 键），返回 JSON 路径
  （如 `$.arms[1].cost`、`$.x[<key nan>]`）；共享容器与自引用容器不重复/不挂死。
- `strict_json_dumps(...)`：有非有限值 → 抛 `NonFiniteJSONError`（带路径与总处数）；
  否则 `json.dumps(..., allow_nan=False)` 作为第二道防线。
- 不做"静默转 null"：非有限数通常是上游缺陷，把它写成 `null` 只是换一种静默。

### 2.2 四条中心写盘路径

- `atomic_write_json` → `strict_json_dumps`（失败发生在临时文件创建之前，旧目标不被触碰）；
- `experiments/run_b8_injection._write_json` → `strict_json_dumps`；
- `experiments/run_b8_injection._Injection._record` → `strict_json_dumps`（不留半行）；
- `src/observability/trace.py` 三处序列化 → `strict_json_dumps`，保留"少记不误记"：
  含非有限值的记录整条丢弃并告警，**文件本身仍逐行严格可解析**。

### 2.3 直写点

为 39 份源码的 41 个 `json.dump(s)` / `write_text` 文件写入点补显式
`allow_nan=False`（按文件：`src/` 8、`experiments/` 17、`scripts/` 14；按写入点：
8 / 19 / 14，其中 `e7_adjudication.py` 与 `run_benchmark.py` 各两处；`json_strict.py`
自身的 `allow_nan=False` 与门禁里用于比对的字面量不计入直写点）。门禁对这 41 处逐一复扫，
当前违规 0。

## 3. 全仓门禁 `check_json_strict.py`

两条判据：

1. **工件严格解析**：`git ls-files` 中全部 `.json` / `.jsonl`，`json.loads(parse_constant=拒绝)`，
   `.jsonl` 逐行解析并报行号；非 git 环境回退 `rglob`。
2. **源码写入点**：`src/` / `experiments/` / `scripts/` 的 AST 扫描——`json.dump` 与
   "`json.dumps` 位于 `write`/`writelines`/`write_text`/`atomic_write_text`/`stdout.write` 实参链内"
   必须带字面 `allow_nan=False`。

防假绿：空集合直接失败（`未扫描到任何 .json/.jsonl 工件` / `未扫描到任何源码文件`）；
2 份历史截断轨迹在 `_ALLOWLIST` 逐路径登记，且**豁免文件若变得严格可解析即报"豁免漂移"**，
防止豁免面悄悄扩大。

实测输出（真实仓）：

```text
工件 7273 份（json/jsonl）= 严格 7271 + 登记豁免 2 + 违规 0；源码 300 份，写入点违规 0 处
```

耗时约 1.2s。已接入 `make gates` 与 CI（`Check strict JSON` 步骤）。

## 4. AE §5.6 的计量勘误（只追加、不改写 AE 原文）

AE §5.6 记："`experiments/results/` 下 68 份 JSON 在文本中含裸 `NaN` / `Nan` / `Infinity` token"。
AF 复测结论：**该计数是文本 grep 结果，不等于 JSON 裸 token 违规**。

- 以 `json.loads(parse_constant=拒绝)` 严格解析全部 7273 份受控工件：**违规 0 份**；
- `experiments/results/` 下确有 69 份文件（worktree；其中 42 份 tracked）在**字符串值内部**
  出现 `NaN` / `Infinity` 字样——这是合法 JSON 文本（例如测试名 `test_sqrt_positive_infinity`、
  诊断文本 "x 为 NaN"），严格解析器接受；
- 因此 AE §5.6 的"68 份非 RFC-8259 工件"不能作为本仓存在非严格工件的证据；
  真正成立的缺口是 §5.7 的写入路径（本轮已修）。

该教训已机器化为两条锁：`test_nan_text_inside_string_is_not_flagged`（门禁不把字符串内文本
计成违规）与 `test_token_inside_string_is_legal_and_not_flagged`（序列化器不转义/不删除文本）。

## 5. 回归锁与变异验证

新增 `tests/test_json_strict_af.py` **28 例**：序列化器路径点名 8、原子写/run_b8 fail-closed 4、
trace 少记不误记 3、门禁 7（含真实仓跑与"字符串内 NaN 不计违规"）、库级 6。

变异验证（基线 28 passed、collected 28；每次写盘前 `compile()`、还原后 sha256 断言）：

| 锚点 | 回退内容 | 转红例数 |
|---|---|---|
| M1 | 非有限检测失效 | 8 |
| M2 | `atomic_write_json` 回退 lenient | 1 |
| M3 | `run_b8._write_json` 回退 lenient | 2（含门禁源码扫描） |
| M4 | `_Injection._record` 回退 lenient | 2（含门禁源码扫描） |
| M5 | `trace` 三处回退 lenient | 3（含门禁源码扫描） |
| M6 | 门禁工件检查关闭 | 2 |
| M7 | 门禁源码写入点检查关闭 | 1 |
| M8 | 门禁豁免漂移检查关闭 | 1 |
| M9 | 直写点移除 `allow_nan=False` | 1（真实仓门禁用例） |

零红锚点 0 个。M3/M4/M5 额外触发 `test_real_repo_passes`，说明门禁对"写入点回退"提供第二道
独立锁；M1 下 trace 用例仍绿，因为 `strict_json_dumps` 的 `allow_nan=False` 第二道防线仍会抛错、
trace 按"丢弃本条"语义处理——这是分层防御的预期行为，不是锁缺口。

## 6. 收口读数

- 全量（`make test-cov`，xdist -n 4 loadfile）：**10351 passed / 5 skipped / 0 failed**，
  collected **10356**（AF 净增 28 例），191.66s。
- 覆盖率（`coverage.xml`）：行 **18486/19009 = 97.2487%**，分支 **6674/7110 = 93.8678%**；
  分母较上一读数 +46 行 / +20 弧（新增 `json_strict.py` 45 语句 / 20 弧 100% 被锁执行 +
  `atomic_io`/`trace` 改写净 +1 行），新增行 100% 被覆盖。
- 登记前一跑：10349 passed / 2 failed / 5 skipped——失败①为本基线守卫（BASELINE 未刷新），
  失败②为**本轮新引入的真实缺陷**：CI 步骤 `name` 含未加引号的 `AF: `，YAML ScannerError，
  被 `test_ci_yaml_parses` 当场抓住；加引号后转绿。该自纠如实登记。
- `make gates` 全链抓到**第三例**（既有 AO3 行锁）：`tests/test_ao_batch.py::TestReadmeEnHeader`
  仍断言英文 README 头部含 "AE round"，而头部已推进到 AF——按该锁既定维护约定推进短语
  （并在 docstring 记下本次推进）后转绿。**这不是"改锁迁就失败"**：该锁的语义就是
  "头部随最新批次推进"，每轮合法更新。之后 `make gates` **单独复跑确认 rc=0**
  （10351 passed / 5 skipped / 0 failed，183.51s；链内不带 `--cov`，与首行 191.66s
  的覆盖率口径不同，不可互换引用）。

## 7. 边界（不得引用为"全仓 JSON 已处处严格"）

1. **2 份 A20 历史截断轨迹仍非严格**（`_ALLOWLIST` 逐路径登记、受保护工件不重写）；
   豁免带漂移检测，文件一旦可严格解析即报红要求删除豁免。
2. **门禁只认字面 `allow_nan=False`**：`**kwargs` 或运行期拼出的关键字不在静态扫描面内；
   当前仓内无此形态，将来出现需人工复核。
3. **`tests/` 不在源码写入点扫描面**：测试夹具自行写 JSON 时仍可能用 lenient 默认；
   这是刻意缩小作用面（测试产物不是对外工件），不是"测试侧已严格"的证明。
4. **字符串内的 `NaN` 文本合法**：门禁不会把它判成违规，也不会自动规范化数据语义。
5. **trace 丢弃语义**：含非有限值的记录从 JSONL 中整条消失（仅 WARNING），消费方无法区分
   "没记录"与"记录坏了"；这是旁路观测层"宁可少记，不写坏行"的既定取舍。
6. **`_Injection._record` 改为抛错**：注入实验记录含非有限值时不再写坏行而是显式失败；
   若上游计时出现 NaN，该实验会中止——这是 fail-closed 的预期代价。

## 8. 复算命令

```bash
# 门禁
.venv/bin/python scripts/gates/check_json_strict.py

# 回归锁
.venv/bin/python -m pytest tests/test_json_strict_af.py -q

# 全量 + 覆盖率（CI 同口径）
COVERAGE_FILE=.coverage.ci .venv/bin/python -m pytest tests/ -n 4 --dist loadfile \
  --cov=src --cov-branch --cov-report=term-missing --cov-report=xml
```
