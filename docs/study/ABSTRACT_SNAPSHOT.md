# 外部读数登记册的官方摘要快照（FE 轮，2026-10-27）

## 这份快照是什么

`docs/study/EXTERNAL_READINGS_ABSTRACTS.json` 存的是**外部读数登记册**
（`docs/study/EXTERNAL_READINGS_2026-10-25.md`）里引用到的每一篇论文的
**arXiv 官方摘要**（`export.arxiv.org/api/query` 的 `summary` + `title` 字段）。

它是 `scripts/tools/verify_citation_quotes.py` 的**判决输入**：该脚本逐条核验
登记册里的引文是否与官方摘要**逐字一致**。快照必须**入库**，因为

- CI **不联网**（离线核验必须能复跑）；
- 「核验结果」必须能被第三方在离线状态下独立复核，而不是只能相信执行者的报告。

## 键的形态

| 键 | 含义 |
|---|---|
| `2609.09315` | 该 arXiv ID 的**最新版**摘要（兜底键） |
| `2609.09315v1` | **指定版本**的摘要 |

**两个键都必须存**：同一个 ID 的不同版本摘要内容可能不同——
`arXiv:2512.08296`（`kim2026scaling`）的 **v2** 摘要写「R²=0.524」，
**v3** 改成「0.373 / 0.413」。只存最新版会把「按 v2 登记」的引文误判成
「摘要里没有这句话」。

## 怎么更新

取数与解析**分离**——取数用 `curl`（走系统 CA），解析用本仓脚本：

```bash
# 1) 取出登记册里用到的全部 arXiv ID（按版本）
python3 scripts/tools/verify_citation_quotes.py --list-ids

# 2) 分批取官方 API 产物（每批 ≤ 30 个 ID，URL 长度可控）
curl -sS "https://export.arxiv.org/api/query?id_list=<ID1,ID2,...>&max_results=40" \
     -o /tmp/arxiv_batch_a.xml

# 3) 解析成快照（覆盖写）
python3 scripts/tools/verify_citation_quotes.py --refresh --xml-dir /tmp
```

> **为什么不用 Python `urllib` 直接联网**：本机企业代理下 Python 的 CA 链缺失
> （`urllib` 报 `CERTIFICATE_VERIFY_FAILED`），而 `curl` 走系统 CA 正常。
> 把取数与解析分开，也让核验脚本本身保持**纯离线**。

## 判据（工具内部）

每条引文必须能被归入两类之一：

- **摘要原文**：引文（归一后）**逐字连续命中**官方摘要；
- **正文摘录**：引文不在摘要里，但出处列或引文列显式标注了正文层级
  （`正文` / `全文` / `§` / `Table N` / `Figure N`）。

**未命中摘要且未标注正文层级 ⇒ rc=1**（CI 阻断）。

「归一」只抹掉**渲染层**差异，每一项都能解释清楚：

- HTML 实体：arXiv 摘要用 `&lt;` `&gt;` `&amp;`，登记册用 `<` `>` `&`；
- LaTeX 转义与数学模式：摘要用 `\%` `&` `\_` `$p = 0.0352$`，登记册用裸字符；
- Markdown 反引号对：摘要用 ``` `` ``` 标代码。

**不做**词形或词序归一——把 `detect` 改成 `identified`、把句序调换，
都必须判红（那才是「改写」，必须暴露）。

## 这套机制抓到过什么（FE 轮实测）

登记册 89 条表格行、188 条引文里，**7 条**在官方摘要中逐字找不到：

| 键 | 缺陷形态 | 处置 |
|---|---|---|
| `hamidi2026criteria` | **翻译腔改写**：登记的是「approximately miss approximately 99%」，摘要里既无此句也无 99% 这个数字 | 换成摘要原句（fault detection「near zero」） |
| `konstantinou2026coding` | **改写**：登记的是「25% for a test-driven workflow」，摘要是「(14% vs. 25%)」 | 换成摘要原句 |
| `tan2026beyondfailtopass` / `liang2026oracleaudit` / `yu2026sweabs` / `paul2026behaviouralgaps` / `alahmad2026classleveltests` / `liang2026sectdd` / `smyth2026overclaim` / `otterson2026instrumentautopsy` / `xu2026discriminatingfixtures` | **跨句拼接**：把摘要里**不连续**的句子接在一起（拼接处漏了句号） | 拆成多段引文（每段各自逐字连续） |
| `kim2026scaling`（R²=0.524 行） | **版本错配**：该读数出自 v2 摘要，快照只存最新版时被误判 | 快照改为**按版本**存 |
| `2512.08296` 去版本键 | **去版本键指向旧版**：快照刷新时同一 ID 的多版本 entry 里「谁排后面谁覆盖」，去版本键被 v2 entry 覆盖而官方最新版是 v3（FE 收口轮用官方 API 全量回核 84 条时抓到） | `refresh_snapshot` 改为**按版本号取最大**（与 entry 顺序解耦）+ 回归锁（`test_bare_key_takes_highest_version_not_entry_order`） |

另有 1 条（`jwalapuram2026illusion` 的第二句）确实出自**正文**而非摘要 ⇒
已在出处列显式标注「第二句出自**正文**（非摘要）」。

## 相关锁

- `tests/test_citation_quote_verification_fe.py`（12 例）——快照完整性 +
  全部引文可核 + 覆盖面不得塌缩 + **3 例负对照**（改写必判未核 / 原句必判命中 /
  快照缺条目不得静默通过）+ 快照刷新的**去版本键取最大版本号**回归锁（3 例）。
- `tests/test_audit_unmeasured_scope_fe.py`（5 例）——审计工具「未测量 ≠ 零缺口」
  守卫的真锁（未测量文件单列不进分母 / CLI 判红 + stderr 点名 / 测量齐全负对照 rc=0）。
- `scripts/gates/check_citations.py` 只核**存在性**（编号是否存在），
  它自己的 docstring 明确写着「不证明引用处的论断忠实于原文」——
  本快照与核验工具正是补上这一环。
- 变异闭环：`scripts/tools/fe_mutation_verify.py`（5 变异全红 + 1 中性对照 0 红）。
