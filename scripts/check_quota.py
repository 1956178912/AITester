#!/usr/bin/env python3
"""
LLM 模型额度/存活探测脚本。

用途：
    逐个向配置的 LLM 端点发一个 1-token 的最小 chat 请求，判断每个模型当前
    处于哪种状态，帮助在「免费额度用完即停」模式下快速弄清哪些模型还活着、
    哪些已返回 403（AllocationQuota.FreeTierOnly）。

设计原则：
    - 最小 token 消耗：每个模型只发 1 个 max_tokens=1 的补全请求。
    - 零密钥泄露：API key 只用于请求头，绝不出现在输出里；错误详情会做脱敏截断。
    - 无新依赖：用 requests（openai/chromadb 已带）打 OpenAI 兼容的 /chat/completions，
      对 dashscope / deepseek / agnes / bigmodel 统一适用。

数据来源：
    - 运行时配置：import config 触发 load_dotenv + load_env_local，填充 LLM_CONFIGS
      （来自 .env.local 的 LLM_N_*，含真实 key / base_url / model）。
    - 模型目录：llm_configs.json（provider → 可用模型名清单）。

用法示例：
    # 探测当前已配置的所有 LLM
    .venv/bin/python scripts/check_quota.py

    # 扫「阿里云百炼」目录下全部模型（用你配在 dashscope 的 key）
    .venv/bin/python scripts/check_quota.py --provider aliyun_bailian

    # 只探测指定几个模型名（默认用第一个已配置 LLM 的 base_url + key）
    .venv/bin/python scripts/check_quota.py --models qwen-max,qwen-plus,qwen-turbo

    # 显式指定 key 来源（env 变量名，运行期读取，不打印值）与端点
    .venv/bin/python scripts/check_quota.py --provider agnes_domestic \
        --key-env AGNES_DOMESTIC_API_KEY

状态标记：
    ✅ live      200 成功，模型可用
    🔴 quota     403 且为 FreeTierOnly，免费额度已用尽（「用完即停」命中）
    ⛔ auth       401/403 非额度原因，key 无效或无权限
    ⚠️  rate      429 速率/并发限制
    🚫 missing    404 模型或端点不存在
    ⏭️  no_key     未找到该端点对应的 API key，跳过（未请求）
    ❓ error      网络/超时/其他 HTTP 状态
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# 让脚本能 import 项目模块（config 等）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests  # noqa: E402  已随 openai/chromadb 安装

# import config 会执行 load_dotenv() + load_env_local()，从而填充 LLM_CONFIGS
import config  # noqa: E402

# provider → 基准 base_url（用于 --provider 扫目录；与 llm_configs.json 保持一致）
PROVIDER_BASE_URL = {
    "aliyun_bailian": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "bigmodel": "https://open.bigmodel.cn/api/paas/v4/",
    "agnes_domestic": "https://api.agnes-ai.cn/v1",
}

# 状态标记（终端可读，避免冗长表格）
_STATUS_LABEL = {
    "live": "✅ live",
    "quota": "🔴 quota(403)",
    "auth": "⛔ auth",
    "rate": "⚠️  rate(429)",
    "missing": "🚫 missing(404)",
    "no_key": "⏭️  no_key",
    "error": "❓ error",
}

# 脱敏：移除任何可能混入的 Bearer 密钥片段
_SECRET_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9\-_.]+", re.IGNORECASE)


def _load_catalog() -> list[dict]:
    """读取模型目录 llm_configs.json，返回条目列表（缺失则空列表）。"""
    path = PROJECT_ROOT / "llm_configs.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _key_for_base_url(base_url: str) -> str | None:
    """在已配置的 LLM_CONFIGS 里找与 base_url 匹配的那条，返回其 api_key（找不到 None）。

    仅用于定位 key，不会把 key 打印出来。
    """
    for cfg in config.LLM_CONFIGS:
        if cfg.base_url.rstrip("/") == base_url.rstrip("/"):
            return cfg.api_key
    return None


def _scrub(text: str, limit: int = 160) -> str:
    """脱敏 + 截断错误详情：去掉 Bearer 密钥片段，控制长度。"""
    text = _SECRET_RE.sub(r"\1<REDACTED>", text or "")
    text = " ".join(text.split())  # 折叠多余空白
    return text[:limit]


def probe(base_url: str, model: str, api_key: str | None,
          max_tokens: int, timeout: float) -> dict:
    """向单个模型端点发一次最小补全请求，返回 {status, detail}。

    - api_key 为 None：不请求，直接标 no_key（省 token、避免无谓 401）。
    - 只发 1 个 max_tokens=max_tokens 的请求，控制 token 消耗。
    """
    if not api_key:
        return {"status": "no_key", "detail": "未找到该端点配置的 API key"}

    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        return {"status": "error", "detail": f"网络/超时: {type(exc).__name__}"}

    body = resp.text or ""
    code = resp.status_code

    if code == 200:
        return {"status": "live", "detail": "OK（可用）"}
    # 专门识别「免费额度用完即停」的 403（FreeTierOnly / Free quota）
    if code == 403 and ("FreeTierOnly" in body or "Free tier" in body or "free quota" in body.lower()):
        return {"status": "quota", "detail": "免费额度已用尽（AllocationQuota.FreeTierOnly）"}
    if code == 401:
        return {"status": "auth", "detail": "API key 无效或未授权"}
    if code == 403:
        return {"status": "auth", "detail": _scrub("403 权限拒绝（非额度原因）： " + body)}
    if code == 429:
        return {"status": "rate", "detail": "速率/并发限制"}
    if code == 404:
        return {"status": "missing", "detail": _scrub("模型或端点不存在： " + body)}
    return {"status": "error", "detail": _scrub(f"HTTP {code}： {body}")}


def _targets_from_configs() -> list[dict]:
    """默认目标：已配置的 LLM_CONFIGS（每条 model + base_url + key）。"""
    return [
        {"model": c.model_name, "base_url": c.base_url, "key": c.api_key, "origin": f"LLM_{i}"}
        for i, c in enumerate(config.LLM_CONFIGS, start=1)
    ]


def _targets_by_provider(provider: str, key_env: str | None) -> list[dict]:
    """按 provider 扫目录：该 provider 全部模型名，用同一 base_url 的 key。"""
    base_url = PROVIDER_BASE_URL.get(provider)
    if base_url is None:
        return []
    models = [e["model_name"] for e in _load_catalog() if e.get("provider") == provider]
    if not models:
        models = []  # 目录里没有该 provider
    key = os.getenv(key_env) if key_env else _key_for_base_url(base_url)
    return [
        {"model": m, "base_url": base_url, "key": key, "origin": f"catalog:{provider}"}
        for m in models
    ]


def _targets_by_models(names: list[str], provider: str | None,
                       key_env: str | None) -> list[dict]:
    """探测指定模型名：base_url/key 取自 --provider 或第一个已配置 LLM。"""
    if provider and provider in PROVIDER_BASE_URL:
        base_url = PROVIDER_BASE_URL[provider]
        key = os.getenv(key_env) if key_env else _key_for_base_url(base_url)
    elif config.LLM_CONFIGS:
        base_url = config.LLM_CONFIGS[0].base_url
        key = os.getenv(key_env) if key_env else config.LLM_CONFIGS[0].api_key
    else:
        base_url, key = "", None
    return [
        {"model": m, "base_url": base_url, "key": key, "origin": "args"}
        for m in names
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="探测各 LLM 模型的存活/免费额度状态（最小 token 消耗）")
    parser.add_argument("--provider", help=f"按 provider 扫目录（{', '.join(PROVIDER_BASE_URL)}）")
    parser.add_argument("--models", help="逗号分隔的模型名清单，直接探测这些名字")
    parser.add_argument("--key-env", help="指定读取 key 的环境变量名（运行期读取，不打印值）")
    parser.add_argument("--max-tokens", type=int, default=1, help="探测用 token 上限（默认 1，最省）")
    parser.add_argument("--timeout", type=float, default=15.0, help="单请求超时秒（默认 15）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将探测的目标清单，不发请求")
    args = parser.parse_args()

    # 组装探测目标
    if args.models:
        names = [m.strip() for m in args.models.split(",") if m.strip()]
        targets = _targets_by_models(names, args.provider, args.key_env)
    elif args.provider:
        targets = _targets_by_provider(args.provider, args.key_env)
    else:
        targets = _targets_from_configs()

    if not targets:
        print("未找到任何可探测目标。")
        print(f"  已配置的 LLM：{len(config.LLM_CONFIGS)} 条（来自 .env.local 的 LLM_N_*）")
        if args.provider:
            print(f"  目录中 provider '{args.provider}' 的模型：0 个")
        print("  建议：在 .env.local 配置 LLM_1_API_KEY / LLM_1_BASE_URL / LLM_1_MODEL_NAME，"
              "或用 --models 显式指定。")
        return 1

    if args.dry_run:
        print(f"将探测 {len(targets)} 个目标（dry-run，未发请求）：")
        for t in targets:
            key_state = "key已配置" if t["key"] else "无key"
            print(f"  [{t['origin']}] {t['model']} @ {t['base_url']}  ({key_state})")
        return 0

    print(f"探测 {len(targets)} 个模型（max_tokens={args.max_tokens}，超时 {args.timeout}s）…\n")
    tally: dict[str, int] = {}
    for t in targets:
        result = probe(t["base_url"], t["model"], t["key"], args.max_tokens, args.timeout)
        status = result["status"]
        tally[status] = tally.get(status, 0) + 1
        label = _STATUS_LABEL.get(status, status)
        print(f"  {label:<14} {t['model']:<20} <- {t['origin']:<16} {result['detail']}")

    # 汇总
    print("\n── 汇总 ──")
    order = ["live", "quota", "auth", "rate", "missing", "no_key", "error"]
    for s in order:
        if tally.get(s):
            print(f"  {_STATUS_LABEL[s]}: {tally[s]}")
    print(f"  合计: {len(targets)}")

    # 退出码：全部 live 返回 0，否则返回 1（便于脚本化）
    return 0 if tally.get("live", 0) == len(targets) else 1


if __name__ == "__main__":
    raise SystemExit(main())
