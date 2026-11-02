# 脚本状态

优先使用安装后的 paperman、paperman-bulk、paperman-doctor 和 python -m paperman.corpus。

- bounded_batch.py：paperman-bulk 的兼容入口。
- web_fetch.py、repository_fetch.py、pdf_probe.py、elsevier_access.py：采集/排查工具，支持 --output 指定数据目录；须先安装本项目，参数见 --help。
- configure_springer.py：本机认证配置辅助工具，不应分享生成的凭据。
- experimental/browser_cdp.py、experimental/browser_cdp.ps1、experimental/browser_publisher_probe.py：浏览器会话实验，依赖 Chrome/CDP，包含 Windows 环境假设。
- experimental/publisher_repair_probe.py、experimental/fullflow_benchmark_monitor.py：针对历史数据集的实验工具，存在固定路径/分组假设，尚未作为可迁移通用入口验证。

后四类实验用途不要直接作为无人值守大规模任务入口。浏览器认证状态留在本机；不要公开个人配置或 Cookie。
