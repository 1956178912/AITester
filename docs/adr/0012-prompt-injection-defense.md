# ADR-0012: Prompt Injection 防御层（输入检测 + 补丁安全校验）

## 状态

已接受（2026-09-29 批次落地，默认关闭保持历史口径）

## 背景

外部数据支撑：

- **Clinejection 事件**：恶意 issue 标题经 prompt injection 污染 AI
  分类机器人 → 构建缓存投毒 → 向 4,000 名开发者推送恶意 npm 版本。
- **PVE（Prompt-Validator-Executor）模式**：2026 年防御教义，对每步
  执行做安全评估——输入侧先验证、输出侧应用前校验。
- **OWASP Top 10 for Agentic Applications 2026**：ASI 类"注入 / 流氓
  agent"为高优先级风险，建议 `require-prompt-injection-guards` 与
  `no-unsafe-prompt-concatenation` 规则。

AITester 的 LLM 调用链接收三类外部可控文本：任务描述（用户输入）、
issue 标题（GitHub 集成场景）、检索入库内容（RAG 语料）。这些文本
直接拼进 prompt，此前无注入检测层；LLM 返回的修复补丁应用前也只做
语法/完整性静态校验（2.2 重采样口径），不检查危险操作语义。

## 决策

新增 `src/agents/injection_guard.py`（纯正则，零 LLM 成本，默认关）：

1. **输入侧（PVE 的 V 层）**：`detect_prompt_injection(text)` 扫描
   四类特征——指令覆盖话术（"忽略之前的所有指令"等中英双口径）、
   数据外传话术（凭证/文件 + 外发渠道组合）、编码绕过（base64 解码
   执行类）、上下文伪造（伪造 system 消息标记）。命中输出特征名列表，
   `build_injection_warning()` 转成追加到 prompt 的安全警示（检测 +
   警示，不静默吞掉，不自动阻断——阻断决策留给调用方/人工策略）。
2. **输出侧（PVE 的 E 前校验）**：`check_llm_patch_safety(patch)`
   静态扫描 LLM 返回补丁中的危险操作——`os.system`/`subprocess`
   等 shell 执行、`eval`/`exec` 动态求值、网络外连语句、`rm -rf`
   强破坏、凭证文件读取。命中即拒绝应用（findings 转拒绝理由，
   走 2.2 重采样 / 通用兜底，同口径）。
3. **开关**：`INJECTION_GUARD_ENABLE` 默认 `false`——关闭时两个函数
   恒返回空列表，调用方行为与历史逐字节一致（保守口径）。

## 后果

- 正面：LLM 调用链获得 PVE 双层防御（输入警示 + 输出校验），封堵
  Clinejection 式"注入 → 缓存投毒"路径在本项目的进入面；特征集
  保守（高召回话术 + 明确危险 API 组合），误伤面小（合法测试
  代码不命中）。
- 负面：正则特征集无法穷举所有注入变体（对抗性绕过是长期猫鼠
  游戏）——定位为**纵深防御层**而非唯一防线；执行沙箱
  （`credential_scrub` 环境变量剔除 + 容器隔离）仍是凭证泄露的
  最后一道闸。误报（如任务描述恰好含"忽略规则"字样的正常讨论）
  只追加警示不阻断，影响面有限。
- 接线现状（批次内）：防御层 + 测试 + 开关就位；`_debugger_node`
  / 生成链的调用点接线留后续批次（开关默认关，接线不改变历史行为）。

## 参考

- 改进建议 6.4（Prompt Injection 防御体系）；
- ADR-0011（缓存投毒读侧防御，同批次）；
- `tests/test_injection_guard.py`（输入/输出双侧 + 开关口径回归）。
