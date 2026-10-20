# E7 修复上限分层抽样候选清单（AL10，2026-10-06）

- 数据来源（与 repair_ceiling_report.md 同参口径）：3 个批次
  - benchmark_synthetic_20261006_164357.json
  - benchmark_synthetic_20261006_151907.json
  - benchmark_synthetic_20261006_140906.json
- 分层框（patch_plausible=1 行）：72 行〔sbfl: 72〕
- 抽样参数：fraction=56%（每层 ceil 上取整）、seed=42（确定性）
- 复核判定口径：equivalent / plausible_overfit / wrong_location / test_only / incomplete

| task_id | 分层（evidence） | stop_reason | error_category | iterations | patch 长度 | 人工判定 |
|----|----|----|----|----|----|----|
| s42__synthetic__task_0044 | sbfl | max_iterations | assertion | 3 | 254 | （待复核） |
| s42__synthetic__task_0013 | sbfl | max_iterations | patch_validation_failed | 3 | 166 | （待复核） |
| s43__synthetic__task_0028 | sbfl | test_passed | test_regenerated_pass_unverified | 2 | 811 | （待复核） |
| s43__synthetic__task_0022 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 205 | （待复核） |
| s43__synthetic__task_0005 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 204 | （待复核） |
| s42__synthetic__task_0055 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 363 | （待复核） |
| s42__synthetic__task_0043 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 583 | （待复核） |
| s42__synthetic__task_0036 | sbfl | test_passed | test_regenerated_pass_unverified | 3 | 318 | （待复核） |
| s44__synthetic__task_0008 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 337 | （待复核） |
| s42__synthetic__task_0012 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 478 | （待复核） |
| s42__synthetic__task_0006 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 196 | （待复核） |
| s42__synthetic__task_0018 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 344 | （待复核） |
| s44__synthetic__task_0050 | sbfl | test_passed | test_regenerated_pass_unverified | 2 | 152 | （待复核） |
| s44__synthetic__task_0082 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 554 | （待复核） |
| s43__synthetic__task_0023 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 228 | （待复核） |
| s43__synthetic__task_0052 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 266 | （待复核） |
| s44__synthetic__task_0039 | sbfl | max_iterations | runtime | 3 | 325 | （待复核） |
| s44__synthetic__task_0067 | sbfl | max_iterations | assertion | 3 | 257 | （待复核） |
| s42__synthetic__task_0037 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 631 | （待复核） |
| s43__synthetic__task_0070 | sbfl | max_iterations | patch_validation_failed | 3 | 353 | （待复核） |
| s43__synthetic__task_0059 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 185 | （待复核） |
| s43__synthetic__task_0067 | sbfl | test_passed | assertion | 1 | 554 | （待复核） |
| s43__synthetic__task_0027 | sbfl | test_passed | test_regenerated_pass_unverified | 2 | 382 | （待复核） |
| s42__synthetic__task_0084 | sbfl | max_iterations | assertion | 3 | 184 | （待复核） |
| s44__synthetic__task_0031 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 201 | （待复核） |
| s44__synthetic__task_0058 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 270 | （待复核） |
| s43__synthetic__task_0043 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 445 | （待复核） |
| s44__synthetic__task_0053 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 188 | （待复核） |
| s42__synthetic__task_0005 | sbfl | test_passed | type_error | 1 | 886 | （待复核） |
| s42__synthetic__task_0035 | sbfl | test_passed | test_regenerated_pass_unverified | 3 | 233 | （待复核） |
| s43__synthetic__task_0002 | sbfl | test_passed | test_regenerated_pass_unverified | 2 | 199 | （待复核） |
| s42__synthetic__task_0068 | sbfl | max_iterations | patch_validation_failed | 3 | 556 | （待复核） |
| s43__synthetic__task_0080 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 173 | （待复核） |
| s42__synthetic__task_0033 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 554 | （待复核） |
| s44__synthetic__task_0034 | sbfl | test_passed | test_regenerated_pass_unverified | 2 | 203 | （待复核） |
| s43__synthetic__task_0058 | sbfl | test_passed | test_regenerated_pass_unverified | 2 | 294 | （待复核） |
| s42__synthetic__task_0020 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 451 | （待复核） |
| s44__synthetic__task_0036 | sbfl | test_passed | test_regenerated_pass_unverified | 2 | 256 | （待复核） |
| s42__synthetic__task_0078 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 256 | （待复核） |
| s44__synthetic__task_0047 | sbfl | test_passed | test_regenerated_pass_unverified | 1 | 234 | （待复核） |
| s42__synthetic__task_0069 | sbfl | max_iterations | assertion | 3 | 185 | （待复核） |

判定规则（预注册）：equivalent 占比 > 0 → repair 口径存在低估，须勘误并给
出修正后上界；= 0 → repair=0 为真零（上限卡在合理性与 gold 正确性）。
