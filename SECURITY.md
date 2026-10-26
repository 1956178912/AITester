# 安全策略

最后更新：2026-10-26

本文件只定义**漏洞披露与响应流程**；攻击面与防护的技术口径见
[docs/threat_model.md](docs/threat_model.md)（A1–A6 + T7 供应链 / T8 复合沙箱失效 / T9 DoS）。

## 支持版本

| 版本 | 支持状态 |
|------|----------|
| `main` 最新 commit | 安全修复 |
| 历史 tag | 请升级到 `main` |

本项目是科研代码（定位见 [MODEL_CARD.md](MODEL_CARD.md)），不提供 LTS 安全维护窗口。

## 报告漏洞

**请勿通过公开 Issue 报告安全漏洞。**

1. 优先使用 GitHub 私有安全通告（Security → Advisories → Report a vulnerability）；
2. 或联系仓库所有者（见 `CODEOWNERS`），主题带 `[security]`；
3. 请附：影响面、复现步骤或 PoC、受影响文件与版本（commit sha）。

我们承诺 7 天内确认收悉；修复进度在私有通道同步，修复后公开致谢（报告者要求匿名除外）。

## 安全基线

- **CI 阻断门禁**：gitleaks 工作树扫描（push/PR 阻断）；bandit（`src/`，豁免逐条登记于
  `pyproject.toml`）；pip-audit（顶层 + lock 全量传递依赖，豁免登记于
  `docs/dependency_exemptions.md` 并由 CI 对照）。
- **提交前防线**：`.git-hooks/check_secret_leak.sh` 扫描 staged 与未跟踪文件的密钥形态。
- **执行隔离**：LLM 生成代码默认 venv 沙箱（`EXECUTOR_USE_VENV=true`）；Docker / 内核级
  沙箱（Seatbelt/bwrap）显式启用，平台不支持时 fail-closed 拒绝执行。
- **凭证卫生**：三条执行链路统一剔除 LLM 凭证（`credential_scrub.scrub_os_environ`）；
  日志三层脱敏；缓存目录 0700、文件 0600。
- **密钥只进 `.env.local`**（不入库）；仓库不承载任何真实密钥。

## 已知未了结事项

1. **git 历史存量泄漏**：已删除文件在历史 commit（`2e5272a` / `c505f506`）残留疑似真实
   API 密钥。因此全历史 gitleaks 扫描保持**非阻断**（周日 schedule）。处置 runbook：
   [docs/security/history_leak_remediation_runbook.md](docs/security/history_leak_remediation_runbook.md)
   ——完成密钥轮换 + 历史重写后转阻断。**在此之前请勿公开分发本仓库的 fork/镜像。**
2. **chromadb 1.5.9 四条已知漏洞**：PyPI 无修复版本，显式豁免登记
   （`docs/dependency_exemptions.md`，季度复审）。RAG 为可选依赖，未安装时透明降级。
