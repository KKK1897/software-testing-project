# Python＋Locust库存查询

测试代码统一使用Python。先读`locustfile.py`中的`InventoryUser.query_stock`：它发送库存查询请求并检查HTTP和业务响应。`run.py`负责登录、按档位启动Locust、资源监控和生成中文报告。

从beginner目录执行：

```powershell
$env:PYTHONIOENCODING='utf-8'
../.venv/Scripts/python.exe ../scripts/start_local.py
# 完整1/3/5用户逐级执行
../.venv/Scripts/python.exe performance/run.py
# 只练习1用户，约半分钟
../.venv/Scripts/python.exe performance/run.py --users 1
# 进阶逐级负载：10/30/50/100用户，每档90秒，预热30秒
../.venv/Scripts/python.exe performance/run.py --users 10 30 50 100 --duration 90 --warmup 30 --spawn-rate 5
```

本机已在父项目`.venv`安装Locust2.37.5，无需重新安装或启动Java性能工具。接口/UI原依赖版本保持不变；完整Windows依赖锁在父目录requirements.lock.txt。换环境时在项目虚拟环境安装，不全局安装：

```powershell
../.venv/Scripts/python.exe -m pip install -r ../requirements.lock.txt
```

默认通过runner启动无界面负载；不要直接启动locustfile或同时跑接口、UI、清理、构建。执行锁与原套件共用，Token通过子进程环境传入，不写磁盘、日志或命令行。只允许127.0.0.1:9999，不关闭验证码、不重试失败请求。没有启用Locust云服务或分布式执行。

|项目|配置|
|---|---|
|用户|默认1、3、5；可选10、30、50、100，闭环并发，档位升序串行，每档独立进程|
|身份|独立HTTP会话，共用一个测试账号Token；不是多个业务账号|
|爬升|默认用户数/3；进阶每秒新增5用户，100用户约20秒，实际达到人数另存证据|
|持续|默认30秒、预热10秒；进阶90秒、预热30秒，测量约60秒；结束最多等5秒完成请求|
|思考|每个任务执行后200ms，非固定总RPS|
|接口|库存列表，QA_筛选、每页20条、隐藏零库存|
|超时|连接3秒、响应5秒；不跟随重定向|
|断言|HTTP200、JSON业务code200、data对象、rows数组、total数字|
|停止|可用内存<1GiB、CPU连续15次采样>90%、超过计划时长35秒；整档含预热错误率>5%或测量P95>2000ms不再升级|
|结果|有任何失败样本即标为失败，runner返回1；无实际请求为准备错误|

输出保存在`artifacts/locust/日期时间/`，latest.txt指向最新轮次：

- `报告.md`、`summary.json`：这轮中文结论、P50/P95、吞吐、错误率、CPU/内存及后端日志观察。
- `1users.samples.csv`等：逐请求时间、HTTP状态、业务码和成功情况，包含预热。
- `*.failures.jsonl`：发生失败时保存脱敏响应，无失败时不生成该文件。
- `1users.html`及`*_stats.csv`等：Locust原生报告，包含预热。
- `*.resources.json`、`*.stdout.log`、`*.log`：资源样本和执行日志。

中文统计从逐请求CSV剔除预热，P50/P95按耗时排序后线性插值，包含失败请求；吞吐=测量样本数/首个测量请求开始到最后一个完成的秒数。Locust原生HTML采用自身口径且包含预热，不能混算。原生stats CSV为周期快照，可能漏掉结束前最后几条请求，最终次数看逐请求CSV和结束HTML/终端汇总。记录请求和校验响应有客户端开销，不能与旧JMeter数值直接比较并宣称性能变好。

CPU为宿主总使用率；服务RSS仅记录命令行归属本项目的Java/MySQL/Redis。后端日志按本轮开始字节偏移观察新增部分，WARN/ERROR与失败响应需要结合分析，不直接认定根因。

本轮迁移验证见[报告](../docs/Locust迁移验证.md)。旧JMeter代码和计划见[归档](../archive/jmeter/README.md)，历史证据仍保留。性能测试本身不需要Java，固定ERP后端和Allure工具仍依赖原Java环境。只有短时1/3/5用户，不能据此宣传高并发、最大容量或长时稳定性。

进阶结果见[逐级负载验证](../docs/逐级负载验证.md)。1、3、5是三档人数，并非三个用户总共运行；100用户也不是100个请求同时到达。每个用户完成一次查询并等待200ms后再发下一次，实际吞吐与响应时间有关。同一个Token代表一个账号身份，不能描述为100个不同账号同时登录。这里只测库存查询，不包含写入、收付款或登录并发。90秒属于短时负载，尚不能验证长时稳定性。

Locust基础用法参考[官方任务说明](https://docs.locust.io/en/2.37.5/writing-a-locustfile.html)。
