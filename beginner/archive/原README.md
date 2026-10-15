> 历史README存档；原位置jshERP-qa/README.md，历史结果不代表本轮。命令工作目录仍是父项目根目录。

# jshERP 进销存业务测试项目

这是独立的传统软件测试学习项目。被测产品来自 [jishenghua/jshERP](https://github.com/jishenghua/jshERP)，不属于测试项目原创代码。未修改 Learning-Agent，未发布到远程仓库或公共环境。

固定基线为 **v3.5 / 7ca0f9d68fef761d98b00854d09e975eba291465**；该提交许可证是 GPL-3.0。实际本地部署采用便携JDK8u472、Maven3.6.3、MySQL8.0.46独立数据目录、Redis3.2.100及Node24.18.1。基线业务源码保持原样，独立POM将JDBC5.1.30换为5.1.49；数据库连接会话关闭ONLY_FULL_GROUP_BY。这些是实际兼容调整，不是原版原封不动运行。

## 当前真实进展

- 后端登录、会话、商品查询及真实浏览器登录可用。
- 核心链路采购100→A向B调拨30→B销售10通过：A70、B20、总库存90；见 `artifacts/core-scenario.json`。
- 最新统一单次40条：37通过、3产品缺陷失败、0准备错误、0跳过；包含35条接口和5条UI。证据为artifacts/acceptance-junit.xml，历史失败与定向回归报告另存。
- 5条UI在统一运行中全部通过：登录退出、仓库创建、供应商必填、只读按钮限制、页面采购100和销售10后库存90。
- 业务操作员真实完成页面仓库新增及采购销售；只读角色后端仍可新增仓库、并发同号可重复入库，失败断言保留。空单号查询缺陷有隔离补丁及修复后通过证据。
- JMeter真实完成1/3/5用户独占功能测试时段的小负载运行，P95约61.9/62/66ms，业务错误率均0；限定条件与原始结果见性能报告，不推断最大容量。
- GitHub Actions文件已提供；本机完整bootstrap重建与登录验收成功。**远程 CI 尚未执行。** 产品存在未解决缺陷，不给出上线通过结论。

## 在当前机器启动与运行

以下命令均在 `E:\Project\Test-Project\jshERP-qa` 执行；已初始化环境无需再次运行初始化脚本。

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv/Scripts/python.exe scripts/start_local.py
.venv/Scripts/python.exe scripts/core_scenario.py
.venv/Scripts/python.exe -m pytest tests -p no:cacheprovider --junitxml=artifacts/my-run.xml --alluredir=artifacts/allure-my-run
.venv/Scripts/python.exe -m pytest tests/test_api.py -p no:cacheprovider --alluredir=artifacts/allure-api-new
.venv/Scripts/python.exe -m pytest tests/test_ui.py -p no:cacheprovider --alluredir=artifacts/allure-ui-new
.venv/Scripts/python.exe -m pytest tests/test_permissions.py -p no:cacheprovider
.venv/Scripts/python.exe scripts/run_performance.py
```

页面：[本机ERP](http://127.0.0.1:3000)。本机学习库保留官方初始化登录；随机数据库与Redis凭据在被忽略的 `runtime/local.json`，不得提交。身份清单在 `runtime/identities.json`。权限测试有真实产品缺陷，非零退出是当前正确结果。

不要同时运行多个写入测试/清理任务。测试使用唯一标识，默认保留数据便于复查。添加`--cleanup-passed`可由fixture清理通过用例，失败数据留存；API和UI两种链路已实际验证该模式。也可按指定manifest清理：

```powershell
.venv/Scripts/python.exe scripts/cleanup_data.py artifacts/data-manifests/QA_实际标识.json
```

清理脚本先通过只读SQL验证数据库名及数据目录，再经业务API逆序清理；新UI单据按登记ID/单号和明细条码校验。不会清库；复杂状态、部分创建失败会明确拒绝。未登记的早期探索数据暂留。

## 目录归属

|目录|内容|
|---|---|
|upstream/jshERP|固定上游源码、编译产物（不计原创成果）|
|scripts、tests|本测试项目脚本、Pytest与Playwright用例|
|locks、requirements.lock.txt|实际依赖锁|
|runtime|本机数据、配置、隔离补丁编译树；不提交|
|artifacts|真实请求、截图、trace、JMeter原始结果、历史失败报告；默认不提交|
|patches|可审查的最小产品修复补丁|
|docs|中文业务分析、问题与交接文档|

首次部署使用`python scripts/bootstrap.py`（要求Python3.13.2、PowerShell7、Git与下载网络）；已有环境不必重复初始化。停止用`.venv/Scripts/python.exe scripts/stop_local.py`。

文档入口：[最终质量报告](../../docs/最终质量报告.md)、[部署排障](../../docs/环境部署与排障.md)、[业务与测试计划](../../docs/业务规则与测试计划.md)、[用例映射](../../docs/测试用例与规则映射.md)、[缺陷记录](../../docs/缺陷与问题记录.md)、[自动化/CI](../../docs/自动化与CI使用说明.md)、[性能](../../docs/性能测试报告.md)、[最小SQL](../../docs/最小SQL说明.md)、[面试及10分钟演示](../../docs/面试与演示草稿.md)、[交接清单](../../docs/交接进度.md)。
