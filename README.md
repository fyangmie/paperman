# Paperman：可迁移的文献采集分支

本分支仓库：[fyangmie/paperman](https://github.com/fyangmie/paperman)。

基于 [laq12345/paperman](https://github.com/laq12345/paperman) 的社区修改版本，保留原作者署名和 MIT 许可。上游基线为提交 a8df113；本分支增加网络诊断、批次记录、HTML/XML 采集和迁移支持，不是上游官方发布。

## 安装与使用

支持 Python 3.11+，批量进程控制面向 Linux / Windows WSL。当前本机验证环境为 Linux Python 3.12；原生 Windows 批量控制尚未支持。

```bash
git clone https://github.com/fyangmie/paperman.git
cd paperman
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements-tested.txt '.[dev]'
paperman-doctor
paperman-bulk /absolute/path/dois.txt --output /absolute/path/pdf-task --timeout 180
```

DOI 文件每行一条。再次运行同一命令会检查已有 PDF、跳过可读文件并重试失败项。每篇 DOI 有独立超时；超时后继续下一篇。需要人工复核的文件标记 needs_review。记录的 DOI 文本命中并不等同于完整内容人工审查。

HTML/XML 是独立的语料采集流程：

```bash
python -m paperman.corpus discover --identifiers /absolute/path/dois.txt --config examples/corpus.toml -o /absolute/path/corpus
python -m paperman.corpus fetch --formats html,xml --resume -o /absolute/path/corpus
python -m paperman.corpus report -o /absolute/path/corpus
```

请先按 [迁移与网络配置](docs/MIGRATION.md) 配好新设备。学校 VPN、代理和网站登录是不同层面的状态；可用性需要在目标设备上实测。

## 下载流程

PDF 获取元数据后，按已有 arXiv 编号 → PMC → Sci-Hub → 出版社尝试；失败等待 3 秒再试一轮；仍失败才用标题检索 arXiv，并保守匹配 DOI 或标题与作者。默认来源顺序保留本分支既有设置；paperman-bulk 的 --sources 和 --retries 可覆盖本次任务设置。

HTML/XML 不由 PDF 下载成功自动产生；正文识别、机构访问、API 或仓储资源情况分别记录。具体入口见 [CORPUS.md](CORPUS.md)。

## 记录与复现

- [本轮验收记录](docs/ACCEPTANCE.md)
- [修改范围与已知限制](docs/CHANGES.md)
- [迁移、恢复、代理设置](docs/MIGRATION.md)
- [脚本用途与实验边界](scripts/README.md)
- [上游原始说明](docs/UPSTREAM_README.md)
- [MIT 许可证](LICENSE)

requirements-tested.txt 记录本次验证环境的精确依赖版本，供 pip 约束使用；它不是覆盖所有平台的带哈希锁文件。旧 pixi 配置保留用于上游兼容，尚未重新生成其锁文件；本分支以以上 pip 安装方式为验证入口。

发布代码时保留 LICENSE 和上游来源说明。下载语料、认证配置、浏览器数据和任务日志留在仓库外；本分支不附带个人语料库。
