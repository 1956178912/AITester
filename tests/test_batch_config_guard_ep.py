"""EP（2026-10-27）批量配置脚本的输入契约缺陷族。

生成物 ``scripts/tools/generate_batch_config.py`` 承诺「防数据丢失」：模型列表为空
时拒绝覆盖现有 ``.env.local``。同一 ``"w"`` 写模式下的**缺 Key** 路径没有守卫——
``generate_config`` 会写占位符 ``your-<provider>-api-key-here``，把可用的真实凭证
替换成伪配置，退出码仍是 0。实测（改前）：

- 现有 ``LLM_1_API_KEY=keep-me`` + 环境无 ``DEEPSEEK_API_KEY`` → 脚本 rc=0，
  文件变成 ``LLM_1_API_KEY=your-deepseek-api-key-here``；
- ``--template`` 在 usage 与 argparse 里声明，但 ``main`` 从不读取，传了也静默
  按默认逻辑生成（rc=0）。

修法：写入前检查每个条目能否产出真实配置（provider 可派生 key 变量、对应
``*_API_KEY`` 已设置），任一不满足即列出原因、rc=1、输出文件原样保留；删除
幽灵 ``--template`` 开关。生成模板与在盘脚本同源锁（本轮起由测试对账）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TRACKED_SCRIPT = _REPO_ROOT / "scripts" / "tools" / "generate_batch_config.py"
_COMPLETE_MODEL = {
    "model_name": "deepseek-flash",
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
}


def _env_without_api_keys(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    env.update(extra)
    return env


def _run_script(
    tmp_path: Path, models: object, output: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    models_file = tmp_path / "models.json"
    models_file.write_text(json.dumps(models), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(_TRACKED_SCRIPT), "--models", str(models_file), "--output", str(output), *args],
        capture_output=True,
        text=True,
        env=env if env is not None else _env_without_api_keys(),
    )


class TestMissingApiKeyRefuses:
    def test_missing_api_key_preserves_existing_file(self, tmp_path: Path) -> None:
        """缺 Key 时不得用占位符覆盖现有配置（改前实测 rc=0 且 Key 被替换）。"""
        output = tmp_path / ".env.local"
        output.write_text("LLM_1_API_KEY=keep-me\n", encoding="utf-8")

        result = _run_script(tmp_path, [_COMPLETE_MODEL], output)

        assert result.returncode == 1, result.stderr
        assert "DEEPSEEK_API_KEY" in result.stderr
        assert "未写入输出文件" in result.stderr
        assert output.read_text(encoding="utf-8") == "LLM_1_API_KEY=keep-me\n"

    def test_missing_api_key_does_not_create_output(self, tmp_path: Path) -> None:
        output = tmp_path / "missing.env"
        result = _run_script(tmp_path, [_COMPLETE_MODEL], output)

        assert result.returncode == 1, result.stderr
        assert not output.exists()

    def test_partial_keys_refuse_whole_batch(self, tmp_path: Path) -> None:
        """一条缺 Key 即整批拒绝：不允许「部分覆盖」把另一条的真实 Key 写出去。"""
        output = tmp_path / ".env.local"
        output.write_text("LLM_1_API_KEY=keep-me\n", encoding="utf-8")
        models = [_COMPLETE_MODEL, {**_COMPLETE_MODEL, "model_name": "other-model", "provider": "other"}]

        result = _run_script(tmp_path, models, output, env=_env_without_api_keys(DEEPSEEK_API_KEY="k"))

        assert result.returncode == 1, result.stderr
        assert output.read_text(encoding="utf-8") == "LLM_1_API_KEY=keep-me\n"

    def test_missing_provider_refuses(self, tmp_path: Path) -> None:
        """provider 缺失时 key 变量无从派生（旧行为写 your--api-key-here），同样拒绝。"""
        output = tmp_path / ".env.local"
        output.write_text("LLM_1_API_KEY=keep-me\n", encoding="utf-8")
        models = [{"model_name": "mystery", "base_url": "https://example.com/v1"}]

        result = _run_script(tmp_path, models, output, env=_env_without_api_keys())

        assert result.returncode == 1, result.stderr
        assert "provider" in result.stderr
        assert output.read_text(encoding="utf-8") == "LLM_1_API_KEY=keep-me\n"


class TestContractGuards:
    def test_configured_key_still_generates(self, tmp_path: Path) -> None:
        output = tmp_path / ".env.local"
        result = _run_script(
            tmp_path,
            [_COMPLETE_MODEL],
            output,
            env=_env_without_api_keys(DEEPSEEK_API_KEY="mock-key"),
        )

        assert result.returncode == 0, result.stderr
        assert "LLM_1_API_KEY=mock-key" in output.read_text(encoding="utf-8")

    def test_template_flag_is_not_silently_ignored(self, tmp_path: Path) -> None:
        """改前实测：--template 被接受但从不读取（rc=0，输出照写）。删除后应参数错误。"""
        output = tmp_path / ".env.local"
        result = _run_script(
            tmp_path,
            [_COMPLETE_MODEL],
            output,
            "--template",
            "x",
            env=_env_without_api_keys(DEEPSEEK_API_KEY="mock-key"),
        )

        assert result.returncode == 2, result.stderr
        assert "--template" in result.stderr
        assert not output.exists()

    def test_tracked_script_matches_generator(self) -> None:
        """在盘脚本是生成模板的产物；两份副本必须逐字节一致（防只修一侧的漂移）。"""
        from src.config.config_generator import generate_batch_config_script

        assert _TRACKED_SCRIPT.read_text(encoding="utf-8") == generate_batch_config_script()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
