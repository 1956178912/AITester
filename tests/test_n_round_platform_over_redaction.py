"""D3 回归锁：日志脱敏"长 base64"模式不得误伤文件系统路径（N-1 上报，2026-10-17）。

背景
----
`src/utils/logging_utils.py` 的"长 base64（≥40 位）"模式字符类含 `/`，把点号后
连续长路径段整体当成 base64 密钥：

    mask_sensitive_info('/tmp/.cache/aitester/quixbugs/correct_python_programs')
    → '/tmp/.<REDACTED_KEY>'

真实症状：`main.py check-dataset quixbugs` 打印
`gold 修复版目录：/Users/<user>/.<REDACTED_KEY>`（诊断可读性下降，非泄露）。

修复（D3）：base64 模式边界锚定（前接路径上下文 `/ . _ ~ + -` 或 `/` 起始不匹配）
+ 内容判定 `_redact_base64_like`（多级路径 / 小写路径段原样返回；含 `+/=` 或
混合大小写的真实 base64 密钥仍脱敏）。

本文件锁定：
1. **负控**：`.cache/...`、`.venv/...`、长临时目录路径、`.env/.ssh` 路径段不被
   整体脱敏（mask / fallback / redact_text / Filter / Formatter 五条路径）；
2. **正控**：真实密钥族（sk-/ghp_/AKIA/长 hex/长 base64/JWT/Bearer/大写凭证赋值）
   仍必须被脱敏；
3. **端到端**：`main.py check-dataset quixbugs` 的 gold 路径可读（数据缺失时 skip）；
4. **既有口径**：跨路径一致性守卫（verify_redaction_consistency）保持通过。
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest

from src.utils.logging_utils import (
    SensitiveFilter,
    SensitiveFormatter,
    fallback_mask_sensitive_info,
    mask_sensitive_info,
    redact_text,
    redaction_consistency_probes,
    verify_redaction_consistency,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: 真实症状形态的路径（点号目录 + 长路径段；修复前被误伤）。
_PATH_SAMPLES = [
    "/tmp/.cache/aitester/quixbugs/correct_python_programs",
    "/Users/someuser/Workspace/AITester/.venv/bin/python",
    "/var/folders/pj/xxxx/T/aitester_m1_bitcount_07q05sj_",
    "/Users/someuser/.cache/aitester/quixbugs/correct_python_programs/python_programs",
    "/Users/someuser/Workspace/AITester/experiments/results/e2e_probe_platform_20261017",
]

#: 真实密钥族（占位假值；必须仍被脱敏）。
_KEY_SAMPLES = {
    "sk": "sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890",
    "ghp": "ghp_" + "aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5zA7bC9dE1fG3hI5",
    "aws": "AKIAPLACEHOLDERXXXXX",
    "hex40": "0123456789abcdef0123456789abcdef0123456789abcdef",
    "base64_mixed_56": "AbCdEfGhIjKlMnOpQrStUvWxYz123AbCdEfGhIjKlMnOpQrStUvWxYz01",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwbGFjZWhvbGRlciJ9.cGxhY2Vob2xkZXJzaWduYXR1cmU",
}


def _mask_via_handler(record: logging.LogRecord) -> str:
    """经 SensitiveFilter + SensitiveFormatter 处理一条 LogRecord（真实 handler 链路）。"""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(SensitiveFormatter("%(message)s"))
    handler.addFilter(SensitiveFilter())
    handler.handle(record)
    return stream.getvalue()


# ─────────────────────────── 1. 负控：路径零误伤 ───────────────────────────


class TestPathNotOverRedacted:
    @pytest.mark.parametrize("path", _PATH_SAMPLES)
    def test_mask_sensitive_info_keeps_paths(self, path: str) -> None:
        """D3 根因回归：点号后长路径段不得被当成 base64 密钥。"""
        assert mask_sensitive_info(path) == path, f"路径被过度脱敏：{mask_sensitive_info(path)}"

    @pytest.mark.parametrize("path", _PATH_SAMPLES)
    def test_fallback_keeps_paths(self, path: str) -> None:
        assert fallback_mask_sensitive_info(path) == path

    @pytest.mark.parametrize("path", _PATH_SAMPLES)
    def test_redact_text_keeps_paths(self, path: str) -> None:
        assert redact_text(path) == path

    @pytest.mark.parametrize("path", _PATH_SAMPLES)
    def test_sensitive_filter_formatter_keep_paths(self, path: str) -> None:
        """SensitiveFormatter（trace JSONL/日志兜底路径）同样不得误伤路径。"""
        record = logging.LogRecord("d3_probe", logging.INFO, __file__, 0, "gold 修复版目录：%s", (path,), None)
        output = _mask_via_handler(record)
        assert path in output, f"handler 链路过度脱敏：{output!r}"
        assert ".<REDACTED_KEY>" not in output

    def test_env_and_ssh_path_segments_not_wholly_redacted(self) -> None:
        """`.env`/`.ssh` 路径段不得被整体误伤（其值/内容脱敏由凭证模式负责）。"""
        samples = [
            "/home/someuser/project/.env",
            "/home/someuser/project/.env.local",
            "/home/someuser/project/.ssh/id_rsa",
            "/home/someuser/project/.venv/lib/python3.14/site-packages",
        ]
        for sample in samples:
            assert mask_sensitive_info(sample) == sample, f"路径段被整体脱敏：{sample} → {mask_sensitive_info(sample)}"

    def test_mixed_line_path_keeps_while_secret_redacted(self) -> None:
        """同一行内：长路径保留 + 真实密钥脱敏（不能因路径判定放宽整体脱敏）。"""
        key = _KEY_SAMPLES["sk"]
        text = f"gold dir {_PATH_SAMPLES[0]} used key {key}"
        result = mask_sensitive_info(text)
        assert _PATH_SAMPLES[0] in result, f"路径被误伤：{result}"
        assert key not in result, f"真实 sk- 密钥泄漏：{result}"
        assert "<REDACTED_API_KEY>" in result

    def test_39_char_base64_like_not_redacted(self) -> None:
        """边界：39 位（<40 阈值）不脱敏（避免把普通长标识误判密钥）。"""
        token = ("AbCdEfGhIjKlMnOpQrStUvWxYz123AbCdEfGhIjKlMnOp")[:39]
        assert len(token) == 39
        assert token in mask_sensitive_info(f"id {token} end")


# ─────────────────────────── 2. 正控：真实密钥族仍脱敏 ───────────────────────────


class TestRealSecretsStillRedacted:
    @pytest.mark.parametrize(
        ("label", "expected_marker"),
        [
            ("sk", "<REDACTED_API_KEY>"),
            ("ghp", "<REDACTED_KEY>"),
            ("aws", "<REDACTED_AWS_KEY>"),
            ("hex40", "<REDACTED_KEY>"),
            ("base64_mixed_56", "<REDACTED_KEY>"),
            ("jwt", "<REDACTED_JWT>"),
        ],
    )
    def test_primary_path_redacts_key_families(self, label: str, expected_marker: str) -> None:
        key = _KEY_SAMPLES[label]
        result = mask_sensitive_info(f"token {key} end")
        assert key not in result, f"真实 {label} 密钥泄漏：{result}"
        assert expected_marker in result

    @pytest.mark.parametrize("label", ["sk", "hex40", "base64_mixed_56"])
    def test_fallback_path_still_redacts(self, label: str) -> None:
        key = _KEY_SAMPLES[label]
        assert key not in fallback_mask_sensitive_info(f"token {key} end")

    def test_bearer_and_credential_assignment_still_redacted(self) -> None:
        bearer = "Authorization: Bearer placeholderToken0000"
        assert "placeholderToken0000" not in mask_sensitive_info(bearer)
        upper = "MYSQL_PASSWORD=placeholderValue"
        assert "placeholderValue" not in mask_sensitive_info(upper)

    def test_path_with_key_after_is_still_redacted(self) -> None:
        """路径后拼接真实密钥：路径保留、密钥脱敏（内容判定不误放过）。"""
        key = _KEY_SAMPLES["hex40"]
        text = f"{_PATH_SAMPLES[1]} token={key}"
        result = mask_sensitive_info(text)
        assert _PATH_SAMPLES[1] in result
        assert key not in result


# ─────────────────────────── 3. 既有口径一致性 ───────────────────────────


class TestRedactionConsistency:
    def test_verify_redaction_consistency_still_passes(self) -> None:
        """跨路径脱敏一致性守卫（正典探针语料）不因 D3 修复回退。"""
        probes = redaction_consistency_probes()
        assert probes
        assert verify_redaction_consistency(probes) is True

    def test_no_redacted_marker_in_normal_paths(self) -> None:
        """普通路径/普通文本整行不含占位符（防止"处处脱敏"退化）。"""
        text = (
            "QuixBugs 加载完成：50 个任务（gold 修复版目录：/Users/u/.cache/aitester/quixbugs/correct_python_programs）"
        )
        assert not re.search(r"<REDACTED", mask_sensitive_info(text))


# ─────────────────────────── 4. 端到端：check-dataset CLI 可读 ───────────────────────────


class TestCheckDatasetCliOverRedaction:
    def test_check_dataset_gold_path_readable(self) -> None:
        """真实症状回归：CLI 输出的 gold 路径不得含 `.<REDACTED_KEY>`。"""
        proc = subprocess.run(
            [sys.executable, "main.py", "check-dataset", "quixbugs"],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(_REPO_ROOT),
        )
        combined = f"{proc.stdout}\n{proc.stderr}"
        assert proc.returncode == 0, f"check-dataset 失败 rc={proc.returncode}: {combined[-500:]}"
        gold_lines = [line for line in combined.splitlines() if "gold 修复版目录" in line]
        if not gold_lines:
            pytest.skip("QuixBugs 数据未就位（输出无 gold 路径行）——数据就位时本用例覆盖真实症状")
        for line in gold_lines:
            assert ".cache/aitester/quixbugs/correct_python_programs" in line, f"gold 路径不可读：{line}"
            assert ".<REDACTED" not in line, f"gold 路径被过度脱敏：{line}"
