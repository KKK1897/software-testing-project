# 原学习版JMeter归档

2026-10-15按用户新要求，默认性能方案迁移为Python版Locust。此目录仅保留原代码、配置和说明，不维护第二套默认性能回归。

|原位置|归档文件|
|---|---|
|beginner/performance/run.py|run.py（原文件备份，原位置现在为Locust runner）|
|beginner/performance/stock-query.jmx|stock-query.jmx（移动归档）|
|beginner/performance/README.md|原README.md（原文备份）|

移动前已检查引用：默认run.py是学习JMX的调用方，已替换；旧质量报告只引用结果目录。父项目旧scripts/run_performance.py引用父performance/stock-query.jmx，均保留原位，没有破坏旧环境脚本。

归档run.py依赖原文件位置计算PROJECT，不能直接在本目录执行；用于阅读原实现。原README命令与相对链接也按原位置解释。若需重现历史方案，应在确认后恢复原相对位置，不直接用归档目录启动。

2026-10-14的原始JTL、日志与中文结论仍在beginner/artifacts/performance及beginner/docs/测试报告.md，没有删除、覆盖或伪装成Locust结果。Java工具包保留，因为ERP后端和Allure仍需要Java环境。
