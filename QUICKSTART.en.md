# Quick Start

> Last updated: 2026-10-26 · 简体中文: [QUICKSTART.md](QUICKSTART.md)

## 1. Install

Python 3.12+ is required (the `scipy` floor decides this).

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
cp .env.example .env                   # non-sensitive config (optional)
cp config.local.example .env.local     # LLM config template
```

One-shot bootstrap: `bash scripts/tools/bootstrap_dev.sh` (creates the venv, installs
dependencies, copies both env templates, and verifies config loading; edit `.env.local`
afterwards with real values).

## 2. Configure an LLM

Fill values only; variable names are fixed:

| Variable | Purpose |
|---|---|
| `LLM_1_API_KEY` | API key |
| `LLM_1_BASE_URL` | OpenAI-compatible endpoint |
| `LLM_1_MODEL_NAME` | Model name |

`1` may be replaced by another index to configure multiple endpoints; only the official
DeepSeek endpoint is built in. `.env.local` is git-ignored; never put real keys into a
tracked file.

## 3. First Task

```bash
make test                    # verify the environment and dependencies first
python3 main.py list-examples
python3 main.py run examples/calculator.py --func add
```

`main.py run` calls an LLM and consumes quota. For a fully offline check:

```bash
bash scripts/tools/smoke_test.sh --no-llm --skip-lint
```

## 4. Sandbox and Safety

- Execution isolation: `EXECUTOR_USE_VENV` is **on by default** (since R10); LLM-generated
  code runs inside a venv sandbox.
- Docker / kernel-level sandboxes are opt-in; when the platform cannot provide them the
  system **fails closed** and refuses to execute.
- All three execution paths scrub LLM credentials, and logs are redacted at three layers.
- Set `EXECUTOR_USE_VENV=false` only for local debugging.

## 5. Troubleshooting

Look up the symptom in [docs/troubleshooting.en.md](docs/troubleshooting.en.md):
install and environment → runtime and sandbox → tests and gates. Run `make gates`
(single chain) before submitting.
