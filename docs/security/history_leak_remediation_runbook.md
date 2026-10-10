# 历史泄漏清理 Runbook（密钥轮换 + git 历史重写）

> W8（2026-10-05 审查落地）。这是项目**当前最大的一笔已登记未修复安全债**
> （threat_model.md T7 自认；gitleaks 全历史扫描因此非阻断）。
> ⚠️ 本 runbook 涉及**改写 git 历史**与**吊销凭证**两类不可逆/外溢操作，
> 必须由仓库所有者在确认无外部协作者克隆的前提下执行（执行前知会所有
> 已知克隆方；GitHub 侧需协调 force-push 保护分支设置）。

## 0. 背景（证据链）

| 事件 | 证据 |
|---|---|
| 已删除文件在历史 commit 残留疑似真实 api.agnes-ai.cn 密钥 | commit `2e5272a` / `c505f506`（ci.yml 注释与 threat_model T7 引用） |
| 本地事故：`.env.local.bak_g8` 曾含 22 条真实 key | `.git-hooks/check_secret_leak.sh` 注释记录（该文件未入库） |
| 当前防线为何非阻断 | `.github/workflows/ci.yml` 全历史 gitleaks 步骤 `continue-on-error`（周日 schedule），注释注明"待凭证轮换" |

## 1. 密钥轮换（先于一切，零停机顺序）

历史重写**不能替代轮换**——重写前的 fork/clone/PR 缓存仍可能持有旧密文。

**核心原则：先创建新凭证，再销毁旧的（顺序颠倒会导致服务中断）。**
一旦密钥被推送到远程仓库，唯一安全的假设是它已被复制（有效密钥从进入
公共仓库到首次恶意使用的中位时间以分钟计），故轮换是**根本性修复**，
purge 历史只是减少暴露面。

1. 盘点泄漏涉及的全部 provider（agnes / aliyun_bailian / bigmodel / deepseek /
   anthropic / openai 编号变体——以 `gitleaks detect --log-opts="all" --redact`
   输出为准）；
2. **创建新密钥**（不触碰旧密钥）——在各 provider 控制台新建；
3. **推送新值到单一真相源**——新 key 只入 `.env.local`（0600，gitignore）
   或 CI Secrets，**绝不入任何被跟踪文件**；
4. **重新部署/重载**使服务拾取新值，然后把旧密钥**设为非活跃**（非删除）；
5. **观察一个轮换窗口**（建议 ≥7 天或一个完整实验周期）的错误后，永久删除旧密钥；
6. **验证旧凭证确已失效**（而非假设撤销成功）：`scripts/tools/check_quota.py` 用旧
   key 探测应返回 401/403。

## 2. git 历史重写

```bash
# 2.1 备份（不可逆操作前的唯一保险）
git clone --mirror <repo-url> repo-backup.git

# 2.2 生成替换清单（命中文件 × 旧值 → REPLACED）
#     文件级清除（对已删除的泄漏文件最直接）：
cat > leak-files.txt <<'EOF'
API_MANAGER_EXTENSION_GUIDE.md
.env.local.bak_g8
EOF

# 2.3 重写（git-filter-repo，官方推荐；rewrite 所有分支与 tag）
pip install git-filter-repo
git filter-repo --invert-paths --paths-from-file leak-files.txt
#     若只需替换值而非删文件：git filter-repo --replace-text <(echo 'OLD_SECRET==>REDACTED')

# 2.4 校验：全历史扫描必须 0 命中
gitleaks detect --log-opts="all" --redact   # 退出码 0

# 2.5 推送（force，需临时关闭分支保护）
git push origin --force --all
git push origin --force --tags
```

## 3. 收尾（转阻断 + 通知）

1. `.github/workflows/ci.yml`：删除全历史 gitleaks 步骤的 `continue-on-error`
   （周日全量档转阻断），提交说明引用本 runbook；
2. 所有已知克隆方执行 `git clone` 重新拉取（旧 clone 的 remote 历史已分叉，
   不要 `pull --rebase`）；
3. GitHub：若有 fork/镜像，评估通知删除重 fork；PR 缓存中的旧 commit 由
   GitHub support 的 view-removal 请求清除（可选，面向高敏感泄漏）；
4. 在 `CHANGELOG.md` 与本文件头部标注"已于 <日期> 完成"。

## 4. 验收标准

- [ ] `gitleaks detect --log-opts="all"` 退出码 0（全历史零命中）
- [ ] 旧 key 在 provider 侧全部失效（`scripts/tools/check_quota.py` 用旧 key 探测应 401）
- [ ] ci.yml 全历史扫描步骤无 `continue-on-error`，周日 schedule 全绿
- [ ] SECURITY.md "已知未了结事项"第 1 条移除
