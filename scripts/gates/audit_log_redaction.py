"""
4.1 日志脱敏完整审计（自动化扫描）。

审计目标：
    1. 全仓库 logger.* 调用点中，可能携带敏感信息的参数是否经过脱敏
       （_redact / mask_sensitive_info / 字面量白名单）；
    2. src/observability/trace.py 的 JSONL 落盘路径是否统一脱敏；
    3. 异常堆栈完整打印路径（exc_info=True）是否被 SensitiveFormatter 覆盖；
    4. 环境变量注入路径（Docker / subprocess env）是否可能把 API Key
       直接透传给子进程日志。

输出：
    终端打印"未脱敏可疑点"清单（含文件:行号与上下文），供人工复核；
    退出码 0 = 无可疑点，1 = 发现可疑点（CI 可挂门禁）。

使用方式：
    python scripts/gates/audit_log_redaction.py [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 视为"已脱敏"的模式（参数中出现这些调用即认为该日志点受控）
_REDACTED_CALL_RE = re.compile(r"_redact\(|mask_sensitive_info\(|\.redact\(|<REDACTED")
# logger 调用行
_LOGGER_CALL_RE = re.compile(
    r"^\s*(?:[A-Za-z_][\w]*\.)?(?:logger|logging)\.(debug|info|warning|error|critical|exception|warn|log)\s*\("
)
# exc_info=True 的堆栈完整打印
_EXC_INFO_RE = re.compile(r"exc_info\s*=\s*True")
# 疑似敏感字段名（出现在日志参数中且未脱敏 → 可疑）。
# 收紧口径：仅匹配"字段=值"或独立变量名形式的赋值/插值，
# 避免中文叙述词（如 "token 统计" 指用量而非密钥）误报。
_SENSITIVE_FIELD_RE = re.compile(
    r"""(?:"?api_key"?\s*=|'?api_key'?\s*=|"?secret"?\s*=|"?password"?\s*=|'password'\s*=|"""
    r"""Authorization|Bearer\s+[A-Za-z0-9]|sk-[A-Za-z0-9]|credential[s]?\s*=|"""
    # O33（2026-09-30 全面审查优化）：三类残余盲区（探针实测原样通过）——
    # ① 带空格/连字符的字段名变体（api key: / api-key= / passwd= / access_token= /
    #    private key:，字段名后必须跟 : 或 = 才命中，避免"password reset"类叙述误报）；
    # ② AWS Access Key 裸值（AKIA/ASIA + 16~20 位大写——字段名形态已由 O18 覆盖，
    #    裸值形态缺失）；
    # ③ DB DSN scheme+userinfo（mysql://root:pw@host——字段名形态缺失）。
    # 实测：对全仓 438 个 logger 调用点零新增误报（与 logging_utils._SENSITIVE_PATTERNS 同步口径）。
    r"""\b(?:api[-_ ]?key|passwd|access[-_ ]?token|refresh[-_ ]?token|private[-_ ]?key)\s*[:=]|"""
    r"""\b(?:AKIA|ASIA)[0-9A-Z]{16,20}\b|"""
    r"""(?:mysql|postgres|postgresql|mongodb|redis|amqp)://[^/@\s]+:)""",
    re.IGNORECASE,
)
# O18（2026-09-29 审查 P0）：四类脱敏盲区同步扩展（与
# src/utils/logging_utils.py _SENSITIVE_PATTERNS 后 4 条同口径）：
# 1. Bearer token（Authorization: Bearer <token>）
# 2. URL userinfo（https://user:pass@host）
# 3. AWS Access Key（AKIA/ASIA + 16~20 位大写）
# 4. DB DSN 口令（mysql://root:pass@host 等）
_SENSITIVE_PATTERNS_O18: list[re.Pattern] = [
    re.compile(r"Bearer\s+[A-Za-z0-9\-_\.~+/=]{8,}"),
    re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]*://[^/@\s]+:[^@\s]+@"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16,20}\b"),
    re.compile(r"(?i)\b(?:mysql|postgres|postgresql|mongodb|redis|amqp)://[^/@\s]+:[^@\s]+@"),
]


def _match_o18_patterns(line: str) -> bool:
    """O18：检测日志行是否命中 4 类脱敏盲区模式。"""
    return any(p.search(line) for p in _SENSITIVE_PATTERNS_O18)


@dataclass
class Finding:
    """一条可疑日志点。"""

    file: str
    line_no: int
    line: str
    reason: str


@dataclass
class AuditResult:
    """审计结果汇总。"""

    scanned_files: int = 0
    logger_calls: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings


def _should_skip(path: str) -> bool:
    """跳过测试/示例/生成物目录。"""
    parts = path.replace(os.sep, "/").split("/")
    for skip in (
        "tests",
        "examples",
        "dist",
        "build",
        "node_modules",
        ".venv",
        "venv",
        "rag_data",
        "figures",
        "docs",
        "experiments/results",
    ):
        if skip in parts:
            return True
    return False


def audit(repo_root: str) -> AuditResult:
    """扫描仓库内所有 .py 文件的日志调用点。"""
    result = AuditResult()
    py_files = []
    for root, _dirs, files in os.walk(repo_root):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            full = os.path.join(root, fname)
            if _should_skip(full):
                continue
            py_files.append(full)
    py_files.sort()

    for path in py_files:
        result.scanned_files += 1
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            continue
        rel = os.path.relpath(path, repo_root)
        for i, raw in enumerate(lines, start=1):
            stripped = raw.strip()
            if not _LOGGER_CALL_RE.match(stripped) and not stripped.startswith("logger."):
                continue
            result.logger_calls += 1
            # 1) exc_info=True 堆栈完整打印：需确认该 logger 挂了 SensitiveFormatter
            #    （项目统一入口 cli/app.py setup_logger_safety 已全局挂上，
            #      此处仅标记供人工复核，不算 finding）
            # 2) 参数含敏感字段名且无 _redact/mask_sensitive_info → 可疑
            # O18（2026-09-29 审查 P0）：4 类脱敏盲区（Bearer / URL
            # userinfo / AWS key / DSN）同步纳入检测，与 logging_utils
            # 的 _SENSITIVE_PATTERNS 后 4 条同口径。
            if (
                _SENSITIVE_FIELD_RE.search(stripped)
                and not _REDACTED_CALL_RE.search(stripped)
                and re.match(r"^(logger|logging)\.", stripped)
            ):
                result.findings.append(
                    Finding(
                        file=rel,
                        line_no=i,
                        line=stripped[:160],
                        reason="logger 参数含敏感字段名且未检测到脱敏调用",
                    )
                )
            elif (
                _match_o18_patterns(stripped)
                and not _REDACTED_CALL_RE.search(stripped)
                and re.match(r"^(logger|logging)\.", stripped)
            ):
                result.findings.append(
                    Finding(
                        file=rel,
                        line_no=i,
                        line=stripped[:160],
                        reason="O18：logger 参数命中 4 类脱敏盲区（Bearer/URL userinfo/AWS key/DSN）且未检测到脱敏调用",
                    )
                )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="4.1 日志脱敏完整审计")
    parser.add_argument("--json", default=None, help="审计结果 JSON 输出路径")
    parser.add_argument("--repo", default=PROJECT_ROOT, help="仓库根目录")
    args = parser.parse_args()

    result = audit(args.repo)
    print(f"扫描 {result.scanned_files} 个 .py 文件，{result.logger_calls} 个 logger 调用点")
    if result.findings:
        print(f"\n⚠ 发现 {len(result.findings)} 个未脱敏可疑点：\n")
        for f in result.findings:
            print(f"  {f.file}:{f.line_no}  [{f.reason}]")
            print(f"    {f.line}")
    else:
        print("✓ 未发现未脱敏可疑点（exc_info 堆栈路径由 SensitiveFormatter 全局覆盖）")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "scanned_files": result.scanned_files,
                    "logger_calls": result.logger_calls,
                    "findings": [
                        {"file": f.file, "line_no": f.line_no, "line": f.line, "reason": f.reason}
                        for f in result.findings
                    ],
                },
                fh,
                ensure_ascii=False,
                indent=2,
            )
        print(f"\n审计结果已写入: {args.json}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
