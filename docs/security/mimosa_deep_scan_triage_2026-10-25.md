# Mimosa 深度安全扫描分诊报告（2026-10-25）

- 扫描：`scan-2026-10-25T03-24-58.785Z-9ddf88142008`（deep、静态边界、193 包、
  seal `sha256:be3ea0b1…f01c`）；报告与工件在 `~/.mimosa/security-scans/`（仓库外）。
- 发现：**160 项**（high 121 / medium 10 / low 29）+ 依赖公告 3 项。
- 分诊结论：**0 项需改产品代码**；1 项依赖补丁组已升级；其余为设计内形态、
  假阳性或既有登记决定。逐类处置如下。

## 分诊矩阵

| 类别 | 数量 | 处置 | 依据 |
|---|---|---|---|
| path-traversal | 100 | **设计内接受** | 命中点全部在基准执行链（executor_repo / run_benchmark / mdo / executor_modes 等）：路径来自内部任务数据与任务 ID 派生文件名，本工具是本地研究基准器，无不可信外部输入面；不可信代码执行由 kernel_sandbox + 凭证剥离 + 子进程超时三重防线承担（tests/test_untrusted_exec_env 等锁面在位） |
| insecure-randomness | 29 | **设计内接受** | 实验统计的种子化随机（bootstrap/抽样/合成难度，`random.seed` 受控），非密码学用途 |
| code-injection | 7 | **产品本体功能** | runtime_probe×3 / kernel_sandbox×2 = 沙箱内执行 LLM 生成代码正是被测产品功能（沙箱与命名契约白名单在位）；e2e_probes×2 = 测试该功能的探针 |
| hardcoded-credential | 7 | **假阳性** | 逐条核对均为显式假 key（`sk-e2eProbeFake…` / `sk-openaiFake…` / `sk-deepseekFake…` / `sk-placeholder…` / example 占位），真实凭证经 .env.local 注入且不入库（推送前抽查复确认） |
| ssrf | 4 | **设计内接受** | check_citations×2 = 文档链接检查器（固定 https 文档目标）；check_quota = 运维者配置的 LLM base_url 探测；patch_applier:625 命中点在**注释文本**（危险调用检测的说明文字），假阳性 |
| sql-injection | 1 | **假阳性（有守卫）** | init_db.py:70 `USE \`{db}\``——db 名来自 .env，第 65-66 行已有 `[A-Za-z0-9_]+` 白名单拒绝其余输入，且 SQL 标识符本身不可参数化；代码注释已载明该设计 |
| other-security | 12 | **测试数据/研究脚本** | data/quixbugs 的 Java 文件是 QuixBugs 数据集原文（含 JavaDeserialization 教学样例）；其余为实验脚本的非网络形态 |
| 疑似跨文件污点 | 9 | **静态 advisory** | 环境变量→process_utils 路径拼接链；运维者控制的环境变量（.env）不属于不可信输入面，与 path-traversal 同处置 |

## 依赖公告处置（pip-audit 实测复核）

| 包 | 公告 | 处置 |
|---|---|---|
| filelock 3.32.2 | CVE-2026-112907/112913/112940 | **已升级 4.2.1**（lock 行同步；仅 datasets/huggingface_hub 传递依赖、本地缓存用途，导入与受影响面 1,067 例测试 + 全量复验绿） |
| gitpython 3.2.0 | CVE-2026-114145 | venv 升 3.2.1（不在 lock，CI 面无此钉版） |
| setuptools 84.0.0 | GHSA-xmj3-9gf7-h52w | venv 升 84.1.0（同上） |
| nltk 3.10.3 | PYSEC-2026-3740 | venv 升 3.10.4（同上） |
| chromadb 1.5.9 | PYSEC-2026-311/3813/3814/3815 等 5 项 | **维持 BZ 轮登记豁免不动**（升级会破坏向量库兼容性，当时决策在案） |

## 验证

- `pip_audit -r requirements.lock`：除 chromadb 5 项既有豁免外 **0 漏洞**；
  `check_lock_sync` rc=0。
- 受影响面（dataset/corpus/fingerprint/token/otel 关键字 1,067 例）+ 全量
  **12,458 passed / 287 skipped / 0 failed**（filelock 4.2.1 后）。

## 边界

- 本分诊基于静态证据与人工核对（假 key 逐条、SSRF 命中行逐行、SQL 守卫上下文）；
  未做运行时渗透验证（evidenceBoundary=static_only）。
- Mimosa 提交钩子的 `scanner_enobufs` 提示（提交前未获完整扫描结论）由本报告
  补齐闭环：完整扫描 + 分诊 + 处置已落盘。
