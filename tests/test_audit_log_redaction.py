"""
4.2 日志脱敏自动审计（scripts/gates/audit_log_redaction.py）的回归测试。

覆盖目标（对应提案 4.2"模拟敏感信息注入"的 CI 门禁）：
- 模拟注入未脱敏日志点（api_key/secret/password/Bearer/sk- 字段名）→ 审计报出可疑点；
- 同一日志点经 _redact / mask_sensitive_info 脱敏 → 审计不报；
- 干净仓库（跳过 tests/ 与示例目录）→ 零可疑点（CI 门禁基线）；
- exc_info=True 堆栈路径不算 finding（由 SensitiveFormatter 全局覆盖，仅标记）。
"""

from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.gates.audit_log_redaction import audit  # noqa: E402

# 审计目标目录（脚本内相对仓库根的路径）：
# - 全仓审计：传 PROJECT_ROOT（自动跳过 tests/ 等目录）
# - 注入审计：在 tmp 仓库的 src/ 下写文件，传 tmp 根
_REPO = PROJECT_ROOT


def _write(py_dir: str, filename: str, content: str) -> str:
    os.makedirs(py_dir, exist_ok=True)
    path = os.path.join(py_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def test_repo_baseline_zero_findings() -> None:
    """当前仓库 src/ 无未脱敏日志点（CI 门禁基线，回归护栏）。"""
    result = audit(_REPO)
    assert result.ok, f"基线应零可疑点，实际发现 {len(result.findings)}: {[f.file for f in result.findings]}"


def test_injected_unredacted_api_key_flagged(tmp_path) -> None:
    """模拟敏感信息注入：日志参数含 api_key= 且无脱敏 → 必须被检出。"""
    src_dir = str(tmp_path / "src")
    _write(
        src_dir,
        "leaky.py",
        (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n"
            "def call(api_key: str, url: str) -> None:\n"
            '    logger.info("calling %s with api_key=%s", url, api_key)\n'
        ),
    )
    result = audit(str(tmp_path))
    assert not result.ok
    assert any("leaky.py" in f.file for f in result.findings), [f.file for f in result.findings]


def test_injected_redacted_not_flagged(tmp_path) -> None:
    """同一敏感字段经 mask_sensitive_info 脱敏后输出 → 不应被检出。"""
    src_dir = str(tmp_path / "src")
    _write(
        src_dir,
        "safe.py",
        (
            "import logging\n"
            "from src.utils.logging_utils import mask_sensitive_info\n"
            "logger = logging.getLogger(__name__)\n"
            "def call(api_key: str, url: str) -> None:\n"
            '    logger.info("calling %s with api_key=%s", url, mask_sensitive_info(api_key))\n'
        ),
    )
    result = audit(str(tmp_path))
    assert result.ok, [f.line for f in result.findings]


def test_pytest_temp_dirs_skipped(tmp_path) -> None:
    """仓内 pytest basetemp 变体目录（.pytest_tmp_v1 等）必须被跳过。

    回归背景（2026-10-12 全量回归实测）：--basetemp 落在仓内时，测试夹具
    生成物（如 test_cache_security 故意注入假敏感串的
    test_injected_bearer_and_sk_*.py）被全仓审计误报为未脱敏日志点，
    阻断 test_repo_baseline_zero_findings（CI 门禁假红）。本测试锁定
    _should_skip 对 `.pytest_tmp*` 全部变体的前缀跳过。
    """
    for variant in (".pytest_tmp", ".pytest_tmp_v1", ".pytest_tmp_fresh"):
        _write(
            str(tmp_path / variant),
            f"test_injected_bearer_and_sk_{variant.strip('._')}.py",
            (
                "import logging\n"
                "logger = logging.getLogger(__name__)\n"
                "def call(api_key: str, url: str) -> None:\n"
                '    logger.info("calling %s with api_key=%s", url, api_key)\n'
            ),
        )
    result = audit(str(tmp_path))
    assert result.ok, f"pytest 临时目录应被跳过，实际发现：{[f.file for f in result.findings]}"
    # 反证：夹具内容本身确实可被检出（防测试因写法失效而假通过）——同内容放
    # 在非跳过目录（src/）下必须报出
    _write(
        str(tmp_path / "src"),
        "control_leak.py",
        (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n"
            "def call(api_key: str, url: str) -> None:\n"
            '    logger.info("calling %s with api_key=%s", url, api_key)\n'
        ),
    )
    control = audit(str(tmp_path))
    assert not control.ok, "同内容在 src/ 下应被检出（反证跳过逻辑未失效）"


def test_injected_bearer_and_sk_flagged(tmp_path) -> None:
    """Authorization: Bearer <token> 与 sk- 前缀凭证注入 → 必须被检出。"""
    src_dir = str(tmp_path / "src")
    _write(
        src_dir,
        "leaky2.py",
        (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n"
            "def call(token: str) -> None:\n"
            '    logger.debug("auth header Authorization: Bearer %s", token)\n'
            '    logger.debug("key sk-abcdef1234567890 sent")\n'
        ),
    )
    result = audit(str(tmp_path))
    assert not result.ok
    assert len(result.findings) >= 2, [f.line for f in result.findings]


def test_exc_info_not_a_finding(tmp_path) -> None:
    """exc_info=True 堆栈路径不算 finding（SensitiveFormatter 全局覆盖，仅标记复核）。"""
    src_dir = str(tmp_path / "src")
    _write(
        src_dir,
        "exc.py",
        (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n"
            "def run() -> None:\n"
            "    try:\n"
            "        1 / 0\n"
            "    except ZeroDivisionError:\n"
            "        logger.exception('run failed', exc_info=True)\n"
        ),
    )
    result = audit(str(tmp_path))
    assert result.ok, [f.line for f in result.findings]


def test_injected_field_variants_flagged(tmp_path) -> None:
    """O33 三类残余盲区注入 → 必须被检出（字段名变体 / AWS 裸值 / DSN 口令）。"""
    src_dir = str(tmp_path / "src")
    _write(
        src_dir,
        "leaky3.py",
        (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n"
            'logger.info("conn passwd=%s", "hunter2hunter2")\n'
            'logger.info("api key: %s", "abcdefghijklmnop1234")\n'
            'logger.info("access_token=%s", "eyJhbGciOiJIUzI1NiJ9.payload.sig")\n'
            'logger.info("AWS AKIAIOSFODNN7EXAMPLE leaked")\n'
            'logger.info("dsn mysql://root:pw0rd@dbhost/prod")\n'
        ),
    )
    result = audit(str(tmp_path))
    assert not result.ok
    assert len(result.findings) >= 5, [f.line for f in result.findings]


def test_benign_field_words_not_flagged(tmp_path) -> None:
    """字段名词根后不跟 :/= 的叙述性文本不误报（O33 收紧口径回归护栏）。"""
    src_dir = str(tmp_path / "src")
    _write(
        src_dir,
        "benign.py",
        (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n"
            'logger.info("password reset email sent")\n'
            'logger.info("API key rotation scheduled")\n'
            'logger.info("token 统计记录失败: %s", e)\n'
            'logger.info("mysql pool created")\n'
        ),
    )
    result = audit(str(tmp_path))
    assert result.ok, [f.line for f in result.findings]


def test_tests_dir_skipped(tmp_path) -> None:
    """tests/ 目录注入不扫描（测试代码常有意构造敏感串验证脱敏，避免误报）。"""
    tests_dir = str(tmp_path / "tests")
    _write(
        tests_dir,
        "leaky_test.py",
        ('import logging\nlogger = logging.getLogger(__name__)\nlogger.info("test api_key=%s", "secret")\n'),
    )
    result = audit(str(tmp_path))
    assert result.ok


# ─── H 轮（2026-10-16）：运行期脱敏自检（audit_runtime_redaction） ──────────────

import pytest  # noqa: E402

from scripts.gates.audit_log_redaction import AuditResult, audit_runtime_redaction  # noqa: E402


def test_runtime_selfcheck_passes_and_gate_ok() -> None:
    """接线后的正例：守卫真跑、两口径一致、13 条探针零盲区。"""
    result = AuditResult()
    audit_runtime_redaction(result)
    assert result.runtime_checked is True
    assert result.runtime_error == ""
    assert result.runtime_consistent is True, "mask_sensitive_info 与 redact_text 口径分叉"
    assert result.runtime_blind_spots == [], f"运行期兜底盲区：{result.runtime_blind_spots}"
    assert result.runtime_ok is True
    assert result.gate_ok is True


def test_unchecked_runtime_is_not_gate_ok() -> None:
    """缺席 ≠ 通过：没跑自检的 AuditResult 不得判门禁通过（G 轮口径）。"""
    result = AuditResult()
    assert result.runtime_checked is False
    assert result.runtime_ok is False
    assert result.gate_ok is False
    assert result.ok is True, "静态半区独立判定，不受运行期半区影响"


def test_blind_spot_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """探针原样通过 = 盲区，必须报出并判不通过（一致性守卫查不出这类问题）。"""
    monkeypatch.setattr("src.utils.logging_utils.mask_sensitive_info", lambda text: text)
    result = AuditResult()
    audit_runtime_redaction(result)
    assert result.runtime_checked is True
    assert len(result.runtime_blind_spots) > 0
    assert result.runtime_ok is False
    assert result.gate_ok is False


def test_path_divergence_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """两口径分叉（CVE-2026-59308 同源形态）必须报出并判不通过。"""
    monkeypatch.setattr("src.utils.logging_utils.verify_redaction_consistency", lambda samples: False)
    result = AuditResult()
    audit_runtime_redaction(result)
    assert result.runtime_consistent is False
    assert result.runtime_ok is False
    assert result.gate_ok is False


def test_selfcheck_exception_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """自检内部抛异常 → fail-closed（记 runtime_error 并判不通过），不得静默放行。"""

    def _boom(text: str) -> str:
        raise RuntimeError("脱敏模块损坏")

    monkeypatch.setattr("src.utils.logging_utils.mask_sensitive_info", _boom)
    result = AuditResult()
    audit_runtime_redaction(result)
    assert "脱敏模块损坏" in result.runtime_error
    assert result.runtime_checked is False
    assert result.runtime_ok is False
    assert result.gate_ok is False


def test_probe_corpus_locks_space_variant_field_names() -> None:
    """H 轮修掉的 3 个盲区留在语料里当回归锁（静态扫描器 O33 早已按该口径拦调用点）。"""
    from src.utils.logging_utils import mask_sensitive_info, redact_text, redaction_consistency_probes

    probes = redaction_consistency_probes()
    for shape in ("api key: ", "private key: ", "refresh token: "):
        assert any(p.startswith(shape) for p in probes), f"语料缺空格变体探针：{shape!r}"
    for shape in ("api key: ", "private key: ", "refresh token: "):
        probe = next(p for p in probes if p.startswith(shape))
        assert mask_sensitive_info(probe) != probe, f"运行期仍未脱敏：{probe!r}"
        assert redact_text(probe) != probe, f"降级链仍未脱敏：{probe!r}"
