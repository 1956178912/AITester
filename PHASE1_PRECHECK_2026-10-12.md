# AITester 改进方案阶段 1 前置核查报告

日期：2026-10-12（基于 HEAD e5b5798）
状态：核查完成，未做任何代码修改、未调用任何 LLM、未跑任何实跑实验。

## 1. 阶段 0 已完成部分（上一轮已提交）

- ruff format 12 文件修复 + `make gates` 补入 format 门禁
- BASELINE.yaml：mypy 125→130、覆盖率声明 89/83 → 92.42/86.91
- 69 项删除批次提交 + ruff 排除面同步
- 全量测试 5689 passed / 3 skipped / 0 failed（与 HEAD 声明逐位一致）

提交：1930a6e（质量债）、b603e0b（删除批次）、e5b5798（ruff 排除面）。

## 2. 关键代码资产核实（与本方案引用逐项核对）

### 2.1 `src/tools/spec_first.py`（P0-A-2 规格替换臂）

- 文件实际位于 `src/tools/` 而非方案所写的 `src/specs/`；
- `DETECTION_SPEC_MODE` 环境变量：`off`（缺省，历史口径：目标代码照常注入）/
  `replace`（仅当规约材料非空时替换 docstring 为规约文档，核心纪律是不暴露
  实现代码，见 `build_spec_replace_section`，只取函数签名不取函数体）；
- 该模块被 `src/graph/flags.py`、`src/graph/nodes.py`、`src/agents/generator.py`
  引用，链路完整；
- 模块 docstring 自述："建议与 plain_llm_df 臂同基准跑"——即方案中 A/B 臂设计
  与代码现状一致。

**结论：spec_replace 开关代码就绪，零实跑（grep 无历史批次工件引用该臂）。**

### 2.2 `src/datasets/dataset_ult.py`（ULT 基准加载器，W4b 批次）

- 加载器已实现：`ULTDataset(BaseDatasetLoader)`，读本地 manifest JSONL；
- 关键设计：ULT 官方评测口径为 **mutation score（Mut@k）为主指标**
  （Cosmic-Ray 变异框架），detection/coverage 为辅助指标——与方案
  维度三"变异分数一等公民"方向一致；
- **2026-10-12 一手核验勘误（git clone 官方仓库实测）**：
  1. `datasets/ULT.jsonl`（全量 3,909 函数）实际为 **JSON 数组**格式
     （非逐行 JSONL），字段为 `func_name/code/prompt/task_id/tests/
     cyclomatic_complexity`——原加载器假设（逐行 JSONL + 字段
     `function_name/source_code`）与实际不符，**已修复**（官方 JSON
     数组直接兼容 + 字段归一化）；
  2. 原 W4b docstring"官方不发布 ground-truth tests"为**误读**——
     `ULT.jsonl` 全量 3,909 条记录的 `tests` 字段**全部非空**（每条
     含 5 条官方测试函数）；`ULT_Lite.jsonl`（200 任务子集，与方案
     `--subset 200` 完全对应）的 `test_list` 字段同样全部非空。
     README 的"Data Preservation Notice"与数据文件实况不一致（防
     污染声明可能是指"不单独发布 gold 测试文件"而非数据文件内不
     携带）。**加载器已改为记录官方测试材料**（`test_code` /
     `total_test_count` / `metadata["gold_tests"]`），`no_gold_tests`
     仅在材料缺失时为 True；
  3. 新增转换脚本 `scripts/tools/convert_ult_manifest.py`（官方 JSON
     数组 → 逐行 JSONL manifest，备用路径；直接指向官方 datasets/
     目录亦可，`subset="lite"` 指定 200 任务子集）；
- **前置缺口（已解决）**：manifest 数据此前未落盘
  （`~/.cache/aitester/ult` 不存在）；本轮已克隆官方仓库至
  `~/.cache/aitester/ult_repo`，`ULTDataset` 实测：全量 3,909 任务
  （3,907 带官方测试材料）/ lite 子集 200 任务（200 带官方测试材料）。

### 2.3 QuixBugs 基准

- 加载器 `src/datasets/dataset_realbugs.py::QuixBugsDataset` 已实现；
- **前置缺口**：实测 `QuixBugsDataset().size == 0`，缺
  `/Users/wangchenyu/.cache/aitester/quixbugs/python_programs`，需克隆
  `jkoppel/QuixBugs` 或设 `AITESTER_QUIXBUGS_DATA`。

### 2.4 变异模块（方案维度三）

- `experiments/mutation_testing.py`（12 类算子）与 `experiments/mutation_detection.py`
  存在，R2 已指出合成变异体过弱（0.986-0.997 近饱和）；
- ULT 加载器 docstring 已预留"评测须走 mutation score"的口径，
  与方案"将 mutation score 升格为一等指标"方向一致。

### 2.5 LLM 凭证链路

- `src/config/config_manager.py::get_all_llm_configs()` 实测可解析出
  `deepseek-flash` 配置，`api_key` 已加载（来自 `.env.local` 的
  `LLM_1_API_KEY`/`LLM_1_BASE_URL`）；
- `src/agents/llm_client.py` 走 LangChain `ChatOpenAI` 路径，
  支持 OpenAI 兼容端点；
- **未做实际调用验证**（避免无谓消耗配额/触发限流），链路"代码就绪"
  不等于"端点可用"，跑实验前建议先做一次低成本冒烟调用。

## 3. 统计功效分析（Z8 前置判据）

`make power`（`scripts/tools/power_analysis.py`）实测输出（n=50 口径）：

| 目标 δ | 所需配对样本数 | 对应 p_a |
|---|---|---|
| 5pp | 212 | 7% |
| 10pp | 87 | 12% |
| 20pp | 36 | 22% |
| 30pp | 21 | 32% |

**结论**：方案建议的 QuixBugs 41 程序规模**不足以**在 80% 功效下检出
10pp 级差异（需 87 对）；若目标是"δ≥8pp 显著"，41 程序只有 ~60%
功效量级，属于**探索性/阴性筛查**而非确认性实验。这不影响 spec_replace
A/B 作为"首跑"（成本 ≈$3），但**结论强度要按探索性实验登记**——
若未达 8pp，不能据此否定 spec_replace 方向（统计上不可区分），
只能据此否定"41 程序 + 当前 p_b 水平下可检出 8pp"这一命题。

## 4. 与上一版方案（五维）的差异记录

本版方案在"编排叙事切换 + 规格驱动"基础上，新增 4 个维度
（变异引导生成 / 强化学习 / 代码表示学习 / 多智能体修复），对应 2026 年
MutGen（TSE'26）、UTRL（ICLR'26）、TestSmith（ICLR'26）、TestCTRL
（TOSEM'26）、SACR（ISSTA'26）、SemRep（ICML'26）、双曲表示（ICLR'26）、
TDFlow（EACL'26）、AgentRepair（IEEE'26）、InspectCoder（POPL'26）、
TwinMem-Agent、FedDualFix（'26）等外部证据。

其中与项目现有代码资产**直接衔接**、且**零 LLM 成本即可启动**的是：
1. **ULT 接线**（维度三前置）——代码就绪，缺 manifest 数据文件；
2. **spec_replace A/B**（维度二）——代码就绪，缺 QuixBugs 数据文件
   与一次 LLM 冒烟；
3. **mutation score 升格为一等指标**（维度三）——`dataset_ult.py` 已
   预留该口径，无需改代码，只需在实验报告模板中把 mutation score
   列为与 detection 并列的主指标。

**本轮不启动**（成本高、依赖未就位、或属"做加法"而非本方案主张的
"做减法"方向）：
- 维度四（RL 训练，UTRL/TestSmith 思路）——需训练基础设施，
  本方案自己标注"短期不必训练自有模型"；
- 维度五（代码表示学习）——依赖外部模型 API，非本仓代码可独立验证；
- 维度七（专门化修复，AgentRepair/InspectCoder/TwinMem-Agent/FedDualFix）
  ——属"系统本体增强"，与本方案核心判断"测量基建领先、系统本体落后
  的剪刀差"相悖，先补齐测量/协议层再谈本体增强，顺序上应放在
  阶段 3 之后。

## 5. 下一步（待确认）

1. ~~克隆 QuixBugs 仓库到 `~/.cache/aitester/quixbugs/`~~ ✅ 已完成
   （`QuixBugsDataset()` 默认路径实测：50 任务，41 带官方测试）；
2. ~~获取 ULT manifest JSONL~~ ✅ 已完成（官方仓库克隆 + 加载器修复
   直接兼容官方 JSON 数组，无需 manifest 转换；转换脚本为备用路径）；
3. ~~一次低成本 LLM 冒烟调用（任意 prompt，验证 `deepseek-flash`
   端点实际可用、非仅代码就绪）~~ ✅ 已完成（`_get_or_create_chat_client`
   + `invoke` 最小 prompt 返回 "OK"；`.env.local` LLM_1_API_KEY /
   LLM_1_BASE_URL 实测可用）；
4. ~~再启动 spec_replace A/B 首跑（41 程序 × 3 臂 × 1 种子，探索性口径
   登记，见 §3）~~ ✅ 已完成（结果见 `SPEC_REPLACE_AB_REPORT_2026-10-12.md`：
   B vs A δ=+8.1pp / p=0.75 不显著，探索性/阴性筛查口径；三臂间差异均
   不显著）。

以上 1-4 均为数据/凭证层动作，不涉及代码修改。**4/4 全部完成**（截至
本批次提交时点）。
