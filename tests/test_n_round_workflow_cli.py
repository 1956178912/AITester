#!/usr/bin/env python3
"""N 轮 N-1：全功能 e2e 探针实测缺陷的回归锁定（CLI 组）。

本文件锁定 N-1 探针在真实链路中发现的 **2 个 CLI 缺陷**（均已在
`src/cli/app.py` 修复）：

1. `run --json --verbose` stdout 污染（cli-run-json-single 探针实测）：
   `--verbose` + `--json` 组合时的提示经 `info_msg` 走 stdout，使
   `python main.py run X --json --verbose | jq` 首行解析失败——与
   `--quiet_console_logs` 文档承诺的"stdout 只承载 JSON"契约矛盾。
   修复：提示改走 stderr；stdout 保持单一合法 JSON。
2. `list-examples` 把 `examples/__init__.py` 当作可运行示例并建议执行
   （cli-list-examples 探针实测）：用户复制"使用示例"首条命令得到空模块
   任务。修复：下划线开头文件不列出；建议优先 `calculator.py`。

全部测试零 LLM / 零网络 / 确定性（通过 mock `_run_single_task` 隔离工作流）。
"""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from src.cli import app as cli_app

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EXAMPLE = _REPO_ROOT / "examples" / "calculator.py"


def _fake_result(target_file: str) -> dict[str, object]:
    return {
        "success": True,
        "file": target_file,
        "func": "all",
        "passed": True,
        "coverage": 100.0,
        "coverage_threshold": 80.0,
        "coverage_ok": True,
        "iterations": 1,
        "max_iterations": 1,
        "diagnosis": None,
        "error_category": None,
        "event_bus": {"counts": {}, "subscribed": []},
        "cost_budget": {"total_consumed": 0},
        "semantic_cache": {},
    }


def _fake_run_single_task(target_file: str, *args: object, **kwargs: object) -> dict[str, object]:
    """冒充真实 `_run_single_task`：JSON 模式下把单任务结果打到 stdout。

    真实实现的 JSON 输出发生在 `_run_single_task` 内部（click.echo），
    因此 mock 必须复刻该副作用，否则测不到 stdout 契约。
    """
    result = _fake_result(target_file)
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def _parse_json_objects(text: str) -> list[object]:
    """解析 stdout 中连续拼接的多个 JSON 文档（多文件 --json 既有语义）。"""
    decoder = json.JSONDecoder()
    objects: list[object] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index] in " \t\r\n":
            index += 1
        if index >= len(text):
            break
        obj, end = decoder.raw_decode(text, index)
        objects.append(obj)
        index = end
    return objects


class TestJsonVerboseStdoutPurity:
    """缺陷 1 回归：--json（含 --verbose 组合）stdout 必须是纯 JSON。"""

    def test_json_verbose_stdout_is_pure_json(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        monkeypatch.setattr(cli_app, "_run_single_task", _fake_run_single_task)

        result = CliRunner().invoke(cli_app.cli, ["run", str(target), "--json", "--verbose"])

        assert result.exit_code == 0, result.output
        # Click 8.2+ 的 result.output 是 stdout+stderr 混流；纯 stdout 用 result.stdout
        # 核心断言：stdout 从第一个字符起就是合法 JSON（可被 jq 直接消费）
        payload = json.loads(result.stdout.strip())
        assert payload["passed"] is True
        # 提示仍在（人读通道 = stderr），不是静默丢失
        assert "提示" in result.stderr
        assert "提示" not in result.stdout

    def test_json_without_verbose_stdout_is_pure_json(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        monkeypatch.setattr(cli_app, "_run_single_task", _fake_run_single_task)

        result = CliRunner().invoke(cli_app.cli, ["run", str(target), "--json"])

        assert result.exit_code == 0
        assert json.loads(result.stdout.strip())["file"] == str(target)

    def test_json_verbose_multi_file_stdout_still_parseable(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """多文件 + --json --verbose：每任务一份 JSON，均可逐份解析。"""

        files = []
        for name in ("a.py", "b.py"):
            path = tmp_path / name
            path.write_text("def f():\n    return 1\n", encoding="utf-8")
            files.append(str(path))
        monkeypatch.setattr(cli_app, "_run_single_task", _fake_run_single_task)

        result = CliRunner().invoke(cli_app.cli, ["run", *files, "--parallel", "2", "--json", "--verbose"])

        assert result.exit_code == 0, result.output
        payloads = _parse_json_objects(result.stdout.strip())
        assert len(payloads) == 2
        dict_payloads = [payload for payload in payloads if isinstance(payload, dict)]
        assert {payload["file"] for payload in dict_payloads} == set(files)
        assert "提示" in result.stderr
        assert "提示" not in result.stdout


class TestListExamplesCleanliness:
    """缺陷 2 回归：list-examples 不列/不推荐不可运行的下划线开头文件。"""

    def test_excludes_dunder_files(self) -> None:
        result = CliRunner().invoke(cli_app.cli, ["list-examples"])
        assert result.exit_code == 0
        listed = [line.strip(" •\t") for line in result.output.splitlines() if line.strip().startswith("•")]
        assert "__init__.py" not in listed
        assert "calculator.py" in listed
        assert "buggy_library.py" in listed

    def test_suggests_runnable_example(self) -> None:
        result = CliRunner().invoke(cli_app.cli, ["list-examples"])
        suggested = [line for line in result.output.splitlines() if "python main.py run examples/" in line]
        assert suggested, "缺少『使用示例』命令行"
        assert "examples/calculator.py" in suggested[-1]
        assert "__init__.py" not in suggested[-1]

    def test_examples_file_exists_for_suggestion(self) -> None:
        """建议的目标必须在 examples/ 下真实存在（防建议漂移到不存在文件）。"""
        assert _EXAMPLE.is_file()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
