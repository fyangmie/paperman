# Paperman 设计方案

## 1. 项目定位

一个增强型的学术论文下载器 CLI，支持多源元数据获取 + 多通道 PDF 下载 + 本地文献管理。

---

## 2. 整体架构

```
paperman/
├── src/paperman/
│   ├── __init__.py
│   ├── __main__.py
│   │
│   ├── cli.py                 # typer CLI 入口
│   ├── config.py              # 全局配置
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── paper.py           # Paper 数据模型（Pydantic）
│   │
│   ├── sources/               # 输入源识别
│   │   ├── __init__.py
│   │   ├── classifier.py      # 识别 DOI / PMID / arXiv / URL / Title
│   │   └── source.py          # Source 数据类
│   │
│   ├── fetchers/              # 元数据获取
│   │   ├── __init__.py
│   │   ├── base.py            # BaseFetcher 抽象
│   │   ├── crossref.py        # CrossRef API
│   │   ├── pubmed.py          # PubMed / NCBI E-utilities
│   │   └── arxiv.py           # arXiv API
│   │
│   ├── downloaders/           # PDF 下载
│   │   ├── __init__.py
│   │   ├── base.py            # BaseDownloader 抽象
│   │   ├── pipeline.py        # 多级回退链调度
│   │   ├── arxiv.py           # arXiv 直链
│   │   ├── pmc.py             # PubMed Central
│   │   ├── publisher.py       # 出版社 URL 推断
│   │   └── scihub.py          # Sci-Hub
│   │
│   ├── exporters/             # 输出
│   │   ├── __init__.py
│   │   ├── pdf.py             # PDF 保存
│   │   ├── bibtex.py          # BibTeX 导出
│   │   └── yaml.py            # YAML 元数据导出
│   │
│   ├── cache/                 # 缓存层
│   │   ├── __init__.py
│   │   └── sqlite.py          # SQLite 缓存
│   │
│   └── utils/
│       ├── __init__.py
│       ├── log.py             # loguru 配置
│       ├── console.py         # rich 终端
│       └── network.py         # HTTP session 管理
```

---

## 3. 数据流

```
用户输入 (DOI/PMID/URL/Title)
        │
        ▼
  ┌─────────────┐
  │ classifier  │──判类型─→ Source(doi=xxx, type='doi')
  └─────────────┘
        │
        ▼
  ┌──────────────┐
  │ fetchers     │──尝试顺序：CrossRef → PubMed → arXiv
  │ (metadata)   │
  └──────────────┘
        │
        ▼
  ┌──────────────┐
  │ Paper 模型   │──含 title, authors, journal, year, doi, pmid, abstract...
  └──────────────┘
        │
        ▼
  ┌──────────────────┐
  │ downloader       │──回退链：arXiv/PMC 免费 → 出版社推断 → Sci-Hub
  │ (PDF pipeline)   │
  └──────────────────┘
        │
        ▼
  ┌──────────────────┐
  │ exporters        │── PDF + metadata.yaml + .bib
  └──────────────────┘
```

---

## 4. 模块设计

### 4.1 Sources 模块

```python
@dataclass
class Source:
    raw: str              # 用户原始输入
    type: SourceType      # doi | pmid | arxiv | title | url
    cleaned: str          # 清洗后的值
```

`classifier.py` 负责判断输入类型：

```
"10.1126/science.aef0825"     → type=doi
"2505.13400"                  → type=arxiv
"40296124"                    → type=pmid
"PIEZO1 controls liver..."    → type=title
```

### 4.2 Fetchers 模块（元数据）

每个 fetcher 继承 BaseFetcher：

```python
class BaseFetcher(ABC):
    name: str
    priority: int            # 尝试顺序
    def fetch(Source) -> Optional[Paper]
```

实现类：
- **CrossRefFetcher** (priority=1): REST API，覆盖面最广，但需邮箱标识
- **PubMedFetcher** (priority=2): NCBI E-utilities，PMID 查询，提供摘要
- **ArxivFetcher** (priority=3): arXiv API，仅限 arXiv 论文

三路并行或串行，取第一个非空结果。

### 4.3 Downloaders 模块（PDF 下载）

四级回退链，每个 Downloader 实现：

```python
class BaseDownloader(ABC):
    name: str
    def get_pdf_url(Paper) -> Optional[str]
    def download(Paper, dest) -> Optional[Path]
```

**Level 0 — Open Access 直链：**
- arXiv → 已有免费 PDF
- PMC → 有 PMCID 的直接构造 pubmedcentral PDF 链接

**Level 1 — 出版社 URL 推断（参考 metapub.FindIt 的 registry 思路）：**
维护一个出版社 URL pattern 表：

```python
PUBLISHER_PATTERNS = {
    "10.1016":  "https://www.sciencedirect.com/science/article/pii/{doi_suffix}/pdfft",
    "10.1038":  "https://www.nature.com/articles/{doi_suffix}.pdf",
    "10.1126":  "https://www.science.org/doi/pdf/{doi}",
    "10.1161":  "https://www.ahajournals.org/doi/pdf/{doi}",
    "10.1186":  "https://link.springer.com/content/pdf/{doi}.pdf",
    "10.1093":  "https://academic.oup.com/{journal}/article-pdf/{doi}/{article}.pdf",
}
```

发送 HEAD 请求验证链接有效性。

**Level 2 — Sci-Hub（参考原项目 + SciDownl）：**
- 自动检测可用 Sci-Hub 镜像
- DOI → Sci-Hub → 提取 iframe PDF 链接 → 下载

**Level 3 — Google Scholar 搜索（参考 PyPaperBot）：**
- 通过标题搜索 Google Scholar
- 提取 PDF 链接

### 4.4 缓存层

```python
class PaperCache:
    def get(doi) -> Optional[Paper]
    def set(paper: Paper)
    def has(doi) -> bool
```

使用 SQLite 缓存已查询的元数据和 PDF 路径，避免重复请求。

### 4.5 输出

- PDF 文件：`{title}.pdf`
- Metadata 文件：`{title}.yaml`
- BibTeX 导出：`{title}.bib`
- 可选输出目录结构：`{year}/{author}/{title}/`

---

## 5. CLI 命令设计

```
paperman [OPTIONS] COMMAND [ARGS]...

Options:
  -v, --verbose            Verbose logging
  -o, --output PATH        输出目录（默认 ~/Documents/papers）

Commands:
  download  通过 DOI/PMID/URL 下载论文
  search    搜索论文（CrossRef / arXiv）
  show      查看已下载论文信息
  list      列出本地库中的论文
  config    查看/修改配置
```

### download 子命令

```
paperman download [OPTIONS] IDENTIFIER

Arguments:
  IDENTIFIER        DOI / PMID / arXiv ID / URL

Options:
  --bib             同时导出 BibTeX
  --no-pdf          只获取元数据，不下载 PDF
  --all             显示完整元数据（包括摘要）
```

### search 子命令

```
paperman search [OPTIONS] QUERY

Arguments:
  QUERY             搜索关键词

Options:
  --source          搜索源：crossref | arxiv | all（默认 all）
  --limit NUMBER    结果数量（默认 10）
  --download        同时下载搜索结果
```

---

## 6. 实施方案（三阶段）

### Phase 1：基础框架 ✅

- [x] CLI 入口（typer）
- [x] Paper 数据模型（Pydantic）
- [x] CrossRef 元数据获取
- [x] arXiv 元数据 + PDF 下载
- [x] Sci-Hub downloader — iframe 提取 + 镜像自动发现
- [x] Source classifier — DOI/PMID/arXiv/URL/Title 自动识别
- [x] BaseDownloader + Pipeline — 四级回退链框架

### Phase 2：增强下载能力 ✅

- [x] PubMed fetcher — NCBI E-utilities 获取 PMID→元数据
- [x] PMC downloader — 有 PMCID 的从 PMC 免费下载
- [x] Publisher URL 推断 — 12 家常用出版社 pattern 覆盖
- [x] Sci-Hub mirror 自动探测 — 多镜像轮换
- [x] **SQLite 缓存** — 避免重复查询
- [x] `paperman search` — arXiv + CrossRef 双源搜索 + 交互式选择下载
- [x] `paperman list / show` — 本地库管理
- [x] 批量下载 — 从文件读 DOI 列表

### Phase 3：完善体验 ✅

- [x] **Google Scholar 搜索** — 参考 PyPaperBot 实现
- [x] **配置文件完善** — 默认输出目录、代理设置
- [x] **bibtex 导出完善** — 完整 BibTeX 格式（abstract、keyword、pmid等）
- [x] **Zotero 集成** — 导出 Better BibTeX 格式，Zotero 自动监控导入
- [x] **pip 发布** — pyproject.toml 完善，`pip install paperman` 就绪

---

## 7. 与参考项目的对比优势

| 能力 | scihub.py | PyPaperBot | metapub | SciDownl | **paperman** |
|------|-----------|------------|---------|----------|-------------|
| 多源元数据 | ✗ | ✗ | ✓ | ✗ | **✓** |
| OA 免费直链 | ✗ | ✗ | ✓ | ✗ | **✓** |
| 出版社 URL 推断 | ✗ | ✗ | ✓ | ✗ | **✓** |
| Sci-Hub 下载 | ✓ | ✓ | ✗ | ✓ | **✓** |
| Google Scholar | ✓ | ✓ | ✗ | ✗ | **✓** |
| 缓存 | ✗ | ✗ | ✓ | ✗ | **✓** |
| 多种输出格式 | ✗ | 仅PDF | ✓ | ✗ | **✓** |
| rich 终端 | ✗ | ✗ | ✗ | ✗ | **✓** |
