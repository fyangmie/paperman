# Paperman

Enhanced academic paper downloader CLI.  
多源元数据获取 + 多通道 PDF 下载 + 本地缓存管理。

---

## 安装

```bash
git clone https://github.com/laq12345/paperman
cd paperman
pixi run paperman --help    # 直接运行
```

或通过 pip 安装：

```bash
pip install paperman
```

---

## 快速开始

```bash
# 通过 DOI 下载论文
paperman download 10.1126/science.aef0825

# 通过 PMID 下载
paperman download 40296124

# 通过 arXiv ID
paperman download 2505.13400

# 搜索论文
paperman search "piezo1 liver regeneration"

# 查看本地缓存
paperman list
paperman stats
```

---

## 命令详解

### `download` — 下载论文

```bash
paperman download [OPTIONS] IDENTIFIER
```

**参数：**

| 参数 | 说明 |
|------|------|
| `IDENTIFIER` | DOI / PMID / arXiv ID / URL / 标题 |
| `-o, --output PATH` | 输出目录（默认 `~/Documents/papers`） |
| `--bib` | 同时导出 BibTeX |
| `--no-pdf` | 只获取元数据，不下载 PDF |
| `-f, --force` | 忽略缓存，重新下载 |

**支持的输入格式：**

```bash
paperman download 10.1186/s13054-026-05843-y       # DOI
paperman download 40296124                           # PMID
paperman download 2505.13400                         # arXiv ID
paperman download https://doi.org/10.1126/...        # URL
paperman download "piezo1 liver regeneration"        # 标题搜索
```

**下载管道（四级回退）：**

```
arXiv 免费直链  →  PMC 免费  →  出版社 URL 推断  →  Sci-Hub
 Level 0            Level 1         Level 2           Level 3
```

每个下载器按优先级顺序尝试，前一个失败自动切换到下一个。

**支持 20+ 出版社 URL 推断：**

| DOI 前缀 | 出版社 |
|----------|--------|
| `10.1016` | Elsevier / ScienceDirect |
| `10.1038` | Nature |
| `10.1126` | Science |
| `10.1161` | AHA Journals (Circulation 等) |
| `10.1186` | Springer / BioMed Central |
| `10.1007` | Springer |
| `10.1093` | Oxford University Press |
| `10.3390` | MDPI |
| `10.1111` | Wiley |
| `10.1021` | ACS |
| `10.1172` | JCI |
| `10.1073` | PNAS |
| `10.1371` | PLOS |
| `10.15252` | EMBO Press |
| `10.1242` | Company of Biologists |

---

### `search` — 搜索论文

```bash
paperman search [OPTIONS] QUERY
```

通过 CrossRef 搜索论文，交互式选择下载。

| 参数 | 说明 |
|------|------|
| `QUERY` | 搜索关键词 |
| `-l, --limit N` | 结果数量（默认 10） |
| `-d, --download` | 搜索完成后提示选择序号并下载 |

**示例：**

```bash
# 搜索
paperman search "mechanosensing piezo1"

# 搜索 + 直接下载第 3 篇
paperman search "ecm stiffness cancer" -d
```

---

### `batch` — 批量下载

```bash
paperman batch [OPTIONS] FILE
```

从文本文件批量下载论文，每行一个 DOI/PMID。

```bash
# 准备文件 doilist.txt
# 10.1126/science.aef0825
# 10.1186/s13054-026-05843-y
# 10.1038/s41586-026-10644-y

# 批量下载
paperman batch doilist.txt

# 指定输出目录
paperman batch doilist.txt -o ~/papers
```

---

### `list` — 查看缓存

```bash
paperman list [OPTIONS]
```

| 参数 | 说明 |
|------|------|
| `-q, --query TEXT` | 按关键词过滤 |

显示缓存中所有论文的 DOI、标题、年份和 PDF 状态。

---

### `show` — 查看详情

```bash
paperman show IDENTIFIER
```

查看缓存中某篇论文的完整元数据。

```bash
paperman show 10.1186/s12931-025-03240-7
```

---

### `stats` — 统计信息

```bash
paperman stats
```

显示缓存统计和磁盘文件统计，**并排展示**两个年份分布表。

```
Cache (metadata queried)                         │ 4
  ├─ With valid PDF                              │ 1
  └─ Stale (file deleted)                        │ 1
Files on disk (~/Documents/papers)               │ 2
  └─ Total size                                  │ 10.2 MB
Cache by Year     Disk by Year
┌──────┬───┐     ┌──────┬───┐
│ 2026 │ 2 │     │ 2026 │ 1 │
│ 2025 │ 2 │     │ 2025 │ 1 │
└──────┴───┘     └──────┴───┘
```

---

### `config` — 配置管理

```bash
# 查看当前配置
paperman config

# 设置代理
paperman config --set proxy socks5://127.0.0.1:1080

# 设置默认输出目录
paperman config --set output ~/papers
```

配置文件位置：`~/.config/paperman/config.ini`

---

### `scholar` — Google Scholar 搜索

```bash
paperman scholar [OPTIONS] QUERY
```

| 参数 | 说明 |
|------|------|
| `QUERY` | 搜索关键词 |
| `-l, --limit N` | 结果数量（默认 5） |
| `-d, --download` | 下载所有结果 |

> 注意：Google Scholar 有反爬机制，可能触发 CAPTCHA 验证。

---

## 输出文件

下载一篇论文后，输出目录下生成：

```
~/Documents/papers/
├── {title}.yaml          # 元数据（YAML 格式）
├── {title}.pdf           # PDF 全文（如果下载成功）
└── {title}.bib           # BibTeX（如果指定 --bib）
```

YAML 元数据示例：

```yaml
title: 'PIEZO-dependent mechanosensing is essential for intestinal stem cell fate decision and maintenance'
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

---

## 缓存系统

查询过的论文元数据自动缓存在 `~/.cache/paperman/papers.db`（SQLite）。

**作用：**
- 重复下载秒回，免去重复请求 API
- `list` / `show` / `stats` 命令离线可用

**管理缓存：**

```bash
paperman list               # 查看所有缓存
paperman show 10.xxx        # 查看单篇详情
paperman stats              # 统计缓存 + 磁盘文件
paperman remove 10.xxx      # 删除某条缓存（同时删 PDF）
```

---

## 配置

配置文件：`~/.config/paperman/config.ini`

```ini
[settings]
output = /var/home/smile/Documents/papers
proxy = socks5://127.0.0.1:1080
```

---

## 开发

```bash
# 安装依赖
pixi install

# 代码检查
pixi run check        # ruff lint

# 自动修复
pixi run fix

# 运行测试
pixi run test         # pytest 15 项

# 全部检查
pixi run all          # lint + test
```

---

## 项目结构

```
paperman/
├── pyproject.toml          # 依赖 + 构建配置
├── src/paperman/
│   ├── cli.py              # typer CLI 入口
│   ├── models/paper.py     # Paper 数据模型
│   ├── sources/            # 输入类型识别
│   ├── fetchers/           # CrossRef, arXiv, PubMed
│   ├── downloaders/        # 四级下载管道
│   ├── exporters/          # YAML, BibTeX 导出
│   ├── cache/              # SQLite 缓存
│   └── utils/              # loguru, rich, 网络
└── tests/                   # pytest 测试
```
