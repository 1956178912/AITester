# 依赖豁免登记表

> 本文件记录 `pip-audit` 安全扫描中对已知漏洞的显式豁免（exemption）：
> 为何豁免、豁免哪些漏洞 ID、复审触发条件与期限。
> 与 CI 的 `--ignore-vuln` 豁免列表、`requirements.lock` 版本保持一致，
> 任何依赖变更或新发修复版时都必须同步本表。
>
> **维护约定**（见 `CONTRIBUTING.md` "依赖变更清单"）：
> - 新增豁免必须在本表登记（依赖 / 版本 / 漏洞 ID / 豁免原因 / 复审触发条件 / 复审期限）；
> - 上游发布修复版后，按"复审触发条件"列的提示尽快升级并移除对应
>   CI `--ignore-vuln` 豁免与本表条目；
> - 每季度复审一次本表，过期未复审的条目在 CHANGELOG 标注"豁免过期"。
>
> **复审触发机制（2026-10 确认；DF 轮补入可执行的过期判据）**：
> 1. **CI 登记门禁**：`scripts/gates/check_dependency_exemptions.py`（经
>    `.github/workflows/ci.yml` 在每次 PR / 推送时运行）把 `ci.yml` 实际生效的
>    `--ignore-vuln` 列表与本表"当前豁免"节逐条对照——未登记的豁免阻断合并
>    （退出码 1）；已登记但"复审期限"列缺失 / 空白时输出 warning。
> 2. **CI 过期门禁**：`scripts/gates/check_dependency_audit.py --require-audit`
>    （同作业、同一次 PR / 推送）真实跑一次**不带 `--ignore-vuln`** 的 pip-audit：
>    本表任一条目在审计结果里出现 `fix_versions` ⇒ 阻断（**豁免必须随修复版失效**）；
>    审计命中未登记 ID、或本表"锁定版本"与 `requirements.lock` 不一致 ⇒ 阻断；
>    本表理由「仅嵌入式、无服务器面、无 `trust_remote_code`」由 `src/` 静态扫描锁定
>    （命中 `HttpClient` / `trust_remote_code` / RBAC provider / `chromadb.app` 即阻断）。
>    这条把下方第 2 点从"人工记得"变成"不记得就红"。
> 3. **上游修复版提醒**：chromadb 上游发布含修复的新版本号（命中 3813/3814/3815
>    任一 advisory）时，`requirements.lock` 版本变化即触发"复审触发条件"；
>    维护者在每次升级依赖时对照本表检查是否有可关闭的豁免条目。
> 4. **季度人工复审**：每季度末检查本表所有条目的"复审期限"，过期未复审的
>    条目在 CHANGELOG 对应批次标注"豁免过期"，并决定是否续期 / 升级 / 关闭。

## 当前豁免

| 依赖 | 锁定版本 | 漏洞 ID | 豁免原因 | 复审触发条件 | 复审期限 | 备注 |
|---|---|---|---|---|---|---|
| chromadb | 1.5.9 | PYSEC-2026-311（重复两条）+ PYSEC-2026-3813 / 3814 / 3815 | PyPI 暂无含修复的发布版本；chromadb 1.5.9 是 RAG 嵌入后端的可选依赖（缺失时透明降级，不进 git 运行时路径） | chromadb 上游发布修复版（新版本号命中 3813/3814/3815 任一 CVE 的 advisory）；或 `requirements.lock` 中 chromadb 版本变化 | 每季度，或修复版发布后立即 | 升级后同步移除 `ci.yml` 对应 `--ignore-vuln` 行 + 本表条目 |

## 已复审关闭的历史豁免

（暂无）

> 历史豁免（如早期 CVE-4583x 系列）在 chromadb 版本升级、CI 豁免 ID
> 漂移为 PYSEC 口径后已关闭；变更记录见 `CHANGELOG.md` 对应批次条目。
