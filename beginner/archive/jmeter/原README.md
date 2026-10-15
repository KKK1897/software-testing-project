# JMeter库存查询

在beginner目录、接口/UI/清理/构建全部结束后执行：

```powershell
../.venv/Scripts/python.exe performance/run.py
```

复用现有JMeter5.6.3和JDK8，不新增Locust。仅维护本目录`stock-query.jmx`作为默认学习方案；旧计划和旧生成器保留原位置作历史资料，不再走默认入口。

脚本取得真实验证码并登录，临时Token写入父项目`runtime/beginner-jmeter.properties`，finally删除。JMX从该属性读取，不含真实凭据。库存查询只指向127.0.0.1:9999，查询`materialParam=QA_`、pageSize=20、zeroStock=0；运行前记录商品总量与匹配量。

|项目|值|
|---|---|
|负载|1、3、5线程闭环逐级串行，每档独立JMeter|
|爬升|每档3秒|
|持续|每档30秒，首个请求起10秒预热剔除，测量约20秒|
|思考时间|每用户请求前200ms，非固定总RPS|
|超时|连接3秒，响应5秒|
|成功判断|HTTP成功且JSON业务code200、data.rows及data.total存在|
|停止条件|可用内存小于1GiB、CPU连续15秒高于90%、每档进程超过65秒立即终止；整档含预热错误率超过5%不再升级|

P50/P95按测量样本排序后线性插值；吞吐=测量样本数/从首个测量请求开始到最后请求完成的时间；错误率用JTL的success统计，业务断言失败也记为错误。JMX无图形监听器，命令行非GUI运行。

输出：`artifacts/performance/日期时间/`内JTL、JMeter日志、stdout、每秒CPU/可用内存及归属本项目的Java/MySQL/Redis进程RSS、summary.json；`latest.txt`指向最新轮次。后端日志按运行开始字节偏移读取新增部分，统计WARN/ERROR及观察行数，不扫描旧故障冒充本轮。

本轮中文结果见[测试报告](../docs/测试报告.md)。只代表本机三个短小负载档位，不代表最大容量、高并发、长时稳定性或生产SLA。宿主其他应用可能影响CPU，不据此猜测数据库瓶颈或进行调优。
