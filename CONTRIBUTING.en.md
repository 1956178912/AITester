> **Language**: [中文版](CONTRIBUTING.md) | English (this document)

# Contributing Guide

Thanks for your interest in AITester! This document explains how to participate in the project's development.

## Setting Up the Development Environment

```bash
# Clone the repository
git clone <repository-url> && cd AITester

# Create a virtual environment (Python 3.12+; the locked dependency scipy requires >=3.12)
python3 -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env           # non-sensitive items
cp config.local.example .env.local   # LLM keys (LLM_N_*, already gitignored; do not commit)
```

## Commit Conventions

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation change
- `refactor:` code refactoring
- `test:` test-related
- `chore:` build/tooling-related

Examples:
```bash
git commit -m "feat: add synthetic dataset generator"
git commit -m "fix: fix incorrect parametrize validation logic"
```

## Code Style

- Python follows [PEP 8](https://peps.python.org/pep-0008/)
- All functions must include a Chinese docstring
- Line length ≤ 120 characters
- Use type annotations (typing module)

## Testing Requirements

New features must be accompanied by unit tests:

```bash
# Run all tests
.venv/bin/python -m pytest tests/ -v

# View coverage
.venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

Coverage requirements: core modules ≥ 90%, overall ≥ 80%.

## Pull Request Process

1. Fork this repository
2. Create a feature branch (`git checkout -b feat/xxx`)
3. Commit your changes (`git commit -m "feat: xxx"`)
4. Push to your fork (`git push origin feat/xxx`)
5. Create a Pull Request

## Reporting Issues

Please use GitHub Issues to report bugs or propose feature suggestions, in the following format:

- **Bug report**: reproduction steps, expected behavior, actual behavior, environment information
- **Feature suggestion**: problem description, proposed solution, use cases
