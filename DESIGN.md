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
│   ├── cli.py                 # typer CLI 入口（全部命令）
│   │
│   ├── models/
│   │   └── paper.py           # Paper 数据模型（Pydantic）
│   │
│   ├── sources/
│   │   └── classifier.py      # 识别 DOI / PMID / arXiv / URL / Title
│   │
│   ├── fetchers/              # 元数据获取（串行回退）
│   │   ├── __init__.py        # BaseFetcher 抽象
│   │   ├── crossref.py        # CrossRef REST API
│   │   ├── pubmed.py          # NCBI E-utilities + EuropePMC
│   │   ├── arxiv.py           # arXiv API
│   │   ├── openalex.py        # OpenAlex（含摘要、概念、OA 链接）
│   │   └── scholar.py         # Google Scholar（requests 模式）
│   │
│   ├── downloaders/           # PDF 下载（四级回退链）
│   │   ├── __init__.py
│   │   ├── base.py            # BaseDownloader 抽象 + PDF 下载
│   │   ├── pipeline.py        # 优先级调度
│   │   ├── arxiv.py           # arXiv 直链
│   │   ├── pmc.py             # PubMed Central
│   │   ├── publisher.py       # 31 家出版社 URL 推断
│   │   └── scihub.py          # Sci-Hub 镜像发现
│   │
│   ├── exporters/             # YAML / BibTeX 导出
│   │   └── __init__.py
│   │
│   ├── cache/                 # SQLite 缓存
│   │   └── __init__.py
│   │
│   └── utils/
│       ├── log.py             # loguru 配置
│       ├── console.py         # rich 终端
│       └── network.py         # 统一 HTTP client（proxy 感知）
```

---

## 3. 数据流

```
用户输入 (DOI/PMID/arXiv URL/Title)
        │
        ▼
  ┌─────────────┐
  │ classifier  │──判类型 → Source(doi=xxx, type='doi')
  └─────────────┘
        │
        ▼
  ┌──────────────────┐
  │ fetchers          │
  │ (元数据串行回退)  │
  │                   │
  │ 优先顺序：        │
  │  1. CrossRef      │
  │  2. arXiv         │
  │  3. OpenAlex      │
  │  4. PubMed (PMID) │
  └──────────────────┘
        │
        ▼
  ┌──────────────────┐
  │ Paper 模型       │──含 title, authors, journal, year, doi,
  │ (Pydantic)       │   pmid, abstract, keywords, pdf_url...
  └──────────────────┘
        │
        ▼
  ┌──────────────────┐
  │ downloader       │──四级回退链（优先级顺序）：
  │ (PDF pipeline)   │  arXiv → PMC → 出版社推断 → Sci-Hub
  └──────────────────┘
        │
        ▼
  ┌──────────────────┐
  │ exporters        │── {title}.pdf + {title}.yaml + {title}.bib
  └──────────────────┘
        │
        ▼
  ┌──────────────────┐
  │ SQLite cache     │──自动缓存 + 下次秒回
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
    def fetch(identifier: str, source_type: SourceType) -> Optional[Paper]
```

实现类（串行尝试，取第一个非空结果）：
- **CrossRefFetcher** (priority=1): REST API，覆盖面最广
- **ArxivFetcher** (priority=3): arXiv API，仅限 arXiv 论文
- **OpenAlexFetcher** (priority=4): 开放学术图谱，含摘要（inverted index 解码）、概念分类、OA PDF 链接、引用数
- **PubMedFetcher** (priority=2, PMID 时优先): NCBI E-utilities，支持 ncbi_api_key 配置提升速率

PubMedFetcher 还提供：
- `search_by_query()` — PubMed 搜索
- `search_europepmc()` — Europe PMC 搜索（含 preprint）
- `resolve_pmcid()` — DOI → PMCID 解析

### 4.3 Downloaders 模块（PDF 下载）

四级回退链，按 priority 排序：

```python
class BaseDownloader(ABC):
    name: str
    priority: int            # 执行顺序
    def get_pdf_url(Paper) -> Optional[str]
    def download(Paper, dest) -> Optional[Path]
```

**Level 0 — arXiv 直链 (priority=0)：**
- arXiv ID → arXiv PDF URL

**Level 1 — PMC (priority=1)：**
- 有 PMCID 的直接构造 PMC PDF 链接

**Level 2 — 出版社 URL 推断 (priority=2)：**
维护 31 家出版社 URL pattern 表，支持 `{doi}`, `{suffix}`, `{journal}` 变量：
- PLOS 从 DOI 中提取 journal slug 并映射到全名（`pbio` → `plosbiology`）
- bioRxiv 使用无版本 URL，服务端自动处理最新版本
- 对非 PLOS URL 发送 HEAD 验证（404 则跳过）

**Level 3 — Sci-Hub (priority=3)：**
- 自动检测可用镜像（now.sh + 硬编码候选列表）
- DOI → 提取 iframe/embed 中的 PDF 链接

### 4.4 缓存层

```python
class PaperCache:
    def get(doi) -> Optional[Paper]
    def get_by_pmid(pmid) -> Optional[Paper]
    def set(paper: Paper)
    def update_pdf_path(doi, path)
    def list_all() -> list[Paper]
    def search(query) -> list[Paper]
    def remove(doi)
    def close()
```

使用 SQLite（`~/.cache/paperman/papers.db`），支持上下文管理器。
搜索策略：SQL 层粗筛（doi/pmid/data LIKE）→ Python 层精筛（title/authors/journal）。

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

Commands:
  download     通过 DOI/PMID/arXiv ID 下载论文（含元数据 + PDF）
  search       搜索论文（crossref | pubmed | eupmc | openalex | all）
  list         列出缓存论文
  show         查看缓存论文详情（含 Semantic Scholar 引用数）
  batch        从文件批量下载
  import-bib   从 BibTeX 文件导入论文
  open-paper   用系统阅读器打开已下载 PDF
  config       查看/修改配置（proxy, ncbi_api_key, output）
  stats        缓存 + 磁盘统计
  scholar      Google Scholar 搜索（requests 模式）
  prune        清理过期或全部缓存
  remove       删除单条缓存
```

### download

```
paperman download [OPTIONS] IDENTIFIER

Options:  --bib, --no-pdf, -f/--force, -o/--output
```

### search

```
paperman search [OPTIONS] QUERY

Options:
  -s, --source   crossref | pubmed | eupmc | openalex | all (默认 crossref)
  -l, --limit    结果数量（默认 10）
  -d, --download 交互式选择下载
  --csv          CSV 输出
```

### batch

```
paperman batch [OPTIONS] FILE

Options:  -o/--output, --bib, --no-pdf, -r/--resume, -l/--log <path>
```

### import-bib / open-paper

```
paperman import-bib refs.bib           # 从 BibTeX 文件导入
paperman open-paper 10.xxx             # 打开已下载 PDF
```

---

## 6. 实施完成状态

### 基础框架 ✅

- CLI 入口（typer，11 个命令）
- Paper 数据模型（Pydantic + YAML/BibTeX 导出）
- Source classifier — DOI/PMID/arXiv/URL/Title 自动识别
- SQLite 缓存（get/set/search/remove/close + 上下文管理器）
- 统一 HTTP client（proxy 感知，所有请求共享）

### 元数据获取（4 源回退）

- ✅ CrossRef REST API — DOI / 标题查询
- ✅ PubMed / NCBI E-utilities — PMID 查询、搜索、EuropePMC 搜索
- ✅ arXiv API — arXiv ID / 标题查询
- ✅ OpenAlex — DOI / 标题查询（含摘要、概念分类、OA 链接）
- ✅ Google Scholar — requests 搜索（无 Selenium 依赖）

### PDF 下载（四级回退链）

- ✅ arXiv 免费直链
- ✅ PMC 免费 PDF
- ✅ 31 家出版社 URL 推断（含 PLOS 多期刊映射、bioRxiv 无版本）
- ✅ Sci-Hub 镜像发现 + iframe 提取

### CLI 功能

- ✅ `download` — DOI/PMID/arXiv/URL/标题 → 元数据 + PDF + YAML + BibTeX
- ✅ `search` — crossref / pubmed / eupmc / openalex / all 多源搜索
- ✅ `batch` — 文件批量下载 + `--resume` 续传 + `--log` TSV 日志
- ✅ `import-bib` — BibTeX 文件导入
- ✅ `open-paper` — 系统阅读器打开 PDF
- ✅ `list / show / stats` — 缓存管理（show 含 S2 引用数）
- ✅ `config` — proxy / ncbi_api_key / output 配置
- ✅ `prune / remove` — 缓存清理

### 工程

- ✅ ruff lint 零警告
- ✅ 101 项 pytest 单元测试
- ✅ pixi 依赖管理（conda-forge + pypi）
- ✅ GitHub Actions CI
- ✅ Nuitka 单文件构建

---

## 7. 与参考项目的对比优势

| 能力 | scihub.py | papis | getpapers | arxiv.py | **paperman** |
|------|-----------|-------|-----------|----------|-------------|
| 多源元数据 | ✗ | ✓ | 4 源 | 1 源 | **5 源** |
| 摘要 + 概念 | ✗ | ✗ | ✗ | ✓ | **✓ (OA)** |
| OA 免费直链 | ✗ | ✗ | ✗ | ✓ | **✓** |
| 出版社 URL 推断 | ✗ | ✗ | ✗ | ✗ | **31 家** |
| Sci-Hub | ✓ | 插件 | ✗ | ✗ | **✓** |
| 缓存 | ✗ | 文件 | ✗ | ✗ | **SQLite** |
| BibTeX 导入/导出 | ✗ | ✓ | ✗ | ✗ | **✓** |
| EuropePMC + OpenAlex | ✗ | ✗ | EUPMC | ✗ | **✓** |
| 引用数据 | ✗ | ✗ | ✗ | ✗ | **S2 (show)** |
| 批量 + Resume + Log | 文件 | ✗ | ✓ | ✗ | **✓** |
