# 文档索引

> 最后更新：2026-10-27 · English: [INDEX.en.md](INDEX.en.md)

本索引是全仓文档的入口：按角色给出最短阅读路径，并列出核心文档。历史批次记录统一归档在
[history/](history/)，不再逐条维护。

## 1. 快速入口

| 你想…… | 从这里开始 |
|---------|------------|
| 了解项目定位与结论边界 | [README.md](../README.md) · [MODEL_CARD.md](../MODEL_CARD.md) |
| 跑起来 | [QUICKSTART.md](../QUICKSTART.md) |
| 看架构与模块 | [algorithm_design.md](algorithm_design.md) · [api_reference.md](api_reference.md) |
| 复现实验 | [REPLICATION.md](../REPLICATION.md) |
| 参与贡献 | [CONTRIBUTING.md](../CONTRIBUTING.md) |

### 1.1 数值的唯一来源

讨论数字前先读：测试计数、静态检查与基准读数统一登记在
[BASELINE.yaml](../BASELINE.yaml)；门禁链与派生读数在
[PROJECT_STATUS_REGISTER.md](PROJECT_STATUS_REGISTER.md) §1 与门禁复算对账。**不要在其他
文档里复制会漂移的计数**。

## 2. 按角色阅读路径

### 2.1 新读者（约 30 分钟）

1. [README.md](../README.md) → 2. [QUICKSTART.md](../QUICKSTART.md) → 3.
   [usage_examples.md](usage_examples.md)

### 2.2 审稿人 15 分钟路径

1. [reviews/README.md](reviews/README.md) → [VALIDITY.md](VALIDITY.md) → [preregistration.md](preregistration.md)

### 2.3 维护者

1. [api_reference.md](api_reference.md) → 2. [performance_guide.md](performance_guide.md) →
   3. [troubleshooting.md](troubleshooting.md)

## 3. 核心文档清单

### 3.1 定位与效度

- [MODEL_CARD.md](../MODEL_CARD.md) · [DATA_CARD.md](DATA_CARD.md) ·
  [VALIDITY.md](VALIDITY.md) · [preregistration.md](preregistration.md) ·
  [EVALUATION_SCOPE.md](EVALUATION_SCOPE.md)
- [MEASUREMENT_INTEGRITY.md](MEASUREMENT_INTEGRITY.md) ·
  [COVERAGE_RATCHET_DEVIATION.md](COVERAGE_RATCHET_DEVIATION.md)

### 3.2 系统与 API

- [algorithm_design.md](algorithm_design.md) · [api_reference.md](api_reference.md) ·
  [threat_model.md](threat_model.md) · [SECURITY.md](../SECURITY.md)

### 3.3 使用与运维

- [QUICKSTART.md](../QUICKSTART.md) · [usage_examples.md](usage_examples.md) ·
  [performance_guide.md](performance_guide.md) · [COST_MODEL.md](COST_MODEL.md) ·
  [troubleshooting.md](troubleshooting.md) · [dependency_exemptions.md](dependency_exemptions.md)

### 3.4 证据与工件

- [REPLICATION.md](../REPLICATION.md) · [failure_analysis.md](failure_analysis.md) ·
  [BASELINE.yaml](../BASELINE.yaml) · [CITATION.cff](../CITATION.cff)

### 3.5 治理、评审与历史

- [PROJECT_STATUS_REGISTER.md](PROJECT_STATUS_REGISTER.md) ·
  [HUMAN_ADJUDICATION_PROTOCOL.md](HUMAN_ADJUDICATION_PROTOCOL.md)
- 评审分册入口：[reviews/README.md](reviews/README.md)
- 归档与专题目录：[adr/](adr/) · [design/](design/) · [emse/](emse/) · [security/](security/) ·
  [history/](history/)

## 4. 链接与双语维护

- **双语配对**：`docs/` 顶层核心文档需要有 `.en.md` 孪生；`make docs-check` 检查配对完整性、
  更新日期同步与章节骨架。
- **链接完整性**：`make docs-check` 同时校验内部链接；坏链在 CI 阻断。历史目录
  `docs/history/` 不参与链接检查，其内部链接不保证可解析。
- **归档约定**：过期批次与历史叙事归档到 `docs/history/`，不就地追加；当前口径文档只保留
  仍然有效的规则。
- 新增文档时：放进上表对应小节，补齐英文孪生（或登记豁免理由），再跑 `make docs-check`。
