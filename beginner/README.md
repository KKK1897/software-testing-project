# 基于jshERP的进销存接口、UI与性能测试项目

学习内容集中在本文件夹。被测ERP是上游开源软件，固定 **v3.5 / 7ca0f9d68fef761d98b00854d09e975eba291465**；我的成果是测试设计、Requests/Pytest接口自动化、Playwright页面测试、Locust性能测试和缺陷分析。不是自行开发ERP。

测试逻辑统一使用Python：接口用Pytest＋Requests，UI用Python版Playwright，性能用Locust。ERP后端和Allure命令行工具仍依赖原有Java环境。原JMeter计划、代码与结果保留为历史资料，不再作为默认性能入口。

核心业务：A仓采购100件→调拨30件到B仓→B仓销售10件，核对三张单据及A70/B20/总90。基础学习集为19条接口用例、3条UI流程；新增3条[进阶收付款结算用例](docs/进阶收付款链路.md)，覆盖采购付款、销售分次收款、欠款和账户流水。不是全量产品验收；已知权限和库存并发风险见[缺陷记录](docs/缺陷记录.md)。

以下PowerShell命令均从本目录执行：

```powershell
cd E:\Project\Test-Project\jshERP-qa\beginner
$env:PYTHONIOENCODING='utf-8'
../.venv/Scripts/python.exe ../scripts/start_local.py
../.venv/Scripts/python.exe -m pytest tests/test_login.py::test_correct_login
../.venv/Scripts/python.exe -m pytest tests/test_inventory.py::test_stock_chain
../.venv/Scripts/python.exe -m pytest tests/test_settlement.py::test_purchase_payment_transfer_sale_collection
../.venv/Scripts/python.exe -m pytest tests -m 'not ui' --alluredir=artifacts/allure-my-api
../.venv/Scripts/python.exe -m pytest tests/test_ui.py --headed --alluredir=artifacts/allure-my-ui
../.venv/Scripts/python.exe performance/run.py
```

进阶库存查询负载（10/30/50/100用户、每档90秒）及停止条件见[性能说明](performance/README.md)，本轮结果见[逐级负载验证](docs/逐级负载验证.md)。

页面：<http://127.0.0.1:3000>，已有本机初始化账号 `jsh / 123456`，验证码照图输入。环境已初始化，不重复bootstrap；依赖复用父目录`.venv`、`tools`、`runtime`，不要单独搬走本文件夹。

手工调试：导入[Collection](postman/jsherp.collection.json)和[Environment示例](postman/local.environment.example.json)，按[Postman说明](postman/README.md)手动填写密码和验证码。Collection已生成并检查，尚未在Postman中执行。

报告：[接口/UI历史验收](docs/测试报告.md)、[Locust迁移验证](docs/Locust迁移验证.md)、[收付款链路验证](docs/进阶收付款链路.md)。生成自己的统一Allure：

```powershell
$env:JAVA_HOME=(Resolve-Path ../tools/jdk8u472-b08).Path
../tools/allure-2.32.0/bin/allure.bat generate artifacts/allure-my-api artifacts/allure-my-ui -o artifacts/allure-my-report
../tools/allure-2.32.0/bin/allure.bat open artifacts/allure-my-report
```

每轮用新的结果目录；失败有脱敏请求、UI截图和trace。所有产物仅留本机；trace可能含凭据，分享前脱敏。停止ERP：

```powershell
../.venv/Scripts/python.exe ../scripts/stop_local.py
```

开始学习：[快速上手及80分钟路线](docs/快速上手.md) → [业务与用例](docs/业务与测试用例.md)。旧测试、CI及辅助工具的原位置和保留原因见[归档索引](archive/保留与归档.md)。
