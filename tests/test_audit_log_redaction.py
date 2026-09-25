"""
4.2 日志脱敏自动审计（scripts/audit_log_redaction.py）的回归测试。

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

from scripts.audit_log_redaction import audit  # noqa: E402

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
