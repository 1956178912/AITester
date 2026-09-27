# Troubleshooting — 故障排查手册

> 语言 / Language：[English](troubleshooting.en.md)（待补） | 简体中文（本文）
>
> 组织口径（外部参照竞品 DevAssure "No brittle scripts to write or
> maintain" 的价值主张 + KAT Dev 的 CI 集成定位）：**症状 → 根因 →
> 解决步骤 → 预防措施** 四段式。本手册是 AITester 的"第一入口第二站"：
> QUICKSTART 跑通后的常见卡点按本手册分诊。

## 分诊总表

| 症状关键词 | 跳转 |
|---|---|
| LLM 调用超时 / 限流 / 401 / 403 | [§1](#1-llm-调用超时与限流) |
| RAG 模型下载失败 / chromadb 报错 | [§2](#2-rag-检索器初始化失败) |
| Docker 执行环境缺失 / 容器起不来 | [§3](#3-docker-执行环境缺失) |
| venv 缓存污染 / 依赖冲突 | [§4](#4-venv-缓存污染) |
| 缓存投毒 / 缓存命中结果异常 | [§5](#5-缓存投毒检测) |
| 修复 agent 反复调用同一工具 / 烧 token | [§6](#6-流氓-agent-行为) |
| 文档链接 404 / 双语漂移 | [§7](#7-文档可访问性与双语守卫) |

---

## 1. LLM 调用超时与限流

**症状**：`LLM 调用失败，已重试 3 次` / 401 / 403 / 长时间无响应。

**根因**（按概率排序）：
1. API Key 无效或额度用尽（401/403 最常见）；
2. 限流（429 / APIReachLimitError，zai 系严格）；
3. 网络出口不通（CI 无外网 / base_url 拼错）；
4. `LLM_TIMEOUT` 过短遇上深度思考模型。

**解决步骤**：
```bash
# 1) 验证 Key 连通性（最小冒烟，零基准成本）
python experiments/run_smoke_llm.py
# 2) 多端点场景检查配置优先级
python -c "from config import LLM_CONFIGS; [print(c.model_name, c.base_url) for c in LLM_CONFIGS]"
# 3) 上调超时（深度思考模型）
export AITESTER_LLM_TIMEOUT=300
```

**预防措施**：
- 配额故障转移已内置（重试耗尽自动切备用 API）；
- `cost_budget`（`COST_BUDGET_ENABLE=true`）设任务级 token 预算，
  超限快速失败而非空转烧钱；
- 批量跑批前跑 `scripts/check_quota.py`。

## 2. RAG 检索器初始化失败

**症状**：日志 `RAG 检索器初始化失败，将跳过 RAG 增强: ...`，
随后 `refine_failure_category` 判定 `rag_retrieval_empty`。

**根因**：
1. chromadb 未安装（`RAG_MODULE_AVAILABLE=false`，预期降级）；
2. 嵌入模型下载失败（网络 / 模型仓库不可达）；
3. `rag_data/` 持久目录损坏（半截 JSON / 权限）。

**解决步骤**：
```bash
# 1) 安装 chromadb（可选组件，不装则全链路降级为无 RAG 口径）
pip install chromadb
# 2) 持久目录损坏 → 重命名让重建
mv rag_data rag_data.corrupt
# 3) 回退内存模式（跨运行不复用历史案例，最快恢复）
export RAG_PERSIST_PATH=
```

**预防措施**：
- 初始化失败标志（`_rag_init_failed`）短路后续节点的重试开销；
- 20. 关键词兜底检索（`RAG_KEYWORD_FALLBACK_ENABLE=true`）：向量
  侧不可用时降级为词袋打分，检索增强不再是全有或全无。

## 3. Docker 执行环境缺失

**症状**：执行器报 `Docker not found` / 容器构建失败 / 挂载卷报错。

**根因**：
1. 本机未装 Docker / 守护进程未启动；
2. 镜像拉取失败（registry 不可达）；
3. 凭证隔离假设被破坏（容器内可见宿主机 LLM 凭证）。

**解决步骤**：
```bash
# 1) 切到 venv 沙箱链路（不用 Docker，历史口径）
python -m src.cli.app --executor-mode venv
# 2) Docker 可用后验证凭证隔离
python -m src.cli.app --executor-mode docker
grep -c "API_KEY" /var/log/docker-*.log   # 应无宿主机凭证残留
```

**预防措施**：
- 三条执行链路（本地 / venv / Docker）共用 `credential_scrub`
  单一脱敏口径（P2 批次已改为从 `PROVIDER_TEMPLATES` 动态推导）；
- 高安全场景长期方案评估 microVM 隔离（Firecracker / Docker
  Cloud Sandboxes）——标准容器共享宿主内核，非为 agent 隔离设计。

## 4. venv 缓存污染

**症状**：仓库环境缓存（`~/.cache/aitester/repo_envs/`）里的 venv
依赖漂移，后续 setup 直接复用旧 venv 导致缺包。

**根因**：依赖指纹（requirements hash）未变化但基础镜像 / 解释器版本变了。

**解决步骤**：
```bash
# 1) 清除该仓库的环境缓存（setup 重建 venv）
python -c "import shutil, pathlib; shutil.rmtree(pathlib.Path.home()/'.cache/aitester/repo_envs', ignore_errors=True)"
# 2) 单仓库精准清除
ls ~/.cache/aitester/repo_envs/   # 按 repo 名删对应目录
```

**预防措施**：依赖指纹含解释器版本口径；基础镜像升级后建议
清一次 repo_envs。

## 5. 缓存投毒检测

**症状**：缓存命中但响应内容"不对劲"（与当前 prompt 不相关 /
疑似被注入指令污染）。

**根因**（外部参照 Clinejection 事件 + KeyPooling 研究）：
1. 跨用户 / 跨 CI 步骤写入同缓存目录（"本地可信域"假设在共享
   环境不成立）；
2. 语义缓存阈值过宽导致"语义相似但不同任务"误命中。

**解决步骤**：
```bash
# 1) 创建者归属校验（19. 批次）：确认缓存文件 creator_uid 与当前用户一致
python - <<'EOF'
import glob, json, os
for f in sorted(glob.glob("src/cache/*.json"))[-10:]:
    d = json.load(open(f))
    print(f, d.get("creator_uid", "<无字段>"))
EOF
# 2) 显式指定创建者标签（多租户/CI 逻辑隔离）
export AITESTER_CACHE_CREATOR=ci-pipeline-a
# 3) 语义缓存收紧阈值（默认 0.92，误命中频发时上调）
export SEMANTIC_CACHE_THRESHOLD=0.97
# 4) 抽样验证假阳性（默认 10% 命中抽样，观察 fp_rate）
export SEMANTIC_FALSE_POSITIVE_SAMPLING=0.2
```

**预防措施**：
- 缓存文件 0o600 / 目录 0o700 + TTL 清理（18. 批次）；
- `tests/test_multiprocess_cache_consistency.py` 的投毒模拟场景
  纳入 CI（外部写入不命中 + 负缓存过期重读语义）。

## 6. 流氓 agent 行为

**症状**：修复 agent 反复调用同一工具不产生进展 / 工具调用序列
熵异常（过重复或过混乱）/ 使用了能力配置之外的工具。

**根因**（外部参照微软 agent-sre SRE 实践 + OWASP ASI-10）：
1. 失控循环（thrashing：反复调用相同工具无进展）；
2. 行为漂移（模型更新静默改变决策模式）；
3. 能力违规（agent 越出允许工具集）。

**解决步骤**：
```bash
# 1) 单 agent 行为体检（三信号：z-score / 熵 / 能力违规）
python - <<'EOF'
from src.agents.rogue_monitor import get_rogue_monitor
m = get_rogue_monitor()
for agent_id in ["generator-1", "debugger-1"]:
    for f in m.check(agent_id):
        print(agent_id, f.kind, f.detail)
EOF
# 2) 拉高判定阈值（误报时）
export ROGUE_AGENT_ZSCORE_LIMIT=5
# 3) 收紧能力配置（隔离越界工具）
#    调用侧构造 RogueAgentMonitor(allowed_tools={...}) 后上报事件
```

**预防措施**：
- 能力配置文件（允许工具列表）随 agent 注册；
- 成本可观测层（token 预算 + 反模式频率）与流氓检测同接
  workflow 收尾报告。

## 7. 文档可访问性与双语守卫

**症状**：文档链接 404 / 中英文章节漂移 / 日期不同步。

**解决步骤**：
```bash
# 1) 双语文档守卫（CI 同款口径）
python scripts/check_bilingual_docs.py
# 2) 文档链接体检（curl 抓取 raw 链接，Content-Type 验证）
for f in $(grep -ohE '\]\([^)]*\.md\)' README.md | tr -d '](' | tr -d ')'); do
  curl -sI "https://raw.githubusercontent.com/<org>/<repo>/main/$f" | head -1
done
```

**预防措施**：文档可访问性检查纳入 CI（所有 Markdown 链接返回
`text/plain` 且长度 > 0 才放行合并）；双语文档 H2 骨架漂移检测
（`check_bilingual_docs.py`）+ 关键段落语义相似度比对（后续批次）。

---

## 升级路径

| 问题域 | 第一响应 | 升级条件 |
|---|---|---|
| LLM 调用 | §1 冒烟 + 配置检查 | 多端点均 401 → 联系 provider |
| RAG | §2 重装 / 清目录 | 嵌入模型持续下载失败 → 回退内存模式 |
| 缓存 | §5 归属校验 + 标签隔离 | 投毒反复出现 → 全量清缓存 + 收紧语义阈值 |
| Agent 行为 | §6 体检 | 行为漂移无法归因 → 锁定模型版本 + 人工介入 |
