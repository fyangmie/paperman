# Paperman

Enhanced academic paper downloader — 多源元数据获取 + 多通道 PDF 下载 + 本地缓存管理。

---

## 技术栈

| 层 | 技术 |
|------|--------|
| CLI 框架 | [typer](https://typer.tiangolo.com/) |
| 终端渲染 | [rich](https://rich.readthedocs.io/) |
| 日志 | [loguru](https://loguru.readthedocs.io/) |
| 数据模型 | [pydantic](https://docs.pydantic.dev/) |
| HTTP | [requests](https://requests.readthedocs.io/) |
| HTML 解析 | [beautifulsoup4](https://www.crummy.com/software/BeautifulSoup/) |
| 缓存 | SQLite（Python 内置） |
| 数据格式 | YAML / BibTeX |
| 包管理 | [pixi](https://pixi.sh/) |
| 代码质量 | [ruff](https://docs.astral.sh/ruff/) |
| 测试 | [pytest](https://docs.pytest.org/) |
| 构建（可选） | [Nuitka](https://nuitka.net/) |

---

## 安装

### 方式一：pixi（推荐）

```bash
git clone https://github.com/laq12345/paperman
cd paperman
pixi install
pixi run paperman --help
```

### 方式二：pip

```bash
pip install paperman
paperman --help
```

### 方式三：Nuitka 单文件二进制

```bash
pixi run nuitka --standalone --onefile -o paperman src/paperman/cli.py
./dist/paperman --help
```

> 二进制约 50MB，包含 Python 解释器和全部依赖，无需 Python 环境即可运行。

---

## 快速开始

```bash
# 下载论文（DOI）
paperman download 10.1186/s13054-026-05843-y

# 下载论文（PMID）
paperman download 40296124

# 下载论文（arXiv ID）
paperman download 2505.13400

# 搜索论文
paperman search "piezo1 liver regeneration"

# 查看本地缓存
paperman list
paperman stats
```

---

## 完整命令参考

### `download` — 下载论文

```
paperman download [OPTIONS] IDENTIFIER
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `IDENTIFIER` | 必填 | DOI / PMID / arXiv ID / URL / 标题 |
| `-o, --output` | PATH | 输出目录（默认 `~/Documents/papers`） |
| `--bib` | flag | 同时导出 BibTeX |
| `--no-pdf` | flag | 只获取元数据，不下载 PDF |
| `-f, --force` | flag | 忽略缓存，重新下载 |

**支持输入格式示例：**

```bash
paperman download 10.1186/s13054-026-05843-y       # DOI
paperman download 40296124                           # PMID
paperman download 2505.13400                         # arXiv ID
paperman download https://doi.org/10.1126/science.aef0825  # DOI URL
paperman download https://pubmed.ncbi.nlm.nih.gov/40296124/ # PubMed URL
paperman download https://arxiv.org/abs/2505.13400  # arXiv URL
paperman download "piezo1 liver regeneration"        # 标题搜索
```

**四级下载管道：**

```
arXiv 免费直链  →  PMC 免费  →  出版社 URL 推断  →  Sci-Hub
 |_ Level 0     |_ Level 1  |_ Level 2           |_ Level 3
```

每个下载器按优先级顺序尝试，前一个失败自动切换到下一个。支持重试 + 代理切换。

**支持 30 家出版社 URL 推断：**

| DOI 前缀 | 出版社/期刊 |
|----------|------------|
| `10.1016` | Elsevier / ScienceDirect |
| `10.1038` | Nature Publishing Group |
| `10.1126` | Science |
| `10.1161` | AHA Journals (Circulation, Circ Res) |
| `10.1186` | Springer / BioMed Central |
| `10.1007` | Springer |
| `10.1093` | Oxford University Press |
| `10.3390` | MDPI |
| `10.1111` | Wiley |
| `10.1021` | American Chemical Society |
| `10.1080` | Taylor & Francis |
| `10.1056` | New England Journal of Medicine |
| `10.1136` | BMJ |
| `10.1152` | American Physiological Society |
| `10.1158` | AACR (Cancer Research) |
| `10.4049` | Journal of Immunology |
| `10.1681` | JASN |
| `10.1200` | Journal of Clinical Oncology |
| `10.1210` | Endocrine Society |
| `10.1172` | JCI |
| `10.1371` | PLOS |
| `10.15252` | EMBO Press |
| `10.1242` | Company of Biologists |
| `10.1101` | bioRxiv / medRxiv |
| `10.1073` | PNAS |
| `10.1084` | Rockefeller University Press |
| `10.2337` | Diabetes |
| `10.4161` | Landes Bioscience |
| `10.2147` | Dove Press |
| `10.21037` | AME Publishing |

---

### `search` — 搜索论文

```
paperman search [OPTIONS] QUERY
```

**参数：**

| 参数 | 说明 |
|------|------|
| `QUERY` | 搜索关键词 |
| `-l, --limit` | 结果数量（默认 10） |
| `-s, --source` | 搜索源：`crossref` / `pubmed` / `all` |
| `-d, --download` | 搜索后选择序号下载 |
| `--csv` | CSV 格式输出（方便复制粘贴） |

**示例：**

```bash
# CrossRef 搜索
paperman search "mechanosensing piezo1" -l 5

# PubMed 搜索
paperman search "piezo1" --source pubmed -l 5 --csv

# 双源搜索 + 下载
paperman search "liver regeneration" --source all -l 10 -d
```

---

### `scholar` — Google Scholar 搜索

```
paperman scholar [OPTIONS] QUERY
```

| 参数 | 说明 |
|------|------|
| `QUERY` | 搜索关键词 |
| `-l, --limit` | 结果数量（默认 5） |
| `-d, --download` | 下载所有结果 |
| `--csv` | CSV 格式输出 |

当 `requests` 被拦截时，自动 fallback 到 Selenium + Chrome 重试。（需安装 Chrome/Chromium）

```bash
paperman scholar "piezo1 liver" -l 10 --csv
```

---

### `batch` — 批量下载

```
paperman batch [OPTIONS] FILE
```

| 参数 | 说明 |
|------|------|
| `FILE` | 文本文件，每行一个 DOI/PMID |
| `-o, --output` | 输出目录 |
| `--bib` | 导出 BibTeX |
| `--no-pdf` | 只获取元数据 |
| `-r, --resume` | 跳过已下载的论文 |

```bash
# 准备文件
echo "10.1126/science.aef0825" > doilist.txt
echo "10.1186/s13054-026-05843-y" >> doilist.txt

# 批量下载
paperman batch doilist.txt

# 续传：跳过已下载的
paperman batch doilist.txt --resume
```

---

### `list` — 查看缓存

```
paperman list [OPTIONS]
```

| 参数 | 说明 |
|------|------|
| `-q, --query` | 按关键词过滤 |

```bash
paperman list
paperman list -q piezo1
```

---

### `show` — 查看缓存详情

```
paperman show IDENTIFIER
```

```bash
paperman show 10.1186/s12931-025-03240-7
paperman show 40296124
```

显示完整元数据：标题、作者、期刊、年份、DOI、PMID、PMCID、摘要。

---

### `stats` — 统计信息

```
paperman stats
```

显示缓存统计和磁盘文件统计，并排展示年份分布：

```
Cache (metadata queried)                         │ 24
  ├─ With valid PDF                              │ 3
  └─ Stale (file deleted)                        │ 2
Files on disk (~/Documents/papers)               │ 5
  └─ Total size                                  │ 15.2 MB
Cache by Year     Disk by Year
┌──────┬───┐     ┌──────┬───┐
│ 2026 │ 8 │     │ 2026 │ 2 │
│ 2025 │ 5 │     │ 2025 │ 1 │
```

---

### `config` — 配置管理

```
paperman config [OPTIONS]
```

```bash
# 查看当前配置
paperman config

# 设置代理（支持 HTTP/HTTPS/SOCKS5）
paperman config --set proxy socks5://127.0.0.1:1080

# 设置默认输出目录
paperman config --set output ~/papers
```

配置文件：`~/.config/paperman/config.ini`

```ini
[settings]
output = /var/home/smile/Documents/papers
proxy = socks5://127.0.0.1:1080
```

---

### `prune` — 清理缓存

```
paperman prune [OPTIONS]
```

| 参数 | 说明 |
|------|------|
| `-n, --dry-run` | 预览要删除的条目 |
| `-y, --yes` | 跳过确认 |
| `-a, --all` | 清空全部缓存 |

```bash
paperman prune --dry-run           # 预览过期条目
paperman prune -y                  # 清理过期条目
paperman prune --all -y            # 清空全部缓存
```

---

### `remove` — 删除单条缓存

```
paperman remove IDENTIFIER
```

```bash
paperman remove 10.1073/pnas.2407765121 -y
```

同时删除缓存记录和 PDF 文件。

---

## 输出文件

下载一篇论文后输出目录生成：

```
~/Documents/papers/
├── {title}.yaml          # 元数据（YAML 格式）
├── {title}.pdf           # PDF 全文（如果下载成功）
└── {title}.bib           # BibTeX（如果指定 --bib）
```

YAML 元数据示例：

```yaml
title: 'PIEZO-dependent mechanosensing is essential...'
authors: [Meryem B. Baghdadi, Ronja M. Houtekamer, ...]
journal: Science
year: 2024
doi: 10.1126/science.adj7615
pmcid: PMC12893899
abstract: 'Stem cells perceive and respond to biochemical and physical signals...'
sources:
  metadata: crossref
  pdf: publisher
```

BibTeX 示例：

```bibtex
@article{Baghdadi2024,
  author = {Meryem B. Baghdadi and Ronja M. Houtekamer ...},
  title = {PIEZO-dependent mechanosensing is essential for intestinal stem cell fate decision and maintenance},
  journal = {Science},
  year = 2024,
  doi = {10.1126/science.adj7615},
  pmid = {39607940},
  pmcid = {PMC12893899}
}
```

---

## 缓存系统

**位置：** `~/.cache/paperman/papers.db`（SQLite）

**自动缓存：**
- 每次 `download` 自动缓存元数据
- 再次下载同篇论文时秒回，不重复请求 API
- `list` / `show` / `stats` 命令离线可用

**手动管理：**

```bash
paperman list               # 查看所有缓存
paperman show 10.xxx        # 查看单篇详情
paperman stats              # 统计缓存 + 磁盘
paperman remove 10.xxx      # 删除一条
paperman prune              # 批量清理过期
paperman prune --all        # 清空全部
```

---

## 高级用法

### 代理配置

在家无法访问出版社时，可通过代理走学校网络：

```bash
paperman config --set proxy http://proxy.example.edu:8080
paperman config --set proxy socks5://127.0.0.1:1080
```

设置后所有 HTTP 请求（包括下载管道）都会走代理。

### Nuitka 构建

```bash
pixi add nuitka --pypi
pixi run nuitka --standalone --onefile -o paperman src/paperman/cli.py
```

产物 `dist/paperman` 是单文件二进制，可直接拷贝到其他机器运行。

### 搭配 Zotero 使用

```bash
paperman download 10.xxx --bib
```

生成的 `.bib` 文件可直接拖入 Zotero，自动导入元数据和 PDF 附件。

---

## 开发

### 环境

需要 [pixi](https://pixi.sh/)（推荐）或 conda + pip。

```bash
git clone https://github.com/laq12345/paperman
cd paperman
pixi install          # 安装全部依赖
pixi run paperman     # 运行
```

### 命令

```bash
pixi run check        # ruff lint 检查
pixi run fix          # ruff 自动修复
pixi run test         # pytest 运行测试
pixi run all          # lint + test 一站式
```

### 测试

```bash
# 单元测试（22 项）
pixi run test

# 完整功能测试（26 项，含网络请求）
pixi run python tests/run_all_tests.py
```

### 项目结构

```
paperman/
├── pyproject.toml               # 项目配置 + 依赖管理
├── .github/workflows/ci.yml     # GitHub Actions CI
├── tests/
│   ├── test_classifier.py       # 输入识别测试
│   ├── test_models.py           # 数据模型测试
│   ├── test_publisher.py        # 出版社 pattern 测试
│   ├── test_integration.py      # 管道集成测试
│   └── run_all_tests.py         # 全功能测试脚本
└── src/paperman/
    ├── cli.py                   # typer CLI 入口
    ├── __main__.py              # python -m paperman
    ├── models/paper.py          # Paper 数据模型
    ├── sources/classifier.py    # DOI/PMID/arXiv/URL 识别
    ├── fetchers/
    │   ├── crossref.py          # CrossRef 元数据
    │   ├── pubmed.py            # PubMed 元数据
    │   ├── arxiv.py             # arXiv 元数据
    │   └── scholar.py           # Google Scholar 搜索
    ├── downloaders/
    │   ├── base.py              # 下载器基类
    │   ├── pipeline.py          # 四级回退管道
    │   ├── arxiv.py             # arXiv 免费直链
    │   ├── pmc.py               # PubMed Central
    │   ├── publisher.py         # 出版社 URL 推断
    │   └── scihub.py            # Sci-Hub
    ├── exporters/               # YAML / BibTeX 导出
    ├── cache/                   # SQLite 缓存
    └── utils/                   # loguru / rich / HTTP
```

### 代码质量

```bash
ruff check src/          # 零警告
pytest tests/            # 22 项测试通过
```

---

## 许可

MIT
