# HTML/XML 聚合物语料采集

此功能在现有 PDF 下载器旁增加独立采集流程，数据默认保存在用户目录下的
`~/Documents/paperman/corpus/`，不使用 `~/.cache/paperman/papers.db`，不调用 PDF 回退链。
安装到其他环境时请用 `-o /your/corpus` 显式指定持久存储位置。

## 快速使用

```bash
paperman corpus discover --config examples/corpus.toml
paperman corpus fetch --formats html,xml --resume
paperman corpus report
```

主 CLI 依赖未安装时，从仓库根目录运行：

```bash
PYTHONPATH=src python3 -m paperman.corpus discover --config examples/corpus.toml
PYTHONPATH=src python3 -m paperman.corpus fetch --formats html,xml --resume
PYTHONPATH=src python3 -m paperman.corpus report
```

该入口需要 Python >=3.11 和 requests。可用 `--help` 查看参数。
语料目录及配置含机构来源信息，请按项目的数据保存条件管理。

## 文献发现与试点

- 默认 2000-01-01 至首次发现任务当天，五家出版社的期刊文章。
- 按配置关键词检索 Crossref，并在标题/摘要中再次匹配；保存命中词和完整摘要。
- 标识符统一为小写裸 DOI；支持 DOI URL、`doi:` 前缀及每行一个 DOI 的清单：
  `paperman corpus discover --identifiers dois.txt`。导入仍执行年份/领域范围筛选。
- 默认每家抽取 20 篇，按五年时间段与已知开放/未知访问状态分层，层内按固定种子对 DOI 哈希排序；固定候选池扩大到 200 篇/家时，
  原 20 篇保留在扩大样本中。新增候选会改变抽样；应保存试点的 manifest 与报告快照。
- `--per-publisher 200` 将目标变为 1000 篇，同时扩大候选池上限。
- 分页游标持久保存；中断后重新执行同一配置即可继续。已结束的查询不会重复拉取。
- 检索按五年时间段分配候选配额；每个查询每次最多 `max_pages` 页，某时间段达到配额即暂停该段。
  单页结果可能令配额略超出，清单是有界候选集，不能解释为全部聚合物文献。段内按 Crossref 记录创建日期排序（游标分页不支持发表日期排序），
  仍可能存在时间偏差；报告保留真实年份分布，需在试点中复核。
- 需更大范围时增加候选上限、重复执行以推进游标；调整关键词/日期会创建新的查询检查点。
- 缺失摘要会保留标记；默认标题或可用摘要需命中关键词，因此缺摘要可能导致漏检。
  设 `openalex=true` 可补全已入选候选的摘要和开放全文位置，必要时设置 `OPENALEX_API_KEY`；不能消除所有召回偏差。
- 100 篇阶段检查出版社、年份及开放/订阅分布；必要时使用固定 DOI 清单构造对照试点。
  不足 20/200 篇的出版社在报告中显示缺口，不用其他出版社替补。

## 出版社渠道

| 出版社 | 实现的获取渠道 | 需要验证的条件 |
|---|---|---|
| Elsevier | Article API XML（显式 `view=FULL`）、Crossref 格式链接、配置的 HTML/XML | API Key、机构出口、文章访问权限 |
| Springer Nature | Open Access JATS API、Crossref 链接、配置的机构 TDM 和 HTML | OA API Key 或机构 TDM 渠道 |
| ACS | Crossref 格式链接、配置的机构渠道、交付文件导入 | 机构实际可用的全文渠道 |
| RSC | Crossref 格式链接、配置的机构渠道、交付文件导入 | 机构实际可用的全文渠道 |
| Wiley | Crossref 格式链接、单独配置的 HTML/XML 渠道、交付文件导入 | 标准 TDM 只提供 PDF，需确认其他格式渠道 |

适配器存在不代表已取得该出版社访问权限。未配置的机构渠道会登记为
`channel_unverified`；缺密钥为 `missing_credentials`；Wiley 未提供 HTML/XML 渠道时为
`format_unavailable`。这些状态和真正发请求后得到的 403、404、网络失败分别统计。

- 标准代理环境变量与已有 `~/.config/paperman/config.ini` 的代理受支持；
  `PAPERMAN_CORPUS_PROXY` 可单独指定语料采集代理。
- 在示例配置中指定环境变量名称，不要填入密钥本身。
- 机构验证通过后才将相应 `html_enabled=true`；它使用元数据落地页或 DOI 解析。
- `html_url` / `xml_url` 是机构或出版社提供的实际 HTTPS 模板，必须包含 `{doi}`。
  可配置 `token_env`、`token_header`、`token_prefix`，支持自定义接口。
- 请求跨域重定向时移除所有自定义凭据头；若交付渠道需要另一域认证，应单独配置该域。
- Crossref 已生效的 Creative Commons 许可可启用出版社域内的公开 HTML 落地页，无需机构 HTML 开关；仍需正文和 DOI 校验，不推测 XML 地址。
- OpenAlex 的 `is_oa` 全文位置可作为 HTML 补充来源，仍需正文校验。
- 出版社交付文件可先批量发现 DOI，再逐个登记：

```bash
paperman corpus import-delivery 10.1021/example /data/publisher/article.xml \
  --format xml --access-basis '机构TDM交付批次编号'
```

此命令不生成、转换 HTML/XML，保存交付文件原始字节。

## 校验、恢复与报告

HTML/XML 各自保存和续传，获得一种有效全文即计入“至少一种全文”覆盖率。
两种都成功才计入“双格式”。不以元数据获取成功代替全文获取成功。

XML 必须可解析、含实质正文；HTML 必须具有文章正文标记及多段正文。
PDF、摘要页、登录页、挑战页、错误 XML、DOI 不符不会计入成功。XML 不加载外部 DTD，
拒绝实体声明。部分出版社页面结构可能被保守校验拒绝，应根据真实样本调整。
无机器可读 DOI 的文件标记为需人工核对身份。

文件以临时文件 + 原子替换写入，SQLite 登记 SHA-256。`--resume` 只跳过相应格式
哈希有效的文件；删除或损坏后会重新下载。强制刷新失败时保留先前的有效文件。
单篇网络/校验失败不会停止其他论文；按来源串行限速，默认间隔 10 秒。
网络错误和 5xx/429 最多重试三次；服务端要求等待超过 60 秒时登记待稍后重试，
不会提前发请求。`retry.jsonl` 是报告清单，恢复下载仍使用 `fetch --resume`。

报告包含样本缺口、年份分布、HTML/XML/任一/双格式覆盖率、格式失败分类、下载次数、
重试次数、文件大小和运行耗时；原始发现错误可从 `summary.json` 查看。
缺样本时覆盖率为 null，而不是 0%。`review.tsv` 需人工填写正文、DOI/标题检查结果，
它按 DOI、格式及文件哈希保留人工结果，文件更新后重新复核。

`discover` 有发现错误或 `fetch` 有未获取格式/没有样本时退出码为 1，成功结果仍保留。
不要仅凭退出码判断整批无成果，具体以报告为准。

当前功能只建立原始语料索引。后续段落解析、表格提取、属性数据库和模型抽取应消费
`manifest.jsonl`，并继续保留 DOI 与原文件定位信息。

## 验证

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p test_corpus.py -v
# 安装项目开发依赖后：
pytest tests/
ruff check src/ tests/
```

接口依据：
- https://www.crossref.org/documentation/retrieve-metadata/text-and-data-mining/
- https://dev.elsevier.com/tecdoc_text_mining.html
- https://dev.springernature.com/docs/api-endpoints/open-access/
- https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining
