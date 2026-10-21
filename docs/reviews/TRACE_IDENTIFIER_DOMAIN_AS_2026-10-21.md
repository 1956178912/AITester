# AS 轮：生产端标识先写对——32/16 位、root、parent 指向（2026-10-21，零 LLM）

**范围**：`src/observability/trace.py` 的 `TraceSession`——`run_id` / `span_id` /
`parent_span_id` 的写入契约，以及结构标识字段与通用 32+ hex 脱敏规则的冲突。
AR 轮在**导出端**做了标识规范化与确定性派生；本轮回到**生产端**，让 JSONL 里
本来就写着合法的 OTel 标识，而不是靠导出端补零与派生掩盖上游缺陷。

**结论**：改前 `TraceSession` 写 16 位 `run_id`、12 位 `span_id`（OTel 要求
trace_id 32 / span_id 16）；`task_start` / `task_end` 完全不带标识；注释承诺的
`parent_span_id` 在全语料**一次都没出现**。真实语料 9086 个 trace 文件、
110926 条 node：61188 条带 16 位 `run_id` / 12 位 `span_id`，49738 条无标识
（全部落在 O7 之前），9085 条 `task_start` / 9046 条 `task_end` 全部无标识。处置后：
一次会话一个 32 位小写 hex `run_id`，`task_start` 是 16 位 root，node /
`task_end` 各带唯一 16 位 `span_id` 且 `parent_span_id` 指向 root；文件追踪与
纯内存两种模式都产 root；结构标识字段按**精确形状**豁免通用长 hex 脱敏，
普通文本里的 32 位 hex 仍照常脱敏。**10 例新锁 + 18/18 变异锚点转红 + 0 逃逸**；
确认跑 **10961 passed / 5 skipped / 0 failed**。**未提交。**

---

## 1. 缺陷定义

改前核心写入（`src/observability/trace.py`，AS 前原文）：

```text
# 会话初始化：run_id 16 位、root span 12 位；task_start 只在启用文件追踪时写
self._run_id = uuid.uuid4().hex[:16]
self._root_span_id = uuid.uuid4().hex[:12]
if self._enabled and directory is not None:
    ...
    self._append({"event": "task_start", "task": task_id, "ts": started_at,
                  "run_id": self._run_id, "span_id": self._root_span_id, ...})

# record_node：span 12 位；注释声称有 parent，代码从未写入
record = {"event": "node", ..., "run_id": self._run_id,
          "span_id": uuid.uuid4().hex[:12]}

# record_task_end：无任何标识
record = {"event": "task_end", "task": self.task_id, "ts": time.time(),
          "passed": passed}
```

三层后果：

1. **宽度不合 OTel**：16 位 / 12 位在导出端只能靠左补零装成 32 / 16 位——
   形态合法了，但生产端并没有真正记录 OTel 宽度标识；
2. **root 缺席**：`task_start` 无标识，导出端只能合成 root（AR 已消除随机性，
   但合成 root 仍不是生产观测值）；纯内存模式甚至没有 `task_start` 记录；
3. **parent 永不出现**：node / task_end 没有 `parent_span_id`，父子关系只能由
   导出端按"每个文件一个 root"隐含推断，跨文件或多 root 时无法复原。

此外还有一个**实现级冲突**：一旦把 `run_id` 写成 32 位 hex，写入前的结构脱敏会
命中 `logging_utils` 的通用"长十六进制密钥"规则
（`(?<![\w-])[A-Fa-f0-9]{32,}(?!\w)` → `<REDACTED_KEY>`），把 `run_id` 本身
抹掉。只改宽度不改脱敏，会得到"标识字段存在但不可用"的假修复。

## 2. 真语料测量（只读探针，改前）

扫描 `experiments/results/**/*.trace.jsonl`（只读，不重写归档）：

| 观测 | 实测 |
|---|---|
| trace 文件 | **9086** |
| node 记录 | **110926** |
| 带 `run_id` 的 node | 61188（长度全部 **16**） |
| 带 `span_id` 的 node | 61188（长度全部 **12**） |
| 无标识 node | **49738**（时间全部落在 **2026-09-26 ~ 2026-09-29**，即 O7 之前；2026-10-01 起全部有标识） |
| `task_start` | 9085 条，**全部无** `run_id` / `span_id` |
| `task_end` | 9046 条，**全部无** `run_id` / `span_id` |
| `parent_span_id` | 全语料 **0 次** |
| 一个文件多个 `task_start` | 0 个文件 |
| 无 `task_start` 的文件 | 1 个（导出端合成 root 的既有兜底路径） |

口径说明：这是**存量语料**，本轮不重写任何历史 trace；它证明的是"生产端从未
满足契约"，不是"导出端修完后仍坏"。历史文件继续由 AR 的导出端规范化读取。

## 3. 处置

### 3.1 会话级标识

```text
self._run_id = uuid.uuid4().hex            # 32 位小写 hex = OTel trace_id 宽度
self._root_span_id = uuid.uuid4().hex[:16] # 16 位小写 hex = root span_id
```

`task_start` 在**文件追踪与纯内存两种模式**都写入 `records`：

```text
self._append({"event": "task_start", "task": task_id, "ts": started_at,
              "run_id": self._run_id, "span_id": self._root_span_id,
              "meta": {...}})
```

root 没有 `parent_span_id`（测试锁定该键缺席，而不是写 `None`）。

### 3.2 子事件

`record_node` 与 `record_task_end` 都写三键：

```text
"run_id": self._run_id,
"span_id": uuid.uuid4().hex[:16],
"parent_span_id": self._root_span_id,
```

每个 node / task_end 的 span_id 独立生成；同一会话内 32 个节点实测 32 个不同
span_id，且都不等于 root。

### 3.3 脱敏豁免按形状精确匹配

```text
_IDENTIFIER_FIELD_SHAPES = {
    "run_id": re.compile(r"[0-9a-fA-F]{32}"),
    "span_id": re.compile(r"[0-9a-fA-F]{16}"),
    "parent_span_id": re.compile(r"[0-9a-fA-F]{16}"),
}

def _restore_identifier_fields(original, redacted):
    for field, shape in _IDENTIFIER_FIELD_SHAPES.items():
        value = original.get(field)
        if isinstance(value, str) and shape.fullmatch(value):
            redacted[field] = value
    return redacted

def _redact_record(record):
    return _restore_identifier_fields(record, _redact_json_value(record, _mask))
```

豁免只作用于**这三个字段名**且**形状完全匹配**的值：

- `run_id` 32 位 hex（大写也保留；33 位不匹配 → 仍脱敏）；
- `span_id` / `parent_span_id` 16 位 hex；
- 普通文本字段（如 `note`）里的 32 位 hex **仍然脱敏**——不因为记录里有合法
  标识就放宽整条记录的脱敏；
- 全局 `mask_sensitive_info` 不变，豁免只在 trace 记录层做。

## 4. 回归锁

`tests/test_trace_identifier_domain_as.py`（**10 例**）：

1. `test_task_start_carries_otel_width_identifiers`——task_start 的 32/16 位
   形态与 root 无 parent；
2. `test_children_share_run_and_point_to_root`——run_id 全链一致、4 个 span_id
   互异、子事件 parent 全指向 root；
3. `test_many_nodes_get_unique_span_ids_under_one_root`——32 个节点唯一
   span_id，均不占用 root；
4. `test_sessions_do_not_share_run_or_root`——不同会话不共享 run/root；
5. `test_memory_only_session_has_root_and_children`——未启用文件追踪时
   records 仍以 task_start 开头，父子链完整；
6. `test_task_end_without_result_still_carries_identity`——崩溃收尾
   （`passed=None`）同样带标识；
7. `test_dump_recent_to_preserves_identifier_chain`——内存缓冲落盘后标识链不变；
8. `test_identifier_exemption_is_shape_exact`——大写 32 位保留、33 位脱敏；
9. `test_identifier_fields_survive_redaction_but_ordinary_hex_does_not`——
   三键保留、普通 `note` 中同值 hex 仍被脱敏；
10. `test_export_of_producer_trace_is_one_clean_trace`——生产端 trace 直接导出：
    单 trace、span_id / parent 与原始记录逐条一致、无 synthetic root、无
    `aitester.export_value_reasons`、两次导出逐字相等。

受影响旧锁只读复核：`tests/test_trace_jsonl_integrity.py`、
`tests/test_trace_observability.py`、`tests/test_trace_quality_grade.py` 均未
断言标识长度或存在性，无需改写。`src/graph/tracing.py` 仅透传，零改动；
`src/observability/otel_export.py` 无需改动（AS 的目标是让导出端不再需要兜底）。

## 5. 变异验证

18 个真实锚点 + M0 中性对照；逐锚点：写入变异 → `compile()` → 跑 10 例 →
sha256 原字节还原。基线 10 passed，collected 恒 10，还原后 10 passed。

| 锚点 | 变异 | 红数 |
|---|---|---|
| M0 | 中性注释（对照） | **0** |
| M1 | run_id 退回 16 位 | 3 |
| M2 | root span 退回 12 位 | 3 |
| M3 | task_start 不写 run_id | 7 |
| M4 | task_start 不写 span_id | 8 |
| M5 | node 不写 parent | 5 |
| M6 | node span 退回 12 位 | 3 |
| M7 | task_end 不写 run_id | 4 |
| M8 | task_end 不写 span_id | 4 |
| M9 | task_end 的 parent 写成 None | 5 |
| M10 | node 的 parent 写成 run_id | 5 |
| M11 | node span 复用 root | 4 |
| M12 | 纯内存模式不写 root | 2 |
| M13 | 脱敏豁免整体绕过 | 5 |
| M14 | node run_id 每次随机 | 4 |
| M15 | node span 常量 | 3 |
| M16 | task_start 带 parent | 2 |
| M17 | task_end span 复用 root | 3 |
| M18 | run_id 写成 33 位 | 4 |

**18/18 真实锚点转红，0 逃逸。** M0 证明"任何改动都会红"不成立；
覆盖长度、root / task_end 标识、parent 方向、内存 root、脱敏豁免、逐节点
run_id、span 复用 / 常量等层。还原后源文件 sha256
`92a0d308d0c44b64a7b1414d42ad26d31e779e0927472f2827699f0325a25e1a`。

## 6. 收口读数

- 登记前一跑（带 `--cov`）：**10960 passed / 1 failed / 5 skipped、179.19s**；
  collected **10966**；唯一失败 = BASELINE 数字守卫（仍写 10951，
  实收 − 声明 = 9 > 6 容差）。
- 行覆盖：**18908 / 19434 = 97.2934%**（两位小数 97.29）；较 AR
  18898/19424 分母 +10、覆盖 +10；未覆盖 **526** 不变。
- 分支覆盖：**6906 / 7342 = 94.0616%**（两位小数 94.06）；较 AR
  6902/7338 分母 +4、覆盖 +4；缺弧 **436** 不变。
- `src/observability/trace.py`：**181 statements / 58 branches / 0 miss /
  0 partial = 100%**——AS 新增代码全部被 10 例锁执行。
- 确认跑（刷新 BASELINE 后）：**10961 passed / 5 skipped / 0 failed、
  176.09s、rc=0**（collected 10966）。
- 门禁（单独跑 `make gates`，不与其他命令重叠）：**rc=0、墙钟 182s**；链内 pytest
  **10961 passed / 5 skipped / 0 failed、176.92s**（84 warnings；collected 10966）；
  ruff `918 files already formatted`；mypy 135 源文件 0 错；双语文档 0 警告 / 0 失败；
  文档链接 strict 161 份文件 / 684 条链接 / 0 错误 / 0 警告；env-budget 253/253；
  状态通道 134 文件；env-snapshot 84/84；JSON 契约 7/7；JSON strict 7273 工件
  （7271 严格 + 2 路径豁免 + 0 违规）/ 300 源文件 0 写入点违规；报告↔工件对账
  [OK]；零断言 437 测试文件 / 0 违规——读数已回填 `BASELINE.yaml last_verified`。
  回填后验证跑 **rc=0、墙钟 184s、链内 179.28s / 38 warnings**（collected 10966 不变）。

`coverage report` 终端的偏弧读数（`BrPart`）与 `coverage.xml` root 的缺弧
（valid − covered）是不同口径；本轮只引用后者（436）。

## 7. 边界（不得引用为「生产端标识已全仓闭合」）

1. **只覆盖 `TraceSession`**：其它写入 trace JSONL 的路径（若有）不在本轮；
   历史文件不重写，旧标识仍由导出端规范化。
2. **parent 只有一层**：node / task_end 都指向 session root，不表达节点间的
   嵌套或因果链；`record_node` 不接受调用方指定 parent。
3. **task_end 的 span_id 独立于 node**：没有"结束事件复用最后一个 node span"
   的语义；只保证同一会话内唯一。
4. **run_id 是会话级不是任务级**：重跑同一 task_id 会产生新的 run_id；
   不能用 run_id 做任务去重。
5. **脱敏豁免是字段名 + 形状双精确匹配**：不匹配的 32 位值仍脱敏；不要把
   "记录里出现合法 run_id"理解为整条记录免于脱敏。
6. **纯内存模式新增一条记录**：`records` 现在以 `task_start` 开头；依赖
   "records 第一条是 node"的消费方需要适配（仓内无此类断言，已只读复核）。
7. **不保证 uuid 碰撞**：span_id 取 `uuid4().hex[:16]`，理论碰撞未加去重；
   与 OTel 16 位 span_id 的常规实践一致，本轮不引入注册表。
8. **存量 49738 条无标识 node 仍是历史事实**：本轮修的是生产端，不回填；
   分析这些文件时仍应使用 AR 导出端的确定性派生值，并注明"派生 ≠ 观测"。
9. **覆盖口径**取 `coverage.xml` root（18908/19434、6906/7342）；终端偏弧
   是另一口径，不得混用。

## 8. 复算命令

```bash
# 目标锁（10 collected）
.venv/bin/python -m pytest tests/test_trace_identifier_domain_as.py -q

# 受影响面（只读复核）
.venv/bin/python -m pytest tests/test_trace_jsonl_integrity.py tests/test_trace_observability.py \
  tests/test_trace_quality_grade.py tests/test_observability_enhanced.py -q

# 全量 + 覆盖率（CI 同口径；不与 make gates 重叠）
make test-cov

# 确认跑（BASELINE 刷新后）
make test

# 门禁（最后单独跑，绝不与其他命令重叠）
make gates
```
