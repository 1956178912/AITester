"""性能基准脚本的**离线可运行性**回归锁（CO 轮，2026-10-25）。

为什么要有这条锁：`scripts/tools/performance_benchmark.py` 只测三个纯函数，
一次模型请求也不发，但它的导入链会构造 langchain 的 `ChatOpenAI`——而该构造
在**构造期**就要求凭据。没有 `.env` 的环境（CI 的每周定时作业）里，脚本在
BaseAgent 基准那一步抛 `openai.OpenAIError: Missing credentials`，perf.yml
自 2026-10-11 起连续三次定时红。

修法是注入占位 provider 三元组（`LLM_1_API_KEY` / `_BASE_URL` / `_MODEL_NAME`，
即 config.py 自己读的那三个变量），而不是塞 `OPENAI_API_KEY`——后者不生效，
因为 `_get_llm_config()` 在无 provider 时返回空三元组。

本锁以子进程方式在**清空凭据环境**下跑脚本，断言 rc=0 且产物落盘。
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "tools" / "performance_benchmark.py"


def test_benchmark_script_runs_without_credentials(tmp_path):
    """无任何 LLM 凭据时，基准脚本仍应跑通并写出结果。"""
    out = tmp_path / "perf.json"
    env = dict(os.environ)
    for name in ("OPENAI_API_KEY", "OPENAI_ADMIN_KEY", "LLM_1_API_KEY"):
        env.pop(name, None)
    env["AITESTER_PERF_BENCHMARK_OUT"] = str(out)

    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
        cwd=str(PROJECT_ROOT),
    )
    assert proc.returncode == 0, f"rc={proc.returncode}\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
    assert out.is_file(), "结果文件未生成"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload, "结果为空"
    assert "base_agent" in payload, "BaseAgent 基准段缺失（构造期失败会在这里断）"


def test_benchmark_script_keeps_existing_provider_config(tmp_path, monkeypatch):
    """已有 provider 配置时不得被占位值覆盖（基准要测真实配置面）。"""
    spec = importlib.util.spec_from_file_location("perf_bench_mod", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setenv("LLM_1_API_KEY", "sk-real-key")
    assert module._ensure_constructible_client() == {}, "已有配置时不应注入占位值"

    monkeypatch.delenv("LLM_1_API_KEY", raising=False)
    injected = module._ensure_constructible_client()
    # 语义：只补「缺的那几个」——已存在的真实配置不得被占位值覆盖。
    assert "LLM_1_API_KEY" in injected, injected
    for name in injected:
        assert name not in os.environ, f"{name} 本已存在，不该被注入"
    assert set(injected) <= set(module._NOOP_LLM_ENV), injected
