# Python性能测试迁移验证

日期：2026-10-15，Australia/Sydney。按本次新要求，默认性能测试从JMeter切换为Locust；接口和UI继续使用原Python测试。被测ERP固定v3.5/7ca0f9d68fef761d98b00854d09e975eba291465，未重写Java业务系统。

## 改了哪些内容

- `performance/locustfile.py`：新增可阅读的Python库存查询任务，检查HTTP200、业务code200、列表结构；保存逐请求记录和失败脱敏响应。
- `performance/run.py`：原命令保持不变，改为启动Locust；支持`--users 1`单档练习，默认1/3/5用户；保留锁、超时、资源停止条件和后端日志观察，自动生成中文报告。
- `performance/test_locustfile.py`：新增离线断言及脱敏检查，不请求ERP，不加入默认19条接口用例。
- `requirements.txt`、`requirements.lock.txt`：加入Locust2.37.5及锁定依赖；安装前已有锁定包版本全部保持。更新README、性能说明和学习路线。
- 学习版JMeter计划移动到`archive/jmeter/stock-query.jmx`，原runner/README也保存备份。父项目旧JMeter环境脚本及全部历史结果保留原位，不维护第二套默认入口。

项目中已有的AI辅助模块及其根README说明保留，没有修改Learning-Agent或其他项目。Postman仍是手工调试材料；其脚本不是默认Python自动化回归的一部分。

默认收集检查还发现现有`test_workbench.py`使用`beginner.ai_testing`导入，而其他测试使用`ai_testing`导入；因此根目录及beginner的pytest.ini补上项目根搜索路径，两份原配置已备份。未改AI模块或断言。当前默认套件除了19接口/3UI，还包含现有4条AI模块测试；本次收集核对不等于将这些测试全部执行通过。

## 实际验证结果

|验证项|状态|实际证据|
|---|---|---|
|ERP启动健康检查|通过|复用原数据库和配置，MySQL13306、Redis16379、后端9999、前端3000健康；未初始化数据库|
|依赖检查|通过|pip check无冲突；Locust2.37.5；[原版本保留核对](../artifacts/locust-dependencies.json)|
|单条正确登录|通过|[locust-login-check.xml](../artifacts/locust-login-check.xml)，1通过|
|Locust1/3/5用户|通过|本轮共934个实际请求，含预热0失败，三个档位真实执行|
|离线断言与脱敏最终检查|通过|[locust-unit-final.xml](../artifacts/locust-unit-final.xml)，9通过，不计作ERP业务覆盖|
|库存链路及浏览器兼容回归|通过|[locust-compatibility-check.xml](../artifacts/locust-compatibility-check.xml)，100→30→10及真实Chromium登录退出共2通过；成功链路定向清理|
|19条接口和3条UI完整重跑|未执行|本轮只跑上述受影响的兼容检查，完整历史结果仍为20通过/2失败，不能宣称产品缺陷已修复|
|Postman本机执行|未执行|保持原状态，无伪造执行结果|

最新Locust2.46.7的安装预检查与Requests2.32.3冲突，因此没有升级Requests，采用兼容版本2.37.5。只在项目`.venv`安装，无全局服务或配置变更。Locust会带入Web界面相关依赖，但本项目只执行本机无界面负载，未启动云服务、测试平台或分布式运行。

离线检查首轮8通过、1准备错误，原因是沙箱临时目录无法创建；[首轮JUnit](../artifacts/locust-unit-check.xml)保留。改用项目内专用临时目录后9条通过，没有跳过、删除断言或重试ERP请求。这里的模拟错误响应只验证测试代码能识别失败，不是产品缺陷证据。

## 本轮Locust负载结果

运行目录：[20261015-021842-127717](../artifacts/locust/20261015-021842-127717)，[实际中文报告](../artifacts/locust/20261015-021842-127717/报告.md)，[summary.json](../artifacts/locust/20261015-021842-127717/summary.json)。

|并发用户|测量样本|P50 ms|P95 ms|吞吐 req/s|含预热失败/总数|
|---|---|---|---|---|---|
|1|72|61.85|80.96|3.610|0/106|
|3|215|59.85|83.21|10.806|0/316|
|5|351|67.66|91.72|17.584|0/512|

每档总30秒，启动速率为用户数/3，目标约3秒爬升；1用户实际首个用户立即生成，实际调度以日志为准。首请求起10秒预热剔除，测量约20秒，任务后思考200ms；连接/响应超时3/5秒。商品总139，QA_筛选匹配67，每页20、隐藏零库存。所有模拟用户使用独立HTTP会话但同一测试账号Token，不是5个真实业务账号。

CPU峰值分别18.7%/17.7%/17.3%，可用内存最低约10.95GiB；后端本轮新增日志22464行，WARN0/ERROR0。记录的是宿主CPU及项目归属服务RSS，不代表后端独占资源；原始样本和日志均保留。

中文统计以完整逐请求CSV剔除预热后计算，P50/P95线性插值、含失败请求；Locust原生HTML包含预热且使用自身百分位口径，数值不同是预期。原生stats CSV是周期快照，可能未包含最后几条请求，例如1用户快照104条、结束汇总及逐请求记录106条；最终次数使用逐请求记录并与结束HTML/终端汇总核对，不以周期CSV当最终总数。

旧JMeter有4个失败样本，本轮Locust未重现；两轮时间、工具和统计条件不同，不能据此认定Redis重置问题修复或系统性能提升。DEF-001/002/003已知风险及历史证据没有删除，不将本轮小负载通过写成全产品质量通过。

## 使用

```powershell
cd E:\Project\Test-Project\jshERP-qa\beginner
$env:PYTHONIOENCODING='utf-8'
../.venv/Scripts/python.exe ../scripts/start_local.py
../.venv/Scripts/python.exe performance/run.py
# 单档练习
../.venv/Scripts/python.exe performance/run.py --users 1
```

不要同时运行接口/UI/清理/构建。先读`locustfile.py`的query_stock；学习Python的字典、with、if以及response.failure/success。runner只负责组织运行，测试参数详见[性能说明](../performance/README.md)。性能脚本不需要Java；固定ERP后端和Allure命令行工具仍使用现成Java环境。

后续每次运行有独立时间目录，不覆盖本轮或历史证据。任意失败使runner返回非零；没有实际样本标准备错误。仅1/3/5用户短时库存查询，不宣传高并发或最大容量。ERP保持运行供学习，停止命令仍使用原scripts/stop_local.py。
