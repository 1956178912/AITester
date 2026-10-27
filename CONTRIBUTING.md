# 贡献指南

> 最后更新：2026-10-27 · English: [CONTRIBUTING.en.md](CONTRIBUTING.en.md)

## 开发环境

```bash
python3 -m venv .venv && source .venv/bin/activate
make install
cp config.local.example .env.local
```

Python 3.12+；依赖以 `requirements.txt` / `requirements.lock` 为准。
详细步骤见 [QUICKSTART.md](QUICKSTART.md)。

## 提交前检查

合并前必须跑 **`make gates`**（单链，勿与其它 pytest 并发）。该目标串起：

- `make lint` / `make format` / `make typecheck`
- `make test`（CI 同口径）
- `make docs-check` / `make doc-commands` / `make baseline-check`
- 登记面、开关有效性、仓库卫生、引用库等门禁

只跑子集不足以作为收口证据：门禁之间有依赖（例如门禁总数与开关实例数要对得上）。

## 文档约定

- **数值只有一个来源**：测试、覆盖率、静态检查读数写在 `BASELINE.yaml`；
  其它文档指向它，不复制计数。
- **过期内容归档，不就地加注**：历史叙事移入 `docs/history/`，当前文档保持简洁。
- **双语配对**：`foo.md` ↔ `foo.en.md`，两边的 `最后更新 / Last updated` 日期必须一致，
  章节数差不超过 2。
- **代码块里的命令必须真实存在**：`make` 目标与 `scripts/*.py` 路径由
  `make doc-commands` 校验。
- 表格行内代码不要写裸 `|`（GFM 会切格并静默丢内容）。

## Pull Request

- 一个 PR 只做一件事；标题写清变更类型（feat / fix / docs / test / chore）。
- 行为变更必须带测试；修 bug 先写复现测试。
- 不提交密钥、`.env.local`、私有目录或运行残留；提交前可跑
  `make repo-hygiene`。
- 在 PR 描述里写：动机、改了什么、如何验证（命令与读数）。
