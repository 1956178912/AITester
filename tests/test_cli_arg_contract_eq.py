"""EQ 轮：CLI 声明与实现脱钩（3 站点）的回归锁。

修前实测（零 LLM / 零真实凭证）：

1. ``scripts/tools/expand_models.py add --name … --url … --key …``：argparse
   声明 ``name`` / ``url`` / ``key``，``cmd_add`` 却读 ``args.model_name`` /
   ``args.base_url`` / ``args.api_key``——必填旗标一给就
   ``AttributeError: 'Namespace' object has no attribute 'api_key'``，rc=1，
   文档里的主命令从未成功执行过一次。
2. ``experiments/oracle_examples_replay.py --repeat N``：参数被接受且全程无
   任何 ``args.repeat`` 读取——用户以为做了 N 次确定性验证，实际只跑一遍。
   （同目录 ``oracle_quality_replay`` / ``misguided_metrics`` /
   ``compile_exec_metrics`` 都实现了整批重复 + body digest 比较，本脚本只抄了
   旗标没抄实现。）
同型已排除：``experiments/emse_batch5_orchestrator.py --skip-rerun`` 同样被
``main()`` 忽略（实测仍调用 ``emse_quixbugs_specir_expand_arms.py``，一次最长
7200s 的 4 臂跑批），但该文件被 ``.gitignore`` 排除且未被跟踪——clean checkout
不存在，不属可交付面，本轮不入测、不改动。

口径护栏（修前即绿）：``list`` / ``batch`` 子命令不受影响、``--repeat`` 删除后
默认解析不变。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_expand_models():
    spec = importlib.util.spec_from_file_location("_expand_models_eq", ROOT / "scripts" / "tools" / "expand_models.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestExpandModelsAdd:
    def test_add_reads_its_own_flags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _load_expand_models()
        recorded: dict[str, str] = {}
        monkeypatch.setattr(module, "add_llm_config", lambda **kwargs: recorded.update(kwargs) or True)
        monkeypatch.setattr(module, "count_llm_configs", lambda: 1)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "expand_models.py",
                "add",
                "--name",
                "probe-model",
                "--url",
                "https://api.deepseek.com/v1",
                "--key",
                "sk-not-real",
            ],
        )
        module.main()
        assert recorded == {
            "api_key": "sk-not-real",
            "base_url": "https://api.deepseek.com/v1",
            "model_name": "probe-model",
        }

    def test_list_subcommand_unaffected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _load_expand_models()
        called: list[str] = []
        monkeypatch.setattr(module, "print_config_report", lambda: called.append("report"))
        monkeypatch.setattr(module, "get_all_llm_configs", lambda: [])
        monkeypatch.setattr(sys, "argv", ["expand_models.py", "list"])
        module.main()
        assert called == ["report"]

    def test_batch_without_source_still_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _load_expand_models()
        monkeypatch.setattr(sys, "argv", ["expand_models.py", "batch"])
        with pytest.raises(SystemExit) as exc:
            module.main()
        assert exc.value.code == 1


class TestExamplesReplayRepeat:
    def test_repeat_flag_is_rejected(self) -> None:
        from experiments import oracle_examples_replay as oer

        stderr = io.StringIO()
        with pytest.raises(SystemExit) as exc, contextlib.redirect_stderr(stderr):
            oer._build_arg_parser().parse_args(["--repeat", "2"])
        assert exc.value.code == 2
        assert "--repeat" in stderr.getvalue()

    def test_examples_parser_defaults_still_parse(self) -> None:
        from experiments import oracle_examples_replay as oer

        args = oer._build_arg_parser().parse_args([])
        assert args.quiet is False
        assert args.skip_markdown is False
        assert args.limit == 20
