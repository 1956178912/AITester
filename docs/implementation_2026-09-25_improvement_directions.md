# 改进方向实施清单（2026-09-25 批次）

> 对应 `docs/assessment_2026-09-25_improvement_directions.md` 的"真实剩余工作"清单。
> 本批次落地其中 5 项（#1/#2/#3/#4/#6），#5（多候选 A/B 实验数据）属实验执行工作，需跑
> `reproduce.sh` 对比批次后入论文，不在代码批次内。

## 本批次改动一览

### 1. 3.3 位置感知迭代修复（LoopRepair 式先定位再补丁）——真实功能缺口
- 新增 `POSITION_AWARE_REPAIR_ENABLE` 开关（默认 false，保持历史实验口径）：
  `src/agents/debugger.py`（`_position_aware_repair_enabled` / `_locate_repair_focus` /
  `_build_position_aware_prompt_section`）+ `debug()` 主流程接线 + 返回 dict 新增
  `position_aware_focus` 键。
- 定位口径（纯静态、不耗 LLM token）：复用 `error_classifier` 已提取的 traceback 行号/
  语法错误行列，经 AST 定位到"包围异常行的最短区间函数"，生成位置感知修复指引注入
  prompt；无法定位（无行号/AST 损坏/跨文件）时自动降级为常规全文件修复。
- state/nodes 接线：`src/graph/state.py` 新增 `position_aware_focus` 字段，
  `src/graph/nodes.py` debugger 节点写入。
- `.env.example` 新增 3.3 区开关说明。
- 测试：`tests/test_debugger.py` 新增 `TestPositionAwareRepair`（9 用例，覆盖开关默认值、
  定位命中/降级/跨文件保护/语法损坏、debug() 接线与 prompt 注入）。

### 2. 5.2 文档同步：错误分类 12 类 → 14 类
- 同步 `README.md` / `README.en.md` / `docs/api_reference.md` / `docs/api_reference.en.md`
  / `docs/failure_analysis.md` 中"十二类/12 类"表述为十四类，补
  `EXECUTION_TRACE_MISSING` / `MULTI_CANDIDATE_ALL_REJECTED` 两类的枚举表行与判定
  优先级说明（`patch_rejected > rag_empty > trace_missing > multi_rejected`）。
- `docs/history/*` 为历史快照，有意保留 12 类表述不改。

### 3. 5.1 补 cross_batch_comparison 单批次边界测试
- `tests/test_smell_detection_v2.py`：补强 `test_single_batch_no_trend`（加
  `resolved_categories`/`failure_trend` 断言）、新增 `test_single_batch_all_passed_empty_trend`
  与 `test_empty_summaries_list`。
- `tests/test_failure_kb.py`：补强单批次断言、新增 `test_empty_summaries_list`。

### 4. 4.2 日志脱敏自动检查钩子
- `.pre-commit-config.yaml` 新增 local hook `audit-log-redaction`（命中
  `src/**/*.py` / `experiments/**/*.py` 时跑 `scripts/audit_log_redaction.py`，
  发现未脱敏日志点退出码 1 阻断提交）。
- `.github/workflows/ci.yml` 新增 "Audit log redaction (4.2)" 步骤（与 pre-commit 同一
  脚本，本地/远端口径一致）。
- 新增"模拟敏感信息注入"回归测试 `tests/test_audit_log_redaction.py`（6 用例：
  仓库基线零可疑点、未脱敏注入必检出、脱敏后不检出、Bearer/sk- 凭证检出、
  exc_info 堆栈不报 finding、tests/ 目录跳过）。

### 5. 2.1 接入真实嵌入钩子（CodeBERT/sentence-transformers 可选依赖）
- 新增 `src/utils/embedding_utils.py`（零新增硬依赖）：
  - `embed_text()`：按 `EMBEDDING_BACKEND` 环境变量选择后端
    （auto：sentence-transformers > chromadb DefaultEmbeddingFunction > None；
    none：强制 None 保持词袋保守口径，便于 A/B 对照）；
  - `cosine_similarity()`：numpy 余弦（项目已依赖 numpy），缺失时纯 Python 回退，
    非负夹取与词袋余弦口径可比；
  - `backend_name()`：供污染检测报告标注语义级来源。
- `experiments/contamination_check.py` 接线：`_embed_code` 委托 `embedding_utils.embed_text`
  （调用期惰性加载，保持 experiments 包零默认外部硬依赖）；
  `patch_semantic_similarity` 新增 `semantic_source` 字段（"embedding"/"token_bag"）；
  渲染层标注语义级来源。
- 测试：`tests/test_embedding_utils.py`（12 用例，覆盖余弦数值正确性、零向量/维度
  不一致边界、numpy 回退、后端选择、空文本保护、semantic_source 传导、
  风险等级计算忽略字符串标注）。

## 验证
- 全量回归：`pytest tests/ -q`（见会话记录，全部通过）
- 受影响子集：test_debugger（38）/ test_workflow（75 含 debugger）/
  test_smell_detection_v2 / test_failure_kb / test_audit_log_redaction（6）/
  test_contamination_check+multidim（40）/ test_embedding_utils（12）
- lint：`ruff check` 改动文件全部通过。
