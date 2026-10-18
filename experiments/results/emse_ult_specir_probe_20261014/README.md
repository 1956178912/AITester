# EMSE ULT SpecExpr 探针（2026-10-14，25 任务）

> 目的：填补 BASELINE `spec_compile_rate.aitester.ult_post_grammar`（T-11 遗留
> "契约后 ULT 零实测"）。干净口径（`DETECTION_SPEC_MODE=replace +
> SPEC_IR_ENABLE + SPEC_IR_DSL_ENABLE`，无 profile），与 QuixBugs pilot /
> synthetic 确认性跑批同口径，跨数据集可此较。

## 结果

| 指标 | 值 |
|---|---|
| spec_compile_rate | **0.5626**（n=25；7/25 恒 0） |
| spec_expr_coverage | 0.6176（n=21） |
| spec_replace_applied | 21/25 replaced（回退率 0.16） |
| detection | 0/24 可测（延续 ult_lite46 的 0/45——ULT 生成测试不产红） |
| 成本 | 524,592 token / 141 调用 ≈ $0.15 |

**provenance**：profile=None、SPEC_IR_ENABLE=true、SPEC_IR_DSL_ENABLE=true、
DETECTION_SPEC_MODE=replace、cache_namespace=specexpr_ult_probe_v1（全新）、
指纹 aeb56401ca74e127… pinned、git_sha e7a0027 clean。

## 结论

ULT（真实基准）契约后 spec_compile_rate=0.5626 **≥0.35 阈值**——与 QuixBugs
0.6321（n=50）并列构成"逻辑驱动"可编译率主张的两个真实基准数据点；
synthetic 模板仅 0.3102（n=174）未达。可编译率呈**数据集分层**：受限表达式
DSL 对真实代码规约接受率良好，对合成模板子句（`unknown_name` 拒绝为主）
不足——下一优化方向 = 扩白名单/扩文法（优先 synthetic 模板场景），见 BASELINE
note 与 EMSE 报告 §6.5/§6.8。

注意：ULT 的 detection 对比仍不可用（生成测试在 ULT 上零检出，0 基线无
McNemar 判别力）——本探针只补 spec_compile_rate 机制观测，不作检测增益证据。

## 文件

- `benchmark_ult_*.json`：批次工件（25 任务 details + provenance）
- `raw/`、`traces/`：环节级状态与轨迹
- `chain.log`：跑批日志（含随后全量 pytest 尝试记录）
- `full_pytest_v2_summary.txt`：全量 pytest 复跑摘要（沙箱阻断模式复现，见下；完整 11MB 日志不留档）
- `SHA256SUMS`：完整性校验（`shasum -a 256 -c SHA256SUMS`）

## 附：全量 pytest 沙箱阻断复现

同链尾的全量 pytest（`--basetemp=.pytest_tmp_full_v2`）再次复现沙箱阻断
模式（4525 errors / 2 failed / 1309 passed）——单文件复跑全部通过
（test_z_batch.py 18/18、test_emse_specexpr_confirm.py 24/24、
test_2026_10_10_optimization_batch.py 26/26），确认错误为环境性
（sitecustomize bulk-delete 守卫 / pytest-of-root 争用），非代码回归。
BASELINE total_passed 维持推导值 5835（collected 5839），实测须提权前台。

## 勘误（2026-10-18，第三方评审 A20）：一处轨迹 JSONL 单行损坏，原字节保留

- **损坏文件**：`traces/ult__string_contrast_aitester_1791954227.trace.jsonl`
- **位置**：第 10 行（1-based）；`json.loads` 报 `Unterminated string`，
  字符串起始于第 201 列左右，行尾停在 `...min(s, key=<REDACTED>`，
  缺少字符串闭合引号与对象闭合花括号（该行共 399 字符）。
- **字节完整性**：损坏文件**未被修补、未被删除、未被替换**——原字节与
  本目录 `SHA256SUMS` 第 26 行记录的 sha256
  `97cf47b9…a7ebbdd22` 逐字节一致；同文件其余 17 行、同批
  `benchmark_ult_20261014_130937.json` 与其余轨迹均不受影响。
- **根因（已定位并修复，不改写历史工件）**：`TraceSession._append` 先把记录
  `json.dumps` 成单行 JSON，再对**整行文本**调用
  `src/utils/logging_utils.mask_sensitive_info` 脱敏；其中
  `(?:key|token|secret|password)=(.{8,})(?:\s|$|")` 模式的 `.` 不排除引号/
  花括号，贪婪匹配会一路吃到行尾并把 JSON 闭合引号与花括号一起吞掉。
  该行 `output` 内的 LLM 诊断文本含 ``min(s, key=<键函数>)`` 形式，恰好触发
  该模式——与本文件第 10 行的截断形态逐字吻合（可用旧模式对同类合法 JSON
  行复现：输出同样停在 `key=<REDACTED>` 且 `json.loads` 抛未闭合字符串）。
- **修复位置**（2026-10-18）：`src/observability/trace.py` 改为
  **先对记录结构逐字段脱敏、再序列化**，并在落盘前用 `json.loads` 做结构
  守卫（失败诊断出口 `dump_recent_to` 同步修复）；`src/utils/logging_utils.py`
  的该模式值字符类收紧为 token 边界（排除引号/花括号/反斜杠等 JSON 结构
  字符），不再消费定界符。回归测试：
  `tests/test_trace_jsonl_integrity.py`（含"诊断文本含 `key=…` 且位于行尾"
  用例，断言落盘 JSONL 逐行可解析）。
- **复核方式**：

  ```bash
  python - <<'PY'
  import json
  from pathlib import Path
  p = Path("experiments/results/emse_ult_specir_probe_20261014/traces/"
           "ult__string_contrast_aitester_1791954227.trace.jsonl")
  for no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
      if not line.strip():
          continue
      try:
          json.loads(line)
      except json.JSONDecodeError as e:
          print("JSONL error:", no, e.msg, e.colno)
  PY
  ```

  预期输出仅 `JSONL error: 10 Unterminated string starting at 201`——
  该行是本批次唯一的已知损坏记录，为**历史工件如实保留**的证据，不参与
  指标复算（复算消费的是 `benchmark_ult_*.json` 汇总 JSON）。

