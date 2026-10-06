"""AF 批次测试（2026-10-06 第十一轮审查第二轮自主收口）。

覆盖四项（对应第十一轮报告 N10/N11/N12 核查结论与 DATA_CARD 待办闭环）：
- AF-A（N11 更正佐证）：容器默认加固已由 S3 批落地——锁定 ci 层面的
  事实由 tests/test_sandbox_hardening.py 承担，此处不重复；本文件只锁
  N12/N10/AF-D 三项文档与静态不变量。
- AF-B（N10 更正佐证）：P1-7 lock 全量审计步骤在位 + 审计工件上传
  清单含 pip_audit_lock.json（AF 批补入的真实缺口）。
- AF-C（N12 阻塞登记）：ADR-0016 修订记录 2 存在——记录"src 层统一
  执行原语"被 Mimosa 污点扫描结构性阻塞的细节与解除路径。
- AF-D problem_statement 消费不变量（DATA_CARD 待办闭环）：泄漏通道
  字段仅注入扫描消费、不进任何 prompt——静态守卫锁定消费面，新增
  prompt 消费必须显式更新 DATA_CARD 与本测试。

全部纯 stdlib / 零 LLM / 零网络 / 零子进程。
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


# ─── AF-D：problem_statement 无 prompt 消费不变量 ────────────────────────────


class TestProblemStatementNoPromptConsumption:
    """DATA_CARD.md"泄漏通道现状"登记的不变量锁定。

    problem_statement（= pattern description，字面上是缺陷答案）当前仅被
    nodes.py 注入扫描消费、不进任何 prompt。本测试锁定消费面——任何新增
    prompt 侧消费（planner/executor/debugger 插值等）都会使本测试失败，
    要求开发者显式更新 DATA_CARD 登记并重新评估泄漏口径（防登记静默失真）。
    """

    @staticmethod
    def _lines_with(path: Path, needle: str) -> list[tuple[int, str]]:
        text = path.read_text(encoding="utf-8")
        return [(i, line) for i, line in enumerate(text.splitlines(), 1) if needle in line]

    def test_prompt_templates_zero_occurrence(self) -> None:
        """src/prompts/ 模板层零出现（prompt 平面无该字段）。"""
        prompts_dir = _ROOT / "src" / "prompts"
        offenders = [p.name for p in prompts_dir.glob("*.py") if self._lines_with(p, "problem_statement")]
        assert offenders == [], f"src/prompts 出现 problem_statement（泄漏面扩大）：{offenders}"

    def test_agents_layer_zero_occurrence(self) -> None:
        """src/agents/ 零出现（planner/generator/debugger 不读该字段）。"""
        agents_dir = _ROOT / "src" / "agents"
        offenders = [p.name for p in agents_dir.glob("*.py") if self._lines_with(p, "problem_statement")]
        assert offenders == [], f"src/agents 出现 problem_statement（泄漏面扩大）：{offenders}"

    def test_graph_layer_consumption_whitelist(self) -> None:
        """src/graph/ 消费白名单：state.py（schema 声明层）+ nodes.py。

        nodes.py 的每一处命中必须是注释行或注入扫描块的唯一 state.get
        读取——运行时消费点恰为一个（注入特征扫描），无其他用途。
        """
        graph_dir = _ROOT / "src" / "graph"
        allowed_files = {"state.py", "nodes.py"}
        hits: dict[str, list[tuple[int, str]]] = {}
        for p in sorted(graph_dir.glob("*.py")):
            found = self._lines_with(p, "problem_statement")
            if found:
                hits[p.name] = found
        assert set(hits) <= allowed_files, f"src/graph 出现白名单外消费文件：{sorted(set(hits) - allowed_files)}"
        if "nodes.py" in hits:
            for lineno, line in hits["nodes.py"]:
                stripped = line.strip()
                is_comment = stripped.startswith("#")
                is_injection_read = 'state.get("problem_statement")' in line
                assert is_comment or is_injection_read, (
                    f"nodes.py:{lineno} 出现非白名单 problem_statement 消费"
                    f"（新 prompt 消费须先更新 DATA_CARD 与本测试）：{stripped[:120]}"
                )
            # 唯一运行时读取 = 注入扫描块（若 >1 处 state.get 读取即登记失真）
            read_lines = [ln for _, ln in hits["nodes.py"] if 'state.get("problem_statement")' in ln]
            assert len(read_lines) == 1, (
                f"nodes.py 出现 {len(read_lines)} 处 problem_statement 运行时读取（登记口径=1）"
            )

    def test_data_card_registration_current(self) -> None:
        """DATA_CARD 登记与实现一致：仍声明"仅注入扫描消费、不进 prompt"。"""
        card = (_ROOT / "docs" / "DATA_CARD.md").read_text(encoding="utf-8")
        assert "problem_statement" in card
        assert "注入扫描消费" in card


# ─── AF-B：P1-7 lock 全量审计在位 + 工件上传守卫 ─────────────────────────────


class TestDependencyAuditCoverage:
    """第十一轮 N10 更正的佐证锁定：传递依赖审计不缺位、审计工件可排障。"""

    def test_lock_full_audit_step_present(self) -> None:
        """P1-7 步骤在位：requirements.lock 全量审计（阻断式）。"""
        ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "pip-audit -r requirements.lock" in ci
        # lock 审计步骤本身不得退回 --no-deps（全量口径是本步骤的存在意义）
        lock_line = next(line for line in ci.splitlines() if "pip-audit -r requirements.lock" in line)
        assert "--no-deps" not in lock_line

    def test_lock_audit_json_uploaded(self) -> None:
        """AF 批修复：pip_audit_lock.json 进入审计工件上传清单。

        此前只上传顶层报告——lock 审计失败时无 JSON 排障材料。
        """
        ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        upload_block = ci.split("name: security-reports-")[1]
        assert "pip_audit_latest.json" in upload_block
        assert "pip_audit_lock.json" in upload_block
        assert "gitleaks_report.json" in upload_block


# ─── AF-C：N12 阻塞登记守卫 ─────────────────────────────────────────────────


class TestADR0016Revision2:
    """ADR-0016 决策 5 收敛尝试的阻塞登记（防静默遗忘）。"""

    def test_revision_2_documents_blocker(self) -> None:
        adr = (_ROOT / "docs" / "adr" / "0016-orchestration-container-repositioning.md").read_text(encoding="utf-8")
        assert "2. 2026-10-06 AF" in adr
        assert "Mimosa" in adr
        assert "experiments/_m1_metrics" in adr
