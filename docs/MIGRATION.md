# 迁移与网络配置

## 新设备安装

复制或克隆本修改版代码，在 Linux 或 WSL 内安装 Python 3.11+ 和 venv 支持。不要直接克隆上游后期望得到本分支新增功能；本分支为 https://github.com/fyangmie/paperman，也可使用纯代码迁移包。不要复制旧设备的 .venv 或 /tmp 运行环境。

新装 Ubuntu 24.04 / WSL Ubuntu 24.04 可先执行：

```bash
sudo apt update
sudo apt install python3 python3-venv git ca-certificates
python3 --version
```

确认 Python 为 3.11 或更高。其他 Linux 发行版使用对应包管理器安装同等组件。解压迁移包后进入含 pyproject.toml 的 paperman 目录，再执行下面的安装命令。首次 pip 安装需要访问依赖仓库；纯代码包不包含所有依赖轮子。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements-tested.txt '.[dev]'
```

需要 SOCKS 时额外安装 '.[socks]'。当前版本约束源于 Linux Python 3.12 实测环境；其他平台先运行测试。虚拟机本身需要能访问 VPN 路由或宿主代理，本程序不会替宿主配置路由。

## 一致的网络配置

PDF 和 HTML/XML 客户端共用配置文件。默认 ~/.config/paperman/config.ini；可用 PAPERMAN_CONFIG 指定另一份文件。复制 examples/config.ini 到私有配置目录后按设备修改，不提交真实配置。以下命令使用独立文件，不覆盖已有配置：

```bash
mkdir -p "$HOME/.config/paperman"
cp -n examples/config.ini "$HOME/.config/paperman/migration.ini"
export PAPERMAN_CONFIG="$HOME/.config/paperman/migration.ini"
```

编辑该文件后，在同一个终端运行诊断和下载命令；新终端需要重新设置 PAPERMAN_CONFIG 或使用默认 config.ini。

校园 VPN 通常先选择 direct：

```ini
[settings]
proxy_mode = direct
proxy =
```

direct 忽略 HTTP_PROXY / HTTPS_PROXY 等环境代理，使用操作系统路由；并不表示绕过系统 VPN。配置 proxy_mode = auto 时，可使用配置中的 proxy；没有显式 proxy 则遵循 requests 的环境代理；显式 proxy 优先于环境变量。

PAPERMAN_CORPUS_PROXY 只覆盖 HTML/XML 客户端。PAPERMAN_SCIHUB_PROXY 只提供 Sci-Hub 的独立代理尝试，前面仍会尝试直连。代理地址需使用新设备实际可达的地址，不能直接照抄旧 WSL 网关。localhost 在虚拟机、WSL 与宿主机上未必指向同一服务。

```bash
paperman-doctor
paperman-doctor --online
```

不加 --online 只读配置；加后分别检查 PDF 和 HTML/XML 的出口。诊断隐藏代理认证信息。校园 IP 或浏览器显示学校名称不能单独证明 Python 请求已经拥有某篇的下载权限；浏览器 Cookie 不会自动同步。不要关闭 TLS 校验解决连通性问题。

## PDF 批量任务与迁移

```bash
paperman-bulk /data/dois.txt --output /data/pdf-task --timeout 180
paperman-bulk /data/dois.txt --output /data/pdf-task --report-only
```

迁移前停止旧任务，复制 DOI 列表及整个 pdf-task 文件夹到新设备，再运行同一命令并修改路径。任务按 DOI 哈希定位目录，不依赖原设备绝对路径；新 PDF 清单使用相对路径。历史 YAML 中可能仍保留旧绝对路径，批量恢复不依赖它。

每次正常运行重新解析已有 PDF；有页且无解析错误的文件会跳过，未发现目标 DOI 的记录为 needs_review。扫描前 20 页发现 DOI 标记为 downloaded / verified；引用列表也可能出现 DOI，仍不代表人工核实。SHA256 用于留存当前文件指纹，并非签名或防篡改保证。

每 DOI 目录含 pdfs/、result.json 和 attempts/。根目录 summary.json 从最新每 DOI 结果重建，attempts.jsonl 保留尝试历史。report-only 仅重算记录，不重新打开 PDF；旧记录缺少审计证据时不计入 verified_pdf_papers。saved_pdf_papers 包含待复核记录。

同一输出目录只允许一个任务。超时和中断会终止该 DOI 的子进程组。Ctrl+C 中断会记录 interrupted，重跑会继续；强制断电或 SIGKILL 仍可能留下 running，应结合实际进程确认。遇到损坏文件会重试，先保留备份以便比较。

## HTML/XML 数据

默认数据目录为 ~/Documents/paperman/corpus；PAPERMAN_DATA_DIR 改变其父目录。推荐每次明确指定 -o。迁移前停止写入，然后复制整个语料目录（数据库、manifest、下载文件和报告），按 README 的三个命令恢复。原有 polymer_corpus 不会自动搬动，应传入它的完整路径。

HTML/XML 仍有不同出版社的格式、认证与访问限制，PDF 成功率不能套用。CORPUS.md 说明正文校验及报告。

## 备份与发布

私有备份可以包含语料和认证信息，但不要推送到 GitHub。公开准备时检查 git status、git diff --cached 和待提交文件名，特别是 .env、config.ini、cookies、浏览器配置、日志、PDF 与数据库。gitignore 不会移除已经跟踪过的敏感文件。

公开仓库应作为 upstream 的 fork，保留 MIT 文件与 Git 历史，并在说明中列出修改。项目 Homepage 指向 fyangmie/paperman，Upstream 单独保留原仓库链接。

## 来源和重试

默认保留现有顺序，也可以显式指定：

```bash
paperman-bulk /data/dois.txt --output /data/pdf-task --timeout 180 --retries 1 --sources arxiv,pmc,scihub,publisher,arxiv_title
```

--retries 是额外轮数，0 表示普通来源只尝试一轮。arxiv_title 若启用必须在最后，在普通来源所有轮次失败后尝试一次。省略某个来源就不会访问它。原生 paperman 命令也可以通过 PAPERMAN_SOURCES 和 PAPERMAN_RETRIES 使用相同设置。

每次尝试保留 stages.jsonl；result.json 区分 article_publisher（元数据的出版社名称）与 download_source（实际文件渠道），并记录 failure_stage 和 last_source。网络失败细节保留在 requests.jsonl，不把所有失败猜测成权限问题。
