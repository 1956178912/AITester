# 威胁模型（Threat Model）

> 最后更新：2026-10-26 · English: [threat_model.en.md](threat_model.en.md)

本文件把攻击面映射到守卫模块与残余风险。系统假设：运行者可信；被测源码可来自
公开数据集；**LLM 生成的测试与补丁会在沙箱内自动执行**——这是本系统最核心的
风险源；LLM API 需外网；不涉及人类受试者数据。

## 1. 资产

| 资产 | 丢失或滥用后的影响 |
|------|--------------------|
| LLM 凭证与宿主环境变量 | API 配额盗用、费用损失、上游账号受限 |
| 宿主文件系统与进程 | 生成代码越权读写或资源耗尽拖垮宿主 |
| 评测数据与读数 | 污染或篡改使实验结论不可信 |
| CI 凭据与发布工件 | 恶意 PR 借流水线执行任意命令 |
| API 配额与磁盘 | 并发 × 缓存写盘放大成本与占用 |

## 2. 对手

| # | 攻击面 | 典型向量 |
|---|--------|----------|
| A1 | 凭证泄露 | 生成代码整包读取 `os.environ` 并外传 |
| A2 | 供应链（slopsquatting） | 自动装依赖时安装仿冒包 |
| A3 | 提示注入 | issue / 被测代码中嵌入指令，诱导泄露密钥或注入恶意补丁 |
| A4 | 沙箱逃逸 | 外联、读宿主文件、越界写入 |
| A5 | 数据污染 | 训练集与评测集重叠，读数虚高 |
| A6 | 滥用 | 把系统用于向目标仓库注入恶意外联测试 |
| T7 | CI/CD 供应链 | 恶意 PR 借工作流与脚本以 CI 凭据执行命令 |
| T8 | 多层沙箱复合失效 | 默认配置下缺少第二道文件系统防线 |
| T9 | 资源耗尽 | 并发、缓存与后台健康检查消耗配额与磁盘 |

## 3. 控制

| # | 守卫 | 状态 |
|---|------|------|
| A1 | `src/utils/credential_scrub.py` 三条执行链路统一剔除凭证；沙箱目录隔离；`.env*` 全部 gitignore | 已实现 |
| A2 | `src/tools/dependency.py` 包白名单（`PIP_PACKAGE_WHITELIST_ENABLE` 默认开，未知名拒绝）+ `requirements.lock` + `scripts/gates/check_lock_sync.py` | 已实现；白名单需人工维护 |
| A3 | `src/agents/injection_guard.py` 输入侧扫描 + `src/agents/deterministic_guard.py` 输出侧扫描 + 对抗样本回归基准（召回 ≥0.8 / 误伤 0） | 已实现（启发式） |
| A4 | 三级隔离：venv 沙箱（默认）/ Docker + 出口白名单 / 内核沙箱（Seatbelt、Landlock+bwrap） | 部分：内核沙箱默认关 |
| A5 | `src/tools/contamination_check.py` 三维检测 + `scripts/gates/check_swe_bench_pro_ready.py` 数据前置门禁 | 已实现；语义级为词袋近似 |
| A6 | `src/graph/risk_approval.py` 三因子风险分级人工回路 + A2/A4 组合 | 部分：`RISK_APPROVAL_ENABLE` 默认关 |
| T7 | actions 全 40 位 SHA 钉版、下载物 sha256 校验、全仓无 `pull_request_target`、`permissions: contents: read`；gitleaks 工作树扫描阻断 | 部分：全历史扫描非阻断 |
| T8 | `src/agents/executor_runtime.py` rlimit 五项（CPU / AS / NPROC / FSIZE / NOFILE）+ 凭证白名单环境 + `AITESTER_PROFILE=safe` 预设 | 部分：默认仅 rlimit + 凭证剔除 |
| T9 | token / 美元 / 墙钟预算 + `clean-venv-cache`（`--max-age-days` / `--max-size-mb`）+ `API_HEALTH_CHECKER_ENABLE` 可关 | 部分：磁盘无自动守护、成本预算默认关 |

**Fail-closed 口径**：内核沙箱启用但平台无 sandbox-exec / bwrap 时拒绝执行
（`build_sandbox_command` 返回 fail-closed 标记）；Docker 不可用时不静默回退
宿主执行；包白名单为空时降级 `--network=none`，而非全放通。

## 4. 残余风险

1. **内核沙箱默认关**（`KERNEL_SANDBOX_ENABLE=false`，P0-4）：本地与 venv
   两条链路已接线；生产或不可信目标建议 `AITESTER_PROFILE=safe` 或显式设
   `KERNEL_SANDBOX_ENABLE=true`。
2. **历史密钥残留**（T7）：已删除文件在 `2e5272a` / `c505f506` 留存疑似真实
   密钥，全历史 gitleaks 维持非阻断，待轮换 + 历史重写；处置见
   [security/history_leak_remediation_runbook.md](security/history_leak_remediation_runbook.md)。
3. **检测为启发式**（A3/A5）：注入扫描可被对抗样本绕过，污染语义层是词袋
   近似；回归基准只防退化，不构成完备性宣称。
4. **维护性缺口**（A2/T9）：白名单无自动更新；成本预算默认关，磁盘用量需
   运维定期执行 `clean-venv-cache`。
5. **已接受风险**：LLM 文件缓存为本地可信域产物（0600、不进 git）；
   chromadb 1.5.9 的 5 条已知漏洞经
   [dependency_exemptions.md](dependency_exemptions.md) 登记豁免并季度复查。
